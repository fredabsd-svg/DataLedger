"""DL-038, critério 7 — a listagem de empresas não quebra com empresa CPF
na base, e a view já calcula `rotulo_inscricao`/`inscricao_formatada`
corretamente para cada tipo (mesmo antes de `templates/empresas/lista.html`
passar a usá-los — troca de template é escopo do `especialista-frontend`,
etapa 2 do plano; ver o comentário em `apps.empresas.views.lista_empresas`).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.views import _mascara_cpf
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def test_mascara_cpf_formata_com_pontuacao():
    assert _mascara_cpf("11144477735") == "111.444.777-35"


def test_mascara_cpf_com_tamanho_errado_devolve_original():
    assert _mascara_cpf("123") == "123"


def test_lista_empresas_com_empresa_cpf_nao_quebra(client, escritorio):
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ Ltda", cnpj="11122233000183"
    )
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    assert resposta.status_code == 200


def test_lista_empresas_calcula_rotulo_e_inscricao_formatada_por_tipo(client, escritorio):
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ Ltda", cnpj="11122233000183"
    )
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    empresas = {e.razao_social: e for e in resposta.context["empresas"]}
    assert empresas["Empresa CNPJ Ltda"].rotulo_inscricao == "CNPJ"
    assert empresas["Empresa CNPJ Ltda"].inscricao_formatada == "11.122.233/0001-83"
    assert empresas["Fulano de Tal"].rotulo_inscricao == "CPF"
    assert empresas["Fulano de Tal"].inscricao_formatada == "111.444.777-35"
