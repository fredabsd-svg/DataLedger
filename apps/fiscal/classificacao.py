"""Classificação fiscal versionada — DL-087, corte 1 (frente A).

Plano: docs/planos/DL-087-classificacao-fiscal-versionada.md (revisão de 12/10/2026). Decisão:
DE-107. Hipóteses: HI-141, HI-142 e HI-153. A pendência PE-91 (pesos ou ordem manual) continua com o
Fred: o corte 1 usa os pesos abaixo, e a escolha dele pode mudar só `PESOS_DE_ESPECIFICIDADE`.

O QUE ESTE MÓDULO FAZ
- Dá UMA resposta para "qual natureza sugerir para este item": `sugerir_natureza_com_regras`.
- Cadastra as regras do escritório e da empresa (`criar_regra`, `desativar_regra`).
- Monta a fila "a classificar": itens das notas a escriturar sem sugestão ou em conflito, agrupados.
- Publica a lista constante `REGRAS_DO_PRODUTO`, que descreve em palavras a sugestão embutida.

O QUE ESTE MÓDULO NÃO FAZ
- Não efetiva nada e não grava natureza em item. A regra só muda a SUGESTÃO. Quem grava é o
  serviço de escrituração (`escrituracao_nfe`), com o contador escolhendo.
- Não converte a sugestão embutida em linhas de tabela: isso é o corte 2 (DE-107). A camada de
  produto continua em código, em `escrituracao_nfe.sugerir_natureza_item`.

ORDEM DA RESOLUÇÃO (por item, em `sugerir_natureza_com_regras`)
1. Nota de ajuste (finNFe 2, 3, 5 ou 6), CFOP fora da tabela oficial, ou item sem sinal: a sugestão
   embutida, sem consultar regra. Ajuste nunca recebe regra.
2. Regras VIGENTES na data de emissão, do escritório e da empresa, que casam com o item e cuja
   natureza cabe no tipo da nota. Uma regra cuja natureza não cabe no tipo não vale (conta como não
   casada); se for o único candidato, o motivo diz isso.
3. Entre as que casam, vence a de MAIOR ESPECIFICIDADE: soma dos pesos publicados, em potência de
   dois (CFOP 64, NCM exato 32, NCM por prefixo 16, CST/CSOSN 8, `idDest` 4, UF do emitente 2, CRT
   do emitente 1; DL-091, A2). Como os pesos são potências de dois, conjuntos diferentes de
   critérios nunca empatam.
4. Empate de especificidade: vence o PREFIXO DE NCM MAIS LONGO (ajuste do arquiteto, 12/10/2026).
5. Empate com o prefixo igual: vence o escopo EMPRESA sobre o ESCRITÓRIO.
6. Empate de precedência com NATUREZAS DIFERENTES: CONFLITO. O item fica sem sugestão e o motivo
   nomeia as regras. Empate com a MESMA natureza não é conflito: o item recebe a sugestão e o motivo
   nomeia as regras. Não há padrão silencioso: o conflito não cai no padrão de combustível.
7. Nenhuma regra casa: `escrituracao_nfe.sugerir_natureza_com_padrao`, exatamente como antes da
DL-087.

Na prática, com pesos em potência de dois, dois conflitos reais só aparecem entre regras com os
MESMOS critérios cuja vigência se cruza com regra já desativada (a duplicidade do cadastro só olha
regras ativas). É o caso que a fila mostra; o teste de servico o cobre.

COMBUSTÍVEL EXIGE NCM (HI-139; consulta de 12/10/2026, item 1): regra cujo resultado é combustível
(consumo, revenda ou devolução para consumo) é recusada sem NCM, exato ou por prefixo. Se o NCM ou o
prefixo alcança NCM de lubrificante, a criação é aceita com aviso (`avisos_da_regra`).

ORIGEM PERSISTIDA (ajuste 6): a natureza CONFIRMADA grava de onde veio (`NaturezaItemNFe.origem`):
regra (com a FK da regra), produto, padrão da empresa, ou manual quando o contador escolheu outra.
Linhas anteriores à DL-087 ficam com origem nula.

PRÉVIA DE IMPACTO (ajuste 7): `previa_de_impacto` conta, sem gravar, quantos itens das notas a
escriturar mudariam de sugestão com uma regra ainda não salva. Uma passada, sem consulta por item.

MÊS CONFIRMADO (ajuste 8): o código NÃO tem gate de competência. Escriturar uma nota de mês
confirmado
reabre a confirmação e a marca "a retificar" (DL-074, `receita.marcar_a_retificar`). A fila mostra o
aviso do mês; a regra nunca muda nota efetivada.

CONTEXTO CARREGADO UMA VEZ
`contexto_da_empresa(empresa)` lê as regras do escritório e da empresa e o padrão de combustível
da empresa, em UMA consulta de regras e UMA do padrão. `sugerir_natureza_com_regras` não consulta o
banco: quem chama carrega o contexto uma vez por chamada e o repassa a todos os itens (BL-698).

VIGÊNCIA (regra da data de emissão, não da data de hoje)
- Uma regra vale para a nota quando `vigencia_inicio <= dia_da_emissão <= vigencia_fim`, com fim
  vazio = sem fim. O dia é o de `dhEmi` no fuso de São Paulo (`escrituracao_nfe.dia_e_competencia`).

DESATIVAR É REVOGAR (correção da rodada 1, A1; DE-108)
- A desativação grava o fim da vigência na véspera do início (`vigencia_revogada`). Vigência vazia:
  nenhuma data de emissão cai nela. A regra revogada NÃO casa com nota nenhuma, pendente ou futura.
- A escrituração efetivada não muda, e guarda a origem que teve (a regra segue no registro, marcada
  como desativada). A regra não é reaproveitada: quem quer outra, cria outra.
- A assinatura do lote muda (a fonte da sugestão some), e uma confirmação com a prévia antiga
  recebe 409 (`PreviaDesatualizada`).
- O gatilho do banco (migração 0019) recusa qualquer fim de vigência que não seja essa revogação.

CADASTRO
- Recusas (400): tipo ajuste, CFOP fora da tabela oficial, natureza que não cabe no tipo, NCM fora
  do modo ou com caractere que não seja dígito ASCII ou ponto, CST/CSOSN e `idDest` fora do formato,
  fim anterior ao início.
- Duplicata (409): duas regras ATIVAS do mesmo escopo, com os mesmos critérios e vigências que se
  cruzam. Regra de escopo diferente não é duplicata: é a precedência. A prévia de impacto recusa a
  duplicata com o mesmo 409, antes de calcular (A2).
- Criar e desativar gravam a trilha (`apps.auditoria`), na mesma transação.
- Regra de escritório só é criada por ADMINISTRADOR e GESTOR; regra de empresa, por quem escritura
  no fiscal. Quem decide isso é a API (`api_classificacao`), no servidor.

CONTAGEM POR EMPRESA (A3)
- Os itens confirmados de uma regra são contados só nas escriturações da EMPRESA da consulta. Regra
  do escritório é compartilhada, mas a contagem de outra empresa não aparece.
  `contagem_de_confirmados` e `confirmados_da_regra` são as duas formas de API e tela lerem isso.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.fiscal import entradas, presumido
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    CRTS_DO_EMITENTE_NA_REGRA,
    SIGLAS_DE_UF_DO_EMITENTE_NA_REGRA,
    EstadoConfirmacaoMes,
    ItemNFe,
    LeituraItensNFe,
    ModoNcmRegraNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    OrigemNaturezaItemNFe,
    PapelNFe,
    RegraClassificacaoNFe,
    TipoEscrituracaoNFe,
    TipoRegraClassificacaoNFe,
)
from apps.fiscal.ncm_combustivel import NCM_LUBRIFICANTE, normalizar_ncm
from apps.tenancy.models import Escritorio

# ---------------------------------------------------------------------------
# Constantes publicadas (pesos de especificidade: aparecem na API e na tela)
# ---------------------------------------------------------------------------

# Potências de dois: qualquer conjunto de critérios opcionais tem soma distinta, e dois conjuntos
# diferentes nunca empatam (com 8/4/2/1 empatavam, p. ex., CFOP+prefixo+CST com CFOP+exato+idDest).
#
# DL-091 (A2): os pesos antigos (CFOP 16, NCM exato 8, NCM prefixo 4, CST/CSOSN 2, idDest 1) foram
# multiplicados por quatro, e os dois critérios de fornecedor (CRT e UF do emitente, só na regra de
# entrada) entraram nos menores valores, 1 e 2. Dobrar não bastava: sobrariam dois valores iguais
# a 1, e dois critérios diferentes empatariam. Multiplicar por quatro mantém a ORDEM entre os
# critérios antigos (todos os pesos antigos cresceram na mesma proporção), e os de fornecedor são
# os menos específicos. `test_dl091_regras_entrada` confere a ausência de empate entre TODOS os
# conjuntos de critérios.
PESO_CFOP = 64
PESO_NCM_EXATO = 32
PESO_NCM_PREFIXO = 16
PESO_CST_CSOSN = 8
PESO_ID_DEST = 4
PESO_UF_EMITENTE = 2
PESO_CRT_EMITENTE = 1
PESOS_DE_ESPECIFICIDADE = {
    "cfop": PESO_CFOP,
    "ncm_exato": PESO_NCM_EXATO,
    "ncm_prefixo": PESO_NCM_PREFIXO,
    "cst_csosn": PESO_CST_CSOSN,
    "id_dest": PESO_ID_DEST,
    "uf_emitente": PESO_UF_EMITENTE,
    "crt_emitente": PESO_CRT_EMITENTE,
}

ESCOPO_EMPRESA = "empresa"
ESCOPO_ESCRITORIO = "escritorio"
# Posição do escopo no desempate: a empresa vence o escritório (passo 4 da ordem acima).
_POSICAO_DO_ESCOPO = {ESCOPO_ESCRITORIO: 0, ESCOPO_EMPRESA: 1}

# Situação de um grupo da fila, como a tela e a API mostram.
SITUACAO_SEM_SUGESTAO = "sem_sugestao"
SITUACAO_CONFLITO = "conflito"

# Naturezas de combustível que o 1,6% e o 8% dependem do NCM (HI-139): a regra que as produz exige
# NCM, exato ou por prefixo, na criação (consulta de 12/10/2026, item 1).
NATUREZAS_DE_COMBUSTIVEL_QUE_EXIGEM_NCM = frozenset(
    {
        NaturezaOperacaoNFe.COMBUSTIVEL,
        NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA,
        NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
        # DL-091 (A2): a compra de combustível para revenda (E6) e para consumo (E7) também exige
        # NCM, como a venda (consulta de 13/10/2026, seção 5).
        NaturezaOperacaoNFe.ENTRADA_COMBUSTIVEL_REVENDA,
        NaturezaOperacaoNFe.ENTRADA_COMBUSTIVEL_CONSUMO,
    }
)

# Tipos que a regra aceita. O ajuste está de fora de propósito (passo 1).
TIPOS_COM_REGRA = frozenset(TipoRegraClassificacaoNFe.values)

_CFOP_DE_4_DIGITOS = re.compile(r"[0-9]{4}")
# `[0-9]` é ASCII de propósito: `\d` aceitaria dígitos de outros alfabetos (A5).
_NCM_SO_DIGITOS_E_PONTOS = re.compile(r"[0-9.]+")
_CST_CSOSN = re.compile(r"[0-9]{2,3}")
_IDS_DEST = ("1", "2", "3")
MENSAGEM_TIPO_AJUSTE = (
    "Nota de ajuste (finNFe 2, 3, 5 ou 6) não recebe regra de classificação: a natureza de ajuste "
    "é fixa."
)
# DL-091 (A2): finNFe 4 em saída própria só leva a devolução de compra oficial (sugerida pelo
# produto). O retorno (conserto, remessa) fica sem sugestão por contrato (A1): regra não o empurra.
MENSAGEM_TIPO_DEVOLUCAO_COMPRA = (
    "A nota de devolução de compra (finNFe 4 em saída própria) não recebe regra: a natureza é a "
    "devolução de compra oficial, e o retorno fica sem sugestão (contrato da DL-091, A1)."
)
MENSAGEM_CRITERIO_SO_NA_ENTRADA = (
    "CRT do emitente, UF do emitente e CFOP de entrada só valem para a regra de entrada: a saída "
    "usa a própria empresa, e o produto não os lê na nota de saída."
)


# Origem gravada em `NaturezaItemNFe.origem` (valores fixos; o modelo os declara).
ORIGEM_NATUREZA_REGRA = "regra"
ORIGEM_NATUREZA_PRODUTO = "produto"
ORIGEM_NATUREZA_PADRAO_EMPRESA = "padrao_empresa"
ORIGEM_NATUREZA_MANUAL = "manual"


class RegraDuplicada(servico.EscrituracaoNFeErro):
    """Regra ativa com o mesmo escopo, critérios e vigência que se cruza. A API responde 409."""


# ---------------------------------------------------------------------------
# Contexto e resolução
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RegrasDoCfop:
    """As regras de UM CFOP, separadas pelo critério de NCM (A6).

    `sem_ncm`: casam qualquer NCM. `exatas`: NCM de 8 dígitos -> regras. `prefixos`: prefixo ->
    regras, e `comprimentos` são os tamanhos de prefixo presentes. Para um NCM, a lista de
    candidatas é `sem_ncm` mais a exata e o prefixo de cada comprimento: uma consulta de dict por
    comprimento, sem percorrer as regras do CFOP. Com 50 regras que não casam, o item custa o mesmo.
    """

    sem_ncm: tuple
    exatas: dict
    prefixos: dict
    comprimentos: tuple


def _indexar_regras_do_cfop(regras) -> _RegrasDoCfop:
    sem_ncm: list = []
    exatas: dict[str, list] = {}
    prefixos: dict[str, list] = {}
    for regra in regras:
        if not regra.ncm:
            sem_ncm.append(regra)
        elif regra.ncm_modo == ModoNcmRegraNFe.EXATO:
            exatas.setdefault(regra.ncm, []).append(regra)
        else:
            prefixos.setdefault(regra.ncm, []).append(regra)
    return _RegrasDoCfop(
        sem_ncm=tuple(sem_ncm),
        exatas={k: tuple(v) for k, v in exatas.items()},
        prefixos={k: tuple(v) for k, v in prefixos.items()},
        comprimentos=tuple(sorted({len(p) for p in prefixos})),
    )


@dataclass(frozen=True)
class ContextoDeClassificacao:
    """O que a resolução precisa, carregado UMA vez por chamada: regras e padrão da empresa.

    As regras são indexadas por CFOP e, dentro dele, por NCM (`candidatas_do_item`): o CFOP é
    critério obrigatório, e o NCM é a outra chave que separa a maioria das regras. Sem o índice,
    cada item percorria todas as regras do escritório (a medida de volume com 50 regras estourou o
    teto de 10 s por chamada, DL-087 frente A).
    """

    escritorio_id: int
    empresa_id: int
    padrao_combustivel: str
    regras: tuple = field(default=())
    _indice: dict = field(init=False, repr=False, compare=False, default_factory=dict)

    def __post_init__(self):
        por_cfop: dict[str, list] = {}
        for regra in self.regras:
            por_cfop.setdefault(regra.cfop, []).append(regra)
        # Frozen: o índice é derivado das regras, preenchido uma vez, e não muda depois.
        indice = {cfop: _indexar_regras_do_cfop(lista) for cfop, lista in por_cfop.items()}
        object.__setattr__(self, "_indice", indice)

    def candidatas_do_item(self, cfop: str, ncm_normalizado: str) -> list:
        """Regras que PODEM casar o item (mesmo CFOP e NCM compatível). `_casa` confere o resto.

        A ordem é a de criação (pk), para que as mensagens e os desempates sejam estáveis.
        """
        indice = self._indice.get(cfop)
        if indice is None:
            return []
        achadas = list(indice.sem_ncm)
        achadas.extend(indice.exatas.get(ncm_normalizado, ()))
        for comprimento in indice.comprimentos:
            achadas.extend(indice.prefixos.get(ncm_normalizado[:comprimento], ()))
        return sorted(achadas, key=_chave_pk)

    def regras_do_cfop(self, cfop: str) -> tuple:
        """Todas as regras do CFOP, sem filtro de NCM (teste e diagnóstico)."""
        indice = self._indice.get(cfop)
        if indice is None:
            return ()
        todas = list(indice.sem_ncm)
        for lista in indice.exatas.values():
            todas.extend(lista)
        for lista in indice.prefixos.values():
            todas.extend(lista)
        return tuple(sorted(todas, key=_chave_pk))


def contexto_da_empresa(empresa) -> ContextoDeClassificacao:
    """Carrega as regras do escritório e da empresa, e o padrão de combustível. Duas consultas.

    As regras de OUTRAS empresas do mesmo escritório não entram: o isolamento começa aqui.
    """
    regras = tuple(
        RegraClassificacaoNFe.objects.filter(escritorio_id=empresa.escritorio_id)
        .filter(Q(empresa__isnull=True) | Q(empresa_id=empresa.pk))
        .order_by("pk")
    )
    return ContextoDeClassificacao(
        escritorio_id=empresa.escritorio_id,
        empresa_id=empresa.pk,
        padrao_combustivel=presumido.parametros_da_empresa(empresa).padrao_combustivel,
        regras=regras,
    )


def especificidade(regra) -> int:
    """Pontos de especificidade de uma regra, pelos pesos publicados."""
    pontos = PESO_CFOP
    if regra.ncm:
        pontos += PESO_NCM_EXATO if regra.ncm_modo == ModoNcmRegraNFe.EXATO else PESO_NCM_PREFIXO
    if regra.cst_csosn:
        pontos += PESO_CST_CSOSN
    if regra.id_dest:
        pontos += PESO_ID_DEST
    if regra.uf_emitente:
        pontos += PESO_UF_EMITENTE
    if regra.crt_emitente:
        pontos += PESO_CRT_EMITENTE
    return pontos


def _rotulo_do_escopo(regra) -> str:
    return "da empresa" if regra.empresa_id is not None else "do escritório"


def _chave_pk(regra) -> int:
    """pk para ordenar. A regra da prévia de impacto ainda não tem pk (é `None`): vale 0, e o
    mesmo valor sai nos desempates. Sem isso, comparar `None` com `int` dava 500 (A2)."""
    return regra.pk or 0


def vigencia_revogada(inicio: date) -> date:
    """Fim da vigência gravado por uma REVOGAÇÃO: a véspera do início (DL-087, A1).

    Com a véspera, nenhuma data de emissão cai na vigência (`dia < início` ou `dia > fim`). Na data
    mínima do calendário não há véspera: o fim fica no próprio início, e a conta continua sem casar
    data real. O gatilho da 0019 faz a MESMA conta no banco; se uma mudar, mude a outra.
    """
    return inicio - timedelta(days=1) if inicio > date.min else inicio


def _casa(regra, contexto: ContextoDeClassificacao, documento, item, tipo: str, dia: date) -> bool:
    """A regra vale para este item? Tipo, escopo, vigência na data de emissão e critérios."""
    # Revogada: não casa com nota nenhuma, pendente ou futura. A vigência vazia já garante isso; a
    # checagem explícita deixa a regra fora mesmo que a conta da vigência mude um dia.
    if regra.desativada_em is not None:
        return False
    if regra.tipo != tipo:
        return False
    if regra.empresa_id is not None and regra.empresa_id != contexto.empresa_id:
        return False
    if dia < regra.vigencia_inicio:
        return False
    if regra.vigencia_fim is not None and dia > regra.vigencia_fim:
        return False
    if regra.cfop != item.cfop:
        return False
    if regra.ncm:
        ncm = normalizar_ncm(item.ncm)
        if regra.ncm_modo == ModoNcmRegraNFe.EXATO:
            if ncm != regra.ncm:
                return False
        elif not ncm.startswith(regra.ncm):
            return False
    # CST ou CSOSN comparado como está na nota: o código pode vir em qualquer um dos dois campos.
    if regra.cst_csosn and regra.cst_csosn not in (item.csosn, item.cst):
        return False
    if regra.id_dest and documento.id_dest != regra.id_dest:
        return False
    # DL-091 (A2): critérios do fornecedor. O CRT vem do XML; a UF do emitente é o `cUF` traduzido
    # para a sigla. Vazio na regra: não restringe.
    if regra.crt_emitente and documento.emitente_crt != regra.crt_emitente:
        return False
    if regra.uf_emitente and entradas.CODIGO_IBGE_DA_UF.get(documento.c_uf) != regra.uf_emitente:
        return False
    return True


def _nomes_das_regras(regras) -> str:
    """'regra n.º 3 (do escritório), regra n.º 7 (da empresa) e regra n.º 9 (...)'."""
    partes = [
        (
            f"regra n.º {r.pk} ({_rotulo_do_escopo(r)})"
            if r.pk is not None
            else f"a regra nova ({_rotulo_do_escopo(r)})"
        )
        for r in regras
    ]
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]


def sugerir_natureza_com_regras(
    contexto: ContextoDeClassificacao, documento, item, tipo: str | None = None
) -> servico.Sugestao:
    """A sugestão de natureza de UM item, com as regras por cima da sugestão embutida.

    Função única de resolução (DL-087, passos 1 a 6 do módulo). Não consulta o banco: tudo vem de
    `contexto`, de `documento` e de `item`, que já foram carregados por quem chama.
    """
    if tipo is None:
        tipo = servico.tipo_da_nota(documento, PapelNFe.EMITENTE) or ""

    def embutida() -> servico.Sugestao:
        return servico.sugerir_natureza_com_padrao(
            documento, item, contexto.padrao_combustivel, tipo
        )

    # Passo 1: ajuste e CFOP fora da tabela seguem a sugestão embutida, sem regra.
    if documento.fin_nfe in ("2", "3", "5", "6") or tipo == TipoEscrituracaoNFe.AJUSTE:
        return embutida()
    if consultar_cfop(item.cfop) is None:
        return embutida()

    # Só as regras do MESMO CFOP e de NCM compatível podem casar (o índice). Sem nenhuma, a embutida
    # responde, e a data da nota nem é lida.
    do_item = contexto.candidatas_do_item(item.cfop, normalizar_ncm(item.ncm))
    if not do_item:
        return embutida()
    dia = servico.dia_e_competencia(documento)[0]
    candidatas = [r for r in do_item if _casa(r, contexto, documento, item, tipo, dia)]
    if not candidatas:
        return embutida()

    # Passo 2: a natureza da regra tem de caber no tipo da nota. Se não cabe, a regra não vale.
    permitidas = servico.naturezas_permitidas(tipo)
    validas = [r for r in candidatas if r.natureza in permitidas]
    if not validas:
        base = embutida()
        nomes = _nomes_das_regras(candidatas)
        return replace(
            base,
            motivo=(
                f"{base.motivo}; {nomes} não vale: a natureza dela não cabe em "
                f"{_rotulo_do_tipo(tipo)}"
            ),
        )

    # Passos 3 a 5, com o desempate de prefixo (consulta de 12/10/2026, item 1): maior
    # especificidade;
    # depois o prefixo de NCM mais longo; depois o escopo empresa sobre o escritório.
    maxima = max(chave_de_precedencia(r) for r in validas)
    vencedoras = [r for r in validas if chave_de_precedencia(r) == maxima]
    naturezas = {r.natureza for r in vencedoras}
    if len(naturezas) > 1:
        return servico.Sugestao(
            None,
            (
                f"conflito entre regras: {_nomes_das_regras(vencedoras)} têm a mesma "
                "especificidade e o mesmo escopo e apontam naturezas diferentes: escolha a natureza"
            ),
            origem=servico.ORIGEM_DA_SUGESTAO_CONFLITO_DE_REGRAS,
            regra_ids=_pks_das(vencedoras),
            escopo_regra=_escopo_da(vencedoras[0]),
        )
    regra = min(vencedoras, key=_chave_pk)
    if len(vencedoras) == 1:
        motivo = (
            f"sugerida pela regra n.º {regra.pk} ({_rotulo_do_escopo(regra)}): "
            f"{_descricao_dos_criterios(regra)}"
        )
    else:
        # Mesma natureza em regras de mesma precedência: não é conflito, e o motivo mostra as duas.
        motivo = (
            f"sugerida pelas regras {_nomes_das_regras(vencedoras)}, que apontam a mesma natureza "
            f"(não é conflito): {_descricao_dos_criterios(regra)}"
        )
    return servico.Sugestao(
        regra.natureza,
        motivo,
        origem=servico.ORIGEM_DA_SUGESTAO_REGRA,
        regra_ids=_pks_das(vencedoras),
        escopo_regra=_escopo_da(regra),
        cfop_entrada=regra.cfop_entrada or "",
    )


def _pks_das(regras) -> tuple[int, ...]:
    """pks das regras gravadas, em ordem. A regra da prévia (sem pk) não entra: nunca é origem."""
    return tuple(sorted(r.pk for r in regras if r.pk is not None))


def chave_de_precedencia(regra) -> tuple:
    """(especificidade, comprimento do NCM, posição do escopo). Vence a chave maior."""
    return (especificidade(regra), len(regra.ncm or ""), _POSICAO_DO_ESCOPO[_escopo_da(regra)])


def _escopo_da(regra) -> str:
    return ESCOPO_EMPRESA if regra.empresa_id is not None else ESCOPO_ESCRITORIO


def _rotulo_do_tipo(tipo: str) -> str:
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO:
        return "devolução de venda"
    if tipo == TipoEscrituracaoNFe.ENTRADA:
        return "entrada de compra"
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA:
        return "devolução de compra (finNFe 4)"
    return "saída própria"


def _descricao_dos_criterios(regra) -> str:
    partes = [f"CFOP {regra.cfop}"]
    if regra.ncm:
        modo = "NCM" if regra.ncm_modo == ModoNcmRegraNFe.EXATO else "NCM com prefixo"
        partes.append(f"{modo} {regra.ncm}")
    if regra.cst_csosn:
        partes.append(f"CST/CSOSN {regra.cst_csosn}")
    if regra.id_dest:
        partes.append(f"idDest {regra.id_dest}")
    if regra.crt_emitente:
        partes.append(f"CRT do emitente {regra.crt_emitente}")
    if regra.uf_emitente:
        partes.append(f"UF do emitente {regra.uf_emitente}")
    return ", ".join(partes)


def fonte_da_sugestao(sugestao: servico.Sugestao) -> str:
    """Identifica a regra que produziu a sugestão, para a assinatura do grupo do lote.

    Vazio quando a sugestão veio do produto ou do padrão da empresa. Assim, sem regra cadastrada, a
    assinatura do lote é a mesma de antes da DL-087. Com regra, a assinatura muda: criar ou
    desativar
    regra muda a prévia, e a confirmação antiga recebe 409 (DL-087, item 4).
    """
    if sugestao.origem == servico.ORIGEM_DA_SUGESTAO_REGRA and sugestao.regra_ids:
        return f"regra:{sugestao.regra_ids[0]}"
    return ""


def origem_da_confirmacao(sugestao: servico.Sugestao, natureza: str) -> tuple[str, int | None]:
    """Origem gravada na natureza CONFIRMADA: (origem, regra_id). Vale para o item confirmado.

    `regra` quando a natureza confirmada é a da regra; `produto` e `padrao_empresa` quando é a da
    sugestão embutida ou do padrão; `manual` quando o contador escolheu outra (ou não há sugestão).
    """
    if sugestao.natureza is None or natureza != sugestao.natureza:
        return ORIGEM_NATUREZA_MANUAL, None
    if sugestao.origem == servico.ORIGEM_DA_SUGESTAO_REGRA:
        return ORIGEM_NATUREZA_REGRA, sugestao.regra_ids[0]
    if sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PADRAO:
        return ORIGEM_NATUREZA_PADRAO_EMPRESA, None
    return ORIGEM_NATUREZA_PRODUTO, None


# ---------------------------------------------------------------------------
# Regras do produto (só leitura): a sugestão embutida, em palavras
# ---------------------------------------------------------------------------

# Cada linha descreve UM sinal da sugestão embutida (`escrituracao_nfe.sugerir_natureza_item` e
# vizinhas) e a fonte que o código cita. A fonte é a da documentação do código, não norma nova.
# Quem altera a sugestão embutida atualiza esta lista no mesmo commit. O teste
# `test_dl087_correcao_rodada1.py` confere que cada linha tem sinal, resultado e fonte, e que os
# sufixos de CFOP citados aqui são os da sugestão embutida (A12).
REGRAS_DO_PRODUTO = (
    {
        "sinal": "Nota de ajuste: finNFe 2, 3, 5 ou 6.",
        "resultado": "ajuste (única natureza de ajuste)",
        "fonte": (
            "consulta de 09/10/2026, item 2 (HI-118), em escrituracao_nfe.sugerir_natureza_item"
        ),
    },
    {
        "sinal": "CFOP fora da tabela oficial.",
        "resultado": "sem sugestão: a classificar",
        "fonte": "tabela oficial de CFOP, Informe 2023.002 v2.10 (apps/fiscal/cfop.py)",
    },
    {
        "sinal": (
            "Devolução (finNFe 4): decide a coluna indDevol da tabela oficial, nunca a faixa do "
            "CFOP."
        ),
        "resultado": "devolução de venda, ou a de combustível para consumo (abaixo)",
        "fonte": "consulta de 09/10/2026, item 2 (HI-140), em _sugestao_de_devolucao",
    },
    {
        "sinal": "Devolução de combustível com NCM de lubrificante.",
        "resultado": "devolução de venda (deduz do 8%, fora do 1,6%)",
        "fonte": "Lei 9.249, art. 15, § 1º, I (citada no código; HI-140)",
    },
    {
        "sinal": (
            "Devolução de combustível com CFOP x.662 (destinado a consumidor final) e NCM de "
            "combustível."
        ),
        "resultado": "devolução de venda de combustível para consumo (deduz do 1,6%)",
        "fonte": "HI-140, em _sugestao_de_devolucao",
    },
    {
        "sinal": (
            "Devolução de combustível com CFOP x.662 e NCM ausente ou fora da lista de combustível."
        ),
        "resultado": "sem sugestão: escolha a natureza",
        "fonte": "HI-140, em _MOTIVO_SEM_NCM_DE_COMBUSTIVEL",
    },
    {
        "sinal": (
            "Devolução de combustível com CFOP x.660 ou x.661 (industrialização ou "
            "comercialização)."
        ),
        "resultado": "devolução de venda (8%)",
        "fonte": "HI-140, em _sugestao_de_devolucao",
    },
    {
        "sinal": "Devolução com NCM de combustível e CFOP genérico (sem x.662 nem x.660/x.661).",
        "resultado": (
            "sem sugestão: só o contador sabe se a venda original foi para consumo ou revenda"
        ),
        "fonte": "HI-140, em _sugestao_de_devolucao",
    },
    {
        "sinal": (
            "Saída própria com finNFe 4 (tpNF 1) e CFOP com indDevol 1 cuja descrição oficial é de "
            "devolução de compra, de mercadoria recebida em transferência, de bem do ativo, de uso "
            "ou consumo, ou de embalagens."
        ),
        "resultado": "devolução de compra: natureza só dela, fora da receita",
        "fonte": (
            "DL-091, correção do arquiteto (13/10/2026), em sugerir_natureza_item e "
            "entradas.TEXTOS_DE_DEVOLUCAO_DE_COMPRA"
        ),
    },
    {
        "sinal": (
            "Saída própria com finNFe 4 (tpNF 1) e CFOP de retorno: sem indDevol 1, "
            "ou com indDevol 1 "
            "mas fora da lista de devolução de compra (conserto, remessa, consignação)."
        ),
        "resultado": "sem sugestão: a nota não efetiva enquanto o item não tiver natureza",
        "fonte": "DL-091, correção do arquiteto (item 3), em sugerir_natureza_item",
    },
    {
        "sinal": "Devolução (finNFe 4) com CFOP sem indDevol.",
        "resultado": "sem sugestão: conflito (não é devolução)",
        "fonte": "escrituracao_nfe.sugerir_natureza_item",
    },
    {
        "sinal": "CFOP x.501, x.502, x.910 ou x.911 (comercial exportadora e bonificação).",
        "resultado": "sem sugestão: a consulta não dá sinal suficiente",
        "fonte": "consulta de 09/10/2026, item 2 (HI-118)",
    },
    {
        "sinal": "CFOP 7.1xx com idDest 3 (venda ao exterior). Remessa e ativo não são venda.",
        "resultado": "exportação direta",
        "fonte": "correção da rodada 1 da DL-081 (A11), em _candidatos_do_item",
    },
    {
        "sinal": "CFOP 5929.",
        "resultado": "operação já registrada em NFC-e ou cupom",
        "fonte": "consulta de 09/10/2026, item 2, em _candidatos_do_item",
    },
    {
        "sinal": "CFOP de transferência (x.151 a x.156) com emitente igual ao destinatário.",
        "resultado": "transferência entre estabelecimentos",
        "fonte": "consulta de 09/10/2026, item 2, em _candidatos_do_item",
    },
    {
        "sinal": "CFOP x.102 ou x.104 (revenda).",
        "resultado": "revenda de mercadoria adquirida de terceiros",
        "fonte": "consulta de 09/10/2026, item 2, em _candidatos_do_item",
    },
    {
        "sinal": "CFOP x.101 ou x.103 (produção).",
        "resultado": "venda de produção própria",
        "fonte": "consulta de 09/10/2026, item 2, em _candidatos_do_item",
    },
    {
        "sinal": (
            "CFOP de combustível pela descrição oficial: 'consumidor ou usuário final' (x.656, "
            "x.667)."
        ),
        "resultado": "revenda de combustível para consumo (1,6% no IRPJ)",
        "fonte": "PE-85.1 e HI-118, em _VENDA_DE_COMBUSTIVEL",
    },
    {
        "sinal": "CFOP de combustível pela descrição oficial: 'comercialização' (x.655).",
        "resultado": "revenda de combustível para revenda (8% no IRPJ)",
        "fonte": "PE-85.1 e HI-118, em _VENDA_DE_COMBUSTIVEL",
    },
    {
        "sinal": "CFOP de produção própria de combustível (x.651 a x.653).",
        "resultado": "sem sugestão: a natureza não está confirmada pelo CFOP",
        "fonte": "PE-85.1, em _VENDA_DE_COMBUSTIVEL",
    },
    {
        "sinal": "CFOP de combustível com NCM de lubrificante.",
        "resultado": "revenda (fora do 1,6%)",
        "fonte": "Lei 9.249, art. 15, § 1º, I (citada no código; HI-139)",
    },
    {
        "sinal": (
            "CFOP de combustível com NCM de combustível (lista positiva; álcool e diesel B quando "
            "o CFOP diz combustível)."
        ),
        "resultado": "a natureza que a descrição do CFOP confirma",
        "fonte": "HI-139, em _candidatos_do_item",
    },
    {
        "sinal": "CFOP de combustível sem NCM de combustível.",
        "resultado": "sem sugestão: escolha a natureza",
        "fonte": "HI-139, em _MOTIVO_SEM_NCM_DE_COMBUSTIVEL",
    },
    {
        "sinal": "CSOSN 500 ou CST 60 (ICMS já recolhido), fora de CFOP de combustível.",
        "resultado": "revenda com ST já substituído",
        "fonte": (
            "consulta de 09/10/2026, item 2, e ajuste de integração da DL-083, em "
            "_candidatos_do_item"
        ),
    },
    {
        "sinal": "CSOSN ou CST de substituto tributário (201, 202, 203, 10, 30, 70).",
        "resultado": "venda como substituto tributário (ST retida na saída)",
        "fonte": "consulta de 09/10/2026, item 2, em _candidatos_do_item",
    },
    {
        "sinal": "Dois sinais que apontam naturezas diferentes.",
        "resultado": "sem sugestão: conflito entre sinais",
        "fonte": "consulta de 09/10/2026, item 2, em sugerir_natureza_item",
    },
    {
        "sinal": "Nenhum sinal.",
        "resultado": "sem sugestão: escolha a natureza",
        "fonte": "consulta de 09/10/2026, item 2, em sugerir_natureza_item",
    },
    {
        "sinal": (
            "Padrão de combustível da empresa (posto ou TRR), quando o CFOP não decide e o NCM é "
            "de combustível."
        ),
        "resultado": "combustível para consumo (1,6%); distribuidora não tem padrão",
        "fonte": "DL-084, item 6 (HI-136; PE-85.1), em sugerir_natureza_com_padrao",
    },
    # DL-091 (A1 e A2): sugestão da COMPRA (NF-e de terceiro, finNFe 1, com a empresa destinatária).
    # Vale só para o tipo `entrada`; a saída não lê estas linhas. Fonte: a conversão e os grupos do
    # código, e a consulta de 13/10/2026, seção 2. Nenhuma linha aqui é norma relida.
    {
        "sinal": (
            "Compra com CFOP do emitente x.101 ou x.103 (industrialização), sem sinal de ST (CST "
            "ou CSOSN): o primeiro dígito é convertido (5→1, 6→2, 7→3)."
        ),
        "resultado": "E2 · compra para industrialização (1.101, 2.101 ou 3.101)",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; consulta de 13/10/2026, seção 2",
    },
    {
        "sinal": (
            "Compra com CFOP do emitente x.102 ou x.104 (revenda), sem sinal de ST (CST ou "
            "CSOSN): o primeiro dígito é convertido (5→1, 6→2, 7→3)."
        ),
        "resultado": "E1 · compra para comercialização (1.102, 2.102 ou 3.102)",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; consulta de 13/10/2026, seção 2",
    },
    {
        "sinal": (
            "Compra com ST do emitente: CST 10, 30, 60 ou 70, ou CSOSN 201, 202, 203 ou 500, com "
            "CFOP x.101 a x.104 (esse sinal troca E1 ou E2 por E3); ou CFOP x.401, x.403 ou x.405."
        ),
        "resultado": (
            "E3 · compra com ICMS-ST: 1.401 para x.101, x.103 e x.401; 1.403 para x.102, x.104, "
            "x.403 e x.405"
        ),
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; consulta de 13/10/2026, seção 2",
    },
    {
        "sinal": "Compra com CFOP do emitente x.402 ou x.404.",
        "resultado": "sem sugestão, com ou sem ST: escolha a natureza e o CFOP de entrada",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada (o código não converte esses dois)",
    },
    {
        "sinal": "Compra com CFOP do emitente x.151 ou x.152 (transferência).",
        "resultado": (
            "E8 · transferência recebida (1.151 ou 1.152); o vínculo da filial fica para o HI-111"
        ),
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada",
    },
    {
        "sinal": "Compra com CFOP do emitente x.910 ou x.911 (bonificação ou amostra).",
        "resultado": "E9 · bonificação, doação ou amostra recebida (1.910 ou 1.911)",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada",
    },
    {
        "sinal": "Compra com CFOP do emitente x.655 e NCM de combustível ou lubrificante.",
        "resultado": "E6 · combustível ou lubrificante para revenda (1.652)",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; NCM exigido como na venda (HI-139)",
    },
    {
        "sinal": "Compra com CFOP do emitente x.656 e NCM de combustível ou lubrificante.",
        "resultado": (
            "E7 · combustível ou lubrificante para consumo próprio (1.653); o contador confirma"
        ),
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; NCM exigido como na venda (HI-139)",
    },
    {
        "sinal": (
            "Compra com CFOP do emitente x.655 ou x.656 e NCM ausente ou fora da lista de "
            "combustível."
        ),
        "resultado": "sem sugestão: escolha a natureza e o CFOP de entrada",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; HI-139",
    },
    {
        "sinal": (
            "Compra com qualquer outro CFOP do emitente (uso e consumo, ativo, remessa, serviço), "
            "ou CFOP fora de 5, 6 e 7."
        ),
        "resultado": ("sem sugestão: o produto não sugere E4, E5, E10 nem E11; escolha a natureza"),
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada; consulta de 13/10/2026, seção 2",
    },
    {
        "sinal": "Compra: CFOP de entrada sugerido com o primeiro dígito fixo (5→1, 6→2, 7→3).",
        "resultado": (
            "os três últimos dígitos são do grupo da natureza; sem padrão de grupo, fica vazio "
            "e o contador escolhe"
        ),
        "fonte": "DL-091 (A2), entradas.cfop_de_entrada_para; consulta de 13/10/2026, seção 2",
    },
    {
        "sinal": "Compra: 1.949 (remessa, retorno, consignação e conserto).",
        "resultado": "nunca sugerido: só por escolha manual do contador",
        "fonte": "DL-091 (A1), entradas.sugerir_par_de_entrada e CATALOGO_EFEITOS_NATUREZA_NFE",
    },
)


# ---------------------------------------------------------------------------
# Regras: validação, cadastro, desativação e listagem
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DadosDaRegra:
    """Critérios e resultado, já normalizados. A API e a fila montam este objeto."""

    tipo: str
    cfop: str
    natureza: str
    vigencia_inicio: date
    vigencia_fim: date | None = None
    ncm: str = ""
    ncm_modo: str = ""
    cst_csosn: str = ""
    id_dest: str = ""
    # DL-091 (A2): só a regra de entrada usa estes três. Vazios nas demais.
    crt_emitente: str = ""
    uf_emitente: str = ""
    cfop_entrada: str = ""


def _recusa(mensagem: str):
    return servico.EntradaInvalidaNFe(mensagem)


def validar_dados_da_regra(dados: DadosDaRegra) -> DadosDaRegra:
    """Confere cada critério e devolve os dados normalizados. Recusa com mensagem (400).

    CFOP: 4 dígitos da tabela oficial (critério obrigatório). NCM: vazio, ou exato de 8 dígitos, ou
    prefixo de 2 a 7. CST/CSOSN: 2 ou 3 dígitos, comparado como está na nota. idDest: 1, 2 ou 3.
    Natureza: a que `naturezas_permitidas(tipo)` aceita, e ajuste nunca.
    """
    tipo = (dados.tipo or "").strip()
    if tipo == TipoEscrituracaoNFe.AJUSTE:
        raise _recusa(MENSAGEM_TIPO_AJUSTE)
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA:
        raise _recusa(MENSAGEM_TIPO_DEVOLUCAO_COMPRA)
    if tipo not in TIPOS_COM_REGRA:
        raise _recusa("Tipo da nota inválido: use saída própria, devolução de venda ou entrada.")

    cfop = (dados.cfop or "").strip().replace(".", "")
    if not _CFOP_DE_4_DIGITOS.fullmatch(cfop):
        raise _recusa("CFOP deve ter exatamente 4 dígitos (ex.: 5102 ou 5.102).")
    if consultar_cfop(cfop) is None:
        raise _recusa(
            f"CFOP {cfop} fora da tabela oficial (Informe 2023.002 v2.10): a regra exige um CFOP "
            "da tabela."
        )

    # A5: só dígitos ASCII e pontos. `normalizar_ncm` tira o que não é dígito, e um "22AB" virava
    # "22" em silêncio, um prefixo mais amplo do que o digitado. Dígitos de outro alfabeto (árabe-
    # índico, largura total) passam pelo `\d` do Python e dariam 500 no CHECK do banco.
    ncm_bruto = (dados.ncm or "").strip()
    if ncm_bruto and not _NCM_SO_DIGITOS_E_PONTOS.fullmatch(ncm_bruto):
        raise _recusa(
            "NCM aceita só dígitos e pontos (ex.: 2203.00.00 ou 22030000). Letras, espaços e "
            "outros caracteres não são aceitos."
        )
    ncm = normalizar_ncm(ncm_bruto)
    modo = (dados.ncm_modo or "").strip()
    if ncm:
        if modo == ModoNcmRegraNFe.EXATO:
            if len(ncm) != 8:
                raise _recusa("NCM exato deve ter 8 dígitos. Para parte do NCM, use prefixo.")
        elif modo == ModoNcmRegraNFe.PREFIXO:
            if not 2 <= len(ncm) <= 7:
                raise _recusa("NCM por prefixo deve ter de 2 a 7 dígitos.")
        else:
            raise _recusa("Informe o modo do NCM: exato ou prefixo.")
    elif modo:
        raise _recusa("Modo do NCM sem NCM: informe o NCM ou deixe o modo vazio.")

    cst_csosn = (dados.cst_csosn or "").strip()
    if cst_csosn and not _CST_CSOSN.fullmatch(cst_csosn):
        raise _recusa("CST ou CSOSN deve ter 2 ou 3 dígitos.")

    id_dest = (dados.id_dest or "").strip()
    if id_dest and id_dest not in _IDS_DEST:
        raise _recusa("idDest deve ser 1 (interna), 2 (interestadual) ou 3 (exterior).")

    natureza = (dados.natureza or "").strip()
    if natureza not in CATALOGO_NATUREZA_NFE:
        raise _recusa("Natureza desconhecida: escolha uma das naturezas do catálogo fiscal.")
    if natureza not in servico.naturezas_permitidas(tipo):
        raise _recusa(
            f"A natureza '{NaturezaOperacaoNFe(natureza).label}' não cabe em "
            f"{_rotulo_do_tipo(tipo)}: escolha uma natureza permitida para o tipo."
        )
    if natureza in NATUREZAS_DE_COMBUSTIVEL_QUE_EXIGEM_NCM and not ncm:
        raise _recusa(
            f"A natureza '{NaturezaOperacaoNFe(natureza).label}' exige NCM (exato ou por prefixo): "
            "sem NCM, a regra levaria qualquer produto do CFOP ao regime de combustível (HI-139). "
            "Informe o NCM de combustível."
        )

    # DL-091 (A2): CRT, UF e CFOP de entrada só existem na regra de entrada (o banco recusa o
    # resto). O CFOP de entrada fixado é conferido contra o CFOP do critério e a natureza, com a
    # mesma regra da escrituração: primeiro dígito e grupo.
    crt = (dados.crt_emitente or "").strip()
    uf = (dados.uf_emitente or "").strip().upper()
    cfop_de_entrada = (dados.cfop_entrada or "").strip().replace(".", "")
    if tipo != TipoEscrituracaoNFe.ENTRADA and (crt or uf or cfop_de_entrada):
        raise _recusa(MENSAGEM_CRITERIO_SO_NA_ENTRADA)
    if crt and crt not in CRTS_DO_EMITENTE_NA_REGRA:
        raise _recusa(
            "CRT do emitente deve ser 1 (Simples Nacional), 2 (Simples, excesso de sublimite), "
            "3 (regime normal) ou 4 (MEI)."
        )
    if uf and uf not in SIGLAS_DE_UF_DO_EMITENTE_NA_REGRA:
        raise _recusa("UF do emitente deve ser uma das 27 siglas (ex.: TO).")
    if cfop_de_entrada:
        cfop_de_entrada = entradas.validar_cfop_de_entrada_para(cfop, natureza, cfop_de_entrada)

    inicio = dados.vigencia_inicio
    if not isinstance(inicio, date):
        raise _recusa("Informe o início da vigência.")
    fim = dados.vigencia_fim
    if fim is not None and fim < inicio:
        raise _recusa("O fim da vigência é anterior ao início.")

    return DadosDaRegra(
        tipo=tipo,
        cfop=cfop,
        natureza=natureza,
        vigencia_inicio=inicio,
        vigencia_fim=fim,
        ncm=ncm,
        ncm_modo=modo if ncm else "",
        cst_csosn=cst_csosn,
        id_dest=id_dest,
        crt_emitente=crt,
        uf_emitente=uf,
        cfop_entrada=cfop_de_entrada,
    )


def avisos_da_regra(dados: DadosDaRegra, escopo: str) -> tuple[str, ...]:
    """Avisos que NÃO bloqueiam a criação (consulta de 12/10/2026, itens 1 e 3).

    - Natureza de combustível com NCM (ou prefixo) que alcança lubrificante: o lubrificante fica
    fora
      do 1,6% (Lei 9.249, art. 15, § 1º, I, citada no código). Pode ser intenção, com trilha.
    - Regra de ESCRITÓRIO com CST de 2 dígitos (regime normal): o cliente do Simples emite CSOSN e a
      regra não o alcança. Só aviso, porque a equivalência CST x CSOSN fica para o corte 2.
    """
    avisos = []
    if dados.natureza in NATUREZAS_DE_COMBUSTIVEL_QUE_EXIGEM_NCM and dados.ncm:
        if dados.ncm_modo == ModoNcmRegraNFe.EXATO:
            alcanca = dados.ncm in NCM_LUBRIFICANTE
        else:
            alcanca = any(ncm.startswith(dados.ncm) for ncm in NCM_LUBRIFICANTE)
        if alcanca:
            avisos.append(
                "O NCM desta regra alcança NCM de lubrificante, que fica fora do 1,6%: a natureza "
                "de combustível não cabe a ele. Confira antes de usar."
            )
    if escopo == ESCOPO_ESCRITORIO and len(dados.cst_csosn) == 2:
        avisos.append(
            "CST de regime normal (2 dígitos): clientes do Simples emitem CSOSN, e esta regra de "
            "escritório não os alcança."
        )
    return tuple(avisos)


def _vigencias_se_cruzam(a_inicio, a_fim, b_inicio, b_fim) -> bool:
    a_fim = a_fim or date.max
    b_fim = b_fim or date.max
    return a_inicio <= b_fim and b_inicio <= a_fim


def _mesmos_criterios(regra, dados: DadosDaRegra) -> bool:
    return (
        regra.tipo == dados.tipo
        and regra.cfop == dados.cfop
        and regra.ncm == dados.ncm
        and regra.ncm_modo == dados.ncm_modo
        and regra.cst_csosn == dados.cst_csosn
        and regra.id_dest == dados.id_dest
        and regra.crt_emitente == dados.crt_emitente
        and regra.uf_emitente == dados.uf_emitente
    )


def _recusar_se_duplicada(escritorio_id: int, empresa_id: int | None, dados: DadosDaRegra) -> None:
    """409 (`RegraDuplicada`) se já há regra ATIVA do mesmo escopo, critérios e vigência cruzada.

    Usada pela criação (com a trava do escritório) e pela prévia de impacto (A2): a prévia recusa
    antes de calcular, em vez de deixar a regra igual empatar com a existente.
    """
    existentes = RegraClassificacaoNFe.objects.filter(
        escritorio_id=escritorio_id,
        empresa_id=empresa_id,
        tipo=dados.tipo,
        cfop=dados.cfop,
        desativada_em__isnull=True,
    )
    for regra in existentes:
        if _mesmos_criterios(regra, dados) and _vigencias_se_cruzam(
            regra.vigencia_inicio, regra.vigencia_fim, dados.vigencia_inicio, dados.vigencia_fim
        ):
            raise RegraDuplicada(
                f"Já existe a regra n.º {regra.pk} com os mesmos critérios e vigência que se "
                "cruza, no mesmo escopo. Desative-a com motivo, ou ajuste a vigência."
            )


def criar_regra(
    *, escritorio: Escritorio, empresa, dados: DadosDaRegra, usuario, request=None, agora=None
) -> RegraClassificacaoNFe:
    """Cria a regra do escritório (`empresa=None`) ou da empresa. Recusa com 400 ou 409.

    A trava é do ESCRITÓRIO: duas criações ao mesmo tempo passam uma de cada vez, e a segunda vê a
    primeira ao checar duplicidade. Quem decide QUEM pode criar é a API, antes de chamar isto.
    """
    dados = validar_dados_da_regra(dados)
    with transaction.atomic():
        Escritorio.objects.select_for_update(of=("self",)).get(pk=escritorio.pk)
        _recusar_se_duplicada(escritorio.pk, empresa.pk if empresa is not None else None, dados)
        regra = RegraClassificacaoNFe(
            escritorio=escritorio,
            empresa=empresa,
            tipo=dados.tipo,
            cfop=dados.cfop,
            ncm=dados.ncm,
            ncm_modo=dados.ncm_modo,
            cst_csosn=dados.cst_csosn,
            id_dest=dados.id_dest,
            crt_emitente=dados.crt_emitente,
            uf_emitente=dados.uf_emitente,
            cfop_entrada=dados.cfop_entrada,
            natureza=dados.natureza,
            vigencia_inicio=dados.vigencia_inicio,
            vigencia_fim=dados.vigencia_fim,
            criada_por=usuario,
        )
        regra.save()
        registrar(
            acao="classificacao_nfe.regra_criada",
            usuario=usuario,
            escritorio=escritorio,
            objeto=regra,
            request=request,
            detalhes=_detalhes_da_regra(regra),
        )
    return regra


def desativar_regra(
    regra: RegraClassificacaoNFe, *, motivo: str, usuario, request=None, agora=None
) -> RegraClassificacaoNFe:
    """REVOGA a regra (DL-087, A1): ela deixa de casar com QUALQUER nota, pendente ou futura.

    Grava o fim da vigência na véspera do início (`vigencia_revogada`), quem, quando e o motivo. A
    escrituração já efetivada não muda e guarda a origem que teve. Não se apaga regra. Recusa 400
    (motivo vazio ou longo) e 409 (já revogada, ou revogada por outra ação ao mesmo tempo).
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise _recusa("Informe o motivo da desativação.")
    if len(motivo) > servico.MOTIVO_MAXIMO:
        raise _recusa(f"O motivo tem no máximo {servico.MOTIVO_MAXIMO} caracteres.")
    agora = agora or timezone.now()
    with transaction.atomic():
        Escritorio.objects.select_for_update(of=("self",)).get(pk=regra.escritorio_id)
        atual = RegraClassificacaoNFe.objects.get(pk=regra.pk)
        if not atual.ativa:
            raise servico.EscrituracaoNFeErro(
                f"A regra n.º {atual.pk} já está desativada. Nada foi alterado."
            )
        novo_fim = vigencia_revogada(atual.vigencia_inicio)
        # O filtro `desativada_em__isnull` torna a revogação condicional: duas chamadas ao mesmo
        # tempo, só uma grava.
        gravadas = RegraClassificacaoNFe.objects.filter(
            pk=atual.pk, desativada_em__isnull=True
        ).update(
            vigencia_fim=novo_fim,
            desativada_em=agora,
            desativada_por=usuario,
            motivo_desativacao=motivo,
        )
        if gravadas != 1:
            raise servico.EscrituracaoNFeErro(
                f"A regra n.º {atual.pk} foi desativada por outra ação. Nada foi alterado."
            )
        atual.refresh_from_db()
        registrar(
            acao="classificacao_nfe.regra_desativada",
            usuario=usuario,
            escritorio=atual.escritorio,
            objeto=atual,
            request=request,
            detalhes={
                **_detalhes_da_regra(atual),
                "motivo": motivo,
                "efeito": "revogada",
                "vigencia_fim_gravada": novo_fim.isoformat(),
            },
        )
    return atual


