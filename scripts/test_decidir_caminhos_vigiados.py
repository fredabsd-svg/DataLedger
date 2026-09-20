"""Testes de `scripts/decidir_caminhos_vigiados.py` — BL-379 (achado J9
da nona auditoria, docs/auditorias/2026-09-19-dl-026-dl-028-rodada-9.md).

**Por que os 11 cenários usam um repositório Git DESCARTÁVEL de verdade,
em vez de mockar `subprocess.run`.** A lógica que importa aqui é a
INTERAÇÃO com `git diff` (intervalos degenerados, SHA inexistente,
`before` só de zeros) — um mock provaria só que o mock foi chamado com
os argumentos certos, não que o COMPORTAMENTO do `git` real bate com a
suposição (AGENTS.md §7: "mocks são adequados para testes isolados, mas
não comprovam a integração real"). O auditor da nona auditoria fez o
mesmo: "extraí o passo `decidir` do YAML... e o rodei, SEM
reimplementar a lógica, contra um repositório Git descartável com
commits reais" — os 11 cenários abaixo são os do §4 do relatório dele,
mais os testes unitários das funções puras (`sha_valida`,
`padrao_para_regex`, `bate`).

Cada teste usa `tmp_path` (descartado pelo próprio `pytest` ao fim) —
NUNCA a árvore deste projeto (BL-311)."""

import fnmatch
import pkgutil
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decidir_caminhos_vigiados as decisor  # noqa: E402
import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# Infraestrutura de teste: um repositório Git minúsculo e determinístico.
# ---------------------------------------------------------------------------


def _git(repo, *args):
    resultado = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "Teste",
            "GIT_AUTHOR_EMAIL": "teste@example.com",
            "GIT_COMMITTER_NAME": "Teste",
            "GIT_COMMITTER_EMAIL": "teste@example.com",
            "HOME": str(repo),
        },
    )
    assert resultado.returncode == 0, (
        f"git {' '.join(args)} falhou: {resultado.stderr}\n{resultado.stdout}"
    )
    return resultado.stdout.strip()


def _commit(repo, arquivos, mensagem):
    """Cria/edita cada `arquivo: conteúdo` de `arquivos` e commita.
    Devolve o SHA do commit criado."""
    for caminho_relativo, conteudo in arquivos.items():
        caminho = repo / caminho_relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", mensagem, "--allow-empty")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    caminho = tmp_path / "repo_descartavel"
    caminho.mkdir()
    _git(caminho, "init", "-q", "-b", "main")
    _commit(caminho, {"README.md": "inicial\n"}, "commit inicial")
    return caminho


# ---------------------------------------------------------------------------
# Os 11 cenários do §4/§8 do relatório da nona auditoria.
# ---------------------------------------------------------------------------


def test_a_push_so_de_documentacao_nao_e_relevante(repo):
    antes = _git(repo, "rev-parse", "HEAD")
    depois = _commit(repo, {"docs/x.md": "novo texto\n"}, "docs: x")
    relevante, motivo = decisor.decidir("push", "", "", antes, depois, cwd=repo)
    assert relevante is False
    assert "docs" in motivo or "irrelevantes" in motivo


def test_b_push_tocando_css_e_relevante(repo):
    antes = _git(repo, "rev-parse", "HEAD")
    depois = _commit(repo, {"static/css/base.css": "body{}\n"}, "css")
    relevante, motivo = decisor.decidir("push", "", "", antes, depois, cwd=repo)
    assert relevante is True
    assert "static/css/base.css" in motivo


def test_c_push_criando_tela_imprimivel_em_app_novo_e_relevante(repo):
    # BL-376 (achado J5): o caso que a lista ANTIGA (`CAMINHOS_VIGIADOS`)
    # deixava passar em silêncio — `apps/<app>/templates/` é o lugar
    # IDIOMÁTICO (APP_DIRS: True) onde um módulo novo (Fiscal, Folha...)
    # vai pôr sua tela imprimível. Com a lista INVERTIDA, isto só seria
    # "irrelevante" se batesse em `docs/**`/`*.md`/`.github/
    # ISSUE_TEMPLATE/**` — não bate, então é relevante por padrão.
    antes = _git(repo, "rev-parse", "HEAD")
    depois = _commit(
        repo,
        {"apps/fiscal/templates/fiscal/apuracao.html": "<div class='timbre-impressao'></div>\n"},
        "feat(fiscal): tela de apuração com timbre",
    )
    relevante, motivo = decisor.decidir("push", "", "", antes, depois, cwd=repo)
    assert relevante is True
    assert "apps/fiscal/templates/fiscal/apuracao.html" in motivo


