"""DL-085 (frente A), critério 5: a receita do mês e o Presumido do trimestre batem com a soma das
notas efetivadas pelo lote. Valores escritos à mão, em reais.

Notas de posto (NFC-e, modelo 65), de combustível (1,6% no Presumido, `combustivel`) e de revenda
(8%, comércio e indústria, `revenda`). A soma à mão: combustível 100,00 + 250,00 + 40,00 = 390,00;
revenda 80,00 + 80,00 = 160,00; total 550,00.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EscrituracaoNFe,
    EstadoConfirmacaoMes,
)
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.test_dl074_suporte import (
    fixar_hoje,
    fixar_inicio_de_uso,
    preparar_simples,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a)


@pytest.fixture
def empresa_presumida(escritorio_a, gestor):
    """Lucro Presumido em 2026, atividade padrão de serviços gerais (32%), como na DL-083. A NF-e
    não usa o padrão: a atividade vem da natureza de cada item."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Presumido DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", gestor)
    presumido_servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        gestor,
    )
    return empresa


def _posto_de_marco(escritorio, usuario):
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio, usuario, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio, usuario, numero=numero, valor="80.00", cfop="5102", csosn="102")


def test_receita_do_mes_e_o_presumido_batem_com_as_notas_efetivadas(
    escritorio_a, gestor, empresa_presumida
):
    """Critério 5. Receita por natureza do mês: combustível 390,00 e revenda 160,00 (total
    550,00). O
    Presumido do 1º trimestre tem as mesmas linhas: 390,00 na atividade de revenda de combustíveis
    (1,6%) e 160,00 em comércio e indústria (8%). O total das notas efetivadas é o mesmo."""
    _posto_de_marco(escritorio_a, gestor)
    previa = previa_lida(empresa_presumida, 2026, 3)
    confirmar_tudo(empresa_presumida, gestor, 2026, 3, previa, limite=2)

    soma_notas = sum(
        (e.receita_bruta for e in EscrituracaoNFe.objects.filter(empresa=empresa_presumida)),
        D("0.00"),
    )
    assert soma_notas == D("550.00")

    composicao = receita_servico.composicao_do_mes(empresa_presumida, 2026, 3)
    assert composicao.de("interno").mercadoria == D("550.00")
    conferencia = servico.conferencia_do_mes(empresa_presumida, 2026, 3)
    assert conferencia.receita_por_natureza["combustivel"]["soma_na_receita"] == D("390.00")
    assert conferencia.receita_por_natureza["revenda"]["soma_na_receita"] == D("160.00")

    apuracao = presumido_servico.apurar_trimestre(empresa_presumida, 2026, 1)
    assert sum((linha.valor for linha in apuracao.nfe), D("0.00")) == D("550.00")
    por_atividade = {}
    for linha in apuracao.nfe:
        por_atividade[linha.atividade] = por_atividade.get(linha.atividade, D("0.00")) + linha.valor
    assert por_atividade == {
        tab.REVENDA_COMBUSTIVEIS: D("390.00"),
        tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA: D("160.00"),
    }


def test_mes_confirmado_vira_a_retificar_quando_o_lote_efetiva_notas_dele(
    escritorio_a, gestor, monkeypatch
):
    """Mês já confirmado (DL-074) vira "a retificar" quando o lote efetiva uma nota dele, na mesma
    transação de cada efetivação. A regra não muda por ser em lote."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Simples DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))
    fixar_inicio_de_uso(empresa, 2021, 1)
    fixar_hoje(monkeypatch, date(2026, 4, 15))
    _posto_de_marco(escritorio_a, gestor)
    receita_servico.confirmar_mes(empresa, 2026, 3, gestor)
    assert _confirmacao(empresa).estado == EstadoConfirmacaoMes.CONFIRMADA

    confirmar_tudo(empresa, gestor, 2026, 3, previa_lida(empresa, 2026, 3), limite=2)

    confirmacao = _confirmacao(empresa)
    assert confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    assert confirmacao.a_retificar


def _confirmacao(empresa):
    return ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=2026, mes=3)
