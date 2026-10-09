"""DL-081 (frente A), reclassificação em massa por filtro (item 7; critério 8 do plano).

Só altera rascunho, registra uma trilha por escrituração afetada, devolve a contagem e nunca toca
nota de outra empresa. Se algum item que casa não aceita a natureza, nada muda (operação atômica).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EstadoEscrituracao, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-reclass-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Reclass Emitente Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Reclass Outra Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def nota_com_itens(escritorio, gestor, empresa_da_nota, *, numero, itens, dh_emi, efetivar=False):
    """`itens` = lista de (cfop, csosn, ncm, vprod)."""
    dets = [
        xml.det(
            i + 1,
            cfop=cfop,
            vprod=vprod,
            ncm=ncm,
            icms_xml=xml.icms(csosn=csosn),
        )
        for i, (cfop, csosn, ncm, vprod) in enumerate(itens)
    ]
    total = sum(Decimal(v) for *_, v in itens)
    documento = receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=dets,
            vnf=str(total),
            totais={"vProd": str(total)},
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", empresa_da_nota.cnpj),
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=gestor)
    if efetivar:
        NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=N.REVENDA)
        esc = servico.efetivar(esc, usuario=gestor)
    return esc


def naturezas_da(esc):
    return sorted(
        (n.item.n_item, n.natureza)
        for n in NaturezaItemNFe.objects.select_related("item").filter(escrituracao=esc)
    )


def test_reclassifica_so_os_rascunhos_que_casam(escritorio_a, gestor, empresa):
    a = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=1,
        itens=[("5102", "102", "22030000", "100.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    b = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=2,
        itens=[("5101", "102", "22030000", "50.00")],
        dh_emi="2026-03-11T10:00:00-03:00",
    )
    efetivada = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=3,
        itens=[("5102", "102", "22030000", "70.00")],
        dh_emi="2026-03-12T10:00:00-03:00",
        efetivar=True,
    )
    NaturezaItemNFe.objects.filter(escrituracao__in=[a, b]).update(natureza=N.REVENDA)
    resultado = servico.reclassificar_em_massa(
        empresa,
        N.PRODUCAO_PROPRIA,
        servico.FiltrosReclassificacao(cfop="5102"),
        usuario=gestor,
    )
    assert resultado.escrituracoes_afetadas == 1
    assert resultado.itens_alterados == 1
    assert naturezas_da(a) == [(1, N.PRODUCAO_PROPRIA)]
    assert naturezas_da(b) == [(1, N.REVENDA)]
    efetivada.refresh_from_db()
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert naturezas_da(efetivada) == [(1, N.REVENDA)]


def test_reclassificacao_registra_uma_trilha_por_escrituracao_afetada(
    escritorio_a, gestor, empresa
):
    a = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=10,
        itens=[("5102", "102", "22030000", "10.00"), ("5102", "102", "22030000", "20.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    b = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=11,
        itens=[("5102", "102", "22030000", "30.00")],
        dh_emi="2026-03-11T10:00:00-03:00",
    )
    antes = RegistroAuditoria.objects.filter(acao="escrituracao_nfe.reclassificada").count()
    resultado = servico.reclassificar_em_massa(
        empresa, N.PRODUCAO_PROPRIA, servico.FiltrosReclassificacao(cfop="5102"), usuario=gestor
    )
    assert resultado.escrituracoes_afetadas == 2
    assert resultado.itens_alterados == 3
    trilhas = RegistroAuditoria.objects.filter(acao="escrituracao_nfe.reclassificada")
    assert trilhas.count() - antes == 2
    assert {t.objeto_id for t in trilhas.order_by("-id")[:2]} == {str(a.pk), str(b.pk)}


def test_filtro_por_ncm_e_por_periodo(escritorio_a, gestor, empresa):
    dentro = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=20,
        itens=[("5102", "102", "22030000", "10.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    fora_de_periodo = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=21,
        itens=[("5102", "102", "22030000", "10.00")],
        dh_emi="2026-04-10T10:00:00-03:00",
    )
    outro_ncm = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=22,
        itens=[("5102", "102", "84713012", "10.00")],
        dh_emi="2026-03-10T11:00:00-03:00",
    )
    filtros = servico.FiltrosReclassificacao(
        inicio=date(2026, 3, 1),
        fim=date(2026, 3, 31),
        ncm="22030000",
    )
    resultado = servico.reclassificar_em_massa(empresa, N.PRODUCAO_PROPRIA, filtros, usuario=gestor)
    assert resultado.itens_alterados == 1
    assert naturezas_da(dentro) == [(1, N.PRODUCAO_PROPRIA)]
    assert naturezas_da(fora_de_periodo) == [(1, "")]
    assert naturezas_da(outro_ncm) == [(1, "")]


def test_filtro_por_cst_csosn(escritorio_a, gestor, empresa):
    st = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=30,
        itens=[("5405", "500", "22030000", "10.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    resultado = servico.reclassificar_em_massa(
        empresa,
        N.REVENDA_ST_SUBSTITUIDO,
        servico.FiltrosReclassificacao(cst_csosn="500"),
        usuario=gestor,
    )
    assert resultado.itens_alterados == 1
    assert naturezas_da(st) == [(1, N.REVENDA_ST_SUBSTITUIDO)]


def test_nota_de_outra_empresa_nao_e_tocada(escritorio_a, gestor, empresa, outra):
    alheia = nota_com_itens(
        escritorio_a,
        gestor,
        outra,
        numero=40,
        itens=[("5102", "102", "22030000", "10.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    resultado = servico.reclassificar_em_massa(
        empresa, N.PRODUCAO_PROPRIA, servico.FiltrosReclassificacao(cfop="5102"), usuario=gestor
    )
    assert resultado.itens_alterados == 0
    assert naturezas_da(alheia) == [(1, "")]


def test_natureza_que_nao_cabe_em_uma_nota_recusa_tudo_sem_gravar(escritorio_a, gestor, empresa):
    """Devolução (natureza 9) não cabe em saída própria: a operação inteira é recusada."""
    saida = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=50,
        itens=[("5102", "102", "22030000", "10.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.reclassificar_em_massa(
            empresa, N.DEVOLUCAO_VENDA, servico.FiltrosReclassificacao(cfop="5102"), usuario=gestor
        )
    assert naturezas_da(saida) == [(1, "")]


def test_natureza_fora_do_catalogo_e_recusada(escritorio_a, gestor, empresa):
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.reclassificar_em_massa(
            empresa, "inventada", servico.FiltrosReclassificacao(), usuario=gestor
        )


def test_sem_casamento_devolve_zero(escritorio_a, gestor, empresa):
    resultado = servico.reclassificar_em_massa(
        empresa, N.REVENDA, servico.FiltrosReclassificacao(cfop="5999"), usuario=gestor
    )
    assert (resultado.escrituracoes_afetadas, resultado.itens_alterados) == (0, 0)
