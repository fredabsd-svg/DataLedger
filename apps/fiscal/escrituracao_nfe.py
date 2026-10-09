"""Escrituração das NF-e de saída e da devolução de venda — DL-081, frente A (domínio).

Plano: docs/planos/DL-081-escrituracao-das-nfe-de-saida.md. Fonte normativa: consulta de
09/10/2026 (docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md), itens 1 a 7.
Hipóteses HI-117 a HI-124 (requisitos.md). Decisões que o código não explica sozinho:

- ELEGIBILIDADE. Saída própria: a empresa é emitente, `tpNF` 1 e `finNFe` 1, modelos 55 e 65.
  Devolução de venda: `finNFe` 4, em nota de terceiro em que a empresa é destinatária, ou nota
  própria de entrada (emitente com `tpNF` 0). Ajuste: `finNFe` 2, 3, 5 ou 6, só na saída própria.
  Compras e demais entradas ficam fora (a recepção da DL-080 continua valendo como está).
- SUGESTÃO DE NATUREZA, por item, sem gravar nada. Sinais (consulta, item 2): `finNFe` decide
  devolução e ajuste; depois CFOP (com a tabela oficial), CST/CSOSN e `idDest`. Se dois sinais
  apontam naturezas DIFERENTES, a sugestão fica em branco ("conflito"). CFOP fora da tabela
  fica "a classificar". Comercial exportadora, bonificação e monofásico nunca têm sugestão.
- DEVOLUÇÃO identificada pelo `indDevol` da tabela oficial, nunca pela faixa do CFOP.
- CONFERÊNCIA (HI-119): a receita dos itens com `indTot` 1 tem de bater com
  `vNF − vST − vIPI − vII − vIPIDevol`, com tolerância ZERO. Nota sem vNF não é conferida: é
  recusa, porque o total é obrigatório no XSD. vST, vIPI, vII e vIPIDevol ausentes valem zero
  só nessa fórmula, e a divergência bloqueia a efetivação com os valores na mensagem.
- Competência = mês de `dhEmi` no fuso de São Paulo (consulta, item 1).
- Nada aqui calcula ICMS, guia ou alíquota. Só se escritura e se confere.
- Concorrência: cada serviço que escreve roda em `transaction.atomic()` e trava a EMPRESA
  (`receita.travar_empresa`) antes do vínculo, na mesma ordem da DL-072/DL-074. A restrição
  parcial do banco é a segunda defesa. A trilha entra na MESMA transação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Exists, Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.fiscal import receita as receita_servico
from apps.fiscal import services
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    PapelNFe,
    TipoEscrituracaoNFe,
    VinculoNFeEmpresa,
    mercado_da_natureza_nfe,
    papel_da_natureza_nfe,
)

FUSO_SP = ZoneInfo("America/Sao_Paulo")
MOTIVO_MAXIMO = 500
_NOME_RESTRICAO_UNICA = "escrituracao_nfe_ativa_unica_por_vinculo"

# Naturezas que só cabem em um tipo de nota (consulta, item 2 e Hipóteses 2 e 3).
_NATUREZA_DE_AJUSTE = NaturezaOperacaoNFe.AJUSTE
_NATUREZA_DE_DEVOLUCAO = NaturezaOperacaoNFe.DEVOLUCAO_VENDA

# Situações da nota, como a tela e a API as mostram.
SITUACAO_A_ESCRITURAR = "a_escriturar"
SITUACAO_RASCUNHO = "rascunho"
SITUACAO_EFETIVADA = "efetivada"
SITUACAO_CANCELADA = "cancelada"
SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA = "cancelada_depois_de_escriturada"
SITUACAO_NAO_ELEGIVEL = "nao_elegivel"

# Sinais de sugestão (consulta, item 2). Cada um dá uma natureza candidata.
ORIGEM_FIN_NFE = "finalidade (finNFe)"
ORIGEM_CFOP = "CFOP"
ORIGEM_CST = "CST/CSOSN"
ORIGEM_ID_DEST = "local de destino (idDest)"

# CFOP de comercial exportadora e de bonificação: a consulta não dá sinal suficiente (HI-118).
_CFOP_SEM_SUGESTAO = frozenset({"501", "502", "910", "911"})
_CFOP_TRANSFERENCIA = frozenset({"151", "152", "153", "154", "155", "156"})
_CFOP_PRODUCAO = frozenset({"101", "103"})
_CFOP_REVENDA = frozenset({"102", "104"})
_CST_SUBSTITUIDO = frozenset({"500", "60"})
_CST_SUBSTITUTO = frozenset({"201", "202", "203", "10", "30", "70"})


class EscrituracaoNFeErro(Exception):
    """Regra de negócio que impede o ato. A API traduz em 409 (estado) ou 400 (entrada)."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaNFe(EscrituracaoNFeErro):
    pass


# ---------------------------------------------------------------------------
# Competência e elegibilidade
# ---------------------------------------------------------------------------


def dia_e_competencia(documento) -> tuple[date, date]:
    """(dia do dhEmi, primeiro dia do mês do dhEmi), no fuso de São Paulo (consulta, item 1)."""
    local = documento.dh_emissao.astimezone(FUSO_SP).date()
    return local, local.replace(day=1)


