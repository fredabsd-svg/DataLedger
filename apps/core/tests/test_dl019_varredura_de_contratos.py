"""Varredura de repositório das superfícies de escrita e dos seus contratos
(BL-149, lacuna (a) do inventário de 2026-09-15; BL-170, achado A1 da
auditoria DL-019 rodada 1).

## Por que ela existe

A política dos cinco dicionários (`apps.core.requisicao`) está aplicada e tem
testes de comportamento em cada superfície. O que faltava era a varredura no
molde da BL-134 — a que **impede a próxima superfície de nascer sem
contrato**. O histórico é literal sobre a necessidade:

- BL-121 corrigiu as duas `APIView` sem `permission_classes` e escreveu um
  teste por NOME; a BL-134 apontou que "a décima quinta não seria detectada"
  e virou varredura.
- BL-145 fechou a política em **1 de 7** superfícies. O critério estava
  escrito, a conferência foi feita, e seis ficaram de fora.
- BL-157/BL-167: o registro de restrições afirmava uma varredura que não
  existia, e **duas** constraints passaram pela conferência manual.

Três vezes a mesma lição: *conferência manual não reprova build*.

## A quarta lição, e ela é sobre ESTA varredura (BL-170)

A primeira versão deste arquivo atacava o que a varredura *faz* e não o que
ela *não enxerga*. O auditor mediu **duas fugas**, cada uma com o mutante
aplicado sozinho e a suíte inteira verde (1027 passed, lint limpo):

1. **View de função que grava sem mencionar nenhum gatilho textual.** A
   classificação "trata POST" era `"request.method" in fonte or "request.POST"
   in fonte`. Uma view no molde que a DL-010 vai precisar — `json.loads(
   request.body)` sob `@require_POST` — não contém nenhum dos dois textos,
   gravava no banco e passava.
2. **`ViewSet` do DRF, inteiro.** `getattr(classe, "post", None)` é `None` num
   `ModelViewSet`: os métodos de escrita dele chamam-se `create`, `update`,
   `partial_update` e `destroy`. Ele **é** subclasse de `APIView`, entrava na
   lista de classes, e saía em silêncio.

E o arquivo **afirmava por escrito** que nada disso podia acontecer — décima
quarta ocorrência da família "comentário que afirma mais do que a defesa
entrega", dentro do arquivo construído para matá-la. A correção, prescrita
pelo auditor, é começar pela pergunta certa: **o que está alcançável por
requisição**, respondida pelo urlconf real, e nunca por nome de módulo mais
heurística de substring.

## O que esta varredura exige

**1. Toda superfície de escrita aplica a política.** Superfície de escrita é
o par (alvo alcançável, método de escrita HTTP) descoberto assim:

- **Classe roteada como `ViewSet`**: os métodos vêm de
  `callback.initkwargs["actions"]` — o que o roteador REALMENTE liga
  (`{"post": "create", "delete": "destroy"}`), não `getattr(classe, "post")`.
- **Demais classes** (`APIView`, `generics.*`, `django.views.View`):
  `http_method_names` cruzado com os handlers que a classe de fato tem — é
  exatamente assim que `dispatch()` escolhe o handler em tempo de execução.
- **View de função**: pelos métodos que o **decorador declara**
  (`@require_POST`, `@require_http_methods`, `@require_safe`), lidos do
  objeto. Nunca por substring do fonte.

Para cada uma, o handler tem de chamar `recusar_dado_nao_contratado` — direta
ou por uma ponte do próprio app (uma indireção é resolvida, e a detecção é por
AST, nunca por substring: `inspect.getsource` de uma função chamada
`_recusar_dado_nao_contratado` contém o nome dela na própria linha do `def`, e
um teste por substring seria permanentemente verdadeiro, que é o defeito da
BL-150).

**2. Toda view de função alcançável DECLARA os métodos que aceita.** Sem
declaração a varredura não sabe classificá-la — e "não sei classificar" nunca
vira "não é superfície de escrita": vira reprovação, nomeando a view. É esta
regra que fecha a fuga (1), porque o fato passa a ser do objeto e não do
texto.

**3. Nenhum `ContratoDeRequisicao` de código de produção fica sem `campos`
explícito.** `campos=None` — o padrão — significa "este contrato não julga o
corpo": um contrato construído sem `campos` recusaria arquivo, querystring e
cabeçalho, e deixaria **passar qualquer chave no corpo**, em silêncio e com
aparência de sucesso. É o formato exato do defeito desta etapa, e o padrão da
classe é permissivo porque existe um uso legítimo (corpo julgado item a item,
noutro ponto). Quem precisar dele declara na lista de exceções, com razão
escrita.

**4. Lista de exceções NOMEADA, nunca padrão permissivo.** Os dois registros
abaixo estão vazios hoje, e vazios são a defesa mais forte. Entrada nova exige
razão escrita, e uma entrada que deixe de corresponder a algo real reprova
(não fica encobrindo nada).

## O que ela NÃO cobre, declarado

A regra de redação desta seção, depois da BL-170: **ela só pode dizer o que a
varredura entrega, medido**. A versão anterior prometia que uma view de função
que passasse a gravar "menciona `request.POST` e entra na varredura pelo mesmo
critério" — e isso era falso, e falso é pior que ausente, porque impede que
alguém vá conferir.

**O que não chega por requisição HTTP.** Escrita por ORM direto, pelo admin do
Django ou por management command não passa por nenhum handler de rota e não é
alcançada aqui. O admin é superfície nunca varrida e tem item próprio
(BL-164); management command não existe no repositório hoje.

**Código de terceiros.** O `admin/`, o `login/` e o `logout/` do urlconf têm
`__module__` fora de `apps.` e ficam de fora: as regras deste produto não
governam o código do Django. Essa fronteira não fica implícita — e não pode,
porque "o módulo não começa com `apps.`" é a forma mais barata de uma rota
desaparecer da varredura. `test_toda_rota_fora_dos_apps_e_de_terceiro_
conhecido` exige que todo callback descartado por esse filtro venha de um
prefixo de terceiro DECLARADO; qualquer outro reprova, nomeando a rota. O
admin tem item próprio (BL-164).

**View ainda não roteada.** A varredura parte do urlconf; uma view de função
escrita e não roteada não é alcançável por requisição e não aparece. As
`APIView` definidas em `apps/**/views*.py` entram mesmo sem rota, porque a
varredura de classes da BL-134 já as descobre e custa nada reaproveitar.

**Se a superfície tem TESTE dos cinco dicionários.** Esta varredura prova que
a política é CHAMADA, não que alguém a exercitou por requisição. Amarrar
superfície a arquivo de teste por casamento de nome seria uma promessa que o
próprio mecanismo não sustenta — o erro que a BL-166 nomeou. O elo que falta
tem item, dono e desenho próprios: **BL-171**.
"""

