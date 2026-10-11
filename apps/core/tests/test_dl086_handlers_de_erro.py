"""DL-086 (H-01): os três handlers de erro do produto (403/404/500).

Antes desta etapa, qualquer recusa ou endereço errado caía na página técnica
do Django ("403 Forbidden"/"Not Found" em HTML cru, inglês, sem caminho de
volta). O contrato novo está em `config/urls.py` (handler403/handler404/
handler500) e nos templates `templates/erros/`; estes testes comprovam cada
cláusula dele:

1. 404 de URL inexistente responde 404 com a tela do produto.
2. 403 devolve ao usuário a mensagem ESPECÍFICA que a view levantou
   (atestado de integração com a mudança BL-584, que passou a levantar
   `PermissionDenied` com a frase do papel em vez de renderizar a recusa na
   própria view) — nunca só o texto genérico.
3. 500 responde com a tela do produto SEM tocar banco nem context processor
   (em 500 a causa costuma ser o banco; a renderização não pode depender dele).

O cenário 2 precisa de uma view que levante a exceção, e por isso este módulo
também é urlconf de teste (mesmo padrão de
`apps.contabilidade.tests.test_dl017_telas`). Os handlers DESTE urlconf são os
do PRODUTO (`config.urls`), não cópias: é a mesma função que o site usa.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test import Client, RequestFactory, override_settings
from django.urls import get_resolver, include, path

from config import urls as urls_do_produto


def _view_que_nega(request):
    # DL-086 (H-01): frase ARBITRÁRIA de propósito — se o corpo do 403 só
    # trouxer o texto padrão do template, este teste reprova.
    raise PermissionDenied("mensagem específica que só a view conhece")


def _view_que_quebra(request):
    raise RuntimeError("falha proposital do teste DL-086")


# urlconf de teste: as duas views acima mais as rotas REAIS que os templates
# de erro precisam reverter (`tenancy:painel`, `empresas:lista`) — sem elas a
# própria renderização do 403/500 recairia em NoReverseMatch.
urlpatterns = [
    path("dl086/sem-permissao/", _view_que_nega, name="dl086_sem_permissao"),
    path("dl086/quebra/", _view_que_quebra, name="dl086_quebra"),
    path("empresas/", include("apps.empresas.urls")),
    path("", include("apps.tenancy.urls")),
]

# Os handlers de erro deste urlconf de teste são os do PRODUTO: o que se testa
# é `config.urls.handler403`/`handler404`/`handler500`, não uma reimplementação.
handler403 = urls_do_produto.handler403
handler404 = urls_do_produto.handler404
handler500 = urls_do_produto.handler500

_URLCONF_DESTE_TESTE = __name__

pytestmark = pytest.mark.django_db


def test_handlers_estao_registrados_no_urlconf_do_produto():
    """O Django só enxerga um handler se ele for atributo do urlconf RAIZ.

    Este teste é o atestado de que `config/urls.py` (o ROOT_URLCONF real) está
    costurado — sem ele, os testes abaixo passariam contra o urlconf de teste
    e o site continuaria servindo a página técnica.
    """
    resolvido = get_resolver()
    assert resolvido.resolve_error_handler(403) is urls_do_produto.handler403
    assert resolvido.resolve_error_handler(404) is urls_do_produto.handler404
    assert resolvido.resolve_error_handler(500) is urls_do_produto.handler500


def test_404_de_endereco_inexistente_mostra_a_tela_do_produto():
    cliente = Client(raise_request_exception=False)
    resposta = cliente.get("/dl086-endereco-que-nao-existe/")
    assert resposta.status_code == 404
    assert "erros/pagina_nao_encontrada.html" in [t.name for t in resposta.templates]
    corpo = resposta.content.decode()
    assert "Página não encontrada" in corpo
    assert "Voltar para o Início" in corpo  # caminho de saída, não só o aviso


def test_403_leva_para_a_tela_a_mensagem_especifica_da_view():
    """A frase da exceção PRECISA chegar ao corpo — é ela que diz qual papel
    recusou o quê (BL-584). Só o default do template não basta."""
    with override_settings(ROOT_URLCONF=_URLCONF_DESTE_TESTE):
        cliente = Client(raise_request_exception=False)
        resposta = cliente.get("/dl086/sem-permissao/")
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    corpo = resposta.content.decode()
    assert "mensagem específica que só a view conhece" in corpo
    assert "Seu papel não permite realizar esta ação." not in corpo
    assert "fale com um administrador ou gestor do escritório" in corpo  # DL-086 (H-02)


def test_403_sem_frase_na_excecao_cai_no_texto_padrao():
    """Exceção sem frase não renderiza parágrafo vazio: o default do template
    entra no lugar (contrato do handler403 — `mensagem` só existe quando a
    exceção TEM texto)."""
    resposta = urls_do_produto.handler403(
        RequestFactory().get("/dl086/sem-permissao/"), PermissionDenied()
    )
    assert resposta.status_code == 403
    assert "Seu papel não permite realizar esta ação." in resposta.content.decode()


def test_500_mostra_a_tela_do_produto_sem_tocar_no_banco(monkeypatch):
    """O 500 acontece também QUANDO o banco é a causa: a renderização não pode
    consultar nada — nem ORM, nem session, nem o `request.escritorio` que o
    middleware monta. O pedido aqui vem do RequestFactory, SEM middleware e
    SEM escritório/papel, exatamente o caso limite do handler500."""

    def _banco_indisponivel(self, *args, **kwargs):
        raise AssertionError("o handler 500 tocou o banco")

    monkeypatch.setattr(BaseDatabaseWrapper, "ensure_connection", _banco_indisponivel)
    monkeypatch.setattr(BaseDatabaseWrapper, "make_cursor", _banco_indisponivel)

    resposta = urls_do_produto.handler500(RequestFactory().get("/qualquer/"))
    assert resposta.status_code == 500
    corpo = resposta.content.decode()
    assert "Erro interno" in corpo
    assert "DataLedger" in corpo
    assert "Voltar para o Início" in corpo


def test_500_de_excecao_na_view_responde_com_a_tela_do_produto():
    """Ponta a ponta: a exceção NÃO tratada na view vira 500 do produto, não
    página técnica nem texto cru."""
    with override_settings(ROOT_URLCONF=_URLCONF_DESTE_TESTE):
        cliente = Client(raise_request_exception=False)
        resposta = cliente.get("/dl086/quebra/")
    assert resposta.status_code == 500
    corpo = resposta.content.decode()
    assert "Erro interno" in corpo
    assert "DataLedger" in corpo
    assert "Traceback" not in corpo  # nada de página técnica