def tipo_da_nota(documento, papel: str) -> str | None:
    """Tipo da escrituração para a empresa no papel dado, ou `None` se a nota não é elegível.

    Não olha cancelamento: a situação é do chamador (`situacao_da_nfe`), que muda com o tempo.
    """
    if documento.modelo not in ("55", "65"):
        return None
    tp_nf, fin = documento.tp_nf, documento.fin_nfe
    if papel == PapelNFe.EMITENTE:
        if tp_nf == "1" and fin == "1":
            return TipoEscrituracaoNFe.SAIDA_PROPRIA
        if tp_nf == "1" and fin in ("2", "3", "5", "6"):
            return TipoEscrituracaoNFe.AJUSTE
        if tp_nf == "0" and fin == "4":
            # Nota própria de entrada que devolve venda (consulta, item 2, natureza 9).
            return TipoEscrituracaoNFe.DEVOLUCAO
        return None
    if papel == PapelNFe.DESTINATARIO and fin == "4":
        # Devolução de venda recebida: a nota é de terceiro e a empresa é a destinatária.
        return TipoEscrituracaoNFe.DEVOLUCAO
    return None


def motivo_fora_da_escrituracao(documento, papel: str) -> str:
    """Por que a nota não entra na escrituração. Nomeado, nunca genérico."""
    if documento.modelo not in ("55", "65"):
        return "modelo fora da escrituração de NF-e (só 55 e 65)."
    if papel == PapelNFe.DESTINATARIO:
        return "nota de entrada (compra): fora desta escrituração, só a recepção."
    if documento.tp_nf == "0":
        return (
            "nota de entrada emitida pela empresa: só entra se for devolução de venda (finNFe 4)."
        )
    return (
        "saída que não é venda própria nem ajuste (finNFe "
        f"{documento.fin_nfe}): fora desta escrituração."
    )


def naturezas_permitidas(tipo: str) -> frozenset[str]:
    """Naturezas aceitas por tipo de nota. Ajuste só ajuste; devolução só natureza 9."""
    if tipo == TipoEscrituracaoNFe.AJUSTE:
        return frozenset({_NATUREZA_DE_AJUSTE})
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO:
        return frozenset({_NATUREZA_DE_DEVOLUCAO})
    return frozenset(CATALOGO_NATUREZA_NFE) - {_NATUREZA_DE_AJUSTE, _NATUREZA_DE_DEVOLUCAO}


# ---------------------------------------------------------------------------
# Sugestão de natureza (consulta, item 2). Nunca grava: quem grava é o contador.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sugestao:
    natureza: str | None
    motivo: str


def _candidatos_do_item(documento, item) -> list[tuple[str, str]]:
    """(natureza, origem) de cada sinal que aponta uma natureza. Vazio = nenhum sinal."""
    candidatos: list[tuple[str, str]] = []
    cfop_digitos = item.cfop
    primeiro, sufixo = cfop_digitos[0], cfop_digitos[1:]

    if primeiro == "7" and documento.id_dest == "3":
        candidatos.append((NaturezaOperacaoNFe.EXPORTACAO_DIRETA, ORIGEM_ID_DEST))
    if cfop_digitos == "5929":
        candidatos.append((NaturezaOperacaoNFe.CUPOM_NFCE, ORIGEM_CFOP))
    if sufixo in _CFOP_TRANSFERENCIA and documento.transferencia_entre_estabelecimentos:
        candidatos.append((NaturezaOperacaoNFe.TRANSFERENCIA, ORIGEM_CFOP))
    if primeiro in ("5", "6"):
        if sufixo in _CFOP_REVENDA:
            candidatos.append((NaturezaOperacaoNFe.REVENDA, ORIGEM_CFOP))
        elif sufixo in _CFOP_PRODUCAO:
            candidatos.append((NaturezaOperacaoNFe.PRODUCAO_PROPRIA, ORIGEM_CFOP))

    csosn, cst = item.csosn, item.cst
    if csosn in _CST_SUBSTITUIDO or cst in _CST_SUBSTITUIDO:
        candidatos.append((NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO, ORIGEM_CST))
    if csosn in _CST_SUBSTITUTO or cst in _CST_SUBSTITUTO:
        candidatos.append((NaturezaOperacaoNFe.SUBSTITUTO_ST, ORIGEM_CST))
    return candidatos


