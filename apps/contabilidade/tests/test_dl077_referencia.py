"""DL-077, fatia 1, frente B: plano de contas no leiaute com separador do sistema de
referência (`formatos/referencia.py`).

Arquivos SINTÉTICOS montados aqui a partir do que o leiaute define (separador `|`,
registros 0000, 0200 e 0250, campos e data `dd/mm/aaaa`). CNPJ e CPF são fictícios.
Nenhum texto do manual aparece neste arquivo (RC-167).

Cobre: leitura (campos, datas, superior pela classificação, avisos, registros
ignorados, codificação, barras nas pontas), a escrita, a ida e volta (escrever, ler,
aplicar no núcleo), a situação das contas e a API (prévia, aplicação e exportação).
A conferência do CNPJ/CPF declarado é do núcleo: ver `test_dl077_documento_declarado.py`.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
)
from apps.contabilidade.intercambio.formatos import ESCRITORES, LEITORES, referencia
from apps.contabilidade.intercambio.formatos.referencia import (
    derivar_pai,
    escrever,
    ler,
)
from apps.contabilidade.intercambio.plano import aplicar_plano, conferir_plano
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
CNPJ = "44444444000144"  # sintético
CNPJ_MASCARADO = "44.444.444/0001-44"
CNPJ_DE_OUTRA_EMPRESA = "55555555000155"  # sintético
CPF = "12345678909"  # sintético (DV válido, dados fictícios)


def _linhas(*linhas):
    """Arquivo ISO-8859-1 com CRLF, como o leiaute é lido pelo projeto."""
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")


def _registro(*campos):
    """Registro na forma CANÔNICA: `|` no início e no fim (a do exemplo oficial do fornecedor)."""
    return "|" + "|".join(campos) + "|"


def _registro_sem_barras(*campos):
    """Registro SEM as barras das pontas: a leitura aceita, com aviso de forma."""
    return "|".join(campos)


def _conta(
    reduzido,
    classificacao,
    tipo,
    descricao,
    situacao="A",
    data="",
    inativacao="",
    relacionamentos=("", "", ""),
):
    """0200 com os 11 campos do leiaute (identificador incluído)."""
    return _registro(
        "0200",
        reduzido,
        classificacao,
        tipo,
        descricao,
        data,
        situacao,
        inativacao,
        *relacionamentos,
    )


def _0250(referencial, orgao="R"):
    return _registro("0250", referencial, orgao)


def _cabecalho(cnpj=CNPJ):
    return _registro("0000", cnpj)


def _plano_sintetico():
    return _linhas(
        _cabecalho(CNPJ_MASCARADO),
        _conta("1", "1", "S", "Ativo"),
        _conta("2", "1.1", "S", "Circulante"),
        _conta("3", "1.1.01", "A", "Caixa geral"),
    )


# -----------------------------------------------------------------------------
# Leitura: campos, superior e avisos
# -----------------------------------------------------------------------------


def test_plano_lido_com_superior_derivada_da_classificacao_e_sem_tipo_nem_natureza():
    resultado = ler(_plano_sintetico())

    assert not resultado.tem_erro, resultado.ocorrencias
    por_codigo = {c.codigo: c for c in resultado.contas}
    assert set(por_codigo) == {"1", "1.1", "1.1.01"}
    assert por_codigo["1"].codigo_pai is None
    assert por_codigo["1.1"].codigo_pai == "1"
    assert por_codigo["1.1.01"].codigo_pai == "1.1"
    assert por_codigo["1.1.01"].analitica is True
    assert por_codigo["1"].analitica is False
    assert all(c.tipo is None and c.natureza is None for c in resultado.contas)  # HI-87/HI-88
    assert por_codigo["1.1.01"].codigo_origem == "3"  # código reduzido, só como origem
    assert resultado.formato == "referencia"


def test_superior_e_o_maior_prefixo_existente_no_arquivo():
    """O LEITOR entrega o pai imediato e as superiores possíveis, da mais próxima para a mais
    distante. A ESCOLHA do maior prefixo existente (no arquivo OU no cadastro) é do núcleo
    (A3, coberta em `test_dl077_correcao_nucleo.py`). Aqui: o imediato é `1.1.01` e a lista
    de candidatas é `1.1.01`, `1.1`, `1`, nessa ordem, respeitando a fronteira de nível."""
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo"),
            _conta("2", "1.1", "S", "Circulante"),
            _conta("3", "1.1.01.001", "A", "Caixa"),
        )
    )

    por_codigo = {c.codigo: c for c in resultado.contas}
    assert por_codigo["1.1.01.001"].codigo_pai == "1.1.01"
    assert por_codigo["1.1.01.001"].superiores_candidatas == ("1.1.01", "1.1", "1")


def test_superior_sem_nenhum_prefixo_no_arquivo_fica_como_prefixo_imediato():
    """`1.2.03` sem `1.2` nem `1` no arquivo: a superior é `1.2`, que o núcleo confere
    contra o cadastro. Se não existir lá, o núcleo recusa; a conta não cai na raiz."""
    resultado = ler(_linhas(_cabecalho(), _conta("1", "1.2.03", "A", "Conta órfã")))

    assert resultado.contas[0].codigo_pai == "1.2"
    assert not resultado.tem_erro


def test_classificacao_sem_separador_deriva_superior_por_prefixo_com_aviso():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "11", "S", "Ativo"),
            _conta("2", "1101", "A", "Caixa"),
        )
    )

    # O leitor entrega o imediato ("110") e as candidatas; a escolha de "11" (que existe no
    # arquivo) é do núcleo (A3).
    por_codigo = {c.codigo: c for c in resultado.contas}
    assert por_codigo["1101"].codigo_pai == "110"
    assert por_codigo["1101"].superiores_candidatas == ("110", "11", "1")
    avisos = [o for o in resultado.ocorrencias if o.nivel == NIVEL_AVISO]
    assert any(o.linha == 3 and "prefixo" in o.mensagem for o in avisos)


def test_derivar_pai_sem_candidato_no_conjunto_devolve_none_para_raiz():
    assert derivar_pai("1", {"1"}) is None
    assert derivar_pai("1.1", set()) == "1"


def test_situacao_do_0200_vai_para_a_conta_e_inativa_tem_aviso():
    """Campo 7: A = ativa, I = inativa. Inativa sai com `ativa=False` e aviso; ativa, True."""
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo"),
            _conta("2", "1.1", "A", "Caixa antiga", situacao="I", inativacao="31/12/2025"),
        )
    )

    assert not resultado.tem_erro
    por_codigo = {c.codigo: c for c in resultado.contas}
    assert por_codigo["1"].ativa is True
    assert por_codigo["1.1"].ativa is False
    assert any(o.campo == "0200.7" and o.nivel == NIVEL_AVISO for o in resultado.ocorrencias)


def test_relacionamentos_do_0200_nao_guardados_geram_aviso_e_nao_entram():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo", relacionamentos=("10", "", "")),
        )
    )

    assert not resultado.tem_erro
    assert any(o.campo == "0200.9" and o.nivel == NIVEL_AVISO for o in resultado.ocorrencias)


def test_0250_vira_referencial_da_conta_que_vem_logo_antes():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo"),
            _0250("1", "R"),
        )
    )

    assert not resultado.tem_erro
    assert resultado.contas[0].referencial == "1"


@pytest.mark.parametrize(
    ("linhas", "campo"),
    [
        # 0250 sem 0200 imediatamente acima (filho do 0200)
        ([_cabecalho(), _0250("1", "R")], "0250.1"),
        # órgão fora de R e C
        ([_cabecalho(), _conta("1", "1", "S", "Ativo"), _0250("1", "X")], "0250.3"),
        # classificação referencial vazia
        ([_cabecalho(), _conta("1", "1", "S", "Ativo"), _0250("", "R")], "0250.2"),
        # segundo 0250 seguido para o mesmo 0200
        (
            [_cabecalho(), _conta("1", "1", "S", "Ativo"), _0250("1", "R"), _0250("2", "R")],
            "0250.1",
        ),
    ],
)
def test_0250_fora_do_leiaute_e_recusado_nomeado(linhas, campo):
    resultado = ler(_linhas(*linhas))

    assert any(o.campo == campo and o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)


def test_0250_com_erro_tira_a_conta_mae_e_so_um_erro_aparece():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo"),
            _0250("", "R"),
        )
    )

    assert resultado.contas == []
    erros = [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert [o.campo for o in erros] == ["0250.2"]


def test_registro_que_o_produto_nao_usa_e_contado_e_nao_descartado_em_silencio():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _registro("0220", "1", "Histórico"),
            _registro("0220", "2", "Outro histórico"),
            _conta("1", "1", "S", "Ativo"),
        )
    )

    assert resultado.registros_ignorados == {"0220": 2}
    assert not resultado.tem_erro


def test_campos_do_0200_fora_do_leiaute_sao_recusados_com_linha_e_campo():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "X", "Ativo"),  # campo 4: tipo
            _conta("2", "1.1", "S", "Sem data", data="31/02/2026"),  # campo 6: data inválida
            _conta("3x", "1.2", "S", "Código reduzido ruim"),  # campo 2: numérico
            _conta("4", "1.3", "S", ""),  # campo 5: descrição vazia
            _conta("5", "1.4", "S", "Situação ruim", situacao="Z"),  # campo 7
        )
    )

    campos = {(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO}
    assert {(2, "0200.4"), (3, "0200.6"), (4, "0200.2"), (5, "0200.5"), (6, "0200.7")} <= campos
    assert resultado.tem_erro


def test_classificacao_repetida_e_erro_na_segunda_ocorrencia():
    resultado = ler(
        _linhas(
            _cabecalho(),
            _conta("1", "1", "S", "Ativo"),
            _conta("2", "1", "S", "Ativo de novo"),
        )
    )

    erros = [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert [(o.linha, o.campo) for o in erros] == [(3, "0200.3")]
    assert len(resultado.contas) == 1


def test_linha_com_numero_de_campos_errado_e_recusada_com_contagem():
    resultado = ler(_linhas(_cabecalho(), _registro("0200", "1", "1", "S", "Ativo")))

    assert resultado.contas == []
    erro = next(o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO)
    assert erro.linha == 2 and erro.campo == "0200"
    assert "11 campos" in erro.mensagem and "a linha tem 5" in erro.mensagem


@pytest.mark.parametrize(
    ("com_inicio", "com_fim"),
    [(True, True), (False, False), (True, False), (False, True)],
    ids=["canonica_com_barras", "sem_barras", "so_inicio", "so_fim"],
)
def test_barras_nas_pontas_canonicas_sem_aviso_e_sem_barras_com_um_aviso_por_arquivo(
    com_inicio, com_fim
):
    """Forma canônica (`|` no início e no fim, do exemplo oficial do fornecedor): sem aviso.
    Qualquer outra forma é aceita, e gera UM aviso por arquivo dizendo que não é a do exemplo.
    Os quatro casos têm o mesmo resultado de conta; só o aviso muda."""

    def com_pontas(linha):
        return ("|" if com_inicio else "") + linha + ("|" if com_fim else "")

    # `[1:-1]` tira EXATAMENTE uma barra de cada ponta. `strip("|")` comeria também o `|` que
    # separa os campos vazios do fim (`A||||`), e a contagem de campos mudaria.
    arquivo = _linhas(
        com_pontas(_cabecalho()[1:-1]),
        com_pontas(_conta("1", "1", "S", "Ativo")[1:-1]),
        com_pontas(_conta("2", "1.1", "S", "Circulante")[1:-1]),
    )

    resultado = ler(arquivo)

    assert not resultado.tem_erro, resultado.ocorrencias
    assert [(c.codigo, c.codigo_pai, c.analitica) for c in resultado.contas] == [
        ("1", None, False),
        ("1.1", "1", False),
    ]
    assert resultado.documento_declarado == CNPJ
    avisos_de_formato = [o for o in resultado.ocorrencias if o.campo == "formato"]
    # Só a forma com as DUAS barras é a canônica. Ela é a única sem aviso.
    assert len(avisos_de_formato) == (0 if (com_inicio and com_fim) else 1)
    assert all(o.nivel == NIVEL_AVISO for o in avisos_de_formato)


def test_campo_vazio_no_fim_nao_e_confundido_com_barra_de_ponta():
    """`A||||` termina com `|`, mas o último `|` separa um campo vazio. A contagem literal
    de 11 campos vale; não se tira barra, e não há aviso de formato."""
    resultado = ler(_linhas(_cabecalho(), _conta("1", "1", "S", "Ativo")))

    assert not resultado.tem_erro
    assert not [o for o in resultado.ocorrencias if o.campo == "formato"]


def test_barra_so_no_inicio_com_contagem_errada_continua_sendo_erro_de_campos():
    """Tolerar a barra não apaga o erro real: sem a barra, a contagem ainda tem de bater."""
    resultado = ler(
        _linhas(_cabecalho(), "|" + _registro_sem_barras("0200", "1", "1", "S", "Ativo"))
    )

    assert resultado.contas == []
    erro = next(o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO and o.linha == 2)
    assert erro.campo == "0200" and "11 campos" in erro.mensagem


def test_identificador_de_registro_que_nao_tem_quatro_digitos_e_erro():
    resultado = ler(_linhas(_cabecalho(), "AB|1|2"))

    assert any(o.campo == "REG" and o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)


def test_arquivo_sem_registro_0000_e_erro_no_leitor():
    resultado = ler(_linhas(_conta("1", "1", "S", "Ativo")))

    assert any(o.campo == "0000" and o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)


def test_registro_0000_repetido_e_erro():
    resultado = ler(_linhas(_cabecalho(), _cabecalho(), _conta("1", "1", "S", "Ativo")))

    assert any(o.campo == "0000" and o.linha == 2 for o in resultado.ocorrencias)


@pytest.mark.parametrize("inscricao", ["12345", "1234567800019A", "123456789012"])
def test_inscricao_que_nao_e_cnpj_nem_cpf_e_erro_no_0000(inscricao):
    resultado = ler(_linhas(_cabecalho(inscricao), _conta("1", "1", "S", "Ativo")))

    assert any(o.campo == "0000.2" and o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)


def test_latin1_com_acentos_e_lido_sem_aviso():
    resultado = ler(
        _linhas(_cabecalho(), _conta("1", "1", "S", "Patrimônio líquido")),
    )

    assert resultado.codificacao == "iso-8859-1"
    assert resultado.contas[0].nome == "Patrimônio líquido"
    assert not [o for o in resultado.ocorrencias if o.campo == "codificacao"]


def test_utf8_com_acentos_e_lido_com_aviso_de_codificacao():
    texto = (_cabecalho() + "\r\n" + _conta("1", "1", "S", "Patrimônio líquido") + "\r\n").encode(
        "utf-8"
    )

    resultado = ler(texto)

    assert resultado.codificacao == "utf-8"
    assert resultado.contas[0].nome == "Patrimônio líquido"
    avisos = [o for o in resultado.ocorrencias if o.campo == "codificacao"]
    assert avisos and avisos[0].nivel == NIVEL_AVISO


# A conferência do CNPJ/CPF declarado no arquivo é do núcleo: ver
# `test_dl077_documento_declarado.py`, que cobre os dois formatos.


# -----------------------------------------------------------------------------
# Escrita
# -----------------------------------------------------------------------------


def _contas_de_exemplo():
    return [
        ContaLida(1, "1", "Ativo", None, False, None, None, None, None, True),
        ContaLida(2, "1.1", "Circulante", "1", False, None, None, None, None, True),
        ContaLida(3, "1.1.01", "Caixa geral", "1.1", True, None, None, None, None, True),
    ]


def test_escrever_sem_documento_recusa_sem_inventar_zero():
    with pytest.raises(IntercambioRecusado, match="CNPJ/CPF da empresa"):
        escrever(_contas_de_exemplo())


def test_escrever_gera_0000_e_0200_em_latin1_crlf_com_codigo_reduzido_sequencial():
    saida = escrever(_contas_de_exemplo(), documento=CNPJ_MASCARADO)

    assert saida.endswith(b"\r\n")
    linhas = saida.decode("iso-8859-1").split("\r\n")[:-1]
    # Forma canônica: `|` no início e no fim de cada registro (decisão do arquiteto, 08/10/2026).
    assert linhas[0] == "|0000|" + CNPJ + "|"  # máscara normalizada na escrita
    assert linhas[1] == "|0200|1|1|S|Ativo||A|||||"
    assert linhas[2] == "|0200|2|1.1|S|Circulante||A|||||"
    assert linhas[3] == "|0200|3|1.1.01|A|Caixa geral||A|||||"


def test_escrita_e_leitura_se_reproduzem_codigo_nome_superior_e_analitica():
    original = _contas_de_exemplo()

    lido = ler(escrever(original, documento=CNPJ))

    assert not lido.tem_erro
    trecho = [(c.codigo, c.nome, c.codigo_pai, c.analitica) for c in lido.contas]
    assert trecho == [(c.codigo, c.nome, c.codigo_pai, c.analitica) for c in original]


def test_escrever_recusa_caractere_fora_do_latin1_sem_substituir():
    contas = _contas_de_exemplo()
    contas[0] = ContaLida(1, "1", "Caixa € reservado", None, False, None, None, None, None, True)

    with pytest.raises(IntercambioRecusado, match="ISO-8859-1"):
        escrever(contas, documento=CNPJ)


def test_escrever_recusa_pipe_no_nome():
    contas = _contas_de_exemplo()
    contas[1] = ContaLida(2, "1.1", "Circulante | ruim", "1", False, None, None, None, None, True)

    with pytest.raises(IntercambioRecusado, match="'\\|'"):
        escrever(contas, documento=CNPJ)


def test_escrever_recusa_hierarquia_que_a_classificacao_nao_reproduz():
    """Raiz '10' com '1' existindo: a classificação faria '10' ser filha de '1', e o
    plano diz que é raiz. Exportar assim mudaria a estrutura na reimportação."""
    contas = [
        ContaLida(1, "1", "Ativo", None, False, None, None, None, None, True),
        ContaLida(2, "10", "Conta solta", None, True, None, None, None, None, True),
    ]

    with pytest.raises(IntercambioRecusado, match="não pode ser exportado"):
        escrever(contas, documento=CNPJ)


def test_escrever_recusa_referencial_que_o_produto_nao_guarda_o_orgao():
    contas = _contas_de_exemplo()
    contas[0] = ContaLida(1, "1", "Ativo", None, False, None, None, None, "1", True)

    with pytest.raises(IntercambioRecusado, match="órgão do plano referencial"):
        escrever(contas, documento=CNPJ)


def test_documento_invalido_na_escrita_e_recusado():
    with pytest.raises(IntercambioRecusado, match="inválido"):
        escrever(_contas_de_exemplo(), documento="123")


def test_formato_registrado_nos_leitores_e_escritores():
    assert referencia.FORMATO == "referencia"
    assert LEITORES["referencia"] is ler
    assert ESCRITORES["referencia"] is escrever


# -----------------------------------------------------------------------------
# Ida e volta com o núcleo (banco): plano de contas
# -----------------------------------------------------------------------------


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL077 Referência", cnpj="33333333000133")


def _empresa(escritorio, nome, cnpj):
    return Empresa.objects.create(escritorio=escritorio, razao_social=nome, cnpj=cnpj)


def _cadastrar_plano(empresa):
    def conta(codigo, nome, tipo, natureza, pai=None, analitica=True):
        return Conta.objects.create(
            empresa=empresa,
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            natureza=natureza,
            conta_pai=pai,
            aceita_lancamento=analitica,
        )

    ativo = conta("1", "Ativo", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False)
    circulante = conta(
        "1.1", "Circulante", TipoConta.ATIVO, NaturezaConta.DEVEDORA, ativo, analitica=False
    )
    conta("1.1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA, circulante)
    # Redutora: a natureza credora NÃO é a presumida pelo tipo. A ida e volta mostra isso.
    conta("1.2", "Depreciação acumulada", TipoConta.ATIVO, NaturezaConta.CREDORA, ativo)
    passivo = conta("2", "Passivo", TipoConta.PASSIVO, NaturezaConta.CREDORA, analitica=False)
    conta("2.1", "Fornecedores", TipoConta.PASSIVO, NaturezaConta.CREDORA, passivo)
    receitas = conta("3", "Receitas", TipoConta.RECEITA, NaturezaConta.CREDORA, analitica=False)
    conta("3.1", "Vendas", TipoConta.RECEITA, NaturezaConta.CREDORA, receitas)
    despesas = conta("4", "Despesas", TipoConta.DESPESA, NaturezaConta.DEVEDORA, analitica=False)
    conta("4.1", "Aluguel", TipoConta.DESPESA, NaturezaConta.DEVEDORA, despesas)
    pl = conta(
        "5",
        "Patrimônio líquido",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
        analitica=False,
    )
    conta("5.1", "Capital social", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA, pl)


def _fotografia(empresa):
    return {
        c.codigo: (
            c.nome,
            c.conta_pai.codigo if c.conta_pai_id else None,
            c.aceita_lancamento,
            c.tipo,
            c.natureza,
        )
        for c in Conta.objects.filter(empresa=empresa).select_related("conta_pai")
    }


def _exportar_direto(empresa):
    """Escreve o plano de `empresa` com o escritor do leiaute, direto.

    Mesmo montagem de `exportar_plano`, mas sem a API: o teste de ida e volta do leiaute
    não depende da ordenação nem dos filtros do núcleo. A exportação pela API tem o
    seu próprio teste, mais abaixo.
    """
    registros = [
        ContaLida(
            linha=0,
            codigo=c.codigo,
            nome=c.nome,
            codigo_pai=c.conta_pai.codigo if c.conta_pai_id else None,
            analitica=c.aceita_lancamento,
            tipo=c.tipo,
            natureza=c.natureza,
            codigo_origem=None,
            referencial=None,
            ativa=c.ativo,
        )
        for c in Conta.objects.filter(empresa=empresa).select_related("conta_pai")
    ]
    return escrever(sorted(registros, key=lambda r: r.codigo), documento=empresa.cnpj)


PREFIXOS = {"1": "ativo", "2": "passivo", "3": "receita", "4": "despesa", "5": "patrimonio_liquido"}


def test_ida_e_volta_em_empresa_vazia_recria_codigo_nome_superior_e_analitica_e_tipo_por_prefixo(
    escritorio,
):
    origem = _empresa(escritorio, "Origem Ltda", "44444444000144")
    outro = Escritorio.objects.create(nome="Outro escritório DL077", cnpj="77777777000177")
    destino = _empresa(outro, "Destino Ltda", CNPJ)
    _cadastrar_plano(origem)
    arquivo = _exportar_direto(origem)

    resultado = ler(arquivo)
    previa = conferir_plano(destino, resultado, "so_acrescentar", PREFIXOS)
    assert not previa.tem_erro, [(o.linha, o.campo, o.mensagem) for o in previa.ocorrencias]
    aplicar_plano(
        destino,
        previa,
        None,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )

    antes = _fotografia(origem)
    depois = _fotografia(destino)
    assert set(depois) == set(antes)
    for codigo in antes:
        nome, pai, analitica, tipo, _natureza = antes[codigo]
        assert depois[codigo][:3] == (nome, pai, analitica), codigo
        assert depois[codigo][3] == tipo, codigo


def test_natureza_so_difere_na_redutora_porque_o_leiaute_nao_a_traz_hi_88(escritorio):
    """HI-88: o leiaute não traz natureza, então a reimportação presume pelo tipo. A
    única diferença desta amostra é a redutora `1.2`, credora no original. O aviso do
    núcleo a aponta para o contador conferir."""
    origem = _empresa(escritorio, "Origem Ltda", "44444444000144")
    outro = Escritorio.objects.create(nome="Outro escritório DL077", cnpj="77777777000177")
    destino = _empresa(outro, "Destino Ltda", CNPJ)
    _cadastrar_plano(origem)

    previa = conferir_plano(destino, ler(_exportar_direto(origem)), "so_acrescentar", PREFIXOS)
    aplicar_plano(
        destino,
        previa,
        None,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )

    diferentes = {
        codigo
        for codigo, valor in _fotografia(origem).items()
        if _fotografia(destino)[codigo][4] != valor[4]
    }
    assert diferentes == {"1.2"}
    assert any(
        i.codigo == "1.2" and i.origem_natureza == "presumida_pelo_tipo" for i in previa.itens
    )


def test_reimportar_na_mesma_empresa_com_so_acrescentar_nao_cria_nem_altera_nada(escritorio):
    empresa = _empresa(escritorio, "Origem Ltda", "44444444000144")
    _cadastrar_plano(empresa)
    antes = _fotografia(empresa)

    previa = conferir_plano(empresa, ler(_exportar_direto(empresa)), "so_acrescentar", {})

    assert not previa.tem_erro, [(o.linha, o.campo, o.mensagem) for o in previa.ocorrencias]
    assert previa.contagens == {"criar": 0, "atualizar": 0, "sem_mudanca": 12, "recusada": 0}
    assert _fotografia(empresa) == antes


def test_conta_superior_fora_do_arquivo_e_do_cadastro_vira_erro_no_nucleo(escritorio):
    destino = _empresa(escritorio, "Destino Ltda", CNPJ)
    arquivo = _linhas(_cabecalho(), _conta("1", "1.2.03", "A", "Órfã"))

    previa = conferir_plano(destino, ler(arquivo), "so_acrescentar", {"1": "ativo"})

    assert previa.tem_erro
    assert any(
        o.campo == "codigo_pai" and "não está no arquivo nem no cadastro" in o.mensagem
        for o in previa.ocorrencias
    )


# -----------------------------------------------------------------------------
# API: prévia e aplicação no leiaute do sistema de referência
# -----------------------------------------------------------------------------


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório Ref A", cnpj="55555555000155")
    escritorio_b = Escritorio.objects.create(nome="Escritório Ref B", cnpj="66666666000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa Ref Ltda", cnpj=CNPJ
    )
    outra = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Outra Ref Ltda", cnpj="88888888000188"
    )
    _usuario("analista-ref", escritorio_a, Papel.ANALISTA)
    _usuario("paralegal-ref", escritorio_a, Papel.PARALEGAL)
    _usuario("gestor-b-ref", escritorio_b, Papel.GESTOR)
    return {"empresa": empresa, "outra": outra}


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


def _previa(client, empresa, conteudo, **extra):
    return client.post(
        reverse("contabilidade:plano-importacao-previa", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile("plano.txt", conteudo, content_type="text/plain"),
            "formato": "referencia",
            "prefixos": '{"1": "ativo"}',
            **extra,
        },
    )


def test_api_previa_no_leiaute_de_referencia_com_cnpj_da_empresa_aceita(client, cenario):
    _entrar(client, "analista-ref")

    resposta = _previa(client, cenario["empresa"], _plano_sintetico())

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["formato"] == "referencia"
    assert corpo["pode_aplicar"] is True
    assert corpo["contagens"]["criar"] == 3
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_api_previa_de_arquivo_de_outra_empresa_marca_erro_no_arquivo_e_aplicacao_recusa(
    client, cenario
):
    """A conferência é do núcleo: a prévia mostra o erro no nível do arquivo (linha 0), não
    responde 400. A aplicação, com o token dessa prévia, recusa com 400 e nada é gravado."""
    empresa = cenario["empresa"]
    _entrar(client, "analista-ref")
    arquivo = _linhas(_cabecalho(CNPJ_DE_OUTRA_EMPRESA), _conta("1", "1", "S", "Ativo"))

    previa = _previa(client, empresa, arquivo)

    assert previa.status_code == 200, previa.content
    corpo = previa.json()
    assert corpo["pode_aplicar"] is False
    documento = next(o for o in corpo["ocorrencias"] if o["campo"] == "documento")
    assert documento["linha"] == 0 and documento["nivel"] == "erro"
    assert CNPJ_DE_OUTRA_EMPRESA not in previa.content.decode()  # sem repetir os números

    resposta = client.post(
        reverse("contabilidade:plano-importacao-aplicar", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile("plano.txt", arquivo, content_type="text/plain"),
            "formato": "referencia",
            "sha256": corpo["sha256"],
            "assinatura": corpo["assinatura"],
        },
    )
    assert resposta.status_code == 400
    assert Conta.objects.filter(empresa=empresa).count() == 0


def test_api_previa_sem_0000_marca_erro_no_arquivo_e_nao_deixa_aplicar(client, cenario):
    _entrar(client, "analista-ref")

    corpo = _previa(client, cenario["empresa"], _linhas(_conta("1", "1", "S", "Ativo"))).json()

    assert corpo["pode_aplicar"] is False
    assert any(o["campo"] == "0000" and o["nivel"] == "erro" for o in corpo["ocorrencias"])


def test_api_aplicacao_no_leiaute_de_referencia_grava_com_o_token_da_previa(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "analista-ref")
    previa = _previa(client, empresa, _plano_sintetico()).json()

    resposta = client.post(
        reverse("contabilidade:plano-importacao-aplicar", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile(
                "plano.txt", _plano_sintetico(), content_type="text/plain"
            ),
            "formato": "referencia",
            "prefixos": '{"1": "ativo"}',
            "sha256": previa["sha256"],
            "assinatura": previa["assinatura"],
        },
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["criadas"] == 3
    assert Conta.objects.filter(empresa=empresa).count() == 3
    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.detalhes["formato"] == "referencia"


def test_api_previa_de_empresa_de_outro_escritorio_responde_404_no_leiaute_de_referencia(
    client, cenario
):
    _entrar(client, "analista-ref")

    assert _previa(client, cenario["outra"], _plano_sintetico()).status_code == 404


def _esvaziar_plano(empresa):
    """Apaga o plano por folhas, para a superior não ficar órfã (PROTECT)."""
    while Conta.objects.filter(empresa=empresa).exists():
        com_filhas = Conta.objects.filter(empresa=empresa, conta_pai__isnull=False).values(
            "conta_pai_id"
        )
        Conta.objects.filter(empresa=empresa).exclude(id__in=com_filhas).delete()


def test_api_ida_e_volta_no_leiaute_de_referencia_preserva_estrutura_e_situacao(client, cenario):
    """Exporta pela API (com CNPJ, aviso no cabeçalho e situação real), esvazia a empresa e
    reimporta o MESMO arquivo pela prévia e pela aplicação. Estrutura, analítica e tipo por
    prefixo voltam; a situação inativa volta como inativa; a natureza segue a regra de HI-88
    (ver o teste de natureza)."""
    empresa = cenario["empresa"]
    _cadastrar_plano(empresa)
    Conta.objects.filter(empresa=empresa, codigo="1.2").update(ativo=False)
    antes = _fotografia(empresa)

    _entrar(client, "paralegal-ref")
    exportado = client.get(
        reverse("contabilidade:plano-exportacao", args=[empresa.id]), {"formato": "referencia"}
    )

    assert exportado.status_code == 200, exportado.content
    assert exportado.headers["Content-Type"] == "text/plain; charset=iso-8859-1"
    assert "leiaute-com-separador" in exportado.headers["Content-Disposition"]
    assert "nao e estavel" in exportado.headers["X-DataLedger-Avisos"]
    arquivo = exportado.content
    assert arquivo.startswith(b"|0000|" + CNPJ.encode() + b"|\r\n")
    # Com as barras das pontas, o índice 0 é vazio, o REG é o 1, e a classificação é o 3.
    linhas_1_2 = [linha for linha in arquivo.split(b"\r\n") if linha.split(b"|")[3:4] == [b"1.2"]]
    assert linhas_1_2 and linhas_1_2[0].split(b"|")[7] == b"I"  # campo 7: situação real

    _esvaziar_plano(empresa)
    _entrar(client, "analista-ref")
    url = reverse("contabilidade:plano-importacao-previa", args=[empresa.id])
    previa = client.post(
        url,
        {
            "arquivo": SimpleUploadedFile("plano.txt", arquivo, content_type="text/plain"),
            "formato": "referencia",
            "prefixos": json.dumps(PREFIXOS),
        },
    )
    assert previa.status_code == 200, previa.content
    corpo = previa.json()
    assert corpo["pode_aplicar"] is True, corpo["ocorrencias"]
    assert corpo["contagens"]["criar"] == 12

    aplicacao = client.post(
        reverse("contabilidade:plano-importacao-aplicar", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile("plano.txt", arquivo, content_type="text/plain"),
            "formato": "referencia",
            "prefixos": json.dumps(PREFIXOS),
            "sha256": corpo["sha256"],
            "assinatura": corpo["assinatura"],
        },
    )
    assert aplicacao.status_code == 200, aplicacao.content
    depois = _fotografia(empresa)
    assert set(depois) == set(antes)
    for codigo in antes:
        assert depois[codigo][:4] == antes[codigo][:4], codigo  # nome, pai, analítica, tipo
    assert Conta.objects.get(empresa=empresa, codigo="1.2").ativo is False
    trilha = RegistroAuditoria.objects.filter(acao="plano_de_contas.importado").latest("id")
    assert trilha.detalhes["inativas_criadas"] == 1


@pytest.mark.parametrize("usuario", ["paralegal-ref"])
def test_api_previa_no_leiaute_de_referencia_recusa_quem_nao_escreve_o_plano(
    client, cenario, usuario
):
    """Mesma regra da frente A por formato: ler é liberado a PARALEGAL, importar não."""
    _entrar(client, usuario)

    assert _previa(client, cenario["empresa"], _plano_sintetico()).status_code == 403
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0
