"""DL-082, ajustes do arquiteto depois da reconferência (R1, R4 e R5; §3.1 do AGENTS.md).

A reconferência foi a última rodada permitida. Os três ajustes abaixo são do arquiteto, e cada um
tem aqui o teste que o prende. Dados sintéticos (`suporte_dl082`). Os números esperados são escritos
à mão, com a conta ao lado.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import SegmentoDevolucao as SD
from apps.fiscal.models import e_devolucao_de_exportacao
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

NCM_COMBUSTIVEL = "27101259"


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Ajustes DL082 Ltda",
        cnpj=CNPJ_EMITENTE_A,
    )


def _devolucao_de_combustivel(escritorio, usuario, empresa, *, numero, dh_emi=None):
    kwargs = {"dh_emi": dh_emi} if dh_emi else {}
    documento = nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        itens=[{"cfop": "1661", "vprod": "10000.00", "ncm": NCM_COMBUSTIVEL}],
        devolucao=True,
        **kwargs,
    )
    escriturar(empresa, usuario, documento, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA})
    return documento


# ---------------------------------------------------------------------------
# R1: devolução de venda de combustível fica fora do saldo do Simples
# ---------------------------------------------------------------------------


def test_devolucao_de_combustivel_sai_das_parcelas_do_simples_e_fica_nas_linhas(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """A linha continua em `linhas_nfe_do_periodo` (o Presumido a usa); só as parcelas do Simples a
    deixam de fora. A devolução comum (1.202) do mesmo mês continua deduzindo: 3.000."""
    empresa = cenario(empresa_a)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "40000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA})
    _devolucao_de_combustivel(escritorio_a, usuario_gestor_a, empresa, numero=2)
    comum = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=3,
        itens=[{"cfop": "1202", "vprod": "3000.00"}],
        devolucao=True,
    )
    escriturar(empresa, usuario_gestor_a, comum, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA})

    linhas = servico_receita.linhas_nfe_do_periodo(empresa, (2026, 6), (2026, 6))
    assert sorted((linha.papel, linha.cfop.replace(".", ""), linha.valor) for linha in linhas) == [
        ("deducao", "1202", Decimal("3000.00")),
        ("deducao", "1661", Decimal("10000.00")),
        ("receita", "5102", Decimal("40000.00")),
    ]

    parcelas = servico_receita._parcelas_do_periodo(empresa, (2026, 6), (2026, 6))[(2026, 6)]
    assert sum(parcelas.devolucoes.values()) == Decimal("3000.00")
    assert sum(parcelas.vendas.values()) == Decimal("40000.00")


def test_devolucao_de_combustivel_de_maio_nao_abate_o_das_de_junho(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """O caso da reconferência (R1). Devolução de combustível de 10.000 em MAIO, sem venda no mesmo
    segmento em maio; venda 5.102 de 40.000 em JUNHO. Antes do ajuste, o saldo de maio passava a
    junho e deduzia: 30.000 × 7,19% = 2.157,00. Agora não passa.

    Esperado (à mão): janela 50.000 × 12, RBT12 600.000, Anexo I faixa 3 (9,5%, dedução 13.860).
    Alíquota efetiva = (600.000 × 9,5% − 13.860) / 600.000 = 43.140 / 600.000.
    DAS = 40.000 × 43.140 / 600.000 = 2.876,00."""
    empresa = cenario(empresa_a)
    _devolucao_de_combustivel(
        escritorio_a, usuario_gestor_a, empresa, numero=2, dh_emi="2026-05-15T10:00:00-03:00"
    )
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "40000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("2876.00")


# ---------------------------------------------------------------------------
# R4: devolução de remessa para formação de lote de exportação recusa, com nome
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cfop", ["1505", "1506", "2505", "2506", "1.505"])
def test_remessa_para_lote_nao_e_devolucao_de_exportacao(cfop):
    assert e_devolucao_de_exportacao(cfop) is False


@pytest.mark.parametrize("cfop", ["1505", "2506"])
def test_devolucao_de_remessa_para_lote_recusa_o_mes_com_o_codigo_nomeado(
    escritorio_a, usuario_gestor_a, empresa_a, cfop
):
    """Venda 5.102 de 40.000 e devolução com CFOP de remessa para lote, de 5.000, no segmento
    revenda (o único que a tela oferece a esse CFOP). Antes do ajuste, deduzia do mercado externo.
    Agora o mês recusa, e a mensagem nomeia a nota e o CFOP."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "40000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=7,
        itens=[{"cfop": cfop, "vprod": "5000.00"}],
        devolucao=True,
    )
    escriturar(
        empresa, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA}
    )
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)
    recusas = {b.codigo: b.mensagem for b in erro.value.bloqueios}

    assert "devolucao_de_remessa_para_lote_de_exportacao" in recusas
    mensagem = recusas["devolucao_de_remessa_para_lote_de_exportacao"]
    assert "nota 7" in mensagem
    assert cfop in mensagem.replace(".", "")


# ---------------------------------------------------------------------------
# R5: os dois lados do "ou" do aviso de exportação direta (A6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cfop", "id_dest", "avisa", "total"),
    [
        ("7102", "3", False, "404.00"),  # coerente: CFOP 7.xxx e destino no exterior
        ("7102", "1", True, "404.00"),  # CFOP certo, idDest errado
        ("5102", "3", True, "404.00"),  # idDest certo, CFOP errado
        ("7101", "3", False, "418.50"),  # outro 7.xxx, coerente; produção própria, Anexo II
    ],
)
def test_aviso_de_exportacao_direta_olha_o_cfop_e_o_id_dest(
    escritorio_a, usuario_gestor_a, empresa_a, cfop, id_dest, avisa, total
):
    """Esperado (à mão): exportação direta de 20.000 com janela 50.000 interno e 10.000 externo,
    como no caso 7 da auditoria: 404,00 no Anexo I (revenda), com ou sem aviso; 418,50 no Anexo
    II (7.101, produção própria), o mesmo valor do externo do Anexo II no caso da comercial
    exportadora.
    O aviso sai quando falta UM dos dois: CFOP 7.xxx ou idDest 3."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12, [10000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=8,
        itens=[{"cfop": cfop, "vprod": "20000.00"}],
        id_dest=id_dest,
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.EXPORTACAO_DIRETA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal(total)
    tem_aviso = any(f"CFOP {cfop}, idDest {id_dest}" in aviso for aviso in resultado.avisos)
    assert tem_aviso is avisa
