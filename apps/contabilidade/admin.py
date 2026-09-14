from django.contrib import admin

from apps.contabilidade.models import Conta, ItemLancamento, LancamentoContabil


class ItemLancamentoInline(admin.TabularInline):
    model = ItemLancamento
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        # `obj` é o `LancamentoContabil` pai (None na inclusão — mas a
        # inclusão está DESABILITADA, ver `LancamentoContabilAdmin.
        # has_add_permission` abaixo). Guardamos a empresa do pai para
        # `formfield_for_foreignkey` restringir o campo `conta` — defesa em
        # profundidade (achado novo 6/BL-79): mesmo que uma política futura
        # reabra a inclusão, o campo já não vai oferecer conta de OUTRA
        # empresa no dropdown.
        self._empresa_do_lancamento = obj.empresa if obj is not None else None
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "conta" and getattr(self, "_empresa_do_lancamento", None) is not None:
            kwargs["queryset"] = Conta.objects.filter(empresa=self._empresa_do_lancamento)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Conta)
class ContaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nome", "tipo", "natureza", "empresa", "aceita_lancamento", "ativo"]
    list_filter = ["empresa", "tipo", "ativo"]
    search_fields = ["codigo", "nome"]


@admin.register(LancamentoContabil)
class LancamentoContabilAdmin(admin.ModelAdmin):
    """Consulta de lançamentos contábeis pelo Django admin — só leitura.

    Achado novo 6 da auditoria da DL-015, rodada 2 (BL-79): pela tela de
    inclusão, o admin gravava item com conta de OUTRA empresa, lote
    DESBALANCEADO e lote SEM NENHUMA partida — nenhum dos três passa por
    `criar_lancamento`, que é onde vive TODA a validação contábil (partida
    dobrada, mesma empresa, valor positivo, escala). A DE-021 afirmava que
    esse estado "só nasce por gravação direta no ORM — a API não permite";
    o admin era um segundo caminho de nascimento que essa decisão não tinha
    considerado.

    Decisão de implementação desta correção (`desenvolvedor-pleno`, com
    delegação explícita do `arquiteto-senior` para "decidir e implementar o
    que o admin pode gravar" no encaminhamento do achado novo 6 — pendente
    de registro formal em `decisoes.md` pelo `arquiteto-senior`): o admin
    NÃO oferece inclusão de lançamento. Reimplementar aqui a validação de
    partida dobrada duplicaria a regra que já vive em `criar_lancamento`
    (AGENTS.md §8 — evitar duplicação de regra de negócio entre telas), e
    o admin não é o caminho de escrituração do produto — é ferramenta de
    suporte/consulta. Toda criação de lançamento continua exigida pela API
    (`POST .../lancamentos/`), que valida tudo. `ItemLancamento.clean()`
    (mesma correção) permanece como defesa em profundidade, para qualquer
    outro caminho que chame `full_clean()`.
    """

    list_display = ["id", "empresa", "data", "historico", "estorno_de"]
    list_filter = ["empresa"]
    inlines = [ItemLancamentoInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Lançamentos são imutáveis (ver LancamentoContabil.save): o admin
        # não deve nem oferecer a tela de edição.
        return False
