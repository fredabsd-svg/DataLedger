"""Achado R5-3 da auditoria DL-017, rodada 5 (BL-142 / DE-034).

Na API, `item["conta"]` (`_extrair_itens`, `apps/contabilidade/views.py`)
ia direto para `Conta.objects.get(pk=item["conta"], empresa=empresa)`, sem
`para_id` — a mesma classe que a tela e `apps.tenancy` já fecham. Medido
pelo auditor (duas partidas balanceadas, variando só o `conta` da
primeira):

    1.9 (número JSON)  -> 201, gravado na CONTA 1
    true               -> 201, gravado na CONTA 1
    " 1 " / "+1"       -> 201, gravado na CONTA 1
    "٢" / "２"         -> 201, gravado na CONTA 2 (dígito Unicode reinterpretado)
    "1_0"              -> 400 (correto, já era)
    "9"*6000           -> 400 (correto, já era)

Mesma classe em `conta_pai` (`ContaSerializer`, `apps/contabilidade/
serializers.py`, via `PrimaryKeyRelatedField`).

**O agravante de método que o auditor nomeou:** dois comentários de
`views_web.py` afirmavam que "a API já usa `para_id`" — não usava.
Corrigido com `para_id` nos dois pontos (`_extrair_itens` e
`_ContaPaiField`); os comentários falsos são do `especialista-frontend`
(avisado, não editados por mim).
"""

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
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-142", cnpj="77777777000188")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-142 Ltda", cnpj="77788899000100"
    )
    conta_1 = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_2 = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl142", email="gestor-bl142@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "conta_1": conta_1, "conta_2": conta_2}


def _cliente_autenticado(client, cenario):
    assert client.login(username="gestor-bl142", password="senha-forte-123")


def _sem_nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


def _post_lancamento(client, cenario, *, conta, chave):
    corpo = {
        "data": "2026-01-15",
        "historico": "R5-3 / BL-142",
        "itens": [
            {"conta": conta, "tipo": "debito", "valor": "10.00"},
            {"conta": cenario["conta_2"].id, "tipo": "credito", "valor": "10.00"},
        ],
    }
    return client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=chave,
    )


# ---------------------------------------------------------------------------
# `item["conta"]` — a tabela do auditor refeita.
# ---------------------------------------------------------------------------

CONTAS_REINTERPRETADAS = [
    pytest.param(1.9, id="numero-json-fracionario"),
    pytest.param(True, id="booleano"),
    pytest.param(" 1 ", id="com-espacos"),
    pytest.param("+1", id="com-sinal"),
]

CONTAS_REINTERPRETADAS_PARA_CONTA_2 = [
    pytest.param("١", id="digito-indico-arabico"),  # "1" arábico-índico
    pytest.param("１", id="digito-fullwidth"),  # "1" fullwidth
]