def sugerir_natureza_item(documento, item, tipo: str | None = None) -> Sugestao:
    """Sugestão de natureza para um item (consulta, item 2 e Hipóteses 2 e 3).

    Ordem: finalidade (`finNFe`) primeiro. Depois, na saída própria, os sinais do item. Sinais que
    apontam naturezas diferentes dão `None` com o motivo "conflito". Sem sinal, `None`.
    """
    if tipo is None:
        tipo = tipo_da_nota(documento, PapelNFe.EMITENTE) or ""
    fin = documento.fin_nfe
    if fin in ("2", "3", "5", "6"):
        return Sugestao(NaturezaOperacaoNFe.AJUSTE, f"{ORIGEM_FIN_NFE} {fin}: ajuste")

    info = consultar_cfop(item.cfop)
    if info is None:
        return Sugestao(None, "a classificar: CFOP fora da tabela oficial (Informe 2023.002 v2.10)")

    if fin == "4":
        # Devolução: a coluna indDevol da tabela decide. A faixa do CFOP não decide.
        if info.ind_devol:
            return Sugestao(_NATUREZA_DE_DEVOLUCAO, f"{ORIGEM_FIN_NFE} 4 e CFOP com indDevol 1")
        return Sugestao(None, "conflito: finNFe 4 com CFOP sem indDevol (não é devolução)")

    sufixo = item.cfop[1:]
    if sufixo in _CFOP_SEM_SUGESTAO:
        return Sugestao(
            None, f"sem sugestão: CFOP {item.cfop} (comercial exportadora, bonificação)"
        )
    if info.ind_devol:
        # Saída com indDevol 1 é devolução de COMPRA: não tem natureza no catálogo de venda.
        return Sugestao(None, "sem sugestão: devolução de compra em saída, fora do catálogo")

    candidatos = _candidatos_do_item(documento, item)
    naturezas = {natureza for natureza, _ in candidatos}
    if not candidatos:
        return Sugestao(None, "sem sinal suficiente: escolha a natureza")
    if len(naturezas) > 1:
        origens = ", ".join(sorted({origem for _, origem in candidatos}))
        return Sugestao(None, f"conflito entre sinais ({origens}): escolha a natureza")
    natureza, origem = candidatos[0]
    return Sugestao(natureza, f"sugerida pelo sinal de {origem}")


def segregacao_da_escrituracao(escrituracao: EscrituracaoNFe) -> dict[str, Decimal]:
    """Receita de mercadoria por segregação do Simples (consulta, item 3): memória, sem alíquota.

    Normal (revenda, produção, substituto: a operação própria), sujeita a ST (natureza 3),
    monofásico (natureza 5) e exportação (mercado externo). Só itens de receita, com indTot 1.
    A natureza de serviço (14) não entra aqui: é segregada no pré-DAS de serviços, fora deste corte.
    """
    total = {
        "normal": Decimal("0.00"),
        "sujeita_st": Decimal("0.00"),
        "monofasico": Decimal("0.00"),
        "exportacao": Decimal("0.00"),
    }
    registros = NaturezaItemNFe.objects.select_related("item").filter(
        escrituracao=escrituracao, item__ind_tot="1"
    )
    for registro in registros:
        if not registro.natureza:
            continue
        info = CATALOGO_NATUREZA_NFE[registro.natureza]
        if info.papel != "receita" or info.segregacao is None:
            continue
        total[info.segregacao] += registro.item.receita_bruta_item
    return total


# ---------------------------------------------------------------------------
# Listagem por mês
# ---------------------------------------------------------------------------


@dataclass
class NotaDoMes:
    """Uma nota da empresa no mês, com a situação derivada e a escrituração ativa, se houver."""

    vinculo: VinculoNFeEmpresa
    documento: object
    tipo: str | None
    motivo_fora: str | None
    situacao: str
    escrituracao: EscrituracaoNFe | None
    leitura_estado: str | None
    leitura_motivo: str
    leitura: LeituraItensNFe | None = None


def _limites_do_mes(ano: int, mes: int) -> tuple[datetime, datetime]:
    inicio = datetime(ano, mes, 1, tzinfo=FUSO_SP)
    proximo = receita_servico._proximo_mes(ano, mes)
    return inicio, datetime(proximo.year, proximo.month, 1, tzinfo=FUSO_SP)


