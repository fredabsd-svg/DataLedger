from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import connection, models, transaction
from django.db.models.functions import ExtractMonth, ExtractYear

from apps.contabilidade.validators import validar_data_de_lancamento_do_modelo
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA


class LancamentoImutavelError(Exception):
    """Levantado ao tentar alterar ou excluir um lançamento já efetivado."""


# DL-065 (BL-550): `code` do `ValidationError` levantado por `Conta.clean()`
# quando trocar (ou remover) a classificação da DLPA ou da DMPL reescreveria a
# demonstração de uma competência já encerrada ou entregue.
#
# Existe para que os SERVIÇOS de classificação consigam distinguir ESTA
# recusa das demais e respondam **409** (conflito de estado — o mesmo
# tratamento de `CompetenciaEncerrada`) em vez de 400 (entrada inválida). O
# admin, que passa pelo mesmo `clean()` sem conhecer o código, continua
# mostrando o erro no formulário.
#
# Uma regra, um código, UMA mensagem (escrita no modelo): duas traduções com
# textos próprios divergem assim que alguém edita uma delas.
CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO = "classificacao_de_periodo_fechado"


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
        # DL-052: usuário se desativa, não se apaga — a autoria do
        # fechamento é parte da trilha do período (PROTECT, era SET_NULL).
        on_delete=models.PROTECT,
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
        # DL-052: idem `fechada_por` (PROTECT, era SET_NULL).
        on_delete=models.PROTECT,
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


class ClassificacaoPatrimonial(models.TextChoices):
    """Classificação circulante × não circulante do Balanço Patrimonial —
    DL-033, fatia 1. Fonte oficial (**RC-106**, com texto literal em
    `docs/projeto/requisitos.md`): Lei 6.404/1976, art. 178, §1º e §2º
    (redação da Lei 11.941/2009), e NBC TG 26 (R5), item 60.

    No ATIVO a lei nomeia QUATRO subgrupos do não circulante (art. 178
    §1º, II) — **não são dois grupos, são dois grupos e quatro
    subdivisões** (o erro que o plano da DL-033 avisa para não cometer). No
    PASSIVO não há subdivisão do não circulante: a lei separa só passivo
    circulante de passivo não circulante — o TERCEIRO grupo do passivo,
    Patrimônio Líquido, fica FORA desta classificação (não é circulante
    nem não circulante; é o terceiro grupo, ao lado dos outros dois). Por
    isso não há valor aqui para Patrimônio Líquido, Receita nem Despesa —
    os dois últimos não fazem parte do Balanço Patrimonial.

    ⚠️ **Decisão de modelagem — HI-18/PE-64 (`arquiteto-senior`):** este é
    um CAMPO da conta, propriedade FIXA — não é calculado por data (a
    norma é relativa à data do balanço, mas o produto não recalcula
    sozinho). A passagem de longo prazo para curto prazo se faz por
    LANÇAMENTO de reclassificação (conta nova + transferência do saldo),
    nunca editando este campo de uma conta já movimentada — ver a guarda
    em `Conta.clean()`, no mesmo molde do BL-83/BL-245/BL-261
    (natureza/tipo). **Reversível com custo baixo** se o Fred (PE-64)
    responder que o escritório dele edita a própria conta em vez de
    lançar: o campo continua, e só a guarda muda (de "recusa" para
    "versiona").

    `Conta.classificacao_patrimonial` é `null=True`: conta existente (e
    conta nova de Patrimônio Líquido/Receita/Despesa) nasce SEM
    classificação — o produto NUNCA infere a partir do código ou do nome
    da conta (a classe de erro do achado A2/BL-475 da DL-032, que reprovou
    a etapa anterior por decidir grupo pela posição na árvore). É o
    contador quem classifica; a camada de saldos só DECLARA o que falta
    (critério 5 do plano DL-033) — nunca corrige, nunca presume.
    """

    ATIVO_CIRCULANTE = "ativo_circulante", "Ativo circulante"
    ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO = (
        "ativo_nao_circulante_realizavel_a_longo_prazo",
        "Ativo não circulante — realizável a longo prazo",
    )
    ATIVO_NAO_CIRCULANTE_INVESTIMENTOS = (
        "ativo_nao_circulante_investimentos",
        "Ativo não circulante — investimentos",
    )
    ATIVO_NAO_CIRCULANTE_IMOBILIZADO = (
        "ativo_nao_circulante_imobilizado",
        "Ativo não circulante — imobilizado",
    )
    ATIVO_NAO_CIRCULANTE_INTANGIVEL = (
        "ativo_nao_circulante_intangivel",
        "Ativo não circulante — intangível",
    )
    PASSIVO_CIRCULANTE = "passivo_circulante", "Passivo circulante"
    PASSIVO_NAO_CIRCULANTE = "passivo_nao_circulante", "Passivo não circulante"


# Fonte ÚNICA (DE-056/critério 1 do plano DL-033) de qual `TipoConta` cada
# `ClassificacaoPatrimonial` pertence — usada pela guarda de consistência em
# `Conta.clean()` logo abaixo. Existe num dict, ao lado do enum que ele
# descreve, para (a) nunca comparar por PREFIXO DE STRING (frágil a rename
# do valor) e (b) permitir a um teste derivado reprovar se um valor novo de
# `ClassificacaoPatrimonial` nascer sem entrada aqui — o mesmo padrão que a
# DL-032 já usa para `TipoConta.values` em `apurar_saldos`.
TIPO_DA_CLASSIFICACAO_PATRIMONIAL = {
    ClassificacaoPatrimonial.ATIVO_CIRCULANTE: TipoConta.ATIVO,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO: TipoConta.ATIVO,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS: TipoConta.ATIVO,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO: TipoConta.ATIVO,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL: TipoConta.ATIVO,
    ClassificacaoPatrimonial.PASSIVO_CIRCULANTE: TipoConta.PASSIVO,
    ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE: TipoConta.PASSIVO,
}


# BL-496 (RESSALVA R1 da rodada 2 de auditoria da DL-033, opção (b) adotada
# no critério 1 do plano DL-034 — DE-068): a natureza NATURAL de cada
# `TipoConta` que participa da separação circulante/não circulante —
# devedora no Ativo, credora no Passivo (Lei 6.404/76; a mesma convenção
# que o docstring de `Conta`, acima, já registra como "regra geral", que a
# MODELAGEM não impõe de propósito, porque conta retificadora existe).
#
# Usada por `apurar_saldos` (services.py) para somar um nó TOPO
# classificado normalizando o sinal por ESTA natureza, em vez de pela
# natureza CADASTRADA da própria conta (`Conta.natureza`/`linha["natureza"]`
# do Balancete). Sem isto, duas contas IRMÃS com natureza cadastrada
# diferente, ambas classificadas no MESMO grupo — ex.: "Clientes" devedora
# (1.220,00) e "(-) PDD" credora (50,00), ambas `ativo_circulante` — somavam
# cada saldo já assinado pela PRÓPRIA natureza (1.220,00 + 50,00 = 1.270,00)
# em vez de aplicar UMA natureza sobre o valor combinado, como a regra
# única de saldo (DE-020) já exige para hierarquia — o correto é
# 1.220,00 − 50,00 = 1.170,00. Ver a RESSALVA R1 (cenário V1d) e o critério
# 1 da DL-034.
#
# Só tem entrada para os `TipoConta` que participam da classificação
# (exatamente `TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()`, conferido pelo
# teste derivado `test_mapa_natureza_natural_cobre_exatamente_os_tipos_
# classificaveis`) — Patrimônio Líquido, Receita e Despesa ficam de fora de
# propósito, no mesmo espírito de `residuo_por_tipo`: a pergunta "qual é o
# lado natural deste tipo, para o Balanço Patrimonial" não se aplica a eles
# aqui.
NATUREZA_NATURAL_DO_TIPO = {
    TipoConta.ATIVO: NaturezaConta.DEVEDORA,
    TipoConta.PASSIVO: NaturezaConta.CREDORA,
}


# DL-062 (BL-604): a natureza NATURAL de TODOS os `TipoConta`, para a soma dos
# TOTAIS do Balanço (`totais_por_tipo`, em `apurar_saldos`) — o quinto tipo
# que faltava para a equação contábil fechar.
#
# **O defeito que este mapa corrige, medido em 04/10/2026 (BL-604):** o sinal
# do saldo vem da natureza da conta que o consolida (regra única de saldo,
# DE-020). Uma conta retificadora aninhada ("(-) Prejuízos Acumulados",
# "(-) Ações em Tesouraria") herda o sinal do GRUPO e sai correto; mas
# cadastrada como RAIZ — `conta_pai is None`, sem ancestral do grupo — não há
# grupo que aplique a natureza credora do PL: a natureza DEVEDORA dela assina
# o próprio saldo, e `totais_por_tipo` somava esse valor como se fosse um
# acréscimo. No caso de referência, PL = 117.000,00 quando o correto é
# 113.000,00, e a equação `ativo = passivo + PL` fechava com −4.000,00 —
# **sem veto nenhum**: o Balanço saía para o cliente errado. A mesma falha
# atinge RAIZ devedora de RECEITA e RAIZ credora de DESPESA (medido: equação
# em −200,00), então a correção é da CLASSE, não do caso do PL.
#
# **Por que este mapa é NOVO, e não o `NATUREZA_NATURAL_DO_TIPO` estendido:**
# aquele responde a uma pergunta diferente — "qual o lado natural deste tipo
# para a classificação circulante/não circulante" — e o teste derivado
# `test_mapa_natureza_natural_cobre_exatamente_os_tipos_classificaveis` exige
# que as chaves sejam exatamente `TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()`.
# Estendê-lo quebraria esse teste por motivo alheio à DL-033. Mesmo motivo que
# separou `NATUREZA_NATURAL_DO_TIPO_DRE` (abaixo) do dict do Balanço.
#
# **Por que PELA NATUREZA e não pela coluna da DMPL:** o sinal do total é
# derivação da equação contábil, e a coluna (`classificacao_dmpl`) é uma
# classificação opcional, sem direção declarada em nenhum símbolo do código.
# Implementar por ela criaria uma segunda fonte de verdade para o mesmo sinal.
NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO = {
    TipoConta.ATIVO: NaturezaConta.DEVEDORA,
    TipoConta.PASSIVO: NaturezaConta.CREDORA,
    TipoConta.PATRIMONIO_LIQUIDO: NaturezaConta.CREDORA,
    TipoConta.RECEITA: NaturezaConta.CREDORA,
    TipoConta.DESPESA: NaturezaConta.DEVEDORA,
}


class GrupoDaLei(models.TextChoices):
    """Os QUATRO grupos que a Lei 6.404/76, art. 178, realmente nomeia para
    fins de separação circulante/não circulante (BL-490, achado A5 da
    auditoria da DL-033): ativo circulante, ativo não circulante — o
    GUARDA-CHUVA dos quatro subgrupos do art. 178 §1º II (realizável a
    longo prazo, investimentos, imobilizado, intangível) —, passivo
    circulante e passivo não circulante. **Não são sete grupos: são
    quatro** — `ClassificacaoPatrimonial` tem sete valores porque o Ativo
    Não Circulante se subdivide em código (para a conta poder apontar para
    o subgrupo exato), mas o SUBTOTAL que a lei manda imprimir no Balanço é
    só "Ativo Não Circulante", sobre a soma dos quatro.
    """

    ATIVO_CIRCULANTE = "ativo_circulante", "Ativo circulante"
    ATIVO_NAO_CIRCULANTE = "ativo_nao_circulante", "Ativo não circulante"
    PASSIVO_CIRCULANTE = "passivo_circulante", "Passivo circulante"
    PASSIVO_NAO_CIRCULANTE = "passivo_nao_circulante", "Passivo não circulante"


# Segundo mapa derivado (BL-490): dos SETE valores de `ClassificacaoPatrimonial`
# para os QUATRO grupos que a lei nomeia — existe para que NENHUM código nem
# teste precise comparar por PREFIXO DE STRING (`startswith("ativo")`, o
# antipadrão que o achado apontou no próprio teste do critério 4) para somar
# "todo o Ativo Não Circulante", por exemplo. Ao lado do enum que descreve,
# como `TIPO_DA_CLASSIFICACAO_PATRIMONIAL` acima.
GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL = {
    ClassificacaoPatrimonial.ATIVO_CIRCULANTE: GrupoDaLei.ATIVO_CIRCULANTE,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO: (
        GrupoDaLei.ATIVO_NAO_CIRCULANTE
    ),
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS: GrupoDaLei.ATIVO_NAO_CIRCULANTE,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO: GrupoDaLei.ATIVO_NAO_CIRCULANTE,
    ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL: GrupoDaLei.ATIVO_NAO_CIRCULANTE,
    ClassificacaoPatrimonial.PASSIVO_CIRCULANTE: GrupoDaLei.PASSIVO_CIRCULANTE,
    ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE: GrupoDaLei.PASSIVO_NAO_CIRCULANTE,
}


