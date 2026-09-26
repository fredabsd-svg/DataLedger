import calendar
import hashlib
import json
import warnings
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count, DecimalField, F, Max, Min, Q, Sum
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.contabilidade.models import (
    GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL,
    NATUREZA_NATURAL_DO_TIPO,
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    ClassificacaoPatrimonial,
    Competencia,
    Conta,
    EstadoCompetencia,
    GrupoDaLei,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
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
from apps.core.restricoes import RestricaoViolada, mensagens_de_gatilho, restricao_como_400

# DL-038 (etapa 2): só o ENUM de tipo de inscrição — usado por
# `rotulo_e_inscricao_da_empresa`, abaixo, para decidir CNPJ ou CPF. Não
# cria dependência nova de verdade: `apps.contabilidade.models` já importa
# `Empresa` do mesmo `apps.empresas.models` no nível do módulo (ver o
# import de `Empresa` em `apps/contabilidade/models.py`), então este app já
# depende daquele — este import só nomeia o enum que faltava.
from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.services import EmpresaEmModoLivroCaixa, recusar_se_livro_caixa

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

# DE-078 item 6 (B4, rodada 1 de auditoria da DL-043): prefixo de
# `chave_idempotencia` RESERVADO para lançamentos gerados pelo próprio
# `zerar_resultado` — nenhum cliente (API, importação, tela) pode usar uma
# chave que comece assim (ver a recusa em `criar_lancamento`, abaixo).
# Precisa estar ANTES de `criar_lancamento` no arquivo (e não junto das
# outras funções de zeramento, mais abaixo) exatamente por isso: é o único
# ponto de escrita por onde toda chave de idempotência passa, e a recusa
# tem que valer ali. Antes desta correção, o achado B4 media que um
# ANALISTA (que não pode zerar, RC-102) conseguia forjar a marca de
# zeramento por esta mesma porta, bloqueando o GESTOR.
_PREFIXO_CHAVE_ZERAMENTO = "zeramento"


def _prefixo_chave_zeramento_da_empresa(empresa_id):
    return f"{_PREFIXO_CHAVE_ZERAMENTO}:{empresa_id}:"


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
    permitir_prefixo_reservado=False,
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

    `permitir_prefixo_reservado` (DE-078 item 6, B4): por padrão, uma
    `chave_idempotencia` que comece com `"zeramento:"` é recusada
    (`LancamentoInvalido`) — esse prefixo é reservado para os lançamentos
    que `zerar_resultado` gera. Só `zerar_resultado` passa `True` aqui;
    nenhuma view (API ou tela) expõe este parâmetro ao cliente.

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
    # Achado B4 da auditoria rodada 1 (DL-038, R5): defesa em profundidade
    # no SERVIÇO — a API (`EmpresaEscopadaContabilMixin`) e a tela (decorador
    # `_sem_contabilidade_para_livro_caixa`) já recusam ANTES de chegar
    # aqui, mas este é o ponto por onde QUALQUER caminho de escrita passa
    # (inclusive um chamador futuro que não use nenhuma das duas portas).
    # A REGRA mora só em `apps.empresas.services.recusar_se_livro_caixa`;
    # aqui só se traduz para `LancamentoInvalido`, o vocabulário de exceção
    # que este serviço já usa (para não obrigar todo chamador a conhecer
    # um segundo tipo de exceção só para este caso).
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        raise LancamentoInvalido(exc.mensagem) from exc

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

    # DE-078 item 6 (B4, rodada 1 de auditoria da DL-043): o prefixo
    # "zeramento:" é RESERVADO para os lançamentos que o próprio
    # `zerar_resultado` gera — nenhum cliente (API, tela, importação) pode
    # usar uma chave que comece assim. Medido pela auditoria: sem esta
    # recusa, um ANALISTA (que não pode zerar — RC-102) conseguia, por
    # `POST .../lancamentos/` com um `Idempotency-Key` forjado, (a)
    # bloquear o zeramento de uma competência (o GESTOR recebia
    # `ChaveIdempotenciaConflitante`, um 500 antes desta rodada) e (b)
    # bloquear o registro de uma vigência nova (a checagem de "zeramento
    # já gravado" em `registrar_parametro_contabil` via o mesmo prefixo).
    # `criar_lancamento` é o ÚNICO ponto por onde toda chave de
    # idempotência passa (AGENTS.md §8) — recusar aqui fecha as duas
    # portas (a tela e a API) de uma vez, sem duplicar a regra.
    #
    # `permitir_prefixo_reservado=True` é a ÚNICA excepão, e só
    # `zerar_resultado` a usa — é o próprio SISTEMA construindo a chave,
    # nunca um valor vindo do cliente. Este parâmetro não é exposto pela
    # API nem pela tela (nenhuma das duas o repassa), então não há caminho
    # de cliente para contornar a recusa chamando `criar_lancamento` com
    # ele — a defesa continua sendo "todo caminho de CLIENTE passa pela
    # recusa", não "toda chamada a esta função".
    if (
        chave_idempotencia
        and not permitir_prefixo_reservado
        and chave_idempotencia.startswith(f"{_PREFIXO_CHAVE_ZERAMENTO}:")
    ):
        raise LancamentoInvalido(
            f"A chave de idempotência não pode começar com '{_PREFIXO_CHAVE_ZERAMENTO}:' "
            "— esse prefixo é reservado para os lançamentos gerados pelo próprio "
            "zeramento do resultado."
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
# Parâmetro contábil por empresa e zeramento do resultado (DL-043, BL-474)
#
# NÍVEL 1 de risco (AGENTS.md §3.1: lançamento, saldo, competência). Duas
# fatias do plano DL-043:
#
# Fatia 1 — `registrar_parametro_contabil`/`encerrar_vigencia_de_
# parametro_contabil`: parâmetro contábil por empresa COM VIGÊNCIA, no
# molde de `apps.empresas.models.HistoricoRegimeTributario` (DE-039).
#
# Fatia 2 — `zerar_resultado`: zeramento do resultado do período (RC-104,
# RC-105), em DUAS etapas, idempotente, com trava de concorrência via
# `_travar_competencia_para_transicao` (já usada por `encerrar_
# competencia`/`reabrir_competencia`/`marcar_competencia_como_entregue`).
#
# Fatia 3 (tela) e a destinação do lucro (dividendos, reservas) ficam FORA
# do escopo desta seção — ver o plano.
# ---------------------------------------------------------------------------


class ParametroContabilInvalido(Exception):
    """Dados do parâmetro contábil (periodicidade, contas de destino) ou do
    pedido de zeramento (ano/mês, periodicidade incompatível, empresa sem
    parâmetro vigente) violam uma regra de negócio — 400: o cliente pode
    corrigir o que enviou. Nomeada à parte de `LancamentoInvalido` porque o
    domínio de origem (parâmetro/período de zeramento, não o corpo de um
    lançamento) é diferente — mesmo padrão de `CompetenciaOperacaoInvalida`
    ao lado de `LancamentoInvalido`.
    """


class VigenciaParametroContabilConflitante(Exception):
    """A vigência (ou o zeramento) pedido colide com o ESTADO já gravado:

    - outra vigência aberta criada por uma requisição concorrente
      (`UniqueConstraint`, camada 1) ou sobreposição com uma vigência já
      existente (gatilho da migração 0009, camada 2) — corrida residual em
      `registrar_parametro_contabil`;
    - uma vigência retroativa que tentaria cobrir um período que já tem
      zeramento gravado — decisão de modelagem da DL-043 (a alternativa
      mais segura das descritas no plano): aceitar tornaria ambíguo, para
      um período já zerado e já entregue, qual conjunto de contas "valia"
      naquele período, sem reescrever o lançamento (imutável) nem o Razão
      já entregue.

    409 nos dois casos: o pedido é bem formado, o que impede é o que já
    está gravado — mesma distinção que `CompetenciaOperacaoRecusada` já
    aplica para competência.
    """


class ZeramentoForaDeOrdem(CompetenciaEncerrada):
    """DE-078 item 2 (B2, BLOQUEADOR na rodada 1 de auditoria da DL-043):
    já existe zeramento da MESMA empresa com data POSTERIOR à data final
    do período pedido — zerar (ou complementar) este período agora
    contaria parte do resultado DUAS VEZES: uma no zeramento posterior já
    gravado (que leu o saldo acumulado incluindo o resíduo deste
    período), outra agora. A correção de período anterior segue o
    RC-101/RC-103 (estornar o(s) zeramento(s) posteriores antes), nunca
    "zerar por cima" fora de ordem.

    Subclasse de `CompetenciaEncerrada` de propósito, não uma hierarquia
    nova: as duas são "a competência/período não pode receber este
    lançamento agora", com a MESMA tradução HTTP (409) — reaproveitar a
    tradução já existente na view evita um `except` a mais só para este
    caso.
    """


class EmpresaTravadaPorOutraOperacao(CompetenciaOperacaoRecusada):
    """DE-078 item 3 (B2(b)/B10): a espera pelo `SELECT ... FOR UPDATE` da
    linha de `Empresa` (`_travar_empresa_para_operacao_de_zeramento`,
    abaixo) estourou o `lock_timeout` do banco — outra operação de
    zeramento, registro ou encerramento de vigência da MESMA empresa está
    em andamento. Subclasse de `CompetenciaOperacaoRecusada`: mesma
    tradução HTTP (409) que `CompetenciaTravadaPorOutraOperacao` já usa
    para o lock de competência, reaproveitada aqui para o lock de
    empresa.
    """


def _chave_idempotencia_zeramento(*, empresa_id, ano, mes, etapa, complemento, parte=None):
    """Chave determinística por (empresa, período, etapa, complemento) —
    critério de idempotência do plano DL-043.

    `etapa` é 1 (zera receita/despesa contra "resultado do exercício") ou 2
    (transfere o saldo do "resultado do exercício" para lucros/prejuízos
    acumulados). `complemento` é o maior número de complemento JÁ GRAVADO
    para esta MESMA combinação (empresa, período, etapa) antes desta
    chamada, mais um (ver `_proximo_complemento`) — 0 na primeira vez, 1
    na primeira correção por movimento novo no período (competência ainda
    aberta), e assim por diante. Cada complemento tem CONTEÚDO diferente
    do anterior (o valor é sempre a DIFERENÇA ainda não zerada, nunca o
    total acumulado de novo) — reaproveitar a mesma chave para conteúdo
    diferente é exatamente o que `ChaveIdempotenciaConflitante` existe
    para recusar, por isso cada complemento precisa de chave própria.

    `parte` (DE-078 item 5, B3): quando a etapa 1 precisa ser DIVIDIDA em
    vários lançamentos por causa do teto de partidas (RC-79,
    `LIMITE_PARTIDAS_POR_LANCAMENTO`), cada lançamento da MESMA etapa/
    complemento leva um sufixo `:parteN` — as partes de um mesmo
    complemento são gravadas atomicamente ou não (a chamadora as cria uma
    a uma, mas todas dentro da MESMA transação de `zerar_resultado`).
    `None` (o caso comum — plano de contas dentro do teto) NÃO acrescenta
    sufixo nenhum: a chave fica idêntica à de antes desta correção, o que
    preserva a compatibilidade da chave para quem já a lia.
    """
    chave = (
        f"{_prefixo_chave_zeramento_da_empresa(empresa_id)}{ano:04d}-{mes:02d}:"
        f"etapa{etapa}:{complemento}"
    )
    if parte is not None:
        chave += f":parte{parte}"
    return chave


def _proximo_complemento(*, empresa, ano, mes, etapa):
    """O próximo número de `complemento` a usar em
    `_chave_idempotencia_zeramento` para (empresa, ano, mes, etapa): o
    MAIOR número de complemento já gravado, mais um (0 se nenhum).

    ⚠️ **Não é mais uma CONTAGEM de lançamentos (correção da DE-078 item
    5, B3):** com a etapa 1 podendo ser dividida em várias "partes" do
    MESMO complemento (`_chave_idempotencia_zeramento`), contar
    lançamentos contaria cada parte como um complemento novo — o próximo
    pedido saltaria vários números em vez de avançar um. Em vez disso,
    lê-se o NÚMERO do complemento (o primeiro segmento depois do prefixo
    de etapa, antes de um eventual `:parteN`) de cada chave já gravada, e
    devolve o maior mais um.
    """
    prefixo = f"{_prefixo_chave_zeramento_da_empresa(empresa.pk)}{ano:04d}-{mes:02d}:etapa{etapa}:"
    chaves = LancamentoContabil.objects.filter(
        empresa=empresa, chave_idempotencia__startswith=prefixo
    ).values_list("chave_idempotencia", flat=True)
    maior = -1
    for chave in chaves:
        resto = chave[len(prefixo) :]
        numero_str = resto.split(":", 1)[0]
        try:
            numero = int(numero_str)
        except ValueError:
            # Chave gravada fora do formato esperado (não deveria
            # acontecer pelo caminho normal — `criar_lancamento` recusa
            # qualquer chave de CLIENTE com este prefixo) — ignora em vez
            # de estourar, mesma defesa em profundidade de "declarar,
            # nunca inventar" já usada em `apurar_saldos`.
            continue
        maior = max(maior, numero)
    return maior + 1


def _travar_empresa_para_operacao_de_zeramento(empresa):
    """`SELECT ... FOR UPDATE` na linha de `Empresa` — DE-078 item 3
    (B2(b), BLOQUEADOR, e B10): serializa TODAS as operações de zeramento,
    registro e encerramento de vigência de parâmetro contábil da MESMA
    empresa, mesmo entre PERÍODOS diferentes.

    ⚠️ **Por que não basta a trava de competência que `zerar_resultado` já
    tinha:** `_travar_competencia_para_transicao` trava a linha de
    `Competencia` de UM período — dois pedidos do MESMO mês serializam
    corretamente por ela, mas dois pedidos de MESES DIFERENTES (março e
    abril, por exemplo) travam linhas DIFERENTES e correm em paralelo. A
    auditoria mediu 15 de 15 rodadas com o resultado contado em dobro
    nesse cenário, porque os dois cálculos leem o saldo ACUMULADO
    (`_calcular_zeramento`) ao mesmo tempo, sem nenhum dos dois ver o
    zeramento que o outro está gravando. A trava por EMPRESA (este lock)
    é o que impede os dois cálculos de rodarem ao mesmo tempo, porque os
    dois travam a MESMA linha (a da empresa), não linhas diferentes.
    Chamada ANTES de `_recusar_zeramento_fora_de_ordem` e de qualquer
    cálculo de saldo, nas três funções que tocam parâmetro contábil ou
    zeramento (`registrar_parametro_contabil`, `encerrar_vigencia_de_
    parametro_contabil`, `zerar_resultado`) — SEMPRE nesta ordem (empresa
    primeiro, competência depois, quando as duas se aplicam), para nunca
    correr risco de dependência circular de lock entre chamadas
    concorrentes.

    Mesma tradução de `lock_timeout` (BL-463) que `_travar_competencia_
    para_transicao` já usa, para `EmpresaTravadaPorOutraOperacao` (409) em
    vez de um `OperationalError` cru.
    """
    try:
        return Empresa.objects.select_for_update().get(pk=empresa.pk)
    except OperationalError as exc:
        if not _e_estouro_de_lock_timeout(exc):
            raise
        raise EmpresaTravadaPorOutraOperacao(
            f"A empresa {empresa} está com outra operação de parâmetro contábil ou "
            "zeramento em andamento; não foi possível travá-la a tempo. Tente "
            "novamente em instantes."
        ) from exc


def _recusar_zeramento_fora_de_ordem(*, empresa, data_final):
    """DE-078 item 2 (B2): recusa (`ZeramentoForaDeOrdem`, 409) se já
    existir zeramento da MESMA empresa com data POSTERIOR a `data_final`
    — ver o docstring de `ZeramentoForaDeOrdem` para o dano que isso
    evita.

    Chamada em DOIS pontos, de propósito: pela PRÉVIA (`pre_visualizar_
    zeramento`), como leitura best-effort sem trava — só para avisar o
    contador antes de tentar gravar —, e por `zerar_resultado`, depois de
    `_travar_empresa_para_operacao_de_zeramento`, como a checagem
    AUTORITATIVA que de fato impede a gravação. A da prévia pode ficar
    desatualizada (outra requisição pode gravar um zeramento posterior
    entre a prévia e o POST); a da execução, sob a trava de empresa,
    nunca.
    """
    ja_zerado_depois = LancamentoContabil.objects.filter(
        empresa=empresa,
        chave_idempotencia__startswith=_prefixo_chave_zeramento_da_empresa(empresa.pk),
        data__gt=data_final,
    ).exists()
    if ja_zerado_depois:
        data_str = data_final.strftime("%d/%m/%Y")
        raise ZeramentoForaDeOrdem(
            f"Já existe zeramento gravado para esta empresa com data posterior a "
            f"{data_str}; zerar (ou complementar) este período agora contaria parte "
            "do resultado duas vezes. Para corrigir um período anterior, estorne "
            "o(s) zeramento(s) posteriores antes (RC-101/RC-103)."
        )


@transaction.atomic
def registrar_parametro_contabil(
    *,
    empresa,
    periodicidade_zeramento,
    conta_resultado_do_exercicio,
    conta_lucros_acumulados,
    conta_prejuizos_acumulados,
    vigencia_inicio,
    usuario=None,
    request=None,
):
    """Registra um novo período de parâmetro contábil para a empresa
    (DL-043 fatia 1, BL-474) — no MOLDE de `apps.empresas.services.
    registrar_regime_tributario` (DE-039): fecha automaticamente a
    vigência aberta anterior (se houver), definindo seu fim como o dia
    anterior ao novo início, e cria a vigência nova, aberta.

    Validações, nesta ordem — todas ANTES de qualquer gravação:

    1. Empresa em modo livro-caixa (DL-038): recusada — parâmetro contábil
       de partidas dobradas não se aplica a quem não escritura por
       partidas dobradas.
    2. `periodicidade_zeramento` é um dos três valores de
       `PeriodicidadeZeramento`.
    3. As TRÊS contas de destino: pertencem à MESMA empresa, são
       ANALÍTICAS (`aceita_lancamento=True`) E FOLHAS (sem conta filha —
       DE-078 item 1/B1: o mesmo risco do B1 se aplicaria a uma conta de
       destino com descendentes), ATIVAS, são do grupo PATRIMÔNIO LÍQUIDO
       (RC-104), e são três contas DIFERENTES entre si.
    4. A conta de prejuízos acumulados tem natureza DEVEDORA — é
       RETIFICADORA dentro do Patrimônio Líquido (RC-61: grupo credor,
       retificadora de natureza contrária). Sem esta checagem, o
       zeramento por prejuízo creditaria uma conta devedora e o PL
       cresceria com prejuízo em vez de encolher. A conta de LUCROS
       acumulados, ao contrário, tem de ter natureza CREDORA (DE-078 item
       1/B7): sem esta checagem, um lucro creditaria uma conta devedora,
       que ficaria com saldo anormal no Balanço.
    5. Ordem de vigência: a nova só pode começar DEPOIS do início da
       vigência aberta atual (se houver) — mesma regra de
       `registrar_regime_tributario`.
    6. ⚠️ Decisão de modelagem da DL-043 (não confirmada pelo Fred; o plano
       pedia a alternativa MAIS SEGURA entre as descritas, e esta é a
       aplicada — ver `VigenciaParametroContabilConflitante`): uma
       vigência cujo início seja igual ou anterior à data de um zeramento
       JÁ GRAVADO para esta empresa é RECUSADA.

    Concorrência: `_travar_empresa_para_operacao_de_zeramento` (DE-078
    item 3/B10) trava a linha da EMPRESA antes de ler a vigência aberta e
    o "já zerado" do item 6 — sem essa trava, um `zerar_resultado`
    concorrente podia commitar um zeramento ENTRE a checagem do item 6 e
    o commit deste registro, e a ambiguidade que o item 6 existe para
    evitar aconteceria mesmo assim (B10). Depois dela,
    `select_for_update()` sobre a vigência aberta (mesmo padrão de
    `registrar_regime_tributario`); a corrida residual (duas requisições
    concorrentes quando NENHUMA vigência existe ainda) é coberta pelas
    DUAS camadas de restrição de banco (`Meta.constraints` e o gatilho da
    migração 0009), traduzidas para `VigenciaParametroContabilConflitante`
    (409) — nunca um 500 cru.
    """
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        raise ParametroContabilInvalido(exc.mensagem) from exc

    if periodicidade_zeramento not in PeriodicidadeZeramento.values:
        raise ParametroContabilInvalido(
            f"Periodicidade de zeramento inválida: {periodicidade_zeramento!r}. "
            f"Valores aceitos: {', '.join(PeriodicidadeZeramento.values)}."
        )

    contas_por_rotulo = {
        "conta de resultado do exercício": conta_resultado_do_exercicio,
        "conta de lucros acumulados": conta_lucros_acumulados,
        "conta de (-) prejuízos acumulados": conta_prejuizos_acumulados,
    }
    ids_vistos = set()
    for rotulo, conta in contas_por_rotulo.items():
        if conta.empresa_id != empresa.id:
            raise ParametroContabilInvalido(
                f"A {rotulo} deve pertencer à mesma empresa do parâmetro contábil."
            )
        if not conta.aceita_lancamento:
            raise ParametroContabilInvalido(
                f"A {rotulo} deve ser uma conta analítica (que aceita lançamento direto)."
            )
        if not _e_folha(conta):
            # DE-078 item 1 (B1): conta de destino com filhas correria o
            # mesmo risco que uma conta de resultado com filhas — saldo
            # PRÓPRIO e saldo CONSOLIDADO divergindo em silêncio.
            raise ParametroContabilInvalido(
                f"A {rotulo} não pode ter conta filha — as três contas de destino do "
                "zeramento precisam ser folhas (sem subconta)."
            )
        if not conta.ativo:
            raise ParametroContabilInvalido(f"A {rotulo} precisa estar ativa.")
        if conta.tipo != TipoConta.PATRIMONIO_LIQUIDO:
            raise ParametroContabilInvalido(
                f"A {rotulo} deve ser do grupo Patrimônio Líquido "
                f"(recebida: {conta.get_tipo_display()})."
            )
        if conta.pk in ids_vistos:
            raise ParametroContabilInvalido(
                "As três contas de destino do zeramento devem ser contas diferentes "
                f"entre si — a {rotulo} repete uma conta já usada por outro destino."
            )
        ids_vistos.add(conta.pk)

    # RC-61 — ver item 4 do docstring acima.
    if conta_prejuizos_acumulados.natureza != NaturezaConta.DEVEDORA:
        raise ParametroContabilInvalido(
            "A conta de (-) prejuízos acumulados precisa ter natureza devedora: "
            "é retificadora dentro do Patrimônio Líquido (RC-61)."
        )
    # DE-078 item 1 (B7) — ver item 4 do docstring acima.
    if conta_lucros_acumulados.natureza != NaturezaConta.CREDORA:
        raise ParametroContabilInvalido(
            "A conta de lucros acumulados precisa ter natureza credora."
        )

    # DE-078 item 3 (B10) — ver a nota de concorrência do docstring.
    _travar_empresa_para_operacao_de_zeramento(empresa)

    aberto = (
        ParametroContabilEmpresa.objects.select_for_update()
        .filter(empresa=empresa, vigencia_fim__isnull=True)
        .first()
    )
    if aberto is not None and vigencia_inicio <= aberto.vigencia_inicio:
        raise ParametroContabilInvalido(
            "A nova vigência deve começar depois do início da vigência atual "
            f"({aberto.vigencia_inicio.strftime('%d/%m/%Y')})."
        )

    # Item 6 do docstring: vigência retroativa cobrindo zeramento já
    # gravado — localizado pelo PREFIXO determinístico da chave de
    # idempotência (nunca por histórico em texto livre, que o contador
    # pode editar... não pode, lançamento é imutável, mas o texto não é
    # estrutura confiável para uma busca de negócio).
    ja_zerado = LancamentoContabil.objects.filter(
        empresa=empresa,
        chave_idempotencia__startswith=_prefixo_chave_zeramento_da_empresa(empresa.pk),
        data__gte=vigencia_inicio,
    ).exists()
    if ja_zerado:
        raise VigenciaParametroContabilConflitante(
            "Já existe zeramento gravado em data igual ou posterior a "
            f"{vigencia_inicio.strftime('%d/%m/%Y')} para esta empresa; uma vigência "
            "que começasse aí deixaria ambíguo qual conjunto de contas valia naquele "
            "período. Registre a vigência nova com início posterior a todo zeramento "
            "já gravado para esta empresa."
        )

    if aberto is not None:
        aberto.vigencia_fim = vigencia_inicio - timedelta(days=1)
        aberto.save(update_fields=["vigencia_fim"])

    try:
        with (
            transaction.atomic(),
            restricao_como_400(mensagens_de_gatilho("parametro_contabil_sem_sobreposicao")),
        ):
            parametro = ParametroContabilEmpresa.objects.create(
                empresa=empresa,
                periodicidade_zeramento=periodicidade_zeramento,
                conta_resultado_do_exercicio=conta_resultado_do_exercicio,
                conta_lucros_acumulados=conta_lucros_acumulados,
                conta_prejuizos_acumulados=conta_prejuizos_acumulados,
                vigencia_inicio=vigencia_inicio,
            )
    except RestricaoViolada as exc:
        raise VigenciaParametroContabilConflitante(str(exc)) from exc
    except IntegrityError as exc:
        # Corrida residual sobre a `UniqueConstraint` (camada 1) — ver o
        # docstring. Mesma técnica de extração de nome de constraint que
        # `apps.empresas.services._e_violacao_de_periodo_unico` já usa.
        nome_constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if nome_constraint != "um_periodo_de_parametro_contabil_aberto_por_empresa":
            raise
        raise VigenciaParametroContabilConflitante(
            "Esta empresa já tem uma vigência de parâmetro contábil aberta, criada "
            "por outra requisição ao mesmo tempo. Recarregue e confira antes de "
            "tentar de novo."
        ) from exc

    registrar(
        acao="parametro_contabil.vigencia_registrada",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=parametro,
        request=request,
        detalhes={
            "empresa_id": empresa.id,
            "periodicidade_zeramento": periodicidade_zeramento,
            "vigencia_inicio": vigencia_inicio.isoformat(),
        },
    )
    return parametro


@transaction.atomic
def encerrar_vigencia_de_parametro_contabil(*, empresa, usuario, request=None):
    """Encerra HOJE a vigência de parâmetro contábil aberta da empresa, sem
    abrir uma nova (DL-043 fatia 1) — o caminho para a empresa deixar de
    ter zeramento parametrizado (ex.: migrou para livro-caixa, ou o
    escritório decidiu suspender o zeramento automático).

    Recusa (`VigenciaParametroContabilConflitante`, 409 — conflito de
    ESTADO, o pedido não tem corpo para "corrigir") se não houver vigência
    aberta — não há o que encerrar — ou se a vigência aberta só começar no
    futuro (encerrar antes do próprio início produziria um intervalo
    invertido, sem sentido no histórico). `select_for_update()` pelo mesmo
    motivo de concorrência das demais transições deste módulo.

    DE-078 item 3 (B10): trava a EMPRESA (`_travar_empresa_para_operacao_
    de_zeramento`) antes de ler a vigência aberta — mesmo motivo de
    `registrar_parametro_contabil`.
    """
    _travar_empresa_para_operacao_de_zeramento(empresa)
    aberto = (
        ParametroContabilEmpresa.objects.select_for_update()
        .filter(empresa=empresa, vigencia_fim__isnull=True)
        .first()
    )
    if aberto is None:
        raise VigenciaParametroContabilConflitante(
            "Esta empresa não tem vigência de parâmetro contábil aberta para encerrar."
        )

    hoje = timezone.localdate()
    if hoje < aberto.vigencia_inicio:
        raise VigenciaParametroContabilConflitante(
            "Não é possível encerrar hoje uma vigência que só começa em "
            f"{aberto.vigencia_inicio.strftime('%d/%m/%Y')}."
        )

    aberto.vigencia_fim = hoje
    aberto.save(update_fields=["vigencia_fim"])
    registrar(
        acao="parametro_contabil.vigencia_encerrada",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=aberto,
        request=request,
        detalhes={"empresa_id": empresa.id, "vigencia_fim": hoje.isoformat()},
    )
    return aberto


def _parametro_contabil_vigente_em(*, empresa, data):
    """A vigência de `ParametroContabilEmpresa` aplicável a `data` — a que
    tem `vigencia_inicio <= data` e (`vigencia_fim` nulo OU `>= data`).

    Nunca a vigência "atual" no momento da chamada: `zerar_resultado`
    processa a DATA FINAL de um período, que pode ser reprocessada
    (complemento) depois de a vigência ter mudado — a leitura tem que
    continuar usando o parâmetro que valia NAQUELE período, mesmo
    raciocínio de `HistoricoRegimeTributario` para apuração fiscal
    histórica (DE-039).
    """
    return (
        ParametroContabilEmpresa.objects.filter(empresa=empresa, vigencia_inicio__lte=data)
        .filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=data))
        .order_by("-vigencia_inicio")
        .first()
    )


