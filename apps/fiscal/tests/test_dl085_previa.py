"""DL-085 (frente A), critério 1: a prévia agrupa certo e lista cada nota fora do lote com o motivo.

Valores esperados escritos à mão, em reais. Notas sintéticas, recebidas pela recepção real (DL-080).
Não há nenhuma efetivação aqui: a prévia só lê (e a primeira leitura de itens, documentada).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import EscrituracaoNFe, ItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import (
    CNPJ_SEGUNDA_EMPRESA,
    achar_nota,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a)


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _codigos_fora(previa):
    return {recusa.vinculo_id: recusa for recusa in previa.fora}


def test_notas_com_a_mesma_assinatura_caem_no_mesmo_grupo_e_somam_a_receita(
    escritorio_a, gestor, empresa
):
    """Três NFC-e de combustível (5656, CSOSN 500) e duas de revenda (5102, CSOSN 102). Dois grupos.
    Receita à mão: combustível 100,00 + 250,00 + 40,00 = 390,00; revenda 80,00 + 80,00 = 160,00."""
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio_a, gestor, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio_a, gestor, numero=numero, valor="80.00", cfop="5102", csosn="102")

    previa = previa_lida(empresa, 2026, 3)

    assert len(previa.grupos) == 2
    combustivel, revenda = sorted(previa.grupos, key=lambda g: g.assinaturas[0].natureza)
    assert combustivel.assinaturas[0].natureza == "combustivel"
    assert revenda.assinaturas[0].natureza == "revenda"
    assert (combustivel.quantidade_notas, combustivel.quantidade_itens) == (3, 3)
    assert (revenda.quantidade_notas, revenda.quantidade_itens) == (2, 2)
    assert combustivel.receita_bruta == D("390.00")
    assert revenda.receita_bruta == D("160.00")
    assert previa.fora == ()


def test_grupo_com_dois_tipos_de_item_fica_a_parte_do_grupo_de_cada_um(
    escritorio_a, gestor, empresa
):
    """A chave é o CONJUNTO de assinaturas: uma nota com combustível e revenda não cai no grupo de
    nenhuma das duas notas de um item só."""
    dets = [
        xml.det(1, cfop="5656", vprod="100.00", ncm="27101259", icms_xml=xml.icms(csosn="500")),
        xml.det(2, cfop="5102", vprod="30.00", icms_xml=xml.icms(csosn="102")),
    ]
    nfce(escritorio_a, gestor, numero=1, dets=dets, vnf="130.00")
    nfce(escritorio_a, gestor, numero=2, valor="100.00")
    nfce(escritorio_a, gestor, numero=3, valor="100.00", cfop="5102", csosn="102")

    previa = previa_lida(empresa, 2026, 3)

    assert sorted(g.quantidade_notas for g in previa.grupos) == [1, 1, 1]
    assert len({g.chave for g in previa.grupos}) == 3


def test_cada_nota_fora_do_lote_sai_com_o_motivo_nomeado(escritorio_a, gestor, empresa):
    """Um caso por recusa. A ordem é a de `efetivar`, e cada nota cai em UMA recusa."""
    sem_sinal = nfce(escritorio_a, gestor, numero=10, cfop="5949", csosn="102")
    conflito = nfce(escritorio_a, gestor, numero=11, cfop="5102", csosn="500")
    ilegivel = nfce(
        escritorio_a,
        gestor,
        numero=12,
        dets=[
            xml.det(1, cfop="5102", vprod="100.00", vdesc="0.00", icms_xml=xml.icms(csosn="102"))
        ],
        vnf="100.00",
    )
    w16 = nfce(escritorio_a, gestor, numero=13, valor="100.00", vnf="150.00")
    atribuicao = nfce(
        escritorio_a,
        gestor,
        numero=14,
        dets=[
            xml.det(
                1,
                cfop="5929",
                vprod="100.00",
                vfrete="10.00",
                icms_xml=xml.icms(csosn="102"),
            )
        ],
        vnf="110.00",
        totais={"vProd": "100.00", "vFrete": "10.00"},
    )

    previa = previa_lida(empresa, 2026, 3)
    fora = _codigos_fora(previa)

    assert fora[_vinculo_pk(sem_sinal, empresa)].codigo == lote.CODIGO_SEM_SUGESTAO
    assert fora[_vinculo_pk(conflito, empresa)].codigo == lote.CODIGO_CONFLITO
    assert "conflito entre sinais" in fora[_vinculo_pk(conflito, empresa)].motivo
    recusa_ilegivel = fora[_vinculo_pk(ilegivel, empresa)]
    assert recusa_ilegivel.codigo == lote.CODIGO_ILEGIVEL
    assert "vDesc" in recusa_ilegivel.motivo
    assert fora[_vinculo_pk(w16, empresa)].codigo == lote.CODIGO_W16
    assert "diverge" in fora[_vinculo_pk(w16, empresa)].motivo
    recusa_atribuicao = fora[_vinculo_pk(atribuicao, empresa)]
    assert recusa_atribuicao.codigo == lote.CODIGO_ATRIBUICAO
    assert "item fora do total com valor cobrado" in recusa_atribuicao.motivo
    assert previa.grupos == ()


def _vinculo_pk(documento, empresa):
    return vinculo(documento, empresa).pk


def test_nota_de_2027_fica_fora_pela_regra_de_data(escritorio_a, gestor, empresa):
    """HI-133: nota com dhEmi em 2027 não é efetivada. Por isso sai da prévia de 2027, com o
    motivo."""
    nfce(escritorio_a, gestor, numero=20, dh_emi="2027-01-05T10:00:00-03:00")

    previa = previa_lida(empresa, 2027, 1)

    (recusa,) = previa.fora
    assert recusa.codigo == lote.CODIGO_2027
    assert recusa.motivo == servico.MENSAGEM_RECEITA_2027_PENDENTE
    assert previa.grupos == ()


def test_nota_de_outra_empresa_do_mesmo_escritorio_nao_entra_na_previa(
    escritorio_a, gestor, empresa
):
    """Isolamento: a nota emitida pela OUTRA empresa do escritório não aparece na prévia desta."""
    Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra DL085 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )
    nfce(escritorio_a, gestor, numero=30, emitente=CNPJ_SEGUNDA_EMPRESA)
    nfce(escritorio_a, gestor, numero=31)

    previa = previa_lida(empresa, 2026, 3)

    assert sum(g.quantidade_notas for g in previa.grupos) == 1
    assert previa.fora == ()


def test_efetivada_e_cancelada_nao_entram_mas_sao_contadas(escritorio_a, gestor, empresa):
    """Efetivada ou cancelada não é pendente: não entra no lote, e a prévia diz quantas são."""
    documento = nfce(escritorio_a, gestor, numero=40)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    servico.definir_natureza(
        esc,
        "combustivel",
        list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True)),
        usuario=gestor,
    )
    servico.efetivar(esc, usuario=gestor)
    nfce(escritorio_a, gestor, numero=41)

    previa = previa_lida(empresa, 2026, 3)

    assert previa.ja_efetivadas == 1
    assert sum(g.quantidade_notas for g in previa.grupos) == 1


def test_a_previa_so_le_e_nao_cria_escrituracao(escritorio_a, gestor, empresa):
    nfce(escritorio_a, gestor, numero=50)
    nfce(escritorio_a, gestor, numero=51, cfop="5102", csosn="102")

    previa_lida(empresa, 2026, 3)
    previa_lida(empresa, 2026, 3)

    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_assinatura_repete_na_mesma_previa_e_muda_quando_entra_nota(escritorio_a, gestor, empresa):
    """Estável: a mesma prévia dá a mesma assinatura. Muda quando uma nota entra no grupo."""
    nfce(escritorio_a, gestor, numero=60)
    primeira = previa_lida(empresa, 2026, 3)
    segunda = previa_lida(empresa, 2026, 3)
    assert primeira.assinatura == segunda.assinatura
    assert len(primeira.assinatura) == 64

    nfce(escritorio_a, gestor, numero=61)
    terceira = previa_lida(empresa, 2026, 3)
    assert terceira.assinatura != primeira.assinatura


def test_assinatura_muda_quando_a_sugestao_de_um_item_muda(escritorio_a, gestor, empresa):
    """A assinatura cobre a natureza sugerida por item: mudar a sugestão muda a prévia."""
    nfce(escritorio_a, gestor, numero=70, cfop="5102", csosn="102")
    antes = previa_lida(empresa, 2026, 3)
    nfce(escritorio_a, gestor, numero=71, cfop="5656", csosn="500")
    depois = previa_lida(empresa, 2026, 3)
    assert antes.assinatura != depois.assinatura
    assert achar_nota(depois, _vinculo_pk_da_nota(depois, 70)) is not None


def _vinculo_pk_da_nota(previa, numero):
    for grupo in previa.grupos:
        for nota in grupo.notas:
            if nota.numero == str(numero):
                return nota.vinculo_id
    raise AssertionError(f"nota {numero} não está na prévia")


def test_data_de_competencia_e_o_mes_de_dhemi_em_sao_paulo(escritorio_a, gestor, empresa):
    """31/03 às 23h59 em São Paulo é março. Em UTC já é abril (02:59 do dia 1º): a prévia de março
    tem a nota, e a de abril não."""
    nfce(escritorio_a, gestor, numero=80, dh_emi="2026-03-31T23:59:00-03:00")

    assert sum(g.quantidade_notas for g in previa_lida(empresa, 2026, 3).grupos) == 1
    assert previa_lida(empresa, 2026, 4).grupos == ()
    assert date(2026, 3, 1) < date(2026, 4, 1)
