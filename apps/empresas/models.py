from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Upper

from apps.empresas.fields import CNPJModelField, CPFModelField
from apps.empresas.validators import (
    normalizar_cnpj,
    normalizar_cpf,
    validar_cnpj,
    validar_cpf,
    validar_vigencia_de_regime,
)
from apps.tenancy.models import Escritorio

# Condição de canonização, compartilhada pela CheckConstraint de Empresa e
# de Estabelecimento: cnpj só contém caracteres A-Z0-9 (maiúsculo) e, por
# consequência, é igual à própria versão em maiúsculas. Ver R1 da
# reauditoria da etapa DL-011 — esta é a camada 1 (restrição de banco) que
# a DE-008 recomenda como a mais forte, porque vale para *save()*, *shell*,
# admin, `bulk_create`/`bulk_update`/`QuerySet.update()` e carga de fixture
# (`loaddata`), que não passam por `Model.save()` (ver o comentário de
# Empresa.save() abaixo). É *no-op* sobre valor já canônico: não rejeita
# nenhum dado que `normalizar_cnpj` já aceitaria.
_CNPJ_E_CANONICO = models.Q(cnpj=Upper("cnpj")) & ~models.Q(cnpj__regex=r"[^A-Z0-9]")

# DL-010, etapa BL-54 (pré-requisito de nível 1, dinheiro/isolamento):
# _CNPJ_E_CANONICO garante maiúsculas e alfabeto A-Z0-9, mas sozinha não
# garante o FORMATO do Anexo I da NT 2025.001 (14 caracteres, com os 2
# últimos sempre numéricos — ver `_FORMATO_CNPJ` em
# `apps.empresas.validators`). Por `bulk_create`/`bulk_update`/
# `QuerySet.update()`/`loaddata` — que não passam por `Model.save()` nem por
# `validar_cnpj` — valores como `""`, `"ABC"` ou `"AB123CDE0001AA"` (13
# caracteres alfanuméricos seguidos de LETRA no lugar do dígito verificador)
# eram canônicos (só A-Z0-9, já maiúsculo) e passavam pela constraint antiga
# sem serem CNPJ nenhum. `_CNPJ_TEM_FORMATO_VALIDO` fecha isso: mesma regex
# de formato usada por `validar_cnpj`, expressa como `Q` porque
# `CheckConstraint.condition` roda no banco, não em Python.
#
# ATENÇÃO — o que esta constraint NÃO faz: ela confere o FORMATO (tamanho e
# que os 2 últimos caracteres são dígitos), não o DÍGITO VERIFICADOR
# calculado pelo módulo 11. Aceita, por exemplo, "AB123CDE000199" mesmo que
# "99" não seja o DV correto para aquela base — isso é aceitável para uma
# restrição de banco (não replicamos módulo 11 em SQL). Quem confere o DV é
# `apps.empresas.validators.validar_cnpj`, chamado por `full_clean()`
# (formulário/admin) e pelo serializer — não pela constraint, e não por
# `bulk_create`/`QuerySet.update()`, que continuam fora do alcance do DV
# (mesma limitação documentada em `Empresa.save()` abaixo).
_CNPJ_TEM_FORMATO_VALIDO = models.Q(cnpj__regex=r"^[A-Z0-9]{12}[0-9]{2}$")

# DL-038 (R1/R2, DE-075): `cnpj` passa a ser BRANCO para empresa CPF — as
# duas condições acima (canonicidade e formato) só podem valer QUANDO o
# tipo de inscrição é CNPJ. `~models.Q(tipo_inscricao=TipoInscricao.CPF)`
# expressa "não é CPF" em vez de "é CNPJ" de propósito: um terceiro valor
# de `tipo_inscricao` que viesse a existir cairia no lado que EXIGE cnpj
# canônico (mais restritivo), não no lado que dispensa — o padrão seguro
# já usado neste projeto (ver comentário de "lado seguro" em
# apps.auditoria.signals).
#
# CPF tem sua própria condição simétrica (formato, não DV — mesma
# limitação documentada acima e em `Empresa.save()`): só dígitos, 11
# posições, exigido apenas quando o tipo É CPF.
_CPF_TEM_FORMATO_VALIDO = models.Q(cpf__regex=r"^[0-9]{11}$")


class TipoInscricao(models.TextChoices):
    """DL-038, R1: o tipo de inscrição da empresa no cadastro. Existentes
    migram como CNPJ (migração aditiva, sem alterar dado — DE-075)."""

    CNPJ = "CNPJ", "CNPJ"
    CPF = "CPF", "CPF"


class ModoEscrituracao(models.TextChoices):
    """DL-038, R4: como a empresa é escriturada. Existentes migram como
    CONTABILIDADE. HI-23 (hipótese, não confirmada pelo Fred): empresa CPF
    nova SUGERE livro-caixa — é comportamento de TELA (a decidir na etapa
    do `especialista-frontend`), não um padrão diferente aqui: o valor
    padrão do campo continua CONTABILIDADE para qualquer tipo de
    inscrição, para não haver dois comportamentos de "vazio" a explicar."""

    CONTABILIDADE = "contabilidade", "Contabilidade (partidas dobradas)"
    LIVRO_CAIXA = "livro_caixa", "Livro-caixa"