class ClassificacaoDre(models.TextChoices):
    """Linha da Demonstração do Resultado do Exercício — DL-045, fatia 1
    (RC-118). Fonte: Lei 6.404/76, art. 187 e art. 175, e NBC TG 26 (R5)
    item 82, NBC TG 1000 (R1) item 5.7 e ITG 1000 (2022) — lidas na fonte
    primária (Planalto, Câmara, PDFs do CFC) em 2026-09-26, PE-70
    respondida (ver `docs/projeto/requisitos.md`). Mesmo molde do
    `ClassificacaoPatrimonial` (circulante × não circulante, DL-033):
    campo FIXO da conta, `null=True`, nunca inferido do código ou do nome
    — é o contador quem classifica, a camada de apuração só DECLARA o
    que falta (mesmo padrão que `contas_sem_classificacao_patrimonial`
    já usa).

    ⚠️ **Confirmação do precedente da DL-033, pedida pela tarefa desta
    etapa:** `ClassificacaoPatrimonial` NÃO tem restrição de banco (só
    migração `AddField`, sem `CheckConstraint` nem gatilho) — a única
    guarda de "classificação compatível com o tipo da conta" mora em
    `Conta.clean()` (roda em `full_clean()`, nunca em `.save()` puro nem
    em `.update()` em massa). `ClassificacaoDre` segue o MESMO desenho,
    de propósito: nenhuma restrição de banco nova, só a guarda de
    `clean()` abaixo — consistente com o resto do campo irmão.

    ⚠️ **HI-29 (revista depois da PE-70): resultado financeiro
    DESTACADO, não dentro do "resultado operacional".** A letra do art.
    187, III embutiria o financeiro no operacional, mas a NBC TG 26 item
    82 e a NBC TG 1000 item 5.7 destacam receitas/despesas financeiras
    como um subtotal próprio, e a ITG 1000 (2022) traz o mesmo modelo —
    é a estrutura que este enum e a apuração (`services.py`) seguem. O
    Fred ainda confirma a apresentação (registrado no plano); a ordem
    exata dos subtotais mora isolada em `_LINHAS_ANTES_DO_RESULTADO_FINANCEIRO`/
    `_LINHAS_DO_RESULTADO_FINANCEIRO` (services.py), para trocar fácil
    se ele decidir diferente.

    ⚠️ **Mapeamento linha → `TipoConta` esperado é uma INFERÊNCIA minha,
    não texto literal do plano** (reportado ao arquiteto, não decidido
    sozinho): o plano lista as treze linhas mas não diz qual `TipoConta`
    cada uma espera — diferente da DL-033, onde a própria Lei (art. 178,
    §1º/§2º) nomeia Ativo/Passivo linha a linha. Seguindo o padrão RC-61
    (retificadora dentro do MESMO tipo/grupo — ex.: "(-) Depreciação
    acumulada" dentro do Ativo, natureza oposta) mapeei "deduções da
    receita" como tipo RECEITA (retificadora da receita bruta) e todas
    as linhas de custo/despesa/provisão/participações como tipo DESPESA
    — ver `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`, abaixo. **Decisão do
    arquiteto, 26/09/2026, revisando a inferência inicial**: mapeamento
    aceito como estava, com UMA correção — "resultado de equivalência
    patrimonial" pode ser GANHO ou PERDA, então aceita conta de tipo
    RECEITA **ou** DESPESA (a perda de equivalência costuma ficar
    classificada no grupo de despesas). O sinal exibido não muda com
    isso: continua seguindo a natureza NATURAL da LINHA (credora, ver
    `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE`), então uma conta de DESPESA
    classificada nesta linha soma NEGATIVO ao resultado de equivalência.
    "Deduções da receita" (RECEITA) e "participações" (DESPESA) seguem
    como estavam. **Confirmadas em requisitos.md** (RC-123 e RC-122,
    26/09/2026, delegação do Fred ao arquiteto-senior sobre as dúvidas
    D1-D6 da rodada 1 de auditoria, conferidas nos manuais e normas) —
    deixaram de ser inferência minha; se o Fred quiser revisitar, ainda
    é só trocar o valor no dict, nada mais depende da escolha em si.
    """

    RECEITA_BRUTA = "receita_bruta", "Receita bruta de vendas e serviços"
    DEDUCOES_DA_RECEITA = (
        "deducoes_da_receita",
        "Deduções da receita (impostos, devoluções e abatimentos)",
    )
    CUSTO = "custo", "Custo (CMV/CPV/CSP)"
    DESPESAS_COM_VENDAS = "despesas_com_vendas", "Despesas com vendas"
    DESPESAS_GERAIS_E_ADMINISTRATIVAS = (
        "despesas_gerais_e_administrativas",
        "Despesas gerais e administrativas",
    )
    OUTRAS_RECEITAS = "outras_receitas", "Outras receitas"
    OUTRAS_DESPESAS = "outras_despesas", "Outras despesas"
    OUTRAS_DESPESAS_OPERACIONAIS = (
        "outras_despesas_operacionais",
        "Outras despesas operacionais",
    )
    RESULTADO_EQUIVALENCIA_PATRIMONIAL = (
        "resultado_equivalencia_patrimonial",
        "Resultado de equivalência patrimonial",
    )
    RECEITAS_FINANCEIRAS = "receitas_financeiras", "Receitas financeiras"
    DESPESAS_FINANCEIRAS = "despesas_financeiras", "Despesas financeiras"
    PROVISAO_IRPJ_CSLL = "provisao_irpj_csll", "Provisão para IRPJ e CSLL"
    PARTICIPACOES = "participacoes", "Participações"


class ClassificacaoDlpa(models.TextChoices):
    """Linha da Demonstração dos Lucros ou Prejuízos Acumulados (DLPA) —
    DL-048, etapas CTB-12 e CTB-13 (RC-137, decisão 1 do Fred em
    2026-09-28). Fonte: Lei 6.404/76, art. 176, II (a DLPA continua
    obrigatória — inciso não revogado) e **art. 186, I–III e §§1º/2º**
    (linhas e relação com a DMPL), lidos no Planalto e registrados em
    `docs/projeto/requisitos.md` ("Fontes normativas das demonstrações
    contábeis — DL-048, consultadas em 28/09/2026").

    ⚠️ **A base NÃO é a NBC TG 26 item 106** — o plano de paridade
    (DL-047) dizia isso e a fonte DESMENTIU: a norma inteira não menciona
    DLPA (0 ocorrências; o item 106 descreve a DMPL). Também não é a Lei
    11.941/2009 (o art. 42 da lei é vetado). Quem sustenta a DLPA é a
    Lei das S.A. — ver a nota em `requisitos.md`.

    Mesmo molde de `ClassificacaoPatrimonial`/`ClassificacaoDre` (CTB-12
    é repetir o padrão): campo FIXO da conta, `null=True`, nunca inferido
    de código ou nome — é o contador quem classifica; a apuração da DLPA
    só DECLARA o que falta (`apurar_dlpa`, services.py) e a emissão é
    recusada enquanto houver movimento sem classificação.

    Dois PAPEIS convivem no mesmo campo, e é proposital:

    - `LUCROS_OU_PREJUIZOS_ACUMULADOS` marca a conta SUBJETO da
      demonstração (a conta cujo movimento a DLPA lê). Podem ser VÁRIAS
      contas classificadas com este valor — o caso real de "Lucros
      Acumulados" + "(-) Prejuízos Acumulados" em plano separado; a
      apuração soma as duas pelo MESMO lado (crédito − débito), que é o
      efeito de ambas sobre o resultado acumulado.
    - Os demais valores marcam a CONTRAPARTIDA de um movimento da conta
      sujeito: é ela que diz QUEM movimentou os lucros acumulados (o
      zeramento, uma reserva, os dividendos…).

    As seis reservas de LUCROS vêm de RC-137 (Fred, 2026-09-28): na
    DLPA elas aparecem como LINHAS DE DESTINAÇÃO; na DMPL (CTB-14) como
    colunas — o mesmo fato por dois lados, lido pela mesma apuração.
    Reservas de CAPITAL (ágio, alienação de partes beneficiárias) ficam
    de FORA de propósito: RC-137 confirma que não transitam pela DLPA
    (não vêm do lucro líquido) — se uma delas movimentar os lucros
    acumulados, o movimento cai em "sem classificação" e a emissão é
    recusada, que é o comportamento honesto.

    ⚠️ **Sem herança de ancestral** (decisão da implementação, registrada
    no plano): diferente da DRE, a classificação da DLPA vale para a
    conta EXATA que participa do lançamento — subconta de uma conta
    classificada não herda. A apuração declara a pendência em vez de
    presumir; classificar a subconta é a correção (uma tela própria
    existe para isso). Se a herança um dia for pedida, ela SUBSTITUI esta
    regra (AGENTS.md §8), nunca convive.
    """

    LUCROS_OU_PREJUIZOS_ACUMULADOS = (
        "lucros_ou_prejuizos_acumulados",
        "Lucros ou prejuízos acumulados (conta da DLPA)",
    )
    RESULTADO_DO_EXERCICIO = (
        "resultado_do_exercicio",
        "Resultado do exercício (lucro ou prejuízo transferido)",
    )
    RESERVA_LEGAL = "reserva_legal", "Reserva legal"
    RESERVA_ESTATUTARIA = "reserva_estatutaria", "Reserva estatutária"
    RESERVA_PARA_CONTINGENCIAS = (
        "reserva_para_contingencias",
        "Reserva para contingências",
    )
    RESERVA_DE_INCENTIVOS_FISCAIS = (
        "reserva_de_incentivos_fiscais",
        "Reserva de incentivos fiscais",
    )
    RESERVA_DE_RETENCAO_DE_LUCROS = (
        "reserva_de_retencao_de_lucros",
        "Reserva de retenção de lucros",
    )
    RESERVA_DE_LUCROS_A_REALIZAR = (
        "reserva_de_lucros_a_realizar",
        "Reserva de lucros a realizar",
    )
    DIVIDENDO = "dividendo", "Dividendos distribuídos"
    # BL-603 (RC-153): a destinação de lucros acumulados à conta de "dividendo
    # adicional proposto" é evento PRÓPRIO, com linha separada de "Dividendos
    # distribuídos" — a proposta não é distribuição (a conta fica no PL até a
    # deliberação que a transfere ao passivo). Base: ICPC 08 (R1),
    # "Contabilização da Proposta de Pagamento de Dividendos" (CVM 683/12; CFC
    # — ITG 08), identificada em fonte oficial em 02/10/2026 (PE-75: o texto
    # integral não foi lido, e por isso NENHUM item numerado é citado).
    DIVIDENDO_ADICIONAL_PROPOSTO = (
        "dividendo_adicional_proposto",
        "Dividendo adicional proposto",
    )
    LUCRO_INCORPORADO_AO_CAPITAL = (
        "lucro_incorporado_ao_capital",
        "Lucro incorporado ao capital",
    )
    AJUSTE_DE_EXERCICIO_ANTERIOR = (
        "ajuste_de_exercicio_anterior",
        "Ajuste de exercício anterior",
    )

    # ⚠️ **A rubrica "Correção monetária do saldo inicial" (art. 186, I) NÃO
    # existe neste enum, por decisão do Fred em 29/09/2026.** A lei ainda
    # cita a linha, mas a Lei 9.249/95, art. 4º, p.ú., vedou a correção
    # monetária da moeda — em exercício de 2026 ela é letra morta, e uma
    # rubrica que nunca pode receber movimento é linha que só ocupa espaço
    # no documento entregue ao cliente. O membro sai do enum INTEIRO (não
    # fica depreciado): a migração 0012 ainda não entrou na `main`, então
    # não existe valor gravado em nenhum ambiente compartilhado — e, se
    # algum dia houver, a guarda `contas_com_classificacao_dlpa_desconhecida`
    # (services.py) trata o valor órfão como pendência que VETA a emissão,
    # em vez de somar linha nenhuma. Reverter é repor membro, rótulo e
    # renderer.


# As SEIS reservas de LUCROS de RC-137 (Fred, 2026-09-28) — o subconjunto
# do enum que a apuração da DLPA trata por DIREÇÃO: um movimento contra
# uma conta assim, que REDUZ os lucros acumulados, é destinação (art. 186,
# III — "transferências para reservas"); um que AUMENTA, é reversão (art.
# 186, II — "reversões de reservas"). O subconjunto existe como conjunto
# declarado porque "é reserva" não se deriva de `TipoConta` (as seis têm o
# mesmo tipo das demais contas de PL) nem do rótulo (comparar string é o
# antipadrão que DL-033 proíbe). Teste derivado confere: todo valor da
# tupla pertence ao enum, e as seis entradas de
# `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA` exatamente batem com ela.
RESERVAS_DE_LUCROS_DA_DLPA = (
    ClassificacaoDlpa.RESERVA_LEGAL,
    ClassificacaoDlpa.RESERVA_ESTATUTARIA,
    ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS,
    ClassificacaoDlpa.RESERVA_DE_INCENTIVOS_FISCAIS,
    ClassificacaoDlpa.RESERVA_DE_RETENCAO_DE_LUCROS,
    ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR,
)


# Fonte ÚNICA (mesmo padrão de `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`, DE-056)
# de quais `TipoConta` cada `ClassificacaoDlpa` aceita — usada pela guarda
# de `Conta.clean()`, abaixo. Teste derivado exige que as chaves sejam
# EXATAMENTE `ClassificacaoDlpa.values`.
#
# - Conta sujeito, resultado do exercício e reservas: Patrimônio Líquido —
#   o mesmo grupo que `registrar_parametro_contabil` já exige das três
#   contas de destino do zeramento (DL-043), regra independente aqui.
# - Dividendos: aceita PASSIVO E PL ("Dividendos a pagar" é passivo;
#   "Lucros a distribuir"/"Dividendos a distribuir" é PL) — os dois
#   arranjos são usuais no plano de contas, e a guarda existe para
#   impedir nonsense (uma conta de receita classificada como dividendo),
#   não para escolher o arranjo do escritório.
# - Ajuste de exercício anterior: QUALQUER tipo de propósito — a
#   contrapartida de uma retificação de erro de exercício anterior (LSA
#   art. 186, §1º; CPC 23) pode ser qualquer conta (uma baixa de ativo, um
#   passivo, uma receita): a norma não restringe o lado de fora, e
#   restringir aqui inventaria regra que a fonte não tem.
TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA = {
    ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESULTADO_DO_EXERCICIO: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_LEGAL: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_ESTATUTARIA: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_DE_INCENTIVOS_FISCAIS: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_DE_RETENCAO_DE_LUCROS: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.DIVIDENDO: (TipoConta.PASSIVO, TipoConta.PATRIMONIO_LIQUIDO),
    # Dividendo adicional proposto: SÓ Patrimônio Líquido (ICPC 08 (R1): a
    # proposta além do mínimo obrigatório permanece no PL, em conta
    # específica, até a deliberação dos acionistas) — diferente de
    # `DIVIDENDO`, que também aceita "dividendos a pagar" no passivo.
    ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL: (TipoConta.PATRIMONIO_LIQUIDO,),
    ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR: tuple(TipoConta.values),
}