def notas_do_mes(empresa, ano: int, mes: int) -> list[NotaDoMes]:
    """Notas recebidas da empresa cuja competência cai no mês, com a situação de cada uma.

    A leitura de itens NÃO é feita aqui (consulta não grava): mostra "ainda não lida" até a
    criação do rascunho ou a conferência. Isolamento: só vínculos desta empresa e deste escritório.
    """
    inicio, fim = _limites_do_mes(ano, mes)
    vinculos = list(
        VinculoNFeEmpresa.objects.filter(
            empresa=empresa,
            documento__escritorio=empresa.escritorio,
            documento__dh_emissao__gte=inicio,
            documento__dh_emissao__lt=fim,
        )
        .select_related("documento")
        .order_by("-documento__dh_emissao", "-documento_id")
    )
    ativas = {
        e.vinculo_id: e
        for e in EscrituracaoNFe.objects.filter(
            vinculo__in=vinculos,
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
    }
    leituras = {
        lt.documento_id: lt
        for lt in LeituraItensNFe.objects.filter(documento__in=[v.documento_id for v in vinculos])
    }
    notas = []
    for vinculo in vinculos:
        documento = vinculo.documento
        tipo = tipo_da_nota(documento, vinculo.papel)
        cancelada = services.situacao_da_nfe(documento) == "cancelada"
        ativa = ativas.get(vinculo.pk)
        leitura = leituras.get(documento.pk)
        if tipo is None:
            situacao, motivo = (
                SITUACAO_NAO_ELEGIVEL,
                motivo_fora_da_escrituracao(documento, vinculo.papel),
            )
        elif ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
            situacao = SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA if cancelada else SITUACAO_EFETIVADA
            motivo = ""
        elif cancelada:
            situacao, motivo = SITUACAO_CANCELADA, "nota cancelada: não é escriturada."
        elif ativa is not None:
            situacao, motivo = SITUACAO_RASCUNHO, ""
        else:
            situacao, motivo = SITUACAO_A_ESCRITURAR, ""
        notas.append(
            NotaDoMes(
                vinculo=vinculo,
                documento=documento,
                tipo=tipo,
                motivo_fora=motivo if tipo is None else None,
                situacao=situacao,
                escrituracao=ativa,
                leitura_estado=leitura.estado if leitura else None,
                leitura_motivo=leitura.motivo if leitura else "",
                leitura=leitura,
            )
        )
    return notas


# ---------------------------------------------------------------------------
# Escrita: rascunho, natureza, efetivação e estorno
# ---------------------------------------------------------------------------


def _snapshot(escrituracao: EscrituracaoNFe | None) -> dict | None:
    if escrituracao is None:
        return None

    def texto(valor):
        return None if valor is None else format(valor, "f")

    return {
        "id": escrituracao.pk,
        "estado": escrituracao.estado,
        "tipo": escrituracao.tipo,
        "competencia": None
        if escrituracao.competencia is None
        else escrituracao.competencia.isoformat(),
        "valor_nf": texto(escrituracao.valor_nf),
        "receita_bruta": texto(escrituracao.receita_bruta),
        "devolucao": texto(escrituracao.devolucao),
        "motivo_estorno": escrituracao.motivo_estorno,
    }


def _naturezas_snapshot(escrituracao: EscrituracaoNFe) -> dict[int, str]:
    return {
        n.item_id: n.natureza for n in NaturezaItemNFe.objects.filter(escrituracao=escrituracao)
    }


def _travar_vinculo(vinculo: VinculoNFeEmpresa) -> VinculoNFeEmpresa:
    """Trava o vínculo, dentro da transação de quem chama."""
    return (
        VinculoNFeEmpresa.objects.select_for_update(of=("self",))
        .select_related("documento", "empresa__escritorio")
        .get(pk=vinculo.pk)
    )


def _ativa_do_vinculo(vinculo: VinculoNFeEmpresa) -> EscrituracaoNFe | None:
    return (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .filter(
            vinculo=vinculo,
            estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
        )
        .first()
    )


def _inserir(escrituracao: EscrituracaoNFe) -> None:
    """INSERT com SAVEPOINT: a corrida na restrição parcial vira erro de negócio, não 500."""
    try:
        with transaction.atomic():
            escrituracao.save()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "__cause__", None), "diag", None)
        if getattr(diag, "constraint_name", None) == _NOME_RESTRICAO_UNICA:
            raise EscrituracaoNFeErro(
                "Esta nota acabou de ser escriturada por outra ação. Atualize a lista."
            ) from exc
        raise


def _validar_natureza_para_o_tipo(natureza: str, tipo: str) -> None:
    if not natureza:
        raise EntradaInvalidaNFe("Escolha a natureza da operação.")
    if natureza not in CATALOGO_NATUREZA_NFE:
        # Não ecoa o valor enviado: ele vem do cliente.
        raise EntradaInvalidaNFe(
            "Natureza de operação desconhecida: escolha uma das opções do catálogo fiscal."
        )
    if natureza not in naturezas_permitidas(tipo):
        raise EntradaInvalidaNFe(
            "Esta natureza não cabe neste tipo de nota "
            f"({TipoEscrituracaoNFe(tipo).label.lower()})."
        )


def criar_rascunho(vinculo: VinculoNFeEmpresa, usuario, request=None) -> EscrituracaoNFe:
    """Cria o rascunho de uma nota elegível, com uma linha de natureza por item (vazia).

    Idempotente: se já há rascunho, devolve-o com `criada_agora = False`. Efetivada, recusa (409).
    Itens ilegíveis ou nota cancelada bloqueiam, com o motivo.

    A LEITURA dos itens roda ANTES da transação de escrita, em transação própria. Assim, a nota
    ilegível fica gravada como tal (idempotente), mesmo com a recusa do rascunho logo depois.
    Dentro de uma transação só, a recusa desfaria a leitura e ela seria refeita a cada clique.
    """
    documento = vinculo.documento
    tipo = tipo_da_nota(documento, vinculo.papel)
    if tipo is None:
        raise EscrituracaoNFeErro(motivo_fora_da_escrituracao(documento, vinculo.papel))
    if services.situacao_da_nfe(documento) == "cancelada":
        raise EscrituracaoNFeErro("Nota cancelada não pode ser escriturada.")
    ler_itens(documento)
    return _criar_rascunho_travado(vinculo, usuario, request)


@transaction.atomic
def _criar_rascunho_travado(vinculo: VinculoNFeEmpresa, usuario, request) -> EscrituracaoNFe:
    travado = _travar_vinculo(vinculo)
    ativa = _ativa_do_vinculo(travado)
    if ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoNFeErro(
            "Esta nota já está efetivada. Estorne a escrituração para refazer."
        )
    if ativa is not None:
        ativa.criada_agora = False
        return ativa

    documento = travado.documento
    leitura = LeituraItensNFe.objects.get(documento=documento)
    if leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL:
        raise EscrituracaoNFeErro(f"Itens ilegíveis, nota bloqueada: {leitura.motivo}")

    escrituracao = EscrituracaoNFe(
        vinculo=travado,
        empresa=travado.empresa,
        tipo=tipo_da_nota(documento, travado.papel),
        estado=EstadoEscrituracao.RASCUNHO,
        criado_por=usuario,
    )
    _inserir(escrituracao)
    NaturezaItemNFe.objects.bulk_create(
        NaturezaItemNFe(escrituracao=escrituracao, item=item)
        for item in ItemNFe.objects.filter(documento=documento).order_by("n_item")
    )
    escrituracao.criada_agora = True
    registrar(
        acao="escrituracao_nfe.rascunho_criado",
        usuario=usuario,
        escritorio=travado.empresa.escritorio,
        objeto=escrituracao,
        request=request,
        detalhes={
            "vinculo_id": travado.pk,
            "tipo": escrituracao.tipo,
            "depois": _snapshot(escrituracao),
        },
    )
    return escrituracao


