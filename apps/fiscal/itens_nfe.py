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
- `receita_bruta_item` = `vProd − vDesc + vFrete + vSeg + vOutro` (HI-119). É o VALOR BRUTO do
  item, e NÃO a receita: não passa por `indTot` nem por `vICMSDeson`, e o `vProd` de um item
  `indTot` 0 entra nele mesmo sem ter sido cobrado. A receita do item é `receita_do_item` (DL-083).
  O campo gravado não muda, e a versão do leitor não sobe (decisão do arquiteto; DL-083). Os
  opcionais ausentes entram como zero NESSA SOMA, porque o XSD os torna opcionais: a ausência é
  "não há essa parcela". Não é uma leitura de campo ausente.

Limites declarados:

- O grupo ICMS é lido pelos nomes dos filhos. Os valores que o XSD enumera em cada grupo
  (por exemplo, a lista de `motDesICMS`) não são re-enumerados aqui: `motDesICMS` aceita dois
  dígitos, e a conferência do domínio fica para a apuração do ICMS.
- Textos (`xProd`, `cProd`, `cBenef`) seguem o padrão TString do XSD (Latin-1, sem espaço nas
  pontas). Real nota autorizada já passou pelo mesmo padrão na SEFAZ.
- Escolha do `imposto` (leiauteNFe_v4.00.xsd:2117, `xs:choice minOccurs="0"`): ou o grupo
  ICMS (com IPI e II opcionais), ou o ISSQN (com IPI opcional). O choice inteiro é opcional, então
  ICMS ausente é válido quando o item tem ISSQN, ou quando não tem ICMS, IPI, II nem ISSQN (o
  `imposto` pode trazer só PIS, Cofins ou ICMSUFDest). ICMS e ISSQN juntos são recusados. IPI ou II
  sem ICMS nem ISSQN também é recusado, porque o XSD não aceita essa combinação.
- O IPI (TIpi, leiauteNFe_v4.00.xsd:7579) tem `cEnq` antes do grupo, e o grupo é IPITrib (linha
  7623) ou IPINT (linha 7678). O leitor acha o grupo pelo nome e ignora `CNPJProd`, `cSelo`,
  `qSelo` e `cEnq`.
