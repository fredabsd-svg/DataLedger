"""Módulo monetário compartilhado (DL-008, decisão DE-010).

Não existe política global de arredondamento no DataLedger: a legislação
brasileira exige métodos DIFERENTES por obrigação — o ICMS, em regra geral,
arredonda pela ABNT NBR 5891 (Convênio ICMS 85/2001, cláusula 27, X, "b");
combustíveis, EFD-Reinf, folha e eSocial truncam. O STJ já decidiu que
truncar o ICMS onde a norma manda arredondar caracteriza sonegação fiscal.
Por isso `quantizar` exige a política como argumento OBRIGATÓRIO, sem valor
por omissão: ninguém arredonda por acidente, e cada chamador declara, de
forma rastreável, qual regra está aplicando e por quê.

Este módulo é a BASE de engenharia monetária (representação, arredondamento,
contagem de escala). Ele não decide qual política se aplica a qual tributo —
isso é atribuição de cada motor de cálculo (fiscal, folha, honorários), com
base em requisito legal confirmado. Ver DE-010 em docs/projeto/decisoes.md
para as fontes e os limites desta decisão.

Nunca usa `float` internamente: toda a cadeia opera em `Decimal`.

Contexto decimal assumido: este módulo usa o contexto decimal PADRÃO do
processo (`decimal.getcontext()`), que no Python é `decimal.DefaultContext`
com 28 dígitos significativos de precisão — não alteramos esse contexto
aqui, porque mudar `decimal.getcontext()` globalmente afetaria toda a
aplicação, uma decisão maior do que este módulo tem escopo para tomar. Um
motor de cálculo que precise de mais dígitos (ou de um contexto isolado do
resto da aplicação) deve usar `decimal.localcontext()` na sua própria
chamada. Uma operação que exceda a precisão disponível levanta
`ValorMonetarioInvalido` (nunca deixa vazar `decimal.InvalidOperation` cru —
achado 3 da auditoria de 2026-09-12).

Limite documentado, não corrigível por este módulo: um `Decimal` construído
a partir de um `float` PELO CHAMADOR, antes de chegar aqui (`Decimal(0.5)`,
por exemplo), chega como um `Decimal` legítimo — não há como este módulo
distinguir isso de um `Decimal` "limpo", porque a informação de que ele veio
de um float não sobrevive à construção. Isso não é uma falha silenciosa
generalizada: a maioria dos floats que não são exatamente representáveis em
binário (por exemplo `Decimal(0.1)`) produz dezenas de casas decimais ao
converter, e a validação de escala de quem chama este módulo (como
`ESCALA_MAXIMA_LANCAMENTO_MANUAL` em `apps.contabilidade.services`) acaba
recusando esses valores por consequência — mas um float EXATAMENTE
representável em binário (`0.5`, `0.25`, `100.0`) gera um `Decimal` com
poucas casas e passaria sem ser detectado. A defesa real contra isso é nunca
construir `Decimal` a partir de `float` em código novo — é exatamente o que
a recusa de `float` neste módulo torna visível no ponto de entrada.
"""

import re
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import models


class PoliticaArredondamento(models.TextChoices):
    """Políticas de redução de casas decimais, nomeadas e amarradas a uma fonte.

    Não há política "padrão" nem "melhor" — cada uma corresponde a uma
    exigência normativa distinta (DE-010). Escolher a política errada não é
    um detalhe estético: o STJ trata truncar o ICMS como sonegação, e
    arredondar onde a norma manda truncar diverge do validador oficial
    (EFD-Reinf, eSocial).
    """

    # Meio para o par ("banker's rounding"), ABNT NBR 5891. Ex.: ICMS em
    # regra geral. Equivale exatamente a ROUND_HALF_EVEN do módulo `decimal`:
    # quando o dígito descartado é 5 seguido só de zeros, o resultado vai
    # para o algarismo par mais próximo (2,345 -> 2,34; o "4" já é par);
    # quando o 5 é seguido de qualquer algarismo diferente de zero, o valor
    # descartado é estritamente maior que a metade da unidade — não há
    # "meio" a resolver, e o resultado sempre sobe (2,3451 -> 2,35).
    ABNT_NBR_5891 = "abnt_nbr_5891"

    # ROUND_HALF_UP: no meio exato, sempre sobe. Só para regra que exija
    # explicitamente este comportamento — não é o método do ICMS.
    MEIO_PARA_CIMA = "meio_para_cima"

    # ROUND_DOWN: descarta as casas excedentes sem examinar seu valor, EM
    # DIREÇÃO A ZERO. Ex.: combustíveis, EFD-Reinf, folha e eSocial. Ver a
    # nota sobre negativos na docstring de `quantizar`.
    TRUNCAR = "truncar"


# Tradução de cada política nomeada para a constante de arredondamento do
# módulo `decimal` da biblioteca padrão. Fica como tabela, não como
# if/elif, para que adicionar uma política nova não exija tocar na lógica de
# `quantizar` — só declarar aqui a correspondência (e a fonte, no comentário
# da própria política acima).
_ARREDONDAMENTO = {
    PoliticaArredondamento.ABNT_NBR_5891: ROUND_HALF_EVEN,
    PoliticaArredondamento.MEIO_PARA_CIMA: ROUND_HALF_UP,
    PoliticaArredondamento.TRUNCAR: ROUND_DOWN,
}


# Formato aceito para `valor` recebido como TEXTO: sinal opcional, um ou mais
# dígitos, opcionalmente seguidos de ponto decimal e um ou mais dígitos.
# Deliberadamente mais estrito do que o construtor `Decimal`, que aceita
# espaços em volta, "_" como separador de dígitos (extensão do próprio
# Python, PEP 515) e notação científica: "1_000" convertido em silêncio para
# 1000 reinterpreta o que o cliente digitou, e "  100.00  " aceito em
# silêncio esconde um erro de origem (espaço colado por algum sistema
# upstream). Um sistema contábil não pode reinterpretar a entrada — RECUSAR
# é a resposta, igual à decisão já tomada para escala (DE-010). Aplica-se só
# a `str`; `int` não tem essa ambiguidade (não existe "int com espaço").
#
# `[0-9]`, não `\d` (achado R2-7 da auditoria DL-017, rodada 2): em Python,
# `\d` casa QUALQUER dígito decimal Unicode, não só ASCII — "０１０,00"
# (dígitos "fullwidth"), "١٢٣.٤٥" (índico-arábico) e "๑๐.00" (tailandês)
# passavam por esta regex, e `Decimal(str)` os aceita, convertendo em
# silêncio para o valor ASCII equivalente. O docstring deste módulo promete
# RECUSAR qualquer representação que não seja a declarada — o mesmo motivo
# já registrado, em comentário, para `_PADRAO_DATA_SIMPLES` e
# `_PADRAO_NIVEL_SIMPLES` em `apps.contabilidade.views`. `[0-9]` casa
# exclusivamente os dez dígitos ASCII.
PADRAO_VALOR_DECIMAL_SIMPLES = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?$")


class ValorMonetarioInvalido(Exception):
    """Levantado quando um valor não pode entrar na cadeia de cálculo monetário.

    Cobre: tipo não suportado (`float`, `bool`), texto fora do formato
    decimal simples aceito, valor não conversível para `Decimal`, valor não
    finito (`NaN`, `Infinity`, `-Infinity`), política de arredondamento
    desconhecida e `casas` inválida.
    """


