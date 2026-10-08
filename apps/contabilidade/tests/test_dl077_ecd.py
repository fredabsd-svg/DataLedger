"""DL-077, fatia 1 (critério 1 e critério 8): leitor e escritor do I050/I051 da ECD.

Os arquivos destas provas são MONTADOS À MÃO, linha a linha, a partir do leiaute
9 (Manual de Orientação do Leiaute 9 da ECD, ADE Cofis nº 01/2026): não passam pelo
escritor, para o teste não ser circular. Dados sintéticos. A página citada em cada
asserção é a impressa no rodapé do manual.
"""

from datetime import date

import pytest

from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
)
from apps.contabilidade.intercambio.formatos import ecd


def _arquivo(*linhas, fim_de_linha="\r\n"):
    """Monta bytes ISO-8859-1 com CRLF (p. 52)."""
    return (fim_de_linha.join(linhas) + fim_de_linha).encode("iso-8859-1")


def _erros(resultado):
    return {(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO}


def _mensagens_de_erro(resultado):
    return [o.mensagem for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]


def _conta(codigo, contas):
    return next(c for c in contas if c.codigo == codigo)


# -----------------------------------------------------------------------------
# Leitura: o caso feliz, do próprio manual
# -----------------------------------------------------------------------------


def test_le_os_exemplos_de_i050_do_manual_sem_erro():
    """Exemplos das pp. 121-122 do manual: hierarquia de 4 níveis, com conta analítica."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|1|1||Ativo Sintética 1|",
            "|I050|01012023|01|S|2|1.1|1|Ativo Sintética 2|",
            "|I050|01012023|01|S|3|1.1.1|1.1|Ativo Sintética 3|",
            "|I050|01012023|01|A|4|1.1.1.1|1.1.1|Ativo Analítica 1|",
            "|I050|01012023|01|A|4|1.1.1.2|1.1.1|Ativo Analítica 2|",
        )
    )

    assert not resultado.tem_erro, resultado.ocorrencias
    assert [c.codigo for c in resultado.contas] == ["1", "1.1", "1.1.1", "1.1.1.1", "1.1.1.2"]
    analitica = _conta("1.1.1.1", resultado.contas)
    assert analitica.codigo_pai == "1.1.1"
    assert analitica.analitica is True
    assert analitica.tipo == "ativo"
    # HI-88: a ECD não traz natureza. O leitor não inventa uma.
    assert analitica.natureza is None
    assert analitica.codigo_origem is None
    assert _conta("1", resultado.contas).codigo_pai is None
    assert resultado.codificacao == "iso-8859-1"


def test_i051_de_conta_analitica_vira_referencial_da_conta():
    """I051 (pp. 123-124): `|I051||11100009|` ligado ao I050 analítico acima."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|1|1||Ativo|",
            "|I050|01012023|01|S|2|1.1|1|Ativo Circulante|",
            "|I050|01012023|01|S|3|1.1.1|1.1|Disponível|",
            "|I050|01012023|01|A|4|1.1.1.1|1.1.1|Caixa|",
            "|I051||11100009|",
        )
    )

    assert not resultado.tem_erro, resultado.ocorrencias
    assert _conta("1.1.1.1", resultado.contas).referencial == "11100009"
    assert _conta("1.1.1", resultado.contas).referencial is None


def test_codificacao_iso_8859_1_le_acento_certo():
    """p. 52: o arquivo é ISO-8859-1. 'ç' e 'ã' são os bytes 0xE7 e 0xE3."""
    bruto = "|I050|01012023|01|A|1|1||Caixa geral ção|".encode("iso-8859-1")
    assert b"\xe7\xe3o" in bruto

    resultado = ecd.ler(bruto + b"\r\n")

    assert resultado.codificacao == "iso-8859-1"
    assert _conta("1", resultado.contas).nome == "Caixa geral ção"
    assert resultado.ocorrencias == []


def test_utf8_e_lido_com_detecao_e_aviso():
    """Arquivo UTF-8 com acento: lido como UTF-8, com AVISO (leitura explícita, não silenciosa)."""
    bruto = "|I050|01012023|01|A|1|1||Caixa geral ção|\r\n".encode("utf-8")

    resultado = ecd.ler(bruto)

    assert resultado.codificacao == "utf-8"
    assert _conta("1", resultado.contas).nome == "Caixa geral ção"
    avisos = [o for o in resultado.ocorrencias if o.nivel == NIVEL_AVISO]
    assert len(avisos) == 1
    assert avisos[0].campo == "codificacao"
    assert "p. 52" in avisos[0].mensagem
    assert not resultado.tem_erro


