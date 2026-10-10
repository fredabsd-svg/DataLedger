"""DL-082, correção da rodada 1 (A2, A3 e A5): regras de CFOP contra a tabela oficial.

Os códigos esperados são escritos à mão. Para conferir contra a fonte, o CSV oficial
(`dados/cfop_it2023002_v210.csv`) é lido aqui com o `csv` do Python, de forma independente da
`cfop.py`. Assim o teste não repete a implementação: ele confere a implementação contra o arquivo.
"""

import csv
from pathlib import Path

import pytest

from apps.fiscal import cfop as tabela_cfop
from apps.fiscal.models import (
    ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA,
    ANEXO_I,
    ANEXO_II,
    MercadoReceita,
    NaturezaOperacaoNFe,
    e_devolucao_de_exportacao,
    mercado_do_item_nfe,
)

ARQUIVO_CSV = Path(tabela_cfop.ARQUIVO_TABELA)


def _linhas_do_csv():
    with ARQUIVO_CSV.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


CODIGOS_DO_CSV = [linha["codigo"] for linha in _linhas_do_csv()]


# ---------------------------------------------------------------------------
# A2: devolução de VENDA de combustível ou lubrificante
# ---------------------------------------------------------------------------

# Escrito à mão, da descrição oficial: "Devolução de venda de combustíveis ou lubrificantes".
DEVOLUCAO_DE_VENDA_DE_COMBUSTIVEL_A_MANO = {
    "1.660",
    "1.661",
    "1.662",
    "2.660",
    "2.661",
    "2.662",
}


def test_devolucao_de_venda_de_combustivel_bate_com_o_csv_oficial():
    """Lido do CSV: as descrições que começam por "Devolução de venda de combustíveis" (com indDevol
    1). Confere com a lista escrita à mão e com a função."""
    do_csv = {
        linha["codigo"]
        for linha in _linhas_do_csv()
        if linha["descricao"].startswith("Devolução de venda de combustíveis ou lubrificantes")
        and linha["indDevol"] == "1"
    }
    assert do_csv == DEVOLUCAO_DE_VENDA_DE_COMBUSTIVEL_A_MANO
    for codigo in CODIGOS_DO_CSV:
        esperado = codigo in DEVOLUCAO_DE_VENDA_DE_COMBUSTIVEL_A_MANO
        assert tabela_cfop.e_devolucao_de_venda_de_combustivel(codigo) is esperado, codigo


@pytest.mark.parametrize("codigo", ["5660", "5661", "5662", "6660", "6661", "6662"])
def test_devolucao_de_compra_de_combustivel_nao_entra_na_recusa_de_venda(codigo):
    """A recusa do A2 é só de VENDA. A devolução de compra (5.66x, 6.66x) é outro fato: a decisão
    não a incluiu, e a função mais larga (`e_devolucao_de_combustivel`) fica como está."""
    assert tabela_cfop.e_devolucao_de_venda_de_combustivel(codigo) is False


@pytest.mark.parametrize("codigo", ["1661", "1.661", "2662"])
def test_devolucao_de_venda_de_combustivel_aceita_com_ou_sem_ponto(codigo):
    assert tabela_cfop.e_devolucao_de_venda_de_combustivel(codigo) is True


# ---------------------------------------------------------------------------
# A5: prestação de serviço de comunicação ou de transporte
# ---------------------------------------------------------------------------

# Escrito à mão, da descrição oficial "Prestação de serviço de comunicação" ou "... de transporte":
# comunicação 5.301 a 5.307, 6.301 a 6.307 e 7.301; transporte 5.351 a 5.357, 5.359, 5.360, 5.932,
# 6.351 a 6.357, 6.359, 6.360, 6.932 e 7.358. O 5.932 e o 6.932 são transporte iniciado em outra UF,
# fora da faixa 5.351 a 5.360, e entram pela descrição.
PRESTACAO_COMUNICACAO_OU_TRANSPORTE_A_MANO = {
    "5.301",
    "5.302",
    "5.303",
    "5.304",
    "5.305",
    "5.306",
    "5.307",
    "6.301",
    "6.302",
    "6.303",
    "6.304",
    "6.305",
    "6.306",
    "6.307",
    "7.301",
    "5.351",
    "5.352",
    "5.353",
    "5.354",
    "5.355",
    "5.356",
    "5.357",
    "5.359",
    "5.360",
    "5.932",
    "6.351",
    "6.352",
    "6.353",
    "6.354",
    "6.355",
    "6.356",
    "6.357",
    "6.359",
    "6.360",
    "6.932",
    "7.358",
}