@transaction.atomic
def definir_natureza(
    escrituracao: EscrituracaoNFe, natureza: str, item_ids, usuario, request=None
) -> EscrituracaoNFe:
    """Confirma a natureza de UM ou de VÁRIOS itens da mesma nota (em bloco, HI-118).

    Só rascunho: efetivada ou estornada não muda (o banco também recusa). Itens de outra nota são
    recusados sem gravar nada.
    """
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        raise EntradaInvalidaNFe("Informe ao menos um item.")
    receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise EscrituracaoNFeErro(
            "Esta escrituração não é mais rascunho. Estornada ou efetivada, a natureza não muda."
        )
    _validar_natureza_para_o_tipo(natureza, travada.tipo)

    alvos = list(
        NaturezaItemNFe.objects.select_for_update(of=("self",)).filter(
            escrituracao=travada, item_id__in=ids
        )
    )
    if len(alvos) != len(ids):
        raise EntradaInvalidaNFe("Algum item informado não pertence a esta nota.")
    antes = {a.item_id: a.natureza for a in alvos}
    NaturezaItemNFe.objects.filter(pk__in=[a.pk for a in alvos]).update(natureza=natureza)

    registrar(
        acao="escrituracao_nfe.natureza_definida",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "natureza": natureza,
            "itens": {
                str(item_id): {"antes": antes[item_id], "depois": natureza} for item_id in ids
            },
        },
    )
    return travada


@dataclass(frozen=True)
class _ConferenciaDaNota:
    soma_itens: Decimal
    receita_bruta: Decimal
    devolucao: Decimal
    valor_nf: Decimal


def _conferir_valores(documento, leitura, itens_e_naturezas) -> _ConferenciaDaNota:
    """Conferência da receita com a nota (HI-119). Divergência bloqueia com os valores.

    `itens_e_naturezas`: lista de (ItemNFe, natureza). Só `indTot` 1 entra na soma.
    """
    soma = Decimal("0.00")
    receita = Decimal("0.00")
    devolucao = Decimal("0.00")
    for item, natureza in itens_e_naturezas:
        if item.ind_tot != "1":
            continue
        soma += item.receita_bruta_item
        papel = papel_da_natureza_nfe(natureza)
        if papel == "receita":
            receita += item.receita_bruta_item
        elif papel == "deducao":
            devolucao += item.receita_bruta_item

    if documento.v_nf is None:
        raise EscrituracaoNFeErro(
            "A nota não tem o valor total (vNF): não há como conferir a receita. Nota bloqueada."
        )
    v_st = documento.v_st or Decimal("0")
    v_ipi = documento.v_ipi or Decimal("0")
    v_ii = leitura.v_ii or Decimal("0")
    v_ipi_devol = leitura.v_ipi_devol or Decimal("0")
    esperado = documento.v_nf - v_st - v_ipi - v_ii - v_ipi_devol
    if soma != esperado:
        raise EscrituracaoNFeErro(
            f"Receita dos itens (R$ {soma:f}) diverge de vNF − vST − vIPI − vII − vIPIDevol "
            f"(R$ {esperado:f}): vNF {documento.v_nf:f}, vST {v_st:f}, vIPI {v_ipi:f}, "
            f"vII {v_ii:f}, vIPIDevol {v_ipi_devol:f}. A nota não é efetivada."
        )
    return _ConferenciaDaNota(soma, receita, devolucao, documento.v_nf)


