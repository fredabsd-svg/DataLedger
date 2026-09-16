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

Toda função pública abaixo que precisa saber "onde fica o repositório" recebe
um :class:`Diretorios` explícito, com um valor padrão que aponta para a raiz
real (calculada a partir deste arquivo). Isso existe por um motivo concreto,
não estético: achado do arquiteto-senior revisando esta etapa — os testes que
reproduzem os cenários de "derivado editado à mão" e "papel removido"
escreviam e apagavam arquivos rastreados de verdade, confiando em um bloco
``finally`` para desfazer. ``finally`` não roda sob ``SIGKILL``/OOM/timeout de
CI, e o ambiente de desenvolvimento é efêmero — um estado corrompido no meio
de um teste podia ser commitado por outro processo sem ninguém perceber.
Threading explícito de :class:`Diretorios` é o que permite aos testes operar
sobre uma cópia isolada em ``tmp_path`` sem duplicar toda a lógica do
gerador.

Por que não usamos PyYAML: o projeto não tem essa dependência hoje
(``requirements/base.txt`` e ``requirements/dev.txt`` não a listam) e a regra
do time é não acrescentar dependência nova só para isto. O frontmatter neutro
tem estrutura fixa e conhecida (duas chaves de topo escalares, dois mapas
aninhados de um nível), então um leitor mínimo, específico para essa forma,
é mais simples de auditar do que justificar e manter uma dependência nova.

Correções da auditoria DL-019, rodada 1 (2026-09-15, REPROVADO — 12 achados,
11 sob responsabilidade do `desenvolvedor-pleno`): este arquivo incorpora as
correções dos achados 1, 2, 3, 6, 7, 8, 9 e 10. Os achados 5, 11 e 12 vivem
no teste (`apps/core/tests/test_agentes_multiplataforma.py`). Cada correção
está comentada no ponto onde vive, citando o achado.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Diretorios:
    """Onde ficam a fonte e os dois derivados, relativos a uma raiz.

    A raiz normalmente é a raiz real do repositório (:data:`REPO_ROOT`), mas
    os testes constroem uma instância apontando para uma cópia isolada em
    ``tmp_path`` — nunca para o repositório de verdade — quando precisam de
    um cenário que grava ou apaga um derivado.
    """

    raiz: Path
    fonte: Path
    claude: Path
    codex: Path

    @classmethod
    def para_raiz(cls, raiz: Path) -> Diretorios:
        return cls(
            raiz=raiz,
            fonte=raiz / "docs" / "agents" / "papeis",
            claude=raiz / ".claude" / "agents",
            codex=raiz / ".codex" / "agents",
        )


REPO_ROOT = Path(__file__).resolve().parents[1]
DIRETORIOS_REPO = Diretorios.para_raiz(REPO_ROOT)

# Caminho (relativo à raiz do repositório) do procedimento para criar um
# papel novo. Citado no derivado Codex (ver `_bloco_como_criar_um_papel`) e
# na skill `.agents/skills/criar-um-papel/SKILL.md`. O lado Claude é
# responsabilidade do `docs/agents/equipe.md`, que não é gerado por este
# script — ver o próprio `como-criar-um-papel.md` para a divisão de
# responsabilidade. É só texto inserido no corpo gerado, não um caminho que
# este script abre — por isso não faz parte de `Diretorios`.
COMO_CRIAR_UM_PAPEL = "docs/agents/como-criar-um-papel.md"

# Achado 3 (auditoria DL-019 rodada 1): a correção anterior do órfão (que
# resolveu um resíduo real) abriu uma remoção destrutiva — `--escrever`
# apagava qualquer `.md`/`.toml` que não fosse gerado, incluindo um agente
# local que ninguém pediu para remover. A partir de agora, só um arquivo que
# CARREGA esta marca (ou seja, que este próprio gerador escreveu antes) pode
# ser apagado automaticamente. O Codex já carrega a marca no corpo (ver
# `_bloco_como_criar_um_papel`); o Claude Code não tem onde colocá-la sem
# quebrar o critério 1 (byte a byte) — por isso `.claude/agents/*.md` nunca é
# apagado sozinho, só relatado como órfão. `verificar()` continua relatando
# os dois tipos; só a remoção automática de `escrever()` ficou restrita.
MARCA_DE_GERADO = "Este arquivo é gerado a partir de `docs/agents/papeis/`."


def marca_de_gerado(nome_do_papel: str) -> str:
    """Marca que autoriza remoção automática, citando o papel de origem.

    Achado A9.1 (BL-182): a marca genérica viajava junto numa cópia
    (`cp auditor-qa.toml meu-agente-pessoal.toml`) e fazia o gerador apagar
    o arquivo pessoal de quem copiou. Citando o papel, a cópia deixa de
    corresponder ao próprio nome e é preservada — sem manifesto e sem
    estado novo para manter em dia.
    """
    return f"{MARCA_DE_GERADO[:-1]} (papel `{nome_do_papel}`)."


LINK_MARKDOWN_RE = re.compile(r"(\[[^\]]+\]\()([^)]+)(\))")

# Achado 2 (auditoria DL-019 rodada 1, alta): `nome` sem validação permitia
# travessia de caminho — `nome: ../../../ESCAPOU` fazia `escrever()` gravar
# fora dos diretórios de destino. `docs/agents/como-criar-um-papel.md`
# convida qualquer ferramenta de IA a criar um arquivo em
# `docs/agents/papeis/` e rodar `--escrever`; um `nome` malformado não podia
# continuar sendo um caminho de escrita arbitrária a partir de dado de
# repositório.
_NOME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Achado 8 (auditoria DL-019 rodada 1, baixa): chave desconhecida em
# `perfil`/`claude` era descartada em silêncio — um papel novo que
# acrescentasse `sandbox_mode` (citado em docs/agents/equipe.md como
# possibilidade futura) acreditava ter configurado algo que não existe em
# lugar nenhum.
_CHAVES_PERFIL = frozenset(
    {"raciocinio", "esforco", "escreve_arquivos", "memoria_de_projeto", "delega_para"}
)
_CHAVES_CLAUDE = frozenset({"model", "effort", "memory", "color", "tools", "disallowedTools"})

