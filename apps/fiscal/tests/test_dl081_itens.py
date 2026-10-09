"""DL-081 (frente A), leitura dos itens da NF-e (item 2 da consulta de 09/10/2026).

Conferências: campo ausente é `None` (nunca zero); valor fora do padrão do XSD torna a nota
"itens ilegíveis" com o campo nomeado e nenhum item gravado; a leitura é idempotente; a receita
por item é `vProd − vDesc + vFrete + vSeg + vOutro` com os valores escritos à mão.
"""

import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal import itens_nfe
from apps.fiscal.models import ItemNFe, LeituraItensNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests import xml_nfe_itens_xsd_dl081 as xsd
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
            # IPI com cEnq, como o XSD exige (TIpi, leiauteNFe_v4.00.xsd:7579).
            ipi_xml=(
                "<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>1000.00</vBC><pIPI>5.00</pIPI>"
                "<vIPI>50.00</vIPI></IPITrib></IPI>"
            ),
            ii_xml="<II><vBC>1000.00</vBC><vII>12.00</vII></II>",
            # ISSQN não entra aqui: com ICMS, o XSD (linha 2117) não aceita. Ver o teste de ISSQN.
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
    assert item.v_issqn is None
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


def test_imposto_sem_icms_com_pis_e_cofins_e_lido_com_icms_none(escritorio_a, gestor, emitente):
    """Correção da rodada 1 (A1). O choice ICMS/ISSQN do `imposto` é `minOccurs="0"` (linha 2117):
    sem ICMS e sem ISSQN, o item é válido, e o leitor NÃO recusa. Antes desta correção, esta nota
    virava "itens ilegíveis" por erro do leitor."""
    dets = [xsd.det(1, xsd.PIS_NT + xsd.COFINS_NT)]
    documento = _nota_xsd(escritorio_a, gestor, dets)
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = ItemNFe.objects.get(documento=documento)
    assert item.csosn is None and item.cst is None and item.orig is None
    assert item.v_icms is None and item.v_bc is None and item.v_icms_st is None


def test_ipi_ou_ii_sem_icms_nem_issqn_e_ilegivel(escritorio_a, gestor, emitente):
    """O choice do `imposto` (linha 2117) não aceita IPI solto: IPI só existe com ICMS ou com ISSQN.
    Esta combinação também é recusada pelo XSD (ver o teste de validação com xmllint)."""
    imposto = f"<IPI><cEnq>999</cEnq>{xsd.IPI_TRIB_50}</IPI>{xsd.PIS_NT}"
    documento = _nota_xsd(escritorio_a, gestor, [xsd.det(1, imposto)])
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "IPI ou II sem grupo ICMS nem ISSQN" in leitura.motivo
    assert not ItemNFe.objects.filter(documento=documento).exists()


def _nota_xsd(escritorio, gestor, dets, vnf="100.00"):
    """Nota de itens válida contra o XSD (corpus de `xml_nfe_itens_xsd_dl081`)."""
    return receber(escritorio, gestor, xsd.nfe_com_itens(dets, vnf=vnf))


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


# --- Correção da rodada 1 (A1): XML válido contra o XSD, lido como lido ---------------------------
# Os três casos do relatório saem "lida", com v_ipi e v_issqn certos e ICMS None. A rodada 1 dava
# "IPI com mais de um grupo: 2", "grupo ICMS ausente no imposto" e a mesma mensagem para o `imposto`
# vazio. Todos os XML destes testes são válidos contra o XSD (ver a validação com xmllint abaixo).


def test_ipi_com_cenq_e_lido_como_lida(escritorio_a, gestor, emitente):
    """Caso 1 do relatório: IPI com `cEnq` (leiauteNFe_v4.00.xsd:7579, linha 7611)."""
    documento = _nota_xsd(
        escritorio_a,
        gestor,
        [xsd.det(1, xsd.ICMS_SN102 + xsd.IPI_COM_CENQ + xsd.PIS_NT + xsd.COFINS_NT)],
    )
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = ItemNFe.objects.get(documento=documento)
    assert item.cst_ipi == "50" and item.v_ipi == Decimal("5.00")
    assert item.csosn == "102"


