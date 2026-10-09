"""DL-081, correção da rodada 1 (A11): sugestão de exportação direta só para venda ao exterior.

Com `idDest` 3 (operação com o exterior), o CFOP 7.1xx é venda: sugere exportação direta. A rodada 1
sugeria também a remessa (7.949) e o ativo imobilizado (7.551), e o bloco "confirmar tudo" as levava
junto. Esses dois CFOP agora ficam sem sugestão.
"""

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import itens_nfe
from apps.fiscal.models import ItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-a11-sugestao-dl081")


@pytest.fixture
def emitente(escritorio_a):
    """A recepção só aceita a nota cujo emitente é de uma empresa do escritório."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Sugestao A11 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _sugestao(escritorio, usuario, cfop):
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod="100.00", icms_xml=xml.icms(csosn="102"))],
            vnf="100.00",
            totais={"vProd": "100.00"},
            numero=str(7000 + int(cfop)),
            id_dest="3",
        ),
    )
    itens_nfe.ler_itens(documento)
    item = ItemNFe.objects.get(documento=documento)
    return servico.sugerir_natureza_item(documento, item, "saida_propria").natureza


@pytest.mark.parametrize("cfop", ["7101", "7127"])
def test_venda_ao_exterior_com_id_dest_3_sugere_exportacao_direta(
    escritorio_a, gestor, emitente, cfop
):
    assert _sugestao(escritorio_a, gestor, cfop) == NaturezaOperacaoNFe.EXPORTACAO_DIRETA


@pytest.mark.parametrize("cfop", ["7949", "7551"])
def test_remessa_e_ativo_com_id_dest_3_ficam_sem_sugestao(escritorio_a, gestor, emitente, cfop):
    assert _sugestao(escritorio_a, gestor, cfop) is None
