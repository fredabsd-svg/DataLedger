"""Admin de `Empresa` e `Estabelecimento`.

DL-023 (BL-211/A2): o `HistoricoRegimeTributarioInline` que existia aqui foi
REMOVIDO — não apenas desabilitado. Ele gravava `HistoricoRegimeTributario`
direto por `ModelForm`/formset, nunca passando por
`apps.empresas.services.registrar_regime_tributario`: medido, o inline
deixava nascer DOIS períodos abertos ao mesmo tempo para a mesma empresa
("302" e "periodos ABERTOS simultaneos: 2"), porque o fechamento automático
do período anterior (a linha que fecha `vigencia_fim` do período vigente
quando um novo começa) só existe DENTRO do serviço.

Duas opções estavam abertas pelo plano da etapa ("o inline sai do admin ou
passa pelo serviço"), e a escolha foi tirar o inline:

- Fazer o inline chamar o serviço exigiria reescrever o `save()` do
  formset inteiro (a criação precisaria ir para
  `registrar_regime_tributario`, e a EDIÇÃO de um período já existente não
  tem contrapartida no serviço — o próprio modelo documenta "nunca editar
  um registro já encerrado para corrigir o regime: criar um novo
  período"), duplicando, na camada do admin, uma máquina de estados que já
  existe em `apps/empresas/services.py` e em
  `HistoricoRegimeTributarioListCreateView`/`HistoricoRegimeTributarioDetailView`
  (apps/empresas/views.py) — o oposto do que a AGENTS.md §8 pede (evitar
  duplicação de regra de negócio entre telas).
- Remover o inline é o MESMO desenho que `LancamentoContabilAdmin` já usa
  para o mesmo tipo de risco (dado estruturante com máquina de estados
  própria): o admin deixa de ser porta de escrita para esse modelo, e toda
  gravação de regime tributário passa a acontecer só pela API, que já
  chama o serviço, já valida a faixa de vigência (RC-85/HI-07) e já grava
  `RegistroAuditoria`.

Consequência DECLARADA, e não escondida: os dois testes de
`apps/empresas/tests/test_dl019_regime_tributario.py` que exercitavam esse
inline por requisição (`test_admin_recusa_vigencia_futura_no_inline_e_nao_
grava` e `test_admin_grava_vigencia_passada_no_inline`) passam a FALHAR —
eles mediam o comportamento do caminho que esta etapa existe para fechar.
Este arquivo não os altera (fora do escopo do `desenvolvedor-pleno`, e a
decisão de retirá-los ou reescrevê-los é do `arquiteto-senior`); ver o
relatório de entrega da DL-023.

O regime tributário segue com a UniqueConstraint
"um_periodo_de_regime_aberto_por_empresa" (apps/empresas/models.py) como
defesa de banco válida em toda porta, inclusive a que restar.
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO_DE_GATILHO,
    RestricaoViolada,
    restricao_como_400,
)
from apps.empresas.forms import ajustar_obrigatoriedade_de_cnpj_cpf
from apps.empresas.models import Empresa, Estabelecimento, TipoInscricao
from apps.empresas.services import (
    CNPJDuplicado,
    InscricaoCruzadaEntreEmpresaEEstabelecimento,
    erro_de_cnpj_duplicado_como_400,
    erros_de_consistencia_de_inscricao,
    mensagem_cnpj_duplicado,
    recusar_cnpj_de_empresa_igual_a_estabelecimento_de_outra_empresa,
    recusar_cnpj_de_estabelecimento_igual_a_outra_empresa,
)


class EstabelecimentoInlineFormSet(forms.BaseInlineFormSet):
    """Achado D1 da auditoria DL-039 rodada 1 (BL-533): o gatilho de banco
    (migração 0011) só enxerga a empresa depois que ela JÁ TEM `pk` — na
    CRIAÇÃO pelo admin, o formulário principal (`EmpresaAdminForm`) e este
    inline nascem no MESMO POST, e o campo `empresa` de cada linha do
    inline é preenchido só em `save_new()`, DEPOIS da validação (o campo é
    excluído do formulário do inline — quem o define é o formset, não o
    usuário). Ou seja: `Estabelecimento.clean()` (apps/empresas/models.py)
    nunca examina `empresa_id` a tempo aqui, esteja a empresa sendo criada
    OU editada — o caminho que fechava isso na API (checagem antes do
    INSERT) não tem equivalente nesta camada. Sem esta checagem, criar uma
    empresa CPF com um estabelecimento no inline dava **500**
    (`IntegrityError` do gatilho, sem qualquer tradução possível, porque
    nenhum formulário chega a reportar erro de campo).

    A checagem lê `self.instance.tipo_inscricao` — o formulário PRINCIPAL
    já populou essa instância (via `form.save(commit=False)`, chamado por
    `ModelAdmin.save_form`) ANTES de os formsets serem construídos e
    validados (`ModelAdmin._changeform_view`) — funciona sem `pk`/
    `empresa_id` existir, tanto no `add` quanto no `change`.
    """

    def clean(self):
        super().clean()
        if getattr(self.instance, "tipo_inscricao", None) == TipoInscricao.CPF:
            for form in self.forms:
                if not hasattr(form, "cleaned_data"):
                    continue
                if self.can_delete and self._should_delete_form(form):
                    continue
                if form.cleaned_data and form.has_changed():
                    raise forms.ValidationError(
                        "Não é possível cadastrar estabelecimento (matriz/filial) para "
                        "uma empresa do tipo CPF: NIRE e estabelecimento são exclusivos "
                        "de pessoa jurídica (CNPJ)."
                    )

        # Achado U-A1 da auditoria DL-041 rodada 1: `escritorio` de
        # `Estabelecimento` é `editable=False` (ver apps/empresas/
        # models.py) — EXCLUÍDO do ModelForm do inline, de propósito
        # (nunca é o usuário quem escolhe; é sempre derivado da empresa).
        # Por isso `Estabelecimento.clean()`/`full_clean()` NUNCA examina
        # a `UniqueConstraint` "estabelecimento_cnpj_unico_por_escritorio"
        # (Meta.constraints): ela envolve um campo que nem chega a existir
        # no formulário. Sem esta checagem, cadastrar um estabelecimento
        # com o CNPJ de outro estabelecimento do MESMO escritório batia
        # direto no gatilho de banco — 500 (regressão do critério 3 do
        # plano DL-041: duplicata no mesmo escritório tem que dar erro de
        # FORMULÁRIO, nunca erro de servidor).
        #
        # `self.instance.escritorio` — o formulário PRINCIPAL
        # (`EmpresaAdminForm`) já populou essa instância ANTES de este
        # formset validar (mesmo raciocínio do bloco de CPF, acima): funciona
        # tanto no `add` (escritório escolhido NESTE POST) quanto no
        # `change` (escritório já gravado).
        escritorio = getattr(self.instance, "escritorio", None)
        if escritorio is None:
            return

        cnpjs_do_envio = {}
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            cnpj = form.cleaned_data.get("cnpj")
            if not cnpj:
                continue

            # Duplicata ENTRE LINHAS do mesmo envio (nenhuma das duas
            # ainda está gravada — a `UniqueConstraint` do banco só vê uma
            # de cada vez, uma por INSERT).
            if cnpj in cnpjs_do_envio:
                form.add_error("cnpj", mensagem_cnpj_duplicado(Estabelecimento))
                continue
            cnpjs_do_envio[cnpj] = form

            # Duplicata contra estabelecimento JÁ GRAVADO no MESMO
            # escritório (de qualquer empresa desse escritório — a
            # constraint é `(escritorio, cnpj)`, não `(empresa, cnpj)`).
            duplicado = Estabelecimento.objects.filter(escritorio=escritorio, cnpj=cnpj)
            if form.instance.pk:
                duplicado = duplicado.exclude(pk=form.instance.pk)
            if duplicado.exists():
                form.add_error("cnpj", mensagem_cnpj_duplicado(Estabelecimento))
                continue

            # Achado U-B4 da auditoria DL-041 rodada 1 (decisão do
            # arquiteto-senior): o CNPJ deste estabelecimento não pode ser
            # o MESMO de OUTRA empresa do mesmo escritório — `self.instance`
            # é a empresa PAI deste inline (matriz), então o caso legítimo
            # (matriz com o CNPJ da própria empresa) continua permitido:
            # é exatamente quem `recusar_cnpj_de_estabelecimento_igual_a_
            # outra_empresa` exclui via `empresa_do_estabelecimento`.
            try:
                recusar_cnpj_de_estabelecimento_igual_a_outra_empresa(
                    escritorio.pk, cnpj, empresa_do_estabelecimento=self.instance
                )
            except InscricaoCruzadaEntreEmpresaEEstabelecimento as exc:
                form.add_error("cnpj", str(exc))


class EstabelecimentoInline(admin.TabularInline):
    model = Estabelecimento
    extra = 0
    formset = EstabelecimentoInlineFormSet


class EmpresaAdminForm(forms.ModelForm):
    """Achado B1 da auditoria rodada 1 (DL-038): o admin passou a devolver
    500 para CNPJ/CPF duplicado e para `tipo_inscricao` inconsistente com
    os campos preenchidos, regressão em relação ao comportamento anterior
    à DL-038 (200 com "já existe" no campo). Causa raiz: as duas checagens
    dependiam de `Model.validate_constraints()`, que virou um no-op nesta
    mesma etapa (ver o comentário em `Empresa.validate_constraints`,
    apps/empresas/models.py) por um motivo LEGÍTIMO — devolver a mensagem
    amigável de duplicidade em vez do texto genérico do Django —, mas isso
    também apagou a ÚNICA checagem em Python que o admin tinha para as
    `Meta.constraints` inteiras (`UniqueConstraint`, INCLUSIVE
    `CheckConstraint`), não só a de duplicidade. `Model.validate_unique()`
    (chamado separadamente por `BaseModelForm._post_clean()`) NÃO cobre
    `UniqueConstraint` de `Meta.constraints` por padrão (`_get_unique_
    checks(include_meta_constraints=False)`) — por isso não bastava
    reativar só isso.

    A camada 1 da DE-008 (a `CheckConstraint`/`UniqueConstraint` no BANCO)
    continua intacta e é quem de fato impede o dado inconsistente — este
    `clean()` é só a camada 2 (pré-aviso em Python, mensagem amigável por
    campo), reconstruída aqui especificamente para o admin, reaproveitando
    as MESMAS funções de `apps.empresas.services` que a API
    (`EmpresaSerializer.validate`) já usa — fonte única da regra e da
    mensagem, sem reimplementar a comparação uma terceira vez.

    Achado N4 da reconferência (BL-529, DL-039): até esta correção, o
    admin não criava NEM editava empresa CPF — um POST com
    `tipo_inscricao=CPF` dava 200 com `cnpj: Este campo é obrigatório.` e
    nada era salvo, porque `Meta.fields = "__all__"` herda `required=True`
    de `Empresa.cnpj` (o campo do MODELO não tem `blank=True`, de
    propósito) e nada neste form ajustava isso antes desta correção. O
    `__init__`, abaixo, chama a MESMA função que `EmpresaForm` (tela,
    apps/empresas/forms.py) já usa — `ajustar_obrigatoriedade_de_cnpj_cpf`
    — fonte única também desta metade da regra (a outra metade, o texto de
    erro quando o campo ERRADO vem preenchido, já vinha de
    `erros_de_consistencia_de_inscricao`, chamada em `clean()` abaixo,
    sem mudança).
    """

    class Meta:
        model = Empresa
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ajustar_obrigatoriedade_de_cnpj_cpf(self)

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_inscricao")
        cnpj = cleaned_data.get("cnpj") or ""
        cpf = cleaned_data.get("cpf") or ""

        for campo, mensagem in erros_de_consistencia_de_inscricao(tipo, cnpj, cpf).items():
            self.add_error(campo, mensagem)

        # DL-041 (RC-115/DE-077): a duplicidade só é examinada DENTRO do
        # MESMO escritório — a unicidade deixou de ser global. `escritorio`
        # não aparece em `cleaned_data` na EDIÇÃO (fica em
        # `readonly_fields`, ver `EmpresaAdmin.get_readonly_fields` —
        # campo somente-leitura é EXCLUÍDO do `ModelForm`, nunca chega a
        # `cleaned_data`); nesse caso, o valor certo é o JÁ GRAVADO em
        # `self.instance` (que nunca muda, DL-023). Na CRIAÇÃO, o campo é
        # editável e vem de `cleaned_data` normalmente.
        escritorio = cleaned_data.get("escritorio")
        if escritorio is None and self.instance.pk:
            escritorio = self.instance.escritorio

        if cnpj and escritorio is not None:
            duplicada = Empresa.objects.filter(cnpj=cnpj, escritorio=escritorio)
            if self.instance.pk:
                duplicada = duplicada.exclude(pk=self.instance.pk)
            if duplicada.exists():
                self.add_error("cnpj", mensagem_cnpj_duplicado(Empresa))
            else:
                # Achado U-B4 da auditoria DL-041 rodada 1 (decisão do
                # arquiteto-senior): o CNPJ desta empresa não pode ser o
                # MESMO de um estabelecimento de OUTRA empresa do mesmo
                # escritório — só verificado quando não há duplicidade
                # entre empresas (acima), para não empilhar dois erros no
                # mesmo campo. `self.instance` é excluído pela própria
                # função: a matriz com o CNPJ da própria empresa continua
                # permitida.
                try:
                    recusar_cnpj_de_empresa_igual_a_estabelecimento_de_outra_empresa(
                        escritorio.pk, cnpj, empresa=self.instance
                    )
                except InscricaoCruzadaEntreEmpresaEEstabelecimento as exc:
                    self.add_error("cnpj", str(exc))
        if cpf and escritorio is not None:
            duplicada = Empresa.objects.filter(cpf=cpf, escritorio=escritorio)
            if self.instance.pk:
                duplicada = duplicada.exclude(pk=self.instance.pk)
            if duplicada.exists():
                self.add_error("cpf", mensagem_cnpj_duplicado(Empresa, "CPF"))

        return cleaned_data


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    """Cadastro de empresa.

    DL-023, critério 5 (BL-211/A3): `escritorio` fica em `readonly_fields`
    no `change` — livre no `add` (H1) — para que a troca de escritório de
    uma empresa já cadastrada nunca aconteça pelo caminho cotidiano do
    admin, com ou sem escrituração: o lado seguro e reversível enquanto a
    pendência P1 (transferir empresa entre escritórios é operação real do
    escritório?) não for respondida pelo Fred. `Empresa.clean()`
    (apps/empresas/models.py) continua existindo como a segunda camada,
    condicionada à escrituração — hoje redundante com este `readonly_fields`
    NESTE admin especificamente (a API nunca expôs `escritorio` como campo
    gravável em `EmpresaSerializer`), mas é a defesa que valeria para
    qualquer outro `ModelForm` que um dia voltasse a expor o campo sem
    repetir esta decisão. As duas são testadas separadamente (uma por
    requisição ao admin, a outra por `full_clean()` direto do modelo) —
    ver apps/empresas/tests/test_dl023_empresa_nao_muda_de_escritorio.py.
    """

    # DL-038: tipo_inscricao/modo_escrituracao entram na listagem e nos
    # filtros — são o que diferencia uma empresa CPF/livro-caixa de uma
    # CNPJ/contabilidade, e o admin sem eles esconderia a distinção mais
    # importante desta etapa. cpf entra em search_fields pelo mesmo motivo
    # de cnpj já estar lá.
    list_display = [
        "razao_social",
        "tipo_inscricao",
        "cnpj",
        "cpf",
        "modo_escrituracao",
        "escritorio",
        "ativo",
    ]
    list_filter = ["escritorio", "ativo", "tipo_inscricao", "modo_escrituracao"]
    search_fields = ["razao_social", "nome_fantasia", "cnpj", "cpf"]
    inlines = [EstabelecimentoInline]
    # Achado B1: sem este form próprio, o admin usa o `ModelForm`
    # AUTOGERADO do Django, que não faz mais a pré-checagem de duplicidade
    # nem de consistência tipo/campo — ver o docstring de `EmpresaAdminForm`.
    form = EmpresaAdminForm

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            # `add`: a empresa ainda não existe, "trocar" de escritório não
            # faz sentido — é a primeira atribuição, não uma transferência.
            return []
        return ["escritorio"]

    def save_model(self, request, obj, form, change):
        # Achado D1 da auditoria DL-039 rodada 1 (BL-533): defesa em
        # profundidade para a JANELA DE CORRIDA entre a validação do
        # formulário (`EmpresaAdminForm.clean()`, camada 2 da DE-008) e
        # este `save()` — outra requisição concorrente (API, outro admin)
        # pode ter gravado um estabelecimento para esta empresa NESSE
        # meio-tempo. Sem isto, o gatilho de banco (camada 1) ainda
        # recusa a gravação (nada fica inconsistente), mas a
        # `IntegrityError` sobe CRUA, com texto interno do banco, e o
        # admin devolve 500. Aqui ela é traduzida para a MESMA mensagem
        # de negócio da API (`apps.core.restricoes.MENSAGENS_DE_
        # RESTRICAO_DE_GATILHO`) antes de subir.
        #
        # LIMITE DECLARADO: `ModelAdmin._changeform_view` não tem um
        # ponto de extensão para, a partir daqui, voltar a renderizar o
        # MESMO formulário com erro de campo (isso já aconteceu — a
        # decisão de "sucesso" já foi tomada antes deste método rodar).
        # Diferente do caminho comum (`EstabelecimentoInlineFormSet.
        # clean()`, acima, que RESOLVE o caso mais provável — empresa CPF
        # com estabelecimento no MESMO POST — com 200 de verdade, ANTES
        # de chegar aqui), esta janela de corrida específica é rara
        # (exige uma escrita concorrente de OUTRO processo, entre a
        # validação e o save desta MESMA requisição) e o resultado, hoje,
        # é uma página de erro do Django com a mensagem TRADUZIDA (nunca
        # o texto cru do banco) — não um 200 com o formulário de volta.
        # Fechar isso por completo exigiria sobrepor `_changeform_view`
        # inteiro (método privado do Django, alto custo de manutenção
        # para um achado de gravidade média); registrado para o
        # arquiteto-senior decidir se vale o custo.
        try:
            with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
                super().save_model(request, obj, form, change)
        except RestricaoViolada as exc:
            # `transaction.atomic()` acima já é um SAVEPOINT (estamos
            # dentro do `atomic()` que envolve `_changeform_view` inteiro)
            # — sai limpo da `IntegrityError`. Este `set_rollback(True)`
            # marca a transação EXTERNA também: nada deste POST pode ficar
            # gravado pela metade (ex.: a empresa salva por este método,
            # mas o estabelecimento do inline recusado por `save_related`
            # depois).
            transaction.set_rollback(True)
            raise ValidationError(str(exc)) from exc

    def save_related(self, request, form, formsets, change):
        # Mesma defesa do `save_model` acima, para o INSERT/UPDATE de
        # `Estabelecimento` que os formsets deste admin gravam.
        #
        # Achado U-A1 (auditoria DL-041 rodada 1): `EstabelecimentoInline
        # FormSet.clean()` (acima) já resolve o caso comum — duplicata no
        # MESMO envio — com erro de formulário de verdade, ANTES de
        # chegar aqui. `erro_de_cnpj_duplicado_como_400()` entra como
        # DEFESA FINAL para a mesma janela de corrida do achado D1/BL-533
        # (DL-039): outra requisição concorrente grava o CNPJ duplicado
        # ENTRE a validação do formset e este `save()`. Traduz a
        # `UniqueConstraint` "estabelecimento_cnpj_unico_por_escritorio"
        # (registrada em `apps.empresas.services._CONSTRAINTS_INSCRICAO_
        # UNICA`, não em `MENSAGENS_DE_RESTRICAO_DE_GATILHO` — aquela é só
        # para pseudo-restrições de GATILHO, ver o comentário em
        # `apps.core.restricoes`) — mesmo limite já declarado para
        # `save_model`: nunca chega a re-renderizar o MESMO formulário
        # com o erro (o Django admin não tem esse gancho depois de
        # `save_model`/`save_related` rodarem), mas nunca mais um 500 com
        # texto cru do banco.
        try:
            with (
                transaction.atomic(),
                erro_de_cnpj_duplicado_como_400(),
                restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO),
            ):
                super().save_related(request, form, formsets, change)
        except CNPJDuplicado as exc:
            transaction.set_rollback(True)
            raise ValidationError(str(exc)) from exc
        except RestricaoViolada as exc:
            transaction.set_rollback(True)
            raise ValidationError(str(exc)) from exc
