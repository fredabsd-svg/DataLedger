"""Tabelas do Simples Nacional, Anexos I a V — DL-075, frente A (dado puro).

NÍVEL 1 (AGENTS.md §3.1): estes números viram o valor do DAS que o contador
confere contra o PGDAS-D. Por isso:

- Nenhum número é calculado aqui. Cada valor é a transcrição literal de
  docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md (seção 2), lida no
  Planalto (LC 123/2006, Anexos na redação da LC 155/2016) em 08/10/2026.
- Percentuais são FRAÇÕES exatas (`Decimal`): "11,20%" vira Decimal("0.1120").
  Nunca `float`. A conversão é `scaleb`, sem arredondamento.
- Cada anexo carrega dispositivo, fonte e vigência (HI-70). A tabela de 2018 a
  2026 é `ANEXOS`. A de 01/01/2027 a 31/12/2028 é `ANEXOS_2027_2028` (DL-088,
  frente A1; HI-146): CBS e IBS no lugar de PIS e Cofins, transcritos do DOU da
  Res. CGSN 190/2026 (consulta de 09/10/2026, seção 1). A escolha é pela data do
  período: `anexo(numero, ano, mes)`. 2029 em diante NÃO está aqui (divergência
  entre a LC 123 e a Resolução, na 6ª faixa do Anexo I); a recusa mora em
  `apps.fiscal.pre_das`.

Fora desta tabela, de propósito (primeiro corte, HI-68):

- Repartição da 6ª faixa de ISS/ICMS (RBT12 acima de R$ 3.600.000,00). A regra
  depende do Manual (exemplos 8 e 10) e da Res. CGSN 140 (art. 25), que não foi
  lida no original. O pré-DAS recusa essa faixa.

Teto do ISS (notas (*) dos Anexos III e IV, LC 123 art. 18 § 1º-B, I): na 5ª
faixa, quando a alíquota efetiva passa do limiar, o ISS fica em 5% e a diferença
vai aos tributos federais, de forma proporcional. Os percentuais de
redistribuição estão em `TetoIss`. Cada conjunto soma 100,00%, conferido em
`apps/fiscal/tests/test_dl075_tabelas.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

FONTE_TABELAS = (
    "Planalto, LC 123/2006 (texto compilado com os Anexos I a V na redação da LC 155/2016), "
    "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm, consultado em 08/10/2026. "
    "Transcrição e conferência: docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md."
)
VIGENCIA_INICIO = date(2018, 1, 1)
VIGENCIA_FIM = date(2026, 12, 31)

# Tabela de 2027 a 2028 (DL-088, frente A1). Fonte: DOU 10/08/2026, Edição 149-A, Seção 1
# Extra A, Res. CGSN 190/2026, art. 6º (Anexos I a V da Res. CGSN 140 com a redação dada).
# Lida no texto oficial em 09/10/2026, conforme a consulta de mesma data (seção 1). Os números
# foram transcritos da consulta, à mão, e conferidos por teste que os escreve de novo.
VIGENCIA_2027_INICIO = date(2027, 1, 1)
VIGENCIA_2027_FIM = date(2028, 12, 31)
# Último mês com alguma tabela cadastrada. 2029 em diante é recusado (HI-146).
VIGENCIA_CADASTRADA_FIM = VIGENCIA_2027_FIM
FONTE_TABELAS_2027 = (
    "DOU 10/08/2026, Edição 149-A, Seção 1 – Extra A: Resolução CGSN nº 190, de 4 de agosto "
    "de 2026, art. 6º, "
    "https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-190-de-4-de-agosto-de-2026-724454118, "
    "lido em 09/10/2026 (texto HTML da Imprensa Nacional). Transcrição: "
    "docs/projeto/consultas/2026-10-09-contador-senior-virada-2027-simples.md, seção 1 (HI-146)."
)

# Tributos por nome, como aparecem nas tabelas do documento de consulta. CBS e IBS entram em 2027
# (Res. CGSN 190/2026, art. 4º, IX e X); PIS e Cofins saem (art. 4º, IV e V revogados).
IRPJ, CSLL, COFINS, PIS, CPP, ISS, ICMS, IPI, CBS, IBS = (
    "IRPJ",
    "CSLL",
    "COFINS",
    "PIS",
    "CPP",
    "ISS",
    "ICMS",
    "IPI",
    "CBS",
    "IBS",
)


def _pc(texto: str) -> Decimal:
    """'11,20%' → Decimal('0.1120'). Exato: escala -2 sobre o número digitado."""
    return Decimal(texto.strip().rstrip("%").replace(",", ".")).scaleb(-2)


def _rs(texto: str) -> Decimal:
    """'5.940,00' → Decimal('5940.00'). Traço de tabela ('–') vira zero."""
    if texto.strip() in ("–", "-"):
        return Decimal("0.00")
    return Decimal(texto.strip().replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class Faixa:
    """Uma das seis faixas de receita bruta acumulada (RBT12) de um anexo.

    `limite_superior` é inclusivo: a faixa vale para RBT12 até esse valor. A
    faixa seguinte começa em centavo acima. `reparticao` segue a ordem da tabela
    e traz só os tributos que existem na faixa (o traço vira ausência).
    """

    numero: int
    limite_superior: Decimal
    aliquota_nominal: Decimal
    parcela_a_deduzir: Decimal
    reparticao: tuple[tuple[str, Decimal], ...]

    def percentual(self, tributo: str) -> Decimal | None:
        for nome, valor in self.reparticao:
            if nome == tributo:
                return valor
        return None


@dataclass(frozen=True)
class TetoIss:
    """Teto de 5% do ISS (LC 123 art. 18 § 1º-B, I, e nota do anexo).

    Vale só na faixa `faixa` e só quando a alíquota efetiva é SUPERIOR a
    `limiar_efetiva`. Então o ISS vale `percentual_iss` e cada tributo federal
    recebe `(alíquota efetiva − percentual_iss) × redistribuicao[tributo]`.
    """

    limiar_efetiva: Decimal
    percentual_iss: Decimal
    faixa: int
    redistribuicao: tuple[tuple[str, Decimal], ...]
    dispositivo: str


@dataclass(frozen=True)
class Anexo:
    numero: str
    tributos: tuple[str, ...]
    faixas: tuple[Faixa, ...]
    teto_iss: TetoIss | None
    dispositivo: str
    fonte: str = FONTE_TABELAS
    inicio: date = VIGENCIA_INICIO
    fim: date = VIGENCIA_FIM

    def faixa(self, numero: int) -> Faixa:
        return self.faixas[numero - 1]

    def faixa_da_receita(self, rbt12: Decimal) -> Faixa:
        """Primeira faixa cujo limite superior cobre o RBT12 (inclusive).

        RBT12 acima do último limite é erro de chamada: quem chama (o pré-DAS)
        recusa antes, com mensagem nomeada.
        """
        for faixa in self.faixas:
            if rbt12 <= faixa.limite_superior:
                return faixa
        raise ValueError(f"RBT12 {rbt12} acima do último limite do Anexo {self.numero}.")


# ---------------------------------------------------------------------------
# Anexo I (comércio). Não é enquadramento de prestação de serviço; fica para
# conferência de dado e para o caso de referência do item 8.1 do Manual.
# ---------------------------------------------------------------------------

_LIMITES = (
    "180.000,00",
    "360.000,00",
    "720.000,00",
    "1.800.000,00",
    "3.600.000,00",
    "4.800.000,00",
)


def _faixas(linhas) -> tuple[Faixa, ...]:
    """Monta as seis faixas a partir de transcrições literais.

    Cada linha: (aliquota, parcela, [(tributo, percentual), ...]). A ordem dos
    limites vem de `_LIMITES`, a mesma para os cinco anexos (faixas idênticas).
    """
    faixas = []
    for indice, (aliquota, parcela, reparticao) in enumerate(linhas, start=1):
        faixas.append(
            Faixa(
                numero=indice,
                limite_superior=_rs(_LIMITES[indice - 1]),
                aliquota_nominal=_pc(aliquota),
                parcela_a_deduzir=_rs(parcela),
                reparticao=tuple((tributo, _pc(valor)) for tributo, valor in reparticao),
            )
        )
    return tuple(faixas)


_ANEXO_I = _faixas(
    (
        (
            "4,00%",
            "–",
            (
                (IRPJ, "5,50%"),
                (CSLL, "3,50%"),
                (COFINS, "12,74%"),
                (PIS, "2,76%"),
                (CPP, "41,50%"),
                (ICMS, "34,00%"),
            ),
        ),
        (
            "7,30%",
            "5.940,00",
            (
                (IRPJ, "5,50%"),
                (CSLL, "3,50%"),
                (COFINS, "12,74%"),
                (PIS, "2,76%"),
                (CPP, "41,50%"),
                (ICMS, "34,00%"),
            ),
        ),
        (
            "9,50%",
            "13.860,00",
            (
                (IRPJ, "5,50%"),
                (CSLL, "3,50%"),
                (COFINS, "12,74%"),
                (PIS, "2,76%"),
                (CPP, "42,00%"),
                (ICMS, "33,50%"),
            ),
        ),
        (
            "10,70%",
            "22.500,00",
            (
                (IRPJ, "5,50%"),
                (CSLL, "3,50%"),
                (COFINS, "12,74%"),
                (PIS, "2,76%"),
                (CPP, "42,00%"),
                (ICMS, "33,50%"),
            ),
        ),
        (
            "14,30%",
            "87.300,00",
            (
                (IRPJ, "5,50%"),
                (CSLL, "3,50%"),
                (COFINS, "12,74%"),
                (PIS, "2,76%"),
                (CPP, "42,00%"),
                (ICMS, "33,50%"),
            ),
        ),
        (
            "19,00%",
            "378.000,00",
            (
                (IRPJ, "13,50%"),
                (CSLL, "10,00%"),
                (COFINS, "28,27%"),
                (PIS, "6,13%"),
                (CPP, "42,10%"),
            ),
        ),
    )
)

# ---------------------------------------------------------------------------
# Anexo II (indústria). Mesma razão do I: dado de conferência.
# ---------------------------------------------------------------------------

_REP_II = (
    (IRPJ, "5,50%"),
    (CSLL, "3,50%"),
    (COFINS, "11,51%"),
    (PIS, "2,49%"),
    (CPP, "37,50%"),
    (IPI, "7,50%"),
    (ICMS, "32,00%"),
)
_ANEXO_II = _faixas(
    (
        ("4,50%", "–", _REP_II),
        ("7,80%", "5.940,00", _REP_II),
        ("10,00%", "13.860,00", _REP_II),
        ("11,20%", "22.500,00", _REP_II),
        ("14,70%", "85.500,00", _REP_II),
        (
            "30,00%",
            "720.000,00",
            (
                (IRPJ, "8,50%"),
                (CSLL, "7,50%"),
                (COFINS, "20,96%"),
                (PIS, "4,54%"),
                (CPP, "23,50%"),
                (IPI, "35,00%"),
            ),
        ),
    )
)

# ---------------------------------------------------------------------------
# Anexo III (serviços em geral; também recebe as atividades do § 5º-D/5º-M com
# fator r ≥ 0,28). Teto do ISS na 5ª faixa, limiar 14,92537%.
# ---------------------------------------------------------------------------

_ANEXO_III = _faixas(
    (
        (
            "6,00%",
            "–",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (COFINS, "12,82%"),
                (PIS, "2,78%"),
                (CPP, "43,40%"),
                (ISS, "33,50%"),
            ),
        ),
        (
            "11,20%",
            "9.360,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (COFINS, "14,05%"),
                (PIS, "3,05%"),
                (CPP, "43,40%"),
                (ISS, "32,00%"),
            ),
        ),
        (
            "13,50%",
            "17.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (COFINS, "13,64%"),
                (PIS, "2,96%"),
                (CPP, "43,40%"),
                (ISS, "32,50%"),
            ),
        ),
        (
            "16,00%",
            "35.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (COFINS, "13,64%"),
                (PIS, "2,96%"),
                (CPP, "43,40%"),
                (ISS, "32,50%"),
            ),
        ),
        (
            "21,00%",
            "125.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (COFINS, "12,82%"),
                (PIS, "2,78%"),
                (CPP, "43,40%"),
                (ISS, "33,50%"),
            ),
        ),
        (
            "33,00%",
            "648.000,00",
            (
                (IRPJ, "35,00%"),
                (CSLL, "15,00%"),
                (COFINS, "16,03%"),
                (PIS, "3,47%"),
                (CPP, "30,50%"),
            ),
        ),
    )
)

_ANEXO_IV = _faixas(
    (
        (
            "4,50%",
            "–",
            (
                (IRPJ, "18,80%"),
                (CSLL, "15,20%"),
                (COFINS, "17,67%"),
                (PIS, "3,83%"),
                (ISS, "44,50%"),
            ),
        ),
        (
            "9,00%",
            "8.100,00",
            (
                (IRPJ, "19,80%"),
                (CSLL, "15,20%"),
                (COFINS, "20,55%"),
                (PIS, "4,45%"),
                (ISS, "40,00%"),
            ),
        ),
        (
            "10,20%",
            "12.420,00",
            (
                (IRPJ, "20,80%"),
                (CSLL, "15,20%"),
                (COFINS, "19,73%"),
                (PIS, "4,27%"),
                (ISS, "40,00%"),
            ),
        ),
        (
            "14,00%",
            "39.780,00",
            (
                (IRPJ, "17,80%"),
                (CSLL, "19,20%"),
                (COFINS, "18,90%"),
                (PIS, "4,10%"),
                (ISS, "40,00%"),
            ),
        ),
        (
            "22,00%",
            "183.780,00",
            (
                (IRPJ, "18,80%"),
                (CSLL, "19,20%"),
                (COFINS, "18,08%"),
                (PIS, "3,92%"),
                (ISS, "40,00%"),
            ),
        ),
        (
            "33,00%",
            "828.000,00",
            ((IRPJ, "53,50%"), (CSLL, "21,50%"), (COFINS, "20,55%"), (PIS, "4,45%")),
        ),
    )
)

_ANEXO_V = _faixas(
    (
        (
            "15,50%",
            "–",
            (
                (IRPJ, "25,00%"),
                (CSLL, "15,00%"),
                (COFINS, "14,10%"),
                (PIS, "3,05%"),
                (CPP, "28,85%"),
                (ISS, "14,00%"),
            ),
        ),
        (
            "18,00%",
            "4.500,00",
            (
                (IRPJ, "23,00%"),
                (CSLL, "15,00%"),
                (COFINS, "14,10%"),
                (PIS, "3,05%"),
                (CPP, "27,85%"),
                (ISS, "17,00%"),
            ),
        ),
        (
            "19,50%",
            "9.900,00",
            (
                (IRPJ, "24,00%"),
                (CSLL, "15,00%"),
                (COFINS, "14,92%"),
                (PIS, "3,23%"),
                (CPP, "23,85%"),
                (ISS, "19,00%"),
            ),
        ),
        (
            "20,50%",
            "17.100,00",
            (
                (IRPJ, "21,00%"),
                (CSLL, "15,00%"),
                (COFINS, "15,74%"),
                (PIS, "3,41%"),
                (CPP, "23,85%"),
                (ISS, "21,00%"),
            ),
        ),
        (
            "23,00%",
            "62.100,00",
            (
                (IRPJ, "23,00%"),
                (CSLL, "12,50%"),
                (COFINS, "14,10%"),
                (PIS, "3,05%"),
                (CPP, "23,85%"),
                (ISS, "23,50%"),
            ),
        ),
        (
            "30,50%",
            "540.000,00",
            (
                (IRPJ, "35,00%"),
                (CSLL, "15,50%"),
                (COFINS, "16,44%"),
                (PIS, "3,56%"),
                (CPP, "29,50%"),
            ),
        ),
    )
)

_TETO_III = TetoIss(
    limiar_efetiva=_pc("14,92537%"),
    percentual_iss=_pc("5%"),
    faixa=5,
    redistribuicao=(
        (IRPJ, _pc("6,02%")),
        (CSLL, _pc("5,26%")),
        (COFINS, _pc("19,28%")),
        (PIS, _pc("4,18%")),
        (CPP, _pc("65,26%")),
    ),
    dispositivo=(
        "LC 123/2006, art. 18, § 1º-B, I, e nota (*) do Anexo III (redação da LC 155/2016): "
        "na 5ª faixa, com alíquota efetiva superior a 14,92537%, ISS fixo em 5% e "
        "(alíquota efetiva − 5%) × percentual de cada tributo federal"
    ),
)

_TETO_IV = TetoIss(
    limiar_efetiva=_pc("12,5%"),
    percentual_iss=_pc("5%"),
    faixa=5,
    redistribuicao=(
        (IRPJ, _pc("31,33%")),
        (CSLL, _pc("32,00%")),
        (COFINS, _pc("30,13%")),
        (PIS, _pc("6,54%")),
    ),
    dispositivo=(
        "LC 123/2006, art. 18, § 1º-B, I, e nota (*) do Anexo IV (redação da LC 155/2016): "
        "na 5ª faixa, com alíquota efetiva superior a 12,5%, ISS fixo em 5% e "
        "(alíquota efetiva − 5%) × percentual de cada tributo federal"
    ),
)

# ---------------------------------------------------------------------------
# Tabelas de 2027 a 2028 (DL-088, A1). Transcritas da consulta de 09/10/2026, seção 1, "Anexos I
# a V — vigência 01/01/2027 a 31/12/2028 (lido, DOU)". Faixas de RBT12 iguais às de 2026
# (`_LIMITES`). Cada linha de repartição soma 100,00%: conferido em
# `apps/fiscal/tests/test_dl088_tabelas_2027.py`.
#
# Anexo I: 1ª e 2ª faixas têm uma repartição; 3ª a 5ª, outra; a 6ª, a sua (sem ICMS nem IBS).
# Anexo II: a mesma repartição nas cinco primeiras faixas; a 6ª, a sua (sem ICMS nem IBS).
# ---------------------------------------------------------------------------

_REP_I_1A_2A = (
    (IRPJ, "5,50%"),
    (CSLL, "3,50%"),
    (CBS, "15,33%"),
    (CPP, "41,50%"),
    (ICMS, "34,00%"),
    (IBS, "0,17%"),
)
_REP_I_3A_5A = (
    (IRPJ, "5,50%"),
    (CSLL, "3,50%"),
    (CBS, "15,33%"),
    (CPP, "42,00%"),
    (ICMS, "33,50%"),
    (IBS, "0,17%"),
)
_ANEXO_I_2027 = _faixas(
    (
        ("4,00%", "–", _REP_I_1A_2A),
        ("7,30%", "5.940,00", _REP_I_1A_2A),
        ("9,50%", "13.860,00", _REP_I_3A_5A),
        ("10,70%", "22.500,00", _REP_I_3A_5A),
        ("14,30%", "87.300,00", _REP_I_3A_5A),
        (
            "18,90%",
            "378.000,00",
            (
                (IRPJ, "13,58%"),
                (CSLL, "10,06%"),
                (CBS, "34,02%"),
                (CPP, "42,34%"),
            ),
        ),
    )
)

_REP_II_2027 = (
    (IRPJ, "5,50%"),
    (CSLL, "3,50%"),
    (CBS, "13,85%"),
    (CPP, "37,50%"),
    (IPI, "7,50%"),
    (ICMS, "32,00%"),
    (IBS, "0,15%"),
)
_ANEXO_II_2027 = _faixas(
    (
        ("4,50%", "–", _REP_II_2027),
        ("7,80%", "5.940,00", _REP_II_2027),
        ("10,00%", "13.860,00", _REP_II_2027),
        ("11,20%", "22.500,00", _REP_II_2027),
        ("14,70%", "85.500,00", _REP_II_2027),
        (
            "29,90%",
            "720.000,00",
            (
                (IRPJ, "8,53%"),
                (CSLL, "7,53%"),
                (CBS, "25,22%"),
                (CPP, "23,59%"),
                (IPI, "35,13%"),
            ),
        ),
    )
)

_ANEXO_III_2027 = _faixas(
    (
        (
            "6,00%",
            "–",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (CBS, "15,43%"),
                (CPP, "43,40%"),
                (ISS, "33,50%"),
                (IBS, "0,17%"),
            ),
        ),
        (
            "11,20%",
            "9.360,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (CBS, "16,91%"),
                (CPP, "43,40%"),
                (ISS, "32,00%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "13,50%",
            "17.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (CBS, "16,41%"),
                (CPP, "43,40%"),
                (ISS, "32,50%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "16,00%",
            "35.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (CBS, "16,41%"),
                (CPP, "43,40%"),
                (ISS, "32,50%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "21,00%",
            "125.640,00",
            (
                (IRPJ, "4,00%"),
                (CSLL, "3,50%"),
                (CBS, "15,43%"),
                (CPP, "43,40%"),
                (ISS, "33,50%"),
                (IBS, "0,17%"),
            ),
        ),
        (
            "32,90%",
            "648.000,00",
            (
                (IRPJ, "35,09%"),
                (CSLL, "15,04%"),
                (CBS, "19,29%"),
                (CPP, "30,58%"),
            ),
        ),
    )
)

_ANEXO_IV_2027 = _faixas(
    (
        (
            "4,50%",
            "–",
            (
                (IRPJ, "18,80%"),
                (CSLL, "15,20%"),
                (CBS, "21,26%"),
                (ISS, "44,50%"),
                (IBS, "0,24%"),
            ),
        ),
        (
            "9,00%",
            "8.100,00",
            (
                (IRPJ, "19,80%"),
                (CSLL, "15,20%"),
                (CBS, "24,73%"),
                (ISS, "40,00%"),
                (IBS, "0,27%"),
            ),
        ),
        (
            "10,20%",
            "12.420,00",
            (
                (IRPJ, "20,80%"),
                (CSLL, "15,20%"),
                (CBS, "23,74%"),
                (ISS, "40,00%"),
                (IBS, "0,26%"),
            ),
        ),
        (
            "14,00%",
            "39.780,00",
            (
                (IRPJ, "17,80%"),
                (CSLL, "19,20%"),
                (CBS, "22,75%"),
                (ISS, "40,00%"),
                (IBS, "0,25%"),
            ),
        ),
        (
            "22,00%",
            "183.780,00",
            (
                (IRPJ, "18,80%"),
                (CSLL, "19,20%"),
                (CBS, "21,76%"),
                (ISS, "40,00%"),
                (IBS, "0,24%"),
            ),
        ),
        (
            "32,90%",
            "828.000,00",
            (
                (IRPJ, "53,71%"),
                (CSLL, "21,59%"),
                (CBS, "24,70%"),
            ),
        ),
    )
)

_ANEXO_V_2027 = _faixas(
    (
        (
            "15,50%",
            "–",
            (
                (IRPJ, "25,00%"),
                (CSLL, "15,00%"),
                (CBS, "16,96%"),
                (CPP, "28,85%"),
                (ISS, "14,00%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "18,00%",
            "4.500,00",
            (
                (IRPJ, "23,00%"),
                (CSLL, "15,00%"),
                (CBS, "16,96%"),
                (CPP, "27,85%"),
                (ISS, "17,00%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "19,50%",
            "9.900,00",
            (
                (IRPJ, "24,00%"),
                (CSLL, "15,00%"),
                (CBS, "17,95%"),
                (CPP, "23,85%"),
                (ISS, "19,00%"),
                (IBS, "0,20%"),
            ),
        ),
        (
            "20,50%",
            "17.100,00",
            (
                (IRPJ, "21,00%"),
                (CSLL, "15,00%"),
                (CBS, "18,94%"),
                (CPP, "23,85%"),
                (ISS, "21,00%"),
                (IBS, "0,21%"),
            ),
        ),
        (
            "23,00%",
            "62.100,00",
            (
                (IRPJ, "23,00%"),
                (CSLL, "12,50%"),
                (CBS, "16,96%"),
                (CPP, "23,85%"),
                (ISS, "23,50%"),
                (IBS, "0,19%"),
            ),
        ),
        (
            "30,40%",
            "540.000,00",
            (
                (IRPJ, "35,10%"),
                (CSLL, "15,54%"),
                (CBS, "19,78%"),
                (CPP, "29,58%"),
            ),
        ),
    )
)

# Teto do ISS de 2027 (nota (*) dos Anexos III e IV). A redistribuição vai aos federais e ao IBS
# (Res. CGSN 190/2026, art. 21, III: "tributos federais e IBS da mesma faixa"). Limiares de 2026.
_TETO_III_2027 = TetoIss(
    limiar_efetiva=_pc("14,92537%"),
    percentual_iss=_pc("5%"),
    faixa=5,
    redistribuicao=(
        (IRPJ, _pc("6,02%")),
        (CSLL, _pc("5,26%")),
        (CBS, _pc("23,20%")),
        (CPP, _pc("65,26%")),
        (IBS, _pc("0,26%")),
    ),
    dispositivo=(
        "Res. CGSN 190/2026, art. 21, III, e nota (*) do Anexo III (consulta de 09/10/2026, "
        "seção 1): "
        "na 5ª faixa, com alíquota efetiva superior a 14,92537%, ISS fixo em 5% e "
        "(alíquota efetiva − 5%) × percentual de cada tributo federal e do IBS"
    ),
)

_TETO_IV_2027 = TetoIss(
    limiar_efetiva=_pc("12,5%"),
    percentual_iss=_pc("5%"),
    faixa=5,
    redistribuicao=(
        (IRPJ, _pc("31,33%")),
        (CSLL, _pc("32,00%")),
        (CBS, _pc("36,27%")),
        (IBS, _pc("0,40%")),
    ),
    dispositivo=(
        "Res. CGSN 190/2026, art. 21, III, e nota (*) do Anexo IV (consulta de 09/10/2026, "
        "seção 1): "
        "na 5ª faixa, com alíquota efetiva superior a 12,5%, ISS fixo em 5% e "
        "(alíquota efetiva − 5%) × percentual de cada tributo federal e do IBS"
    ),
)

# Anexo IV não tem coluna de CPP: a contribuição patronal fica FORA do DAS
# (LC 123 art. 18 § 5º-C, com o art. 13, VI). Por isso `tributos` não a traz.
ANEXOS: dict[str, Anexo] = {
    "I": Anexo(
        numero="I",
        tributos=(IRPJ, CSLL, COFINS, PIS, CPP, ICMS),
        faixas=_ANEXO_I,
        teto_iss=None,
        dispositivo="LC 123/2006, art. 18, § 1º-B e Anexo I (redação da LC 155/2016)",
    ),
    "II": Anexo(
        numero="II",
        tributos=(IRPJ, CSLL, COFINS, PIS, CPP, IPI, ICMS),
        faixas=_ANEXO_II,
        teto_iss=None,
        dispositivo="LC 123/2006, art. 18, § 1º-B e Anexo II (redação da LC 155/2016)",
    ),
    "III": Anexo(
        numero="III",
        tributos=(IRPJ, CSLL, COFINS, PIS, CPP, ISS),
        faixas=_ANEXO_III,
        teto_iss=_TETO_III,
        dispositivo="LC 123/2006, art. 18, § 1º-B e Anexo III (redação da LC 155/2016)",
    ),
    "IV": Anexo(
        numero="IV",
        tributos=(IRPJ, CSLL, COFINS, PIS, ISS),
        faixas=_ANEXO_IV,
        teto_iss=_TETO_IV,
        dispositivo="LC 123/2006, art. 18, § 1º-B e Anexo IV (redação da LC 155/2016)",
    ),
    "V": Anexo(
        numero="V",
        tributos=(IRPJ, CSLL, COFINS, PIS, CPP, ISS),
        faixas=_ANEXO_V,
        teto_iss=None,
        dispositivo="LC 123/2006, art. 18, § 1º-B e Anexo V (redação da LC 155/2016)",
    ),
}


# Tabela de 2027 a 2028 (DL-088). Mesmo conjunto de anexos da tabela de 2018 a 2026; o que muda é
# o tributo (CBS e IBS no lugar de PIS e Cofins), a 6ª faixa e os tetos do ISS.
_DISPOSITIVO_DO_ANEXO_2027 = (
    "Res. CGSN 190/2026, art. 6º (Anexo {n} da Res. CGSN 140/2018 na redação dada pela Res. 190); "
    "LC 123/2006, art. 18, § 1º-B, com o Anexo {n} na redação da LC 214/2025, art. 519"
)
ANEXOS_2027_2028: dict[str, Anexo] = {
    "I": Anexo(
        numero="I",
        tributos=(IRPJ, CSLL, CBS, CPP, ICMS, IBS),
        faixas=_ANEXO_I_2027,
        teto_iss=None,
        dispositivo=_DISPOSITIVO_DO_ANEXO_2027.format(n="I"),
        fonte=FONTE_TABELAS_2027,
        inicio=VIGENCIA_2027_INICIO,
        fim=VIGENCIA_2027_FIM,
    ),
    "II": Anexo(
        numero="II",
        tributos=(IRPJ, CSLL, CBS, CPP, IPI, ICMS, IBS),
        faixas=_ANEXO_II_2027,
        teto_iss=None,
        dispositivo=_DISPOSITIVO_DO_ANEXO_2027.format(n="II"),
        fonte=FONTE_TABELAS_2027,
        inicio=VIGENCIA_2027_INICIO,
        fim=VIGENCIA_2027_FIM,
    ),
    "III": Anexo(
        numero="III",
        tributos=(IRPJ, CSLL, CBS, CPP, ISS, IBS),
        faixas=_ANEXO_III_2027,
        teto_iss=_TETO_III_2027,
        dispositivo=_DISPOSITIVO_DO_ANEXO_2027.format(n="III"),
        fonte=FONTE_TABELAS_2027,
        inicio=VIGENCIA_2027_INICIO,
        fim=VIGENCIA_2027_FIM,
    ),
    "IV": Anexo(
        numero="IV",
        tributos=(IRPJ, CSLL, CBS, ISS, IBS),
        faixas=_ANEXO_IV_2027,
        teto_iss=_TETO_IV_2027,
        dispositivo=_DISPOSITIVO_DO_ANEXO_2027.format(n="IV"),
        fonte=FONTE_TABELAS_2027,
        inicio=VIGENCIA_2027_INICIO,
        fim=VIGENCIA_2027_FIM,
    ),
    "V": Anexo(
        numero="V",
        tributos=(IRPJ, CSLL, CBS, CPP, ISS, IBS),
        faixas=_ANEXO_V_2027,
        teto_iss=None,
        dispositivo=_DISPOSITIVO_DO_ANEXO_2027.format(n="V"),
        fonte=FONTE_TABELAS_2027,
        inicio=VIGENCIA_2027_INICIO,
        fim=VIGENCIA_2027_FIM,
    ),
}

_TABELAS_POR_VIGENCIA = (ANEXOS, ANEXOS_2027_2028)


def anexo(numero: str, ano: int = 2026, mes: int = 12) -> Anexo:
    """Tabela do Anexo `numero` vigente em `mes/ano`.

    A escolha é pela data do PERÍODO (DL-088): 2027 e 2028 usam `ANEXOS_2027_2028`; 2018 a 2026,
    `ANEXOS`. O padrão `2026/12` existe só para os chamadores anteriores à DL-088, que apuram 2026
    e não passam período. Quem apura um período DEVE passar `ano` e `mes`: é o que impede a tabela
    de 2026 de ser usada em 2027. Fora das vigências cadastradas, levanta ValueError.
    """
    referencia = date(ano, mes, 1)
    for tabela in _TABELAS_POR_VIGENCIA:
        candidato = tabela[numero]  # KeyError se o anexo não existe: erro de chamada.
        if candidato.inicio <= referencia <= candidato.fim:
            return candidato
    raise ValueError(f"Não há tabela do Anexo {numero} vigente em {mes:02d}/{ano}.")


def tabelas_vigentes_em(ano: int, mes: int) -> bool:
    """True se o mês cai em alguma vigência cadastrada (01/01/2018 a 31/12/2028).

    2029 em diante é False: a divergência entre a LC 123 e a Res. CGSN 190/2026 na 6ª faixa do
    Anexo I (HI-146) ainda não foi resolvida. A recusa com motivo nomeado fica em `pre_das`.
    """
    referencia = date(ano, mes, 1)
    return VIGENCIA_INICIO <= referencia <= VIGENCIA_CADASTRADA_FIM
