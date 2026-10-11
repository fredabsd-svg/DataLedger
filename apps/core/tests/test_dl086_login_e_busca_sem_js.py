"""DL-086 — textos de acesso honestos: login (E-01) e busca sem JS (G-01).

- E-01: o cartão de login diz o caminho REAL de quem esqueceu a senha (pedir
  ao administrador do escritório — ou ao da instalação, no primeiro acesso),
  porque a redefinição self-service ainda não existe (BL-640). A tela não
  pode prometer nem linkar o que não há: por isso NÃO há link de recuperação,
  e este teste também trava o aparecimento de um link morto futuro.
- G-01: a busca "Buscar empresa" dos filtros da home só funciona com
  JavaScript; sem ele, um `<noscript>` manda o usuário ao seletor de empresa
  em vez de deixar um campo que não faz nada.
"""

import re

import pytest
from django.template.loader import get_template
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_diz_o_caminho_real_de_quem_esqueceu_a_senha(client):
    html = client.get(reverse("login")).content.decode()
    assert "Esqueceu a senha?" in html
    assert "Peça a redefinição ao administrador do seu escritório" in html
    assert "primeiro acesso" in html
    assert "ainda não existe no produto" in html


def test_login_nao_oferece_link_de_redefinicao_que_nao_existe(client):
    """BL-640: sem fluxo self-service, não há o que linkar. Um link de
    "esqueci a senha" aqui seria promessa falsa — e este teste é o que pega
    o link morto quando alguém o adicionar sem criar o fluxo."""
    html = client.get(reverse("login")).content.decode()
    links_que_prometem_senha = re.findall(r"<a\b[^>]*>[^<]*senha[^<]*", html, flags=re.IGNORECASE)
    assert links_que_prometem_senha == []


def test_busca_de_empresa_avisa_que_precisa_de_javascript():
    """G-01: solução só de template — o `<noscript>` fica junto do campo que
    depende de JS, apontando o seletor de empresa como alternativa."""
    html = get_template("core/_home_components.html").render(
        {
            "parte": "filtros",
            "home": {
                "filtros": {
                    "empresa": "todas",
                    "empresas_opcoes": [],
                    "competencias_opcoes": [],
                    "competencia": "2026-10",
                    "competencia_rotulo": "10/2026",
                },
            },
        }
    )
    assert "data-home-company-search" in html  # o campo que depende de JS
    assert "<noscript>" in html
    assert "use o seletor de empresa" in html
    # O aviso vem DEPOIS do campo, dentro do mesmo disclosure.
    assert html.index("data-home-company-search") < html.index("<noscript>")
