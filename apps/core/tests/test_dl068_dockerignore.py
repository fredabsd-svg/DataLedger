"""DL-068 (item 3 e critérios 7 e 11): o que o `Dockerfile` leva para a imagem.

O `Dockerfile` faz `COPY . .`. Sem `.dockerignore`, o `.env` real (segredos) e o
`.git` (todo o histórico) entram na imagem. Procurar o texto `.env` dentro do
arquivo NÃO prova nada: uma regra comentada, ou desfeita por uma negação
posterior, passaria. Por isso este teste INTERPRETA o `.dockerignore` com a
semântica do Docker e pergunta, caminho a caminho, se ele fica fora ou dentro.

Semântica implementada (a do Docker, `moby/patternmatcher`):

- uma linha por padrão; vazia e iniciada por `#` são ignoradas;
- `!` no início nega: re-inclui o que as regras anteriores excluíram;
- a ÚLTIMA regra que casa decide;
- o padrão é relativo à raiz do contexto e casa segmento por segmento: `*` não
  atravessa `/`, e um segmento `**` casa zero ou mais diretórios;
- um padrão que casa um diretório exclui tudo o que está dentro dele.

O casamento de cada segmento é `fnmatch` (`*`, `?` e `[...]`).
"""

import fnmatch
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DOCKERIGNORE = RAIZ / ".dockerignore"
DOCKERFILE = RAIZ / "Dockerfile"
ENV_EXAMPLE = RAIZ / ".env.example"


# --- O interpretador ---------------------------------------------------------


def _ler_regras(texto):
    """Lista de `(negacao, segmentos)` na ordem do arquivo."""
    regras = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        negacao = linha.startswith("!")
        if negacao:
            linha = linha[1:].strip()
        linha = linha.lstrip("/").rstrip("/")
        if linha:
            regras.append((negacao, tuple(linha.split("/"))))
    return regras


def _casa(padrao, partes):
    """`padrao` e `partes` são tuplas de segmentos; `**` casa zero ou mais."""
    if not padrao:
        return not partes
    if padrao[0] == "**":
        return any(_casa(padrao[1:], partes[i:]) for i in range(len(partes) + 1))
    if not partes:
        return False
    # `fnmatchcase`: o Docker não ignora caixa nem normaliza nada no Linux.
    return fnmatch.fnmatchcase(partes[0], padrao[0]) and _casa(padrao[1:], partes[1:])


def _fica_fora(regras, caminho):
    """Verdadeiro se o caminho NÃO entra no contexto de build."""
    partes = tuple(caminho.split("/"))
    # O caminho e cada diretório que o contém: regra que casa um pai vale.
    candidatos = [partes[: i + 1] for i in range(len(partes))]
    excluido = False
    for negacao, padrao in regras:
        if any(_casa(padrao, candidato) for candidato in candidatos):
            excluido = not negacao
    return excluido


@pytest.fixture(scope="module")
def regras():
    return _ler_regras(DOCKERIGNORE.read_text(encoding="utf-8"))


# --- Controles positivos: o interpretador não aprova tudo --------------------


def test_interpretador_a_ultima_regra_que_casa_decide():
    regras = _ler_regras(".env\n.env.*\n!.env.example\n")

    assert _fica_fora(regras, ".env")
    assert _fica_fora(regras, ".env.producao")
    assert not _fica_fora(regras, ".env.example")

    # Invertida, a negação perde: a ordem importa, e o interpretador sabe.
    invertidas = _ler_regras("!.env.example\n.env.*\n")
    assert _fica_fora(invertidas, ".env.example")


def test_interpretador_ignora_comentario_e_linha_vazia():
    regras = _ler_regras("# .env\n\n   \n# .git\n")

    assert regras == []
    assert not _fica_fora(regras, ".env")


def test_interpretador_estrela_nao_atravessa_diretorio_e_dupla_estrela_atravessa():
    simples = _ler_regras("*.pyc\n")
    dupla = _ler_regras("**/*.pyc\n")

    assert _fica_fora(simples, "x.pyc")
    assert not _fica_fora(simples, "apps/x.pyc")
    assert _fica_fora(dupla, "x.pyc")
    assert _fica_fora(dupla, "apps/core/__pycache__/x.pyc")


def test_interpretador_diretorio_excluido_leva_o_conteudo():
    regras = _ler_regras(".git\n")

    assert _fica_fora(regras, ".git/HEAD")
    assert _fica_fora(regras, ".git/objects/ab/cdef")
    # `.git` não pode casar `.github` por prefixo de texto.
    assert not _fica_fora(regras, ".github/workflows/backend.yml")


# --- Critério 7: o que fica fora da imagem -----------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        # Segredos.
        ".env",
        ".env.producao",
        ".env.local",
        # Segredo em QUALQUER profundidade e com qualquer nome terminado em
        # `.env` (auditoria da DL-068, N5): o padrão do Docker sem `**/` vale
        # só na raiz do contexto.
        "config/.env",
        "apps/x/.env",
        "prod.env",
        "config/.env.local",
        "ENV.env",
        # Certificado e chave privada (o módulo fiscal tratará certificado
        # digital; o repositório é público).
        "certs/empresa.pfx",
        "a/b/chave.key",
        "cert.pem",
        "x.p12",
        # Histórico.
        ".git/HEAD",
        ".git/objects/ab/cdef0123",
        ".github/workflows/backend.yml",
        # Ambiente local e caches.
        ".venv/bin/python",
        "venv/bin/python",
        "apps/core/__pycache__/models.cpython-313.pyc",
        "manage.pyc",
        ".pytest_cache/v/cache/lastfailed",
        ".ruff_cache/CACHEDIR.TAG",
        ".coverage",
        "htmlcov/index.html",
        "staticfiles/admin/css/base.css",
        # Banco local: um banco inteiro, possivelmente com dado de cliente.
        "db.sqlite3",
        "nao_deve_ser_criado.sqlite3",
        # Ferramentas de IA.
        ".claude/settings.json",
        ".claude/agents/auditor-qa.md",
        ".codex/agents/auditor-qa.toml",
        ".agents/skills/x/SKILL.md",
    ],
)
def test_dockerignore_deixa_de_fora_segredo_historico_e_ambiente_local(regras, caminho):
    assert _fica_fora(regras, caminho), f"{caminho} entraria na imagem"


