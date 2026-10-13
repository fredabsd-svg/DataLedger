"""Escrituração das NF-e de saída e da devolução de venda — DL-081, frente A (domínio).

Plano: docs/planos/DL-081-escrituracao-das-nfe-de-saida.md. Fonte normativa: consulta de
09/10/2026 (docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md), itens 1 a 7.
Hipóteses HI-117 a HI-124 (requisitos.md). Decisões que o código não explica sozinho:

- ELEGIBILIDADE. Saída própria: a empresa é emitente, `tpNF` 1 e `finNFe` 1, modelos 55 e 65.
  Devolução de venda: `finNFe` 4, em nota de terceiro em que a empresa é destinatária, ou nota
  própria de entrada (emitente com `tpNF` 0). Ajuste: `finNFe` 2, 3, 5 ou 6, só na saída própria.
  Compra de NF-e modelo 55 com finNFe 1 (empresa destinatária, tpNF 1) é ENTRADA, da DL-091
  (`entradas.py`). Os outros casos de entrada continuam fora (a recepção da DL-080 vale como está).
- SUGESTÃO DE NATUREZA, por item, sem gravar nada. Sinais (consulta, item 2): `finNFe` decide
  devolução e ajuste; depois CFOP (com a tabela oficial), CST/CSOSN e `idDest`. Se dois sinais
  apontam naturezas DIFERENTES, a sugestão fica em branco ("conflito"). CFOP fora da tabela
  fica "a classificar". Comercial exportadora, bonificação e monofásico nunca têm sugestão.
- DEVOLUÇÃO identificada pelo `indDevol` da tabela oficial, nunca pela faixa do CFOP.
- RECEITA DO ITEM (DL-083): a receita de cada item é `itens_nfe.receita_do_item`, com a parcela do
  resíduo de item que não é receita atribuída à nota (HI-138, `atribuir_receita_da_nota`). Item
  `indTot` 0 não tem o vProd na receita; o frete, o seguro e as outras despesas de item que não é
  receita vão para a receita da venda da mesma nota, com aviso. Toda soma de receita passa pela
  atribuição.
- CONFERÊNCIA (HI-119; DL-083): a receita de TODOS os itens tem de bater com
  `vNF − vST − vFCPST − vIPI − vII − vIPIDevol`, com tolerância ZERO. Nota sem vNF não é
  conferida: é recusa, porque o total é obrigatório no XSD. vST, vFCPST, vIPI, vII e vIPIDevol
  ausentes valem zero só nessa fórmula, e a divergência bloqueia a efetivação com os valores na
  mensagem. A atribuição (HI-138) bloqueia nos três casos de `itens_nfe`: sem item de receita, com
  resíduo negativo maior que a receita, e sem base para rateio.
- 2027 (HI-133; consulta PE-84.4; DL-088 A2, HI-149): a NT 2026.008 diz que IBS, CBS e IS compõem
  o `vProd` a partir de 2027 e não diz como fica o vNF. Para a empresa do Simples no REGIME ÚNICO
  do semestre, a nota de 2027 é efetivada com receita = `vProd − vDesc`
   (`itens_nfe.receita_do_item_2027` — o
   desconto incondicional sai da receita bruta, LC 123, art. 3º, § 1º; correção do achado A2 da
   auditoria da DL-088),
  sem a conferência W16 (não há identidade publicada para o vNF de 2027), e o `vProdLiq` vira
  memória quando o leitor o trouxer (BL-687). Para o Presumido e para quem optou pelo regime
  regular a recusa continua, cada caso com o motivo nomeado (`motivo_bloqueio_efetivacao`), até a
  leitura do DL 1.598, art. 12, § 4º.
- Competência = mês de `dhEmi` no fuso de São Paulo (consulta, item 1). Na ENTRADA (DL-091), o
  mês da `data_entrada` (HI-158).
- Nada aqui calcula ICMS, guia ou alíquota. Só se escritura e se confere.
- Concorrência: cada serviço que escreve roda em `transaction.atomic()` e trava a EMPRESA
  (`receita.travar_empresa`) antes do vínculo, na mesma ordem da DL-072/DL-074. A restrição
  parcial do banco é a segunda defesa. A trilha entra na MESMA transação.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import RegimeTributario
from apps.fiscal import receita as receita_servico
from apps.fiscal import services
from apps.fiscal.cfop import (
    cfop as consultar_cfop,
)
from apps.fiscal.cfop import (
    e_devolucao_de_combustivel,
    e_devolucao_de_combustivel_para_consumo,
)
from apps.fiscal.entradas import AVISO_DEVOLUCAO_DE_COMPRA, TEXTOS_DE_DEVOLUCAO_DE_COMPRA
from apps.fiscal.formatacao_ptbr import valor_ptbr
from apps.fiscal.itens_nfe import (
    MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR,  # noqa: F401 (reexportada: a API e a tela a comparam)
    VERSAO_LEITOR_ITENS,
    ResiduoNaoAtribuivel,
    atribuicao_pelo_vprod,
    atribuir_receita_da_nota,
    atribuir_receita_da_nota_efetivada,
    avisos_da_atribuicao,
    ler_itens,
    receita_do_item,
    receita_do_item_2027,
)
from apps.fiscal.models import (
    ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA,
    ANEXO_E_SEGMENTO_DA_DEVOLUCAO,
    ANEXO_I,
    ANEXO_II,
    CATALOGO_NATUREZA_NFE,
    NATUREZAS_DE_ENTRADA,
    NATUREZAS_DE_MERCADORIA,
    EscrituracaoNFe,
    EstadoEscrituracao,
    EventoNFe,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    OrigemNaturezaItemNFe,
    PapelNFe,
    SegmentoDevolucao,
    TipoEscrituracaoNFe,
    VinculoNFeEmpresa,
    classificacao_da_venda,
    e_devolucao_de_exportacao,
    mercado_da_natureza_nfe,
    papel_da_natureza_nfe,
    segmento_da_mercadoria,
    segmentos_permitidos,
)
from apps.fiscal.ncm_combustivel import (
    NCM_COMBUSTIVEL,
    NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL,
    NCM_LUBRIFICANTE,
    normalizar_ncm,
)
from apps.fiscal.services import CODIGOS_CANCELAMENTO_NFE, CODIGOS_EFETIVOS_NFE

FUSO_SP = ZoneInfo("America/Sao_Paulo")
MOTIVO_MAXIMO = 500
_NOME_RESTRICAO_UNICA = "escrituracao_nfe_ativa_unica_por_vinculo"

# Naturezas que só cabem em um tipo de nota (consulta, item 2 e Hipóteses 2 e 3).
_NATUREZA_DE_AJUSTE = NaturezaOperacaoNFe.AJUSTE
# Devolução de venda: a natureza comum (deduz do 8%) e a de combustível para consumo (deduz do 1,6%,
# HI-140). A escolha é do contador, e a sugestão só aponta a segunda com CFOP e NCM que dizem isso.
_NATUREZAS_DE_DEVOLUCAO = frozenset(
    {
        NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
    }
)
_NATUREZA_DE_DEVOLUCAO = NaturezaOperacaoNFe.DEVOLUCAO_VENDA
_NATUREZA_DE_DEVOLUCAO_DE_COMPRA = NaturezaOperacaoNFe.DEVOLUCAO_COMPRA

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
ORIGEM_NCM_LUBRIFICANTE = (
    "NCM de lubrificante: fora do 1,6% (Lei 9.249, art. 15, § 1º, I; revenda a 8%)"
)
# NCM de combustível que o CFOP de "combustíveis ou lubrificantes" confirma: a lista positiva mais
# álcool e diesel B (HI-139). Com CFOP genérico, só a lista positiva conta (ver
# `_sugestao_de_devolucao`).
_NCM_DE_COMBUSTIVEL_PELO_CFOP = NCM_COMBUSTIVEL | NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL
_MOTIVO_SEM_NCM_DE_COMBUSTIVEL = (
    "sem sugestão: CFOP de combustível com NCM ausente ou fora da lista de combustível "
    "(escolha a natureza)"
)

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


class DivergenciaComVnf(EscrituracaoNFeErro):
    """A receita dos itens não bate com a nota (conferência W16). Tipo próprio, para a tela tratar
    SÓ este caso como divergência. Os bloqueios de regra não decidida (PE-85) não são
    divergência."""


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
        if tp_nf == "1" and fin == "4" and documento.modelo == "55":
            # DL-091 (contrato do arquiteto): finNFe 4 é devolução/retorno genérico. A devolução de
            # compra do cliente sai assim. Só `devolucao_compra` cabe aqui (`naturezas_permitidas`).
            return TipoEscrituracaoNFe.DEVOLUCAO_COMPRA
        if tp_nf == "1" and fin in ("2", "3", "5", "6"):
            return TipoEscrituracaoNFe.AJUSTE
        if tp_nf == "0" and fin == "4":
            # Nota própria de entrada que devolve venda (consulta, item 2, natureza 9).
            return TipoEscrituracaoNFe.DEVOLUCAO
        return None
    if papel == PapelNFe.DESTINATARIO and fin == "4":
        # Devolução de venda recebida: a nota é de terceiro e a empresa é a destinatária.
        return TipoEscrituracaoNFe.DEVOLUCAO
    if papel == PapelNFe.DESTINATARIO and fin == "1" and tp_nf == "1" and documento.modelo == "55":
        # DL-091 (A1): compra de NF-e modelo 55 (tpNF 1 do fornecedor, finNFe 1). NFC-e (65) e
        # tpNF 0 de terceiro ficam de fora, com motivo nomeado (`motivo_fora_da_escrituracao`).
        return TipoEscrituracaoNFe.ENTRADA
    return None


def motivo_fora_da_escrituracao(documento, papel: str) -> str:
    """Por que a nota não entra na escrituração. Nomeado, nunca genérico."""
    if documento.modelo not in ("55", "65"):
        return "modelo fora da escrituração de NF-e (só 55 e 65)."
    if papel == PapelNFe.DESTINATARIO:
        # DL-091 (A1): recusas nomeadas da compra. Entrada de terceiro com finNFe 1 e modelo 55 é
        # escriturável; o que sobra aqui tem motivo próprio.
        if documento.modelo == "65" and documento.fin_nfe != "4":
            return (
                "NFC-e em que a empresa é destinatária: fora desta escrituração "
                "(NFC-e como compra: confirmar)."
            )
        if documento.tp_nf == "0" and documento.fin_nfe != "4":
            return (
                "entrada emitida por terceiro com tpNF 0: confirme o fato antes de escriturar "
                f"(finNFe {documento.fin_nfe})."
            )
        if documento.fin_nfe in ("2", "3"):
            return (
                f"nota de terceiro com finNFe {documento.fin_nfe} (ajuste de entrada): "
                "fora desta escrituração, como antes da DL-091."
            )
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
    """Naturezas aceitas por tipo de nota. Ajuste só ajuste; devolução só as de devolução
    (HI-140)."""
    if tipo == TipoEscrituracaoNFe.AJUSTE:
        return frozenset({_NATUREZA_DE_AJUSTE})
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO:
        return frozenset(_NATUREZAS_DE_DEVOLUCAO)
    if tipo == TipoEscrituracaoNFe.ENTRADA:
        # DL-091 (A1): só E1 a E11. Nenhuma natureza de saída ou de devolução de venda cabe aqui.
        return frozenset(NATUREZAS_DE_ENTRADA)
    if tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA:
        # DL-091 (contrato do arquiteto): finNFe 4 em saída própria só leva devolução de compra.
        # Revenda
        # e as demais naturezas de receita não cabem: é o que protege a receita.
        return frozenset({_NATUREZA_DE_DEVOLUCAO_DE_COMPRA})
    # Saída própria (e o tipo vazio das consultas de sugestão): tudo do catálogo de saída, inclusive
    # `devolucao_compra` (saída com indDevol 1). Naturezas de entrada não cabem.
    return (
        frozenset(CATALOGO_NATUREZA_NFE)
        - {_NATUREZA_DE_AJUSTE}
        - _NATUREZAS_DE_DEVOLUCAO
        - NATUREZAS_DE_ENTRADA
    )


# ---------------------------------------------------------------------------
# Sugestão de natureza (consulta, item 2). Nunca grava: quem grava é o contador.
# ---------------------------------------------------------------------------


# DL-087: de onde veio a sugestão, para a tela e a API dizerem. `produto` são os sinais da tabela
# oficial e do item (`sugerir_natureza_item`); `padrao_combustivel` é o padrão da empresa (DL-084);
# `regra` é uma regra do escritório ou da empresa (`apps.fiscal.classificacao`);
# `conflito_de_regras` é o caso em que regras de mesma precedência apontam naturezas diferentes.
ORIGEM_DA_SUGESTAO_PRODUTO = "produto"
ORIGEM_DA_SUGESTAO_PADRAO = "padrao_combustivel"
ORIGEM_DA_SUGESTAO_REGRA = "regra"
ORIGEM_DA_SUGESTAO_CONFLITO_DE_REGRAS = "conflito_de_regras"


@dataclass(frozen=True)
class Sugestao:
    natureza: str | None
    motivo: str
    origem: str = ORIGEM_DA_SUGESTAO_PRODUTO
    # Ids das regras que produziram a sugestão (uma, se venceu; várias, se houve conflito).
    regra_ids: tuple[int, ...] = ()
    # "escritorio" ou "empresa" quando a sugestão veio de uma regra.
    escopo_regra: str | None = None


# Venda de combustível pela DESCRIÇÃO oficial da tabela de `cfop.py` (PE-85.1; HI-118). Só o que a
# descrição confirma. "Consumidor final" → "para consumo" (1,6% no IRPJ): 5.656 e 6.656 (adquiridos
# de terceiros), 5.667 e 6.667 (outra UF). "Comercialização" → "para revenda" (8%): 5.655 e 6.655. A
# produção própria (5.653, 6.653 e o resto de x.651 a x.653) fica SEM sugestão: a descrição é de
# "produção do estabelecimento", e a natureza não está confirmada pelo CFOP.
_VENDA_DE_COMBUSTIVEL = (
    (
        "Venda de combustíveis ou lubrificantes adquiridos ou recebidos de terceiros destinados a "
        "consumidor ou usuário final",
        NaturezaOperacaoNFe.COMBUSTIVEL,
    ),
    (
        "Venda de combustíveis ou lubrificantes a consumidor ou usuário final",
        NaturezaOperacaoNFe.COMBUSTIVEL,
    ),
    (
        "Venda de combustíveis ou lubrificantes adquiridos ou recebidos de terceiros destinados à "
        "comercialização",
        NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA,
    ),
)


def _natureza_de_combustivel_pelo_cfop(codigo: str) -> str | None:
    """Natureza de combustível que a descrição oficial do CFOP confirma, ou `None`."""
    info = consultar_cfop(codigo)
    if info is None:
        return None
    for prefixo, natureza in _VENDA_DE_COMBUSTIVEL:
        if info.descricao.startswith(prefixo):
            return natureza
    return None


def _candidatos_do_item(documento, item) -> list[tuple[str, str]]:
    """(natureza, origem) de cada sinal que aponta uma natureza. Vazio = nenhum sinal."""
    candidatos: list[tuple[str, str]] = []
    cfop_digitos = item.cfop
    primeiro, sufixo = cfop_digitos[0], cfop_digitos[1:]

    # Exportação direta é a VENDA ao exterior (CFOP 7.1xx). Remessa (7.949) e ativo (7.551), com
    # idDest 3, não são venda: ficam sem sugestão, e o contador escolhe (correção da rodada 1, A11).
    if cfop_digitos[:2] == "71" and documento.id_dest == "3":
        candidatos.append((NaturezaOperacaoNFe.EXPORTACAO_DIRETA, ORIGEM_ID_DEST))
    if cfop_digitos == "5929":
        candidatos.append((NaturezaOperacaoNFe.CUPOM_NFCE, ORIGEM_CFOP))
    if sufixo in _CFOP_TRANSFERENCIA and documento.transferencia_entre_estabelecimentos:
        candidatos.append((NaturezaOperacaoNFe.TRANSFERENCIA, ORIGEM_CFOP))
    natureza_combustivel = None
    # CFOP de "combustíveis ou lubrificantes", com ou sem sugestão pelo NCM. Vale para o CSOSN 500 /
    # CST 60 (ICMS já recolhido), que não é sinal de substituto nessa venda (DL-083, ajuste de
    # integração).
    cfop_de_combustivel = False
    if primeiro in ("5", "6"):
        if sufixo in _CFOP_REVENDA:
            candidatos.append((NaturezaOperacaoNFe.REVENDA, ORIGEM_CFOP))
        elif sufixo in _CFOP_PRODUCAO:
            candidatos.append((NaturezaOperacaoNFe.PRODUCAO_PROPRIA, ORIGEM_CFOP))
        natureza_combustivel = _natureza_de_combustivel_pelo_cfop(cfop_digitos)
        cfop_de_combustivel = natureza_combustivel is not None
        ncm = normalizar_ncm(item.ncm)
        # HI-139: o CFOP diz "combustíveis ou lubrificantes", e só o NCM separa os dois.
        # Lubrificante
        # fica fora do 1,6% (Lei 9.249, art. 15, § 1º, I): sugere a revenda, com o aviso. NCM
        # ausente
        # ou fora das listas não tem sugestão pelo CFOP (ver `sugerir_natureza_item`).
        if natureza_combustivel is not None and ncm in NCM_LUBRIFICANTE:
            candidatos.append((NaturezaOperacaoNFe.REVENDA, ORIGEM_NCM_LUBRIFICANTE))
        elif natureza_combustivel is not None and ncm in _NCM_DE_COMBUSTIVEL_PELO_CFOP:
            candidatos.append((natureza_combustivel, ORIGEM_CFOP))

    csosn, cst = item.csosn, item.cst
    # Ajuste de integração do arquiteto (DL-083): na venda de combustível, o ICMS já recolhido
    # antes (CSOSN 500, CST 60) é o caso normal do posto, não um segundo sinal. A natureza de
    # combustível já carrega o ICMS fora do DAS (HI-132). Sem isto, toda NFC-e de posto ficaria
    # sem sugestão, e a escrituração em volume (DL-085, RC-173) não teria o que confirmar. O sinal
    # de SUBSTITUTO (ST retida na saída) continua contando e gera conflito.
    if (csosn in _CST_SUBSTITUIDO or cst in _CST_SUBSTITUIDO) and not cfop_de_combustivel:
        candidatos.append((NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO, ORIGEM_CST))
    if csosn in _CST_SUBSTITUTO or cst in _CST_SUBSTITUTO:
        candidatos.append((NaturezaOperacaoNFe.SUBSTITUTO_ST, ORIGEM_CST))
    return candidatos


def _sugestao_de_devolucao(item) -> Sugestao:
    """Natureza sugerida para a devolução (HI-140). Sugere; nunca grava.

    - devolução de combustível (CFOP da tabela oficial) com NCM de lubrificante: `devolucao_venda`,
      deduz do 8%, porque lubrificante fica fora do 1,6%;
    - x.662 (destinação a consumidor final) com NCM de combustível: `devolucao_combustivel_consumo`,
      do 1,6%. Com NCM ausente ou fora da lista: sem sugestão;
    - x.660 e x.661 (industrialização e comercialização): `devolucao_venda`, do 8%;
    - CFOP genérico de devolução com NCM de combustível: sem sugestão. Só o contador sabe se a
      venda original foi para consumo (1,6%) ou para revenda (8%);
    - sem sinal: `devolucao_venda`, como antes da DL-083.
    """
    ncm = normalizar_ncm(item.ncm)
    if not e_devolucao_de_combustivel(item.cfop):
        if ncm in NCM_COMBUSTIVEL:
            return Sugestao(
                None,
                "devolução de combustível: escolha consumo (1,6%) ou revenda (8%)",
            )
        return Sugestao(_NATUREZA_DE_DEVOLUCAO, f"{ORIGEM_FIN_NFE} 4 e CFOP com indDevol 1")
    if ncm in NCM_LUBRIFICANTE:
        return Sugestao(
            _NATUREZA_DE_DEVOLUCAO,
            "devolução de lubrificante: fora do 1,6% (Lei 9.249, art. 15, § 1º, I)",
        )
    if e_devolucao_de_combustivel_para_consumo(item.cfop):
        if ncm in _NCM_DE_COMBUSTIVEL_PELO_CFOP:
            return Sugestao(
                NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
                "devolução de combustível para consumo (CFOP x.662 e NCM de combustível)",
            )
        return Sugestao(None, _MOTIVO_SEM_NCM_DE_COMBUSTIVEL)
    return Sugestao(
        _NATUREZA_DE_DEVOLUCAO,
        "devolução de combustível para industrialização ou comercialização (CFOP x.660 ou x.661)",
    )


def sugerir_natureza_item(documento, item, tipo: str | None = None) -> Sugestao:
    """Sugestão de natureza para um item (consulta, item 2 e Hipóteses 2 e 3).

    Ordem: finalidade (`finNFe`) primeiro. Depois, na saída própria, os sinais do item. Sinais que
    apontam naturezas diferentes dão `None` com o motivo "conflito". Sem sinal, `None`.
    """
    if tipo == TipoEscrituracaoNFe.ENTRADA:
        # DL-091 (A1): a compra tem os seus próprios sinais (CFOP do emitente, CST, NCM, CRT).
        from apps.fiscal import entradas

        return entradas.sugerir_natureza_de_entrada(documento, item)
    if tipo is None:
        tipo = tipo_da_nota(documento, PapelNFe.EMITENTE) or ""
    fin = documento.fin_nfe
    if fin in ("2", "3", "5", "6"):
        return Sugestao(NaturezaOperacaoNFe.AJUSTE, f"{ORIGEM_FIN_NFE} {fin}: ajuste")

    info = consultar_cfop(item.cfop)
    if info is None:
        return Sugestao(None, "a classificar: CFOP fora da tabela oficial (Informe 2023.002 v2.10)")

    if tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA:
        # DL-091 (contrato do arquiteto, item 3): saída própria com finNFe 4. Só a devolução de
        # compra
        # oficial é sugerida. Qualquer outro CFOP de retorno (conserto, remessa, consignação) fica
        # sem
        # sugestão, com o motivo, e a nota não efetiva enquanto o item não tiver natureza.
        if info.ind_devol and info.descricao.startswith(TEXTOS_DE_DEVOLUCAO_DE_COMPRA):
            return Sugestao(
                NaturezaOperacaoNFe.DEVOLUCAO_COMPRA,
                f"devolução de compra: finNFe 4 e CFOP {item.cfop} com indDevol 1 "
                "e descrição oficial",
            )
        return Sugestao(None, "retorno em finNFe 4: fora do catálogo do corte 1")

    if fin == "4":
        # Devolução: a coluna indDevol da tabela decide. A faixa do CFOP não decide.
        if info.ind_devol:
            return _sugestao_de_devolucao(item)
        return Sugestao(None, "conflito: finNFe 4 com CFOP sem indDevol (não é devolução)")

    sufixo = item.cfop[1:]
    if sufixo in _CFOP_SEM_SUGESTAO:
        return Sugestao(
            None, f"sem sugestão: CFOP {item.cfop} (comercial exportadora, bonificação)"
        )
    if info.ind_devol:
        # Saída com indDevol 1 é devolução de COMPRA (DL-091, item 7). A natureza `devolucao_compra`
        # é sugerida só pelas descrições oficiais listadas (HI-157). Outras descrições (por exemplo
        # "Devolução de mercadoria recebida em consignação") continuam sem sugestão.
        if info.descricao.startswith(TEXTOS_DE_DEVOLUCAO_DE_COMPRA):
            return Sugestao(
                NaturezaOperacaoNFe.DEVOLUCAO_COMPRA,
                f"devolução de compra: CFOP {item.cfop} com indDevol 1 e descrição oficial de "
                f"devolução",
            )
        return Sugestao(None, "sem sugestão: devolução de compra em saída, fora do catálogo")

    candidatos = _candidatos_do_item(documento, item)
    naturezas = {natureza for natureza, _ in candidatos}
    if not candidatos:
        if _natureza_de_combustivel_pelo_cfop(item.cfop) is not None:
            return Sugestao(None, _MOTIVO_SEM_NCM_DE_COMBUSTIVEL)
        return Sugestao(None, "sem sinal suficiente: escolha a natureza")
    if len(naturezas) > 1:
        origens = ", ".join(sorted({origem for _, origem in candidatos}))
        return Sugestao(None, f"conflito entre sinais ({origens}): escolha a natureza")
    natureza, origem = candidatos[0]
    return Sugestao(natureza, f"sugerida pelo sinal de {origem}")


# DL-084, item 6 (HI-136; PE-85.1): o padrão de combustível da empresa sugere a natureza "para
# consumo" (1,6%) SÓ quando o CFOP não decide. Posto e TRR vendem a consumidor final. Distribuidora
# não tem padrão: quem decide é o item.
#
# Quando o CFOP não decide: o item NÃO tem CFOP de combustível (5949, por exemplo) e o NCM diz que é
# combustível. Aí o CFOP não separa consumo de revenda, e o padrão separa. Não entram: (a) CFOP de
# combustível, que já decide consumo (x.656) ou revenda (x.655) e só espera o NCM; (b) item comum de
# posto (loja de conveniência), cujo NCM não é de combustível.
_PADROES_QUE_SUGEREM_CONSUMO = ("posto", "trr")


def sugerir_natureza_com_padrao(
    documento, item, padrao_combustivel: str | None, tipo: str | None = None
) -> Sugestao:
    """`sugerir_natureza_item` com o padrão de combustível da empresa, como último recurso (DL-084).

    DL-087: os caminhos reais de sugestão NÃO chamam esta função diretamente. Eles chamam
    `apps.fiscal.classificacao.sugerir_natureza_com_regras`, que tenta as regras do escritório e da
    empresa e, quando nenhuma casa, cai AQUI com o padrão já carregado no contexto. Esta função
    continua sendo a sugestão embutida e o caminho sem regra: não muda de comportamento.
    """
    base = sugerir_natureza_item(documento, item, tipo)
    if base.natureza is not None or padrao_combustivel not in _PADROES_QUE_SUGEREM_CONSUMO:
        return base
    if _natureza_de_combustivel_pelo_cfop(item.cfop) is not None:
        return base
    if normalizar_ncm(item.ncm) not in NCM_COMBUSTIVEL:
        return base
    return Sugestao(
        NaturezaOperacaoNFe.COMBUSTIVEL,
        "sugerida pelo padrão de combustível da empresa (posto ou TRR): o NCM é de combustível "
        "e o CFOP não diz se é consumo ou revenda",
        origem=ORIGEM_DA_SUGESTAO_PADRAO,
    )


def segregacao_da_escrituracao(escrituracao: EscrituracaoNFe) -> dict[str, Decimal]:
    """Receita de mercadoria por segregação do Simples (consulta, item 3): memória, sem alíquota.

    Normal (revenda, produção, substituto: a operação própria), sujeita a ST (natureza 3),
    monofásico (natureza 5 ou a marca do item) e exportação (mercado externo). DL-082: ST e
    monofásico no mesmo item é a chave `st_monofasico` (união dos dois conjuntos, HI-127), e não se
    junta a `sujeita_st` (correção A8). Só naturezas de receita. A receita de cada item é
    `receita_do_item` (DL-083): item indTot 0 entra
    só pelo que foi cobrado. A natureza de serviço (14) não entra aqui: é segregada no pré-DAS de
    serviços. A receita de cada item já vem com a parcela do resíduo atribuída à nota (HI-138), e a
    leitura usa `atribuir_receita_da_nota_efetivada`: a nota efetivada antes da DL-083 que a regra
    nova recusaria é lida pelo critério anterior, sem derrubar a receita do mês (reconferência, R2).
    """
    total = {
        "normal": Decimal("0.00"),
        "sujeita_st": Decimal("0.00"),
        "monofasico": Decimal("0.00"),
        "st_monofasico": Decimal("0.00"),
        "exportacao": Decimal("0.00"),
    }
    registros = NaturezaItemNFe.objects.select_related("item").filter(escrituracao=escrituracao)
    atribuicao = atribuir_receita_da_nota_efetivada([(r.item, r.natureza) for r in registros])
    for registro in registros:
        if not registro.natureza:
            continue
        info = CATALOGO_NATUREZA_NFE[registro.natureza]
        if info.papel != "receita" or info.segregacao is None:
            continue
        # DL-082: a memória tem as cinco chaves que a tela conhece. Monofásico pela marca cai em
        # `monofasico`. ST com monofásico no mesmo item cai em `st_monofasico` (A8): a memória e a
        # tela o dizem, e o pré-DAS segrega os dois tributos certos.
        classe = classificacao_da_venda(registro.natureza, registro.monofasico, registro.item.cfop)
        segmento = info.segregacao if classe is None else classe[1]
        total[segmento] += atribuicao.valores[registro.item_id]
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
    # Cancelamento anotado em LOTE, com `Exists` (como `services.vinculos_nfe_da_empresa`): a lista
    # do mês custa o mesmo número de consultas, com 5 notas ou com 400 (DL-081, A6).
    eventos_de_cancelamento = EventoNFe.objects.filter(
        escritorio_id=OuterRef("documento__escritorio_id"),
        chave=OuterRef("documento__chave"),
        tp_evento__in=CODIGOS_CANCELAMENTO_NFE,
        c_stat__in=CODIGOS_EFETIVOS_NFE,
    )
    # `xml_original` não é carregado: a lista do mês só precisa do cabeçalho e dos itens. A leitura
    # de itens, que precisa do XML, carrega o campo na hora (DL-085, auditoria A7).
    vinculos = list(
        VinculoNFeEmpresa.objects.filter(
            empresa=empresa,
            documento__escritorio=empresa.escritorio,
            documento__dh_emissao__gte=inicio,
            documento__dh_emissao__lt=fim,
        )
        .select_related("documento")
        .defer("documento__xml_original")
        .annotate(cancelada=Exists(eventos_de_cancelamento))
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
    return [
        _nota_do_vinculo(
            vinculo,
            cancelada=vinculo.cancelada,
            ativa=ativas.get(vinculo.pk),
            leitura=leituras.get(vinculo.documento_id),
        )
        for vinculo in vinculos
    ]


def _nota_do_vinculo(vinculo, *, cancelada: bool, ativa, leitura) -> NotaDoMes:
    """A situação de UMA nota: a regra única, usada pela lista do mês e pela tela de uma nota."""
    documento = vinculo.documento
    tipo = tipo_da_nota(documento, vinculo.papel)
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
    return NotaDoMes(
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


def nota_do_vinculo(empresa, vinculo: VinculoNFeEmpresa) -> NotaDoMes:
    """A nota de UM vínculo, sem listar o mês inteiro (DL-081, A6: a tela de uma nota busca direto).

    O vínculo tem de ser desta empresa. Outro vínculo é recusado, porque a tela não confia no id.
    """
    if vinculo.empresa_id != empresa.pk:
        raise LookupError("vínculo de NF-e de outra empresa")
    documento = vinculo.documento
    cancelada = EventoNFe.objects.filter(
        escritorio_id=documento.escritorio_id,
        chave=documento.chave,
        tp_evento__in=CODIGOS_CANCELAMENTO_NFE,
        c_stat__in=CODIGOS_EFETIVOS_NFE,
    ).exists()
    ativa = EscrituracaoNFe.objects.filter(
        vinculo=vinculo,
        estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
    ).first()
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    return _nota_do_vinculo(vinculo, cancelada=cancelada, ativa=ativa, leitura=leitura)


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
        # O XML original não é usado aqui; carregá-lo a cada nota pesava no lote (DL-085, R2).
        # Quem precisa dele (a leitura dos itens) o carrega sob demanda.
        .defer("documento__xml_original")
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


def criar_rascunho(
    vinculo: VinculoNFeEmpresa, usuario, request=None, data_entrada: date | None = None
) -> EscrituracaoNFe:
    """Cria o rascunho de uma nota elegível, com uma linha de natureza por item (vazia).

    Idempotente: se já há rascunho, devolve-o com `criada_agora = False` (a data de entrada passada
    nesse caso não muda o rascunho: use `entradas.definir_data_de_entrada`). Efetivada, recusa
    (409).
    Itens ilegíveis ou nota cancelada bloqueiam, com o motivo.

    DL-091 (A1): na ENTRADA, `data_entrada` é opcional e vale a data de emissão (HI-158); data
    anterior à emissão é recusada. Nas outras, `data_entrada` é recusada.

    A LEITURA dos itens roda ANTES da transação de escrita, em transação própria. Assim, a nota
    ilegível fica gravada como tal (idempotente), mesmo com a recusa do rascunho logo depois.
    Dentro de uma transação só, a recusa desfaria a leitura e ela seria refeita a cada clique.
    """
    from apps.fiscal import entradas

    documento = vinculo.documento
    tipo = tipo_da_nota(documento, vinculo.papel)
    if tipo is None:
        raise EscrituracaoNFeErro(motivo_fora_da_escrituracao(documento, vinculo.papel))
    if tipo == TipoEscrituracaoNFe.ENTRADA:
        data_entrada = entradas.validar_data_de_entrada(
            documento, data_entrada or dia_e_competencia(documento)[0]
        )
    elif data_entrada is not None:
        raise EntradaInvalidaNFe("A data de entrada só existe na escrituração de entrada.")
    if services.situacao_da_nfe(documento) == "cancelada":
        raise EscrituracaoNFeErro("Nota cancelada não pode ser escriturada.")
    ler_itens(documento)
    return _criar_rascunho_travado(vinculo, usuario, request, data_entrada)


@transaction.atomic
def _criar_rascunho_travado(
    vinculo: VinculoNFeEmpresa, usuario, request, data_entrada: date | None = None
) -> EscrituracaoNFe:
    # Ajuste do arquiteto depois da correção da DL-085 (A5): a empresa é travada ANTES do vínculo,
    # na mesma ordem da efetivação e do lote (empresa → vínculo → escrituração). Antes, a criação
    # individual pegava o vínculo e depois precisava da linha da empresa (o INSERT da escrituração
    # pede KEY SHARE nela), e o lote, que já tinha a empresa, podia entrar em deadlock com ela.
    receita_servico.travar_empresa(vinculo.empresa)
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
        data_entrada=data_entrada,
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


def natureza_incompativel_com_marca(
    natureza: str, monofasico: bool, segmento_devolucao: str
) -> bool:
    """Uma natureza nova não aceita a marca de monofásico ou o segmento de devolução do item.

    A marca só vale para natureza de mercadoria, e o segmento só para devolução de venda. Esta é a
    ÚNICA regra disto: `definir_natureza` e `reclassificar_em_massa` a usam, para que a troca de
    natureza em lote não contorne a que vale item a item (correção da rodada 1, A12).
    """
    if monofasico and natureza not in NATUREZAS_DE_MERCADORIA:
        return True
    return bool(segmento_devolucao) and natureza != NaturezaOperacaoNFe.DEVOLUCAO_VENDA


def _gravar_origem(natureza_item_ids, origem: str, regra_id: int | None) -> None:
    """Grava a origem de um grupo de naturezas confirmadas (DL-087, item 6), uma consulta por grupo.

    Atualiza se a linha já existe (o rascunho pode trocar a natureza confirmada); cria se não
    existe.
    """
    OrigemNaturezaItemNFe.objects.bulk_create(
        [
            OrigemNaturezaItemNFe(
                natureza_item_id=pk, origem=origem, regra_classificacao_id=regra_id
            )
            for pk in natureza_item_ids
        ],
        update_conflicts=True,
        unique_fields=["natureza_item"],
        update_fields=["origem", "regra_classificacao"],
    )


@transaction.atomic
def definir_natureza(
    escrituracao: EscrituracaoNFe,
    natureza: str,
    item_ids,
    usuario,
    request=None,
    contexto=None,
) -> EscrituracaoNFe:
    """Confirma a natureza de UM ou de VÁRIOS itens da mesma nota (em bloco, HI-118).

    Só rascunho: efetivada ou estornada não muda (o banco também recusa). Itens de outra nota são
    recusados sem gravar nada.

    DL-087, item 6: grava também a ORIGEM da natureza confirmada (regra, produto, padrão ou manual),
    calculada com a mesma sugestão da tela e da prévia. `contexto` (regras e padrão, de
    `classificacao.contexto_da_empresa`) é opcional: o lote o passa, para não recarregar por nota.
    """
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        raise EntradaInvalidaNFe("Informe ao menos um item.")
    receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .defer("vinculo__documento__xml_original")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise EscrituracaoNFeErro(
            "Esta escrituração não é mais rascunho. Estornada ou efetivada, a natureza não muda."
        )
    if travada.tipo == TipoEscrituracaoNFe.ENTRADA:
        # DL-091 (A1): a natureza de entrada só entra com o CFOP de entrada, item a item.
        raise EntradaInvalidaNFe(
            "Na escrituração de entrada, a natureza e o CFOP de entrada se confirmam juntos: "
            "use a confirmação de entrada."
        )
    _validar_natureza_para_o_tipo(natureza, travada.tipo)

    alvos = list(
        NaturezaItemNFe.objects.select_for_update(of=("self",))
        .select_related("item")
        .filter(escrituracao=travada, item_id__in=ids)
    )
    if len(alvos) != len(ids):
        raise EntradaInvalidaNFe("Algum item informado não pertence a esta nota.")
    # DL-082: a marca de monofásico e o segmento da devolução só valem para a natureza certa.
    for alvo in alvos:
        if natureza_incompativel_com_marca(natureza, alvo.monofasico, alvo.segmento_devolucao):
            raise EntradaInvalidaNFe(MENSAGEM_NATUREZA_COM_MARCA)
        if natureza == NaturezaOperacaoNFe.DEVOLUCAO_COMPRA:
            # DL-091 (A1): devolução de compra exige CFOP de indDevol 1 no item.
            from apps.fiscal import entradas

            entradas.validar_devolucao_de_compra(alvo.item)
    antes = {a.item_id: a.natureza for a in alvos}
    # Origem: a sugestão de HOJE, com as regras de agora. Agrupa os itens por origem para gravar
    # com um UPDATE por grupo, e não um por item.
    from apps.fiscal import classificacao

    if contexto is None:
        contexto = classificacao.contexto_da_empresa(travada.empresa)
    documento = travada.vinculo.documento
    por_origem: dict[tuple, list[int]] = {}
    for alvo in alvos:
        sugestao = classificacao.sugerir_natureza_com_regras(
            contexto, documento, alvo.item, travada.tipo
        )
        origem = classificacao.origem_da_confirmacao(sugestao, natureza)
        por_origem.setdefault(origem, []).append(alvo.pk)
    for (origem, regra_id), pks in por_origem.items():
        NaturezaItemNFe.objects.filter(pk__in=pks).update(natureza=natureza)
        _gravar_origem(pks, origem, regra_id)

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


# ---------------------------------------------------------------------------
# DL-082: marca de monofásico (HI-128) e segmento CONFIRMADO da devolução (HI-129). Só em rascunho:
# o gatilho da DL-081 (migração 0011) recusa qualquer mudança depois da efetivação.
# ---------------------------------------------------------------------------

MENSAGEM_MARCA_SO_EM_MERCADORIA = (
    "A marca de monofásico só vale para venda de mercadoria (revenda, produção própria, ST, "
    "substituto, monofásico ou exportação). Esta natureza não é mercadoria."
)
MENSAGEM_NATUREZA_COM_MARCA = (
    "Este item tem marca de monofásico ou segmento de devolução confirmado: tire a marca ou o "
    "segmento antes de mudar a natureza para uma que não os aceita."
)
# A3: o segmento de exportação e a devolução de exportação andam juntos, nos dois sentidos. O texto
# começa por "Devolução de exportação tem CFOP 3.xxx" (as telas e os testes o citam).
MENSAGEM_SEGMENTO_DE_EXPORTACAO = (
    "Devolução de exportação tem CFOP 3.xxx, ou 1.503 a 1.506 e 2.503 a 2.506: o segmento de "
    "exportação só vale com esses CFOP, e esses CFOP só com o segmento de exportação."
)

# Par (anexo, segmento) → valor de `SegmentoDevolucao`. A tabela de `models` é a fonte; esta é a
# inversa.
_SEGMENTO_DEVOLUCAO_POR_PAR = {par: valor for valor, par in ANEXO_E_SEGMENTO_DA_DEVOLUCAO.items()}
# CFOP de devolução: x.201 (produção) e x.410 (produção com ST); x.202 (revenda) e x.411 (revenda
# com ST).
_PRODUCAO_NA_DEVOLUCAO = frozenset({"201", "410"})
_REVENDA_NA_DEVOLUCAO = frozenset({"202", "411"})


@dataclass(frozen=True)
class SugestaoSegmento:
    """Segmento sugerido para uma devolução. `segmento` None = sem sugestão (o contador escolhe)."""

    segmento: str | None
    motivo: str


def sugerir_segmento_devolucao(item, monofasico: bool) -> SugestaoSegmento:
    """Segmento sugerido para UMA devolução de venda, pelo item (HI-129). Sugere; nunca grava.

    - Anexo: CFOP x.201/x.410 é produção (Anexo II); x.202/x.411 é revenda (Anexo I). CFOP 3.xxx
      segue a mesma regra e é exportação.
    - Exportação (A3): x.503 a x.506 (1.503 a 1.506 e 2.503 a 2.506) são devolução de exportação. O
      anexo sai da descrição oficial (`ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA`). Os 3.50x não
      dizem produção ou revenda, e ficam sem sugestão.
    - ST: CFOP x.410/x.411, ou CSOSN/CST 500 (60), é ICMS-ST substituído. Na exportação o ST não
      muda o segmento: exportação tira tudo o que ST tiraria.
    - Monofásico: só a marca do item (não há tabela de NCM; HI-128).
    - Sem anexo pelo CFOP (CFOP fora das listas acima), não há sugestão.
    """
    cfop = item.cfop
    primeiro, sufixo = cfop[0], cfop[1:]
    if primeiro not in ("1", "2", "3"):
        return SugestaoSegmento(None, f"CFOP {cfop} não é de devolução de venda")
    anexo_da_exportacao = ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA.get(f"{primeiro}.{sufixo}")
    if anexo_da_exportacao is not None:
        anexo = anexo_da_exportacao
    elif sufixo in _PRODUCAO_NA_DEVOLUCAO:
        anexo = ANEXO_II
    elif sufixo in _REVENDA_NA_DEVOLUCAO:
        anexo = ANEXO_I
    else:
        return SugestaoSegmento(
            None,
            f"sem sugestão: CFOP {cfop} não diz se a venda original era de produção ou revenda",
        )
    st = sufixo in ("410", "411") or item.csosn in _CST_SUBSTITUIDO or item.cst in _CST_SUBSTITUIDO
    segmento = segmento_da_mercadoria(
        st=st, monofasico=monofasico, exportacao=e_devolucao_de_exportacao(cfop)
    )
    return SugestaoSegmento(
        _SEGMENTO_DEVOLUCAO_POR_PAR[(anexo, segmento)],
        f"sugerida pelo CFOP {cfop}, pelo CSOSN/CST e pela marca de monofásico (HI-129)",
    )


def _travar_rascunho(escrituracao: EscrituracaoNFe, ids: list[int]):
    """Trava a empresa e a escrituração e devolve os itens pedidos. Recusa se não for rascunho."""
    if not ids:
        raise EntradaInvalidaNFe("Informe ao menos um item.")
    receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .defer("vinculo__documento__xml_original")
        .get(pk=escrituracao.pk)
    )
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise EscrituracaoNFeErro(
            "Esta escrituração não é mais rascunho. Estornada ou efetivada, a marca e o segmento "
            "não mudam."
        )
    alvos = list(
        NaturezaItemNFe.objects.select_for_update(of=("self",))
        .select_related("item")
        .filter(escrituracao=travada, item_id__in=ids)
    )
    if len(alvos) != len(ids):
        raise EntradaInvalidaNFe("Algum item informado não pertence a esta nota.")
    return travada, alvos


@transaction.atomic
def definir_marca_monofasico(
    escrituracao: EscrituracaoNFe, item_ids, monofasico: bool, usuario, request=None
) -> EscrituracaoNFe:
    """Marca (ou desmarca) o monofásico de PIS e Cofins de UM ou VÁRIOS itens (DL-082, HI-128).

    A marca é do contador, na escrituração em rascunho. Só vale para natureza de mercadoria: a
    devolução marca o segmento (`definir_segmento_devolucao`), e combustível ou serviço não aceitam
    a marca. Sem marca, o item é normal (lado conservador).
    """
    if not isinstance(monofasico, bool):
        raise EntradaInvalidaNFe("A marca de monofásico é verdadeiro ou falso.")
    ids = sorted({int(i) for i in item_ids})
    travada, alvos = _travar_rascunho(escrituracao, ids)
    if monofasico:
        for alvo in alvos:
            if alvo.natureza and alvo.natureza not in NATUREZAS_DE_MERCADORIA:
                raise EntradaInvalidaNFe(MENSAGEM_MARCA_SO_EM_MERCADORIA)
            if alvo.segmento_devolucao:
                raise EntradaInvalidaNFe(
                    "Este item tem segmento de devolução confirmado: a marca de monofásico não se "
                    "aplica a devolução."
                )
    antes = {a.item_id: a.monofasico for a in alvos}
    NaturezaItemNFe.objects.filter(pk__in=[a.pk for a in alvos]).update(monofasico=monofasico)
    registrar(
        acao="escrituracao_nfe.monofasico_definido",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "monofasico": monofasico,
            "itens": {
                str(item_id): {"antes": antes[item_id], "depois": monofasico} for item_id in ids
            },
        },
    )
    return travada


@transaction.atomic
def definir_segmento_devolucao(
    escrituracao: EscrituracaoNFe, item_ids, segmento: str, usuario, request=None
) -> EscrituracaoNFe:
    """Confirma o anexo e o segmento de UMA ou VÁRIAS devoluções de venda (DL-082, HI-129).

    `segmento` vazio desfaz a confirmação. Só rascunho. A devolução de exportação tem CFOP 3.xxx ou
    1.503 a 1.506 e 2.503 a 2.506 (A3): o segmento de exportação só vale com esses CFOP, e esses
    CFOP só com o segmento de exportação. A regra é `segmentos_permitidos`, a mesma da tela (A9).
    Sem segmento confirmado, o pré-DAS do mês recusa; nunca há rateio.
    """
    segmento = (segmento or "").strip()
    if segmento and segmento not in SegmentoDevolucao.values:
        raise EntradaInvalidaNFe(
            "Segmento de devolução desconhecido: escolha uma das opções do catálogo fiscal."
        )
    ids = sorted({int(i) for i in item_ids})
    travada, alvos = _travar_rascunho(escrituracao, ids)
    for alvo in alvos:
        if alvo.natureza and alvo.natureza != NaturezaOperacaoNFe.DEVOLUCAO_VENDA:
            raise EntradaInvalidaNFe(
                "O segmento confirma devolução de venda. Este item não é devolução de venda."
            )
        # A3: o CFOP de exportação de entrada (1.503 a 1.506, 2.503 a 2.506) conta como 3.xxx. A
        # regra é `segmentos_permitidos`, a mesma que a tela usa (A9).
        if segmento and segmento not in segmentos_permitidos(alvo.item.cfop):
            raise EntradaInvalidaNFe(MENSAGEM_SEGMENTO_DE_EXPORTACAO)
    antes = {a.item_id: a.segmento_devolucao for a in alvos}
    NaturezaItemNFe.objects.filter(pk__in=[a.pk for a in alvos]).update(segmento_devolucao=segmento)
    registrar(
        acao="escrituracao_nfe.segmento_devolucao_definido",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "segmento": segmento,
            "itens": {
                str(item_id): {"antes": antes[item_id], "depois": segmento} for item_id in ids
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


# Regra de receita de 2027 (HI-133; consulta PE-84.4; DL-088 A2, HI-149): a NT 2026.008 diz que
# IBS, CBS e IS compõem o vProd a partir de 2027, e não diz como fica o vNF. Sem a regra por
# regime, a nota não tem receita efetivada. Os textos são fixos: a tela os mostra no botão, e o
# servidor, na recusa.
MENSAGEM_RECEITA_2027_PENDENTE = "regra de receita de 2027 pendente: NT 2026.008 e vNF"
# Texto da recusa de NF-e de 2027 no Presumido (A8): a nota não pode ser escriturada.
MENSAGEM_NFE_2027_PENDENTE = (
    "NF-e de 2027 sem regra de receita (NT 2026.008 e vNF): não pode ser escriturada"
)
# DL-088 A2 (HI-149): só o Simples no regime único do semestre tem receita de 2027 (o `vProd`). Os
# demais casos recusam com o motivo nomeado, cada um dizendo o que falta (o texto é o que a tela e
# a API mostram).
MENSAGEM_RECEITA_2027_REGIME_REGULAR = (
    "NF-e de 2027 não se efetiva para quem optou pelo regime regular de IBS/CBS: a receita do "
    "regime regular depende do DL 1.598, art. 12, § 4º, não lido (HI-149)"
)
MENSAGEM_RECEITA_2027_SEM_OPCAO = (
    "NF-e de 2027 não se efetiva sem a opção de regime de IBS/CBS do semestre (art. 22-A da Res. "
    "CGSN 190/2026): não se sabe se a empresa está no regime único (HI-149)"
)
MENSAGEM_RECEITA_2027_PRESUMIDO = (
    "NF-e de 2027 não se efetiva no Lucro Presumido: a receita do regime depende do DL 1.598, "
    "art. 12, § 4º, não lido (HI-149)"
)


def motivo_bloqueio_efetivacao(documento, empresa=None) -> str | None:
    """Por que a nota não pode ser efetivada por regra de DATA e de REGIME, ou `None`.

    O ano é o de São Paulo: 31/12/2026 23:59 é de 2026. Antes de 2027 nunca bloqueia. Quem chama é
    a tela (desabilita o botão com o motivo), o serviço de efetivação (recusa no POST), a API e o
    lote.

    Em 2027 em diante (DL-088 A2; HI-149), a receita de NF-e só sai para a empresa do Simples no
    REGIME ÚNICO do semestre da emissão (receita = `vProd − vDesc`; ver `receita_servico.
    receita_nfe_pelo_vprod`). Sem `empresa`, a checagem é a PURA DATA da DL-083 (A8): 2027 bloqueia
    com `MENSAGEM_RECEITA_2027_PENDENTE` — é o que a tela mostra antes de saber o regime, e o que o
    Presumido sempre verá. Com a `empresa`, cada recusa tem o motivo nomeado:

    - Simples sem a opção do semestre informada → `MENSAGEM_RECEITA_2027_SEM_OPCAO`;
    - Simples no regime regular (art. 22-A) → `MENSAGEM_RECEITA_2027_REGIME_REGULAR`;
    - Lucro Presumido → `MENSAGEM_RECEITA_2027_PRESUMIDO`;
    - demais (sem o Simples na data) → `MENSAGEM_RECEITA_2027_PENDENTE`.
    """
    dia, _competencia = dia_e_competencia(documento)
    if dia.year < 2027:
        return None
    if empresa is None:
        return MENSAGEM_RECEITA_2027_PENDENTE
    if receita_servico.receita_nfe_pelo_vprod(empresa, dia):
        return None
    regimes = receita_servico.regimes_em(empresa, dia)
    if RegimeTributario.SIMPLES_NACIONAL in regimes:
        # Empresa do Simples, mas não no regime único do semestre: ou a opção não está informada
        # (o pré-DAS do mês também recusa), ou ela é de regime regular. Cada caso, seu motivo.
        opcao = receita_servico.opcao_regime_ibs_cbs_do_semestre(
            empresa, dia.year, 1 if dia.month <= 6 else 2
        )
        if opcao is None:
            return MENSAGEM_RECEITA_2027_SEM_OPCAO
        return MENSAGEM_RECEITA_2027_REGIME_REGULAR
    if RegimeTributario.LUCRO_PRESUMIDO in regimes:
        return MENSAGEM_RECEITA_2027_PRESUMIDO
    return MENSAGEM_RECEITA_2027_PENDENTE


def memoria_v_prod_liq(itens) -> dict[str, str] | None:
    """`vProdLiq` de cada item, para a memória da efetivação de 2027 (HI-149), ou `None`.

    Guardado como memória QUANDO o leitor tiver o campo (BL-687): o leitor de hoje não o lê, e aí
    não há valor que guardar. `getattr` porque o campo entra com o BL-687, sem subir a versão do
    leitor desta etapa (a efetivação continua exigindo `VERSAO_LEITOR_ITENS`). Chave: `nItem` do
    item; valor: o número como texto, sem float.
    """
    valores = {
        str(item.n_item): str(valor)
        for item in itens
        if (valor := getattr(item, "v_prod_liq", None)) is not None
    }
    return valores or None


def avisos_do_item(item) -> tuple[str, ...]:
    """Avisos de UM item na escrituração (DL-083, itens 3 e 4). Texto para a memória e a tela.

    Só informa: quem decide a receita é `receita_do_item` com a atribuição da nota, e quem confere é
    `conferir_valores`. O aviso de atribuição (frete, desconto etc. que foi para a venda) vem de
    `avisos_da_nota`, porque depende da nota inteira.
    """
    avisos = []
    if item.ind_tot != "1" and item.v_prod is not None:
        avisos.append(
            f"item {item.n_item} fora do total: vProd R$ {valor_ptbr(item.v_prod)} "
            "não compõe a receita"
        )
    if item.ind_deduz_deson == "1" and item.v_icms_deson is not None:
        avisos.append(f"ICMS desonerado deduzido do total: R$ {valor_ptbr(item.v_icms_deson)}")
    return tuple(avisos)


def receitas_atribuidas(pares) -> dict[int, Decimal] | None:
    """Receita de cada item (`ItemNFe.pk`) depois da atribuição, ou `None` se a regra recusa.

    Para a API e a tela mostrarem o valor que a conta usa. Não grava nada.
    """
    try:
        return atribuir_receita_da_nota(pares).valores
    except ResiduoNaoAtribuivel:
        return None


def avisos_da_nota(pares) -> dict[int, tuple[str, ...]]:
    """Avisos de cada item da nota, por `ItemNFe.pk`: os do item e o da atribuição de resíduo
    (HI-138).

    Se a atribuição recusa, o aviso de atribuição não sai: a recusa já aparece na efetivação, com a
    mensagem nomeada. Não é silêncio: a nota não pode ser efetivada enquanto a regra recusar.
    """
    try:
        atribuicao = atribuir_receita_da_nota(pares)
    except ResiduoNaoAtribuivel:
        atribuicao = None
    por_numero = avisos_da_atribuicao(atribuicao) if atribuicao is not None else {}
    resultado: dict[int, tuple[str, ...]] = {}
    for item, natureza in pares:
        # DL-091 (item 7): a devolução de compra avisa o estorno do crédito (etapa do ICMS).
        aviso_de_devolucao = (
            (AVISO_DEVOLUCAO_DE_COMPRA,) if natureza == NaturezaOperacaoNFe.DEVOLUCAO_COMPRA else ()
        )
        resultado[item.pk] = (
            avisos_do_item(item) + por_numero.get(item.n_item, ()) + aviso_de_devolucao
        )
    return resultado


def conferir_valores(
    documento, leitura, itens_e_naturezas, *, receita_pelo_vprod: bool = False
) -> _ConferenciaDaNota:
    """Conferência da receita com o vNF, pela regra W16 do MOC 7.0 (HI-119; DL-083).

    Tolerância zero.

    A regra, com a receita de TODOS os itens (`receita_do_item`):

        Σ receita_do_item (todos os itens) = vNF − vST − vFCPST − vIPI − vII − vIPIDevol

    Cada item já traz o que a regra manda: `indTot` 0 sem o vProd, e `vICMSDeson` deduzido só com
    `indDeduzDeson` 1 (W04a). `vFCPST` é o total declarado em ICMSTot (`leitura.v_fcp_st_total`), e
    vale zero se ausente. É o que a nota declara, e não a soma dos itens.

    Antes, a receita de cada item passa pela atribuição por nota (HI-138,
    `atribuir_receita_da_nota`):
    o valor de item que não é receita (indTot 0 ou 1) vai para a receita da venda da mesma nota. Os
    bloqueios são os da atribuição, com mensagem fixa: nota sem item de receita com resíduo; resíduo
    negativo maior que a receita; resíduo sem base para ratear. A soma da nota não muda com a
    atribuição, então a W16 é a mesma. `itens_e_naturezas`: lista de (ItemNFe, natureza).

    `receita_pelo_vprod=True` (DL-088 A2; HI-149) é a nota de 2027 em diante do Simples no regime
    único: a receita é o `vProd − vDesc` (`itens_nfe.receita_do_item_2027`), sem atribuição de
    resíduo, e a
    W16 NÃO é aplicada — a composição do `vNF` em 2027 não está publicada (a NT 2026.008 fala do
    `vProd`, não do `vNF`; PE-84.4), e aplicar a identidade seria presumir um leiaute. `soma_itens`
    continua a soma do valor de TODOS os itens com natureza, para a conferência do contador.
    """
    pares = list(itens_e_naturezas)
    if receita_pelo_vprod:
        if documento.v_nf is None:
            raise EscrituracaoNFeErro(
                "A nota não tem o valor total (vNF): o total é obrigatório no XSD. Nota bloqueada."
            )
        soma = Decimal("0.00")
        receita = Decimal("0.00")
        devolucao = Decimal("0.00")
        valores = atribuicao_pelo_vprod(pares).valores
        for item, natureza in pares:
            if not natureza:
                continue
            soma += receita_do_item_2027(item)
            papel = papel_da_natureza_nfe(natureza)
            if papel == "receita":
                receita += valores[item.pk]
            elif papel == "deducao":
                devolucao += valores[item.pk]
        return _ConferenciaDaNota(soma, receita, devolucao, documento.v_nf)
    try:
        atribuicao = atribuir_receita_da_nota(pares)
    except ResiduoNaoAtribuivel as exc:
        raise EscrituracaoNFeErro(exc.motivo) from exc
    soma = Decimal("0.00")
    receita = Decimal("0.00")
    devolucao = Decimal("0.00")
    for item, natureza in pares:
        if not natureza:
            continue
        valor = receita_do_item(item)
        papel = papel_da_natureza_nfe(natureza)
        soma += valor
        if papel == "receita":
            receita += atribuicao.valores[item.pk]
        elif papel == "deducao":
            devolucao += valor

    if documento.v_nf is None:
        raise EscrituracaoNFeErro(
            "A nota não tem o valor total (vNF): não há como conferir a receita. Nota bloqueada."
        )
    v_st = documento.v_st or Decimal("0")
    v_fcp_st = leitura.v_fcp_st_total or Decimal("0")
    v_ipi = documento.v_ipi or Decimal("0")
    v_ii = leitura.v_ii or Decimal("0")
    v_ipi_devol = leitura.v_ipi_devol or Decimal("0")
    esperado = documento.v_nf - v_st - v_fcp_st - v_ipi - v_ii - v_ipi_devol
    if soma != esperado:
        raise DivergenciaComVnf(
            f"Receita dos itens (R$ {valor_ptbr(soma)}) diverge de vNF − vST − vFCPST − vIPI − vII "
            f"− vIPIDevol (R$ {valor_ptbr(esperado)}). "
            f"Valores da nota: vNF {valor_ptbr(documento.v_nf)}, "
            f"vST {valor_ptbr(v_st)}, vFCPST {valor_ptbr(v_fcp_st)}, vIPI {valor_ptbr(v_ipi)}, "
            f"vII {valor_ptbr(v_ii)}, vIPIDevol {valor_ptbr(v_ipi_devol)}. A nota não é efetivada."
        )
    return _ConferenciaDaNota(soma, receita, devolucao, documento.v_nf)


@transaction.atomic
def efetivar(escrituracao: EscrituracaoNFe, usuario, request=None) -> EscrituracaoNFe:
    """Efetiva a escrituração. Idempotente: efetivada de novo, devolve a mesma, sem trilha nova.

    Exige: itens lidos, natureza em TODOS os itens e conferência com vNF. Efetivar em mês já
    confirmado reabre a confirmação e marca "a retificar" (DL-074, critério 6), na mesma transação.

    DL-088 A2 (HI-149): a nota de 2027 em diante só se efetiva para o Simples no regime único do
    semestre (o portão é `motivo_bloqueio_efetivacao`, com a empresa), e sai com receita =
    `vProd − vDesc`
    (`conferir_valores(receita_pelo_vprod=True)`). A memória do `vProdLiq` vai para a trilha quando
    o leitor o trouxer (BL-687).
    """
    empresa = receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .defer("vinculo__documento__xml_original")
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
    if travada.tipo == TipoEscrituracaoNFe.ENTRADA:
        # DL-091 (A1): a entrada não tem receita, então não passa pelo portão de receita de 2027,
        # pela
        # conferência com vNF nem pelo gatilho de mês confirmado. Tem caminho próprio, na mesma
        # transação (`efetivar` é atômica).
        from apps.fiscal import entradas

        return entradas.efetivar_entrada(travada, usuario, request)
    # O ano é o de São Paulo, não o de UTC: 31/12/2026 23:59 em SP é 01/01/2027 02:59 UTC, e uma
    # comparação em UTC recusaria a nota de 2026. Em 2027 o motivo já vem do regime (HI-149).
    motivo = motivo_bloqueio_efetivacao(documento, empresa)
    if motivo is not None:
        raise EscrituracaoNFeErro(motivo)
    dia, competencia = dia_e_competencia(documento)
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    if leitura is None or leitura.estado != LeituraItensNFe.ESTADO_LIDA:
        motivo = "itens ainda não lidos" if leitura is None else leitura.motivo
        raise EscrituracaoNFeErro(f"Itens ilegíveis, nota bloqueada: {motivo}")
    # Leitura de versão anterior não tem os campos que a conferência usa (vFCPST, indDeduzDeson).
    # Gerar o rascunho de novo relê a nota (`criar_rascunho` chama `ler_itens`), antes de efetivar.
    if leitura.versao_leitor != VERSAO_LEITOR_ITENS:
        raise EscrituracaoNFeErro(
            "Itens lidos por versão anterior do leitor. Gere o rascunho de novo para reler a nota."
        )

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

    # HI-149: a receita da nota de 2027 do regime único é o vProd menos o desconto incondicional
    # (vDesc — LC 123, art. 3º, § 1º; correção do achado A2); a regra decide o caminho da
    # conferência (sem W16). O portão acima já garante que só essa nota chega aqui em 2027+.
    receita_pelo_vprod = receita_servico.receita_nfe_pelo_vprod(empresa, dia)
    conferencia = conferir_valores(documento, leitura, pares, receita_pelo_vprod=receita_pelo_vprod)
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

    detalhes = {
        "vinculo_id": travada.vinculo_id,
        "antes": antes,
        "depois": _snapshot(travada),
        "naturezas": {str(item.pk): natureza for item, natureza in pares},
    }
    if receita_pelo_vprod:
        # Memória da receita de 2027 (HI-149; LC 123, art. 3º, § 1º — correção do achado A2): o
        # que a regra usou, item a item agregado — vProd, o desconto incondicional (vDesc) e a
        # receita resultante (vProd − vDesc) — e o vProdLiq quando o leitor o trouxer (BL-687),
        # que NÃO entra na receita.
        itens_com_natureza = [item for item, natureza in pares if natureza]
        v_prod = sum(
            (item.v_prod for item in itens_com_natureza if item.ind_tot == "1"),
            Decimal("0.00"),
        )
        v_desc = sum(
            (
                item.v_desc
                for item in itens_com_natureza
                if item.ind_tot == "1" and item.v_desc is not None
            ),
            Decimal("0.00"),
        )
        detalhes["receita_2027"] = {
            "regra": "vProd − vDesc (HI-149)",
            "v_prod": str(v_prod),
            "v_desc": str(v_desc),
            "receita": str(conferencia.soma_itens),
            "v_prod_liq": memoria_v_prod_liq(item for item, _natureza in pares),
        }
    registrar(
        acao="escrituracao_nfe.efetivada",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes=detalhes,
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
    # DL-091 (A1): o estorno de entrada não mexe em receita: não há mês de receita a retificar.
    if travada.tipo != TipoEscrituracaoNFe.ENTRADA:
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


def assinatura_da_reclassificacao(pares) -> str:
    """Hash dos pares (escrituração, item) que a reclassificação altera (correção da rodada 1, A10).

    A prévia grava esta assinatura no formulário, e a confirmação a recalcula. Se o conjunto mudou,
    nem o número de notas nem o de itens bastam para dizer que é o mesmo: a assinatura muda. Os
    pares vão ordenados, e o hash é SHA-256 sobre o texto deles.
    """
    texto = json.dumps(sorted(pares), separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResultadoReclassificacao:
    natureza: str
    escrituracoes_afetadas: int
    itens_alterados: int
    # Hash dos pares (escrituração, item) alterados. Vai no formulário da prévia (A10).
    assinatura: str = ""


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

    # A12: a troca em massa não pode contornar a regra item a item de `definir_natureza`. Um item
    # casado com marca de monofásico ou segmento de devolução que a natureza nova não aceita recusa
    # a operação INTEIRA, antes de qualquer `update`. Nada muda.
    incompativeis = [
        registro
        for registro in casamentos
        if natureza_incompativel_com_marca(
            natureza, registro.monofasico, registro.segmento_devolucao
        )
    ]
    if incompativeis:
        notas = len({registro.escrituracao_id for registro in incompativeis})
        raise EntradaInvalidaNFe(
            f"A natureza {natureza} não aceita a marca de monofásico ou o segmento de devolução "
            f"de {len(incompativeis)} item(ns) em {notas} nota(s) que casam com o filtro. Tire a "
            "marca ou o segmento desses itens antes. Nada foi alterado."
        )

    afetadas = 0
    itens_alterados = 0
    pares: list[tuple[int, int]] = []
    contexto_reclass = None
    for escrituracao_id, registros in sorted(por_escrituracao.items()):
        alterar = [r for r in registros if r.natureza != natureza]
        if not alterar:
            continue
        pares.extend((escrituracao_id, r.item_id) for r in alterar)
        antes = {r.item_id: r.natureza for r in alterar}
        # DL-087, item 6: a origem de cada item, pela mesma sugestão da confirmação individual.
        from apps.fiscal import classificacao

        if contexto_reclass is None:
            contexto_reclass = classificacao.contexto_da_empresa(
                travadas_por_id[escrituracao_id].empresa
            )
        documento_reclass = travadas_por_id[escrituracao_id].vinculo.documento
        itens_reclass = ItemNFe.objects.in_bulk([r.item_id for r in alterar])
        por_origem: dict[tuple, list[int]] = {}
        for r in alterar:
            sugestao = classificacao.sugerir_natureza_com_regras(
                contexto_reclass,
                documento_reclass,
                itens_reclass[r.item_id],
                travadas_por_id[escrituracao_id].tipo,
            )
            por_origem.setdefault(
                classificacao.origem_da_confirmacao(sugestao, natureza), []
            ).append(r.pk)
        for (origem, regra_id), pks in por_origem.items():
            NaturezaItemNFe.objects.filter(pk__in=pks).update(natureza=natureza)
            _gravar_origem(pks, origem, regra_id)
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
    return ResultadoReclassificacao(
        natureza, afetadas, itens_alterados, assinatura=assinatura_da_reclassificacao(pares)
    )


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
    # Valor BRUTO por CFOP (`ItemNFe.receita_bruta_item`), dos itens indTot 1 efetivados, inclusive
    # o que não é receita (DL-083: o bruto não é a receita, e o item indTot 0 não entra aqui).
    # A soma
    # da receita não sai daqui; sai de `receita_por_natureza` (A12: o nome antigo enganava).
    valor_bruto_por_cfop: dict = field(default_factory=dict)
    nao_elegiveis: int = 0
    # As notas que a conferência já leu. A tela usa estas, e não chama `notas_do_mes` de novo (A6).
    notas: list = field(default_factory=list)


def conferencia_do_mes(empresa, ano: int, mes: int) -> ConferenciaDoMes:
    """Conferência do mês: recebidas × escrituradas × pendentes, receita por natureza e CFOP,
    canceladas, escrituradas que foram canceladas depois, e itens sem sugestão.

    Receita por natureza mostra o valor de cada natureza; a soma da receita (`receita_por_natureza`
    com papel "receita", menos a dedução) é a receita do mês. Natureza que não é receita aparece
    à parte, com soma zero (HI-124)."""
    resultado = ConferenciaDoMes(ano=ano, mes=mes)
    # `notas_do_mes` é lida UMA vez, e os itens sem sugestão saem de uma consulta só (DL-081, A6).
    notas = notas_do_mes(empresa, ano, mes)
    sem_sugestao = _itens_sem_sugestao_do_mes(notas, empresa)
    for nota in notas:
        if nota.tipo is None:
            resultado.nao_elegiveis += 1
            continue
        if nota.tipo == TipoEscrituracaoNFe.ENTRADA:
            # DL-091 (A1): a compra tem conferência própria (A2). Não entra nos números de saída.
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
        resultado.itens_sem_sugestao += sem_sugestao.get(nota.documento.pk, 0)
    resultado.notas = notas
    _preencher_receita(empresa, ano, mes, resultado)
    return resultado


def _itens_sem_sugestao_do_mes(notas: list[NotaDoMes], empresa) -> dict[int, int]:
    """Itens sem sugestão de natureza, por documento, só nas notas lidas e ainda não efetivadas.

    Uma consulta para todas as notas do mês: a conferência não repete a consulta por nota (A6). A
    sugestão lê só campos do item e do documento, já carregados, e a tabela de CFOP é em memória.

    DL-084 (RC-173, item 3): a sugestão passa pelo padrão de combustível da empresa, que decide o
    que o CFOP não decidiu. O padrão é lido UMA vez por chamada e repassado aos itens: a conferência
    percorre o mês inteiro, e consulta por item estoura o orçamento (BL-698).
    """
    candidatas = {
        nota.documento.pk: nota
        for nota in notas
        if nota.tipo is not None
        and nota.tipo != TipoEscrituracaoNFe.ENTRADA
        and nota.leitura_estado == LeituraItensNFe.ESTADO_LIDA
        and nota.situacao in (SITUACAO_A_ESCRITURAR, SITUACAO_RASCUNHO)
    }
    if not candidatas:
        return {}
    # DL-087: a sugestão passa pelas regras do escritório e da empresa antes da embutida. O contexto
    # (regras e padrão) é carregado UMA vez aqui, e não por item. `classificacao` importa o
    # Presumido,
    # que importa este módulo: o import fica dentro da função para não fechar o ciclo.
    from apps.fiscal import classificacao

    contexto = classificacao.contexto_da_empresa(empresa)
    contagem: dict[int, int] = {}
    for item in ItemNFe.objects.filter(documento_id__in=list(candidatas)):
        nota = candidatas[item.documento_id]
        sugestao = classificacao.sugerir_natureza_com_regras(
            contexto, nota.documento, item, nota.tipo
        )
        if sugestao.natureza is None:
            contagem[item.documento_id] = contagem.get(item.documento_id, 0) + 1
    return contagem


def _preencher_receita(empresa, ano: int, mes: int, resultado: ConferenciaDoMes) -> None:
    """Receita por natureza e por CFOP, das escriturações efetivadas do mês, sem canceladas.

    A receita de cada item é a ATRIBUIDA à nota (HI-138): o resíduo de frete, desconto etc. de item
    que não é receita já está nos itens de receita. Por isso a atribuição roda por escrituração, e
    não por item.
    """
    inicio = date(ano, mes, 1)
    proximo = receita_servico._proximo_mes(ano, mes)
    registros = (
        NaturezaItemNFe.objects.select_related("item")
        .filter(
            escrituracao__empresa=empresa,
            escrituracao__estado=EstadoEscrituracao.EFETIVADA,
            escrituracao__competencia__gte=inicio,
            escrituracao__competencia__lt=proximo,
        )
        .exclude(natureza="")
        # DL-091 (A1): a compra não é receita nem dedução de nenhum regime.
        .exclude(escrituracao__tipo=TipoEscrituracaoNFe.ENTRADA)
        .filter(~Exists(receita_servico._cancelada_depois_de_escriturada("escrituracao__")))
    )
    por_escrituracao: dict[int, list] = {}
    for registro in registros:
        por_escrituracao.setdefault(registro.escrituracao_id, []).append(registro)
    por_natureza: dict[str, dict] = {}
    por_cfop: dict[str, Decimal] = {}
    for registros_da_nota in por_escrituracao.values():
        atribuicao = atribuir_receita_da_nota_efetivada(
            [(r.item, r.natureza) for r in registros_da_nota]
        )
        for registro in registros_da_nota:
            natureza = registro.natureza
            papel = papel_da_natureza_nfe(natureza)
            item = registro.item
            linha = por_natureza.setdefault(
                natureza,
                {
                    "papel": papel,
                    "mercado": mercado_da_natureza_nfe(natureza),
                    "bruto": Decimal("0.00"),
                    "soma_na_receita": Decimal("0.00"),
                },
            )
            # "bruto" é o valor bruto dos itens com indTot 1 (como antes da DL-083). A receita é a
            # atribuída de cada item, e é ela que entra na soma (DL-083, HI-138).
            if item.ind_tot == "1":
                linha["bruto"] += item.receita_bruta_item
                por_cfop[item.cfop] = (
                    por_cfop.get(item.cfop, Decimal("0.00")) + item.receita_bruta_item
                )
            valor = atribuicao.valores[item.pk]
            if papel == "receita":
                linha["soma_na_receita"] += valor
            elif papel == "deducao":
                linha["soma_na_receita"] -= valor
    resultado.receita_por_natureza = por_natureza
    resultado.valor_bruto_por_cfop = por_cfop
