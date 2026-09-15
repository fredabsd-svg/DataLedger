"""Varredura de repositório das superfícies de escrita e dos seus contratos
(BL-196, lacuna (a) do inventário de 2026-09-15; BL-217, achado A1 da
auditoria DL-020 rodada 1).

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
- BL-204/BL-214: o registro de restrições afirmava uma varredura que não
  existia, e **duas** constraints passaram pela conferência manual.

Três vezes a mesma lição: *conferência manual não reprova build*.

## A quarta lição, e ela é sobre ESTA varredura (BL-217)

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

## A quinta lição, e ela é sobre a correção da quarta (BL-221)

A correção acima trocou `getattr(classe, "post")` por
`callback.initkwargs["actions"]` — e **esse mecanismo nunca executou uma vez**.
`ViewSetMixin.as_view` faz `view.actions = actions`: `actions` é atributo
**próprio da view**, nunca chave de `initkwargs`. Logo
`initkwargs.get("actions")` era sempre `None` para rota real, e todo o
comportamento observado vinha do mapa fixo de retaguarda — que por acaso tem
os nomes de um `ModelViewSet` (`create`/`update`/`partial_update`/`destroy`),
e por isso a verificação feita com um `ModelViewSet` "confirmou" o caminho
errado. Um `viewsets.ViewSet` puro com `@action(detail=False,
methods=["post"])` que grava produzia **zero superfícies**, com lint limpo,
urlconf carregando e a suíte verde — medido pelo auditor em `d97a188`, e
remedido aqui na revisão `b8d4b0a` antes da correção: **14 superfícies, zero
acusadas, 34 passed** neste arquivo com o mutante aplicado.

Duas consequências entraram na correção, e a segunda é a que faz a primeira
não virar outro defeito:

1. A fonte passou a ser `getattr(callback, "actions", None)`.
   `initkwargs["actions"]` continua sendo lido, mas **como retaguarda**, nunca
   como fonte.
2. A chave de `_alvos_alcancaveis` deixou de colapsar rotas. Um `ViewSet`
   roteado gera **duas** rotas (lista e detalhe) com o mesmo
   `modulo.qualname`: ler `actions` sem corrigir a chave faria a rota de lista
   (`{"get": "list", "post": "create"}`) ser sobrescrita pela de detalhe, e o
   POST de `create` **desapareceria**. Agora as ações das rotas de um mesmo
   alvo são **unidas**, e a superfície carrega o nome da ação
   (`...ImportacaoViewSet.importar.post`), que é o que impede duas ações
   ligadas ao mesmo método HTTP de se apagarem.

## A sexta lição, e ela é a TERCEIRA da mesma família (BL-230)

Três rodadas, três fugas, **todas na mesma fronteira**: o que a varredura
**lê** contra o que o framework **faz em tempo de execução**.

| rodada | leu | o framework usa |
| --- | --- | --- |
| 1 | `getattr(classe, "post")` | o que o roteador liga |
| 2 | `initkwargs["actions"]` | `callback.actions` |
| 3 | `http_method_names` da **classe** | o `http_method_names` da **rota** |

`View.as_view(**initkwargs)` guarda os `initkwargs` e o `view()` interno faz
`setattr(self, chave, valor)` em cada requisição: `dispatch()` consulta o valor
**da instância**, isto é, o da rota. Uma `APIView` com
`http_method_names = ["get"]` na classe, um `post` que grava a partir de
`request.data` e a rota
`as_view(http_method_names=["get", "post"])` respondia **201 e gravava** com a
varredura acusando **nada** — a mesma assinatura do B1, medida pelo auditor.

A regra que sai daqui, e que vale para toda leitura estática de comportamento
de framework: **ela só é defesa se vier com um teste de precedência** — dois
valores que existem, DIVERGEM, e o teste mede qual vence. É o que
`test_a_fonte_das_acoes_e_o_callback_e_o_initkwargs_e_so_retaguarda` já fazia
para o DRF e o que `test_o_django_deixa_a_rota_ampliar_http_method_names`
passa a fazer para o Django (405 pela rota estreita, 201 pela ampla, medidos
sobre a mesma classe).

E a generalização, porque `http_method_names` não é o único `initkwargs` capaz
de mudar o despacho — `as_view(post=outra_funcao)` também é aceito pelo Django
quando `post` não está no `http_method_names` da classe, e troca o handler na
instância: todo `initkwargs` que a varredura não resolva **reprova nomeando a
rota**, em vez de ser ignorado. Errar para o lado estrito é o que este arquivo
faz em todo lugar; era aqui que ele não fazia.

## O que esta varredura exige

**1. Toda superfície de escrita aplica a política.** Superfície de escrita é o
par (alvo alcançável, método de escrita HTTP) — e, num `ViewSet`, o **trio**
(alvo, ação, método), porque duas ações podem estar ligadas ao mesmo método
HTTP e o par faria uma apagar a outra. Descoberta assim:

- **Classe roteada como `ViewSet`**: os métodos vêm de `callback.actions` —
  o atributo que `ViewSetMixin.as_view` pendura na view, e que é o que o
  roteador REALMENTE liga (`{"post": "create"}` numa rota de lista,
  `{"post": "importar"}` numa rota de `@action`). Não
  `getattr(classe, "post")`, que é `None` em todo `ViewSet`, e não
  `initkwargs["actions"]`, que o roteador **nunca** preenche — o fato está
  preso por `test_o_roteador_do_drf_poe_actions_no_callback_e_nao_no_
  initkwargs`, medido sobre um `DefaultRouter` de verdade.
- **Demais classes** (`APIView`, `generics.*`, `django.views.View`): os
  handlers que a classe de fato tem, cruzados com os métodos que o DESPACHO
  permite. E o despacho lê `http_method_names` **da rota**: a varredura
  resolve `initkwargs.get("http_method_names", classe.http_method_names)`,
  que é literalmente como `dispatch()` resolve, **une** o resultado das várias
  rotas do mesmo alvo e soma o valor da classe — a soma é o lado estrito, e
  serve à classe descoberta sem rota nenhuma. O fato do Django está preso por
  `test_o_django_deixa_a_rota_ampliar_http_method_names` (BL-230/C1).
- **Qualquer outro `initkwargs` da rota**: ou está na lista curta do que a
  varredura sabe resolver (`http_method_names`, `actions`) ou na lista, também
  declarada, do que comprovadamente não muda o despacho (o que o roteador do
  DRF passa: `suffix`, `basename`, `detail`, `name`, `description`) — ou a
  rota entra em `nao_classificadas` e **reprova nomeada**, como forma não
  suportada. Não há ramo que ignore em silêncio um `initkwargs` desconhecido.
- **View de função**: pelos métodos que o **decorador declara**
  (`@require_POST`, `@require_http_methods`, `@require_safe`), lidos do
  objeto. Nunca por substring do fonte.

Para cada uma, o handler tem de chamar `recusar_dado_nao_contratado` — direta
ou por uma ponte do próprio app (uma indireção é resolvida, e a detecção é por
AST, nunca por substring: `inspect.getsource` de uma função chamada
`_recusar_dado_nao_contratado` contém o nome dela na própria linha do `def`, e
um teste por substring seria permanentemente verdadeiro, que é o defeito da
BL-197).

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

A regra de redação desta seção, depois da BL-217: **ela só pode dizer o que a
varredura entrega, medido**. A versão anterior prometia que uma view de função
que passasse a gravar "menciona `request.POST` e entra na varredura pelo mesmo
critério" — e isso era falso, e falso é pior que ausente, porque impede que
alguém vá conferir.

**O que não chega por requisição HTTP.** Escrita por ORM direto, pelo admin do
Django ou por management command não passa por nenhum handler de rota e não é
alcançada aqui. O admin é superfície nunca varrida e tem item próprio
(BL-211); management command não existe no repositório hoje.

**Código de terceiros.** O `admin/`, o `login/` e o `logout/` do urlconf têm
`__module__` fora de `apps.` e ficam de fora: as regras deste produto não
governam o código do Django. Essa fronteira não fica implícita — e não pode,
porque "o módulo não começa com `apps.`" é a forma mais barata de uma rota
desaparecer da varredura. `test_toda_rota_fora_dos_apps_e_de_terceiro_
conhecido` exige que todo callback descartado por esse filtro venha de um
prefixo de terceiro DECLARADO; qualquer outro reprova, nomeando a rota. O
admin tem item próprio (BL-211).

**View ainda não roteada.** A varredura parte do urlconf; uma view de função
escrita e não roteada não é alcançável por requisição e não aparece. As
`APIView` definidas em `apps/**/views*.py` entram mesmo sem rota, porque a
varredura de classes da BL-134 já as descobre e custa nada reaproveitar.

**Escrita por método HTTP de LEITURA.** A varredura equipara "superfície de
escrita" a "método de escrita HTTP" (`POST`, `PUT`, `PATCH`, `DELETE`). Uma
view decorada com `@require_safe` que gravasse em `GET` é invisível **por
construção** — e, agora que a classificação é por decorador declarado, ela é
invisível com o aval de um fato do objeto, o que é mais convincente que a
heurística anterior e por isso precisa estar escrito aqui. Nenhuma existe hoje
(BL-228/B8); a defesa contra ela é de revisão, não desta varredura.

**Middleware.** Middleware não é handler de rota, não aparece no urlconf e não
entra nesta varredura: um middleware que gravasse a partir do corpo da
requisição não seria visto. O produto tem **um**,
`apps.tenancy.middleware.EscritorioAtivoMiddleware`, que grava apenas
`request.session["escritorio_id"]` e não julga corpo de requisição —
conferido, não presumido. `test_o_unico_middleware_do_produto_continua_sendo_o
_do_escritorio_ativo` prende o fato: middleware novo de `apps.` reprova a
suíte, nomeando-o, para que a decisão de varrê-lo ou não seja de alguém.

**Rota ligada por roteador que não seja o `SimpleRouter`/`DefaultRouter`.**
Para um `ViewSet` **sem rota** (escrito hoje, roteado amanhã) a retaguarda
deriva as ações do próprio DRF: o mapa de `SimpleRouter.routes` unido a
`cls.get_extra_actions()`. Essas são as duas únicas fontes de que o
`SimpleRouter` dispõe, então a retaguarda é completa em relação a ele — e
somente a ele. Um roteador próprio, que ligasse `POST` a um método de nome
arbitrário, só seria visto depois de a rota existir (aí `callback.actions`
responde).

**Se a superfície tem TESTE dos cinco dicionários.** Esta varredura prova que
a política é CHAMADA, não que alguém a exercitou por requisição. Amarrar
superfície a arquivo de teste por casamento de nome seria uma promessa que o
próprio mecanismo não sustenta — o erro que a BL-213 nomeou. O elo que falta
tem item, dono e desenho próprios: **BL-218**.
"""

