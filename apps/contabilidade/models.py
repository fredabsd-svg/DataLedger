from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import connection, models

from apps.contabilidade.validators import validar_data_de_lancamento_do_modelo
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

    def _tem_movimento_proprio_ou_de_descendente(self):
        """`True` se esta conta OU qualquer descendente (profundidade
        qualquer) tem ao menos uma partida gravada.

        BL-245 (achado P1 da auditoria DL-023 rodada 1): uma conta
        SINTÉTICA (`aceita_lancamento=False`) sem movimento PRÓPRIO, mas
        com filha movimentada, trocava de natureza/tipo livremente pelo
        admin — e `apurar_balancete` aplica a natureza da conta
        APRESENTADA (a sintética) uma única vez, no fim, sobre o
        CONSOLIDADO de toda a subárvore (próprio + descendentes). Olhar só
        `self.itens_lancamento` cumpria o texto do requisito antigo
        ("conta com movimento") e não o dano que a BL-83 nomeia (inverter
        o sinal de todo o histórico do GRUPO). O requisito passou a ser
        "movimento próprio OU de descendente" (decisão do
        `arquiteto-senior`, rodada 2).

        UMA consulta só — `WITH RECURSIVE` sobe a árvore inteira dentro do
        PRÓPRIO PostgreSQL — em vez de um laço em Python que desce nível a
        nível (o padrão que `apps.contabilidade.services._descendentes_de`
        usa para o Razão). Custo importa aqui: `Conta.clean()` já paga
        consultas extra por `full_clean()` de conta persistida (achado P9/
        BL-253), e multiplicar por uma consulta por NÍVEL da árvore
        agravaria exatamente o que aquele achado já registra. `UNION`
        (não `UNION ALL`) deduplica ids já visitados, o que também torna a
        recursão seguro contra um CICLO pré-existente na hierarquia
        (alcançável só por ORM/SQL direto, contornando o guard de ciclo de
        `clean()` acima): sem novos ids para adicionar, o `WITH RECURSIVE`
        termina sozinho, sem loop infinito nem exceção — não é papel deste
        guard diagnosticar ciclo, é papel de
        `localizar_inconsistencias_de_hierarquia` (BL-64/conferência).

        Não filtra por `empresa`: `self.pk` já identifica uma conta de UMA
        empresa, e `conta_pai_id` só aponta para outra empresa em estado
        já inconsistente (o guard de `conta_pai`/empresa em `clean()`
        acima impede isso pelo caminho validado) — se existir, a subárvore
        ficaria maior do que deveria, o que é o lado ESTRITO de errar,
        nunca o contrário.
        """
        # BL-265 (achado P5 da auditoria DL-023 rodada 3): nomes de TABELA
        # já vinham do `_meta` (`db_table`), mas os de COLUNA estavam
        # escritos à mão (`conta_pai_id`, `conta_id`) — hoje corretos, mas
        # em assimetria com o resto da consulta, e frágeis a um
        # `db_column=` futuro numa das duas FKs (o projeto já tem
        # precedente de migração corretiva de coluna, BL-47). Perguntar ao
        # `_meta` os quatro identificadores fecha a assimetria com o mesmo
        # custo: nenhuma consulta a mais, é resolvido em Python antes do
        # SQL.
        tabela_conta = Conta._meta.db_table
        tabela_item = ItemLancamento._meta.db_table
        coluna_conta_pai = Conta._meta.get_field("conta_pai").column
        coluna_conta_do_item = ItemLancamento._meta.get_field("conta").column
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH RECURSIVE arvore(id) AS (
                    SELECT id FROM {tabela_conta} WHERE id = %s
                    UNION
                    SELECT c.id FROM {tabela_conta} c
                    INNER JOIN arvore a ON c.{coluna_conta_pai} = a.id
                )
                SELECT EXISTS (
                    SELECT 1 FROM {tabela_item}
                    WHERE {coluna_conta_do_item} IN (SELECT id FROM arvore)
                )
                """,
                [self.pk],
            )
            (existe,) = cursor.fetchone()
        return existe

    def clean(self):
        if self.conta_pai_id and self.conta_pai.empresa_id != self.empresa_id:
            raise ValidationError("A conta pai deve pertencer à mesma empresa.")

        # Impede o ciclo NA ORIGEM (achado 6 da auditoria DL-015, rodada 1):
        # sem esta checagem, atribuir como pai uma conta descendente da
        # própria conta (inclusive a própria conta, o caso degenerado de
        # profundidade zero) criava um laço que derrubava o Balancete e o
        # Razão com RecursionError. Só se aplica a conta já persistida
        # (`self.pk`): uma conta nova, sem filhos ainda, não pode ser
        # ancestral de nada. O limite de profundidade é uma defesa
        # REDUNDANTE contra um ciclo PRÉ-EXISTENTE não relacionado a esta
        # conta (ex.: duas outras contas já formando um laço) — sem ele,
        # `ancestral.conta_pai` desse laço alheio faria este laço FOR
        # nunca terminar.
        if self.pk and self.conta_pai_id:
            ancestral = self.conta_pai
            profundidade = 0
            while ancestral is not None:
                if ancestral.pk == self.pk:
                    raise ValidationError(
                        "A conta pai não pode ser a própria conta nem uma conta "
                        f"descendente dela — isto criaria um ciclo envolvendo "
                        f"{self.codigo} ({self.nome})."
                    )
                profundidade += 1
                if profundidade > 1000:
                    raise ValidationError(
                        "Não foi possível validar a hierarquia de contas: "
                        "profundidade excessiva ou ciclo pré-existente entre "
                        "outras contas."
                    )
                ancestral = ancestral.conta_pai

        # Guarda de dado (achado 2 / DE-020): recusa marcar como sintética
        # ("aceita_lancamento=False") uma conta que já tem movimento próprio
        # gravado. Antes desta guarda, o Django admin permitia essa
        # reclassificação sem checagem alguma, e o valor da conta ficava
        # órfão no Balancete (o débito existia no Diário e não aparecia em
        # linha nenhuma). A regra única de saldo do Balancete já impede o
        # valor de desaparecer mesmo que este estado exista — esta guarda
        # existe para não deixar o estado ACONTECER pelo caminho validado
        # (admin/formulário); acesso direto ao ORM continua contornando-a,
        # risco já aceito e documentado no projeto (DE-008).
        #
        # Achado novo 14 (rodada 2): a guarda original disparava sempre que
        # o ESTADO ATUAL fosse "sintética com movimento", mesmo quando esta
        # gravação não tem NADA a ver com `aceita_lancamento` — por exemplo,
        # uma conta já em estado legado (alcançado por `.update()` direto no
        # ORM, contornando esta mesma guarda) que alguém só quer RENOMEAR.
        # A mensagem acusava "não é possível marcar esta conta como
        # sintética" a quem não tocou nesse campo. A guarda agora só
        # dispara na TRANSIÇÃO real desta gravação (o valor gravado no banco
        # era `True`, e esta chamada está mudando para `False`) — um estado
        # já inconsistente ANTES desta gravação não é reportado aqui de
        # novo: quem aponta esse caso é a conferência (BL-64, quarta
        # categoria e `contas_sinteticas_com_movimento`), que não acusa
        # ninguém de uma ação específica.
        if self.pk and not self.aceita_lancamento and self.itens_lancamento.exists():
            valor_gravado = (
                Conta.objects.filter(pk=self.pk).values_list("aceita_lancamento", flat=True).first()
            )
            if valor_gravado:
                raise ValidationError(
                    "Não é possível marcar esta conta como sintética: ela já tem "
                    "lançamento próprio gravado. Estorne ou mova o movimento "
                    "antes de reclassificar."
                )

        # DL-023, critérios 1-4 (BL-83): `ContaAdmin` deixava mover conta COM
        # movimento para outra empresa e trocar a NATUREZA de conta já
        # movimentada — medido: o balancete da empresa de origem passava a
        # mostrar zero de débito contra mil de crédito, com o Diário
        # continuando a fechar e nenhuma das quatro categorias da
        # conferência acusando nada; trocar a natureza inverte o sinal de
        # todo o histórico da conta.
        #
        # Mesmo padrão de TRANSIÇÃO do guard de `aceita_lancamento` acima:
        # só dispara quando o valor GRAVADO no banco é diferente do que
        # está sendo salvo agora — uma conta já em estado legado (mudada
        # por `.update()` direto, contornando esta guarda) não é reportada
        # aqui de novo, e uma conta SEM movimento e SEM filhas continua
        # livre para editar `empresa`, `natureza` e `tipo` (critério 4: a
        # defesa não pode engessar o cadastro legítimo).
        #
        # Critério 11 da DL-023 (trilha), AUSÊNCIA DECLARADA: uma recusa
        # levantada aqui NÃO grava `RegistroAuditoria` — nada foi alterado,
        # `clean()` não tem acesso a `request`/`usuario`, e nenhum
        # `admin.py` deste projeto chama `registrar()` hoje (BL-244,
        # pacote 3, é quem endereça trilha genérica do admin). Só a
        # exclusão de regime tributário (RC-86/DE-039), que já gravava
        # antes desta etapa, continua gravando.
        if self.pk:
            original = (
                Conta.objects.filter(pk=self.pk)
                .values("empresa_id", "natureza", "tipo", "empresa__escritorio_id")
                .first()
            )
            if original is not None:
                tem_movimento = self.itens_lancamento.exists()
                tem_filhas = self.subcontas.exists()

                if original["empresa_id"] != self.empresa_id:
                    # BL-248 (achado P4, auditoria DL-023 rodada 1): nenhuma
                    # camada checava a fronteira de ESCRITÓRIO ao mover
                    # conta — só a de empresa. Uma conta LIVRE (sem
                    # movimento e sem filhas) podia ser movida para uma
                    # empresa de OUTRO escritório inteiro, porque o guard
                    # abaixo só recusa quando há movimento/filhas. Cruzar a
                    # fronteira de escritório é sempre recusado, MESMO SEM
                    # movimento — é a mesma fronteira que a Empresa.clean()
                    # protege para "trocar de escritório", e trocar a
                    # empresa de uma conta para um escritório diferente é a
                    # mesma operação por outra porta. Troca de empresa
                    # DENTRO do mesmo escritório continua sujeita só à
                    # regra de movimento/filhas abaixo (critério 4
                    # preservado: conta livre continua podendo mudar de
                    # empresa no mesmo escritório).
                    # BL-264 (achado P4/DoesNotExist da auditoria DL-023
                    # rodada 3, introduzido nesta etapa): `self.empresa.
                    # escritorio_id` resolve a FK via `self.empresa`, que
                    # levanta `Empresa.DoesNotExist` — não `ValidationError`
                    # — quando `empresa_id` aponta para um registro
                    # inexistente (`conta.empresa_id = 999999`). Isso não é
                    # alcançável pelo admin (o `ModelChoiceField` já recusa
                    # a FK antes de `clean()` rodar), mas é alcançável por
                    # qualquer `full_clean()` direto — candidato: a
                    # importação em lote da DL-010, que grava por
                    # `bulk_create`/lote e pode chamar `full_clean()` linha
                    # a linha. Mesmo padrão que `original` já usa duas
                    # linhas acima: `.values_list(...).first()` nunca
                    # levanta `DoesNotExist` — devolve `None` — e não
                    # carrega a linha inteira de `Empresa`.
                    escritorio_novo_id = (
                        Empresa.objects.filter(pk=self.empresa_id)
                        .values_list("escritorio_id", flat=True)
                        .first()
                    )
                    if original["empresa__escritorio_id"] != escritorio_novo_id:
                        raise ValidationError(
                            "Não é possível mudar esta conta para uma empresa de outro "
                            "escritório: contas não atravessam a fronteira de isolamento "
                            "entre escritórios pelo cadastro comum."
                        )
                    if tem_movimento or tem_filhas:
                        motivo = "lançamento próprio" if tem_movimento else "conta filha"
                        raise ValidationError(
                            f"Não é possível mudar a empresa desta conta: ela já tem {motivo} "
                            "gravado. O balancete da empresa de origem deixaria de fechar. "
                            "Estorne o movimento (ou mova as contas filhas) antes de "
                            "reclassificar, ou cadastre uma conta nova na empresa de destino."
                        )

                mudou_natureza = original["natureza"] != self.natureza
                mudou_tipo = original["tipo"] != self.tipo
                # BL-245 (achado P1, auditoria DL-023 rodada 1): a checagem
                # só roda quando natureza OU tipo de fato mudaram (short-
                # circuit: a consulta recursiva de `_tem_movimento_proprio_
                # ou_de_descendente` custa mais que `itens_lancamento.
                # exists()`, e não há razão para pagá-la numa gravação que
                # não toca nenhum dos dois campos). Movimento de QUALQUER
                # descendente conta, não só o próprio: é a correção do
                # requisito, não só do código — ver o docstring do método.
                mudou_algo = mudou_natureza or mudou_tipo
                if mudou_algo and self._tem_movimento_proprio_ou_de_descendente():
                    campo = (
                        "a natureza"
                        if mudou_natureza and not mudou_tipo
                        else (
                            "o tipo" if mudou_tipo and not mudou_natureza else "a natureza e o tipo"
                        )
                    )
                    raise ValidationError(
                        f"Não é possível mudar {campo} desta conta: ela ou uma conta "
                        "descendente já tem lançamento gravado — a troca inverteria o "
                        "sinal (ou a classificação) do histórico da conta ou do grupo no "
                        "Balancete. Estorne o movimento antes de reclassificar, ou "
                        "cadastre uma conta nova."
                    )


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
    # RC-77 / BL-205: a faixa de data também como validador de CAMPO, e não
    # só em `criar_lancamento`. Motivo (item 2 da DE-034 — o mesmo campo nas
    # outras superfícies): `full_clean()` é o que qualquer `ModelForm` chama,
    # inclusive o do admin, e o admin NÃO passa por `criar_lancamento`.
    # A regra mora em `apps.contabilidade.validators` (módulo sem ORM, que
    # este arquivo pode importar sem circularidade — `services.py` não
    # poderia ser importado aqui).
    #
    # Isto é defesa em profundidade, não a defesa principal: validador de
    # campo não roda em `objects.create()`, `bulk_create()` nem
    # `QuerySet.update()`, porque o ORM não chama `full_clean()`. Quem
    # garante a faixa no caminho de negócio é `criar_lancamento`; para o dado
    # gravado por fora dos dois, quem acende a luz é a categoria nova da
    # Conferência (`localizar_lancamentos_com_data_fora_da_faixa`).
    data = models.DateField("data", validators=[validar_data_de_lancamento_do_modelo])
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
    chave_idempotencia = models.CharField(
        "chave de idempotência",
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "Cabeçalho Idempotency-Key enviado pelo cliente ao criar o "
            "lançamento. Opcional: repetir o POST com a mesma chave, na "
            "mesma empresa, devolve o lançamento já criado em vez de "
            "duplicá-lo (BL-41). Não é derivada de data/histórico/itens — "
            "dois lançamentos idênticos podem ser legítimos em contabilidade."
        ),
    )
    chave_idempotencia_fingerprint = models.CharField(
        "impressão digital da chave de idempotência",
        max_length=64,
        null=True,
        blank=True,
        help_text=(
            "Hash SHA-256 (hexadecimal) do conteúdo do lançamento (data, "
            "histórico e itens) no momento em que a Idempotency-Key foi "
            "usada. Permite recusar com 409 quando a MESMA chave é "
            "reaproveitada para um conteúdo DIFERENTE, em vez de devolver "
            "silenciosamente o lançamento antigo como se fosse sucesso "
            "(achado de auditoria A2 do plano DL-007 — reaproveitar a chave "
            "para outra coisa é 'corrupção por omissão', que não aparece na "
            "conciliação)."
        ),
    )

    class Meta:
        verbose_name = "lançamento contábil"
        verbose_name_plural = "lançamentos contábeis"
        ordering = ["-data", "-criado_em"]
        constraints = [
            # Defesa de banco (DE-008, camada 1) para o achado BL-41: um
            # lançamento só pode ser estornado uma vez. `estorno_de` é nulo em
            # todo lançamento que não é estorno de nada — a `condition`
            # restringe a unicidade só às linhas que efetivamente referenciam
            # um original, para que múltiplos NULL continuem permitidos (do
            # contrário nem seria necessário declarar a condição, mas isso
            # torna explícito que a regra é "no máximo um estorno por
            # original", não "no máximo um NULL").
            models.UniqueConstraint(
                fields=["estorno_de"],
                condition=models.Q(estorno_de__isnull=False),
                name="estorno_de_unico",
            ),
            # Defesa de banco para a idempotência opcional de criação (BL-41):
            # a mesma chave só precisa ser única dentro da mesma empresa, para
            # que a mesma chave usada por clientes de empresas diferentes não
            # colida entre si. NULL (ausência de chave) nunca conflita.
            models.UniqueConstraint(
                fields=["empresa", "chave_idempotencia"],
                condition=models.Q(chave_idempotencia__isnull=False),
                name="chave_idempotencia_unica_por_empresa",
            ),
        ]

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

    def clean(self):
        # Achado 10 da auditoria (rodada 1) e achado novo 6 (rodada 2, BL-79):
        # um `ItemLancamento` pode apontar para uma `conta` de uma empresa e
        # um `lancamento` de OUTRA — quando isso existe, o histórico e o
        # nome de conta de um cliente aparecem no Diário/Balancete de outro
        # (a defesa em CÓDIGO já existe em `apurar_razao`/`apurar_balancete`,
        # que filtram por `lancamento__empresa` além de `conta__empresa` —
        # DE-021). `criar_lancamento` já recusa este estado no caminho
        # normal da API (`conta.empresa_id != empresa.id`); esta checagem
        # aqui é a MESMA regra na camada de conveniência do Django admin/
        # formulários (DE-008), porque o DRF e `.objects.create()` não
        # chamam `full_clean()`. A garantia de BANCO (constraint que
        # atravesse as três tabelas) fica para a DL-016 (DE-021, BL-78) —
        # exige migração de esquema.
        #
        # Só valida quando os DOIS lados já têm empresa resolvida: um item
        # em construção sem `conta` ou sem `lancamento` ainda atribuídos
        # (formulário em preenchimento) não deveria estourar aqui — o campo
        # obrigatório do model já recusaria a ausência na gravação.
        if (
            self.conta_id
            and self.lancamento_id
            and self.conta.empresa_id != self.lancamento.empresa_id
        ):
            raise ValidationError(
                "A conta deste item deve pertencer à mesma empresa do lançamento "
                f"({self.conta} é de uma empresa; o lançamento é de outra)."
            )

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
