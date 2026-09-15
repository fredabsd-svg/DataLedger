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
(cenários 2, 3 e 4 do plano DL-019) agora operam sobre uma **cópia isolada
em ``tmp_path``** (ver ``_copiar_repositorio_isolado``), nunca sobre os
arquivos reais — e a fixture ``_protege_a_arvore_de_trabalho_real`` abaixo,
que envolve todo teste deste módulo, prova isso em execução: compara um
instantâneo de ``git status`` antes e depois de cada teste e reprova,
apontando o teste exato, se algo mudou.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
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
COMO_CRIAR = REPO_ROOT / "docs" / "agents" / "como-criar-um-papel.md"
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


# --------------------------------------------------------------------------
# Trava de segurança: nenhum teste deste módulo pode sujar o repositório real
# --------------------------------------------------------------------------

# Escopo deliberadamente restrito aos diretórios que este módulo e o gerador
# tocam. Um `git status` sobre o repositório inteiro pegaria também edições
# legítimas de outro agente rodando em paralelo (o arquiteto-senior, por
# exemplo, edita `docs/planos/` e `docs/agents/estado.md` na mesma janela de
# tempo) e produziria falso positivo sem relação com este arquivo de teste.
_CAMINHOS_MONITORADOS = ("docs/agents/papeis", ".claude/agents", ".codex/agents")