import ast
import inspect
import pathlib
import sys
import textwrap

import pytest
from django.contrib.auth.decorators import login_required
from django.urls import get_resolver
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from rest_framework import viewsets
from rest_framework.views import APIView

# Molde reaproveitado, de propósito: a varredura da BL-134 já resolve "quais
# módulos de views existem" e "quais APIView são definidas aqui, não
# importadas". Reimplementar isso seria a segunda cópia da mesma regra
# (DE-026) — e, se aquele auxiliar for renomeado, este arquivo falha no
# import, em vez de passar a varrer um conjunto vazio em silêncio.
from apps.core.tests.test_permission_classes_explicito import (
    _apiviews_definidas_no_repositorio,
)

METODOS_DE_ESCRITA = ("post", "put", "patch", "delete")
METODOS_DE_ESCRITA_EM_MAIUSCULAS = frozenset(m.upper() for m in METODOS_DE_ESCRITA)

NOME_DA_POLITICA = "recusar_dado_nao_contratado"

# Nome da variável livre que `django.views.decorators.http.require_http_
# methods` fecha sobre a lista de métodos declarada. Ler o fechamento é o que
# transforma o decorador num FATO DO OBJETO — o Django não expõe a lista por
# atributo nenhum. Se o Django renomear essa variável, `metodos_http_
# declarados` devolve `None` e a view passa a ser reprovada como NÃO
# DECLARADA: a quebra é alta e nomeada, nunca "a view deixou de ser escrita".
# `test_a_leitura_do_decorador_de_metodos_funciona` é o controle positivo
# disso, decorando funções aqui dentro e conferindo o que sai.
NOME_DA_LISTA_DE_METODOS_DO_DJANGO = "request_method_list"

# Mapa que o `SimpleRouter` do DRF usa para ligar método HTTP a nome de ação
# num `ViewSet`. Usado APENAS como retaguarda, para um `ViewSet` descoberto
# sem rota (e portanto sem `initkwargs["actions"]`): quando há rota, quem
# manda é o que o roteador de fato ligou, inclusive `@action` com nome
# próprio. Este mapa nunca substitui o `actions` real.
ACOES_DE_ESCRITA_PADRAO_DO_ROTEADOR = {
    "post": "create",
    "put": "update",
    "patch": "partial_update",
    "delete": "destroy",
}

# Raiz do repositório: este arquivo é `<raiz>/apps/core/tests/…`, logo três
# níveis acima. Conferida por `test_a_raiz_do_repositorio_esta_correta` — um
# `parents[2]` (o erro que este arquivo cometeu ao nascer) faria
# `_arquivos_de_producao_dos_apps` devolver LISTA VAZIA, e a varredura de
# contratos passaria sem ler uma linha. Foi o controle positivo que pegou.
RAIZ = pathlib.Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Exceções NOMEADAS. Vazias hoje — e vazias é o estado desejado.
#
# Formato: {"caminho.pontilhado.da.superficie.metodo": "razão escrita"}. Uma
# entrada aqui não é dispensa: é declaração verificável de que alguém decidiu,
# e de por quê. `test_nenhuma_excecao_registrada_ficou_obsoleta` reprova se a
# superfície citada deixar de existir — uma exceção órfã encobriria a
# superfície seguinte que herdasse o mesmo nome.
#
# A última entrada que existiria aqui era `apps.empresas.views.criar_empresa`,
# a tela de cadastro de empresa: única superfície de escrita do repositório
# sem a política, encontrada por ESTA varredura na segunda rodada da DL-019 e
# corrigida no mesmo passo (ver `_contrato_da_tela_de_empresa`), em vez de
# registrada como exceção.
SUPERFICIES_DE_ESCRITA_SEM_POLITICA = {}

# Formato: {"caminho.pontilhado.da.view": "razão escrita"} para uma view de
# função alcançável pelo urlconf que não declare os métodos que aceita. Vazio,
# e vazio é o estado desejado: a declaração custa uma linha e é o que impede
# a fuga (1) da BL-170 de voltar.
VIEWS_DE_FUNCAO_SEM_DECLARACAO_DE_METODOS = {}

# Formato: {"arquivo:linha": "razão escrita"} para um `ContratoDeRequisicao`
# construído sem `campos` explícito. Ver o item 3 do docstring: existe uso
# legítimo (corpo julgado item a item noutro ponto), e ele precisa ser
# declarado, não presumido.
CONTRATOS_SEM_CAMPOS_AUTORIZADOS = {}


# ---------------------------------------------------------------------------
# Detecção por AST — nunca por substring
# ---------------------------------------------------------------------------


