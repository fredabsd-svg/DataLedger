"""RC-77 / BL-158 — faixa de data de lançamento: 01/01/2000 a hoje + 30 dias.

Regra **confirmada pelo Fred em 2026-09-15** (docs/projeto/requisitos.md,
RC-77), em resposta a proposta do `arquiteto-senior`. Nada aqui é hipótese.

O defeito, medido pelo auditor na rodada 6 (achado R6-4): `data` de
`0001-01-01`, `9999-12-31`, `1500-06-15` e `2999-01-01` eram aceitas com
**201** pela API e **302** pela tela. E o efeito, que é a razão declarada de a
DL-019 existir antes da DL-010: um lançamento de 5.000,00 datado `9999-12-31`
**não aparece em nenhuma tela de operação normal** — nem Diário, nem Razão,
nem Balancete, nem Conferência —, o balancete do período CONCILIA e nenhuma
conferência acusa.

Este arquivo cobre as três superfícies onde a faixa precisa valer:

1. o **domínio** (`criar_lancamento`), por onde tela e API passam;
2. a **API**;
3. o **modelo** (`LancamentoContabil.data`, validador de campo), que é o que
   faz `full_clean()` — e portanto qualquer `ModelForm`, inclusive o do admin
   — respeitar a faixa.

A tela tem os testes do `especialista-frontend` (`test_dl019_frontend*`).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    DATA_MINIMA_LANCAMENTO,
    DIAS_FUTUROS_MAXIMOS_LANCAMENTO,
    LancamentoInvalido,
    criar_lancamento,
    data_maxima_lancamento,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório RC-77", cnpj="44444444000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa RC-77 Ltda", cnpj="44455566000199"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-rc77",
        email="gestora-rc77@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _itens(cenario):
    return [
        {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
        {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
    ]


def _criar(cenario, data):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico="RC-77",
        itens=_itens(cenario),
    )


def _post(client, cenario, data_texto):
    return client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        {
            "data": data_texto,
            "historico": "RC-77 pela API",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["receita"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )


def _nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


# ---------------------------------------------------------------------------
# 1. Domínio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data_fora",
    [
        date(9999, 12, 31),  # `date.max`, o caso do achado: um 9 no lugar do 2
        date(2999, 1, 1),
        date(1500, 6, 15),
        date(1, 1, 1),
        date(1999, 12, 31),  # um dia antes do piso
    ],
)
def test_data_fora_da_faixa_e_recusada_pelo_dominio(cenario, data_fora):
    with pytest.raises(LancamentoInvalido) as erro:
        _criar(cenario, data_fora)

    # A mensagem diz a faixa inteira: quem errou o ano precisa saber qual ano
    # cabe, não só que "a data é inválida".
    assert "fora da faixa" in str(erro.value)
    assert _nada_gravado()


def test_data_futura_alem_do_teto_e_recusada(cenario):
    """O teto se move com "hoje", então o caso-limite é calculado, nunca
    escrito como literal — um literal passaria a testar outra coisa amanhã."""
    um_dia_depois_do_teto = data_maxima_lancamento() + timedelta(days=1)

    with pytest.raises(LancamentoInvalido):
        _criar(cenario, um_dia_depois_do_teto)

    assert _nada_gravado()


@pytest.mark.parametrize("deslocamento", [0, 1, DIAS_FUTUROS_MAXIMOS_LANCAMENTO])
def test_datas_dentro_da_faixa_continuam_gravando(cenario, deslocamento):
    """Controle positivo, nas bordas: hoje, amanhã e o último dia aceito
    (hoje + 30) gravam. Sem isto, a correção poderia ter fechado a porta
    inteira e "passado" no teste negativo."""
    lancamento = _criar(cenario, timezone.localdate() + timedelta(days=deslocamento))

    assert lancamento.pk is not None
    assert lancamento.data == timezone.localdate() + timedelta(days=deslocamento)


def test_borda_inferior_exata_e_aceita(cenario):
    lancamento = _criar(cenario, DATA_MINIMA_LANCAMENTO)

    assert lancamento.data == DATA_MINIMA_LANCAMENTO


def test_data_que_nao_e_date_puro_e_recusada_como_erro_de_dominio(cenario):
    """`datetime` é subclasse de `date` e passaria num `isinstance` ingênuo: o
    campo é `DateField`, então ele seria TRUNCADO na gravação, e a comparação
    de faixa estouraria `TypeError` cru. Texto idem."""
    for valor in (timezone.now(), "2026-01-15", 20260115, None):
        with pytest.raises(LancamentoInvalido):
            _criar(cenario, valor)

    assert _nada_gravado()


# ---------------------------------------------------------------------------
# 2. API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("data_texto", ["9999-12-31", "1500-06-15", "0001-01-01", "1999-12-31"])
def test_api_recusa_data_fora_da_faixa_com_400(client, cenario, data_texto):
    assert client.login(username="gestora-rc77", password="senha-forte-123")

    resposta = _post(client, cenario, data_texto)

    assert resposta.status_code == 400, (data_texto, resposta.status_code, resposta.content)
    assert _nada_gravado()


def test_api_aceita_data_no_teto_e_recusa_um_dia_depois(client, cenario):
    assert client.login(username="gestora-rc77", password="senha-forte-123")
    teto = data_maxima_lancamento()

    no_teto = _post(client, cenario, teto.isoformat())
    depois = _post(client, cenario, (teto + timedelta(days=1)).isoformat())

    assert no_teto.status_code == 201, (no_teto.status_code, no_teto.content)
    assert depois.status_code == 400, (depois.status_code, depois.content)
    assert LancamentoContabil.objects.count() == 1


# ---------------------------------------------------------------------------
# 3. Modelo (o que faz `full_clean()`/`ModelForm`/admin respeitarem a faixa)
# ---------------------------------------------------------------------------


def test_full_clean_do_modelo_recusa_data_fora_da_faixa(cenario):
    """Item 2 da DE-034 — o mesmo campo nas outras superfícies. Quem grava por
    `ModelForm` (admin) não passa por `criar_lancamento`, e sem o validador de
    campo criaria um lançamento em `9999-12-31` — invisível em todas as saídas
    de uso normal, que é o BL-151 inteiro por outra porta."""
    lancamento = LancamentoContabil(
        empresa=cenario["empresa"], data=date(9999, 12, 31), historico="pelo admin"
    )

    with pytest.raises(ValidationError) as erro:
        lancamento.full_clean()

    assert "data" in erro.value.message_dict
    assert "fora da faixa" in erro.value.message_dict["data"][0]


def test_full_clean_do_modelo_aceita_data_na_faixa(cenario):
    lancamento = LancamentoContabil(
        empresa=cenario["empresa"], data=timezone.localdate(), historico="pelo admin"
    )

    lancamento.full_clean()  # não levanta


def test_admin_continua_recusando_criacao_de_lancamento_por_permissao(client, cenario):
    """Limite DECLARADO, e não cobertura: no admin, `LancamentoContabilAdmin`
    já recusa inclusão e alteração por permissão (`has_add_permission` e
    `has_change_permission` devolvem `False`), então a faixa de data nem chega
    a ser exercida por ali — o POST responde 403 antes.

    O teste existe para que essa afirmação seja VERIFICADA e não presumida: se
    alguém reabrir a inclusão pelo admin no futuro, este teste falha e obriga
    a decidir conscientemente (o validador de campo acima é o que segura a
    faixa nesse cenário). Ver também
    `test_dl015_saidas_com_periodo.py::test_admin_recusa_inclusao_de_lancamento_nos_tres_casos_do_relatorio`.
    """
    admin = get_user_model().objects.create_superuser(
        username="admin-rc77", email="admin-rc77@escritorio.com.br", password="senha-forte-123"
    )
    assert admin.is_superuser
    assert client.login(username="admin-rc77", password="senha-forte-123")

    resposta = client.post(
        "/admin/contabilidade/lancamentocontabil/add/",
        {
            "empresa": cenario["empresa"].id,
            "data": "9999-12-31",
            "historico": "tentativa pelo admin",
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-conta": cenario["caixa"].id,
            "itens-0-tipo": "debito",
            "itens-0-valor": "100.00",
            "itens-1-conta": cenario["receita"].id,
            "itens-1-tipo": "credito",
            "itens-1-valor": "100.00",
        },
    )

    assert resposta.status_code == 403, resposta.status_code
    assert _nada_gravado()
