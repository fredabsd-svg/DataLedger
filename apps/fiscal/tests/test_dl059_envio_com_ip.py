"""DL-059 (BL-579) — o evento `fiscal.envio_recebido` grava o IP da requisição.

Antes, `receber_envio` chamava `registrar` sem `request` e a trilha do recebimento
de lote fiscal ficava sem origem. Dados sintéticos; IP de documentação (RFC 5737).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal.services import receber_envio
from apps.fiscal.tests.xml_sinteticos import xml_nfse

pytestmark = pytest.mark.django_db

IP = "198.51.100.9"


def test_envio_pela_tela_grava_o_ip_da_requisicao(
    client, settings, escritorio_a, empresa_a, usuario_gestor_a
):
    settings.PROXIES_CONFIAVEIS = []
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        reverse("fiscal_web:recepcao"),
        {"arquivo": SimpleUploadedFile("nota.xml", xml_nfse(), content_type="application/xml")},
        REMOTE_ADDR=IP,
    )

    assert resposta.status_code == 302
    evento = RegistroAuditoria.objects.get(acao="fiscal.envio_recebido")
    assert evento.endereco_ip == IP
    assert evento.escritorio == escritorio_a


def test_servico_sem_request_continua_funcionando_sem_ip(escritorio_a, empresa_a, usuario_gestor_a):
    receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=SimpleUploadedFile("nota.xml", xml_nfse(), content_type="application/xml"),
        nome_arquivo="nota.xml",
    )

    evento = RegistroAuditoria.objects.get(acao="fiscal.envio_recebido")
    assert evento.endereco_ip is None