# Meses de encerramento por periodicidade (RC-104/RC-105, confirmado pelo
# Fred: trimestre e ano CIVIS): mensal fecha todo mês; trimestral, só em
# março/junho/setembro/dezembro; anual, só em dezembro. Tabela, não
# if/elif, pelo mesmo motivo de `_ARREDONDAMENTO` em `apps.core.dinheiro`
# — acrescentar uma periodicidade não deveria exigir tocar na lógica de
# validação, só declarar aqui a correspondência.
_MESES_DE_ENCERRAMENTO_POR_PERIODICIDADE = {
    PeriodicidadeZeramento.MENSAL: frozenset(range(1, 13)),
    PeriodicidadeZeramento.TRIMESTRAL: frozenset({3, 6, 9, 12}),
    PeriodicidadeZeramento.ANUAL: frozenset({12}),
}


def _validar_periodo_de_zeramento(*, periodicidade, mes):
    """Recusa (`ParametroContabilInvalido`) se `mes` não for um mês de
    encerramento da `periodicidade` vigente — critério 7 do plano DL-043.
    """
    meses_validos = _MESES_DE_ENCERRAMENTO_POR_PERIODICIDADE[periodicidade]
    if mes not in meses_validos:
        rotulo = PeriodicidadeZeramento(periodicidade).label.lower()
        nomes_meses = ", ".join(f"{m:02d}" for m in sorted(meses_validos))
        raise ParametroContabilInvalido(
            f"A periodicidade vigente desta empresa é '{rotulo}': o zeramento só "
            f"pode ser pedido para os meses de encerramento do período ({nomes_meses}); "
            f"recebido: {mes:02d}."
        )


def _e_folha(conta):
    """`True` se `conta` NÃO tem nenhuma conta filha (DE-022: "analítica" é
    decidido pela ÁRVORE — sem descendentes —, nunca por `aceita_
    lancamento`). Usada por `registrar_parametro_contabil` (DE-078 item
    1/B1) para exigir que as três contas de destino do zeramento sejam
    folhas: uma conta de destino com filhas correria o mesmo risco que uma
    conta de resultado com filhas (B1) — saldo PRÓPRIO e CONSOLIDADO
    divergindo em silêncio, só que agora do lado de onde o dinheiro
    chega, não de onde sai.
    """
    return not Conta.objects.filter(conta_pai=conta).exists()


