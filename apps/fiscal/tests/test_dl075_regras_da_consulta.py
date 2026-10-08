"""DL-075 (frente C) — regras da consulta do contador-senior de 08/10/2026: HI-78, HI-79, HI-81.

Cada valor esperado está ESCRITO À MÃO no comentário do teste, a partir das tabelas oficiais
(docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md), e nunca é gerado pelo código.
Dados sintéticos. Valores em reais, duas casas, ROUND_HALF_UP por tributo (HI-71).

Tabelas usadas (Anexo III, salvo indicação):
- 1ª faixa (até 180.000,00): alíquota 6%, PD 0; repartição IRPJ 4,00%, CSLL 3,50%,
  Cofins 12,82%, PIS 2,78%, CPP 43,40%, ISS 33,50%.
- 2ª faixa (180.000,01 a 360.000,00): alíquota 11,20%, PD 9.360; ISS 32,00%.
- 4ª faixa (720.000,01 a 1.800.000,00): alíquota 16%, PD 35.640; repartição IRPJ 4,00%,
  CSLL 3,50%, Cofins 13,64%, PIS 2,96%, CPP 43,40%, ISS 32,50%.
- 5ª faixa (1.800.000,01 a 3.600.000,00): alíquota 21%, PD 125.640. Acima de 14,92537% de
  alíquota efetiva, teto do ISS: ISS fixo em 5% e federais = (efetiva − 5%) × IRPJ 6,02%,
  CSLL 5,26%, Cofins 19,28%, PIS 4,18%, CPP 65,26%.
- Anexo V, 1ª faixa: alíquota 15,5%, PD 0; repartição IRPJ 25%, CSLL 15%, Cofins 14,10%,
  PIS 3,05%, CPP 28,85%, ISS 14%.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import folha_fator_r as folha_servico
from apps.fiscal import pre_das as servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EnquadramentoAtividade,
    NaturezaOperacao,
    SituacaoIssReceitaInformada,
)
from apps.fiscal.tests.test_dl074_suporte import escriturar, informar_e_confirmar
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    janela_de_receitas,
    receber_e_confirmar_mes,
    sequencia_anterior,
)

pytestmark = pytest.mark.django_db

ANEXO_III = EnquadramentoAtividade.ANEXO_III
ANEXO_III_OU_V = EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R


def _janela_externa(empresa, usuario, ate_ano, ate_mes, valor_mensal):
    """RBT12 EXTERNO: os 12 meses anteriores ao PA, confirmados, sem ISS (exportação)."""
    for ano, mes in sequencia_anterior(ate_ano, ate_mes):
        informar_e_confirmar(empresa, usuario, ano, mes, valor_mensal, mercado="externo")
        servico_receita.confirmar_mes(empresa, ano, mes, usuario)


def _janela_com_zeros(empresa, usuario, ate_ano, ate_mes, valores):
    """Os 12 meses anteriores ao PA. Mês de valor zero é confirmado SEM receita (a receita
    informada não aceita zero: ela é positiva por regra)."""
    for (ano, mes), valor in zip(sequencia_anterior(ate_ano, ate_mes), valores, strict=True):
        if valor == 0:
            servico_receita.confirmar_mes(empresa, ano, mes, usuario)
        else:
            receber_e_confirmar_mes(empresa, usuario, ano, mes, valor)


def _receita_informada(empresa, usuario, *, mercado, valor, situacao=None, mes=6):
    receita = servico_receita.lancar_receita_informada(
        empresa,
        2026,
        mes,
        mercado,
        valor,
        "outras_receitas_atividade",
        "Motivo sintético.",
        SUPORTE_SINTETICO,
        usuario,
        situacao_iss=situacao,
    )
    return servico_receita.confirmar_receita_informada(receita, usuario)


def _valores(linhas):
    return {linha.tributo: str(linha.valor) for linha in linhas}


# ---------------------------------------------------------------------------
# HI-79: teto do ISS (5ª faixa) ANTES de desconsiderar o ISS da receita retida ou exportada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("via", ["escriturada", "informada"])
def test_hi79_retido_na_5a_faixa_com_teto_aplica_o_teto_antes_de_desconsiderar_o_iss(
    empresa_a, usuario_gestor_a, via
):
    """Mão, com RBT12 interno = 12 × 250.000 = 3.000.000 (5ª faixa):
    alíquota efetiva = (3.000.000 × 21% − 125.640) / 3.000.000 = 504.360 / 3.000.000 = 16,812%.
    Acima de 14,92537%: o teto fixa o ISS em 5% e redistribui o excedente, 16,812% − 5% = 11,812%:
      IRPJ 11,812% × 6,02% = 0,7110824%; CSLL × 5,26% = 0,6213112%;
      Cofins × 19,28% = 2,2773536%; PIS × 4,18% = 0,4937416%; CPP × 65,26% = 7,7085112%.
    DEPOIS, o ISS (5%) é desconsiderado. Receita retida 100.000,00:
      IRPJ 711,0824 → 711,08; CSLL 621,3112 → 621,31; Cofins 2.277,3536 → 2.277,35;
      PIS 493,7416 → 493,74; CPP 7.708,5112 → 7.708,51; ISS 0,00. Total 11.811,99.
    A receita informada retida (HI-80) tem de dar exatamente o mesmo resultado."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [250000] * 12)
    if via == "escriturada":
        escriturar(
            empresa_a.escritorio,
            empresa,
            usuario_gestor_a,
            sufixo=9401,
            competencia=(2026, 6),
            valor="100000.00",
            natureza=NaturezaOperacao.PRESTADO_ISS_RETIDO,
        )
    else:
        _receita_informada(
            empresa,
            usuario_gestor_a,
            mercado="interno",
            valor="100000.00",
            situacao=SituacaoIssReceitaInformada.RETIDO,
        )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    assert anexo.teto_iss_aplicado is True
    assert anexo.aliquota_efetiva == Decimal("0.16812")
    (segmento,) = anexo.segmentos
    assert segmento.segmento == servico.SEG_RETIDO
    linhas = {linha.tributo: linha for linha in segmento.linhas}
    # Os percentuais dos federais já trazem o excedente (teto ANTES); o ISS é 5% e cai a zero.
    assert linhas["IRPJ"].percentual == Decimal("0.007110824")
    assert linhas["CSLL"].percentual == Decimal("0.006213112")
    assert linhas["COFINS"].percentual == Decimal("0.022773536")
    assert linhas["PIS"].percentual == Decimal("0.004937416")
    assert linhas["CPP"].percentual == Decimal("0.077085112")
    assert linhas["ISS"].percentual == Decimal("0.05")
    assert linhas["ISS"].desconsiderado is True
    assert _valores(segmento.linhas) == {
        "IRPJ": "711.08",
        "CSLL": "621.31",
        "COFINS": "2277.35",
        "PIS": "493.74",
        "CPP": "7708.51",
        "ISS": "0.00",
    }
    assert str(resultado.total) == "11811.99"


