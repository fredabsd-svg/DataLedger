"""Achado B1 da auditoria rodada 1 (DL-038) — o admin de `Empresa` voltou a
devolver 500 para CNPJ/CPF duplicado e para `tipo_inscricao` inconsistente
com os campos preenchidos (regressão medida contra a revisão anterior à
DL-038, que dava 200 com "já existe" no campo).

Cobre os dois casos de teste propostos pela auditoria: 200 (formulário
reexibido com erro), nada gravado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


def _payload_base(escritorio):
    return {
        "escritorio": escritorio.pk,
        "nome_fantasia": "",
        "tipo_inscricao": "CNPJ",
        "cnpj": "",
        "cpf": "",
        "modo_escrituracao": "contabilidade",
        "ativo": "on",
        "estabelecimentos-TOTAL_FORMS": "0",
        "estabelecimentos-INITIAL_FORMS": "0",
        "estabelecimentos-MIN_NUM_FORMS": "0",
        "estabelecimentos-MAX_NUM_FORMS": "1000",
    }


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório Admin B1", cnpj="91100000000010")


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser(
        username="admin-b1", password="senha-forte-123", email="admin-b1@x.com.br"
    )


def test_admin_cnpj_duplicado_da_200_com_erro_no_campo_nunca_500(escritorio, superusuario):
    Empresa.objects.create(escritorio=escritorio, razao_social="Original B1", cnpj="11122233000183")
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update({"razao_social": "Duplicada B1", "cnpj": "11122233000183"})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    conteudo = resposta.content.decode()
    assert "já existe" in conteudo
    assert not Empresa.objects.filter(razao_social="Duplicada B1").exists()


def test_admin_cpf_duplicado_da_200_com_erro_no_campo_nunca_500(escritorio, superusuario):
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Original B1",
        tipo_inscricao="CPF",
        cpf="11144477735",
        cnpj="",
    )
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update(
        {
            "razao_social": "Fulano Duplicado B1",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
        }
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert "já existe" in resposta.content.decode()
    assert not Empresa.objects.filter(razao_social="Fulano Duplicado B1").exists()


def test_admin_tipo_cpf_com_cnpj_e_cpf_preenchidos_da_200_com_erro_nunca_500(
    escritorio, superusuario
):
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update(
        {
            "razao_social": "Inconsistente B1",
            "tipo_inscricao": "CPF",
            "cnpj": "99988877000161",
            "cpf": "11144477735",
        }
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert not Empresa.objects.filter(razao_social="Inconsistente B1").exists()


def test_admin_tipo_cnpj_sem_cnpj_preenchido_da_200_com_erro_nunca_500(escritorio, superusuario):
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update({"razao_social": "Sem CNPJ B1", "tipo_inscricao": "CNPJ", "cnpj": ""})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert not Empresa.objects.filter(razao_social="Sem CNPJ B1").exists()


def test_admin_criar_empresa_cnpj_valida_continua_funcionando(escritorio, superusuario):
    # Prova de que a correção não bloqueou o caminho FELIZ (CNPJ, o único
    # que o admin hoje consegue cadastrar de ponta a ponta — ver a
    # pendência conhecida abaixo): sem duplicidade, ainda grava
    # normalmente (302, redirect de sucesso).
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update({"razao_social": "Empresa Válida B1", "cnpj": "11122233000183"})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 302, resposta.content
    assert Empresa.objects.filter(razao_social="Empresa Válida B1", cnpj="11122233000183").exists()


def test_admin_criar_empresa_cpf_esbarra_na_limitacao_conhecida_do_campo_cnpj_obrigatorio(
    escritorio, superusuario
):
    # PENDÊNCIA CONHECIDA (já registrada no relatório de entrega da
    # DL-038, não é o escopo do achado B1): `Empresa.cnpj` continua SEM
    # `blank=True` no MODELO (decisão de "menor impacto" para não alterar
    # o comportamento de `EmpresaForm`/admin pré-existente) — o `ModelForm`
    # AUTOGERADO trata `cnpj` como campo OBRIGATÓRIO mesmo para
    # `tipo_inscricao=CPF`. Resultado: o admin não consegue, hoje, cadastrar
    # uma empresa CPF de ponta a ponta — sempre 200 com "Este campo é
    # obrigatório" em `cnpj`, nunca 500 (o achado B1 é só sobre 500 virar
    # 400/200; não é sobre o admin passar a oferecer CPF, que segue em
    # aberto para o arquiteto decidir). Este teste fixa o comportamento
    # ATUAL — se um dia o admin passar a oferecer CPF de verdade, este
    # teste é quem avisa que a decisão mudou.
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update(
        {"razao_social": "Fulano Pendência B1", "tipo_inscricao": "CPF", "cpf": "11144477735"}
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert "Este campo é obrigatório" in resposta.content.decode()
    assert not Empresa.objects.filter(razao_social="Fulano Pendência B1").exists()
