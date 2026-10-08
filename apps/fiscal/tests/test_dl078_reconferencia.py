"""DL-078 — testes da reconferência (R4 e R5), escritos pelo auditor e integrados pelo arquiteto.

Pela regra de parada do §3.1 não há nova rodada de correção: as duas lacunas de teste da
reconferência (docs/auditorias/2026-10-08-dl-078-reconferencia.md) fecham com os casos do
próprio auditor, que derrubam os mutantes N8, N10 (permissão da rota de limpar) e N11
(`hoje()` em UTC em vez da data de São Paulo). Este módulo NÃO usa a fixture
`relogio_do_teste`: o ponto aqui é o relógio real.
"""

import json
from datetime import UTC, date, datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.fiscal import tomadas as servico
from apps.fiscal.escrituracao import EntradaInvalidaEscrituracao
from apps.fiscal.tests.suporte_tomada_dl078 import T2, tomada_efetivada
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario(escritorio, papel, nome):
    usuario = get_user_model().objects.create_user(
        username=nome, email=f"{nome}@exemplo.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _congelar(monkeypatch, instante_utc):
    monkeypatch.setattr(timezone, "now", lambda: instante_utc)


@pytest.fixture
def nota(escritorio_a, usuario_gestor_a, empresa_a2):
    return tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9101,
        T2,
        tp_ret_issqn="1",
        v_ret_irrf="15.00",
        d_compet="2026-10-05",
        dh_emi="2026-10-05T09:00:00-03:00",
        v_liq="985.00",
    )


@pytest.fixture
def nota_com_data(monkeypatch, nota, usuario_gestor_a):
    _congelar(monkeypatch, datetime(2026, 12, 15, 15, 0, 0, tzinfo=UTC))
    servico.informar_data_pagamento(nota, date(2026, 10, 6), "pagou", usuario_gestor_a)
    return nota


# ---------- R5: a janela usa a data de São Paulo, não a de UTC ----------


@pytest.mark.parametrize(
    "instante_utc,hoje_esperado",
    [
        (datetime(2026, 10, 9, 2, 59, 59, tzinfo=UTC), date(2026, 10, 8)),  # 23:59:59 em SP
        (datetime(2026, 10, 9, 3, 0, 0, tzinfo=UTC), date(2026, 10, 9)),  # 00:00:00 em SP
        (datetime(2026, 10, 9, 0, 0, 0, tzinfo=UTC), date(2026, 10, 8)),  # 21:00 em SP
        (datetime(2027, 1, 1, 2, 59, 0, tzinfo=UTC), date(2026, 12, 31)),
    ],
)
def test_hoje_e_a_data_local_de_sao_paulo(monkeypatch, instante_utc, hoje_esperado):
    _congelar(monkeypatch, instante_utc)
    assert servico.hoje() == hoje_esperado


def test_virada_do_dia_recusa_amanha_e_aceita_hoje(monkeypatch, nota, usuario_gestor_a):
    # 23:59:59 de 08/10 em São Paulo (UTC já é 09/10): 09/10 ainda é futuro.
    _congelar(monkeypatch, datetime(2026, 10, 9, 2, 59, 59, tzinfo=UTC))
    with pytest.raises(EntradaInvalidaEscrituracao):
        servico.informar_data_pagamento(nota, date(2026, 10, 9), "m", usuario_gestor_a)
    servico.informar_data_pagamento(nota, date(2026, 10, 8), "m", usuario_gestor_a)
    # 00:00:00 de 09/10 em São Paulo: 09/10 passa a ser hoje; 10/10 continua futuro.
    _congelar(monkeypatch, datetime(2026, 10, 9, 3, 0, 0, tzinfo=UTC))
    servico.informar_data_pagamento(nota, date(2026, 10, 9), "m2", usuario_gestor_a)
    with pytest.raises(EntradaInvalidaEscrituracao):
        servico.informar_data_pagamento(nota, date(2026, 10, 10), "m3", usuario_gestor_a)


# ---------- R4: limpar a data exige papel de escriturar, na API e na tela ----------


def _url_api(empresa_id, escrituracao_id):
    return reverse(
        "fiscal_api:tomada_data_pagamento_limpar",
        kwargs={"empresa_id": empresa_id, "escrituracao_id": escrituracao_id},
    )


def _url_web(empresa_id, escrituracao_id):
    return reverse("fiscal_web:tomada_data_pagamento_limpar", args=[empresa_id, escrituracao_id])


@pytest.mark.parametrize(
    "papel,esperado",
    [
        (Papel.CLIENTE, 403),
        (Papel.PARALEGAL, 403),
        (Papel.ANALISTA, 200),
        (Papel.FINANCEIRO, 200),
        (Papel.ADMINISTRADOR, 200),
    ],
)
def test_api_limpar_exige_papel_de_escriturar(
    client, nota_com_data, empresa_a2, escritorio_a, papel, esperado
):
    client.force_login(_usuario(escritorio_a, papel, f"api-{papel}"))
    resposta = client.post(
        _url_api(empresa_a2.pk, nota_com_data.pk),
        data=json.dumps({"motivo": "engano"}),
        content_type="application/json",
    )
    assert resposta.status_code == esperado, resposta.content
    nota_com_data.refresh_from_db()
    assert (nota_com_data.data_pagamento is None) == (esperado == 200)


@pytest.mark.parametrize(
    "papel,esperado",
    [
        (Papel.CLIENTE, 403),
        (Papel.PARALEGAL, 403),
        (Papel.ANALISTA, 302),
        (Papel.FINANCEIRO, 302),
        (Papel.ADMINISTRADOR, 302),
    ],
)
def test_tela_limpar_exige_papel_de_escriturar(
    client, nota_com_data, empresa_a2, escritorio_a, papel, esperado
):
    client.force_login(_usuario(escritorio_a, papel, f"web-{papel}"))
    resposta = client.post(_url_web(empresa_a2.pk, nota_com_data.pk), {"motivo": "engano"})
    assert resposta.status_code == esperado
    nota_com_data.refresh_from_db()
    assert (nota_com_data.data_pagamento is None) == (esperado == 302)
