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

Achado B3 da auditoria rodada 1: a versão anterior deste arquivo tentava
GET primeiro e só tentava POST quando o GET devolvia 405 — para
`ContaListCreateView`/`LancamentoListCreateView` (que aceitam os DOIS
métodos), o GET já recusava com 400 (via `get_queryset()`), então o `if
405` nunca disparava e o POST — a porta que GRAVA — nunca era exercitado. A
mutação C05 (troca `self.get_empresa()` por `EmpresaEscopadaMixin.
get_empresa(self)` dentro de `LancamentoListCreateView.post`) sobrevivia à
suíte inteira por causa disso.

Correção: os métodos aceitos por CADA rota são DERIVADOS também — de um
DELETE de sonda (nenhuma rota deste conjunto aceita DELETE), lendo o
cabeçalho `Allow` que o Django/DRF sempre populam numa resposta 405. Cada
método aceito (GET, POST — HEAD/OPTIONS não são interessantes aqui) é
exercitado; para POST, confere-se ADICIONALMENTE que nada foi gravado.

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
from apps.contabilidade.models import Competencia, Conta, LancamentoContabil
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
def test_a_derivacao_encontrou_as_dezessete_rotas_web_e_as_treze_da_api():
    # DL-043 fatia 2 (servidor): três rotas novas na API (parâmetro
    # contábil: listar/criar e encerrar vigência; zeramento do resultado).
    # 10 -> 13 do lado da API, sem contrapartida na tela ainda.
    #
    # DL-043 fatia 3 (especialista-frontend): as MESMAS três operações
    # ganham tela — "parametros_contabeis" (listar/criar),
    # "parametro_contabil_encerrar" (encerrar vigência) e "zerar_resultado"
    # (prévia GET + execução POST). 13 -> 16 do lado da tela. Nenhuma rota
    # nova na API (já existiam desde a fatia 2) — só a CONTRAPARTIDA de
    # tela que faltava.
    #
    # DL-044 (3ª iteração): hub de relatórios ("relatorios/") — segundo
    # caminho para Diário/Razão/Balancete/Balanço/Conferência, mesma
    # permissão de leitura e mesma recusa de livro-caixa das cinco. Nenhuma
    # rota nova na API. 16 -> 17 do lado da tela.
    assert len(ROTAS_API) == 13, ROTAS_API
    assert len(ROTAS_WEB) == 17, ROTAS_WEB


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


def _metodos_aceitos(client, endereco):
    """Achado B3: os métodos que UMA rota aceita, DERIVADOS de verdade —
    nenhuma rota deste conjunto aceita DELETE, então uma sonda DELETE
    sempre dá 405, e o cabeçalho `Allow` (que Django e DRF sempre populam
    numa resposta 405) lista exatamente o que a rota aceita. Filtra
    HEAD/OPTIONS — não são interessantes para esta varredura (nenhum dos
    dois grava nem lê dado de negócio)."""
    resposta = client.delete(endereco)
    allow = resposta.headers.get("Allow", "")
    metodos = {m.strip().upper() for m in allow.split(",") if m.strip()}
    return metodos - {"HEAD", "OPTIONS"}


def _nada_foi_gravado(empresa):
    return (
        not Conta.objects.filter(empresa=empresa).exists()
        and not LancamentoContabil.objects.filter(empresa=empresa).exists()
        and not Competencia.objects.filter(empresa=empresa).exists()
    )


@pytest.mark.parametrize("rota,nomes_de_parametro", ROTAS_API, ids=[r[0] for r in ROTAS_API])
def test_toda_rota_da_api_recusa_empresa_em_livro_caixa_em_todo_metodo_aceito(
    client, empresa_livro_caixa, rota, nomes_de_parametro
):
    usuario, empresa = empresa_livro_caixa
    client.login(username="gestor-livro-caixa-dl038", password="senha-forte-123")
    endereco = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, empresa.pk))

    metodos = _metodos_aceitos(client, endereco)
    assert metodos, (rota, "nenhum método aceito detectado — sonda quebrada")

    for metodo in metodos:
        if metodo == "GET":
            resposta = client.get(endereco)
        elif metodo == "POST":
            resposta = client.post(endereco, data=json.dumps({}), content_type="application/json")
        else:
            continue

        assert resposta.status_code == 400, (rota, metodo, resposta.status_code, resposta.content)
        corpo = resposta.json()
        assert corpo.get("empresa") == [MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA], (
            rota,
            metodo,
            corpo,
        )
        if metodo == "POST":
            assert _nada_foi_gravado(empresa), (rota, metodo, "gravou mesmo recusando")


@pytest.mark.parametrize("rota,nomes_de_parametro", ROTAS_WEB, ids=[r[0] for r in ROTAS_WEB])
def test_toda_rota_da_tela_recusa_empresa_em_livro_caixa_em_todo_metodo_aceito(
    client, empresa_livro_caixa, rota, nomes_de_parametro
):
    usuario, empresa = empresa_livro_caixa
    client.login(username="gestor-livro-caixa-dl038", password="senha-forte-123")
    endereco = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, empresa.pk))

    metodos = _metodos_aceitos(client, endereco)
    assert metodos, (rota, "nenhum método aceito detectado — sonda quebrada")

    for metodo in metodos:
        if metodo == "GET":
            resposta = client.get(endereco)
        elif metodo == "POST":
            resposta = client.post(endereco, data={})
        else:
            continue

        assert resposta.status_code == 403, (rota, metodo, resposta.status_code)
        assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode(), (
            rota,
            metodo,
        )
        if metodo == "POST":
            assert _nada_foi_gravado(empresa), (rota, metodo, "gravou mesmo recusando")


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
