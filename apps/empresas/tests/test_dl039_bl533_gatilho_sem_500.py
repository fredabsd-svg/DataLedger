"""Achado D1 da auditoria DL-039 rodada 1 (BL-533): quando o gatilho de
banco (migração 0010/0011) dispara, admin e API respondiam **500** — o
`RAISE EXCEPTION` não informava `CONSTRAINT`, então `apps.core.restricoes.
restricao_como_400` não tinha como traduzir a `IntegrityError` crua.

Três casos, exatamente como o relatório propôs:

1. Admin, caminho COMUM (sem corrida): criar empresa CPF com um
   estabelecimento no MESMO POST, pelo inline. Fechado por
   `EstabelecimentoInlineFormSet.clean()` (apps/empresas/admin.py) — 200
   de verdade, formulário reexibido com erro, nada gravado.
2. API, JANELA DE CORRIDA simulada: `POST api-estabelecimentos` para uma
   empresa CPF, com a checagem em Python (`recusar_estabelecimento_para_
   empresa_cpf`) neutralizada — como aconteceria se outra transação
   tivesse mudado a empresa para CPF ENTRE a checagem e o INSERT. Fechado
   por `mensagens_de_gatilho("estabelecimento_empresa_nao_e_cpf")` em
   `EstabelecimentoListCreateView.perform_create` — 400, nada gravado.
3. API, JANELA DE CORRIDA simulada: `PATCH api-detalhe` de PJ com filial
   para CPF, com `recusar_transicao_para_cpf_com_estabelecimento`
   neutralizada. Fechado por `mensagens_de_gatilho("empresa_transicao_
   cpf_com_estabelecimento")` em `EmpresaDetailView.perform_update` — 400,
   nada gravado.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.empresas import serializers as empresas_serializers
from apps.empresas import views as empresas_views
from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento, TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _payload_admin_base(escritorio):
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
    return Escritorio.objects.create(nome="Escritório BL-533", cnpj="91100000000080")


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser(
        username="admin-bl533", password="senha-forte-123", email="admin-bl533@x.com.br"
    )


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-bl533", email="gestor-bl533@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def empresa_cpf(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano BL-533",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )


@pytest.fixture
def empresa_cnpj_com_filial(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-533 Ltda", cnpj="11122233000183"
    )
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial BL-533",
        cnpj="AB123CDE000155",
    )
    return empresa


# --- Caso 1: admin, inline no mesmo POST -------------------------------


def test_admin_cria_empresa_cpf_com_estabelecimento_no_inline_da_200_sem_gravar(
    escritorio, superusuario
):
    client = Client()
    client.login(username="admin-bl533", password="senha-forte-123")

    payload = _payload_admin_base(escritorio)
    payload.update(
        {
            "razao_social": "Fulano CPF Com Inline BL-533",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "estabelecimentos-TOTAL_FORMS": "1",
            "estabelecimentos-0-tipo": "matriz",
            "estabelecimentos-0-nome": "Matriz Indevida BL-533",
            "estabelecimentos-0-cnpj": "11122233000183",
            "estabelecimentos-0-ativo": "on",
        }
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    assert "pessoa jurídica" in resposta.content.decode()
    assert not Empresa.objects.filter(razao_social="Fulano CPF Com Inline BL-533").exists()
    assert not Estabelecimento.objects.filter(nome="Matriz Indevida BL-533").exists()


def test_admin_cria_empresa_cnpj_com_estabelecimento_no_inline_continua_funcionando(
    escritorio, superusuario
):
    # Controle: o caso NORMAL (empresa CNPJ com matriz no inline) não pode
    # ser afetado pela checagem nova.
    client = Client()
    client.login(username="admin-bl533", password="senha-forte-123")

    payload = _payload_admin_base(escritorio)
    payload.update(
        {
            "razao_social": "Empresa CNPJ Com Inline BL-533 Ltda",
            "cnpj": "11122233000183",
            "estabelecimentos-TOTAL_FORMS": "1",
            "estabelecimentos-0-tipo": "matriz",
            "estabelecimentos-0-nome": "Matriz Válida BL-533",
            "estabelecimentos-0-cnpj": "AB123CDE000155",
            "estabelecimentos-0-ativo": "on",
        }
    )
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 302, resposta.content
    empresa = Empresa.objects.get(razao_social="Empresa CNPJ Com Inline BL-533 Ltda")
    assert Estabelecimento.objects.filter(empresa=empresa, nome="Matriz Válida BL-533").exists()


# --- Caso 2: API, janela de corrida no POST de estabelecimento ---------


def test_api_post_estabelecimento_na_janela_de_corrida_da_400_nao_500(
    monkeypatch, client, gestor, empresa_cpf
):
    # Simula a janela: a checagem em Python que normalmente recusaria
    # ANTES do INSERT foi neutralizada — exatamente como aconteceria se
    # outra transação tivesse mudado a empresa para CPF entre a checagem
    # e o INSERT desta. Só o GATILHO DE BANCO sobra como defesa.
    monkeypatch.setattr(
        empresas_views, "recusar_estabelecimento_para_empresa_cpf", lambda empresa: None
    )
    client.login(username="gestor-bl533", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa_cpf.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": "11122233000183"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert "pessoa jurídica" in resposta.json()["empresa"][0]
    assert not Estabelecimento.objects.filter(empresa=empresa_cpf).exists()


# --- Caso 3: API, janela de corrida no PATCH de empresa -----------------


def test_api_patch_empresa_para_cpf_na_janela_de_corrida_da_400_nao_500(
    monkeypatch, client, gestor, empresa_cnpj_com_filial
):
    # Mesma simulação de janela, do outro lado: a checagem que normalmente
    # recusaria a TRANSIÇÃO (chamada em `EmpresaSerializer.validate`) foi
    # neutralizada.
    monkeypatch.setattr(
        empresas_serializers,
        "recusar_transicao_para_cpf_com_estabelecimento",
        lambda empresa, *, tipo_anterior, tipo_novo: None,
    )
    client.login(username="gestor-bl533", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa_cnpj_com_filial.pk}),
        data=json.dumps({"tipo_inscricao": "CPF", "cpf": "11144477735", "cnpj": ""}),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert "estabelecimento" in json.dumps(resposta.json())
    empresa_cnpj_com_filial.refresh_from_db()
    assert empresa_cnpj_com_filial.tipo_inscricao == TipoInscricao.CNPJ
    assert empresa_cnpj_com_filial.estabelecimentos.exists()
