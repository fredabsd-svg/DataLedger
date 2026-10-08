"""DL-072 (frente A) — imutabilidade e invariantes no banco.

Critério 4: efetivada não se edita; o estorno é o único caminho. Critério 11:
a trava de imutabilidade e a restrição parcial são o que o mutante testa.

Três camadas são exercitadas separadamente, porque cada uma cobre o que a
outra não alcança:
- `save()`/`delete()` do modelo (recusa em Python);
- `QuerySet.update()`/`bulk_create()`/`delete()` (passam por cima do `save()`);
- gatilhos e `CheckConstraint`/`UniqueConstraint` no PostgreSQL.

As recusas do banco são verificadas pelo NOME da restrição violada
(`diag.constraint_name`), não só pela classe de erro: um `IntegrityError`
qualquer não provaria que a regra certa disparou.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EscrituracaoImutavel,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

pytestmark = pytest.mark.django_db

NATUREZA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
OUTRA_NATUREZA = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO


def _nota(escritorio, usuario, sufixo=1):
    identificador = identificador_nfse(sufixo)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero=str(sufixo)),
        nome_arquivo="nota.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _vinculo(documento, empresa, papel=PapelDocumento.PRESTADOR):
    return VinculoDocumentoEmpresa.objects.get(documento=documento, empresa=empresa, papel=papel)


def _efetivada(escritorio, empresa, usuario, sufixo=1):
    nota = _nota(escritorio, usuario, sufixo)
    return servico.efetivar_escrituracao(_vinculo(nota, empresa), NATUREZA, usuario)


def _nome_da_restricao_violada(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def _recusa_do_banco(restricao, operacao):
    """Espera IntegrityError causado pela restrição NOMEADA. A operação roda
    num SAVEPOINT para que a transação de teste continue utilizável."""
    with pytest.raises(IntegrityError) as info:
        with transaction.atomic():
            operacao()
    assert _nome_da_restricao_violada(info.value) == restricao, str(info.value)


# ---------------------------------------------------------------------------
# Camada 1 — o modelo (save/delete em Python)
# ---------------------------------------------------------------------------


def test_save_de_efetivada_e_recusado_e_nada_muda(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    escrituracao.natureza = OUTRA_NATUREZA
    with pytest.raises(EscrituracaoImutavel):
        escrituracao.save()

    gravada = EscrituracaoFiscal.objects.get(pk=escrituracao.pk)
    assert gravada.natureza == NATUREZA


def test_save_de_estornada_e_recusado(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)
    estornada = servico.estornar_escrituracao(escrituracao, "erro", usuario_gestor_a)

    estornada.motivo_estorno = "outro motivo"
    with pytest.raises(EscrituracaoImutavel):
        estornada.save()

    assert EscrituracaoFiscal.objects.get(pk=estornada.pk).motivo_estorno == "erro"


def test_save_usa_o_estado_gravado_e_nao_o_da_memoria(escritorio_a, empresa_a, usuario_gestor_a):
    # O objeto em memória diz "rascunho", mas o banco já está efetivada: a
    # guarda olha o banco, então não deixa passar.
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)
    desatualizada = EscrituracaoFiscal.objects.get(pk=escrituracao.pk)
    desatualizada.estado = EstadoEscrituracao.RASCUNHO

    with pytest.raises(EscrituracaoImutavel):
        desatualizada.save()


def test_delete_de_efetivada_e_recusado(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    with pytest.raises(EscrituracaoImutavel):
        escrituracao.delete()

    assert EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).exists()


def test_delete_de_rascunho_e_permitido(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    rascunho = servico.salvar_rascunho(_vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a)

    rascunho.delete()

    assert not EscrituracaoFiscal.objects.filter(pk=rascunho.pk).exists()


def test_modelo_recusa_vinculo_de_tomador(escritorio_a, empresa_a, empresa_a2, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    tomador = _vinculo(nota, empresa_a2, papel=PapelDocumento.TOMADOR)

    with pytest.raises(ValidationError, match="prestadora"):
        EscrituracaoFiscal.objects.create(
            vinculo=tomador,
            empresa=empresa_a2,
            natureza=NATUREZA,
            criado_por=usuario_gestor_a,
        )
    assert EscrituracaoFiscal.objects.count() == 0


def test_modelo_recusa_empresa_diferente_da_do_vinculo(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    prestador = _vinculo(nota, empresa_a)

    with pytest.raises(ValidationError, match="mesma empresa"):
        EscrituracaoFiscal.objects.create(
            vinculo=prestador,
            empresa=empresa_b,
            natureza=NATUREZA,
            criado_por=usuario_gestor_a,
        )
    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# Camada 2 — o banco contra QuerySet.update()/delete(), que ignoram o save()
# ---------------------------------------------------------------------------

RESTRICAO_IMUTAVEL = "escrituracao_imutavel_depois_de_efetivada"


def test_update_em_efetivada_e_recusado_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
            valor_servico=Decimal("1.00")
        ),
    )
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).valor_servico != Decimal("1.00")


def test_delete_em_efetivada_e_recusado_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).delete(),
    )
    assert EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).exists()


def test_efetivada_nao_volta_a_rascunho_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
            estado=EstadoEscrituracao.RASCUNHO
        ),
    )


def test_estorno_pelo_banco_so_muda_as_colunas_do_estorno(
    escritorio_a, empresa_a, usuario_gestor_a
):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    # Estorno que também troca a natureza: recusado, mesmo sendo "estorno".
    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
            estado=EstadoEscrituracao.ESTORNADA,
            estornada_em=escrituracao.efetivada_em,
            estornada_por=usuario_gestor_a,
            motivo_estorno="motivo",
            natureza=OUTRA_NATUREZA,
        ),
    )
    # O mesmo estorno, sem tocar no ato, passa.
    EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
        estado=EstadoEscrituracao.ESTORNADA,
        estornada_em=escrituracao.efetivada_em,
        estornada_por=usuario_gestor_a,
        motivo_estorno="motivo",
    )
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == (
        EstadoEscrituracao.ESTORNADA
    )


def test_estornada_nao_muda_mais_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)
    servico.estornar_escrituracao(escrituracao, "primeiro", usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
            motivo_estorno="apagando a história"
        ),
    )


def test_rascunho_nao_pula_direto_para_estornada_pelo_banco(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    rascunho = servico.salvar_rascunho(_vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: EscrituracaoFiscal.objects.filter(pk=rascunho.pk).update(
            estado=EstadoEscrituracao.ESTORNADA
        ),
    )


def test_bulk_create_de_tomador_e_recusado_pelo_banco(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    tomador = _vinculo(nota, empresa_a2, papel=PapelDocumento.TOMADOR)

    _recusa_do_banco(
        "escrituracao_vinculo_prestador_da_empresa",
        lambda: EscrituracaoFiscal.objects.bulk_create(
            [
                EscrituracaoFiscal(
                    vinculo=tomador,
                    empresa=empresa_a2,
                    natureza=NATUREZA,
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )


def test_bulk_create_com_empresa_de_outra_empresa_e_recusado_pelo_banco(
    escritorio_a, empresa_a, empresa_b, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    prestador = _vinculo(nota, empresa_a)

    _recusa_do_banco(
        "escrituracao_vinculo_prestador_da_empresa",
        lambda: EscrituracaoFiscal.objects.bulk_create(
            [
                EscrituracaoFiscal(
                    vinculo=prestador,
                    empresa=empresa_b,
                    natureza=NATUREZA,
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Camada 3 — restrições declaradas: unicidade parcial e coerência do estado
# ---------------------------------------------------------------------------


def test_so_uma_escrituracao_ativa_por_vinculo_no_banco(escritorio_a, empresa_a, usuario_gestor_a):
    # Critério 6 e 11: a restrição parcial, e não só a trava do serviço, é o
    # que impede a segunda linha ativa. O create() usa INSERT direto.
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    servico.efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    _recusa_do_banco(
        "escrituracao_ativa_unica_por_vinculo",
        lambda: EscrituracaoFiscal.objects.create(
            vinculo=vinculo,
            empresa=empresa_a,
            natureza=OUTRA_NATUREZA,
            estado=EstadoEscrituracao.RASCUNHO,
            criado_por=usuario_gestor_a,
        ),
    )
    assert EscrituracaoFiscal.objects.count() == 1


def test_estornada_libera_a_unicidade_parcial(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    primeira = servico.efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)
    servico.estornar_escrituracao(primeira, "erro", usuario_gestor_a)

    # Estornada não conta: um rascunho novo para o mesmo vínculo é aceito.
    EscrituracaoFiscal.objects.create(
        vinculo=vinculo,
        empresa=empresa_a,
        natureza=OUTRA_NATUREZA,
        estado=EstadoEscrituracao.RASCUNHO,
        criado_por=usuario_gestor_a,
    )
    assert EscrituracaoFiscal.objects.count() == 2


def test_efetivada_sem_colunas_do_ato_e_recusada_pelo_banco(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)

    _recusa_do_banco(
        "escrituracao_campos_coerentes_com_o_estado",
        lambda: EscrituracaoFiscal.objects.bulk_create(
            [
                EscrituracaoFiscal(
                    vinculo=_vinculo(nota, empresa_a),
                    empresa=empresa_a,
                    natureza=NATUREZA,
                    estado=EstadoEscrituracao.EFETIVADA,
                    criado_por=usuario_gestor_a,
                    # efetivada_em/por, valores e datas ficam de fora de propósito
                )
            ]
        ),
    )


def test_estornada_sem_motivo_e_recusada_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    escrituracao = _efetivada(escritorio_a, empresa_a, usuario_gestor_a)

    _recusa_do_banco(
        "escrituracao_campos_coerentes_com_o_estado",
        lambda: EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).update(
            estado=EstadoEscrituracao.ESTORNADA,
            estornada_em=escrituracao.efetivada_em,
            estornada_por=usuario_gestor_a,
            motivo_estorno="",
        ),
    )


def test_estado_fora_do_catalogo_e_recusado_pelo_banco(escritorio_a, empresa_a, usuario_gestor_a):
    # Um estado fora de rascunho/efetivada/estornada viola DUAS restrições de
    # forma: `escrituracao_estado_valido` e `escrituracao_campos_coerentes_...`
    # (esta exige um dos três ramos, e nenhum casa). O PostgreSQL reporta
    # qualquer uma das duas, na ordem que escolher; o que o teste prova é que
    # a recusa vem de uma das restrições de estado, nomeadas.
    nota = _nota(escritorio_a, usuario_gestor_a)

    with pytest.raises(IntegrityError) as info:
        with transaction.atomic():
            EscrituracaoFiscal.objects.bulk_create(
                [
                    EscrituracaoFiscal(
                        vinculo=_vinculo(nota, empresa_a),
                        empresa=empresa_a,
                        natureza=NATUREZA,
                        estado="pendente",
                        criado_por=usuario_gestor_a,
                    )
                ]
            )
    assert _nome_da_restricao_violada(info.value) in {
        "escrituracao_estado_valido",
        "escrituracao_campos_coerentes_com_o_estado",
    }
    assert EscrituracaoFiscal.objects.count() == 0


def test_autor_da_escrituracao_nao_pode_ser_apagado(escritorio_a, empresa_a, usuario_gestor_a):
    # `criado_por`/`efetivada_por` são PROTECT: apagar o usuário não pode
    # apagar a autoria de um ato fiscal (mesma decisão da DL-052 na contabilidade).
    nota = _nota(escritorio_a, usuario_gestor_a)
    servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a)

    with pytest.raises(ProtectedError):
        usuario_gestor_a.delete()
    assert EscrituracaoFiscal.objects.count() == 1