def test_ipi_com_cnpjprod_selo_e_cenq_nao_confunde_os_filhos_com_o_grupo(
    escritorio_a, gestor, emitente
):
    """CNPJProd, cSelo, qSelo e cEnq são filhos de IPI, mas não são o grupo. O grupo é o IPITrib.
    Com IPINT (sem vIPI), o leitor devolve `v_ipi` None, e não erro."""
    documento = _nota_xsd(
        escritorio_a,
        gestor,
        [
            xsd.det(1, xsd.ICMS_SN102 + xsd.IPI_COM_OPCIONAIS + xsd.PIS_NT + xsd.COFINS_NT),
            xsd.det(2, xsd.ICMS_SN102 + xsd.IPI_NT_COM_CENQ + xsd.PIS_NT + xsd.COFINS_NT),
        ],
    )
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    itens = {i.n_item: i for i in ItemNFe.objects.filter(documento=documento)}
    assert itens[1].cst_ipi == "50" and itens[1].v_ipi == Decimal("5.00")
    assert itens[2].cst_ipi == "53" and itens[2].v_ipi is None


def test_item_so_com_issqn_cfop_5933_e_lido_com_v_issqn_e_icms_none(escritorio_a, gestor, emitente):
    """Caso 2 do relatório: serviço conjugado, CFOP 5.933, só ISSQN no `imposto`."""
    documento = _nota_xsd(
        escritorio_a,
        gestor,
        [xsd.det(1, xsd.ISSQN_SERVICO + xsd.PIS_NT + xsd.COFINS_NT, cfop="5933")],
    )
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = ItemNFe.objects.get(documento=documento)
    assert item.v_issqn == Decimal("5.00")
    assert item.csosn is None and item.cst is None and item.v_icms is None
    assert item.cfop == "5933"
    assert item.receita_bruta_item == Decimal("100.00")


def test_imposto_vazio_e_lido_com_icms_none(escritorio_a, gestor, emitente):
    """Caso 3 do relatório: `imposto` sem nenhum filho. O XSD aceita (linha 2106 e seguintes)."""
    documento = _nota_xsd(escritorio_a, gestor, [xsd.det(1, "")])
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = ItemNFe.objects.get(documento=documento)
    assert item.csosn is None and item.v_icms is None
    assert item.v_ipi is None and item.v_issqn is None


@pytest.mark.parametrize(
    ("nome", "imposto", "trecho_no_motivo"),
    [
        # ICMS e ISSQN no mesmo item: o choice aceita um ou outro (linha 2117).
        (
            "icms_e_issqn",
            xsd.ICMS_SN102 + xsd.ISSQN_SERVICO + xsd.PIS_NT,
            "ICMS e ISSQN no mesmo item",
        ),
        # IPI sem ICMS nem ISSQN: o choice não aceita.
        (
            "ipi_sem_icms_nem_issqn",
            f"<IPI><cEnq>999</cEnq>{xsd.IPI_TRIB_50}</IPI>{xsd.PIS_NT}",
            "IPI ou II sem grupo ICMS nem ISSQN",
        ),
        # II sem ICMS nem ISSQN: idem.
        (
            "ii_sem_icms_nem_issqn",
            "<II><vBC>100.00</vBC><vII>1.00</vII></II>" + xsd.PIS_NT,
            "IPI ou II sem grupo ICMS nem ISSQN",
        ),
        # Dois grupos de IPI: IPITrib e IPINT juntos, o XSD exige um.
        (
            "dois_grupos_de_ipi",
            xsd.ICMS_SN102
            + f"<IPI><cEnq>999</cEnq>{xsd.IPI_TRIB_50}<IPINT><CST>53</CST></IPINT></IPI>"
            + xsd.PIS_NT,
            "IPI sem grupo IPITrib ou IPINT único (encontrados: 2)",
        ),
    ],
)
def test_combinacao_que_o_xsd_recusa_e_ilegivel_com_motivo(
    escritorio_a, gestor, emitente, nome, imposto, trecho_no_motivo
):
    documento = _nota_xsd(escritorio_a, gestor, [xsd.det(1, imposto)])
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL, nome
    assert trecho_no_motivo in leitura.motivo
    assert not ItemNFe.objects.filter(documento=documento).exists()


