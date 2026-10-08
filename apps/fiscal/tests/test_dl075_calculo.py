"""DL-075 (frente A) — regras de cálculo: fator r, teto do ISS, segregação, arredondamento.

Os valores esperados são escritos à mão e derivados das regras do plano (critérios
2 a 7) e das tabelas do documento de consulta. Os testes "puros" não usam banco; os
de pipeline usam o banco real (receita, folha, escrituração sintética).
"""

from decimal import Decimal, localcontext

import pytest

from apps.fiscal import pre_das as servico
from apps.fiscal import receita as servico_receita
from apps.fiscal import simples_tabelas as tabelas
from apps.fiscal.models import EnquadramentoAtividade, NaturezaOperacao
from apps.fiscal.tests.test_dl074_suporte import escriturar, informar_e_confirmar, sequencia
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folhas_dos_12_meses,
    janela_de_receitas,
    receber_e_confirmar_mes,
)

pytestmark = pytest.mark.django_db


def _tributos(linhas):
    return {linha.tributo: linha.valor for linha in linhas}


# ---------------------------------------------------------------------------
# Fator r (critério 2): truncar em 2 casas; regras de zero como rotina
# ---------------------------------------------------------------------------


def test_fator_r_0_2799_trunca_para_0_27_e_vai_ao_anexo_v():
    valor, regra = servico.fator_r(Decimal("2799"), Decimal("10000"))
    assert valor == Decimal("0.27")
    assert regra is None
    assert (
        servico.anexo_do_enquadramento(EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R, valor) == "V"
    )


def test_fator_r_0_28_vai_ao_anexo_iii():
    valor, _regra = servico.fator_r(Decimal("2800"), Decimal("10000"))
    assert valor == Decimal("0.28")
    assert (
        servico.anexo_do_enquadramento(EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R, valor)
        == "III"
    )


def test_fator_r_trunca_sem_arredondar_para_cima():
    """0,2799… cai em 0,27 (truncado), não em 0,28 (arredondado)."""
    valor, _ = servico.fator_r(Decimal("27999999"), Decimal("100000000"))
    assert valor == Decimal("0.27")


def test_regras_de_zero_do_manual_sao_rotina_marcada_como_tal():
    valor, regra = servico.fator_r(Decimal("0"), Decimal("500000"))
    assert valor == Decimal("0.01")
    assert "rotina" in regra.lower()
    valor, regra = servico.fator_r(Decimal("100"), Decimal("0"))
    assert valor == Decimal("0.28")
    assert "rotina" in regra.lower()
    valor, regra = servico.fator_r(Decimal("0"), Decimal("0"))
    assert valor == Decimal("0.01")


# ---------------------------------------------------------------------------
# Alíquota efetiva (§ 1º-A): precisão total, RBT12 = 0 vira 1
# ---------------------------------------------------------------------------


def test_aliquota_efetiva_com_rbt12_zero_usa_a_nominal_da_primeira_faixa():
    faixa = tabelas.anexo("III").faixa_da_receita(Decimal("0"))
    assert faixa.numero == 1
    assert servico.aliquota_efetiva(Decimal("0"), faixa) == Decimal("0.06")


def test_aliquota_efetiva_nao_e_arredondada():
    """RBT12 = 300.001: o resultado tem a fração exata, sem corte nas casas decimais."""
    faixa = tabelas.anexo("III").faixa(2)
    efetiva = servico.aliquota_efetiva(Decimal("300001"), faixa)
    with localcontext() as contexto:
        contexto.prec = 60
        exata = (Decimal("300001") * Decimal("0.112") - Decimal("9360")) / Decimal("300001")
    assert abs(efetiva - exata) < Decimal("1E-50")
    assert efetiva.quantize(Decimal("0.0001")) != efetiva


def test_limite_de_faixa_e_inclusivo_no_teto_da_faixa():
    anexo = tabelas.anexo("III")
    assert anexo.faixa_da_receita(Decimal("180000.00")).numero == 1
    assert anexo.faixa_da_receita(Decimal("180000.01")).numero == 2


# ---------------------------------------------------------------------------
# Teto do ISS (critério 3)
# ---------------------------------------------------------------------------


