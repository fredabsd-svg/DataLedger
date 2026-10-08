"""Escrituração das NFS-e TOMADAS — DL-078, frente A (serviço).

Plano: docs/planos/DL-078-servicos-tomados-e-retencoes.md. Base normativa e hipóteses:
docs/projeto/consultas/2026-10-08-contador-senior-servicos-tomados.md (itens 1 a 4) e
HI-93 a HI-96 em docs/projeto/requisitos.md. Decisões que o código não explica sozinho:

- Tomada é o vínculo de TOMADOR (`VinculoDocumentoEmpresa.papel`). Nota em que a empresa é
  prestadora fica na escrituração prestada (DL-072) e NUNCA entra aqui, e a escrituração
  tomada nunca entra em receita, RBT12, pré-DAS nem no ISS próprio (critério 7).
- A natureza é SUGERIDA a partir do XML e CONFIRMADA pelo contador (HI-93). Quem sugere
  é `sugerir_natureza`; quem decide é o contador, e a sugestão nunca vira efetivação.
- Recusas (decididas aqui, registradas na trilha como recusa de entrada):
  * tpEmit 2 ou 3: emissão pelo tomador ou pelo intermediário. Fica fora do catálogo.
    O XSD mostra que tpEmit 2 não é só importação: o motivo está em cMotivoEmisTI (1 é
    importação; 2, 3 e 4 são emissão por obrigação municipal, recusa ou rejeição do
    prestador). Por isso a recusa não separa o motivo. Divergência com a consulta, item 1.
  * T1 (ISS retido pelo cliente) só com tpRetISSQN 2. Sem isso, o total do ISS a recolher
    somaria imposto que o XML diz não ter sido retido. Por isso a incompatibilidade é
    RECUSA, não aviso. A tarefa pedia "aviso forte, decida e justifique": esta é a decisão.
  * T2 e T3 (sem retenção) só com tpRetISSQN 1. Com tpRetISSQN 2 a nota teria retenção e
    ficaria fora do total de ISS a recolher, o que esconderia uma obrigação do tomador.
- T5, T6 e T7 aceitam qualquer tpRetISSQN. Se o XML diz 2 (retido pelo tomador) nessas
  naturezas, a nota NÃO entra no total de ISS a recolher (que soma só T1) e aparece em
  "fora do total — conferir" (ver `apps.fiscal.retencoes`). Nada some em silêncio.
- Os valores são COPIADOS do documento e do XML guardado no ato de efetivar. Ausência
  (vISSQN, vRetCP etc.) fica NULA, nunca zero.
- A data de pagamento é o ÚNICO campo que muda depois de efetivada (HI-96). Ela só existe
  em nota efetivada, sempre com motivo e com quem e quando informou. O banco permite a
  alteração só dessas colunas (gatilho da migração 0008).

Concorrência e atomicidade: cada serviço que escreve é `transaction.atomic()` e trava o
VÍNCULO com `select_for_update` antes de decidir. A restrição parcial
`escrituracao_tomada_ativa_unica_por_vinculo` é a segunda defesa. A trilha (`registrar`)
entra na MESMA transação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal.escrituracao import (
    SITUACAO_A_ESCRITURAR,
    SITUACAO_CANCELADA,
    SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA,
    SITUACAO_EFETIVADA,
    SITUACAO_RASCUNHO,
    EntradaInvalidaEscrituracao,
    EscrituracaoErro,
)
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoTomada,
    EstadoEscrituracao,
    NaturezaTomada,
    PapelDocumento,
    TipoDocumentoParticipante,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.services import documentos_do_escritorio, situacao_do_documento
from apps.fiscal.tomadas_campos import CamposTomada, campos_tomada_do_documento

# tpEmit (TSEmitenteDPS): 2 tomador e 3 intermediário emitem fora do catálogo desta etapa.
TP_EMIT_FORA_DO_CATALOGO = frozenset({"2", "3"})

# tpRetPisCofins (TSTipoRetPISCofins): 1 e 3 a 9 indicam retenção; 0 e 2 não (consulta, A2).
TP_RET_PIS_COFINS_COM_RETENCAO = frozenset({"1", "3", "4", "5", "6", "7", "8", "9"})
TP_RET_PIS_COFINS_SEM_RETENCAO = frozenset({"0", "2"})

# Valor "abaixo do mínimo de dispensa" (consulta, A5): até R$ 10,00 (Lei 10.833, art. 31, § 3º,
# red. Lei 13.137/2015). O limite de R$ 5.000 foi revogado e não se usa aqui.
LIMITE_MINIMO_DISPENSA = Decimal("10.00")
# Tolerância da conta de vLiq (P&R NFS-e 13.2, consulta A1). Acima disso, o aviso sai.
TOLERANCIA_LIQUIDO = Decimal("0.01")

# Município de Palmas (IBGE). Só para o aviso de CNES/RANFS, RCTM arts. 218 a 222.
PALMAS = "1721000"

MOTIVO_MAXIMO = 500  # coluna `motivo_estorno` e `motivo_pagamento` (models.py)

_NOME_RESTRICAO_UNICA = "escrituracao_tomada_ativa_unica_por_vinculo"

MENSAGEM_NATUREZA_VAZIA = "Escolha a natureza da operação."
# Não ecoa o valor enviado: ele vem do cliente e não precisa voltar na mensagem.
MENSAGEM_NATUREZA_FORA_DO_CATALOGO = (
    "Natureza de operação desconhecida: o valor enviado não é uma das naturezas "
    "do catálogo de notas tomadas. Escolha uma das opções da lista."
)
MENSAGEM_TP_EMIT_FORA = (
    "Esta NFS-e foi emitida pelo tomador ou pelo intermediário (tpEmit 2 ou 3). Essa emissão "
    "fica fora do catálogo desta etapa: a importação de serviço (T4) ainda não é tratada, e o "
    "motivo da emissão pelo tomador está em cMotivoEmisTI. Nada foi gravado."
)


# ---------------------------------------------------------------------------
# Avisos (consulta, item 3: A1 a A8, e a conferência de vPis/vCofins)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AvisoTomada:
    """Aviso de conferência. Nunca bloqueia. `fundamento` cita a fonte do aviso."""

    codigo: str
    texto: str
    fundamento: str


@dataclass(frozen=True)
class DadosTomada:
    """Os campos que os avisos leem. Vêm do XML (sugestão) ou da escrituração (relatórios).

    Mesmos nomes do XSD em português de negócio. Ausência é `None`, e os avisos tratam
    `None` como "não destacado", nunca como zero, salvo onde a fórmula do XSD diz outra coisa
    (A1, com a nota explicando).
    """

    prestador_tipo_documento: str
    tp_ret_issqn: str | None
    op_simp_nac: str | None
    reg_ap_trib_sn: str | None
    valor_servico: Decimal | None
    valor_liquido: Decimal | None
    v_desc_incond: Decimal | None
    v_desc_cond: Decimal | None
    v_iss_qn: Decimal | None
    v_ret_cp: Decimal | None
    v_ret_irrf: Decimal | None
    v_ret_csll: Decimal | None
    tp_ret_pis_cofins: str | None
    v_pis: Decimal | None
    v_cofins: Decimal | None


def dados_do_xml(documento: DocumentoFiscal, campos: CamposTomada) -> DadosTomada:
    return DadosTomada(
        prestador_tipo_documento=documento.prestador_tipo_documento,
        tp_ret_issqn=campos.tp_ret_issqn,
        op_simp_nac=campos.op_simp_nac,
        reg_ap_trib_sn=campos.reg_ap_trib_sn,
        valor_servico=campos.v_serv,
        valor_liquido=campos.v_liq,
        v_desc_incond=campos.v_desc_incond,
        v_desc_cond=campos.v_desc_cond,
        v_iss_qn=campos.v_iss_qn,
        v_ret_cp=campos.v_ret_cp,
        v_ret_irrf=campos.v_ret_irrf,
        v_ret_csll=campos.v_ret_csll,
        tp_ret_pis_cofins=campos.tp_ret_pis_cofins,
        v_pis=campos.v_pis,
        v_cofins=campos.v_cofins,
    )


def dados_da_escrituracao(escrituracao: EscrituracaoTomada) -> DadosTomada:
    return DadosTomada(
        prestador_tipo_documento=escrituracao.prestador_tipo_documento,
        tp_ret_issqn=escrituracao.tp_ret_issqn,
        op_simp_nac=escrituracao.op_simp_nac,
        reg_ap_trib_sn=escrituracao.reg_ap_trib_sn,
        valor_servico=escrituracao.valor_servico,
        valor_liquido=escrituracao.valor_liquido,
        v_desc_incond=escrituracao.v_desc_incond,
        v_desc_cond=escrituracao.v_desc_cond,
        v_iss_qn=escrituracao.v_iss_qn,
        v_ret_cp=escrituracao.v_ret_cp,
        v_ret_irrf=escrituracao.v_ret_irrf,
        v_ret_csll=escrituracao.v_ret_csll,
        tp_ret_pis_cofins=escrituracao.tp_ret_pis_cofins,
        v_pis=escrituracao.v_pis,
        v_cofins=escrituracao.v_cofins,
    )


def regime_em(empresa, data: date) -> str | None:
    """Regime tributário da empresa na data, pelo histórico de vigência (AGENTS.md §10).

    O histórico não se corrige por edição: cada período é um registro. Sem período que
    cubra a data, devolve None, e o aviso que depende do regime não dispara.
    """
    historico = (
        HistoricoRegimeTributario.objects.filter(empresa=empresa, vigencia_inicio__lte=data)
        .filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=data))
        .order_by("-vigencia_inicio", "-id")
        .first()
    )
    return historico.regime if historico is not None else None


def _positivo(valor: Decimal | None) -> bool:
    return valor is not None and valor > 0


def avisos_da_tomada(dados: DadosTomada, regime_tomador: str | None) -> tuple[AvisoTomada, ...]:
    """Avisos A1 a A8 e a conferência de PIS/COFINS, da consulta de 08/10/2026, item 3.

    Todos são AVISO: nenhum bloqueia. `regime_tomador` é o regime da empresa TOMADORA na
    competência (só A4 usa). Ausência de campo não dispara aviso que exija o campo, salvo A8,
    que é justamente o aviso de ausência.
    """
    avisos: list[AvisoTomada] = []
    csll = dados.v_ret_csll
    irrf = dados.v_ret_irrf
    cp = dados.v_ret_cp
    tp_pc = dados.tp_ret_pis_cofins

    # A1 — vLiq não fecha com a fórmula do P&R 13.2: vLiq = vServ − vDescIncond − vDescCond −
    # vTotalRet, com vTotalRet = vRetCP + vRetIRRF + vRetCSLL + vISSQN (só se retido). Termo
    # opcional ausente conta como zero: é a própria fórmula do XSD (ver `iss_nota`).
    if dados.valor_servico is not None and dados.valor_liquido is not None:
        iss_retido = dados.v_iss_qn if dados.tp_ret_issqn == "2" else None
        total_retido = sum(
            (
                valor if valor is not None else Decimal("0")
                for valor in (cp, irrf, csll, iss_retido)
            ),
            Decimal("0"),
        )
        desconto = sum(
            (
                valor if valor is not None else Decimal("0")
                for valor in (dados.v_desc_incond, dados.v_desc_cond)
            ),
            Decimal("0"),
        )
        esperado = dados.valor_servico - desconto - total_retido
        if abs(dados.valor_liquido - esperado) > TOLERANCIA_LIQUIDO:
            avisos.append(
                AvisoTomada(
                    "A1",
                    f"O valor líquido ({dados.valor_liquido}) não fecha com a fórmula do XML "
                    f"({esperado}): serviço menos descontos menos valores retidos. Termos "
                    "ausentes contam como zero. Confira a nota.",
                    "P&R NFS-e v1.1, item 13.2 (tolerância de R$ 0,01)",
                )
            )

    # A2 — tpRetPisCofins e vRetCSLL devem dizer a mesma coisa (P&R 13.1, NT 007/2026).
    if tp_pc in TP_RET_PIS_COFINS_COM_RETENCAO and not _positivo(csll):
        avisos.append(
            AvisoTomada(
                "A2",
                f"tpRetPisCofins {tp_pc} indica retenção, mas vRetCSLL está ausente ou zerado. "
                "Desde a NT 007/2026 os retidos vêm somados em vRetCSLL.",
                "P&R NFS-e v1.1, item 13.1",
            )
        )
    if tp_pc in TP_RET_PIS_COFINS_SEM_RETENCAO and _positivo(csll):
        avisos.append(
            AvisoTomada(
                "A2",
                f"tpRetPisCofins {tp_pc} diz que não há retenção de PIS/COFINS/CSLL, mas vRetCSLL "
                f"traz {csll}. Confira a nota.",
                "P&R NFS-e v1.1, item 13.1",
            )
        )

    # A3 — prestador do Simples (MEI ou ME/EPP) com CSRF ou IRRF retidos: retenção provavelmente
    # indevida. Exceção: regApTribSN 3 (federais por fora do SN), inferência da consulta.
    if (
        dados.op_simp_nac in ("2", "3")
        and dados.reg_ap_trib_sn != "3"
        and (_positivo(csll) or _positivo(irrf))
    ):
        avisos.append(
            AvisoTomada(
                "A3",
                "Prestador optante pelo Simples Nacional com CSRF ou IRRF retidos: retenção "
                "provavelmente indevida. Confira se o prestador estava fora do SN nas federais.",
                "Lei 10.833, art. 32, III; IN RFB 765/2007, art. 1º; IN SRF 459, art. 3º, II "
                "(cópias); consulta, A3",
            )
        )

    # A4 — tomador optante do Simples não retém CSRF (Lei 10.833, art. 30, § 2º).
    if regime_tomador == RegimeTributario.SIMPLES_NACIONAL and _positivo(csll):
        avisos.append(
            AvisoTomada(
                "A4",
                "A empresa tomadora está no Simples Nacional na competência, e a nota traz CSRF "
                "retida. O optante do Simples não retém CSRF.",
                "Lei 10.833, art. 30, § 2º (lido)",
            )
        )

    # A5 — valor de retenção positivo e até o mínimo de dispensa.
    for nome, valor in (("vRetCSLL", csll), ("vRetIRRF", irrf)):
        if _positivo(valor) and valor <= LIMITE_MINIMO_DISPENSA:
            avisos.append(
                AvisoTomada(
                    "A5",
                    f"{nome} de {valor} está abaixo do mínimo de dispensa de R$ "
                    f"{LIMITE_MINIMO_DISPENSA}. Confira se a retenção deveria existir.",
                    "Lei 10.833, art. 31, § 3º, red. Lei 13.137/2015 (lido); Lei 9.430, art. 67",
                )
            )

    # A6 — INSS sobre optante do Simples só cabe no Anexo IV (IN RFB 2.110, arts. 166-167).
    if dados.op_simp_nac == "3" and _positivo(cp):
        avisos.append(
            AvisoTomada(
                "A6",
                "Prestador ME/EPP do Simples com INSS retido. A retenção de 11% sobre optante só "
                "se aplica ao Anexo IV. Confira o anexo do prestador.",
                "IN RFB 2.110, arts. 166-167 (cópia); consulta, A6",
            )
        )

    # A7 — informativo: INSS retido só existe em cessão de mão de obra ou empreitada.
    if _positivo(cp):
        avisos.append(
            AvisoTomada(
                "A7",
                "INSS retido (vRetCP). Só cabe em cessão de mão de obra ou empreitada; não se "
                "aplica a empreitada total nem a transporte de cargas. Informativo, sem cálculo.",
                "Lei 8.212, art. 31, §§ 3º a 4º (lido); IN RFB 2.110, arts. 111-114 (cópia)",
            )
        )

    # A8 — prestador pessoa física ou MEI sem nenhum campo federal: retenções, se houver, foram
    # calculadas fora da nota. Ausência não é "sem retenção".
    sem_federais = all(
        valor is None for valor in (cp, irrf, csll, tp_pc, dados.v_pis, dados.v_cofins)
    )
    if (
        dados.prestador_tipo_documento == TipoDocumentoParticipante.CPF or dados.op_simp_nac == "2"
    ) and sem_federais:
        avisos.append(
            AvisoTomada(
                "A8",
                "Prestador pessoa física ou MEI sem campos federais na nota. Retenções, se "
                "houver, foram calculadas fora da nota.",
                "P&R NFS-e v1.1, item 11.1 (E0675 e E0676)",
            )
        )

    # vPis e vCofins são débito próprio do prestador. Com tpRetPisCofins de retenção, o XML
    # fica ambíguo: nunca somar os dois.
    if tp_pc in TP_RET_PIS_COFINS_COM_RETENCAO and (
        dados.v_pis is not None or dados.v_cofins is not None
    ):
        avisos.append(
            AvisoTomada(
                "AMBIGUO_PIS_COFINS",
                "vPis ou vCofins preenchidos junto com tpRetPisCofins de retenção. Pode ser "
                "débito próprio do prestador. Ambíguo, conferir: não somado.",
                "P&R NFS-e v1.1, itens 13.1 e 13.2",
            )
        )
    return tuple(avisos)


# ---------------------------------------------------------------------------
# Sugestão e recusas
# ---------------------------------------------------------------------------


def _recusa_do_documento(documento: DocumentoFiscal, campos: CamposTomada) -> str | None:
    """Motivo pelo qual a nota não entra em escrituração tomada, ou None.

    Vale para rascunho e para efetivação. Sem emitente conhecido, não há como saber se a nota
    é tomada de fato, então é recusa, e não sugestão.
    """
    if campos.erro_leitura:
        return (
            "O XML guardado desta nota não pode ser lido, então ela não entra na escrituração "
            "tomada. Nada foi gravado."
        )
    if campos.tp_emit is None:
        return "O XML guardado desta nota não informa tpEmit. Nada foi gravado."
    if campos.tp_emit in TP_EMIT_FORA_DO_CATALOGO:
        return MENSAGEM_TP_EMIT_FORA
    return None


def sugerir_natureza(
    documento: DocumentoFiscal, campos: CamposTomada | None = None
) -> NaturezaTomada | None:
    """Natureza SUGERIDA para a nota tomada (HI-93), ou None quando o XML não permite sugerir.

    Ordem, e a primeira regra que casa vence (consulta, item 1):
    1. tpEmit 2 ou 3 → None (fora do catálogo; a recusa diz o motivo).
    2. tpRetISSQN 2 → T1, ISS retido pelo cliente tomador.
    3. opSimpNac 2 → T5, MEI.
    4. opSimpNac 3 → T6, ME/EPP do Simples.
    5. prestador com CPF → T7, pessoa física.
    6. tpRetISSQN 1 com cLocIncid e cLocPrestacao diferentes → T3, prestador de outro município.
    7. tpRetISSQN 1 → T2, sem retenção.
    8. Qualquer outro caso (tpRetISSQN ausente ou inválido) → None.
    """
    campos = campos if campos is not None else campos_tomada_do_documento(documento)
    if campos.tp_emit in TP_EMIT_FORA_DO_CATALOGO or campos.tp_emit is None:
        return None
    if campos.tp_ret_issqn == "2":
        return NaturezaTomada.TOMADO_ISS_RETIDO_PELO_CLIENTE
    if campos.op_simp_nac == "2":
        return NaturezaTomada.TOMADO_DE_MEI
    if campos.op_simp_nac == "3":
        return NaturezaTomada.TOMADO_DE_SIMPLES
    if documento.prestador_tipo_documento == TipoDocumentoParticipante.CPF:
        return NaturezaTomada.TOMADO_DE_PESSOA_FISICA
    if campos.tp_ret_issqn == "1":
        if (
            campos.c_loc_incid is not None
            and campos.c_loc_prestacao is not None
            and campos.c_loc_incid != campos.c_loc_prestacao
        ):
            return NaturezaTomada.TOMADO_PRESTADOR_OUTRO_MUNICIPIO
        return NaturezaTomada.TOMADO_SEM_RETENCAO
    return None


def _recusa_de_natureza(natureza: str, campos: CamposTomada) -> str | None:
    """Natureza incompatível com o XML, nomeada, ou None. Só vale para efetivar (ver módulo).

    T1 exige tpRetISSQN 2; T2 e T3 exigem tpRetISSQN 1. As outras naturezas não têm regra de
    compatibilidade por tpRetISSQN (T5, T6 e T7 podem vir com retenção; ver `retencoes`).
    """
    tp = campos.tp_ret_issqn or "ausente"
    if natureza == NaturezaTomada.TOMADO_ISS_RETIDO_PELO_CLIENTE:
        if campos.tp_ret_issqn != "2":
            return (
                "A natureza 'ISS retido pelo cliente' (T1) exige tpRetISSQN 2 no XML, e esta "
                f"nota traz {tp}. Escolha a natureza compatível com o documento. Nada foi gravado."
            )
    elif natureza in (
        NaturezaTomada.TOMADO_SEM_RETENCAO,
        NaturezaTomada.TOMADO_PRESTADOR_OUTRO_MUNICIPIO,
    ):
        if campos.tp_ret_issqn == "2":
            return (
                "A natureza sem retenção contradiz o XML: tpRetISSQN 2 é ISS retido pelo tomador. "
                "Use 'ISS retido pelo cliente' (T1). Nada foi gravado."
            )
        if campos.tp_ret_issqn != "1":
            return (
                f"A natureza sem retenção exige tpRetISSQN 1 no XML, e esta nota traz {tp}. "
                "Nada foi gravado."
            )
    return None


# ---------------------------------------------------------------------------
# Leitura para a tela e a API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotaTomada:
    vinculo: VinculoDocumentoEmpresa
    documento: DocumentoFiscal
    situacao: str
    escrituracao: EscrituracaoTomada | None
    # None quando o XML não permite sugerir: nada vem pré-selecionado.
    natureza_sugerida: NaturezaTomada | None
    data_emissao: date | None
    # Motivo pelo qual esta nota NÃO pode ser efetivada, ou None.
    bloqueio: str | None
    avisos: tuple[AvisoTomada, ...]


def _cancelada(documento: DocumentoFiscal) -> bool:
    anotada = getattr(documento, "cancelada", None)
    if anotada is not None:
        return bool(anotada)
    return situacao_do_documento(documento) == "cancelada"


def _situacao(documento: DocumentoFiscal, escrituracao: EscrituracaoTomada | None) -> str:
    cancelada = _cancelada(documento)
    efetivada = escrituracao is not None and escrituracao.estado == EstadoEscrituracao.EFETIVADA
    if cancelada and efetivada:
        return SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA
    if cancelada:
        return SITUACAO_CANCELADA
    if escrituracao is None:
        return SITUACAO_A_ESCRITURAR
    if efetivada:
        return SITUACAO_EFETIVADA
    return SITUACAO_RASCUNHO


def _montar_nota(
    vinculo: VinculoDocumentoEmpresa,
    documento: DocumentoFiscal,
    escrituracao: EscrituracaoTomada | None,
    regimes: dict,
) -> NotaTomada:
    campos = campos_tomada_do_documento(documento)
    dados = dados_do_xml(documento, campos)
    # O regime do tomador só é consultado se A4 pode disparar (CSRF positiva), e fica em cache
    # por competência, para a lista do mês não consultar o histórico por nota.
    regime = None
    if _positivo(dados.v_ret_csll) and documento.d_competencia is not None:
        chave = documento.d_competencia
        if chave not in regimes:
            regimes[chave] = regime_em(vinculo.empresa, chave)
        regime = regimes[chave]
    return NotaTomada(
        vinculo=vinculo,
        documento=documento,
        situacao=_situacao(documento, escrituracao),
        escrituracao=escrituracao,
        natureza_sugerida=sugerir_natureza(documento, campos),
        data_emissao=campos.data_emissao,
        bloqueio=_recusa_do_documento(documento, campos),
        avisos=avisos_da_tomada(dados, regime),
    )


def notas_tomadas(empresa, ano: int, mes: int) -> list[NotaTomada]:
    """NFS-e em que `empresa` é TOMADORA e cuja `dCompet` cai em `ano/mes`.

    A consulta parte do escritório da empresa (AGENTS.md §11): nota de outro escritório nunca
    aparece. Vínculo de PRESTADOR não entra aqui; isso é a escrituração prestada (DL-072).
    """
    documentos = {
        documento.pk: documento
        for documento in documentos_do_escritorio(
            empresa.escritorio, empresa=empresa, competencia=(ano, mes)
        )
    }
    vinculos = list(
        VinculoDocumentoEmpresa.objects.filter(
            empresa=empresa,
            papel=PapelDocumento.TOMADOR,
            documento_id__in=list(documentos.keys()),
        )
        .select_related("empresa")
        .order_by("documento__dh_emissao", "id")
    )
    ativas = {
        escrituracao.vinculo_id: escrituracao
        for escrituracao in EscrituracaoTomada.objects.filter(
            vinculo_id__in=[v.pk for v in vinculos],
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
    }
    regimes: dict = {}
    return [
        _montar_nota(vinculo, documentos[vinculo.documento_id], ativas.get(vinculo.pk), regimes)
        for vinculo in vinculos
    ]


def nota_tomada_do_vinculo(empresa, vinculo: VinculoDocumentoEmpresa) -> NotaTomada | None:
    """A mesma linha que `notas_tomadas` daria para ESTE vínculo. None para vínculo prestado."""
    if vinculo.empresa_id != empresa.pk:
        raise ValueError("O vínculo não pertence à empresa informada.")
    if vinculo.papel != PapelDocumento.TOMADOR:
        return None
    escrituracao = EscrituracaoTomada.objects.filter(
        vinculo=vinculo,
        estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
    ).first()
    return _montar_nota(vinculo, vinculo.documento, escrituracao, {})


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


def _snapshot(escrituracao: EscrituracaoTomada | None) -> dict | None:
    """Estado da escrituração para o `antes`/`depois` da trilha. Só dados do próprio ato."""
    if escrituracao is None:
        return None

    def iso(valor):
        return valor.isoformat() if valor is not None else None

    def texto(valor: Decimal | None):
        return str(valor) if valor is not None else None

    return {
        "estado": escrituracao.estado,
        "natureza": escrituracao.natureza,
        "data_emissao": iso(escrituracao.data_emissao),
        "data_competencia": iso(escrituracao.data_competencia),
        "valor_servico": texto(escrituracao.valor_servico),
        "valor_liquido": texto(escrituracao.valor_liquido),
        "tp_ret_issqn": escrituracao.tp_ret_issqn,
        "v_iss_qn": texto(escrituracao.v_iss_qn),
        "efetivada_em": iso(escrituracao.efetivada_em),
        "efetivada_por": escrituracao.efetivada_por_id,
        "estornada_em": iso(escrituracao.estornada_em),
        "estornada_por": escrituracao.estornada_por_id,
        "motivo_estorno": escrituracao.motivo_estorno,
        "data_pagamento": iso(escrituracao.data_pagamento),
        "motivo_pagamento": escrituracao.motivo_pagamento,
    }


def _validar_natureza(natureza: str) -> None:
    if not natureza:
        raise EntradaInvalidaEscrituracao(MENSAGEM_NATUREZA_VAZIA)
    if natureza not in NaturezaTomada.values:
        raise EntradaInvalidaEscrituracao(MENSAGEM_NATUREZA_FORA_DO_CATALOGO)


def _travar_vinculo_tomador(vinculo: VinculoDocumentoEmpresa) -> VinculoDocumentoEmpresa:
    """Trava o vínculo e recusa o que não pode ser escriturado aqui. Chamado dentro de atomic().

    `of=("self",)` trava só a linha do vínculo, não as linhas que o `select_related` traz junto.
    """
    travado = (
        VinculoDocumentoEmpresa.objects.select_for_update(of=("self",))
        .select_related("documento", "empresa__escritorio")
        .get(pk=vinculo.pk)
    )
    if travado.papel != PapelDocumento.TOMADOR:
        raise EntradaInvalidaEscrituracao(
            "Só é escriturada aqui a nota em que a empresa é tomadora. "
            "Nota prestada é escriturada na escrituração de prestadas."
        )
    if situacao_do_documento(travado.documento) == "cancelada":
        raise EscrituracaoErro("Nota cancelada não pode ser escriturada.")
    return travado


def _ativa_do_vinculo_travado(vinculo: VinculoDocumentoEmpresa) -> EscrituracaoTomada | None:
    return (
        EscrituracaoTomada.objects.select_for_update(of=("self",))
        .filter(
            vinculo=vinculo,
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
        .first()
    )


def _erro_de_unicidade(exc: IntegrityError) -> bool:
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diag, "constraint_name", None) == _NOME_RESTRICAO_UNICA


def _inserir_escrituracao_tomada(escrituracao: EscrituracaoTomada) -> None:
    """INSERT traduzindo a corrida em erro de negócio (409), e não em 500.

    A trava de `_travar_vinculo_tomador` deveria impedir duas linhas ativas para o vínculo.
    Se uma corrida escapar, a restrição parcial do banco recusa o segundo INSERT. O SAVEPOINT
    isola só este INSERT, e a transação de quem chamou segue viva.
    """
    try:
        with transaction.atomic():
            escrituracao.save()
    except IntegrityError as exc:
        if _erro_de_unicidade(exc):
            raise EscrituracaoErro(
                "Esta nota acabou de ser escriturada por outra ação. Atualize a lista."
            ) from exc
        raise


def _valores_copiados(documento: DocumentoFiscal, campos: CamposTomada) -> dict:
    """Valores copiados NA EFETIVAÇÃO. Nada é inventado: sem a data escrita no XML, não há ato."""
    if campos.data_emissao is None:
        raise EscrituracaoErro(
            "O XML guardado desta nota não informa a data de emissão. "
            "A nota não pode ser escriturada."
        )
    return {
        "data_emissao": campos.data_emissao,
        "data_competencia": documento.d_competencia,
        "prestador_tipo_documento": documento.prestador_tipo_documento,
        "tp_emit": campos.tp_emit,
        "tp_ret_issqn": documento.tp_ret_issqn,
        "c_loc_incid": campos.c_loc_incid,
        "op_simp_nac": campos.op_simp_nac,
        "reg_ap_trib_sn": campos.reg_ap_trib_sn,
        "valor_servico": documento.v_serv,
        "valor_liquido": documento.v_liq,
        "v_desc_incond": campos.v_desc_incond,
        "v_desc_cond": campos.v_desc_cond,
        "v_iss_qn": campos.v_iss_qn,
        "v_ret_cp": campos.v_ret_cp,
        "v_ret_irrf": campos.v_ret_irrf,
        "v_ret_csll": campos.v_ret_csll,
        "tp_ret_pis_cofins": campos.tp_ret_pis_cofins,
        "v_pis": campos.v_pis,
        "v_cofins": campos.v_cofins,
    }


@transaction.atomic
def salvar_rascunho(
    vinculo: VinculoDocumentoEmpresa, natureza: str, usuario, request=None
) -> EscrituracaoTomada:
    """Grava (ou troca) a natureza ainda NÃO confirmada — estado `rascunho`.

    Rascunho aceita qualquer natureza do catálogo: a compatibilidade com o XML só é cobrada
    na efetivação. A recusa de tpEmit 2 ou 3 vale já aqui, porque essa nota não é tomada do
    catálogo desta etapa.
    """
    _validar_natureza(natureza)
    travado = _travar_vinculo_tomador(vinculo)
    recusa = _recusa_do_documento(travado.documento, campos_tomada_do_documento(travado.documento))
    if recusa is not None:
        raise EntradaInvalidaEscrituracao(recusa)
    ativa = _ativa_do_vinculo_travado(travado)
    if ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoErro(
            "Esta nota já está efetivada. Estorne a escrituração para alterar a natureza."
        )

    antes = _snapshot(ativa)
    if ativa is None:
        escrituracao = EscrituracaoTomada(
            vinculo=travado,
            empresa=travado.empresa,
            natureza=natureza,
            estado=EstadoEscrituracao.RASCUNHO,
            criado_por=usuario,
        )
        _inserir_escrituracao_tomada(escrituracao)
    else:
        atualizadas = EscrituracaoTomada.objects.filter(
            pk=ativa.pk, estado=EstadoEscrituracao.RASCUNHO
        ).update(natureza=natureza)
        if atualizadas != 1:
            raise EscrituracaoErro("A escrituração mudou enquanto era alterada. Atualize a lista.")
        escrituracao = EscrituracaoTomada.objects.get(pk=ativa.pk)

    registrar(
        acao="escrituracao_tomada.rascunho_salvo",
        usuario=usuario,
        escritorio=travado.empresa.escritorio,
        objeto=escrituracao,
        request=request,
        detalhes={
            "vinculo_id": travado.pk,
            "antes": antes,
            "depois": _snapshot(escrituracao),
        },
    )
    return escrituracao


@transaction.atomic
def efetivar_escrituracao_tomada(
    vinculo: VinculoDocumentoEmpresa, natureza: str, usuario, request=None
) -> EscrituracaoTomada:
    """Efetiva a nota tomada com a natureza confirmada pelo contador.

    IDEMPOTÊNCIA (mesma decisão da DL-072): se já está efetivada com a MESMA natureza, devolve a
    existente com `criada_agora = False`, sem gravar nada e sem nova entrada na trilha. Se está
    efetivada com OUTRA natureza, recusa com 409: a troca é estorno e nova efetivação.

    Efetivar NÃO altera receita, confirmação de mês nem RBT12: a tomada não é receita. Por isso
    este serviço não chama `marcar_a_retificar`, diferente da escrituração prestada.
    """
    _validar_natureza(natureza)
    travado = _travar_vinculo_tomador(vinculo)
    ativa = _ativa_do_vinculo_travado(travado)

    if ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
        if ativa.natureza == natureza:
            ativa.criada_agora = False
            return ativa
        raise EscrituracaoErro(
            "Esta nota já está escriturada como "
            f"'{ativa.get_natureza_display()}'. Estorne a escrituração antes de "
            "efetivar outra natureza."
        )

    documento = travado.documento
    campos = campos_tomada_do_documento(documento)
    recusa = _recusa_do_documento(documento, campos)
    if recusa is not None:
        raise EntradaInvalidaEscrituracao(recusa)
    recusa = _recusa_de_natureza(natureza, campos)
    if recusa is not None:
        raise EntradaInvalidaEscrituracao(recusa)
    valores = _valores_copiados(documento, campos)
    antes = _snapshot(ativa)
    agora = timezone.now()

    if ativa is None:
        escrituracao = EscrituracaoTomada(
            vinculo=travado,
            empresa=travado.empresa,
            natureza=natureza,
            estado=EstadoEscrituracao.EFETIVADA,
            efetivada_em=agora,
            efetivada_por=usuario,
            criado_por=usuario,
            **valores,
        )
        _inserir_escrituracao_tomada(escrituracao)
    else:
        atualizadas = EscrituracaoTomada.objects.filter(
            pk=ativa.pk, estado=EstadoEscrituracao.RASCUNHO
        ).update(
            natureza=natureza,
            estado=EstadoEscrituracao.EFETIVADA,
            efetivada_em=agora,
            efetivada_por=usuario,
            **valores,
        )
        if atualizadas != 1:
            raise EscrituracaoErro("A escrituração mudou enquanto era efetivada. Atualize a lista.")
        escrituracao = EscrituracaoTomada.objects.get(pk=ativa.pk)

    escrituracao.criada_agora = True
    registrar(
        acao="escrituracao_tomada.efetivada",
        usuario=usuario,
        escritorio=travado.empresa.escritorio,
        objeto=escrituracao,
        request=request,
        detalhes={
            "vinculo_id": travado.pk,
            "natureza_sugerida": sugerir_natureza(documento, campos),
            "antes": antes,
            "depois": _snapshot(escrituracao),
        },
    )
    return escrituracao


def _motivo_limpo(motivo: str, rotulo: str) -> str:
    limpo = (motivo or "").strip()
    if not limpo:
        raise EntradaInvalidaEscrituracao(f"Informe o {rotulo}.")
    if len(limpo) > MOTIVO_MAXIMO:
        raise EntradaInvalidaEscrituracao(f"O {rotulo} tem no máximo {MOTIVO_MAXIMO} caracteres.")
    return limpo


@transaction.atomic
def estornar_escrituracao_tomada(
    escrituracao: EscrituracaoTomada, motivo: str, usuario, request=None
) -> EscrituracaoTomada:
    """Estorna uma escrituração de tomada efetivada, com motivo obrigatório.

    A linha não é apagada: o estorno é o registro da correção, e a trilha guarda o antes e o
    depois. A nota volta a "a escriturar", porque a linha deixa de ser ativa.
    """
    motivo_limpo = _motivo_limpo(motivo, "motivo do estorno")
    travada = (
        EscrituracaoTomada.objects.select_for_update(of=("self",))
        .select_related("empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoErro(
            "Só escrituração efetivada pode ser estornada; esta está "
            f"'{travada.get_estado_display()}'."
        )

    antes = _snapshot(travada)
    atualizadas = EscrituracaoTomada.objects.filter(
        pk=travada.pk, estado=EstadoEscrituracao.EFETIVADA
    ).update(
        estado=EstadoEscrituracao.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario,
        motivo_estorno=motivo_limpo,
    )
    if atualizadas != 1:
        raise EscrituracaoErro("A escrituração mudou enquanto era estornada. Atualize a lista.")
    travada.refresh_from_db()

    registrar(
        acao="escrituracao_tomada.estornada",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "antes": antes,
            "depois": _snapshot(travada),
        },
    )
    return travada


@transaction.atomic
def informar_data_pagamento(
    escrituracao: EscrituracaoTomada,
    data_pagamento: date,
    motivo: str,
    usuario,
    request=None,
) -> EscrituracaoTomada:
    """Informa (ou corrige) a data em que o valor foi pago ou creditado (HI-96).

    Só nota EFETIVADA recebe data de pagamento, porque é a única com retenção no total. O motivo
    é obrigatório em toda informação ou correção, e a trilha guarda o antes e o depois. Repetir a
    mesma data é no-op, como a repetição de efetivação: não é fato novo.
    """
    # `type(...) is date` e não `isinstance`: datetime é subclasse de date, e um instante com
    # hora não é o dia de pagamento que a retenção agrupa.
    if type(data_pagamento) is not date:
        raise EntradaInvalidaEscrituracao("Informe a data de pagamento no formato AAAA-MM-DD.")
    motivo_limpo = _motivo_limpo(motivo, "motivo da data de pagamento")
    travada = (
        EscrituracaoTomada.objects.select_for_update(of=("self",))
        .select_related("empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoErro(
            "A data de pagamento só é informada em escrituração efetivada; esta está "
            f"'{travada.get_estado_display()}'."
        )
    if travada.data_pagamento == data_pagamento:
        travada.criada_agora = False
        return travada

    antes = _snapshot(travada)
    atualizadas = EscrituracaoTomada.objects.filter(
        pk=travada.pk, estado=EstadoEscrituracao.EFETIVADA
    ).update(
        data_pagamento=data_pagamento,
        pagamento_informado_em=timezone.now(),
        pagamento_informado_por=usuario,
        motivo_pagamento=motivo_limpo,
    )
    if atualizadas != 1:
        raise EscrituracaoErro(
            "A escrituração mudou enquanto a data era informada. Atualize a lista."
        )
    travada.refresh_from_db()
    travada.criada_agora = True

    registrar(
        acao="escrituracao_tomada.data_pagamento_informada",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "antes": antes,
            "depois": _snapshot(travada),
        },
    )
    return travada
