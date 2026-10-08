"""DL-076 (frente A), critério 1: os campos de ISS batem com o XSD, e ausência não vira zero.

Caminhos conferidos nos XSD v1.00 e v1.01 (ver `apps/fiscal/iss_nota.py`). Os valores
esperados são escritos À MÃO, como texto, e comparados com o `Decimal` lido.
"""

from decimal import Decimal

import pytest

from apps.fiscal import iss_nota
from apps.fiscal.iss_nota import (
    ler_campos_iss,
    subitem_de_c_trib_nac,
)
from apps.fiscal.tests.xml_iss_dl076 import xml_nfse_iss


def _ler(xml: bytes, versao: str = "1.01"):
    return ler_campos_iss(xml, versao)


def test_le_os_campos_de_iss_da_versao_1_01():
    campos = _ler(
        xml_nfse_iss(
            c_trib_nac="170101",
            c_loc_incid="1721000",
            v_serv="1000.00",
            v_desc_incond="100.00",
            v_dr="50.00",
            v_bc="850.00",
            p_aliq_aplic="5.00",
            v_iss_qn="42.50",
            tp_ret_issqn="1",
            trib_issqn="1",
        )
    )
    assert campos.erro_leitura is None
    assert campos.c_loc_incid == "1721000"
    assert campos.c_trib_nac == "170101"
    assert campos.subitem == "17.01"
    assert campos.v_serv == Decimal("1000.00")
    assert campos.v_desc_incond == Decimal("100.00")
    assert campos.v_dr == Decimal("50.00")
    assert campos.v_bc == Decimal("850.00")
    assert campos.p_aliq_aplic == Decimal("5.00")
    assert campos.v_iss_qn == Decimal("42.50")
    assert campos.tp_ret_issqn == "1"
    assert campos.trib_issqn == "1"
    # Sem vCalcDR no XML: é opcional no XSD, então fica NOMEADO como ausente, não zero.
    assert campos.v_calc_dr is None
    assert "NFSe/infNFSe/valores/vCalcDR" in campos.ausentes
    assert campos.invalidos == ()


def test_mesmos_caminhos_na_versao_1_00():
    campos = _ler(
        xml_nfse_iss(versao="1.00", v_bc="1000.00", p_aliq_aplic="2.00", v_iss_qn="20.00"),
        "1.00",
    )
    assert campos.erro_leitura is None
    assert campos.v_bc == Decimal("1000.00")
    assert campos.p_aliq_aplic == Decimal("2.00")
    assert campos.v_iss_qn == Decimal("20.00")
    assert campos.subitem == "17.01"


@pytest.mark.parametrize(
    ("c_trib_nac", "subitem"),
    [("070201", "07.02"), ("170601", "17.06"), ("140101", "14.01"), ("010101", "01.01")],
)
def test_subitem_e_o_par_de_digitos_do_meio_do_codigo_nacional(c_trib_nac, subitem):
    # cTribNac = item(2) + subitem(2) + desdobro(2) (TSCodTribNac, 6 dígitos).
    # Os 2 últimos (desdobro) não entram no subitem.
    assert subitem_de_c_trib_nac(c_trib_nac) == subitem
    assert _ler(xml_nfse_iss(c_trib_nac=c_trib_nac)).subitem == subitem


def test_campo_ausente_vira_none_e_e_nomeado_nunca_zero():
    campos = _ler(xml_nfse_iss(omitir=frozenset({"vBC"})))
    assert campos.v_bc is None
    assert "NFSe/infNFSe/valores/vBC" in campos.ausentes


@pytest.mark.parametrize(
    ("omitido", "atributo", "caminho"),
    [
        ("vISSQN", "v_iss_qn", "NFSe/infNFSe/valores/vISSQN"),
        ("pAliqAplic", "p_aliq_aplic", "NFSe/infNFSe/valores/pAliqAplic"),
        ("cLocIncid", "c_loc_incid", "NFSe/infNFSe/cLocIncid"),
        ("cTribNac", "c_trib_nac", "NFSe/infNFSe/DPS/infDPS/serv/cServ/cTribNac"),
    ],
)
def test_ausencia_de_cada_campo_e_nomeada_e_nunca_zero(omitido, atributo, caminho):
    campos = _ler(xml_nfse_iss(omitir=frozenset({omitido})))
    assert getattr(campos, atributo) is None
    assert caminho in campos.ausentes
    if atributo == "c_trib_nac":
        assert campos.subitem is None


def test_campos_opcionais_do_xsd_ausentes_ficam_none_e_nomeados():
    # vDescCondIncond, vDedRed e vCalcDR são minOccurs=0 no XSD. Ausência não é zero: fica
    # nomeada, e quem usa decide o que a ausência significa.
    campos = _ler(xml_nfse_iss())
    assert campos.v_desc_incond is None
    assert campos.v_dr is None
    assert campos.v_calc_dr is None
    assert "NFSe/infNFSe/DPS/infDPS/valores/vDescCondIncond/vDescIncond" in campos.ausentes


def test_valor_com_virgula_e_recusado_como_invalido_nao_convertido():
    campos = _ler(xml_nfse_iss(v_iss_qn="50,00"))
    assert campos.v_iss_qn is None
    assert "NFSe/infNFSe/valores/vISSQN" in campos.invalidos
    assert "NFSe/infNFSe/valores/vISSQN" not in campos.ausentes


