"""DL-038, critério 4 do plano — R5: a contabilidade por partidas dobradas
recusa, no servidor, TODA rota (API e tela) para uma empresa em modo
`livro_caixa`, com a MESMA mensagem, em um ponto só do código.

A prova é uma VARREDURA DERIVADA das rotas registradas — não uma lista
escrita à mão. Este teste lê `apps.contabilidade.urls.urlpatterns` e
`apps.contabilidade.urls_web.urlpatterns` diretamente (os mesmos módulos que
`config/urls.py` inclui), extrai TODO padrão com `empresa_id` no caminho, e
bate em cada um com uma empresa em modo livro-caixa — sem hardcodar nome de
view nem de rota. Uma rota nova, adicionada amanhã sem o decorador/mixin de
recusa, reprova este teste automaticamente, porque ele nunca deixa de
enumerar tudo o que existe hoje.

Os parâmetros de caminho que não são `empresa_id` (lancamento_id, conta_id,
ano, mes) recebem `1` — nenhum deles chega a ser usado: tanto
`EmpresaEscopadaContabilMixin.get_empresa()` (API) quanto o decorador
`_sem_contabilidade_para_livro_caixa` (tela) resolvem a empresa e recusam
ANTES de qualquer outro parâmetro do caminho ser lido (ver os comentários
nos dois pontos de origem, `apps/contabilidade/views.py` e
`apps/contabilidade/views_web.py`).
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade import urls as contabilidade_urls_api
from apps.contabilidade import urls_web as contabilidade_urls_web
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _rotas_com_empresa_id(modulo_urls, app_name):
    """Deriva, do PRÓPRIO `urlpatterns` do módulo, o nome de rota
    namespaced e os nomes de TODOS os parâmetros de caminho de cada
    padrão que inclui `empresa_id` — nenhuma lista escrita à mão."""
    rotas = []
    for padrao in modulo_urls.urlpatterns:
        nomes_de_parametro = tuple(padrao.pattern.converters)
        if "empresa_id" in nomes_de_parametro:
            rotas.append((f"{app_name}:{padrao.name}", nomes_de_parametro))
    return rotas


ROTAS_API = _rotas_com_empresa_id(contabilidade_urls_api, "contabilidade")
ROTAS_WEB = _rotas_com_empresa_id(contabilidade_urls_web, "contabilidade_web")


# Prova de que a derivação encontrou algo de verdade — se `urls.py`/
# `urls_web.py` for esvaziado por engano, o teste abaixo falha alto em vez
# de "passar" varrendo zero rotas (vacuidade).
def test_a_derivacao_encontrou_as_treze_rotas_web_e_as_dez_da_api():
    assert len(ROTAS_API) == 10, ROTAS_API
    assert len(ROTAS_WEB) == 13, ROTAS_WEB


@pytest.fixture
def empresa_livro_caixa():
    escritorio = Escritorio.objects.create(
        nome="Escritório Livro-Caixa DL-038", cnpj="80808080000180"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-livro-caixa-dl038",
        email="gestor-livro-caixa-dl038@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Livro-Caixa Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    return usuario, empresa


def _kwargs_para(nomes_de_parametro, empresa_id):
    # Todo parâmetro que não é `empresa_id` recebe 1 — nunca chega a ser
    # usado (ver o docstring do módulo).
    return {nome: (empresa_id if nome == "empresa_id" else 1) for nome in nomes_de_parametro}


@pytest.mark.parametrize("rota,nomes_de_parametro", ROTAS_API, ids=[r[0] for r in ROTAS_API])
def test_toda_rota_da_api_recusa_empresa_em_livro_caixa(
    client, empresa_livro_caixa, rota, nomes_de_parametro
):
    usuario, empresa = empresa_livro_caixa
    client.login(username="gestor-livro-caixa-dl038", password="senha-forte-123")
    endereco = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, empresa.pk))

    resposta = client.get(endereco)
    if resposta.status_code == 405:  # rota só aceita POST (ações sem leitura)
        resposta = client.post(endereco, data=json.dumps({}), content_type="application/json")

    assert resposta.status_code == 400, (rota, resposta.status_code, resposta.content)
    corpo = resposta.json()
    assert corpo.get("empresa") == [MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA], (rota, corpo)


@pytest.mark.parametrize("rota,nomes_de_parametro", ROTAS_WEB, ids=[r[0] for r in ROTAS_WEB])
def test_toda_rota_da_tela_recusa_empresa_em_livro_caixa(
    client, empresa_livro_caixa, rota, nomes_de_parametro
):
    usuario, empresa = empresa_livro_caixa
    client.login(username="gestor-livro-caixa-dl038", password="senha-forte-123")
    endereco = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, empresa.pk))

    resposta = client.get(endereco)
    if resposta.status_code == 405:
        resposta = client.post(endereco, data={})

    assert resposta.status_code == 403, (rota, resposta.status_code)
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode(), rota


def test_a_mensagem_da_api_e_da_tela_e_identica(client, empresa_livro_caixa):
    # A prova mais direta de "um ponto só": as duas pontas (API via
    # EmpresaEscopadaContabilMixin, tela via _sem_contabilidade_para_
    # livro_caixa) chamam a MESMA `apps.empresas.services.
    # recusar_se_livro_caixa`, então a string tem que ser IDÊNTICA — não
    # só "parecida" — nas duas.
    usuario, empresa = empresa_livro_caixa
    client.login(username="gestor-livro-caixa-dl038", password="senha-forte-123")

    resposta_api = client.get(reverse("contabilidade:diario", kwargs={"empresa_id": empresa.pk}))
    resposta_web = client.get(
        reverse("contabilidade_web:diario", kwargs={"empresa_id": empresa.pk})
    )

    (mensagem_api,) = resposta_api.json()["empresa"]
    assert mensagem_api == MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta_web.content.decode()
