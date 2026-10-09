"""DL-079, critérios 1 (tabelas), 6 (quotas e vencimentos) e a parte de calendário do critério 6.

Tabelas como dado: cada valor tem fonte e vigência, e os percentuais são `Decimal` exato. Os valores
esperados são escritos aqui à mão, conforme a consulta de 08/10/2026 e os textos lidos
nessa data.
"""

from datetime import date
from decimal import Decimal as D

import pytest

from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab

# ---------------------------------------------------------------------------
# Tabelas: catálogo, alíquotas, LC 224, DARF
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "irpj", "csll"),
    [
        (tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA, D("0.08"), D("0.12")),
        (tab.REVENDA_COMBUSTIVEIS, D("0.016"), D("0.12")),
        (tab.TRANSPORTE_PASSAGEIROS, D("0.16"), D("0.12")),
        (tab.SERVICOS_GERAIS, D("0.32"), D("0.32")),
        (tab.INTERMEDIACAO_NEGOCIOS, D("0.32"), D("0.32")),
        (tab.ADMINISTRACAO_LOCACAO_CESSAO_BENS, D("0.32"), D("0.32")),
        (tab.SERVICOS_HOSPITALARES, D("0.08"), D("0.12")),
    ],
)
def test_catalogo_de_atividades_tem_os_percentuais_do_plano(codigo, irpj, csll):
    atividade = tab.ATIVIDADES_POR_CODIGO[codigo]
    assert atividade.irpj == irpj
    assert atividade.csll == csll


def test_catalogo_e_fechado_com_sete_atividades():
    assert len(tab.CATALOGO_ATIVIDADES) == 7
    assert len(set(tab.CODIGOS_DE_ATIVIDADE)) == 7


def test_percentuais_sao_decimal_exato_nunca_float():
    for atividade in tab.CATALOGO_ATIVIDADES:
        assert isinstance(atividade.irpj, D)
        assert isinstance(atividade.csll, D)
    assert isinstance(tab.ALIQUOTA_IRPJ, D) and tab.ALIQUOTA_IRPJ == D("0.15")
    assert isinstance(tab.ALIQUOTA_ADICIONAL_IRPJ, D) and tab.ALIQUOTA_ADICIONAL_IRPJ == D("0.10")
    assert tab.LIMITE_ADICIONAL_POR_MES == D("20000.00")
    assert tab.ALIQUOTA_CSLL == D("0.09")


def test_lc224_fator_limite_e_inicio_de_vigencia():
    assert tab.FATOR_ACRESCIMO_LC224 == D("1.10")
    assert tab.LIMITE_TRIMESTRAL_LC224 == D("1250000.00")
    assert tab.INICIO_ACRESCIMO[tab.IRPJ] == date(2026, 1, 1)
    assert tab.INICIO_ACRESCIMO[tab.CSLL] == date(2026, 4, 1)


def test_codigos_darf_informativos_2089_e_2372():
    assert tab.CODIGO_DARF[tab.IRPJ] == "2089"
    assert tab.CODIGO_DARF[tab.CSLL] == "2372"
    assert "gov.br/receitafederal" in tab.FONTE_CODIGOS_DARF


def test_toda_tabela_tem_fonte_citada():
    for fonte in (
        tab.FONTE_PERCENTUAIS,
        tab.FONTE_ALIQUOTAS,
        tab.FONTE_LIMITE_LC224,
        tab.FONTE_CODIGOS_DARF,
        tab.FONTE_FERIADOS,
    ):
        assert fonte.strip()
    assert "art. 4º" in tab.FONTE_LIMITE_LC224
    assert "art. 3º" in tab.FONTE_ALIQUOTAS


# ---------------------------------------------------------------------------
# Feriados: fixos por lei, Lei 14.759/2023 (20/11) lida em 08/10/2026
# ---------------------------------------------------------------------------


def test_feriados_nacionais_fixos_sao_os_das_leis():
    datas = {(mes, dia) for mes, dia, _, _ in tab.FERIADOS_NACIONAIS_FIXOS}
    assert datas == {
        (1, 1),  # Lei 662/1949
        (4, 21),
        (5, 1),
        (9, 7),
        (10, 12),  # Lei 6.802/1980
        (11, 2),
        (11, 15),
        (11, 20),  # Lei 14.759/2023, art. 1º
        (12, 25),
    }


