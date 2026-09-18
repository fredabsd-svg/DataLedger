"""BL-275 (achado A2 da auditoria DL-024, rodada 1): mecanismo para a
exigência de acessibilidade dos atalhos de teclado que o `arquiteto-senior`
impôs em `templates/base.html` e em
`templates/contabilidade/_navegacao_empresa.html`.

**O que o auditor mediu e o que ele achou.** A árvore de acessibilidade do
Chromium confirmava que o nome anunciado de um link era "Balancete", não
"Balancete Alt L" — a implementação estava CERTA. O problema é que nada
GUARDAVA isso: o auditor removeu todo `aria-hidden="true"` da página e trocou
o `accesskey` do Diário de "i" para "c" (colidindo com Plano de contas), e a
suíte inteira — 1292 testes — devolveu verde. O modo de falha que o comentário
de `base.html` diz ter evitado ("um leitor de tela anunciaria 'Balancete Alt
L' como se fosse parte do rótulo") voltava em silêncio.

Este arquivo fecha essa lacuna com quatro guardas, cada uma com controle
positivo — a lição da BL-271, repetida na nota do `arquiteto-senior` sobre a
A1 desta mesma rodada: teste que não morre quando a defesa é removida não é
guarda, é enfeite:

1. Todo `kbd.tecla` (o texto do atalho à mostra, ex. "Alt+L") tem
   `aria-hidden="true"` — sem isso, o atalho vaza para o nome acessível do
   link.
2. Todo elemento com `accesskey` tem `aria-keyshortcuts` COERENTE (a mesma
   tecla, no formato "Alt+<LETRA>") — sem isso, quem usa leitor de tela nunca
   fica sabendo do atalho.
3. Nenhum `accesskey` se repete na MESMA página renderizada — a moldura
   (`base.html`: Painel/Empresas) e a navegação da empresa
   (`_navegacao_empresa.html`: Plano de contas/Diário/Balancete/
   Conferência/Novo lançamento) precisam somar sete teclas distintas, não
   seis com uma repetida.
4. Os cinco atalhos da contabilidade (Plano de contas, Diário, Balancete,
   Conferência, Novo lançamento) existem em TODA tela que inclui a parcial —
   hoje as oito de `templates/contabilidade/` (BL-283(c) fechou as duas que
   faltavam: `conta_form.html` e `lancamento_detalhe.html`).

As guardas 1 a 4 rodam contra a RENDERIZAÇÃO REAL de cada tela (cliente de
teste do Django, não parsing estático de template) — é a página que o
usuário de fato recebe, com `base.html` e a parcial já compostos. As duas
mutações do próprio auditor são reproduzidas literalmente nos testes
`test_mutacao_*` abaixo, sobre HTML real renderizado, não sobre um trecho
sintético — se a defesa correspondente for removida do produto, o teste de
mutação PASSA A FALHAR (porque a mutação deixa de mudar nada), entregando o
mesmo sinal que a remoção direta da guarda.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# urlconf de teste, mesmo espelho de apps/contabilidade/tests/test_dl017_telas.py
# (ver a docstring de módulo de lá sobre por que este espelho existe e não
# substitui apps.contabilidade.tests.test_dl017_urlconf_integrado).
urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("empresas/", include("apps.empresas.urls")),
    path("contabilidade/", include("apps.contabilidade.urls")),
    path("contabilidade/painel/", include("apps.contabilidade.urls_web")),
    path("", include("apps.tenancy.urls")),
]

pytestmark = [pytest.mark.django_db, pytest.mark.urls(__name__)]


# ---------------------------------------------------------------------------
# Detectores — funções puras sobre HTML já renderizado
# ---------------------------------------------------------------------------

PADRAO_TECLA = re.compile(r'<kbd\b[^>]*class="tecla"[^>]*>', re.IGNORECASE)
PADRAO_ACCESSKEY = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*\baccesskey="([a-zA-Z])"[^>]*>')

# As cinco páginas fixas de templates/contabilidade/_navegacao_empresa.html,
# na ordem em que a parcial as lista.
ATALHOS_CONTABILIDADE = [
    ("c", "Plano de contas"),
    ("i", "Diário"),
    ("l", "Balancete"),
    ("k", "Conferência"),
    ("n", "Novo lançamento"),
]


def teclas_sem_aria_hidden(html):
    """Todo `kbd.tecla` precisa de `aria-hidden="true"` — sem isso, o
    atalho ("Alt+L") vaza para o nome acessível do link (achado A2)."""
    return [
        m.group(0) for m in PADRAO_TECLA.finditer(html) if 'aria-hidden="true"' not in m.group(0)
    ]


def accesskeys_incoerentes(html):
    """Todo elemento com `accesskey="x"` precisa do `aria-keyshortcuts`
    correspondente ("Alt+X") NA MESMA TAG — sem isso, quem usa leitor de
    tela não fica sabendo que o atalho existe."""
    achados = []
    for m in PADRAO_ACCESSKEY.finditer(html):
        tecla = m.group(1)
        esperado = f'aria-keyshortcuts="Alt+{tecla.upper()}"'
        if esperado not in m.group(0):
            achados.append(m.group(0)[:120])
    return achados


def accesskeys_duplicados(html):
    """Nenhum `accesskey` pode se repetir na MESMA página — repetição
    significa que um dos dois atalhos simplesmente não funciona (o
    navegador resolve para um só), e a colisão do auditor (Diário e Plano
    de contas, os dois em "c") não aparecia em nenhum teste antes desta
    guarda."""
    vistos = set()
    duplicados = []
    for m in PADRAO_ACCESSKEY.finditer(html):
        tecla = m.group(1).lower()
        if tecla in vistos and tecla not in duplicados:
            duplicados.append(tecla)
        vistos.add(tecla)
    return duplicados


def _link_de_atalho_presente(html, tecla, rotulo):
    padrao = re.compile(
        rf'accesskey="{tecla}"\s+aria-keyshortcuts="Alt\+{tecla.upper()}">\s*{re.escape(rotulo)}'
    )
    return bool(padrao.search(html))


def _item_atual_presente(html, rotulo):
    padrao = re.compile(rf'class="item-atual" aria-current="page">{re.escape(rotulo)}</span>')
    return bool(padrao.search(html))


def atalhos_ausentes(html):
    """Os cinco atalhos da contabilidade — como link com `accesskey`
    coerente, OU como o rótulo da página atual (`item-atual`, que não é
    link porque a página não linka para si mesma) — precisam estar
    presentes em toda tela que inclui a parcial. Some da lista uma tela
    inteira que esqueceu de incluir `_navegacao_empresa.html` (a mesma
    classe de defeito da BL-283(c): `conta_form.html` e
    `lancamento_detalhe.html` ficaram de fora até a rodada 2)."""
    return [
        rotulo
        for tecla, rotulo in ATALHOS_CONTABILIDADE
        if not _link_de_atalho_presente(html, tecla, rotulo)
        and not _item_atual_presente(html, rotulo)
    ]


def assert_pagina_acessivel(html):
    assert not teclas_sem_aria_hidden(html), "kbd.tecla sem aria-hidden='true': " + repr(
        teclas_sem_aria_hidden(html)
    )
    assert not accesskeys_incoerentes(html), "accesskey sem aria-keyshortcuts coerente: " + repr(
        accesskeys_incoerentes(html)
    )
    assert not accesskeys_duplicados(html), "accesskey repetido na mesma página: " + repr(
        accesskeys_duplicados(html)
    )
    assert not atalhos_ausentes(html), "atalhos da contabilidade ausentes: " + repr(
        atalhos_ausentes(html)
    )


# ---------------------------------------------------------------------------
# Cenário — dados 100% sintéticos
# ---------------------------------------------------------------------------


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-a11y"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


@pytest.fixture
def cenario(client):
    escritorio = Escritorio.objects.create(nome="Escritório A11y", cnpj="11333555000199")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A11y Ltda", cnpj="22444666000177"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    _autenticar(client, escritorio)
    hoje = timezone.localdate()
    lancamento = criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Lançamento sintético para a12y",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
        criado_por=get_user_model().objects.get(username="gestor-a11y"),
        chave_idempotencia="a11y-seed-1",
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "capital": capital,
        "lancamento": lancamento,
    }


def _urls_de_contabilidade(cenario):
    empresa_id = cenario["empresa"].id
    inicio = timezone.localdate().replace(day=1).isoformat()
    fim = timezone.localdate().isoformat()
    periodo = f"?inicio={inicio}&fim={fim}"
    return {
        "plano_de_contas": reverse("contabilidade_web:plano_de_contas", args=[empresa_id]),
        "conta_nova": reverse("contabilidade_web:conta_nova", args=[empresa_id]),
        "diario": reverse("contabilidade_web:diario", args=[empresa_id]) + periodo,
        "razao": reverse("contabilidade_web:razao", args=[empresa_id, cenario["caixa"].id])
        + periodo,
        "balancete": reverse("contabilidade_web:balancete", args=[empresa_id]) + periodo,
        "conferencia": reverse("contabilidade_web:conferencia", args=[empresa_id]),
        "lancamento_novo": reverse("contabilidade_web:lancamento_novo", args=[empresa_id]),
        "lancamento_detalhe": reverse(
            "contabilidade_web:lancamento_detalhe", args=[empresa_id, cenario["lancamento"].id]
        ),
    }


# ---------------------------------------------------------------------------
# As guardas — sobre a renderização real das oito telas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_tela",
    [
        "plano_de_contas",
        "conta_nova",
        "diario",
        "razao",
        "balancete",
        "conferencia",
        "lancamento_novo",
        "lancamento_detalhe",
    ],
)
def test_tela_de_contabilidade_e_acessivel_nos_atalhos(client, cenario, nome_tela):
    """As quatro guardas, contra a renderização real de cada uma das oito
    telas de `templates/contabilidade/` — não sobra tela sem a parcial
    (critério: os cinco atalhos aparecem), e nenhuma delas introduz
    `kbd.tecla` sem `aria-hidden` nem `accesskey` incoerente ou repetido.
    """
    url = _urls_de_contabilidade(cenario)[nome_tela]
    resposta = client.get(url)
    assert resposta.status_code == 200, f"{nome_tela}: {resposta.status_code}"
    assert_pagina_acessivel(resposta.content.decode())


# ---------------------------------------------------------------------------
# Mutações — repetindo literalmente as duas do auditor, sobre HTML real
# ---------------------------------------------------------------------------


def test_mutacao_removendo_todo_aria_hidden_e_detectada(client, cenario):
    """Repete a mutação nº1 do achado A2: remover TODO `aria-hidden="true"`
    da página. No produto (revisão `5c7303e`), essa mutação deixava a
    suíte inteira — 1292 testes — verde. Aqui ela precisa matar a guarda.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not teclas_sem_aria_hidden(html), "controle: a página real já deveria estar limpa"

    mutado = html.replace('aria-hidden="true"', "")
    achados = teclas_sem_aria_hidden(mutado)
    assert achados, "a mutação (remover aria-hidden) não foi detectada — a guarda não guarda"


