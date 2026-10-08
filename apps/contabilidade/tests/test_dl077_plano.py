"""DL-077, fatia 1 (critérios 3, 4 e 5): conferência do plano antes de gravar.

`conferir_plano` não grava. Estes testes provam as regras de tipo, natureza, conta
superior, duplicidade e política sobre arquivos sintéticos montados à mão, contra
um cadastro real no banco de teste. Regra de origem: HI-87 (tipo), HI-88 (natureza),
plano DL-077 (conta superior sintética, nunca apagar, nunca mudar conta existente).
"""

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    ResultadoLeitura,
)
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import (
    ACAO_ATUALIZAR,
    ACAO_CRIAR,
    ACAO_RECUSADA,
    ACAO_SEM_MUDANCA,
    POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
    POLITICA_SO_ACRESCENTAR,
    ParametroInvalido,
    conferir_plano,
)
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 Plano", cnpj="11111111000111")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL077 Plano Ltda", cnpj="11122233000183"
    )


def _proprio(*linhas):
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")
    return ler_arquivo("proprio", conteudo, nome_arquivo="plano.txt")


def _ecd(*linhas):
    conteudo = ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
    return ler_arquivo("ecd", conteudo, nome_arquivo="plano.txt")


def _conferir(empresa, resultado, politica=POLITICA_SO_ACRESCENTAR, prefixos=None):
    return conferir_plano(empresa, resultado, politica, prefixos or {})


def _item(previa, codigo):
    return next(i for i in previa.itens if i.codigo == codigo)


def _erros(previa):
    return {(o.linha, o.campo) for o in previa.ocorrencias if o.nivel == NIVEL_ERRO}


def _avisos(previa):
    return {(o.linha, o.campo) for o in previa.ocorrencias if o.nivel == NIVEL_AVISO}


def _cadastrar(empresa, codigo, nome, tipo, natureza, pai=None, analitica=True):
    return Conta.objects.create(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        conta_pai=pai,
        aceita_lancamento=analitica,
    )


# -----------------------------------------------------------------------------
# Tipo (HI-87) e natureza (HI-88)
# -----------------------------------------------------------------------------


def test_arquivo_com_tipo_e_natureza_em_empresa_vazia_cria_tudo_com_origem_no_arquivo(empresa):
    previa = _conferir(
        empresa,
        _proprio("1;Ativo;;N;ativo;devedora", "1.1;Caixa;1;S;ativo;devedora"),
    )

    assert not previa.tem_erro, previa.ocorrencias
    assert previa.contagens == {"criar": 2, "atualizar": 0, "sem_mudanca": 0, "recusada": 0}
    caixa = _item(previa, "1.1")
    assert (caixa.acao, caixa.tipo, caixa.origem_tipo) == (ACAO_CRIAR, "ativo", "arquivo")
    assert (caixa.natureza, caixa.origem_natureza) == ("devedora", "arquivo")
    assert caixa.codigo_pai == "1"
    assert caixa.analitica is True
    # A12: conta nova sem classificação gera o aviso de classificar depois (linha 0). É o
    # único aviso que este teste espera.
    assert _avisos(previa) == {(0, "classificacao")}


def test_tipo_herdado_da_conta_superior_quando_o_arquivo_nao_diz(empresa):
    previa = _conferir(
        empresa,
        _proprio("3;Receitas;;N;receita;credora", "3.1;Vendas;3;S;;"),
    )

    vendas = _item(previa, "3.1")
    assert (vendas.tipo, vendas.origem_tipo) == ("receita", "conta_superior")


def test_tipo_herdado_do_cadastro_quando_a_superior_ja_existe(empresa):
    """A superior cadastrada (receita) dá o tipo da filha nova (ECD 04 não diz receita)."""
    _cadastrar(empresa, "3", "Receitas", TipoConta.RECEITA, NaturezaConta.CREDORA, analitica=False)

    previa = _conferir(empresa, _ecd("|I050|01012023|04|A|2|3.1|3|Vendas|"))

    vendas = _item(previa, "3.1")
    assert (vendas.acao, vendas.tipo, vendas.origem_tipo) == (
        ACAO_CRIAR,
        "receita",
        "conta_superior",
    )


