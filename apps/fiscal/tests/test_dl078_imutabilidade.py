"""DL-078, critério 2 (imutabilidade em todas as portas) e mutante (f).

Três camadas, como a DL-072: `save()`/`delete()` do modelo; `QuerySet.update()`, `bulk_create()`
e `delete()`, que passam por cima do `save()`; e o banco (gatilhos e restrições). A recusa do banco
é verificada pelo NOME da restrição violada (`diag.constraint_name`), não só pela classe de erro.

O mutante (f) é este: se o gatilho deixar alterar qualquer coluna além da data de pagamento, o
teste que altera `natureza` junto com a data de pagamento precisa falhar.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fiscal import tomadas as servico
from apps.fiscal.models import (
    EscrituracaoImutavel,
    EscrituracaoTomada,
    EstadoEscrituracao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T1,
    T5,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)

pytestmark = pytest.mark.django_db

RESTRICAO_IMUTAVEL = "escrituracao_tomada_imutavel_depois_de_efetivada"
RESTRICAO_BATE = "escrituracao_tomada_efetivada_bate_com_o_documento"
RESTRICAO_VINCULO = "escrituracao_tomada_vinculo_tomador_da_empresa"
RESTRICAO_UNICA = "escrituracao_tomada_ativa_unica_por_vinculo"
RESTRICAO_PAGAMENTO = "escrituracao_tomada_pagamento_com_informante"


def _nome_da_restricao(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def _recusa_do_banco(restricao: str, operacao):
    """Executa `operacao` e exige que o banco recuse com a restrição indicada."""
    with pytest.raises(IntegrityError) as excinfo:
        with transaction.atomic():
            operacao()
    assert _nome_da_restricao(excinfo.value) == restricao


@pytest.fixture
def efetivada(escritorio_a, usuario_gestor_a, empresa_a2):
    return tomada_efetivada(
        escritorio_a, empresa_a2, usuario_gestor_a, 7001, T1, tp_ret_issqn="2", v_iss_qn="50.00"
    )


# ---------------------------------------------------------------------------
# Camada 1: save() e delete() do modelo
# ---------------------------------------------------------------------------


def test_save_de_efetivada_e_recusado_e_nada_muda(efetivada):
    efetivada.natureza = T5
    with pytest.raises(EscrituracaoImutavel):
        efetivada.save()
    assert EscrituracaoTomada.objects.get(pk=efetivada.pk).natureza == T1


def test_delete_de_efetivada_e_recusado(efetivada):
    with pytest.raises(EscrituracaoImutavel):
        efetivada.delete()
    assert EscrituracaoTomada.objects.filter(pk=efetivada.pk).exists()


def test_delete_de_rascunho_e_permitido(escritorio_a, usuario_gestor_a, empresa_a2):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 7002, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    rascunho = servico.salvar_rascunho(vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a)

    rascunho.delete()

    assert not EscrituracaoTomada.objects.filter(pk=rascunho.pk).exists()


def test_modelo_recusa_vinculo_de_prestador(escritorio_a, usuario_gestor_a, empresa_a2):
    # A empresa é PRESTADORA desta nota: o vínculo que existe é de prestador, e o modelo recusa.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        7003,
        prestador_documento=empresa_a2.cnpj,
        tomador_documento="77888999000155",
        tp_ret_issqn="2",
    )
    prestado = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa_a2, papel=PapelDocumento.PRESTADOR
    )
    escrituracao = EscrituracaoTomada(
        vinculo=prestado,
        empresa=empresa_a2,
        natureza=T1,
        criado_por=usuario_gestor_a,
    )

    with pytest.raises(ValidationError, match="tomadora"):
        escrituracao.save()
    assert EscrituracaoTomada.objects.count() == 0


# ---------------------------------------------------------------------------
# Camada 2: QuerySet.update() e bulk_create(), que contornam o save()
# ---------------------------------------------------------------------------


def test_update_de_natureza_em_efetivada_e_recusado_pelo_banco(efetivada):
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(natureza=T5),
    )


def test_update_de_valor_em_efetivada_e_recusado_pelo_banco(efetivada):
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
            valor_servico=Decimal("999.99")
        ),
    )


def test_update_de_iss_em_efetivada_e_recusado_pelo_banco(efetivada):
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(v_iss_qn=Decimal("1.00")),
    )


def test_efetivada_nao_volta_a_rascunho_pelo_banco(efetivada):
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
            estado=EstadoEscrituracao.RASCUNHO, efetivada_em=None, efetivada_por=None
        ),
    )


def test_data_de_pagamento_junto_com_outra_coluna_e_recusada_pelo_banco(
    efetivada, usuario_gestor_a
):
    # Mutante (f): se o gatilho deixasse mudar qualquer coluna além da data de pagamento, este
    # teste deixa de recusar, porque a natureza foi trocada junto com a data.
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
            natureza=T5,
            data_pagamento=date(2026, 10, 30),
            pagamento_informado_em=timezone.now(),
            pagamento_informado_por=usuario_gestor_a,
            motivo_pagamento="Teste de mutante",
        ),
    )


def test_so_as_colunas_de_pagamento_mudam_em_efetivada_pelo_banco(efetivada, usuario_gestor_a):
    atualizadas = EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
        data_pagamento=date(2026, 10, 30),
        pagamento_informado_em=timezone.now(),
        pagamento_informado_por=usuario_gestor_a,
        motivo_pagamento="Comprovante sintético",
    )

    assert atualizadas == 1
    alterada = EscrituracaoTomada.objects.get(pk=efetivada.pk)
    assert alterada.data_pagamento == date(2026, 10, 30)
    assert alterada.natureza == T1
    assert alterada.v_iss_qn == Decimal("50.00")


def test_data_de_pagamento_no_rascunho_e_recusada_pelo_banco(
    escritorio_a, usuario_gestor_a, empresa_a2, efetivada
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 7004, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    rascunho = servico.salvar_rascunho(vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=rascunho.pk).update(
            data_pagamento=date(2026, 10, 30),
            pagamento_informado_em=timezone.now(),
            pagamento_informado_por=usuario_gestor_a,
            motivo_pagamento="x",
        ),
    )


def test_data_de_pagamento_sem_quem_informou_e_recusada_pela_checagem(efetivada):
    _recusa_do_banco(
        RESTRICAO_PAGAMENTO,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
            data_pagamento=date(2026, 10, 30)
        ),
    )


def test_estorno_pelo_banco_so_muda_as_colunas_do_estorno(efetivada, usuario_gestor_a):
    atualizadas = EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
        estado=EstadoEscrituracao.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario_gestor_a,
        motivo_estorno="Estorno sintético",
    )

    assert atualizadas == 1
    assert EscrituracaoTomada.objects.get(pk=efetivada.pk).estado == EstadoEscrituracao.ESTORNADA


def test_estornada_nao_recebe_data_de_pagamento_pelo_banco(efetivada, usuario_gestor_a):
    EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
        estado=EstadoEscrituracao.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario_gestor_a,
        motivo_estorno="Estorno sintético",
    )

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoTomada.objects.filter(pk=efetivada.pk).update(
            data_pagamento=date(2026, 10, 30),
            pagamento_informado_em=timezone.now(),
            pagamento_informado_por=usuario_gestor_a,
            motivo_pagamento="x",
        ),
    )


def test_insert_direto_com_vinculo_de_prestador_e_recusado_pelo_banco(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        7005,
        prestador_documento=empresa_a2.cnpj,
        tomador_documento="77888999000155",
        tp_ret_issqn="2",
    )
    prestado = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa_a2, papel=PapelDocumento.PRESTADOR
    )

    _recusa_do_banco(
        RESTRICAO_VINCULO,
        lambda: EscrituracaoTomada.objects.bulk_create(
            [
                EscrituracaoTomada(
                    vinculo=prestado,
                    empresa=empresa_a2,
                    natureza=T1,
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )


def test_insert_efetivada_com_valor_diferente_do_documento_e_recusado_pelo_banco(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 7006, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    vinculo = vinculo_tomador(documento, empresa_a2)

    _recusa_do_banco(
        RESTRICAO_BATE,
        lambda: EscrituracaoTomada.objects.bulk_create(
            [
                EscrituracaoTomada(
                    vinculo=vinculo,
                    empresa=empresa_a2,
                    natureza=T1,
                    estado=EstadoEscrituracao.EFETIVADA,
                    efetivada_em=timezone.now(),
                    efetivada_por=usuario_gestor_a,
                    criado_por=usuario_gestor_a,
                    data_emissao=date(2026, 10, 5),
                    data_competencia=date(2026, 10, 5),
                    valor_servico=Decimal("999.99"),  # o documento tem 1000.00
                    valor_liquido=Decimal("1000.00"),
                    tp_ret_issqn="2",
                    tp_emit="1",
                )
            ]
        ),
    )


def test_segunda_escrituracao_ativa_para_o_mesmo_vinculo_e_recusada_pelo_banco(
    escritorio_a, usuario_gestor_a, empresa_a2, efetivada
):
    _recusa_do_banco(
        RESTRICAO_UNICA,
        lambda: EscrituracaoTomada.objects.bulk_create(
            [
                EscrituracaoTomada(
                    vinculo=efetivada.vinculo,
                    empresa=empresa_a2,
                    natureza=T1,
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )
