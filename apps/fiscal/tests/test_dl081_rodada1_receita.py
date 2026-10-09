"""DL-081, correção da rodada 1 (receita): mercado da devolução, absorção e indTot 0.

- A8: devolução com CFOP 3.201 (devolução de exportação) deduz o mercado EXTERNO, não o interno.
- X12: a comercial exportadora entra no mercado externo.
- X7 e X8: a devolução é absorvida também pela NFS-e e pela receita informada (não só pela NF-e).
- E2a, E2b e X6: item com indTot 0 fica fora da composição, da conferência e da segregação.
- E4b: o pré-DAS recusa um mês que só tem SALDO de devolução de meses anteriores.

Valores escritos à mão. Todo CNPJ é sintético (o do prestador de NFS-e de teste, para a mesma
empresa
ter NFS-e e NF-e).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    escriturar,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe
ZERO = Decimal("0.00")


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-receita-rodada1-dl081")


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Receita Rodada 1 Ltda", cnpj=CNPJ_PRESTADOR_PADRAO
    )
    fixar_inicio_de_uso(empresa, 2024, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _nota(
    escritorio,
    usuario,
    empresa_da_nota,
    *,
    valor,
    natureza,
    numero,
    cfop="5102",
    dets=None,
    devolucao=False,
    dh_emi="2026-03-15T10:00:00-03:00",
):
    """Uma NF-e efetivada com a natureza dada. `dets` (opcional) troca o item único."""
    if dets is None:
        dets = [xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))]
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=dets,
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            tp_nf="0" if devolucao else "1",
            fin_nfe="4" if devolucao else "1",
            emitente=("CNPJ", CNPJ_PRESTADOR_PADRAO),
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return servico.efetivar(esc, usuario=usuario)


def _composicao(empresa):
    return servico_receita.composicao_do_mes(empresa, 2026, 3)


# --- A8 e X12: o mercado da devolução e da comercial exportadora -----------------------------


def test_devolucao_de_exportacao_com_cfop_3201_deduz_o_mercado_externo(
    escritorio_a, gestor, empresa
):
    """Exportação de 1.000,00 e devolução de exportação (CFOP 3.201) de 300,00 no mês. O externo cai
    para 700,00. O interno não muda: antes da correção, a devolução deduzia o interno."""
    _nota(escritorio_a, gestor, empresa, valor="1000.00", natureza=N.EXPORTACAO_DIRETA, numero=1)
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=2,
        cfop="3201",
        devolucao=True,
    )
    composicao = _composicao(empresa)
    assert composicao.externo.total == Decimal("700.00")
    assert composicao.externo.devolucao == Decimal("300.00")
    assert composicao.interno.devolucao == ZERO


def test_devolucao_comum_com_cfop_1202_continua_deduzindo_o_mercado_interno(
    escritorio_a, gestor, empresa
):
    _nota(escritorio_a, gestor, empresa, valor="1000.00", natureza=N.REVENDA, numero=3)
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=4,
        cfop="1202",
        devolucao=True,
    )
    composicao = _composicao(empresa)
    assert composicao.interno.total == Decimal("700.00")
    assert composicao.externo.devolucao == ZERO


def test_comercial_exportadora_entra_no_mercado_externo(escritorio_a, gestor, empresa):
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="800.00",
        natureza=N.COMERCIAL_EXPORTADORA,
        numero=5,
        cfop="5501",
    )
    composicao = _composicao(empresa)
    assert composicao.externo.mercadoria == Decimal("800.00")
    assert composicao.interno.mercadoria == ZERO


# --- X7 e X8: a devolução é absorvida também pela NFS-e e pelo informado ----------------------


def test_devolucao_e_absorvida_pela_nfs_e_do_mes(escritorio_a, gestor, empresa):
    """NFS-e de 1.000,00 e devolução de 400,00 no mês: o total do interno é 600,00."""
    escriturar(
        escritorio_a,
        empresa,
        gestor,
        sufixo=901,
        competencia=(2026, 3),
        valor="1000.00",
    )
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="400.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=6,
        cfop="1202",
        devolucao=True,
    )
    composicao = _composicao(empresa)
    assert composicao.interno.documento == Decimal("1000.00")
    assert composicao.interno.total == Decimal("600.00")


def test_devolucao_e_absorvida_pela_receita_informada_do_mes(escritorio_a, gestor, empresa):
    """Receita informada confirmada de 1.000,00 e devolução de 400,00: o total do interno é
    600,00."""
    informar_e_confirmar(empresa, gestor, 2026, 3, "1000.00", mercado="interno")
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="400.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=7,
        cfop="1202",
        devolucao=True,
    )
    composicao = _composicao(empresa)
    assert composicao.interno.informado == Decimal("1000.00")
    assert composicao.interno.total == Decimal("600.00")


# --- E2a, E2b e X6: indTot 0 fica fora da composição, da conferência e da segregação ----------


def test_item_indtot_zero_fica_fora_da_composicao_da_conferencia_e_da_segregacao(
    escritorio_a, gestor, empresa
):
    """Nota de dois itens: o item 1 (100,00, indTot 1) e o item 2 (500,00, indTot 0). A nota vale
    100,00. O item 2 não entra na receita, na conferência nem na segregação."""
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="500.00", ind_tot="0"),
    ]
    esc = _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="100.00",
        natureza=N.REVENDA,
        numero=8,
        dets=dets,
    )
    assert _composicao(empresa).interno.mercadoria == Decimal("100.00")
    assert esc.soma_itens == Decimal("100.00")
    assert esc.receita_bruta == Decimal("100.00")
    segregacao = servico.segregacao_da_escrituracao(esc)
    assert sum(segregacao.values(), ZERO) == Decimal("100.00")


# --- E4b: o pré-DAS recusa o mês que só tem SALDO de devolução --------------------------------


def test_pre_das_recusa_o_mes_que_so_tem_saldo_de_devolucao_de_meses_anteriores(
    escritorio_a, gestor, empresa
):
    """Devolução de 300,00 em janeiro, sem venda. Fevereiro não tem NF-e, mas recebe o saldo de
    300,00.
    O pré-DAS de fevereiro recusa com o motivo de receita de mercadoria, de ponta a ponta."""
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=9,
        cfop="1202",
        devolucao=True,
        dh_emi="2026-01-10T10:00:00-03:00",
    )
    with pytest.raises(pre_das_servico.PreDasRecusado) as erro:
        pre_das_servico.pre_das(empresa, 2026, 2)
    codigos = [b.codigo for b in erro.value.bloqueios]
    assert "receita_de_mercadoria" in codigos
