"""DL-084, itens 3 e 4 (HI-102, HI-103): coerência da CSLL retida, e retenção confirmada depois.

- Pura: `proposta_de_retencao` nas três faixas e nas bordas de um centavo. Os valores são escritos à
  mão (base 1.000,00: 4,65% = 46,50; 1% = 10,00).
- Banco: a retenção confirmada tarde não deduz no trimestre seguinte. Os números de IRPJ são
  escritos à mão: 100.000,00 de serviço de comércio por trimestre. Abaixo de R$ 1.250.000,00, não há
  excedente, e o acréscimo de 10% (LC 224) incide só sobre o excedente. A base é a presunção de 8%:
  8.000,00 × 15% = 1.200,00 de IRPJ por trimestre.
"""

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada

pytestmark = pytest.mark.django_db


def _campos(v_ret_csll, tp="3", v_ret_irrf=None, v_pis=None, v_cofins=None):
    """Campos da nota já lidos (sintéticos): só os que a proposta lê."""
    return SimpleNamespace(
        v_ret_csll=None if v_ret_csll is None else D(v_ret_csll),
        tp_ret_pis_cofins=tp,
        v_ret_irrf=v_ret_irrf,
        v_pis=v_pis,
        v_cofins=v_cofins,
    )


# ---------------------------------------------------------------------------
# Critério 3: as três faixas e as bordas de um centavo (base 1.000,00)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("v_ret_csll", "valor_csll"),
    [
        ("46.50", D("10.00")),  # 4,65% exato
        ("46.49", D("10.00")),  # um centavo abaixo: ainda confere
        ("46.51", D("10.00")),  # um centavo acima: ainda confere
    ],
)
def test_faixa_de_465_por_cento_confirma_a_estimativa_nas_bordas_de_um_centavo(
    v_ret_csll, valor_csll
):
    proposta = servico.proposta_de_retencao(_campos(v_ret_csll), D("1000.00"))
    assert proposta.csll_situacao == "estimada"
    assert proposta.csll == valor_csll


@pytest.mark.parametrize("v_ret_csll", ["46.52", "46.48"])
def test_dois_centavos_fora_da_faixa_de_465_viram_a_classificar(v_ret_csll):
    proposta = servico.proposta_de_retencao(_campos(v_ret_csll), D("1000.00"))
    assert proposta.csll is None
    assert proposta.csll_situacao == "a_classificar"
    assert "não bate com 4,65% nem com 1%" in proposta.csll_motivo


@pytest.mark.parametrize("v_ret_csll", ["10.00", "10.01", "9.99"])
def test_faixa_de_1_por_cento_avisa_que_so_a_csll_foi_retida(v_ret_csll):
    # Igual a 1% da base: o tomador reteve só a CSLL. Não se estima; fica "a classificar" com aviso.
    proposta = servico.proposta_de_retencao(_campos(v_ret_csll), D("1000.00"))
    assert proposta.csll is None
    assert proposta.csll_situacao == "a_classificar"
    assert "o tomador reteve só a CSLL?" in proposta.csll_motivo


@pytest.mark.parametrize("v_ret_csll", ["10.02", "9.98", "20.00"])
def test_fora_das_duas_faixas_e_a_classificar_sem_aviso_de_so_csll(v_ret_csll):
    proposta = servico.proposta_de_retencao(_campos(v_ret_csll), D("1000.00"))
    assert proposta.csll is None and proposta.csll_situacao == "a_classificar"
    assert "o tomador reteve só a CSLL?" not in proposta.csll_motivo


def test_base_minuscula_em_que_as_duas_faixas_se_sobrepoem_nao_confirma_nada():
    # Base 0,10: 4,65% = 0,00465 e 1% = 0,001. Com a tolerância de um centavo, zero casa com as
    # duas.
    # Sem ponto de decisão único, a nota fica "a classificar".
    proposta = servico.proposta_de_retencao(_campos("0.00"), D("0.10"))
    assert proposta.csll is None and proposta.csll_situacao == "a_classificar"


def test_codigo_8_e_exato_e_nao_passa_pelo_teste_de_coerencia():
    # tpRetPisCofins 8: a CSLL é o próprio vRetCSLL. Coerência só se aplica ao código 3.
    proposta = servico.proposta_de_retencao(_campos("20.00", tp="8"), D("1000.00"))
    assert proposta.csll == D("20.00") and proposta.csll_situacao == "exata"