def confirmados_da_regra(empresa, regra: RegraClassificacaoNFe):
    """Origens gravadas (um item confirmado cada) que vieram desta regra NA EMPRESA da consulta.

    É a lista de "ver notas" (A8): nota e item, a natureza confirmada e o estado da escrituração
    (rascunho, efetivada ou estornada). Outra empresa do mesmo escritório não entra.
    """
    return (
        OrigemNaturezaItemNFe.objects.filter(
            regra_classificacao=regra,
            natureza_item__escrituracao__empresa_id=empresa.pk,
        )
        .select_related(
            "natureza_item__escrituracao",
            "natureza_item__item__documento",
        )
        .order_by("natureza_item__escrituracao__pk", "natureza_item__item__n_item")
    )


def contagem_de_confirmados(empresa) -> Count:
    """Anotação `Count` dos itens confirmados que vieram da regra, SÓ da empresa da consulta (A3).

    Sem o filtro, a contagem da regra do escritório somava as confirmações de todas as empresas, e
    a empresa consultada via o volume de outro cliente.
    """
    return Count(
        "itens_confirmados",
        filter=Q(itens_confirmados__natureza_item__escrituracao__empresa_id=empresa.pk),
    )


def _detalhes_da_regra(regra: RegraClassificacaoNFe) -> dict:
    """Só critérios e vigência. Nada de dado pessoal nem de cliente além do id da empresa."""
    return {
        "regra_id": regra.pk,
        "escopo": ESCOPO_EMPRESA if regra.empresa_id else ESCOPO_ESCRITORIO,
        "empresa_id": regra.empresa_id,
        "tipo": regra.tipo,
        "cfop": regra.cfop,
        "ncm": regra.ncm,
        "ncm_modo": regra.ncm_modo,
        "cst_csosn": regra.cst_csosn,
        "id_dest": regra.id_dest,
        "crt_emitente": regra.crt_emitente,
        "uf_emitente": regra.uf_emitente,
        "cfop_entrada": regra.cfop_entrada,
        "natureza": regra.natureza,
        "vigencia_inicio": regra.vigencia_inicio.isoformat(),
        "vigencia_fim": regra.vigencia_fim.isoformat() if regra.vigencia_fim else None,
    }


