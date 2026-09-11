from django.db import models

from apps.empresas.validators import validar_cnpj
from apps.tenancy.models import Escritorio

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
    cnpj = models.CharField("CNPJ", max_length=14, unique=True, validators=[validar_cnpj])
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["razao_social"]

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
    cnpj = models.CharField("CNPJ", max_length=14, unique=True, validators=[validar_cnpj])
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
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()}) — {self.empresa}"
