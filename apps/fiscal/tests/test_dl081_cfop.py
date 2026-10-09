"""DL-081 (frente A), tabela de CFOP como dado com fonte (item 1 da consulta de 09/10/2026).

Conferências: o CSV é o da planilha oficial, sem alteração (sha256 do arquivo); a devolução é a
coluna `indDevol` e não a faixa do CFOP; CFOP fora da tabela não recebe suposição.
"""

import hashlib

from apps.fiscal import cfop as tabela_cfop
from apps.fiscal.cfop import ARQUIVO_TABELA, cfop

# sha256 do CSV copiado sem alteração (escrito aqui à mão, na cópia de 09/10/2026).
SHA256_DO_CSV = "58e3b552e094a3223192b8fa817d398b7a9ff9e93cd8d43cc68eef6ab092476a"
# Planilha de origem, citada no cabeçalho de `apps/fiscal/cfop.py` e no plano DL-081.
SHA256_DA_PLANILHA_DE_ORIGEM = "577e05eec452294945d0e9df1f9bb9b21a4af115938e75ec74cf6a541ae4dacf"
TOTAL_DE_CODIGOS = 619


def test_csv_tem_o_sha256_registrado():
    """Se o arquivo mudar, o teste acusa: a tabela é dado com fonte, não texto editável."""
    digest = hashlib.sha256(ARQUIVO_TABELA.read_bytes()).hexdigest()
    assert digest == SHA256_DO_CSV


def test_csv_tem_619_codigos_e_nenhum_repetido():
    tabela = tabela_cfop._tabela()
    assert len(tabela) == TOTAL_DE_CODIGOS


def test_cabecalho_cita_fonte_data_sha_da_planilha_e_ressalva():
    """Fonte, data de 04/09/2026, sha256 da planilha e a ressalva do Convênio s/nº de 1970."""
    cabecalho = tabela_cfop.__doc__
    assert "Portal Nacional da NF-e" in cabecalho
    assert "04/09/2026" in cabecalho
    assert SHA256_DA_PLANILHA_DE_ORIGEM in cabecalho
    assert "Convênio s/nº de 1970 prevalece" in cabecalho


def test_codigo_com_e_sem_ponto_dao_o_mesmo_cfop():
    assert cfop("5929") is cfop("5.929")
    assert cfop("5929").codigo == "5.929"


def test_descricao_e_indicadores_de_um_cfop_comum():
    registro = cfop("5.102")
    assert registro.descricao.startswith("Venda de mercadoria adquirida ou recebida de terceiros")
    assert registro.ind_nfe is True
    assert registro.ind_devol is False


def test_vigencia_vem_da_tabela():
    registro = cfop("5.102")
    assert registro.vigencia_inicio.isoformat() == "2006-01-01"
    assert registro.vigencia_fim is None


def test_devolucao_e_a_coluna_indDevol_da_entrada_e_da_saida():
    """Devolução de venda na entrada (1.201, 1.202) tem indDevol 1."""
    assert cfop("1.201").ind_devol is True
    assert cfop("1.202").ind_devol is True


def test_devolucao_de_compra_em_saida_tambem_tem_indDevol_1():
    """5.202 é devolução de COMPRA (consulta, item 2). A regra decide pelo sentido da nota, não pelo
    indicador sozinho: em saída, indDevol 1 não vira devolução de venda (ver
    test_dl081_sugestao)."""
    assert cfop("5.202").ind_devol is True


def test_indDevol_nao_segue_a_faixa_do_cfop():
    """5.410 e 5.102 estão na mesma centena de venda, mas só o primeiro tem indDevol 1: a faixa
    não decide devolução (consulta, item 2)."""
    assert cfop("5.410").ind_devol is True
    assert cfop("5.102").ind_devol is False


def test_cfop_fora_da_tabela_e_none_nunca_suposicao():
    """Código bem formado mas inexistente na tabela: None (vira "a classificar")."""
    assert cfop("5.000") is None
    assert cfop("9.999") is None


def test_formato_invalido_e_none():
    for valor in ("", "abcd", "5.10", "51023", "0.102", None, 5102, "5.1O2"):
        assert cfop(valor) is None, valor


def test_registro_e_imutavel():
    """`Cfop` é dataclass congelada: a sugestão não pode alterar a descrição de um código."""
    registro = cfop("5.929")
    try:
        registro.descricao = "outra"
    except Exception as exc:  # FrozenInstanceError
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("o registro de CFOP devia ser imutável")
