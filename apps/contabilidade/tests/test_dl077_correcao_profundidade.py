"""DL-077, reconferência da fatia 1 (2026-10-08): profundidade da hierarquia (R1, A8, N30).

- T-R1: cadeia de 1.200 contas no CADASTRO, criada por ORM. A exportação nos três formatos
  responde 200 ou 400 com mensagem. O cliente de teste re-levanta exceção, então um
  `RecursionError` aparece como falha, e não como 500 silencioso.
- T-R1 (importação): a conta que pendura sob uma cadeia já cadastrada de 61 contas passa do
  limite de 50 superiores e é recusada com erro nomeado. Sob 50 superiores, é aceita.
- A ordem de saída da exportação (`_ordenar_em_arvore`, agora iterativa) é a pré-ordem que a
  recursão dava.
- A8: um ciclo em `_altura_da_cadeia` termina em tempo limitado. O teste roda a função numa
  thread com `join(timeout)`; se ela não terminar, falha (sem plugin de timeout).
- N30: o limite é 50, e a fixação é literal: cadeia de 51 contas aceita, de 52 recusada.

Dados sintéticos. Nenhum arquivo de cliente real.
"""

import threading
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.intercambio.canonico import NIVEL_ERRO, ContaLida
from apps.contabilidade.intercambio.formatos import ecd
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import (
    MAXIMO_DE_NIVEIS_DE_SUPERIOR,
    _Conferencia,
    _ordenar_em_arvore,
    conferir_plano,
    exportar_plano,
)
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"
SENHA = "senha-forte-123"
PROFUNDIDADE_DO_T_R1 = 1200
LIMITE_DO_TESTE_DE_CICLO_S = 5.0


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(
        nome="Escritório DL077 Profundidade", cnpj="33333333000133"
    )
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL077 Profundidade Ltda", cnpj="22233344000138"
    )


def _proprio(*linhas):
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")
    return ler_arquivo("proprio", conteudo, nome_arquivo="plano-profundidade.txt")


def _cadeia_no_cadastro(empresa, quantidade):
    """`quantidade` contas no cadastro, cada uma filha da anterior: c0 é a raiz.

    Liga pelo `conta_pai_id`, não pelo objeto. Com o objeto, o Django mantém a cadeia inteira
    em cache de instâncias, e ao desalocá-la o `ModelState.__del__` do Django 6.1 estoura a
    recursão (a exceção é engolida pelo interpretador, mas polui a saída do teste). O cadastro
    gravado é o mesmo.
    """
    superior_id = None
    for indice in range(quantidade):
        superior_id = Conta.objects.create(
            empresa=empresa,
            codigo=f"c{indice}",
            nome=f"Nível {indice}",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
            aceita_lancamento=False,
            conta_pai_id=superior_id,
        ).pk


def _cadeia_de_contas(total):
    """Um arquivo com `total` contas em cadeia, a folha PRIMEIRO. c0 é a raiz."""
    linhas = [f"c{i};Nível {i};c{i - 1};N;;" for i in range(total - 1, 0, -1)]
    linhas.append("c0;Raiz;;N;ativo;devedora")
    return linhas


def _erros_de_profundidade(previa):
    return [
        o.mensagem
        for o in previa.ocorrencias
        if o.nivel == NIVEL_ERRO and "passa de 50 níveis" in o.mensagem
    ]


# -----------------------------------------------------------------------------
# T-R1: cadeia acumulada no cadastro, exportação
# -----------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("formato", ["proprio", "ecd", "referencia"])
def test_exportacao_de_cadeia_de_1200_no_cadastro_nao_levanta_recursion_error(
    client, empresa, formato
):
    _cadeia_no_cadastro(empresa, PROFUNDIDADE_DO_T_R1)
    escritorio = empresa.escritorio
    usuario = get_user_model().objects.create_user(
        username="analista-profundidade",
        email="analista-profundidade@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ANALISTA
    )
    assert client.login(username="analista-profundidade", password=SENHA)
    parametros = {"formato": formato}
    if formato == "ecd":
        parametros["data_alteracao"] = "2026-01-31"

    resposta = client.get(reverse("contabilidade:plano-exportacao", args=[empresa.id]), parametros)

    assert resposta.status_code in (200, 400), resposta.content[:300]
    if resposta.status_code == 400:
        assert resposta.json(), "a recusa de exportação precisa dizer o motivo"


@pytest.mark.django_db
def test_exportar_plano_de_1200_niveis_devolve_todas_as_contas(empresa):
    _cadeia_no_cadastro(empresa, PROFUNDIDADE_DO_T_R1)

    arquivo = exportar_plano(empresa=empresa, formato="proprio")

    assert arquivo.quantidade_contas == PROFUNDIDADE_DO_T_R1


def _conta_lida(codigo, pai):
    return ContaLida(
        linha=0,
        codigo=codigo,
        nome=codigo,
        codigo_pai=pai,
        analitica=False,
        tipo="ativo",
        natureza="devedora",
        codigo_origem=None,
        referencial=None,
    )


