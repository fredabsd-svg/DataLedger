"""DL-061, fatia 1 — correção da rodada 1 da auditoria (N1, N2, N3, N4, N6,
N7, N8, N9; relatório `docs/auditorias/2026-10-01-dl-061-rodada-1.md`).

Cada teste daqui reprova SEM a correção do achado que cita (verificado antes
de corrigir e anotado no relatório de entrega) e passa com ela. As regras
novas, que o arquiteto decidiu:

- N1: contrapartidas externas SEM classificação decisiva não decidem a linha
  uma a uma; o LÍQUIDO delas na coluna decide (coluna + direção).
- N2: a classificação da DLPA da contrapartida só decide a linha nas colunas
  onde ela faz sentido (resultado e ajuste de exercício anterior: lucros
  acumulados; dividendo: lucros acumulados e as seis reservas de lucros).
- N3: aviso `resultado_na_conta_de_passagem`.
- N4: `classificavel` e `orientacao` na pendência de conta de PL sem coluna.
- N6: recusa da marca de adoção antecipada sem efeito.
- N7: coluna debitada E creditada no mesmo lançamento com outra partida é
  ambígua; ensaio diferencial DLPA × DMPL com semente fixa.
- N8: capital/reservas → tesouraria = cancelamento.
- N9: `D Ágio / C Capital` e a propriedade P4 (mesmo sinal por coluna).

Dados 100% sintéticos; aleatoriedade com semente FIXA (AGENTS.md §7).
"""

import random
from datetime import date
from decimal import Decimal

import pytest
from django.db import transaction

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA,
    ClassificacaoDlpa,
    LancamentoContabil,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
)
from apps.contabilidade.services import (
    ParametroContabilInvalido,
    apurar_dlpa,
    apurar_dmpl,
    avaliar_emissao_da_dlpa,
    avaliar_emissao_da_dmpl,
    definir_adocao_antecipada_da_nbc_tg_51,
    estornar_lancamento,
    linha_da_dmpl_equivalente_a_linha_da_dlpa,
    norma_das_demonstracoes,
    registrar_parametro_contabil,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    LUCROS,
    MES,
    PL,
    C,
    D,
    _apurar,
    _caso_a,
    _celula,
    _chaves_das_linhas,
    _conta,
    _contas_do_caso_b,
    _dec,
    _empresa,
    _gestor,
    _lancar,
    _lancar_itens,
    _linha,
    _pendencias_nao_vazias,
    _plano_basico,
)

pytestmark = pytest.mark.django_db

TESOURARIA = "acoes_ou_quotas_em_tesouraria"
LINHA_AQUISICAO = "aquisicao_de_acoes_ou_quotas_em_tesouraria"
LINHA_ALIENACAO = "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria"


def _caso_a_com_tesouraria():
    empresa, contas, gestor = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    return empresa, contas, gestor


# ---------------------------------------------------------------------------
# N1 — o LÍQUIDO da coluna decide a linha, não cada contrapartida
# ---------------------------------------------------------------------------


def test_n1_venda_de_acoes_em_tesouraria_com_ganho_em_receita_nao_infla_as_linhas():
    """Caso 1 da auditoria. D Caixa 1.800 / C Tesouraria 1.500 / C Receita 300:
    a coluna recebeu um crédito líquido de 1.500 — alienação de 1.500, e
    NENHUMA aquisição nova (antes saía aquisição de 1.800 e alienação de
    1.800, cada uma inflada em 300)."""
    empresa, contas, _ = _caso_a_com_tesouraria()
    _lancar(
        empresa, date(2026, 1, 5), "Aquisição", contas["tesouraria"], contas["caixa"], "1500.00"
    )
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Venda das ações com ganho levado à receita",
        [
            (contas["caixa"], "D", "1800.00"),
            (contas["tesouraria"], "C", "1500.00"),
            (contas["receita"], "C", "300.00"),
        ],
    )
    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("1500.00")
    # A única aquisição é a de janeiro; a venda não criou aquisição nenhuma.
    assert _celula(dmpl, LINHA_AQUISICAO, TESOURARIA) == _dec("-1500.00")
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("0.00")


