"""DL-062 (servidor) — continuação da DMPL (DL-061): a coluna do dividendo
adicional proposto (G1, RC-153), o veto do lançamento com eventos opostos na
mesma coluna (G2, RC-155) e a saída pelo estorno (G3, M3 da reconferência).

Plano: docs/planos/DL-062-dmpl-dividendo-proposto-e-vetos.md. Cada regra tem
um teste que reprova sob a mutação plausível dela (as mutações aplicadas estão
no relatório de entrega). Dados 100% sintéticos; datas no passado (hoje é
2026-10-01) e, por isso, o caso do dividendo usa os exercícios de 2025 e 2026;
aleatoriedade com semente FIXA (AGENTS.md §7).

NENHUM item da ICPC 08 é citado: a PE-75 (leitura em fonte oficial) segue
aberta.
"""

import random
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.contabilidade.models import (
    COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA,
    ClassificacaoDlpa,
    ClassificacaoDmpl,
    GrupoDaDmpl,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
    divergencia_entre_dlpa_e_dmpl,
)
from apps.contabilidade.services import (
    _TITULOS_DAS_LINHAS_DA_DMPL,
    _e_o_estorno_exato,
    apurar_dlpa,
    apurar_dmpl,
    avaliar_emissao_da_dlpa,
    avaliar_emissao_da_dmpl,
    classificar_conta_na_dmpl,
    criar_lancamento,
    estornar_lancamento,
    linha_da_dmpl_equivalente_a_linha_da_dlpa,
    linhas_da_dmpl_que_somam_a_linha_da_dlpa,
    registrar_parametro_contabil,
    zerar_resultado,
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
    comparar_lucros_da_dmpl_com_as_linhas_da_dlpa,
)
from apps.contabilidade.tests.test_dl061_dmpl_correcao_rodada1 import (
    _NOMES_DO_ENSAIO,
    _conferir_identidade_com_a_dlpa_se_as_duas_emitem,
    _conferir_p4,
    _descrever,
    _ensaiar,
    _itens_aleatorios,
    _plano_do_ensaio,
)

pytestmark = pytest.mark.django_db

PROPOSTO = COL.DIVIDENDO_ADICIONAL_PROPOSTO
LINHA_PROPOSTA = "dividendo_adicional_proposto"
LINHA_DIVIDENDOS = "dividendos"


def _identidade_com_a_dlpa(empresa, *, ano=ANO, mes=MES):
    """`(dlpa, dmpl)` depois de provar a identidade da coluna de lucros com a
    DLPA (saldos e linhas, com a soma do dividendo — G1)."""
    dlpa = apurar_dlpa(empresa=empresa, ano=ano, mes=mes)
    dmpl = apurar_dmpl(empresa=empresa, ano=ano, mes=mes)
    assert dmpl["saldo_inicial"]["valores"][LUCROS] == dlpa["saldo_inicial"]
    assert dmpl["saldo_final"]["valores"][LUCROS] == dlpa["saldo_final"]
    esperado, encontrado = comparar_lucros_da_dmpl_com_as_linhas_da_dlpa(dlpa, dmpl)
    assert encontrado == esperado
    return dlpa, dmpl


# ===========================================================================
# G1 — coluna "Dividendo adicional proposto" (RC-153)
# ===========================================================================


def _contas_com_dividendo_adicional_proposto(empresa, contas):
    contas["proposto"] = _conta(
        empresa,
        "3.20",
        "Dividendo Adicional Proposto",
        PL,
        C,
        dmpl=PROPOSTO,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=contas["pl"],
    )
    return contas


def _empresa_com_proposta_em_2025_e_aprovacao_em_2026():
    """Exercício de 2025 e abril de 2026, calculados à mão:

    - 31/12/2024: capital integralizado de 100.000,00;
    - junho/2025: lucro de 30.000,00 (zeramento mensal feito);
    - 20/12/2025: reserva legal de 1.500,00;
    - 31/12/2025: dividendos obrigatórios de 6.000,00 (passivo) e PROPOSTA de
      dividendo adicional de 9.000,00 (coluna nova);
    - 15/04/2026: APROVAÇÃO dos 9.000,00 (a coluna nova vai ao passivo).
    """
    empresa = _empresa("Empresa Dividendo Proposto Ltda")
    contas = _contas_com_dividendo_adicional_proposto(empresa, _plano_basico(empresa))
    gestor = _gestor(empresa, f"gestor-g1-{empresa.pk}")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2025, 1, 1),
        usuario=gestor,
    )
    _lancar(
        empresa,
        date(2024, 12, 31),
        "Capital integralizado",
        contas["caixa"],
        contas["capital"],
        "100000.00",
    )
    _lancar(empresa, date(2025, 6, 10), "Receita", contas["caixa"], contas["receita"], "30000.00")
    zerar_resultado(empresa=empresa, ano=2025, mes=6, usuario=gestor)
    _lancar(
        empresa,
        date(2025, 12, 20),
        "Reserva legal",
        contas["lucros"],
        contas["reserva_legal"],
        "1500.00",
    )
    _lancar(
        empresa,
        date(2025, 12, 31),
        "Dividendos obrigatórios",
        contas["lucros"],
        contas["dividendos"],
        "6000.00",
    )
    _lancar(
        empresa,
        date(2025, 12, 31),
        "Proposta de dividendo adicional",
        contas["lucros"],
        contas["proposto"],
        "9000.00",
    )
    aprovacao = _lancar(
        empresa,
        date(2026, 4, 15),
        "Aprovação do dividendo adicional",
        contas["proposto"],
        contas["dividendos"],
        "9000.00",
    )
    return empresa, contas, gestor, aprovacao