def test_prefixo_informado_define_o_tipo_de_conta_raiz_sem_tipo_HI87(empresa):
    """ECD COD_NAT 04 não separa receita de despesa: o contador informa por prefixo."""
    previa = _conferir(
        empresa,
        _ecd(
            "|I050|01012023|04|S|1|3||Receitas|",
            "|I050|01012023|04|A|2|3.1|3|Vendas|",
        ),
        prefixos={"3": "receita"},
    )

    assert not previa.tem_erro, previa.ocorrencias
    receitas = _item(previa, "3")
    assert (receitas.tipo, receitas.origem_tipo) == ("receita", "prefixo")
    assert _item(previa, "3.1").origem_tipo == "conta_superior"


def test_prefixo_mais_longo_vence_o_mais_curto(empresa):
    previa = _conferir(
        empresa,
        _proprio("3.1;Vendas;;S;;", "3.9.1;Despesa especial;;S;;"),
        prefixos={"3": "receita", "3.9": "despesa"},
    )

    assert _item(previa, "3.1").tipo == "receita"
    assert _item(previa, "3.9.1").tipo == "despesa"


def test_sem_tipo_e_sem_prefixo_e_erro_HI87(empresa):
    """Sem arquivo, sem superior e sem prefixo: o produto não adivinha tipo."""
    previa = _conferir(empresa, _ecd("|I050|01012023|04|S|1|3||Receitas|"))

    assert previa.tem_erro
    assert _erros(previa) == {(1, "tipo")}
    assert _item(previa, "3").acao == ACAO_RECUSADA
    assert "HI-87" in _item(previa, "3").ocorrencias[0].mensagem


def test_tipo_do_arquivo_incompativel_com_o_da_superior_e_erro(empresa):
    previa = _conferir(
        empresa,
        _proprio("1;Ativo;;N;ativo;devedora", "1.1;Algo;1;S;receita;credora"),
    )

    assert _erros(previa) == {(3, "tipo")}


def test_natureza_presumida_pelo_tipo_gera_aviso_por_conta_HI88(empresa):
    """Sem natureza no arquivo: presumida pelo tipo, e um aviso para cada conta."""
    previa = _conferir(
        empresa,
        _proprio(
            "1;Ativo;;N;ativo;",
            "1.1;Caixa;1;S;ativo;",
            "3;Receitas;;N;receita;",
            "3.1;Vendas;3;S;receita;",
        ),
    )

    assert not previa.tem_erro, previa.ocorrencias
    # A12: além dos avisos de natureza por conta, o aviso de classificação pendente (linha 0).
    assert _avisos(previa) == {
        (0, "classificacao"),
        (2, "natureza"),
        (3, "natureza"),
        (4, "natureza"),
        (5, "natureza"),
    }
    assert _item(previa, "1").natureza == "devedora"
    assert _item(previa, "3.1").natureza == "credora"
    assert _item(previa, "1.1").origem_natureza == "presumida_pelo_tipo"


def test_natureza_informada_pelo_arquivo_nao_gera_aviso_nem_e_trocada(empresa):
    """Conta redutora (ativo credora, p. ex. depreciação acumulada) passa sem aviso."""
    previa = _conferir(
        empresa,
        _proprio(
            "1;Ativo;;N;ativo;devedora",
            "1.2;Depreciação acumulada;1;S;ativo;credora",
        ),
    )

    # A12: conta nova sem classificação gera o aviso de classificar depois (linha 0). É o
    # único aviso que este teste espera.
    assert _avisos(previa) == {(0, "classificacao")}
    redutora = _item(previa, "1.2")
    assert (redutora.natureza, redutora.origem_natureza) == ("credora", "arquivo")


# -----------------------------------------------------------------------------
# Conta superior e duplicidade (critérios 3 e 4)
# -----------------------------------------------------------------------------


def test_conta_superior_que_nao_existe_e_erro(empresa):
    previa = _conferir(empresa, _proprio("1.1;Caixa;9;S;ativo;devedora"))

    assert _erros(previa) == {(2, "codigo_pai")}


