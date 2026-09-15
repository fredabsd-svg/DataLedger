"""Guarda a portabilidade dos papéis de agente entre ferramentas (DL-019).

Contexto: até esta etapa, a equipe de agentes do DataLedger só existia em
``.claude/agents/*.md``, no formato do Claude Code. Quem abrisse o
repositório com o Codex CLI (a ferramenta que o Fred usa pelo terminal,
segundo resposta dele em 2026-09-15) encontrava só o ``AGENTS.md`` — sem
saber que existe um auditor que não corrige implementação, um auxiliar que
não delega, nem por que essas restrições existem.

A correção foi extrair o conteúdo de cada papel para uma fonte única neutra
(``docs/agents/papeis/<papel>.md``) e gerar, a partir dela,
``.claude/agents/<papel>.md`` e ``.codex/agents/<papel>.toml`` com
``scripts/gerar_agentes.py``. Três cópias mantidas à mão divergiriam no
primeiro ajuste — é a mesma causa (duplicação, não distração) que motivou
``docs/agents/estado.md`` e ``test_documentacao_do_estado.py``, agora
aplicada aos papéis em vez de ao estado do projeto.

Este módulo não precisa de banco de dados: como ``test_documentacao_do_estado.py``,
ele lê e valida arquivos do repositório.

**A árvore de trabalho real nunca é escrita, apagada nem renomeada por
nenhum teste aqui.** Uma versão anterior deste arquivo corrompia
``.claude/agents/auditor-qa.md`` de propósito e confiava num bloco
``finally`` para desfazer — achado do arquiteto-senior revisando a entrega:
``finally`` não roda sob ``SIGKILL``/OOM/timeout de CI, o ambiente de
desenvolvimento é efêmero, e um estado corrompido no meio de um teste podia
ser preservado por outro processo sem ninguém perceber. Os cenários que
precisam de um derivado divergente, de um papel novo ou de um papel ausente
operam sobre uma **cópia isolada em ``tmp_path``** (ver
``_copiar_repositorio_isolado``), nunca sobre os arquivos reais — e a
fixture ``_protege_a_arvore_de_trabalho_real`` abaixo, que envolve todo
teste deste módulo, prova isso em execução.

Auditoria DL-019, rodada 1 (2026-09-15, REPROVADO — 12 achados). Os achados
1, 2, 3, 6, 7, 8, 9 e 10 foram corrigidos em ``scripts/gerar_agentes.py``, e
os testes que os provam estão nas seções marcadas abaixo. Os achados 5, 11 e
12 são corrigidos neste próprio arquivo.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

# apps/core/tests/test_x.py -> apps/core -> apps -> raiz do repositório.
REPO_ROOT = Path(__file__).resolve().parents[3]
FONTE_DIR = REPO_ROOT / "docs" / "agents" / "papeis"
CLAUDE_DIR = REPO_ROOT / ".claude" / "agents"
CODEX_DIR = REPO_ROOT / ".codex" / "agents"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

# Os sete papéis reais da equipe (docs/agents/equipe.md). O teste verifica
# que eles existem na fonte, mas não assume que é a lista *exaustiva*: um
# papel descartável criado durante um experimento não deveria quebrar este
# teste por si só — só os testes de sincronia (que cobrem qualquer papel
# presente na fonte, seja qual for) protegem a consistência de verdade.
PAPEIS_CONHECIDOS = {
    "arquiteto-senior",
    "desenvolvedor-pleno",
    "especialista-frontend",
    "auditor-qa",
    "auxiliar-pesquisa",
    "auxiliar-implementacao",
    "auxiliar-verificacao",
}


def _carregar_gerador():
    """Importa ``scripts/gerar_agentes.py`` sem depender de ``scripts`` ser
    um pacote instalável — o script foi desenhado para rodar tanto como CLI
    (``python scripts/gerar_agentes.py``) quanto para ser importado aqui.
    """
    caminho = REPO_ROOT / "scripts" / "gerar_agentes.py"
    spec = importlib.util.spec_from_file_location("gerar_agentes", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses com `from __future__ import annotations` resolve o módulo
    # da classe via `sys.modules`; sem registrar aqui antes de executar, a
    # busca falha com AttributeError em vez de importar o script.
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


ga = _carregar_gerador()

# Achado 11 (auditoria DL-019 rodada 1, baixa): o caminho do procedimento
# estava escrito literalmente em quatro lugares (o gerador, este teste, as
# duas skills), sem nenhum apontar para o outro. Agora só existe uma
# constante — a do próprio gerador — e este teste a reaproveita.
COMO_CRIAR = REPO_ROOT / ga.COMO_CRIAR_UM_PAPEL


# --------------------------------------------------------------------------
# Trava de segurança: nenhum teste deste módulo pode sujar o repositório real
# --------------------------------------------------------------------------
#
# Achado 5 (auditoria DL-019 rodada 1, média): a primeira versão desta trava
# usava `git status` sobre só três diretórios (`docs/agents/papeis`,
# `.claude/agents`, `.codex/agents`). `AGENTS.md`, `docs/agents/como-criar-
# um-papel.md` e `.agents/skills/` ficavam de fora, mesmo sendo lidos por
# testes deste módulo — uma sonda escrevendo neles passava em silêncio. A
# correção troca `git status` (que depende do estado do índice do Git) por
# um instantâneo de HASH do conteúdo de cada arquivo que o módulo
# efetivamente lê ou que o gerador pode escrever, computado dinamicamente
# (glob), não hardcoded.
#
# `docs/agents/equipe.md` e `docs/agents/estado.md` ficam FORA de propósito,
# mesmo estando ao lado de `como-criar-um-papel.md`: este módulo não os lê,
# e o arquiteto-senior os edita em paralelo com frequência (ele é dono
# dessa dupla nesta etapa) — monitorá-los sem necessidade recriaria o
# problema oposto, falso positivo por edição legítima concorrente em vez de
# reincidência real do defeito original.


def _arquivos_monitorados(raiz: Path = REPO_ROOT) -> list[Path]:
    """Todo arquivo que este módulo lê, mais o próprio gerador.

    Parametrizado por ``raiz`` para poder ser testado (ver
    ``test_instantaneo_monitorado_detecta_mudanca_fora_dos_tres_diretorios_originais``)
    sem nunca precisar apontar para o repositório real.
    """
    fonte = raiz / "docs" / "agents" / "papeis"
    claude = raiz / ".claude" / "agents"
    codex = raiz / ".codex" / "agents"
    skills = raiz / ".agents" / "skills"

    arquivos = [
        raiz / "AGENTS.md",
        raiz / "docs" / "agents" / "como-criar-um-papel.md",
        raiz / "scripts" / "gerar_agentes.py",
    ]
    if fonte.is_dir():
        arquivos += sorted(fonte.glob("*.md"))
    if claude.is_dir():
        arquivos += sorted(claude.glob("*.md"))
    if codex.is_dir():
        arquivos += sorted(codex.glob("*.toml"))
    if skills.is_dir():
        arquivos += sorted(skills.glob("*/SKILL.md"))
    return arquivos


def _instantaneo_arquivos_monitorados(raiz: Path = REPO_ROOT) -> str:
    hasher = hashlib.sha256()
    for caminho in _arquivos_monitorados(raiz):
        relativo = caminho.relative_to(raiz).as_posix()
        hasher.update(relativo.encode("utf-8"))
        try:
            hasher.update(caminho.read_bytes())
        except FileNotFoundError:
            hasher.update(b"<ausente>")
    return hasher.hexdigest()


@pytest.fixture(autouse=True)
def _protege_a_arvore_de_trabalho_real(request):
    """Prova, em execução, que nenhum teste escreve fora de ``tmp_path``.

    Envolve TODO teste deste módulo (``autouse=True``). Complementa a
    correção de verdade (operar sobre cópias isoladas — ver
    ``_copiar_repositorio_isolado``), não a substitui: mesmo que um teste
    futuro reintroduza a prática de escrever no repositório real, esta
    fixture reprova a suíte e aponta exatamente qual teste foi.
    """
    antes = _instantaneo_arquivos_monitorados()
    yield
    depois = _instantaneo_arquivos_monitorados()
    assert antes == depois, (
        f"{request.node.nodeid} alterou algum arquivo monitorado do repositório "
        "real (ver _arquivos_monitorados). Testes deste módulo só podem "
        "escrever dentro de tmp_path — use _copiar_repositorio_isolado(tmp_path) "
        "em vez de tocar nos arquivos reais."
    )


def _copiar_repositorio_isolado(tmp_path: Path) -> ga.Diretorios:
    """Copia a fonte e os dois derivados reais para dentro de ``tmp_path``.

    Usada pelos cenários que precisam de um repositório "de verdade" para
    operar, mas nunca podem ser o repositório de verdade. A cópia mora
    inteiramente em ``tmp_path``, que o pytest apaga sozinho ao final — não
    depende de nenhum código deste arquivo para ser limpa.
    """
    raiz_isolada = tmp_path / "repo"
    for origem in (FONTE_DIR, CLAUDE_DIR, CODEX_DIR):
        destino = raiz_isolada / origem.relative_to(REPO_ROOT)
        shutil.copytree(origem, destino)
    return ga.Diretorios.para_raiz(raiz_isolada)


_FONTE_MINIMA = (
    "---\n"
    "nome: {nome}\n"
    "descricao: >-\n"
    "  {descricao}\n"
    "perfil:\n"
    "  raciocinio: equilibrado\n"
    "  esforco: medio\n"
    "  escreve_arquivos: nao\n"
    "  memoria_de_projeto: nao\n"
    "  delega_para: []\n"
    "claude:\n"
    "  model: sonnet\n"
    "  effort: medium\n"
    "  color: cyan\n"
    '  tools: "Read"\n'
    '  disallowedTools: "Write, Edit, NotebookEdit, Agent"\n'
    "---\n\n# Papel de teste\n\nVocê existe só para este teste.\n"
)


def _escrever_fonte_minima(
    caminho: Path, *, nome: str, descricao: str = "Papel de teste.", **overrides
) -> None:
    """Grava uma fonte sintética válida (por padrão), para testes que
    exercitam uma única regra de validação sem precisar copiar um papel
    real. ``overrides`` substitui uma linha inteira do frontmatter por
    chave (ex.: ``perfil_raciocinio="rapido"``) — ver usos abaixo.
    """
    conteudo = _FONTE_MINIMA.format(nome=nome, descricao=descricao)
    for chave, valor in overrides.items():
        conteudo = conteudo.replace(chave, valor)
    caminho.write_text(conteudo, encoding="utf-8")


# --------------------------------------------------------------------------
# Reimplementação mínima de scripts/validate-docs.ps1
# --------------------------------------------------------------------------
#
# `pwsh` não está disponível neste ambiente de desenvolvimento (ver relato de
# entrega da DL-019). A execução OFICIAL das regras de documentação continua
# sendo `scripts/validate-docs.ps1` na integração contínua, sobre TODO o
# repositório; esta função cobre só os arquivos que esta etapa criou, como
# verificação prévia equivalente, para não entregar Markdown que a CI
# reprovaria.
_LINK_MD_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_BLOCO_CODIGO_RE = re.compile(r"^```.*?^```[^\n]*", re.MULTILINE | re.DOTALL)


def _validar_markdown(caminho: Path) -> list[str]:
    problemas = []
    try:
        conteudo = caminho.read_bytes().decode("utf-8")
    except UnicodeDecodeError as erro:
        return [f"{caminho}: UTF-8 inválido ({erro})"]

    if not re.search(r"^# .+", conteudo, re.MULTILINE):
        problemas.append(f"{caminho}: sem título principal '# ' no corpo")
    if re.search(r"[ \t]+\r?$", conteudo, re.MULTILINE):
        problemas.append(f"{caminho}: espaço em branco no fim de uma linha")
    if not conteudo.endswith("\n"):
        problemas.append(f"{caminho}: sem nova linha no final do arquivo")

    prosa = _BLOCO_CODIGO_RE.sub("", conteudo)
    for correspondencia in _LINK_MD_RE.finditer(prosa):
        destino = correspondencia.group(1).strip().strip("<>")
        if not destino or destino.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destino):
            continue
        destino_sem_ancora = destino.split("#", 1)[0].split("?", 1)[0]
        if not destino_sem_ancora:
            continue
        alvo = (caminho.parent / destino_sem_ancora).resolve()
        if not alvo.exists():
            problemas.append(f"{caminho}: link relativo inexistente: {destino}")
    return problemas


def _extrair_links(texto: str) -> list[str]:
    """Extrai destinos de link markdown locais (não URL, não âncora)."""
    destinos = []
    for correspondencia in _LINK_MD_RE.finditer(texto):
        destino = correspondencia.group(1).strip().strip("<>")
        if not destino or destino.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destino):
            continue
        destinos.append(destino.split("#", 1)[0].split("?", 1)[0])
    return [d for d in destinos if d]


# --------------------------------------------------------------------------
# Critério 2: a fonte única existe, com frontmatter neutro e corpo em pt-br
# --------------------------------------------------------------------------


def test_fonte_unica_tem_os_sete_papeis_conhecidos():
    """Todo papel real da equipe (docs/agents/equipe.md) tem fonte neutra."""
    papeis = ga.carregar_papeis()
    nomes = {papel.nome for papel in papeis}
    ausentes = PAPEIS_CONHECIDOS - nomes
    assert not ausentes, (
        f"Papéis sem fonte em {FONTE_DIR}: {sorted(ausentes)}. Todo papel "
        "real da equipe precisa de docs/agents/papeis/<papel>.md."
    )


def test_cada_papel_tem_corpo_em_portugues_com_titulo():
    """O corpo (depois do frontmatter) é a definição legível do papel."""
    for papel in ga.carregar_papeis():
        assert re.search(r"^# .+", papel.corpo, re.MULTILINE), (
            f"{papel.arquivo_fonte}: corpo sem título principal '# '"
        )
        # "Você" é o pronome de tratamento usado em todo papel existente
        # (ver .claude/agents/*.md original); um corpo sem ele é sinal de
        # que a extração perdeu o texto ou ele não está em português.
        assert "Você" in papel.corpo, (
            f"{papel.arquivo_fonte}: corpo não parece estar em português (pronome 'Você' ausente)"
        )


def test_frontmatter_neutro_rejeita_valores_fora_do_vocabulario_fixo(tmp_path):
    """`raciocinio`/`esforco`/etc. só aceitam o vocabulário do plano DL-019.

    Sem isto, um papel novo poderia escrever `raciocinio: rapido` (que não
    existe em nenhuma ferramenta) e o gerador propagaria o valor sem
    reclamar. Testa a validação diretamente, sem tocar na fonte real.
    """
    invalido = tmp_path / "papel-invalido.md"
    _escrever_fonte_minima(
        invalido,
        nome="papel-invalido",
        **{"raciocinio: equilibrado": "raciocinio: rapido"},
    )
    with pytest.raises(ga.ErroFrontmatter, match="raciocinio"):
        ga.carregar_papel(invalido)


# --------------------------------------------------------------------------
# Achado 2 (alta): `nome` sem validação permitia travessia de caminho
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_ruim",
    [
        "../../../ESCAPOU",
        "Meu Papel",
        "tem espaço",
        "MAIUSCULO",
        "termina-com-hifen-",
        "-comeca-com-hifen",
        "tem/barra",
        "",
    ],
)
def test_nome_invalido_e_rejeitado(tmp_path, nome_ruim):
    """Reprodução do achado 2: `nome: ../../../ESCAPOU` fazia `escrever()`
    gravar fora dos diretórios de destino. A regex agora recusa qualquer
    coisa que não seja letras minúsculas, dígitos e hífen simples.
    """
    caminho = tmp_path / "arquivo-qualquer.md"
    conteudo = _FONTE_MINIMA.format(nome=nome_ruim, descricao="Papel de teste.")
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ga.ErroFrontmatter, match="nome"):
        ga.carregar_papel(caminho)


def test_nome_precisa_bater_com_o_nome_do_arquivo(tmp_path):
    caminho = tmp_path / "meu-papel.md"
    _escrever_fonte_minima(caminho, nome="nome-diferente")
    with pytest.raises(ga.ErroFrontmatter, match="nome"):
        ga.carregar_papel(caminho)


def test_escrever_nunca_grava_fora_da_raiz_isolada(tmp_path):
    """Reprodução direta do achado 2: fonte válida, `escrever()` só pode
    tocar arquivos dentro de `diretorios.claude`/`diretorios.codex`.
    """
    raiz = tmp_path / "repo"
    diretorios = ga.Diretorios.para_raiz(raiz)
    diretorios.fonte.mkdir(parents=True)
    _escrever_fonte_minima(diretorios.fonte / "papel-teste.md", nome="papel-teste")

    antes = set(tmp_path.rglob("*"))
    ga.escrever(ga.carregar_papeis(diretorios), diretorios)
    depois = set(tmp_path.rglob("*"))

    novos = depois - antes
    for caminho in novos:
        if caminho.is_dir():
            continue
        assert caminho.is_relative_to(diretorios.claude) or caminho.is_relative_to(
            diretorios.codex
        ), f"escrever() criou {caminho}, fora dos diretórios de destino esperados"


# --------------------------------------------------------------------------
# Achado 6 (média): `perfil` e `claude` podiam se contradizer sem acusar
# --------------------------------------------------------------------------


def test_coerencia_dos_sete_papeis_reais():
    """`carregar_papeis()` sobre a fonte real não deve levantar — prova que
    a validação de coerência não é falso positivo nos papéis atuais.
    """
    ga.carregar_papeis()  # não deve levantar ErroFrontmatter


def test_escreve_arquivos_nao_com_write_nas_tools_e_rejeitado(tmp_path):
    """Reprodução do achado 6: acrescentar `Write` ao `tools` do
    `auditor-qa` mantendo `escreve_arquivos: nao` não acusava nada.
    """
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{'tools: "Read"': 'tools: "Read, Write"'},
    )
    with pytest.raises(ga.ErroFrontmatter, match="escreve_arquivos"):
        ga.carregar_papel(caminho)


def test_escreve_arquivos_nao_sem_disallowed_completo_e_rejeitado(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{'disallowedTools: "Write, Edit, NotebookEdit, Agent"': 'disallowedTools: "Agent"'},
    )
    with pytest.raises(ga.ErroFrontmatter, match="disallowedTools"):
        ga.carregar_papel(caminho)


def test_delega_vazio_com_agent_nas_tools_e_rejeitado(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{'tools: "Read"': 'tools: "Read, Agent"'},
    )
    with pytest.raises(ga.ErroFrontmatter, match="Agent"):
        ga.carregar_papel(caminho)


def test_memoria_de_projeto_sim_sem_memory_project_e_rejeitado(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{"memoria_de_projeto: nao": "memoria_de_projeto: sim"},
    )
    with pytest.raises(ga.ErroFrontmatter, match="memoria_de_projeto"):
        ga.carregar_papel(caminho)


def test_delega_para_papel_inexistente_e_rejeitado(tmp_path):
    """Só detectável com o conjunto completo — testado via `carregar_papeis`."""
    diretorios = ga.Diretorios.para_raiz(tmp_path)
    diretorios.fonte.mkdir(parents=True)
    _escrever_fonte_minima(
        diretorios.fonte / "papel-teste.md",
        nome="papel-teste",
        **{"delega_para: []": "delega_para: [papel-que-nao-existe]"},
    )
    with pytest.raises(ga.ErroFrontmatter, match="papel-que-nao-existe"):
        ga.carregar_papeis(diretorios)


# --------------------------------------------------------------------------
# Achado 8 (baixa): chave desconhecida no frontmatter era aceita em silêncio
# --------------------------------------------------------------------------


def test_chave_desconhecida_no_perfil_e_rejeitada(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{"delega_para: []": "delega_para: []\n  sandbox: workspace"},
    )
    with pytest.raises(ga.ErroFrontmatter, match="sandbox"):
        ga.carregar_papel(caminho)


def test_chave_desconhecida_no_claude_e_rejeitada(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    _escrever_fonte_minima(
        caminho,
        nome="papel-teste",
        **{'tools: "Read"': 'tools: "Read"\n  sandbox_mode: workspace'},
    )
    with pytest.raises(ga.ErroFrontmatter, match="sandbox_mode"):
        ga.carregar_papel(caminho)


# --------------------------------------------------------------------------
# Achado 7 (baixa): caractere de controle derrubava o gerador com traceback
# --------------------------------------------------------------------------


def test_caractere_de_controle_no_corpo_e_rejeitado_com_mensagem_clara(tmp_path):
    caminho = tmp_path / "papel-teste.md"
    conteudo = _FONTE_MINIMA.format(nome="papel-teste", descricao="Papel de teste.")
    conteudo = conteudo.replace("Você existe", "Você\x0cexiste")  # \x0c = form feed
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ga.ErroFrontmatter, match="controle"):
        ga.carregar_papel(caminho)


# --------------------------------------------------------------------------
# Critério 3 / cenário 6: TOML do Codex é válido e preserva acentuação
# --------------------------------------------------------------------------


def test_codex_toml_tem_os_tres_campos_e_e_carregavel_por_tomllib():
    for papel in ga.carregar_papeis():
        conteudo = ga.construir_codex_toml(papel)
        dados = tomllib.loads(conteudo)
        assert set(dados.keys()) == {"name", "description", "developer_instructions"}, (
            f"{papel.nome}: TOML do Codex só pode ter os três campos confirmados "
            f"em documentação oficial, encontrei {sorted(dados.keys())}"
        )
        assert dados["name"] == papel.nome


def test_codex_toml_preserva_acentuacao_utf8():
    """`developer_instructions` não pode virar `?` nem escapar acentos."""
    papel_pt = next(p for p in ga.carregar_papeis() if p.nome == "desenvolvedor-pleno")
    conteudo = ga.construir_codex_toml(papel_pt)
    dados = tomllib.loads(conteudo)
    # Palavra que aparece no corpo real de desenvolvedor-pleno.md com
    # acentuação: se o escapamento do gerador corromper UTF-8, ela some.
    instrucoes = dados["developer_instructions"]
    assert "não" in instrucoes
    assert "contábil" in instrucoes or "contábeis" in instrucoes


# --------------------------------------------------------------------------
# Achado 1 (alta): derivados do Codex afirmavam restrição técnica inexistente
# --------------------------------------------------------------------------


def test_codex_toml_nao_afirma_restricao_tecnica_que_nao_existe():
    """Reprodução do achado 1: 4 dos 7 arquivos do Codex afirmavam, em texto
    categórico, uma restrição técnica que ali não existe.
    """
    # "Essa restrição é" sozinho NÃO entra: também aparece, honestamente, na
    # frase "Essa restrição é uma **instrução de comportamento**" (a
    # restrição de delegação, que é comportamental em toda ferramenta). As
    # três frases abaixo são inequívocas — só aparecem quando o texto afirma
    # mecanismo técnico que o Codex não tem.
    frases_proibidas = ("restrição técnica", "é **técnica**", "Restrição técnica")
    for papel in ga.carregar_papeis():
        conteudo = (CODEX_DIR / f"{papel.nome}.toml").read_text(encoding="utf-8")
        dados = tomllib.loads(conteudo)
        instrucoes = dados["developer_instructions"]
        for frase in frases_proibidas:
            assert frase not in instrucoes, (
                f"{papel.nome}.toml afirma {frase!r}, que é falso no Codex"
            )


def test_aviso_de_honestidade_aparece_antes_de_qualquer_mencao_a_ferramenta():
    """O aviso precisa vir ANTES da primeira menção a Write/Agent no corpo —
    quem lê de cima para baixo tem de encontrar a verdade primeiro.
    """
    for papel in ga.carregar_papeis():
        if not papel.precisa_aviso_de_honestidade:
            continue
        conteudo = (CODEX_DIR / f"{papel.nome}.toml").read_text(encoding="utf-8")
        dados = tomllib.loads(conteudo)
        instrucoes = dados["developer_instructions"]
        indice_aviso = instrucoes.find("instrução de comportamento")
        assert indice_aviso != -1, f"{papel.nome}: aviso de honestidade ausente"
        indices_ferramenta = [
            i for i in (instrucoes.find("Write"), instrucoes.find("Agent")) if i != -1
        ]
        assert indices_ferramenta, f"{papel.nome}: esperava menção a Write ou Agent no corpo"
        assert indice_aviso < min(indices_ferramenta), (
            f"{papel.nome}.toml: aviso de honestidade aparece depois da primeira "
            "menção a Write/Agent — quem lê de cima para baixo vê a afirmação "
            "errada antes da retificação"
        )


def test_aviso_de_honestidade_cita_a_ferramenta_certa_para_a_razao_certa():
    """Achado 1, agravante: `auxiliar-implementacao` só não delega (a
    restrição real é sobre `Agent`), mas o aviso antigo sempre citava
    `Write`/`Edit`, mesmo quando a razão era outra.
    """
    conteudo = (CODEX_DIR / "auxiliar-implementacao.toml").read_text(encoding="utf-8")
    dados = tomllib.loads(conteudo)
    instrucoes = dados["developer_instructions"]
    assert "`Agent`" in instrucoes
    assert "Write" not in instrucoes and "Edit" not in instrucoes, (
        "auxiliar-implementacao escreve arquivos (não é a razão do aviso dele); "
        "o aviso não deveria citar Write/Edit"
    )


# --------------------------------------------------------------------------
# Critério 7 (guarda de sincronia) e cenários 2, 3 e 4 do plano DL-019
# --------------------------------------------------------------------------


def test_derivados_estao_sincronizados_com_a_fonte():
    """Guarda principal: nenhum `.claude/agents/*` ou `.codex/agents/*`
    diverge do que `docs/agents/papeis/` geraria agora, e não há órfão.

    Esta é a verificação que reprova o build (critério 7 do plano DL-019)
    quando alguém edita um derivado à mão em vez da fonte, ou esquece de
    rodar o gerador depois de mudar um papel. `verificar()` só lê arquivos
    (ver docstring dela em scripts/gerar_agentes.py), por isso é seguro
    chamá-la sobre o repositório real sem cópia isolada.
    """
    problemas = ga.verificar(ga.carregar_papeis())
    assert not problemas, (
        "Derivados fora de sincronia com docs/agents/papeis/ — rode "
        "'.venv/bin/python scripts/gerar_agentes.py --escrever' e "
        f"reveja o diff: {problemas}"
    )


def test_derivado_editado_a_mao_reprova_a_sincronia(tmp_path):
    """Cenário 2 do plano DL-019, como regressão automatizada.

    Roda inteiramente sobre uma cópia isolada em `tmp_path` (ver
    `_copiar_repositorio_isolado`) — o `.claude/agents/auditor-qa.md` real
    nunca é tocado.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.claude / "auditor-qa.md"
    alvo.write_text(
        alvo.read_text(encoding="utf-8") + "\n<!-- edição manual indevida -->\n", encoding="utf-8"
    )

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    caminho_relativo = str(alvo.relative_to(diretorios.raiz))
    assert any(caminho_relativo in problema for problema in problemas), (
        f"Editar {alvo} à mão deveria ter sido detectado por verificar(), "
        f"mas os problemas relatados foram: {problemas}"
    )


