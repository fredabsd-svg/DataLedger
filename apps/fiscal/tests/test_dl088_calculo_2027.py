"""DL-088, frente A1: cálculo do pré-DAS de 2027 por tributo, com contas escritas à mão.

Cada teste traz a CONTA no docstring: alíquota efetiva, percentual de cada tributo, valor
arredondado a centavo (ROUND_HALF_UP por tributo, HI-71) e total. O número esperado é o da conta,
não o que o módulo devolve. Sem banco: é o cálculo puro de `calcular_anexo`.

Convenção: receita do segmento em R$, RBT12 em R$, percentuais da tabela de 2027 (consulta de
09/10/2026, seção 1). Efetiva = (RBT12 × alíquota nominal − parcela a deduzir) / RBT12.
"""

from decimal import Decimal

from apps.fiscal import pre_das as motor
from apps.fiscal.models import ANEXO_I, ANEXO_II

D = Decimal


def por_tributo(calculo, indice=0):
    """{tributo: valor} do primeiro segmento (ou do indicado)."""
    return {linha.tributo: linha.valor for linha in calculo.segmentos[indice].linhas}


def desconsiderados(calculo, indice=0):
    return {linha.tributo for linha in calculo.segmentos[indice].linhas if linha.desconsiderado}


def test_comercio_anexo_i_2027_faixa_2_normal():
    """Comércio, Anexo I, RBT12 300.000, venda normal 10.000.

    Faixa 2 (180.000,01 a 360.000): nominal 7,30%, a deduzir 5.940,00.
    Efetiva = (300.000 × 0,073 − 5.940) / 300.000 = 15.960 / 300.000 = 0,0532 (5,32%).
    IRPJ 5,50% → 10.000 × 0,002926 = 29,26 · CSLL 3,50% → 18,62 · CBS 15,33% → 81,5556 → 81,56
    CPP 41,50% → 220,78 · ICMS 34,00% → 180,88 · IBS 0,17% → 0,9044 → 0,90.
    Total: 29,26 + 18,62 + 81,56 + 220,78 + 180,88 + 0,90 = 532,00 (= 5,32% de 10.000).
    """
    calculo = motor.calcular_anexo(ANEXO_I, D("300000"), [("normal", D("10000"))], ano=2027, mes=1)
    assert calculo.faixa.numero == 2
    assert calculo.efetiva == D("0.0532")
    assert por_tributo(calculo) == {
        "IRPJ": D("29.26"),
        "CSLL": D("18.62"),
        "CBS": D("81.56"),
        "CPP": D("220.78"),
        "ICMS": D("180.88"),
        "IBS": D("0.90"),
    }
    assert calculo.total == D("532.00")
    assert desconsiderados(calculo) == set()


def test_comercio_anexo_i_2027_com_regime_regular_deduz_cbs_e_ibs():
    """Mesmo cenário, com a opção pelo regime regular (art. 22-A).

    CBS 81,56 e IBS 0,90 saem do DAS (deduzidos da faixa). Total: 532,00 − 81,56 − 0,90 = 449,54.
    """
    calculo = motor.calcular_anexo(
        ANEXO_I, D("300000"), [("normal", D("10000"))], ano=2027, mes=1, regime_regular=True
    )
    assert por_tributo(calculo) == {
        "IRPJ": D("29.26"),
        "CSLL": D("18.62"),
        "CBS": D("0.00"),
        "CPP": D("220.78"),
        "ICMS": D("180.88"),
        "IBS": D("0.00"),
    }
    assert calculo.total == D("449.54")
    deduzidos = {linha.tributo: linha.deduzido for linha in calculo.segmentos[0].linhas}
    assert deduzidos["CBS"] == D("81.56")
    assert deduzidos["IBS"] == D("0.90")
    assert deduzidos["IRPJ"] == D("0.00")


def test_monofasico_2027_desconsidera_cbs_e_ibs_do_segmento():
    """Tributação concentrada (hipótese de leitura, HI-148): CBS e IBS desconsiderados.

    Mesma conta do comércio normal, sem CBS (81,56) e sem IBS (0,90): 532,00 − 82,46 = 449,54.
    Sem dedução de art. 22-A: é o segmento que sai do DAS, não a opção.
    """
    calculo = motor.calcular_anexo(
        ANEXO_I, D("300000"), [("monofasico", D("10000"))], ano=2027, mes=1
    )
    assert desconsiderados(calculo) == {"CBS", "IBS"}
    assert por_tributo(calculo)["CBS"] == D("0.00")
    assert calculo.total == D("449.54")
    assert all(linha.deduzido == D("0.00") for linha in calculo.segmentos[0].linhas)


