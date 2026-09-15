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
#
# Cuidado de método, em TODOS os testes abaixo: nunca uso o inteiro literal
# `1`/`2` para representar "o PK da conta 1/2". O banco de teste é
# COMPARTILHADO entre todos os arquivos da suíte, na mesma sessão — a
# sequência de PKs do Postgres NÃO é resetada por teste (só a transação é
# desfeita; `nextval()` de uma sequência não é transacional), então "1"
# pode já ter sido consumido por uma Conta de outro teste, de OUTRA
# empresa, muito antes deste rodar. Um teste que assumisse `conta_1.id ==
# 1` só passaria por acidente de ORDEM DE EXECUÇÃO — a mesma classe de
# fragilidade que a própria auditoria desta rodada nomeou para o teste de
# permissão de `apps.tenancy` (override_settings dependente de ordem).
# Todo valor usado abaixo deriva do PK REAL de `cenario["conta_1"]`/
# `cenario["conta_2"]`, nunca de um número escolhido a dedo.
# ---------------------------------------------------------------------------


def _fullwidth(n):
    return str(n).translate(str.maketrans("0123456789", "０１２３４５６７８９"))


def _arabico_indico(n):
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def test_conta_com_numero_json_fracionario_e_recusada(client, cenario):
    """Antes, um número JSON fracionário era truncado por `int()` (Python:
    `int(1.9) == 1`) e gravava na conta cujo PK batesse com a parte
    inteira — sempre 201, sem aviso. Agora: 400, nada gravado."""
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=pk_real + 0.9, chave="bl142-fracionario")

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
    assert _sem_nada_gravado()


@pytest.mark.parametrize("modelo", [" {pk} ", "+{pk}"])
def test_conta_com_espaco_ou_sinal_e_recusada(client, cenario, modelo):
    """`" 1 "`/`"+1"` (com espaço ou sinal) eram aceitos por `int()` e
    gravavam na conta correspondente, sem aviso. Agora: 400."""
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    conta_bruta = modelo.format(pk=pk_real)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=conta_bruta, chave=f"bl142-{conta_bruta}")

    assert resposta.status_code == 400, (conta_bruta, resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
    assert _sem_nada_gravado()


def test_conta_booleana_e_recusada_por_tipo(client, cenario):
    """`bool` é recusado por TIPO (`para_id` recusa `bool` explicitamente
    — subclasse de `int` em Python, mesmo motivo de `para_decimal`) —
    não depende de `True == 1` coincidir com o PK de conta nenhuma."""
    _cliente_autenticado(client, cenario)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=True, chave="bl142-booleano")

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
    assert _sem_nada_gravado()


@pytest.mark.parametrize(
    "transformar", [_fullwidth, _arabico_indico], ids=["fullwidth", "arabico-indico"]
)
def test_conta_com_digito_unicode_nao_e_reinterpretada_para_outra_conta(
    client, cenario, transformar
):
    """Reprodução literal do achado, amarrada ao PK REAL da conta 2 (não
    ao literal `"2"`): o dígito Unicode do PK de `conta_2`, escrito em
    fullwidth ou índico-arábico, é aceito por `int()` e gravaria
    EXATAMENTE na conta 2 — mesmo quando a intenção do índice não era
    essa (o achado original usa `"٢"`/`"２"` para "2" com o mesmo efeito,
    mas fixo em bases pequenas; aqui o dígito é derivado do PK real,
    então o teste vale qualquer que seja esse PK).
    """
    _cliente_autenticado(client, cenario)
    pk_conta_2 = cenario["conta_2"].id
    conta_bruta = transformar(pk_conta_2)
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(client, cenario, conta=conta_bruta, chave=f"bl142-{conta_bruta}")

    assert resposta.status_code == 400, (conta_bruta, resposta.status_code, resposta.content)
    assert LancamentoContabil.objects.count() == antes
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


def test_conta_pai_com_numero_json_fracionario_e_recusada(client, cenario):
    """Mesma classe do `item["conta"]`, agora em `conta_pai`: antes, um
    número JSON fracionário resolvia para a conta cujo PK batesse com a
    parte truncada — sempre 201, sem aviso. Amarrado ao PK REAL (não ao
    literal `1`), pelo mesmo motivo do bloco de comentário acima."""
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    antes = Conta.objects.count()

    resposta = _post_conta(client, cenario, conta_pai=pk_real + 0.9)

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert Conta.objects.count() == antes


@pytest.mark.parametrize("modelo", [" {pk} ", "+{pk}"])
def test_conta_pai_com_espaco_ou_sinal_e_recusada(client, cenario, modelo):
    _cliente_autenticado(client, cenario)
    pk_real = cenario["conta_1"].id
    conta_pai_bruta = modelo.format(pk=pk_real)
    antes = Conta.objects.count()

    resposta = _post_conta(client, cenario, conta_pai=conta_pai_bruta)

    assert resposta.status_code == 400, (conta_pai_bruta, resposta.status_code, resposta.content)
    assert Conta.objects.count() == antes


def test_conta_pai_booleana_e_recusada_por_tipo(client, cenario):
    _cliente_autenticado(client, cenario)
    antes = Conta.objects.count()

    resposta = _post_conta(client, cenario, conta_pai=True)

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert Conta.objects.count() == antes


@pytest.mark.parametrize(
    "transformar", [_fullwidth, _arabico_indico], ids=["fullwidth", "arabico-indico"]
)
def test_conta_pai_com_digito_unicode_nao_e_reinterpretada(client, cenario, transformar):
    """Amarrado ao PK REAL de `conta_2` — o dígito Unicode do PK
    resolveria, sob o mutante, EXATAMENTE para a conta 2 como pai."""
    _cliente_autenticado(client, cenario)
    pk_conta_2 = cenario["conta_2"].id
    conta_pai_bruta = transformar(pk_conta_2)
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