def _contas_de_resultado(empresa):
    """TODAS as contas de RECEITA ou DESPESA da empresa — analíticas E
    sintéticas (DE-078 item 1/B1, correção do BLOQUEADOR da rodada 1 de
    auditoria da DL-043).

    ⚠️ **Por que TODAS, e não só `aceita_lancamento=True`:** o universo do
    zeramento é decidido pelo SALDO PRÓPRIO de cada conta
    (`_saldo_proprio_assinado`), nunca por `aceita_lancamento` — uma conta
    "4" que aceita lançamento E tem filha "4.1" (o estado PADRÃO do
    cadastro, `aceita_lancamento` nasce `True`) precisa ter seu saldo
    PRÓPRIO zerado independentemente da filha, e uma conta SINTÉTICA
    (`aceita_lancamento=False`) com saldo próprio — estado LEGADO,
    alcançável só por `.update()`/importação direta, nunca pelo caminho
    normal de escrituração, que já recusa lançamento em conta que não
    aceita — precisa aparecer aqui para ser RECUSADA por
    `_calcular_zeramento`, nunca para ser ignorada em silêncio (o valor
    sumiria da apuração, sem nenhum aviso).
    """
    return list(
        Conta.objects.filter(
            empresa=empresa, tipo__in=(TipoConta.RECEITA, TipoConta.DESPESA)
        ).order_by("codigo")
    )


def _saldo_proprio_assinado(linha):
    """Saldo PRÓPRIO — nunca o CONSOLIDADO com descendentes — de uma linha
    do balancete (`apurar_balancete`), assinado pela natureza CADASTRADA
    da conta.

    ⚠️ **Correção do achado B1 (BLOQUEADOR, rodada 1 de auditoria da
    DL-043): `saldo_final` é CONSOLIDADO por construção (DE-020: movimento
    próprio MAIS o de toda a subárvore, com a natureza da conta
    apresentada aplicada uma única vez) — é exatamente essa consolidação
    que dobrava o resultado quando uma conta de resultado tinha filhas (o
    estado PADRÃO do cadastro, já que `aceita_lancamento` nasce `True`):
    a conta "4" com filha "4.1" recebia, na etapa 1, um item pelo saldo
    CONSOLIDADO (próprio + "4.1"), e a "4.1" recebia OUTRO pelo mesmo
    movimento — contado duas vezes.** `debitos_proprios_totais`/
    `creditos_proprios_totais` (DL-034/BL-496) já vêm ACUMULADOS até
    `fim` (mesma razão de `saldo_final` — ver o docstring de
    `apurar_balancete`) e SEM a soma das descendentes: é a dupla condição
    que este cálculo precisa, e o balancete já a calcula, sem consulta
    nova.
    """
    return _saldo_por_natureza(
        linha["debitos_proprios_totais"], linha["creditos_proprios_totais"], linha["natureza"]
    )


def _item_de_zeramento(conta, saldo_assinado):
    """O item de lançamento (tipo + valor) que zera `saldo_assinado` de
    `conta` — `None` se já está em zero (nada a fazer, e é isto que torna
    o cálculo idempotente: chamar de novo sem movimento novo não gera
    item nenhum).

    `saldo_assinado` é positivo quando o saldo está do MESMO lado da
    natureza CADASTRADA da conta (convenção de `apurar_balancete`/
    `apurar_saldos`). Para zerar: se a conta é DEVEDORA e o saldo é
    positivo (saldo devedor), credita-se o valor; se é CREDORA e positivo
    (saldo credor), debita-se; e o inverso quando o saldo está do lado
    CONTRÁRIO ao cadastrado (saldo negativo nesta convenção) — é assim que
    uma conta retificadora de receita (RC-61: cadastrada DEVEDORA dentro
    de um grupo de Receita CREDOR) é zerada pelo lado certo sem nenhum
    `if` especial para "isto é retificadora": a fórmula só olha a
    natureza CADASTRADA da própria conta e o sinal do saldo, nunca o tipo
    do grupo em que ela está.
    """
    if saldo_assinado == 0:
        return None
    do_lado_cadastrado = saldo_assinado > 0
    if conta.natureza == NaturezaConta.DEVEDORA:
        tipo = TipoPartida.CREDITO if do_lado_cadastrado else TipoPartida.DEBITO
    else:
        tipo = TipoPartida.DEBITO if do_lado_cadastrado else TipoPartida.CREDITO
    return {"conta": conta, "tipo": tipo, "valor": abs(saldo_assinado)}


def _efeito_no_saldo_assinado(conta, tipo, valor):
    """Quanto `valor`, lançado como `tipo` (débito/crédito) em `conta`,
    somaria ao saldo assinado (convenção de `_saldo_proprio_assinado`) dela
    — usado só para SIMULAR, sem gravar nada, o efeito do item de zeramento
    da etapa 1 sobre a conta "resultado do exercício" antes de decidir a
    etapa 2 (a prévia — GET — precisa desse número sem gravar; a execução
    — POST — usa a MESMA função, para as duas nunca discordarem).
    """
    mesmo_lado = (conta.natureza == NaturezaConta.DEVEDORA and tipo == TipoPartida.DEBITO) or (
        conta.natureza == NaturezaConta.CREDORA and tipo == TipoPartida.CREDITO
    )
    return valor if mesmo_lado else -valor


def _calcular_zeramento(*, empresa, parametro, data_final):
    """Calcula, SEM GRAVAR NADA, os itens que `zerar_resultado` geraria
    para (empresa, data_final) sob o `parametro` vigente — a MESMA conta,
    chamada tanto pela prévia (`pre_visualizar_zeramento`, GET, leitura
    sem trava — best-effort, pode divergir de uma execução concorrente
    entre a prévia e o POST) quanto pela execução real (`zerar_resultado`,
    dentro da trava de competência e de empresa).

    Devolve um dict:
    - `itens_etapa1`: lista de `{"conta", "tipo", "valor"}` (uma por conta
      de receita/despesa com saldo PRÓPRIO diferente de zero acumulado até
      `data_final` — RC-104, corrigido pelo achado B1: nunca o saldo
      consolidado com descendentes).
    - `item_resultado_etapa1`: o item de CONTRAPARTIDA em "resultado do
      exercício" que fecha os débitos e créditos de `itens_etapa1` — `None`
      quando `itens_etapa1` já fecha por si (resultado exatamente zero:
      receita = despesa) ou quando `itens_etapa1` está vazia.
    - `etapa2`: `None` (nada a transferir) ou
      `{"item_resultado", "item_destino", "destino"}`, onde `destino` é
      `"lucros_acumulados"` ou `"prejuizos_acumulados"` (RC-104: destino
      pelo SINAL do resultado).

    Levanta `ParametroContabilInvalido` se alguma conta de receita/despesa
    SINTÉTICA (`aceita_lancamento=False`) tiver saldo PRÓPRIO diferente de
    zero — estado LEGADO (DE-078 item 1/B1): o zeramento nunca ignora esse
    valor em silêncio, porque ele sumiria da apuração sem nenhum aviso.

    ⚠️ **UMA única chamada a `apurar_balancete` para TODAS as contas
    (DE-078 item 5/B5, correção do cálculo QUADRÁTICO):** antes desta
    correção, `_saldo_assinado_ate` chamava `apurar_balancete` (3
    consultas próprias) uma vez POR CONTA de receita/despesa — o custo
    crescia com o QUADRADO do número de contas, e a auditoria mediu 4,84s
    e 910 consultas com 300 contas, dentro da trava de competência
    (bloqueando outros lançamentos do mês por todo esse tempo). Agora o
    balancete é apurado UMA vez, e cada conta lê a própria linha por
    código, num dict já montado em memória — custo constante em relação
    ao número de contas de receita/despesa.
    """
    balancete = apurar_balancete(empresa=empresa, inicio=data_final, fim=data_final)
    linhas_por_codigo = {linha["conta"]: linha for linha in balancete["contas"]}

    itens_etapa1 = []
    for conta in _contas_de_resultado(empresa):
        linha = linhas_por_codigo.get(conta.codigo)
        saldo_proprio = _saldo_proprio_assinado(linha) if linha is not None else Decimal("0")
        if saldo_proprio == 0:
            continue
        if not conta.aceita_lancamento:
            # B1: sintética LEGADA com saldo próprio — ver o docstring.
            raise ParametroContabilInvalido(
                f"A conta {conta.codigo} — {conta.nome} não aceita lançamento direto "
                f"(é sintética), mas tem saldo próprio diferente de zero ({saldo_proprio}); "
                "o zeramento não pode ignorar esse valor em silêncio. Corrija o cadastro "
                "ou o movimento desta conta antes de zerar o resultado."
            )
        item = _item_de_zeramento(conta, saldo_proprio)
        if item is not None:
            itens_etapa1.append(item)

    zero = Decimal("0")
    total_debito = sum(
        (item["valor"] for item in itens_etapa1 if item["tipo"] == TipoPartida.DEBITO), zero
    )
    total_credito = sum(
        (item["valor"] for item in itens_etapa1 if item["tipo"] == TipoPartida.CREDITO), zero
    )
    diferenca = total_debito - total_credito

    item_resultado_etapa1 = None
    if diferenca != 0:
        # A contrapartida em "resultado do exercício" é sempre do lado que
        # FALTA para igualar débito e crédito de `itens_etapa1` — nunca
        # calculada a partir de receita/despesa separadamente (o que
        # exigiria presumir que toda receita é credora e toda despesa
        # devedora, presunção que uma retificadora quebra). Quando
        # `diferenca == 0` (receita = despesa item a item, resultado
        # exatamente zero), `itens_etapa1` já fecha por construção e
        # NENHUM item de resultado é necessário nem permitido (um item de
        # valor zero seria recusado por `criar_lancamento`) — é o caso
        # "resultado zero" do critério 2 do plano.
        tipo_resultado = TipoPartida.CREDITO if diferenca > 0 else TipoPartida.DEBITO
        item_resultado_etapa1 = {
            "conta": parametro.conta_resultado_do_exercicio,
            "tipo": tipo_resultado,
            "valor": abs(diferenca),
        }

    # Etapa 2: simula o saldo de "resultado do exercício" DEPOIS do item
    # acima (ainda sem gravar nada) para decidir se há o que transferir, e
    # para qual das duas contas (RC-104: destino pelo SINAL). Lê a MESMA
    # `linha` já carregada acima (nenhuma consulta nova) — "resultado do
    # exercício" é, por construção (`registrar_parametro_contabil`, DE-078
    # item 1), uma conta FOLHA, então saldo próprio e saldo consolidado
    # coincidem para ela; usar o próprio de qualquer forma mantém a MESMA
    # convenção de todo o resto deste cálculo.
    linha_resultado = linhas_por_codigo.get(parametro.conta_resultado_do_exercicio.codigo)
    saldo_resultado_atual = (
        _saldo_proprio_assinado(linha_resultado) if linha_resultado is not None else zero
    )
    saldo_resultado_pos_etapa1 = saldo_resultado_atual
    if item_resultado_etapa1 is not None:
        saldo_resultado_pos_etapa1 += _efeito_no_saldo_assinado(
            parametro.conta_resultado_do_exercicio,
            item_resultado_etapa1["tipo"],
            item_resultado_etapa1["valor"],
        )

    etapa2 = None
    item_resultado_etapa2 = _item_de_zeramento(
        parametro.conta_resultado_do_exercicio, saldo_resultado_pos_etapa1
    )
    if item_resultado_etapa2 is not None:
        # Sinal VERDADEIRO (D/C), não o assinado pela natureza cadastrada:
        # é o que decide lucro (credor) ou prejuízo (devedor) pelo RC-104,
        # independentemente de "resultado do exercício" ter sido cadastrada
        # devedora ou credora.
        credor_verdadeiro = (
            saldo_resultado_pos_etapa1
            if parametro.conta_resultado_do_exercicio.natureza == NaturezaConta.CREDORA
            else -saldo_resultado_pos_etapa1
        )
        if credor_verdadeiro > 0:
            destino_nome = "lucros_acumulados"
            conta_destino = parametro.conta_lucros_acumulados
        else:
            destino_nome = "prejuizos_acumulados"
            conta_destino = parametro.conta_prejuizos_acumulados

        # O item de destino é sempre o OPOSTO do item que zera "resultado
        # do exercício" — é o que faz o lançamento de DUAS pernas (RC-104)
        # bater sem cálculo à parte: mesmo valor, tipo trocado.
        tipo_destino = (
            TipoPartida.CREDITO
            if item_resultado_etapa2["tipo"] == TipoPartida.DEBITO
            else TipoPartida.DEBITO
        )
        etapa2 = {
            "item_resultado": item_resultado_etapa2,
            "item_destino": {
                "conta": conta_destino,
                "tipo": tipo_destino,
                "valor": item_resultado_etapa2["valor"],
            },
            "destino": destino_nome,
        }

    return {
        "itens_etapa1": itens_etapa1,
        "item_resultado_etapa1": item_resultado_etapa1,
        "etapa2": etapa2,
    }


def _dividir_em_lancamentos_balanceados(itens_zerados, *, conta_resultado):
    """Divide `itens_zerados` (os itens de `itens_etapa1` — SEM a
    contrapartida) em grupos que cabem no teto de partidas por lançamento
    (RC-79, `LIMITE_PARTIDAS_POR_LANCAMENTO`) — DE-078 item 5, correção do
    achado B3 (ALTA): sem isto, uma empresa com 200 contas de resultado ou
    mais NUNCA conseguia zerar (o único `criar_lancamento` da etapa 1
    recusava com `LancamentoInvalido`, que a view deixava vazar como 500).

    Cada grupo recebe a SUA PRÓPRIA contrapartida em "resultado do
    exercício" — recalculada a partir dos itens DAQUELE grupo, nunca uma
    fração do total original — para que cada lançamento feche
    (débito = crédito) por si só, sozinho, sem depender de nenhum outro
    grupo. A soma das contrapartidas de todos os grupos é, por construção,
    igual à contrapartida ÚNICA que `_calcular_zeramento` calcularia
    (débito/crédito somam de forma aditiva entre grupos) — os dois
    caminhos concordam sobre o total transferido.

    Reserva UMA vaga de cada grupo para a própria contrapartida (o teto
    vale para o lançamento inteiro, contrapartida incluída). Devolve uma
    lista de listas de itens — o caso comum (dentro do teto) devolve uma
    lista com UM único grupo, idêntico ao que `zerar_resultado` gravava
    antes desta correção (chave sem sufixo `:parteN` — ver
    `_chave_idempotencia_zeramento`).
    """
    if not itens_zerados:
        return []

    tamanho_do_grupo = LIMITE_PARTIDAS_POR_LANCAMENTO - 1
    grupos_de_itens = [
        itens_zerados[inicio : inicio + tamanho_do_grupo]
        for inicio in range(0, len(itens_zerados), tamanho_do_grupo)
    ]

    zero = Decimal("0")
    lancamentos = []
    for itens_do_grupo in grupos_de_itens:
        debito_do_grupo = sum(
            (item["valor"] for item in itens_do_grupo if item["tipo"] == TipoPartida.DEBITO), zero
        )
        credito_do_grupo = sum(
            (item["valor"] for item in itens_do_grupo if item["tipo"] == TipoPartida.CREDITO), zero
        )
        diferenca_do_grupo = debito_do_grupo - credito_do_grupo
        itens_completos = list(itens_do_grupo)
        if diferenca_do_grupo != 0:
            tipo_contrapartida = (
                TipoPartida.CREDITO if diferenca_do_grupo > 0 else TipoPartida.DEBITO
            )
            itens_completos.append(
                {
                    "conta": conta_resultado,
                    "tipo": tipo_contrapartida,
                    "valor": abs(diferenca_do_grupo),
                }
            )
        lancamentos.append(itens_completos)
    return lancamentos


