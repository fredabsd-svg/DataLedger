"""Achado A9 da auditoria DL-017, rodada 4 (BL-133):
`HistoricoRegimeTributarioListCreateView.post` (apps/empresas/views.py)
usava `date.fromisoformat` direto sobre `vigencia_inicio`, sem gramática
nem checagem de tipo — a mesma classe do R3-3 (DE-030), num campo de data.

Medido pelo auditor, pela API real:

    vigencia_inicio = "2026-W01-1"  -> 201, gravado 2025-12-29 (reinterpretado)
    vigencia_inicio = 20260101      -> 500 (TypeError não tratado)
    vigencia_inicio = "20260101"    -> 201, gravado 2026-01-01

Corrigido com `apps.core.datas.para_data` — o mesmo módulo que
`apps.contabilidade.views._periodo_obrigatorio` usa para `inicio`/`fim`
(BL-133: não duplicar a regra entre os dois apps, DE-026).
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório BL-133", cnpj="66666666000177")


@pytest.fixture
def empresa(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-133 Ltda", cnpj="66677788000199"
    )


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-bl133", email="gestor-bl133@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def _url(empresa):
    return reverse("empresas:api-regime-tributario", args=[empresa.id])


def _sem_nada_gravado():
    return not HistoricoRegimeTributario.objects.exists()


# ---------------------------------------------------------------------------
# A tabela do auditor, refeita: os quatro valores medidos.
# ---------------------------------------------------------------------------


def test_data_de_semana_iso_nao_e_reinterpretada_em_silencio(client, gestor, empresa):
    """Antes: `"2026-W01-1"` era aceito por `date.fromisoformat` e
    convertido para `2025-12-29` — outro ano, outro mês, outro dia — sem
    aviso nenhum. Agora: recusado com 400, nada gravado."""
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {"regime": RegimeTributario.SIMPLES_NACIONAL, "vigencia_inicio": "2026-W01-1"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


def test_vigencia_inicio_como_numero_json_nunca_500(client, gestor, empresa):
    """Antes: `20260101` (número JSON) derrubava a view com `TypeError:
    fromisoformat: argument must be str`, sem captura — 500 cru. Agora:
    400, nada gravado."""
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {"regime": RegimeTributario.SIMPLES_NACIONAL, "vigencia_inicio": 20260101},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


def test_vigencia_inicio_sem_hifen_e_recusada(client, gestor, empresa):
    """Antes: `"20260101"` (8 dígitos, sem separador) era aceito por
    `date.fromisoformat` mesmo fora do contrato anunciado (AAAA-MM-DD).
    Agora: recusado por não casar a gramática estrita, 400."""
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {"regime": RegimeTributario.SIMPLES_NACIONAL, "vigencia_inicio": "20260101"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


def test_vigencia_inicio_com_hora_continua_recusada_sem_regressao(client, gestor, empresa):
    """Controle: já era 400 antes da correção (`date.fromisoformat`
    recusa datetime com hora só quando o formato tem separador `T` no
    meio inesperado para `date` — mantido)."""
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {
            "regime": RegimeTributario.SIMPLES_NACIONAL,
            "vigencia_inicio": "2026-01-01T00:00:00",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


def test_vigencia_inicio_valida_continua_gravando_a_data_exata(client, gestor, empresa):
    """Controle positivo: o caminho normal (texto AAAA-MM-DD válido)
    continua funcionando, e a data gravada é exatamente a digitada."""
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {"regime": RegimeTributario.SIMPLES_NACIONAL, "vigencia_inicio": "2026-01-01"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    registro = HistoricoRegimeTributario.objects.get(empresa=empresa)
    assert registro.vigencia_inicio == date(2026, 1, 1)


@pytest.mark.parametrize(
    "vigencia_invalida",
    [
        None,
        True,
        1.5,
        "２０２６-０１-０１",  # dígitos fullwidth (mesma lição do R2-7/R3-6)
        "2026-02-30",  # formato certo, data inexistente
    ],
)
def test_outros_formatos_invalidos_de_vigencia_inicio_nunca_500(
    client, gestor, empresa, vigencia_invalida
):
    client.login(username="gestor-bl133", password="senha-forte-123")

    resposta = client.post(
        _url(empresa),
        {"regime": RegimeTributario.SIMPLES_NACIONAL, "vigencia_inicio": vigencia_invalida},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (vigencia_invalida, resposta.status_code, resposta.content)
    assert _sem_nada_gravado()
