"""DL-088, frente A2: o pré-DAS de 2027 pelo caminho PÚBLICO, ao centavo, com a opção registrada.

Cada teste traz a CONTA escrita à mão no docstring (as memórias de cálculo são as da A1,
`test_dl088_calculo_2027.py` e `test_dl088_pre_das_2027.py`). O que a A2 acrescenta:

- a opção de regime de IBS/CBS do SEMESTRE é dado da empresa
  (`receita.registrar_opcao_regime_ibs_cbs`) e é o que libera o caminho público de 2027: regime
  ÚNICO deixa CBS e IBS no DAS; regime REGULAR
  deduz as parcelas (art. 22-A); sem opção informada, a recusa `opcao_regime_regular_nao_informada`
  continua EXATAMENTE como antes;
- o Anexo II de 2027 é só da indústria com IPI MANTIDO (Zona Franca; HI-152): o dado da empresa
  decide, produção própria fora da ZFM vai ao Anexo I, e o dado não informado NÃO presume ZFM.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import pre_das as motor
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    ANEXO_I,
    EnquadramentoAtividade,
    RegimeIbsCbsSimples,
    SituacaoIpiMantido,
)
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
    """Relógio de Brasília em 15/03/2028 (só se confirma mês completo), como na A1."""
    fixar_hoje(monkeypatch, date(2028, 3, 15))


D = Decimal
ANEXO_III = EnquadramentoAtividade.ANEXO_III


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


def registrar_opcao(empresa, usuario, regime, *, ano=2027, semestre=1):
    """A opção de regime de IBS/CBS do semestre, pelo serviço (com trilha)."""
    return servico_receita.registrar_opcao_regime_ibs_cbs(empresa, ano, semestre, regime, usuario)


# ---------------------------------------------------------------------------
# O caminho público de 2027, cenário a cenário
# ---------------------------------------------------------------------------


def test_regime_unico_deixa_cbs_e_ibs_no_das_ao_centavo(empresa_a, usuario_gestor_a):
    """Serviço, Anexo III, RBT12 300.000 (janela defasada de 25.000/mês, 12/2026 de 900.000 fora),
    PA 01/2027 de 10.000, com a opção REGIME ÚNICO do 1º semestre registrada.

    Faixa 2: nominal 11,20%, a deduzir 9.360,00. Efetiva = (300.000 × 0,112 − 9.360) / 300.000
    = 0,0808. Por tributo sobre 10.000: IRPJ 4,00% → 32,32 · CSLL 3,50% → 28,28
    CBS 16,91% → 136,63 · CPP 43,40% → 350,67 · ISS 32,00% → 258,56 · IBS 0,19% → 1,54.
    Total 808,00. CBS e IBS FICAM no DAS: é o regime único.
    """
    empresa = cenario_servico(
        empresa_a, usuario_gestor_a, valor_mensal=25000, valor_mes_anterior=900000
    )
    registrar_opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)

    resultado = motor.pre_das(empresa, 2027, 1)

    assert resultado.rbt12["interno"] == D("300000")
    assert por_tributo(resultado) == {
        "IRPJ": D("32.32"),
        "CSLL": D("28.28"),
        "CBS": D("136.63"),
        "CPP": D("350.67"),
        "ISS": D("258.56"),
        "IBS": D("1.54"),
    }
    assert resultado.total == D("808.00")


def test_regime_regular_deduz_cbs_e_ibs_art_22a(empresa_a, usuario_gestor_a):
    """Mesma conta de 808,00, com a opção REGIME REGULAR do 1º semestre (art. 22-A).

    CBS 136,63 e IBS 1,54 saem do DAS: total 808,00 − 138,17 = 669,83. O valor deduzido fica na
    memória e em `LinhaTributo.deduzido`.
    """
    empresa = cenario_servico(
        empresa_a, usuario_gestor_a, valor_mensal=25000, valor_mes_anterior=900000
    )
    registrar_opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_REGULAR)

    resultado = motor.pre_das(empresa, 2027, 1)

    assert por_tributo(resultado)["CBS"] == D("0.00")
    assert por_tributo(resultado)["IBS"] == D("0.00")
    assert por_tributo(resultado)["ISS"] == D("258.56")
    assert resultado.total == D("669.83")
    linhas = {linha.tributo: linha for linha in resultado.anexos[0].segmentos[0].linhas}
    assert linhas["CBS"].deduzido == D("136.63")
    assert linhas["IBS"].deduzido == D("1.54")


def test_exportacao_de_servico_2027_desconsidera_cbs_ibs_e_iss(empresa_a, usuario_gestor_a):
    """Exportação de serviço, Anexo III, RBT12 externo 300.000 (janela de 25.000/mês externo),
    PA externo 10.000, opção REGIME ÚNICO. Efetiva 0,0808.

    Sobram IRPJ 32,32 · CSLL 28,28 · CPP 350,67: total 411,27. CBS, IBS e ISS saem (art. 25, § 3º).
    """
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    for ano, mes in JANELA_DE_2027_01:
        receber_e_confirmar_mes(empresa, usuario_gestor_a, ano, mes, 25000, mercado="externo")
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000, mercado="externo")
    registrar_opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)

    resultado = motor.pre_das(empresa, 2027, 1)

    assert por_tributo(resultado) == {
        "IRPJ": D("32.32"),
        "CSLL": D("28.28"),
        "CBS": D("0.00"),
        "CPP": D("350.67"),
        "ISS": D("0.00"),
        "IBS": D("0.00"),
    }
    assert resultado.total == D("411.27")


def test_sem_opcao_informada_o_pre_das_de_2027_continua_recusando(empresa_a, usuario_gestor_a):
    """Com tudo o mais em ordem e SEM a opção registrada, o único bloqueio continua sendo
    `opcao_regime_regular_nao_informada` — a recusa é a mesma da A1, não se presume regime."""
    empresa = cenario_servico(empresa_a, usuario_gestor_a, valor_mensal=25000)

    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor.pre_das(empresa, 2027, 1)

    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "opcao_regime_regular_nao_informada"
    assert "regime regular" in bloqueio.mensagem
    assert "190/2026" in bloqueio.dispositivo


def test_a_opcao_do_semestre_vale_so_para_o_seu_semestre(empresa_a, usuario_gestor_a):
    """A opção é por (empresa, ano, SEMESTRE): a do 1º semestre não libera o PA de outro semestre.

    Com a opção só do 2º semestre de 2027, o PA 01/2027 (1º semestre) continua recusando.
    """
    empresa = cenario_servico(empresa_a, usuario_gestor_a, valor_mensal=25000)
    registrar_opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO, semestre=2)

    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is None
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 2) is False
    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor.pre_das(empresa, 2027, 1)
    assert {b.codigo for b in excecao.value.bloqueios} == {"opcao_regime_regular_nao_informada"}


def test_2029_continua_recusado_com_a_divergencia(empresa_a, usuario_gestor_a):
    """A A2 não mexe em 2029 (HI-146): a recusa da divergência é a primeira, mesmo com opção."""
    empresa = cenario_simples(empresa_a)
    registrar_opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)

    with pytest.raises(motor.PreDasRecusado) as excecao:
        motor.pre_das(empresa, 2029, 1)

    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "tabela_fora_de_vigencia"
    assert "19,00%" in bloqueio.mensagem and "18,90%" in bloqueio.mensagem


# ---------------------------------------------------------------------------
# Anexo II em 2027 só com IPI mantido (Zona Franca; HI-152, item 2)
# ---------------------------------------------------------------------------


def _producao_propria(empresa, usuario, monkeypatch):
    """DADO SINTÉTICO ISOLADO (mock da leitura de mercadoria, identificado, como na A1).

    Produção própria no mercado interno: bruto 11.000, devolução 1.000, líquido 10.000. O anexo do
    segmento é ANEXO_II na origem; quem decide o anexo efetivo é o dado de IPI mantido.
    """
    atividade_padrao(empresa, usuario, ANEXO_III)
    confirmar_janela_de_2027_01(empresa, usuario, 25000)
    servico_receita.confirmar_mes(empresa, 2027, 1, usuario)

    def mercadoria_sintetica(empresa_, ano, mes):
        return MercadoriaDoMes(
            segmentos=(
                SegmentoDeMercadoria(
                    mercado="interno",
                    anexo="II",
                    segmento="normal",
                    bruto=D("11000"),
                    deduzido=D("1000"),
                ),
            ),
            deduzido_sem_segmento={"interno": D("0"), "externo": D("0")},
        )

    monkeypatch.setattr(servico_receita, "mercadoria_do_mes", mercadoria_sintetica)


def test_producao_propria_com_ipi_mantido_vai_ao_anexo_ii_em_2027(
    empresa_a, usuario_gestor_a, monkeypatch
):
    """IPI mantido (ZFM) informado: produção própria fica no ANEXO II em 2027 (art. 25, § 1º, II).

    Anexo II, RBT12 300.000, faixa 2 (nominal 7,80%, a deduzir 5.940): efetiva
    (23.400 − 5.940) / 300.000 = 0,0582. Receita líquida 10.000:
    IRPJ 5,50% → 32,01 · CSLL 3,50% → 20,37 · CBS 13,85% → 80,607 → 80,61 · CPP 37,50% → 218,25
    IPI 7,50% → 43,65 · ICMS 32,00% → 186,24 · IBS 0,15% → 0,873 → 0,87. Total 582,00.

    MUTANTE que este teste derruba: ignorar o dado da empresa (tudo de produção própria ao Anexo I
    em 2027) — aí sairiam 532,00, sem IPI na lista.
    """
    empresa = cenario_simples(empresa_a)
    _producao_propria(empresa, usuario_gestor_a, monkeypatch)
    servico_receita.definir_ipi_mantido(
        empresa,
        SituacaoIpiMantido.IPI_MANTIDO,
        "Ato de incentivo à Zona Franca de Manaus (declaração do cliente, 10/2026)",
        usuario_gestor_a,
    )

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert [(a.anexo, a.mercado) for a in resultado.anexos] == [("II", "interno")]
    assert por_tributo(resultado) == {
        "IRPJ": D("32.01"),
        "CSLL": D("20.37"),
        "CBS": D("80.61"),
        "CPP": D("218.25"),
        "IPI": D("43.65"),
        "ICMS": D("186.24"),
        "IBS": D("0.87"),
    }
    assert resultado.total == D("582.00")


def test_producao_propria_com_sem_ipi_mantido_vai_ao_anexo_i_em_2027(
    empresa_a, usuario_gestor_a, monkeypatch
):
    """Sem IPI mantido (fora da ZFM) informado: produção própria vai ao ANEXO I em 2027.

    Mesma conta do comércio do Anexo I (faixa 2, efetiva 5,32%) sobre 10.000:
    IRPJ 29,26 · CSLL 18,62 · CBS 81,56 · CPP 220,78 · ICMS 180,88 · IBS 0,90. Total 532,00.
    """
    empresa = cenario_simples(empresa_a)
    _producao_propria(empresa, usuario_gestor_a, monkeypatch)
    servico_receita.definir_ipi_mantido(
        empresa,
        SituacaoIpiMantido.SEM_IPI_MANTIDO,
        "Declaração do cliente: indústria fora da Zona Franca (10/2026)",
        usuario_gestor_a,
    )

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert [(a.anexo, a.mercado) for a in resultado.anexos] == [(ANEXO_I, "interno")]
    assert por_tributo(resultado) == {
        "IRPJ": D("29.26"),
        "CSLL": D("18.62"),
        "CBS": D("81.56"),
        "CPP": D("220.78"),
        "ICMS": D("180.88"),
        "IBS": D("0.90"),
    }
    assert resultado.total == D("532.00")


def test_dado_de_ipi_mantido_nao_informado_nao_presume_zfm_e_avisa(
    empresa_a, usuario_gestor_a, monkeypatch
):
    """Sem linha de IPI mantido, o produto NÃO presume ZFM: a produção própria calcula no Anexo I
    (a regra geral) e o pré-DAS AVISA que o dado falta, nomeando a consequência.

    Total 532,00 (Anexo I), como no caso de "sem IPI mantido". MUTANTE que este teste derruba:
    presumir ZFM sem dado (produção própria ao Anexo II por padrão) — sairiam 582,00 com IPI.
    """
    empresa = cenario_simples(empresa_a)
    _producao_propria(empresa, usuario_gestor_a, monkeypatch)

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert [(a.anexo, a.mercado) for a in resultado.anexos] == [(ANEXO_I, "interno")]
    assert resultado.total == D("532.00")
    assert any("IPI mantido" in aviso and "não informado" in aviso for aviso in resultado.avisos)
    assert any("IPI mantido" in p.descricao for p in resultado.memoria)


def test_revenda_nao_depende_do_dado_de_ipi_mantido(empresa_a, usuario_gestor_a, monkeypatch):
    """Revenda (Anexo I) em 2027 não é afetada pelo dado de IPI mantido, informado ou não: sem
    produção própria não há aviso nem mudança de anexo."""
    empresa = cenario_simples(empresa_a)
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
                    bruto=D("11000"),
                    deduzido=D("1000"),
                ),
            ),
            deduzido_sem_segmento={"interno": D("0"), "externo": D("0")},
        )

    monkeypatch.setattr(servico_receita, "mercadoria_do_mes", mercadoria_sintetica)

    resultado = motor._calcular_pre_das(empresa, 2027, 1, regime_regular_ibs_cbs=False)

    assert [(a.anexo, a.mercado) for a in resultado.anexos] == [(ANEXO_I, "interno")]
    assert resultado.total == D("532.00")
    assert not any("IPI mantido" in aviso for aviso in resultado.avisos)
