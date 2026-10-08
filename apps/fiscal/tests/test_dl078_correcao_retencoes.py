"""DL-078, correção da auditoria rodada 1, achado A3: três regras que a suíte não protegia.

- M7: INSS (vRetCP) pelo mês de EMISSÃO, não pelo de competência (Lei 8.212, art. 31; HI-96).
- M9: T5, T6 e T7 sem retenção (tpRetISSQN 1 ou 3) NÃO entram no ISS retido, mesmo com vISSQN
  destacado: o que conta é tpRetISSQN 2 (item 0 da frente B).
- M5b: a prestadora não vê como TOMADA a nota que ela própria emitiu (isolamento entre empresas do
  mesmo escritório, AGENTS.md §11).

Cada teste tem um controle positivo: sem ele, um resultado vazio passaria sem provar nada.
Valores sintéticos, escritos à mão.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import tomadas as servico
from apps.fiscal.retencoes import iss_retido_a_recolher, retencoes_federais
from apps.fiscal.tests.suporte_tomada_dl078 import (
    PALMAS,
    T1,
    T2,
    T5,
    T6,
    T7,
    receber_tomada,
    tomada_efetivada,
)
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]

D = Decimal


def test_inss_entra_pelo_mes_de_emissao_e_nao_pelo_de_competencia(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    # Emitida em 28/09 com competência 02/10: o INSS é de SETEMBRO (emissão), não de outubro.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8401,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-02",
        dh_emi="2026-09-28T09:00:00-03:00",
        v_ret_cp="110.00",
        v_liq="890.00",
    )

    setembro = retencoes_federais(empresa_a2, 2026, 9)
    outubro = retencoes_federais(empresa_a2, 2026, 10)

    assert setembro.inss_total == D("110.00")
    assert setembro.inss_vencimento == date(2026, 10, 20)
    assert outubro.inss_total is None
    assert outubro.inss_notas == ()


def test_t5_t6_t7_sem_retencao_com_iss_destacado_nao_entram_no_iss_retido(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    # Controle positivo: a única retida de verdade (tpRetISSQN 2) entra, com o valor dela.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8411,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid=PALMAS,
    )
    # Prestadores do Simples, MEI e pessoa física SEM retenção, com vISSQN destacado: fora.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8412,
        T6,
        tp_ret_issqn="1",
        op_simp_nac="3",
        v_iss_qn="40.00",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8413,
        T5,
        tp_ret_issqn="1",
        op_simp_nac="2",
        v_iss_qn="3.00",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
        federal=False,
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8414,
        T7,
        tp_ret_issqn="1",
        prestador_tipo="CPF",
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        v_iss_qn="2.00",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
        federal=False,
    )
    # tpRetISSQN 3 (não retido) também fica de fora, mesmo na natureza do Simples.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8415,
        T6,
        tp_ret_issqn="3",
        op_simp_nac="3",
        v_iss_qn="9.00",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
    )

    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert [grupo.total for grupo in resultado.grupos] == [D("50.00")]
    assert [nota.natureza for grupo in resultado.grupos for nota in grupo.notas] == [T1]


def test_prestadora_nao_ve_como_tomada_a_nota_que_ela_emitiu(
    escritorio_a, usuario_gestor_a, empresa_a, empresa_a2
):
    # empresa_a EMITE a nota (prestadora) e empresa_a2 é a tomadora: o controle positivo mostra que
    # a tomadora vê a nota, e a prestadora, que é a mesma nota pelo outro lado, não a vê como
    # tomada.
    receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8421,
        prestador_documento=empresa_a.cnpj,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="5.00",
        v_liq="995.00",
        c_loc_incid=PALMAS,
    )

    assert len(servico.notas_tomadas(empresa_a2, 2026, 10)) == 1
    assert servico.notas_tomadas(empresa_a, 2026, 10) == []
    assert iss_retido_a_recolher(empresa_a, 2026, 10).grupos == ()
