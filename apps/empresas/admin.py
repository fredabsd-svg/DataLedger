from django.contrib import admin

from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario


class EstabelecimentoInline(admin.TabularInline):
    model = Estabelecimento
    extra = 0


class HistoricoRegimeTributarioInline(admin.TabularInline):
    model = HistoricoRegimeTributario
    extra = 0


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ["razao_social", "cnpj", "escritorio", "ativo"]
    list_filter = ["escritorio", "ativo"]
    search_fields = ["razao_social", "nome_fantasia", "cnpj"]
    inlines = [EstabelecimentoInline, HistoricoRegimeTributarioInline]
