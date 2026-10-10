"""DL-088, frente A1: pré-DAS de 2027 por tributo, pelo motor interno, e a recusa pública.

Contas escritas à mão, no docstring de cada teste. Os cenários de serviço passam pelo pré-DAS real
(atividade, receita informada e confirmada, RBT12 defasado). O caminho PÚBLICO `pre_das` recusa 2027
com o bloqueio nomeado: falta a opção pelo regime regular (dado da frente A2).

Os números da janela de 2027 estão em `suporte_dl088`: 12/2025 a 11/2026, 12/2026 fora.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import pre_das as motor
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import EnquadramentoAtividade
from apps.fiscal.receita import MercadoriaDoMes, SegmentoDeMercadoria
from apps.fiscal.tests.suporte_dl088 import (
    JANELA_DE_2027_01,
    confirmar_janela_de_2027_01,
    receber_pa_2027_01,
)
from apps.fiscal.tests.test_dl074_suporte import fixar_hoje
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    receber_e_confirmar_mes,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    """Relógio de Brasília em 15/03/2028 (A7: só se confirma mês completo). Os meses de 2027 e
    de 01 e 02/2028 dos cenários ficam confirmáveis, e o teste não depende da data real."""
    fixar_hoje(monkeypatch, date(2028, 3, 15))


D = Decimal
ANEXO_III = EnquadramentoAtividade.ANEXO_III
ANEXO_III_OU_V = EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R


def por_tributo(resultado):
    return dict(resultado.total_por_tributo)


def cenario_servico(empresa_a, usuario, *, valor_mensal, valor_mes_anterior=0, pa=10000):
    """Serviço, Anexo III, Simples desde 2018, PA 01/2027 com `pa` de receita interna."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario, ANEXO_III)
    confirmar_janela_de_2027_01(
        empresa, usuario, valor_mensal, valor_mes_anterior=valor_mes_anterior
    )
    receber_pa_2027_01(empresa, usuario, pa)
    return empresa


# ---------------------------------------------------------------------------
# Caminho público: recusa de 2027 e de 2029
# ---------------------------------------------------------------------------


def test_pre_das_publico_de_2027_recusa_com_a_opcao_pelo_regime_regular_nao_informada(
    empresa_a, usuario_gestor_a
):
    """Com tudo o mais em ordem, o único bloqueio é a opção pelo regime regular (A2)."""
    empresa = cenario_servico(empresa_a, usuario_gestor_a, valor_mensal=25000)

    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor.pre_das(empresa, 2027, 1)

    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "opcao_regime_regular_nao_informada"
    assert "regime regular" in bloqueio.mensagem
    assert "190/2026" in bloqueio.dispositivo


