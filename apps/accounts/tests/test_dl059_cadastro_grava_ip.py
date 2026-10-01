"""DL-059 (BL-579), integração: o cadastro de escritório grava o IP na trilha.

`escritorio.criado_por_bootstrap` já gravava o IP pela tela de primeiro acesso;
pelo cadastro (`apps.accounts.views.cadastro`) saía sem IP porque a view não
repassava o `request` ao serviço. Dados 100% sintéticos.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.test_dl056_limite_de_tentativas import _dados_cadastro
from apps.auditoria.models import RegistroAuditoria

pytestmark = pytest.mark.django_db

IP = "198.51.100.23"


@pytest.fixture(autouse=True)
def sem_proxy_confiavel(settings):
    # Sem proxy configurado, o IP gravado é o REMOTE_ADDR (DL-057).
    settings.PROXIES_CONFIAVEIS = []


def test_cadastro_de_escritorio_grava_o_ip_na_trilha():
    resposta = Client().post(reverse("cadastro"), _dados_cadastro(901), REMOTE_ADDR=IP)

    assert resposta.status_code == 302
    (evento,) = RegistroAuditoria.objects.filter(acao="escritorio.criado_por_bootstrap")
    assert evento.endereco_ip == IP
    assert evento.escritorio is not None
    assert evento.usuario is not None