import ast
import inspect
import pathlib
import sys
import textwrap
from typing import NamedTuple

import pytest
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import get_resolver, path
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from rest_framework import routers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

# `conftest.py` da raiz. Importado — e não reimplementado — porque a fronteira
# "isto é código de teste?" precisa ser UMA, usada pelos dois lados: a
# instrumentação do elo de execução (BL-218) e esta varredura faziam a mesma
# pergunta com duas regras diferentes, e as duas tinham o mesmo buraco
# (BL-228/B7).
import conftest

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

# Nome do atributo que `ViewSetMixin.as_view` pendura NA VIEW (`view.actions =
# actions`). É a fonte de verdade sobre o que o roteador ligou, e não
# `initkwargs`, onde ele nunca aparece — foi ler o lugar errado que produziu a
# BL-221. `test_o_roteador_do_drf_poe_actions_no_callback_e_nao_no_initkwargs`
# mede os dois lados sobre um `DefaultRouter` real: se o DRF mudar de lugar, a
# suíte reprova alto e nomeado, em vez de a varredura voltar a ler `None` para
# sempre.
NOME_DO_ATRIBUTO_DE_ACOES_DO_DRF = "actions"

# Nome do atributo que `View.dispatch` consulta para decidir se o método da
# requisição é aceito. Ele é lido **da instância**, e `View.as_view` faz
# `setattr(self, chave, valor)` para cada `initkwargs` antes do `dispatch`:
# logo quem manda é o valor DA ROTA, e o da classe é só o padrão de quando a
# rota não passa nada (BL-230/C1). Ler o da classe era a terceira fuga da
# mesma família, e `test_o_django_deixa_a_rota_ampliar_http_method_names` mede
# a precedência em vez de afirmá-la.
NOME_DO_ATRIBUTO_DE_METODOS_DO_DISPATCH = "http_method_names"

# Os `initkwargs` que esta varredura sabe RESOLVER — isto é, cujo efeito sobre
# "qual handler responde a qual método HTTP" ela reproduz.
INITKWARGS_RESOLVIDOS_PELA_VARREDURA = frozenset(
    {NOME_DO_ATRIBUTO_DE_METODOS_DO_DISPATCH, NOME_DO_ATRIBUTO_DE_ACOES_DO_DRF}
)

# Os `initkwargs` que o roteador do DRF passa e que NÃO mudam o despacho:
# `suffix`/`name`/`description` só nomeiam a view na API navegável, `basename`
# é o prefixo dos nomes de rota e `detail` diz se a rota é de item ou de lista.
# Nenhum deles altera qual método HTTP chega a qual handler — o que altera é
# `actions`, que está na lista de cima. A lista é DECLARADA, e não presumida:
# `test_todo_initkwargs_que_o_roteador_do_drf_passa_e_conhecido` mede as chaves
# que um `DefaultRouter` real produz e reprova nomeando se aparecer uma nova.
INITKWARGS_SEM_EFEITO_NO_DESPACHO = frozenset(
    {"suffix", "basename", "detail", "name", "description"}
)

# Nome que `rest_framework.decorators.api_view` dá à classe que cria por
# `type(...)`. Ele ajusta `__name__` e `__module__` da classe para os da função
# embrulhada, mas NÃO o `__qualname__` — então duas views `@api_view` no mesmo
# módulo teriam a mesma chave e uma sumiria da varredura (BL-223/B3, forma b).
NOME_DA_CLASSE_CRIADA_PELO_API_VIEW = "WrappedAPIView"

# Nome da variável livre que `api_view` fecha sobre a função do desenvolvedor.
# O handler instalado na classe é a função `handler` do PRÓPRIO DRF, e
# `inspect.getsource` dela devolve fonte de terceiro que jamais chama a
# política: sem desembrulhar, a view seria acusada mesmo aplicando a política
# corretamente, e a saída para quem topasse com isso seria registrar a
# superfície na lista de exceções — que é como um registro vazio deixa de ser
# vazio pelo motivo errado (BL-224/B4). Se o DRF renomear a variável, o
# desembrulho falha e a view volta a ser ACUSADA: erra para o lado estrito.
NOME_DA_FUNCAO_FECHADA_PELO_API_VIEW = "func"


def _mapa_de_escrita_do_simple_router():
    """`{"post": {"create"}, ...}` — o mapa padrão do `SimpleRouter`, lido do
    PRÓPRIO DRF (`routers.SimpleRouter.routes`), não copiado para cá.

    Mesma escolha da BL-219 com o gerador de nomes de índice do Django: uma
    segunda cópia da gramática envelhece em silêncio; ler a fonte faz uma
    mudança do DRF aparecer como falha alta. `test_o_mapa_padrao_do_roteador_
    vem_do_proprio_drf` fixa o conteúdo esperado, para que a mudança seja
    também NOMEADA.
    """
    mapa = {}
    for rota in routers.SimpleRouter.routes:
        mapeamento = getattr(rota, "mapping", None) or {}
        for metodo, nome_da_acao in mapeamento.items():
            if metodo.lower() in METODOS_DE_ESCRITA:
                mapa.setdefault(metodo.lower(), set()).add(nome_da_acao)
    return {metodo: frozenset(nomes) for metodo, nomes in mapa.items()}


# Retaguarda, e SOMENTE retaguarda: vale para um `ViewSet` descoberto sem rota
# (escrito hoje, roteado amanhã). Quando há rota, quem manda é
# `callback.actions`. Para o `ViewSet` sem rota, este mapa é unido a
# `cls.get_extra_actions()` — as duas únicas fontes de que o `SimpleRouter`
# dispõe para montar URLs —, e é essa união que faz a retaguarda enxergar
# `@action` de nome próprio em vez de devolver `{}`.
ACOES_DE_ESCRITA_PADRAO_DO_ROTEADOR = _mapa_de_escrita_do_simple_router()

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
# sem a política, encontrada por ESTA varredura na segunda rodada da DL-020 e
# corrigida no mesmo passo (ver `_contrato_da_tela_de_empresa`), em vez de
# registrada como exceção.
SUPERFICIES_DE_ESCRITA_SEM_POLITICA = {}

