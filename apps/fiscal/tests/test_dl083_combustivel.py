"""DL-083 (frente A), natureza de combustível (HI-118, PE-85.1).

- Rótulos, catálogo e entrada no CHECK de banco (migração 0012), com a lista igual à do enum.
- Sugestão pelo CFOP só quando a DESCRIÇÃO da tabela oficial confirma (cfop.py).
- Devolução de venda de combustível, pela descrição e pelo indDevol da tabela.
- A reversão da migração recusa com mensagem se existir item `combustivel_revenda`, e não apaga
  nada.

CFOP usados na sugestão, com a descrição oficial (tabela `dados/cfop_it2023002_v210.csv`):
- 5.656 e 6.656: "Venda de combustíveis ou lubrificantes adquiridos ou recebidos de terceiros
  destinados a consumidor ou usuário final." → combustível para consumo (1,6%).
- 5.667 e 6.667: "Venda de combustíveis ou lubrificantes a consumidor ou usuário final estabelecido
  em outra unidade da Federação [...]" → combustível para consumo (1,6%).
- 5.655 e 6.655: "Venda de combustíveis ou lubrificantes adquiridos ou recebidos de terceiros
  destinados à comercialização." → combustível para revenda (8%).
- 5.653 e 6.653 (produção própria, consumidor final): sem sugestão.
"""

import importlib
from types import SimpleNamespace

import django.apps
import pytest
from django.db import IntegrityError, transaction

from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.cfop import e_devolucao_de_venda_de_combustivel
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

MIGRACAO = importlib.import_module("apps.fiscal.migrations.0012_dl083_combustivel_revenda")

pytestmark = pytest.mark.django_db


def test_rotulos_das_duas_naturezas_de_combustivel():
    assert (
        NaturezaOperacaoNFe.COMBUSTIVEL.label
        == "Revenda de combustíveis para consumo (1,6% no IRPJ)"
    )
    assert (
        NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA.label
        == "Revenda de combustíveis para revenda (8% no IRPJ)"
    )
    assert NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA.value == "combustivel_revenda"


def test_combustivel_revenda_tem_papel_mercado_e_segregacao_da_combustivel():
    from apps.fiscal.models import CATALOGO_NATUREZA_NFE

    consumo = CATALOGO_NATUREZA_NFE[NaturezaOperacaoNFe.COMBUSTIVEL]
    revenda = CATALOGO_NATUREZA_NFE[NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA]
    assert (revenda.papel, revenda.mercado, revenda.segregacao) == (
        consumo.papel,
        consumo.mercado,
        consumo.segregacao,
    )
    assert (revenda.papel, revenda.mercado, revenda.segregacao) == ("receita", "interno", "normal")


def test_lista_do_check_de_banco_e_igual_ao_enum_de_naturezas():
    """A migração 0012 recria o CHECK com a lista literal. Se o enum mudar sem a migração, o banco
    recusa uma natureza que o Python aceita. Esta conferência pega o desvio."""
    assert set(MIGRACAO._NATUREZAS_NOVAS) == set(NaturezaOperacaoNFe.values)
    assert len(MIGRACAO._NATUREZAS_NOVAS) == len(set(MIGRACAO._NATUREZAS_NOVAS))
    assert set(MIGRACAO._NATUREZAS_ANTIGAS) == set(NaturezaOperacaoNFe.values) - {
        "combustivel_revenda"
    }


def _sugestao(cfop, csosn="102", cst=None):
    documento = SimpleNamespace(
        fin_nfe="1", id_dest="1", transferencia_entre_estabelecimentos=False
    )
    item = SimpleNamespace(cfop=cfop, csosn=csosn, cst=cst)
    return servico.sugerir_natureza_item(documento, item, "saida_propria")


@pytest.mark.parametrize(
    ("cfop", "natureza"),
    [
        ("5656", NaturezaOperacaoNFe.COMBUSTIVEL),
        ("6656", NaturezaOperacaoNFe.COMBUSTIVEL),
        ("5667", NaturezaOperacaoNFe.COMBUSTIVEL),
        ("6667", NaturezaOperacaoNFe.COMBUSTIVEL),
        ("5655", NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA),
        ("6655", NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA),
    ],
)
def test_sugestao_de_combustivel_pela_descricao_oficial_do_cfop(cfop, natureza):
    assert _sugestao(cfop).natureza == natureza


