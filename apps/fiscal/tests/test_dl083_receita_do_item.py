"""DL-083 (frente A), critério 1: a receita de cada item nos casos indTot 1 ou 0 × indDeduzDeson
1, 0 ou ausente. Os valores esperados são escritos à mão, em `Decimal`, e nenhum sai de float.

Também: o campo gravado `ItemNFe.receita_bruta_item` continua sendo o VALOR BRUTO (não muda), e a
versão do leitor não sobe (decisão do arquiteto, DL-083).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import itens_nfe
from apps.fiscal.itens_nfe import receita_do_item
from apps.fiscal.models import ItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


def _item(**campos):
    """Um item com os campos que `receita_do_item` lê. Ausente é None, como no leitor."""
    base = {
        "ind_tot": "1",
        "v_prod": Decimal("100.00"),
        "v_desc": None,
        "v_frete": None,
        "v_seg": None,
        "v_outro": None,
        "v_icms_deson": None,
        "ind_deduz_deson": None,
    }
    base.update(campos)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    ("campos", "esperado"),
    [
        # indTot 1, vProd 100,00. Sem deson: a receita é o vProd.
        ({"ind_tot": "1"}, Decimal("100.00")),
        (
            {"ind_tot": "1", "ind_deduz_deson": "0", "v_icms_deson": Decimal("10.00")},
            Decimal("100.00"),
        ),
        (
            {"ind_tot": "1", "ind_deduz_deson": None, "v_icms_deson": Decimal("10.00")},
            Decimal("100.00"),
        ),
        # indTot 1 com deson deduzido (indDeduzDeson 1): 100,00 − 10,00 = 90,00.
        (
            {"ind_tot": "1", "ind_deduz_deson": "1", "v_icms_deson": Decimal("10.00")},
            Decimal("90.00"),
        ),
        # indTot 1 com todas as parcelas: 100,00 − 5,00 + 10,00 + 1,00 + 2,00 = 108,00.
        (
            {
                "ind_tot": "1",
                "v_desc": Decimal("5.00"),
                "v_frete": Decimal("10.00"),
                "v_seg": Decimal("1.00"),
                "v_outro": Decimal("2.00"),
            },
            Decimal("108.00"),
        ),
        # indTot 1: desconto, deson deduzido e frete: 100,00 − 5,00 − 10,00 + 10,00 = 95,00.
        (
            {
                "ind_tot": "1",
                "v_desc": Decimal("5.00"),
                "v_icms_deson": Decimal("10.00"),
                "ind_deduz_deson": "1",
                "v_frete": Decimal("10.00"),
            },
            Decimal("95.00"),
        ),
        # indTot 0 (o vProd de 100,00 não foi cobrado): sem nada, a receita é zero.
        ({"ind_tot": "0"}, Decimal("0.00")),
        # indTot 0 com frete de 10,00: só o frete compõe a receita (não os 100,00 do vProd).
        ({"ind_tot": "0", "v_frete": Decimal("10.00")}, Decimal("10.00")),
        # indTot 0 com desconto de 5,00: a receita fica negativa, −5,00.
        ({"ind_tot": "0", "v_desc": Decimal("5.00")}, Decimal("-5.00")),
        # indTot 0 com desconto 5,00, frete 10,00, seguro 1,00 e outras 2,00: 8,00.
        (
            {
                "ind_tot": "0",
                "v_desc": Decimal("5.00"),
                "v_frete": Decimal("10.00"),
                "v_seg": Decimal("1.00"),
                "v_outro": Decimal("2.00"),
            },
            Decimal("8.00"),
        ),
        # indTot 0 com deson deduzido: só o −10,00 do ICMS desonerado (o vProd não entra).
        (
            {"ind_tot": "0", "ind_deduz_deson": "1", "v_icms_deson": Decimal("10.00")},
            Decimal("-10.00"),
        ),
        # indTot 0 com deson NÃO deduzido: nada se deduz, a receita é zero.
        (
            {"ind_tot": "0", "ind_deduz_deson": "0", "v_icms_deson": Decimal("10.00")},
            Decimal("0.00"),
        ),
        (
            {"ind_tot": "0", "ind_deduz_deson": None, "v_icms_deson": Decimal("10.00")},
            Decimal("0.00"),
        ),
    ],
)
def test_receita_do_item_nos_casos_de_indtot_e_de_deson(campos, esperado):
    resultado = receita_do_item(_item(**campos))
    assert resultado == esperado
    assert isinstance(resultado, Decimal)


def test_receita_do_item_com_deson_deduzido_mas_sem_valor_nao_deduz_nada():
    """indDeduzDeson 1 sem vICMSDeson gravado: não há valor a deduzir, e a receita é o vProd. Não se
    inventa um número."""
    assert receita_do_item(_item(ind_deduz_deson="1", v_icms_deson=None)) == Decimal("100.00")


def test_receita_do_item_nao_usa_float_mesmo_com_centavos_que_o_float_erra():
    """0,10 + 0,20 é 0,30 em Decimal. Em float binário sairia 0,30000000000000004."""
    item = _item(ind_tot="0", v_frete=Decimal("0.10"), v_seg=Decimal("0.20"))
    assert receita_do_item(item) == Decimal("0.30")


# ---------------------------------------------------------------------------------------------
# O campo gravado é o valor bruto, e a versão do leitor não sobe
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-receita-item-dl083")


def test_versao_do_leitor_nao_sobe_na_dl083():
    """Decisão do arquiteto (DL-083): subir a versão deixaria sem saída a nota estornada
    (BL-686)."""
    assert itens_nfe.VERSAO_LEITOR_ITENS == 2


def test_receita_bruta_item_gravado_continua_sendo_o_valor_bruto(escritorio_a, gestor):
    """Item indTot 0 com vProd 50,00 e frete 10,00. O campo gravado é o BRUTO, 60,00 (vProd − vDesc
    + vFrete + vSeg + vOutro), como antes. A receita do item, por `receita_do_item`, é 10,00."""
    # A recepção só grava nota de participante do escritório: a empresa emitente existe aqui.
    Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[
                xml.det(1, vprod="100.00"),
                xml.det(2, vprod="50.00", ind_tot="0", vfrete="10.00"),
            ],
            vnf="110.00",
            numero="701",
        ),
    )
    itens_nfe.ler_itens(documento)
    item_2 = ItemNFe.objects.get(documento=documento, n_item=2)
    assert item_2.receita_bruta_item == Decimal("60.00")
    assert receita_do_item(item_2) == Decimal("10.00")
    item_1 = ItemNFe.objects.get(documento=documento, n_item=1)
    assert item_1.receita_bruta_item == Decimal("100.00")
    assert receita_do_item(item_1) == Decimal("100.00")
