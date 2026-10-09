"""DL-081, correção da rodada 1 (A3): itens e leitura da nota são imutáveis no BANCO.

A receita do Simples e o RBT12 leem `ItemNFe.receita_bruta_item` e `ind_tot` ao vivo. Antes da
correção, um UPDATE por SQL direto no item mudava a receita de uma escrituração efetivada, sem
trilha e sem alerta. Os gatilhos da migração 0011 (`fiscal_itens_nfe_imutaveis`) recusam INSERT,
UPDATE e DELETE em `fiscal_itemnfe` e em `fiscal_leituraitensnfe` quando a nota tem escrituração
efetivada ou estornada. Sem essa escrituração, o rascunho continua podendo ser refeito.

Todos os testes usam SQL ou ORM direto: a recusa tem de vir do banco, não do Python.
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import itens_nfe
from apps.fiscal.models import (
    EscrituracaoNFe,
    ItemNFe,
    LeituraItensNFe,
    NaturezaOperacaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

SQLSTATE_CHECAGEM = "23514"
NOME_DA_RESTRICAO = "fiscal_itemnfe_imutavel_depois_de_efetivada"


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-imut-itens-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Imutabilidade Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _nota(escritorio, gestor):
    """Nota de um item, receita 100,00 = vNF 100,00: efetiva sem divergência."""
    return receber(escritorio, gestor, xml.nfe(dets=[xml.det(1, vprod="100.00")], vnf="100.00"))


def _efetivada(escritorio, gestor, emitente):
    documento = _nota(escritorio, gestor)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))
    servico.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, ids, gestor)
    servico.efetivar(esc, usuario=gestor)
    return documento, esc


def _sqlstate(erro) -> str:
    """Código SQL do erro do PostgreSQL (23514 = violação de checagem, como nos gatilhos da
    0011)."""
    return erro.value.__cause__.sqlstate


def _nome_da_restricao(erro) -> str:
    return erro.value.__cause__.diag.constraint_name


# --- Efetivada: o banco recusa, por SQL direto --------------------------------------------------


def test_update_da_receita_do_item_de_nota_efetivada_e_recusado_pelo_banco(
    escritorio_a, gestor, emitente
):
    """O caso do relatório: `receita_bruta_item = 1` mudava a composição de 150,00 para 51,00."""
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            ItemNFe.objects.filter(documento=documento).update(receita_bruta_item=Decimal("1.00"))
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    assert _nome_da_restricao(erro) == NOME_DA_RESTRICAO
    assert ItemNFe.objects.get(documento=documento).receita_bruta_item == Decimal("100.00")


def test_update_do_indtot_de_nota_efetivada_e_recusado_pelo_banco(escritorio_a, gestor, emitente):
    """`ind_tot = '0'` tirava a receita da composição (a composição caía para 1,00 no relatório)."""
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE fiscal_itemnfe SET ind_tot = '0' WHERE documento_id = %s",
                    [documento.pk],
                )
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    assert ItemNFe.objects.get(documento=documento).ind_tot == "1"


def test_insert_de_item_em_nota_efetivada_e_recusado_pelo_banco(escritorio_a, gestor, emitente):
    """Um item a mais muda a receita da nota, por isso o INSERT também é recusado."""
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            ItemNFe.objects.create(
                documento=documento,
                n_item=2,
                c_prod="000002",
                x_prod="Item inserido por SQL",
                ncm="22030000",
                cfop="5102",
                u_com="UN",
                q_com=Decimal("1.0000"),
                v_un_com=Decimal("50.0000000000"),
                v_prod=Decimal("50.00"),
                ind_tot="1",
                receita_bruta_item=Decimal("50.00"),
            )
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    assert ItemNFe.objects.filter(documento=documento).count() == 1


def test_delete_de_item_de_nota_efetivada_e_recusado_pelo_banco(escritorio_a, gestor, emitente):
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM fiscal_itemnfe WHERE documento_id = %s", [documento.pk])
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    assert ItemNFe.objects.filter(documento=documento).count() == 1


def test_update_da_leitura_de_nota_efetivada_e_recusado_pelo_banco(escritorio_a, gestor, emitente):
    """A leitura guarda os totais que a conferência usa (vNFTot, vII, IBS etc.). Também é
    protegida."""
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LeituraItensNFe.objects.filter(documento=documento).update(
                quantidade_itens=99, v_nf_tot=Decimal("1.00")
            )
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    leitura = LeituraItensNFe.objects.get(documento=documento)
    assert leitura.quantidade_itens == 1 and leitura.v_nf_tot is None


def test_delete_da_leitura_de_nota_efetivada_e_recusado_pelo_banco(escritorio_a, gestor, emitente):
    documento, _ = _efetivada(escritorio_a, gestor, emitente)
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LeituraItensNFe.objects.filter(documento=documento).delete()
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM
    assert LeituraItensNFe.objects.filter(documento=documento).exists()


def test_nota_estornada_continua_protegida(escritorio_a, gestor, emitente):
    """Estornada também é imutável: o histórico do ato fica como foi gravado."""
    documento, esc = _efetivada(escritorio_a, gestor, emitente)
    servico.estornar(esc, "Teste de imutabilidade do item", usuario=gestor)
    assert EscrituracaoNFe.objects.get(pk=esc.pk).estado == "estornada"
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            ItemNFe.objects.filter(documento=documento).update(receita_bruta_item=Decimal("1.00"))
    assert _sqlstate(erro) == SQLSTATE_CHECAGEM


# --- Sem escrituração efetivada: o rascunho continua podendo ser refeito -------------------------


def test_update_do_item_sem_escrituracao_efetivada_continua_possivel(
    escritorio_a, gestor, emitente
):
    """Sem escrituração, o banco não bloqueia: o rascunho e a releitura dependem disso."""
    documento = _nota(escritorio_a, gestor)
    itens_nfe.ler_itens(documento)
    ItemNFe.objects.filter(documento=documento).update(receita_bruta_item=Decimal("99.00"))
    assert ItemNFe.objects.get(documento=documento).receita_bruta_item == Decimal("99.00")


def test_update_do_item_com_rascunho_continua_possivel(escritorio_a, gestor, emitente):
    """Rascunho não é efetivação: o item pode ser alterado (a releitura de versão anterior faz
    isto)."""
    documento = _nota(escritorio_a, gestor)
    servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ItemNFe.objects.filter(documento=documento).update(receita_bruta_item=Decimal("99.00"))
    assert ItemNFe.objects.get(documento=documento).receita_bruta_item == Decimal("99.00")


def test_releitura_com_rascunho_recria_as_naturezas_vazias(escritorio_a, gestor, emitente):
    """A releitura de versão anterior troca itens e leitura. Com rascunho, a natureza antiga sai em
    cascata, e o rascunho precisa de uma linha de natureza VAZIA por item novo: sem ela, nunca se
    efetiva. A natureza antiga não é transportada (o contador confirma de novo)."""
    documento = _nota(escritorio_a, gestor)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    LeituraItensNFe.objects.filter(documento=documento).update(versao_leitor=1)
    itens_nfe.ler_itens(documento)
    assert (
        LeituraItensNFe.objects.get(documento=documento).versao_leitor
        == itens_nfe.VERSAO_LEITOR_ITENS
    )
    assert ItemNFe.objects.filter(documento=documento).count() == 1
    naturezas = EscrituracaoNFe.objects.get(pk=esc.pk).naturezas_dos_itens.all()
    assert [n.natureza for n in naturezas] == [""], "uma linha de natureza vazia por item novo"