@pytest.mark.parametrize("via", ["escriturada", "informada"])
def test_hi79_exportacao_na_5a_faixa_com_teto_desconsidera_iss_e_pis_cofins_ja_com_o_excedente(
    empresa_a, usuario_gestor_a, via
):
    """Mão, com RBT12 EXTERNO = 3.000.000 (5ª faixa, efetiva 16,812%, teto como acima).
    Exportação de 100.000,00: desconsidera ISS (5%), Cofins e PIS, JÁ com o excedente:
    Cofins 2,2773536% e PIS 0,4937416%, que saem a zero. IRPJ, CSLL e CPP ficam:
      IRPJ 711,08; CSLL 621,31; CPP 7.708,51; Total 9.040,90."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    _janela_externa(empresa, usuario_gestor_a, 2026, 6, Decimal("250000"))
    if via == "escriturada":
        escriturar(
            empresa_a.escritorio,
            empresa,
            usuario_gestor_a,
            sufixo=9402,
            competencia=(2026, 6),
            valor="100000.00",
            natureza=NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
        )
    else:
        _receita_informada(empresa, usuario_gestor_a, mercado="externo", valor="100000.00")
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.rbt12["externo"] == Decimal("3000000.00")
    (anexo,) = resultado.anexos
    assert (anexo.mercado, anexo.anexo, anexo.teto_iss_aplicado) == ("externo", "III", True)
    (segmento,) = anexo.segmentos
    assert segmento.segmento == servico.SEG_EXPORTACAO
    linhas = {linha.tributo: linha for linha in segmento.linhas}
    assert linhas["COFINS"].percentual == Decimal("0.022773536")
    assert linhas["PIS"].percentual == Decimal("0.004937416")
    assert all(
        linhas[t].desconsiderado and linhas[t].valor == Decimal("0.00")
        for t in ("COFINS", "PIS", "ISS")
    )
    assert _valores(segmento.linhas) == {
        "IRPJ": "711.08",
        "CSLL": "621.31",
        "COFINS": "0.00",
        "PIS": "0.00",
        "CPP": "7708.51",
        "ISS": "0.00",
    }
    assert str(resultado.total) == "9040.90"


# ---------------------------------------------------------------------------
# HI-78: exportação SEM redistribuição (IRPJ, CSLL e CPP pela efetiva do RBT12 externo)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("via", ["escriturada", "informada"])
def test_hi78_exportacao_sem_redistribuicao_irpj_csll_cpp_na_efetiva_do_rbt12_externo(
    empresa_a, usuario_gestor_a, via
):
    """Mão, com RBT12 EXTERNO = 12 × 100.000 = 1.200.000 → 4ª faixa (720.000,01 a 1.800.000):
    alíquota efetiva = (1.200.000 × 16% − 35.640) / 1.200.000 = 156.360 / 1.200.000 = 13,03%.
    Abaixo de 14,92537%: não há teto. Sem redistribuição (art. 25 § 3º, "tão somente"):
      IRPJ 4% × 13,03% = 0,5212%; CSLL 3,5% × 13,03% = 0,45605%; CPP 43,40% × 13,03% = 5,65502%.
    Exportação de 100.000,00: IRPJ 521,20; CSLL 456,05; CPP 5.655,02; Cofins, PIS e ISS 0,00.
    Total 6.632,27. Com a receita informada (mercado externo, sem situação de ISS) o
    resultado é o mesmo: a exportação informada vai ao segmento de exportação."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    _janela_externa(empresa, usuario_gestor_a, 2026, 6, Decimal("100000"))
    if via == "escriturada":
        escriturar(
            empresa_a.escritorio,
            empresa,
            usuario_gestor_a,
            sufixo=9403,
            competencia=(2026, 6),
            valor="100000.00",
            natureza=NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
        )
    else:
        _receita_informada(empresa, usuario_gestor_a, mercado="externo", valor="100000.00")
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    assert anexo.teto_iss_aplicado is False
    assert anexo.aliquota_efetiva == Decimal("0.1303")
    (segmento,) = anexo.segmentos
    linhas = {linha.tributo: linha for linha in segmento.linhas}
    assert linhas["IRPJ"].percentual == Decimal("0.005212")
    assert linhas["CSLL"].percentual == Decimal("0.0045605")
    assert linhas["CPP"].percentual == Decimal("0.0565502")
    assert _valores(segmento.linhas) == {
        "IRPJ": "521.20",
        "CSLL": "456.05",
        "COFINS": "0.00",
        "PIS": "0.00",
        "CPP": "5655.02",
        "ISS": "0.00",
    }
    assert str(resultado.total) == "6632.27"