def test_pre_das_publico_de_2029_recusa_com_a_divergencia_e_a_190(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor.pre_das(empresa, 2029, 1)
    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "tabela_fora_de_vigencia"
    assert "190/2026" in bloqueio.mensagem
    assert "01/2029" in bloqueio.mensagem
    assert "19,00%" in bloqueio.mensagem and "18,90%" in bloqueio.mensagem


def test_regime_regular_em_2026_e_erro_de_chamada(empresa_a, usuario_gestor_a):
    """A opção pelo regime regular não existe antes de 2027: `True` em 2026 é erro."""
    empresa = cenario_simples(empresa_a)
    with pytest.raises(ValueError):
        motor._calcular_pre_das(empresa, 2026, 6, regime_regular_ibs_cbs=True)


# ---------------------------------------------------------------------------
# Motor de 2027, com a opção explícita
# ---------------------------------------------------------------------------


def test_servico_anexo_iii_2027_sem_opcao_cbs_e_ibs_entram_no_das_ao_centavo(
    empresa_a, usuario_gestor_a
):
    """Serviço, Anexo III, RBT12 300.000 (janela defasada), PA 10.000, sem opção.

    Faixa 2: nominal 11,20%, a deduzir 9.360,00. Efetiva = (300.000 × 0,112 − 9.360) / 300.000
    = 0,0808. Cada tributo sobre 10.000:
    IRPJ 4,00% → 32,32 · CSLL 3,50% → 28,28 · CBS 16,91% → 136,63 · CPP 43,40% → 350,67
    ISS 32,00% → 258,56 · IBS 0,19% → 1,54. Total 808,00.
    A janela 01/2026 a 12/2026 daria RBT12 de 25.000 × 11 + 900.000 e outra faixa: o teste a guarda.
    """
    empresa = cenario_servico(
        empresa_a, usuario_gestor_a, valor_mensal=25000, valor_mes_anterior=900000
    )

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert resultado.rbt12["interno"] == D("300000")
    (anexo,) = resultado.anexos
    assert (anexo.anexo, anexo.faixa) == ("III", 2)
    assert anexo.aliquota_efetiva == D("0.0808")
    assert por_tributo(resultado) == {
        "IRPJ": D("32.32"),
        "CSLL": D("28.28"),
        "CBS": D("136.63"),
        "CPP": D("350.67"),
        "ISS": D("258.56"),
        "IBS": D("1.54"),
    }
    assert resultado.total == D("808.00")
    assert any("Opção pelo regime regular" in p.descricao for p in resultado.memoria)


def test_servico_anexo_iii_2027_com_opcao_deduz_cbs_e_ibs_art_22a(empresa_a, usuario_gestor_a):
    """Mesmo cenário de 808,00, com a opção pelo regime regular (art. 22-A).

    CBS 136,63 e IBS 1,54 saem do DAS: total 808,00 − 138,17 = 669,83. Os valores deduzidos
    ficam na memória e em `LinhaTributo.deduzido`.
    """
    empresa = cenario_servico(
        empresa_a, usuario_gestor_a, valor_mensal=25000, valor_mes_anterior=900000
    )

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=True)

    assert por_tributo(resultado)["CBS"] == D("0.00")
    assert por_tributo(resultado)["IBS"] == D("0.00")
    assert por_tributo(resultado)["ISS"] == D("258.56")
    assert resultado.total == D("669.83")
    linhas = {linha.tributo: linha for linha in resultado.anexos[0].segmentos[0].linhas}
    assert linhas["CBS"].deduzido == D("136.63")
    assert linhas["IBS"].deduzido == D("1.54")
    assert any(
        "deduzido do DAS" in p.descricao or "art. 22-A" in p.dispositivo for p in resultado.memoria
    )


def test_servico_anexo_iii_2027_com_teto_do_iss_ao_centavo_por_tributo(empresa_a, usuario_gestor_a):
    """Teto do ISS, Anexo III, 5ª faixa: RBT12 3.000.000 (janela de 250.000 por mês), PA 100.000.

    Efetiva = (3.000.000 × 0,21 − 125.640) / 3.000.000 = 0,16812. Acima de 14,92537%: ISS 5% e
    excedente 0,11812, redistribuído a IRPJ 6,02%, CSLL 5,26%, CBS 23,20%, CPP 65,26%, IBS 0,26%.
    Por tributo sobre 100.000: IRPJ 711,08 · CSLL 621,31 · CBS 2.740,38 · CPP 7.708,51
    IBS 30,71 · ISS 5.000,00. Total 16.811,99 (a conta exata, 16.812,00, perde o centavo dos
    arredondamentos por tributo). O mês 12/2026, de 900.000, não entra na janela.
    """
    empresa = cenario_servico(
        empresa_a,
        usuario_gestor_a,
        valor_mensal=250000,
        valor_mes_anterior=900000,
        pa=100000,
    )

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert resultado.rbt12["interno"] == D("3000000")
    assert resultado.anexos[0].teto_iss_aplicado
    assert por_tributo(resultado) == {
        "IRPJ": D("711.08"),
        "CSLL": D("621.31"),
        "CBS": D("2740.38"),
        "CPP": D("7708.51"),
        "ISS": D("5000.00"),
        "IBS": D("30.71"),
    }
    assert resultado.total == D("16811.99")