def _periodo_de_zeramento(*, empresa, ano, mes):
    """Validações comuns à prévia e à execução do zeramento — tudo o que
    NÃO depende de trava/gravação: faixa de mês, parâmetro vigente,
    correspondência periodicidade × mês de encerramento (critério 7) e
    período já terminado (HI-25).

    Devolve `(parametro, data_final)`. Levanta `ParametroContabilInvalido`
    (400) para qualquer uma das quatro causas.
    """
    if not (1 <= mes <= 12):
        raise ParametroContabilInvalido(f"'mes' inválido: {mes} — deve estar entre 1 e 12.")

    # `calendar.monthrange` devolve (dia da semana do dia 1, número de dias
    # do mês) — o segundo elemento É o último dia do mês, exatamente a data
    # final do período que `zerar_resultado` usa para o lançamento (RC-104:
    # o zeramento é lançado na data final do período).
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    data_final = date(ano, mes, ultimo_dia)

    # HI-25 (DE-078 item 4): período cujo ÚLTIMO DIA ainda não chegou não é
    # zerado. Antes desta correção, a única barreira era a faixa de data
    # de LANÇAMENTO (RC-77, hoje + 30 dias) — a auditoria mediu que isso
    # deixava a empresa zerar outubro ou novembro de 2026 estando ainda em
    # setembro, e a mensagem de erro do RC-77 (quando a faixa finalmente
    # recusava) não fazia sentido para quem pediu um zeramento, sem contar
    # que hoje == data_final é aceito por hora, e essa checagem existe
    # ANTES de qualquer cálculo, com mensagem própria do domínio.
    hoje = timezone.localdate()
    if data_final > hoje:
        raise ParametroContabilInvalido(
            f"O período cujo encerramento seria em {data_final.strftime('%d/%m/%Y')} ainda não "
            f"terminou (hoje é {hoje.strftime('%d/%m/%Y')}); não é possível zerar um período "
            "que ainda não acabou (HI-25)."
        )

    parametro = _parametro_contabil_vigente_em(empresa=empresa, data=data_final)
    if parametro is None:
        data_str = data_final.strftime("%d/%m/%Y")
        raise ParametroContabilInvalido(
            f"Esta empresa não tem parâmetro contábil vigente em {data_str}; cadastre a "
            "vigência (periodicidade e contas de destino) antes de zerar o resultado."
        )
    _validar_periodo_de_zeramento(periodicidade=parametro.periodicidade_zeramento, mes=mes)
    return parametro, data_final


def pre_visualizar_zeramento(*, empresa, ano, mes):
    """Prévia do zeramento (DL-043, GET — "devolve os valores que seriam
    lançados, sem gravar"): mesmas validações e o MESMO cálculo
    (`_calcular_zeramento`) de `zerar_resultado`, sem trava de competência
    ou de empresa e sem gravar nada — leitura best-effort, que pode
    divergir do que a execução real produzir se, entre a prévia e o POST,
    outra requisição gravar lançamento no período ou mudar a vigência.
    `zerar_resultado` é sempre a fonte da verdade; esta função é
    conveniência de conferência antes de gravar (critério "prévia" do
    plano).

    Levanta `ParametroContabilInvalido` (400) para empresa em livro-caixa,
    período/periodicidade incompatíveis, período ainda não terminado
    (HI-25) ou empresa sem parâmetro vigente, e `ZeramentoForaDeOrdem`
    (409, DE-078 item 2/B2) se já existir zeramento posterior — um
    vocabulário só de exceção, mesmo padrão de `criar_lancamento`
    traduzindo `EmpresaEmModoLivroCaixa` para o vocabulário do próprio
    serviço em vez de vazar um tipo de outro módulo.
    """
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        raise ParametroContabilInvalido(exc.mensagem) from exc
    parametro, data_final = _periodo_de_zeramento(empresa=empresa, ano=ano, mes=mes)
    _recusar_zeramento_fora_de_ordem(empresa=empresa, data_final=data_final)
    calculo = _calcular_zeramento(empresa=empresa, parametro=parametro, data_final=data_final)
    return {
        "parametro": parametro,
        "data_final": data_final,
        **calculo,
    }


@transaction.atomic
def zerar_resultado(*, empresa, ano, mes, usuario, request=None):
    """Zera o resultado do período cuja competência final é (ano, mes),
    segundo a periodicidade vigente da empresa (DL-043 fatia 2, RC-104/
    RC-105) — dentro de UMA transação, com a trava de EMPRESA (DE-078
    item 3/B2(b)/B10) seguida da trava de competência que
    `encerrar_competencia` já usa.

    Gera, na DATA FINAL do período (último dia de `mes`/`ano`):

    1. Um ou mais lançamentos (DE-078 item 5/B3: divididos quando
       excedem o teto de partidas, RC-79 — ver `_dividir_em_lancamentos_
       balanceados`) que zeram o saldo PRÓPRIO ACUMULADO (nunca o
       consolidado com descendentes — correção do achado B1) de cada
       conta de receita/despesa contra a conta "resultado do exercício"
       — só se houver ao menos uma conta com saldo próprio diferente de
       zero (critério 2 do plano: "resultado zero" ainda assim zera
       receita/despesa quando elas não são zero individualmente, mas se
       TUDO já está zero não gera lançamento nenhum).
    2. Um lançamento que transfere o saldo de "resultado do exercício"
       para "lucros acumulados" (credor) ou "(-) prejuízos acumulados"
       (devedor), pelo SINAL — só se esse saldo for diferente de zero
       depois do item 1.

    IDEMPOTÊNCIA e COMPLEMENTO (critério 5): cada etapa usa uma
    `chave_idempotencia` DETERMINÍSTICA por (empresa, período, etapa,
    complemento) — ver `_chave_idempotencia_zeramento`. Como o cálculo lê
    o saldo PRÓPRIO ACUMULADO (não o "ainda não zerado" somado à parte),
    repetir a chamada sem movimento novo sempre encontra saldo zero em
    toda conta (o zeramento anterior já levou tudo a zero) e não gera
    lançamento nenhum; uma chamada depois de movimento novo no período
    (competência ainda aberta) encontra só a DIFERENÇA ainda não zerada,
    e gera exatamente o COMPLEMENTO — nunca duplica o que já foi zerado.

    ORDEM CRONOLÓGICA (DE-078 item 2/B2, BLOQUEADOR): recusa
    (`ZeramentoForaDeOrdem`, 409) se já existir zeramento da MESMA
    empresa com data POSTERIOR à data final deste período — zerar (ou
    complementar) fora de ordem contaria parte do resultado duas vezes
    (a auditoria mediu 15 de 15 rodadas erradas com meses concorrentes).
    Checado DEPOIS da trava de empresa, para a checagem ser autoritativa.

    CONCORRÊNCIA (critério 5, B2(b) e B10): a EMPRESA é travada primeiro
    (`_travar_empresa_para_operacao_de_zeramento`) — serializa TODOS os
    zeramentos da mesma empresa, mesmo entre PERÍODOS diferentes, o que a
    trava de competência (adquirida depois, para o período específico)
    não fazia. Dois pedidos do MESMO período serializam nas DUAS travas;
    dois pedidos de períodos DIFERENTES da MESMA empresa agora também
    serializam, só na trava de empresa. O segundo pedido, em qualquer dos
    dois casos, só lê o estado (e os saldos já zerados pelo primeiro)
    depois que o primeiro COMMITAR.

    COMPETÊNCIA ENCERRADA (RC-57): recusa (`CompetenciaEncerrada`, 409)
    ANTES de calcular qualquer saldo — a correção de um período encerrado
    segue o estorno (RC-103), nunca um novo zeramento por cima.

    PERMISSÃO (RC-102): verificada pela view (`PodeFecharCompetencia`,
    ADMINISTRADOR/GESTOR), no servidor — esta função não verifica papel;
    quem a chama sem passar pela view (shell, tarefa em segundo plano)
    assume a responsabilidade da autorização, mesmo padrão de
    `encerrar_competencia`.

    TRILHA: um único `registrar()`, na MESMA transação, com o resultado
    completo da chamada (que lançamentos foram criados/reaproveitados).
    `request` é opcional (DE-078/B8: trilha sem IP) — só serve para o
    `registrar()` capturar o endereço IP quando existir uma requisição
    HTTP por trás; parâmetro NOVO, keyword, com padrão `None` — chamada
    direta (sem `request`) continua funcionando exatamente como antes.
    """
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        raise ParametroContabilInvalido(exc.mensagem) from exc

    # A trava de EMPRESA mora AQUI, ANTES de resolver o parâmetro vigente
    # e de calcular qualquer saldo — ver a nota de concorrência do
    # docstring e o docstring de `_travar_empresa_para_operacao_de_
    # zeramento`.
    _travar_empresa_para_operacao_de_zeramento(empresa)

    parametro, data_final = _periodo_de_zeramento(empresa=empresa, ano=ano, mes=mes)
    _recusar_zeramento_fora_de_ordem(empresa=empresa, data_final=data_final)

    # A trava de COMPETÊNCIA vem DEPOIS da de empresa (ordem fixa — ver o
    # docstring de `_travar_empresa_para_operacao_de_zeramento` — para
    # nunca haver dependência circular de lock entre chamadas
    # concorrentes). `_travar_competencia_para_transicao` é o MESMO `FOR
    # UPDATE` que `encerrar_competencia`/`reabrir_competencia`/`marcar_
    # competencia_como_entregue` usam — reusar em vez de inventar uma
    # segunda trava para o mesmo recurso (a competência de destino).
    competencia = obter_ou_criar_competencia(empresa=empresa, ano=ano, mes=mes)
    competencia = _travar_competencia_para_transicao(competencia, ano=ano, mes=mes, empresa=empresa)
    if competencia.estado != EstadoCompetencia.ABERTA:
        nome_do_estado = EstadoCompetencia(competencia.estado).label.lower()
        raise CompetenciaEncerrada(
            f"A competência {mes:02d}/{ano} de {empresa} está '{nome_do_estado}'; não é "
            "possível zerar o resultado nela. A correção de período encerrado segue o "
            "estorno (RC-103), nunca um novo zeramento por cima."
        )

    calculo = _calcular_zeramento(empresa=empresa, parametro=parametro, data_final=data_final)

    historico_base = (
        f"Zeramento do resultado ({parametro.get_periodicidade_zeramento_display()}) — "
        f"encerramento de {mes:02d}/{ano}"
    )

    # DE-078 item 5 (B3): a etapa 1 pode virar VÁRIOS lançamentos quando
    # excede o teto de partidas (RC-79) — cada "parte" do MESMO
    # complemento leva a MESMA chave-base com sufixo `:parteN` (ver
    # `_chave_idempotencia_zeramento`). No caso comum (dentro do teto),
    # `grupos_etapa1` tem exatamente UM grupo, e a chave sai SEM sufixo —
    # idêntica à de antes desta correção.
    grupos_etapa1 = _dividir_em_lancamentos_balanceados(
        calculo["itens_etapa1"], conta_resultado=parametro.conta_resultado_do_exercicio
    )
    lancamentos_etapa1 = []
    if grupos_etapa1:
        complemento1 = _proximo_complemento(empresa=empresa, ano=ano, mes=mes, etapa=1)
        multiplas_partes = len(grupos_etapa1) > 1
        for indice, itens_do_grupo in enumerate(grupos_etapa1):
            chave1 = _chave_idempotencia_zeramento(
                empresa_id=empresa.pk,
                ano=ano,
                mes=mes,
                etapa=1,
                complemento=complemento1,
                parte=indice if multiplas_partes else None,
            )
            lancamentos_etapa1.append(
                criar_lancamento(
                    empresa=empresa,
                    data=data_final,
                    historico=f"{historico_base} — contas de resultado",
                    itens=itens_do_grupo,
                    criado_por=usuario,
                    chave_idempotencia=chave1,
                    permitir_prefixo_reservado=True,
                )
            )

    lancamento_etapa2 = None
    if calculo["etapa2"] is not None:
        etapa2 = calculo["etapa2"]
        rotulo_destino = (
            "lucros acumulados"
            if etapa2["destino"] == "lucros_acumulados"
            else "(-) prejuízos acumulados"
        )
        complemento2 = _proximo_complemento(empresa=empresa, ano=ano, mes=mes, etapa=2)
        chave2 = _chave_idempotencia_zeramento(
            empresa_id=empresa.pk, ano=ano, mes=mes, etapa=2, complemento=complemento2
        )
        lancamento_etapa2 = criar_lancamento(
            empresa=empresa,
            data=data_final,
            historico=f"{historico_base} — transferência para {rotulo_destino}",
            itens=[etapa2["item_resultado"], etapa2["item_destino"]],
            criado_por=usuario,
            chave_idempotencia=chave2,
            permitir_prefixo_reservado=True,
        )

    # `lancamento_etapa1`/`criado_etapa1` continuam existindo, apontando
    # para o PRIMEIRO grupo — compatibilidade com quem já lê estas duas
    # chaves (o caso comum, dentro do teto de partidas, tem exatamente um
    # grupo, então elas nunca mudam de significado nesse caso).
    # `lancamentos_etapa1` (lista, sempre presente) é o contrato COMPLETO,
    # para quem precisar dos grupos adicionais.
    primeiro_lancamento_etapa1 = lancamentos_etapa1[0] if lancamentos_etapa1 else None
    resultado = {
        "empresa_id": empresa.id,
        "ano": ano,
        "mes": mes,
        "data_final": data_final,
        "periodicidade_zeramento": parametro.periodicidade_zeramento,
        "lancamento_etapa1": primeiro_lancamento_etapa1,
        "criado_etapa1": bool(primeiro_lancamento_etapa1)
        and primeiro_lancamento_etapa1.criado_agora,
        "lancamentos_etapa1": lancamentos_etapa1,
        "lancamento_etapa2": lancamento_etapa2,
        "criado_etapa2": bool(lancamento_etapa2) and lancamento_etapa2.criado_agora,
        "destino_etapa2": calculo["etapa2"]["destino"] if calculo["etapa2"] else None,
    }
    registrar(
        acao="zeramento.resultado",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=competencia,
        request=request,
        detalhes={
            "empresa_id": empresa.id,
            "ano": ano,
            "mes": mes,
            "lancamentos_etapa1_ids": [lanc.pk for lanc in lancamentos_etapa1],
            "criado_etapa1": resultado["criado_etapa1"],
            "lancamento_etapa2_id": lancamento_etapa2.pk if lancamento_etapa2 else None,
            "criado_etapa2": resultado["criado_etapa2"],
        },
    )
    return resultado


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