def nomes_chamados(fonte):
    """Nomes de tudo que é CHAMADO em `fonte` (`Name` e `Attribute`).

    Por AST, e isso é a diferença entre uma defesa e uma afirmação que não
    pode ser falsa: a linha `def _recusar_dado_nao_contratado(request,
    contrato):` contém o texto `recusar_dado_nao_contratado(`, então
    `"recusar_dado_nao_contratado(" in inspect.getsource(...)` seria
    verdadeiro para a própria ponte, para um comentário que a citasse e para
    um `import`. É exatamente o M17 da BL-150, na mesma etapa.
    """
    arvore = ast.parse(textwrap.dedent(fonte))
    nomes = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if isinstance(alvo, ast.Name):
            nomes.add(alvo.id)
        elif isinstance(alvo, ast.Attribute):
            nomes.add(alvo.attr)
    return nomes


def aplica_a_politica(fonte, resolver=None, profundidade=1):
    """`True` se `fonte` chama a política — direta ou por uma ponte do app.

    A indireção de UM nível é necessária e é o máximo aceito: `apps.empresas.
    views.EmpresaDetailView.put` chama `self._recusar_dado_nao_contratado_na_
    atualizacao(request)`, que chama a ponte do app, que chama a política.
    Mais níveis transformariam a varredura em análise de fluxo, com falso
    positivo silencioso na primeira refatoração.
    """
    nomes = nomes_chamados(fonte)
    if any(nome.lstrip("_") == NOME_DA_POLITICA for nome in nomes):
        return True
    if not (resolver and profundidade > 0):
        return False
    for nome in nomes:
        fonte_indireta = resolver(nome)
        if fonte_indireta and aplica_a_politica(
            fonte_indireta, resolver, profundidade=profundidade - 1
        ):
            return True
    return False


def contratos_sem_campos_explicitos(fonte_do_arquivo, rotulo_do_arquivo):
    """`["arquivo:linha", ...]` para cada `ContratoDeRequisicao(...)` sem
    `campos` explícito, ou com `campos=None` literal.

    Os dois casos têm o MESMO efeito — o contrato não julga o corpo — e o
    segundo entra aqui de propósito: declarar `campos=None` é uma decisão
    legítima em um caso e um esquecimento disfarçado no resto, e a diferença
    entre os dois só existe se estiver escrita na lista de exceções.
    """
    achados = []
    for no in ast.walk(ast.parse(fonte_do_arquivo)):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        nome = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", None)
        if nome != "ContratoDeRequisicao":
            continue
        campos = next((kw for kw in no.keywords if kw.arg == "campos"), None)
        ausente = campos is None
        nulo_literal = (
            campos is not None
            and isinstance(campos.value, ast.Constant)
            and campos.value.value is None
        )
        if ausente or nulo_literal:
            achados.append(f"{rotulo_do_arquivo}:{no.lineno}")
    return achados


# ---------------------------------------------------------------------------
# Descoberta das superfícies — a partir do que está ALCANÇÁVEL
# ---------------------------------------------------------------------------


def metodos_http_declarados(objeto):
    """Métodos HTTP que os decoradores de `objeto` declaram, em maiúsculas, ou
    `None` quando não há declaração nenhuma.

    BL-170. Este é o substituto da heurística textual `"request.method" in
    fonte`, e a diferença é de natureza: aqui a resposta é um **fato do
    objeto** (o que `@require_POST`/`@require_http_methods` fechou sobre a
    função), não uma substring que pode simplesmente não estar no arquivo. A
    fuga medida pelo auditor era exatamente essa — uma view que grava com
    `json.loads(request.body)` não escreve `request.POST` em lugar nenhum.

    Percorre a cadeia de `__wrapped__` porque `@login_required` fica POR FORA
    no molde deste repositório, e `functools.wraps` é o que deixa o rastro.
    Declarações empilhadas se INTERSECTAM: dois decoradores restringem, nunca
    ampliam.
    """
    declarados = None
    vistos = set()
    atual = objeto
    while atual is not None and id(atual) not in vistos:
        vistos.add(id(atual))
        codigo = getattr(atual, "__code__", None)
        celulas = getattr(atual, "__closure__", None) or ()
        if (
            codigo is not None
            and NOME_DA_LISTA_DE_METODOS_DO_DJANGO in codigo.co_freevars
            and len(celulas) == len(codigo.co_freevars)
        ):
            indice = codigo.co_freevars.index(NOME_DA_LISTA_DE_METODOS_DO_DJANGO)
            valor = celulas[indice].cell_contents
            if isinstance(valor, (list, tuple, set, frozenset)) and all(
                isinstance(metodo, str) for metodo in valor
            ):
                deste_nivel = frozenset(metodo.upper() for metodo in valor)
                declarados = deste_nivel if declarados is None else declarados & deste_nivel
        atual = getattr(atual, "__wrapped__", None)
    return declarados


# Prefixos de módulo cujo código NÃO é governado pelas regras deste produto.
# Declarados, e não presumidos: o filtro `__module__.startswith("apps.")` é o
# ponto em que uma rota pode sair da varredura sem ninguém ver, e
# `test_toda_rota_fora_dos_apps_e_de_terceiro_conhecido` exige que tudo o que
# ele descarta caia num destes prefixos. As rotas do admin do Django ficam
# aqui — a varredura do admin contra as regras de negócio é a BL-164.
PREFIXOS_DE_MODULO_DE_TERCEIROS = ("django.", "rest_framework.")


def _percorrer_callbacks_do_urlconf():
    """`(alvo, initkwargs)` de todo callback de rota do urlconf REAL, sem
    nenhum filtro de módulo — é sobre esta lista crua que o filtro de
    terceiros é medido."""
    encontrados = []

    def percorrer(padroes):
        for padrao in padroes:
            if hasattr(padrao, "url_patterns"):
                percorrer(padrao.url_patterns)
                continue
            callback = getattr(padrao, "callback", None)
            if callback is None:
                continue
            alvo = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
            alvo = alvo or callback
            encontrados.append((alvo, getattr(callback, "initkwargs", None) or {}))

    percorrer(get_resolver().url_patterns)
    return encontrados


