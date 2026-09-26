"""BL-244 (DL-024) / DL-030: trilha do painel administrativo.

Medido pelo auditor: nenhum `apps/*/admin.py` chama `registrar()`. Salvar
ou excluir modelo administrável pelo admin saía sem rastro na trilha do
produto (só o `LogEntry` interno do Django, log de framework).

DL-030 substituiu a cobertura original (tupla fixa de seis modelos,
`MODELOS_DA_TRILHA_DO_ADMIN`) por uma PROPRIEDADE derivada do registro de
apps do Django — ver `signals.modelos_cobertos_pela_trilha()` e o teste
`test_cobertura_da_trilha_e_todo_modelo_concreto_dos_apps_do_projeto_menos_exclusao`
abaixo. Os testes de R2 (guarda da cobertura), R4 (redação de segredo), R5
(atomicidade do admin), R6 (escritório do objeto) e R7 (inline) da DL-030
vivem em `apps/core/tests/test_dl030_trilha_cobre_o_admin.py`, arquivo
próprio da etapa — este arquivo manteve os testes originais da DL-024
que continuam válidos sem alteração de comportamento.

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


def test_cobertura_da_trilha_e_todo_modelo_concreto_dos_apps_do_projeto_menos_exclusao():
    """DL-030 (R1), substituindo o RETRATO anterior (tupla fixa de seis
    nomes — `MODELOS_DA_TRILHA_DO_ADMIN`, removida): a cobertura agora é a
    PROPRIEDADE "todo modelo concreto de app PRÓPRIO do projeto está
    coberto, exceto o que estiver declarado em
    `EXCLUSAO_DA_TRILHA_DO_ADMIN` com motivo".

    Não é mais um conjunto fixo de nomes — modelo novo criado em
    `apps/*/models.py` (accounts, auditoria, contabilidade, core,
    empresas, fiscal, tenancy) precisa aparecer aqui SOZINHO, sem editar
    este teste. A LISTA abaixo é o retrato — precisa ser atualizada quando
    um app novo entra (como `apps.fiscal`, DL-010 F1); a PROPRIEDADE que o
    mecanismo garante é a fonte de verdade (`signals.
    modelos_cobertos_pela_trilha()`), nunca esta lista sozinha.
    """
    from apps.accounts.models import Usuario
    from apps.auditoria import signals
    from apps.auditoria.models import RegistroAuditoria
    from apps.contabilidade.models import (
        Competencia,
        Conta,
        ItemLancamento,
        LancamentoContabil,
        ParametroContabilEmpresa,
    )
    from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
    from apps.fiscal.models import (
        DocumentoFiscal,
        EventoFiscal,
        LoteDeRecepcao,
        ResultadoDoArquivo,
        VinculoDocumentoEmpresa,
    )
    from apps.tenancy.models import ConviteEscritorio, Escritorio, VinculoUsuarioEscritorio

    cobertos = signals.modelos_cobertos_pela_trilha()

    esperados_cobertos = {
        Usuario,
        Escritorio,
        VinculoUsuarioEscritorio,
        ConviteEscritorio,
        Empresa,
        HistoricoRegimeTributario,
        Estabelecimento,
        Competencia,
        Conta,
        LancamentoContabil,
        ItemLancamento,
        # DL-043 (BL-474): `ParametroContabilEmpresa` entrou na cobertura
        # pelo MESMO mecanismo "por padrão" do bloco de `apps.fiscal`
        # abaixo — nenhum admin.py registra este modelo de propósito (ver
        # o docstring da classe em `apps/contabilidade/models.py`: a
        # ÚNICA porta de escrita é o serviço, sob `select_for_update()`,
        # e um `ModelForm` de admin contornaria essa trava de
        # concorrência/vigência, o mesmo motivo que já tirou o inline de
        # `HistoricoRegimeTributario` do admin de empresas). Sem registro
        # no admin, os handlers deste módulo nunca disparam por essa
        # rota hoje — a cobertura aqui é só a garantia de que, se algum
        # dia alguém registrar o modelo no admin, a trilha já alcança.
        ParametroContabilEmpresa,
        # DL-010 F1 (2026-09-25): apps.fiscal é um app PRÓPRIO do projeto e
        # não tem entrada em EXCLUSAO_DA_TRILHA_DO_ADMIN — entrou na
        # cobertura por PADRÃO (R1/DE-056), sem decisão explícita, mesmo
        # sem admin.py próprio (o plano da etapa proíbe registrar estes
        # modelos no admin — BL-262, admin não isola por escritório). Isso
        # é seguro: sem registro no admin, não existe rota /admin/ para
        # estes modelos, então os handlers deste módulo nunca disparam de
        # fato hoje — a cobertura é só a garantia de que, se algum dia
        # alguém registrar um destes modelos no admin, a trilha já os
        # alcança sem precisar lembrar de habilitar nada aqui.
        DocumentoFiscal,
        EventoFiscal,
        LoteDeRecepcao,
        ResultadoDoArquivo,
        VinculoDocumentoEmpresa,
    }
    assert cobertos == esperados_cobertos, (
        f"DL-030: cobertura da trilha divergente.\n"
        f"Esperado: {sorted(m.__name__ for m in esperados_cobertos)}\n"
        f"Obtido: {sorted(m.__name__ for m in cobertos)}"
    )
    # RegistroAuditoria é a única exclusão hoje, e precisa continuar FORA
    # da cobertura e DENTRO da lista de exclusão com motivo (evita o laço
    # "trilha audita a si mesma" — ver docstring de EXCLUSAO_DA_TRILHA_DO_ADMIN).
    assert RegistroAuditoria not in cobertos
    assert RegistroAuditoria in signals.EXCLUSAO_DA_TRILHA_DO_ADMIN
    assert signals.EXCLUSAO_DA_TRILHA_DO_ADMIN[RegistroAuditoria], (
        "DL-030: toda exclusão precisa ter motivo não vazio escrito"
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
            "tipo_inscricao": "CNPJ",
            "cnpj": "11122233000183",
            "modo_escrituracao": "contabilidade",
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
            "tipo_inscricao": "CNPJ",
            "cnpj": "44455566000183",
            "modo_escrituracao": "contabilidade",
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