# --- O que PRECISA entrar na imagem ------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        ".env.example",
        "manage.py",
        "Dockerfile",
        "requirements/base.txt",
        "config/settings.py",
        "config/wsgi.py",
        "apps/core/models.py",
        "apps/auditoria/checks.py",
        "templates/base.html",
        "static/css/base.css",
        # `docs/` não é lido em tempo de execução pelo produto, mas o pedido é
        # não excluí-lo: o que a imagem leva é decisão do arquiteto, não efeito
        # colateral do `.dockerignore`.
        "docs/projeto/requisitos.md",
    ],
)
def test_dockerignore_nao_exclui_o_que_a_aplicacao_precisa(regras, caminho):
    """A falha deste teste é a pior: a imagem sobe sem o código, ou sem as
    folhas de estilo que `collectstatic` empacota. `static/` em particular não
    pode ser pego por uma regra de `staticfiles`."""
    assert not _fica_fora(regras, caminho), f"{caminho} NÃO entraria na imagem"


def test_dockerignore_nao_usa_padrao_em_que_o_interpretador_diverge_do_docker():
    """O interpretador do teste foi comparado com o `moby/patternmatcher` (o
    código do Docker) e só diverge em formas que este arquivo não usa:
    `dir/**` sobre o próprio `dir`, `**` colado a outro texto no segmento
    (`foo**bar`) e caminhos com `./` ou `..`. Se uma delas entrar, o teste do
    `.dockerignore` deixaria de ser fiel ao Docker; melhor reprovar aqui."""
    for _negacao, segmentos in _ler_regras(DOCKERIGNORE.read_text(encoding="utf-8")):
        padrao = "/".join(segmentos)
        assert segmentos[-1] != "**", f"{padrao}: `**` no fim diverge do Docker"
        assert all("**" not in s or s == "**" for s in segmentos), f"{padrao}: `**` colado"
        assert all(s not in (".", "..") for s in segmentos), f"{padrao}: `.` ou `..`"


def test_todo_arquivo_copiado_pelo_dockerfile_existe_no_contexto(regras):
    """O `Dockerfile` copia `requirements/base.txt` isoladamente (para o cache
    de dependências) antes do `COPY . .`. Se o `.dockerignore` o excluísse, o
    build quebraria no segundo passo."""
    for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if partes and partes[0] == "COPY" and partes[1] != ".":
            origem = partes[1]
            assert (RAIZ / origem).exists(), origem
            assert not _fica_fora(regras, origem), origem


# --- Critério 11: Dockerfile e .env.example declaram o ambiente --------------


def _instrucoes_do_dockerfile():
    """Instruções do Dockerfile, com as continuações `\\` unidas e os
    comentários descartados (um comentário que cite `DJANGO_AMBIENTE=producao`
    não pode contar como declaração)."""
    instrucoes = []
    atual = ""
    for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if not atual and (not linha.strip() or linha.lstrip().startswith("#")):
            continue
        atual += " " + linha.strip().removesuffix("\\")
        if not linha.rstrip().endswith("\\"):
            instrucoes.append(atual.split())
            atual = ""
    return instrucoes


def test_imagem_declara_ambiente_producao():
    """DL-068: quem roda a imagem é produção até dizer o contrário. Sem isto, a
    guarda do BL-82 só funcionaria para quem se lembrasse de declarar."""
    declaracoes = [
        palavra
        for instrucao in _instrucoes_do_dockerfile()
        if instrucao[0] == "ENV"
        for palavra in instrucao[1:]
        if palavra.startswith("DJANGO_AMBIENTE=")
    ]

    assert declaracoes == ["DJANGO_AMBIENTE=producao"]


def test_env_example_declara_ambiente_desenvolvimento():
    """O `.env.example` traz `DEBUG=True`. Sobre a imagem (produção), isso só
    sobe se o mesmo arquivo declarar `desenvolvimento`."""
    valores = {}
    for linha in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()

    assert valores.get("DJANGO_AMBIENTE") == "desenvolvimento"
    assert valores.get("DEBUG") == "True"


def test_collectstatic_do_dockerfile_declara_o_proprio_banco_descartavel():
    """Com o `.env` fora da imagem, o `collectstatic` (que roda com DEBUG=False)
    perde a `DATABASE_URL` que antes vinha por acidente do `COPY . .`, e
    `settings.py` recusa importar sem ela. O build precisa declará-la no
    próprio `RUN`; sem isso a imagem deixa de ser construída."""
    runs = [
        instrucao
        for instrucao in _instrucoes_do_dockerfile()
        if instrucao[0] == "RUN" and "collectstatic" in instrucao
    ]

    assert len(runs) == 1
    assert any(palavra.startswith("DATABASE_URL=postgres") for palavra in runs[0])
    assert any(palavra.startswith("DJANGO_SECRET_KEY=") for palavra in runs[0])
