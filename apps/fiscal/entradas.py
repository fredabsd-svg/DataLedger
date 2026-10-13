"""Escrituração das NF-e de ENTRADA (compras) — DL-091, frente A1 (corte 1).

Plano: docs/planos/DL-091-nfe-de-entrada.md. Consulta de 13/10/2026 (docs/projeto/consultas/
2026-10-13-contador-senior-nfe-de-entrada.md), seções 2 a 6. Hipóteses HI-154 a HI-158. Decisões
que o código não explica sozinho:

- ELEGIBILIDADE: decidida em `escrituracao_nfe.tipo_da_nota` (destinatária, modelo 55, tpNF 1,
  finNFe 1). As recusas nomeadas ficam em `motivo_fora_da_escrituracao`.
- COMPETÊNCIA (HI-158): o mês da `data_entrada`, sugerida pela data de emissão. Data anterior à
  emissão é recusada. A escrituração de saída continua pelo mês de `dhEmi`.
- NATUREZA E CFOP DE ENTRADA se confirmam JUNTOS, por item. O primeiro dígito é fixo (5→1, 6→2,
  7→3); os três últimos dígitos têm de estar no grupo da natureza; CFOP fora da tabela oficial é
  recusado; 1.949 só por escolha manual (a sugestão nunca o propõe). O CFOP do emitente
  (`ItemNFe.cfop`) nunca muda.
- SUGESTÃO nunca grava. Ela usa o CFOP do emitente, o CST/CSOSN, o NCM e o CRT do emitente.
- RECEITA: nenhuma natureza de entrada compõe receita. Esta escrituração NÃO passa pela atribuição
  de receita (HI-138), nem pela conferência com o vNF (que é de receita), nem pelo gatilho
  `marcar_a_retificar`, que é do mês de receita confirmado. `receita.py` e `presumido.py` a excluem.
  A identidade do vNF não é aplicada à entrada: ela não tem receita e a composição do vNF de 2027
  não está publicada (PE-84.4). Só se soma a receita de cada item, como informação.
- MEMÓRIA POR ITEM: gravada na efetivação, imutável (gatilho da migração 0021). Repete o que a nota
  destaca. NENHUMA alíquota do Tocantins em código: não há alíquota de ICMS neste módulo.
- AVISOS nomeados, sem valor: dizem que há uma regra que o produto não calcula (DIFAL, antecipação
  do Tocantins) e não cobram nada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import RegimeTributario, TipoEstabelecimento
from apps.fiscal import receita as receita_servico
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.itens_nfe import receita_do_item
from apps.fiscal.models import (
    CATALOGO_EFEITOS_NATUREZA_NFE,
    NATUREZAS_DE_ENTRADA,
    EscrituracaoNFe,
    EstadoEscrituracao,
    LeituraItensNFe,
    MarcaCreditoEntrada,
    MemoriaEntradaItemNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.ncm_combustivel import (
    NCM_COMBUSTIVEL,
    NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL,
    NCM_LUBRIFICANTE,
    normalizar_ncm,
)

# Primeiro dígito do CFOP de entrada, em função do CFOP do emitente (consulta, seção 2). Fixo.
PRIMEIRO_DIGITO_DA_ENTRADA = {"5": "1", "6": "2", "7": "3"}

# Código IBGE da UF, o `cUF` que vem nos dois primeiros dígitos da chave de acesso. Tabela pública
# do
# IBGE. Serve só para comparar a UF do emitente com a UF da matriz da empresa (aviso de UF).
CODIGO_IBGE_DA_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip

# CSOSN/CST com ST retido pelo fornecedor (CST 60, CSOSN 500). É a memória "ST retido" (item 5).
CST_ST_RETIDO = "60"
CSOSN_ST_RETIDO = "500"
# CST que não dá crédito pleno (LC 87, art. 20, § 1º; consulta, seção 3). Aviso em natureza com
# crédito.
CST_SEM_CREDITO_PLENO = frozenset({"40", "41", "50", "51", "60", "90"})
# CST que dá crédito pleno do ICMS próprio no regime normal (consulta, seção 3).
CST_COM_CREDITO_PLENO = frozenset({"00", "10", "20", "70"})
# Só o caso do Simples depende de pCredSN: o crédito vem do vCredICMSSN (LC 123, art. 23).
CRTS_DO_SIMPLES = frozenset({"1", "2"})
CRT_REGIME_NORMAL = "3"

# Monofásico do combustível do art. 2º da LC 192 (DL-091, correção do arquiteto). A enumeração é a
# da
# consulta de 13/10/2026, seção 5 (lida no Planalto): gasolina e correntes, etanol anidro, diesel e
# correntes, biodiesel e GLP. Este filtro por NCM é só da entrada: `ncm_combustivel.py` serve à
# saída
# e NÃO é alterado. Quando a lista não separa com segurança, não se afirma monofásico.
# - Diesel (27101921, óleo diesel) e GLP (27111910): monofásico (art. 2º, diesel e correntes; GLP).
NCM_MONOFASICO_DO_ART_2_DA_LC_192 = frozenset({"27101921", "27111910"})
# - Combustível da lista que NÃO está na enumeração do art. 2º (querosene de aviação, óleos
#   combustíveis, gás natural): a regra não se afirma. Marca "a conferir" e aviso.
NCM_DE_COMBUSTIVEL_FORA_DO_ART_2 = frozenset(
    {"27101251", "27101911", "27101919", "27101922", "27101929", "27111100", "27112100"}
)
# - Demais NCM da lista, cuja descrição não separa a gasolina com segurança: "conferir NCM".

# Avisos nomeados (item 6). Texto fixo: a tela e a API mostram este texto, sem valor.
AVISO_SIMPLES_OUTRO_ESTADO = (
    "compra de outro estado por optante do Simples: possível antecipação ou DIFAL fora do DAS "
    "(LC 123, art. 13, § 1º, XIII, g e h); a regra do Tocantins não foi lida"
)
AVISO_NORMAL_OUTRO_ESTADO_USO = (
    "compra de outro estado para uso, consumo ou ativo no regime normal: possível DIFAL "
    "(CF art. 155, § 2º, VII e VIII, não conferido); a regra do Tocantins não foi lida"
)
AVISO_CST_SEM_CREDITO_PLENO = (
    "CST sem direito a crédito pleno em natureza com crédito: conferir (LC 87, art. 20, § 1º)"
)
AVISO_SIMPLES_SEM_PCREDSN = "fornecedor do Simples sem pCredSN: sem crédito (LC 123, art. 23, § 4º)"
AVISO_LUBRIFICANTE_EM_COMBUSTIVEL = (
    "lubrificante: não é monofásico da LC 192; o regime do Tocantins não foi lido (pendência P5)"
)
AVISO_ALCOOL_OU_DIESEL_B = (
    "álcool ou diesel B: anidro é monofásico (LC 192); hidratado e o regime do Tocantins não foram "
    "lidos (pendência P5)"
)
AVISO_UF_INCOERENTE = (
    "UF do emitente incoerente com o CFOP: CFOP interno (5) com emitente de outra UF, ou "
    "interestadual (6) com emitente da mesma UF da empresa"
)
AVISO_REGIME_NAO_CADASTRADO = (
    "regime da empresa na data da entrada não cadastrado: avisos de outro estado não avaliados"
)
AVISO_UF_DA_EMPRESA_NAO_CADASTRADA = (
    "UF da matriz não cadastrada: avisos de outro estado não avaliados"
)
AVISO_DEVOLUCAO_DE_COMPRA = "estorno do crédito de ICMS: etapa do ICMS (não feita no corte 1)"
AVISO_COMBUSTIVEL_FORA_DO_ART_2 = (
    "NCM de combustível fora da enumeração do art. 2º da LC 192 (consulta de 13/10/2026, seção 5): "
    "regra de monofásico não afirmada; conferir"
)

# Textos oficiais que sugerem devolução de compra (DL-091, item 7), pela descrição do CFOP.
TEXTOS_DE_DEVOLUCAO_DE_COMPRA = (
    "Devolução de compra",
    "Devolução de mercadoria recebida em transferência",
    "Devolução de bem do ativo",
    "Devolução de mercadoria destinada para uso ou consumo",
    "Devolução de embalagens",
)

MOTIVO_DATA_ANTERIOR_A_EMISSAO = (
    "data de entrada anterior à data de emissão da nota: a entrada não pode ser antes da emissão."
)
# DL-091 (rodada 1, A11): data de entrada no futuro é erro de digitação (p. ex., 2062), e a nota
# sumiria da lista do mês. O motivo é nomeado, para o contador corrigir a data.
MOTIVO_DATA_POSTERIOR_A_HOJE = (
    "data de entrada posterior a hoje: confira a data digitada. A entrada não pode ser futura."
)
MENSAGEM_CFOP_FORA_DA_TABELA = (
    "CFOP de entrada fora da tabela oficial (Informe 2023.002 v2.10): recusado."
)


@dataclass(frozen=True)
class SugestaoDeEntrada:
    """Sugestão do par (natureza, CFOP de entrada) de UM item. `None` nos dois = sem sugestão."""

    natureza: str | None
    cfop: str | None
    motivo: str


@dataclass(frozen=True)
class ContextoDaEntrada:
    """Regime e UF da empresa na data da entrada. Lido UMA vez por escrituração (BL-698)."""

    simples: bool
    normal: bool
    uf_empresa: str | None

    @property
    def regime_conhecido(self) -> bool:
        return self.simples or self.normal


# ---------------------------------------------------------------------------
# Data de entrada (HI-158)
# ---------------------------------------------------------------------------


def hoje_em_sao_paulo() -> date:
    """O dia de hoje em São Paulo. O relógio é o de `timezone.now()`, para o teste controlar."""
    from apps.fiscal.escrituracao_nfe import FUSO_SP

    return timezone.now().astimezone(FUSO_SP).date()


def validar_data_de_entrada(documento, data) -> date:
    """A data de entrada, se for uma data, não for anterior à emissão e não for posterior a hoje.

    Recusa com motivo nomeado. A emissão é o dia de `dhEmi` no fuso de São Paulo
    (`escrituracao_nfe.dia_e_competencia`).

    DL-091 (rodada 1, A11): o teto é HOJE. Se a própria emissão for posterior a hoje (relógio do
    emitente adiantado), o teto passa a ser a emissão, senão a data-padrão (= emissão) seria
    recusada e a nota não entraria em nenhum mês. Quem chama a tela, a API e o lote passa por aqui.
    """
    from apps.fiscal.escrituracao_nfe import EntradaInvalidaNFe, dia_e_competencia

    if not isinstance(data, date):
        raise EntradaInvalidaNFe("Data de entrada inválida: informe uma data.")
    emissao, _ = dia_e_competencia(documento)
    if data < emissao:
        raise EntradaInvalidaNFe(MOTIVO_DATA_ANTERIOR_A_EMISSAO)
    if data > max(hoje_em_sao_paulo(), emissao):
        raise EntradaInvalidaNFe(MOTIVO_DATA_POSTERIOR_A_HOJE)
    return data


def competencia_da_entrada(data_entrada: date) -> date:
    """Competência da entrada: o primeiro dia do mês da data de entrada (HI-158)."""
    return data_entrada.replace(day=1)


# ---------------------------------------------------------------------------
# CFOP de entrada (item 4)
# ---------------------------------------------------------------------------


def normalizar_cfop(texto: str | None) -> str:
    """CFOP só com dígitos: "1.102" e "1102" viram "1102". Vazio se não for quatro dígitos."""
    limpo = (texto or "").replace(".", "").strip()
    return limpo if re.fullmatch(r"[1-3][0-9]{3}", limpo) else ""


def validar_cfop_de_entrada(item, natureza: str, cfop_entrada: str) -> str:
    """Confere o CFOP de entrada de UM item contra a natureza e o CFOP do emitente. Devolve o CFOP.

    Recusa, com motivo nomeado: formato; fora da tabela oficial; primeiro dígito diferente do que o
    CFOP do emitente manda; grupo (três últimos dígitos) que a natureza não aceita. CFOP do emitente
    fora de 5, 6 e 7 também é recusado: não há conversão para ele.
    """
    return validar_cfop_de_entrada_para(item.cfop, natureza, cfop_entrada)


def validar_cfop_de_entrada_para(cfop_emitente: str, natureza: str, cfop_entrada: str) -> str:
    """A mesma conferência, pelo CFOP do emitente (sem item). Usada também pela regra de entrada
    (DL-091, A2), que valida o CFOP fixado contra o CFOP do próprio critério antes de gravar."""
    from apps.fiscal.escrituracao_nfe import EntradaInvalidaNFe

    if natureza not in NATUREZAS_DE_ENTRADA:
        raise EntradaInvalidaNFe("Esta natureza não é de entrada.")
    limpo = normalizar_cfop(cfop_entrada)
    if not limpo:
        raise EntradaInvalidaNFe(
            "CFOP de entrada inválido: são quatro dígitos, com 1, 2 ou 3 na frente."
        )
    if consultar_cfop(limpo) is None:
        raise EntradaInvalidaNFe(MENSAGEM_CFOP_FORA_DA_TABELA)
    primeiro_do_emitente = cfop_emitente[0] if cfop_emitente else ""
    primeiro_esperado = PRIMEIRO_DIGITO_DA_ENTRADA.get(primeiro_do_emitente)
    if primeiro_esperado is None:
        raise EntradaInvalidaNFe(
            f"CFOP {cfop_emitente} do emitente não tem conversão para entrada (só 5, 6 e 7)."
        )
    if limpo[0] != primeiro_esperado:
        raise EntradaInvalidaNFe(
            f"O primeiro dígito do CFOP de entrada é {primeiro_esperado} para o CFOP "
            f"{cfop_emitente} do emitente (5→1, 6→2, 7→3). Informado: {limpo}."
        )
    if limpo[1:] not in CATALOGO_EFEITOS_NATUREZA_NFE[natureza].sufixos:
        raise EntradaInvalidaNFe(
            f"O CFOP de entrada {limpo} não pertence ao grupo da natureza escolhida."
        )
    return limpo


def cfop_de_entrada_para(documento, item, natureza: str, sugestao=None) -> str:
    """CFOP de entrada SUGERIDO para um item, numa natureza. Vazio = não há padrão: escolha manual.

    DL-091 (A2). Ordem, a primeira que vale:
    1. o CFOP de entrada que a REGRA fixou, se a sugestão veio dela para esta mesma natureza;
    2. a conversão da A1 (`sugerir_par_de_entrada`), se ela sugere esta natureza para o item;
    3. o único sufixo do grupo da natureza, se o grupo tem um só (com o primeiro dígito da
       conversão: 5→1, 6→2, 7→3);
    4. vazio. Natureza de grupo com mais de um sufixo e sem sinal do item (p. ex., E4 sem o CFOP
       do emitente) não tem padrão: o contador escolhe. O lote não confirma esse grupo.

    Não grava nada. `sugestao` é a `Sugestao` da resolução de regras, quando já foi calculada.
    """
    if natureza not in NATUREZAS_DE_ENTRADA:
        return ""
    if sugestao is not None and sugestao.natureza == natureza and sugestao.cfop_entrada:
        return sugestao.cfop_entrada
    par = sugerir_par_de_entrada(documento, item)
    if par.natureza == natureza and par.cfop:
        return par.cfop
    primeiro = PRIMEIRO_DIGITO_DA_ENTRADA.get(item.cfop[0] if item.cfop else "")
    grupo = CATALOGO_EFEITOS_NATUREZA_NFE[natureza].sufixos
    if primeiro is None or len(grupo) != 1:
        return ""
    return f"{primeiro}{next(iter(grupo))}"


def sugerir_par_de_entrada(documento, item) -> SugestaoDeEntrada:
    """Sugestão do par (natureza, CFOP de entrada) a partir do CFOP do emitente (consulta, seção 2).

    Nunca grava. O que a sugestão não decide fica sem sugestão, e o contador escolhe. A variante ST
    (1.403, 1.401) entra com ST do emitente: CFOP 5.401 a 5.405, ou CST 10/30/60/70, ou CSOSN
    201/202/203/500. Combustível exige NCM da lista (HI-139), como na saída.
    """
    primeiro = item.cfop[0] if item.cfop else ""
    if primeiro not in PRIMEIRO_DIGITO_DA_ENTRADA:
        return SugestaoDeEntrada(None, None, "sem sugestão: CFOP do emitente fora de 5, 6 e 7")
    sufixo = item.cfop[1:]
    primeiro_entrada = PRIMEIRO_DIGITO_DA_ENTRADA[primeiro]
    st = (
        sufixo in ("401", "402", "403", "404", "405")
        or item.cst in ("10", "30", "60", "70")
        or item.csosn in ("201", "202", "203", "500")
    )
    ncm = normalizar_ncm(item.ncm)

    def par(natureza: str, sufixo_entrada: str, motivo: str) -> SugestaoDeEntrada:
        cfop_entrada = f"{primeiro_entrada}{sufixo_entrada}"
        return SugestaoDeEntrada(natureza, cfop_entrada, motivo)

    if sufixo in ("102", "104"):
        if st:
            return par(
                NaturezaOperacaoNFe.ENTRADA_ST,
                "403",
                "compra para revenda com ST (CFOP ou CST do emitente)",
            )
        return par(
            NaturezaOperacaoNFe.ENTRADA_COMERCIALIZACAO,
            "102",
            "compra para comercialização (CFOP 5.102/5.104 do emitente)",
        )
    if sufixo in ("101", "103"):
        if st:
            return par(
                NaturezaOperacaoNFe.ENTRADA_ST,
                "401",
                "compra para industrialização com ST (CFOP ou CST do emitente)",
            )
        return par(
            NaturezaOperacaoNFe.ENTRADA_INDUSTRIALIZACAO,
            "101",
            "compra para industrialização (CFOP 5.101/5.103 do emitente)",
        )
    if sufixo in ("401", "403", "405"):
        sufixo_entrada = "401" if sufixo == "401" else "403"
        return par(
            NaturezaOperacaoNFe.ENTRADA_ST,
            sufixo_entrada,
            "venda do emitente com ST: compra com ST",
        )
    if sufixo in ("151", "152"):
        return par(
            NaturezaOperacaoNFe.ENTRADA_TRANSFERENCIA,
            sufixo,
            "transferência do emitente (vínculo de entrada da filial: HI-111)",
        )
    if sufixo in ("910", "911"):
        return par(
            NaturezaOperacaoNFe.ENTRADA_BONIFICACAO, sufixo, "bonificação ou amostra do emitente"
        )
    if sufixo in ("655", "656"):
        if (
            ncm not in NCM_COMBUSTIVEL
            and ncm not in NCM_LUBRIFICANTE
            and ncm not in NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL
        ):
            return SugestaoDeEntrada(
                None,
                None,
                "sem sugestão: CFOP de combustível com NCM ausente ou fora da lista (HI-139)",
            )
        if sufixo == "655":
            return par(
                NaturezaOperacaoNFe.ENTRADA_COMBUSTIVEL_REVENDA,
                "652",
                "combustível do emitente para revenda "
                "(CFOP 5.655 e NCM de combustível ou lubrificante)",
            )
        return par(
            NaturezaOperacaoNFe.ENTRADA_COMBUSTIVEL_CONSUMO,
            "653",
            "combustível do emitente para consumidor final (CFOP 5.656): "
            "consumo próprio pelo CFOP; o contador confirma",
        )
    return SugestaoDeEntrada(
        None, None, "sem sinal suficiente: escolha a natureza e o CFOP de entrada"
    )


def sugerir_natureza_de_entrada(documento, item):
    """Sugestão de natureza para a escrituração de entrada
    (`escrituracao_nfe.sugerir_natureza_item`).

    Devolve um `escrituracao_nfe.Sugestao`. A classificação
    (`classificacao.sugerir_natureza_com_regras`)
    chama esta função para a natureza embutida, e a DL-087 pode trocá-la por regra.
    """
    from apps.fiscal.escrituracao_nfe import Sugestao

    par = sugerir_par_de_entrada(documento, item)
    return Sugestao(par.natureza, par.motivo, cfop_entrada=par.cfop or "")


def validar_devolucao_de_compra(item) -> None:
    """A natureza `devolucao_compra` só vale para item de saída com CFOP de `indDevol` 1.

    Sem essa conferência, uma venda escolhida por engano como devolução sairia da receita sem aviso.
    """
    from apps.fiscal.escrituracao_nfe import EntradaInvalidaNFe

    info = consultar_cfop(item.cfop)
    if info is None or not info.ind_devol:
        raise EntradaInvalidaNFe(
            f"Devolução de compra exige CFOP com indDevol 1; o CFOP {item.cfop} do item "
            f"{item.n_item} não tem."
        )


# ---------------------------------------------------------------------------
# Memória de crédito e avisos (itens 5 e 6)
# ---------------------------------------------------------------------------


def _destaca_icms(item) -> bool:
    return item.v_icms is not None and item.v_icms > 0


def _tem_icms_para_credito(item) -> bool:
    """A nota traz algum ICMS que um crédito poderia usar: o destacado (vICMS) ou o do Simples."""
    return _destaca_icms(item) or (item.v_cred_icms_sn is not None and item.v_cred_icms_sn > 0)


def _st_retido(item) -> bool:
    return (
        item.cst == CST_ST_RETIDO
        or item.csosn == CSOSN_ST_RETIDO
        or (item.v_icms_st_ret is not None and item.v_icms_st_ret > 0)
    )


def marca_do_credito(
    documento, item, natureza: str, contexto: ContextoDaEntrada
) -> tuple[str, Decimal | None]:
    """Marca de crédito de UM item, e o valor que a regra admite (ou `None`). Função pura.

    A ordem importa e está aqui por motivo:
    1. NCM de combustível: monofásico SÓ para o art. 2º da LC 192 (diesel e GLP); o combustível da
       lista fora do art. 2º fica "a conferir"; o demais da lista fica "monofásico: conferir NCM".
    2. REGIME DO COMPRADOR na data de entrada (DL-091, rodada 1, A1; HI-155). Regime desconhecido,
       ou ambíguo no dia (transição: Simples e normal ao mesmo tempo), é "a conferir". Comprador
       optante do Simples não se apropria de crédito (LC 123, art. 23, caput): "sem crédito,
       optante", sem valor elegível, qualquer que seja a natureza. Só o regime normal (Presumido
       ou Real) chega às regras de crédito seguintes.
    3. Natureza que veda ou restringe o crédito (E4 até 2032, E5 em 1/48, E6 e E11 a conferir):
       nunca vira "crédito destacado", mesmo com `vICMS` destacado (criterio 5, E4).
    4. ST retido (CST 60, CSOSN 500, `vICMSSTRet` > 0): sem crédito, compõe o custo.
    5. Natureza sem crédito (E7, E10, E3 sem ST retido).
    6. Fornecedor do Simples (CRT 1 ou 2): só o `vCredICMSSN`, com `pCredSN` (LC 123, art. 23, §§ 1º
       a 4º). Sem `pCredSN`, não há crédito (§ 4º, II). Nunca se presume o destacado como crédito.
       Vale para comprador do regime normal, que pode tomar esse crédito do fornecedor do Simples.
    7. Regime normal (CRT 3): o ICMS destacado, se o CST dá crédito pleno.
    CRT do fornecedor ausente ou de outro valor: "a conferir". Não se presume o regime do
    fornecedor.
    """
    efeitos = CATALOGO_EFEITOS_NATUREZA_NFE[natureza]
    ncm = normalizar_ncm(item.ncm)
    if ncm in NCM_MONOFASICO_DO_ART_2_DA_LC_192:
        return MarcaCreditoEntrada.MONOFASICO, None
    if ncm in NCM_DE_COMBUSTIVEL_FORA_DO_ART_2:
        return MarcaCreditoEntrada.A_CONFERIR, None
    if ncm in NCM_COMBUSTIVEL:
        return MarcaCreditoEntrada.MONOFASICO_CONFERIR_NCM, None
    # DL-091 (rodada 1, A1): o regime é do comprador, não do fornecedor. Ambíguo no dia também é
    # "a conferir": não há como escolher entre os dois regimes sem o dado.
    if not contexto.regime_conhecido or (contexto.simples and contexto.normal):
        return MarcaCreditoEntrada.A_CONFERIR, None
    if contexto.simples:
        return MarcaCreditoEntrada.SEM_CREDITO_OPTANTE_DO_SIMPLES, None
    credito = efeitos.credito
    if credito == "vedado_ate_2032":
        return MarcaCreditoEntrada.VEDADO_ATE_2032, None
    if credito == "um_quarenta_oitavo":
        return MarcaCreditoEntrada.UM_QUARENTA_OITAVO, None
    if credito in ("monofasico", "a_confirmar"):
        return MarcaCreditoEntrada.A_CONFERIR, None
    if _st_retido(item):
        return MarcaCreditoEntrada.ST_RETIDO, None
    if credito == "nao":
        return MarcaCreditoEntrada.NAO_SE_CREDITA, None
    crt = documento.emitente_crt
    if crt in CRTS_DO_SIMPLES:
        if item.p_cred_sn is None:
            return MarcaCreditoEntrada.SEM_CREDITO_SEM_PCREDSN, None
        if item.v_cred_icms_sn is None or item.v_cred_icms_sn <= 0:
            return MarcaCreditoEntrada.SEM_DESTAQUE, None
        return MarcaCreditoEntrada.CREDITO_LIMITADO, item.v_cred_icms_sn
    if crt == CRT_REGIME_NORMAL:
        if not _destaca_icms(item):
            return MarcaCreditoEntrada.SEM_DESTAQUE, None
        if item.cst in CST_COM_CREDITO_PLENO:
            return MarcaCreditoEntrada.CREDITO_DESTACADO, item.v_icms
        return MarcaCreditoEntrada.SEM_CREDITO_PLENO, None
    return MarcaCreditoEntrada.A_CONFERIR, None


def _fora_do_estado(documento, contexto: ContextoDaEntrada) -> bool | None:
    """True se a compra é de outro estado, False se não, None se a UF da empresa não está
    cadastrada.

    O `idDest` 2 (interestadual) decide sozinho, mesmo se o `cUF` não estiver na tabela.
    """
    if documento.id_dest == "2":
        return True
    if contexto.uf_empresa is None:
        return None
    uf_do_emitente = CODIGO_IBGE_DA_UF.get(documento.c_uf)
    if uf_do_emitente is None:
        return None
    return uf_do_emitente != contexto.uf_empresa


def avisos_da_entrada(
    documento, item, natureza: str, contexto: ContextoDaEntrada
) -> tuple[str, ...]:
    """Avisos nomeados de UM item de entrada (item 6). Função pura; não grava nada."""
    efeitos = CATALOGO_EFEITOS_NATUREZA_NFE[natureza]
    avisos: list[str] = []
    ncm = normalizar_ncm(item.ncm)
    fora = _fora_do_estado(documento, contexto)
    if not contexto.regime_conhecido:
        avisos.append(AVISO_REGIME_NAO_CADASTRADO)
    if contexto.uf_empresa is None:
        avisos.append(AVISO_UF_DA_EMPRESA_NAO_CADASTRADA)
    if fora and contexto.simples:
        avisos.append(AVISO_SIMPLES_OUTRO_ESTADO)
    if fora and contexto.normal and efeitos.difal_possivel:
        avisos.append(AVISO_NORMAL_OUTRO_ESTADO_USO)
    if efeitos.credito in ("sim", "sim_se_destacado") and item.cst in CST_SEM_CREDITO_PLENO:
        avisos.append(AVISO_CST_SEM_CREDITO_PLENO)
    if (
        documento.emitente_crt in CRTS_DO_SIMPLES
        and item.p_cred_sn is None
        and (_tem_icms_para_credito(item))
    ):
        avisos.append(AVISO_SIMPLES_SEM_PCREDSN)
    if natureza == NaturezaOperacaoNFe.ENTRADA_COMBUSTIVEL_REVENDA:
        if ncm in NCM_LUBRIFICANTE:
            avisos.append(AVISO_LUBRIFICANTE_EM_COMBUSTIVEL)
        elif ncm in NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL:
            avisos.append(AVISO_ALCOOL_OU_DIESEL_B)
    if contexto.uf_empresa is not None:
        uf_do_emitente = CODIGO_IBGE_DA_UF.get(documento.c_uf)
        if uf_do_emitente is not None:
            if item.cfop[0] == "5" and uf_do_emitente != contexto.uf_empresa:
                avisos.append(AVISO_UF_INCOERENTE)
            if item.cfop[0] == "6" and uf_do_emitente == contexto.uf_empresa:
                avisos.append(AVISO_UF_INCOERENTE)
    if ncm in NCM_DE_COMBUSTIVEL_FORA_DO_ART_2:
        avisos.append(AVISO_COMBUSTIVEL_FORA_DO_ART_2)
    if natureza == NaturezaOperacaoNFe.DEVOLUCAO_COMPRA:
        avisos.append(AVISO_DEVOLUCAO_DE_COMPRA)
    return tuple(avisos)


def memoria_do_item(
    documento, item, natureza: str, cfop_entrada: str, contexto: ContextoDaEntrada
) -> dict:
    """Valores da memória de UM item, copiados do XML lido e a marca/avisos calculados. Sem
    alíquota. `contexto` é o regime do comprador na data de entrada (DL-091, A1)."""
    marca, credito_elegivel = marca_do_credito(documento, item, natureza, contexto)
    return {
        "marca_credito": marca,
        "credito_elegivel": credito_elegivel,
        "cst": item.cst or "",
        "csosn": item.csosn or "",
        "v_bc": item.v_bc,
        "p_icms": item.p_icms,
        "v_icms": item.v_icms,
        "p_cred_sn": item.p_cred_sn,
        "v_cred_icms_sn": item.v_cred_icms_sn,
        "v_bc_st_ret": item.v_bc_st_ret,
        "v_icms_st_ret": item.v_icms_st_ret,
        "v_fcp": item.v_fcp,
        "cst_ipi": item.cst_ipi or "",
        "v_ipi": item.v_ipi,
        "cst_pis": item.cst_pis or "",
        "v_pis": item.v_pis,
        "cst_cofins": item.cst_cofins or "",
        "v_cofins": item.v_cofins,
        "avisos": list(avisos_da_entrada(documento, item, natureza, contexto)),
    }


def contexto_da_entrada(empresa, dia: date) -> ContextoDaEntrada:
    """Regime (histórico de regime, `receita.regimes_em`) e UF da matriz na data da entrada."""
    regimes = receita_servico.regimes_em(empresa, dia)
    uf = (
        empresa.estabelecimentos.filter(tipo=TipoEstabelecimento.MATRIZ)
        .values_list("uf", flat=True)
        .first()
    )
    return ContextoDaEntrada(
        simples=RegimeTributario.SIMPLES_NACIONAL in regimes,
        normal=bool(regimes & {RegimeTributario.LUCRO_PRESUMIDO, RegimeTributario.LUCRO_REAL}),
        uf_empresa=uf or None,
    )


# ---------------------------------------------------------------------------
# Escrita: natureza e CFOP de entrada, data de entrada, efetivação
# ---------------------------------------------------------------------------


@transaction.atomic
def definir_natureza_de_entrada(
    escrituracao: EscrituracaoNFe,
    natureza: str,
    cfop_entrada: str,
    item_ids,
    usuario,
    request=None,
) -> EscrituracaoNFe:
    """Confirma a natureza E1 a E11 e o CFOP de entrada de UM ou VÁRIOS itens (só rascunho).

    O CFOP é validado item a item (primeiro dígito e grupo dependem do CFOP de cada emitente): um
    CFOP que vale para um item pode não valer para outro, e a nota inteira é recusada nesse caso.
    """
    from apps.fiscal import classificacao
    from apps.fiscal import escrituracao_nfe as servico

    ids = sorted({int(i) for i in item_ids})
    if not ids:
        raise servico.EntradaInvalidaNFe("Informe ao menos um item.")
    receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .defer("vinculo__documento__xml_original")
        .get(pk=escrituracao.pk)
    )
    if travada.tipo != TipoEscrituracaoNFe.ENTRADA:
        raise servico.EntradaInvalidaNFe("Esta escrituração não é de entrada.")
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise servico.EscrituracaoNFeErro(
            "Esta escrituração não é mais rascunho. Estornada ou efetivada, a natureza não muda."
        )
    if natureza not in NATUREZAS_DE_ENTRADA:
        raise servico.EntradaInvalidaNFe(
            "Natureza de entrada desconhecida: escolha uma das naturezas E1 a E11."
        )
    alvos = list(
        NaturezaItemNFe.objects.select_for_update(of=("self",))
        .select_related("item")
        .filter(escrituracao=travada, item_id__in=ids)
    )
    if len(alvos) != len(ids):
        raise servico.EntradaInvalidaNFe("Algum item informado não pertence a esta nota.")
    antes = {a.item_id: (a.natureza, a.cfop_entrada) for a in alvos}
    cfops = {}
    for alvo in alvos:
        cfops[alvo.item_id] = validar_cfop_de_entrada(alvo.item, natureza, cfop_entrada)
    contexto = classificacao.contexto_da_empresa(travada.empresa)
    documento = travada.vinculo.documento
    por_origem: dict[tuple, list[tuple[int, str]]] = {}
    for alvo in alvos:
        sugestao = classificacao.sugerir_natureza_com_regras(
            contexto, documento, alvo.item, travada.tipo
        )
        origem = classificacao.origem_da_confirmacao(sugestao, natureza)
        por_origem.setdefault(origem, []).append((alvo.pk, cfops[alvo.item_id]))
    for (origem, regra_id), pares in por_origem.items():
        for pk, cfop in pares:
            NaturezaItemNFe.objects.filter(pk=pk).update(natureza=natureza, cfop_entrada=cfop)
        servico._gravar_origem([pk for pk, _ in pares], origem, regra_id)
    registrar(
        acao="escrituracao_nfe.entrada_natureza_definida",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "natureza": natureza,
            "itens": {
                str(item_id): {
                    "antes": {"natureza": antes[item_id][0], "cfop_entrada": antes[item_id][1]},
                    "depois": {"natureza": natureza, "cfop_entrada": cfops[item_id]},
                }
                for item_id in ids
            },
        },
    )
    return travada


@transaction.atomic
def definir_data_de_entrada(
    escrituracao: EscrituracaoNFe, data, usuario, request=None
) -> EscrituracaoNFe:
    """Troca a data de entrada de uma escrituração de entrada em rascunho (HI-158)."""
    from apps.fiscal import escrituracao_nfe as servico

    receita_servico.travar_empresa(escrituracao.empresa)
    travada = (
        EscrituracaoNFe.objects.select_for_update(of=("self",))
        .select_related("vinculo__documento", "empresa__escritorio")
        .defer("vinculo__documento__xml_original")
        .get(pk=escrituracao.pk)
    )
    if travada.tipo != TipoEscrituracaoNFe.ENTRADA:
        raise servico.EntradaInvalidaNFe("A data de entrada só existe na escrituração de entrada.")
    if travada.estado != EstadoEscrituracao.RASCUNHO:
        raise servico.EscrituracaoNFeErro(
            "Esta escrituração não é mais rascunho. Efetivada ou estornada, a data não muda."
        )
    nova = validar_data_de_entrada(travada.vinculo.documento, data)
    antes = travada.data_entrada
    EscrituracaoNFe.objects.filter(pk=travada.pk, estado=EstadoEscrituracao.RASCUNHO).update(
        data_entrada=nova
    )
    travada.refresh_from_db()
    registrar(
        acao="escrituracao_nfe.data_entrada_definida",
        usuario=usuario,
        escritorio=travada.empresa.escritorio,
        objeto=travada,
        request=request,
        detalhes={
            "vinculo_id": travada.vinculo_id,
            "antes": antes.isoformat() if antes else None,
            "depois": nova.isoformat(),
        },
    )
    return travada


def efetivar_entrada(travada: EscrituracaoNFe, usuario, request=None) -> EscrituracaoNFe:
    """Efetiva uma escrituração de ENTRADA. Chamada por `escrituracao_nfe.efetivar`, na mesma
    transação.

    Exige: itens lidos pela versão atual do leitor; natureza e CFOP de entrada em TODOS os itens;
    data de entrada não anterior à emissão; vNF presente. Grava a memória dos itens ANTES de mudar
    o estado (o gatilho só deixa gravar com rascunho). Não chama `marcar_a_retificar`: a entrada
    não muda receita do mês.
    """
    from apps.fiscal import escrituracao_nfe as servico

    documento = travada.vinculo.documento
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    if leitura is None or leitura.estado != LeituraItensNFe.ESTADO_LIDA:
        motivo = "itens ainda não lidos" if leitura is None else leitura.motivo
        raise servico.EscrituracaoNFeErro(f"Itens ilegíveis, nota bloqueada: {motivo}")
    if leitura.versao_leitor != servico.VERSAO_LEITOR_ITENS:
        raise servico.EscrituracaoNFeErro(
            "Itens lidos por versão anterior do leitor. Gere o rascunho de novo para reler a nota."
        )
    if documento.v_nf is None:
        raise servico.EscrituracaoNFeErro(
            "A nota não tem o valor total (vNF): o total é obrigatório no XSD. Nota bloqueada."
        )
    if travada.data_entrada is None:
        raise servico.EscrituracaoNFeErro("Informe a data de entrada antes de efetivar.")
    emissao, _ = servico.dia_e_competencia(documento)
    if travada.data_entrada < emissao:
        raise servico.EscrituracaoNFeErro(MOTIVO_DATA_ANTERIOR_A_EMISSAO)
    # Reconferência da DL-091, N1 (ajuste do arquiteto): o teto da data de entrada (A11) também na
    # efetivação, e não só na criação e na troca. Um rascunho gravado por outro caminho com data
    # futura não efetiva.
    if travada.data_entrada > max(hoje_em_sao_paulo(), emissao):
        raise servico.EscrituracaoNFeErro(MOTIVO_DATA_POSTERIOR_A_HOJE)

    registros = list(
        NaturezaItemNFe.objects.select_related("item")
        .filter(escrituracao=travada)
        .order_by("item__n_item")
    )
    faltam = [r for r in registros if not r.natureza]
    if not registros or faltam:
        raise servico.EscrituracaoNFeErro(
            f"Falta a natureza de {len(faltam)} item(ns). "
            "Confirme a natureza de cada item antes de efetivar."
        )
    for registro in registros:
        if not registro.cfop_entrada:
            raise servico.EscrituracaoNFeErro(
                f"Falta o CFOP de entrada do item {registro.item.n_item}. "
                "Confirme-o antes de efetivar."
            )
        validar_cfop_de_entrada(registro.item, registro.natureza, registro.cfop_entrada)

    contexto = contexto_da_entrada(travada.empresa, travada.data_entrada)
    # Memória ANTES do estado: o gatilho da 0021 só deixa gravar a memória com a escrituração em
    # rascunho. A linha de estado vem depois, na mesma transação.
    memorias = [
        MemoriaEntradaItemNFe(
            natureza_item=registro,
            **memoria_do_item(
                documento, registro.item, registro.natureza, registro.cfop_entrada, contexto
            ),
        )
        for registro in registros
    ]
    soma = sum((receita_do_item(r.item) for r in registros), Decimal("0.00"))
    antes = servico._snapshot(travada)
    MemoriaEntradaItemNFe.objects.bulk_create(memorias)
    agora = timezone.now()
    atualizadas = EscrituracaoNFe.objects.filter(
        pk=travada.pk, estado=EstadoEscrituracao.RASCUNHO
    ).update(
        estado=EstadoEscrituracao.EFETIVADA,
        efetivada_em=agora,
        efetivada_por=usuario,
        competencia=competencia_da_entrada(travada.data_entrada),
        data_emissao=emissao,
        valor_nf=documento.v_nf,
        soma_itens=soma,
        receita_bruta=Decimal("0.00"),
        devolucao=Decimal("0.00"),
    )
    if atualizadas != 1:
        raise servico.EscrituracaoNFeErro(
            "A escrituração mudou enquanto era efetivada. Atualize a lista."
        )
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
            "depois": servico._snapshot(travada),
            "naturezas": {str(r.item_id): r.natureza for r in registros},
            "cfop_entrada": {str(r.item_id): r.cfop_entrada for r in registros},
            "data_entrada": travada.data_entrada.isoformat(),
            "marcas": {str(m.natureza_item.item_id): m.marca_credito for m in memorias},
            "receita_nao_afetada": True,
        },
    )
    return travada


def previa_do_item(
    escrituracao: EscrituracaoNFe,
    item,
    natureza: str,
    cfop_entrada: str,
    contexto: ContextoDaEntrada | None = None,
) -> dict:
    """Marca e avisos de UM item ANTES da efetivação, para a tela e a API. Não grava nada.

    DL-091 (A9): quem mostra vários itens passa o `contexto` já lido (uma vez por requisição). Sem
    ele, lê o da escrituração, o que custa consultas por item.
    """
    if contexto is None:
        contexto = contexto_da_entrada(escrituracao.empresa, escrituracao.data_entrada)
    documento = escrituracao.vinculo.documento
    marca, credito = marca_do_credito(documento, item, natureza, contexto)
    return {
        "marca_credito": marca,
        "credito_elegivel": credito,
        "avisos": list(avisos_da_entrada(documento, item, natureza, contexto)),
    }
