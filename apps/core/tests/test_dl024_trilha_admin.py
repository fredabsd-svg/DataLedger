"""BL-244 (DL-024): trilha do painel administrativo.

Medido pelo auditor: nenhum `apps/*/admin.py` chama `registrar()`. Salvar
ou excluir `Empresa`, `Conta`, `Estabelecimento`, `HistoricoRegimeTributario`,
`Escritorio` ou `VinculoUsuarioEscritorio` pelo admin saía sem rastro na
trilha do produto (só o `LogEntry` interno do Django, log de framework).

Esta correção adiciona três signals genéricos em
`apps/auditoria/signals.py`:

- `pre_save` tira snapshot do estado em disco ANTES do save (só quando
  UPDATE + via admin).
- `post_save` registra `"{model}.admin_criado"` ou
  `"{model}.admin_atualizado"` com `detalhes = {valores_anteriores,
  valores_novos}` para UPDATE; INSERT com `detalhes` vazio.
- `pre_delete` registra `"{model}.admin_excluido"` com
  `detalhes = {valores_anteriores}` antes do `DELETE` sair.

A detecção do "caminho admin" usa `request.path.startswith("/admin/")`,
e a request vem de uma thread-local
(`apps.core.current_request.set_current_request`) preenchida pelo
`CurrentRequestMiddleware`. Se não-admin (API, teste, management
command), os handlers saem sem fazer nada — as views continuam
responsáveis pelo seu próprio `registrar()` (BL-14) e a BL-244 não
duplica trilha.

Testes:

1. **Estático** (`test_*`): lê o fonte via `inspect.getsource` e
   confirma a presença da estrutura. Roda sem banco.

2. **Runtime** (`@pytest.mark.django_db(transaction=True)`): usa o
   cliente Django, simula `POST /admin/.../.../add/` e
   `POST /admin/.../.../<pk>/change/`, e verifica o `RegistroAuditoria`
   resultante. A CI é quem roda.
"""

import inspect

# -----------------------------------------------------------------------
# 1. Fonte estático — estrutura da correção
# -----------------------------------------------------------------------


def test_middleware_current_request_existe_e_esta_em_settings():
    """`apps.core.middleware.CurrentRequestMiddleware` precisa existir e
    estar em `settings.MIDDLEWARE`."""
    from config import settings

    assert "apps.core.middleware.CurrentRequestMiddleware" in settings.MIDDLEWARE, (
        "BL-244: `apps.core.middleware.CurrentRequestMiddleware` precisa "
        "estar em settings.MIDDLEWARE — sem isso, a thread-local não é "
        "preenchida e o signal handler da BL-244 cai fora."
    )


def test_thread_local_de_current_request_existe():
    """`apps/core/current_request.py` precisa expor `set_current_request`,
    `get_current_request` e `clear_current_request`."""
    from apps.core import current_request

    for nome in ("set_current_request", "get_current_request", "clear_current_request"):
        assert hasattr(current_request, nome), (
            f"BL-244: `apps.core.current_request.{nome}` precisa existir"
        )


def test_signals_de_admin_existem_e_cobrem_os_seis_modelos():
    """`apps/auditoria/signals.py` precisa definir `MODELOS_DA_TRILHA_DO_ADMIN`
    com exatamente os seis modelos da CA-4:
    `Empresa`, `Conta`, `Estabelecimento`, `HistoricoRegimeTributario`,
    `Escritorio`, `VinculoUsuarioEscritorio`.

    Cobertura explícita (não ancorada em `sender=Model`) porque se
    `ModelAdmin` for registrado para um modelo que NÃO está aqui, a
    falha tem de ser visível (em vez de cair fora por engano).
    """
    from apps.auditoria import signals

    assert hasattr(signals, "MODELOS_DA_TRILHA_DO_ADMIN"), (
        "BL-244: `MODELOS_DA_TRILHA_DO_ADMIN` precisa existir em signals.py"
    )

    esperados = {
        "Empresa",
        "Conta",
        "Estabelecimento",
        "HistoricoRegimeTributario",
        "Escritorio",
        "VinculoUsuarioEscritorio",
    }
    nomes = {m.__name__ for m in signals.MODELOS_DA_TRILHA_DO_ADMIN}
    assert nomes == esperados, (
        f"BL-244: lista da trilha do admin divergente.\n"
        f"Esperado: {sorted(esperados)}\nObtido: {sorted(nomes)}"
    )


