"""DL-086 (BL-585) — o Início gateia a CARTEIRA pela regra da carteira.

O bloco "Empresas da carteira" (e a fila/atalhos que o alimentam) usava
`papel_pode_ler_contabilidade` para decidir dado de CADASTRO — latente
enquanto as duas tuplas são a mesma por referência (DE-026), divergente no
dia em que "ler carteira" deixar de ser "ler contabilidade" (critério de
aceite do BL-585: "teste com as listas divergentes").

O teste cria as divergências de propósito: monkeypatch devolve papéis
DISTINTOS para as duas funções e o bloco precisa seguir a de carteira.
Mutante que derruba: voltar para `papel_pode_ler_contabilidade` no
`pode_ver_carteira` e o segundo teste inverte o resultado.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio_com_empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL-086", cnpj="11222333000181")
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Comércio DL-086 Ltda",
        tipo_inscricao=TipoInscricao.CNPJ,
        cnpj="11122233000181",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    usuario = get_user_model().objects.create_user(
        username="analista-dl086",
        email="analista-dl086@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ANALISTA
    )
    return escritorio


def _entrar(client, escritorio):
    assert client.login(username="analista-dl086", password="senha-forte-123")
    return client.get(reverse("tenancy:painel"))


def test_carteira_aparece_quando_a_regra_da_carteira_permite(monkeypatch, escritorio_com_empresa):
    # Listas DIVERGENTES de propósito: carteira permite, contabilidade não.
    monkeypatch.setattr("apps.tenancy.views.papel_pode_ler_carteira", lambda papel: True)
    monkeypatch.setattr("apps.tenancy.views.papel_pode_ler_contabilidade", lambda papel: False)
    from django.test import Client

    resposta = _entrar(Client(), escritorio_com_empresa)

    # Segue a regra da CARTEIRA (True), não a da contabilidade (False).
    assert resposta.context["empresas_da_carteira"] is not None
    assert len(resposta.context["empresas_da_carteira"]) == 1


def test_carteira_some_quando_a_regra_da_carteira_recusa(monkeypatch, escritorio_com_empresa):
    # Inverso: contabilidade permite, carteira não — o bloco não aparece.
    monkeypatch.setattr("apps.tenancy.views.papel_pode_ler_carteira", lambda papel: False)
    monkeypatch.setattr("apps.tenancy.views.papel_pode_ler_contabilidade", lambda papel: True)
    from django.test import Client

    resposta = _entrar(Client(), escritorio_com_empresa)

    assert resposta.context["empresas_da_carteira"] is None