def test_ascii_puro_nao_gera_aviso_de_codificacao():
    resultado = ecd.ler(_arquivo("|I050|01012023|01|A|1|1||Caixa|"))

    assert resultado.codificacao == "ascii"
    assert resultado.ocorrencias == []


# -----------------------------------------------------------------------------
# Leitura: recusas com linha e campo (critério 1)
# -----------------------------------------------------------------------------


def test_data_dt_alt_que_nao_e_ddmmaaaa_real_e_recusada_com_campo():
    """Campo 02 DT_ALT, N8 em ddmmaaaa (p. 118; formato p. 53). 31/02 não existe."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|31022023|01|A|1|1||Caixa|",
            "|I050|2023-01-31|01|A|1|2||Banco|",
        )
    )

    assert _erros(resultado) == {(1, "DT_ALT"), (2, "DT_ALT")}
    assert resultado.contas == []
    assert "p. 53" in _mensagens_de_erro(resultado)[0]


def test_numero_de_campos_errado_e_recusado_pela_linha():
    """I050 tem 8 campos (pp. 118-119). Um campo a mais, por um '|' no nome, é erro."""
    resultado = ecd.ler(_arquivo("|I050|01012023|01|A|1|1||Caixa|extra|"))

    assert _erros(resultado) == {(1, "REG")}
    assert resultado.contas == []


def test_campo_obrigatorio_vazio_cta_e_recusado():
    """Campo 08, CTA, obrigatório (p. 118). Nome só com espaços é vazio (p. 120)."""
    resultado = ecd.ler(_arquivo("|I050|01012023|01|A|1|1|| |"))

    assert _erros(resultado) == {(1, "CTA")}


def test_linha_que_nao_comeca_e_termina_com_pipe_e_recusada():
    """p. 52: cada registro começa e termina com '|'."""
    resultado = ecd.ler(_arquivo("I050|01012023|01|A|1|1||Caixa"))

    assert _erros(resultado) == {(1, "linha")}


def test_registro_desconhecido_e_erro_nomeado_pela_linha():
    """Tabela de registros (pp. 57-58): 'X999' não consta do leiaute."""
    resultado = ecd.ler(_arquivo("|X999|1|2|"))

    assert _erros(resultado) == {(1, "REG")}
    assert "X999" in _mensagens_de_erro(resultado)[0]


def test_registros_do_leiaute_fora_do_bloco_i_sao_contados_nao_recusados():
    """0000 e I010 são do leiaute, mas o leitor não os usa: contam, não viram erro."""
    resultado = ecd.ler(
        _arquivo(
            "|0000|LECD|01012023|31122023|Empresa Fictícia|",
            "|I010|G|",
            "|I050|01012023|01|A|1|1||Caixa|",
            "|I155|1|0,00|D|0,00|0,00|0,00|D|",
            "|I155|1|0,00|D|0,00|0,00|0,00|D|",
            "|9999|8|",
        )
    )

    assert not resultado.tem_erro, resultado.ocorrencias
    assert resultado.registros_ignorados == {"0000": 1, "I010": 1, "I155": 2, "9999": 1}
    assert [c.codigo for c in resultado.contas] == ["1"]


# -----------------------------------------------------------------------------
# Leitura: natureza, nível e conta superior (pp. 118-121)
# -----------------------------------------------------------------------------


def test_cod_nat_04_resultado_vira_tipo_none_HI87():
    """COD_NAT 04 (p. 119) não separa receita de despesa: tipo None (HI-87)."""
    resultado = ecd.ler(_arquivo("|I050|01012023|04|S|1|3||Receitas e despesas|"))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert _conta("3", resultado.contas).tipo is None


@pytest.mark.parametrize(
    ("cod_nat", "rotulo"),
    [("05", "compensação"), ("09", "outras")],
)
def test_cod_nat_05_e_09_sao_recusados_com_erro_nomeado(cod_nat, rotulo):
    """Tabela da p. 119: 05 e 09 existem no leiaute, mas o DataLedger não os cadastra."""
    resultado = ecd.ler(_arquivo(f"|I050|01012023|{cod_nat}|A|1|9||Conta fora|"))

    assert _erros(resultado) == {(1, "COD_NAT")}
    assert rotulo in _mensagens_de_erro(resultado)[0]
    assert resultado.contas == []


def test_cod_nat_fora_da_tabela_e_recusado():
    resultado = ecd.ler(_arquivo("|I050|01012023|07|A|1|1||Caixa|"))

    assert _erros(resultado) == {(1, "COD_NAT")}
    assert "p. 119" in _mensagens_de_erro(resultado)[0]


def test_ind_cta_diferente_de_s_ou_a_e_recusado():
    resultado = ecd.ler(_arquivo("|I050|01012023|01|X|1|1||Caixa|"))

    assert _erros(resultado) == {(1, "IND_CTA")}


def test_nivel_zero_ou_nao_numerico_e_recusado():
    """Campo 05, NIVEL, 'maior ou igual a 1' (p. 120, REGRA_MAIOR_QUE_UM)."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|A|0|1||Caixa|",
            "|I050|01012023|01|A|um|2||Banco|",
        )
    )

    assert _erros(resultado) == {(1, "NIVEL"), (2, "NIVEL")}


