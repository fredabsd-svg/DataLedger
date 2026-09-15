"""Testes do módulo monetário compartilhado (DL-008 / DE-010).

Não usam banco de dados: `PoliticaArredondamento`, `quantizar` e
`casas_decimais` são funções puras sobre `Decimal`. Cada teste referencia o
critério de aceite do plano DL-008 que cobre.
"""

from decimal import Decimal

import pytest

from apps.core.dinheiro import (
    PoliticaArredondamento,
    ValorMonetarioInvalido,
    casas_decimais,
    para_decimal,
    quantizar,
)


# Critério 1: `quantizar` sem `politica` falha (argumento obrigatório, sem
# valor por omissão — DE-010). É o próprio Python que recusa a chamada, por
# ser palavra-chave sem padrão: TypeError, não uma exceção de domínio.
def test_quantizar_sem_politica_e_erro_de_programacao():
    with pytest.raises(TypeError):
        quantizar(Decimal("1.005"), casas=2)  # falta a palavra-chave `politica`


# Critério 2: ABNT NBR 5891 (meio para o par) — 2,345 -> 2,34 (o "4" já é
# par, fica); 2,355 -> 2,36 (o "5" não é par, sobe).
def test_abnt_nbr_5891_manda_o_meio_exato_para_o_par():
    assert quantizar(
        Decimal("2.345"), casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891
    ) == Decimal("2.34")
    assert quantizar(
        Decimal("2.355"), casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891
    ) == Decimal("2.36")


# Critério 3: ABNT NBR 5891 — 5 seguido de algarismo diferente de zero sobe,
# porque o valor descartado já é estritamente maior que a metade (não há
# "meio" a resolver pela paridade).
def test_abnt_nbr_5891_sobe_quando_5_e_seguido_de_digito_diferente_de_zero():
    assert quantizar(
        Decimal("2.3451"), casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891
    ) == Decimal("2.35")


# Critério 4: MEIO_PARA_CIMA (ROUND_HALF_UP) — no meio exato, sempre sobe.
def test_meio_para_cima_sempre_sobe_no_meio_exato():
    assert quantizar(
        Decimal("2.345"), casas=2, politica=PoliticaArredondamento.MEIO_PARA_CIMA
    ) == Decimal("2.35")


# Critério 5: TRUNCAR (ROUND_DOWN) — descarta sem examinar o valor, e o
# comportamento com negativo é documentado e testado: em direção a ZERO.
def test_truncar_descarta_sem_examinar_o_valor():
    assert quantizar(Decimal("2.349"), casas=2, politica=PoliticaArredondamento.TRUNCAR) == Decimal(
        "2.34"
    )


def test_truncar_com_negativo_vai_em_direcao_a_zero_no_ao_infinito():
    # -1,999 truncado a 2 casas dá -1,99 (em direção a zero), NÃO -2,00 (que
    # seria a direção de menos infinito). Este é o comportamento documentado
    # de TRUNCAR/ROUND_DOWN neste módulo.
    assert quantizar(
        Decimal("-1.999"), casas=2, politica=PoliticaArredondamento.TRUNCAR
    ) == Decimal("-1.99")
    assert quantizar(
        Decimal("-2.995"), casas=2, politica=PoliticaArredondamento.TRUNCAR
    ) == Decimal("-2.99")


# Critério 6: `quantizar` recusa float, com mensagem explicativa (a razão
# precisa aparecer no texto do erro, não só o fato de ter sido recusado).
def test_quantizar_recusa_float_com_mensagem_explicativa():
    with pytest.raises(ValorMonetarioInvalido) as excinfo:
        quantizar(2.345, casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)
    mensagem = str(excinfo.value).lower()
    assert "float" in mensagem
    assert "binári" in mensagem or "binary" in mensagem  # explica o PORQUÊ, não só recusa


