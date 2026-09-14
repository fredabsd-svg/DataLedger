"""Módulo de identificador numérico compartilhado (BL-127, auditoria DL-017
rodada 4, achado A2 — e o gêmeo em `apps.tenancy.views.EscritorioAtivoView.
post`, encontrado durante a mesma correção, mesma classe).

Espelha `apps.core.dinheiro`/`apps.core.datas`, pelo mesmo motivo (DE-030,
estendida a dado tipado): nenhuma camada deve interpretar um identificador
de cliente por conta própria.

O defeito original: `apps/tenancy/views.py` (`ativar_escritorio`) validava
`escritorio_id` com `str(escritorio_id).isdigit()` e só então chamava
`int(escritorio_id)`. O comentário que justificava a escolha dizia
explicitamente que evitava depender de `try/except` sobre `int()` — e é
exatamente essa escolha que causa o defeito:

1. `"9" * 6000` passa em `.isdigit()` (são só dígitos ASCII), mas
   `int("9" * 6000)` levanta `ValueError` — o limite de conversão
   string→int do próprio Python (`sys.int_max_str_digits`, 4300 por
   padrão) — sem `try/except`, 500 cru.
2. `.isdigit()` também aceita dígito Unicode não-ASCII (`"２"`.isdigit()`
   é `True`), e `int("２")` funciona e devolve `2` — reinterpretação
   silenciosa, mesma classe do R2-7/R3-6, só que sem `[0-9]` explícito.

Este módulo resolve as DUAS direções que um identificador pode chegar —
texto (formulário HTML, querystring) e número JSON (API) — com o mesmo
julgador, nunca reimplementado em cada view.
"""

import re

# Identificador numérico ASCII estrito: sem sinal, sem espaço, sem "_" como
# separador, comprimento limitado a 19 dígitos — o maior `BigAutoField`
# (BIGINT do Postgres, `DEFAULT_AUTO_FIELD` deste projeto) cabe em
# 9223372036854775807, 19 dígitos. Um identificador de banco legítimo
# NUNCA precisa de mais dígitos que isso; limitar aqui evita depender do
# limite de conversão string→int do interpretador (`sys.
# int_max_str_digits`) como única defesa. `[0-9]`, não `\d` (R2-7/R3-6):
# `\d` casaria qualquer dígito decimal Unicode.
PADRAO_ID_SIMPLES = re.compile(r"^[0-9]{1,19}$")


class IdentificadorInvalido(Exception):
    """Levantada quando um valor não pode entrar na cadeia como identificador.

    Cobre: tipo não suportado (`float`, `bool`, `None`, lista/dict), texto
    fora do formato ASCII estrito, e número (inteiro Python) grande demais
    para converter para texto sem estourar o limite do interpretador.
    """


def para_id(valor):
    """Converte `valor` (texto ou `int`) para um identificador inteiro positivo.

    Aceita as DUAS formas legítimas de um identificador chegar a uma view:
    texto (formulário HTML, querystring — sempre `str`) e número JSON (a
    API DRF decodifica um número JSON sem aspas como `int` do Python, não
    como `str`). Um `int` do Python não tem o mesmo problema de precisão
    que `float` (arbitrário, exato) — por isso, ao contrário de
    `para_decimal`, este módulo ACEITA `int` sem recusar, mas ainda impõe o
    mesmo teto de magnitude, porque um `int` gigante (milhares de dígitos)
    também pode estourar o limite de conversão do interpretador ao virar
    texto para comparação com o banco.

    Recusa, nesta ordem:

    1. `bool`: subclasse de `int` em Python — mesmo motivo de
       `para_decimal` recusá-lo (não é um identificador, é uma marca
       verdadeiro/falso).
    2. Qualquer tipo que não seja `str` nem `int`.
    3. `int` cuja representação em texto excede o limite de conversão do
       interpretador (`sys.int_max_str_digits`) — capturado explicitamente,
       nunca deixado vazar como `ValueError` cru.
    4. Texto (de entrada `str`, ou já convertido de um `int` grande) fora
       do formato `PADRAO_ID_SIMPLES` — sem sinal, só dígitos ASCII,
       1 a 19 caracteres.
    """
    if isinstance(valor, bool):
        raise IdentificadorInvalido(f"Identificador não pode ser bool (recebido {valor!r}).")
    if isinstance(valor, int):
        try:
            texto = str(valor)
        except ValueError as exc:
            # `str()` sobre um `int` com mais dígitos do que o
            # interpretador aceita converter levanta `ValueError` — mesma
            # defesa que a checagem de comprimento abaixo dá ao caminho de
            # texto, só que a origem aqui é um número já grande demais
            # ANTES de virar texto.
            raise IdentificadorInvalido("Identificador numérico grande demais.") from exc
    elif isinstance(valor, str):
        texto = valor
    else:
        raise IdentificadorInvalido(
            f"Identificador deve ser texto ou número inteiro; recebido tipo {type(valor).__name__}."
        )

    if not PADRAO_ID_SIMPLES.fullmatch(texto):
        raise IdentificadorInvalido(f"{valor!r} não é um identificador numérico válido.")
    return int(texto)
