"""DL-078, critério 2: natureza sugerida nos sinais do XML, confirmada pelo contador, recusas
nomeadas (tpEmit 2 e 3; T1, T2 e T3 contra o tpRetISSQN), efetivada imutável nas portas do
serviço e estorno com motivo. Trilha na mesma transação.

Dados sintéticos; valores e naturezas escritos à mão.
"""

from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import tomadas as servico
from apps.fiscal.escrituracao import EntradaInvalidaEscrituracao, EscrituracaoErro
from apps.fiscal.models import (
    EscrituracaoTomada,
    EstadoEscrituracao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T1,
    T2,
    T3,
    T5,
    T6,
    T7,
    cancelar,
    efetivar,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_TOMADOR_PADRAO

pytestmark = pytest.mark.django_db

CPF_SINTETICO = "52998224725"


def _trilha(acao):
    return list(RegistroAuditoria.objects.filter(acao=acao).order_by("id"))


@pytest.mark.parametrize(
    ("xml", "esperada"),
    [
        ({"tp_ret_issqn": "2"}, T1),
        ({"tp_ret_issqn": "1", "op_simp_nac": "2"}, T5),
        ({"tp_ret_issqn": "1", "op_simp_nac": "3"}, T6),
        (
            {
                "tp_ret_issqn": "1",
                "prestador_tipo": "CPF",
                "prestador_documento": CPF_SINTETICO,
                "federal": False,
            },
            T7,
        ),
        ({"tp_ret_issqn": "1", "c_loc_incid": "1721000", "c_loc_prestacao": "1100205"}, T3),
        ({"tp_ret_issqn": "1", "c_loc_incid": "1721000", "c_loc_prestacao": "1721000"}, T2),
        ({"tp_ret_issqn": "3"}, None),
    ],
    ids=[
        "retido_pelo_tomador",
        "mei",
        "simples",
        "pessoa_fisica",
        "outro_municipio",
        "sem_retencao",
        "intermediario",
    ],
)
def test_sugestao_segue_os_sinais_do_xml(escritorio_a, usuario_gestor_a, empresa_a2, xml, esperada):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6001, tomador_documento=empresa_a2.cnpj, **xml
    )

    assert servico.sugerir_natureza(documento) == esperada


@pytest.mark.parametrize("tp_emit", ["2", "3"])
def test_tpemit_2_ou_3_nao_tem_sugestao_e_e_recusado_no_rascunho_e_na_efetivacao(
    escritorio_a, usuario_gestor_a, empresa_a2, tp_emit
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6010, tomador_documento=empresa_a2.cnpj, tp_emit=tp_emit
    )
    vinculo = vinculo_tomador(documento, empresa_a2)

    assert servico.sugerir_natureza(documento) is None
    with pytest.raises(EntradaInvalidaEscrituracao, match="tpEmit 2 ou 3"):
        servico.salvar_rascunho(vinculo, T1, usuario_gestor_a)
    with pytest.raises(EntradaInvalidaEscrituracao, match="tpEmit 2 ou 3"):
        servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)
    assert EscrituracaoTomada.objects.count() == 0


def test_t1_sem_tpretissqn_2_e_recusada_e_nada_e_gravado(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6020, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="1"
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="exige tpRetISSQN 2"):
        servico.efetivar_escrituracao_tomada(
            vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a
        )
    assert EscrituracaoTomada.objects.count() == 0
    assert _trilha("escrituracao_tomada.efetivada") == []


def test_t2_com_tpretissqn_2_e_recusada_por_esconder_a_retencao(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6021, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="contradiz o XML"):
        servico.efetivar_escrituracao_tomada(
            vinculo_tomador(documento, empresa_a2), T2, usuario_gestor_a
        )
    assert EscrituracaoTomada.objects.count() == 0


def test_t3_exige_tpretissqn_1_e_recusa_intermediario(escritorio_a, usuario_gestor_a, empresa_a2):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6022, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="3"
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="exige tpRetISSQN 1"):
        servico.efetivar_escrituracao_tomada(
            vinculo_tomador(documento, empresa_a2), T3, usuario_gestor_a
        )


