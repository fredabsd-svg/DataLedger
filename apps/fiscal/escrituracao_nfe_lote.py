"""Escrituração de NF-e e NFC-e em lote — DL-085, frente A (RC-173).

Plano: docs/planos/DL-085-escrituracao-de-nfe-em-volume.md. A escrituração nota a nota (DL-081) não
fecha o mês de um posto, que emite milhares de NFC-e. Este módulo agrupa as notas pendentes, deixa o
contador confirmar cada grupo e efetiva em partes.

REGRA DE NÃO ATALHO: o lote não tem regra própria. Cada nota passa por `criar_rascunho`,
`definir_natureza` e `efetivar`, as MESMAS funções da escrituração individual, com as
mesmas recusas,
a mesma conferência W16 e a mesma trilha. O lote só decide QUAIS notas e QUAIS naturezas.

PRÉVIA (`previa_do_lote`)
- Notas: `notas_do_mes`, com tipo elegível e situação a escriturar ou em rascunho. Efetivadas e
  canceladas não entram na prévia: entram só na contagem.
- Ordem das recusas, a MESMA de `efetivar`: 2027 (HI-133); itens ilegíveis; leitura de versão
  anterior; item sem sugestão ou em conflito; atribuição do resíduo (HI-138); nota sem vNF; W16
  (HI-119). A W16 roda com as naturezas SUGERIDAS e sem gravar nada. Nota em rascunho com
  natureza já escolhida pelo contador, diferente da sugestão, sai com `natureza_escolhida`: o lote
  nunca sobrescreve a escolha (DL-085, A2).
- Leitura de itens: a prévia NÃO lê XML. A nota sem leitura atual (nunca lida, ou de versão
  anterior e ainda não rascunho) vai para `a_ler`, e `ler_notas_do_mes` a lê em partes (endpoint
  próprio, mesmo desenho das partes de efetivação). Nota em rascunho com leitura antiga sai do lote
  com o motivo: a releitura apagaria as naturezas já escolhidas, e a escrituração individual a relê.
- Chave do grupo: hash curto de (tipo da nota, conjunto ordenado e SEM repetição de
  (CFOP, CST ou CSOSN, natureza sugerida) dos itens). Notas com o mesmo conjunto de assinaturas caem
  no mesmo grupo. A natureza entra na chave: duas notas com o mesmo CFOP e CST, mas naturezas
  sugeridas diferentes (por exemplo, NCM de combustível diferente), caem em grupos diferentes.
- Assinatura da prévia: SHA-256 sobre (empresa, ano, mês) e, para cada grupo em ordem de chave, a
  lista ordenada de (vínculo, [(item, natureza sugerida)]) e a lista dos vínculos de `a_ler`. Muda
  com qualquer nota que entra ou sai, com qualquer item relido (o id muda) e com qualquer sugestão
  que muda. Não cobre as recusas: uma
  nota que muda de recusa para sugestão entra na próxima prévia, e aí muda a assinatura.

CONFIRMAÇÃO (`confirmar_lote`)
- A primeira chamada recalcula a prévia dentro da trava da empresa. Se a assinatura não bate, recusa
  com `PreviaDesatualizada` (409), sem gravar nada. Se bate, grava o LOTE: o conjunto de notas, as
  naturezas FIXADAS de cada item (sugerida e escolhida), quem confirmou e a trilha do lote.
- Por que o conjunto é gravado: depois da primeira parte, as notas efetivadas saem da prévia e a
  assinatura muda. Sem o registro do conjunto, a parte seguinte não saberia quais notas o contador
  confirmou. As partes seguintes referem o lote pelo id e não recalculam a prévia.
- Escolhas: por grupo, troca a natureza de uma assinatura (CFOP, CST/CSOSN, natureza sugerida) por
  outra natureza permitida para o tipo. Escolha que deixa nota sem fechar a W16 recusa a
  confirmação inteira (400), antes de gravar: nada é efetivado com natureza que o servidor sabe que
  não fecha.
- Repetição: com o mesmo lote em andamento, a confirmação com a mesma assinatura CONTINUA o
  lote; com outra assinatura, recusa com 409 (há lote em andamento deste mês). Lote concluído não
  processa nada.

PARTES (`_processar_parte`)
- Cada parte processa até `limite` notas pendentes, na ordem do vínculo. Cada nota tem a PRÓPRIA
  transação: trava a empresa (`travar_empresa`), trava a linha do lote, e então faz o trabalho. Uma
  nota que falha não desfaz as já efetivadas: ela vira `falhou`, com o motivo, e a parte segue.
- Idempotência: a linha `pendente` é a única que a parte processa. Se a escrituração da nota já está
  efetivada (por outra ação, ou por uma parte que caiu antes de gravar a linha), a linha vira
  `ja_efetivada` e nenhuma escrituração nova é criada. Efetivar de novo continua idempotente.
- Nota estornada DEPOIS da confirmação do lote não é reefetivada pelo lote: o estorno foi uma
  decisão posterior, e o lote falha a nota com motivo. Estorno anterior à confirmação é pendência
  normal (a prévia já a mostrava).
- Desvio desde a confirmação: antes de gravar, a parte compara os itens e as sugestões de hoje com
  os gravados. Se mudaram (nota relida, sugestão nova), a nota falha e refaz-se a prévia.
- Mês já confirmado vira "a retificar" dentro da própria `efetivar` (DL-074), por nota.

TRILHA
- `escrituracao_nfe.lote_confirmado`: na criação. Quem confirmou, a assinatura, as quantidades e,
  por grupo, as notas, os itens, a receita, a devolução e as naturezas fixadas.
- `escrituracao_nfe.lote_parte`: a cada parte que processou nota (efetivadas, puladas e falhas).
- `escrituracao_nfe.lote_concluido`: quando não resta nota pendente.
- A trilha de CADA nota é a da escrituração individual (`criar_rascunho`, `definir_natureza`,
  `efetivar`), na mesma transação da nota.

DESEMPENHO
- A prévia lê as notas de uma consulta (`notas_do_mes`) e os itens de uma consulta por lote de 5.000
  notas. Sem consulta por nota.
- A confirmação calcula a prévia ANTES de travar a empresa; dentro da trava só confere o lote em
  andamento e grava (reconferência, R1).
- O tamanho da parte (`LIMITE_PADRAO_DA_PARTE`) é medido, com os tempos no comentário da constante.
- Orçamento de tempo: cada parte (de efetivação e de leitura) para depois da nota em que o tempo
  decorrido passa de `ORCAMENTO_DA_PARTE_SEGUNDOS`. O que sobrou fica pendente, e `restam` (ou
  `restantes`) diz quanto. A chamada não depende só do número de notas.
- A prévia não lê XML. A leitura de uma nota nunca lida custa uma leitura de XML, e é feita em
  partes por `ler_notas_do_mes` (`LIMITE_PADRAO_DA_LEITURA`), não na prévia.
- Memória: as consultas da prévia e das partes não carregam `xml_original` (é adiado com `defer`),
  salvo na leitura, que precisa dele. Medida em `apps/fiscal/tests/test_dl085_memoria.py`.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from django.db import DatabaseError, OperationalError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.core.restricoes import RestricaoViolada, mensagens_de, restricao_como_400
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.itens_nfe import (
    VERSAO_LEITOR_ITENS,
    ResiduoNaoAtribuivel,
    atribuir_receita_da_nota,
    ler_itens,
)
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    EscrituracaoNFe,
    EstadoEscrituracao,
    EstadoLoteEscrituracaoNFe,
    EstadoNotaDoLoteNFe,
    ItemNFe,
    LeituraItensNFe,
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
    NaturezaItemNFe,
    VinculoNFeEmpresa,
)

# Tamanho de cada parte, em notas por chamada (DL-085, item 3). Medido com 10.000 NFC-e de 1 a 5
# itens (`apps/fiscal/tests/test_dl085_volume.py`, com DL085_MEDIR_VOLUME=1): 99 partes de 100
# notas, de 3,8 s a 5,3 s (média 4,4 s). A primeira chamada (prévia do mês, criação do lote e a
# primeira parte) levou 7,9 s. O teto do servidor é de cerca de 30 s; a chamada deve caber em 10 s.
LIMITE_PADRAO_DA_PARTE = 100
# Teto que a API aceita por parte. A média medida é de 44 ms por nota: 150 notas dão cerca de 6,6 s,
# dentro do orçamento de tempo da parte. Acima disso, a parte come a folga do servidor.
LIMITE_MAXIMO_DA_PARTE = 150
# Tempo, em segundos, que uma parte (de efetivação ou de leitura) pode consumir. Passado o
# orçamento, a parte para depois da nota em que ele estourou; o resto fica pendente (DL-085, A6).
ORCAMENTO_DA_PARTE_SEGUNDOS = 10
# Relógio das partes. Injetável nos testes: o tempo do teste é controlado, não o do servidor.
_relogio = time.monotonic

ANO_MINIMO, ANO_MAXIMO = 1970, 2999
# Notas por consulta de itens. Mantém o `IN (...)` longe do limite de parâmetros do PostgreSQL.
_NOTAS_POR_CONSULTA_DE_ITENS = 5000
_CAMPOS_DO_ITEM = (
    "documento",
    "n_item",
    "cfop",
    "cst",
    "csosn",
    "ncm",
    "ind_tot",
    "v_prod",
    "v_desc",
    "v_frete",
    "v_seg",
    "v_outro",
    "v_icms_deson",
    "ind_deduz_deson",
)

# Códigos das recusas da prévia: a tela agrupa por eles.
CODIGO_2027 = "receita_2027"
CODIGO_SEM_LEITURA = "sem_leitura"
CODIGO_ILEGIVEL = "ilegivel"
CODIGO_LEITURA_ANTIGA = "leitura_antiga"
CODIGO_SEM_SUGESTAO = "sem_sugestao"
CODIGO_CONFLITO = "conflito"
CODIGO_ATRIBUICAO = "atribuicao"
CODIGO_SEM_VNF = "sem_vnf"
CODIGO_W16 = "w16"
CODIGO_CONFERENCIA = "conferencia"
CODIGO_NATUREZA_ESCOLHIDA = "natureza_escolhida"

MENSAGEM_SEM_VNF = "A nota não tem o valor total (vNF): não há como conferir a receita."
MENSAGEM_PREVIA_DESATUALIZADA = (
    "A prévia mudou desde que foi exibida: notas, itens ou sugestões são outros. Atualize a prévia "
    "e confirme de novo. Nada foi efetivado."
)
MENSAGEM_LOTE_EM_ANDAMENTO = (
    "Há um lote em andamento para este mês. Continue-o pelo lote_id, ou aguarde a conclusão. "
    "Nada foi efetivado nesta chamada."
)
MENSAGEM_ASSINATURA_DO_LOTE = (
    "A assinatura não é a do lote informado. Nada foi efetivado nesta chamada."
)
MENSAGEM_DESVIO = (
    "A nota mudou desde a confirmação do lote (itens ou sugestões). Atualize a prévia e confirme "
    "de "
    "novo."
)
MENSAGEM_ESTORNADA_DEPOIS = (
    "Escrituração estornada depois da confirmação do lote: o lote não a efetiva de novo. Escriture "
    "pela escrituração individual."
)
MENSAGEM_SEM_PENDENTES = "Não há nota pendente de escrituração neste mês."
MENSAGEM_NATUREZA_ESCOLHIDA = (
    "natureza já escolhida no rascunho: escriture esta nota individualmente"
)
# Estado devolvido por `_processar_nota` quando a linha já estava processada por OUTRA chamada (duas
# partes correndo ao mesmo tempo). Não é estado do banco, e não entra em `efetivadas` nem na trilha.
_OUTRA_CHAMADA = "outra_chamada"
# Deadlock do PostgreSQL (SQLSTATE 40P01): o banco desfaz a transação da vítima por inteiro. A nota
# é tentada de novo, sem estado parcial. Três tentativas bastam: o outro lado termina na primeira.
_TENTATIVAS_POR_DEADLOCK = 3
_SQLSTATE_DEADLOCK = "40P01"
MENSAGEM_ESCOLHA_SEM_CONFERENCIA = (
    "Com a natureza escolhida, a nota {numero} não fecha a conferência: {motivo}. Nada foi "
    "efetivado; escolha outra natureza."
)


class PreviaDesatualizada(servico.EscrituracaoNFeErro):
    """A assinatura não bate com a prévia de agora. A API traduz em 409 (DL-085, item 2)."""


class LoteNaoEncontrado(Exception):
    """Lote que não existe nesta empresa. A API traduz em 404 (não é `LookupError`: um `KeyError` de
    bug não pode virar 404 em silêncio)."""


class LoteEmAndamento(servico.EscrituracaoNFeErro):
    """Já há lote em andamento neste mês, e a chamada não continua esse lote. A API responde 409."""


# ---------------------------------------------------------------------------
# Resultado da prévia
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemDoLote:
    """Um item da nota na prévia: a natureza é a SUGERIDA. A escolha do contador vem depois."""

    item_id: int
    n_item: int
    cfop: str
    cst_csosn: str
    natureza_sugerida: str


@dataclass(frozen=True)
class AssinaturaDoItem:
    """Par (CFOP, CST ou CSOSN, natureza sugerida) de um grupo. A troca de natureza é por ele."""

    cfop: str
    cst_csosn: str
    natureza: str

    @property
    def id(self) -> str:
        return _id_da_assinatura(self.cfop, self.cst_csosn, self.natureza)


@dataclass(frozen=True)
class NotaDoLote:
    vinculo_id: int
    documento_id: int
    numero: str
    serie: str
    chave: str
    dh_emissao: datetime
    itens: tuple[ItemDoLote, ...]
    receita_bruta: Decimal
    devolucao: Decimal


@dataclass(frozen=True)
class GrupoDoLote:
    chave: str
    tipo: str
    assinaturas: tuple[AssinaturaDoItem, ...]
    notas: tuple[NotaDoLote, ...]

    @property
    def quantidade_notas(self) -> int:
        return len(self.notas)

    @property
    def quantidade_itens(self) -> int:
        return sum(len(nota.itens) for nota in self.notas)

    @property
    def receita_bruta(self) -> Decimal:
        return sum((nota.receita_bruta for nota in self.notas), Decimal("0.00"))

    @property
    def devolucao(self) -> Decimal:
        return sum((nota.devolucao for nota in self.notas), Decimal("0.00"))


@dataclass(frozen=True)
class ForaDoLote:
    vinculo_id: int
    documento_id: int
    numero: str
    serie: str
    dh_emissao: datetime
    codigo: str
    motivo: str
    # vNF da nota, como está no XML (None só se a nota não o tem: a recusa é "sem vNF").
    valor_nf: Decimal | None = None


@dataclass
class PreviaDoLote:
    empresa_id: int
    ano: int
    mes: int
    assinatura: str
    grupos: tuple[GrupoDoLote, ...]
    fora: tuple[ForaDoLote, ...]
    ja_efetivadas: int
    canceladas: int
    nao_elegiveis: int
    # Lote em andamento deste mês, se houver: a tela oferece continuar, e não recalcular.
    lote_em_andamento: LoteEscrituracaoNFe | None = None
    # Vínculos das notas SEM leitura atual: a prévia não as lê. Ficam fora dos grupos e da lista
    # "fora do lote", e entram na assinatura (a confirmação recusa se o conjunto mudou).
    a_ler: tuple[int, ...] = ()
    # Dados que a confirmação usa (documento, leitura e itens com objeto). Não entram na API.
    _candidatas: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class _Candidata:
    documento: object
    leitura: LeituraItensNFe
    tipo: str
    pares: tuple[tuple[ItemNFe, str | None], ...]


@dataclass(frozen=True)
class FalhaDaNota:
    vinculo_id: int
    motivo: str
    # Número e série da nota, para a tela mostrar a nota e não só o id do vínculo.
    numero: str = ""
    serie: str = ""


@dataclass(frozen=True)
class ProgressoDoLote:
    """O que uma chamada de confirmação devolve. `falhas_nesta_chamada` são só as desta chamada."""

    lote_id: int
    ano: int
    mes: int
    assinatura: str
    estado: str
    total_notas: int
    efetivadas_nesta_chamada: int
    ja_efetivadas_nesta_chamada: int
    falhas_nesta_chamada: tuple[FalhaDaNota, ...]
    restantes: int
    efetivadas_total: int
    ja_efetivadas_total: int
    falhas_total: int

    @property
    def terminou(self) -> bool:
        return self.estado == EstadoLoteEscrituracaoNFe.CONCLUIDO


@dataclass
class _Parte:
    efetivadas: list[int] = field(default_factory=list)
    ja_efetivadas: list[int] = field(default_factory=list)
    falhas: list[FalhaDaNota] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chaves, assinatura e helpers
# ---------------------------------------------------------------------------


def _cst_csosn(item) -> str:
    return item.csosn or item.cst or ""


def _id_da_assinatura(cfop: str, cst_csosn: str, natureza: str) -> str:
    """Identificador estável de um par de grupo. Vai na API e nas escolhas."""
    return f"{cfop}|{cst_csosn}|{natureza}"


def _chave_do_grupo(tipo: str, assinaturas: tuple[tuple[str, str, str], ...]) -> str:
    """Chave curta do grupo: hash do tipo e do conjunto de assinaturas, sem repetição."""
    texto = json.dumps([tipo, [list(a) for a in assinaturas]], separators=(",", ":"))
    return f"{tipo}-{hashlib.sha256(texto.encode('utf-8')).hexdigest()[:16]}"


def _assinatura_da_previa(empresa_id: int, ano: int, mes: int, grupos, a_ler) -> str:
    """SHA-256 da prévia. Ver a docstring do módulo: vínculo e item (pelo pk) com a sugestão."""
    corpo = {
        "empresa": empresa_id,
        "ano": ano,
        "mes": mes,
        "grupos": [
            [
                grupo.chave,
                [
                    [
                        nota.vinculo_id,
                        [[item.item_id, item.natureza_sugerida] for item in nota.itens],
                    ]
                    for nota in grupo.notas
                ],
            ]
            for grupo in grupos
        ],
    }
    # As notas ainda não lidas entram pelo vínculo: se uma nota entra ou sai desse conjunto sem ser
    # lida, a confirmação percebe a mudança, e não confirma um mês que o contador não viu inteiro.
    corpo["a_ler"] = sorted(a_ler)
    texto = json.dumps(corpo, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _validar_competencia(ano, mes) -> None:
    if isinstance(ano, bool) or not isinstance(ano, int) or not ANO_MINIMO <= ano <= ANO_MAXIMO:
        raise servico.EntradaInvalidaNFe(
            f"Ano inválido: deve estar entre {ANO_MINIMO} e {ANO_MAXIMO}."
        )
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise servico.EntradaInvalidaNFe("Mês inválido: deve estar entre 1 e 12.")


def _validar_limite(limite) -> int:
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or not (1 <= limite <= LIMITE_MAXIMO_DA_PARTE)
    ):
        raise servico.EntradaInvalidaNFe(
            f"O tamanho da parte deve estar entre 1 e {LIMITE_MAXIMO_DA_PARTE} notas."
        )
    return limite


def _itens_dos_documentos(documento_ids) -> dict[int, list[ItemNFe]]:
    """Itens das notas, por documento, em consultas de `_NOTAS_POR_CONSULTA_DE_ITENS` notas."""
    ids = list(documento_ids)
    resultado: dict[int, list[ItemNFe]] = {}
    for inicio in range(0, len(ids), _NOTAS_POR_CONSULTA_DE_ITENS):
        bloco = ids[inicio : inicio + _NOTAS_POR_CONSULTA_DE_ITENS]
        consulta = (
            ItemNFe.objects.filter(documento_id__in=bloco)
            .only(*_CAMPOS_DO_ITEM)
            .order_by("documento_id", "n_item")
        )
        for item in consulta:
            resultado.setdefault(item.documento_id, []).append(item)
    return resultado


def _fora(nota: servico.NotaDoMes, codigo: str, motivo: str) -> ForaDoLote:
    documento = nota.documento
    return ForaDoLote(
        vinculo_id=nota.vinculo.pk,
        documento_id=documento.pk,
        numero=documento.numero,
        serie=documento.serie,
        dh_emissao=documento.dh_emissao,
        codigo=codigo,
        motivo=motivo,
        valor_nf=documento.v_nf,
    )


def _recusa_de_data(nota: servico.NotaDoMes) -> tuple[str, str] | None:
    """Nota de 2027 (HI-133). Primeira recusa, como em `efetivar`."""
    motivo = servico.motivo_bloqueio_efetivacao(nota.documento)
    return (CODIGO_2027, motivo) if motivo else None


def _conferencia_ou_recusa(documento, leitura, pares):
    """(conferência, None) quando a nota fecha; (None, (código, motivo)) quando não fecha.

    Mesma ordem de `efetivar`: atribuição, vNF, W16. Não grava nada.
    """
    try:
        atribuir_receita_da_nota(pares)
    except ResiduoNaoAtribuivel as exc:
        return None, (CODIGO_ATRIBUICAO, exc.motivo)
    if documento.v_nf is None:
        return None, (CODIGO_SEM_VNF, MENSAGEM_SEM_VNF)
    try:
        return servico.conferir_valores(documento, leitura, pares), None
    except servico.DivergenciaComVnf as exc:
        return None, (CODIGO_W16, exc.mensagem)
    except servico.EscrituracaoNFeErro as exc:
        return None, (CODIGO_CONFERENCIA, exc.mensagem)


def _lote_em_andamento(empresa, competencia: date) -> LoteEscrituracaoNFe | None:
    return LoteEscrituracaoNFe.objects.filter(
        empresa=empresa,
        competencia=competencia,
        estado=EstadoLoteEscrituracaoNFe.EM_ANDAMENTO,
    ).first()


def _lote_da_empresa(empresa, lote_id: int) -> LoteEscrituracaoNFe:
    """Lote desta empresa. Outro lote, ou lote inexistente, é `LoteNaoEncontrado` (a API: 404)."""
    lote = LoteEscrituracaoNFe.objects.filter(pk=lote_id, empresa=empresa).first()
    if lote is None:
        raise LoteNaoEncontrado()
    return lote


def _naturezas_dos_rascunhos(escrituracao_ids) -> dict[int, dict[int, str]]:
    """{escrituração: {item: natureza}} das naturezas JÁ GRAVADAS nos rascunhos (só as não vazias).

    Uma consulta para o mês inteiro: a prévia não paga uma consulta por nota.
    """
    ids = list(escrituracao_ids)
    gravadas: dict[int, dict[int, str]] = {}
    if not ids:
        return gravadas
    linhas = (
        NaturezaItemNFe.objects.filter(escrituracao_id__in=ids)
        .exclude(natureza="")
        .values_list("escrituracao_id", "item_id", "natureza")
    )
    for escrituracao_id, item_id, natureza in linhas:
        gravadas.setdefault(escrituracao_id, {})[item_id] = natureza
    return gravadas


def _diverge_do_rascunho(gravadas: dict[int, str], sugeridas) -> bool:
    """True se o rascunho já tem natureza escolhida que não é a sugerida de algum item.

    `sugeridas`: pares (item_id, natureza sugerida). Item sem natureza gravada não diverge: o
    rascunho sem escolha entra no lote como antes (DL-085, auditoria A2, opção (a)).
    """
    return any(gravadas.get(item_id) not in (None, sugerida) for item_id, sugerida in sugeridas)


# ---------------------------------------------------------------------------
# Prévia
# ---------------------------------------------------------------------------


def previa_do_lote(empresa, ano: int, mes: int) -> PreviaDoLote:
    """Prévia do mês em lote: grupos por assinatura, notas fora do lote com o motivo, e assinatura.

    Só lê o que já está no banco. Não lê XML: a nota ainda não lida fica em `a_ler`, e
    `ler_notas_do_mes` a lê em partes. Não efetiva nem grava nada.
    """
    _validar_competencia(ano, mes)
    aberto = _lote_em_andamento(empresa, date(ano, mes, 1))
    return _calcular(empresa, ano, mes, aberto)


def _calcular(empresa, ano: int, mes: int, aberto) -> PreviaDoLote:
    notas = servico.notas_do_mes(empresa, ano, mes)
    ja_efetivadas = canceladas = nao_elegiveis = 0
    pendentes: list[servico.NotaDoMes] = []
    for nota in notas:
        if nota.tipo is None:
            nao_elegiveis += 1
        elif nota.situacao == servico.SITUACAO_EFETIVADA:
            ja_efetivadas += 1
        elif nota.situacao in (
            servico.SITUACAO_CANCELADA,
            servico.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA,
        ):
            canceladas += 1
        else:
            pendentes.append(nota)

    fora: list[ForaDoLote] = []
    lidas: list[tuple[servico.NotaDoMes, LeituraItensNFe]] = []
    a_ler: list[int] = []
    for nota in pendentes:
        # Sem leitura atual, a prévia NÃO lê o XML (DL-085, leitura em partes): a nota vai para o
        # bloco "a ler", e `ler_notas_do_mes` a lê. Esta regra vem ANTES da de data, para a contagem
        # de "a ler" ser a mesma que a leitura percorre (inclusive a nota de 2027, que é lida e
        # depois recusada).
        if _sem_leitura_atual(nota):
            a_ler.append(nota.vinculo.pk)
            continue
        recusa = _recusa_de_data(nota)
        if recusa is not None:
            fora.append(_fora(nota, *recusa))
            continue
        leitura = nota.leitura
        if leitura is None:
            fora.append(_fora(nota, CODIGO_SEM_LEITURA, "itens ainda não lidos"))
            continue
        if leitura.estado != LeituraItensNFe.ESTADO_LIDA:
            fora.append(
                _fora(nota, CODIGO_ILEGIVEL, f"itens ilegíveis, nota bloqueada: {leitura.motivo}")
            )
            continue
        if leitura.versao_leitor != VERSAO_LEITOR_ITENS:
            fora.append(
                _fora(
                    nota,
                    CODIGO_LEITURA_ANTIGA,
                    "itens lidos por versão anterior do leitor: gere o rascunho de novo para "
                    "reler a nota",
                )
            )
            continue
        lidas.append((nota, leitura))

    gravadas_dos_rascunhos = _naturezas_dos_rascunhos(
        nota.escrituracao.pk for nota, _ in lidas if nota.escrituracao is not None
    )
    itens_das_notas = _itens_dos_documentos([nota.documento.pk for nota, _ in lidas])
    candidatas: dict[int, _Candidata] = {}
    acumulado: dict[tuple, list[NotaDoLote]] = {}
    for nota, leitura in lidas:
        documento = nota.documento
        pares: list[tuple[ItemNFe, str | None]] = []
        sem_sugestao: list[tuple[ItemNFe, str]] = []
        for item in itens_das_notas.get(documento.pk, ()):
            sugestao = servico.sugerir_natureza_item(documento, item, nota.tipo)
            pares.append((item, sugestao.natureza))
            if sugestao.natureza is None:
                sem_sugestao.append((item, sugestao.motivo))
        if sem_sugestao:
            item, motivo = sem_sugestao[0]
            # "conflito" é o texto da sugestão quando dois sinais discordam (sugerir_natureza_item)
            codigo = CODIGO_CONFLITO if motivo.startswith("conflito") else CODIGO_SEM_SUGESTAO
            extra = f" (e mais {len(sem_sugestao) - 1} item(ns))" if len(sem_sugestao) > 1 else ""
            fora.append(_fora(nota, codigo, f"item {item.n_item}: {motivo}{extra}"))
            continue
        # Rascunho com natureza escolhida pelo contador que difere da sugestão: não é sobrescrito em
        # silêncio. Sai do lote com o motivo (DL-085, auditoria A2, opção (a)).
        gravadas = (
            gravadas_dos_rascunhos.get(nota.escrituracao.pk, {})
            if nota.escrituracao is not None
            else {}
        )
        if _diverge_do_rascunho(gravadas, [(item.pk, natureza) for item, natureza in pares]):
            fora.append(_fora(nota, CODIGO_NATUREZA_ESCOLHIDA, MENSAGEM_NATUREZA_ESCOLHIDA))
            continue

        conferencia, recusa = _conferencia_ou_recusa(documento, leitura, pares)
        if recusa is not None:
            fora.append(_fora(nota, *recusa))
            continue

        itens_da_nota = tuple(
            ItemDoLote(item.pk, item.n_item, item.cfop, _cst_csosn(item), natureza)
            for item, natureza in pares
        )
        assinaturas = tuple(
            sorted({(i.cfop, i.cst_csosn, i.natureza_sugerida) for i in itens_da_nota})
        )
        candidatas[nota.vinculo.pk] = _Candidata(
            documento, leitura, nota.tipo, tuple((item, natureza) for item, natureza in pares)
        )
        nota_do_lote = NotaDoLote(
            vinculo_id=nota.vinculo.pk,
            documento_id=documento.pk,
            numero=documento.numero,
            serie=documento.serie,
            chave=documento.chave,
            dh_emissao=documento.dh_emissao,
            itens=itens_da_nota,
            receita_bruta=conferencia.receita_bruta,
            devolucao=conferencia.devolucao,
        )
        acumulado.setdefault((nota.tipo, assinaturas), []).append(nota_do_lote)

    grupos = []
    for (tipo, assinaturas), notas_do_grupo in acumulado.items():
        grupos.append(
            GrupoDoLote(
                chave=_chave_do_grupo(tipo, assinaturas),
                tipo=tipo,
                assinaturas=tuple(
                    sorted((AssinaturaDoItem(*a) for a in assinaturas), key=lambda a: a.id)
                ),
                notas=tuple(sorted(notas_do_grupo, key=lambda n: n.vinculo_id)),
            )
        )
    grupos.sort(key=lambda g: g.chave)
    return PreviaDoLote(
        empresa_id=empresa.pk,
        ano=ano,
        mes=mes,
        assinatura=_assinatura_da_previa(empresa.pk, ano, mes, grupos, a_ler),
        grupos=tuple(grupos),
        fora=tuple(sorted(fora, key=lambda f: f.vinculo_id)),
        ja_efetivadas=ja_efetivadas,
        canceladas=canceladas,
        nao_elegiveis=nao_elegiveis,
        lote_em_andamento=aberto,
        a_ler=tuple(sorted(a_ler)),
        _candidatas=candidatas,
    )


# ---------------------------------------------------------------------------
# Leitura em partes (DL-085): o XML de cada nota é lido por um endpoint próprio, não pela prévia.
# ---------------------------------------------------------------------------

# Notas por parte da leitura. Medida em 10.000 NFC-e (test_dl085_volume.py): 25 partes de 400 notas,
# de 5,01 s a 5,61 s (média 5,22 s), ou ~13 ms por nota. Dentro do orçamento de tempo da parte
# (`ORCAMENTO_DA_PARTE_SEGUNDOS`, 10 s); o teto do servidor é de cerca de 30 s.
LIMITE_PADRAO_DA_LEITURA = 400
LIMITE_MAXIMO_DA_LEITURA = 800


@dataclass(frozen=True)
class FalhaDeLeitura:
    vinculo_id: int
    motivo: str


@dataclass(frozen=True)
class LeituraDoMes:
    """Uma parte da leitura. `restam` conta também as notas que falharam (ainda não lidas)."""

    ano: int
    mes: int
    lidas_nesta_chamada: int
    ilegiveis_nesta_chamada: int
    falhas_nesta_chamada: tuple[FalhaDeLeitura, ...]
    restam: int

    @property
    def terminou(self) -> bool:
        return self.restam == 0


def _sem_leitura_atual(nota: servico.NotaDoMes) -> bool:
    """Nota a escriturar sem leitura da versão atual do leitor. A prévia a põe em "a ler"."""
    return nota.situacao == servico.SITUACAO_A_ESCRITURAR and (
        nota.leitura is None or nota.leitura.versao_leitor != VERSAO_LEITOR_ITENS
    )


def _validar_limite_leitura(limite) -> int:
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or not (1 <= limite <= LIMITE_MAXIMO_DA_LEITURA)
    ):
        raise servico.EntradaInvalidaNFe(
            f"O tamanho da parte de leitura deve estar entre 1 e {LIMITE_MAXIMO_DA_LEITURA} notas."
        )
    return limite


def ler_notas_do_mes(
    empresa, ano: int, mes: int, limite: int = LIMITE_PADRAO_DA_LEITURA
) -> LeituraDoMes:
    """Lê até `limite` notas do mês sem leitura atual, em ordem de vínculo.

    - Cada nota é lida na própria transação (`ler_itens`). Uma falha de banco numa nota não
      derruba as outras: ela fica em `falhas_nesta_chamada` e continua em `restam`.
    - Ilegível é resultado, não erro: a nota vira ilegível e sai da conta de "a ler".
    - Idempotente: a nota já lida não é tocada (`ler_itens` devolve a leitura atual). Repetir a
      chamada lê o que sobrou e nunca duplica item.
    - Orçamento de tempo: passado `ORCAMENTO_DA_PARTE_SEGUNDOS`, a parte para antes da nota
      seguinte. O que sobra fica em `restam`.
    - Só lê. Não cria escrituração, rascunho nem lote.
    """
    _validar_competencia(ano, mes)
    limite = _validar_limite_leitura(limite)
    pendentes = sorted(
        (nota for nota in servico.notas_do_mes(empresa, ano, mes) if _sem_leitura_atual(nota)),
        key=lambda nota: nota.vinculo.pk,
    )
    lidas = ilegiveis = 0
    falhas: list[FalhaDeLeitura] = []
    inicio = _relogio()
    for indice, nota in enumerate(pendentes[:limite]):
        if indice and _relogio() - inicio >= ORCAMENTO_DA_PARTE_SEGUNDOS:
            break
        try:
            with transaction.atomic():
                leitura = ler_itens(nota.documento)
        except DatabaseError as exc:
            falhas.append(
                FalhaDeLeitura(
                    nota.vinculo.pk,
                    f"erro de banco ao ler os itens ({type(exc).__name__}): tente de novo",
                )
            )
            continue
        if leitura.versao_leitor != VERSAO_LEITOR_ITENS:
            # Leitura de versão anterior que o leitor não refez (nota com escrituração estornada):
            # não é "lida" para a conta, e fica em falha com o motivo.
            falhas.append(
                FalhaDeLeitura(nota.vinculo.pk, "leitura de versão anterior não pôde ser refeita")
            )
        elif leitura.estado == LeituraItensNFe.ESTADO_LIDA:
            lidas += 1
        else:
            ilegiveis += 1
    return LeituraDoMes(
        ano=ano,
        mes=mes,
        lidas_nesta_chamada=lidas,
        ilegiveis_nesta_chamada=ilegiveis,
        falhas_nesta_chamada=tuple(falhas),
        restam=len(pendentes) - lidas - ilegiveis,
    )


# ---------------------------------------------------------------------------
# Escolhas e fixação das naturezas
# ---------------------------------------------------------------------------


def _natureza_final(escolhas: dict, chave_grupo: str, cfop: str, cst_csosn: str, sugerida: str):
    """A natureza que a nota recebe: a escolhida para a assinatura do grupo, ou a sugerida."""
    return escolhas.get(chave_grupo, {}).get(_id_da_assinatura(cfop, cst_csosn, sugerida), sugerida)


def _normalizar_escolhas(escolhas: dict | None) -> dict[str, dict[str, str]]:
    """Tira da escolha o que é igual à sugestão. O id da assinatura termina na natureza sugerida.

    Não precisa da prévia: serve para comparar a repetição da confirmação com o lote gravado.
    """
    normalizadas: dict[str, dict[str, str]] = {}
    for chave_grupo, trocas in (escolhas or {}).items():
        for id_da_assinatura, natureza in trocas.items():
            if natureza != id_da_assinatura.rsplit("|", 1)[-1]:
                normalizadas.setdefault(chave_grupo, {})[id_da_assinatura] = natureza
    return normalizadas


def _escolhas_validas(previa: PreviaDoLote, escolhas: dict) -> dict[str, dict[str, str]]:
    """Confere as escolhas contra a prévia e o tipo de nota. Guarda só as que trocam a sugestão.

    `escolhas`: {chave_do_grupo: {id_da_assinatura: natureza}}. Escolha igual à sugestão não é
    gravada, para a trilha mostrar só o que o contador mudou.
    """
    grupos = {grupo.chave: grupo for grupo in previa.grupos}
    normalizadas: dict[str, dict[str, str]] = {}
    for chave_grupo, trocas in escolhas.items():
        grupo = grupos.get(chave_grupo)
        if grupo is None:
            raise servico.EntradaInvalidaNFe(
                "Grupo de escolha desconhecido: a prévia não tem este grupo. Confira a prévia."
            )
        sugeridas = {assinatura.id: assinatura.natureza for assinatura in grupo.assinaturas}
        for id_da_assinatura, natureza in trocas.items():
            if id_da_assinatura not in sugeridas:
                raise servico.EntradaInvalidaNFe("Item de escolha fora do grupo: confira a prévia.")
            # Não ecoa o valor enviado: ele vem do cliente.
            if (
                natureza not in CATALOGO_NATUREZA_NFE
                or natureza not in servico.naturezas_permitidas(grupo.tipo)
            ):
                raise servico.EntradaInvalidaNFe(
                    "Esta natureza não cabe neste grupo: escolha uma das opções do catálogo fiscal "
                    "para o tipo da nota."
                )
            if natureza != sugeridas[id_da_assinatura]:
                normalizadas.setdefault(chave_grupo, {})[id_da_assinatura] = natureza
    return normalizadas


def _fixar_naturezas(previa: PreviaDoLote, escolhas: dict) -> dict[int, list]:
    """Naturezas finais de cada nota, com a W16 simulada para as notas que a escolha mudou.

    Devolve {vinculo_id: [[item_id, sugerida, final], ...]}. Recusa (400) antes de gravar nada,
    se alguma escolha deixa uma nota sem fechar a atribuição ou a W16.
    """
    fixados: dict[int, list] = {}
    for grupo in previa.grupos:
        for nota in grupo.notas:
            candidata = previa._candidatas[nota.vinculo_id]
            itens = []
            finais = []
            mudou = False
            for item_do_lote, (item, sugerida) in zip(nota.itens, candidata.pares, strict=True):
                final = _natureza_final(
                    escolhas, grupo.chave, item_do_lote.cfop, item_do_lote.cst_csosn, sugerida
                )
                itens.append([item.pk, sugerida, final])
                finais.append((item, final))
                mudou = mudou or final != sugerida
            if mudou:
                _simular_conferencia(nota, candidata, finais)
            fixados[nota.vinculo_id] = itens
    return fixados


def _simular_conferencia(nota: NotaDoLote, candidata: _Candidata, finais) -> None:
    """Recusa a escolha que deixa a nota sem fechar a conferência. Não grava nada."""
    _conferencia, recusa = _conferencia_ou_recusa(candidata.documento, candidata.leitura, finais)
    if recusa is not None:
        _codigo, motivo = recusa
        raise servico.EntradaInvalidaNFe(
            MENSAGEM_ESCOLHA_SEM_CONFERENCIA.format(numero=nota.numero, motivo=motivo)
        )


def _detalhes_dos_grupos(previa: PreviaDoLote, escolhas: dict) -> list[dict]:
    """Quantidades, receita e naturezas FIXADAS de cada grupo, para a trilha do lote."""
    detalhes = []
    for grupo in previa.grupos:
        detalhes.append(
            {
                "chave": grupo.chave,
                "tipo": grupo.tipo,
                "notas": grupo.quantidade_notas,
                "itens": grupo.quantidade_itens,
                "receita_bruta": format(grupo.receita_bruta, "f"),
                "devolucao": format(grupo.devolucao, "f"),
                "naturezas": {
                    a.id: _natureza_final(escolhas, grupo.chave, a.cfop, a.cst_csosn, a.natureza)
                    for a in grupo.assinaturas
                },
            }
        )
    return detalhes


def _recorte_da_previa(previa: PreviaDoLote, grupos: list[str] | None) -> PreviaDoLote:
    """A prévia só com os grupos pedidos (DL-085, confirmação por grupo). `None` é a prévia inteira.

    A assinatura continua sendo a da prévia inteira: o recorte só decide quais notas entram no lote.
    Lista vazia e grupo que a prévia não tem são 400, nomeados, antes de qualquer gravação.
    """
    if grupos is None:
        return previa
    if not grupos:
        raise servico.EntradaInvalidaNFe(
            "Marque ao menos um grupo para confirmar. Nada foi efetivado."
        )
    existentes = {grupo.chave for grupo in previa.grupos}
    if set(grupos) - existentes:
        raise servico.EntradaInvalidaNFe(
            "Um dos grupos marcados não existe mais na prévia: atualize a prévia e confirme de "
            "novo. "
            "Nada foi efetivado."
        )
    pedidos = set(grupos)
    return replace(previa, grupos=tuple(g for g in previa.grupos if g.chave in pedidos))


def _grupos_do_lote(lote: LoteEscrituracaoNFe) -> set[str]:
    """Chaves dos grupos que o lote confirmou. Vêm das linhas de nota (cada uma tem o seu grupo)."""
    return set(
        LoteEscrituracaoNFeNota.objects.filter(lote=lote)
        .values_list("chave_grupo", flat=True)
        .distinct()
    )


def _grupos_divergem(empresa, ano: int, mes: int, aberto, grupos: list[str] | None) -> bool:
    """Os grupos da repetição são os do lote em andamento? (DL-085, auditoria A4).

    `grupos` informado: tem de ser exatamente o conjunto gravado. `None` significa "a prévia
    inteira": então o lote só serve se nenhum grupo da prévia de agora ficou de fora dele.
    """
    gravados = _grupos_do_lote(aberto)
    if grupos is not None:
        return set(grupos) != gravados
    previa = _calcular(empresa, ano, mes, aberto)
    return any(grupo.chave not in gravados for grupo in previa.grupos)


def _criar_lote(
    empresa,
    ano: int,
    mes: int,
    assinatura: str,
    escolhas: dict,
    usuario,
    request,
    grupos: list[str] | None = None,
    previa_inteira=None,
) -> LoteEscrituracaoNFe:
    """Grava o lote: o conjunto de notas, as naturezas fixadas e a trilha. Dentro da trava da
    empresa.

    `previa_inteira` vem calculada ANTES da trava (reconferência da DL-085, R1): a prévia de um mês
    com milhares de notas leva segundos, e segurar a trava da empresa por esse tempo fazia a
    recepção e a escrituração individual da mesma empresa caírem por `lock_timeout`. Calcular fora
    é seguro: a assinatura é conferida contra essa prévia, e cada nota é revalidada na sua parte
    (desvio desde a confirmação recusa a nota com o motivo)."""
    if previa_inteira is None:
        previa_inteira = _calcular(empresa, ano, mes, None)
    if previa_inteira.assinatura != assinatura:
        raise PreviaDesatualizada(MENSAGEM_PREVIA_DESATUALIZADA)
    if not previa_inteira.grupos:
        raise servico.EntradaInvalidaNFe(MENSAGEM_SEM_PENDENTES)
    previa = _recorte_da_previa(previa_inteira, grupos)
    # Escolha de natureza de um grupo que NÃO entra no lote é recusada, não ignorada em silêncio.
    fora_do_recorte = set(escolhas) - {grupo.chave for grupo in previa.grupos}
    if fora_do_recorte & {grupo.chave for grupo in previa_inteira.grupos}:
        raise servico.EntradaInvalidaNFe(
            "Há escolha de natureza para um grupo que não está marcado. Marque o grupo ou tire a "
            "escolha. Nada foi efetivado."
        )
    escolhas_validas = _escolhas_validas(previa, escolhas)
    fixados = _fixar_naturezas(previa, escolhas_validas)

    # A trava da empresa e a checagem em `confirmar_lote` evitam a corrida. Se ela passar mesmo
    # assim (outra transação gravou um lote em andamento depois da checagem), a restrição do
    # banco a recusa, e o cliente recebe 400 com a mensagem de negócio, não 500 (registro em
    # apps/core/restricoes.py). O savepoint isola o IntegrityError para a transação de fora.
    try:
        with (
            transaction.atomic(),
            restricao_como_400(mensagens_de("lote_nfe_em_andamento_unico_por_mes")),
        ):
            lote = LoteEscrituracaoNFe.objects.create(
                escritorio=empresa.escritorio,
                empresa=empresa,
                competencia=date(ano, mes, 1),
                assinatura=assinatura,
                escolhas=escolhas_validas,
                quantidade_notas=sum(g.quantidade_notas for g in previa.grupos),
                quantidade_itens=sum(g.quantidade_itens for g in previa.grupos),
                criado_por=usuario,
            )
    except RestricaoViolada as exc:
        raise servico.EntradaInvalidaNFe(str(exc)) from exc
    LoteEscrituracaoNFeNota.objects.bulk_create(
        LoteEscrituracaoNFeNota(
            lote=lote,
            vinculo_id=nota.vinculo_id,
            chave_grupo=grupo.chave,
            itens=fixados[nota.vinculo_id],
        )
        for grupo in previa.grupos
        for nota in grupo.notas
    )
    registrar(
        acao="escrituracao_nfe.lote_confirmado",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=lote,
        request=request,
        detalhes={
            "lote_id": lote.pk,
            "competencia": f"{ano:04d}-{mes:02d}",
            "assinatura": assinatura,
            "quantidade_notas": lote.quantidade_notas,
            "quantidade_itens": lote.quantidade_itens,
            "escolhas": escolhas_validas,
            # Quais grupos foram confirmados. Os não marcados não têm nota no lote: ficam intactos.
            "grupos_confirmados": [grupo.chave for grupo in previa.grupos],
            "grupos": _detalhes_dos_grupos(previa, escolhas_validas),
        },
    )
    return lote


# ---------------------------------------------------------------------------
# Partes: efetivação nota a nota, pelas funções da escrituração individual
# ---------------------------------------------------------------------------


def _itens_do_documento(documento) -> list[ItemNFe]:
    return list(
        ItemNFe.objects.filter(documento=documento).only(*_CAMPOS_DO_ITEM).order_by("n_item")
    )


def _desvio_desde_a_confirmacao(linha: LoteEscrituracaoNFeNota) -> str | None:
    """Compara itens e sugestões de HOJE com os fixados. Diferente: a nota não é efetivada."""
    documento = linha.vinculo.documento
    tipo = servico.tipo_da_nota(documento, linha.vinculo.papel)
    atuais = [
        (item.pk, servico.sugerir_natureza_item(documento, item, tipo).natureza)
        for item in _itens_do_documento(documento)
    ]
    gravados = [(int(item_id), sugerida) for item_id, sugerida, _final in linha.itens]
    return None if atuais == gravados else MENSAGEM_DESVIO


def _por_natureza(itens) -> list[tuple[str, list[int]]]:
    """Itens por natureza final, na ordem da natureza. Um `definir_natureza` por natureza."""
    agrupado: dict[str, list[int]] = {}
    for item_id, _sugerida, natureza in itens:
        agrupado.setdefault(natureza, []).append(int(item_id))
    return sorted(agrupado.items())


def _gravar_estado(linha_id: int, estado: str, escrituracao=None, motivo: str = "") -> bool:
    """Muda o estado da linha SÓ se ainda estiver pendente. Devolve True se ESTA chamada a mudou.

    Não sobrescreve a parte concorrente: se outra chamada já processou a linha, o UPDATE não casa e
    devolve False (DL-085, auditoria A1). Quem chama conta só o que esta chamada gravou.
    """
    atualizadas = LoteEscrituracaoNFeNota.objects.filter(
        pk=linha_id, estado=EstadoNotaDoLoteNFe.PENDENTE
    ).update(
        estado=estado,
        escrituracao=escrituracao,
        motivo=motivo[:500],
        processada_em=timezone.now(),
    )
    return atualizadas == 1


def _marcar_sob_trava(linha_id: int, estado: str, escrituracao=None) -> None:
    """Grava o estado final de uma nota que ESTA transação travou. A linha tem de estar pendente:
    a trava garante isso. Se não estiver, é defeito, e a transação é desfeita (nada pela metade)."""
    if not _gravar_estado(linha_id, estado, escrituracao=escrituracao):
        raise RuntimeError(f"linha {linha_id} do lote mudou sob a trava: transação desfeita")


def _processar_nota(lote, linha_id: int, usuario, request, estornadas: set[int]) -> tuple[str, str]:
    """Uma nota, na PRÓPRIA transação. Nova tentativa se o banco desfizer a transação por deadlock.

    Desde o ajuste do arquiteto depois da correção (A5), a criação individual do rascunho trava a
    empresa antes do vínculo, na mesma ordem do lote, e o deadlock entre os dois caminhos não foi
    mais reproduzido (reconferência da DL-085). A nova tentativa fica como defesa: se o banco ainda
    escolher esta transação como vítima, repetir a nota é seguro, porque nada da tentativa foi
    gravado.
    """
    for tentativa in range(1, _TENTATIVAS_POR_DEADLOCK + 1):
        try:
            return _processar_nota_uma_vez(lote, linha_id, usuario, request, estornadas)
        except OperationalError as exc:
            causa = exc.__cause__
            deadlock = getattr(causa, "sqlstate", None) == _SQLSTATE_DEADLOCK
            if not deadlock or tentativa == _TENTATIVAS_POR_DEADLOCK:
                raise
    raise AssertionError("inalcançável: o laço sempre devolve ou levanta")


def _processar_nota_uma_vez(
    lote, linha_id: int, usuario, request, estornadas: set[int]
) -> tuple[str, str]:
    """Uma tentativa de `_processar_nota`. Devolve (estado final, motivo).

    Ordem das travas: a empresa, a linha do lote, o VÍNCULO e só então a escrituração (DL-085,
    auditoria A5), a mesma ordem da criação individual, que também trava a empresa primeiro (ajuste
    do arquiteto). `_processar_nota` ainda repete a nota num deadlock, como defesa. A recusa
    do serviço vira `falhou` fora da transação, para que o rollback não a
    apague.

    Se a linha já não está pendente (outra chamada a processou), devolve `_OUTRA_CHAMADA`: não é
    efetivação desta chamada e não entra na contagem nem na trilha.
    """
    try:
        with transaction.atomic():
            receita_servico.travar_empresa(lote.empresa)
            linha = (
                LoteEscrituracaoNFeNota.objects.select_for_update(of=("self",))
                .select_related("vinculo__documento")
                .defer("vinculo__documento__xml_original")
                .get(pk=linha_id)
            )
            if linha.estado != EstadoNotaDoLoteNFe.PENDENTE:
                return _OUTRA_CHAMADA, ""
            VinculoNFeEmpresa.objects.select_for_update(of=("self",)).only("pk").get(
                pk=linha.vinculo_id
            )
            ativa = (
                EscrituracaoNFe.objects.select_for_update(of=("self",))
                .filter(
                    vinculo_id=linha.vinculo_id,
                    estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
                )
                .first()
            )
            # Já efetivada (por outra ação, ou por uma parte que caiu antes de gravar a linha):
            # pula, sem criar escrituração nova. É a idempotência do lote.
            if ativa is not None and ativa.estado == EstadoEscrituracao.EFETIVADA:
                _marcar_sob_trava(linha.pk, EstadoNotaDoLoteNFe.JA_EFETIVADA, escrituracao=ativa)
                return EstadoNotaDoLoteNFe.JA_EFETIVADA, ""
            if linha.vinculo_id in estornadas:
                raise servico.EscrituracaoNFeErro(MENSAGEM_ESTORNADA_DEPOIS)
            desvio = _desvio_desde_a_confirmacao(linha)
            if desvio is not None:
                raise servico.EscrituracaoNFeErro(desvio)
            if ativa is not None:
                # Rascunho com natureza escolhida que difere da sugestão gravada: a nota não é
                # sobrescrita. É a mesma regra da prévia, revalidada no momento da efetivação.
                gravadas = _naturezas_dos_rascunhos([ativa.pk]).get(ativa.pk, {})
                sugeridas = [(int(item_id), sugerida) for item_id, sugerida, _final in linha.itens]
                if _diverge_do_rascunho(gravadas, sugeridas):
                    raise servico.EscrituracaoNFeErro(MENSAGEM_NATUREZA_ESCOLHIDA)

            escrituracao = servico.criar_rascunho(linha.vinculo, usuario=usuario, request=request)
            for natureza, ids in _por_natureza(linha.itens):
                servico.definir_natureza(
                    escrituracao, natureza, ids, usuario=usuario, request=request
                )
            escrituracao = servico.efetivar(escrituracao, usuario=usuario, request=request)
            _marcar_sob_trava(linha.pk, EstadoNotaDoLoteNFe.EFETIVADA, escrituracao=escrituracao)
            return EstadoNotaDoLoteNFe.EFETIVADA, ""
    except servico.EscrituracaoNFeErro as exc:
        motivo = exc.mensagem
    with transaction.atomic():
        if not _gravar_estado(linha_id, EstadoNotaDoLoteNFe.FALHOU, motivo=motivo):
            # A outra chamada já fechou a linha: a falha desta não é gravada por cima.
            return _OUTRA_CHAMADA, ""
    return EstadoNotaDoLoteNFe.FALHOU, motivo


def _processar_parte(lote, usuario, request, limite: int) -> _Parte:
    """Efetiva até `limite` notas pendentes, na ordem do vínculo, cada uma na própria transação.

    Para depois da nota em que o orçamento de tempo da parte (`ORCAMENTO_DA_PARTE_SEGUNDOS`)
    estoura. As notas que sobram ficam pendentes e a próxima parte as pega.
    """
    pendentes = list(
        LoteEscrituracaoNFeNota.objects.filter(lote=lote, estado=EstadoNotaDoLoteNFe.PENDENTE)
        .order_by("vinculo_id", "pk")
        .values_list("pk", "vinculo_id")[:limite]
    )
    parte = _Parte()
    if not pendentes:
        return parte
    # Número e série só das notas desta parte, numa consulta: a falha mostra a nota, não o id. O XML
    # não é carregado: a efetivação não o usa (a leitura já foi feita e gravada).
    documentos = {
        vinculo.pk: vinculo.documento
        for vinculo in VinculoNFeEmpresa.objects.select_related("documento")
        .defer("documento__xml_original")
        .filter(pk__in=[vinculo_id for _pk, vinculo_id in pendentes])
    }
    # Estornada DEPOIS da confirmação: o lote não a reefetiva (ver MENSAGEM_ESTORNADA_DEPOIS).
    estornadas = set(
        EscrituracaoNFe.objects.filter(
            vinculo_id__in=[vinculo for _pk, vinculo in pendentes],
            estado=EstadoEscrituracao.ESTORNADA,
            estornada_em__gte=lote.criado_em,
        ).values_list("vinculo_id", flat=True)
    )
    inicio = _relogio()
    for linha_id, vinculo_id in pendentes:
        estado, motivo = _processar_nota(lote, linha_id, usuario, request, estornadas)
        if estado == EstadoNotaDoLoteNFe.EFETIVADA:
            parte.efetivadas.append(vinculo_id)
        elif estado == EstadoNotaDoLoteNFe.JA_EFETIVADA:
            parte.ja_efetivadas.append(vinculo_id)
        elif estado == EstadoNotaDoLoteNFe.FALHOU:
            nota = documentos[vinculo_id]
            parte.falhas.append(
                FalhaDaNota(vinculo_id, motivo, numero=nota.numero, serie=nota.serie)
            )
        if _relogio() - inicio >= ORCAMENTO_DA_PARTE_SEGUNDOS:
            break
    return parte


def resumo_do_lote(lote: LoteEscrituracaoNFe) -> dict:
    """Situação do lote para a tela e a API: restantes, efetivadas, puladas, falhas e os grupos
    que o lote confirmou (das linhas de nota: o grupo não marcado não tem linha)."""
    contagem = _contagem(lote)
    return {
        "lote_id": lote.pk,
        "grupos": sorted(_grupos_do_lote(lote)),
        "assinatura": lote.assinatura,
        "estado": lote.estado,
        "restantes": contagem.get(EstadoNotaDoLoteNFe.PENDENTE, 0),
        "efetivadas": contagem.get(EstadoNotaDoLoteNFe.EFETIVADA, 0),
        "ja_efetivadas": contagem.get(EstadoNotaDoLoteNFe.JA_EFETIVADA, 0),
        "falhas": contagem.get(EstadoNotaDoLoteNFe.FALHOU, 0),
    }


def _contagem(lote) -> dict[str, int]:
    linhas = (
        LoteEscrituracaoNFeNota.objects.filter(lote=lote)
        .values("estado")
        .annotate(total=Count("pk"))
    )
    return {linha["estado"]: linha["total"] for linha in linhas}


def _concluir_se_terminou(lote, usuario, request) -> None:
    with transaction.atomic():
        travado = LoteEscrituracaoNFe.objects.select_for_update(of=("self",)).get(pk=lote.pk)
        if travado.estado != EstadoLoteEscrituracaoNFe.EM_ANDAMENTO:
            return
        if LoteEscrituracaoNFeNota.objects.filter(
            lote=travado, estado=EstadoNotaDoLoteNFe.PENDENTE
        ).exists():
            return
        travado.estado = EstadoLoteEscrituracaoNFe.CONCLUIDO
        travado.concluido_em = timezone.now()
        travado.save(update_fields=["estado", "concluido_em"])
        registrar(
            acao="escrituracao_nfe.lote_concluido",
            usuario=usuario,
            escritorio=travado.escritorio,
            objeto=travado,
            request=request,
            detalhes={"lote_id": travado.pk, "contagem": _contagem(travado)},
        )


def _progresso(lote, parte: _Parte, restantes: int, contagem: dict[str, int]) -> ProgressoDoLote:
    competencia = lote.competencia
    return ProgressoDoLote(
        lote_id=lote.pk,
        ano=competencia.year,
        mes=competencia.month,
        assinatura=lote.assinatura,
        estado=lote.estado,
        total_notas=sum(contagem.values()),
        efetivadas_nesta_chamada=len(parte.efetivadas),
        ja_efetivadas_nesta_chamada=len(parte.ja_efetivadas),
        falhas_nesta_chamada=tuple(parte.falhas),
        restantes=restantes,
        efetivadas_total=contagem.get(EstadoNotaDoLoteNFe.EFETIVADA, 0),
        ja_efetivadas_total=contagem.get(EstadoNotaDoLoteNFe.JA_EFETIVADA, 0),
        falhas_total=contagem.get(EstadoNotaDoLoteNFe.FALHOU, 0),
    )


def _continuar(lote, usuario, request, limite: int) -> ProgressoDoLote:
    """Uma parte do lote. Não recalcula a prévia: o conjunto é o gravado."""
    parte = _Parte()
    if lote.estado == EstadoLoteEscrituracaoNFe.EM_ANDAMENTO:
        parte = _processar_parte(lote, usuario, request, limite)
        if parte.efetivadas or parte.ja_efetivadas or parte.falhas:
            registrar(
                acao="escrituracao_nfe.lote_parte",
                usuario=usuario,
                escritorio=lote.escritorio,
                objeto=lote,
                request=request,
                detalhes={
                    "lote_id": lote.pk,
                    "efetivadas": len(parte.efetivadas),
                    "ja_efetivadas": len(parte.ja_efetivadas),
                    "falhas": [
                        {"vinculo_id": f.vinculo_id, "motivo": f.motivo} for f in parte.falhas
                    ],
                },
            )
        _concluir_se_terminou(lote, usuario, request)
        lote.refresh_from_db()
    contagem = _contagem(lote)
    return _progresso(lote, parte, contagem.get(EstadoNotaDoLoteNFe.PENDENTE, 0), contagem)


def confirmar_lote(
    empresa,
    ano: int | None,
    mes: int | None,
    assinatura: str | None,
    escolhas: dict | None,
    usuario,
    request=None,
    limite: int = LIMITE_PADRAO_DA_PARTE,
    lote_id: int | None = None,
    grupos: list[str] | None = None,
) -> ProgressoDoLote:
    """Confirma a prévia (1ª chamada) ou continua o lote (com `lote_id`). Uma parte por chamada.

    - Primeira chamada: `ano`, `mes`, `assinatura` e `escolhas` (opcional, `{grupo: {id: nat}}`).
      Assinatura diferente da prévia de agora: `PreviaDesatualizada` (409), nada gravado.
    - `grupos` (opcional, só na primeira chamada): as chaves dos grupos que entram no lote. `None` é
      a prévia inteira. Os grupos não listados não têm nota gravada: nem rascunho é criado. A
      assinatura continua sendo a da prévia inteira. Lista vazia, ou grupo que a prévia não tem:
      400 nomeado, sem gravar nada.
    - Continuação: `lote_id` (e a assinatura, se enviada, tem de ser a do lote). Escolhas e grupos
      não valem na continuação: vêm com erro de entrada (400), e não são ignorados em silêncio.
    - Repetir a primeira chamada com a mesma assinatura, com o lote ainda em andamento, CONTINUA o
      lote, sem duplicar nada. Com outros grupos ou outras escolhas, é outro ato: 409.
    """
    limite = _validar_limite(limite)
    if lote_id is not None:
        lote = _lote_da_empresa(empresa, lote_id)
        if escolhas:
            raise servico.EntradaInvalidaNFe(
                "As escolhas valem na confirmação do lote, não na continuação."
            )
        if grupos is not None:
            raise servico.EntradaInvalidaNFe(
                "Os grupos valem na confirmação do lote, não na continuação."
            )
        if assinatura and assinatura != lote.assinatura:
            raise PreviaDesatualizada(MENSAGEM_ASSINATURA_DO_LOTE)
        return _continuar(lote, usuario, request, limite)

    _validar_competencia(ano, mes)
    if not assinatura:
        raise servico.EntradaInvalidaNFe("Informe a assinatura da prévia confirmada.")
    if grupos is not None and not grupos:
        raise servico.EntradaInvalidaNFe(
            "Marque ao menos um grupo para confirmar. Nada foi efetivado."
        )
    competencia = date(ano, mes, 1)
    # A prévia pesada é calculada FORA da trava da empresa (reconferência da DL-085, R1). Só quando
    # não há lote em andamento: a repetição do mesmo ato não precisa dela.
    previa_inteira = None
    if _lote_em_andamento(empresa, competencia) is None:
        previa_inteira = _calcular(empresa, ano, mes, None)
    with transaction.atomic():
        travada = receita_servico.travar_empresa(empresa)
        aberto = _lote_em_andamento(travada, competencia)
        if aberto is not None:
            # Repetição do mesmo ato (ex.: a resposta se perdeu): continua o lote. Assinatura,
            # escolha ou grupos diferentes do gravado são outro ato, e recusam (409).
            escolhas_do_pedido = _normalizar_escolhas(escolhas)
            if (
                assinatura != aberto.assinatura
                or (escolhas_do_pedido and escolhas_do_pedido != aberto.escolhas)
                or _grupos_divergem(travada, ano, mes, aberto, grupos)
            ):
                raise LoteEmAndamento(MENSAGEM_LOTE_EM_ANDAMENTO)
            lote = aberto
        else:
            lote = _criar_lote(
                travada,
                ano,
                mes,
                assinatura,
                escolhas or {},
                usuario,
                request,
                grupos,
                previa_inteira=previa_inteira,
            )
    return _continuar(lote, usuario, request, limite)
