"""DL-074 (frente A) — confirmação mensal, reabertura e o gancho do estorno.

Critérios do plano cobertos aqui: 6 (estornar escrituração ou receita de mês confirmado
reabre a confirmação e marca o mês "a retificar"; o RBT12 dos meses seguintes volta a
"não apurável" até reconfirmar) e a regra de "reabrir exige motivo" (item 4).

Cenário padrão: abertura em 2015, Simples desde 2018, para que o RBT12 de jun/2026 use
a janela de jun/2025 a mai/2026 (§ 1º), que contém maio.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EstadoConfirmacaoMes,
    EstadoEscrituracao,
    EstadoReceitaInformada,
    MercadoReceita,
)
from apps.fiscal.tests.test_dl074_suporte import (
    escriturar,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
    sequencia,
)

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO


@pytest.fixture
def empresa(empresa_a):
    fixar_inicio_de_uso(empresa_a, 2025, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _confirmar_janela(empresa, usuario, *, exceto=()):
    """Confirma jan/2025 a jun/2026 (exceto os meses em `exceto`)."""
    for ano, mes in sequencia(2025, 1, 18):
        if (ano, mes) not in exceto:
            servico.confirmar_mes(empresa, ano, mes, usuario)


# ---------------------------------------------------------------------------
# Confirmação: ato com autor, totais no instante e recusa de duplicidade
# ---------------------------------------------------------------------------


def test_confirmar_mes_grava_o_total_de_cada_mercado_no_instante_do_ato(
    empresa, escritorio_a, usuario_gestor_a
):
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=201, competencia=(2026, 5), valor="1000"
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 5, "250")

    confirmacao = servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    confirmacao.refresh_from_db()
    assert confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
    assert confirmacao.valor_confirmado_interno == Decimal("1250.00")
    assert confirmacao.valor_confirmado_externo == Decimal("0.00")
    assert confirmacao.confirmada_por_id == usuario_gestor_a.pk
    assert servico.situacao_do_mes(empresa, 2026, 5) == "confirmado"


def test_confirmar_mes_ja_confirmado_e_recusado(empresa, usuario_gestor_a):
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    with pytest.raises(servico.ReceitaErro, match="já está confirmada"):
        servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)


def test_reabrir_exige_motivo_e_so_vale_para_mes_confirmado(empresa, usuario_gestor_a):
    with pytest.raises(servico.ReceitaErro, match="Só mês confirmado"):
        servico.reabrir_mes(empresa, 2026, 5, "Motivo.", usuario_gestor_a)

    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    with pytest.raises(servico.EntradaInvalidaReceita, match="motivo"):
        servico.reabrir_mes(empresa, 2026, 5, "  ", usuario_gestor_a)

    reaberta = servico.reabrir_mes(
        empresa, 2026, 5, "Recebemos o extrato corrigido.", usuario_gestor_a
    )

    assert reaberta.estado == EstadoConfirmacaoMes.REABERTA
    assert reaberta.motivo_reabertura == "Recebemos o extrato corrigido."
    assert reaberta.a_retificar is False
    assert servico.situacao_do_mes(empresa, 2026, 5) == "nao_confirmado"


def test_mes_reaberto_pode_ser_confirmado_de_novo_e_limpa_a_reabertura(empresa, usuario_gestor_a):
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    servico.reabrir_mes(empresa, 2026, 5, "Correção.", usuario_gestor_a)

    de_novo = servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    de_novo.refresh_from_db()
    assert de_novo.estado == EstadoConfirmacaoMes.CONFIRMADA
    assert de_novo.reaberta_em is None
    assert de_novo.motivo_reabertura == ""


def test_receita_informada_nao_entra_em_mes_ja_confirmado(empresa, usuario_gestor_a):
    # Mudaria o total de um mês declarado completo, sem o ato de reabertura com motivo.
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    receita = servico.lancar_receita_informada(
        empresa, 2026, 5, INTERNO, "100", "ajuste", "Motivo.", "Suporte.", usuario_gestor_a
    )

    with pytest.raises(servico.ReceitaErro, match="já está confirmada"):
        servico.confirmar_receita_informada(receita, usuario_gestor_a)


# ---------------------------------------------------------------------------
# Critério 6 — o gancho do estorno
# ---------------------------------------------------------------------------


def test_estornar_escrituracao_de_mes_confirmado_reabre_e_marca_a_retificar(
    empresa, escritorio_a, usuario_gestor_a
):
    escrituracao = escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=301, competencia=(2026, 5), valor="1000"
    )
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    servico_escrituracao.estornar_escrituracao(escrituracao, "Nota cancelada.", usuario_gestor_a)

    confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=5)
    assert confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    assert confirmacao.a_retificar is True
    assert "05/2026" in confirmacao.motivo_reabertura
    assert f"escrituração nº {escrituracao.pk}" in confirmacao.motivo_reabertura
    assert servico.situacao_do_mes(empresa, 2026, 5) == "a_retificar"
    # A receita do mês já reflete o estorno: a escrituração saiu do total.
    assert servico.receita_do_mes(empresa, 2026, 5).composicao.de(INTERNO).total == Decimal("0.00")


def test_estornar_receita_informada_de_mes_confirmado_reabre_a_retificar(empresa, usuario_gestor_a):
    receita = informar_e_confirmar(empresa, usuario_gestor_a, 2026, 5, "400")
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    servico.estornar_receita_informada(receita, "Valor digitado errado.", usuario_gestor_a)

    confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=5)
    assert confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    assert confirmacao.a_retificar is True
    assert f"receita informada nº {receita.pk}" in confirmacao.motivo_reabertura
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.ESTORNADA


def test_estorno_em_mes_nao_confirmado_nao_cria_confirmacao(
    empresa, escritorio_a, usuario_gestor_a
):
    escrituracao = escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=302, competencia=(2026, 5), valor="1000"
    )

    servico_escrituracao.estornar_escrituracao(escrituracao, "Nota cancelada.", usuario_gestor_a)

    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2026, mes=5).exists()
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.ESTORNADA


def test_estorno_nao_abate_o_mes_corrente(empresa, escritorio_a, usuario_gestor_a):
    # Estorno de maio não mexe na confirmação de junho (o mês corrente): só o mês de origem.
    escrituracao = escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=303, competencia=(2026, 5), valor="1000"
    )
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    servico.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    servico_escrituracao.estornar_escrituracao(escrituracao, "Nota cancelada.", usuario_gestor_a)

    junho = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=6)
    assert junho.estado == EstadoConfirmacaoMes.CONFIRMADA
    assert junho.a_retificar is False
    assert servico.situacao_do_mes(empresa, 2026, 6) == "confirmado"


def test_rbt12_volta_a_nao_apuravel_depois_do_estorno_ate_reconfirmar(
    empresa, escritorio_a, usuario_gestor_a
):
    escrituracao = escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=304, competencia=(2026, 5), valor="1000"
    )
    _confirmar_janela(empresa, usuario_gestor_a)
    assert apuracao.rbt12(empresa, 2026, 6).apuravel

    servico_escrituracao.estornar_escrituracao(escrituracao, "Nota cancelada.", usuario_gestor_a)

    resultado = apuracao.rbt12(empresa, 2026, 6)
    assert not resultado.apuravel
    assert resultado.pendentes_da_janela == ((2026, 5, "a_retificar"),)

    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)

    reconfirmado = apuracao.rbt12(empresa, 2026, 6)
    assert reconfirmado.apuravel
    # A escrituração de maio saiu: a janela de jun/25 a mai/26 soma zero em maio.
    assert reconfirmado.de(INTERNO).apurado == Decimal("0.00")


def test_mes_reaberto_a_mao_nao_e_a_retificar_mas_nao_confirma(empresa, usuario_gestor_a):
    _confirmar_janela(empresa, usuario_gestor_a)
    servico.reabrir_mes(empresa, 2026, 5, "Revisão do contador.", usuario_gestor_a)

    resultado = apuracao.rbt12(empresa, 2026, 6)

    assert resultado.pendentes_da_janela == ((2026, 5, "nao_confirmado"),)


def test_escrituracao_efetivada_em_mes_confirmado_deixa_o_mes_a_retificar_sem_gancho(
    empresa, escritorio_a, usuario_gestor_a
):
    # A efetivação não passa pelo gancho do estorno. A proteção é o total guardado no ato:
    # o total mudou, e o mês deixa de estar confirmado de fato.
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=305, competencia=(2026, 5), valor="90"
    )

    assert servico.situacao_do_mes(empresa, 2026, 5) == "a_retificar"
    assert ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=5).estado == (
        EstadoConfirmacaoMes.CONFIRMADA
    )


def test_gancho_nao_mexe_em_mes_ja_reaberto_alem_de_marcar_a_retificar(
    empresa, escritorio_a, usuario_gestor_a
):
    escrituracao = escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=306, competencia=(2026, 5), valor="1000"
    )
    servico.confirmar_mes(empresa, 2026, 5, usuario_gestor_a)
    servico.reabrir_mes(empresa, 2026, 5, "Revisão.", usuario_gestor_a)

    servico_escrituracao.estornar_escrituracao(escrituracao, "Nota cancelada.", usuario_gestor_a)

    confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=5)
    assert confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    assert confirmacao.a_retificar is True
    assert confirmacao.motivo_reabertura == "Revisão."