# Lista oficial de siglas de unidade federativa (não é uma regra fiscal:
# apenas os 26 estados e o Distrito Federal).
_UFS = [
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
]
UF_CHOICES = [(uf, uf) for uf in _UFS]


class Empresa(models.Model):
    """Empresa cliente de um escritório.

    Isolamento: toda consulta de negócio sobre Empresa deve filtrar pelo
    escritório ativo da requisição (request.escritorio), nunca listar
    empresas de outro escritório.
    """

    escritorio = models.ForeignKey(
        Escritorio, verbose_name="escritório", on_delete=models.PROTECT, related_name="empresas"
    )
    razao_social = models.CharField("razão social", max_length=200)
    nome_fantasia = models.CharField("nome fantasia", max_length=200, blank=True)
    # DL-038 (R1, DE-075): tipo de inscrição — CNPJ (pessoa jurídica) ou CPF
    # (pessoa física, RC-112/RC-114). Decide qual dos dois campos abaixo é
    # obrigatório; a consistência entre os três é imposta pela
    # CheckConstraint "empresa_inscricao_consistente_com_tipo" no Meta.
    tipo_inscricao = models.CharField(
        "tipo de inscrição",
        max_length=4,
        choices=TipoInscricao.choices,
        default=TipoInscricao.CNPJ,
    )
    # `unique=True` REMOVIDO na DL-038: a unicidade de CNPJ é CONDICIONAL
    # — vazio (empresa CPF) não pode contar como "duplicata" de outro
    # vazio. Django não expressa unicidade condicional com `unique=True`
    # de campo; a unicidade real está na UniqueConstraint "empresa_cnpj_
    # unico_por_escritorio" (Meta, abaixo), que substitui o índice
    # implícito `empresas_empresa_cnpj_key` que existia antes (ver
    # apps.empresas.services._CONSTRAINTS_INSCRICAO_UNICA e apps.core.
    # restricoes). DL-041 (RC-115/DE-077): a unicidade deixou de ser
    # GLOBAL e passou a ser POR ESCRITÓRIO — ver o comentário completo
    # junto da constraint, no Meta.
    #
    # `default=""` (permite gravar vazio para empresa CPF), mas SEM
    # `blank=True`: a obrigatoriedade em FORMULÁRIO (EmpresaForm,
    # `especialista-frontend`, e o `ModelForm` automático do
    # `EmpresaAdmin`) continua exatamente como era ANTES desta etapa —
    # nenhum dos dois formulários conhece `tipo_inscricao` ainda, então
    # "CNPJ obrigatório" é o comportamento CORRETO e de MENOR IMPACTO para
    # os dois (medido: `apps/empresas/tests/test_forms.py` e as rotas do
    # admin exigem isso hoje). `blank`/`required` do Django é regra de
    # FORMULÁRIO, não de banco — não afeta a API (o serializer declara
    # `required=False` explicitamente, sem olhar para `blank` do modelo) e
    # não afeta a CheckConstraint (que roda no banco, sobre o VALOR
    # gravado, nunca sobre este atributo Python). Uma empresa CPF só
    # nasce, hoje, pela API — a tela ganha isso na etapa do
    # `especialista-frontend`, quando o formulário souber pedir tipo de
    # inscrição, e aí sim `EmpresaForm` (fora do meu escopo) decide como
    # tornar `cnpj` condicionalmente obrigatório.
    cnpj = CNPJModelField("CNPJ", max_length=14, default="", validators=[validar_cnpj])
    # DL-038 (R2): CPF de 11 dígitos, sem máscara, com zero à esquerda
    # preservado (é `CharField`, nunca convertido para número). Unicidade
    # condicional POR ESCRITÓRIO (DL-041/RC-115), mesmo padrão do cnpj
    # acima — ver "empresa_cpf_unico_por_escritorio" no Meta. DV validado
    # por `validar_cpf` (`apps.empresas.validators` — fonte NÃO oficial,
    # declarada lá).
    cpf = CPFModelField("CPF", max_length=11, blank=True, default="", validators=[validar_cpf])
    # DL-038 (R4): como a empresa é escriturada. Ver ModoEscrituracao acima
    # para a política de valor padrão (sempre CONTABILIDADE, mesmo para
    # CPF — HI-23 é sugestão de TELA, não de modelo).
    modo_escrituracao = models.CharField(
        "modo de escrituração",
        max_length=20,
        choices=ModoEscrituracao.choices,
        default=ModoEscrituracao.CONTABILIDADE,
    )
    # DL-027 (Fatia A) — RC-93: identificação obrigatória do relatório
    # exige "razão social, CNPJ, período, NIRE e as demais informações".
    # Antes desta etapa NIRE não existia no cadastro (BL-340), e a
    # obrigação do RC-93 não era atendível com os dados disponíveis.
    # O campo é texto curto (até 14 dígitos — mesmo limite do CNPJ) e
    # opcional: o sistema emite o relatório com `(não informado)`
    # quando vazio (regra do vazio em `apps.documentos.identificacao`).
    # A canonização (remoção de máscara, validação de DV) NÃO é
    # declarada aqui porque depende de fonte oficial ainda não
    # levantada — fica para o `BL-340` continuar quando a fonte vier.
    nire = models.CharField(
        "NIRE",
        max_length=14,
        blank=True,
        default="",
        help_text=(
            "Número de Inscrição no Registro de Empresas. Opcional: "
            "empresa sem NIRE imprime o marcador `(não informado)` no "
            "cabeçalho do relatório (DL-027, RC-93)."
        ),
    )
    # DL-027 (Fatia A) — RC-95, NBC TG 26 (R5) item 51(e): "o nível
    # de arredondamento usado" é parte da identificação obrigatória
    # de DEMONSTRAÇÃO contábil. Sem este campo o sistema não imprime
    # o que a norma exige. Texto (não enum) porque a regra do DE-010
    # é explícita por cálculo, e o default é só fallback para a
    # impressão — o motor determinístico sobrescreve quando calcula.
    # O limite de 100 caracteres cabe "2 casas decimais (ABNT NBR
    # 5891)" e "4 casas para volume (TRUNCAR)" — variações razoáveis
    # sem permitir texto de baixa qualidade.
    nivel_de_arredondamento = models.CharField(
        "nível de arredondamento",
        max_length=100,
        blank=True,
        default="2 casas decimais (ABNT NBR 5891)",
        help_text=(
            "Texto que sai no cabeçalho do relatório de demonstração "
            "(NBC TG 26 item 51e). Default segue a política monetária "
            "ABNT NBR 5891 (DE-010)."
        ),
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["razao_social"]
        constraints = [
            # DL-038: agora CONDICIONAL a `tipo_inscricao != CPF` — ver o
            # comentário de `_CPF_TEM_FORMATO_VALIDO` acima. O NOME
            # continua "empresa_cnpj_canonico" (não renomeado): é o mesmo
            # invariante de sempre, só que dispensado para empresa CPF —
            # `apps.core.restricoes` e `apps.empresas.views` continuam
            # reconhecendo esta constraint pelo nome antigo, sem qualquer
            # mudança nos dois.
            models.CheckConstraint(
                condition=(
                    ~models.Q(tipo_inscricao=TipoInscricao.CPF)
                    & _CNPJ_E_CANONICO
                    & _CNPJ_TEM_FORMATO_VALIDO
                )
                | models.Q(tipo_inscricao=TipoInscricao.CPF),
                name="empresa_cnpj_canonico",
            ),
            # DL-038 (R2): formato do CPF (11 dígitos), só exigido quando
            # `tipo_inscricao` É CPF — o DV não é conferido aqui pelo mesmo
            # motivo do CNPJ (constraint de banco não recalcula módulo 11);
            # `apps.empresas.validators.validar_cpf` faz essa conferência
            # nos caminhos que chamam `full_clean()`/serializer.
            models.CheckConstraint(
                condition=(models.Q(tipo_inscricao=TipoInscricao.CPF) & _CPF_TEM_FORMATO_VALIDO)
                | ~models.Q(tipo_inscricao=TipoInscricao.CPF),
                name="empresa_cpf_formato_valido",
            ),
            # DL-038: a invariante de CONSISTÊNCIA entre os três campos —
            # exatamente um dos dois (cnpj XOR cpf) preenchido, e ele bate
            # com `tipo_inscricao`. Sem isto, nada impediria uma empresa
            # "CNPJ" com cnpj vazio E cpf preenchido (ou os dois vazios, ou
            # os dois preenchidos) — um estado que nenhuma tela ou API
            # pretende produzir, mas que só a restrição de banco fecha em
            # TODA porta (shell, admin, bulk_create — camada 1 da DE-008).
            models.CheckConstraint(
                condition=(
                    models.Q(tipo_inscricao=TipoInscricao.CNPJ)
                    & ~models.Q(cnpj="")
                    & models.Q(cpf="")
                )
                | (
                    models.Q(tipo_inscricao=TipoInscricao.CPF)
                    & models.Q(cnpj="")
                    & ~models.Q(cpf="")
                ),
                name="empresa_inscricao_consistente_com_tipo",
            ),
            # DL-041 (RC-115/DE-077): substitui o índice implícito
            # `empresas_empresa_cnpj_key` (unique=True de campo, removido
            # do `cnpj` acima) — unicidade só sobre valor NÃO vazio (duas
            # empresas CPF, `cnpj=""`, nunca colidem entre si por este
            # motivo) e agora POR ESCRITÓRIO, não mais global. ANTES desta
            # etapa (DL-038, achado R3/PE-21) a unicidade era global — o
            # Fred decidiu (PE-68/PE-21, RC-115) que isso vazava a carteira
            # de um escritório para outro (e, com CPF, dado pessoal —
            # LGPD): um escritório descobria, ao tentar cadastrar, que um
            # CNPJ/CPF já era cliente de OUTRO escritório. `fields` inclui
            # `escritorio`: a MESMA empresa (mesmo CNPJ) pode existir em
            # dois escritórios diferentes — o caso normal de cliente que
            # troca de contador (consequência aceita, DE-077).
            models.UniqueConstraint(
                fields=["escritorio", "cnpj"],
                condition=~models.Q(cnpj=""),
                name="empresa_cnpj_unico_por_escritorio",
            ),
            # DL-041: simétrica à de cima, para CPF.
            models.UniqueConstraint(
                fields=["escritorio", "cpf"],
                condition=~models.Q(cpf=""),
                name="empresa_cpf_unico_por_escritorio",
            ),
            # Achado B8 da auditoria rodada 1: `modo_escrituracao` não tinha
            # NENHUMA restrição de domínio no banco — `Empresa.objects.
            # create(..., modo_escrituracao="qualquer")` gravava, e
            # `apps.empresas.services.recusar_se_livro_caixa` passava a
            # tratar essa empresa como "contabilidade" (só recusa quando o
            # valor é EXATAMENTE "livro_caixa"), silenciosamente. Diferente
            # de `tipo_inscricao` — coberto INDIRETAMENTE por
            # "empresa_inscricao_consistente_com_tipo" acima, porque aquela
            # constraint só reconhece os dois valores do enum nas suas duas
            # condições — `modo_escrituracao` não tinha nenhuma constraint
            # que dependesse do seu valor para fechar o domínio.
            # `choices=` (ModoEscrituracao.choices, no campo) é só
            # validação de FORM/serializer — nunca alcança ORM direto,
            # bulk_create nem shell (camada 1 da DE-008, a única que
            # sobrevive a todos esses caminhos).
            models.CheckConstraint(
                condition=models.Q(
                    modo_escrituracao__in=[
                        ModoEscrituracao.CONTABILIDADE,
                        ModoEscrituracao.LIVRO_CAIXA,
                    ]
                ),
                name="empresa_modo_escrituracao_valido",
            ),
        ]

    def save(self, *args, **kwargs):
        # Canoniza o CNPJ (remove máscara, converte para maiúsculas) antes
        # de gravar. Cobre save() explícito, .objects.create(),
        # get_or_create() e update_or_create() — todos passam por este
        # método. NÃO cobre bulk_create(), bulk_update(),
        # QuerySet.update() nem a carga de fixture via loaddata
        # (serializers.deserialize + save_base): nenhum desses chama
        # Model.save() (R1 da reauditoria da etapa DL-011 — a versão
        # anterior deste comentário dizia "em todo caminho de ORM", o que é
        # falso, e um comentário errado no ponto único de canonização é
        # pior que nenhum comentário). Hoje nenhum desses métodos aparece em
        # código de produção (só em testes), mas a DL-010 vai importar
        # documentos em lote e é candidata natural a usar bulk_create por
        # desempenho — por isso a garantia real, que cobre esses caminhos
        # também, é a CheckConstraint "empresa_cnpj_canonico" acima (camada
        # 1 da DE-008, a mais forte: sobrevive a shell, ORM, admin e
        # corrida). Este save() continua existindo como conveniência: sem
        # ele, toda gravação normal precisaria confiar em o chamador ter
        # normalizado antes.
        #
        # A validação do dígito verificador continua em validar_cnpj,
        # acionada por full_clean()/serializer/form; aqui só canonizamos.
        #
        # Risco herdado, aceito conscientemente: normalizar_cnpj levanta
        # ValidationError para valor com caractere ou máscara inválidos.
        # Isso significa que um registro que já estivesse gravado com CNPJ
        # inválido se tornaria impossível de salvar de novo — mesmo só para
        # alterar outro campo, porque este save() sempre re-normaliza. Aqui
        # isso é aceitável: o campo cnpj tem validar_cnpj desde a DL-004,
        # então só uma chamada direta de ORM (fora de formulário/serializer)
        # produziria um registro assim, e nenhum dos dados de teste ou de
        # produção conhecidos está nessa situação.
        #
        # Isso NÃO vale para Escritorio (apps/tenancy/models.py), que não
        # tem validar_cnpj nenhum e cujo campo cnpj nunca foi canonizado
        # (BL-47, ainda não feito). A reauditoria da etapa DL-011 confirmou
        # que os CNPJs de Escritorio usados nos testes atuais — incluindo
        # "11111111000111", "22222222000122", "33333333000133",
        # "55566677000155" e "55566677000255" — têm dígito verificador
        # inválido pela regra oficial. Aplicar a mesma canonização (ou a
        # mesma CheckConstraint) em Escritorio sem um plano de dados
        # quebraria a suíte e, em produção, travaria a gravação de
        # escritórios já cadastrados. Não replicar este padrão em
        # Escritorio fora do BL-47.
        #
        # DL-038: canoniza SÓ quando o campo não está vazio — `normalizar_
        # cnpj("")`/`normalizar_cpf("")` levantam ValidationError (formato
        # inválido), e uma empresa CPF tem `cnpj == ""` de propósito (e
        # vice-versa). O `if` não verifica `tipo_inscricao`: normaliza
        # qualquer um dos dois campos que estiver preenchido, o que é mais
        # robusto (funciona mesmo se algum caminho legado só setar o campo
        # sem setar o tipo) e continua sendo *no-op* para o campo vazio.
        if self.cnpj:
            self.cnpj = normalizar_cnpj(self.cnpj)
        if self.cpf:
            self.cpf = normalizar_cpf(self.cpf)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome_fantasia or self.razao_social

    def validate_constraints(self, exclude=None):
        # DL-038 — achado desta etapa, medido por execução real (não
        # presumido, ver `apps/empresas/tests/test_views.py`): desde o
        # Django 4.1, `Model.validate_constraints()` faz uma checagem em
        # PYTHON de `Meta.constraints` (inclusive `UniqueConstraint`),
        # separada de `validate_unique()` (que só cobre `unique=True` de
        # campo). `BaseModelForm._post_clean()` chama os DOIS: passa
        # `validate_constraints=False` para `full_clean()`, mas depois
        # chama `self.validate_constraints()` (do FORM) SEPARADAMENTE, que
        # delega para `self.instance.validate_constraints(...)` — este
        # método aqui. Sobrescrever `full_clean()` NÃO intercepta esse
        # segundo caminho; só sobrescrever este método intercepta os DOIS.
        #
        # Antes desta etapa isso não importava: `cnpj` era `unique=True`,
        # então `validate_unique()` (que `ModelForm.is_valid()` também
        # chama) já cobria a duplicidade, com a mensagem amigável do
        # `UniqueValidator`. Ao trocar para `UniqueConstraint` condicional
        # ("empresa_cnpj_unico_por_escritorio"/"empresa_cpf_unico_por_
        # escritorio" — a unicidade condicional NÃO é expressável com
        # `unique=True` de campo),
        # `validate_constraints()` virou o único caminho que a detecta
        # dentro do ciclo de vida do `ModelForm`, e ele produz uma
        # mensagem GENÉRICA do próprio Django ("Restrição "X" foi
        # violada."), em vez do texto amigável de `apps.empresas.services.
        # mensagem_cnpj_duplicado`. Medido: o cliente via tela via essa
        # mensagem genérica para um CNPJ/CPF duplicado comum, pior
        # experiência para o caso mais frequente.
        #
        # No-op aqui restaura o desenho ORIGINAL da DE-008:
        # `full_clean()`/`Model.clean()` são conveniência de ModelForm/
        # admin, NUNCA a defesa principal. A defesa real continua em DUAS
        # camadas, intactas: (1) a `UniqueConstraint`/`CheckConstraint` no
        # BANCO (camada 1 da DE-008, sobrevive a qualquer ORM — este
        # método não toca nelas, só no PRÉ-AVISO em Python);
        # (2) `erro_de_cnpj_duplicado_como_400` traduzindo o
        # `IntegrityError` real em `CNPJDuplicado`, com a mensagem boa —
        # exatamente o caminho que `criar_empresa`/`EmpresaListCreateView`
        # já percorrem quando a gravação de fato viola a constraint.
        return

    def clean(self):
        # DL-023, critério 5 (BL-211/A3): `EmpresaAdmin` deixava mover uma
        # empresa inteira de escritório com um POST — medido: `302`,
        # levando junto plano de contas, escrituração e estabelecimentos,
        # sem nenhum `RegistroAuditoria`. A pendência P1 (transferir empresa
        # entre escritórios é operação real?) segue em aberto; enquanto não
        # houver resposta do Fred, o lado seguro e reversível é RECUSAR.
        #
        # Só dispara na TRANSIÇÃO desta gravação (o `escritorio_id` GRAVADO
        # no banco é diferente do que está sendo salvo agora) — mesmo
        # padrão do guard de `aceita_lancamento` em `Conta.clean()`: uma
        # empresa nova (`self.pk` ainda None) não tem transição nenhuma, e
        # fica livre no `add` (H1).
        #
        # "Escrituração" é checada pelas TRÊS relações reversas que a
        # etapa nomeia — plano de contas, lançamento e estabelecimento —
        # via `related_name`, sem importar `apps.contabilidade.models` aqui
        # (evitaria import circular: `apps.contabilidade.models` já importa
        # `Empresa` deste módulo). `self.contas`/`self.lancamentos` são
        # resolvidos pelo registro de apps do Django em tempo de chamada,
        # não em tempo de import.
        #
        # Limite conhecido, e não é novo neste projeto (mesmo risco já
        # aceito e documentado em `Conta.clean()`, DE-008): `full_clean()`
        # só é chamado por `ModelForm`/admin, nunca por `.save()` puro nem
        # por `QuerySet.update()` — esta guarda não impede ORM direto. Hoje
        # a ÚNICA porta que expõe `escritorio` como campo editável é o
        # `ModelForm` gerado pelo `EmpresaAdmin` (a API não inclui
        # `escritorio` em `EmpresaSerializer.Meta.fields`), e o admin
        # também trava esse campo por `readonly_fields` no `change` — ver
        # `EmpresaAdmin.get_readonly_fields`. As duas camadas continuam
        # coexistindo de propósito (defesa em profundidade, mesmo padrão do
        # resto do projeto): esta é a que protegeria qualquer ModelForm
        # futuro que voltasse a expor o campo sem repetir a decisão.
        #
        # Critério 11 da DL-023 (trilha), AUSÊNCIA DECLARADA: a recusa
        # levantada aqui NÃO grava `RegistroAuditoria` — mesmo motivo do
        # guard equivalente em `Conta.clean()` (nada foi alterado, e
        # nenhum `admin.py` deste projeto chama `registrar()` hoje;
        # BL-244, pacote 3, endereça trilha genérica do admin).
        if self.pk:
            escritorio_gravado = (
                Empresa.objects.filter(pk=self.pk).values_list("escritorio_id", flat=True).first()
            )
            if escritorio_gravado is not None and escritorio_gravado != self.escritorio_id:
                tem_plano_de_contas = self.contas.exists()
                tem_lancamentos = self.lancamentos.exists()
                tem_estabelecimentos = self.estabelecimentos.exists()
                if tem_plano_de_contas or tem_lancamentos or tem_estabelecimentos:
                    raise ValidationError(
                        "Não é possível mudar o escritório desta empresa: ela já tem "
                        "escrituração gravada (plano de contas, lançamento contábil "
                        "ou estabelecimento). Transferir empresa entre escritórios "
                        "não é suportado pelo cadastro comum — registre a solicitação "
                        "com o responsável técnico do sistema, se este for um caso "
                        "real do escritório."
                    )

            # DL-038, R6: mesma TRANSIÇÃO acima, para `modo_escrituracao`.
            # Import LOCAL (dentro do método, não no topo do módulo): evita
            # ciclo de import — `apps.empresas.services` já importa `Empresa`
            # deste módulo (mesmo motivo do comentário sobre "Escrituração"
            # logo acima, para plano de contas/lançamento/estabelecimento).
            # A REGRA (condição + mensagem) mora só em `apps.empresas.
            # services.recusar_transicao_para_livro_caixa_com_movimento` —
            # aqui e em `EmpresaSerializer.validate` (o caminho que a API
            # de fato usa) só CHAMAM essa função, nunca reimplementam a
            # comparação. Mesmo limite de `full_clean()` documentado acima
            # (não cobre ORM direto nem `QuerySet.update()`) — a defesa que
            # cobre o caminho real de escrita (API) é a do serializer.
            from apps.empresas.services import (
                recusar_transicao_para_cpf_com_estabelecimento,
                recusar_transicao_para_livro_caixa_com_movimento,
            )

            modo_gravado = (
                Empresa.objects.filter(pk=self.pk)
                .values_list("modo_escrituracao", flat=True)
                .first()
            )
            if modo_gravado is not None and modo_gravado != self.modo_escrituracao:
                # Levanta `TransicaoParaLivroCaixaInvalida`, subclasse de
                # `ValidationError` — propaga direto, sem tradução: é
                # exatamente o contrato que `full_clean()` espera.
                recusar_transicao_para_livro_caixa_com_movimento(
                    self, modo_anterior=modo_gravado, modo_novo=self.modo_escrituracao
                )

            # DL-038, R7 (achado B2 da auditoria): mesma TRANSIÇÃO acima,
            # agora para `tipo_inscricao` — trocar para CPF com
            # estabelecimento gravado deixaria o cadastro inconsistente
            # (matriz/filial é conceito de pessoa jurídica). A REGRA mora
            # só em `apps.empresas.services.recusar_transicao_para_cpf_
            # com_estabelecimento`.
            tipo_gravado = (
                Empresa.objects.filter(pk=self.pk).values_list("tipo_inscricao", flat=True).first()
            )
            if tipo_gravado is not None and tipo_gravado != self.tipo_inscricao:
                recusar_transicao_para_cpf_com_estabelecimento(
                    self, tipo_anterior=tipo_gravado, tipo_novo=self.tipo_inscricao
                )


class RegimeTributario(models.TextChoices):
    SIMPLES_NACIONAL = "simples_nacional", "Simples Nacional"
    LUCRO_PRESUMIDO = "lucro_presumido", "Lucro Presumido"
    LUCRO_REAL = "lucro_real", "Lucro Real"


class HistoricoRegimeTributario(models.Model):
    """Regime tributário de uma empresa por período de vigência.

    Nunca editar um registro já encerrado para "corrigir" o regime: criar
    um novo período. `vigencia_fim` nulo indica o regime vigente. Preservar
    esse histórico é obrigatório para reproduzir apurações fiscais antigas
    (AGENTS.md, seção 10).
    """

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="historico_regime_tributario"
    )
    regime = models.CharField("regime tributário", max_length=20, choices=RegimeTributario.choices)
    # RC-85 (teto em hoje, confirmado) e HI-07 (piso em 2000, HIPÓTESE) como
    # validador de CAMPO, e não só em `registrar_regime_tributario`: o
    # `HistoricoRegimeTributarioInline` do admin (apps/empresas/admin.py)
    # grava por `ModelForm`, chama `full_clean()` e NUNCA passa pelo serviço
    # — é a segunda, e única outra, superfície de escrita deste campo hoje
    # (item 2 da DE-034). Ver `apps.empresas.validators`, fonte única da
    # faixa e da mensagem.
    vigencia_inicio = models.DateField("vigência (início)", validators=[validar_vigencia_de_regime])
    vigencia_fim = models.DateField("vigência (fim)", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "histórico de regime tributário"
        verbose_name_plural = "históricos de regime tributário"
        # BL-251 (achado P7, auditoria DL-023 rodada 1): o desempate
        # `(-vigencia_inicio, -id)` existia só DENTRO de
        # `excluir_ultimo_regime_tributario` (apps/empresas/services.py),
        # que sobrescreve este `Meta.ordering` com o próprio `order_by()`.
        # A rota de LISTAGEM (`HistoricoRegimeTributarioListCreateView.
        # get_queryset`, apps/empresas/views.py) usa a ordenação do `Meta`
        # tal como está — com dois períodos de mesmo `vigencia_inicio`
        # (dado herdado/importado, nunca produzido por
        # `registrar_regime_tributario`), a ordem devolvida ao CLIENTE era
        # indefinida no PostgreSQL (sem `-id`, o banco pode devolver
        # qualquer uma das duas primeiro, e pode mudar entre chamadas). O
        # requisito 5 da etapa ("a escolha do 'último' é determinística")
        # cobria só o caminho medido (a exclusão); agora cobre TODO
        # caminho que lê este `Meta.ordering`.
        ordering = ["-vigencia_inicio", "-id"]
        constraints = [
            # DL-023, critério 1 (a defesa que vale em TODA porta, e por
            # isso vem primeiro na ordem obrigatória de execução da etapa):
            # BL-211/A2 mediu, pelo admin, dois períodos ABERTOS ao mesmo
            # tempo para a mesma empresa (`vigencia_fim IS NULL` nas duas
            # linhas) — o "último regime", justamente o que o RC-86/DE-039
            # autoriza apagar, deixava de ser único. `registrar_regime_
            # tributario` já serializa por `select_for_update()`, mas isso
            # só protege quem passa por ele; o admin (antes desta etapa) e
            # qualquer ORM direto não passavam. Esta restrição vale para
            # TODAS as portas, inclusive shell e importação futura — é a
            # camada 1 da DE-008. A `condition` restringe a unicidade às
            # linhas com `vigencia_fim` nulo, para que várias linhas
            # FECHADAS (histórico) continuem coexistindo sem violar nada;
            # só o período ABERTO precisa ser único por empresa.
            #
            # Efeito colateral desejado: como nenhuma outra superfície de
            # escrita deste campo passa por ModelForm hoje (o inline saiu do
            # admin — ver apps/empresas/admin.py), a única forma de violar
            # esta constraint por cliente é concorrência dentro do próprio
            # `registrar_regime_tributario`, e `apps.empresas.services`
            # traduz o `IntegrityError` correspondente para `ValueError`
            # (400), no mesmo molde de `erro_de_cnpj_duplicado_como_400`.
            models.UniqueConstraint(
                fields=["empresa"],
                condition=models.Q(vigencia_fim__isnull=True),
                name="um_periodo_de_regime_aberto_por_empresa",
            ),
        ]

    def __str__(self):
        return f"{self.empresa} — {self.get_regime_display()} desde {self.vigencia_inicio}"


class TipoEstabelecimento(models.TextChoices):
    MATRIZ = "matriz", "Matriz"
    FILIAL = "filial", "Filial"


class Estabelecimento(models.Model):
    """Unidade (matriz ou filial) de uma empresa, com CNPJ e endereço próprios."""

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="estabelecimentos")
    # DL-041 (RC-115/DE-077): DESNORMALIZADO a partir de `empresa.
    # escritorio` — nunca gravável por formulário/API/admin (`editable=
    # False`, excluído de `Meta.fields = "__all__"` e de qualquer
    # ModelForm/serializer automaticamente), sempre DERIVADO em `save()`,
    # abaixo. Existe para a unicidade de CNPJ do estabelecimento poder ser
    # POR ESCRITÓRIO (critério 2 do plano DL-041) sem uma sub-consulta:
    # `Estabelecimento` não tinha coluna de escritório nenhuma antes desta
    # etapa, e a alternativa (JOIN com `empresas_empresa` dentro da
    # `UniqueConstraint`) não é uma operação que o PostgreSQL/Django
    # oferece — `UniqueConstraint` só enxerga colunas da PRÓPRIA tabela.
    # Escolhida em vez de gatilho VALIDADOR (como o de B2/DL-039) porque
    # aqui não há duas pontas de uma invariante bidirecional para travar
    # contra corrida — a empresa NÃO MUDA de escritório (DL-023, guarda em
    # `Empresa.clean()`), então a coluna, uma vez preenchida certo, nunca
    # fica desatualizada por uma mudança legítima. O risco que sobra é só
    # "alguém grava o valor errado direto" — coberto por DUAS camadas:
    # `save()` (abaixo, Python, os dois bancos) e, só em PostgreSQL, um
    # gatilho que SEMPRE recalcula a partir de `empresa_id` antes de
    # gravar (migração 0012) — cobre `bulk_create`/`QuerySet.update()`/SQL
    # direto, que `save()` não alcança. Em SQLite (desenvolvimento,
    # DE-014) só a camada Python existe — limite ACEITO e declarado na
    # migração, mesmo padrão do gatilho de B2 (DL-039).
    escritorio = models.ForeignKey(
        Escritorio, verbose_name="escritório", on_delete=models.PROTECT, editable=False
    )
    tipo = models.CharField("tipo", max_length=10, choices=TipoEstabelecimento.choices)
    nome = models.CharField("nome/apelido", max_length=200)
    # `unique=True` REMOVIDO nesta etapa (DL-041): a unicidade deixou de
    # ser GLOBAL — ver a `UniqueConstraint` "estabelecimento_cnpj_unico_
    # por_escritorio" no Meta, abaixo, e o comentário do campo
    # `escritorio` acima sobre por que existe uma coluna nova para isso.
    cnpj = CNPJModelField("CNPJ", max_length=14, validators=[validar_cnpj])
    logradouro = models.CharField("logradouro", max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField("complemento", max_length=100, blank=True)
    bairro = models.CharField("bairro", max_length=100, blank=True)
    municipio = models.CharField("município", max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    cep = models.CharField("CEP", max_length=8, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "estabelecimento"
        verbose_name_plural = "estabelecimentos"
        ordering = ["empresa", "tipo"]
        constraints = [
            # Cada empresa tem no máximo uma matriz; filiais não têm limite.
            models.UniqueConstraint(
                fields=["empresa"],
                condition=models.Q(tipo=TipoEstabelecimento.MATRIZ),
                name="uma_matriz_por_empresa",
            ),
            # Mesma regra e mesmo motivo da CheckConstraint de Empresa (ver
            # comentário em Empresa.save()/Empresa.Meta): cnpj aqui também é
            # unique=True, e esta constraint é a camada que fecha os
            # caminhos de gravação em massa que Estabelecimento.save() não
            # alcança (R1 da reauditoria da etapa DL-011).
            models.CheckConstraint(
                condition=_CNPJ_E_CANONICO & _CNPJ_TEM_FORMATO_VALIDO,
                name="estabelecimento_cnpj_canonico",
            ),
            # DL-041 (RC-115/DE-077, critério 2 do plano): substitui o
            # `unique=True` global removido de `cnpj` acima. `escritorio`
            # é a coluna desnormalizada documentada no campo, no início da
            # classe — em PostgreSQL, um gatilho (migração 0012) garante
            # que ela SEMPRE reflete `empresa.escritorio`, mesmo por
            # caminhos que não chamam `save()`.
            models.UniqueConstraint(
                fields=["escritorio", "cnpj"],
                name="estabelecimento_cnpj_unico_por_escritorio",
            ),
        ]

    def save(self, *args, **kwargs):
        # Mesmo motivo e mesma regra de Empresa.save(): canoniza antes de
        # gravar, cobrindo save()/create()/get_or_create()/
        # update_or_create() — não bulk_create(), bulk_update(),
        # QuerySet.update() nem loaddata, que não passam por save() (ver o
        # comentário completo em Empresa.save()). A CheckConstraint
        # "estabelecimento_cnpj_canonico" acima é quem garante isso também
        # nesses caminhos.
        self.cnpj = normalizar_cnpj(self.cnpj)
        # DL-041: `escritorio` é SEMPRE derivado de `empresa.escritorio`
        # aqui — nunca aceito de fora (o campo é `editable=False`, ver o
        # comentário completo no início da classe). Consulta direta pelo
        # `pk` (não `self.empresa`, que levantaria `DoesNotExist` cru para
        # um `empresa_id` inválido — mesmo cuidado do resto do arquivo,
        # ver `Empresa.clean()`/BL-264): um `empresa_id` inválido aqui
        # grava `escritorio_id=None`, e é a FK (`NOT NULL` + restrição de
        # chave estrangeira) quem recusa a gravação com `IntegrityError`
        # — nunca um `DoesNotExist` não tratado.
        if self.empresa_id is not None:
            self.escritorio_id = (
                Empresa.objects.filter(pk=self.empresa_id)
                .values_list("escritorio_id", flat=True)
                .first()
            )
        super().save(*args, **kwargs)

    def clean(self):
        # DL-038, R7 (achado B2 da auditoria rodada 1): estabelecimento
        # (matriz/filial) é conceito de pessoa JURÍDICA — não existe para
        # empresa CPF. A REGRA mora só em `apps.empresas.services.
        # recusar_estabelecimento_para_empresa_cpf`; este `clean()` é a
        # defesa de ModelForm/admin (DE-008) — o caminho real de escrita
        # (API) tem a mesma checagem em `EstabelecimentoListCreateView.
        # perform_create` (apps/empresas/views.py). Mesmo limite já
        # documentado no restante do arquivo: não cobre ORM direto
        # (`objects.create()`) nem `bulk_create()`/`QuerySet.update()`.
        from apps.empresas.services import recusar_estabelecimento_para_empresa_cpf

        if self.empresa_id is not None:
            recusar_estabelecimento_para_empresa_cpf(self.empresa)

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()}) — {self.empresa}"
