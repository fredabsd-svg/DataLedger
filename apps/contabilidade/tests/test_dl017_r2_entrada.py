"""Correções R2-4 e R2-7 da rodada 2 da auditoria da DL-017
(docs/auditorias/2026-09-14-dl-017-rodada-2.md).

R2-4 — byte nulo em `historico`/`chave_idempotencia`, nas DUAS portas: um
POST com `\\x00` chegava ao INSERT do Postgres e derrubava com
`django.db.utils.DataError: PostgreSQL text fields cannot contain NUL (0x00)
bytes` — 500 cru, tanto pela tela (`views_web.py`) quanto pela API
(`views.py`), porque as duas leem esses dois campos "à mão" (sem
`ModelForm`/`ModelSerializer`, que teriam a recusa embutida). Corrigido em
`apps.contabilidade.services.criar_lancamento` — o único ponto por onde as
duas portas passam para gravar (AGENTS.md §8: não duplicar regra entre tela
e API); a recusa vira `LancamentoInvalido`, que as duas views já traduzem
para 400 com mensagem própria.

R2-7 — `apps.core.dinheiro.PADRAO_VALOR_DECIMAL_SIMPLES` usava `\\d`, que
casa QUALQUER dígito decimal Unicode (fullwidth, índico-arábico, tailandês
etc.), não só ASCII. Corrigido para `[0-9]`.

Usa o urlconf real (`config/urls.py`), como os demais testes de integração
da DL-017 (`contabilidade_web:` para a tela, `contabilidade:` para a API).
Dados 100% sintéticos, criados nos próprios testes. Este arquivo NÃO importa
fixtures de `test_dl017_rodada1_correcoes.py` (arquivo do
`especialista-frontend`, em edição paralela nesta mesma rodada) — os
auxiliares abaixo são próprios, para não acoplar este teste a uma mudança
concorrente em outro arquivo.
"""

from datetime import date
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
from apps.contabilidade.services import LancamentoInvalido, criar_lancamento
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório R2-entrada", cnpj="22222222000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa R2-entrada Ltda", cnpj="22233344000199"
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
        username="gestora-r2-entrada",
        email="gestora-r2-entrada@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-r2-entrada", password="senha-forte-123")


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _url_api(cen):
    return reverse("contabilidade:lancamentos", args=[cen["empresa"].id])


def _sem_nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


def _post_tela(client, cen, *, historico, chave_idempotencia, valor="10,00"):
    return client.post(
        _url_tela(cen),
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": historico,
            "chave_idempotencia": chave_idempotencia,
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": valor,
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": valor,
        },
    )


def _post_api(client, cen, *, historico, chave_idempotencia, valor="10.00"):
    corpo = {
        "data": timezone.localdate().isoformat(),
        "historico": historico,
        "itens": [
            {"conta": cen["caixa"].id, "tipo": "debito", "valor": valor},
            {"conta": cen["receita"].id, "tipo": "credito", "valor": valor},
        ],
    }
    extra = {}
    if chave_idempotencia is not None:
        extra["HTTP_IDEMPOTENCY_KEY"] = chave_idempotencia
    return client.post(_url_api(cen), corpo, content_type="application/json", **extra)


# ---------------------------------------------------------------------------
# R2-4 — camada de serviço: `criar_lancamento` é o ponto único que fecha as
# duas portas. Testado diretamente primeiro, porque é aqui que a correção
# vive de fato — os testes HTTP abaixo provam que as duas views herdam a
# recusa sem precisar repeti-la.
# ---------------------------------------------------------------------------


def _itens_validos(cen, valor=Decimal("10.00")):
    return [
        {"conta": cen["caixa"], "tipo": TipoPartida.DEBITO, "valor": valor},
        {"conta": cen["receita"], "tipo": TipoPartida.CREDITO, "valor": valor},
    ]


def test_criar_lancamento_recusa_historico_com_byte_nulo(cen):
    with pytest.raises(LancamentoInvalido, match="caractere nulo"):
        criar_lancamento(
            empresa=cen["empresa"],
            data=date(2026, 1, 15),
            historico="Aporte\x00 de capital",
            itens=_itens_validos(cen),
            chave_idempotencia=None,
        )
    assert _sem_nada_gravado()


