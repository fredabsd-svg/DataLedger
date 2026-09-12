from django.db import models
from django.db.models.functions import Upper

from apps.empresas.fields import CNPJModelField
from apps.empresas.validators import normalizar_cnpj, validar_cnpj
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
    vigencia_inicio = models.DateField("vigência (início)")
    vigencia_fim = models.DateField("vigência (fim)", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "histórico de regime tributário"
        verbose_name_plural = "históricos de regime tributário"
        ordering = ["-vigencia_inicio"]

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
