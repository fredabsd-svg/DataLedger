"""Suporte dos testes da DL-081 (frente A): recepção de XML sintético e usuários por papel.

Sem fixtures aqui: cada módulo de teste declara as suas. Tudo é sintético. Os CNPJ vêm de
`xml_nfe_dl080`, que já tem dígito verificador correto.
"""

from django.contrib.auth import get_user_model

from apps.fiscal import services
from apps.fiscal.models import DocumentoNFe, VinculoNFeEmpresa
from apps.tenancy.models import VinculoUsuarioEscritorio


def usuario_com_papel(escritorio, papel, nome):
    usuario = get_user_model().objects.create_user(
        username=nome,
        email=f"{nome}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def receber(escritorio, usuario, xml: bytes):
    """Recebe um XML pela recepção da DL-080 e devolve o `DocumentoNFe` gravado."""
    services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=xml, nome_arquivo="nota.xml"
    )
    return DocumentoNFe.objects.filter(escritorio=escritorio).latest("pk")


def vinculo(documento, empresa) -> VinculoNFeEmpresa:
    return VinculoNFeEmpresa.objects.get(documento=documento, empresa=empresa)
