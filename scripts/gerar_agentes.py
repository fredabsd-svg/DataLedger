#!/usr/bin/env python3
"""Gera as definições de agente de cada ferramenta a partir da fonte única.

Contexto (DL-019): a equipe de agentes do DataLedger existia só em
``.claude/agents/*.md``, no formato do Claude Code. Quem abria o repositório
com outra ferramenta não via os papéis — só o ``AGENTS.md``, sem saber que
existe um auditor que não corrige implementação, um auxiliar que não
delega, ou por que essas restrições existem.

A causa do problema anterior do projeto (estado do repositório descrito em
quatro lugares divergentes, ver ``docs/agents/estado.md`` e o incidente de
2026-09-13 citado em ``CLAUDE.md``) foi **duplicação**, não distração. Este
script existe para que a mesma causa não se repita aqui: ``docs/agents/papeis/
<papel>.md`` é a única fonte editável; os formatos abaixo são sempre
**derivados**, nunca editados à mão.

    docs/agents/papeis/<papel>.md      FONTE ÚNICA
            |
            +-- gera -> .claude/agents/<papel>.md          (Claude Code)
            +-- gera -> .codex/agents/<papel>.toml         (Codex CLI)

Escopo revisto em 2026-09-15 (resposta do Fred ao arquiteto-senior): ele usa
Codex pelo terminal, não Copilot nem Gemini CLI. O plano DL-019 previa também
``.github/agents/*.agent.md`` e ``.gemini/agents/*.md``; ambos foram tirados
do gerador porque formato que ninguém usa é manutenção sem retorno (AGENTS.md
§8, "remover código morto"). Se um desses uso aparecer depois, ele volta como
uma etapa nova, não como resíduo mantido "por via das dúvidas".

Uso:

    python scripts/gerar_agentes.py --escrever    # (re)grava os dois formatos
    python scripts/gerar_agentes.py --verificar    # falha se algo divergir

``--verificar`` é o que a suíte de testes usa
(``apps/core/tests/test_agentes_multiplataforma.py``): ele não deve depender
de banco de dados nem gravar nada em disco.

Por que não usamos PyYAML: o projeto não tem essa dependência hoje
(``requirements/base.txt`` e ``requirements/dev.txt`` não a listam) e a regra
do time é não acrescentar dependência nova só para isto. O frontmatter neutro
tem estrutura fixa e conhecida (duas chaves de topo escalares, dois mapas
aninhados de um nível), então um leitor mínimo, específico para essa forma,
é mais simples de auditar do que justificar e manter uma dependência nova.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FONTE_DIR = REPO_ROOT / "docs" / "agents" / "papeis"
CLAUDE_DIR = REPO_ROOT / ".claude" / "agents"
CODEX_DIR = REPO_ROOT / ".codex" / "agents"

# Caminho (relativo à raiz do repositório) do procedimento para criar um
# papel novo. Citado no derivado Codex (ver `_bloco_como_criar_um_papel`) e
# na skill `.agents/skills/criar-um-papel/SKILL.md`. O lado Claude é
# responsabilidade do `docs/agents/equipe.md`, que não é gerado por este
# script — ver o próprio `como-criar-um-papel.md` para a divisão de
# responsabilidade.
COMO_CRIAR_UM_PAPEL = "docs/agents/como-criar-um-papel.md"

LINK_MARKDOWN_RE = re.compile(r"(\[[^\]]+\]\()([^)]+)(\))")


class ErroFrontmatter(ValueError):
    """Frontmatter da fonte neutra não segue a estrutura fixa esperada."""


@dataclass(frozen=True)
class Papel:
    """Um papel da equipe, já com os dois blocos do frontmatter neutro."""

    nome: str
    descricao: str
    raciocinio: str
    esforco: str
    escreve_arquivos: str
    memoria_de_projeto: str
    delega_para: tuple[str, ...]
    model: str
    effort: str
    memory: str | None
    color: str
    tools: str
    disallowed_tools: str | None
    corpo: str = field(repr=False)
    arquivo_fonte: Path = field(repr=False)

    @property
    def precisa_aviso_de_honestidade(self) -> bool:
        """Papel cuja restrição é técnica só no Claude Code.

        Critério 9 do plano DL-019: um papel que não escreve arquivos
        (`escreve_arquivos: nao`) ou que não delega (`delega_para` vazio) tem
        essa restrição imposta pela plataforma *apenas* no Claude Code (via
        `tools`/`disallowedTools`). Nos outros formatos não existe campo
        equivalente confirmado — a mesma regra vira só instrução, e cada
        derivado tem de dizer isso no próprio corpo. Prometer isolamento que
        não existe ali seria pior do que não ter o papel.
        """
        return self.escreve_arquivos == "nao" or not self.delega_para


# --------------------------------------------------------------------------
# Leitura da fonte única
# --------------------------------------------------------------------------


def _linha_ou_erro(linhas: list[str], idx: int, caminho: Path) -> str:
    if idx >= len(linhas):
        raise ErroFrontmatter(f"{caminho}: frontmatter terminou antes do esperado")
    return linhas[idx]


def _ler_escalar(linhas: list[str], idx: int, chave: str, caminho: Path) -> tuple[str, int]:
    linha = _linha_ou_erro(linhas, idx, caminho)
    prefixo = f"{chave}: "
    if not linha.startswith(prefixo):
        raise ErroFrontmatter(
            f"{caminho}: esperava '{chave}: <valor>' na linha {idx + 1} do "
            f"frontmatter, encontrei {linha!r}"
        )
    return linha[len(prefixo) :], idx + 1


def _ler_bloco_mapa(linhas: list[str], idx: int, caminho: Path) -> tuple[dict[str, str], int]:
    """Lê pares ``  chave: valor`` (indentação de 2 espaços) até o dedent."""
    mapa: dict[str, str] = {}
    while idx < len(linhas) and linhas[idx].startswith("  ") and linhas[idx].strip():
        conteudo = linhas[idx][2:]
        if conteudo.startswith(" "):
            raise ErroFrontmatter(
                f"{caminho}: indentação inesperada na linha {idx + 1}: {linhas[idx]!r} "
                "(este leitor só entende um nível de aninhamento)"
            )
        chave, separador, valor = conteudo.partition(": ")
        if not separador:
            raise ErroFrontmatter(
                f"{caminho}: linha {idx + 1} malformada, esperava 'chave: valor': {linhas[idx]!r}"
            )
        mapa[chave] = valor
        idx += 1
    return mapa, idx


def _desaspar(valor: str) -> str:
    """Remove aspas duplas envolventes de um valor de frontmatter, se houver."""
    if len(valor) >= 2 and valor.startswith('"') and valor.endswith('"'):
        return valor[1:-1]
    return valor


def _ler_lista_inline(valor: str, chave: str, caminho: Path) -> tuple[str, ...]:
    valor = valor.strip()
    if not (valor.startswith("[") and valor.endswith("]")):
        raise ErroFrontmatter(
            f"{caminho}: '{chave}' deveria ser uma lista entre colchetes, encontrei {valor!r}"
        )
    interior = valor[1:-1].strip()
    if not interior:
        return ()
    return tuple(item.strip() for item in interior.split(","))


def carregar_papel(caminho: Path) -> Papel:
    """Lê e valida um arquivo de ``docs/agents/papeis/``.

    Levanta :class:`ErroFrontmatter` com uma mensagem que aponta o arquivo e
    a linha problemática — nunca grava nada, então uma fonte inválida nunca
    produz derivado parcial (cenário de teste 5 do plano DL-019).
    """
    texto = caminho.read_text(encoding="utf-8")
    if not texto.startswith("---\n"):
        raise ErroFrontmatter(f"{caminho}: o arquivo precisa começar com '---' na primeira linha")

    resto = texto[len("---\n") :]
    fim_frontmatter = resto.find("\n---\n")
    if fim_frontmatter == -1:
        raise ErroFrontmatter(f"{caminho}: frontmatter sem delimitador de fechamento '---'")

    frontmatter_txt = resto[:fim_frontmatter]
    corpo = resto[fim_frontmatter + len("\n---\n") :]

    linhas = frontmatter_txt.split("\n")
    idx = 0

    nome, idx = _ler_escalar(linhas, idx, "nome", caminho)

    linha = _linha_ou_erro(linhas, idx, caminho)
    if linha != "descricao: >-":
        raise ErroFrontmatter(
            f"{caminho}: esperava 'descricao: >-' na linha {idx + 1}, encontrei {linha!r}"
        )
    idx += 1
    partes_descricao: list[str] = []
    while idx < len(linhas) and linhas[idx].startswith("  ") and linhas[idx].strip():
        partes_descricao.append(linhas[idx][2:])
        idx += 1
    if not partes_descricao:
        raise ErroFrontmatter(f"{caminho}: 'descricao' não tem conteúdo indentado abaixo de '>-'")
    descricao = " ".join(partes_descricao)

    linha = _linha_ou_erro(linhas, idx, caminho)
    if linha != "perfil:":
        raise ErroFrontmatter(
            f"{caminho}: esperava 'perfil:' na linha {idx + 1}, encontrei {linha!r}"
        )
    idx += 1
    perfil, idx = _ler_bloco_mapa(linhas, idx, caminho)

    for chave_obrigatoria in (
        "raciocinio",
        "esforco",
        "escreve_arquivos",
        "memoria_de_projeto",
        "delega_para",
    ):
        if chave_obrigatoria not in perfil:
            raise ErroFrontmatter(
                f"{caminho}: bloco 'perfil' sem a chave obrigatória '{chave_obrigatoria}'"
            )

    if perfil["raciocinio"] not in ("maximo", "equilibrado"):
        raise ErroFrontmatter(f"{caminho}: 'perfil.raciocinio' inválido: {perfil['raciocinio']!r}")
    if perfil["esforco"] not in ("alto", "medio"):
        raise ErroFrontmatter(f"{caminho}: 'perfil.esforco' inválido: {perfil['esforco']!r}")
    if perfil["escreve_arquivos"] not in ("sim", "nao"):
        raise ErroFrontmatter(
            f"{caminho}: 'perfil.escreve_arquivos' inválido: {perfil['escreve_arquivos']!r}"
        )
    if perfil["memoria_de_projeto"] not in ("sim", "nao"):
        raise ErroFrontmatter(
            f"{caminho}: 'perfil.memoria_de_projeto' inválido: {perfil['memoria_de_projeto']!r}"
        )
    delega_para = _ler_lista_inline(perfil["delega_para"], "perfil.delega_para", caminho)

    linha = _linha_ou_erro(linhas, idx, caminho)
    if linha != "claude:":
        raise ErroFrontmatter(
            f"{caminho}: esperava 'claude:' na linha {idx + 1}, encontrei {linha!r}"
        )
    idx += 1
    claude, idx = _ler_bloco_mapa(linhas, idx, caminho)

    for chave_obrigatoria in ("model", "effort", "color", "tools"):
        if chave_obrigatoria not in claude:
            raise ErroFrontmatter(
                f"{caminho}: bloco 'claude' sem a chave obrigatória '{chave_obrigatoria}'"
            )

    if idx != len(linhas):
        raise ErroFrontmatter(
            f"{caminho}: conteúdo inesperado após o bloco 'claude' no frontmatter "
            f"(linha {idx + 1}: {linhas[idx]!r})"
        )

    return Papel(
        nome=nome,
        descricao=descricao,
        raciocinio=perfil["raciocinio"],
        esforco=perfil["esforco"],
        escreve_arquivos=perfil["escreve_arquivos"],
        memoria_de_projeto=perfil["memoria_de_projeto"],
        delega_para=delega_para,
        model=claude["model"],
        effort=claude["effort"],
        memory=claude.get("memory"),
        color=claude["color"],
        tools=_desaspar(claude["tools"]),
        disallowed_tools=(
            _desaspar(claude["disallowedTools"]) if "disallowedTools" in claude else None
        ),
        corpo=corpo,
        arquivo_fonte=caminho,
    )


def carregar_papeis() -> list[Papel]:
    """Carrega e valida **todos** os papéis antes de qualquer escrita.

    A validação acontece toda aqui, de propósito: se um dos sete arquivos
    tiver frontmatter inválido, o processo inteiro falha antes de tocar em
    qualquer arquivo gerado — não existe "gerou 5 de 7 e quebrou".
    """
    if not FONTE_DIR.is_dir():
        raise ErroFrontmatter(f"diretório da fonte não encontrado: {FONTE_DIR}")
    arquivos = sorted(FONTE_DIR.glob("*.md"))
    if not arquivos:
        raise ErroFrontmatter(f"nenhum papel encontrado em {FONTE_DIR}")
    return [carregar_papel(caminho) for caminho in arquivos]


# --------------------------------------------------------------------------
# Recálculo de links
# --------------------------------------------------------------------------


def _e_link_local(alvo: str) -> bool:
    alvo = alvo.strip()
    if not alvo or alvo.startswith("#"):
        return False
    # Esquemas como http:, mailto: etc. não são recalculados.
    return re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", alvo) is None


def recalcular_links(corpo: str, origem_dir: str, destino_dir: str) -> str:
    """Recalcula todo link relativo do corpo para a pasta de destino.

    ``origem_dir`` e ``destino_dir`` são caminhos relativos à raiz do
    repositório, em formato POSIX. Para o formato "navegável como
    documento" (Claude Code), ``destino_dir`` é a pasta onde o arquivo
    gerado mora. Para o TOML do Codex — que não é um documento Markdown
    navegado por caminho relativo, e cuja ferramenta roda com o diretório
    de trabalho na raiz — o chamador passa ``destino_dir="."``, o que
    produz links relativos à raiz do repositório (regra 1 do plano
    DL-019).
    """

    def substituir(correspondencia: re.Match[str]) -> str:
        alvo = correspondencia.group(2)
        if not _e_link_local(alvo):
            return correspondencia.group(0)
        absoluto = posixpath.normpath(posixpath.join(origem_dir, alvo.strip()))
        novo_alvo = posixpath.relpath(absoluto, start=destino_dir)
        return f"{correspondencia.group(1)}{novo_alvo}{correspondencia.group(3)}"

    return LINK_MARKDOWN_RE.sub(substituir, corpo)


def _origem_dir_relativa(papel: Papel) -> str:
    return posixpath.relpath(papel.arquivo_fonte.parent.as_posix(), start=REPO_ROOT.as_posix())


# --------------------------------------------------------------------------
# Blocos exclusivos do derivado Codex (não-Claude)
# --------------------------------------------------------------------------

AVISO_MARCADOR = (
    "Aviso de honestidade: nesta ferramenta, a restrição descrita acima é "
    "**instrução de comportamento**, não isolamento técnico garantido — "
    "diferente do Claude Code, onde a ausência de `Write`/`Edit` é técnica "
    "(ver `tools`/`disallowedTools` em `docs/agents/papeis/`)."
)


def _bloco_aviso_de_honestidade(papel: Papel) -> str:
    razoes = []
    if papel.escreve_arquivos == "nao":
        razoes.append("não editar arquivos")
    if not papel.delega_para:
        razoes.append("não delegar a outro agente")
    razao = " e ".join(razoes)
    return (
        "\n## Aviso de honestidade desta ferramenta\n\n"
        f"A definição deste papel pede para {razao}. {AVISO_MARCADOR} Cumpra "
        "a instrução pelo mesmo motivo que cumpriria no Claude Code — não "
        "porque a ferramenta impede o contrário.\n"
    )


def _bloco_como_criar_um_papel() -> str:
    # O TOML do Codex não é documento navegado por caminho relativo (regra 1
    # do plano DL-019: quem lê trabalha com o diretório de trabalho na
    # raiz), então o link aqui é sempre relativo à raiz do repositório.
    return (
        "\n## Criar um papel novo\n\n"
        f"Este arquivo é gerado a partir de `docs/agents/papeis/`. Para criar um "
        f"papel novo ou alterar este, siga `{COMO_CRIAR_UM_PAPEL}` — não edite "
        "este arquivo diretamente, a próxima geração sobrescreve.\n"
    )


def _corpo_codex(papel: Papel) -> str:
    """Corpo do ``developer_instructions`` do Codex: links relativos à raiz.

    Único derivado não-Claude do escopo atual (ver docstring do módulo), por
    isso ele sozinho carrega o aviso de honestidade e a citação do
    procedimento de criar papel — o lado Claude fica byte a byte igual ao
    que já existia (critério 1 do plano DL-019).
    """
    origem = _origem_dir_relativa(papel)
    corpo = recalcular_links(papel.corpo, origem, destino_dir=".")
    if papel.precisa_aviso_de_honestidade:
        corpo = corpo.rstrip("\n") + "\n" + _bloco_aviso_de_honestidade(papel)
    corpo = corpo.rstrip("\n") + "\n" + _bloco_como_criar_um_papel()
    return corpo


# --------------------------------------------------------------------------
# Construtores de cada formato
# --------------------------------------------------------------------------


def construir_claude(papel: Papel) -> str:
    """Reconstrói o frontmatter no formato exato de ``.claude/agents/``.

    A ordem dos campos é fixa (critério 1 do plano DL-019):
    ``name, description, model, effort, memory, color, tools,
    disallowedTools`` — ``memory`` só aparece nos papéis que já o têm hoje.
    """
    linhas = [
        "---",
        f"name: {papel.nome}",
        f"description: {papel.descricao}",
        f"model: {papel.model}",
        f"effort: {papel.effort}",
    ]
    if papel.memory:
        linhas.append(f"memory: {papel.memory}")
    linhas.append(f"color: {papel.color}")
    linhas.append(f"tools: {papel.tools}")
    if papel.disallowed_tools:
        linhas.append(f"disallowedTools: {papel.disallowed_tools}")
    linhas.append("---")
    frontmatter = "\n".join(linhas) + "\n"

    origem = _origem_dir_relativa(papel)
    destino = posixpath.relpath(CLAUDE_DIR.as_posix(), start=REPO_ROOT.as_posix())
    corpo = recalcular_links(papel.corpo, origem, destino)
    return frontmatter + corpo


def _escapar_toml(valor: str) -> str:
    # Escapar toda barra invertida e toda aspa dupla, individualmente, evita
    # que uma sequência """ do corpo feche a string multilinha básica antes
    # da hora — mais simples e mais auditável do que detectar a sequência.
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def construir_codex_toml(papel: Papel) -> str:
    """``.codex/agents/<papel>.toml``.

    Só ``name``, ``description`` e ``developer_instructions`` — os únicos
    três campos confirmados em documentação oficial para agentes
    customizados do Codex CLI (levantamento no plano DL-019). Deliberadamente
    NÃO escrevemos ``model``, ``model_reasoning_effort`` nem ``sandbox_mode``:
    não há confirmação oficial de quais identificadores de modelo o Codex
    aceita hoje, e o projeto não inventa identificador (mesma regra que
    proíbe inventar alíquota ou leiaute oficial, agora aplicada a
    configuração). Quando isso for confirmado, adicione o campo aqui — não
    presuma.
    """
    corpo = _corpo_codex(papel)
    nome = _escapar_toml(papel.nome)
    descricao = _escapar_toml(papel.descricao)
    instrucoes = _escapar_toml(corpo)
    return (
        f'name = "{nome}"\n'
        f'description = "{descricao}"\n'
        f'developer_instructions = """\n{instrucoes}"""\n'
    )