def test_sujeita_st_2027_desconsidera_so_o_icms():
    """ST de ICMS (segmento sujeita_st): ICMS 180,88 sai; o resto fica. 532,00 − 180,88 = 351,12."""
    calculo = motor.calcular_anexo(
        ANEXO_I, D("300000"), [("sujeita_st", D("10000"))], ano=2027, mes=1
    )
    assert desconsiderados(calculo) == {"ICMS"}
    assert calculo.total == D("351.12")


def test_exportacao_de_comercio_2027_desconsidera_cbs_ibs_ipi_icms_e_iss():
    """Exportação de mercadoria, Anexo I, RBT12 externo 300.000, receita 10.000.

    Efetiva 0,0532. Sobram IRPJ 29,26, CSLL 18,62 e CPP 220,78: total 268,66. CBS, IBS e ICMS
    saem (art. 25, § 3º). Se o IPI fosse o ponto, não teria linha no Anexo I.
    """
    calculo = motor.calcular_anexo(
        ANEXO_I, D("300000"), [("exportacao", D("10000"))], ano=2027, mes=1
    )
    assert desconsiderados(calculo) == {"CBS", "IBS", "ICMS"}
    assert por_tributo(calculo) == {
        "IRPJ": D("29.26"),
        "CSLL": D("18.62"),
        "CBS": D("0.00"),
        "CPP": D("220.78"),
        "ICMS": D("0.00"),
        "IBS": D("0.00"),
    }
    assert calculo.total == D("268.66")


def test_servico_anexo_iii_2027_faixa_2_sem_teto():
    """Serviço, Anexo III, RBT12 300.000, receita 10.000.

    Faixa 2 (180.000,01 a 360.000): nominal 11,20%, a deduzir 9.360,00.
    Efetiva = (300.000 × 0,112 − 9.360) / 300.000 = 24.240 / 300.000 = 0,0808 (8,08%).
    IRPJ 4,00% → 32,32 · CSLL 3,50% → 28,28 · CBS 16,91% → 136,6328 → 136,63
    CPP 43,40% → 350,672 → 350,67 · ISS 32,00% → 258,56 · IBS 0,19% → 1,5352 → 1,54.
    Total: 808,00 (= 8,08% de 10.000).
    """
    calculo = motor.calcular_anexo("III", D("300000"), [("normal", D("10000"))], ano=2027, mes=1)
    assert calculo.efetiva == D("0.0808")
    assert not calculo.teto_aplicado
    assert por_tributo(calculo) == {
        "IRPJ": D("32.32"),
        "CSLL": D("28.28"),
        "CBS": D("136.63"),
        "CPP": D("350.67"),
        "ISS": D("258.56"),
        "IBS": D("1.54"),
    }
    assert calculo.total == D("808.00")


def test_servico_anexo_iii_2027_exportacao_sem_cbs_ibs_iss():
    """Exportação de serviço, Anexo III, mesma conta: sobram IRPJ 32,32, CSLL 28,28 e CPP 350,67.

    Total 411,27. CBS (136,63), IBS (1,54) e ISS (258,56) saem (art. 25, § 3º).
    """
    calculo = motor.calcular_anexo(
        "III", D("300000"), [("exportacao", D("10000"))], ano=2027, mes=1
    )
    assert desconsiderados(calculo) == {"CBS", "IBS", "ISS"}
    assert calculo.total == D("411.27")