def test_papel_novo_so_na_fonte_reprova_ate_os_derivados_existirem(tmp_path):
    """Cenário 3 do plano DL-019: papel acrescentado só na fonte."""
    diretorios = _copiar_repositorio_isolado(tmp_path)
    nome_temporario = "papel-teste-temporario-pytest"
    _escrever_fonte_minima(diretorios.fonte / f"{nome_temporario}.md", nome=nome_temporario)
    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any(nome_temporario in problema for problema in problemas), (
        f"Um papel novo só na fonte deveria aparecer como derivado ausente, "
        f"problemas encontrados: {problemas}"
    )


def test_papel_removido_da_fonte_deixa_derivado_orfao_detectavel(tmp_path):
    """Cenário 4 do plano DL-019: papel removido da fonte.

    Usa um papel SINTÉTICO, não um dos sete reais: depois da correção do
    achado 6, remover um papel real que outros `delega_para` referenciam
    (como `auxiliar-verificacao`, citado por quatro papéis) é rejeitado
    ainda em `carregar_papeis()` — corretamente, é uma fonte inconsistente,
    não o cenário "derivado ficou órfão" que este teste quer reproduzir. O
    papel sintético não é referenciado por ninguém, então isola a
    característica que o cenário 4 testa.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    nome = "papel-temporario-para-remover"
    _escrever_fonte_minima(diretorios.fonte / f"{nome}.md", nome=nome)
    ga.escrever(ga.carregar_papeis(diretorios), diretorios)  # cria os derivados dele
    (diretorios.fonte / f"{nome}.md").unlink()  # remove só da fonte, derivados ficam

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("órfão" in problema and nome in problema for problema in problemas), (
        f"Remover {nome}.md da fonte deveria deixar os derivados órfãos "
        f"detectáveis; problemas encontrados: {problemas}"
    )


def test_fonte_com_frontmatter_invalido_nao_grava_nada(tmp_path):
    """Cenário 5: frontmatter inválido falha alto e claro, sem gravar.

    Usa uma raiz isolada inteiramente dentro de `tmp_path` — nunca toca no
    diretório real, nem precisa (`carregar_papeis` só lê).
    """
    fonte_isolada = tmp_path / "docs" / "agents" / "papeis"
    fonte_isolada.mkdir(parents=True)
    (fonte_isolada / "quebrado.md").write_text("isto não começa com '---'\n", encoding="utf-8")

    diretorios = ga.Diretorios.para_raiz(tmp_path)
    with pytest.raises(ga.ErroFrontmatter, match="'---'"):
        ga.carregar_papeis(diretorios)


# --------------------------------------------------------------------------
# Achado 3 (média): `--escrever` apagava arquivo não gerado sem confirmação
# --------------------------------------------------------------------------


def test_escrever_nao_apaga_derivado_claude_sem_papel_correspondente(tmp_path):
    """Reprodução do achado 3, lado Claude: um agente local (`.md` sem a
    marca de gerado, e o Claude Code não tem onde colocar essa marca sem
    quebrar o critério 1) precisa sobreviver a `--escrever`.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.claude / "meu-agente-local.md"
    alvo.write_text("---\nname: meu-agente-local\n---\n\n# Agente pessoal\n", encoding="utf-8")

    ga.escrever(ga.carregar_papeis(diretorios), diretorios)

    assert alvo.exists(), "arquivo local sem papel correspondente foi apagado por engano"
    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("meu-agente-local.md" in p for p in problemas), (
        "o arquivo devia continuar sendo relatado como órfão, mesmo não removido"
    )


