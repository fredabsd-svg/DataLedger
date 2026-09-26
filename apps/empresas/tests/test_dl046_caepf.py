"""DL-046, RC-129/HI-31: CAEPF (Cadastro de Atividade Econômica da Pessoa
Física) — campo opcional no cadastro de cliente pessoa física.

Fonte (consultada em 2026-09-26): documentação oficial do Cadastro
Compartilhado da Receita Federal (SERPRO) — 14 posições (9 do CPF + 5 do
número resumido de inscrição), SEM algoritmo de dígito verificador
documentado. Por isso a validação aqui é só de FORMATO (14 dígitos) e de
COERÊNCIA estrutural com o CPF do titular (os 9 primeiros dígitos batem) —
nunca um DV inventado (HI-31, requisitos.md).
"""

import json

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.validators import normalizar_caepf, validar_caepf
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_VALIDO = "12345678909"
CAEPF_COERENTE = "12345678900001"  # 9 primeiros dígitos == CPF_VALIDO[:9]
CAEPF_INCOERENTE = "99999999900001"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório CAEPF", cnpj="91100000000070")


# ---------------------------------------------------------------------------
# Validador puro
# ---------------------------------------------------------------------------


def test_validar_caepf_aceita_14_digitos():
    validar_caepf(CAEPF_COERENTE)  # não levanta


def test_validar_caepf_recusa_tamanho_errado():
    with pytest.raises(ValidationError):
        validar_caepf("123456789")


def test_validar_caepf_recusa_nao_numerico_apos_normalizar():
    with pytest.raises(ValidationError):
        validar_caepf("abcdefghijklmn")


def test_normalizar_caepf_remove_mascara():
    assert normalizar_caepf("123.456.789-00001") == CAEPF_COERENTE.replace("00001", "") + "00001"


def test_validar_caepf_recusa_incoerencia_com_cpf():
    with pytest.raises(ValidationError):
        validar_caepf(CAEPF_INCOERENTE, cpf=CPF_VALIDO)


def test_validar_caepf_aceita_coerencia_com_cpf():
    validar_caepf(CAEPF_COERENTE, cpf=CPF_VALIDO)  # não levanta


# ---------------------------------------------------------------------------
# Modelo — Empresa.clean() / CheckConstraint
# ---------------------------------------------------------------------------


def test_empresa_cpf_com_caepf_coerente_e_aceita(escritorio):
    # `exclude=["cnpj"]`: `Empresa.cnpj` não tem `blank=True` de propósito
    # (obrigatoriedade de FORMULÁRIO pré-existente à DL-046 — comentário em
    # `models.py` sobre EmpresaForm/admin ainda não conhecerem
    # `tipo_inscricao`); não é a regra sob teste aqui.
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano CAEPF",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
        caepf=CAEPF_COERENTE,
    )
    empresa.full_clean(exclude=["cnpj"])
    empresa.save()
    assert empresa.pk is not None


def test_empresa_cpf_com_caepf_incoerente_e_recusada(escritorio):
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano CAEPF Incoerente",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
        caepf=CAEPF_INCOERENTE,
    )
    with pytest.raises(ValidationError) as excinfo:
        empresa.full_clean(exclude=["cnpj"])
    assert "caepf" in excinfo.value.message_dict or "__all__" in excinfo.value.message_dict


def test_empresa_caepf_e_opcional(escritorio):
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano Sem CAEPF",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
    )
    empresa.full_clean(exclude=["cnpj"])
    empresa.save()
    assert empresa.caepf == ""


def test_constraint_recusa_caepf_para_empresa_cnpj_no_banco(escritorio):
    # Bypassa `full_clean()` de propósito (mesmo padrão de
    # test_dl076_b8_modo_escrituracao_constraint.py): a CheckConstraint é a
    # camada que sobrevive a bulk_create/gravação direta pelo ORM, sem
    # passar por `clean()`.
    with pytest.raises(IntegrityError, match="empresa_caepf_so_para_cpf_com_formato_valido"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio,
                razao_social="Empresa CNPJ CAEPF Direto",
                tipo_inscricao=TipoInscricao.CNPJ,
                cnpj="11122233000183",
                caepf=CAEPF_COERENTE,
            )


def test_constraint_recusa_caepf_com_formato_invalido_no_banco(escritorio):
    with pytest.raises(IntegrityError, match="empresa_caepf_so_para_cpf_com_formato_valido"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio,
                razao_social="Empresa CPF CAEPF Curto Demais",
                tipo_inscricao=TipoInscricao.CPF,
                cpf=CPF_VALIDO,
                caepf="123",
            )


def test_constraint_aceita_caepf_vazio_para_cpf(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa CPF Sem CAEPF Direto",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
    )
    assert empresa.caepf == ""


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _usuario_gestor(escritorio, username):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def test_api_cria_empresa_cpf_com_caepf_coerente(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-ok")
    client.login(username="gestor-caepf-ok", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Fulano CAEPF API",
                "tipo_inscricao": "CPF",
                "cpf": CPF_VALIDO,
                "caepf": CAEPF_COERENTE,
                "modo_escrituracao": "livro_caixa",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.get(cpf=CPF_VALIDO).caepf == CAEPF_COERENTE


def test_api_recusa_caepf_incoerente_com_cpf(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-incoerente")
    client.login(username="gestor-caepf-incoerente", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Fulano CAEPF Incoerente API",
                "tipo_inscricao": "CPF",
                "cpf": CPF_VALIDO,
                "caepf": CAEPF_INCOERENTE,
                "modo_escrituracao": "livro_caixa",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert "caepf" in resposta.json()


def test_api_recusa_caepf_para_empresa_cnpj(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-cnpj")
    client.login(username="gestor-caepf-cnpj", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Empresa CNPJ CAEPF API",
                "tipo_inscricao": "CNPJ",
                "cnpj": "11122233000183",
                "caepf": CAEPF_COERENTE,
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert "caepf" in resposta.json()