# Formato: {"caminho.pontilhado.da.view": "razão escrita"} para uma view de
# função alcançável pelo urlconf que não declare os métodos que aceita. Vazio,
# e vazio é o estado desejado: a declaração custa uma linha e é o que impede
# a fuga (1) da BL-217 de voltar.
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
    um `import`. É exatamente o M17 da BL-197, na mesma etapa.
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

    BL-217. Este é o substituto da heurística textual `"request.method" in
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
# aqui — a varredura do admin contra as regras de negócio é a BL-211.
PREFIXOS_DE_MODULO_DE_TERCEIROS = ("django.", "rest_framework.")


class RotaDescoberta(NamedTuple):
    """Uma entrada do urlconf, com o que o roteador ligou nela.

    `acoes` é `{"post": "create"}` — o que `ViewSetMixin.as_view` pendurou no
    callback — ou `None` quando a rota não é de `ViewSet`. Guardar a rota
    inteira, e não só o alvo, é o que permite UNIR as ações das várias rotas do
    mesmo `ViewSet` em vez de deixar uma sobrescrever a outra (BL-223/B3).
    """

    alvo: object
    initkwargs: dict
    acoes: dict | None


def _acoes_ligadas_pelo_roteador(callback, initkwargs):
    """O `actions` que o roteador do DRF ligou neste callback, ou `None`.

    A FONTE é `callback.actions` (BL-221). `initkwargs["actions"]` fica como
    retaguarda porque um roteador de terceiro poderia passá-lo por
    `as_view(actions=...)` — mas o `SimpleRouter`/`DefaultRouter` do DRF nunca
    põe nada ali, e é por ter tratado a retaguarda como fonte que a varredura
    anterior nunca executou o mecanismo que anunciava.
    """
    acoes = getattr(callback, NOME_DO_ATRIBUTO_DE_ACOES_DO_DRF, None)
    if acoes is None and initkwargs:
        acoes = initkwargs.get(NOME_DO_ATRIBUTO_DE_ACOES_DO_DRF)
    if not isinstance(acoes, dict):
        return None
    return dict(acoes)


def _percorrer_callbacks(padroes):
    """`[RotaDescoberta, ...]` para uma lista de padrões de URL, sem nenhum
    filtro de módulo — é sobre esta lista crua que o filtro de terceiros é
    medido.

    Recebe os padrões como PARÂMETRO para que a demonstração da BL-221 possa
    registrar um `ViewSet` num `DefaultRouter` de verdade e ser lida por ESTE
    caminho, o mesmo do teste principal. Os dois mutantes anteriores passavam
    `initkwargs={"actions": ...}` à mão, numa forma que o roteador nunca
    produz, e por isso provavam um caminho que a produção não percorre — é
    exatamente o que deixou a BL-221 passar.
    """
    encontrados = []

    def percorrer(lista):
        for padrao in lista:
            if hasattr(padrao, "url_patterns"):
                percorrer(padrao.url_patterns)
                continue
            callback = getattr(padrao, "callback", None)
            if callback is None:
                continue
            alvo = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
            alvo = alvo or callback
            initkwargs = getattr(callback, "initkwargs", None) or {}
            encontrados.append(
                RotaDescoberta(alvo, initkwargs, _acoes_ligadas_pelo_roteador(callback, initkwargs))
            )

    percorrer(padroes)
    return encontrados


def _percorrer_callbacks_do_urlconf():
    return _percorrer_callbacks(get_resolver().url_patterns)


def nome_do_alvo(alvo):
    """O nome pelo qual o alvo é identificado na varredura.

    `__qualname__`, exceto quando ele é o `WrappedAPIView` que o `api_view` do
    DRF cria: nesse caso vale `__name__`, que o decorador ajusta para o nome da
    função do desenvolvedor. Sem isso, duas views `@api_view` no mesmo módulo
    produzem a mesma chave e **uma desaparece da varredura** — medido na
    BL-223/B3 e preso por `test_duas_views_api_view_no_mesmo_modulo_nao_
    colidem`.
    """
    qualname = getattr(alvo, "__qualname__", None) or getattr(alvo, "__name__", "")
    if qualname == NOME_DA_CLASSE_CRIADA_PELO_API_VIEW:
        return getattr(alvo, "__name__", qualname)
    return qualname


def rotas_fora_dos_apps():
    """`{"modulo.nome": modulo}` para todo callback do urlconf cujo módulo
    não é de `apps.` — a lista que o filtro descarta."""
    fora = {}
    for rota in _percorrer_callbacks_do_urlconf():
        modulo = getattr(rota.alvo, "__module__", "") or ""
        if modulo.startswith("apps."):
            continue
        fora[f"{modulo}.{nome_do_alvo(rota.alvo) or rota.alvo}"] = modulo
    return fora


class AlvoAlcancavel(NamedTuple):
    """`alvo` mais o que as rotas dele ligaram.

    `acoes_por_metodo` é `{"post": {"create", "importar"}}` — a UNIÃO das ações
    de todas as rotas do mesmo alvo — ou `None` quando não há rota de `ViewSet`
    (view de função, `APIView`, ou `ViewSet` ainda não roteado).

    `initkwargs_das_rotas` é a tupla dos `initkwargs` de CADA rota deste alvo,
    guardados um a um e nunca fundidos: `dispatch()` resolve por rota, e duas
    rotas do mesmo alvo podem permitir métodos diferentes. Descartá-los aqui
    foi o BL-230/C1 — a rota ampliava `http_method_names`, a varredura lia o da
    classe, e a superfície de escrita ficava invisível. O campo é OBRIGATÓRIO
    de propósito: com um padrão, o próximo caminho de construção voltaria ao
    comportamento antigo sem ninguém decidir.
    """

    alvo: object
    acoes_por_metodo: dict | None
    initkwargs_das_rotas: tuple


def _alvos_de(rotas):
    """`{"caminho.pontilhado": AlvoAlcancavel}` para as rotas de `apps.`.

    Rotas do MESMO alvo são unidas, nunca sobrescritas. Um `ViewSet` roteado
    gera duas entradas com a mesma chave — `{"get": "list", "post": "create"}`
    na rota de lista e `{"get": "retrieve", "put": "update", ...}` na de
    detalhe —, e a atribuição simples que existia aqui fazia a segunda apagar a
    primeira, levando junto o POST de `create` (BL-223/B3, forma a; medido pelo
    auditor).

    O mesmo molde vale para os `initkwargs` (BL-230/C1): eles são ACUMULADOS,
    rota a rota. Duas rotas do mesmo alvo, uma com `http_method_names` ampliado
    e outra sem, precisam somar os métodos — se a segunda sobrescrevesse a
    primeira, a superfície de escrita ampliada sumiria, que é exatamente o
    defeito que se está corrigindo, só que por outra porta.
    """
    alvos = {}
    for rota in rotas:
        modulo = getattr(rota.alvo, "__module__", "") or ""
        if not modulo.startswith("apps."):
            continue
        caminho = f"{modulo}.{nome_do_alvo(rota.alvo)}"
        anterior = alvos.get(caminho)
        acoes = (
            {metodo: set(nomes) for metodo, nomes in anterior.acoes_por_metodo.items()}
            if anterior and anterior.acoes_por_metodo
            else None
        )
        if rota.acoes is not None:
            acoes = acoes or {}
            for metodo, nome_da_acao in rota.acoes.items():
                acoes.setdefault(metodo.lower(), set()).add(nome_da_acao)
        initkwargs = (anterior.initkwargs_das_rotas if anterior else ()) + (dict(rota.initkwargs),)
        alvos[caminho] = AlvoAlcancavel(rota.alvo, acoes, initkwargs)
    return alvos


def colisoes_de_chave(rotas):
    """`{"caminho": [descrição, ...]}` para caminhos que duas rotas de alvos
    DIFERENTES reivindicam.

    Colisão de chave não é detalhe de implementação: é uma rota alcançável
    sumindo da varredura em silêncio, que é a classe inteira da BL-223.
    """
    por_caminho = {}
    for rota in rotas:
        modulo = getattr(rota.alvo, "__module__", "") or ""
        if not modulo.startswith("apps."):
            continue
        caminho = f"{modulo}.{nome_do_alvo(rota.alvo)}"
        por_caminho.setdefault(caminho, {})[id(rota.alvo)] = (
            f"{getattr(rota.alvo, '__qualname__', rota.alvo)} "
            f"(id {id(rota.alvo)}, ações {sorted(rota.acoes or {})})"
        )
    return {
        caminho: sorted(alvos.values()) for caminho, alvos in por_caminho.items() if len(alvos) > 1
    }


def _alvos_alcancaveis():
    """`{"caminho.pontilhado": AlvoAlcancavel}` — tudo que responde a uma
    requisição neste projeto.

    Parte do urlconf REAL, que é a pergunta certa ("o que está alcançável por
    requisição"), e não de nome de módulo mais heurística de substring.
    `view_class` é o atributo que o Django pendura em `View.as_view()`; `cls`,
    o que o DRF pendura em `APIView.as_view()`; `callback.actions`, o que o
    roteador do DRF ligou num `ViewSet` — é ele que fecha a fuga (2) da BL-217
    de verdade, depois da BL-221.

    As `APIView` definidas em `apps/**/views*.py` e ainda SEM rota entram
    depois, sem ações ligadas: custa nada, e uma view de escrita escrita hoje e
    roteada amanhã já nasce dentro da varredura.
    """
    alvos = _alvos_de(_percorrer_callbacks_do_urlconf())

    for classe in _apiviews_definidas_no_repositorio():
        alvos.setdefault(
            f"{classe.__module__}.{nome_do_alvo(classe)}", AlvoAlcancavel(classe, None, ())
        )

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


def _nomes_de_acao(nomes):
    """Aceita `"create"` ou `{"create", "importar"}` e devolve sempre um
    conjunto — o roteador liga UM nome por rota, mas o mesmo alvo pode ter
    várias rotas ligando o mesmo método HTTP a ações diferentes."""
    return {nomes} if isinstance(nomes, str) else set(nomes)


def acoes_de_escrita_ligadas(classe, acoes_por_metodo):
    """`{"post": {"create", "importar"}, ...}` para um `ViewSet`, ou `None`
    quando a classe não é `ViewSet` (aí quem responde é `http_method_names`).

    Duas situações, e a diferença entre elas é toda a BL-221:

    1. **Com rota** (`acoes_por_metodo` veio de `callback.actions`): manda o
       que o roteador de fato ligou, `@action` de nome próprio inclusive. Não
       há palpite nenhum aqui.
    2. **Sem rota** (`ViewSet` escrito hoje, roteado amanhã): a retaguarda é o
       mapa padrão do `SimpleRouter` UNIDO a `cls.get_extra_actions()` — as
       duas únicas fontes de que o `SimpleRouter` dispõe para montar URLs. A
       união é o que impede o defeito da BL-221 de voltar pela porta da
       retaguarda: só o mapa fixo devolveria `{}` para um `ViewSet` puro com
       `@action`, e `{}` é o lado errado do erro. Quando a união é vazia, isso
       é um FATO conferível sobre a classe (nenhum dos nomes padrão e nenhuma
       `@action` de escrita), não um silêncio.
    """
    if acoes_por_metodo is not None:
        return {
            metodo.lower(): _nomes_de_acao(nomes)
            for metodo, nomes in acoes_por_metodo.items()
            if metodo.lower() in METODOS_DE_ESCRITA
        }
    if not (isinstance(classe, type) and issubclass(classe, viewsets.ViewSetMixin)):
        return None

    ligadas = {}
    for metodo, nomes_padrao in ACOES_DE_ESCRITA_PADRAO_DO_ROTEADOR.items():
        for nome_da_acao in nomes_padrao:
            if getattr(classe, nome_da_acao, None) is not None:
                ligadas.setdefault(metodo, set()).add(nome_da_acao)
    for acao_extra in classe.get_extra_actions():
        for metodo, nome_da_acao in acao_extra.mapping.items():
            if metodo.lower() in METODOS_DE_ESCRITA:
                ligadas.setdefault(metodo.lower(), set()).add(nome_da_acao)
    return ligadas


def metodos_permitidos_pelo_despacho(classe, initkwargs_das_rotas=()):
    """Os métodos HTTP que o `dispatch()` desta classe aceita, considerando
    TODAS as rotas por onde ela é alcançável.

    Por rota, é literalmente a conta que o `dispatch()` faz:
    `initkwargs.get("http_method_names", classe.http_method_names)` — porque
    `View.as_view` faz `setattr(self, chave, valor)` e o `dispatch()` lê a
    instância. Entre rotas, **união**: a classe é alcançável por todas elas, e
    basta uma permitir o POST para o POST existir.

    O valor da CLASSE entra sempre na união, e isso é decisão de direção do
    erro, não descuido: uma classe descoberta sem rota (`APIView` escrita hoje,
    roteada amanhã) responde pelo próprio valor, e uma rota que RESTRINJA não
    apaga o handler de escrita que a classe declara — no máximo exigimos
    contrato de uma superfície que aquela rota específica recusaria com 405.
    Exigir contrato a mais custa uma linha; deixar de exigir foi o C1.
    """
    permitidos = {
        metodo.lower()
        for metodo in getattr(classe, NOME_DO_ATRIBUTO_DE_METODOS_DO_DISPATCH, METODOS_DE_ESCRITA)
    }
    for initkwargs in initkwargs_das_rotas:
        da_rota = initkwargs.get(NOME_DO_ATRIBUTO_DE_METODOS_DO_DISPATCH)
        if da_rota is None:
            continue
        permitidos |= {metodo.lower() for metodo in da_rota}
    return permitidos


def _handlers_por_http_method_names(classe, initkwargs_das_rotas=()):
    """`{"post": handler, ...}` para classe que NÃO é `ViewSet`: os handlers
    que a classe tem, cruzados com o que o despacho permite. Cobre também o
    `@api_view`, cujo `WrappedAPIView` tem `http_method_names` restrito ao que
    foi declarado."""
    permitidos = metodos_permitidos_pelo_despacho(classe, initkwargs_das_rotas)
    handlers = {}
    for metodo in METODOS_DE_ESCRITA:
        if metodo not in permitidos:
            continue
        handler = getattr(classe, metodo, None)
        if handler is not None:
            handlers[metodo] = handler
    return handlers


def initkwargs_nao_suportados(initkwargs_das_rotas):
    """As chaves de `initkwargs` que esta varredura não sabe resolver e não
    declarou inofensivas.

    `as_view(**initkwargs)` aceita qualquer nome que já seja atributo da
    classe, e o efeito pode ser qualquer um — inclusive trocar o handler:
    `as_view(post=outra_funcao)` é aceito pelo Django quando `post` não está no
    `http_method_names` da classe, e aí quem responde ao POST é a função da
    rota, que a varredura nunca leu. Como não dá para enumerar o efeito de
    todos, a lista é ao contrário: o que não está declarado REPROVA nomeado.
    """
    conhecidas = INITKWARGS_RESOLVIDOS_PELA_VARREDURA | INITKWARGS_SEM_EFEITO_NO_DESPACHO
    desconhecidas = set()
    for initkwargs in initkwargs_das_rotas:
        desconhecidas |= set(initkwargs) - conhecidas
    return desconhecidas


class Superficie(NamedTuple):
    """Uma superfície de escrita descoberta.

    `nome_efetivo` é o nome pelo qual o ELO DE EXECUÇÃO (BL-218) reconhece esta
    superfície na pilha, e ele identifica a superfície INTEIRA — os mesmos
    segmentos da chave, método HTTP incluído:
    `modulo.Classe.metodo`, `modulo.Classe.acao.metodo`, `modulo.funcao.metodo`.

    Duas correções moram nisso, e as duas são da mesma classe ("evidência de
    execução valendo para superfície que ninguém tocou"):

    - o nome é da CLASSE ROTEADA, não do código que define o handler — duas
      rotas que compartilhem o handler de um mixin têm nomes distintos
      (BL-226/B6);
    - o nome carrega o MÉTODO — um handler ligado a POST e a PUT tem duas
      superfícies e dois nomes, e exercitar uma não marca a outra (BL-232/C3).

    Que `nome_efetivo` coincida com a chave é invariante, e está preso por
    `test_o_nome_efetivo_de_toda_superficie_e_a_propria_chave`.
    """

    handler: object
    escopo: object
    nome_efetivo: str


def superficies_de_escrita(alvos):
    """`(superficies, nao_classificadas)` para os alvos dados.

    - `superficies`: `{"caminho[.acao].metodo": Superficie}`. O segmento da
      ação existe para `ViewSet` e é o que impede duas ações ligadas ao MESMO
      método HTTP (`create` pela rota de lista e `importar` por uma `@action`)
      de se apagarem — o par (alvo, método) não identifica uma superfície de
      `ViewSet`, o trio (alvo, ação, método) identifica.
    - `nao_classificadas`: `{"caminho": motivo}` para o que a varredura não
      SABE classificar, e por isso reprova em vez de presumir leitura.

    Recebe os alvos como PARÂMETRO, e não os busca por conta própria, para que
    os mutantes da BL-217 e da BL-221 possam ser reconstruídos dentro do
    próprio arquivo (molde da BL-197), sem depender de ninguém ter registrado
    que viu a suíte falhar e sem tocar em nenhuma view real.
    """
    superficies = {}
    nao_classificadas = {}

    for caminho, (alvo, acoes_por_metodo, initkwargs_das_rotas) in sorted(alvos.items()):
        escopo = _escopo_da_indirecao(alvo)
        desconhecidas = initkwargs_nao_suportados(initkwargs_das_rotas)
        if desconhecidas:
            # Reprova NOMEANDO, e as superfícies que a varredura consegue ver
            # continuam sendo emitidas logo abaixo: o desconhecido acrescenta
            # uma acusação, nunca retira uma exigência.
            nao_classificadas[caminho] = (
                f"a rota passa initkwargs que esta varredura não resolve: "
                f"{sorted(desconhecidas)} — `as_view(**initkwargs)` faz "
                "`setattr` na instância e pode mudar qual handler responde a "
                "qual método HTTP (é o caso de `http_method_names`, resolvido, "
                "e de `post=outra_funcao`, que o Django aceita). Resolva a "
                "chave na varredura ou declare-a em "
                "INITKWARGS_SEM_EFEITO_NO_DESPACHO, com a razão escrita"
            )
        if isinstance(alvo, type):
            ligadas = acoes_de_escrita_ligadas(alvo, acoes_por_metodo)
            if ligadas is None:
                for metodo, handler in _handlers_por_http_method_names(
                    alvo, initkwargs_das_rotas
                ).items():
                    nome = f"{caminho}.{metodo}"
                    superficies[nome] = Superficie(handler, escopo, nome)
                continue
            for metodo, nomes in sorted(ligadas.items()):
                for nome_da_acao in sorted(nomes):
                    # O MÉTODO entra no nome efetivo (BL-232/C3): uma `@action`
                    # ligada a POST e a PUT tem duas superfícies e precisa de
                    # dois nomes, senão exercitar uma marca a outra no elo da
                    # BL-218.
                    nome = f"{caminho}.{nome_da_acao}.{metodo}"
                    handler = getattr(alvo, nome_da_acao, None)
                    if handler is None:
                        # O roteador ligou um nome que a classe não tem. Não
                        # deveria acontecer com os roteadores do DRF; se
                        # acontecer, a varredura não sabe o que ler e reprova.
                        nao_classificadas[nome] = (
                            f"o roteador liga {metodo.upper()} à ação {nome_da_acao!r}, "
                            "que não existe nesta classe — a varredura não tem handler "
                            "para ler"
                        )
                        continue
                    superficies[nome] = Superficie(handler, escopo, nome)
            continue

        declarados = metodos_http_declarados(alvo)
        if declarados is None:
            nao_classificadas[caminho] = (
                "view de função alcançável pelo urlconf sem declarar os métodos que "
                "aceita — decore com @require_safe, @require_POST ou "
                "@require_http_methods([...])"
            )
            continue
        for metodo in sorted(declarados & METODOS_DE_ESCRITA_EM_MAIUSCULAS):
            # Idem BL-232/C3 para a view de função: `@require_http_methods(
            # ["POST", "PUT"])` produz duas superfícies, e o nome efetivo sem o
            # método fazia um teste de POST marcar o PUT como exercitado.
            nome = f"{caminho}.{metodo.lower()}"
            superficies[nome] = Superficie(alvo, escopo, nome)

    return superficies, nao_classificadas


def funcao_embrulhada_por_api_view(handler):
    """A função do desenvolvedor que um handler de `@api_view` embrulha, ou
    `None` quando não é esse caso.

    `api_view` instala como handler a função `handler` do PRÓPRIO DRF
    (`def handler(self, *args, **kwargs): return func(*args, **kwargs)`).
    `inspect.getsource` dela devolve fonte de terceiro que nunca chama a
    política: sem desembrulhar, uma view `@api_view(["POST"])` é acusada mesmo
    aplicando a política corretamente, e a única saída de quem topasse com isso
    seria registrar a superfície na lista de exceções — que é como um registro
    vazio deixa de ser vazio pelo motivo errado (BL-224/B4).

    Lê a variável livre pelo mesmo mecanismo com que `metodos_http_declarados`
    lê o decorador do Django, e com a mesma direção de erro: se o DRF renomear
    a variável, isto devolve `None`, o fonte volta a ser o do DRF e a view
    volta a ser ACUSADA. Estrito é o lado certo de errar.
    """
    codigo = getattr(handler, "__code__", None)
    celulas = getattr(handler, "__closure__", None) or ()
    if codigo is None or len(celulas) != len(codigo.co_freevars):
        return None
    if NOME_DA_FUNCAO_FECHADA_PELO_API_VIEW not in codigo.co_freevars:
        return None
    valor = celulas[codigo.co_freevars.index(NOME_DA_FUNCAO_FECHADA_PELO_API_VIEW)].cell_contents
    return valor if inspect.isfunction(valor) else None


def superficies_de_escrita_sem_politica(alvos=None):
    """`{"caminho[.acao].metodo": "motivo"}` para cada superfície de escrita
    que NÃO chega à política."""
    if alvos is None:
        alvos = _alvos_alcancaveis()
    superficies, _ = superficies_de_escrita(alvos)

    faltando = {}
    for nome, superficie in superficies.items():
        handler, escopo = superficie.handler, superficie.escopo
        embrulhada = funcao_embrulhada_por_api_view(handler)
        if embrulhada is not None:
            # A política e a ponte do app moram no módulo da função do
            # desenvolvedor, não na classe sintética do DRF.
            handler = embrulhada
            escopo = sys.modules.get(getattr(embrulhada, "__module__", "") or "")
        try:
            fonte = inspect.getsource(handler)
        except (OSError, TypeError) as erro:
            # BL-231/C2. `continue` aqui APROVAVA: a superfície era descoberta
            # e sumia da acusação, em silêncio, e este era o único ramo do
            # arquivo a errar para o lado permissivo — marcado, ainda por
            # cima, como declaradamente não exercitado. Handler sem fonte
            # nasce de fábrica de views, `functools.partial` ou código gerado
            # em tempo de execução, e a DL-010, com um importador por formato,
            # é candidata natural a isso. A regra do arquivo inteiro é "não
            # sei classificar → reprova nomeando", e agora ela vale aqui
            # também.
            faltando[nome] = (
                "a varredura não conseguiu ler o fonte do handler que responde a esta "
                f"superfície ({type(erro).__name__}: {erro}) — e ela não aprova o que "
                "não conseguiu ler. Um handler construído em tempo de execução (fábrica "
                "de views, partial, exec) precisa expor fonte legível ou ser roteado por "
                "uma função de módulo que a varredura consiga ler"
            )
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
        partes = caminho.relative_to(RAIZ).with_suffix("").parts
        # Mesma função que o elo de execução usa (BL-228/B7): duas regras
        # diferentes para "isto é código de teste?" é como as duas ficaram com
        # o mesmo buraco sem ninguém notar.
        if conftest.e_codigo_de_teste(".".join(partes)):
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

    BL-217, item 3 da correção: este controle usa **o mesmo caminho** do teste
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

    A pergunta mudou com a BL-217: antes era "o atributo ainda existe?"
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
    """BL-217, fuga (1). A varredura só pode dizer "isto não é superfície de
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
        "A varredura não sabe classificar isto, e não presume leitura:\n"
        + "\n".join(f"  {nome}: {motivo}" for nome, motivo in sorted(nao_autorizadas.items()))
        + "\n\nSe for view de função sem declaração de métodos: decore com "
        "@require_safe (só leitura), @require_POST ou @require_http_methods("
        "[...]). A declaração é o que permite a esta varredura saber se a view "
        "é superfície de escrita sem depender de procurar 'request.POST' no "
        "fonte — heurística que o auditor da rodada 1 contornou com uma view "
        "que grava lendo request.body.\n"
        "Se for forma de roteamento não suportada (initkwargs desconhecido, "
        "ação que a classe não tem), o motivo acima diz qual, e a saída é "
        "resolver a forma na varredura — o registro de exceções abaixo é só "
        "para view de função."
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
# As demonstrações, reconstruídas dentro do próprio teste (molde BL-197)
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
    """O M17 da BL-197 reconstruído nesta varredura: as três formas de o nome
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


# --- Fuga (1) da BL-217: a view de função que grava sem gatilho textual -----


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
@require_http_methods(["POST", "PUT"])
def _mutante_importar_por_post_e_put(request):  # pragma: no cover - objeto de medição
    """View de função ligada a DOIS métodos de escrita (BL-232/C3): duas
    superfícies, e antes da correção um só nome efetivo para as duas."""
    from apps.core.requisicao import recusar_dado_nao_contratado

    recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
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
    """Fuga (1) da BL-217, reconstruída e medida aqui dentro."""
    fonte = inspect.getsource(_mutante_conta_nova_json)

    # O fato que tornava a heurística textual falsa, preso como asserção: a
    # view grava e NÃO contém nenhum dos dois gatilhos que a versão anterior
    # procurava. Se alguém "consertar" este mutante acrescentando
    # `request.POST`, o teste falha aqui e não silenciosamente adiante.
    assert "request.method" not in fonte
    assert "request.POST" not in fonte

    alvos = {
        "apps.ficticio.views.conta_nova_json": AlvoAlcancavel(_mutante_conta_nova_json, None, ())
    }
    superficies, nao_classificadas = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.conta_nova_json.post"}
    assert nao_classificadas == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == {
        "apps.ficticio.views.conta_nova_json.post"
    }


def test_a_varredura_aprova_a_mesma_view_de_funcao_quando_ela_aplica_a_politica():
    alvos = {
        "apps.ficticio.views.conta_nova_json": AlvoAlcancavel(
            _mutante_conta_nova_json_com_politica, None, ()
        ),
    }
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.conta_nova_json.post"}
    assert superficies_de_escrita_sem_politica(alvos) == {}


def test_a_varredura_reprova_view_de_funcao_sem_declaracao_de_metodos():
    alvos = {
        "apps.ficticio.views.tela_nova": AlvoAlcancavel(
            _mutante_tela_sem_declaracao_de_metodos, None, ()
        )
    }
    superficies, nao_classificadas = superficies_de_escrita(alvos)

    assert superficies == {}
    assert set(nao_classificadas) == {"apps.ficticio.views.tela_nova"}


# --- Fuga (2) da BL-217: o ViewSet do DRF ----------------------------------


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
    duas ações de escrita aparecem, nomeadas pela AÇÃO e pelo método.

    E o mapa fixo NÃO se soma: este `ModelViewSet` herda `update` e
    `partial_update` do `UpdateModelMixin`, e mesmo assim PUT e PATCH não
    aparecem, porque o roteador não os ligou. É a asserção que prende a frase
    "a retaguarda não substitui o `actions` real" — que durante uma rodada
    inteira foi prosa, e falsa.
    """
    alvos = {
        "apps.ficticio.views.ContaViewSet": AlvoAlcancavel(
            _MutanteContaViewSetSemContrato,
            {"post": {"create"}, "delete": {"destroy"}},
            (),
        )
    }

    superficies, nao_classificadas = superficies_de_escrita(alvos)

    assert set(superficies) == {
        "apps.ficticio.views.ContaViewSet.create.post",
        "apps.ficticio.views.ContaViewSet.destroy.delete",
    }
    assert nao_classificadas == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == set(superficies)


def test_a_varredura_enxerga_o_viewset_mesmo_sem_rota_registrada():
    """Retaguarda: um `ViewSet` descoberto sem rota (escrito hoje, roteado
    amanhã) cai no mapa padrão do `SimpleRouter` — não some.

    Aparecem os QUATRO métodos, e não os dois que este mutante escreve à mão:
    `update`/`partial_update` vêm do `UpdateModelMixin` do DRF e respondem a
    PUT/PATCH de verdade assim que alguém rotear o `ViewSet` com o roteador
    padrão. Sem rota não há como saber quais ações serão ligadas, e a
    retaguarda erra para o lado de EXIGIR contrato — que é o lado certo.
    """
    alvos = {
        "apps.ficticio.views.ContaViewSet": AlvoAlcancavel(
            _MutanteContaViewSetSemContrato, None, ()
        )
    }

    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {
        "apps.ficticio.views.ContaViewSet.create.post",
        "apps.ficticio.views.ContaViewSet.update.put",
        "apps.ficticio.views.ContaViewSet.partial_update.patch",
        "apps.ficticio.views.ContaViewSet.destroy.delete",
    }


def test_a_varredura_aprova_o_viewset_que_aplica_a_politica():
    alvos = {
        "apps.ficticio.views.ContaViewSet": AlvoAlcancavel(
            _MutanteContaViewSetComContrato, {"post": {"create"}, "delete": {"destroy"}}, ()
        )
    }

    superficies, _ = superficies_de_escrita(alvos)

    assert len(superficies) == 2
    assert superficies_de_escrita_sem_politica(alvos) == {}


# --- BL-221: o ViewSet PURO com @action, roteado por um DefaultRouter real --
#
# Os mutantes acima passam as ações à mão. Isso é suficiente para medir a
# CLASSIFICAÇÃO, e insuficiente para medir a DESCOBERTA — e foi exatamente aí
# que a BL-221 se escondeu por uma rodada inteira: o roteador nunca produz
# `initkwargs={"actions": ...}`, então o caminho que os mutantes provavam não
# era o que a produção percorria. Os quatro testes abaixo partem de um
# `DefaultRouter` de verdade e são lidos pelo MESMO caminho do teste principal
# (`_percorrer_callbacks` → `_alvos_de` → `superficies_de_escrita`).


class _MutanteImportacaoViewSetSemContrato(viewsets.ViewSet):
    """`viewsets.ViewSet` PURO — não `ModelViewSet` — com uma `@action` de
    escrita de nome próprio.

    É a forma que o auditor mediu produzindo ZERO superfícies, e é o formato
    mais natural que existe no DRF para a recepção de documentos fiscais da
    DL-010: `@action(detail=False, methods=["post"]) def importar`. Nenhum dos
    quatro nomes do mapa fixo (`create`, `update`, `partial_update`,
    `destroy`) existe aqui, que é por isso que o mapa fixo devolvia `{}`.
    """

    @action(detail=False, methods=["post"])
    def importar(self, request):  # pragma: no cover - objeto de medição
        return _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])


class _MutanteImportacaoViewSetComContrato(viewsets.ViewSet):
    """O mesmo `ViewSet` puro, com a política na ação de escrita."""

    @action(detail=False, methods=["post"])
    def importar(self, request):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])


def _rotas_de_um_roteador_real(viewset, basename):
    """As rotas que um `DefaultRouter` de verdade gera para `viewset`, lidas
    pelo mesmo `_percorrer_callbacks` do teste principal."""
    roteador = routers.DefaultRouter()
    roteador.register(f"{basename}", viewset, basename=basename)
    return _percorrer_callbacks(roteador.urls)


def test_o_roteador_do_drf_poe_actions_no_callback_e_nao_no_initkwargs():
    """BL-222/B2: a afirmação sobre o DRF vira asserção SOBRE o DRF.

    O arquivo diz, em três lugares, que os métodos vêm do que o roteador liga.
    Enquanto isso era prosa, ele afirmou durante uma rodada inteira que lia
    `initkwargs["actions"]` — que o roteador nunca preenche. Aqui o fato é
    medido num `DefaultRouter` real: se o DRF mudar de lugar, isto falha alto
    e nomeado, em vez de a varredura voltar a ler `None` para sempre.
    """
    roteador = routers.DefaultRouter()
    roteador.register("conta", _MutanteContaViewSetSemContrato, basename="conta")

    ligados = {}
    for padrao in roteador.urls:
        callback = padrao.callback
        acoes = getattr(callback, "actions", None)
        if acoes is None:
            continue  # a rota do índice da API do DefaultRouter não é ViewSet
        assert "actions" not in callback.initkwargs, callback.initkwargs
        ligados[padrao.name] = acoes

    assert ligados["conta-list"] == {"get": "list", "post": "create"}
    assert ligados["conta-detail"] == {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }


def test_a_fonte_das_acoes_e_o_callback_e_o_initkwargs_e_so_retaguarda():
    """A ordem das duas fontes, medida.

    O arquivo afirma que `initkwargs["actions"]` "continua sendo lido, mas
    como retaguarda". Afirmação sobre precedência precisa de teste de
    precedência: aqui os dois valores existem e DIVERGEM, e vence o do
    callback. Foi tratar a retaguarda como fonte que fez o mecanismo anunciado
    na rodada anterior nunca executar.
    """

    class CallbackFalso:  # pragma: no cover - objeto de medição
        pass

    callback = CallbackFalso()
    callback.actions = {"post": "create"}
    initkwargs = {"actions": {"post": "acao_de_retaguarda"}}

    assert _acoes_ligadas_pelo_roteador(callback, initkwargs) == {"post": "create"}

    del callback.actions
    assert _acoes_ligadas_pelo_roteador(callback, initkwargs) == {"post": "acao_de_retaguarda"}
    assert _acoes_ligadas_pelo_roteador(CallbackFalso(), {}) is None


def test_o_mapa_padrao_do_roteador_vem_do_proprio_drf():
    """A retaguarda é derivada de `routers.SimpleRouter.routes`, não copiada.
    Este teste fixa o conteúdo esperado para que uma mudança do DRF apareça
    como falha nomeada, e não como retaguarda silenciosamente mais estreita."""
    assert ACOES_DE_ESCRITA_PADRAO_DO_ROTEADOR == {
        "post": frozenset({"create"}),
        "put": frozenset({"update"}),
        "patch": frozenset({"partial_update"}),
        "delete": frozenset({"destroy"}),
    }
    assert any(
        getattr(rota, "mapping", None) == {"get": "list", "post": "create"}
        for rota in routers.SimpleRouter.routes
    )


def test_a_varredura_enxerga_action_de_escrita_de_nome_proprio_em_roteador_real():
    """**O mutante da BL-221.** `ViewSet` puro com `@action(detail=False,
    methods=["post"])` que grava, roteado por um `DefaultRouter` de verdade.

    Antes da correção este caso produzia ZERO superfícies. Agora a superfície
    aparece nomeada pela AÇÃO (`...importar.post`) e é acusada por não chamar
    a política.
    """
    rotas = _rotas_de_um_roteador_real(_MutanteImportacaoViewSetSemContrato, "importacao")

    # O fato que a torna um teste de DESCOBERTA e não de classificação: o
    # roteador não passou nada por `initkwargs`, e a rota da `@action` existe.
    acoes_por_rota = [rota.acoes for rota in rotas if rota.acoes]
    assert {"post": "importar"} in acoes_por_rota
    assert all("actions" not in rota.initkwargs for rota in rotas)

    alvos = _alvos_de(rotas)
    superficies, nao_classificadas = superficies_de_escrita(alvos)

    esperada = (
        "apps.core.tests.test_dl019_varredura_de_contratos."
        "_MutanteImportacaoViewSetSemContrato.importar.post"
    )
    assert set(superficies) == {esperada}
    assert nao_classificadas == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == {esperada}


def test_a_varredura_aprova_o_mesmo_viewset_puro_quando_ele_aplica_a_politica():
    """Par positivo do mutante acima: sem ele, uma varredura que acusasse TUDO
    também passaria na metade de cima."""
    alvos = _alvos_de(_rotas_de_um_roteador_real(_MutanteImportacaoViewSetComContrato, "imp2"))
    superficies, _ = superficies_de_escrita(alvos)

    assert len(superficies) == 1
    assert superficies_de_escrita_sem_politica(alvos) == {}


def test_a_retaguarda_enxerga_action_de_nome_proprio_em_viewset_sem_rota():
    """O `{}` que era o lado errado do erro.

    Sem rota, o mapa fixo sozinho não tem o que casar num `ViewSet` puro e
    devolvia `{}` — a superfície sumia. A retaguarda passou a ser o mapa do
    `SimpleRouter` UNIDO a `get_extra_actions()`, que são as duas únicas
    fontes do roteador: a `@action` de escrita aparece mesmo antes de existir
    rota.
    """
    alvos = {
        "apps.ficticio.views.ImportacaoViewSet": AlvoAlcancavel(
            _MutanteImportacaoViewSetSemContrato, None, ()
        )
    }
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.ImportacaoViewSet.importar.post"}


def test_as_duas_rotas_de_um_viewset_nao_se_apagam():
    """BL-223/B3, forma (a). Um `ViewSet` roteado gera duas rotas com o mesmo
    `modulo.qualname`: a de lista (`{"get": "list", "post": "create"}`) e a de
    detalhe (`{"get": "retrieve", "put": "update", ...}`).

    Com a atribuição simples que existia aqui, a segunda apagava a primeira e
    o POST de `create` DESAPARECIA — medido pelo auditor. Agora as ações são
    unidas, e os quatro métodos de escrita continuam visíveis.
    """
    rotas = _rotas_de_um_roteador_real(_MutanteContaViewSetSemContrato, "conta")
    caminhos = [f"{rota.alvo.__module__}.{nome_do_alvo(rota.alvo)}" for rota in rotas if rota.acoes]

    # O fato que produzia a colisão, preso: as rotas de lista e de detalhe
    # reivindicam a MESMA chave (e o `DefaultRouter` ainda duplica cada uma
    # pelos sufixos de formato). O que mudou não foi a chave — foi ela deixar
    # de sobrescrever.
    assert len(caminhos) >= 2
    assert len(set(caminhos)) == 1

    alvos = _alvos_de(rotas)
    superficies, _ = superficies_de_escrita(alvos)
    prefixo = "apps.core.tests.test_dl019_varredura_de_contratos._MutanteContaViewSetSemContrato"

    assert set(superficies) == {
        f"{prefixo}.create.post",
        f"{prefixo}.update.put",
        f"{prefixo}.partial_update.patch",
        f"{prefixo}.destroy.delete",
    }


# --- BL-223/B3, forma (b), e BL-224/B4: as views de `@api_view` -------------


@api_view(["POST"])
def _mutante_importar_xml(request):  # pragma: no cover - objeto de medição
    """`@api_view` que grava sem a política."""
    return _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])


@api_view(["POST"])
def _mutante_importar_sped(request):  # pragma: no cover - objeto de medição
    """A segunda `@api_view` do mesmo módulo: é o par que produz a colisão de
    chave, porque as duas classes sintéticas têm o mesmo `__qualname__`."""
    from apps.core.requisicao import recusar_dado_nao_contratado

    recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
    return _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])


def test_duas_views_api_view_no_mesmo_modulo_nao_colidem():
    """BL-223/B3, forma (b). `api_view` cria a classe por `type(...)` e ajusta
    `__name__` e `__module__`, **mas não `__qualname__`** — as duas ficam
    `WrappedAPIView`. Com a chave por qualname, uma das duas DESAPARECIA da
    varredura em silêncio."""
    classes = [_mutante_importar_xml.cls, _mutante_importar_sped.cls]

    # O fato do DRF, preso como asserção.
    assert [classe.__qualname__ for classe in classes] == [
        NOME_DA_CLASSE_CRIADA_PELO_API_VIEW,
        NOME_DA_CLASSE_CRIADA_PELO_API_VIEW,
    ]
    assert [nome_do_alvo(classe) for classe in classes] == [
        "_mutante_importar_xml",
        "_mutante_importar_sped",
    ]

    rotas = [RotaDescoberta(classe, {}, None) for classe in classes]
    alvos = _alvos_de(rotas)

    assert len(alvos) == 2
    assert colisoes_de_chave(rotas) == {}


def test_a_varredura_detecta_colisao_de_chave_em_vez_de_sobrescrever():
    """Par negativo: se duas rotas de alvos DIFERENTES reivindicarem o mesmo
    caminho, isso é uma rota sumindo em silêncio — e a varredura precisa
    dizê-lo. Reconstruído com duas classes de mesmo nome em módulos
    homônimos."""

    class Colidente:  # pragma: no cover - objeto de medição
        __module__ = "apps.ficticio.views"
        __qualname__ = "Colidente"

    class Outra:  # pragma: no cover - objeto de medição
        __module__ = "apps.ficticio.views"
        __qualname__ = "Colidente"

    colisoes = colisoes_de_chave(
        [RotaDescoberta(Colidente, {}, None), RotaDescoberta(Outra, {}, None)]
    )

    assert set(colisoes) == {"apps.ficticio.views.Colidente"}
    assert len(colisoes["apps.ficticio.views.Colidente"]) == 2


def test_nenhuma_chave_de_alvo_colide_no_urlconf_real():
    """O par acima aplicado ao urlconf de verdade: nenhuma rota deste produto
    pode estar sumindo por chave repetida."""
    colisoes = colisoes_de_chave(_percorrer_callbacks_do_urlconf())

    assert colisoes == {}, (
        "Duas rotas de alvos diferentes reivindicam o mesmo caminho na "
        f"varredura, e uma delas some em silêncio:\n{colisoes}"
    )


def test_api_view_que_aplica_a_politica_nao_e_acusada():
    """BL-224/B4. O handler que `api_view` instala é a função `handler` do
    PRÓPRIO DRF, e `inspect.getsource` dela devolve fonte de terceiro que nunca
    chama a política: sem desembrulhar, a view seria acusada mesmo aplicando a
    política corretamente, e a saída de quem topasse com isso seria registrar a
    superfície na lista de exceções — enchendo pelo motivo errado o registro
    que hoje é a defesa mais forte deste arquivo.
    """
    handler = _mutante_importar_sped.cls.post

    # Os dois fatos que o auditor mediu, presos como asserção.
    assert handler.__module__ == "rest_framework.decorators"
    assert NOME_DA_POLITICA not in inspect.getsource(handler)

    embrulhada = funcao_embrulhada_por_api_view(handler)
    # Asserção antes de uso: se o desembrulho parar de funcionar, a morte deste
    # teste é por ASSERÇÃO NOMEADA e não por `AttributeError` num `None` — o
    # ponto fraco que a BL-216 registrou honestamente no mutante 11.
    assert embrulhada is not None, (
        "O desembrulho do @api_view parou de achar a função do desenvolvedor. "
        "A varredura volta a ler o fonte do DRF e a acusar toda @api_view, e a "
        "saída de quem topar com isso é a lista de exceções."
    )
    assert embrulhada.__name__ == "_mutante_importar_sped"

    alvos = {
        "apps.ficticio.views.importar_sped": AlvoAlcancavel(_mutante_importar_sped.cls, None, ())
    }
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.importar_sped.post"}
    assert superficies_de_escrita_sem_politica(alvos) == {}


def test_api_view_que_nao_aplica_a_politica_continua_acusada():
    """Par negativo do anterior: desembrulhar não pode virar dispensa."""
    alvos = {
        "apps.ficticio.views.importar_xml": AlvoAlcancavel(_mutante_importar_xml.cls, None, ())
    }

    assert set(superficies_de_escrita_sem_politica(alvos)) == {
        "apps.ficticio.views.importar_xml.post"
    }


# --- BL-226/B6: duas rotas que compartilham o handler de um mixin -----------


class _MutanteMixinDeImportacao(APIView):
    """Handler de escrita compartilhado por duas views — o desenho provável da
    DL-010 (duas rotas de importação com o mesmo `post`)."""

    def post(self, request):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return None


class _MutanteImportarXmlView(_MutanteMixinDeImportacao):
    """Primeira rota."""


class _MutanteImportarSpedView(_MutanteMixinDeImportacao):
    """Segunda rota, com o MESMO objeto de handler."""


def test_duas_superficies_com_o_mesmo_handler_tem_nomes_efetivos_distintos():
    """BL-226/B6. O registro do elo de execução aceitava
    `f"{modulo}.{qualname}"` do handler — e o qualname do handler de um mixin é
    o MESMO nos dois. Exercitar uma rota marcava a outra como exercitada, sem
    ninguém a ter tocado.

    O nome efetivo passou a ser o da CLASSE ROTEADA. Aqui o handler é
    literalmente o mesmo objeto nas duas superfícies, e mesmo assim os nomes
    efetivos diferem.
    """
    alvos = {
        "apps.ficticio.views.ImportarXmlView": AlvoAlcancavel(_MutanteImportarXmlView, None, ()),
        "apps.ficticio.views.ImportarSpedView": AlvoAlcancavel(_MutanteImportarSpedView, None, ()),
    }
    superficies, _ = superficies_de_escrita(alvos)

    xml = superficies["apps.ficticio.views.ImportarXmlView.post"]
    sped = superficies["apps.ficticio.views.ImportarSpedView.post"]

    assert xml.handler is sped.handler
    assert xml.handler.__qualname__ == "_MutanteMixinDeImportacao.post"
    assert xml.nome_efetivo == "apps.ficticio.views.ImportarXmlView.post"
    assert sped.nome_efetivo == "apps.ficticio.views.ImportarSpedView.post"


# --- BL-228/B8: a fronteira "middleware", declarada e conferível ------------


def test_o_unico_middleware_do_produto_continua_sendo_o_do_escritorio_ativo():
    """A seção "O que ela NÃO cobre" afirma que middleware fica de fora e que o
    produto tem um só. Afirmação sobre o repositório precisa de verificação
    sobre o repositório: um middleware novo de `apps.` reprova aqui, nomeado,
    para que alguém decida se ele é superfície de escrita."""
    proprios = [caminho for caminho in settings.MIDDLEWARE if caminho.startswith("apps.")]

    assert proprios == ["apps.tenancy.middleware.EscritorioAtivoMiddleware"], (
        "A fronteira declarada no docstring deste arquivo diz que o produto tem "
        "UM middleware próprio, que só grava na sessão. Esta lista mudou: "
        f"{proprios}. Decida se o novo é superfície de escrita e atualize a "
        "seção — não deixe a fronteira afirmar mais do que o repositório tem."
    )


# --- BL-230/C1: o `http_method_names` que a ROTA amplia ---------------------
#
# A terceira fuga da mesma família, e a razão de esta seção existir com um
# teste de PRECEDÊNCIA na frente dos mutantes: enquanto "é assim que o
# `dispatch()` escolhe o handler" foi prosa, ela ficou falsa por três rodadas.
# Aqui os dois valores existem, divergem, e o teste mede qual vence.
#
# As rotas destes mutantes vêm de `path()` de verdade — passar `initkwargs` à
# mão foi o que deixou a BL-221 se esconder por uma rodada inteira.


class _MutanteEstreitaViewSemContrato(APIView):
    """`APIView` que RESTRINGE `http_method_names` na classe e mesmo assim tem
    um `post` que grava a partir de `request.data`, sem a política.

    É o M-C1 do auditor: roteada com `as_view(http_method_names=["get",
    "post"])`, ela respondia **201 e gravava** enquanto a varredura acusava
    nada — `TOTAL 14, ACUSADAS {}`, a assinatura do B1.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get"]

    def get(self, request):  # pragma: no cover - objeto de medição
        return Response({"ok": True})

    def post(self, request):  # pragma: no cover - objeto de medição
        _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])
        return Response({"gravou": True}, status=201)