# --- Versão do leitor (A1 e A12): leitura antiga é refeita --------------------------------------


def test_leitura_gravada_pela_versao_1_e_refeita_e_vira_lida(escritorio_a, gestor, emitente):
    """Uma leitura da rodada 1 recusava o IPI com `cEnq`. Gravada com versão 1, ela é refeita na
    próxima tentativa e substitui a antiga: sem duplicar itens nem deixar duas leituras."""
    documento = _nota_xsd(
        escritorio_a,
        gestor,
        [xsd.det(1, xsd.ICMS_SN102 + xsd.IPI_COM_CENQ + xsd.PIS_NT + xsd.COFINS_NT)],
    )
    LeituraItensNFe.objects.create(
        documento=documento,
        estado=LeituraItensNFe.ESTADO_ILEGIVEL,
        motivo="IPI com mais de um grupo: 2",
        versao_leitor=1,
    )
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    assert leitura.versao_leitor == itens_nfe.VERSAO_LEITOR_ITENS
    assert LeituraItensNFe.objects.filter(documento=documento).count() == 1
    assert ItemNFe.objects.filter(documento=documento).count() == 1


def test_versao_do_leitor_atual_e_gravada_e_nao_e_refeita(escritorio_a, gestor, emitente):
    documento = _nota(escritorio_a, gestor, [xml.det(1, vprod="100.00")], vnf="100.00")
    primeira = _ler(documento)
    assert primeira.versao_leitor == itens_nfe.VERSAO_LEITOR_ITENS == 2
    assert _ler(documento).pk == primeira.pk


