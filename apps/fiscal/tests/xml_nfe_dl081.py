"""Gerador SINTÉTICO de NF-e com ITENS configuráveis — DL-081, frente A.

Estende `xml_nfe_dl080`, que emite um único `det` mínimo. Aqui cada item pode trazer o grupo de
ICMS, a alíquota, o frete, o IPI, o II, o PIS e a Cofins que o teste pede. A ordem dos elementos
segue o XSD do PL 010f (leiauteNFe_v4.00.xsd), na medida em que o leitor de itens lê os campos.

Todo CNPJ, CPF e chave é SINTÉTICO (reaproveitados de `xml_nfe_dl080`). Os valores de um teste
são escritos à mão no próprio teste: este gerador só monta o XML, não calcula total de nota.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DESTINATARIO_A,
    CNPJ_EMITENTE_A,
    NS_NFE,
    _assinatura_marcador,
    _pessoa,
    _protocolo,
    chave_nfe,
)

# Ordem dos campos do ICMSTot (leiauteNFe_v4.00.xsd:5339 em diante). Ausente no dicionário é ausente
# no XML, e o leitor devolve None para ele.
CAMPOS_ICMSTOT = (
    "vBC",
    "vICMS",
    "vICMSDeson",
    "vFCP",
    "vBCST",
    "vST",
    "vFCPST",
    "vFCPSTRet",
    "vProd",
    "vFrete",
    "vSeg",
    "vDesc",
    "vII",
    "vIPI",
    "vIPIDevol",
    "vPIS",
    "vCOFINS",
    "vOutro",
    "vNF",
)


def icms(*, csosn: str | None = None, cst: str | None = None, orig: str = "0", filhos: str = ""):
    """Grupo de ICMS. `csosn` (ICMSSN500, por exemplo) ou `cst` (ICMS60, por exemplo).

    `filhos` entra depois de `orig` e do código: é onde o teste põe `vBCSTRet`, `pCredSN` etc.
    """
    if csosn is not None:
        return (
            f"<ICMS><ICMSSN{csosn}><orig>{orig}</orig><CSOSN>{csosn}</CSOSN>"
            f"{filhos}</ICMSSN{csosn}></ICMS>"
        )
    if cst is not None:
        return f"<ICMS><ICMS{cst}><orig>{orig}</orig><CST>{cst}</CST>{filhos}</ICMS{cst}></ICMS>"
    raise ValueError("icms() precisa de csosn ou cst")


def det(
    n: int,
    *,
    cfop: str = "5102",
    vprod: str = "100.00",
    ncm: str = "22030000",
    cest: str | None = None,
    cbenef: str | None = None,
    q_com: str = "1.0000",
    v_un_com: str = "100.0000000000",
    vfrete: str | None = None,
    vseg: str | None = None,
    vdesc: str | None = None,
    voutro: str | None = None,
    ind_tot: str = "1",
    icms_xml: str | None = None,
    ipi_xml: str = "",
    ii_xml: str = "",
    issqn_xml: str = "",
    pis_xml: str | None = None,
    cofins_xml: str | None = None,
    icms_ufdest_xml: str = "",
    ibscbs: bool = False,
    prod_extra: str = "",
) -> str:
    """Um `det` (leiauteNFe_v4.00.xsd:867). `*_xml` são trechos prontos, para o teste escolher o
    caminho.

    Os campos opcionais de valor (`vfrete`, `vseg`, `vdesc`, `voutro`) só saem quando são passados:
    ausente é ausente, como o leitor espera.
    """

    def valor(tag: str, texto: str | None) -> str:
        return "" if texto is None else f"<{tag}>{texto}</{tag}>"

    cest_xml = valor("CEST", cest)
    cbenef_xml = valor("cBenef", cbenef)
    prod = (
        f"<prod><cProd>{n:06d}</cProd><cEAN>SEM GTIN</cEAN>"
        f"<xProd>Produto sintetico {n}</xProd><NCM>{ncm}</NCM>{cest_xml}{cbenef_xml}"
        f"<CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>{q_com}</qCom>"
        f"<vUnCom>{v_un_com}</vUnCom><vProd>{vprod}</vProd>"
        f"<cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>{q_com}</qTrib>"
        f"<vUnTrib>{v_un_com}</vUnTrib>"
        f"{valor('vFrete', vfrete)}{valor('vSeg', vseg)}{valor('vDesc', vdesc)}"
        f"{valor('vOutro', voutro)}"
        f"<indTot>{ind_tot}</indTot>{prod_extra}</prod>"
    )
    if icms_xml is None:
        icms_xml = icms(csosn="102")
    pis = pis_xml if pis_xml is not None else "<PIS><PISNT><CST>07</CST></PISNT></PIS>"
    cofins = (
        cofins_xml
        if cofins_xml is not None
        else ("<COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS>")
    )
    ibs = "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>" if ibscbs else ""
    imposto = (
        f"<imposto>{icms_xml}{ipi_xml}{ii_xml}{issqn_xml}{pis}{cofins}"
        f"{icms_ufdest_xml}{ibs}</imposto>"
    )
    return f'<det nItem="{n}">{prod}{imposto}</det>'


def _totais_xml(totais: dict[str, str | None], vnf: str) -> str:
    """ICMSTot com os campos dados. `vNF` é sempre o que o teste escreveu, nunca calculado aqui."""
    valores = {campo: totais[campo] for campo in CAMPOS_ICMSTOT if totais.get(campo) is not None}
    valores["vNF"] = vnf
    corpo = "".join(
        f"<{campo}>{valores[campo]}</{campo}>" for campo in CAMPOS_ICMSTOT if campo in valores
    )
    return f"<ICMSTot>{corpo}</ICMSTot>"


def nfe(
    *,
    dets: list[str],
    vnf: str,
    totais: dict[str, str | None] | None = None,
    modelo: str = "55",
    serie: str = "1",
    numero: str = "1",
    tp_nf: str = "1",
    fin_nfe: str = "1",
    id_dest: str = "1",
    dh_emi: str = "2026-03-15T10:00:00-03:00",
    emitente: tuple[str, str] = ("CNPJ", CNPJ_EMITENTE_A),
    emitente_nome: str = "Emitente Sintetico Ltda",
    crt: str | None = "3",
    destinatario: tuple[str, str] | None = ("CNPJ", CNPJ_DESTINATARIO_A),
    destinatario_nome: str = "Destinatario Sintetico Ltda",
    chave: str | None = None,
    ist_vis: str | None = None,
    ibscbs_total_vnftot: str | None = None,
    ibscbs_total: tuple[str, str, str] | None = None,
    c_stat: str = "100",
    dh_recbto: str = "2026-03-15T10:01:00-03:00",
) -> bytes:
    """`nfeProc` sintética. Totais e `vNF` escritos pelo teste. `ibscbs_total` é (vBCIBSCBS,
    vIBS, vCBS).

    `ist_vis` põe `ISTot/vIS`; `ibscbs_total_vnftot` põe `total/vNFTot` (LEIAUTE: depois de
    IBSCBSTot).
    """
    tipo_emit, documento_emit = emitente
    if chave is None:
        chave = chave_nfe(
            emitente=documento_emit.zfill(14) if tipo_emit == "CPF" else documento_emit,
            modelo=modelo,
            serie=serie,
            numero=numero,
        )
    crt_xml = f"<CRT>{crt}</CRT>" if crt is not None else ""
    emit = _pessoa("emit", tipo_emit, documento_emit, emitente_nome).replace(
        "</emit>", f"{crt_xml}</emit>"
    )
    dest = ""
    if destinatario is not None:
        dest = _pessoa("dest", destinatario[0], destinatario[1], destinatario_nome)
    ide = (
        "<ide>"
        f"<cUF>{chave[:2]}</cUF><cNF>{chave[35:43]}</cNF><natOp>Venda sintetica</natOp>"
        f"<mod>{modelo}</mod><serie>{int(serie)}</serie><nNF>{int(numero)}</nNF>"
        f"<dhEmi>{dh_emi}</dhEmi><tpNF>{tp_nf}</tpNF><idDest>{id_dest}</idDest>"
        "<cMunFG>3550308</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis>"
        f"<cDV>{chave[43]}</cDV><tpAmb>1</tpAmb><finNFe>{fin_nfe}</finNFe>"
        "<indFinal>1</indFinal><indPres>1</indPres><procEmi>0</procEmi>"
        "<verProc>sintetico-dl081</verProc></ide>"
    )
    valores = dict(totais or {})
    icmstot = _totais_xml(valores, vnf)
    istot = f"<ISTot><vIS>{ist_vis}</vIS></ISTot>" if ist_vis is not None else ""
    ibs_tot = ""
    if ibscbs_total is not None:
        vbc, vibs, vcbs = ibscbs_total
        ibs_tot = (
            f"<IBSCBSTot><vBCIBSCBS>{vbc}</vBCIBSCBS><gIBS><vIBS>{vibs}</vIBS></gIBS>"
            f"<gCBS><vCBS>{vcbs}</vCBS></gCBS></IBSCBSTot>"
        )
    vnftot = f"<vNFTot>{ibscbs_total_vnftot}</vNFTot>" if ibscbs_total_vnftot is not None else ""
    total = f"<total>{icmstot}{istot}{ibs_tot}{vnftot}</total>"
    inf = (
        f'<infNFe Id="NFe{chave}" versao="4.00">{ide}{emit}{dest}{"".join(dets)}{total}'
        "<transp><modFrete>9</modFrete></transp></infNFe>"
    )
    protocolo = _protocolo(chave, c_stat, dh_recbto, "135260000000001")
    texto = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<nfeProc xmlns="{NS_NFE}" versao="4.00"><NFe>{inf}{_assinatura_marcador()}</NFe>'
        f"{protocolo}</nfeProc>"
    )
    return texto.encode("utf-8")


def texto_seguro(valor: str) -> str:
    """Escapa texto para XML (usado quando o teste põe caractere especial no nome do produto)."""
    return escape(valor)