def regras_da_empresa(empresa, *, escopo: str | None = None, situacao: str | None = None):
    """Regras que VALEM para a empresa: as do escritório e as dela (nunca as de outra empresa).

    `escopo`: "empresa" ou "escritorio" (None = as duas). `situacao`: "ativa", "desativada" ou None.
    """
    consulta = RegraClassificacaoNFe.objects.filter(escritorio_id=empresa.escritorio_id)
    if escopo == ESCOPO_EMPRESA:
        consulta = consulta.filter(empresa_id=empresa.pk)
    elif escopo == ESCOPO_ESCRITORIO:
        consulta = consulta.filter(empresa__isnull=True)
    else:
        consulta = consulta.filter(Q(empresa__isnull=True) | Q(empresa_id=empresa.pk))
    if situacao == "ativa":
        consulta = consulta.filter(desativada_em__isnull=True)
    elif situacao == "desativada":
        consulta = consulta.filter(desativada_em__isnull=False)
    return consulta.order_by("pk")


# ---------------------------------------------------------------------------
# Fila "a classificar"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrupoAClassificar:
    """Itens das notas a escriturar sem sugestão ou em conflito, com um critério em comum."""

    chave: str
    tipo: str
    cfop: str
    ncm: str
    cst_csosn: str
    id_dest: str
    motivo: str
    situacao: str
    notas: int
    itens: int
    valor: Decimal
    criavel: bool
    motivo_nao_criavel: str
    criterios_da_regra: dict


