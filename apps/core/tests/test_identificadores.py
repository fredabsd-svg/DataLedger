"""Testes de `apps.core.identificadores` (BL-127, achado A2 da auditoria
DL-017 rodada 4 — módulo compartilhado que fecha o defeito nas duas views
de `apps.tenancy.views` que usam identificador de escritório).
"""

import pytest

from apps.core.identificadores import IdentificadorInvalido, para_id


def test_para_id_aceita_texto_numerico_simples():
    assert para_id("42") == 42
    assert para_id("1") == 1


def test_para_id_aceita_int_diretamente():
    assert para_id(42) == 42


@pytest.mark.parametrize("valor_bool", [True, False])
def test_para_id_recusa_bool_explicitamente(valor_bool):
    """`bool` é subclasse de `int` em Python — mesma recusa que
    `apps.core.dinheiro.para_decimal` já aplica, e pelo mesmo motivo: não
    confundir uma marca verdadeiro/falso com um identificador."""
    with pytest.raises(IdentificadorInvalido) as excinfo:
        para_id(valor_bool)
    assert "bool" in str(excinfo.value).lower()


def test_para_id_recusa_texto_com_milhares_de_digitos():
    """O defeito original (A2): `"9" * 6000` passava em `.isdigit()`, e só
    `int()` estourava com `ValueError` cru. `para_id` recusa ANTES de
    qualquer conversão, pelo comprimento."""
    with pytest.raises(IdentificadorInvalido):
        para_id("9" * 6000)


def test_para_id_recusa_int_com_milhares_de_digitos():
    """A mesma classe, pela outra porta: um `int` do Python já gigante —
    `str()` sobre ele também estoura o limite de conversão do
    interpretador, e `para_id` captura isso.

    Construído por potenciação (`2**20000`), não por `int("9" * 6000)`: a
    conversão texto->int TAMBÉM está sujeita ao mesmo limite do
    interpretador, então um literal de 6000 dígitos nem chega a virar `int`
    por esse caminho — é exatamente por isso que, na porta HTTP real, um
    número JSON deste tamanho nunca chega à view (falha ANTES, ao
    decodificar o JSON — ver `test_api_escritorio_ativo_post_com_json_
    numero_gigante_ja_e_recusado_pelo_parser_json` em
    apps/tenancy/tests/test_views.py). Este teste cobre o `int` já
    construído por outro caminho (aritmética, não texto) — o único jeito
    de um Python `int` gigante chegar até aqui sem passar por conversão de
    texto.
    """
    with pytest.raises(IdentificadorInvalido):
        para_id(2**20000)


@pytest.mark.parametrize("digito_unicode", ["２", "٢", "๒"])
def test_para_id_recusa_digito_unicode_nao_ascii(digito_unicode):
    """`"２".isdigit()` é `True` e `int("２")` devolve `2` — a
    reinterpretação silenciosa que motivou a correção. `para_id` usa
    `[0-9]`, não `\\d` nem `.isdigit()` (mesma lição do R2-7/R3-6)."""
    with pytest.raises(IdentificadorInvalido):
        para_id(digito_unicode)


@pytest.mark.parametrize("valor_invalido", ["", "abc", "-1", "1.5", " 1", "1 ", "1_000"])
def test_para_id_recusa_formatos_invalidos(valor_invalido):
    with pytest.raises(IdentificadorInvalido):
        para_id(valor_invalido)


@pytest.mark.parametrize("valor_tipo_errado", [None, 1.5, [1], {"id": 1}])
def test_para_id_recusa_tipos_nao_suportados(valor_tipo_errado):
    with pytest.raises(IdentificadorInvalido):
        para_id(valor_tipo_errado)


def test_para_id_aceita_maior_bigint_valido():
    """Controle de limite: o maior valor que cabe num BigAutoField
    (BIGINT do Postgres, `DEFAULT_AUTO_FIELD` deste projeto) continua
    sendo aceito — a correção não pode ter apertado o caso real."""
    maior_bigint = 9223372036854775807  # 2**63 - 1, 19 dígitos
    assert para_id(str(maior_bigint)) == maior_bigint
    assert para_id(maior_bigint) == maior_bigint


def test_para_id_recusa_vinte_digitos():
    """Um dígito a mais que o maior BigAutoField — já não é um
    identificador plausível deste projeto."""
    with pytest.raises(IdentificadorInvalido):
        para_id("1" * 20)
