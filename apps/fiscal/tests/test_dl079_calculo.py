"""DL-079, critérios 1, 2, 3, 4 e 10: cálculo puro do IRPJ e da CSLL com o acréscimo da LC 224.

Os VALORES ESPERADOS são escritos à mão, com a conta no comentário. Nenhum teste
reaproveita a função
de produção para calcular o próprio resultado (AGENTS.md §7). Fonte: consulta de 08/10/2026, itens 1
a 4 (P&R da RFB, item 11 e 14; IN 2.305, art. 15).

Convenção: "base" é a base de cálculo; "imposto" é o IRPJ (15% + adicional) ou a CSLL (9%).
"""

from decimal import Decimal as D

import pytest

from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
SERVICOS = tab.SERVICOS_GERAIS


def periodo(trimestre, comercio=None, servicos=None, integrais="0", meses=3, em_atividade=True):
    receitas = []
    if comercio is not None:
        receitas.append((COMERCIO, D(comercio)))
    if servicos is not None:
        receitas.append((SERVICOS, D(servicos)))
    return calc.PeriodoTrimestre(
        trimestre=trimestre,
        receitas=tuple(receitas),
        integrais=D(integrais),
        meses=meses,
        em_atividade=em_atividade,
    )


def exemplo_consulta_2026():
    """Receitas do exemplo de quatro trimestres (consulta, item 4).

    Integrais: T2 12.000; T4 8.000.
    """
    return [
        periodo(1, "600000", "300000"),
        periodo(2, "1200000", "700000", integrais="12000"),
        periodo(3, "800000", "400000"),
        periodo(4, "1000000", "500000", integrais="8000"),
    ]


# ---------------------------------------------------------------------------
# Critério 1: exemplo oficial do P&R (item 11) e exemplo de quatro trimestres (item 4)
# ---------------------------------------------------------------------------


def test_exemplo_oficial_do_pr_item_11_base_de_122_mil():
    # Comércio, R$ 1.500.000 no trimestre. Limite de R$ 1.250.000 sem excedente acima dele;
    # excedente
    # E = 250.000. Normal: (1.500.000 − 250.000) × 8% = 1.250.000 × 0,08 = 100.000,00.
    # Acrescido: 250.000 × 8% × 1,10 = 250.000 × 0,088 = 22.000,00. Base = 100.000 + 22.000 =
    # 122.000,00.
    apuracao = calc.apurar_ano(
        tab.IRPJ, 2026, [periodo(1, "1500000"), periodo(2), periodo(3), periodo(4)]
    )
    trimestre_1 = apuracao.linhas[0]
    assert trimestre_1.excedente == D("250000.00")
    assert trimestre_1.com_lc224.base == D("122000.00")
    assert trimestre_1.com_lc224.linhas[0].base_normal == D("100000.00")
    assert trimestre_1.com_lc224.linhas[0].base_acrescida == D("22000.00")