def test_conta_superior_analitica_no_arquivo_nao_aceita_filha_p120(empresa):
    """Ponto (a) da mutação: pai analítico é recusado, não aceito."""
    previa = _conferir(
        empresa,
        _proprio("1;Ativo;;S;ativo;devedora", "1.1;Caixa;1;S;ativo;devedora"),
    )

    assert _erros(previa) == {(3, "codigo_pai")}
    assert _item(previa, "1.1").acao == ACAO_RECUSADA
    assert "analítica" in _item(previa, "1.1").ocorrencias[0].mensagem


def test_conta_superior_analitica_no_cadastro_nao_aceita_filha(empresa):
    _cadastrar(empresa, "1", "Caixa analítica", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1.1;Banco;1;S;ativo;devedora"))

    assert _erros(previa) == {(2, "codigo_pai")}


def test_conta_superior_sintetica_no_cadastro_aceita_filha(empresa):
    _cadastrar(empresa, "1", "Ativo", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False)

    previa = _conferir(empresa, _proprio("1.1;Banco;1;S;ativo;devedora"))

    assert not previa.tem_erro, previa.ocorrencias
    assert _item(previa, "1.1").acao == ACAO_CRIAR


def test_codigo_repetido_no_arquivo_e_erro_na_segunda_ocorrencia(empresa):
    previa = _conferir(
        empresa,
        _proprio("1;Ativo;;N;ativo;devedora", "1;Outro;;N;ativo;devedora"),
    )

    assert _erros(previa) == {(3, "codigo")}


def test_ciclo_na_hierarquia_e_erro(empresa):
    previa = _conferir(
        empresa,
        _proprio("1;A;2;N;ativo;devedora", "2;B;1;N;ativo;devedora"),
    )

    assert previa.tem_erro
    assert _item(previa, "1").acao == ACAO_RECUSADA
    assert _item(previa, "2").acao == ACAO_RECUSADA


def test_conta_que_e_superior_de_si_mesma_e_erro(empresa):
    previa = _conferir(empresa, _proprio("1;A;1;N;ativo;devedora"))

    assert _erros(previa) == {(2, "codigo_pai")}


# -----------------------------------------------------------------------------
# Conta existente: nunca muda tipo, natureza, superior ou caráter analítico
# -----------------------------------------------------------------------------


def test_conta_existente_igual_ao_arquivo_fica_sem_mudanca(empresa):
    _cadastrar(empresa, "1", "Ativo", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False)

    previa = _conferir(empresa, _proprio("1;Ativo;;N;ativo;devedora"))

    assert not previa.tem_erro, previa.ocorrencias
    assert _item(previa, "1").acao == ACAO_SEM_MUDANCA


def test_tipo_diferente_de_conta_existente_e_erro_e_nao_muda_c(empresa):
    """Ponto (c) da mutação: conta existente nunca tem o tipo trocado pelo arquivo."""
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1.1;Caixa;;S;passivo;devedora"))

    assert _erros(previa) == {(2, "tipo")}
    assert _item(previa, "1.1").tipo == "ativo"
    assert _item(previa, "1.1").origem_tipo == "cadastro"


def test_natureza_diferente_de_conta_existente_e_erro(empresa):
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1.1;Caixa;;S;ativo;credora"))

    assert _erros(previa) == {(2, "natureza")}


def test_analitica_diferente_de_conta_existente_e_erro(empresa):
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=True)

    previa = _conferir(empresa, _proprio("1.1;Caixa;;N;ativo;devedora"))

    assert _erros(previa) == {(2, "analitica")}


def test_conta_superior_diferente_da_cadastrada_e_erro(empresa):
    pai_a = _cadastrar(
        empresa, "1", "Ativo", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False
    )
    _cadastrar(empresa, "2", "Outro", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False)
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA, pai=pai_a)

    previa = _conferir(
        empresa, _proprio("2;Outro;;N;ativo;devedora", "1.1;Caixa;2;S;ativo;devedora")
    )

    assert _erros(previa) == {(3, "codigo_pai")}


def test_politica_so_acrescentar_mantem_o_nome_cadastrado_com_aviso(empresa):
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1.1;Caixa geral;;S;ativo;devedora"))

    caixa = _item(previa, "1.1")
    assert caixa.acao == ACAO_SEM_MUDANCA
    assert (2, "nome") in _avisos(previa)
    assert caixa.nome == "Caixa geral"  # o que o arquivo diz fica visível; o cadastro não muda


