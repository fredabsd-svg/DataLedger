"""Escrituração das NFS-e prestadas — DL-072, frente A (domínio).

Contrato: docs/planos/DL-072-escrituracao-das-nfse-prestadas.md (critérios
1 a 11 desta frente). Decisões que o código não explica sozinho:

- A escrituração é por VÍNCULO de PRESTADOR (`VinculoDocumentoEmpresa.papel`).
  Nota em que a empresa é tomadora não entra aqui (plano, "fica fora").
- O mês da escrituração é o de `dCompet` (HI-57). A DATA de emissão é o dia
  ESCRITO no documento: os 10 primeiros caracteres do `dhEmi` lido do XML
  guardado, no fuso do emitente (HI-72). Não é a conversão para Brasília, que
  mudaria o dia de uma nota emitida à noite em outro fuso. Essa data só serve
  ao AVISO de competência diferente da emissão e à coluna "data de emissão".
- A natureza é SUGERIDA a partir do XML e CONFIRMADA pelo contador. A sugestão
  nunca vira efetivação sozinha. Ela distingue retido, exportação e ISS
  imune/isento/reduzido; não-incidência não gera sugestão (None); e nunca
  presume "outro município" nem "fora da lista da LC 116" (HI-67).
- Nenhum serviço aqui calcula alíquota, base ou imposto. Os valores são
  copiados do documento no ato de efetivar (plano, item 4).
- Situação "cancelada" é a de `apps.fiscal.services.situacao_do_documento`,
  a fonte única. Este módulo não recalcula cancelamento por conta própria.

Concorrência e atomicidade: cada serviço que escreve é `transaction.atomic()`
e trava o VÍNCULO com `select_for_update` antes de decidir. A trava é a
primeira defesa; a restrição parcial `escrituracao_ativa_unica_por_vinculo`
do banco é a segunda, e cobre a corrida que a trava não cobre. A trilha
(`registrar`) entra na MESMA transação: se ela falhar, a escrituração não é
gravada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.fiscal.leitor import NS_NFSE, ArquivoRecusado, _raiz_segura
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.services import documentos_do_escritorio, situacao_do_documento

# tpRetISSQN 2 (retido pelo tomador) e 3 (retido pelo intermediário) são o
# "retido" da natureza. 1 (não retido) não é contado aqui — cai em "devido
# pelo prestador". Leitura do código, não cálculo: a retenção é só marcada.
TP_RET_ISSQN_RETIDO = frozenset({"2", "3"})

# `tribISSQN` — tributação do ISSQN sobre o serviço prestado. A TABELA DE
# CÓDIGOS MUDA ENTRE LEIAUTES, por isso há uma tabela por versão. Conferido nos
# XSD oficiais do pacote nfse-esquemas_xsd-v1-01-20260209.zip (caminhos dentro
# do pacote, 08/10/2026):
#   1.01 — Schemas/1.01/tiposSimples_v1.01.xsd:1068 (TSTribISSQN), enumeração
#          nas linhas 1080-1083: 1 operação tributável; 2 imunidade;
#          3 exportação de serviço; 4 não incidência.
#   1.00 — Schemas/1.00/tiposSimples_v1.00.xsd:1074 (TSTribISSQN), enumeração
#          nas linhas 1086-1089: 1 operação tributável; 2 exportação de serviço;
#          3 não incidência; 4 imunidade.
# Caminho do campo, nas duas versões: NFSe/infNFSe/DPS/infDPS/valores/trib/
# tribMun/tribISSQN (valores em TCInfDPS; trib em TCInfoValores; tribMun em
# TCInfoTributacao; tribISSQN em TCTribMunicipal):
#   1.01 — tiposComplexos_v1.01.xsd:831, :1626, :1638, :1859
#   1.00 — tiposComplexos_v1.00.xsd:365, :1229, :1242, :1471
# Só os códigos que a sugestão usa estão aqui; "1" (tributável) cai na regra
# seguinte, "devido pelo prestador".
_TRIB_ISSQN_POR_VERSAO = {
    "1.01": {"exportacao": "3", "imunidade": "2", "nao_incidencia": "4"},
    "1.00": {"exportacao": "2", "imunidade": "4", "nao_incidencia": "3"},
}
_NS = {"n": NS_NFSE}
_CAMINHO_TRIB_ISSQN = "n:infNFSe/n:DPS/n:infDPS/n:valores/n:trib/n:tribMun/n:tribISSQN"
# Mesmo caminho que o leitor usa para `dhEmi` (apps/fiscal/leitor.py, _ler_nfse).
_CAMINHO_DH_EMI = "n:infNFSe/n:DPS/n:infDPS/n:dhEmi"

# Situações devolvidas por `notas_a_escriturar` e pela conferência.
SITUACAO_A_ESCRITURAR = "a_escriturar"
SITUACAO_RASCUNHO = "rascunho"
SITUACAO_EFETIVADA = "efetivada"
SITUACAO_CANCELADA = "cancelada"
SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA = "cancelada_depois_de_escriturada"

_NOME_RESTRICAO_UNICA = "escrituracao_ativa_unica_por_vinculo"


# ---------------------------------------------------------------------------
# Exceções — mensagens em português, sem alíquota nem imposto.
# A API traduz `EscrituracaoErro` para 409 (conflito de estado) e
# `EntradaInvalidaEscrituracao` para 400 (entrada recusada antes de gravar).
# ---------------------------------------------------------------------------


class EscrituracaoErro(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaEscrituracao(EscrituracaoErro):
    pass


# ---------------------------------------------------------------------------
# Sugestão e leitura
# ---------------------------------------------------------------------------


def _iss_retido(documento: DocumentoFiscal) -> bool:
    return documento.tp_ret_issqn in TP_RET_ISSQN_RETIDO


@dataclass(frozen=True)
class _LeituraDoXml:
    """O que se lê do XML guardado, em UMA passada: dia de emissão e `tribISSQN`.

    Os dois campos são `None` quando o XML não permite lê-los. Nenhum dos dois
    cai num valor inventado (ver `_ler_xml`).
    """

    dia_emissao: date | None
    trib_issqn: str | None


_SEM_LEITURA = _LeituraDoXml(dia_emissao=None, trib_issqn=None)


def _ler_xml(documento: DocumentoFiscal) -> _LeituraDoXml:
    """Lê do XML guardado o dia de emissão (HI-72) e o `tribISSQN`.

    Não levanta exceção: XML ilegível, raiz fora do namespace da NFS-e e campo
    ausente viram `None`. A leitura usa `_raiz_segura` (defusedxml, sem DTD),
    o mesmo caminho seguro do recebimento: a sugestão e a data não abrem brecha
    que a recepção fecha. Lê-se UMA vez por nota, porque a lista de notas usa
    as duas coisas e o XML de cada nota pesa (medido na auditoria, A10).
    """
    try:
        raiz = _raiz_segura(bytes(documento.xml_original or b""))
    except ArquivoRecusado:
        return _SEM_LEITURA
    if raiz.tag != f"{{{NS_NFSE}}}NFSe":
        return _SEM_LEITURA
    return _LeituraDoXml(
        dia_emissao=_dia_do_dh_emi(raiz),
        trib_issqn=_trib_issqn_da_raiz(raiz, documento.versao),
    )


def _dia_do_dh_emi(raiz) -> date | None:
    # HI-72: o DIA ESCRITO no documento são os 10 primeiros caracteres do dhEmi,
    # no fuso do próprio emitente. Não se converte o instante para Brasília, que
    # trocaria o dia de uma nota emitida à noite em um fuso mais a oeste.
    elemento = raiz.find(_CAMINHO_DH_EMI, _NS)
    if elemento is None or elemento.text is None:
        return None
    try:
        return date.fromisoformat(elemento.text.strip()[:10])
    except ValueError:
        return None


def _trib_issqn_da_raiz(raiz, versao: str) -> str | None:
    if versao not in _TRIB_ISSQN_POR_VERSAO:
        return None
    elemento = raiz.find(_CAMINHO_TRIB_ISSQN, _NS)
    if elemento is None or elemento.text is None:
        return None
    # O texto é aparado e comparado, depois, com os códigos exatos da tabela.
    return elemento.text.strip()


def _data_de_emissao(documento: DocumentoFiscal) -> date | None:
    """Dia escrito no documento (HI-72), ou None se o XML guardado não o informa."""
    return _ler_xml(documento).dia_emissao


# Naturezas que o XML NÃO contradiz quando ele não diz exportação: todas, menos a
# própria exportação, que é a única que a regra A7 (b) contradiz. Devido, outro
# município, fora da lista, imune e retido são escolhas que esse XML não desmente.
# Outro município e fora da lista nunca são sugeridas (HI-67), então compará-las com
# a sugestão daria aviso falso. Retido sem tpRetISSQN 2 ou 3 também fica aceito: a
# regra A7 não cobre essa direção, e a correção não a amplia.
_NAO_CONTRADITO_SEM_EXPORTACAO = frozenset(NaturezaOperacao.values) - {
    NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO
}


@dataclass(frozen=True)
class _Veredito:
    """O que o XML diz sobre a natureza, calculado em UM lugar (reconferência R1).

    `sugerida` é o que o contador vê pré-selecionado. `aceitas` são as naturezas
    que o XML não contradiz, e a divergência é "natureza gravada FORA de `aceitas`".
    Os dois saem da mesma passada, pela mesma precedência, então não podem divergir:
    a sugestão está sempre em `aceitas` (teste nas 30 combinações de versão,
    tribISSQN e tpRetISSQN). `retido` e `exportacao` são os fatos do XML que a
    mensagem de aviso cita.
    """

    sugerida: NaturezaOperacao | None
    aceitas: frozenset
    retido: bool
    exportacao: bool


def _veredito(documento: DocumentoFiscal, trib_issqn: str | None) -> _Veredito:
    # Precedência da sugestão (HI-67): retenção, exportação, imunidade, não incidência
    # (sugestão None), e por fim devido. A primeira regra que casa vence.
    retido = _iss_retido(documento)
    codigos = _TRIB_ISSQN_POR_VERSAO.get(documento.versao, {})
    exportacao = trib_issqn is not None and trib_issqn == codigos.get("exportacao")
    if retido:
        # A retenção vence o tribISSQN na sugestão. Exportação no XML não contradiz
        # a retenção, então as duas são aceitas, e a escolha entre elas é do contador.
        aceitas = {NaturezaOperacao.PRESTADO_ISS_RETIDO}
        if exportacao:
            aceitas.add(NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO)
        return _Veredito(NaturezaOperacao.PRESTADO_ISS_RETIDO, frozenset(aceitas), True, exportacao)
    if exportacao:
        return _Veredito(
            NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
            frozenset({NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO}),
            False,
            True,
        )
    sugerida = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
    if trib_issqn is not None:
        if trib_issqn == codigos.get("imunidade"):
            sugerida = NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO
        elif trib_issqn == codigos.get("nao_incidencia"):
            sugerida = None
    # Imunidade não tem regra de divergência em A7: o escopo da correção não a inclui.
    return _Veredito(sugerida, _NAO_CONTRADITO_SEM_EXPORTACAO, False, False)


def sugerir_natureza(documento: DocumentoFiscal) -> NaturezaOperacao | None:
    """Natureza SUGERIDA para a nota (HI-67), ou None quando o XML não permite sugerir.

    Ordem, e a primeira regra que casa vence:
    1. `tpRetISSQN` 2 ou 3 → "ISS retido". A retenção vence qualquer `tribISSQN`.
    2. `tribISSQN` = exportação → exportação de serviço.
    3. `tribISSQN` = imunidade → "ISS imune, isento ou reduzido por lei do ente".
    4. `tribISSQN` = não incidência → **None**. Não-incidência NÃO é o mesmo que
       "fora da lista da LC 116", e o XML não diz qual dos dois é: o contador
       escolhe, e nada vem pré-selecionado.
    5. Qualquer outro caso (`tribISSQN` 1, campo ausente, XML ilegível, versão
       sem tabela) → "ISS devido pelo prestador".

    NUNCA sugere "ISS devido a outro município" nem "fora da lista da LC 116".
    Os códigos de `tribISSQN` estão conferidos nos XSD: ver `_TRIB_ISSQN_POR_VERSAO`.
    A sugestão e a divergência da natureza saem do mesmo `_Veredito` (reconferência R1).
    """
    return _veredito(documento, _ler_xml(documento).trib_issqn).sugerida


@dataclass(frozen=True)
class NotaPrestada:
    vinculo: VinculoDocumentoEmpresa
    documento: DocumentoFiscal
    situacao: str
    escrituracao: EscrituracaoFiscal | None
    # None quando a sugestão é "não incidência": nada vem pré-selecionado.
    natureza_sugerida: NaturezaOperacao | None
    # Dia escrito no documento (HI-72). None só se o XML guardado não o informa.
    data_emissao: date | None = None
    # Contradições entre a natureza GRAVADA e o XML (A7). Vazio sem escrituração.
    divergencias_de_natureza: tuple[str, ...] = ()

    @property
    def competencia_difere_da_emissao(self) -> bool:
        """Aviso (HI-57): mês de `dCompet` diferente do mês de emissão (HI-72).

        Sem data legível no XML não há com o que comparar, e o aviso não dispara.
        Isso não acontece com XML recebido pelo leitor, que exige `dhEmi` com fuso.
        """
        if self.data_emissao is None:
            return False
        competencia = self.documento.d_competencia
        return (self.data_emissao.year, self.data_emissao.month) != (
            competencia.year,
            competencia.month,
        )


@dataclass(frozen=True)
class Conferencia:
    """`recebidas == escrituradas + pendentes`, sempre.

    `pendentes` inclui as notas CANCELADAS que nunca foram escrituradas: elas
    não bloqueiam (não há o que escriturar), mas a identidade da conferência
    exige que cada nota recebida esteja em um dos dois grupos.
    `bloqueios` são as notas sem escrituração efetivada que ainda exigem ação.
    `avisos` são as notas com competência diferente da emissão (HI-59: avisa).
    """

    ano: int
    mes: int
    recebidas: int
    escrituradas: int
    pendentes: int
    bloqueios: list[NotaPrestada]
    avisos: list[NotaPrestada]
    # Natureza gravada que contradiz o XML (A7). Só relata; não bloqueia.
    divergencias: list[NotaPrestada]
    # Valores em R$ (A8): soma exata de `valor_servico` do documento, em Decimal.
    total_recebidas: Decimal
    total_escrituradas: Decimal
    total_pendentes: Decimal
    # Conciliação com a escrituração: o que foi GRAVADO nas efetivadas contra o
    # que está nos documentos correspondentes. Diferença ≠ 0 é destacada na tela.
    soma_gravada_escrituradas: Decimal
    soma_documentos_escrituradas: Decimal

    @property
    def diferenca_escrituradas(self) -> Decimal:
        return self.soma_gravada_escrituradas - self.soma_documentos_escrituradas


def notas_a_escriturar(empresa, ano: int, mes: int) -> list[NotaPrestada]:
    """NFS-e em que `empresa` é PRESTADORA e cuja `dCompet` cai em `ano/mes`.

    A consulta parte do escritório da empresa, então nota de outro escritório
    nunca aparece (AGENTS.md §11). A situação é derivada aqui, sem gravação.
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
            papel=PapelDocumento.PRESTADOR,
            documento_id__in=list(documentos.keys()),
        ).order_by("documento__dh_emissao", "id")
    )
    ativas = {
        escrituracao.vinculo_id: escrituracao
        for escrituracao in EscrituracaoFiscal.objects.filter(
            vinculo_id__in=[v.pk for v in vinculos],
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
    }

    return [
        _montar_nota(vinculo, documentos[vinculo.documento_id], ativas.get(vinculo.pk))
        for vinculo in vinculos
    ]


def nota_do_vinculo(empresa, vinculo: VinculoDocumentoEmpresa) -> NotaPrestada | None:
    """A mesma linha que `notas_a_escriturar` daria para ESTE vínculo, sem reprocessar
    o mês inteiro (auditoria A10). `None` para nota tomada, que não entra nesta lista.

    Quem chama confere antes que o vínculo é de `empresa` e de um documento do
    escritório ativo. Aqui isso é um erro de programação, então levanta.
    """
    if vinculo.empresa_id != empresa.pk:
        raise ValueError("O vínculo não pertence à empresa informada.")
    if vinculo.papel != PapelDocumento.PRESTADOR:
        return None
    escrituracao = EscrituracaoFiscal.objects.filter(
        vinculo=vinculo,
        estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
    ).first()
    return _montar_nota(vinculo, vinculo.documento, escrituracao)


def _cancelada(documento: DocumentoFiscal) -> bool:
    # Lê a anotação `.cancelada` de `documentos_do_escritorio` quando ela existe
    # (sem consulta extra por nota). Sem a anotação, cai na fonte única.
    anotada = getattr(documento, "cancelada", None)
    if anotada is not None:
        return bool(anotada)
    return situacao_do_documento(documento) == "cancelada"


def _situacao(documento: DocumentoFiscal, escrituracao: EscrituracaoFiscal | None) -> str:
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
    escrituracao: EscrituracaoFiscal | None,
) -> NotaPrestada:
    # Uma leitura do XML por nota (HI-72: a data; tribISSQN) e UM veredito, que alimenta
    # a sugestão e a divergência (R1). Não se recalcula uma coisa a partir da outra.
    leitura = _ler_xml(documento)
    veredito = _veredito(documento, leitura.trib_issqn)
    divergencias = ()
    if escrituracao is not None:
        divergencias = tuple(_divergencias_da_natureza(escrituracao.natureza, veredito, documento))
    return NotaPrestada(
        vinculo=vinculo,
        documento=documento,
        situacao=_situacao(documento, escrituracao),
        escrituracao=escrituracao,
        natureza_sugerida=veredito.sugerida,
        data_emissao=leitura.dia_emissao,
        divergencias_de_natureza=divergencias,
    )


# Naturezas que afirmam "sem retenção" (a retenção do XML, tpRetISSQN 2 ou 3, as contradiz).
_NATUREZAS_QUE_CONTRADIZEM_RETENCAO = frozenset(
    {
        NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR,
        NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO,
        NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO,
        NaturezaOperacao.PRESTADO_FORA_LISTA_LC116,
    }
)


def _divergencias_da_natureza(
    natureza: str, veredito: _Veredito, documento: DocumentoFiscal
) -> list[str]:
    """Contradições entre a natureza GRAVADA e o XML (auditoria A7, HI-59 "avisa").

    Só relata: o contador decide, e a divergência não bloqueia a efetivação.

    Por que a regra é "fora de `aceitas`", e não "diferente da sugestão" (R1): a
    sugestão é a pré-seleção de uma precedência, não tudo o que o XML permite. Com
    "diferente da sugestão", um outro município escolhido pelo contador, num XML sem
    retenção nem exportação, viraria aviso falso. Aceitar a sugestão nunca gera aviso,
    porque a sugestão sempre está em `aceitas`. As mensagens continuam por regra, e
    só saem quando a natureza já foi recusada por `aceitas`.
    """
    if natureza in veredito.aceitas:
        return []
    avisos = []
    if veredito.retido and natureza in _NATUREZAS_QUE_CONTRADIZEM_RETENCAO:
        avisos.append(
            f"O XML indica retenção do ISS (tpRetISSQN {documento.tp_ret_issqn}), "
            f"mas a natureza gravada é '{NaturezaOperacao(natureza).label}'."
        )
    if natureza == NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO and not veredito.exportacao:
        avisos.append(
            "A natureza gravada é exportação de serviço, mas o XML não traz "
            "tribISSQN de exportação."
        )
    if natureza != NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO and veredito.exportacao:
        avisos.append(
            "O XML traz tribISSQN de exportação, mas a natureza gravada é "
            f"'{NaturezaOperacao(natureza).label}'."
        )
    return avisos


