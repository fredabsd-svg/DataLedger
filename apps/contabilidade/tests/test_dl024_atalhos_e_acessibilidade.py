"""BL-275 (achado A2 da auditoria DL-026, rodada 1): mecanismo para a
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

BL-334 (M2 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): até esta correção, as
guardas 1 a 3 (aria-hidden/coerência/duplicidade) só corriam contra as OITO
telas de `templates/contabilidade/` — uma LISTA escrita à mão
(`_urls_de_contabilidade`). O produto tem mais telas fora dessa pasta
(`empresas/`, `tenancy/`, `registration/`, `erros/`), todas estendendo a
MESMA moldura (`base.html`) com os MESMOS atalhos Painel/Empresas — e
nenhuma delas tinha guarda nenhuma. Medido pelo auditor: um
`<a href="#sabotagem" accesskey=p>` inserido em
`templates/empresas/lista.html`, colidindo com o `Alt+P` do Painel e sem
`aria-keyshortcuts`, passava com `1715 passed` — **literalmente o defeito
do BL-323, um diretório ao lado**.

A varredura ESTÁTICA (`apps/core/tests/test_dl024_varredura_de_interface.py`)
já fazia isso certo desde o BL-320: deriva as raízes de
`settings.TEMPLATES` e varre TODOS os templates. A guarda RENDERIZADA
(este arquivo) ficou para trás, com uma lista.

A correção deriva o conjunto de ROTAS (não de arquivos de template — o
requisito é sobre o que o usuário RECEBE ao navegar, e mais de uma rota
pode renderizar o mesmo template em estados diferentes, como
`empresas:lista` → `empresas/lista.html` OU `empresas/sem_escritorio.html`
conforme o vínculo do usuário) diretamente da urlconf REAL do produto
(`config/urls.py`, via `django.urls.get_resolver`) — nunca retypada. Toda
rota nomeada alcançável dali tem de estar em UM dos dois lados:

- `NOMES_DE_TELA_DE_CONTABILIDADE`/`NOMES_DE_TELA_FORA_DA_CONTABILIDADE`:
  coberta por um teste real desta suíte, contra a renderização de verdade.
- `EXCLUSOES_NOMEADAS_DE_TELA` (e a subárvore `SUBARVORES_EXCLUIDAS`, para
  namespaces inteiros como o admin do Django): excluída, com o MOTIVO
  escrito — no padrão de `PASTAS_QUE_NAO_SAO_MODULO`
  (`apps/core/tests/test_dl024_varredura_de_interface.py`).

`test_toda_rota_do_produto_esta_coberta_ou_excluida`, ao fim deste arquivo,
é quem cobra isso: rota nova sem entrada em nenhum dos dois lados reprova a
suíte, nomeando a rota que falta classificar.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.urls import get_resolver, include, path, reverse
from django.urls.resolvers import URLPattern, URLResolver
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.core.marcacao import tem_classe, tokens_de_atributo
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

# M4/BL-295 (rodada 4 da auditoria DL-026,
# docs/auditorias/2026-09-18-dl-024-rodada-2.md): a versão anterior deste
# padrão casava `class="tecla"` por IGUALDADE do valor INTEIRO do
# atributo — `class="tecla destaque"` (uma segunda classe, adicionada por
# qualquer alteração de CSS sem pensar duas vezes) escapava por COMPLETO
# do alcance da guarda, e junto dela a exigência de `aria-hidden`
# (`teclas_sem_aria_hidden` abaixo). Medido pelo auditor na árvore de
# acessibilidade do Chromium: o mutante anunciava `link nome='Plano de
# contas Alt+C'` — o achado A2 da rodada 1 de volta — com 15 passed.
#
# Agora o padrão encontra QUALQUER `<kbd ...>` e `teclas_sem_aria_hidden`
# decide, por `tem_classe` (apps.core.marcacao — casamento por TOKEN do
# atributo `class`, compartilhado com a varredura de interface e com
# `test_dl017_rodada2_frontend.descricoes_de_data_sem_defesa`, para não
# escrever esta lógica uma terceira vez), se o elemento carrega a classe
# "tecla" — não importa quantas outras classes tenha.
PADRAO_TAG_KBD = re.compile(r"<kbd\b[^>]*>", re.IGNORECASE)

# M4/BL-295: o mesmo defeito valia para `accesskey` — o padrão antigo só
# reconhecia um valor de EXATAMENTE uma letra (`accesskey="([a-zA-Z])"`).
# Um valor com mais de um token, como `accesskey="c d"` (dois atalhos
# alternativos — válido pela HTML Living Standard, mas fora da convenção
# deste produto, que usa sempre UM atalho por elemento), não casava com o
# padrão NENHUMA vez: o elemento inteiro desaparecia das guardas de
# coerência (`accesskeys_incoerentes`) e de duplicidade
# (`accesskeys_duplicados`), em vez de ser REPROVADO por não seguir a
# convenção. O padrão passou a encontrar qualquer TAG que declare
# `accesskey` ENTRE ASPAS e `_accesskey_de` (abaixo) decide, por
# `tokens_de_atributo`, se o valor é uma letra ASCII só —
# `accesskeys_malformados` reprova quando não é.
#
# BL-323 (M5 da auditoria DL-026, rodada 4,
# docs/auditorias/2026-09-19-dl-024-rodada-4.md): "entre aspas" continuava
# sendo uma LISTA de duas formas (`"..."` e `'...'`), não o requisito —
# que é NENHUM `accesskey` escapar da guarda, EM NENHUMA forma de escrita
# que o navegador aceite. Medido pelo auditor: um link NOVO em
# `base.html`, `accesskey=c` SEM ASPAS (HTML5 válido — o Chromium aplica:
# `element.accessKey == 'c'`, IDÊNTICO à forma com aspas), colidindo com o
# `Alt+C` já existente (Plano de contas) e SEM `aria-keyshortcuts` —
# passava com a suíte inteira `1525 passed`. O padrão antigo não
# reconhecia a TAG nenhuma vez: o elemento inteiro desaparecia das TRÊS
# guardas (malformado, coerência, duplicidade), não só da terceira
# alternativa de aspas que faltava dentro de `apps.core.marcacao`
# (`marcacao._padrao_atributo` já aceitava valor sem aspas — o problema
# era este padrão nunca CHEGAR a chamá-lo, porque exigia aspas para
# considerar a tag candidata).
#
# A correção não acrescenta uma quarta alternativa de aspas ao próprio
# padrão (aspas duplas | aspas simples | sem aspas | ...— a mesma lista
# que ficaria "uma auditoria atrás" da próxima forma de escrever um
# atributo HTML). Ela PARA DE EXIGIR VALOR AQUI: o padrão casa qualquer
# TAG que contenha `accesskey` como atributo — com ou sem valor, com ou
# sem aspas, de qualquer tipo —, exatamente como `PADRAO_TAG_KBD` já faz
# para `<kbd>` (casa a TAG inteira, sem descrever a forma do atributo que
# está procurando). A decisão sobre se o valor encontrado é uma letra
# ASCII só continua inteira em `_accesskey_de`, que já delega para
# `apps.core.marcacao.tokens_de_atributo` — uma implementação só de "o
# que é um valor de atributo tokenizado válido", no módulo que existe
# para isso, em vez de este arquivo reimplementar um quarto caso de
# aspas. Um `accesskey` sem NENHUM valor (`<a accesskey>`, HTML inválido
# mas que o Chromium ainda tenta processar) agora também é encontrado
# aqui e cai, corretamente, em `accesskeys_malformados` — `_accesskey_de`
# não encontra atributo com `=` para extrair e devolve `None`.
PADRAO_TAG_COM_ACCESSKEY = re.compile(
    r"<[a-zA-Z][a-zA-Z0-9]*\b[^>]*\saccesskey\b[^>]*>",
    re.IGNORECASE,
)

# As cinco páginas fixas de templates/contabilidade/_navegacao_empresa.html,
# na ordem em que a parcial as lista.
ATALHOS_CONTABILIDADE = [
    ("c", "Plano de contas"),
    ("i", "Diário"),
    ("l", "Balancete"),
    ("k", "Conferência"),
    ("n", "Novo lançamento"),
]

# BL-334: nome CURTO (usado em `_urls_de_contabilidade`/no parametrize) →
# nome COMPLETO da rota (namespace:nome), a mesma string que
# `django.urls.reverse` aceita e a mesma que
# `_nomes_de_rota_do_produto` devolve ao percorrer a urlconf real —
# ÚNICA fonte para as duas pontas, para as duas nunca divergirem.
NOMES_DE_TELA_DE_CONTABILIDADE = {
    "plano_de_contas": "contabilidade_web:plano_de_contas",
    "conta_nova": "contabilidade_web:conta_nova",
    "diario": "contabilidade_web:diario",
    "razao": "contabilidade_web:razao",
    "balancete": "contabilidade_web:balancete",
    "conferencia": "contabilidade_web:conferencia",
    "lancamento_novo": "contabilidade_web:lancamento_novo",
    "lancamento_detalhe": "contabilidade_web:lancamento_detalhe",
}


def teclas_sem_aria_hidden(html):
    """Todo `kbd.tecla` precisa de `aria-hidden="true"` — sem isso, o
    atalho ("Alt+L") vaza para o nome acessível do link (achado A2)."""
    return [
        m.group(0)
        for m in PADRAO_TAG_KBD.finditer(html)
        if tem_classe(m.group(0), "tecla") and 'aria-hidden="true"' not in m.group(0)
    ]


def _accesskey_de(tag):
    """Tecla ÚNICA declarada no `accesskey` de `tag`, ou `None` se o valor
    não for exatamente uma letra ASCII (convenção deste produto: nunca mais
    de um atalho alternativo por elemento — ver o comentário de
    `PADRAO_TAG_COM_ACCESSKEY`)."""
    tokens = tokens_de_atributo(tag, "accesskey")
    if len(tokens) != 1 or not re.fullmatch(r"[a-zA-Z]", tokens[0]):
        return None
    return tokens[0]


def accesskeys_malformados(html):
    """`accesskey` que não é uma letra ASCII só — inclusive o caso do
    achado M4/BL-295 (mais de um token, ex. `accesskey="c d"`) e o do
    BL-323 (valor SEM ASPAS, ex. `accesskey=c`, ou SEM VALOR nenhum, ex.
    `<a accesskey>` — este último não tem `=` para `tokens_de_atributo`
    extrair, então `_accesskey_de` devolve `None` do mesmo jeito que um
    valor de mais de uma letra), que antes desapareciam por completo da
    varredura em vez de serem reprovados."""
    return [
        m.group(0)[:120]
        for m in PADRAO_TAG_COM_ACCESSKEY.finditer(html)
        if _accesskey_de(m.group(0)) is None
    ]


def accesskeys_incoerentes(html):
    """Todo elemento com `accesskey="x"` (uma letra só) precisa do
    `aria-keyshortcuts` correspondente ("Alt+X") NA MESMA TAG — sem isso,
    quem usa leitor de tela não fica sabendo que o atalho existe. Um
    `accesskey` MALFORMADO (mais de um token) já é reprovado por
    `accesskeys_malformados`; não entra aqui de novo."""
    achados = []
    for m in PADRAO_TAG_COM_ACCESSKEY.finditer(html):
        tecla = _accesskey_de(m.group(0))
        if tecla is None:
            continue
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
    for m in PADRAO_TAG_COM_ACCESSKEY.finditer(html):
        tecla = _accesskey_de(m.group(0))
        if tecla is None:
            continue
        tecla = tecla.lower()
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


def assert_moldura_acessivel(html):
    """As QUATRO guardas gerais, válidas em QUALQUER tela do produto que
    estenda `base.html` — não só as de `templates/contabilidade/`. BL-334:
    extraída de `assert_pagina_acessivel` para poder ser aplicada às telas
    de fora da contabilidade, que não incluem `_navegacao_empresa.html` e
    portanto NÃO têm os cinco atalhos que `atalhos_ausentes` cobra (essa
    quinta checagem reprovaria, incorretamente, toda tela que nunca teve
    esses links)."""
    assert not teclas_sem_aria_hidden(html), "kbd.tecla sem aria-hidden='true': " + repr(
        teclas_sem_aria_hidden(html)
    )
    assert not accesskeys_malformados(html), "accesskey não é uma letra ASCII só: " + repr(
        accesskeys_malformados(html)
    )
    assert not accesskeys_incoerentes(html), "accesskey sem aria-keyshortcuts coerente: " + repr(
        accesskeys_incoerentes(html)
    )
    assert not accesskeys_duplicados(html), "accesskey repetido na mesma página: " + repr(
        accesskeys_duplicados(html)
    )


def assert_pagina_acessivel(html):
    """As quatro guardas gerais (`assert_moldura_acessivel`) MAIS a quinta,
    específica das telas que incluem `_navegacao_empresa.html`: os cinco
    atalhos da contabilidade precisam estar presentes."""
    assert_moldura_acessivel(html)
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
    # Nomes de rota vêm de NOMES_DE_TELA_DE_CONTABILIDADE (BL-334) — nunca
    # retypados aqui —, só os `args`/query string (que dependem do cenário)
    # continuam próprios de cada rota.
    args_por_tela = {
        "plano_de_contas": ([empresa_id], ""),
        "conta_nova": ([empresa_id], ""),
        "diario": ([empresa_id], periodo),
        "razao": ([empresa_id, cenario["caixa"].id], periodo),
        "balancete": ([empresa_id], periodo),
        "conferencia": ([empresa_id], ""),
        "lancamento_novo": ([empresa_id], ""),
        "lancamento_detalhe": ([empresa_id, cenario["lancamento"].id], ""),
    }
    return {
        nome_curto: reverse(NOMES_DE_TELA_DE_CONTABILIDADE[nome_curto], args=args) + query
        for nome_curto, (args, query) in args_por_tela.items()
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


def test_mutacao_kbd_com_segunda_classe_e_detectada(client, cenario):
    """M4/BL-295 (rodada 4 da auditoria DL-026): repete a sabotagem do
    auditor — `class="tecla" aria-hidden="true"` vira `class="tecla
    destaque"` (perde o `aria-hidden` junto), nos cinco `kbd` da parcial de
    navegação. Medido pelo auditor na árvore de acessibilidade do
    Chromium: o link passava a se chamar 'Plano de contas Alt+C' em vez de
    'Plano de contas' — o achado A2 da rodada 1 de volta. Antes desta
    correção (PADRAO_TECLA casando por igualdade do valor inteiro), a
    suíte inteira devolvia 15 passed. Agora `tem_classe` casa por TOKEN e a
    mutação tem que continuar sendo detectada.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not teclas_sem_aria_hidden(html), "controle: a página real já deveria estar limpa"

    mutado = html.replace('class="tecla" aria-hidden="true"', 'class="tecla destaque"')
    assert 'class="tecla destaque"' in mutado, "controle: a substituição precisa ter ocorrido"
    achados = teclas_sem_aria_hidden(mutado)
    assert achados, "a mutação (kbd com segunda classe) não foi detectada — o A2 voltaria"


