"""DL-074 (frente B) — data de abertura no CNPJ no formulário WEB de empresa.

O formulário de cadastro (`EmpresaForm`, tela `empresas:criar`) passa a oferecer o campo,
com o validador do modelo (não futura) e um texto curto sobre por que importa: o início de
atividade do Simples é a abertura do CNPJ (Res. CGSN 140, art. 2º, V). Não há tela web de
EDIÇÃO de empresa no produto hoje; a edição é a API (PATCH), já coberta por
test_dl074_data_abertura.py.

Dados 100% sintéticos (CNPJ de teste, nomes fictícios).
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CNPJ = "11122233000183"
SENHA = "senha-forte-123"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL074 Form", cnpj="91100000000075")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-dl074-form", email="gestor-dl074-form@x.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def _dados(**sobrescritas):
    dados = {
        "razao_social": "Abertura Form Sintética Ltda",
        "tipo_inscricao": "CNPJ",
        "cnpj": CNPJ,
        "data_abertura_cnpj": "",
    }
    dados.update(sobrescritas)
    return dados


def test_formulario_web_oferece_o_campo_com_o_motivo(client, gestor):
    client.force_login(gestor)

    resposta = client.get(reverse("empresas:criar"))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'name="data_abertura_cnpj"' in html
    assert "data de abertura no cnpj" in html.lower()
    # O texto curto diz por que importa, com o dispositivo (sem alíquota).
    assert "Res. CGSN 140, art. 2º, V" in html
    assert "sem ela o RBT12 não é apurado" in html


def test_formulario_web_grava_a_data_de_abertura_em_dd_mm_aaaa(client, gestor):
    client.force_login(gestor)

    resposta = client.post(reverse("empresas:criar"), data=_dados(data_abertura_cnpj="10/03/2015"))

    assert resposta.status_code == 302
    assert Empresa.objects.get(cnpj=CNPJ).data_abertura_cnpj.isoformat() == "2015-03-10"


def test_formulario_web_aceita_a_data_vazia_como_opcional(client, gestor):
    client.force_login(gestor)

    resposta = client.post(reverse("empresas:criar"), data=_dados())

    assert resposta.status_code == 302
    assert Empresa.objects.get(cnpj=CNPJ).data_abertura_cnpj is None


def test_formulario_web_recusa_data_futura_sem_gravar(client, gestor):
    client.force_login(gestor)
    futura = timezone.localdate() + timedelta(days=5)

    resposta = client.post(
        reverse("empresas:criar"),
        data=_dados(data_abertura_cnpj=futura.strftime("%d/%m/%Y")),
    )

    assert resposta.status_code == 200
    assert "não pode ser futura" in resposta.content.decode()
    assert not Empresa.objects.filter(cnpj=CNPJ).exists()


def test_formulario_direto_usa_o_validador_do_modelo():
    futura = timezone.localdate() + timedelta(days=1)

    formulario = EmpresaForm(data=_dados(data_abertura_cnpj=futura.isoformat()))

    assert not formulario.is_valid()
    assert "data_abertura_cnpj" in formulario.errors
    assert "não pode ser futura" in formulario.errors["data_abertura_cnpj"][0]


def test_formulario_direto_aceita_data_de_hoje_e_de_dez_anos_atras():
    hoje = timezone.localdate()

    assert EmpresaForm(data=_dados(data_abertura_cnpj=hoje.isoformat())).is_valid()
    assert EmpresaForm(
        data=_dados(data_abertura_cnpj=(hoje - timedelta(days=3650)).isoformat())
    ).is_valid()