@dataclass(frozen=True)
class FilaAClassificar:
    ano: int
    mes: int
    grupos: tuple[GrupoAClassificar, ...]
    quantidade_notas: int
    quantidade_itens: int
    valor: Decimal
    notas_sem_leitura: int
    # DL-087, item 8: mês com confirmação "confirmada". A escrituração NÃO é bloqueada nele (o
    # código
    # não tem gate de competência): a efetivação reabre o mês e o marca "a retificar" (DL-074). Por
    # isso os grupos continuam acionáveis, com o aviso.
    mes_confirmado: bool = False
    aviso_do_mes: str = ""


MENSAGEM_MES_CONFIRMADO = (
    "Mês já confirmado: escriturar uma nota dele reabre a confirmação e a marca a retificar "
    "(DL-074). A regra não muda nota efetivada."
)


def _chave_do_grupo(*partes) -> str:
    texto = json.dumps(list(partes), separators=(",", ":"), ensure_ascii=False)
    return "fila-" + hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _itens_em_lotes(documento_ids: list[int]):
    """Itens das notas, em consultas de 5.000 notas (o `IN` fica longe do limite de parâmetros)."""
    for inicio in range(0, len(documento_ids), 5000):
        bloco = documento_ids[inicio : inicio + 5000]
        yield from (
            ItemNFe.objects.filter(documento_id__in=bloco)
            .only("documento_id", "n_item", "cfop", "cst", "csosn", "ncm", "v_prod")
            .order_by("documento_id", "n_item")
        )