def apurar_balancete(*, empresa, inicio, fim, nivel=None, criterio_de_apuracao="todas"):
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

    `criterio_de_apuracao` (DL-027 Fatia B.2) controla o RECORTE da lista de
    linhas exibidas — não afeta o TOTAL (que continua somando TODOS os
    itens do período, em agregação independente). Dois valores aceitos:

    - `"todas"` (padrão): comportamento idêntico ao código anterior. Todas
      as contas da empresa aparecem, independente de saldo ou movimento.
    - `"com_movimento"`: mantém contas com movimento consolidado no
      período OU saldo líquido de abertura diferente de zero. Débitos e
      créditos históricos compensatórios não contam como saldo de
      abertura. Sintéticas cujo movimento ou saldo veio dos filhos
      continuam aparecendo, o que preserva a leitura hierárquica.

    O `criterio_de_apuracao` é uma propriedade da EMISSÃO (não do
    cadastro), decidido na view via querystring — sem migração de modelo
    nesta fatia (PE-65). O nome da função é puro: sem I/O, decide só
    em cima do resultado já calculado.

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

    # DL-032 fatia 1, correção do achado A2 (BL-475): id da RAIZ de cada
    # conta, para expor `tipo_da_raiz` por linha SEM consulta nova — só
    # percorre `conta_pai_id`, já carregado em `contas_por_id` pela mesma
    # `_construir_hierarquia` acima (memoizado, como `nivel_de`). Ciclo ou
    # `conta_pai` de outra empresa já levantou `HierarquiaInconsistente`
    # ali, então esta função nunca anda sobre uma cadeia quebrada.
    raizes_por_id = {}

    def raiz_id_de(conta_id):
        if conta_id in raizes_por_id:
            return raizes_por_id[conta_id]
        conta = contas_por_id[conta_id]
        if conta.conta_pai_id is None:
            raizes_por_id[conta_id] = conta_id
        else:
            raizes_por_id[conta_id] = raiz_id_de(conta.conta_pai_id)
        return raizes_por_id[conta_id]

    # DL-033 (RC-106): classificação (circulante/não circulante) do
    # ANCESTRAL MAIS PRÓXIMO desta conta — estritamente ACIMA, nunca a
    # própria —, memoizado como `raiz_id_de` acima, sem consulta nova.
    # Diferente de `tipo` (sempre preenchido em toda conta), a classificação
    # é OPCIONAL e pode ser declarada em QUALQUER nível da árvore (o nó que
    # representa "Ativo Circulante", por exemplo, normalmente um ou dois
    # níveis abaixo da raiz "Ativo" — nunca a raiz inteira, que a lei não
    # classifica). Existe para `apurar_saldos` distinguir, sem consulta
    # nova, três situações: (1) a própria conta DEFINE a classificação do
    # grupo (tem `classificacao_patrimonial` própria e NENHUM ancestral
    # também classificado) — soma o `saldo_final` dela (já CONSOLIDADO,
    # própria + toda a subárvore, pela mesma regra única de saldo — DE-020
    # — que `tipo_da_raiz` já usa) no grupo; (2) a conta está ANINHADA sob
    # outra já classificada (tem a própria E um ancestral classificado —
    # dado inconsistente: duas contas da MESMA árvore declarando o MESMO
    # dinheiro) — DECLARADA, nunca somada de novo, mesmo padrão do achado
    # A2/BL-475 da DL-032; (3) a conta HERDA a classificação de um
    # ancestral (não tem a própria, mas um ancestral tem) — já está coberta
    # pelo saldo consolidado desse ancestral, não entra em soma nem em
    # declaração de "sem classificação".
    classificacoes_ancestrais_por_id = {}

    def classificacao_ancestral_de(conta_id):
        if conta_id in classificacoes_ancestrais_por_id:
            return classificacoes_ancestrais_por_id[conta_id]
        conta = contas_por_id[conta_id]
        if conta.conta_pai_id is None:
            resultado = None
        else:
            pai = contas_por_id[conta.conta_pai_id]
            resultado = pai.classificacao_patrimonial or classificacao_ancestral_de(
                conta.conta_pai_id
            )
        classificacoes_ancestrais_por_id[conta_id] = resultado
        return resultado

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
        # DL-027 Fatia B.2: recorte "com_movimento" mantém movimento
        # consolidado no período OU saldo líquido de abertura não zero.
        # O teste do saldo é líquido e leva em conta a natureza da conta:
        # débitos e créditos históricos compensatórios não deixam saldo
        # para conferir. Movimento e saldo são consolidados (próprio +
        # descendentes), portanto sintéticas continuam visíveis quando
        # algum filho tem atividade ou saldo de abertura relevante.
        if criterio_de_apuracao == "com_movimento":
            tem_movimento_periodo = (
                bruto["debito_periodo"] > zero or bruto["credito_periodo"] > zero
            )
            tem_saldo_anterior = saldo_anterior != zero
            if not (tem_movimento_periodo or tem_saldo_anterior):
                continue
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

        # DL-034 (BL-496, critério 1 condição 4) — `debitos_proprios_totais`/
        # `creditos_proprios_totais`: a MESMA ideia de "próprio" acima
        # (bruto desta conta menos o dos filhos exibidos), mas somando
        # ANTERIOR e PERÍODO juntos — "houve movimento próprio ALGUMA VEZ
        # até `fim`", não só "neste período". Campo NOVO, aditivo: NÃO
        # substitui `debitos_proprios`/`creditos_proprios` acima, cuja
        # identidade com o rodapé (`total_debitos`/`total_creditos`, também
        # escopados ao período) continua valendo exatamente como antes —
        # mudar aquele campo para somar `saldo_anterior` quebraria essa
        # reconciliação (BL-281) por uma necessidade de OUTRA camada. Existe
        # porque `apurar_saldos` chama `apurar_balancete(inicio=fim=data_
        # base)`: um lançamento antigo (a maioria, na prática) cai inteiro em
        # `saldo_anterior`, e `debitos_proprios`/`creditos_proprios` (só
        # período) ficariam ZERO para uma conta com movimento próprio real,
        # só mais antigo que `data_base` — a guarda ficaria cega para o
        # caso comum, só pegando quem tem movimento próprio bem no dia de
        # corte.
        debitos_totais = bruto["debito_anterior"] + bruto["debito_periodo"]
        creditos_totais = bruto["credito_anterior"] + bruto["credito_periodo"]
        debitos_proprios_totais = debitos_totais - sum(
            (
                brutos[filho_id]["debito_anterior"] + brutos[filho_id]["debito_periodo"]
                for filho_id in filhos_exibidos_ids
            ),
            zero,
        )
        creditos_proprios_totais = creditos_totais - sum(
            (
                brutos[filho_id]["credito_anterior"] + brutos[filho_id]["credito_periodo"]
                for filho_id in filhos_exibidos_ids
            ),
            zero,
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
                #
                # `tipo_da_raiz` (correção do achado A2, BL-475/DL-032): o
                # `tipo` do ANCESTRAL raiz desta conta — igual ao próprio
                # `tipo` quando a linha É a raiz. Existe para
                # `apurar_saldos` DECLARAR (nunca corrigir) uma conta cujo
                # `tipo` próprio diverge do `tipo` da árvore em que está
                # pendurada: a agregação por raízes soma o saldo dela no
                # grupo da RAIZ (é a regra única de saldo, correta —
                # DE-020), então sem este campo a linha da conta e o
                # `totais_por_tipo` da resposta podiam se contradizer em
                # silêncio, e a equação fechava sem ter classificado nada.
                "tipo": conta.tipo,
                "tipo_da_raiz": contas_por_id[raiz_id_de(conta.id)].tipo,
                "raiz": conta.conta_pai_id is None,
                # `conta_pai` (DL-034, BL-496/critério 1 condição 3): o
                # CÓDIGO da conta pai direta (ou `None` para raiz) — sem
                # consulta nova, `contas_por_id` já carregou a árvore
                # inteira. Existe só para `apurar_saldos` agrupar contas
                # IRMÃS (mesmo pai) sem reabrir o banco, na guarda que
                # detecta nós topo-classificados de natureza cadastrada
                # divergente sob o mesmo ancestral não classificado (o
                # mesmo padrão de "expor um campo extra, de graça, para
                # quem consome" que `raiz`/`tipo_da_raiz` já seguem).
                "conta_pai": (
                    contas_por_id[conta.conta_pai_id].codigo
                    if conta.conta_pai_id is not None
                    else None
                ),
                # `classificacao_patrimonial`/`classificacao_patrimonial_
                # ancestral` (DL-033/RC-106): a classificação PRÓPRIA desta
                # conta (ou `None`) e a do ANCESTRAL mais próximo que tiver
                # uma (ou `None`, inclusive quando a conta é raiz — sem
                # ancestral nenhum). Ver o docstring de
                # `classificacao_ancestral_de`, acima, para os três casos
                # que os dois campos juntos permitem `apurar_saldos`
                # distinguir sem consulta nova.
                "classificacao_patrimonial": conta.classificacao_patrimonial,
                "classificacao_patrimonial_ancestral": classificacao_ancestral_de(conta.id),
                "saldo_anterior": saldo_anterior,
                "debitos": debitos,
                "creditos": creditos,
                "debitos_proprios": debitos_proprios,
                "creditos_proprios": creditos_proprios,
                # DL-034/BL-496: "próprio", mas somando anterior + período —
                # ver o comentário de origem, acima, no laço que os calcula.
                "debitos_proprios_totais": debitos_proprios_totais,
                "creditos_proprios_totais": creditos_proprios_totais,
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


def avaliar_emissao_do_balancete(apuracao):
    """DL-027 Fatia B (item 3 do plano): decide, no SERVIDOR, se o Balancete
    de verificação PODE ser emitido a partir do resultado de
    `apurar_balancete`, e devolve um veredito estruturado para a view
    consumir.

    Função PURA: não toca em banco, não lê request, não chama models.
    Recebe a apuração pronta (o mesmo dict que `apurar_balancete`
    devolve) e devolve três chaves:

    - `pode_emitir` (bool): a decisão que a view obedece.
    - `veredito` (Literal["fecha", "nao_fecha", "nada_a_conferir"]):
      rótulo para a faixa do documento, no mesmo formato que a view já
      usava para o display (BL-290 / A2 da DL-026 rodada 2).
    - `diferenca_ptbr` (Optional[str]): `None` exceto quando `veredito
      == "nao_fecha"`, onde traz `|total_debitos - total_creditos|` em
      pt-BR (`_valor_ptbr`) — a tela mostra onde está o desvio.

    TrÊS ramos:

    1. `nada_a_conferir`: total_debitos == 0 E total_creditos == 0 — não
       há o que conferir (sem movimento no período). **Pode emitir**
       (o BL-302/B4 da DL-026 corrigiu exatamente o veto silencioso que
       dizer "Fecha" sobre 0,00/0,00 seria).
    2. `fecha`: total_debitos == total_creditos, com movimento no
       período. **Pode emitir**.
    3. `nao_fecha`: total_debitos != total_creditos. **NÃO pode
       emitir** — o documento sai com um desvio que a partida dobrada
       proíbe. Por construção de `criar_lancamento`, isto é
       inalcançável em uso normal do produto; a porta existe para o dia
       em que algo corromper o dado (rede de segurança — uma rede que
       ninguém nunca viu funcionar não é rede).

    Comparação em `Decimal`, nunca em texto pt-BR já formatado (a mesma
    lição do BL-290: `_valor_ptbr` arredonda, e 300,004 vs 300,00 viram
    o mesmo "300,00" lado a lado). A função `_valor_ptbr` mora na
    view porque é formatação para a tela; aqui só decide em Decimal.

    Não verifica autorização nem papel: o que a `request` pode fazer
    continua sendo da `view` (e da `Empresa.objects.filter(...)` que
    antecede a chamada a `apurar_balancete`).

    O contrato paralelo é o de `avaliar_emissao_do_balanco` (DL-034):
    mesma forma de devolver a decisão, mesma regra de "decide no
    server, view pergunta e obedece". Diário e Razão vão reusar a
    mesma estrutura quando entrarem na mesma etapa — é o catálogo
    do plano, não três implementações separadas (AGENTS.md §8).
    """
    total_debitos = apuracao["total_debitos"]
    total_creditos = apuracao["total_creditos"]

    if total_debitos == 0 and total_creditos == 0:
        return {
            "pode_emitir": True,
            "veredito": "nada_a_conferir",
            "diferenca_ptbr": None,
        }
    if total_debitos == total_creditos:
        return {
            "pode_emitir": True,
            "veredito": "fecha",
            "diferenca_ptbr": None,
        }
    diferenca = abs(total_debitos - total_creditos)
    return {
        "pode_emitir": False,
        "veredito": "nao_fecha",
        "diferenca_ptbr": _formatar_diferenca_ptbr(diferenca),
    }


def _formatar_diferenca_ptbr(valor_decimal):
    """`Decimal` → pt-BR com 2 casas. Função local de `services` (não
    importa a de `views_web`) porque a função pura não pode puxar o
    módulo da view — `views_web` importa `services` (dependência
    invertida), e o ciclo seria import-time. A view usa a sua
    própria `_valor_ptbr` para o display, e aqui só calcula o texto
    que vai na mensagem do veto."""
    # Mesma convenção que `_valor_ptbr` em views_web — quantiza a 2
    # casas e troca ponto por vírgula. Replicado aqui por simetria com
    # a regra do AGENTS.md §8 ("evitar duplicação de regras entre
    # tela, API, tarefa e IA"); a view continua usando a sua. É
    # formatação de moeda: 1 lugar, 1 regra.
    quantizado = valor_decimal.quantize(Decimal("0.01"))
    return f"{quantizado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    `(receita - despesa)` é o resultado AINDA NÃO transferido ao PL —
    exposto em `equacao["resultado_nao_transferido"]` (renomeado do
    `resultado_do_periodo` original, achado A4/BL-478: o nome antigo
    MENTIA sobre o que o valor é). Durante o exercício ele é diferente de
    zero sem que haja erro nenhum; depois do zeramento (RC-104: mensal,
    trimestral ou anual, por lançamento, contra uma conta "Resultado do
    Exercício" e desta para "Lucros Acumulados" ou, no prejuízo, para a
    retificadora "(-) Prejuízos Acumulados") o termo zera por construção e
    a equação vira a forma clássica — as duas formas são o MESMO cálculo,
    nunca um `if` de "já encerrou". A diferença (`equacao["diferenca"]`) é
    CALCULADA e DEVOLVIDA, com valor e sinal; NENHUM saldo é alterado para
    fechá-la (critério 2) — "o que eu somei fecha, e quando não fecha eu
    digo, nunca conserto".

    ⚠️ **Esta camada NÃO serve para apurar a DRE (RC-104, penúltima
    ressalva).** Com zeramento mensal ou trimestral, `resultado_nao_
    transferido` reporta ZERO logo depois de cada fechamento, mesmo num mês
    lucrativo — porque é o SALDO ainda não transferido, e o zeramento acabou
    de levá-lo a zero (ver
    `test_apos_zeramento_resultado_nao_transferido_e_zero_mas_resultado_do_mes_nao`).
    A DRE de um período se constrói pelo MOVIMENTO do período (créditos de
    Receita, débitos de Despesa dentro de `[inicio, fim]`), nunca pelo saldo
    de `data_base` — quem precisar disso chama `apurar_balancete(inicio,
    fim)` diretamente e lê `debitos`/`creditos`, não `apurar_saldos`.

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

    ⚠️ **Conta descendente com `tipo` diferente do `tipo` da raiz (achado
    A2/BL-475):** a agregação por raízes (acima) atribui o saldo
    CONSOLIDADO da árvore inteira ao `tipo` da RAIZ — decisão certa,
    provada por mutação contra a retificadora do RC-104 (somar todas as
    linhas ou só as folhas quebra `test_retificadora_...`). Mas isso tem
    uma premissa: a árvore é homogênea de `tipo`. Quando não é (mau
    cadastro: uma conta "Despesa" pendurada sob a raiz do "Ativo"), esta
    função NUNCA reclassifica nem corrige — DECLARA:
    `contas_com_tipo_divergente_da_raiz` lista, para cada conta cujo
    `tipo` PRÓPRIO diverge do `tipo` da sua raiz, `{"conta", "nome",
    "tipo", "tipo_da_raiz"}`; VAZIA no caso são (plano de contas
    coerente). Sem isto, a linha da conta dizia um `tipo` e
    `totais_por_tipo` dizia outro, contradizendo-se no mesmo dicionário, e
    a `equacao["diferenca"]` fechava em zero — a camada afirmando ter
    classificado o que não classificou. Quem consumir esta camada (fatia
    2) trata uma lista não vazia como aviso, no molde de
    `HierarquiaInconsistente`.

    ⚠️ **Tipo gravado fora de `TipoConta` (achado A1/BL-476):** o banco não
    tem CHECK que impeça um `tipo` fora de `choices` (só alcançável por
    ORM/SQL direto ou por uma migração de dado futura — a tela e o
    serializer sempre validam `choices`). Esta função NUNCA estoura
    `KeyError` nem cria uma chave nova dentro de `totais_por_tipo` (o que
    desmontaria a garantia do critério 4/DE-056, que `totais_por_tipo` tem
    EXATAMENTE as chaves de `TipoConta.values`): o tipo desconhecido
    aparece, nomeado, em `contas_com_tipo_desconhecido`
    (`{"conta", "nome", "tipo"}`), vazia no caso normal.

    ⚠️ **A frase acima ("tipo desconhecido") NÃO diz que o DINHEIRO some —
    e essa distinção depende de a conta corrompida ser RAIZ ou DESCENDENTE
    (achado NOVO, BL-484, nascido da própria correção do A1):** quando a
    conta corrompida É a raiz, o valor dela fica de fato OMITIDO de
    `totais_por_tipo` (nenhum `TipoConta` real recebe aquele saldo — é o
    caso do teste `test_tipo_gravado_fora_de_tipoconta_e_nomeado_nunca_
    derruba`). Quando a conta corrompida é DESCENDENTE de uma raiz com
    `tipo` VÁLIDO, o dinheiro NÃO desaparece: a regra única de saldo
    (DE-020) consolida a subárvore inteira — inclusive a conta corrompida
    — no saldo da raiz, que continua entrando normalmente em
    `totais_por_tipo` pelo `tipo` dela (válido). A conta corrompida, nesse
    caso, aparece NOMEADA em DUAS listas — `contas_com_tipo_desconhecido`
    **e** `contas_com_tipo_divergente_da_raiz` (o `tipo` dela nunca bate
    com o `tipo_da_raiz`, por construção) — mas o valor dela CONTINUA
    somado, por dentro do consolidado da raiz (ver `test_tipo_desconhecido_
    em_descendente_e_nomeado_mas_continua_somado`). **Omitir o descendente
    da soma seria PIOR** — o Balanço perderia dinheiro de verdade — então o
    comportamento certo nos dois casos não é "sempre omitir": é "nunca
    inventar", e as duas listas declaram o que a soma sozinha não diz.
    Mesma defesa (nomear, nunca inventar) que `views_web.py` já aplica ao
    campo irmão `natureza`.

    **`raiz` é repassado em cada linha de `contas` (achado A8/BL-481):**
    `linha["raiz"]` é EXATAMENTE `linha["nivel"] == 1` (toda conta sem pai
    é nível 1, e vice-versa) — dito aqui, com todas as letras, porque somar
    `contas` por `tipo` SEM filtrar por `raiz` conta cada descendente E sua
    raiz, dobrando (ou mais, em árvore mais funda) o valor de
    `totais_por_tipo`: a leitura que o critério 4 convida é a errada.
    `totais_por_tipo` já soma correto (só raízes) — é para quem quiser
    REPRODUZIR essa soma a partir de `contas` que `raiz` existe.

    **`HierarquiaInconsistente` pode escapar (achado A7/BL-480):** herdado
    do reuso de `apurar_balancete` → `_construir_hierarquia` — ciclo na
    hierarquia ou `conta_pai` de outra empresa (só alcançável por ORM
    direto, BL-40) levantam `HierarquiaInconsistente`, nomeando a conta,
    em vez de um `RecursionError`/`KeyError` cru. `apurar_saldos` NÃO
    trata essa exceção — propaga. Quem chamar por uma view (fatia 2)
    precisa do mesmo `try/except` que `views.py` e `views_web.py` já usam
    para `apurar_balancete`.

    **Conta inativa (`Conta.ativo=False`) entra no saldo (achado
    A9/BL-482):** deliberado — a consulta de `apurar_balancete` não filtra
    por `ativo`, então uma conta desativada com saldo residual continua
    aparecendo em `contas` e contribuindo para `totais_por_tipo`; do
    contrário o Balanço perderia dinheiro. A decisão de APRESENTAÇÃO
    (esconder linha de saldo zero de conta inativa, por exemplo) é da
    fatia que gerar o documento imprimível, não desta camada de leitura.

    ⚠️ **Leitura sem snapshot único (achado A6/DE-067, decisão do
    `arquiteto-senior`):** `apurar_balancete` faz TRÊS consultas
    (hierarquia, agregados por conta, total geral) e nenhuma delas está
    dentro de uma `transaction.atomic` com isolamento elevado — sob
    `READ COMMITTED` (padrão do PostgreSQL), cada uma recebe snapshot
    PRÓPRIO. Uma escrita concorrente (`criar_lancamento` de outra conexão)
    entre a 1ª e a 2ª consulta pode produzir uma diferença TRANSITÓRIA em
    `equacao["diferenca"]`, sem nenhum desbalanço real gravado na base —
    a diferença some na chamada seguinte. Esta fatia NÃO implementa
    `REPEATABLE READ` nem `SET TRANSACTION SNAPSHOT` (decisão consciente,
    DE-067: mexer no isolamento agora alteraria o Balancete inteiro do
    produto por causa de uma fatia que ainda não tem porta de entrada por
    requisição). Conclusão prática: a diferença só é CONCLUSIVA quando lida
    contra uma base parada (sem escrita concorrente) — é o caso de uso
    desta fatia (leitura ad-hoc, sem view ainda). A fatia que gerar o
    documento imprimível decide o snapshot.

    ⚠️ **Circulante × não circulante (DL-033/RC-106), o que falta para o
    Balanço Patrimonial existir:** `totais_por_classificacao` soma o
    `saldo_final` (CONSOLIDADO — própria conta + subárvore) de cada conta
    que DEFINE uma classificação (tem `classificacao_patrimonial` própria
    e nenhum ancestral também classificado — é o "raiz" de `tipo_da_raiz`,
    generalizado: aqui não é o topo absoluto da árvore, é o nó mais alto
    ONDE a classificação foi declarada, porque a lei não classifica o
    Ativo inteiro, só as suas subdivisões). **Esta camada NÃO adivinha
    classificação nenhuma** (a classe de erro do achado A2/BL-475 que
    reprovou a DL-032): conta sem classificação própria nem ancestral
    classificado é DECLARADA em `contas_sem_classificacao_patrimonial`
    (só para contas COM SALDO — critério BL-493, "a régua é o saldo, não
    a marca de `ativo`": classificar uma conta de saldo zero é trabalho
    sem efeito nenhum no Balanço — de tipo Ativo ou Passivo; Patrimônio
    Líquido, Receita e Despesa não entram na separação circulante/não
    circulante, RC-106); duas contas da mesma árvore tentando classificar
    o MESMO grupo (uma conta com classificação própria sob um ancestral
    TAMBÉM classificado) são DECLARADAS em `contas_com_classificacao_
    aninhada`, sem nunca somar o mesmo lançamento duas vezes. Um valor
    gravado fora de `ClassificacaoPatrimonial` (só por ORM/SQL direto —
    mesma defesa em profundidade do achado A1/BL-476 para `tipo`) NUNCA
    estoura `KeyError`: aparece, nomeado, em `contas_com_classificacao_
    desconhecida`.

    ⚠️ **As três listas acima são PISTAS, não a GARANTIA (achado BLOQUEADOR
    BL-486, rodada 1 de auditoria da DL-033) — quem garante é o RESÍDUO,
    abaixo.** A primeira versão desta camada tentou provar reconciliação
    catalogando CASOS (aninhamento, folha sem classificação) — e um
    catálogo de casos só cobre o que alguém pensou. O BL-486 mediu o caso
    que ninguém tinha pensado: DUAS contas IRMÃS (nenhuma ancestral da
    outra), cada uma com `classificacao_patrimonial` PRÓPRIA e naturezas
    DIFERENTES — ex.: "Clientes" (devedora, 1.220,00) e "(-) PDD"
    (credora, retificadora, 50,00), ambas `ativo_circulante`. As DUAS são
    "topo classificado" (nenhuma tem ancestral classificado), então as DUAS
    entram na soma — mas somar dois valores cada um já assinado pela
    PRÓPRIA natureza (em vez de aplicar UMA natureza sobre o bruto
    combinado, como a regra única de saldo exige) dá **1.220,00 + 50,00 =
    1.270,00**, quando o correto (o que `totais_por_tipo` calcula
    corretamente, via a raiz) é **1.170,00** — excesso de 100,00, o DOBRO
    da retificadora. É literalmente a aritmética que justificou o desenho
    (ver o comentário de `classificacao_ancestral_de`, em
    `apurar_balancete`) escapando pela MESMA porta que o comentário do
    código já nomeia: classificação "pode ser declarada em QUALQUER nível
    da árvore", inclusive em duas folhas irmãs.

    **A correção NÃO é mais uma lista — é uma IDENTIDADE ARITMÉTICA,
    devolvida em `residuo_por_tipo`:**

        residuo_por_tipo[tipo] = totais_por_tipo[tipo] − Σ(totais_por_classificacao
                                                             dos grupos daquele tipo)

    para cada `tipo` que PARTICIPA da separação (Ativo, Passivo — derivado
    de `TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()`, nunca uma lista
    `[ATIVO, PASSIVO]` escrita à mão). **Diferente das três listas, o
    resíduo NÃO depende de reconhecer a TOPOLOGIA do problema** — ele
    reprova qualquer descasamento entre os dois totais, seja por
    aninhamento, por folha esquecida, por contas irmãs com natureza
    diferente, ou por qualquer topologia que ninguém pensou ainda. É
    `0,00` no caso são (plano de contas totalmente classificado, sem
    aninhamento nem irmãs de natureza mista) e DIFERENTE de zero sempre
    que `totais_por_classificacao` não reflete fielmente o `totais_por_
    tipo` correspondente — nomeando o TAMANHO e o SINAL da divergência,
    nunca corrigindo nada (mesmo espírito de `equacao["diferenca"]`: "o
    que eu somei fecha, e quando não fecha eu digo, nunca conserto").
    **Isto fecha também o achado ALTO BL-487** (nó intermediário sem
    classificação própria, com movimento próprio, desdobrado de uma conta
    já em uso — `contas_sem_classificacao_patrimonial` só cobria FOLHAS, e
    um nó que ganha filha deixa de ser folha sem deixar de precisar de
    classificação; a DE-022 já registra que esse desdobramento é rotina
    normal, não erro).

    ⚠️ **BL-496 (RESSALVA R1 da rodada 2 de auditoria da DL-033, DE-068) —
    o resíduo garante o TOTAL POR TIPO, NUNCA o subtotal por GRUPO, e é o
    GRUPO que o Balanço imprime.** A rodada 2 mediu o cenário **V1d**: dois
    defeitos no MESMO Ativo, calibrados para se ANULAREM na soma agregada
    (retificadora entre irmãs, como acima, **e** um nó intermediário
    desclassificado com movimento próprio, como o BL-487) — resíduo
    `0,00`, as cinco listas vazias, equação fechando, **e dois grupos do
    Balanço errados**. A identidade continua VERDADEIRA (ela soma
    conjuntos de nós diferentes dos dois lados, não é tautologia); o que
    era falso era achar que "resíduo zero" bastava. Duas respostas,
    tomadas JUNTAS (DE-068: "enuncie a invariante E o escopo dela"):

    1. **A correção de FUNDO (opção (b) do auditor):** o laço acima soma
       cada nó topo classificado normalizando o sinal por
       `NATUREZA_NATURAL_DO_TIPO` (models.py), não pela natureza CADASTRADA
       da própria conta — torna o NÚMERO certo (ver o comentário no laço),
       não só detectado, para a topologia exata do BL-486/V1a.
    2. **Mas (b) não tem prova para TODA topologia** ("pode haver
       interação com retificadora DE GRUPO que eu não enxerguei" — palavras
       do próprio auditor). Por isso as condições 3 e 4 do critério 1 da
       DL-034 continuam vivas como GUARDA ESTRUTURAL, cinto e suspensório
       ao lado do resíduo:
       `contas_topo_classificadas_com_natureza_divergente_entre_irmas`
       (irmãos topo classificados com natureza cadastrada divergente — a
       topologia do BL-486) e
       `contas_nao_folha_sem_classificacao_com_movimento_proprio` (nó
       não-folha desclassificado com movimento próprio — a topologia do
       BL-487). **Nenhuma das duas é removida por (b) ter corrigido o
       número** — ver `avaliar_emissao_do_balanco`, que exige a CONJUNÇÃO
       de resíduo zero, as cinco listas antigas vazias e estas duas
       também vazias antes de liberar a emissão.

    ⚠️ **`totais_por_grupo` (BL-490, achado MÉDIO) — o subtotal que a lei
    manda IMPRIMIR no Balanço:** soma `totais_por_classificacao` pelos
    QUATRO grupos de `GrupoDaLei` (via `GRUPO_DA_LEI_DA_CLASSIFICACAO_
    PATRIMONIAL`, o SEGUNDO mapa derivado — nunca `classificacao.
    startswith("ativo")`, que nem distingue "Ativo Circulante" de "Ativo
    Não Circulante"): os quatro subgrupos do Ativo Não Circulante (art.
    178 §1º II) se somam num único "Ativo Não Circulante" aqui, que é o
    que o Balanço de fato imprime.

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
            # BL-481/achado A8: exatamente `nivel == 1` — repassado para
            # quem quiser reproduzir `totais_por_tipo` a partir de `contas`
            # sem contar cada descendente em dobro (ver docstring).
            "raiz": linha["raiz"],
            # DL-033/RC-106: classificação PRÓPRIA desta conta (ou `None`,
            # a maioria das contas — o produto nunca infere uma).
            "classificacao_patrimonial": linha["classificacao_patrimonial"],
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
    # BL-476/achado A1: tipo gravado fora de `TipoConta` (só alcançável por
    # dado corrompido — ver docstring) NUNCA cria chave dentro de
    # `totais_por_tipo` nem estoura `KeyError` — aparece, nomeado, aqui.
    contas_com_tipo_desconhecido = []
    # BL-475/achado A2: conta cujo `tipo` PRÓPRIO diverge do `tipo` da sua
    # RAIZ — o saldo dela já está (corretamente) consolidado no grupo da
    # raiz; isto só DECLARA a divergência, nunca corrige nada. Vazia no
    # caso são.
    contas_com_tipo_divergente_da_raiz = []
    for linha in balancete["contas"]:
        tipo = linha["tipo"]
        if tipo not in totais_por_tipo:
            contas_com_tipo_desconhecido.append(
                {"conta": linha["conta"], "nome": linha["nome"], "tipo": tipo}
            )
        elif linha["raiz"]:
            totais_por_tipo[tipo] += linha["saldo_final"]

        if tipo != linha["tipo_da_raiz"]:
            contas_com_tipo_divergente_da_raiz.append(
                {
                    "conta": linha["conta"],
                    "nome": linha["nome"],
                    "tipo": tipo,
                    "tipo_da_raiz": linha["tipo_da_raiz"],
                }
            )

    # DL-033 (RC-106), critério 1: os grupos circulante/não circulante
    # vêm de UMA fonte única no código — `ClassificacaoPatrimonial.values`,
    # lido do MODELO — nunca de uma tupla escrita à mão (mesmo padrão de
    # `totais_por_tipo` acima). Um grupo novo aparece aqui automaticamente,
    # com zero, em vez de ficar fora em silêncio.
    totais_por_classificacao = {
        classificacao: zero for classificacao in ClassificacaoPatrimonial.values
    }
    # Conta que tem classificação PRÓPRIA E TAMBÉM um ancestral já
    # classificado — dado inconsistente (duas contas da MESMA árvore
    # declarando o MESMO grupo). DECLARADA, nunca somada duas vezes: o
    # ancestral já consolida esta conta dentro do próprio `saldo_final`
    # dele (regra única de saldo, DE-020) — somar esta linha de novo
    # contaria o mesmo lançamento duas vezes. Vazia no caso são.
    contas_com_classificacao_aninhada = []
    # Mesma defesa do achado A1/BL-476 (`contas_com_tipo_desconhecido`),
    # agora para o campo NOVO desta etapa: um valor gravado fora de
    # `ClassificacaoPatrimonial` (só alcançável por ORM/SQL direto — a
    # tela e o serializer sempre validam `choices`, e a guarda de
    # consistência do `Conta.clean()` nem chega a rodar fora do caminho
    # validado) NUNCA estoura `KeyError` dentro de `totais_por_classificacao`
    # nem cria uma chave nova ali — aparece, nomeada, aqui.
    contas_com_classificacao_desconhecida = []
    # Conta de tipo ATIVO ou PASSIVO, ANALÍTICA (sem descendentes —
    # DE-022), COM SALDO (BL-493, achado A8: "a régua é o saldo, não a
    # marca de `ativo`" — mesmo princípio do BL-482/achado A9 da DL-032,
    # onde conta desativada com saldo residual continua somando: aqui, o
    # inverso — conta sem saldo nenhum não precisa de classificação,
    # esteja ela ativa ou não, porque classificá-la não muda NADA no
    # Balanço), cuja própria classificação E a de TODOS os ancestrais
    # estão vazias: nenhum lugar da árvore, do topo até esta folha,
    # declarou circulante ou não circulante. Critério 5 do plano DL-033:
    # DECLARADA, NUNCA presumida a partir do código ou do nome da conta —
    # a classe de erro do achado A2/BL-475 da DL-032. Vazia quando todas
    # as contas relevantes (com saldo) estão classificadas (controle
    # positivo do critério 5).
    #
    # ⚠️ BL-498 (achado BAIXO, "R3" da rodada 2 de auditoria da DL-033): a
    # régua desta lista (e da lista irmã abaixo) é o SALDO/MOVIMENTO em
    # `data_base` — não uma propriedade fixa da conta. Uma conta com
    # movimento no período cujo saldo volta a `0,00` exatamente em
    # `data_base` SAI da lista (classificá-la não mudaria o Balanço nesta
    # data), e pode voltar a aparecer numa `data_base` diferente para o
    # MESMO plano de contas. Aritmeticamente inofensivo (saldo zero
    # contribui zero à soma), mas quem consome esta lista não pode tratá-la
    # como "o que falta classificar no plano de contas" — é "o que falta
    # classificar NESTA DATA".
    contas_sem_classificacao_patrimonial = []
    # BL-487, critério 1 condição 4 da DL-034 (guarda ESTRUTURAL, "cinto e
    # suspensório" — ver a nota grande abaixo, depois do laço, sobre por
    # que ela continua viva mesmo com `residuo_por_tipo` cobrindo o mesmo
    # defeito): nó NÃO-FOLHA (tem descendente — o oposto exato da condição
    # acima, que só olha folha) cuja classificação própria E ancestral
    # estão vazias, mas que tem MOVIMENTO PRÓPRIO — `debitos_proprios_
    # totais`/`creditos_proprios_totais` (anterior + período, "alguma vez
    # até `fim`"), NUNCA `debitos_proprios`/`creditos_proprios` (só
    # período): como `apurar_saldos` sempre chama `apurar_balancete` com
    # `inicio=fim=data_base`, um lançamento antigo cai inteiro em
    # `saldo_anterior` — usar os campos só-período deixaria esta guarda
    # cega para o caso comum (conta com movimento próprio mais antigo que
    # `data_base`), pegando só quem tem movimento bem no dia de corte. O
    # desdobramento que a DE-022 já registra como ROTINA normal (conta
    # ganha filha) deixa esse valor invisível para a lista de folhas
    # acima, mesmo sem nenhum dado corrompido.
    contas_nao_folha_sem_classificacao_com_movimento_proprio = []
    # BL-496, critério 1 condição 3 da DL-034 — DECLARATIVA desde a DE-070
    # (deixou de VETAR a emissão; ver o comentário grande depois do laço, e
    # `avaliar_emissao_do_balanco`). Agrupa cada nó TOPO classificado
    # (classificação própria válida, nenhum ancestral também classificado)
    # por seu pai declarado e tipo, com a natureza CADASTRADA — para,
    # depois do laço, achar grupos com natureza divergente entre si. É a
    # topologia EXATA do BL-486 (ver a nota grande abaixo).
    #
    # ⚠️ **BL-499/BL-516 — chave de agrupamento `(conta_pai, tipo)`:**
    # agrupar só por `conta_pai` juntava raízes de tipos diferentes porque
    # todas têm pai `None`; a chave também inclui `tipo`, então Ativo e
    # Passivo nunca se cruzam. Raízes do mesmo tipo permanecem comparáveis:
    # se suas naturezas divergem, a lista informativa as nomeia (BL-516).
    # Os cenários L1 e L2 em `test_dl034_balanco_patrimonial.py` provam
    # que os planos de contas coerentes continuam emitindo. A lista é
    # aviso, não veto.
    topo_classificados_por_pai = defaultdict(list)
    for linha in balancete["contas"]:
        propria = linha["classificacao_patrimonial"]
        ancestral = linha["classificacao_patrimonial_ancestral"]
        if propria:
            if propria not in totais_por_classificacao:
                contas_com_classificacao_desconhecida.append(
                    {
                        "conta": linha["conta"],
                        "nome": linha["nome"],
                        "classificacao_patrimonial": propria,
                    }
                )
            elif ancestral:
                contas_com_classificacao_aninhada.append(
                    {
                        "conta": linha["conta"],
                        "nome": linha["nome"],
                        "classificacao_patrimonial": propria,
                        "classificacao_patrimonial_ancestral": ancestral,
                    }
                )
            else:
                # BL-496 (RESSALVA R1, opção (b), DE-068) — a CORREÇÃO DE
                # FUNDO desta etapa: soma o nó TOPO classificado
                # normalizando o sinal pela natureza NATURAL do TIPO da
                # classificação (`NATUREZA_NATURAL_DO_TIPO`, models.py —
                # devedora no Ativo, credora no Passivo), NUNCA pela
                # natureza CADASTRADA da própria conta
                # (`linha["natureza"]`). `linha["saldo_final"]` já vem
                # assinado relativo à natureza CADASTRADA (ver o
                # comentário de origem em `apurar_balancete`) — quando ela
                # coincide com a natural do tipo, o valor já está no sinal
                # certo; quando diverge (a conta é uma RETIFICADORA, ex.:
                # "(-) PDD" credora sob Ativo Circulante), o sinal precisa
                # inverter para que a soma do grupo aplique UMA natureza
                # sobre o valor combinado — exatamente a regra única de
                # saldo (DE-020) que já vale para hierarquia, agora
                # aplicada entre contas classificadas independentemente
                # no mesmo grupo, seja qual for sua posição na árvore.
                # Sem isto, "Clientes"
                # (D, 1.220,00) e "(-) PDD" (C, 50,00), ambas
                # `ativo_circulante`, somavam 1.220,00 + 50,00 = 1.270,00;
                # com a normalização, 1.220,00 − 50,00 = 1.170,00 —
                # correto, e igual ao que `totais_por_tipo` já calculava
                # via a raiz (prova: `test_bl486_...`, reescrito nesta
                # etapa).
                natureza_natural = NATUREZA_NATURAL_DO_TIPO[
                    TIPO_DA_CLASSIFICACAO_PATRIMONIAL[propria]
                ]
                valor_normalizado = (
                    linha["saldo_final"]
                    if linha["natureza"] == natureza_natural
                    else -linha["saldo_final"]
                )
                totais_por_classificacao[propria] += valor_normalizado
                # BL-516: mantenha também as raízes na chave. O `None`
                # comum só aproxima contas de mesmo tipo; naturezas
                # divergentes viram aviso nomeado, sem afirmar que há um
                # ancestral ou vetar a emissão.
                topo_classificados_por_pai[(linha["conta_pai"], linha["tipo"])].append(
                    {
                        "conta": linha["conta"],
                        "nome": linha["nome"],
                        "classificacao_patrimonial": propria,
                        "natureza": linha["natureza"],
                    }
                )
        elif ancestral is None and linha["tipo"] in (TipoConta.ATIVO, TipoConta.PASSIVO):
            if linha["analitica"]:
                if linha["saldo_final"] != zero:
                    contas_sem_classificacao_patrimonial.append(
                        {"conta": linha["conta"], "nome": linha["nome"], "tipo": linha["tipo"]}
                    )
            elif (
                linha["debitos_proprios_totais"] != zero
                or linha["creditos_proprios_totais"] != zero
            ):
                contas_nao_folha_sem_classificacao_com_movimento_proprio.append(
                    {"conta": linha["conta"], "nome": linha["nome"], "tipo": linha["tipo"]}
                )

    # ⚠️ Fecha a condição 3 do critério 1 (DL-034) — DECLARATIVA desde a
    # [DE-070](../../docs/projeto/decisoes.md#de-070), não mais VETO. Eu
    # (arquiteto) tinha mandado mantê-la como "cinto e suspensório" porque o
    # auditor que sugeriu a correção (b), acima, declarou o limite da
    # própria sugestão — "conferi só a aritmética à mão... pode haver
    # interação com retificadora DE GRUPO que eu não enxerguei" (RESSALVA
    # R1). A auditoria da DL-034 MEDIU essa interação e ela NÃO EXISTE: (b)
    # dá o número CERTO tanto para a retificadora de grupo quanto para a
    # topologia pura do BL-486 — o pressuposto que sustentava o suspensório
    # deixou de existir, e a condição 3, combinada com o defeito do BL-499
    # (agrupar TODA raiz como irmã, corrigido acima), passou a recusar
    # também planos de contas corretos, com mensagem factualmente falsa.
    #
    # A lista continua CALCULADA e DECLARADA — em `listas_informativas`,
    # NUNCA em `listas_pendentes` (`avaliar_emissao_do_balanco`; correção
    # de integração do arquiteto-senior: este comentário ficou apontando
    # para `listas_pendentes` depois da separação em duas tuplas, e chave
    # errada em comentário vira código errado na próxima leitura) — contas
    # topo-classificadas com o mesmo valor de `conta_pai` (inclusive `None`
    # para raízes) e mesmo `TipoConta`, com natureza CADASTRADA divergente
    # entre si (BL-486/BL-516), continuam sendo um AVISO útil ao contador
    # sobre o plano de contas — só deixaram de BLOQUEAR a emissão. Quem
    # continua vetando: o resíduo (condição 1) e a condição 4 (cobertura).
    contas_topo_classificadas_com_natureza_divergente_entre_irmas = []
    for irmaos in topo_classificados_por_pai.values():
        naturezas_dos_irmaos = {irmao["natureza"] for irmao in irmaos}
        if len(naturezas_dos_irmaos) > 1:
            contas_topo_classificadas_com_natureza_divergente_entre_irmas.extend(irmaos)

    # BL-490 (achado MÉDIO): o subtotal que a Lei 6.404/76 art. 178 manda
    # IMPRIMIR no Balanço — os QUATRO grupos de `GrupoDaLei`, nunca sete —
    # somado pelo SEGUNDO mapa derivado (`GRUPO_DA_LEI_DA_CLASSIFICACAO_
    # PATRIMONIAL`), nunca por `classificacao.startswith("ativo")` (que
    # nem distingue Ativo Circulante de Ativo Não Circulante).
    totais_por_grupo = {grupo: zero for grupo in GrupoDaLei.values}
    for classificacao, valor in totais_por_classificacao.items():
        totais_por_grupo[GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]] += valor

    # BL-486 (BLOQUEADOR, corrigido): a IDENTIDADE ARITMÉTICA que garante o
    # critério 4 — não mais um catálogo de casos que alguém pensou. Só
    # calculada para os `TipoConta` que PARTICIPAM da separação (Ativo,
    # Passivo), derivado de `TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()`
    # (nunca uma lista `[ATIVO, PASSIVO]` escrita à mão): Patrimônio
    # Líquido, Receita e Despesa nunca têm classificação (RC-106), então a
    # pergunta "quanto falta classificar" não se aplica a eles — incluí-los
    # aqui devolveria o saldo inteiro deles como "resíduo" sempre, o que
    # não é discrepância nenhuma, é ausência de sentido da pergunta.
    tipos_com_classificacao = set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values())
    residuo_por_tipo = {
        tipo: totais_por_tipo[tipo]
        - sum(
            (
                valor
                for classificacao, valor in totais_por_classificacao.items()
                if TIPO_DA_CLASSIFICACAO_PATRIMONIAL[classificacao] == tipo
            ),
            zero,
        )
        for tipo in tipos_com_classificacao
    }

    ativo = totais_por_tipo[TipoConta.ATIVO]
    passivo = totais_por_tipo[TipoConta.PASSIVO]
    patrimonio_liquido = totais_por_tipo[TipoConta.PATRIMONIO_LIQUIDO]
    receita = totais_por_tipo[TipoConta.RECEITA]
    despesa = totais_por_tipo[TipoConta.DESPESA]
    # BL-478/achado A4: renomeado de `resultado_do_periodo` — o nome antigo
    # afirmava ser o resultado do PERÍODO; é o SALDO ainda não transferido
    # ao PL, que o zeramento leva a zero mesmo num mês lucrativo (ver
    # docstring, "esta camada NÃO serve para apurar a DRE").
    resultado_nao_transferido = receita - despesa

    # O momento da verdade: a diferença é CALCULADA e DEVOLVIDA — nunca usada
    # para ajustar saldo nenhum, aqui ou em quem chama (critério 2).
    diferenca = ativo - (passivo + patrimonio_liquido + resultado_nao_transferido)

    return {
        "data_base": data_base,
        "contas": contas,
        "totais_por_tipo": totais_por_tipo,
        "contas_com_tipo_desconhecido": contas_com_tipo_desconhecido,
        "contas_com_tipo_divergente_da_raiz": contas_com_tipo_divergente_da_raiz,
        # DL-033/RC-106 — circulante × não circulante do Balanço
        # Patrimonial (fatia 1): ver os comentários acima, no bloco que os
        # monta.
        "totais_por_classificacao": totais_por_classificacao,
        # BL-490: subtotal pelos QUATRO grupos que a lei manda imprimir.
        "totais_por_grupo": totais_por_grupo,
        # BL-486: a identidade aritmética que GARANTE o critério 4 —
        # `Σ(totais_por_classificacao do tipo) + residuo_por_tipo[tipo] ==
        # totais_por_tipo[tipo]`, sempre, por construção. `0,00` no caso
        # são; diferente de zero nomeia o tamanho e o sinal de qualquer
        # descasamento, qualquer que seja a topologia que o causou.
        "residuo_por_tipo": residuo_por_tipo,
        "contas_com_classificacao_aninhada": contas_com_classificacao_aninhada,
        "contas_com_classificacao_desconhecida": contas_com_classificacao_desconhecida,
        "contas_sem_classificacao_patrimonial": contas_sem_classificacao_patrimonial,
        # DL-034, critério 1, condição 3 (BL-496) — DECLARATIVA, não veto
        # desde a DE-070 (ver o comentário grande acima, antes desta
        # variável ser fechada). Vazia no caso são; nomeia contas
        # topo-classificadas com o mesmo valor de pai (inclui None para
        # raízes) e mesmo `TipoConta` quando duas ou mais têm natureza
        # cadastrada divergente entre si (BL-486/BL-516).
        "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
            contas_topo_classificadas_com_natureza_divergente_entre_irmas
        ),
        # DL-034, critério 1, condição 4 — guarda ESTRUTURAL (BL-487): vazia
        # no caso são; nomeia nó NÃO-FOLHA sem classificação própria nem
        # ancestral que tem movimento PRÓPRIO (não só consolidado).
        "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
            contas_nao_folha_sem_classificacao_com_movimento_proprio
        ),
        "equacao": {
            "ativo": ativo,
            "passivo": passivo,
            "patrimonio_liquido": patrimonio_liquido,
            "receita": receita,
            "despesa": despesa,
            "resultado_nao_transferido": resultado_nao_transferido,
            "diferenca": diferenca,
        },
    }


