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
`_rasterizar_pagina`), localiza a posição REAL de cada linha do
timbre no PDF exportado (`pdftotext -bbox`, ver `_palavras_da_pagina` e
`_bbox_da_linha`/`_localizar_bloco_do_timbre` — a posição de um objeto de
texto no PDF não depende da cor com que ele foi pintado) e exige uma
contagem de pixels com CONTRASTE suficiente contra o papel acima de um
piso medido (`_diagnostico_de_contraste_na_faixa`,
`PISO_PIXELS_ESCUROS_POR_LINHA` — DL-029, C2: contraste MEDIDO contra o
fundo da própria folha, contra um piso do WCAG 2.2 aplicado POR LINHA,
não um limiar fixo de luminância nem uma razão única escolhida a dedo.
Ver o comentário de `RAZAO_MINIMA_WCAG_TEXTO_NORMAL`). É a pergunta do
contador — "tem tinta que CONTRASTA com o papel onde deveria ter?" — e
ela SOMA às checagens anteriores (DOM: `checkVisibility` +
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

# ---------------------------------------------------------------------------
# C5 da DL-029 (docs/planos/DL-029-a-frase-executavel-do-criterio-9.md) —
# "não carrega nenhum identificador do fornecedor do software, em qualquer
# caixa ou espaçamento". Fecha o K1/BL-404 (bloqueador da décima
# auditoria, docs/auditorias/2026-09-20-dl-026-dl-028-rodada-10.md):
# `MARCA_DO_FORNECEDOR = "DataLedger"` era uma LISTA DE UM ITEM (a mesma
# forma proibida pela DE-056), comparada por SUBSTRING sensível a caixa —
# `"DataLedger" in texto_pdf` não fecha `"DATALEDGER"`, `"Data Ledger"` nem
# `"D a t a L e d g e r"`, e a marca do fornecedor voltou ao papel do
# Balancete com a suíte inteira verde E com este instrumento em `exit 0`.
#
# A correção tem DUAS frentes, na ordem em que o K1 as pediu:
#
# 1. DERIVAR o identificador de UMA fonte, nunca repeti-lo aqui
#    (AGENTS.md §8: duas cópias do mesmo texto divergem assim que uma for
#    editada sem a outra) — `_derivar_marca_do_fornecedor`, abaixo, lê
#    `templates/base.html`.
# 2. Perguntar por PROPRIEDADE (ausência normalizada: caixa, espaço,
#    pontuação e separadores desprezados), não por substring literal —
#    `_normalizar_para_busca_do_fornecedor`, abaixo.
_CAMINHO_BASE_HTML = RAIZ / "templates" / "base.html"

# `<title>{% block titulo %}DataLedger{% endblock %}{% block
# titulo_sufixo_do_fornecedor %} — DataLedger{% endblock %}</title>` —
# grupo 1 captura o CONTEÚDO PADRÃO do primeiro bloco (o nome sozinho,
# sem o traço do sufixo).
_PADRAO_TITULO_PADRAO = re.compile(r"<title>\{% block titulo %\}([^{<]+)\{% endblock %\}")

# `<a href="{% url 'tenancy:painel' %}">DataLedger<span
# class="marca__ponto">.</span></a>` dentro de `<div class="marca">` —
# grupo 1 captura o texto entre o fechamento da tag `<a ...>` e o `<span
# class="marca__ponto">` que seria o ponto final da marca.
_PADRAO_MARCA = re.compile(
    r'<div class="marca">.*?<a[^>]*>([^<]+)<span class="marca__ponto">', re.DOTALL
)


def _derivar_marca_do_fornecedor():
    """Lê o identificador do fornecedor de ONDE O PRODUTO O ESCREVE —
    `templates/base.html`, nos dois lugares que a décima auditoria (K1)
    nomeou: o conteúdo PADRÃO do bloco `titulo` (a tag `<title>` das telas
    sem cliente no contexto) e o texto de `.marca` (o link "DataLedger."
    do cabeçalho). NUNCA um literal repetido aqui — é exatamente a lista
    de um item que o K1 encontrou (BL-404).

    As DUAS fontes precisam CONCORDAR: se um dia alguém trocar o nome só
    em um dos dois lugares, este instrumento não pode continuar medindo
    contra um valor que já não corresponde aos DOIS pontos onde o produto
    de fato o escreve — prefere RECUSAR (infraestrutura, código 2; não é
    veredito sobre o produto) a escolher um dos dois em silêncio, que é
    exatamente o que a DE-056 proíbe ("limite declarado não é limite
    fechado" só vale quando o limite é DECLARADO, não quando é escondido
    por uma escolha arbitrária).

    ACHADO PRÓPRIO, registrado no relatório desta etapa e não corrigido
    aqui (fora do escopo da DL-029: `templates/**` é proibido a este
    instrumento): a string "DataLedger" aparece em MAIS de dois lugares do
    produto — além de `<title>`/`.marca` em `templates/base.html`, também
    em `templates/tenancy/primeiro_acesso.html` ("Bem-vindo ao
    DataLedger"), sem nenhuma das duas fontes que este método deriva. A
    DL-029 (docs/planos/DL-029-a-frase-executavel-do-criterio-9.md, risco
    declarado) prevê exatamente este caso: "registre em vez de escolher
    um" — este instrumento deriva SÓ dos dois lugares que o próprio plano
    nomeou; a terceira ocorrência é matéria para quem decide o produto,
    não para este script."""
    if not _CAMINHO_BASE_HTML.is_file():
        _recusar(f"não encontrei {_CAMINHO_BASE_HTML} para derivar o identificador do fornecedor.")
    conteudo = _CAMINHO_BASE_HTML.read_text(encoding="utf-8")

    casamento_titulo = _PADRAO_TITULO_PADRAO.search(conteudo)
    casamento_marca = _PADRAO_MARCA.search(conteudo)
    if casamento_titulo is None or casamento_marca is None:
        _recusar(
            f"{_CAMINHO_BASE_HTML} mudou de forma que este instrumento não reconhece mais "
            "onde o identificador do fornecedor é escrito (bloco 'titulo' padrão e/ou "
            "'.marca') — atualize os padrões de _derivar_marca_do_fornecedor junto com o "
            "template, nunca volte a um literal fixo aqui."
        )

    marca_no_titulo = casamento_titulo.group(1).strip()
    marca_na_navegacao = casamento_marca.group(1).strip()
    if marca_no_titulo != marca_na_navegacao:
        _recusar(
            f"{_CAMINHO_BASE_HTML}: a tag <title> ('{marca_no_titulo}') e '.marca' "
            f"('{marca_na_navegacao}') declaram identificadores DIFERENTES do fornecedor — "
            "este instrumento não escolhe um dos dois por conta própria (DE-056); "
            "corrija a divergência no produto ou confirme qual das duas é a fonte certa."
        )
    return marca_no_titulo


_PADRAO_NAO_ALFANUMERICO = re.compile(r"[^a-z0-9]")


def _normalizar_para_busca_do_fornecedor(texto):
    """Minúsculas e só letras/dígitos — caixa, espaço, pontuação e
    QUALQUER separador (hífen, ponto, sublinhado, quebra de linha)
    desprezados. É a pergunta por PROPRIEDADE que o K1 pediu, não uma
    lista de grafias: fecha `DATALEDGER`, `dataledger`, `Data Ledger`,
    `D a t a L e d g e r` e `dataledger.com.br` de uma vez só, sem
    precisar enumerar cada uma (ver os casos de teste em
    scripts/test_medir_identificacao_do_emitente.py)."""
    return _PADRAO_NAO_ALFANUMERICO.sub("", (texto or "").lower())


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
    reaproveitado, não reimplementado.

    C1 da DL-029 (K3/BL-406, décima auditoria): `kwargs_conhecidos`
    ganhou `lancamento_id` — a base semeada por
    `scripts/semear_base_de_medicao.py` já grava 60 lançamentos; MEDIDO
    contra o K3, uma tela nova com timbre em
    `contabilidade_web:lancamento_detalhe` (rota que exige
    `lancamento_id`) NUNCA era alcançada antes desta correção, e a
    varredura estática do `pytest` (que só olha `templates/**`, sem
    requisitar nada) via a tela nova enquanto este instrumento — o
    mecanismo que o Fred escolheu tornar obrigatório — a ignorava, em
    AVISO, dentro de um job VERDE."""
    from django.urls import reverse

    from apps.contabilidade.models import LancamentoContabil

    # C1/K3: o PRIMEIRO lançamento da empresa semeada — mesmo padrão de
    # "primeiro registro da empresa semeada" que o plano pede (não o
    # "mais movimentado": aquele critério é de `medir_impressao.py`, para
    # a MEDIÇÃO de paginação; aqui só precisamos de UM id válido para
    # alcançar a rota, não de nenhuma propriedade específica do registro).
    lancamento = LancamentoContabil.objects.filter(empresa=empresa).order_by("id").first()

    kwargs_conhecidos = {"empresa_id": empresa.id, "conta_id": conta.id}
    if lancamento is not None:
        kwargs_conhecidos["lancamento_id"] = lancamento.id
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
        # LIMITE DECLARADO, no formato da DE-056 — não fechado por esta
        # etapa (a mesma classe de honestidade que o BL-404/C5 cobrou
        # para a marca do fornecedor: "limite declarado não é limite
        # fechado" também vale para o QUE FALTA, não só para o que já
        # está coberto). Os parâmetros que sobram aqui hoje (medido: `pk`
        # das rotas REST de `empresas`/`accounts`, e `token` do convite
        # de `tenancy`) não têm um valor "primeiro registro da empresa
        # semeada" óbvio — `pk` é genérico por modelo (não diz QUAL
        # modelo) e `token` é um segredo de uso único, não uma chave
        # primária. Preencher esses dois exigiria um mapa nome-de-
        # parâmetro→modelo (escopo maior que esta etapa, e risco de
        # adivinhar em vez de medir) — este instrumento CONTINUA
        # incapaz de decidir se essas rotas carregam `.timbre-impressao`,
        # e diz isso em aviso, não em silêncio. Se uma tela NOVA nascer
        # numa rota assim, ela PODE escapar desta varredura — quem fechar
        # essa lacuna registra a decisão, não adivinha aqui.
        print(
            f"AVISO (não é falha): {len(puladas)} rota(s) nomeada(s) puladas na "
            "varredura por precisarem de parâmetro que este instrumento não sabe "
            f"preencher hoje (conhecidos: {sorted(kwargs_conhecidos)}) — uma tela "
            "nova que dependa só desses entraria sozinha; uma que dependa de outro "
            "parâmetro (tipicamente `pk` genérico ou `token` de uso único) precisa "
            "de extensão deste script, e este instrumento NÃO consegue hoje "
            "confirmar se ela carrega timbre (limite declarado, ver o comentário "
            "acima):",
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
# C2 da DL-029: o piso de contraste do WCAG 2.2 depende do TAMANHO e do
# PESO da fonte REALMENTE renderizados (ver _razao_minima_wcag_para_linha,
# em medir_identificacao_do_emitente.py) -- perguntados ao NAVEGADOR via
# getComputedStyle, nunca deduzidos de um token CSS ou de uma lista de
# seletores "que deveriam ser grandes". Consulta um seletor SEPARADO
# (não sonda_visibilidade.py -- é específica deste instrumento, não do
# gauntlet que aquele módulo também serve) sobre os MESMOS elementos que
# "seletor_filhos" já enumera, na MESMA ordem (querySelectorAll é
# determinístico para o mesmo DOM).
js_fonte_das_linhas = (
    "(seletor) => [...document.querySelectorAll(seletor)].map((el) => {"
    "  const cs = getComputedStyle(el);"
    "  return {tamanho_px: parseFloat(cs.fontSize), peso: parseInt(cs.fontWeight, 10) || 400};"
    "})"
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
                medida["fonte_das_linhas"] = pagina.evaluate(
                    js_fonte_das_linhas, especificacao["seletor_filhos"]
                )
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


_PADRAO_PDFINFO_PAGINAS = re.compile(r"^Pages:\s*(\d+)\s*$", re.MULTILINE)


def _total_de_paginas(caminho_pdf):
    """Número de páginas do PDF exportado, via `pdfinfo` (poppler-utils —
    JÁ dependência de sistema deste projeto, ao lado de `pdftotext` e
    `pdftoppm`; nenhuma lib nova). C1 da DL-029
    (docs/planos/DL-029-a-frase-executavel-do-criterio-9.md): "a folha A4
    exportada" cobre TODAS as páginas, não só a primeira por premissa não
    declarada (K7, décima auditoria) — este número é o que permite ao
    oráculo do papel procurar uma linha nas páginas seguintes quando ela
    não está na primeira, em vez de reportar "sem tinta" para uma linha que
    só foi PAGINADA.

    BL-378: `check=False` — `pdfinfo` quebrado é a MESMA classe de falha de
    infraestrutura que `_texto_do_pdf`/`_palavras_da_pagina`/`pdftoppm`
    já tratam, nunca um veredito sobre o produto."""
    resultado = subprocess.run(
        ["pdfinfo", str(caminho_pdf)], capture_output=True, text=True, check=False
    )
    if resultado.returncode != 0:
        _recusar(
            f"'pdfinfo' falhou (código {resultado.returncode}) ao consultar {caminho_pdf} — "
            f"falha de infraestrutura, não veredito sobre o produto.\nerro: {resultado.stderr}"
        )
    casamento = _PADRAO_PDFINFO_PAGINAS.search(resultado.stdout)
    if casamento is None:
        _recusar(
            f"'pdfinfo' não relatou o número de páginas de {caminho_pdf} — "
            f"saída inesperada:\n{resultado.stdout}"
        )
    return int(casamento.group(1))


_PADRAO_LINHA_PDFINFO = re.compile(r"^([A-Za-z ]+?):\s+(.*)$", re.MULTILINE)

# C5 da DL-029 — pergunta do arquiteto-senior no meio da etapa (não estava
# no plano original): a frase do critério 9 diz "a folha A4 EXPORTADA …
# não carrega nenhum identificador do fornecedor". Até esta correção, "a
# folha exportada" só era lida como TINTA (texto do corpo do PDF,
# `_texto_do_pdf`) — mas o arquivo que o escritório entrega ao cliente é
# o PDF inteiro, e PDF carrega METADADOS além de conteúdo visual. O
# `<title>` de `templates/base.html` alimenta o campo `/Title` do PDF
# exportado pelo Chromium — sem nenhum pixel de tinta na folha.
#
# MEDIDO (não hipotetizado) contra as três telas reais que este
# instrumento mede, em cópia isolada, banco `ag_dl029`:
#
#   $ pdfinfo contabilidade_web_balancete.pdf | \
#       grep -E '^(Title|Author|Subject|Keywords|Creator|Producer):'
#   Title:           Balancete — Comércio Sintético de Materiais Ltda
#   Creator:         Chromium
#   Producer:        Skia/PDF m153
#
# (idem para `diario` e `razao`, só o nome do relatório muda no Título;
# `Author`/`Subject`/`Keywords` não aparecem — poppler omite a linha
# inteira quando o campo é vazio, MEDIDO).
#
# **Por que o Título não carrega a marca HOJE, medido — e é uma cadeia
# que ninguém tinha escrito antes desta medição**: a DECISÃO do Fred de
# 2026-09-19 (RC-97, comentário completo em `templates/base.html`) já
# esvazia `titulo_sufixo_do_fornecedor` nas TRÊS telas com timbre — mas
# essa decisão mirava OUTRO canal (a FAIXA DO NAVEGADOR ao imprimir,
# BL-332/A2), não o metadado do PDF. O efeito colateral, medido agora: o
# MESMO bloco Django (`{% block titulo_sufixo_do_fornecedor %}`)
# alimenta os DOIS canais — a faixa do navegador E o `/Title` do PDF
# exportado —, então limpar um limpou o outro DE CARONA, sem que a
# correção de 2026-09-19 soubesse disso. Se algum dia alguém reintroduzir
# o sufixo por outro motivo (ex.: uma tela nova que precise dele por
# razão alheia a este critério), o `/Title` volta a carregar a marca
# JUNTO — é um acoplamento real, não hipotético, e fica registrado aqui
# para não ser redescoberto do zero.
#
# **`Creator`/`Producer` são identidade do MOTOR DE PDF (Chromium/Skia),
# não do produto — e por isso NÃO entram na reprovação, só no
# diagnóstico** (decisão do arquiteto-senior, no meio desta etapa):
# incluí-los na reprovação teria valor de detecção ZERO (a página não
# controla esses dois campos hoje) e risco de FALSO ALARME não-zero — a
# comparação é normalizada e chaveada pelo NOME do fornecedor; no dia em
# que esse nome mudar para algo que também apareça dentro de "Skia/PDF"
# ou "Chromium" por coincidência, o job ficaria vermelho sobre produto
# CORRETO (exatamente a classe de falso alarme que a BL-321/K4 já puniu
# nesta mesma auditoria). Por isso `Creator`/`Producer` são SEMPRE
# reportados na saída (`entrada["metadados_pdf"]`), mas nunca entram em
# `motivos` — se um dia o projeto trocar o motor de exportação por uma
# biblioteca que ele PRÓPRIO configura, esses dois campos passam a ser
# escolha do produto, e a mudança de categoria (de diagnóstico para
# reprovação) precisa ser uma decisão nova, não uma dedução silenciosa
# deste comentário.
#
# **Limite declarado (formato da DE-056), não fechado por esta etapa:**
# esta checagem lê só o dicionário clássico `Info` do PDF (`pdfinfo`,
# sem `-meta`) — SEIS campos nomeados, e SÓ os que existem nesse
# dicionário. PDF moderno também pode carregar um pacote XMP (outro
# formato de metadado, com campos como `dc:title`/`xmp:CreatorTool`).
# MEDIDO contra as três telas: `pdfinfo -meta` devolve saída VAZIA
# (código 0) e `pdfinfo` (sem `-meta`) relata `Metadata Stream: no` —
# hoje o Chromium NÃO embute XMP nestes PDFs, então não há um segundo
# lugar para checar. Se isso mudar (troca de motor de exportação, opção
# nova do Chromium), esta checagem NÃO alcança o XMP — é limite
# declarado, não fechado, e fechá-lo é outra etapa.
#
# DE-058: as afirmações de medição acima têm teste ao lado —
# `_checar_marca_do_fornecedor_nos_metadados` (abaixo) faz a pergunta
# PARA VALER a cada execução (não só nesta calibração), então uma
# regressão futura (ex.: alguém reintroduzir o sufixo nas telas de
# documento) É PEGA pela MESMA verificação que fecha o C5, sem depender
# de ninguém lembrar desta medição.
_CAMPOS_DE_METADADO_PDF = ("Title", "Author", "Subject", "Keywords", "Creator", "Producer")

# Controlados pelo PRODUTO (via templates Django) — reprovam se carregarem
# o identificador do fornecedor.
_CAMPOS_DE_METADADO_CONTROLADOS_PELO_PRODUTO = ("Title", "Author", "Subject", "Keywords")

# Identidade do MOTOR de exportação (Chromium/Skia) — só diagnóstico, ver
# o comentário acima sobre por que NÃO reprovam hoje.
_CAMPOS_DE_METADADO_DO_MOTOR_DE_PDF = ("Creator", "Producer")


def _metadados_do_pdf(caminho_pdf):
    """`{"Title": ..., "Author": ..., "Subject": ..., "Keywords": ...,
    "Creator": ..., "Producer": ...}` — só os campos que
    `_CAMPOS_DE_METADADO_PDF` nomeia, lidos do dicionário `Info` clássico
    via `pdfinfo` (MESMA dependência de sistema já usada por `_total_de_
    paginas`; NÃO lê XMP — ver o limite declarado no comentário acima).
    Campo ausente na saída do poppler (ex.: `Author` vazio, MEDIDO:
    poppler omite a linha inteira) não entra no dicionário — tratado
    como string vazia por quem chama, nunca como erro.

    BL-378: `check=False` — `pdfinfo` quebrado é a MESMA classe de falha
    de infraestrutura que os demais usos de poppler-utils neste módulo."""
    resultado = subprocess.run(
        ["pdfinfo", str(caminho_pdf)], capture_output=True, text=True, check=False
    )
    if resultado.returncode != 0:
        _recusar(
            f"'pdfinfo' falhou (código {resultado.returncode}) ao consultar {caminho_pdf} — "
            f"falha de infraestrutura, não veredito sobre o produto.\nerro: {resultado.stderr}"
        )
    encontrados = dict(_PADRAO_LINHA_PDFINFO.findall(resultado.stdout))
    return {campo: encontrados.get(campo, "").strip() for campo in _CAMPOS_DE_METADADO_PDF}


def _checar_marca_do_fornecedor_nos_metadados(metadados, marca_normalizada):
    """Devolve o NOME do primeiro campo de metadado CONTROLADO PELO
    PRODUTO (`_CAMPOS_DE_METADADO_CONTROLADOS_PELO_PRODUTO` — nunca
    `Creator`/`Producer`, ver o comentário acima) cujo valor, normalizado,
    contém o identificador do fornecedor — ou `None` se nenhum contém.
    Mesma normalização de `_normalizar_para_busca_do_fornecedor` (caixa,
    espaço, pontuação e separadores desprezados): o C5 vale para o
    ARQUIVO PDF inteiro, não só para o texto visível na folha."""
    for campo in _CAMPOS_DE_METADADO_CONTROLADOS_PELO_PRODUTO:
        valor = metadados.get(campo, "")
        if marca_normalizada in _normalizar_para_busca_do_fornecedor(valor):
            return campo
    return None


# ---------------------------------------------------------------------------
# Oráculo do papel (BL-372, achado J1 da nona auditoria) — "tem tinta que
# CONTRASTA com o papel na faixa onde a linha do timbre deveria estar?" Ver
# o parágrafo correspondente na docstring do módulo para o raciocínio
# completo; os comentários abaixo cobrem só as decisões de CADA função.
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

# C2 da DL-029 (docs/planos/DL-029-a-frase-executavel-do-criterio-9.md) —
# "com tinta que CONTRASTA com o papel": substitui o `LIMIAR_LUMINANCIA_
# TINTA = 128` fixo (K4/BL-407, décima auditoria). A docstring daquele
# limiar AFIRMAVA uma medição — "nenhuma medição produziu pixel de linha
# do timbre entre 1 e 254" — e uma linha de CSS banal a desmentiu:
# `opacity: 0.4` pinta pixels entre 153 e 225, todos ACIMA de 128, e o
# instrumento reprovava produto correto anunciando "0 pixels escuros"
# (BL-321: falso alarme). É exatamente a DE-058 ("justificativa escrita
# não é justificativa medida") aplicada contra o próprio código que a
# nomeou.
#
# **Correção descartada, e por quê**: a primeira versão desta correção
# fixava `RAZAO_MINIMA_DE_CONTRASTE_TINTA = 2.4` — um valor MEDIDO, mas
# ESCOLHIDO para caber entre dois casos de teste específicos (a janela
# entre "branco declarado" e "opacity: 0.4"). O arquiteto-senior apontou,
# no meio desta etapa, que isso é a MESMA forma de defeito que a etapa
# inteira combate: "número que existe porque um teste precisava dele" —
# só que desta vez o número era uma RAZÃO, não uma lista. A decisão foi
# revertida.
#
# **A correção final não escolhe um número — TOMA EMPRESTADO um padrão
# publicado, versionado e externo ao projeto**: WCAG 2.2, Critério de
# Sucesso 1.4.3 "Contraste (Mínimo)", nível AA — W3C Recommendation, 5 de
# outubro de 2023 (https://www.w3.org/TR/WCAG22/#contrast-minimum,
# consultado em 2026-09-20). Ele exige razão de contraste >= **4,5:1**
# para texto NORMAL e >= **3:1** para texto GRANDE (>= 18pt, ou >= 14pt
# em negrito) — ver `_razao_minima_wcag_para_linha`, abaixo, que aplica
# esses dois números ao tamanho e peso de fonte REALMENTE renderizados
# (perguntados ao NAVEGADOR, `getComputedStyle`, nunca a uma lista de
# tokens CSS — ver `_SCRIPT_DO_SUBPROCESSO`).
#
# ⚠️ **LIMITE DECLARADO, com todas as letras (exigência do
# arquiteto-senior)**: o WCAG 2.2 é um EMPRÉSTIMO, não uma norma que
# governa este critério. Ele rege CONTEÚDO WEB (contraste de texto numa
# TELA), não papel impresso, e não é norma contábil nem legal — o
# AGENTS.md proíbe inventar exigência normativa, e este comentário não
# afirma que o WCAG É a norma do critério 9. É a referência de
# LEGIBILIDADE adotada por ESCOLHA DECLARADA deste projeto, na falta de
# um piso específico para documento contábil impresso — decisão do
# arquiteto-senior, registrada aqui e em `docs/projeto/decisoes.md`. Se o
# Fred (responsável pelo produto) ou uma norma contábil futura fixar um
# piso próprio, ELE substitui este, não o contrário.
#
# **Consequência medida desta escolha, que inverteu um critério de
# aceite do plano**: com o piso do WCAG, `opacity: 0.4` no timbre
# REPROVA — razão 2,81:1 na linha mais fraca, abaixo até do piso de
# texto GRANDE (3:1). O critério 7 original da DL-029 ("opacity: 0.4 tem
# de passar") herdava, sem medir, o juízo visual do K4 ("timbre
# perfeitamente legível") — a mesma classe de afirmação não medida que a
# DE-058 existe para proibir. Corrigido pelo arquiteto-senior no plano.
RAZAO_MINIMA_WCAG_TEXTO_NORMAL = 4.5
RAZAO_MINIMA_WCAG_TEXTO_GRANDE = 3.0

# 18pt e 14pt, convertidos para pixel CSS pela MESMA definição usada em
# todo este módulo (`DPI_ORACULO_DO_PAPEL = 96` — 1pt = 1/72 polegada,
# 1px CSS = 1/96 polegada; ver o comentário de `DPI_ORACULO_DO_PAPEL`).
# 1 ponto tem MAIS pixels do que "pontos por pixel" sugeriria — a
# conversão é PIXELS POR PONTO (96/72 ≈ 1,333), não o inverso; 18pt vira
# 24px, não 13,5px. (Achado próprio, corrigido nesta mesma revisão: a
# primeira versão desta constante multiplicava por PONTOS por pixel —
# 72/96 = 0,75 — invertendo a conversão e classificando as linhas de
# 14px/peso normal do timbre real como "texto grande" por engano, MEDIDO
# contra o produto: as três linhas do Balancete saíam com
# razao_minima_wcag_exigida=3.0, quando as duas linhas de peso normal
# deveriam exigir 4.5. `scripts/test_medir_identificacao_do_emitente.py`
# fixa o valor CORRETO, 24px para 18pt, para este erro não voltar.)
# WCAG 2.2 define "negrito" como peso >= 700 (a palavra-chave CSS
# `bold`) — nenhuma lista de pesos "parecidos com negrito", a MESMA
# convenção que `getComputedStyle(...).fontWeight` já usa.
_PIXELS_POR_PONTO = DPI_ORACULO_DO_PAPEL / PONTOS_POR_POLEGADA
TAMANHO_MINIMO_TEXTO_GRANDE_PX = 18 * _PIXELS_POR_PONTO
TAMANHO_MINIMO_TEXTO_GRANDE_NEGRITO_PX = 14 * _PIXELS_POR_PONTO
PESO_MINIMO_NEGRITO = 700


def _razao_minima_wcag_para_linha(tamanho_px, peso):
    """Razão de contraste mínima (WCAG 2.2, 1.4.3) para uma linha com o
    TAMANHO (px CSS) e PESO (100–900, `getComputedStyle(...).fontWeight`)
    realmente renderizados — nunca uma lista de seletores CSS "que
    deveriam ser grandes". "Texto grande" é >= 18pt (>=
    `TAMANHO_MINIMO_TEXTO_GRANDE_PX`) em qualquer peso, OU >= 14pt
    (>= `TAMANHO_MINIMO_TEXTO_GRANDE_NEGRITO_PX`) em negrito
    (peso >= `PESO_MINIMO_NEGRITO`) — a definição textual do próprio
    critério, sem arredondamento silencioso: MEDIDO que a razão social do
    timbre (negrito, `--tipo-md`) e as demais linhas (peso normal, mesmo
    tamanho) podem cair em categorias DIFERENTES conforme o tamanho real
    da fonte do produto — por isso o piso é calculado POR LINHA, nunca
    um só para o timbre inteiro."""
    eh_negrito = peso >= PESO_MINIMO_NEGRITO
    eh_grande = tamanho_px >= TAMANHO_MINIMO_TEXTO_GRANDE_PX or (
        eh_negrito and tamanho_px >= TAMANHO_MINIMO_TEXTO_GRANDE_NEGRITO_PX
    )
    return RAZAO_MINIMA_WCAG_TEXTO_GRANDE if eh_grande else RAZAO_MINIMA_WCAG_TEXTO_NORMAL


def _luminancia_relativa_srgb(fracao_do_canal):
    """Luminância relativa de um canal sRGB (0.0–1.0) — fórmula da WCAG 2.x
    ("Relative Luminance"). `pdftoppm -gray` devolve um BYTE por pixel (não
    três canais RGB): para cinza puro R=G=B, então a luminância relativa
    do PIXEL inteiro é o resultado desta função aplicada uma vez — nenhuma
    ponderação de canal (0.2126/0.7152/0.0722) é necessária aqui."""
    if fracao_do_canal <= 0.03928:
        return fracao_do_canal / 12.92
    return ((fracao_do_canal + 0.055) / 1.055) ** 2.4


def _razao_de_contraste(nivel_de_cinza_a, nivel_de_cinza_b):
    """Razão de contraste WCAG entre dois níveis de cinza 0–255 — sempre
    >= 1.0 (dois pixels idênticos dão exatamente 1.0), simétrica (não
    importa qual argumento é o mais claro). É a mesma fórmula que decide
    conformidade de contraste de texto em acessibilidade web; aqui mede
    tinta contra papel em vez de texto contra fundo de tela."""
    luminancia_a = _luminancia_relativa_srgb(nivel_de_cinza_a / 255)
    luminancia_b = _luminancia_relativa_srgb(nivel_de_cinza_b / 255)
    mais_clara, mais_escura = max(luminancia_a, luminancia_b), min(luminancia_a, luminancia_b)
    return (mais_clara + 0.05) / (mais_escura + 0.05)


def _luminancia_do_papel(dados_pgm):
    """Fundo do PAPEL nesta rasterização — a MODA (nível de cinza mais
    frequente) da folha INTEIRA, não um branco (255) presumido. C2 da
    DL-029: "o fundo da PRÓPRIA folha", medido, não hipotetizado. Uma
    folha A4 impressa é, de longe, majoritariamente papel em branco —
    MEDIDO: no Balancete da base de medição, 815099 dos 893580 pixels
    (91%) — então a moda encontra o papel mesmo numa página com tabela
    cheia de texto preto."""
    _, _, corpo = _pgm_para_matriz(dados_pgm)
    histograma = [0] * 256
    for byte in corpo:
        histograma[byte] += 1
    return max(range(256), key=histograma.__getitem__)


def _niveis_de_cinza_com_contraste_suficiente(luminancia_do_papel, razao_minima):
    """Pré-computa, uma vez por folha E por linha (o piso é POR LINHA —
    ver `_razao_minima_wcag_para_linha`), quais dos 256 níveis de cinza
    satisfazem `razao_minima` contra ESTE fundo — evita recalcular
    `_razao_de_contraste` pixel a pixel (uma folha A4 a 96 dpi tem ~900
    mil pixels; a faixa de uma linha, alguns milhares). Devolve um
    `frozenset` de níveis de cinza (0–255)."""
    return frozenset(
        nivel
        for nivel in range(256)
        if _razao_de_contraste(luminancia_do_papel, nivel) >= razao_minima
    )


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
    existe, aqui" e "há tinta que CONTRASTA com o papel aqui" que
    `_diagnostico_de_contraste_na_faixa` fecha.

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


def _localizar_bloco_do_timbre(palavras, linhas_esperadas):
    """C4/C3 da DL-029 — ancora as N linhas do timbre por OCORRÊNCIA, na
    ordem de leitura, NUNCA pelo primeiro texto igual em qualquer lugar da
    página (K2/BL-405, décima auditoria,
    docs/auditorias/2026-09-20-dl-026-dl-028-rodada-10.md).

    **Por que um rodapé (ou qualquer outro elemento) que repita o TEXTO de
    uma linha do timbre não engana esta função.** No HTML, as linhas do
    timbre são um `<p>` logo após o outro, dentro do MESMO
    `.timbre-impressao`, sem nada entre elas
    (`{% for linha in timbre_linhas %}<p>{{ linha }}</p>{% endfor %}` —
    `templates/contabilidade/balancete.html` e as demais telas com
    timbre). Isso significa que, no PDF exportado, as N linhas aparecem
    como uma sequência CONTÍGUA — sem NENHUMA palavra estranha entre o
    fim de uma e o início da próxima. Esta função procura, em TODA
    posição possível da página, essa sequência de N linhas JUNTAS (a
    mesma técnica de concatenação sem espaço de `_bbox_da_linha`,
    estendida para as N linhas em sequência) — e só aceita a PRIMEIRA
    posição em que as N fecham, uma após a outra, sem lacuna.

    MEDIDO construindo esta correção, contra o cenário do K2/BL-405 (um
    rodapé ANTES do timbre repetindo a linha 0): a varredura abaixo NUNCA
    fecha começando no rodapé — depois do texto da linha 0 ali, a PRÓXIMA
    coisa na página é OUTRA cópia da linha 0 (a real, do timbre), não a
    linha 1 —, e só fecha na posição real do timbre (linha 0 do timbre,
    seguida imediatamente por linha 1, seguida por linha 2). O bbox
    devolvido para a linha 0 é o da posição REAL do timbre (tinta do
    negrito, não a do rodapé).

    LIMITE DECLARADO (formato da DE-056), apontado pelo arquiteto-senior
    no meio desta etapa — não fechado aqui, de propósito: **a
    CONTIGUIDADE é propriedade do TEMPLATE de HOJE, não do requisito.**
    "Sem nada entre elas" é verdade porque `templates/contabilidade/
    balancete.html` (e as demais telas com timbre) hoje só desenham um
    `<p>` por linha, um após o outro, sem NENHUM outro elemento no meio.
    A [DL-027](docs/planos/DL-027-documento-emitido-e-personalizacao.md)
    — personalização de relatório, timbre com logotipo, marca d'água ou
    linha de contexto entre as linhas — é exatamente a etapa que pode
    ROMPER essa premissa: um elemento de TEXTO inserido entre duas linhas
    do timbre quebra a sequência contígua, e esta função passa a devolver
    `[None, None, ...]` PERMANENTEMENTE para aquela tela — não porque o
    timbre esteja errado, mas porque a âncora por bloco deixou de se
    aplicar. Quem chama (`_localizar_linhas_do_timbre_no_documento`)
    cai então para o caminho de EXCEÇÃO (busca individual por linha,
    sem anti-decoy) em TODA execução, não só quando paginação acontece —
    e o limite DAQUELE caminho (ver a docstring dele) passa a valer
    sempre, não como exceção rara.

    MEDIDO (não hipotético) que esse caminho de exceção CONTINUA seguro
    para o caso que mais importa — decoy MAIS elemento intruso QUEBRANDO
    a contiguidade MAIS a linha real escondida — porque a checagem de
    VISIBILIDADE DO NAVEGADOR (`filhos[i]`, em `main`, indexada por
    POSIÇÃO em `.timbre-impressao p`) não depende de contiguidade
    nenhuma: um `<span>` ou `<div>` intruso entre duas linhas NÃO entra
    em `filhos` (o seletor é `p`, não `*`), então a correspondência
    posicional `filhos[i] ↔ linhas_esperadas[i]` continua válida mesmo
    quando o bloco textual do PDF não fecha. Testado contra: um `<span>`
    intruso entre a linha 0 e a linha 1 do timbre, MAIS um rodapé decoy
    repetindo a linha 0, MAIS a linha 0 real escondida (`display: none`)
    — resultado REPROVADO, código 1, nomeando corretamente "linha do
    timbre NÃO visível sob impressão" para a linha 0. O MESMO intruso,
    sozinho, sem decoy nem esconder nada, continua PASSANDO (código 0) —
    a contiguidade quebrada não produz falso alarme por si só.

    Se a DL-027 introduzir um `<p>` NOVO dentro de `.timbre-impressao`
    (não um `<span>`/`<div>`), o limite MUDA: `filhos` passaria a incluir
    esse `<p>` também, deslocando a correspondência posicional — isso
    NÃO foi medido aqui (a DL-027 ainda não decidiu o formato), e fica
    como pergunta em aberto para quem implementar aquela etapa, não como
    garantia desta.

    Devolve uma LISTA — nunca um dicionário chaveado por texto (é
    exatamente a fenda do C3: duas linhas com o MESMO texto colapsariam
    na mesma chave) —, na MESMA ordem/posição de `linhas_esperadas`, com
    a caixa `(xmin, ymin, xmax, ymax)` de cada linha quando o BLOCO
    INTEIRO fecha nesta página, ou `[None, None, ...]` (todas) quando não
    há, em NENHUM ponto da página, uma sequência contígua que bata com as
    N linhas esperadas NESTA ORDEM — ex.: quando o timbre tem duas linhas
    com o MESMO texto e uma delas está escondida (`display: none`): sem a
    segunda repetição da mesma palavra, a sequência de N linhas nunca
    fecha em lugar nenhum da página (MEDIDO contra o cenário do K2 com
    `registro_no_timbre == endereco_no_timbre` e o terceiro `<p>`
    escondido — ver os testes).

    Quando o bloco não fecha NESTA página (ex.: paginação partiu o
    timbre entre duas folhas — K7/BL-410), quem chama (`main`, abaixo)
    cai para uma busca INDIVIDUAL por linha, página a página — ver o
    comentário de `main` sobre esse caminho e o limite que ele declara."""
    total = len(palavras)
    alvos = ["".join(linha.split()) for linha in linhas_esperadas]
    if not palavras or not alvos or not all(alvos):
        return [None] * len(alvos)

    for inicio in range(total):
        posicao = inicio
        caixas = []
        bloco_fechou = True
        for alvo in alvos:
            grupo_inicio = posicao
            acumulado = ""
            linha_encontrada = False
            fim = posicao
            while fim < total:
                acumulado += "".join(palavras[fim][4].split())
                if acumulado == alvo:
                    grupo = palavras[grupo_inicio : fim + 1]
                    caixas.append(
                        (
                            min(p[0] for p in grupo),
                            min(p[1] for p in grupo),
                            max(p[2] for p in grupo),
                            max(p[3] for p in grupo),
                        )
                    )
                    posicao = fim + 1
                    linha_encontrada = True
                    break
                if len(acumulado) > len(alvo):
                    break
                fim += 1
            if not linha_encontrada:
                bloco_fechou = False
                break
        if bloco_fechou:
            return caixas
    return [None] * len(alvos)


def _rasterizar_pagina(caminho_pdf, pagina=1, dpi=DPI_ORACULO_DO_PAPEL):
    """Rasteriza UMA página do PDF (padrão: a primeira) para tons de cinza
    (PGM binário `P5`) via `pdftoppm -gray` — a MESMA dependência de
    sistema (poppler-utils) que `_texto_do_pdf`/`_palavras_da_pagina` já
    exigem; NENHUMA biblioteca de imagem nova em `requirements/` (mesma
    decisão registrada na docstring de `scripts/medir_impressao.py` para
    não acrescentar lib de PDF). `-singlefile` evita o poppler acrescentar
    sufixo numérico ao nome de saída, já que só pedimos uma página.

    C1 da DL-029 (K7, décima auditoria): antes desta correção, esta
    função só rasterizava a PRIMEIRA página, por premissa não declarada —
    uma linha empurrada para a página 2 (por paginação comum: margem,
    cabeçalho mais alto) media "0 pixels escuros" na folha 1, a MESMA
    mensagem de tinta realmente ausente. O parâmetro `pagina` (usado por
    `main`, abaixo, para procurar nas páginas seguintes antes de reportar
    ausência de tinta) fecha essa lacuna.

    BL-378: `pdftoppm` quebrado é a MESMA classe de falha de
    infraestrutura que os demais usos de poppler-utils neste módulo."""
    with tempfile.TemporaryDirectory(prefix="dl-oraculo-papel-") as pasta:
        prefixo = Path(pasta) / "pagina"
        resultado = subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(dpi),
                "-f",
                str(pagina),
                "-l",
                str(pagina),
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
                f"rasterizar a página {pagina} de {caminho_pdf} — falha de infraestrutura.\n"
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


def _diagnostico_de_contraste_na_faixa(
    dados_pgm,
    retangulo_pt,
    luminancia_do_papel,
    razao_minima,
    dpi=DPI_ORACULO_DO_PAPEL,
    margem_px=2,
):
    """C2 da DL-029 — mede, dentro do retângulo `(xmin, ymin, xmax, ymax)`
    (em PONTOS de PDF, convertido para pixel do raster por `dpi/72` — ver
    `DPI_ORACULO_DO_PAPEL`), contra `luminancia_do_papel` (o fundo MEDIDO
    desta MESMA folha — `_luminancia_do_papel`) e `razao_minima` (o piso
    POR LINHA do WCAG — `_razao_minima_wcag_para_linha`): quantos pixels
    atingem o piso, E qual é o CONTRASTE MÁXIMO (o pixel mais escuro)
    encontrado na faixa. Devolve `(pixels_com_contraste_suficiente,
    contraste_maximo_medido)`.

    **Por que as DUAS medidas, e não só a contagem** — exigência do
    arquiteto-senior: quem chama precisa DISTINGUIR duas causas de
    reprovação diferentes, com mensagens diferentes. Se o CONTRASTE
    MÁXIMO da faixa já fica abaixo do piso, nenhuma quantidade de pixels
    ajudaria — é reprovação por CONTRASTE (a tinta é clara demais).  Se o
    contraste máximo passa o piso mas a CONTAGEM não chega no piso de
    `PISO_PIXELS_ESCUROS_POR_LINHA`, a tinta é escura o bastante mas a
    ÁREA pintada é pequena demais (ex.: `font-size: 1px`) — é reprovação
    por CONTAGEM. As duas eram a MESMA mensagem antes desta correção
    ("SEM TINTA ESCURA suficiente"), e distingui-las é o que o critério 8
    (não regredir `font-size: 1px`) exige nomear corretamente.

    Substitui `_pixels_escuros_na_faixa` (que comparava contra um
    `LIMIAR_LUMINANCIA_TINTA` fixo — K4/BL-407) e a primeira versão desta
    função (`_pixels_com_contraste_suficiente_na_faixa`, que só devolvia
    a contagem contra uma razão FIXA para o timbre inteiro — ver o
    comentário de `RAZAO_MINIMA_WCAG_TEXTO_NORMAL` sobre por que aquilo
    foi revertido).

    `margem_px` expande a caixa igualmente nos quatro lados: absorve só o
    arredondamento do `int()` e a folga do antialiasing do glifo — NÃO é o
    que separa tinta de sabotagem (isso é a RAZÃO de contraste e o PISO de
    contagem); é para não cortar 1px do próprio glifo por arredondamento.
    MEDIDO ao construir o oráculo original: margem de 2px não alcança a
    linha vizinha em nenhuma das três telas (a menor distância entre duas
    linhas do timbre medida foi de ~17px) — comportamento herdado sem
    alteração por esta correção, que só troca o CRITÉRIO por pixel."""
    largura_pagina, altura_pagina, corpo = _pgm_para_matriz(dados_pgm)
    niveis_com_contraste = _niveis_de_cinza_com_contraste_suficiente(
        luminancia_do_papel, razao_minima
    )
    fator = dpi / PONTOS_POR_POLEGADA
    xmin, ymin, xmax, ymax = retangulo_pt
    x0 = max(0, int(xmin * fator) - margem_px)
    y0 = max(0, int(ymin * fator) - margem_px)
    x1 = min(largura_pagina, int(xmax * fator) + margem_px + 1)
    y1 = min(altura_pagina, int(ymax * fator) + margem_px + 1)
    contagem = 0
    nivel_mais_escuro = 255
    for y in range(y0, y1):
        inicio_da_linha = y * largura_pagina
        for x in range(x0, x1):
            nivel = corpo[inicio_da_linha + x]
            if nivel < nivel_mais_escuro:
                nivel_mais_escuro = nivel
            if nivel in niveis_com_contraste:
                contagem += 1
    contraste_maximo = _razao_de_contraste(luminancia_do_papel, nivel_mais_escuro)
    return contagem, contraste_maximo


def _localizar_linhas_do_timbre_no_documento(caminho_pdf, linhas_esperadas, razoes_minimas):
    """Orquestra C1 (todas as páginas) e C4/C3 (âncora por ocorrência) para
    as `linhas_esperadas` de UMA tela — chamada uma vez por tela dentro de
    `main`. `razoes_minimas` é uma lista, na MESMA ordem/posição de
    `linhas_esperadas`, com o piso de contraste WCAG DAQUELA linha
    (`_razao_minima_wcag_para_linha`, POR LINHA — texto grande/negrito e
    texto normal têm pisos diferentes). Devolve uma LISTA, na MESMA
    ordem/posição de `linhas_esperadas` (nunca um dicionário chaveado por
    texto — C3), de dicionários `{"bbox": (...)|None, "folha": int|None,
    "pixels_com_contraste": int, "contraste_maximo_medido": float}`.

    **Duas camadas, nesta ordem:**

    1. **Bloco inteiro na página 1** (`_localizar_bloco_do_timbre`): cobre
       CORRETAMENTE o caso de texto duplicado (K2/K4) — ver a docstring
       daquela função. Se o bloco inteiro fecha na página 1, esta função
       para aqui: é o caminho RÁPIDO e o único que a âncora por ocorrência
       garante ser distinguível de decoys iguais em outro lugar da folha.

    2. **Busca INDIVIDUAL, página a página** (`_bbox_da_linha`, a busca
       antiga, de UMA linha), só para as linhas que a camada 1 NÃO
       resolveu — o caso de PAGINAÇÃO (K7/BL-410): o bloco pode estar
       PARTIDO entre duas folhas (ex.: `margin-top` empurra só a terceira
       linha para a página 2), e nesse caso nenhuma página sozinha tem as
       N linhas contíguas, então a camada 1 devolve `None` para todas
       mesmo que a maioria esteja, sim, no papel. Quando uma linha é
       achada numa página > 1, o campo `"folha"` sai diferente de 1, e
       `main` (abaixo) nomeia a PAGINAÇÃO na mensagem — nunca "0 pixels
       escuros", que é a queixa exata do K7.

    LIMITE DECLARADO desta camada 2 (não fechado por esta etapa): ela NÃO
    dedupe ocorrências da MESMA linha entre si — se o bloco falhou por
    causa de texto duplicado dentro do MESMO timbre (não por paginação:
    ex.: a variante do K2 com `registro_no_timbre == endereco_no_timbre` e
    o terceiro `<p>` escondido), a busca individual pode achar, para a
    linha ESCONDIDA, a MESMA ocorrência já usada pela linha IRMÃ visível —
    dando um bbox (e pixels) não-nulos para uma linha que na verdade não
    está lá. Isso não produz falso-conforme aqui: a checagem de
    visibilidade do NAVEGADOR (`filhos[i]`, em `main`) já reprova esse
    caso de forma independente (é uma checagem em DOM, não depende do
    PDF) — mas é uma imprecisão real desta camada de fallback, e fica
    registrada, não escondida."""
    total_paginas = _total_de_paginas(caminho_pdf)
    palavras_pagina1 = _palavras_da_pagina(caminho_pdf, pagina=1)
    bboxes_do_bloco = _localizar_bloco_do_timbre(palavras_pagina1, linhas_esperadas)

    cache_por_pagina = {}

    def _dados_da_pagina(pagina):
        if pagina not in cache_por_pagina:
            palavras = palavras_pagina1 if pagina == 1 else _palavras_da_pagina(caminho_pdf, pagina)
            dados_pgm = _rasterizar_pagina(caminho_pdf, pagina)
            luminancia_do_papel = _luminancia_do_papel(dados_pgm)
            cache_por_pagina[pagina] = (palavras, dados_pgm, luminancia_do_papel)
        return cache_por_pagina[pagina]

    resultados = []
    for indice, linha in enumerate(linhas_esperadas):
        bbox = bboxes_do_bloco[indice]
        folha = 1 if bbox is not None else None

        if bbox is None:
            # Camada 2 (K7/C1): a linha não fez parte de um bloco fechado
            # na página 1 — procura ISOLADA, página a página, até achar
            # ou esgotar o documento.
            for pagina in range(1, total_paginas + 1):
                palavras_da_pagina, _, _ = _dados_da_pagina(pagina)
                candidato = _bbox_da_linha(palavras_da_pagina, linha)
                if candidato is not None:
                    bbox = candidato
                    folha = pagina
                    break

        if bbox is not None:
            _, dados_pgm, luminancia_do_papel = _dados_da_pagina(folha)
            pixels, contraste_maximo = _diagnostico_de_contraste_na_faixa(
                dados_pgm, bbox, luminancia_do_papel, razoes_minimas[indice]
            )
        else:
            pixels, contraste_maximo = 0, 1.0

        resultados.append(
            {
                "bbox": bbox,
                "folha": folha,
                "pixels_com_contraste": pixels,
                "contraste_maximo_medido": contraste_maximo,
            }
        )
    return resultados


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

    # C5 da DL-029: derivado de templates/base.html, nunca um literal
    # repetido aqui — ver o comentário completo de _derivar_marca_do_fornecedor.
    marca_do_fornecedor = _derivar_marca_do_fornecedor()
    marca_do_fornecedor_normalizada = _normalizar_para_busca_do_fornecedor(marca_do_fornecedor)

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
            entrada["pdf"] = str(caminho_pdf)

            # C5: ausência NORMALIZADA (caixa/espaço/pontuação/separadores
            # desprezados) do identificador DERIVADO — nunca um literal
            # repetido, e o texto vem de `_texto_do_pdf`, que já lê TODAS
            # as páginas do PDF (C1), não só a primeira.
            entrada["pdf_contem_marca_do_fornecedor"] = (
                marca_do_fornecedor_normalizada in _normalizar_para_busca_do_fornecedor(texto_pdf)
            )

            # C5, cobrindo o ARQUIVO PDF inteiro, não só a folha
            # rasterizada: o `<title>` de `templates/base.html` alimenta o
            # metadado `/Title` do PDF exportado (ver o comentário de
            # `_checar_marca_do_fornecedor_nos_metadados`) — "a folha A4
            # exportada" é o ARQUIVO que o escritório entrega ao cliente,
            # e um identificador nos metadados vaza tanto quanto um pixel
            # no papel, só que aparece nas PROPRIEDADES do arquivo em vez
            # da tinta.
            metadados_pdf = _metadados_do_pdf(caminho_pdf)
            campo_com_marca = _checar_marca_do_fornecedor_nos_metadados(
                metadados_pdf, marca_do_fornecedor_normalizada
            )
            entrada["metadados_pdf"] = metadados_pdf

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

            # C4/C3 (K2, décima auditoria): `filhos` já vem do NAVEGADOR
            # restrito a `.timbre-impressao p` (a sonda de
            # `sonda_visibilidade.js_sonda_container_e_filhos`) — nunca
            # inclui um decoy FORA do timbre (ex.: um rodapé repetindo o
            # mesmo texto). Por isso a linha `i` de `linhas_esperadas`
            # casa com `filhos[i]` por POSIÇÃO, nunca pelo TEXTO: buscar
            # por texto (`next(f for f in filhos if texto==linha)`, a
            # forma antiga) sempre acha a MESMA primeira ocorrência para
            # duas linhas com o mesmo texto, escondendo a segunda em
            # silêncio — a fenda exata que o K2 mediu.
            filhos = medida.get("filhos", [])
            if len(filhos) != len(linhas_esperadas):
                # C3 ("comparação de CONJUNTOS: faltar OU sobrar linha
                # reprova"): o número de `<p>` que o navegador viu dentro
                # do timbre diverge do número de linhas que o servidor
                # declarou (`Escritorio.linhas_do_timbre`) — um `<p>` a
                # mais ou a menos no template/CSS, sem precisar adivinhar
                # QUAL.
                motivos.append(
                    f"número de linhas do timbre no papel ({len(filhos)}) diverge do "
                    f"número declarado pelo servidor ({len(linhas_esperadas)})"
                )

            # C2 da DL-029: o piso de contraste é POR LINHA, do tamanho e
            # peso REALMENTE renderizados (`medida["fonte_das_linhas"]`,
            # perguntado ao navegador em `_SCRIPT_DO_SUBPROCESSO` — nunca
            # deduzido de token CSS). Faltar essa informação (subprocesso
            # antigo, ou o `querySelectorAll` não achou nada) é falha de
            # INFRAESTRUTURA desta medição, não veredito sobre o produto:
            # sem ela não há como aplicar o WCAG com confiança.
            fonte_das_linhas = medida.get("fonte_das_linhas")
            if fonte_das_linhas is None or len(fonte_das_linhas) != len(linhas_esperadas):
                _recusar(
                    f"{nome}: a medição de tamanho/peso de fonte por linha "
                    f"('fonte_das_linhas') veio ausente ou com contagem incompatível "
                    f"({fonte_das_linhas!r}) — não é possível aplicar o piso de contraste "
                    "do WCAG 2.2 sem saber o tamanho/peso REAL de cada linha."
                )
            razoes_minimas = [
                _razao_minima_wcag_para_linha(fonte["tamanho_px"], fonte["peso"])
                for fonte in fonte_das_linhas
            ]

            localizacoes_no_pdf = _localizar_linhas_do_timbre_no_documento(
                caminho_pdf, linhas_esperadas, razoes_minimas
            )

            linhas_no_pdf = []
            for indice, linha in enumerate(linhas_esperadas):
                filho_da_linha = filhos[indice] if indice < len(filhos) else None
                visivel_no_navegador = bool(filho_da_linha and filho_da_linha.get("visivel"))
                legivel = visivel_no_navegador and not _tinta_invisivel(
                    filho_da_linha.get("cor_efetiva") if filho_da_linha else None
                )
                presente_no_pdf = linha in texto_pdf

                localizacao = localizacoes_no_pdf[indice]
                folha_da_linha = localizacao["folha"]
                pixels_com_contraste = localizacao["pixels_com_contraste"]
                contraste_maximo_medido = localizacao["contraste_maximo_medido"]
                razao_minima_exigida = razoes_minimas[indice]
                # C2, regra DUPLA e DISTINGUÍVEL (exigência do
                # arquiteto-senior): duas causas de reprovação diferentes,
                # nunca a mesma mensagem para as duas.
                # - CONTRASTE insuficiente: o pixel mais escuro da faixa já
                #   fica abaixo do piso WCAG desta linha — nenhuma
                #   quantidade de pixels ajudaria (a tinta é CLARA demais).
                # - CONTAGEM insuficiente: o contraste do pixel mais
                #   escuro passa o piso, mas poucos pixels alcançam esse
                #   nível — a tinta é escura o bastante, mas a ÁREA
                #   pintada é pequena demais (ex.: `font-size: 1px`).
                contraste_insuficiente = contraste_maximo_medido < razao_minima_exigida
                tinta_visivel_no_papel = (
                    not contraste_insuficiente
                    and pixels_com_contraste >= PISO_PIXELS_ESCUROS_POR_LINHA
                )

                # C3: LISTA (posição = a mesma de `linhas_esperadas`),
                # nunca um dicionário chaveado por texto — duas linhas
                # IGUAIS colapsariam na mesma chave (a fenda que o K2
                # mediu em `linhas_no_pdf[linha] = {...}`).
                linhas_no_pdf.append(
                    {
                        "texto": linha,
                        "visivel_no_navegador": visivel_no_navegador,
                        "legivel": legivel,
                        "presente_no_pdf": presente_no_pdf,
                        "folha": folha_da_linha,
                        "razao_minima_wcag_exigida": razao_minima_exigida,
                        "contraste_maximo_medido": round(contraste_maximo_medido, 3),
                        "pixels_com_contraste_no_papel": pixels_com_contraste,
                        "tinta_visivel_no_papel": tinta_visivel_no_papel,
                    }
                )
                if not visivel_no_navegador:
                    motivos.append(f"linha do timbre NÃO visível sob impressão: {linha!r}")
                elif not legivel:
                    motivos.append(f"linha do timbre com tinta de alfa zero (ilegível): {linha!r}")
                if not presente_no_pdf:
                    motivos.append(f"linha do timbre AUSENTE do texto do PDF: {linha!r}")
                elif folha_da_linha is not None and folha_da_linha != 1:
                    # C1/K7 (BL-410): a linha ESTÁ no papel, só que NÃO na
                    # primeira folha — nomeia PAGINAÇÃO, nunca "0 pixels
                    # escuros" (a mensagem que a rodada 10 flagrou como
                    # culpando a tinta por um problema de layout).
                    motivos.append(
                        f"linha do timbre está na folha {folha_da_linha}, não na folha 1: {linha!r}"
                    )
                elif contraste_insuficiente:
                    # C2: CONTRASTE, não contagem — a tinta é clara demais
                    # para o tamanho/peso REAL desta linha, medido contra
                    # o piso do WCAG 2.2 (empréstimo declarado — ver o
                    # comentário de RAZAO_MINIMA_WCAG_TEXTO_NORMAL).
                    motivos.append(
                        f"linha do timbre com CONTRASTE insuficiente contra o papel: {linha!r} — "
                        f"{contraste_maximo_medido:.2f}:1 medido, mínimo exigido "
                        f"{razao_minima_exigida:.1f}:1 (WCAG 2.2, 1.4.3)"
                    )
                elif not tinta_visivel_no_papel:
                    # C2: CONTAGEM, não contraste — a tinta É escura o
                    # bastante (o pixel mais escuro passa o piso do WCAG),
                    # mas a ÁREA pintada é pequena demais (ex.:
                    # `font-size: 1px`) para alcançar o piso de pixels.
                    motivos.append(
                        "linha do timbre com POUCOS PIXELS de tinta visível: "
                        f"{linha!r} — {pixels_com_contraste} pixel(s) com contraste "
                        f"suficiente na faixa esperada, piso exigido "
                        f"{PISO_PIXELS_ESCUROS_POR_LINHA}"
                    )
            entrada["linhas_do_timbre"] = linhas_no_pdf

            if entrada["pdf_contem_marca_do_fornecedor"]:
                motivos.append(
                    f"identificador do fornecedor ({marca_do_fornecedor!r}, normalizado: "
                    f"{marca_do_fornecedor_normalizada!r}) presente no PDF (busca normalizada — "
                    "caixa, espaço, pontuação e separadores desprezados)"
                )
            if campo_com_marca is not None:
                motivos.append(
                    f"identificador do fornecedor ({marca_do_fornecedor!r}) presente no metadado "
                    f"{campo_com_marca!r} do PDF ({metadados_pdf[campo_com_marca]!r}) — não é "
                    "tinta na folha, mas é identificação de quem vende o software no ARQUIVO "
                    "que o escritório entrega ao cliente"
                )

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
