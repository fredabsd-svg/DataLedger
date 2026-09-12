"""Testes de ponta a ponta da API de empresas/estabelecimentos para CNPJ.

Cobre o achado 2 (alta) da auditoria da etapa DL-011: o CharField gerado
automaticamente pelo ModelSerializer herda max_length=14 do model (o CNPJ já
canonizado), então um CNPJ mascarado — até 18 caracteres — era recusado pelo
MaxLengthValidator antes de normalizar_cnpj tirar a máscara. EmpresaSerializer
e EstabelecimentoSerializer agora normalizam em to_internal_value, antes da
validação de campo do DRF. Testado aqui via requisição HTTP real (não só
chamando a função de validação isolada), porque foi assim que a auditoria
reproduziu o defeito.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor", email="gestor@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def test_criar_empresa_via_api_com_cnpj_mascarado_e_aceito_e_gravado_canonico(client, gestor):
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Mascarada Ltda", "cnpj": "11.122.233/0001-83"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="11122233000183").exists()
    # A resposta também deve devolver o valor canônico, não o que foi
    # enviado, para o cliente da API não ficar com uma ideia errada do que
    # foi persistido.
    assert resposta.json()["cnpj"] == "11122233000183"


def test_criar_empresa_via_api_com_cnpj_alfanumerico_mascarado_e_minusculo_e_aceito(client, gestor):
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Alfanumérica Ltda", "cnpj": "ab.123.cde/0001-55"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="AB123CDE000155").exists()
    assert resposta.json()["cnpj"] == "AB123CDE000155"


def test_criar_empresa_via_api_com_cnpj_com_dv_invalido_e_recusado(client, gestor):
    # A normalização não pode enfraquecer a validação: continua recusando
    # DV incorreto, agora sobre o valor já canonizado.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Invalida Ltda", "cnpj": "11.122.233/0001-84"},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Empresa.objects.filter(razao_social="Empresa Invalida Ltda").exists()


def test_criar_empresa_via_api_com_cnpj_mascarado_e_espacos_na_borda_e_aceito(client, gestor):
    # Ajuste 1 (reauditoria da etapa DL-011): CNPJ colado de planilha vem
    # com espaço, com frequência. O caminho da tela já aceitava (CharField
    # de formulário tem strip=True por padrão); o caminho da API recusava,
    # porque _normalizar_cnpj_do_payload rodava antes do trim_whitespace do
    # DRF. Este teste é de ponta a ponta (POST real), não só unitário.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Com Espaco Ltda", "cnpj": " 11.222.333/0001-81 "},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="11222333000181").exists()
    assert resposta.json()["cnpj"] == "11222333000181"


def test_criar_estabelecimento_via_api_com_cnpj_mascarado_e_aceito(client, gestor, escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": "11.122.233/0001-83"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert empresa.estabelecimentos.filter(cnpj="11122233000183").exists()
