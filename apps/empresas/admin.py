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

from apps.empresas.models import Empresa, Estabelecimento
from apps.empresas.services import erros_de_consistencia_de_inscricao, mensagem_cnpj_duplicado


class EstabelecimentoInline(admin.TabularInline):
    model = Estabelecimento
    extra = 0


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
    """

    class Meta:
        model = Empresa
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_inscricao")
        cnpj = cleaned_data.get("cnpj") or ""
        cpf = cleaned_data.get("cpf") or ""

        for campo, mensagem in erros_de_consistencia_de_inscricao(tipo, cnpj, cpf).items():
            self.add_error(campo, mensagem)

        if cnpj:
            duplicada = Empresa.objects.filter(cnpj=cnpj)
            if self.instance.pk:
                duplicada = duplicada.exclude(pk=self.instance.pk)
            if duplicada.exists():
                self.add_error("cnpj", mensagem_cnpj_duplicado(Empresa))
        if cpf:
            duplicada = Empresa.objects.filter(cpf=cpf)
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
