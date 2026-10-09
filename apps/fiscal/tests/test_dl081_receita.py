"""DL-081 (frente A), receita do Simples e RBT12 com a NF-e (item 4 e critério 5 do plano).

Regras conferidas, com valores escritos à mão:
- NF-e efetivada entra na receita do mês, por mercado (interno, ou externo na exportação);
- devolução deduz no MÊS da devolução e, se passar da receita do mês, transporta o saldo (HI-121,
  Res. CGSN 140, art. 17);
- cancelamento deduz no período de origem: a nota cancelada sai da composição do seu mês (art. 18);
- rascunho e estornada não entram; natureza que não é receita soma zero (HI-124);
- o RBT12 soma a NF-e (teste de referência com o número escrito à mão);
- a composição é por empresa: a NF-e de uma empresa não altera a de outra;
- efetivar em mês confirmado reabre a confirmação (gancho da DL-074).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EstadoEscrituracao,
    EventoNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    fixar_hoje,
    fixar_inicio_de_uso,
    preparar_simples,
    sequencia,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe
ZERO = Decimal("0.00")


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-receita-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Receita Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra Empresa Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def nfe_efetivada(
    escritorio,
    usuario,
    empresa_da_nota,
    *,
    valor,
    natureza,
    numero,
    dh_emi="2026-03-15T10:00:00-03:00",
    tp_nf="1",
    fin="1",
    cfop="5102",
    id_dest="1",
    efetivar=True,
):
    """Recebe uma nota de UM item, confirma a natureza e efetiva (ou só cria o rascunho)."""
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            tp_nf=tp_nf,
            fin_nfe=fin,
            id_dest=id_dest,
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    if efetivar:
        esc = servico.efetivar(esc, usuario=usuario)
    return documento, esc


def cancelar(escritorio, documento, empresa_da_nota):
    EventoNFe.objects.create(
        escritorio=escritorio,
        identificador=f"ID110111{documento.chave}01",
        tp_evento="110111",
        n_seq_evento=1,
        chave=documento.chave,
        dh_evento=documento.dh_emissao,
        autor_tipo_documento="CNPJ",
        autor_documento=CNPJ_EMITENTE_A,
        c_stat="135",
        xml_original=b"<evento-sintetico/>",
        sha256_arquivo="1" * 64,
    )


def composicao(empresa, ano, mes):
    return servico_receita.composicao_do_mes(empresa, ano, mes)


# --- a receita do mês, por mercado -------------------------------------------------------------


def test_mes_sem_nfe_nao_tem_parcela_nova(empresa):
    """Critério do plano: meses sem NF-e não mudam. Tudo zero nas parcelas novas."""
    comp = composicao(empresa, 2026, 3)
    for mercado in (comp.interno, comp.externo):
        assert mercado.mercadoria == ZERO
        assert mercado.devolucao == ZERO
        assert mercado.saldo_entrada == ZERO
        assert mercado.deduzido == ZERO
        assert mercado.saldo_transportado == ZERO
        assert mercado.total == ZERO


def test_nfe_de_revenda_entra_como_receita_interna(escritorio_a, gestor, empresa):
    nfe_efetivada(escritorio_a, gestor, empresa, valor="2880.00", natureza=N.REVENDA, numero=1)
    comp = composicao(empresa, 2026, 3)
    assert comp.interno.mercadoria == Decimal("2880.00")
    assert comp.interno.total == Decimal("2880.00")
    assert comp.externo.total == ZERO


def test_exportacao_entra_no_mercado_externo(escritorio_a, gestor, empresa):
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="500.00",
        natureza=N.EXPORTACAO_DIRETA,
        numero=2,
        id_dest="3",
        cfop="7101",
    )
    comp = composicao(empresa, 2026, 3)
    assert comp.externo.mercadoria == Decimal("500.00")
    assert comp.interno.total == ZERO


def test_natureza_que_nao_e_receita_soma_zero(escritorio_a, gestor, empresa):
    """Remessa (10), transferência (11), bonificação (12), cupom (13) e ajuste somam zero
    (HI-124)."""
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.REMESSA_RETORNO,
        numero=3,
        cfop="5949",
    )
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="200.00",
        natureza=N.TRANSFERENCIA,
        numero=4,
        cfop="5151",
    )
    nfe_efetivada(
        escritorio_a, gestor, empresa, valor="50.00", natureza=N.BONIFICACAO, numero=5, cfop="5910"
    )
    nfe_efetivada(
        escritorio_a, gestor, empresa, valor="100.00", natureza=N.CUPOM_NFCE, numero=6, cfop="5929"
    )
    comp = composicao(empresa, 2026, 3)
    assert comp.interno.total == ZERO
    assert comp.interno.mercadoria == ZERO


def test_rascunho_e_estornada_nao_entram(escritorio_a, gestor, empresa):
    _, rascunho = nfe_efetivada(
        escritorio_a, gestor, empresa, valor="1000.00", natureza=N.REVENDA, numero=7, efetivar=False
    )
    _, efetivada = nfe_efetivada(
        escritorio_a, gestor, empresa, valor="700.00", natureza=N.REVENDA, numero=8
    )
    servico.estornar(efetivada, "Teste de estorno", usuario=gestor)
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert composicao(empresa, 2026, 3).interno.total == ZERO


# --- devolução e saldo transportado (HI-121) ---------------------------------------------------


def test_devolucao_deduz_no_mes_da_devolucao_e_nao_no_da_venda(escritorio_a, gestor, empresa):
    """Venda de 2.880,00 em março. Em abril, receita de 1.500,00 e devolução de 1.000,00: abril
    deduz
    1.000,00 e fica com 500,00; março não muda (a dedução não volta para a venda)."""
    nfe_efetivada(escritorio_a, gestor, empresa, valor="2880.00", natureza=N.REVENDA, numero=10)
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="1500.00",
        natureza=N.REVENDA,
        numero=12,
        dh_emi="2026-04-05T10:00:00-03:00",
    )
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="1000.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=11,
        dh_emi="2026-04-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    marco = composicao(empresa, 2026, 3)
    abril = composicao(empresa, 2026, 4)
    assert marco.interno.total == Decimal("2880.00")
    assert abril.interno.devolucao == Decimal("1000.00")
    assert abril.interno.deduzido == Decimal("1000.00")
    assert abril.interno.total == Decimal("500.00")
    assert abril.interno.saldo_transportado == ZERO


def test_devolucao_maior_que_a_receita_do_mes_transporta_o_saldo(escritorio_a, gestor, empresa):
    """Maio: devolução de 500,00 sem receita -> saldo de 500,00 para junho.
    Junho: receita de 300,00 absorve 300,00 e transporta 200,00 para julho.
    Julho: receita de 1.000,00 absorve 200,00 e fica com 800,00."""
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="500.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=20,
        dh_emi="2026-05-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    maio = composicao(empresa, 2026, 5)
    assert maio.interno.devolucao == Decimal("500.00")
    assert maio.interno.deduzido == ZERO
    assert maio.interno.saldo_transportado == Decimal("500.00")
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.REVENDA,
        numero=21,
        dh_emi="2026-06-10T10:00:00-03:00",
    )
    junho = composicao(empresa, 2026, 6)
    assert junho.interno.saldo_entrada == Decimal("500.00")
    assert junho.interno.deduzido == Decimal("300.00")
    assert junho.interno.total == ZERO
    assert junho.interno.saldo_transportado == Decimal("200.00")
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="1000.00",
        natureza=N.REVENDA,
        numero=22,
        dh_emi="2026-07-10T10:00:00-03:00",
    )
    julho = composicao(empresa, 2026, 7)
    assert julho.interno.saldo_entrada == Decimal("200.00")
    assert julho.interno.deduzido == Decimal("200.00")
    assert julho.interno.total == Decimal("800.00")
    assert julho.interno.saldo_transportado == ZERO


def test_cancelamento_deduz_no_periodo_de_origem(escritorio_a, gestor, empresa):
    """Venda de 1.000,00 em março, cancelada depois de escriturada: sai da composição de MARÇO.
    Abril, sem nada, continua zero (art. 18: o cancelamento volta ao período da operação)."""
    documento, _ = nfe_efetivada(
        escritorio_a, gestor, empresa, valor="1000.00", natureza=N.REVENDA, numero=30
    )
    assert composicao(empresa, 2026, 3).interno.total == Decimal("1000.00")
    cancelar(escritorio_a, documento, empresa)
    assert composicao(empresa, 2026, 3).interno.total == ZERO
    assert composicao(empresa, 2026, 4).interno.total == ZERO


def test_devolucao_de_nota_cancelada_nao_deduz(escritorio_a, gestor, empresa):
    """Devolução de 400,00 em agosto, com receita de 1.000,00 no mês para absorvê-la. Cancelada,
    a devolução não deduz: a receita volta a ser 1.000,00."""
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="1000.00",
        natureza=N.REVENDA,
        numero=32,
        dh_emi="2026-08-02T10:00:00-03:00",
    )
    documento, _ = nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="400.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=31,
        dh_emi="2026-08-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    assert composicao(empresa, 2026, 8).interno.deduzido == Decimal("400.00")
    cancelar(escritorio_a, documento, empresa)
    assert composicao(empresa, 2026, 8).interno.deduzido == ZERO
    assert composicao(empresa, 2026, 8).interno.total == Decimal("1000.00")


def test_saldo_nao_vaza_para_outra_empresa(escritorio_a, gestor, empresa, outra_empresa):
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="500.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=40,
        dh_emi="2026-09-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    assert composicao(empresa, 2026, 9).interno.saldo_transportado == Decimal("500.00")
    assert composicao(outra_empresa, 2026, 9).interno.saldo_transportado == ZERO
    assert composicao(outra_empresa, 2026, 10).interno.saldo_entrada == ZERO


def test_porta_do_pre_das_e_do_presumido_sinaliza_o_mes_e_o_trimestre(
    escritorio_a, gestor, empresa
):
    assert servico_receita.componente_nfe_no_mes(empresa, 2026, 2) is False
    assert servico_receita.receita_de_nfe_no_mes(empresa, 2026, 2) is False
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="100.00",
        natureza=N.REVENDA,
        numero=50,
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    assert servico_receita.componente_nfe_no_mes(empresa, 2026, 2) is True
    assert servico_receita.receita_de_nfe_no_mes(empresa, 2026, 2) is True


def test_saldo_de_devolucao_faz_o_pre_das_do_mes_seguinte_recusar(escritorio_a, gestor, empresa):
    """Devolução de maio sem receita: junho não tem NF-e nova, mas recebe o saldo. Mesmo assim, há
    componente de NF-e no mês (a composição mudou): a porta responde True."""
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="500.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=51,
        dh_emi="2026-05-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    assert servico_receita.componente_nfe_no_mes(empresa, 2026, 6) is True
    assert servico_receita.receita_de_nfe_no_mes(empresa, 2026, 6) is False


# --- RBT12 com NF-e (critério 5) ---------------------------------------------------------------


def test_rbt12_soma_a_nfe_com_numero_escrito_a_mao(escritorio_a, gestor, empresa, monkeypatch):
    """Simples desde 2018 (aberta em 2015). PA março de 2026: janela = mar/2025 a fev/2026.
    Venda de 1.000,00 em out/2025. Em jan/2026: venda de 500,00 e devolução de 300,00 (deduz 300,00,
    fica 200,00). RBT12 interno = 1.000,00 + 200,00 = 1.200,00."""
    fixar_inicio_de_uso(empresa, 2025, 1)
    preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))
    fixar_hoje(monkeypatch, date(2026, 4, 15))
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="1000.00",
        natureza=N.REVENDA,
        numero=60,
        dh_emi="2025-10-10T10:00:00-03:00",
    )
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="500.00",
        natureza=N.REVENDA,
        numero=62,
        dh_emi="2026-01-12T10:00:00-03:00",
    )
    nfe_efetivada(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=61,
        dh_emi="2026-01-10T10:00:00-03:00",
        tp_nf="0",
        fin="4",
        cfop="1202",
    )
    confirmar_meses(empresa, gestor, sequencia(2025, 3, 12))
    resultado = apuracao.rbt12(empresa, 2026, 3)
    assert resultado.por_mercado["interno"].soma == Decimal("1200.00")


# --- mês confirmado (gancho da DL-074) ---------------------------------------------------------


def test_efetivar_em_mes_confirmado_marca_a_retificar(escritorio_a, gestor, empresa, monkeypatch):
    fixar_hoje(monkeypatch, date(2026, 4, 15))
    fixar_inicio_de_uso(empresa, 2025, 1)
    confirmar_meses(empresa, gestor, [(2026, 3)])
    assert servico_receita.situacao_do_mes(empresa, 2026, 3) == servico_receita.SITUACAO_CONFIRMADO
    nfe_efetivada(escritorio_a, gestor, empresa, valor="250.00", natureza=N.REVENDA, numero=70)
    assert servico_receita.situacao_do_mes(empresa, 2026, 3) == servico_receita.SITUACAO_A_RETIFICAR