def test_politica_acrescentar_e_atualizar_nome_marca_atualizar(empresa):
    _cadastrar(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(
        empresa,
        _proprio("1.1;Caixa geral;;S;ativo;devedora"),
        politica=POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
    )

    assert not previa.tem_erro, previa.ocorrencias
    assert _item(previa, "1.1").acao == ACAO_ATUALIZAR


def test_conta_que_nao_esta_no_arquivo_nunca_aparece_como_acao(empresa):
    """Nunca apagar: conta do cadastro fora do arquivo não vira item nenhum."""
    _cadastrar(empresa, "9", "Só no cadastro", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1;Ativo;;N;ativo;devedora"))

    assert "9" not in {i.codigo for i in previa.itens}
    assert previa.contagens["criar"] == 1


def test_conta_de_outra_empresa_com_o_mesmo_codigo_nao_entra_na_conferencia(empresa):
    """Isolamento: o mesmo código em outra empresa não vira 'sem mudança' aqui."""
    outra = Empresa.objects.create(
        escritorio=empresa.escritorio, razao_social="Outra Ltda", cnpj="44455566000183"
    )
    _cadastrar(outra, "1", "Ativo de outra empresa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    previa = _conferir(empresa, _proprio("1;Ativo;;N;ativo;devedora"))

    assert _item(previa, "1").acao == ACAO_CRIAR


# -----------------------------------------------------------------------------
# Entrada, limites e recusas de parâmetro
# -----------------------------------------------------------------------------


def test_arquivo_sem_nenhuma_conta_e_erro(empresa):
    previa = _conferir(empresa, _proprio())

    assert previa.tem_erro
    assert (0, "arquivo") in _erros(previa)


def test_referencial_lido_gera_aviso_e_nao_e_gravado(empresa):
    previa = _conferir(
        empresa,
        _ecd(
            "|I050|01012023|01|S|1|1||Ativo|",
            "|I050|01012023|01|S|2|1.1|1|Circulante|",
            "|I050|01012023|01|S|3|1.1.1|1.1|Disponível|",
            "|I050|01012023|01|A|4|1.1.1.1|1.1.1|Caixa|",
            "|I051||11100009|",
        ),
    )

    assert not previa.tem_erro, previa.ocorrencias
    assert (4, "referencial") in _avisos(previa)


def test_politica_desconhecida_levanta_parametro_invalido(empresa):
    with pytest.raises(ParametroInvalido):
        _conferir(empresa, _proprio("1;A;;N;ativo;devedora"), politica="apagar_tudo")


def test_prefixo_com_tipo_inexistente_levanta_parametro_invalido(empresa):
    with pytest.raises(ParametroInvalido):
        _conferir(
            empresa,
            _proprio("1;A;;N;ativo;devedora"),
            prefixos={"3": "lucro"},
        )


def test_codigo_acima_de_20_caracteres_e_erro_no_plano(empresa):
    """Limite do cadastro (`Conta.codigo`, 20). A conferência é quem impõe, não o formato."""
    resultado = ResultadoLeitura(
        formato="proprio",
        contas=[
            ContaLida(
                linha=2,
                codigo="1" * 21,
                nome="Longo",
                codigo_pai=None,
                analitica=True,
                tipo="ativo",
                natureza="devedora",
                codigo_origem=None,
                referencial=None,
            )
        ],
    )

    previa = _conferir(empresa, resultado)

    assert _erros(previa) == {(2, "codigo")}


def test_conferir_nao_grava_nada_no_banco(empresa):
    """Conferir é só leitura: nenhuma conta nova e nenhum registro de auditoria."""
    antes_contas = Conta.objects.count()
    antes_trilha = RegistroAuditoria.objects.count()

    _conferir(empresa, _proprio("1;Ativo;;N;ativo;devedora", "1.1;Caixa;1;S;ativo;devedora"))

    assert Conta.objects.count() == antes_contas
    assert RegistroAuditoria.objects.count() == antes_trilha
