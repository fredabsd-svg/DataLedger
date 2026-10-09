"""DL-083 (HI-140, A4): devolução e saldo por atividade no Presumido, e os mutantes sobreviventes da
auditoria (M25/N01, N03/N06, M07b/N02, N10).

Os valores esperados são escritos à mão, em centavos, com a conta em comentário. Nenhum teste
calcula o
esperado chamando a função de produção. Dados sintéticos (`xml_nfe_dl081` e
`suporte_presumido_dl079`).

Conta do IRPJ usada aqui (Lucro Presumido, critério de competência, sem LC 224 nos casos pequenos):
imposto = 15% × base; base = Σ receita de cada atividade × percentual (8% comércio e indústria, 1,6%
revenda de combustíveis). O adicional de 10% só passa de 60.000,00 por trimestre, e nenhum caso aqui
passa.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as nfe_servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
COMBUSTIVEIS = tab.REVENDA_COMBUSTIVEIS
SERVICOS = tab.SERVICOS_GERAIS
D = Decimal

DH_01_01 = "2026-01-01T00:30:00-03:00"


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-saldo-dl083")


def _empresa(escritorio, gestor, atividade_padrao):
    """Lucro Presumido em 2026, critério de competência, atividade padrão informada."""
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Saldo DL083 Ltda", cnpj=CNPJ_PRESTADOR_PADRAO
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", gestor)
    atividade = presumido_servico.criar_atividade(
        empresa, {"atividade": atividade_padrao, "inicio": date(2026, 1, 1), "padrao": True}, gestor
    )
    return empresa, atividade


@pytest.fixture
def empresa(escritorio_a, gestor):
    """Padrão SERVICOS (32%): a NF-e de revenda ou de combustível não usa o padrão (cada item tem
    a atividade da sua natureza)."""
    return _empresa(escritorio_a, gestor, SERVICOS)[0]


@pytest.fixture
def empresa_comercio(escritorio_a, gestor):
    """Padrão COMÉRCIO e INDÚSTRIA (8%): a NFS-e e a receita informada caem em comércio."""
    return _empresa(escritorio_a, gestor, COMERCIO)


def _nfe(escritorio, gestor, empresa, *, numero, valor, dh_emi, cfop="5102", tp_nf="1", fin="1"):
    return receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", empresa.cnpj),
            tp_nf=tp_nf,
            fin_nfe=fin,
        ),
    )


def efetivar_nfe(escritorio, gestor, empresa, *, natureza, **dados):
    documento = _nfe(escritorio, gestor, empresa, **dados)
    esc = nfe_servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return nfe_servico.efetivar(esc, usuario=gestor)


def _apurar(empresa, trimestre):
    return presumido_servico.apurar_trimestre(empresa, 2026, trimestre)


def _numeros(apuracao):
    return {linha.numero for linha in apuracao.nfe}


# ---------------------------------------------------------------------------------------------
# N03 e N06: devolução de 10.000 entre comércio e combustível (trimestre com os dois)
# ---------------------------------------------------------------------------------------------


def test_devolucao_de_venda_deduz_do_comercio_e_nao_do_combustivel_irpj_1320(
    empresa, escritorio_a, gestor
):
    """T1: revenda 100.000,00 (8%), combustível para consumo 100.000,00 (1,6%) e devolução de venda
    de 10.000,00 (natureza devolucao_venda, 8%, CFOP 1202).
    Conta à mão: a devolução deduz do comércio: 100.000 − 10.000 = 90.000 × 8% = 7.200,00.
    Combustível: 100.000 × 1,6% = 1.600,00. Base: 8.800,00. IRPJ: 15% × 8.800 = 1.320,00.
    Se a devolução abatesse o combustível, a base seria 8.000 + 1.440 = 9.440, e o IRPJ 1.416,00."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=101,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=102,
        valor="100000.00",
        dh_emi="2026-02-11T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=103,
        valor="10000.00",
        dh_emi="2026-02-12T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.irpj is not None
    assert apuracao.irpj.imposto_sem_lc224 == D("1320.00")
    assert apuracao.devolucao_por_atividade == ((COMERCIO, D("10000.00")),)