- Versão do leitor (`VERSAO_LEITOR_ITENS`): cada leitura grava a versão com que foi feita. Leitura
  de versão anterior é refeita na próxima tentativa e substitui a antiga, desde que a nota não
  tenha escrituração efetivada ou estornada. Assim, notas que a leitura antiga recusou por erro
  do próprio leitor são relidas (DL-081, correção da rodada 1, A1 e A12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree

from django.db import DataError, IntegrityError, transaction

from apps.fiscal.formatacao_ptbr import valor_ptbr
from apps.fiscal.leitor import ArquivoRecusado, _raiz_segura
from apps.fiscal.leitor_nfe import NS_NFE
from apps.fiscal.models import (
    DocumentoNFe,
    EscrituracaoNFe,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    papel_da_natureza_nfe,
)

_NS = {"n": NS_NFE}

# Versão deste leitor, gravada em cada `LeituraItensNFe`. Suba o número quando a regra de leitura
# mudar: a leitura gravada com versão anterior é refeita (ver `ler_itens`). Versão 1 é a da rodada
# 1 da DL-081, que recusava IPI com `cEnq`, item só com ISSQN e `imposto` sem ICMS.
VERSAO_LEITOR_ITENS = 2

# Limite de `numeric(15,2)`, o tipo de `receita_bruta_item` e dos totais: 13 dígitos inteiros, ou
# seja, valor absoluto menor que 10^13. Acima disso, o banco recusa com DataError (500 na API).
# A nota vira ilegível antes, com o motivo, e nada é gravado (DL-081, A5).
LIMITE_MONETARIO = Decimal("10000000000000")

# Os campos do grupo ICMS, na ordem do `_ler_icms`. Quando o grupo não existe no item (choice do
# `imposto` com ISSQN, ou sem nenhum grupo da choice), todos ficam `None`.
_CAMPOS_ICMS = (
    "orig",
    "cst",
    "csosn",
    "mod_bc",
    "v_bc",
    "p_icms",
    "v_icms",
    "v_icms_deson",
    "mot_des_icms",
    "mod_bc_st",
    "v_bc_st",
    "p_icms_st",
    "v_icms_st",
    "v_bc_st_ret",
    "v_icms_st_ret",
    "p_cred_sn",
    "v_cred_icms_sn",
    "v_fcp",
    "v_fcp_st",
    "ind_deduz_deson",
)

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
    # leiauteNFe_v4.00.xsd:2586 (indDeduzDeson: 0 não deduz do total, 1 deduz)
    "indDeduz": re.compile(r"0|1"),
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


def _conferir_escolha_do_imposto(imposto) -> None:
    """Recusa a combinação que o `xs:choice` do `imposto` não aceita (leiauteNFe_v4.00.xsd:2117).

    A escolha é ICMS (com IPI e II) OU ISSQN (com IPI). O choice inteiro é opcional, então não ter
    ICMS nem ISSQN é válido, desde que não haja IPI nem II soltos.
    """
    tem_icms = imposto.find("n:ICMS", _NS) is not None
    tem_issqn = imposto.find("n:ISSQN", _NS) is not None
    tem_ipi_ou_ii = imposto.find("n:IPI", _NS) is not None or imposto.find("n:II", _NS) is not None
    if tem_icms and tem_issqn:
        raise _Ilegivel("imposto com ICMS e ISSQN no mesmo item (XSD: um ou outro, linha 2117)")
    if not tem_icms and not tem_issqn and tem_ipi_ou_ii:
        raise _Ilegivel("IPI ou II sem grupo ICMS nem ISSQN no imposto (XSD, linha 2117)")


def _ler_icms(imposto) -> dict:
    """ICMS, ICMS-ST, crédito do Simples e FCP. Os nomes dos campos são os do grupo.

    Cada campo fica no filho do grupo (ICMS00, ICMS10 ... ICMSSN500 ...). O XSD define quais
    grupos têm cada campo, e um campo ausente no grupo fica `None`. O grupo ICMS é obrigatório
    só na alternativa ICMS do choice (leiauteNFe_v4.00.xsd:2117): sem ele, por ISSQN ou por
    ausência do choice, todos os campos ficam `None`, e isso NÃO é recusa.
    """
    icms = imposto.find("n:ICMS", _NS)
    if icms is None:
        return {campo: None for campo in _CAMPOS_ICMS}
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
        "ind_deduz_deson": _texto(grupo, "n:indDeduzDeson", "indDeduzDeson", "indDeduz"),
    }
    return dados


def _ler_ipi(imposto) -> dict:
    """IPI (TIpi, leiauteNFe_v4.00.xsd:7579). O grupo é IPITrib (linha 7623) ou IPINT (linha 7678).

    `cEnq` vem antes do grupo, e `CNPJProd`, `cSelo` e `qSelo` são opcionais. Nenhum deles é o
    grupo: o grupo é achado pelo NOME, e exatamente um deve existir.
    """
    ipi = imposto.find("n:IPI", _NS)
    if ipi is None:
        return {"cst_ipi": None, "v_ipi": None}
    grupos = ipi.findall("n:IPITrib", _NS) + ipi.findall("n:IPINT", _NS)
    if len(grupos) != 1:
        raise _Ilegivel(f"IPI sem grupo IPITrib ou IPINT único (encontrados: {len(grupos)})")
    grupo = grupos[0]
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
    _conferir_escolha_do_imposto(imposto)

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
    if abs(dados["receita_bruta_item"]) >= LIMITE_MONETARIO:
        raise _Ilegivel(f"receita do item acima do limite (nItem {n_item}; numeric(15,2))")
    return dados


def receita_bruta_do_item(dados: dict) -> Decimal:
    """Valor BRUTO do item: `vProd − vDesc + vFrete + vSeg + vOutro` (HI-119; consulta, item 3).

    Ausente soma zero. Este é o número gravado em `ItemNFe.receita_bruta_item`, e NÃO é a receita:
    para a receita, use `receita_do_item`, que aplica `indTot` e `vICMSDeson` (DL-083).
    """
    total = dados["v_prod"]
    for parcela in ("v_frete", "v_seg", "v_outro"):
        total += dados[parcela] or Decimal("0")
    if dados["v_desc"] is not None:
        total -= dados["v_desc"]
    return total


