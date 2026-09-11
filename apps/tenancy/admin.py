from django.contrib import admin

from apps.tenancy.models import Escritorio, VinculoUsuarioEscritorio


class VinculoInline(admin.TabularInline):
    model = VinculoUsuarioEscritorio
    extra = 0


@admin.register(Escritorio)
class EscritorioAdmin(admin.ModelAdmin):
    list_display = ["nome", "cnpj", "ativo", "criado_em"]
    search_fields = ["nome", "cnpj"]
    inlines = [VinculoInline]


@admin.register(VinculoUsuarioEscritorio)
class VinculoUsuarioEscritorioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "escritorio", "papel", "ativo"]
    list_filter = ["papel", "ativo", "escritorio"]
