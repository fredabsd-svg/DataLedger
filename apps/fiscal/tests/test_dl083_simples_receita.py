"""DL-083 (frente A): a composição do Simples (e o RBT12, que lê a mesma composição) usa a
receita de cada item por `receita_do_item`, e não o valor bruto.

Nota de três itens, com valores escritos à mão:
  item 1: indTot 1, vProd 100,00                               → receita 100,00
  item 2: indTot 0, vProd 50,00 (não cobrado), vFrete 10,00    → receita  10,00 (o vProd não entra)
  item 3: indTot 1, vProd 200,00, vICMSDeson 20,00 (deduz 1)   → receita 180,00
Mercadoria do mês = 100,00 + 10,00 + 180,00 = 290,00 (vNF = 290,00).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import fixar_inicio_de_uso, preparar_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-simples-dl083")


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Simples DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2025, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def test_composicao_do_mes_soma_a_receita_do_item_nao_o_bruto(escritorio_a, gestor, empresa):
    icms_deson = xml.icms(
        cst="40", filhos="<vICMSDeson>20.00</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
    )
    dets = [
        xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102")),
        xml.det(
            2,
            cfop="5102",
            vprod="50.00",
            ind_tot="0",
            vfrete="10.00",
            icms_xml=xml.icms(csosn="102"),
        ),
        xml.det(3, cfop="5102", vprod="200.00", icms_xml=icms_deson),
    ]
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=dets,
            vnf="290.00",
            totais={"vProd": "300.00"},
            numero="971",
            dh_emi="2026-03-15T10:00:00-03:00",
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=NaturezaOperacaoNFe.REVENDA)
    esc = servico.efetivar(esc, usuario=gestor)
    assert esc.soma_itens == Decimal("290.00")
    assert esc.receita_bruta == Decimal("290.00")

    composicao = receita_servico.composicao_do_mes(empresa, 2026, 3)
    assert composicao.interno.mercadoria == Decimal("290.00")
    assert composicao.interno.total == Decimal("290.00")
