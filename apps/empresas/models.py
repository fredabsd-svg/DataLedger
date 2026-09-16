from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Upper

from apps.empresas.fields import CNPJModelField
from apps.empresas.validators import (
    normalizar_cnpj,
    validar_cnpj,
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
    cnpj = CNPJModelField("CNPJ", max_length=14, unique=True, validators=[validar_cnpj])
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["razao_social"]
        constraints = [
            models.CheckConstraint(
                condition=_CNPJ_E_CANONICO,
                name="empresa_cnpj_canonico",
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
        self.cnpj = normalizar_cnpj(self.cnpj)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome_fantasia or self.razao_social

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
    tipo = models.CharField("tipo", max_length=10, choices=TipoEstabelecimento.choices)
    nome = models.CharField("nome/apelido", max_length=200)
    cnpj = CNPJModelField("CNPJ", max_length=14, unique=True, validators=[validar_cnpj])
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
                condition=_CNPJ_E_CANONICO,
                name="estabelecimento_cnpj_canonico",
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
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()}) — {self.empresa}"
