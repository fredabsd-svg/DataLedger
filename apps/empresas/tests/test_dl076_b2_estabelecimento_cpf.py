"""Achado B2 da auditoria rodada 1 (DL-038, R7): estabelecimento é conceito
de pessoa jurídica — não pode existir para empresa CPF, nem a API deve
oferecer isso, nem a troca de CNPJ->CPF deve ser aceita com estabelecimento
já gravado.

Cobre os dois casos de teste propostos pela auditoria (API cria
estabelecimento para empresa CPF -> 400; PATCH de PJ com filial para CPF ->
400), mais o `clean()` do modelo (defesa de admin) e a prova de que a
identificação fiscal não vincula por estabelecimento de empresa CPF (não
tem como haver estabelecimento de empresa CPF, dado que a criação já é
recusada — provado indiretamente).
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento, TipoInscricao
from apps.empresas.services import (
    EstabelecimentoParaEmpresaCPF,
    recusar_estabelecimento_para_empresa_cpf,
    recusar_transicao_para_cpf_com_estabelecimento,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório B2", cnpj="91100000000020")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-b2", email="gestor-b2@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def empresa_cpf(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano B2",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )


@pytest.fixture
def empresa_cnpj_com_filial(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B2 Ltda", cnpj="11122233000183"
    )
    Estabelecimento.objects.create(
        empresa=empresa, tipo=TipoEstabelecimento.FILIAL, nome="Filial B2", cnpj="AB123CDE000155"
    )
    return empresa


# --- Serviço, isolado -------------------------------------------------


def test_recusar_estabelecimento_para_empresa_cpf_levanta_para_cpf(empresa_cpf):
    with pytest.raises(EstabelecimentoParaEmpresaCPF):
        recusar_estabelecimento_para_empresa_cpf(empresa_cpf)


def test_recusar_estabelecimento_para_empresa_cpf_nao_levanta_para_cnpj(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ B2 Ltda", cnpj="11122233000183"
    )
    recusar_estabelecimento_para_empresa_cpf(empresa)  # não levanta


def test_transicao_para_cpf_com_estabelecimento_e_recusada(empresa_cnpj_com_filial):
    with pytest.raises(EstabelecimentoParaEmpresaCPF, match="estabelecimento"):
        recusar_transicao_para_cpf_com_estabelecimento(
            empresa_cnpj_com_filial, tipo_anterior=TipoInscricao.CNPJ, tipo_novo=TipoInscricao.CPF
        )


def test_transicao_para_cpf_sem_estabelecimento_e_permitida(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Sem Filial B2 Ltda", cnpj="11122233000183"
    )
    recusar_transicao_para_cpf_com_estabelecimento(
        empresa, tipo_anterior=TipoInscricao.CNPJ, tipo_novo=TipoInscricao.CPF
    )  # não levanta


def test_transicao_que_nao_e_para_cpf_nunca_e_examinada(empresa_cnpj_com_filial):
    # Voltar de CPF para CNPJ (ou não mudar) nunca aciona esta regra, mesmo
    # com estabelecimento — só a transição PARA CPF importa.
    recusar_transicao_para_cpf_com_estabelecimento(
        empresa_cnpj_com_filial, tipo_anterior=TipoInscricao.CPF, tipo_novo=TipoInscricao.CNPJ
    )
    recusar_transicao_para_cpf_com_estabelecimento(
        empresa_cnpj_com_filial, tipo_anterior=TipoInscricao.CNPJ, tipo_novo=TipoInscricao.CNPJ
    )


# --- Model.clean() (admin, DE-008) -----------------------------------


def test_estabelecimento_clean_recusa_para_empresa_cpf(empresa_cpf):
    estabelecimento = Estabelecimento(
        empresa=empresa_cpf, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz", cnpj="11122233000183"
    )
    with pytest.raises(ValidationError):
        estabelecimento.clean()


def test_empresa_clean_recusa_transicao_para_cpf_com_estabelecimento(empresa_cnpj_com_filial):
    # Achado N18 da reconferência (BL-529, DL-039): os testes acima
    # (`test_transicao_para_cpf_com_estabelecimento_e_recusada`) chamam
    # `recusar_transicao_para_cpf_com_estabelecimento` DIRETO, sem nunca
    # passar por `Empresa.clean()` — uma mutação que removesse a CHAMADA
    # dentro de `Empresa.clean()` (deixando a função do serviço intacta)
    # sobrevivia à suíte inteira. Este teste chama `clean()` no MODELO
    # diretamente (não `full_clean()`, que também dispara `clean_fields()`
    # — a obrigatoriedade de `cnpj` é OUTRA checagem, de FORMULÁRIO, fora
    # do escopo deste teste) — é a segunda camada de defesa (DE-008) que
    # `Empresa.clean()` promete, testada isoladamente.
    empresa_cnpj_com_filial.tipo_inscricao = TipoInscricao.CPF
    empresa_cnpj_com_filial.cnpj = ""
    empresa_cnpj_com_filial.cpf = "11144477735"
    with pytest.raises(ValidationError, match="estabelecimento"):
        empresa_cnpj_com_filial.clean()


def test_empresa_clean_permite_transicao_para_cpf_sem_estabelecimento(escritorio):
    # Controle negativo do teste acima: a MESMA transição, sem
    # estabelecimento gravado, tem que continuar permitida por `clean()`
    # — senão o teste positivo poderia estar recusando qualquer transição
    # para CPF, não especificamente a com filial.
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Sem Filial N18 Ltda", cnpj="11122233000183"
    )
    empresa.tipo_inscricao = TipoInscricao.CPF
    empresa.cnpj = ""
    empresa.cpf = "22255588846"
    empresa.clean()  # não levanta


# --- API: criar estabelecimento para empresa CPF -> 400 --------------


def test_api_cria_estabelecimento_para_empresa_cpf_e_recusado(client, gestor, empresa_cpf):
    client.login(username="gestor-b2", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa_cpf.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not Estabelecimento.objects.filter(empresa=empresa_cpf).exists()


def test_api_cria_estabelecimento_para_empresa_cnpj_continua_funcionando(
    client, gestor, escritorio
):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B2 Feliz Ltda", cnpj="11122233000183"
    )
    client.login(username="gestor-b2", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": "34028316000103"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Estabelecimento.objects.filter(empresa=empresa).exists()


# --- API: PATCH de PJ com filial para CPF -> 400 ----------------------


def test_api_patch_de_pj_com_filial_para_cpf_e_recusado(client, gestor, empresa_cnpj_com_filial):
    client.login(username="gestor-b2", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa_cnpj_com_filial.pk}),
        data=json.dumps({"tipo_inscricao": "CPF", "cpf": "11144477735", "cnpj": ""}),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    empresa_cnpj_com_filial.refresh_from_db()
    assert empresa_cnpj_com_filial.tipo_inscricao == TipoInscricao.CNPJ
    assert empresa_cnpj_com_filial.estabelecimentos.exists()


def test_api_patch_de_pj_sem_filial_para_cpf_e_aceito(client, gestor, escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B2 Sem Filial Ltda", cnpj="11122233000183"
    )
    client.login(username="gestor-b2", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data=json.dumps({"tipo_inscricao": "CPF", "cpf": "11144477735", "cnpj": ""}),
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.tipo_inscricao == TipoInscricao.CPF
