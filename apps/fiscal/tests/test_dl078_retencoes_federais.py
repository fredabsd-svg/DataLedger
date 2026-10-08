"""DL-078, critério 5 e HI-95/HI-96: retenções federais por tributo, com a competência de cada um.

- INSS (vRetCP): pelo mês de EMISSÃO; vencimento informativo no dia 20 do mês seguinte.
- IRRF (vRetIRRF) e CSRF (vRetCSLL): pela DATA DE PAGAMENTO informada; sem ela, pendentes.
- Ausência de campo não é zero; cancelada, estornada e rascunho não entram.

Valores escritos à mão. Notas sintéticas, pelo pipeline real e pelo serviço real.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import tomadas as servico
from apps.fiscal.models import EscrituracaoTomada, EstadoEscrituracao
from apps.fiscal.retencoes import retencoes_federais
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T2,
    cancelar,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa_a2):
    e, u, t = escritorio_a, usuario_gestor_a, empresa_a2
    c = {}
    # f1: emitida em outubro, paga em 30/10: INSS 11,00 (emissão); IRRF 15,00 e CSRF 20,00
    # (pagamento).
    c["f1"] = tomada_efetivada(
        e,
        t,
        u,
        9301,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-05",
        v_liq="954.00",
        v_ret_cp="11.00",
        v_ret_irrf="15.00",
        v_ret_csll="20.00",
        tp_ret_pis_cofins="3",
        v_pis="6.50",
        v_cofins="30.00",
    )
    servico.informar_data_pagamento(c["f1"], date(2026, 10, 30), "Pagamento sintético", u)
    # f2: emitida em setembro, competência setembro, sem pagamento: fora do INSS de outubro.
    c["f2_setembro"] = tomada_efetivada(
        e,
        t,
        u,
        9302,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-09-28",
        dh_emi="2026-09-28T10:00:00-03:00",
        v_liq="995.00",
        v_ret_cp="5.00",
    )
    # f3: emitida em outubro, CSRF retida, SEM data de pagamento: pendente.
    c["f3_pendente"] = tomada_efetivada(
        e,
        t,
        u,
        9303,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-12",
        dh_emi="2026-10-12T10:00:00-03:00",
        v_liq="995.35",
        v_ret_csll="4.65",
        tp_ret_pis_cofins="3",
    )
    # f4: emitida em outubro, INSS 2,00 e IRRF 1,50 pagos em novembro: INSS de outubro e IRRF de
    # novembro.
    c["f4_novembro"] = tomada_efetivada(
        e,
        t,
        u,
        9304,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-14",
        dh_emi="2026-10-14T10:00:00-03:00",
        v_liq="996.50",
        v_ret_cp="2.00",
        v_ret_irrf="1.50",
    )
    servico.informar_data_pagamento(c["f4_novembro"], date(2026, 11, 2), "Pagamento sintético", u)
    # f5: emitida em outubro, só IRRF 15,00, paga no mesmo dia que f1. SEM vRetCP (ausência ≠ zero).
    c["f5"] = tomada_efetivada(
        e,
        t,
        u,
        9305,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-16",
        dh_emi="2026-10-16T10:00:00-03:00",
        v_liq="985.00",
        v_ret_irrf="15.00",
    )
    servico.informar_data_pagamento(c["f5"], date(2026, 10, 30), "Pagamento sintético", u)
    # f9: competência setembro, paga em 02/10: IRRF 3,00 entra em outubro pela data de pagamento.
    c["f9_pago_em_outubro"] = tomada_efetivada(
        e,
        t,
        u,
        9309,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-09-30",
        dh_emi="2026-09-30T10:00:00-03:00",
        v_liq="997.00",
        v_ret_irrf="3.00",
    )
    servico.informar_data_pagamento(
        c["f9_pago_em_outubro"], date(2026, 10, 2), "Pagamento sintético", u
    )
    # f6: emitida em outubro com INSS 100,00, e depois CANCELADA: fora, à parte.
    c["f6_cancelada"] = tomada_efetivada(
        e,
        t,
        u,
        9306,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-18",
        dh_emi="2026-10-18T10:00:00-03:00",
        v_liq="900.00",
        v_ret_cp="100.00",
    )
    cancelar(e, u, c["f6_cancelada"].vinculo.documento, sufixo_evento=1)
    # f8: emitida em outubro com INSS 60,00, depois ESTORNADA: fora.
    c["f8_estornada"] = tomada_efetivada(
        e,
        t,
        u,
        9308,
        T2,
        tp_ret_issqn="1",
        d_compet="2026-10-20",
        dh_emi="2026-10-20T10:00:00-03:00",
        v_liq="940.00",
        v_ret_cp="60.00",
    )
    servico.estornar_escrituracao_tomada(c["f8_estornada"], "Duplicidade", u)
    # f7: RASCUNHO com INSS 50,00: não entra.
    rascunho = receber_tomada(
        e,
        u,
        9307,
        tomador_documento=t.cnpj,
        tp_ret_issqn="1",
        d_compet="2026-10-19",
        dh_emi="2026-10-19T10:00:00-03:00",
        v_liq="950.00",
        v_ret_cp="50.00",
    )
    servico.salvar_rascunho(vinculo_tomador(rascunho, t), T2, u)
    return c


def test_inss_e_pela_emissao_e_soma_so_as_notas_efetivadas_com_valor(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    # f1 (11,00) e f4 (2,00), emitidas em outubro. f2 (setembro), f5 (sem vRetCP), f6 (cancelada),
    # f8 (estornada) e f7 (rascunho) ficam de fora.
    assert resultado.inss_total == Decimal("13.00")
    assert [n.pk for n in resultado.inss_notas] == [cenario["f1"].pk, cenario["f4_novembro"].pk]
    assert resultado.inss_vencimento == date(2026, 11, 20)
    assert "Lei 8.212, art. 31" in resultado.inss_vencimento_texto


def test_rascunho_com_inss_copiado_nao_entra_pela_regra_de_estado(
    cenario, empresa_a2, escritorio_a, usuario_gestor_a
):
    # Mesmo caso do ISS: rascunho com valores copiados (que o serviço nunca grava). Só a regra de
    # estado pode excluí-lo do INSS do mês de emissão.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9350,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="1",
        d_compet="2026-10-23",
        dh_emi="2026-10-23T10:00:00-03:00",
        v_liq="923.00",
    )
    EscrituracaoTomada.objects.bulk_create(
        [
            EscrituracaoTomada(
                vinculo=vinculo_tomador(documento, empresa_a2),
                empresa=empresa_a2,
                natureza=T2,
                estado=EstadoEscrituracao.RASCUNHO,
                data_emissao=date(2026, 10, 23),
                data_competencia=date(2026, 10, 23),
                tp_ret_issqn="1",
                valor_servico=Decimal("1000.00"),
                valor_liquido=Decimal("923.00"),
                v_ret_cp=Decimal("77.00"),
                tp_emit="1",
                criado_por=usuario_gestor_a,
            )
        ]
    )

    resultado = retencoes_federais(empresa_a2, 2026, 10)

    assert resultado.inss_total == Decimal("13.00")  # sem os 77,00 do rascunho
    assert cenario["f1"].pk in [n.pk for n in resultado.inss_notas]


def test_irrf_e_agrupado_pela_data_de_pagamento_de_outubro(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    por_data = {g.data_pagamento: g for g in resultado.irrf_por_pagamento}
    # 30/10: f1 (15,00) e f5 (15,00) = 30,00. 02/10: f9 (3,00). f4 é de 02/11: não está aqui.
    assert set(por_data) == {date(2026, 10, 2), date(2026, 10, 30)}
    assert por_data[date(2026, 10, 30)].total == Decimal("30.00")
    assert por_data[date(2026, 10, 2)].total == Decimal("3.00")
    assert resultado.irrf_total == Decimal("33.00")


def test_csrf_e_agrupada_pela_data_de_pagamento_e_e_csll_mais_pis_cofins(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    assert [g.data_pagamento for g in resultado.csrf_por_pagamento] == [date(2026, 10, 30)]
    assert resultado.csrf_total == Decimal("20.00")
    assert resultado.csrf_por_pagamento[0].notas[0].pk == cenario["f1"].pk


def test_irrf_e_csrf_sem_data_de_pagamento_ficam_pendentes_e_nunca_presumidas(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    # f3 tem CSRF 4,65 e competência outubro, sem data de pagamento: pendente.
    # f2 (setembro) não tem IRRF/CSRF; f5 tem pagamento. Nenhuma é presumida como paga.
    assert [n.pk for n in resultado.pendentes_de_pagamento] == [cenario["f3_pendente"].pk]


def test_cancelada_aparece_a_parte_e_nunca_soma(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    assert [n.pk for n in resultado.canceladas] == [cenario["f6_cancelada"].pk]
    assert resultado.inss_total == Decimal("13.00")  # os 100,00 da cancelada não somaram


def test_competencia_de_novembro_mostra_o_irrf_pago_em_novembro(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 11)

    assert [g.data_pagamento for g in resultado.irrf_por_pagamento] == [date(2026, 11, 2)]
    assert resultado.irrf_total == Decimal("1.50")
    # Nenhuma nota foi emitida em novembro: INSS total é None (nada destacado), não zero.
    assert resultado.inss_total is None


def test_avisos_de_conferencia_aparecem_na_nota_certa(cenario, empresa_a2):
    resultado = retencoes_federais(empresa_a2, 2026, 10)

    codigos_por_nota = {}
    for escrituracao, aviso in resultado.avisos:
        codigos_por_nota.setdefault(escrituracao.pk, set()).add(aviso.codigo)
    # f1 tem vPis com tpRetPisCofins 3: ambíguo, nunca somado. Tem INSS: A7 informativo.
    assert "AMBIGUO_PIS_COFINS" in codigos_por_nota[cenario["f1"].pk]
    assert "A7" in codigos_por_nota[cenario["f1"].pk]
    # f3 tem CSRF de 4,65 (A5: abaixo de R$ 10,00).
    assert "A5" in codigos_por_nota[cenario["f3_pendente"].pk]
