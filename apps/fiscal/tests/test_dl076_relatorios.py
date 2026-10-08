"""DL-076 (frente A), critério 7: relatórios de retido sofrido (HI-86) e de outros
municípios (HI-85).

Totais por município conferidos com as notas. Os valores são escritos à mão.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import iss_municipal as iss
from apps.fiscal.tests.suporte_iss_dl076 import (
    DEVIDO,
    OUTRO,
    OUTRO_MUNICIPIO,
    PALMAS,
    RETIDO,
    receber,
    regime_aliquota,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def notas_retidas(escritorio_a, usuario_gestor_a, empresa_a):
    """Retidas em outubro: 2 em Palmas (uma com tomador identificado) e 1 em outro município.
    Mais uma devida, que NÃO entra no retido, e uma retida com tpRetISSQN 1 (contradição)."""
    regime_aliquota(empresa_a, usuario_gestor_a)
    r1 = receber(
        escritorio_a,
        usuario_gestor_a,
        20001,
        RETIDO,
        tp_ret_issqn="2",
        c_trib_nac="170101",
        c_loc_incid=PALMAS,
        v_bc="1000.00",
        p_aliq_aplic="5.00",
        v_iss_qn="50.00",
        tomador_documento="99888777000166",
        tomador_nome="Tomadora Retenção Ltda",
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        20002,
        RETIDO,
        tp_ret_issqn="3",
        c_trib_nac="070201",
        c_loc_incid=PALMAS,
        v_bc="200.00",
        p_aliq_aplic="3.00",
        v_iss_qn="6.00",
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        20003,
        RETIDO,
        tp_ret_issqn="2",
        c_trib_nac="170101",
        c_loc_incid=OUTRO_MUNICIPIO,
        v_bc="400.00",
        p_aliq_aplic="2.00",
        v_iss_qn="8.00",
    )
    receber(escritorio_a, usuario_gestor_a, 20004, DEVIDO, c_trib_nac="170101", v_iss_qn="77.00")
    receber(escritorio_a, usuario_gestor_a, 20005, RETIDO, tp_ret_issqn="1", v_iss_qn="13.00")
    return r1


def test_retido_sofrido_total_por_municipio_confere_com_as_notas(notas_retidas, empresa_a):
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    assert {n.numero for n in rel.notas} == {"20001", "20002", "20003"}
    por = {g.municipio_ibge: g.total for g in rel.grupos}
    assert por[PALMAS] == Decimal("56.00")  # 50,00 + 6,00
    assert por[OUTRO_MUNICIPIO] == Decimal("8.00")


def test_retido_sofrido_traz_tomador_municipio_subitem_base_aliquota_e_valor(
    notas_retidas, empresa_a
):
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    nota = next(n for n in rel.notas if n.numero == "20001")
    assert nota.tomador_documento == "99888777000166"
    assert nota.tomador_nome == "Tomadora Retenção Ltda"
    assert nota.c_loc_incid == PALMAS
    assert nota.subitem == "17.01"
    assert nota.v_bc == Decimal("1000.00")
    assert nota.p_aliq_aplic == Decimal("5.00")
    assert nota.v_iss_qn == Decimal("50.00")


def test_retido_com_tpretissqn_1_e_devido_ficam_fora_com_aviso(notas_retidas, empresa_a):
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    assert "20004" not in {n.numero for n in rel.notas}
    assert "20005" not in {n.numero for n in rel.notas}
    assert any(a.codigo == "retencao_nao_confirmada" and "20005" in a.mensagem for a in rel.avisos)


def test_vencimento_do_retido_em_palmas_e_dia_15_do_mes_seguinte(notas_retidas, empresa_a):
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    palmas = next(g for g in rel.grupos if g.municipio_ibge == PALMAS)
    assert palmas.vencimento_retido == date(2026, 11, 15)


def test_retido_de_municipio_sem_regra_fica_sem_vencimento_e_com_aviso(notas_retidas, empresa_a):
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    grupo = next(g for g in rel.grupos if g.municipio_ibge == OUTRO_MUNICIPIO)
    assert grupo.vencimento_retido is None
    assert grupo.aviso and "não cadastrada" in grupo.aviso


def test_retido_com_campo_ausente_nao_soma_como_zero(escritorio_a, usuario_gestor_a, empresa_a):
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        20101,
        RETIDO,
        tp_ret_issqn="2",
        c_trib_nac="170101",
        v_iss_qn=None,
    )
    rel = iss.relatorio_iss_retido_sofrido(empresa_a, 2026, 10)
    grupo = next(g for g in rel.grupos if g.municipio_ibge == PALMAS)
    assert grupo.total == Decimal("0.00")
    assert grupo.incompletas == ("20101",)
    nota = rel.notas[0]
    assert nota.v_iss_qn is None
    assert any("vISSQN" in ausente for ausente in nota.ausentes)


# ---------------------------------------------------------------------------
# Outros municípios (HI-85)
# ---------------------------------------------------------------------------


@pytest.fixture
def notas_outro_municipio(escritorio_a, usuario_gestor_a, empresa_a):
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        30001,
        OUTRO,
        c_loc_incid=OUTRO_MUNICIPIO,
        c_trib_nac="170101",
        p_aliq_aplic="5.00",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        30002,
        OUTRO,
        c_loc_incid="1200401",
        c_trib_nac="170101",
        p_aliq_aplic="1.50",
        v_bc="100.00",
        v_iss_qn="1.50",
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        30003,
        OUTRO,
        c_loc_incid=OUTRO_MUNICIPIO,
        c_trib_nac="070201",
        p_aliq_aplic="3.00",
        v_bc="100.00",
        v_iss_qn="3.00",
    )


def test_outros_municipios_agrupa_os_valores_da_propria_nota(notas_outro_municipio, empresa_a):
    rel = iss.relatorio_iss_outros_municipios(empresa_a, 2026, 10)
    por = {g.municipio_ibge: g.total for g in rel.grupos}
    assert por[OUTRO_MUNICIPIO] == Decimal("53.00")  # 50,00 + 3,00
    assert por["1200401"] == Decimal("1.50")


def test_outros_municipios_avisa_aliquota_fora_de_2_a_5(notas_outro_municipio, empresa_a):
    rel = iss.relatorio_iss_outros_municipios(empresa_a, 2026, 10)
    avisos = [a for a in rel.avisos if a.codigo == "aliquota_fora_de_2_a_5"]
    assert len(avisos) == 1 and "30002" in avisos[0].mensagem


def test_outros_municipios_avisa_incidencia_possivelmente_errada_so_fora_das_excecoes(
    notas_outro_municipio, empresa_a
):
    # 17.01 não está nas exceções do art. 3º e o local é outro: aviso.
    # 07.02 (inciso III) está nas exceções: sem aviso.
    rel = iss.relatorio_iss_outros_municipios(empresa_a, 2026, 10)
    erradas = [a for a in rel.avisos if a.codigo == "incidencia_possivelmente_errada"]
    assert {a.mensagem.split("Nota ")[1].split(":")[0] for a in erradas} == {"30001", "30002"}


def test_outros_municipios_nao_calcula_nem_gera_valor_novo(notas_outro_municipio, empresa_a):
    rel = iss.relatorio_iss_outros_municipios(empresa_a, 2026, 10)
    assert all(n.v_iss_qn is not None for n in rel.notas)
    assert {n.numero for n in rel.notas} == {"30001", "30002", "30003"}


# ---------------------------------------------------------------------------
# Tabela de exceções do art. 3º da LC 116 (texto do Planalto)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subitem", "inciso"),
    [
        ("03.05", "II"),
        ("07.02", "III"),
        ("14.14", "III"),
        ("07.04", "IV"),
        ("07.05", "V"),
        ("07.16", "XII"),
        ("11.01", "XV"),
        ("17.05", "XX"),
        ("17.10", "XXI"),
        ("04.22", "XXIII"),
        ("05.09", "XXIII"),
        ("15.01", "XXIV"),
        ("15.09", "XXV"),
        ("03.04", "§ 1º"),
        ("22.01", "§ 2º"),
        ("12.01", "XVIII"),
        ("16.01", "XIX"),
        ("20.01", "XXII"),
    ],
)
def test_subitem_das_excecoes_do_art_3_com_dois_digitos(subitem, inciso):
    # Subitens de item com um dígito (03, 04, 05, 07) precisam casar no formato II.SS.
    assert iss.excecao_do_art_3(subitem) == inciso


@pytest.mark.parametrize("subitem", ["17.01", "12.13", "01.01", "14.01", "08.01"])
def test_subitem_fora_das_excecoes_do_art_3(subitem):
    # 12.13 é o único subitem do item 12 que NÃO está na exceção (inciso XVIII).
    assert iss.excecao_do_art_3(subitem) is None
