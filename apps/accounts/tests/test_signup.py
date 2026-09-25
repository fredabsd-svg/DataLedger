from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.tenancy.models import ConviteEscritorio, Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def dados():
    return {
        "nome": "Pessoa de Teste",
        "email": "novo@example.com",
        "nome_escritorio": "Escritório Novo",
        "cnpj": "12.345.678/0001-95",
        "password1": "UmaSenha!Forte987",
        "password2": "UmaSenha!Forte987",
    }


def test_visitante_tem_landing_e_cadastro(client):
    assert client.get("/").status_code == 200
    assert client.get(reverse("cadastro")).status_code == 200
    assert client.get(reverse("tenancy:api-escritorios")).status_code in (401, 403)


def test_cadastro_cria_ambiente_isolado_e_login_funciona(client, dados):
    outro = Escritorio.objects.create(nome="Outro", cnpj="11222333000181")
    response = client.post(reverse("cadastro"), dados)
    assert response.status_code == 302
    usuario = get_user_model().objects.get(email=dados["email"])
    assert usuario.check_password(dados["password1"])
    assert not usuario.is_staff and not usuario.is_superuser
    vinculo = usuario.vinculos.get()
    assert vinculo.papel == Papel.ADMINISTRADOR
    assert vinculo.escritorio.cnpj == "12345678000195"
    assert vinculo.escritorio_id != outro.pk
    assert client.session["escritorio_id"] == vinculo.escritorio_id
    assert RegistroAuditoria.objects.filter(
        usuario=usuario, escritorio=vinculo.escritorio, acao="escritorio.criado_por_bootstrap"
    ).exists()
    assert client.get("/").templates[0].name == "tenancy/painel.html"
    client.logout()
    assert client.login(username=dados["email"], password=dados["password1"])


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("nome", "   "),
        ("nome_escritorio", " "),
        ("email", "invalido"),
        ("cnpj", "00000000000000"),
        ("password1", "123"),
        ("password2", "diferente"),
        ("email", "a" * 145 + "@example.com"),
    ],
)
def test_dados_invalidos_nao_persistem(client, dados, campo, valor):
    dados[campo] = valor
    response = client.post(reverse("cadastro"), dados)
    assert response.status_code == 400
    assert campo in response.context["form"].errors
    assert not get_user_model().objects.exists()
    assert not Escritorio.objects.exists()


def test_normaliza_email_e_impede_duplicata_sem_associar(client, dados):
    dados["email"] = "NOVO@EXAMPLE.COM"
    assert client.post(reverse("cadastro"), dados).status_code == 302
    client.logout()
    dados["email"] = "novo@example.com"
    dados["cnpj"] = "11222333000181"
    assert client.post(reverse("cadastro"), dados).status_code == 400
    assert get_user_model().objects.count() == 1
    assert Escritorio.objects.count() == 1


def test_cnpj_existente_nao_cria_usuario(client, dados):
    Escritorio.objects.create(nome="Existente", cnpj="12345678000195")
    assert client.post(reverse("cadastro"), dados).status_code == 400
    assert not get_user_model().objects.exists()


def test_falha_auditoria_desfaz_todo_cadastro(client, dados):
    with patch("apps.tenancy.services.primeiro_acesso.registrar", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            client.post(reverse("cadastro"), dados)
    assert not get_user_model().objects.exists()
    assert not Escritorio.objects.exists()
    assert not VinculoUsuarioEscritorio.objects.exists()
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("extra", [{"is_superuser": "1"}, {"escritorio_id": "1"}])
def test_recusa_campos_nao_contratados(client, dados, extra):
    assert client.post(reverse("cadastro"), dados | extra).status_code == 400
    assert not get_user_model().objects.exists()


def test_cadastro_exige_csrf(dados):
    client = Client(enforce_csrf_checks=True)
    assert client.post(reverse("cadastro"), dados).status_code == 403
    assert not get_user_model().objects.exists()


def test_conta_nova_nao_descobre_convite_por_email(client, dados):
    administrador = get_user_model().objects.create_user(
        username="admin", email="admin@example.com"
    )
    escritorio = Escritorio.objects.create(nome="Privado", cnpj="11222333000181")
    convite = ConviteEscritorio.objects.create(
        email=dados["email"],
        escritorio=escritorio,
        emitido_por=administrador,
    )
    response = client.post(reverse("cadastro"), dados, follow=True)
    usuario = get_user_model().objects.get(email=dados["email"])
    assert not usuario.vinculos.filter(escritorio=escritorio).exists()
    assert convite.token not in response.content.decode()
    convite.refresh_from_db()
    assert convite.consumido_por is None


def test_usuario_autenticado_nao_cria_nova_conta(client, dados):
    usuario = get_user_model().objects.create_user(username="legado", email="legado@example.com")
    client.force_login(usuario)
    assert client.post(reverse("cadastro"), dados).status_code == 302
    assert get_user_model().objects.count() == 1
    assert not Escritorio.objects.exists()


def test_cnpj_alfanumerico_normalizado(client, dados):
    dados["cnpj"] = "ab.123.cde/0001-55"
    assert client.post(reverse("cadastro"), dados).status_code == 302
    assert Escritorio.objects.get().cnpj == "AB123CDE000155"


def test_concorrencia_duplicada_nao_deixa_usuario_orfao(client, dados):
    from django.db import IntegrityError

    with patch(
        "apps.accounts.views.criar_primeiro_escritorio_e_vinculo_admin", side_effect=IntegrityError
    ):
        assert client.post(reverse("cadastro"), dados).status_code == 400
    assert not get_user_model().objects.exists()
    assert not Escritorio.objects.exists()


@pytest.mark.parametrize("modo", ["query", "arquivo", "header"])
def test_recusa_outros_dicionarios(client, dados, modo):
    from django.core.files.uploadedfile import SimpleUploadedFile

    url = reverse("cadastro")
    headers = {}
    if modo == "query":
        url += "?escritorio_id=1"
    elif modo == "arquivo":
        dados["anexo"] = SimpleUploadedFile("arquivo.txt", b"nao aceito")
    else:
        headers["HTTP_IDEMPOTENCY_KEY"] = "nao-aceito"
    assert client.post(url, dados, **headers).status_code == 400
    assert not get_user_model().objects.exists()


def test_login_email_aceita_caixa_original(client, dados):
    dados["email"] = "Novo@Example.COM"
    assert client.post(reverse("cadastro"), dados).status_code == 302
    client.logout()
    response = client.post(
        reverse("login"),
        {
            "username": dados["email"],
            "password": dados["password1"],
        },
    )
    assert response.status_code == 302
    assert "_auth_user_id" in client.session


def test_login_legado_exato_prevalece(client):
    Usuario = get_user_model()
    Usuario.objects.create_user(
        username="Novo@Example.COM", email="legado@example.com", password="SenhaLegada987!"
    )
    Usuario.objects.create_user(
        username="novo@example.com", email="novo@example.com", password="OutraSenha987!"
    )
    response = client.post(
        reverse("login"),
        {
            "username": "Novo@Example.COM",
            "password": "SenhaLegada987!",
        },
    )
    assert response.status_code == 302
    assert Usuario.objects.get(pk=client.session["_auth_user_id"]).email == "legado@example.com"
