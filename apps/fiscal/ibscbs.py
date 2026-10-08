"""Validador de conformidade IBS/CBS das NFS-e recebidas — DL-073, modo AVISO.

Nível 2 do plano docs/planos/DL-073-validador-ibscbs.md: relatório de
CONFERÊNCIA. Nada aqui grava dado, rejeita nota, calcula guia ou apuração.
Cada aviso aponta um indício para revisão e traz a fonte que o motiva; quem
decide é o contador.

Caminhos, tipos e regras vêm de docs/projeto/consultas/2026-10-08-leiaute-
ibscbs-nfse.md, conferidos nos XSD v1.01 (tiposComplexos_v1.01.xsd e
tiposSimples_v1.01.xsd) e no Anexo I v1.01 e Anexo VI v1.04.01 (NT 009),
consultados em 08/10/2026. Os arquivos oficiais não entram no repositório.

A leitura do XML reaproveita a leitura segura de `apps.fiscal.leitor`
(defusedxml, DE-074): nenhum parser novo é criado aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, localcontext

from apps.fiscal.leitor import NS_NFSE, ArquivoRecusado, _raiz_segura
from apps.fiscal.models import DocumentoFiscal, PapelDocumento

# ---------------------------------------------------------------------------
# Vigência, alíquotas e tolerância — constantes com fonte e data de consulta
# ---------------------------------------------------------------------------

# Cronograma do destaque IBS/CBS: 01/10/2026 para a maioria dos serviços da
# LC 116; 01/12/2026 para as demais categorias. O sistema não classifica a
# categoria do serviço, por isso o aviso cita as duas datas.
# Fonte: P&R NFS-e v1.1 (22/09/2026), item 15.1; consultado em 08/10/2026.
DATA_OBRIGATORIEDADE = date(2026, 10, 1)
DATA_OBRIGATORIEDADE_OUTRAS_CATEGORIAS = date(2026, 12, 1)

# Alíquotas de TESTE de 2026, válidas só para competência de 2026.
# CBS 0,9% — LC 214/2025, art. 346. IBS UF 0,1% — LC 214/2025, art. 343.
# IBS municipal 0 em 2026 — Informe Técnico 2025.002 v1.60, seção 05.
ANO_DAS_ALIQUOTAS_DE_TESTE = 2026
ALIQUOTA_CBS_TESTE_2026 = Decimal("0.90")
ALIQUOTA_IBS_UF_TESTE_2026 = Decimal("0.10")
ALIQUOTA_IBS_MUN_TESTE_2026 = Decimal("0")

# Margem de R$ 0,01 das comparações com a Calculadora oficial (coluna de
# observações do Anexo I v1.01, p. ex. E1539, E1578 e E1558). Não há regra de
# arredondamento oficial levantada em 08/10/2026: a comparação é
# |declarado − calculado| ≤ 0,01, sem arredondar o valor calculado.
TOLERANCIA = Decimal("0.01")

# Situação do TIPO DE LEIAUTE e da presença do grupo (texto para a tela).
SITUACAO_LEIAUTE_SEM_GRUPO = "leiaute sem grupo IBS/CBS"
SITUACAO_COM_GRUPO = "grupo IBS/CBS presente"
SITUACAO_SEM_GRUPO = "grupo IBS/CBS ausente"
SITUACAO_XML_ILEGIVEL = "XML ilegível"

VERSAO_SEM_GRUPO = "1.00"

# TSOpSimpNac (tiposSimples_v1.01.xsd, linha 996): 1 não optante; 2 MEI;
# 3 ME/EPP. Os dois últimos são optantes do Simples Nacional.
_NAO_OPTANTE = "1"
_OPTANTES_SIMPLES = ("2", "3")

# Fontes citadas nos avisos. Mudar um texto aqui muda todos os avisos que o
# usam — cada uma diz de onde veio o motivo do aviso.
FONTE_CRONOGRAMA = "P&R NFS-e v1.1, item 15.1 (22/09/2026)"
FONTE_E1515 = "Anexo I v1.01, regra E1515 (grupo da DPS exige grupo da NFS-e)"
FONTE_E1517 = "Anexo I v1.01, regra E1517 (grupo da NFS-e sem grupo da DPS)"
FONTE_CST = (
    "XSD NFS-e v1.01, tiposSimples_v1.01.xsd, TSRTCCodSitTrib ([0-9]{3}); "
    "Anexo VI v1.04.01 (NT 009), posição de CST"
)
FONTE_CCLASSTRIB = (
    "XSD NFS-e v1.01, tiposSimples_v1.01.xsd, TSRTCCodClassTrib ([0-9]{6}); "
    "Anexo VI v1.04.01 (NT 009), posição de cClassTrib"
)
FONTE_ALIQ_CBS = (
    "LC 214/2025, art. 346 (CBS 0,9%); Informe Técnico 2025.002 v1.60, seção 05; "
    "Anexo I v1.01, regra E1558"
)
FONTE_ALIQ_IBS_UF = (
    "LC 214/2025, art. 343 (IBS UF 0,1%); Informe Técnico 2025.002 v1.60, seção 05; "
    "Anexo I v1.01, regra E1539"
)
FONTE_ALIQ_IBS_MUN = (
    "Informe Técnico 2025.002 v1.60, seção 05 (IBS municipal 0 em 2026); Anexo I v1.01, regra E1578"
)
FONTE_VALOR_CBS = (
    "Anexo VI v1.04.01 (NT 009), NFSe/infNFSe/IBSCBS/totCIBS/gCBS/vCBS: "
    "vCBS = vBC x (pCBS ou pAliqEfetCBS); Anexo I v1.01, regra E1582"
)
FONTE_VALOR_IBS_UF = (
    "HIPÓTESE do DL-073 (item 6): vIBSUF = vBC x alíquota efetiva da UF; "
    "Anexo I v1.01, regra E1568 (comparação com a Calculadora)"
)
FONTE_VALOR_IBS_MUN = (
    "HIPÓTESE do DL-073 (item 6): vIBSMun = vBC x alíquota efetiva do município; "
    "Anexo I v1.01, regra E1572 (comparação com a Calculadora)"
)
FONTE_E1530 = (
    "Anexo I v1.01, regra E1530 (fórmula de 2026); "
    "XSD NFS-e v1.01, tiposComplexos_v1.01.xsd, TCRTCValoresIBSCBS/vBC"
)
FONTE_GRUPO_XSD = "XSD NFS-e v1.01, tiposComplexos_v1.01.xsd (TCRTCIBSCBS e tipos filhos)"
FONTE_DECIMAL = "XSD NFS-e v1.01, tiposSimples_v1.01.xsd (TSDec2V2, TSDec15V2)"
FONTE_LEITURA = "Leitura segura do leitor da NFS-e (apps/fiscal/leitor.py, DE-074)"

# Decimal a partir de TEXTO, nunca float (AGENTS.md §10). Aceita "0.9" e
# "0.90" (critério 8 do plano) e não aceita vírgula, sinal nem notação
# científica. A precisão de casas decimais do XSD não é julgada aqui: o
# leitor da NFS-e já recusa isso nos campos vServ e vLiq.
_PADRAO_DECIMAL = re.compile(r"[0-9]{1,15}(\.[0-9]{1,6})?")
_PADRAO_CST = re.compile(r"[0-9]{3}")
_PADRAO_CCLASSTRIB = re.compile(r"[0-9]{6}")

_NS = {"n": NS_NFSE}

# Caminhos relativos à raiz NFSe, como tuplas de nomes de elemento. Cada um
# foi conferido no XSD v1.01 (ver docs/projeto/consultas/2026-10-08-leiaute-
# ibscbs-nfse.md, seções 2.1 a 2.4, com linhas de tiposComplexos_v1.01.xsd).
_P_GRUPO_NFSE = ("infNFSe", "IBSCBS")  # TCRTCIBSCBS, linha 142 e 287
_P_GRUPO_DPS = ("infNFSe", "DPS", "infDPS", "IBSCBS")  # TCInfDPS, linha 838
_P_OPSIMPNAC = ("infNFSe", "DPS", "infDPS", "prest", "regTrib", "opSimpNac")  # linha 955
_P_CST_PRODUCAO = _P_GRUPO_DPS + ("valores", "trib", "gIBSCBS", "CST")  # linha 2627
_P_CCLASSTRIB_PRODUCAO = _P_GRUPO_DPS + ("valores", "trib", "gIBSCBS", "cClassTrib")  # 2634
_P_CST_NT009 = _P_GRUPO_DPS + ("valores", "trib", "CST")  # NT 009, leiaute, linha 423
_P_CCLASSTRIB_NT009 = _P_GRUPO_DPS + ("valores", "trib", "cClassTrib")  # NT 009, linha 424
_P_VSERV = ("infNFSe", "DPS", "infDPS", "valores", "vServPrest", "vServ")  # linha 1669
_P_VDESCINCOND = ("infNFSe", "DPS", "infDPS", "valores", "vDescCondIncond", "vDescIncond")  # 1679
_P_VPIS = ("infNFSe", "DPS", "infDPS", "valores", "trib", "tribFed", "piscofins", "vPis")  # 2084
_P_VCOFINS = ("infNFSe", "DPS", "infDPS", "valores", "trib", "tribFed", "piscofins", "vCofins")
_P_VISSQN = ("infNFSe", "valores", "vISSQN")  # TCValoresNFSe, linha 261
_P_VCALCREEREPRES = _P_GRUPO_NFSE + ("valores", "vCalcReeRepRes")  # linha 338
_P_VBC = _P_GRUPO_NFSE + ("valores", "vBC")  # linha 329
_P_PIBSUF = _P_GRUPO_NFSE + ("valores", "uf", "pIBSUF")  # linha 373
_P_PALIQEFETUF = _P_GRUPO_NFSE + ("valores", "uf", "pAliqEfetUF")  # linha 387
_P_PIBSMUN = _P_GRUPO_NFSE + ("valores", "mun", "pIBSMun")  # linha 400
_P_PALIQEFETMUN = _P_GRUPO_NFSE + ("valores", "mun", "pAliqEfetMun")  # linha 414
_P_PCBS = _P_GRUPO_NFSE + ("valores", "fed", "pCBS")  # linha 427
_P_PALIQEFETCBS = _P_GRUPO_NFSE + ("valores", "fed", "pAliqEfetCBS")  # linha 441
_P_VIBSTOT = _P_GRUPO_NFSE + ("totCIBS", "gIBS", "vIBSTot")  # linha 497
_P_VIBSUF = _P_GRUPO_NFSE + ("totCIBS", "gIBS", "gIBSUFTot", "vIBSUF")  # linha 559
_P_VIBSMUN = _P_GRUPO_NFSE + ("totCIBS", "gIBS", "gIBSMunTot", "vIBSMun")  # linha 580
_P_VCBS = _P_GRUPO_NFSE + ("totCIBS", "gCBS", "vCBS")  # linha 608

# Elementos que o validador PRECISA para conferir o grupo. Se o grupo existe
# e um deles falta, o aviso `elemento_ausente` o nomeia (critério 9).
_OBRIGATORIOS_COM_GRUPO = (
    _P_VSERV,
    _P_VBC,
    _P_PIBSUF,
    _P_PIBSMUN,
    _P_PCBS,
    _P_VIBSUF,
    _P_VIBSMUN,
    _P_VCBS,
)

# Termos OPCIONAIS da fórmula da E1530 (ausência conta como zero; presença
# com valor ilegível faz a conferência ser pulada, com o aviso de valor).
_TERMOS_OPCIONAIS_DA_E1530 = (
    _P_VDESCINCOND,
    _P_VCALCREEREPRES,
    _P_VISSQN,
    _P_VPIS,
    _P_VCOFINS,
)

# Precisão exata para os produtos e as diferenças (nunca o contexto padrão de
# 28 dígitos, que poderia arredondar uma soma com muitas casas).
_CONTEXTO_EXATO = Context(prec=60)


@dataclass(frozen=True)
class Aviso:
    """Um indício de desconformidade. `codigo` é curto e estável; `mensagem`
    é o texto em português para o contador; `fonte` diz de onde vem a
    regra, com item, artigo ou regra E-código."""

    codigo: str
    mensagem: str
    fonte: str


@dataclass(frozen=True)
class GrupoIBSCBS:
    """O que a leitura do XML encontrou. Campo ausente fica `None`; nada é
    presumido. Só `Decimal` para valor e alíquota (nunca `float`)."""

    versao: str
    erro_leitura: str | None = None
    tem_grupo_nfse: bool = False
    tem_grupo_dps: bool = False
    regime_opsimpnac: str | None = None
    cst_producao: str | None = None
    cclasstrib_producao: str | None = None
    cst_nt009: str | None = None
    cclasstrib_nt009: str | None = None
    v_serv: Decimal | None = None
    v_desc_incond: Decimal | None = None
    v_calc_ree_rep_res: Decimal | None = None
    v_iss_qn: Decimal | None = None
    v_pis: Decimal | None = None
    v_cofins: Decimal | None = None
    v_bc: Decimal | None = None
    p_ibs_uf: Decimal | None = None
    p_aliq_efet_uf: Decimal | None = None
    p_ibs_mun: Decimal | None = None
    p_aliq_efet_mun: Decimal | None = None
    p_cbs: Decimal | None = None
    p_aliq_efet_cbs: Decimal | None = None
    v_ibs_uf: Decimal | None = None
    v_ibs_mun: Decimal | None = None
    v_ibs_tot: Decimal | None = None
    v_cbs: Decimal | None = None
    ausentes: tuple[str, ...] = ()
    invalidos: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotaConferida:
    """Uma NFS-e da empresa com a situação e os avisos de conformidade."""

    documento: DocumentoFiscal
    situacao: str
    avisos: tuple[Aviso, ...]


# ---------------------------------------------------------------------------
# Leitura (sem regra de negócio: só interpreta bytes)
# ---------------------------------------------------------------------------


def _achar(raiz, caminho):
    return raiz.find("/".join(f"n:{parte}" for parte in caminho), _NS)


def _legivel(caminho):
    return "/".join(("NFSe",) + caminho)


def _texto(raiz, caminho):
    elemento = _achar(raiz, caminho)
    if elemento is None:
        return None
    return (elemento.text or "").strip()


def _decimal(raiz, caminho, invalidos, ausentes):
    """`Decimal` do campo, ou `None`. `ausentes` é a lista a preencher quando o
    elemento falta (`None` quando a ausência não importa)."""
    elemento = _achar(raiz, caminho)
    if elemento is None:
        if ausentes is not None:
            ausentes.append(_legivel(caminho))
        return None
    texto = (elemento.text or "").strip()
    if not _PADRAO_DECIMAL.fullmatch(texto):
        invalidos.append(_legivel(caminho))
        return None
    return Decimal(texto)


def ler_grupo_ibscbs(xml_bytes: bytes, versao: str) -> GrupoIBSCBS:
    """Lê o grupo IBS/CBS da NFS-e e da DPS embutida. Não levanta exceção:
    XML ilegível vira `erro_leitura` (critério 9)."""
    try:
        raiz = _raiz_segura(bytes(xml_bytes))
    except ArquivoRecusado as exc:
        return GrupoIBSCBS(versao=versao, erro_leitura=str(exc))
    if raiz.tag != f"{{{NS_NFSE}}}NFSe":
        return GrupoIBSCBS(versao=versao, erro_leitura="elemento raiz diferente de NFSe")
    if _achar(raiz, ("infNFSe",)) is None:
        return GrupoIBSCBS(versao=versao, erro_leitura="NFS-e sem infNFSe")

    tem_nfse = _achar(raiz, _P_GRUPO_NFSE) is not None
    tem_dps = _achar(raiz, _P_GRUPO_DPS) is not None
    ausentes: list[str] = []
    invalidos: list[str] = []
    # A ausência de um campo do grupo só é problema quando o grupo existe.
    exigidos = ausentes if tem_nfse else None

    return GrupoIBSCBS(
        versao=versao,
        tem_grupo_nfse=tem_nfse,
        tem_grupo_dps=tem_dps,
        regime_opsimpnac=_texto(raiz, _P_OPSIMPNAC),
        cst_producao=_texto(raiz, _P_CST_PRODUCAO),
        cclasstrib_producao=_texto(raiz, _P_CCLASSTRIB_PRODUCAO),
        cst_nt009=_texto(raiz, _P_CST_NT009),
        cclasstrib_nt009=_texto(raiz, _P_CCLASSTRIB_NT009),
        v_serv=_decimal(raiz, _P_VSERV, invalidos, exigidos),
        v_desc_incond=_decimal(raiz, _P_VDESCINCOND, invalidos, None),
        v_calc_ree_rep_res=_decimal(raiz, _P_VCALCREEREPRES, invalidos, None),
        v_iss_qn=_decimal(raiz, _P_VISSQN, invalidos, None),
        v_pis=_decimal(raiz, _P_VPIS, invalidos, None),
        v_cofins=_decimal(raiz, _P_VCOFINS, invalidos, None),
        v_bc=_decimal(raiz, _P_VBC, invalidos, exigidos),
        p_ibs_uf=_decimal(raiz, _P_PIBSUF, invalidos, exigidos),
        p_aliq_efet_uf=_decimal(raiz, _P_PALIQEFETUF, invalidos, None),
        p_ibs_mun=_decimal(raiz, _P_PIBSMUN, invalidos, exigidos),
        p_aliq_efet_mun=_decimal(raiz, _P_PALIQEFETMUN, invalidos, None),
        p_cbs=_decimal(raiz, _P_PCBS, invalidos, exigidos),
        p_aliq_efet_cbs=_decimal(raiz, _P_PALIQEFETCBS, invalidos, None),
        v_ibs_uf=_decimal(raiz, _P_VIBSUF, invalidos, exigidos),
        v_ibs_mun=_decimal(raiz, _P_VIBSMUN, invalidos, exigidos),
        v_ibs_tot=_decimal(raiz, _P_VIBSTOT, invalidos, None),
        v_cbs=_decimal(raiz, _P_VCBS, invalidos, exigidos),
        ausentes=tuple(ausentes),
        invalidos=tuple(invalidos),
    )


# ---------------------------------------------------------------------------
# Formatação e aritmética (texto para o contador; cálculo exato)
# ---------------------------------------------------------------------------


def _numero_ptbr(valor: Decimal) -> str:
    """Texto pt-BR para mensagem: duas casas quando o valor cabe nelas, sem
    arredondar o que não cabe (ex.: 0,90 e 0,125)."""
    duas_casas = valor.quantize(Decimal("0.01"))
    texto = format(duas_casas if duas_casas == valor else valor, "f")
    return texto.replace(".", ",")


def _percentual_de(base: Decimal, taxa_percentual: Decimal) -> Decimal:
    """base × taxa / 100, exato. A taxa vem em PERCENTUAL (0,90 = 0,9%)."""
    with localcontext(_CONTEXTO_EXATO):
        return base * taxa_percentual / Decimal(100)


def _dentro_da_tolerancia(declarado: Decimal, esperado: Decimal) -> bool:
    with localcontext(_CONTEXTO_EXATO):
        return abs(declarado - esperado) <= TOLERANCIA


def _zero_se_ausente(valor: Decimal | None) -> Decimal:
    return Decimal("0") if valor is None else valor


def _primeiro_definido(*valores):
    """O primeiro valor que NÃO é `None`. Não usa `or`: `Decimal("0")` é falso
    e um percentual de zero (alíquota efetiva zerada por redução total) não
    pode cair no valor nominal por engano."""
    for valor in valores:
        if valor is not None:
            return valor
    return None


# ---------------------------------------------------------------------------
# As verificações (uma função por regra do plano DL-073)
# ---------------------------------------------------------------------------


def _verificar_presenca(g: GrupoIBSCBS, competencia: date) -> list[Aviso]:
    """Verificação 2 do plano: ausência do grupo, só para prestador não
    optante e competência a partir de 01/10/2026."""
    if g.tem_grupo_nfse or g.tem_grupo_dps or competencia < DATA_OBRIGATORIEDADE:
        return []
    if g.regime_opsimpnac in _OPTANTES_SIMPLES:
        return []
    if g.regime_opsimpnac == _NAO_OPTANTE:
        return [
            Aviso(
                "grupo_ausente",
                "Sem grupo IBS/CBS em nota de competência a partir de "
                f"{DATA_OBRIGATORIEDADE:%d/%m/%Y}, de prestador não optante do Simples. "
                "É obrigatório desde essa data para a maioria dos serviços da LC 116 e "
                f"desde {DATA_OBRIGATORIEDADE_OUTRAS_CATEGORIAS:%d/%m/%Y} para as demais "
                "categorias; o sistema não classifica a categoria do serviço. Até "
                "31/12/2026 a ausência não rejeita a nota, mas é desconformidade.",
                FONTE_CRONOGRAMA,
            )
        ]
    return [
        Aviso(
            "regime_nao_informado",
            "Sem grupo IBS/CBS em nota de competência a partir de "
            f"{DATA_OBRIGATORIEDADE:%d/%m/%Y}, e regime do prestador não informado na "
            "nota — conferir.",
            f"{FONTE_CRONOGRAMA}; TSOpSimpNac (prest/regTrib/opSimpNac)",
        )
    ]


def _verificar_coerencia(g: GrupoIBSCBS) -> list[Aviso]:
    """Verificação 3 do plano: o grupo está em um lado e não no outro."""
    if g.tem_grupo_dps and not g.tem_grupo_nfse:
        return [
            Aviso(
                "grupo_so_na_dps",
                "Grupo IBS/CBS informado na DPS e ausente na NFS-e.",
                FONTE_E1515,
            )
        ]
    if g.tem_grupo_nfse and not g.tem_grupo_dps:
        return [
            Aviso(
                "grupo_so_na_nfse",
                "Grupo IBS/CBS informado na NFS-e e ausente na DPS.",
                FONTE_E1517,
            )
        ]
    return []


def _conferir_codigo(*, rotulo, slug, padrao, digitos, fonte, posicoes):
    presentes = [(caminho, valor) for caminho, valor in posicoes if valor is not None]
    if not presentes:
        onde = " ou ".join(caminho for caminho, _ in posicoes)
        return [Aviso(f"{slug}_ausente", f"{rotulo} não encontrado na DPS (em {onde}).", fonte)]
    avisos = []
    for caminho, valor in presentes:
        if not padrao.fullmatch(valor):
            avisos.append(
                Aviso(
                    f"{slug}_formato",
                    f"{rotulo} '{valor}' em {caminho} não tem {digitos} dígitos numéricos.",
                    fonte,
                )
            )
    if len({valor for _, valor in presentes}) > 1:
        detalhe = "; ".join(f"{caminho}: '{valor}'" for caminho, valor in presentes)
        avisos.append(
            Aviso(
                f"{slug}_divergente",
                f"{rotulo} diferente entre as duas posições ({detalhe}).",
                fonte,
            )
        )
    return avisos


def _verificar_codigos_tributarios(g: GrupoIBSCBS) -> list[Aviso]:
    """Verificação 4 do plano: CST e cClassTrib nas DUAS posições. A
    existência do código na tabela oficial NÃO é verificada aqui (a tabela
    ainda não é importada)."""
    if not g.tem_grupo_dps:
        return []
    avisos = _conferir_codigo(
        rotulo="CST",
        slug="cst",
        padrao=_PADRAO_CST,
        digitos=3,
        fonte=FONTE_CST,
        posicoes=(
            (_legivel(_P_CST_PRODUCAO), g.cst_producao),
            (_legivel(_P_CST_NT009), g.cst_nt009),
        ),
    )
    avisos += _conferir_codigo(
        rotulo="cClassTrib",
        slug="cclasstrib",
        padrao=_PADRAO_CCLASSTRIB,
        digitos=6,
        fonte=FONTE_CCLASSTRIB,
        posicoes=(
            (_legivel(_P_CCLASSTRIB_PRODUCAO), g.cclasstrib_producao),
            (_legivel(_P_CCLASSTRIB_NT009), g.cclasstrib_nt009),
        ),
    )
    return avisos


def _verificar_aliquotas(g: GrupoIBSCBS, competencia: date) -> list[Aviso]:
    """Verificação 5 do plano: alíquotas de TESTE, só em 2026. Para 2027 em
    diante não há alíquota confirmada aqui, então nada é conferido."""
    if not g.tem_grupo_nfse or competencia.year != ANO_DAS_ALIQUOTAS_DE_TESTE:
        return []
    avisos = []
    conferencias = (
        ("pCBS", "aliquota_cbs", g.p_cbs, ALIQUOTA_CBS_TESTE_2026, FONTE_ALIQ_CBS),
        ("pIBSUF", "aliquota_ibs_uf", g.p_ibs_uf, ALIQUOTA_IBS_UF_TESTE_2026, FONTE_ALIQ_IBS_UF),
        (
            "pIBSMun",
            "aliquota_ibs_mun",
            g.p_ibs_mun,
            ALIQUOTA_IBS_MUN_TESTE_2026,
            FONTE_ALIQ_IBS_MUN,
        ),
    )
    for campo, codigo, declarada, esperada, fonte in conferencias:
        if declarada is not None and declarada != esperada:
            avisos.append(
                Aviso(
                    codigo,
                    f"{campo} declarado {_numero_ptbr(declarada)}; a alíquota de teste "
                    f"de {ANO_DAS_ALIQUOTAS_DE_TESTE} é {_numero_ptbr(esperada)}.",
                    fonte,
                )
            )
    return avisos


def _verificar_valores_do_grupo(g: GrupoIBSCBS, competencia: date) -> list[Aviso]:
    """Verificações 6 e 7 do plano: aritmética de vCBS, vIBSUF e vIBSMun com a
    alíquota efetiva quando a nota a informa (NT 009: vCBS = vBC x (pCBS ou
    pAliqEfetCBS)), e a fórmula da E1530 de 2026 para vBC."""
    if not g.tem_grupo_nfse or g.v_bc is None:
        return []  # ausência já avisada por `elemento_ausente`
    avisos = []
    conferencias = (
        (
            "vCBS",
            "valor_cbs",
            g.v_cbs,
            _primeiro_definido(g.p_aliq_efet_cbs, g.p_cbs),
            FONTE_VALOR_CBS,
        ),
        (
            "vIBSUF",
            "valor_ibs_uf",
            g.v_ibs_uf,
            _primeiro_definido(g.p_aliq_efet_uf, g.p_ibs_uf),
            FONTE_VALOR_IBS_UF,
        ),
        (
            "vIBSMun",
            "valor_ibs_mun",
            g.v_ibs_mun,
            _primeiro_definido(g.p_aliq_efet_mun, g.p_ibs_mun),
            FONTE_VALOR_IBS_MUN,
        ),
    )
    for campo, codigo, declarado, taxa, fonte in conferencias:
        if declarado is None or taxa is None:
            continue  # valor ausente ou ilegível já avisado
        esperado = _percentual_de(g.v_bc, taxa)
        if not _dentro_da_tolerancia(declarado, esperado):
            avisos.append(
                Aviso(
                    codigo,
                    f"{campo} declarado {_numero_ptbr(declarado)}; base "
                    f"{_numero_ptbr(g.v_bc)} x alíquota {_numero_ptbr(taxa)}% dá "
                    f"{_numero_ptbr(esperado)}. Diferença acima de R$ 0,01.",
                    fonte,
                )
            )
    if competencia.year == ANO_DAS_ALIQUOTAS_DE_TESTE:
        avisos += _verificar_base_da_e1530(g)
    return avisos


def _verificar_base_da_e1530(g: GrupoIBSCBS) -> list[Aviso]:
    if g.v_serv is None or g.v_bc is None:
        return []
    if any(_legivel(caminho) in g.invalidos for caminho in _TERMOS_OPCIONAIS_DA_E1530):
        return []  # valor ilegível de um termo: conferir a base seria chutar
    esperado = (
        g.v_serv
        - _zero_se_ausente(g.v_desc_incond)
        - _zero_se_ausente(g.v_calc_ree_rep_res)
        - _zero_se_ausente(g.v_iss_qn)
        - _zero_se_ausente(g.v_pis)
        - _zero_se_ausente(g.v_cofins)
    )
    if _dentro_da_tolerancia(g.v_bc, esperado):
        return []
    return [
        Aviso(
            "base_calculo",
            f"vBC declarado {_numero_ptbr(g.v_bc)}; a fórmula da E1530 para 2026 "
            "(vServ − vDescIncond − vCalcReeRepRes − vISSQN − vPis − vCofins) dá "
            f"{_numero_ptbr(esperado)}. Diferença acima de R$ 0,01.",
            FONTE_E1530,
        )
    ]


def _verificar_ausentes(g: GrupoIBSCBS) -> list[Aviso]:
    return [
        Aviso(
            "elemento_ausente",
            f"Elemento esperado ausente: {caminho}. A conferência que depende dele não foi feita.",
            FONTE_GRUPO_XSD,
        )
        for caminho in g.ausentes
    ]


def _verificar_invalidos(g: GrupoIBSCBS) -> list[Aviso]:
    return [
        Aviso(
            "valor_invalido",
            f"Valor fora do formato decimal em {caminho}; o campo não foi conferido.",
            FONTE_DECIMAL,
        )
        for caminho in g.invalidos
    ]


# ---------------------------------------------------------------------------
# Interface do módulo
# ---------------------------------------------------------------------------


def _avaliar(documento) -> tuple[str, tuple[Aviso, ...]]:
    """Situação e avisos de UMA nota. Não consulta banco: só lê os atributos
    do documento (por isso a lista da empresa custa uma consulta só)."""
    if documento.versao == VERSAO_SEM_GRUPO:
        return SITUACAO_LEIAUTE_SEM_GRUPO, ()
    g = ler_grupo_ibscbs(bytes(documento.xml_original), documento.versao)
    if g.erro_leitura is not None:
        aviso = Aviso(
            "xml_ilegivel",
            f"XML não pôde ser lido: {g.erro_leitura}.",
            FONTE_LEITURA,
        )
        return SITUACAO_XML_ILEGIVEL, (aviso,)

    competencia = documento.d_competencia
    avisos = [
        *_verificar_presenca(g, competencia),
        *_verificar_coerencia(g),
        *_verificar_codigos_tributarios(g),
        *_verificar_aliquotas(g, competencia),
        *_verificar_valores_do_grupo(g, competencia),
        *_verificar_ausentes(g),
        *_verificar_invalidos(g),
    ]
    situacao = SITUACAO_COM_GRUPO if (g.tem_grupo_nfse or g.tem_grupo_dps) else SITUACAO_SEM_GRUPO
    return situacao, tuple(avisos)


def avaliar_conformidade(documento) -> list[Aviso]:
    """Avisos de conformidade IBS/CBS de UMA nota (`DocumentoFiscal`). Lista
    vazia quando não há indício; leiaute 1.00 nunca gera aviso."""
    return list(_avaliar(documento)[1])


def situacao_de_conformidade(documento) -> str:
    """Texto da situação da nota: leiaute sem grupo, grupo presente ou
    ausente, ou XML ilegível. Não é um veredito de conformidade."""
    return _avaliar(documento)[0]


def conformidade_do_mes(empresa, ano: int, mes: int) -> list[NotaConferida]:
    """Notas em que a empresa é PRESTADORA, com competência no mês, e a
    conferência de cada uma. Uma consulta ao banco para os documentos; o
    parsing é feito em memória (sem N+1). Isolamento: só documentos do
    escritório da empresa."""
    documentos = DocumentoFiscal.objects.filter(
        escritorio_id=empresa.escritorio_id,
        vinculos__empresa=empresa,
        vinculos__papel=PapelDocumento.PRESTADOR,
        d_competencia__year=ano,
        d_competencia__month=mes,
    ).order_by("dh_emissao", "id")
    notas = []
    for documento in documentos:
        situacao, avisos = _avaliar(documento)
        notas.append(NotaConferida(documento=documento, situacao=situacao, avisos=avisos))
    return notas
