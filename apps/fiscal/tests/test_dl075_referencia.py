"""DL-075 (frente A) — CASOS DE REFERÊNCIA OFICIAIS do Manual do PGDAS-D.

Os valores esperados estão escritos À MÃO a partir de
docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md (seção 6, exemplos 2, 4, 5,
8 e item 8.1). Não vêm do código. A comparação é CENTAVO A CENTAVO, por tributo e no
total (critério 1 do plano DL-075).

Dois níveis:
- puro: `pre_das.aliquota_efetiva` e `percentuais_efetivos` sobre a tabela;
- pipeline: `pre_das.pre_das(empresa, ano, mes)` com banco real (receita informada
  confirmada, RBT12 pela janela, folha confirmada, fator r e segregação).
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from apps.fiscal import pre_das as servico
from apps.fiscal import simples_tabelas as tabelas
from apps.fiscal.models import EnquadramentoAtividade
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    folhas_dos_12_meses,
    janela_de_receitas,
    receber_e_confirmar_mes,
)

pytestmark = pytest.mark.django_db


def _por_tributo(linhas):
    return {linha.tributo: str(linha.valor) for linha in linhas}


# ---------------------------------------------------------------------------
# Puro: alíquota efetiva e percentuais, sobre a tabela (sem banco)
# ---------------------------------------------------------------------------


def test_item_8_1_anexo_i_aliquota_efetiva_de_9_2_por_cento():
    """Manual, item 8.1: RBT12 = 1.500.000, nominal 10,70%, PD 22.500,00 → 9,2%."""
    anexo = tabelas.anexo("I")
    faixa = anexo.faixa_da_receita(Decimal("1500000"))
    assert faixa.numero == 4
    assert faixa.aliquota_nominal == Decimal("0.1070")
    assert faixa.parcela_a_deduzir == Decimal("22500.00")
    assert servico.aliquota_efetiva(Decimal("1500000"), faixa) == Decimal("0.092")


def test_exemplo_8_redistribuicao_do_excesso_do_iss_confere_com_o_manual():
    """Manual, exemplo 8: excesso do ISS da 5ª faixa sobre 5% = 1,09968%.

    Só a conferência das CONSTANTES da redistribuição, com os valores impressos no
    Manual (IRPJ 0,0662%, CSLL 0,0578%, Cofins 0,2120%, PIS 0,0460%, CPP 0,7177%). A 6ª
    faixa, que é o resto do exemplo 8, fica fora do primeiro corte (HI-68).
    """
    anexo = tabelas.anexo("III")
    faixa5 = anexo.faixa(5)
    iss_quinta_faixa = (
        (Decimal("4500000") * Decimal("0.21") - Decimal("125640")) / Decimal("4500000")
    ) * faixa5.percentual("ISS")
    assert iss_quinta_faixa == Decimal("0.0609968")
    excesso = iss_quinta_faixa - Decimal("0.05")
    impresso = {
        "IRPJ": "0.0662",
        "CSLL": "0.0578",
        "COFINS": "0.2120",
        "PIS": "0.0460",
        "CPP": "0.7177",
    }
    for tributo, valor_impresso in impresso.items():
        redistribuido_em_percentual = (excesso * dict(anexo.teto_iss.redistribuicao)[tributo]) * 100
        assert redistribuido_em_percentual.quantize(Decimal("0.0001"), ROUND_HALF_UP) == Decimal(
            valor_impresso
        ), tributo


# ---------------------------------------------------------------------------
# Pipeline com banco: exemplos 2, 4 e 5, centavo a centavo
# ---------------------------------------------------------------------------


def test_exemplo_2_anexo_iii_segunda_faixa_centavo_a_centavo(empresa_a, usuario_gestor_a):
    """Manual, exemplo 2: RBT12 300.000; receita do mês 100.000; Anexo III, 2ª faixa.

    Esperado (à mão): alíquota efetiva 8,08%; total 8.080,00; IRPJ 323,20; CSLL 282,80;
    Cofins 1.135,24; PIS 246,44; CPP 3.506,72; ISS 2.585,60.
    """
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.rbt12 == {"interno": Decimal("300000.00")}
    (anexo,) = resultado.anexos
    assert (anexo.anexo, anexo.faixa) == ("III", 2)
    assert anexo.aliquota_efetiva == Decimal("0.0808")
    assert _por_tributo(anexo.segmentos[0].linhas) == {
        "IRPJ": "323.20",
        "CSLL": "282.80",
        "COFINS": "1135.24",
        "PIS": "246.44",
        "CPP": "3506.72",
        "ISS": "2585.60",
    }
    assert str(resultado.total) == "8080.00"


def test_exemplo_4_anexo_iii_pelo_fator_r_0_50_terceira_faixa(empresa_a, usuario_gestor_a):
    """Manual, exemplo 4: fator r 0,50 (FS12 250.000 / RBT12 500.000) → Anexo III, 3ª faixa.

    Esperado (à mão): alíquota efetiva 9,972%; total 997,20; IRPJ 39,89; CSLL 34,90;
    Cofins 136,02; PIS 29,52; CPP 432,78; ISS 324,09.
    """
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [40000] * 11 + [60000])
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [20000] * 11 + [30000])
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "10000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.fator_r.fs12 == Decimal("250000.00")
    assert resultado.fator_r.valor == Decimal("0.50")
    (anexo,) = resultado.anexos
    assert (anexo.anexo, anexo.faixa, anexo.rbt12) == ("III", 3, Decimal("500000.00"))
    assert anexo.aliquota_efetiva == Decimal("0.09972")
    assert _por_tributo(anexo.segmentos[0].linhas) == {
        "IRPJ": "39.89",
        "CSLL": "34.90",
        "COFINS": "136.02",
        "PIS": "29.52",
        "CPP": "432.78",
        "ISS": "324.09",
    }
    assert str(resultado.total) == "997.20"


def test_exemplo_5_anexo_v_pelo_fator_r_0_20_terceira_faixa(empresa_a, usuario_gestor_a):
    """Manual, exemplo 5: fator r 0,20 (FS12 100.000 / RBT12 500.000) → Anexo V, 3ª faixa.

    Esperado (à mão): alíquota efetiva 17,52%; total 1.752,00; IRPJ 420,48; CSLL 262,80;
    Cofins 261,40; PIS 56,59; CPP 417,85; ISS 332,88.
    """
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [40000] * 11 + [60000])
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [10000] * 10 + [0, 0])
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "10000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.fator_r.valor == Decimal("0.20")
    (anexo,) = resultado.anexos
    assert (anexo.anexo, anexo.faixa) == ("V", 3)
    assert anexo.aliquota_efetiva == Decimal("0.1752")
    assert _por_tributo(anexo.segmentos[0].linhas) == {
        "IRPJ": "420.48",
        "CSLL": "262.80",
        "COFINS": "261.40",
        "PIS": "56.59",
        "CPP": "417.85",
        "ISS": "332.88",
    }
    assert str(resultado.total) == "1752.00"


def test_memoria_de_calculo_traz_passo_com_valor_e_dispositivo(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    resultado = servico.pre_das(empresa, 2026, 6)

    assert len(resultado.memoria) >= 10
    assert [passo.ordem for passo in resultado.memoria] == list(
        range(1, len(resultado.memoria) + 1)
    )
    for passo in resultado.memoria:
        assert passo.dispositivo.strip(), passo.descricao
        assert passo.valor.strip(), passo.descricao
    textos = " | ".join(passo.dispositivo for passo in resultado.memoria)
    assert "§ 1º-A" in textos and "§ 1º-B" in textos
