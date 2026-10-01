import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


def test_papel_cliente_nao_pode_criar_empresa(client, escritorio):
    _usuario_com_papel(Papel.CLIENTE, escritorio, "cliente")
    client.login(username="cliente", password="senha-forte-123")

    response = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Nova Ltda", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert not Empresa.objects.exists()


def test_papel_gestor_pode_criar_empresa_e_gera_auditoria(client, escritorio):
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Nova Ltda", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert response.status_code == 201
    empresa = Empresa.objects.get(cnpj="11122233000183")
    assert RegistroAuditoria.objects.filter(
        acao="empresa.criada", objeto_tipo="Empresa", objeto_id=str(empresa.pk)
    ).exists()


def test_papel_cliente_nao_lista_empresas(client, escritorio):
    # DL-055 (DE-020 §4): antes, o CLIENTE listava a carteira inteira do
    # escritório (200). Matriz completa em test_dl055_cliente_nao_ve_carteira.py.
    Empresa.objects.create(escritorio=escritorio, razao_social="Empresa A", cnpj="11122233000183")
    _usuario_com_papel(Papel.CLIENTE, escritorio, "cliente")
    client.login(username="cliente", password="senha-forte-123")

    response = client.get(reverse("empresas:api-lista"))

    assert response.status_code == 403
    assert "Empresa A" not in response.content.decode()
    assert "11122233000183" not in response.content.decode()