def test_mutacao_colisao_de_accesskey_e_detectada(client, cenario):
    """Repete a mutação nº2 do achado A2: trocar o `accesskey` do Diário de
    "i" para "c", colidindo com Plano de contas. No produto, a árvore de
    acessibilidade do mutante mostrava os DOIS links respondendo a
    `aria-keyshortcuts="Alt+C"` — e a suíte inteira continuava verde.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not accesskeys_duplicados(html), "controle: a página real não deveria colidir"

    mutado = html.replace(
        'accesskey="i" aria-keyshortcuts="Alt+I"', 'accesskey="c" aria-keyshortcuts="Alt+C"'
    )
    duplicados = accesskeys_duplicados(mutado)
    assert duplicados == ["c"], f"a mutação (colisão de accesskey) não foi detectada: {duplicados}"


def test_mutacao_removendo_a_parcial_de_uma_tela_e_detectada(client, cenario):
    """Repete a classe de defeito da BL-283(c): uma tela que deixa de
    incluir `_navegacao_empresa.html` perde os cinco atalhos em silêncio.
    Simula a ausência removendo o `<nav class="navegacao-empresa">` do
    HTML já renderizado, em vez de editar o template em disco.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not atalhos_ausentes(html), "controle: a página real deveria ter os cinco atalhos"

    inicio = html.find('<nav class="navegacao-empresa"')
    assert inicio != -1, "a página de controle precisa conter a parcial para o teste fazer sentido"
    fim = html.find("</nav>", inicio) + len("</nav>")
    mutado = html[:inicio] + html[fim:]

    ausentes = atalhos_ausentes(mutado)
    assert set(ausentes) == {rotulo for _tecla, rotulo in ATALHOS_CONTABILIDADE}, (
        "a mutação (remover a parcial) não foi detectada por completo: " + repr(ausentes)
    )