def test_g1_proposta_em_dezembro_emite_com_os_valores_calculados_a_mao():
    empresa, _, _, _ = _empresa_com_proposta_em_2025_e_aprovacao_em_2026()
    dmpl = apurar_dmpl(empresa=empresa, ano=2025, mes=12)

    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    assert [c["chave"] for c in dmpl["colunas"]] == [
        "capital_social",
        "reserva_legal",
        LUCROS,
        "dividendo_adicional_proposto",
    ]
    # Coluna nova: grupo "demais contas exigidas", depois de lucros ou prejuízos.
    nova = dmpl["colunas"][-1]
    assert nova["titulo"] == "Dividendo adicional proposto"
    assert nova["grupo"] == "demais_contas_exigidas"
    assert nova["grupo_titulo"] == "Demais contas exigidas"

    # A linha nova vem logo depois de "Dividendos"; a aprovação ainda não houve.
    assert _chaves_das_linhas(dmpl) == [
        "saldo_inicial",
        "resultado_do_exercicio",
        "constituicao_de_reservas",
        "dividendos",
        "dividendo_adicional_proposto",
        "saldo_final",
    ]
    assert _celula(dmpl, LINHA_DIVIDENDOS, LUCROS) == _dec("-6000.00")
    assert _celula(dmpl, LINHA_DIVIDENDOS, PROPOSTO) == _dec("0")
    # Proposta: lucros diminuem, a coluna nova aumenta, e o total da linha é zero.
    assert _celula(dmpl, LINHA_PROPOSTA, LUCROS) == _dec("-9000.00")
    assert _celula(dmpl, LINHA_PROPOSTA, PROPOSTO) == _dec("9000.00")
    assert _linha(dmpl, LINHA_PROPOSTA)["total"] == _dec("0.00")
    assert dmpl["linhas"][-2]["titulo"] == "Dividendo adicional proposto"

    # 100.000 + 30.000 − 6.000 = 124.000 (a proposta só muda de coluna).
    assert dmpl["saldo_inicial"]["total"] == _dec("100000.00")
    assert dmpl["saldo_final"]["valores"] == {
        "capital_social": _dec("100000.00"),
        "reserva_legal": _dec("1500.00"),
        LUCROS: _dec("13500.00"),
        "dividendo_adicional_proposto": _dec("9000.00"),
    }
    assert dmpl["saldo_final"]["total"] == _dec("124000.00")
    assert dmpl["conciliacao"]["total"]["diferenca"] == _dec("0")


def test_g1_aprovacao_em_abril_do_ano_seguinte_baixa_a_coluna_nova_pela_linha_dividendos():
    empresa, _, _, aprovacao = _empresa_com_proposta_em_2025_e_aprovacao_em_2026()
    dmpl = apurar_dmpl(empresa=empresa, ano=2026, mes=4)

    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    # O saldo inicial de 2026 é o final de 2025.
    assert dmpl["saldo_inicial"]["valores"] == {
        "capital_social": _dec("100000.00"),
        "reserva_legal": _dec("1500.00"),
        LUCROS: _dec("13500.00"),
        "dividendo_adicional_proposto": _dec("9000.00"),
    }
    assert dmpl["saldo_inicial"]["total"] == _dec("124000.00")
    # Aprovação: a linha é "Dividendos", com a coluna nova NEGATIVA — é aqui
    # que o total do PL diminui. Nenhuma linha de proposta.
    assert _chaves_das_linhas(dmpl) == ["saldo_inicial", "dividendos", "saldo_final"]
    assert _celula(dmpl, LINHA_DIVIDENDOS, PROPOSTO) == _dec("-9000.00")
    assert _celula(dmpl, LINHA_DIVIDENDOS, LUCROS) == _dec("0")
    assert _linha(dmpl, LINHA_DIVIDENDOS)["total"] == _dec("-9000.00")
    assert _linha(dmpl, LINHA_DIVIDENDOS)["lancamentos"][PROPOSTO] == [aprovacao.id]
    assert dmpl["saldo_final"]["valores"][PROPOSTO] == _dec("0")
    assert dmpl["saldo_final"]["total"] == _dec("115000.00")
    assert dmpl["conciliacao"]["total"]["diferenca"] == _dec("0")


def test_g1_identidade_com_a_dlpa_pela_soma_de_dividendos_e_dividendo_adicional_proposto():
    empresa, _, _, _ = _empresa_com_proposta_em_2025_e_aprovacao_em_2026()

    dlpa, dmpl = _identidade_com_a_dlpa(empresa, ano=2025, mes=12)
    assert avaliar_emissao_da_dlpa(dlpa)["pode_emitir"] is True
    (linha_dlpa,) = [x for x in dlpa["linhas"] if x["chave"] == "dividendo"]
    # A DLPA mostra UMA linha de dividendo: 6.000 + 9.000.
    assert linha_dlpa["valor"] == _dec("-15000.00")
    dividendos = _celula(dmpl, LINHA_DIVIDENDOS, LUCROS)
    proposta = _celula(dmpl, LINHA_PROPOSTA, LUCROS)
    assert dividendos + proposta == linha_dlpa["valor"]
    # A soma é necessária: nenhuma das duas linhas, sozinha, é a da DLPA.
    assert dividendos != linha_dlpa["valor"]
    assert proposta != linha_dlpa["valor"]

    # 2026: a aprovação não toca os lucros acumulados, e a DLPA não muda.
    dlpa_2026, dmpl_2026 = _identidade_com_a_dlpa(empresa, ano=2026, mes=4)
    assert [x["valor"] for x in dlpa_2026["linhas"] if x["chave"] == "dividendo"] in ([], [0])
    assert _celula(dmpl_2026, LINHA_DIVIDENDOS, LUCROS) == _dec("0")


def test_g1_a_identidade_soma_so_a_linha_de_dividendo_e_nao_afrouxa_as_demais():
    """`linhas_da_dmpl_que_somam_a_linha_da_dlpa`: a linha de dividendo da DLPA
    tem duas linhas na DMPL; toda outra continua UMA a uma, igual à tabela
    do DL-061 (propriedade sobre o enum inteiro, não uma lista)."""
    chaves = [*ClassificacaoDlpa.values, "transferencia:reserva_legal", "reversao:reserva_legal"]
    for chave in chaves:
        grupo = linhas_da_dmpl_que_somam_a_linha_da_dlpa(chave)
        equivalente = linha_da_dmpl_equivalente_a_linha_da_dlpa(chave)
        if chave == ClassificacaoDlpa.DIVIDENDO:
            assert grupo == ("dividendos", "dividendo_adicional_proposto")
        elif equivalente is None:
            assert grupo == (), chave
        else:
            assert grupo == (equivalente,), chave
    # Saldos não têm par.
    assert linhas_da_dmpl_que_somam_a_linha_da_dlpa("saldo_inicial") == ()
    assert linhas_da_dmpl_que_somam_a_linha_da_dlpa("saldo_final") == ()