def test_ordem_de_saida_e_a_pre_ordem_da_arvore_com_irmas_por_codigo():
    """r tem as filhas b e a (fora de ordem na entrada); a tem a2; b tem b1. A pré-ordem com
    irmãs por código é r, a, a2, b, b1. A versão iterativa tem de dar o mesmo."""
    contas = [
        _conta_lida("b1", "b"),
        _conta_lida("b", "r"),
        _conta_lida("a2", "a"),
        _conta_lida("r", None),
        _conta_lida("a", "r"),
    ]

    saida = _ordenar_em_arvore(contas)

    assert [c.codigo for c in saida] == ["r", "a", "a2", "b", "b1"]


def test_ordem_de_saida_de_cadeia_de_1200_sai_da_raiz_para_a_folha_sem_recursao():
    cadeia = [_conta_lida(f"c{i}", None if i == 0 else f"c{i - 1}") for i in range(1200)]

    saida = _ordenar_em_arvore(list(reversed(cadeia)))

    assert [c.codigo for c in saida] == [f"c{i}" for i in range(1200)]


# -----------------------------------------------------------------------------
# T-R1: importação que levaria a mais de 50 níveis totais
# -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_importacao_sob_cadeia_de_61_contas_cadastradas_e_recusada_com_erro_nomeado(empresa):
    """c60 já cadastrada tem 60 superiores. A conta nova sob ela tem 61: passa do limite."""
    _cadeia_no_cadastro(empresa, 61)

    previa = conferir_plano(empresa, _proprio("filha;Filha;c60;S;;"), "so_acrescentar", {})

    assert previa.tem_erro
    assert _erros_de_profundidade(previa), [o.mensagem for o in previa.ocorrencias]


@pytest.mark.django_db
def test_importacao_sob_50_niveis_do_cadastro_e_aceita(empresa):
    """c49 cadastrada tem 49 superiores. A conta nova sob ela tem 50: está no limite, aceita."""
    _cadeia_no_cadastro(empresa, 50)

    previa = conferir_plano(empresa, _proprio("filha;Filha;c49;S;;"), "so_acrescentar", {})

    assert not previa.tem_erro, [o.mensagem for o in previa.ocorrencias]


# -----------------------------------------------------------------------------
# A8: ciclo em _altura_da_cadeia termina em tempo limitado
# -----------------------------------------------------------------------------


def test_altura_da_cadeia_com_ciclo_no_arquivo_termina_em_tempo_limitado():
    """a -> b -> a. Sem as guardas de `visitados` e de limite, o laço gira para sempre. Sem
    plugin de timeout: a função roda numa thread, e a espera é limitada."""
    resultado = _proprio("a;A;b;S;ativo;devedora", "b;B;a;S;ativo;devedora")
    conferencia = _Conferencia(resultado, {}, "so_acrescentar", {})
    saida = {}

    def rodar():
        saida["altura"] = conferencia._altura_da_cadeia("a")

    fio = threading.Thread(target=rodar, daemon=True)
    fio.start()
    fio.join(timeout=LIMITE_DO_TESTE_DE_CICLO_S)

    assert not fio.is_alive(), "o laço de _altura_da_cadeia não terminou (ciclo sem guarda)"
    assert saida["altura"] == 1


# -----------------------------------------------------------------------------
# N30: o limite é 50, fixado por valor literal
# -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_limite_de_niveis_e_50_com_cadeias_literais_de_51_aceita_e_52_recusada(empresa):
    assert MAXIMO_DE_NIVEIS_DE_SUPERIOR == 50

    aceita = conferir_plano(empresa, _proprio(*_cadeia_de_contas(51)), "so_acrescentar", {})
    recusada = conferir_plano(empresa, _proprio(*_cadeia_de_contas(52)), "so_acrescentar", {})

    assert len(aceita.itens) == 51
    assert not aceita.tem_erro, [o.mensagem for o in aceita.ocorrencias]
    assert len(recusada.itens) == 52
    assert _erros_de_profundidade(recusada)


def test_escrita_ecd_de_cadeia_de_1200_na_ordem_inversa_nao_levanta_recursion_error():
    """Caminho que a exportação não percorre: `escrever` do ECD recebe a lista como vier. A
    exportação entrega em pré-ordem, então a recursão de `nivel_de` nunca passaria de dois
    quadros por ali. Aqui a folha vem PRIMEIRO: a versão recursiva teria 1.200 quadros, e a
    iterativa calcula o nível de cada conta. O NIVEL da folha é 1.200 e o da raiz é 1."""
    cadeia = [_conta_lida(f"c{i}", None if i == 0 else f"c{i - 1}") for i in range(1200)]

    conteudo = ecd.escrever(list(reversed(cadeia)), data_alteracao=date(2026, 1, 31))

    linhas = conteudo.decode("iso-8859-1").split("\r\n")
    i050 = [linha for linha in linhas if linha.startswith("|I050|")]
    assert len(i050) == 1200
    assert i050[0].split("|")[5] == "1200", i050[0]
    assert i050[-1].split("|")[5] == "1", i050[-1]