def rotas_fora_dos_apps():
    """`{"modulo.qualname": modulo}` para todo callback do urlconf cujo módulo
    não é de `apps.` — a lista que o filtro descarta."""
    fora = {}
    for alvo, _initkwargs in _percorrer_callbacks_do_urlconf():
        modulo = getattr(alvo, "__module__", "") or ""
        if modulo.startswith("apps."):
            continue
        fora[f"{modulo}.{getattr(alvo, '__qualname__', alvo)}"] = modulo
    return fora


def _alvos_alcancaveis():
    """`{"caminho.pontilhado": (alvo, initkwargs)}` — tudo que responde a uma
    requisição neste projeto.

    Parte do urlconf REAL, que é a pergunta certa ("o que está alcançável por
    requisição"), e não de nome de módulo mais heurística de substring.
    `view_class` é o atributo que o Django pendura em `View.as_view()`; `cls`,
    o que o DRF pendura em `APIView.as_view()`; `initkwargs` carrega o
    `actions` que o roteador do DRF liga num `ViewSet` — é ele que fecha a
    fuga (2) da BL-170.

    As `APIView` definidas em `apps/**/views*.py` e ainda SEM rota entram
    depois, com `initkwargs` vazio: custa nada, e uma view de escrita escrita
    hoje e roteada amanhã já nasce dentro da varredura.
    """
    alvos = {}
    for alvo, initkwargs in _percorrer_callbacks_do_urlconf():
        modulo = getattr(alvo, "__module__", "") or ""
        if not modulo.startswith("apps."):
            continue
        alvos[f"{modulo}.{alvo.__qualname__}"] = (alvo, initkwargs)

    for classe in _apiviews_definidas_no_repositorio():
        alvos.setdefault(f"{classe.__module__}.{classe.__qualname__}", (classe, {}))

    return alvos


def _escopo_da_indirecao(alvo):
    """Onde procurar a ponte do app: a própria classe, ou o módulo da view de
    função."""
    if isinstance(alvo, type):
        return alvo
    return sys.modules.get(getattr(alvo, "__module__", "") or "")


def _resolvedor_de_indirecao(escopo):
    """Devolve o fonte de `nome` quando ele é uma função do PROJETO acessível
    em `escopo` (a classe da view, ou o módulo dela)."""

    def resolver(nome):
        alvo = getattr(escopo, nome, None)
        if alvo is None or not (inspect.isfunction(alvo) or inspect.ismethod(alvo)):
            return None
        if not (getattr(alvo, "__module__", "") or "").startswith("apps."):
            return None
        try:
            return inspect.getsource(alvo)
        except (OSError, TypeError):  # pragma: no cover - fonte indisponível
            return None

    return resolver


def _handlers_de_escrita_da_classe(classe, initkwargs):
    """`{"post": handler, ...}` — só os métodos de escrita que esta classe
    RESPONDE de verdade.

    Duas fontes, nesta ordem, e a primeira é a correção da fuga (2):

    1. `initkwargs["actions"]`, se houver: é o que o roteador do DRF ligou
       (`{"post": "create", "delete": "destroy"}`), inclusive para `@action`
       com nome próprio. Um `ViewSet` NÃO tem atributo `post`, e foi por
       `getattr(classe, "post", None) is None` que o padrão mais comum do DRF
       saía inteiro da varredura anterior, em silêncio.
    2. `http_method_names` cruzado com os handlers existentes — que é
       exatamente como `dispatch()` escolhe o handler em tempo de execução,
       tanto no `View` do Django quanto na `APIView` do DRF. Cobre também o
       `@api_view`, cujo `WrappedAPIView` tem `http_method_names` restrito ao
       que foi declarado.
    """
    acoes = initkwargs.get("actions") if initkwargs else None
    if acoes is None and issubclass(classe, viewsets.ViewSetMixin):
        acoes = ACOES_DE_ESCRITA_PADRAO_DO_ROTEADOR

    handlers = {}
    if acoes:
        for metodo, nome_da_acao in acoes.items():
            if metodo.lower() not in METODOS_DE_ESCRITA:
                continue
            handler = getattr(classe, nome_da_acao, None)
            if handler is not None:
                handlers[metodo.lower()] = handler
        return handlers

    permitidos = {
        metodo.lower() for metodo in getattr(classe, "http_method_names", METODOS_DE_ESCRITA)
    }
    for metodo in METODOS_DE_ESCRITA:
        if metodo not in permitidos:
            continue
        handler = getattr(classe, metodo, None)
        if handler is not None:
            handlers[metodo] = handler
    return handlers


def superficies_de_escrita(alvos):
    """`(superficies, sem_declaracao)` para os alvos dados.

    - `superficies`: `{"caminho.metodo": (handler, escopo_da_indirecao)}`.
    - `sem_declaracao`: `{"caminho": motivo}` para view de função alcançável
      que não declara os métodos que aceita — o caso em que a varredura não
      SABE classificar, e por isso reprova em vez de presumir leitura.

    Recebe os alvos como PARÂMETRO, e não os busca por conta própria, para que
    os dois mutantes da BL-170 possam ser reconstruídos dentro do próprio
    arquivo (molde da BL-150), sem depender de ninguém ter registrado que viu
    a suíte falhar e sem tocar em nenhuma view real.
    """
    superficies = {}
    sem_declaracao = {}

    for caminho, (alvo, initkwargs) in sorted(alvos.items()):
        escopo = _escopo_da_indirecao(alvo)
        if isinstance(alvo, type):
            for metodo, handler in _handlers_de_escrita_da_classe(alvo, initkwargs).items():
                superficies[f"{caminho}.{metodo}"] = (handler, escopo)
            continue

        declarados = metodos_http_declarados(alvo)
        if declarados is None:
            sem_declaracao[caminho] = (
                "view de função alcançável pelo urlconf sem declarar os métodos que "
                "aceita — decore com @require_safe, @require_POST ou "
                "@require_http_methods([...])"
            )
            continue
        for metodo in sorted(declarados & METODOS_DE_ESCRITA_EM_MAIUSCULAS):
            superficies[f"{caminho}.{metodo.lower()}"] = (alvo, escopo)

    return superficies, sem_declaracao


