"""DL-081 (frente A), leitura dos itens da NF-e (item 2 da consulta de 09/10/2026).

Conferências: campo ausente é `None` (nunca zero); valor fora do padrão do XSD torna a nota
"itens ilegíveis" com o campo nomeado e nenhum item gravado; a leitura é idempotente; a receita
por item é `vProd − vDesc + vFrete + vSeg + vOutro` com os valores escritos à mão.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import itens_nfe
from apps.fiscal.models import ItemNFe, LeituraItensNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-itens-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Itens Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _nota(escritorio, gestor, dets, **kwargs):
    kwargs.setdefault("vnf", "1000.00")
    return receber(escritorio, gestor, xml.nfe(dets=dets, **kwargs))


def _ler(documento):
    return itens_nfe.ler_itens(documento)


# --- campos lidos e campo ausente ---------------------------------------------------------------


def test_grupo_icms_csosn500_traz_st_retido_em_decimal(escritorio_a, gestor, emitente):
    dets = [
        xml.det(
            1,
            cfop="5405",
            vprod="800.00",
            icms_xml=xml.icms(
                csosn="500",
                filhos="<vBCSTRet>800.00</vBCSTRet><vICMSSTRet>96.00</vICMSSTRet>",
            ),
        )
    ]
    documento = _nota(escritorio_a, gestor, dets, vnf="800.00", totais={"vProd": "800.00"})
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = ItemNFe.objects.get(documento=documento, n_item=1)
    assert item.csosn == "500"
    assert item.cst is None
    assert item.v_bc_st_ret == Decimal("800.00")
    assert item.v_icms_st_ret == Decimal("96.00")
    assert isinstance(item.v_prod, Decimal)


def test_campo_ausente_e_none_nunca_zero(escritorio_a, gestor, emitente):
    """ICMSSN102 não tem BC nem alíquota: ficam None. vDesc, vFrete, vSeg e vOutro ausentes:
    None."""
    documento = _nota(escritorio_a, gestor, [xml.det(1, vprod="100.00")], vnf="100.00")
    _ler(documento)
    item = ItemNFe.objects.get(documento=documento)
    for campo in ("v_bc", "p_icms", "v_icms", "v_bc_st", "v_icms_st", "v_desc", "v_frete"):
        assert getattr(item, campo) is None, campo
    assert item.v_seg is None and item.v_outro is None
    assert item.cest == ""  # texto ausente vira vazio no campo de texto, nunca um código inventado


def test_todos_os_grupos_do_item_sao_lidos(escritorio_a, gestor, emitente):
    dets = [
        xml.det(
            1,
            cfop="5102",
            vprod="1000.00",
            vdesc="50.00",
            vfrete="30.00",
            vseg="5.00",
            voutro="2.00",
            cest="0100100",
            cbenef="SEM CBENEF",
            icms_xml=xml.icms(
                cst="00",
                filhos="<modBC>3</modBC><vBC>1000.00</vBC><pICMS>18.00</pICMS><vICMS>180.00</vICMS>",
            ),
            ipi_xml=(
                "<IPI><IPITrib><CST>50</CST><vBC>1000.00</vBC><pIPI>5.00</pIPI>"
                "<vIPI>50.00</vIPI></IPITrib></IPI>"
            ),
            ii_xml="<II><vBC>1000.00</vBC><vII>12.00</vII></II>",
            issqn_xml="<ISSQN><vISSQN>10.00</vISSQN></ISSQN>",
            pis_xml="<PIS><PISAliq><CST>01</CST><vBC>1000.00</vBC><pPIS>1.65</pPIS><vPIS>16.50</vPIS></PISAliq></PIS>",
            cofins_xml=(
                "<COFINS><COFINSAliq><CST>01</CST><vBC>1000.00</vBC><pCOFINS>7.60</pCOFINS>"
                "<vCOFINS>76.00</vCOFINS></COFINSAliq></COFINS>"
            ),
            icms_ufdest_xml="<ICMSUFDest><vICMSUFDest>10.00</vICMSUFDest></ICMSUFDest>",
        )
    ]
    documento = _nota(escritorio_a, gestor, dets, vnf="1000.00")
    _ler(documento)
    item = ItemNFe.objects.get(documento=documento)
    assert item.cest == "0100100"
    assert item.c_benef == "SEM CBENEF"
    assert item.cst == "00" and item.mod_bc == "3"
    assert item.v_bc == Decimal("1000.00")
    assert item.p_icms == Decimal("18.00")
    assert item.v_icms == Decimal("180.00")
    assert item.cst_ipi == "50" and item.v_ipi == Decimal("50.00")
    assert item.v_ii == Decimal("12.00")
    assert item.v_issqn == Decimal("10.00")
    assert item.cst_pis == "01" and item.v_pis == Decimal("16.50")
    assert item.cst_cofins == "01" and item.v_cofins == Decimal("76.00")
    assert item.v_icms_ufdest == Decimal("10.00")


def test_ibscbs_no_item_guarda_presenca_e_xml_bruto(escritorio_a, gestor, emitente):
    dets = [xml.det(1, vprod="100.00", ibscbs=True)]
    documento = _nota(escritorio_a, gestor, dets, vnf="100.00")
    _ler(documento)
    item = ItemNFe.objects.get(documento=documento)
    assert item.tem_ibscbs is True
    assert "IBSCBS" in item.ibscbs_xml and "cClassTrib" in item.ibscbs_xml


def test_totais_de_ii_ipidevol_vnftot_e_ibs_sao_lidos(escritorio_a, gestor, emitente):
    documento = _nota(
        escritorio_a,
        gestor,
        [xml.det(1, vprod="100.00")],
        vnf="100.00",
        totais={"vII": "3.00", "vIPIDevol": "1.00"},
        ibscbs_total=("100.00", "0.10", "0.90"),
        ibscbs_total_vnftot="101.00",
        ist_vis="0.00",
    )
    leitura = _ler(documento)
    assert leitura.v_ii == Decimal("3.00")
    assert leitura.v_ipi_devol == Decimal("1.00")
    assert leitura.v_nf_tot == Decimal("101.00")
    assert leitura.v_ibs == Decimal("0.10")
    assert leitura.v_cbs == Decimal("0.90")
    assert leitura.v_is == Decimal("0.00")


def test_totais_ausentes_sao_none(escritorio_a, gestor, emitente):
    documento = _nota(escritorio_a, gestor, [xml.det(1, vprod="100.00")], vnf="100.00")
    leitura = _ler(documento)
    assert leitura.v_ii is None and leitura.v_ipi_devol is None
    assert leitura.v_nf_tot is None and leitura.v_ibs is None and leitura.v_cbs is None


# --- valor fora do padrão do XSD: nota ilegível ------------------------------------------------


@pytest.mark.parametrize(
    ("campo_xml", "trecho", "nome_no_motivo"),
    [
        # vICMS com três casas: TDec_1302 aceita só duas (tiposBasico_v4.00.xsd:301).
        ("vICMS", "<vICMS>1.234</vICMS>", "vICMS"),
        # NCM com três dígitos: nem 2 nem 8 (leiauteNFe_v4.00.xsd:924).
        ("NCM", "<NCM>220</NCM>", "NCM"),
        # CST com letra: o CST é de dois dígitos.
        ("CST", "<CST>0A</CST>", "CST"),
        # Origem fora de 0 a 8 (Torig, leiauteNFe_v4.00.xsd:7454).
        ("orig", "<orig>9</orig>", "orig"),
    ],
)
def test_valor_fora_do_padrao_torna_a_nota_ilegivel(
    escritorio_a, gestor, emitente, campo_xml, trecho, nome_no_motivo
):
    if campo_xml in ("vICMS",):
        icms_xml = xml.icms(cst="00", filhos=trecho)
        det = xml.det(1, vprod="100.00", icms_xml=icms_xml)
    elif campo_xml == "NCM":
        det = xml.det(1, vprod="100.00", ncm="220")
    elif campo_xml == "CST":
        det = xml.det(1, vprod="100.00", icms_xml=xml.icms(cst="0A"))
    else:
        det = xml.det(
            1,
            vprod="100.00",
            icms_xml=f"<ICMS><ICMSSN102>{trecho}<CSOSN>102</CSOSN></ICMSSN102></ICMS>",
        )
    documento = _nota(escritorio_a, gestor, [det], vnf="100.00")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert nome_no_motivo in leitura.motivo
    assert not ItemNFe.objects.filter(documento=documento).exists()


def test_desconto_zero_explicito_e_ilegivel_porque_o_xsd_nao_aceita_zero_em_tag_opcional(
    escritorio_a, gestor, emitente
):
    """vDesc é TDec_1302Opc (tiposBasico_v4.00.xsd:310): `0.00` não é valor válido. Nota
    recusada."""
    documento = _nota(
        escritorio_a, gestor, [xml.det(1, vprod="100.00", vdesc="0.00")], vnf="100.00"
    )
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "vDesc" in leitura.motivo


def test_nitem_repetido_e_ilegivel(escritorio_a, gestor, emitente):
    dets = [xml.det(1, vprod="50.00"), xml.det(1, vprod="50.00")]
    documento = _nota(escritorio_a, gestor, dets, vnf="100.00")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "repetido" in leitura.motivo


def test_grupo_icms_ausente_e_ilegivel(escritorio_a, gestor, emitente):
    """O grupo ICMS é obrigatório no imposto (XSD). Sem ele, a nota não é lida como íntegra."""
    det = xml.det(1, vprod="100.00").replace(xml.icms(csosn="102"), "")
    documento = _nota(escritorio_a, gestor, [det], vnf="100.00")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "ICMS" in leitura.motivo


def test_nota_sem_itens_e_ilegivel(escritorio_a, gestor, emitente):
    documento = _nota(escritorio_a, gestor, [], vnf="0.00")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "sem itens" in leitura.motivo


# --- idempotência e receita por item --------------------------------------------------------------


def test_leitura_e_idempotente(escritorio_a, gestor, emitente):
    documento = _nota(
        escritorio_a, gestor, [xml.det(1, vprod="100.00"), xml.det(2, vprod="50.00")], vnf="150.00"
    )
    primeira = _ler(documento)
    segunda = _ler(documento)
    assert primeira.pk == segunda.pk
    assert LeituraItensNFe.objects.filter(documento=documento).count() == 1
    assert ItemNFe.objects.filter(documento=documento).count() == 2


def test_leitura_ilegivel_tambem_e_gravada_e_nao_relida(escritorio_a, gestor, emitente):
    documento = _nota(escritorio_a, gestor, [xml.det(1, vprod="100.00", ncm="2203")], vnf="100.00")
    primeira = _ler(documento)
    assert primeira.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert _ler(documento).pk == primeira.pk


def test_receita_bruta_do_item_segue_a_formula(escritorio_a, gestor, emitente):
    """vProd − vDesc + vFrete + vSeg + vOutro. Exemplo da consulta: 1.000,00 − 50,00 + 30,00 =
    980,00."""
    dets = [
        xml.det(1, vprod="1000.00", vdesc="50.00", vfrete="30.00"),
        xml.det(2, vprod="200.00", vseg="5.00", voutro="3.00"),
        xml.det(3, vprod="100.00"),
    ]
    documento = _nota(escritorio_a, gestor, dets, vnf="1518.00")
    _ler(documento)
    receitas = {i.n_item: i.receita_bruta_item for i in ItemNFe.objects.filter(documento=documento)}
    assert receitas == {1: Decimal("980.00"), 2: Decimal("208.00"), 3: Decimal("100.00")}


def test_indTot_zero_fica_gravado_e_a_receita_do_item_permanece(escritorio_a, gestor, emitente):
    """indTot 0: o vProd não compõe o total da NF-e (leiauteNFe_v4.00.xsd:1126). O item fica
    lido."""
    dets = [xml.det(1, vprod="100.00", ind_tot="0")]
    documento = _nota(escritorio_a, gestor, dets, vnf="0.00")
    _ler(documento)
    item = ItemNFe.objects.get(documento=documento)
    assert item.ind_tot == "0"
    assert item.receita_bruta_item == Decimal("100.00")


def test_receita_bruta_item_e_funcao_pura_e_nao_float():
    dados = {
        "v_prod": Decimal("0.10"),
        "v_desc": None,
        "v_frete": Decimal("0.20"),
        "v_seg": None,
        "v_outro": None,
    }
    resultado = itens_nfe.receita_bruta_do_item(dados)
    assert resultado == Decimal("0.30")
    assert isinstance(resultado, Decimal)
