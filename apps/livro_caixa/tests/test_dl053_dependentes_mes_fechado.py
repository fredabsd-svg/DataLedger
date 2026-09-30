"""DL-053 / RC-147 — dependentes do carnê-leão travam em mês encerrado.

Registrar ou retificar a quantidade de dependentes muda a dedução do carnê-leão
dos meses que a vigência cobre (`_dependentes_por_mes`) e, pelo encadeamento
dentro do ano-calendário (RC-130), dos meses seguintes até dezembro. Se algum
desses meses está encerrado, a alteração é recusada (`MesCaixaEncerrado`, 409)
até o mês ser reaberto. A regra exata de "meses alcançados" está em
`services._recusar_se_dependentes_alteram_mes_encerrado`.

Dados sintéticos. A concorrência segue a DL-050 (`join` com timeout e asserção
de conclusão das threads).
"""

# ruff: noqa: F811
# (a fixture `cenario` importada é usada como parâmetro, o padrão do repositório)
import contextlib
import json
import threading
import time
from datetime import date
from unittest import mock

import pytest
from django.db import transaction

from apps.auditoria.models import RegistroAuditoria
from apps.livro_caixa import carne_leao, services
from apps.livro_caixa.carne_leao import (
    registrar_dependentes_carne_leao,
    retificar_dependentes_carne_leao,
)
from apps.livro_caixa.models import DependentesCarneLeaoCliente, FechamentoMesCaixa
from apps.livro_caixa.services import (
    MesCaixaEncerrado,
    MesCaixaOcupado,
    encerrar_mes_caixa,
)
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (  # noqa: F401
    _TIMEOUT_DE_JOIN,
    _cenario_commitado,
    _cliente_logado,
    _encerrar,
    _esperar,
    _pausando,
    _reabrir,
    _rodar_em_thread,
    _url,
    _usuario,
    cenario,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

_PAUSA_CURTA = 0.4


def _dependentes(cenario, quantidade, inicio, empresa=None):
    return registrar_dependentes_carne_leao(
        empresa=empresa or cenario["empresa"],
        quantidade=quantidade,
        competencia_inicio=inicio,
        criado_por=cenario["gestor"],
    )


def _fotografia(empresa):
    return {
        "dependentes": list(
            DependentesCarneLeaoCliente.objects.filter(empresa=empresa)
            .order_by("id")
            .values_list("id", "competencia_inicio", "quantidade")
        ),
        "trilha": list(
            RegistroAuditoria.objects.filter(acao__startswith="dependentes_carne_leao.")
            .order_by("id")
            .values_list("id", flat=True)
        ),
    }


# ---------------------------------------------------------------------------
# A regra de meses alcançados (unidade, sem banco)
# ---------------------------------------------------------------------------


def _idx(ano, mes):
    return ano * 12 + mes - 1


def test_intervalos_registro_novo_sem_posterior_e_aberto():
    antes = [(date(2026, 1, 1), 1)]
    depois = [*antes, (date(2026, 6, 1), 3)]
    assert services._intervalos_de_meses_com_quantidade_diferente(antes, depois) == [
        (_idx(2026, 6), None)
    ]


def test_intervalos_registro_novo_termina_no_proximo_registro_existente():
    antes = [(date(2026, 1, 1), 1), (date(2026, 9, 1), 4)]
    depois = [*antes, (date(2026, 4, 1), 2)]
    assert services._intervalos_de_meses_com_quantidade_diferente(antes, depois) == [
        (_idx(2026, 4), _idx(2026, 9))
    ]


def test_intervalos_mesma_quantidade_que_ja_valia_nao_altera_nada():
    antes = [(date(2026, 1, 1), 2)]
    depois = [*antes, (date(2026, 5, 1), 2)]
    assert services._intervalos_de_meses_com_quantidade_diferente(antes, depois) == []


def test_intervalos_retificar_cobre_ate_o_proximo_registro():
    antes = [(date(2026, 1, 1), 1), (date(2026, 6, 1), 3)]
    depois = [(date(2026, 1, 1), 5), (date(2026, 6, 1), 3)]
    assert services._intervalos_de_meses_com_quantidade_diferente(antes, depois) == [
        (_idx(2026, 1), _idx(2026, 6))
    ]


def test_quantidade_aplicavel_segue_a_regra_de_dependentes_por_mes(cenario):
    """A função usada pela trava tem de concordar com `_dependentes_por_mes`,
    a que a apuração realmente usa."""
    _dependentes(cenario, 1, date(2026, 2, 1))
    _dependentes(cenario, 4, date(2026, 7, 1))
    registros = list(
        DependentesCarneLeaoCliente.objects.filter(empresa=cenario["empresa"]).values_list(
            "competencia_inicio", "quantidade"
        )
    )
    real = carne_leao._dependentes_por_mes(cenario["empresa"], 2026, 12)
    for mes in range(1, 13):
        assert services._quantidade_aplicavel(registros, _idx(2026, mes)) == real[mes], mes


# ---------------------------------------------------------------------------
# Registrar
# ---------------------------------------------------------------------------


def test_registrar_com_inicio_em_mes_encerrado_e_recusado_e_nada_e_gravado(cenario):
    _encerrar(cenario, mes=3)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        _dependentes(cenario, 2, date(2026, 3, 1))

    assert "03/2026" in str(erro.value)
    assert "Reabra" in str(erro.value)
    assert _fotografia(cenario["empresa"]) == antes


def test_registrar_antes_de_mes_encerrado_com_vigencia_aberta_alcanca_o_mes_e_e_recusado(cenario):
    _encerrar(cenario, mes=3)
    antes = _fotografia(cenario["empresa"])
    with pytest.raises(MesCaixaEncerrado):
        _dependentes(cenario, 2, date(2026, 1, 1))
    assert _fotografia(cenario["empresa"]) == antes


def test_registrar_com_inicio_posterior_ao_ultimo_mes_encerrado_e_aceito(cenario):
    _encerrar(cenario, mes=3)
    _encerrar(cenario, mes=5)
    registro = _dependentes(cenario, 2, date(2026, 6, 1))
    assert DependentesCarneLeaoCliente.objects.filter(pk=registro.pk).exists()


def test_registrar_depois_de_reabrir_o_mes_e_aceito(cenario):
    _encerrar(cenario, mes=3)
    with pytest.raises(MesCaixaEncerrado):
        _dependentes(cenario, 2, date(2026, 3, 1))
    _reabrir(cenario, mes=3)
    assert _dependentes(cenario, 2, date(2026, 3, 1)).pk


def test_mes_encerrado_so_de_ano_anterior_nao_trava_registro_do_ano_seguinte(cenario):
    _encerrar(cenario, ano=2025, mes=12)
    assert _dependentes(cenario, 2, date(2026, 1, 1)).pk


def test_registro_com_fim_no_proximo_registro_nao_alcanca_ano_seguinte(cenario):
    """Existe vigência desde 2026-01 (q=1). Registrar q=3 em 2025-01 só muda
    2025 (até o registro de 2026-01): mês encerrado de 2026 não é alcançado,
    mesmo com encadeamento (que não atravessa o ano-calendário)."""
    _dependentes(cenario, 1, date(2026, 1, 1))
    _encerrar(cenario, ano=2026, mes=2)
    assert _dependentes(cenario, 3, date(2025, 1, 1)).pk


def test_encadeamento_dentro_do_ano_alcanca_meses_seguintes_ate_dezembro(cenario):
    """Conservador por desenho: registrar em 02/2026 com fim em 05/2026 muda a
    dedução de fev-abr, e o carnê-leão de 08/2026 (encerrado) depende do
    encadeamento daqueles meses. Recusa; 01/2027 já é outro ano-calendário."""
    _dependentes(cenario, 1, date(2026, 1, 1))
    _dependentes(cenario, 1, date(2026, 5, 1))
    _encerrar(cenario, ano=2026, mes=8)
    with pytest.raises(MesCaixaEncerrado) as erro:
        _dependentes(cenario, 3, date(2026, 2, 1))
    assert "08/2026" in str(erro.value)


def test_encadeamento_nao_atravessa_a_virada_do_ano(cenario):
    _dependentes(cenario, 1, date(2026, 1, 1))
    _dependentes(cenario, 1, date(2026, 5, 1))
    _encerrar(cenario, ano=2027, mes=1)
    assert _dependentes(cenario, 3, date(2026, 2, 1)).pk


def test_registrar_a_mesma_quantidade_que_ja_vale_nao_muda_nada_e_e_aceito(cenario):
    _dependentes(cenario, 2, date(2026, 1, 1))
    _encerrar(cenario, mes=3)
    assert _dependentes(cenario, 2, date(2026, 2, 1)).pk


def test_fechamento_de_outra_empresa_nao_trava(cenario):
    _encerrar(cenario, mes=3, empresa=cenario["empresa_irma"])
    assert _dependentes(cenario, 2, date(2026, 1, 1)).pk


def test_mensagem_nomeia_o_primeiro_mes_encerrado_alcancado(cenario):
    _encerrar(cenario, mes=9)
    _encerrar(cenario, mes=4)
    with pytest.raises(MesCaixaEncerrado) as erro:
        _dependentes(cenario, 2, date(2026, 1, 1))
    assert "04/2026" in str(erro.value)


# ---------------------------------------------------------------------------
# Retificar
# ---------------------------------------------------------------------------


def test_retificar_registro_que_cobre_mes_encerrado_e_recusado_e_depois_de_reabrir_passa(cenario):
    a = _dependentes(cenario, 1, date(2026, 1, 1))
    _dependentes(cenario, 3, date(2026, 6, 1))
    _encerrar(cenario, mes=3)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        retificar_dependentes_carne_leao(a, quantidade=5, retificado_por=cenario["gestor"])

    assert "03/2026" in str(erro.value)
    assert _fotografia(cenario["empresa"]) == antes
    a.refresh_from_db()
    assert a.quantidade == 1

    _reabrir(cenario, mes=3)
    retificar_dependentes_carne_leao(a, quantidade=5, retificado_por=cenario["gestor"])
    a.refresh_from_db()
    assert a.quantidade == 5


def test_retificar_registro_posterior_ao_mes_encerrado_e_aceito(cenario):
    _dependentes(cenario, 1, date(2026, 1, 1))
    b = _dependentes(cenario, 3, date(2026, 6, 1))
    _encerrar(cenario, mes=3)
    retificar_dependentes_carne_leao(b, quantidade=4, retificado_por=cenario["gestor"])
    b.refresh_from_db()
    assert b.quantidade == 4


def test_retificar_para_a_mesma_quantidade_e_aceito_mesmo_com_mes_encerrado(cenario):
    a = _dependentes(cenario, 2, date(2026, 1, 1))
    _encerrar(cenario, mes=3)
    retificar_dependentes_carne_leao(a, quantidade=2, retificado_por=cenario["gestor"])


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_api_registrar_e_retificar_em_mes_encerrado_dao_409_e_nada_e_gravado(cenario):
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    registro = _dependentes(cenario, 1, date(2026, 1, 1))
    _encerrar(cenario, mes=3)
    antes = _fotografia(cenario["empresa"])
    url_lista = _url("dependentes-carne-leao", cenario["empresa"].id)
    url_retificar = _url("dependentes-carne-leao-retificar", cenario["empresa"].id, registro.id)

    criar = gestor.post(
        url_lista,
        data=json.dumps({"quantidade": 2, "competencia_inicio": "2026-02-01"}),
        content_type="application/json",
    )
    retificar = gestor.patch(
        url_retificar, data=json.dumps({"quantidade": 3}), content_type="application/json"
    )

    assert criar.status_code == 409
    assert "03/2026" in criar.json()["detail"]
    assert retificar.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes

    _reabrir(cenario, mes=3)
    assert (
        gestor.post(
            url_lista,
            data=json.dumps({"quantidade": 2, "competencia_inicio": "2026-02-01"}),
            content_type="application/json",
        ).status_code
        == 201
    )
    assert (
        gestor.patch(
            url_retificar, data=json.dumps({"quantidade": 3}), content_type="application/json"
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Concorrência (transaction=True)
# ---------------------------------------------------------------------------


def _pausando_dependentes(acao_alvo):
    """Pausa DENTRO da transação de registrar dependentes (a trilha é
    importada por `carne_leao`, não por `services`)."""
    dentro, liberar = threading.Event(), threading.Event()
    original = carne_leao.registrar

    def _registrar(*args, **kwargs):
        if kwargs.get("acao") == acao_alvo:
            dentro.set()
            assert liberar.wait(timeout=_TIMEOUT_DE_JOIN), "pausa nunca liberada"
        return original(*args, **kwargs)

    @contextlib.contextmanager
    def _ctx():
        try:
            with mock.patch.object(carne_leao, "registrar", _registrar):
                yield dentro, liberar
        finally:
            liberar.set()

    return _ctx()


@pytest.mark.django_db(transaction=True)
def test_encerramento_em_andamento_faz_o_registro_de_dependentes_esperar_e_ser_recusado():
    """Mês sem linha: o fechamento cria a linha. Sem o lock dos dependentes, o
    registro leria "nenhum mês encerrado", o fechamento comitaria, e o
    registro seria gravado depois, alterando mês encerrado."""
    c = _cenario_commitado()
    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "fechamento nunca chegou à pausa"

        registrar_thread, res_registro = _rodar_em_thread(
            lambda: registrar_dependentes_carne_leao(
                empresa=c["empresa"],
                quantidade=2,
                competencia_inicio=date(2026, 1, 1),
                criado_por=c["gestor"],
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert registrar_thread.is_alive(), "o registro não esperou o fechamento em andamento"
        assert not DependentesCarneLeaoCliente.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(fechar, registrar_thread)

    assert "erro" not in res_fechar, res_fechar
    assert isinstance(res_registro.get("erro"), MesCaixaEncerrado), res_registro
    assert not DependentesCarneLeaoCliente.objects.filter(empresa=c["empresa"]).exists()


@pytest.mark.django_db(transaction=True)
def test_registro_de_dependentes_em_andamento_faz_o_encerramento_esperar_e_fechar_depois():
    c = _cenario_commitado()
    with _pausando_dependentes("dependentes_carne_leao.registrado") as (dentro, liberar):
        registrar_thread, res_registro = _rodar_em_thread(
            lambda: registrar_dependentes_carne_leao(
                empresa=c["empresa"],
                quantidade=2,
                competencia_inicio=date(2026, 1, 1),
                criado_por=c["gestor"],
            )
        )
        assert dentro.wait(timeout=30), "registro nunca chegou à pausa"

        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
        )
        time.sleep(_PAUSA_CURTA)
        assert fechar.is_alive(), "o fechamento não esperou o registro de dependentes"
        assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(registrar_thread, fechar)

    assert "erro" not in res_registro, res_registro
    assert "erro" not in res_fechar, res_fechar
    assert DependentesCarneLeaoCliente.objects.filter(empresa=c["empresa"]).count() == 1
    assert FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_corrida_repetida_de_encerramento_e_dependentes_nunca_altera_mes_encerrado():
    """Oito corridas sem pausa artificial. O fechamento, já com os locks, conta
    os dependentes da empresa; o total final tem de ser IGUAL a essa contagem —
    se fosse maior, um registro teria comitado depois de o mês ser assumido pelo
    fechamento."""
    original = services.registrar
    visto = {}

    def _registrar(*args, **kwargs):
        if kwargs.get("acao") == "fechamento_mes_caixa.encerrado":
            visto[kwargs["detalhes"]["empresa_id"]] = DependentesCarneLeaoCliente.objects.filter(
                empresa_id=kwargs["detalhes"]["empresa_id"]
            ).count()
        return original(*args, **kwargs)

    with mock.patch.object(services, "registrar", _registrar):
        for _ in range(8):
            c = _cenario_commitado()
            barreira = threading.Barrier(2)

            def _registrar_dep(c=c, barreira=barreira):
                barreira.wait(timeout=30)
                return registrar_dependentes_carne_leao(
                    empresa=c["empresa"],
                    quantidade=2,
                    competencia_inicio=date(2026, 1, 1),
                    criado_por=c["gestor"],
                )

            def _fechar(c=c, barreira=barreira):
                barreira.wait(timeout=30)
                return encerrar_mes_caixa(
                    empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"]
                )

            td, rd = _rodar_em_thread(_registrar_dep)
            tf, rf = _rodar_em_thread(_fechar)
            _esperar(td, tf)

            assert "erro" not in rf, rf
            assert "erro" not in rd or isinstance(rd["erro"], MesCaixaEncerrado), rd
            final = DependentesCarneLeaoCliente.objects.filter(empresa=c["empresa"]).count()
            assert final == visto[c["empresa"].id], (final, visto)
            assert final == (0 if "erro" in rd else 1), rd


@pytest.mark.django_db(transaction=True)
def test_espera_pelo_lock_dos_dependentes_que_estoura_vira_409_de_dominio():
    c = _cenario_commitado()
    preso, liberar = threading.Event(), threading.Event()

    def _segurar():
        with transaction.atomic():
            services._adquirir_lock_dos_dependentes(empresa_id=c["empresa"].id, exclusivo=True)
            preso.set()
            assert liberar.wait(timeout=_TIMEOUT_DE_JOIN)

    segurando, res = _rodar_em_thread(_segurar)
    try:
        assert preso.wait(timeout=30)
        with pytest.raises(MesCaixaOcupado):
            registrar_dependentes_carne_leao(
                empresa=c["empresa"],
                quantidade=2,
                competencia_inicio=date(2026, 1, 1),
                criado_por=c["gestor"],
            )
        with pytest.raises(services.FechamentoMesCaixaTravado):
            encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
    finally:
        liberar.set()
        _esperar(segurando)
    assert "erro" not in res, res
    assert not DependentesCarneLeaoCliente.objects.filter(empresa=c["empresa"]).exists()
    assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()