def test_teto_iss_iii_quinta_faixa_acima_do_limiar_fixa_iss_em_5_por_cento():
    anexo = tabelas.anexo("III")
    faixa = anexo.faixa_da_receita(Decimal("3000000"))
    efetiva = servico.aliquota_efetiva(Decimal("3000000"), faixa)
    assert efetiva == Decimal("0.16812")
    itens, aplicado, _dif, _destino = servico.percentuais_efetivos(anexo, faixa, efetiva)
    assert aplicado is True
    pct = dict(itens)
    assert pct["ISS"] == Decimal("0.05")
    excedente = efetiva - Decimal("0.05")
    assert pct["CPP"] == excedente * Decimal("0.6526")
    assert pct["IRPJ"] == excedente * Decimal("0.0602")
    # Soma igual à alíquota efetiva (critério 3): nada se perde nem sobra.
    assert abs(sum(pct.values()) - efetiva) < Decimal("1E-50")


def test_teto_iss_nao_aplica_abaixo_do_limiar():
    anexo = tabelas.anexo("III")
    faixa = anexo.faixa_da_receita(Decimal("2000000"))
    efetiva = servico.aliquota_efetiva(Decimal("2000000"), faixa)
    assert efetiva == Decimal("0.14718")
    itens, aplicado, _dif, _destino = servico.percentuais_efetivos(anexo, faixa, efetiva)
    assert aplicado is False
    assert dict(itens)["ISS"] == efetiva * Decimal("0.335")


def test_teto_iss_nao_aplica_no_proprio_limiar_superior_a_estritamente():
    """Critério "superior a 14,92537%": no limiar exato, o teto não se aplica."""
    anexo = tabelas.anexo("III")
    faixa = anexo.faixa(5)
    _itens, aplicado, _dif, _destino = servico.percentuais_efetivos(
        anexo, faixa, anexo.teto_iss.limiar_efetiva
    )
    assert aplicado is False


def test_teto_iss_iv_quinta_faixa_acima_de_12_5_por_cento_sem_cpp():
    anexo = tabelas.anexo("IV")
    faixa = anexo.faixa_da_receita(Decimal("2500000"))
    efetiva = servico.aliquota_efetiva(Decimal("2500000"), faixa)
    assert efetiva == Decimal("0.146488")
    itens, aplicado, _dif, _destino = servico.percentuais_efetivos(anexo, faixa, efetiva)
    assert aplicado is True
    pct = dict(itens)
    assert "CPP" not in pct  # critério 6: Anexo IV sem CPP
    assert pct["ISS"] == Decimal("0.05")
    assert abs(sum(pct.values()) - efetiva) < Decimal("1E-50")


# ---------------------------------------------------------------------------
# Arredondamento do valor (HI-71) e diferença centesimal (§ 1º-B, II)
# ---------------------------------------------------------------------------


def test_valor_do_tributo_arredonda_meio_centavo_para_cima():
    """ROUND_HALF_UP: 1,00 × 0,005 = 0,005 vai para 0,01 (o HALF_EVEN daria 0,00)."""
    assert servico.valor_do_tributo(Decimal("1.00"), Decimal("0.005")) == Decimal("0.01")
    assert servico.valor_do_tributo(Decimal("1.00"), Decimal("0.015")) == Decimal("0.02")
    assert servico.valor_do_tributo(Decimal("1.00"), Decimal("0.0049")) == Decimal("0.00")


def test_diferenca_centesimal_fica_no_tributo_de_maior_percentual_nominal():
    anexo = tabelas.anexo("III")
    faixa = anexo.faixa(3)
    efetiva = servico.aliquota_efetiva(Decimal("500000"), faixa)
    _itens, _aplicado, diferenca, destino = servico.percentuais_efetivos(anexo, faixa, efetiva)
    assert abs(diferenca) < Decimal("1E-40")  # precisão total: a diferença é ínfima
    assert destino == "CPP"  # 43,40% é o maior percentual nominal da 3ª faixa do Anexo III


# ---------------------------------------------------------------------------
# Pipeline: segregação (critérios 4 e 5) e Anexo IV (critério 6)
# ---------------------------------------------------------------------------


def _janela_externa(empresa, usuario, ate_ano, ate_mes, valor_mensal):
    """12 meses de receita EXTERNA confirmada (RBT12 externo) e mês interno vazio confirmado."""
    for ano, mes in sequencia(ate_ano - 1, ate_mes, 12):
        informar_e_confirmar(empresa, usuario, ano, mes, valor_mensal, mercado="externo")
        servico_receita.confirmar_mes(empresa, ano, mes, usuario)


