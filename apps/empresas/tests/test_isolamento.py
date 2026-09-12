import json

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


def test_atualizar_empresa_de_outro_escritorio_da_404(client, cenario):
    # C7 (auditoria de fechamento da etapa DL-011, rodada 5): test_detalhe_...
    # acima cobre o GET; PUT/PATCH nunca tinha sido exercitado contra
    # empresa de outro escritório. EmpresaDetailView.perform_update é
    # criação desta etapa (A1) — a proteção vem do mesmo get_queryset que o
    # GET já usa (EmpresaQuerySetMixin), mas isso merece teste próprio, não
    # inferência a partir do teste do GET.
    client.login(username="ana", password="senha-forte-123")
    _ativar(client, cenario["escritorio_a"].id)

    response = client.patch(
        reverse("empresas:api-detalhe", args=[cenario["empresa_b"].id]),
        data=json.dumps({"razao_social": "Tentativa de alteração indevida"}),
        content_type="application/json",
    )

    assert response.status_code == 404
    cenario["empresa_b"].refresh_from_db()
    assert cenario["empresa_b"].razao_social == "Empresa B Ltda"


def test_criar_estabelecimento_em_empresa_de_outro_escritorio_da_404(client, cenario):
    # Mesmo motivo do teste acima, para EstabelecimentoListCreateView: a
    # empresa da URL é resolvida por EmpresaEscopadaMixin.get_empresa(),
    # escopada ao escritório ativo — POST de estabelecimento numa empresa
    # de outro escritório deve dar 404, nunca criar o estabelecimento lá.
    client.login(username="ana", password="senha-forte-123")
    _ativar(client, cenario["escritorio_a"].id)

    response = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": cenario["empresa_b"].id}),
        data={"tipo": "matriz", "nome": "Matriz Indevida", "cnpj": "34028316000103"},
        content_type="application/json",
    )

    assert response.status_code == 404
    assert not cenario["empresa_b"].estabelecimentos.exists()


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