# Fonte ÚNICA (mesmo padrão de `TIPO_DA_CLASSIFICACAO_PATRIMONIAL`, DE-056)
# de quais `TipoConta` cada `ClassificacaoDre` aceita — usada pela guarda de
# `Conta.clean()` abaixo, pelo serializer e pela apuração da DRE
# (services.py) para o cálculo do resíduo por tipo. Ver a ressalva sobre
# inferência no docstring de `ClassificacaoDre`, acima.
#
# Um TUPLE, não um valor único: TODA linha aceita hoje exatamente UM
# `TipoConta`, EXCETO "resultado de equivalência patrimonial" — decisão do
# arquiteto de 26/09/2026 — que aceita RECEITA (ganho) OU DESPESA (perda),
# porque a perda de equivalência costuma ser classificada no grupo de
# despesas. O sinal exibido continua vindo de
# `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE` (por LINHA, fixo), nunca do
# `TipoConta` da conta — por isso aceitar dois tipos aqui não muda o sinal:
# uma conta de DESPESA classificada em MEP soma NEGATIVO ao resultado de
# equivalência, automaticamente (não é um `if` especial em lugar nenhum).
TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE = {
    ClassificacaoDre.RECEITA_BRUTA: (TipoConta.RECEITA,),
    ClassificacaoDre.DEDUCOES_DA_RECEITA: (TipoConta.RECEITA,),
    ClassificacaoDre.CUSTO: (TipoConta.DESPESA,),
    ClassificacaoDre.DESPESAS_COM_VENDAS: (TipoConta.DESPESA,),
    ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS: (TipoConta.DESPESA,),
    ClassificacaoDre.OUTRAS_RECEITAS: (TipoConta.RECEITA,),
    ClassificacaoDre.OUTRAS_DESPESAS: (TipoConta.DESPESA,),
    ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS: (TipoConta.DESPESA,),
    ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL: (TipoConta.RECEITA, TipoConta.DESPESA),
    ClassificacaoDre.RECEITAS_FINANCEIRAS: (TipoConta.RECEITA,),
    ClassificacaoDre.DESPESAS_FINANCEIRAS: (TipoConta.DESPESA,),
    ClassificacaoDre.PROVISAO_IRPJ_CSLL: (TipoConta.DESPESA,),
    ClassificacaoDre.PARTICIPACOES: (TipoConta.DESPESA,),
}


# Natureza NATURAL de cada `TipoConta` que participa da DRE — mesma ideia de
# `NATUREZA_NATURAL_DO_TIPO` (acima, escopado a Ativo/Passivo para o
# Balanço), mas um dict PRÓPRIO, nunca o mesmo: estender o dict do Balanço
# misturaria o invariante de duas features diferentes (e o teste derivado
# que confere `NATUREZA_NATURAL_DO_TIPO.keys() ==
# TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()` quebraria por um motivo alheio
# à DL-033). Usada pela apuração da DRE para o resíduo por tipo (receita,
# despesa), no mesmo espírito do resíduo do Balanço (DE-068/BL-496): soma
# CADA nó topo classificado normalizando o sinal por esta natureza, nunca
# pela natureza CADASTRADA de cada conta isolada — protege contra duas
# contas irmãs topo-classificadas na MESMA linha com naturezas cadastradas
# diferentes (a mesma aritmética do BL-486, adaptada à DRE).
NATUREZA_NATURAL_DO_TIPO_DRE = {
    TipoConta.RECEITA: NaturezaConta.CREDORA,
    TipoConta.DESPESA: NaturezaConta.DEVEDORA,
}


# Natureza NATURAL de cada LINHA da DRE — PER-LINHA, não derivada de
# `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`/`NATUREZA_NATURAL_DO_TIPO_DRE` (achado
# encontrado escrevendo o teste do critério 2d desta etapa): "deduções da
# receita" precisa ser tipo RECEITA para a guarda de `Conta.clean()`
# aceitar (retificadora DENTRO do grupo receita, RC-61 — nunca uma despesa
# separada), mas o lado NATURAL dela, para efeito de MAGNITUDE exibida na
# DRE, é DEVEDOR (ela é alimentada por débitos — impostos sobre vendas,
# devoluções — que REDUZEM a receita bruta). Usar `NATUREZA_NATURAL_DO_
# TIPO_DRE[RECEITA]` (CREDORA) para ela daria uma magnitude NEGATIVA para
# o caso comum (conta majoritariamente debitada), invertendo o sinal que
# `receita_liquida = receita_bruta − deduções` espera. Todas as outras
# doze linhas coincidem com o lado natural do `TipoConta` esperado — só
# "deduções da receita" é a exceção, e por isso este dict existe SEPARADO
# de `NATUREZA_NATURAL_DO_TIPO_DRE` (que continua servindo à apuração do
# RESÍDUO por `TipoConta`, uma pergunta diferente — "qual o lado natural
# de TODAS as contas de RECEITA/DESPESA da empresa", não de uma linha
# específica).
NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE = {
    ClassificacaoDre.RECEITA_BRUTA: NaturezaConta.CREDORA,
    ClassificacaoDre.DEDUCOES_DA_RECEITA: NaturezaConta.DEVEDORA,
    ClassificacaoDre.CUSTO: NaturezaConta.DEVEDORA,
    ClassificacaoDre.DESPESAS_COM_VENDAS: NaturezaConta.DEVEDORA,
    ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS: NaturezaConta.DEVEDORA,
    ClassificacaoDre.OUTRAS_RECEITAS: NaturezaConta.CREDORA,
    ClassificacaoDre.OUTRAS_DESPESAS: NaturezaConta.DEVEDORA,
    ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS: NaturezaConta.DEVEDORA,
    ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL: NaturezaConta.CREDORA,
    ClassificacaoDre.RECEITAS_FINANCEIRAS: NaturezaConta.CREDORA,
    ClassificacaoDre.DESPESAS_FINANCEIRAS: NaturezaConta.DEVEDORA,
    ClassificacaoDre.PROVISAO_IRPJ_CSLL: NaturezaConta.DEVEDORA,
    ClassificacaoDre.PARTICIPACOES: NaturezaConta.DEVEDORA,
}


class GrupoDaDmpl(models.TextChoices):
    """Os grupos de componentes do patrimônio líquido que a NBC TG 51
    (item 111A) e a NBC TG 26 (R5) (item 106B) mandam apresentar, na ordem
    da norma. É o AGRUPAMENTO das colunas da DMPL: a RC-137 do Fred pede
    uma coluna por TIPO de reserva, e a norma pede GRUPOS — cada coluna
    declara a que grupo pertence para o documento mostrar as duas coisas
    sem confundi-las (coluna por tipo é desenho permitido, não obrigação).
    """

    CAPITAL_SOCIAL = "capital_social", "Capital social"
    RESERVAS_DE_CAPITAL = "reservas_de_capital", "Reservas de capital"
    AJUSTES_DE_AVALIACAO_PATRIMONIAL = (
        "ajustes_de_avaliacao_patrimonial",
        "Ajustes de avaliação patrimonial",
    )
    RESERVAS_DE_LUCROS = "reservas_de_lucros", "Reservas de lucros"
    ACOES_OU_QUOTAS_EM_TESOURARIA = (
        "acoes_ou_quotas_em_tesouraria",
        "Ações ou quotas em tesouraria",
    )
    LUCROS_OU_PREJUIZOS_ACUMULADOS = (
        "lucros_ou_prejuizos_acumulados",
        "Lucros ou prejuízos acumulados",
    )
    # BL-603 (RC-153): a coluna "dividendo adicional proposto" não é membro
    # dos grupos do item 111A/106B — a norma de apresentação não a prevê; a
    # conta específica vem da ICPC 08 (R1) (PE-75). Grupo próprio, o último,
    # para o documento não fingir que a coluna pertence a um grupo da norma.
    FORA_DO_ITEM_111A = "fora_do_item_111a", "Fora dos grupos do item 111A"


class ClassificacaoDmpl(models.TextChoices):
    """Coluna da Demonstração das Mutações do Patrimônio Líquido (DMPL) —
    DL-061 (CTB-14 da DL-048), decisão E1 do plano. Fonte: NBC TG 51, item
    111A (a partir de 01/01/2027), ou NBC TG 26 (R5), item 106B; RC-137 do
    Fred (28/09/2026: uma coluna por TIPO de reserva).

    Mesmo molde de `ClassificacaoDlpa`: campo FIXO da conta, `null=True`,
    nunca inferido de código ou nome, e SEM herança de ancestral (a
    classificação vale para a conta EXATA que recebe o lançamento — a regra
    D5 da DLPA). A ordem dos membros é a ordem das colunas no documento.

    O que NÃO é coluna, de propósito:

    - a conta "Resultado do exercício" (`classificacao_dlpa =
      resultado_do_exercicio`) é conta de PASSAGEM do zeramento — o lucro
      aparece como LINHA da coluna de lucros acumulados;
    - as reservas de capital do art. 182, §1º, alíneas "c" e "d", da Lei
      6.404/76 (HI-50 em `docs/projeto/requisitos.md`: hipótese de que
      foram revogadas pela Lei 11.638/2007; a conferência no Planalto está
      pendente) e a correção monetária do capital realizado (§2º, letra
      morta pela Lei 9.249/95, art. 4º, p.ú.). Quem precisar delas antes da
      conferência classifica a conta fora da DMPL, e a apuração vai
      declarar a pendência — nunca presumir.

    Os valores das seis reservas de lucros e o de lucros/prejuízos
    acumulados são IGUAIS aos de `ClassificacaoDlpa` de propósito: é o
    mesmo fato visto pelos dois lados (RC-137), e a consistência entre as
    duas classificações é verificada por `COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_
    CLASSIFICACAO_DLPA`, abaixo.
    """

    CAPITAL_SOCIAL = "capital_social", "Capital social"
    AGIO_NA_EMISSAO_DE_ACOES = "agio_na_emissao_de_acoes", "Ágio na emissão de ações"
    ALIENACAO_DE_PARTES_BENEFICIARIAS_E_BONUS_DE_SUBSCRICAO = (
        "alienacao_de_partes_beneficiarias_e_bonus_de_subscricao",
        "Alienação de partes beneficiárias e bônus de subscrição",
    )
    AJUSTES_DE_AVALIACAO_PATRIMONIAL = (
        "ajustes_de_avaliacao_patrimonial",
        "Ajustes de avaliação patrimonial",
    )
    RESERVA_LEGAL = "reserva_legal", "Reserva legal"
    RESERVA_ESTATUTARIA = "reserva_estatutaria", "Reserva estatutária"
    RESERVA_PARA_CONTINGENCIAS = (
        "reserva_para_contingencias",
        "Reserva para contingências",
    )
    RESERVA_DE_INCENTIVOS_FISCAIS = (
        "reserva_de_incentivos_fiscais",
        "Reserva de incentivos fiscais",
    )
    RESERVA_DE_RETENCAO_DE_LUCROS = (
        "reserva_de_retencao_de_lucros",
        "Reserva de retenção de lucros",
    )
    RESERVA_DE_LUCROS_A_REALIZAR = (
        "reserva_de_lucros_a_realizar",
        "Reserva de lucros a realizar",
    )
    ACOES_OU_QUOTAS_EM_TESOURARIA = (
        "acoes_ou_quotas_em_tesouraria",
        "Ações ou quotas em tesouraria",
    )
    LUCROS_OU_PREJUIZOS_ACUMULADOS = (
        "lucros_ou_prejuizos_acumulados",
        "Lucros ou prejuízos acumulados",
    )
    # BL-603 (RC-153): conta específica de "dividendo adicional proposto"
    # (ICPC 08 (R1)) — coluna FORA dos grupos do item 111A/106B, que não a
    # prevê; a última da ordem é apresentada depois de lucros acumulados.
    DIVIDENDO_ADICIONAL_PROPOSTO = (
        "dividendo_adicional_proposto",
        "Dividendo adicional proposto",
    )


# Grupo do item 111A de cada coluna. Fonte ÚNICA do agrupamento; teste
# derivado exige que as chaves sejam EXATAMENTE `ClassificacaoDmpl.values`.
GRUPO_DA_CLASSIFICACAO_DMPL = {
    ClassificacaoDmpl.CAPITAL_SOCIAL: GrupoDaDmpl.CAPITAL_SOCIAL,
    ClassificacaoDmpl.AGIO_NA_EMISSAO_DE_ACOES: GrupoDaDmpl.RESERVAS_DE_CAPITAL,
    ClassificacaoDmpl.ALIENACAO_DE_PARTES_BENEFICIARIAS_E_BONUS_DE_SUBSCRICAO: (
        GrupoDaDmpl.RESERVAS_DE_CAPITAL
    ),
    ClassificacaoDmpl.AJUSTES_DE_AVALIACAO_PATRIMONIAL: (
        GrupoDaDmpl.AJUSTES_DE_AVALIACAO_PATRIMONIAL
    ),
    ClassificacaoDmpl.RESERVA_LEGAL: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_ESTATUTARIA: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_PARA_CONTINGENCIAS: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_DE_INCENTIVOS_FISCAIS: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_DE_RETENCAO_DE_LUCROS: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_DE_LUCROS_A_REALIZAR: GrupoDaDmpl.RESERVAS_DE_LUCROS,
    ClassificacaoDmpl.ACOES_OU_QUOTAS_EM_TESOURARIA: GrupoDaDmpl.ACOES_OU_QUOTAS_EM_TESOURARIA,
    ClassificacaoDmpl.LUCROS_OU_PREJUIZOS_ACUMULADOS: GrupoDaDmpl.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    ClassificacaoDmpl.DIVIDENDO_ADICIONAL_PROPOSTO: GrupoDaDmpl.FORA_DO_ITEM_111A,
}