@pytest.fixture
def emitente_xsd(escritorio_a):
    """Empresa com o CNPJ do corpus XSD (`xml_nfe_itens_xsd_dl081`), para o vínculo da nota."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Itens XSD Ltda", cnpj=xsd.CNPJ_EMITENTE
    )


def test_releitura_nao_troca_leitura_de_versao_anterior_com_escrituracao_efetivada(
    escritorio_a, gestor, emitente_xsd
):
    """Com escrituração efetivada, a leitura de versão anterior fica como está: os itens são
    imutáveis no banco (gatilho da 0011), e a releitura não tenta trocá-los.

    O estado da rodada 1 (efetivada com a leitura antiga) não se monta pelo app, porque a
    efetivação recusa versão antiga e o gatilho recusa a troca depois. Por isso o teste DESATIVA o
    gatilho de leitura, na própria transação do teste, para gravar a versão 1, e o reativa.
    """
    documento = _nota_xsd(escritorio_a, gestor, [xsd.det(1, xsd.ICMS_SN102 + xsd.PIS_NT)])
    _ler(documento)
    _rascunho_com_natureza(escritorio_a, gestor, emitente_xsd, documento)
    _efetivar(documento, gestor)
    with connection.cursor() as cur:
        # As checagens de chave estrangeira são adiadas até o fim da transação, e o ALTER não roda
        # com evento pendente. Forçar as checagens agora resolve, sem mudar o resultado.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute(
            "ALTER TABLE fiscal_leituraitensnfe DISABLE TRIGGER trg_leitura_itens_nfe_imutavel"
        )
        cur.execute(
            "UPDATE fiscal_leituraitensnfe SET versao_leitor = 1 WHERE documento_id = %s",
            [documento.pk],
        )
        cur.execute(
            "ALTER TABLE fiscal_leituraitensnfe ENABLE TRIGGER trg_leitura_itens_nfe_imutavel"
        )

    leitura = _ler(documento)
    assert leitura.versao_leitor == 1
    assert ItemNFe.objects.filter(documento=documento).count() == 1


def _rascunho_com_natureza(escritorio, gestor, emitente, documento):
    """Rascunho e natureza de revenda em todos os itens, pelos serviços (sem SQL)."""
    from apps.fiscal import escrituracao_nfe as servico
    from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
    from apps.fiscal.tests.suporte_dl081 import vinculo

    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, ids, gestor)
    return esc


def _efetivar(documento, gestor):
    from apps.fiscal import escrituracao_nfe as servico
    from apps.fiscal.models import EscrituracaoNFe

    return servico.efetivar(EscrituracaoNFe.objects.get(vinculo__documento=documento), gestor)


# --- Valor acima do campo (A5): nota ilegível, nunca erro de servidor ---------------------------


def test_receita_do_item_acima_do_limite_e_ilegivel_sem_erro_de_banco(
    escritorio_a, gestor, emitente
):
    """A5: vProd 9.999.999.999.999,99 mais vFrete 5,00 passa do numeric(15,2). A nota fica ilegível
    com o motivo, e nenhum item é gravado. Antes, a gravação estourava com DataError (500)."""
    det_grande = xml.det(1, vprod="9999999999999.99", vfrete="5.00")
    documento = _nota(escritorio_a, gestor, [det_grande], vnf="9999999999999.99")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "receita do item acima do limite" in leitura.motivo
    assert not ItemNFe.objects.filter(documento=documento).exists()


def test_soma_das_receitas_acima_do_limite_e_ilegivel(escritorio_a, gestor, emitente):
    """Cada item cabe (abaixo de 10^13), mas a soma não: `soma_itens` da escrituração também é
    numeric(15,2). O vNF fica dentro do XSD (13 inteiros); a soma dos itens é que estoura."""
    dets = [
        xml.det(1, vprod="9999999999999.99"),
        xml.det(2, vprod="9999999999999.99"),
    ]
    documento = _nota(escritorio_a, gestor, dets, vnf="9999999999999.99")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "soma da receita dos itens acima do limite" in leitura.motivo


def test_valor_que_o_banco_recusa_vira_ilegivel_nao_500(
    escritorio_a, gestor, emitente, monkeypatch
):
    """Defesa em profundidade (A5): se a checagem do leitor deixar passar um valor que o banco
    recusa, o DataError é capturado. A nota vira ilegível, nada parcial fica gravado, e a chamada
    não estoura. Aqui o valor é forjado depois do parse, então o banco é o que recusa, de
    verdade."""
    original = itens_nfe._ler_itens_do_xml

    def forjado(xml_bytes):
        itens, totais = original(xml_bytes)
        itens[0]["receita_bruta_item"] = Decimal("10000000000000.00")
        return itens, totais

    monkeypatch.setattr(itens_nfe, "_ler_itens_do_xml", forjado)
    documento = _nota(escritorio_a, gestor, [xml.det(1, vprod="100.00")], vnf="100.00")
    leitura = _ler(documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "limite de um campo monetário" in leitura.motivo
    assert not ItemNFe.objects.filter(documento=documento).exists()


# --- Validação contra o XSD (só com xmllint e a pasta dos XSD) -----------------------------------


def test_todo_caso_do_corpus_xsd_e_lido_pelo_leitor_real(escritorio_a, gestor, emitente):
    """A leitura do corpus roda SEMPRE (sem xmllint): cada caso válido sai "lida". O que o XSD
    aceita, o leitor lê; a validação com xmllint, quando há o binário, prova a outra metade."""
    for nome, dets in sorted(_CASOS_VALIDOS.items()):
        documento = _nota_xsd(escritorio_a, gestor, dets)
        assert _ler(documento).estado == LeituraItensNFe.ESTADO_LIDA, nome


_XMLLINT = shutil.which("xmllint")
_DIR_XSD = os.environ.get("DL080_XSD_DIR", "")

_CASOS_VALIDOS = {
    # Casos que já existiam nas fixtures da rodada 1, agora validados contra o XSD.
    "icms_st_csosn500": [xsd.det(1, xsd.ICMS_SN500_ST + xsd.PIS_NT + xsd.COFINS_NT, cfop="5405")],
    "todos_os_grupos_legiveis": [
        xsd.det(
            1,
            # Ordem do XSD (linha 2117): ICMS, depois IPI, depois II; PIS e Cofins por último.
            xsd.ICMS_00 + xsd.IPI_COM_CENQ + xsd.II_XML + xsd.PIS_ALIQ + xsd.COFINS_ALIQ,
        )
    ],
    "ipi_com_cenq": [xsd.det(1, xsd.ICMS_SN102 + xsd.IPI_COM_CENQ + xsd.PIS_NT + xsd.COFINS_NT)],
    "ipi_com_opcionais_e_nt": [
        xsd.det(1, xsd.ICMS_SN102 + xsd.IPI_COM_OPCIONAIS + xsd.PIS_NT + xsd.COFINS_NT),
        xsd.det(2, xsd.ICMS_SN102 + xsd.IPI_NT_COM_CENQ + xsd.PIS_NT + xsd.COFINS_NT),
    ],
    "so_issqn_cfop_5933": [
        xsd.det(1, xsd.ISSQN_SERVICO + xsd.PIS_NT + xsd.COFINS_NT, cfop="5933"),
    ],
    "imposto_vazio": [xsd.det(1, "")],
    "imposto_so_pis_e_cofins": [xsd.det(1, xsd.PIS_NT + xsd.COFINS_NT)],
}

_CASOS_RECUSADOS = {
    "icms_e_issqn": [xsd.det(1, xsd.ICMS_SN102 + xsd.ISSQN_SERVICO + xsd.PIS_NT)],
    "ipi_sem_cenq": [xsd.det(1, xsd.ICMS_SN102 + f"<IPI>{xsd.IPI_TRIB_50}</IPI>" + xsd.PIS_NT)],
    "ipi_sem_icms_nem_issqn": [
        xsd.det(1, f"<IPI><cEnq>999</cEnq>{xsd.IPI_TRIB_50}</IPI>{xsd.PIS_NT}")
    ],
}

if _XMLLINT and _DIR_XSD and Path(_DIR_XSD, "procNFe_v4.00.xsd").is_file():

    def _valida(tmp_path, nome, conteudo):
        arquivo = tmp_path / f"{nome}.xml"
        arquivo.write_bytes(conteudo)
        return subprocess.run(
            [
                _XMLLINT,
                "--noout",
                "--schema",
                str(Path(_DIR_XSD, "procNFe_v4.00.xsd")),
                str(arquivo),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    @pytest.mark.parametrize("nome", sorted(_CASOS_VALIDOS))
    def test_corpus_de_itens_valida_contra_o_procnfe_xsd(tmp_path, nome):
        resultado = _valida(tmp_path, nome, xsd.nfe_com_itens(_CASOS_VALIDOS[nome]))
        assert resultado.returncode == 0, resultado.stderr

    @pytest.mark.parametrize("nome", sorted(_CASOS_RECUSADOS))
    def test_combinacao_recusada_pelo_leitor_tambem_e_recusada_pelo_xsd(tmp_path, nome):
        """Prova que o leitor não é mais permissivo que o XSD: cada caso recusado pelo leitor
        falha na validação do schema."""
        resultado = _valida(tmp_path, nome, xsd.nfe_com_itens(_CASOS_RECUSADOS[nome]))
        assert resultado.returncode != 0