def test_g1_o_comparador_de_identidade_reprova_dividendo_adicional_sem_dividendo_na_dlpa():
    """O comparador não é um sim universal: linha da DMPL com valor nos
    lucros que nenhuma linha da DLPA espelha reprova. Aqui a proposta aparece
    na DMPL mas a conta não tem a classificação de dividendo na DLPA, então a
    DLPA nem a vê — e a diferença é acusada."""
    empresa, contas, _ = _caso_a()
    sem_dlpa = _conta(
        empresa,
        "3.21",
        "Proposto sem DLPA",
        PL,
        C,
        dmpl=PROPOSTO,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 3, 31), "Proposta", contas["lucros"], sem_dlpa, "700.00")
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    dmpl = _apurar(empresa)
    esperado, encontrado = comparar_lucros_da_dmpl_com_as_linhas_da_dlpa(dlpa, dmpl)
    assert encontrado != esperado
    # A DLPA só vê os 10.000 do caso A; a DMPL soma os 700 da proposta.
    grupo = ("dividendos", "dividendo_adicional_proposto")
    assert esperado[grupo] == _dec("-10000.00")
    assert encontrado[grupo] == _dec("-10700.00")


def test_g1_o_dividendo_da_dlpa_admite_a_coluna_nova_e_so_ela():
    """Propriedade sobre o enum: entre TODAS as colunas, a única que a
    classificação DLPA "dividendo" admite é a nova."""
    admitidas = COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA[ClassificacaoDlpa.DIVIDENDO]
    assert admitidas == frozenset({PROPOSTO})
    empresa = _empresa()
    for coluna in ClassificacaoDmpl:
        conta = _conta(empresa, f"3.{ClassificacaoDmpl.values.index(coluna)}", "Conta", PL, C)
        conta.classificacao_dlpa = ClassificacaoDlpa.DIVIDENDO
        conta.classificacao_dmpl = coluna
        if coluna == PROPOSTO:
            assert divergencia_entre_dlpa_e_dmpl(ClassificacaoDlpa.DIVIDENDO, coluna) is None
            conta.full_clean()
        else:
            with pytest.raises(ValidationError, match="DLPA"):
                conta.full_clean()


@pytest.mark.parametrize(
    "dlpa",
    [d for d in ClassificacaoDlpa if d not in (ClassificacaoDlpa.DIVIDENDO,)],
)
def test_g1_a_coluna_nova_nao_combina_com_outra_classificacao_da_dlpa(dlpa):
    empresa = _empresa()
    conta = _conta(empresa, "3.9", "Conta", PL, C)
    conta.classificacao_dlpa = dlpa
    conta.classificacao_dmpl = PROPOSTO
    with pytest.raises(ValidationError, match="DLPA"):
        conta.full_clean()


def test_g1_a_coluna_nova_tem_grupo_e_so_aceita_conta_de_patrimonio_liquido():
    from apps.contabilidade.models import (
        GRUPO_DA_CLASSIFICACAO_DMPL,
        TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL,
    )

    assert GRUPO_DA_CLASSIFICACAO_DMPL[PROPOSTO] == GrupoDaDmpl.DEMAIS_CONTAS_EXIGIDAS
    assert TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL[PROPOSTO] == (TipoConta.PATRIMONIO_LIQUIDO,)
    empresa = _empresa()
    passivo = _conta(empresa, "2.9", "Dividendos a Pagar", TipoConta.PASSIVO, C)
    passivo.classificacao_dmpl = PROPOSTO
    with pytest.raises(ValidationError, match="não é compatível com o tipo"):
        passivo.full_clean()


def test_g1_conta_de_pl_de_dividendo_e_classificavel_e_a_pendencia_some_ao_classificar():
    """N4: a conta de PL com DLPA dividendo e SEM coluna é pendência
    classificável (sem orientação de saída); classificada na coluna nova, a
    pendência some e a DMPL emite."""
    empresa, contas, gestor = _caso_a()
    proposto = _conta(
        empresa,
        "3.20",
        "Dividendo Adicional Proposto",
        PL,
        C,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 3, 31), "Proposta", contas["lucros"], proposto, "2000.00")
    dmpl = _apurar(empresa)
    (pendencia,) = dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]
    assert pendencia["conta"] == "3.20"
    assert pendencia["classificavel"] is True
    assert pendencia["orientacao"] == ""
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False

    classificar_conta_na_dmpl(conta=proposto, classificacao=PROPOSTO, usuario=gestor)
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, LINHA_PROPOSTA, PROPOSTO) == _dec("2000.00")
    _identidade_com_a_dlpa(empresa)


