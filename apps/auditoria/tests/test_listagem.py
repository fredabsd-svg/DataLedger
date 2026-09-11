import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.services import registrar
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def test_papel_cliente_nao_acessa_auditoria(client):
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    _usuario_com_papel(Papel.CLIENTE, escritorio, "cliente")
    client.login(username="cliente", password="senha-forte-123")

    response = client.get(reverse("auditoria:api-lista"))

    assert response.status_code == 403


def test_administrador_ve_apenas_auditoria_do_proprio_escritorio(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    _usuario_com_papel(Papel.ADMINISTRADOR, escritorio_a, "admin_a")

    registrar(acao="teste.a", escritorio=escritorio_a)
    registrar(acao="teste.b", escritorio=escritorio_b)

    client.login(username="admin_a", password="senha-forte-123")
    response = client.get(reverse("auditoria:api-lista"))

    acoes = [item["acao"] for item in response.json()]
    assert acoes == ["teste.a"]
