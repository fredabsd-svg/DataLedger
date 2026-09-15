"""Achado R5-5 da auditoria DL-017, rodada 5 (BL-144 / DE-034).

`EstabelecimentoListCreateView.perform_create` (`apps/empresas/views.py`)
JÁ envolvia a gravação em `erro_de_cnpj_duplicado_como_400()` — a defesa
existia, na MESMA função, só para a unicidade de CNPJ, e não para
`uma_matriz_por_empresa` (`Estabelecimento.Meta.constraints`, quatro
linhas abaixo da de CNPJ no modelo). Uma segunda matriz para a mesma
empresa derrubava com `IntegrityError` cru, HTTP 500.

Corrigido acrescentando `apps.core.restricoes.restricao_como_400` no MESMO
`with` que já trata o CNPJ.
"""

import json
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-144-B", cnpj="12121212000133")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-144-B Ltda", cnpj="12131415000166"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl144b",
        email="gestor-bl144b@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa}


def _cliente_autenticado(client, cenario):
    assert client.login(username="gestor-bl144b", password="senha-forte-123")


def _post_estabelecimento(client, cenario, *, tipo, cnpj, nome="Unidade"):
    corpo = {"tipo": tipo, "nome": nome, "cnpj": cnpj}
    return client.post(
        reverse("empresas:api-estabelecimentos", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
    )


def test_segunda_matriz_da_mesma_empresa_retorna_400_nao_500(client, cenario):
    _cliente_autenticado(client, cenario)
    primeira = _post_estabelecimento(
        client, cenario, tipo=TipoEstabelecimento.MATRIZ, cnpj="11222333000181", nome="Matriz"
    )
    assert primeira.status_code == 201, (primeira.status_code, primeira.content)

    segunda = _post_estabelecimento(
        client, cenario, tipo=TipoEstabelecimento.MATRIZ, cnpj="22333444000181", nome="Outra Matriz"
    )

    assert segunda.status_code == 400, (segunda.status_code, segunda.content)
    assert (
        Estabelecimento.objects.filter(
            empresa=cenario["empresa"], tipo=TipoEstabelecimento.MATRIZ
        ).count()
        == 1
    )


def test_segunda_filial_da_mesma_empresa_continua_permitida_sem_regressao(client, cenario):
    """Controle: a constraint só limita MATRIZ — filiais não têm teto. A
    correção não pode ter apertado esse caso."""
    _cliente_autenticado(client, cenario)
    primeira = _post_estabelecimento(
        client, cenario, tipo=TipoEstabelecimento.FILIAL, cnpj="33444555000262", nome="Filial 1"
    )
    segunda = _post_estabelecimento(
        client, cenario, tipo=TipoEstabelecimento.FILIAL, cnpj="44555666000343", nome="Filial 2"
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert (
        Estabelecimento.objects.filter(
            empresa=cenario["empresa"], tipo=TipoEstabelecimento.FILIAL
        ).count()
        == 2
    )


def test_matriz_em_empresa_diferente_continua_permitida(client, cenario):
    """Controle: a constraint é por empresa — cada empresa pode ter a
    própria matriz."""
    _cliente_autenticado(client, cenario)
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Outra Empresa BL-144-B",
        cnpj="55666777000105",
    )
    Estabelecimento.objects.create(
        empresa=outra_empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz de outra empresa",
        cnpj="66777888000106",
    )

    resposta = _post_estabelecimento(
        client, cenario, tipo=TipoEstabelecimento.MATRIZ, cnpj="55666777000424"
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)


@pytest.mark.django_db(transaction=True)
def test_quatro_criacoes_simultaneas_de_matriz_nunca_500():
    """Mesma medição do R5-5, aplicada à constraint de matriz: 4 conexões
    simultâneas tentando criar a MATRIZ da mesma empresa. Exatamente uma
    grava (201); as demais recusam com 400 — nunca 500."""
    escritorio = Escritorio.objects.create(
        nome="Escritório BL-144-B Corrida", cnpj="20202020000144"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-144-B Corrida Ltda", cnpj="20212223000188"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl144b-corrida",
        email="gestor-bl144b-corrida@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(4)
    resultados = {}
    # Cada thread usa um CNPJ diferente (a matriz não compete por CNPJ,
    # compete por SER a matriz da mesma empresa) — CNPJs alfanuméricos
    # válidos, canônicos, um por thread.
    cnpjs = {
        "A": "66777888000505",
        "B": "AB11111100AA91",
        "C": "AB22222200BB28",
        "D": "AB33333300CC64",
    }

    def _postar(chave):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-bl144b-corrida", password="senha-forte-123")
            barreira.wait()
            resposta = cliente.post(
                reverse("empresas:api-estabelecimentos", args=[empresa.id]),
                data=json.dumps(
                    {
                        "tipo": TipoEstabelecimento.MATRIZ,
                        "nome": f"Matriz {chave}",
                        "cnpj": cnpjs[chave],
                    }
                ),
                content_type="application/json",
            )
            resultados[chave] = resposta.status_code
        finally:
            connection.close()

    threads = [threading.Thread(target=_postar, args=(chave,)) for chave in "ABCD"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert set(resultados.values()) <= {201, 400}, resultados
    assert list(resultados.values()).count(201) == 1, resultados
    assert (
        Estabelecimento.objects.filter(empresa=empresa, tipo=TipoEstabelecimento.MATRIZ).count()
        == 1
    )
