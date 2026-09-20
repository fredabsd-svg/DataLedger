"""DL-028, fatia 1 (docs/planos/DL-028-o-juiz-aponta-para-o-produto.md):
instrumento que responde, por MEDIÇÃO DO NAVEGADOR sobre o PRODUTO REAL —
não sobre protótipos autônomos, e não por simulação de cascata CSS em
Python — se cada documento imprimível do produto sai com a identificação
do ESCRITÓRIO emitente.

**Por que este instrumento existe.** A oitava auditoria da DL-026
(docs/auditorias/2026-09-19-dl-026-rodada-8.md, §7) mediu que o juiz de
bancada (`scripts/juiz.py`) só consome HTML autônomo
das variantes do gauntlet — nunca `static/css/base.css` + `templates/**`,
que é o que o cliente do escritório de fato recebe. Para a pergunta "o
emitente aparece no papel?", isso deixava a guarda do `pytest`
(`apps/contabilidade/tests/test_bl329_marca_fora_do_papel.py` e
`test_bl331_timbre_do_escritorio_no_papel.py`, que simulam cascata CSS SEM
navegador) como a ÚNICA camada, não a primeira de duas — e o mesmo
relatório mediu **onze construções banais de CSS** que apagam a
identificação do escritório com aquela suíte inteira verde (H1).

**O que este instrumento NÃO é.** Não substitui a suíte `pytest` (que
continua sendo a "primeira linha barata" — rebaixamento formalizado na
fatia 3 deste plano). Não roda na integração contínua (isso é a fatia 2).
É ferramenta de BANCADA, como `scripts/juiz.py` e
`scripts/medir_impressao.py`: quem fecha uma etapa que mexa em
`static/css/base.css`, em `templates/**` ou em qualquer tela nova com
timbre roda este script manualmente contra o produto antes de declarar a
etapa pronta.

**Os dois interpretadores, a mesma separação de `medir_impressao.py`.** O
Python da venv do projeto (3.14) não tem Playwright — não é dependência de
`requirements/`, de propósito. Este script usa a venv do projeto para
RENDERIZAR o produto (Django real, `django.test.Client`, banco descartável
semeado) e delega só a medição no NAVEGADOR (visibilidade sob impressão +
PDF A4) a um subprocesso do Python DO SISTEMA
(`DL_PYTHON_DO_SISTEMA`, default `/usr/bin/python3`), que tem Playwright.

**Nenhum caminho fixo de navegador.** A resolução do executável do
Chromium é feita por `scripts/sonda_visibilidade.resolver_executavel_do_
chromium` — variável de ambiente `DL_CHROMIUM_EXECUTAVEL` ou descoberta
nativa do Playwright — nunca um literal de caminho de uma máquina
específica.

**O conjunto de telas é DERIVADO, nunca escrito à mão** (`_descobrir_telas_
com_timbre`, abaixo): este script anda por TODA a urlconf nomeada do
projeto (exceto o `django.contrib.admin`, terceiro reconhecido — nunca
carrega `.timbre-impressao`), requisita (GET, autenticado) cada rota cujos
parâmetros são conhecidos da base semeada (`empresa_id`, `conta_id` — os
dois que este script sabe preencher hoje) e mantém as respostas cujo HTML
contém a classe `timbre-impressao`. Se amanhã uma tela nova (Fiscal, por
exemplo) ganhar timbre e só precisar de `empresa_id` para ser alcançada,
ela entra aqui SOZINHA — é o BL-363 resolvido, para o navegador real, no
mesmo espírito da correção que a rodada 12 da DL-026 está fazendo (em
arquivo DISJUNTO: `apps/contabilidade/tests/**`) no motor CSS simulado.
Rotas cujos parâmetros este script NÃO conhece são PULADAS, com aviso
explícito em stderr — nunca silenciosamente ausentes (BL-356).

**Identificação PARCIAL conta como falha** (decisão desta etapa, a
confirmar com o Fred): não basta o CONTÊINER `.timbre-impressao` estar
visível — CADA linha (`Escritorio.linhas_do_timbre`, um `<p>` por linha)
precisa estar visível E aparecer no texto extraído do PDF. Uma sabotagem
que esconda só uma linha (ex.: `.timbre-impressao p:nth-of-type(2) {
display: none }` — o registro profissional some, a razão social continua)
REPROVA aqui, porque o documento sai com identificação incompleta, não
íntegra.

**O oráculo final é o PIXEL no papel, não a cor computada** (BL-372, achado
J1 da nona auditoria,
docs/auditorias/2026-09-19-dl-026-dl-028-rodada-9.md). Até esta correção,
a única checagem de "a tinta pinta de verdade" era `_tinta_invisivel`:
"o alfa da cor computada é zero?" — uma LISTA de um item (alfa zero),
não a propriedade que interessa (a tinta contrasta com o papel). O
auditor mediu, no arquivo que fecha exatamente esta classe de defeito nas
rodadas anteriores: `.conteudo-principal { color: var(--papel-elevado) }`
(`#FFFFFF`, token LEGÍTIMO do projeto) apaga o timbre do papel com
`1910 passed` E com este instrumento em `exit 0`, porque branco tem alfa
OPACO (1, não 0) — `_tinta_invisivel` não pega, e `pdftotext` ainda lê o
glifo (pintado, só que da cor do fundo). As duas metades da checagem
antiga são cegas pela MESMA razão.

A correção NÃO troca a lista por outra lista (`#fff`, `clip-path` — é o
erro que esta etapa paga há doze rodadas): rasteriza a folha A4 já gerada
(`pdftoppm -gray`, mesma dependência de sistema de `_texto_do_pdf`, ver
`_rasterizar_primeira_pagina`), localiza a posição REAL de cada linha do
timbre no PDF exportado (`pdftotext -bbox`, ver `_palavras_da_pagina` e
`_bbox_da_linha` — a posição de um objeto de texto no PDF não depende da
cor com que ele foi pintado) e exige uma contagem de PIXELS ESCUROS acima
de um piso medido (`_pixels_escuros_na_faixa`, `PISO_PIXELS_ESCUROS_POR_
LINHA`). É a pergunta do contador — "tem tinta no papel onde deveria
ter?" — e ela SOMA às checagens anteriores (DOM: `checkVisibility` +
área + alcançabilidade; `_tinta_invisivel`: alfa zero, mais barato,
continua rodando primeiro), nunca as substitui.

**Falha de infraestrutura é distinguível de falha de conteúdo** (BL-356).
Códigos de saída:

- `0`: sucesso — todas as telas derivadas saem com o emitente completo.
- `1`: **REPROVADO** — o script rodou até o fim, mas ao menos uma tela saiu
  sem o emitente completo. É um achado sobre o PRODUTO.
- `2`: **Recusado** — falha de infraestrutura (banco ausente, poppler-utils
  ausente, Python do sistema sem Playwright, Chromium indisponível, zero
  telas derivadas). Não é um veredito sobre o produto.

## Como usar

```bash
export DL_CONFIRMO_BANCO_DESCARTAVEL='<nome exato do banco>'
python scripts/medir_identificacao_do_emitente.py [pasta-de-saida] \
    [--telas=contabilidade_web:balancete,contabilidade_web:razao]
```

`pasta-de-saida` (opcional): onde preservar os PDFs A4 gerados (padrão:
pasta temporária descartada ao fim). `--telas=` (opcional): restringe a
MEDIÇÃO às telas nomeadas — a DERIVAÇÃO continua completa; é só um filtro
de saída, útil em bancada para repetir uma sabotagem numa tela só sem
esperar as demais. Nomeie pelo NOME COMPLETO da rota
(`namespace:nome`, o mesmo que aparece em "telas derivadas com timbre"),
nunca só o `nome` — desde o BL-374/J3 essa é a CHAVE de `--telas=`, não
mais um apelido curto que pode colidir entre apps.
"""