@transaction.atomic
def efetivar(escrituracao: EscrituracaoNFe, usuario, request=None) -> EscrituracaoNFe:
    """Efetiva a escrituração. Idempotente: efetivada de novo, devolve a mesma, sem trilha nova.

    Exige: itens lidos, natureza em TODOS os itens e conferência com vNF. Efetivar em mês já
    confirmado reabre a confirmação e marca "a retificar" (DL-074, critério 6), na mesma transação.
    """
    empresa = receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado == EstadoEscrituracao.EFETIVADA:
        travada.criada_agora = False
        return travada
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise EscrituracaoNFeErro("Escrituração estornada não é efetivada: crie outro rascunho.")

    documento = travada.vinculo.documento
    if services.situacao_da_nfe(documento) == "cancelada":
        raise EscrituracaoNFeErro("Nota cancelada não pode ser efetivada.")
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    if leitura is None or leitura.estado != LeituraItensNFe.ESTADO_LIDA:
        motivo = "itens ainda não lidos" if leitura is None else leitura.motivo
        raise EscrituracaoNFeErro(f"Itens ilegíveis, nota bloqueada: {motivo}")

    pares = [
        (n.item, n.natureza)
        for n in NaturezaItemNFe.objects.select_related("item")
        .filter(escrituracao=travada)
        .order_by("item__n_item")
    ]
    faltam = [item for item, natureza in pares if not natureza]
    if not pares or faltam:
        raise EscrituracaoNFeErro(
            f"Falta a natureza de {len(faltam)} item(ns). "
            "Confirme a natureza de cada item antes de efetivar."
        )
    for _, natureza in pares:
        _validar_natureza_para_o_tipo(natureza, travada.tipo)

    conferencia = _conferir_valores(documento, leitura, pares)
    dia, competencia = dia_e_competencia(documento)
    agora = timezone.now()
    antes = _snapshot(travada)
    atualizadas = EscrituracaoNFe.objects.filter(
        pk=travada.pk, estado=EstadoEscrituracao.RASCUNHO
    ).update(
        estado=EstadoEscrituracao.EFETIVADA,
        efetivada_em=agora,
        efetivada_por=usuario,
        competencia=competencia,
        data_emissao=dia,
        valor_nf=conferencia.valor_nf,
        soma_itens=conferencia.soma_itens,
        receita_bruta=conferencia.receita_bruta,
        devolucao=conferencia.devolucao,
    )
    if atualizadas != 1:
        raise EscrituracaoNFeErro("A escrituração mudou enquanto era efetivada. Atualize a lista.")
    travada.refresh_from_db()
    travada.criada_agora = True

    registrar(
        acao="escrituracao_nfe.efetivada",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "antes": antes,
            "depois": _snapshot(travada),
            "naturezas": {str(item.pk): natureza for item, natureza in pares},
        },
    )
    marcar_a_retificar_do_mes(empresa, competencia, usuario, travada, request)
    return travada


def marcar_a_retificar_do_mes(empresa, competencia: date, usuario, escrituracao, request):
    """Gancho DL-074: a receita do mês mudou. Confirmação do mês vira "a retificar", se houver."""
    receita_servico.marcar_a_retificar(
        empresa,
        competencia.year,
        competencia.month,
        usuario,
        origem=f"escrituração de NF-e nº {escrituracao.pk}",
        motivo=(
            f"Efetivação de escrituração de NF-e nº {escrituracao.pk} em mês confirmado: "
            f"receita de {competencia.month:02d}/{competencia.year} a retificar."
        ),
        acao="receita_mensal.a_retificar_por_efetivacao",
        request=request,
    )


MENSAGEM_MOTIVO_OBRIGATORIO = "Informe o motivo do estorno."


@transaction.atomic
def estornar(escrituracao: EscrituracaoNFe, motivo: str, usuario, request=None) -> EscrituracaoNFe:
    """Estorna uma escrituração efetivada, com motivo obrigatório. A linha não é apagada."""
    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise EntradaInvalidaNFe(MENSAGEM_MOTIVO_OBRIGATORIO)
    if len(motivo_limpo) > MOTIVO_MAXIMO:
        raise EntradaInvalidaNFe(f"O motivo do estorno tem no máximo {MOTIVO_MAXIMO} caracteres.")

    empresa = receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("empresa__escritorio")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.EFETIVADA:
        raise EscrituracaoNFeErro(
            "Só escrituração efetivada pode ser estornada; esta está "
            f"'{travada.get_estado_display()}'."
        )
    antes = _snapshot(travada)
    atualizadas = EscrituracaoNFe.objects.filter(
        pk=travada.pk, estado=EstadoEscrituracao.EFETIVADA
    ).update(
        estado=EstadoEscrituracao.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario,
        motivo_estorno=motivo_limpo,
    )
    if atualizadas != 1:
        raise EscrituracaoNFeErro("A escrituração mudou enquanto era estornada. Atualize a lista.")
    travada.refresh_from_db()
    registrar(
        acao="escrituracao_nfe.estornada",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={"vinculo_id": travada.vinculo_id, "antes": antes, "depois": _snapshot(travada)},
    )
    receita_servico.marcar_a_retificar_por_estorno(
        empresa,
        travada.competencia.year,
        travada.competencia.month,
        usuario,
        origem=f"escrituração de NF-e nº {travada.pk}",
        request=request,
    )
    return travada


# ---------------------------------------------------------------------------
# Reclassificação em massa (DL-081, item 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FiltrosReclassificacao:
    """Filtros da reclassificação. Todos opcionais, combinados por E."""

    inicio: date | None = None
    fim: date | None = None
    cfop: str | None = None
    cst_csosn: str | None = None
    ncm: str | None = None


@dataclass(frozen=True)
class ResultadoReclassificacao:
    natureza: str
    escrituracoes_afetadas: int
    itens_alterados: int


def _itens_que_casam(empresa, filtros: FiltrosReclassificacao, escrituracoes):
    """Naturezas por item que casam com os filtros, só nas escriturações dadas (já travadas)."""
    qs = NaturezaItemNFe.objects.filter(
        escrituracao__in=escrituracoes,
        escrituracao__empresa=empresa,
        item__documento__escritorio=empresa.escritorio,
    ).select_related("item", "escrituracao")
    if filtros.inicio is not None:
        qs = qs.filter(
            item__documento__dh_emissao__gte=datetime(
                filtros.inicio.year, filtros.inicio.month, filtros.inicio.day, tzinfo=FUSO_SP
            )
        )
    if filtros.fim is not None:
        proximo = date.fromordinal(filtros.fim.toordinal() + 1)
        qs = qs.filter(
            item__documento__dh_emissao__lt=datetime(
                proximo.year, proximo.month, proximo.day, tzinfo=FUSO_SP
            )
        )
    if filtros.cfop is not None:
        qs = qs.filter(item__cfop=filtros.cfop)
    if filtros.cst_csosn is not None:
        qs = qs.filter(Q(item__csosn=filtros.cst_csosn) | Q(item__cst=filtros.cst_csosn))
    if filtros.ncm is not None:
        qs = qs.filter(item__ncm=filtros.ncm)
    return qs


