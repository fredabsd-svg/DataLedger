from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import connection, models

from apps.contabilidade.validators import validar_data_de_lancamento_do_modelo
from apps.empresas.models import Empresa


class LancamentoImutavelError(Exception):
    """Levantado ao tentar alterar ou excluir um lançamento já efetivado."""


class EstadoCompetencia(models.TextChoices):
    """Ciclo de vida da competência contábil de uma empresa.

    ⚠️ **Decisão da fatia 1 da DL-016, registrada aqui porque o campo já
    existia com um plano de transição diferente do que foi implementado**
    (o comentário anterior previa `aberta -> em_encerramento -> encerrada`,
    de um plano F3/F4 que a DE-050 substituiu): o plano vigente
    (`docs/planos/DL-016-competencia-e-fechamento.md`, seção "Fatia 1")
    manda fechar com a transição DIRETA `aberta -> encerrada`. `EM_ENCERRAMENTO`
    é, portanto, **RESERVADO e NÃO ALCANÇÁVEL** por nenhum código de produção
    desta fatia — nenhum service escreve este valor. Ele continua declarado
    no enum só para não quebrar a migração já aplicada (a coluna já existe
    com estes três valores em `choices`) e para deixar um nome pronto **se**
    um dia o produto precisar de um fechamento em duas etapas (ex.: uma
    janela de conferência antes de consolidar) — decisão de produto que
    ninguém tomou ainda. `test_dl016_fatia1_fechamento_reabertura_entrega.py`
    tem um teste que prova esta reserva: nenhuma chamada aos services de
    fechar/reabrir/entregar desta fatia deixa uma `Competencia` em
    `EM_ENCERRAMENTO`.

    O estado é persistido como texto curto, não como FK, porque o domínio é
    fechado e a lista de valores é do próprio projeto (RC do DL-016).
    """

    ABERTA = "aberta", "Aberta"
    EM_ENCERRAMENTO = "em_encerramento", "Em encerramento"
    ENCERRADA = "encerrada", "Encerrada"