import html
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Reaproveita a infraestrutura de `medir_impressao.py` — Django configurado,
# cliente autenticado, cenário (empresa/conta) da base semeada, reescrita do
# CSS para `file://` — NUNCA reimplementada aqui (docstring do módulo).
import medir_impressao  # noqa: E402 — precisa vir depois de ajustar o sys.path

# `sonda_visibilidade.py` é módulo IRMÃO de `juiz.py` E deste script — os
# três moram em `scripts/` desde a correção do BL-408/K5 (décima
# auditoria): até então, os dois primeiros viviam em
# `docs/assets/design/gauntlet/`, fora do alcance do `ruff`/`pytest`
# porque `docs/**` é tratado como prosa (`pyproject.toml` e
# `scripts/decidir_caminhos_vigiados.py` os pulavam os dois) — exatamente
# a classe de defeito que o BL-379 existia para fechar, reproduzida no
# arquivo de que ESTE script depende. `sonda_visibilidade.py` não é um
# pacote instalado. A venv do projeto (Python 3.14, sem Playwright) NÃO
# importa este módulo em tempo de execução normal — só o Python DO
# SISTEMA (subprocesso, abaixo) importa de verdade, porque só ele usa
# Playwright. O caminho é só uma STRING passada ao subprocesso via JSON;
# `_verificar_sonda_disponivel` (abaixo) confirma cedo, na venv, que o
# ARQUIVO existe e tem sintaxe válida — sem precisar de Playwright para
# isso — em vez de deixar um caminho errado só aparecer como erro dentro
# do subprocesso.
_DIRETORIO_SONDA = str(Path(__file__).resolve().parent)

SELETOR_TIMBRE_CONTAINER = ".timbre-impressao"
SELETOR_TIMBRE_FILHOS = ".timbre-impressao p"

# BL-282/BL-331: a marca de quem VENDE o software — precisa estar AUSENTE
# do papel. Checado no texto do PDF ao lado da presença do timbre, pelo
# mesmo motivo que `scripts/medir_impressao.py` já checa isto: as duas
# metades do critério 9 ("o fornecedor sai" e "o escritório entra") só
# se provam JUNTAS — uma sozinha não garante que o papel saiu identificado.
MARCA_DO_FORNECEDOR = "DataLedger"

# ---------------------------------------------------------------------------
# Piso de regressão — LIMITE ESTRUTURAL da derivação, medido construindo o
# instrumento (não hipotetizado), e a resposta ao eixo do BL-363 que o
# arquiteto pediu para esta fatia: "reprova NOMEANDO a tela, sem ser uma
# lista escrita à mão que a derivação existe para evitar".
#
# `_descobrir_telas_com_timbre` deriva o CRESCIMENTO corretamente (uma tela
# nova que ganhe `.timbre-impressao` entra sozinha) — mas MEDIDO aqui,
# sabotando `templates/contabilidade/razao.html` (removendo só o bloco do
# timbre, nada de CSS): o instrumento saiu com "2 telas derivadas" e
# **código 0** — a Razão não RECEBE nota reprovada, ela simplesmente
# DEIXA DE EXISTIR para o instrumento, porque a única coisa que o
# qualifica como candidata é a MESMA marca que a sabotagem apagou. Isso
# vale para QUALQUER derivação por presença de marcador — inclusive a
# varredura estática de `templates/**` que a correção do BL-363 no motor
# simulado (rodada 12 da DL-026, arquivo disjunto) também usa: as duas
# têm o MESMO limite estrutural, porque as duas partem do mesmo sinal.
#
# Não existe marcador estrutural independente e confiável para "esta tela
# É um documento que precisa de timbre" — MEDIDO: `table.tabela-dados`
# também aparece em Conferência, Plano de Contas e no detalhe do
# lançamento, que CORRETAMENTE não têm timbre (H2/rodada 8: são telas de
# TRABALHO, não documentos entregues ao cliente). Adotar essa classe como
# universo produziria falso alarme nas telas de trabalho (BL-321).
#
# A saída, sem reintroduzir a lista proibida pelo BL-363 (aquela era o
# ÚNICO lugar que decidia QUAIS telas existem — cresce e encolhe junto
# com o produto sem ninguém tocar): um PISO pequeno, versionado à parte,
# que decide só REGRESSÃO. `_descobrir_telas_com_timbre` continua sendo a
# fonte para o que EXISTE (cresce sozinha); este conjunto é o mínimo que
# TEM que continuar existindo — o critério 3 da DL-026 ("Balancete,
# Diário, Razão"), já normativo hoje, sem esperar navegador nenhum para
# ser verdade. Se o produto legitimamente aposentar uma dessas telas,
# ALGUÉM edita esta linha — mudança visível, revisada, não divergência
# silenciosa entre duas cópias da mesma lista (que É o que o BL-352/363
# proíbe).
#
# BL-374 (achado J3 da nona auditoria): chaveado pelo NOME COMPLETO da
# rota (`namespace:nome`), nunca pelo nome curto (`nome.rsplit(":", 1)
# [-1]`) — MEDIDO: uma rota `name="balancete"` num SEGUNDO app com timbre
# (ex.: `tenancy:balancete`) colidia, pelo nome curto, com
# `contabilidade_web:balancete`; a chave curta ficava com QUALQUER uma
# das duas (a última varrida), a contagem continuava "3 telas", o piso
# continuava satisfeito, e o Balancete de verdade da contabilidade
# deixava de ser medido — em silêncio, com `exit 0`. O namespace existe
# justamente para permitir essa coexistência; jogá-lo fora ao montar a
# chave era o defeito.
TELAS_MINIMAS_COM_TIMBRE_ESPERADAS = frozenset(
    {"contabilidade_web:balancete", "contabilidade_web:diario", "contabilidade_web:razao"}
)


