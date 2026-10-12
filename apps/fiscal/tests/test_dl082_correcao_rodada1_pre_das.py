"""DL-082, correção da rodada 1 (A2, A4, A5, A6, A7 e A13): pré-DAS de mercadoria.

Dados sintéticos (`suporte_dl082`). Os números esperados são escritos à mão, com a conta ao lado
de cada teste. O caso de cada teste é o da auditoria (2026-10-09-dl-082-rodada-1.md, casos 1, 4,
5, 6, 7 e 8), salvo quando o comentário diz outra coisa.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal.api import _pre_das_payload
from apps.fiscal.models import MercadoReceita
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import SegmentoDevolucao as SD
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Correção DL082 Pré-DAS Ltda",
        cnpj=CNPJ_EMITENTE_A,
    )


def _recusa(empresa):
    """Devolve {código: mensagem} da recusa. Falha se o pré-DAS calcular."""
    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)
    return {b.codigo: b.mensagem for b in erro.value.bloqueios}


# ---------------------------------------------------------------------------
# A2: devolução de VENDA de combustível recusa, seja qual for a natureza
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cfop", ["1660", "1661", "1662", "2660", "2661", "2662"])
def test_devolucao_de_venda_de_combustivel_recusa_o_mes_com_o_codigo_nomeado(
    escritorio_a, usuario_gestor_a, empresa_a, cfop
):
    """Caso 1 da auditoria. Esperado (à mão): janela 50.000 × 12, RBT12 600.000. Venda 5102 de
    40.000 e devolução de combustível de 10.000 com NCM de combustível (natureza devolucao_venda,
    segmento revenda). Antes da correção: calculava 2.157,01 (30.000 × 7,19%), deduzindo da receita
    de mercadoria comum. Agora: recusa, nomeando a nota e o CFOP."""
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
        numero=3,
        itens=[{"cfop": cfop, "vprod": "10000.00", "ncm": "27101259"}],
        devolucao=True,
    )
    escriturar(
        empresa, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA}
    )
    confirmar_pa(empresa, usuario_gestor_a)

    recusas = _recusa(empresa)

    assert "devolucao_combustivel_cfop" in recusas
    assert f"CFOP {cfop}" in recusas["devolucao_combustivel_cfop"]
    assert "nota 3" in recusas["devolucao_combustivel_cfop"]


# ---------------------------------------------------------------------------
# A4: CSOSN de benefício recusa só no mercado interno
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("csosn", ["103", "300", "400"])
def test_exportacao_com_csosn_de_beneficio_calcula(
    escritorio_a, usuario_gestor_a, empresa_a, csosn
):
    """Caso 4 da auditoria. Esperado (à mão): exportação 7102 de 20.000, idDest 3, natureza
    exportacao_direta. RBT12 externo 120.000 (10.000 × 12): Anexo I, faixa 1, alíquota efetiva 4%.
    Exportação tira PIS (2,76), Cofins (12,74) e ICMS (34) do percentual de cada tributo. Sobram
    IRPJ (5,5), CSLL (3,5) e CPP (41,5), que somam 50,5%. 20.000 × 4% × 50,5% = 404,00."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12, [10000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "7102", "vprod": "20000.00", "csosn": csosn}],
        id_dest="3",
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.EXPORTACAO_DIRETA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("404.00")


@pytest.mark.parametrize("csosn", ["103", "300", "400"])
def test_venda_interna_com_csosn_de_beneficio_continua_recusando(
    escritorio_a, usuario_gestor_a, empresa_a, csosn
):
    """A4, o outro lado: no mercado interno a recusa (HI-131) continua. Esperado: a recusa
    `beneficio_icms_sem_parametro` nomeia a nota e o CSOSN."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=2,
        itens=[{"cfop": "5102", "vprod": "40000.00", "csosn": csosn}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    recusas = _recusa(empresa)

    assert f"CSOSN {csosn}" in recusas["beneficio_icms_sem_parametro"]


# ---------------------------------------------------------------------------
# A5: serviço de comunicação ou de transporte sob natureza de mercadoria recusa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cfop", ["5353", "5301", "5932", "7358"])
def test_cfop_de_servico_de_comunicacao_ou_transporte_sob_mercadoria_recusa_com_nome(
    escritorio_a, usuario_gestor_a, empresa_a, cfop
):
    """Esperado: recusa `servico_de_comunicacao_ou_transporte`, com a nota e o CFOP. 5.353 é o caso
    da auditoria (caso 8). 5.932 e 7.358 são transporte pela descrição oficial."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=4,
        itens=[{"cfop": cfop, "vprod": "10000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    recusas = _recusa(empresa)

    assert f"CFOP {cfop}" in recusas["servico_de_comunicacao_ou_transporte"]


# ---------------------------------------------------------------------------
# A6: exportação direta incoerente com o CFOP ou o idDest gera AVISO, não recusa
# ---------------------------------------------------------------------------


def test_exportacao_direta_com_cfop_interno_calcula_e_avisa(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso 7 da auditoria. Esperado (à mão): natureza exportacao_direta com CFOP 5102 e idDest 1,
    de 20.000. Calcula como exportação (Anexo I, faixa 1, 404,00, como no caso de CSOSN acima), e o
    aviso nomeia a nota, o CFOP e o idDest. Não recusa."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12, [10000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=5,
        itens=[{"cfop": "5102", "vprod": "20000.00"}],
        id_dest="1",
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.EXPORTACAO_DIRETA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("404.00")
    assert any("CFOP 5102, idDest 1" in aviso for aviso in resultado.avisos)


def test_exportacao_direta_coerente_nao_avisa(escritorio_a, usuario_gestor_a, empresa_a):
    """O lado sem aviso: CFOP 7.102 e idDest 3. O aviso não aparece, e o total é o mesmo 404,00."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12, [10000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=6,
        itens=[{"cfop": "7102", "vprod": "20000.00"}],
        id_dest="3",
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: N.EXPORTACAO_DIRETA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("404.00")
    assert resultado.avisos == ()


# ---------------------------------------------------------------------------
# A7: segmento com venda e líquido zero continua no resultado
# ---------------------------------------------------------------------------


def test_devolucao_integral_de_segmento_aparece_com_liquido_zero(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso 5 da auditoria. Esperado (à mão): venda ST de 20.000 (5405, CSOSN 500) e devolução ST de
    20.000 (1411, CSOSN 500, segmento revenda_st), no mesmo mês; RBT12 600.000. O segmento
    sujeita_st aparece com bruto 20.000,00, deduzido 20.000,00 e receita 0,00. O total é 0,00.
    Antes: o segmento sumia, e a tela não mostrava a tabela de venda, devolução e receita
    líquida."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=7,
        itens=[{"cfop": "5405", "vprod": "20000.00", "csosn": "500"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA_ST_SUBSTITUIDO})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=8,
        itens=[{"cfop": "1411", "vprod": "20000.00", "csosn": "500"}],
        devolucao=True,
    )
    escriturar(
        empresa, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA_ST}
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("0.00")
    segmentos = [
        (s.segmento, s.bruto, s.deduzido, s.receita) for a in resultado.anexos for s in a.segmentos
    ]
    assert segmentos == [
        ("sujeita_st", Decimal("20000.00"), Decimal("20000.00"), Decimal("0.00")),
    ]
    # A memória e a API mostram o mesmo segmento, com a venda, a devolução e o líquido.
    assert any("sujeita_st" in passo.descricao for passo in resultado.memoria)
    payload = _pre_das_payload(resultado)
    segmento_na_api = payload["anexos"][0]["segmentos"][0]
    assert segmento_na_api["segmento"] == "sujeita_st"
    assert segmento_na_api["bruto"] == "20000.00"
    assert segmento_na_api["deduzido"] == "20000.00"
    assert segmento_na_api["receita"] == "0.00"


# ---------------------------------------------------------------------------
# A13: limite exato do primeiro corte (RBT12 = R$ 3.600.000,00)
# ---------------------------------------------------------------------------


def test_rbt12_exatamente_no_limite_do_primeiro_corte_calcula(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso 6 da auditoria. Esperado (à mão): RBT12 = 12 × 300.000 = 3.600.000,00. Anexo I, faixa 5
    (acima de 1.800.000 até 3.600.000), alíquota nominal 14,3% e parcela a deduzir 87.300.
    Alíquota efetiva = 14,3% − 87.300 / 3.600.000 = 14,3% − 2,425% = 11,875%. Venda de revenda de
    10.000: 10.000 × 11,875% = 1.187,50. O limite é inclusivo: não recusa."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [300000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=9,
        itens=[{"cfop": "5102", "vprod": "10000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.rbt12[MercadoReceita.INTERNO] == Decimal("3600000.00")
    assert resultado.total == Decimal("1187.50")


def test_rbt12_um_centavo_acima_do_limite_recusa(escritorio_a, usuario_gestor_a, empresa_a):
    """O outro lado do limite: RBT12 = 3.600.000,01 recusa com o código do primeiro corte."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [300000] * 11 + [300000.01])
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=10,
        itens=[{"cfop": "5102", "vprod": "10000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: N.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    recusas = _recusa(empresa)

    assert "rbt12_acima_do_primeiro_corte" in recusas
