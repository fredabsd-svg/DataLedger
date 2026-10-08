"""DL-078, critério 1: os campos de tomada batem com o XSD, nas duas versões, e ausência não é zero.

Teste puro: nenhuma gravação. Valores escritos à mão a partir do XML sintético.
Os caminhos citados nas asserções são os de `apps/fiscal/tomadas_campos.py`, conferidos no
pacote oficial (XSD 1.00 e 1.01).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.tests.xml_tomada_dl078 import xml_tomada
from apps.fiscal.tomadas_campos import ler_campos_tomada

# Valores sintéticos escritos à mão. Prestador do Simples (3), federais retidos, ISS retido (2).
VALORES = {
    "v_serv": "1000.00",
    "v_desc_incond": "10.00",
    "v_desc_cond": "5.00",
    "v_liq": "889.00",
    "v_iss_qn": "50.00",
    "v_ret_cp": "11.00",
    "v_ret_irrf": "15.00",
    "v_ret_csll": "20.00",
    "v_pis": "6.50",
    "v_cofins": "30.00",
}


def _xml(versao="1.01", **mudancas):
    dados = {
        "versao": versao,
        "v_serv": VALORES["v_serv"],
        "v_desc_incond": VALORES["v_desc_incond"],
        "v_desc_cond": VALORES["v_desc_cond"],
        "v_liq": VALORES["v_liq"],
        "v_iss_qn": VALORES["v_iss_qn"],
        "tp_ret_issqn": "2",
        "c_loc_incid": "1721000",
        "c_loc_prestacao": "1100205",
        "tp_emit": "1",
        "op_simp_nac": "3",
        "reg_ap_trib_sn": "1",
        "v_ret_cp": VALORES["v_ret_cp"],
        "v_ret_irrf": VALORES["v_ret_irrf"],
        "v_ret_csll": VALORES["v_ret_csll"],
        "tp_ret_pis_cofins": "3",
        "v_pis": VALORES["v_pis"],
        "v_cofins": VALORES["v_cofins"],
        "dh_emi": "2026-10-05T23:30:00-03:00",
    }
    dados.update(mudancas)
    versao = dados.pop("versao")
    return xml_tomada(versao=versao, **dados)


@pytest.mark.parametrize("versao", ["1.01", "1.00"])
def test_campos_federais_e_de_regime_sao_lidos_nas_duas_versoes(versao):
    campos = ler_campos_tomada(_xml(versao=versao), versao)

    assert campos.erro_leitura is None
    assert campos.ausentes == ()
    assert campos.invalidos == ()
    # NFSe/infNFSe/DPS/infDPS/dhEmi (1.01: :751 | 1.00: :301). Dia escrito no documento (HI-72).
    assert campos.data_emissao == date(2026, 10, 5)
    # NFSe/infNFSe/cLocIncid (1.01: :35 | 1.00: :44) e serv/locPrest/cLocPrestacao (1.01: :1316).
    assert campos.c_loc_incid == "1721000"
    assert campos.c_loc_prestacao == "1100205"
    # infDPS/tpEmit (1.01: :776 | 1.00: :326).
    assert campos.tp_emit == "1"
    # infNFSe/valores/vISSQN (1.01: :261 | 1.00: :251) e tribMun/tpRetISSQN (1.01: :1909).
    assert campos.v_iss_qn == Decimal("50.00")
    assert campos.tp_ret_issqn == "2"
    # infDPS/prest/regTrib/opSimpNac (1.01: :955) e regApTribSN (1.01: :965).
    assert campos.op_simp_nac == "3"
    assert campos.reg_ap_trib_sn == "1"
    # infDPS/valores/vServPrest/vServ (1.01: :1669), vDescCondIncond (1.01: :1679 e :1684).
    assert campos.v_serv == Decimal("1000.00")
    assert campos.v_desc_incond == Decimal("10.00")
    assert campos.v_desc_cond == Decimal("5.00")
    # infNFSe/valores/vLiq (1.01: :276 | 1.00: :266).
    assert campos.v_liq == Decimal("889.00")
    # infDPS/valores/trib/tribFed/vRetCP (1.01: :1996), vRetIRRF (:2003), vRetCSLL (:2010).
    assert campos.v_ret_cp == Decimal("11.00")
    assert campos.v_ret_irrf == Decimal("15.00")
    assert campos.v_ret_csll == Decimal("20.00")
    # tribFed/piscofins/tpRetPisCofins (1.01: :2098), vPis (:2084), vCofins (:2091).
    assert campos.tp_ret_pis_cofins == "3"
    assert campos.v_pis == Decimal("6.50")
    assert campos.v_cofins == Decimal("30.00")


def test_todo_valor_monetario_e_decimal_nunca_float():
    campos = ler_campos_tomada(_xml(), "1.01")

    valores = [
        campos.v_iss_qn,
        campos.v_serv,
        campos.v_desc_incond,
        campos.v_desc_cond,
        campos.v_liq,
        campos.v_ret_cp,
        campos.v_ret_irrf,
        campos.v_ret_csll,
        campos.v_pis,
        campos.v_cofins,
    ]
    assert all(isinstance(valor, Decimal) for valor in valores)


def test_ausencia_do_grupo_federal_vira_none_nomeado_e_nunca_zero():
    campos = ler_campos_tomada(_xml(federal=False), "1.01")

    assert campos.v_ret_cp is None
    assert campos.v_ret_irrf is None
    assert campos.v_ret_csll is None
    assert campos.tp_ret_pis_cofins is None
    # Nomeada, com o caminho do grupo inteiro: não é "sem retenção", é "não destacado".
    assert "NFSe/infNFSe/DPS/infDPS/valores/trib/tribFed/vRetCSLL" in campos.ausentes
    assert "NFSe/infNFSe/DPS/infDPS/valores/trib/tribFed/vRetCP" in campos.ausentes


def test_ausencia_de_vissqn_e_de_tpemit_fica_nomeada():
    campos = ler_campos_tomada(_xml(omitir=frozenset({"vISSQN", "tpEmit"})), "1.01")

    assert campos.v_iss_qn is None
    assert campos.tp_emit is None
    assert "NFSe/infNFSe/valores/vISSQN" in campos.ausentes
    assert "NFSe/infNFSe/DPS/infDPS/tpEmit" in campos.ausentes


def test_ausencia_de_regime_no_simples_fica_nomeada_e_nao_vira_mei_nem_zero():
    campos = ler_campos_tomada(_xml(omitir=frozenset({"opSimpNac", "regApTribSN"})), "1.01")

    assert campos.op_simp_nac is None
    assert campos.reg_ap_trib_sn is None
    assert "NFSe/infNFSe/DPS/infDPS/prest/regTrib/opSimpNac" in campos.ausentes


def test_valor_com_virgula_e_recusado_como_invalido_e_nao_convertido():
    campos = ler_campos_tomada(_xml(v_ret_irrf="15,00"), "1.01")

    assert campos.v_ret_irrf is None
    assert "NFSe/infNFSe/DPS/infDPS/valores/trib/tribFed/vRetIRRF" in campos.invalidos


def test_tipo_fora_do_enumerado_e_invalido():
    campos = ler_campos_tomada(_xml(op_simp_nac="4", tp_emit="9"), "1.01")

    assert campos.op_simp_nac is None
    assert campos.tp_emit is None
    assert "NFSe/infNFSe/DPS/infDPS/prest/regTrib/opSimpNac" in campos.invalidos
    assert "NFSe/infNFSe/DPS/infDPS/tpEmit" in campos.invalidos


def test_tp_ret_pis_cofins_aceita_0_a_9_e_recusa_10():
    assert ler_campos_tomada(_xml(tp_ret_pis_cofins="9"), "1.01").tp_ret_pis_cofins == "9"
    campos = ler_campos_tomada(_xml(tp_ret_pis_cofins="10"), "1.01")
    assert campos.tp_ret_pis_cofins is None
    assert campos.invalidos


def test_xml_ilegivel_nao_levanta_e_vira_erro_de_leitura():
    campos = ler_campos_tomada(b"isto nao e xml", "1.01")

    assert campos.erro_leitura is not None
    assert campos.v_ret_cp is None
    assert campos.tp_emit is None


def test_versao_sem_leitura_e_erro_de_leitura_e_nao_chute():
    campos = ler_campos_tomada(_xml(), "2.00")

    assert campos.erro_leitura is not None
    assert campos.data_emissao is None
