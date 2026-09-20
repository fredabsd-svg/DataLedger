"""BL-379 (achado J9 da nona auditoria,
docs/auditorias/2026-09-19-dl-026-dl-028-rodada-9.md) + BL-376 (achado
J5, mesma auditoria): extrai a lógica de decisão de
`.github/workflows/identificacao-do-emitente.yml` para um ARQUIVO.

**Por que isto existe (BL-379).** Até esta correção, a decisão morava em
120 linhas de Python dentro de uma STRING de YAML (o passo "Decidir se os
caminhos vigiados mudaram"). Três consequências medidas: `ruff check .`
passava e não via aquele código (não é um arquivo `.py`); `pytest` não o
cobria (zero testes); e das 7 execuções reais do workflow, TODAS eram
`event: push` — o ramo `pull_request`, o único que de fato importa para
bloquear merge (é ele quem calcula `git diff base...head` num checkout de
`refs/pull/N/merge`), nunca rodou. Um cenário medido nesse ramo nunca
exercitado (`pull_request` com `base.sha`/`head.sha` vazios) produzia
`relevante=False` com um motivo tranquilizador ("nenhum dos 0 arquivo(s)
alterado(s) bate...") — inversão latente do lado seguro. Com a lógica
neste arquivo, ela entra de uma vez dentro do `ruff`, do `pytest` e do
job `Backend` — as três verificações que já existem e já valem para
qualquer outro `.py` do projeto.

**Por que a lista também mudou de lado (BL-376).** `CAMINHOS_VIGIADOS`
(a lista antiga) listava o que IMPORTAVA — e MEDIDO: uma tela imprimível
nova em `apps/fiscal/templates/fiscal/apuracao.html` (o lugar IDIOMÁTICO
para um módulo novo, já que `config/settings.py` liga `APP_DIRS: True`)
não batia em NENHUM padrão da lista, e a garantia desligava em silêncio
— na etapa (DL-027) que cria justamente esse tipo de tela em todo módulo.
`CAMINHOS_NAO_RELEVANTES`, abaixo, inverte o lado seguro: a lista passa a
dizer o que é IRRELEVANTE, e qualquer coisa fora dela é medida por
padrão. Custo aceito, medido pelo arquiteto-senior: ~30s de runner numa
alteração de código que não é visual.

## Uso

```bash
python scripts/decidir_caminhos_vigiados.py
```

Lê `NOME_DO_EVENTO`, `BASE_SHA`, `HEAD_SHA`, `ANTES_SHA`, `DEPOIS_SHA` do
ambiente — os MESMOS nomes que o passo do workflow já define a partir de
`github.event_name`/`github.event.pull_request.base.sha`/`github.event.
pull_request.head.sha`/`github.event.before`/`github.sha`. Escreve
`relevante=true`/`relevante=false` em `GITHUB_OUTPUT`, se a variável
estiver definida; sempre imprime o resultado e o motivo em `stdout`, para
aparecer no log do job independente disso.
"""

import os
import re
import subprocess

# BL-376 (achado J5): lista do lado SEGURO — o que é IRRELEVANTE para o
# job de identificação do emitente. QUALQUER OUTRA COISA é relevante por
# padrão (o inverso da lista antiga, que listava o que IMPORTAVA e
# deixava o resto de fora, em silêncio, sempre que alguém esquecesse de
# atualizá-la). Deliberadamente PEQUENA (decisão do arquiteto-senior):
# uma lista de exclusão grande é a mesma lista de inclusão de novo, só
# que escrita ao contrário.
#
# `*.md` e `**/*.md` JUNTOS: a conversão de padrão abaixo segue a
# semântica documentada do GitHub, em que `*` NÃO cruza `/` — então
# `*.md` só bate arquivo Markdown na RAIZ do repositório (`README.md`,
# `AGENTS.md`) e `**/*.md` só bate um que esteja dentro de algum
# diretório (Markdown fora de `docs/` — `docs/**`, abaixo, já cobre esse
# caso — ex.: um `README.md` futuro dentro de `apps/<app>/`). São dois
# padrões porque são dois casos, não uma duplicata.
CAMINHOS_NAO_RELEVANTES = [
    "docs/**",
    "*.md",
    "**/*.md",
    ".github/ISSUE_TEMPLATE/**",
]

_PADRAO_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def sha_valida(sha):
    """`True` só para uma string de exatamente 40 dígitos hexadecimais —
    o formato de um SHA-1 completo do Git. BL-379 (achado J9): um SHA
    vazio ou malformado precisa virar "sem intervalo para comparar"
    (RELEVANTE, lado seguro) — nunca "0 arquivos alterados" (irrelevante).
    MEDIDO antes desta correção: `pull_request` com `base.sha`/`head.sha`
    vazios montava o intervalo `"..."`; `git diff --name-only ...` saía
    com código `0` e saída VAZIA — indistinguível de "nada mudou", quando
    na verdade era "não sei comparar nada"."""
    return bool(_PADRAO_SHA.fullmatch(sha or ""))


def padrao_para_regex(padrao):
    """Sintaxe documentada do GitHub para `paths:` — `**` casa zero ou
    mais diretórios (inclusive `/`); `*` casa qualquer coisa MENOS `/`;
    `?` casa um caractere que não seja `/`. EXTRAÍDA do workflow
    (BL-379) sem mudar a semântica — só o LUGAR mudou, e agora `ruff` e
    `pytest` alcançam este código."""
    partes = []
    i = 0
    while i < len(padrao):
        if padrao[i : i + 2] == "**":
            partes.append(".*")
            i += 2
        elif padrao[i] == "*":
            partes.append("[^/]*")
            i += 1
        elif padrao[i] == "?":
            partes.append("[^/]")
            i += 1
        else:
            partes.append(re.escape(padrao[i]))
            i += 1
    return re.compile("^" + "".join(partes) + "$")