@pytest.mark.parametrize("conta_bruta", CONTAS_REINTERPRETADAS)
def test_conta_reinterpretada_em_silencio_agora_e_recusada(client, cenario, conta_bruta):
    """Antes, os quatro valores abaixo eram gravados na conta 1, com 201,
    sem uma palavra — o lote fecha balanceado (débito na conta 1, crédito
    na conta 2), nenhuma conferência aponta. Agora: 400, nada gravado."""
    _cliente_autenticado(client, cenario)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=conta_bruta, chave=f"bl142-{conta_bruta!r}")

    assert resposta.status_code == 400, (conta_bruta, resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
    assert _sem_nada_gravado()


@pytest.mark.parametrize("conta_bruta", CONTAS_REINTERPRETADAS_PARA_CONTA_2)
def test_conta_com_digito_unicode_nao_e_reinterpretada_para_outra_conta(
    client, cenario, conta_bruta
):
    """`"١"`/`"１"` (dígito Unicode "1" em outro script) eram gravados na
    conta 1 mesmo escrevendo o dígito de "1" em outro alfabeto — o achado
    original do auditor usou `"٢"`/`"２"` (dígito "2") para o efeito ficar
    óbvio (grava na conta 2 quando o cliente pediu conta 1). Reproduzo o
    caso equivalente com o dígito "1": qualquer um dos dois, gravado ou
    recusado, tem que ser o MESMO veredito de `para_id("1")` — recusado,
    porque só ASCII é aceito.
    """
    _cliente_autenticado(client, cenario)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=conta_bruta, chave=f"bl142-{conta_bruta}")

    assert resposta.status_code == 400, (conta_bruta, resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes


def test_digito_unicode_gravaria_na_conta_errada_se_nao_fosse_recusado(client, cenario):
    """Reprodução literal do achado: `"٢"` (dígito arábico-índico de "2")
    tem que ser recusado — e ANTES da correção, teria gravado na conta 2
    mesmo quando a intenção do índice não era essa. Prova por mutação
    (não aqui): a matriz de verificação desta entrega reverte `para_id`
    para o `.get(pk=...)` direto e mostra a conta 2 sendo gravada.
    """
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(client, cenario, conta="٢", chave="bl142-digito-2-arabico")
    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


@pytest.mark.parametrize("conta_ja_recusada", ["1_0", "9" * 6000])
def test_formatos_ja_recusados_continuam_recusados_sem_regressao(
    client, cenario, conta_ja_recusada
):
    _cliente_autenticado(client, cenario)
    resposta = _post_lancamento(
        client, cenario, conta=conta_ja_recusada, chave=f"bl142-controle-{len(conta_ja_recusada)}"
    )
    assert resposta.status_code == 400, resposta.status_code
    assert _sem_nada_gravado()


@pytest.mark.parametrize("como_texto", [False, True])
def test_conta_1_como_int_ou_texto_continua_gravando_na_conta_1(client, cenario, como_texto):
    """Controle positivo: o PK real de `conta_1` (não necessariamente o
    inteiro literal `1` — o banco de teste é compartilhado entre suítes, e
    a sequência de PKs não é resetada por teste), como `int` e como `str`,
    continua sendo aceito e grava exatamente na conta 1 — a correção não
    pode ter apertado o caminho normal.
    """
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    conta_valida = str(pk_real) if como_texto else pk_real

    resposta = _post_lancamento(
        client, cenario, conta=conta_valida, chave=f"bl142-valido-{como_texto}"
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    item_debito = ItemLancamento.objects.get(tipo="debito")
    assert item_debito.conta_id == pk_real
    assert item_debito.valor == Decimal("10.00")


# ---------------------------------------------------------------------------
# `conta_pai` (ContaSerializer) — mesma classe, outro caminho.
# ---------------------------------------------------------------------------


def _post_conta(client, cenario, *, conta_pai, codigo="1.1"):
    corpo = {
        "codigo": codigo,
        "nome": "Subconta BL-142",
        "tipo": "ativo",
        "natureza": "devedora",
        "conta_pai": conta_pai,
    }
    return client.post(
        reverse("contabilidade:contas", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
    )


@pytest.mark.parametrize("conta_pai_bruta", [1.9, True, " 1 ", "+1", "٢", "２"])
def test_conta_pai_reinterpretada_em_silencio_agora_e_recusada(client, cenario, conta_pai_bruta):
    """Mesma tabela do `item["conta"]`, agora em `conta_pai`: antes, `1.9`
    resolvia para a conta 1 como pai, e `"٢"`/`"２"` resolviam para a
    conta 2 — sempre 201, sem aviso. Agora: 400, nenhuma conta criada."""
    _cliente_autenticado(client, cenario)
    antes = Conta.objects.count()

    resposta = _post_conta(client, cenario, conta_pai=conta_pai_bruta)

    assert resposta.status_code == 400, (conta_pai_bruta, resposta.status_code, resposta.content)
    assert Conta.objects.count() == antes


@pytest.mark.parametrize("como_texto", [False, True])
def test_conta_pai_1_e_conta_pai_um_texto_continuam_funcionando(client, cenario, como_texto):
    """Controle positivo: `conta_pai` como PK real (`int`) ou como texto
    continua aceito e aponta exatamente para a conta 1. Mesmo cuidado do
    teste equivalente acima: usa o PK real, não o inteiro literal `1`."""
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    conta_pai_valida = str(pk_real) if como_texto else pk_real

    resposta = _post_conta(client, cenario, conta_pai=conta_pai_valida, codigo=f"sub-{como_texto}")

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    subconta = Conta.objects.get(pk=resposta.json()["id"])
    assert subconta.conta_pai_id == pk_real


def test_conta_pai_nulo_continua_aceito(client, cenario):
    """Controle: `conta_pai` continua opcional (conta raiz do plano)."""
    _cliente_autenticado(client, cenario)
    resposta = _post_conta(client, cenario, conta_pai=None, codigo="3")
    assert resposta.status_code == 201, (resposta.status_code, resposta.content)


# ---------------------------------------------------------------------------
# A view não constrói a conta a partir de um identificador não julgado
# (verificação estática, no molde de `test_dl030_valor_texto_na_api.py`).
# ---------------------------------------------------------------------------


def test_extrair_itens_usa_para_id():
    import inspect

    from apps.contabilidade import views as views_modulo

    codigo_fonte = inspect.getsource(views_modulo._extrair_itens)
    assert "para_id(" in codigo_fonte


def test_conta_serializer_usa_para_id_para_conta_pai():
    import inspect

    from apps.contabilidade import serializers as serializers_modulo

    codigo_fonte = inspect.getsource(serializers_modulo)
    assert "para_id(" in codigo_fonte
    assert "_ContaPaiField" in codigo_fonte
