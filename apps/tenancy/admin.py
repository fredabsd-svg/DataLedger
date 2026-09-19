from django.contrib import admin

from apps.tenancy.models import Escritorio, VinculoUsuarioEscritorio


class VinculoInline(admin.TabularInline):
    model = VinculoUsuarioEscritorio
    extra = 0


@admin.register(Escritorio)
class EscritorioAdmin(admin.ModelAdmin):
    list_display = ["nome", "cnpj", "ativo", "criado_em"]
    search_fields = ["nome", "cnpj"]
    # BL-282: campos de timbre editáveis junto do cadastro — sem eles aqui o
    # único jeito de preencher o timbre seria acesso direto ao banco.
    fields = [
        "nome",
        "cnpj",
        "ativo",
        "razao_social_no_timbre",
        "endereco_no_timbre",
        "registro_no_timbre",
    ]
    inlines = [VinculoInline]


@admin.register(VinculoUsuarioEscritorio)
class VinculoUsuarioEscritorioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "escritorio", "papel", "ativo"]
    list_filter = ["papel", "ativo", "escritorio"]
