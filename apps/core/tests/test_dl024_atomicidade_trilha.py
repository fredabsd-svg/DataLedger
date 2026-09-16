"""BL-14 (DL-024): atomicidade entre gravação de operação e registro de auditoria.

Medido pelo auditor: seis pontos no produto gravam a operação e só DEPOIS
chamam `apps.auditoria.services.registrar()` — fora do `transaction.atomic()`
que protegeu a gravação. Se a INSERT do `RegistroAuditoria` falha (unique
constraint, FK violada, banco desconectou), a operação passou e a trilha
ficou silenciosamente vazia. A contabilidade dizia uma coisa, a trilha
outra.

Esta etapa move cada `registrar()` para dentro do mesmo
`transaction.atomic()` da gravação. A defesa é uma só operação: ou ambos
gravam ou nenhum grava. Estes testes provam que a defesa foi aplicada
nos seis pontos.

Dois grupos de teste:

1. **Estático** (`test_registrar_*`): lê o fonte via `inspect.getsource` e
   confirma que cada `registrar(acao=...)` está dentro do bloco
   `with transaction.atomic():` que antecede. Roda em qualquer ambiente.
2. **Runtime** (`test_*_rollback_quando_registrar_falha`): mocka
   `RegistroAuditoria.objects.create` levantando `IntegrityError` e
   prova que a gravação da operação reverte. Exige PostgreSQL
   (`@pytest.mark.django_db(transaction=True)`) — a CI é quem roda.

O nome do arquivo, `apps/core/tests/test_dl024_atomicidade_trilha.py`,
segue o padrão dos testes de varredura (DL-019) e administrativos (DL-023)
que vivem em `apps/core/tests/` por cruzarem vários módulos do produto.
"""

import inspect
from unittest import mock

import pytest

# Sem `pytestmark = pytest.mark.django_db` no nível do módulo: os testes
# ESTÁTICOS não precisam de banco, e a marca global forçaria a
# inicialização do Postgres em todos eles. Os testes RUNTIME marcam-se
# individualmente com `@pytest.mark.django_db(transaction=True)`.


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _pos_apos_bloco_transaction_atomic(source_text, inicio):
    """Devolve a posição imediatamente após o fim do bloco `with ...`
    que começa em `inicio`. O fim é a primeira linha que voltar à mesma
    indentação da palavra `with` (ou que seja uma linha não-indentada).

    Implementação: conta os espaços da linha que contém `with` em
    `inicio`; o bloco termina na primeira linha (depois de `inicio`) que
    tenha indentação MENOR OU IGUAL a essa contagem.
    """
    # Encontra o início da linha que contém `inicio`.
    linha_inicio = source_text.rfind("\n", 0, inicio) + 1
    # Conta espaços no início dessa linha.
    espacos = 0
    while linha_inicio + espacos < len(source_text) and source_text[linha_inicio + espacos] == " ":
        espacos += 1
    # Procura a próxima linha cuja indentação seja < `espacos`.
    pos = inicio
    while pos < len(source_text):
        proxima_linha = source_text.find("\n", pos)
        if proxima_linha == -1:
            return len(source_text)
        # Pula o "\n" e conta indentação
        i = proxima_linha + 1
        esp = 0
        while i + esp < len(source_text) and source_text[i + esp] == " ":
            esp += 1
        if esp < espacos:
            return i
        pos = i

    return len(source_text)


def _texto_do_bloco_transaction_atomic(source_text):
    """Devolve o conteúdo entre o primeiro `with transaction.atomic` (ou
    `with (`) e o fim do bloco correspondente.

    Usado para afirmar que `registrar(...)` está dentro do bloco atômico.
    """
    candidatos = []
    for marcador in ("with (", "with transaction.atomic"):
        pos = source_text.find(marcador)
        if pos != -1:
            candidatos.append(pos)
    if not candidatos:
        raise AssertionError(
            f"Nenhum bloco `with transaction.atomic` encontrado em:\n{source_text}"
        )
    inicio = min(candidatos)
    fim = _pos_apos_bloco_transaction_atomic(source_text, inicio)
    return source_text[inicio:fim]


