import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

pytestmark = pytest.mark.django_db


def test_email_e_obrigatorio_e_unico():
    Usuario = get_user_model()
    Usuario.objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )

    with pytest.raises(IntegrityError):
        Usuario.objects.create_user(
            username="ana2", email="ana@escritorio.com.br", password="outra-senha-123"
        )


def test_str_usa_nome_completo_ou_username():
    Usuario = get_user_model()
    sem_nome = Usuario.objects.create_user(
        username="bia", email="bia@escritorio.com.br", password="senha-forte-123"
    )
    assert str(sem_nome) == "bia"

    com_nome = Usuario.objects.create_user(
        username="caio",
        email="caio@escritorio.com.br",
        password="senha-forte-123",
        first_name="Caio",
        last_name="Silva",
    )
    assert str(com_nome) == "Caio Silva"