def test_prestacao_de_comunicacao_ou_transporte_bate_com_o_csv_oficial():
    do_csv = {
        linha["codigo"]
        for linha in _linhas_do_csv()
        if linha["descricao"].startswith(
            ("Prestação de serviço de comunicação", "Prestação de serviço de transporte")
        )
    }
    assert do_csv == PRESTACAO_COMUNICACAO_OU_TRANSPORTE_A_MANO
    for codigo in CODIGOS_DO_CSV:
        esperado = codigo in PRESTACAO_COMUNICACAO_OU_TRANSPORTE_A_MANO
        assert tabela_cfop.e_prestacao_de_comunicacao_ou_transporte(codigo) is esperado, codigo


@pytest.mark.parametrize(
    "codigo",
    [
        "1.353",  # aquisição de transporte: entrada, não prestação
        "2.301",  # aquisição de comunicação
        "5.931",  # lançamento (indTransp 1, mas não é prestação)
        "5.933",  # serviço sujeito ao ISSQN: é a NF-e conjugada, outro caminho
        "5.101",  # venda de produção
        "5.102",  # venda de mercadoria de terceiros
    ],
)
def test_cfop_que_nao_e_prestacao_de_comunicacao_ou_transporte(codigo):
    assert tabela_cfop.e_prestacao_de_comunicacao_ou_transporte(codigo) is False


def test_cfop_fora_da_tabela_nao_e_prestacao():
    assert tabela_cfop.e_prestacao_de_comunicacao_ou_transporte("9.999") is False


# ---------------------------------------------------------------------------
# A3: devolução de exportação de ENTRADA (1.503 a 1.506 e 2.503 a 2.506)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cfop", "esperado"),
    [
        ("3202", True),  # 3.xxx: sempre exportação (regra da DL-081, A8)
        ("3503", True),
        ("1503", True),
        ("1504", True),
        ("1505", False),  # reconferência, R4: devolução de remessa para lote, não de venda
        ("1506", False),
        ("2503", True),
        ("2504", True),
        ("2505", False),
        ("2506", False),
        ("1.503", True),  # com ponto
        ("1501", False),
        ("1661", False),  # devolução de combustível, interna
        ("1202", False),
        (
            "5503",
            False,
        ),  # saída: devolução de mercadoria recebida para exportação; fora deste corte
    ],
)
def test_devolucao_de_exportacao(cfop, esperado):
    assert e_devolucao_de_exportacao(cfop) is esperado


def test_anexo_da_devolucao_de_exportacao_segue_a_descricao_oficial():
    """Escrito à mão. 1.503 é de produção do estabelecimento (Anexo II); 1.504 é de mercadoria
    adquirida de terceiros (Anexo I). Os 2.50x valem o mesmo. Os x.505 e x.506 saíram na
    reconferência (R4): devolvem remessa para formação de lote, não venda."""
    assert ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA == {
        "1.503": ANEXO_II,
        "1.504": ANEXO_I,
        "2.503": ANEXO_II,
        "2.504": ANEXO_I,
    }
    descricoes = {linha["codigo"]: linha["descricao"] for linha in _linhas_do_csv()}
    for codigo, anexo in ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA.items():
        texto = descricoes[codigo]
        if anexo == ANEXO_II:
            assert "produção do estabelecimento" in texto or "produzidos pelo próprio" in texto
        else:
            assert "adquirida ou recebida de terceiros" in texto or (
                "adquiridas ou recebidas de terceiros" in texto
            ), codigo


@pytest.mark.parametrize("cfop", ["1503", "1504", "2503", "2504", "3202"])
def test_mercado_da_devolucao_de_exportacao_e_externo(cfop):
    assert mercado_do_item_nfe(NaturezaOperacaoNFe.DEVOLUCAO_VENDA, cfop) == MercadoReceita.EXTERNO


def test_mercado_da_devolucao_comum_continua_interno_e_da_venda_de_exportacao_tambem():
    assert (
        mercado_do_item_nfe(NaturezaOperacaoNFe.DEVOLUCAO_VENDA, "1202") == MercadoReceita.INTERNO
    )
    assert mercado_do_item_nfe(NaturezaOperacaoNFe.REVENDA, "1503") == MercadoReceita.INTERNO