def test_exportacao_de_servico_2027_desconsidera_cbs_ibs_e_iss(empresa_a, usuario_gestor_a):
    """Exportação de serviço, Anexo III, RBT12 externo 300.000 (janela de 25.000 por mês externo),
    PA externo 10.000. Efetiva 0,0808. IRPJ 32,32 · CSLL 28,28 · CPP 350,67. Total 411,27.
    CBS, IBS e ISS saem (art. 25, § 3º). O interno, sem receita, não gera linha."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    # A janela de 2027 é toda do mercado externo: 25.000 por mês, e o interno fica sem receita.
    for ano, mes in JANELA_DE_2027_01:
        receber_e_confirmar_mes(empresa, usuario_gestor_a, ano, mes, 25000, mercado="externo")
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000, mercado="externo")

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert list(resultado.rbt12) == ["externo"]
    assert resultado.rbt12["externo"] == D("300000")
    assert por_tributo(resultado) == {
        "IRPJ": D("32.32"),
        "CSLL": D("28.28"),
        "CBS": D("0.00"),
        "CPP": D("350.67"),
        "ISS": D("0.00"),
        "IBS": D("0.00"),
    }
    assert resultado.total == D("411.27")


def test_primeiro_mes_de_atividade_usa_a_primeira_faixa_sem_rbt12(empresa_a, usuario_gestor_a):
    """Abertura em 15/01/2027, PA 01/2027 (mês 1), serviço Anexo III, receita 10.000.

    1ª faixa, sem RBT12: nominal 6,00%, a deduzir zero. Efetiva 6%.
    IRPJ 4,00% → 24,00 · CSLL 3,50% → 21,00 · CBS 15,43% → 92,58 · CPP 43,40% → 260,40
    ISS 33,50% → 201,00 · IBS 0,17% → 1,02. Total 600,00 (= 6% de 10.000).
    """
    empresa = cenario_simples(
        empresa_a, abertura=date(2027, 1, 15), inicio_simples=date(2027, 1, 15)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, inicio=date(2027, 1, 1))
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert resultado.rbt12["interno"] is None
    (anexo,) = resultado.anexos
    assert anexo.faixa == 1
    assert anexo.aliquota_efetiva == D("0.06")
    assert por_tributo(resultado) == {
        "IRPJ": D("24.00"),
        "CSLL": D("21.00"),
        "CBS": D("92.58"),
        "CPP": D("260.40"),
        "ISS": D("201.00"),
        "IBS": D("1.02"),
    }
    assert resultado.total == D("600.00")


def test_fator_r_no_primeiro_mes_de_atividade_recusa_com_motivo(empresa_a, usuario_gestor_a):
    """Fator r exigido no 1º mês: o FS12 não tem janela lida nesse estado. Recusa nomeada."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2027, 1, 15), inicio_simples=date(2027, 1, 15)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III_OU_V, inicio=date(2027, 1, 1))
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)

    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    codigos = {b.codigo for b in excecao.value.bloqueios}
    assert "fator_r_no_inicio_de_atividade" in codigos


def test_producao_propria_com_segmentos_de_mesmo_anexo_soma_bruto_e_deducao(
    empresa_a, usuario_gestor_a, monkeypatch
):
    """DADO SINTÉTICO ISOLADO (mock da leitura de mercadoria, identificado).

    Em 2027 a produção própria (Anexo II, fora da ZFM) vai ao Anexo I: os dois segmentos de
    mesma chave (interno, I, normal) SOMAM. Simulado: produção 6.000 com devolução 1.000 (Anexo II)
    e revenda 4.000 (Anexo I). Líquido somado: 9.000. Anexo I, faixa 2 (RBT12 300.000, efetiva
    5,32%): IRPJ 26,33 · CSLL 16,76 · CBS 73,40 · CPP 198,70 · ICMS 162,79 · IBS 0,81. Total 478,79.
    """
    empresa = cenario_simples(empresa_a)
    # A regra pede atividade padrão no mês sem NF-e de mercadoria real: o mock não cria NF-e,
    # então a atividade (que não entra no cálculo de mercadoria) é cadastrada para o mês.
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    confirmar_janela_de_2027_01(empresa, usuario_gestor_a, 25000)
    servico_receita.confirmar_mes(empresa, 2027, 1, usuario_gestor_a)

    def mercadoria_sintetica(empresa_, ano, mes):
        return MercadoriaDoMes(
            segmentos=(
                SegmentoDeMercadoria(
                    mercado="interno",
                    anexo="I",
                    segmento="normal",
                    bruto=D("4000"),
                    deduzido=D("0"),
                ),
                SegmentoDeMercadoria(
                    mercado="interno",
                    anexo="II",
                    segmento="normal",
                    bruto=D("6000"),
                    deduzido=D("1000"),
                ),
            ),
            deduzido_sem_segmento={"interno": D("0"), "externo": D("0")},
        )

    monkeypatch.setattr(servico_receita, "mercadoria_do_mes", mercadoria_sintetica)

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert [(a.anexo, a.mercado) for a in resultado.anexos] == [("I", "interno")]
    (segmento,) = resultado.anexos[0].segmentos
    assert segmento.receita == D("9000")
    assert por_tributo(resultado) == {
        "IRPJ": D("26.33"),
        "CSLL": D("16.76"),
        "CBS": D("73.40"),
        "CPP": D("198.70"),
        "ICMS": D("162.79"),
        "IBS": D("0.81"),
    }
    assert resultado.total == D("478.79")
