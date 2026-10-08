"""DL-078, correção da auditoria rodada 1, achados A5 e A6 (avisos da tomada).

A5: o aviso AMBIGUO_PIS_COFINS só sai com vPis ou vCofins POSITIVOS. A P&R 13.1 manda manter os dois
zerados quando há retenção, então zero não é ambiguidade (regra de dado, sem norma nova).

A6: os valores nos textos dos avisos saem em pt-BR ("10.000,00"), com o formatador do próprio app
(`apps.fiscal.formatacao_ptbr`, movido de `views_web` sem mudança de comportamento).

Testes puros: `avisos_da_tomada` não toca no banco. Valores sintéticos.
"""

from decimal import Decimal

import pytest

from apps.fiscal.formatacao_ptbr import valor_ptbr
from apps.fiscal.tomadas import DadosTomada, avisos_da_tomada


def _dados(**campos) -> DadosTomada:
    base = dict(
        prestador_tipo_documento="CNPJ",
        tp_ret_issqn=None,
        op_simp_nac=None,
        reg_ap_trib_sn=None,
        valor_servico=None,
        valor_liquido=None,
        v_desc_incond=None,
        v_desc_cond=None,
        v_iss_qn=None,
        v_ret_cp=None,
        v_ret_irrf=None,
        v_ret_csll=None,
        tp_ret_pis_cofins=None,
        v_pis=None,
        v_cofins=None,
    )
    base.update(campos)
    return DadosTomada(**base)


def _por_codigo(avisos, codigo):
    return [aviso for aviso in avisos if aviso.codigo == codigo]


# ---------------------------------------------------------------------------
# A5 — AMBIGUO_PIS_COFINS
# ---------------------------------------------------------------------------


def test_ambiguo_pis_cofins_nao_dispara_com_pis_e_cofins_zerados():
    dados = _dados(
        tp_ret_pis_cofins="3",
        v_ret_csll=Decimal("36.00"),
        v_pis=Decimal("0.00"),
        v_cofins=Decimal("0.00"),
    )

    assert _por_codigo(avisos_da_tomada(dados, None), "AMBIGUO_PIS_COFINS") == []


@pytest.mark.parametrize(
    "campos",
    [
        {"v_pis": Decimal("1.00"), "v_cofins": Decimal("0.00")},
        {"v_pis": Decimal("0.00"), "v_cofins": Decimal("1.00")},
        {"v_pis": Decimal("1.00"), "v_cofins": Decimal("1.00")},
    ],
    ids=["so_pis", "so_cofins", "os_dois"],
)
def test_ambiguo_pis_cofins_dispara_com_valor_positivo_em_qualquer_dos_dois(campos):
    dados = _dados(tp_ret_pis_cofins="3", v_ret_csll=Decimal("36.00"), **campos)

    assert len(_por_codigo(avisos_da_tomada(dados, None), "AMBIGUO_PIS_COFINS")) == 1


def test_ambiguo_pis_cofins_nao_dispara_sem_retencao_mesmo_com_valor_positivo():
    # tpRetPisCofins 0 diz que não há retenção: pis e cofins positivos não são ambíguos aqui.
    dados = _dados(tp_ret_pis_cofins="0", v_pis=Decimal("1.00"), v_cofins=Decimal("1.00"))

    assert _por_codigo(avisos_da_tomada(dados, None), "AMBIGUO_PIS_COFINS") == []


# ---------------------------------------------------------------------------
# A6 — valores em pt-BR nos textos dos avisos
# ---------------------------------------------------------------------------


def test_aviso_a1_mostra_os_valores_em_pt_br():
    # 10000.00 − 36.00 = 9964.00 esperado; líquido informado 10000.00: não fecha.
    dados = _dados(
        valor_servico=Decimal("10000.00"),
        valor_liquido=Decimal("10000.00"),
        v_ret_csll=Decimal("36.00"),
    )

    a1 = _por_codigo(avisos_da_tomada(dados, None), "A1")

    assert len(a1) == 1
    assert "10.000,00" in a1[0].texto
    assert "9.964,00" in a1[0].texto
    assert "10000.00" not in a1[0].texto
    assert "9964.00" not in a1[0].texto


def test_aviso_a5_e_a2_mostram_os_valores_em_pt_br():
    a5 = _por_codigo(avisos_da_tomada(_dados(v_ret_irrf=Decimal("0.50")), None), "A5")
    a2 = _por_codigo(
        avisos_da_tomada(_dados(tp_ret_pis_cofins="0", v_ret_csll=Decimal("1234.50")), None),
        "A2",
    )

    assert "vRetIRRF de 0,50" in a5[0].texto
    assert "R$ 10,00" in a5[0].texto
    assert "vRetCSLL traz 1.234,50" in a2[0].texto


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (Decimal("0"), "0,00"),
        (Decimal("0.5"), "0,50"),
        (Decimal("1234.5"), "1.234,50"),
        (Decimal("1234567.89"), "1.234.567,89"),
        (Decimal("-1234.5"), "-1.234,50"),
        (None, "—"),
    ],
)
def test_valor_ptbr_formata_em_pt_br_sem_float(valor, texto):
    assert valor_ptbr(valor) == texto
