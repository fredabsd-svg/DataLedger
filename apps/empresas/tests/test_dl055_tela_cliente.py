"""DL-055 (complemento de interface): a tela é coerente com o 403 do servidor.

O servidor já recusa o papel CLIENTE em todo o app `empresas`. Aqui se garante
que a tela não CONVIDA esse papel a abrir o que será recusado: Início sem o
indicador "Empresas ativas" (nem o total, nem o link), menu sem "Empresas",
sem o tile e o botão "Ver empresas" do Início, e a página 403 com um botão que
leva a uma página que ele abre (nunca a outro 403). Os demais papéis veem
exatamente o que viam. A defesa continua sendo o servidor; estes testes só
cobrem a apresentação.

Dados sintéticos.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.permissoes import PAPEIS_QUE_LEEM_CARTEIRA
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
URL_LISTA = "/empresas/"
LEITORES = list(PAPEIS_QUE_LEEM_CARTEIRA)
BOTAO_VOLTAR = r'<a class="botao botao--secundario" href="([^"]+)">‹ Voltar'


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL055 tela", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Tela Sintetica Alfa Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Tela Sintetica Beta Ltda",
        cnpj="44455566000264",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    return {"escritorio": escritorio, "empresa": empresa}


def _entrar(client, cenario, papel):
    usuario = get_user_model().objects.create_user(
        username=f"u-{papel}", email=f"{papel}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=cenario["escritorio"], papel=papel
    )
    assert client.login(username=usuario.username, password=SENHA)


def _html(resposta):
    return resposta.content.decode()


def _links(html):
    return re.findall(r'href="([^"]*)"', html)


def _links_para_a_lista(html):
    return [h for h in _links(html) if h.split("?")[0] == URL_LISTA]


def test_a_rota_de_empresas_e_a_esperada():
    # Ancora os testes abaixo: se a rota mudar, eles não passam a ser vácuos.
    assert reverse("empresas:lista") == URL_LISTA


# --------------------------------------------------------------------------
# CLIENTE
# --------------------------------------------------------------------------


def test_cliente_nao_ve_o_indicador_empresas_ativas_no_inicio(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    html = _html(resposta)
    assert "Empresas ativas" not in html
    assert 'id="titulo-indicadores"' not in html
    assert "Tela Sintetica" not in html


def test_cliente_nao_recebe_nenhum_link_para_a_lista_de_empresas_no_inicio(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    html = _html(client.get(reverse("tenancy:painel")))
    assert _links_para_a_lista(html) == []
    assert "Ver empresas" not in html
    assert "Cadastro e carteira do escritório" not in html  # tile "Empresas"
    assert reverse("empresas:criar") not in _links(html)


def test_cliente_nao_ve_o_menu_de_cadastros_nem_empresas(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    html = _html(client.get(reverse("tenancy:painel")))
    assert "Cadastros" not in html
    assert "Alt+M" not in html
    assert 'accesskey="m"' not in html
    assert "Trocar de empresa" not in html
    assert "Ir para Empresas" not in html


def test_cliente_na_pagina_403_tem_botao_para_destino_acessivel(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    recusa = client.get(reverse("empresas:lista"))
    assert recusa.status_code == 403
    html = _html(recusa)
    assert "Voltar para empresas" not in html
    assert _links_para_a_lista(html) == []
    assert "‹ Voltar para o Início" in html
    destino = re.search(BOTAO_VOLTAR, html)
    assert destino is not None
    assert client.get(destino.group(1)).status_code == 200


def test_cliente_na_pagina_403_de_outra_rota_tambem_nao_cai_em_laco(client, cenario):
    """O 403 de contabilidade usa o mesmo template: mesmo botão, mesmo destino."""
    _entrar(client, cenario, Papel.CLIENTE)
    recusa = client.get(reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa"].id]))
    assert recusa.status_code == 403
    html = _html(recusa)
    assert _links_para_a_lista(html) == []
    destino = re.search(BOTAO_VOLTAR, html)
    assert destino is not None
    assert client.get(destino.group(1)).status_code == 200


# --------------------------------------------------------------------------
# Demais papéis: exatamente o que viam
# --------------------------------------------------------------------------


@pytest.mark.parametrize("papel", LEITORES)
def test_leitores_continuam_vendo_o_indicador_com_o_total_e_o_link(client, cenario, papel):
    _entrar(client, cenario, papel)
    html = _html(client.get(reverse("tenancy:painel")))
    assert "Empresas ativas" in html
    assert "Ver empresas" in html
    assert URL_LISTA in _links_para_a_lista(html)
    # O total (2 empresas ativas) está no mesmo indicador que o título.
    trecho = html[html.index("Empresas ativas") - 400 : html.index("Empresas ativas") + 400]
    assert re.search(r">\s*2\s*<", trecho)


@pytest.mark.parametrize("papel", LEITORES)
def test_leitores_continuam_vendo_o_menu_e_o_tile_de_empresas(client, cenario, papel):
    _entrar(client, cenario, papel)
    html = _html(client.get(reverse("tenancy:painel")))
    assert "Cadastros" in html
    assert 'accesskey="m"' in html
    assert "Alt+M" in html
    assert "Cadastro e carteira do escritório" in html
    assert "Ir para Empresas" in html


@pytest.mark.parametrize("papel", LEITORES)
def test_leitores_continuam_vendo_trocar_de_empresa_dentro_de_uma_empresa(client, cenario, papel):
    _entrar(client, cenario, papel)
    resposta = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa"].id])
    )
    assert resposta.status_code == 200
    assert "Trocar de empresa" in _html(resposta)


@pytest.mark.parametrize("papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL])
def test_leitor_sem_poder_de_cadastrar_ve_a_pagina_403_com_o_botao_de_sempre(
    client, cenario, papel
):
    _entrar(client, cenario, papel)
    recusa = client.get(reverse("empresas:criar"))
    assert recusa.status_code == 403
    html = _html(recusa)
    assert "‹ Voltar para empresas" in html
    assert URL_LISTA in _links_para_a_lista(html)
    assert "Voltar para o Início" not in html


# --------------------------------------------------------------------------
# A decisão vem da MESMA lista do servidor, não de uma lista no template
# --------------------------------------------------------------------------


def test_a_tela_segue_a_lista_do_servidor_quando_ela_muda(client, cenario, monkeypatch):
    """Se a lista deixar de incluir um papel que ainda lê a contabilidade, a
    tela acompanha sozinha: nenhum papel está escrito no template. Cobre os
    links de trocar de empresa do menu, que o CLIENTE nunca alcança hoje porque
    estão dentro do bloco de contabilidade."""
    monkeypatch.setattr(
        "apps.empresas.permissoes.PAPEIS_QUE_LEEM_CARTEIRA",
        tuple(p for p in PAPEIS_QUE_LEEM_CARTEIRA if p != Papel.ANALISTA),
    )
    _entrar(client, cenario, Papel.ANALISTA)

    inicio = _html(client.get(reverse("tenancy:painel")))
    assert "Empresas ativas" not in inicio
    assert "Cadastro e carteira do escritório" not in inicio  # tile "Empresas"
    assert "Ir para Empresas" not in inicio
    assert "Cadastros" not in inicio  # ANALISTA tampouco cadastra empresa

    dentro = client.get(reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa"].id]))
    assert dentro.status_code == 200
    assert "Trocar de empresa" not in _html(dentro)