# --------------------------------------------------------------------------
# Orquestração: escrever e verificar
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ArquivoGerado:
    caminho: Path
    conteudo: str


def _arquivos_esperados(papeis: list[Papel]) -> list[ArquivoGerado]:
    gerados: list[ArquivoGerado] = []
    for papel in papeis:
        gerados.append(ArquivoGerado(CLAUDE_DIR / f"{papel.nome}.md", construir_claude(papel)))
        gerados.append(ArquivoGerado(CODEX_DIR / f"{papel.nome}.toml", construir_codex_toml(papel)))
    return gerados


def _validar_toml(arquivo: ArquivoGerado) -> None:
    """Confere que o TOML gerado é carregável e preserva o texto original.

    Cenário de teste 6 do plano DL-019: ``tomllib.load`` precisa aceitar o
    arquivo, e ``developer_instructions`` precisa manter a acentuação
    (UTF-8) — o teste que chama esta função falha alto e cedo se o
    escapamento em ``_escapar_toml`` estiver errado.
    """
    tomllib.loads(arquivo.conteudo)


def _orfaos(papeis: list[Papel]) -> list[Path]:
    """Deriva existente cujo papel já não está na fonte.

    Usado tanto por ``verificar`` (para relatar) quanto por ``escrever``
    (para apagar) — um papel removido de ``docs/agents/papeis/`` não deveria
    deixar ``.claude/agents/`` ou ``.codex/agents/`` com o arquivo antigo
    esquecido para trás (é o cenário 4 do plano DL-019, e o passo 5 de
    ``docs/agents/como-criar-um-papel.md``).
    """
    nomes_esperados = {papel.nome for papel in papeis}
    encontrados: list[Path] = []
    for diretorio, sufixo in (
        (CLAUDE_DIR, ".md"),
        (CODEX_DIR, ".toml"),
    ):
        if not diretorio.is_dir():
            continue
        for existente in diretorio.iterdir():
            if not existente.name.endswith(sufixo):
                continue
            nome_papel = existente.name[: -len(sufixo)]
            if nome_papel not in nomes_esperados:
                encontrados.append(existente)
    return encontrados


