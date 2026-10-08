"""DL-070 (BL-648, frente B): a lista de empresas não faz consulta por linha.

Contrato (plano DL-070, critério 5): `GET /empresas/api/empresas/` faz número
de consultas CONSTANTE em relação à quantidade de empresas, e o `regime_atual`
devolvido é o mesmo de antes da correção: o regime do período vigente
(`vigencia_fim` nulo), ou `None` quando não há período vigente. Antes, cada
empresa disparava uma consulta própria em `EmpresaSerializer.get_regime_atual`.

Dados sintéticos: razões sociais e CNPJs fictícios.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL070 lista", cnpj="33333333000133")


@pytest.fixture
def administrador(escritorio, client):
    usuario = get_user_model().objects.create_user(
        username="admin-dl070", email="admin-dl070@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ADMINISTRADOR
    )
    assert client.login(username="admin-dl070", password=SENHA)
    return usuario


def _empresa(escritorio, indice, razao="Empresa sintética Ltda"):
    # CNPJ sintético de 14 dígitos, único por `indice`.
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social=f"{razao} {indice:02d}",
        cnpj=f"9{indice:013d}",
    )


def _empresa_com_regime_vigente(escritorio, indice):
    empresa = _empresa(escritorio, indice)
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio="2024-01-01",
    )
    return empresa


def _consultas_e_corpo(client, url):
    with CaptureQueriesContext(connection) as contexto:
        resposta = client.get(url)
    assert resposta.status_code == 200, resposta.content
    return len(contexto.captured_queries), resposta.json()


def test_lista_faz_o_mesmo_numero_de_consultas_com_2_e_com_20_empresas(
    client, escritorio, administrador
):
    url = reverse("empresas:api-lista")
    # A primeira requisição depois do login grava a sessão (UPDATE em
    # `django_session` e SAVEPOINT): custo fixo, não por linha. Aquecer antes
    # de medir compara só o que cresce com o número de empresas.
    client.get(url)
    for indice in range(1, 3):
        _empresa_com_regime_vigente(escritorio, indice)
    consultas_com_2, corpo_com_2 = _consultas_e_corpo(client, url)

    for indice in range(3, 21):
        _empresa_com_regime_vigente(escritorio, indice)
    consultas_com_20, corpo_com_20 = _consultas_e_corpo(client, url)

    assert len(corpo_com_2) == 2
    assert len(corpo_com_20) == 20
    assert consultas_com_20 == consultas_com_2, (
        f"consultas por linha: {consultas_com_2} com 2 empresas, {consultas_com_20} com 20"
    )


def test_regime_atual_da_lista_e_o_esperado_e_o_mesmo_do_detalhe(client, escritorio, administrador):
    # Cada caso cobre um formato de histórico que o `.first()` antigo tratava.
    vigente = _empresa(escritorio, 1, razao="Empresa com regime vigente")
    HistoricoRegimeTributario.objects.create(
        empresa=vigente,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio="2023-01-01",
    )

    sem_regime = _empresa(escritorio, 2, razao="Empresa sem regime")

    encerrada_e_vigente = _empresa(escritorio, 3, razao="Empresa com histórico encerrado")
    HistoricoRegimeTributario.objects.create(
        empresa=encerrada_e_vigente,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio="2019-01-01",
        vigencia_fim="2021-12-31",
    )
    HistoricoRegimeTributario.objects.create(
        empresa=encerrada_e_vigente,
        regime=RegimeTributario.LUCRO_REAL,
        vigencia_inicio="2022-01-01",
    )

    so_encerrada = _empresa(escritorio, 4, razao="Empresa só com período encerrado")
    HistoricoRegimeTributario.objects.create(
        empresa=so_encerrada,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio="2019-01-01",
        vigencia_fim="2020-12-31",
    )

    esperado = {
        vigente.pk: RegimeTributario.LUCRO_PRESUMIDO,
        sem_regime.pk: None,
        encerrada_e_vigente.pk: RegimeTributario.LUCRO_REAL,
        so_encerrada.pk: None,
    }

    _, corpo = _consultas_e_corpo(client, reverse("empresas:api-lista"))
    regime_na_lista = {item["id"]: item["regime_atual"] for item in corpo}

    assert regime_na_lista == esperado

    # O detalhe não usa o prefetch: é a referência do comportamento anterior.
    for empresa_pk, regime_esperado in esperado.items():
        detalhe = client.get(reverse("empresas:api-detalhe", args=[empresa_pk]))
        assert detalhe.status_code == 200, detalhe.content
        assert detalhe.json()["regime_atual"] == regime_esperado
