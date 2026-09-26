from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.empresas.fields import CNPJModelField, CPFModelField
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.empresas.validators import validar_cnpj, validar_cpf
from apps.livro_caixa.validators import (
    CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO,
    mensagem_de_codigo_carne_leao_invalido,
    validar_data_de_lancamento_caixa_do_modelo,
)


class LancamentoCaixaImutavelError(Exception):
    """Levantada por `LancamentoCaixa.save()`/`.delete()` em cima de um
    registro já persistido — mesmo padrão de `LancamentoImutavelError`
    (apps.contabilidade.models): um lançamento de caixa efetivado nunca é
    editado nem apagado; a correção é sempre um ESTORNO (novo lançamento
    reverso), preservando a trilha completa (AGENTS.md, seção 10)."""


class NaturezaCaixa(models.TextChoices):
    """DL-046 (fatia 1): toda conta do livro-caixa é de RECEITA ou de
    DESPESA — não há conta "patrimonial" no livro-caixa (regime de caixa,
    sem balanço). A dedutibilidade da despesa e o tipo do rendimento
    decorrem do `codigo_carne_leao` associado (HI-30), nunca desta
    natureza isolada."""

    RECEITA = "receita", "Receita"
    DESPESA = "despesa", "Despesa"


class OrigemRecebimento(models.TextChoices):
    """PF/PJ/EX — mesmo vocabulário do campo "Recebido de" dos modelos de
    arquivo de rendimentos do Carnê-Leão Web (Receita Federal, 2025; ver
    `apps.livro_caixa.validators`). Só se aplica a lançamento de RECEITA —
    despesa não tem "recebido de"."""

    PF = "PF", "Pessoa física"
    PJ = "PJ", "Pessoa jurídica"
    EX = "EX", "Exterior"