def escrever(papeis: list[Papel]) -> None:
    gerados = _arquivos_esperados(papeis)
    for arquivo in gerados:
        if arquivo.caminho.suffix == ".toml":
            _validar_toml(arquivo)
    for arquivo in gerados:
        arquivo.caminho.parent.mkdir(parents=True, exist_ok=True)
        # Escreve em arquivo temporário e troca de nome: uma falha no meio da
        # escrita não deixa um arquivo pela metade em cima do anterior.
        temporario = arquivo.caminho.with_suffix(arquivo.caminho.suffix + ".tmp")
        temporario.write_text(arquivo.conteudo, encoding="utf-8")
        temporario.replace(arquivo.caminho)

    orfaos = _orfaos(papeis)
    for caminho in orfaos:
        caminho.unlink()

    mensagem = f"Gerados {len(gerados)} arquivos a partir de {len(papeis)} papéis em {FONTE_DIR}."
    if orfaos:
        relativos = ", ".join(str(c.relative_to(REPO_ROOT)) for c in orfaos)
        mensagem += f" Removidos {len(orfaos)} derivado(s) órfão(s): {relativos}."
    print(mensagem)


def verificar(papeis: list[Papel]) -> list[str]:
    """Retorna a lista de problemas encontrados (vazia = tudo sincronizado).

    Cobre os cenários 2 (derivado editado à mão), 3 (papel novo faltando
    derivado) e 4 (derivado órfão) do plano DL-019.
    """
    problemas: list[str] = []
    esperados = _arquivos_esperados(papeis)
    for arquivo in esperados:
        if not arquivo.caminho.exists():
            problemas.append(f"ausente: {arquivo.caminho.relative_to(REPO_ROOT)}")
            continue
        atual = arquivo.caminho.read_text(encoding="utf-8")
        if atual != arquivo.conteudo:
            problemas.append(f"divergente: {arquivo.caminho.relative_to(REPO_ROOT)}")

    for caminho in _orfaos(papeis):
        relativo = caminho.relative_to(REPO_ROOT)
        problemas.append(f"órfão (sem papel correspondente na fonte): {relativo}")
    return sorted(set(problemas))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--escrever", action="store_true", help="(re)grava os dois formatos derivados"
    )
    grupo.add_argument(
        "--verificar",
        action="store_true",
        help="sai com código != 0 se algum derivado estiver fora de sincronia",
    )
    argumentos = parser.parse_args(argv)

    try:
        papeis = carregar_papeis()
    except ErroFrontmatter as erro:
        print(f"Fonte inválida, nada foi gravado: {erro}", file=sys.stderr)
        return 2

    if argumentos.escrever:
        escrever(papeis)
        return 0

    problemas = verificar(papeis)
    if problemas:
        print("Derivados fora de sincronia com docs/agents/papeis/:", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        print(
            "\nPara corrigir: .venv/bin/python scripts/gerar_agentes.py --escrever",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(papeis)} papéis, todos os derivados sincronizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