def bate(padroes_compilados, arquivo):
    return any(p.match(arquivo) for p in padroes_compilados)


def determinar_intervalo(evento, base_sha, head_sha, antes_sha, depois_sha):
    """Devolve `(intervalo_ou_None, motivo_do_lado_seguro_ou_None)` —
    função PURA, nunca chama `git`. `intervalo is None` sempre significa
    "relevante=True, lado seguro", com o motivo já pronto para relatar;
    caso contrário, `intervalo` é o argumento de `git diff --name-only
    <intervalo>`."""
    if evento == "pull_request":
        # BL-379/J9: a validação de FORMATO acontece ANTES de montar o
        # intervalo, de propósito — ver a docstring de `sha_valida`.
        if not (sha_valida(base_sha) and sha_valida(head_sha)):
            return None, (
                "evento 'pull_request' com SHA de base e/ou head ausente ou "
                f"fora do formato de 40 hexadecimais (base={base_sha!r}, "
                f"head={head_sha!r}) — tratado como RELEVANTE, lado seguro: "
                "nunca 'relevante=False' por SHA inválido."
            )
        return f"{base_sha}...{head_sha}", None

    if evento == "push":
        # `before` vem só de zeros no PRIMEIRO push de uma branch nova
        # (não há commit anterior para comparar); string VAZIA recebe o
        # MESMO tratamento (`set("") <= {"0"}` já é verdadeiro — conjunto
        # vazio é subconjunto de qualquer conjunto). Sem intervalo,
        # tratado como relevante — o lado seguro: medir de mais nunca
        # aprova documento sem emitente por engano; medir de menos, sim.
        if set(antes_sha or "") <= {"0"}:
            return None, (
                "evento 'push' sem commit anterior para comparar (before="
                f"{antes_sha!r}) — primeiro push de uma branch nova, tratado "
                "como RELEVANTE, lado seguro."
            )
        return f"{antes_sha}...{depois_sha}", None

    # `workflow_dispatch` (disparo manual) ou evento futuro sem base
    # natural para comparar: tratado como pedido explícito de medir de
    # verdade.
    return None, (
        f"evento {evento!r} sem intervalo de diff natural para comparar "
        "(disparo manual, ou evento sem base/head conhecidos) — lado seguro."
    )


def arquivos_alterados_no_intervalo(intervalo, cwd=None):
    """`(arquivos_ou_None, aviso_ou_None)` — roda `git diff --name-only
    <intervalo>` de verdade. `aviso` não-`None` significa "não consegui
    comparar" (ex.: `before` de um force-push depois de `git gc`,
    `unknown revision`) — o chamador trata isso como RELEVANTE, lado
    seguro, nunca como "0 arquivos"."""
    resultado = subprocess.run(
        ["git", "diff", "--name-only", intervalo],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if resultado.returncode != 0:
        return None, (
            f"'git diff {intervalo}' falhou (código {resultado.returncode}): "
            f"{resultado.stderr.strip()!r} — tratando como RELEVANTE (lado seguro)."
        )
    return [linha for linha in resultado.stdout.splitlines() if linha], None


def decidir(evento, base_sha, head_sha, antes_sha, depois_sha, cwd=None):
    """Decide se algo RELEVANTE mudou nesta revisão — "relevante" quer
    dizer "não bate em NENHUM padrão de `CAMINHOS_NAO_RELEVANTES`" (ver o
    comentário da constante sobre o porquê do lado invertido). Devolve
    `(relevante: bool, motivo: str)`; `cwd`, se informado, é o diretório
    onde `git diff` roda — usado pelos testes contra um repositório
    Git descartável, nunca contra a árvore deste projeto."""
    intervalo, motivo_lado_seguro = determinar_intervalo(
        evento, base_sha, head_sha, antes_sha, depois_sha
    )
    if intervalo is None:
        return True, motivo_lado_seguro

    arquivos, aviso = arquivos_alterados_no_intervalo(intervalo, cwd=cwd)
    if aviso is not None:
        return True, aviso

    padroes_compilados = [padrao_para_regex(p) for p in CAMINHOS_NAO_RELEVANTES]
    relevantes = sorted(a for a in arquivos if not bate(padroes_compilados, a))
    if relevantes:
        return True, (
            f"{len(relevantes)} de {len(arquivos)} arquivo(s) alterado(s) NÃO "
            f"batem com nenhum padrão irrelevante: {', '.join(relevantes)}"
        )
    if arquivos:
        return False, (
            f"os {len(arquivos)} arquivo(s) alterado(s) batem TODOS com os "
            f"{len(CAMINHOS_NAO_RELEVANTES)} padrões irrelevantes "
            f"({', '.join(CAMINHOS_NAO_RELEVANTES)}) — pulando Playwright, "
            "poppler-utils e a medição no navegador."
        )
    return False, "nenhum arquivo alterado no intervalo — pulando a medição."


def main():
    evento = os.environ.get("NOME_DO_EVENTO", "")
    relevante, motivo = decidir(
        evento,
        os.environ.get("BASE_SHA", ""),
        os.environ.get("HEAD_SHA", ""),
        os.environ.get("ANTES_SHA", ""),
        os.environ.get("DEPOIS_SHA", ""),
    )
    print(f"relevante={relevante}")
    print(f"motivo: {motivo}")

    caminho_saida = os.environ.get("GITHUB_OUTPUT")
    if caminho_saida:
        with open(caminho_saida, "a") as saida_do_passo:
            saida_do_passo.write(f"relevante={'true' if relevante else 'false'}\n")


if __name__ == "__main__":
    main()
