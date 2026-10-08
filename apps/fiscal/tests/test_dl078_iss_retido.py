"""DL-078, critérios 3 e 4: ISS retido a recolher pelo tomador, e o vencimento de Palmas.

Cenário sintético em 10/2026, empresa tomadora de Palmas. Os valores esperados são escritos à mão.
Entram: efetivadas com tpRetISSQN 2, de QUALQUER natureza de NATUREZAS_COM_ISS_RETIDO (T1, T5, T6
e T7), com `dCompet` em 10/2026 (item 0 da DL-078 frente B). Ficam de fora: rascunho, estornada,
cancelada, competência de outro mês e nota prestada. A nota retida sem `vISSQN` aparece em "sem
valor destacado", nunca como zero. vLiq de cada nota é o da fórmula (vServ − vISSQN), para não
disparar o aviso A1 por inconsistência de dado de teste.
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
    T5,
    T6,
    T7,
    cancelar,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_TOMADOR_PADRAO
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO

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
    # Tomado do Simples (T6) com retenção pelo tomador: entra no total (item 0), sem aviso de MEI.
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


def test_iss_retido_soma_as_efetivadas_com_retencao_da_competencia_por_municipio(
    cenario, empresa_a2
):
    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    # 50,00 (T1) + 30,25 (T1) + 7,00 (T6, item 0) = 87,25. Fora: rascunho (99,00), estornada
    # (77,00), cancelada (88,00), novembro (40,00) e prestada (500,00).
    assert palmas.total == Decimal("87.25")
    assert {n.pk for n in palmas.notas} == {
        cenario["n1"].pk,
        cenario["n2"].pk,
        cenario["n9_simples_retido"].pk,
    }


def test_nota_retida_sem_vissqn_fica_para_conferir_e_nao_vira_zero(cenario, empresa_a2):
    palmas = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    assert [n.pk for n in palmas.sem_valor] == [cenario["n3_sem_valor"].pk]
    # A nota sem valor não somou zero nem mudou o total.
    assert palmas.total == Decimal("87.25")


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


def test_retida_pelo_simples_entra_no_total_do_iss_retido(cenario, empresa_a2):
    # Item 0 (HI-94): a retenção não depende do tipo do prestador. T6 com tpRetISSQN 2 soma.
    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert resultado.fora_do_total == ()
    palmas = _grupo(resultado, PALMAS)
    assert cenario["n9_simples_retido"].pk in [n.pk for n in palmas.notas]
    assert palmas.total == Decimal("87.25")


def test_tomado_de_mei_com_retencao_entra_no_total_e_recebe_aviso(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    # MEI com tpRetISSQN 2: some (item 0) e sai o aviso "conferir", sem alterar valor.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9201,
        T5,
        tp_ret_issqn="2",
        v_iss_qn="20.00",
        v_liq="980.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-12",
        op_simp_nac="2",
    )

    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert _grupo(resultado, PALMAS).total == Decimal("20.00")
    avisos_mei = [aviso for _, aviso in resultado.avisos if aviso.codigo == "MEI_ISS_RETIDO"]
    assert len(avisos_mei) == 1
    assert avisos_mei[0].texto.startswith("MEI não sofre retenção de ISS em regra — conferir.")
    assert "LC 123, art. 18-A" in avisos_mei[0].fundamento
    assert "inferência" in avisos_mei[0].fundamento


def test_tomado_de_mei_retido_sem_vissqn_fica_para_conferir_sem_zero(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9202,
        T5,
        tp_ret_issqn="2",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-13",
        op_simp_nac="2",
    )

    grupo = _grupo(iss_retido_a_recolher(empresa_a2, 2026, 10), PALMAS)

    assert grupo.total is None
    assert len(grupo.sem_valor) == 1


def test_aviso_de_mei_nao_aparece_para_retencao_de_simples(cenario, empresa_a2):
    # Nenhuma nota do cenário é T5, e o Simples retido (T6) não recebe o aviso de MEI.
    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert not [aviso for _, aviso in resultado.avisos if aviso.codigo == "MEI_ISS_RETIDO"]


def test_tomado_de_pessoa_fisica_com_retencao_entra_no_total(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    # Prestador CPF sintético: a natureza T7 vem da sugestão do XML, não de escolha livre.
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9203,
        T7,
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        prestador_tipo="CPF",
        tp_ret_issqn="2",
        v_iss_qn="15.00",
        v_liq="985.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-14",
    )

    resultado = iss_retido_a_recolher(empresa_a2, 2026, 10)

    assert _grupo(resultado, PALMAS).total == Decimal("15.00")
    assert not [aviso for _, aviso in resultado.avisos if aviso.codigo == "MEI_ISS_RETIDO"]


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

    assert palmas.total == Decimal("87.25")  # sem os 99,00 do rascunho


def test_iss_retido_de_outra_empresa_nao_aparece_nesta_empresa(cenario, empresa_a):
    # empresa_a só é prestadora ou não aparece nas notas do cenário: nada é tomado por ela.
    resultado = iss_retido_a_recolher(empresa_a, 2026, 10)

    assert resultado.grupos == ()
    assert resultado.fora_do_total == ()
