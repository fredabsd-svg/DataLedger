"""BL-95 (achado 9 da auditoria DL-017, rodada 1): nenhum dos 446 testes da
etapa exercitava o `config/urls.py` REAL — `test_dl017_telas.py` declara o
próprio urlconf via `@pytest.mark.urls(__name__)`, então nenhum teste veria
uma colisão de prefixo acontecer na costura de verdade.

A API da contabilidade vive sob `contabilidade/` e as telas sob
`contabilidade/painel/` (ver `config/urls.py:16-24` e o comentário lá, e
`docs/planos/DL-017-interface-da-contabilidade.md`, seção "Onde é fácil
errar", item 1). Não é gosto: comparando literalmente, segmento por
segmento, `apps/contabilidade/urls.py` (API) e `apps/contabilidade/
urls_web.py` (tela) sob o prefixo comum `empresas/<int:empresa_id>/`, três
rotas têm o MESMO caminho literal e os MESMOS conversores dos dois lados:

    diario/
    razao/<int:conta_id>/
    balancete/

(levantamento: leitura de `apps/contabilidade/urls.py` e `apps/
contabilidade/urls_web.py` lado a lado, e confirmação por medição abaixo —
`reverse()` contra o `ROOT_URLCONF` real, sem `pytest.mark.urls`). As demais
rotas diferem no literal e por isso não colidem: `contas/` (API) x
`plano-de-contas/` e `plano-de-contas/nova/` (tela); `lancamentos/` e
`lancamentos/<int:lancamento_id>/estornar/` (API) x `lancamento/novo/` e
`lancamento/<int:lancamento_id>/` (tela); `conferencia/lotes-
desbalanceados/` (API) x `conferencia/` (tela) — o segmento extra da API
torna os dois caminhos literalmente diferentes, mesmo compartilhando o
prefixo `conferencia/`.

Se alguém um dia unificar os dois prefixos (por exemplo, os dois
`include()` de `config/urls.py` apontando para o mesmo literal), o Django
resolve a PRIMEIRA inclusão que casar com o caminho e a segunda nunca é
alcançada — sem erro, sem aviso: a tela, ou a API, simplesmente desaparece.
Este teste detecta isso comparando o `Content-Type` das duas respostas: a
API (DRF, sem `BrowsableAPIRenderer` acionado pelo cliente de teste)
devolve sempre `application/json`; a tela (Django comum, `TemplateResponse`)
devolve sempre `text/html`. Sob colisão, um dos dois lados passa a devolver
o `Content-Type` do outro, ou 404 — o teste falha nos dois casos.

Prova por mutação (registrada no relatório de entrega, não neste arquivo):
unificar os dois prefixos numa cópia isolada da árvore de trabalho faz este
teste falhar; desfeito a seguir, sem tocar `config/urls.py` de verdade
(fora do escopo desta tarefa — ver AGENTS.md e a delegação do
arquiteto-senior).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

# Período válido mínimo, só para passar da validação de entrada das três
# saídas (DE-016) e chegar à resposta 200 que este teste precisa comparar.
# O valor em si não importa: nenhuma asserção depende do conteúdo do
# período, só do Content-Type e do status de cada lado.
PERIODO = "?inicio=2024-01-01&fim=2024-01-31"


def _autenticar(client, escritorio, username="gestor-urlconf-integrado"):
    # GESTOR está em PAPEIS_QUE_LEEM_CONTABILIDADE (permissoes.py): qualquer
    # um dos cinco papéis operacionais serviria aqui, porque este teste não
    # verifica a regra de permissão (isso é o critério 1 do plano DL-017,
    # já coberto em test_dl017_telas.py e test_permissoes_contabilidade.py)
    # — só precisa de UM papel que enxergue as duas rotas para comparar o
    # Content-Type de cada uma.
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username=username, password="senha-forte-123")


@pytest.fixture
def cenario():
    """Escritório, empresa e uma conta analítica — o mínimo para as três
    saídas (Diário, Razão, Balancete) responderem 200 nos dois urlconfs.
    Dados 100% sintéticos.
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório urlconf integrado", cnpj="11133355000177"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa urlconf integrado Ltda",
        cnpj="11122233000199",
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa}


@pytest.mark.parametrize(
    "rota,precisa_de_conta",
    [
        ("diario", False),
        ("razao", True),
        ("balancete", False),
    ],
)
def test_mesma_rota_logica_devolve_json_na_api_e_html_na_tela(
    client, cenario, rota, precisa_de_conta
):
    """BL-95: contra o `config/urls.py` REAL (nenhum `pytest.mark.urls`
    neste módulo), a mesma rota lógica sob o mesmo `empresa_id` resolve para
    a API (JSON, prefixo `contabilidade/`) e para a tela (HTML, prefixo
    `contabilidade/painel/`) como conjuntos DISTINTOS de view, e as duas
    respondem 200. Se os prefixos forem unificados, uma das duas para de
    responder o que respondia (outro Content-Type, ou 404) e a asserção
    correspondente falha.
    """
    _autenticar(client, cenario["escritorio"])
    empresa_id = cenario["empresa"].id
    args = [empresa_id, cenario["caixa"].id] if precisa_de_conta else [empresa_id]

    url_api = reverse(f"contabilidade:{rota}", args=args) + PERIODO
    url_tela = reverse(f"contabilidade_web:{rota}", args=args) + PERIODO

    # As duas rotas resolvidas têm de ser caminhos DIFERENTES (prefixos
    # distintos) — se algum dia coincidirem, é o próprio urlconf que já
    # unificou os prefixos, e não faria sentido comparar Content-Type de
    # uma requisição contra ela mesma.
    assert url_api != url_tela

    resposta_api = client.get(url_api)
    resposta_tela = client.get(url_tela)

    assert resposta_api.status_code == 200, f"API {url_api}: {resposta_api.status_code}"
    assert resposta_tela.status_code == 200, f"tela {url_tela}: {resposta_tela.status_code}"
    assert resposta_api["Content-Type"] == "application/json", resposta_api["Content-Type"]
    assert resposta_tela["Content-Type"].startswith("text/html"), resposta_tela["Content-Type"]


def test_rotas_da_api_e_da_tela_nao_compartilham_prefixo(cenario):
    """Confirma a premissa da própria colisão: a API está sob
    `/contabilidade/` e a tela sob `/contabilidade/painel/` — nunca o
    mesmo prefixo — para as três rotas colidentes. Se um dia a costura em
    `config/urls.py` mudar o prefixo de um dos dois lados para igualar o do
    outro, este teste já falha aqui, antes até de chegar à comparação de
    Content-Type.
    """
    empresa_id = cenario["empresa"].id
    conta_id = cenario["caixa"].id

    for rota, args in (("diario", [empresa_id]), ("balancete", [empresa_id])):
        url_api = reverse(f"contabilidade:{rota}", args=args)
        url_tela = reverse(f"contabilidade_web:{rota}", args=args)
        assert url_api.startswith("/contabilidade/") and not url_api.startswith(
            "/contabilidade/painel/"
        )
        assert url_tela.startswith("/contabilidade/painel/")

    url_api = reverse("contabilidade:razao", args=[empresa_id, conta_id])
    url_tela = reverse("contabilidade_web:razao", args=[empresa_id, conta_id])
    assert url_api.startswith("/contabilidade/") and not url_api.startswith(
        "/contabilidade/painel/"
    )
    assert url_tela.startswith("/contabilidade/painel/")