def test_conta_de_nivel_maior_que_1_sem_superior_e_recusada():
    """COD_CTA_SUP obrigatório se NIVEL > 1 (p. 120, REGRA_COD_CTA_SUP_OBRIGATORIO)."""
    resultado = ecd.ler(_arquivo("|I050|01012023|01|A|2|1.1||Caixa|"))

    assert _erros(resultado) == {(1, "COD_CTA_SUP")}
    assert "p. 120" in _mensagens_de_erro(resultado)[0]


def test_conta_de_nivel_1_com_superior_e_recusada():
    """p. 121, REGRA_CONTA_SUPERIOR_NAO_SE_APLICA: nível 1 não tem superior."""
    resultado = ecd.ler(_arquivo("|I050|01012023|01|S|1|1|9|Ativo|"))

    assert _erros(resultado) == {(1, "COD_CTA_SUP")}
    assert "p. 121" in _mensagens_de_erro(resultado)[0]


def test_conta_que_e_superior_de_si_mesma_e_recusada():
    """p. 120, REGRA_COD_CTA_IGUAL_COD_CTA_SUP."""
    resultado = ecd.ler(_arquivo("|I050|01012023|01|S|2|1.1|1.1|Ativo|"))

    assert _erros(resultado) == {(1, "COD_CTA_SUP")}


def test_superior_analitica_nao_pode_ter_filha_p120():
    """REGRA_CONTA_NIVEL_SUPERIOR_NAO_SINTETICA (p. 120): a superior tem de ser S."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|A|1|1||Caixa|",
            "|I050|01012023|01|A|2|1.1|1|Filha de analítica|",
        )
    )

    assert _erros(resultado) == {(2, "COD_CTA_SUP")}
    assert "p. 120" in _mensagens_de_erro(resultado)[0]
    assert [c.codigo for c in resultado.contas] == ["1"]


def test_filha_com_mesmo_nivel_que_a_superior_e_recusada_p120():
    """REGRA_NIVEL_DE_CONTA_NIVEL_SUPERIOR_INVALIDO (p. 120): o nível cresce."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|2|1.1|1|Pai|",
            "|I050|01012023|01|S|2|1.1.1|1.1|Filha de mesmo nível|",
        )
    )

    assert (2, "NIVEL") in _erros(resultado)


def test_natureza_diferente_da_superior_a_partir_do_nivel_3_e_recusada_p121():
    """REGRA_NATUREZA_CONTA (p. 121): nível > 2 exige a mesma COD_NAT da superior."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|1|1||Ativo|",
            "|I050|01012023|01|S|2|1.1|1|Circulante|",
            "|I050|01012023|04|A|3|1.1.1|1.1|Conta de resultado sob ativo|",
        )
    )

    assert (3, "COD_NAT") in _erros(resultado)
    assert "p. 121" in " ".join(_mensagens_de_erro(resultado))


def test_conta_superior_recusada_derruba_a_filha_em_cascata():
    """Quem depende de conta recusada não entra; a mensagem aponta a origem."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|05|S|1|9||Compensação|",
            "|I050|01012023|01|S|2|9.1|9|Filha da recusada|",
            "|I050|01012023|01|A|3|9.1.1|9.1|Neta|",
        )
    )

    assert _erros(resultado) == {(1, "COD_NAT"), (2, "COD_CTA_SUP"), (3, "COD_CTA_SUP")}
    assert resultado.contas == []