# ---------------------------------------------------------------------------
# HI-81 (i): sublimite — receita acumulada no ano acima de R$ 3,6 mi, RBT12 ainda ≤ 3,6 mi
# ---------------------------------------------------------------------------


def test_hi81_acumulado_no_ano_acima_do_sublimite_com_rbt12_dentro_recusa_nomeando_o_sublimite(
    empresa_a, usuario_gestor_a
):
    """Mão, PA 03/2026, abertura antiga (regime cheio). Os 12 meses anteriores ao PA são
    mar/2025 a fev/2026: jan/2026 = 2.000.000, fev/2026 = 500.000, os outros 10 meses = 0.
      RBT12 = 2.000.000 + 500.000 = 2.500.000 ≤ 3.600.000 (o RBT12 sozinho não recusa).
      Acumulado no ano (jan a mar) = 2.000.000 + 500.000 + 1.200.000 (PA) = 3.700.000,
      acima do sublimite de 3.600.000 (Res. CGSN 140, art. 12; Portaria CGSN 54/2025).
      Excesso de 2,78%, até 20%. O pré-DAS RECUSA e nomeia o sublimite, sem calcular número."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    _janela_com_zeros(empresa, usuario_gestor_a, 2026, 3, [0] * 10 + [2000000, 500000])
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 3, "1200000.00")

    assert apuracao.rbt12(empresa, 2026, 3).de("interno").apurado == Decimal("2500000")

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2026, 3)
    (bloqueio,) = [
        b for b in excecao.value.bloqueios if b.codigo == "excesso_de_limite_ou_sublimite"
    ]
    assert "sublimite de 3600000.00" in bloqueio.mensagem
    assert "(3700000.00)" in bloqueio.mensagem


# ---------------------------------------------------------------------------
# HI-81 (ii): fator r no PRIMEIRO mês de atividade (art. 26 § 6º): folha do mês / receita do mês
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "folha, fs12, fator, anexo, total",
    [
        # FS do mês 2.800 → FS12 = 2.800 × 12 = 33.600; r = 33.600 / 120.000 = 0,28 → Anexo III.
        # Anexo III, 1ª faixa: 6% × 10.000 = 600,00.
        ("2800.00", "33600", "0.28", "III", "600.00"),
        # 2.799 → r = 0,2799, truncado em 0,27 → Anexo V. Efetiva 15,5% × 10.000, com cada
        # tributo arredondado (HI-71): 387,50 + 232,50 + 218,55 + 47,28 (47,275) + 447,18
        # (447,175) + 217,00 = 1.550,01.
        ("2799.00", "33588", "0.27", "V", "1550.01"),
        # FS do mês 0 com receita do mês > 0 → r = 0,01 (art. 26 § 6º, II) → Anexo V: 1.550,01.
        ("0", "0", "0.01", "V", "1550.01"),
    ],
)
def test_hi81_fator_r_do_primeiro_mes_e_folha_do_mes_sobre_receita_do_mes(
    empresa_a, usuario_gestor_a, folha, fs12, fator, anexo, total
):
    """Abertura e opção em 10/03/2026: PA 03/2026 é o 1º mês (§ 2º). RBT12 = receita do
    próprio mês × 12 = 10.000 × 12 = 120.000. A folha usa a mesma escala (× 12), e a razão
    é FSPA / RPAr = folha do mês / receita do mês (art. 26 § 6º, III)."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III_OU_V)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 3, "10000.00")
    folha_confirmada(empresa, usuario_gestor_a, 2026, 3, remuneracao=folha)

    resultado = servico.pre_das(empresa, 2026, 3)

    assert resultado.rbt12["interno"] == Decimal("120000")
    assert resultado.fator_r.fs12 == Decimal(fs12)
    assert resultado.fator_r.valor == Decimal(fator)
    (apurado,) = resultado.anexos
    assert apurado.anexo == anexo
    assert str(resultado.total) == total


