"""Achado R3-4 da auditoria DL-017, rodada 3
(docs/auditorias/2026-09-14-dl-017-rodada-3.md).

`apps/contabilidade/views_web.py` usava `except TypeError, ValueError:`
(sintaxe da PEP 758, exclusiva do Python 3.14) desde `9b22b03`, enquanto o
`README.md` promete "Python 3.12+" (a integração contínua roda em 3.14, e o
`Dockerfile` é `python:3.14-slim` — ninguém rodando 3.12/3.13 jamais
carregaria esse arquivo durante o desenvolvimento). Quem seguisse o README
literalmente, instalando 3.12 ou 3.13, recebia `SyntaxError` ao carregar o
URLconf — o site inteiro deixava de subir, não só a contabilidade —, e nada
no projeto detectava isso: a CI só roda 3.14, e `pyproject.toml` não
declarava `requires-python`.

O `especialista-frontend` corrigiu a sintaxe (`except (TypeError,
ValueError):`, compatível com 3.12+) no arquivo dele. Este módulo cobre a
OUTRA metade do achado, que é minha: declarar a versão mínima
(`pyproject.toml`, `requires-python`) e VERIFICAR essa declaração por
mecanismo — nunca só prometer em documento (mesma lição de
`test_documentacao_do_estado.py` para o estado do projeto, agora aplicada à
versão de Python).

Por que `ast.parse(..., feature_version=...)` em vez de instalar três
interpretadores na CI: o parser do Python aceita o parâmetro `feature_version`
desde a 3.8 e RECUSA sintaxe exclusiva de versões posteriores àquela
declarada — inclusive rodando num interpretador mais novo (testado: 3.14
recusa `except A, B:` sem parênteses quando `feature_version=(3, 12)`, a
mesma mensagem que um interpretador 3.12 real daria). Isso roda em qualquer
lugar (não depende de instalar 3.12/3.13 na imagem da CI, que é 3.14) e é
rápido — compilar ~100 arquivos leva frações de segundo.

**Medição cuja falha não consegue falhar não é medição** (lição registrada
pelo próprio arquiteto-senior na rodada 3, depois de usar `py_compile ... |
tail -1 && echo OK` — o código de saída de um pipeline é o do ÚLTIMO
comando, e "OK" aparecia mesmo nas versões que falhavam). Por isso
`test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`
abaixo prova, na própria suíte, que a checagem SABE falhar: aplica
`feature_version=(3, 12)` sobre a sintaxe exata do defeito original e exige
`SyntaxError` — se alguém "consertar" a verificação principal para nunca
reprovar nada (o mesmo erro do `tail -1`), este teste continua reprovando.
"""

import ast
import tomllib
from pathlib import Path

import pytest

# apps/core/tests/test_x.py -> apps/core -> apps -> raiz do repositório.
BASE_DIR = Path(__file__).resolve().parents[3]

# Diretórios que NUNCA contêm código de produção deste projeto — ambiente
# virtual, controle de versão e caches. Migrações ENTRAM na varredura de
# propósito: são código real, executado em produção, não um artefato
# gerado.
_DIRETORIOS_EXCLUIDOS = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}


def _dados_pyproject():
    return tomllib.loads((BASE_DIR / "pyproject.toml").read_text(encoding="utf-8"))


def _versao_minima_declarada(dados=None):
    """Lê `requires-python` de `pyproject.toml` e devolve `(maior, menor)`.

    Não hardcoda a versão aqui: se `pyproject.toml` mudar a declaração (a
    decisão do R3-4 é reversível — ver `docs/projeto/decisoes.md`, DE-030 e
    o achado R3-4), este teste passa a verificar a versão NOVA
    automaticamente, sem precisar de outra alteração. É a mesma razão pela
    qual a declaração e a verificação vivem em arquivos diferentes, mas
    concordam sempre: uma lê a outra, nunca duplica o número.
    """
    dados = dados if dados is not None else _dados_pyproject()
    bruto = dados["project"]["requires-python"]
    # Formato esperado: ">=3.12" (o único que este projeto usa hoje). Um
    # formato mais complexo (">=3.12,<4") levantaria aqui, de propósito —
    # melhor um erro claro no teste do que uma extração errada silenciosa.
    assert bruto.startswith(">="), (
        f"requires-python={bruto!r} não começa com '>=': ajuste este parser "
        "junto com a mudança em pyproject.toml."
    )
    maior_str, menor_str = bruto.removeprefix(">=").split(".")
    return int(maior_str), int(menor_str)


def _target_version_do_ruff(dados=None):
    """Lê `[tool.ruff].target-version` (formato `"py312"`) e devolve
    `(maior, menor)`, na mesma forma de `_versao_minima_declarada`.

    Assume major único ("3") seguido do minor sem separador — verdadeiro
    para todo `target-version` do ruff até hoje (`py38` .. `py314`); um
    Python 4 exigiria revisar este parser, e a asserção abaixo torna isso
    visível em vez de extrair um número errado em silêncio.
    """
    dados = dados if dados is not None else _dados_pyproject()
    bruto = dados["tool"]["ruff"]["target-version"]
    assert bruto.startswith("py") and bruto[2:].isdigit(), (
        f"target-version={bruto!r} não está no formato 'pyXYZ' esperado."
    )
    digitos = bruto.removeprefix("py")
    return int(digitos[0]), int(digitos[1:])


def _arquivos_py_do_repositorio():
    for caminho in sorted(BASE_DIR.rglob("*.py")):
        relativo = caminho.relative_to(BASE_DIR)
        if any(parte in _DIRETORIOS_EXCLUIDOS for parte in relativo.parts):
            continue
        yield caminho