def test_criar_lancamento_recusa_chave_idempotencia_com_byte_nulo(cen):
    with pytest.raises(LancamentoInvalido, match="caractere nulo"):
        criar_lancamento(
            empresa=cen["empresa"],
            data=date(2026, 1, 15),
            historico="Aporte de capital",
            itens=_itens_validos(cen),
            chave_idempotencia="chave-\x00-ruim",
        )
    assert _sem_nada_gravado()


def test_criar_lancamento_aceita_historico_e_chave_sem_byte_nulo(cen):
    """Controle positivo: a correção não pode ter apertado o caminho normal."""
    lancamento = criar_lancamento(
        empresa=cen["empresa"],
        data=date(2026, 1, 15),
        historico="Aporte de capital, sem nulo",
        itens=_itens_validos(cen),
        chave_idempotencia="chave-normal-sem-nulo",
    )
    assert lancamento.criado_agora is True
    assert LancamentoContabil.objects.count() == 1


# ---------------------------------------------------------------------------
# R2-4 — as duas portas HTTP, campo a campo. Repete a tabela do auditor:
# nenhuma combinação pode dar 500 nem gravar nada; o veredito é sempre 400.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["historico", "chave_idempotencia"])
def test_byte_nulo_na_tela_nunca_500_e_nada_e_gravado(client, cen, campo):
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    historico = "Contém \x00 nulo" if campo == "historico" else "histórico normal"
    chave = "chave-\x00-nula" if campo == "chave_idempotencia" else "chave-tela-normal"

    resposta = _post_tela(client, cen, historico=historico, chave_idempotencia=chave)

    assert resposta.status_code == 400, (campo, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes
    assert "caractere nulo" in resposta.content.decode()


@pytest.mark.parametrize("campo", ["historico", "chave_idempotencia"])
def test_byte_nulo_na_api_nunca_500_e_nada_e_gravado(client, cen, campo):
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    historico = "Contém \x00 nulo" if campo == "historico" else "histórico normal"
    chave = "chave-\x00-nula" if campo == "chave_idempotencia" else "chave-api-normal"

    resposta = _post_api(client, cen, historico=historico, chave_idempotencia=chave)

    assert resposta.status_code == 400, (campo, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes
    assert "caractere nulo" in resposta.content.decode()


def test_byte_nulo_no_campo_data_da_api_continua_400_sem_regressao(client, cen):
    """Controle de regressão: o auditor já media este campo como correto
    (400) antes desta correção — `date.fromisoformat` recusa qualquer texto
    que não seja AAAA-MM-DD, `\\x00` incluso. Confirma que a correção do
    R2-4 (histórico/chave) não precisou mexer neste caminho, que já estava
    certo.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    corpo = {
        "data": "\x00",
        "historico": "data com nulo",
        "itens": [
            {"conta": cen["caixa"].id, "tipo": "debito", "valor": "10.00"},
            {"conta": cen["receita"].id, "tipo": "credito", "valor": "10.00"},
        ],
    }
    resposta = client.post(_url_api(cen), corpo, content_type="application/json")
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes


def test_tela_e_api_gravam_normalmente_sem_byte_nulo(client, cen):
    """Controle positivo, nas duas portas: a correção não pode ter apertado
    o caminho sem `\\x00`."""
    _login(client, cen)

    resposta_tela = _post_tela(
        client, cen, historico="Lançamento normal", chave_idempotencia="k-tela-ok"
    )
    assert resposta_tela.status_code == 302, resposta_tela.status_code

    resposta_api = _post_api(
        client, cen, historico="Lançamento normal", chave_idempotencia="k-api-ok"
    )
    assert resposta_api.status_code == 201, resposta_api.status_code

    assert LancamentoContabil.objects.count() == 2


# ---------------------------------------------------------------------------
# R2-7 — `para_decimal` deixa de aceitar dígito Unicode não latino como
# dinheiro. Os quatro textos medidos pelo auditor.
# ---------------------------------------------------------------------------

TEXTOS_COM_DIGITO_UNICODE_NAO_LATINO = [
    pytest.param("０１０,00", id="fullwidth"),
    pytest.param("10,0０", id="fullwidth-nos-centavos"),
    pytest.param("١٢٣.٤٥", id="indico-arabico"),
    pytest.param("๑๐.00", id="tailandes"),
]


@pytest.mark.parametrize("texto", TEXTOS_COM_DIGITO_UNICODE_NAO_LATINO)
def test_para_decimal_recusa_digito_unicode_nao_latino(texto):
    """R2-7: antes da correção, `para_decimal` aceitava estes quatro textos
    (medido pelo auditor: `'０１０,00'`/`'10,0０'` gravavam 10.00 pela tela,
    `'١٢٣.٤٥'` e `'๑๐.00'` eram aceitos como 123.45/10.00) porque `\\d`
    casa qualquer dígito decimal Unicode. Note: o texto acima tem vírgula
    pt-BR (`'０１０,00'`, `'10,0０'`) só para reproduzir o texto exato do
    achado — `para_decimal` recebe o texto já SEM tradução de locale (essa
    tradução é responsabilidade da view, DE-027/DE-029); aqui testamos o
    módulo monetário isoladamente, como o achado nomeia o defeito: qualquer
    um desses quatro textos, com ponto decimal (formato que `para_decimal`
    aceita) ou não, precisa ser recusado.
    """
    with pytest.raises(ValorMonetarioInvalido):
        para_decimal(texto)


# As mesmas quatro strings, mas já convertidas para o formato com PONTO
# decimal (o que `para_decimal` aceitaria se não fosse pelo dígito Unicode) —
# é a forma mais direta de provar que o defeito é o dígito, não a vírgula.
TEXTOS_COM_DIGITO_UNICODE_FORMATO_PONTO = [
    pytest.param("０１０.00", id="fullwidth-ponto"),
    pytest.param("10.0０", id="fullwidth-nos-centavos-ponto"),
    pytest.param("١٢٣.٤٥", id="indico-arabico-ponto"),
    pytest.param("๑๐.00", id="tailandes-ponto"),
]


@pytest.mark.parametrize("texto", TEXTOS_COM_DIGITO_UNICODE_FORMATO_PONTO)
def test_para_decimal_recusa_digito_unicode_nao_latino_formato_ponto(texto):
    with pytest.raises(ValorMonetarioInvalido):
        para_decimal(texto)


def test_para_decimal_continua_aceitando_digitos_ascii():
    """Controle positivo: a correção não pode ter apertado o formato ASCII
    normal, incluindo o sinal `+` (DE-027 — `+10.00` continua aceito)."""
    assert para_decimal("10.00") == Decimal("10.00")
    assert para_decimal("+10.00") == Decimal("10.00")
    assert para_decimal("-10.00") == Decimal("-10.00")
    assert para_decimal("0.01") == Decimal("0.01")


@pytest.mark.parametrize("texto", TEXTOS_COM_DIGITO_UNICODE_FORMATO_PONTO)
def test_criar_lancamento_recusa_digito_unicode_nao_latino(cen, texto):
    """R2-7 na camada de serviço: `criar_lancamento` delega a `para_decimal`
    via `apps.core.dinheiro.para_decimal` (achado 6 da auditoria de
    2026-09-12) — a recusa do módulo monetário precisa chegar como
    `LancamentoInvalido`, nunca deixar o dígito Unicode ser silenciosamente
    convertido para o valor ASCII equivalente.
    """
    itens = [
        {"conta": cen["caixa"], "tipo": TipoPartida.DEBITO, "valor": texto},
        {"conta": cen["receita"], "tipo": TipoPartida.CREDITO, "valor": texto},
    ]
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cen["empresa"],
            data=date(2026, 1, 15),
            historico="dígito Unicode não latino",
            itens=itens,
            chave_idempotencia=None,
        )
    assert _sem_nada_gravado()
