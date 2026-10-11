"""DL-086 (parte do achado C-07) — Referrer-Policy sempre ativo.

O token do convite mora no path da URL (BL-547, aberta). Sem Referrer-Policy,
um link externo clicado a partir de `/convite/<token>/` envia a URL inteira —
token incluído — no cabeçalho `Referer` ao site de destino. `same-origin`
mantém o Referer dentro do próprio sistema e o suprime para fora; não depende
de HTTPS, então vive no bloco sempre-ativo do settings (junto de X-Frame e
nosniff, que este teste também prende contra regressão).

A CSP inteira (`default-src 'self'`) NÃO entra aqui: exige mapear antes os
estilos embutidos dos templates e está registrada no BL-689.
"""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_cabecalhos_de_seguranca_sempre_ativos_na_entrada_publica():
    resposta = Client().get("/login/")

    assert resposta["Referrer-Policy"] == "same-origin"
    assert resposta["X-Frame-Options"] == "DENY"
    assert resposta["X-Content-Type-Options"] == "nosniff"


def test_referrer_policy_tambem_na_pagina_autenticada(client):
    # A página que interessa ao BL-547 é interna: o aceite do convite. O
    # cabeçalho vale para toda resposta, autenticada ou não.
    resposta = client.get("/", follow=False)
    assert resposta["Referrer-Policy"] == "same-origin"
