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


def test_caminhos_nao_relevantes_so_esconde_prosa_e_imagem_conhecida():
    """BL-409/K6 (décima auditoria,
    docs/auditorias/2026-09-20-dl-026-dl-028-rodada-10.md), CORRIGIDO por
    BL-415 (achado do arquiteto-senior sobre a integração do BL-409): a
    primeira versão deste teste também era uma LISTA — perguntava "a
    extensão do arquivo está em `{py, css, html, yml, yaml, toml}`?" — e o
    arquiteto mediu o item seguinte dela em menos de uma hora: um `.sh`,
    um `.ps1` e um `.js` sob `docs/`, nenhum deles numa extensão que a
    lista antiga sabia nomear, passavam pelo teste em silêncio — a MESMA
    classe de defeito do BL-408, um nível acima.

    **A correção inverte o lado, como `CAMINHOS_NAO_RELEVANTES` já faz e
    como o J9 elogiou**: em vez de enumerar o que é PERIGOSO (lista aberta,
    cresce com a linguagem — é o erro do BL-355/BL-367, aqui de novo), esta
    função enumera o que pode LEGITIMAMENTE ficar invisível para
    `ruff`/`pytest`/CI — prosa e imagem, `EXTENSOES_SEGURAS_PARA_FICAR_
    INVISIVEIS` abaixo — e reprova TUDO o mais que qualquer padrão de
    `CAMINHOS_NAO_RELEVANTES` esconder, inclusive um arquivo SEM extensão
    nenhuma (`arquivo.endswith(EXTENSOES_SEGURAS...)` já falha por conta
    própria quando não há `.` nenhum no nome — não precisa de caso especial).

    Continuamos andando por `git ls-files` — nunca por `os.walk` ou
    `Path.glob`: o que importa é o ÍNDICE do Git, não o disco solto de
    quem roda o teste.

    **MEDIDO antes de escrever a lista permitida** (nunca deduzido — é a
    exigência do BL-321 que o `pyproject.toml` já cumpriu e que este teste
    replica): `git ls-files` mais os padrões de `CAMINHOS_NAO_RELEVANTES`
    aplicados dão **158** arquivos hoje escondidos de CI, e TODOS caem em
    só três extensões — `md` (115), `png` (29), `svg` (14); zero sem
    extensão, zero em qualquer outra. Comando exato, reproduzível:

    ```
    python3 -c "
    import subprocess, collections
    import decidir_caminhos_vigiados as d
    arquivos = subprocess.run(['git', 'ls-files'], capture_output=True,
        text=True, check=True, cwd='..').stdout.splitlines()
    padroes = [d.padrao_para_regex(p) for p in d.CAMINHOS_NAO_RELEVANTES]
    escondidos = [a for a in arquivos if d.bate(padroes, a)]
    print(len(escondidos), collections.Counter(
        a.rsplit('.', 1)[-1].lower() if '.' in a.rsplit('/', 1)[-1] else '(sem extensão)'
        for a in escondidos))
    "
    ```
    devolve `158 Counter({'md': 115, 'png': 29, 'svg': 14})` — é exatamente
    por isso que a lista permitida abaixo tem só três itens: não é uma
    escolha estética, é o inventário real na data desta correção.

    **DE-056 (R5), aplicada a este próprio arquivo — a lista que SOBROU
    depois de inverter, e o que acontece com o item seguinte dela.**
    `EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS`, abaixo, também é uma lista —
    só que agora do LADO SEGURO: o item seguinte dela (uma quarta extensão
    de prosa ou imagem ainda não prevista — `.rst`, `.jpg`, `.pdf` de um
    manual, por exemplo) faz este teste REPROVAR o arquivo novo, mesmo que
    ele seja inofensivo. MEDIDO, não deduzido: criei em cópia isolada
    (`git worktree`, removida depois — não a árvore deste projeto, BL-311)
    um `docs/exemplo/manual.pdf` versionado e rodei este teste contra
    aquele worktree: reprova, nomeando `docs/exemplo/manual.pdf` como
    ofensor. É o comportamento CORRETO e é a troca deliberada: o lado
    seguro de uma lista de exclusão (`CAMINHOS_NAO_RELEVANTES`) é pecar por
    RELEVÂNCIA DEMAIS (medir de mais nunca esconde regressão); o lado
    seguro de uma lista de permissão (esta) é pecar por PERMISSÃO DE MENOS
    — um `.pdf` legítimo em `docs/` reprova a suíte e obriga alguém a
    ACRESCENTAR a extensão aqui, em vez de a lista permitida crescer
    sozinha por trás de ninguém olhar. A mesma troca que `CAMINHOS_NAO_
    RELEVANTES` fez ao virar do avesso (BL-376) — só que aqui o lado que
    "erra para o seguro" é o oposto, porque a pergunta também é oposta
    ("o que pode ficar escondido" em vez de "o que precisa ser visto")."""
    raiz = Path(__file__).resolve().parents[1]
    resultado = subprocess.run(
        ["git", "ls-files"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    arquivos_versionados = [linha for linha in resultado.stdout.splitlines() if linha]

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
    padroes_compilados = [decisor.padrao_para_regex(p) for p in decisor.CAMINHOS_NAO_RELEVANTES]

    escondidos = [a for a in arquivos_versionados if decisor.bate(padroes_compilados, a)]
    ofensores = sorted(
        arquivo
        for arquivo in escondidos
        if not arquivo.lower().endswith(EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS)
    )
    assert not ofensores, (
        f"{len(ofensores)} arquivo(s) VERSIONADO(S) ficam INVISÍVEIS para "
        f"ruff/pytest/CI (batem em algum padrão de CAMINHOS_NAO_RELEVANTES: "
        f"{decisor.CAMINHOS_NAO_RELEVANTES}) com uma extensão que NÃO está "
        f"na lista segura {EXTENSOES_SEGURAS_PARA_FICAR_INVISIVEIS} (ou sem "
        f"extensão nenhuma): {ofensores}"
    )


def test_determinar_intervalo_evento_nao_previsto_e_lado_seguro():
    intervalo, motivo = decisor.determinar_intervalo("merge_group", "", "", "", "")
    assert intervalo is None
    assert "lado seguro" in motivo
