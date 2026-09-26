"""Achado B5 da auditoria rodada 1 (DL-038): HI-23 (nova empresa CPF SUGERE
o modo livro-caixa quando o modo não é informado) divergia entre tela e
API — o mesmo pedido "CPF sem modo" dava `livro_caixa` pela tela e
`contabilidade` pela API. Prova de convergência: o serviço compartilhado
(`apps.empresas.services.modo_escrituracao_sugerido`) e o caminho real da
API (agora usando essa função).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.empresas.services import modo_escrituracao_sugerido
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def test_modo_sugerido_e_livro_caixa_para_cpf():
    assert modo_escrituracao_sugerido(TipoInscricao.CPF) == ModoEscrituracao.LIVRO_CAIXA


def test_modo_sugerido_e_contabilidade_para_cnpj():
    assert modo_escrituracao_sugerido(TipoInscricao.CNPJ) == ModoEscrituracao.CONTABILIDADE


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório B5", cnpj="91100000000040")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-b5", email="gestor-b5@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def test_api_cria_empresa_cpf_sem_modo_sugere_livro_caixa(client, gestor):
    # Achado B5: ANTES da correção, este pedido dava "contabilidade" pela
    # API — divergindo da tela, que já sugeria "livro_caixa".
    client.login(username="gestor-b5", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Fulano B5", "tipo_inscricao": "CPF", "cpf": "11144477735"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["modo_escrituracao"] == "livro_caixa"
    empresa = Empresa.objects.get(razao_social="Fulano B5")
    assert empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA


def test_api_cria_empresa_cnpj_sem_modo_continua_sugerindo_contabilidade(client, gestor):
    # R1: nenhuma regressão para o caso CNPJ — cliente que não manda nem
    # tipo_inscricao nem modo_escrituracao continua com o comportamento
    # de antes da DL-038.
    client.login(username="gestor-b5", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa B5 Ltda", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["modo_escrituracao"] == "contabilidade"


def test_api_cria_empresa_cpf_com_modo_explicito_nao_e_sobrescrito(client, gestor):
    # A sugestão nunca pisa numa escolha EXPLÍCITA do cliente, mesmo que
    # ele escolha o "oposto" da sugestão.
    client.login(username="gestor-b5", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Explícito B5",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "modo_escrituracao": "contabilidade",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["modo_escrituracao"] == "contabilidade"


def test_api_patch_omitindo_modo_nao_aciona_a_sugestao_preserva_valor_atual(
    client, gestor, escritorio
):
    # PATCH parcial que omite modo_escrituracao NUNCA deve reabrir a
    # sugestão de criação — semântica de atualização parcial: campo
    # omitido não muda.
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Patch B5",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    client.login(username="gestor-b5", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data='{"nome_fantasia": "Novo nome"}',
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE
