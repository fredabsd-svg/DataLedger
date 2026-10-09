"""Itens da NF-e, lidos do XML guardado — DL-081, frente A (item 2 da consulta de 09/10/2026).

Leitura do `xml_original` do `DocumentoNFe` (DE-074 item 1), com o mesmo leitor seguro da NFS-e e
da NF-e (`defusedxml`, DTD proibido, em `apps.fiscal.leitor._raiz_segura`). O produto LÊ os campos
e NÃO os interpreta: a apuração do ICMS é etapa própria, e lê daqui sem reabrir o XML.

Fonte dos caminhos: `leiauteNFe_v4.00.xsd` do PL 010f (pacote baixado do Portal da NF-e em
09/10/2026, só leitura, fora do repositório). Cada campo abaixo traz a linha da declaração do
elemento no XSD. Os padrões de valor são copiados do `tiposBasico_v4.00.xsd` e do
`DFeTiposBasicos_v1.00.xsd` (TDec_1302, TDec_1302Opc, TDec_1104v, TDec_1110v, TDec_0302a04,
TDec_0302a04Opc, TString, TDec1302RTC).

Regras de leitura:

- Campo ausente é `None`, nunca zero. Zero só aparece se o XML trouxer zero.
- Campo presente FORA do padrão do XSD torna a nota "itens ilegíveis": nenhum item é gravado e a
  mensagem nomeia o campo. Não há conversão silenciosa para zero nem palpite.
- A leitura é IDEMPOTENTE: o resultado, lido ou ilegível, fica gravado em `LeituraItensNFe`.
  Duas chamadas, ou duas requisições em paralelo, dão o mesmo resultado sem duplicar item.
- `receita_bruta_item` = `vProd − vDesc + vFrete + vSeg + vOutro` (HI-119). Os opcionais
  ausentes entram como zero NESSA SOMA, porque o XSD os torna opcionais: a ausência é "não há
  essa parcela". Não é uma leitura de campo ausente.

Limites declarados:

- O grupo ICMS é lido pelos nomes dos filhos. Os valores que o XSD enumera em cada grupo
  (por exemplo, a lista de `motDesICMS`) não são re-enumerados aqui: `motDesICMS` aceita dois
  dígitos, e a conferência do domínio fica para a apuração do ICMS.
- Textos (`xProd`, `cProd`, `cBenef`) seguem o padrão TString do XSD (Latin-1, sem espaço nas
  pontas). Real nota autorizada já passou pelo mesmo padrão na SEFAZ.
"""

from __future__ import annotations

import re
from decimal import Decimal
from xml.etree import ElementTree

from django.db import IntegrityError, transaction

from apps.fiscal.leitor import ArquivoRecusado, _raiz_segura
from apps.fiscal.leitor_nfe import NS_NFE
from apps.fiscal.models import DocumentoNFe, ItemNFe, LeituraItensNFe

_NS = {"n": NS_NFE}

