"""DL-081 (frente A), proteção dos cálculos que ainda não tratam mercadoria (item 5; HI-122).

- O pré-DAS recusa o MÊS com receita de NF-e, com o motivo nomeado.
- O Presumido fica PARCIAL no TRIMESTRE com NF-e, com o motivo "receita de NF-e ainda não
integrada".
- Meses e trimestres sem NF-e não mudam: a lista de recusas é a mesma de antes da NF-e.
"""

from datetime import date

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import fixar_inicio_de_uso, preparar_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

MENSAGEM_PRE_DAS = (
    "receita de mercadoria (NF-e) no mês — pré-DAS de comércio e indústria ainda não disponível"
)
MENSAGEM_PRESUMIDO = "receita de NF-e ainda não integrada ao Presumido"


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-protecao-dl081")


@pytest.fixture
def empresa_presumido(escritorio_a, gestor):
    """Empresa do LUCRO PRESUMIDO em 2026 (como na DL-079), com atividade padrão de comércio.

    O A2 da rodada 1 mostrou que o teste anterior usava uma empresa do Simples, e por isso não
    detectava nada no Presumido. Esta fixture é a do Presumido.
    """
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumida Protegida Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", gestor)
    presumido_servico.criar_atividade(
        empresa,
        {
            "atividade": tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
            "inicio": date(2026, 1, 1),
            "padrao": True,
        },
        gestor,
    )
    return empresa


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Protegida Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2025, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def nfe_de_revenda(escritorio, gestor, empresa, *, numero, valor, dh_emi):
    documento = receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5102", vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=NaturezaOperacaoNFe.REVENDA)
    return servico.efetivar(esc, usuario=gestor)


def codigos_do_pre_das(empresa, ano, mes):
    try:
        pre_das_servico.pre_das(empresa, ano, mes)
    except pre_das_servico.PreDasRecusado as exc:
        return [(b.codigo, b.mensagem) for b in exc.bloqueios]
    return []


def codigos_do_presumido(empresa, ano, trimestre):
    apuracao = presumido_servico.apurar_trimestre(empresa, ano, trimestre)
    return apuracao.situacao, tuple(r.codigo for r in apuracao.recusas)


# --- pré-DAS -----------------------------------------------------------------------------------


def test_pre_das_recusa_o_mes_com_nfe_com_motivo_nomeado(escritorio_a, gestor, empresa):
    nfe_de_revenda(
        escritorio_a, gestor, empresa, numero=1, valor="2880.00", dh_emi="2026-03-15T10:00:00-03:00"
    )
    bloqueios = codigos_do_pre_das(empresa, 2026, 3)
    assert ("receita_de_mercadoria", MENSAGEM_PRE_DAS) in bloqueios


def test_pre_das_nao_recusa_por_nfe_em_mes_sem_nfe(escritorio_a, gestor, empresa):
    nfe_de_revenda(
        escritorio_a, gestor, empresa, numero=2, valor="100.00", dh_emi="2026-03-15T10:00:00-03:00"
    )
    bloqueios = codigos_do_pre_das(empresa, 2026, 4)
    assert all(codigo != "receita_de_mercadoria" for codigo, _ in bloqueios)


def test_pre_das_mes_sem_nfe_tem_a_mesma_lista_de_antes(empresa):
    """Sem NF-e nenhuma, a lista de bloqueios não ganha o motivo novo."""
    bloqueios = codigos_do_pre_das(empresa, 2026, 3)
    assert all(codigo != "receita_de_mercadoria" for codigo, _ in bloqueios)


# --- Presumido ---------------------------------------------------------------------------------


