"""Varredura de repositório das superfícies de escrita e dos seus contratos
(BL-149, lacuna (a) do inventário de 2026-09-15).

## Por que ela existe

A política dos cinco dicionários (`apps.core.requisicao`) está aplicada e tem
testes de comportamento em cada superfície. O que faltava era a varredura no
molde da BL-134 — a que **impede a próxima superfície de nascer sem
contrato**. O histórico é literal sobre a necessidade:

- BL-121 corrigiu as duas `APIView` sem `permission_classes` e escreveu um
  teste por NOME; a BL-134 apontou que "a décima quinta não seria detectada" e
  virou varredura.
- BL-145 fechou a política em **1 de 7** superfícies. O critério estava
  escrito, a conferência foi feita, e seis ficaram de fora.
- BL-157/BL-167: o registro de restrições afirmava uma varredura que não
  existia, e **duas** constraints passaram pela conferência manual.

Três vezes a mesma lição: *conferência manual não reprova build*.

## O que esta varredura exige

**1. Toda superfície de escrita aplica a política.** Para cada `APIView` do
projeto alcançável pelo urlconf, cada método de escrita (`post`, `put`,
`patch`, `delete`) chama `recusar_dado_nao_contratado` — direta ou por uma
ponte do próprio app (uma indireção é resolvida, e a detecção é por AST, nunca
por substring: `inspect.getsource` de uma função chamada
`_recusar_dado_nao_contratado` contém o nome dela na própria linha do `def`, e
um teste por substring seria permanentemente verdadeiro, que é o defeito da
BL-150). Para as views de FUNÇÃO (telas), a mesma exigência vale para as que
tratam POST.

**2. Nenhum `ContratoDeRequisicao` de código de produção fica sem `campos`
explícito.** `campos=None` — o padrão — significa "este contrato não julga o
corpo": um contrato construído sem `campos` recusaria arquivo, querystring e
cabeçalho, e deixaria **passar qualquer chave no corpo**, em silêncio e com
aparência de sucesso. É o formato exato do defeito desta etapa, e o padrão da
classe é permissivo porque existe um uso legítimo (corpo julgado item a item,
noutro ponto). Quem precisar dele declara na lista de exceções, com razão
escrita.

**3. Lista de exceções NOMEADA, nunca padrão permissivo.** Os dois registros
abaixo estão vazios hoje, e vazios são a defesa mais forte. Entrada nova exige
razão escrita, e uma entrada que deixe de corresponder a algo real reprova
(não fica encobrindo nada).

## O que ela NÃO cobre, declarado

**Views de função que não tratam POST.** A classificação "trata POST" é
textual (`request.method`/`request.POST` no fonte). Uma tela de LEITURA que
receba um POST hoje renderiza a página ignorando o corpo — nada é gravado, e
nenhuma gravação aparenta sucesso, que é o efeito proibido da BL-149. Se
alguma passar a gravar, ela menciona `request.POST` e entra na varredura pelo
mesmo critério.

**Se a superfície tem TESTE dos cinco dicionários.** Esta varredura prova que
a política é CHAMADA, não que alguém a exercitou por requisição. Amarrar
superfície a arquivo de teste por casamento de nome seria uma promessa que o
próprio mecanismo não sustenta — o erro que a BL-166 nomeou. Os testes de
comportamento continuam por superfície, e a cobertura deles é item de
backlog, não afirmação deste arquivo.
"""

import ast
import inspect
import pathlib
import textwrap

import pytest
from django.urls import get_resolver
from rest_framework.views import APIView

# Molde reaproveitado, de propósito: a varredura da BL-134 já resolve "quais
# módulos de views existem" e "quais APIView são definidas aqui, não
# importadas". Reimplementar isso seria a segunda cópia da mesma regra
# (DE-026) — e, se aquele auxiliar for renomeado, este arquivo falha no
# import, em vez de passar a varrer um conjunto vazio em silêncio.
from apps.core.tests.test_permission_classes_explicito import (
    _apiviews_definidas_no_repositorio,
    _modulos_de_views_do_repositorio,
)

