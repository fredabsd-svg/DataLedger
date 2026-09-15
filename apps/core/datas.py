"""Módulo de data compartilhado (BL-133, auditoria DL-017 rodada 4, achado A9).

Espelha `apps.core.dinheiro`, e pelo mesmo motivo (DE-030, estendida a dado
tipado em geral — não só valor monetário, BL-135): nenhuma camada deve
interpretar texto de data por conta própria, e todo caminho de entrada usa
o MESMO julgador. Antes deste módulo existir, `apps.contabilidade.views`
tinha `_PADRAO_DATA_SIMPLES` — correto, mas PRIVADO daquele módulo — e
`apps.empresas.views` não tinha proteção nenhuma: `date.fromisoformat`
direto sobre `request.data`, sem checagem de tipo nem de formato. É o R3-3
inteiro (número JSON reinterpretado / 500) num campo de data:

    vigencia_inicio = "2026-W01-1"  -> 201, gravado 2025-12-29 (reinterpretado)
    vigencia_inicio = 20260101      -> 500 (TypeError: fromisoformat exige str)
    vigencia_inicio = "20260101"    -> 201, gravado 2026-01-01 (sem hífen, aceito)

A causa raiz é a mesma do R3-3: `date.fromisoformat` (como `Decimal()`) é
mais permissivo do que o contrato que o sistema anuncia — aceita formatos
fora do AAAA-MM-DD (data de semana ISO, por exemplo) e os reinterpreta em
silêncio, e não é `str`-safe (levanta `TypeError` para outros tipos, não
`ValueError`). Nunca usar `date.fromisoformat` direto sobre entrada de
cliente em código novo — é exatamente o que a recusa deste módulo torna
visível no ponto de entrada.
"""

import re
from datetime import date

# Formato ESTRITO aceito: exatamente quatro dígitos, hífen, dois dígitos,
# hífen, dois dígitos — `[0-9]`, nunca `\d` (R2-7/R3-6: `\d` casa qualquer
# dígito decimal Unicode, não só ASCII). Verificado ANTES de
# `date.fromisoformat`, pelo motivo explicado no docstring do módulo.
PADRAO_DATA_SIMPLES = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class DataInvalida(Exception):
    """Levantada quando um valor não pode entrar na cadeia como data.

    Cobre: tipo não suportado (não é `str` — inclui número JSON, `None`,
    `bool`), texto fora do formato AAAA-MM-DD estrito, e texto no formato
    certo mas que não corresponde a uma data real (`"2026-02-30"`).
    """


def para_data(valor):
    """Converte `valor` para `datetime.date`, com as recusas do contrato de data.

    Função pública, mesma razão de `apps.core.dinheiro.para_decimal`
    (docstring dela): mais de um caminho de entrada (contabilidade,
    empresas, e o que vier depois — DL-010 inclusive) precisa da MESMA
    normalização, em vez de reimplementá-la.

    Recusa, nesta ordem:

    1. `valor` que não seja `str` — um número JSON (`20260101`), `None` ou
       `bool` chegaria aqui sem ambiguidade de formato, mas também sem
       garantia nenhuma sobre o que o cliente pretendia (um `int` não tem
       hífen para indicar onde o ano termina). Aceitar reinterpretaria em
       silêncio; recusar é a mesma decisão que `para_decimal` toma para
       `float`.
    2. Texto fora do formato `PADRAO_DATA_SIMPLES` (AAAA-MM-DD estrito) —
       antes de `date.fromisoformat`, que aceita formatos fora do contrato
       anunciado (data de semana ISO, data sem separador, data com hora) e
       os reinterpreta em silêncio.
    3. Texto no formato certo mas que não é uma data válida (`"2026-02-30"`,
       `"2026-13-01"`) — `date.fromisoformat` ainda levanta `ValueError`
       aqui; convertido para `DataInvalida`, nunca deixado vazar cru.

    Aceita só `str` como entrada válida — ao contrário de `para_decimal`
    (que aceita `Decimal`/`int` além de `str`), não existe um tipo "data
    limpa" equivalente que um chamador Python de confiança precise passar
    direto: quem já tem um `date` não precisa desta função.
    """
    if not isinstance(valor, str):
        raise DataInvalida(
            f"Data deve ser enviada como texto no formato AAAA-MM-DD; "
            f"recebido tipo {type(valor).__name__} ({valor!r})."
        )
    if not PADRAO_DATA_SIMPLES.fullmatch(valor):
        raise DataInvalida(f"'{valor}' não é uma data no formato AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise DataInvalida(f"'{valor}' não é uma data válida.") from exc