def test_superior_que_vem_depois_no_arquivo_tambem_e_aceita():
    """A checagem de superior é feita sobre o arquivo inteiro, não linha a linha."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|A|2|1.1|1|Caixa|",
            "|I050|01012023|01|S|1|1||Ativo|",
        )
    )

    assert not resultado.tem_erro, resultado.ocorrencias
    assert {c.codigo for c in resultado.contas} == {"1", "1.1"}
    assert _conta("1.1", resultado.contas).codigo_pai == "1"


# -----------------------------------------------------------------------------
# Leitura: duplicidade e I051 (pp. 119, 123-124)
# -----------------------------------------------------------------------------


def test_codigo_repetido_no_arquivo_e_recusado_p119():
    """REGRA_COD_CTA_DUPLICADO (p. 119): a chave do I050 é COD_CTA."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|1|1||Ativo|",
            "|I050|01012023|01|A|2|1.1|1|Caixa|",
            "|I050|01012023|01|A|2|1.1|1|Caixa de novo|",
        )
    )

    assert _erros(resultado) == {(3, "COD_CTA")}
    assert "p. 119" in _mensagens_de_erro(resultado)[0]
    assert [c.codigo for c in resultado.contas] == ["1", "1.1"]


def test_i051_em_conta_sintetica_e_recusado_p124():
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|S|1|1||Ativo|",
            "|I051||11100009|",
        )
    )

    assert _erros(resultado) == {(2, "REG")}
    assert "p. 124" in _mensagens_de_erro(resultado)[0]


def test_i051_com_centro_de_custo_e_aviso_e_nao_e_guardado_p123():
    """Centro de custo não existe no DataLedger nesta fatia: aviso, nunca silêncio."""
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|A|1|1||Caixa|",
            "|I051|123|101010102|",
        )
    )

    assert not resultado.tem_erro
    avisos = [o for o in resultado.ocorrencias if o.nivel == NIVEL_AVISO]
    assert [(o.linha, o.campo) for o in avisos] == [(2, "COD_CCUS")]
    assert _conta("1", resultado.contas).referencial is None


def test_i051_sem_i050_acima_e_recusado_p124():
    resultado = ecd.ler(_arquivo("|I051||11100009|"))

    assert _erros(resultado) == {(1, "REG")}


def test_dois_i051_sem_centro_de_custo_para_a_mesma_conta_sao_recusados_p123():
    resultado = ecd.ler(
        _arquivo(
            "|I050|01012023|01|A|1|1||Caixa|",
            "|I051||11100009|",
            "|I051||11100010|",
        )
    )

    assert _erros(resultado) == {(3, "COD_CTA_REF")}


# -----------------------------------------------------------------------------
# Escrita (critério 1 da escrita; pp. 52, 118, 121, 124)
# -----------------------------------------------------------------------------


def _contas_de_exemplo():
    def conta(codigo, nome, codigo_pai, analitica, tipo, referencial=None):
        return ContaLida(
            linha=0,
            codigo=codigo,
            nome=nome,
            codigo_pai=codigo_pai,
            analitica=analitica,
            tipo=tipo,
            natureza=None,
            codigo_origem=None,
            referencial=referencial,
        )

    return [
        conta("1", "Ativo", None, False, "ativo"),
        conta("1.1", "Caixa", "1", False, "ativo"),
        conta("1.1.1", "Caixa geral", "1.1", True, "ativo", referencial="11100009"),
        conta("3", "Receitas", None, False, "receita"),
        conta("3.1", "Vendas", "3", True, "receita"),
        conta("4", "Despesas", None, False, "despesa"),
        conta("4.1", "Aluguel", "4", True, "despesa"),
    ]


def test_escrita_gera_i050_com_dt_alt_cod_nat_nivel_e_superior_exatos():
    """Saída byte a byte, conferida contra os exemplos das pp. 121 e 124.

    Receita e despesa saem ambas como COD_NAT 04 (p. 119): a ECD não as separa (HI-87).
    """
    saida = ecd.escrever(_contas_de_exemplo(), data_alteracao=date(2026, 1, 31))

    assert saida == (
        b"|I050|31012026|01|S|1|1||Ativo|\r\n"
        b"|I050|31012026|01|S|2|1.1|1|Caixa|\r\n"
        b"|I050|31012026|01|A|3|1.1.1|1.1|Caixa geral|\r\n"
        b"|I051||11100009|\r\n"
        b"|I050|31012026|04|S|1|3||Receitas|\r\n"
        b"|I050|31012026|04|A|2|3.1|3|Vendas|\r\n"
        b"|I050|31012026|04|S|1|4||Despesas|\r\n"
        b"|I050|31012026|04|A|2|4.1|4|Aluguel|\r\n"
    )