# Achado 7 (auditoria DL-019 rodada 1, baixa): caractere de controle no corpo
# derrubava `--escrever` com um `tomllib.TOMLDecodeError` bruto, sem citar o
# arquivo-fonte — contrariando a promessa do próprio procedimento publicado
# ("o gerador falha com uma mensagem que aponta o arquivo e a linha"). Lista
# dos controles que o TOML não aceita em string básica (tab e LF ficam de
# fora, são válidos).
_CONTROLE_PROIBIDO_TOML = frozenset(
    chr(codigo) for codigo in (*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20), 0x7F)
)


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


def _tokens_de_ferramentas(valor: str | None) -> set[str]:
    """Extrai os nomes de ferramenta de um campo `tools`/`disallowedTools`.

    Remove qualquer conteúdo entre parênteses primeiro — `arquiteto-senior`
    declara `Agent(desenvolvedor-pleno, especialista-frontend, ...)`, e os
    nomes de papel dentro dos parênteses não são ferramentas.
    """
    if not valor:
        return set()
    sem_parenteses = re.sub(r"\([^)]*\)", "", valor)
    return {token.strip() for token in sem_parenteses.split(",") if token.strip()}


def _validar_sem_controle_proibido(texto: str, caminho: Path) -> None:
    """Achado 7: recusa cedo, citando arquivo e linha, em vez de deixar o
    caractere chegar ao `tomllib` e explodir num traceback sem contexto."""
    for indice, caractere in enumerate(texto):
        if caractere in _CONTROLE_PROIBIDO_TOML:
            linha = texto.count("\n", 0, indice) + 1
            raise ErroFrontmatter(
                f"{caminho}: contém caractere de controle proibido "
                f"U+{ord(caractere):04X} na linha {linha} — provavelmente colado "
                "de um PDF ou terminal; remova-o antes de gerar"
            )


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


def _validar_coerencia(papel: Papel) -> None:
    """Achado 6 (auditoria DL-019 rodada 1, média): nada impedia `perfil`
    (neutro) e `claude` (ferramentas concedidas de verdade) de se
    contradizerem. Era possível acrescentar `Write` ao `tools` do
    `auditor-qa` mantendo `escreve_arquivos: nao`, com os 18 testes daquela
    rodada passando e os dois derivados continuando a *afirmar* que ele não
    escreve. Essa é a única restrição que é mecanismo de verdade neste
    projeto (ausência de `Write`/`Edit` no Claude Code); ela precisa de
    coerência verificada, não só declarada.
    """
    caminho = papel.arquivo_fonte
    concedidas = _tokens_de_ferramentas(papel.tools)
    proibidas = _tokens_de_ferramentas(papel.disallowed_tools)

    if papel.escreve_arquivos == "nao":
        escrita_concedida = concedidas & {"Write", "Edit", "NotebookEdit"}
        if escrita_concedida:
            raise ErroFrontmatter(
                f"{caminho}: perfil.escreve_arquivos=nao, mas claude.tools concede "
                f"{sorted(escrita_concedida)} — perfil e claude estão em desacordo"
            )
        escrita_nao_proibida = {"Write", "Edit", "NotebookEdit"} - proibidas
        if escrita_nao_proibida:
            raise ErroFrontmatter(
                f"{caminho}: perfil.escreve_arquivos=nao exige claude.disallowedTools "
                f"com Write, Edit e NotebookEdit; falta {sorted(escrita_nao_proibida)}"
            )

    # Achado A6 (BL-179): a validação acima cobria só a direção RESTRITIVA —
    # "o perfil diz que não pode, o claude concede". Faltava a simétrica: o
    # perfil declara uma capacidade que o Claude Code nega. Nesse caso os dois
    # derivados prometem ao modelo algo que ele não tem, e nem sequer ganham o
    # aviso de honestidade, porque o aviso só liga quando a restrição é
    # *declarada*. Era a direção que o achado A2 mostrou viva no repositório.
    if papel.escreve_arquivos == "sim":
        escrita_faltante = {"Write", "Edit"} - concedidas
        if escrita_faltante:
            raise ErroFrontmatter(
                f"{caminho}: perfil.escreve_arquivos=sim, mas claude.tools não concede "
                f"{sorted(escrita_faltante)} — o papel promete uma capacidade que a "
                "ferramenta nega"
            )
        escrita_proibida = {"Write", "Edit", "NotebookEdit"} & proibidas
        if escrita_proibida:
            raise ErroFrontmatter(
                f"{caminho}: perfil.escreve_arquivos=sim, mas claude.disallowedTools "
                f"proíbe {sorted(escrita_proibida)} — perfil e claude estão em desacordo"
            )

    if not papel.delega_para:
        if "Agent" in concedidas:
            raise ErroFrontmatter(
                f"{caminho}: perfil.delega_para vazio, mas claude.tools concede Agent"
            )
        if "Agent" not in proibidas:
            raise ErroFrontmatter(
                f"{caminho}: perfil.delega_para vazio exige claude.disallowedTools com Agent"
            )
    else:
        # Mesma simetria do bloco de escrita, para delegação.
        if "Agent" not in concedidas:
            raise ErroFrontmatter(
                f"{caminho}: perfil.delega_para lista {list(papel.delega_para)}, mas "
                "claude.tools não concede Agent — o papel promete delegação que a "
                "ferramenta nega"
            )
        if "Agent" in proibidas:
            raise ErroFrontmatter(
                f"{caminho}: perfil.delega_para não é vazio, mas claude.disallowedTools "
                "proíbe Agent — perfil e claude estão em desacordo"
            )

    memoria_no_perfil = papel.memoria_de_projeto == "sim"
    memoria_no_claude = papel.memory == "project"
    if memoria_no_perfil != memoria_no_claude:
        raise ErroFrontmatter(
            f"{caminho}: perfil.memoria_de_projeto={papel.memoria_de_projeto!r} não "
            f"bate com claude.memory={papel.memory!r} — os dois precisam concordar"
        )


