"""Achado A10 da auditoria DL-017, rodada 4 (BL-134).

A BL-121 (achado R3-10, rodada 3) corrigiu `MeusEscritoriosView` e
`EscritorioAtivoView` (as duas únicas `APIView` sem `permission_classes`
próprio) e escreveu um teste estrutural — mas ele resolve **duas classes
pelo nome** (`apps/tenancy/tests/test_views.py`). O auditor apontou: hoje
as 14 `APIView`/`generics.*APIView` do repositório declaram permissão
(conferido uma a uma por ele), mas a **décima quinta não seria detectada**
— nenhuma rota nova fica protegida "por acaso".

Este módulo varre TODA `APIView` definida em `apps/**/views.py` (não uma
lista fixa de nomes) e exige que `permission_classes` esteja declarado em
algum ponto da cadeia de herança PRÓPRIA do projeto — a própria classe ou
um mixin do projeto (`EmpresaQuerySetMixin`, por exemplo) — nunca só
herdado, por omissão, do padrão global via `rest_framework.views.APIView`.

Mantém o par estrutural (este módulo) + comportamental (os testes HTTP já
existentes por view, que continuam por view, porque cada uma tem sua
própria regra de negócio) que a BL-121 já estabeleceu para as duas
primeiras — a diferença é que a varredura ESTRUTURAL agora cobre a CLASSE
("nenhuma APIView fica autorizada por omissão"), não só o caso nomeado.
"""

import importlib
import inspect
import pkgutil

import pytest
from rest_framework.views import APIView


def _modulos_de_views_do_repositorio():
    """Importa todo módulo `views.py` de cada app declarado em `apps/`.

    Não depende do urlconf real já ter importado o módulo (a robustez
    desta varredura não pode depender de acaso de import, ou uma `APIView`
    em um módulo nunca referenciado por nenhuma rota escaparia da
    checagem). `views_web.py` também é tentado, por simetria — hoje
    nenhum app o usa para `APIView` (são views Django comuns), mas se um
    dia usar, entra na varredura sem precisar editar este arquivo.
    """
    import apps as pacote_apps

    modulos = []
    for _finder, nome_app, is_pkg in pkgutil.iter_modules(pacote_apps.__path__, "apps."):
        if not is_pkg:
            continue
        for sufixo in ("views", "views_web"):
            caminho = f"{nome_app}.{sufixo}"
            try:
                modulos.append(importlib.import_module(caminho))
            except ModuleNotFoundError:
                continue
    return modulos


def _apiviews_definidas_no_repositorio():
    """Toda classe DEFINIDA (não só importada) num módulo de views do
    projeto que seja subclasse de `APIView` — inclusive via
    `generics.*APIView`, que também herda de `APIView`.

    `objeto.__module__ == modulo.__name__` é o que distingue "definida
    aqui" de "importada aqui": sem essa checagem, `APIView` e
    `generics.ListCreateAPIView` em si (importados por quase todo módulo
    de views) apareceriam na varredura como se fossem views do projeto.
    """
    encontradas = []
    for modulo in _modulos_de_views_do_repositorio():
        for _nome, objeto in inspect.getmembers(modulo, inspect.isclass):
            if (
                issubclass(objeto, APIView)
                and objeto is not APIView
                and objeto.__module__ == modulo.__name__
            ):
                encontradas.append(objeto)
    return encontradas


def _classe_que_declara_permission_classes(view_classe):
    """Primeira classe na ordem de resolução de método (MRO) que tem
    `permission_classes` no PRÓPRIO `__dict__` — é assim que o Python
    resolve `view_classe.permission_classes` de verdade, e é exatamente
    por isso que não se pode usar `"permission_classes" in view_classe.
    __dict__` sozinho: uma view que herda a permissão de um MIXIN do
    projeto (`EmpresaQuerySetMixin`, por exemplo, não do `APIView` do DRF)
    está correta, mas não tem a chave no PRÓPRIO `__dict__`.
    """
    for classe in view_classe.__mro__:
        if "permission_classes" in classe.__dict__:
            return classe
    return None  # nunca deveria acontecer: APIView sempre declara.


def test_apiviews_definidas_no_repositorio_sao_encontradas():
    """Controle de que a varredura funciona — se cair para perto de zero,
    suspeite de `_modulos_de_views_do_repositorio`/`_apiviews_definidas_
    no_repositorio` antes de confiar no teste principal (mesmo espírito de
    `test_todos_os_py_do_repositorio_compilam_na_versao_minima_declarada`,
    em `test_versao_minima_python.py`)."""
    apiviews = _apiviews_definidas_no_repositorio()
    nomes = sorted(f"{c.__module__}.{c.__qualname__}" for c in apiviews)
    assert len(apiviews) >= 10, (nomes, len(apiviews))


def test_nenhuma_apiview_do_repositorio_depende_do_padrao_global_por_omissao():
    """A10: nenhuma rota fica autorizada por omissão. Para CADA `APIView`
    definida em `apps/**/views.py`, `permission_classes` precisa vir de
    algum ponto da cadeia de herança do PROJETO (a própria classe, ou um
    mixin escrito aqui) — nunca só do padrão global do `rest_framework.
    views.APIView`, que é o que aconteceria se uma view nova esquecesse de
    declarar a permissão.
    """
    falhas = []
    for view_classe in _apiviews_definidas_no_repositorio():
        origem = _classe_que_declara_permission_classes(view_classe)
        if origem is APIView:
            falhas.append(f"{view_classe.__module__}.{view_classe.__qualname__}")

    assert not falhas, (
        "As seguintes APIView não têm permission_classes declarado em nenhuma "
        "classe do projeto na cadeia de herança (dependem só do padrão global "
        "de rest_framework.views.APIView):\n" + "\n".join(sorted(falhas))
    )


@pytest.mark.parametrize(
    "modulo_e_classe",
    [
        "apps.contabilidade.views.ContaListCreateView",
        "apps.contabilidade.views.LancamentoListCreateView",
        "apps.contabilidade.views.EstornarLancamentoView",
        "apps.contabilidade.views.DiarioView",
        "apps.contabilidade.views.RazaoView",
        "apps.contabilidade.views.BalanceteView",
        "apps.contabilidade.views.ConferenciaLotesDesbalanceadosView",
        "apps.empresas.views.EmpresaListCreateView",
        "apps.empresas.views.EmpresaDetailView",
        "apps.empresas.views.EstabelecimentoListCreateView",
        "apps.empresas.views.HistoricoRegimeTributarioListCreateView",
        "apps.tenancy.views.MeusEscritoriosView",
        "apps.tenancy.views.EscritorioAtivoView",
        "apps.auditoria.views.RegistroAuditoriaListView",
    ],
)
def test_varredura_inclui_as_14_apiviews_conferidas_pelo_auditor(modulo_e_classe):
    """Controle nominal: as 14 `APIView` que o auditor conferiu uma a uma
    (rodada 4) precisam aparecer na varredura — se uma sumir (renomeada,
    movida, removida), este teste falha apontando qual, em vez de o total
    de `test_apiviews_definidas_no_repositorio_sao_encontradas` só cair em
    silêncio."""
    caminho_modulo, nome_classe = modulo_e_classe.rsplit(".", 1)
    modulo = importlib.import_module(caminho_modulo)
    classe = getattr(modulo, nome_classe)
    assert classe in _apiviews_definidas_no_repositorio()