class ContaLivroCaixa(models.Model):
    """Conta do plano de contas do livro-caixa de UMA empresa (cliente
    pessoa física em modo livro-caixa — DL-038/RC-114).

    Cada conta carrega o código do Carnê-Leão Web (`codigo_carne_leao`)
    que corresponde a ela — rendimento (`R01.xxx.xxx`, só para conta de
    RECEITA) ou pagamento (`P10`/`P11`/`P20` + dígitos, só para conta de
    DESPESA). A dedutibilidade decorre desse código (HI-30: `P10`
    dedutível, `P11` não dedutível, `P20` — imposto/pensão/previdência,
    sempre um código FIXO da Receita, nunca "dedutível" no sentido do
    art. 68) — não existe um segundo campo "dedutível" nesta etapa, de
    propósito (evita uma classificação paralela que poderia divergir do
    código associado).
    """

    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="contas_livro_caixa"
    )
    codigo = models.CharField("código", max_length=20)
    nome = models.CharField("nome", max_length=200)
    natureza = models.CharField("natureza", max_length=10, choices=NaturezaCaixa.choices)
    codigo_carne_leao = models.CharField(
        "código do Carnê-Leão Web",
        max_length=30,
        help_text=(
            "Rendimento (R01.xxx.xxx) para conta de receita; pagamento "
            "(P10/P11/P20 + dígitos) para conta de despesa (HI-30)."
        ),
    )
    ativa = models.BooleanField("ativa", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "conta do livro-caixa"
        verbose_name_plural = "contas do livro-caixa"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "codigo"], name="conta_livro_caixa_codigo_unico_por_empresa"
            ),
            # Domínio de `natureza` fechado no BANCO — mesmo motivo do
            # achado B8 (DL-038) que criou "empresa_modo_escrituracao_
            # valido": `choices=` no campo só vale para form/serializer,
            # nunca para ORM direto/bulk_create/QuerySet.update().
            models.CheckConstraint(
                condition=models.Q(natureza__in=[NaturezaCaixa.RECEITA, NaturezaCaixa.DESPESA]),
                name="conta_livro_caixa_natureza_valida",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"

    def _tem_lancamento_gravado(self):
        return self.lancamentos.exists()

    def clean(self):
        # DL-046, critério 1: só para empresa em modo LIVRO_CAIXA — o
        # espelho de `recusar_se_livro_caixa` (contabilidade). A REGRA
        # mora só em `apps.empresas.services.recusar_se_nao_livro_caixa`;
        # aqui só se traduz para `ValidationError`, contrato de
        # `full_clean()`.
        if self.empresa_id:
            try:
                recusar_se_nao_livro_caixa(self.empresa)
            except EmpresaNaoEmModoLivroCaixa as exc:
                raise ValidationError(exc.mensagem) from exc

        # Coerência natureza <-> formato do código do Carnê-Leão Web
        # (HI-30). Não é um validador de CAMPO isolado (`validators=
        # [...]` no `codigo_carne_leao`) porque depende de `self.natureza`,
        # outro campo do MESMO modelo — mesmo padrão de `Conta.clean()`
        # (contabilidade) para `classificacao_dre` × `tipo`.
        if self.natureza and self.codigo_carne_leao:
            mensagem = mensagem_de_codigo_carne_leao_invalido(
                self.codigo_carne_leao, natureza=self.natureza
            )
            if mensagem is not None:
                raise ValidationError({"codigo_carne_leao": mensagem})

        # Guarda de TRANSIÇÃO (mesmo molde do BL-83/DL-023 e da DL-033/
        # DL-045): mudar a NATUREZA de uma conta que já tem lançamento
        # gravado inverteria o sentido (receita <-> despesa) do histórico
        # inteiro sem nenhum lançamento novo — o mesmo dano que trocar a
        # natureza de `Conta` (contabilidade) já protege contra. A
        # PRIMEIRA gravação (`self.pk` ainda `None`) é sempre livre.
        if self.pk:
            natureza_gravada = (
                ContaLivroCaixa.objects.filter(pk=self.pk)
                .values_list("natureza", flat=True)
                .first()
            )
            if natureza_gravada is not None and natureza_gravada != self.natureza:
                if self._tem_lancamento_gravado():
                    raise ValidationError(
                        "Não é possível mudar a natureza desta conta do livro-caixa: "
                        "ela já tem lançamento gravado — a troca inverteria o sentido "
                        "(receita/despesa) do histórico. Estorne o movimento antes de "
                        "reclassificar, ou cadastre uma conta nova."
                    )


class LancamentoCaixa(models.Model):
    """Lançamento de caixa (entrada ou saída) do livro-caixa — regime de
    CAIXA (RC-113): um valor só, contra uma `ContaLivroCaixa`, nunca
    partidas dobradas (isso é a contabilidade, `apps.contabilidade`).

    Nunca editar nem excluir um lançamento efetivado: uma correção é feita
    por ESTORNO (um novo lançamento reverso, referenciando o original em
    `estorno_de`), preservando a trilha completa (AGENTS.md, seção 10) —
    mesmo padrão de `LancamentoContabil`. Aplicado em `save()`/`delete()`,
    não só por convenção.
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="lancamentos_caixa")
    conta = models.ForeignKey(ContaLivroCaixa, on_delete=models.PROTECT, related_name="lancamentos")
    data = models.DateField("data", validators=[validar_data_de_lancamento_caixa_do_modelo])
    valor = models.DecimalField(
        "valor",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    historico = models.CharField("histórico", max_length=300)
    documento_origem = models.CharField(
        "documento de origem", max_length=100, blank=True, default=""
    )
    # Só para RECEITA (modelos de arquivo de rendimentos) — vazio/nulo para
    # DESPESA, checado em `clean()`.
    recebido_de = models.CharField(
        "recebido de",
        max_length=2,
        choices=OrigemRecebimento.choices,
        null=True,
        blank=True,
    )
    # CPF do titular do pagamento e do beneficiário do serviço — exigidos
    # quando o CÓDIGO de rendimento de trabalho não assalariado exigir
    # (instrução da tarefa; ver `mensagem_de_cpf_obrigatorio_ausente` em
    # `apps.livro_caixa.services`, chamada por `clean()` abaixo). CNPJ do
    # pagador é sempre OPCIONAL (instrução da tarefa), mesmo para
    # recebido_de=PJ.
    cpf_titular_pagamento = CPFModelField(
        "CPF do titular do pagamento",
        max_length=11,
        blank=True,
        default="",
        validators=[validar_cpf],
    )
    cpf_beneficiario_servico = CPFModelField(
        "CPF do beneficiário do serviço",
        max_length=11,
        blank=True,
        default="",
        validators=[validar_cpf],
    )
    cnpj_pagador = CNPJModelField(
        "CNPJ do pagador", max_length=14, blank=True, default="", validators=[validar_cnpj]
    )
    # Idempotência (BL-41, mesmo padrão de `LancamentoContabil`).
    chave_idempotencia = models.CharField(
        "chave de idempotência",
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "Cabeçalho Idempotency-Key enviado pelo cliente. Repetir o POST "
            "com a mesma chave, na mesma empresa, devolve o lançamento já "
            "criado em vez de duplicá-lo."
        ),
    )
    chave_idempotencia_fingerprint = models.CharField(
        "impressão digital da chave de idempotência",
        max_length=64,
        null=True,
        blank=True,
    )
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
        verbose_name = "lançamento de caixa"
        verbose_name_plural = "lançamentos de caixa"
        ordering = ["-data", "-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor__gt=0), name="lancamento_caixa_valor_positivo"
            ),
            models.UniqueConstraint(
                fields=["estorno_de"],
                condition=models.Q(estorno_de__isnull=False),
                name="lancamento_caixa_estorno_de_unico",
            ),
            models.UniqueConstraint(
                fields=["empresa", "chave_idempotencia"],
                condition=models.Q(chave_idempotencia__isnull=False),
                name="lancamento_caixa_chave_idempotencia_unica_por_empresa",
            ),
        ]

    def __str__(self):
        return f"Lançamento de caixa {self.pk} — {self.data} — {self.historico}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise LancamentoCaixaImutavelError(
                "Lançamentos de caixa não podem ser alterados; registre um estorno."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LancamentoCaixaImutavelError(
            "Lançamentos de caixa não podem ser excluídos; registre um estorno."
        )

    def clean(self):
        if self.empresa_id:
            try:
                recusar_se_nao_livro_caixa(self.empresa)
            except EmpresaNaoEmModoLivroCaixa as exc:
                raise ValidationError({"empresa": exc.mensagem}) from exc

        if self.conta_id and self.empresa_id and self.conta.empresa_id != self.empresa_id:
            raise ValidationError(
                {"conta": "A conta do livro-caixa deve pertencer à mesma empresa do lançamento."}
            )

        if not self.conta_id:
            return

        if self.conta.natureza == NaturezaCaixa.DESPESA:
            if (
                self.recebido_de
                or self.cpf_titular_pagamento
                or self.cpf_beneficiario_servico
                or self.cnpj_pagador
            ):
                raise ValidationError(
                    "Lançamento de DESPESA não tem 'recebido de', CPF do titular/"
                    "beneficiário nem CNPJ do pagador — esses campos são só de "
                    "lançamento de RECEITA."
                )
            return

        # RECEITA a partir daqui.
        if not self.recebido_de:
            raise ValidationError(
                {"recebido_de": "Lançamento de receita exige 'recebido de' (PF, PJ ou EX)."}
            )

        # Instrução da tarefa: "CPF titular do pagamento e CPF beneficiário
        # quando o código de rendimento de trabalho não assalariado
        # exigir" — inferência minha (reportada, não decidida): restrinjo
        # literalmente ao código de trabalho não assalariado (R01.001.001),
        # o único citado nos modelos de arquivo de referência com os DOIS
        # campos de CPF preenchidos para "recebido de PF". Para as demais
        # linhas de receita (aluguel, outros rendimentos, notarial), os
        # modelos de referência não exigem os dois.
        exige_cpf_do_trabalho_nao_assalariado = (
            self.conta.codigo_carne_leao == CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO
            and self.recebido_de == OrigemRecebimento.PF
        )
        if exige_cpf_do_trabalho_nao_assalariado:
            erros = {}
            if not self.cpf_titular_pagamento:
                erros["cpf_titular_pagamento"] = (
                    "Rendimento do trabalho não assalariado recebido de pessoa "
                    "física exige o CPF do titular do pagamento."
                )
            if not self.cpf_beneficiario_servico:
                erros["cpf_beneficiario_servico"] = (
                    "Rendimento do trabalho não assalariado recebido de pessoa "
                    "física exige o CPF do beneficiário do serviço."
                )
            if erros:
                raise ValidationError(erros)
