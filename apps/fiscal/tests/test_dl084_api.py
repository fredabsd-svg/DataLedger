"""DL-084: a API expõe o que o serviço decidiu (competência, forma padrão, antecipação e avisos).

Sintético. Os valores das parcelas são construídos à mão nos testes; o cálculo já está testado em
`test_dl084_calendario.py`. Aqui se confere o contrato: campos novos, campos ausentes e o status.
"""

import json
from datetime import date
from decimal import Decimal as D

import pytest

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.api_presumido import _parcela_payload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fim_de_2026(monkeypatch):
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))


@pytest.fixture
def presumido_api(empresa_a, usuario_gestor_a):
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


def _url(empresa, sufixo):
    return f"/fiscal/api/empresas/{empresa.pk}/presumido/{sufixo}"


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def test_receita_pela_api_aceita_competencia_e_devolve_o_campo(
    client, presumido_api, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2026,
        "trimestre": 1,
        "tipo": "presuncao",
        "atividade_id": presumido_api["atividade"].pk,
        "descricao": "Mensalidade sintética",
        "valor": "900.00",
        "suporte": "Contrato sintético 9",
        "competencia": "2026-02",
    }
    criada = _post(client, _url(presumido_api["empresa"], "receitas/"), corpo)
    assert criada.status_code == 201
    assert criada.json()["competencia"] == "2026-02"


def test_receita_pela_api_sem_competencia_na_segunda_igual_e_409(
    client, presumido_api, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2026,
        "trimestre": 1,
        "tipo": "presuncao",
        "atividade_id": presumido_api["atividade"].pk,
        "descricao": "Mensalidade sintética",
        "valor": "900.00",
        "suporte": "Contrato sintético 9",
    }
    assert _post(client, _url(presumido_api["empresa"], "receitas/"), corpo).status_code == 201
    segunda = _post(client, _url(presumido_api["empresa"], "receitas/"), corpo)
    assert segunda.status_code == 409
    assert "parcela" in segunda.json()["detail"]


def test_apuracao_mostra_a_forma_padrao_do_escritorio_e_a_gravada(
    client, presumido_api, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    url = _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
    assert client.get(url).json()["forma_recolhimento_padrao"] == "tres_quotas"
    _post(
        client,
        _url(presumido_api["empresa"], "parametros/"),
        {"forma_recolhimento": "quota_unica"},
    )
    assert client.get(url).json()["forma_recolhimento_padrao"] == "quota_unica"


def test_parcela_na_api_traz_a_data_antecipada_e_os_avisos_locais():
    # Parcela construída à mão: 30/03/2029 (Sexta-feira Santa) antecipou para 29/03/2029.
    parcela = calc.Parcela(
        numero=1,
        valor=D("1000.00"),
        vencimento=date(2029, 3, 29),
        aviso_calendario=False,
        juros="sem juros",
        antecipada_de=date(2029, 3, 30),
        avisos_locais=("feriado local: confirmar expediente bancário na praça",),
    )
    payload = _parcela_payload(parcela)
    assert payload["vencimento"] == "2029-03-29"
    assert payload["antecipada_de"] == "2029-03-30"
    assert payload["aviso_calendario"] is False
    assert payload["avisos_locais"] == ["feriado local: confirmar expediente bancário na praça"]


def test_parcela_sem_antecipacao_devolve_nulo_e_lista_vazia():
    parcela = calc.Parcela(
        numero=1,
        valor=D("1000.00"),
        vencimento=date(2026, 4, 30),
        aviso_calendario=False,
        juros="sem juros",
    )
    payload = _parcela_payload(parcela)
    assert payload["antecipada_de"] is None
    assert payload["avisos_locais"] == []


def test_tabela_de_dias_sem_expediente_nao_tem_mais_o_aviso_de_calendario_a_conferir():
    # O texto do aviso antigo não pode voltar: a tela e a API não o usam mais (DL-084, item 1).
    assert tab.DIAS_SEM_EXPEDIENTE_BANCARIO
    assert not hasattr(calc, "datas_a_conferir")


def test_medida_na_api_traz_o_fim_efetivo_e_o_encerramento(client, presumido_api, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    criada = _post(
        client,
        _url(presumido_api["empresa"], "medidas/"),
        {
            "tributo": "irpj",
            "ano_inicial": 2026,
            "trimestre_inicial": 1,
            "numero_processo": "PROCESSO-SINTETICO-API",
            "orgao": "Juízo sintético",
            "data_decisao": "2026-01-15",
            "suporte": "Decisão sintética",
        },
    )
    assert criada.status_code == 201
    corpo = criada.json()
    assert corpo["fim_efetivo"] is None and corpo["encerramento"] is None
