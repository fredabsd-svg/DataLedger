import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, Q, Sum
from django.utils import timezone

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoPartida,
)
from apps.core.dinheiro import ValorMonetarioInvalido, casas_decimais, para_decimal

# Campo de saída explícito para os agregados condicionais abaixo (Sum com
# `filter=` combinado com `default=`): sem `output_field`, o Django pode não
# conseguir inferir o tipo do resultado quando o valor por omissão é
# combinado com um CASE/WHEN condicional, e uma inferência errada quebraria
# a precisão decimal exigida para dinheiro (AGENTS.md, seção 10). Mesma
# escala de ItemLancamento.valor (max_digits=18, decimal_places=2).
_CAMPO_SOMA_MONETARIA = DecimalField(max_digits=18, decimal_places=2)

# Escala máxima aceita na escrituração MANUAL (DL-008 / DE-010). Não é uma
# política de arredondamento: é a decisão específica e deliberada de
# RECUSAR, nunca arredondar, um lançamento manual com mais casas decimais do
# que a conta suporta. Quem digita um lançamento manual já deveria ter o
# valor final — arredondar na entrada moveria o problema (achado 4: a
# igualdade débito = crédito era conferida ANTES do arredondamento do banco,
# então 100,004 + 100,004 contra 200,00 passava e gravava desbalanceado).
# Arredondamento fica a cargo dos MOTORES de cálculo (fiscal, folha,
# honorários), onde existe uma regra legal que diz qual política usar.
ESCALA_MAXIMA_LANCAMENTO_MANUAL = 2


class LancamentoInvalido(Exception):
    """Levantado quando os dados de um lançamento violam uma regra contábil."""


class ChaveIdempotenciaConflitante(Exception):
    """A mesma Idempotency-Key foi reaproveitada para um conteúdo diferente.

    Deliberadamente distinta de `LancamentoInvalido`: o cliente não violou
    uma regra contábil (débito/crédito, conta, etc.) — ele reaproveitou uma
    chave que já está associada a outro lançamento. A view precisa devolver
    409 (conflito de estado), não 400 (entrada inválida), para que o cliente
    perceba que precisa gerar uma nova chave, não corrigir o corpo enviado.
    """


