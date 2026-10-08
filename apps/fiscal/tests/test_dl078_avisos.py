"""DL-078, critério 6: cada aviso A1 a A8 dispara no caso que o justifica, e não no contrário.

Função pura: sem banco. Valores escritos à mão. As fronteiras (limite de R$ 10,00, tolerância de
R$ 0,01, regApTribSN 3, regime do tomador) são testadas nos dois lados.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import RegimeTributario
from apps.fiscal.tomadas import DadosTomada, avisos_da_tomada


def _dados(**mudancas) -> DadosTomada:
    base = {
        "prestador_tipo_documento": "CNPJ",
        "tp_ret_issqn": "1",
        "op_simp_nac": None,
        "reg_ap_trib_sn": None,
        "valor_servico": Decimal("1000.00"),
        "valor_liquido": Decimal("1000.00"),
        "v_desc_incond": None,
        "v_desc_cond": None,
        "v_iss_qn": None,
        "v_ret_cp": None,
        "v_ret_irrf": None,
        "v_ret_csll": None,
        "tp_ret_pis_cofins": None,
        "v_pis": None,
        "v_cofins": None,
    }
    base.update(mudancas)
    return DadosTomada(**base)


def _codigos(dados, regime=None):
    return [aviso.codigo for aviso in avisos_da_tomada(dados, regime)]


def test_nota_limpa_sem_retencao_nao_tem_aviso():
    assert _codigos(_dados()) == []


# A1 — vLiq = vServ − vDescIncond − vDescCond − vTotalRet (P&R 13.2), tolerância R$ 0,01.
# Com tpRetISSQN 2, o vTotalRet soma o vISSQN: 1000 − 15 − (20 + 50) = 915.00.


def test_a1_dispara_quando_o_liquido_nao_fecha_com_a_formula():
    dados = _dados(
        valor_liquido=Decimal("900.00"),
        v_desc_incond=Decimal("10.00"),
        v_desc_cond=Decimal("5.00"),
        v_ret_csll=Decimal("20.00"),
        v_iss_qn=Decimal("50.00"),
        tp_ret_issqn="2",
    )
    assert _codigos(dados) == ["A1"]


def test_a1_nao_dispara_com_liquido_que_fecha_e_tolera_um_centavo():
    base = {
        "v_desc_incond": Decimal("10.00"),
        "v_desc_cond": Decimal("5.00"),
        "v_ret_csll": Decimal("20.00"),
        "v_iss_qn": Decimal("50.00"),
        "tp_ret_issqn": "2",
    }
    assert _codigos(_dados(valor_liquido=Decimal("915.00"), **base)) == []
    assert (
        _codigos(_dados(valor_liquido=Decimal("915.01"), **base)) == []
    )  # 0,01: dentro da tolerância
    assert _codigos(_dados(valor_liquido=Decimal("915.02"), **base)) == ["A1"]  # 0,02: acima


def test_a1_iss_so_entra_na_formula_quando_retido():
    # Mesmos números, sem retenção de ISS: o vISSQN do prestador NÃO é subtraído, e 915,00 não
    # fecha.
    dados = _dados(
        valor_liquido=Decimal("915.00"),
        v_desc_incond=Decimal("10.00"),
        v_desc_cond=Decimal("5.00"),
        v_ret_csll=Decimal("20.00"),
        v_iss_qn=Decimal("50.00"),
        tp_ret_issqn="1",
    )
    assert "A1" in _codigos(dados)


# A2 — tpRetPisCofins e vRetCSLL devem dizer a mesma coisa (P&R 13.1).


@pytest.mark.parametrize(
    ("tp", "csll"),
    [("1", None), ("3", Decimal("0.00")), ("9", None)],
    ids=["tp1_csll_ausente", "tp3_csll_zero", "tp9_csll_ausente"],
)
def test_a2_dispara_quando_ha_retencao_declarada_sem_csll(tp, csll):
    assert "A2" in _codigos(_dados(tp_ret_pis_cofins=tp, v_ret_csll=csll))


@pytest.mark.parametrize(
    ("tp", "csll"),
    [("0", Decimal("20.00")), ("2", Decimal("20.00"))],
    ids=["tp0_com_csll", "tp2_com_csll"],
)
def test_a2_dispara_no_inverso_csll_com_tp_sem_retencao(tp, csll):
    assert "A2" in _codigos(_dados(tp_ret_pis_cofins=tp, v_ret_csll=csll))


@pytest.mark.parametrize(
    ("tp", "csll"),
    [("3", Decimal("20.00")), ("2", None), ("0", None), (None, None)],
    ids=["tp3_csll_ok", "tp2_sem_csll", "tp0_sem_csll", "sem_tp"],
)
def test_a2_nao_dispara_quando_tp_e_csll_conferem(tp, csll):
    assert "A2" not in _codigos(_dados(tp_ret_pis_cofins=tp, v_ret_csll=csll))


# A3 — prestador optante do Simples (2 ou 3) com CSRF ou IRRF retidos: provavelmente indevida.
# Exceção: regApTribSN 3 (federais por fora do SN).


@pytest.mark.parametrize(
    ("op", "reg", "csll", "irrf"),
    [
        ("3", None, Decimal("20.00"), None),
        ("2", None, None, Decimal("15.00")),
    ],
    ids=["simples_csll", "mei_irrf"],
)
def test_a3_dispara_optante_com_federal_retido(op, reg, csll, irrf):
    assert "A3" in _codigos(
        _dados(op_simp_nac=op, reg_ap_trib_sn=reg, v_ret_csll=csll, v_ret_irrf=irrf)
    )


@pytest.mark.parametrize(
    ("op", "reg", "csll"),
    [
        ("3", "3", Decimal("20.00")),  # federais por fora do SN: exceção
        ("1", None, Decimal("20.00")),  # não optante: não é o caso do aviso
        ("3", None, None),  # sem federal retido
    ],
    ids=["regapur3_excecao", "nao_optante", "sem_federal"],
)
def test_a3_nao_dispara_no_contrario(op, reg, csll):
    assert "A3" not in _codigos(_dados(op_simp_nac=op, reg_ap_trib_sn=reg, v_ret_csll=csll))


# A4 — tomador optante do Simples não retém CSRF (Lei 10.833, art. 30, § 2º).


def test_a4_dispara_quando_o_tomador_esta_no_simples_e_retem_csll():
    dados = _dados(v_ret_csll=Decimal("20.00"))
    assert "A4" in _codigos(dados, RegimeTributario.SIMPLES_NACIONAL)


@pytest.mark.parametrize(
    ("regime", "csll"),
    [
        (RegimeTributario.SIMPLES_NACIONAL, None),
        (RegimeTributario.LUCRO_PRESUMIDO, Decimal("20.00")),
        (None, Decimal("20.00")),
    ],
    ids=["simples_sem_csll", "presumido", "regime_desconhecido"],
)
def test_a4_nao_dispara_no_contrario(regime, csll):
    assert "A4" not in _codigos(_dados(v_ret_csll=csll), regime)


# A5 — valor de retenção positivo e até R$ 10,00 (Lei 10.833, art. 31, § 3º).


def test_a5_dispara_em_valor_positivo_ate_dez_reais_inclusive():
    assert "A5" in _codigos(_dados(v_ret_csll=Decimal("10.00")))
    assert "A5" in _codigos(_dados(v_ret_irrf=Decimal("0.01")))


@pytest.mark.parametrize(
    ("csll", "irrf"),
    [(Decimal("10.01"), None), (Decimal("0.00"), None), (None, Decimal("0.00"))],
    ids=["acima_de_dez", "zero", "irrf_zero"],
)
def test_a5_nao_dispara_fora_da_faixa(csll, irrf):
    assert "A5" not in _codigos(_dados(v_ret_csll=csll, v_ret_irrf=irrf))


# A6 — INSS sobre optante do Simples só cabe no Anexo IV. A7 — informativo de cessão.


def test_a6_dispara_inss_com_prestador_no_simples_e_a7_tambem():
    codigos = _codigos(_dados(op_simp_nac="3", v_ret_cp=Decimal("11.00")))
    assert "A6" in codigos
    assert "A7" in codigos


def test_a6_nao_dispara_para_mei_nem_sem_inss_mas_a7_segue_o_inss():
    codigos = _codigos(_dados(op_simp_nac="2", v_ret_cp=Decimal("11.00")))
    assert "A6" not in codigos
    assert "A7" in codigos
    assert "A6" not in _codigos(_dados(op_simp_nac="3", v_ret_cp=None))


def test_a7_nao_dispara_com_inss_zerado():
    assert "A7" not in _codigos(_dados(v_ret_cp=Decimal("0.00")))


# A8 — prestador pessoa física ou MEI sem nenhum campo federal (retenções calculadas fora da nota).


def test_a8_dispara_para_pessoa_fisica_e_mei_sem_campos_federais():
    assert "A8" in _codigos(_dados(prestador_tipo_documento="CPF"))
    assert "A8" in _codigos(_dados(op_simp_nac="2"))


@pytest.mark.parametrize(
    "mudancas",
    [
        {"v_ret_csll": Decimal("20.00")},
        {"tp_ret_pis_cofins": "0"},
        {"prestador_tipo_documento": "CNPJ"},
    ],
    ids=["com_csll", "com_tp_pis_cofins", "cnpj_sem_federal"],
)
def test_a8_nao_dispara_com_campo_federal_ou_prestador_juridico(mudancas):
    assert "A8" not in _codigos(_dados(**mudancas))


# Conferência de vPis e vCofins com tpRetPisCofins de retenção: ambíguo, nunca somado.


def test_pis_cofins_com_retencao_declarada_e_ambiguo():
    assert "AMBIGUO_PIS_COFINS" in _codigos(
        _dados(tp_ret_pis_cofins="3", v_pis=Decimal("6.50"), v_ret_csll=Decimal("20.00"))
    )


@pytest.mark.parametrize("tp", ["0", "2"])
def test_pis_cofins_sem_retencao_nao_e_ambiguo(tp):
    assert "AMBIGUO_PIS_COFINS" not in _codigos(
        _dados(tp_ret_pis_cofins=tp, v_pis=Decimal("6.50"), v_cofins=Decimal("30.00"))
    )