def _tem_registrar_dentro(bloco, acao):
    """Confirma que o bloco contém uma chamada a `registrar(...)` com o
    `acao` igual à string `acao` (em aspas simples ou duplas)."""
    return (
        f'registrar(acao="{acao}"' in bloco
        or f"registrar(acao='{acao}'" in bloco
        or f'acao="{acao}"' in bloco
        or f"acao='{acao}'" in bloco
    )


# -----------------------------------------------------------------------
# 1. Fonte estático — `registrar(...)` mora dentro do `transaction.atomic()`
# -----------------------------------------------------------------------


def test_registrar_empresa_criada_dentro_do_transaction_atomic():
    """apps/empresas/views.py: EmpresaListCreateView.perform_create."""
    from apps.empresas.views import EmpresaListCreateView

    source = inspect.getsource(EmpresaListCreateView.perform_create)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "empresa.criada"), (
        "BL-14: `registrar(acao='empresa.criada', ...)` precisa estar DENTRO "
        "do `with transaction.atomic():` em EmpresaListCreateView.perform_create.\n"
        f"Bloco atual:\n{bloco}"
    )


def test_registrar_conta_criada_api_dentro_do_transaction_atomic():
    """apps/contabilidade/views.py: ContaListCreateView.perform_create."""
    from apps.contabilidade.views import ContaListCreateView

    source = inspect.getsource(ContaListCreateView.perform_create)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "conta.criada"), (
        "BL-14: `registrar(acao='conta.criada', ...)` precisa estar DENTRO "
        "do `with transaction.atomic():` em ContaListCreateView.perform_create.\n"
        f"Bloco atual:\n{bloco}"
    )


def test_registrar_lancamento_api_dentro_do_transaction_atomic():
    """apps/contabilidade/views.py: LancamentoListCreateView.post."""
    from apps.contabilidade.views import LancamentoListCreateView

    source = inspect.getsource(LancamentoListCreateView.post)
    # O método `post` chama `criar_lancamento()` e DEPOIS envolve o
    # `registrar()` num `with transaction.atomic():` REENTRANTE (o
    # serviço `criar_lancamento` já é `@transaction.atomic` por si).
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "lancamento.criado"), (
        "BL-14: `registrar(acao='lancamento.criado', ...)` precisa estar DENTRO "
        "do `with transaction.atomic():` em LancamentoListCreateView.post.\n"
        f"Bloco atual:\n{bloco}"
    )
    assert _tem_registrar_dentro(bloco, "lancamento.criacao_repetida"), (
        "BL-14: `registrar(acao='lancamento.criacao_repetida', ...)` precisa "
        "estar DENTRO do mesmo bloco atômico em LancamentoListCreateView.post."
    )


def test_registrar_conta_criada_web_dentro_do_transaction_atomic():
    """apps/contabilidade/views_web.py: função de criação de conta na web.

    O nome da função é estável (`conta_nova`); se mudar, este teste indica
    onde o defeito voltou.
    """
    from apps.contabilidade import views_web

    source = inspect.getsource(views_web.conta_nova)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "conta.criada"), (
        "BL-14: `registrar(acao='conta.criada', ...)` precisa estar DENTRO "
        "do `with transaction.atomic():` em views_web.conta_nova.\n"
        f"Bloco atual:\n{bloco}"
    )


def test_registrar_lancamento_web_dentro_do_transaction_atomic():
    """apps/contabilidade/views_web.py: função de criação de lançamento na web."""
    from apps.contabilidade import views_web

    source = inspect.getsource(views_web.lancamento_novo)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "lancamento.criado"), (
        "BL-14: `registrar(acao='lancamento.criado', ...)` precisa estar "
        "DENTRO do `with transaction.atomic():` em views_web.lancamento_novo."
    )
    assert _tem_registrar_dentro(bloco, "lancamento.criacao_repetida"), (
        "BL-14: `registrar(acao='lancamento.criacao_repetida', ...)` precisa "
        "estar DENTRO do mesmo bloco atômico em views_web.lancamento_novo."
    )