def test_hi81_fator_r_com_folha_no_primeiro_mes_e_receita_zero_e_0_28(empresa_a, usuario_gestor_a):
    """Art. 26 § 6º, I: FSPA > 0 e RPAr = 0 → 0,28 (rotina do PGDAS-D, não norma).
    Mão: FS12 = 2.800 × 12 = 33.600 e RBT12 = 0 × 12 = 0. Sem receita, a razão não existe:
    a regra de zero dá 0,28. O mês confirmado sem receita é o caso."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    servico_receita.confirmar_mes(empresa, 2026, 3, usuario_gestor_a)
    folha_confirmada(empresa, usuario_gestor_a, 2026, 3, remuneracao="2800.00")

    fs = folha_servico.fs12(empresa, 2026, 3)
    rbt = apuracao.rbt12(empresa, 2026, 3)
    conjunto = rbt.de("interno").apurado + rbt.de("externo").apurado
    valor, regra_de_zero = servico.fator_r(fs.valor, conjunto)

    assert (fs.valor, conjunto) == (Decimal("33600"), Decimal("0"))
    assert valor == Decimal("0.28")
    assert regra_de_zero is not None


# ---------------------------------------------------------------------------
# HI-81 (iii): empresa aberta em 10/2025, PA 02/2026 — soma/média da ATIVIDADE, nunca 12 meses
# ---------------------------------------------------------------------------


def test_hi81_fator_r_de_empresa_aberta_em_10_2025_soma_os_meses_de_atividade_nao_12_meses(
    empresa_a, usuario_gestor_a
):
    """Abertura e opção em 10/10/2025 (§ 3º). PA 02/2026 é o 5º mês de atividade; os meses
    da janela são out/2025 a jan/2026 (4 meses). Mão, com receita de 10.000 e folha de 3.000
    por mês:
      RBT12 = (4 × 10.000) / 4 × 12 = 120.000 (a média dos meses de atividade, × 12).
      FS12  = (4 × 3.000) / 4 × 12 = 36.000.
      Fator r = 36.000 / 120.000 = 0,30 → Anexo III; 6% × 10.000 = 600,00.
    Somar 12 meses (zeros antes da abertura) daria FS12 = 12.000 e r = 0,10 → Anexo V."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2025, 10, 10), inicio_simples=date(2025, 10, 10)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III_OU_V)
    for ano, mes in [(2025, 10), (2025, 11), (2025, 12), (2026, 1)]:
        receber_e_confirmar_mes(empresa, usuario_gestor_a, ano, mes, "10000.00")
        folha_confirmada(empresa, usuario_gestor_a, ano, mes, remuneracao="3000.00")
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 2, "10000.00")

    resultado = servico.pre_das(empresa, 2026, 2)

    assert resultado.rbt12["interno"] == Decimal("120000")
    assert resultado.fator_r.fs12 == Decimal("36000")
    assert resultado.fator_r.valor == Decimal("0.30")
    (apurado,) = resultado.anexos
    assert apurado.anexo == "III"
    assert str(resultado.total) == "600.00"