def _soma(valores) -> Decimal:
    # Soma exata em Decimal, na escala do documento (duas casas). Nunca float.
    return sum(valores, Decimal("0.00"))


def conferencia(empresa, ano: int, mes: int) -> Conferencia:
    """Recebidas × escrituradas × pendentes, com bloqueios e avisos (HI-59).

    Só relatório: nenhum fechamento, nenhuma gravação.
    """
    notas = notas_a_escriturar(empresa, ano, mes)
    escrituradas = [n for n in notas if n.situacao == SITUACAO_EFETIVADA]
    pendentes = [n for n in notas if n.situacao != SITUACAO_EFETIVADA]
    bloqueios = [
        n
        for n in pendentes
        if n.situacao
        in (SITUACAO_A_ESCRITURAR, SITUACAO_RASCUNHO, SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA)
    ]
    avisos = [n for n in notas if n.competencia_difere_da_emissao]
    divergencias = [n for n in notas if n.divergencias_de_natureza]
    return Conferencia(
        ano=ano,
        mes=mes,
        recebidas=len(notas),
        escrituradas=len(escrituradas),
        pendentes=len(pendentes),
        bloqueios=bloqueios,
        avisos=avisos,
        divergencias=divergencias,
        total_recebidas=_soma(n.documento.v_serv for n in notas),
        total_escrituradas=_soma(n.documento.v_serv for n in escrituradas),
        total_pendentes=_soma(n.documento.v_serv for n in pendentes),
        soma_gravada_escrituradas=_soma(n.escrituracao.valor_servico for n in escrituradas),
        soma_documentos_escrituradas=_soma(n.documento.v_serv for n in escrituradas),
    )


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


