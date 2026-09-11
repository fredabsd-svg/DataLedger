from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import LancamentoInvalido, criar_lancamento, estornar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


def _item(conta, tipo, valor):
    return {"conta": conta, "tipo": tipo, "valor": Decimal(valor)}


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    outra_empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B Ltda", cnpj="44455566000183"
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
    sintetica = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    return {
        "empresa": empresa,
        "outra_empresa": outra_empresa,
        "caixa": caixa,
        "capital": capital,
        "sintetica": sintetica,
    }


def test_lancamento_balanceado_e_criado_com_sucesso(cenario):
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Integralização de capital",
        itens=[
            _item(cenario["caixa"], TipoPartida.DEBITO, "1000.00"),
            _item(cenario["capital"], TipoPartida.CREDITO, "1000.00"),
        ],
    )

    assert lancamento.itens.count() == 2


def test_debito_diferente_de_credito_e_rejeitado(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Lançamento desbalanceado",
            itens=[
                _item(cenario["caixa"], TipoPartida.DEBITO, "1000.00"),
                _item(cenario["capital"], TipoPartida.CREDITO, "900.00"),
            ],
        )


def test_menos_de_duas_partidas_e_rejeitado(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Partida única",
            itens=[_item(cenario["caixa"], TipoPartida.DEBITO, "1000.00")],
        )


def test_conta_de_outra_empresa_e_rejeitada(cenario):
    conta_de_outra_empresa = Conta.objects.create(
        empresa=cenario["outra_empresa"],
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Lançamento cruzado",
            itens=[
                _item(conta_de_outra_empresa, TipoPartida.DEBITO, "100"),
                _item(cenario["capital"], TipoPartida.CREDITO, "100"),
            ],
        )


def test_conta_sintetica_nao_aceita_lancamento(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Lançamento em conta sintética",
            itens=[
                _item(cenario["sintetica"], TipoPartida.DEBITO, "100"),
                _item(cenario["capital"], TipoPartida.CREDITO, "100"),
            ],
        )


def test_estorno_inverte_as_partidas_e_referencia_o_original(cenario):
    original = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Lançamento original",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )

    estorno = estornar_lancamento(original)

    assert estorno.estorno_de_id == original.pk
    item_caixa_estorno = estorno.itens.get(conta=cenario["caixa"])
    assert item_caixa_estorno.tipo == TipoPartida.CREDITO
    assert item_caixa_estorno.valor == Decimal("500.00")


def test_nao_pode_estornar_um_estorno(cenario):
    original = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Lançamento original",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    estorno = estornar_lancamento(original)

    with pytest.raises(LancamentoInvalido):
        estornar_lancamento(estorno)