def _itens_a_classificar(empresa, ano: int, mes: int):
    """Contexto, notas do mês pendentes, notas sem leitura e os pares (nota, item) sem natureza
    escolhida. Uma consulta de notas, uma de rascunhos, uma de itens por 5.000 notas.

    Só notas LIDAS entram nos pares; as não lidas contam à parte. Item de rascunho com natureza já
    escolhida sai: ele já está classificado.
    """
    contexto = contexto_da_empresa(empresa)
    notas = [
        nota
        for nota in servico.notas_do_mes(empresa, ano, mes)
        if nota.tipo is not None
        and nota.situacao in (servico.SITUACAO_A_ESCRITURAR, servico.SITUACAO_RASCUNHO)
    ]
    lidas = [n for n in notas if n.leitura_estado == LeituraItensNFe.ESTADO_LIDA]
    sem_leitura = len(notas) - len(lidas)
    if not lidas:
        return contexto, notas, sem_leitura, []
    escolhidas = set(
        NaturezaItemNFe.objects.filter(
            escrituracao_id__in=[n.escrituracao.pk for n in lidas if n.escrituracao is not None]
        )
        .exclude(natureza="")
        .values_list("item_id", flat=True)
    )
    por_documento = {n.documento.pk: n for n in lidas}
    pares = [
        (por_documento[item.documento_id], item)
        for item in _itens_em_lotes(list(por_documento))
        if item.pk not in escolhidas
    ]
    return contexto, notas, sem_leitura, pares


