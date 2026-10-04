"""DL-063 (BL-606) — a coluna da DMPL passa a ser gravável pelas DUAS portas
que cadastram conta, como a linha da DRE e a linha da DLPA.

**O defeito:** `Conta.classificacao_dmpl` existia no modelo e era lido pela
apuração, mas não era gravável. O formulário de conta nova não o oferecia, e
na API o campo era `read_only` e o POST o recusava por contrato, com "dado não
contratado" — recusa que, por acontecer por contrato, nem nomeava o campo.
Quem criava a conta por qualquer uma das duas portas tinha de sair dali para
depois classificá-la, e a integração por API **não tinha porta nenhuma**: a
porta própria (`ContaClassificacaoDmplView`) reclassifica conta EXISTENTE.

**A porta própria continua existindo** e não é redundância: ela grava com
trilha antes/depois na mesma transação, que é o que reclassificar conta com
movimento exige. O POST é cadastro INICIAL — operações diferentes, contratos
diferentes (D2 do plano da DL-063).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import ClassificacaoDmpl, Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"

CONTADOR = iter(range(73000000000000, 73000000009999))


def _cnpj():
    return f"{next(CONTADOR):014d}"


# ---------------------------------------------------------------------------
# Cenário
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-063", cnpj=_cnpj())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-063 Ltda", cnpj=_cnpj()
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-dl063", email="gestor-dl063@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa}


@pytest.fixture
def gestor(client, cenario):
    """⚠️ **Esta fixture se chama `gestor`, e não `autenticado` como nos
    arquivos vizinhos — de propósito, e por anomalia medida.**

    Numa cópia mínima deste cenário (só `pytest`, `get_user_model`,
    `pytestmark = pytest.mark.django_db`, uma fixture que cria escritório,
    empresa e gestor, e outra que faz `client.login`), o pytest desta
    máquina **falha ao resolver uma fixture de módulo chamada
    `autenticado`**, com `fixture 'autenticado' not found` — mesmo com a
    fixture DEFINIDA no módulo e LISTADA por `pytest --fixtures`, e mesmo
    limpando `.pytest_cache` e `__pycache__`. Renomeada para `gestor`, a
    cópia mínima passa. Arquivos **antigos** com o mesmo nome
    (`test_dl019_politica_api.py`) continuam passando, e os dois rodam juntos
    na mesma sessão — então não é o nome que está envenenado, é a combinação
    com módulo novo nesta máquina. A causa **não foi explicada**.

    Omitir isso seria esconder um defeito de ambiente que pode morder quem
    criar arquivo de teste novo hoje. O nome fica incomum **e
    documentado**, e o teste continua provando o que tem de provar."""
    assert client.login(username="gestor-dl063", password=SENHA)
    return client


def _corpo_de_conta(**extra):
    corpo = {
        "codigo": "3",
        "nome": "Conta nova",
        "tipo": TipoConta.PATRIMONIO_LIQUIDO,
        "natureza": NaturezaConta.CREDORA,
    }
    corpo.update(extra)
    return corpo


# ---------------------------------------------------------------------------
# Critérios 1 e 2 — a tela oferece e grava
# ---------------------------------------------------------------------------


def test_a_tela_de_conta_nova_oferece_a_coluna_da_dmpl(gestor, cenario):
    """Critério 1. Sem a correção, o campo não estava em `Meta.fields` e a
    tela não o oferecia."""
    resposta = gestor.get(reverse("contabilidade_web:conta_nova", args=[cenario["empresa"].id]))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert 'name="classificacao_dmpl"' in conteudo
    # O rótulo do select, no mesmo tom dos outros dois campos.
    assert "Coluna da DMPL" in conteudo


def test_a_conta_nova_grava_a_coluna_da_dmpl(gestor, cenario):
    """Critério 2 — o caminho de escrita do formulário, espelhando
    `test_a_conta_nova_aceita_a_classificacao_da_dlpa`."""
    resposta = gestor.post(
        reverse("contabilidade_web:conta_nova", args=[cenario["empresa"].id]),
        data={
            "codigo": "9",
            "nome": "Ações em tesouraria",
            "tipo": TipoConta.PATRIMONIO_LIQUIDO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "classificacao_dmpl": ClassificacaoDmpl.ACOES_OU_QUOTAS_EM_TESOURARIA,
        },
    )

    assert resposta.status_code == 302, resposta.content[:400]
    conta = Conta.objects.get(codigo="9", empresa=cenario["empresa"])
    assert conta.classificacao_dmpl == ClassificacaoDmpl.ACOES_OU_QUOTAS_EM_TESOURARIA


def test_a_conta_nova_recusa_coluna_incompativel_sem_gravar(gestor, cenario):
    """Critério 2, caminho de recusa: coluna que o tipo da conta não aceita
    volta com o erro e **não grava nada** — a guarda é do servidor
    (`Conta.clean()`), não da tela."""
    resposta = gestor.post(
        reverse("contabilidade_web:conta_nova", args=[cenario["empresa"].id]),
        data={
            "codigo": "4.9",
            "nome": "Receita com coluna de DMPL",
            "tipo": TipoConta.RECEITA,
            "natureza": NaturezaConta.CREDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "classificacao_dmpl": ClassificacaoDmpl.CAPITAL_SOCIAL,
        },
    )

    assert resposta.status_code == 200
    assert not Conta.objects.filter(codigo="4.9", empresa=cenario["empresa"]).exists()


# ---------------------------------------------------------------------------
# Critérios 3, 4 e 5 — a API
# ---------------------------------------------------------------------------


def test_a_api_grava_a_coluna_da_dmpl(gestor, cenario):
    """Critério 3. Sem a correção, o campo era `read_only` e o contrato do
    POST recusava a chave com "dado não contratado" — sem porta nenhuma."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = gestor.post(
        url,
        _corpo_de_conta(
            codigo="3.1",
            nome="Capital Social",
            classificacao_dmpl=ClassificacaoDmpl.CAPITAL_SOCIAL,
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    conta = Conta.objects.get(codigo="3.1", empresa=cenario["empresa"])
    assert conta.classificacao_dmpl == ClassificacaoDmpl.CAPITAL_SOCIAL
    # A resposta devolve a conta já classificada — a porta grava e mostra.
    assert ClassificacaoDmpl.CAPITAL_SOCIAL in resposta.content.decode()


def test_a_api_recusa_coluna_incompativel_nomeando_o_campo(gestor, cenario):
    """Critério 3, caminho de recusa — e a diferença que importa entre os
    dois motivos de recusa: aqui a mensagem **nomeia o campo** e diz o
    motivo, porque a validação rodou; o contrato (critério 4) recusa sem
    dizer nada porque não chegou a examinar."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = gestor.post(
        url,
        _corpo_de_conta(
            codigo="4.1",
            nome="Receita com coluna de DMPL",
            tipo=TipoConta.RECEITA,
            classificacao_dmpl=ClassificacaoDmpl.CAPITAL_SOCIAL,
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    conteudo = resposta.content.decode()
    assert "classificacao_dmpl" in conteudo
    assert "Patrimônio Líquido" in conteudo, "a mensagem diz qual tipo aceita"
    assert not Conta.objects.filter(codigo="4.1", empresa=cenario["empresa"]).exists()


def test_a_api_normaliza_coluna_vazia_para_nada(gestor, cenario):
    """Critério 5 — `""` grava `None`, pelo mesmo motivo do achado A4 da
    DL-045: sem a normalização, o `ChoiceField` gravaria `""` e a guarda de
    transição de `Conta.clean()` a trataria como "já classificada",
    TRAVANDO a conta para uma classificação real posterior."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = gestor.post(
        url,
        _corpo_de_conta(codigo="3.2", nome="Conta sem coluna", classificacao_dmpl=""),
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    conta = Conta.objects.get(codigo="3.2", empresa=cenario["empresa"])
    assert conta.classificacao_dmpl is None


def test_a_api_ainda_recusa_chave_desconhecida(gestor, cenario):
    """Critério 4 — abrir uma porta NÃO afrouxa o contrato. A política dos
    cinco dicionários (BL-196) continua sendo o filtro, e a recusa por
    contrato continua distinta da recusa por validação."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = gestor.post(
        url,
        _corpo_de_conta(codigo="3.3", nome="Conta com chave estranha", xpto=1),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "xpto" in resposta.content.decode()
    assert not Conta.objects.filter(codigo="3.3", empresa=cenario["empresa"]).exists()


# ---------------------------------------------------------------------------
# Critério 6 — a porta própria continua, e continua gravando com trilha
# ---------------------------------------------------------------------------


def test_a_porta_propria_de_classificacao_continua_gravando(gestor, cenario):
    """Critério 6. Abrir o POST não pode ter derrubado a porta de
    classificação, que é a que grava **com trilha antes/depois** — a que
    serve para reclassificar conta com movimento, e a única que o contador
    usa depois do cadastro."""
    conta = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="3.4",
        nome="Reserva sem coluna",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    url = reverse("contabilidade:conta-classificacao-dmpl", args=[cenario["empresa"].id, conta.id])
    # A porta própria é PATCH (`ContaClassificacaoDmplView.patch`) — e é
    # assim que ela tem de continuar sendo: cadastro inicial pelo POST,
    # reclassificação pelo PATCH com trilha.
    resposta = gestor.patch(
        url,
        {"classificacao_dmpl": ClassificacaoDmpl.RESERVA_LEGAL},
        content_type="application/json",
    )

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    assert conta.classificacao_dmpl == ClassificacaoDmpl.RESERVA_LEGAL
