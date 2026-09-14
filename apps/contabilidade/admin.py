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
    """Cadastro do plano de contas — inclusão, alteração E exclusão ficam
    disponíveis (decisão explícita, achado novo 2 da auditoria da DL-015,
    rodada 3: "avalie o ContaAdmin e decida"). Diferente de
    `LancamentoContabilAdmin`, `Conta` não tem invariante de partida dobrada
    para reimplementar aqui, e as duas chaves estrangeiras que apontam para
    ela usam `on_delete=PROTECT` (`ItemLancamento.conta` e `Conta.conta_pai`,
    ver models.py): o Django recusa a exclusão — em lote ou individual — de
    QUALQUER conta que já tenha lançamento próprio ou conta filha, com
    mensagem listando o que está protegendo. O `PROTECT` vale tanto para
    `.delete()` quanto para `QuerySet.delete()` (a ação de exclusão em
    lote), porque é aplicado pelo `Collector` de exclusão do Django, não por
    um método sobrescrito no modelo — não é o mesmo problema do achado novo
    2 do lançamento contábil, cuja guarda vivia em `LancamentoContabil.
    delete()` e por isso não valia para a ação em lote. O risco residual
    (apagar conta SEM movimento e SEM filhas, plano de contas mal montado
    por engano) é aceitável para uma tela de cadastro/manutenção.
    """

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

    def has_delete_permission(self, request, obj=None):
        # Achado novo 2 da auditoria da DL-015, rodada 3 (gravidade alta): a
        # ação "delete_selected" da listagem do admin chama
        # `QuerySet.delete()`, que NÃO passa por `LancamentoContabil.delete()`
        # (a guarda que levanta `LancamentoImutavelError`) — apagava
        # lançamento e itens em lote, DEFINITIVAMENTE, sem estorno, sem
        # versão anterior e sem registro em `apps/auditoria`. Pelo caminho
        # individual (".../<id>/delete/") a guarda do modelo rodava, mas
        # como uma exceção que vazava (500), não como uma recusa
        # apresentável. `has_delete_permission=False` fecha os dois
        # caminhos na ORIGEM (o Django nem oferece a ação nem a URL),
        # devolvendo 403 em vez de apagar ou de estourar.
        #
        # A DE-023 já dizia que o admin de lançamento é "somente leitura";
        # esta era a metade que faltava (a outra, alterar, já era False).
        return False
