"""RC-78 / BL-159 (estorno nunca anterior ao lançamento que reverte) e
RC-79 / BL-160 (teto de 200 partidas), as duas confirmadas pelo Fred em
2026-09-15 (docs/projeto/requisitos.md).

**RC-78 — o que o auditor mediu** (achado R6-4c da rodada 6): o estorno
recebia `timezone.localdate()` SEMPRE, sem nenhuma comparação com a data do
original. Lançamento datado `2027-03-10`, estornado hoje:

    original data=2027-03-10 / estorno data=2026-09-14 / estorno anterior: True

O Diário mostrava a reversão acontecendo antes do fato que ela reverte. E a
frase que justifica este arquivo existir: **"o mutante M16, que faz o estorno
herdar a data do original, sobrevive a 766 testes com 0 mortes"** — a regra
não tinha teste em nenhum dos dois sentidos. O Fred escolheu **recusar**, não
"permitir desde que registrado".

**RC-79 — o teto era um número de TELA.** `LINHAS_MAXIMAS_LANCAMENTO` vivia em
`views_web.py`, e por isso a API não tinha teto nenhum (item 2 da DE-034: o
mesmo campo na superfície ao lado). A recusa passa a ser de domínio, em
`criar_lancamento`, e **nunca truncamento** (BL-91).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
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
    LIMITE_PARTIDAS_POR_LANCAMENTO,
    LancamentoInvalido,
    criar_lancamento,
    estornar_lancamento,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório RC-78/79", cnpj="55555555000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa RC-78/79 Ltda", cnpj="55566677000111"
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
        username="gestora-rc78",
        email="gestora-rc78@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _lancamento(cenario, data, *, valor="100.00"):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico=f"Lançamento de {data}",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


# ---------------------------------------------------------------------------
# RC-78 — estorno nunca anterior ao original
# ---------------------------------------------------------------------------


def test_estorno_de_lancamento_futuro_e_recusado(cenario):
    """O caso exato do achado: lançamento datado no FUTURO (o que a faixa do
    RC-77 permite até hoje + 30 dias), estornado hoje — o estorno ficaria
    ANTERIOR ao fato que reverte."""
    futuro = timezone.localdate() + timedelta(days=10)
    original = _lancamento(cenario, futuro)

    with pytest.raises(LancamentoInvalido) as erro:
        estornar_lancamento(original)

    assert "anterior" in str(erro.value)
    # A mensagem nomeia as duas datas: sem elas, o contador não sabe se o
    # problema é o original ou o estorno.
    assert futuro.strftime("%d/%m/%Y") in str(erro.value)
    # Nada gravado: continua existindo só o original.
    assert LancamentoContabil.objects.count() == 1
    assert not original.estornos.exists()


def test_estorno_com_data_explicita_anterior_ao_original_e_recusado(cenario):
    original = _lancamento(cenario, date(2024, 6, 10))

    with pytest.raises(LancamentoInvalido):
        estornar_lancamento(original, data=date(2024, 6, 9))

    assert LancamentoContabil.objects.count() == 1


def test_estorno_na_mesma_data_do_original_e_aceito(cenario):
    """A regra é "nunca ANTERIOR", não "sempre posterior": estornar no mesmo
    dia é rotina (erro percebido na hora) e continua valendo."""
    original = _lancamento(cenario, date(2024, 6, 10))

    estorno = estornar_lancamento(original, data=date(2024, 6, 10))

    assert estorno.data == original.data
    assert estorno.estorno_de_id == original.pk


def test_estorno_posterior_continua_funcionando(cenario):
    original = _lancamento(cenario, date(2024, 6, 10))

    estorno = estornar_lancamento(original)

    assert estorno.data == timezone.localdate()
    assert estorno.data >= original.data


def test_estorno_nunca_herda_a_data_do_original(cenario):
    """Mata o mutante M16 do auditor (o que sobreviveu a 766 testes): fazer o
    estorno HERDAR a data do original produziria um estorno datado no passado
    para um lançamento antigo — plausível de passar desapercebido, porque a
    regra "nunca anterior" continuaria satisfeita por igualdade.

    Por isso o teste fixa a regra nos DOIS sentidos: sem `data`, o estorno é
    de HOJE (e não a do original); com `data` anterior, recusa."""
    original = _lancamento(cenario, date(2024, 1, 5))

    estorno = estornar_lancamento(original)

    assert estorno.data == timezone.localdate()
    assert estorno.data != original.data


def test_estorno_pela_api_de_lancamento_futuro_devolve_400(client, cenario):
    """Mesma regra pela porta da API — é ela que o contador usa por
    integração, e é onde o estorno não aceita data nenhuma do cliente."""
    assert client.login(username="gestora-rc78", password="senha-forte-123")
    original = _lancamento(cenario, timezone.localdate() + timedelta(days=5))

    resposta = client.post(
        reverse("contabilidade:estornar", args=[cenario["empresa"].id, original.pk])
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == 1


# ---------------------------------------------------------------------------
# RC-79 — teto de 200 partidas, com recusa e nunca truncamento
# ---------------------------------------------------------------------------


def _itens_balanceados(cenario, quantidade):
    """`quantidade` partidas, metade débito e metade crédito, somando igual.

    Valor fixo de 1,00 em cada lado: o objetivo é contar partidas, não somar
    dinheiro, e um lote balanceado garante que a recusa testada é a do TETO e
    não a da igualdade débito = crédito.
    """
    itens = []
    for indice in range(quantidade):
        tipo = TipoPartida.DEBITO if indice % 2 == 0 else TipoPartida.CREDITO
        conta = cenario["caixa"] if indice % 2 == 0 else cenario["receita"]
        itens.append({"conta": conta, "tipo": tipo, "valor": Decimal("1.00")})
    return itens


def test_teto_exato_de_200_partidas_grava(cenario):
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=timezone.localdate(),
        historico="200 partidas",
        itens=_itens_balanceados(cenario, LIMITE_PARTIDAS_POR_LANCAMENTO),
    )

    assert lancamento.itens.count() == LIMITE_PARTIDAS_POR_LANCAMENTO


def test_uma_partida_acima_do_teto_e_recusada_e_nada_e_gravado(cenario):
    """Recusa EXPLÍCITA, nunca truncamento (BL-91): truncar gravaria um lote
    menor do que o enviado — e, pior, provavelmente desbalanceado — com
    aparência de sucesso."""
    with pytest.raises(LancamentoInvalido) as erro:
        criar_lancamento(
            empresa=cenario["empresa"],
            data=timezone.localdate(),
            historico="201 partidas",
            itens=_itens_balanceados(cenario, LIMITE_PARTIDAS_POR_LANCAMENTO + 1),
        )

    mensagem = str(erro.value)
    assert str(LIMITE_PARTIDAS_POR_LANCAMENTO) in mensagem
    assert "201" in mensagem
    assert not LancamentoContabil.objects.exists()
    assert not ItemLancamento.objects.exists()


def test_api_herda_o_teto_sem_declarar_numero_nenhum(client, cenario):
    """O ponto do item 2 da DE-034: antes da BL-160 o teto era um número de
    TELA (`LINHAS_MAXIMAS_LANCAMENTO`, em `views_web.py`) e a API não tinha
    teto nenhum. Agora a recusa é de domínio e vale nas duas portas."""
    assert client.login(username="gestora-rc78", password="senha-forte-123")
    itens = [
        {
            "conta": (cenario["caixa"] if indice % 2 == 0 else cenario["receita"]).id,
            "tipo": "debito" if indice % 2 == 0 else "credito",
            "valor": "1.00",
        }
        for indice in range(LIMITE_PARTIDAS_POR_LANCAMENTO + 1)
    ]

    resposta = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        {"data": timezone.localdate().isoformat(), "historico": "201 pela API", "itens": itens},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content[:300])
    assert str(LIMITE_PARTIDAS_POR_LANCAMENTO) in resposta.content.decode()
    assert not LancamentoContabil.objects.exists()


def test_teto_de_negocio_e_o_numero_confirmado_pelo_fred(cenario):
    """O valor é regra de produto (RC-79), não detalhe de implementação: se
    alguém o mudar, a mudança precisa passar por uma decisão registrada e por
    este teste — que é onde está escrito de onde o número veio."""
    assert LIMITE_PARTIDAS_POR_LANCAMENTO == 200
