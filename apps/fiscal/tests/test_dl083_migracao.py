"""DL-083 (A2): reversão e reaplicação da migração 0012 com dados reais, pelo `migrate` do Django.

A reversão da 0012 (natureza `combustivel_revenda` e `devolucao_combustivel_consumo`):
(i)   item em RASCUNHO com natureza nova: a reversão recusa com a mensagem, e nada muda no banco;
(ii)  item EFETIVADA e depois ESTORNADA com natureza nova: a reversão passa. O CHECK antigo fica
como
      NOT VALID (vale para linhas novas; a estornada, imutável, fica como está);
(iii) a reaplicação recria o CHECK com a lista nova, VALIDADO.

Os testes usam `transaction=True`: a reversão precisa rodar fora de uma transação de teste. Cada um
termina com o banco no estado mais recente (head), como estava.
"""

import pytest
from django.core.management import call_command
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

NOME_CHECK = "natureza_item_nfe_valida"
ULTIMA_ANTES = "0011_dl081_escrituracao_nfe"


def _check_do_banco():
    """(convalidated, definição) do CHECK de natureza, lidos do catálogo do PostgreSQL."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT convalidated, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            [NOME_CHECK],
        )
        return cursor.fetchone()


def _gestor_e_empresa(escritorio):
    gestor = usuario_com_papel(escritorio, Papel.GESTOR, "gestor-migracao-dl083")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Migracao DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    return gestor, empresa


def _nota_saida(escritorio, gestor, empresa, numero):
    return receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5656", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
            vnf="100.00",
            totais={"vProd": "100.00"},
            numero=str(numero),
        ),
    )


@pytest.fixture
def rascunho(escritorio_a):
    gestor, empresa = _gestor_e_empresa(escritorio_a)
    documento = _nota_saida(escritorio_a, gestor, empresa, 801)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    return esc, gestor


@pytest.mark.django_db(transaction=True)
def test_reversao_recusa_com_item_em_rascunho_com_natureza_nova_e_nao_muda_nada(rascunho):
    esc, _gestor = rascunho
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA
    )
    convalidado_antes = _check_do_banco()[0]

    with pytest.raises(RuntimeError) as erro:
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)

    assert "Reversão da migração 0012 recusada" in str(erro.value)
    assert "combustivel_revenda em 1" in str(erro.value)
    # Nada mudou: o CHECK novo continua como estava, e a natureza continua no item.
    assert convalidado_antes is True
    assert _check_do_banco()[0] is True
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == "combustivel_revenda"


@pytest.mark.django_db(transaction=True)
def test_reversao_passa_com_efetivada_estornada_e_o_check_antigo_fica_not_valid(escritorio_a):
    gestor, empresa = _gestor_e_empresa(escritorio_a)
    documento = _nota_saida(escritorio_a, gestor, empresa, 802)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA
    )
    servico.efetivar(esc, usuario=gestor)
    servico.estornar(esc, "migração DL083: teste de reversão", usuario=gestor)
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == "combustivel_revenda"

    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)

    convalidado, definicao = _check_do_banco()
    assert convalidado is False  # NOT VALID: vale para linhas novas, não revalida a estornada.
    assert "combustivel_revenda" not in definicao
    assert "devolucao_combustivel_consumo" not in definicao
    # A estornada é imutável: a natureza continua no item, e o banco aceita a leitura.
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == "combustivel_revenda"

    # (iii) reaplicação: o CHECK com a lista nova volta, validado.
    call_command("migrate", "fiscal", "0012", verbosity=0)
    convalidado, definicao = _check_do_banco()
    assert convalidado is True
    assert "combustivel_revenda" in definicao
    assert "devolucao_combustivel_consumo" in definicao


@pytest.mark.django_db(transaction=True)
def test_reaplicacao_com_devolucao_de_combustivel_consumo_estornada_valida_o_check(escritorio_a):
    """A devolução de combustível para consumo (29 caracteres) cabe na coluna depois da reversão e
    da
    reaplicação, e o CHECK novo volta validado. A coluna não é encolhida na reversão."""
    gestor, empresa = _gestor_e_empresa(escritorio_a)
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="1662", vprod="50.00", icms_xml=xml.icms(csosn="102"))],
            vnf="50.00",
            totais={"vProd": "50.00"},
            numero="803",
            tp_nf="0",
            fin_nfe="4",
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO
    )
    servico.efetivar(esc, usuario=gestor)
    servico.estornar(esc, "migração DL083: devolução de consumo", usuario=gestor)

    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _check_do_banco()[0] is False
    call_command("migrate", "fiscal", "0012", verbosity=0)

    assert _check_do_banco()[0] is True
    assert NaturezaItemNFe.objects.get(escrituracao=esc).natureza == (
        "devolucao_combustivel_consumo"
    )