class _MutanteEstreitaViewComContrato(APIView):
    """A mesma view, com a política. Sem o par, uma varredura que acusasse
    TUDO passaria na metade de cima."""

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get"]

    def get(self, request):  # pragma: no cover - objeto de medição
        return Response({"ok": True})

    def post(self, request):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])
        return Response({"gravou": True}, status=201)


def _rotas_de_um_path_real(*views):
    """As rotas que `path()` de verdade produz para estas views, lidas pelo
    mesmo `_percorrer_callbacks` do teste principal.

    Recebe o resultado de `as_view(...)`, que é onde os `initkwargs` entram —
    o ponto exato em que a produção os cria, e não uma imitação deles.
    """
    return _percorrer_callbacks(
        [
            path(f"mutante-{indice}/", view, name=f"mutante-{indice}")
            for indice, view in enumerate(views)
        ]
    )


_PREFIXO_DOS_MUTANTES = "apps.core.tests.test_dl019_varredura_de_contratos"


def test_o_django_deixa_a_rota_ampliar_http_method_names():
    """**O teste de precedência do `http_method_names`**, o molde que faltava.

    Dois valores existem e DIVERGEM: `["get"]` na classe e `["get", "post"]`
    nos `initkwargs` da rota. O que este teste afirma sobre o Django é que
    vence o da ROTA — porque `View.as_view` guarda os `initkwargs` e o `view()`
    interno faz `setattr(self, chave, valor)` antes do `dispatch()`, que lê a
    instância.

    Medido pelos dois lados, com a MESMA classe: a rota estreita responde
    **405** ao POST e a ampliada responde **201**. Se o Django mudar essa
    resolução, isto falha alto e nomeado — em vez de a varredura voltar a ler
    o valor da classe para sempre, que é o achado C1.
    """
    fabrica = APIRequestFactory()
    estreita = _MutanteEstreitaViewSemContrato.as_view()
    ampla = _MutanteEstreitaViewSemContrato.as_view(http_method_names=["get", "post"])

    # Os dois valores, e a divergência entre eles.
    assert _MutanteEstreitaViewSemContrato.http_method_names == ["get"]
    assert estreita.initkwargs == {}
    assert ampla.initkwargs == {"http_method_names": ["get", "post"]}

    # Qual vence, em tempo de execução.
    corpo = {"codigo": "1.1.1", "nome": "Caixa"}
    assert estreita(fabrica.post("/x/", corpo, format="json")).status_code == 405
    assert ampla(fabrica.post("/x/", corpo, format="json")).status_code == 201

    # E a classe continua intocada: quem foi alterado é a INSTÂNCIA de cada
    # requisição, que é por que ler a classe não responde à pergunta.
    assert _MutanteEstreitaViewSemContrato.http_method_names == ["get"]