def test_base_da_nota_desconta_o_desconto_incondicional():
    # Base = vServ − desconto incondicional (HI-103). Com 2.000,00 de serviço e 1.000,00 de
    # desconto,
    # a base é 1.000,00 e 46,50 confere.
    campos = SimpleNamespace(v_desc_incond=D("1000.00"))
    assert servico.base_da_nota(D("2000.00"), campos) == D("1000.00")
    assert servico.base_da_nota(D("2000.00"), SimpleNamespace(v_desc_incond=None)) == D("2000.00")


# ---------------------------------------------------------------------------
# Critério 3 pelo banco: a nota com `vRetCSLL` de 1% aparece com o aviso
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def relogio_fim_de_2026(monkeypatch):
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))


@pytest.fixture
def presumido(empresa_a, usuario_gestor_a, escritorio_a):
    """Empresa de Lucro Presumido em 2026, critério de competência, comércio como padrão."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    servico.criar_atividade(
        empresa_a,
        {
            "atividade": tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
            "inicio": date(2026, 1, 1),
            "padrao": True,
        },
        usuario_gestor_a,
    )
    return {"empresa": empresa_a}


def test_nota_com_1_por_cento_aparece_a_classificar_com_o_aviso_no_banco(
    presumido, escritorio_a, usuario_gestor_a
):
    nota = nota_efetivada(
        escritorio_a,
        presumido["empresa"],
        usuario_gestor_a,
        sufixo=811,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_csll="10.00",
        tp_ret="3",
    )
    linhas = {
        linha.escrituracao_id: linha
        for linha in servico.retencoes_do_trimestre(presumido["empresa"], 2026, 1)
    }
    assert linhas[nota.pk].csll_proposta is None
    assert linhas[nota.pk].csll_situacao == "a_classificar"
    assert "o tomador reteve só a CSLL?" in linhas[nota.pk].csll_motivo


# ---------------------------------------------------------------------------
# Critério 4: retenção confirmada depois do trimestre de origem
# ---------------------------------------------------------------------------


def _apurar_com_declaracoes(presumido, usuario, trimestres):
    for trimestre in trimestres:
        servico.declarar_sem_receitas_integrais(presumido["empresa"], 2026, trimestre, usuario)


def test_retencao_tardia_reabre_a_origem_e_nunca_deduz_no_trimestre_seguinte(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    nota_t1 = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=821,
        v_serv="100000.00",
        d_compet="2026-01-10",
        ret_irrf="1500.00",
    )
    nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=822,
        v_serv="100000.00",
        d_compet="2026-04-10",
    )
    _apurar_com_declaracoes(presumido, usuario_gestor_a, (1, 2))

    t2_antes = servico.apurar_trimestre(empresa, 2026, 2).irpj
    t1_antes = servico.apurar_trimestre(empresa, 2026, 1).irpj
    assert t1_antes.a_recolher == D("1200.00")  # 8.000,00 × 15%, sem retenção confirmada
    assert t1_antes.saldo_negativo == D("0.00")

    # A retenção de 1.500,00 (nota de janeiro) é confirmada depois: o trimestre de janeiro já
    # existe, e o de abril também.
    servico.confirmar_retencao(empresa, nota_t1.pk, "1500.00", None, "", usuario_gestor_a)

    t1_depois = servico.apurar_trimestre(empresa, 2026, 1).irpj
    t2_depois = servico.apurar_trimestre(empresa, 2026, 2).irpj
    # O excesso (1.500,00 − 1.200,00 = 300,00) aparece no trimestre da receita como saldo negativo
    # (PER/DCOMP), e não vira crédito automático.
    assert t1_depois.a_recolher == D("0.00")
    assert t1_depois.saldo_negativo == D("300.00")
    assert t1_depois.retencao_confirmada == D("1500.00")
    # O trimestre seguinte não muda nada: a dedução ficou no trimestre da receita.
    assert t2_depois.a_recolher == t2_antes.a_recolher == D("1200.00")
    assert t2_depois.retencao_confirmada == D("0.00")
    assert t2_depois.saldo_negativo == D("0.00")
