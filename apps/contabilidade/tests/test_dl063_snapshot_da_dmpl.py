"""BL-607 — o par de CORRIDA da DMPL: a apuração lê sob snapshot
`REPEATABLE READ` (DE-067) e nada no projeto MEDIA que isso proteja.

`apurar_dmpl` faz três leituras de instantes diferentes da mesma apuração: a
que lista as contas (o `Conta.objects.filter` que monta `contas`), a que lê o
movimento do exercício (`_itens_dos_lancamentos_do_exercicio_que_tocam`) e a
que concilia com o Balanço (`apurar_saldos`). Sem `REPEATABLE READ`, uma escrita
concorrente que commitar ENTRE elas entra pela metade no documento: a parte
que passou pelas contas já carregadas entra, a parte que passou por uma conta
que nasceu depois da pausa não. A apuração da DRE (`test_dl045_dre.py`, par A5)
e a do Balanço (`test_dl034_balanco_patrimonial.py`, par DE-067) têm o par
"sem o wrapper / com o wrapper" que mede essa corrida com DUAS conexões de
verdade; a DMPL não tinha — e a DLPA também não tem, então a lacuna é MAIOR
do que a descrição do backlog.

Este arquivo é o par que faltava, no MESMO desenho dos outros dois (as
funções auxiliares e as constantes vêm do cenário da DL-061; nada aqui é
cenário reescrito). Nada de produção muda: o snapshot JÁ existe. O que
faltava era a MEDIÇÃO — e uma proteção de leitura que ninguém mede é uma
proteção que ninguém sabe dizer se ainda protege.

⚠️ **ESTE ARQUIVO SÓ EXECUTA NO PostgreSQL.** O par depende do `SET
TRANSACTION ISOLATION LEVEL REPEATABLE READ`, que o SQLite não tem: nele a
falha é `sqlite3.OperationalError: near "SET": syntax error` — limite do
ambiente, não defeito do teste (AGENTS.md §7: teste não executado é
pendente, com motivo). A evidência é a integração contínua, em PostgreSQL 16.
"""

import calendar
import threading
from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection

from apps.contabilidade import services as contabilidade_services
from apps.contabilidade.models import (
    ClassificacaoDlpa,
    Conta,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import apurar_dmpl, avaliar_emissao_da_dmpl, criar_lancamento

# O cenário (caso A, helpers e constantes) é IMPORTADO do arquivo da DL-061, não
# reescrito: o par tem de medir a apuração real, sobre o plano de contas que a
# suíte da DMPL já provou, e não uma cópia que pode divergir dele.
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    MES,
    PL,
    C,
    _caso_a,
    _conta,
)

# Colunas derivadas do enum, nunca escritas à mão: o valor gravado é a chave do
# documento (`apurar_dmpl` monta as colunas a partir de `ClassificacaoDmpl.values`).
COLUNA_CAPITAL = COL.CAPITAL_SOCIAL.value
COLUNA_RESERVA_LEGAL = COL.RESERVA_LEGAL.value
COLUNA_RESERVA_A_REALIZAR = COL.RESERVA_DE_LUCROS_A_REALIZAR.value
COLUNA_LUCROS = COL.LUCROS_OU_PREJUIZOS_ACUMULADOS.value

# A escrita concorrente: transferência de 500,00 da reserva legal para uma
# reserva de lucros a REALIZAR que ainda não existe quando a leitura listou as
# contas. É um evento real de escrituração (reserva de expansão, art. 193) e
# não uma operação montada para o teste: o que o torna venenoso para a leitura
# sem snapshot é o NASCIMENTO da conta, não o valor.
CONTA_DA_ESCRITA = "3.9"
DATA_DA_ESCRITA = date(ANO, MES, 20)
VALOR_DA_ESCRITA = Decimal("500.00")


