"""Retenções destacadas na NFS-e TOMADA — DL-078, frente A (escopo itens 4 e 5).

Só LÊ e TOTALIZA o que a nota destaca (HI-94 e HI-95). Não recalcula alíquota, não decide se a
retenção era devida e não gera guia: DAM, DARF, EFD-Reinf e DCTFWeb ficam fora. Entram no total
só escriturações EFETIVADAS de notas NÃO canceladas. Rascunho, estornada e cancelada ficam de
fora, e a cancelada depois de escriturada aparece à parte, nunca somada em silêncio.

ISS retido (HI-94, item 0 da DL-078 frente B): entra toda tomada efetivada com tpRetISSQN 2,
seja qual for a natureza do prestador (T1, T5, T6 ou T7). O tipo do prestador e a retenção são
independentes: retenção sobre prestador do Simples é legítima (Res. CGSN 140, art. 27; LC 123,
art. 21, § 4º, indicados pelo arquiteto-senior, não conferidos nesta etapa).

Três relógios de competência (HI-96; consulta, item 4):
- ISS retido a recolher: mês de `dCompet` (RCTM art. 145). Vencimento pela regra do município.
- INSS (vRetCP): mês de EMISSÃO (Lei 8.212, art. 31). Vencimento informativo no dia 20.
- IRRF e CSRF: DATA DE PAGAMENTO informada pelo contador. Sem ela, a retenção fica pendente,
  e nunca é presumida como paga no dia da emissão nem na competência.

Ausência nunca vira zero: campo que a nota não destaca fica fora da soma, e o total de um
grupo sem nenhum valor destacado é None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.fiscal import iss_municipal
from apps.fiscal.models import (
    EscrituracaoTomada,
    EstadoEscrituracao,
    NaturezaTomada,
    PapelDocumento,
)
from apps.fiscal.services import documentos_do_escritorio
from apps.fiscal.tomadas import (
    PALMAS,
    AvisoTomada,
    avisos_da_tomada,
    dados_da_escrituracao,
    regime_em,
)

# Vencimento informativo do INSS retido (Lei 8.212, art. 31, red. Lei 11.933/2009). O texto
# da lei admite o dia útil anterior quando não há expediente bancário: o produto mostra o dia
# nominal e não calcula feriado.
DIA_VENCIMENTO_INSS = 20
FUNDAMENTO_INSS = "Lei 8.212, art. 31, red. Lei 11.933/2009 (lido); informativo, sem cálculo"

# Naturezas que totalizam o ISS retido quando tpRetISSQN é 2. A retenção não depende do tipo do
# prestador (HI-94): T5 (MEI), T6 (Simples) e T7 (pessoa física) entram como T1. T2 e T3 ficam de
# fora por construção: a efetivação exige tpRetISSQN 1 nelas (`tomadas._recusa_de_natureza`).
NATUREZAS_COM_ISS_RETIDO = frozenset(
    {
        NaturezaTomada.TOMADO_ISS_RETIDO_PELO_CLIENTE,
        NaturezaTomada.TOMADO_DE_MEI,
        NaturezaTomada.TOMADO_DE_SIMPLES,
        NaturezaTomada.TOMADO_DE_PESSOA_FISICA,
    }
)

# Fundamento do aviso de MEI com ISS retido. Inferência, não norma lida: o texto de LC 123, art.
# 18-A não foi conferido nesta etapa (a citação vem do DL-067, MF-SN-12).
FUNDAMENTO_AVISO_MEI = (
    "LC 123, art. 18-A (citado no DL-067, MF-SN-12; texto não conferido); consulta, item 1 "
    "(inferência). Informativo: nenhum valor é alterado."
)


@dataclass(frozen=True)
class GrupoIssRetido:
    """ISS retido de UM município de incidência, no mês de competência."""

    municipio: str | None
    # Soma do vISSQN das notas COM valor destacado. None quando nenhuma nota do grupo tem valor:
    # retenção sem ISS destacado não é zero (ver `sem_valor`).
    total: Decimal | None
    notas: tuple[EscrituracaoTomada, ...]
    # Retidas (tpRetISSQN 2, qualquer natureza do ISS_RETIDO) sem vISSQN no XML:
    # "retida sem valor destacado — conferir".
    sem_valor: tuple[EscrituracaoTomada, ...]
    vencimento: date | None
    vencimento_texto: str
    regra_dia_nao_util: str


@dataclass(frozen=True)
class IssRetidoAReceber:
    ano: int
    mes: int
    grupos: tuple[GrupoIssRetido, ...]
    # Efetivadas com tpRetISSQN 2 numa natureza FORA de NATUREZAS_COM_ISS_RETIDO. Hoje vazio por
    # construção (a efetivação recusa esse caso), e mantido porque a API lê este campo. Se
    # aparecer, fica visível e de fora do total, nunca somado nem sumido em silêncio.
    fora_do_total: tuple[EscrituracaoTomada, ...]
    canceladas: tuple[EscrituracaoTomada, ...]
    avisos: tuple[tuple[EscrituracaoTomada, AvisoTomada], ...]


@dataclass(frozen=True)
class PagamentoRetido:
    """Retenção de UMA data de pagamento informada (IRRF ou CSRF)."""

    data_pagamento: date
    total: Decimal | None
    notas: tuple[EscrituracaoTomada, ...]


@dataclass(frozen=True)
class RetencoesFederais:
    ano: int
    mes: int
    # INSS (vRetCP) das notas EMITIDAS no mês. Vencimento informativo.
    inss_total: Decimal | None
    inss_notas: tuple[EscrituracaoTomada, ...]
    inss_vencimento: date
    inss_vencimento_texto: str
    # IRRF e CSRF (vRetIRRF e vRetCSLL) das notas com data de PAGAMENTO no mês, por data.
    irrf_por_pagamento: tuple[PagamentoRetido, ...]
    csrf_por_pagamento: tuple[PagamentoRetido, ...]
    irrf_total: Decimal | None
    csrf_total: Decimal | None
    # IRRF ou CSRF retido SEM data de pagamento, das notas com competência no mês.
    pendentes_de_pagamento: tuple[EscrituracaoTomada, ...]
    canceladas: tuple[EscrituracaoTomada, ...]
    avisos: tuple[tuple[EscrituracaoTomada, AvisoTomada], ...]


def _efetivadas(empresa, **filtro):
    """(válidas, canceladas). Uma escrituração efetivada de nota NÃO cancelada é válida.

    A situação de cancelamento vem de `documentos_do_escritorio` (anotação `cancelada`, na
    fonte única), numa só consulta. A consulta parte do escritório da empresa (AGENTS.md §11).
    """
    escrituracoes = list(
        EscrituracaoTomada.objects.filter(
            empresa=empresa,
            estado=EstadoEscrituracao.EFETIVADA,
            vinculo__papel=PapelDocumento.TOMADOR,
            vinculo__documento__escritorio=empresa.escritorio,
            **filtro,
        )
        .select_related("vinculo__documento")
        .order_by("vinculo__documento__dh_emissao", "id")
    )
    if not escrituracoes:
        return [], []
    ids = {e.vinculo.documento_id for e in escrituracoes}
    canceladas_ids = {
        documento.pk
        for documento in documentos_do_escritorio(empresa.escritorio, empresa=empresa).filter(
            pk__in=ids
        )
        if documento.cancelada
    }
    validas = [e for e in escrituracoes if e.vinculo.documento_id not in canceladas_ids]
    canceladas = [e for e in escrituracoes if e.vinculo.documento_id in canceladas_ids]
    return validas, canceladas


def _positivo(valor: Decimal | None) -> bool:
    return valor is not None and valor > 0


def _soma(valores) -> Decimal | None:
    """Soma exata em Decimal dos valores PRESENTES. Nenhum presente devolve None, nunca zero."""
    presentes = [valor for valor in valores if valor is not None]
    if not presentes:
        return None
    return sum(presentes, Decimal("0.00"))


def _avisos_das_notas(
    empresa, notas, regimes: dict
) -> tuple[tuple[EscrituracaoTomada, AvisoTomada], ...]:
    """Avisos A1 a A8 de cada nota, com o regime do tomador só quando A4 pode disparar."""
    pares = []
    for escrituracao in notas:
        regime = None
        if _positivo(escrituracao.v_ret_csll):
            competencia = escrituracao.data_competencia
            if competencia not in regimes:
                regimes[competencia] = regime_em(empresa, competencia)
            regime = regimes[competencia]
        for aviso in avisos_da_tomada(dados_da_escrituracao(escrituracao), regime):
            pares.append((escrituracao, aviso))
    return tuple(pares)


def _vencimento_do_retido(municipio: str | None, ano: int, mes: int):
    """(data, texto, regra do dia não útil). Sem regra cadastrada, não há data a mostrar."""
    if municipio is None:
        return None, "Nota sem município de incidência: vencimento não calculado.", ""
    regra, situacao = iss_municipal._regra_do_mes(municipio, ano, mes)
    if regra is None:
        if situacao == "ausente":
            texto = f"Município {municipio} sem regra cadastrada: vencimento não parametrizado."
        else:
            texto = (
                f"Regra do município {municipio} não cobre {mes:02d}/{ano}: "
                "vencimento não parametrizado."
            )
        return None, texto, ""
    ano_venc, mes_venc = iss_municipal._mes_seguinte(ano, mes)
    vencimento = date(ano_venc, mes_venc, regra.dia_vencimento_retido)
    return vencimento, iss_municipal.data_nominal_br(vencimento), regra.regra_dia_nao_util


def iss_retido_a_recolher(empresa, ano: int, mes: int) -> IssRetidoAReceber:
    """ISS retido a recolher pelo cliente TOMADOR, por município, no mês de `dCompet` (HI-94).

    Soma o vISSQN de toda escrituração efetivada com tpRetISSQN 2, qualquer que seja a natureza
    de NATUREZAS_COM_ISS_RETIDO (T1, T5, T6 ou T7). Nota retida sem vISSQN aparece em `sem_valor`,
    nunca como zero. Vencimento: regra do município (Palmas: dia 15 do mês seguinte, RCTM Anexo
    I). Município sem regra: "não parametrizado". Tomada de MEI com retenção recebe aviso.
    """
    iss_municipal._validar_competencia(ano, mes)
    primeiro, ultimo = iss_municipal._primeiro_e_ultimo(ano, mes)
    validas, canceladas = _efetivadas(
        empresa, data_competencia__gte=primeiro, data_competencia__lte=ultimo
    )
    retidas = [
        e for e in validas if e.tp_ret_issqn == "2" and e.natureza in NATUREZAS_COM_ISS_RETIDO
    ]
    fora = [
        e for e in validas if e.tp_ret_issqn == "2" and e.natureza not in NATUREZAS_COM_ISS_RETIDO
    ]

    por_municipio: dict[str | None, list[EscrituracaoTomada]] = {}
    for escrituracao in retidas:
        por_municipio.setdefault(escrituracao.c_loc_incid, []).append(escrituracao)

    grupos = []
    for municipio in sorted(por_municipio, key=lambda m: (m is None, m or "")):
        notas = por_municipio[municipio]
        vencimento, texto, regra = _vencimento_do_retido(municipio, ano, mes)
        grupos.append(
            GrupoIssRetido(
                municipio=municipio,
                total=_soma(e.v_iss_qn for e in notas),
                notas=tuple(e for e in notas if e.v_iss_qn is not None),
                sem_valor=tuple(e for e in notas if e.v_iss_qn is None),
                vencimento=vencimento,
                vencimento_texto=texto,
                regra_dia_nao_util=regra,
            )
        )

    regimes: dict = {}
    avisos = list(_avisos_das_notas(empresa, retidas + fora, regimes))
    # MEI em regra não sofre retenção de ISS (LC 123, art. 18-A, ver FUNDAMENTO_AVISO_MEI). O valor
    # destacado ENTRA no total, porque é o que a nota diz. O aviso só pede conferência.
    for escrituracao in retidas:
        if escrituracao.natureza == NaturezaTomada.TOMADO_DE_MEI:
            avisos.append(
                (
                    escrituracao,
                    AvisoTomada(
                        "MEI_ISS_RETIDO",
                        "MEI não sofre retenção de ISS em regra — conferir. A nota traz "
                        "tpRetISSQN 2 e entra no total do ISS retido.",
                        FUNDAMENTO_AVISO_MEI,
                    ),
                )
            )
    # Cliente em Palmas, com ISS devido no local do tomador (T3): CNES e RANFS (RCTM arts.
    # 218 a 222). Informativo, sem cálculo: a aplicação a NFS-e nacional não está determinada.
    for escrituracao in validas:
        if (
            escrituracao.natureza == NaturezaTomada.TOMADO_PRESTADOR_OUTRO_MUNICIPIO
            and escrituracao.c_loc_incid == PALMAS
        ):
            avisos.append(
                (
                    escrituracao,
                    AvisoTomada(
                        "CNES_RANFS",
                        "Prestador de outro município com ISS no local do tomador em Palmas: "
                        "verificar o cadastro no CNES e o RANFS. Informativo, sem cálculo.",
                        "RCTM de Palmas, arts. 218 a 222 (cópia legisweb); consulta, item 2",
                    ),
                )
            )

    return IssRetidoAReceber(
        ano=ano,
        mes=mes,
        grupos=tuple(grupos),
        fora_do_total=tuple(fora),
        canceladas=tuple(canceladas),
        avisos=tuple(avisos),
    )


def _agrupar_por_pagamento(notas, campo: str) -> tuple[PagamentoRetido, ...]:
    grupos: dict[date, list[EscrituracaoTomada]] = {}
    for escrituracao in notas:
        if getattr(escrituracao, campo) is None:
            continue
        grupos.setdefault(escrituracao.data_pagamento, []).append(escrituracao)
    return tuple(
        PagamentoRetido(
            data_pagamento=data,
            total=_soma(getattr(e, campo) for e in grupo),
            notas=tuple(grupo),
        )
        for data, grupo in sorted(grupos.items())
    )


def retencoes_federais(empresa, ano: int, mes: int) -> RetencoesFederais:
    """Retenções federais destacadas, por tributo, com a competência de cada um (HI-95, HI-96).

    - INSS (vRetCP): notas EMITIDAS no mês (`data_emissao`).
    - IRRF (vRetIRRF) e CSRF (vRetCSLL, que já é PIS+COFINS+CSLL quando retidos): notas com
      DATA DE PAGAMENTO informada no mês, agrupadas por essa data.
    - Pendentes: IRRF ou CSRF retido, de nota com competência no mês e SEM data de pagamento.
    """
    iss_municipal._validar_competencia(ano, mes)
    primeiro, ultimo = iss_municipal._primeiro_e_ultimo(ano, mes)

    emitidas, canc_emitidas = _efetivadas(
        empresa, data_emissao__gte=primeiro, data_emissao__lte=ultimo
    )
    inss_notas = [e for e in emitidas if e.v_ret_cp is not None]

    pagas, canc_pagas = _efetivadas(
        empresa, data_pagamento__gte=primeiro, data_pagamento__lte=ultimo
    )

    competencia, canc_competencia = _efetivadas(
        empresa,
        data_competencia__gte=primeiro,
        data_competencia__lte=ultimo,
        data_pagamento__isnull=True,
    )
    pendentes = [e for e in competencia if _positivo(e.v_ret_irrf) or _positivo(e.v_ret_csll)]

    irrf = _agrupar_por_pagamento(pagas, "v_ret_irrf")
    csrf = _agrupar_por_pagamento(pagas, "v_ret_csll")

    ano_venc, mes_venc = iss_municipal._mes_seguinte(ano, mes)
    inss_venc = date(ano_venc, mes_venc, DIA_VENCIMENTO_INSS)

    canceladas_por_id = {e.pk: e for e in (*canc_emitidas, *canc_pagas, *canc_competencia)}
    notas_com_avisos = {e.pk: e for e in (*inss_notas, *pagas, *pendentes)}
    regimes: dict = {}
    return RetencoesFederais(
        ano=ano,
        mes=mes,
        inss_total=_soma(e.v_ret_cp for e in inss_notas),
        inss_notas=tuple(inss_notas),
        inss_vencimento=inss_venc,
        inss_vencimento_texto=f"{iss_municipal.data_nominal_br(inss_venc)}; {FUNDAMENTO_INSS}",
        irrf_por_pagamento=irrf,
        csrf_por_pagamento=csrf,
        irrf_total=_soma(g.total for g in irrf),
        csrf_total=_soma(g.total for g in csrf),
        pendentes_de_pagamento=tuple(pendentes),
        canceladas=tuple(canceladas_por_id.values()),
        avisos=_avisos_das_notas(empresa, list(notas_com_avisos.values()), regimes),
    )
