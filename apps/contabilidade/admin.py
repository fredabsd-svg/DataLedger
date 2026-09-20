from django.contrib import admin

from apps.contabilidade.models import Competencia, Conta, ItemLancamento, LancamentoContabil
from apps.empresas.models import Empresa


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

    O risco de ALTERAÇÃO (não só o de exclusão, que o parágrafo acima já
    cobria) foi corrigido na DL-023 (BL-83, achado novo 1 da auditoria
    DL-015 rodada 4): este admin deixava mover conta COM movimento para
    OUTRA empresa e trocar a NATUREZA/TIPO de conta já movimentada — o
    balancete da empresa de origem passava a fechar torto (zero de débito
    contra mil de crédito) sem nenhuma das quatro categorias da conferência
    acusar, e a troca de natureza invertia o sinal de todo o histórico da
    conta. A defesa mora em `Conta.clean()` (apps/contabilidade/models.py),
    não aqui: um validador de MODELO vale para este `ModelForm` e para
    qualquer outro caminho que chame `full_clean()`, e não só para esta
    tela — é o padrão da etapa ("regra que o admin tem que respeitar mora
    no modelo"). Conta SEM movimento e SEM filhas continua totalmente
    editável (critério 4 da DL-023): a defesa só dispara na TRANSIÇÃO de um
    estado que já tem o que proteger.
    """

    list_display = ["codigo", "nome", "tipo", "natureza", "empresa", "aceita_lancamento", "ativo"]
    list_filter = ["empresa", "tipo", "ativo"]
    search_fields = ["codigo", "nome"]

    def _escritorio_da_conta_em_edicao(self, request):
        """`escritorio_id` da empresa ATUAL da conta sendo editada, ou
        `None` no `add` (não há conta ainda) — usado por
        `formfield_for_foreignkey` para restringir o dropdown de `empresa`
        (BL-248, achado P4 da auditoria DL-023 rodada 1).

        Lido da URL resolvida (`request.resolver_match.kwargs["object_id"]`),
        não de `self.model.objects.get(...)` adivinhado de outro jeito — é o
        mesmo mecanismo que o próprio Django usa internamente para saber
        qual objeto a view de `change` está editando.
        """
        resolver_match = getattr(request, "resolver_match", None)
        object_id = resolver_match.kwargs.get("object_id") if resolver_match else None
        if not object_id:
            return None
        return (
            Conta.objects.filter(pk=object_id)
            .values_list("empresa__escritorio_id", flat=True)
            .first()
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "empresa":
            escritorio_id = self._escritorio_da_conta_em_edicao(request)
            if escritorio_id is not None:
                # BL-248: sem isto, o dropdown listava a razão social de
                # TODAS as empresas de TODOS os escritórios — vazamento
                # pré-existente que a varredura do critério 12 tinha
                # classificado como "defendida" sem nomear (medido pelo
                # auditor: `CLIENTE SIGILOSO`, de outro escritório,
                # aparecia no corpo do formulário reapresentado). Restringe
                # ao escritório da empresa ATUAL da conta:
                # `Conta.clean()` já recusa a GRAVAÇÃO de uma empresa de
                # outro escritório (defesa de modelo, camada 2); isto é a
                # defesa de FORMULÁRIO — nem oferece a opção no dropdown
                # (camada 1, evita o vazamento em si, não só a gravação).
                # No `add` (`escritorio_id is None`, sem conta ainda para
                # ancorar a restrição), o campo continua livre — mesmo
                # limite que o `add` de `EmpresaAdmin` já tem (H1).
                kwargs["queryset"] = Empresa.objects.filter(escritorio_id=escritorio_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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


@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    """Consulta de competências pelo Django admin — só leitura.

    Uma competência nasce em `criar_lancamento` (F2, transação atômica),
    quando o escritório registra o primeiro lançamento de um mês, ou em
    qualquer das três operações da fatia 1 da DL-016
    (`apps.contabilidade.services.encerrar_competencia`,
    `reabrir_competencia`, `marcar_competencia_como_entregue` —
    `obter_ou_criar_competencia` garante a linha nos quatro caminhos, com o
    mesmo tratamento de corrida). Pelo produto, a única operação esperada do
    admin sobre competência é CONSULTAR (qual mês está em aberto para qual
    empresa, qual está encerrado, quais lançamentos pertencem a qual).
    Reproduzir a abertura/encerramento/reabertura/entrega no admin
    duplicaria a regra de transição de estado que já vive nos services
    (mesma razão que motivou o `has_add_permission=False` em
    `LancamentoContabilAdmin` logo acima), e abriria um caminho de transição
    que pula a validação de origem (RC-58 no fechamento, RC-101 na
    reabertura) e a trilha de auditoria — a guarda de transição de estado é
    a parte que a auditoria da DL-015 rodada 3 mais detalhou (achado novo 3,
    gravidade alta) e que decidiu centralizar nos services. Aqui, listamos
    e filtramos; mutações continuam pela API.
    """

    list_display = [
        "empresa",
        "ano",
        "mes",
        "estado",
        "fechada_em",
        "entregue_em",
        "criado_em",
    ]
    list_filter = ["estado", "ano", "mes"]
    search_fields = ["empresa__razao_social"]

    def has_add_permission(self, request):
        # Não oferecemos o botão "Adicionar competência": competência nasce
        # na F2 (criar_lancamento). Sem add aqui = sem caminho de criação
        # via admin.
        return False

    def has_change_permission(self, request, obj=None):
        # Não oferecemos edição: encerramento/reabertura passam pelos
        # services de F3 e F4 (validação de transições + auditoria).
        return False

    def has_delete_permission(self, request, obj=None):
        # Não oferecemos exclusão: competência não é descartável; o
        # encerramento é via `encerrar_competencia` (F3).
        return False