# As seis reservas de LUCROS na DMPL — espelho de `RESERVAS_DE_LUCROS_DA_DLPA`.
RESERVAS_DE_LUCROS_DA_DMPL = (
    ClassificacaoDmpl.RESERVA_LEGAL,
    ClassificacaoDmpl.RESERVA_ESTATUTARIA,
    ClassificacaoDmpl.RESERVA_PARA_CONTINGENCIAS,
    ClassificacaoDmpl.RESERVA_DE_INCENTIVOS_FISCAIS,
    ClassificacaoDmpl.RESERVA_DE_RETENCAO_DE_LUCROS,
    ClassificacaoDmpl.RESERVA_DE_LUCROS_A_REALIZAR,
)

# As duas reservas de CAPITAL da RC-137 (as alíneas "c" e "d" do art. 182,
# §1º, ficaram de fora: HI-50).
RESERVAS_DE_CAPITAL_DA_DMPL = (
    ClassificacaoDmpl.AGIO_NA_EMISSAO_DE_ACOES,
    ClassificacaoDmpl.ALIENACAO_DE_PARTES_BENEFICIARIAS_E_BONUS_DE_SUBSCRICAO,
)

# Todas as colunas são do Patrimônio Líquido (E1: "só para conta de tipo
# PL"). Um dict e não uma regra solta, no molde de `TIPOS_ACEITOS_DA_
# CLASSIFICACAO_DLPA`: coluna nova sem entrada aqui reprova o teste
# derivado em vez de aceitar qualquer tipo em silêncio.
TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL = {
    coluna: (TipoConta.PATRIMONIO_LIQUIDO,) for coluna in ClassificacaoDmpl
}

# CONSISTÊNCIA DLPA × DMPL (E1) — fonte ÚNICA, lida pela guarda de
# `Conta.clean()` e pela apuração (`apurar_dmpl`). Para cada valor de
# `ClassificacaoDlpa`, quais colunas da DMPL a MESMA conta pode ter. `None`
# (conta sem coluna) é sempre admitido aqui: "conta de PL com movimento e
# sem coluna" é pendência da apuração, não erro de cadastro.
#
# - Lucros/prejuízos acumulados e as seis reservas de lucros: a MESMA
#   coluna. É o que faz a coluna de lucros acumulados da DMPL ser idêntica à
#   DLPA (E3) — duas contas com leitura diferente nas duas demonstrações
#   fariam os documentos discordarem em silêncio.
# - Lucro incorporado ao capital: a conta que recebe o capital.
# - Resultado do exercício: NENHUMA — é conta de passagem do zeramento, fora
#   das colunas.
# - Dividendo e ajuste de exercício anterior: NENHUMA. Quando a conta é de PL
#   ("dividendos a distribuir", "ajustes de exercícios anteriores"), ela
#   segue sem coluna e a emissão da DMPL fica VETADA enquanto a conta tiver
#   saldo ou movimento. Não há o que o contador classificar: a pendência diz
#   isso (`classificavel = False` + `orientacao`, N4). BL-603 (RC-153),
#   implementada na etapa 2 da DL-061: a conta de PL "dividendo adicional
#   proposto" ganha a linha e a coluna próprias — ver a entrada
#   `DIVIDENDO_ADICIONAL_PROPOSTO` abaixo.
COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA = {
    ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS: frozenset(
        {ClassificacaoDmpl.LUCROS_OU_PREJUIZOS_ACUMULADOS}
    ),
    ClassificacaoDlpa.RESULTADO_DO_EXERCICIO: frozenset(),
    ClassificacaoDlpa.RESERVA_LEGAL: frozenset({ClassificacaoDmpl.RESERVA_LEGAL}),
    ClassificacaoDlpa.RESERVA_ESTATUTARIA: frozenset({ClassificacaoDmpl.RESERVA_ESTATUTARIA}),
    ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS: frozenset(
        {ClassificacaoDmpl.RESERVA_PARA_CONTINGENCIAS}
    ),
    ClassificacaoDlpa.RESERVA_DE_INCENTIVOS_FISCAIS: frozenset(
        {ClassificacaoDmpl.RESERVA_DE_INCENTIVOS_FISCAIS}
    ),
    ClassificacaoDlpa.RESERVA_DE_RETENCAO_DE_LUCROS: frozenset(
        {ClassificacaoDmpl.RESERVA_DE_RETENCAO_DE_LUCROS}
    ),
    ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR: frozenset(
        {ClassificacaoDmpl.RESERVA_DE_LUCROS_A_REALIZAR}
    ),
    ClassificacaoDlpa.DIVIDENDO: frozenset(),
    # BL-603 (RC-153): o par é EXATO (linha da DLPA = coluna da DMPL) — é o
    # que mantém a identidade por construção: a destinação lê a mesma chave
    # nas duas demonstrações.
    ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO: frozenset(
        {ClassificacaoDmpl.DIVIDENDO_ADICIONAL_PROPOSTO}
    ),
    ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL: frozenset({ClassificacaoDmpl.CAPITAL_SOCIAL}),
    ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR: frozenset(),
}


def divergencia_entre_dlpa_e_dmpl(classificacao_dlpa, classificacao_dmpl):
    """Devolve a mensagem da divergência entre as duas classificações da
    MESMA conta, ou `None` se são consistentes (DL-061, E1).

    Só compara quando as DUAS existem: conta sem coluna na DMPL, ou sem
    linha na DLPA, não tem o que divergir (a falta é pendência da apuração,
    não erro de cadastro). Valor fora dos enums também devolve `None` — é a
    guarda de "classificação desconhecida" (ORM direto) que o nomeia, nunca
    esta.
    """
    if not classificacao_dlpa or not classificacao_dmpl:
        return None
    admitidas = COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA.get(classificacao_dlpa)
    if admitidas is None or classificacao_dmpl not in ClassificacaoDmpl.values:
        return None
    if classificacao_dmpl in admitidas:
        return None
    rotulo_dlpa = ClassificacaoDlpa(classificacao_dlpa).label
    rotulo_dmpl = ClassificacaoDmpl(classificacao_dmpl).label
    if not admitidas:
        return (
            f'A linha da DLPA "{rotulo_dlpa}" não tem coluna na DMPL, mas esta conta está '
            f'na coluna "{rotulo_dmpl}". Remova uma das duas classificações.'
        )
    colunas_admitidas = " ou ".join(f'"{ClassificacaoDmpl(c).label}"' for c in sorted(admitidas))
    return (
        f'A linha da DLPA "{rotulo_dlpa}" só combina com a coluna {colunas_admitidas} da DMPL, '
        f'mas esta conta está na coluna "{rotulo_dmpl}". A DLPA e a DMPL leriam a mesma conta '
        "de formas diferentes."
    )


class ClassificacaoFluxoCaixa(models.TextChoices):
    """Atividade do fluxo de caixa — DL-066 (CTB-15).

    CPC 03 (R2), item 6 (definições) e item 10 (apresentação): a DFC classifica
    os fluxos do período por **atividades operacionais, de investimento e de
    financiamento**, e essa é a classificação que a demonstração apresenta.

    O enum traz os três rótulos da norma e **nada além deles**: a repartição
    dentro de cada atividade (quais receitas são operacionais, quais
    aquisições são de investimento) é do cadastro da empresa, exatamente como
    nas demais classificações de conta do módulo — e é por isso que este é um
    campo da conta, e não um tipo derivado de `TipoConta`. `TipoConta` separa
    ativo, passivo, patrimônio líquido, receita e despesa; a norma separa
    fluxo operacional, de investimento e de financiamento, e nenhuma das duas
    divisions é a outra.

    Ordem do enum = ordem de apresentação na demonstração, como nos demais
    enums do módulo.
    """

    OPERACIONAL = "operacional", "Operacional"
    INVESTIMENTO = "investimento", "Investimento"
    FINANCIAMENTO = "financiamento", "Financiamento"


