from django.contrib import admin

from apps.auditoria.models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ["acao", "usuario", "escritorio", "objeto_tipo", "criado_em"]
    list_filter = ["acao", "escritorio"]
    search_fields = ["acao", "objeto_tipo", "objeto_id"]
    readonly_fields = [f.name for f in RegistroAuditoria._meta.fields]

    def has_add_permission(self, request):
        # Registros de auditoria só são criados pelo próprio sistema.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # DL-023, critério 13 (achado do inventário de `24f6bbc`):
        # `has_add_permission` e `has_change_permission` já devolviam
        # `False`, e todos os campos já eram `readonly` — mas a exclusão
        # não estava sobrescrita, e ficava sujeita só à permissão de
        # modelo padrão do Django (`delete_registroauditoria`). Qualquer
        # usuário com essa permissão podia apagar registro de auditoria
        # pelo admin, individualmente OU pela ação em lote da listagem
        # ("Excluir os X registros de auditoria selecionados"), sem
        # nenhuma checagem própria — e a trilha de auditoria é o que resta
        # quando todo o resto falha (AGENTS.md, seção 11: "trilha de
        # auditoria protegida"). O restante da atomicidade/exclusão do log
        # (BL-14/BL-16/BL-57) segue fora do escopo desta etapa: aqui entra
        # só este bloqueio de exclusão pelo admin.
        #
        # Critério 11 da DL-023 (trilha), AUSÊNCIA DECLARADA: a tentativa
        # bloqueada aqui NÃO gera um segundo `RegistroAuditoria` registrando
        # a tentativa — geraria log sobre log, e nenhum mecanismo deste
        # projeto faz isso hoje. Auditar TENTATIVAS de violação, se um dia
        # for necessário, é BL-244 (pacote 3), não esta etapa.
        return False
