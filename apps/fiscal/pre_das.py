"""Pré-DAS do Simples Nacional para prestador de serviço — DL-075, frente A.

NÍVEL 1 (AGENTS.md §3.1): é o valor do DAS que o contador confere contra o PGDAS-D.
PRÉ-APURAÇÃO, NUNCA TRANSMISSÃO: não gera DAS, não transmite e não substitui o
aplicativo oficial (HI-55). Contrato: docs/planos/DL-075-pre-das-do-simples.md
(itens 2, 4, 5, 6, 7 e 8; critérios 1 a 8). Tabelas: `apps.fiscal.simples_tabelas`.

Cadeia de cálculo, na ordem em que a memória de cálculo a mostra:

1. Bloqueios: competência dentro da vigência das tabelas; mês confirmado (HI-64);
   regime de caixa em 2026 (HI-66); RBT12 apurável (HI-64; HI-65); sem excesso de
   limite ou sublimite (HI-70); atividade padrão vigente no mês inteiro (HI-68).
   Todos são coletados e nomeados juntos: a recusa diz TUDO que falta.
2. Lançamentos por natureza e atividade (`receita.lancamentos_do_mes`). Cada
   natureza vira um SEGMENTO: normal, ISS retido, ISS a outro município ou
   exportação. Natureza fora do primeiro corte (HI-68) recusa com nome.
3. Anexo de cada atividade. Anexo III e IV são fixos. Anexo III ou V depende do
   fator r (≥ 0,28 → III; senão V), e aí entra a folha confirmada (HI-69).
4. Por MERCADO (HI-67): faixa pelo RBT12 do mercado, alíquota efetiva
   `(RBT12 × Aliq − PD) / RBT12` (RBT12 = 0 → 1, § 1º-A), percentuais efetivos
   por tributo (repartição × alíquota efetiva), teto de 5% do ISS (5ª faixa) com
   redistribuição aos federais, e diferença centesimal (§ 1º-B, II).
5. Valor por tributo = receita do segmento × percentual, ROUND_HALF_UP a 2 casas
   (HI-71). Total = soma dos tributos arredondados.

Precisão: toda a cadeia (RBT12, alíquota efetiva, percentuais) é `Decimal` com 60
dígitos e SEM arredondamento. Só o valor de cada tributo é arredondado. Nada aqui
usa `float`.

Segregação (HI-68, critérios 4 e 5; consulta de 08/10/2026, itens 1 a 3):
- ISS retido (`prestado_iss_retido`, ou receita informada com situação `retido`,
  HI-80): o PERCENTUAL do ISS é desconsiderado e os federais ficam como estão, sem
  redistribuição (LC 123, art. 18, § 4º-A, II; Res. CGSN 140, art. 25, § 9º, II;
  HI-78). Ver a ordem com teto, abaixo.
- Exportação (`prestado_exportacao_servico`, ou receita informada do mercado externo):
  desconsideram-se só PIS, Cofins e ISS, "tão somente" (LC 123, art. 18, § 14; Res. CGSN
  140, art. 25, § 3º; exemplo 6 do Manual do PGDAS-D, lido pelo contador-senior na
  consulta de 08/10/2026, item 2; HI-78). IRPJ, CSLL e CPP ficam com o cálculo normal, na
  alíquota efetiva do RBT12 do mercado externo, sem redistribuição (HI-78). Anexo IV
  continua sem CPP.
- Ordem com o teto de 5% do ISS (HI-79; consulta, item 3): o teto e a redistribuição
  aos federais (art. 21, por `percentuais_efetivos`) rodam PRIMEIRO; DEPOIS o ISS, que
  na 5ª faixa vale 5%, é desconsiderado (art. 25). Os federais da exportação saem
  com o excedente já incorporado. Não há exemplo oficial desta combinação: é inferência
  textual, a conferir na primeira empresa real nessa situação.
- ISS a outro município (`prestado_iss_outro_municipio`, ou receita informada com
  situação `outro_municipio`): o ISS tem o mesmo percentual do normal e fica no DAS, só
  muda o destino (LC 123, art. 18, § 4º-A, V; Res. CGSN 140, art. 25, § 9º, I; consulta,
  item 7). A alíquota de ISS da lei municipal não entra no cálculo. A divisão do ISS
  POR MUNICÍPIO não é feita: o XML do leitor atual não traz `cLocIncid` (HI-81; BL-668,
  pendente).
- Receita informada (HI-80): o mercado interno exige a situação do ISS. Sem ela, o
  pré-DAS recusa e nomeia cada receita (LC 123, art. 18, § 4º-A; Res. CGSN 140, art. 25,
  § 9º). Com ela, a situação escolhe o segmento: próprio município → normal; outro
  município → ISS a outro município; retido → ISS retido. Nunca se presume "próprio".
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa
from apps.fiscal import folha_fator_r
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as receita_servico
from apps.fiscal import simples_tabelas as tabelas
from apps.fiscal.models import (
    AtividadeEmpresa,
    ConfirmacaoReceitaMensal,
    EnquadramentoAtividade,
    EstadoConfirmacaoMes,
    MercadoReceita,
    NaturezaOperacao,
    SituacaoIssReceitaInformada,
    mercado_da_natureza,
)

# ---------------------------------------------------------------------------
# Dispositivos e constantes
# ---------------------------------------------------------------------------

DISP_TABELAS = (
    "LC 123/2006, art. 18, caput e §§ 1º-A e 1º-B; Anexos I a V na redação da LC 155/2016 "
    "(vigência 01/01/2018 a 31/12/2026; tabelas em apps/fiscal/simples_tabelas.py)"
)
DISP_ALIQUOTA_EFETIVA = (
    "LC 123/2006, art. 18, § 1º-A: (RBT12 × Aliq − PD) / RBT12; RBT12 = 0 considera-se 1 "
    "(Manual do PGDAS-D, item 8.1)"
)
DISP_REPARTICAO = (
    "LC 123/2006, art. 18, § 1º-B (percentual efetivo = alíquota efetiva × repartição)"
)
DISP_DIFERENCA = "LC 123/2006, art. 18, § 1º-B, II (diferença centesimal ao maior percentual)"
DISP_VALOR = (
    "HI-71 (hipótese, não norma): valor do tributo = receita × percentual, ROUND_HALF_UP, 2 casas"
)
DISP_FS12 = (
    "LC 123/2006, arts. 18, §§ 5º-K e 24; Res. CGSN 140/2018, art. 26, I e § 4º (janela do art. 22)"
)
DISP_RBT12_CONJUNTO = (
    "Res. CGSN 140/2018, art. 26, II e § 5º, V (RBT12 conjunto, interno + externo)"
)
DISP_FATOR_R = (
    "LC 123/2006, art. 18, §§ 5º-J e 5º-K; Manual do PGDAS-D, item 8.2.1: truncar em 2 casas"
)
DISP_REGRA_DE_ZERO = (
    "ROTINA do PGDAS-D (Manual do PGDAS-D, item 8.2.1), NÃO norma: não usar como "
    "fundamento normativo"
)
DISP_RBT12 = "Res. CGSN 140/2018, art. 22 (regra do PA); LC 123/2006, art. 18, § 2º"
DISP_CAIXA = "HI-66; Res. CGSN 140/2018, arts. 16 e 19, parágrafo único; SC Cosit 102/2026"
DISP_MES_CONFIRMADO = (
    "HI-64 (consulta contador-senior, item 1): mês só entra depois de confirmado completo"
)
DISP_PRIMEIRO_CORTE = "HI-68 (primeiro corte do pré-DAS); HI-70 (sublimite e limite como dado)"
DISP_EXPORTACAO = (
    "Res. CGSN 140/2018, art. 25, § 3º (PIS, Cofins, IPI, ICMS e ISS desconsiderados); "
    "§ 4º (conceito); HI-67 (mercado externo tem RBT12 próprio)"
)
DISP_RETIDO = (
    "Res. CGSN 140/2018, art. 25, § 9º (retenção: desconsidera o percentual do ISS); critério 4"
)
DISP_OUTRO_MUNICIPIO = (
    "Res. CGSN 140/2018, art. 25, § 9º, I (município a que o ISS é devido; ISS no DAS); "
    "HI-81; BL-668 (detalhamento por município pendente)"
)
DISP_SITUACAO_ISS = "LC 123, art. 18, § 4º-A; Res. CGSN 140, art. 25, § 9º; HI-80"
DISP_ANEXO_IV = "LC 123/2006, art. 18, § 5º-C; art. 13, VI (CPP fora do Simples, paga à parte)"

DISPOSITIVO_DO_ENQUADRAMENTO = {
    EnquadramentoAtividade.ANEXO_III: (
        "LC 123/2006, art. 18, §§ 5º-B e 5º-F (atividade do Anexo III, sem fator r)"
    ),
    EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R: (
        "LC 123/2006, art. 18, §§ 5º-D, 5º-I, 5º-J e 5º-M (Anexo III se fator r ≥ 0,28; "
        "senão Anexo V)"
    ),
    EnquadramentoAtividade.ANEXO_IV: DISP_ANEXO_IV,
}

# Rótulo do enquadramento na lista de atividades da mensagem (A5).
_ROTULO_DO_ANEXO = {
    EnquadramentoAtividade.ANEXO_III: "Anexo III",
    EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R: "Anexo III ou V, pelo fator r",
    EnquadramentoAtividade.ANEXO_IV: "Anexo IV",
}

# Segmentos da receita (HI-68). Um segmento é uma natureza, agrupada por tratamento.
SEG_NORMAL = "normal"
SEG_RETIDO = "iss_retido"
SEG_OUTRO_MUNICIPIO = "iss_outro_municipio"
SEG_EXPORTACAO = "exportacao"

SEGMENTO_DA_NATUREZA = {
    NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR: SEG_NORMAL,
    NaturezaOperacao.PRESTADO_ISS_RETIDO: SEG_RETIDO,
    NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO: SEG_OUTRO_MUNICIPIO,
    NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO: SEG_EXPORTACAO,
}

# Receita informada do mercado INTERNO (HI-80): a situação do ISS escolhe o segmento,
# do mesmo jeito que a natureza da nota escolhe no escriturado. Não há default: sem
# situação a receita não chega aqui (o pré-DAS a recusa antes). A receita informada de
# EXPORTAÇÃO não tem situação e vai ao segmento de exportação (ver `_segmento_informado`).
SEGMENTO_DA_SITUACAO_ISS = {
    SituacaoIssReceitaInformada.PROPRIO_MUNICIPIO: SEG_NORMAL,
    SituacaoIssReceitaInformada.OUTRO_MUNICIPIO: SEG_OUTRO_MUNICIPIO,
    SituacaoIssReceitaInformada.RETIDO: SEG_RETIDO,
}

# Naturezas FORA do primeiro corte: recusa nomeada, nunca cálculo silencioso.
MOTIVO_FORA_DO_CORTE = {
    NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO: (
        "ISS imune, isento ou reduzido por lei do ente (Res. CGSN 140, art. 25, § 10, e "
        "arts. 30 a 35): depende de parâmetro municipal com lei e vigência"
    ),
    NaturezaOperacao.PRESTADO_FORA_LISTA_LC116: (
        "serviço fora da lista da LC 116, sem ISS (LC 123, art. 18, § 1º-A e Res. CGSN 140, "
        "art. 25, § 1º, VI e § 5º): tratamento próprio, fora do primeiro corte"
    ),
}

_DISP_DO_SEGMENTO = {
    SEG_NORMAL: DISP_VALOR,
    SEG_RETIDO: DISP_RETIDO,
    SEG_OUTRO_MUNICIPIO: DISP_OUTRO_MUNICIPIO,
    SEG_EXPORTACAO: DISP_EXPORTACAO,
}

# Tributos desconsiderados por segmento (sem redistribuição; ver a docstring).
_DESCONSIDERADOS = {
    SEG_RETIDO: frozenset({tabelas.ISS}),
    SEG_EXPORTACAO: frozenset({tabelas.PIS, tabelas.COFINS, tabelas.ISS}),
}

# O primeiro corte vai até o último limite do Anexo III (RBT12 de R$ 3.600.000,00).
LIMITE_DO_PRIMEIRO_CORTE = tabelas.anexo("III").faixa(5).limite_superior
LIMITE_DO_FATOR_R = Decimal("0.28")
_PRECISAO = 60
_CENTAVO = Decimal("0.01")

# A10.3 (auditoria DL-075): a situação do mês aparece em texto para o contador, e não pelo código.
_SITUACAO_LEGIVEL = {
    receita_servico.SITUACAO_CONFIRMADO: "confirmado",
    receita_servico.SITUACAO_NAO_CONFIRMADO: "não confirmado",
    receita_servico.SITUACAO_A_RETIFICAR: "a retificar",
}


# ---------------------------------------------------------------------------
# Erros e resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bloqueio:
    """Motivo que impede o pré-DAS. `mensagem` nomeia o que falta."""

    codigo: str
    mensagem: str
    dispositivo: str


class PreDasRecusado(Exception):
    """Pré-DAS não calculado. `bloqueios` lista TODOS os motivos encontrados (critério 7)."""

    def __init__(self, bloqueios):
        self.bloqueios = tuple(bloqueios)
        super().__init__("; ".join(b.mensagem for b in self.bloqueios))


@dataclass(frozen=True)
class Passo:
    """Um passo da memória de cálculo. `valor` é texto para exibir; o número exato
    fica nos campos tipados do resultado."""

    ordem: int
    descricao: str
    valor: str
    dispositivo: str


@dataclass(frozen=True)
class LinhaTributo:
    tributo: str
    percentual: Decimal
    valor: Decimal
    desconsiderado: bool


@dataclass(frozen=True)
class SegmentoApurado:
    segmento: str
    receita: Decimal
    linhas: tuple[LinhaTributo, ...]
    total: Decimal


@dataclass(frozen=True)
class AnexoApurado:
    """Um anexo efetivo de um mercado: faixa, alíquotas, percentuais e segmentos."""

    mercado: str
    anexo: str
    rbt12: Decimal
    faixa: int
    limite_superior: Decimal
    aliquota_nominal: Decimal
    parcela_a_deduzir: Decimal
    aliquota_efetiva: Decimal
    teto_iss_aplicado: bool
    diferenca: Decimal
    tributo_da_diferenca: str
    segmentos: tuple[SegmentoApurado, ...]
    total: Decimal


@dataclass(frozen=True)
class FatorRApurado:
    fs12: Decimal
    rbt12_conjunto: Decimal
    valor: Decimal
    regra_zero: str | None


@dataclass(frozen=True)
class PreDas:
    empresa_id: int
    ano: int
    mes: int
    rbt12: dict = field(default_factory=dict)
    fator_r: FatorRApurado | None = None
    anexos: tuple[AnexoApurado, ...] = ()
    total: Decimal = Decimal("0.00")
    total_por_tributo: tuple[tuple[str, Decimal], ...] = ()
    memoria: tuple[Passo, ...] = ()


# ---------------------------------------------------------------------------
# Funções puras (sem banco): alíquota, fator r, percentuais, valor
# ---------------------------------------------------------------------------


def aliquota_efetiva(rbt12: Decimal, faixa: tabelas.Faixa) -> Decimal:
    """(RBT12 × Aliq − PD) / RBT12, em precisão total (LC 123, art. 18, § 1º-A).

    RBT12 = 0 usa 1 no lugar (Manual, item 8.1). Sem arredondamento: o arredondamento
    é só do valor de cada tributo (HI-71).
    """
    base = rbt12 if rbt12 > 0 else Decimal(1)
    with localcontext() as contexto:
        contexto.prec = _PRECISAO
        return (base * faixa.aliquota_nominal - faixa.parcela_a_deduzir) / base


def fator_r(fs12_valor: Decimal, rbt12_conjunto: Decimal) -> tuple[Decimal, str | None]:
    """Fator r = FS12 / RBT12 conjunto, TRUNCADO em 2 casas (Manual 8.2.1).

    Truncar, e não arredondar: 0,2799 vira 0,27 e cai no Anexo V (critério 2). As
    duas regras de zero são ROTINA do PGDAS-D (ver DISP_REGRA_DE_ZERO), e a segunda
    devolve o texto que a aplica, para a memória.
    """
    if fs12_valor == 0:
        return Decimal("0.01"), "FS12 = 0: fator r = 0,01 (rotina do PGDAS-D)"
    if rbt12_conjunto == 0:
        return Decimal("0.28"), "FS12 > 0 e RBT12 = 0: fator r = 0,28 (rotina do PGDAS-D)"
    with localcontext() as contexto:
        contexto.prec = _PRECISAO
        bruto = fs12_valor / rbt12_conjunto
    return bruto.quantize(_CENTAVO, rounding=ROUND_DOWN), None


def percentuais_efetivos(
    anexo: tabelas.Anexo, faixa: tabelas.Faixa, efetiva: Decimal
) -> tuple[tuple[tuple[str, Decimal], ...], bool, Decimal, str]:
    """Percentual efetivo de cada tributo do anexo na faixa.

    Devolve (percentuais na ordem do anexo, teto do ISS aplicado, diferença antes do
    ajuste, tributo que recebe a diferença).

    Sem teto: percentual = alíquota efetiva × repartição da faixa.
    Com teto (ISS, 5ª faixa, alíquota efetiva acima do limiar): ISS = 5% e cada
    federal = (alíquota efetiva − 5%) × redistribuição. A soma dá a alíquota efetiva.
    Diferença (§ 1º-B, II): vai ao tributo de maior percentual nominal da faixa.
    Com precisão total a diferença é da ordem de 10^-60; o passo existe para conferir.
    """
    teto = anexo.teto_iss
    aplicado = teto is not None and faixa.numero == teto.faixa and efetiva > teto.limiar_efetiva
    with localcontext() as contexto:
        contexto.prec = _PRECISAO
        if aplicado:
            mapa = {tabelas.ISS: teto.percentual_iss}
            excedente = efetiva - teto.percentual_iss
            for tributo, parcela in teto.redistribuicao:
                mapa[tributo] = excedente * parcela
        else:
            mapa = {}
            for tributo in anexo.tributos:
                nominal = faixa.percentual(tributo)
                if nominal is not None:
                    mapa[tributo] = efetiva * nominal
        soma = sum(mapa.values(), Decimal(0))
        diferenca = efetiva - soma
        # § 1º-B, II: a diferença vai ao tributo de maior percentual NOMINAL da faixa.
        # Empate: `max` devolve o primeiro na ordem de inserção (ordem do anexo).
        destino = max(mapa, key=lambda t: faixa.percentual(t) or Decimal(0))
        if diferenca != 0:
            mapa[destino] = mapa[destino] + diferenca
    itens = tuple((tributo, mapa[tributo]) for tributo in anexo.tributos if tributo in mapa)
    return itens, aplicado, diferenca, destino


def valor_do_tributo(receita: Decimal, percentual: Decimal) -> Decimal:
    """Receita × percentual, arredondado a 2 casas, ROUND_HALF_UP (HI-71)."""
    with localcontext() as contexto:
        contexto.prec = _PRECISAO
        bruto = receita * percentual
    return bruto.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def anexo_do_enquadramento(enquadramento: str, fator: Decimal | None) -> str:
    """Anexo efetivo de um enquadramento. Fator r exigido quando o catálogo pede."""
    if enquadramento == EnquadramentoAtividade.ANEXO_III:
        return "III"
    if enquadramento == EnquadramentoAtividade.ANEXO_IV:
        return "IV"
    if fator is None:
        raise ValueError("Anexo III ou V depende do fator r; ele não foi informado.")
    return "III" if fator >= LIMITE_DO_FATOR_R else "V"


def _fmt(valor: Decimal, casas: int = 12) -> str:
    """Texto para a memória. Exibição com `casas` decimais; o cálculo não usa isto."""
    return format(valor, f".{casas}f")


def _dinheiro(valor: Decimal) -> str:
    """Dinheiro na memória: 2 casas, ROUND_HALF_UP, pt-BR ('500.000,00'). Só exibição.

    A10.3 (auditoria DL-075): a memória mostrava dinheiro com 12 casas. Percentuais continuam
    com a precisão de `_fmt`, que é a que o cálculo usa para conferir.
    """
    with localcontext() as contexto:
        contexto.prec = _PRECISAO
        quantizado = Decimal(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    return f"{quantizado:,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


# ---------------------------------------------------------------------------
# Atividades: cadastro com vigência (DL-075, item 2)
# ---------------------------------------------------------------------------

_RESTRICAO_PADRAO_UNICA = "atividade_padrao_unica_em_aberto"
_RESTRICAO_FIM = "atividade_fim_depois_do_inicio"
_RESTRICAO_ENQUADRAMENTO = "atividade_enquadramento_valido"
_CAMPOS_ATIVIDADE = ("descricao", "codigo_subitem", "enquadramento", "inicio", "fim", "padrao")


class EntradaInvalidaAtividade(Exception):
    """Entrada fora da regra. API: 400."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class AtividadeConflito(Exception):
    """Conflito com o estado atual (padrão sobreposta, atividade em uso). API: 409."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _snapshot_atividade(atividade: AtividadeEmpresa) -> dict:
    return {
        "descricao": atividade.descricao,
        "codigo_subitem": atividade.codigo_subitem,
        "enquadramento": atividade.enquadramento,
        "inicio": atividade.inicio.isoformat(),
        "fim": atividade.fim.isoformat() if atividade.fim else None,
        "padrao": atividade.padrao,
    }


def _validar_atividade(dados: dict, atual: AtividadeEmpresa | None) -> dict:
    """Valores válidos de uma atividade. `atual` preenche o que não veio (PATCH)."""
    base = {
        "descricao": atual.descricao if atual else "",
        "codigo_subitem": atual.codigo_subitem if atual else "",
        "enquadramento": atual.enquadramento if atual else "",
        "inicio": atual.inicio if atual else None,
        "fim": atual.fim if atual else None,
        "padrao": atual.padrao if atual else False,
    }
    base.update({chave: valor for chave, valor in dados.items() if chave in _CAMPOS_ATIVIDADE})

    descricao = base["descricao"].strip() if isinstance(base["descricao"], str) else ""
    if not descricao:
        raise EntradaInvalidaAtividade("Informe a descrição da atividade.")
    if len(descricao) > 200:
        raise EntradaInvalidaAtividade("A descrição tem no máximo 200 caracteres.")

    codigo = (base["codigo_subitem"] or "").strip()
    if len(codigo) > 20 or any(caractere not in "0123456789." for caractere in codigo):
        raise EntradaInvalidaAtividade(
            "O código do subitem tem no máximo 20 caracteres, só dígitos e pontos."
        )

    if base["enquadramento"] not in EnquadramentoAtividade.values:
        raise EntradaInvalidaAtividade(
            f"Enquadramento fora do catálogo: {base['enquadramento']!r}."
        )
    inicio, fim = base["inicio"], base["fim"]
    if not isinstance(inicio, date):
        raise EntradaInvalidaAtividade("Informe o início da vigência (AAAA-MM-DD).")
    # A11 (auditoria DL-075): a vigência das tabelas cadastradas começa em 01/01/2018. Uma data
    # anterior (ex.: 0001-01-01, aceita pelo calendário) não tem tabela nem limite para o mês.
    if inicio < tabelas.VIGENCIA_INICIO:
        raise EntradaInvalidaAtividade(
            "O início da vigência não pode ser anterior a 01/01/2018: é o início da vigência "
            "das tabelas cadastradas (01/01/2018 a 31/12/2026)."
        )
    if fim is not None and not isinstance(fim, date):
        raise EntradaInvalidaAtividade("O fim da vigência tem de ser uma data (AAAA-MM-DD).")
    if fim is not None and fim < inicio:
        raise EntradaInvalidaAtividade("O fim da vigência é anterior ao início.")
    if not isinstance(base["padrao"], bool):
        raise EntradaInvalidaAtividade("Padrão tem de ser verdadeiro ou falso.")
    return {
        "descricao": descricao,
        "codigo_subitem": codigo,
        "enquadramento": base["enquadramento"],
        "inicio": inicio,
        "fim": fim,
        "padrao": base["padrao"],
    }


def _padroes_sobrepostos(empresa: Empresa, inicio: date, fim: date | None, excluir_pk=None):
    """Atividades padrão cuja vigência se cruza com [inicio, fim] (fim None = em aberto)."""
    consulta = AtividadeEmpresa.objects.filter(empresa=empresa, padrao=True)
    if excluir_pk is not None:
        consulta = consulta.exclude(pk=excluir_pk)
    consulta = consulta.filter(Q(fim__isnull=True) | Q(fim__gte=inicio))
    if fim is not None:
        consulta = consulta.filter(inicio__lte=fim)
    return consulta


def _inserir_atividade(objeto: AtividadeEmpresa) -> None:
    """save() com savepoint. Violação de constraint vira erro de negócio (400 ou 409)."""
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "__cause__", None), "diag", None)
        nome = getattr(diag, "constraint_name", None)
        if nome == _RESTRICAO_PADRAO_UNICA:
            raise AtividadeConflito(
                "Já há uma atividade padrão em aberto. Encerre a vigência dela antes."
            ) from exc
        if nome in (_RESTRICAO_FIM, _RESTRICAO_ENQUADRAMENTO):
            raise EntradaInvalidaAtividade("Dados da atividade fora da regra.") from exc
        raise


def _checar_padrao(empresa: Empresa, valores: dict, excluir_pk=None) -> None:
    """Padrão não pode se sobrepor a outra padrão (a constraint só cobre a em aberto)."""
    if not valores["padrao"]:
        return
    if _padroes_sobrepostos(empresa, valores["inicio"], valores["fim"], excluir_pk).exists():
        raise AtividadeConflito(
            "Já há atividade padrão com vigência sobreposta. A padrão é uma por vez."
        )


@transaction.atomic
def cadastrar_atividade(empresa: Empresa, dados: dict, usuario, request=None) -> AtividadeEmpresa:
    valores = _validar_atividade(dados, None)
    travada = receita_servico.travar_empresa(empresa)
    _checar_padrao(travada, valores)
    _recusar_cadastro_em_mes_confirmado(travada, valores)
    atividade = AtividadeEmpresa(empresa=travada, criada_por=usuario, **valores)
    _inserir_atividade(atividade)
    registrar(
        acao="atividade_fiscal.criada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atividade,
        request=request,
        detalhes={"empresa_id": travada.pk, "depois": _snapshot_atividade(atividade)},
    )
    return atividade


def _meses_confirmados(empresa: Empresa) -> list[tuple[int, int]]:
    """Meses com receita CONFIRMADA da empresa, do mais antigo ao mais recente."""
    return sorted(
        ConfirmacaoReceitaMensal.objects.filter(
            empresa=empresa, estado=EstadoConfirmacaoMes.CONFIRMADA
        ).values_list("ano", "mes")
    )


def _dias_cobertos_no_mes(ano: int, mes: int, inicio: date, fim: date | None):
    """Primeiro e último dia da vigência DENTRO do mês, ou None se ela não toca o mês.

    Comparar esses dias (e não só "toca ou não") é o que pega a troca de cobertura inteira
    para parcial (R1 da reconferência DL-075): encerrar em 15/06 deixa de cobrir 06/2026
    inteiro, e o pré-DAS desse mês muda, mesmo que a vigência ainda toque o mês.
    """
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, _ultimo_dia(ano, mes))
    de = max(inicio, primeiro)
    ate = ultimo if fim is None else min(fim, ultimo)
    return (de, ate) if de <= ate else None


def _recusar_mudanca_em_mes_confirmado(
    empresa: Empresa,
    antes: tuple[date, date | None],
    depois: tuple[date, date | None] | None,
    *,
    muda_calculo: bool,
    acao: str,
) -> None:
    """Recusa a mudança de atividade que altera o pré-DAS de mês com receita confirmada (A6).

    Mês confirmado não muda de anexo: se a atividade cobre um mês confirmado e a mudança
    altera o cálculo dele, a operação é recusada, nomeando o mês. `muda_calculo`: troca de
    enquadramento ou de padrão, que afeta todo mês que a atividade cobre (antes ou depois).
    Sem isso, conta a mudança nos dias cobertos do mês: encerrar a vigência no último dia do
    mês, ou para o futuro depois dos meses confirmados, continua permitido; encerrar no meio
    de um mês confirmado não é.
    """
    for ano, mes in _meses_confirmados(empresa):
        dias_antes = _dias_cobertos_no_mes(ano, mes, *antes)
        dias_depois = _dias_cobertos_no_mes(ano, mes, *depois) if depois is not None else None
        if muda_calculo:
            afetado = dias_antes is not None or dias_depois is not None
        else:
            afetado = dias_antes != dias_depois
        if afetado:
            raise AtividadeConflito(
                f"{acao} mudaria o pré-DAS do mês confirmado {_mes_rotulo(ano, mes)}. Mês "
                "confirmado não muda: encerre a vigência desta atividade e cadastre uma nova "
                "a partir do mês aberto."
            )


def _recusar_cadastro_em_mes_confirmado(empresa: Empresa, valores: dict) -> None:
    """Cadastro retroativo: a vigência nova não pode cobrir nenhum mês confirmado (R1, DL-075).

    Cadastrar atividade que toca mês confirmado muda o pré-DAS desse mês (anexo, ou bloqueio
    de atividade não definida com nota). Cadastrar a partir do mês aberto continua permitido.
    """
    for ano, mes in _meses_confirmados(empresa):
        if _dias_cobertos_no_mes(ano, mes, valores["inicio"], valores["fim"]) is not None:
            raise AtividadeConflito(
                f"O cadastro desta atividade mudaria o pré-DAS do mês confirmado "
                f"{_mes_rotulo(ano, mes)}. Mês confirmado não muda: cadastre a atividade a "
                "partir do mês aberto."
            )


@transaction.atomic
def alterar_atividade(
    atividade: AtividadeEmpresa, dados: dict, usuario, request=None
) -> AtividadeEmpresa:
    travada = receita_servico.travar_empresa(atividade.empresa)
    atual = AtividadeEmpresa.objects.select_for_update(of=("self",)).get(
        pk=atividade.pk, empresa=travada
    )
    antes = _snapshot_atividade(atual)
    valores = _validar_atividade(dados, atual)
    _checar_padrao(travada, valores, excluir_pk=atual.pk)
    troca_enquadramento = valores["enquadramento"] != atual.enquadramento
    troca_padrao = valores["padrao"] != atual.padrao
    if (
        troca_enquadramento
        or troca_padrao
        or (valores["inicio"], valores["fim"])
        != (
            atual.inicio,
            atual.fim,
        )
    ):
        acao = (
            "A mudança de enquadramento"
            if troca_enquadramento
            else "A troca de atividade padrão"
            if troca_padrao
            else "A mudança de vigência"
        )
        _recusar_mudanca_em_mes_confirmado(
            travada,
            (atual.inicio, atual.fim),
            (valores["inicio"], valores["fim"]),
            muda_calculo=troca_enquadramento or troca_padrao,
            acao=acao,
        )
    for nome, valor in valores.items():
        setattr(atual, nome, valor)
    _inserir_atividade(atual)
    registrar(
        acao="atividade_fiscal.alterada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={
            "empresa_id": travada.pk,
            "antes": antes,
            "depois": _snapshot_atividade(atual),
        },
    )
    return atual


@transaction.atomic
def excluir_atividade(atividade: AtividadeEmpresa, usuario, request=None) -> None:
    travada = receita_servico.travar_empresa(atividade.empresa)
    atual = AtividadeEmpresa.objects.select_for_update(of=("self",)).get(
        pk=atividade.pk, empresa=travada
    )
    antes = _snapshot_atividade(atual)
    _recusar_mudanca_em_mes_confirmado(
        travada,
        (atual.inicio, atual.fim),
        None,
        muda_calculo=True,
        acao="A exclusão",
    )
    try:
        atual.delete()
    except ProtectedError as exc:
        raise AtividadeConflito(
            "A atividade está ligada a receita informada. Encerre a vigência em vez de excluir."
        ) from exc
    registrar(
        acao="atividade_fiscal.excluida",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=None,
        request=request,
        detalhes={"empresa_id": travada.pk, "antes": antes},
    )


def _vigentes_no_mes(empresa: Empresa, ano: int, mes: int, *, so_padrao: bool):
    """Atividades cuja vigência toca o mês (qualquer dia). `so_padrao` filtra a padrão."""
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, _ultimo_dia(ano, mes))
    consulta = AtividadeEmpresa.objects.filter(empresa=empresa, inicio__lte=ultimo).filter(
        Q(fim__isnull=True) | Q(fim__gte=primeiro)
    )
    if so_padrao:
        consulta = consulta.filter(padrao=True)
    return list(consulta)


def atividades_vigentes_no_mes(empresa: Empresa, ano: int, mes: int):
    """Todas as atividades vigentes no mês, padrão ou não (A5, DL-075): ordem do cadastro."""
    return _vigentes_no_mes(empresa, ano, mes, so_padrao=False)


def atividade_padrao_do_mes(empresa: Empresa, ano: int, mes: int):
    """(atividade padrão, bloqueio). Exatamente uma, cobrindo o mês inteiro, ou bloqueio."""
    candidatas = _vigentes_no_mes(empresa, ano, mes, so_padrao=True)
    rotulo = f"{mes:02d}/{ano}"
    if not candidatas:
        return None, Bloqueio(
            "sem_atividade_padrao",
            f"Não há atividade padrão vigente em {rotulo}. Cadastre a atividade que a empresa "
            "presta, com o enquadramento (HI-68).",
            "LC 123/2006, art. 18, §§ 5º-B a 5º-M (enquadramento por atividade)",
        )
    if len(candidatas) > 1:
        # Duas padrões no mesmo mês só ocorrem na TROCA: a vigência de uma termina no meio do
        # mês e a da outra começa ali. O pré-DAS não divide o mês; a mensagem diz o que fazer.
        # "Mantenha só uma" é para o caso em que as duas cobrem o mês inteiro.
        if all(atividade.cobre_o_mes(ano, mes) for atividade in candidatas):
            return None, Bloqueio(
                "atividades_padrao_sobrepostas",
                f"Há mais de uma atividade padrão vigente em {rotulo}. Mantenha só uma.",
                "HI-68",
            )
        return None, Bloqueio(
            "atividades_padrao_sobrepostas",
            f"Mudança de atividade padrão no meio de {rotulo}: o pré-DAS não divide o mês — "
            "ajuste a vigência para o 1º dia.",
            "HI-68",
        )
    atividade = candidatas[0]
    if not atividade.cobre_o_mes(ano, mes):
        return None, Bloqueio(
            "atividade_padrao_muda_no_mes",
            f"A atividade padrão muda no meio de {rotulo}: o pré-DAS não tem anexo único "
            "para o mês.",
            "HI-68",
        )
    return atividade, None


def _ultimo_dia(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]


# ---------------------------------------------------------------------------
# Pré-DAS
# ---------------------------------------------------------------------------


def _mes_rotulo(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


def _situacao_em_texto(meses) -> str:
    return ", ".join(f"{m:02d}/{a}" for a, m, _s in meses)


def _mensagem_sem_situacao_iss(receitas) -> str:
    """Recusa nomeada: cada receita confirmada do interno sem situação, com o que a identifica.

    A receita confirmada é imutável (DL-074): a correção é estornar e relançar com a
    situação. A mensagem diz isso, em vez de sugerir uma alteração que o banco recusa.
    """
    itens = "; ".join(
        f"receita nº {r.pk}, competência {_mes_rotulo(r.ano, r.mes)}, valor {r.valor}, "
        f"documento de suporte '{r.documento_suporte}'"
        for r in receitas
    )
    return (
        "Receita informada confirmada do mercado interno sem a situação do ISS "
        f"(HI-80): {itens}. Informe a situação do ISS (estorne e relance)."
    )


def _segmento_informado(lancamento) -> str:
    """Segmento de uma soma de receita informada confirmada.

    Exportação (mercado externo) vai ao segmento de exportação, como a nota de exportação:
    desconsidera PIS, Cofins e ISS (HI-78). Interno: a situação do ISS escolhe o segmento
    (HI-80); a situação ausente já foi recusada antes de chegar aqui.
    """
    if lancamento.mercado == MercadoReceita.EXTERNO:
        return SEG_EXPORTACAO
    return SEGMENTO_DA_SITUACAO_ISS[lancamento.situacao_iss]


def pre_das(empresa: Empresa, ano: int, mes: int) -> PreDas:
    """Pré-DAS do mês, por mercado e anexo efetivo, com a memória de cálculo.

    Recusa com `PreDasRecusado` (lista todos os bloqueios). Não grava nada: é
    cálculo sob demanda, a partir dos lançamentos atuais. A entrada inválida
    (competência) sai como `EntradaInvalidaReceita`, antes de qualquer cálculo.
    """
    receita_servico.validar_competencia(ano, mes)
    bloqueios: list[Bloqueio] = []

    # 1. Tabelas: vigência cadastrada, e 2027 recusado citando a Res. CGSN 190/2026.
    if not tabelas.tabelas_vigentes_em(ano, mes):
        if ano >= 2027:
            mensagem = (
                f"O pré-DAS de {_mes_rotulo(ano, mes)} não é calculado: as tabelas a partir de "
                "01/01/2027 dependem da Res. CGSN 190/2026 e da LC 214/2025 (arts. 519 a 534), "
                "que não foram incorporadas (HI-70)."
            )
            dispositivo = "Res. CGSN 190/2026 (cópia; texto não lido); LC 214/2025, arts. 519 a 534"
        else:
            mensagem = (
                f"Não há tabela cadastrada para {_mes_rotulo(ano, mes)}: a vigência cadastrada "
                f"é 01/01/2018 a {tabelas.VIGENCIA_FIM:%d/%m/%Y}."
            )
            dispositivo = "LC 123/2006, art. 18; LC 155/2016, art. 11 (vigência dos anexos)"
        raise PreDasRecusado([Bloqueio("tabela_fora_de_vigencia", mensagem, dispositivo)])

    # 2. Mês confirmado e regime de caixa (HI-64; HI-66).
    situacao = receita_servico.situacao_do_mes(empresa, ano, mes)
    if situacao != receita_servico.SITUACAO_CONFIRMADO:
        bloqueios.append(
            Bloqueio(
                "mes_nao_confirmado",
                f"A receita de {_mes_rotulo(ano, mes)} não está confirmada completa "
                f"(situação: {_SITUACAO_LEGIVEL.get(situacao, situacao)}). "
                "Confirme o mês antes do pré-DAS.",
                DISP_MES_CONFIRMADO,
            )
        )
    if receita_servico.opcao_caixa_do_ano(empresa, ano):
        bloqueios.append(
            Bloqueio(
                "regime_de_caixa",
                f"Empresa optante pelo regime de caixa em {ano}: a base mensal é a receita "
                "recebida, e o sistema não tem contas a receber. O pré-DAS não aproxima pela "
                "emissão.",
                DISP_CAIXA,
            )
        )

    # 2b. DL-081 (HI-122): mês com NF-e de mercadoria (receita, devolução ou saldo de devolução
    # de antes). O pré-DAS de comércio e indústria ainda não existe: recusa nomeada, e nunca
    # um cálculo que ignore a receita de NF-e. Meses sem NF-e não entram aqui.
    if receita_servico.componente_nfe_no_mes(empresa, ano, mes):
        bloqueios.append(
            Bloqueio(
                "receita_de_mercadoria",
                "receita de mercadoria (NF-e) no mês — pré-DAS de comércio e indústria "
                "ainda não disponível",
                "HI-122; consulta de 09/10/2026, item 3 (segregação de ST e monofásico)",
            )
        )

    # 3. RBT12 por mercado, com recusa nomeada e excesso de limite ou sublimite.
    rbt = None
    try:
        rbt = apuracao.rbt12(empresa, ano, mes)
    except apuracao.ApuracaoRecusada as exc:
        bloqueios.append(Bloqueio("rbt12_recusado", exc.mensagem, "Res. CGSN 140/2018, art. 22"))
    if rbt is not None and not rbt.apuravel:
        bloqueios.append(
            Bloqueio(
                "rbt12_nao_apuravel",
                "RBT12 não apurável: faltam confirmar os meses "
                f"{_situacao_em_texto(rbt.pendentes_da_janela)} (HI-64).",
                "Res. CGSN 140/2018, art. 22, § 1º (janela do PA)",
            )
        )
    if rbt is not None:
        for aviso in rbt.avisos:
            # A7 (auditoria DL-075): PA anterior à vigência dos limites cadastrados. Sem o
            # sublimite, o pré-DAS não confere o excesso e não pode calcular o ISS (HI-70).
            if aviso.codigo == "limites_nao_cadastrados":
                bloqueios.append(
                    Bloqueio(
                        "limites_nao_cadastrados",
                        f"Os limites e o sublimite de {ano} não estão cadastrados: o pré-DAS "
                        "não confere o sublimite e não calcula (HI-70).",
                        aviso.dispositivo,
                    )
                )
            elif aviso.codigo.startswith(
                ("limite_excedido", "sublimite_excedido", "limites_nao_apurados")
            ):
                # A10.1: o sufixo do primeiro corte só vale para o excesso. O aviso de limite
                # não apurado já diz o motivo (mês não confirmado) e não é corte.
                texto = aviso.mensagem
                if not aviso.codigo.startswith("limites_nao_apurados"):
                    texto += " Fora do primeiro corte do pré-DAS (HI-68; HI-70)."
                bloqueios.append(
                    Bloqueio(
                        "excesso_de_limite_ou_sublimite",
                        texto,
                        aviso.dispositivo,
                    )
                )

    # 4. Atividade padrão e lançamentos por natureza e atividade.
    padrao, bloqueio_padrao = atividade_padrao_do_mes(empresa, ano, mes)
    if bloqueio_padrao is not None:
        bloqueios.append(bloqueio_padrao)
    lancamentos = receita_servico.lancamentos_do_mes(empresa, ano, mes)
    # A5 (auditoria DL-075, decisão do arquiteto): a escrituração não diz a qual atividade cada
    # nota pertence. Com mais de uma atividade vigente e nota efetivada no mês, o pré-DAS
    # recusa, em vez de mandar todas as notas para a padrão sem aviso. A receita informada com
    # atividade explícita não entra aqui: ela já traz a atividade.
    vigentes = atividades_vigentes_no_mes(empresa, ano, mes)
    if len(vigentes) > 1 and lancamentos.documento_por_natureza:
        lista = ", ".join(
            f"{atividade.descricao} ({_ROTULO_DO_ANEXO[atividade.enquadramento]})"
            for atividade in vigentes
        )
        bloqueios.append(
            Bloqueio(
                "notas_sem_atividade_definida",
                f"A empresa tem mais de uma atividade vigente em {_mes_rotulo(ano, mes)} ({lista}) "
                "e as notas do mês não dizem a qual pertencem: o pré-DAS não escolhe o anexo por "
                "você. Atividade por nota ainda não existe (BL-670).",
                "HI-68; LC 123/2006, art. 18, §§ 5º-B a 5º-M",
            )
        )

    ids = {linha.atividade_id for linha in lancamentos.informados if linha.atividade_id}
    atividades = {a.pk: a for a in AtividadeEmpresa.objects.filter(empresa=empresa, pk__in=ids)}
    linhas: list[
        tuple[str, str, str | None, Decimal]
    ] = []  # (mercado, segmento, enquadramento, valor)
    for natureza, valor in sorted(lancamentos.documento_por_natureza.items()):
        if natureza in MOTIVO_FORA_DO_CORTE:
            bloqueios.append(
                Bloqueio(
                    "natureza_fora_do_corte",
                    f"Há receita de natureza fora do primeiro corte do pré-DAS: "
                    f"{MOTIVO_FORA_DO_CORTE[natureza]} (HI-68).",
                    "HI-68; Res. CGSN 140/2018, art. 25",
                )
            )
            continue
        if valor == 0:
            continue
        enquadramento = padrao.enquadramento if padrao is not None else None
        linhas.append(
            (mercado_da_natureza(natureza), SEGMENTO_DA_NATUREZA[natureza], enquadramento, valor)
        )
    # HI-80: receita informada CONFIRMADA do mercado interno sem situação do ISS (receita de
    # antes da regra). Recusa nomeando cada uma; nunca se presume "próprio município", que
    # duplicaria o ISS retido ou o destinaria ao ente errado.
    sem_situacao = receita_servico.receitas_informadas_sem_situacao_iss(empresa, ano, mes)
    if sem_situacao:
        bloqueios.append(
            Bloqueio(
                "receita_informada_sem_situacao_iss",
                _mensagem_sem_situacao_iss(sem_situacao),
                DISP_SITUACAO_ISS,
            )
        )
    for lancamento in lancamentos.informados:
        if lancamento.valor == 0:
            continue
        if lancamento.mercado == MercadoReceita.INTERNO and lancamento.situacao_iss is None:
            # Recusada acima, com a lista de cada receita. Não entra em segmento nenhum.
            continue
        if lancamento.atividade_id is None:
            enquadramento = padrao.enquadramento if padrao is not None else None
        else:
            atividade = atividades.get(lancamento.atividade_id)
            if atividade is None or not atividade.cobre_o_mes(ano, mes):
                bloqueios.append(
                    Bloqueio(
                        "atividade_informada_fora_da_vigencia",
                        f"Uma receita informada de {_mes_rotulo(ano, mes)} aponta atividade "
                        "que não está vigente no mês inteiro.",
                        "HI-68",
                    )
                )
                continue
            enquadramento = atividade.enquadramento
        linhas.append(
            (lancamento.mercado, _segmento_informado(lancamento), enquadramento, lancamento.valor)
        )

    # 5. Fator r, só se alguma linha o exige, com folha confirmada nos meses da janela.
    precisa_fator_r = any(
        enquadramento == EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R
        for _m, _s, enquadramento, _v in linhas
    )
    fator = None
    if precisa_fator_r and rbt is not None and rbt.apuravel:
        fs = folha_fator_r.fs12(empresa, ano, mes)
        if fs.valor is None:
            bloqueios.append(
                Bloqueio(
                    "folha_nao_confirmada",
                    "Fator r exigido sem folha confirmada: faltam confirmar os meses "
                    f"{_situacao_em_texto(fs.pendentes)} (HI-69).",
                    DISP_FS12,
                )
            )
        else:
            conjunto = (
                rbt.de(MercadoReceita.INTERNO).apurado + rbt.de(MercadoReceita.EXTERNO).apurado
            )
            valor_r, regra_zero = fator_r(fs.valor, conjunto)
            fator = FatorRApurado(
                fs12=fs.valor, rbt12_conjunto=conjunto, valor=valor_r, regra_zero=regra_zero
            )

    if bloqueios:
        raise PreDasRecusado(bloqueios)

    # 6. Anexo efetivo por linha, e teto de RBT12 do primeiro corte (HI-68).
    grupos: dict[tuple[str, str, str], Decimal] = {}
    enquadramentos_do_anexo: dict[tuple[str, str], set[str]] = {}
    for mercado, segmento, enquadramento, valor in linhas:
        anexo_numero = anexo_do_enquadramento(
            enquadramento, fator.valor if fator is not None else None
        )
        chave = (mercado, anexo_numero, segmento)
        grupos[chave] = grupos.get(chave, Decimal("0.00")) + valor
        enquadramentos_do_anexo.setdefault((mercado, anexo_numero), set()).add(enquadramento)

    rbt_por_mercado: dict[str, Decimal] = {}
    for mercado in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO):
        if any(chave[0] == mercado for chave in grupos):
            rbt_por_mercado[mercado] = rbt.de(mercado).apurado
            if rbt_por_mercado[mercado] > LIMITE_DO_PRIMEIRO_CORTE:
                bloqueios.append(
                    Bloqueio(
                        "rbt12_acima_do_primeiro_corte",
                        f"RBT12 do mercado {mercado} ({rbt_por_mercado[mercado]}) acima de "
                        f"{LIMITE_DO_PRIMEIRO_CORTE}: a 6ª faixa e o excesso ficam fora do "
                        "primeiro corte (HI-68). O exemplo 8 do Manual é caso de "
                        "referência futuro.",
                        "Manual do PGDAS-D, itens 8.4 e exemplo 8; HI-68",
                    )
                )
    if bloqueios:
        raise PreDasRecusado(bloqueios)

    # 7. Cálculo por mercado e anexo, com a memória de cálculo.
    memoria: list[Passo] = []
    passo = _Memoria(memoria)
    passo.add("Competência e tabelas", _mes_rotulo(ano, mes), DISP_TABELAS)
    passo.add("Mês confirmado completo", "confirmado", DISP_MES_CONFIRMADO)
    for mercado in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO):
        if mercado in rbt_por_mercado:
            passo.add(
                f"RBT12 do mercado {mercado} (regra {rbt.regra})",
                _dinheiro(rbt_por_mercado[mercado]),
                DISP_RBT12,
            )
    if fator is not None:
        passo.add("FS12 (folha dos 12 meses)", _dinheiro(fator.fs12), DISP_FS12)
        passo.add(
            "RBT12 conjunto (interno + externo)",
            _dinheiro(fator.rbt12_conjunto),
            DISP_RBT12_CONJUNTO,
        )
        passo.add(
            "Fator r = FS12 / RBT12 conjunto, truncado em 2 casas",
            f"{fator.valor}",
            DISP_FATOR_R,
        )
        if fator.regra_zero is not None:
            passo.add("Regra de zero aplicada", fator.regra_zero, DISP_REGRA_DE_ZERO)

    anexos: list[AnexoApurado] = []
    total_por_tributo: dict[str, Decimal] = {}
    total = Decimal("0.00")
    for mercado, anexo_numero in sorted(
        {(m, a) for m, a, _s in grupos}, key=lambda c: (c[0], c[1])
    ):
        anexo = tabelas.anexo(anexo_numero)
        rbt_mercado = rbt_por_mercado[mercado]
        faixa = anexo.faixa_da_receita(rbt_mercado)
        efetiva = aliquota_efetiva(rbt_mercado, faixa)
        itens, teto_aplicado, diferenca, destino = percentuais_efetivos(anexo, faixa, efetiva)
        percentual_de = dict(itens)
        rotulo = f"{mercado}, Anexo {anexo_numero}"

        enquadrados = sorted(enquadramentos_do_anexo[(mercado, anexo_numero)])
        passo.add(
            f"Anexo {anexo_numero} aplicado ao mercado {mercado}",
            anexo_numero,
            " | ".join(DISPOSITIVO_DO_ENQUADRAMENTO[e] for e in enquadrados),
        )
        passo.add(
            f"{rotulo}: faixa {faixa.numero} (RBT12 até {_dinheiro(faixa.limite_superior)})",
            f"faixa {faixa.numero}",
            anexo.dispositivo,
        )
        passo.add(f"{rotulo}: alíquota nominal", _fmt(faixa.aliquota_nominal, 6), anexo.dispositivo)
        passo.add(
            f"{rotulo}: parcela a deduzir", _dinheiro(faixa.parcela_a_deduzir), anexo.dispositivo
        )
        passo.add(f"{rotulo}: alíquota efetiva", _fmt(efetiva), DISP_ALIQUOTA_EFETIVA)
        passo.add(
            f"{rotulo}: repartição nominal da faixa",
            "; ".join(f"{t} {_fmt(p, 6)}" for t, p in faixa.reparticao),
            anexo.dispositivo,
        )
        if teto_aplicado:
            passo.add(
                f"{rotulo}: teto do ISS (5ª faixa, efetiva acima de "
                f"{anexo.teto_iss.limiar_efetiva})",
                "ISS 5%; federais = (efetiva − 5%) × redistribuição",
                anexo.teto_iss.dispositivo,
            )
        passo.add(
            f"{rotulo}: percentual efetivo por tributo",
            "; ".join(f"{t} {_fmt(p)}" for t, p in itens),
            DISP_REPARTICAO,
        )
        passo.add(
            f"{rotulo}: diferença centesimal, ao tributo {destino}",
            _fmt(diferenca),
            DISP_DIFERENCA,
        )

        segmentos: list[SegmentoApurado] = []
        total_anexo = Decimal("0.00")
        for (m, a, segmento), receita in sorted(grupos.items()):
            if m != mercado or a != anexo_numero:
                continue
            desconsiderados = _DESCONSIDERADOS.get(segmento, frozenset())
            linhas_tributo = []
            total_segmento = Decimal("0.00")
            for tributo in anexo.tributos:
                if tributo not in percentual_de:
                    continue
                desconsiderado = tributo in desconsiderados
                percentual = percentual_de[tributo]
                valor = Decimal("0.00") if desconsiderado else valor_do_tributo(receita, percentual)
                linhas_tributo.append(LinhaTributo(tributo, percentual, valor, desconsiderado))
                total_segmento += valor
                total_por_tributo[tributo] = total_por_tributo.get(tributo, Decimal("0.00")) + valor
                passo.add(
                    f"{rotulo}, {segmento}: {tributo} = {_dinheiro(receita)} × {_fmt(percentual)}"
                    + (" (desconsiderado)" if desconsiderado else ""),
                    _dinheiro(valor),
                    _DISP_DO_SEGMENTO[segmento],
                )
            segmentos.append(
                SegmentoApurado(
                    segmento=segmento,
                    receita=receita,
                    linhas=tuple(linhas_tributo),
                    total=total_segmento,
                )
            )
            total_anexo += total_segmento
        passo.add(f"{rotulo}: subtotal", _dinheiro(total_anexo), DISP_VALOR)
        total += total_anexo
        anexos.append(
            AnexoApurado(
                mercado=mercado,
                anexo=anexo_numero,
                rbt12=rbt_mercado,
                faixa=faixa.numero,
                limite_superior=faixa.limite_superior,
                aliquota_nominal=faixa.aliquota_nominal,
                parcela_a_deduzir=faixa.parcela_a_deduzir,
                aliquota_efetiva=efetiva,
                teto_iss_aplicado=teto_aplicado,
                diferenca=diferenca,
                tributo_da_diferenca=destino,
                segmentos=tuple(segmentos),
                total=total_anexo,
            )
        )

    passo.add("Total do pré-DAS", _dinheiro(total), DISP_VALOR)
    return PreDas(
        empresa_id=empresa.pk,
        ano=ano,
        mes=mes,
        rbt12=rbt_por_mercado,
        fator_r=fator,
        anexos=tuple(anexos),
        total=total,
        total_por_tributo=tuple(sorted(total_por_tributo.items())),
        memoria=tuple(memoria),
    )


class _Memoria:
    """Acumula os passos com ordem sequencial."""

    def __init__(self, destino: list[Passo]):
        self._destino = destino

    def add(self, descricao: str, valor: str, dispositivo: str) -> None:
        self._destino.append(
            Passo(
                ordem=len(self._destino) + 1,
                descricao=descricao,
                valor=valor,
                dispositivo=dispositivo,
            )
        )