# ---------------------------------------------------------------------------
# Controles positivos dos detectores — sobre HTML sintético, sem banco
# ---------------------------------------------------------------------------


def test_controle_positivo_tecla_sem_aria_hidden():
    limpo = '<kbd class="tecla" aria-hidden="true">Alt+L</kbd>'
    sujo = '<kbd class="tecla">Alt+L</kbd>'
    assert not teclas_sem_aria_hidden(limpo)
    assert teclas_sem_aria_hidden(sujo)


def test_controle_positivo_accesskey_incoerente():
    coerente = '<a href="#" accesskey="l" aria-keyshortcuts="Alt+L">Balancete</a>'
    incoerente_sem_atributo = '<a href="#" accesskey="l">Balancete</a>'
    incoerente_tecla_errada = '<a href="#" accesskey="l" aria-keyshortcuts="Alt+K">Balancete</a>'
    assert not accesskeys_incoerentes(coerente)
    assert accesskeys_incoerentes(incoerente_sem_atributo)
    assert accesskeys_incoerentes(incoerente_tecla_errada)


def test_controle_positivo_accesskey_duplicado():
    sem_colisao = (
        '<a accesskey="c" aria-keyshortcuts="Alt+C">Plano de contas</a>'
        '<a accesskey="i" aria-keyshortcuts="Alt+I">Diário</a>'
    )
    com_colisao = (
        '<a accesskey="c" aria-keyshortcuts="Alt+C">Plano de contas</a>'
        '<a accesskey="c" aria-keyshortcuts="Alt+C">Diário</a>'
    )
    assert not accesskeys_duplicados(sem_colisao)
    assert accesskeys_duplicados(com_colisao) == ["c"]


def test_controle_positivo_atalho_ausente():
    completo = "".join(
        f'<a accesskey="{tecla}" aria-keyshortcuts="Alt+{tecla.upper()}">{rotulo}</a>'
        for tecla, rotulo in ATALHOS_CONTABILIDADE
    )
    faltando_um = "".join(
        f'<a accesskey="{tecla}" aria-keyshortcuts="Alt+{tecla.upper()}">{rotulo}</a>'
        for tecla, rotulo in ATALHOS_CONTABILIDADE
        if rotulo != "Diário"
    )
    assert not atalhos_ausentes(completo)
    assert atalhos_ausentes(faltando_um) == ["Diário"]