def test_devolucao_de_combustivel_para_consumo_deduz_do_combustivel_irpj_1416(
    empresa, escritorio_a, gestor
):
    """O mesmo trimestre, com a devolução como devolucao_combustivel_consumo (1,6%). Conta à mão:
    comércio 100.000 × 8% = 8.000,00. Combustível: 90.000 × 1,6% = 1.440,00. Base 9.440,00.
    IRPJ: 15% × 9.440 = 1.416,00. Diferença para o caso anterior: 96,00
    (= 10.000 × 6,4% × 15%)."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=111,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=112,
        valor="100000.00",
        dh_emi="2026-02-11T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
        numero=113,
        valor="10000.00",
        dh_emi="2026-02-12T10:00:00-03:00",
        cfop="1662",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.irpj.imposto_sem_lc224 == D("1416.00")
    assert apuracao.devolucao_por_atividade == ((COMBUSTIVEIS, D("10000.00")),)


# ---------------------------------------------------------------------------------------------
# N06 e M07b/N02: a base da devolução inclui NFS-e e receita informada da atividade
# ---------------------------------------------------------------------------------------------


def test_devolucao_deduz_da_nfse_de_comercio_mesmo_sem_nfe_de_revenda(
    empresa_comercio, escritorio_a, gestor
):
    """M07b: NFS-e de 100.000,00 na atividade de comércio (padrão). Devolução de 10.000,00 (NF-e
    1202, sem NF-e de revenda). A base da devolução é a receita de comércio, que inclui a NFS-e.
    Deduzido: 10.000,00. Saldo: 0,00."""
    empresa = empresa_comercio[0]
    nota_efetivada(escritorio_a, empresa, gestor, 1, v_serv="100000.00", d_compet="2026-02-15")
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=121,
        valor="10000.00",
        dh_emi="2026-02-12T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.devolucao_deduzida == D("10000.00")
    assert apuracao.saldo_devolucao_transportado == D("0.00")


def test_devolucao_deduz_da_receita_informada_de_comercio(empresa_comercio, escritorio_a, gestor):
    """N02: receita informada de 100.000,00 na atividade de comércio, sem NFS-e nem NF-e de revenda.
    Devolução de 10.000,00: deduz 10.000,00 da receita informada."""
    empresa, atividade = empresa_comercio
    presumido_servico.criar_receita(
        empresa,
        2026,
        1,
        {
            "tipo": "presuncao",
            "valor": "100000.00",
            "descricao": "receita informada de comércio",
            "suporte": "dl083-saldo",
            "atividade_id": atividade.pk,
        },
        gestor,
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=131,
        valor="10000.00",
        dh_emi="2026-02-12T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.devolucao_deduzida == D("10000.00")
    assert apuracao.saldo_devolucao_transportado == D("0.00")


# ---------------------------------------------------------------------------------------------
# HI-140: o saldo é por atividade. Combustível e comércio não se absorvem.
# ---------------------------------------------------------------------------------------------


def test_saldo_de_combustivel_passa_ao_trimestre_seguinte_e_so_e_absorvido_por_combustivel(
    empresa, escritorio_a, gestor
):
    """T1: combustível 0, comércio 100.000,00, devolução de combustível para consumo 10.000,00.
    T1: a devolução não tem receita de combustível para deduzir: saldo de combustível 10.000,00.
        A receita de comércio (100.000,00) fica inteira.
    T2: combustível 5.000,00 (COMBUSTIVEL). Absorve 5.000,00 do saldo; saldo 5.000,00.
    T4: sem receita de combustível. O aviso sai para combustível (5.000,00) e não para comércio."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=141,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
        numero=142,
        valor="10000.00",
        dh_emi="2026-02-13T10:00:00-03:00",
        cfop="1662",
        tp_nf="0",
        fin="4",
    )
    primeiro = _apurar(empresa, 1)
    assert primeiro.devolucao_deduzida == D("0.00")
    assert primeiro.saldo_por_atividade == ((COMBUSTIVEIS, D("10000.00")),)
    assert primeiro.irpj.receita_presumida == D("100000.00")

    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=143,
        valor="5000.00",
        dh_emi="2026-05-10T10:00:00-03:00",
    )
    segundo = _apurar(empresa, 2)
    # Absorvido: 5.000,00 do saldo de combustível. A receita de combustível (5.000,00) fica zerada.
    assert segundo.devolucao_por_atividade == ((COMBUSTIVEIS, D("5000.00")),)
    assert segundo.devolucao_deduzida == D("5000.00")
    assert segundo.saldo_por_atividade == ((COMBUSTIVEIS, D("5000.00")),)
    assert segundo.irpj.receita_presumida == D("0.00")

    quarto = _apurar(empresa, 4)
    assert quarto.saldo_por_atividade == ((COMBUSTIVEIS, D("5000.00")),)
    rotulo = tab.ATIVIDADES_POR_CODIGO[COMBUSTIVEIS].rotulo
    avisos = " ".join(quarto.avisos)
    assert (
        f"Saldo de devolução de NF-e que não coube na receita do ano: R$ 5.000,00 ({rotulo})"
        in avisos
    )
    assert "comércio e indústria" not in avisos


