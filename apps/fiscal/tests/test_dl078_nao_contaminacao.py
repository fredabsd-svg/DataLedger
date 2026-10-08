"""DL-078, critério 7: nenhuma tomada entra em receita, RBT12, pré-DAS, apuração do ISS próprio,
nem nos relatórios de ISS retido sofrido e de outros municípios.

Método: captura os resultados dos seis cálculos da empresa ANTES e DEPOIS de efetivar tomadas de
todas as naturezas (T1, T2, T3, T5, T6, T7), com retenções federais e data de pagamento. Os dois
conjuntos têm de ser iguais.

Uma captura "recusada" não prova nada: duas recusas iguais são igualdade vazia. Por isso CADA teste
afirma, ANTES de comparar, que os cálculos que o seu cenário cobre devolvem resultado ("ok"). O
cenário do Simples cobre composição, RBT12, pré-DAS, ISS retido sofrido e outros municípios; o de
regime por alíquota cobre a apuração do ISS próprio. (Auditoria da DL-078, rodada 1, achado A4.)
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as escrituracao_prestada
from apps.fiscal import receita as servico_receita
from apps.fiscal import tomadas as servico
from apps.fiscal.escrituracao import notas_a_escriturar
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
from apps.fiscal.tests.suporte_iss_dl076 import DEVIDO, RETIDO, cenario_outubro, receber
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
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    enquadramento_iii_ou_v,
    folha_confirmada,
    folhas_dos_12_meses,
    janela_de_receitas,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]

ANO, MES = 2026, 10
D = Decimal

# Cálculos que cada cenário cobre. Os nomes são as chaves de `_capturas`.
CALCULOS_DO_SIMPLES = ("composicao", "rbt12", "pre_das", "retido_sofrido", "outros_municipios")
CALCULOS_DO_REGIME_POR_ALIQUOTA = (
    "composicao",
    "apuracao_iss_proprio",
    "retido_sofrido",
    "outros_municipios",
)

# CNPJ sintético de prestador de FORA da empresa de teste (nunca a própria empresa).
PRESTADOR_DE_FORA = "55666777000188"


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


def _afirmar_que_executam(capturas, nomes):
    """Os cálculos de `nomes` devolveram resultado. Só então a comparação antes/depois conta."""
    recusados = {nome: capturas[nome] for nome in nomes if capturas[nome][0] != "ok"}
    assert not recusados, f"cálculo recusado: a igualdade seria vazia: {recusados}"


def _tomadas_de_todas_as_naturezas(escritorio, usuario, empresa):
    """Tomadas da MESMA empresa, de todas as naturezas do catálogo, com valores altos, retenções
    federais e data de pagamento. Nenhuma tem a empresa como prestadora."""
    t1 = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9410,
        T1,
        prestador_documento=PRESTADOR_DE_FORA,
        tp_ret_issqn="2",
        v_serv="99999.00",
        v_iss_qn="4999.95",
        v_liq="94999.05",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
        v_ret_csll="1.00",
        v_ret_irrf="1.00",
        v_ret_cp="1.00",
        tp_ret_pis_cofins="3",
    )
    servico.informar_data_pagamento(t1, date(2026, 10, 30), "Pagamento sintético", usuario)
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9411,
        T2,
        prestador_documento=PRESTADOR_DE_FORA,
        tp_ret_issqn="1",
        v_serv="88888.00",
        v_liq="88888.00",
        d_compet="2026-10-07",
        v_iss_qn="10.00",
    )
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9412,
        T3,
        prestador_documento=PRESTADOR_DE_FORA,
        tp_ret_issqn="1",
        c_loc_incid="1721000",
        c_loc_prestacao="1100205",
        v_serv="77777.00",
        v_liq="77777.00",
        d_compet="2026-10-08",
    )
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9413,
        T5,
        prestador_documento=PRESTADOR_DE_FORA,
        op_simp_nac="2",
        tp_ret_issqn="2",
        v_iss_qn="5.00",
        v_serv="66666.00",
        v_liq="66661.00",
        c_loc_incid="1100205",
        d_compet="2026-10-09",
        federal=False,
    )
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9414,
        T6,
        prestador_documento=PRESTADOR_DE_FORA,
        op_simp_nac="3",
        tp_ret_issqn="2",
        v_iss_qn="6.00",
        v_serv="55555.00",
        v_liq="55549.00",
        c_loc_incid="1721000",
        d_compet="2026-10-10",
    )
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9415,
        T7,
        prestador_tipo="CPF",
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        tp_ret_issqn="2",
        v_iss_qn="7.00",
        v_serv="44444.00",
        v_liq="44437.00",
        c_loc_incid="1721000",
        d_compet="2026-10-11",
        federal=False,
    )
    # Tomada em mês da janela do RBT12 (maio/2026): é ela que mexeria no RBT12, se entrasse.
    tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9416,
        T2,
        prestador_documento=PRESTADOR_DE_FORA,
        tp_ret_issqn="1",
        v_serv="33333.00",
        v_liq="33333.00",
        d_compet="2026-05-11",
        dh_emi="2026-05-11T10:00:00-03:00",
    )


def _cenario_simples(escritorio, usuario, empresa):
    """Empresa no Simples com atividade padrão, janela de receitas e folhas, prestadas devida e
    retida, e o mês 10/2026 confirmado. Com isso, RBT12 e pré-DAS têm o que calcular."""
    cenario_simples(empresa)
    atividade_padrao(empresa, usuario, enquadramento_iii_ou_v())
    janela_de_receitas(empresa, usuario, ANO, MES, [D("10000")] * 12)
    folhas_dos_12_meses(empresa, usuario, ANO, MES, [D("3000")] * 12)
    receber(
        escritorio, usuario, 1001, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00"
    )
    receber(escritorio, usuario, 2001, RETIDO, tp_ret_issqn="2", v_iss_qn="30.00")
    folha_confirmada(empresa, usuario, ANO, MES, remuneracao=D("3000"))
    servico_receita.confirmar_mes(empresa, ANO, MES, usuario)


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
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Cenário do Simples: composição, RBT12, pré-DAS, ISS retido sofrido e outros municípios
    EXECUTAM antes e depois das tomadas, e são iguais."""
    _cenario_simples(escritorio_a, usuario_gestor_a, empresa_a)
    antes = _capturas(empresa_a)
    _afirmar_que_executam(antes, CALCULOS_DO_SIMPLES)
    # A receita das prestadas está lá: duas notas de 1.000,00 (a devida e a retida). Sem isso, a
    # igualdade abaixo seria vazia, mesmo com todos os cálculos executando.
    assert antes["composicao"][1].total("interno") == D("2000.00")

    _tomadas_de_todas_as_naturezas(escritorio_a, usuario_gestor_a, empresa_a)
    # As tomadas estão mesmo gravadas: o teste não pode passar com o cenário vazio.
    assert EscrituracaoTomada.objects.filter(empresa=empresa_a).count() == 7

    depois = _capturas(empresa_a)
    _afirmar_que_executam(depois, CALCULOS_DO_SIMPLES)
    assert depois == antes, {k: (antes[k], depois[k]) for k in antes if antes[k] != depois[k]}


def test_tomadas_nao_entram_na_apuracao_do_iss_proprio(escritorio_a, usuario_gestor_a, empresa_a):
    """Regime por alíquota: a apuração do ISS próprio EXECUTA antes e depois, e é igual."""
    cenario_outubro(escritorio_a, usuario_gestor_a, empresa_a)
    antes = _capturas(empresa_a)
    _afirmar_que_executam(antes, CALCULOS_DO_REGIME_POR_ALIQUOTA)

    _tomadas_de_todas_as_naturezas(escritorio_a, usuario_gestor_a, empresa_a)
    assert EscrituracaoTomada.objects.filter(empresa=empresa_a).count() == 7

    depois = _capturas(empresa_a)
    _afirmar_que_executam(depois, CALCULOS_DO_REGIME_POR_ALIQUOTA)
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
    assert all(
        n.vinculo.papel == PapelDocumento.PRESTADOR
        for n in notas_a_escriturar(empresa_a2, ANO, MES)
    )