def test_a_varredura_le_o_http_method_names_da_rota_e_nao_o_da_classe():
    """**O mutante M-C1, reconstruído aqui dentro, com rota de `path()`
    real.**

    Antes da correção este caso produzia ZERO superfícies: a rota era
    descoberta, os `initkwargs` eram até guardados em `RotaDescoberta` — e
    `_alvos_de` os jogava fora. Agora a superfície aparece e é acusada.
    """
    rotas = _rotas_de_um_path_real(
        _MutanteEstreitaViewSemContrato.as_view(http_method_names=["get", "post"])
    )

    # O que torna isto um teste de DESCOBERTA e não de classificação: os
    # `initkwargs` vieram do `as_view` real, pela rota real.
    assert [rota.initkwargs for rota in rotas] == [{"http_method_names": ["get", "post"]}]

    alvos = _alvos_de(rotas)
    assert [alvo.initkwargs_das_rotas for alvo in alvos.values()] == [
        ({"http_method_names": ["get", "post"]},)
    ]

    superficies, nao_classificadas = superficies_de_escrita(alvos)
    esperada = f"{_PREFIXO_DOS_MUTANTES}._MutanteEstreitaViewSemContrato.post"

    assert set(superficies) == {esperada}
    assert nao_classificadas == {}
    assert set(superficies_de_escrita_sem_politica(alvos)) == {esperada}


