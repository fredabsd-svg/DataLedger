import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )


def test_login_com_sucesso_gera_registro_de_auditoria(client, usuario):
    client.post(reverse("login"), {"username": "ana", "password": "senha-forte-123"})

    assert RegistroAuditoria.objects.filter(acao="login.sucesso", usuario=usuario).exists()


def test_login_com_falha_gera_registro_de_auditoria_sem_senha(client, usuario):
    client.post(reverse("login"), {"username": "ana", "password": "senha-errada"})

    registro = RegistroAuditoria.objects.get(acao="login.falha")
    assert registro.usuario is None
    assert registro.detalhes == {"username": "ana"}
    assert "senha-errada" not in str(registro.detalhes)