# A atividade é permitida em qualquer `TipoConta`, e o motivo merece a nota
# porque o módulo tem o contrário nos outros campos: "operacional" inclui uma
# obrigação que é de operação (juros sobre empréstimo, item 31) e
# "financiamento" inclui uma conta de resultado (a despesa de juros, cujo
# pagamento a norma manda classificar pelo item 34A). Filtrar por tipo aqui
# estreitaria a regra e faria a conta legítima virar "classificação
# desconhecida" na apuração.


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
    # DL-033/RC-106: circulante × não circulante do Balanço Patrimonial —
    # PROPRIEDADE da conta (decisão HI-18), `null=True`/`blank=True` porque
    # conta existente (e conta de Patrimônio Líquido/Receita/Despesa) nasce
    # SEM classificação; ninguém infere a partir do código ou do nome (ver
    # o docstring de `ClassificacaoPatrimonial`, acima).
    classificacao_patrimonial = models.CharField(
        "classificação (circulante/não circulante)",
        max_length=60,
        choices=ClassificacaoPatrimonial.choices,
        null=True,
        blank=True,
    )
    # DL-045/RC-118: linha da DRE (art. 187) — PROPRIEDADE da conta, mesmo
    # desenho de `classificacao_patrimonial` (`null=True`/`blank=True`,
    # nunca inferido do código ou do nome; ver o docstring de
    # `ClassificacaoDre`, acima).
    classificacao_dre = models.CharField(
        "classificação (DRE)",
        max_length=60,
        choices=ClassificacaoDre.choices,
        null=True,
        blank=True,
    )
    # DL-048/CTB-12–CTB-13: linha da DLPA (Lei 6.404/76, art. 186) — o
    # TERCEIRO campo de classificação do mesmo padrão, mesmas razões dos
    # dois acima (`null=True`/`blank=True`, nunca inferido; ver o docstring
    # de `ClassificacaoDlpa` para os dois papéis do campo: conta sujeito e
    # contrapartida).
    classificacao_dlpa = models.CharField(
        "classificação (DLPA)",
        max_length=60,
        choices=ClassificacaoDlpa.choices,
        null=True,
        blank=True,
    )
    # DL-061/CTB-14: coluna da DMPL (NBC TG 51, item 111A) — o QUARTO campo
    # de classificação do mesmo padrão, mesmas razões dos anteriores
    # (`null=True`/`blank=True`, nunca inferido, sem herança). Só para conta
    # de Patrimônio Líquido (ver `ClassificacaoDmpl`).
    classificacao_dmpl = models.CharField(
        "classificação (coluna da DMPL)",
        max_length=60,
        choices=ClassificacaoDmpl.choices,
        null=True,
        blank=True,
    )
    aceita_lancamento = models.BooleanField(
        "aceita lançamento",
        default=True,
        help_text="Contas sintéticas (agrupadoras) não devem receber lançamento direto.",
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    # -------------------------------------------------------------------------
    # DL-066 (CTB-15) — DFC. Três campos, no mesmo molde da CTB-12 (E2 e E3
    # do plano), e todos com a mesma justificativa: são **propriedade da
    # conta**, nunca inferidos de nome nem de código.
    #
    # `caixa_e_equivalentes` responde ao item 45 do CPC 03 (R2) — "divulgar os
    # componentes de caixa e equivalentes de caixa e apresentar uma conciliação
    # dos montantes na DFC com os respectivos itens no balanço patrimonial". Sem
    # esse campo a conciliação não tem contra o que conferir. NOME de conta
    # não serve: "Banco Conta Corrente" tanto serve quanto abriga ajustes de
    # regularização, e conta de aplicação só é equivalente se o contador
    # disser que é (item 7: curto prazo, até três meses).
    #
    # ⚠️ **Este campo NÃO é restrito a conta de ATIVO, e o motivo é o item 8**
    # do CPC 03 (R2), não uma liberalidade: *"saldos bancários a descoberto,
    # decorrentes de empréstimos obtidos por meio de instrumentos como cheques
    # especiais ou contas correntes garantidas que são liquidados em curto
    # lapso temporal, compõem parte integral da gestão de caixa da entidade.
    # Nessas circunstâncias, saldos bancários a descoberto são incluídos como
    # componente de caixa e equivalentes de caixa"*. Na prática contábil o
    # descoberto é ativo negativo, e no plano de contas brasileiro ele costuma
    # ser uma conta de PASSIVO. Uma guarda que exigisse ATIVO tiraria o cheque
    # especial e a conta garantida de fora da conciliação do item 45 — que é
    # justamente o que a entrega precisa provar. Ver **DE-099**.
    caixa_e_equivalentes = models.BooleanField(
        "caixa e equivalente de caixa",
        default=False,
        help_text=(
            "Entra na conciliação do item 45 do CPC 03 (R2) e é o lado CAIXA "
            "dos lançamentos na apuração da DFC. Equivalente de caixa é "
            "aplicação de curto prazo, em regra vencimento de três meses ou "
            "menos (item 7) — o padrão fica a cargo do escritório, não do "
            "produto, e por isso não há marcação automática."
        ),
    )
    # `classificacao_dfc` é a ATIVIDADE do fluxo em que a conta participa
    # (itens 13 a 17). Fica na conta porque é a regra geral; o que a regra não
    # decide — uma transação com duas atividades (item 12) — é exceção por
    # lançamento, e vive na marcação manual (E4, fatia 2).
    classificacao_dfc = models.CharField(
        "atividade do fluxo de caixa",
        max_length=60,
        choices=ClassificacaoFluxoCaixa.choices,
        null=True,
        blank=True,
        help_text=(
            "CPC 03 (R2), itens 10 e 13 a 17: em qual das três atividades o "
            "movimento desta conta entra na DFC. Vazio quando a conta ainda "
            "não foi classificada — e a apuração veta enquanto houver conta "
            "movimentada sem classificação."
        ),
    )
    # `item_de_resultado_sem_caixa` é o item 20(b) do método indireto:
    # despesa ou receita que NÃO movimenta caixa (depreciação, amortização,
    # provisões). Só existe para conta de resultado — a mesma restrição que
    # a linha da DRE e a da DLPA já fazem com `tipo`.
    item_de_resultado_sem_caixa = models.BooleanField(
        "item de resultado que não movimenta caixa",
        default=False,
        help_text=(
            "CPC 03 (R2), item 20(b): depreciação, amortização, provisões e "
            "semelhantes entram no ajuste do método indireto e não como fluxo. "
            "Só vale para conta de resultado."
        ),
    )

    class Meta:
        verbose_name = "conta"
        verbose_name_plural = "contas"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="codigo_unico_por_empresa"),
            # A4 (auditoria DL-045, rodada 1): `classificacao_dre=""` (string
            # vazia, diferente de `NULL`) é um estado torto que só existia
            # pela API — o `ChoiceField` gerado por padrão para um campo com
            # `blank=True` aceitava `""` e gravava. O CÓDIGO já normaliza
            # `""` para `None` na entrada (serializer) e em `clean()`, abaixo
            # — esta constraint é a defesa de BANCO (DE-008, camada 1) para
            # quem grava por fora dos dois (ORM direto, migração de dado,
            # importação): sem ela, `""` continuaria alcançável e distinto
            # de `None` para quem lê direto do banco (ex.: a lista `contas_
            # com_classificacao_dre_desconhecida` da apuração da DRE, que
            # trataria `""` como linha desconhecida). DE-086 (reconferência):
            # a classificação da DRE deixou de ser imutável com movimento —
            # esta constraint continua por higiene de dado, não porque um
            # estado torto travaria a conta para sempre (isso não existe
            # mais: qualquer classificação, inclusive corrigir um `""`
            # legado, é sempre livre agora).
            models.CheckConstraint(
                condition=~models.Q(classificacao_dre=""),
                name="ck_conta_classificacao_dre_nao_vazia",
            ),
            # DL-048/CTB-12: mesma defesa de BANCO (DE-008, camada 1) da
            # DRE acima, desde o DIA UM do campo — `""` nunca é um estado
            # válido, e sem esta constraint ele seria alcançável por quem
            # grava por fora do serializer e do `clean()` (ORM direto,
            # migração de dado), aparecendo como classificação DESCONHECIDA
            # na apuração da DLPA em vez de "sem classificação". A guarda
            # de `clean()` normaliza `""` → `None` no caminho validado.
            models.CheckConstraint(
                condition=~models.Q(classificacao_dlpa=""),
                name="ck_conta_classificacao_dlpa_nao_vazia",
            ),
            # DL-061/CTB-14: mesma defesa de BANCO (DE-008, camada 1) das
            # duas anteriores, desde o dia um do campo: `""` nunca é um
            # estado válido, e sem esta constraint ele apareceria como
            # coluna DESCONHECIDA na apuração da DMPL em vez de "sem
            # coluna". `Conta.clean()` normaliza `""` → `None` no caminho
            # validado.
            models.CheckConstraint(
                condition=~models.Q(classificacao_dmpl=""),
                name="ck_conta_classificacao_dmpl_nao_vazia",
            ),
            # DL-066/CTB-15: mesma defesa de BANCO (DE-008, camada 1) das três
            # anteriores, desde o dia um do campo — `""` nunca é estado
            # válido, e sem a constraint ele apareceria como atividade
            # DESCONHECIDA na apuração da DFC em vez de "sem classificação".
            # `Conta.clean()` normaliza `""` → `None` no caminho validado.
            models.CheckConstraint(
                condition=~models.Q(classificacao_dfc=""),
                name="ck_conta_classificacao_dfc_nao_vazia",
            ),
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

    def _ids_da_subarvore(self):
        """Os ids desta conta e de todos os descendentes (profundidade
        qualquer), numa consulta só.

        Mesma árvore de `_tem_movimento_proprio_ou_de_descendente` (BL-245),
        devolvida em lista: a guarda de período fechado precisa dos ids mais
        de uma vez — uma para os meses com movimento, outra que se nada tiver
        movimento — e refazer a recursiva a cada uso custaria mais que
        guardá-los.
        """
        tabela_conta = Conta._meta.db_table
        coluna_conta_pai = Conta._meta.get_field("conta_pai").column
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH RECURSIVE arvore(id) AS (
                    SELECT id FROM {tabela_conta} WHERE id = %s
                    UNION
                    SELECT c.id FROM {tabela_conta} c
                    INNER JOIN arvore a ON c.{coluna_conta_pai} = a.id
                )
                SELECT id FROM arvore
                """,
                [self.pk],
            )
            return [linha[0] for linha in cursor.fetchall()]

    def _competencia_fechada_com_movimento(self):
        """A competência **encerrada** (ou entregue) mais recente em que esta
        conta OU qualquer descendente tem partida gravada — `None` se não
        houver nenhuma.

        DL-065 (BL-550). Devolve a LINHA da competência, não um booleano, por
        um motivo de produto: a recusa precisa **nomear** o período. Uma
        recusa que não diz qual competência impede a troca devolve o trabalho
        ao contador sem caminho, e o caminho é a parte mais cara de uma regra
        de bloqueio (a mesma razão que fez `CompetenciaEncerrada` dizer o que
        fazer, e não só que não pode).

        Só entra `estado <> 'aberta'`: a regra acompanha o **estado** da
        competência, não o registro de que houve recusa. Reabrir o período
        encerra o bloqueio, que é o comportamento correto — competência
        reaberta é um período em aberto. Por isso a lista de competências
        afetadas é recalculada a cada tentativa, e não é memorizada.

        A árvore é a MESMA de `_tem_movimento_proprio_ou_de_descendente`
        (BL-245: `WITH RECURSIVE` dentro do PostgreSQL, `UNION` para
        deduplicar e não entrar em ciclo com hierarquia inconsistente),
        devolvida em lista por `_ids_da_subarvore`, que a guarda consulta uma
        vez e reaproveita.

        ⚠️ **O movimento é filtrado por DATA, e é isso que amarra a guarda às
        demonstrações** (achado A1 da auditoria da DL-065). Toda a camada de
        apuração — Balancete, `apurar_saldos`, DRE, DLPA e DMPL — lê o
        movimento por `lancamento__data__gte/__lte` e **nunca** pela FK
        `LancamentoContabil.competencia`. A primeira versão desta guarda
        ligava pela FK e por isso era cega ao lançamento sem competência
        gravada: `competencia_id` é **anulável** no banco (a restrição
        `NOT NULL` da DL-016 F6 cobre `empresa_id`), e a data desse
        lançamento entrava normalmente na DLPA do período encerrado. Guarda
        que filtra por um critério diferente do que a apuração filtra é
        guarda que pode ser contornada; o critério tem de ser o mesmo.

        ⚠️ **A trava das competências ABERTAS vem ANTES da verificação**
        (achado A2 da mesma auditoria, demonstrado com duas threads: sem ela
        o fechamento do mês commita entre a leitura do estado e o commit da
        reclassificação, e o período termina encerrado com a classificação já
        trocada). O que segura a corrida é o MESMO `FOR SHARE` que
        `criar_lancamento` usa: ele não impede o fechamento — impede que ele
        passe POR CIMA da reclassificação. Qualquer ordem passa a ser
        legítima: ou a reclassificação entra primeiro e o mês fecha em
        seguida, ou o mês fecha primeiro e a reclassificação acorda vendo o
        estado novo e recusa.

        A trava só é pedida dentro de uma transação, e só onde o motor a
        suporta — nos dois casos a REGRA continua valendo, sem a proteção
        contra a corrida e sem estourar exceção em `full_clean()` chamada
        fora de transação.

        **Custo: quatro consultas, e constante nas DUAS dimensões que
        importam** (achado N2 da reconferência, e sua própria medição
        depois). A versão intermediária fazia uma consulta por competência e
        media 507 consultas e 393 ms com 480 períodos fechados — e, como a
        travagem vem antes da varredura, segurava o `FOR SHARE` por todo
        esse tempo, bloqueando o fechamento junto. A pergunta é uma interseção
        de conjuntos (o mês com movimento × o mês fechado), e interseção se
        faz em memória: as consultas trazem sempre o lado pequeno — as
        **abertas** da empresa, que são uma ou duas, e as **fechadas só dos
        anos em que houve movimento**.

        ⚠️ A primeira versão desta correção trocou o eixo do crescimento sem
        eliminá-lo: ela iterava os **meses com movimento** perguntando se cada
        um estava aberto, e a verificação dirigida mediu 39 consultas com 36
        meses com movimento. Numa empresa de quarenta anos, quase todo mês tem
        movimento — então a conta voltava aos mesmos ~480 por outro caminho.
        Iterar do lado pequeno é o que fecha as duas dimensões.

        A lista de competências afetadas é recalculada a cada tentativa e não
        é memorizada: o que decide é o estado de agora, não o de antes.
        """
        ids = self._ids_da_subarvore()
        # Os MÊSES (`ano`, `mes`) em que esta conta — ou qualquer descendente —
        # tem movimento, numa consulta só. É a resposta de "que períodos esta
        # reclassificação pode mexer": a competência de um mês cobre
        # exatamente aquele mês, então bloquear é perguntar se ALGUM desses
        # meses já está fechado.
        #
        # `ExtractYear`/`ExtractMonth` sobre um `DateField` é exatamente a
        # mesma partição de `data__gte=date(ano, mes, 1)` /
        # `data__lte=date(ano, mes, ultimo_dia)` que a apuração usa — sem
        # componente de hora, não há como os dois discordarem, inclusive em
        # fevereiro de ano bissexto. E o custo não cresce com o número de
        # meses que a empresa já fechou.
        meses_com_movimento = set(
            LancamentoContabil.objects.filter(itens__conta_id__in=ids)
            .annotate(_ano=ExtractYear("data"), _mes=ExtractMonth("data"))
            .values_list("_ano", "_mes")
            .distinct()
        )
        if not meses_com_movimento:
            return None

        # Import TARDIO e deliberado: `services` importa `models`, então o
        # caminho inverso só fecha aqui dentro do método — é o mesmo truque que
        # `MarcacaoDmpl.clean()` já usa, e pelo mesmo motivo.
        #
        # Reusar o PRIMITIVO do módulo, e não um lock novo, é o que importa
        # aqui: `_travar_competencia_em_modo_compartilhado` já sabe das três
        # coisas que esta trava precisa saber — que `FOR SHARE` é
        # PostgreSQL, que fora dele a degradação tem de ser AVISADA e não
        # silenciosa, e que o estouro de `lock_timeout` precisa virar erro de
        # domínio e não `InternalError` de transação abortada.
        from apps.contabilidade.services import (  # noqa: PLC0415 (cíclico por natureza)
            CompetenciaOcupada,
            _travar_competencia_em_modo_compartilhado,
        )

        # Trava as ABERTAS **com movimento**, iterando do lado PEQUENO.
        #
        # Iterar os meses com movimento perguntando se cada um está aberto
        # parecia a solução e era o **mesmo N+1 com outro eixo**: numa empresa
        # de quarenta anos de contabilidade quase todo mês tem movimento, e a
        # contagem voltava aos mesmos ~480 (medido: 36 meses com movimento já
        # davam 39 consultas). O lado pequeno é o das competências **abertas**,
        # que são uma ou duas por natureza, e a pertinência no conjunto de
        # meses com movimento está em memória, sem consulta.
        #
        # Ordem `-ano`, `-mes`: é a ordem em que duas reclassificações
        # concorrentes deste mesmo código pediriam o lock, e o que impede que
        # duas delas travem uma a outra em linha de frente.
        #
        # ⚠️ A ordem das três leituras é o que fecha a corrida do A2, e ela é
        # medida: ler as **abertas** → tomar o `FOR SHARE` → ler as
        # **fechadas**. A trava vem ANTES da decisão, e é por isso que o
        # `FOR SHARE` precisa sobreviver ao savepoint (achado N1).
        for aberta in Competencia.objects.filter(
            empresa_id=self.empresa_id, estado=EstadoCompetencia.ABERTA
        ).order_by("-ano", "-mes"):
            if (aberta.ano, aberta.mes) not in meses_com_movimento:
                continue
            try:
                with transaction.atomic():
                    # `self.empresa`, e não `aberta.empresa`: a FK da
                    # competência **não vem em cache**, e buscá-la a cada
                    # trava era uma consulta por mês aberto — 37 numa empresa
                    # com três anos de livros abertos. `self.empresa` é
                    # buscada no máximo uma vez, e o parâmetro só existe para
                    # a mensagem de erro do primitivo.
                    _travar_competencia_em_modo_compartilhado(
                        aberta, ano=aberta.ano, mes=aberta.mes, empresa=self.empresa
                    )
            except CompetenciaOcupada as exc:
                # Estouro de `lock_timeout`: outra operação está em curso
                # sobre a competência. É conflito de ESTADO, como a recusa
                # abaixo — mesmo código, para que a API responda 409 e o
                # contador receba "tente de novo" em vez de um 500.
                raise ValidationError(
                    "Não foi possível verificar o período desta conta agora: outra "
                    f"operação está em curso na competência "
                    f"{aberta.mes:02d}/{aberta.ano} ({exc}). "
                    "Tente de novo em instantes.",
                    code=CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO,
                ) from exc

        # A competência FECHADA mais recente entre os meses com movimento. O
        # cruzamento é feito em Python de propósito (achado N2 da
        # reconferência): a versão anterior fazia uma consulta por competência
        # e media **507 consultas e 393 ms** numa empresa com 480 períodos já
        # fechados — crescimento linear no histórico, dentro de uma transação
        # que segura o `FOR SHARE` e portanto bloqueia o fechamento. A
        # pergunta é uma interseção de conjuntos, e interseção se faz em
        # memória: o número de consultas aqui é **constante**, não cresce com
        # os meses que a empresa já fechou.
        for fechada in (
            Competencia.objects.filter(
                empresa_id=self.empresa_id,
                ano__in={ano for ano, _ in meses_com_movimento},
            )
            .exclude(estado=EstadoCompetencia.ABERTA)
            .order_by("-ano", "-mes")
        ):
            if (fechada.ano, fechada.mes) in meses_com_movimento:
                return {
                    "ano": fechada.ano,
                    "mes": fechada.mes,
                    "estado": fechada.estado,
                    "entregue": fechada.entregue_em is not None,
                }
        return None

    def clean(self):
        # A4 (auditoria DL-045, rodada 1): `""` (string vazia) normalizado
        # para `None` AQUI, antes de qualquer guarda ler o campo — a mesma
        # normalização que o serializer já faz na entrada da API
        # (`validate_classificacao_dre`), repetida porque `clean()` também
        # roda por caminhos que não passam pelo serializer (admin, ORM
        # direto seguido de `full_clean()`). Continua sendo necessária
        # depois da DE-086 (reconferência, que removeu a guarda de
        # transição que originalmente motivou isto): sem a normalização,
        # `""` gravado por qualquer caminho apareceria como linha
        # DESCONHECIDA em `contas_com_classificacao_dre_desconhecida`
        # (services.py, `_apurar_coluna_dre`) em vez de "sem
        # classificação" — vetando a emissão da DRE por um valor que
        # nunca foi uma escolha de ninguém.
        if self.classificacao_dre == "":
            self.classificacao_dre = None
        # DL-048/A4-da-DLPA: `""` → `None` na MESMA batida, pelo mesmo
        # motivo do achado A4 da DL-045 — string vazia gravada por qualquer
        # caminho que não o serializer apareceria como classificação
        # DESCONHECIDA em `apurar_dlpa` (services.py), vetando a emissão por
        # um valor que nunca foi escolha de ninguém.
        if self.classificacao_dlpa == "":
            self.classificacao_dlpa = None
        # DL-061/CTB-14: a coluna da DMPL, na mesma batida e pelo mesmo motivo.
        if self.classificacao_dmpl == "":
            self.classificacao_dmpl = None
        # DL-066/CTB-15: a atividade do fluxo de caixa, idem.
        if self.classificacao_dfc == "":
            self.classificacao_dfc = None

        # Achado B4 da auditoria rodada 1 (DL-038, R5): a recusa de
        # contabilidade por partidas dobradas para empresa em modo
        # livro-caixa só existia no mixin da API e no decorador da tela —
        # o admin (`admin:contabilidade_conta_add`) e qualquer serviço de
        # escrita que não passasse por essas duas portas continuavam
        # aceitando. A REGRA mora só em `apps.empresas.services.
        # recusar_se_livro_caixa` (nunca uma segunda cópia da comparação
        # `modo_escrituracao == LIVRO_CAIXA`); aqui só se traduz para
        # `ValidationError`, o contrato que `full_clean()` exige.
        #
        # `Empresa.objects.filter(pk=...).values_list(...).first()` — NUNCA
        # `self.empresa` — pelo mesmo motivo já documentado mais abaixo
        # neste método (BL-264/rodada 6): `self.empresa` resolve a FK e
        # levanta `Empresa.DoesNotExist`/`TypeError`/`ValueError` crus para
        # `empresa_id` inexistente ou de tipo inválido — não é papel desta
        # checagem reportar isso (outro guard, abaixo, já cuida com
        # mensagem própria); aqui, "não deu para confirmar o modo" apenas
        # NÃO recusa por livro-caixa (a checagem de empresa inválida, mais
        # abaixo, é quem recusa a gravação de qualquer forma).
        if self.empresa_id:
            try:
                modo_escrituracao_gravado = (
                    Empresa.objects.filter(pk=self.empresa_id)
                    .values_list("modo_escrituracao", flat=True)
                    .first()
                )
            except (TypeError, ValueError):
                modo_escrituracao_gravado = None
            if modo_escrituracao_gravado == ModoEscrituracao.LIVRO_CAIXA:
                raise ValidationError(MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA)

        if self.conta_pai_id and self.conta_pai.empresa_id != self.empresa_id:
            raise ValidationError("A conta pai deve pertencer à mesma empresa.")

        # DL-033/RC-106: a classificação circulante/não circulante só existe
        # para ATIVO e PASSIVO (Lei 6.404/76, art. 178, §1º/§2º) — Patrimônio
        # Líquido é o TERCEIRO grupo do passivo, ao lado de circulante/não
        # circulante, nunca dentro; Receita e Despesa não fazem parte do
        # Balanço. Guarda de CONSISTÊNCIA interna (não é regra nova: é o que
        # a própria norma já delimita), roda em TODA gravação — inclusive
        # conta nova, sem `self.pk` — porque não depende de histórico. Usa
        # `.get(...)` com `None` de propósito: um valor gravado fora de
        # `ClassificacaoPatrimonial` (só alcançável por ORM/SQL direto, já
        # que `choices` valida na tela e no serializer) não tem entrada no
        # mapa — esta guarda se cala nesse caso em vez de estourar
        # `KeyError`, mesma defesa em profundidade já usada para `tipo`
        # desconhecido na camada de saldos (achado A1/BL-476 da DL-032).
        if self.classificacao_patrimonial:
            tipo_esperado = TIPO_DA_CLASSIFICACAO_PATRIMONIAL.get(self.classificacao_patrimonial)
            if tipo_esperado is not None and self.tipo != tipo_esperado:
                rotulo_classificacao = ClassificacaoPatrimonial(
                    self.classificacao_patrimonial
                ).label
                rotulo_tipo_esperado = TipoConta(tipo_esperado).label
                raise ValidationError(
                    f'A classificação "{rotulo_classificacao}" não é compatível com o '
                    f"tipo desta conta: só se aplica a contas de tipo {rotulo_tipo_esperado} "
                    "(Lei 6.404/76, art. 178)."
                )

        # DL-045/RC-118: a linha da DRE só existe para RECEITA e DESPESA
        # (Lei 6.404/76, art. 187) — conta PATRIMONIAL (Ativo, Passivo,
        # Patrimônio Líquido) com `classificacao_dre` é recusada. MESMO
        # padrão da guarda de `classificacao_patrimonial` acima: `.get(...)`
        # com `None` para um valor gravado fora de `ClassificacaoDre` (só
        # por ORM/SQL direto) não estourar `KeyError`. A maioria das linhas
        # aceita um ÚNICO `TipoConta`; "resultado de equivalência
        # patrimonial" aceita RECEITA ou DESPESA (decisão do arquiteto,
        # 26/09/2026 — ver `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`).
        if self.classificacao_dre:
            tipos_aceitos_dre = TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE.get(self.classificacao_dre)
            if tipos_aceitos_dre is not None and self.tipo not in tipos_aceitos_dre:
                rotulo_classificacao_dre = ClassificacaoDre(self.classificacao_dre).label
                rotulos_tipos_aceitos_dre = " ou ".join(
                    TipoConta(tipo).label for tipo in tipos_aceitos_dre
                )
                raise ValidationError(
                    f'A linha da DRE "{rotulo_classificacao_dre}" não é compatível com o '
                    f"tipo desta conta: só se aplica a contas de tipo "
                    f"{rotulos_tipos_aceitos_dre} (Lei 6.404/76, art. 187)."
                )

        # DL-048/CTB-12: linha da DLPA (Lei 6.404/76, art. 186) — MESMO
        # padrão das duas guardas acima: `.get(...)` com `None` para valor
        # gravado fora do enum não estourar `KeyError` (só alcançável por
        # ORM/SQL direto, já que `choices` valida nos formulários). As duas
        # exceções declaradas no mapa (dividendo; ajuste/correção, que
        # aceitam qualquer tipo) têm sua razão escrita em
        # `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA`, nunca aqui.
        if self.classificacao_dlpa:
            tipos_aceitos_dlpa = TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA.get(self.classificacao_dlpa)
            if tipos_aceitos_dlpa is not None and self.tipo not in tipos_aceitos_dlpa:
                rotulo_classificacao_dlpa = ClassificacaoDlpa(self.classificacao_dlpa).label
                rotulos_tipos_aceitos_dlpa = " ou ".join(
                    TipoConta(tipo).label for tipo in tipos_aceitos_dlpa
                )
                raise ValidationError(
                    f'A linha da DLPA "{rotulo_classificacao_dlpa}" não é compatível com o '
                    f"tipo desta conta: só se aplica a contas de tipo "
                    f"{rotulos_tipos_aceitos_dlpa} (Lei 6.404/76, art. 186)."
                )

        # DL-061/CTB-14 (E1): a coluna da DMPL só existe para Patrimônio
        # Líquido (NBC TG 51, item 111A) — MESMO padrão das guardas acima
        # (`.get(...)` com `None`: valor fora do enum, só alcançável por
        # ORM/SQL direto, não estoura `KeyError`; é a apuração que o nomeia).
        if self.classificacao_dmpl:
            tipos_aceitos_dmpl = TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL.get(self.classificacao_dmpl)
            if tipos_aceitos_dmpl is not None and self.tipo not in tipos_aceitos_dmpl:
                rotulo_classificacao_dmpl = ClassificacaoDmpl(self.classificacao_dmpl).label
                rotulos_tipos_aceitos_dmpl = " ou ".join(
                    TipoConta(tipo).label for tipo in tipos_aceitos_dmpl
                )
                raise ValidationError(
                    f'A coluna da DMPL "{rotulo_classificacao_dmpl}" não é compatível com o '
                    f"tipo desta conta: só se aplica a contas de tipo "
                    f"{rotulos_tipos_aceitos_dmpl} (NBC TG 51, item 111A)."
                )

        # DL-061 (E1): a DLPA e a DMPL não podem ler a MESMA conta de formas
        # diferentes — é o que garante a coluna de lucros acumulados idêntica
        # à DLPA (E3). A regra mora em `divergencia_entre_dlpa_e_dmpl`, que a
        # apuração também usa; aqui só se traduz em `ValidationError`.
        divergencia = divergencia_entre_dlpa_e_dmpl(
            self.classificacao_dlpa, self.classificacao_dmpl
        )
        if divergencia is not None:
            raise ValidationError(divergencia)

        # DL-066 (CTB-15): duas coerências que a apuração da DFC pressupõe e
        # que, sem guarda aqui, virariam **número errado** em vez de erro.
        #
        # (1) Conta marcada como caixa e equivalentes com atividade atribuída:
        # na DFC a conta de caixa é o LADO CAIXA do fluxo, e a atividade vem da
        # contrapartida (E1 do plano). Uma conta que é as duas coisas não tem
        # atividade — ou o contador a declarou caixa por engano, ou quer que ela
        # conte duas vezes. Nos dois casos é cadastro a corrigir, e a apuração
        # não pode escolher por ele.
        if self.caixa_e_equivalentes and self.classificacao_dfc:
            rotulo = ClassificacaoFluxoCaixa(self.classificacao_dfc).label
            raise ValidationError(
                "Esta conta está marcada como caixa e equivalente de caixa e ao mesmo "
                f'tempo com a atividade "{rotulo}" na DFC. São papéis diferentes: a '
                "conta de caixa é o lado por onde o dinheiro entra e sai, e a atividade "
                "é da contrapartida. Escolha um dos dois — sem essa escolha a apuração "
                "contaria o mesmo fluxo duas vezes."
            )
        # (2) "Item de resultado que não movimenta caixa" fora de resultado: a
        # distinção do item 20(b) é sobre receita e despesa, e aplicá-la a um
        # ativo faria o ajuste do método indireto somar um saldo patrimonial ao
        # resultado — que é o tipo de erro que a conciliação do item 45
        # acusaria só depois, longe da causa.
        if self.item_de_resultado_sem_caixa and self.tipo not in (
            TipoConta.RECEITA,
            TipoConta.DESPESA,
        ):
            raise ValidationError(
                "Só conta de resultado pode ser marcada como item que não movimenta "
                f"caixa; esta conta é do tipo {TipoConta(self.tipo).label}. A marcação "
                "existe para depreciação, amortização e provisões (CPC 03, item 20(b)), "
                "que são receita ou despesa."
            )

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
                .values(
                    "empresa_id",
                    "natureza",
                    "tipo",
                    "conta_pai_id",
                    "empresa__escritorio_id",
                    "classificacao_patrimonial",
                    # DL-065 (BL-550): a guarda de período fechado abaixo
                    # precisa do valor GRAVADO das duas classificações de
                    # demonstração anual, pelo mesmo motivo do
                    # `classificacao_patrimonial` acima — a regra é de
                    # TRANSIÇÃO, e transição se mede contra o que está no
                    # banco, não contra o atributo da instância (que o
                    # chamador acabou de atribuir).
                    "classificacao_dlpa",
                    "classificacao_dmpl",
                )
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
                # DL-033 (RC-106/HI-18): mesma lógica de TRANSIÇÃO acima,
                # agora para a classificação circulante/não circulante —
                # campo NOVO desta etapa, com uma diferença DELIBERADA em
                # relação ao molde do BL-83: só conta como TROCA (bloqueável
                # com movimento) quando já havia uma classificação GRAVADA e
                # o valor novo é diferente dela. A PRIMEIRA classificação
                # (gravado `None` -> qualquer valor) é SEMPRE livre, mesmo
                # com movimento — é o caminho que o contador precisa para
                # classificar o plano de contas JÁ EM USO: toda conta nasce
                # SEM classificação nesta etapa (nenhuma migração classifica
                # nada — ver `ClassificacaoPatrimonial`), e quase toda conta
                # real de uma empresa em operação já tem movimento. Se a
                # guarda bloqueasse também a primeira classificação, o
                # recurso ficaria inutilizável: NENHUMA conta existente
                # poderia ser classificada sem antes estornar tudo.
                # Preencher o que faltava não reescreve nenhum Balanço
                # anterior — antes da 1ª classificação a conta simplesmente
                # não entrava em grupo nenhum (aparecia em `contas_sem_
                # classificacao_patrimonial`, camada de saldos); TROCAR ou
                # APAGAR uma classificação já declarada, essa sim,
                # reescreveria um grupo que já apareceu num Balanço.
                classificacao_gravada = original["classificacao_patrimonial"]
                mudou_classificacao = (
                    classificacao_gravada is not None
                    and classificacao_gravada != self.classificacao_patrimonial
                )
                # BL-245 (achado P1, auditoria DL-023 rodada 1): a checagem
                # só roda quando natureza, tipo OU classificação patrimonial
                # de fato mudaram (short-circuit: a consulta recursiva de
                # `_tem_movimento_proprio_ou_de_descendente` custa mais que
                # `itens_lancamento.exists()`, e não há razão para pagá-la
                # numa gravação que não toca nenhum dos três campos).
                # Movimento de QUALQUER descendente conta, não só o
                # próprio — é a correção do requisito, não só do código
                # (ver o docstring do método) — e vale igualmente para a
                # classificação patrimonial: reclassificar um GRUPO com
                # movimento herdado de descendente reescreveria o Balanço
                # da mesma forma que trocar a natureza/tipo do grupo
                # reescreveria o Balancete (é a MESMA classe de dano, era
                # só uma questão de tempo até precisar da mesma defesa).
                # Computa o movimento no MÁXIMO uma vez para as duas
                # guardas (natureza/tipo, classificação patrimonial). A
                # linha da DRE (`classificacao_dre`) NÃO entra mais aqui —
                # DE-086 (reconferência da DL-045) reabriu o critério de
                # imutabilidade: a classificação da DRE é propriedade de
                # apresentação (não altera nenhum saldo), o manual do
                # sistema de referência trata o "Grupo DRE" como campo
                # simples do cadastro, sem restrição por movimento, e a
                # guarda de transição criada na rodada 1 (mais as duas
                # guardas do A6, abaixo) fechavam a ÚNICA saída de um
                # veto que a própria correção do A2 criou (R1, achado
                # ALTO da reconferência: conta patrimonial pendurada sob
                # linha de resultado ficava sem correção possível, e o
                # Balanço — DL-034 — inemitível sem SQL direto). Mudar a
                # linha da DRE com movimento é sempre livre agora, sempre
                # com trilha (`classificar_conta_na_dre`, em services.py,
                # grava antes/depois, usuário, data, IP).
                mudou_algo = mudou_natureza or mudou_tipo
                tem_movimento_para_guarda = None
                if mudou_algo or mudou_classificacao:
                    tem_movimento_para_guarda = self._tem_movimento_proprio_ou_de_descendente()
                if mudou_algo and tem_movimento_para_guarda:
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

                # DL-033 (RC-106/HI-18): mensagem PRÓPRIA — diferente da de
                # natureza/tipo acima de propósito. O caminho certo aqui
                # NÃO é estornar e cadastrar conta nova: é LANÇAR A
                # RECLASSIFICAÇÃO (transferir o saldo para uma conta nova
                # já com a classificação correta), porque a HI-18 decidiu
                # que a classificação é propriedade FIXA da conta — editar
                # uma conta já movimentada reescreveria, em silêncio,
                # Balanços já entregues ao cliente que leram aquele saldo
                # daquela conta.
                if mudou_classificacao and tem_movimento_para_guarda:
                    raise ValidationError(
                        "Não é possível mudar a classificação (circulante/não "
                        "circulante) desta conta: ela ou uma conta descendente já "
                        "tem lançamento gravado — o Balanço já apurado com esta "
                        "conta mudaria retroativamente. Cadastre uma conta nova "
                        "com a classificação correta e lance a RECLASSIFICAÇÃO "
                        "(a transferência do saldo), em vez de editar esta conta."
                    )

                # DL-065 (BL-550): as DUAS classificações de demonstração
                # anual — a linha da DLPA e a coluna da DMPL — não podem ser
                # trocadas, nem removidas, quando a conta (ou qualquer
                # descendente) tem movimento em competência já ENCERRADA ou
                # entregue.
                #
                # É a MESMA classe de dano da classificação patrimonial acima,
                # com uma condição a mais: lá o bloqueio vale em qualquer
                # competência porque o Balanço é lido por data; aqui ele só
                # começa no fechamento, porque enquanto o período está
                # aberto a classificação ainda é trabalho em curso — é
                # exatamente o caminho que limpa o veto da própria DLPA e da
                # própria DMPL, e bloqueá-lo antes deixaria as duas
                # demonstrações inemitíveis sem caminho.
                #
                # A PRIMEIRA classificação (gravado `None` -> valor) é livre,
                # pelo mesmo motivo pelo qual a patrimonial a mantém livre e
                # por um mais forte aqui: nenhuma migração do projeto
                # classificou conta alguma, então bloquear a primeira
                # classificação tornaria impossível classificar o plano de
                # contas de uma empresa que já está em operação.
                #
                # A DRE NÃO entra — DE-086 (reconferência da DL-045): a linha
                # da DRE é propriedade de apresentação e muda com movimento,
                # sempre. O critério 10 do plano da DL-065 existe para provar
                # que este bloco não vazou para lá: travar a DRE em período
                # encerrado tiraria do contador a única saída do veto do A2.
                mudou_dlpa = (
                    original["classificacao_dlpa"] is not None
                    and original["classificacao_dlpa"] != self.classificacao_dlpa
                )
                mudou_dmpl = (
                    original["classificacao_dmpl"] is not None
                    and original["classificacao_dmpl"] != self.classificacao_dmpl
                )
                if mudou_dlpa or mudou_dmpl:
                    nome_da_demonstracao = (
                        "a linha da DLPA e a coluna da DMPL"
                        if mudou_dlpa and mudou_dmpl
                        else ("a linha da DLPA" if mudou_dlpa else "a coluna da DMPL")
                    )
                    competencia = self._competencia_fechada_com_movimento()
                    if competencia is not None:
                        rotulo_do_estado = (
                            dict(EstadoCompetencia.choices)
                            .get(competencia["estado"], competencia["estado"])
                            .lower()
                        )
                        if competencia["entregue"]:
                            # Achado A3 da auditoria da DL-065: competência
                            # ENTREGUE não se reabre — `reabrir_competencia`
                            # recusa sempre (RC-101). Dizer "reabra a
                            # competência" aqui mandava o contador para uma
                            # porta que o próprio produto fecha, e a frase
                            # seguinte ("a correção nunca é uma
                            # reclassificação") ainda contradizia o caminho
                            # da competência apenas encerrada, onde reabrir
                            # É a saída. Cada situação recebe o caminho que
                            # ela realmente tem, como o BL-468 fez em
                            # `criar_lancamento`.
                            caminho = (
                                "Esta competência já foi entregue ao cliente e não pode "
                                "ser reaberta: a correção é um lançamento de ajuste na "
                                "competência aberta, transferindo o valor para uma conta "
                                "já com a classificação certa — esta conta não muda."
                            )
                        else:
                            caminho = (
                                "Reabra a competência para corrigir a classificação; "
                                "enquanto ela estiver fechada, a demonstração do período "
                                "não pode mudar. Se houver movimento em outro período "
                                "ainda aberto, o ajuste pode ser lançado nele."
                            )
                        raise ValidationError(
                            f"Não é possível mudar {nome_da_demonstracao} desta conta: "
                            "ela ou uma conta descendente tem lançamento na competência "
                            f"{competencia['mes']:02d}/{competencia['ano']}, que está "
                            f"{rotulo_do_estado} — a demonstração daquele período mudaria "
                            "retroativamente, depois de o período ter sido fechado. "
                            f"{caminho}",
                            code=CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO,
                        )

                # DE-086 (reconferência da DL-045): NÃO HÁ guarda de
                # transição para `classificacao_dre` aqui — a linha da DRE
                # pode mudar livremente com movimento (ver o comentário
                # acima de `mudou_algo`). As guardas do A6 (rodada 1 desta
                # mesma auditoria: primeira classificação do PAI "engolindo"
                # descendente já classificada; reparentamento que mudava a
                # linha herdada) também saíram — eram as duas travas que
                # fechavam a saída do veto do A2 (R1, achado ALTO). A ÚNICA
                # guarda de reparentamento que sobrevive é a de NATUREZA
                # (BL-261, abaixo), que já existia antes da DL-045 e nunca
                # foi sobre a linha da DRE.

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

            # DE-086 (reconferência da DL-045): a guarda que travava aqui o
            # reparentamento quando a linha da DRE EFETIVA (herdada)
            # mudava (A6, rodada 1) SAIU — era ela quem fechava a ÚNICA
            # saída da pendência criada pela correção do A2 (R1, achado
            # ALTO: conta patrimonial pendurada sob linha de resultado não
            # tinha como ser corrigida, e o Balanço — DL-034 — ficava
            # inemitível sem SQL direto). O reparentamento desta conta
            # volta a obedecer só à regra de NATUREZA acima (BL-261): a
            # linha da DRE é propriedade de apresentação, não uma trava de
            # hierarquia.


class LancamentoContabil(models.Model):
    """Lançamento contábil por partidas dobradas.

    Nunca editar nem excluir um lançamento efetivado: uma correção é feita
    por estorno (um novo lançamento reverso, referenciando o original em
    `estorno_de`), preservando a trilha de auditoria contábil completa
    (AGENTS.md, seção 10). Isso é aplicado em `save`/`delete`, não só por
    convenção: qualquer tentativa de alterar um lançamento já persistido
    levanta LancamentoImutavelError.

    `save`/`delete` não alcançam `QuerySet.update()`/`.delete()`/
    `bulk_create()`. Desde a DL-052 (migração 0013), em PostgreSQL o BANCO
    também recusa UPDATE e DELETE de lançamento e de item (gatilhos
    `trg_lancamento_contabil_imutavel`/`trg_item_lancamento_imutavel`), e
    recusa no COMMIT lançamento cujos débitos diferem dos créditos ou que
    não tenha um débito e um crédito (`CONSTRAINT TRIGGER` adiado). Única
    exceção: `competencia_id` de NULL para um valor, sem mudar mais nada —
    o backfill da DL-016 F5. Em SQLite (só desenvolvimento local) vale a
    guarda de Python.
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
    # DL-052 (decisão do Fred, 30/09/2026): usuário se DESATIVA, não se apaga.
    # `PROTECT` (era `SET_NULL`) impede que apagar um usuário apague a
    # AUTORIA de um lançamento efetivado — e o gatilho de imutabilidade do
    # banco (migração 0013) recusaria o UPDATE que o `SET_NULL` emitiria.
    # `null=True` permanece: lançamento gerado pelo sistema (zeramento,
    # testes, importação) pode não ter autor.
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
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
        constraints = [
            # DL-052 (A1, critério 5): `valor > 0` no BANCO. `criar_lancamento`
            # já recusa valor <= 0 (débito e crédito se expressam por `tipo`,
            # nunca pelo sinal — um "débito de -50" e um "crédito de 50"
            # seriam indistinguíveis na soma), mas `MinValueValidator` só
            # roda em `full_clean()` e `objects.create()`/`bulk_create()`/
            # `update()` não o chamam. Os gatilhos de imutabilidade e de
            # partidas dobradas da migração 0013 (PostgreSQL) completam a
            # defesa; esta constraint vale também em SQLite.
            models.CheckConstraint(
                condition=models.Q(valor__gt=0),
                name="ck_itemlancamento_valor_positivo",
            ),
            # DL-052 (rodada 1, D1): `tipo` só pode ser débito ou crédito. O
            # gatilho de partidas dobradas soma apenas esses dois tipos; sem
            # esta constraint, um item com tipo inválido (`"lixo"`, `"DEBITO"`)
            # passava pelo gatilho e fazia Razão e Balancete divergirem.
            models.CheckConstraint(
                condition=models.Q(tipo__in=["debito", "credito"]),
                name="ck_itemlancamento_tipo_valido",
            ),
        ]

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


