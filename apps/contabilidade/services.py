import hashlib
import json
import warnings
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count, DecimalField, F, Max, Min, Q, Sum
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.validators import (
    DATA_MINIMA_LANCAMENTO as DATA_MINIMA_LANCAMENTO,
)
from apps.contabilidade.validators import (
    DIAS_FUTUROS_MAXIMOS_LANCAMENTO as DIAS_FUTUROS_MAXIMOS_LANCAMENTO,
)
from apps.contabilidade.validators import (
    LIMITE_PARTIDAS_POR_LANCAMENTO as LIMITE_PARTIDAS_POR_LANCAMENTO,
)
from apps.contabilidade.validators import (
    data_maxima_lancamento as data_maxima_lancamento,
)
from apps.contabilidade.validators import (
    mensagem_de_data_de_lancamento_fora_da_faixa,
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

# RC-77 e RC-79 moram em `apps.contabilidade.validators`, módulo PURO (sem
# ORM), e são REEXPORTADOS aqui — uma definição, um número. O motivo de não
# viverem neste arquivo está no docstring de lá: `models.py` precisa da faixa
# como validador de campo (é o que faz o ADMIN respeitá-la) e não pode
# importar `services.py`, que importa `models.py`.
#
# O reexport não é conveniência gratuita: a tela (`views_web.py`) e os testes
# importam estes nomes de `services`, e este módulo continua sendo o endereço
# de domínio da escrituração. Quem escrever código novo pode usar qualquer um
# dos dois caminhos; quem MUDAR o número mexe num lugar só. A forma
# `from ... import X as X` é o reexport explícito da PEP 484 — é o que diz ao
# ruff, e a quem lê, que o nome está aqui de propósito e não por sobra.


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


class CompetenciaEncerrada(Exception):
    """Lançamento (ou estorno) recusado: a competência de destino já está
    encerrada (RC-57, RC-101; fatia 1 da DL-016, critérios 1 e 2).

    Deliberadamente distinta de `LancamentoInvalido`: o corpo do lançamento
    em si é válido (partidas batem, contas existem) — o que recusa é o
    ESTADO da competência em que ele cairia. A view traduz isto para 409
    (conflito de estado), não 400, mesma distinção que
    `ChaveIdempotenciaConflitante` já aplica. A mensagem sempre NOMEIA a
    competência (mês/ano/empresa) recusada — critério 1 do plano exige que
    o contador saiba QUAL competência está fechada, não só que alguma está.

    Vale IGUALMENTE para lançamento novo e para estorno: `estornar_lancamento`
    chama `criar_lancamento` com a DATA DO ESTORNO (nunca a do original — ver
    o comentário de `estornar_lancamento`), então esta exceção, levantada
    dentro de `criar_lancamento`, já cobre os dois casos sem nenhum código
    especial no estorno (critério 2 do plano).
    """


class CompetenciaOcupada(CompetenciaEncerrada):
    """`criar_lancamento` recusado porque a ESPERA pelo `FOR SHARE` da
    competência estourou o `lock_timeout` do banco (BL-463, achado B1 da
    rodada 2 de auditoria) — nunca porque a competência está de fato
    encerrada. É deliberadamente subclasse de `CompetenciaEncerrada`, não
    uma exceção irmã: a view (`apps/contabilidade/views.py`) já traduz
    aquela classe para 409 com `str(exc)`, e o Python despacha uma
    subclasse pelo `except CompetenciaEncerrada` já existente — sem
    precisar tocar em `views.py`, que nesta etapa é arquivo de outra
    frente (ver o plano DL-031). O DESFECHO para quem chama é o mesmo
    (recusar e orientar a tentar de novo); só a CAUSA muda, e a mensagem
    abaixo (`_mensagem_de_competencia_ocupada`) diz isso explicitamente —
    nunca a frase de "está encerrada", que seria falsa aqui.
    """


class CompetenciaOperacaoInvalida(Exception):
    """Entrada malformada para fechar, reabrir ou marcar como entregue uma
    competência — ex.: motivo de reabertura vazio (critério 5).

    A view traduz para 400: o cliente pode corrigir o que enviou. Contraste
    com `CompetenciaOperacaoRecusada`, abaixo, que é sobre o ESTADO da
    competência/base, não sobre a forma do pedido.
    """


class CompetenciaOperacaoRecusada(Exception):
    """O ESTADO atual da competência (ou da base contábil da empresa) impede
    a transição pedida — ex.: fechar com lote desbalanceado na base
    (critério 3/RC-58), reabrir ou entregar uma competência que não está no
    estado exigido para a operação.

    A view traduz para 409 (conflito), nunca 400: o pedido em si é bem
    formado, o que impede é o que já está gravado. Mesma distinção que
    `ChaveIdempotenciaConflitante` já aplica para lançamento.
    """


class CompetenciaJaEntregue(CompetenciaOperacaoRecusada):
    """Reabertura recusada: a competência já foi entregue ao cliente
    (RC-101, critério 6 do plano). Subclasse de `CompetenciaOperacaoRecusada`
    — mesma tradução HTTP (409) —, com mensagem própria que nomeia a DATA da
    entrega e orienta o ajuste no mês aberto, como o critério exige.
    """


class CompetenciaTravadaPorOutraOperacao(CompetenciaOperacaoRecusada):
    """`encerrar_competencia`, `reabrir_competencia` ou
    `marcar_competencia_como_entregue` recusados porque a espera pelo
    `select_for_update()` da competência estourou o `lock_timeout` do banco
    (BL-463). Mesma técnica de `CompetenciaOcupada` acima: subclasse de
    `CompetenciaOperacaoRecusada` para herdar a tradução HTTP 409 já
    existente na view, sem editar `views.py`. Só acontece quando OUTRA
    transação está segurando a mesma linha por tempo anormal (ex.: um
    fechamento genuinamente travado, ou uma sessão de `psql` esquecida
    aberta) — em operação normal a janela do lock é a de um `UPDATE`
    (BL-463) e nunca chega perto do `lock_timeout`.
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


def validar_data_de_lancamento(data):
    """Aplica a faixa do RC-77 a `data`, levantando `LancamentoInvalido`.

    Julgador de DOMÍNIO, separado da gramática: `apps.core.datas.para_data`
    decide se o TEXTO é uma data (formato, tipo, dia existente) e não sabe
    nada de contabilidade; esta função decide se aquela data é PLAUSÍVEL para
    um lançamento contábil. As duas superfícies chamam a primeira na fronteira
    e esta pelo serviço, e nenhuma das duas repete a faixa.

    A comparação em si — e a mensagem — moram em
    `apps.contabilidade.validators`, que não importa ORM e por isso pode ser
    usado TAMBÉM como validador de campo do modelo (o que faz o admin
    respeitar a faixa). Aqui só se traduz para a exceção de domínio que as
    duas views já convertem em 400.
    """
    mensagem = mensagem_de_data_de_lancamento_fora_da_faixa(data)
    if mensagem is not None:
        raise LancamentoInvalido(mensagem)


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
def obter_ou_criar_competencia(*, empresa, ano, mes):
    """Garante que existe uma `Competencia` para (empresa, ano, mes) e a
    devolve — criando-a como `aberta` (o `default` do campo `estado`) se
    ainda não existir.

    Extraída de `criar_lancamento` (F2 da DL-016) para ser reutilizada pela
    fatia 1 (`encerrar_competencia`, `reabrir_competencia`,
    `marcar_competencia_como_entregue`): fechar um mês que ainda não tem
    NENHUM lançamento é um caso real (RC-53 — implantar uma empresa é
    declarar que tudo antes de uma certa data está fechado), e precisa da
    MESMA linha `Competencia` para gravar o estado. Uma função, um
    tratamento de corrida, reutilizado nos dois lugares — não uma segunda
    cópia do `get_or_create` com seu próprio `except IntegrityError`.

    Trata a corrida de duas transações concorrentes tentando criar a MESMA
    linha pela primeira vez (`get_or_create` pode levantar `IntegrityError`
    quando duas chegam juntas — a `UniqueConstraint(empresa, ano, mes)`
    resolve qual das duas grava primeiro): a perdedora reconsulta por
    `filter().first()` (nunca `.get()`, que levantaria `DoesNotExist` se o
    `IntegrityError` tiver outra causa) dentro da MESMA transação.

    Também é o ponto que faz um `mes`/`ano` fora da faixa das
    `CheckConstraint` de `Competencia.Meta` (`1..12`, `1970..2999`) levantar
    `IntegrityError` — que aqui vira o mesmo `LancamentoInvalido` de
    "competência inconsistente", nunca um 500 cru. As views que expõem
    `ano`/`mes` ao cliente (fechar/reabrir/entregar, `views.py`) validam a
    faixa ANTES de chegar aqui, de propósito — ver `_validar_ano_mes` — para
    que o erro comum (mês digitado errado) vire uma mensagem específica de
    fronteira, e não a mensagem genérica de corrida que sobra para o caso
    realmente raro.
    """
    try:
        with transaction.atomic():
            competencia, _ = Competencia.objects.get_or_create(empresa=empresa, ano=ano, mes=mes)
            return competencia
    except IntegrityError:
        # Corrida: o outro lado gravou primeiro (ou o par ano/mês viola uma
        # CheckConstraint — ver docstring acima). Reconsulta dentro da MESMA
        # transação; se `None` persistir, não é corrida, é dado inválido ou
        # inconsistência real — propaga como erro de domínio, nunca 500.
        competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
        if competencia is None:
            raise LancamentoInvalido(
                f"Não foi possível preparar a competência contábil para {ano}-{mes:02d}: "
                "a empresa informada não existe, o par ano/mês é inválido, ou a corrida "
                "entre requisições deixou a competência em estado inconsistente. Tente "
                "novamente."
            ) from None
        return competencia


# BL-463 (rodada 2 de auditoria, achado B1): `config/settings.py` passou a
# definir `lock_timeout` na conexão PostgreSQL — antes deste ajuste, uma
# espera de lock por qualquer motivo (fechamento genuinamente travado,
# sessão de `psql` esquecida aberta) prendia a requisição INDEFINIDAMENTE,
# até o cliente ou o worker gunicorn (timeout de 30s, sem `--workers`,
# `Dockerfile:36`) desistirem primeiro — e o segundo caminho mata o
# processo com o worker inteiro, sem chance de responder nada legível.
#
# `lock_timeout` transforma essa espera indefinida num erro NOMEADO
# (SQLSTATE 55P03, "lock_not_available") depois de um tempo comedido — mas
# só é seguro definir o timeout se TODO ponto do código que pode esperar
# por aquele lock também SOUBER traduzir esse erro para uma mensagem de
# domínio, em vez de deixar o `OperationalError` cru propagar como 500.
# Esta função compara pelo SQLSTATE (nunca pelo TEXTO da mensagem, que muda com
# o idioma configurado no servidor via `lc_messages`) e é usada pelos
# QUATRO pontos que adquirem lock de competência: o `FOR SHARE` de
# `_travar_competencia_em_modo_compartilhado` (usado por `criar_lancamento`
# — é o lado que a auditoria MEDIU esperando 1,73s na varredura simulada de
# 2s) e o `select_for_update()` de `encerrar_competencia`,
# `reabrir_competencia` e `marcar_competencia_como_entregue`.
def _e_estouro_de_lock_timeout(excecao_de_banco):
    """`True` quando `excecao_de_banco` (um `OperationalError` do Django,
    capturado ao redor de uma consulta que pode esperar por um lock de
    linha) foi causado pelo `lock_timeout` do PostgreSQL estourando — nunca
    por outro motivo de `OperationalError` (conexão caída, servidor fora do
    ar), que deve continuar propagando sem conversão.

    O SQLSTATE `55P03` é a identidade ESTÁVEL do erro (classe 55, "objeto
    não está em estado pré-requisito", código `lock_not_available`;
    documentado no Apêndice A do manual do PostgreSQL) — `psycopg`
    preserva esse código na exceção ORIGINAL do driver, acessível pelo
    encadeamento padrão do Python (`exc.__cause__`, que o `DatabaseWrapper`
    do Django sempre preenche). Comparar pelo SQLSTATE, e não pelo texto da
    mensagem, é o que torna esta checagem independente do idioma do
    servidor (`lc_messages`) e da versão exata da biblioteca cliente.
    """
    causa = excecao_de_banco.__cause__
    return getattr(causa, "sqlstate", None) == "55P03"


def _travar_competencia_em_modo_compartilhado(competencia, *, ano, mes, empresa):
    """Bloqueia a linha de `competencia` com `SELECT ... FOR SHARE` e devolve
    `(estado, entregue_em)` LIDOS NESTA MESMA CONSULTA — nunca os atributos
    do objeto Python já em memória (correção do achado BL-456/A1, rodada 1
    de auditoria da fatia 1: a versão anterior lia o atributo em memória,
    SEM travar a linha, e a auditoria MEDIU 30 gravações em 30 tentativas de
    uma corrida natural, sem nenhuma instrumentação, contra a hipótese
    registrada de "janela estreita").

    `ano`/`mes`/`empresa` são só para a MENSAGEM de erro (nomear a
    competência), nunca para a consulta em si, que sempre trava pelo `pk`
    já resolvido — mesmo contrato de `_travar_competencia_para_transicao`,
    logo abaixo. Correção do achado BLOQUEADOR BL-470 (verificação dirigida
    da DL-031, rodada 1): a versão anterior não recebia estes parâmetros e
    construía a mensagem acessando `competencia.mes`/`competencia.ano`/
    `competencia.empresa` DEPOIS de capturar o `OperationalError`. Os dois
    primeiros são campos escalares já carregados (inofensivos), mas
    `competencia.empresa` é uma FK **não cacheada** neste objeto — ele vem
    de `obter_ou_criar_competencia`, e `get_or_create(empresa=empresa, ...)`
    não popula o cache da relação. Acessá-la disparava uma SEGUNDA consulta
    SQL, e essa consulta roda numa transação PostgreSQL já **abortada** pelo
    próprio estouro do `FOR SHARE` (o `try/except` abaixo não abre um
    savepoint próprio — ver o comentário do `try`), então a segunda consulta
    falhava com `InternalError` ("current transaction is aborted"), que
    SUBSTITUÍA a `CompetenciaOcupada` pretendida e propagava cru até a view
    (500 em produção). A correção é não tocar em NENHUM atributo de
    `competencia` dentro do `except`: usar só os parâmetros já em memória.

    `entregue_em` entrou na MESMA consulta pela correção do achado B6/BL-468
    (rodada 2 de auditoria): a mensagem de `CompetenciaEncerrada` (ver
    `criar_lancamento`, abaixo) precisa saber se a competência já foi
    ENTREGUE para não oferecer "reabra" quando esse caminho já está fechado
    pelo RC-101 — e essa informação está sujeita à MESMA corrida que o
    `estado` (uma entrega pode commitar enquanto este `criar_lancamento`
    espera o `FOR SHARE`, exatamente o cenário do teste
    `test_bl456_reproducao_2_lancamento_concorrente_recusado_em_competencia_entregue`).
    Buscar as duas colunas juntas, sob o mesmo lock, evita reabrir a MESMA
    classe de defeito do BL-456 para um campo novo.

    `FOR SHARE` é um lock COMPARTILHADO: duas transações podem segurá-lo ao
    mesmo tempo sobre a MESMA linha — por isso dois lançamentos do MESMO mês
    não se bloqueiam um ao outro, e a escrituração normal continua
    concorrente. Mas ele CONFLITA com `FOR UPDATE` — o lock que
    `select_for_update()` emite, e que `encerrar_competencia`,
    `reabrir_competencia` e `marcar_competencia_como_entregue` JÁ usam, sem
    nenhuma mudança nelas. Quando uma dessas três está seguindo a linha em
    `FOR UPDATE`, esta consulta FICA BLOQUEADA até aquela transação commitar
    ou reverter — e só então lê o `estado`, já ATUALIZADO (é essa
    "espera, depois lê" que fecha a corrida: nenhuma leitura deste bloco
    acontece antes do fechamento concorrente ter terminado). Precisa rodar
    DENTRO de uma transação já aberta pelo chamador — `criar_lancamento`
    garante isso.

    Medição de custo (rodada 2 da auditoria, achado BL-456): comparei, com
    threads reais e conexões PostgreSQL reais, N lançamentos concorrentes no
    MESMO mês com `FOR SHARE` (esta função) contra a alternativa mais simples
    (`select_for_update()` também no lançamento, que serializa todo mundo).
    Números no relatório de entrega da rodada 2 — `FOR SHARE` não serializa
    lançamentos entre si; `select_for_update()` serializa, com o tempo total
    crescendo linearmente com N. Por isso esta é a escolha, não a mais
    simples de escrever.

    Django não expõe `FOR SHARE` por `QuerySet.select_for_update()` (só
    `FOR UPDATE`/`FOR NO KEY UPDATE`), daí o SQL cru — nome de tabela e de
    colunas resolvidos por `_meta`, nunca string fixa, mesmo padrão que
    `apps.contabilidade.models._tem_movimento_proprio_ou_de_descendente` já
    usa pelo mesmo motivo.

    Limite DECLARADO de backend: `FOR SHARE` é sintaxe do PostgreSQL: o
    SQLite (usado só em desenvolvimento local, nunca em produção — DE-014,
    BL-50) não tem row-level locking equivalente e rejeitaria esta consulta.
    Fora do PostgreSQL, esta função cai para `(estado, entregue_em)` já
    carregados em `competencia` — a MESMA leitura desprotegida de antes
    desta correção, documentada como limite de ambiente (mesma família de
    declaração que `apps.core.restricoes._nome_da_constraint_violada`,
    específica de psycopg). A suíte roda contra PostgreSQL
    (`config/settings.py`); a concorrência real só é garantida lá.

    ⚠️ Correção do achado B2/BL-464 (rodada 2 de auditoria): este ramo
    degradava em SILÊNCIO — quem lê o código de fora vê uma trava; em
    outro backend não há trava nenhuma, e nada avisava disso. O limite em
    si já está CONTIDO (`config/settings.py` recusa subir com SQLite e
    `DEBUG=False`, BL-50/DE-014, então produção nunca alcança este ramo) e
    a trava SERIAL continua funcionando fora daqui (a constraint de banco
    e a checagem de estado do objeto recém-lido ainda impedem a maioria
    dos casos práticos) — o que faltava era o AVISO. `RuntimeWarning`,
    mesma classe usada pelo aviso de "SQLite local" em
    `config/settings.py`, para quem sobe localmente sem PostgreSQL saber
    que a garantia de CONCORRÊNCIA (não a trava em si) está ausente.
    """
    if connection.vendor != "postgresql":
        warnings.warn(
            f"_travar_competencia_em_modo_compartilhado degradou para leitura "
            f"em memória (SEM lock) porque a conexão é '{connection.vendor}', "
            "não PostgreSQL: a garantia de CONCORRÊNCIA do BL-456 não vale "
            "aqui, só a checagem serial de estado. Válido apenas em "
            "desenvolvimento local (BL-50/DE-014 já recusa subir com SQLite "
            "e DEBUG=False, então produção nunca alcança este ramo).",
            RuntimeWarning,
            stacklevel=2,
        )
        return competencia.estado, competencia.entregue_em
    tabela = Competencia._meta.db_table
    coluna_id = Competencia._meta.pk.column
    coluna_estado = Competencia._meta.get_field("estado").column
    coluna_entregue_em = Competencia._meta.get_field("entregue_em").column
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {coluna_estado}, {coluna_entregue_em} FROM {tabela} "
                f"WHERE {coluna_id} = %s FOR SHARE",
                [competencia.pk],
            )
            estado, entregue_em = cursor.fetchone()
    except OperationalError as exc:
        # BL-463: a espera por este `FOR SHARE` estourou o `lock_timeout`
        # (ver o comentário acima de `_e_estouro_de_lock_timeout`) — quase
        # sempre porque um `encerrar_competencia`/`reabrir_competencia`/
        # `marcar_competencia_como_entregue` concorrente está segurando o
        # `FOR UPDATE` por tempo anormal. `CompetenciaOcupada` é subclasse
        # de `CompetenciaEncerrada`: a mesma tradução HTTP (409) já existe
        # na view, sem editar `views.py`. Qualquer OUTRO `OperationalError`
        # (conexão caída, servidor fora do ar) propaga sem conversão — não
        # é um caso de negócio, é uma falha de infraestrutura.
        if not _e_estouro_de_lock_timeout(exc):
            raise
        # BL-470: a mensagem usa SÓ `ano`/`mes`/`empresa` — os parâmetros já
        # em memória, recebidos pelo chamador — e NUNCA `competencia.mes`/
        # `competencia.ano`/`competencia.empresa`. Ver o comentário na
        # docstring desta função: acessar a FK `competencia.empresa` aqui
        # dispararia uma consulta na transação já abortada pelo estouro do
        # `FOR SHARE`, e o `InternalError` resultante substituiria esta
        # `CompetenciaOcupada` antes dela sequer ser levantada.
        raise CompetenciaOcupada(
            f"A competência {mes:02d}/{ano} de {empresa} está sendo fechada "
            "por outra operação agora; não foi possível confirmar o estado "
            "dela a tempo. Tente gravar este lançamento novamente em "
            "instantes."
        ) from exc
    return estado, entregue_em


def _travar_competencia_para_transicao(competencia, *, ano, mes, empresa):
    """`select_for_update()` sobre a linha de `competencia`, traduzindo o
    estouro de `lock_timeout` (BL-463; ver o comentário de
    `_e_estouro_de_lock_timeout`) para `CompetenciaTravadaPorOutraOperacao`
    em vez de deixar o `OperationalError` cru do driver propagar como 500.

    Reunida aqui porque as TRÊS transições de estado desta fatia
    (`encerrar_competencia`, `reabrir_competencia`,
    `marcar_competencia_como_entregue`) adquirem o MESMO tipo de lock
    (`FOR UPDATE`) sobre a MESMA tabela pelo mesmo motivo — uma função, uma
    tradução de erro, nunca três cópias divergentes do mesmo `try/except`.
    `ano`/`mes`/`empresa` são só para a MENSAGEM (nomear a competência),
    nunca para a consulta em si, que sempre trava pelo `pk` já resolvido.
    """
    try:
        return Competencia.objects.select_for_update().get(pk=competencia.pk)
    except OperationalError as exc:
        if not _e_estouro_de_lock_timeout(exc):
            raise
        raise CompetenciaTravadaPorOutraOperacao(
            f"A competência {mes:02d}/{ano} de {empresa} está sendo alterada "
            "por outra operação agora; não foi possível travá-la a tempo. "
            "Tente novamente em instantes."
        ) from exc


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

    `historico` e `chave_idempotencia` são recusados (`LancamentoInvalido`)
    se contiverem o caractere nulo (achado R2-4, auditoria DL-017 rodada 2):
    sem esta checagem, o PostgreSQL rejeitaria o INSERT com `DataError`, um
    500 cru — ver o comentário junto da checagem, mais abaixo.

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

    # RC-79 / BL-207: teto de NEGÓCIO, verificado aqui porque este é o ponto
    # por onde a tela e a API passam (ver o comentário de
    # `LIMITE_PARTIDAS_POR_LANCAMENTO`). Recusa NOMEANDO a quantidade
    # recebida e o teto — nunca truncar a lista e gravar um lote menor do
    # que o enviado, que é a perda silenciosa que a BL-91 proíbe e que
    # deixaria o lote desbalanceado em silêncio.
    if len(itens) > LIMITE_PARTIDAS_POR_LANCAMENTO:
        raise LancamentoInvalido(
            f"Um lançamento aceita no máximo {LIMITE_PARTIDAS_POR_LANCAMENTO} partidas; "
            f"foram enviadas {len(itens)}. Nenhuma partida foi gravada — divida o "
            "lançamento ou use importação."
        )

    # RC-77 / BL-205: faixa de data, na mesma função e antes de qualquer
    # gravação. A gramática da data já foi julgada na fronteira de cada
    # superfície (`apps.core.datas.para_data`); o que falta, e que só o
    # domínio sabe, é se a data é plausível — ver `validar_data_de_lancamento`.
    validar_data_de_lancamento(data)

    # Byte nulo (achado R2-4 da auditoria DL-017, rodada 2): o PostgreSQL
    # recusa `\x00` em coluna de texto com `DataError: PostgreSQL text
    # fields cannot contain NUL (0x00) bytes` — um 500 cru, não um erro de
    # domínio. Um navegador não digita NUL num campo de texto; um cliente de
    # integração, um trecho colado de arquivo binário ou um proxy
    # mal-comportado enviam. `historico` e `chave_idempotencia` chegam aqui
    # como texto já lido "à mão" pelas DUAS portas (a tela em
    # `views_web.py` e a API em `views.py`) — nenhuma das duas passa por um
    # `ModelForm`/`ModelSerializer`, que teria essa recusa embutida (é
    # exatamente por que o formulário de CONTA está protegido e este não
    # estava). `criar_lancamento` é o único ponto por onde as duas portas
    # passam para gravar (AGENTS.md §8: não duplicar regra entre tela e
    # API) — verificar aqui, uma vez só, fecha as duas ao mesmo tempo, sem
    # tocar em nenhuma das duas views. Levanta `LancamentoInvalido`, que as
    # duas views já traduzem para 400 com mensagem própria — nunca deixa o
    # `\x00` chegar ao INSERT.
    if "\x00" in historico:
        raise LancamentoInvalido("O histórico não pode conter o caractere nulo (código 0).")
    if chave_idempotencia and "\x00" in chave_idempotencia:
        raise LancamentoInvalido(
            "A chave de idempotência não pode conter o caractere nulo (código 0)."
        )

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
            # DL-016 / F2: garantir que exista uma `Competencia` para o (empresa,
            # ano, mês) do lançamento ESTA linha é o que casa com a estratégia
            # T1=A do plano (criar dentro do service, não via sinal pós-save
            # externo): a mesma transação atômica que grava o lançamento
            # também cria a competência; ou ambos gravam, ou nenhum grava.
            #
            # ⚠️ Correção do achado BL-460/A6 (rodada 2 de auditoria): esta
            # linha dizia existir um sinal `post_save(LancamentoContabil)`
            # como "rede de segurança" para caminhos não-canônicos (ex.:
            # `objects.create` direto). **Esse sinal nunca existiu** —
            # `apps/contabilidade/` não tem `signals.py` nem `AppConfig.
            # ready()`. Quem não passar por `criar_lancamento` não tem
            # competência nem trava nenhuma; não há rede de segurança.
            competencia = obter_ou_criar_competencia(empresa=empresa, ano=data.year, mes=data.month)

            # DL-016 fatia 1 (RC-57, RC-101, RC-103; critérios 1 e 2 do
            # plano): A TRAVA MORA AQUI, no serviço — não na view. Qualquer
            # porta que chame `criar_lancamento` (a API, a tela, o estorno,
            # uma futura importação em lote) herda a recusa sem precisar
            # repeti-la.
            #
            # ⚠️ Correção do achado BLOQUEADOR BL-456/A1 (rodada 1 de
            # auditoria): a versão anterior comparava `competencia.estado`
            # — o atributo do objeto Python já em memória, de uma leitura
            # ANTERIOR a qualquer lock — contra `ENCERRADA`, e um comentário
            # aqui mesmo chamava a ausência de trava de "risco residual,
            # janela de corrida ESTREITA, decisão proporcional". MEDIDO
            # (DE-058: justificativa escrita não é justificativa medida):
            # com duas conexões PostgreSQL reais, sem NENHUMA instrumentação,
            # a corrida gravou lançamento em competência que terminava
            # ENCERRADA em **30 gravações de 30 tentativas** — inclusive em
            # competência já **entregue ao cliente** (RC-19). A janela era,
            # na prática, a duração inteira desta transação.
            #
            # A correção trava a linha com `FOR SHARE`
            # (`_travar_competencia_em_modo_compartilhado`, acima) e usa o
            # `estado` LIDO NAQUELA CONSULTA — nunca mais o atributo em
            # memória. `EM_ENCERRAMENTO` também passou a bloquear (BL-461/
            # A7): a condição é `!= ABERTA`, não mais `== ENCERRADA` — mais
            # segura, e sem efeito prático hoje porque nenhum service desta
            # fatia escreve `EM_ENCERRAMENTO` (ver `EstadoCompetencia`).
            #
            # Estorno (critério 2): `estornar_lancamento` chama esta mesma
            # função com a DATA DO ESTORNO (nunca a do lançamento original —
            # ver o comentário lá), então a competência travada acima já É
            # a do estorno. Nenhum código especial precisa existir para o
            # estorno: o caso "original fechado, estorno em mês aberto" passa
            # (confirmado pelo Fred, RC-57/RC-103), e "estorno cairia em mês
            # fechado" é recusado pela MESMA linha abaixo.
            estado_travado, entregue_em_travado = _travar_competencia_em_modo_compartilhado(
                competencia, ano=data.year, mes=data.month, empresa=empresa
            )
            if estado_travado != EstadoCompetencia.ABERTA:
                nome_do_estado = EstadoCompetencia(estado_travado).label.lower()
                # BL-468 (achado B6, rodada 2 de auditoria): a mensagem
                # ANTES oferecia "reabra a competência (se ela ainda não
                # foi entregue ao cliente)" mesmo quando a competência JÁ
                # tinha sido entregue — o parêntese salvava a frase de ser
                # FALSA, mas ainda apontava um caminho que o RC-101 já
                # fecha (`reabrir_competencia` recusa com
                # `CompetenciaJaEntregue`). `entregue_em_travado` vem da
                # MESMA consulta `FOR SHARE` que leu `estado_travado`
                # (nunca do atributo em memória — mesma correção de
                # classe do BL-456), então a distinção abaixo é segura
                # mesmo sob corrida (é o cenário exato do teste
                # `test_bl456_reproducao_2_..._entregue`).
                if entregue_em_travado is not None:
                    raise CompetenciaEncerrada(
                        f"A competência {data.month:02d}/{data.year} de {empresa} já "
                        "foi entregue ao cliente; não é possível gravar lançamento "
                        "nela e ela não pode ser reaberta (RC-101). Lance o ajuste "
                        "em uma competência ABERTA, com histórico apontando para "
                        f"a competência de origem ({data.month:02d}/{data.year})."
                    )
                raise CompetenciaEncerrada(
                    f"A competência {data.month:02d}/{data.year} de {empresa} está "
                    f"'{nome_do_estado}'; não é possível gravar lançamento nela. Reabra a "
                    "competência ou lance em uma competência aberta."
                )

            lancamento = LancamentoContabil.objects.create(
                empresa=empresa,
                data=data,
                historico=historico,
                criado_por=criado_por,
                estorno_de=estorno_de,
                chave_idempotencia=chave_idempotencia,
                chave_idempotencia_fingerprint=impressao,
                competencia=competencia,
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

    Competência encerrada (DL-016 fatia 1, RC-57, critério 2 do plano): NÃO
    há checagem própria aqui — `criar_lancamento`, chamado no fim desta
    função com `data=data_do_estorno`, já recusa (`CompetenciaEncerrada`) se
    a competência DO ESTORNO estiver encerrada. É deliberado que seja a
    competência do estorno, nunca a do original: a data do estorno é sempre
    "hoje" (ou a data explícita informada), nunca herdada do lançamento
    original — ver a checagem de RC-78 logo abaixo —, então "original em mês
    fechado, estorno em mês aberto" É PERMITIDO (confirmado pelo Fred).
    """
    with transaction.atomic():
        lancamento = LancamentoContabil.objects.select_for_update().get(pk=lancamento.pk)

        if lancamento.estorno_de_id is not None:
            raise LancamentoInvalido("Não é possível estornar um lançamento que já é um estorno.")
        if lancamento.estornos.exists():
            raise LancamentoInvalido("Este lançamento já foi estornado.")

        # RC-78 / BL-206, confirmado pelo Fred em 2026-09-15: o estorno NUNCA
        # pode ser datado antes do lançamento que ele reverte — recusar, e
        # não "permitir desde que registrado" (a escolha foi dele).
        #
        # O defeito medido (achado R6-4c da rodada 6): a data do estorno era
        # `timezone.localdate()` SEMPRE, sem nenhuma comparação com o
        # original. Um lançamento datado no futuro (o que a faixa do RC-77
        # continua permitindo até hoje + 30 dias) estornado hoje produzia um
        # estorno ANTERIOR ao fato, e o Diário mostrava a reversão
        # acontecendo antes do que ela reverte. O mutante que faz o estorno
        # HERDAR a data do original sobrevivia a 766 testes: a regra não
        # tinha teste em NENHUM dos dois sentidos.
        #
        # `data` é calculada aqui, uma vez, e passada explicitamente a
        # `criar_lancamento` — antes o `data or timezone.localdate()` ficava
        # na própria chamada, e por isso não havia onde comparar.
        data_do_estorno = data or timezone.localdate()
        # `validar_data_de_lancamento` ANTES da comparação, e não só por
        # causa do RC-77: é ela que garante que `data_do_estorno` é um
        # `date` puro, sem o que a comparação abaixo poderia estourar
        # `TypeError` cru (texto, `datetime`) em vez de erro de domínio.
        validar_data_de_lancamento(data_do_estorno)
        if data_do_estorno < lancamento.data:
            raise LancamentoInvalido(
                "O estorno não pode ter data anterior à do lançamento que ele "
                f"reverte: o lançamento {lancamento.pk} é de "
                f"{lancamento.data.strftime('%d/%m/%Y')} e o estorno ficaria em "
                f"{data_do_estorno.strftime('%d/%m/%Y')}. Informe uma data igual "
                "ou posterior à do lançamento original."
            )

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
                data=data_do_estorno,
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
# Fechamento, reabertura e entrega de competência (DL-016, fatia 1)
#
# As três funções abaixo são NÍVEL 1 (AGENTS.md §3.1: mexem no livro
# contábil) e implementam, e só implementam, os 12 critérios de aceite da
# fatia 1 do plano DL-016 — nada de tela, filtro nas saídas da DL-015 ou
# política de período de trabalho, que são fatias seguintes.
#
# As três recebem `(empresa, ano, mes)`, não uma `Competencia` já resolvida:
# fechar (RC-53) precisa funcionar mesmo para um mês SEM nenhum lançamento
# ainda — `obter_ou_criar_competencia` garante a linha nos três casos, com o
# mesmo tratamento de corrida que `criar_lancamento` já usa (F2).
# ---------------------------------------------------------------------------


@transaction.atomic
def encerrar_competencia(*, empresa, ano, mes, usuario, request=None):
    """Fecha a competência (ano, mes) da empresa: `aberta -> encerrada`.

    Critério 3 do plano: recusa (`CompetenciaOperacaoRecusada`, 409) se
    houver LOTE DESBALANCEADO na base da empresa (RC-58) — a conferência da
    DL-015 é pré-condição do fechamento, verificada com
    `localizar_lotes_desbalanceados`, que já existe e não tem período (uma
    base torta é torta em qualquer recorte). Grava `fechada_em`/
    `fechada_por` e devolve o objeto com o atributo NÃO PERSISTIDO
    `encerrada_agora` (mesmo padrão de `criado_agora` em `criar_lancamento`):
    `True` só quando esta chamada de fato fechou agora.

    Idempotência (critério 4): se a competência JÁ está `encerrada`, esta
    função é um NO-OP — devolve o objeto como está, com `encerrada_agora =
    False`, SEM tocar `fechada_em`/`fechada_por` (o autor do PRIMEIRO
    fechamento nunca é trocado) e SEM checar lote desbalanceado de novo (a
    checagem só faz sentido na transição, não a cada chamada repetida) e
    SEM gravar novo registro de trilha (ver abaixo) — repetir a chamada não
    duplica a auditoria.

    Concorrência (critério 10): `select_for_update()` bloqueia a linha da
    Competencia durante a transição — duas requisições simultâneas de
    fechamento da MESMA competência produzem UM único fechamento; a segunda,
    ao adquirir o lock depois da primeira commitar, já encontra `encerrada`
    e cai no ramo idempotente. Mesmo padrão que `estornar_lancamento`
    já usa para `estorno_de_unico`. Este MESMO lock (`FOR UPDATE`) é o que
    faz `_travar_competencia_em_modo_compartilhado` (usada por
    `criar_lancamento`) esperar: um lançamento em voo não vê a competência
    "sumir" no meio da gravação (BL-456/A1, rodada 2 de auditoria).

    ⚠️ Correção do achado B1/BL-463 (rodada 2 de auditoria): a ORDEM entre
    a checagem RC-58 (abaixo) e a aquisição do lock foi INVERTIDA. Antes,
    o `select_for_update()` era adquirido primeiro e a varredura da base
    INTEIRA (`localizar_lotes_desbalanceados`, sem período por desenho)
    rodava com a linha travada — depois da correção do BL-456, isso
    passou a bloquear TODO lançamento daquele mês pela duração inteira da
    varredura (medido: 1,73s de espera do lançamento contra uma varredura
    simulada de 2s). A checagem agora roda ANTES do lock, e isso é seguro:
    `criar_lancamento` NUNCA consegue gravar um lote desbalanceado (a
    igualdade débito = crédito é verificada antes de qualquer `save()`),
    então a base não pode ficar torta ENTRE a checagem e o lock — o único
    jeito de um lote desbalanceado existir é por um caminho que já
    contorna a aplicação (ver o docstring de
    `localizar_lotes_desbalanceados`), fora do alcance de qualquer lock
    que esta função pudesse segurar de qualquer forma. Depois da correção,
    a janela do lock caiu para a de um `UPDATE` — ver a medição no
    relatório de entrega desta etapa.

    Um segundo atalho, também sem lock, cobre o caso REPETIDO (critério 4):
    se a leitura em memória de `competencia` (a mesma que
    `obter_ou_criar_competencia` acabou de fazer) já mostra `ENCERRADA`,
    devolve o NO-OP imediatamente, sem pagar nem o lock nem a varredura.
    Essa leitura PODE estar desatualizada — não há problema: é só uma
    OTIMIZAÇÃO. Quem garante a corrida do critério 10 é a releitura de
    baixo, JÁ SOB o `FOR UPDATE`; se o atalho não disparar (leitura
    desatualizada), o código simplesmente segue o caminho de sempre, sem
    NENHUMA perda de correção.

    `lock_timeout` (BL-463, `config/settings.py`): se a espera pelo
    `select_for_update()` estourar — outra transação segurando a linha por
    tempo anormal —, `_travar_competencia_para_transicao` traduz o
    `OperationalError` cru para `CompetenciaTravadaPorOutraOperacao` (409,
    mesma tradução HTTP de `CompetenciaOperacaoRecusada`, da qual é
    subclasse), com mensagem que orienta tentar de novo.

    ⚠️ Correção do achado BL-458/A3 (rodada 2 de auditoria): a trilha de
    auditoria (`registrar()`) passou a ser gravada AQUI, dentro do serviço
    — antes vivia só na view (`apps/contabilidade/views.py`), e qualquer
    chamada direta a este serviço (`shell`, comando de gerência, futuro
    importador ou tarefa em segundo plano) não deixava rastro NENHUM.
    `request` é opcional e só serve para o `registrar()` capturar o
    endereço IP quando existir uma requisição HTTP por trás — usuário e
    escritório são sempre os parâmetros explícitos, nunca inferidos de
    `request`, para que a chamada direta (sem `request`) grave do mesmo
    jeito. `detalhes` carrega `ano`/`mes`/`empresa_id` (BL-459/A4): a
    trilha se basta sozinha, sem precisar consultar a `Competencia` para
    saber qual mês foi fechado.
    """
    competencia = obter_ou_criar_competencia(empresa=empresa, ano=ano, mes=mes)

    # Atalho idempotente SEM lock (BL-463) — ver docstring acima.
    if competencia.estado == EstadoCompetencia.ENCERRADA:
        competencia.encerrada_agora = False
        return competencia

    # RC-58 / critério 3: pré-condição de conferência, rodada ANTES do lock
    # (BL-463) — ver docstring acima para o motivo de ser seguro.
    if localizar_lotes_desbalanceados(empresa=empresa).exists():
        raise CompetenciaOperacaoRecusada(
            f"Não é possível fechar a competência {mes:02d}/{ano} de {empresa}: "
            "há lançamento(s) desbalanceado(s) na base desta empresa. Resolva "
            "a conferência (RC-58) antes de fechar."
        )

    # Só a partir daqui o lock é adquirido (BL-463): a janela que ele
    # segura caiu para o tamanho de um `UPDATE`.
    competencia = _travar_competencia_para_transicao(competencia, ano=ano, mes=mes, empresa=empresa)

    if competencia.estado == EstadoCompetencia.ENCERRADA:
        # Corrida: outra transação fechou a competência ENTRE o atalho sem
        # lock acima e a aquisição do `FOR UPDATE` agora. Não é erro — é o
        # MESMO caminho idempotente, agora com leitura garantida pelo lock
        # (é o que sustenta o critério 10 sob corrida real — ver
        # `test_criterio10_corrida_real_de_fechamento_produz_um_unico_fechamento`).
        competencia.encerrada_agora = False
        return competencia

    competencia.estado = EstadoCompetencia.ENCERRADA
    competencia.fechada_em = timezone.now()
    competencia.fechada_por = usuario
    competencia.save(update_fields=["estado", "fechada_em", "fechada_por"])
    competencia.encerrada_agora = True
    registrar(
        acao="competencia.encerrada",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=competencia,
        request=request,
        detalhes={"ano": ano, "mes": mes, "empresa_id": empresa.id},
    )
    return competencia


@transaction.atomic
def reabrir_competencia(*, empresa, ano, mes, usuario, motivo, request=None):
    """Reabre a competência (ano, mes) da empresa: `encerrada -> aberta`.

    Critério 5: `motivo` é OBRIGATÓRIO — vazio ou só espaço em branco é
    recusado com `CompetenciaOperacaoInvalida` (400), ANTES de qualquer
    consulta com lock, porque é um erro de ENTRADA, não de estado.

    Critério 6 / RC-101: recusa (`CompetenciaJaEntregue`, subclasse de
    `CompetenciaOperacaoRecusada`, 409) se a competência já foi entregue ao
    cliente (`entregue_em` não nulo) — é a decisão de modelagem do
    arquiteto-senior: "entregue" é fato datado e NUNCA se desfaz por esta
    função; a mensagem nomeia a DATA da entrega e orienta o ajuste no mês
    aberto, como o critério exige. Esta checagem vem ANTES da checagem de
    estado abaixo porque é a mais específica das duas — mas na prática
    `entregue_em` só é gravado sobre competência `encerrada`
    (`marcar_competencia_como_entregue` exige isso), então uma competência
    `aberta` nunca chega com `entregue_em` preenchido.

    Fora dos 12 critérios, mas necessário para a função ter sentido: só é
    possível reabrir uma competência que ESTÁ `encerrada` — tentar reabrir
    uma competência `aberta` (nunca foi fechada) é recusado com
    `CompetenciaOperacaoRecusada` (409: o pedido é bem formado, o que
    impede é o estado atual).

    `select_for_update()` (via `_travar_competencia_para_transicao`) pelo
    mesmo motivo de `encerrar_competencia`: embora não haja critério de
    concorrência explícito para reabertura, a escrita do estado precisa
    ler a linha mais recente antes de decidir — e é o mesmo lock que faz
    `criar_lancamento` esperar (ver `_travar_competencia_em_modo_
    compartilhado`). BL-463: se a espera por esse lock estourar o
    `lock_timeout`, a mesma função traduz para
    `CompetenciaTravadaPorOutraOperacao` (409), nunca um `OperationalError`
    cru.

    `fechada_em`/`fechada_por` são LIMPOS (`None`): eles descrevem o
    fechamento ATUAL, que deixou de existir — ver o docstring de
    `Competencia`.

    ⚠️ Correção dos achados BL-458/A3 e BL-459/A4 (rodada 2 de auditoria):
    o `registrar()` mora AQUI agora (era só na view — chamada direta ao
    serviço não deixava NENHUM rastro, e esta é a operação mais afiada das
    três: ela APAGA `fechada_em`/`fechada_por`). `detalhes` carrega
    `ano`/`mes`/`empresa_id` e também `fechada_por_anterior`/
    `fechada_em_anterior` — os valores que estão sendo apagados da linha,
    capturados ANTES do `save()`, para que a trilha preserve "quem tinha
    fechado" mesmo que a própria `Competencia` não preserve mais. Devolve
    só `competencia` agora (antes devolvia `(competencia,
    motivo_normalizado)` — o motivo já vai para `detalhes` aqui dentro, a
    view não precisa mais dele).
    """
    motivo_normalizado = (motivo or "").strip()
    if not motivo_normalizado:
        raise CompetenciaOperacaoInvalida(
            "Informe o motivo da reabertura: não pode ficar em branco."
        )

    competencia = obter_ou_criar_competencia(empresa=empresa, ano=ano, mes=mes)
    competencia = _travar_competencia_para_transicao(competencia, ano=ano, mes=mes, empresa=empresa)

    if competencia.entregue_em is not None:
        raise CompetenciaJaEntregue(
            f"Não é possível reabrir a competência {mes:02d}/{ano} de {empresa}: "
            f"ela já foi entregue ao cliente em "
            f"{timezone.localtime(competencia.entregue_em):%d/%m/%Y %H:%M}. "
            "Depois da entrega, a competência não reabre — a correção vai no mês "
            "aberto, com histórico apontando para esta competência de origem."
        )
    if competencia.estado != EstadoCompetencia.ENCERRADA:
        raise CompetenciaOperacaoRecusada(
            f"Só é possível reabrir uma competência encerrada; a competência "
            f"{mes:02d}/{ano} de {empresa} está '{competencia.get_estado_display()}'."
        )

    # Capturados ANTES do `save()` (BL-459/A4): são os valores que a linha
    # está prestes a PERDER — a trilha precisa deles porque a `Competencia`
    # não vai mais tê-los depois desta transação.
    fechada_por_anterior = competencia.fechada_por_id
    fechada_em_anterior = competencia.fechada_em

    competencia.estado = EstadoCompetencia.ABERTA
    competencia.fechada_em = None
    competencia.fechada_por = None
    competencia.save(update_fields=["estado", "fechada_em", "fechada_por"])
    registrar(
        acao="competencia.reaberta",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=competencia,
        request=request,
        detalhes={
            "ano": ano,
            "mes": mes,
            "empresa_id": empresa.id,
            "motivo": motivo_normalizado,
            "fechada_por_anterior": fechada_por_anterior,
            "fechada_em_anterior": (
                fechada_em_anterior.isoformat() if fechada_em_anterior else None
            ),
        },
    )
    return competencia


@transaction.atomic
def marcar_competencia_como_entregue(*, empresa, ano, mes, usuario, request=None):
    """Marca a competência (ano, mes) da empresa como entregue ao cliente.

    Critério 7: só é possível entregar uma competência `encerrada` — mês
    aberto é recusado (`CompetenciaOperacaoRecusada`, 409). Grava
    `entregue_em`/`entregue_por`.

    Repetível de propósito (ver o docstring de `Competencia`): a entrega
    "pode repetir-se" (balancete ao cliente, depois ECD transmitida, no
    texto do plano) — cada chamada bem-sucedida ATUALIZA os dois campos
    para o evento mais recente; nenhuma trava de "já entregue" existe aqui
    (a trava de RC-101 é sobre REABRIR uma competência entregue, não sobre
    entregar de novo). Devolve o atributo não persistido `entregue_agora`
    (sempre `True` quando a função retorna sem levantar exceção — mantido
    pelo mesmo motivo de simetria de `criado_agora`/`encerrada_agora`, ainda
    que aqui não haja um ramo "já estava assim" a distinguir).

    ⚠️ Correção dos achados BL-458/A3 e BL-459/A4 (rodada 2 de auditoria):
    `registrar()` mora AQUI, com `detalhes={"ano", "mes", "empresa_id"}` —
    mesma correção das outras duas funções desta fatia.

    BL-463: o lock é adquirido por `_travar_competencia_para_transicao`,
    que traduz o estouro de `lock_timeout` para
    `CompetenciaTravadaPorOutraOperacao` (409) em vez de propagar o
    `OperationalError` cru — mesma função usada por `encerrar_competencia`
    e `reabrir_competencia`.
    """
    competencia = obter_ou_criar_competencia(empresa=empresa, ano=ano, mes=mes)
    competencia = _travar_competencia_para_transicao(competencia, ano=ano, mes=mes, empresa=empresa)

    if competencia.estado != EstadoCompetencia.ENCERRADA:
        raise CompetenciaOperacaoRecusada(
            f"Só é possível marcar como entregue uma competência encerrada; a "
            f"competência {mes:02d}/{ano} de {empresa} está "
            f"'{competencia.get_estado_display()}'."
        )

    competencia.entregue_em = timezone.now()
    competencia.entregue_por = usuario
    competencia.save(update_fields=["entregue_em", "entregue_por"])
    competencia.entregue_agora = True
    registrar(
        acao="competencia.entregue",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=competencia,
        request=request,
        detalhes={"ano": ano, "mes": mes, "empresa_id": empresa.id},
    )
    return competencia


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
    `total_debito`, `total_credito` (do período), `saldo_final` e
    `ids_contas`.

    `ids_contas` (BL-212) é o conjunto EXATO de ids que esta apuração somou
    — a conta e todas as descendentes, o que `_descendentes_de` devolveu.
    Está no resultado porque quem acabou de apurar o Razão costuma precisar
    do MESMO recorte para outra consulta da mesma requisição (hoje, o aviso
    de movimento fora do período, BL-198), e `_descendentes_de` faz UMA
    CONSULTA POR NÍVEL de profundidade: recomputá-lo DOBRARIA o custo do
    Razão de um plano profundo. Devolver o conjunto é o que permite à
    segunda consulta ser barata — ver `movimento_fora_do_periodo`, que o
    aceita em `ids_contas`, e o teto de consultas declarado em função da
    profundidade em `test_dl015_saidas_com_periodo.py`.
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
        # BL-212: o recorte de contas desta apuração, para quem precisar do
        # MESMO conjunto na mesma requisição sem pagar de novo a consulta
        # por nível de `_descendentes_de`. `frozenset` de propósito: é um
        # fato já apurado, e ninguém que o receba deve poder alterar o
        # conjunto que declaradamente foi somado aqui.
        "ids_contas": frozenset(ids_contas),
    }