def _apurar_dmpl_sem_snapshot(*, empresa, ano, mes):
    """Réplica MÍNIMA do corpo de `apurar_dmpl`, SEM o wrapper de snapshot.

    Chama as MESMAS funções internas, na MESMA ordem — `_colunas_de_cada_conta`
    logo depois da consulta que lista as contas (é ali que a pausa entra),
    `_saldo_anterior_por_conta`, `_itens_dos_lancamentos_do_exercicio_que_tocam`,
    `_atribuir_lancamento_as_linhas_da_dmpl` e a conciliação com `apurar_saldos` —
    e apenas omite a transação e o `SET TRANSACTION ISOLATION LEVEL`. É o mesmo
    desenho de `_apurar_dre_sem_snapshot` (`test_dl045_dre.py`): chamar
    `apurar_dmpl` (a função pública) testaria SEMPRE a versão protegida, então o
    "antes" da correção precisa da réplica.

    Devolve só o que a prova mede: as colunas, o movimento, o saldo final e a
    conciliação (por coluna e total) — as pendências e as linhas de evento não
    entram, porque o defeito que este arquivo mede é um NÚMERO, não uma
    pendência.
    """
    ultimo_dia_do_mes = calendar.monthrange(ano, mes)[1]
    data_inicio = date(ano, 1, 1)
    data_fim = date(ano, mes, ultimo_dia_do_mes)
    zero = Decimal("0")

    contas = {conta.id: conta for conta in Conta.objects.filter(empresa=empresa)}
    coluna_de, contas_da_coluna, _desconhecidas = contabilidade_services._colunas_de_cada_conta(
        contas
    )
    colunas_chaves = [coluna for coluna in COL.values if coluna in contas_da_coluna]

    saldo_anterior = contabilidade_services._saldo_anterior_por_conta(
        empresa=empresa, conta_ids=list(coluna_de), data_inicio=data_inicio
    )
    saldo_inicial = {
        coluna: sum((saldo_anterior.get(c.id, zero) for c in contas_da_coluna[coluna]), zero)
        for coluna in colunas_chaves
    }

    # A SEGUNDA leitura — a que o snapshot precisa proteger: ela roda depois da
    # pausa, então é ela que enxerga o lançamento concorrente.
    itens = contabilidade_services._itens_dos_lancamentos_do_exercicio_que_tocam(
        empresa=empresa, conta_ids=list(coluna_de), data_inicio=data_inicio, data_fim=data_fim
    )
    itens_por_lancamento = defaultdict(list)
    for item in itens:
        itens_por_lancamento[item.lancamento_id].append(item)
    ids_de_estorno = set(
        LancamentoContabil.objects.filter(
            empresa=empresa, id__in=list(itens_por_lancamento), estorno_de__isnull=False
        ).values_list("id", flat=True)
    )

    movimento = {coluna: zero for coluna in colunas_chaves}
    for lancamento_id, itens_do_lancamento in itens_por_lancamento.items():
        _celulas, movimento_do_lancamento, _problemas = (
            contabilidade_services._atribuir_lancamento_as_linhas_da_dmpl(
                itens=itens_do_lancamento,
                coluna_de=coluna_de,
                contas=contas,
                e_estorno=lancamento_id in ids_de_estorno,
            )
        )
        for coluna, valor in movimento_do_lancamento.items():
            movimento[coluna] = movimento.get(coluna, zero) + valor
    saldo_final = {coluna: saldo_inicial[coluna] + movimento[coluna] for coluna in colunas_chaves}

    # A TERCEIRA leitura, a conciliação (E5): caminho independente do número da
    # DMPL, o `saldo` que `apurar_saldos` apura em `data_fim`. Ela enxerga o
    # lançamento concorrente INTEIRO — é por isso que a metade que a DMPL não viu
    # aparece aqui como diferença.
    saldos = contabilidade_services.apurar_saldos(empresa=empresa, data_base=data_fim)
    linhas_do_balanco = {linha["conta"]: linha for linha in saldos["contas"]}

    def _contribuicao_no_balanco(conta):
        linha = linhas_do_balanco.get(conta.codigo)
        if linha is None:
            return None
        if linha["natureza"] != NaturezaConta.CREDORA:
            return -linha["saldo"]
        return linha["saldo"]

    por_coluna = {}
    divergencias = []
    for coluna in colunas_chaves:
        saldo_no_balanco = zero
        for conta in contas_da_coluna[coluna]:
            contribuicao = _contribuicao_no_balanco(conta)
            if contribuicao is not None:
                saldo_no_balanco += contribuicao
        diferenca = saldo_final[coluna] - saldo_no_balanco
        por_coluna[coluna] = {
            "saldo_na_dmpl": saldo_final[coluna],
            "saldo_no_balanco": saldo_no_balanco,
            "diferenca": diferenca,
        }
        if diferenca != zero:
            divergencias.append(coluna)

    total_da_dmpl = sum(saldo_final.values(), zero)
    saldo_de_passagem = zero
    for conta in contas.values():
        if conta.classificacao_dlpa == ClassificacaoDlpa.RESULTADO_DO_EXERCICIO:
            contribuicao = _contribuicao_no_balanco(conta)
            if contribuicao is not None:
                saldo_de_passagem += contribuicao
    pl_do_balanco = saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO]
    diferenca_total = total_da_dmpl + saldo_de_passagem - pl_do_balanco
    if diferenca_total != zero:
        divergencias.append("total")

    return {
        "colunas": colunas_chaves,
        "movimento": movimento,
        "saldo_final": {"valores": saldo_final, "total": total_da_dmpl},
        "conciliacao": {
            "por_coluna": por_coluna,
            "total": {
                "saldo_na_dmpl": total_da_dmpl,
                "saldo_contas_de_passagem": saldo_de_passagem,
                "saldo_no_balanco": pl_do_balanco,
                "diferenca": diferenca_total,
            },
        },
        "divergencias": divergencias,
    }


