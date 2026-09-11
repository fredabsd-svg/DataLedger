import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


def test_registrar_grava_acao_usuario_e_escritorio():
    usuario = get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")

    registro = registrar(acao="teste.acao", usuario=usuario, escritorio=escritorio)

    assert registro.acao == "teste.acao"
    assert registro.usuario == usuario
    assert registro.escritorio == escritorio


def test_registrar_grava_objeto_e_detalhes():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )

    registro = registrar(acao="empresa.criada", objeto=empresa, detalhes={"origem": "teste"})

    assert registro.objeto_tipo == "Empresa"
    assert registro.objeto_id == str(empresa.pk)
    assert registro.detalhes == {"origem": "teste"}


def test_registrar_infere_usuario_escritorio_e_ip_da_requisicao():
    usuario = get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")

    request = RequestFactory().get("/")
    request.user = usuario
    request.escritorio = escritorio
    request.META["REMOTE_ADDR"] = "203.0.113.10"

    registro = registrar(acao="teste.acao", request=request)

    assert registro.usuario == usuario
    assert registro.escritorio == escritorio
    assert registro.endereco_ip == "203.0.113.10"


def test_registrar_persiste_no_banco():
    registrar(acao="teste.acao")

    assert RegistroAuditoria.objects.filter(acao="teste.acao").exists()