def para_decimal(valor):
    """Converte `valor` para `Decimal`, com as recusas do contrato monetário.

    Função pública (não só uso interno deste módulo): outros pontos da
    aplicação que recebam valor monetário de origem não confiável — por
    exemplo `apps.contabilidade.services.criar_lancamento`, que pode ser
    chamado por código além da view HTTP — precisam da MESMA normalização,
    em vez de reimplementá-la (AGENTS.md §8, evitar duplicar regra).

    Recusa, nesta ordem:

    1. `bool`: embora seja subclasse de `int` em Python (`True == 1`,
       `False == 0`), aceitar um `bool` aqui confundiria silenciosamente uma
       marca verdadeiro/falso com um valor monetário. É o tipo errado para
       dinheiro, e o silêncio é pior que o erro (achado 6 da auditoria de
       2026-09-12).
    2. `float`: a representação binária de ponto flutuante não guarda
       exatamente a maioria dos valores decimais (0.1, por exemplo, é uma
       dízima em binário); ver a nota no docstring do módulo sobre o limite
       desta recusa quando o `Decimal` já chega pré-construído de um float.
    3. Texto (`str`) fora do formato decimal simples aceito (ver
       `PADRAO_VALOR_DECIMAL_SIMPLES`) — acha 7 da auditoria.
    4. Valor não conversível para `Decimal`.
    5. Valor não finito (`NaN`, `Infinity`, `-Infinity`).

    Aceita `Decimal`, `str` e `int` como entrada válida.
    """
    if isinstance(valor, bool):
        raise ValorMonetarioInvalido(
            f"Valor monetário não pode ser bool (recebido {valor!r}). Mesmo sendo "
            "tecnicamente um int em Python, um bool representa verdadeiro/falso, "
            "não uma quantia — aceitar silenciosamente confundiria as duas coisas."
        )
    if isinstance(valor, float):
        raise ValorMonetarioInvalido(
            f"Valor monetário não pode ser float (recebido {valor!r}). A "
            "representação binária de ponto flutuante não guarda exatamente "
            "a maioria dos valores decimais (por exemplo, 0.1 é uma dízima "
            "em binário); dois cálculos aritmeticamente equivalentes podem "
            "chegar a centavos diferentes conforme a ordem das operações. "
            "Use Decimal, ou str/int, que são convertidos para Decimal."
        )
    if isinstance(valor, Decimal):
        decimal_valor = valor
    elif isinstance(valor, (str, int)):
        if isinstance(valor, str) and not PADRAO_VALOR_DECIMAL_SIMPLES.fullmatch(valor):
            raise ValorMonetarioInvalido(
                f"Valor monetário em texto deve ser um número decimal simples "
                f"(sinal opcional, dígitos, ponto decimal opcional); recebido: "
                f"{valor!r}. Sem espaços, sem '_' como separador de dígitos e sem "
                "notação científica — o sistema não reinterpreta em silêncio o "
                "que foi digitado."
            )
        try:
            decimal_valor = Decimal(valor)
        except InvalidOperation as exc:
            raise ValorMonetarioInvalido(f"Valor monetário inválido: {valor!r}.") from exc
    else:
        raise ValorMonetarioInvalido(
            f"Tipo não suportado para valor monetário: {type(valor).__name__}."
        )

    if not decimal_valor.is_finite():
        # Cobre NaN, Infinity e -Infinity. Importante: `Decimal("Infinity")`
        # e `Decimal("NaN")` NÃO levantam `InvalidOperation` na conversão
        # acima — o parsing tem sucesso, o resultado só não é finito. É
        # exatamente o mecanismo do achado BL-44/N3 (entrada não finita
        # passando pelo `try/except` de conversão sem ser detectada) — por
        # isso esta checagem é separada e obrigatória. (Na prática, para
        # `str`, o padrão de formato acima já rejeita "NaN"/"Infinity" antes
        # de chegar aqui; esta checagem continua necessária para um
        # `Decimal` não finito passado diretamente por um chamador Python.)
        raise ValorMonetarioInvalido(
            f"Valor monetário deve ser finito; recebido: {decimal_valor!r}."
        )
    return decimal_valor


