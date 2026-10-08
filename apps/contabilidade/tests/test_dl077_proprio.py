"""DL-077, fatia 1 (critérios 1 e 2): formato próprio do plano (UTF-8, ';', cabeçalho).

Arquivos montados à mão segundo a especificação do docstring de
`apps/contabilidade/intercambio/formatos/proprio.py`. Dados sintéticos.
"""

import pytest

from apps.contabilidade.intercambio.canonico import NIVEL_ERRO, ContaLida, IntercambioRecusado
from apps.contabilidade.intercambio.formatos import proprio

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"


def _texto(*linhas, bom=False, fim="\r\n"):
    conteudo = (fim.join([CABECALHO, *linhas]) + fim).encode("utf-8")
    return (b"\xef\xbb\xbf" + conteudo) if bom else conteudo


def _erros(resultado):
    return {(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO}


def test_le_contas_com_todas_as_colunas_preenchidas():
    resultado = proprio.ler(
        _texto(
            "1;Ativo;;N;ativo;devedora",
            "1.1;Caixa;1;S;ativo;devedora",
        )
    )

    assert not resultado.tem_erro, resultado.ocorrencias
    ativo, caixa = resultado.contas
    assert (ativo.codigo, ativo.codigo_pai, ativo.analitica) == ("1", None, False)
    assert (ativo.tipo, ativo.natureza) == ("ativo", "devedora")
    assert (caixa.codigo_pai, caixa.analitica) == ("1", True)
    assert resultado.codificacao == "utf-8"


def test_bom_e_descartado_e_nao_atrapalha_o_cabecalho():
    resultado = proprio.ler(_texto("1;Ativo;;N;ativo;devedora", bom=True))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert [c.codigo for c in resultado.contas] == ["1"]


def test_colunas_vazias_viram_none_HI87_e_HI88():
    """tipo e natureza vazios = o formato não diz (HI-87, HI-88): None, nunca palpite."""
    resultado = proprio.ler(_texto("1.1;Banco;;S;;"))

    conta = resultado.contas[0]
    assert conta.tipo is None
    assert conta.natureza is None
    assert conta.codigo_pai is None


def test_campo_com_ponto_e_virgula_e_aspas_e_lido_pelo_escape_rfc4180():
    """Escape: campo entre aspas; aspas dentro do campo são duplicadas (`""`)."""
    resultado = proprio.ler(_texto('1.1;"Caixa; bancos ""BB""";1;S;ativo;devedora'))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert resultado.contas[0].nome == 'Caixa; bancos "BB"'


def test_escrita_e_leitura_se_pagam_com_separador_aspas_e_acento():
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome='Caixa; "geral" ção',
            codigo_pai=None,
            analitica=False,
            tipo="ativo",
            natureza="devedora",
            codigo_origem=None,
            referencial=None,
        ),
        ContaLida(
            linha=0,
            codigo="1.1",
            nome="Banco",
            codigo_pai="1",
            analitica=True,
            tipo=None,
            natureza=None,
            codigo_origem=None,
            referencial=None,
        ),
    ]

    saida = proprio.escrever(contas)
    resultado = proprio.ler(saida)

    assert saida.startswith(CABECALHO.encode() + b"\r\n")
    assert b"\xef\xbb\xbf" not in saida  # sem BOM na escrita
    assert not resultado.tem_erro, resultado.ocorrencias
    assert resultado.contas[0].nome == 'Caixa; "geral" ção'
    assert resultado.contas[1].tipo is None


def test_cabecalho_diferente_do_especificado_e_recusado_sem_ler_as_linhas():
    conteudo = "codigo;nome;superior;analitica;tipo;natureza\r\n1;Ativo;;N;ativo;devedora\r\n"
    resultado = proprio.ler(conteudo.encode("utf-8"))

    assert _erros(resultado) == {(1, "cabecalho")}
    assert resultado.contas == []


def test_arquivo_vazio_e_recusado():
    resultado = proprio.ler(b"")

    assert _erros(resultado) == {(1, "cabecalho")}


def test_arquivo_que_nao_e_utf8_e_recusado_com_codificacao_nomeada():
    resultado = proprio.ler(b"codigo;nome\r\n1;Caixa \xe7\xe3\r\n")

    assert _erros(resultado) == {(0, "codificacao")}
    assert resultado.contas == []