def test_exemplo_de_quatro_trimestres_irpj_linha_a_linha():
    # T1: R 900.000 (comércio 600.000 + serviços 300.000). L = 1.250.000 (sem sobra). E = 0.
    #     Base = 600.000 × 8% + 300.000 × 32% = 48.000 + 96.000 = 144.000,00.
    # IRPJ = 15% × 144.000 = 21.600,00 + adicional 10% × (144.000 − 60.000) = 8.400,00 → 30.000,00.
    # T2: R 1.900.000 (1.200.000 + 700.000), integrais 12.000. L = 1.250.000 + 350.000 (sobra de T1)
    # =
    # 1.600.000. E = 300.000, rateado: comércio 300.000 × 1.200/1.900 = 189.473,68; serviços
    # 110.526,32.
    # Base (linhas): comércio normal 1.010.526,32 × 8% = 80.842,11; comércio acrescido 189.473,68 ×
    # 8,8%
    # = 16.673,68; serviços normal 589.473,68 × 32% = 188.631,58; serviços acrescido 110.526,32 ×
    # 35,2%
    #     = 38.905,26. Soma 325.052,63 + integrais 12.000 = 337.052,63.
    # IRPJ = 15% × 337.052,63 = 50.557,89 (arredondado) + 10% × (337.052,63 − 60.000) = 27.705,26 →
    # 78.263,15.
    #     Sem LC 224: 1.200.000 × 8% + 700.000 × 32% + 12.000 = 96.000 + 224.000 + 12.000 = 332.000;
    # IRPJ = 49.800 + 10% × 272.000 = 27.200 → 77.000,00. Parcela = 78.263,15 − 77.000,00 =
    # 1.263,15.
    # T3: R 1.200.000. L = 1.250.000 (sobra de T2 é zero). Base = 800.000 × 8% + 400.000 × 32% =
    # 64.000 +
    #     128.000 = 192.000,00. IRPJ = 28.800 + 10% × 132.000 = 13.200 → 42.000,00.
    # T4: R 1.500.000, integrais 8.000. L = 1.250.000 + 50.000 (sobra de T3) = 1.300.000. E =
    # 200.000.
    # Base: 1.000.000 × 8% + 500.000 × 32% = 80.000 + 160.000 = 240.000 sem LC; com LC, E rateado
    # 133.333,33 (comércio) e 66.666,67 (serviços): 866.666,67 × 8% = 69.333,33 + 133.333,33 × 8,8%
    # = 11.733,33 + 433.333,33 × 32% = 138.666,67 + 66.666,67 × 35,2% = 23.466,67 → 243.200,00 +
    # 8.000 =
    # 251.200,00. IRPJ = 37.680 + 10% × 191.200 = 19.120 → 56.800,00. Sem LC: 248.000 → 56.000,00.
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, exemplo_consulta_2026())
    t1, t2, t3, t4 = apuracao.linhas
    assert t1.limite == D("1250000.00") and t1.excedente == D("0.00")
    assert t1.com_lc224.base == D("144000.00") and t1.com_lc224.total == D("30000.00")

    assert t2.limite == D("1600000.00") and t2.excedente == D("300000.00")
    assert t2.com_lc224.base == D("337052.63")
    assert t2.com_lc224.total == D("78263.15")
    assert t2.sem_lc224.total == D("77000.00")
    assert t2.parcela_lc224 == D("1263.15")
    comercio_t2, servicos_t2 = t2.com_lc224.linhas
    assert comercio_t2.excedente == D("189473.68")
    assert comercio_t2.base_normal == D("80842.11")
    assert comercio_t2.base_acrescida == D("16673.68")
    assert servicos_t2.excedente == D("110526.32")  # resíduo na última atividade
    assert servicos_t2.base_normal == D("188631.58")
    assert servicos_t2.base_acrescida == D("38905.26")

    assert t3.com_lc224.base == D("192000.00") and t3.com_lc224.total == D("42000.00")

    assert t4.limite == D("1300000.00") and t4.excedente == D("200000.00")
    assert t4.com_lc224.base == D("251200.00") and t4.com_lc224.total == D("56800.00")
    assert t4.sem_lc224.total == D("56000.00")
    assert t4.parcela_lc224 == D("800.00")

    assert apuracao.fechamento.n == 4
    assert apuracao.fechamento.excedente_anual == D("500000.00")  # 5.500.000 − 5.000.000
    assert apuracao.fechamento.s == D("300000.00")  # E1 + E2 + E3
    assert apuracao.fechamento.caso == calc.CASO_III
    assert apuracao.deducao_quarto_trimestre == D("0.00")


def test_exemplo_de_quatro_trimestres_csll_linha_a_linha():
    # T1: sem acréscimo (CSLL começa em 01/04/2026). Base = 600.000 × 12% + 300.000 × 32% = 72.000 +
    #     96.000 = 168.000,00. CSLL = 9% × 168.000 = 15.120,00. Fora de N e sem sobra para T2.
    # T2: L = 1.250.000 (sem sobra de T1). E = 650.000 (R 1.900.000). Rateio: comércio 410.526,32;
    # serviços
    # 239.473,68. Normal comércio 789.473,68 × 12% = 94.736,84; acrescido 410.526,32 × 13,2% =
    # 54.189,47;
    #     normal serviços 460.526,32 × 32% = 147.368,42; acrescido 239.473,68 × 35,2% = 84.294,74.
    #     Soma 380.589,47 + integrais 12.000 = 392.589,47. CSLL = 9% × 392.589,47 = 35.333,05.
    # T3: R 1.200.000, sem excedente. Base 800.000 × 12% + 400.000 × 32% = 96.000 + 128.000 =
    # 224.000,00.
    #     CSLL = 20.160,00.
    # T4: L = 1.250.000 + 50.000 = 1.300.000. E = 200.000. Base: comércio 866.666,67 × 12% =
    # 104.000,00,
    # acrescido 133.333,33 × 13,2% = 17.600,00; serviços 433.333,33 × 32% = 138.666,67, acrescido
    #     66.666,67 × 35,2% = 23.466,67 → 283.733,34 + 8.000 = 291.733,34. CSLL = 9% = 26.256,00.
    # Fechamento: N = 3 (T2 a T4); Σ R = 4.600.000; ExcAnual = 4.600.000 − 3.750.000 = 850.000;
    # S = 650.000 → caso III (ExcAnual ≥ S). E4 = 850.000 − 650.000 = 200.000.
    apuracao = calc.apurar_ano(tab.CSLL, 2026, exemplo_consulta_2026())
    t1, t2, t3, t4 = apuracao.linhas
    assert t1.em_acrescimo is False and t1.com_lc224 is None
    assert t1.sem_lc224.base == D("168000.00") and t1.sem_lc224.total == D("15120.00")
    assert t2.limite == D("1250000.00")  # sem sobra de T1 (a CSLL não começou no 1º trimestre)
    assert t2.excedente == D("650000.00")
    assert t2.com_lc224.base == D("392589.47") and t2.com_lc224.total == D("35333.05")
    assert t3.com_lc224.base == D("224000.00") and t3.com_lc224.total == D("20160.00")
    assert t4.limite == D("1300000.00") and t4.excedente == D("200000.00")
    assert t4.com_lc224.base == D("291733.34") and t4.com_lc224.total == D("26256.00")
    assert apuracao.fechamento.n == 3
    assert apuracao.fechamento.excedente_anual == D("850000.00")
    assert apuracao.fechamento.s == D("650000.00")
    assert apuracao.fechamento.caso == calc.CASO_III