def test_20_de_novembro_so_vale_a_partir_de_2023():
    assert calc.feriado_nacional_fixo(date(2026, 11, 20)) is True
    assert calc.feriado_nacional_fixo(date(2022, 11, 20)) is False


def test_feriado_nao_inclui_pontos_facultativos_nem_estaduais():
    # Corpus Christi e 9 de julho não são feriado nacional fixo: ficam fora (HI-105).
    assert calc.feriado_nacional_fixo(date(2026, 7, 9)) is False


# ---------------------------------------------------------------------------
# Páscoa (Gauss/Meeus) e as datas que pedem conferência de calendário
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ano", "pascoa"),
    [
        (2024, date(2024, 3, 31)),  # domingo de Páscoa conhecido
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2029, date(2029, 4, 1)),
    ],
)
def test_pascoa_pelo_algoritmo_de_gauss_meeus(ano, pascoa):
    assert calc.pascoa(ano) == pascoa


def test_sexta_feira_santa_de_2029_e_30_de_marco_e_avisa():
    # 30/03/2029 é Sexta-feira Santa (Páscoa 01/04/2029 − 2 dias). Só esta data avisa.
    assert date(2029, 3, 30) in calc.datas_a_conferir(2029)
    assert date(2029, 3, 29) not in calc.datas_a_conferir(2029)
    assert date(2029, 3, 31) not in calc.datas_a_conferir(2029)


def test_sexta_feira_santa_de_2027_e_26_de_marco_e_avisa():
    # Páscoa 28/03/2027 → Sexta-feira Santa 26/03/2027. Só esta avisa; 27/03 e 29/03 não.
    assert date(2027, 3, 26) in calc.datas_a_conferir(2027)
    assert date(2027, 3, 27) not in calc.datas_a_conferir(2027)
    assert date(2027, 3, 29) not in calc.datas_a_conferir(2027)


def test_terca_de_carnaval_avisa_e_a_data_certa():
    # Terça de Carnaval = Páscoa − 47 dias: 13/02/2029 e 09/02/2027.
    assert date(2029, 2, 13) in calc.datas_a_conferir(2029)
    assert date(2027, 2, 9) in calc.datas_a_conferir(2027)
    assert date(2029, 2, 12) not in calc.datas_a_conferir(2029)


def test_vencimento_em_sexta_santa_nao_recua_so_avisa():
    # Último dia útil de março de 2029: 31/03 é sábado → recua a 30/03 (Sexta-feira Santa, que não é
    # feriado nacional por lei). A data fica e sai com o aviso "calendário a conferir".
    vencimento, aviso = calc.ultimo_dia_util(2029, 3)
    assert vencimento == date(2029, 3, 30)
    assert aviso is True


def test_vencimento_no_fim_de_semana_recua_para_o_util_anterior():
    # 31/10/2026 é sábado → 30/10/2026 (sexta), sem aviso.
    assert calc.ultimo_dia_util(2026, 10) == (date(2026, 10, 30), False)


def test_fim_de_semana_de_fevereiro_recua_para_sexta():
    # 28/02/2026 é sábado; não há feriado nacional fixo nesse fim de mês. Recua para 27/02 (sexta).
    assert calc.ultimo_dia_util(2026, 2) == (date(2026, 2, 27), False)


def test_20_de_novembro_nunca_muda_vencimento_porque_nao_e_fim_de_mes():
    # O último dia do mês nunca é 20/11, então o feriado de 20/11 não altera nenhum vencimento de
    # quota. A função de feriado o reconhece (teste acima); aqui se fixa o vencimento de novembro.
    assert calc.feriado_nacional_fixo(date(2026, 11, 20)) is True
    assert calc.ultimo_dia_util(2026, 11) == (date(2026, 11, 30), False)


# ---------------------------------------------------------------------------
# Critério 6: quotas. 1.999,99; 2.000,00; 2.999,99; 3.000,00
# ---------------------------------------------------------------------------


def test_quota_1999_99_recusa_o_plano_por_imposto_abaixo_de_2000():
    opcoes = calc.opcoes_de_quota(D("1999.99"), 2026, 1)
    assert opcoes.tres_quotas is None
    assert opcoes.motivo_sem_tres_quotas == "Imposto abaixo de R$ 2.000,00: só quota única."
    assert len(opcoes.quota_unica) == 1


