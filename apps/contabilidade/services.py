import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, F, Q, Sum
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


class HierarquiaInconsistente(Exception):
    """O plano de contas tem um ciclo ou uma referência de hierarquia inválida.

    Levantada por `_construir_hierarquia` (achado 6 da auditoria da DL-015,
    rodada 1): antes desta exceção existir, um ciclo na hierarquia
    (`A.conta_pai = B`, `B.conta_pai = A`, inclusive uma conta apontando para
    si mesma) derrubava o Balancete e o Razão com `RecursionError` — um 500
    sem nenhuma pista de qual conta está errada — e uma `conta_pai` que
    aponta para conta de OUTRA empresa (só alcançável por ORM/SQL direto,
    contornando a validação da camada 3) derrubava com `KeyError`. A
    mensagem desta exceção NOMEIA a conta e o problema, para que a view
    devolva uma resposta controlada (409) em vez de um 500 mudo, e para que
    a conferência (BL-64) consiga apontar o problema em vez de quebrar.
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


def _construir_hierarquia(contas):
    """A partir de uma lista de `Conta` da MESMA empresa, monta o mapa de
    filhos e a função de nível, com proteção contra ciclo e contra
    `conta_pai` apontando para fora da lista (ex.: conta de outra empresa,
    alcançável só por ORM/SQL direto) — achado 6 da auditoria da DL-015,
    rodada 1.

    Levanta `HierarquiaInconsistente`, NOMEANDO a conta e o problema, no
    lugar de deixar a recursão estourar em `RecursionError` (ciclo,
    inclusive conta pai de si mesma) ou `KeyError` (pai fora da lista) —
    nunca um 500 sem explicação. A validação acontece para TODA conta da
    lista, aqui, antes de qualquer outra recursão (soma de saldos, Razão de
    sintética) — se houver ciclo ou pai órfão em qualquer conta, falha
    AGORA, não a meio caminho de outro cálculo.

    Devolve `(contas_por_id, filhos_de, nivel_de)`: `nivel_de(conta_id)` é
    memoizado (toda a árvore já está em memória, então subir até a raiz não
    custa consulta nenhuma, só Python).

    Usada por `apurar_balancete` e `localizar_inconsistencias_de_hierarquia`
    (achado 9 da conferência), que PRECISAM do nível/da árvore completa da
    empresa para listar TODAS as contas. `apurar_razao` NÃO usa mais esta
    função (achados novos 10 e 14, rodada 2 da auditoria): o Razão só
    precisa da subárvore da conta consultada, e usa `_descendentes_de`, que
    busca no banco por nível em vez de carregar o plano de contas inteiro.
    """
    contas_por_id = {conta.id: conta for conta in contas}
    filhos_de = defaultdict(list)
    for conta in contas:
        if conta.conta_pai_id is not None:
            filhos_de[conta.conta_pai_id].append(conta.id)

    niveis = {}

    def nivel_de(conta_id, visitando=frozenset()):
        if conta_id in niveis:
            return niveis[conta_id]
        if conta_id in visitando:
            conta = contas_por_id[conta_id]
            raise HierarquiaInconsistente(
                f"Ciclo detectado na hierarquia de contas envolvendo a conta "
                f"{conta.codigo} ({conta.nome})."
            )
        conta = contas_por_id[conta_id]
        if conta.conta_pai_id is None:
            nivel = 1
        elif conta.conta_pai_id not in contas_por_id:
            raise HierarquiaInconsistente(
                f"A conta {conta.codigo} ({conta.nome}) tem uma conta pai que "
                "não pertence a esta empresa."
            )
        else:
            nivel = 1 + nivel_de(conta.conta_pai_id, visitando | {conta_id})
        niveis[conta_id] = nivel
        return nivel

    for conta in contas:
        nivel_de(conta.id)

    return contas_por_id, filhos_de, nivel_de


def _descendentes_de(conta, empresa):
    """{conta.id} ∪ todos os ids descendentes (qualquer profundidade), buscados
    NO BANCO por nível da árvore — NUNCA carrega o plano de contas inteiro da
    empresa (achados novos 10 e 14 da auditoria da DL-015, rodada 2).

    Antes desta correção, `apurar_razao` chamava `_construir_hierarquia` sobre
    TODAS as contas da empresa só para consolidar UMA conta e sua subárvore —
    o que (a) custava uma consulta que crescia com o plano de contas inteiro
    (achado 10) e (b) fazia um ciclo em QUALQUER ramo do plano derrubar o
    Razão de QUALQUER conta, mesmo uma sem relação nenhuma com o ciclo
    (achado 14: um erro em "4"/"4.1" tornava indisponível até o Razão de
    "1.1 Caixa"). O Razão nunca precisou saber de ANCESTRAIS nem de nível —
    só de quais contas são descendentes da conta consultada, para decidir se
    consolida (DE-022) e o que somar.

    Cada iteração deste laço busca só os FILHOS DIRETOS do nível anterior
    (uma consulta por nível de profundidade da SUBÁRVORE consultada, não da
    empresa inteira) — para a conta folha, o caso mais comum, é UMA única
    consulta que devolve zero filhos.

    Levanta `HierarquiaInconsistente`, nomeando a conta, se encontrar um
    ciclo alcançável a partir desta conta (ela mesma reaparecendo como sua
    própria descendente) — nunca um laço infinito nem um 500 mudo.
    """
    ids = {conta.id}
    nivel_atual = [conta.id]
    while nivel_atual:
        filhos_ids = list(
            Conta.objects.filter(empresa=empresa, conta_pai_id__in=nivel_atual).values_list(
                "id", flat=True
            )
        )
        proximo_nivel = []
        for filho_id in filhos_ids:
            if filho_id in ids:
                raise HierarquiaInconsistente(
                    "Ciclo detectado na hierarquia de contas ao consolidar as "
                    f"descendentes da conta {conta.codigo} ({conta.nome})."
                )
            ids.add(filho_id)
            proximo_nivel.append(filho_id)
        nivel_atual = proximo_nivel
    return ids


def apurar_razao(*, conta, empresa, inicio, fim):
    """Apura o Razão de uma conta no período [inicio, fim] (BL-60).

    `saldo_anterior` (critério 3) é a soma de TODOS os itens da conta com
    data anterior a `inicio` — sem limite inferior, "desde sempre" — já com
    o sinal da natureza da conta. A coluna `saldo`, de cada linha do
    período, acumula a PARTIR do saldo anterior, nunca de zero.

    Consolidação (achado 8 / DE-020, corrigida pela DE-022 — achado novo 1 da
    rodada 2): o Razão CONSOLIDA sempre que a conta TIVER DESCENDENTES —
    nunca mais pela permissão de lançamento (`aceita_lancamento`). Antes desta
    correção, o critério era `not conta.aceita_lancamento`, e o Balancete já
    somava "movimento próprio + descendentes" para QUALQUER conta desde a
    DE-020: uma conta que ACEITA lançamento e TEM filhas (estado que a API
    cria pelo valor padrão de `aceita_lancamento`, sem exigir nada
    inconsistente — DE-022 explica por que este estado não é proibido)
    aparecia no Balancete com o total consolidado e, no Razão da MESMA
    conta, MESMO período, com zero — porque o Razão nunca entrava no ramo de
    consolidação. Agora os dois critérios são o MESMO: "tem descendentes".
    O sinal aplicado a CADA item, mesmo vindo de uma descendente com
    natureza diferente (ex.: retificadora), é sempre o da conta CONSULTADA
    (o grupo) — mesma decisão do achado 3: a natureza do grupo é aplicada
    uma única vez, nunca a de cada descendente (achado novo 9).

    `empresa` é exigida explicitamente (achado 10): os itens considerados
    são sempre filtrados também por `lancamento__empresa=empresa`, nunca só
    pela conta — um `ItemLancamento` corrompido (conta de uma empresa,
    lançamento de outra, só alcançável por ORM direto) não pode aparecer no
    Razão de ninguém. Isto vale TANTO para o saldo anterior quanto para o
    período (achado novo 5: a primeira correção só cobriu o período).

    Devolve um dict com `consolidado` (bool), `saldo_anterior`, `itens`
    (lista de dicts com `lancamento_id`, `data`, `historico`, `conta`,
    `conta_nome`, `tipo`, `valor`, `saldo`, todos com valores em `Decimal` —
    a formatação para string de moeda é responsabilidade da view),
    `total_debito`, `total_credito` (do período) e `saldo_final`.
    """
    zero = Decimal("0")

    # `_descendentes_de` busca SÓ a subárvore da conta consultada (achados
    # novos 10 e 14) — nunca a árvore inteira da empresa. `consolidado` é
    # exatamente "esta conta tem descendentes" (DE-022): `ids_contas` sempre
    # contém a própria conta, então ter mais de um id É ter descendentes.
    ids_contas = _descendentes_de(conta, empresa)
    consolidado = len(ids_contas) > 1

    # Uma única consulta agregada para o saldo anterior: soma condicional de
    # débito e crédito separadamente (CASE/WHEN dentro do próprio SUM), sem
    # depender de iterar item a item — o Razão de uma conta com histórico
    # longo não precisa carregar tudo em memória só para este número.
    anteriores = ItemLancamento.objects.filter(
        conta_id__in=ids_contas, lancamento__empresa=empresa, lancamento__data__lt=inicio
    ).aggregate(
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
            conta_id__in=ids_contas,
            lancamento__empresa=empresa,
            lancamento__data__gte=inicio,
            lancamento__data__lte=fim,
        )
        .select_related("lancamento", "conta")
        .order_by("lancamento__data", "lancamento__criado_em", "id")
    )

    saldo = saldo_anterior
    total_debito = zero
    total_credito = zero
    linhas = []
    for item in itens_periodo:
        # Sinal SEMPRE pela natureza da conta CONSULTADA (o grupo, quando
        # consolidado) — nunca pela do item.conta individual. Ver docstring.
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
                "conta": item.conta.codigo,
                "conta_nome": item.conta.nome,
                "tipo": item.tipo,
                "valor": item.valor,
                "saldo": saldo,
            }
        )

    return {
        "consolidado": consolidado,
        "saldo_anterior": saldo_anterior,
        "itens": linhas,
        "total_debito": total_debito,
        "total_credito": total_credito,
        "saldo_final": saldo,
    }


def apurar_balancete(*, empresa, inicio, fim, nivel=None):
    """Apura o Balancete de verificação da empresa no período [inicio, fim] (BL-61).

    Quatro colunas CONSOLIDADAS por conta (saldo_anterior, débitos, créditos,
    saldo_final) mais duas colunas PRÓPRIAS (débitos_proprios,
    creditos_proprios — achado novo 3 da rodada 3 / DE-024 §2, ver comentário
    junto do `append` abaixo). `nivel` é opcional: ausente, devolve todas as
    contas (analíticas e sintéticas); presente, devolve só as contas com
    nível <= `nivel` (raiz = nível 1) — mas o TOTAL da resposta continua
    somando TODOS os itens do período da empresa, sem recorte (ver
    comentário perto do `return`).

    Regra ÚNICA de saldo (achados 2, 3 e 7 / DE-020): o saldo de QUALQUER
    conta é o movimento próprio dela MAIS o das descendentes — não depende
    de `aceita_lancamento`. Isso substitui a decisão antiga ("sintética soma
    os filhos, analítica lê os próprios itens, nunca as duas coisas"), que
    fazia o valor desaparecer quando o estado do dado fugia da hipótese:
    conta com movimento reclassificada como sintética (achado 2), ou conta
    analítica que também tem filhas (achado 7). Débitos e créditos são
    acumulados BRUTOS (sem sinal) na recursão, e a natureza da CONTA QUE ESTÁ
    SENDO APRESENTADA é aplicada uma ÚNICA vez, no fim — nunca a de cada
    descendente. Isto corrige também o achado 3 (grupo com conta
    retificadora): antes, o ramo sintético somava os saldos já assinados dos
    filhos, então uma retificadora (natureza oposta à do grupo) ENTRAVA
    somando em vez de subtrair, e a linha do grupo ficava internamente
    contraditória (`saldo_final` não batia com `saldo_anterior ± (debitos −
    creditos)` usando a própria natureza do grupo). Agora bate, em toda
    linha, analítica ou sintética.

    Isso significa que uma conta com permissão de lançamento e filhas
    (achado 7, e achado novo 1 quando a permissão continua `True`) soma o
    próprio movimento MAIS o das filhas — deixa de ser um estado "impossível"
    que descartava o valor das filhas em silêncio.

    O campo `analitica` de cada linha (DE-022, achado novo 1) significa
    CONTA SEM DESCENDENTES — nunca mais `aceita_lancamento`. Antes desta
    correção, o Balancete usava `aceita_lancamento` para "analitica" e o
    Razão usava o MESMO campo para decidir se consolidava: uma conta que
    aceita lançamento e tem filhas aparecia aqui com o total consolidado
    (próprio + descendentes, regra já vigente pela DE-020) e marcada
    `analitica: true` — então somar as linhas marcadas como analíticas
    contava o valor da conta E o das filhas separadamente, e o total dava o
    DOBRO do rodapé. Ver `apurar_razao`, que usa o MESMO critério
    ("tem descendentes") para decidir quando consolidar — as duas saídas
    agora concordam sobre o que "analítica" significa.

    O TOTAL da resposta (`total_debitos`/`total_creditos`) deixa de ser a
    soma das LINHAS exibidas: passa a ser a soma de TODOS os itens do
    período da empresa, em uma agregação PRÓPRIA (uma única consulta, sem
    depender da árvore de contas estar bem formada nem do parâmetro `nivel`).
    Assim `total_debitos == total_creditos` nunca depende de arranjo de
    hierarquia — é a partida dobrada dos LANÇAMENTOS aparecendo direto na
    saída, não uma soma derivada que pode se perder.

    Hierarquia inconsistente (ciclo, conta_pai de outra empresa — achado 6):
    levanta `HierarquiaInconsistente` (nomeando a conta), NUNCA deixa a
    recursão virar um 500 sem explicação — a view converte isto numa
    resposta controlada.

    Sem N+1 (critério 12): a árvore de contas é carregada em UMA consulta, os
    totais de débito/crédito (antes do período e dentro dele) de TODAS as
    contas vêm de UMA ÚNICA consulta agregada por conta, e o total geral vem
    de mais UMA consulta agregada — nenhuma delas cresce com o número de
    contas.
    """
    zero = Decimal("0")
    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    if not contas:
        return {"contas": [], "total_debitos": zero, "total_creditos": zero}

    # Valida a hierarquia inteira ANTES de qualquer recursão de saldo
    # (achado 6): ciclo ou conta_pai de outra empresa falha aqui, nomeando a
    # conta, nunca um RecursionError/KeyError mais adiante.
    contas_por_id, filhos_de, nivel_de = _construir_hierarquia(contas)

    # A ÚNICA consulta agregada de valores POR CONTA: filtra por
    # `data <= fim` (itens posteriores ao período não interessam a NENHUMA
    # das quatro colunas) e separa, por conta, quatro somas condicionais —
    # anterior a `inicio` (para saldo_anterior) e dentro do período (para
    # débitos/créditos). O filtro de "período" só precisa checar o limite
    # INFERIOR porque o filtro externo já garante o limite superior.
    # `lancamento__empresa=empresa` (além de `conta__empresa=empresa`,
    # achado 10) fecha os dois lados do escopo: um `ItemLancamento`
    # corrompido cuja conta é desta empresa mas cujo lançamento é de outra
    # (só alcançável por ORM direto) não entra na soma de nenhuma das duas.
    agregados_por_conta = {
        linha["conta"]: linha
        for linha in (
            ItemLancamento.objects.filter(
                conta__empresa=empresa, lancamento__empresa=empresa, lancamento__data__lte=fim
            )
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

    brutos = {}

    def bruto_de(conta_id):
        """Débitos/créditos BRUTOS (sem sinal) do movimento próprio da conta
        MAIS o de todas as descendentes, recursivamente — regra única de
        saldo (DE-020). Sem sinal de propósito: a natureza só é aplicada
        pelo chamador, uma única vez, com a natureza da conta que está
        sendo apresentada (ver docstring de `apurar_balancete`, achado 3).
        """
        if conta_id in brutos:
            return brutos[conta_id]

        agregado = agregados_por_conta.get(conta_id, linha_vazia)
        resultado = {
            "debito_anterior": agregado["debito_anterior"],
            "credito_anterior": agregado["credito_anterior"],
            "debito_periodo": agregado["debito_periodo"],
            "credito_periodo": agregado["credito_periodo"],
        }
        for filho_id in filhos_de.get(conta_id, []):
            filho = bruto_de(filho_id)
            for chave in resultado:
                resultado[chave] += filho[chave]

        brutos[conta_id] = resultado
        return resultado

    linhas = []
    for conta in contas:
        bruto = bruto_de(conta.id)
        if nivel is not None and nivel_de(conta.id) > nivel:
            continue
        saldo_anterior = _saldo_por_natureza(
            bruto["debito_anterior"], bruto["credito_anterior"], conta.natureza
        )
        debitos = bruto["debito_periodo"]
        creditos = bruto["credito_periodo"]
        saldo_final = saldo_anterior + _saldo_por_natureza(debitos, creditos, conta.natureza)

        # Achado novo 3 da auditoria (rodada 3) / DE-024 §2: além do
        # CONSOLIDADO acima (própria conta + TODAS as descendentes), cada
        # linha declara também o movimento PRÓPRIO — o que foi lançado
        # DIRETAMENTE nesta conta, sem o das descendentes. É sobre este
        # valor, não sobre o consolidado, que a soma das linhas reconcilia
        # com o rodapé: a soma dos PRÓPRIOS de todas as linhas EXIBIDAS é
        # sempre `total_debitos`/`total_creditos`, porque todo lançamento é
        # próprio de EXATAMENTE uma conta (nunca de duas, nunca de nenhuma).
        # A DE-022 dizia que "analítica" (folha) resolvia essa soma — não
        # resolvia quando a conta tem movimento próprio E filhas (o valor
        # próprio do grupo não aparecia em folha nenhuma); esta é a correção.
        #
        # SEM filtro de `nivel`: "próprio" é o bruto da própria conta MENOS
        # o bruto de cada filho DIRETO — o que sobra é exatamente o valor
        # gravado nesta conta antes de somar qualquer descendente (o mesmo
        # que `agregados_por_conta` traria sem a recursão de `bruto_de`).
        #
        # COM filtro de `nivel`: uma conta na BORDA do corte (cujo filho
        # ficou de fora da exibição por estar mais profundo que `nivel`)
        # precisa ABSORVER o movimento do que não é exibido — senão a soma
        # das linhas EXIBIDAS ficaria menor que o rodapé exatamente pelo
        # valor que foi cortado da lista. Por isso só se subtrai o bruto de
        # um filho quando esse filho TAMBÉM está sendo exibido
        # (`nivel_de(filho) <= nivel`); o que não é subtraído permanece
        # dentro do "próprio" do ancestral visível mais profundo. Com
        # `nivel=None` (tudo exibido) a fórmula se reduz ao caso simples
        # acima, porque todo filho é sempre "exibido".
        filhos_exibidos_ids = [
            filho_id
            for filho_id in filhos_de.get(conta.id, [])
            if nivel is None or nivel_de(filho_id) <= nivel
        ]
        debitos_proprios = debitos - sum(
            (brutos[filho_id]["debito_periodo"] for filho_id in filhos_exibidos_ids), zero
        )
        creditos_proprios = creditos - sum(
            (brutos[filho_id]["credito_periodo"] for filho_id in filhos_exibidos_ids), zero
        )

        linhas.append(
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                "nivel": nivel_de(conta.id),
                # DE-022 (achado novo 1, rodada 2): "analítica" significa
                # CONTA SEM DESCENDENTES (folha da árvore) — não depende de
                # `aceita_lancamento`. Não é mais o critério para somar
                # linhas sem contar valor em dobro (ver `debitos_proprios`/
                # `creditos_proprios` acima) — continua útil para quem quer
                # saber se a conta tem descendentes.
                "analitica": conta.id not in filhos_de,
                "saldo_anterior": saldo_anterior,
                "debitos": debitos,
                "creditos": creditos,
                "debitos_proprios": debitos_proprios,
                "creditos_proprios": creditos_proprios,
                "saldo_final": saldo_final,
            }
        )

    # O total NÃO é mais a soma das linhas (nem só das analíticas): é a soma
    # de TODOS os itens do período da empresa, em agregação PRÓPRIA — uma
    # única consulta, independente da árvore de contas e do parâmetro
    # `nivel` (DE-020). Isto garante `total_debitos == total_creditos`
    # SEMPRE, porque é a mesma partida dobrada dos lançamentos de origem,
    # não um valor derivado que pode se perder num arranjo de hierarquia
    # inesperado.
    totais = ItemLancamento.objects.filter(
        conta__empresa=empresa,
        lancamento__empresa=empresa,
        lancamento__data__gte=inicio,
        lancamento__data__lte=fim,
    ).aggregate(
        debitos=Sum(
            "valor",
            filter=Q(tipo=TipoPartida.DEBITO),
            default=zero,
            output_field=_CAMPO_SOMA_MONETARIA,
        ),
        creditos=Sum(
            "valor",
            filter=Q(tipo=TipoPartida.CREDITO),
            default=zero,
            output_field=_CAMPO_SOMA_MONETARIA,
        ),
    )

    return {
        "contas": linhas,
        "total_debitos": totais["debitos"],
        "total_creditos": totais["creditos"],
    }


def localizar_lotes_desbalanceados(*, empresa):
    """Lançamentos da empresa com menos de duas partidas OU débito diferente
    de crédito (BL-64, achado 9).

    Sem período: uma base torta é torta em qualquer recorte de datas. Em
    operação normal, `criar_lancamento` IMPEDE que isto exista — esta busca
    existe para achar o que foi gravado por um caminho que não passou por
    ele (ex.: acesso direto ao ORM em uma migração de dados ou um bug em
    código futuro), não para validar o fluxo normal.

    Antes desta correção, um lote SEM NENHUM item somava débito=crédito=0 e
    escapava da conferência (achado 9) — pior, ainda ocupava uma linha
    numerada no Diário, como um "fato contábil" que não representa nada.
    Agora, `quantidade_itens` (contagem de itens do lote, na MESMA consulta
    agregada) entra na condição: um lote com MENOS de duas partidas é
    sinalizado mesmo que débito e crédito coincidam por acaso (0 == 0).

    `total_debito`/`total_credito`/`quantidade_itens` chegam como atributos
    anotados em cada `LancamentoContabil` (uma única consulta, sem N+1).
    Quem chama decide o `motivo` — TRÊS vias, não duas (achado novo 12):
    "sem_partidas" (zero itens), "partida_unica" (exatamente um item, que é
    NECESSARIAMENTE desbalanceado, mas por um motivo diferente de "duas ou
    mais partidas cuja soma não fecha" — antes da correção, as duas
    situações compartilhavam o rótulo "sem_partidas", e um lote com uma
    partida de 5,00 aparecia rotulado "sem_partidas" na MESMA linha em que o
    total mostrava 5,00, contradizendo a si mesmo) e "desbalanceado" (duas
    ou mais partidas com débito ≠ crédito) — e calcula
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
            quantidade_itens=Count("itens", distinct=True),
        )
        .exclude(Q(quantidade_itens__gte=2) & Q(total_debito=F("total_credito")))
        .order_by("data", "criado_em", "id")
    )