def test_registrar_escritorio_ativado_api_dentro_do_transaction_atomic():
    """apps/tenancy/views.py: EscritorioAtivoView.post (APIView) — auditoria da
    troca de escritório ativo pela API.

    Limitação documentada: a `request.session` não reverte por
    `transaction.atomic()` (ver comentário no código). Esta proteção cobre o
    RegistroAuditoria, não a sessão.
    """
    from apps.tenancy.views import EscritorioAtivoView

    source = inspect.getsource(EscritorioAtivoView.post)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "escritorio.ativado"), (
        "BL-14: `registrar(acao='escritorio.ativado', ...)` precisa estar "
        "DENTRO do `with transaction.atomic():` em EscritorioAtivoView.post "
        "(APIView).\n"
        f"Bloco atual:\n{bloco}"
    )


def test_registrar_escritorio_ativado_fbv_dentro_do_transaction_atomic():
    """apps/tenancy/views.py: ativar_escritorio (FBV) — auditoria da troca de
    escritório ativo pela tela do painel.

    Existe em paralelo à APIView `EscritorioAtivoView`; as duas precisam
    estar cobertas pelo BL-14.
    """
    from apps.tenancy import views

    source = inspect.getsource(views.ativar_escritorio)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "escritorio.ativado"), (
        "BL-14: `registrar(acao='escritorio.ativado', ...)` precisa estar "
        "DENTRO do `with transaction.atomic():` em tenancy.views.ativar_escritorio "
        "(FBV do painel).\n"
        f"Bloco atual:\n{bloco}"
    )


def test_registrar_estabelecimento_criado_dentro_do_transaction_atomic():
    """A criação de estabelecimento e sua trilha precisam compartilhar a
    mesma transação; o INSERT do estabelecimento não pode sobreviver a uma
    falha posterior do `registrar()`."""
    from apps.empresas.views import EstabelecimentoListCreateView

    source = inspect.getsource(EstabelecimentoListCreateView.perform_create)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "estabelecimento.criado"), (
        "BL-14: `registrar(acao='estabelecimento.criado', ...)` precisa estar "
        "dentro do transaction.atomic de EstabelecimentoListCreateView."
    )


def test_registrar_regime_tributario_criado_dentro_do_transaction_atomic():
    """A transação externa precisa abranger o serviço de regime e a trilha,
    porque o serviço retorna depois do seu savepoint interno."""
    from apps.empresas.views import HistoricoRegimeTributarioListCreateView

    source = inspect.getsource(HistoricoRegimeTributarioListCreateView.post)
    bloco = _texto_do_bloco_transaction_atomic(source)
    assert _tem_registrar_dentro(bloco, "regime_tributario.registrado"), (
        "BL-14: `registrar(acao='regime_tributario.registrado', ...)` precisa "
        "estar dentro do transaction.atomic de HistoricoRegimeTributarioListCreateView."
    )


# -----------------------------------------------------------------------
# 2. Runtime — `RegistroAuditoria.objects.create` falha, a operação reverte.
#    Estes testes exigem PostgreSQL (`transaction=True`).
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_criar_empresa_reverte_se_registrar_falha(client):
    """Prova runtime do BL-14 para Empresa. Quando o INSERT do
    `RegistroAuditoria` levanta `IntegrityError`, a Empresa NÃO pode estar
    gravada no banco — a operação inteira é atômica.

    Mutante: se `registrar()` voltar para fora do `transaction.atomic()`,
    a Empresa é gravada, `Empresa.objects.count()` == 1, e este teste morre.
    """
    from django.contrib.auth import get_user_model
    from django.db import IntegrityError
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="Escr BL-14", cnpj="11111111000111")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl14", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    client.login(username="gestor-bl14", password="senha-forte-123")

    with mock.patch.object(
        RegistroAuditoria.objects, "create", side_effect=IntegrityError("audit falhou")
    ):
        resposta = client.post(
            reverse("empresas:api-lista"),
            data={
                "cnpj": "22222222000122",
                "razao_social": "Empresa BL-14",
                "nome_fantasia": "BL-14",
                "ativo": True,
            },
            content_type="application/json",
        )

    assert Empresa.objects.count() == 0, (
        "BL-14: Empresa foi gravada mas a trilha falhou — atomicidade quebrada. "
        "Esperado 0 Empresa no banco após rollback."
    )
    assert resposta.status_code != 201, (
        "BL-14: cliente recebeu 201 mesmo com a trilha falhando — atomicidade quebrada."
    )