# ---------------------------------------------------------------------------
# Critério 2: os três casos do 4º trimestre, com o valor esperado à mão
# ---------------------------------------------------------------------------


def test_caso_ii_deducao_e_1100_com_contas_a_mao():
    # T1: comércio 2.000.000 → E1 = 750.000 (L1 = 1.250.000). T2 500.000 → sobra 750.000. T3 500.000
    # →
    # L3 = 2.000.000, sobra 1.500.000. T4 2.200.000 → L4 = 2.750.000 → E4 = 0.
    # Σ R = 5.200.000; ExcAnual = 5.200.000 − 5.000.000 = 200.000. S = E1 + E2 + E3 = 750.000.
    # 0 < 200.000 < 750.000 → caso II. E1' = 750.000 × 200.000 / 750.000 = 200.000.
    # IRPJ de T1 com E = 750.000: base = 1.250.000 × 8% + 750.000 × 8,8% = 100.000 + 66.000 =
    # 166.000;
    #     IRPJ = 24.900 + 10% × (166.000 − 60.000) = 10.600 → 35.500.
    # IRPJ de T1 com E = 200.000: base = 1.800.000 × 8% + 200.000 × 8,8% = 144.000 + 17.600 =
    # 161.600;
    #     IRPJ = 24.240 + 10% × 101.600 = 10.160 → 34.400.
    # Dedução = 35.500 − 34.400 = 1.100,00 (no 4º trimestre). T4 sem excedente: 2.200.000 × 8% =
    # 176.000;
    # IRPJ = 26.400 + 10% × 116.000 = 11.600 → 38.000; a recolher = 38.000 − 1.100 = 36.900,00.
    periodos = [
        periodo(1, "2000000"),
        periodo(2, "500000"),
        periodo(3, "500000"),
        periodo(4, "2200000"),
    ]
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, periodos)
    assert apuracao.fechamento.caso == calc.CASO_II
    assert apuracao.fechamento.excedente_anual == D("200000.00")
    assert apuracao.fechamento.s == D("750000.00")
    assert apuracao.linhas[0].excedente_ajustado == D("200000.00")
    assert apuracao.linhas[0].com_lc224.total == D("35500.00")
    assert apuracao.deducao_quarto_trimestre == D("1100.00")
    t4 = apuracao.linhas[3]
    assert t4.excedente == D("0.00")
    assert t4.sem_lc224.total == D("38000.00")
    assert t4.sem_lc224.total - apuracao.deducao_quarto_trimestre == D("36900.00")


def test_caso_i_deduz_toda_a_parcela_da_lc224_de_t1():
    # T1 2.000.000 → E1 = 750.000. T2 500.000, T3 500.000, T4 1.000.000 (sem excedente em T4).
    # Σ R = 4.000.000 < 5.000.000 → ExcAnual = 0 → caso I. E' = 0 para todos.
    # Parcela de T1 = IRPJ(E = 750.000) − IRPJ(E = 0) = 35.500 − 34.000 = 1.500,00.
    # Sem acréscimo: base 1.250.000... no caso: 2.000.000 × 8% = 160.000; IRPJ = 24.000 + 10% ×
    # 100.000 = 10.000 → 34.000.
    periodos = [
        periodo(1, "2000000"),
        periodo(2, "500000"),
        periodo(3, "500000"),
        periodo(4, "1000000"),
    ]
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, periodos)
    assert apuracao.fechamento.caso == calc.CASO_I
    assert apuracao.fechamento.excedente_anual == D("0.00")
    assert apuracao.linhas[0].parcela_lc224 == D("1500.00")
    assert apuracao.deducao_quarto_trimestre == D("1500.00")


