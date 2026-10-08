"""DL-070 (BL-649, frente B): a trilha não faz consulta por linha.

Contrato (plano DL-070, critério 6): `GET /api/auditoria/` faz número de
consultas CONSTANTE em relação à quantidade de registros com usuários
distintos, e o campo `usuario` continua sendo o texto de `str(usuario)`.
Antes, `RegistroAuditoriaSerializer.usuario` (StringRelatedField) buscava o
usuário de cada registro em uma consulta própria. A paginação continua fora
desta etapa: a resposta segue sendo a lista completa do escritório.

Dados sintéticos: usuários e escritórios fictícios.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.auditoria.services import registrar
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL070 trilha", cnpj="55555555000155")


@pytest.fixture
def administrador(escritorio, client):
    usuario = get_user_model().objects.create_user(
        username="admin-trilha-dl070", email="admin-trilha-dl070@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ADMINISTRADOR
    )
    assert client.login(username="admin-trilha-dl070", password=SENHA)
    return usuario


def _usuario(username, **campos):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA, **campos
    )


def _consultas_e_corpo(client, url):
    with CaptureQueriesContext(connection) as contexto:
        resposta = client.get(url)
    assert resposta.status_code == 200, resposta.content
    return len(contexto.captured_queries), resposta.json()


def test_trilha_faz_o_mesmo_numero_de_consultas_com_2_e_com_20_usuarios(
    client, escritorio, administrador
):
    url = reverse("auditoria:api-lista")
    # Aquecimento: a primeira requisição depois do login grava a sessão (custo
    # fixo, não por linha). Medir depois dele compara só o que cresce por registro.
    client.get(url)
    for indice in range(1, 3):
        registrar(
            acao=f"teste.dl070.{indice:02d}",
            escritorio=escritorio,
            usuario=_usuario(f"autor-{indice:02d}"),
        )
    consultas_com_2, corpo_com_2 = _consultas_e_corpo(client, url)

    for indice in range(3, 21):
        registrar(
            acao=f"teste.dl070.{indice:02d}",
            escritorio=escritorio,
            usuario=_usuario(f"autor-{indice:02d}"),
        )
    consultas_com_20, corpo_com_20 = _consultas_e_corpo(client, url)

    assert len(corpo_com_2) == 2
    assert len(corpo_com_20) == 20
    assert consultas_com_20 == consultas_com_2, (
        f"consultas por linha: {consultas_com_2} com 2 usuários, {consultas_com_20} com 20"
    )


def test_campo_usuario_e_o_texto_de_antes_e_outro_escritorio_nao_aparece(
    client, escritorio, administrador
):
    autora = _usuario("autora-dl070", first_name="Autora", last_name="Sintética")
    registrar(acao="teste.dl070.propria", escritorio=escritorio, usuario=autora)

    outro = Escritorio.objects.create(nome="Escritório DL070 outro", cnpj="66666666000166")
    registrar(
        acao="teste.dl070.outro",
        escritorio=outro,
        usuario=_usuario("autor-outro-dl070"),
    )

    _, corpo = _consultas_e_corpo(client, reverse("auditoria:api-lista"))
    acoes = [item["acao"] for item in corpo]

    # `str(Usuario)` é `get_full_name()` ou `username`: o texto exato é o de antes.
    registro_proprio = next(item for item in corpo if item["acao"] == "teste.dl070.propria")
    assert registro_proprio["usuario"] == "Autora Sintética"
    assert "teste.dl070.outro" not in acoes
