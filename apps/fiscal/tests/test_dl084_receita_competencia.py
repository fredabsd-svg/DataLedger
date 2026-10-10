"""DL-084, item 5 (HI-135): competência ou parcela na receita informada entra na identidade.

Critério 5: três mensalidades iguais com competências diferentes são aceitas; sem competência, a
segunda é recusada como hoje. Dados sintéticos.
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import ReceitaTrimestralPresumido

pytestmark = pytest.mark.django_db


@pytest.fixture
def presumido(empresa_a, usuario_gestor_a, escritorio_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    atividade = servico.criar_atividade(
        empresa_a,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1)},
        usuario_gestor_a,
    )
    return {"empresa": empresa_a, "atividade": atividade, "usuario": usuario_gestor_a}


def _mensalidade(presumido, competencia=None, suporte="Contrato sintético 77", parcela=None):
    dados = {
        "tipo": "presuncao",
        "atividade_id": presumido["atividade"].pk,
        "valor": "1500.00",
        "descricao": "Mensalidade de assessoria sintética",
        "suporte": suporte,
    }
    if competencia is not None:
        dados["competencia"] = competencia
    return servico.criar_receita(presumido["empresa"], 2026, 1, dados, presumido["usuario"])


def test_tres_mensalidades_iguais_com_competencias_diferentes_sao_aceitas(presumido):
    # Mesmo contrato, mesmo valor, mesmo suporte: três meses do trimestre.
    recebidas = [
        _mensalidade(presumido, competencia=mes) for mes in ("2026-01", "2026-02", "2026-03")
    ]
    assert [r.competencia for r in recebidas] == ["2026-01", "2026-02", "2026-03"]
    assert len(servico.listar_receitas(presumido["empresa"], 2026, 1)) == 3


def test_sem_competencia_a_segunda_mensalidade_igual_e_recusada_e_pede_a_parcela(presumido):
    _mensalidade(presumido)
    with pytest.raises(servico.PresumidoConflito) as exc:
        _mensalidade(presumido)
    # A mensagem pede a competência quando for outra parcela do mesmo contrato.
    assert "competência (AAAA-MM) ou o número da parcela" in exc.value.mensagem


def test_mesma_competencia_duas_vezes_e_recusada(presumido):
    _mensalidade(presumido, competencia="2026-02")
    with pytest.raises(servico.PresumidoConflito) as exc:
        _mensalidade(presumido, competencia="2026-02")
    assert "competência 2026-02" in exc.value.mensagem


def test_parcela_numerada_entra_na_identidade_e_a_repetida_e_recusada(presumido):
    _mensalidade(presumido, competencia="parcela 1")
    _mensalidade(presumido, competencia="parcela 2")
    with pytest.raises(servico.PresumidoConflito):
        _mensalidade(presumido, competencia="parcela 2")


def test_a_descricao_nao_diferencia_a_receita(presumido):
    # Descrição livre diferente não torna a receita outra: só a competência ou a parcela.
    _mensalidade(presumido)
    dados = {
        "tipo": "presuncao",
        "atividade_id": presumido["atividade"].pk,
        "valor": "1500.00",
        "descricao": "outra descrição",
        "suporte": "Contrato sintético 77",
    }
    with pytest.raises(servico.PresumidoConflito):
        servico.criar_receita(presumido["empresa"], 2026, 1, dados, presumido["usuario"])


def test_competencia_fora_do_trimestre_e_recusada(presumido):
    with pytest.raises(servico.EntradaInvalidaPresumido) as exc:
        _mensalidade(presumido, competencia="2026-04")
    assert "não está no 1º trimestre de 2026" in exc.value.mensagem


@pytest.mark.parametrize("ruim", ["2026/02", "fevereiro", "parcela 0", "parcela 100", "2026-13", 5])
def test_formato_de_competencia_invalido_e_recusado(presumido, ruim):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        _mensalidade(presumido, competencia=ruim)


def test_competencia_em_maiusculas_vira_forma_canonica(presumido):
    receita = _mensalidade(presumido, competencia="Parcela 3")
    assert receita.competencia == "parcela 3"


def test_banco_recusa_competencia_fora_do_formato_mesmo_por_insert_direto(presumido):
    # A CHECK é a segunda defesa: um INSERT direto com formato inválido não entra. (O UPDATE nem
    # chega à CHECK: o gatilho da receita já o bloqueia, por imutabilidade.)
    with pytest.raises(IntegrityError), transaction.atomic():
        ReceitaTrimestralPresumido.objects.create(
            empresa=presumido["empresa"],
            ano=2026,
            trimestre=1,
            tipo="presuncao",
            atividade=presumido["atividade"],
            descricao="insert direto sintético",
            valor="10.00",
            suporte="suporte sintético",
            competencia="2026/02",
            criada_por=presumido["usuario"],
        )
