"""DL-074 (frente A) — imutabilidade e invariantes no banco (receita, confirmação e caixa).

Como na DL-072, três camadas são exercitadas separadamente, porque cada uma cobre o que
a outra não alcança:
- `save()`/`delete()` do modelo (recusa em Python);
- `QuerySet.update()`/`bulk_create()`/`delete()` (passam por cima do `save()`);
- gatilhos e `CheckConstraint`/`UniqueConstraint` no PostgreSQL.

As recusas do banco são verificadas pelo NOME da restrição violada
(`diag.constraint_name`), e não só pela classe de erro.
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fiscal import receita as servico
from apps.fiscal.models import (
    ConfirmacaoImutavel,
    ConfirmacaoReceitaMensal,
    EstadoReceitaInformada,
    MercadoReceita,
    OpcaoRegimeCaixaSimples,
    ReceitaInformada,
    ReceitaInformadaImutavel,
)
from apps.fiscal.tests.test_dl074_suporte import informar_e_confirmar, preparar_simples

pytestmark = pytest.mark.django_db

RESTRICAO_RECEITA = "receita_informada_imutavel_depois_de_confirmada"
RESTRICAO_CONFIRMACAO = "confirmacao_mes_imutavel_depois_de_confirmada"


def _recusa_do_banco(restricao, operacao):
    with pytest.raises(IntegrityError) as info:
        with transaction.atomic():
            operacao()
    diag = getattr(info.value.__cause__, "diag", None)
    assert diag is not None and diag.constraint_name == restricao, info.value


@pytest.fixture
def receita_confirmada(empresa_a, usuario_gestor_a):
    return informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "100.00")


@pytest.fixture
def confirmacao(empresa_a, usuario_gestor_a):
    return servico.confirmar_mes(empresa_a, 2026, 5, usuario_gestor_a)


# ---------------------------------------------------------------------------
# Receita informada: camada Python
# ---------------------------------------------------------------------------


def test_save_de_receita_confirmada_e_recusado_e_nada_muda(receita_confirmada):
    receita_confirmada.valor = receita_confirmada.valor + 1

    with pytest.raises(ReceitaInformadaImutavel):
        receita_confirmada.save()

    receita_confirmada.refresh_from_db()
    assert receita_confirmada.valor.__str__() == "100.00"


def test_delete_de_receita_confirmada_e_recusado(receita_confirmada):
    with pytest.raises(ReceitaInformadaImutavel):
        receita_confirmada.delete()

    assert ReceitaInformada.objects.filter(pk=receita_confirmada.pk).exists()


def test_save_e_delete_de_rascunho_sao_permitidos(empresa_a, usuario_gestor_a):
    rascunho = servico.lancar_receita_informada(
        empresa_a, 2026, 5, MercadoReceita.INTERNO, "10", "ajuste", "M.", "S.", usuario_gestor_a
    )

    rascunho.delete()

    assert not ReceitaInformada.objects.filter(pk=rascunho.pk).exists()


# ---------------------------------------------------------------------------
# Receita informada: camada do banco (QuerySet.update e SQL direto)
# ---------------------------------------------------------------------------


def test_update_de_valor_em_receita_confirmada_e_recusado_pelo_banco(receita_confirmada):
    _recusa_do_banco(
        RESTRICAO_RECEITA,
        lambda: ReceitaInformada.objects.filter(pk=receita_confirmada.pk).update(valor="999.00"),
    )


def test_voltar_receita_confirmada_a_rascunho_e_recusado_pelo_banco(receita_confirmada):
    _recusa_do_banco(
        RESTRICAO_RECEITA,
        lambda: ReceitaInformada.objects.filter(pk=receita_confirmada.pk).update(
            estado=EstadoReceitaInformada.RASCUNHO
        ),
    )


def test_delete_de_receita_confirmada_e_recusado_pelo_banco(receita_confirmada):
    _recusa_do_banco(
        RESTRICAO_RECEITA,
        lambda: ReceitaInformada.objects.filter(pk=receita_confirmada.pk).delete(),
    )


def test_estorno_pelo_banco_so_muda_as_colunas_do_estorno(receita_confirmada, usuario_gestor_a):
    # As colunas do estorno são as únicas que podem mudar: estado, quando, quem e o motivo.
    ReceitaInformada.objects.filter(pk=receita_confirmada.pk).update(
        estado=EstadoReceitaInformada.ESTORNADA,
        estornada_em=timezone.now(),
        motivo_estorno="Estorno sintético.",
        estornada_por=usuario_gestor_a,
    )

    receita_confirmada.refresh_from_db()
    assert receita_confirmada.estado == EstadoReceitaInformada.ESTORNADA


def test_receita_estornada_nao_muda_mais_pelo_banco(receita_confirmada, usuario_gestor_a):
    servico.estornar_receita_informada(receita_confirmada, "Motivo.", usuario_gestor_a)

    _recusa_do_banco(
        RESTRICAO_RECEITA,
        lambda: ReceitaInformada.objects.filter(pk=receita_confirmada.pk).update(
            estado=EstadoReceitaInformada.CONFIRMADA
        ),
    )


def test_mercado_fora_do_catalogo_e_recusado_pelo_banco(empresa_a, usuario_gestor_a):
    # Rascunho pode ser alterado pelo banco, então o catálogo é checado pela restrição.
    receita = servico.lancar_receita_informada(
        empresa_a, 2026, 5, MercadoReceita.INTERNO, "10", "ajuste", "M.", "S.", usuario_gestor_a
    )

    _recusa_do_banco(
        "receita_informada_catalogos_validos",
        lambda: ReceitaInformada.objects.filter(pk=receita.pk).update(mercado="misto"),
    )


def test_valor_zero_e_recusado_pelo_banco(empresa_a, usuario_gestor_a):
    _recusa_do_banco(
        "receita_informada_valor_positivo",
        lambda: ReceitaInformada.objects.bulk_create(
            [
                ReceitaInformada(
                    empresa=empresa_a,
                    ano=2026,
                    mes=5,
                    mercado=MercadoReceita.INTERNO,
                    valor="0.00",
                    origem="ajuste",
                    motivo="M.",
                    documento_suporte="S.",
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )


def test_mes_fora_de_1_a_12_e_recusado_pelo_banco(empresa_a, usuario_gestor_a):
    _recusa_do_banco(
        "receita_informada_mes_valido",
        lambda: ReceitaInformada.objects.bulk_create(
            [
                ReceitaInformada(
                    empresa=empresa_a,
                    ano=2026,
                    mes=13,
                    mercado=MercadoReceita.INTERNO,
                    valor="10.00",
                    origem="ajuste",
                    motivo="M.",
                    documento_suporte="S.",
                    criado_por=usuario_gestor_a,
                )
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Confirmação do mês: camada Python e do banco
# ---------------------------------------------------------------------------


def test_save_em_confirmacao_existente_e_recusado(confirmacao):
    confirmacao.valor_confirmado_interno = 0

    with pytest.raises(ConfirmacaoImutavel):
        confirmacao.save()


def test_delete_de_confirmacao_e_recusado(confirmacao):
    with pytest.raises(ConfirmacaoImutavel):
        confirmacao.delete()


def test_total_confirmado_nao_muda_por_update_pelo_banco(confirmacao):
    # O mês de teste não tem receita: o total gravado é 0,00. Mudá-lo para 5,00 é a alteração.
    _recusa_do_banco(
        RESTRICAO_CONFIRMACAO,
        lambda: ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).update(
            valor_confirmado_interno="5.00"
        ),
    )


def test_confirmada_nao_vai_para_reaberta_mudando_o_ato_pelo_banco(confirmacao):
    _recusa_do_banco(
        RESTRICAO_CONFIRMACAO,
        lambda: ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).update(
            estado="reaberta",
            reaberta_em="2026-10-08T12:00:00+00:00",
            reaberta_por=confirmacao.confirmada_por,
            motivo_reabertura="Motivo.",
            valor_confirmado_interno="5.00",
        ),
    )


def test_reabertura_sem_motivo_e_recusada_pelo_banco(confirmacao):
    # Coerência do estado: reaberta exige motivo (restrição, sem depender do serviço).
    _recusa_do_banco(
        "confirmacao_campos_coerentes_com_o_estado",
        lambda: ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).update(
            estado="reaberta",
            reaberta_em="2026-10-08T12:00:00+00:00",
            reaberta_por=confirmacao.confirmada_por,
            motivo_reabertura="",
        ),
    )


def test_mesma_empresa_e_mes_duas_vezes_e_recusado_pelo_banco(
    empresa_a, usuario_gestor_a, confirmacao
):
    def inserir():
        ConfirmacaoReceitaMensal.objects.bulk_create(
            [
                ConfirmacaoReceitaMensal(
                    empresa=empresa_a,
                    ano=2026,
                    mes=5,
                    valor_confirmado_interno="0",
                    valor_confirmado_externo="0",
                    confirmada_em="2026-10-08T12:00:00+00:00",
                    confirmada_por=usuario_gestor_a,
                )
            ]
        )

    _recusa_do_banco("confirmacao_mes_unica_por_empresa", inserir)


def test_mes_confirmado_de_novo_pelo_servico_e_recusado_e_nao_duplica(
    empresa_a, usuario_gestor_a, confirmacao
):
    with pytest.raises(servico.ReceitaErro):
        servico.confirmar_mes(empresa_a, 2026, 5, usuario_gestor_a)

    assert ConfirmacaoReceitaMensal.objects.filter(empresa=empresa_a, ano=2026, mes=5).count() == 1


# ---------------------------------------------------------------------------
# Opção pelo regime de caixa: restrições (HI-66)
# ---------------------------------------------------------------------------


@pytest.fixture
def empresa_optante(empresa_a):
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def test_opcao_de_caixa_duplicada_no_mesmo_ano_e_recusada_pela_restricao(
    empresa_optante, usuario_gestor_a
):
    servico.registrar_opcao_regime_caixa(empresa_optante, 2026, usuario_gestor_a)

    with pytest.raises(servico.ReceitaErro, match="irretratável"):
        servico.registrar_opcao_regime_caixa(empresa_optante, 2026, usuario_gestor_a)

    assert OpcaoRegimeCaixaSimples.objects.filter(empresa=empresa_optante).count() == 1


def test_opcao_de_caixa_para_2027_e_recusada_pelo_banco(empresa_optante, usuario_gestor_a):
    _recusa_do_banco(
        "opcao_caixa_so_ate_2026",
        lambda: OpcaoRegimeCaixaSimples.objects.bulk_create(
            [
                OpcaoRegimeCaixaSimples(
                    empresa=empresa_optante, ano_calendario=2027, registrada_por=usuario_gestor_a
                )
            ]
        ),
    )


def test_opcao_de_caixa_para_2027_e_recusada_pelo_servico_antes_de_gravar(
    empresa_optante, usuario_gestor_a
):
    with pytest.raises(servico.EntradaInvalidaReceita, match="até o PA 12/2026"):
        servico.registrar_opcao_regime_caixa(empresa_optante, 2027, usuario_gestor_a)

    assert not OpcaoRegimeCaixaSimples.objects.exists()


def test_opcao_de_caixa_sem_simples_no_ano_e_recusada(empresa_a, usuario_gestor_a):
    # Empresa sem nenhum período do Simples: não há o que optar.
    with pytest.raises(servico.ReceitaErro, match="período do Simples"):
        servico.registrar_opcao_regime_caixa(empresa_a, 2026, usuario_gestor_a)