def _recusar(mensagem):
    """Saída de código `2` — FALHA DE INFRAESTRUTURA (ver a tabela de
    códigos de saída na docstring do módulo). `sys.exit(str)` sozinho
    sempre sai com código `1`, o MESMO código do achado de CONTEÚDO
    (`_reprovar_por_conteudo`, abaixo) — as duas coisas precisam ser
    distinguíveis por quem chama este script (BL-356/DL-028 fatia 2: é o
    job de integração contínua quem lê este código agora), então a saída
    de infraestrutura passa sempre por aqui, nunca por um `sys.exit(str)`
    direto. Par de `_reprovar_por_conteudo` — as duas funções existem
    lado a lado, com o MESMO formato, de propósito: a distinção entre os
    dois códigos é um contrato, não uma convenção espalhada em `sys.exit`
    soltos pelo arquivo (testado em
    `scripts/test_medir_identificacao_do_emitente.py`, sem Playwright nem
    Django)."""
    sys.stderr.write(f"Recusado: {mensagem}\n")
    sys.exit(2)


def _reprovar_por_conteudo(mensagem):
    """Saída de código `1` — achado sobre o PRODUTO (documento sem
    emitente completo), NUNCA sobre infraestrutura. Par de `_recusar`
    (acima) — ver o comentário de lá para o porquê da distinção existir
    como duas funções nomeadas em vez de `sys.exit` soltos."""
    sys.stderr.write(f"REPROVADO: {mensagem}\n")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Derivação do conjunto de telas — NUNCA uma lista escrita à mão (BL-363,
# resolvido aqui para o navegador real).
# ---------------------------------------------------------------------------

# Namespace de terceiro RECONHECIDO (não é "produto"): nunca carrega
# `.timbre-impressao`, e andar pelas suas ~dezenas de rotas (uma por
# modelo registrado) só adicionaria tempo de execução e ruído ao relatório
# de rotas puladas, sem chance de achar uma tela imprimível. Não é uma
# lista de TELAS (o que o BL-363 proíbe) — é a exclusão de um subsistema
# de terceiro já reconhecido em outras guardas deste projeto (ex.:
# apps/core/tests/test_dl019_varredura_de_contratos.py).
NAMESPACES_DE_TERCEIRO_IGNORADOS = {"admin"}


def _todas_as_rotas_get_nomeadas():
    """`[(nome_completo, {chaves_de_kwargs})]` para TODA rota nomeada da
    urlconf do projeto, andando recursivamente por `include()` — a mesma
    IDEIA de `apps/core/tests/test_dl019_varredura_de_contratos.py::
    _percorrer_callbacks` (não a mesma função: aquele módulo é teste,
    este é instrumento de bancada, e nenhum dos dois deveria depender do
    outro para enumerar rotas). Rota sem `name` é invisível a
    `django.urls.reverse` — não entra aqui, e portanto não é candidata a
    este instrumento (o mesmo furo do BL-334/H3 da rodada 8, fora do
    escopo desta etapa)."""
    from django.urls import get_resolver

    encontradas = []

    def percorrer(padroes, prefixo):
        for padrao in padroes:
            sub_padroes = getattr(padrao, "url_patterns", None)
            if sub_padroes is not None:
                namespace = getattr(padrao, "namespace", None)
                if namespace in NAMESPACES_DE_TERCEIRO_IGNORADOS:
                    continue
                novo_prefixo = f"{prefixo}{namespace}:" if namespace else prefixo
                percorrer(sub_padroes, novo_prefixo)
                continue
            nome = getattr(padrao, "name", None)
            if not nome:
                continue
            conversores = set(getattr(padrao.pattern, "converters", {}) or {})
            encontradas.append((f"{prefixo}{nome}", conversores))

    percorrer(get_resolver().url_patterns, "")
    return encontradas


def _descobrir_telas_com_timbre(cliente, empresa, conta):
    """DERIVA o conjunto de telas do produto que carregam
    `.timbre-impressao` — ver a docstring do módulo. Devolve
    `{nome_completo_da_rota: {"rota": ..., "url": ..., "html": ...}}` —
    chaveado pelo NOME COMPLETO (`namespace:nome`), não pelo nome curto
    (BL-374/J3: nome curto colide entre apps, ver o comentário de
    `TELAS_MINIMAS_COM_TIMBRE_ESPERADAS`). HTML já com o `href` do CSS
    reescrito para `file://`, via `medir_impressao._com_css_local` —
    reaproveitado, não reimplementado."""
    from django.urls import reverse

    kwargs_conhecidos = {"empresa_id": empresa.id, "conta_id": conta.id}
    periodo = f"?inicio={medir_impressao.PERIODO_INICIO}&fim={medir_impressao.PERIODO_FIM}"
    padrao_timbre = re.compile(r'class="[^"]*\btimbre-impressao\b[^"]*"')

    telas = {}
    puladas = []
    for nome_completo, chaves in _todas_as_rotas_get_nomeadas():
        if not chaves.issubset(kwargs_conhecidos):
            puladas.append((nome_completo, sorted(chaves - set(kwargs_conhecidos))))
            continue
        args = {k: kwargs_conhecidos[k] for k in chaves}
        try:
            url = reverse(nome_completo, kwargs=args)
        except Exception:  # noqa: BLE001 — rota não-reversível não é candidata
            continue

        resposta = cliente.get(url + periodo)
        if resposta.status_code != 200:
            continue
        html_da_tela = resposta.content.decode()
        if not padrao_timbre.search(html_da_tela):
            continue
        # BL-374 (achado J3 da nona auditoria): chave = NOME COMPLETO da
        # rota (`namespace:nome`), nunca o nome curto — ver o comentário
        # de `TELAS_MINIMAS_COM_TIMBRE_ESPERADAS` sobre a colisão medida.
        # `nome_completo` já É a identidade que `django.urls.reverse`
        # usa; reduzi-la aqui era o que jogava fora a informação que a
        # torna única.
        telas[nome_completo] = {
            "rota": nome_completo,
            "url": url,
            "html": medir_impressao._com_css_local(html_da_tela),
        }

    if puladas:
        print(
            f"AVISO (não é falha): {len(puladas)} rota(s) nomeada(s) puladas na "
            "varredura por precisarem de parâmetro que este instrumento não sabe "
            "preencher hoje (só empresa_id/conta_id são conhecidos) — uma tela "
            "nova que dependa só desses dois entraria sozinha; uma que dependa de "
            "outro parâmetro precisa de extensão deste script:",
            file=sys.stderr,
        )
        for nome, faltando in puladas:
            print(f"  - {nome}: falta {faltando}", file=sys.stderr)

    return telas


# ---------------------------------------------------------------------------
# Medição no navegador (subprocesso do Python do sistema, com Playwright) —
# mesma separação de `medir_impressao.py`.
# ---------------------------------------------------------------------------

_SCRIPT_DO_SUBPROCESSO = r"""
import json, sys
from pathlib import Path

especificacao = json.loads(sys.argv[1])
sys.path.insert(0, especificacao["diretorio_sonda"])
import sonda_visibilidade
from playwright.sync_api import sync_playwright

pasta_html = Path(especificacao["pasta_html"])
pasta_saida = Path(especificacao["pasta_saida"])
pasta_saida.mkdir(parents=True, exist_ok=True)
sonda = sonda_visibilidade.js_sonda_container_e_filhos(
    especificacao["seletor_container"], especificacao["seletor_filhos"]
)

resultados = {}
erro_infra = None
try:
    with sync_playwright() as p:
        navegador = sonda_visibilidade.lancar_chromium(p)
        pagina = navegador.new_page()
        for nome in especificacao["telas"]:
            try:
                # BL-374 (achado J3): `nome` agora É o nome COMPLETO da
                # rota (`namespace:nome`) — mantido como chave de
                # `resultados` sem alteração (é a identidade), mas ":"
                # não é ideal em nome de arquivo em todo sistema; só o
                # NOME DE ARQUIVO troca ":" por "_", nunca a chave.
                nome_arquivo = nome.replace(":", "_")
                pagina.goto(
                    (pasta_html / f"{nome_arquivo}.html").as_uri(), wait_until="networkidle"
                )
                # Espera a troca de font-display: swap terminar (BL-347/F5,
                # o mesmo cuidado de medir_impressao.py) -- texto medido
                # ANTES da troca ainda é visivel/legivel, mas a altura de
                # linha pode diferir; nao afeta a pergunta deste script
                # (existe/esta visivel), so a mantem consistente com o
                # resto do projeto.
                pagina.evaluate("() => document.fonts.ready.then(() => true)")
                pagina.emulate_media(media="print")
                medida = pagina.evaluate(sonda)
                pagina.pdf(
                    path=str(pasta_saida / f"{nome_arquivo}.pdf"),
                    format="A4",
                    display_header_footer=False,
                    margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
                )
                pagina.emulate_media(media=None)
                resultados[nome] = medida
            except Exception as erro:
                resultados[nome] = {"erro": f"{type(erro).__name__}: {erro}"}
        navegador.close()
except sonda_visibilidade.NavegadorIndisponivel as erro:
    erro_infra = f"{erro}"

print(json.dumps({"resultados": resultados, "erro_infra": erro_infra}, ensure_ascii=False))
"""


def _medir_no_navegador(pasta_html, pasta_saida, nomes_das_telas):
    especificacao = json.dumps(
        {
            "diretorio_sonda": _DIRETORIO_SONDA,
            "pasta_html": str(pasta_html),
            "pasta_saida": str(pasta_saida),
            "telas": nomes_das_telas,
            "seletor_container": SELETOR_TIMBRE_CONTAINER,
            "seletor_filhos": SELETOR_TIMBRE_FILHOS,
        }
    )
    resultado = subprocess.run(
        [medir_impressao.PYTHON_DO_SISTEMA, "-c", _SCRIPT_DO_SUBPROCESSO, especificacao],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        _recusar(
            "a medição no navegador (subprocesso do Python do sistema) "
            f"terminou com código {resultado.returncode}.\n"
            f"saida padrao: {resultado.stdout}\nerro: {resultado.stderr}"
        )
    try:
        saida = json.loads(resultado.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        _recusar(
            "a saída do subprocesso de medição não é o JSON esperado.\n"
            f"Detalhe: {exc}\nsaida bruta: {resultado.stdout!r}"
        )
    if saida.get("erro_infra"):
        _recusar(str(saida["erro_infra"]))
    return saida["resultados"]


def _verificar_sonda_disponivel():
    """Confirma cedo, na venv do projeto (sem precisar de Playwright), que
    `sonda_visibilidade.py` existe e importa sem erro de sintaxe — em vez
    de deixar um `_DIRETORIO_SONDA` errado só se manifestar como erro dentro
    do subprocesso do Python do sistema, três camadas depois."""
    import importlib.util

    caminho = Path(_DIRETORIO_SONDA) / "sonda_visibilidade.py"
    especificacao = importlib.util.spec_from_file_location("sonda_visibilidade", caminho)
    if especificacao is None or especificacao.loader is None:
        _recusar(f"não encontrei {caminho}.")
    modulo = importlib.util.module_from_spec(especificacao)
    try:
        especificacao.loader.exec_module(modulo)
    except Exception as erro:  # noqa: BLE001 — reportado, não engolido
        _recusar(f"{caminho} não importa: {type(erro).__name__}: {erro}")


def _texto_do_pdf(caminho_pdf):
    """Texto do PDF inteiro, espaço normalizado — mesma técnica de
    `medir_impressao.py` (`-layout`, depois `re.sub(r"\\s+", " ", ...)`),
    não reimplementada com outra assinatura.

    BL-378 (achado J7 da nona auditoria): `check=False` — um `pdftotext`
    PRESENTE no PATH mas QUEBRADO (biblioteca do sistema faltando, PDF
    corrompido por um bug do Chromium, I/O) é FALHA DE INFRAESTRUTURA,
    nunca veredito sobre o produto. Antes desta correção, `check=True`
    deixava o `CalledProcessError` subir sem tratamento, `main` morria com
    código `1` — o MESMO código de "o produto saiu sem identificação
    completa" — e o job de integração contínua anunciava exatamente essa
    frase para uma falha que não tinha nada a ver com o timbre. MEDIDO:
    `pdftotext` quebrado no PATH produzia esse anúncio falso antes desta
    correção."""
    resultado = subprocess.run(
        ["pdftotext", "-layout", str(caminho_pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        _recusar(
            f"'pdftotext -layout' falhou (código {resultado.returncode}) ao "
            f"processar {caminho_pdf} — falha de infraestrutura (poppler-utils "
            f"quebrado, PDF corrompido, I/O), não veredito sobre o produto.\n"
            f"erro: {resultado.stderr}"
        )
    return re.sub(r"\s+", " ", resultado.stdout).strip()


# ---------------------------------------------------------------------------
# Oráculo do papel (BL-372, achado J1 da nona auditoria) — "tem tinta
# ESCURA na faixa onde a linha do timbre deveria estar?" Ver o parágrafo
# correspondente na docstring do módulo para o raciocínio completo; os
# comentários abaixo cobrem só as decisões de CADA função.
# ---------------------------------------------------------------------------

DPI_ORACULO_DO_PAPEL = 96
"""96 é a própria DEFINIÇÃO de "pixel CSS" (1 CSS px = 1/96 polegada —
CSS Values and Units Module, §5.2): rasterizar a folha exatamente nesta
resolução converte ponto de PDF (1/72 polegada, `PONTOS_POR_POLEGADA`
abaixo) para pixel de raster com UM fator só (`dpi/72`). Não depende do
retângulo que `sonda_visibilidade` mede no NAVEGADOR antes de gerar o
PDF — ver `_palavras_da_pagina` sobre por quê."""

PONTOS_POR_POLEGADA = 72.0

# MEDIDO ao construir este oráculo (exigência do arquiteto-senior: piso e
# limiar precisam de medição, não intuição) — script e evidência completa
# no relatório da etapa. Contra a base semeada por
# `scripts/semear_base_de_medicao.py` (três linhas de timbre, três
# telas): o CONTROLE limpo nunca desceu de 329 pixels escuros numa linha
# (a menor: "CRC-TO 000000/O-0 (sintético)" no Balancete); um controle
# NEGATIVO plausível (`letter-spacing: 0.01em` no timbre, que não some
# tinta nenhuma) mediu 329-620. TODA construção testada que efetivamente
# apaga a tinta sem remover o objeto de texto do PDF — `color: var(
# --papel-elevado)` no contêiner, no `<p>` e em `.conteudo-principal`;
# `-webkit-text-stroke: 0` combinado com a mesma cor; `opacity: 0.02` —
# mediu EXATAMENTE ZERO pixel escuro. A margem entre "zero" e "329" é de
# duas ordens de grandeza: o piso NÃO é frágil (nenhum controle limpo
# ficou perto do limite). `clip-path: inset(100%)` e `.timbre-impressao p
# { text-indent: -9999px }` nem chegam a esta contagem — o Chromium não
# escreve objeto de texto nenhum para elas, e a linha já reprova antes,
# por `_bbox_da_linha` devolver `None` (o mesmo sinal que `presente_no_pdf`
# já usa). `mix-blend-mode: screen` foi MEDIDO e NÃO some a tinta no PDF
# exportado (626/350/318 pixels — o mesmo patamar do controle): o backend
# Skia PDF do Chromium não aplica composição de blend mode na exportação
# de impressão, então esta construção PASSA — corretamente, porque a
# tinta realmente chega ao papel.
PISO_PIXELS_ESCUROS_POR_LINHA = 40

# Ponto médio da escala de cinza de 8 bits (0 preto, 255 branco). A tinta
# de impressão do produto é `--impressao-tinta: #000000` — preto puro,
# `static/css/base.css` — então qualquer limiar bem afastado dos dois
# extremos separa tinta de papel; o meio da escala é a escolha mais
# simples de justificar, e NENHUMA medição feita para calibrar este
# oráculo produziu um pixel de linha do timbre entre 1 e 254: ou a tinta
# está lá (grupos de pixel em 0, por antialiasing subindo a poucas
# dezenas acima disso) ou não está (grupo em 255).
LIMIAR_LUMINANCIA_TINTA = 128

_PADRAO_PALAVRA_BBOX = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
)


def _palavras_da_pagina(caminho_pdf, pagina=1):
    """Lista `(xmin, ymin, xmax, ymax, texto)`, em PONTOS de PDF, de cada
    palavra da página `pagina` — via `pdftotext -bbox` (poppler-utils, JÁ
    dependência de sistema deste projeto; nenhuma lib nova). Ao contrário
    do texto plano que `_texto_do_pdf` extrai, o bbox devolve a POSIÇÃO do
    objeto de texto no PDF — que existe mesmo quando a tinta é da MESMA
    cor do papel (`color: transparent`/`color: var(--papel-elevado)`): o
    glifo continua sendo um objeto de texto posicionado, só não pinta
    pixel escuro nenhum. É esse descolamento entre "o objeto de texto
    existe, aqui" e "há tinta ESCURA aqui" que `_pixels_escuros_na_faixa`
    fecha.

    MEDIDO ao construir este oráculo — e por isso a escolha do bbox do
    PRÓPRIO PDF em vez do retângulo que `sonda_visibilidade` devolve do
    NAVEGADOR: a posição de uma palavra no PDF exportado por `page.pdf()`
    é a MESMA independente da largura do viewport interativo usado para
    medi-la (conferido: dois PDFs gerados com viewport de 1280px e de
    794px de largura têm coordenadas de bbox byte-a-byte IDÊNTICAS) — a
    exportação de impressão do Chromium pagina pelo tamanho do PAPEL, não
    pelo do viewport interativo. Um retângulo medido por
    `getBoundingClientRect` ANTES de gerar o PDF não tem essa garantia:
    MEDIDO, o mesmo elemento aparece até ~15px mais acima ou mais abaixo
    no PDF do que a medição do navegador previa, variando por TELA
    conforme a altura do cabeçalho de cada uma — o bbox do PDF não tem
    essa incerteza porque é a posição REAL, não uma previsão.

    BL-378: `check=False` — `pdftotext -bbox` quebrado é a MESMA classe de
    falha de infraestrutura que `_texto_do_pdf` já trata."""
    resultado = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(pagina), "-l", str(pagina), str(caminho_pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        _recusar(
            f"'pdftotext -bbox' falhou (código {resultado.returncode}) ao "
            f"processar {caminho_pdf} — falha de infraestrutura, não veredito "
            f"sobre o produto.\nerro: {resultado.stderr}"
        )
    return [
        (float(a), float(b), float(c), float(d), html.unescape(e))
        for a, b, c, d, e in _PADRAO_PALAVRA_BBOX.findall(resultado.stdout)
    ]


def _bbox_da_linha(palavras, texto_esperado):
    """Encontra, dentro de `palavras` (na ordem devolvida por
    `_palavras_da_pagina`), a sequência CONTÍGUA de palavras cuja
    concatenação — sem espaço, dos dois lados da comparação — reproduz
    `texto_esperado`. Sem espaço porque `pdftotext -bbox` tokeniza por
    caractere de espaço VISUAL, que nem sempre bate 1:1 com `str.split()`
    do Python (pontuação colada a uma palavra pode virar um token à
    parte, dependendo da fonte) — MEDIDO com as duas linhas sintéticas de
    `scripts/semear_base_de_medicao.py` (endereço com vírgula e hífen;
    registro com parênteses): as duas casaram sem precisar de nenhuma
    normalização além desta.

    Devolve `(xmin, ymin, xmax, ymax)` em PONTOS de PDF — a caixa UNIÃO
    das palavras encontradas — ou `None` se a sequência não aparece na
    página: o MESMO sinal de "esta linha não está no papel" que
    `presente_no_pdf` já usa (texto removido do DOM inteiramente, ex.:
    `display: none`, ou recortado por completo, ex.: `clip-path:
    inset(100%)` — MEDIDO: o Chromium não escreve objeto de texto nenhum
    para um elemento assim recortado)."""
    alvo = "".join(texto_esperado.split())
    if not alvo:
        return None
    total = len(palavras)
    for inicio in range(total):
        acumulado = ""
        for fim in range(inicio, total):
            acumulado += "".join(palavras[fim][4].split())
            if acumulado == alvo:
                grupo = palavras[inicio : fim + 1]
                return (
                    min(p[0] for p in grupo),
                    min(p[1] for p in grupo),
                    max(p[2] for p in grupo),
                    max(p[3] for p in grupo),
                )
            if len(acumulado) > len(alvo):
                break
    return None


def _rasterizar_primeira_pagina(caminho_pdf, dpi=DPI_ORACULO_DO_PAPEL):
    """Rasteriza a PRIMEIRA página do PDF para tons de cinza (PGM binário
    `P5`) via `pdftoppm -gray` — a MESMA dependência de sistema
    (poppler-utils) que `_texto_do_pdf`/`_palavras_da_pagina` já exigem;
    NENHUMA biblioteca de imagem nova em `requirements/` (mesma decisão
    registrada na docstring de `scripts/medir_impressao.py` para não
    acrescentar lib de PDF). `-singlefile` evita o poppler acrescentar
    sufixo numérico ao nome de saída, já que só pedimos uma página.

    O timbre está sempre na primeira folha, nas três telas hoje (MEDIDO).
    Se um documento futuro empurrar o timbre para depois da folha 1, esta
    função precisa de um parâmetro de página — não é uma limitação
    escondida, é a MESMA que `_texto_do_pdf`/`_palavras_da_pagina` já têm
    ao não receber número de página nenhum.

    BL-378: `pdftoppm` quebrado é a MESMA classe de falha de
    infraestrutura que os dois acima."""
    with tempfile.TemporaryDirectory(prefix="dl-oraculo-papel-") as pasta:
        prefixo = Path(pasta) / "pagina"
        resultado = subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(dpi),
                "-f",
                "1",
                "-l",
                "1",
                "-gray",
                "-singlefile",
                str(caminho_pdf),
                str(prefixo),
            ],
            capture_output=True,
        )
        if resultado.returncode != 0:
            _recusar(
                f"'pdftoppm -gray' falhou (código {resultado.returncode}) ao "
                f"rasterizar {caminho_pdf} — falha de infraestrutura.\n"
                f"erro: {resultado.stderr.decode(errors='replace')}"
            )
        return (prefixo.with_suffix(".pgm")).read_bytes()


def _pgm_para_matriz(dados_pgm):
    """Parseia um PGM BINÁRIO (`P5`) sem depender de Pillow nem de
    nenhuma lib de imagem — é exatamente o formato que `pdftoppm -gray`
    produz nativamente (8 bits: `maxval < 256`, sempre o caso aqui), 1
    byte por pixel, 0 = preto, 255 = branco. Devolve `(largura, altura,
    corpo_de_bytes)`. Função PURA — testada em
    `scripts/test_medir_identificacao_do_emitente.py` com bytes
    sintéticos, sem chamar `pdftoppm` de verdade."""
    if not dados_pgm.startswith(b"P5"):
        raise ValueError("dados não começam com a assinatura PGM binária 'P5'")
    pos = 2
    campos = []
    # Cabeçalho PGM: três inteiros (largura, altura, maxval) separados por
    # espaço em branco — comentários `#...\n` são permitidos pelo formato
    # entre tokens; ignorados aqui se aparecerem (poppler não os emite,
    # mas o formato PERMITE, e um parser que quebra num comentário válido
    # é um parser errado, não um limite documentado).
    while len(campos) < 3:
        while dados_pgm[pos : pos + 1].isspace():
            pos += 1
        if dados_pgm[pos : pos + 1] == b"#":
            pos = dados_pgm.index(b"\n", pos) + 1
            continue
        inicio = pos
        while not dados_pgm[pos : pos + 1].isspace():
            pos += 1
        campos.append(int(dados_pgm[inicio:pos]))
    largura, altura, maxval = campos
    if maxval >= 256:
        raise ValueError(f"PGM com maxval {maxval} >= 256 (16 bits) não é suportado")
    pos += 1  # o único espaço em branco exigido pelo formato após o maxval
    corpo = dados_pgm[pos : pos + largura * altura]
    if len(corpo) < largura * altura:
        raise ValueError(
            f"PGM truncado: esperava {largura * altura} bytes de pixel, achei {len(corpo)}"
        )
    return largura, altura, corpo


def _pixels_escuros_na_faixa(dados_pgm, retangulo_pt, dpi=DPI_ORACULO_DO_PAPEL, margem_px=2):
    """Conta pixels com luminância <= `LIMIAR_LUMINANCIA_TINTA` dentro do
    retângulo `(xmin, ymin, xmax, ymax)` — em PONTOS de PDF, convertido
    para pixel do raster por `dpi/72` (ver `DPI_ORACULO_DO_PAPEL`).
    `margem_px` expande a caixa igualmente nos quatro lados: absorve só o
    arredondamento do `int()` e a folga do antialiasing do glifo — NÃO é
    o que separa tinta de sabotagem (isso é o LIMIAR de luminância e o
    PISO de contagem, ambos acima); é para não cortar 1px do próprio
    glifo por arredondamento. MEDIDO ao construir este oráculo: margem de
    2px não alcança a linha vizinha em nenhuma das três telas (a menor
    distância entre duas linhas do timbre medida foi de ~17px)."""
    largura_pagina, altura_pagina, corpo = _pgm_para_matriz(dados_pgm)
    fator = dpi / PONTOS_POR_POLEGADA
    xmin, ymin, xmax, ymax = retangulo_pt
    x0 = max(0, int(xmin * fator) - margem_px)
    y0 = max(0, int(ymin * fator) - margem_px)
    x1 = min(largura_pagina, int(xmax * fator) + margem_px + 1)
    y1 = min(altura_pagina, int(ymax * fator) + margem_px + 1)
    contagem = 0
    for y in range(y0, y1):
        inicio_da_linha = y * largura_pagina
        for x in range(x0, x1):
            if corpo[inicio_da_linha + x] <= LIMIAR_LUMINANCIA_TINTA:
                contagem += 1
    return contagem


_PADRAO_COR_RGBA = re.compile(r"[\d.]+")


def _tinta_invisivel(cor_css):
    """`True` quando `cor_css` (o `getComputedStyle(...).color` bruto, ex.:
    `"rgba(0, 0, 0, 0)"`) tem alfa ZERO — "tinta" que não pinta pixel
    nenhum. Fecha o limite que `visivelDeVerdade` já declara por escrito
    (ver o comentário em `sonda_visibilidade.js_sonda_container_e_filhos`):
    `color: transparent` MEDIDO nesta etapa: não muda `checkVisibility()`,
    não zera a área, e o texto AINDA aparece no `pdftotext` — o glifo é
    pintado (com tinta transparente), `pdftotext` lê o OBJETO de texto do
    PDF, não o pixel renderizado. Sem esta checagem, `.timbre-impressao {
    color: transparent }` passaria pelas duas medições deste script
    (visibilidade E texto do PDF) — falso negativo medido, não hipotético,
    ao construir este instrumento."""
    numeros = [float(n) for n in _PADRAO_COR_RGBA.findall(cor_css or "")]
    return len(numeros) >= 4 and numeros[3] == 0


def _com_saida_de_infraestrutura(func, *args, **kwargs):
    """Chama uma rotina `_exigir_*`/`_preparar_*` REAPROVEITADA de
    `medir_impressao.py` — que sai com `sys.exit(str)` (código `1`) em
    caso de falha — e RENORMALIZA a saída para código `2`, preservando a
    mensagem original. Sem isto, uma falha de infraestrutura vinda de uma
    função reaproveitada sairia com o MESMO código do achado de CONTEÚDO
    (REPROVADO, no fim de `main`), quebrando a distinção que este script
    promete na própria docstring (BL-356)."""
    try:
        return func(*args, **kwargs)
    except SystemExit as erro:
        if erro.code not in (0, None):
            sys.stderr.write(f"{erro.code}\n")
            sys.exit(2)
        raise


# ---------------------------------------------------------------------------
# Orquestração.
# ---------------------------------------------------------------------------


def main(argv):
    inicio = time.monotonic()

    _com_saida_de_infraestrutura(medir_impressao._exigir_ferramentas_de_pdf)
    _com_saida_de_infraestrutura(medir_impressao._exigir_python_do_sistema_com_playwright)
    _verificar_sonda_disponivel()

    pasta_informada = None
    filtro_telas = None
    for arg in argv:
        if arg.startswith("--telas="):
            filtro_telas = set(arg.removeprefix("--telas=").split(","))
        else:
            pasta_informada = Path(arg).resolve()

    cliente, empresa, conta = _com_saida_de_infraestrutura(
        medir_impressao._preparar_cliente_e_cenario_de_medicao
    )
    escritorio = empresa.escritorio
    # Contrato ÚNICO servidor→template (Escritorio.linhas_do_timbre, ver
    # apps/tenancy/models.py) -- as linhas ESPERADAS no papel vêm do MESMO
    # método que o template usa para desenhá-las, nunca de um literal
    # reescrito aqui (duas fontes do mesmo texto divergem, AGENTS.md §8).
    linhas_esperadas = [linha.strip() for linha in escritorio.linhas_do_timbre]
    if not linhas_esperadas:
        _recusar(
            "Escritorio.linhas_do_timbre devolveu lista vazia para a base "
            "semeada — contrato quebrado (o método nunca deveria devolver vazio)."
        )

    telas = _descobrir_telas_com_timbre(cliente, empresa, conta)
    if not telas:
        _recusar(
            "a varredura de rotas não achou NENHUMA tela com "
            "'.timbre-impressao' — o produto tem pelo menos três (Balancete, "
            "Diário, Razão), então isto é sinal de regressão na urlconf, no "
            "HTML ou na varredura em si, não ausência real. Investigue antes "
            "de confiar em qualquer resultado deste instrumento."
        )
    print(
        f"telas derivadas com timbre ({len(telas)}): {', '.join(sorted(telas))}",
        file=sys.stderr,
    )

    # Piso de regressão (ver o comentário de TELAS_MINIMAS_COM_TIMBRE_
    # ESPERADAS): computado sobre o conjunto DERIVADO completo, sempre —
    # independente de `--telas=`, que é um filtro de CONVENIÇÃO de bancada
    # para a medição no navegador, não para esta checagem (barata, sem
    # navegador nenhum). Uma tela do piso que a varredura NÃO achou vira
    # reprovação de CONTEÚDO nomeada, mesmo sem HTML nenhum para medir —
    # é exatamente o caso em que não HÁ HTML com o marcador para medir.
    telas_do_piso_ausentes = sorted(TELAS_MINIMAS_COM_TIMBRE_ESPERADAS - telas.keys())
    reprovacoes_do_piso = [
        f"{nome}: tela do piso mínimo (critério 3 da DL-026) NÃO encontrada pela "
        "varredura — o timbre pode ter sido removido inteiro do template, não só "
        "escondido por CSS"
        for nome in telas_do_piso_ausentes
    ]

    nomes_para_medir = sorted(telas if filtro_telas is None else (telas.keys() & filtro_telas))
    if filtro_telas and not nomes_para_medir:
        _recusar(
            f"--telas={sorted(filtro_telas)} não bate com nenhuma tela derivada ({sorted(telas)})."
        )

    with tempfile.TemporaryDirectory(prefix="dl-medir-emitente-") as pasta_temp:
        pasta_html = Path(pasta_temp) / "html"
        pasta_html.mkdir()
        for nome in nomes_para_medir:
            # BL-374: só o NOME DE ARQUIVO troca ":" por "_" — a chave
            # `nome` (nome completo da rota) segue intacta em todo o
            # resto (ver o comentário equivalente em
            # `_SCRIPT_DO_SUBPROCESSO`, que constrói o MESMO nome de
            # arquivo do lado do Playwright).
            (pasta_html / f"{nome.replace(':', '_')}.html").write_text(
                telas[nome]["html"], encoding="utf-8"
            )

        pasta_saida = pasta_informada or (Path(pasta_temp) / "pdfs")
        pasta_saida.mkdir(parents=True, exist_ok=True)

        resultados_navegador = _medir_no_navegador(pasta_html, pasta_saida, nomes_para_medir)

        relatorio = {}
        reprovacoes = []
        for nome in nomes_para_medir:
            medida = resultados_navegador.get(nome, {})
            entrada = {
                "url": telas[nome]["url"],
                "rota": telas[nome]["rota"],
                "medicao_navegador": medida,
            }
            relatorio[nome] = entrada

            if "erro" in medida:
                # BL-378 (achado J7): erro de NAVEGAÇÃO/MEDIÇÃO (timeout de
                # `goto`, aba travada, exceção do Playwright) é falha de
                # INFRAESTRUTURA, nunca veredito sobre o produto — "não
                # consegui medir esta tela" não é "a tela saiu sem
                # emitente". Antes desta correção isto virava uma
                # REPROVAÇÃO de conteúdo (código 1) acumulada em
                # `reprovacoes`, e o job anunciava a frase errada. Recusa
                # AQUI, imediatamente: sem confiança na medição desta
                # tela, não há por que seguir medindo as demais.
                _recusar(f"{nome}: erro de navegação/medição — {medida['erro']}")

            caminho_pdf = pasta_saida / f"{nome.replace(':', '_')}.pdf"
            texto_pdf = _texto_do_pdf(caminho_pdf) if caminho_pdf.exists() else ""
            # Oráculo do papel (BL-372/J1, ver a docstring do módulo):
            # posição REAL de cada palavra no PDF exportado (independente
            # da cor com que foi pintada) e o raster em tons de cinza da
            # mesma folha, para exigir tinta ESCURA onde o texto deveria
            # estar — não só "o objeto de texto existe" (`_texto_do_pdf`)
            # nem "o alfa não é zero" (`_tinta_invisivel`, abaixo).
            palavras_pdf = _palavras_da_pagina(caminho_pdf) if caminho_pdf.exists() else []
            dados_pgm_da_pagina = (
                _rasterizar_primeira_pagina(caminho_pdf) if caminho_pdf.exists() else None
            )
            entrada["pdf"] = str(caminho_pdf)
            entrada["pdf_contem_marca_do_fornecedor"] = MARCA_DO_FORNECEDOR in texto_pdf

            motivos = []
            if not medida.get("encontrado"):
                motivos.append("container '.timbre-impressao' não encontrado no HTML")
            elif not medida.get("visivel"):
                motivos.append("container '.timbre-impressao' NÃO visível sob impressão")
            elif _tinta_invisivel(medida.get("cor_efetiva")):
                motivos.append(
                    "container '.timbre-impressao' com tinta de alfa zero "
                    f"({medida.get('cor_efetiva')!r}) — visível por layout, ilegível na prática"
                )

            filhos = medida.get("filhos", [])
            linhas_no_pdf = {}
            for linha in linhas_esperadas:
                filho_da_linha = next(
                    (f for f in filhos if f.get("texto", "").strip() == linha), None
                )
                visivel_no_navegador = bool(filho_da_linha and filho_da_linha.get("visivel"))
                legivel = visivel_no_navegador and not _tinta_invisivel(
                    filho_da_linha.get("cor_efetiva") if filho_da_linha else None
                )
                presente_no_pdf = linha in texto_pdf

                # Oráculo do papel: onde esta linha REALMENTE está no PDF
                # exportado (bbox, em pontos — existe mesmo se a tinta for
                # da cor do papel) e quantos pixels ESCUROS aparecem ali
                # na folha rasterizada. `bbox_no_pdf is None` é o MESMO
                # sinal que `presente_no_pdf=False` (texto removido do
                # DOM ou recortado por completo) — não duplicamos o
                # motivo quando os dois já apontam pra a mesma ausência.
                bbox_no_pdf = _bbox_da_linha(palavras_pdf, linha)
                if bbox_no_pdf is not None and dados_pgm_da_pagina is not None:
                    pixels_escuros = _pixels_escuros_na_faixa(dados_pgm_da_pagina, bbox_no_pdf)
                else:
                    pixels_escuros = 0
                tinta_visivel_no_papel = pixels_escuros >= PISO_PIXELS_ESCUROS_POR_LINHA

                linhas_no_pdf[linha] = {
                    "visivel_no_navegador": visivel_no_navegador,
                    "legivel": legivel,
                    "presente_no_pdf": presente_no_pdf,
                    "pixels_escuros_no_papel": pixels_escuros,
                    "tinta_visivel_no_papel": tinta_visivel_no_papel,
                }
                if not visivel_no_navegador:
                    motivos.append(f"linha do timbre NÃO visível sob impressão: {linha!r}")
                elif not legivel:
                    motivos.append(f"linha do timbre com tinta de alfa zero (ilegível): {linha!r}")
                if not presente_no_pdf:
                    motivos.append(f"linha do timbre AUSENTE do texto do PDF: {linha!r}")
                elif not tinta_visivel_no_papel:
                    # BL-372/J1: a linha ESTÁ no texto do PDF (objeto de
                    # texto presente) mas a folha rasterizada não mostra
                    # tinta escura onde ele deveria estar — o caso exato
                    # de `color: var(--papel-elevado)` (branco opaco:
                    # alfa 1, `_tinta_invisivel` não pega) e de qualquer
                    # construção futura que pinte a tinta da cor do papel.
                    motivos.append(
                        "linha do timbre SEM TINTA ESCURA suficiente no papel "
                        f"rasterizado (oráculo do pixel): {linha!r} — "
                        f"{pixels_escuros} pixel(s) escuro(s) na faixa esperada, "
                        f"piso exigido {PISO_PIXELS_ESCUROS_POR_LINHA}"
                    )
            entrada["linhas_do_timbre"] = linhas_no_pdf

            if entrada["pdf_contem_marca_do_fornecedor"]:
                motivos.append(f"marca do fornecedor ({MARCA_DO_FORNECEDOR!r}) presente no PDF")

            entrada["veredito"] = "PASSOU" if not motivos else "REPROVADO"
            entrada["motivos"] = motivos
            if motivos:
                reprovacoes.append(f"{nome}: {'; '.join(motivos)}")

        for nome in telas_do_piso_ausentes:
            relatorio[nome] = {
                "url": None,
                "rota": None,
                "veredito": "AUSENTE (piso mínimo)",
                "motivos": [
                    "tela do piso mínimo (critério 3 da DL-026) não encontrada pela varredura"
                ],
            }
        reprovacoes = reprovacoes_do_piso + reprovacoes

        tempo = time.monotonic() - inicio
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        for nome, entrada in relatorio.items():
            print(f"{nome}: {entrada['veredito']} — {entrada['url']}")
        print(f"\ntempo de execução: {tempo:.1f}s", file=sys.stderr)
        if pasta_informada:
            print(f"PDFs preservados em: {pasta_informada}", file=sys.stderr)

        if reprovacoes:
            total_telas_consideradas = len(nomes_para_medir) + len(telas_do_piso_ausentes)
            detalhe = "\n".join(f"  - {linha}" for linha in reprovacoes)
            _reprovar_por_conteudo(
                f"{len(reprovacoes)} de {total_telas_consideradas} tela(s) sem "
                f"identificação completa do emitente no papel:\n{detalhe}"
            )


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as erro:  # noqa: BLE001 — BL-378 (achado J7): um
        # traceback NÃO PREVISTO (bug deste script, exceção de biblioteca
        # não tratada em nenhum ponto acima) nunca deve sair com o MESMO
        # código de "o produto saiu sem identificação completa" (`1`,
        # `_reprovar_por_conteudo`) — quem lê o código de saída do job
        # precisa poder confiar que `1` é sempre um achado sobre o
        # PRODUTO. `_recusar` (código `2`) preserva o tipo e a mensagem
        # originais da exceção para investigação, sem fingir veredito.
        _recusar(f"exceção não prevista ({type(erro).__name__}): {erro}")
