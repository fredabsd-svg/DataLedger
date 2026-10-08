"""DL-078, critérios 3 e 4: ISS retido a recolher pelo tomador, e o vencimento de Palmas.

Cenário sintético em 10/2026, empresa tomadora de Palmas. Os valores esperados são escritos à mão.
Entram: efetivadas, de natureza T1, com `dCompet` em 10/2026. Ficam de fora: rascunho, estornada,
cancelada, competência de outro mês e nota prestada. A nota T1 sem `vISSQN` aparece em "sem valor
destacado", nunca como zero. vLiq de cada nota é o da fórmula (vServ − vISSQN), para não disparar
o aviso A1 por inconsistência de dado de teste.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import escrituracao as escrituracao_prestada
from apps.fiscal import tomadas as servico
from apps.fiscal.models import (
    EscrituracaoTomada,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.retencoes import iss_retido_a_recolher
from apps.fiscal.tests.suporte_tomada_dl078 import (
    OUTRO_MUNICIPIO,
    PALMAS,
    T1,
    T3,
    T6,
    cancelar,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_TOMADOR_PADRAO

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa_a2):
    """Competência 10/2026 da tomadora. Devolve as escriturações pelo nome do caso."""
    escritorio, usuario, empresa = escritorio_a, usuario_gestor_a, empresa_a2
    c = {}
    c["n1"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9001,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-05",
    )
    c["n2"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9002,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="30.25",
        v_liq="969.75",
        c_loc_incid=PALMAS,
        d_compet="2026-10-20",
    )
    # Retida (T1) sem vISSQN destacado: entra em "sem valor", nunca como zero.
    c["n3_sem_valor"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9003,
        T1,
        tp_ret_issqn="2",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-21",
    )
    # Efetivada e depois estornada: fora.
    c["n5_estornada"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9005,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="77.00",
        v_liq="923.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-23",
    )
    servico.estornar_escrituracao_tomada(c["n5_estornada"], "Lançada em duplicidade", usuario)
    # Efetivada e depois cancelada pelo evento da NFS-e: fora do total, à parte.
    c["n6_cancelada"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9006,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="88.00",
        v_liq="912.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-24",
    )
    cancelar(escritorio, usuario, c["n6_cancelada"].vinculo.documento, sufixo_evento=1)
    # Outro mês de competência: fora de 10/2026.
    c["n7_novembro"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9007,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="40.00",
        v_liq="960.00",
        c_loc_incid=PALMAS,
        d_compet="2026-11-03",
    )
    # Município sem regra cadastrada: grupo próprio, vencimento "não parametrizado".
    c["n8_sem_regra"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9008,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid=OUTRO_MUNICIPIO,
        d_compet="2026-10-06",
    )
    # Tomado do Simples (T6) com retenção pelo tomador: NÃO é T1, fica fora do total, com aviso.
    c["n9_simples_retido"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9009,
        T6,
        tp_ret_issqn="2",
        v_iss_qn="7.00",
        v_liq="993.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-07",
        op_simp_nac="3",
    )
    # Prestador de outro município (T3), tpRetISSQN 1, cLocIncid em Palmas: aviso CNES/RANFS.
    c["n10_outro_municipio"] = tomada_efetivada(
        escritorio,
        empresa,
        usuario,
        9010,
        T3,
        tp_ret_issqn="1",
        c_loc_incid=PALMAS,
        c_loc_prestacao=OUTRO_MUNICIPIO,
        d_compet="2026-10-08",
        v_liq="1000.00",
    )
    # Rascunho com vISSQN destacado: não entra no total.
    rascunho_doc = receber_tomada(
        escritorio,
        usuario,
        9004,
        tomador_documento=empresa.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="99.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-22",
        v_liq="901.00",
    )
    servico.salvar_rascunho(vinculo_tomador(rascunho_doc, empresa), T1, usuario)
    # Nota PRESTADA com ISS retido: a empresa é a PRESTADORA. Não é tomada.
    prestada_doc = receber_tomada(
        escritorio,
        usuario,
        9020,
        prestador_documento=CNPJ_TOMADOR_PADRAO,
        tomador_documento="77888999000155",
        tp_ret_issqn="2",
        v_iss_qn="500.00",
        v_liq="500.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-09",
    )
    escrituracao_prestada.efetivar_escrituracao(
        VinculoDocumentoEmpresa.objects.get(
            documento=prestada_doc, empresa=empresa, papel=PapelDocumento.PRESTADOR
        ),
        NaturezaOperacao.PRESTADO_ISS_RETIDO,
        usuario,
    )
    return c


def _grupo(resultado, municipio):
    return next(g for g in resultado.grupos if g.municipio == municipio)


def test_iss_retido_soma_so_as_efetivadas_t1_da_competencia_por_municipio(cenario, empresa_a2):
    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    # 50,00 + 30,25 = 80,25. Fora: rascunho (99,00), estornada (77,00), cancelada (88,00),
    # novembro (40,00), prestada (500,00) e T6 (7,00, fora do total).
    assert palmas.total == Decimal("80.25")
    assert [n.pk for n in palmas.notas] == [cenario["n1"].pk, cenario["n2"].pk]


def test_nota_retida_sem_vissqn_fica_para_conferir_e_nao_vira_zero(cenario, empresa_a2):
    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    assert [n.pk for n in palmas.sem_valor] == [cenario["n3_sem_valor"].pk]
    assert palmas.total == Decimal("80.25")  # a nota sem valor não somou zero nem mudou o total


def test_grupo_so_com_nota_sem_valor_tem_total_none_e_nao_zero(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9101,
        T1,
        tp_ret_issqn="2",
        c_loc_incid=PALMAS,
        d_compet="2026-10-05",
        v_liq="1000.00",
    )

    grupo = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    assert grupo.total is None
    assert len(grupo.sem_valor) == 1


def test_vencimento_de_palmas_competencia_10_2026_cai_em_15_11_2026_no_domingo(cenario, empresa_a2):
    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    # Regra cadastrada (migração da DL-076): dia do retido = 15, do mês seguinte.
    assert palmas.vencimento == date(2026, 11, 15)
    # 15/11/2026 é domingo: o texto mostra o dia da semana (HI-90, item 4).
    assert palmas.vencimento_texto == "15/11/2026 (domingo)"
    assert "primeiro dia útil seguinte" in palmas.regra_dia_nao_util


def test_municipio_sem_regra_fica_nao_parametrizado_sem_data(cenario, empresa_a2):
    grupo = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), OUTRO_MUNICIPIO)

    assert grupo.total == Decimal("10.00")
    assert grupo.vencimento is None
    assert "não parametrizado" in grupo.vencimento_texto


def test_retida_pelo_simples_fora_da_natureza_t1_fica_fora_do_total(cenario, empresa_a2):
    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert [n.pk for n in resultado.fora_do_total] == [cenario["n9_simples_retido"].pk]
    # Os 7,00 não entram em nenhum grupo: nem como grupo próprio, nem dentro de Palmas.
    assert all(
        cenario["n9_simples_retido"].pk not in [n.pk for n in g.notas] for g in resultado.grupos
    )


def test_prestador_de_outro_municipio_com_iss_no_tomador_em_palmas_pede_cnes_ranfs(
    cenario, empresa_a2
):
    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    cnes = [e for e, aviso in resultado.avisos if aviso.codigo == "CNES_RANFS"]
    assert [e.pk for e in cnes] == [cenario["n10_outro_municipio"].pk]
    # Informativo, sem valor: a nota T3 não entra no total de ISS a recolher.
    assert all(
        cenario["n10_outro_municipio"].pk not in [n.pk for n in g.notas] for g in resultado.grupos
    )


def test_nota_sem_municipio_de_incidencia_nao_tem_vencimento(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9102,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="12.00",
        v_liq="988.00",
        c_loc_incid=None,
        d_compet="2026-10-05",
    )

    grupo = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), None)

    assert grupo.total == Decimal("12.00")
    assert grupo.vencimento is None
    assert "sem município" in grupo.vencimento_texto.lower()


def test_rascunho_com_valores_copiados_nao_entra_no_total_pela_regra_de_estado(
    cenario, empresa_a2, escritorio_a, usuario_gestor_a
):
    # Um rascunho SERVIÇO nunca copia data nem valor: por isso os filtros de data já o excluiriam
    # sozinhos. Aqui o rascunho tem os valores copiados (o banco aceita, porque a restrição de
    # rascunho não proíbe essas colunas), e só a regra de ESTADO pode excluí-lo.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9050,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="99.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-22",
        v_liq="901.00",
    )
    EscrituracaoTomada.objects.bulk_create(
        [
            EscrituracaoTomada(
                vinculo=vinculo_tomador(documento, empresa_a2),
                empresa=empresa_a2,
                natureza=T1,
                estado=EstadoEscrituracao.RASCUNHO,
                data_emissao=date(2026, 10, 22),
                data_competencia=date(2026, 10, 22),
                tp_ret_issqn="2",
                c_loc_incid=PALMAS,
                valor_servico=Decimal("1000.00"),
                valor_liquido=Decimal("901.00"),
                v_iss_qn=Decimal("99.00"),
                tp_emit="1",
                criado_por=usuario_gestor_a,
            )
        ]
    )

    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    assert palmas.total == Decimal("80.25")  # sem os 99,00 do rascunho


def test_iss_retido_de_outra_empresa_nao_aparece_nesta_empresa(cenario, empresa_a):
    # empresa_a só é prestadora ou não aparece nas notas do cenário: nada é tomado por ela.
    resultado = iss_retido_a_recolher(empresa_a, 2026, 10)

    assert resultado.grupos == ()
    assert resultado.fora_do_total == ()
