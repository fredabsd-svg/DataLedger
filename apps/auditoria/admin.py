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