@transaction.atomic
def reclassificar_em_massa(
    empresa, natureza: str, filtros: FiltrosReclassificacao, usuario, request=None
) -> ResultadoReclassificacao:
    """Troca a natureza dos itens que casam com os filtros, SÓ em rascunho, com trilha por nota.

    Nunca toca efetivada nem estornada, e nunca nota de outra empresa ou de outro escritório
    (filtros de empresa e de escritório, e a trava nas escriturações). Se algum item que casa
    pertence a nota cujo tipo não aceita a natureza, a operação inteira é recusada e nada muda.
    """
    if not natureza or natureza not in CATALOGO_NATUREZA_NFE:
        raise EntradaInvalidaNFe("Escolha a natureza da operação.")
    empresa = receita_servico.travar_empresa(empresa)

    candidatas = list(
        EscrituracaoNFe.objects.filter(
            empresa=empresa,
            estado=EstadoEscrituracao.RASCUNHO,
            vinculo__documento__escritorio=empresa.escritorio,
        ).values_list("pk", flat=True)
    )
    travadas = list(
        EscrituracaoNFe.objects.select_for_update(of=("self",)).filter(
            pk__in=candidatas, estado=EstadoEscrituracao.RASCUNHO
        )
    )
    casamentos = _itens_que_casam(empresa, filtros, travadas)
    por_escrituracao: dict[int, list[NaturezaItemNFe]] = {}
    for registro in casamentos:
        por_escrituracao.setdefault(registro.escrituracao_id, []).append(registro)

    travadas_por_id = {e.pk: e for e in travadas}
    for escrituracao_id in por_escrituracao:
        tipo = travadas_por_id[escrituracao_id].tipo
        if natureza not in naturezas_permitidas(tipo):
            raise EntradaInvalidaNFe(
                "Esta natureza não cabe em alguma das notas que casam com o filtro "
                f"({len(por_escrituracao)} nota(s) no conjunto). Nada foi alterado."
            )

    afetadas = 0
    itens_alterados = 0
    for escrituracao_id, registros in sorted(por_escrituracao.items()):
        alterar = [r for r in registros if r.natureza != natureza]
        if not alterar:
            continue
        antes = {r.item_id: r.natureza for r in alterar}
        NaturezaItemNFe.objects.filter(pk__in=[r.pk for r in alterar]).update(natureza=natureza)
        afetadas += 1
        itens_alterados += len(alterar)
        escrituracao = travadas_por_id[escrituracao_id]
        registrar(
            acao="escrituracao_nfe.reclassificada",
            usuario=usuario,
            escritorio=empresa.escritorio,
            objeto=escrituracao,
            request=request,
            detalhes={
                "natureza": natureza,
                "filtros": {
                    "inicio": filtros.inicio.isoformat() if filtros.inicio else None,
                    "fim": filtros.fim.isoformat() if filtros.fim else None,
                    "cfop": filtros.cfop,
                    "cst_csosn": filtros.cst_csosn,
                    "ncm": filtros.ncm,
                },
                "itens": {
                    str(item_id): {"antes": nat, "depois": natureza}
                    for item_id, nat in antes.items()
                },
            },
        )
    return ResultadoReclassificacao(natureza, afetadas, itens_alterados)


# ---------------------------------------------------------------------------
# Avisos de IBS/CBS (DL-081, item 6; HI-123). Nada disso entra na receita.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AvisoNFe:
    codigo: str
    mensagem: str
    dispositivo: str


_DISP_IBSCBS = "LC 214/2025, art. 348, § 1º; consulta de 09/10/2026, item 6 (HI-123)"


