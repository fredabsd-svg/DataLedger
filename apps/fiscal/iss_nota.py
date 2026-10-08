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
# Termos da fórmula do vBC que o XSD 1.01 traz (tiposComplexos_v1.01.xsd:250, em TCValoresNFSe):
#   vBC = vServ - descIncond - (vDR ou vCalcDR + vCalcReeRepRes) - (vRedBCBM ou VCalcBM)
# (o XSD escreve "VCalcBM" com V maiúsculo; o elemento é vCalcBM, linha :239). Os três são
# opcionais (minOccurs=0). A versão 1.00 não traz o texto da fórmula no vBC e não tem o grupo
# IBSCBS, por isso `vCalcReeRepRes` não existe nela.
CAMINHO_V_CALC_BM = ("infNFSe", "valores", "vCalcBM")  # 1.01: :239 | 1.00: :230
CAMINHO_V_RED_BC_BM = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribMun",
    "BM",
    "vRedBCBM",
)  # 1.01: :1948 (escolha com pRedBCBM) | 1.00: :1562
CAMINHO_V_CALC_REE_REP_RES = (
    "infNFSe",
    "IBSCBS",
    "valores",
    "vCalcReeRepRes",
)  # 1.01: :338 (grupo IBSCBS da NFS-e) | 1.00: inexistente

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
    # Termos da fórmula do vBC (A10): benefício municipal (vCalcBM, ou vRedBCBM do BM da DPS)
    # e reembolso (vCalcReeRepRes). Opcionais; ausência é tratada em `divergencia_de_base`.
    v_calc_bm: Decimal | None = None
    v_red_bc_bm: Decimal | None = None
    v_calc_ree_rep_res: Decimal | None = None
    ausentes: tuple[str, ...] = ()
    invalidos: tuple[str, ...] = ()


def _legivel(caminho) -> str:
    return "/".join(("NFSe",) + tuple(caminho))


# Campos que o XSD torna opcionais e que o produto não exige (minOccurs=0 e fora da apuração e
# dos relatórios). A ausência é normal: não entra no alerta do relatório (A11 da auditoria
# DL-076). vBC, pAliqAplic e vISSQN também são minOccurs=0 no XSD, mas o produto os exige
# (DL-076, item 1), por isso NÃO estão aqui.
CAMINHOS_OPCIONAIS = frozenset(
    _legivel(caminho)
    for caminho in (
        CAMINHO_V_DESC_INCOND,
        CAMINHO_V_DR,
        CAMINHO_V_CALC_DR,
        CAMINHO_V_CALC_BM,
        CAMINHO_V_RED_BC_BM,
        CAMINHO_V_CALC_REE_REP_RES,
    )
)


def ausentes_que_alertam(campos: CamposIss) -> tuple[str, ...]:
    """Campos AUSENTES que o produto precisa (sem os opcionais do XSD). Campo presente e
    ilegível não passa por aqui: está em `invalidos` e sempre alerta."""
    return tuple(caminho for caminho in campos.ausentes if caminho not in CAMINHOS_OPCIONAIS)


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
        v_calc_bm=_decimal(raiz, CAMINHO_V_CALC_BM, _PADRAO_DEC15V2, ausentes, invalidos),
        v_red_bc_bm=_decimal(raiz, CAMINHO_V_RED_BC_BM, _PADRAO_DEC15V2, ausentes, invalidos),
        v_calc_ree_rep_res=_decimal(
            raiz, CAMINHO_V_CALC_REE_REP_RES, _PADRAO_DEC15V2, ausentes, invalidos
        ),
        ausentes=tuple(ausentes),
        invalidos=tuple(invalidos),
    )


def campos_iss_do_documento(documento) -> CamposIss:
    """Atalho: lê o `DocumentoFiscal` pelo XML guardado (`xml_original`) e pela versão."""
    return ler_campos_iss(bytes(documento.xml_original or b""), documento.versao)


def divergencia_de_base(campos: CamposIss) -> str | None:
    """Aviso quando `vBC` não bate com a fórmula do XSD (DL-076, item 5; auditoria A10).

    Fórmula, conforme `tiposComplexos_v1.01.xsd:250` (TCValoresNFSe, linha do elemento vBC
    em :246):

        vBC = vServ - vDescIncond - (vDR ou vCalcDR + vCalcReeRepRes) - (vRedBCBM ou vCalcBM)

    Caminhos dos termos (ver as constantes CAMINHO_* acima): `vServ` e `vDescIncond` em
    `infDPS/valores`; `vDR` em `infDPS/valores/vDedRed`; `vCalcDR` e `vCalcBM` em
    `infNFSe/valores`; `vCalcReeRepRes` em `infNFSe/IBSCBS/valores`; `vRedBCBM` no BM de
    `infDPS/valores/trib/tribMun`. A versão 1.00 não traz o texto da fórmula; a conta vale
    para as duas, porque os termos novos não existem na 1.00.

    Regra de ausência (decisão do arquiteto, DL-076 auditoria A10, dúvidas 3 e 4): TODO termo
    opcional da fórmula (minOccurs=0 no XSD) que estiver ausente conta como ZERO nesta conta:
    vDescIncond, vDR, vCalcDR, vCalcReeRepRes, vCalcBM e vRedBCBM. Isto vale só para o AVISO
    de base. O total continua sendo a soma do vISSQN, e a conferência não muda. Limite
    conhecido: benefício dado só em percentual (`pRedBCBM`) não entra na fórmula; sem `vCalcBM`
    o aviso pode sair, e a mensagem mostra os números para o contador conferir.

    Campos obrigatórios (vServ, vBC) ausentes não entram aqui: a função não avisa nada.
    """
    if campos.v_serv is None or campos.v_bc is None:
        return None
    desconto = campos.v_desc_incond if campos.v_desc_incond is not None else Decimal(0)
    deducoes = campos.v_dr if campos.v_dr is not None else campos.v_calc_dr
    deducoes = deducoes if deducoes is not None else Decimal(0)
    reembolso = campos.v_calc_ree_rep_res if campos.v_calc_ree_rep_res is not None else Decimal(0)
    beneficio = campos.v_calc_bm if campos.v_calc_bm is not None else campos.v_red_bc_bm
    beneficio = beneficio if beneficio is not None else Decimal(0)
    recomposta = campos.v_serv - desconto - deducoes - reembolso - beneficio
    if recomposta != campos.v_bc:
        return (
            f"vBC ({campos.v_bc}) difere de vServ − vDescIncond − deduções "
            f"({recomposta}) no XML; termos opcionais ausentes contam como zero"
        )
    return None
