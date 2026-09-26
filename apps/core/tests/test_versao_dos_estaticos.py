"""O link da folha de estilo leva a impressão digital do conteúdo (`?v=`).

Achado do Fred em 2026-09-26: depois do merge da DL-044 a tela veio com a
estrutura nova e a folha de estilo antiga, porque o link era um caminho
fixo. A versão no link muda sozinha quando o conteúdo do arquivo muda.
"""

import hashlib

from django.contrib.staticfiles import finders
from django.test import RequestFactory

from apps.core.context_processors import (
    _impressao_digital_do_estatico,
    versao_dos_estaticos,
)


def _esperado(caminho):
    with open(finders.find(caminho), "rb") as arquivo:
        return hashlib.sha256(arquivo.read()).hexdigest()[:12]


def test_versao_e_a_impressao_digital_do_conteudo_de_cada_folha():
    contexto = versao_dos_estaticos(RequestFactory().get("/"))
    assert contexto["versao_css_base"] == _esperado("css/base.css")
    assert contexto["versao_css_publico"] == _esperado("css/public.css")
    assert len(contexto["versao_css_base"]) == 12


def test_arquivo_inexistente_devolve_vazio_sem_quebrar():
    assert _impressao_digital_do_estatico("css/nao-existe.css") == ""


def test_paginas_publica_e_autenticada_levam_a_versao_no_link(client, django_user_model):
    base = versao_dos_estaticos(None)["versao_css_base"]
    publico = versao_dos_estaticos(None)["versao_css_publico"]

    corpo_publico = client.get("/").content.decode()
    assert f'href="/static/css/public.css?v={publico}"' in corpo_publico

    usuario = django_user_model.objects.create_user(
        username="versao-estaticos", password="senha-sintetica-123"
    )
    client.force_login(usuario)
    corpo = client.get("/", follow=True).content.decode()
    assert f'href="/static/css/base.css?v={base}"' in corpo
