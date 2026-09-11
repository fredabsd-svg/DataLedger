import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def duas_empresas_com_usuarios():
    Usuario = get_user_model()

    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")

    usuario_a = Usuario.objects.create_user(
        username="usuario_a", email="a@escritorio.com.br", password="senha-forte-123"
    )
    usuario_b = Usuario.objects.create_user(
        username="usuario_b", email="b@escritorio.com.br", password="senha-forte-123"
    )

    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_a, escritorio=escritorio_a, papel=Papel.GESTOR
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )

    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "usuario_a": usuario_a,
        "usuario_b": usuario_b,
    }


def test_endpoint_de_escritorios_exige_autenticacao(client):
    response = client.get(reverse("tenancy:api-escritorios"))

    assert response.status_code in (401, 403)


def test_usuario_so_ve_o_proprio_escritorio(client, duas_empresas_com_usuarios):
    client.login(username="usuario_a", password="senha-forte-123")

    response = client.get(reverse("tenancy:api-escritorios"))

    nomes = [item["nome"] for item in response.json()]
    assert nomes == ["Escritório A"]


def test_middleware_seleciona_automaticamente_escritorio_unico(client, duas_empresas_com_usuarios):
    client.login(username="usuario_a", password="senha-forte-123")

    response = client.get(reverse("tenancy:api-escritorio-ativo"))

    assert response.json()["escritorio_ativo"]["nome"] == "Escritório A"


def test_usuario_nao_consegue_ativar_escritorio_de_terceiros(client, duas_empresas_com_usuarios):
    escritorio_b = duas_empresas_com_usuarios["escritorio_b"]
    client.login(username="usuario_a", password="senha-forte-123")

    response = client.post(
        reverse("tenancy:api-escritorio-ativo"),
        data={"escritorio_id": escritorio_b.id},
        content_type="application/json",
    )

    assert response.status_code == 403


def test_painel_exige_login(client):
    response = client.get(reverse("tenancy:painel"))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_ativar_escritorio_gera_registro_de_auditoria(client, duas_empresas_com_usuarios):
    usuario_a = duas_empresas_com_usuarios["usuario_a"]
    escritorio_b = duas_empresas_com_usuarios["escritorio_b"]
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_a, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    client.login(username="usuario_a", password="senha-forte-123")

    client.post(
        reverse("tenancy:api-escritorio-ativo"),
        data={"escritorio_id": escritorio_b.id},
        content_type="application/json",
    )

    assert RegistroAuditoria.objects.filter(
        acao="escritorio.ativado", usuario=usuario_a, escritorio=escritorio_b
    ).exists()