class MarcacaoDmpl(models.Model):
    """Marcação manual de UM lançamento numa célula (linha × coluna) da DMPL.

    DL-061, fatia 2 (BL-605), decisões E15–E17 do plano. É a "guia DMPL" do
    sistema de referência, e é a EXCEÇÃO prevista pela RC-151: quando a regra
    automática de linha (`_atribuir_lancamento_as_linhas_da_dmpl`,
    services.py) não decide o evento, o contador reparte o efeito do
    lançamento à mão entre as células e a emissão deixa de ser vetada.

    **Guardada FORA do livro (E15):** nada é gravado em `LancamentoContabil`
    nem em `ItemLancamento` — o lançamento efetivado é imutável (e os
    gatilhos da DL-052 recusariam qualquer UPDATE). A marcação é
    RECLASSIFICAÇÃO DA LEITURA: muda ONDE o valor aparece na demonstração,
    nunca QUANTO existe. Por isso `apurar_dmpl` só a aceita quando o conjunto
    reproduz exatamente o `movimento` do lançamento (E16) — ver
    `salvar_marcacoes_da_dmpl` (services.py).

    Campos, no molde dos modelos vizinhos:

    - `lancamento` (`PROTECT`): o livro efetivado não se apaga, e apagar o
      lançamento levaria junto a marcação que explica a emissão de um
      documento entregue ao cliente;
    - `empresa`: a MESMA do lançamento (conferida em `clean()`), para o
      isolamento entre empresas valer já na consulta
      (`MarcacaoDmpl.objects.filter(empresa=...)` em `apurar_dmpl`);
    - `linha`: chave de `_TITULOS_DAS_LINHAS_DA_DMPL` (services.py), menos as
      duas linhas de saldo (ver `clean()`);
    - `coluna`: `ClassificacaoDmpl`, a coluna da conta classificada;
    - `valor` (`Decimal`): o efeito da marcação na coluna (crédito − débito),
      ≠ 0 — a marcação de valor zero não descreve evento nenhum e só
      confundiria a soma por coluna;
    - autoria (`criado_por`, DL-052: usuário se DESATIVA, não se apaga —
      `PROTECT`) e `criado_em`, como `LancamentoContabil`.

    ⚠️ A validação de linha/coluna/valor mora em `clean()` (com import
    TARDIO de `services`, para não fechar o ciclo services → models →
    services) e é o que o serviço roda em `full_clean()` antes de gravar —
    uma fonte só da regra, alcançada também pelo admin/`ModelForm`.
    """

    lancamento = models.ForeignKey(
        LancamentoContabil, on_delete=models.PROTECT, related_name="marcacoes_dmpl"
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="marcacoes_dmpl")
    linha = models.CharField("linha da DMPL", max_length=60)
    coluna = models.CharField("coluna da DMPL", max_length=60, choices=ClassificacaoDmpl.choices)
    valor = models.DecimalField("valor", max_digits=18, decimal_places=2)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "marcação da DMPL"
        verbose_name_plural = "marcações da DMPL"
        ordering = ["id"]
        constraints = [
            # E15/contrato do conjunto: cada linha × coluna aparece UMA vez
            # por lançamento. Duas marcações para a mesma célula se
            # sobrepõem em `apurar_dmpl` e tornariam a soma por coluna
            # ambígua de ler na trilha; o serviço já recusa a duplicata
            # ANTES do INSERT — esta é a defesa de banco (DE-008, camada 1)
            # contra `bulk_create()`/SQL direto. O par de células de uma
            # MESMA coluna em LINHAS diferentes (compra e venda de ações em
            # tesouraria) continua permitido, e é um dos cenários do plano.
            models.UniqueConstraint(
                fields=["lancamento", "linha", "coluna"],
                name="marcacao_dmpl_unica_por_linha_e_coluna",
            ),
            # `valor ≠ 0` no banco (mesmo molde de
            # `ck_itemlancamento_valor_positivo`): marcação de valor zero não
            # é evento nenhum e só atrapalharia a soma por coluna. O serviço
            # recusa antes (via `clean()`); a constraint é a defesa contra
            # escrita direta no ORM/banco.
            models.CheckConstraint(
                condition=~models.Q(valor=0),
                name="ck_marcacaodmpl_valor_diferente_de_zero",
            ),
        ]

    def __str__(self):
        return f"{self.linha} × {self.coluna} = {self.valor} (lançamento {self.lancamento_id})"

    def clean(self):
        super().clean()
        # Import TARDIO de propósito (o mesmo raciocínio de
        # `validar_data_de_lancamento_do_modelo`, acima): `services.py`
        # importa este módulo, então o import no topo fecharia um ciclo. O
        # alvo é o mapa de linhas da DMPL, que é regra de apuração e mora lá.
        from apps.contabilidade.services import _LINHAS_DE_EVENTO_DA_DMPL

        if self.linha not in _LINHAS_DE_EVENTO_DA_DMPL:
            raise ValidationError(
                f'Linha da DMPL desconhecida: "{self.linha}". As linhas de '
                "evento possíveis são: "
                + ", ".join(f'"{chave}"' for chave in _LINHAS_DE_EVENTO_DA_DMPL)
                + '. As duas linhas de saldo ("saldo_inicial", "saldo_final") '
                "ficam de fora de propósito: saldo inicial e saldo final são "
                "CALCULADOS pela apuração (saldo anterior + movimento), nunca "
                "distribuídos por lançamento, e uma marcação nelas sumiria do "
                "documento."
            )
        if self.coluna not in ClassificacaoDmpl.values:
            raise ValidationError(
                f'Coluna da DMPL desconhecida: "{self.coluna}". As colunas '
                "possíveis são: "
                + ", ".join(f'"{chave}"' for chave in ClassificacaoDmpl.values)
                + " (a coluna de uma conta do patrimônio líquido)."
            )
        if self.valor is None or self.valor == 0:
            raise ValidationError(
                "O valor da marcação não pode ser zero: a marcação descreve o "
                "efeito de um evento numa coluna, e evento nenhum tem efeito "
                "zero. Para limpar as marcações de um lançamento, remova o "
                "conjunto inteiro (não grave uma marcação vazia)."
            )
        # Mesma guarda de `ItemLancamento.clean()`: marcação de uma empresa e
        # lançamento de outra faria o dado de um cliente aparecer na
        # demonstração do outro (a defesa de código em `apurar_dmpl` filtra
        # por empresa; esta é a camada de conveniência do admin/formulário).
        if self.lancamento_id and self.empresa_id and self.lancamento.empresa_id != self.empresa_id:
            raise ValidationError(
                "A marcação deve ser da mesma empresa do lançamento "
                f"({self.empresa} é de uma empresa; o lançamento é de outra)."
            )