def test_n1_integralizacao_com_receita_no_mesmo_lancamento_nao_cria_reducao_de_capital():
    """Caso 1, variante do capital. D Caixa 150 / C Capital 100 / C Receita 50:
    aumento de capital de 100,00 e NENHUMA redução (antes: aumento 150 e
    "redução" de 50 que nunca houve)."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Integralização com receita no mesmo lançamento",
        [
            (contas["caixa"], "D", "150.00"),
            (contas["capital"], "C", "100.00"),
            (contas["receita"], "C", "50.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("100.00")
    assert "reducao_de_capital" not in _chaves_das_linhas(dmpl)
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100100.00")


def test_n1_reducao_de_capital_com_contrapartida_de_sentido_oposto_vira_so_a_liquida():
    """D Capital 100 / D Despesa 50 / C Caixa 150: o capital caiu 100, uma só
    redução — e nenhum "aumento de capital" de 50 vindo da despesa."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Devolução de capital com despesa",
        [
            (contas["capital"], "D", "100.00"),
            (contas["despesa"], "D", "50.00"),
            (contas["caixa"], "C", "150.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "reducao_de_capital", "capital_social") == _dec("-100.00")
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)


def test_n1_aquisicao_de_tesouraria_com_contrapartida_de_sentido_oposto():
    """D Tesouraria 1.500 / D Despesa 200 / C Caixa 1.700: coluna -1.500 =
    aquisição de 1.500, sem "alienação" de 200 vinda da despesa."""
    empresa, contas, _ = _caso_a_com_tesouraria()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Compra das ações com corretagem lançada em despesa",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["despesa"], "D", "200.00"),
            (contas["caixa"], "C", "1700.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_AQUISICAO, TESOURARIA) == _dec("-1500.00")
    assert LINHA_ALIENACAO not in _chaves_das_linhas(dmpl)


def test_n1_reserva_de_capital_decide_pelo_liquido_credito_constitui_e_debito_e_pendencia():
    empresa, contas, _ = _caso_a()
    agio = _conta(
        empresa,
        "3.7",
        "Ágio na Emissão",
        PL,
        C,
        dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES,
        pai=contas["pl"],
    )
    # Crédito líquido de 150 (200 do caixa a débito, 50 de receita a crédito).
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Ágio com receita",
        [
            (contas["caixa"], "D", "200.00"),
            (agio, "C", "150.00"),
            (contas["receita"], "C", "50.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "constituicao_de_reservas_de_capital", "agio_na_emissao_de_acoes") == _dec(
        "150.00"
    )
    # Débito líquido de 100 (despesa 30 a débito, caixa 130 a crédito): sem regra.
    _lancar_itens(
        empresa,
        date(2026, 2, 6),
        "Devolução de ágio com despesa",
        [
            (agio, "D", "100.00"),
            (contas["despesa"], "D", "30.00"),
            (contas["caixa"], "C", "130.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert "contrapartidas_sem_classificacao" in _pendencias_nao_vazias(dmpl)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_n1_reservas_de_lucros_e_lucros_continuam_pendencia_por_contrapartida_sem_classificacao():
    """O líquido NÃO vale para lucros acumulados nem reservas de lucros: lá o
    evento é destinação ou ajuste e quem diz qual é a classificação da conta
    (D3 da DLPA)."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Lucros contra caixa e receita",
        [
            (contas["lucros"], "D", "100.00"),
            (contas["caixa"], "C", "150.00"),
            (contas["despesa"], "D", "50.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert {e["conta"] for e in dmpl["pendencias"]["contrapartidas_sem_classificacao"]} == {
        "1.1",
        "5.1",
    }
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


# Contas e sorteio compartilhados pelos ensaios aleatórios (P4 e DLPA × DMPL).


def _plano_do_ensaio(empresa):
    contas = _plano_basico(empresa)
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    contas["agio"] = _conta(
        empresa, "3.8", "Ágio", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES, pai=contas["pl"]
    )
    contas["retencao"] = _conta(
        empresa,
        "3.9",
        "Reserva de Retenção",
        PL,
        C,
        dmpl=COL.RESERVA_DE_RETENCAO_DE_LUCROS,
        dlpa=ClassificacaoDlpa.RESERVA_DE_RETENCAO_DE_LUCROS,
        pai=contas["pl"],
    )
    contas["a_integralizar"] = _conta(
        empresa,
        "3.7",
        "(-) Capital a Integralizar",
        PL,
        D,
        dmpl=COL.CAPITAL_SOCIAL,
        pai=contas["pl"],
    )
    contas["banco"] = _conta(empresa, "1.3", "Banco", TipoConta.ATIVO, D)
    return contas


_NOMES_DO_ENSAIO = (
    "caixa",
    "banco",
    "receita",
    "despesa",
    "dividendos",
    "resultado",
    "capital",
    "reserva_legal",
    "retencao",
    "agio",
    "ajustes",
    "tesouraria",
    "lucros",
    "prejuizos",
    "a_integralizar",
)


def _itens_aleatorios(rnd, contas):
    """Um lançamento de partidas dobradas válido: 1 a 3 débitos e 1 a 3
    créditos, valores inteiros múltiplos de 100 que fecham. Pode repetir uma
    conta nos dois lados (a coluna debitada e creditada no mesmo lançamento
    é justamente o caso N7)."""
    n_debitos, n_creditos = rnd.randint(1, 3), rnd.randint(1, 3)
    debitos = rnd.sample(_NOMES_DO_ENSAIO, n_debitos)
    creditos = rnd.sample(_NOMES_DO_ENSAIO, n_creditos)
    total = rnd.randint(max(n_debitos, n_creditos), 60)

    def _repartir(n):
        cortes = sorted(rnd.sample(range(1, total), n - 1)) if n > 1 else []
        limites = [0, *cortes, total]
        return [limites[i + 1] - limites[i] for i in range(n)]

    partes_d, partes_c = _repartir(n_debitos), _repartir(n_creditos)
    return [(contas[n], "D", f"{p * 100}.00") for n, p in zip(debitos, partes_d, strict=True)] + [
        (contas[n], "C", f"{p * 100}.00") for n, p in zip(creditos, partes_c, strict=True)
    ]


def _descrever(itens):
    return " ".join(f"{lado}:{conta.codigo}:{valor}" for conta, lado, valor in itens)


def _ensaiar(semente, quantidade, conferir):
    """Gera `quantidade` lançamentos aleatórios (semente FIXA), um por vez e
    ISOLADO — cada um é apurado sozinho dentro de um ponto de salvamento que é
    desfeito, de modo que a DMPL só enxerga aquele lançamento. `conferir(
    itens, dmpl)` devolve a lista de violações. Devolve `(violacoes,
    emitidas)`."""
    rnd = random.Random(semente)
    empresa = _empresa(f"Ensaio {semente}")
    contas = _plano_do_ensaio(empresa)
    violacoes = []
    emitidas = 0
    for _ in range(quantidade):
        itens = _itens_aleatorios(rnd, contas)
        with transaction.atomic():
            _lancar_itens(empresa, date(2026, 2, 10), "ensaio", itens)
            dmpl = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)
            if avaliar_emissao_da_dmpl(dmpl)["pode_emitir"]:
                emitidas += 1
                violacoes.extend(conferir(empresa, itens, dmpl))
            transaction.set_rollback(True)
    return violacoes, emitidas


# As três linhas que a CONTRAPARTIDA classificada na DLPA decide: seguem o
# item a item da DLPA (identidade, E3) e podem, legitimamente, ter sinais
# diferentes na mesma coluna (dividendo e ajuste no mesmo lançamento).
_LINHAS_DECIDIDAS_PELA_CLASSIFICACAO_DA_CONTRAPARTIDA = {
    "resultado_do_exercicio",
    "dividendos",
    "ajustes_de_exercicios_anteriores",
}


def _conferir_p4(_empresa_, itens, dmpl):
    """P4 — por lançamento, em toda DMPL emitida: a soma das células de cada
    coluna é o efeito líquido da coluna, e as células das linhas de evento
    (as que NÃO vêm da classificação da contrapartida) têm o mesmo sinal desse
    efeito líquido."""
    violacoes = []
    for coluna, final in dmpl["saldo_final"]["valores"].items():
        liquido = final - dmpl["saldo_inicial"]["valores"][coluna]
        soma = Decimal("0")
        for linha in dmpl["linhas"]:
            if linha["chave"] in ("saldo_inicial", "saldo_final"):
                continue
            valor = linha["valores"][coluna]
            soma += valor
            if linha["chave"] in _LINHAS_DECIDIDAS_PELA_CLASSIFICACAO_DA_CONTRAPARTIDA:
                continue
            if valor != 0 and (valor > 0) != (liquido > 0):
                violacoes.append(
                    ("sinal", coluna, linha["chave"], valor, liquido, _descrever(itens))
                )
        if soma != liquido:
            violacoes.append(("soma", coluna, soma, liquido, _descrever(itens)))
    return violacoes


@pytest.mark.parametrize("semente", [20261001, 61, 1234])
def test_p4_em_toda_dmpl_emitida_cada_coluna_tem_o_sinal_do_seu_efeito_liquido(semente):
    violacoes, emitidas = _ensaiar(semente, 90, _conferir_p4)
    assert emitidas >= 15, f"ensaio vazio demais: só {emitidas} lançamentos emitíveis"
    assert violacoes == [], violacoes[:5]


# ---------------------------------------------------------------------------
# N2 — a classificação da DLPA só decide a linha onde faz sentido
# ---------------------------------------------------------------------------


def test_n2_dividendos_a_pagar_capitalizados_viram_aumento_de_capital_e_nao_dividendos():
    """Caso 2 da auditoria. D Dividendos a pagar / C Capital 4.000: aumento de
    capital de 4.000,00; a linha "Dividendos" segue com os 10.000,00 do caso A
    (antes: Dividendos +4.000 no capital, total da linha (6.000))."""
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 31),
        "Capitalização de dividendos a pagar",
        contas["dividendos"],
        contas["capital"],
        "4000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("4000.00")
    assert _celula(dmpl, "dividendos", "capital_social") == _dec("0")
    assert _linha(dmpl, "dividendos")["total"] == _dec("-10000.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("104000.00")


def test_n2_dividendos_a_pagar_creditando_reserva_de_lucros_sem_estorno_e_pendencia():
    """D Dividendos a pagar / C Reserva legal 1.000: dividendo com efeito
    POSITIVO numa reserva de lucros, e o lançamento não é estorno de nada — o
    evento não é decidível (reconstituição de reserva com dividendo declarado?).
    Na dúvida, pendência: nunca um "Dividendos" positivo presumido."""
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 31),
        "Dividendos a pagar para reserva",
        contas["dividendos"],
        contas["reserva_legal"],
        "1000.00",
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert entrada["conta"] == "2.1" and entrada["coluna"] == "reserva_legal"
    assert "dividendo" in entrada["mensagem"].lower()
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # O dividendo POSITIVO não apareceu na linha de dividendos.
    assert _celula(dmpl, "dividendos", "reserva_legal") == _dec("0")
    # O saldo final continua certo: a pendência não esconde nem inventa saldo.
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("2250.00")


def test_n2_estorno_de_dividendo_pago_com_reserva_continua_dividendos_nos_dois_sinais():
    """O estorno é o procedimento de correção (RC-103) e PRESERVA a linha: o
    dividendo pago com a reserva (-300) e o seu estorno (+300) ficam na linha
    "Dividendos", líquido zero — e a emissão não é vetada."""
    empresa, contas, _ = _caso_a()
    pagamento = _lancar(
        empresa,
        date(2026, 3, 22),
        "Dividendo da reserva",
        contas["reserva_legal"],
        contas["dividendos"],
        "300.00",
    )
    estornar_lancamento(pagamento, data=date(2026, 3, 23))
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "dividendos", "reserva_legal") == _dec("0.00")
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("1250.00")


def test_n2_estorno_de_dividendo_nos_lucros_continua_positivo_pela_identidade_com_a_dlpa():
    empresa, contas, _ = _caso_a()
    pagamento = _lancar(
        empresa,
        date(2026, 3, 31),
        "Outro dividendo",
        contas["lucros"],
        contas["dividendos"],
        "400.00",
    )
    estornar_lancamento(pagamento, data=date(2026, 3, 31))
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    assert dlpa["saldo_final"] == dmpl["saldo_final"]["valores"][LUCROS]


@pytest.mark.parametrize(
    "classificacao", ["resultado_do_exercicio", "ajuste_de_exercicio_anterior"]
)
def test_n2_resultado_e_ajuste_de_exercicio_anterior_so_decidem_a_linha_nos_lucros(classificacao):
    """A classificação de resultado / ajuste de exercício anterior na
    contrapartida decide a linha SÓ na coluna de lucros acumulados. Contra o
    capital, a conta é uma contrapartida externa comum (aumento de capital);
    contra uma reserva de lucros, sem regra (pendência)."""
    empresa, contas, _ = _caso_a()
    if classificacao == "resultado_do_exercicio":
        # A classificação de resultado só existe em conta de PL: a de passagem.
        externa = contas["resultado"]
    else:
        externa = _conta(
            empresa,
            "1.9",
            "Correção de exercício anterior",
            TipoConta.ATIVO,
            D,
            dlpa=ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
        )
    _lancar(empresa, date(2026, 3, 10), "Para o capital", externa, contas["capital"], "700.00")
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("700.00")
    # Nenhuma das linhas "decididas pela classificação" recebeu valor no capital.
    for chave in ("resultado_do_exercicio", "ajustes_de_exercicios_anteriores"):
        if _linha(dmpl, chave) is not None:
            assert _celula(dmpl, chave, "capital_social") == _dec("0"), chave
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100700.00")

    _lancar(empresa, date(2026, 3, 11), "Para a reserva", externa, contas["reserva_legal"], "50.00")
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert entrada["coluna"] == "reserva_legal"


def test_n2_ajuste_de_exercicio_anterior_e_resultado_continuam_decidindo_nos_lucros():
    """Nenhuma mudança onde a classificação faz sentido (coluna de lucros)."""
    empresa, contas, _ = _caso_a()
    ajuste = _conta(
        empresa,
        "1.3",
        "Ajuste",
        TipoConta.ATIVO,
        D,
        dlpa=ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
    )
    _lancar(empresa, date(2026, 3, 22), "Retificação", ajuste, contas["lucros"], "150.00")
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "ajustes_de_exercicios_anteriores", LUCROS) == _dec("150.00")
    assert _celula(dmpl, "resultado_do_exercicio", LUCROS) == _dec("25000.00")


# ---------------------------------------------------------------------------
# N3 — aviso de saldo na conta de passagem
# ---------------------------------------------------------------------------


def _estornar_a_transferencia_para_lucros(empresa):
    transferencia = LancamentoContabil.objects.get(
        empresa=empresa, historico__contains="transferência para lucros acumulados"
    )
    return estornar_lancamento(transferencia, data=date(2026, 3, 31))


def test_n3_saldo_na_conta_de_passagem_gera_aviso_e_nao_veta():
    """Caso 3 da auditoria: estornada a transferência para os lucros, o
    resultado de 25.000,00 volta à conta de passagem. O total do documento
    fica 25.000,00 abaixo do PL do Balanço — o aviso diz isso (E5 do plano)."""
    empresa, contas, _ = _caso_a()
    _estornar_a_transferencia_para_lucros(empresa)
    dmpl = _apurar(empresa)

    assert dmpl["avisos"]["resultado_na_conta_de_passagem"] == [
        {
            "valor": _dec("25000.00"),
            "contas": [
                {
                    "conta_id": contas["resultado"].id,
                    "conta": "3.0",
                    "nome": "Resultado do Exercício",
                    "saldo": _dec("25000.00"),
                }
            ],
        }
    ]
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, "aviso nunca veta"
    assert emissao["avisos"]["resultado_na_conta_de_passagem"][0]["valor"] == _dec("25000.00")
    assert dmpl["conciliacao"]["total"]["saldo_contas_de_passagem"] == _dec("25000.00")


def test_n3_sem_saldo_na_passagem_a_chave_existe_e_vem_vazia():
    empresa, _, _ = _caso_a()
    dmpl = _apurar(empresa)
    assert dmpl["avisos"]["resultado_na_conta_de_passagem"] == []
    assert "resultado_na_conta_de_passagem" not in avaliar_emissao_da_dmpl(dmpl)["avisos"]


def test_n3_saldo_devedor_na_passagem_e_negativo_e_so_lista_conta_com_saldo():
    empresa = _empresa()
    contas = _plano_basico(empresa)
    outra = _conta(
        empresa,
        "3.0.1",
        "Outra conta de passagem",
        PL,
        C,
        dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2025, 12, 31), "Capital", contas["caixa"], contas["capital"], "1000.00")
    _lancar(
        empresa,
        date(2026, 3, 5),
        "Prejuízo apurado",
        contas["resultado"],
        contas["caixa"],
        "200.00",
    )
    dmpl = _apurar(empresa)
    (aviso,) = dmpl["avisos"]["resultado_na_conta_de_passagem"]
    assert aviso["valor"] == _dec("-200.00")
    assert [c["conta_id"] for c in aviso["contas"]] == [contas["resultado"].id]
    assert outra.id not in [c["conta_id"] for c in aviso["contas"]]
    assert aviso["contas"][0]["saldo"] == _dec("-200.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


# ---------------------------------------------------------------------------
# N4 — conta de PL cuja classificação da DLPA não admite coluna
# ---------------------------------------------------------------------------


def test_n4_conta_de_pl_de_dividendo_ou_ajuste_nao_e_classificavel_e_traz_orientacao():
    empresa, contas, _ = _caso_a()
    proposto = _conta(
        empresa,
        "3.8",
        "Dividendos Propostos (PL)",
        PL,
        D,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=contas["pl"],
    )
    ajuste = _conta(
        empresa,
        "3.9",
        "Ajustes de Exercícios Anteriores (PL)",
        PL,
        C,
        dlpa=ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
        pai=contas["pl"],
    )
    comum = _conta(empresa, "3.10", "Outra conta de PL", PL, C, pai=contas["pl"])
    for conta in (proposto, ajuste, comum):
        _lancar(empresa, date(2026, 3, 10), "Movimento", contas["caixa"], conta, "10.00")
    dmpl = _apurar(empresa)
    entradas = {
        e["conta"]: e for e in dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]
    }
    assert set(entradas) == {"3.8", "3.9", "3.10"}
    for codigo in ("3.8", "3.9"):
        assert entradas[codigo]["classificavel"] is False, codigo
        orientacao = entradas[codigo]["orientacao"]
        assert isinstance(orientacao, str) and "BL-603" in orientacao
        assert "ainda não tem coluna na DMPL" in orientacao
    assert "passivo" in entradas["3.8"]["orientacao"]
    assert entradas["3.10"]["classificavel"] is True
    assert entradas["3.10"]["orientacao"] == ""


def test_n4_classificavel_e_derivado_do_mapa_de_consistencia_da_dlpa_e_da_dmpl():
    """Propriedade, não lista: toda classificação da DLPA que o mapa de
    consistência liga a NENHUMA coluna dá `classificavel = False`; as demais,
    `True` (o servidor aceitaria alguma coluna)."""
    nao_classificaveis = {
        dlpa
        for dlpa, colunas in COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA.items()
        if not colunas
    }
    assert nao_classificaveis >= {
        ClassificacaoDlpa.DIVIDENDO,
        ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
    }
    for dlpa in ClassificacaoDlpa.values:
        if dlpa == ClassificacaoDlpa.RESULTADO_DO_EXERCICIO:
            continue  # conta de passagem: nunca entra na pendência.
        empresa = _empresa(f"N4 {dlpa}")
        pl = _conta(empresa, "3", "Patrimônio Líquido", PL, C)
        caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, D)
        conta = _conta(empresa, "3.1", "Conta de PL", PL, C, dlpa=dlpa, pai=pl)
        _lancar(empresa, date(2026, 3, 10), "Movimento", caixa, conta, "10.00")
        dmpl = _apurar(empresa)
        (entrada,) = dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]
        assert entrada["classificavel"] is (dlpa not in nao_classificaveis), dlpa
        assert bool(entrada["orientacao"]) is (dlpa in nao_classificaveis), dlpa


# ---------------------------------------------------------------------------
# N6 — marca de adoção antecipada sem efeito é recusada
# ---------------------------------------------------------------------------


def _empresa_com_vigencia(inicio, fim=None, usuario_nome="gestor-n6"):
    empresa = _empresa(f"N6 {inicio}")
    contas = _plano_basico(empresa)
    gestor = _gestor(empresa, usuario_nome + str(empresa.pk))
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=inicio,
        usuario=gestor,
    )
    if fim is not None:
        ParametroContabilEmpresa.objects.filter(empresa=empresa).update(vigencia_fim=fim)
    return empresa, gestor


def test_n6_vigencia_iniciada_depois_de_primeiro_de_janeiro_sem_exercicio_dentro_e_recusada():
    """Caso 6: vigência de 01/03/2026 em diante — nenhum 01/01 anterior a
    2027 cai nela. A marca não teria efeito (a TG 51 vale por si em 2027):
    recusa clara, nada gravado, nenhuma trilha."""
    empresa, gestor = _empresa_com_vigencia(date(2026, 3, 1))
    trilhas_antes = RegistroAuditoria.objects.count()
    with pytest.raises(ParametroContabilInvalido) as erro:
        definir_adocao_antecipada_da_nbc_tg_51(
            empresa=empresa, data_inicio_exercicio=date(2026, 3, 1), adota=True, usuario=gestor
        )
    assert "2027" in str(erro.value) and "01/03/2026" in str(erro.value)
    assert (
        ParametroContabilEmpresa.objects.get(empresa=empresa).adota_nbc_tg_51_antecipadamente
        is False
    )
    assert RegistroAuditoria.objects.count() == trilhas_antes
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 1, 1))["chave"]
        == "nbc_tg_26_r5"
    )


def test_n6_vigencia_encerrada_antes_do_primeiro_de_janeiro_seguinte_tambem_e_recusada():
    empresa, gestor = _empresa_com_vigencia(date(2025, 3, 15), fim=date(2025, 12, 31))
    with pytest.raises(ParametroContabilInvalido):
        definir_adocao_antecipada_da_nbc_tg_51(
            empresa=empresa, data_inicio_exercicio=date(2025, 6, 1), adota=True, usuario=gestor
        )


@pytest.mark.parametrize(
    ("inicio", "fim"),
    [
        (date(2026, 1, 1), None),  # começa em 01/01 de 2026
        (date(2025, 3, 15), None),  # cobre o 01/01/2026
        (date(2025, 3, 15), date(2026, 1, 1)),  # o 01/01/2026 é o último dia
    ],
)
def test_n6_vigencia_com_primeiro_de_janeiro_anterior_a_2027_aceita_a_marca(inicio, fim):
    empresa, gestor = _empresa_com_vigencia(inicio, fim=fim)
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=inicio, adota=True, usuario=gestor
    )
    assert ParametroContabilEmpresa.objects.get(empresa=empresa).adota_nbc_tg_51_antecipadamente


def test_n6_desligar_a_marca_nunca_e_recusado():
    """Marca legada (gravada antes da regra) numa vigência sem efeito tem de
    poder ser DESLIGADA."""
    empresa, gestor = _empresa_com_vigencia(date(2026, 3, 1))
    ParametroContabilEmpresa.objects.filter(empresa=empresa).update(
        adota_nbc_tg_51_antecipadamente=True
    )
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 3, 1), adota=False, usuario=gestor
    )
    assert not ParametroContabilEmpresa.objects.get(empresa=empresa).adota_nbc_tg_51_antecipadamente


# ---------------------------------------------------------------------------
# N7 — coluna debitada E creditada no mesmo lançamento
# ---------------------------------------------------------------------------


def test_n7_reserva_debitada_e_creditada_no_mesmo_lancamento_com_lucros_e_ambigua():
    """Caso 7. D Reserva legal 3.300 / C Reserva legal 1.300 / C Lucros 2.000:
    a DLPA lê item a item (reversão 3.300 e constituição 1.300); a DMPL
    somaria por coluna (reversão 2.000) e as duas discordariam na quebra. O
    lançamento é AMBÍGUO (veto), nunca duas decomposições diferentes."""
    empresa, contas, _ = _caso_a()
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Reserva debitada e creditada",
        [
            (contas["reserva_legal"], "D", "3300.00"),
            (contas["reserva_legal"], "C", "1300.00"),
            (contas["lucros"], "C", "2000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["lancamentos_ambiguos"]
    assert entrada["lancamento_id"] == ambiguo.id
    assert "Reserva legal" in entrada["colunas"]
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # Nenhuma célula foi decidida para o lançamento; o saldo final segue certo.
    assert _linha(dmpl, "reversao_de_reservas") is None
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("-750.00")


def test_n7_mesma_coluna_nos_dois_lados_com_conta_externa_tambem_e_ambigua():
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Reserva debitada e creditada contra o caixa",
        [
            (contas["reserva_legal"], "D", "300.00"),
            (contas["reserva_legal"], "C", "100.00"),
            (contas["caixa"], "C", "200.00"),
        ],
    )
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(_apurar(empresa))


def test_n7_subscricao_pura_contra_capital_a_integralizar_continua_efeito_zero_sem_pendencia():
    """O que NÃO muda: a subscrição (capital a integralizar × capital, sem
    outra partida) não tem evento e não tem pendência."""
    empresa, contas, _ = _caso_a()
    a_integralizar = _conta(
        empresa,
        "3.8",
        "(-) Capital a Integralizar",
        PL,
        D,
        dmpl=COL.CAPITAL_SOCIAL,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 2, 1), "Subscrição", a_integralizar, contas["capital"], "50000.00")
    dmpl = _apurar(empresa)
    assert _pendencias_nao_vazias(dmpl) == set()
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)


def test_n7_lucros_e_prejuizos_na_mesma_coluna_no_mesmo_lancamento_nao_divergem_da_dlpa():
    """A coluna de lucros reúne duas contas sujeito; a DLPA TAMBÉM soma os
    itens delas (`movimento += efeito`). Por isso lucros debitado e
    creditado no mesmo lançamento não diverge, e não é veto."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Compensação e reserva no mesmo lançamento",
        [
            (contas["lucros"], "D", "300.00"),
            (contas["prejuizos"], "C", "100.00"),
            (contas["reserva_legal"], "C", "200.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    _conferir_identidade_linha_a_linha(empresa, dmpl)


def _conferir_identidade_linha_a_linha(empresa, dmpl):
    """Devolve as divergências entre a coluna de lucros da DMPL e a DLPA, ou
    `[]`. Só chamada com as DUAS emissíveis (a DLPA pode vetar o que a DMPL
    emite: ela exige classificação de toda contrapartida)."""
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    divergencias = []
    if dmpl["saldo_inicial"]["valores"][LUCROS] != dlpa["saldo_inicial"]:
        divergencias.append("saldo inicial")
    if dmpl["saldo_final"]["valores"][LUCROS] != dlpa["saldo_final"]:
        divergencias.append("saldo final")
    esperado = {}
    for linha in dlpa["linhas"]:
        if linha["chave"] in ("saldo_inicial", "saldo_final"):
            continue
        equivalente = linha_da_dmpl_equivalente_a_linha_da_dlpa(linha["chave"])
        esperado[equivalente] = esperado.get(equivalente, Decimal("0")) + linha["valor"]
    encontrado = {
        linha["chave"]: linha["valores"][LUCROS]
        for linha in dmpl["linhas"]
        if linha["chave"] not in ("saldo_inicial", "saldo_final") and linha["valores"][LUCROS] != 0
    }
    esperado = {chave: valor for chave, valor in esperado.items() if valor != 0}
    if encontrado != esperado:
        divergencias.append(("linhas", encontrado, esperado))
    return divergencias


def _conferir_identidade_com_a_dlpa_se_as_duas_emitem(empresa, itens, dmpl):
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    if not avaliar_emissao_da_dlpa(dlpa)["pode_emitir"]:
        return []
    return [(_descrever(itens), d) for d in _conferir_identidade_linha_a_linha(empresa, dmpl)]


@pytest.mark.parametrize("semente", [20261001, 61, 1234])
def test_n7_ensaio_diferencial_dlpa_x_dmpl_identidade_linha_a_linha_com_semente_fixa(semente):
    """O ensaio do auditor como teste: para lançamentos aleatórios, sempre
    que as DUAS demonstrações emitem, a coluna de lucros da DMPL é a DLPA
    linha a linha (saldo inicial, cada evento, saldo final)."""
    violacoes, emitidas = _ensaiar(semente, 90, _conferir_identidade_com_a_dlpa_se_as_duas_emitem)
    assert emitidas >= 15
    assert violacoes == [], violacoes[:5]


# ---------------------------------------------------------------------------
# N8 — cancelamento de ações em tesouraria
# ---------------------------------------------------------------------------


def test_n8_capital_para_tesouraria_e_cancelamento_de_acoes():
    """D Capital / C Tesouraria: o capital é reduzido pelo cancelamento das
    ações em tesouraria. Linha "Alienação ou cancelamento…", capital negativo
    e tesouraria positiva (a retificadora diminui)."""
    empresa, contas, _ = _caso_a_com_tesouraria()
    _lancar(
        empresa, date(2026, 2, 1), "Aquisição", contas["tesouraria"], contas["caixa"], "2000.00"
    )
    _lancar(
        empresa,
        date(2026, 3, 1),
        "Cancelamento",
        contas["capital"],
        contas["tesouraria"],
        "1500.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_ALIENACAO, "capital_social") == _dec("-1500.00")
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("1500.00")
    assert _linha(dmpl, LINHA_ALIENACAO)["total"] == _dec("0.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("98500.00")
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("-500.00")


@pytest.mark.parametrize("origem", ["reserva_legal", "agio"])
def test_n8_reservas_de_lucros_e_de_capital_para_tesouraria_tambem_sao_cancelamento(origem):
    empresa, contas, _ = _caso_a_com_tesouraria()
    contas["agio"] = _conta(
        empresa, "3.7", "Ágio", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES, pai=contas["pl"]
    )
    _lancar(empresa, date(2026, 1, 10), "Ágio recebido", contas["caixa"], contas["agio"], "800.00")
    _lancar(empresa, date(2026, 2, 1), "Aquisição", contas["tesouraria"], contas["caixa"], "600.00")
    _lancar(
        empresa, date(2026, 3, 1), "Cancelamento", contas[origem], contas["tesouraria"], "500.00"
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, _pendencias_nao_vazias(dmpl)
    coluna = "reserva_legal" if origem == "reserva_legal" else "agio_na_emissao_de_acoes"
    assert _celula(dmpl, LINHA_ALIENACAO, coluna) == _dec("-500.00")
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("500.00")


def test_n8_lucros_acumulados_para_tesouraria_continua_sem_regra():
    """A DLPA também vetaria (a tesouraria não tem linha lá): sem regra."""
    empresa, contas, _ = _caso_a_com_tesouraria()
    _lancar(
        empresa,
        date(2026, 3, 1),
        "Lucros para tesouraria",
        contas["lucros"],
        contas["tesouraria"],
        "100.00",
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["pares_de_colunas_sem_regra"]
    assert (entrada["origem"], entrada["destino"]) == (LUCROS, TESOURARIA)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


# ---------------------------------------------------------------------------
# N9 — lacunas de teste
# ---------------------------------------------------------------------------


def test_n9_agio_incorporado_ao_capital_e_aumento_de_capital_com_reservas_e_lucros():
    """Caso 8. D Ágio 500 / C Capital 500 (ágio já constituído). Mata o
    mutante N02 (reservas de capital fora da lista de origens)."""
    empresa, contas, _ = _caso_a()
    agio = _conta(
        empresa,
        "3.7",
        "Ágio na Emissão",
        PL,
        C,
        dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 1, 3), "Ágio recebido", contas["caixa"], agio, "500.00")
    _lancar(empresa, date(2026, 3, 30), "Capitalização do ágio", agio, contas["capital"], "500.00")
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    linha = "aumento_de_capital_com_reservas_e_lucros"
    assert _celula(dmpl, linha, "agio_na_emissao_de_acoes") == _dec("-500.00")
    assert _celula(dmpl, linha, "capital_social") == _dec("500.00")
    assert dmpl["saldo_final"]["valores"]["agio_na_emissao_de_acoes"] == _dec("0.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100500.00")