def _snapshot(escrituracao: EscrituracaoFiscal | None) -> dict | None:
    """Estado da escrituração em forma serializável, para o `antes`/`depois`
    da trilha. Só dados do próprio ato; nada de segredo."""
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
        "iss_retido": escrituracao.iss_retido,
        "efetivada_em": iso(escrituracao.efetivada_em),
        "efetivada_por": escrituracao.efetivada_por_id,
        "estornada_em": iso(escrituracao.estornada_em),
        "estornada_por": escrituracao.estornada_por_id,
        "motivo_estorno": escrituracao.motivo_estorno,
    }


def _valores_copiados_do_documento(documento: DocumentoFiscal) -> dict:
    # Copiados NA EFETIVAÇÃO (plano, item 4), com a escala do documento.
    data_emissao = _data_de_emissao(documento)
    if data_emissao is None:
        # Sem o dia escrito no XML não há data a copiar. Nada é gravado inventado.
        raise EscrituracaoErro(
            "O XML guardado desta nota não informa a data de emissão. "
            "A nota não pode ser escriturada."
        )
    return {
        "data_emissao": data_emissao,
        "data_competencia": documento.d_competencia,
        "valor_servico": documento.v_serv,
        "valor_liquido": documento.v_liq,
        "iss_retido": _iss_retido(documento),
    }