# ⚠️ Correção de CONTRATO pedida pelo arquiteto-senior na rodada de
# correção da DL-034 (depois de eu ter devolvido, na primeira versão desta
# correção, uma ÚNICA tupla com as sete listas e deixado a separação
# veto/aviso só DENTRO de `avaliar_emissao_do_balanco`): um nome chamado
# "pendência" cujo conteúdo pode não impedir NADA mente para quem lê o
# código. A partir de agora são DUAS tuplas, nunca uma só — cada lista de
# `apurar_saldos` pertence a EXATAMENTE uma das duas, nunca as duas, nunca
# nenhuma (as três asserções do teste `test_bl502_...` no arquivo de
# testes provam isto: união == inventário real, interseção vazia).
#
# 1) as que IMPEDEM a emissão (VETO) — a condição 2 (as cinco herdadas dos
#    achados A1/A2 da DL-032 e BL-493 da DL-033) mais a condição 4 (BL-487,
#    cobertura). A condição 1 (resíduo) é tratada à parte por ser um dict
#    de Decimal, não uma lista.
_LISTAS_QUE_IMPEDEM_A_EMISSAO = (
    "contas_com_tipo_desconhecido",
    "contas_com_tipo_divergente_da_raiz",
    "contas_com_classificacao_aninhada",
    "contas_com_classificacao_desconhecida",
    "contas_sem_classificacao_patrimonial",
    "contas_nao_folha_sem_classificacao_com_movimento_proprio",
)