def _cenario_da_corrida():
    """Caso A do plano da DL-061 (capital 100.000,00, lucro 25.000,00, reserva
    legal 1.250,00, dividendos 10.000,00, com o zeramento de verdade): três
    colunas (capital, reserva legal, lucros acumulados), total 115.000,00, e
    uma conciliação que FECHA — o número honesto contra o qual o fantasma é
    medido."""
    empresa, contas, _gestor = _caso_a()
    return empresa, contas


def _escrever_reserva_nova(*, empresa, contas):
    """A escrita concorrente, a MESMA nos dois testes do par: nasce a conta
    "3.9 Reserva de Lucros a Realizar" (classificada nas DUAS demonstrações,
    como manda o par-exato da consistência DLPA × DMPL) e um lançamento que
    tira 500,00 da reserva legal e põe 500,00 nela.

    Metade visível: o DÉBITO na reserva legal, conta JÁ carregada quando a
    leitura listou o plano de contas. Metade invisível: o CRÉDITO na conta que
    ainda não existia. A classificação da conta nova é o que torna a meia
    leitura DIAGNOSTICÁVEL: se ela nascesse SEM coluna, a DMPL a trataria como
    "conta de PL sem coluna" e a leitura corrida cairia por acidente no mesmo
    número da leitura limpa — e o teste não provaria nada."""
    reserva_nova = _conta(
        empresa,
        CONTA_DA_ESCRITA,
        "Reserva de Lucros a Realizar",
        PL,
        C,
        dmpl=COL.RESERVA_DE_LUCROS_A_REALIZAR,
        dlpa=ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR,
        pai=contas["pl"],
    )
    criar_lancamento(
        empresa=empresa,
        data=DATA_DA_ESCRITA,
        historico="Escrita concorrente: transferência para reserva de lucros a realizar",
        itens=[
            {
                "conta": contas["reserva_legal"],
                "tipo": TipoPartida.DEBITO,
                "valor": VALOR_DA_ESCRITA,
            },
            {"conta": reserva_nova, "tipo": TipoPartida.CREDITO, "valor": VALOR_DA_ESCRITA},
        ],
    )
    return reserva_nova


def _pausa_apos_listar_as_contas(monkeypatch):
    """Troca `_colunas_de_cada_conta` por uma versão que pausa DEPOIS de fazer o
    que a original faz. A pausa é o intervalo exato da janela: a consulta que
    listou as contas já rodou (o snapshot, se houver um, já foi tirado) e a
    consulta do movimento ainda não. Devolve a original, para o teste devolver o
    monkeypatch antes da releitura limpa."""
    liberar_escrita = threading.Event()
    escrita_commitou = threading.Event()
    original = contabilidade_services._colunas_de_cada_conta

    def pausa_apos_carregar_contas(contas):
        resultado = original(contas)
        liberar_escrita.set()
        assert escrita_commitou.wait(timeout=5), "a escrita concorrente não commitou a tempo"
        return resultado

    monkeypatch.setattr(
        contabilidade_services, "_colunas_de_cada_conta", pausa_apos_carregar_contas
    )
    return original, liberar_escrita, escrita_commitou