def apurar_balancete(*, empresa, inicio, fim, nivel=None):
    """Apura o Balancete de verificação da empresa no período [inicio, fim] (BL-61).

    Quatro colunas CONSOLIDADAS por conta (saldo_anterior, débitos, créditos,
    saldo_final) mais duas colunas PRÓPRIAS (débitos_proprios,
    creditos_proprios — achado novo 3 da rodada 3 / DE-024 §2, ver comentário
    junto do `append` abaixo) e duas colunas de CLASSIFICAÇÃO (`tipo`,
    `raiz` — DL-032 fatia 1, para `apurar_saldos` agregar por `TipoConta`
    reusando esta mesma função, sem reimplementar a hierarquia). `nivel` é
    opcional: ausente, devolve todas as
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
                # Natureza CADASTRADA da conta (`Conta.natureza`) — exposta
                # aqui só para permitir à VIEW converter `saldo_anterior`/
                # `saldo_final` (ainda assinados, abaixo) em valor absoluto
                # + natureza APURADA (RC-61 / BL-77, critério 5 do plano
                # DL-017): a apurada NÃO é a cadastrada quando o movimento
                # do período inverte o lado do saldo — ver
                # `views._saldo_absoluto_com_natureza`. Esta função
                # continua devolvendo o saldo ASSINADO (positivo = mesmo
                # lado da natureza cadastrada): a conversão para
                # apresentação é responsabilidade da view, não do serviço
                # (o valor "continua Decimal até o template" — DL-017,
                # seção de riscos).
                "natureza": conta.natureza,
                # `tipo` e `raiz` (DL-032, fatia 1): expostos SÓ para que
                # `apurar_saldos` agregue por `TipoConta` sem reabrir o
                # banco nem reimplementar a hierarquia — os dois vêm do
                # MESMO objeto `Conta` já carregado nesta função, sem
                # consulta extra. `raiz` é `conta_pai_id is None`: é o que
                # permite a `apurar_saldos` somar cada árvore EXATAMENTE
                # uma vez (a raiz já vem CONSOLIDADA — próprio + toda a
                # subárvore, regra única de saldo acima —, então somar
                # TODAS as linhas, não só as raízes, contaria o mesmo
                # lançamento mais de uma vez).
                "tipo": conta.tipo,
                "raiz": conta.conta_pai_id is None,
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


def apurar_saldos(*, empresa, data_base):
    """Camada de saldos (DL-032, fatia 1): saldo de CADA conta da empresa em
    `data_base`, mais os cinco totais por `TipoConta` e a equação contábil
    que fecha nos dois estados do exercício — RC-104 (confirmado pelo Fred em
    2026-09-20).

    ⚠️ **CONTRATO DE DERIVAÇÃO, não tabela.** Esta função é LEITURA PURA — não
    grava saldo, cache nem trilha (critério 6; provado por
    `test_apurar_saldos_nao_grava_nada` (e
    `test_competencia_encerrada_e_entregue_nao_muda_o_resultado_nem_grava`),
    capturando as consultas SQL da chamada e conferindo que todas são
    `SELECT`). Se um dia o desempenho exigir materializar, isso é decisão
    própria do `arquiteto-senior`, com verificador que reprove divergência —
    nunca cache silencioso (ver docstring do plano DL-032).

    **Reusa o motor do Balancete — não reimplementa a DE-020.** Chama
    `apurar_balancete(empresa=empresa, inicio=data_base, fim=data_base)` e lê
    `saldo_final` de cada linha. Isso é MATEMATICAMENTE equivalente ao saldo
    em `data_base` de QUALQUER outra chamada a `apurar_balancete` com o MESMO
    `fim` e um `inicio` diferente (inclusive um início de exercício real),
    contanto que `inicio <= fim`: `_saldo_por_natureza` é linear em
    (débito, crédito), e a partição de `apurar_balancete` entre
    "saldo_anterior" (data < inicio) e "período" (inicio <= data <= fim)
    cobre exatamente o mesmo universo (data <= fim) qualquer que seja o
    ponto de corte `inicio` — corta o total em dois pedaços diferentes, mas
    o produto da soma (com a natureza aplicada UMA vez, no fim, sobre a
    soma) é o mesmo. **É esta prova, não uma coincidência de teste, que
    garante o critério 1** (`apurar_saldos` e `apurar_balancete` nunca
    discordam): as duas funções literalmente fazem a mesma conta.

    **Saldo de abertura (escopo item 5):** `data_base` anterior a qualquer
    lançamento não é caso especial — `apurar_balancete` já devolve
    `saldo_final = 0` para toda conta sem movimento até `fim`, então esta
    função devolve zeros sem precisar de `if`.

    **Data futura e data absurda (critério 7):** qualquer `datetime.date` é
    aceito, sem checagem de faixa. Não é lacuna: `apurar_balancete` já
    aceita qualquer par de datas — é o mesmo mecanismo que a DL-020 usa para
    achar lançamento fora da faixa (BL-198), alargando o período até o ano
    9999 sem erro. `apurar_saldos` herda esse comportamento por reuso, de
    propósito: `data_base=date(9999, 12, 31)` sem lançamento nenhum devolve
    saldo zero em toda conta, não exceção. A validação de FORMATO (texto →
    `datetime.date`) é responsabilidade da fronteira que ainda não existe
    nesta fatia (view) — `apurar_saldos`, como `apurar_balancete` e
    `apurar_razao`, confia que quem chama já entregou um `datetime.date`.

    **A equação, e o momento da verdade (RC-104):**
    `ativo = passivo + patrimonio_liquido + (receita - despesa)`. O termo
    `(receita - despesa)` é o resultado AINDA NÃO transferido ao PL — durante
    o exercício ele é diferente de zero sem que haja erro nenhum; depois do
    zeramento (RC-104: mensal, trimestral ou anual, por lançamento, contra
    uma conta "Resultado do Exercício" e desta para "Lucros Acumulados" ou,
    no prejuízo, para a retificadora "(-) Prejuízos Acumulados") o termo
    zera por construção e a equação vira a forma clássica — as duas formas
    são o MESMO cálculo, nunca um `if` de "já encerrou". A diferença
    (`equacao["diferenca"]`) é CALCULADA e DEVOLVIDA, com valor e sinal;
    NENHUM saldo é alterado para fechá-la (critério 2) — "o que eu somei
    fecha, e quando não fecha eu digo, nunca conserto".

    **Os cinco totais por `TipoConta`, e por que são as RAÍZES, não todas as
    linhas (critério 4, DE-056):** `totais_por_tipo` nasce de
    `{tipo: 0 for tipo in TipoConta.values}` — lido do MODELO, nunca de uma
    tupla escrita à mão; um `TipoConta` novo aparece aqui com zero, em vez de
    ficar de fora em silêncio. A soma em si usa só as linhas com `raiz=True`
    (`conta_pai is None`): a raiz já vem CONSOLIDADA pela regra única de
    saldo (própria + TODA a subárvore, com a natureza da RAIZ aplicada uma
    única vez — DE-020), então somar as raízes cobre a árvore inteira
    exatamente uma vez. Sem hierarquia (conta sem pai nem filho), cada conta
    é sua própria raiz e a soma continua correta. **É por isto, e não por
    uma tabela de "natureza esperada por tipo", que uma retificadora
    SUBTRAI em vez de somar** (RC-104: "(-) Prejuízos Acumulados", natureza
    DEVEDORA dentro de um grupo Patrimônio Líquido CREDOR — o mesmo padrão
    já existente na base de medição de 73 contas, em "(-) Depreciação
    acumulada" e em "Deduções da receita bruta"): quem aplica o sinal final
    é a natureza da RAIZ do grupo (o motor do Balancete, DE-020), nunca a da
    retificadora isolada — somar `saldo_final` de CADA conta por `tipo`
    PRÓPRIO (em vez de só das raízes) contaria a retificadora com a
    natureza DELA, na direção errada, e SOMARIA onde deveria SUBTRAIR (a
    conta é a prova:
    `test_retificadora_dentro_do_patrimonio_liquido_subtrai_nunca_soma`).
    Depende de a retificadora estar aninhada sob um ancestral do MESMO
    grupo — é assim que o plano de contas de referência do Fred já está
    estruturado (RC-104), e é exatamente o caso que a DE-020 existe para
    resolver; um plano de contas em que a retificadora fosse uma raiz
    isolada (sem ancestral do grupo) não teria como ser corrigido por
    algoritmo nenhum sem reclassificar a conta — o que esta camada está
    proibida de fazer.

    **Conta sem tipo coerente com a natureza:** deliberado (o modelo
    permite retificadora). Esta função NUNCA reclassifica — soma o que está
    lá, com a natureza e o tipo que a conta tem.

    **Desempenho:** UMA chamada a `apurar_balancete` (já livre de N+1 —
    3 consultas, independente do número de contas) mais UM laço em Python
    sobre as linhas já carregadas — mesma classe de custo do Balancete.
    Medido em `test_desempenho_em_plano_de_contas_realista` num plano de
    contas realista (73 contas, 4 níveis, mesma base de
    `scripts/semear_base_de_medicao.py`); o número está no `print` daquele
    teste, não aqui, para não haver dois lugares para desatualizar.
    """
    balancete = apurar_balancete(empresa=empresa, inicio=data_base, fim=data_base)

    contas = [
        {
            "conta": linha["conta"],
            "nome": linha["nome"],
            "tipo": linha["tipo"],
            "natureza": linha["natureza"],
            "nivel": linha["nivel"],
            "saldo": linha["saldo_final"],
        }
        for linha in balancete["contas"]
    ]

    # DE-056 / critério 4: os totais nascem de TODOS os `TipoConta` do
    # MODELO — nunca de uma tupla de cinco strings escrita à mão (o
    # anti-padrão que este projeto já pagou caro). Um tipo novo no modelo
    # aparece aqui automaticamente, com zero, em vez de ficar fora em
    # silêncio.
    zero = Decimal("0")
    totais_por_tipo = {tipo: zero for tipo in TipoConta.values}
    for linha in balancete["contas"]:
        if linha["raiz"]:
            totais_por_tipo[linha["tipo"]] += linha["saldo_final"]

    ativo = totais_por_tipo[TipoConta.ATIVO]
    passivo = totais_por_tipo[TipoConta.PASSIVO]
    patrimonio_liquido = totais_por_tipo[TipoConta.PATRIMONIO_LIQUIDO]
    receita = totais_por_tipo[TipoConta.RECEITA]
    despesa = totais_por_tipo[TipoConta.DESPESA]
    resultado_do_periodo = receita - despesa

    # O momento da verdade: a diferença é CALCULADA e DEVOLVIDA — nunca usada
    # para ajustar saldo nenhum, aqui ou em quem chama (critério 2).
    diferenca = ativo - (passivo + patrimonio_liquido + resultado_do_periodo)

    return {
        "data_base": data_base,
        "contas": contas,
        "totais_por_tipo": totais_por_tipo,
        "equacao": {
            "ativo": ativo,
            "passivo": passivo,
            "patrimonio_liquido": patrimonio_liquido,
            "receita": receita,
            "despesa": despesa,
            "resultado_do_periodo": resultado_do_periodo,
            "diferenca": diferenca,
        },
    }


def movimento_fora_do_periodo(*, empresa, inicio, fim, conta=None, ids_contas=None):
    """Existe movimento da empresa FORA de [inicio, fim]? (BL-198, achado R6-4b.)

    É a razão de a DL-020 existir. O auditor mediu: um lançamento de
    5.000,00 datado `9999-12-31`, ao lado de um de 100,00 de hoje, **não
    aparece em nenhuma saída de uso normal** — Diário, Razão, Balancete e
    Conferência todos respondem "não" para ele — e o balancete do período
    CONCILIA, porque os totais do período estão certos. Nada avisa que
    existe mais. Validar a entrada (RC-77) fecha a porta para o futuro; esta
    consulta é o que ACENDE A LUZ sobre o que já está gravado.

    Devolve `None` quando não há nada fora do período (o caso normal, para a
    tela não precisar comparar dicionário vazio) e, quando há:

        {"anteriores":  {"quantidade": int, "data_extrema": date} | None,
         "posteriores": {"quantidade": int, "data_extrema": date} | None}

    `data_extrema` é a data MAIS DISTANTE de cada lado (a mais antiga antes
    do período, a mais recente depois) — é o que permite à saída dizer "há
    movimento até 31/12/9999" e oferecer um período que o alcance.
    `quantidade` conta LANÇAMENTOS, não partidas.

    Deliberadamente NÃO devolve valor somado: o aviso não é um saldo, e um
    total parcial ao lado do total do período convidaria a somar os dois —
    que é justamente a conciliação errada. Quem quer ver o movimento alarga
    o período e vê pelo Diário, com os lançamentos de origem.

    `conta` opcional: quando informada (e sem `ids_contas`), o recorte é o
    MESMO conjunto de contas que `apurar_razao` usa (a conta e todas as
    descendentes, `_descendentes_de`), para um aviso por conta falar da conta
    consultada e não da empresa inteira. Sem ela, o recorte é a empresa
    (Diário e Balancete). Neste caminho — e SÓ nele — a função levanta
    `HierarquiaInconsistente` no mesmo caso em que `apurar_razao` já levanta
    (ciclo alcançável a partir da conta); quem chamar por aqui precisa tratar
    isso na mesma requisição. Nenhuma superfície chama por aqui hoje: as duas
    do Razão passam `ids_contas` (BL-212), que não percorre hierarquia
    nenhuma e por isso não levanta.

    `ids_contas` é a versão BARATA do recorte por conta, para quem acabou de
    chamar `apurar_razao` e já tem o conjunto pronto (ele vem no resultado,
    na chave `ids_contas` — BL-212): evita percorrer a subárvore uma segunda
    vez. Isso não é micro-otimização — `_descendentes_de` faz UMA CONSULTA
    POR NÍVEL de profundidade, então recomputar DOBRARIA o custo do Razão de
    um plano profundo, e existe teste de teto de consulta declarado em função
    da profundidade justamente para isso
    (`test_dl015_saidas_com_periodo.py`). A frase acima já foi FALSA uma vez:
    `apurar_razao` não devolvia `ids_contas`, as duas superfícies do Razão
    chamaram o caminho caro e o teto de consultas reprovou (24 onde o teto
    era 17). Por isso as duas metades desta promessa têm teste próprio em
    `test_dl019_razao_reaproveita_ids_contas.py`: que a chave existe, e que
    nenhuma das duas superfícies percorre a subárvore duas vezes.
    Quando os dois vêm, `ids_contas` vence e `conta` é ignorada.

    Custo: **uma** consulta agregada de tamanho constante, com as quatro
    medidas (quantidade e data extrema de cada lado) em agregação
    condicional — não uma por lado. Mais as de `_descendentes_de` só quando
    há `conta` sem `ids_contas`. Nada disso cresce com a quantidade de
    lançamentos.
    """
    if conta is None and ids_contas is None:
        base = LancamentoContabil.objects.filter(empresa=empresa)
        campo_data = "data"
        alvo_da_contagem = "id"
    else:
        if ids_contas is None:
            ids_contas = _descendentes_de(conta, empresa)
        base = ItemLancamento.objects.filter(conta_id__in=ids_contas, lancamento__empresa=empresa)
        campo_data = "lancamento__data"
        # Contar `lancamento` (com `distinct`) é o que faz a contagem ser de
        # LANÇAMENTOS: um lançamento com débito e crédito na mesma subárvore
        # tem dois itens e contaria duas vezes se contássemos itens.
        alvo_da_contagem = "lancamento"

    antes_do_periodo = Q(**{f"{campo_data}__lt": inicio})
    depois_do_periodo = Q(**{f"{campo_data}__gt": fim})
    medidas = base.aggregate(
        quantidade_anteriores=Count(alvo_da_contagem, filter=antes_do_periodo, distinct=True),
        data_extrema_anteriores=Min(campo_data, filter=antes_do_periodo),
        quantidade_posteriores=Count(alvo_da_contagem, filter=depois_do_periodo, distinct=True),
        data_extrema_posteriores=Max(campo_data, filter=depois_do_periodo),
    )

    def _lado(sufixo):
        if not medidas[f"quantidade_{sufixo}"]:
            return None
        return {
            "quantidade": medidas[f"quantidade_{sufixo}"],
            "data_extrema": medidas[f"data_extrema_{sufixo}"],
        }

    lados = {"anteriores": _lado("anteriores"), "posteriores": _lado("posteriores")}
    if lados["anteriores"] is None and lados["posteriores"] is None:
        return None
    return lados


def localizar_lancamentos_com_data_fora_da_faixa(*, empresa):
    """Lançamentos já GRAVADOS com data fora da faixa do RC-77 (BL-198).

    A Conferência não tem período — uma base torta é torta em qualquer
    recorte —, então o aviso de "movimento fora do período" não se aplica a
    ela. O equivalente, e o que fecha o buraco do achado R6-4b para o dado
    que JÁ EXISTE, é este: listar o que está fora da faixa plausível
    (`DATA_MINIMA_LANCAMENTO` .. `data_maxima_lancamento()`).

    É a única saída em que o `9999-12-31` aparece sem o contador precisar
    suspeitar primeiro. A validação de entrada não conserta o passado, e a
    DL-020 declara o reparo de dado já gravado fora de escopo: a Conferência
    é onde esse passado fica visível, com o lançamento nomeado, para o
    contador decidir o que fazer (estorno, ajuste) pelos caminhos normais.

    O limite superior se MOVE com "hoje": um lançamento programado para
    hoje + 40 dias aparece aqui hoje e deixa de aparecer daqui a dez dias,
    quando entrar na faixa. É o comportamento pretendido — a faixa descreve
    plausibilidade na data da consulta, não um selo permanente.

    Devolve lista (não queryset): a Conferência sempre consome tudo, e a
    lista deixa explícito que não há paginação aqui — em base sadia ela é
    vazia.
    """
    return list(
        LancamentoContabil.objects.filter(empresa=empresa)
        .filter(Q(data__lt=DATA_MINIMA_LANCAMENTO) | Q(data__gt=data_maxima_lancamento()))
        .order_by("data", "id")
    )


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