# Critério 7: `quantizar` recusa NaN e infinitos.
@pytest.mark.parametrize("valor", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_quantizar_recusa_nan_e_infinitos(valor):
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(valor, casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)


def test_quantizar_recusa_string_nao_finita():
    # Mesmo cenário do achado BL-44/N3, mas na entrada direta do módulo:
    # `Decimal("Infinity")` não levanta `InvalidOperation` ao converter uma
    # string — o parsing tem sucesso, e é preciso checar `is_finite()`.
    with pytest.raises(ValorMonetarioInvalido):
        quantizar("Infinity", casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)
    with pytest.raises(ValorMonetarioInvalido):
        quantizar("NaN", casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)


def test_quantizar_recusa_politica_desconhecida():
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(Decimal("2.345"), casas=2, politica="metade_para_lua")


def test_quantizar_aceita_str_e_int():
    assert quantizar("2.345", casas=2, politica=PoliticaArredondamento.MEIO_PARA_CIMA) == Decimal(
        "2.35"
    )
    assert quantizar(100, casas=2, politica=PoliticaArredondamento.TRUNCAR) == Decimal("100.00")


# `casas_decimais`: conta escala SIGNIFICATIVA, sem arredondar e sem passar
# por texto. Zero à direita não é precisão real (100.00 é exatamente igual a
# 100), então não conta como casa decimal — só o dígito significativo conta.
def test_casas_decimais_conta_sem_arredondar():
    assert casas_decimais(Decimal("2.3451")) == 4
    assert casas_decimais(Decimal("100")) == 0
    assert casas_decimais(Decimal("0")) == 0


def test_casas_decimais_zero_a_direita_nao_conta_como_escala():
    # 100.000, 100.00 e 100 representam exatamente o MESMO valor monetário —
    # nenhuma casa a mais é perdida ao reduzir para 2 (ou até para 0) casas.
    # Sem esta normalização, um cliente que escreve o valor com mais zeros à
    # direita do que outro seria recusado por "escala maior" sem ter, de
    # fato, mais precisão nenhuma — um falso positivo, diferente do achado 4
    # (onde o dígito final de 100,004 É informação real).
    assert casas_decimais(Decimal("100.000")) == 0
    assert casas_decimais(Decimal("100.00")) == 0
    assert casas_decimais(Decimal("0.00")) == 0
    assert casas_decimais(Decimal("2.30")) == 1  # o zero à direita não conta; só o "3"


def test_casas_decimais_notacao_cientifica_nao_confunde_a_contagem():
    # Decimal("1E+2") vale 100, com expoente POSITIVO: zero casas decimais,
    # apesar de a string conter "E" — uma contagem baseada em texto poderia
    # errar aqui.
    assert casas_decimais(Decimal("1E+2")) == 0
    # Decimal("1.5E+1") vale 15 (dígitos "15", expoente 0): zero casas.
    assert casas_decimais(Decimal("1.5E+1")) == 0


def test_casas_decimais_aceita_str_e_int():
    assert casas_decimais("2.345") == 3
    assert casas_decimais(100) == 0


def test_casas_decimais_recusa_float():
    with pytest.raises(ValorMonetarioInvalido):
        casas_decimais(2.30)


@pytest.mark.parametrize("valor", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_casas_decimais_recusa_nan_e_infinitos(valor):
    with pytest.raises(ValorMonetarioInvalido):
        casas_decimais(valor)


# ---------------------------------------------------------------------------
# Achados da auditoria de 2026-09-12 (aprovação com ressalvas da DL-008)
# ---------------------------------------------------------------------------


# Achado 3 (MÉDIA, obrigatório): o contrato do módulo vazava
# `decimal.InvalidOperation` cru em vez de `ValorMonetarioInvalido` quando o
# resultado excede a precisão do contexto decimal disponível — e não
# validava `casas` (negativo quantizava em silêncio; tipo errado dava
# `TypeError` cru). Este módulo é a base dos motores fiscais futuros: uma
# exceção fora do contrato anunciado viraria 500 num motor que a receba sem
# esperar.
def test_quantizar_recusa_valor_que_excede_a_precisao_do_contexto():
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(Decimal("1E+30"), casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)


def test_quantizar_recusa_casas_que_excede_a_precisao_do_contexto():
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(Decimal("2.345"), casas=50, politica=PoliticaArredondamento.ABNT_NBR_5891)


def test_quantizar_recusa_casas_negativa():
    # Sem esta validação, `casas=-2` quantizava em silêncio para centenas
    # (`Decimal("2.345")` -> `Decimal("0E+2")`) — comportamento correto do
    # `decimal.quantize`, mas fora do contrato deste módulo, que só promete
    # REDUZIR a `casas` decimais (um número de casas negativo não é uma
    # "quantidade de casas decimais").
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(Decimal("2.345"), casas=-2, politica=PoliticaArredondamento.ABNT_NBR_5891)


@pytest.mark.parametrize("casas_invalida", ["2", None, 2.0])
def test_quantizar_recusa_casas_de_tipo_errado(casas_invalida):
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(Decimal("2.345"), casas=casas_invalida, politica=PoliticaArredondamento.TRUNCAR)


# Achado 6 (BAIXA, obrigatório): `bool` é subclasse de `int` em Python
# (`True == 1`, `False == 0`); sem recusa explícita, `para_decimal` (usado
# por `quantizar` e `casas_decimais`) aceitaria `True`/`False` como se
# fossem 1/0, confundindo em silêncio uma marca verdadeiro/falso com um
# valor monetário.
@pytest.mark.parametrize("valor_bool", [True, False])
def test_para_decimal_recusa_bool_explicitamente(valor_bool):
    with pytest.raises(ValorMonetarioInvalido) as excinfo:
        para_decimal(valor_bool)
    assert "bool" in str(excinfo.value).lower()


@pytest.mark.parametrize("valor_bool", [True, False])
def test_quantizar_recusa_bool_explicitamente(valor_bool):
    with pytest.raises(ValorMonetarioInvalido):
        quantizar(valor_bool, casas=2, politica=PoliticaArredondamento.ABNT_NBR_5891)


# Achado 7 (BAIXA, obrigatório): o construtor `Decimal` aceita "_" como
# separador de dígitos (PEP 515) e espaços em volta do número, reinterpretando
# em silêncio o que foi digitado — "1_000" vira 1000, "  100.00  " vira
# 100.00. Um sistema contábil não pode fazer isso silenciosamente; o formato
# aceito é só sinal opcional + dígitos + ponto decimal opcional.
@pytest.mark.parametrize(
    "texto_reinterpretado",
    ["1_000", "  100.00  ", "100.00 ", " 100.00", "1e2", "+_1", "100_00.00"],
)
def test_para_decimal_recusa_texto_fora_do_formato_simples(texto_reinterpretado):
    with pytest.raises(ValorMonetarioInvalido):
        para_decimal(texto_reinterpretado)


def test_para_decimal_aceita_formato_simples_com_sinal():
    assert para_decimal("100.00") == Decimal("100.00")
    assert para_decimal("+100.00") == Decimal("100.00")
    assert para_decimal("-100.00") == Decimal("-100.00")
    assert para_decimal("100") == Decimal("100")


# R2-7 (achado da auditoria DL-017, rodada 2, MÉDIA): `\d` do Python casa
# QUALQUER dígito decimal Unicode, não só ASCII 0-9. Os quatro textos abaixo
# são os medidos pelo auditor — cada um usa uma família de dígito diferente
# (fullwidth, fullwidth misturado com ASCII, índico-arábico, tailandês) para
# provar que a recusa vale para dígito Unicode em geral, não só um script
# específico. O docstring do módulo promete RECUSAR qualquer representação
# que não seja a declarada; antes da correção, `para_decimal` convertia
# estes textos em silêncio para o valor ASCII equivalente (`Decimal` aceita
# dígito Unicode nativamente).
@pytest.mark.parametrize(
    "texto_digito_unicode",
    [
        "０１０.00",  # dígitos "fullwidth" (formulário japonês/chinês de largura total)
        "10.0０",  # fullwidth misturado com ASCII, só no último dígito
        "١٢٣.٤٥",  # dígitos índico-arábicos (usados em árabe)
        "๑๐.00",  # dígitos tailandeses
    ],
)
def test_para_decimal_recusa_digito_unicode_nao_latino(texto_digito_unicode):
    with pytest.raises(ValorMonetarioInvalido):
        para_decimal(texto_digito_unicode)


def test_para_decimal_continua_aceitando_apenas_digitos_ascii():
    """Controle positivo da correção do R2-7: dígitos ASCII (0-9) continuam
    sendo o único formato aceito — a correção (`\\d` -> `[0-9]`) não pode
    ter deixado de aceitar nenhum texto que já era válido."""
    assert para_decimal("0123456789.99") == Decimal("123456789.99")