def _dispara_a_corrida(ler, escrever, liberar_escrita, escrita_commitou):
    """Duas threads, DUAS conexões de verdade (o `django_db` padrão do
    pytest-django embrulha o teste inteiro num `transaction.atomic()` invisível
    para a outra conexão — daí o `transaction=True` na marcação de cada teste).

    Toda espera tem `timeout` e toda thread é verificada como CONCLUÍDA: sem
    isso, uma falha dentro da thread vira um `resultado` vazio e o teste
    reprova por um `KeyError` que não aponta a causa (regra do projeto, commit
    `f68faf7` — "toda espera de thread ganha timeout, com asserção de que
    concluiu")."""
    resultado = {}

    def _ler():
        resultado["dmpl"] = ler()
        connection.close()

    def _escrever():
        assert liberar_escrita.wait(timeout=5), "a leitura não chegou à pausa a tempo"
        escrever()
        escrita_commitou.set()
        connection.close()

    t1 = threading.Thread(target=_ler)
    t2 = threading.Thread(target=_escrever)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()
    return resultado


@pytest.mark.django_db(transaction=True)
def test_snapshot_desligado_a_escrita_concorrente_produz_saldo_fantasma(monkeypatch):
    """**ANTES** (a vulnerabilidade é real, medida — não presumida): a mesma
    corrida do par, pela réplica SEM o snapshot. O débito concorrente na
    reserva legal (conta JÁ carregada antes da pausa) entra no movimento; o
    crédito na conta que nasceu depois da pausa não entra — a coluna da reserva
    some do documento e a conciliação com o Balanço, que enxerga o lançamento
    INTEIRO, acusa uma diferença de 500,00 que NÃO EXISTE em leitura limpa
    nenhuma: nem antes da escrita (que fecha em 0,00) nem depois dela (que
    fecha em 0,00 também).

    Este teste não depende do wrapper — a réplica não o tem, com ele ou não —
    e é por isso que ele mede o defeito, e não o conserto."""
    empresa, contas = _cenario_da_corrida()
    original, liberar_escrita, escrita_commitou = _pausa_apos_listar_as_contas(monkeypatch)

    resultado = _dispara_a_corrida(
        ler=lambda: _apurar_dmpl_sem_snapshot(empresa=empresa, ano=ANO, mes=MES),
        escrever=lambda: _escrever_reserva_nova(empresa=empresa, contas=contas),
        liberar_escrita=liberar_escrita,
        escrita_commitou=escrita_commitou,
    )
    dmpl_racy = resultado["dmpl"]

    # A MEIA LEITURA: 1.250,00 − 500,00 na reserva legal, e a coluna da conta
    # nova simplesmente não existe no documento — o número que o contador leu
    # não é o saldo que a base tem.
    assert dmpl_racy["colunas"] == [COLUNA_CAPITAL, COLUNA_RESERVA_LEGAL, COLUNA_LUCROS]
    assert dmpl_racy["saldo_final"]["valores"][COLUNA_RESERVA_LEGAL] == Decimal("750.00")
    assert dmpl_racy["saldo_final"]["total"] == Decimal("114500.00")
    # A DIFERENÇA FANTASMA: o Balanço (lido depois da pausa) viu o lançamento
    # inteiro e o PL fechou em 115.000,00; a DMPL parou em 114.500,00 — 500,00
    # de diferença que não correspondem a nada gravado, e a acusação vem só no
    # TOTAL: nenhuma coluna diverge, porque a conta que explica o valor não
    # estava na lista de colunas da leitura.
    assert dmpl_racy["conciliacao"]["total"]["saldo_no_balanco"] == Decimal("115000.00")
    assert dmpl_racy["conciliacao"]["total"]["diferenca"] == Decimal("-500.00")
    assert dmpl_racy["divergencias"] == ["total"]

    # Releitura LIMPA (concorrência desfeita, monkeypatch devolvido): a verdade
    # fecha em 0,00, a coluna que existe de verdade aparece, e o que existe de
    # verdade é uma pendência que NOMEIA o par — não a divergência inventada
    # acima.
    monkeypatch.setattr(contabilidade_services, "_colunas_de_cada_conta", original)
    connection.close()
    dmpl_depois = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)

    assert COLUNA_RESERVA_A_REALIZAR in [coluna["chave"] for coluna in dmpl_depois["colunas"]]
    assert dmpl_depois["saldo_final"]["valores"][COLUNA_RESERVA_A_REALIZAR] == VALOR_DA_ESCRITA
    assert dmpl_depois["saldo_final"]["total"] == Decimal("115000.00")
    assert dmpl_depois["conciliacao"]["total"]["diferenca"] == Decimal("0")
    assert dmpl_depois["pendencias"]["diferenca_de_fechamento"] == []
    sem_regra = dmpl_depois["pendencias"]["pares_de_colunas_sem_regra"]
    assert [(p["origem"], p["destino"]) for p in sem_regra] == [
        (COLUNA_RESERVA_LEGAL, COLUNA_RESERVA_A_REALIZAR)
    ]