def test_g1_proposta_e_aprovacao_parcial_no_mesmo_lancamento_de_lucros():
    """`D Lucros 5.000 / C Proposto 3.000 / C Dividendos a pagar 2.000`: a
    âncora é a coluna de lucros; 3.000 são proposta e 2.000, dividendos."""
    empresa, contas, _ = _caso_a()
    _contas_com_dividendo_adicional_proposto(empresa, contas)
    _lancar_itens(
        empresa,
        date(2026, 3, 31),
        "Dividendos e proposta",
        [
            (contas["lucros"], "D", "5000.00"),
            (contas["proposto"], "C", "3000.00"),
            (contas["dividendos"], "C", "2000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, LINHA_PROPOSTA, LUCROS) == _dec("-3000.00")
    assert _celula(dmpl, LINHA_PROPOSTA, PROPOSTO) == _dec("3000.00")
    # 10.000 do caso A + 2.000.
    assert _celula(dmpl, LINHA_DIVIDENDOS, LUCROS) == _dec("-12000.00")
    _identidade_com_a_dlpa(empresa)


def test_g1_volta_da_coluna_nova_para_lucros_e_par_sem_regra_e_veta():
    empresa, contas, _ = _caso_a()
    _contas_com_dividendo_adicional_proposto(empresa, contas)
    _lancar(empresa, date(2026, 3, 30), "Proposta", contas["lucros"], contas["proposto"], "900.00")
    volta = _lancar(
        empresa, date(2026, 3, 31), "Desistência", contas["proposto"], contas["lucros"], "400.00"
    )
    dmpl = _apurar(empresa)
    (par,) = dmpl["pendencias"]["pares_de_colunas_sem_regra"]
    assert (par["origem"], par["destino"]) == (PROPOSTO, LUCROS)
    assert par["lancamentos"] == [volta.id]
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # A proposta (o outro sentido) tem regra: só a volta está vetada.
    assert _celula(dmpl, LINHA_PROPOSTA, PROPOSTO) == _dec("900.00")
    # O saldo final não esconde nem inventa: 900 − 400.
    assert dmpl["saldo_final"]["valores"][PROPOSTO] == _dec("500.00")


def test_g1_dividendo_a_pagar_creditando_a_coluna_nova_sem_estorno_e_pendencia():
    """`D Dividendos a pagar / C Proposto`: o dividendo com efeito POSITIVO na
    coluna nova só é a linha de dividendos quando é o estorno da aprovação."""
    empresa, contas, _ = _caso_a()
    _contas_com_dividendo_adicional_proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 31),
        "Desistência",
        contas["dividendos"],
        contas["proposto"],
        "300.00",
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert entrada["conta"] == "2.1" and entrada["coluna"] == "dividendo_adicional_proposto"
    assert "dividendo" in entrada["mensagem"].lower()
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert _celula(dmpl, LINHA_DIVIDENDOS, PROPOSTO) == _dec("0")


def test_g1_estorno_da_aprovacao_no_periodo_volta_a_coluna_nova_e_emite():
    """O estorno é o procedimento de correção: a aprovação (−) e o seu estorno
    (+) ficam na linha "Dividendos", líquido zero, e a coluna nova volta ao
    saldo anterior. O estorno positivo NÃO é pendência (e_estorno)."""
    empresa, contas, _ = _caso_a()
    _contas_com_dividendo_adicional_proposto(empresa, contas)
    _lancar(empresa, date(2026, 3, 20), "Proposta", contas["lucros"], contas["proposto"], "900.00")
    aprovacao = _lancar(
        empresa, date(2026, 3, 25), "Aprovação", contas["proposto"], contas["dividendos"], "900.00"
    )
    estornar_lancamento(aprovacao, data=date(2026, 3, 26))
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, LINHA_DIVIDENDOS, PROPOSTO) == _dec("0.00")
    assert len(_linha(dmpl, LINHA_DIVIDENDOS)["lancamentos"][PROPOSTO]) == 2
    assert dmpl["saldo_final"]["valores"][PROPOSTO] == _dec("900.00")
    _identidade_com_a_dlpa(empresa)


def test_g1_contrapartida_sem_classificacao_na_coluna_nova_e_pendencia_por_conta():
    """`D Caixa / C Proposto`: a coluna nova não decide a linha pela direção
    (como lucros e reservas de lucros). Vira pendência, nunca uma linha."""
    empresa, contas, _ = _caso_a()
    _contas_com_dividendo_adicional_proposto(empresa, contas)
    _lancar(empresa, date(2026, 3, 31), "Aporte", contas["caixa"], contas["proposto"], "100.00")
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert entrada["conta"] == "1.1" and entrada["coluna"] == "dividendo_adicional_proposto"
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_g1_as_pendencias_e_a_ordem_das_linhas_incluem_a_linha_nova_depois_de_dividendos():
    chaves = list(_TITULOS_DAS_LINHAS_DA_DMPL)
    assert chaves.index(LINHA_PROPOSTA) == chaves.index(LINHA_DIVIDENDOS) + 1
    assert chaves[-1] == "saldo_final"


# --- P4 e diferencial DLPA × DMPL com a coluna nova no plano ------------------


def _plano_do_ensaio_com_proposto(empresa):
    contas = _plano_do_ensaio(empresa)
    return _contas_com_dividendo_adicional_proposto(empresa, contas)


_NOMES_COM_PROPOSTO = (*_NOMES_DO_ENSAIO, "proposto")
# Só as contas que podem formar um lançamento DECIDÍVEL com a coluna nova. Com
# o plano inteiro quase todo sorteio com a coluna nova cai em pendência, e o
# ensaio não exerceria a regra: este recorte garante lançamentos emitidos
# (conferido pelos contadores de cada teste).
_NOMES_DO_DIVIDENDO = ("lucros", "prejuizos", "proposto", "dividendos", "reserva_legal", "caixa")


@pytest.mark.parametrize("semente", [20261001, 62, 1234])
def test_g1_p4_com_a_coluna_nova_no_plano_cada_coluna_tem_o_sinal_do_seu_efeito_liquido(
    semente,
):
    movimentos_na_coluna_nova = []

    def _conferir(empresa, itens, dmpl):
        if dmpl["saldo_final"]["valores"][PROPOSTO] != 0:
            movimentos_na_coluna_nova.append(_descrever(itens))
        return _conferir_p4(empresa, itens, dmpl)

    violacoes, emitidas = _ensaiar(
        semente, 150, _conferir, plano=_plano_do_ensaio_com_proposto, nomes=_NOMES_DO_DIVIDENDO
    )
    assert emitidas >= 15, f"ensaio vazio demais: só {emitidas} lançamentos emitíveis"
    assert len(movimentos_na_coluna_nova) >= 3, "o ensaio quase não exercita a coluna nova"
    assert violacoes == [], violacoes[:5]


@pytest.mark.parametrize("semente", [20261001, 62, 1234])
def test_g1_diferencial_dlpa_x_dmpl_com_a_coluna_nova_no_plano_identidade_linha_a_linha(semente):
    exercitou = []

    def _conferir(empresa, itens, dmpl):
        if _linha(dmpl, LINHA_PROPOSTA) is not None:
            exercitou.append(_descrever(itens))
        return _conferir_identidade_com_a_dlpa_se_as_duas_emitem(empresa, itens, dmpl)

    violacoes, emitidas = _ensaiar(
        semente, 150, _conferir, plano=_plano_do_ensaio_com_proposto, nomes=_NOMES_DO_DIVIDENDO
    )
    assert emitidas >= 15
    assert len(exercitou) >= 2, "o ensaio quase não exercita a linha da proposta"
    assert violacoes == [], violacoes[:5]


# ===========================================================================
# G2 — veto do lançamento com eventos opostos na mesma coluna (RC-155)
# ===========================================================================

# Coluna -> (natureza das contas, linha do evento quando o líquido é POSITIVO).
_COLUNAS_DO_G2 = {
    "capital_social": (C, "aumento_de_capital"),
    "agio_na_emissao_de_acoes": (C, "constituicao_de_reservas_de_capital"),
    "alienacao_de_partes_beneficiarias_e_bonus_de_subscricao": (
        C,
        "constituicao_de_reservas_de_capital",
    ),
    "ajustes_de_avaliacao_patrimonial": (C, "outros_resultados_abrangentes"),
    "acoes_ou_quotas_em_tesouraria": (
        D,
        "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria",
    ),
}


def _empresa_do_g2(coluna):
    """O caso A mais DUAS contas na coluna pedida (`a` e `b`)."""
    empresa, contas, _ = _caso_a()
    natureza, _linha_positiva = _COLUNAS_DO_G2[coluna]
    contas["a"] = _conta(
        empresa, "3.30", "Conta A da coluna", PL, natureza, dmpl=coluna, pai=contas["pl"]
    )
    contas["b"] = _conta(
        empresa, "3.31", "Conta B da coluna", PL, natureza, dmpl=coluna, pai=contas["pl"]
    )
    return empresa, contas


def _eventos_da_coluna_no_periodo(dmpl, coluna):
    """As linhas de evento com valor na coluna (sem os saldos)."""
    return {
        x["chave"]: x["valores"][coluna]
        for x in dmpl["linhas"]
        if x["chave"] not in ("saldo_inicial", "saldo_final") and x["valores"][coluna] != 0
    }


def _variacao_da_coluna(dmpl, coluna):
    """Saldo final menos o inicial: a coluna do capital já tem o saldo do caso A."""
    return dmpl["saldo_final"]["valores"][coluna] - dmpl["saldo_inicial"]["valores"][coluna]


def _afirmar_vetado(empresa, lancamento, coluna):
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["lancamentos_ambiguos"]
    assert entrada["lancamento_id"] == lancamento.id
    assert ClassificacaoDmpl(coluna).label in entrada["colunas"]
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # Nenhuma célula foi decidida para a coluna (o líquido não vira linha) e
    # o lançamento não aparece como origem de nada.
    assert _eventos_da_coluna_no_periodo(dmpl, coluna) == {}
    for linha in dmpl["linhas"]:
        assert lancamento.id not in sum(linha["lancamentos"].values(), [])
    return dmpl


@pytest.mark.parametrize("coluna", list(_COLUNAS_DO_G2))
def test_g2_mesma_conta_a_debito_e_a_credito_com_externa_so_de_um_lado_e_vetado(coluna):
    """Condição (b) sozinha: `D A 200 / D Caixa 800 / C A 1.000` — a mesma
    conta nos dois lados; a externa só de um (a condição (a) NÃO vale)."""
    empresa, c = _empresa_do_g2(coluna)
    lancamento = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Redução e aumento na mesma conta",
        [(c["a"], "D", "200.00"), (c["caixa"], "D", "800.00"), (c["a"], "C", "1000.00")],
    )
    dmpl = _afirmar_vetado(empresa, lancamento, coluna)
    # O saldo final continua certo: a pendência não esconde nem inventa saldo.
    assert _variacao_da_coluna(dmpl, coluna) == _dec("800.00")