METODOS_DE_ESCRITA = ("post", "put", "patch", "delete")

NOME_DA_POLITICA = "recusar_dado_nao_contratado"

# Raiz do repositório: este arquivo é `<raiz>/apps/core/tests/…`, logo três
# níveis acima. Conferida por `test_a_raiz_do_repositorio_esta_correta` — um
# `parents[2]` (o erro que este arquivo cometeu ao nascer) faria
# `_arquivos_de_producao_dos_apps` devolver LISTA VAZIA, e a varredura de
# contratos passaria sem ler uma linha. Foi o controle positivo que pegou.
RAIZ = pathlib.Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Exceções NOMEADAS. Vazias hoje — e vazias é o estado desejado.
#
# Formato: {"caminho.pontilhado.da.superficie": "razão escrita"}. Uma entrada
# aqui não é dispensa: é declaração verificável de que alguém decidiu, e de
# por quê. `test_nenhuma_excecao_registrada_ficou_obsoleta` reprova se a
# superfície citada deixar de existir — uma exceção órfã encobriria a
# superfície seguinte que herdasse o mesmo nome.
#
# A última entrada que existiria aqui era `apps.empresas.views.criar_empresa`,
# a tela de cadastro de empresa: única superfície de escrita do repositório
# sem a política, encontrada por ESTA varredura na segunda rodada da DL-019 e
# corrigida no mesmo passo (ver `_contrato_da_tela_de_empresa`), em vez de
# registrada como exceção.
SUPERFICIES_DE_ESCRITA_SEM_POLITICA = {}

# Formato: {"arquivo:linha": "razão escrita"} para um `ContratoDeRequisicao`
# construído sem `campos` explícito. Ver o item 2 do docstring: existe uso
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
# Descoberta das superfícies
# ---------------------------------------------------------------------------


def _alvos_do_urlconf():
    """Todo callable de rota do urlconf REAL, como (classe_ou_funcao).

    Partir do urlconf, e não de uma varredura de arquivos, responde à
    pergunta certa: o que está ALCANÇÁVEL por requisição. `view_class` é o
    atributo que o Django pendura em `View.as_view()`; `cls`, o que o DRF
    pendura em `APIView.as_view()`.
    """
    alvos = {}

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
            modulo = getattr(alvo, "__module__", "") or ""
            if not modulo.startswith("apps."):
                continue
            alvos[f"{modulo}.{alvo.__qualname__}"] = alvo

    percorrer(get_resolver().url_patterns)
    return alvos


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