def test_d_primeiro_push_de_branch_nova_e_relevante_lado_seguro(repo):
    depois = _git(repo, "rev-parse", "HEAD")
    relevante, motivo = decisor.decidir("push", "", "", "0" * 40, depois, cwd=repo)
    assert relevante is True
    assert "branch nova" in motivo


def test_e_before_vazio_e_relevante_lado_seguro(repo):
    depois = _git(repo, "rev-parse", "HEAD")
    relevante, motivo = decisor.decidir("push", "", "", "", depois, cwd=repo)
    assert relevante is True


def test_f_before_inexistente_apos_gc_e_relevante_por_aviso(repo):
    # Força-push com o commit anterior já coletado pelo `git gc`: `git
    # diff` não consegue resolver a revisão. Simulado com um SHA de
    # FORMATO válido (40 hex) mas que não existe como objeto no repo —
    # `git diff` sai com código != 0 ("unknown revision").
    depois = _git(repo, "rev-parse", "HEAD")
    sha_inexistente = "a" * 40
    relevante, motivo = decisor.decidir("push", "", "", sha_inexistente, depois, cwd=repo)
    assert relevante is True
    assert "AVISO" not in motivo or "git diff" in motivo  # o motivo nomeia o comando que falhou
    assert "falhou" in motivo


def test_g_pull_request_so_de_documentacao_nao_e_relevante(repo):
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"docs/y.md": "texto\n"}, "docs: y")
    relevante, motivo = decisor.decidir("pull_request", base, head, "", "", cwd=repo)
    assert relevante is False


def test_h_pull_request_com_css_e_tela_nova_e_relevante(repo):
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(
        repo,
        {
            "static/css/base.css": "body{}\n",
            "templates/fiscal/apuracao.html": "<div></div>\n",
        },
        "feat: css + tela",
    )
    relevante, motivo = decisor.decidir("pull_request", base, head, "", "", cwd=repo)
    assert relevante is True
    assert "static/css/base.css" in motivo
    assert "templates/fiscal/apuracao.html" in motivo


def test_i_pull_request_com_base_igual_a_head_nao_e_relevante(repo):
    sha = _git(repo, "rev-parse", "HEAD")
    relevante, motivo = decisor.decidir("pull_request", sha, sha, "", "", cwd=repo)
    assert relevante is False


def test_j_workflow_dispatch_e_relevante_lado_seguro(repo):
    relevante, motivo = decisor.decidir("workflow_dispatch", "", "", "", "", cwd=repo)
    assert relevante is True
    assert "lado seguro" in motivo


def test_k_pull_request_com_sha_vazios_e_relevante_nunca_false(repo):
    # BL-379/J9: o cenário que a lógica ANTIGA (embutida no YAML) errava
    # — `base.sha`/`head.sha` vazios montavam o intervalo degenerado
    # `"..."`, `git diff --name-only ...` saía com código 0 e string
    # vazia, e o resultado era `relevante=False` com um motivo
    # TRANQUILIZADOR ("nenhum dos 0 arquivo(s) alterado(s) bate..."). A
    # validação de formato em `determinar_intervalo` fecha isto ANTES de
    # chegar ao `git diff`.
    relevante, motivo = decisor.decidir("pull_request", "", "", "", "", cwd=repo)
    assert relevante is True
    assert "RELEVANTE" in motivo or "relevante" in motivo.lower()
    assert "SHA" in motivo


# ---------------------------------------------------------------------------
# Funções puras — sem git, sem repositório.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sha", "esperado"),
    [
        ("a" * 40, True),
        ("A" * 40, True),
        ("0123456789abcdef" * 2 + "01234567", True),  # 40 hex válidos
        ("", False),
        (None, False),
        ("a" * 39, False),  # curto demais
        ("a" * 41, False),  # longo demais
        ("g" * 40, False),  # 'g' não é hexadecimal
        ("0" * 40, True),  # zeros são um SHA de FORMATO válido (o caso 'before' é tratado à parte)
    ],
)
def test_sha_valida(sha, esperado):
    assert decisor.sha_valida(sha) is esperado