def _instantaneo_git_status() -> str:
    resultado = subprocess.run(
        ["git", "status", "--porcelain", "--", *_CAMINHOS_MONITORADOS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return resultado.stdout


@pytest.fixture(autouse=True)
def _protege_a_arvore_de_trabalho_real(request):
    """Prova, em execução, que nenhum teste escreve fora de ``tmp_path``.

    Envolve TODO teste deste módulo (``autouse=True``). Complementa a
    correção de verdade (operar sobre cópias isoladas — ver
    ``_copiar_repositorio_isolado``), não a substitui: mesmo que um teste
    futuro reintroduza a prática de escrever no repositório real, esta
    fixture reprova a suíte e aponta exatamente qual teste foi, em vez de
    deixar a corrupção passar em silêncio até alguém notar um `git diff`
    inesperado depois.
    """
    antes = _instantaneo_git_status()
    yield
    depois = _instantaneo_git_status()
    assert antes == depois, (
        f"{request.node.nodeid} alterou a árvore de trabalho real em um dos "
        f"caminhos monitorados ({', '.join(_CAMINHOS_MONITORADOS)}). Testes "
        "deste módulo só podem escrever dentro de tmp_path — use "
        "_copiar_repositorio_isolado(tmp_path) em vez de tocar nos arquivos "
        f"reais.\ngit status antes:\n{antes!r}\ngit status depois:\n{depois!r}"
    )


def _copiar_repositorio_isolado(tmp_path: Path) -> ga.Diretorios:
    """Copia a fonte e os dois derivados reais para dentro de ``tmp_path``.

    Usada pelos cenários 2, 3 e 4 do plano DL-019 (derivado editado à mão,
    papel novo, papel removido): eles precisam de um repositório "de
    verdade" para operar, mas nunca podem ser o repositório de verdade. A
    cópia mora inteiramente em ``tmp_path``, que o pytest apaga sozinho ao
    final — não depende de nenhum código deste arquivo para ser limpa.
    """
    raiz_isolada = tmp_path / "repo"
    for origem in (FONTE_DIR, CLAUDE_DIR, CODEX_DIR):
        destino = raiz_isolada / origem.relative_to(REPO_ROOT)
        shutil.copytree(origem, destino)
    return ga.Diretorios.para_raiz(raiz_isolada)


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
    invalido.write_text(
        "---\n"
        "nome: papel-invalido\n"
        "descricao: >-\n"
        "  Papel só para este teste.\n"
        "perfil:\n"
        "  raciocinio: rapido\n"
        "  esforco: alto\n"
        "  escreve_arquivos: nao\n"
        "  memoria_de_projeto: nao\n"
        "  delega_para: []\n"
        "claude:\n"
        "  model: sonnet\n"
        "  effort: high\n"
        "  color: cyan\n"
        '  tools: "Read"\n'
        "---\n\n# Papel inválido\n",
        encoding="utf-8",
    )
    with pytest.raises(ga.ErroFrontmatter, match="raciocinio"):
        ga.carregar_papel(invalido)


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
    """Cenário 3 do plano DL-019: papel acrescentado só na fonte.

    Também sobre a cópia isolada — o novo papel nunca chega a existir em
    `docs/agents/papeis/` de verdade.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    nome_temporario = "papel-teste-temporario-pytest"
    (diretorios.fonte / f"{nome_temporario}.md").write_text(
        "---\n"
        f"nome: {nome_temporario}\n"
        "descricao: >-\n"
        "  Papel temporário criado só durante este teste automatizado.\n"
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
        "---\n\n# Papel temporário de teste\n\nSó existe durante o teste.\n",
        encoding="utf-8",
    )
    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any(nome_temporario in problema for problema in problemas), (
        f"Um papel novo só na fonte deveria aparecer como derivado ausente, "
        f"problemas encontrados: {problemas}"
    )


def test_papel_removido_da_fonte_deixa_derivado_orfao_detectavel(tmp_path):
    """Cenário 4 do plano DL-019: papel removido da fonte.

    Apaga o arquivo só na cópia isolada — `auxiliar-verificacao.md` real
    nunca é removido.
    """
    diretorios = _copiar_repositorio_isolado(tmp_path)
    papel = "auxiliar-verificacao"
    (diretorios.fonte / f"{papel}.md").unlink()

    problemas = ga.verificar(ga.carregar_papeis(diretorios), diretorios)
    assert any("órfão" in problema and papel in problema for problema in problemas), (
        f"Remover {papel}.md da fonte deveria deixar os derivados órfãos "
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
# Critério 9: aviso de honestidade nos papéis sem restrição técnica no Codex
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
# Critério 11: procedimento de criar papel novo existe e é citado
# --------------------------------------------------------------------------


def test_como_criar_um_papel_existe_e_e_citado_no_codex():
    assert COMO_CRIAR.is_file(), (
        "docs/agents/como-criar-um-papel.md precisa existir — é o procedimento "
        "que o Fred pediu para que outras ferramentas também criem papéis."
    )
    for papel in ga.carregar_papeis():
        conteudo = (CODEX_DIR / f"{papel.nome}.toml").read_text(encoding="utf-8")
        assert "como-criar-um-papel.md" in conteudo, (
            f"{papel.nome}.toml não cita docs/agents/como-criar-um-papel.md"
        )


def test_skill_de_criar_papel_aponta_para_o_procedimento():
    skill = SKILLS_DIR / "criar-um-papel" / "SKILL.md"
    assert skill.is_file(), "esperava a skill .agents/skills/criar-um-papel/SKILL.md"
    assert "como-criar-um-papel.md" in skill.read_text(encoding="utf-8")


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
# Guarda novo (pedido do arquiteto-senior, 2026-09-15): limite do Codex CLI
# --------------------------------------------------------------------------


def test_agents_md_nao_ultrapassa_a_margem_de_seguranca_do_codex():
    """O Codex CLI concatena os `AGENTS.md` do caminho e PARA em 32.768 bytes.

    `project_doc_max_bytes` é o nome do limite, documentado como padrão do
    Codex CLI. Ele não é um erro visível: a ferramenta simplesmente para de
    ler depois desse tanto de bytes, e as últimas seções do arquivo — hoje,
    justamente "Como estas regras são impostas" — deixam de chegar ao
    modelo, sem aviso nenhum para quem está usando.

    Medido em 2026-09-15: AGENTS.md tinha 22.601 bytes (69% do limite) e
    cresce a cada etapa do projeto. Esta verificação usa uma margem de
    30.000 bytes, deliberadamente abaixo do limite real de 32.768, para dar
    folga de reação antes que o truncamento comece a acontecer de verdade.
    Se este teste falhar, o AGENTS.md já passou da margem de segurança: mova
    conteúdo para um documento apontado por ele (o padrão que o próprio
    projeto já usa para não duplicar o estado, por exemplo) em vez de só
    aumentar o número aqui.
    """
    limite_real_do_codex = 32_768
    margem_de_seguranca = 30_000
    tamanho = AGENTS_MD.stat().st_size
    assert tamanho <= margem_de_seguranca, (
        f"AGENTS.md tem {tamanho} bytes, acima da margem de segurança de "
        f"{margem_de_seguranca} bytes. O limite real do Codex CLI "
        f"(project_doc_max_bytes) é {limite_real_do_codex} bytes — depois "
        "disso a ferramenta trunca as regras EM SILÊNCIO, sem erro visível, "
        "cortando primeiro as últimas seções do arquivo. Reduza o arquivo ou "
        "mova conteúdo para um documento apontado por ele antes que o limite "
        "real seja atingido."
    )