def test_servico_anexo_iii_2027_com_teto_do_iss_redistribui_ao_ibs():
    """Teto do ISS, Anexo III, 5ª faixa, RBT12 3.000.000, receita 100.000.

    Faixa 5 (1.800.000,01 a 3.600.000): nominal 21,00%, a deduzir 125.640,00.
    Efetiva = (3.000.000 × 0,21 − 125.640) / 3.000.000 = 504.360 / 3.000.000 = 0,16812.
    Acima de 14,92537%: ISS 5% e excedente = 0,16812 − 0,05 = 0,11812, redistribuído:
    IRPJ 6,02% → 0,0071108 → 711,08 · CSLL 5,26% → 621,3112 → 621,31
    CBS 23,20% → 2.740,384 → 2.740,38 · CPP 65,26% → 7.708,5112 → 7.708,51
    IBS 0,26% → 30,7112 → 30,71 · ISS 5% → 5.000,00.
    Total por tributo: 16.811,99. A conta exata é 16.812,00: o centavo vem dos arredondamentos.
    """
    calculo = motor.calcular_anexo("III", D("3000000"), [("normal", D("100000"))], ano=2027, mes=1)
    assert calculo.teto_aplicado
    assert calculo.efetiva == D("0.16812")
    assert por_tributo(calculo) == {
        "IRPJ": D("711.08"),
        "CSLL": D("621.31"),
        "CBS": D("2740.38"),
        "CPP": D("7708.51"),
        "ISS": D("5000.00"),
        "IBS": D("30.71"),
    }
    assert calculo.total == D("16811.99")


def test_servico_anexo_iv_2027_com_teto_do_iss_sem_cpp():
    """Teto do ISS, Anexo IV, 5ª faixa, RBT12 2.000.000, receita 100.000. Anexo IV não tem CPP.

    Faixa 5: nominal 22,00%, a deduzir 183.780,00. Efetiva = (440.000 − 183.780) / 2.000.000
    = 0,12811 (12,811%). Acima de 12,5%: ISS 5% e excedente 0,07811.
    IRPJ 31,33% → 2.447,1863 → 2.447,19 · CSLL 32,00% → 2.499,52
    CBS 36,27% → 2.833,0497 → 2.833,05
    IBS 0,40% → 31,244 → 31,24 · ISS 5% → 5.000,00. Total: 12.811,00 (= 12,811% de 100.000).
    """
    calculo = motor.calcular_anexo("IV", D("2000000"), [("normal", D("100000"))], ano=2027, mes=1)
    assert calculo.teto_aplicado
    assert por_tributo(calculo) == {
        "IRPJ": D("2447.19"),
        "CSLL": D("2499.52"),
        "CBS": D("2833.05"),
        "ISS": D("5000.00"),
        "IBS": D("31.24"),
    }
    assert "CPP" not in por_tributo(calculo)
    assert calculo.total == D("12811.00")


def test_servico_anexo_iii_2027_regime_regular_deduz_cbs_e_ibs_da_faixa():
    """Art. 22-A, Anexo III, mesma conta de 808,00: CBS 136,63 e IBS 1,54 saem do DAS.

    Total: 808,00 − 136,63 − 1,54 = 669,83 (= 32,32 + 28,28 + 258,56 + 350,67).
    """
    calculo = motor.calcular_anexo(
        "III", D("300000"), [("normal", D("10000"))], ano=2027, mes=1, regime_regular=True
    )
    assert calculo.total == D("669.83")
    deduzidos = {linha.tributo: linha.deduzido for linha in calculo.segmentos[0].linhas}
    assert deduzidos["CBS"] == D("136.63")
    assert deduzidos["IBS"] == D("1.54")


def test_servico_com_regime_regular_nao_deduz_o_que_ja_saiu_na_exportacao():
    """Exportação com opção pelo regime regular: CBS e IBS já estão desconsiderados, então não há
    o que deduzir. Total continua 411,27 e `deduzido` fica zero nas duas."""
    calculo = motor.calcular_anexo(
        "III",
        D("300000"),
        [("exportacao", D("10000"))],
        ano=2027,
        mes=1,
        regime_regular=True,
    )
    assert calculo.total == D("411.27")
    deduzidos = {linha.tributo: linha.deduzido for linha in calculo.segmentos[0].linhas}
    assert deduzidos["CBS"] == D("0.00")
    assert deduzidos["IBS"] == D("0.00")