def test_mutacao_accesskey_com_dois_tokens_e_detectada(client, cenario):
    """M4/BL-295: o mesmo defeito de casamento por igualdade valia para
    `PADRAO_ACCESSKEY`, que só reconhecia `accesskey` de UMA letra —
    `accesskey="c d"` (dois tokens) desaparecia por completo das guardas
    de coerência e duplicidade em vez de ser reprovado. Agora
    `accesskeys_malformados` (apps.core.marcacao.tokens_de_atributo) tem
    que reprovar.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not accesskeys_malformados(html), (
        "controle: a página real não deveria ter accesskey malformado"
    )

    mutado = html.replace(
        'accesskey="c" aria-keyshortcuts="Alt+C"', 'accesskey="c d" aria-keyshortcuts="Alt+C"'
    )
    assert 'accesskey="c d"' in mutado, "controle: a substituição precisa ter ocorrido"
    achados = accesskeys_malformados(mutado)
    assert achados, "a mutação (accesskey com dois tokens) não foi detectada"


# ---------------------------------------------------------------------------
# BL-323 (M5 da auditoria DL-026, rodada 4): três formas de `accesskey`
# SEM ASPAS que escapavam das três guardas antes desta correção. A
# primeira reproduz LITERALMENTE o link do relatório do auditor; as duas
# seguintes são formas que o relatório NÃO cita — o requisito é "nenhum
# `accesskey` escapa, em nenhuma forma de escrita", não "este link
# específico reprova". As três precisam nomear o elemento sabotado na
# mensagem de falha (via `m.group(0)`, que as três funções devolvem —
# nunca só a tecla) para a asserção ser útil quem lê o resultado, não só
# o pytest.
# ---------------------------------------------------------------------------


def test_mutacao_accesskey_sem_aspas_e_detectada(client, cenario):
    """Reproduz LITERALMENTE a sabotagem do relatório do auditor
    (docs/auditorias/2026-09-19-dl-024-rodada-4.md, achado M5): um link
    NOVO, `<a href="/relatorios/" accesskey=c>Relatórios</a>` — sem aspas,
    colidindo com o `Alt+C` já existente (Plano de contas) e SEM
    `aria-keyshortcuts`. Medido pelo auditor no produto: suíte inteira
    `1525 passed`, e o Chromium confirmando `element.accessKey == 'c'`
    IDÊNTICO ao link com aspas — os dois atalhos disputam a mesma tecla e
    o segundo não anuncia nada a leitor de tela. Tem que reprovar em DUAS
    guardas: duplicidade (a tecla "c" repete) e coerência (falta
    `aria-keyshortcuts`) — e a segunda NOMEIA o elemento, porque devolve o
    texto da tag, não só a tecla.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not accesskeys_duplicados(html), "controle: a página real não deveria colidir"
    assert not accesskeys_incoerentes(html), "controle: a página real já deveria estar coerente"

    link_sabotado = '<a href="/relatorios/" accesskey=c>Relatórios</a>'
    mutado = html.replace("</body>", link_sabotado + "</body>")
    assert link_sabotado in mutado, "controle: a inserção precisa ter ocorrido"

    duplicados = accesskeys_duplicados(mutado)
    assert duplicados == ["c"], (
        f"a mutação (accesskey=c sem aspas, colidindo) não foi detectada: {duplicados}"
    )
    incoerentes = accesskeys_incoerentes(mutado)
    assert any("/relatorios/" in achado for achado in incoerentes), (
        "a mutação (accesskey=c sem aspas, sem aria-keyshortcuts) não nomeou o elemento "
        f"sabotado: {incoerentes}"
    )


