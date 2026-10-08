"""Campos da NFS-e TOMADA lidos do XML guardado — DL-078, frente A (item 1).

Função pura de leitura, no molde de `apps.fiscal.iss_nota` (que ela reusa para os campos
do ISS): não grava, não calcula e não decide. Campo ausente vira `None` e fica NOMEADO em
`ausentes`; nunca vira zero. No XML, a ausência de `tribFed` ou de `vRetCSLL` NÃO é "sem
retenção": a consulta de 08/10/2026 (item 3, aviso A8) manda tratá-la como "calculada fora
da nota". Campo presente fora do formato do XSD vira `None` e entra em `invalidos`. Todo
valor monetário é `Decimal` lido de TEXTO; `float` não entra aqui.

Caminhos conferidos no pacote oficial `nfse-esquemas_xsd-v1-01-20260209.zip` (sha256
e7935cbd9470527c6cc32984c1b2263e614183bf0139ce2733eaaed2de9a8072, o mesmo de `iss_nota`),
nas duas versões. Em cada constante: a linha do ELEMENTO em
`Schemas/1.01/tiposComplexos_v1.01.xsd` | `Schemas/1.00/tiposComplexos_v1.00.xsd`.
Os caminhos do ISS (vISSQN, tpRetISSQN, cLocIncid, vServ, vDescIncond) são os de
`iss_nota`, já conferidos lá.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.fiscal.iss_nota import (
    _PADRAO_COD_MUN,
    _PADRAO_DEC15V2,
    _PADRAO_TP_RET_ISSQN,
    CAMINHO_C_LOC_INCID,
    CAMINHO_TP_RET_ISSQN,
    CAMINHO_V_DESC_INCOND,
    CAMINHO_V_ISSQN,
    CAMINHO_V_SERV,
    VERSOES_LIDAS,
    _decimal,
    _elemento,
    _texto_validado,
)
from apps.fiscal.leitor import NS_NFSE, ArquivoRecusado, _raiz_segura

# dhEmi, TSDateTimeUTC. Só o DIA escrito no documento importa (HI-72): os 10 primeiros
# caracteres, no fuso do próprio emitente. Mesmo caminho de `apps.fiscal.escrituracao`.
# 1.01: tiposComplexos_v1.01.xsd:751 (TCInfDPS, :744) | 1.00: tiposComplexos_v1.00.xsd:301.
CAMINHO_DH_EMI = ("infNFSe", "DPS", "infDPS", "dhEmi")

# cLocPrestacao: município da prestação, em serv/locPrest (TCLocPrest). Usado só para a
# sugestão da natureza T3 (prestador de outro município). 1.01: :1316 (TCLocPrest :1314,
# obrigatório) | 1.00: :867 (minOccurs="0").
CAMINHO_C_LOC_PRESTACAO = ("infNFSe", "DPS", "infDPS", "serv", "locPrest", "cLocPrestacao")

# tpEmit, emitente da DPS: 1 prestador; 2 tomador; 3 intermediário. Valor 2 NÃO é só
# importação: o motivo está em cMotivoEmisTI (1 importação; 2, 3 e 4 emissão pelo tomador
# ou intermediário por obrigação municipal, recusa do prestador ou rejeição). Por isso o
# serviço recusa 2 e 3 sem distinguir o motivo (DL-078, decisão registrada).
# 1.01: tiposComplexos_v1.01.xsd:776 (TCInfDPS) | 1.00: tiposComplexos_v1.00.xsd:326.
CAMINHO_TP_EMIT = ("infNFSe", "DPS", "infDPS", "tpEmit")

# Situação perante o Simples Nacional, em infDPS/prest/regTrib (TCRegTrib).
# 1.01: :955 (TCRegTrib :953; regTrib :943 em TCInfoPrestador :877; prest :811) |
# 1.00: :484 (TCRegTrib :482; regTrib :471; prest :345).
CAMINHO_OP_SIMP_NAC = ("infNFSe", "DPS", "infDPS", "prest", "regTrib", "opSimpNac")
# Regime de apuração (opcional). 1.01: :965 | 1.00: :494 (minOccurs="0").
# Valor 3 = federais por fora do SN e municipal pelo SN (texto do próprio campo, 1.01).
CAMINHO_REG_AP_TRIB_SN = ("infNFSe", "DPS", "infDPS", "prest", "regTrib", "regApTribSN")

# Desconto condicionado, em infDPS/valores/vDescCondIncond (TCVDescCondIncond).
# 1.01: :1684 (TCVDescCondIncond :1677) | 1.00: :1290 (TCVDescCondIncond :1283).
CAMINHO_V_DESC_COND = ("infNFSe", "DPS", "infDPS", "valores", "vDescCondIncond", "vDescCond")

# Valor líquido, em infNFSe/valores (TCValoresNFSe). 1.01: :276 | 1.00: :266.
CAMINHO_V_LIQ = ("infNFSe", "valores", "vLiq")

# Grupo federal, em infDPS/valores/trib/tribFed (TCTribFederal). A linha do grupo:
# 1.01: :1645 (TCInfoTributacao :1636) | 1.00: :1249 (TCInfoTributacao :1240). Todos
# minOccurs="0". Os campos abaixo são o elemento de cada um dentro do grupo.
CAMINHO_V_RET_CP = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "vRetCP",
)  # 1.01: :1996 | 1.00: :1612
CAMINHO_V_RET_IRRF = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "vRetIRRF",
)  # 1.01: :2003 | 1.00: :1619
CAMINHO_V_RET_CSLL = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "vRetCSLL",
)  # 1.01: :2010 | 1.00: :1626
# PIS/COFINS, em tribFed/piscofins (TCTribOutrosPisCofins). vPis e vCofins são débito
# PRÓPRIO do prestador (apuração própria), não retenção; ver aviso "ambíguo" em `avisos`.
CAMINHO_TP_RET_PIS_COFINS = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "piscofins",
    "tpRetPisCofins",
)  # 1.01: :2098 | 1.00: :1715
CAMINHO_V_PIS = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "piscofins",
    "vPis",
)  # 1.01: :2084 | 1.00: :1701
CAMINHO_V_COFINS = (
    "infNFSe",
    "DPS",
    "infDPS",
    "valores",
    "trib",
    "tribFed",
    "piscofins",
    "vCofins",
)  # 1.01: :2091 | 1.00: :1708

# Tipos simples, pelo nome do tipo (tiposSimples_v1.0x.xsd, mesmo padrão nas duas versões).
# TSEmitenteDPS, TSOpSimpNac e TSRegimeApuracaoSimpNac: enumeração {1, 2, 3}.
_PADRAO_UM_A_TRES = re.compile(r"[123]")
# TSTipoRetPISCofins: enumeração {0..9} (tiposSimples_v1.01.xsd:1231; 1.00:1235).
_PADRAO_TP_RET_PIS_COFINS = re.compile(r"[0-9]")
# dhEmi: TSDateTimeUTC, início "AAAA-MM-DDT".
_PADRAO_DH_EMI = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T.*")


@dataclass(frozen=True)
class CamposTomada:
    """O que a leitura do XML encontrou para uma NFS-e TOMADA. Campo ausente fica `None`.

    `ausentes` e `invalidos` trazem o caminho legível de cada campo que faltou ou veio
    fora do formato. Quem consome decide o que a ausência significa; esta função nunca
    presume valor.
    """

    versao: str
    erro_leitura: str | None = None
    data_emissao: date | None = None
    c_loc_incid: str | None = None
    c_loc_prestacao: str | None = None
    tp_emit: str | None = None
    tp_ret_issqn: str | None = None
    v_iss_qn: Decimal | None = None
    v_serv: Decimal | None = None
    v_desc_incond: Decimal | None = None
    v_desc_cond: Decimal | None = None
    v_liq: Decimal | None = None
    op_simp_nac: str | None = None
    reg_ap_trib_sn: str | None = None
    v_ret_cp: Decimal | None = None
    v_ret_irrf: Decimal | None = None
    v_ret_csll: Decimal | None = None
    tp_ret_pis_cofins: str | None = None
    v_pis: Decimal | None = None
    v_cofins: Decimal | None = None
    ausentes: tuple[str, ...] = ()
    invalidos: tuple[str, ...] = ()


def _legivel(caminho) -> str:
    return "/".join(("NFSe",) + tuple(caminho))


def _data_do_dh_emi(raiz, ausentes: list, invalidos: list) -> date | None:
    elemento = _elemento(raiz, CAMINHO_DH_EMI)
    if elemento is None:
        ausentes.append(_legivel(CAMINHO_DH_EMI))
        return None
    texto = (elemento.text or "").strip()
    if not _PADRAO_DH_EMI.fullmatch(texto):
        invalidos.append(_legivel(CAMINHO_DH_EMI))
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        invalidos.append(_legivel(CAMINHO_DH_EMI))
        return None


def ler_campos_tomada(xml_bytes: bytes, versao: str) -> CamposTomada:
    """Lê os campos de uma NFS-e tomada. Não levanta exceção: XML ilegível vira `erro_leitura`.

    A leitura usa `_raiz_segura` (defusedxml, sem DTD), o mesmo caminho seguro da recepção.
    """
    if versao not in VERSOES_LIDAS:
        return CamposTomada(versao=versao, erro_leitura=f"versão sem leitura de tomada: {versao!r}")
    try:
        raiz = _raiz_segura(bytes(xml_bytes or b""))
    except ArquivoRecusado as exc:
        return CamposTomada(versao=versao, erro_leitura=str(exc))
    if raiz.tag != f"{{{NS_NFSE}}}NFSe":
        return CamposTomada(versao=versao, erro_leitura="elemento raiz diferente de NFSe")
    if _elemento(raiz, ("infNFSe",)) is None:
        return CamposTomada(versao=versao, erro_leitura="NFS-e sem infNFSe")

    ausentes: list[str] = []
    invalidos: list[str] = []

    def dec(caminho):
        return _decimal(raiz, caminho, _PADRAO_DEC15V2, ausentes, invalidos)

    def txt(caminho, padrao):
        return _texto_validado(raiz, caminho, padrao, ausentes, invalidos)

    return CamposTomada(
        versao=versao,
        data_emissao=_data_do_dh_emi(raiz, ausentes, invalidos),
        c_loc_incid=txt(CAMINHO_C_LOC_INCID, _PADRAO_COD_MUN),
        c_loc_prestacao=txt(CAMINHO_C_LOC_PRESTACAO, _PADRAO_COD_MUN),
        tp_emit=txt(CAMINHO_TP_EMIT, _PADRAO_UM_A_TRES),
        tp_ret_issqn=txt(CAMINHO_TP_RET_ISSQN, _PADRAO_TP_RET_ISSQN),
        v_iss_qn=dec(CAMINHO_V_ISSQN),
        v_serv=dec(CAMINHO_V_SERV),
        v_desc_incond=dec(CAMINHO_V_DESC_INCOND),
        v_desc_cond=dec(CAMINHO_V_DESC_COND),
        v_liq=dec(CAMINHO_V_LIQ),
        op_simp_nac=txt(CAMINHO_OP_SIMP_NAC, _PADRAO_UM_A_TRES),
        reg_ap_trib_sn=txt(CAMINHO_REG_AP_TRIB_SN, _PADRAO_UM_A_TRES),
        v_ret_cp=dec(CAMINHO_V_RET_CP),
        v_ret_irrf=dec(CAMINHO_V_RET_IRRF),
        v_ret_csll=dec(CAMINHO_V_RET_CSLL),
        tp_ret_pis_cofins=txt(CAMINHO_TP_RET_PIS_COFINS, _PADRAO_TP_RET_PIS_COFINS),
        v_pis=dec(CAMINHO_V_PIS),
        v_cofins=dec(CAMINHO_V_COFINS),
        ausentes=tuple(ausentes),
        invalidos=tuple(invalidos),
    )


def campos_tomada_do_documento(documento) -> CamposTomada:
    """Atalho: lê o `DocumentoFiscal` pelo XML guardado (`xml_original`) e pela versão."""
    return ler_campos_tomada(bytes(documento.xml_original or b""), documento.versao)