def superficies_de_escrita_sem_politica(alvos=None):
    """`{"caminho.metodo": "motivo"}` para cada superfície de escrita que NÃO
    chega à política."""
    if alvos is None:
        alvos = _alvos_alcancaveis()
    superficies, _ = superficies_de_escrita(alvos)

    faltando = {}
    for nome, (handler, escopo) in superficies.items():
        try:
            fonte = inspect.getsource(handler)
        except (OSError, TypeError):  # pragma: no cover - fonte indisponível
            continue
        if aplica_a_politica(fonte, _resolvedor_de_indirecao(escopo)):
            continue
        onde = getattr(handler, "__qualname__", nome)
        faltando[nome] = (
            f"o handler que responde a esta superfície é {onde} e não chama {NOME_DA_POLITICA}"
        )
    return faltando


def _arquivos_de_producao_dos_apps():
    """Todo `.py` de `apps/` fora de pasta de testes.

    Não se limita a `views.py`: um `ContratoDeRequisicao` construído em
    `services.py` ou num mixin teria exatamente o mesmo efeito, e limitar a
    varredura ao lugar onde o padrão nasceu é como a BL-144 deixou duas
    constraints de fora.
    """
    for caminho in sorted((RAIZ / "apps").rglob("*.py")):
        partes = caminho.relative_to(RAIZ).parts
        if "tests" in partes or caminho.name.startswith("test_"):
            continue
        yield caminho


# ---------------------------------------------------------------------------
# Controles de que a varredura enxerga algo
# ---------------------------------------------------------------------------


def test_a_raiz_do_repositorio_esta_correta():
    """`RAIZ` errada não faz nada falhar por conta própria: só torna a
    varredura de contratos vazia. Prender os dois marcos do repositório é o
    que impede que ela volte a passar lendo nada."""
    assert (RAIZ / "apps").is_dir()
    assert (RAIZ / "manage.py").is_file()
    assert (RAIZ / "apps" / "core" / "requisicao.py").is_file()


def test_a_leitura_do_decorador_de_metodos_funciona():
    """Controle positivo de `metodos_http_declarados`, que é o mecanismo de
    que a metade "views de função" da varredura inteira depende.

    Se ele parar de funcionar (o Django renomeia a variável livre, alguém
    troca a ordem dos decoradores), toda view de função vira NÃO DECLARADA e
    reprova alto — mas este teste é o que diz, em uma linha, que o defeito é
    da leitura e não das views."""

    @require_POST
    def so_post(request):  # pragma: no cover - objeto de medição
        return None

    @login_required
    @require_http_methods(["GET", "POST"])
    def get_e_post(request):  # pragma: no cover - objeto de medição
        return None

    @login_required
    @require_safe
    def so_leitura(request):  # pragma: no cover - objeto de medição
        return None

    @login_required
    def sem_declaracao(request):  # pragma: no cover - objeto de medição
        return None

    assert metodos_http_declarados(so_post) == frozenset({"POST"})
    assert metodos_http_declarados(get_e_post) == frozenset({"GET", "POST"})
    assert metodos_http_declarados(so_leitura) == frozenset({"GET", "HEAD"})
    assert metodos_http_declarados(sem_declaracao) is None


# As superfícies de escrita conhecidas em 2026-09-15, agora com o MÉTODO no
# nome — porque é o par (alvo, método) que a varredura julga.
SUPERFICIES_DE_ESCRITA_CONHECIDAS = (
    "apps.contabilidade.views.ContaListCreateView.post",
    "apps.contabilidade.views.LancamentoListCreateView.post",
    "apps.contabilidade.views.EstornarLancamentoView.post",
    "apps.contabilidade.views_web.conta_nova.post",
    "apps.contabilidade.views_web.lancamento_novo.post",
    "apps.empresas.views.EmpresaListCreateView.post",
    "apps.empresas.views.EmpresaDetailView.put",
    "apps.empresas.views.EmpresaDetailView.patch",
    "apps.empresas.views.EstabelecimentoListCreateView.post",
    "apps.empresas.views.HistoricoRegimeTributarioListCreateView.post",
    "apps.empresas.views.HistoricoRegimeTributarioDetailView.delete",
    "apps.empresas.views.criar_empresa.post",
    "apps.tenancy.views.EscritorioAtivoView.post",
    "apps.tenancy.views.ativar_escritorio.post",
)


def test_a_varredura_encontra_as_superficies_de_escrita_de_hoje():
    """Controle: se a descoberta quebrar, o teste principal passaria a varrer
    um conjunto vazio e "nenhuma falta" viraria vácuo.

    BL-170, item 3 da correção: este controle usa **o mesmo caminho** do teste
    principal (`superficies_de_escrita(_alvos_alcancaveis())`). Antes ele
    contava pelo urlconf enquanto o teste principal varria por módulo — dois
    conjuntos diferentes, e o controle não protegia a metade que podia
    esvaziar. É o mesmo furo que `test_a_raiz_do_repositorio_esta_correta` já
    fechava na outra metade do arquivo.
    """
    superficies, _ = superficies_de_escrita(_alvos_alcancaveis())
    assert len(superficies) >= len(SUPERFICIES_DE_ESCRITA_CONHECIDAS), sorted(superficies)


@pytest.mark.parametrize("superficie", SUPERFICIES_DE_ESCRITA_CONHECIDAS)
def test_cada_superficie_de_escrita_conhecida_continua_visivel_a_varredura(superficie):
    """Controle NOMINAL, no molde de `test_varredura_inclui_as_14_apiviews_
    conferidas_pelo_auditor`. Se uma superfície for renomeada, movida, ou
    deixar de ser CLASSIFICADA como escrita (o decorador sumiu, o roteador
    deixou de ligar a ação), este teste falha apontando QUAL — em vez de ela
    sair da varredura em silêncio, que é a forma mais fácil de uma varredura
    passar a não medir nada.

    A pergunta mudou com a BL-170: antes era "o atributo ainda existe?"
    (`getattr(classe, "post")`), que é justamente a pergunta que devolvia
    `None` para todo `ViewSet`. Agora é "a varredura ainda enxerga esta
    superfície?", que é a pergunta que o teste principal faz.
    """
    superficies, _ = superficies_de_escrita(_alvos_alcancaveis())
    assert superficie in superficies, sorted(superficies)