def test_a_varredura_aprova_a_mesma_view_estreita_quando_ela_aplica_a_politica():
    alvos = _alvos_de(
        _rotas_de_um_path_real(
            _MutanteEstreitaViewComContrato.as_view(http_method_names=["get", "post"])
        )
    )
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {f"{_PREFIXO_DOS_MUTANTES}._MutanteEstreitaViewComContrato.post"}
    assert superficies_de_escrita_sem_politica(alvos) == {}


def test_a_rota_que_restringe_nao_apaga_a_rota_que_amplia():
    """BL-230, item 1: rotas do mesmo alvo UNEM os métodos, nunca
    sobrescrevem — o mesmo molde já usado para as ações de `ViewSet`.

    Duas rotas para a mesma classe, uma sem `initkwargs` e outra ampliando, nas
    DUAS ordens: se a segunda sobrescrevesse a primeira, o POST sumiria numa
    das ordens e o defeito voltaria por outra porta.
    """
    esperada = f"{_PREFIXO_DOS_MUTANTES}._MutanteEstreitaViewSemContrato.post"

    for views in (
        (
            _MutanteEstreitaViewSemContrato.as_view(),
            _MutanteEstreitaViewSemContrato.as_view(http_method_names=["get", "post"]),
        ),
        (
            _MutanteEstreitaViewSemContrato.as_view(http_method_names=["get", "post"]),
            _MutanteEstreitaViewSemContrato.as_view(),
        ),
    ):
        alvos = _alvos_de(_rotas_de_um_path_real(*views))
        superficies, _ = superficies_de_escrita(alvos)

        assert len(alvos) == 1
        assert len(next(iter(alvos.values())).initkwargs_das_rotas) == 2
        assert set(superficies) == {esperada}


