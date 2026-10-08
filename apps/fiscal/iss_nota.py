"""Campos de ISS da NFS-e nacional, lidos do XML guardado — DL-076, frente A (item 1).

Função pura de leitura: não grava nada, não calcula imposto e não decide nada. Quem
decide é `apps.fiscal.iss_municipal`. Aqui vale uma regra só: **campo ausente vira
`None` e fica NOMEADO em `ausentes`; nunca vira zero** (uma nota sem `vISSQN` não é
uma nota de ISS zero). Campo presente mas fora do formato do XSD vira `None` e entra
em `invalidos`. Todo valor monetário ou alíquota é `Decimal` lido de TEXTO; `float`
não entra aqui.

Caminhos conferidos no esquema oficial da NFS-e nacional, pacote
`nfse-esquemas_xsd-v1-01-20260209.zip` (sha256
e7935cbd9470527c6cc32984c1b2263e614183bf0139ce2733eaaed2de9a8072; o pacote com os XSD
das duas versões, `Schemas/1.00` e `Schemas/1.01`, foi baixado em 08/10/2026 e
conferido por extração limpa). Em cada constante, a linha do ELEMENTO em
`Schemas/1.01/tiposComplexos_v1.01.xsd` e em `Schemas/1.00/tiposComplexos_v1.00.xsd`.
Os tipos simples (TSDec15V2, TSDec1V2, TSCodMunIBGE, TSCodTribNac, TSTipoRetISSQN) estão
em `tiposSimples_v1.0x.xsd` com o MESMO padrão nas duas versões; o padrão de cada um
é citado pelo nome do tipo.

Achado do próprio XSD, registrado para o Fred: `vBC` e `vISSQN` ficam em
`infNFSe/valores` (TCValoresNFSe), NÃO em `infNFSe/DPS/infDPS/valores`. O grupo IBS/CBS
tem `vBC` próprio em `infNFSe/IBSCBS/valores` (ver `apps.fiscal.ibscbs`); por isso o
caminho do ISS é diferente do caminho da base do IBS/CBS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from apps.fiscal.leitor import NS_NFSE, ArquivoRecusado, _raiz_segura

_NS = {"n": NS_NFSE}

VERSOES_LIDAS = ("1.00", "1.01")

# Caminhos a partir da raiz NFSe, como tuplas de nomes de elemento.
# Cada linha citada é do elemento (não do tipo que o contém).
CAMINHO_C_LOC_INCID = ("infNFSe", "cLocIncid")  # 1.01: :35 | 1.00: :44 (minOccurs=0)
CAMINHO_C_TRIB_NAC = (
    "infNFSe",
    "DPS",
    "infDPS",
    "serv",
    "cServ",
    "cTribNac",
)  # 1.01: :1331 | 1.00: :883
CAMINHO_V_SERV = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "vServPrest",
    "vServ",
)  # 1.01: :1669 | 1.00: :1274
CAMINHO_V_DESC_INCOND = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "vDescCondIncond",
    "vDescIncond",
)  # 1.01: :1679 | 1.00: :1285 (minOccurs=0)
CAMINHO_V_DR = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "vDedRed",
    "vDR",
)  # 1.01: :1702 | 1.00: :1309
CAMINHO_V_CALC_DR = ("infNFSe", "valores", "vCalcDR")  # 1.01: :221 | 1.00: :216 (minOccurs=0)
CAMINHO_V_BC = ("infNFSe", "valores", "vBC")  # 1.01: :246 | 1.00: :237 (minOccurs=0)
CAMINHO_P_ALIQ_APLIC = ("infNFSe", "valores", "pAliqAplic")  # 1.01: :254 | 1.00: :244
CAMINHO_V_ISSQN = ("infNFSe", "valores", "vISSQN")  # 1.01: :261 | 1.00: :251 (minOccurs=0)
CAMINHO_TRIB_ISSQN = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribMun",
    "tribISSQN",
)  # 1.01: :1859 | 1.00: :1471
CAMINHO_TP_RET_ISSQN = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribMun",
    "tpRetISSQN",
)  # 1.01: :1909 | 1.00: :1528

# Padrões dos tipos simples do XSD, usados como `fullmatch`.
# TSDec15V2: "0|0\.[0-9]{2}|[1-9][0-9]{0,14}(\.[0-9]{2})?" (tiposSimples_v1.01.xsd, :1432).
_PADRAO_DEC15V2 = re.compile(r"0|0\.[0-9]{2}|[1-9][0-9]{0,14}(\.[0-9]{2})?")
# TSDec1V2: "0|[0-9]{1}(\.[0-9]{2})?" (tiposSimples_v1.01.xsd, :1441). Alíquota em
# pontos: uma casa inteira e duas decimais.
_PADRAO_DEC1V2 = re.compile(r"0|[0-9](\.[0-9]{2})?")
# TSCodMunIBGE: "[0-9]{7}" (tiposSimples_v1.01.xsd, :1340).
_PADRAO_COD_MUN = re.compile(r"[0-9]{7}")
# TSCodTribNac: "[0-9]{6}" (tiposSimples_v1.01.xsd, :1358). Os 6 dígitos são
# item(2) + subitem(2) + desdobro(2).
_PADRAO_C_TRIB_NAC = re.compile(r"[0-9]{6}")
# TSTipoRetISSQN: enumeração {1, 2, 3} (tiposSimples_v1.01.xsd, :1123-1140).
_PADRAO_TP_RET_ISSQN = re.compile(r"[123]")


@dataclass(frozen=True)
class CamposIss:
    """O que a leitura do XML encontrou para o ISS. Campo ausente fica `None`.

    `ausentes` e `invalidos` trazem o caminho legível (ex.: "NFSe/infNFSe/valores/vISSQN")
    de cada campo que faltou ou veio fora do formato. Quem consome decide o que fazer;
    esta função nunca presume valor.
    """

    versao: str
    erro_leitura: str | None = None
    c_loc_incid: str | None = None
    c_trib_nac: str | None = None
    # "II.SS", derivado dos 4 primeiros dígitos do cTribNac (LC 116, lista por subitem).
    subitem: str | None = None
    v_serv: Decimal | None = None
    v_desc_incond: Decimal | None = None
    # Dedução declarada na DPS (vDedRed/vDR) e dedução calculada na NFS-e (vCalcDR).
    v_dr: Decimal | None = None
    v_calc_dr: Decimal | None = None
    # Base de cálculo do ISSQN da NFS-e (vBC), alíquota aplicada (pAliqAplic, em pontos)
    # e valor do ISSQN (vISSQN).
    v_bc: Decimal | None = None
    p_aliq_aplic: Decimal | None = None
    v_iss_qn: Decimal | None = None
    trib_issqn: str | None = None
    tp_ret_issqn: str | None = None
    ausentes: tuple[str, ...] = ()
    invalidos: tuple[str, ...] = ()


def _legivel(caminho) -> str:
    return "/".join(("NFSe",) + tuple(caminho))


def _elemento(raiz, caminho):
    return raiz.find("/".join(f"n:{parte}" for parte in caminho), _NS)


def _texto_validado(raiz, caminho, padrao, ausentes, invalidos):
    """Texto do elemento aparado, se casa com o padrão; senão `None` e registra o caminho."""
    elemento = _elemento(raiz, caminho)
    if elemento is None:
        ausentes.append(_legivel(caminho))
        return None
    texto = (elemento.text or "").strip()
    if not padrao.fullmatch(texto):
        invalidos.append(_legivel(caminho))
        return None
    return texto


def _decimal(raiz, caminho, padrao, ausentes, invalidos) -> Decimal | None:
    texto = _texto_validado(raiz, caminho, padrao, ausentes, invalidos)
    # Decimal a partir de TEXTO, nunca float (AGENTS.md §10).
    return Decimal(texto) if texto is not None else None


def subitem_de_c_trib_nac(c_trib_nac: str) -> str:
    """ "II.SS" a partir dos 6 dígitos do cTribNac. Quem chama já validou os 6 dígitos."""
    return f"{c_trib_nac[0:2]}.{c_trib_nac[2:4]}"


def ler_campos_iss(xml_bytes: bytes, versao: str) -> CamposIss:
    """Lê os campos de ISS da NFS-e. Não levanta exceção: XML ilegível vira `erro_leitura`.

    A leitura usa `_raiz_segura` (defusedxml, sem DTD), o mesmo caminho seguro da
    recepção; não se abre parser novo aqui.
    """
    if versao not in VERSOES_LIDAS:
        return CamposIss(versao=versao, erro_leitura=f"versão sem leitura de ISS: {versao!r}")
    try:
        raiz = _raiz_segura(bytes(xml_bytes or b""))
    except ArquivoRecusado as exc:
        return CamposIss(versao=versao, erro_leitura=str(exc))
    if raiz.tag != f"{{{NS_NFSE}}}NFSe":
        return CamposIss(versao=versao, erro_leitura="elemento raiz diferente de NFSe")
    if _elemento(raiz, ("infNFSe",)) is None:
        return CamposIss(versao=versao, erro_leitura="NFS-e sem infNFSe")

    ausentes: list[str] = []
    invalidos: list[str] = []

    c_loc_incid = _texto_validado(raiz, CAMINHO_C_LOC_INCID, _PADRAO_COD_MUN, ausentes, invalidos)
    c_trib_nac = _texto_validado(raiz, CAMINHO_C_TRIB_NAC, _PADRAO_C_TRIB_NAC, ausentes, invalidos)
    tp_ret = _texto_validado(raiz, CAMINHO_TP_RET_ISSQN, _PADRAO_TP_RET_ISSQN, ausentes, invalidos)
    trib_elemento = _elemento(raiz, CAMINHO_TRIB_ISSQN)
    trib_issqn = (trib_elemento.text or "").strip() if trib_elemento is not None else None
    if trib_elemento is None:
        ausentes.append(_legivel(CAMINHO_TRIB_ISSQN))

    return CamposIss(
        versao=versao,
        c_loc_incid=c_loc_incid,
        c_trib_nac=c_trib_nac,
        subitem=subitem_de_c_trib_nac(c_trib_nac) if c_trib_nac is not None else None,
        v_serv=_decimal(raiz, CAMINHO_V_SERV, _PADRAO_DEC15V2, ausentes, invalidos),
        # Desconto incondicional e deduções são OPCIONAIS no XSD (minOccurs=0). Ausência
        # fica nomeada e não vira zero; quem usa decide o que a ausência significa.
        v_desc_incond=_decimal(raiz, CAMINHO_V_DESC_INCOND, _PADRAO_DEC15V2, ausentes, invalidos),
        v_dr=_decimal(raiz, CAMINHO_V_DR, _PADRAO_DEC15V2, ausentes, invalidos),
        v_calc_dr=_decimal(raiz, CAMINHO_V_CALC_DR, _PADRAO_DEC15V2, ausentes, invalidos),
        v_bc=_decimal(raiz, CAMINHO_V_BC, _PADRAO_DEC15V2, ausentes, invalidos),
        p_aliq_aplic=_decimal(raiz, CAMINHO_P_ALIQ_APLIC, _PADRAO_DEC1V2, ausentes, invalidos),
        v_iss_qn=_decimal(raiz, CAMINHO_V_ISSQN, _PADRAO_DEC15V2, ausentes, invalidos),
        trib_issqn=trib_issqn,
        tp_ret_issqn=tp_ret,
        ausentes=tuple(ausentes),
        invalidos=tuple(invalidos),
    )


def campos_iss_do_documento(documento) -> CamposIss:
    """Atalho: lê o `DocumentoFiscal` pelo XML guardado (`xml_original`) e pela versão."""
    return ler_campos_iss(bytes(documento.xml_original or b""), documento.versao)


def divergencia_de_base(campos: CamposIss) -> str | None:
    """Aviso quando `vBC` não bate com `vServ − vDescIncond − deduções` (DL-076, item 5).

    A base de conferência é `vBC` (HI-82). Esta função só informa o que o XML diz de
    diferente. A dedução usada é `vDedRed/vDR` (da DPS) quando existe, senão
    `vCalcDR` (da NFS-e), como na fórmula do próprio XSD (`vBC = vServ - descIncond -
    (vDR ou vCalcDR + vCalcReeRepRes) - ...`, tiposComplexos_v1.01.xsd:246).

    Se falta um termo, o aviso só sai quando `vBC` difere de `vServ`, e nomeia o que
    faltou. Não se presume zero no termo ausente.
    """
    if campos.v_serv is None or campos.v_bc is None:
        return None
    deducoes = campos.v_dr if campos.v_dr is not None else campos.v_calc_dr
    if campos.v_desc_incond is not None and deducoes is not None:
        recomposta = campos.v_serv - campos.v_desc_incond - deducoes
        if recomposta != campos.v_bc:
            return (
                f"vBC ({campos.v_bc}) difere de vServ − vDescIncond − deduções "
                f"({recomposta}) no XML"
            )
        return None
    if campos.v_bc != campos.v_serv:
        faltam = []
        if campos.v_desc_incond is None:
            faltam.append("vDescIncond")
        if deducoes is None:
            faltam.append("deduções (vDedRed/vDR ou vCalcDR)")
        return (
            f"vBC ({campos.v_bc}) difere de vServ ({campos.v_serv}) e a diferença não "
            f"pode ser explicada: campo(s) ausente(s) {', '.join(faltam)}"
        )
    return None
