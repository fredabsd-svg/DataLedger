from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.empresas.models import Empresa


class LancamentoImutavelError(Exception):
    """Levantado ao tentar alterar ou excluir um lançamento já efetivado."""


class TipoConta(models.TextChoices):
    ATIVO = "ativo", "Ativo"
    PASSIVO = "passivo", "Passivo"
    PATRIMONIO_LIQUIDO = "patrimonio_liquido", "Patrimônio Líquido"
    RECEITA = "receita", "Receita"
    DESPESA = "despesa", "Despesa"


class NaturezaConta(models.TextChoices):
    DEVEDORA = "devedora", "Devedora"
    CREDORA = "credora", "Credora"


class Conta(models.Model):
    """Conta do plano de contas de uma empresa, organizada em hierarquia.

    Regra geral de natureza (não imposta pelo modelo, para permitir contas
    retificadoras deliberadas): ativo e despesa costumam ser devedores;
    passivo, patrimônio líquido e receita costumam ser credores.
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="contas")
    conta_pai = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subcontas"
    )
    codigo = models.CharField("código", max_length=20)
    nome = models.CharField("nome", max_length=200)
    tipo = models.CharField("tipo", max_length=20, choices=TipoConta.choices)
    natureza = models.CharField("natureza", max_length=10, choices=NaturezaConta.choices)
    aceita_lancamento = models.BooleanField(
        "aceita lançamento",
        default=True,
        help_text="Contas sintéticas (agrupadoras) não devem receber lançamento direto.",
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "conta"
        verbose_name_plural = "contas"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="codigo_unico_por_empresa"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"

    def clean(self):
        if self.conta_pai_id and self.conta_pai.empresa_id != self.empresa_id:
            raise ValidationError("A conta pai deve pertencer à mesma empresa.")


class LancamentoContabil(models.Model):
    """Lançamento contábil por partidas dobradas.

    Nunca editar nem excluir um lançamento efetivado: uma correção é feita
    por estorno (um novo lançamento reverso, referenciando o original em
    `estorno_de`), preservando a trilha de auditoria contábil completa
    (AGENTS.md, seção 10). Isso é aplicado em `save`/`delete`, não só por
    convenção: qualquer tentativa de alterar um lançamento já persistido
    levanta LancamentoImutavelError.
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="lancamentos")
    data = models.DateField("data")
    historico = models.CharField("histórico", max_length=300)
    estorno_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="estornos"
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "lançamento contábil"
        verbose_name_plural = "lançamentos contábeis"
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"Lançamento {self.pk} — {self.data} — {self.historico}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise LancamentoImutavelError(
                "Lançamentos contábeis não podem ser alterados; registre um estorno."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LancamentoImutavelError(
            "Lançamentos contábeis não podem ser excluídos; registre um estorno."
        )


class TipoPartida(models.TextChoices):
    DEBITO = "debito", "Débito"
    CREDITO = "credito", "Crédito"


class ItemLancamento(models.Model):
    """Uma partida (débito ou crédito) de um lançamento contábil."""

    lancamento = models.ForeignKey(
        LancamentoContabil, on_delete=models.CASCADE, related_name="itens"
    )
    conta = models.ForeignKey(Conta, on_delete=models.PROTECT, related_name="itens_lancamento")
    tipo = models.CharField("tipo", max_length=10, choices=TipoPartida.choices)
    valor = models.DecimalField(
        "valor", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        verbose_name = "item de lançamento"
        verbose_name_plural = "itens de lançamento"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.valor} — {self.conta}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise LancamentoImutavelError(
                "Itens de lançamento não podem ser alterados; registre um estorno."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LancamentoImutavelError(
            "Itens de lançamento não podem ser excluídos; registre um estorno."
        )