def superficies_de_escrita_sem_politica():
    """`{"caminho.da.superficie": "motivo"}` para cada superfície de escrita
    que NÃO chega à política."""
    faltando = {}

    classes = set(_apiviews_definidas_no_repositorio())
    for alvo in _alvos_do_urlconf().values():
        if isinstance(alvo, type) and issubclass(alvo, APIView):
            classes.add(alvo)

    for classe in sorted(classes, key=lambda c: f"{c.__module__}.{c.__qualname__}"):
        for metodo in METODOS_DE_ESCRITA:
            handler = getattr(classe, metodo, None)
            if handler is None:
                continue
            try:
                fonte = inspect.getsource(handler)
            except (OSError, TypeError):  # pragma: no cover
                continue
            if aplica_a_politica(fonte, _resolvedor_de_indirecao(classe)):
                continue
            onde = getattr(handler, "__qualname__", metodo)
            faltando[f"{classe.__module__}.{classe.__qualname__}.{metodo}"] = (
                f"o handler que responde {metodo.upper()} é {onde} e não chama {NOME_DA_POLITICA}"
            )

    for modulo in _modulos_de_views_do_repositorio():
        for nome, funcao in vars(modulo).items():
            if not inspect.isfunction(funcao) or funcao.__module__ != modulo.__name__:
                continue
            if nome.startswith("_"):
                continue
            fonte = inspect.getsource(funcao)
            trata_post = "request.method" in fonte or "request.POST" in fonte
            if not trata_post:
                continue
            if aplica_a_politica(fonte, _resolvedor_de_indirecao(modulo)):
                continue
            faltando[f"{modulo.__name__}.{nome}"] = (
                f"view de função que trata POST e não chama {NOME_DA_POLITICA}"
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


def test_a_varredura_encontra_as_superficies_de_escrita_de_hoje():
    """Controle: se a descoberta quebrar, o teste principal passaria a varrer
    um conjunto vazio e "nenhuma falta" viraria vácuo."""
    encontradas = []
    for alvo in _alvos_do_urlconf().values():
        if isinstance(alvo, type) and issubclass(alvo, APIView):
            encontradas.extend(m for m in METODOS_DE_ESCRITA if getattr(alvo, m, None))
        elif inspect.isfunction(alvo):
            fonte = inspect.getsource(alvo)
            if "request.method" in fonte or "request.POST" in fonte:
                encontradas.append(alvo.__qualname__)

    assert len(encontradas) >= 12, encontradas


@pytest.mark.parametrize(
    "superficie",
    [
        "apps.contabilidade.views.ContaListCreateView.post",
        "apps.contabilidade.views.LancamentoListCreateView.post",
        "apps.contabilidade.views.EstornarLancamentoView.post",
        "apps.empresas.views.EmpresaListCreateView.post",
        "apps.empresas.views.EmpresaDetailView.put",
        "apps.empresas.views.EmpresaDetailView.patch",
        "apps.empresas.views.EstabelecimentoListCreateView.post",
        "apps.empresas.views.HistoricoRegimeTributarioListCreateView.post",
        "apps.empresas.views.HistoricoRegimeTributarioDetailView.delete",
        "apps.empresas.views.criar_empresa",
        "apps.tenancy.views.EscritorioAtivoView.post",
        "apps.tenancy.views.ativar_escritorio",
        "apps.contabilidade.views_web.conta_nova",
        "apps.contabilidade.views_web.lancamento_novo",
    ],
)
def test_cada_superficie_de_escrita_conhecida_continua_visivel_a_varredura(superficie):
    """Controle NOMINAL, no molde de `test_varredura_inclui_as_14_apiviews_
    conferidas_pelo_auditor`: as superfícies de escrita conhecidas em
    2026-09-15. Se uma for renomeada ou movida, este teste falha apontando
    QUAL — em vez de ela sair da varredura em silêncio, que é a forma mais
    fácil de uma varredura passar a não medir nada.
    """
    caminho, nome = superficie.rsplit(".", 1)
    if nome in METODOS_DE_ESCRITA:
        caminho_classe, metodo = caminho, nome
    else:
        caminho_classe, metodo = superficie, None

    modulo_nome, atributo = caminho_classe.rsplit(".", 1)
    modulo = __import__(modulo_nome, fromlist=[atributo])
    alvo = getattr(modulo, atributo, None)
    assert alvo is not None, f"{caminho_classe} não existe mais"
    if metodo is not None:
        assert getattr(alvo, metodo, None) is not None, f"{superficie} não existe mais"


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


def test_nenhuma_excecao_registrada_ficou_obsoleta():
    """Exceção órfã é pior que exceção: ela continua dispensando um nome que
    ninguém mais reconhece, e cobriria a próxima superfície que o herdasse."""
    faltando = superficies_de_escrita_sem_politica()
    orfas = sorted(set(SUPERFICIES_DE_ESCRITA_SEM_POLITICA) - set(faltando))

    assert not orfas, (
        "Estas exceções não correspondem mais a nenhuma superfície de escrita "
        f"sem política — remova-as: {orfas}"
    )


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
    """Controle positivo da parte 2: se o reconhecimento do `Call` quebrar
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
# As duas demonstrações, reconstruídas dentro do próprio teste (molde BL-150)
# ---------------------------------------------------------------------------


def test_a_varredura_reprova_superficie_de_escrita_sem_a_politica():
    """O mutante "nasceu uma superfície de escrita nova, sem contrato",
    construído aqui em fonte sintético — a demonstração não depende de ninguém
    ter registrado que viu a suíte falhar (BL-169)."""
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