def mes_confirmado_da_empresa(empresa, ano: int, mes: int) -> bool:
    confirmacao = receita_servico.confirmacao_do_mes(empresa, ano, mes)
    return confirmacao is not None and confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA


def _chave_do_grupo_da_fila(nota, item, sugestao: servico.Sugestao) -> tuple:
    """Critério do grupo da fila: tipo, CFOP, NCM, CST/CSOSN, idDest e motivo, e a situação."""
    situacao = (
        SITUACAO_CONFLITO if sugestao.motivo.startswith("conflito") else SITUACAO_SEM_SUGESTAO
    )
    return (
        nota.tipo,
        item.cfop,
        normalizar_ncm(item.ncm),
        item.csosn or item.cst or "",
        nota.documento.id_dest or "",
        sugestao.motivo,
        situacao,
    )


def _motivo_nao_criavel(tipo: str, cfop: str, criavel: bool) -> str:
    """Por que o grupo da fila não vira regra. Vazio quando vira."""
    if consultar_cfop(cfop) is None:
        return f"CFOP {cfop} fora da tabela oficial: a regra exige um CFOP da tabela."
    if not criavel and tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA:
        return (
            "retorno em finNFe 4: sem regra (contrato da DL-091, A1). Escolha a natureza na nota."
        )
    return ""