@pytest.mark.parametrize("coluna", list(_COLUNAS_DO_G2))
def test_g2_externas_nos_dois_lados_com_contas_diferentes_na_coluna_e_vetado(coluna):
    """Condição (a) sozinha: `D A 1.500 / D Caixa 1.000 / C Caixa 1.500 / C B
    1.000` — contas DIFERENTES da coluna; as externas nos dois lados."""
    empresa, c = _empresa_do_g2(coluna)
    lancamento = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta",
        [
            (c["a"], "D", "1500.00"),
            (c["caixa"], "D", "1000.00"),
            (c["caixa"], "C", "1500.00"),
            (c["b"], "C", "1000.00"),
        ],
    )
    dmpl = _afirmar_vetado(empresa, lancamento, coluna)
    assert _variacao_da_coluna(dmpl, coluna) == _dec("-500.00")


@pytest.mark.parametrize("coluna", list(_COLUNAS_DO_G2))
def test_g2_subscricao_com_integralizacao_parcial_continua_liquida_sem_veto(coluna):
    """`D Caixa 500 / D B 500 / C A 1.000`: contas diferentes na coluna e a
    externa de um lado só — nem (a) nem (b). O líquido (+500) vira a linha da
    coluna, sem pendência (para o capital: aumento de capital de 500,00)."""
    empresa, c = _empresa_do_g2(coluna)
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Subscrição com integralização parcial",
        [(c["caixa"], "D", "500.00"), (c["b"], "D", "500.00"), (c["a"], "C", "1000.00")],
    )
    dmpl = _apurar(empresa)
    assert _pendencias_nao_vazias(dmpl) == set()
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _eventos_da_coluna_no_periodo(dmpl, coluna) == {
        _COLUNAS_DO_G2[coluna][1]: _dec("500.00")
    }


@pytest.mark.parametrize("coluna", list(_COLUNAS_DO_G2))
def test_g2_coluna_so_de_um_lado_com_externas_nos_dois_lados_nao_e_vetada(coluna):
    """`D Caixa 1.800 / C A 1.500 / C Receita 300`: as externas estão nos dois
    lados, mas a coluna só tem crédito — não há evento oposto nela."""
    empresa, c = _empresa_do_g2(coluna)
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Venda com ganho",
        [
            (c["caixa"], "D", "1800.00"),
            (c["a"], "C", "1500.00"),
            (c["receita"], "C", "300.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert "lancamentos_ambiguos" not in _pendencias_nao_vazias(dmpl)
    assert _eventos_da_coluna_no_periodo(dmpl, coluna) == {
        _COLUNAS_DO_G2[coluna][1]: _dec("1500.00")
    }


def test_g2_exemplo_1_do_plano_compra_e_venda_de_tesouraria_no_mesmo_lancamento():
    """`D Tesouraria 1.500 / D Caixa 1.000 / C Caixa 1.500 / C Tesouraria
    1.000`: veto. A compra (1.500) e a venda (1.000) não viram "Aquisição
    (500)"."""
    empresa, contas, _ = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    permuta = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    dmpl = _afirmar_vetado(empresa, permuta, "acoes_ou_quotas_em_tesouraria")
    assert dmpl["saldo_final"]["valores"]["acoes_ou_quotas_em_tesouraria"] == _dec("-500.00")
    assert "aquisicao_de_acoes_ou_quotas_em_tesouraria" not in _chaves_das_linhas(dmpl)


def test_g2_exemplo_2_do_plano_reducao_e_aumento_de_capital_na_mesma_conta():
    """`D Capital 200 / D Caixa 800 / C Capital 1.000`: veto — não vira
    "Aumento de capital 800,00"."""
    empresa, contas, _ = _caso_a()
    lancamento = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Redução e aumento",
        [
            (contas["capital"], "D", "200.00"),
            (contas["caixa"], "D", "800.00"),
            (contas["capital"], "C", "1000.00"),
        ],
    )
    dmpl = _afirmar_vetado(empresa, lancamento, "capital_social")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100800.00")
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)


