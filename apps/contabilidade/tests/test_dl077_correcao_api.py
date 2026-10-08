"""DL-077, fatia 1: correção única da auditoria (rodada 1), parte das PORTAS (API e tela).

Cobre, com expectativas escritas à mão:
- T7 (A7 e A10): campo de TEXTO enviado como ARQUIVO é recusado NO CAMPO, com 400, na API e
  na tela. Antes, a API respondia 500 (`.strip()` sobre `UploadedFile`) e a tela descartava o
  valor em silêncio.
- T6 (A6, porta): arquivo acima do teto de contas responde 413 na API.

Chamadas reais pelo cliente HTTP, com sessão autenticada. Dados sintéticos.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.plano import MAXIMO_DE_CONTAS_POR_IMPORTACAO
from apps.contabilidade.models import Conta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"
PLANO_VALIDO = (CABECALHO + "\r\n1;Ativo;;N;ativo;devedora\r\n1.1;Caixa;1;S;;\r\n").encode("utf-8")
MENSAGEM_DE_TEXTO = "é texto: não envie arquivo nele"


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario(client):
    escritorio = Escritorio.objects.create(nome="Escritório Correção Portas", cnpj="99999999000199")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Portas Ltda", cnpj="98989898000198"
    )
    _usuario("analista-portas", escritorio, Papel.ANALISTA)
    return {"empresa": empresa}


def _entrar(client):
    assert client.login(username="analista-portas", password=SENHA)


def _arquivo(conteudo=PLANO_VALIDO, nome="plano.txt"):
    return SimpleUploadedFile(nome, conteudo, content_type="text/plain")


def _previa_url(empresa):
    return reverse("contabilidade:plano-importacao-previa", args=[empresa.id])


def _aplicar_url(empresa):
    return reverse("contabilidade:plano-importacao-aplicar", args=[empresa.id])


def _tela_url(nome, empresa):
    return reverse(f"contabilidade_web:{nome}", args=[empresa.id])


# -----------------------------------------------------------------------------
# T7 (A7): API. Texto como arquivo = 400 no campo, nunca 500
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["formato", "politica", "prefixos"])
def test_api_previa_com_campo_de_texto_enviado_como_arquivo_responde_400_no_campo(
    client, cenario, campo
):
    _entrar(client)
    dados = {"arquivo": _arquivo(), "formato": "proprio", "politica": "so_acrescentar"}
    dados[campo] = _arquivo(b"{}" if campo == "prefixos" else b"x", nome=f"{campo}.txt")

    resposta = client.post(_previa_url(cenario["empresa"]), dados)

    assert resposta.status_code == 400, resposta.content
    assert campo in resposta.json()
    assert MENSAGEM_DE_TEXTO in resposta.json()[campo][0]


@pytest.mark.parametrize("campo", ["sha256", "assinatura", "formato"])
def test_api_aplicacao_com_campo_de_texto_como_arquivo_responde_400_e_nao_grava(
    client, cenario, campo
):
    _entrar(client)
    dados = {
        "arquivo": _arquivo(),
        "formato": "proprio",
        "sha256": "a" * 64,
        "assinatura": "b" * 64,
    }
    dados[campo] = _arquivo(b"x", nome=f"{campo}.txt")

    resposta = client.post(_aplicar_url(cenario["empresa"]), dados)

    assert resposta.status_code == 400, resposta.content
    assert campo in resposta.json()
    assert not Conta.objects.filter(empresa=cenario["empresa"]).exists()
    assert not RegistroAuditoria.objects.filter(acao="plano_de_contas.importado").exists()


# -----------------------------------------------------------------------------
# T6 (A6, porta): teto de contas responde 413 na API
# -----------------------------------------------------------------------------


def test_api_previa_acima_do_teto_de_contas_responde_413_nomeado(client, cenario):
    _entrar(client)
    linhas = [
        f"c{i};Conta {i};;S;ativo;devedora" for i in range(MAXIMO_DE_CONTAS_POR_IMPORTACAO + 1)
    ]
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")

    resposta = client.post(
        _previa_url(cenario["empresa"]), {"arquivo": _arquivo(conteudo), "formato": "proprio"}
    )

    assert resposta.status_code == 413
    assert str(MAXIMO_DE_CONTAS_POR_IMPORTACAO) in str(resposta.json())


# -----------------------------------------------------------------------------
# T7 (A10): tela. Texto como arquivo = 400 no campo, sem descarte em silêncio
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["politica", "prefixo_1", "tipo_1", "formato"])
def test_tela_previa_com_campo_de_texto_enviado_como_arquivo_responde_400_no_campo(
    client, cenario, campo
):
    _entrar(client)
    dados = {
        "arquivo": _arquivo(),
        "formato": "proprio",
        "politica": "so_acrescentar",
        "prefixo_1": "",
        "tipo_1": "",
    }
    dados[campo] = _arquivo(b"x", nome=f"{campo}.txt")

    resposta = client.post(_tela_url("plano_importar", cenario["empresa"]), dados)

    assert resposta.status_code == 400
    chave = "prefixos" if campo.startswith(("prefixo_", "tipo_")) else campo
    assert chave in resposta.context["erros"]
    assert MENSAGEM_DE_TEXTO in resposta.context["erros"][chave]
    assert MENSAGEM_DE_TEXTO in resposta.content.decode("utf-8")


def test_tela_aplicacao_com_sha256_como_arquivo_responde_400_e_nao_grava(client, cenario):
    _entrar(client)

    resposta = client.post(
        _tela_url("plano_importar_aplicar", cenario["empresa"]),
        {
            "arquivo": _arquivo(),
            "formato": "proprio",
            "politica": "so_acrescentar",
            "sha256": _arquivo(b"x", nome="sha.txt"),
            "assinatura": "b" * 64,
        },
    )

    assert resposta.status_code == 400
    assert MENSAGEM_DE_TEXTO in resposta.context["erros"]["sha256"]
    assert not Conta.objects.filter(empresa=cenario["empresa"]).exists()