def _travar_vinculo_prestador(vinculo: VinculoDocumentoEmpresa) -> VinculoDocumentoEmpresa:
    """Trava o vínculo e recusa o que não pode ser escriturado.

    Chamado DENTRO de `transaction.atomic()`. `of=("self",)` trava só a linha
    do vínculo, não as linhas de empresa e documento que o `select_related`
    traz junto.
    """
    travado = (
        VinculoDocumentoEmpresa.objects.select_for_update(of=("self",))
        .select_related("documento", "empresa__escritorio")
        .get(pk=vinculo.pk)
    )
    if travado.papel != PapelDocumento.PRESTADOR:
        # Nota tomada (entrada) é outra etapa (DL-072 "fica fora").
        raise EntradaInvalidaEscrituracao(
            "Só é escriturada a nota em que a empresa é prestadora. "
            "Nota tomada não entra nesta escrituração."
        )
    if situacao_do_documento(travado.documento) == "cancelada":
        # Recusa nomeada (critério 5): cancelada não é efetivada.
        raise EscrituracaoErro("Nota cancelada não pode ser escriturada.")
    return travado


def _ativa_do_vinculo_travado(vinculo: VinculoDocumentoEmpresa) -> EscrituracaoFiscal | None:
    return (
        EscrituracaoFiscal.objects.select_for_update(of=("self",))
        .filter(
            vinculo=vinculo,
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
        .first()
    )


def _erro_de_unicidade_da_escrituracao(exc: IntegrityError) -> bool:
    """A violação foi a da restrição parcial, e não outra integridade?"""
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diag, "constraint_name", None) == _NOME_RESTRICAO_UNICA