def carregar_papel(caminho: Path) -> Papel:
    """Lê e valida um arquivo de ``docs/agents/papeis/``.

    Levanta :class:`ErroFrontmatter` com uma mensagem que aponta o arquivo e
    a linha problemática — nunca grava nada, então uma fonte inválida nunca
    produz derivado parcial (cenário de teste 5 do plano DL-019).
    """
    # Achado 9 (auditoria DL-019 rodada 1): a correção recomendada tinha duas
    # partes — comparar bytes em `verificar()` (feito, ver lá) e ler a fonte
    # com `newline=""` para não normalizar quebra de linha antes de gerar.
    # Discordo dessa segunda parte, por escrito: `read_text()` com quebra de
    # linha universal (padrão) converte CRLF/CR para LF UMA VEZ, na leitura
    # da fonte, o que é o comportamento que queremos — saída sempre LF,
    # independente de como a fonte foi salva. Ler com `newline=""`
    # preservaria um CRLF acidental da fonte e o propagaria para dentro do
    # derivado gerado, que é o problema oposto ao que motivou o achado. O
    # ponto cego de verdade era a COMPARAÇÃO em `verificar()` usar texto
    # normalizado em vez de bytes — isso está corrigido abaixo.
    texto = caminho.read_text(encoding="utf-8")
    _validar_sem_controle_proibido(texto, caminho)

    if not texto.startswith("---\n"):
        raise ErroFrontmatter(f"{caminho}: o arquivo precisa começar com '---' na primeira linha")

    resto = texto[len("---\n") :]
    fim_frontmatter = resto.find("\n---\n")
    if fim_frontmatter == -1:
        raise ErroFrontmatter(f"{caminho}: frontmatter sem delimitador de fechamento '---'")

    frontmatter_txt = resto[:fim_frontmatter]
    corpo = resto[fim_frontmatter + len("\n---\n") :]

    # Achado A1: valida o marcador aqui, junto da leitura, para que fonte
    # malformada nunca chegue a gerar arquivo. A linha reportada é a do
    # arquivo, contando o frontmatter que ficou para trás.
    _validar_marcadores_de_mecanismo(
        corpo, caminho, texto.count("\n", 0, len(texto) - len(corpo)) + 1
    )

    linhas = frontmatter_txt.split("\n")
    idx = 0

    nome, idx = _ler_escalar(linhas, idx, "nome", caminho)

    # Achado 2: valida ANTES de qualquer outro processamento, porque é o
    # valor usado depois para montar caminho de arquivo de saída.
    if not _NOME_RE.fullmatch(nome):
        raise ErroFrontmatter(
            f"{caminho}: 'nome' inválido {nome!r} — só letras minúsculas, dígitos "
            "e hífen simples entre grupos (regex "
            f"{_NOME_RE.pattern!r}); isso existe para impedir travessia de "
            "caminho quando o gerador grava os derivados"
        )
    if nome != caminho.stem:
        raise ErroFrontmatter(
            f"{caminho}: 'nome' ({nome!r}) precisa ser igual ao nome do arquivo "
            f"sem extensão ({caminho.stem!r}) — nomes divergentes escondem qual "
            "papel está sendo editado e quebram a correspondência 1-para-1 "
            "usada para detectar órfão"
        )

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
    desconhecidas = set(perfil) - _CHAVES_PERFIL
    if desconhecidas:
        raise ErroFrontmatter(
            f"{caminho}: bloco 'perfil' tem chave desconhecida {sorted(desconhecidas)}; "
            f"as aceitas são {sorted(_CHAVES_PERFIL)}"
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
    desconhecidas = set(claude) - _CHAVES_CLAUDE
    if desconhecidas:
        raise ErroFrontmatter(
            f"{caminho}: bloco 'claude' tem chave desconhecida {sorted(desconhecidas)}; "
            f"as aceitas são {sorted(_CHAVES_CLAUDE)}"
        )

    if idx != len(linhas):
        raise ErroFrontmatter(
            f"{caminho}: conteúdo inesperado após o bloco 'claude' no frontmatter "
            f"(linha {idx + 1}: {linhas[idx]!r})"
        )

    papel = Papel(
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
    _validar_coerencia(papel)
    return papel


def carregar_papeis(diretorios: Diretorios = DIRETORIOS_REPO) -> list[Papel]:
    """Carrega e valida **todos** os papéis antes de qualquer escrita.

    A validação acontece toda aqui, de propósito: se um dos sete arquivos
    tiver frontmatter inválido, o processo inteiro falha antes de tocar em
    qualquer arquivo gerado — não existe "gerou 5 de 7 e quebrou".
    """
    if not diretorios.fonte.is_dir():
        raise ErroFrontmatter(f"diretório da fonte não encontrado: {diretorios.fonte}")
    arquivos = sorted(diretorios.fonte.glob("*.md"))
    if not arquivos:
        raise ErroFrontmatter(f"nenhum papel encontrado em {diretorios.fonte}")
    papeis = [carregar_papel(caminho) for caminho in arquivos]

    # Achado 6 (parte cruzada): `delega_para` citando um papel que não existe
    # na fonte só é detectável depois que TODOS os papéis foram carregados.
    nomes = {papel.nome for papel in papeis}
    for papel in papeis:
        desconhecidos = [d for d in papel.delega_para if d not in nomes]
        if desconhecidos:
            raise ErroFrontmatter(
                f"{papel.arquivo_fonte}: perfil.delega_para cita papel inexistente "
                f"na fonte: {desconhecidos}"
            )
    return papeis


# --------------------------------------------------------------------------
# Achado 1 — resolução do marcador {{MECANISMO}}
# --------------------------------------------------------------------------
#
# Seis frases do corpo afirmavam, em texto categórico, que uma restrição era
# "técnica" — verdade só no Claude Code. No Codex, que também lê o mesmo
# corpo, a afirmação é falsa: o agente tem a ferramenta. O aviso de
# honestidade sozinho não bastava (ficava ~5 KB abaixo, como ressalva
# genérica, sem retificar a frase específica).
#
# Correção: a fonte guarda as duas versões lado a lado, dentro de um bloco
# ``{{MECANISMO}}...{{/MECANISMO}}``, e o gerador escolhe uma delas por
# destino. Isso preserva o critério 1 (a versão ``CLAUDE:`` é o texto
# histórico exato, byte a byte) e remove a afirmação falsa do lado Codex sem
# inferir automaticamente uma reformulação — cada frase foi escrita à mão
# para o destino que a lê, o que evita o risco de uma transformação genérica
# produzir texto estranho ou ambíguo em algum papel.
# Achado A1 (auditoria DL-019 rodada 2, BL-174): a primeira versão deste
# padrão usava `.*?` com `re.DOTALL` nos dois grupos. Não-guloso não impede
# atravessar bloco: num corpo com DOIS blocos em que o primeiro não tinha
# `CODEX:`, o casamento ia da abertura do bloco A até o `{{/MECANISMO}}` do
# bloco B e **engolia tudo entre eles** — uma regra inteira do papel sumiu do
# derivado Codex, em silêncio, com todos os guardas verdes.
#
# `(?:(?!\{\{/?MECANISMO\}\}).)*?` lê "qualquer caractere, desde que aqui não
# comece um marcador": o grupo não consegue mais passar por cima de uma
# abertura ou de um fechamento. Bloco malformado deixa de casar — e, como
# tudo que não casa é recusado por `_validar_marcadores_de_mecanismo`, ele
# falha alto em vez de calado.
_MECANISMO_RE = re.compile(
    r"\{\{MECANISMO\}\}\nCLAUDE:\n(?P<claude>(?:(?!\{\{/?MECANISMO\}\}).)*?)"
    r"\nCODEX:\n(?P<codex>(?:(?!\{\{/?MECANISMO\}\}).)*?)\n\{\{/MECANISMO\}\}",
    re.DOTALL,
)

# Qualquer grafia aproximada do marcador. Serve para detectar o que o padrão
# acima NÃO casou: espaço dentro das chaves, minúsculas, falta de `CLAUDE:`
# ou de `CODEX:`, fechamento ausente. Tudo isso antes vazava literal para
# dentro do derivado, e o modelo lia `{{/MECANISMO}}` como se fosse regra.
_MARCADOR_RESIDUAL_RE = re.compile(r"\{\{\s*/?\s*MECANISMO", re.IGNORECASE)

# Linha que contém só `CLAUDE:` ou só `CODEX:`. Fora de um bloco bem formado,
# é quase sempre um bloco que perdeu a abertura ou o fechamento — recusar é
# melhor que gerar dois derivados silenciosamente diferentes do pretendido.
_ROTULO_SOLTO_RE = re.compile(r"(?m)^(?:CLAUDE|CODEX):[ \t]*$")


def _validar_marcadores_de_mecanismo(corpo: str, caminho: Path, linha_base: int) -> None:
    """Recusa marcador malformado, citando arquivo e linha.

    Existe porque o mecanismo do achado 1 era a única parte da entrega sem
    teste e falhava por **omissão**: sintaxe errada não dava erro, produzia
    derivado errado. ``linha_base`` é a linha do arquivo onde o corpo começa,
    para que a mensagem aponte a linha real e não a posição dentro do corpo.
    """
    blocos = list(_MECANISMO_RE.finditer(corpo))
    intervalos = [(m.start(), m.end()) for m in blocos]

    def dentro_de_bloco(posicao: int) -> bool:
        return any(inicio <= posicao < fim for inicio, fim in intervalos)

    def linha_de(posicao: int) -> int:
        return linha_base + corpo.count("\n", 0, posicao)

    # Achado R3-1 (auditoria rodada 3, ALTA): a validação anterior isentava
    # TODO rótulo que caísse dentro de um bloco casado. Com dois pares
    # `CLAUDE:`/`CODEX:` no mesmo bloco — o erro natural de quem lê "toda
    # afirmação de mecanismo vai dentro de um bloco" e tem duas afirmações a
    # fazer — o bloco casava, o segundo par ficava "dentro" dele e ninguém
    # reclamava. Resultado medido pelo auditor: o derivado do Claude perdia um
    # parágrafo inteiro e o do Codex recebia o rótulo literal MAIS uma frase
    # de mecanismo falsa. Eram os dois modos de falha do achado original,
    # vivos de novo.
    #
    # A lição, e é a razão de esta checagem existir assim: as oito sintaxes
    # recusadas antes eram **a lista de exemplos do auditor**, não a
    # propriedade que ela ilustrava. A propriedade é "cada bloco carrega
    # exatamente um par de rótulos, nesta ordem" — verificá-la fecha a classe
    # inteira, inclusive os casos que ninguém enumerou.
    for bloco in blocos:
        for rotulo in ("claude", "codex"):
            extra = _ROTULO_SOLTO_RE.search(bloco.group(rotulo))
            if extra is None:
                continue
            posicao = bloco.start(rotulo) + extra.start()
            raise ErroFrontmatter(
                f"{caminho}: linha {linha_de(posicao)}: rótulo {extra.group(0)!r} "
                "repetido dentro de um mesmo bloco {{MECANISMO}}. Cada bloco leva "
                "exatamente um `CLAUDE:` e um `CODEX:`, nesta ordem. Se você tem duas "
                "afirmações de mecanismo a fazer, use **dois blocos** consecutivos — "
                "senão o texto entre os rótulos extras some de um derivado e vaza "
                "literal no outro."
            )

    for ocorrencia in _MARCADOR_RESIDUAL_RE.finditer(corpo):
        if dentro_de_bloco(ocorrencia.start()):
            continue
        raise ErroFrontmatter(
            f"{caminho}: linha {linha_de(ocorrencia.start())}: marcador de mecanismo "
            "malformado. A única forma aceita é, exatamente:\n"
            "{{MECANISMO}}\\nCLAUDE:\\n<texto do Claude Code>\\n"
            "CODEX:\\n<texto do Codex>\\n{{/MECANISMO}}\n"
            "Sem espaço dentro das chaves, em maiúsculas, com as duas seções e "
            "com o fechamento. Marcador que não casa exatamente vazaria literal "
            "para dentro do arquivo que o modelo lê."
        )

    for ocorrencia in _ROTULO_SOLTO_RE.finditer(corpo):
        if dentro_de_bloco(ocorrencia.start()):
            continue
        raise ErroFrontmatter(
            f"{caminho}: linha {linha_de(ocorrencia.start())}: rótulo "
            f"{ocorrencia.group(0)!r} fora de um bloco {{{{MECANISMO}}}} bem formado. "
            "Ou o bloco perdeu a abertura/fechamento, ou o rótulo é texto comum — "
            "nos dois casos, escreva-o de outra forma para não confundir com o marcador."
        )


def resolver_mecanismo(corpo: str, alvo: str) -> str:
    """Substitui cada bloco ``{{MECANISMO}}`` pelo texto do ``alvo``.

    ``alvo`` é ``"claude"`` ou ``"codex"``. Note que a substituição usa o
    texto capturado tal como está, sem acrescentar quebra de linha: o ``\\n``
    que já existe depois de ``{{/MECANISMO}}`` no arquivo-fonte faz esse
    papel — é o mesmo ``\\n`` que terminava a frase original antes da
    marcação, preservando parágrafos e linhas em branco ao redor byte a
    byte.
    """
    if alvo not in ("claude", "codex"):
        raise ValueError(f"alvo inválido para resolver_mecanismo: {alvo!r}")

    def substituir(correspondencia: re.Match[str]) -> str:
        return correspondencia.group(alvo)

    return _MECANISMO_RE.sub(substituir, corpo)


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
    repositório (ou da raiz isolada em teste), em formato POSIX. Para o
    formato "navegável como documento" (Claude Code), ``destino_dir`` é a
    pasta onde o arquivo gerado mora. Para o TOML do Codex — que não é um
    documento Markdown navegado por caminho relativo, e cuja ferramenta roda
    com o diretório de trabalho na raiz — o chamador passa
    ``destino_dir="."``, o que produz links relativos à raiz do repositório
    (regra 1 do plano DL-019).
    """

    def substituir(correspondencia: re.Match[str]) -> str:
        alvo = correspondencia.group(2)
        if not _e_link_local(alvo):
            return correspondencia.group(0)
        absoluto = posixpath.normpath(posixpath.join(origem_dir, alvo.strip()))
        novo_alvo = posixpath.relpath(absoluto, start=destino_dir)
        return f"{correspondencia.group(1)}{novo_alvo}{correspondencia.group(3)}"

    return LINK_MARKDOWN_RE.sub(substituir, corpo)


def _origem_dir_relativa(papel: Papel, diretorios: Diretorios) -> str:
    return posixpath.relpath(
        papel.arquivo_fonte.parent.as_posix(), start=diretorios.raiz.as_posix()
    )


# --------------------------------------------------------------------------
# Blocos exclusivos do derivado Codex (não-Claude)
# --------------------------------------------------------------------------


def _bloco_aviso_de_honestidade(papel: Papel) -> str:
    """Achado 1 (parte 2): o texto do aviso era fixo, sempre citando
    `Write`/`Edit`, mesmo quando a restrição real do papel era sobre
    `Agent` (caso do `auxiliar-implementacao`, que só não delega). Agora o
    texto — e a lista de ferramentas citadas — depende da razão real do
    aviso. Também passou a dizer "descrita abaixo": este bloco agora fica no
    TOPO do `developer_instructions` (ver `_corpo_codex`), não mais depois
    do corpo.
    """
    razoes = []
    ferramentas_tecnicas = []
    if papel.escreve_arquivos == "nao":
        razoes.append("não editar arquivos")
        ferramentas_tecnicas.append("`Write`/`Edit`")
    if not papel.delega_para:
        razoes.append("não delegar a outro agente")
        ferramentas_tecnicas.append("`Agent`")
    razao = " e ".join(razoes)
    ferramentas = " e ".join(ferramentas_tecnicas)
    return (
        "## Aviso de honestidade desta ferramenta\n\n"
        f"A definição deste papel pede para {razao}. Aviso de honestidade: "
        "nesta ferramenta, a restrição descrita abaixo é **instrução de "
        "comportamento**, não isolamento técnico garantido — diferente do "
        f"Claude Code, onde a ausência de {ferramentas} é técnica (ver "
        "`tools`/`disallowedTools` em `docs/agents/papeis/`). Cumpra a "
        "instrução pelo mesmo motivo que cumpriria no Claude Code — não "
        "porque a ferramenta impede o contrário."
    )


def _bloco_como_criar_um_papel(nome_do_papel: str) -> str:
    # O TOML do Codex não é documento navegado por caminho relativo (regra 1
    # do plano DL-019: quem lê trabalha com o diretório de trabalho na
    # raiz), então o link aqui é sempre relativo à raiz do repositório.
    #
    # A primeira frase é `MARCA_DE_GERADO`: `_e_arquivo_gerado` procura por
    # ela para decidir se `escrever()` pode apagar este arquivo sozinho
    # quando ele virar órfão (achado 3). Não mude o texto sem atualizar a
    # constante junto.
    # Achado A9.1 (BL-182): a marca era genérica, então `cp auditor-qa.toml
    # meu-agente-pessoal.toml` — o caminho mais natural para criar um agente
    # pessoal do Codex — herdava a marca junto, e o `--escrever` seguinte
    # APAGAVA o arquivo do usuário. Agora a marca cita o papel de origem, e
    # `_e_arquivo_gerado` só autoriza a remoção quando o nome citado bate com
    # o nome do próprio arquivo. Uma cópia continua dizendo que veio de
    # `auditor-qa.md`, não bate com `meu-agente-pessoal`, e é preservada.
    return (
        f"## Criar um papel novo\n\n"
        f"{marca_de_gerado(nome_do_papel)} Para criar um "
        f"papel novo ou alterar este, siga `{COMO_CRIAR_UM_PAPEL}` — não edite "
        "este arquivo diretamente, a próxima geração sobrescreve."
    )


def _corpo_codex(papel: Papel, diretorios: Diretorios) -> str:
    """Corpo do ``developer_instructions`` do Codex: links relativos à raiz.

    Único derivado não-Claude do escopo atual (ver docstring do módulo), por
    isso ele sozinho carrega o aviso de honestidade e a citação do
    procedimento de criar papel — o lado Claude fica byte a byte igual ao
    que já existia (critério 1 do plano DL-019).

    Achado 1 (parte 3): o aviso de honestidade agora vem **antes** do corpo,
    não depois. Quem lê de cima para baixo precisa encontrar a retificação
    antes de chegar a qualquer menção a `Write`/`Agent` no texto do papel —
    ver `test_aviso_de_honestidade_aparece_antes_de_qualquer_mencao_a_ferramenta`.
    """
    origem = _origem_dir_relativa(papel, diretorios)
    corpo = resolver_mecanismo(papel.corpo, "codex")
    corpo = recalcular_links(corpo, origem, destino_dir=".").strip("\n")

    blocos = []
    if papel.precisa_aviso_de_honestidade:
        blocos.append(_bloco_aviso_de_honestidade(papel))
    blocos.append(corpo)
    blocos.append(_bloco_como_criar_um_papel(papel.nome))
    return "\n\n".join(blocos) + "\n"


# --------------------------------------------------------------------------
# Construtores de cada formato
# --------------------------------------------------------------------------


def construir_claude(papel: Papel, diretorios: Diretorios = DIRETORIOS_REPO) -> str:
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

    origem = _origem_dir_relativa(papel, diretorios)
    destino = posixpath.relpath(diretorios.claude.as_posix(), start=diretorios.raiz.as_posix())
    corpo = resolver_mecanismo(papel.corpo, "claude")
    corpo = recalcular_links(corpo, origem, destino)
    return frontmatter + corpo


def _escapar_toml(valor: str) -> str:
    # Escapar toda barra invertida e toda aspa dupla, individualmente, evita
    # que uma sequência """ do corpo feche a string multilinha básica antes
    # da hora — mais simples e mais auditável do que detectar a sequência.
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def construir_codex_toml(papel: Papel, diretorios: Diretorios = DIRETORIOS_REPO) -> str:
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
    corpo = _corpo_codex(papel, diretorios)
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


def _arquivos_esperados(papeis: list[Papel], diretorios: Diretorios) -> list[ArquivoGerado]:
    gerados: list[ArquivoGerado] = []
    for papel in papeis:
        gerados.append(
            ArquivoGerado(
                diretorios.claude / f"{papel.nome}.md", construir_claude(papel, diretorios)
            )
        )
        gerados.append(
            ArquivoGerado(
                diretorios.codex / f"{papel.nome}.toml", construir_codex_toml(papel, diretorios)
            )
        )
    return gerados


def _confinar_no_destino(caminho: Path, diretorio_base: Path) -> None:
    """Achado 2 (defesa em profundidade): mesmo com `nome` validado por
    regex, confirma que o caminho final resolvido continua dentro do
    diretório de destino esperado antes de escrever nele. Duas defesas
    independentes, não uma — se uma falhar por um motivo que não previmos, a
    outra ainda segura.
    """
    resolvido = caminho.resolve()
    base = diretorio_base.resolve()
    if not resolvido.is_relative_to(base):
        raise ErroFrontmatter(
            f"recusando gravar fora do destino esperado: {resolvido} não é descendente de {base}"
        )


def _validar_toml(arquivo: ArquivoGerado) -> None:
    """Confere que o TOML gerado é carregável e preserva o texto original.

    Cenário de teste 6 do plano DL-019: ``tomllib.load`` precisa aceitar o
    arquivo, e ``developer_instructions`` precisa manter a acentuação
    (UTF-8) — o teste que chama esta função falha alto e cedo se o
    escapamento em ``_escapar_toml`` estiver errado.

    Achado 7 (parte 2): se ainda assim o TOML gerado for inválido por algum
    motivo que a validação de caractere de controle não previu, o erro vira
    ``ErroFrontmatter`` citando o arquivo de destino, em vez de um
    ``tomllib.TOMLDecodeError`` bruto sem contexto subindo até o usuário.
    """
    try:
        tomllib.loads(arquivo.conteudo)
    except tomllib.TOMLDecodeError as erro:
        raise ErroFrontmatter(
            f"{arquivo.caminho}: TOML gerado é inválido ({erro}) — isso indica um "
            "bug no gerador, não necessariamente na fonte; nada foi gravado"
        ) from erro


def _e_arquivo_gerado(caminho: Path) -> bool:
    """Achado 3: só um arquivo que carrega a marca de geração pode ser
    apagado automaticamente. Ver o comentário em `MARCA_DE_GERADO`.
    """
    if caminho.suffix != ".toml":
        # .claude/agents/*.md nunca carrega a marca (quebraria o critério 1)
        # — por isso nunca é elegível para remoção automática aqui.
        return False
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    # Achado A9.1: exige que a marca cite ESTE papel. Uma cópia de um arquivo
    # gerado carrega a marca do original, não bate com o próprio nome, e por
    # isso é preservada e apenas relatada.
    return marca_de_gerado(caminho.stem) in conteudo


def _orfaos(papeis: list[Papel], diretorios: Diretorios) -> list[Path]:
    """Todo arquivo em `.claude/agents/`/`.codex/agents/` que não corresponde
    a um papel atual da fonte — para relatar (`verificar`) e, entre estes,
    só os marcados como gerados são elegíveis para apagar (`escrever`, via
    `_e_arquivo_gerado`).

    Achado 10 (auditoria DL-019 rodada 1, baixa): a versão anterior só
    olhava `sufixo` esperado com `iterdir()` (não recursivo), então um
    arquivo em subdiretório (`.claude/agents/sub/x.md`) ou com extensão
    alternativa (`intruso.markdown`) escapava do guarda inteiro — nem
    relatado, nem removido, simplesmente invisível. Agora a varredura é
    recursiva (`rglob`) e qualquer coisa que não seja **exatamente** um
    `<papel>.md`/`<papel>.toml` esperado, direto no diretório (não em
    subpasta), conta como divergência.
    """
    nomes_esperados = {papel.nome for papel in papeis}
    esperados_por_diretorio = {
        diretorios.claude: {f"{nome}.md" for nome in nomes_esperados},
        diretorios.codex: {f"{nome}.toml" for nome in nomes_esperados},
    }
    encontrados: list[Path] = []
    for diretorio, nomes_no_diretorio in esperados_por_diretorio.items():
        if not diretorio.is_dir():
            continue
        for existente in sorted(diretorio.rglob("*")):
            if existente.is_dir():
                continue
            relativo = existente.relative_to(diretorio)
            if len(relativo.parts) == 1 and relativo.name in nomes_no_diretorio:
                continue
            encontrados.append(existente)
    return encontrados


def escrever(papeis: list[Papel], diretorios: Diretorios = DIRETORIOS_REPO) -> None:
    gerados = _arquivos_esperados(papeis, diretorios)
    for arquivo in gerados:
        if arquivo.caminho.suffix == ".toml":
            _validar_toml(arquivo)
        # Achado 2: confina ANTES de qualquer escrita — se algum caminho
        # escapar do destino esperado, a função inteira falha sem gravar
        # nenhum dos arquivos desta chamada (mesma disciplina "tudo ou
        # nada" que carregar_papeis já aplica à leitura).
        _confinar_no_destino(
            arquivo.caminho,
            diretorios.claude if arquivo.caminho.suffix == ".md" else diretorios.codex,
        )

    for arquivo in gerados:
        arquivo.caminho.parent.mkdir(parents=True, exist_ok=True)
        # Escreve em arquivo temporário e troca de nome: uma falha no meio da
        # escrita não deixa um arquivo pela metade em cima do anterior.
        temporario = arquivo.caminho.with_suffix(arquivo.caminho.suffix + ".tmp")
        # Achado da DL-021: `write_text` em Windows converte `\n` para `\r\n`
        # na escrita, contaminando os derivados com CRLF e fazendo o
        # verificador byte-strict (achado 9 do DL-019) reportar divergência
        # em qualquer clone Windows. `write_bytes` grava os bytes literais
        # que `arquivo.conteudo.encode("utf-8")` produz — sempre LF, em
        # qualquer sistema operacional.
        temporario.write_bytes(arquivo.conteudo.encode("utf-8"))
        temporario.replace(arquivo.caminho)
        # Achado A3 (BL-175): `write_text` cria com `0o666 & ~umask`, então o
        # modo do arquivo gerado dependia do umask de quem rodou o comando —
        # 0o644 sob umask 022, 0o664 sob 002, 0o600 sob 077. Fixar aqui torna a
        # saída do gerador igual em qualquer máquina. Note que isto sozinho não
        # bastaria: o `verificar()` também parou de exigir modo exato, porque o
        # Git não versiona a diferença e um clone limpo não passa por aqui.
        arquivo.caminho.chmod(0o644)

    todos_orfaos = _orfaos(papeis, diretorios)
    removiveis = [caminho for caminho in todos_orfaos if _e_arquivo_gerado(caminho)]
    so_relatados = [caminho for caminho in todos_orfaos if caminho not in removiveis]
    for caminho in removiveis:
        caminho.unlink()

    mensagem = (
        f"Gerados {len(gerados)} arquivos a partir de {len(papeis)} papéis em {diretorios.fonte}."
    )
    if removiveis:
        relativos = ", ".join(str(c.relative_to(diretorios.raiz)) for c in removiveis)
        mensagem += (
            f" Removidos {len(removiveis)} derivado(s) órfão(s) marcado(s) como "
            f"gerado(s): {relativos}."
        )
    if so_relatados:
        relativos = ", ".join(str(c.relative_to(diretorios.raiz)) for c in so_relatados)
        mensagem += (
            f" ATENÇÃO: {len(so_relatados)} arquivo(s) sem papel correspondente na "
            f"fonte e SEM marca de gerado — não removidos automaticamente, decida "
            f"à mão: {relativos}."
        )
    print(mensagem)


def verificar(papeis: list[Papel], diretorios: Diretorios = DIRETORIOS_REPO) -> list[str]:
    """Retorna a lista de problemas encontrados (vazia = tudo sincronizado).

    Cobre os cenários 2 (derivado editado à mão), 3 (papel novo faltando
    derivado) e 4 (derivado órfão) do plano DL-019. Só lê arquivos — nunca
    grava nem apaga nada, por isso é seguro chamar sobre o repositório real.
    """
    problemas: list[str] = []
    esperados = _arquivos_esperados(papeis, diretorios)
    for arquivo in esperados:
        relativo = None
        if not arquivo.caminho.exists() and not arquivo.caminho.is_symlink():
            problemas.append(f"ausente: {arquivo.caminho.relative_to(diretorios.raiz)}")
            continue

        relativo = arquivo.caminho.relative_to(diretorios.raiz)

        # Achado 10: um symlink para fora do repositório tem o MESMO
        # conteúdo textual do derivado esperado (então uma comparação só de
        # texto aprova), mas deixou de ser um arquivo sob controle de
        # versão. `exists()` segue o link; por isso a checagem de symlink
        # vem antes e é independente da leitura de conteúdo.
        if arquivo.caminho.is_symlink():
            problemas.append(f"é um link simbólico, não um arquivo gerado: {relativo}")
            continue
        if not arquivo.caminho.is_file():
            problemas.append(f"não é um arquivo regular: {relativo}")
            continue

        informacao = arquivo.caminho.stat()
        modo = stat.S_IMODE(informacao.st_mode)
        # Achado A3 (BL-175): a versão anterior exigia modo EXATAMENTE 0o644 e
        # reprovava um clone limpo sob `umask 002` — padrão de usuário comum em
        # Debian/Ubuntu, onde o checkout cria 0o664. Sem uma linha alterada, o
        # build ficava vermelho; e como o Git não versiona a diferença entre
        # 664 e 644, `git status` e `git diff` saíam limpos e não havia como
        # diagnosticar. Pior: a remediação impressa (`--escrever`) não
        # convergia, porque a escrita também herdava o umask.
        #
        # Agora verificamos PROPRIEDADE, não valor: o que interessa é que o
        # arquivo não seja executável nem gravável por terceiros. 0o644 e
        # 0o664 passam; 0o755 e 0o666 reprovam.
        if modo & 0o111:
            problemas.append(
                f"permissão {oct(modo)} marca o arquivo como executável, e um papel "
                f"é só texto: {relativo}"
            )
        if modo & 0o002:
            problemas.append(
                f"permissão {oct(modo)} deixa o arquivo gravável por qualquer "
                f"usuário da máquina: {relativo}"
            )

        # Achado A9.2: `is_symlink()` é falso e `is_file()` é verdadeiro para um
        # hard link, e os bytes batem — o derivado passava a ser o mesmo inode de
        # um arquivo fora do repositório, com o guarda aprovando. Editar o outro
        # lado mudava o papel sem passar pelo gerador.
        if informacao.st_nlink != 1:
            problemas.append(
                f"tem {informacao.st_nlink} vínculos (hard link): {relativo} — um papel "
                "precisa ser um arquivo exclusivo do repositório, senão editar o outro "
                "vínculo altera o papel sem passar pelo gerador"
            )

        # Achado 9: compara BYTES, não texto. `Path.read_text()` normaliza
        # quebra de linha universal (`\r\n`/`\r` -> `\n`) antes da
        # comparação, então um derivado inteiro convertido para CRLF batia
        # com o esperado e "sincronizado" saía errado.
        atual = arquivo.caminho.read_bytes()
        esperado = arquivo.conteudo.encode("utf-8")
        if atual != esperado:
            problemas.append(f"divergente: {relativo}")

    for caminho in _orfaos(papeis, diretorios):
        relativo = caminho.relative_to(diretorios.raiz)
        # Achado A4 (BL-177): a mensagem mandava rodar `--escrever` para
        # corrigir, e para um `.md` órfão isso NÃO corrige — desde o achado 3,
        # `.claude/agents/*.md` nunca é apagado automaticamente. Quem seguia a
        # instrução via o build continuar vermelho sem entender por quê.
        if _e_arquivo_gerado(caminho):
            problemas.append(f"órfão (sem papel correspondente na fonte): {relativo}")
        else:
            problemas.append(
                f"órfão (sem papel correspondente na fonte): {relativo} — este NÃO é "
                "removido por --escrever, de propósito: pode ser um agente pessoal, e "
                "o gerador só apaga o que ele mesmo assinou. Remova à mão se for resíduo."
            )
    return sorted(set(problemas))


def main(argv: list[str] | None = None, diretorios: Diretorios | None = None) -> int:
    """CLI. ``diretorios`` existe para o teste do rodapé (achado R3-7).

    Sem ele, ``main`` só poderia ser exercitada contra a raiz real — e os
    testes deste projeto não escrevem na árvore de trabalho. Um valor padrão
    de parâmetro é resolvido na definição da função, então nem monkeypatch da
    constante global alcançaria; passar explicitamente é o mesmo padrão já
    usado por ``escrever`` e ``verificar``.
    """
    diretorios = diretorios if diretorios is not None else DIRETORIOS_REPO
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
        papeis = carregar_papeis(diretorios)
        if argumentos.escrever:
            escrever(papeis, diretorios)
            return 0
        problemas = verificar(papeis, diretorios)
    except ErroFrontmatter as erro:
        print(f"Fonte inválida, nada foi gravado: {erro}", file=sys.stderr)
        return 2

    if problemas:
        print("Derivados fora de sincronia com docs/agents/papeis/:", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        # Achado R3-7 (rodada 3): este rodapé era incondicional e aparecia logo
        # abaixo da linha que diz "este NÃO é removido por --escrever". A
        # informação certa estava na tela e era desmentida pela última linha —
        # que é a que o olho procura. Só sugere o comando quando ele resolve
        # pelo menos um dos problemas listados.
        if any("NÃO é removido por --escrever" not in problema for problema in problemas):
            print(
                "\nPara corrigir: .venv/bin/python scripts/gerar_agentes.py --escrever",
                file=sys.stderr,
            )
        else:
            print(
                "\nOs problemas acima exigem ação manual — leia cada linha; "
                "--escrever não os resolve.",
                file=sys.stderr,
            )
        return 1
    print(f"OK: {len(papeis)} papéis, todos os derivados sincronizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