def localizar_contas_sinteticas_com_movimento(*, empresa):
    """Contas marcadas como sintéticas (`aceita_lancamento=False`) que já
    têm itens de lançamento próprios (achado 2 / DE-020, BL-64).

    Deixou de ser um bug de CÁLCULO — a regra única de saldo do Balancete
    (`apurar_balancete`) soma o movimento próprio de qualquer conta mais o
    das descendentes, então o valor não desaparece mais — mas continua
    sendo uma inconsistência de CLASSIFICAÇÃO que vale apontar: uma conta
    sintética não deveria ter recebido lançamento direto.
    `Conta.clean()` passou a recusar isto para alterações NOVAS feitas pelo
    caminho validado (guarda de dado); esta função existe para achar o que
    já está gravado (dado anterior à guarda, ou alterado por fora dela, ex.:
    `.update()` direto no ORM).
    """
    zero = Decimal("0")
    return list(
        Conta.objects.filter(
            empresa=empresa, aceita_lancamento=False, itens_lancamento__isnull=False
        )
        .distinct()
        .annotate(
            debitos=Sum(
                "itens_lancamento__valor",
                filter=Q(itens_lancamento__tipo=TipoPartida.DEBITO),
                default=zero,
                output_field=_CAMPO_SOMA_MONETARIA,
            ),
            creditos=Sum(
                "itens_lancamento__valor",
                filter=Q(itens_lancamento__tipo=TipoPartida.CREDITO),
                default=zero,
                output_field=_CAMPO_SOMA_MONETARIA,
            ),
        )
    )


def localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(*, empresa):
    """Contas que ACEITAM lançamento direto e TÊM contas subordinadas
    (DE-022, achado novo 1 — quarta categoria da conferência, BL-64).

    NÃO é erro nem é bloqueado: a DE-022 decide explicitamente NÃO proibir
    este estado — planos de contas importados de outros escritórios chegam
    assim, e a regra única de saldo (DE-020) já garante que o valor não se
    perde nem duplica, e o Razão e o Balancete já concordam sobre quando
    consolidar (mesmo critério: "tem descendentes"). Esta categoria existe
    para o contador ENXERGAR o caso e decidir se quer reclassificar a
    permissão de lançamento — não para impedir nada.

    Devolve lista vazia se a hierarquia estiver inconsistente (ciclo,
    `conta_pai` de outra empresa): esse problema já é reportado por
    `localizar_inconsistencias_de_hierarquia` (achado 6); esta função nunca
    deve derrubar a conferência com 500 por causa dele.
    """
    contas = list(Conta.objects.filter(empresa=empresa))
    try:
        _, filhos_de, _ = _construir_hierarquia(contas)
    except HierarquiaInconsistente:
        return []
    return [conta for conta in contas if conta.aceita_lancamento and filhos_de.get(conta.id)]


def localizar_inconsistencias_de_hierarquia(*, empresa):
    """Varre a árvore de contas da empresa (achado 6, BL-64) e devolve TODAS
    as mensagens de inconsistência encontradas — ciclo ou `conta_pai` de
    outra empresa — vazia numa base sadia.

    Achado novo 13 (rodada 2): antes, esta função delegava a
    `_construir_hierarquia`, que LEVANTA na primeira inconsistência
    encontrada — correto para o caminho de CÁLCULO (Balancete, Razão: não dá
    para continuar computando saldo com uma árvore quebrada, então falhar
    cedo é a escolha certa), mas errado para a CONFERÊNCIA, cujo propósito é
    justamente listar tudo que está torto de uma vez. Um plano com dois
    ciclos independentes reportava só o primeiro, e corrigir o plano virava
    tentativa e erro (corrige um, reemite, descobre o próximo).

    Algoritmo: para cada conta ainda não resolvida, sobe pela cadeia de
    `conta_pai` marcando o caminho percorrido (`no_caminho`). Encontrar uma
    conta já em `no_caminho` fecha um ciclo (reportado UMA vez, nomeando a
    conta onde o laço se fechou); encontrar um `conta_pai` fora do mapa da
    empresa é o órfão (achado 6). Encontrar uma conta já `visitado` (de um
    percurso anterior, sem problema) termina o percurso ATUAL sem reportar
    nada — evita reprocessar a mesma cadeia várias vezes e, mais importante,
    evita reportar o MESMO ciclo mais de uma vez (todo o caminho percorrido
    entra em `visitado` ao final de cada percurso, com ou sem problema).
    NUNCA deixa `HierarquiaInconsistente` subir — o problema é dado, não
    exceção.
    """
    contas = list(Conta.objects.filter(empresa=empresa))
    contas_por_id = {conta.id: conta for conta in contas}
    mensagens = []
    visitado = set()

    for conta in contas:
        if conta.id in visitado:
            continue

        caminho = []
        no_caminho = set()
        atual = conta
        problema = None
        while True:
            if atual.id in no_caminho:
                problema = (
                    "Ciclo detectado na hierarquia de contas envolvendo a conta "
                    f"{atual.codigo} ({atual.nome})."
                )
                break
            if atual.id in visitado:
                # Este percurso desemboca numa conta JÁ resolvida (de outro
                # percurso, sem problema) — caminho limpo, nada a reportar.
                break
            caminho.append(atual.id)
            no_caminho.add(atual.id)
            if atual.conta_pai_id is None:
                break
            if atual.conta_pai_id not in contas_por_id:
                problema = (
                    f"A conta {atual.codigo} ({atual.nome}) tem uma conta pai que "
                    "não pertence a esta empresa."
                )
                break
            atual = contas_por_id[atual.conta_pai_id]

        if problema:
            mensagens.append(problema)
        visitado.update(caminho)

    return mensagens
