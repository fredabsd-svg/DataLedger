import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )


def test_codigo_e_unico_por_empresa(empresa):
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    with pytest.raises(IntegrityError):
        Conta.objects.create(
            empresa=empresa,
            codigo="1",
            nome="Ativo (duplicado)",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )


def test_conta_pai_deve_ser_da_mesma_empresa(empresa):
    outro_escritorio = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    outra_empresa = Empresa.objects.create(
        escritorio=outro_escritorio, razao_social="Empresa B Ltda", cnpj="44455566000183"
    )
    conta_pai_de_outra_empresa = Conta.objects.create(
        empresa=outra_empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    conta = Conta(
        empresa=empresa,
        conta_pai=conta_pai_de_outra_empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    with pytest.raises(ValidationError):
        conta.full_clean()
