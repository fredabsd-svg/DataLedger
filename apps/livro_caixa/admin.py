from django.contrib import admin

from apps.empresas.models import Empresa
from apps.livro_caixa.models import ContaLivroCaixa, LancamentoCaixa


@admin.register(ContaLivroCaixa)
class ContaLivroCaixaAdmin(admin.ModelAdmin):
    """Cadastro de conta do livro-caixa — inclusão e alteração disponíveis.

    O `ModelForm` automático do admin passa por `ContaLivroCaixa.full_clean()`
    (`_post_clean()`), que já aplica a recusa por modo de escrituração e a
    coerência natureza↔código do Carnê-Leão Web (`clean()`, model.py) — não
    há validação de negócio própria para reimplementar aqui, mesmo raciocínio
    de `ContaAdmin` (contabilidade): a regra mora no modelo, não na tela nem
    no admin.

    M3 (rodada 1 de auditoria): `empresa` é SOMENTE LEITURA na edição —
    mesmo padrão de `EmpresaAdmin.get_readonly_fields` para `escritorio`
    (DL-023). `ContaLivroCaixa.clean()` já recusa a troca quando há
    lançamento gravado (defesa de MODELO, camada 2 da DE-008); esta é a
    camada 1 — nem oferece o campo editável no formulário do admin, único
    caminho que a rodada 1 mediu como capaz de produzir o estado
    inconsistente (`empresa` do lançamento ≠ `empresa` da conta).
    """

    list_display = ["codigo", "nome", "natureza", "codigo_carne_leao", "empresa", "ativa"]
    list_filter = ["empresa", "natureza", "ativa"]
    search_fields = ["codigo", "nome"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            # `add`: a conta ainda não existe, "trocar" de empresa não faz
            # sentido — é a primeira atribuição, não uma transferência.
            return []
        return ["empresa"]

    def _escritorio_da_conta_em_edicao(self, request):
        resolver_match = getattr(request, "resolver_match", None)
        object_id = resolver_match.kwargs.get("object_id") if resolver_match else None
        if not object_id:
            return None
        return (
            ContaLivroCaixa.objects.filter(pk=object_id)
            .values_list("empresa__escritorio_id", flat=True)
            .first()
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "empresa":
            escritorio_id = self._escritorio_da_conta_em_edicao(request)
            if escritorio_id is not None:
                # Mesma defesa de isolamento de `ContaAdmin` (BL-248): não
                # oferece empresa de OUTRO escritório no dropdown.
                kwargs["queryset"] = Empresa.objects.filter(escritorio_id=escritorio_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(LancamentoCaixa)
class LancamentoCaixaAdmin(admin.ModelAdmin):
    """Consulta de lançamentos de caixa pelo Django admin — só LEITURA.

    Mesma decisão de `LancamentoContabilAdmin` (contabilidade): a criação de
    um lançamento de caixa passa pela API (`POST .../lancamentos/`), que
    valida tudo pelo serviço `apps.livro_caixa.services.
    criar_lancamento_caixa` (recusa por modo, coerência, idempotência,
    trilha de auditoria na mesma transação). Reimplementar isso aqui
    duplicaria a regra de negócio (AGENTS.md §8); o admin não é o caminho de
    escrituração do produto, é ferramenta de suporte/consulta. `save()`/
    `delete()` do modelo já recusam qualquer tentativa de alteração/exclusão
    individual (`LancamentoCaixaImutavelError`), mas a ação em lote
    "delete_selected" da listagem chama `QuerySet.delete()` — que NÃO passa
    por `LancamentoCaixa.delete()` — por isso `has_delete_permission=False`
    fecha esse caminho na ORIGEM, não só pelo caminho individual.
    """

    list_display = ["id", "empresa", "data", "conta", "valor", "historico", "estorno_de"]
    list_filter = ["empresa", "conta__natureza"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