def test_versao_minima_esta_declarada_em_pyproject():
    """Controle de que a leitura acima funciona e devolve algo plausível —
    se `pyproject.toml` perder `requires-python`, este teste falha com uma
    mensagem clara, em vez de o teste principal falhar por um `KeyError`
    difícil de relacionar ao achado R3-4."""
    maior, menor = _versao_minima_declarada()
    assert (maior, menor) >= (3, 8), (maior, menor)  # ast.parse aceita feature_version >= 3.8


def test_target_version_do_ruff_bate_com_requires_python():
    """Achado do arquiteto-senior durante a revisão desta etapa: declarar
    `requires-python = ">=3.12"` sem alinhar `[tool.ruff].target-version`
    reabre exatamente a classe do R3-4 por outra porta. `target-version`
    diz ao ruff qual sintaxe é aceitável MODERNIZAR PARA — com ele em
    `"py314"` ao lado de `requires-python = ">=3.12"`, o ruff ficava
    autorizado a sugerir (e, com `--fix`, a ESCREVER) construções
    exclusivas do 3.14, como o `except A, B:` sem parênteses que originou
    este achado. Medido: com `target-version = "py312"`, o próprio `ruff
    check .` passou a acusar essa sintaxe como `invalid-syntax` — o linter
    virou uma SEGUNDA camada de defesa, sem duplicar a regra (ele lê a
    mesma versão, não redeclara um número).

    Este teste garante que as duas declarações nunca voltam a divergir: se
    alguém atualizar uma sem a outra, a suíte reprova aqui, explicando o
    motivo, em vez de esperar uma auditoria encontrar a divergência de novo.
    """
    dados = _dados_pyproject()
    versao_minima = _versao_minima_declarada(dados)
    versao_alvo_ruff = _target_version_do_ruff(dados)
    assert versao_alvo_ruff == versao_minima, (
        f"[tool.ruff].target-version (py{versao_alvo_ruff[0]}{versao_alvo_ruff[1]}) "
        f"diverge de [project].requires-python (>={versao_minima[0]}.{versao_minima[1]}) "
        "em pyproject.toml — um target-version mais NOVO que a versão mínima "
        "autoriza o ruff a sugerir/escrever sintaxe que o projeto promete não exigir "
        "(a causa exata do achado R3-4, auditoria DL-017 rodada 3)."
    )


def test_todos_os_py_do_repositorio_compilam_na_versao_minima_declarada():
    """O mecanismo central do R3-4: nenhum `.py` do repositório pode usar
    sintaxe exclusiva de uma versão de Python posterior à declarada em
    `requires-python`. Reprova listando TODOS os arquivos com problema (não
    só o primeiro), para que uma futura regressão múltipla apareça de uma
    vez, como a conferência de hierarquia (`localizar_inconsistencias_de_
    hierarquia`) faz para o plano de contas.
    """
    versao_minima = _versao_minima_declarada()
    falhas = []
    total_arquivos = 0
    for caminho in _arquivos_py_do_repositorio():
        total_arquivos += 1
        codigo_fonte = caminho.read_text(encoding="utf-8")
        try:
            ast.parse(codigo_fonte, filename=str(caminho), feature_version=versao_minima)
        except SyntaxError as exc:
            falhas.append(f"{caminho.relative_to(BASE_DIR)}:{exc.lineno}: {exc.msg}")

    # Nenhum repositório real tem zero arquivos .py — um total de 0 aqui
    # significaria que `_arquivos_py_do_repositorio` está varrendo o lugar
    # errado (ex.: `BASE_DIR` calculado errado), e o teste passaria por
    # engano, sem testar nada. Falhar alto é melhor que um "sucesso" vazio.
    assert total_arquivos > 50, (
        f"Só {total_arquivos} arquivo(s) .py encontrado(s) — suspeite de "
        "BASE_DIR ou dos diretórios excluídos antes de confiar neste teste."
    )
    assert not falhas, (
        f"{len(falhas)} arquivo(s) usam sintaxe incompatível com Python "
        f"{versao_minima[0]}.{versao_minima[1]}+ (declarado em "
        f"pyproject.toml, requires-python):\n" + "\n".join(falhas)
    )


def test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior():
    """A medição que consegue falhar (lição do arquiteto-senior na rodada 3
    sobre o `tail -1 && echo OK`): prova, na própria suíte, que `ast.parse`
    com `feature_version=(3, 12)` REJEITA a sintaxe exata do defeito
    original — `except A, B:` sem parênteses, PEP 758, exclusiva do Python
    3.14. Se este teste um dia passar a aceitar essa sintaxe (por exemplo,
    por um upgrade do `requires-python` sem atualizar este teste, ou por um
    erro na forma de chamar `ast.parse`), ele reprova sozinho — nunca um
    "OK" que não consegue virar erro.
    """
    codigo_exclusivo_do_314 = "try:\n    pass\nexcept TypeError, ValueError:\n    pass\n"
    # Controle negativo primeiro: a MESMA sintaxe, corrigida (com
    # parênteses), tem que continuar compilando em 3.12 — senão o teste
    # acima poderia estar recusando a sintaxe ERRADA por outro motivo, e
    # este teste positivo garante que o parser não está simplesmente
    # rejeitando qualquer `except` com duas exceções.
    codigo_compativel = "try:\n    pass\nexcept (TypeError, ValueError):\n    pass\n"
    ast.parse(codigo_compativel, feature_version=(3, 12))

    with pytest.raises(SyntaxError):
        ast.parse(codigo_exclusivo_do_314, feature_version=(3, 12))

    # E continua compilando sem restrição de versão (comprova que a
    # sintaxe em si é válida — é exclusiva de versão, não quebrada):
    ast.parse(codigo_exclusivo_do_314, feature_version=(3, 14))
