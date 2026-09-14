"""Achado R3-3 da auditoria DL-017, rodada 3
(docs/auditorias/2026-09-14-dl-017-rodada-3.md), governado pela DE-030
(docs/projeto/decisoes.md).

Antes desta correção, `apps.contabilidade.views._extrair_itens` fazia
`str(valor_bruto)` e depois `Decimal(texto_valor)` — reimplementava a
checagem de `apps.core.dinheiro.para_decimal` com a mesma expressão regular,
em vez de chamá-lo, e nunca recusava `valor` que chegasse como NÚMERO JSON.
Um número JSON vira `float` de precisão binária no Python assim que o corpo
da requisição é decodificado — antes de qualquer julgamento deste módulo —,
e para magnitudes grandes (acima de ~7×10¹³, medido pelo auditor) o `float`
já tinha perdido a última casa decimal: `99999999999999.99` enviado como
número era gravado como `99999999999999.98`, HTTP 201, sem uma palavra. É o
bloqueador da rodada 2 (R2-1, `apps/core/tests/test_dinheiro.py` e
`test_dl017_r2_entrada.py`) na outra porta.

DE-030 institui, para todo caminho de entrada de valor monetário: (1)
nenhuma camada constrói `Decimal` a partir de entrada de cliente — só
`para_decimal` julga; (2) valor que chegue como número (não texto) é
recusado na fronteira, com mensagem própria; (3) cada caminho declara sua
gramática. Este arquivo testa a API (o caminho que a DE-030 fecha) — a tela
já está coberta por `test_dl017_r2_entrada.py`/`test_dinheiro.py` (R2-7) e
pelos testes do `especialista-frontend` (R2-1).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
)
from apps.contabilidade.services import criar_lancamento
from apps.core.dinheiro import para_decimal
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DE-030", cnpj="33333333000144")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DE-030 Ltda", cnpj="33344455000188"
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
        username="gestora-de030", email="gestora-de030@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _cliente_autenticado(client, cenario):
    assert client.login(username="gestora-de030", password="senha-forte-123")


def _sem_nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


def _post_lancamento(client, cenario, *, valor, chave=None):
    corpo = {
        "data": "2026-01-15",
        "historico": "R3-3 / DE-030",
        "itens": [
            {"conta": cenario["caixa"].id, "tipo": "debito", "valor": valor},
            {"conta": cenario["receita"].id, "tipo": "credito", "valor": valor},
        ],
    }
    extra = {}
    if chave is not None:
        extra["HTTP_IDEMPOTENCY_KEY"] = chave
    return client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
        **extra,
    )


# ---------------------------------------------------------------------------
# A tabela do auditor: os quatro valores medidos, na API real, com leitura
# do banco. Os três primeiros SÃO o defeito (número JSON grande, perde
# precisão); o quarto é o controle de que um número "pequeno" gravava
# corretamente (o "protegido por acidente de escala" que o achado nomeia) —
# hoje os quatro devem ser recusados, porque nenhum foi enviado como texto.
# ---------------------------------------------------------------------------

VALORES_NUMERO_JSON = [
    pytest.param(99999999999999.99, id="99999999999999_99"),
    pytest.param(70368744177664.01, id="70368744177664_01"),
    pytest.param(562949953421312.07, id="562949953421312_07"),
    pytest.param(1000.00, id="1000_00-controle-antes-protegido-por-acidente"),
]


@pytest.mark.parametrize("valor_numero", VALORES_NUMERO_JSON)
def test_valor_como_numero_json_e_recusado_nunca_grava_valor_diferente(
    client, cenario, valor_numero
):
    """R3-3: antes da correção, os três primeiros valores eram gravados
    DIFERENTES do enviado (ex.: 99999999999999.99 -> 99999999999999.98),
    com HTTP 201 — sucesso silencioso. Depois da correção, NENHUM número
    JSON é aceito: a API recusa antes de qualquer conversão, nunca grava.
    """
    _cliente_autenticado(client, cenario)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, valor=valor_numero, chave=f"num-{valor_numero!r}")

    assert resposta.status_code == 400, (valor_numero, resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
    assert _sem_nada_gravado()
    assert "TEXTO" in resposta.content.decode()


def test_1e3_como_texto_e_como_numero_recebe_o_mesmo_veredito(client, cenario):
    """Medição do auditor: `1e3` enviado como TEXTO já dava 400 (notação
    científica recusada); `1e3` enviado como NÚMERO JSON contornava essa
    recusa e gravava 1000,00. Depois da correção, os dois são 400 — o
    número, por não ser texto; o texto, por notação científica.
    """
    _cliente_autenticado(client, cenario)

    resposta_texto = _post_lancamento(client, cenario, valor="1e3", chave="1e3-texto")
    assert resposta_texto.status_code == 400, resposta_texto.status_code

    resposta_numero = _post_lancamento(client, cenario, valor=1e3, chave="1e3-numero")
    assert resposta_numero.status_code == 400, resposta_numero.status_code

    assert _sem_nada_gravado()


@pytest.mark.parametrize("valor_numero", [1, 100, -50, 0])
def test_valor_como_int_json_tambem_e_recusado(client, cenario, valor_numero):
    """DE-030 recusa NÚMERO (não só `float`) — um `int` JSON pequeno não
    perde precisão, mas ainda assim não é texto, e a decisão é sobre a
    FORMA de envio, não sobre a magnitude."""
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(client, cenario, valor=valor_numero, chave=f"int-{valor_numero}")
    assert resposta.status_code == 400, (valor_numero, resposta.status_code)
    assert _sem_nada_gravado()


def test_valor_bool_json_e_recusado(client, cenario):
    """`bool` é subclasse de `int` em Python e chega decodificado como tal
    pelo parser JSON — continua sendo NÚMERO, não texto, e cai na mesma
    recusa (reforça, na fronteira da API, a mesma regra que `para_decimal`
    já aplica para `bool` explícito)."""
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(client, cenario, valor=True, chave="bool-true")
    assert resposta.status_code == 400, resposta.status_code
    assert _sem_nada_gravado()


def test_valor_null_json_e_recusado(client, cenario):
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(client, cenario, valor=None, chave="null")
    assert resposta.status_code == 400, resposta.status_code
    assert _sem_nada_gravado()


def test_valor_como_texto_continua_gravando_exatamente_o_enviado(client, cenario):
    """Controle positivo: o caminho normal (texto) não pode ter sido
    afetado — e o valor gravado é exatamente o Decimal que o texto
    significa, inclusive nas magnitudes grandes que expunham o R3-3."""
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(client, cenario, valor="99999999999999.99", chave="texto-grande")
    assert resposta.status_code == 201, (resposta.status_code, resposta.content)

    item = ItemLancamento.objects.get(conta=cenario["caixa"])
    assert item.valor == Decimal("99999999999999.99")


# ---------------------------------------------------------------------------
# A view não constrói `Decimal` a partir de entrada de cliente (DE-030 §1):
# verificação estática de que o padrão antigo (`str(...)` seguido de
# `Decimal(texto)` sobre o valor do item) não está mais presente.
# ---------------------------------------------------------------------------


def test_views_da_api_nao_constroem_decimal_a_partir_de_texto_de_cliente():
    import inspect

    from apps.contabilidade import views as views_modulo

    codigo_fonte = inspect.getsource(views_modulo._extrair_itens)
    assert "Decimal(texto_valor)" not in codigo_fonte
    assert "Decimal(valor_bruto)" not in codigo_fonte
    assert "para_decimal" in codigo_fonte


# ---------------------------------------------------------------------------
# Camada de serviço: `para_decimal` (o julgador único) já recusa `float`
# por contrato — controle de que a fronteira da API e o módulo monetário
# concordam, sem duplicar a regra.
# ---------------------------------------------------------------------------


def test_para_decimal_ja_recusava_float_por_contrato():
    from apps.core.dinheiro import ValorMonetarioInvalido

    with pytest.raises(ValorMonetarioInvalido):
        para_decimal(99999999999999.99)


def test_criar_lancamento_continua_aceitando_decimal_construido_pelo_chamador(cenario):
    """Controle: `criar_lancamento` (services.py) continua aceitando um
    `Decimal` já construído por um chamador Python de confiança (não é o
    caminho afetado pela DE-030, que é sobre TEXTO de cliente não
    confiável) — a correção da API não pode ter quebrado esse uso."""
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 1, 15),
        historico="controle",
        itens=[
            {"conta": cenario["caixa"], "tipo": "debito", "valor": Decimal("10.00")},
            {"conta": cenario["receita"], "tipo": "credito", "valor": Decimal("10.00")},
        ],
        chave_idempotencia=None,
    )
    assert lancamento.criado_agora is True