class PeriodicidadeZeramento(models.TextChoices):
    """RC-105 (confirmado pelo Fred em 2026-09-20): a periodicidade do
    zeramento do resultado é ALTERNATIVA e por empresa — mensal, trimestral
    OU anual, nunca duas ao mesmo tempo na mesma empresa (a
    `UniqueConstraint` de vigência aberta em `ParametroContabilEmpresa.Meta`,
    abaixo, é o que torna isso garantia do BANCO, não promessa de tela).

    Trimestre e ano são CIVIS (RC-104/RC-105, confirmado pelo Fred): a
    periodicidade trimestral zera em março, junho, setembro e dezembro; a
    anual, só em dezembro. `apps.contabilidade.services.zerar_resultado` é
    quem aplica essa correspondência entre periodicidade e mês de
    encerramento — este enum só nomeia os três valores.
    """

    MENSAL = "mensal", "Mensal"
    TRIMESTRAL = "trimestral", "Trimestral"
    ANUAL = "anual", "Anual"


class ParametroContabilEmpresa(models.Model):
    """Parâmetro contábil de uma empresa, com VIGÊNCIA (DL-043/BL-474).

    O DataLedger não tinha, antes desta etapa, nenhum lugar para guardar
    parâmetro contábil por empresa (BL-474) — o zeramento é o primeiro a
    precisar. No MOLDE de `apps.empresas.models.HistoricoRegimeTributario`
    (DE-039, RC-85/RC-86), e de propósito: o mesmo problema (parâmetro que
    muda no meio do tempo, e cuja mudança não pode reescrever o que já foi
    apurado sob o valor antigo) já tinha solução aceita neste projeto —
    inventar um terceiro jeito seria o erro que a BL-474 avisa para não
    cometer.

    Guarda dois parâmetros, os dois exigidos pelo zeramento (RC-104/RC-105):
    a periodicidade e as TRÊS contas de destino. `apps.contabilidade.
    services.zerar_resultado` lê a vigência aplicável à DATA FINAL do
    período que está zerando — nunca a vigência "atual" no momento da
    chamada — para que reprocessar um período antigo continue usando o
    parâmetro que valia NAQUELE período (mesmo raciocínio de
    `HistoricoRegimeTributario` para apuração fiscal histórica).

    ⚠️ **As TRÊS contas de destino são validadas pelo SERVIÇO
    (`apps.contabilidade.services.registrar_parametro_contabil`), não por
    `clean()` deste modelo.** Decisão deliberada, não descuido: este modelo
    não tem (e não deve ganhar) um segundo caminho de escrita por
    admin/`ModelForm` — o mesmo padrão que `HistoricoRegimeTributarioInline`
    já tinha e foi REMOVIDO do admin de empresas (DL-023/BL-211, ver
    `apps/empresas/admin.py`), porque um `ModelForm` grava por `full_clean()`
    e contorna a checagem de concorrência/vigência que só o SERVIÇO faz sob
    `select_for_update()`. Com uma única porta de escrita, duplicar a
    validação em `clean()` seria a segunda cópia da regra que o AGENTS.md
    §8 proíbe, sem nenhum caminho que a alcançasse.

    ⚠️ **Não sobreposição, garantida em DUAS camadas (DL-043, critério 1):**
    1. `UniqueConstraint` condicional (`vigencia_fim IS NULL`): no máximo UMA
       vigência ABERTA por empresa — a mesma técnica de
       `HistoricoRegimeTributario`.
    2. Um GATILHO, só em PostgreSQL (migração 0009, mesmo padrão
       condicionado a `connection.vendor` das migrações 0010–0013 de
       `apps.empresas`/DL-039/DL-041): recusa QUALQUER `INSERT`/`UPDATE`
       cujo intervalo `[vigencia_inicio, vigencia_fim ou infinito]` se
       sobreponha ao de outra linha da MESMA empresa — inclusive vigências
       já FECHADAS, que a constraint 1 não alcança (ela só protege a
       aberta). É defesa em profundidade: o serviço já fecha a vigência
       anterior de forma sequencial (nunca produz sobreposição pelo
       caminho normal), mas o gatilho recusa também `bulk_create`/
       `QuerySet.update()`/SQL direto. **Limite ACEITO e declarado**
       (mesmo padrão das migrações 0010–0013): em SQLite (desenvolvimento
       local, DE-014) só a camada 1 existe — produção nunca roda SQLite
       (`config/settings.py` recusa com `DEBUG=False`).

    ⚠️ **Medido pelo auxiliar de teste da DL-043, e vale registrar para
    quem for depurar um `IntegrityError` daqui:** em PostgreSQL, com as
    DUAS camadas ativas, tentar abrir uma SEGUNDA vigência aberta
    (`vigencia_fim=None`) para a mesma empresa SEMPRE estoura pelo GATILHO
    (`parametro_contabil_sem_sobreposicao`), nunca pela `UniqueConstraint`
    (`um_periodo_de_parametro_contabil_aberto_por_empresa`) — porque o
    gatilho `BEFORE INSERT` roda ANTES da checagem do índice único (ordem
    de execução do próprio PostgreSQL), e `daterange(inicio, 'infinity',
    '[]')` de uma vigência aberta sempre cruza com o de qualquer outra
    vigência aberta, seja qual for a data de início das duas. A
    `UniqueConstraint` continua sendo a barreira OBSERVÁVEL nesse cenário
    apenas em SQLite (sem gatilho) — nunca em produção/neste banco de
    teste. Ver `test_criterio6_segunda_vigencia_aberta_simultanea_viola_
    unique_constraint_do_banco`
    (`apps/contabilidade/tests/test_dl043_parametro_contabil.py`), que
    aceita os dois nomes de constraint por este motivo, documentado ali.
    """

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="parametros_contabeis"
    )
    periodicidade_zeramento = models.CharField(
        "periodicidade do zeramento", max_length=10, choices=PeriodicidadeZeramento.choices
    )
    conta_resultado_do_exercicio = models.ForeignKey(
        Conta,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="conta de resultado do exercício",
    )
    conta_lucros_acumulados = models.ForeignKey(
        Conta,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="conta de lucros acumulados",
    )
    conta_prejuizos_acumulados = models.ForeignKey(
        Conta,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="conta de (-) prejuízos acumulados",
    )
    # DL-061 (E7): adoção ANTECIPADA da NBC TG 51. A norma vale por padrão
    # para exercícios iniciados a partir de 01/01/2027; a entidade que a
    # adota antes marca aqui, na vigência que cobre o INÍCIO do exercício.
    # Só muda a norma CITADA nas demonstrações (`norma_das_demonstracoes`),
    # nunca um valor — por isso é editável com trilha, sem nova vigência.
    adota_nbc_tg_51_antecipadamente = models.BooleanField(
        "adota a NBC TG 51 antecipadamente", default=False
    )
    vigencia_inicio = models.DateField("vigência (início)")
    vigencia_fim = models.DateField("vigência (fim)", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "parâmetro contábil da empresa"
        verbose_name_plural = "parâmetros contábeis da empresa"
        ordering = ["-vigencia_inicio", "-id"]
        constraints = [
            # Camada 1 da não sobreposição — ver o docstring da classe.
            # Mesma técnica de "um_periodo_de_regime_aberto_por_empresa"
            # (HistoricoRegimeTributario.Meta).
            models.UniqueConstraint(
                fields=["empresa"],
                condition=models.Q(vigencia_fim__isnull=True),
                name="um_periodo_de_parametro_contabil_aberto_por_empresa",
            ),
        ]

    def __str__(self):
        return (
            f"{self.empresa} — zeramento {self.get_periodicidade_zeramento_display()} "
            f"desde {self.vigencia_inicio}"
        )