def _impressao_digital(*, empresa_id, data, historico, itens):
    """Hash estável do conteúdo de um lançamento, para a idempotência (BL-41 / A2).

    Usado para distinguir "é literalmente a mesma requisição, repetida" de
    "a mesma Idempotency-Key foi reaproveitada para outra coisa". Aceitar o
    segundo caso em silêncio devolveria ao cliente o lançamento ERRADO como
    se fosse sucesso — é a "corrupção por omissão" que o plano DL-007 chama
    de pior que a duplicidade, porque não aparece em nenhuma conciliação.

    Não usamos `hash()` do Python: seu valor depende de `PYTHONHASHSEED` e
    varia entre processos, então a mesma requisição, do mesmo cliente,
    processada por dois workers diferentes teria impressões diferentes —
    inutilizando a comparação. `hashlib.sha256` sobre uma representação
    textual canônica é estável entre processos, reprodutível e determinístico.

    A codificação precisa ser INJETIVA: nenhum conteúdo de campo pode imitar
    a fronteira entre campos (achado N1 da auditoria — uma versão anterior
    concatenava as partes com "|" sem escape, e um `historico` como
    "Honorario|3:debito:100.00" produzia a MESMA impressão que
    `historico="Honorario"` com um item a mais, porque o "|" do texto livre
    do cliente se confundia com o separador). Por isso serializamos com
    `json.dumps(..., sort_keys=True, separators=(",", ":"))`: o JSON escapa
    aspas, barras e qualquer caractere especial dentro das strings, então a
    fronteira entre campos nunca pode ser forjada pelo conteúdo de um campo
    — ao contrário de uma concatenação com separador literal.

    A ordenação dos itens por (conta, tipo) evita falso conflito quando o
    cliente reenvia o mesmo lançamento com os itens em outra ordem. A
    normalização do valor para duas casas decimais aqui serve só para esta
    comparação de igualdade entre requisições — não é, e não substitui, a
    validação de escala/sinal do achado BL-17 (fora do escopo desta etapa).
    """
    itens_ordenados = sorted(itens, key=lambda item: (item["conta"].pk, str(item["tipo"])))
    estrutura = {
        "empresa_id": empresa_id,
        "data": data.isoformat(),
        "historico": (historico or "").strip(),
        "itens": [
            [
                item["conta"].pk,
                str(item["tipo"]),
                str(Decimal(item["valor"]).quantize(Decimal("0.01"))),
            ]
            for item in itens_ordenados
        ],
    }
    texto = json.dumps(estrutura, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@transaction.atomic
def criar_lancamento(
    *,
    empresa,
    data,
    historico,
    itens,
    criado_por=None,
    estorno_de=None,
    chave_idempotencia=None,
):
    """Cria um lançamento contábil validando a igualdade de partidas dobradas.

    `itens` é uma lista de dicts {"conta": Conta, "tipo": TipoPartida, "valor": Decimal}.
    Toda validação contábil acontece antes de qualquer gravação, e a criação
    do lançamento com seus itens é atômica: ou tudo é gravado, ou nada é.

    Cada item tem seu valor validado (sinal e escala, DL-008 / DE-010) ANTES
    da soma de débitos e créditos: valor menor ou igual a zero é recusado, e
    valor com mais de `ESCALA_MAXIMA_LANCAMENTO_MANUAL` casas decimais é
    recusado — nunca arredondado em silêncio.

    `chave_idempotencia` é opcional (BL-41). Quando informada:
    - se já existir um lançamento com a MESMA chave, NESTA empresa, e com o
      MESMO conteúdo (comparado por `_impressao_digital`), devolve esse
      lançamento em vez de criar outro — repetição de rede ou duplo clique
      não duplica a escrituração;
    - se já existir um lançamento com a MESMA chave mas conteúdo DIFERENTE,
      levanta `ChaveIdempotenciaConflitante` (achado A2) — nunca devolve o
      lançamento errado como se fosse sucesso.
    Não deduzimos duplicidade por data/histórico/itens sozinhos, sem a chave:
    dois lançamentos com o mesmo conteúdo podem ser legítimos em contabilidade
    (decisão registrada no plano DL-007).

    Importante (achado A2): a checagem de idempotência só roda DEPOIS de toda
    a validação contábil abaixo. Um corpo inválido (partidas desbalanceadas,
    conta de outra empresa etc.) tem que ser recusado com `LancamentoInvalido`
    mesmo quando a chave já existe — nunca pode "atalhar" para 200 sem passar
    pela invariante débito = crédito.

    O lançamento devolvido sempre traz o atributo `criado_agora` (bool, não
    persistido): `True` quando esta chamada de fato gravou o lançamento,
    `False` quando devolveu um já existente por causa da chave repetida. Quem
    chama precisa dessa informação para não afirmar "criado" numa trilha de
    auditoria quando nada foi criado (AGENTS.md §11 — a trilha registra
    operação e resultado, e o resultado real aqui é "reaproveitado", não
    "criado"); é melhor o serviço informar isso do que a view reconsultar o
    banco tentando adivinhar.
    """
    if len(itens) < 2:
        raise LancamentoInvalido("Um lançamento precisa de ao menos duas partidas.")

    # Sinal e escala são verificados ITEM A ITEM, e ANTES de somar débitos e
    # créditos (achado 4 / BL-17, DE-010). A ordem importa: se a soma
    # viesse primeiro, dois valores com mais casas do que a conta suporta
    # (ex.: 100,004 e 100,004) ainda poderiam ser gravados e só seriam
    # arredondados pelo BANCO depois da checagem de igualdade — exatamente o
    # mecanismo do achado 4, em que 100,004 + 100,004 contra 200,00 passava
    # na comparação e gravava um lançamento desbalanceado.
    for item in itens:
        # Normaliza o valor para `Decimal` ANTES de qualquer comparação
        # (achado 6 da auditoria de 2026-09-12): `criar_lancamento` é
        # chamável por qualquer código, não só pela view HTTP (que já
        # entrega `Decimal`), e `para_decimal` também recusa `float`/`bool`
        # e texto fora do formato decimal simples (achados 6 e 7) — sem
        # isto, um chamador que passasse `valor="100.00"` (string, tipo que
        # `casas_decimais` já aceitava) quebraria na comparação `valor <= 0`
        # abaixo com um `TypeError` cru, não com `LancamentoInvalido`.
        # Reatribuir a `item["valor"]` garante que a soma de débitos/créditos
        # e a gravação em `ItemLancamento` mais abaixo usem o MESMO valor
        # já validado, nunca o original não normalizado.
        try:
            valor = para_decimal(item["valor"])
        except ValorMonetarioInvalido as exc:
            # Traduz o erro de tipo/valor do módulo monetário (float, bool,
            # texto malformado, NaN, infinito) para a exceção de domínio
            # deste serviço. Na prática a view já deveria ter filtrado boa
            # parte disto antes de chegar aqui (achado BL-44/N3), mas
            # `criar_lancamento` não confia apenas no chamador.
            raise LancamentoInvalido(str(exc)) from exc
        item["valor"] = valor
        escala = casas_decimais(valor)

        # Sinal: débito e crédito são expressos pelo campo `tipo`, nunca
        # pelo sinal do valor. Permitir valor negativo criaria DUAS
        # representações para a mesma coisa (um "débito de -50" e um
        # "crédito de 50" ficariam indistinguíveis na soma) e foi
        # exatamente o que deixou {débito 100, débito -50, crédito 50}
        # passar na checagem de igualdade no achado 4. Zero também é
        # recusado: uma partida sem valor não representa nenhum fato
        # contábil.
        if valor <= 0:
            raise LancamentoInvalido(
                f"O valor de uma partida deve ser maior que zero; recebido {valor}. "
                "Débito e crédito são expressos pelo campo 'tipo', não pelo sinal do valor."
            )

        # Escala: a escrituração manual RECUSA, nunca arredonda (DE-010).
        if escala > ESCALA_MAXIMA_LANCAMENTO_MANUAL:
            raise LancamentoInvalido(
                f"O valor {valor} tem {escala} casas decimais; a escrituração "
                f"manual aceita no máximo {ESCALA_MAXIMA_LANCAMENTO_MANUAL}."
            )

    total_debito = sum(
        (item["valor"] for item in itens if item["tipo"] == TipoPartida.DEBITO),
        start=type(itens[0]["valor"])(0),
    )
    total_credito = sum(
        (item["valor"] for item in itens if item["tipo"] == TipoPartida.CREDITO),
        start=type(itens[0]["valor"])(0),
    )

    if total_debito != total_credito:
        raise LancamentoInvalido(
            f"Débitos ({total_debito}) e créditos ({total_credito}) devem ser iguais."
        )
    if total_debito <= 0:
        raise LancamentoInvalido("O lançamento precisa ter valor maior que zero.")

    for item in itens:
        conta = item["conta"]
        if conta.empresa_id != empresa.id:
            raise LancamentoInvalido(f"A conta {conta} não pertence a esta empresa.")
        if not conta.aceita_lancamento:
            raise LancamentoInvalido(f"A conta {conta} não aceita lançamento direto.")

    # Só a partir daqui, com o corpo já validado, a chave de idempotência
    # entra em jogo (achado A2 — ver docstring acima).
    impressao = None
    if chave_idempotencia:
        impressao = _impressao_digital(
            empresa_id=empresa.id, data=data, historico=historico, itens=itens
        )
        existente = LancamentoContabil.objects.filter(
            empresa=empresa, chave_idempotencia=chave_idempotencia
        ).first()
        if existente is not None:
            if existente.chave_idempotencia_fingerprint == impressao:
                existente.criado_agora = False
                return existente
            raise ChaveIdempotenciaConflitante(
                "A mesma Idempotency-Key já foi usada para um lançamento com "
                "conteúdo diferente. Gere uma nova chave para este lançamento."
            )

    # A criação do lançamento com seus itens roda em um savepoint próprio
    # (nested atomic), separado da checagem de idempotência acima. Isso
    # permite capturar um IntegrityError daqui sem invalidar a transação
    # inteira (Django proíbe continuar usando uma transação depois de um erro
    # de banco não tratado por rollback a um savepoint) — é o que fecha a
    # corrida de duas requisições concorrentes com a mesma chave de
    # idempotência, ou de dois estornos concorrentes do mesmo lançamento
    # (constraint `estorno_de_unico`, achado BL-41).
    try:
        with transaction.atomic():
            lancamento = LancamentoContabil.objects.create(
                empresa=empresa,
                data=data,
                historico=historico,
                criado_por=criado_por,
                estorno_de=estorno_de,
                chave_idempotencia=chave_idempotencia,
                chave_idempotencia_fingerprint=impressao,
            )
            for item in itens:
                ItemLancamento.objects.create(
                    lancamento=lancamento,
                    conta=item["conta"],
                    tipo=item["tipo"],
                    valor=item["valor"],
                )
    except IntegrityError:
        if chave_idempotencia:
            # Duas requisições concorrentes com a mesma chave: uma perdeu a
            # corrida da constraint de banco. Buscamos por `filter().first()`,
            # nunca por `.get()` (achado A1 da auditoria): se a violação foi
            # de OUTRA constraint (por exemplo `estorno_de_unico`), pode não
            # existir nenhuma linha com esta chave ainda, e `.get()`
            # levantaria `DoesNotExist` — um 500 disfarçado de 400.
            # `filter().first()` devolve `None` nesse caso, e cai no `raise`
            # abaixo (propositalmente sem conversão — ver comentário).
            existente = LancamentoContabil.objects.filter(
                empresa=empresa, chave_idempotencia=chave_idempotencia
            ).first()
            if existente is not None:
                if existente.chave_idempotencia_fingerprint == impressao:
                    existente.criado_agora = False
                    return existente
                # Corrida entre duas requisições com a MESMA chave e
                # conteúdo DIFERENTE: quem perdeu a corrida do banco também
                # recebe o conflito, nunca o lançamento da outra requisição.
                raise ChaveIdempotenciaConflitante(
                    "A mesma Idempotency-Key já foi usada para um lançamento "
                    "com conteúdo diferente. Gere uma nova chave para este "
                    "lançamento."
                ) from None
        # Qualquer OUTRA violação de integridade propaga sem conversão, de
        # propósito (decisão revista: uma versão anterior converteu tudo em
        # `LancamentoInvalido` aqui, e isso estava errado). `criar_lancamento`
        # é uma função de uso geral — não sabe, neste ponto, se quem chamou
        # é a view (onde só há duas constraints possíveis e ambas já foram
        # tratadas acima) ou algum outro código, presente ou futuro, para o
        # qual uma violação de integridade pode ser um defeito NOSSO (FK
        # quebrada, constraint nova, bug), não um erro do cliente. Converter
        # tudo em 400 atribuiria ao cliente uma falha que pode ser do
        # sistema, e esconderia o defeito de quem monitora 500. Quem sabe o
        # contexto de negócio de uma violação específica é o chamador — é
        # ele que deve decidir a conversão (ver `estornar_lancamento`, que
        # sabe que ali a única violação plausível é `estorno_de_unico`).
        raise
    lancamento.criado_agora = True
    return lancamento


def estornar_lancamento(lancamento, *, criado_por=None, data=None, historico=None):
    """Cria o lançamento reverso (débito e crédito trocados) do original.

    Nunca edita nem apaga o lançamento original — o estorno é sempre um
    novo lançamento, preservando a trilha contábil completa.

    Estorno único (BL-41), em duas camadas (DE-008): (1) `select_for_update`
    bloqueia a linha do lançamento original durante toda a operação, para que
    duas chamadas concorrentes não passem ambas pela checagem "ainda não foi
    estornado" antes de qualquer gravação; (2) a constraint de banco
    `estorno_de_unico` é a defesa final, para qualquer corrida que a camada 1
    não cubra. Por isso a função é `@transaction.atomic`: `select_for_update()`
    exige uma transação aberta.
    """
    with transaction.atomic():
        lancamento = LancamentoContabil.objects.select_for_update().get(pk=lancamento.pk)

        if lancamento.estorno_de_id is not None:
            raise LancamentoInvalido("Não é possível estornar um lançamento que já é um estorno.")
        if lancamento.estornos.exists():
            raise LancamentoInvalido("Este lançamento já foi estornado.")

        itens_invertidos = [
            {
                "conta": item.conta,
                "tipo": (
                    TipoPartida.CREDITO if item.tipo == TipoPartida.DEBITO else TipoPartida.DEBITO
                ),
                "valor": item.valor,
            }
            for item in lancamento.itens.all()
        ]

        try:
            return criar_lancamento(
                empresa=lancamento.empresa,
                data=data or timezone.localdate(),
                historico=historico or f"Estorno do lançamento {lancamento.pk}",
                itens=itens_invertidos,
                criado_por=criado_por,
                estorno_de=lancamento,
            )
        except IntegrityError as exc:
            # Atribuição CONTEXTUAL, não conversão genérica (decisão revista
            # após a rodada anterior de auditoria — ver o comentário em
            # `criar_lancamento`, onde a mesma conversão foi removida por ser
            # genérica demais). Aqui o contexto é específico: este bloco só
            # chama `criar_lancamento` com `estorno_de=lancamento` e SEM
            # `chave_idempotencia`, então a única violação de integridade
            # plausível neste ponto é a constraint `estorno_de_unico` — a
            # checagem `estornos.exists()` acima e o `select_for_update`
            # já deveriam ter impedido isto, e só chegaríamos aqui numa
            # corrida que essas duas camadas não cobrissem. Por isso é
            # seguro e ÚTIL converter para uma mensagem de negócio acionável
            # (400): o contador sabe exatamente o que aconteceu e o que
            # fazer. NÃO remova este bloco achando-o redundante com
            # `criar_lancamento` — lá a conversão foi removida de propósito,
            # porque lá o chamador é genérico e não tem este contexto.
            raise LancamentoInvalido("Este lançamento já foi estornado.") from exc


# ---------------------------------------------------------------------------
# Saídas contábeis com período (DL-015 / BL-59, BL-60, BL-61, BL-64)
#
# DE-016: as três primeiras funções abaixo SEMPRE recebem `inicio`/`fim` já
# validados (date) — a validação de formato, ausência e inversão é
# responsabilidade da view (fronteira HTTP, mesma decisão de onde vive a
# validação de 'data' em `LancamentoListCreateView`). Este módulo não sabe
# nada de querystring; recebe `date` prontos.
#
# As bordas do intervalo são as DUAS inclusivas (`data >= inicio` e
# `data <= fim`): um lançamento datado exatamente em `inicio` ou em `fim`
# pertence ao período (critério 10 do plano DL-015).
# ---------------------------------------------------------------------------


def _saldo_por_natureza(total_debito, total_credito, natureza):
    """Aplica o sinal da natureza da conta a débitos/créditos já somados.

    Devedora (ativo, despesa): débito aumenta o saldo, crédito reduz —
    `debito - credito`. Credora (passivo, patrimônio líquido, receita): é o
    oposto — `credito - debito`. Sem esta inversão, uma conta de patrimônio
    líquido "cresceria" negativamente a cada aporte de capital (um crédito),
    o que diverge do balancete que um contador espera ler, e do sinal já
    usado no Razão linha a linha (`_sinal_do_item`, abaixo) — as duas saídas
    têm que concordar (critério 6: conciliação Razão x Balancete).
    """
    if natureza == NaturezaConta.DEVEDORA:
        return total_debito - total_credito
    return total_credito - total_debito


def _sinal_do_item(tipo, natureza):
    """Sinal (+1/-1) de UM item, para acumular o saldo linha a linha no Razão.

    Matematicamente equivalente a `_saldo_por_natureza` aplicado a um único
    item (débito vira `total_debito` positivo, crédito vira `total_credito`
    positivo) — mantido como função própria porque o Razão soma item a item
    (para produzir a coluna "saldo" de cada linha), enquanto o Balancete soma
    débitos e créditos primeiro e aplica o sinal uma única vez ao total.
    """
    sinal = 1 if tipo == TipoPartida.DEBITO else -1
    if natureza == NaturezaConta.CREDORA:
        sinal *= -1
    return sinal


def listar_diario(*, empresa, inicio, fim):
    """Lançamentos da empresa no período [inicio, fim], para o livro Diário (BL-59).

    Ordenação cronológica ESTÁVEL: data, depois criado_em, depois id — dois
    lançamentos na mesma data (ou até no mesmo segundo) precisam de um
    critério de desempate determinístico, ou a ordem mudaria entre chamadas
    sem nenhum dado ter mudado.

    `prefetch_related("itens__conta")` carrega todos os itens (e a conta de
    cada item) em consultas adicionais de tamanho CONSTANTE (não uma por
    lançamento) — quem chama pode iterar `lancamento.itens.all()` para
    montar os totais e a lista de partidas sem gerar N+1.
    """
    return (
        LancamentoContabil.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .prefetch_related("itens__conta")
        .order_by("data", "criado_em", "id")
    )


def apurar_razao(*, conta, inicio, fim):
    """Apura o Razão de uma conta no período [inicio, fim] (BL-60).

    `saldo_anterior` (critério 3) é a soma de TODOS os itens da conta com
    data anterior a `inicio` — sem limite inferior, "desde sempre" — já com
    o sinal da natureza da conta. A coluna `saldo`, de cada linha do
    período, acumula a PARTIR do saldo anterior, nunca de zero.

    Devolve um dict com `saldo_anterior`, `itens` (lista de dicts com
    `lancamento_id`, `data`, `historico`, `tipo`, `valor`, `saldo`, todos com
    valores em `Decimal` — a formatação para string de moeda é
    responsabilidade da view), `total_debito`, `total_credito` (do período) e
    `saldo_final`.
    """
    zero = Decimal("0")

    # Uma única consulta agregada para o saldo anterior: soma condicional de
    # débito e crédito separadamente (CASE/WHEN dentro do próprio SUM), sem
    # depender de iterar item a item — o Razão de uma conta com histórico
    # longo não precisa carregar tudo em memória só para este número.
    anteriores = ItemLancamento.objects.filter(conta=conta, lancamento__data__lt=inicio).aggregate(
        debito=Sum(
            "valor",
            filter=Q(tipo=TipoPartida.DEBITO),
            default=zero,
            output_field=_CAMPO_SOMA_MONETARIA,
        ),
        credito=Sum(
            "valor",
            filter=Q(tipo=TipoPartida.CREDITO),
            default=zero,
            output_field=_CAMPO_SOMA_MONETARIA,
        ),
    )
    saldo_anterior = _saldo_por_natureza(
        anteriores["debito"], anteriores["credito"], conta.natureza
    )

    itens_periodo = (
        ItemLancamento.objects.filter(
            conta=conta, lancamento__data__gte=inicio, lancamento__data__lte=fim
        )
        .select_related("lancamento")
        .order_by("lancamento__data", "lancamento__criado_em", "id")
    )

    saldo = saldo_anterior
    total_debito = zero
    total_credito = zero
    linhas = []
    for item in itens_periodo:
        saldo += _sinal_do_item(item.tipo, conta.natureza) * item.valor
        if item.tipo == TipoPartida.DEBITO:
            total_debito += item.valor
        else:
            total_credito += item.valor
        linhas.append(
            {
                "lancamento_id": item.lancamento_id,
                "data": item.lancamento.data,
                "historico": item.lancamento.historico,
                "tipo": item.tipo,
                "valor": item.valor,
                "saldo": saldo,
            }
        )

    return {
        "saldo_anterior": saldo_anterior,
        "itens": linhas,
        "total_debito": total_debito,
        "total_credito": total_credito,
        "saldo_final": saldo,
    }


def apurar_balancete(*, empresa, inicio, fim, nivel=None):
    """Apura o Balancete de verificação da empresa no período [inicio, fim] (BL-61).

    Quatro colunas por conta (saldo_anterior, débitos, créditos, saldo_final)
    em vez da coluna única de antes desta etapa. `nivel` é opcional: ausente,
    devolve todas as contas (analíticas e sintéticas); presente, devolve só
    as contas com nível <= `nivel` (raiz = nível 1) — mas o TOTAL da resposta
    continua somando todas as analíticas, sem recorte (ver comentário perto
    do `return`).

    Contas SINTÉTICAS (aceita_lancamento=False) nunca recebem lançamento
    direto, então somar seus próprios itens sempre daria zero — o valor de
    uma sintética é a soma RECURSIVA dos filhos diretos (que, por indução,
    já é a soma de todas as analíticas subordinadas, em qualquer
    profundidade — critério 8). Cada item de lançamento pertence a
    exatamente UMA conta analítica, então esta soma nunca conta o mesmo
    lançamento duas vezes, mesmo com hierarquia de vários níveis.

    Sem N+1 (critério 12): a árvore de contas é carregada em UMA consulta, e
    os totais de débito/crédito (antes do período e dentro dele) de TODAS as
    contas vêm de UMA ÚNICA consulta agregada (`values("conta").annotate`,
    com soma condicional por filtro) — o número de consultas não cresce com
    o número de contas.
    """
    zero = Decimal("0")
    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    if not contas:
        return {"contas": [], "total_debitos": zero, "total_creditos": zero}

    contas_por_id = {conta.id: conta for conta in contas}
    filhos_de = defaultdict(list)
    for conta in contas:
        if conta.conta_pai_id is not None:
            filhos_de[conta.conta_pai_id].append(conta.id)

    # Nível memoizado: toda a árvore já está em memória (consulta única
    # acima), então subir até a raiz não custa consulta nenhuma, só Python.
    niveis = {}

    def nivel_de(conta_id):
        if conta_id not in niveis:
            conta = contas_por_id[conta_id]
            niveis[conta_id] = 1 if conta.conta_pai_id is None else 1 + nivel_de(conta.conta_pai_id)
        return niveis[conta_id]

    # A ÚNICA consulta agregada de valores: filtra por `data <= fim` (itens
    # posteriores ao período não interessam a NENHUMA das quatro colunas) e
    # separa, por conta, quatro somas condicionais — anterior a `inicio`
    # (para saldo_anterior) e dentro do período (para débitos/créditos). O
    # filtro de "período" só precisa checar o limite INFERIOR porque o
    # filtro externo já garante o limite superior.
    agregados_por_conta = {
        linha["conta"]: linha
        for linha in (
            ItemLancamento.objects.filter(conta__empresa=empresa, lancamento__data__lte=fim)
            .values("conta")
            .annotate(
                debito_anterior=Sum(
                    "valor",
                    filter=Q(tipo=TipoPartida.DEBITO, lancamento__data__lt=inicio),
                    default=zero,
                    output_field=_CAMPO_SOMA_MONETARIA,
                ),
                credito_anterior=Sum(
                    "valor",
                    filter=Q(tipo=TipoPartida.CREDITO, lancamento__data__lt=inicio),
                    default=zero,
                    output_field=_CAMPO_SOMA_MONETARIA,
                ),
                debito_periodo=Sum(
                    "valor",
                    filter=Q(tipo=TipoPartida.DEBITO, lancamento__data__gte=inicio),
                    default=zero,
                    output_field=_CAMPO_SOMA_MONETARIA,
                ),
                credito_periodo=Sum(
                    "valor",
                    filter=Q(tipo=TipoPartida.CREDITO, lancamento__data__gte=inicio),
                    default=zero,
                    output_field=_CAMPO_SOMA_MONETARIA,
                ),
            )
        )
    }
    linha_vazia = {
        "debito_anterior": zero,
        "credito_anterior": zero,
        "debito_periodo": zero,
        "credito_periodo": zero,
    }

    resultados = {}

    def resultado_de(conta_id):
        """Dict {saldo_anterior, debitos, creditos, saldo_final} da conta.

        Analítica: lida direto do agregado. Sintética: soma dos filhos
        diretos, já resolvidos (recursão, sem consulta nova) — ver a
        docstring de `apurar_balancete` sobre por que isto nunca conta um
        lançamento duas vezes.
        """
        if conta_id in resultados:
            return resultados[conta_id]

        conta = contas_por_id[conta_id]
        if conta.aceita_lancamento:
            agregado = agregados_por_conta.get(conta_id, linha_vazia)
            saldo_anterior = _saldo_por_natureza(
                agregado["debito_anterior"], agregado["credito_anterior"], conta.natureza
            )
            debitos = agregado["debito_periodo"]
            creditos = agregado["credito_periodo"]
            saldo_final = saldo_anterior + _saldo_por_natureza(debitos, creditos, conta.natureza)
            resultado = {
                "saldo_anterior": saldo_anterior,
                "debitos": debitos,
                "creditos": creditos,
                "saldo_final": saldo_final,
            }
        else:
            resultado = {
                "saldo_anterior": zero,
                "debitos": zero,
                "creditos": zero,
                "saldo_final": zero,
            }
            for filho_id in filhos_de.get(conta_id, []):
                filho = resultado_de(filho_id)
                for chave in resultado:
                    resultado[chave] += filho[chave]

        resultados[conta_id] = resultado
        return resultado

    linhas = []
    for conta in contas:
        resultado = resultado_de(conta.id)
        if nivel is not None and nivel_de(conta.id) > nivel:
            continue
        linhas.append(
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                "nivel": nivel_de(conta.id),
                "analitica": conta.aceita_lancamento,
                **resultado,
            }
        )

    # O total soma SÓ as analíticas (nunca as sintéticas — contaria o mesmo
    # valor duas vezes, e ainda assim "fecharia", porque débito e crédito
    # dobrariam igualmente; erro que passa despercebido sem teste dedicado,
    # critério 5) e SEMPRE sobre o conjunto COMPLETO de contas, independente
    # de `nivel`: o parâmetro só decide o que é EXIBIDO, nunca o que é
    # somado — do contrário o total deixaria de bater com o Diário do mesmo
    # período (critério 7) sempre que alguém pedisse um `nivel` que corta
    # contas profundas da lista.
    total_debitos = sum(
        (resultado_de(c.id)["debitos"] for c in contas if c.aceita_lancamento), zero
    )
    total_creditos = sum(
        (resultado_de(c.id)["creditos"] for c in contas if c.aceita_lancamento), zero
    )

    return {"contas": linhas, "total_debitos": total_debitos, "total_creditos": total_creditos}