def test_quota_2000_00_recusa_o_plano_porque_a_quota_fica_em_666_67():
    # 2.000,00 / 3 = 666,67 (abaixo de R$ 1.000,00). O plano é recusado pela quota, não pelo
    # imposto.
    opcoes = calc.opcoes_de_quota(D("2000.00"), 2026, 1)
    assert opcoes.tres_quotas is None
    assert "abaixo de R$ 1.000,00" in opcoes.motivo_sem_tres_quotas


def test_quota_2999_99_recusa_o_plano_porque_a_quota_fica_em_999_99():
    # 2.999,99 / 3 = 999,99 (abaixo de R$ 1.000,00): recusa pela quota, e não pelo imposto.
    opcoes = calc.opcoes_de_quota(D("2999.99"), 2026, 1)
    assert opcoes.tres_quotas is None
    assert "abaixo de R$ 1.000,00" in opcoes.motivo_sem_tres_quotas


def test_quota_3000_00_aceita_o_plano_de_3_quotas_iguais():
    # 3.000,00 / 3 = 1.000,00 exato em cada quota: o plano existe.
    opcoes = calc.opcoes_de_quota(D("3000.00"), 2026, 1)
    assert opcoes.motivo_sem_tres_quotas is None
    assert [p.valor for p in opcoes.tres_quotas] == [D("1000.00")] * 3


def test_quota_residuo_fica_na_terceira():
    # 3.000,01 / 3 = 1.000,0033 → 1.000,00; a 3ª leva o resíduo: 1.000,01.
    opcoes = calc.opcoes_de_quota(D("3000.01"), 2026, 1)
    assert [p.valor for p in opcoes.tres_quotas] == [D("1000.00"), D("1000.00"), D("1000.01")]
    assert sum(p.valor for p in opcoes.tres_quotas) == D("3000.01")


def test_juros_de_cada_quota_como_texto_sem_embutir_taxa():
    # Trimestre do 1º trimestre de 2026 (termina em março). 1ª: sem juros. 2ª: 1%. 3ª: Selic a
    # partir do 2º mês seguinte (maio) + 1%, taxa não embutida.
    opcoes = calc.opcoes_de_quota(D("3000.00"), 2026, 1)
    juros = [p.juros for p in opcoes.tres_quotas]
    assert juros[0] == "sem juros"
    assert juros[1] == "1%"
    assert juros[2] == "Selic acumulada de maio + 1% — taxa não embutida"


def test_vencimentos_das_quotas_seguem_o_mes_seguinte_ao_trimestre():
    # Trimestre de março: quota única e 1ª em abril, 2ª em maio, 3ª em junho (último dia útil).
    opcoes = calc.opcoes_de_quota(D("3000.00"), 2026, 1)
    assert [p.vencimento for p in opcoes.tres_quotas] == [
        date(2026, 4, 30),
        date(2026, 5, 29),
        date(2026, 6, 30),
    ]
    assert opcoes.quota_unica[0].vencimento == date(2026, 4, 30)


def test_quota_unica_com_imposto_zero_nao_tem_pagamento():
    opcoes = calc.opcoes_de_quota(D("0"), 2026, 2)
    assert opcoes.quota_unica == ()
    assert opcoes.tres_quotas is None


def test_quotas_do_quarto_trimestre_viram_janeiro_do_ano_seguinte():
    # Trimestre de dezembro de 2028: quotas em janeiro, fevereiro e março de 2029.
    opcoes = calc.opcoes_de_quota(D("9000.00"), 2028, 4)
    venc = [p.vencimento for p in opcoes.tres_quotas]
    assert venc[0].year == 2029 and venc[0].month == 1
    assert venc[2] == date(2029, 3, 30)
    assert opcoes.tres_quotas[2].aviso_calendario is True
    assert opcoes.tres_quotas[2].juros == "Selic acumulada de fevereiro + 1% — taxa não embutida"


# ---------------------------------------------------------------------------
# Medida judicial: cobertura do trimestre (puro)
# ---------------------------------------------------------------------------


def test_medida_com_prazo_indeterminado_cobre_qualquer_trimestre_depois_do_inicio():
    assert calc.cobre_o_trimestre((2026, 2), None, 2026, 2) is True
    assert calc.cobre_o_trimestre((2026, 2), None, 2030, 4) is True
    assert calc.cobre_o_trimestre((2026, 2), None, 2026, 1) is False


def test_medida_com_fim_cobre_so_o_periodo():
    assert calc.cobre_o_trimestre((2026, 1), (2026, 3), 2026, 3) is True
    assert calc.cobre_o_trimestre((2026, 1), (2026, 3), 2026, 4) is False