# ---------------------------------------------------------------------------
# Os testes principais
# ---------------------------------------------------------------------------


def test_toda_superficie_de_escrita_aplica_a_politica_dos_cinco_dicionarios():
    faltando = superficies_de_escrita_sem_politica()
    nao_autorizadas = {
        nome: motivo
        for nome, motivo in faltando.items()
        if nome not in SUPERFICIES_DE_ESCRITA_SEM_POLITICA
    }

    assert not nao_autorizadas, (
        "Superfície de escrita que não chega a apps.core.requisicao."
        + NOME_DA_POLITICA
        + ":\n"
        + "\n".join(f"  {nome}: {motivo}" for nome, motivo in sorted(nao_autorizadas.items()))
        + "\n\nAplique a política (uma linha, pela ponte do app) ou registre a "
        "superfície em SUPERFICIES_DE_ESCRITA_SEM_POLITICA com a razão escrita. "
        "Padrão permissivo não é defesa: foi com sete superfícies 'conferidas' "
        "que a BL-145 fechou em uma."
    )


def test_toda_rota_fora_dos_apps_e_de_terceiro_conhecido():
    """A fronteira do filtro de módulo, virada verificação.

    `__module__.startswith("apps.")` é o que faz o admin do Django e as rotas
    de autenticação ficarem de fora — e é também a forma mais barata de uma
    rota DESTE produto desaparecer da varredura em silêncio (basta um
    decorador que troque o `__module__` do callback). Exigir que tudo o que o
    filtro descarta caia num prefixo de terceiro DECLARADO transforma o
    descarte em decisão conferível, em vez de efeito colateral.
    """
    desconhecidas = {
        nome: modulo
        for nome, modulo in rotas_fora_dos_apps().items()
        if not modulo.startswith(PREFIXOS_DE_MODULO_DE_TERCEIROS)
    }

    assert not desconhecidas, (
        "Estas rotas do urlconf saem da varredura de contratos por não terem "
        "módulo de `apps.`, e não vêm de nenhum prefixo de terceiro "
        f"declarado:\n{sorted(desconhecidas.items())}\n\n"
        "Ou o módulo é do produto (e a rota precisa entrar na varredura), ou "
        "o prefixo entra em PREFIXOS_DE_MODULO_DE_TERCEIROS com a decisão "
        "explícita de que aquelas regras não são deste produto."
    )


def test_o_filtro_de_terceiros_esta_de_fato_descartando_o_admin():
    """Par do teste acima: se `rotas_fora_dos_apps` passar a devolver vazio
    (a travessia do urlconf quebrou), aquele teste ficaria verdadeiro por
    vácuo — e é justamente o vácuo que esta etapa inteira existe para não
    deixar passar."""
    fora = rotas_fora_dos_apps()

    assert any(modulo.startswith("django.contrib.admin") for modulo in fora.values()), sorted(fora)
    assert len(fora) >= 10, sorted(fora)


def test_toda_view_de_funcao_alcancavel_declara_os_metodos_que_aceita():
    """BL-170, fuga (1). A varredura só pode dizer "isto não é superfície de
    escrita" quando tem um FATO em que se apoiar. Sem declaração de métodos
    ela não tem — e a resposta certa para "não sei" é reprovar nomeando a
    view, nunca presumir leitura.

    O custo é uma linha por view; o que ele compra é que a próxima view de
    função a gravar não possa nascer invisível, seja qual for o jeito de ler
    o corpo da requisição (`request.POST`, `request.body`, `request.FILES`) —
    e a DL-010 chega com os três.
    """
    _, sem_declaracao = superficies_de_escrita(_alvos_alcancaveis())
    nao_autorizadas = {
        nome: motivo
        for nome, motivo in sem_declaracao.items()
        if nome not in VIEWS_DE_FUNCAO_SEM_DECLARACAO_DE_METODOS
    }

    assert not nao_autorizadas, (
        "View de função alcançável por requisição sem declaração de métodos:\n"
        + "\n".join(f"  {nome}: {motivo}" for nome, motivo in sorted(nao_autorizadas.items()))
        + "\n\nDecore a view com @require_safe (só leitura), @require_POST ou "
        "@require_http_methods([...]). A declaração é o que permite a esta "
        "varredura saber se a view é superfície de escrita sem depender de "
        "procurar 'request.POST' no fonte — heurística que o auditor da "
        "rodada 1 contornou com uma view que grava lendo request.body."
    )


def test_nenhuma_excecao_registrada_ficou_obsoleta():
    """Exceção órfã é pior que exceção: ela continua dispensando um nome que
    ninguém mais reconhece, e cobriria a próxima superfície que o herdasse."""
    faltando = superficies_de_escrita_sem_politica()
    _, sem_declaracao = superficies_de_escrita(_alvos_alcancaveis())

    orfas = sorted(set(SUPERFICIES_DE_ESCRITA_SEM_POLITICA) - set(faltando))
    orfas += sorted(set(VIEWS_DE_FUNCAO_SEM_DECLARACAO_DE_METODOS) - set(sem_declaracao))

    assert not orfas, f"Estas exceções não correspondem mais a nada de real — remova-as: {orfas}"