@pytest.mark.parametrize(
    ("linha", "campo"),
    [
        ("1;Ativo;;N;ativo", "estrutura"),  # 5 campos
        ("1;Ativo;;N;ativo;devedora;extra", "estrutura"),  # 7 campos
    ],
)
def test_linha_com_numero_de_campos_errado_e_recusada(linha, campo):
    resultado = proprio.ler(_texto(linha))

    assert _erros(resultado) == {(2, campo)}


def test_analitica_so_aceita_S_ou_N():
    resultado = proprio.ler(_texto("1;Ativo;;X;ativo;devedora"))

    assert _erros(resultado) == {(2, "analitica")}


def test_tipo_e_natureza_fora_do_enum_sao_recusados():
    resultado = proprio.ler(
        _texto(
            "1;Ativo;;N;patrimonio;devedora",
            "2;Passivo;;N;passivo;devedor",
        )
    )

    assert _erros(resultado) == {(2, "tipo"), (3, "natureza")}


def test_codigo_repetido_no_arquivo_e_recusado_na_segunda_ocorrencia():
    resultado = proprio.ler(
        _texto(
            "1;Ativo;;N;ativo;devedora",
            "1;Outro ativo;;N;ativo;devedora",
        )
    )

    assert _erros(resultado) == {(3, "codigo")}


def test_codigo_nome_ausente_e_recusados_com_campo():
    resultado = proprio.ler(_texto(";Sem código;;N;ativo;devedora", "2; ;;N;ativo;devedora"))

    assert _erros(resultado) == {(2, "codigo"), (3, "nome")}


def test_codigo_acima_de_20_caracteres_e_recusado():
    """Limite do cadastro (`Conta.codigo`, max_length=20)."""
    resultado = proprio.ler(_texto("1" * 21 + ";Longo;;N;ativo;devedora"))

    assert _erros(resultado) == {(2, "codigo")}


def test_aspas_malformadas_param_a_leitura_com_linha():
    """Aspas no meio de campo sem aspas de abertura: erro de estrutura, na linha."""
    resultado = proprio.ler(_texto("1;Ativo;;N;ativo;devedora", '2;Caixa "x";;N;ativo;devedora'))

    assert (3, "estrutura") in _erros(resultado)
    assert [c.codigo for c in resultado.contas] == ["1"]


def test_linhas_em_branco_sao_ignoradas():
    resultado = proprio.ler(_texto("", "1;Ativo;;N;ativo;devedora", ""))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert [c.codigo for c in resultado.contas] == ["1"]


def test_lf_sem_cr_tambem_e_aceito_na_leitura():
    resultado = proprio.ler(_texto("1;Ativo;;N;ativo;devedora", fim="\n"))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert len(resultado.contas) == 1


def test_escrita_recusa_tipo_que_nao_esta_no_enum():
    """A escrita não converte nada: se o tipo não é de `TipoConta`, é erro."""
    conta = ContaLida(
        linha=7,
        codigo="1",
        nome="Ativo",
        codigo_pai=None,
        analitica=True,
        tipo="inventado",
        natureza=None,
        codigo_origem=None,
        referencial=None,
    )

    with pytest.raises(IntercambioRecusado) as exc:
        proprio.escrever([conta])

    assert exc.value.ocorrencias[0].campo == "tipo"
    assert exc.value.ocorrencias[0].linha == 7


def test_quebra_de_linha_dentro_de_campo_entre_aspas_sobrevive_ao_ida_e_volta():
    """Escape (especificação): CR ou LF dentro de campo entre aspas. A linha seguinte
    continua sendo contada na linha física certa."""
    contas = [
        ContaLida(
            linha=0,
            codigo="1",
            nome="Linha um\nLinha dois",
            codigo_pai=None,
            analitica=True,
            tipo="ativo",
            natureza="devedora",
            codigo_origem=None,
            referencial=None,
        ),
        ContaLida(
            linha=0,
            codigo="2",
            nome="Segunda",
            codigo_pai=None,
            analitica=True,
            tipo="passivo",
            natureza="credora",
            codigo_origem=None,
            referencial=None,
        ),
    ]

    resultado = proprio.ler(proprio.escrever(contas))

    assert not resultado.tem_erro, resultado.ocorrencias
    assert resultado.contas[0].nome == "Linha um\nLinha dois"
    assert resultado.contas[1].linha == 4  # cabeçalho + 2 linhas físicas da primeira conta + 1


def test_caractere_solto_depois_de_campo_entre_aspas_e_erro_de_estrutura():
    resultado = proprio.ler(_texto('1;"Ativo"x;;S;ativo;devedora'))

    assert _erros(resultado) == {(2, "estrutura")}
    assert resultado.contas == []