def test_g2_exemplo_3_do_plano_subscricao_com_integralizacao_parcial_e_aumento_de_500():
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
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Subscrição com integralização parcial",
        [
            (contas["caixa"], "D", "500.00"),
            (a_integralizar, "D", "500.00"),
            (contas["capital"], "C", "1000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert _pendencias_nao_vazias(dmpl) == set()
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("500.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100500.00")


def test_g2_o_veto_das_reservas_de_lucros_n7_continua_como_estava():
    """O N7 não muda: reserva de lucros debitada e creditada com outra partida
    vetada, e lucros acumulados com D e C continua sem veto (a DLPA soma)."""
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


def test_g2_a_mensagem_do_veto_nao_manda_dividir_o_lancamento_e_aponta_a_saida():
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Redução e aumento",
        [
            (contas["capital"], "D", "200.00"),
            (contas["caixa"], "D", "800.00"),
            (contas["capital"], "C", "1000.00"),
        ],
    )
    (entrada,) = _apurar(empresa)["pendencias"]["lancamentos_ambiguos"]
    mensagem = entrada["mensagem"]
    assert "divida o lançamento" not in mensagem.lower()
    assert "efetivado não se altera" in mensagem
    assert "estorne-o e lance de novo cada evento em um lançamento separado" in mensagem
    assert "fatia 2" in mensagem and "marcação manual" in mensagem


# ===========================================================================
# G3 — a saída pelo estorno (M3)
# ===========================================================================


def _empresa_com_tesouraria():
    empresa, contas, gestor = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    return empresa, contas, gestor


def _permuta_de_tesouraria(empresa, contas, data=date(2026, 2, 5)):
    """O misto do G2 (exemplo 1): vetado."""
    return _lancar_itens(
        empresa,
        data,
        "Permuta",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )


def test_g3_lancamento_vetado_estornado_e_relancado_em_dois_emite_com_os_valores_certos():
    empresa, contas, _ = _empresa_com_tesouraria()
    permuta = _permuta_de_tesouraria(empresa, contas)
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is False

    estorno = estornar_lancamento(permuta, data=date(2026, 2, 6))
    dmpl = _apurar(empresa)
    # O par (L + E) saiu junto: nada pendente, nada em tesouraria, e nenhum dos
    # dois aparece como origem de célula.
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert dmpl["saldo_final"]["valores"]["acoes_ou_quotas_em_tesouraria"] == _dec("0")
    for linha in dmpl["linhas"]:
        origens = sum(linha["lancamentos"].values(), [])
        assert permuta.id not in origens and estorno.id not in origens

    # Relança cada evento em lançamento próprio: aquisição de 1.500 e venda de 1.000.
    _lancar(
        empresa, date(2026, 2, 7), "Aquisição", contas["tesouraria"], contas["caixa"], "1500.00"
    )
    _lancar(empresa, date(2026, 2, 8), "Venda", contas["caixa"], contas["tesouraria"], "1000.00")
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    aquisicao = "aquisicao_de_acoes_ou_quotas_em_tesouraria"
    alienacao = "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria"
    tesouraria = "acoes_ou_quotas_em_tesouraria"
    assert _celula(dmpl, aquisicao, tesouraria) == _dec("-1500.00")
    assert _celula(dmpl, alienacao, tesouraria) == _dec("1000.00")
    assert dmpl["saldo_final"]["valores"][tesouraria] == _dec("-500.00")
    # 100.000 + 25.000 − 1.250 (reserva é interna) − 10.000 − 500 = 114.500.
    assert dmpl["saldo_final"]["total"] == _dec("114500.00")
    assert dmpl["conciliacao"]["total"]["diferenca"] == _dec("0")
    _identidade_com_a_dlpa(empresa)


def test_g3_dividendo_positivo_em_reserva_vetado_estornado_e_relancado_emite():
    empresa, contas, _ = _caso_a()
    pendente = _lancar(
        empresa,
        date(2026, 3, 20),
        "Dividendo a pagar para reserva",
        contas["dividendos"],
        contas["reserva_legal"],
        "1000.00",
    )
    assert "contrapartidas_sem_classificacao" in _pendencias_nao_vazias(_apurar(empresa))

    estornar_lancamento(pendente, data=date(2026, 3, 21))
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("1250.00")
    assert _celula(dmpl, LINHA_DIVIDENDOS, "reserva_legal") == _dec("0")

    # Relança o evento de verdade: a reconstituição da reserva com lucros.
    _lancar(
        empresa,
        date(2026, 3, 22),
        "Reconstituição da reserva",
        contas["lucros"],
        contas["reserva_legal"],
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, "constituicao_de_reservas", "reserva_legal") == _dec("2250.00")
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-2250.00")
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("2250.00")
    assert dmpl["saldo_final"]["valores"][LUCROS] == _dec("12750.00")
    _identidade_com_a_dlpa(empresa)


def test_g3_ambiguo_de_reserva_liberado_pelo_estorno_e_o_limite_da_identidade_por_linha():
    """O N7 (reserva debitada e creditada com lucros) é liberado pelo estorno:
    a DMPL emite e os SALDOS e a soma de todas as linhas seguem idênticos à
    DLPA. **Limite declarado:** a DLPA lê a reserva item a item e divide por
    direção, então mostra o par L + E como duas linhas opostas de reserva
    (reversão 600 / transferência 600, líquido zero) que a DMPL, ao tirar o
    par, não mostra. É o mesmo defeito da DLPA da BL-622 (M1), fora do escopo
    do DL-062. Se a DLPA passar a tirar o par, este teste deve passar a exigir
    a identidade linha a linha."""
    empresa, contas, _ = _caso_a()
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Reserva debitada e creditada",
        [
            (contas["reserva_legal"], "D", "300.00"),
            (contas["reserva_legal"], "C", "100.00"),
            (contas["lucros"], "C", "200.00"),
        ],
    )
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(_apurar(empresa))
    estornar_lancamento(ambiguo, data=date(2026, 3, 21))
    _lancar(
        empresa, date(2026, 3, 22), "Reversão", contas["reserva_legal"], contas["lucros"], "200.00"
    )
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, "reversao_de_reservas", LUCROS) == _dec("200.00")
    assert dmpl["saldo_inicial"]["valores"][LUCROS] == dlpa["saldo_inicial"]
    assert dmpl["saldo_final"]["valores"][LUCROS] == dlpa["saldo_final"]
    esperado, encontrado = comparar_lucros_da_dmpl_com_as_linhas_da_dlpa(dlpa, dmpl)
    assert sum(esperado.values()) == sum(encontrado.values())
    assert esperado != encontrado  # o limite declarado acima