def test_iss_retido_sai_do_valor_e_os_demais_tributos_nao_mudam(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9101,
        competencia=(2026, 6),
        valor="100000.00",
        natureza=NaturezaOperacao.PRESTADO_ISS_RETIDO,
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    (segmento,) = anexo.segmentos
    assert segmento.segmento == servico.SEG_RETIDO
    valores = {linha.tributo: str(linha.valor) for linha in segmento.linhas}
    assert valores == {
        "IRPJ": "323.20",
        "CSLL": "282.80",
        "COFINS": "1135.24",
        "PIS": "246.44",
        "CPP": "3506.72",
        "ISS": "0.00",
    }
    assert str(resultado.total) == "5494.40"


def test_iss_devido_a_outro_municipio_mantem_o_iss(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9102,
        competencia=(2026, 6),
        valor="100000.00",
        natureza=NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO,
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    (segmento,) = resultado.anexos[0].segmentos
    assert segmento.segmento == servico.SEG_OUTRO_MUNICIPIO
    assert _tributos(segmento.linhas)["ISS"] == Decimal("2585.60")
    assert str(resultado.total) == "8080.00"


def test_exportacao_zera_pis_cofins_e_iss_e_usa_o_rbt12_externo(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _janela_externa(empresa, usuario_gestor_a, 2026, 6, Decimal("25000"))
    # Mês de referência: interno sem receita, confirmado; a exportação é escriturada.
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9103,
        competencia=(2026, 6),
        valor="100000.00",
        natureza=NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.rbt12["externo"] == Decimal("300000.00")
    (anexo,) = resultado.anexos
    assert (anexo.mercado, anexo.anexo) == ("externo", "III")
    valores = {linha.tributo: linha for linha in anexo.segmentos[0].linhas}
    assert valores["PIS"].valor == Decimal("0.00") and valores["PIS"].desconsiderado
    assert valores["COFINS"].valor == Decimal("0.00") and valores["COFINS"].desconsiderado
    assert valores["ISS"].valor == Decimal("0.00") and valores["ISS"].desconsiderado
    assert str(valores["IRPJ"].valor) == "323.20"
    assert str(valores["CPP"].valor) == "3506.72"
    assert str(resultado.total) == "4112.72"


def test_anexo_iv_no_pipeline_nao_tem_cpp_e_bate_a_conta(empresa_a, usuario_gestor_a):
    """Anexo IV, RBT12 300.000 (2ª faixa: nominal 9,00%, PD 8.100,00), receita 100.000.

    Alíquota efetiva = (300.000 × 9% − 8.100) / 300.000 = 6,30%. Total = 6.300,00.
    """
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_IV)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    assert anexo.anexo == "IV"
    assert anexo.aliquota_efetiva == Decimal("0.063")
    valores = _tributos(anexo.segmentos[0].linhas)
    assert "CPP" not in valores
    assert {k: str(v) for k, v in valores.items()} == {
        "IRPJ": "1247.40",
        "CSLL": "957.60",
        "COFINS": "1294.65",
        "PIS": "280.35",
        "ISS": "2520.00",
    }
    assert str(resultado.total) == "6300.00"


def test_fator_r_pelo_pipeline_na_fronteira_0_28_vai_ao_anexo_iii(empresa_a, usuario_gestor_a):
    """Critério 2 pelo banco: FS12 33.600 / RBT12 120.000 = 0,28 → Anexo III."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [10000] * 12)
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [2800] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "1000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.fator_r.valor == Decimal("0.28")
    assert resultado.anexos[0].anexo == "III"


def test_fator_r_pelo_pipeline_abaixo_da_fronteira_0_2799_vai_ao_anexo_v(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [10000] * 12)
    # FS12 = 0,2799 × 120.000 = 33.588, ou seja 2.799,00 por mês (12 meses).
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [Decimal("2799.00")] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "1000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.fator_r.fs12 == Decimal("33588.00")
    assert resultado.fator_r.valor == Decimal("0.27")
    assert resultado.anexos[0].anexo == "V"


def test_rascunho_de_receita_nao_entra_no_pre_das(empresa_a, usuario_gestor_a):
    """Critério de rascunho distinguível: o rascunho não é receita do mês."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    servico_receita.lancar_receita_informada(
        empresa,
        2026,
        6,
        "interno",
        "100000.00",
        "outras_receitas_atividade",
        "Rascunho sintético.",
        SUPORTE_SINTETICO,
        usuario_gestor_a,
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("0.00")
    assert resultado.anexos == ()