def avisos_ibscbs(documento, leitura: LeituraItensNFe | None) -> tuple[AvisoNFe, ...]:
    """Avisos de 2026 sobre o grupo IBS/CBS. Só avisa: não bloqueia e não muda a receita.

    1. Grupo presente em nota de CRT 1, 2 ou 4 com emissão em 2026.
    2. Grupo ausente em nota de CRT 3 emitida a partir de 03/08/2026.
    3. `vNFTot` diferente de `vNF + vIBS + vCBS + vIS`. Ausente nesta fórmula vale zero, por ser
       tributo que pode não existir na nota. Sem vNF, não há como conferir: não avisa.
    """
    avisos: list[AvisoNFe] = []
    dia = documento.dh_emissao.astimezone(FUSO_SP).date()
    presente = bool(documento.tem_ibscbs_total or documento.tem_ibscbs_item)
    crt = documento.emitente_crt
    if presente and crt in ("1", "2", "4") and dia.year == 2026:
        avisos.append(
            AvisoNFe(
                "ibscbs_presente_em_crt_1_2_4",
                f"Grupo IBS/CBS presente em nota de CRT {crt} emitida em 2026: conferir.",
                _DISP_IBSCBS,
            )
        )
    if not presente and crt == "3" and dia >= date(2026, 8, 3):
        avisos.append(
            AvisoNFe(
                "ibscbs_ausente_em_crt_3",
                "Grupo IBS/CBS ausente em nota de CRT 3 emitida a partir de 03/08/2026: conferir.",
                _DISP_IBSCBS,
            )
        )
    if leitura is not None and leitura.v_nf_tot is not None and documento.v_nf is not None:
        esperado = (
            documento.v_nf
            + (leitura.v_ibs or Decimal("0"))
            + (leitura.v_cbs or Decimal("0"))
            + (leitura.v_is or Decimal("0"))
        )
        if leitura.v_nf_tot != esperado:
            avisos.append(
                AvisoNFe(
                    "vnftot_incoerente",
                    f"vNFTot ({leitura.v_nf_tot:f}) diferente de vNF + vIBS + vCBS + vIS "
                    f"({esperado:f}): conferir.",
                    _DISP_IBSCBS,
                )
            )
    return tuple(avisos)


# ---------------------------------------------------------------------------
# Conferência do mês (DL-081, item 9 e API)
# ---------------------------------------------------------------------------


@dataclass
class ConferenciaDoMes:
    ano: int
    mes: int
    recebidas: int = 0
    escrituradas: int = 0
    pendentes: int = 0
    canceladas: int = 0
    escrituradas_canceladas: int = 0
    itens_sem_sugestao: int = 0
    receita_por_natureza: dict = field(default_factory=dict)
    receita_por_cfop: dict = field(default_factory=dict)
    nao_elegiveis: int = 0


def conferencia_do_mes(empresa, ano: int, mes: int) -> ConferenciaDoMes:
    """Conferência do mês: recebidas × escrituradas × pendentes, receita por natureza e CFOP,
    canceladas, escrituradas que foram canceladas depois, e itens sem sugestão.

    Receita por natureza mostra o valor de cada natureza; a soma da receita (`receita_por_natureza`
    com papel "receita", menos a dedução) é a receita do mês. Natureza que não é receita aparece
    à parte, com soma zero (HI-124)."""
    resultado = ConferenciaDoMes(ano=ano, mes=mes)
    for nota in notas_do_mes(empresa, ano, mes):
        if nota.tipo is None:
            resultado.nao_elegiveis += 1
            continue
        resultado.recebidas += 1
        if nota.situacao == SITUACAO_EFETIVADA:
            resultado.escrituradas += 1
        elif nota.situacao == SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA:
            resultado.escrituradas_canceladas += 1
            resultado.canceladas += 1
        elif nota.situacao == SITUACAO_CANCELADA:
            resultado.canceladas += 1
        else:
            resultado.pendentes += 1
        if nota.leitura_estado == LeituraItensNFe.ESTADO_LIDA:
            resultado.itens_sem_sugestao += _itens_sem_sugestao_da_nota(nota)
    _preencher_receita(empresa, ano, mes, resultado)
    return resultado


def _itens_sem_sugestao_da_nota(nota: NotaDoMes) -> int:
    """Itens da nota sem sugestão de natureza (em nota ainda não efetivada)."""
    if nota.situacao not in (SITUACAO_A_ESCRITURAR, SITUACAO_RASCUNHO):
        return 0
    return sum(
        1
        for item in ItemNFe.objects.filter(documento=nota.documento)
        if sugerir_natureza_item(nota.documento, item, nota.tipo).natureza is None
    )


def _preencher_receita(empresa, ano: int, mes: int, resultado: ConferenciaDoMes) -> None:
    """Receita por natureza e por CFOP, das escriturações efetivadas do mês, sem canceladas."""
    inicio = date(ano, mes, 1)
    proximo = receita_servico._proximo_mes(ano, mes)
    itens = (
        NaturezaItemNFe.objects.select_related("item")
        .filter(
            escrituracao__empresa=empresa,
            escrituracao__estado=EstadoEscrituracao.EFETIVADA,
            escrituracao__competencia__gte=inicio,
            escrituracao__competencia__lt=proximo,
            item__ind_tot="1",
        )
        .exclude(natureza="")
        .filter(~Exists(receita_servico._cancelada_depois_de_escriturada("escrituracao__")))
    )
    por_natureza: dict[str, dict] = {}
    por_cfop: dict[str, Decimal] = {}
    for registro in itens:
        natureza = registro.natureza
        papel = papel_da_natureza_nfe(natureza)
        valor = registro.item.receita_bruta_item
        linha = por_natureza.setdefault(
            natureza,
            {
                "papel": papel,
                "mercado": mercado_da_natureza_nfe(natureza),
                "bruto": Decimal("0.00"),
                "soma_na_receita": Decimal("0.00"),
            },
        )
        linha["bruto"] += valor
        if papel == "receita":
            linha["soma_na_receita"] += valor
        elif papel == "deducao":
            linha["soma_na_receita"] -= valor
        por_cfop[registro.item.cfop] = por_cfop.get(registro.item.cfop, Decimal("0.00")) + valor
    resultado.receita_por_natureza = por_natureza
    resultado.receita_por_cfop = por_cfop