def test_caso_iii_mantem_a_sobra_e_nao_deduz():
    # Mesmo exemplo de quatro trimestres: ExcAnual 500.000 ≥ S 300.000 → caso III, dedução zero, e
    # E4 da sobra (200.000) igual ao ExcAnual − S (500.000 − 300.000). A identidade vale: sem
    # arredondar.
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, exemplo_consulta_2026())
    assert apuracao.fechamento.caso == calc.CASO_III
    assert (
        apuracao.linhas[3].excedente == apuracao.fechamento.excedente_anual - apuracao.fechamento.s
    )
    assert apuracao.deducao_quarto_trimestre == D("0.00")


def test_caso_ii_com_deducao_maior_que_o_devido_no_quarto_trimestre():
    # T1 2.500.000 → E1 = 1.250.000; T2 2.500.000 → L2 = 1.250.000, E2 = 1.250.000; T3 zero → sobra
    # 2.500.000
    # (L3 = 1.250.000 + 1.250.000 − 0 ... ); T4 50.000. Σ R = 5.050.000 → ExcAnual = 50.000.
    # S = E1 + E2 = 2.500.000 → caso II. E1' = E2' = 1.250.000 × 50.000 / 2.500.000 = 25.000.
    # Cada trimestre perde 1.225.000 de E: Δbase comércio = 1.225.000 × 0,008 = 9.800 (8,8% − 8%).
    # ΔIRPJ = 15% × 9.800 + 10% × 9.800 = 1.470 + 980 = 2.450 por trimestre; dedução = 4.900.
    # T4 com 50.000 comércio: base 4.000; IRPJ = 600 (abaixo do adicional). 4.900 > 600.
    periodos = [
        periodo(1, "2500000"),
        periodo(2, "2500000"),
        periodo(3, "0"),
        periodo(4, "50000"),
    ]
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, periodos)
    assert apuracao.fechamento.caso == calc.CASO_II
    assert apuracao.fechamento.excedente_anual == D("50000.00")
    assert apuracao.deducao_quarto_trimestre == D("4900.00")
    assert apuracao.linhas[3].sem_lc224.total == D("600.00")


# ---------------------------------------------------------------------------
# Critério 3: CSLL sem acréscimo no 1º trimestre; IRPJ com acréscimo desde o 1º
# ---------------------------------------------------------------------------


def test_csll_nao_tem_acrescimo_no_primeiro_trimestre_de_2026():
    assert calc.primeiro_trimestre_do_acrescimo(tab.CSLL, 2026) == 2
    assert calc.primeiro_trimestre_do_acrescimo(tab.IRPJ, 2026) == 1
    assert calc.primeiro_trimestre_do_acrescimo(tab.CSLL, 2027) == 1
    assert calc.primeiro_trimestre_do_acrescimo(tab.CSLL, 2025) is None


def test_limite_anual_da_csll_em_2026_e_3_75_milhoes():
    # N = 3 (T2 a T4), 1.250.000 × 3 = 3.750.000. Com 4 trimestres (IRPJ), 5.000.000.
    apuracao = calc.apurar_ano(tab.CSLL, 2026, exemplo_consulta_2026())
    assert apuracao.fechamento.limite_anual == D("3750000.00")
    irpj = calc.apurar_ano(tab.IRPJ, 2026, exemplo_consulta_2026())
    assert irpj.fechamento.limite_anual == D("5000000.00")


# ---------------------------------------------------------------------------
# Critério 10 (partes puras): início de atividade, integrais fora do limite, rateio, adicional
# ---------------------------------------------------------------------------