def test_o_valor_da_classe_continua_valendo_quando_a_rota_nao_diz_nada():
    """Par negativo da resolução: sem `initkwargs`, quem responde é o valor da
    classe — que é o `dispatch()` de novo, e é o caso das 14 superfícies de
    hoje. Sem isto, "a varredura lê a rota" poderia ter virado "a varredura
    deixou de ler a classe"."""
    assert metodos_permitidos_pelo_despacho(_MutanteEstreitaViewSemContrato, ()) == {"get"}
    assert metodos_permitidos_pelo_despacho(
        _MutanteEstreitaViewSemContrato, ({"http_method_names": ["get", "post"]},)
    ) == {"get", "post"}
    assert "post" in metodos_permitidos_pelo_despacho(_MutanteImportarXmlView, ())


def _outro_post(request):  # pragma: no cover - objeto de medição
    """Handler injetado pela ROTA, que a varredura nunca leu — e que responde
    ao POST de verdade (medido no teste abaixo)."""
    return Response({"handler": "o da rota"}, status=202)


def test_a_varredura_reprova_initkwargs_que_ela_nao_sabe_resolver():
    """BL-230, item 2: a generalização.

    `http_method_names` não é o único `initkwargs` capaz de mudar o despacho.
    `as_view(post=outra_funcao)` é ACEITO pelo Django sempre que `post` não
    está no `http_method_names` da classe — e o handler da rota passa a
    responder, com fonte que a varredura nunca abriu. Não dá para enumerar o
    efeito de todo atributo de classe; dá para exigir que o desconhecido
    reprove nomeado, que é o que o arquivo faz em todo lugar menos aqui.
    """
    fabrica = APIRequestFactory()
    view = _MutanteEstreitaViewSemContrato.as_view(
        http_method_names=["get", "post"], post=_outro_post
    )

    # O fato do Django, preso como asserção: aceito, e é ele que responde.
    assert sorted(view.initkwargs) == ["http_method_names", "post"]
    resposta = view(fabrica.post("/x/", {"codigo": "1", "nome": "n"}, format="json"))
    assert resposta.status_code == 202

    alvos = _alvos_de(_rotas_de_um_path_real(view))
    caminho = f"{_PREFIXO_DOS_MUTANTES}._MutanteEstreitaViewSemContrato"
    _, nao_classificadas = superficies_de_escrita(alvos)

    assert set(nao_classificadas) == {caminho}
    assert "'post'" in nao_classificadas[caminho]


