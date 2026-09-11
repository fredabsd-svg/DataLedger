import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def test_usuario_nao_pode_ter_dois_vinculos_com_o_mesmo_escritorio():
    Usuario = get_user_model()
    usuario = Usuario.objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )
    escritorio = Escritorio.objects.create(nome="Escritório Alfa", cnpj="11111111000111")
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    with pytest.raises(IntegrityError):
        VinculoUsuarioEscritorio.objects.create(
            usuario=usuario, escritorio=escritorio, papel=Papel.ANALISTA
        )