@pytest.mark.parametrize("cfop", ["5653", "6653", "5651"])
def test_venda_de_combustivel_de_producao_propria_nao_tem_sugestao(cfop):
    """A descrição é de "produção do estabelecimento": a natureza não está confirmada pelo CFOP."""
    assert _sugestao(cfop).natureza is None


@pytest.mark.parametrize(
    ("cfop", "csosn", "cst", "natureza"),
    [
        ("5656", "500", None, NaturezaOperacaoNFe.COMBUSTIVEL),
        ("5656", None, "60", NaturezaOperacaoNFe.COMBUSTIVEL),
        ("5655", "500", None, NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA),
        ("5655", None, "60", NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA),
    ],
)
def test_combustivel_com_icms_ja_recolhido_segue_o_cfop(cfop, csosn, cst, natureza):
    """Ajuste de integração do arquiteto: na venda de combustível, CSOSN 500 ou CST 60 é o caso
    normal do posto e não conflita com o CFOP (antes, toda NFC-e de posto ficava sem sugestão)."""
    assert _sugestao(cfop, csosn=csosn, cst=cst).natureza == natureza


def test_combustivel_com_st_substituido_fora_do_cfop_de_combustivel_continua_substituido():
    assert _sugestao("5405", csosn="500").natureza == NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO


@pytest.mark.parametrize(("csosn", "cst"), [("201", None), (None, "10")])
def test_combustivel_com_sinal_de_substituto_continua_em_conflito(csosn, cst):
    sugestao = _sugestao("5656", csosn=csosn, cst=cst)
    assert sugestao.natureza is None
    assert "conflito" in sugestao.motivo


@pytest.mark.parametrize(
    ("cfop", "esperado"),
    [
        ("1660", True),
        ("1661", True),
        ("1662", True),
        ("2660", True),
        ("2662", True),
        ("1.662", True),
        ("1202", False),
        ("1651", False),
        ("5660", False),
        ("5656", False),
        ("9999", False),
    ],
)
def test_devolucao_de_venda_de_combustivel_pela_tabela_oficial(cfop, esperado):
    """Devolução de venda de combustível (indDevol 1, "Devolução de venda de combustíveis").
    A devolução de COMPRA de combustível (5.660) e a compra (1.651) não são devolução de venda."""
    assert e_devolucao_de_venda_de_combustivel(cfop) is esperado


@pytest.fixture
def escrituracao_rascunho(escritorio_a):
    gestor = usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-combustivel-dl083")
    from apps.empresas.models import Empresa

    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5656", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
            vnf="100.00",
            totais={"vProd": "100.00"},
            numero="901",
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    return esc, gestor


def test_banco_aceita_a_natureza_combustivel_revenda(escrituracao_rascunho):
    esc, _ = escrituracao_rascunho
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA
    )
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == "combustivel_revenda"


def test_banco_recusa_natureza_fora_da_lista(escrituracao_rascunho):
    """O CHECK continua valendo: um valor fora do catálogo não entra, nem por SQL direto."""
    esc, _ = escrituracao_rascunho
    with pytest.raises(IntegrityError), transaction.atomic():
        NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="combustivel_qualquer")


def test_reversao_da_migracao_recusa_com_item_combustivel_revenda(escrituracao_rascunho):
    """Com um item `combustivel_revenda`, a reversão levanta erro com a mensagem, antes de qualquer
    DDL. Nada é apagado, e a natureza continua no item."""
    esc, _ = escrituracao_rascunho
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA
    )
    with pytest.raises(RuntimeError) as erro:
        MIGRACAO._recusar_reversao_com_combustivel_revenda(django.apps.apps, None)
    assert "Reversão da migração 0012 recusada" in str(erro.value)
    assert "1 item(ns)" in str(erro.value)
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == "combustivel_revenda"


def test_reversao_da_migracao_passa_sem_item_combustivel_revenda(escrituracao_rascunho):
    esc, _ = escrituracao_rascunho
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL
    )
    MIGRACAO._recusar_reversao_com_combustivel_revenda(django.apps.apps, None)
