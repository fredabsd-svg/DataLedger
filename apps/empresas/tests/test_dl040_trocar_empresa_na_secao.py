"""DL-040 — seletor de empresa do menu global: `empresas:trocar-secao`.

Comportamento (nível 2 — AGENTS.md §3.1: "plano de uma página; testes do
comportamento"): a view nunca renderiza tela própria — sempre redireciona
(302) para a MESMA seção, na empresa escolhida, ou recusa antes de
redirecionar (404 para empresa que não pertence ao escritório ativo; a
tela de "sem escritório" quando não há escritório ativo). Isolamento é o
que mais importa aqui: o formulário GET só manda um `empresa_id`, e o
servidor precisa confirmar que ele pertence ao escritório ativo — nunca
confiar só no ID recebido (mesma regra de `_empresa_do_escritorio_ativo`,
em apps.contabilidade.views_web, e de `_documento_do_escritorio_ativo`, em
apps.fiscal.views_web).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_vinculo(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def escritorio_a():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


@pytest.fixture
def escritorio_b():
    return Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A", cnpj="11222333000181"
    )


@pytest.fixture
def empresa_a2(escritorio_a):
    """Segunda empresa do MESMO escritório A — o destino legítimo da troca."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A2", cnpj="11222333000280"
    )


@pytest.fixture
def empresa_de_outro_escritorio(escritorio_b):
    return Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa de outro escritório", cnpj="99888777000199"
    )


def test_troca_para_empresa_do_mesmo_escritorio_redireciona_para_a_mesma_secao(
    client, escritorio_a, empresa_a, empresa_a2
):
    _usuario_com_vinculo(Papel.ANALISTA, escritorio_a, "analista")
    client.login(username="analista", password="senha-forte-123")

    resposta = client.get(
        reverse("empresas:trocar-secao"),
        {"empresa_id": empresa_a2.id, "secao": "balancete"},
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("contabilidade_web:balancete", args=[empresa_a2.id])


def test_troca_para_empresa_de_outro_escritorio_e_404_nunca_302(
    client, escritorio_a, empresa_a, empresa_de_outro_escritorio
):
    """Isolamento: o formulário GET só manda o ID — o servidor confirma que
    a empresa pertence ao escritório ATIVO, nunca confia só no ID recebido.
    404, nunca 403: não confirma nem a existência da empresa de outro
    escritório para quem não tem acesso a ela (mesmo critério já usado nas
    telas da contabilidade e do Fiscal)."""
    _usuario_com_vinculo(Papel.ANALISTA, escritorio_a, "analista")
    client.login(username="analista", password="senha-forte-123")

    resposta = client.get(
        reverse("empresas:trocar-secao"),
        {"empresa_id": empresa_de_outro_escritorio.id, "secao": "balancete"},
    )

    assert resposta.status_code == 404


def test_empresa_id_invalido_e_404_nao_500(client, escritorio_a, empresa_a):
    _usuario_com_vinculo(Papel.ANALISTA, escritorio_a, "analista")
    client.login(username="analista", password="senha-forte-123")

    resposta = client.get(
        reverse("empresas:trocar-secao"),
        {"empresa_id": "9" * 6000, "secao": "balancete"},
    )

    assert resposta.status_code == 404


def test_secao_desconhecida_cai_no_padrao_plano_de_contas_em_vez_de_erro(
    client, escritorio_a, empresa_a, empresa_a2
):
    """Razão exige conta_id; as telas de ação do fechamento exigem ano/mês —
    nenhuma das duas tem uma seção "equivalente" resolvível só com
    empresa_id. A troca ainda funciona: cai no padrão, em vez de 400."""
    _usuario_com_vinculo(Papel.ANALISTA, escritorio_a, "analista")
    client.login(username="analista", password="senha-forte-123")

    resposta = client.get(
        reverse("empresas:trocar-secao"),
        {"empresa_id": empresa_a2.id, "secao": "razao"},
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse(
        "contabilidade_web:plano_de_contas", args=[empresa_a2.id]
    )


def test_sem_escritorio_ativo_mostra_tela_propria_nunca_500(client):
    get_user_model().objects.create_user(
        username="sem-vinculo", email="sem-vinculo@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="sem-vinculo", password="senha-forte-123")

    resposta = client.get(reverse("empresas:trocar-secao"), {"empresa_id": 1, "secao": "balancete"})

    assert resposta.status_code == 200
    assert "escritório" in resposta.content.decode().lower()


def test_requer_autenticacao(client):
    resposta = client.get(reverse("empresas:trocar-secao"), {"empresa_id": 1})
    assert resposta.status_code == 302
    assert resposta["Location"].startswith(reverse("login"))


def test_metodo_post_nao_e_aceito(client, escritorio_a, empresa_a):
    """`require_safe`: só GET/HEAD — é um seletor de navegação, não uma
    escrita (mesmo espírito de `tenancy:ativar`, que É POST, mas aqui a
    troca é idempotente e não grava nada; GET é o método certo)."""
    _usuario_com_vinculo(Papel.ANALISTA, escritorio_a, "analista")
    client.login(username="analista", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:trocar-secao"), {"empresa_id": empresa_a.id, "secao": "balancete"}
    )

    assert resposta.status_code == 405