def receita_do_item(item) -> Decimal:
    """Receita do item de NF-e: a ÚNICA regra de receita por item (DL-083; consulta de 09/10/2026,
    PE-85.5, e HI-119 complementada).

    Aceita um `ItemNFe` ou qualquer objeto com os mesmos campos. Devolve `Decimal`, nunca float.

        indTot 1:  vProd − vDesc − vICMSDeson (só se indDeduzDeson = 1) + vFrete + vSeg + vOutro
        indTot 0: −vDesc − vICMSDeson (idem)                           + vFrete + vSeg + vOutro

    `indTot` 0 é o item que não compõe o total da nota (leiauteNFe_v4.00.xsd:1126): o `vProd` não
    foi cobrado, então não entra. Desconto, frete, seguro e outras despesas do item, porém, entram
    no total da nota (MOC 7.0, W07 a W16), e por isso compõem a receita. `vICMSDeson` deduz só com
    `indDeduzDeson` 1 (desconto incondicional): com 0 ou ausente, o adquirente pagou o valor cheio.
    Ausente soma zero. Quem chama soma o resultado; a soma é a receita da nota.
    """
    base = item.v_prod if item.ind_tot == "1" else Decimal("0.00")
    total = base
    for parcela in (item.v_frete, item.v_seg, item.v_outro):
        if parcela is not None:
            total += parcela
    if item.v_desc is not None:
        total -= item.v_desc
    if item.ind_deduz_deson == "1" and item.v_icms_deson is not None:
        total -= item.v_icms_deson
    return total


# ---------------------------------------------------------------------------
# Atribuição por nota (DL-083, HI-138; consulta de 09/10/2026, item 1). Única etapa que distribui o
# valor de item que não é receita. Todo soma de receita de NF-e passa por ela.
# ---------------------------------------------------------------------------

# Textos fixos: a API e a tela os repetem, e os testes comparam pela constante.
MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR = (
    "item fora do total com valor cobrado: escolha uma natureza de receita"
)
MENSAGEM_RESIDUO_MAIOR_QUE_A_RECEITA = (
    "desconto ou despesa de item fora do total maior que a receita da nota: a receita ficaria "
    "negativa"
)
MENSAGEM_RESIDUO_SEM_BASE_DE_RATEIO = (
    "valor de item fora do total sem base para ratear: os itens de receita da nota somam zero"
)

_CENTAVO = Decimal("0.01")


class ResiduoNaoAtribuivel(Exception):
    """O valor de item que não é receita não tem onde compor a receita da nota. A mensagem nomeia a
    regra; quem chama a traduz (efetivação recusa, tela mostra)."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class ParcelaDoResiduo:
    """Parcela do resíduo que caiu num item de receita (natureza e nItem do receptor)."""

    n_item: int
    natureza: str
    valor: Decimal


@dataclass(frozen=True)
class ResiduoDoItem:
    """Valor de um item que não é receita (`receita_do_item` dele) e para onde o resíduo da nota
    foi.

    `rateio` são as parcelas dos itens de receita da nota. Vazio quando o resíduo da nota é zero.
    """

    n_item: int
    natureza: str
    valor: Decimal
    rateio: tuple[ParcelaDoResiduo, ...]


@dataclass(frozen=True)
class AtribuicaoDaNota:
    """Receita de cada item da nota depois da atribuição.

    `valores`: `receita_do_item` do item de receita já com a sua parcela do resíduo; `Decimal` zero
    no item que não é receita; o `receita_do_item` cru no item de dedução. Chave: `ItemNFe.pk`.
    Itens sem natureza ainda não entram (a tela mostra "falta a natureza").
    `residuo_total` é a soma dos itens que não são receita. `itens_fora_do_total` diz cada um.
    """

    valores: dict
    residuo_total: Decimal
    itens_fora_do_total: tuple[ResiduoDoItem, ...]


def valor_cobrado_do_item(item) -> Decimal:
    """O que um item que NÃO é receita cobrou da nota, e que a atribuição leva à venda (HI-138).

    - `indTot` 0: `receita_do_item` inteiro (−vDesc − vICMSDeson, com indDeduzDeson 1, + frete,
      seguro
      e outras despesas). O vProd não foi cobrado, então não entra.
    - `indTot` 1: só frete, seguro e outras despesas. O vProd menos o desconto (e o ICMS
      desonerado) é
      a MERCADORIA do item: pela natureza (remessa, bonificação, transferência), ela não é receita.
      Atribuí-la à venda seria receita a maior pela mercadoria remetida. A consulta de 09/10/2026 e
      o
      HI-138 falam só em frete, seguro, outras despesas e desconto, e o critério 7 exige que a
      remessa de valor (indTot 1, sem despesa) continue somando zero (DL-081, HI-124).
    """
    if item.ind_tot != "1":
        return receita_do_item(item)
    total = Decimal("0.00")
    for parcela in (item.v_frete, item.v_seg, item.v_outro):
        if parcela is not None:
            total += parcela
    return total


def atribuir_receita_da_nota(pares) -> AtribuicaoDaNota:
    """Atribui o valor dos itens que não são receita aos itens de receita da MESMA nota (HI-138).

    `pares`: (ItemNFe, natureza) de UMA nota. A regra:

    - resíduo = Σ `valor_cobrado_do_item` dos itens de papel "nao_receita" (positivo ou negativo).
      A mercadoria de item indTot 1 fica fora (ver `valor_cobrado_do_item`). A natureza de dedução
      (devolução) também fica FORA: devolução com frete não entra no resíduo, e continua deduzindo o
      que deduz.
    - resíduo zero: nada a ratear, e cada item de receita fica com o seu `receita_do_item`.
    - resíduo diferente de zero, e nenhum item de receita: recusa (MENSAGEM_ITEM_FORA_DO_TOTAL...).
    - resíduo negativo maior, em valor absoluto, que a receita dos itens de receita: recusa.
    - resíduo positivo com receita dos itens de receita somando zero: não há base para ratear.
      Recusa.
    - caso contrário, rateio proporcional à `receita_do_item` de cada item de receita (só o positivo
      pesa), arredondado a centavo com ROUND_HALF_UP. A diferença de arredondamento vai para o item
      de receita de MAIOR valor; empate, o de menor nItem. A soma da nota não muda.

    A parcela herda a natureza e a atividade do item que a recebe, porque é ele que é classificado.
    """
    valores: dict = {}
    receita_itens = []
    nao_receita_itens = []
    residuo_total = Decimal("0.00")
    for item, natureza in pares:
        if not natureza:
            continue
        papel = papel_da_natureza_nfe(natureza)
        if papel == "receita":
            receita_itens.append((item, natureza, receita_do_item(item)))
        elif papel == "nao_receita":
            cobrado = valor_cobrado_do_item(item)
            nao_receita_itens.append((item, natureza, cobrado))
            residuo_total += cobrado
        else:
            # Dedução: fica com o valor cru, e não entra no resíduo.
            valores[item.pk] = receita_do_item(item)

    for item, _natureza, _valor in nao_receita_itens:
        valores[item.pk] = Decimal("0.00")

    if residuo_total == 0:
        for item, _natureza, valor in receita_itens:
            valores[item.pk] = valor
        return AtribuicaoDaNota(valores, Decimal("0.00"), ())

    if not receita_itens:
        raise ResiduoNaoAtribuivel(MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR)
    pesos = [max(valor, Decimal("0.00")) for _item, _nat, valor in receita_itens]
    base = sum(pesos, Decimal("0.00"))
    if residuo_total < 0 and -residuo_total > base:
        raise ResiduoNaoAtribuivel(MENSAGEM_RESIDUO_MAIOR_QUE_A_RECEITA)
    if base == 0:
        raise ResiduoNaoAtribuivel(MENSAGEM_RESIDUO_SEM_BASE_DE_RATEIO)

    parcelas = [
        (residuo_total * peso / base).quantize(_CENTAVO, rounding=ROUND_HALF_UP) for peso in pesos
    ]
    # A diferença de arredondamento vai para o item de maior valor. Empate: menor nItem. Assim a
    # soma das parcelas é exatamente o resíduo, e o W16 continua ao centavo.
    diferenca = residuo_total - sum(parcelas, Decimal("0.00"))
    recebedor = min(
        range(len(receita_itens)),
        key=lambda i: (-pesos[i], receita_itens[i][0].n_item),
    )
    parcelas[recebedor] += diferenca

    for (item, _natureza, valor), parcela in zip(receita_itens, parcelas, strict=True):
        valores[item.pk] = valor + parcela

    rateio = tuple(
        ParcelaDoResiduo(item.n_item, natureza, parcela)
        for (item, natureza, _valor), parcela in zip(receita_itens, parcelas, strict=True)
    )
    fora = tuple(
        ResiduoDoItem(item.n_item, natureza, valor, rateio)
        for item, natureza, valor in nao_receita_itens
    )
    return AtribuicaoDaNota(valores, residuo_total, fora)


def avisos_da_atribuicao(atribuicao: AtribuicaoDaNota) -> dict[int, tuple[str, ...]]:
    """Aviso por item que não é receita cujo valor foi atribuído à receita da venda desta nota.

    Só quando o resíduo da nota é diferente de zero e o item tem valor diferente de zero: o aviso
    diz
    o que foi para onde. Com mais de uma natureza de receita, mostra o rateio por natureza.
    Chave: `n_item` do item que não é receita.
    """
    if atribuicao.residuo_total == 0:
        return {}
    avisos: dict[int, tuple[str, ...]] = {}
    for fora in atribuicao.itens_fora_do_total:
        if fora.valor == 0:
            continue
        rotulo = NaturezaOperacaoNFe(fora.natureza).label
        texto = (
            f"item {fora.n_item} ({rotulo}): R$ {valor_ptbr(fora.valor)} de "
            "frete/seguro/outros/desconto atribuído à receita da venda desta nota"
        )
        naturezas = {parcela.natureza for parcela in fora.rateio}
        if len(naturezas) > 1:
            por_natureza: dict[str, Decimal] = {}
            for parcela in fora.rateio:
                por_natureza[parcela.natureza] = (
                    por_natureza.get(parcela.natureza, Decimal("0.00")) + parcela.valor
                )
            partes = "; ".join(
                f"{rotulo} R$ {valor_ptbr(v)}"
                for rotulo, v in sorted(
                    (NaturezaOperacaoNFe(n).label, v) for n, v in por_natureza.items()
                )
            )
            texto += f" (rateio: {partes})"
        avisos[fora.n_item] = (texto,)
    return avisos


def _ler_itens_do_xml(xml: bytes) -> tuple[list[dict], dict]:
    """Itens e totais de uma NF-e (`nfeProc`), ou `_Ilegivel` com o campo nomeado.

    Retorna (itens, totais). Os totais são os que a conferência e os avisos usam e que o
    `DocumentoNFe` não guarda: vII, vIPIDevol, vNFTot, vIBS, vCBS, vIS e vFCPST (total).
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

    # A soma das receitas dos itens vai para `soma_itens` e para a receita da escrituração, que
    # também são numeric(15,2). Cada item cabe, mas a soma pode não caber.
    if sum(abs(item["receita_bruta_item"]) for item in itens) >= LIMITE_MONETARIO:
        raise _Ilegivel("soma da receita dos itens acima do limite (numeric(15,2))")

    total = inf.find("n:total", _NS)
    icms_tot = total.find("n:ICMSTot", _NS) if total is not None else None
    ibs = total.find("n:IBSCBSTot", _NS) if total is not None else None
    totais = {
        "v_fcp_st_total": _decimal(icms_tot, "n:vFCPST", "vFCPST (total)", "TDec_1302"),
        "v_ii": _decimal(icms_tot, "n:vII", "vII (total)", "TDec_1302"),
        "v_ipi_devol": _decimal(icms_tot, "n:vIPIDevol", "vIPIDevol (total)", "TDec_1302"),
        "v_nf_tot": _decimal(total, "n:vNFTot", "vNFTot (total)", "TDec_1302"),
        "v_ibs": _decimal(ibs, "n:gIBS/n:vIBS", "vIBS (total)", "TDec_1302"),
        "v_cbs": _decimal(ibs, "n:gCBS/n:vCBS", "vCBS (total)", "TDec_1302"),
        "v_is": _decimal(total, "n:ISTot/n:vIS", "vIS (total)", "TDec_1302"),
    }
    return itens, totais