def _inserir_escrituracao(escrituracao: EscrituracaoFiscal) -> None:
    """INSERT de uma escrituração nova, traduzindo a corrida em erro de negócio.

    A trava de `_travar_vinculo_prestador` deveria impedir duas linhas ativas
    para o mesmo vínculo. Se uma corrida escapar dela, a restrição parcial do
    banco recusa o segundo INSERT, e aqui isso vira 409 com mensagem (não 500).
    O SAVEPOINT isola só este INSERT: a transação de quem chamou segue viva.
    """
    try:
        with transaction.atomic():
            escrituracao.save()
    except IntegrityError as exc:
        if _erro_de_unicidade_da_escrituracao(exc):
            raise EscrituracaoErro(
                "Esta nota acabou de ser escriturada por outra ação. Atualize a lista."
            ) from exc
        raise


MENSAGEM_NATUREZA_VAZIA = "Escolha a natureza da operação."
# Não ecoa o valor enviado: ele vem do cliente e não precisa voltar na mensagem.
MENSAGEM_NATUREZA_FORA_DO_CATALOGO = (
    "Natureza de operação desconhecida: o valor enviado não é uma das naturezas "
    "do catálogo fiscal. Escolha uma das opções da lista."
)


def _validar_natureza(natureza: str) -> None:
    if not natureza:
        raise EntradaInvalidaEscrituracao(MENSAGEM_NATUREZA_VAZIA)
    if natureza not in NaturezaOperacao.values:
        raise EntradaInvalidaEscrituracao(MENSAGEM_NATUREZA_FORA_DO_CATALOGO)


