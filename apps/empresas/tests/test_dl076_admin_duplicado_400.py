"""Achado B1 da auditoria rodada 1 (DL-038) — o admin de `Empresa` voltou a
devolver 500 para CNPJ/CPF duplicado e para `tipo_inscricao` inconsistente
com os campos preenchidos (regressão medida contra a revisão anterior à
DL-038, que dava 200 com "já existe" no campo).

Cobre os dois casos de teste propostos pela auditoria: 200 (formulário
reexibido com erro), nada gravado.

Achado N4 da reconferência (BL-529, DL-039): os testes do fim deste
arquivo cobrem a correção de uma limitação relacionada, mas distinta —
antes dela, o admin não criava NEM editava empresa CPF (sempre "Este
campo é obrigatório" em `cnpj`). O teste-marcador que fixava essa
limitação como comportamento ATUAL foi substituído pelos testes do
comportamento CORRETO (criar e editar empresa CPF com sucesso).
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


def test_admin_cria_empresa_cpf_com_sucesso(escritorio, superusuario):
    # Achado N4 da reconferência (BL-529, DL-039): ANTES desta correção, o
    # admin não conseguia cadastrar uma empresa CPF de ponta a ponta —
    # sempre 200 com "Este campo é obrigatório" em `cnpj`, porque
    # `Meta.fields = "__all__"` herdava `required=True` do campo do
    # MODELO. `EmpresaAdminForm.__init__` agora chama a MESMA função que
    # `EmpresaForm` (tela) já usa — `ajustar_obrigatoriedade_de_cnpj_cpf`
    # — e `cnpj` deixa de ser obrigatório quando `tipo_inscricao=CPF`.
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update({"razao_social": "Fulano CPF B1", "tipo_inscricao": "CPF", "cpf": "11144477735"})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 302, resposta.content
    empresa = Empresa.objects.get(razao_social="Fulano CPF B1")
    assert empresa.tipo_inscricao == "CPF"
    assert empresa.cpf == "11144477735"
    assert empresa.cnpj == ""


def test_admin_edita_empresa_cpf_existente_sem_preencher_cnpj_continua_funcionando(
    escritorio, superusuario
):
    # A mesma limitação bloqueava EDIÇÃO, não só criação — uma empresa CPF
    # cadastrada por qualquer outra porta (API, ORM direto) não podia ser
    # salva de novo pelo admin sem antes preencher `cnpj` (que não faz
    # sentido para ela). Este teste cobre o `change`, não o `add`.
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano CPF Edição B1",
        tipo_inscricao="CPF",
        cpf="22255588846",
        cnpj="",
    )
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update(
        {
            "razao_social": "Fulano CPF Edição B1 (atualizado)",
            "tipo_inscricao": "CPF",
            "cpf": "22255588846",
        }
    )
    resposta = client.post(
        reverse("admin:empresas_empresa_change", args=[empresa.pk]), data=payload
    )

    assert resposta.status_code == 302, resposta.content
    empresa.refresh_from_db()
    assert empresa.razao_social == "Fulano CPF Edição B1 (atualizado)"
    assert empresa.cnpj == ""


def test_admin_tipo_cpf_ainda_recusa_cnpj_preenchido_junto(escritorio, superusuario):
    # Controle: tornar `cnpj` OPCIONAL para tipo CPF não pode virar "o
    # admin aceita os dois campos preenchidos" — essa checagem
    # (`erros_de_consistencia_de_inscricao`, achado B1) continua intacta.
    client = Client()
    client.login(username="admin-b1", password="senha-forte-123")

    payload = _payload_base(escritorio)
    payload.update(
        {
            "razao_social": "Fulano CPF Com CNPJ B1",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "cnpj": "99988877000161",
        }
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert not Empresa.objects.filter(razao_social="Fulano CPF Com CNPJ B1").exists()
