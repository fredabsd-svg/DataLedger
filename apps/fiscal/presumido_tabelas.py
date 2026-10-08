"""Tabelas do Lucro Presumido, IRPJ e CSLL — DL-079, frente A (dado puro, com fonte e vigência).

NÍVEL 1 (AGENTS.md §3.1): estes números viram o valor do IRPJ e da CSLL que o contador confere.
Por isso:

- Nenhum valor é calculado aqui. Cada número tem fonte e vigência. As frações são `Decimal`
  exato (`Decimal("0.15")` é 15%). Nunca `float`.
- Fonte geral: docs/projeto/consultas/2026-10-08-contador-senior-presumido.md (itens 1 a 12). A
  consulta foi conferida nos textos oficiais lidos em 08/10/2026 (Planalto e gov.br).
- Hipóteses e pendências ficam em docs/projeto/requisitos.md (HI-100 a HI-107) e na consulta.

Nada aqui é regra de calendário nem de alíquota que não esteja nos textos citados ao lado de
cada constante. A lei de feriados vem com a data da leitura, porque a fonte pode mudar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# ---------------------------------------------------------------------------
# Tributos
# ---------------------------------------------------------------------------

IRPJ = "irpj"
CSLL = "csll"
AMBOS = "ambos"
TRIBUTOS = (IRPJ, CSLL)

# Ano em que o acréscimo da LC 224 passa a valer. Antes dele a apuração desta frente não
# existe: a recusa é nomeada em `apps.fiscal.presumido`.
ANO_INICIAL_LC224 = 2026

# ---------------------------------------------------------------------------
# Catálogo fechado de atividades de presunção (Lei 9.249/1995, arts. 15 e 20)
# ---------------------------------------------------------------------------

FONTE_PERCENTUAIS = (
    "Lei 9.249/1995, art. 15 (IRPJ: caput e § 1º, III) e art. 20 (CSLL: incisos I a III, "
    "red. LC 167/2019); serviços hospitalares: art. 15, § 1º, III, 'a', com os requisitos "
    "de sociedade empresária e Anvisa. Texto lido no Planalto em 08/10/2026. Consulta "
    "2026-10-08-contador-senior-presumido.md, itens 2 e 3."
)

COMERCIO_INDUSTRIA_TRANSPORTE_CARGA = "comercio_industria_transporte_carga"
REVENDA_COMBUSTIVEIS = "revenda_combustiveis"
TRANSPORTE_PASSAGEIROS = "transporte_passageiros"
SERVICOS_GERAIS = "servicos_gerais"
INTERMEDIACAO_NEGOCIOS = "intermediacao_negocios"
ADMINISTRACAO_LOCACAO_CESSAO_BENS = "administracao_locacao_cessao_bens"
SERVICOS_HOSPITALARES = "servicos_hospitalares"


@dataclass(frozen=True)
class AtividadePresuncao:
    """Uma atividade do catálogo. Os percentuais são FRAÇÕES (8% = 0,08), nunca `float`."""

    codigo: str
    rotulo: str
    irpj: Decimal
    csll: Decimal
    observacao: str = ""


CATALOGO_ATIVIDADES = (
    AtividadePresuncao(
        COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
        "Comércio, indústria e transporte de cargas",
        Decimal("0.08"),
        Decimal("0.12"),
    ),
    AtividadePresuncao(
        REVENDA_COMBUSTIVEIS,
        "Revenda de combustíveis",
        Decimal("0.016"),
        Decimal("0.12"),
        "Revenda de combustíveis: 1,6% no IRPJ (Lei 9.249, art. 15, conforme consulta, item 2).",
    ),
    AtividadePresuncao(
        TRANSPORTE_PASSAGEIROS,
        "Transporte de passageiros",
        Decimal("0.16"),
        Decimal("0.12"),
    ),
    AtividadePresuncao(
        SERVICOS_GERAIS,
        "Serviços em geral",
        Decimal("0.32"),
        Decimal("0.32"),
    ),
    AtividadePresuncao(
        INTERMEDIACAO_NEGOCIOS,
        "Intermediação de negócios",
        Decimal("0.32"),
        Decimal("0.32"),
    ),
    AtividadePresuncao(
        ADMINISTRACAO_LOCACAO_CESSAO_BENS,
        "Administração, locação e cessão de bens",
        Decimal("0.32"),
        Decimal("0.32"),
    ),
    AtividadePresuncao(
        SERVICOS_HOSPITALARES,
        "Serviços hospitalares",
        Decimal("0.08"),
        Decimal("0.12"),
        "Só com os dois requisitos legais confirmados pelo contador (HI-101).",
    ),
)

ATIVIDADES_POR_CODIGO = {atividade.codigo: atividade for atividade in CATALOGO_ATIVIDADES}
CODIGOS_DE_ATIVIDADE = tuple(atividade.codigo for atividade in CATALOGO_ATIVIDADES)

# ---------------------------------------------------------------------------
# Alíquotas do IRPJ e da CSLL
# ---------------------------------------------------------------------------

FONTE_ALIQUOTAS = (
    "IRPJ: Lei 9.249/1995, art. 3º, caput (15%) e § 1º (adicional de 10% sobre a parcela que "
    "exceder R$ 20.000,00 x meses do período). CSLL: Lei 7.689/1988, art. 3º (9% para as demais "
    "pessoas jurídicas). Textos lidos no Planalto em 08/10/2026. Consulta, item 1."
)
ALIQUOTA_IRPJ = Decimal("0.15")
ALIQUOTA_ADICIONAL_IRPJ = Decimal("0.10")
LIMITE_ADICIONAL_POR_MES = Decimal("20000.00")
ALIQUOTA_CSLL = Decimal("0.09")

# Fator do acréscimo: MULTIPLICA o percentual de presunção (8% vira 8,8%). Não soma pontos.
# LC 224/2025, art. 4º, § 4º, VII; Decreto 12.808/2025, art. 12; P&R da RFB, itens 11 e 14.
FATOR_ACRESCIMO_LC224 = Decimal("1.10")

# ---------------------------------------------------------------------------
# Limite da LC 224 (LC 224/2025, art. 4º, § 5º; IN RFB 2.305/2025, art. 15, red. IN 2.306/2026)
# ---------------------------------------------------------------------------

FONTE_LIMITE_LC224 = (
    "LC 224/2025, art. 4º, §§ 4º, VII e 5º, e art. 14; IN RFB 2.305/2025, art. 15, §§ 2º a 6º e "
    "9º, na redação da IN RFB 2.306/2026 (cópia íntegra, DOU de 23/01/2026); P&R da RFB, "
    "itens 11 a 14 (V5, 30/07/2026). Lidos em 08/10/2026. Redação ORIGINAL dos incisos I e II do "
    "art. 15 da IN 2.305 NÃO foi conferida (pendência da consulta)."
)
LIMITE_TRIMESTRAL_LC224 = Decimal("1250000.00")
# O limite anual não é gravado: é `N x LIMITE_TRIMESTRAL_LC224`, com N os trimestres em atividade.

# Início do acréscimo, por tributo. O IRPJ começa no 1º trimestre; a CSLL, só em 01/04/2026
# (noventena do art. 195, § 6º da CF, não o art. 150, III, "c", que não se aplica ao IRPJ).
# LC 224/2025, art. 14, I, "a" e III; P&R da RFB, itens 12 e 13.
INICIO_ACRESCIMO = {
    IRPJ: date(2026, 1, 1),
    CSLL: date(2026, 4, 1),
}

# Divisor da estimativa da CSLL retida quando tpRetPisCofins = 3 (PIS + Cofins + CSLL).
# Lei 10.833/2003, art. 31, caput: 1% (CSLL) + 3% (Cofins) + 0,65% (PIS) = 4,65%. Só é
# estimativa, sempre marcada "estimada" (HI-103).
FATOR_ESTIMATIVA_CSLL_TP3 = Decimal("4.65")

# Aviso fixo sobre as ADIs contra o acréscimo (consulta, item 10; portal do STF, lido em
# 08/10/2026). É texto de conferência, não decisão judicial.
ADI_REFERENCIA = "ADI 7936 e ADI 7944"
DATA_CONFERENCIA_ADI = date(2026, 10, 8)
AVISO_ADI = (
    f"{ADI_REFERENCIA} sem decisão cautelar ou de mérito visível em 08/10/2026 (última "
    "manifestação do andamento em 27/08/2026). Liminar de primeira instância vale só para a "
    "parte que a obteve."
)

# ---------------------------------------------------------------------------
# Códigos de DARF (informativos; o produto NÃO gera DARF)
# ---------------------------------------------------------------------------

CODIGO_DARF = {IRPJ: "2089", CSLL: "2372"}
ROTULO_DARF = {
    IRPJ: "2089 — IRPJ Lucro Presumido",
    CSLL: "2372 — CSLL Lucro Presumido",
}
FONTE_CODIGOS_DARF = (
    "Receita Federal, tabelas de códigos e extensões de IRPJ (gov.br, atualizada em 12/03/2024) "
    "e de CSLL (mesma data). Consultadas em 08/10/2026: "
    "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-"
    "demonstrativos/dctf/tabelas-de-codigos-extensoes/irpj e .../csll."
)

# ---------------------------------------------------------------------------
# Feriados nacionais fixos, para o último dia útil (HI-105)
# ---------------------------------------------------------------------------

FONTE_FERIADOS = (
    "Lei 662/1949, art. 1º (red. Lei 10.607/2002): 1/1, 21/4, 1/5, 7/9, 2/11, 15/11 e 25/12; "
    "Lei 6.802/1980, art. 1º: 12/10; Lei 14.759/2023, art. 1º: 20/11 ('Fica declarado feriado "
    "nacional o dia 20 de novembro'). Lei 14.759 lida no Planalto em 08/10/2026 (texto de "
    "21/12/2023, DOU de 22/12/2023). Feriados estaduais e municipais ficam fora (HI-105)."
)
# (mês, dia, nome, fundamento)
FERIADOS_NACIONAIS_FIXOS = (
    (1, 1, "Confraternização Universal", "Lei 662/1949, art. 1º"),
    (4, 21, "Tiradentes", "Lei 662/1949, art. 1º"),
    (5, 1, "Dia do Trabalho", "Lei 662/1949, art. 1º"),
    (9, 7, "Independência do Brasil", "Lei 662/1949, art. 1º"),
    (10, 12, "Nossa Senhora Aparecida", "Lei 6.802/1980, art. 1º"),
    (11, 2, "Finados", "Lei 662/1949, art. 1º"),
    (11, 15, "Proclamação da República", "Lei 662/1949, art. 1º"),
    (11, 20, "Dia Nacional de Zumbi e da Consciência Negra", "Lei 14.759/2023, art. 1º"),
    (12, 25, "Natal", "Lei 662/1949, art. 1º"),
)
# Ano a partir do qual o feriado de 20/11 vale. A Lei 14.759 é de 21/12/2023.
ANO_FERIADO_20_NOVEMBRO = 2023

MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