def test_g3_estorno_depois_da_data_final_o_lancamento_conta_sozinho_e_o_veto_persiste():
    empresa, contas, _ = _empresa_com_tesouraria()
    permuta = _permuta_de_tesouraria(empresa, contas, data=date(2026, 3, 20))
    estornar_lancamento(permuta, data=date(2026, 4, 2))  # depois de 31/03

    marco = _apurar(empresa, mes=3)
    (entrada,) = marco["pendencias"]["lancamentos_ambiguos"]
    assert entrada["lancamento_id"] == permuta.id
    assert avaliar_emissao_da_dmpl(marco)["pode_emitir"] is False
    # O saldo de março ainda tem o líquido do lançamento isolado.
    assert marco["saldo_final"]["valores"]["acoes_ou_quotas_em_tesouraria"] == _dec("-500.00")

    # Em abril o par inteiro está no período: liberado.
    abril = _apurar(empresa, mes=4)
    assert avaliar_emissao_da_dmpl(abril)["pode_emitir"] is True, abril["pendencias"]
    assert abril["saldo_final"]["valores"]["acoes_ou_quotas_em_tesouraria"] == _dec("0")


def test_g3_original_no_exercicio_anterior_e_estorno_no_periodo_o_estorno_conta_sozinho():
    """O par só sai quando os DOIS caem no período: o original de 2025 já está
    no saldo inicial, e o estorno de 2026 é movimento do exercício."""
    empresa, contas = _empresa_com_tesouraria()[:2]
    permuta = _permuta_de_tesouraria(empresa, contas, data=date(2025, 11, 20))
    estornar_lancamento(permuta, data=date(2026, 2, 10))
    dmpl = _apurar(empresa)
    tesouraria = "acoes_ou_quotas_em_tesouraria"
    assert dmpl["saldo_inicial"]["valores"][tesouraria] == _dec("-500.00")
    assert dmpl["saldo_final"]["valores"][tesouraria] == _dec("0")
    estorno_id = permuta.estornos.get().id
    # O estorno, sozinho no período, é o misto invertido: vetado pelo mesmo
    # motivo do original. Nenhum par o tirou da atribuição.
    ids_ambiguos = [e["lancamento_id"] for e in dmpl["pendencias"]["lancamentos_ambiguos"]]
    assert ids_ambiguos == [estorno_id]


def test_g3_par_que_a_regra_decide_mantem_as_duas_pontas_e_a_identidade_com_a_dlpa():
    """A constituição de reserva estornada continua "constituição" e
    "reversão" (as duas pontas): a DLPA divide as reservas por direção, e tirar
    o par decidido quebraria a identidade linha a linha."""
    empresa, contas, _ = _caso_a()
    constituicao = _lancar(
        empresa,
        date(2026, 3, 31),
        "Outra reserva",
        contas["lucros"],
        contas["reserva_legal"],
        "400.00",
    )
    estornar_lancamento(constituicao, data=date(2026, 3, 31))
    dlpa, dmpl = _identidade_com_a_dlpa(empresa)
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-1650.00")
    assert _celula(dmpl, "reversao_de_reservas", LUCROS) == _dec("400.00")
    assert {x["chave"] for x in dlpa["linhas"]} >= {
        "transferencia:reserva_legal",
        "reversao:reserva_legal",
    }


def test_g3_estorno_que_nao_e_o_inverso_exato_nao_neutraliza_o_par():
    """Defesa: o par só sai se a soma dos dois for ZERO em toda coluna. O livro
    é imutável por trigger, então o estorno "adulterado" é construído por
    `criar_lancamento(estorno_de=...)` com itens que NÃO invertem o original
    (100,00 passam do caixa para a tesouraria): o par não é neutralizado e o veto do
    original persiste."""
    empresa, contas, _ = _empresa_com_tesouraria()
    permuta = _permuta_de_tesouraria(empresa, contas)
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 2, 6),
        historico="Estorno parcial (não é o inverso exato)",
        itens=[
            {"conta": contas["caixa"], "tipo": TipoPartida.DEBITO, "valor": _dec("1500.00")},
            {"conta": contas["tesouraria"], "tipo": TipoPartida.DEBITO, "valor": _dec("1000.00")},
            {"conta": contas["caixa"], "tipo": TipoPartida.CREDITO, "valor": _dec("1100.00")},
            {"conta": contas["tesouraria"], "tipo": TipoPartida.CREDITO, "valor": _dec("1400.00")},
        ],
        estorno_de=permuta,
    )
    dmpl = _apurar(empresa)
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_g3_o_estorno_exato_e_reconhecido_item_a_item():
    """Unidade de `_e_o_estorno_exato`: troca de lado, mesmas contas e valores,
    e a multiplicidade conta (dois itens iguais não são um)."""
    from types import SimpleNamespace as Item

    deb, cred = TipoPartida.DEBITO, TipoPartida.CREDITO
    original = [
        Item(conta_id=1, tipo=deb, valor=_dec("10.00")),
        Item(conta_id=2, tipo=cred, valor=_dec("10.00")),
    ]
    inverso = [
        Item(conta_id=1, tipo=cred, valor=_dec("10.0")),
        Item(conta_id=2, tipo=deb, valor=_dec("10.00")),
    ]
    assert _e_o_estorno_exato(original, inverso) is True
    assert _e_o_estorno_exato(original, original) is False  # sem trocar os lados
    assert _e_o_estorno_exato(original, inverso[:1]) is False
    assert _e_o_estorno_exato(original, [*inverso, inverso[0]]) is False
    outro_valor = [Item(conta_id=1, tipo=cred, valor=_dec("11.00")), inverso[1]]
    assert _e_o_estorno_exato(original, outro_valor) is False
    outra_conta = [Item(conta_id=3, tipo=cred, valor=_dec("10.00")), inverso[1]]
    assert _e_o_estorno_exato(original, outra_conta) is False