@transaction.atomic
def salvar_rascunho(
    vinculo: VinculoDocumentoEmpresa, natureza: str, usuario, request=None
) -> EscrituracaoFiscal:
    """Grava (ou troca) a natureza ainda NÃO confirmada — estado `rascunho`.

    O contador pode mudar a natureza sugerida antes de efetivar (critério 3).
    Não há efetivação aqui: o rascunho não conta como escriturado.
    """
    _validar_natureza(natureza)
    travado = _travar_vinculo_prestador(vinculo)
    ativa = _ativa_do_vinculo_travado(travado)
    if ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoErro(
            "Esta nota já está efetivada. Estorne a escrituração para alterar a natureza."
        )

    antes = _snapshot(ativa)
    if ativa is None:
        escrituracao = EscrituracaoFiscal(
            vinculo=travado,
            empresa=travado.empresa,
            natureza=natureza,
            estado=EstadoEscrituracao.RASCUNHO,
            criado_por=usuario,
        )
        _inserir_escrituracao(escrituracao)
    else:
        atualizadas = EscrituracaoFiscal.objects.filter(
            pk=ativa.pk, estado=EstadoEscrituracao.RASCUNHO
        ).update(natureza=natureza)
        if atualizadas != 1:
            raise EscrituracaoErro("A escrituração mudou enquanto era alterada. Atualize a lista.")
        escrituracao = EscrituracaoFiscal.objects.get(pk=ativa.pk)

    registrar(
        acao="escrituracao_fiscal.rascunho_salvo",
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
def efetivar_escrituracao(
    vinculo: VinculoDocumentoEmpresa, natureza: str, usuario, request=None
) -> EscrituracaoFiscal:
    """Efetiva a nota com a natureza confirmada pelo contador.

    IDEMPOTÊNCIA (decisão registrada): se a nota já está efetivada com a MESMA
    natureza, devolve a escrituração existente com `criada_agora = False`, sem
    gravar nada e sem nova entrada na trilha — repetir o clique não é um fato
    novo. Se já está efetivada com OUTRA natureza, recusa com 409: a troca é
    estorno + nova efetivação, para que a trilha mostre as duas.

    Se havia rascunho, ele vira efetivada (a mesma linha, não uma duplicata).
    """
    _validar_natureza(natureza)
    travado = _travar_vinculo_prestador(vinculo)
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
    agora = timezone.now()
    valores = _valores_copiados_do_documento(documento)
    antes = _snapshot(ativa)

    if ativa is None:
        escrituracao = EscrituracaoFiscal(
            vinculo=travado,
            empresa=travado.empresa,
            natureza=natureza,
            estado=EstadoEscrituracao.EFETIVADA,
            efetivada_em=agora,
            efetivada_por=usuario,
            criado_por=usuario,
            **valores,
        )
        _inserir_escrituracao(escrituracao)
    else:
        atualizadas = EscrituracaoFiscal.objects.filter(
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
        escrituracao = EscrituracaoFiscal.objects.get(pk=ativa.pk)

    escrituracao.criada_agora = True
    registrar(
        acao="escrituracao_fiscal.efetivada",
        usuario=usuario,
        escritorio=travado.empresa.escritorio,
        objeto=escrituracao,
        request=request,
        detalhes={
            "vinculo_id": travado.pk,
            # Divergência entre a natureza confirmada e a sugerida fica
            # visível na trilha; não é bloqueada (o contador decide).
            "natureza_sugerida": sugerir_natureza(documento),
            "antes": antes,
            "depois": _snapshot(escrituracao),
        },
    )
    return escrituracao


MOTIVO_MAXIMO = 500  # EscrituracaoFiscal.motivo_estorno (models.py)


@transaction.atomic
def estornar_escrituracao(
    escrituracao: EscrituracaoFiscal, motivo: str, usuario, request=None
) -> EscrituracaoFiscal:
    """Estorna uma escrituração efetivada, com motivo obrigatório.

    A nota volta a "a escriturar" porque a linha deixa de ser ativa (a
    restrição parcial só conta rascunho e efetivada). A linha não é apagada:
    o estorno é o próprio registro da correção, e a trilha guarda o antes e o
    depois.
    """
    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise EntradaInvalidaEscrituracao("Informe o motivo do estorno.")
    if len(motivo_limpo) > MOTIVO_MAXIMO:
        raise EntradaInvalidaEscrituracao(
            f"O motivo do estorno tem no máximo {MOTIVO_MAXIMO} caracteres."
        )

    travada = (
        EscrituracaoFiscal.objects.select_for_update(of=("self",))
        .select_related("empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoErro(
            "Só escrituração efetivada pode ser estornada; esta está "
            f"'{travada.get_estado_display()}'."
        )

    antes = _snapshot(travada)
    atualizadas = EscrituracaoFiscal.objects.filter(
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
        acao="escrituracao_fiscal.estornada",
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
