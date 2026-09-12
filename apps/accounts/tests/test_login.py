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


def test_login_com_credenciais_invalidas_anuncia_erro_para_leitor_de_tela(client, usuario):
    """Critério 9, sem teste antes do achado A4: o erro de login precisa ser
    anunciado (role="alert") e associado aos dois campos — sem isso, quem
    usa leitor de tela não sabe que a tentativa falhou."""
    resposta = client.post(
        reverse("login"),
        {"username": "ana", "password": "senha-errada"},
    )

    conteudo = resposta.content.decode()
    assert 'id="erro-login"' in conteudo
    assert 'role="alert"' in conteudo
    assert 'aria-describedby="erro-login"' in conteudo
    assert conteudo.count('aria-describedby="erro-login"') == 2  # usuário e senha