def test_nenhum_contrato_de_requisicao_e_construido_sem_campos_explicito():
    achados = {}
    for caminho in _arquivos_de_producao_dos_apps():
        rotulo = str(caminho.relative_to(RAIZ))
        for onde in contratos_sem_campos_explicitos(caminho.read_text(encoding="utf-8"), rotulo):
            achados[onde] = rotulo

    nao_autorizados = sorted(set(achados) - set(CONTRATOS_SEM_CAMPOS_AUTORIZADOS))

    assert not nao_autorizados, (
        "ContratoDeRequisicao construído sem `campos` explícito (ou com "
        f"`campos=None`): {nao_autorizados}\n"
        "Um contrato assim recusa arquivo, querystring e cabeçalho e deixa "
        "passar QUALQUER chave no corpo, em silêncio e com aparência de "
        "sucesso. Declare os campos, ou registre em "
        "CONTRATOS_SEM_CAMPOS_AUTORIZADOS a razão de o corpo ser julgado "
        "noutro ponto."
    )


def test_a_varredura_de_contratos_enxerga_os_contratos_de_hoje():
    """Controle positivo da parte 3: se o reconhecimento do `Call` quebrar
    (renomearam a classe, passou a ser construída por outro nome), a varredura
    aprovaria um repositório que ela não está mais lendo."""
    total = 0
    for caminho in _arquivos_de_producao_dos_apps():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            alvo = getattr(no, "func", None)
            nome = getattr(alvo, "id", None) or getattr(alvo, "attr", None)
            if isinstance(no, ast.Call) and nome == "ContratoDeRequisicao":
                total += 1

    assert total >= 8, total


# ---------------------------------------------------------------------------
# As demonstrações, reconstruídas dentro do próprio teste (molde BL-150)
#
# As duas primeiras são as DUAS FUGAS que o auditor mediu na rodada 1 (A1),
# reconstruídas aqui para a prova não depender de ninguém ter registrado que
# viu a suíte falhar — e para que, se alguém voltar a classificar por
# substring ou por `getattr(classe, "post")`, a suíte reprove no mesmo commit.
# ---------------------------------------------------------------------------


def test_a_varredura_reprova_superficie_de_escrita_sem_a_politica():
    """O mutante "nasceu uma superfície de escrita nova, sem contrato",
    construído aqui em fonte sintético."""
    sem_politica = """
        def post(self, request):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(status=201)
    """
    com_politica = """
        def post(self, request):
            _recusar_dado_nao_contratado(request, CONTRATO)
            return super().post(request)
    """

    assert aplica_a_politica(sem_politica) is False
    assert aplica_a_politica(com_politica) is True


def test_a_varredura_nao_se_satisfaz_com_mencao_em_comentario_ou_def():
    """O M17 da BL-150 reconstruído nesta varredura: as três formas de o nome
    da política aparecer no fonte SEM ninguém chamá-la. Uma varredura por
    substring aprovaria as três."""
    so_no_comentario = """
        def post(self, request):
            # a política de recusar_dado_nao_contratado vale aqui
            return super().post(request)
    """
    so_no_import = """
        def post(self, request):
            from apps.core.requisicao import recusar_dado_nao_contratado

            return super().post(request)
    """
    so_na_propria_assinatura = """
        def _recusar_dado_nao_contratado(request, contrato):
            return None
    """

    assert aplica_a_politica(so_no_comentario) is False
    assert aplica_a_politica(so_no_import) is False
    assert aplica_a_politica(so_na_propria_assinatura) is False


def test_a_varredura_reprova_contrato_sem_campos_e_com_campos_none():
    """O mutante da exigência acrescentada pelo arquiteto: contrato de view de
    escrita construído sem `campos`. As duas formas do mesmo efeito."""
    sem_campos = 'C = ContratoDeRequisicao(cabecalhos_ignorados=("Idempotency-Key",))\n'
    campos_none = "C = ContratoDeRequisicao(campos=None, contexto='x')\n"
    com_campos = 'C = ContratoDeRequisicao(campos={"a"}, contexto="x")\n'

    assert contratos_sem_campos_explicitos(sem_campos, "fonte") == ["fonte:1"]
    assert contratos_sem_campos_explicitos(campos_none, "fonte") == ["fonte:1"]
    assert contratos_sem_campos_explicitos(com_campos, "fonte") == []


# --- Fuga (1) da BL-170: a view de função que grava sem gatilho textual -----


@login_required
@require_POST
def _mutante_conta_nova_json(request, empresa_id):  # pragma: no cover - objeto de medição
    """Reconstrução EXATA da reprodução (a) do achado A1: uma view no molde
    que a DL-010 vai precisar — lê o corpo com `json.loads(request.body)`,
    grava, e não contém nenhum dos dois gatilhos textuais que a varredura
    anterior procurava (o teste abaixo afirma isso sobre este fonte, e por
    isso nem este docstring pode citá-los).

    O auditor acrescentou esta view a `apps/contabilidade/views_web.py`, rodou
    a suíte inteira e obteve 1027 passed com lint limpo. Ela vive aqui agora,
    e a suíte reprova se a varredura voltar a não enxergá-la.
    """
    import json

    dados = json.loads(request.body)
    _gravar_conta_ficticia(empresa_id, dados["codigo"], dados["nome"])
    return None


@login_required
@require_POST
def _mutante_conta_nova_json_com_politica(
    request, empresa_id
):  # pragma: no cover - objeto de medição
    """A mesma view, com a política. O par é o que impede o teste de passar
    por acidente: sem ele, uma varredura que reprovasse TUDO também passaria
    na metade de cima."""
    import json

    from apps.core.requisicao import recusar_dado_nao_contratado

    recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
    dados = json.loads(request.body)
    _gravar_conta_ficticia(empresa_id, dados["codigo"], dados["nome"])
    return None


@login_required
def _mutante_tela_sem_declaracao_de_metodos(request):  # pragma: no cover - objeto de medição
    """View de função alcançável e sem declarar método nenhum: o caso em que a
    varredura não SABE classificar."""
    return None


_CONTRATO_FICTICIO = object()