def test_aliquota_fora_do_tipo_tsdec1v2_e_invalida():
    # TSDec1V2: uma casa inteira e, no máximo, duas decimais. "5.000" não casa.
    campos = _ler(xml_nfse_iss(p_aliq_aplic="5.000"))
    assert campos.p_aliq_aplic is None
    assert "NFSe/infNFSe/valores/pAliqAplic" in campos.invalidos


def test_codigo_de_municipio_com_seis_digitos_e_invalido():
    # TSCodMunIBGE: exatamente 7 dígitos.
    campos = _ler(xml_nfse_iss(c_loc_incid="172100"))
    assert campos.c_loc_incid is None
    assert "NFSe/infNFSe/cLocIncid" in campos.invalidos


def test_tp_ret_issqn_fora_do_dominio_e_invalido():
    # TSTipoRetISSQN: enumeração {1, 2, 3}. O código 4 não existe.
    campos = _ler(xml_nfse_iss(tp_ret_issqn="4"))
    assert campos.tp_ret_issqn is None
    assert "NFSe/infNFSe/DPS/infDPS/valores/trib/tribMun/tpRetISSQN" in campos.invalidos


def test_retencao_2_e_3_sao_lidas_como_texto():
    assert _ler(xml_nfse_iss(tp_ret_issqn="2")).tp_ret_issqn == "2"
    assert _ler(xml_nfse_iss(tp_ret_issqn="3")).tp_ret_issqn == "3"


def test_vissqn_no_caminho_errado_nao_e_lido():
    # vISSQN fica em infNFSe/valores (TCValoresNFSe). Posto dentro de DPS/infDPS/valores,
    # ele não é o imposto da nota: a leitura tem de dar ausente.
    xml = xml_nfse_iss(omitir=frozenset({"vISSQN"})).decode("utf-8")
    xml_errado = xml.replace("<vServPrest>", "<vISSQN>50.00</vISSQN><vServPrest>", 1)
    assert xml_errado != xml
    campos = _ler(xml_errado.encode("utf-8"))
    assert campos.v_iss_qn is None
    assert "NFSe/infNFSe/valores/vISSQN" in campos.ausentes


def test_xml_ilegivel_nao_levanta_e_vira_erro_de_leitura():
    campos = _ler(b"<NFSe xmlns='http://www.sped.fazenda.gov.br/nfse'><infNFSe")
    assert campos.erro_leitura is not None
    assert campos.v_iss_qn is None
    assert campos.v_bc is None


def test_xml_vazio_e_raiz_de_outro_namespace_viram_erro_de_leitura():
    assert _ler(b"").erro_leitura is not None
    outro = b"<NFSe xmlns='urn:outro'><infNFSe/></NFSe>"
    assert _ler(outro).erro_leitura == "elemento raiz diferente de NFSe"


def test_versao_sem_leitura_e_recusada_sem_levantar():
    campos = ler_campos_iss(xml_nfse_iss(), "2.00")
    assert campos.erro_leitura is not None


def test_todo_valor_monetario_e_decimal_nunca_float():
    campos = _ler(xml_nfse_iss(v_desc_incond="10.00", v_dr="5.00", v_bc="985.00"))
    for valor in (
        campos.v_serv,
        campos.v_desc_incond,
        campos.v_dr,
        campos.v_calc_dr,
        campos.v_bc,
        campos.p_aliq_aplic,
        campos.v_iss_qn,
    ):
        assert valor is None or isinstance(valor, Decimal)
        assert not isinstance(valor, float)


def test_divergencia_de_base_sem_aviso_quando_bate():
    campos = _ler(
        xml_nfse_iss(v_serv="1000.00", v_desc_incond="100.00", v_dr="50.00", v_bc="850.00")
    )
    assert iss_nota.divergencia_de_base(campos) is None


def test_divergencia_de_base_avisa_quando_vbc_nao_bate_com_os_termos():
    campos = _ler(
        xml_nfse_iss(v_serv="1000.00", v_desc_incond="100.00", v_dr="50.00", v_bc="900.00")
    )
    aviso = iss_nota.divergencia_de_base(campos)
    assert aviso is not None
    assert "900" in aviso and "850" in aviso


def test_divergencia_de_base_termo_opcional_ausente_conta_como_zero():
    # Decisão do arquiteto (DL-076, auditoria A10, dúvida 4): vDescIncond é minOccurs=0 e, ausente,
    # conta como zero no aviso. Com vServ 1000 e vBC 900 sem nenhum termo, a recomposição é 1000,
    # e o aviso mostra esse número e diz que o opcional ausente vale zero.
    campos = _ler(xml_nfse_iss(v_serv="1000.00", v_bc="900.00"))
    aviso = iss_nota.divergencia_de_base(campos)
    assert aviso is not None
    assert "(1000.00)" in aviso and "contam como zero" in aviso


def test_divergencia_de_base_silenciosa_quando_vbc_igual_a_vserv_sem_termos():
    campos = _ler(xml_nfse_iss(v_serv="1000.00", v_bc="1000.00"))
    assert iss_nota.divergencia_de_base(campos) is None