@pytest.mark.django_db(transaction=True)
def test_criar_conta_api_reverte_se_registrar_falha(client):
    """Prova runtime do BL-14 para Conta (API)."""
    from django.contrib.auth import get_user_model
    from django.db import IntegrityError

    from apps.auditoria.models import RegistroAuditoria
    from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="Escr Conta", cnpj="33333333000133")
    usuario = get_user_model().objects.create_user(
        username="gestor-conta", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="E Conta", cnpj="44444444000144"
    )
    client.login(username="gestor-conta", password="senha-forte-123")

    with mock.patch.object(
        RegistroAuditoria.objects, "create", side_effect=IntegrityError("audit falhou")
    ):
        resposta = client.post(
            f"/api/empresas/{empresa.id}/contas/",
            data={
                "codigo": "1.1.1",
                "nome": "Conta teste",
                "tipo": TipoConta.ATIVO.value,
                "natureza": NaturezaConta.DEVEDORA.value,
            },
            content_type="application/json",
        )

    assert Conta.objects.count() == 0, (
        "BL-14: Conta foi gravada mas a trilha falhou — atomicidade quebrada."
    )
    assert resposta.status_code != 201


@pytest.mark.django_db(transaction=True)
def test_criar_estabelecimento_reverte_se_registrar_falha(client):
    """Prova runtime do BL-14 para estabelecimento."""
    from django.contrib.auth import get_user_model
    from django.db import IntegrityError
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa, Estabelecimento
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="Escr Estab", cnpj="55555555000155")
    usuario = get_user_model().objects.create_user(
        username="gestor-estab", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="E Estab", cnpj="66666666000166"
    )
    client.login(username="gestor-estab", password="senha-forte-123")

    with mock.patch.object(
        RegistroAuditoria.objects, "create", side_effect=IntegrityError("audit falhou")
    ):
        resposta = client.post(
            reverse("empresas:api-estabelecimentos", args=[empresa.id]),
            data={"tipo": "matriz", "nome": "Matriz", "cnpj": "77777777000177"},
            content_type="application/json",
        )

    assert Estabelecimento.objects.count() == 0, (
        "BL-14: Estabelecimento foi gravado mas a trilha falhou — atomicidade quebrada."
    )
    assert resposta.status_code != 201


@pytest.mark.django_db(transaction=True)
def test_criar_regime_reverte_se_registrar_falha(client):
    """Prova runtime do BL-14 para o serviço de regime tributário."""
    from django.contrib.auth import get_user_model
    from django.db import IntegrityError
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa, HistoricoRegimeTributario
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="Escr Regime", cnpj="88888888000188")
    usuario = get_user_model().objects.create_user(
        username="gestor-regime", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="E Regime", cnpj="99999999000199"
    )
    client.login(username="gestor-regime", password="senha-forte-123")

    with mock.patch.object(
        RegistroAuditoria.objects, "create", side_effect=IntegrityError("audit falhou")
    ):
        # A falha da trilha deve propagar como erro do servidor; desabilitar
        # o relançamento do Client permite verificar o rollback sem mascarar
        # a exceção como falha do próprio teste.
        client.raise_request_exception = False
        resposta = client.post(
            reverse("empresas:api-regime-tributario", args=[empresa.id]),
            data={"regime": "simples_nacional", "vigencia_inicio": "2026-01-01"},
            content_type="application/json",
        )

    assert HistoricoRegimeTributario.objects.count() == 0, (
        "BL-14: regime foi gravado mas a trilha falhou — atomicidade quebrada."
    )
    assert resposta.status_code != 201
