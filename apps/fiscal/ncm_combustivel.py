"""NCM de combustível e de lubrificante — DL-083, frente A (HI-139; auditoria da DL-083, A6).

Fonte: Nomenclatura NCM vigente, Portal Único Siscomex, https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO
, 'Vigente em 09/10/2026', Resolução Gecex nº 926/2026, sha256
4ca9f857fc20393718ee5d413a2842016f6fad0bc10cb92756f2c2f7418de59b, lida em 09/10/2026;
classificação pela descrição oficial; Lei 9.249, art. 15, § 1º, I (HI-139).

Por que existe: o 1,6% de IRPJ vale só para revenda de "combustível derivado de petróleo, álcool
etílico carburante e gás natural" (Lei 9.249, art. 15, § 1º, I). Lubrificante não é combustível. A
descrição de CFOP ("combustíveis ou lubrificantes") junta os dois na mesma faixa por razão de ICMS,
então a sugestão de natureza precisa do NCM para separá-los. O NCM é só SUGESTÃO: o contador
confirma.

Os códigos são de 8 dígitos, sem pontos. Cada conjunto abaixo é uma decisão com origem:

- `NCM_COMBUSTIVEL`: a descrição oficial diz combustível (gasolina, gasóleo, fuel-oil, querosene de
  aviação, GLP e gás natural). Sugere a natureza de combustível pelo CFOP.
- `NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL`: álcool etílico e diesel com biodiesel. A descrição da
  NCM
  não diz "carburante". Só vale quando o CFOP é de "combustíveis ou lubrificantes" e o NCM não é de
  lubrificante: a única leitura é combustível (decisão do arquiteto). Com CFOP genérico, não conta
  como sinal de combustível.
- `NCM_LUBRIFICANTE`: óleos lubrificantes (2710.19.3) e preparações lubrificantes (3403). Ficam fora
  do 1,6%. Com CFOP de combustível, a sugestão é a revenda (8%), com aviso.

Biodiesel puro (B100, NCM 3826) não está em nenhum conjunto: fica fora do 1,6%, sem sugestão de
combustível (HI-139, hipótese para confirmação).
"""

from __future__ import annotations

import re

NCM_COMBUSTIVEL: frozenset[str] = frozenset(
    {
        "27101251",  # 2710.12.51, óleos leves, de aviação.
        "27101259",  # 2710.12.59, óleos leves, outras.
        "27101911",  # 2710.19.11, querosenes, de aviação.
        "27101919",  # 2710.19.19, querosenes, outros.
        "27101921",  # 2710.19.21, óleos combustíveis, gasóleo (óleo diesel).
        "27101922",  # 2710.19.22, óleos combustíveis, fuel-oil.
        "27101929",  # 2710.19.29, óleos combustíveis, outros.
        "27111100",  # 2711.11.00, gás natural, liquefeito.
        "27111910",  # 2711.19.10, gás liquefeito de petróleo (GLP).
        "27112100",  # 2711.21.00, gás natural, no estado gasoso.
    }
)

NCM_COMBUSTIVEL_SE_CFOP_DE_COMBUSTIVEL: frozenset[str] = frozenset(
    {
        "22071010",  # 2207.10.10, álcool etílico não desnaturado, teor de água até 1% vol.
        "22071090",  # 2207.10.90, álcool etílico não desnaturado, outros.
        "22072011",  # 2207.20.11, álcool etílico desnaturado, teor de água até 1% vol.
        "22072019",  # 2207.20.19, álcool etílico desnaturado, outros.
        "27102000",  # 2710.20.00, óleos de petróleo que contêm biodiesel (diesel B).
    }
)

NCM_LUBRIFICANTE: frozenset[str] = frozenset(
    {
        "27101931",  # 2710.19.31, óleos lubrificantes, sem aditivos.
        "27101932",  # 2710.19.32, óleos lubrificantes, com aditivos.
        "34031900",  # 3403.19.00, preparações lubrificantes que contêm óleos de petróleo, outras.
        "34039900",  # 3403.99.00, outras preparações lubrificantes, outras.
    }
)

_SO_DIGITOS = re.compile(r"\D")


def normalizar_ncm(texto: str | None) -> str:
    """NCM só com dígitos, para comparar com os conjuntos acima.

    O XML traz o NCM sem ponto, mas a normalização também aceita "2710.12.59". Vazio ou `None` vira
    "", que não está em conjunto nenhum: sem NCM, não há sinal.
    """
    return _SO_DIGITOS.sub("", texto or "")


def e_combustivel_pelo_ncm(ncm: str) -> bool:
    """O NCM é de combustível (lista positiva, sem o caso que depende do CFOP)."""
    return normalizar_ncm(ncm) in NCM_COMBUSTIVEL


def e_lubrificante(ncm: str) -> bool:
    return normalizar_ncm(ncm) in NCM_LUBRIFICANTE