def test_escrever_apaga_toml_orfao_que_carrega_a_marca_de_gerado(tmp_path):
    """O outro lado do achado 3: um `.toml` que ESTE gerador escreveu antes
    (carrega `MARCA_DE_GERADO`) e cujo papel já não existe na fonte pode
    (e deve) ser removido automaticamente — é o comportamento do cenário 4
    que a correção do achado 3 não podia quebrar.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    papeis = ga.carregar_papeis(diretorios)
    conteudo_gerado = ga.construir_codex_toml(papeis[0], diretorios)
    alvo = diretorios.codex / "papel-fantasma.toml"
    alvo.write_text(conteudo_gerado, encoding="utf-8")
    assert ga.MARCA_DE_GERADO in conteudo_gerado, (
        "pré-condição do teste: o conteúdo carrega a marca"
    )

    ga.escrever(papeis, diretorios)

    assert not alvo.exists(), "TOML órfão marcado como gerado deveria ter sido removido"


def test_escrever_nao_apaga_toml_sem_a_marca_de_gerado(tmp_path):
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.codex / "nao-gerado-por-nos.toml"
    alvo.write_text(
        'name = "x"\ndescription = "y"\ndeveloper_instructions = "z"\n', encoding="utf-8"
    )

    ga.escrever(ga.carregar_papeis(diretorios), diretorios)

    assert alvo.exists(), "TOML sem a marca de gerado foi apagado por engano"


# --------------------------------------------------------------------------
# Achado 9 (baixa): guarda não detectava divergência de fim de linha (CRLF)
# --------------------------------------------------------------------------


def test_verificar_detecta_derivado_convertido_para_crlf(tmp_path):
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.claude / "auditor-qa.md"
    alvo.write_bytes(alvo.read_bytes().replace(b"\n", b"\r\n"))

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("auditor-qa.md" in p for p in problemas), (
        "conversão para CRLF muda os bytes do arquivo e devia ser detectada "
        f"como divergência; problemas encontrados: {problemas}"
    )


# --------------------------------------------------------------------------
# Achado 10 (baixa): symlink, permissão, subdiretório e extensão escapavam
# --------------------------------------------------------------------------


def test_verificar_detecta_symlink_no_lugar_do_derivado(tmp_path):
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.claude / "auditor-qa.md"
    alvo_fora_do_repo = tmp_path / "fora-do-repo.md"
    alvo_fora_do_repo.write_text(alvo.read_text(encoding="utf-8"), encoding="utf-8")
    alvo.unlink()
    alvo.symlink_to(alvo_fora_do_repo)

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("simbólico" in p and "auditor-qa.md" in p for p in problemas), (
        f"symlink para fora do repositório devia ser detectado; problemas: {problemas}"
    )


def test_verificar_detecta_permissao_diferente_da_esperada(tmp_path):
    diretorios = _copiar_repositorio_isolado(tmp_path)
    alvo = diretorios.claude / "auditor-qa.md"
    alvo.chmod(0o777)

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("permissão" in p and "auditor-qa.md" in p for p in problemas), (
        f"chmod 777 devia ser detectado; problemas: {problemas}"
    )


def test_orfaos_detecta_subdiretorio_e_extensao_alternativa(tmp_path):
    diretorios = _copiar_repositorio_isolado(tmp_path)
    (diretorios.claude / "sub").mkdir()
    (diretorios.claude / "sub" / "x.md").write_text("x", encoding="utf-8")
    (diretorios.claude / "intruso.markdown").write_text("x", encoding="utf-8")

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("sub" in p and "x.md" in p for p in problemas), problemas
    assert any("intruso.markdown" in p for p in problemas), problemas


# --------------------------------------------------------------------------
# Achado 9: papéis com aviso de honestidade
# --------------------------------------------------------------------------


def test_papeis_restritos_recebem_aviso_de_honestidade_no_codex():
    """`auditor-qa`, os três auxiliares: restrição só é técnica no Claude."""
    for papel in ga.carregar_papeis():
        if not papel.precisa_aviso_de_honestidade:
            continue
        caminho = CODEX_DIR / f"{papel.nome}.toml"
        conteudo = caminho.read_text(encoding="utf-8")
        tem_aviso = "instrução de comportamento" in conteudo
        tem_aviso = tem_aviso and "isolamento técnico garantido" in conteudo
        assert tem_aviso, (
            f"{caminho}: papel com escreve_arquivos=nao ou delega_para vazio "
            "precisa do aviso de honestidade explícito no corpo do derivado "
            "Codex (critério 9 do plano DL-019)."
        )


def test_papeis_sem_restricao_nao_ganham_aviso_falso():
    """Quem escreve e delega no Claude não devia parecer restrito no Codex."""
    for papel in ga.carregar_papeis():
        if papel.precisa_aviso_de_honestidade:
            continue
        caminho = CODEX_DIR / f"{papel.nome}.toml"
        conteudo = caminho.read_text(encoding="utf-8")
        assert "Aviso de honestidade desta ferramenta" not in conteudo, (
            f"{caminho}: papel que escreve e delega no Claude não deveria "
            "carregar um aviso de restrição que não existe para ele."
        )


# --------------------------------------------------------------------------
# Critério 6 / cenário 7: links recalculados existem de verdade
# --------------------------------------------------------------------------


def test_fontes_e_procedimento_passam_na_validacao_de_documentacao():
    arquivos = [COMO_CRIAR, *sorted(FONTE_DIR.glob("*.md"))]
    if SKILLS_DIR.is_dir():
        arquivos.extend(sorted(SKILLS_DIR.glob("*/SKILL.md")))
    problemas = []
    for arquivo in arquivos:
        problemas.extend(_validar_markdown(arquivo))
    mensagem = "Documentação fora das regras de scripts/validate-docs.ps1:\n" + "\n".join(problemas)
    assert not problemas, mensagem


def test_link_relativo_inexistente_na_fonte_reprova_a_validacao(tmp_path):
    """Cenário 7 do plano DL-019, contra a reimplementação em Python."""
    quebrado = tmp_path / "com-link-quebrado.md"
    quebrado.write_text(
        "# Título\n\nVeja [um arquivo que não existe](./nao-existe-de-verdade.md).\n",
        encoding="utf-8",
    )
    problemas = _validar_markdown(quebrado)
    assert any("link relativo inexistente" in problema for problema in problemas)


# --------------------------------------------------------------------------
# Achado 11 (baixa): links dos .codex/agents/*.toml não eram validados
# --------------------------------------------------------------------------


def test_links_dos_codex_toml_resolvem_a_partir_da_raiz():
    """`scripts/validate-docs.ps1` só olha `.md`, e este módulo, antes desta
    correção, também não conferia os links dentro de `developer_instructions`
    — 13 links viviam sem nenhum mecanismo checando se continuavam válidos.
    """
    problemas = []
    for papel in ga.carregar_papeis():
        conteudo = (CODEX_DIR / f"{papel.nome}.toml").read_text(encoding="utf-8")
        dados = tomllib.loads(conteudo)
        for destino in _extrair_links(dados["developer_instructions"]):
            # Links do Codex são relativos à RAIZ (regra 1 do plano DL-019),
            # não ao diretório do arquivo — diferente de Markdown comum.
            if not (REPO_ROOT / destino).exists():
                problemas.append(f"{papel.nome}.toml: link quebrado: {destino}")
    assert not problemas, problemas


def test_validacao_de_link_do_toml_reprova_alvo_renomeado(tmp_path):
    """Forma de verificar proposta pela auditoria: um alvo citado deixa de
    existir → a validação (função pura, sem tocar arquivo real) reprova.
    """
    conteudo_instrucoes = "Leia [algo](docs/projeto/requisitos-que-nao-existe-mais.md)."
    problemas = [
        destino
        for destino in _extrair_links(conteudo_instrucoes)
        if not (REPO_ROOT / destino).exists()
    ]
    assert problemas == ["docs/projeto/requisitos-que-nao-existe-mais.md"]


# --------------------------------------------------------------------------
# Critério 10 (adaptado ao escopo Codex): ponteiros não duplicam AGENTS.md
# --------------------------------------------------------------------------


def test_skills_de_codex_nao_duplicam_regra_do_agents_md():
    """`.agents/skills/` deve apontar para AGENTS.md, nunca repeti-lo.

    Extrai frases longas (>= 80 caracteres) do AGENTS.md real e confere que
    nenhuma aparece, literal, dentro das skills. Um trecho curto compartilhado
    por acaso não é problema; um parágrafo inteiro copiado é exatamente a
    duplicação que este projeto já pagou caro por uma vez (ver
    docs/agents/estado.md e o incidente de 2026-09-13 citado no CLAUDE.md).
    """
    assert SKILLS_DIR.is_dir(), ".agents/skills/ deveria existir como ponteiro"
    texto_regras = AGENTS_MD.read_text(encoding="utf-8")
    frases_longas = [
        linha.strip()
        for linha in re.split(r"(?<=[.!?])\s+|\n", texto_regras)
        if len(linha.strip()) >= 80
    ]
    assert frases_longas, "AGENTS.md não rendeu frase longa para comparar — verifique o regex"

    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        conteudo_skill = skill_md.read_text(encoding="utf-8")
        duplicadas = [frase for frase in frases_longas if frase in conteudo_skill]
        assert not duplicadas, (
            f"{skill_md} copiou trecho literal do AGENTS.md em vez de apontar "
            f"para ele: {duplicadas[:1]!r}"
        )


# --------------------------------------------------------------------------
# Achado 5: prova de que o instantâneo cobre o ponto cego original
# --------------------------------------------------------------------------


def test_instantaneo_monitorado_detecta_mudanca_fora_dos_tres_diretorios_originais(tmp_path):
    """Reprodução segura do achado 5: a auditoria provou o ponto cego
    escrevendo em `AGENTS.md` e `docs/agents/equipe.md` DE VERDADE, num
    ambiente descartável só dela. Este teste prova a mesma cobertura contra
    uma raiz sintética — nunca a real — montando os arquivos que o módulo
    lê e confirmando que mudar cada um muda o instantâneo.
    """
    (tmp_path / "AGENTS.md").write_text("conteúdo original do AGENTS.md", encoding="utf-8")
    (tmp_path / "docs" / "agents" / "papeis").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gerar_agentes.py").write_text("# placeholder", encoding="utf-8")
    (tmp_path / "docs" / "agents" / "como-criar-um-papel.md").write_text(
        "# Como criar um papel\n\nProcedimento original.\n", encoding="utf-8"
    )

    antes = _instantaneo_arquivos_monitorados(tmp_path)

    (tmp_path / "AGENTS.md").write_text("conteúdo ALTERADO do AGENTS.md", encoding="utf-8")
    depois_agents = _instantaneo_arquivos_monitorados(tmp_path)
    assert antes != depois_agents, (
        "mudança em AGENTS.md não alterou o instantâneo (achado 5 reaberto)"
    )

    (tmp_path / "AGENTS.md").write_text("conteúdo original do AGENTS.md", encoding="utf-8")
    (tmp_path / "docs" / "agents" / "como-criar-um-papel.md").write_text(
        "# Como criar um papel\n\nProcedimento ALTERADO.\n", encoding="utf-8"
    )
    depois_procedimento = _instantaneo_arquivos_monitorados(tmp_path)
    assert antes != depois_procedimento, (
        "mudança em docs/agents/como-criar-um-papel.md não alterou o "
        "instantâneo (achado 5 reaberto)"
    )


def test_instantaneo_monitorado_nao_inclui_equipe_md_ou_estado_md(tmp_path):
    """Decisão explícita, não esquecimento: este módulo não lê
    `docs/agents/equipe.md` nem `docs/agents/estado.md` (o arquiteto-senior
    os edita em paralelo com frequência), então eles ficam fora do
    instantâneo de propósito — monitorá-los recriaria falso positivo por
    edição concorrente legítima.
    """
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "papeis").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gerar_agentes.py").write_text("x", encoding="utf-8")

    antes = _instantaneo_arquivos_monitorados(tmp_path)
    (tmp_path / "docs" / "agents" / "equipe.md").write_text("mudou", encoding="utf-8")
    (tmp_path / "docs" / "agents" / "estado.md").write_text("mudou", encoding="utf-8")
    depois = _instantaneo_arquivos_monitorados(tmp_path)
    assert antes == depois


# --------------------------------------------------------------------------
# Critério 11: procedimento de criar papel novo existe e é citado
# --------------------------------------------------------------------------


def test_como_criar_um_papel_existe_e_e_citado_no_codex():
    assert COMO_CRIAR.is_file(), (
        "docs/agents/como-criar-um-papel.md precisa existir — é o procedimento "
        "que o Fred pediu para que outras ferramentas também criem papéis."
    )
    for papel in ga.carregar_papeis():
        conteudo = (CODEX_DIR / f"{papel.nome}.toml").read_text(encoding="utf-8")
        assert ga.COMO_CRIAR_UM_PAPEL in conteudo, (
            f"{papel.nome}.toml não cita {ga.COMO_CRIAR_UM_PAPEL}"
        )


def test_skill_de_criar_papel_aponta_para_o_procedimento():
    skill = SKILLS_DIR / "criar-um-papel" / "SKILL.md"
    assert skill.is_file(), "esperava a skill .agents/skills/criar-um-papel/SKILL.md"
    assert "como-criar-um-papel.md" in skill.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Achado 12 (baixa): guarda de tamanho cobria só o AGENTS.md da raiz
# --------------------------------------------------------------------------

_DIRETORIOS_EXCLUIDOS_TAMANHO = {".venv", ".git", "node_modules", "__pycache__"}


def _tamanho_total_dos_agents_md(raiz: Path) -> tuple[int, list[Path]]:
    """Soma o tamanho de TODO `AGENTS.md` sob `raiz`, não só o da raiz.

    Achado 12: o `project_doc_max_bytes` do Codex se aplica ao CONJUNTO de
    arquivos de instrução que ele concatena subindo o caminho a partir do
    diretório de trabalho — se um dia existir `apps/AGENTS.md`, cada um pode
    ficar abaixo da margem individualmente e a SOMA estourar sem aviso.
    """
    arquivos = sorted(
        caminho
        for caminho in raiz.rglob("AGENTS.md")
        if not any(
            parte in _DIRETORIOS_EXCLUIDOS_TAMANHO for parte in caminho.relative_to(raiz).parts
        )
    )
    return sum(caminho.stat().st_size for caminho in arquivos), arquivos


def test_soma_de_todos_os_agents_md_e_calculada_corretamente(tmp_path):
    """Prova a lógica de soma numa raiz sintética, sem tocar no repositório
    real — forma de verificar proposta pela auditoria ("criar apps/AGENTS.md
    grande numa cópia isolada e exigir que o teste reprove"), adaptada para
    não precisar criar o arquivo no repositório de verdade.
    """
    (tmp_path / "AGENTS.md").write_text("a" * 100, encoding="utf-8")
    sub = tmp_path / "apps"
    sub.mkdir()
    (sub / "AGENTS.md").write_text("b" * 250, encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "AGENTS.md").write_text("c" * 99999, encoding="utf-8")

    total, arquivos = _tamanho_total_dos_agents_md(tmp_path)

    assert total == 350, "deveria somar só os dois AGENTS.md fora de .venv"
    assert len(arquivos) == 2
    assert (tmp_path / ".venv" / "AGENTS.md") not in arquivos


def test_agents_md_nao_ultrapassa_a_margem_de_seguranca_do_codex():
    """O Codex CLI concatena os `AGENTS.md` do caminho e PARA em 32.768 bytes.

    `project_doc_max_bytes` é o nome do limite, documentado como padrão do
    Codex CLI. Ele não é um erro visível: a ferramenta simplesmente para de
    ler depois desse tanto de bytes, e as últimas seções do arquivo — hoje,
    justamente "Como estas regras são impostas" — deixam de chegar ao
    modelo, sem aviso nenhum para quem está usando.

    Medido em 2026-09-15: a soma de todos os `AGENTS.md` do repositório
    (hoje, só um) estava em 22.601-22.639 bytes (~69% do limite) e cresce a
    cada etapa do projeto. Esta verificação usa uma margem de 30.000 bytes,
    deliberadamente abaixo do limite real de 32.768, para dar folga de
    reação antes que o truncamento comece a acontecer de verdade. Se este
    teste falhar, o total já passou da margem de segurança: mova conteúdo
    para um documento apontado por ele em vez de só aumentar o número aqui.
    """
    limite_real_do_codex = 32_768
    margem_de_seguranca = 30_000
    tamanho_total, arquivos = _tamanho_total_dos_agents_md(REPO_ROOT)
    nomes = [str(a.relative_to(REPO_ROOT)) for a in arquivos]
    assert tamanho_total <= margem_de_seguranca, (
        f"Soma de {len(arquivos)} AGENTS.md ({nomes}) = {tamanho_total} bytes, "
        f"acima da margem de segurança de {margem_de_seguranca} bytes. O limite "
        f"real do Codex CLI (project_doc_max_bytes) é {limite_real_do_codex} "
        "bytes — depois disso a ferramenta trunca as regras EM SILÊNCIO, sem "
        "erro visível, cortando primeiro as últimas seções do arquivo. Reduza "
        "o(s) arquivo(s) ou mova conteúdo para um documento apontado por eles "
        "antes que o limite real seja atingido."
    )