@pytest.mark.parametrize(
    ("padrao", "arquivo", "esperado"),
    [
        ("static/css/**", "static/css/base.css", True),
        ("static/css/**", "static/js/app.js", False),
        ("*.md", "README.md", True),
        ("*.md", "docs/x.md", False),  # "*" não cruza "/"
        ("**/*.md", "docs/x.md", True),
        ("**/*.md", "README.md", False),  # exige ao menos um "/" antes do nome
        (".github/ISSUE_TEMPLATE/**", ".github/ISSUE_TEMPLATE/bug.md", True),
        ("apps/**/templates/**", "apps/fiscal/templates/x.html", True),
    ],
)
def test_padrao_para_regex_e_bate(padrao, arquivo, esperado):
    compilado = decisor.padrao_para_regex(padrao)
    assert bool(compilado.match(arquivo)) is esperado
    assert decisor.bate([compilado], arquivo) is esperado


def test_caminhos_nao_relevantes_e_a_lista_pequena_do_lado_seguro():
    """BL-376: a lista precisa continuar PEQUENA e nomeada — se alguém
    acrescentar um padrão amplo aqui sem querer, este teste não impede
    (não é uma trava de tamanho), mas documenta a expectativa: cada
    entrada é uma exceção CONSCIENTE, não uma lista que cresce por
    comodidade.

    **BL-409/K6 (décima auditoria) — por que este RETRATO continua ao
    lado do teste de PROPRIEDADE abaixo, em vez de ser substituído por
    ele.** Este teste só prova que a lista não mudou sem alguém revisar o
    diff: ele obriga a EDITAR este arquivo (e o motivo aparece no PR) toda
    vez que alguém acrescentar ou remover uma entrada de
    `CAMINHOS_NAO_RELEVANTES` — inclusive uma entrada que, hoje, não
    bateria em nenhum arquivo versionado (o teste de propriedade não
    reprovaria essa mudança, porque ela ainda não teria vítima). O teste
    de propriedade prova a coisa OPOSTA e complementar: que a lista, seja
    qual for o seu conteúdo no momento, não esconde um arquivo de
    código/config que já existe no repositório. Um não substitui o outro:
    este é o "a lista não mudou por acidente"; o de baixo é "a lista está
    certa contra o estado real do repositório"."""
    assert decisor.CAMINHOS_NAO_RELEVANTES == [
        "docs/**",
        "*.md",
        "**/*.md",
        ".github/ISSUE_TEMPLATE/**",
    ]


# ---------------------------------------------------------------------------
# BL-416/BL-417 — a UNIÃO das duas fontes de exclusão, cada uma com o
# matcher que ela realmente usa.
# ---------------------------------------------------------------------------