def localizar_lotes_desbalanceados(*, empresa):
    """Lançamentos da empresa cuja soma de débitos difere da de créditos (BL-64).

    Sem período: uma base torta é torta em qualquer recorte de datas. Em
    operação normal, `criar_lancamento` IMPEDE que isto exista — esta busca
    existe para achar o que foi gravado por um caminho que não passou por
    ele (ex.: acesso direto ao ORM em uma migração de dados ou um bug em
    código futuro), não para validar o fluxo normal.

    `total_debito`/`total_credito` chegam como atributos anotados em cada
    `LancamentoContabil` (uma única consulta, soma condicional por filtro —
    mesmo padrão de `apurar_balancete`, sem N+1). Quem chama calcula
    `diferenca = total_debito - total_credito` (positivo quando o débito
    excede o crédito, negativo no caso contrário — preserva a direção do
    desbalanceamento, útil para quem for investigar).
    """
    zero = Decimal("0")
    return (
        LancamentoContabil.objects.filter(empresa=empresa)
        .annotate(
            total_debito=Sum(
                "itens__valor",
                filter=Q(itens__tipo=TipoPartida.DEBITO),
                default=zero,
                output_field=_CAMPO_SOMA_MONETARIA,
            ),
            total_credito=Sum(
                "itens__valor",
                filter=Q(itens__tipo=TipoPartida.CREDITO),
                default=zero,
                output_field=_CAMPO_SOMA_MONETARIA,
            ),
        )
        .exclude(total_debito=F("total_credito"))
        .order_by("data", "criado_em", "id")
    )
