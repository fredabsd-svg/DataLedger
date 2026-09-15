"""Testes de `apps.core.escolhas` (BL-141, achado R5-2 da auditoria
DL-017 rodada 5 — o quarto irmão de `dinheiro.py`/`datas.py`/
`identificadores.py`)."""

import pytest

from apps.core.escolhas import EscolhaInvalida, para_escolha


def test_para_escolha_aceita_valor_exato():
    assert para_escolha("simples_nacional", ["simples_nacional", "lucro_real"], nome_campo="x") == (
        "simples_nacional"
    )


@pytest.mark.parametrize(
    "valor_invalido",
    [
        ["simples_nacional"],
        {"a": 1},
        1,
        True,
        None,
        "SIMPLES_NACIONAL",
        " simples_nacional ",
        "x" * 500,
        "",
    ],
)
def test_para_escolha_recusa_o_que_nao_e_uma_opcao_exata(valor_invalido):
    """Os sete casos medidos pelo auditor (mais None e string vazia, de
    controle): lista, dicionário, número, booleano, maiúsculas, espaço em
    volta e texto longo demais — todos fora do domínio, nenhum gravável."""
    with pytest.raises(EscolhaInvalida):
        para_escolha(
            valor_invalido,
            ["simples_nacional", "lucro_presumido", "lucro_real"],
            nome_campo="regime",
        )


def test_para_escolha_mensagem_cita_o_nome_do_campo_e_as_opcoes():
    with pytest.raises(EscolhaInvalida) as excinfo:
        para_escolha("x", ["a", "b"], nome_campo="regime")
    mensagem = str(excinfo.value)
    assert "regime" in mensagem
    assert "a" in mensagem and "b" in mensagem


def test_para_escolha_nao_normaliza_nunca_corrige_em_silencio():
    """Documenta a política deste módulo (a mesma do resto da família): um
    valor fora da grafia exata é RECUSADO, nunca normalizado. Se algum dia
    alguém "melhorar" isto para aceitar `.strip()`/`.lower()`, este teste
    tem que reprovar."""
    with pytest.raises(EscolhaInvalida):
        para_escolha("SIMPLES_NACIONAL", ["simples_nacional"], nome_campo="regime")
    with pytest.raises(EscolhaInvalida):
        para_escolha(" simples_nacional", ["simples_nacional"], nome_campo="regime")