def _arquivos_versionados(raiz):
    resultado = subprocess.run(
        ["git", "ls-files"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    return [linha for linha in resultado.stdout.splitlines() if linha]


def _escondidos_pelo_job_de_ci(arquivos_versionados):
    """`CAMINHOS_NAO_RELEVANTES` é lida pelo passo do GitHub Actions
    (`scripts/decidir_caminhos_vigiados.py`), com a semântica do `paths:`
    documentada pelo GitHub — `*` NÃO cruza `/`, `**` cruza. É exatamente
    o que `decidir_caminhos_vigiados.padrao_para_regex`/`bate` implementam,
    e é o matcher CERTO para esta lista especificamente (ver BL-417,
    abaixo, sobre por que NÃO é o matcher certo para a outra)."""
    padroes = [decisor.padrao_para_regex(p) for p in decisor.CAMINHOS_NAO_RELEVANTES]
    return {a for a in arquivos_versionados if decisor.bate(padroes, a)}


def _escondidos_pelo_ruff(raiz, arquivos_versionados):
    """`tool.ruff.extend-exclude`, lida do `pyproject.toml` EM TEMPO DE
    TESTE (`tomllib`, biblioteca padrão desde o 3.11 — nenhuma dependência
    nova) — nunca copiada para uma constante aqui, para um padrão novo
    acrescentado lá aparecer aqui automaticamente, sem editar dois lugares.

    **BL-417 (achado desta correção, registrado pelo arquiteto-senior) —
    LIMITE DECLARADO sobre qual matcher usar.** `decidir_caminhos_
    vigiados.padrao_para_regex` implementa a semântica do `paths:` do
    GitHub Actions, em que `*` NÃO cruza `/`. O glob do `ruff` CRUZA.
    MEDIDO, não presumido — os dois comandos que provam a diferença:

    ```
    >>> import decidir_caminhos_vigiados as d
    >>> p = d.padrao_para_regex("*/migrations/*")
    >>> bool(p.match("apps/contabilidade/migrations/0001_initial.py"))
    False
    ```
    ```
    $ ruff check --show-files . | grep -c migrations/
    0
    ```
    O `ruff` real EXCLUI o arquivo (`--show-files` não o lista); o
    conversor de `paths:` do GitHub diz que o padrão NÃO bate nele. Usar
    `padrao_para_regex`/`bate` aqui faria este teste MENTIR para o lado de
    DEIXAR PASSAR — o pior dos dois lados (um arquivo realmente escondido
    do `ruff` apareceria como "não escondido", e não seria checado nem
    contra a lista segura nem contra o reconhecimento do Django). Por
    isso esta função usa `fnmatch.fnmatch` (biblioteca padrão), que
    trata `*` como "qualquer coisa, inclusive `/`" — mais perto do glob
    real de exclusão de arquivos que ferramentas como o `ruff` usam.

    **E esta equivalência foi medida NESTA ÁRVORE, NESTA DATA, com ESTE
    comando — não é uma afirmação de que `fnmatch` é equivalente ao
    `ruff` em geral** (foi precisamente uma afirmação sem essa ressalva,
    sobre o LIMIAR_LUMINANCIA_TINTA, que virou o achado K4 da décima
    auditoria — não repetir a classe aqui):

    ```
    $ python3 -c "
    import subprocess, fnmatch, tomllib, os
    raiz = os.getcwd()
    cfg = tomllib.load(open('pyproject.toml', 'rb'))
    patterns = cfg['tool']['ruff']['extend-exclude']
    r = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True)
    arquivos = r.stdout.splitlines()
    py = [a for a in arquivos if a.endswith(('.py', '.pyi', '.ipynb'))]
    previsto = {a for a in py if any(fnmatch.fnmatch(a, p) for p in patterns)}
    r2 = subprocess.run(
        ['ruff', 'check', '--show-files', '.'], capture_output=True, text=True, check=True)
    mostrados_rel = {os.path.relpath(l, raiz) for l in r2.stdout.splitlines() if l}
    real = {a for a in py if a not in mostrados_rel}
    print('diferenca:', previsto ^ real, 'total py:', len(py), 'excluidos:', len(previsto))
    "
    diferenca: set() total py: 217 excluidos: 22
    ```
    Diferença simétrica vazia entre "o que `fnmatch` prevê" e "o que o
    `ruff` de fato mostra" — hoje, nesta árvore, para os padrões que
    existem hoje (`*/migrations/*`, `docs/**`). Se um padrão futuro usar
    uma sintaxe de glob que `fnmatch` não cobre (classes de caractere
    `[...]`, por exemplo — o `ruff` aceita, `fnmatch` também aceita mas
    com semântica ligeiramente diferente de `!` em classe), esta função
    precisa ser remedida, não presumida corrigida."""
    with open(raiz / "pyproject.toml", "rb") as arquivo_toml:
        configuracao = tomllib.load(arquivo_toml)
    padroes = configuracao["tool"]["ruff"]["extend-exclude"]
    return {a for a in arquivos_versionados if any(fnmatch.fnmatch(a, p) for p in padroes)}


def _migracoes_reconhecidas_pelo_django(raiz):
    """Devolve `(reconhecidas, falhas)`: `reconhecidas` é o conjunto de
    caminhos (relativos a `raiz`) que o Django, de verdade, reconhece como
    migração — importa sem erro E tem uma classe `Migration`; `falhas` é
    `{caminho: motivo}` para candidato que existe em disco mas não passou
    no reconhecimento.

    **Por que não é só `MigrationLoader(...).load_disk()` direto** (que
    seria a chamada mais óbvia, e o arquiteto-senior pediu "o grafo que o
    próprio `MigrationLoader` carrega"): MEDIDO — `load_disk()` processa
    TODOS os apps num laço só e PARA no primeiro arquivo sem classe
    `Migration` (`BadMigrationError`), sem terminar de olhar os apps
    seguintes. Tentei isolar o app ruim redirecionando
    `settings.MIGRATION_MODULES` para um módulo inexistente
    (`ignore_no_migrations=True`) e tentando de novo — e MEDI que isso
    joga fora TAMBÉM as migrações boas do MESMO app (Django trata o app
    inteiro como não-migrado), não só o arquivo ruim: numa árvore com
    `apps/contabilidade/migrations/utilitario.py` sabotado, essa tentativa
    fazia sumir as 5 migrações verdadeiras de `contabilidade` junto — falso
    positivo em arquivo correto, o oposto do que se quer de uma guarda.

    A função abaixo usa os MESMOS blocos que `MigrationLoader.load_disk()`
    usa por dentro — `MigrationLoader.migrations_module` (resolução do
    nome do módulo por app, a mesma API pública), `pkgutil.iter_modules`
    (mesmo filtro: ignora pacote e nome começando com `_`/`~` — é por isso
    que `__init__.py` nunca aparece aqui, nem como reconhecido nem como
    falha; ver o comentário no teste sobre o tratamento explícito dele) e
    o MESMO critério de reconhecimento (`hasattr(módulo, "Migration")`)
    — só que isolando a exceção POR ARQUIVO, para um `utilitario.py` malformado
    em `contabilidade` não apagar o veredito das migrações verdadeiras de
    `contabilidade` nem de nenhum outro app. Continua sendo "o Django diz
    o que é migração" — nenhuma lista nossa decide isso — só que aplicado
    arquivo a arquivo em vez de depender do laço que para no primeiro erro."""
    from importlib import import_module

    from django.apps import apps as django_apps
    from django.db.migrations.loader import MigrationLoader

    reconhecidas = set()
    falhas = {}
    for app_config in django_apps.get_app_configs():
        module_name, _ = MigrationLoader.migrations_module(app_config.label)
        if module_name is None:
            continue
        try:
            modulo = import_module(module_name)
        except ModuleNotFoundError:
            continue
        if not hasattr(modulo, "__path__"):
            continue
        nomes = [
            nome
            for _, nome, is_pkg in pkgutil.iter_modules(modulo.__path__)
            if not is_pkg and nome[0] not in "_~"
        ]
        for nome in nomes:
            caminho_absoluto = (Path(app_config.path) / "migrations" / f"{nome}.py").resolve()
            try:
                caminho = str(caminho_absoluto.relative_to(raiz))
            except ValueError:
                continue  # fora do repositório (biblioteca instalada, ex. django.contrib.*)
            try:
                submodulo = import_module(f"{module_name}.{nome}")
                if not hasattr(submodulo, "Migration"):
                    falhas[caminho] = "importa, mas não tem classe Migration"
                    continue
            except Exception as erro:  # noqa: BLE001 — reportado, nunca engolido
                falhas[caminho] = f"{type(erro).__name__}: {erro}"
                continue
            reconhecidas.add(caminho)
    return reconhecidas, falhas


def test_caminhos_nao_relevantes_so_esconde_prosa_e_imagem_conhecida():
    """BL-409/K6 (décima auditoria) → BL-415 (achado do arquiteto: extensão
    é lista aberta, corrigido invertendo para `EXTENSOES_SEGURAS_PARA_
    FICAR_INVISIVEIS`) → **BL-416 (achado do arquiteto na integração do
    BL-415): o teste só olhava UMA das DUAS listas que a própria décima
    auditoria (K5) nomeou** — `CAMINHOS_NAO_RELEVANTES` (o job de CI) e
    `tool.ruff.extend-exclude` (o `ruff`, `pyproject.toml`). MEDIDO pelo
    arquiteto: um `ferramentas/velho.py` com 4 erros reais de `ruff`,
    escondido só pelo `extend-exclude` (nunca por `CAMINHOS_NAO_
    RELEVANTES`), passava com a suíte inteira verde — a MESMA classe do
    K5 original ("as duas listas erram junto porque nenhuma sabe da
    outra"), agora reproduzida na própria guarda que existia para fechar
    o K5.

    **A correção: o universo de "escondido" vira a UNIÃO das duas fontes,
    lida de onde cada uma mora** (`_escondidos_pelo_job_de_ci` e
    `_escondidos_pelo_ruff`, acima — cada função com o MATCHER que a sua
    fonte realmente usa; ver BL-417 na docstring de `_escondidos_pelo_
    ruff` sobre por que os dois matchers são DIFERENTES de propósito, não
    por descuido). Extensão nova em QUALQUER uma das duas listas passa a
    ser visível a este teste.

    **A categoria "migração" (BL-416, decisão do arquiteto-senior) — e por
    que ela NÃO é "é `.py` sob uma pasta `migrations/`".** O motivo de
    migração poder ficar fora do `ruff` não é "convenção da indústria" nem
    "é código gerado" — nenhuma das duas é verificável (e justificativa
    não verificável é o que a DE-058 proíbe). É uma propriedade que se
    mede: **migração excluída do `ruff` continua sendo EXECUTADA** —
    `python manage.py migrate` roda de verdade em banco vazio na CI e em
    toda semeadura de teste. Ao contrário de `sonda_visibilidade.py` sob
    `docs/` (BL-408), que não era executado por NENHUM mecanismo, uma
    migração real É alcançada, só não pelo `ruff`. A categoria correta é
    **"escondido do lint, mas alcançado pela execução"**, não "está numa
    pasta chamada migrations".

    ⚠️ **A amarra que impede a dispensa de virar porta aberta**: a
    dispensa NÃO é "o caminho contém `migrations/`" (isso deixaria
    `apps/qualquer/migrations/utilitario.py` entrar escondido — a MESMA
    classe, uma pasta adiante). A dispensa é **provada contra o Django**:
    um candidato sob uma pasta `migrations/` só é dispensado se
    `_migracoes_reconhecidas_pelo_django` (acima) o reconhecer de
    verdade — importa e tem uma classe `Migration`. `apps/contabilidade/
    migrations/utilitario.py` (sem classe `Migration`) REPROVA, nomeado,
    porque o Django não o reconhece — não porque uma lista nossa saiba
    que aquele nome específico é suspeito.

    `__init__.py` de um pacote de migrações é tratado À PARTE, de forma
    EXPLÍCITA (não por acidente): `pkgutil.iter_modules` — usado tanto por
    `MigrationLoader.load_disk()` quanto por `_migracoes_reconhecidas_
    pelo_django` acima — nunca lista `__init__` como submódulo (é o
    próprio arquivo que DEFINE o pacote, não um item dele) nem nomes que
    comecem com `_`/`~`. Ele nunca aparece nem como "reconhecido" nem como
    "falha" — por isso é dispensado por definição de arquivo (nome exato
    `__init__.py`, dentro de uma pasta `migrations/`), separado, ANTES de
    perguntar ao Django, e o comentário no código diz isso.

    MEDIDO (não deduzido) que o desenho não perde o que já existia:
    `EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS` continua tratando arquivo
    fora de pasta `migrations/` exatamente como antes (o `docs/ferramentas/
    {rodar_medicao.sh,medir.ps1,sonda.js}` do BL-415 continua reprovando —
    critério 2 da rodada). E, contra a árvore real, sem sabotagem nenhuma:
    a união dá **180** arquivos escondidos (158 pelo job de CI + os 22 que
    só o `ruff` esconde, todas as migrações), **zero ofensores** — os 22
    candidatos de `migrations/` batem exatamente com os 16 que o Django
    reconhece mais os 6 `__init__.py` dispensados à parte (16 + 6 = 22).

    **DE-056 (R5), de novo — fontes de invisibilidade que ESTE teste ainda
    NÃO lê, medidas, não deduzidas:**

    1. **`exclude` padrão do `ruff`** (diferente de `extend-exclude`,
       substitui em vez de somar se alguém o declarar). MEDIDO: o projeto
       não declara `exclude` próprio — só o embutido do `ruff`
       (`.git`, `.venv`, `node_modules`, `dist`, etc., 25 entradas,
       `ruff check --show-settings . | grep -A25 "file_resolver.exclude ="`),
       e **zero** arquivos versionados caem nele hoje (`git ls-files` sem
       nenhum componente de caminho batendo a lista). Limite declarado:
       se este projeto um dia declarar `[tool.ruff] exclude = [...]`
       PRÓPRIO (não o embutido), este teste não o vê.
    2. **`per-file-ignores`** (`[tool.ruff.lint.per-file-ignores]`).
       MEDIDO: `grep -n "per-file-ignores" pyproject.toml` não bate —
       não existe hoje. Se existir um dia, ele desliga REGRA por arquivo
       (não o arquivo inteiro), e este teste não olha para essa chave.
    3. **`# noqa` em linha.** MEDIDO: `grep -rn "# noqa" --include="*.py" .`
       (fora `.venv`) dá **15** ocorrências, e as 15 têm código específico
       (`# noqa: E402`, `# noqa: BLE001`, `# noqa: F401`) — nenhuma
       silencia a linha inteira sem nomear a regra. Este teste não
       verifica NENHUMA delas: um `# noqa` sem código, ou um código que
       desligue justo a regra que pegaria um problema real, passa batido.
    4. **`testpaths`/`norecursedirs` do `pytest`.** MEDIDO:
       `[tool.pytest.ini_options]` não declara nenhum dos dois — o pytest
       usa os padrões dele (coleta a partir do rootdir, com o
       `norecursedirs` embutido). Se um dia alguém declarar `testpaths`
       restrito, um `test_*.py` fora dele para de rodar em silêncio, e
       este teste — que É um desses arquivos — não teria como se
       autodenunciar.

    Não fechei nenhuma das quatro nesta rodada — são limite declarado,
    não lista de pendência silenciosa."""
    raiz = Path(__file__).resolve().parents[1]
    arquivos_versionados = _arquivos_versionados(raiz)

    escondidos = _escondidos_pelo_job_de_ci(arquivos_versionados) | _escondidos_pelo_ruff(
        raiz, arquivos_versionados
    )

    # Migração é dispensada por PROVA contra o Django, nunca por o caminho
    # conter "migrations/" (ver a docstring acima — é a amarra do BL-416).
    # `__init__.py` de pacote de migração é tratado à parte, explicitamente:
    # nem `MigrationLoader.load_disk()` nem `_migracoes_reconhecidas_pelo_
    # django` o listam (pkgutil.iter_modules nunca lista nomes começando
    # com "_"), então ele precisa de uma regra própria para não virar
    # "ofensor" por ausência.
    candidatos_de_migracao = {a for a in escondidos if Path(a).parent.name == "migrations"}
    inits_de_pacote_de_migracao = {
        a for a in candidatos_de_migracao if Path(a).name == "__init__.py"
    }
    outros_candidatos_de_migracao = candidatos_de_migracao - inits_de_pacote_de_migracao

    reconhecidas_pelo_django, falhas_do_django = _migracoes_reconhecidas_pelo_django(raiz)
    migracoes_nao_reconhecidas = sorted(outros_candidatos_de_migracao - reconhecidas_pelo_django)

    # LADO SEGURO (BL-415): lista FECHADA do que pode legitimamente ficar
    # fora do alcance de ruff/pytest/CI — prosa e imagem, nada que rode.
    # Qualquer extensão fora daqui, OU AUSÊNCIA de extensão, reprova. Não
    # enumeramos "o que é perigoso" (lista aberta, cresce com a
    # linguagem — .sh, .ps1, .js, .rb, .go, ... — e o BL-415 mediu que
    # essa enumeração furava em menos de uma hora); enumeramos "o que já
    # sabemos que é seguro", e o padrão comparado é o NOME INTEIRO em
    # minúsculas, não uma lista de sufixos soltos, para não confundir
    # `.md` com `.markdown-antigo` por acidente de `str.endswith`.
    EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS = (".md", ".png", ".svg")
    nao_migracoes = escondidos - candidatos_de_migracao
    ofensores_por_extensao = sorted(
        a for a in nao_migracoes if not a.lower().endswith(EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS)
    )

    ofensores = sorted(set(ofensores_por_extensao) | set(migracoes_nao_reconhecidas))
    assert not ofensores, (
        f"{len(ofensores)} arquivo(s) VERSIONADO(S) ficam invisíveis para o "
        "ruff (extend-exclude) e/ou para o job de CI (CAMINHOS_NAO_RELEVANTES) "
        "sem justificativa válida — nem prosa/imagem segura "
        f"({EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS}), nem migração que o "
        f"Django reconheça: {ofensores}"
        + (
            f" | falhas do Django ao tentar reconhecer: {falhas_do_django}"
            if falhas_do_django
            else ""
        )
    )


def test_determinar_intervalo_evento_nao_previsto_e_lado_seguro():
    intervalo, motivo = decisor.determinar_intervalo("merge_group", "", "", "", "")
    assert intervalo is None
    assert "lado seguro" in motivo