def test_todo_initkwargs_que_o_roteador_do_drf_passa_e_conhecido():
    """A outra ponta da generalização: ela não pode acusar o uso NORMAL.

    O roteador do DRF passa `suffix`/`name`/`description`/`basename`/`detail`
    em toda rota de `ViewSet`. Nenhum muda qual método chega a qual handler —
    quem faz isso é `actions`, que a varredura resolve. Este teste mede as
    chaves que um `DefaultRouter` de verdade produz: se o DRF passar uma chave
    nova, ela aparece aqui NOMEADA, em vez de o `ViewSet` inteiro começar a
    reprovar sem explicação (ou, pior, a chave nova mudar o despacho sem
    ninguém olhar).
    """
    rotas = [
        rota
        for rota in _rotas_de_um_roteador_real(_MutanteImportacaoViewSetSemContrato, "importacao3")
        if getattr(rota.alvo, "__module__", "").startswith("apps.")
    ]
    chaves = {chave for rota in rotas for chave in rota.initkwargs}

    assert chaves == {"name", "description", "basename", "detail"}, sorted(chaves)
    assert initkwargs_nao_suportados([rota.initkwargs for rota in rotas]) == set()
    # A rota de lista de um `ViewSet` com `create` traz `suffix`; o mutante
    # acima só tem `@action`, então o conjunto acima não o exercita.
    assert "suffix" in {
        chave
        for rota in _rotas_de_um_roteador_real(_MutanteContaViewSetSemContrato, "conta3")
        for chave in rota.initkwargs
    }


def test_nenhuma_rota_do_urlconf_real_usa_initkwargs_desconhecido():
    """A generalização aplicada ao urlconf de verdade. Hoje NENHUMA rota deste
    produto passa `initkwargs` — estado mais forte possível, e é este teste que
    faz a primeira que passar ser uma decisão de alguém."""
    por_alvo = {
        caminho: alvo.initkwargs_das_rotas for caminho, alvo in _alvos_alcancaveis().items()
    }
    desconhecidos = {
        caminho: sorted(initkwargs_nao_suportados(initkwargs))
        for caminho, initkwargs in por_alvo.items()
        if initkwargs_nao_suportados(initkwargs)
    }

    assert not desconhecidos, (
        "Estas rotas passam initkwargs que a varredura não resolve, e um "
        "initkwargs pode mudar qual handler responde a qual método HTTP:\n"
        f"{desconhecidos}"
    )


# --- BL-231/C2: fonte ilegível reprova, e não aprova em silêncio ------------


class _MutanteSemFonteView(APIView):
    """Classe cujo `post` é instalado abaixo a partir de código COMPILADO em
    memória — `inspect.getsource` não tem arquivo para ler.

    É a forma que nasce com fábrica de views, `functools.partial` ou handler
    montado em tempo de execução, e a DL-010, com um importador por formato, é
    candidata natural a isso.
    """


class _MutanteComFonteView(APIView):
    """O par legível da classe acima: mesmo desenho, fonte que existe, e a
    política aplicada."""

    def post(self, request):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return None


def _handler_compilado_em_memoria():
    """Um handler de verdade, sem arquivo de origem. `exec` é o jeito mais
    curto de produzir exatamente a condição que o auditor mediu."""
    espaco = {}
    exec(
        compile(
            "def post(self, request):\n    return request.data\n",
            "<gerado em tempo de execução>",
            "exec",
        ),
        espaco,
    )
    return espaco["post"]


_MutanteSemFonteView.post = _handler_compilado_em_memoria()


def test_a_varredura_reprova_a_superficie_cujo_fonte_ela_nao_consegue_ler():
    """BL-231/C2. `except (OSError, TypeError): continue` APROVAVA: a
    superfície era descoberta e sumia da acusação, em silêncio, no único ramo
    do arquivo que errava para o lado permissivo."""
    with pytest.raises((OSError, TypeError)):
        inspect.getsource(_MutanteSemFonteView.post)

    alvos = {"apps.ficticio.views.SemFonte": AlvoAlcancavel(_MutanteSemFonteView, None, ())}
    superficies, _ = superficies_de_escrita(alvos)
    faltando = superficies_de_escrita_sem_politica(alvos)

    # Descoberta: ela existe para a varredura...
    assert set(superficies) == {"apps.ficticio.views.SemFonte.post"}
    # ...e agora também para a ACUSAÇÃO, que é a metade que faltava.
    assert set(faltando) == {"apps.ficticio.views.SemFonte.post"}
    assert "não conseguiu ler o fonte" in faltando["apps.ficticio.views.SemFonte.post"]


def test_a_varredura_aprova_a_mesma_superficie_quando_o_fonte_existe_e_tem_politica():
    """Par positivo: "não consegui ler" não pode ter virado "reprovo todo
    mundo"."""
    alvos = {"apps.ficticio.views.ComFonte": AlvoAlcancavel(_MutanteComFonteView, None, ())}
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {"apps.ficticio.views.ComFonte.post"}
    assert inspect.getsource(_MutanteComFonteView.post)
    assert superficies_de_escrita_sem_politica(alvos) == {}


# --- BL-232/C3: o nome efetivo carrega o método HTTP ------------------------


class _MutanteDoisMetodosViewSet(viewsets.ViewSet):
    """`@action` ligada a DOIS métodos de escrita — o caso em que o par (alvo,
    ação) deixa de identificar a superfície.

    A varredura já produzia duas CHAVES aqui; o que colapsava era o
    `nome_efetivo`, que é o nome pelo qual o elo de execução (BL-218) reconhece
    a superfície. Duas chaves e um nome efetivo faziam exercitar o POST marcar
    o PUT como exercitado.
    """

    @action(detail=False, methods=["post", "put"])
    def importar(self, request):  # pragma: no cover - objeto de medição
        from apps.core.requisicao import recusar_dado_nao_contratado

        recusar_dado_nao_contratado(request, _CONTRATO_FICTICIO)
        return _gravar_conta_ficticia(1, request.data["codigo"], request.data["nome"])


def test_um_handler_ligado_a_dois_metodos_tem_dois_nomes_efetivos():
    """BL-232/C3, a metade da varredura. Medido pelo auditor antes da
    correção: `chaves distintas = 2, nomes_efetivos distintos = 1`."""
    rotas = _rotas_de_um_roteador_real(_MutanteDoisMetodosViewSet, "dois-metodos")

    # O fato que produz o caso: uma rota só, ligando os dois métodos à MESMA
    # ação — não é invenção do teste, é o que o `@action` gera.
    assert {"post": "importar", "put": "importar"} in [rota.acoes for rota in rotas if rota.acoes]

    superficies, _ = superficies_de_escrita(_alvos_de(rotas))
    prefixo = f"{_PREFIXO_DOS_MUTANTES}._MutanteDoisMetodosViewSet.importar"

    assert set(superficies) == {f"{prefixo}.post", f"{prefixo}.put"}
    assert {superficie.nome_efetivo for superficie in superficies.values()} == {
        f"{prefixo}.post",
        f"{prefixo}.put",
    }


def test_uma_view_de_funcao_com_dois_metodos_tem_dois_nomes_efetivos():
    """A outra forma que o auditor mediu com o mesmo resultado: view de função
    com `@require_http_methods(["POST", "PUT"])`."""
    alvos = {
        "apps.ficticio.views.importar": AlvoAlcancavel(_mutante_importar_por_post_e_put, None, ())
    }
    superficies, _ = superficies_de_escrita(alvos)

    assert set(superficies) == {
        "apps.ficticio.views.importar.post",
        "apps.ficticio.views.importar.put",
    }
    assert {superficie.nome_efetivo for superficie in superficies.values()} == set(superficies)


def test_o_nome_efetivo_de_toda_superficie_e_a_propria_chave():
    """O invariante, no urlconf REAL: a chave que a varredura julga e o nome
    que o elo de execução exige são o mesmo texto.

    Enquanto os dois divergiam, a diferença era silenciosa — a conferência da
    BL-218 continuava verde marcando uma superfície por outra. Aqui a
    coincidência é verificada nas três formas de uma vez (view de função,
    classe comum e ação de `ViewSet`, se houver)."""
    superficies, _ = superficies_de_escrita(_alvos_alcancaveis())

    divergentes = {
        chave: superficie.nome_efetivo
        for chave, superficie in superficies.items()
        if superficie.nome_efetivo != chave
    }

    assert not divergentes, divergentes
    assert len(superficies) >= len(SUPERFICIES_DE_ESCRITA_CONHECIDAS)