def test_inicio_de_atividade_no_segundo_trimestre_usa_dois_meses_no_adicional():
    # Abertura em maio: T1 fora da atividade; T2 com 2 meses (maio e junho). N = 3 (T2 a T4).
    # T2: R 1.300.000 → E = 50.000 (L = 1.250.000). Base com LC: 1.250.000 × 8% = 100.000 + 50.000 ×
    # 8,8%
    # = 4.400 → 104.400. IRPJ = 15% × 104.400 = 15.660 + 10% × (104.400 − 2 × 20.000) = 6.440 →
    # 22.100.
    # Sem LC: base 104.000 (1.300.000 × 8%); IRPJ = 15.600 + 10% × 64.000 = 6.400 → 22.000. Parcela
    # = 100.
    periodos = [
        periodo(1, em_atividade=False, meses=0),
        periodo(2, "1300000", meses=2),
        periodo(3, em_atividade=True),
        periodo(4, em_atividade=True),
    ]
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, periodos)
    assert apuracao.fechamento.n == 3
    assert apuracao.fechamento.limite_anual == D("3750000.00")
    t2 = apuracao.linhas[1]
    assert t2.excedente == D("50000.00")
    assert t2.com_lc224.total == D("22100.00")
    assert t2.sem_lc224.total == D("22000.00")
    assert t2.parcela_lc224 == D("100.00")
    assert apuracao.linhas[0].em_acrescimo is False


def test_integrais_nao_entram_no_limite_e_entram_integrais_na_base():
    # R 1.250.000 (comércio) → E = 0 e L = 1.250.000 (integrais de 500.000 NÃO contam no limite).
    # Base = 1.250.000 × 8% + 500.000 = 100.000 + 500.000 = 600.000,00. IRPJ = 90.000 + 10% ×
    # 540.000 = 54.000
    # → 144.000,00. A sobra de T1 é zero, então T2 começa em 1.250.000.
    periodos = [
        periodo(1, "1250000", integrais="500000"),
        periodo(2, "1250000"),
        periodo(3, "0"),
        periodo(4, "0"),
    ]
    apuracao = calc.apurar_ano(tab.IRPJ, 2026, periodos)
    t1 = apuracao.linhas[0]
    assert t1.excedente == D("0.00")
    assert t1.limite == D("1250000.00")
    assert t1.com_lc224.base == D("600000.00")
    assert t1.com_lc224.receitas_integrais == D("500000.00")
    assert t1.com_lc224.total == D("144000.00")


def test_rateio_do_excedente_com_residuo_na_ultima_atividade():
    # E = 100,00 entre R de 1 e 2 (total 3): 100 × 1/3 = 33,33 (arredondado); o resto, 66,67, vai à
    # última.
    rateio = calc.ratear_excedente(D("100.00"), ((COMERCIO, D("1")), (SERVICOS, D("2"))))
    assert rateio == {COMERCIO: D("33.33"), SERVICOS: D("66.67")}
    assert sum(rateio.values()) == D("100.00")


def test_arredondamento_de_linha_e_metade_para_cima():
    # 0,005 deve virar 0,01 (ROUND_HALF_UP). Sem isso a parcela de centavos mudaria.
    assert calc.centavos(D("0.005")) == D("0.01")
    assert calc.centavos(D("0.004")) == D("0.00")
    assert calc.centavos(D("2.345")) == D("2.35")


def test_adicional_do_irpj_e_zero_abaixo_de_20_mil_por_mes():
    # Base de 60.000 num trimestre cheio: limite do adicional = 60.000. Excesso 0 → adicional 0.
    # Principal = 15% × 60.000 = 9.000.
    periodo_pequeno = periodo(1, "750000")  # 750.000 × 8% = 60.000
    imposto = calc.calcular_imposto(tab.IRPJ, periodo_pequeno, D("0"))
    assert imposto.base == D("60000.00")
    assert imposto.principal == D("9000.00")
    assert imposto.adicional == D("0.00")


def test_csll_nao_tem_adicional():
    imposto = calc.calcular_imposto(tab.CSLL, periodo(1, "1000000"), D("0"))
    assert imposto.adicional == D("0.00")
    assert imposto.principal == D("10800.00")  # 1.000.000 × 12% × 9%


def test_fator_de_acrescimo_multiplica_e_nao_soma_pontos():
    # Serviços em geral: 32% vira 35,2% (× 1,10), e NÃO 42% (+ 10 pontos).
    assert tab.ATIVIDADES_POR_CODIGO[SERVICOS].irpj * tab.FATOR_ACRESCIMO_LC224 == D("0.352")
    assert tab.ATIVIDADES_POR_CODIGO[COMERCIO].irpj * tab.FATOR_ACRESCIMO_LC224 == D("0.088")
    assert tab.FATOR_ACRESCIMO_LC224 == D("1.10")


@pytest.mark.parametrize("trimestre", [0, 5])
def test_trimestre_fora_de_1_a_4_nao_passa_pelo_calculo(trimestre):
    # O calculo exige exatamente os quatro trimestres; um trimestre fora disso é erro de
    # programação.
    periodos = [periodo(1), periodo(2), periodo(3), periodo(trimestre)]
    with pytest.raises(ValueError):
        calc.apurar_ano(tab.IRPJ, 2026, periodos)