def test_mutacao_accesskey_sem_valor_e_detectado(client, cenario):
    """Forma que o relatório do auditor NÃO cita: `accesskey` declarado
    SEM VALOR nenhum — `<a href="/exportar-x9/" accesskey>Exportar</a>`.
    HTML inválido (o atributo exige valor), mas o padrão antigo também não
    reconhecia esta tag — ela exigia `accesskey\\s*=\\s*` seguido de aspas
    para considerar a tag candidata, e sem `=` o elemento inteiro
    desaparecia de TODAS as guardas, malformado incluso. Agora
    `PADRAO_TAG_COM_ACCESSKEY` encontra a tag pelo TOKEN `accesskey`
    sozinho, e `_accesskey_de` (via `tokens_de_atributo`) não encontra
    valor para extrair — cai em `accesskeys_malformados`, nomeando o
    elemento pelo `href`.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not accesskeys_malformados(html), "controle: a página real não tem accesskey malformado"

    link_sabotado = '<a href="/exportar-x9/" accesskey>Exportar</a>'
    mutado = html.replace("</body>", link_sabotado + "</body>")
    assert link_sabotado in mutado, "controle: a inserção precisa ter ocorrido"

    malformados = accesskeys_malformados(mutado)
    assert any("/exportar-x9/" in achado for achado in malformados), (
        f"a mutação (accesskey sem valor nenhum) não foi detectada, nomeando o elemento: "
        f"{malformados}"
    )


def test_mutacao_accesskey_sem_aspas_em_tag_multilinha_e_detectada(client, cenario):
    """Terceira forma, também fora do relatório: `accesskey` SEM ASPAS
    dentro de uma tag em VÁRIAS LINHAS (atributos quebrados, comuns em
    marcação formatada por ferramenta), colidindo com um atalho de PÁGINA
    (Diário, "i") em vez do atalho da moldura ("c") que o relatório usou —
    prova que a correção não depende da tecla nem de a tag estar numa
    linha só. `[^>]*` já cobre newline (classe negada inclui `\\n`); esta
    prova exercita isso de verdade, não só por leitura do padrão.
    """
    url = _urls_de_contabilidade(cenario)["balancete"]
    html = client.get(url).content.decode()
    assert not accesskeys_duplicados(html), "controle: a página real não deveria colidir"

    link_sabotado = '<a\n    href="/relatorio-diario-alt/"\n    accesskey=i>Relatório diário</a>'
    mutado = html.replace("</body>", link_sabotado + "</body>")
    assert link_sabotado in mutado, "controle: a inserção precisa ter ocorrido"

    duplicados = accesskeys_duplicados(mutado)
    assert duplicados == ["i"], (
        f"a mutação (accesskey=i sem aspas, tag multilinha, colidindo) não foi detectada: "
        f"{duplicados}"
    )
    incoerentes = accesskeys_incoerentes(mutado)
    assert any("relatorio-diario-alt" in achado for achado in incoerentes), (
        "a mutação (tag multilinha sem aria-keyshortcuts) não nomeou o elemento sabotado: "
        f"{incoerentes}"
    )
    # Controle negativo: o valor É uma letra ASCII só ("i"), então esta
    # forma NÃO deveria cair em malformado — só em duplicidade/coerência.
    # Sem este controle, um detector "acusa tudo" passaria disfarçado de
    # correto.
    assert not accesskeys_malformados(mutado), (
        "accesskey=i sem aspas é um valor VÁLIDO (uma letra); não deveria ser malformado"
    )


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


def test_controle_positivo_tecla_com_segunda_classe():
    """BL-295: `class="tecla destaque"` continua sendo alcançada pela
    guarda (com `tem_classe`, casamento por token) — reprova sem
    `aria-hidden`, passa com ele, igual a `class="tecla"` sozinha."""
    com_aria_hidden = '<kbd class="tecla destaque" aria-hidden="true">Alt+C</kbd>'
    sem_aria_hidden = '<kbd class="tecla destaque">Alt+C</kbd>'
    assert not teclas_sem_aria_hidden(com_aria_hidden)
    assert teclas_sem_aria_hidden(sem_aria_hidden)


def test_controle_positivo_accesskey_malformado():
    """BL-295: `accesskey` de uma letra só passa; com mais de um token
    (`"c d"`) ou mais de um caractere colado (`"cd"`) é malformado."""
    valido = '<a href="#" accesskey="c" aria-keyshortcuts="Alt+C">Plano de contas</a>'
    dois_tokens = '<a href="#" accesskey="c d" aria-keyshortcuts="Alt+C">Plano de contas</a>'
    colado = '<a href="#" accesskey="cd" aria-keyshortcuts="Alt+C">Plano de contas</a>'
    assert not accesskeys_malformados(valido)
    assert accesskeys_malformados(dois_tokens)
    assert accesskeys_malformados(colado)
    # Um accesskey malformado não entra em accesskeys_incoerentes/
    # accesskeys_duplicados de novo — accesskeys_malformados já cobre.
    assert not accesskeys_incoerentes(dois_tokens)
    assert not accesskeys_duplicados(dois_tokens)


def test_controle_positivo_accesskey_sem_aspas_e_sem_valor():
    """BL-323: sobre HTML SINTÉTICO (sem passar pelo cliente de teste),
    as três formas de escrita que escapavam da guarda antes desta
    correção — cobrindo o requisito em unidade, não só na página real.

    - `accesskey=c` (sem aspas) é um valor VÁLIDO: uma letra só. Tem que
      ser tratado EXATAMENTE como `accesskey="c"` — mesmo resultado nas
      três funções, para as duas formas.
    - `accesskey='c'` (aspas simples) já funcionava antes desta rodada;
      entra aqui como controle de que a correção não regrediu essa forma.
    - `accesskey` sem `=` nenhum é malformado (nenhum valor para
      extrair) — não é "letra colidindo", é "não há tecla".
    - `accesskey=c/` (sem aspas, imediatamente antes de `/>` autofechante)
      é registrado aqui como caso ACEITO como está: é a mesma limitação,
      documentada em `apps.core.marcacao` (M4 da rodada 4, sobre `class=
      valor-monetario/`), de que o valor sem aspas consome o `/` da tag
      autofechante — direção conservadora (marca como malformado em vez
      de aceitar "c"), sem caso real na base de templates deste projeto.
    """
    com_aspas_duplas = '<a href="#" accesskey="c" aria-keyshortcuts="Alt+C">Plano de contas</a>'
    sem_aspas = '<a href="#" accesskey=c aria-keyshortcuts="Alt+C">Plano de contas</a>'
    com_aspas_simples = "<a href='#' accesskey='c' aria-keyshortcuts=\"Alt+C\">Plano de contas</a>"
    sem_valor = '<a href="#" accesskey>Plano de contas</a>'

    for tag, rotulo in [
        (com_aspas_duplas, "aspas duplas"),
        (sem_aspas, "sem aspas"),
        (com_aspas_simples, "aspas simples"),
    ]:
        assert not accesskeys_malformados(tag), f"{rotulo}: não deveria ser malformado"
        assert not accesskeys_incoerentes(tag), f"{rotulo}: aria-keyshortcuts já é coerente"

    assert accesskeys_malformados(sem_valor), "accesskey sem valor nenhum precisa ser malformado"

    # Autofechante sem aspas: limitação herdada e documentada, medida
    # aqui para não ser "descoberta" de novo por auditoria — mesma
    # direção conservadora do M4/marcacao.py (acusa em vez de aceitar).
    autofechante_sem_aspas = "<input accesskey=c/>"
    assert accesskeys_malformados(autofechante_sem_aspas), (
        "limitação conhecida: accesskey=c/ (autofechante, sem aspas) consome o '/' "
        "e é tratado como malformado — se este assert falhar, a limitação mudou e "
        "o comentário precisa ser revisto"
    )


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


# ---------------------------------------------------------------------------
# BL-334 (M2 da auditoria DL-026, rodada 5): a guarda de telas deixa de
# depender de uma lista de oito URLs escrita à mão e passa a cobrir TODA
# rota nomeada da urlconf REAL do produto — coberta por um teste real, ou
# excluída com o motivo escrito. Ver a docstring do módulo para o
# raciocínio completo.
# ---------------------------------------------------------------------------

# Namespaces tratados como UM bloco só — o equivalente, em granularidade de
# SUBÁRVORE, do que `PASTAS_QUE_NAO_SAO_MODULO` já faz por PASTA em
# `apps/core/tests/test_dl024_varredura_de_interface.py`. Sem isto, o
# admin do Django sozinho acrescentaria ~50 nomes gerados dinamicamente
# (um `changelist`/`add`/`change`/`delete`/`history` por MODELO registrado),
# nenhum deles um template do produto — e cresceria a cada novo `ModelAdmin`
# registrado, sem relação nenhuma com este produto ou com esta guarda.
SUBARVORES_EXCLUIDAS_DE_TELA = {
    "admin": (
        "admin embutido do Django (django.contrib.admin) — dezenas de rotas "
        "geradas dinamicamente por modelo registrado, nenhuma delas um "
        "template do produto que estenda base.html"
    ),
    "contabilidade": (
        "API REST da contabilidade (apps.contabilidade.urls, DRF "
        "generics/APIView) — respostas JSON; a TELA equivalente já está "
        "coberta sob o namespace contabilidade_web (NOMES_DE_TELA_DE_CONTABILIDADE)"
    ),
}

# Rotas FOLHA excluídas individualmente, com o motivo — mesmo padrão de
# `PASTAS_QUE_NAO_SAO_MODULO`, em granularidade de ROTA em vez de pasta.
EXCLUSOES_NOMEADAS_DE_TELA = {
    **SUBARVORES_EXCLUIDAS_DE_TELA,
    "logout": (
        "LogoutView aceita só POST/OPTIONS (Django 6.1: "
        "LogoutView.http_method_names) — GET não renderiza página, 405"
    ),
    "core:health": (
        "sonda de saúde do processo (apps.core.views.health_check) — devolve JSON, não HTML"
    ),
    "auditoria:api-lista": "API REST de auditoria (RegistroAuditoriaListView, DRF) — JSON",
    "empresas:api-lista": "API REST de empresas (EmpresaListCreateView, DRF) — JSON",
    "empresas:api-detalhe": "API REST de empresas (EmpresaDetailView, DRF) — JSON",
    "empresas:api-estabelecimentos": (
        "API REST de estabelecimentos (EstabelecimentoListCreateView, DRF) — JSON"
    ),
    "empresas:api-regime-tributario": (
        "API REST de regime tributário (HistoricoRegimeTributarioListCreateView, DRF) — JSON"
    ),
    "empresas:api-regime-tributario-detalhe": (
        "API REST de regime tributário (HistoricoRegimeTributarioDetailView, DRF) — JSON"
    ),
    "tenancy:ativar": (
        "sempre redireciona (302) para tenancy:painel, em GET e em POST "
        "(apps.tenancy.views.ativar_escritorio) — nunca renderiza template próprio"
    ),
    "tenancy:emitir-convite": (
        "require_http_methods(['POST']) — sem GET, nunca renderiza página, 405"
    ),
    "tenancy:api-escritorios": "API REST (MeusEscritoriosView, DRF) — JSON",
    "tenancy:api-escritorio-ativo": "API REST (EscritorioAtivoView, DRF) — JSON",
}

# Rota nomeada → função(ões) desta suíte que exercitam a renderização REAL
# dela. Cada valor é só documentação (nome do(s) teste(s), para quem lê);
# a fonte de verdade da COBERTURA é a UNIÃO das chaves deste dicionário com
# as de NOMES_DE_TELA_DE_CONTABILIDADE, comparada contra a urlconf real em
# `test_toda_rota_do_produto_esta_coberta_ou_excluida`, abaixo. Limite
# conhecido (declarado, não escondido): nada IMPEDE alguém de acrescentar
# uma chave aqui sem escrever o teste correspondente — a mesma limitação
# que qualquer lista nomeada de exclusão/cobertura já tem neste projeto
# (ex. `PASTAS_QUE_NAO_SAO_MODULO`). O que esta guarda FECHA é o defeito
# medido pelo auditor: uma rota nova ficar de fora dos DOIS lados, em
# silêncio.
NOMES_DE_TELA_FORA_DA_CONTABILIDADE = {
    "login": "test_tela_de_login_e_acessivel",
    "empresas:lista": (
        "test_tela_empresas_lista_e_acessivel, "
        "test_tela_empresas_sem_escritorio_e_acessivel, "
        "test_mutacao_accesskey_colidente_em_empresas_lista_e_detectada"
    ),
    "empresas:criar": (
        "test_tela_empresas_form_e_acessivel, test_tela_erro_sem_permissao_e_acessivel"
    ),
    "tenancy:painel": (
        "test_tela_painel_e_acessivel, "
        "test_mutacao_accesskey_colidente_em_tenancy_painel_e_detectada"
    ),
    "tenancy:aceitar-convite": "test_tela_aceitar_convite_e_acessivel",
    "tenancy:bootstrap-primeiro-acesso": "test_tela_bootstrap_primeiro_acesso_e_acessivel",
}


def _nomes_de_rota_do_produto(urlconf="config.urls"):
    """Nome COMPLETO (`namespace:nome`, ou só `nome` sem namespace) de TODA
    rota NOMEADA alcançável a partir da urlconf REAL do produto
    (`config/urls.py`) — nunca retypada à mão. Usa `django.urls.get_resolver`
    com o `urlconf` explícito (não o urlconf ATIVO do teste — este arquivo
    roda sob o espelho `apps.contabilidade.tests.test_dl024_atalhos_e_
    acessibilidade` via `pytest.mark.urls`, mas a DERIVAÇÃO precisa ler a
    urlconf de verdade, `config.urls`, senão uma rota nova acrescentada só
    lá — nunca no espelho — ficaria invisível para esta guarda).

    Não desce dentro das `SUBARVORES_EXCLUIDAS_DE_TELA` (ver o comentário
    de lá) — cada uma vira UM nome só no resultado, em vez de dezenas de
    folhas individuais."""
    resolver = get_resolver(urlconf)
    nomes = set()

    def _percorrer(padroes, prefixo):
        for padrao in padroes:
            if isinstance(padrao, URLResolver):
                namespace = padrao.namespace
                if not prefixo and namespace in SUBARVORES_EXCLUIDAS_DE_TELA:
                    nomes.add(namespace)
                    continue
                novo_prefixo = f"{prefixo}{namespace}:" if namespace else prefixo
                _percorrer(padrao.url_patterns, novo_prefixo)
            elif isinstance(padrao, URLPattern) and padrao.name:
                nomes.add(f"{prefixo}{padrao.name}")

    _percorrer(resolver.url_patterns, "")
    return nomes


def test_toda_rota_do_produto_esta_coberta_ou_excluida():
    """BL-334: a guarda do próprio conjunto de telas. Rota nova, nomeada,
    alcançável a partir de `config/urls.py`, sem entrada em
    `NOMES_DE_TELA_DE_CONTABILIDADE`/`NOMES_DE_TELA_FORA_DA_CONTABILIDADE`
    NEM em `EXCLUSOES_NOMEADAS_DE_TELA`, reprova — nomeando a rota que
    falta classificar, para quem lê a falha saber exatamente o que fazer."""
    nomes_reais = _nomes_de_rota_do_produto()
    cobertas = set(NOMES_DE_TELA_FORA_DA_CONTABILIDADE) | set(
        NOMES_DE_TELA_DE_CONTABILIDADE.values()
    )
    excluidas = set(EXCLUSOES_NOMEADAS_DE_TELA)

    sobrepostas = cobertas & excluidas
    assert not sobrepostas, f"rota classificada nos DOIS lados (coberta E excluída): {sobrepostas}"

    nao_classificadas = nomes_reais - cobertas - excluidas
    assert not nao_classificadas, (
        "rota nova, sem entrada em NOMES_DE_TELA_DE_CONTABILIDADE/"
        "NOMES_DE_TELA_FORA_DA_CONTABILIDADE nem em EXCLUSOES_NOMEADAS_DE_TELA: "
        + repr(sorted(nao_classificadas))
    )

    # Controle inverso: nada declarado aqui pode ter deixado de existir na
    # urlconf real — senão a lista de cobertura/exclusão estaria testando
    # rota fantasma, e uma remoção de rota de verdade passaria em silêncio.
    excedentes = (cobertas | excluidas) - nomes_reais
    assert not excedentes, (
        "nome declarado em NOMES_DE_TELA_*/EXCLUSOES_NOMEADAS_DE_TELA que não existe "
        "(mais) na urlconf real: " + repr(sorted(excedentes))
    )


# ---------------------------------------------------------------------------
# BL-334 — as telas de FORA de templates/contabilidade/, uma a uma.
# ---------------------------------------------------------------------------


def test_tela_de_login_e_acessivel(client):
    """Tela SEM autenticação — a moldura de `base.html` não inclui os
    atalhos Painel/Empresas (guardados por `request.user.is_authenticated`
    em `templates/base.html`), então nem `kbd.tecla` nem `accesskey`
    aparecem aqui; mesmo assim é uma tela real do produto e precisa estar
    coberta, não esquecida."""
    resposta = client.get(reverse("login"))
    assert resposta.status_code == 200
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_empresas_lista_e_acessivel(client, cenario):
    """`empresas/lista.html` — a tela EXATA que o auditor sabotou para
    provar o achado M2 (accesskey=p colidindo com o Alt+P do Painel)."""
    resposta = client.get(reverse("empresas:lista"))
    assert resposta.status_code == 200
    assert "empresas/lista.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_empresas_sem_escritorio_e_acessivel(client, django_user_model):
    """Estado ALTERNATIVO da mesma rota `empresas:lista`: usuário
    autenticado SEM vínculo de escritório nenhum recebe
    `empresas/sem_escritorio.html` — outro template que ficava fora de
    qualquer guarda renderizada."""
    usuario = django_user_model.objects.create_user(
        username="sem-vinculo-a11y", email="sv-a11y@escritorio.com.br", password="senha-forte-123"
    )
    assert client.login(username=usuario.username, password="senha-forte-123")
    resposta = client.get(reverse("empresas:lista"))
    assert resposta.status_code == 200
    assert "empresas/sem_escritorio.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_empresas_form_e_acessivel(client, cenario):
    """`empresas/form.html` (GET de `empresas:criar`)."""
    resposta = client.get(reverse("empresas:criar"))
    assert resposta.status_code == 200
    assert "empresas/form.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_erro_sem_permissao_e_acessivel(client, cenario):
    """Estado ALTERNATIVO de `empresas:criar`: papel sem autorização de
    cadastro (CLIENTE, nem ADMINISTRADOR nem GESTOR) recebe
    `erros/sem_permissao.html`, 403 — a varredura ESTÁTICA (BL-320) já
    alcançava este template; a RENDERIZADA não."""
    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio"], "cliente-sem-permissao-a11y")
    assert client.login(username="cliente-sem-permissao-a11y", password="senha-forte-123")
    resposta = client.get(reverse("empresas:criar"))
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_painel_e_acessivel(client, cenario):
    """`tenancy/painel.html` — a SEGUNDA tela que o auditor citou
    explicitamente no achado M2 como alvo da mesma sabotagem."""
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_aceitar_convite_e_acessivel(client, cenario):
    """`tenancy/aceitar_convite.html` — renderiza mesmo com token
    inexistente (a view resolve o convite como `None` e o template lida
    com isso; a validação de verdade acontece no POST)."""
    resposta = client.get(reverse("tenancy:aceitar-convite", args=["token-inexistente-a11y"]))
    assert resposta.status_code == 200
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_bootstrap_primeiro_acesso_e_acessivel(client, django_user_model):
    """`tenancy/primeiro_acesso.html` — só renderiza para usuário SEM
    vínculo ativo nenhum (a view redireciona para o painel se já tiver)."""
    usuario = django_user_model.objects.create_user(
        username="sem-vinculo-bootstrap-a11y",
        email="svb-a11y@escritorio.com.br",
        password="senha-forte-123",
    )
    assert client.login(username=usuario.username, password="senha-forte-123")
    resposta = client.get(reverse("tenancy:bootstrap-primeiro-acesso"))
    assert resposta.status_code == 200
    assert "tenancy/primeiro_acesso.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


# ---------------------------------------------------------------------------
# BL-334 — reprodução das sabotagens do achado M2, sobre a renderização
# REAL de cada tela (mutação em memória sobre o HTML já buscado — nunca no
# template em disco, BL-311).
# ---------------------------------------------------------------------------


def test_mutacao_accesskey_colidente_em_empresas_lista_e_detectada(client, cenario):
    """Reprodução LITERAL da sabotagem do achado M2:
    `<a href="#sabotagem" accesskey=p>` inserido em
    `templates/empresas/lista.html`, colidindo com o `Alt+P` do Painel da
    moldura e sem `aria-keyshortcuts`. No produto medido pelo auditor
    (`53388c8`), essa sabotagem deixava a suíte inteira verde — porque
    `empresas/lista.html` não tinha teste NENHUM que buscasse a
    renderização real dela. Agora `test_tela_empresas_lista_e_acessivel`
    já busca essa renderização; esta mutação prova que, SE a sabotagem
    real estivesse no template, a guarda morreria."""
    resposta = client.get(reverse("empresas:lista"))
    html = resposta.content.decode()
    assert not accesskeys_duplicados(html), "controle: a página real não deveria colidir"
    assert not accesskeys_incoerentes(html), "controle: a página real já deveria estar coerente"

    link_sabotado = '<a href="#sabotagem" accesskey=p>Sabotagem</a>'
    mutado = html.replace("</body>", link_sabotado + "</body>")
    assert link_sabotado in mutado, "controle: a inserção precisa ter ocorrido"

    duplicados = accesskeys_duplicados(mutado)
    assert duplicados == ["p"], (
        f"a sabotagem do BL-334 (empresas/lista.html) não foi detectada: {duplicados}"
    )
    incoerentes = accesskeys_incoerentes(mutado)
    assert any("#sabotagem" in achado for achado in incoerentes), (
        f"a sabotagem do BL-334 (empresas/lista.html) não nomeou o elemento sabotado: {incoerentes}"
    )


def test_mutacao_accesskey_colidente_em_tenancy_painel_e_detectada(client, cenario):
    """Mesma reprodução, na SEGUNDA tela que o achado M2 citou:
    `templates/tenancy/painel.html`."""
    resposta = client.get(reverse("tenancy:painel"))
    html = resposta.content.decode()
    assert not accesskeys_duplicados(html), "controle: a página real não deveria colidir"
    assert not accesskeys_incoerentes(html), "controle: a página real já deveria estar coerente"

    link_sabotado = '<a href="#sabotagem" accesskey=p>Sabotagem</a>'
    mutado = html.replace("</body>", link_sabotado + "</body>")
    assert link_sabotado in mutado, "controle: a inserção precisa ter ocorrido"

    duplicados = accesskeys_duplicados(mutado)
    assert duplicados == ["p"], (
        f"a sabotagem do BL-334 (tenancy/painel.html) não foi detectada: {duplicados}"
    )
    incoerentes = accesskeys_incoerentes(mutado)
    assert any("#sabotagem" in achado for achado in incoerentes), (
        f"a sabotagem do BL-334 (tenancy/painel.html) não nomeou o elemento sabotado: {incoerentes}"
    )