def test_handlers_de_admin_existem_e_estao_anexados_a_post_save_pre_save_pre_delete():
    """Os três handlers da BL-244 precisam estar ancorados nos signals
    certos, sem `sender=` específico (filtragem pela lista)."""
    from apps.auditoria import signals

    src = inspect.getsource(signals)
    assert "@receiver(pre_save)" in src, (
        "BL-244: handler `_admin_pre_save_snapshot` precisa estar anexado a `@receiver(pre_save)`"
    )
    assert "@receiver(post_save)" in src, (
        "BL-244: handler `_admin_post_save_registra` precisa estar anexado a `@receiver(post_save)`"
    )
    assert "@receiver(pre_delete)" in src, (
        "BL-244: handler `_admin_pre_delete_registra` precisa estar "
        "anexado a `@receiver(pre_delete)`"
    )


def test_deteccao_do_caminho_admin_por_prefixo_de_path():
    """A heurística de detecção é `request.path.startswith("/admin/")` —
    o suficiente para o painel padrão do Django. Sem isso, signal pode
    disparar por engano em testes/API."""
    from apps.auditoria.signals import _vem_do_admin

    class Req:
        def __init__(self, path):
            self.path = path

    assert _vem_do_admin(Req("/admin/empresas/empresa/add/")) is True
    assert _vem_do_admin(Req("/admin/contabilidade/conta/1/change/")) is True
    assert _vem_do_admin(Req("/api/empresas/")) is False
    assert _vem_do_admin(Req("/auditoria/")) is False
    assert _vem_do_admin(None) is False


# -----------------------------------------------------------------------
# 2. Runtime — save/excluir via admin gera trilha (CI only)
# -----------------------------------------------------------------------


import pytest  # noqa: E402


@pytest.mark.django_db(transaction=True)
def test_save_de_empresa_via_admin_gera_trilha():
    """`POST /admin/empresas/empresa/add/` resulta em um `RegistroAuditoria`
    com `acao='empresas.empresa.admin_criado'`."""
    from django.contrib.auth import get_user_model
    from django.test import Client

    from apps.auditoria.models import RegistroAuditoria
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-244", cnpj="11111111000111")
    get_user_model().objects.create_superuser(
        username="admin", password="senha-forte-123", email="a@a.com"
    )

    client = Client()
    client.login(username="admin", password="senha-forte-123")

    resposta = client.post(
        "/admin/empresas/empresa/add/",
        data={
            "escritorio": escritorio.pk,
            "razao_social": "R BL-244",
            "nome_fantasia": "F BL-244",
            "cnpj": "11122233000183",
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
        },
        follow=False,
    )
    # 302 = redirect para a página de "object saved" do admin.
    assert resposta.status_code == 302, resposta.content

    regs = RegistroAuditoria.objects.filter(acao="empresas.empresa.admin_criado")
    assert regs.count() >= 1


@pytest.mark.django_db(transaction=True)
def test_change_de_empresa_via_admin_gera_trilha_com_diff():
    """`POST /admin/empresas/empresa/<pk>/change/` resulta em `RegistroAuditoria`
    com `detalhes = {valores_anteriores, valores_novos}` para os campos
    que mudaram."""
    from django.contrib.auth import get_user_model
    from django.test import Client

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-244c", cnpj="33333333000133")
    get_user_model().objects.create_superuser(
        username="admin2", password="senha-forte-123", email="b@b.com"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Original",
        nome_fantasia="F Original",
        cnpj="44455566000183",
    )

    client = Client()
    client.login(username="admin2", password="senha-forte-123")

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        data={
            "escritorio": escritorio.pk,
            "razao_social": "Atualizada",
            "nome_fantasia": "F Original",
            "cnpj": "44455566000183",
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
        },
        follow=False,
    )
    assert resposta.status_code == 302

    reg = RegistroAuditoria.objects.filter(acao__endswith="admin_atualizado").get()
    assert "valores_anteriores" in reg.detalhes
    assert "valores_novos" in reg.detalhes
    assert reg.detalhes["valores_anteriores"].get("razao_social") == "Original"
    assert reg.detalhes["valores_novos"].get("razao_social") == "Atualizada"
