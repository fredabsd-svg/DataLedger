"""DL-078, critério 7: nenhuma tomada entra em receita, RBT12, pré-DAS, apuração do ISS próprio,
nem nos relatórios de ISS retido sofrido e de outros municípios.

Método: captura todos os resultados dos cálculos da empresa com só NOTAS PRESTADAS; efetiva
notas tomadas de todas as naturezas (T1, T2, T3, T5, T6, T7), com retenções federais e data de
pagamento; captura de novo. Os dois conjuntos têm de ser iguais. Uma captura vazia não prova
nada, então também se afirma que a receita de prestadas aparece na captura.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as escrituracao_prestada
from apps.fiscal import tomadas as servico
from apps.fiscal.iss_municipal import (
    apuracao_iss_proprio,
    relatorio_iss_outros_municipios,
    relatorio_iss_retido_sofrido,
)
from apps.fiscal.models import (
    EscrituracaoFiscal,
    EscrituracaoTomada,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.pre_das import pre_das
from apps.fiscal.rbt12 import rbt12
from apps.fiscal.receita import composicao_do_mes, confirmar_mes
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T1,
    T2,
    T3,
    T5,
    T6,
    T7,
    receber_tomada,
    tomada_efetivada,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 10


def _capturar(funcao, *args, **kwargs):
    """Resultado do cálculo, ou a recusa dele. Recusa também é resultado a comparar."""
    try:
        return ("ok", funcao(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 — qualquer recusa do cálculo é um resultado
        return ("recusado", type(exc).__name__, str(exc))


def _capturas(empresa):
    return {
        "composicao": _capturar(composicao_do_mes, empresa, ANO, MES),
        "rbt12": _capturar(rbt12, empresa, ANO, MES),
        "pre_das": _capturar(pre_das, empresa, ANO, MES),
        "apuracao_iss_proprio": _capturar(apuracao_iss_proprio, empresa, ANO, MES),
        "retido_sofrido": _capturar(relatorio_iss_retido_sofrido, empresa, ANO, MES),
        "outros_municipios": _capturar(relatorio_iss_outros_municipios, empresa, ANO, MES),
    }


@pytest.fixture
def prestadas(escritorio_a, usuario_gestor_a, empresa_a2):
    """Empresa tomadora (também prestadora de notas próprias). Só prestadas, até aqui."""
    devida = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9401,
        prestador_documento=empresa_a2.cnpj,
        tomador_documento="77888999000155",
        tp_ret_issqn="1",
        v_serv="1000.00",
        v_liq="1000.00",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
    )
    escrituracao_prestada.efetivar_escrituracao(
        VinculoDocumentoEmpresa.objects.get(
            documento=devida, empresa=empresa_a2, papel=PapelDocumento.PRESTADOR
        ),
        NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR,
        usuario_gestor_a,
    )
    retida = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9402,
        prestador_documento=empresa_a2.cnpj,
        tomador_documento="77888999000155",
        tp_ret_issqn="2",
        v_iss_qn="30.00",
        v_liq="970.00",
        c_loc_incid="1721000",
        d_compet="2026-10-06",
    )
    escrituracao_prestada.efetivar_escrituracao(
        VinculoDocumentoEmpresa.objects.get(
            documento=retida, empresa=empresa_a2, papel=PapelDocumento.PRESTADOR
        ),
        NaturezaOperacao.PRESTADO_ISS_RETIDO,
        usuario_gestor_a,
    )
    return devida, retida


def test_tomadas_nao_entram_em_nenhum_calculo_da_prestadora(
    escritorio_a, usuario_gestor_a, empresa_a2, prestadas
):
    antes = _capturas(empresa_a2)
    # A captura real: a receita das prestadas está lá. Sem isso, a igualdade seria vazia.
    assert antes["composicao"][0] == "ok"
    # Duas prestadas de 1.000,00 cada (a devida e a retida), no mercado interno.
    assert antes["composicao"][1].total("interno") == Decimal("2000.00")

    # Notas TOMADAS da mesma empresa, de todas as naturezas do catálogo, com federais e pagamento.
    t1 = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9410,
        T1,
        prestador_documento=CNPJ_PRESTADOR_PADRAO,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
        v_ret_csll="20.00",
        v_ret_irrf="15.00",
        v_ret_cp="11.00",
        tp_ret_pis_cofins="3",
    )
    servico.informar_data_pagamento(t1, date(2026, 10, 30), "Pagamento sintético", usuario_gestor_a)
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9411,
        T2,
        tp_ret_issqn="1",
        v_liq="1000.00",
        d_compet="2026-10-07",
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9412,
        T3,
        tp_ret_issqn="1",
        c_loc_incid="1721000",
        c_loc_prestacao="1100205",
        v_liq="1000.00",
        d_compet="2026-10-08",
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9413,
        T5,
        op_simp_nac="2",
        tp_ret_issqn="1",
        v_liq="1000.00",
        d_compet="2026-10-09",
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9414,
        T6,
        op_simp_nac="3",
        tp_ret_issqn="2",
        v_iss_qn="20.00",
        v_liq="980.00",
        v_ret_cp="11.00",
        c_loc_incid="1721000",
        d_compet="2026-10-10",
    )
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9415,
        T7,
        prestador_tipo="CPF",
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        tp_ret_issqn="1",
        federal=False,
        v_liq="1000.00",
        d_compet="2026-10-11",
    )
    # As tomadas estão mesmo gravadas: o teste não pode passar com o cenário vazio.
    assert EscrituracaoTomada.objects.filter(empresa=empresa_a2).count() == 6

    depois = _capturas(empresa_a2)

    assert depois == antes, {k: (antes[k], depois[k]) for k in antes if antes[k] != depois[k]}


def test_efetivar_tomada_em_mes_confirmado_nao_reabre_a_receita(
    escritorio_a, usuario_gestor_a, empresa_a2, prestadas
):
    # Mês CONFIRMADO: é aqui que a escrituração prestada reabriria a receita e a marcaria "a
    # retificar". A tomada não pode fazer isso.
    confirmar_mes(empresa_a2, ANO, MES, usuario_gestor_a)
    ids_antes = set(RegistroAuditoria.objects.values_list("id", flat=True))
    composicao_antes = composicao_do_mes(empresa_a2, ANO, MES)

    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9420,
        T1,
        prestador_documento=CNPJ_PRESTADOR_PADRAO,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
    )

    novas = list(
        RegistroAuditoria.objects.exclude(id__in=ids_antes)
        .order_by("id")
        .values_list("acao", flat=True)
    )
    # A recepção do XML grava o seu próprio registro (fiscal.envio_recebido). Descontada essa,
    # o único fato da escrituração é a efetivação da tomada. Nada de receita, nada de retificar.
    assert [acao for acao in novas if acao != "fiscal.envio_recebido"] == [
        "escrituracao_tomada.efetivada"
    ]
    assert composicao_do_mes(empresa_a2, ANO, MES) == composicao_antes


def test_tomada_nao_muda_as_escrituracoes_prestadas(
    escritorio_a, usuario_gestor_a, empresa_a2, prestadas
):
    prestadas_antes = list(
        EscrituracaoFiscal.objects.filter(empresa=empresa_a2).values_list(
            "pk", "natureza", "valor_servico"
        )
    )

    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9430,
        T2,
        prestador_documento=CNPJ_PRESTADOR_PADRAO,
        tp_ret_issqn="1",
        v_liq="1000.00",
        d_compet="2026-10-12",
    )

    prestadas_depois = list(
        EscrituracaoFiscal.objects.filter(empresa=empresa_a2).values_list(
            "pk", "natureza", "valor_servico"
        )
    )
    assert prestadas_depois == prestadas_antes
    # E a nota tomada não está na lista de notas a escriturar das prestadas.
    from apps.fiscal.escrituracao import notas_a_escriturar

    assert all(
        n.vinculo.papel == PapelDocumento.PRESTADOR
        for n in notas_a_escriturar(empresa_a2, ANO, MES)
    )
