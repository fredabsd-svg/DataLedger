from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import (
    Conta,
    LancamentoImutavelError,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def contas():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {"empresa": empresa, "caixa": caixa, "capital": capital}


@pytest.fixture
def lancamento(contas):
    return criar_lancamento(
        empresa=contas["empresa"],
        data=date(2024, 1, 1),
        historico="Integralização de capital",
        itens=[
            {"conta": contas["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
            {"conta": contas["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
        ],
    )


def test_nao_pode_editar_lancamento_existente(lancamento):
    lancamento.historico = "Tentativa de edição"

    with pytest.raises(LancamentoImutavelError):
        lancamento.save()


def test_nao_pode_excluir_lancamento(lancamento):
    with pytest.raises(LancamentoImutavelError):
        lancamento.delete()


def test_nao_pode_editar_item_de_lancamento(lancamento):
    item = lancamento.itens.first()
    item.valor = Decimal("999.00")

    with pytest.raises(LancamentoImutavelError):
        item.save()


def test_nao_pode_excluir_item_de_lancamento(lancamento):
    item = lancamento.itens.first()

    with pytest.raises(LancamentoImutavelError):
        item.delete()