# Padrões copiados do XSD (texto exato da expressão regular). A referência é a linha da
# declaração do tipo em `tiposBasico_v4.00.xsd` (ou `DFeTiposBasicos_v1.00.xsd`, para TDec1302RTC).
_PADRAO = {
    # tiposBasico_v4.00.xsd:301-307
    "TDec_1302": re.compile(r"0|0\.[0-9]{2}|[1-9]{1}[0-9]{0,12}(\.[0-9]{2})?"),
    # tiposBasico_v4.00.xsd:310-316 (opcional: o XSD não aceita zero em tag opcional)
    "TDec_1302Opc": re.compile(
        r"0\.[0-9]{1}[1-9]{1}|0\.[1-9]{1}[0-9]{1}|[1-9]{1}[0-9]{0,12}(\.[0-9]{2})?"
    ),
    # tiposBasico_v4.00.xsd:229-235
    "TDec_1104v": re.compile(
        r"0|0\.[0-9]{1,4}|[1-9]{1}[0-9]{0,10}|[1-9]{1}[0-9]{0,10}(\.[0-9]{1,4})?"
    ),
    # tiposBasico_v4.00.xsd:247-253
    "TDec_1110v": re.compile(
        r"0|0\.[0-9]{1,10}|[1-9]{1}[0-9]{0,10}|[1-9]{1}[0-9]{0,10}(\.[0-9]{1,10})?"
    ),
    # tiposBasico_v4.00.xsd:157-163
    "TDec_0302a04": re.compile(r"0|0\.[0-9]{2,4}|[1-9]{1}[0-9]{0,2}(\.[0-9]{2,4})?"),
    # tiposBasico_v4.00.xsd:166-172 (opcional)
    "TDec_0302a04Opc": re.compile(r"0\.[0-9]{2,4}|[1-9]{1}[0-9]{0,2}(\.[0-9]{2,4})?"),
    # tiposBasico_v4.00.xsd:519 (TString)
    "TString": re.compile(r"[!-ÿ]{1}[ -ÿ]{0,}[!-ÿ]{1}|[!-ÿ]{1}"),
    # leiauteNFe_v4.00.xsd:5305-5330 (nItem, 1 a 990)
    "nItem": re.compile(
        r"[1-9]{1}[0-9]{0,1}|[1-8]{1}[0-9]{2}|[9]{1}[0-8]{1}[0-9]{1}|[9]{1}[9]{1}[0]{1}"
    ),
    # leiauteNFe_v4.00.xsd:924 (NCM: 2 ou 8 dígitos)
    "NCM": re.compile(r"[0-9]{2}|[0-9]{8}"),
    # leiauteNFe_v4.00.xsd:947
    "CEST": re.compile(r"[0-9]{7}"),
    # leiauteNFe_v4.00.xsd:1026
    "CFOP": re.compile(r"[1-7][0-9]{3}"),
    # leiauteNFe_v4.00.xsd:972 (cBenef: 8 ou 10 caracteres, ou "SEM CBENEF")
    "cBenef": re.compile(r"[!-ÿ]{8}|[!-ÿ]{10}|SEM CBENEF"),
    # leiauteNFe_v4.00.xsd:1126-1137 (indTot: 0 não compõe vProd no total da NF-e; 1 compõe)
    "indTot": re.compile(r"0|1"),
    # leiauteNFe_v4.00.xsd:2132 (Torig, enumeração 0 a 8)
    "orig": re.compile(r"[0-8]"),
    # leiauteNFe_v4.00.xsd:2139 e 7403 (CST de dois dígitos)
    "CST": re.compile(r"[0-9]{2}"),
    # leiauteNFe_v4.00.xsd:3913 (CSOSN de três dígitos)
    "CSOSN": re.compile(r"[0-9]{3}"),
    # leiauteNFe_v4.00.xsd:2151 (modBC, enumeração 0 a 3)
    "modBC": re.compile(r"[0-3]"),
    # leiauteNFe_v4.00.xsd:2315 (modBCST, enumeração 0 a 6)
    "modBCST": re.compile(r"[0-6]"),
    # leiauteNFe_v4.00.xsd:2571 (motDesICMS: aqui só o formato de até dois dígitos)
    "motDesICMS": re.compile(r"[0-9]{1,2}"),
}

_TAMANHO = {
    "cProd": 60,
    "xProd": 120,
    "uCom": 6,
    "cBenef": 10,
    "CST": 2,
    "CSOSN": 3,
    "motDesICMS": 2,
    "NCM": 8,
    "CEST": 7,
}


