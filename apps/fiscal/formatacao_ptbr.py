"""Formatação de valores monetários em pt-BR para TEXTO (avisos e telas) — DL-078 (auditoria A6).

Estas funções são as que `apps.fiscal.views_web` já usava (`_milhar_ptbr` e `_valor_ptbr`), movidas
para cá sem mudança de comportamento. Ficam fora de `views_web` porque o serviço de tomadas
(`apps.fiscal.tomadas`) compõe textos de aviso com valores, e um serviço não pode importar a
camada de tela: `views_web` importa o serviço, e a importação inversa seria circular.

Só APRESENTAÇÃO: nunca recebe `float` (AGENTS.md §10). Entrada e saída de valor continuam `Decimal`.
"""

from __future__ import annotations

from decimal import Decimal


def milhar_ptbr(parte_inteira):
    """Texto de inteiro com '.' de milhar, sinal de menos preservado."""
    negativo = parte_inteira.startswith("-")
    digitos = parte_inteira[1:] if negativo else parte_inteira
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    resultado = ".".join(grupos)
    return f"-{resultado}" if negativo else resultado


def valor_ptbr(valor):
    """`Decimal` -> texto pt-BR, sempre duas casas, '.' de milhar, ',' decimal.

    `None` vira "—" (ausência não é zero). Nunca recebe `float` (AGENTS.md §10): `v_serv`/`v_liq`
    chegam como `Decimal` desde `apps.fiscal.leitor` (DE-010) e permanecem assim até aqui.
    """
    if valor is None:
        return "—"
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    sinal, digitos, expoente = quantizado.as_tuple()
    texto_digitos = "".join(str(d) for d in digitos).rjust(3, "0")
    parte_inteira = texto_digitos[:-2] or "0"
    parte_decimal = texto_digitos[-2:]
    resultado = f"{milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if sinal else resultado