def quantizar(valor, *, casas, politica):
    """Reduz `valor` a `casas` decimais aplicando `politica`.

    `politica` é OBRIGATÓRIA e não tem valor por omissão (DE-010): chamar
    sem ela é erro de programação — o próprio Python levanta `TypeError`,
    por ser palavra-chave sem padrão — e isso é intencional. Ninguém deve
    arredondar por acidente usando uma política implícita.

    `casas` deve ser um `int` maior ou igual a zero. Sem esta validação,
    `casas` negativo quantiza em silêncio para dezenas/centenas/etc (achado
    3 da auditoria de 2026-09-12: `quantizar(Decimal("2.345"), casas=-2,
    ...)` devolveria `Decimal("0E+2")` sem avisar), e `casas` de tipo errado
    (`"2"`, `None`) levantaria um `TypeError` cru em vez do erro de contrato
    deste módulo.

    `valor` aceita `Decimal`, `str` ou `int` (convertidos via `Decimal`);
    `float` e `bool` são recusados, assim como `NaN` e infinitos (ver
    `para_decimal`).

    Comportamento de `TRUNCAR` com valores negativos: descarta as casas
    excedentes EM DIREÇÃO A ZERO (`ROUND_DOWN`), não em direção a menos
    infinito. Ou seja, truncar `-1,999` para 2 casas dá `-1,99`, não
    `-2,00` — é o comportamento do truncamento aritmético comum (e o do
    `ROUND_DOWN` do módulo `decimal` da biblioteca padrão). Uma regra que
    precisasse de "sempre para baixo em valor absoluto" (piso, não
    truncamento) exigiria outra política, que este módulo não oferece
    porque nenhuma regra confirmada em DE-010 pede isso — não inventamos
    política sem fonte.

    Levanta `ValorMonetarioInvalido` para valor inválido (tipo, NaN,
    infinito), `casas` inválida, política desconhecida, ou quando o
    resultado excede a precisão do contexto decimal disponível (ver a nota
    de contexto no docstring do módulo) — nunca deixa vazar
    `decimal.InvalidOperation` cru.
    """
    if not isinstance(casas, int) or isinstance(casas, bool) or casas < 0:
        raise ValorMonetarioInvalido(
            f"'casas' deve ser um número inteiro maior ou igual a zero; recebido: {casas!r}."
        )
    if politica not in _ARREDONDAMENTO:
        raise ValorMonetarioInvalido(f"Política de arredondamento desconhecida: {politica!r}.")

    decimal_valor = para_decimal(valor)
    # `Decimal(1).scaleb(-casas)` monta o quantum sem passar por string
    # formatada (ex.: casas=2 -> Decimal("0.01")), mantendo a cadeia
    # inteiramente em `Decimal`.
    quantum = Decimal(1).scaleb(-casas)
    try:
        return decimal_valor.quantize(quantum, rounding=_ARREDONDAMENTO[politica])
    except InvalidOperation as exc:
        # `Decimal.quantize` levanta `InvalidOperation` quando o resultado
        # exigiria mais dígitos do que a precisão do contexto decimal ativo
        # permite (padrão: 28 dígitos significativos) — por exemplo, um
        # valor de magnitude 1E+30 quantizado para 2 casas. Sem este
        # try/except, essa exceção do módulo `decimal` vazaria fora do
        # contrato anunciado por este módulo (que promete
        # `ValorMonetarioInvalido`), e um motor de cálculo que a receba sem
        # esperar viraria um 500 (achado 3 da auditoria de 2026-09-12).
        raise ValorMonetarioInvalido(
            f"Não foi possível representar {decimal_valor!r} com {casas} casa(s) "
            "decimal(is) dentro da precisão do contexto decimal disponível."
        ) from exc


def casas_decimais(valor):
    """Conta as casas decimais SIGNIFICATIVAS de `valor`, SEM arredondar.

    "Significativas" é a palavra que importa: `Decimal("100.000")` e
    `Decimal("100")` representam exatamente o MESMO valor monetário, sem
    nenhuma perda ao reduzir para 2 casas — o zero à direita não é precisão
    real, é só forma de escrever. Por isso a contagem NORMALIZA o valor
    antes de olhar o expoente (`Decimal.normalize()` remove zeros à direita
    sem alterar o valor numérico), e só então mede quantas casas restam.
    Sem essa normalização, um cliente que envia "100.000" onde outro envia
    "100" seria recusado por "3 casas decimais" mesmo sem ter, de fato, mais
    precisão do que "100" — um falso positivo, não uma violação real de
    escala. `Decimal("100.004")` continua com 3 casas depois de normalizar,
    porque o "4" final É informação real, que se perderia ao truncar para 2
    casas (o mecanismo exato do achado 4).

    A regra geral, que vale mais do que o caso específico: a checagem certa
    é "reduzir a escala perde informação?", não "quantos dígitos vieram
    escritos" — refinamento de DE-010 confirmado pelo arquiteto-senior em
    2026-09-12.

    A normalização também resolve notação científica pela mesma via:
    `Decimal("1E+2")` já normalizado tem expoente positivo (+2), ou seja,
    ZERO casas decimais — uma contagem baseada em
    `str(valor).split(".")` não veria ponto nenhum e uma contagem baseada em
    "tem E, deve ter decimais" erraria na direção contrária. Basear a
    contagem no expoente do `Decimal` normalizado evita as duas armadilhas.

    Aceita os mesmos tipos que `quantizar` (`Decimal`, `str`, `int`); recusa
    `float`, `bool` e valores não finitos pelo mesmo motivo (`para_decimal`).
    """
    decimal_valor = para_decimal(valor)
    expoente = decimal_valor.normalize().as_tuple().exponent
    if not isinstance(expoente, int):
        # Defesa redundante e documentada: `as_tuple().exponent` só assume
        # valores não inteiros ("n", "N", "F") para NaN e infinito, que
        # `para_decimal` já deveria ter recusado acima via `is_finite()`.
        raise ValorMonetarioInvalido(f"Valor monetário deve ser finito; recebido: {valor!r}.")
    return max(0, -expoente)
