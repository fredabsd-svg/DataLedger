"""Testes do ContaSerializer, incluindo a defesa de ciclo na hierarquia
acrescentada pela correção da rodada 1 de auditoria da DL-015 (achado 6).

`ContaListCreateView` só expõe criação hoje (sem rota de atualização), então
o cenário de ciclo via serializer é exercitado diretamente sobre o
serializer, com `instance` explícito — a mesma defesa continua útil no dia
em que existir uma rota de atualização (DE-008: invariante contábil não mora
só em `Model.clean()`, porque o DRF não chama `full_clean()`).
"""

import pytest

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.serializers import ContaSerializer
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def hierarquia():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    circulante = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Circulante",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
        conta_pai=ativo,
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1.01",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=circulante,
    )
    return {"empresa": empresa, "ativo": ativo, "circulante": circulante, "caixa": caixa}


def test_serializer_recusa_pai_que_e_descendente_da_propria_conta(hierarquia):
    # "Caixa" é descendente de "Ativo" (via "Circulante"); atribuir "Caixa"
    # como pai de "Ativo" criaria um ciclo.
    serializer = ContaSerializer(
        instance=hierarquia["ativo"],
        data={"conta_pai": hierarquia["caixa"].id},
        partial=True,
        context={"empresa": hierarquia["empresa"]},
    )

    assert not serializer.is_valid()
    assert "conta_pai" in serializer.errors


def test_serializer_recusa_conta_pai_de_si_mesma(hierarquia):
    serializer = ContaSerializer(
        instance=hierarquia["caixa"],
        data={"conta_pai": hierarquia["caixa"].id},
        partial=True,
        context={"empresa": hierarquia["empresa"]},
    )

    assert not serializer.is_valid()
    assert "conta_pai" in serializer.errors


def test_serializer_aceita_pai_valido_que_nao_e_descendente(hierarquia):
    # "Circulante" pode continuar filho de "Ativo" (não é ciclo nenhum) —
    # a defesa nova não pode recusar hierarquia legítima.
    serializer = ContaSerializer(
        instance=hierarquia["circulante"],
        data={"conta_pai": hierarquia["ativo"].id},
        partial=True,
        context={"empresa": hierarquia["empresa"]},
    )

    assert serializer.is_valid(), serializer.errors


def test_serializer_permite_ciclo_de_criacao_pois_conta_nova_nao_tem_instance(hierarquia):
    # Em CRIAÇÃO (instance=None, o único caminho hoje via API), não há como
    # a conta nova já ser ancestral de nada — a defesa de ciclo não se
    # aplica, e não deveria: `conta_pai` só precisa ser da mesma empresa.
    serializer = ContaSerializer(
        data={
            "codigo": "9",
            "nome": "Conta nova",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": hierarquia["caixa"].id,
        },
        context={"empresa": hierarquia["empresa"]},
    )

    assert serializer.is_valid(), serializer.errors
