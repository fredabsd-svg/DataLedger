"""Achado A10 da auditoria rodada 1 — `apps.fiscal.uploads.
LimiteDeTamanhoUploadHandler`, ligado só em `apps.fiscal.views_web.
recepcao`: um upload acima de `LIMITE_TAMANHO_ENVIO_BYTES` é abortado PELO
HANDLER (não grava mais nada em disco/memória depois do limite) e a view
responde 400 com mensagem legível, nunca 500 e nunca silenciosamente "sem
arquivo".

Não testa o arquivo de tela proibido desta rodada
(`apps/fiscal/tests/test_telas_dl010_f1.py`, do `especialista-frontend`) —
arquivo novo, mesmo padrão de fixtures de `apps/fiscal/tests/conftest.py`.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import apps.fiscal.views_web as views_web
from apps.fiscal.models import LoteDeRecepcao
from apps.fiscal.tests.xml_sinteticos import xml_nfse

pytestmark = pytest.mark.django_db


def test_upload_acima_do_limite_e_recusado_com_mensagem_legivel(
    client, escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    # SÓ o nome em `views_web` — é o valor que a VIEW de fato usa para
    # dimensionar o handler (`from apps.fiscal.services import
    # LIMITE_TAMANHO_ENVIO_BYTES` copia o VALOR na hora do import, não
    # cria uma referência viva a `apps.fiscal.services.
    # LIMITE_TAMANHO_ENVIO_BYTES`). Trap medido nesta rodada: monkeypatchar
    # `apps.fiscal.services.LIMITE_TAMANHO_ENVIO_BYTES` TAMBÉM, antes do
    # primeiro `import apps.fiscal.views_web` do processo de teste,
    # corrompe permanentemente o valor de `views_web` para o resto da
    # sessão — o import (esse sim, uma referência nova) capturaria o
    # valor JÁ PATCHADO de `services`, e o `monkeypatch` não tem como
    # desfazer um import que nunca rastreou. Import no TOPO do arquivo
    # (não dentro da função) para garantir que já aconteceu antes de
    # qualquer monkeypatch.
    monkeypatch.setattr(views_web, "LIMITE_TAMANHO_ENVIO_BYTES", 1000)

    client.login(username="gestor-fiscal-a", password="senha-forte-123")
    arquivo_grande = SimpleUploadedFile("grande.zip", b"x" * 5000, content_type="application/zip")

    resposta = client.post(reverse("fiscal_web:recepcao"), {"arquivo": arquivo_grande}, follow=True)

    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "limite" in conteudo.lower()
    assert not LoteDeRecepcao.objects.filter(escritorio=escritorio_a).exists()


def test_upload_dentro_do_limite_continua_funcionando(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # Prova de que ligar o handler não quebra o caminho feliz — mesmo
    # cenário de sempre, agora com o handler ativo na requisição real.
    client.login(username="gestor-fiscal-a", password="senha-forte-123")
    conteudo = xml_nfse(incluir_tomador=False)
    arquivo = SimpleUploadedFile("nota.xml", conteudo, content_type="application/xml")

    resposta = client.post(reverse("fiscal_web:recepcao"), {"arquivo": arquivo}, follow=True)

    assert resposta.status_code == 200
    assert LoteDeRecepcao.objects.filter(escritorio=escritorio_a, total_recebidos=1).exists()


def test_get_da_recepcao_continua_funcionando_sem_handler(client, escritorio_a, usuario_gestor_a):
    # GET não envia arquivo — o handler nem é inserido (`recepcao` só
    # insere em POST); confirma que a tela carrega normalmente.
    client.login(username="gestor-fiscal-a", password="senha-forte-123")
    resposta = client.get(reverse("fiscal_web:recepcao"))
    assert resposta.status_code == 200