class _Ilegivel(Exception):
    """Um valor do XML está fora do padrão do XSD. A mensagem nomeia o campo."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _texto(pai, caminho: str, campo: str, padrao: str, obrigatorio: bool = False):
    """Texto do filho, conferido pelo padrão do XSD. `None` se ausente e opcional."""
    achado = pai.find(caminho, _NS) if pai is not None else None
    if achado is None:
        if obrigatorio:
            raise _Ilegivel(f"campo obrigatório ausente: {campo}")
        return None
    texto = achado.text if achado.text is not None else ""
    if not _PADRAO[padrao].fullmatch(texto):
        raise _Ilegivel(f"{campo} fora do padrão do XSD: {texto!r}")
    limite = _TAMANHO.get(campo)
    if limite is not None and len(texto) > limite:
        raise _Ilegivel(f"{campo} com {len(texto)} caracteres, acima de {limite}")
    return texto


def _decimal(pai, caminho: str, campo: str, padrao: str, obrigatorio: bool = False):
    """Valor monetário ou de alíquota em `Decimal`, pelo padrão TDec do XSD. Nunca `float`."""
    texto = _texto(pai, caminho, campo, padrao, obrigatorio)
    return None if texto is None else Decimal(texto)


def _grupo_unico(pai, campo: str):
    """O filho do grupo (ICMS00, PISAliq, IPITrib...). Mais de um é recusa, nunca escolha."""
    if pai is None:
        return None
    filhos = list(pai)
    if len(filhos) > 1:
        raise _Ilegivel(f"{campo} com mais de um grupo: {len(filhos)}")
    return filhos[0] if filhos else None


def _ler_icms(imposto) -> dict:
    """ICMS, ICMS-ST, crédito do Simples e FCP. Os nomes dos campos são os do grupo.

    Cada campo fica no filho do grupo (ICMS00, ICMS10 ... ICMSSN500 ...). O XSD define quais
    grupos têm cada campo, e um campo ausente no grupo fica `None`. O grupo ICMS é obrigatório
    no `imposto` (XSD:2125 e seguintes), por isso a ausência é recusa.
    """
    icms = imposto.find("n:ICMS", _NS) if imposto is not None else None
    if icms is None:
        raise _Ilegivel("grupo ICMS ausente no imposto (obrigatório pelo XSD)")
    grupo = _grupo_unico(icms, "ICMS")
    if grupo is None:
        raise _Ilegivel("grupo ICMS sem nenhum tributo")
    dados = {
        "orig": _texto(grupo, "n:orig", "orig", "orig"),
        "cst": _texto(grupo, "n:CST", "CST", "CST"),
        "csosn": _texto(grupo, "n:CSOSN", "CSOSN", "CSOSN"),
        "mod_bc": _texto(grupo, "n:modBC", "modBC", "modBC"),
        "v_bc": _decimal(grupo, "n:vBC", "vBC", "TDec_1302"),
        "p_icms": _decimal(grupo, "n:pICMS", "pICMS", "TDec_0302a04"),
        "v_icms": _decimal(grupo, "n:vICMS", "vICMS", "TDec_1302"),
        "v_icms_deson": _decimal(grupo, "n:vICMSDeson", "vICMSDeson", "TDec_1302"),
        "mot_des_icms": _texto(grupo, "n:motDesICMS", "motDesICMS", "motDesICMS"),
        "mod_bc_st": _texto(grupo, "n:modBCST", "modBCST", "modBCST"),
        "v_bc_st": _decimal(grupo, "n:vBCST", "vBCST", "TDec_1302"),
        "p_icms_st": _decimal(grupo, "n:pICMSST", "pICMSST", "TDec_0302a04"),
        "v_icms_st": _decimal(grupo, "n:vICMSST", "vICMSST", "TDec_1302"),
        "v_bc_st_ret": _decimal(grupo, "n:vBCSTRet", "vBCSTRet", "TDec_1302"),
        "v_icms_st_ret": _decimal(grupo, "n:vICMSSTRet", "vICMSSTRet", "TDec_1302"),
        "p_cred_sn": _decimal(grupo, "n:pCredSN", "pCredSN", "TDec_0302a04"),
        "v_cred_icms_sn": _decimal(grupo, "n:vCredICMSSN", "vCredICMSSN", "TDec_1302"),
        "v_fcp": _decimal(grupo, "n:vFCP", "vFCP", "TDec_1302"),
        "v_fcp_st": _decimal(grupo, "n:vFCPST", "vFCPST", "TDec_1302"),
    }
    return dados


def _ler_ipi(imposto) -> dict:
    ipi = imposto.find("n:IPI", _NS) if imposto is not None else None
    if ipi is None:
        return {"cst_ipi": None, "v_ipi": None}
    grupo = _grupo_unico(ipi, "IPI")
    return {
        "cst_ipi": _texto(grupo, "n:CST", "CST do IPI", "CST"),
        "v_ipi": _decimal(grupo, "n:vIPI", "vIPI", "TDec_1302"),
    }


def _ler_tributo_de_grupo(imposto, nome: str, sufixo: str) -> dict:
    """PIS (`nome` "PIS", `sufixo` "pis") ou Cofins ("COFINS", "cofins").

    O grupo (PISAliq, COFINSNT ...) traz o CST e o valor. A tag do valor é `vPIS` ou `vCOFINS`
    (leiauteNFe_v4.00.xsd:4611 e 4861, primeiros grupos de cada tributo).
    """
    tributo = imposto.find(f"n:{nome}", _NS) if imposto is not None else None
    if tributo is None:
        return {f"cst_{sufixo}": None, f"v_{sufixo}": None}
    grupo = _grupo_unico(tributo, nome)
    cst = _texto(grupo, "n:CST", f"CST do {nome}", "CST")
    valor = _decimal(grupo, f"n:v{nome}", f"v{nome}", "TDec_1302")
    return {f"cst_{sufixo}": cst, f"v_{sufixo}": valor}


def _ler_ibscbs(imposto) -> tuple[bool, str]:
    """Só a presença e o XML bruto do grupo IBSCBS (HI-123). Nada é interpretado."""
    grupo = imposto.find("n:IBSCBS", _NS) if imposto is not None else None
    if grupo is None:
        return False, ""
    return True, ElementTree.tostring(grupo, encoding="unicode")


def _ler_det(det) -> dict:
    """Um `det` (leiauteNFe_v4.00.xsd:867) como dicionário dos campos de `ItemNFe`."""
    prod = det.find("n:prod", _NS)
    if prod is None:
        raise _Ilegivel("item sem grupo prod (obrigatório pelo XSD)")
    imposto = det.find("n:imposto", _NS)
    if imposto is None:
        raise _Ilegivel("item sem grupo imposto (obrigatório pelo XSD)")

    # nItem é atributo de `det` (leiauteNFe_v4.00.xsd:5320), obrigatório.
    n_item = det.get("nItem")
    if n_item is None or not _PADRAO["nItem"].fullmatch(n_item):
        raise _Ilegivel(f"nItem fora do padrão do XSD: {n_item!r} (leiauteNFe_v4.00.xsd:5320)")

    v_prod = _decimal(prod, "n:vProd", "vProd", "TDec_1302", obrigatorio=True)
    v_desc = _decimal(prod, "n:vDesc", "vDesc", "TDec_1302Opc")
    v_frete = _decimal(prod, "n:vFrete", "vFrete", "TDec_1302Opc")
    v_seg = _decimal(prod, "n:vSeg", "vSeg", "TDec_1302Opc")
    v_outro = _decimal(prod, "n:vOutro", "vOutro", "TDec_1302Opc")
    # indTot é filho de `prod` (leiauteNFe_v4.00.xsd:1126). 0: vProd não compõe o total da NF-e.
    ind_tot = _texto(prod, "n:indTot", "indTot", "indTot", obrigatorio=True)

    tem_ibscbs, ibscbs_xml = _ler_ibscbs(imposto)
    dados = {
        "n_item": int(n_item),
        "c_prod": _texto(prod, "n:cProd", "cProd", "TString", obrigatorio=True),
        "x_prod": _texto(prod, "n:xProd", "xProd", "TString", obrigatorio=True),
        "ncm": _texto(prod, "n:NCM", "NCM", "NCM", obrigatorio=True),
        "cest": _texto(prod, "n:CEST", "CEST", "CEST") or "",
        "cfop": _texto(prod, "n:CFOP", "CFOP", "CFOP", obrigatorio=True),
        "u_com": _texto(prod, "n:uCom", "uCom", "TString", obrigatorio=True),
        "q_com": _decimal(prod, "n:qCom", "qCom", "TDec_1104v", obrigatorio=True),
        "v_un_com": _decimal(prod, "n:vUnCom", "vUnCom", "TDec_1110v", obrigatorio=True),
        "v_prod": v_prod,
        "v_desc": v_desc,
        "v_frete": v_frete,
        "v_seg": v_seg,
        "v_outro": v_outro,
        "ind_tot": ind_tot,
        "c_benef": _texto(prod, "n:cBenef", "cBenef", "cBenef") or "",
        "v_ii": _decimal(imposto, "n:II/n:vII", "vII", "TDec_1302"),
        "v_issqn": _decimal(imposto, "n:ISSQN/n:vISSQN", "vISSQN", "TDec_1302"),
        "v_icms_ufdest": _decimal(
            imposto, "n:ICMSUFDest/n:vICMSUFDest", "vICMSUFDest", "TDec_1302"
        ),
        "tem_ibscbs": tem_ibscbs,
        "ibscbs_xml": ibscbs_xml,
    }
    dados.update(_ler_icms(imposto))
    dados.update(_ler_ipi(imposto))
    dados.update(_ler_tributo_de_grupo(imposto, "PIS", "pis"))
    dados.update(_ler_tributo_de_grupo(imposto, "COFINS", "cofins"))
    dados["receita_bruta_item"] = receita_bruta_do_item(dados)
    return dados


def receita_bruta_do_item(dados: dict) -> Decimal:
    """`vProd − vDesc + vFrete + vSeg + vOutro` (HI-119; consulta, item 3). Ausente soma zero."""
    total = dados["v_prod"]
    for parcela in ("v_frete", "v_seg", "v_outro"):
        total += dados[parcela] or Decimal("0")
    if dados["v_desc"] is not None:
        total -= dados["v_desc"]
    return total


def _ler_itens_do_xml(xml: bytes) -> tuple[list[dict], dict]:
    """Itens e totais de uma NF-e (`nfeProc`), ou `_Ilegivel` com o campo nomeado.

    Retorna (itens, totais). Os totais são os que a conferência e os avisos usam e que o
    `DocumentoNFe` não guarda: vII, vIPIDevol, vNFTot, vIBS, vCBS e vIS.
    """
    try:
        raiz = _raiz_segura(xml)
    except ArquivoRecusado as exc:
        raise _Ilegivel(f"XML guardado não lê: {exc}") from exc
    inf = raiz.find("n:NFe/n:infNFe", _NS)
    if inf is None:
        raise _Ilegivel("XML guardado sem infNFe")

    dets = inf.findall("n:det", _NS)
    if not dets:
        raise _Ilegivel("nota sem itens (det)")
    if len(dets) > 990:
        raise _Ilegivel(f"nota com {len(dets)} itens, acima do limite do XSD (990)")
    itens = []
    numeros: set[int] = set()
    for det in dets:
        dados = _ler_det(det)
        if dados["n_item"] in numeros:
            raise _Ilegivel(f"nItem {dados['n_item']} repetido na nota")
        numeros.add(dados["n_item"])
        itens.append(dados)

    total = inf.find("n:total", _NS)
    icms_tot = total.find("n:ICMSTot", _NS) if total is not None else None
    ibs = total.find("n:IBSCBSTot", _NS) if total is not None else None
    totais = {
        "v_ii": _decimal(icms_tot, "n:vII", "vII (total)", "TDec_1302"),
        "v_ipi_devol": _decimal(icms_tot, "n:vIPIDevol", "vIPIDevol (total)", "TDec_1302"),
        "v_nf_tot": _decimal(total, "n:vNFTot", "vNFTot (total)", "TDec_1302"),
        "v_ibs": _decimal(ibs, "n:gIBS/n:vIBS", "vIBS (total)", "TDec_1302"),
        "v_cbs": _decimal(ibs, "n:gCBS/n:vCBS", "vCBS (total)", "TDec_1302"),
        "v_is": _decimal(total, "n:ISTot/n:vIS", "vIS (total)", "TDec_1302"),
    }
    return itens, totais


def _gravar_leitura(documento: DocumentoNFe, xml: bytes) -> LeituraItensNFe:
    """Lê e grava o resultado (lido ou ilegível) numa transação. Chamado por `ler_itens`."""
    try:
        itens, totais = _ler_itens_do_xml(xml)
    except _Ilegivel as exc:
        return LeituraItensNFe.objects.create(
            documento=documento,
            estado=LeituraItensNFe.ESTADO_ILEGIVEL,
            motivo=exc.motivo[:500],
            **{
                campo: None
                for campo in ("v_ii", "v_ipi_devol", "v_nf_tot", "v_ibs", "v_cbs", "v_is")
            },
        )
    leitura = LeituraItensNFe.objects.create(
        documento=documento,
        estado=LeituraItensNFe.ESTADO_LIDA,
        quantidade_itens=len(itens),
        **totais,
    )
    ItemNFe.objects.bulk_create(ItemNFe(documento=documento, **dados) for dados in itens)
    return leitura


def ler_itens(documento: DocumentoNFe) -> LeituraItensNFe:
    """Itens da nota, lidos UMA vez e gravados. Idempotente (DL-081, item 2).

    Chamada com o documento já escolhido pela empresa (o isolamento é de quem chama). A leitura
    roda em transação: itens e resultado entram juntos ou nenhum entra. Se duas requisições
    lerem a mesma nota ao mesmo tempo, a segunda perde a corrida no `OneToOneField` e devolve a
    leitura que a primeira gravou, sem duplicar item.
    """
    existente = LeituraItensNFe.objects.filter(documento=documento).first()
    if existente is not None:
        return existente
    xml = bytes(documento.xml_original)
    try:
        with transaction.atomic():
            return _gravar_leitura(documento, xml)
    except IntegrityError:
        existente = LeituraItensNFe.objects.filter(documento=documento).first()
        if existente is None:
            raise
        return existente