def fila_a_classificar(empresa, ano: int, mes: int) -> FilaAClassificar:
    """Itens sem sugestão ou em conflito, das notas a escriturar e dos rascunhos sem natureza.

    Cada grupo reúne itens pelo tipo, CFOP, NCM, CST/CSOSN, idDest e motivo, e traz os critérios
    para
    criar a regra. Só notas lidas entram; as demais contam em `notas_sem_leitura`.
    """
    contexto, notas, sem_leitura, pares = _itens_a_classificar(empresa, ano, mes)
    acumulado: dict[tuple, dict] = {}
    notas_com_pendencia: set[int] = set()
    for nota, item in pares:
        sugestao = sugerir_natureza_com_regras(contexto, nota.documento, item, nota.tipo)
        if sugestao.natureza is not None:
            continue
        chave = _chave_do_grupo_da_fila(nota, item, sugestao)
        grupo = acumulado.setdefault(chave, {"notas": set(), "itens": 0, "valor": Decimal("0.00")})
        grupo["notas"].add(nota.documento.pk)
        grupo["itens"] += 1
        grupo["valor"] += item.v_prod
        notas_com_pendencia.add(nota.documento.pk)

    inicio_do_mes = date(ano, mes, 1)
    grupos = []
    for (tipo, cfop, ncm, cst_csosn, id_dest, motivo, situacao), dados in acumulado.items():
        criavel = consultar_cfop(cfop) is not None and tipo != TipoEscrituracaoNFe.DEVOLUCAO_COMPRA
        criterios = {
            "tipo": tipo,
            "cfop": cfop,
            "ncm": ncm if len(ncm) == 8 else "",
            "ncm_modo": ModoNcmRegraNFe.EXATO if len(ncm) == 8 else "",
            "cst_csosn": cst_csosn if len(cst_csosn) in (2, 3) else "",
            "id_dest": id_dest if id_dest in _IDS_DEST else "",
            # A regra começa no dia 1 do mês da fila: as notas do mês inteiro caem nela.
            "vigencia_inicio": inicio_do_mes.isoformat(),
        }
        grupos.append(
            GrupoAClassificar(
                chave=_chave_do_grupo(tipo, cfop, ncm, cst_csosn, id_dest, motivo, situacao),
                tipo=tipo,
                cfop=cfop,
                ncm=ncm,
                cst_csosn=cst_csosn,
                id_dest=id_dest,
                motivo=motivo,
                situacao=situacao,
                notas=len(dados["notas"]),
                itens=dados["itens"],
                valor=dados["valor"],
                criavel=criavel,
                motivo_nao_criavel=_motivo_nao_criavel(tipo, cfop, criavel),
                criterios_da_regra=criterios,
            )
        )
    grupos.sort(key=lambda g: (-g.itens, g.chave))
    mes_confirmado = mes_confirmado_da_empresa(empresa, ano, mes)
    return FilaAClassificar(
        ano=ano,
        mes=mes,
        grupos=tuple(grupos),
        quantidade_notas=len(notas_com_pendencia),
        quantidade_itens=sum(g.itens for g in grupos),
        valor=sum((g.valor for g in grupos), Decimal("0.00")),
        notas_sem_leitura=sem_leitura,
        mes_confirmado=mes_confirmado,
        aviso_do_mes=MENSAGEM_MES_CONFIRMADO if mes_confirmado else "",
    )


