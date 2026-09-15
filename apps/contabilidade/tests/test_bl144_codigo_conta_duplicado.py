"""Achado R5-5 da auditoria DL-017, rodada 5 (BL-144 / DE-034).

`ContaListCreateView.perform_create` (`apps/contabilidade/views.py`) não
tinha `try` nenhum: `codigo` repetido na mesma empresa
(`Conta.Meta.constraints`, `codigo_unico_por_empresa`) derrubava com
`IntegrityError` cru, HTTP 500 — o erro mais comum de quem monta um plano
de contas. A integridade do dado NUNCA foi violada (a constraint sempre
segurou); o que quebrava era a RESPOSTA.

Medido pelo auditor, sob 4 conexões simultâneas com o mesmo `codigo`:
`500, 201, 500, 500`. Corrigido com `apps.core.restricoes.
restricao_como_400`, no mesmo molde de `erro_de_cnpj_duplicado_como_400`
(`apps.empresas.services`).
"""

import json
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-144", cnpj="88888888000199")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-144 Ltda", cnpj="88899900000111"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl144", email="gestor-bl144@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa}


def _cliente_autenticado(client, cenario):
    assert client.login(username="gestor-bl144", password="senha-forte-123")


def _post_conta(client, cenario, *, codigo, nome="Caixa"):
    corpo = {
        "codigo": codigo,
        "nome": nome,
        "tipo": TipoConta.ATIVO,
        "natureza": NaturezaConta.DEVEDORA,
    }
    return client.post(
        reverse("contabilidade:contas", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
    )


def test_codigo_repetido_na_mesma_empresa_retorna_400_nao_500(client, cenario):
    _cliente_autenticado(client, cenario)
    primeira = _post_conta(client, cenario, codigo="1")
    assert primeira.status_code == 201, (primeira.status_code, primeira.content)

    segunda = _post_conta(client, cenario, codigo="1", nome="Caixa Duplicado")

    assert segunda.status_code == 400, (segunda.status_code, segunda.content)
    assert Conta.objects.filter(empresa=cenario["empresa"], codigo="1").count() == 1
    assert "código" in segunda.json()["codigo"][0].lower()


def test_codigo_diferente_continua_gravando_sem_regressao(client, cenario):
    _cliente_autenticado(client, cenario)
    primeira = _post_conta(client, cenario, codigo="1")
    segunda = _post_conta(client, cenario, codigo="2", nome="Receita")

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 2


def test_codigo_repetido_em_empresa_diferente_continua_permitido(client, cenario):
    """Controle: a constraint é por (empresa, codigo) — o mesmo código em
    OUTRA empresa não é duplicidade nenhuma. A correção não pode ter
    apertado esse caso."""
    _cliente_autenticado(client, cenario)
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"], razao_social="Outra Empresa Ltda", cnpj="99900011000122"
    )
    Conta.objects.create(
        empresa=outra_empresa,
        codigo="1",
        nome="Caixa de outra empresa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    resposta = _post_conta(client, cenario, codigo="1")

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)


@pytest.mark.django_db(transaction=True)
def test_quatro_criacoes_simultaneas_do_mesmo_codigo_nunca_500():
    """Reprodução da medição do auditor: 4 conexões simultâneas com o
    MESMO `codigo`, pela API. Antes: `500, 201, 500, 500`. Agora: exatamente
    um 201 (ou 400, se a corrida se resolver diferente — nunca 500) e o
    restante 400; sempre exatamente UMA conta gravada com aquele código.

    `django_db(transaction=True)` (sobrepõe o `pytestmark` do módulo, que é
    `django_db` simples): necessário para as threads reais comitarem e se
    enxergarem — mesmo padrão de
    `apps.empresas.tests.test_api.test_criar_empresa_via_api_com_corrida_...`.
    """
    escritorio = Escritorio.objects.create(nome="Escritório BL-144 Corrida", cnpj="10101010000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-144 Corrida Ltda", cnpj="10111213000144"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl144-corrida",
        email="gestor-bl144-corrida@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(4)
    resultados = {}

    def _postar(chave):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-bl144-corrida", password="senha-forte-123")
            barreira.wait()
            resposta = cliente.post(
                reverse("contabilidade:contas", args=[empresa.id]),
                data=json.dumps(
                    {
                        "codigo": "1",
                        "nome": f"Caixa {chave}",
                        "tipo": TipoConta.ATIVO,
                        "natureza": NaturezaConta.DEVEDORA,
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
    assert Conta.objects.filter(empresa=empresa, codigo="1").count() == 1