# ---------------------------------------------------------------------------------------------
# N10: o aviso de saldo sai só quando há saldo
# ---------------------------------------------------------------------------------------------


def test_quarto_trimestre_sem_saldo_nao_tem_aviso_de_saldo(empresa, escritorio_a, gestor):
    """Sem nenhuma devolução, o 4º trimestre não tem aviso de saldo (saldo zero não avisa)."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=151,
        valor="100000.00",
        dh_emi="2026-11-10T10:00:00-03:00",
    )
    quarto = _apurar(empresa, 4)
    assert not any("não coube na receita do ano" in aviso for aviso in quarto.avisos)
    assert quarto.saldo_devolucao_transportado == D("0.00")


def test_quarto_trimestre_com_devolucao_absorvida_nao_tem_aviso_de_saldo(
    empresa, escritorio_a, gestor
):
    """Devolução de 10.000,00 absorvida inteira no 4º trimestre (venda de 100.000,00 no mesmo):
    saldo zero, sem aviso."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=152,
        valor="100000.00",
        dh_emi="2026-10-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=153,
        valor="10000.00",
        dh_emi="2026-11-10T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    quarto = _apurar(empresa, 4)
    assert quarto.devolucao_deduzida == D("10000.00")
    assert not any("não coube na receita do ano" in aviso for aviso in quarto.avisos)


# ---------------------------------------------------------------------------------------------
# M25 e N01: cada mês do trimestre, e a passagem entre trimestres (fuso de São Paulo)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("numero", "dh_emi", "trimestre"),
    [
        (161, "2026-03-31T23:30:00-03:00", 1),
        (162, "2026-06-30T23:30:00-03:00", 2),
        (163, "2026-09-30T23:30:00-03:00", 3),
        (164, "2026-12-31T23:30:00-03:00", 4),
        (165, "2026-01-01T00:30:00-03:00", 1),
        (166, "2026-04-01T00:30:00-03:00", 2),
        (167, "2026-07-01T00:30:00-03:00", 3),
        (168, "2026-10-01T00:30:00-03:00", 4),
    ],
)
def test_nfe_em_fim_e_inicio_de_trimestre_cai_no_trimestre_certo(
    empresa, escritorio_a, gestor, numero, dh_emi, trimestre
):
    """M25 e N01: a NF-e de revenda de 1.000,00 cai no trimestre do seu mês, nos meses que terminam
    e começam trimestre (31/03, 30/06, 30/09, 31/12 e os dias seguintes, às 00h30 ou 23h30 de
    São Paulo). Uma nota em março ou em dezembro não pode sumir do Presumido."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=numero,
        valor="1000.00",
        dh_emi=dh_emi,
    )
    assert str(numero) in _numeros(_apurar(empresa, trimestre))
    for outro in (1, 2, 3, 4):
        if outro != trimestre:
            assert str(numero) not in _numeros(_apurar(empresa, outro))


def test_todos_os_meses_do_trimestre_entram_na_receita(empresa, escritorio_a, gestor):
    """N01: uma nota de 1.000,00 em cada mês do 1º trimestre. A receita de comércio é 3.000,00 ×
    8%."""
    for mes, numero in ((1, 171), (2, 172), (3, 173)):
        efetivar_nfe(
            escritorio_a,
            gestor,
            empresa,
            natureza=NaturezaOperacaoNFe.REVENDA,
            numero=numero,
            valor="1000.00",
            dh_emi=f"2026-{mes:02d}-15T10:00:00-03:00",
        )
    apuracao = _apurar(empresa, 1)
    assert _numeros(apuracao) == {"171", "172", "173"}
    assert apuracao.irpj.receita_presumida == D("3000.00")