def test_presumido_fica_parcial_no_trimestre_com_nfe_com_motivo_nomeado(
    escritorio_a, gestor, empresa_presumido
):
    situacao, codigos = codigos_do_presumido(empresa_presumido, 2026, 1)
    assert "receita_nfe_nao_integrada" not in codigos
    nfe_de_revenda(
        escritorio_a,
        gestor,
        empresa_presumido,
        numero=3,
        valor="100.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    situacao, codigos = codigos_do_presumido(empresa_presumido, 2026, 1)
    assert situacao == "parcial"
    assert "receita_nfe_nao_integrada" in codigos
    apuracao = presumido_servico.apurar_trimestre(empresa_presumido, 2026, 1)
    motivos = [r.mensagem for r in apuracao.recusas if r.codigo == "receita_nfe_nao_integrada"]
    assert motivos == [MENSAGEM_PRESUMIDO]


def test_presumido_trimestre_sem_nfe_ate_ele_nao_muda(escritorio_a, gestor, empresa_presumido):
    """Trimestre 2 (abr-jun) sem NF-e em nenhum mês até ele: a lista de recusas é idêntica antes
    e depois de uma NF-e do T3, que vem DEPOIS do T2 e não o afeta."""
    antes = codigos_do_presumido(empresa_presumido, 2026, 2)
    nfe_de_revenda(
        escritorio_a,
        gestor,
        empresa_presumido,
        numero=4,
        valor="100.00",
        dh_emi="2026-08-10T10:00:00-03:00",
    )
    depois = codigos_do_presumido(empresa_presumido, 2026, 2)
    assert antes == depois
    assert "receita_nfe_nao_integrada" not in depois[1]


# Correção da rodada 1 (A2): o limite da LC 224 é recursivo para a frente. Uma NF-e do trimestre
# anterior deixava o seguinte completo, com IRPJ 1.500,00 a menos (cenário do relatório).


@pytest.mark.parametrize("trimestre", [1, 2, 3, 4])
def test_nfe_so_no_t1_deixa_parcial_o_t1_ao_t4_com_o_motivo(
    escritorio_a, gestor, empresa_presumido, trimestre
):
    nfe_de_revenda(
        escritorio_a,
        gestor,
        empresa_presumido,
        numero=10,
        valor="3000000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    situacao, codigos = codigos_do_presumido(empresa_presumido, 2026, trimestre)
    assert situacao == "parcial"
    assert "receita_nfe_nao_integrada" in codigos


def test_nfe_so_no_t2_nao_parcializa_o_t1_e_parcializa_o_t2_ao_t4(
    escritorio_a, gestor, empresa_presumido
):
    nfe_de_revenda(
        escritorio_a,
        gestor,
        empresa_presumido,
        numero=11,
        valor="500000.00",
        dh_emi="2026-05-10T10:00:00-03:00",
    )
    _, codigos_t1 = codigos_do_presumido(empresa_presumido, 2026, 1)
    assert "receita_nfe_nao_integrada" not in codigos_t1
    for trimestre in (2, 3, 4):
        _, codigos = codigos_do_presumido(empresa_presumido, 2026, trimestre)
        assert "receita_nfe_nao_integrada" in codigos, trimestre


def test_presumido_sem_nfe_nenhuma_nao_tem_o_motivo_em_nenhum_trimestre(empresa_presumido):
    for trimestre in (1, 2, 3, 4):
        _, codigos = codigos_do_presumido(empresa_presumido, 2026, trimestre)
        assert "receita_nfe_nao_integrada" not in codigos, trimestre


def test_nfe_de_outra_empresa_nao_parcializa_o_presumido(escritorio_a, gestor, empresa):
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra Protegida Ltda", cnpj="77888999000155"
    )
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
            vnf="100.00",
            totais={"vProd": "100.00"},
            numero="5",
            dh_emi="2026-02-10T10:00:00-03:00",
            emitente=("CNPJ", outra.cnpj),
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, outra), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=NaturezaOperacaoNFe.REVENDA)
    servico.efetivar(esc, usuario=gestor)
    _, codigos = codigos_do_presumido(empresa, 2026, 1)
    assert "receita_nfe_nao_integrada" not in codigos
