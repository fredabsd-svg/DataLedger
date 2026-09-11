import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    Usuario = get_user_model()

    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")

    # Usuário com vínculo aos dois escritórios: prova que o isolamento
    # depende do escritório *ativo*, não apenas do vínculo existir.
    usuario = Usuario.objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_a, papel=Papel.GESTOR
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )

    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj="44455566000183"
    )

    return {
        "usuario": usuario,
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
    }


def _ativar(client, escritorio_id):
    return client.post(
        reverse("tenancy:api-escritorio-ativo"),
        data={"escritorio_id": escritorio_id},
        content_type="application/json",
    )


def test_sem_escritorio_ativo_endpoint_nega_acesso(client, cenario):
    client.login(username="ana", password="senha-forte-123")

    response = client.get(reverse("empresas:api-lista"))

    assert response.status_code == 403


def test_usuario_so_ve_empresas_do_escritorio_ativo(client, cenario):
    client.login(username="ana", password="senha-forte-123")
    _ativar(client, cenario["escritorio_a"].id)

    response = client.get(reverse("empresas:api-lista"))

    razoes_sociais = [item["razao_social"] for item in response.json()]
    assert razoes_sociais == ["Empresa A Ltda"]

    _ativar(client, cenario["escritorio_b"].id)
    response = client.get(reverse("empresas:api-lista"))
    razoes_sociais = [item["razao_social"] for item in response.json()]
    assert razoes_sociais == ["Empresa B Ltda"]


def test_detalhe_de_empresa_de_outro_escritorio_da_404(client, cenario):
    client.login(username="ana", password="senha-forte-123")
    _ativar(client, cenario["escritorio_a"].id)

    response = client.get(reverse("empresas:api-detalhe", args=[cenario["empresa_b"].id]))

    assert response.status_code == 404


def test_criar_empresa_usa_o_escritorio_ativo_e_ignora_o_do_cliente(client, cenario):
    client.login(username="ana", password="senha-forte-123")
    _ativar(client, cenario["escritorio_a"].id)

    response = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Empresa Nova Ltda",
            "cnpj": "77788899000183",
            # Um escritorio_id aqui, se aceito, violaria o isolamento —
            # a view não usa nenhum campo desse tipo do corpo da requisição.
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    empresa_criada = Empresa.objects.get(cnpj="77788899000183")
    assert empresa_criada.escritorio_id == cenario["escritorio_a"].id