@pytest.mark.django_db(transaction=True)
def test_com_o_snapshot_a_escrita_concorrente_nao_altera_a_dmpl(monkeypatch):
    """**DEPOIS** (DE-067 na DMPL, provado): a MESMA corrida, agora pela
    `apurar_dmpl` de verdade, com o `SET TRANSACTION ISOLATION LEVEL REPEATABLE
    READ`. A consulta do movimento e a conciliação com o Balanço enxergam o
    MESMO snapshot da consulta que listou as contas (tirado ANTES da escrita
    concorrente commitar): nem a conta nova nem o seu lançamento aparecem nesta
    leitura, a reserva legal continua em 1.250,00 e a conciliação fecha em
    0,00 — o número impresso é o ORIGINAL, o que o contador veria se ninguém
    tivesse escrito nada.

    A releitura posterior mostra por que isso importa: a conta nova e sua
    coluna existem DE VERDADE, e a pendência que acende é a honesta (o par de
    colunas sem regra), nunca a divergência fantasma que a leitura sem
    snapshot inventa."""
    empresa, contas = _cenario_da_corrida()
    original, liberar_escrita, escrita_commitou = _pausa_apos_listar_as_contas(monkeypatch)

    resultado = _dispara_a_corrida(
        ler=lambda: apurar_dmpl(empresa=empresa, ano=ANO, mes=MES),
        escrever=lambda: _escrever_reserva_nova(empresa=empresa, contas=contas),
        liberar_escrita=liberar_escrita,
        escrita_commitou=escrita_commitou,
    )
    dmpl_com_snapshot = resultado["dmpl"]

    # O documento é o do caso A, byte a byte: três colunas (a reserva nova não
    # existe NESTA leitura), 115.000,00 no total e a conciliação fechada.
    assert [coluna["chave"] for coluna in dmpl_com_snapshot["colunas"]] == [
        COLUNA_CAPITAL,
        COLUNA_RESERVA_LEGAL,
        COLUNA_LUCROS,
    ]
    assert dmpl_com_snapshot["saldo_final"]["valores"] == {
        COLUNA_CAPITAL: Decimal("100000.00"),
        COLUNA_RESERVA_LEGAL: Decimal("1250.00"),
        COLUNA_LUCROS: Decimal("13750.00"),
    }
    assert dmpl_com_snapshot["saldo_final"]["total"] == Decimal("115000.00")
    assert dmpl_com_snapshot["conciliacao"]["total"]["diferenca"] == Decimal("0")
    assert dmpl_com_snapshot["pendencias"]["diferenca_de_fechamento"] == []
    assert avaliar_emissao_da_dmpl(dmpl_com_snapshot)["pode_emitir"] is True

    # E a escrita concorrente REALMENTE aconteceu e commitou — não é que o
    # teste "não viu porque não rodou": numa leitura NOVA (concorrência
    # desfeita, monkeypatch devolvido, sem transação especial nenhuma) a coluna
    # nova aparece com 500,00, a reserva legal desce para 750,00, o total
    # volta a ser 115.000,00 — e o que acende é a pendência do par sem regra.
    monkeypatch.setattr(contabilidade_services, "_colunas_de_cada_conta", original)
    connection.close()
    dmpl_depois = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)

    assert COLUNA_RESERVA_A_REALIZAR in [coluna["chave"] for coluna in dmpl_depois["colunas"]]
    assert dmpl_depois["saldo_final"]["valores"][COLUNA_RESERVA_A_REALIZAR] == VALOR_DA_ESCRITA
    assert dmpl_depois["saldo_final"]["valores"][COLUNA_RESERVA_LEGAL] == Decimal("750.00")
    assert dmpl_depois["saldo_final"]["total"] == Decimal("115000.00")
    assert dmpl_depois["conciliacao"]["total"]["diferenca"] == Decimal("0")
    emissao_depois = avaliar_emissao_da_dmpl(dmpl_depois)
    assert emissao_depois["pode_emitir"] is False
    assert "diferenca_de_fechamento" not in emissao_depois["listas_pendentes"]
    assert [
        (p["origem"], p["destino"])
        for p in emissao_depois["listas_pendentes"]["pares_de_colunas_sem_regra"]
    ] == [(COLUNA_RESERVA_LEGAL, COLUNA_RESERVA_A_REALIZAR)]
