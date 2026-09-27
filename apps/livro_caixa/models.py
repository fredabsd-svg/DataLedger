from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, ProhibitNullCharactersValidator
from django.db import models

from apps.empresas.fields import CNPJModelField, CPFModelField
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.empresas.validators import validar_cnpj, validar_codigo_ocupacao, validar_cpf
from apps.livro_caixa.validators import (
    erro_de_codigo_ocupacao_da_conta,
    erro_de_valor_irrf,
    erros_de_cpf_cnpj_do_rendimento,
    erros_de_previdencia_oficial,
    mensagem_de_codigo_carne_leao_invalido,
    modelo_do_codigo_de_rendimento,
    validar_data_de_lancamento_caixa_do_modelo,
)

# DL-046, fatia 2: mesmos limites de precisão do resto do módulo monetário
# (`apps.core.dinheiro`, DE-010) — `max_digits`/`decimal_places` generosos o
# bastante para qualquer valor real de carnê-leão, sem inventar um teto
# arbitrário menor que o do resto do sistema.
_MAX_DIGITOS_VALOR_NORMATIVO = 18
_CASAS_VALOR_NORMATIVO = 2

# M2 (rodada 1 de auditoria da DL-046): `models.CharField` NÃO inclui
# `ProhibitNullCharactersValidator` por padrão (só `forms.CharField` inclui,
# na camada de FORMULÁRIO) — por isso um `\x00` num campo de texto livre
# chegava direto ao INSERT do PostgreSQL, que recusa com `DataError` cru
# (500). Aplicado nos quatro `CharField` de texto livre dos dois modelos
# (nunca em `choices=`/CPF/CNPJ, que já têm seus próprios validadores de
# formato restritos a um alfabeto sem NUL).
_SEM_CARACTERE_NULO = ProhibitNullCharactersValidator()


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
    codigo = models.CharField("código", max_length=20, validators=[_SEM_CARACTERE_NULO])
    nome = models.CharField("nome", max_length=200, validators=[_SEM_CARACTERE_NULO])
    natureza = models.CharField("natureza", max_length=10, choices=NaturezaCaixa.choices)
    codigo_carne_leao = models.CharField(
        "código do Carnê-Leão Web",
        max_length=30,
        help_text=(
            "Rendimento (R01.xxx.xxx) para conta de receita; pagamento "
            "(P10/P11/P20 + dígitos) para conta de despesa (HI-30)."
        ),
    )
    # DL-046, fatia 3 (RC-127/HI-34): sobrepõe o código de ocupação do
    # cadastro (`Empresa.codigo_ocupacao`) SÓ para esta conta — o leiaute
    # oficial pede a ocupação por LINHA de rendimento de trabalho não
    # assalariado, e o escritório pode ter um cliente com mais de uma
    # ocupação, cada uma numa conta diferente. Vazio (padrão) usa o do
    # cadastro; a coerência com o MODELO da conta (só trabalho não
    # assalariado e notarial — este último travado em 117) é validada em
    # `clean()`, porque depende de `self.codigo_carne_leao`/`self.natureza`,
    # outros campos do MESMO modelo.
    codigo_ocupacao = models.CharField(
        "código de ocupação (Carnê-Leão Web) — sobrepõe o do cadastro",
        max_length=3,
        blank=True,
        default="",
        validators=[validar_codigo_ocupacao],
        help_text=(
            "Opcional — sobrepõe o código de ocupação do cadastro da "
            "empresa só para esta conta (HI-34). Só em conta de rendimento "
            "de trabalho não assalariado ou notarial (neste último, sempre "
            "117)."
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
            # DL-046, fatia 3: FORMATO do código de ocupação (3 dígitos ou
            # vazio) — mesmo padrão condicional de `Empresa.codigo_
            # ocupacao`/CAEPF (DE-008, camada 1). A coerência com o MODELO
            # da conta (só trabalho não assalariado/notarial) e o
            # pertencimento à tabela oficial ficam em `clean()`/
            # `validar_codigo_ocupacao` — uma `CheckConstraint` de banco não
            # confere pertencimento a uma tabela Python nem compara com
            # OUTRO campo de texto livre (`codigo_carne_leao`) de forma
            # simples em SQL.
            models.CheckConstraint(
                condition=models.Q(codigo_ocupacao="")
                | models.Q(codigo_ocupacao__regex=r"^[0-9]{3}$"),
                name="conta_livro_caixa_codigo_ocupacao_formato_valido",
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

        # DL-046, fatia 3 (RC-127/HI-34): coerência do código de ocupação
        # (sobreposição) com o MODELO de rendimento da conta — só depois da
        # checagem de formato do código do Carnê-Leão Web, acima, porque
        # `modelo_do_codigo_de_rendimento` espera um código já coerente com
        # a natureza (um código de PAGAMENTO nunca é "trabalho não
        # assalariado" nem "notarial").
        if self.codigo_ocupacao:
            modelo = modelo_do_codigo_de_rendimento(self.codigo_carne_leao)
            erro_ocupacao = erro_de_codigo_ocupacao_da_conta(
                modelo, natureza=self.natureza, codigo_ocupacao=self.codigo_ocupacao
            )
            if erro_ocupacao is not None:
                raise ValidationError({"codigo_ocupacao": erro_ocupacao})

        # Guardas de TRANSIÇÃO (mesmo molde do BL-83/DL-023 e da DL-033/
        # DL-045), consolidadas numa consulta só. A PRIMEIRA gravação
        # (`self.pk` ainda `None`) é sempre livre para as três.
        if self.pk:
            gravado = (
                ContaLivroCaixa.objects.filter(pk=self.pk)
                .values("natureza", "codigo_carne_leao", "empresa_id")
                .first()
            )
            if gravado is not None:
                tem_lancamento = self._tem_lancamento_gravado()

                # Natureza: mudar a NATUREZA de uma conta que já tem
                # lançamento gravado inverteria o sentido (receita <->
                # despesa) do histórico inteiro sem nenhum lançamento novo.
                if gravado["natureza"] != self.natureza and tem_lancamento:
                    raise ValidationError(
                        "Não é possível mudar a natureza desta conta do livro-caixa: "
                        "ela já tem lançamento gravado — a troca inverteria o sentido "
                        "(receita/despesa) do histórico. Estorne o movimento antes de "
                        "reclassificar, ou cadastre uma conta nova."
                    )

                # M4 (achado da rodada 1 de auditoria, DE-087 item 4): o
                # código do Carnê-Leão Web decide a DEDUTIBILIDADE e o que
                # vai para a Receita (HI-30) — trocá-lo numa conta com
                # lançamento mudaria a classificação de meses já
                # escriturados (e possivelmente já apurados no carnê-leão)
                # sem nenhum lançamento novo e sem trilha. Mesma defesa da
                # natureza, acima; mesma saída (conta nova).
                if gravado["codigo_carne_leao"] != self.codigo_carne_leao and tem_lancamento:
                    raise ValidationError(
                        {
                            "codigo_carne_leao": (
                                "Não é possível mudar o código do Carnê-Leão Web desta "
                                "conta: ela já tem lançamento gravado, e o código decide "
                                "a dedutibilidade (HI-30). Cadastre uma conta nova para a "
                                "nova classificação."
                            )
                        }
                    )

                # M3 (achado da rodada 1 de auditoria): mover uma conta com
                # lançamento para OUTRA empresa deixaria `LancamentoCaixa.
                # empresa != LancamentoCaixa.conta.empresa` — o mesmo estado
                # que `LancamentoCaixa.clean()` já proíbe na ORIGEM, e que
                # tornava o estorno desse lançamento impossível (o serviço
                # recusa "conta não pertence a esta empresa"). Mesmo
                # precedente de `Conta.clean()` (contabilidade).
                if gravado["empresa_id"] != self.empresa_id and tem_lancamento:
                    raise ValidationError(
                        "Não é possível mudar a empresa desta conta do livro-caixa: ela "
                        "já tem lançamento gravado."
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
    historico = models.CharField("histórico", max_length=300, validators=[_SEM_CARACTERE_NULO])
    documento_origem = models.CharField(
        "documento de origem",
        max_length=100,
        blank=True,
        default="",
        validators=[_SEM_CARACTERE_NULO],
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
    # CPF do titular do pagamento, CPF do beneficiário do serviço e o
    # indicador de "CPF não informado" seguem o leiaute oficial dos modelos
    # de importação do Carnê-Leão Web (Receita, 2025 — M5/DE-087 item 6,
    # corrigindo a hipótese original desta etapa, que restringia a
    # exigência ao código de trabalho não assalariado): rendimento recebido
    # de PF exige o CPF do titular do pagamento; o CPF do beneficiário pode
    # faltar desde que o indicador esteja marcado; CPF só é aceito quando
    # `recebido_de=PF`, e CNPJ só quando `recebido_de=PJ` — tudo checado em
    # `clean()`, porque depende de `self.recebido_de`, outro campo do MESMO
    # modelo. Código de ocupação e IRRF (também do leiaute oficial) ficam
    # para a fatia 3 (RC-127), planejados antes dela.
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
    # M5/DE-087 item 6: "preenchido somente nos casos em que houver a
    # exigência do CPF do beneficiário e esse não foi informado" (leiaute
    # oficial, campo 10) — indicador explícito, nunca inferido do campo
    # `cpf_beneficiario_servico` estar vazio (um campo vazio por OMISSÃO,
    # sem o indicador marcado, é recusado — ver `LancamentoCaixa.clean()`).
    cpf_beneficiario_nao_informado = models.BooleanField(
        "CPF do beneficiário não informado", default=False
    )
    cnpj_pagador = CNPJModelField(
        "CNPJ do pagador", max_length=14, blank=True, default="", validators=[validar_cnpj]
    )
    # DL-046, fatia 3 (RC-127): IRRF retido — leiaute oficial dos modelos de
    # rendimento (Receita, 2025), campos "Indicador de IRRF"/"Valor IRRF".
    # Só o VALOR é gravado; o INDICADOR ("S"/"N") é DERIVADO na geração do
    # arquivo (S com valor > 0, N sem retenção) — nunca um segundo campo que
    # poderia divergir do valor. Só aceito quando `recebido_de="PJ"`
    # (`clean()`, abaixo — `apps.livro_caixa.validators.erro_de_valor_irrf`).
    valor_irrf = models.DecimalField(
        "valor de IRRF retido",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=(
            "Opcional — só em rendimento recebido de pessoa jurídica (PJ). "
            "O indicador S/N do arquivo de importação é derivado deste "
            "valor (S se maior que zero, N caso contrário)."
        ),
    )
    # DL-046, fatia 3 (RC-127): competência, multa e juros do PAGAMENTO de
    # previdência oficial (`P20.01.00001`) — leiaute oficial ("Modelo de
    # Arquivo de Pagamentos Gerais", campos 5 a 7: "para os pagamentos do
    # tipo Imposto Pago e Previdência Oficial"). Nesta fatia, restrito só à
    # previdência oficial (o "Imposto Pago" — P20.01.00004 — está fora do
    # escopo, ver o plano DL-046); qualquer OUTRO código recusa os três
    # (`clean()`, abaixo — `apps.livro_caixa.validators.
    # erros_de_previdencia_oficial`). `competencia_previdencia` guarda
    # sempre o PRIMEIRO DIA do mês (mesma convenção de `VigenciaTabela
    # ProgressivaCarneLeao.vigencia_inicio`/`DependentesCarneLeaoCliente.
    # competencia_inicio`) — só mês/ano importam, o dia é descartado na
    # geração do arquivo (formato MM/AAAA).
    competencia_previdencia = models.DateField(
        "competência da previdência oficial (mês)",
        null=True,
        blank=True,
        help_text=(
            "Obrigatória só no pagamento de previdência oficial "
            "(P20.01.00001) — sempre o primeiro dia do mês de competência."
        ),
    )
    multa_previdencia = models.DecimalField(
        "valor da multa (previdência oficial)",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    juros_previdencia = models.DecimalField(
        "valor dos juros (previdência oficial)",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # Idempotência (BL-41, mesmo padrão de `LancamentoContabil`).
    chave_idempotencia = models.CharField(
        "chave de idempotência",
        max_length=255,
        null=True,
        blank=True,
        validators=[_SEM_CARACTERE_NULO],
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
            # DL-046, fatia 3: valores não negativos dos três campos novos
            # de previdência oficial e do IRRF — mesma camada 1 (DE-008) de
            # `lancamento_caixa_valor_positivo`, acima; a COERÊNCIA com o
            # código da conta (só previdência oficial aceita os três; só PJ
            # aceita IRRF) fica em `clean()`, que não é alcançável por SQL
            # puro (depende de `self.conta.codigo_carne_leao`, outra
            # tabela).
            models.CheckConstraint(
                condition=models.Q(valor_irrf__isnull=True) | models.Q(valor_irrf__gte=0),
                name="lancamento_caixa_valor_irrf_nao_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(multa_previdencia__isnull=True)
                | models.Q(multa_previdencia__gte=0),
                name="lancamento_caixa_multa_previdencia_nao_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(juros_previdencia__isnull=True)
                | models.Q(juros_previdencia__gte=0),
                name="lancamento_caixa_juros_previdencia_nao_negativa",
            ),
            # A competência é sempre o PRIMEIRO DIA do mês (mesmo motivo de
            # "vigencia_tabela_carne_leao_inicio_dia_1" — o arquivo só usa
            # MM/AAAA; um dia fora do 1º só criaria ambiguidade sem
            # propósito).
            models.CheckConstraint(
                condition=models.Q(competencia_previdencia__isnull=True)
                | models.Q(competencia_previdencia__day=1),
                name="lancamento_caixa_competencia_previdencia_dia_1",
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

        # M4 (DE-087 item 4): o ESTORNO copia o original campo a campo e
        # NÃO revalida as regras abaixo, que dependem do código do Carnê-
        # Leão Web da conta ATUAL — a rodada 1 de auditoria mediu que
        # trocar o código de uma conta com lançamento (antes desta rodada,
        # livre) quebrava o estorno de um lançamento ANTIGO, que passava a
        # ser julgado contra uma regra que não valia quando ele foi criado.
        # A guarda de imutabilidade do código (`ContaLivroCaixa.clean()`)
        # fecha o caminho de ORIGEM; esta flag é a segunda camada, para o
        # ESTORNO nunca depender da conta atual, ainda que a guarda de
        # origem mude no futuro. Setada só por
        # `apps.livro_caixa.services.estornar_lancamento_caixa`, nunca por
        # entrada de cliente.
        if getattr(self, "_estorno_nao_revalida_regras_da_conta", False):
            return

        if self.conta.natureza == NaturezaCaixa.DESPESA:
            if (
                self.recebido_de
                or self.cpf_titular_pagamento
                or self.cpf_beneficiario_servico
                or self.cpf_beneficiario_nao_informado
                or self.cnpj_pagador
                or self.valor_irrf is not None
            ):
                raise ValidationError(
                    "Lançamento de DESPESA não tem 'recebido de', CPF do titular/"
                    "beneficiário, CNPJ do pagador nem IRRF — esses campos são só "
                    "de lançamento de RECEITA."
                )
            # DL-046, fatia 3 (RC-127): competência/multa/juros só no
            # pagamento de previdência oficial — a regra por CÓDIGO mora em
            # `apps.livro_caixa.validators.erros_de_previdencia_oficial`
            # (módulo puro, sem ORM), mesmo padrão de `erros_de_cpf_cnpj_
            # do_rendimento` para RECEITA, abaixo.
            erros_previdencia = erros_de_previdencia_oficial(
                self.conta.codigo_carne_leao,
                competencia=self.competencia_previdencia,
                multa=self.multa_previdencia,
                juros=self.juros_previdencia,
            )
            if erros_previdencia:
                raise ValidationError(erros_previdencia)
            return

        # RECEITA a partir daqui.
        if not self.recebido_de:
            raise ValidationError(
                {"recebido_de": "Lançamento de receita exige 'recebido de' (PF, PJ ou EX)."}
            )

        # DL-046, fatia 3: os três campos de previdência oficial são só de
        # DESPESA (P20.01.00001) — uma RECEITA nunca os aceita.
        if (
            self.competencia_previdencia is not None
            or self.multa_previdencia is not None
            or self.juros_previdencia is not None
        ):
            raise ValidationError(
                "Competência, multa e juros de previdência oficial são só de "
                "lançamento de DESPESA (P20.01.00001) — não se aplicam a "
                "lançamento de RECEITA."
            )

        # M5/DE-088 item 1 (reabertura da DE-087 item 6, reconferência):
        # regra do LEIAUTE OFICIAL do Carnê-Leão Web, POR MODELO de
        # rendimento (não mais uma regra universal para toda receita — a
        # generalização era o próprio defeito apontado na reconferência).
        # A tabela código → modelo e a regra de cada um moram em
        # `apps.livro_caixa.validators` (módulo puro, sem ORM).
        modelo = modelo_do_codigo_de_rendimento(self.conta.codigo_carne_leao)
        erros = erros_de_cpf_cnpj_do_rendimento(
            modelo,
            recebido_de=self.recebido_de,
            cpf_titular_pagamento=self.cpf_titular_pagamento,
            cpf_beneficiario_servico=self.cpf_beneficiario_servico,
            cpf_beneficiario_nao_informado=self.cpf_beneficiario_nao_informado,
            cnpj_pagador=self.cnpj_pagador,
        )
        if erros:
            raise ValidationError(erros)

        # DL-046, fatia 3 (RC-127): IRRF retido só em rendimento recebido de
        # PJ — `apps.livro_caixa.validators.erro_de_valor_irrf`.
        erro_irrf = erro_de_valor_irrf(recebido_de=self.recebido_de, valor_irrf=self.valor_irrf)
        if erro_irrf is not None:
            raise ValidationError({"valor_irrf": erro_irrf})


# ---------------------------------------------------------------------------
# DL-046, fatia 2 — apuração mensal do carnê-leão (RC-131, HI-32 a HI-36).
#
# ⚠️ Critério 5 do plano: "nenhum número normativo no código: teste que
# falha se a tabela vier de constante". Por isso NENHUM valor da tabela
# progressiva, da redução da Lei 15.270/2025 ou do valor por dependente
# aparece como literal Python em `apps.livro_caixa.carne_leao` — os quatro
# modelos abaixo são a ÚNICA fonte desses números, e chegam ao banco só por
# MIGRAÇÃO DE DADOS (nunca por admin: ver o comentário de
# `VigenciaTabelaProgressivaCarneLeao`, abaixo, sobre por que este app não
# registra `ModelAdmin` para eles nesta fatia).
#
# DE-089 (decisões.md): o desenho de VIGÊNCIA aqui é DELIBERADAMENTE mais
# simples que o de `ParametroContabilEmpresa`/`HistoricoRegimeTributario`
# (apps.contabilidade/apps.empresas) — sem `vigencia_fim`, sem gatilho de
# não sobreposição. Não é descuido: aqueles dois modelos guardam PARÂMETRO
# POR EMPRESA, escrito por múltiplos usuários concorrentes, onde uma
# vigência aberta duplicada é um estado inconsistente alcançável por
# corrida real (dois `POST` simultâneos). As quatro tabelas normativas
# abaixo são GLOBAIS (não por empresa), escritas SÓ por migração de dados
# — nunca por uma requisição HTTP concorrente —, então a pergunta "qual
# vigência vale para esta data" tem uma resposta simples e suficiente: a de
# MAIOR `vigencia_inicio` que não seja posterior à data pedida. Uma
# `UniqueConstraint` em `vigencia_inicio` já impede duas vigências com a
# mesma data de início (a única ambiguidade que este desenho não resolve
# por construção); não há "vigência aberta/fechada" para rastrear.
def _vigencia_aplicavel_ou_none(queryset, referencia):
    """Devolve a linha de maior `vigencia_inicio` que não seja POSTERIOR a
    `referencia`, ou `None` se não houver nenhuma — mesmo raciocínio do
    parágrafo do DE-089 acima, compartilhado pelas quatro tabelas
    normativas desta fatia (`carne_leao.py` importa esta função; ela mora
    aqui, ao lado dos modelos, para não duplicar a MESMA consulta quatro
    vezes)."""
    return queryset.filter(vigencia_inicio__lte=referencia).order_by("-vigencia_inicio").first()


class VigenciaTabelaProgressivaCarneLeao(models.Model):
    """Uma VERSÃO da tabela progressiva mensal do carnê-leão (RIR/2018,
    art. 122; Lei nº 11.482/2007, art. 1º, XII, na redação da Lei
    15.191/2025) — as FAIXAS (`FaixaTabelaProgressivaCarneLeao`) vivem à
    parte, uma linha por faixa, todas apontando para esta vigência.

    `fonte` é OBRIGATÓRIA e fica gravada ao lado do número (AGENTS.md §9):
    quem ler o banco no futuro precisa saber de onde cada valor veio, sem
    precisar abrir a migração de dados que o inseriu.

    ⚠️ Sem `ModelAdmin` nesta fatia (decisão reportada, ver o plano
    DL-046): um valor normativo mudar por um `POST` de formulário do admin,
    sem revisão de código nem citação de fonte no mesmo commit, é
    exatamente o risco que "gravado por migração de dados, com a fonte
    citada" existe para evitar. Uma vigência nova entra por uma migração
    de dados nova — revisável, versionada, com a fonte no próprio código
    da migração —, nunca por edição ad-hoc.
    """

    # `UniqueConstraint` explícita em `Meta.constraints`, NUNCA
    # `unique=True` no campo: um `unique=True` gera um índice único
    # IMPLÍCITO, que a varredura de restrições
    # (`apps/core/tests/test_dl019_varredura_de_restricoes.py`) trata numa
    # lista PRÓPRIA e mais rígida (fora do escopo de arquivos desta etapa),
    # separada de `Meta.constraints` (que `apps/core/restricoes.py`, dentro
    # do escopo, já cobre). Mesmo VALOR de unicidade; forma DIFERENTE de
    # declará-lo.
    vigencia_inicio = models.DateField("vigência (início)")
    fonte = models.TextField("fonte normativa")
    # B-1 (auditoria da fatia 2, rodada 1): o percentual do desconto
    # simplificado (25%) MORA na vigência, com fonte — antes era
    # `Decimal("0.25")` literal em `carne_leao.py`, violando o critério 5
    # do plano ("nenhum número normativo no código"). Fonte: Lei nº
    # 9.250/1995, art. 4º, § 2º (redação da Lei nº 14.663/2023): "25% (vinte
    # e cinco por cento) do valor máximo da faixa com alíquota zero da
    # tabela progressiva mensal". Gravado como FRAÇÃO (0.2500), mesmo
    # padrão de `FaixaTabelaProgressivaCarneLeao.aliquota`.
    percentual_desconto_simplificado = models.DecimalField(
        "percentual do desconto simplificado (fração)", max_digits=6, decimal_places=4
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vigência da tabela progressiva do carnê-leão"
        verbose_name_plural = "vigências da tabela progressiva do carnê-leão"
        ordering = ["-vigencia_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["vigencia_inicio"], name="vigencia_tabela_carne_leao_inicio_unico"
            ),
            # B-5 (auditoria da fatia 2, rodada 1): toda vigência normativa
            # do carnê-leão começa no dia 1º de um mês (as leis e a IN
            # sempre falam em "a partir do mês de..."); um `vigencia_inicio`
            # no meio do mês só valeria a partir do mês SEGUINTE, na
            # comparação de `_maior_vigencia_nao_posterior` (que usa o
            # primeiro dia de cada mês como referência) — deixar isso
            # gravável seria uma armadilha silenciosa. Só migração de dados
            # grava este campo; a `CheckConstraint` é defesa de banco, sem
            # caminho de cliente (ver `apps/core/restricoes.py`).
            models.CheckConstraint(
                condition=models.Q(vigencia_inicio__day=1),
                name="vigencia_tabela_carne_leao_inicio_dia_1",
            ),
            models.CheckConstraint(
                condition=models.Q(percentual_desconto_simplificado__gte=0)
                & models.Q(percentual_desconto_simplificado__lte=1),
                name="vigencia_tabela_carne_leao_percentual_simplificado_valido",
            ),
        ]

    def __str__(self):
        return f"Tabela progressiva do carnê-leão desde {self.vigencia_inicio}"


class FaixaTabelaProgressivaCarneLeao(models.Model):
    """Uma FAIXA (alíquota + parcela a deduzir) de uma vigência da tabela
    progressiva. `aliquota` é gravada como FRAÇÃO (0.0750 = 7,5%), para a
    apuração multiplicar direto pela base, sem dividir por 100 em nenhum
    ponto do motor de cálculo."""

    vigencia = models.ForeignKey(
        VigenciaTabelaProgressivaCarneLeao, on_delete=models.PROTECT, related_name="faixas"
    )
    ordem = models.PositiveSmallIntegerField("ordem")
    limite_inferior = models.DecimalField(
        "limite inferior",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    # `null=True`: a última faixa (maior alíquota) não tem limite superior
    # ("acima de X") — `None` representa "sem limite", nunca um número
    # grande arbitrário inventado para simular infinito.
    limite_superior = models.DecimalField(
        "limite superior",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
        null=True,
        blank=True,
    )
    aliquota = models.DecimalField("alíquota (fração)", max_digits=6, decimal_places=4)
    parcela_a_deduzir = models.DecimalField(
        "parcela a deduzir",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )

    class Meta:
        verbose_name = "faixa da tabela progressiva do carnê-leão"
        verbose_name_plural = "faixas da tabela progressiva do carnê-leão"
        ordering = ["vigencia", "ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=["vigencia", "ordem"], name="faixa_carne_leao_ordem_unica_por_vigencia"
            ),
            models.CheckConstraint(
                condition=models.Q(ordem__gte=1), name="faixa_carne_leao_ordem_positiva"
            ),
            models.CheckConstraint(
                condition=models.Q(aliquota__gte=0) & models.Q(aliquota__lte=1),
                name="faixa_carne_leao_aliquota_valida",
            ),
            models.CheckConstraint(
                condition=models.Q(limite_inferior__gte=0),
                name="faixa_carne_leao_limite_inferior_nao_negativo",
            ),
        ]

    def __str__(self):
        return f"Faixa {self.ordem} — {self.vigencia}"


class VigenciaReducaoCarneLeao(models.Model):
    """Uma VERSÃO dos parâmetros da redução mensal da Lei 15.270/2025 (Lei
    nº 9.250/1995, art. 3º-A): até `limite_faixa_plena`, redução fixa de
    `reducao_maxima` (imposto zero); de `limite_faixa_plena` até
    `limite_superior`, redução linear decrescente
    `constante_formula - coeficiente * base`; acima de `limite_superior`,
    sem redução (§2º). A memória de cálculo completa mora em
    `apps.livro_caixa.carne_leao`."""

    # Mesmo motivo do comentário em `VigenciaTabelaProgressivaCarneLeao`
    # (unicidade por `Meta.constraints`, não `unique=True` de campo).
    vigencia_inicio = models.DateField("vigência (início)")
    fonte = models.TextField("fonte normativa")
    limite_faixa_plena = models.DecimalField(
        "limite da faixa de redução plena",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    reducao_maxima = models.DecimalField(
        "redução máxima (faixa plena)",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    constante_formula = models.DecimalField(
        "constante da fórmula linear",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    coeficiente = models.DecimalField(
        "coeficiente da fórmula linear", max_digits=10, decimal_places=6
    )
    limite_superior = models.DecimalField(
        "limite superior (fim da redução)",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vigência da redução do carnê-leão (Lei 15.270/2025)"
        verbose_name_plural = "vigências da redução do carnê-leão (Lei 15.270/2025)"
        ordering = ["-vigencia_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["vigencia_inicio"], name="vigencia_reducao_carne_leao_inicio_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(limite_faixa_plena__gte=0)
                & models.Q(reducao_maxima__gte=0)
                & models.Q(limite_superior__gte=0),
                name="reducao_carne_leao_valores_nao_negativos",
            ),
            # B-5 — mesmo motivo de `vigencia_tabela_carne_leao_inicio_dia_1`.
            models.CheckConstraint(
                condition=models.Q(vigencia_inicio__day=1),
                name="vigencia_reducao_carne_leao_inicio_dia_1",
            ),
        ]

    def __str__(self):
        return f"Redução do carnê-leão (Lei 15.270/2025) desde {self.vigencia_inicio}"


class VigenciaDependenteCarneLeao(models.Model):
    """Uma VERSÃO do valor de dedução mensal por dependente (RIR/2018,
    art. 71; HI-32 — 2026 sem confirmação literal, sem norma posterior
    encontrada que altere)."""

    # Mesmo motivo do comentário em `VigenciaTabelaProgressivaCarneLeao`
    # (unicidade por `Meta.constraints`, não `unique=True` de campo).
    vigencia_inicio = models.DateField("vigência (início)")
    fonte = models.TextField("fonte normativa")
    valor_por_dependente = models.DecimalField(
        "valor por dependente",
        max_digits=_MAX_DIGITOS_VALOR_NORMATIVO,
        decimal_places=_CASAS_VALOR_NORMATIVO,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vigência do valor por dependente do carnê-leão"
        verbose_name_plural = "vigências do valor por dependente do carnê-leão"
        ordering = ["-vigencia_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["vigencia_inicio"], name="vigencia_dependente_carne_leao_inicio_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(valor_por_dependente__gte=0),
                name="dependente_carne_leao_valor_nao_negativo",
            ),
            # B-5 — mesmo motivo de `vigencia_tabela_carne_leao_inicio_dia_1`.
            models.CheckConstraint(
                condition=models.Q(vigencia_inicio__day=1),
                name="vigencia_dependente_carne_leao_inicio_dia_1",
            ),
        ]

    def __str__(self):
        return f"R$ {self.valor_por_dependente} por dependente desde {self.vigencia_inicio}"


class DependentesCarneLeaoCliente(models.Model):
    """Quantidade de dependentes de UM cliente (empresa em modo
    livro-caixa), informada pelo escritório, com vigência MENSAL (HI-35 —
    sem cadastro nominal nesta fatia: só a quantidade usada na dedução).

    `competencia_inicio` é sempre o PRIMEIRO DIA de um mês — "a partir de
    um mês" (HI-35) — e a apuração de um mês qualquer usa o registro de
    maior `competencia_inicio` que não seja posterior ao primeiro dia
    daquele mês (mesmo raciocínio de `_vigencia_aplicavel_ou_none`, mas por
    EMPRESA em vez de global — por isso o índice único é composto)."""

    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="dependentes_carne_leao"
    )
    quantidade = models.PositiveSmallIntegerField("quantidade de dependentes")
    competencia_inicio = models.DateField("vigente a partir de (mês)")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "quantidade de dependentes do carnê-leão"
        verbose_name_plural = "quantidades de dependentes do carnê-leão"
        ordering = ["empresa", "-competencia_inicio"]
        constraints = [
            # B-4 (auditoria da fatia 2, rodada 1): `violation_error_message`
            # (Django ≥ 4.1) faz `full_clean()`/`validate_unique()` devolver
            # ESTA mensagem no caminho SEQUENCIAL (o comum) — antes desta
            # correção, `validate_unique()` já resolvia a duplicidade com a
            # mensagem PADRÃO do Django ("...com este Empresa e Vigente a
            # partir de (mês) já existe.") antes de qualquer `INSERT`, e a
            # mensagem registrada em `apps/core/restricoes.py`
            # (`MENSAGENS_DE_RESTRICAO`) só se aplicava ao caminho RESIDUAL
            # de corrida (`IntegrityError`) — os dois continuam cobertos,
            # cada um na sua camada.
            models.UniqueConstraint(
                fields=["empresa", "competencia_inicio"],
                name="dependentes_carne_leao_competencia_unica_por_empresa",
                violation_error_message=(
                    "Já existe uma quantidade de dependentes registrada para esta "
                    "empresa a partir deste mês — use Retificar para corrigir o "
                    "valor, em vez de um novo registro."
                ),
            ),
            # B-5: mesmo motivo das tabelas normativas, mas aqui já existe
            # validação de campo em `clean()` (mensagem melhor, citando
            # HI-35) — esta `CheckConstraint` é defesa de banco para
            # ORM/SQL direto, redundante com a validação de cima.
            models.CheckConstraint(
                condition=models.Q(competencia_inicio__day=1),
                name="dependentes_carne_leao_competencia_dia_1",
            ),
        ]

    def __str__(self):
        return f"{self.empresa} — {self.quantidade} dependente(s) desde {self.competencia_inicio}"

    def clean(self):
        if self.empresa_id:
            try:
                recusar_se_nao_livro_caixa(self.empresa)
            except EmpresaNaoEmModoLivroCaixa as exc:
                raise ValidationError({"empresa": exc.mensagem}) from exc
        if self.competencia_inicio and self.competencia_inicio.day != 1:
            raise ValidationError(
                {
                    "competencia_inicio": (
                        "A vigência dos dependentes começa sempre no primeiro dia de um mês."
                    )
                }
            )