def test_produção_propria_fora_da_zfm_vai_ao_anexo_i_em_2027():
    """Produção própria fora da ZFM: em 2027 o Anexo II fica só para IPI mantido (art. 25, § 1º).

    `anexo_da_mercadoria_no_ano(2027, II)` é I; em 2026 continua II (regra anterior, sem mudança).
    A conta é a do comércio do Anexo I: 532,00 para RBT12 300.000 e venda de 10.000.
    """
    assert motor.anexo_da_mercadoria_no_ano(2027, ANEXO_II) == ANEXO_I
    assert motor.anexo_da_mercadoria_no_ano(2028, ANEXO_II) == ANEXO_I
    assert motor.anexo_da_mercadoria_no_ano(2026, ANEXO_II) == ANEXO_II
    assert motor.anexo_da_mercadoria_no_ano(2027, ANEXO_I) == ANEXO_I
    calculo = motor.calcular_anexo(
        motor.anexo_da_mercadoria_no_ano(2027, ANEXO_II),
        D("300000"),
        [("normal", D("10000"))],
        ano=2027,
        mes=1,
    )
    assert calculo.total == D("532.00")


def test_ipi_fica_no_segmento_normal_do_anexo_ii_e_sai_na_exportacao():
    """Anexo II, 2027, RBT12 300.000, faixa 2 (nominal 7,80%, a deduzir 5.940). Efetiva
    (23.400 − 5.940) / 300.000 = 0,0582.

    Normal, receita 10.000: IRPJ 5,50% → 32,01 · CSLL 3,50% → 20,37 · CBS 13,85% → 80,607 → 80,61
    CPP 37,50% → 218,25 · IPI 7,50% → 43,65 · ICMS 32,00% → 186,24 · IBS 0,15% → 0,873 → 0,87.
    Total: 582,00 (= 5,82% de 10.000). O IPI entra.

    Exportação, mesma receita: IPI, CBS, IBS e ICMS saem. Sobram IRPJ 32,01, CSLL 20,37 e CPP
    218,25: total 270,63. É este caso que o teste de IPI na exportação guarda (mutante).
    """
    normal = motor.calcular_anexo(ANEXO_II, D("300000"), [("normal", D("10000"))], ano=2027, mes=1)
    assert por_tributo(normal)["IPI"] == D("43.65")
    assert normal.total == D("582.00")

    exportacao = motor.calcular_anexo(
        ANEXO_II, D("300000"), [("exportacao", D("10000"))], ano=2027, mes=1
    )
    assert desconsiderados(exportacao) == {"CBS", "IBS", "IPI", "ICMS"}
    assert por_tributo(exportacao) == {
        "IRPJ": D("32.01"),
        "CSLL": D("20.37"),
        "CBS": D("0.00"),
        "CPP": D("218.25"),
        "IPI": D("0.00"),
        "ICMS": D("0.00"),
        "IBS": D("0.00"),
    }
    assert exportacao.total == D("270.63")


def test_primeira_faixa_sem_rbt12_usa_a_nominal_porque_a_deducao_e_zero():
    """Início de atividade, 1º e 2º mês: 1ª faixa, sem RBT12 numérico (Res. 190, art. 22, § 2º, I).

    Anexo I, 1ª faixa: nominal 4,00%, a deduzir zero. Efetiva = (R × 0,04 − 0) / R = 0,04 para
    qualquer R. Venda 10.000: IRPJ 22,00 · CSLL 14,00 · CBS 61,32 · CPP 166,00 · ICMS 136,00
    · IBS 0,68. Total: 400,00 (= 4% de 10.000).
    """
    calculo = motor.calcular_anexo(
        ANEXO_I, None, [("normal", D("10000"))], ano=2027, mes=1, primeira_faixa=True
    )
    assert calculo.faixa.numero == 1
    assert calculo.efetiva == D("0.04")
    assert por_tributo(calculo) == {
        "IRPJ": D("22.00"),
        "CSLL": D("14.00"),
        "CBS": D("61.32"),
        "CPP": D("166.00"),
        "ICMS": D("136.00"),
        "IBS": D("0.68"),
    }
    assert calculo.total == D("400.00")


def test_calculo_sem_rbt12_fora_da_primeira_faixa_e_erro_de_chamada():
    import pytest

    with pytest.raises(ValueError):
        motor.calcular_anexo(ANEXO_I, None, [("normal", D("10000"))], ano=2027, mes=1)


def test_2026_nao_muda_com_os_parametros_novos():
    """Chamadores de 2026 não passam período: continuam na tabela de PIS e Cofins, sem CBS."""
    calculo = motor.calcular_anexo("III", D("300000"), [("normal", D("10000"))])
    tributos = {linha.tributo for linha in calculo.segmentos[0].linhas}
    assert "COFINS" in tributos and "PIS" in tributos
    assert "CBS" not in tributos and "IBS" not in tributos