def _gravar_conta_ficticia(empresa_id, codigo, nome):  # pragma: no cover - objeto de medição
    """Fica aqui para os mutantes acima terem o que "gravar" sem tocar no
    banco: o que está sob medição é a VARREDURA, não a gravação."""
    return (empresa_id, codigo, nome)


def test_a_varredura_enxerga_view_de_funcao_que_grava_sem_mencionar_request_post():
    """Fuga (1) da BL-170, reconstruída e medida aqui dentro."""
    fonte = inspect.getsource(_mutante_conta_nova_json)

    # O fato que tornava a heurística textual falsa, preso como asserção: a
    # view grava e NÃO contém nenhum dos dois gatilhos que a versão anterior
    # procurava. Se alguém "consertar" este mutante acrescentando
    # `request.POST`, o teste falha aqui e não silenciosamente adiante.
    assert "request.method" not in fonte
    assert "request.POST" not in fonte

    alvos = {"apps.ficticio.views.conta_nova_json": (_mutante_conta_nova_json, {})}
    superficies, sem_declaracao = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.conta_nova_json.post"}
    assert sem_declaracao == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == {
        "apps.ficticio.views.conta_nova_json.post"
    }


def test_a_varredura_aprova_a_mesma_view_de_funcao_quando_ela_aplica_a_politica():
    alvos = {
        "apps.ficticio.views.conta_nova_json": (_mutante_conta_nova_json_com_politica, {}),
    }
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.conta_nova_json.post"}
    assert superficies_de_escrita_sem_politica(alvos) == {}


def test_a_varredura_reprova_view_de_funcao_sem_declaracao_de_metodos():
    alvos = {"apps.ficticio.views.tela_nova": (_mutante_tela_sem_declaracao_de_metodos, {})}
    superficies, sem_declaracao = superficies_de_escrita(alvos)

    assert superficies == {}
    assert set(sem_declaracao) == {"apps.ficticio.views.tela_nova"}


# --- Fuga (2) da BL-170: o ViewSet do DRF ----------------------------------


class _MutanteContaViewSetSemContrato(viewsets.ModelViewSet):
    """Reconstrução EXATA da reprodução (b) do achado A1.

    Um `ModelViewSet` **é** subclasse de `APIView` — entrava na lista de
    classes da varredura anterior — e **não tem** nenhum dos atributos `post`,
    `put`, `patch`, `delete`: os métodos de escrita dele chamam-se `create`,
    `update`, `partial_update` e `destroy`. O laço antigo fazia
    `getattr(classe, metodo, None); if handler is None: continue`, e o padrão
    mais comum do DRF saía inteiro, em silêncio.
    """

    def create(self, request, *args, **kwargs):  # pragma: no cover - objeto de medição
        return self.get_serializer(data=request.data)

    def destroy(self, request, *args, **kwargs):  # pragma: no cover - objeto de medição
        return self.get_object().delete()


class _MutanteContaViewSetComContrato(viewsets.ModelViewSet):
    """O mesmo `ViewSet`, com a política nas duas ações de escrita."""

    def create(self, request, *args, **kwargs):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return self.get_serializer(data=request.data)

    def destroy(self, request, *args, **kwargs):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return self.get_object().delete()


def test_o_viewset_do_drf_escapava_por_getattr_e_isso_fica_preso_aqui():
    """A medição do auditor, virada asserção: é a explicação de por que a
    varredura anterior não via nada, e o que impede alguém de voltar a
    `getattr(classe, "post")` achando que resolve."""
    assert issubclass(_MutanteContaViewSetSemContrato, APIView)
    for metodo in METODOS_DE_ESCRITA:
        assert getattr(_MutanteContaViewSetSemContrato, metodo, None) is None


def test_a_varredura_enxerga_o_viewset_pelo_que_o_roteador_liga():
    """Fuga (2): com `actions` — o que o roteador do DRF de fato liga — as
    duas ações de escrita aparecem, nomeadas."""
    initkwargs = {"actions": {"get": "list", "post": "create", "delete": "destroy"}}
    alvos = {"apps.ficticio.views.ContaViewSet": (_MutanteContaViewSetSemContrato, initkwargs)}

    superficies, sem_declaracao = superficies_de_escrita(alvos)

    assert set(superficies) == {
        "apps.ficticio.views.ContaViewSet.post",
        "apps.ficticio.views.ContaViewSet.delete",
    }
    assert sem_declaracao == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == {
        "apps.ficticio.views.ContaViewSet.post",
        "apps.ficticio.views.ContaViewSet.delete",
    }


def test_a_varredura_enxerga_o_viewset_mesmo_sem_rota_registrada():
    """Retaguarda: um `ViewSet` descoberto sem `actions` (escrito hoje,
    roteado amanhã) cai no mapa padrão do `SimpleRouter` — não some.

    Aparecem os QUATRO métodos, e não os dois que este mutante escreve à mão:
    `update`/`partial_update` vêm do `UpdateModelMixin` do DRF e respondem a
    PUT/PATCH de verdade assim que alguém rotear o `ViewSet` com o roteador
    padrão. Sem rota não há como saber quais ações serão ligadas, e a
    retaguarda erra para o lado de EXIGIR contrato — que é o lado certo.
    """
    alvos = {"apps.ficticio.views.ContaViewSet": (_MutanteContaViewSetSemContrato, {})}

    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {
        "apps.ficticio.views.ContaViewSet.post",
        "apps.ficticio.views.ContaViewSet.put",
        "apps.ficticio.views.ContaViewSet.patch",
        "apps.ficticio.views.ContaViewSet.delete",
    }


def test_a_varredura_aprova_o_viewset_que_aplica_a_politica():
    initkwargs = {"actions": {"post": "create", "delete": "destroy"}}
    alvos = {"apps.ficticio.views.ContaViewSet": (_MutanteContaViewSetComContrato, initkwargs)}

    superficies, _ = superficies_de_escrita(alvos)

    assert len(superficies) == 2
    assert superficies_de_escrita_sem_politica(alvos) == {}