@dataclass(frozen=True)
class PreviaDeImpacto:
    """O que uma regra AINDA NÃO SALVA mudaria, no mês, para a empresa. Nada é gravado."""

    ano: int
    mes: int
    escopo: str
    itens_a_escriturar: int
    itens_que_mudam: int
    itens_que_saem_da_fila: int
    itens_que_entram_na_fila: int
    grupos_afetados: int
    notas_afetadas: int
    avisos: tuple[str, ...]
    # DL-087, A7: o mês já confirmado não bloqueia, mas a prévia diz (como a fila).
    mes_confirmado: bool = False
    aviso_do_mes: str = ""


def previa_de_impacto(
    empresa, ano: int, mes: int, dados: DadosDaRegra, escopo: str
) -> PreviaDeImpacto:
    """Uma prévia de impacto. Ver `previas_de_impacto`, que é quem calcula."""
    return previas_de_impacto(empresa, ano, mes, [dados], escopo)[0]


def previas_de_impacto(
    empresa, ano: int, mes: int, dados_das_variantes, escopo: str
) -> list[PreviaDeImpacto]:
    """Conta, sem gravar, o efeito de uma ou mais variantes de regra AINDA NÃO salva (A6).

    `dados_das_variantes[0]` é a regra completa, e é a única que checa duplicidade (409, A2). As
    demais são variantes (p. ex., a mesma regra sem o NCM) e saem com as mesmas contagens. Tudo numa
    PASSADA: a leitura das notas e dos itens e a sugestão ATUAL de cada item são feitas uma vez; a
    sugestão de cada variante é a única conta extra por item.

    Os critérios passam pela mesma validação da criação (400 se inválidos). A regra não tem id: as
    mensagens dela dizem "a regra nova". Não grava nada.
    """
    if escopo not in (ESCOPO_EMPRESA, ESCOPO_ESCRITORIO):
        raise _recusa("Escopo inválido: use empresa ou escritório.")
    validadas = [validar_dados_da_regra(dados) for dados in dados_das_variantes]
    completa = validadas[0]
    _recusar_se_duplicada(
        empresa.escritorio_id, empresa.pk if escopo == ESCOPO_EMPRESA else None, completa
    )
    contexto, _notas, _sem_leitura, pares = _itens_a_classificar(empresa, ano, mes)
    antes = [
        sugerir_natureza_com_regras(contexto, nota.documento, item, nota.tipo)
        for nota, item in pares
    ]
    mes_confirmado = mes_confirmado_da_empresa(empresa, ano, mes)
    resultados = []
    for dados in validadas:
        virtual = RegraClassificacaoNFe(
            escritorio_id=empresa.escritorio_id,
            empresa_id=empresa.pk if escopo == ESCOPO_EMPRESA else None,
            tipo=dados.tipo,
            cfop=dados.cfop,
            ncm=dados.ncm,
            ncm_modo=dados.ncm_modo,
            cst_csosn=dados.cst_csosn,
            id_dest=dados.id_dest,
            crt_emitente=dados.crt_emitente,
            uf_emitente=dados.uf_emitente,
            cfop_entrada=dados.cfop_entrada,
            natureza=dados.natureza,
            vigencia_inicio=dados.vigencia_inicio,
            vigencia_fim=dados.vigencia_fim,
        )
        contexto_com_a_nova = replace(contexto, regras=(*contexto.regras, virtual))
        mudam = saem = entram = 0
        notas_afetadas: set[int] = set()
        grupos_afetados: set[tuple] = set()
        for (nota, item), resposta_atual in zip(pares, antes, strict=True):
            depois = sugerir_natureza_com_regras(
                contexto_com_a_nova, nota.documento, item, nota.tipo
            )
            if resposta_atual.natureza == depois.natureza:
                continue
            mudam += 1
            notas_afetadas.add(nota.documento.pk)
            if resposta_atual.natureza is None:
                saem += 1
                grupos_afetados.add(_chave_do_grupo_da_fila(nota, item, resposta_atual))
            elif depois.natureza is None:
                entram += 1
                grupos_afetados.add(_chave_do_grupo_da_fila(nota, item, depois))
        resultados.append(
            PreviaDeImpacto(
                ano=ano,
                mes=mes,
                escopo=escopo,
                itens_a_escriturar=len(pares),
                itens_que_mudam=mudam,
                itens_que_saem_da_fila=saem,
                itens_que_entram_na_fila=entram,
                grupos_afetados=len(grupos_afetados),
                notas_afetadas=len(notas_afetadas),
                avisos=avisos_da_regra(dados, escopo),
                mes_confirmado=mes_confirmado,
                aviso_do_mes=MENSAGEM_MES_CONFIRMADO if mes_confirmado else "",
            )
        )
    return resultados