class Competencia(models.Model):
    """Um mês contábil de uma empresa — mês em que lançamentos podem existir.

    Existe exatamente uma linha por (empresa, ano, mês) — a unicidade é
    defendida por `UniqueConstraint` no `Meta` (camada 1 da DE-008). F1 só
    cria a tabela; F2 é responsável por GARANTIR que, ao chegar o primeiro
    lançamento de um mês, exista uma `Competencia` correspondente (estratégia
    T1 do plano de execução: `Competencia.objects.get_or_create(...)` dentro
    de `criar_lancamento`, opção A confirmada pelo Fred). F5 cuida do
    backfill de competências anteriores ao deploy da DL-016.

    O par (ano, mês) foi preferido a um único `DateField` porque:
    - Validar a faixa de mês (1..12) e de ano (1970..2999) vira
      `CheckConstraint`, não regra Python que pode ser esquecida em outro
      caminho de escrita.
    - Exibir "novembro de 2026" é trivial sem precisar de formatação de data
      a cada leitura.
    - Não há nada a ganhar com um único campo `DATE`: a data do PRIMEIRO dia
      do mês seria convencional, e a regra de "mês fechado" sempre lê o par
      (ano, mês), não a data. Manter o par explícito reduz surpresa.

    ## Fatia 1 da DL-016 (fechamento, reabertura, entrega)

    Quatro campos novos, todos `null=True`/`blank=True` (nenhuma competência
    existente muda de valor com a migração — critério 11 do plano):

    - `fechada_em`/`fechada_por`: quando `estado == ENCERRADA`, registram
      QUEM fechou e QUANDO (além do registro de auditoria em
      `apps.auditoria`, que é a trilha completa — estes dois campos existem
      para responder "quem fechou este mês" sem precisar consultar a
      trilha). Reabrir (`apps.contabilidade.services.reabrir_competencia`)
      LIMPA os dois: eles descrevem o fechamento ATUAL, não o histórico —
      quem quer o histórico completo (inclusive fechamentos/reaberturas
      anteriores) consulta `RegistroAuditoria`.
    - `entregue_em`/`entregue_por`: **fato datado**, não um quarto estado
      (decisão do `arquiteto-senior`, RC-101). Diferente de
      `fechada_em`/`fechada_por`, estes DOIS campos NUNCA são limpos por
      nenhum service desta fatia — uma vez entregue, a competência
      permanece "entregue" para sempre (a trava de RC-101 depende disso:
      reabrir uma competência entregue é recusado justamente PORQUE o fato
      "já foi entregue" não se desfaz). "Marcar como entregue" pode ser
      chamado mais de uma vez (a entrega "pode repetir-se" — balancete ao
      cliente, depois ECD transmitida, no texto do plano): cada chamada
      apenas ATUALIZA os dois campos para o evento mais recente; se um dia
      for preciso o HISTÓRICO de todas as entregas (não só a última), isso
      vira modelo próprio, sem refazer esta trava (nota do plano).
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="competencias")
    ano = models.IntegerField("ano")
    mes = models.IntegerField("mês")
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoCompetencia.choices,
        default=EstadoCompetencia.ABERTA,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    fechada_em = models.DateTimeField(
        "fechada em",
        null=True,
        blank=True,
        help_text=(
            "Preenchido quando o estado passa a 'encerrada'. Limpo se a competência for reaberta."
        ),
    )
    fechada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="fechada por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Usuário que fechou a competência (RC do DL-016, critério 3 da fatia 1).",
    )
    # RC-101 / decisão do arquiteto-senior: "entregue" é um FATO DATADO,
    # nunca um quarto estado de `estado`. Ver o docstring da classe para o
    # contrato completo (inclusive por que estes dois campos NUNCA são
    # limpos por nenhum service, ao contrário de `fechada_em`/`fechada_por`).
    entregue_em = models.DateTimeField(
        "entregue em",
        null=True,
        blank=True,
        help_text=(
            "Data/hora em que o documento desta competência (balancete, ECD etc.) foi "
            "entregue ao cliente. Uma vez preenchido, a reabertura da competência é "
            "sempre recusada (RC-101) — o ajuste passa a ser feito no mês aberto."
        ),
    )
    entregue_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="entregue por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Usuário que marcou a competência como entregue.",
    )

    class Meta:
        verbose_name = "competência"
        verbose_name_plural = "competências"
        ordering = ["-ano", "-mes"]
        constraints = [
            # DE-008 camada 1: no banco, só pode haver uma competência por
            # (empresa, ano, mês). Sem isso, F2 (get_or_create) precisa
            # confiar em índice de aplicação, e qualquer INSERT direto via
            # admin/shell contorna.
            models.UniqueConstraint(
                fields=["empresa", "ano", "mes"], name="competencia_unica_por_empresa_ano_mes"
            ),
            # Faixa do mês é parte do invariante, não convenção: 0 e 13 não
            # existem no calendário gregoriano e, se aparecerem, quebram
            # silenciosamente a apuração (consultas que assumem 1..12 vão
            # tratar `0` como "antes de janeiro" sem avisar).
            models.CheckConstraint(
                condition=models.Q(mes__gte=1) & models.Q(mes__lte=12),
                name="competencia_mes_entre_1_e_12",
            ),
            # Faixa de ano arbitrada em 1970..2999: recusa anos absurdos
            # (0, 10000) sem fechar a porta para migrações contábeis muito
            # antigas — escritórios que digitalizam livros dos anos 80 não
            # cabem em `ano >= 2000`.
            models.CheckConstraint(
                condition=models.Q(ano__gte=1970) & models.Q(ano__lte=2999),
                name="competencia_ano_entre_1970_e_2999",
            ),
        ]

    def __str__(self):
        # Exibição em PT-BR sem depender de locale do servidor (que pode
        # estar em en_US.UTF-8 em produção): a lista está fixa e cobre os
        # 12 meses. Em branco, devolve só o ano — não acontece na prática
        # porque a CheckConstraint acima recusa `mes` fora de 1..12.
        meses = [
            "",
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        nome_mes = meses[self.mes] if 1 <= self.mes <= 12 else f"mês {self.mes}"
        return f"{nome_mes} de {self.ano} — {self.empresa}"


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
                .values("empresa_id", "natureza", "tipo", "conta_pai_id", "empresa__escritorio_id")
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
                    # rodada 3, introduzido nesta etapa): a primeira versão
                    # deste guard lia `self.empresa.escritorio_id`, que
                    # resolve a FK via `self.empresa` e levanta `Empresa.
                    # DoesNotExist` — não `ValidationError` — quando
                    # `empresa_id` aponta para um registro inexistente
                    # (`conta.empresa_id = 999999`). Isso não é alcançável
                    # pelo admin (o `ModelChoiceField` já recusa a FK antes
                    # de `clean()` rodar), mas é alcançável por qualquer
                    # `full_clean()` direto — candidato: a importação em
                    # lote da DL-010, que pode chamar `full_clean()` linha a
                    # linha. Mesmo padrão que `original` já usa duas linhas
                    # acima: `.values_list(...).first()` nunca levanta
                    # `DoesNotExist` — devolve `None` — e não carrega a
                    # linha inteira de `Empresa`.
                    #
                    # Segunda correção, ainda na rodada 4: a versão anterior
                    # deste guard tratava `escritorio_novo_id is None` como
                    # "empresa de outro escritório" — mensagem que nomeia a
                    # causa ERRADA quando o que houve foi FK apontando para
                    # registro inexistente. É a mesma família de defeito da
                    # BL-142 (comentário falso) e da BL-246 (cobertura
                    # declarada que não existia): afirmação que não
                    # corresponde ao que aconteceu — só que agora na
                    # mensagem que o contador lê, não num comentário interno.
                    # Os dois casos são distintos e têm mensagem própria.
                    #
                    # Rodada 6 (achado P1 da auditoria focada): a sonda do
                    # auditor comparou três revisões e achou que a BL-264
                    # fechou a forma MENOS provável (`empresa_id` grande
                    # demais, `2**70`, já tratado acima por devolver `None`
                    # do `.filter(...).first()`) e deixou aberta a MAIS
                    # provável — `empresa_id` de um TIPO que a coluna
                    # inteira de `Empresa.pk` não aceita (`"abc"`, `"1e3"`,
                    # `"  "`, `[]`). O candidato que o comentário acima já
                    # nomeia (importação em lote da DL-010, `full_clean()`
                    # linha a linha de uma planilha) é justamente onde texto
                    # numa coluna numérica é mais comum do que um id inteiro
                    # que só não existe. Sem este `try`, `Empresa.objects.
                    # filter(pk=self.empresa_id)` levanta `ValueError`
                    # (string) ou `TypeError` (lista) na hora de montar a
                    # consulta — antes de `.first()` devolver `None` — e
                    # esse erro NÃO é `ValidationError`: vaza como 500 em
                    # qualquer `full_clean()` direto, o mesmo dano que a
                    # BL-264 original já tinha para FK inexistente. Mensagem
                    # PRÓPRIA (terceira causa, terceira mensagem — mesmo
                    # princípio de "uma causa, uma mensagem" das duas
                    # acima): não é "não existe" (isso pressupõe um
                    # identificador válido que não bate com nenhum
                    # registro) nem "outro escritório" (pressupõe um
                    # registro real).
                    #
                    # `empresa_id = None` é uma QUARTA causa, e não é papel
                    # deste guard reportá-la: `empresa` não é `null=True`
                    # (linha ~37), então `clean_fields()` — chamado por
                    # `full_clean()` ANTES de `clean()`, e que continua
                    # rodando mesmo se `clean()` também levantar erro, os
                    # dois acumulam no mesmo dicionário — já acusa a
                    # ausência com a mensagem padrão de campo obrigatório.
                    # Antes desta linha, o valor caía direto no `try`
                    # abaixo: `Empresa.objects.filter(pk=None)` não levanta
                    # nada, devolve `None` de `.first()` como qualquer id
                    # inexistente, e este guard relançava "a empresa
                    # informada não existe" — mensagem que nomeia a causa
                    # errada (nada foi *informado*; é a mesma família de
                    # defeito de cima, agora entre "ausente" e
                    # "inexistente"). Não relançar aqui evita a mensagem
                    # duplicada/confusa sem abrir mão da recusa: o campo
                    # nulo já barra a gravação por outra via.
                    if self.empresa_id is None:
                        return
                    try:
                        escritorio_novo_id = (
                            Empresa.objects.filter(pk=self.empresa_id)
                            .values_list("escritorio_id", flat=True)
                            .first()
                        )
                    except (TypeError, ValueError):
                        raise ValidationError(
                            "Não é possível mudar esta conta: o identificador de "
                            "empresa informado não é válido."
                        ) from None
                    if escritorio_novo_id is None:
                        raise ValidationError(
                            "Não é possível mudar esta conta: a empresa informada não "
                            "existe. Confira o identificador enviado."
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

        # BL-261 (terceiro caminho da BL-83, achado novo 1 da auditoria DL-023
        # rodada 3): o guard acima protege natureza e tipo da própria conta e
        # o guard de empresa protege o reparentamento entre empresas, mas o
        # admin deixava trocar SOMENTE `conta_pai` de uma conta com movimento
        # para um grupo de natureza oposta. Efeito medido: o Balancete da
        # empresa continuava fechando (débito = crédito), mas a linha do
        # grupo de destino mostrava -R$ 1.000,00 enquanto a do grupo de
        # origem mostrava R$ 0,00 — e nenhuma das cinco categorias da
        # conferência acusava. A correção segue o MESMO PADRÃO de transição
        # do guard de natureza/tipo acima: só dispara quando o GRAVADO é
        # diferente do novo E a conta (ou descendente) tem movimento.
        if (
            self.pk
            and original["conta_pai_id"] != self.conta_pai_id
            and self.conta_pai_id is not None
            and self._tem_movimento_proprio_ou_de_descendente()
        ):
            natureza_pai_novo = (
                Conta.objects.filter(pk=self.conta_pai_id)
                .values_list("natureza", flat=True)
                .first()
            )
            if natureza_pai_novo is not None and natureza_pai_novo != original["natureza"]:
                raise ValidationError(
                    "Não é possível reparentar esta conta para um grupo de natureza "
                    "oposta: ela ou uma conta descendente já tem lançamento gravado. "
                    "O movimento herdado mudaria de lado no Balancete, sem que nenhum "
                    "lançamento novo fosse gerado. Estorne o movimento (ou mova as "
                    "contas filhas) antes de reclassificar, ou cadastre uma conta "
                    "nova."
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
    # DL-016 (F1): ponteiro para a competência (mês contábil) em que este
    # lançamento está sendo registrado. Nullable até F5 (backfill) — D1
    # confirmada pelo Fred. Em F2, `criar_lancamento` preenche via
    # `Competencia.objects.get_or_create(...)` a partir de `self.data`
    # (estratégia T1=A). A constraint `unique(empresa, ano, mes)` em
    # `Competencia.Meta` é a defesa de unicidade da própria FK.
    #
    # `on_delete=PROTECT` por dois motivos:
    # 1. Mesmo princípio de `Conta.empresa` (BL-83): apagar uma competência
    #    com lançamentos gravados quebraria o vínculo contábil sem aviso.
    # 2. F3/F4 vão criar uma API de FECHAMENTO e REABERTURA — não de
    #    exclusão. Se um dia for preciso apagar uma competência vazia (LGPD,
    #    RC-52, BL-66), isso vira caso explícito em F+, não efeito
    #    colateral de um admin distraído.
    competencia = models.ForeignKey(
        "Competencia",
        on_delete=models.PROTECT,
        related_name="lancamentos",
        null=True,
        blank=True,
        verbose_name="competência",
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
            # BL-455/A5 (achado pré-existente, corrigido na rodada 2 de
            # auditoria da fatia 1 — o `arquiteto-senior` autorizou tocar
            # `apps/core/restricoes.py` para fechar esta correção): a
            # `CheckConstraint` que a migração 0005 adicionou ao BANCO por
            # `AddConstraint` avulso (hand-written) nunca tinha sido
            # DECLARADA aqui, em `Meta.constraints` — divergência que fazia
            # `manage.py makemigrations --check` reprovar em HEAD limpo
            # (medido, não presumido) e que, se alguém aplicasse o resultado
            # de um `makemigrations` real, DERRUBARIA esta defesa de banco
            # contra `empresa_id NULL` por INSERT direto (DE-051). A
            # declaração agora bate com o banco; nenhuma migração nova foi
            # necessária — a 0005 já registrou esta constraint no ESTADO de
            # migração (`manage.py makemigrations --check --dry-run`
            # responde "No changes detected"; BL-465, achado B3 da rodada 2
            # de auditoria: a versão anterior deste comentário citava uma
            # "migração corretiva (0007)" que nunca existiu — mesma família
            # do BL-460, comentário afirmando um artefato que não existe).
            # Registrada também em
            # `apps/core/restricoes.py::RESTRICOES_SEM_CAMINHO_DE_CLIENTE`
            # (exigido pela varredura de `apps/core/tests/test_dl019_
            # varredura_de_restricoes.py`).
            models.CheckConstraint(
                condition=models.Q(empresa_id__isnull=False),
                name="ck_lancamentocontabil_empresa_not_null",
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
