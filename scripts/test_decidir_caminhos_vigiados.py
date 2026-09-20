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

import pkgutil
import shutil
import subprocess
import sys
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
    """PERGUNTA ao `ruff` de verdade o que ele enxerga — nunca deduz lendo
    configuração e reimplementando o resolvedor de exclusão.

    **BL-418 (achado do arquiteto-senior, e é o mesmo eixo da DE-057 um
    nível abaixo).** Até esta correção, esta função lia `tool.ruff.
    extend-exclude` do `pyproject.toml` (`tomllib`) e reimplementava o
    glob do `ruff` com `fnmatch.fnmatch` (BL-417, ver histórico abaixo).
    MEDIDO pelo arquiteto: acrescentar a chave IRMÃ `exclude` (que SOMA a
    `extend-exclude`, não a substitui) na mesma tabela `[tool.ruff]` — sem
    tocar `extend-exclude` — escondia `ferramentas/velho.py` (4 erros
    reais) do `ruff check .` (`All checks passed!`) enquanto este teste,
    que só sabia ler UMA das chaves, continuava `31 passed`. E o próximo
    item da MESMA lista já é conhecido sem precisar medir: `ruff.toml`/
    `.ruff.toml` na raiz SUBSTITUEM o `[tool.ruff]` do `pyproject.toml`
    inteiro; `respect-gitignore`; configuração por subdiretório. Cada um
    exigiria uma nova função de leitura e um novo "limite declarado" —
    exatamente o padrão que a DE-057 já cortou uma vez, na fatia 2 da
    DL-028: o motor de cascata CSS simulava o navegador em vez de abrir um
    Chromium de verdade, e cada propriedade nova (`clip-path`,
    `content-visibility`, pseudo-classe) virava um limite declarado novo,
    até a correção certa ser PERGUNTAR ao motor de layout real. Aqui é o
    MESMO eixo, um nível abaixo: em vez de reimplementar "o que o `ruff`
    esconde" lendo arquivo de configuração, PERGUNTAMOS ao `ruff`.

    **A derivação, sem lista nenhuma:** todo arquivo de código VERSIONADO
    (`.py`/`.pyi`/`.ipynb` — as extensões que o `ruff` considera por
    padrão) que NÃO aparece em `ruff check --show-files .` está escondido
    — não importa POR QUE (`exclude`, `extend-exclude`, `ruff.toml`
    substituindo tudo, `.gitignore`, uma opção que a próxima versão do
    `ruff` inventar). Isso fecha a CLASSE, não o caso do `extend-exclude`
    — é a resposta à objeção do arquiteto: "não vou comprar o quarto item
    da mesma lista".

    **Custo medido (a objeção real a abrir um subprocesso por execução):**
    ver a docstring do teste principal, abaixo, para o número antes/depois
    — aqui só a decisão de design: um subprocesso por chamada desta
    função (uma vez por execução do teste) é aceitável porque substitui
    UMA leitura de arquivo mais um loop em memória (o que a versão
    anterior fazia) por UMA chamada de processo — não é um subprocesso
    por ARQUIVO.

    **`ruff` ausente no ambiente — decisão explícita, nunca silêncio
    (BL-375: diferencial que vira no-op na CI é o MESMO defeito de
    inversão de lado seguro que já custou uma auditoria inteira aqui).**
    Se `shutil.which("ruff")` não encontrar o binário, este teste PULA
    (`pytest.skip`) com o motivo nomeado — nunca passa calado tratando
    "não consegui perguntar" como "a resposta é vazia". `ruff` é
    dependência de desenvolvimento (`requirements/dev.txt`) e a CI sempre
    o instala antes de rodar o `pytest` (mesmo job, passo anterior) — o
    `skip` é para bancada sem o `requirements/dev.txt` instalado, nunca
    esperado na integração contínua.

    **Histórico (BL-417, não mecanismo vivo mais):** a versão anterior
    media que `decidir_caminhos_vigiados.padrao_para_regex` (semântica do
    `paths:` do GitHub Actions, onde `*` não cruza `/`) NÃO reproduzia o
    `ruff` real para `*/migrations/*`, e usava `fnmatch.fnmatch` como
    matcher mais fiel — medido equivalente, NESTA árvore, NESTA data,
    contra `ruff check --show-files .`. Essa medição e o comentário
    completo ficam preservados no histórico do Git (commit `40d8329`);
    esta função não lê mais configuração nenhuma, então o matcher deixou
    de existir para ela — não há mais "qual glob simular", porque não há
    mais simulação."""
    if shutil.which("ruff") is None:
        pytest.skip(
            "ruff não está instalado neste ambiente (shutil.which('ruff') "
            "devolveu None) — este teste PERGUNTA à ferramenta o que ela "
            "esconde (nunca deduz lendo pyproject.toml/ruff.toml), então sem "
            "o binário não há a quem perguntar. Pular com motivo nomeado, "
            "nunca passar em silêncio (BL-375). Instale via "
            "requirements/dev.txt antes de rodar esta suíte."
        )

    codigo_que_o_ruff_poderia_ver = {
        a for a in arquivos_versionados if a.endswith((".py", ".pyi", ".ipynb"))
    }
    resultado = subprocess.run(
        ["ruff", "check", "--show-files", "."],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    visto_pelo_ruff = {
        str(Path(linha).resolve().relative_to(raiz))
        for linha in resultado.stdout.splitlines()
        if linha
    }
    return codigo_que_o_ruff_poderia_ver - visto_pelo_ruff


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
    """BL-409/K6 (décima auditoria) → BL-415 (extensão é lista aberta,
    corrigido com `EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS`) → BL-416/417
    (o teste só olhava UMA das duas listas do K5; a correção uniu
    `CAMINHOS_NAO_RELEVANTES` com `tool.ruff.extend-exclude`, lida e
    reimplementada com `fnmatch`) → **BL-418 (achado do arquiteto-senior,
    e o mesmo eixo da DE-057 um nível abaixo): a correção do BL-416 ainda
    ERA uma lista — não de extensão, de CHAVE de configuração.** MEDIDO
    pelo arquiteto: acrescentar `exclude = ["ferramentas/**"]` na MESMA
    tabela `[tool.ruff]`, ao lado (nunca substituindo) de `extend-exclude`
    — chave IRMÃ que soma, não a mesma — voltava a esconder `ferramentas/
    velho.py` (4 erros reais) do `ruff check .`, com este teste (que só
    sabia ler `extend-exclude`) `31 passed`. E o item seguinte já era
    conhecido sem precisar medir: `ruff.toml`/`.ruff.toml` na raiz
    SUBSTITUEM o `[tool.ruff]` inteiro do `pyproject.toml`;
    `respect-gitignore`; configuração por subdiretório — cada um exigiria
    uma função de leitura nova e um limite declarado novo.

    **A correção fecha a CLASSE, não o caso: pergunta ao `ruff`, não
    deduz da configuração dele** (`_escondidos_pelo_ruff`, acima — a
    docstring de lá tem a medição completa, o custo e o comportamento
    para `ruff` ausente). `fnmatch` e a leitura de `tomllib` SAÍRAM desta
    função; o matcher do BL-417 vira história no comentário — deixou de
    existir mecanismo para simular, porque não há mais simulação. O
    universo de "escondido" continua sendo a UNIÃO — só que agora um dos
    dois lados é medido de verdade (`ruff check --show-files .`) e o
    outro continua lido da fonte (`CAMINHOS_NAO_RELEVANTES`, que É nosso
    código — perguntar à fonte, ali, já é o `import`).

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
    critério 3 da rodada do BL-418; e o `"ferramentas/**"` no
    `extend-exclude`, do BL-416, critério 2). E, contra a árvore real, sem
    sabotagem nenhuma: `git ls-files` dá **217** arquivos `.py`/`.pyi`/
    `.ipynb`; `ruff check --show-files .` mostra **196** linhas — mas
    ATENÇÃO, `217 - 196` não é a conta certa por subtração direta: o
    `ruff` também lista `pyproject.toml` em `--show-files` (não é
    `.py`/`.pyi`/`.ipynb`, fora do nosso universo de código), então a
    DIFERENÇA DE CONJUNTOS (a operação que o código faz, nunca a
    aritmética dos dois totais publicados) é o número correto: **22**
    arquivos de código escondidos só pelo `ruff` — todas as migrações. A
    união com o job de CI dá **180** arquivos escondidos (158 pelo job de
    CI + os 22 do `ruff`), **zero ofensores** — os 22 candidatos de
    `migrations/` batem exatamente com os 16 que o Django reconhece mais
    os 6 `__init__.py` dispensados à parte (16 + 6 = 22).

    **Custo medido (a objeção do arquiteto à ideia de abrir um
    subprocesso por execução).** `ruff check --show-files .` sozinho:
    `real 0m0.011s` (`time`). A suíte deste arquivo inteira (31 testes),
    três execuções ANTES desta correção (versão `fnmatch`/`tomllib`,
    sem subprocesso): `0.35s`, `0.37s`, `0.39s`. Três execuções DEPOIS
    (com o subprocesso do `ruff`): `0.37s`, `0.37s`, `0.33s`. Sem
    diferença que se distinga do ruído de medição — o `ruff` é escrito em
    Rust e o `--show-files` não faz o lint completo, só a resolução de
    arquivos; o custo de abrir UM subprocesso por EXECUÇÃO do teste
    (nunca por arquivo) é desprezível perto do resto da suíte (a suíte
    INTEIRA do projeto leva dezenas de segundos por causa do Django/
    Postgres, não deste teste).

    **`ruff` ausente no ambiente:** `pytest.skip`, com o motivo nomeado
    (ver `_escondidos_pelo_ruff`) — nunca passa em silêncio. `ruff` é
    dependência de desenvolvimento (`requirements/dev.txt`) e a CI
    sempre a instala antes do `pytest` no MESMO job (`backend.yml`),
    então o `skip` só deveria acontecer em bancada sem `requirements/
    dev.txt` instalado — nunca esperado na integração contínua.

    **DE-056 (R5), de novo — e a natureza das respostas MUDOU**, como o
    arquiteto previu: as quatro fontes anteriores eram todas sobre "ler a
    configuração do `ruff`" e SOMEM com esta correção (perguntar à
    ferramenta fecha `exclude`, `extend-exclude`, `ruff.toml`/`.ruff.toml`
    substituindo tudo, `respect-gitignore`, configuração por subdiretório
    — nenhuma lista nossa nomeia mais nada disso). O que sobra é de OUTRA
    natureza — dentro de um arquivo que o `ruff` EXAMINA, ou fora do
    `ruff` por completo:

    1. **`per-file-ignores` e `# noqa` em linha — mesma classe, e ela NÃO
       é sobre configuração lida.** MEDIDO de novo (nada mudou no
       repositório): `grep -n "per-file-ignores" pyproject.toml` não bate
       (não existe hoje); `grep -rn "# noqa" --include="*.py" .` (fora
       `.venv`) dá **15** ocorrências, todas com código específico
       (`E402`, `BLE001`, `F401`) — nenhuma silencia a linha inteira. Mas
       o motivo de ficarem fora **mudou**: não é mais "não lemos essa
       chave" — é que a derivação deste teste responde SÓ "o `ruff`
       EXAMINA este arquivo?" (binário), nunca "toda regra aplicável
       está ATIVA nele?". Um arquivo aparece em `--show-files`
       (visível, não-ofensor) e ainda assim ter uma regra real desligada
       por dentro — `per-file-ignores` ou `# noqa` — sem que a visão
       binária "visto/não visto" tenha como saber. É um limite da FORMA
       da pergunta, não da fonte da resposta.
    2. **O lado do `pytest` ("o que ninguém executa")** — que o arquiteto
       pediu para eu MEDIR e DECLARAR, não fechar. MEDIDO:
       `[tool.pytest.ini_options]` não declara `testpaths` nem
       `norecursedirs`; `conftest.py` não tem `collect_ignore` nem
       `pytest_ignore_collect`; nenhum `addopts`. Hoje, nada restringe a
       coleta. Mas ESTE teste é, ele mesmo, um `test_*.py` — se algum dia
       alguém declarar `testpaths` restrito (ou um `collect_ignore` em
       `conftest.py`), ESTE arquivo pode parar de ser coletado, e a
       suíte fica silenciosamente MENOR (menos itens coletados, sem
       nenhum vermelho) — a guarda desaparece em vez de reprovar. Não
       fechei isto (é decisão do arquiteto-senior e do Fred, não minha).
    3. **O lado do job — declarado, não medido de novo por mim** (não
       tenho acesso à API do GitHub, e não é meu papel medir de novo o
       que já está medido): este teste pode deixar o job `Backend`
       vermelho, mas `AGENTS.md` já registra, com fonte (achado J2 da
       nona auditoria, `docs/auditorias/2026-09-19-dl-026-dl-028-rodada-
       9.md`), que a `main` **não tem proteção de branch** — um job
       vermelho não impede merge hoje. Cito a fonte em vez de reafirmar
       sem medir (a lição do K4)."""
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