MOTIVO_LIMITE_DO_CAMPO = (
    "valor acima do limite de um campo monetário (numeric(15,2)); nenhum item foi gravado"
)


def _criar_leitura_ilegivel(documento: DocumentoNFe, motivo: str) -> LeituraItensNFe:
    return LeituraItensNFe.objects.create(
        documento=documento,
        estado=LeituraItensNFe.ESTADO_ILEGIVEL,
        motivo=motivo[:500],
        versao_leitor=VERSAO_LEITOR_ITENS,
        **{
            campo: None
            for campo in (
                "v_ii",
                "v_ipi_devol",
                "v_nf_tot",
                "v_ibs",
                "v_cbs",
                "v_is",
                "v_fcp_st_total",
            )
        },
    )


def _recriar_naturezas_dos_rascunhos(documento: DocumentoNFe) -> None:
    """Uma linha de natureza VAZIA por item, para cada rascunho da nota.

    Chamada quando a releitura troca os itens: as naturezas dos itens antigos saem em cascata, e
    um rascunho sem linha de natureza nunca se efetiva (o gatilho da 0011 exige todos os itens com
    natureza). A natureza antiga NÃO é transportada para o item novo, de propósito: o contador
    confirma de novo, porque a leitura mudou.
    """
    rascunhos = EscrituracaoNFe.objects.filter(vinculo__documento=documento, estado="rascunho")
    itens = list(ItemNFe.objects.filter(documento=documento).order_by("n_item"))
    for escrituracao in rascunhos:
        NaturezaItemNFe.objects.bulk_create(
            NaturezaItemNFe(escrituracao=escrituracao, item=item) for item in itens
        )


