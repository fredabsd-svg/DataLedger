"""Correção única da auditoria das fatias 2 e 3 (DL-077, rodada 1): API e TELAS da importação.

Chamadas reais pelo cliente HTTP, com sessão autenticada. Dados SINTÉTICOS (CNPJ de exemplo, plano
do cenário de exportação). Cada teste nomeia o achado (A1 a A12) ou a lacuna (M26, M58).
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    EstadoImportacaoLancamentos,
    ImportacaoLancamentos,
    LancamentoContabil,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db

CABECALHO = "numero;data;historico;conta;lado;valor\r\n"


def _proprio(*linhas):
    return (CABECALHO + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _par(
    numero, data="2026-03-10", historico="Compra", conta_d="1.1.1", conta_c="2.1", valor="100.00"
):
    return [
        f"{numero};{data};{historico};{conta_d};D;{valor}",
        f"{numero};{data};{historico};{conta_c};C;{valor}",
    ]


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


@pytest.fixture
def cenario(client):
    escritorio = criar_escritorio("Escritório Correção Telas", "22222222000122")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Telas", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    _usuario("gestor-corr", escritorio, Papel.GESTOR)
    _usuario("cliente-corr", escritorio, Papel.CLIENTE)
    return {"empresa": empresa, "contas": contas}


def _receber(empresa, *linhas, nome="lanc.txt"):
    return servico.receber(
        empresa=empresa,
        formato="proprio",
        conteudo=_proprio(*linhas),
        nome_arquivo=nome,
        usuario=None,
    )


def _url_tela(nome, empresa, *args):
    return reverse(f"contabilidade_web:{nome}", args=[empresa.id, *args])


def _url_api(nome, empresa, *args):
    return reverse(f"contabilidade:{nome}", args=[empresa.id, *args])


def _aceitar_o_arquivo_pela_tela(client, empresa, importacao):
    resposta = client.post(
        _url_tela("lancamentos_importacao_avisos", empresa, importacao.id),
        {"aceitar_arquivo": "1"},
    )
    assert resposta.status_code == 302, resposta.content.decode()


# --- A1 na tela: só-válidos indisponível com o erro do arquivo listado ------------------------


def test_t_a1_tela_so_validos_fica_indisponivel_e_lista_o_erro_do_arquivo(client, cenario):
    """A1: com o erro do arquivo inteiro, a política só-válidos não é oferecida; o erro aparece."""
    empresa = cenario["empresa"]
    importacao = servico.receber(
        empresa=empresa,
        formato="ecd",
        conteudo=(
            "|0000|LECD|01032026|31032026|Empresa|1234567800019|SP|||\r\n"
            "|I200|1|10032026|100,00|N||\r\n"
            "|I250|1.1.1||100,00|D|||Compra||\r\n"
            "|I250|2.1||100,00|C|||Compra||\r\n"
        ).encode("iso-8859-1"),
        nome_arquivo="ecd.txt",
        usuario=None,
    )
    _entrar(client, "gestor-corr")

    html = client.get(_url_tela("lancamentos_importacao", empresa, importacao.id)).content.decode()

    assert 'value="so_validos"' not in html, "a tela ofereceu só-válidos com erro do arquivo"
    assert "Não é possível efetivar só os válidos" in html
    assert "erro do arquivo inteiro" in html
    assert "CNPJ do registro 0000" in html


# --- A2: byte nulo recusado pela API e pela tela, sem 500 e sem gravar -----------------------


BYTE_NULO = [
    pytest.param(_proprio(*_par(1, historico="Com\x00nulo")), id="historico"),
    pytest.param(_proprio(*_par(1)) + b"\x00", id="fim-do-arquivo"),
    pytest.param(
        _proprio("1;2026-03-10;Compra;1.1.1;D;100\x00.00", "1;2026-03-10;Compra;2.1;C;100.00"),
        id="valor",
    ),
]


@pytest.mark.parametrize("conteudo", BYTE_NULO)
def test_t_a2_api_recusa_byte_nulo_com_400_e_nada_gravado(client, cenario, conteudo):
    """A2 (API): byte nulo é 400 com mensagem nomeada. Antes era HTTP 500."""
    _entrar(client, "gestor-corr")

    resposta = client.post(
        _url_api("lancamentos-importacao", cenario["empresa"]),
        {"formato": "proprio", "arquivo": SimpleUploadedFile("a.txt", conteudo)},
    )

    assert resposta.status_code == 400, resposta.content[:300]
    assert "byte nulo" in str(resposta.json())
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


@pytest.mark.parametrize("conteudo", BYTE_NULO)
def test_t_a2_tela_recusa_byte_nulo_com_400_e_nada_gravado(client, cenario, conteudo):
    """A2 (tela): o mesmo arquivo, pela tela de envio: 400 e a mensagem nomeada, sem 500."""
    _entrar(client, "gestor-corr")

    resposta = client.post(
        _url_tela("lancamentos_importar", cenario["empresa"]),
        {"formato": "proprio", "arquivo": SimpleUploadedFile("a.txt", conteudo)},
    )

    assert resposta.status_code == 400
    assert "byte nulo" in resposta.content.decode()
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


# --- A7 na tela: gravado e lido, e a frase no singular ------------------------------------------


def test_t_a7_tela_mostra_o_gravado_e_o_lido_e_a_frase_no_singular(client, cenario):
    """A7: a efetivação só-válidos mostra a soma gravada e a lida, e 'lançamento', no singular."""
    empresa = cenario["empresa"]
    importacao = _receber(
        empresa,
        *_par(1, valor="100.00"),
        "2;2026-03-10;Ruim;9.9;D;200.00",
        "2;2026-03-10;Ruim;2.1;C;200.00",
    )
    _entrar(client, "gestor-corr")
    _aceitar_o_arquivo_pela_tela(client, empresa, importacao)

    resposta = client.post(
        _url_tela("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "so_validos", "confirmar": "sim"},
        follow=True,
    )

    html = resposta.content.decode()
    assert "Efetivada: 1 lançamento gravado no Diário." in html
    assert "1 lançamentos gravados" not in html
    assert "Gravado no Diário: débitos 100,00, créditos 100,00." in html
    assert "Lido do arquivo: débitos 300,00, créditos 300,00." in html


# --- A8: lista da API sem as ocorrências; detalhe com o total -----------------------------------


def test_t_a8_lista_da_api_nao_traz_ocorrencias_e_o_tamanho_fica_pequeno(client, cenario):
    """A8: 3.000 linhas inválidas. A lista não traz as ocorrências, e a resposta fica pequena."""
    empresa = cenario["empresa"]
    _receber(empresa, *[f"x{n};2026-03-10;Lixo;1.1.1;D;1.00" for n in range(3000)])
    _entrar(client, "gestor-corr")

    resposta = client.get(_url_api("lancamentos-importacao", empresa))

    assert resposta.status_code == 200
    item = resposta.json()["importacoes"][0]
    assert "ocorrencias_do_arquivo" not in item
    assert len(resposta.content) < 100_000, len(resposta.content)


def test_t_a8_detalhe_da_api_traz_no_maximo_500_e_o_total(client, cenario):
    """A8: o detalhe traz até 500 ocorrências e o total real: o contador vê o que não coube."""
    empresa = cenario["empresa"]
    importacao = _receber(empresa, *[f"x{n};2026-03-10;Lixo;1.1.1;D;1.00" for n in range(600)])
    _entrar(client, "gestor-corr")

    resposta = client.get(_url_api("lancamentos-importacao-detalhe", empresa, importacao.id))

    corpo = resposta.json()["importacao"]
    assert corpo["quantidade_ocorrencias_do_arquivo"] == 601
    assert len(corpo["ocorrencias_do_arquivo"]) == 500


# --- A11: aceite do aviso do arquivo, pela API e pela tela ------------------------------------


def test_t_a11_tela_sem_empresa_mostra_o_aceite_e_bloqueia_a_efetivacao(client, cenario):
    """A11 (tela): o formulário de aceite aparece; sem ele, nenhuma política grava."""
    empresa = cenario["empresa"]
    importacao = _receber(empresa, *_par(1))
    _entrar(client, "gestor-corr")

    html = client.get(_url_tela("lancamentos_importacao", empresa, importacao.id)).content.decode()
    assert "Confirmo que o arquivo é desta empresa" in html
    assert 'value="tudo_ou_nada"' not in html

    recusa = client.post(
        _url_tela("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "tudo_ou_nada", "confirmar": "sim"},
    )
    assert recusa.status_code == 400
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()

    _aceitar_o_arquivo_pela_tela(client, empresa, importacao)
    ok = client.post(
        _url_tela("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "tudo_ou_nada", "confirmar": "sim"},
    )
    assert ok.status_code == 302
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1


def test_t_a11_api_aceitar_arquivo_so_aceita_booleano(client, cenario):
    """A11 (API): `aceitar_arquivo` é true ou false; outro tipo é 400 e não aceita nada."""
    empresa = cenario["empresa"]
    importacao = _receber(empresa, *_par(1))
    _entrar(client, "gestor-corr")
    url = _url_api("lancamentos-importacao-avisos", empresa, importacao.id)

    ruim = client.post(
        url,
        data=json.dumps({"numeros": [], "aceitar_arquivo": "sim"}),
        content_type="application/json",
    )
    bom = client.post(
        url,
        data=json.dumps({"numeros": [], "aceitar_arquivo": True}),
        content_type="application/json",
    )

    assert ruim.status_code == 400
    assert bom.status_code == 200
    importacao.refresh_from_db()
    assert importacao.aceite_do_arquivo is True


# --- M26 e M58: contratos e prefixo reservado, na API -------------------------------------------


@pytest.mark.parametrize("chave", ["IMPORTACAO:x:1", "Importacao:x:1"])
def test_m26_rota_de_lancamento_manual_recusa_o_prefixo_em_qualquer_caixa(client, cenario, chave):
    """M26: `importacao:` é reservado em qualquer caixa. Antes só a minúscula era testada."""
    _entrar(client, "gestor-corr")
    contas = cenario["contas"]

    resposta = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2026-03-10",
            "historico": "Forjado",
            "itens": [
                {"conta": contas["1.1.1"].id, "tipo": "debito", "valor": "10.00"},
                {"conta": contas["2.1"].id, "tipo": "credito", "valor": "10.00"},
            ],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=chave,
    )

    assert resposta.status_code == 400
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()


def test_m58_envio_da_api_com_campo_extra_e_400_e_nada_gravado(client, cenario):
    """M58: `empresa` no corpo do envio não é contrato. Recusa com 400, e não grava."""
    _entrar(client, "gestor-corr")

    resposta = client.post(
        _url_api("lancamentos-importacao", cenario["empresa"]),
        {
            "formato": "proprio",
            "empresa": "999",
            "arquivo": SimpleUploadedFile("a.txt", _proprio(*_par(1))),
        },
    )

    assert resposta.status_code == 400
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_m58_envio_da_tela_com_campo_extra_e_400_e_nada_gravado(client, cenario):
    """M58 (tela): o mesmo campo extra, pela tela de envio: 400 e nada gravado."""
    _entrar(client, "gestor-corr")

    resposta = client.post(
        _url_tela("lancamentos_importar", cenario["empresa"]),
        {
            "formato": "proprio",
            "empresa": "999",
            "arquivo": SimpleUploadedFile("a.txt", _proprio(*_par(1))),
        },
    )

    assert resposta.status_code == 400
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_recebimento_de_arquivo_em_conferencia_nao_muda_o_diario(client, cenario):
    """Regressão: receber e conferir não grava nada no Diário (só a efetivação grava)."""
    _entrar(client, "gestor-corr")
    _receber(cenario["empresa"], *_par(1))

    importacao = ImportacaoLancamentos.objects.get(empresa=cenario["empresa"])
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()
