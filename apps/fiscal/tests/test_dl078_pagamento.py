"""DL-078, critério 2 e HI-96: a data de pagamento informada pelo contador.

Regras testadas: só nota efetivada recebe data; motivo obrigatório em toda informação ou correção;
quem e quando informou ficam no registro e na trilha; repetir a mesma data não é fato novo; estorno
não apaga a data; a alteração não mexe no resto do ato.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import tomadas as servico
from apps.fiscal.escrituracao import EntradaInvalidaEscrituracao, EscrituracaoErro
from apps.fiscal.models import EstadoEscrituracao
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T1,
    tomada_efetivada,
    vinculo_tomador,
)

pytestmark = pytest.mark.django_db


def _trilha(acao):
    return list(RegistroAuditoria.objects.filter(acao=acao).order_by("id"))


@pytest.fixture
def efetivada(escritorio_a, usuario_gestor_a, empresa_a2):
    return tomada_efetivada(
        escritorio_a, empresa_a2, usuario_gestor_a, 8001, T1, tp_ret_issqn="2", v_iss_qn="50.00"
    )


def test_informa_a_data_com_quem_quando_e_motivo_e_registra_a_trilha(efetivada, usuario_gestor_a):
    informada = servico.informar_data_pagamento(
        efetivada, date(2026, 10, 30), "Comprovante de pagamento sintético", usuario_gestor_a
    )

    assert informada.data_pagamento == date(2026, 10, 30)
    assert informada.pagamento_informado_por_id == usuario_gestor_a.pk
    assert informada.pagamento_informado_em is not None
    assert informada.motivo_pagamento == "Comprovante de pagamento sintético"
    assert informada.criada_agora is True
    trilha = _trilha("escrituracao_tomada.data_pagamento_informada")
    assert len(trilha) == 1
    assert trilha[0].detalhes["antes"]["data_pagamento"] is None
    assert trilha[0].detalhes["depois"]["data_pagamento"] == "2026-10-30"


def test_data_so_e_informada_em_nota_efetivada(escritorio_a, usuario_gestor_a, empresa_a2):
    from apps.fiscal.tests.suporte_tomada_dl078 import receber_tomada as receber

    documento = receber(
        escritorio_a, usuario_gestor_a, 8002, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    rascunho = servico.salvar_rascunho(vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a)

    with pytest.raises(EscrituracaoErro, match="só é informada em escrituração efetivada"):
        servico.informar_data_pagamento(rascunho, date(2026, 10, 30), "x", usuario_gestor_a)


def test_motivo_e_obrigatorio_e_tem_limite(efetivada, usuario_gestor_a):
    with pytest.raises(EntradaInvalidaEscrituracao, match="Informe o motivo da data de pagamento"):
        servico.informar_data_pagamento(efetivada, date(2026, 10, 30), "  ", usuario_gestor_a)
    with pytest.raises(EntradaInvalidaEscrituracao, match="no máximo 500"):
        servico.informar_data_pagamento(efetivada, date(2026, 10, 30), "x" * 501, usuario_gestor_a)
    efetivada.refresh_from_db()
    assert efetivada.data_pagamento is None


@pytest.mark.parametrize("valor", ["2026-10-30", datetime(2026, 10, 30, 12, 0)])
def test_data_tem_de_ser_dia_e_nao_texto_nem_instante(efetivada, usuario_gestor_a, valor):
    # Um instante com hora não é o dia de pagamento que a retenção agrupa.
    with pytest.raises(EntradaInvalidaEscrituracao, match="formato AAAA-MM-DD"):
        servico.informar_data_pagamento(efetivada, valor, "motivo", usuario_gestor_a)


def test_correcao_de_data_cria_nova_trilha_e_nao_mexe_no_resto_do_ato(efetivada, usuario_gestor_a):
    servico.informar_data_pagamento(
        efetivada, date(2026, 10, 30), "Primeira informação", usuario_gestor_a
    )

    corrigida = servico.informar_data_pagamento(
        efetivada, date(2026, 11, 2), "Pagamento caiu no dia seguinte", usuario_gestor_a
    )

    assert corrigida.data_pagamento == date(2026, 11, 2)
    assert corrigida.motivo_pagamento == "Pagamento caiu no dia seguinte"
    assert len(_trilha("escrituracao_tomada.data_pagamento_informada")) == 2
    # O ato que a data acompanha continua igual.
    assert corrigida.estado == EstadoEscrituracao.EFETIVADA
    assert corrigida.natureza == T1
    assert corrigida.valor_servico == Decimal("1000.00")
    assert corrigida.v_iss_qn == Decimal("50.00")


def test_repetir_a_mesma_data_e_no_op_sem_nova_trilha(efetivada, usuario_gestor_a):
    servico.informar_data_pagamento(
        efetivada, date(2026, 10, 30), "Primeira informação", usuario_gestor_a
    )

    repetida = servico.informar_data_pagamento(
        efetivada, date(2026, 10, 30), "Outro texto", usuario_gestor_a
    )

    assert repetida.criada_agora is False
    assert repetida.motivo_pagamento == "Primeira informação"
    assert len(_trilha("escrituracao_tomada.data_pagamento_informada")) == 1


def test_nota_estornada_nao_recebe_data_de_pagamento(efetivada, usuario_gestor_a):
    servico.estornar_escrituracao_tomada(efetivada, "Lançada em duplicidade", usuario_gestor_a)

    with pytest.raises(EscrituracaoErro, match="só é informada em escrituração efetivada"):
        servico.informar_data_pagamento(efetivada, date(2026, 10, 30), "x", usuario_gestor_a)


def test_estorno_nao_apaga_a_data_de_pagamento_ja_informada(efetivada, usuario_gestor_a):
    servico.informar_data_pagamento(efetivada, date(2026, 10, 30), "Comprovante", usuario_gestor_a)

    estornada = servico.estornar_escrituracao_tomada(efetivada, "Correção do ato", usuario_gestor_a)

    assert estornada.estado == EstadoEscrituracao.ESTORNADA
    assert estornada.data_pagamento == date(2026, 10, 30)