def test_rascunho_aceita_qualquer_natureza_e_so_a_efetivacao_confere_o_xml(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6030, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    vinculo = vinculo_tomador(documento, empresa_a2)

    rascunho = servico.salvar_rascunho(vinculo, T2, usuario_gestor_a)
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    rascunho = servico.salvar_rascunho(vinculo, T1, usuario_gestor_a)
    assert rascunho.natureza == T1
    assert EscrituracaoTomada.objects.count() == 1

    efetivada = servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.pk == rascunho.pk  # o rascunho vira efetivada; não nasce uma segunda linha


def test_efetivar_copia_os_valores_do_documento_e_do_xml_sem_inventar_ausente(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    escrituracao = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        6040,
        T1,
        tp_ret_issqn="2",
        v_serv="1000.00",
        v_liq="950.00",
        v_iss_qn="50.00",
        v_desc_incond="0.00",
        dh_emi="2026-10-05T23:30:00-03:00",
        d_compet="2026-10-05",
    )

    assert str(escrituracao.data_emissao) == "2026-10-05"
    assert str(escrituracao.data_competencia) == "2026-10-05"
    assert escrituracao.valor_servico == Decimal("1000.00")
    assert escrituracao.valor_liquido == Decimal("950.00")
    assert escrituracao.v_iss_qn == Decimal("50.00")
    assert escrituracao.tp_ret_issqn == "2"
    # Federais não destacados ficam NULOS, nunca zero.
    assert escrituracao.v_ret_cp is None
    assert escrituracao.v_ret_irrf is None
    assert escrituracao.v_ret_csll is None
    assert escrituracao.tp_ret_pis_cofins is None


def test_efetivada_com_outra_natureza_e_recusada_e_a_mesma_e_idempotente(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6050, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    primeira = servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)

    with pytest.raises(EscrituracaoErro, match="Estorne a escrituração"):
        servico.efetivar_escrituracao_tomada(vinculo, T6, usuario_gestor_a)

    repetida = servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)
    assert repetida.pk == primeira.pk
    assert repetida.criada_agora is False
    # A repetição não é fato novo: a trilha guarda uma única efetivação.
    assert len(_trilha("escrituracao_tomada.efetivada")) == 1


def test_estorno_exige_motivo_libera_a_nota_e_nao_apaga_a_linha(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    escrituracao = tomada_efetivada(
        escritorio_a, empresa_a2, usuario_gestor_a, 6060, T1, tp_ret_issqn="2"
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="Informe o motivo do estorno"):
        servico.estornar_escrituracao_tomada(escrituracao, "   ", usuario_gestor_a)
    estornada = servico.estornar_escrituracao_tomada(
        escrituracao, "Nota lançada no mês errado", usuario_gestor_a
    )

    assert estornada.estado == EstadoEscrituracao.ESTORNADA
    assert estornada.motivo_estorno == "Nota lançada no mês errado"
    assert EscrituracaoTomada.objects.filter(pk=escrituracao.pk).exists()
    assert len(_trilha("escrituracao_tomada.estornada")) == 1
    nota = servico.notas_tomadas(empresa_a2, 2026, 10)[0]
    assert nota.situacao == "a_escriturar"


def test_nota_cancelada_nao_e_efetivada(escritorio_a, usuario_gestor_a, empresa_a2):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 6070, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    cancelar(escritorio_a, usuario_gestor_a, documento, sufixo_evento=1)

    with pytest.raises(EscrituracaoErro, match="cancelada"):
        efetivar(documento, empresa_a2, T1, usuario_gestor_a)
    assert EscrituracaoTomada.objects.count() == 0


def test_nota_em_que_a_empresa_e_prestadora_nao_entra_na_escrituracao_de_tomadas(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        6080,
        prestador_documento=CNPJ_TOMADOR_PADRAO,
        tomador_documento="77888999000155",
        tp_ret_issqn="2",
    )
    vinculo_prestado = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa_a2, papel=PapelDocumento.PRESTADOR
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="Só é escriturada aqui"):
        servico.efetivar_escrituracao_tomada(vinculo_prestado, T1, usuario_gestor_a)
    assert servico.notas_tomadas(empresa_a2, 2026, 10) == []


def test_depois_de_estornada_a_nota_pode_ser_efetivada_em_outra_linha(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    escrituracao = tomada_efetivada(
        escritorio_a, empresa_a2, usuario_gestor_a, 6090, T1, tp_ret_issqn="2"
    )
    servico.estornar_escrituracao_tomada(escrituracao, "Correção", usuario_gestor_a)
    vinculo = escrituracao.vinculo

    nova = servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)

    assert nova.pk != escrituracao.pk  # estorno é histórico; a nova efetivação é outra linha
    assert nova.criada_agora is True
    assert EscrituracaoTomada.objects.filter(vinculo=vinculo).count() == 2