# 2) a ÚNICA que só AVISA — a condição 3 (BL-496), aposentada como veto
# pela [DE-070](../../docs/projeto/decisoes.md#de-070): a auditoria da
# DL-034 mediu que a correção (b) dá o número CERTO também para
# retificadora DE GRUPO (o pressuposto que sustentava o veto deixou de
# existir) e que, sem essa prova, a condição bloqueava planos de contas
# CORRETOS (BL-499 — agrupar só por pai cruzava raízes de tipos diferentes).
# Continua CALCULADA por `apurar_saldos`, com a chave `(conta_pai, tipo)`
# que também nomeia raízes do mesmo tipo com natureza divergente (BL-516),
# e DECLARADA — só não impede mais nada, e por isso não entra na tupla acima.
_LISTAS_QUE_SO_AVISAM = ("contas_topo_classificadas_com_natureza_divergente_entre_irmas",)


def avaliar_emissao_do_balanco(saldos):
    """ "O que eu vou entregar fecha, e eu sei o que ele NÃO diz" — DL-034,
    critério 1: decide, no SERVIDOR (nunca só na tela), se o Balanço
    Patrimonial PODE ser emitido a partir do resultado de `apurar_saldos`,
    e — quando não pode — NOMEIA o que falta, para a tela mostrar o
    caminho, nunca só recusar em silêncio.

    A condição de VETO é a CONJUNÇÃO de três exigências — nenhuma sozinha é
    suficiente (DE-068, a lição da RESSALVA R1/cenário V1d: "resíduo zero"
    sozinho JÁ produziu, na auditoria, um Balanço com dois grupos errados
    em R$ 500,00 cada, com as cinco listas antigas vazias e a equação
    fechando):

    1. `residuo_por_tipo` é ZERO em todos os tipos que participam da
       separação (Ativo, Passivo).
    2. as CINCO listas de declaração herdadas de `apurar_saldos`
       (`contas_com_tipo_desconhecido`, `contas_com_tipo_divergente_da_
       raiz`, `contas_com_classificacao_aninhada`, `contas_com_
       classificacao_desconhecida`, `contas_sem_classificacao_
       patrimonial`) estão vazias.
    3. NENHUM nó não-folha sem classificação própria nem ancestral tem
       movimento próprio
       (`contas_nao_folha_sem_classificacao_com_movimento_proprio` vazia
       — BL-487).

    ⚠️ **A condição de natureza cadastrada divergente entre contas
    topo-classificadas (`contas_topo_classificadas_com_natureza_divergente_
    entre_irmas` — BL-496) NÃO veta mais, desde a
    [DE-070](../../docs/projeto/decisoes.md#de-070).** Ela continua
    CALCULADA por `apurar_saldos`, com agrupamento `(conta_pai, tipo)`:
    raízes de tipos diferentes não se cruzam (BL-499), e raízes do mesmo
    tipo com natureza divergente continuam nomeadas (BL-516). O resultado
    é devolvido SEPARADO, em `listas_informativas` — nunca misturado com
    `listas_pendentes`, que só contém o que IMPEDE (ver "Retorna", abaixo).
    Eu (arquiteto) tinha mandado mantê-la como veto ("cinto e suspensório")
    enquanto a correção (b) não tivesse prova para retificadora DE GRUPO;
    a auditoria da DL-034 mediu essa prova e ela é CERTA — o suspensório
    deixou de ter pressuposto.

    ⚠️ **DERIVADA, nunca uma lista de `if` escrita à mão (DE-056 — o
    projeto já pagou caro por enumeração), com DUAS tuplas EXPLÍCITAS, não
    um inventário só com exceção embutida:** `_LISTAS_QUE_IMPEDEM_A_
    EMISSAO` (seis nomes) decide `pode_emitir`; `_LISTAS_QUE_SO_AVISAM` (um
    nome) nunca decide nada. O teste do BL-502
    (`test_bl502_as_duas_tuplas_particionam_o_inventario_real_de_apurar_saldos`)
    prova apenas a forma da partição. O teste parametrizado
    `test_bl515_cada_lista_que_veta_sozinha_continua_impedindo` percorre
    cada nome da tupla, com resíduo zero e só aquela lista não vazia, e
    exige recusa. Uma lista nova que `apurar_saldos` ganhar no futuro só
    participa desta função se entrar em UMA das duas tuplas.

    Não verifica autorização nem papel nenhum — mesmo limite que
    `apurar_saldos` já declara: esta função continua sem saber o que é uma
    requisição HTTP. Quem chama (a view) verifica permissão ANTES de
    chamar esta função.

    Retorna:
        {"pode_emitir": bool,
         "residuo_pendente": {TipoConta: Decimal, ...},        # só os != 0
         "listas_pendentes": {"nome_da_lista": [...], ...},    # só as que
                                                                # IMPEDEM,
                                                                # não vazias
         "listas_informativas": {"nome_da_lista": [...], ...}} # só as que
                                                                # AVISAM,
                                                                # não vazias
                                                                # — NUNCA
                                                                # impedem

    `residuo_pendente`, `listas_pendentes` e `listas_informativas` vêm
    VAZIOS (`{}`) no caso são — quem consome não precisa checar
    `pode_emitir` antes de iterá-los. ⚠️ `listas_pendentes` nunca contém
    uma lista de `listas_informativas`, e vice-versa (são as duas tuplas
    acima, disjuntas por construção).
    """
    zero = Decimal("0")
    residuo_pendente = {
        tipo: valor for tipo, valor in saldos["residuo_por_tipo"].items() if valor != zero
    }
    # Só o que IMPEDE decide `pode_emitir` — nenhum `if` por condição, a
    # mesma derivação que a DL-034 já tinha (V3 da auditoria).
    listas_pendentes = {
        nome: saldos[nome] for nome in _LISTAS_QUE_IMPEDEM_A_EMISSAO if saldos[nome]
    }
    # A que só avisa (DE-070) vem SEPARADA — nunca contamina a decisão
    # nem a mensagem de "o que impede".
    listas_informativas = {nome: saldos[nome] for nome in _LISTAS_QUE_SO_AVISAM if saldos[nome]}
    return {
        "pode_emitir": not residuo_pendente and not listas_pendentes,
        "residuo_pendente": residuo_pendente,
        "listas_pendentes": listas_pendentes,
        "listas_informativas": listas_informativas,
    }


