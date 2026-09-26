"""Testes de ponta a ponta da API de empresas para CPF/tipo de inscrição —
DL-038.

Cobre, pela API (critérios 2, 3, 5 e parte do 9 do plano):
  - CPF válido aceito; DV errado e duplicado recusados com 400 (nunca 500).
  - CNPJ e CPF são mutuamente exclusivos, conforme `tipo_inscricao`.
  - R6: troca de modo de escrituração, com e sem movimento existente,
    inclusive a trilha de auditoria.
  - R9: cadastro pela API grava a trilha de criação/alteração como já
    acontecia para CNPJ (nenhuma regressão).

Segue o mesmo padrão de fixtures e de asserção de `test_api.py` (mesmo
arquivo de referência da etapa DL-011).
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.validators import UniqueValidator

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import Conta, TipoConta
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-dl038", email="gestor-dl038@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


# --- Critério 2: CPF válido/inválido pela API -------------------------


def test_criar_empresa_cpf_valida_via_api_e_aceita(client, gestor):
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano de Tal",
            "tipo_inscricao": "CPF",
            "cpf": "111.444.777-35",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["tipo_inscricao"] == "CPF"
    assert corpo["cpf"] == "11144477735"
    assert corpo["cnpj"] == ""
    assert Empresa.objects.filter(cpf="11144477735", tipo_inscricao=TipoInscricao.CPF).exists()


def test_criar_empresa_cpf_com_dv_invalido_e_recusado(client, gestor):
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Inválido",
            "tipo_inscricao": "CPF",
            "cpf": "11144477736",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Empresa.objects.filter(razao_social="Fulano Inválido").exists()


def test_criar_empresa_cpf_sem_cnpj_nao_exige_cnpj(client, gestor):
    # R1/R2: CPF não precisa de CNPJ nenhum — payload sem a chave "cnpj"
    # de jeito nenhum, não só vazia.
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Fulano Sem Cnpj", "tipo_inscricao": "CPF", "cpf": "11144477735"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content


def test_criar_empresa_cnpj_com_cpf_informado_e_recusado(client, gestor):
    # Mutuamente exclusivo: tipo CNPJ não pode vir com CPF preenchido.
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Empresa Mista Ltda",
            "tipo_inscricao": "CNPJ",
            "cnpj": "11122233000183",
            "cpf": "11144477735",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "cpf" in resposta.json()
    assert not Empresa.objects.filter(razao_social="Empresa Mista Ltda").exists()


def test_criar_empresa_cpf_com_cnpj_informado_e_recusado(client, gestor):
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Empresa Mista 2 Ltda",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "cnpj": "11122233000183",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "cnpj" in resposta.json()


def test_criar_empresa_sem_tipo_inscricao_continua_cnpj_por_default(client, gestor):
    # R1: cliente de API que não manda tipo_inscricao continua criando
    # empresa CNPJ exatamente como antes da DL-038 — nenhuma regressão.
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Sem Tipo Ltda", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["tipo_inscricao"] == "CNPJ"
    assert corpo["modo_escrituracao"] == "contabilidade"


# --- Critério 3: CPF duplicado é recusado com 400, nunca 500 ---------------


def test_criar_empresa_com_cpf_duplicado_e_recusado_com_400(client, gestor):
    Empresa.objects.create(
        escritorio=Escritorio.objects.get(cnpj="11111111000111"),
        razao_social="Fulano Original",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Duplicado",
            "tipo_inscricao": "CPF",
            "cpf": "111.444.777-35",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cpf"]
    assert "já existe" in mensagem
    assert Empresa.objects.filter(cpf="11144477735").count() == 1


def test_criar_empresa_com_corrida_no_cpf_neutralizando_o_unique_validator_da_400(
    client, gestor, monkeypatch
):
    # Mesma reprodução determinística de
    # test_criar_empresa_via_api_com_corrida_neutralizando_o_unique_validator_da_400
    # (test_api.py, R4 da DL-011), agora para o campo cpf: neutraliza o
    # UniqueValidator para forçar o caminho que só a corrida real
    # percorreria — o INSERT esbarra no IntegrityError da constraint do
    # banco, e `erro_de_cnpj_duplicado_como_400` tem que traduzir isso
    # para 400, nunca deixar subir como 500.
    monkeypatch.setattr(UniqueValidator, "__call__", lambda self, value, serializer_field: None)

    Empresa.objects.create(
        escritorio=Escritorio.objects.get(cnpj="11111111000111"),
        razao_social="Fulano Original",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Concorrente",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cpf"]
    assert "já existe" in mensagem
    assert Empresa.objects.filter(cpf="11144477735").count() == 1


def test_cpf_duplicado_recusado_diretamente_no_banco_nunca_500(escritorio):
    # Defesa em profundidade (camada 1 da DE-008): mesmo sem passar pela
    # API/serializer, a UniqueConstraint do banco recusa o segundo CPF
    # igual — o mesmo padrão que test_gerenciador_traduz_apenas_a_unique_de_
    # cnpj (test_services.py) já prova para CNPJ.
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Original",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Fulano Duplicado Direto",
            tipo_inscricao=TipoInscricao.CPF,
            cpf="11144477735",
            cnpj="",
        )

    assert "empresa_cpf_unico" in str(excinfo.value)


# --- R6: troca de modo de escrituração, com e sem movimento ----------------


def test_trocar_para_livro_caixa_sem_movimento_e_permitido_e_fica_na_trilha(
    client, gestor, escritorio
):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Sem Movimento Ltda", cnpj="11122233000183"
    )
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data=json.dumps({"modo_escrituracao": "livro_caixa"}),
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA
    # R9: a trilha registra a alteração, como já acontecia antes da DL-038
    # para qualquer PATCH de empresa.
    registro = RegistroAuditoria.objects.filter(
        acao="empresa.atualizada", objeto_id=str(empresa.pk)
    ).first()
    assert registro is not None
    assert registro.detalhes["valores_anteriores"]["modo_escrituracao"] == "contabilidade"
    assert registro.detalhes["valores_novos"]["modo_escrituracao"] == "livro_caixa"


def test_trocar_para_livro_caixa_com_plano_de_contas_existente_e_recusado(
    client, gestor, escritorio
):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Com Conta Ltda", cnpj="11122233000183"
    )
    Conta.objects.create(
        empresa=empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora"
    )
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data=json.dumps({"modo_escrituracao": "livro_caixa"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert "modo_escrituracao" in resposta.json()
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE


def test_trocar_de_livro_caixa_para_contabilidade_e_sempre_permitido(client, gestor, escritorio):
    # R6 só recusa a transição PARA livro-caixa com movimento — voltar de
    # livro-caixa para contabilidade nunca é bloqueado por esta regra (a
    # empresa em livro-caixa, por definição, nunca teve plano de contas
    # nem lançamento — R5 recusa a contabilidade para ela desde o início).
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Livro Caixa Ltda",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    client.login(username="gestor-dl038", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data=json.dumps({"modo_escrituracao": "contabilidade"}),
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE
