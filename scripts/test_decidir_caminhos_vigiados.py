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


def test_caminhos_nao_relevantes_nao_engole_arquivo_versionado_executavel():
    """BL-409/K6 (décima auditoria,
    docs/auditorias/2026-09-20-dl-026-dl-028-rodada-10.md): teste de
    PROPRIEDADE que o retrato acima não dava — "nenhum padrão desta lista
    engole arquivo executável ou de configuração que esteja VERSIONADO".

    Andamos por `git ls-files` — nunca por `os.walk` ou `Path.glob`: o que
    importa para `ruff`/`pytest`/CI é o que está no ÍNDICE do Git, não o
    que existe solto no disco de quem roda o teste (`__pycache__`, uma
    cópia de trabalho suja, um arquivo novo ainda não adicionado). Antes
    da correção do BL-408/K5, este teste REPROVAVA nomeando os dois
    arquivos do gauntlet (`docs/assets/design/gauntlet/sonda_visibilidade.
    py` e `docs/assets/design/gauntlet/juiz.py`) — 262 e 104 linhas de
    Python executável, importadas em tempo de execução por
    `scripts/medir_identificacao_do_emitente.py`, e mesmo assim invisíveis
    para `ruff check`, `ruff format --check` e para a suíte inteira do
    `pytest`, só por estarem sob `docs/**`. Depois de movê-los para
    `scripts/`, este teste passa a ser a GUARDA que impede a mesma classe
    de defeito de voltar: se `docs/**` (ou qualquer padrão futuro) voltar
    a casar com um `.py`/`.css`/`.html`/`.yml`/`.yaml`/`.toml` versionado,
    o nome do arquivo aparece na mensagem de falha — não é preciso uma
    auditoria para descobrir.

    **DE-056 (R5 da tarefa K5/K6) — a pergunta obrigatória sobre a lista
    que esta correção NÃO tocou.** `CAMINHOS_NAO_RELEVANTES` mora em
    `scripts/decidir_caminhos_vigiados.py`, arquivo que esta correção não
    edita (só o TESTA, aqui e no `pytest` acima). MEDIDO, não hipotetizado
    (acrescentei um quinto padrão, `"vendor_futuro/**"`, e rodei os dois
    testes contra a árvore real — nenhum arquivo versionado bate nele):
    o teste RETRATO acima REPROVA imediatamente, apontando a lista inteira
    na mensagem de diff; **este** teste de propriedade PASSA — 30/31 verdes,
    só o retrato vermelho. Ou seja: um padrão amplo, escrito HOJE, que
    ainda não tem vítima nenhuma no repositório passa batido por este
    teste — ele só reprova quando alguém, depois, adicionar um arquivo de
    código/configuração que caia nesse padrão novo. Se o "próximo item da
    lista" for esse tipo de entrada (uma exclusão pensada para algo que
    ainda não existe), a ÚNICA rede que pega a intenção no MOMENTO em que
    ela é escrita é o retrato — que obriga revisar o diff da lista — não
    esta função. É exatamente por isso que o retrato continua ao lado
    deste teste (ver a docstring dele, acima): nenhum dos dois substitui
    o outro."""
    raiz = Path(__file__).resolve().parents[1]
    resultado = subprocess.run(
        ["git", "ls-files"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    arquivos_versionados = [linha for linha in resultado.stdout.splitlines() if linha]

    # Extensões de CÓDIGO ou CONFIGURAÇÃO que, se ficarem fora do alcance
    # do `ruff`/`pytest`, reproduzem exatamente a classe de defeito do
    # BL-379/BL-408: lint e testes "passam" porque nunca viram o arquivo.
    extensoes_de_codigo_ou_configuracao = (".py", ".css", ".html", ".yml", ".yaml", ".toml")
    padroes_compilados = [decisor.padrao_para_regex(p) for p in decisor.CAMINHOS_NAO_RELEVANTES]

    ofensores = sorted(
        arquivo
        for arquivo in arquivos_versionados
        if arquivo.endswith(extensoes_de_codigo_ou_configuracao)
        and decisor.bate(padroes_compilados, arquivo)
    )
    assert not ofensores, (
        f"{len(ofensores)} arquivo(s) de código/configuração VERSIONADO(S) "
        "casam com algum padrão de CAMINHOS_NAO_RELEVANTES "
        f"({decisor.CAMINHOS_NAO_RELEVANTES}) e por isso ficam INVISÍVEIS "
        f"para ruff/pytest/CI: {ofensores}"
    )


def test_determinar_intervalo_evento_nao_previsto_e_lado_seguro():
    intervalo, motivo = decisor.determinar_intervalo("merge_group", "", "", "", "")
    assert intervalo is None
    assert "lado seguro" in motivo