def identificacao_da_demonstracao():
    """DL-034 — NBC TG 26 (R5), item 51, alíneas (b), (d) e (e) (RC-95):
    três campos do bloco de identificação OBRIGATÓRIO do Balanço que NÃO
    EXISTEM hoje no produto. São "da entidade e da emissão" (o plano da
    DL-034), mas NENHUM dos três VARIA por empresa nem por emissão no
    DataLedger de hoje — por isso entram como CONSTANTE declarada, nunca
    como campo de `Empresa` deduzido ou perguntado ao usuário: inventar uma
    escolha que o produto não oferece seria pior do que declarar, com
    fonte, o único valor que o produto de fato produz hoje (a instrução do
    plano: "declarar não é adivinhar").

    - **(b) individual ou de grupo:** o DataLedger **não consolida**
      (nenhuma tela, nenhum serviço soma o Balanço de duas empresas) —
      "individual" é a única resposta possível hoje.
    - **(d) moeda de apresentação:** a NBC ITG 2000 (R1), item 5(d)
      (RC-96), exige escrituração em moeda NACIONAL — não há escolha a
      fazer.
    - **(e) nível de arredondamento:** a política monetária do produto
      inteiro já é "unidade de real, com centavos" (DE-010) — declarar
      isso no documento É o cumprimento da alínea (e), sem campo novo
      nem migração.

    Função (não consulta banco, não faz parte de `apurar_saldos`) para que
    a view/template chame em QUALQUER página do documento impresso —
    critério 4 do plano, o bloco de identificação se repete em toda
    página (NBC TG 26, item 52) — sem custo de consulta nenhuma.

    Reversível pelo Fred a qualquer momento: se o produto vier a oferecer
    consolidação, moeda estrangeira ou arredondamento em milhares, estes
    três valores passam a ser CAMPO (de `Empresa` ou da emissão), não mais
    constante — decisão que este limite deixa explícita, não escondida.
    """
    return {
        "entidade_individual_ou_grupo": "individual",
        "moeda_de_apresentacao": "Real (R$)",
        "nivel_de_arredondamento": "unidade de real, com centavos",
    }


def rotulo_e_inscricao_da_empresa(empresa):
    """DL-038 (etapa 2, critério 7) — PONTO ÚNICO de formatação da
    inscrição da empresa para o cabeçalho de identificação de um
    documento impresso desta app.

    Devolve `(rotulo, inscricao_formatada)`:
      - `("CNPJ", "XX.XXX.XXX/XXXX-XX")` para empresa pessoa jurídica;
      - `("CPF", "XXX.XXX.XXX-XX")` para empresa pessoa física (RC-112).

    Antes desta etapa, o único documento que imprimia a inscrição da
    empresa (o Balanço — `_cnpj_mascarado`, `apps/contabilidade/
    views_web.py`) assumia sempre CNPJ: uma empresa CPF em modo
    contabilidade (permitida pelo modelo — nada no R4 proíbe CPF +
    contabilidade, só CPF costuma SUGERIR livro-caixa, HI-23) sairia com
    a inscrição EM BRANCO no papel, porque `empresa.cnpj` é vazio por
    invariante de banco para empresa CPF (`empresa_inscricao_
    consistente_com_tipo`, apps/empresas/models.py). Esta função é o
    lugar ÚNICO que decide qual dos dois campos ler e como mascarar cada
    um — nenhum template repete o `if tipo_inscricao == CPF` (mesmo
    requisito de R7/critério 7 já aplicado à listagem de empresas,
    `apps.empresas.views.lista_empresas`).

    Reescreve, de propósito, a MESMA regra de máscara de
    `apps.empresas.views._mascara_cnpj`/`_mascara_cpf` (não importa os
    símbolos privados de outro app — mesma decisão consciente já
    declarada na docstring de `_cnpj_mascarado`, que esta função
    substitui). Puramente apresentação: devolve o valor original quando
    o tamanho não bate com o esperado (dado herdado ou corrompido), em
    vez de mascarar errado — nunca levanta exceção, porque não é validação.
    """
    if empresa.tipo_inscricao == TipoInscricao.CPF:
        cpf = empresa.cpf
        if len(cpf) != 11:
            return "CPF", cpf
        return "CPF", f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"
    cnpj = empresa.cnpj
    if len(cnpj) != 14:
        return "CNPJ", cnpj
    return "CNPJ", f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def apurar_balanco_patrimonial(*, empresa, data_base):
    """Monta os TRÊS ingredientes que a tela do Balanço Patrimonial
    consome (DL-034) num único ponto de entrada: os saldos classificados
    (`apurar_saldos`), a decisão de emissão (`avaliar_emissao_do_balanco`)
    e a identificação obrigatória do item 51 que não depende de dado
    nenhum (`identificacao_da_demonstracao`).

    Retorna `{"saldos": <dict de apurar_saldos>, "emissao": <dict de
    avaliar_emissao_do_balanco>, "identificacao": <dict de
    identificacao_da_demonstracao>}`.

    ⚠️ **DE-067 — a leitura roda sob SNAPSHOT, aqui e SÓ aqui.** A
    auditoria da DL-032 (achado A6) mediu que `apurar_balancete`/
    `apurar_saldos` fazem TRÊS consultas fora de transação, sob `READ
    COMMITTED`: uma escrita concorrente entre elas pode produzir uma
    diferença TRANSITÓRIA na equação — sem nenhum desbalanço real gravado
    na base, mas indistinguível de erro real para quem lê. A DE-067
    decidiu ADIAR o custo do isolamento até existir uma superfície que
    gera DOCUMENTO IMPRIMÍVEL — esta função é essa superfície, e paga a
    dívida: `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` roda como a
    PRIMEIRA instrução desta transação (exigência do PostgreSQL — em
    qualquer outra posição da transação, o comando levanta erro). A partir
    dela, TODAS as consultas de `apurar_saldos`/`apurar_balancete` dentro
    deste `with` enxergam o MESMO snapshot do banco, tirado neste
    instante: nenhuma escrita concorrente entre a primeira e a última
    consulta pode mais produzir a diferença fantasma (prova de corrida:
    `test_dl034_snapshot_do_balanco.py`).

    `apurar_saldos`/`apurar_balancete` continuam sob `READ COMMITTED`
    quando chamadas DIRETO (ex.: a API ad hoc que a DL-032 já expõe) — só
    o caminho que GERA o Balanço paga o custo do isolamento elevado, como
    a DE-067 manda; NENHUM comportamento do Balancete do produto muda.

    Só leitura: nenhuma escrita acontece dentro deste `with`, então
    `REPEATABLE READ` nunca produz "could not serialize access due to
    concurrent update" aqui (erro exclusivo de CONFLITO escrita-escrita,
    inexistente numa transação 100% de leitura) — não precisa de
    `try/except` de serialização nem de `retry`.

    ⚠️ **Precondição — degrada em vez de derrubar a página:** `SET
    TRANSACTION ISOLATION LEVEL` só é válido como a PRIMEIRA instrução
    depois do `BEGIN`. No caminho normal de produção (`ATOMIC_REQUESTS`
    desligado de propósito — `config/settings.py` —, e nenhuma view abre
    `atomic()` antes de chamar esta função), esta função abre a PRÓPRIA
    transação de nível superior e recebe o `REPEATABLE READ` inteiro,
    como descrito acima. **Se for chamada de dentro de um
    `transaction.atomic()` JÁ aberto** — o caso do cliente de teste do
    Django, que embrulha toda a requisição simulada num `atomic()` para
    poder desfazer no fim (`@pytest.mark.django_db` padrão, sem
    `transaction=True`) — o `with transaction.atomic()` abaixo vira uma
    SAVEPOINT, e `SET TRANSACTION ISOLATION LEVEL` no meio de uma
    transação em andamento levantaria erro do PostgreSQL. Em vez de deixar
    a página quebrar por causa de como o AMBIENTE embrulhou a chamada
    (nunca por decisão desta função), o comando é SIMPLESMENTE PULADO
    nesse caso — a leitura roda sob o isolamento que a transação externa
    já tiver (o padrão do Postgres, `READ COMMITTED`, na prática de hoje),
    sem a garantia extra do snapshot único. **Isto é honesto, não
    silencioso:** o dado não some nem mente — só a garantia de corrida
    fica mais fraca nesse caminho aninhado específico, que hoje só existe
    em teste, nunca em produção (medido: nenhuma view do projeto abre
    `atomic()` antes de chamar esta função).

    Não verifica autorização nem papel — mesmo limite que `apurar_saldos`
    já declara; quem chama (a view) verifica permissão ANTES de chamar
    esta função.
    """
    ja_estava_em_transacao = connection.in_atomic_block
    with transaction.atomic():
        if not ja_estava_em_transacao:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        saldos = apurar_saldos(empresa=empresa, data_base=data_base)

    return {
        "saldos": saldos,
        "emissao": avaliar_emissao_do_balanco(saldos),
        "identificacao": identificacao_da_demonstracao(),
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