def test_escrita_e_iso_8859_1_com_crlf_e_acento_no_lugar_certo():
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome="Caixa geral ção",
            codigo_pai=None,
            analitica=True,
            tipo="ativo",
            natureza=None,
            codigo_origem=None,
            referencial=None,
        )
    ]

    saida = ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert saida.endswith(b"\r\n")
    assert b"\xe7\xe3o" in saida  # 'ção' em ISO-8859-1
    assert saida.decode("iso-8859-1").count("\r\n") == 1


def test_escrita_sem_data_de_alteracao_e_recusada():
    """DT_ALT é obrigatório (p. 118). O DataLedger não inventa a data."""
    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(_contas_de_exemplo(), data_alteracao=None)

    assert "p. 118" in exc.value.mensagem


def test_escrita_recusa_caractere_fora_do_latin1_sem_substituir():
    """'€' não existe em ISO-8859-1 (p. 52). A exportação recusa; não troca por '?'."""
    contas = _contas_de_exemplo()
    contas[0] = ContaLida(
        linha=0,
        codigo="1",
        nome="Ativo € reservado",
        codigo_pai=None,
        analitica=False,
        tipo="ativo",
        natureza=None,
        codigo_origem=None,
        referencial=None,
    )

    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert "'€'" in exc.value.mensagem
    assert "p. 52" in exc.value.mensagem
    assert any(o.campo == "CTA" for o in exc.value.ocorrencias)


def test_escrita_recusa_barra_vertical_no_nome():
    """'|' é o separador do leiaute e não pode aparecer em campo (p. 52)."""
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome="Caixa | banco",
            codigo_pai=None,
            analitica=True,
            tipo="ativo",
            natureza=None,
            codigo_origem=None,
            referencial=None,
        )
    ]

    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert "p. 52" in exc.value.mensagem


def test_escrita_recusa_nome_acima_de_255_caracteres_p53():
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome="x" * 256,
            codigo_pai=None,
            analitica=True,
            tipo="ativo",
            natureza=None,
            codigo_origem=None,
            referencial=None,
        )
    ]

    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert "p. 53" in exc.value.mensagem


def test_escrita_recusa_superior_analitica_no_cadastro():
    """A ECD exige superior sintética. Superior analítica no cadastro é recusada,
    não corrigida em silêncio."""
    contas = _contas_de_exemplo()
    contas[1] = ContaLida(
        linha=0,
        codigo="1.1",
        nome="Caixa",
        codigo_pai="1",
        analitica=True,
        tipo="ativo",
        natureza=None,
        codigo_origem=None,
        referencial=None,
    )
    contas[2] = ContaLida(
        linha=0,
        codigo="1.1.1",
        nome="Caixa geral",
        codigo_pai="1.1",
        analitica=True,
        tipo="ativo",
        natureza=None,
        codigo_origem=None,
        referencial=None,
    )

    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert "p. 120" in exc.value.mensagem


def test_escrita_recusa_conta_sem_tipo():
    """Sem tipo não há COD_NAT (p. 119); a escrita não chuta."""
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome="Sem tipo",
            codigo_pai=None,
            analitica=True,
            tipo=None,
            natureza=None,
            codigo_origem=None,
            referencial=None,
        )
    ]

    with pytest.raises(IntercambioRecusado) as exc:
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))

    assert any(o.campo == "COD_NAT" for o in exc.value.ocorrencias)


def test_escrita_nao_grava_parcial_quando_uma_conta_falha():
    """Uma conta ruim recusa o arquivo inteiro: nenhuma linha sai."""
    contas = _contas_de_exemplo()
    contas.append(
        ContaLida(
            linha=0,
            codigo="9",
            nome="Compensação € ruim",
            codigo_pai=None,
            analitica=True,
            tipo="ativo",
            natureza=None,
            codigo_origem=None,
            referencial=None,
        )
    )

    with pytest.raises(IntercambioRecusado):
        ecd.escrever(contas, data_alteracao=date(2026, 1, 31))