def _gravar_leitura(
    documento: DocumentoNFe, xml: bytes, anterior: LeituraItensNFe | None
) -> LeituraItensNFe:
    """Lê o XML e grava o resultado (lido ou ilegível). Chamado por `ler_itens`, dentro de
    transação.

    Se havia uma leitura de versão anterior, ela e os itens saem antes, e a nova entra no lugar.
    """
    if anterior is not None:
        ItemNFe.objects.filter(documento=documento).delete()
        anterior.delete()
    try:
        itens, totais = _ler_itens_do_xml(xml)
    except _Ilegivel as exc:
        return _criar_leitura_ilegivel(documento, exc.motivo)
    # O savepoint cobre leitura e itens: se o banco recusar um valor (DataError), nada parcial fica
    # gravado, e a nota vira ilegível com motivo, em vez de 500 (DL-081, A5).
    try:
        with transaction.atomic():
            leitura = LeituraItensNFe.objects.create(
                documento=documento,
                estado=LeituraItensNFe.ESTADO_LIDA,
                quantidade_itens=len(itens),
                versao_leitor=VERSAO_LEITOR_ITENS,
                **totais,
            )
            ItemNFe.objects.bulk_create(ItemNFe(documento=documento, **dados) for dados in itens)
    except DataError:
        return _criar_leitura_ilegivel(documento, MOTIVO_LIMITE_DO_CAMPO)
    _recriar_naturezas_dos_rascunhos(documento)
    return leitura


def _escrituracao_efetivada_ou_estornada(documento: DocumentoNFe) -> bool:
    """Se a nota tem escrituração efetivada ou estornada, os itens e a leitura são imutáveis
    (gatilho
    da 0011). Nesse caso a versão antiga fica, e a releitura não tenta trocá-la."""
    return EscrituracaoNFe.objects.filter(
        vinculo__documento=documento, estado__in=["efetivada", "estornada"]
    ).exists()


def ler_itens(documento: DocumentoNFe) -> LeituraItensNFe:
    """Itens da nota, lidos e gravados. Idempotente (DL-081, item 2).

    Uma leitura com a versão atual (`VERSAO_LEITOR_ITENS`) é devolvida como está. Uma leitura de
    versão anterior é refeita e substitui a antiga, mas só enquanto a nota não tem escrituração
    efetivada ou estornada (correção da rodada 1, A1 e A12).

    Chamada com o documento já escolhido pela empresa (o isolamento é de quem chama). A leitura
    roda em transação, com o `DocumentoNFe` travado: duas requisições em corrida leem uma de cada
    vez, e a segunda vê a versão que a primeira gravou, sem duplicar item.
    """
    existente = LeituraItensNFe.objects.filter(documento=documento).first()
    if existente is not None and existente.versao_leitor == VERSAO_LEITOR_ITENS:
        return existente
    xml = bytes(documento.xml_original)
    try:
        with transaction.atomic():
            # Trava a linha da nota: a releitura apaga e recria itens, e não pode correr em
            # paralelo.
            DocumentoNFe.objects.select_for_update().only("pk").get(pk=documento.pk)
            atual = LeituraItensNFe.objects.filter(documento=documento).first()
            if atual is not None and atual.versao_leitor == VERSAO_LEITOR_ITENS:
                return atual
            if atual is not None and _escrituracao_efetivada_ou_estornada(documento):
                return atual
            return _gravar_leitura(documento, xml, anterior=atual)
    except IntegrityError:
        existente = LeituraItensNFe.objects.filter(documento=documento).first()
        if existente is None:
            raise
        return existente