def test_g3_as_mensagens_novas_nao_mandam_dividir_o_lancamento():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Dividendo a pagar para reserva",
        contas["dividendos"],
        contas["reserva_legal"],
        "1000.00",
    )
    _lancar_itens(
        empresa,
        date(2026, 3, 21),
        "Reserva debitada e creditada",
        [
            (contas["reserva_legal"], "D", "300.00"),
            (contas["reserva_legal"], "C", "100.00"),
            (contas["lucros"], "C", "200.00"),
        ],
    )
    dmpl = _apurar(empresa)
    mensagens = [e["mensagem"] for e in dmpl["pendencias"]["contrapartidas_sem_classificacao"]]
    mensagens += [e["mensagem"] for e in dmpl["pendencias"]["lancamentos_ambiguos"]]
    assert len(mensagens) == 2
    for mensagem in mensagens:
        texto = mensagem.lower()
        assert "divida o lançamento" not in texto
        assert "estorne o dividendo original" not in texto
        assert "efetivado não se altera" in texto
        assert "estorne-o e lance de novo cada evento em um lançamento separado" in texto
        assert "fatia 2" in texto and "marcação manual" in texto


# --- propriedade: qualquer lançamento é liberado pelo seu estorno -----------


@pytest.mark.parametrize("semente", [20261001, 62, 1234])
def test_g3_propriedade_o_estorno_no_periodo_libera_qualquer_lancamento(semente):
    """Para lançamentos aleatórios (semente fixa, plano ampliado com a coluna
    nova): L e o seu estorno E, ambos no período, SEMPRE emitem, nenhuma coluna
    muda de saldo, e — quando a DLPA também emite — a coluna de lucros segue
    idêntica a ela."""
    rnd = random.Random(semente)
    empresa = _empresa(f"G3 {semente}")
    contas = _plano_do_ensaio_com_proposto(empresa)
    vetados_antes = 0
    com_dlpa_item_a_item = 0
    violacoes = []
    for _ in range(80):
        itens = _itens_aleatorios(rnd, contas, _NOMES_COM_PROPOSTO)
        with transaction.atomic():
            original = _lancar_itens(empresa, date(2026, 2, 10), "ensaio", itens)
            antes = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)
            if not avaliar_emissao_da_dmpl(antes)["pode_emitir"]:
                vetados_antes += 1
            estornar_lancamento(original, data=date(2026, 2, 11))
            dmpl = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)
            emissao = avaliar_emissao_da_dmpl(dmpl)
            if not emissao["pode_emitir"]:
                violacoes.append(("veto", _descrever(itens), emissao["motivos"]))
            for coluna, final in dmpl["saldo_final"]["valores"].items():
                if final != dmpl["saldo_inicial"]["valores"][coluna]:
                    violacoes.append(("saldo", coluna, _descrever(itens)))
            dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
            if avaliar_emissao_da_dlpa(dlpa)["pode_emitir"]:
                if dmpl["saldo_final"]["valores"][LUCROS] != dlpa["saldo_final"]:
                    violacoes.append(("saldo_da_dlpa", _descrever(itens)))
                esperado, encontrado = comparar_lucros_da_dmpl_com_as_linhas_da_dlpa(dlpa, dmpl)
                if esperado != encontrado:
                    # Limite declarado (teste do ambíguo de reserva): a DLPA lê
                    # a reserva item a item e mostra o par como linhas opostas
                    # de líquido zero. Só vale para o lançamento que a DMPL
                    # vetou como ambíguo; qualquer outra diferença é violação.
                    so_o_par_da_dlpa = (
                        "lancamentos_ambiguos" in _pendencias_nao_vazias(antes)
                        and sum(esperado.values()) == sum(encontrado.values()) == 0
                    )
                    if so_o_par_da_dlpa:
                        com_dlpa_item_a_item += 1
                    else:
                        violacoes.append(("identidade", _descrever(itens), esperado, encontrado))
            transaction.set_rollback(True)
    assert vetados_antes >= 10, f"o ensaio vetou só {vetados_antes} lançamentos antes do estorno"
    assert com_dlpa_item_a_item <= 4, "a exceção declarada ficou frequente demais"
    assert violacoes == [], violacoes[:5]


def test_g3_o_estorno_fora_do_periodo_nunca_libera_qualquer_lancamento_vetado():
    """Contraprova da propriedade: com o estorno DEPOIS da data final, todo
    lançamento vetado continua vetado."""
    rnd = random.Random(62)
    empresa = _empresa("G3 fora do período")
    contas = _plano_do_ensaio_com_proposto(empresa)
    vetados = 0
    liberados = []
    for _ in range(60):
        itens = _itens_aleatorios(rnd, contas, _NOMES_COM_PROPOSTO)
        with transaction.atomic():
            original = _lancar_itens(empresa, date(2026, 2, 10), "ensaio", itens)
            antes = avaliar_emissao_da_dmpl(apurar_dmpl(empresa=empresa, ano=ANO, mes=MES))
            estornar_lancamento(original, data=date(2026, 4, 5))
            depois = avaliar_emissao_da_dmpl(apurar_dmpl(empresa=empresa, ano=ANO, mes=MES))
            if not antes["pode_emitir"]:
                vetados += 1
                if depois["pode_emitir"]:
                    liberados.append(_descrever(itens))
            transaction.set_rollback(True)
    assert vetados >= 8
    assert liberados == []
