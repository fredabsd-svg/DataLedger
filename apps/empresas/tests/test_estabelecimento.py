import pytest
from django.db import IntegrityError

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )


def test_empresa_pode_ter_apenas_uma_matriz(empresa):
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz",
        cnpj="11122233000183",
    )

    with pytest.raises(IntegrityError):
        Estabelecimento.objects.create(
            empresa=empresa,
            tipo=TipoEstabelecimento.MATRIZ,
            nome="Outra matriz",
            cnpj="44455566000183",
        )


def test_empresa_pode_ter_varias_filiais(empresa):
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial 1",
        cnpj="44455566000183",
    )
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial 2",
        cnpj="44455566000264",
    )

    assert empresa.estabelecimentos.count() == 2
