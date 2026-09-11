import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    Usuario = get_user_model()
    return Usuario.objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )


def test_login_com_credenciais_validas_redireciona(client, usuario):
    response = client.post(
        reverse("login"),
        {"username": "ana", "password": "senha-forte-123"},
    )

    assert response.status_code == 302


def test_login_com_credenciais_invalidas_mostra_erro(client, usuario):
    response = client.post(
        reverse("login"),
        {"username": "ana", "password": "senha-errada"},
    )

    assert response.status_code == 200
    assert response.context["form"].errors
