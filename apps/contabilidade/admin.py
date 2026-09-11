from django.contrib import admin

from apps.contabilidade.models import Conta, ItemLancamento, LancamentoContabil


class ItemLancamentoInline(admin.TabularInline):
    model = ItemLancamento
    extra = 0


@admin.register(Conta)
class ContaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nome", "tipo", "natureza", "empresa", "aceita_lancamento", "ativo"]
    list_filter = ["empresa", "tipo", "ativo"]
    search_fields = ["codigo", "nome"]


@admin.register(LancamentoContabil)
class LancamentoContabilAdmin(admin.ModelAdmin):
    list_display = ["id", "empresa", "data", "historico", "estorno_de"]
    list_filter = ["empresa"]
    inlines = [ItemLancamentoInline]

    def has_change_permission(self, request, obj=None):
        # Lançamentos são imutáveis (ver LancamentoContabil.save): o admin
        # não deve nem oferecer a tela de edição.
        return False
