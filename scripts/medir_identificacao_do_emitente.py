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
EM COR (`pdftoppm`, mesma dependência de sistema de `_texto_do_pdf`, ver
`_rasterizar_pagina` — BL-429/DE-060, décima primeira auditoria: era
`-gray` até essa correção, e cinza é um SUBSTITUTO que mede 2,1× mais
contraste do que existe em tinta colorida), localiza a posição REAL de
cada linha do timbre no PDF exportado (`pdftotext -bbox`, ver
`_palavras_da_pagina` e `_bbox_da_linha`/`_localizar_bloco_do_timbre` — a
posição de um objeto de texto no PDF não depende da cor com que ele foi
pintado) e exige uma contagem de pixels com CONTRASTE suficiente contra o
papel acima de um piso medido (`_diagnostico_de_contraste_na_faixa_cor`,
`PISO_PIXELS_ESCUROS_POR_LINHA` — DL-029, C2: contraste MEDIDO contra o
fundo da própria folha, EM COR, com a fórmula de três canais do WCAG 2.2
aplicada POR LINHA, não um limiar fixo de luminância nem uma razão única
escolhida a dedo. Ver o comentário de `RAZAO_MINIMA_WCAG_TEXTO_NORMAL`).
É a pergunta do contador — "tem tinta que CONTRASTA com o papel onde
deveria ter?" — e ela SOMA às checagens anteriores (DOM: `checkVisibility`
+ área + alcançabilidade; `_tinta_invisivel`: alfa zero, mais barato,
continua rodando primeiro), nunca as substitui.

**Falha de infraestrutura é distinguível de falha de conteúdo** (BL-356).
Códigos de saída:

- `0`: sucesso — todas as telas derivadas saem com o emitente completo.
- `1`: **REPROVADO** — o script rodou até o fim, mas ao menos uma tela saiu
  sem o emitente completo. É um achado sobre o PRODUTO.
- `2`: **Recusado** — falha de infraestrutura (banco ausente, poppler-utils
  ausente, Python do sistema sem Playwright, Chromium indisponível, zero
  telas derivadas). Não é um veredito sobre o produto.

**Limites declarados (nível 2/3 — DE-054, medidos e registrados, não
fechados: o Fred decidiu não comprá-los agora), no formato da DE-056:**

- **M3/BL-445:** este instrumento mede a identificação do **ESCRITÓRIO**
  na folha 1. **Não** mede empresa, período, nem numeração de folha, e
  **não** mede nada nas folhas 2..N do documento.
- **M5/BL-447:** a ordem das linhas casadas é a ordem do **DOM**
  (`querySelectorAll`), não a ordem de leitura no papel —
  `flex-direction: column-reverse` inverte o timbre visualmente e PASSA.
- **M13/BL-454:** o isolamento do timbre entre escritórios diferentes é
  provado no **contexto do servidor** (`apps/tenancy/tests/
  test_bl282_timbre_escritorio.py`), não na tinta que este instrumento
  mede.

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
# ⚠️ **A fronteira do C5, redação corrigida na décima segunda auditoria
# (M2, docs/auditorias/2026-09-20-dl-029-dl-030-rodada-12.md)** — a
# redação anterior da DE-061 dizia "no conteúdo que o documento controla,
# isto é, tinta na folha e metadados do arquivo": uma ENUMERAÇÃO DE DOIS
# CANAIS, a mesma forma que a DE-056 proíbe, cometida DENTRO da correção
# que fechava exatamente essa forma de defeito para outro campo. MEDIDO
# pelo auditor: um `<a href="https://dataledger.com.br/">` inócuo no
# corpo do documento grava `/URI (https://dataledger.com.br/)` como
# anotação de link no PDF — um TERCEIRO canal, que não é tinta (invisível
# a `pdftotext`, que só lê o TEXTO âncora, nunca o ALVO do link) nem
# metadado clássico (ausente do dicionário `Info` que `_metadados_do_pdf`
# lê) — e passava com `exit 0`, com o domínio do fornecedor clicável
# dentro do arquivo entregue ao cliente (o BL-404 por outro canal). A
# redação correta, adotada aqui, TROCA A LISTA POR UM CRITÉRIO: o C5 vale
# para **tudo que o arquivo exportado carrega e que o template ou a
# folha de estilo podem suprimir**, excluída a faixa que o navegador
# acrescenta por fora e que nenhuma folha de estilo alcança (BL-332).
# Anotação de link é controlada INTEIRAMENTE pelo template (é o `<a
# href>` que o Django escreve) — está DENTRO do critério, mesmo sem
# aparecer em nenhuma lista.
#
# A correção tem TRÊS frentes, agora — as duas que o K1 pediu, mais a
# que o M2 acrescentou:
#
# 1. DERIVAR o identificador de UMA fonte, nunca repeti-lo aqui
#    (AGENTS.md §8: duas cópias do mesmo texto divergem assim que uma for
#    editada sem a outra) — `_derivar_marca_do_fornecedor`, abaixo, lê
#    `templates/base.html`.
# 2. Perguntar por PROPRIEDADE (ausência normalizada: caixa, espaço,
#    pontuação e separadores desprezados), não por substring literal —
#    `_normalizar_para_busca_do_fornecedor`, abaixo.
# 3. Varrer TAMBÉM as anotações de link do PDF, com a MESMA normalização
#    — `_anotacoes_de_link_do_pdf`/`_anotacao_de_link_com_marca_do_
#    fornecedor`, logo depois de `_checar_marca_do_fornecedor_nos_
#    metadados` (M2/BL-444).
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
# BL-501 (achado A3 da auditoria da DL-034, docs/auditorias/2026-09-21-
# dl-034-rodada-1.md): o critério 4 do plano DL-034 ("o bloco do item 51,
# NBC TG 26 R5, sai em CADA página impressa") tinha UMA medição manual, de
# uma pessoa, e NENHUMA guarda versionada — a única linha do repositório
# que conhece `.identificacao-do-documento` era
# `apps/contabilidade/tests/test_dl034_tela_do_balanco.py:659`, que mede
# PRESENÇA DE CLASSE NO HTML SERVIDO, nunca TINTA NO PAPEL. O auditor
# mediu, em cópia isolada (BL-311): `@media print {
# .identificacao-do-documento { display: none; } }` apaga o bloco de
# TODAS as folhas com `1810 passed, 14 skipped` — porque o job de CI
# (`scripts/medir_identificacao_do_emitente.py`, ANTES desta correção) só
# conhecia `.timbre-impressao` (o ESCRITÓRIO, RC-97), nunca o bloco da
# ENTIDADE (RC-95).
#
# Esta seção estende o MESMO instrumento — reusa `_medir_no_navegador`
# (agora parametrizado, ver o comentário lá) para o MESMO tipo de
# medição: navegação real, PDF A4 de verdade, sonda de visibilidade —
# mas para um seletor e um conjunto de telas DIFERENTES: as de CLASSE 2
# (demonstração contábil, `docs/projeto/personalizacao-de-relatorio.md`
# §1), não as de classe 1 (Balancete/Diário/Razão, que têm TIMBRE do
# escritório e NUNCA este bloco — são documentos de CONFERÊNCIA, sem
# forma fixada por norma).
# ---------------------------------------------------------------------------

SELETOR_IDENTIFICACAO_DO_DOCUMENTO = ".identificacao-do-documento"
SELETOR_IDENTIFICACAO_DO_DOCUMENTO_FILHOS = ".identificacao-do-documento p"

# Piso de regressão, MESMA lógica de `TELAS_MINIMAS_COM_TIMBRE_ESPERADAS`
# (ver o comentário completo lá sobre por que um piso pequeno e
# versionado, ao lado da derivação que cresce sozinha): hoje só o Balanço
# (DL-034) é classe 2. Um módulo novo que ganhe demonstração própria
# (Fiscal, Folha) e o comentário deste piso não crescer junto é erro
# visível, revisado — nunca divergência silenciosa entre duas cópias.
TELAS_MINIMAS_COM_IDENTIFICACAO_DO_DOCUMENTO_ESPERADAS = frozenset({"contabilidade_web:balanco"})

_PADRAO_MARCADOR_IDENTIFICACAO_DO_DOCUMENTO = re.compile(
    r'class="[^"]*\bidentificacao-do-documento\b[^"]*"'
)

# Extrai o CONTEÚDO do bloco (para derivar o texto esperado — ver
# `_derivar_texto_da_identificacao_do_documento`, abaixo). Não confundir
# com o padrão de MARCADOR acima: aquele só confirma que a classe existe
# em algum lugar do HTML (para decidir "esta tela é candidata"); este lê
# o TEXTO de dentro para saber O QUE deveria repetir em cada página.
_PADRAO_BLOCO_IDENTIFICACAO_DO_DOCUMENTO = re.compile(
    r'<div class="identificacao-do-documento">(.*?)</div>', re.DOTALL
)
_PADRAO_TAG_HTML = re.compile(r"<[^>]+>")


def _derivar_texto_da_identificacao_do_documento(html_da_tela):
    """Lê o TEXTO do bloco `.identificacao-do-documento` diretamente do
    HTML que o SERVIDOR escreveu para aquela requisição — razão social,
    CNPJ e data-base variam por empresa e por data-base, então NENHUM
    literal fixo poderia representar "o que deveria estar em cada
    página" para qualquer empresa. Mesma filosofia de
    `_derivar_marca_do_fornecedor` (acima): o instrumento pergunta ao
    PRODUTO o que ele prometeu escrever na folha 1 (onde `pdftotext`
    já prova que o bloco existe — é o HTML que o Django serviu) e depois
    confere se esse MESMO texto aparece em CADA página do PDF exportado.
    Isto também evita hardcodar, no instrumento, a prosa de uma norma
    contábil (NBC TG 26) — o instrumento não é o lugar para reafirmar o
    que o item 51 exige, só para conferir que o produto cumpriu o que
    ele MESMO escreveu.

    Devolve o texto SEM tags e SEM NENHUM espaço (mesma normalização de
    `_bbox_da_linha`, por não ter mesma razão de existir: `pdftotext
    -layout` tokeniza por espaço VISUAL, que não bate 1:1 com o espaço do
    HTML de origem — comparar ignorando espaço nos dois lados evita falso
    alarme por diferença de quebra de linha/indentação, sem perder
    nenhuma palavra) — ou `None` se a tela não tiver o bloco (não é
    candidata a esta checagem; `main` trata isso como o bloco NUNCA
    tendo existido, não como "vazio mas presente")."""
    casamento = _PADRAO_BLOCO_IDENTIFICACAO_DO_DOCUMENTO.search(html_da_tela)
    if casamento is None:
        return None
    texto_sem_tags = _PADRAO_TAG_HTML.sub(" ", casamento.group(1))
    texto_sem_tags = html.unescape(texto_sem_tags)
    return "".join(texto_sem_tags.split())


# CNPJ sintético FIXO (não gerado a cada execução) — a mesma convenção de
# `CNPJ_EMPRESA_DE_MEDICAO`, acima, para esta empresa ser IDEMPOTENTE
# entre execuções contra o MESMO banco (`_preparar_empresa_classe_2`,
# abaixo, reaproveita se já existir em vez de recriar — mesma economia
# que `semear_base_de_medicao.py` já aplica à base padrão).
CNPJ_EMPRESA_DE_MEDICAO_CLASSE_2 = "44555666000280"

# Número de pares (conta do Ativo Circulante + conta de Passivo
# Circulante, cada par com um lançamento que soma o MESMO valor aos
# dois) que produz, MEDIDO contra o template e o CSS desta revisão, um
# Balanço de SEIS folhas — o piso do critério de aceite 2 da correção da
# DL-034 (BL-501). Não é uma conta redonda por estética: é o número
# medido (ver o relatório da etapa) que faz `total_de_paginas == 6` com
# ESTE template. Se o template mudar de forma que a linha fique mais
# alta/baixa, este número pode precisar de recalibração — mesma
# fragilidade que a direção de arte já declara para os pisos de
# densidade (§4.8: "número sem método é opinião com casas decimais").
N_PARES_PARA_SEIS_FOLHAS = 60


def _preparar_empresa_classe_2(escritorio):
    """Cria (ou REAPROVEITA, se já existir — idempotente) uma empresa
    PRÓPRIA, sob o MESMO escritório da base de medição compartilhada, com
    um plano de contas grande o bastante para o Balanço sair em VÁRIAS
    folhas — BL-501 (auditoria da DL-034, achado A3) exige controle
    POSITIVO com pelo menos 6.

    ⚠️ **Por que uma empresa PRÓPRIA, nunca a `empresa` de
    `scripts/semear_base_de_medicao.py`.** MEDIDO nesta correção: a base
    padrão (73 contas, 4 níveis) não classifica NENHUMA conta em
    circulante/não circulante (RC-106) — ela serve ao Balancete/Diário/
    Razão, que não exigem essa classificação. O Balanço daquela empresa
    fica PERMANENTEMENTE em estado de pendência (`pode_emitir=False`), e
    o bloco do item 51 nunca é renderizado (só existe no ramo
    `pode_emitir`) — a varredura deste instrumento contra a base padrão
    devolve ZERO telas de classe 2, não por regressão, mas porque a base
    não foi desenhada para esta pergunta. `scripts/semear_base_de_
    medicao.py` é COMPARTILHADO por outras medições já publicadas
    (`docs/projeto/direcao-de-arte.md` §4.8, piso de densidade) — não é
    desta correção acrescentar uma responsabilidade nova a ele; uma
    empresa PRÓPRIA, sob o mesmo escritório (mesmo usuário autenticado
    enxerga as duas — autorização é por ESCRITÓRIO, não por empresa
    dentro dele, ver `apps.contabilidade.views_web._pode_ler`), é a
    correção sem acoplar duas medições com propósitos diferentes.

    Devolve `(empresa, conta)` — `conta` é a primeira conta ANALÍTICA da
    empresa nova (para preencher `kwargs_conhecidos["conta_id"]` de rotas
    que precisem, hoje nenhuma de classe 2, mas a assinatura fica igual
    à de `_descobrir_telas_com_timbre`/`_descobrir_telas_com_
    identificacao_do_documento` por uniformidade)."""
    from decimal import Decimal

    from django.utils import timezone

    from apps.contabilidade.models import (
        ClassificacaoPatrimonial,
        Conta,
        NaturezaConta,
        TipoConta,
        TipoPartida,
    )
    from apps.contabilidade.services import criar_lancamento
    from apps.empresas.models import Empresa

    empresa_existente = Empresa.objects.filter(
        cnpj=CNPJ_EMPRESA_DE_MEDICAO_CLASSE_2, escritorio=escritorio
    ).first()
    if empresa_existente is not None:
        conta_existente = Conta.objects.filter(
            empresa=empresa_existente, aceita_lancamento=True
        ).first()
        return empresa_existente, conta_existente

    D = NaturezaConta.DEVEDORA
    C = NaturezaConta.CREDORA

    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa de Medição — Balanço de Seis Folhas (BL-501) Ltda",
        cnpj=CNPJ_EMPRESA_DE_MEDICAO_CLASSE_2,
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="ATIVO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        aceita_lancamento=False,
    )
    # O CONTÊINER em si NÃO leva classificação — só as FOLHAS, abaixo
    # (`contas_com_classificacao_aninhada` recusa os DOIS níveis
    # classificados ao mesmo tempo — mesma regra que
    # `cenario_classificado`, em test_dl034_tela_do_balanco.py, já segue).
    circulante = Conta.objects.create(
        empresa=empresa,
        conta_pai=ativo,
        codigo="1.1",
        nome="Ativo Circulante",
        tipo=TipoConta.ATIVO,
        natureza=D,
        aceita_lancamento=False,
    )
    passivo = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    passivo_circulante = Conta.objects.create(
        empresa=empresa,
        conta_pai=passivo,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    # Receita SEM lançamento de encerramento — cria o "lucro não
    # transferido" que o RC-104 pede (BL-503), com o MESMO valor que a
    # auditoria da DL-034 mediu (R$ 77.777,77), para esta medição também
    # provar o critério de aceite 3 (a nota de reconciliação em CADA
    # folha que traz um dos dois grandes totais) no MESMO documento que
    # prova o critério 2 — um só PDF cobre os dois.
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="4",
        nome="Receita de serviços",
        tipo=TipoConta.RECEITA,
        natureza=C,
        aceita_lancamento=True,
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        conta_pai=circulante,
        codigo="1.1.000",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao_patrimonial=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )

    hoje = timezone.localdate()
    for i in range(1, N_PARES_PARA_SEIS_FOLHAS + 1):
        conta_ativo = Conta.objects.create(
            empresa=empresa,
            conta_pai=circulante,
            codigo=f"1.1.{i:03d}",
            nome=f"Cliente sintético {i:03d}",
            tipo=TipoConta.ATIVO,
            natureza=D,
            classificacao_patrimonial=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
        )
        conta_passivo = Conta.objects.create(
            empresa=empresa,
            conta_pai=passivo_circulante,
            codigo=f"2.1.{i:03d}",
            nome=f"Fornecedor sintético {i:03d}",
            tipo=TipoConta.PASSIVO,
            natureza=C,
            classificacao_patrimonial=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
        )
        valor = Decimal("100.00") + Decimal(i)
        criar_lancamento(
            empresa=empresa,
            data=hoje,
            historico=f"Lançamento sintético {i:04d} — BL-501/BL-503 (medição)",
            itens=[
                {"conta": conta_ativo, "tipo": TipoPartida.DEBITO, "valor": valor},
                {"conta": conta_passivo, "tipo": TipoPartida.CREDITO, "valor": valor},
            ],
        )
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Receita de serviços ainda não transferida ao PL (BL-503, medição)",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("77777.77")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("77777.77")},
        ],
    )
    return empresa, caixa


def _descobrir_telas_com_identificacao_do_documento(cliente, empresa, conta):
    """DERIVA o conjunto de telas do produto que carregam
    `.identificacao-do-documento` — MESMA varredura de rotas de
    `_descobrir_telas_com_timbre` (ver a docstring de lá para o porquê de
    derivar em vez de enumerar à mão, BL-363), trocado só o MARCADOR
    procurado. Não reaproveita a função de lá diretamente: os dois
    marcadores identificam CONJUNTOS DIFERENTES de tela (Balancete/
    Diário/Razão têm timbre e NUNCA este bloco — são classe 1; o Balanço
    tem os DOIS, porque carrega tanto a identificação do ESCRITÓRIO
    quanto a da EMPRESA cliente), e uma varredura ÚNICA tentando os dois
    marcadores ao mesmo tempo obscureceria qual tela pertence a qual
    critério normativo — RC-95 (item 51, entidade) não é RC-97 (timbre,
    escritório), mesmo as duas aparecendo juntas no Balanço hoje."""
    from django.urls import reverse

    kwargs_conhecidos = {"empresa_id": empresa.id, "conta_id": conta.id}
    periodo = f"?inicio={medir_impressao.PERIODO_INICIO}&fim={medir_impressao.PERIODO_FIM}"

    telas = {}
    for nome_completo, chaves in _todas_as_rotas_get_nomeadas():
        if not chaves.issubset(kwargs_conhecidos):
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
        if not _PADRAO_MARCADOR_IDENTIFICACAO_DO_DOCUMENTO.search(html_da_tela):
            continue
        telas[nome_completo] = {
            "rota": nome_completo,
            "url": url,
            "html": medir_impressao._com_css_local(html_da_tela),
        }
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
#
# BL-436/BL-437 (décima segunda auditoria, verificação independente,
# rodada 3 da DL-029) -- DE-060: `tamanho_px` (getComputedStyle) é a
# fonte DECLARADA, e a rodada 2 já a usava para DUAS coisas -- o piso de
# TAMANHO (corrigido naquela rodada, via bbox do papel) e a
# CLASSIFICAÇÃO "texto grande/normal" do WCAG (_razao_minima_wcag_para_
# linha, NUNCA corrigida). MEDIDO pelo verificador: `font-size: 24px +
# transform: scale(0.6)` renderiza a ~14,4px no papel -- abaixo do piso
# de "texto grande" (18pt/24px) -- mas a CLASSIFICAÇÃO usava o 24px
# DECLARADO, continuava chamando a linha de "grande" e emprestava o piso
# de contraste mais FROUXO (3:1) a uma linha que já não é grande.
# FALSO CONFORME: reprovação que deveria acontecer (contraste 4,17:1,
# abaixo do piso de 4,5:1 correto) não acontecia.
#
# CORREÇÃO: pergunta a ESCALA ACUMULADA diretamente ao navegador --
# `escala_acumulada`, abaixo. `tamanho_efetivo_px = tamanho_px *
# escala_acumulada` é o tamanho REALMENTE renderizado, em px CSS --
# independente de FONTE (substitui FATOR_ALTURA_DE_GLIFO_SOBRE_FONTE_
# DECLARADA da rodada 2, que MEDIA a altura do glifo no bbox do papel e
# dividia por uma razão MEDIDA só em UMA família tipográfica --
# BL-437: a razão diverge entre famílias -- 1,088 no serif do produto,
# ~0,93-0,97 em monospace/sans-serif --, então o piso de 11px efetivo
# variava de família para família, e `font-family: monospace` a 11px
# (exatamente o piso) reprovava por FALSO ALARME, com "9,85px"
# relatado para um texto que renderiza a 11px de verdade).
#
# **Tentativa 1, DESCARTADA, e por quê** (a proposta original desta
# correção): `getBoundingClientRect().height / offsetHeight`.
# `getBoundingClientRect` INCLUI `transform`/`zoom`/ancestral;
# `offsetHeight` NÃO inclui nenhuma delas -- MEDIDO que funciona nos 5
# casos sintéticos testados (own transform, zoom, ancestral, combinação,
# controle). Mas `offsetHeight` é um INTEIRO (arredondado pelo CSSOM
# View, ao contrário de `getBoundingClientRect`, que é subpixel) --
# MEDIDO contra o PRODUTO REAL (não sintético): `font-family: serif` a
# EXATOS 11px (sem transform/zoom nenhum, escala verdadeira = 1,0)
# relatava `escala_offset = 0,9961`, `tamanho_efetivo = 10,957px` --
# ABAIXO do piso de 11px -- FALSO ALARME, o mesmo defeito que esta
# correção existe para fechar, só que por arredondamento de layout em
# vez de família tipográfica. `offsetHeight` some INTEIRO mesmo quando
# a altura de linha real é fracionária (ex.: 13,6px vira 14), e ISSO
# introduz ruído de até ~0,5px em QUALQUER caso, com ou sem sabotagem.
#
# **Tentativa 2, DESCARTADA na décima segunda auditoria (M1,
# docs/auditorias/2026-09-20-dl-029-dl-030-rodada-12.md)** — decompunha a
# ESCALA VERTICAL da matriz de `transform` computada
# (`getComputedStyle(el).transform`) e multiplicava por `cs.zoom`,
# ANDANDO POR TODOS OS ANCESTRAIS. Resolvia os 5 casos sintéticos
# testados na rodada anterior (own transform, zoom, ancestral,
# combinação, controle) — mas lia DUAS PROPRIEDADES NOMEADAS
# (`cs.transform`, `cs.zoom`), e a propriedade CSS `scale:` (a forma
# INDIVIDUAL de escrever escala, hoje recomendada ao lado de `rotate:` e
# `translate:` como alternativa moderna a `transform: scale(...)`) fica
# em `getComputedStyle(el).scale` — um TERCEIRO campo, nunca lido.
# MEDIDO pelo auditor: `scale: 0.6` produz `cs.transform === 'none'` e
# `cs.scale === '0.6'` — a MESMA folha A4 exportada (pixels de tinta e
# bbox do glifo idênticos ao milésimo de ponto ao `transform: scale(0.6)`
# equivalente), com `escala_acumulada` lida como 1,0 em vez de 0,6. Isso
# reabria o BL-428 (piso de tamanho) E o BL-436 (classificação "texto
# grande" do WCAG) inteiros, com uma única palavra de CSS. **A correção
# NÃO troca a leitura por uma lista maior** (`cs.transform`, `cs.zoom`,
# `cs.scale`, e amanhã `cs.rotate`, `cs.translate`, `cs.offsetPath`,
# `cs.perspective` — a DÉCIMA SÉTIMA ocorrência da classe de defeito que
# a DE-055 existe para proibir: "guarda derivada de uma LISTA, não
# aguenta" — AGENTS.md §8).
#
# **Tentativa 3, ADOTADA:** não lê NENHUMA propriedade CSS de
# transformação — pergunta a ESCALA VISUAL COMPOSTA diretamente à
# geometria renderizada, do jeito que o auditor recomendou. Insere, como
# ÚLTIMO FILHO de cada linha do timbre, um elemento-SONDA com altura CSS
# CONHECIDA (`display:inline-block; height:100px; width:0`) e lê
# `getBoundingClientRect().height / 100`. Como a sonda é FILHA da própria
# linha, ela herda toda transformação aplicada a ela e a QUALQUER
# ancestral — via `transform`, `zoom`, `scale`, `rotate` (componente
# vertical), ou qualquer propriedade futura que o CSSWG venha a
# especificar — sem o instrumento precisar SABER o nome de nenhuma delas.
# É geometria COMPOSTA e SUBPIXEL (`getBoundingClientRect`, não
# `offsetHeight` — ver por que a tentativa 1 foi descartada, acima), a
# mesma classe de correção que fechou C3 (contagem de linhas por
# PROPRIEDADE do servidor, não por lista). A sonda é removida do DOM
# logo em seguida — não fica na página que vira o PDF.
js_fonte_das_linhas = (
    "(seletor) => {"
    "  const escalaComposta = (elemento) => {"
    "    const sonda = document.createElement('span');"
    "    sonda.style.cssText = 'display:inline-block;height:100px;width:0;';"
    "    elemento.appendChild(sonda);"
    "    const altura = sonda.getBoundingClientRect().height;"
    "    sonda.remove();"
    "    return altura / 100;"
    "  };"
    "  return [...document.querySelectorAll(seletor)].map((el) => {"
    "    const cs = getComputedStyle(el);"
    "    const declarado = parseFloat(cs.fontSize);"
    "    const escala = escalaComposta(el);"
    "    return {"
    "      tamanho_px: declarado,"
    "      peso: parseInt(cs.fontWeight, 10) || 400,"
    "      escala_acumulada: escala,"
    "      tamanho_efetivo_px: declarado * escala,"
    "    };"
    "  });"
    "}"
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


def _medir_no_navegador(
    pasta_html,
    pasta_saida,
    nomes_das_telas,
    seletor_container=SELETOR_TIMBRE_CONTAINER,
    seletor_filhos=SELETOR_TIMBRE_FILHOS,
):
    """BL-501 (achado A3 da auditoria da DL-034): os dois parâmetros de
    seletor ganharam PADRÃO (o timbre do escritório, único uso até esta
    correção) em vez de ficarem embutidos como constante fixa dentro
    desta função — para o MESMO subprocesso (navegação real, PDF A4,
    sonda de visibilidade e de fonte) medir também o bloco de
    identificação do item 51 (`.identificacao-do-documento`, NBC TG 26 R5
    — RC-95), sem reimplementar a chamada ao Python do sistema nem o
    script do subprocesso. Chamadas existentes (timbre do escritório)
    continuam idênticas — os dois novos parâmetros são POSICIONAIS por
    padrão, nunca exigidos."""
    especificacao = json.dumps(
        {
            "diretorio_sonda": _DIRETORIO_SONDA,
            "pasta_html": str(pasta_html),
            "pasta_saida": str(pasta_saida),
            "telas": nomes_das_telas,
            "seletor_container": seletor_container,
            "seletor_filhos": seletor_filhos,
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
    correção.

    BL-425 (achado da verificação independente, depois do C2 fechar) —
    LIMITE DECLARADO, não fechado nesta etapa: este texto (`-layout`) e o
    bbox de `_palavras_da_pagina` (`-bbox`) são DOIS MECANISMOS de
    extração do poppler, e ELES DIVERGEM em tamanhos de fonte extremos.
    MEDIDO: com `font-size: 4px` no timbre, `pdftotext -layout` insere
    ESPAÇOS ESPÚRIOS dentro das palavras ("Rua Sin tética 100, Sala 2 -
    P almas/TO") — a heurística de layout do poppler, que tenta
    reconstruir colunas e espaçamento visual, interpreta o espaçamento
    entre glifos minúsculos como separação de palavra. O resultado:
    `linha in texto_pdf` (a checagem de `presente_no_pdf`, em `main`)
    devolve `False` para uma linha que, na verdade, ESTÁ no papel —
    `_bbox_da_linha` (que concatena palavras SEM espaço antes de
    comparar, ver a docstring dela) ENCONTRA a mesma linha sem problema
    (29 pixels de contraste medido, razão 9,00:1 — tinta real, presente).

    **Consequência**: o veredito relatado, hoje, é "linha do timbre
    AUSENTE do texto do PDF" — uma frase que, neste caso ESPECÍFICO,
    descreve mal o que aconteceu (a linha está no papel; o mecanismo de
    extração plana é que não a reproduziu). `presente_no_pdf` é checado
    ANTES de tamanho/contraste/contagem em `main` (ver a ORDEM das
    checagens ali), então essa mensagem imprecisa VENCE mesmo quando
    `TAMANHO_MINIMO_RENDERIZADO_PX` (BL-424) reprovaria a mesma linha por
    um motivo mais correto (4px está bem abaixo do piso de 11px — a tela
    REPROVA de qualquer forma, só que com o nome errado da causa).
    Fechar isso de verdade exigiria trocar `presente_no_pdf` por uma
    pergunta baseada em bbox (não em substring), o que é MAIS escopo do
    que esta etapa comprou — fica registrado, não escondido, e não
    fechado aqui."""
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


def _texto_da_pagina_sem_espaco(caminho_pdf, pagina):
    """BL-501: texto de UMA página do PDF (`pdftotext -layout -f N -l N`
    — mesma técnica de `_texto_do_pdf`, restrita a uma página, MESMA
    técnica de recorte de `_palavras_da_pagina`), sem NENHUM espaço —
    mesma normalização de `_derivar_texto_da_identificacao_do_documento`,
    para os dois lados da comparação usarem a MESMA régua (`pdftotext
    -layout` insere espaço por reconstrução de COLUNA, que não bate 1:1
    com o espaço do HTML de origem; comparar ignorando espaço dos dois
    lados é a mesma correção que `_bbox_da_linha`/C1 já adotam para o
    timbre, aplicada aqui à pergunta "a página N contém X?").

    BL-378: `check=False` — `pdftotext` quebrado é a MESMA classe de
    falha de infraestrutura que os demais usos de poppler-utils neste
    módulo, nunca veredito sobre o produto."""
    resultado = subprocess.run(
        ["pdftotext", "-layout", "-f", str(pagina), "-l", str(pagina), str(caminho_pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        _recusar(
            f"'pdftotext -layout -f {pagina} -l {pagina}' falhou (código "
            f"{resultado.returncode}) ao processar {caminho_pdf} — falha de infraestrutura, "
            f"não veredito sobre o produto.\nerro: {resultado.stderr}"
        )
    return "".join(resultado.stdout.split())


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
# M2/BL-444 (décima segunda auditoria, achado do auditor-qa,
# docs/auditorias/2026-09-20-dl-029-dl-030-rodada-12.md) — TERCEIRO canal
# do C5, ao lado da tinta (`_texto_do_pdf`) e do dicionário `Info`
# (`_metadados_do_pdf`): a ANOTAÇÃO DE LINK (`/Annot` do tipo `/Link`,
# PDF Reference §8.4.5, campo `/A << /URI (...) >>`). Ver o comentário no
# topo do módulo (fronteira do C5 corrigida) para o porquê deste canal
# entrar no critério.
#
# **Por que ler os BYTES BRUTOS do arquivo, em vez de decodificar a
# árvore de objetos do PDF** (a mesma técnica que o auditor usou —
# `strings <pdf> | grep`): MEDIDO contra o PDF real exportado por este
# produto (Chromium/Skia, ver `_metadados_do_pdf`) que o dicionário de
# anotação NÃO é comprimido em fluxo de objetos — a string `/URI (...)`
# aparece LITERAL nos bytes do arquivo, do mesmo jeito que `strings` a
# encontrou. **Limite declarado, não escondido**: se o motor de
# exportação mudar para um que comprima objetos (fluxo `/ObjStm`), esta
# leitura para de encontrar anotações comprimidas, e passaria a exigir um
# parser de estrutura de PDF de verdade — não é o caso hoje, e
# `scripts/test_medir_identificacao_do_emitente.py` prova o caminho
# funcionando contra bytes de PDF reais (não só sintéticos).
_PADRAO_ANOTACAO_URI = re.compile(rb"/URI\s*\(((?:\\.|[^()\\])*)\)")


def _anotacoes_de_link_do_pdf(caminho_pdf):
    """Lista o ALVO (string dentro de `/URI (...)`) de TODAS as anotações
    de link do PDF — não o TEXTO ÂNCORA visível (que `_texto_do_pdf` já
    cobre), o DESTINO do link, que pode ser completamente diferente do
    que aparece escrito na página (exatamente a sabotagem do BL-444: o
    texto visível é "Emitido pelo sistema", o alvo é o domínio do
    fornecedor).

    Desescapa só as sequências que a especificação define dentro de uma
    PDF `(string)` literal (`\\(`, `\\)`, `\\\\`, e as demais fugas de
    uma barra invertida seguida de um caractere) — suficiente para uma
    URL, que não costuma usar as fugas octais de controle da
    especificação completa."""
    bytes_do_pdf = Path(caminho_pdf).read_bytes()
    alvos = []
    for bruto in _PADRAO_ANOTACAO_URI.findall(bytes_do_pdf):
        desescapado = re.sub(rb"\\(.)", rb"\1", bruto)
        try:
            alvos.append(desescapado.decode("utf-8"))
        except UnicodeDecodeError:
            # PDF não garante UTF-8 dentro de uma string literal — cai
            # para latin-1 (nunca falha: todo byte é um code point válido
            # nela), suficiente para a NORMALIZAÇÃO que _anotacao_de_
            # link_com_marca_do_fornecedor aplica em seguida (ASCII
            # minúsculo, o resto é descartado de qualquer forma).
            alvos.append(desescapado.decode("latin-1"))
    return alvos


def _anotacao_de_link_com_marca_do_fornecedor(anotacoes_de_link, marca_normalizada):
    """Devolve o primeiro ALVO de anotação de link cuja versão
    normalizada contém o identificador do fornecedor, ou `None` se
    nenhum contém — mesma normalização e mesmo contrato de
    `_checar_marca_do_fornecedor_nos_metadados` (par, não coincidência: o
    C5 é UMA pergunta — "o identificador aparece, em qualquer canal que o
    template controla?" —, feita a canais diferentes)."""
    for alvo in anotacoes_de_link:
        if marca_normalizada in _normalizar_para_busca_do_fornecedor(alvo):
            return alvo
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
#
# PAPEL REBAIXADO (BL-424, achado da verificação independente após o C2
# fechar): este piso já foi a ÚNICA guarda contra tinta ausente E contra
# texto minúsculo — as duas perguntas produziam "poucos pixels" contra um
# limiar de luminância fixo, então uma contagem bastava para as duas.
# Isso NÃO é mais verdade: "a tinta sumiu?" agora é pergunta de
# CONTRASTE (`_diagnostico_de_contraste_na_faixa`, contra o piso do
# WCAG — ver `RAZAO_MINIMA_WCAG_TEXTO_NORMAL`), e "o texto ficou pequeno
# demais?" agora é pergunta de TAMANHO (`TAMANHO_MINIMO_RENDERIZADO_PX`,
# abaixo). MEDIDO que a contagem sozinha, sem essas duas, deixava passar
# `font-size: 8px` com contraste altíssimo (19,8:1) e 57–58 pixels — mais
# que o piso, porque um traço grande o bastante em QUALQUER tamanho
# consegue contar 40 pixels contrastantes cedo. Este número continua
# valendo como SANIDADE RESIDUAL (um glifo real, no tamanho e contraste
# certos, sempre pinta uma quantidade generosa de pixels — controle nunca
# abaixo de ~324 com o oráculo de contraste, ver o comentário de
# `RAZAO_MINIMA_WCAG_TEXTO_NORMAL`), não como a guarda principal de
# nenhuma das duas perguntas que ele um dia respondeu sozinho.
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


def _razao_minima_wcag_para_linha(tamanho_efetivo_px, peso):
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
    um só para o timbre inteiro.

    BL-436 (verificação independente, rodada 3 da DL-029) — DE-060:
    `tamanho_efetivo_px` PRECISA ser o tamanho REALMENTE renderizado
    (`fonte_das_linhas[i]["tamanho_efetivo_px"]`, via `escala_acumulada`
    — ver o comentário de `js_fonte_das_linhas`), nunca o `tamanho_px`
    DECLARADO. MEDIDO: `font-size: 24px` + `transform: scale(0.6)`
    renderiza a ~14,4px — abaixo do piso de texto grande (24px) — mas
    classificar pelo DECLARADO (24px, "grande") emprestava o piso mais
    FROUXO (3:1) a uma linha que já não é grande, e um contraste de
    4,17:1 — abaixo do piso CORRETO de 4,5:1 — passava como conforme.
    Falso conforme, a mesma classe de defeito que a DE-060 existe para
    fechar: um argumento sobre comportamento ("a checagem de tamanho já
    protege isso") escrito no comentário e não medido — e a medição
    desmentiu."""
    eh_negrito = peso >= PESO_MINIMO_NEGRITO
    eh_grande = tamanho_efetivo_px >= TAMANHO_MINIMO_TEXTO_GRANDE_PX or (
        eh_negrito and tamanho_efetivo_px >= TAMANHO_MINIMO_TEXTO_GRANDE_NEGRITO_PX
    )
    return RAZAO_MINIMA_WCAG_TEXTO_GRANDE if eh_grande else RAZAO_MINIMA_WCAG_TEXTO_NORMAL


# BL-424 (verificação independente, achada depois do C2 fechar com o
# piso de contraste do WCAG): `PISO_PIXELS_ESCUROS_POR_LINHA = 40` era a
# ÚLTIMA constante do módulo ainda escolhida a dedo, sem derivar de
# propriedade nenhuma — a MESMA forma de `MARCA_DO_FORNECEDOR` (K1) e do
# `LIMIAR_LUMINANCIA_TINTA` (K4) que esta etapa inteira existe para
# aposentar. MEDIDO: com `font-size: 8px` no timbre, o texto é extraído,
# o contraste é altíssimo (19,8:1 e 9,29:1 — muito acima do piso do
# WCAG) e a CONTAGEM de pixels (57–58 na linha mais fraca) passa o piso
# de 40 — o instrumento aprova. Em 7px, a mesma linha mede 41/14 pixels
# e reprova; em 6px, 13/4. O piso de contagem, sozinho, aceita uma linha
# renderizada a menos de 1/6 do tamanho normal do produto (14px), porque
# ele nunca soube o que era "tamanho" — só contava pixels.
#
# **A pergunta que a contagem respondia mudou de dono.** Antes do C2,
# "a tinta sumiu?" e "o texto ficou minúsculo?" eram a MESMA pergunta,
# porque as duas produziam poucos pixels contra um limiar de luminância
# fixo. Depois do C2, "a tinta sumiu?" é pergunta de CONTRASTE (razão
# WCAG) — a contagem não decide mais isso. A ÚNICA coisa que sobrou para
# a contagem proteger é "o texto foi renderizado grande o bastante para
# ser lido?" — que é pergunta de TAMANHO, não de pixels pintados. E o
# instrumento JÁ PERGUNTA o tamanho renderizado ao navegador (`fonte_das_
# linhas`, usado por `_razao_minima_wcag_para_linha`) — só não FAZIA
# nada com essa resposta além de escolher o piso de contraste.
#
# **TAMANHO_MINIMO_RENDERIZADO_PX é ESCOLHA DECLARADA deste projeto, não
# um padrão publicado** — ao contrário do WCAG (contraste) e da definição
# textual de "texto grande" (18pt/14pt), NÃO existe um número de
# acessibilidade citável para "tamanho mínimo legível em PAPEL impresso"
# (o WCAG não define piso de tamanho; ele pressupõe que o leitor pode dar
# zoom — papel não tem zoom). Inventar uma norma aqui violaria o
# AGENTS.md ("não inventar exigência"). O valor abaixo é medido e
# justificado, mas continua sendo NOSSO, não do WCAG:
#
# 11px, o MESMO valor de `--tipo-2xs` em `static/css/base.css` — o
# tamanho que o próprio produto já declara, por escrito, como "o piso
# legível" (comentário de `kbd.tecla`, BL-283/B2: *"era 0.72em sobre
# --tipo-sm = 9,36px medidos, o menor texto da interface — pequeno
# demais... --tipo-2xs (11px) é o próprio piso legível já usado"*). Não é
# um número novo inventado para esta etapa — é o piso de legibilidade que
# a DIREÇÃO DE ARTE do produto já havia fixado, para OUTRO elemento
# (atalho de teclado na tela), antes da DL-029 existir. Usá-lo aqui é
# emprestar uma decisão JÁ TOMADA, não decidir de novo. Reusar o mesmo
# limite evita duas respostas diferentes para "que tamanho é pequeno
# demais neste produto" — o risco que a DE-056 nomeia.
#
# LIMITE DECLARADO, não escondido: aquele piso foi fixado para TELA, não
# para PAPEL — os dois meios têm resolução e distância de leitura
# diferentes, e não há medição própria de papel que sustente 11px como
# "correto" para documento impresso (só que é razoável, e não foi
# escolhido só para bater com o corte atual: MEDIDO que 8px passava antes
# desta correção — 11 é maior que 8, então a correção MUDA o veredito de
# 8px, não o preserva por acidente). **A pergunta "que tamanho mínimo o
# timbre pode ter numa folha real?" fica registrada como PE-58 — pendente,
# do Fred, a ser respondida olhando uma folha impressa de verdade, não
# medida por este instrumento.** Se o Fred decidir outro valor, ele
# substitui este, não o contrário.
TAMANHO_MINIMO_RENDERIZADO_PX = 11

# BL-437 (verificação independente, rodada 3 da DL-029) — a rodada 2
# comparava contra o papel dividindo a altura do bbox por
# `FATOR_ALTURA_DE_GLIFO_SOBRE_FONTE_DECLARADA`, uma razão MEDIDA em
# UMA família tipográfica só (a do produto, `FAMILIA_DA_FONTE` em
# `medir_impressao.py`) e generalizada para QUALQUER fonte — sem medir
# se a generalização valia. MEDIDO pelo verificador que NÃO vale:
# `font-family: monospace` mediu razão 0,9743; `serif`, 0,9269;
# `sans-serif`, 0,9351 — todas abaixo de 1,088. Consequência: o piso de
# 11px efetivo (declarado) virava ~12,3–12,9px nessas famílias, e
# `font-family: monospace` a exatos 11px — o PISO, sem sabotagem
# nenhuma de tamanho — reprovava por FALSO ALARME.
#
# Esta constante (e a divisão pelo bbox do papel) foi REMOVIDA — não
# ajustada. A correção substituta (`escala_acumulada`/`tamanho_efetivo_
# px`, ver o comentário de `js_fonte_das_linhas` em `_SCRIPT_DO_
# SUBPROCESSO`) pergunta a escala ao NAVEGADOR via
# `getBoundingClientRect()/offsetHeight` — geometria de layout, não
# métrica de fonte —, então não depende de família tipográfica nenhuma
# para nenhuma das duas perguntas que a antiga constante respondia
# (piso de tamanho E classificação "texto grande" do WCAG — ver
# `_razao_minima_wcag_para_linha`, abaixo, que agora recebe o tamanho
# EFETIVO, não mais o declarado — BL-436).


def _luminancia_relativa_srgb(fracao_do_canal):
    """Luminância relativa de UM canal sRGB (0.0–1.0) — fórmula da WCAG 2.x
    ("Relative Luminance"). Usada de DUAS formas neste módulo: (1) para um
    byte de CINZA (onde R=G=B, e a luminância do pixel inteiro é o
    resultado desta função aplicada uma vez, sem ponderação de canal —
    caminho legado, ver `_razao_de_contraste`); e (2) como a base de
    `_TABELA_LUMINANCIA_SRGB`/`_luminancia_relativa_rgb` (BL-429/DE-060),
    aplicada uma vez POR CANAL e depois ponderada (0,2126/0,7152/0,0722)
    — o caminho de PRODUÇÃO, que mede a tinta EM COR."""
    if fracao_do_canal <= 0.03928:
        return fracao_do_canal / 12.92
    return ((fracao_do_canal + 0.055) / 1.055) ** 2.4


def _razao_a_partir_de_luminancias(luminancia_a, luminancia_b):
    """Razão de contraste WCAG a partir de DUAS luminâncias relativas
    (0.0–1.0) JÁ CALCULADAS — a fórmula final (WCAG 2.x): `(clara+0,05) /
    (escura+0,05)`. Compartilhada entre o caminho CINZA (`_razao_de_
    contraste`, um canal — mantido como utilitário testado, não mais
    chamado pelo veredito de produção) e o caminho EM COR
    (`_razao_de_contraste_rgb`, três canais — BL-429/DE-060, o que decide
    o veredito hoje): a fórmula de RAZÃO é a MESMA nos dois; o que muda é
    só COMO cada luminância é calculada (um canal vs. três ponderados)."""
    mais_clara, mais_escura = max(luminancia_a, luminancia_b), min(luminancia_a, luminancia_b)
    return (mais_clara + 0.05) / (mais_escura + 0.05)


def _razao_de_contraste(nivel_de_cinza_a, nivel_de_cinza_b):
    """Razão de contraste WCAG entre dois níveis de cinza 0–255 — sempre
    >= 1.0 (dois pixels idênticos dão exatamente 1.0), simétrica (não
    importa qual argumento é o mais claro).

    BL-429/DE-060 (décima primeira auditoria): esta função mede a
    PROPRIEDADE só quando a tinta É cinza (R=G=B) — para tinta colorida,
    ela é um SUBSTITUTO que mede 2,1× mais contraste do que a razão real
    do WCAG mede (ver o comentário de `_rasterizar_pagina`). Por isso o
    CAMINHO DE PRODUÇÃO (`_localizar_linhas_do_timbre_no_documento`) não
    chama mais esta função — usa `_razao_de_contraste_rgb`, que aplica a
    ponderação de três canais que a etiqueta da mensagem ("WCAG 2.2,
    1.4.3") de fato promete. Esta função permanece como utilitário PURO
    testado (a fórmula de razão, isolada da ponderação de canal — ver
    `_razao_a_partir_de_luminancias`) e como base de comparação para o
    teste que mede a divergência entre as duas fórmulas."""
    luminancia_a = _luminancia_relativa_srgb(nivel_de_cinza_a / 255)
    luminancia_b = _luminancia_relativa_srgb(nivel_de_cinza_b / 255)
    return _razao_a_partir_de_luminancias(luminancia_a, luminancia_b)


_TABELA_LUMINANCIA_SRGB = tuple(_luminancia_relativa_srgb(byte / 255) for byte in range(256))
"""Tabela de 256 entradas, pré-computada UMA VEZ na importação do módulo:
`_TABELA_LUMINANCIA_SRGB[byte]` é a luminância relativa (0.0–1.0) daquele
BYTE de canal (0–255), pela MESMA fórmula de `_luminancia_relativa_srgb`.
Existe por CUSTO (critério 9 do plano — "tempo do passo de medição, real,
não estimado"): `_luminancia_relativa_rgb`, abaixo, roda para CADA pixel
de CADA faixa de linha medida (até 3 canais × milhares de pixels por
linha) — pré-computar os 256 valores possíveis por canal troca ``**2.4``
repetido por uma busca em tabela (O(1)), a MESMA técnica que `_niveis_de_
cinza_com_contraste_suficiente` já usa para o caminho cinza."""


def _luminancia_relativa_rgb(r, g, b):
    """Luminância relativa (WCAG 2.x) de um pixel RGB — três bytes de canal
    (0–255) —, com a ponderação que a fórmula do WCAG 2.2 exige
    (0,2126/0,7152/0,0722, vermelho/verde/azul). Esta é a PROPRIEDADE que
    a etiqueta "WCAG 2.2, 1.4.3" promete (BL-429/DE-060) — ao contrário de
    `_luminancia_relativa_srgb` aplicada a um nível de CINZA (que só
    coincide com esta fórmula quando R=G=B, isto é, quando a tinta já não
    tem cor nenhuma)."""
    return (
        0.2126 * _TABELA_LUMINANCIA_SRGB[r]
        + 0.7152 * _TABELA_LUMINANCIA_SRGB[g]
        + 0.0722 * _TABELA_LUMINANCIA_SRGB[b]
    )


def _razao_de_contraste_rgb(pixel_a, pixel_b):
    """Razão de contraste WCAG entre DOIS PIXELS RGB (tuplas `(r, g, b)`,
    0–255 cada) — a fórmula que a etiqueta da mensagem ("WCAG 2.2, 1.4.3")
    de fato promete (BL-429/DE-060). Substitui `_razao_de_contraste`
    (cinza) NO CAMINHO DE PRODUÇÃO — ver o comentário daquela função e de
    `_rasterizar_pagina` sobre a divergência medida (tinta vermelha: 2,1×
    mais contraste relatado em cinza do que a razão RGB real)."""
    return _razao_a_partir_de_luminancias(
        _luminancia_relativa_rgb(*pixel_a), _luminancia_relativa_rgb(*pixel_b)
    )


def _luminancia_do_papel(dados_pgm):
    """Fundo do PAPEL nesta rasterização — a MODA (nível de cinza mais
    frequente) da folha INTEIRA, não um branco (255) presumido. C2 da
    DL-029: "o fundo da PRÓPRIA folha", medido, não hipotetizado. Uma
    folha A4 impressa é, de longe, majoritariamente papel em branco —
    MEDIDO: no Balancete da base de medição, 815099 dos 893580 pixels
    (91%) — então a moda encontra o papel mesmo numa página com tabela
    cheia de texto preto.

    BL-426 (achado da verificação independente) — PREMISSA que precisa
    ficar escrita, não só medida: **hoje esta função SEMPRE mede branco**
    (255), qualquer que seja o `background` declarado no CSS do produto.
    MEDIDO: com `body { background: #1a1a1a }` (e mesmo com
    `print-color-adjust: exact` no CSS), a moda continua 255 e o
    instrumento aprova — porque `pagina.pdf(...)`
    (`_SCRIPT_DO_SUBPROCESSO`) NUNCA recebe `print_background=True`, e o
    Playwright/Chromium OMITE toda cor de fundo do PDF exportado por
    padrão (`print_background` vale `False`), INDEPENDENTE da propriedade
    CSS — que só importa quando o fundo É impresso. Confirmado o inverso,
    só para esta medição (patch temporário, revertido, não parte desta
    entrega): com `print_background=True` E `print-color-adjust: exact`
    no CSS, o MESMO fundo `#1a1a1a` faz a moda cair para ~26, e o timbre
    (tinta preta contra fundo quase preto) reprova por contraste, ~1,2:1.

    **Não é defeito, e é o comportamento CORRETO para o critério**: o
    navegador não imprime fundo de página por padrão (a mesma economia de
    tinta que qualquer impressora real aplicaria), e o PDF exportado por
    este instrumento é fiel a isso — "o fundo da própria folha" mede,
    hoje, exatamente o que uma impressora real produziria com a
    configuração padrão do produto. **A premissa que precisa ficar
    explícita para quem ler "contraste contra o fundo da própria folha"**:
    isso pressupõe fundo IMPRESSO — um `background` no CSS que dependa de
    `print-color-adjust: exact` (ou de `print_background=True` neste
    instrumento) para chegar ao papel NÃO é medido por este oráculo hoje.
    Se o produto um dia imprimir fundo de verdade, este comentário e a
    função continuam corretos (a moda mediria o fundo real); só a
    afirmação "a folha é sempre branca hoje" deixaria de valer — LIMITE
    DECLARADO, não fechado, porque o produto não usa fundo impresso
    hoje.

    BL-429/DE-060: esta função mede o fundo em TONS DE CINZA e não é mais
    chamada pelo CAMINHO DE PRODUÇÃO (`_localizar_linhas_do_timbre_no_
    documento` usa `_cor_do_papel`, abaixo, que mede o fundo EM COR — a
    mesma razão da troca de `_razao_de_contraste` por `_razao_de_
    contraste_rgb`). Mantida como utilitário puro testado; a premissa "a
    folha é sempre branca hoje" (acima) vale igualmente para o fundo em
    cor: branco é branco nos dois espaços."""
    _, _, corpo = _pgm_para_matriz(dados_pgm)
    return _moda_do_canal(corpo)


def _cor_do_papel(dados_ppm):
    """Fundo do PAPEL, EM COR — a moda `(r, g, b)` da folha inteira,
    calculada POR CANAL (MESMA técnica de `_luminancia_do_papel`, three
    vezes: uma para cada canal, via fatiamento `corpo[0::3]`/`[1::3]`/
    `[2::3]`) em vez de um histograma único de tuplas RGB — um histograma
    de tuplas sobre ~900 mil pixels precisaria de dicionário/`Counter`
    hasheando uma tupla por pixel, MEDIDO como sensivelmente mais lento em
    Python puro do que três histogramas de 256 posições (a MESMA
    otimização, aplicada three vezes). Para uma folha de fundo SÓLIDO
    (o caso do produto hoje — ver `_luminancia_do_papel`), a moda de cada
    canal isoladamente RECOMPÕE a cor do fundo corretamente: o fundo é o
    MESMO valor `(r, g, b)` repetido na maioria absoluta dos pixels, então
    cada canal, isoladamente, também tem esse valor como o mais frequente.
    BL-429/DE-060: substitui `_luminancia_do_papel` no CAMINHO DE
    PRODUÇÃO — mede a PROPRIEDADE (a cor real do fundo), não uma
    aproximação em cinza."""
    largura, altura, corpo = _ppm_para_matriz(dados_ppm)
    return (
        _moda_do_canal(corpo[0::3]),
        _moda_do_canal(corpo[1::3]),
        _moda_do_canal(corpo[2::3]),
    )


def _moda_do_canal(bytes_do_canal):
    """Nível 0–255 mais frequente numa sequência de bytes de UM canal —
    função PURA, extraída de `_luminancia_do_papel`/`_cor_do_papel` para
    as duas reaproveitarem o MESMO histograma de 256 posições."""
    histograma = [0] * 256
    for byte in bytes_do_canal:
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

    DE-060 (décima primeira auditoria): a quinta medição do instrumento —
    "cada linha está no SEU PRÓPRIO lugar" (C4). Esta função mede a
    PROPRIEDADE diretamente: o `(xmin, ymin, xmax, ymax)` devolvido é a
    posição REAL do bloco de texto no PDF exportado (via `pdftotext
    -bbox`, ver `_palavras_da_pagina`), não uma aproximação — não há
    substituto aqui para declarar, ao contrário das outras quatro
    medições (BL-427/428/429/430).

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
    """Rasteriza UMA página do PDF (padrão: a primeira) EM COR (PPM binário
    `P6`) via `pdftoppm` SEM `-gray` — a MESMA dependência de sistema
    (poppler-utils) que `_texto_do_pdf`/`_palavras_da_pagina` já exigem;
    NENHUMA biblioteca de imagem nova em `requirements/` (mesma decisão
    registrada na docstring de `scripts/medir_impressao.py` para não
    acrescentar lib de PDF — `-png`/PPM são as DUAS opções do MESMO binário
    já usado, nenhum pacote novo). `-singlefile` evita o poppler acrescentar
    sufixo numérico ao nome de saída, já que só pedimos uma página.

    BL-429 (L3, décima primeira auditoria,
    docs/auditorias/2026-09-20-dl-029-rodada-11.md) — DE-060: até esta
    correção, esta função rasterizava em TONS DE CINZA (`-gray`, PGM `P5`),
    e essa era a fonte da divergência: "cinza" é um SUBSTITUTO da
    propriedade que a etiqueta da mensagem promete (a razão de contraste do
    WCAG 2.2, que é definida sobre TRÊS canais RGB ponderados —
    0,2126/0,7152/0,0722 —, não sobre um nível de cinza). `pdftoppm -gray`
    CONVERTE qualquer tinta colorida para cinza ANTES deste oráculo
    enxergar qualquer coisa — a ponderação de canal é feita pelo poppler,
    em espaço gama, não pela fórmula do WCAG. MEDIDO: `color: #FF0000` no
    timbre relatava 8,45:1 de contraste (aprovando, `exit 0`) quando a
    razão WCAG REAL de `#FF0000` sobre `#FFFFFF` é 4,00:1 — REPROVA. O
    instrumento media 2,1× MAIS contraste do que existe.

    **Decisão (DE-060, plano da rodada 2, seção "A decisão que o BL-429
    exige"): medir SEMPRE em COR**, nunca declarar a premissa
    monocromática como alternativa — a medida em cor é a MAIS ESTRITA das
    duas (cobre o PDF na tela do cliente, onde a cor existe, E a
    impressora monocromática, onde a tinta vira cinza e o critério só fica
    MAIS folgado; medir em cinza aprovaria folha que o próprio piso
    adotado, em cor, reprova). Ver `_cor_do_papel`/`_luminancia_relativa_
    rgb`/`_razao_de_contraste_rgb`, abaixo, que substituem `_luminancia_do_
    papel`/`_razao_de_contraste` NO CAMINHO DE PRODUÇÃO — as duas funções
    em CINZA continuam presentes e testadas (utilitário genérico,
    reaproveitado pela fórmula em COR via `_razao_a_partir_de_luminancias`
    — ver o comentário de `_razao_de_contraste`), mas o VEREDITO do
    instrumento não depende mais delas.

    C1 da DL-029 (K7, décima auditoria): antes daquela correção, esta
    função só rasterizava a PRIMEIRA página, por premissa não declarada —
    uma linha empurrada para a página 2 (por paginação comum: margem,
    cabeçalho mais alto) media "0 pixels escuros" na folha 1, a MESMA
    mensagem de tinta realmente ausente. O parâmetro `pagina` (usado por
    `main`, abaixo, para procurar nas páginas seguintes antes de reportar
    ausência de tinta) fecha essa lacuna — e continua valendo aqui.

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
                "-singlefile",
                str(caminho_pdf),
                str(prefixo),
            ],
            capture_output=True,
        )
        if resultado.returncode != 0:
            _recusar(
                f"'pdftoppm' (rasterização em cor) falhou (código {resultado.returncode}) ao "
                f"rasterizar a página {pagina} de {caminho_pdf} — falha de infraestrutura.\n"
                f"erro: {resultado.stderr.decode(errors='replace')}"
            )
        return (prefixo.with_suffix(".ppm")).read_bytes()


def _cabecalho_e_corpo_netpbm(dados, assinatura, bytes_por_pixel):
    """Parser COMPARTILHADO do cabeçalho binário Netpbm (P5 = PGM/cinza, 1
    byte por pixel; P6 = PPM/cor, 3 bytes por pixel — MESMO formato de
    cabeçalho nos dois: assinatura, três inteiros [largura, altura,
    maxval] separados por espaço em branco, um único espaço, depois os
    bytes de pixel). Extraído para `_pgm_para_matriz` (P5) e `_ppm_para_
    matriz` (P6, BL-429) compartilharem o MESMO parser em vez de duas
    cópias que divergem assim que uma for corrigida sem a outra
    (AGENTS.md §8). Devolve `(largura, altura, corpo_de_bytes)`."""
    if not dados.startswith(assinatura):
        raise ValueError(f"dados não começam com a assinatura Netpbm binária {assinatura!r}")
    pos = len(assinatura)
    campos = []
    # Cabeçalho: três inteiros (largura, altura, maxval) separados por
    # espaço em branco — comentários `#...\n` são permitidos pelo formato
    # entre tokens; ignorados aqui se aparecerem (poppler não os emite,
    # mas o formato PERMITE, e um parser que quebra num comentário válido
    # é um parser errado, não um limite documentado).
    while len(campos) < 3:
        while dados[pos : pos + 1].isspace():
            pos += 1
        if dados[pos : pos + 1] == b"#":
            pos = dados.index(b"\n", pos) + 1
            continue
        inicio = pos
        while not dados[pos : pos + 1].isspace():
            pos += 1
        campos.append(int(dados[inicio:pos]))
    largura, altura, maxval = campos
    if maxval >= 256:
        raise ValueError(f"Netpbm com maxval {maxval} >= 256 (16 bits) não é suportado")
    pos += 1  # o único espaço em branco exigido pelo formato após o maxval
    tamanho_esperado = largura * altura * bytes_por_pixel
    corpo = dados[pos : pos + tamanho_esperado]
    if len(corpo) < tamanho_esperado:
        raise ValueError(
            f"Netpbm truncado: esperava {tamanho_esperado} bytes de pixel, achei {len(corpo)}"
        )
    return largura, altura, corpo


def _pgm_para_matriz(dados_pgm):
    """Parseia um PGM BINÁRIO (`P5`) sem depender de Pillow nem de
    nenhuma lib de imagem — é exatamente o formato que `pdftoppm -gray`
    produz nativamente (8 bits: `maxval < 256`, sempre o caso aqui), 1
    byte por pixel, 0 = preto, 255 = branco. Devolve `(largura, altura,
    corpo_de_bytes)`. Função PURA — testada em
    `scripts/test_medir_identificacao_do_emitente.py` com bytes
    sintéticos, sem chamar `pdftoppm` de verdade."""
    return _cabecalho_e_corpo_netpbm(dados_pgm, b"P5", bytes_por_pixel=1)


def _ppm_para_matriz(dados_ppm):
    """Parseia um PPM BINÁRIO (`P6`) sem depender de Pillow nem de nenhuma
    lib de imagem — é exatamente o formato que `pdftoppm` produz
    nativamente SEM `-gray`/`-mono`/`-png` (8 bits por canal, 3 bytes por
    pixel, R-G-B intercalados). Devolve `(largura, altura, corpo_de_
    bytes)`, com `corpo` de comprimento `largura*altura*3` — o pixel `(x,
    y)` começa no offset `(y*largura + x) * 3`. BL-429/DE-060: a
    rasterização EM COR que substitui `-gray` no caminho de produção (ver
    `_rasterizar_pagina`). Função PURA — testada com bytes sintéticos, sem
    chamar `pdftoppm` de verdade."""
    return _cabecalho_e_corpo_netpbm(dados_ppm, b"P6", bytes_por_pixel=3)


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
    alteração por esta correção, que só troca o CRITÉRIO por pixel.

    BL-429/DE-060: esta função mede em TONS DE CINZA — só a PROPRIEDADE
    quando a tinta é cinza (ver o comentário de `_razao_de_contraste`).
    Não é mais chamada pelo CAMINHO DE PRODUÇÃO
    (`_localizar_linhas_do_timbre_no_documento` usa `_diagnostico_de_
    contraste_na_faixa_cor`, abaixo). Mantida como utilitário puro
    testado — a técnica de pré-computar os níveis suficientes
    (`_niveis_de_cinza_com_contraste_suficiente`) só funciona em cinza
    (256 níveis possíveis); em COR o espaço é grande demais (16 milhões
    de combinações) para pré-computar um conjunto, então a versão em cor
    calcula a razão PIXEL A PIXEL — ver o comentário da função abaixo
    sobre o custo disso."""
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


def _diagnostico_de_contraste_na_faixa_cor(
    dados_ppm,
    retangulo_pt,
    cor_do_papel,
    razao_minima,
    dpi=DPI_ORACULO_DO_PAPEL,
    margem_px=2,
):
    """C2 da DL-029, EM COR (BL-429/DE-060) — a mesma pergunta de
    `_diagnostico_de_contraste_na_faixa` (quantos pixels da faixa atingem
    `razao_minima` contra o fundo, e qual é o CONTRASTE MÁXIMO
    encontrado), mas com a luminância de CADA pixel e do papel calculada
    pelos TRÊS canais RGB ponderados (`_luminancia_relativa_rgb`) — a
    fórmula que a etiqueta "WCAG 2.2, 1.4.3" de fato promete, em vez da
    aproximação em cinza que `pdftoppm -gray` produzia (ver o comentário
    de `_rasterizar_pagina`).

    **Por que não pré-computar um conjunto de "níveis suficientes"
    (a técnica de `_niveis_de_cinza_com_contraste_suficiente`)**: em
    cinza há 256 combinações possíveis: cabe pré-computar uma vez por
    linha. Em COR há até 256³ (~16,7 milhões) combinações de pixel — pré-
    computar um `frozenset` desse tamanho custaria mais do que calcular a
    razão pixel a pixel para as poucas MILHARES de posições que uma faixa
    de linha ocupa. Por isso esta função calcula `_razao_de_contraste_rgb`
    diretamente, pixel a pixel, usando `_TABELA_LUMINANCIA_SRGB` (256
    entradas, uma busca O(1) por canal) para manter o CUSTO POR PIXEL
    baixo — ver a medição de custo no relatório desta etapa (critério 9
    do plano).

    Devolve `(pixels_com_contraste_suficiente, contraste_maximo_medido)`
    — MESMA assinatura de retorno da versão em cinza, para `main` não
    precisar distinguir qual foi chamada."""
    largura_pagina, altura_pagina, corpo = _ppm_para_matriz(dados_ppm)
    fator = dpi / PONTOS_POR_POLEGADA
    xmin, ymin, xmax, ymax = retangulo_pt
    x0 = max(0, int(xmin * fator) - margem_px)
    y0 = max(0, int(ymin * fator) - margem_px)
    x1 = min(largura_pagina, int(xmax * fator) + margem_px + 1)
    y1 = min(altura_pagina, int(ymax * fator) + margem_px + 1)
    luminancia_papel = _luminancia_relativa_rgb(*cor_do_papel)
    contagem = 0
    # `1.0`, não `1.0` de "sem contraste" — a razão mínima MATEMÁTICA
    # entre duas luminâncias é sempre >= 1.0 (dois pixels idênticos ao
    # papel), então este valor inicial nunca falsifica um contraste que
    # não foi medido, e é substituído assim que QUALQUER pixel da faixa
    # existir (a faixa sempre tem pelo menos um pixel, pelo `margem_px`).
    contraste_maximo = 1.0
    for y in range(y0, y1):
        inicio_da_linha = y * largura_pagina * 3
        for x in range(x0, x1):
            offset = inicio_da_linha + x * 3
            luminancia_pixel = _luminancia_relativa_rgb(
                corpo[offset], corpo[offset + 1], corpo[offset + 2]
            )
            razao = _razao_a_partir_de_luminancias(luminancia_papel, luminancia_pixel)
            if razao > contraste_maximo:
                contraste_maximo = razao
            if razao >= razao_minima:
                contagem += 1
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
            # BL-429/DE-060: rasterização EM COR (`_rasterizar_pagina`
            # já produz PPM desde essa correção — ver a docstring dela)
            # e fundo/contraste medidos pela fórmula RGB do WCAG, não
            # mais pela aproximação em cinza.
            dados_ppm = _rasterizar_pagina(caminho_pdf, pagina)
            cor_do_papel = _cor_do_papel(dados_ppm)
            cache_por_pagina[pagina] = (palavras, dados_ppm, cor_do_papel)
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
            _, dados_ppm, cor_do_papel = _dados_da_pagina(folha)
            pixels, contraste_maximo = _diagnostico_de_contraste_na_faixa_cor(
                dados_ppm, bbox, cor_do_papel, razoes_minimas[indice]
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

            # M2/BL-444 (décima segunda auditoria): TERCEIRO canal do C5 —
            # anotação de link (`/URI` dentro de `/Annot`). Controlada
            # INTEIRAMENTE pelo template (é o `<a href>` que o Django
            # escreve), então entra no critério corrigido (ver o
            # comentário no topo do módulo e o de
            # `_anotacoes_de_link_do_pdf`) mesmo sem ser tinta na folha
            # nem metadado clássico.
            anotacoes_de_link_pdf = (
                _anotacoes_de_link_do_pdf(caminho_pdf) if caminho_pdf.exists() else []
            )
            anotacao_com_marca = _anotacao_de_link_com_marca_do_fornecedor(
                anotacoes_de_link_pdf, marca_do_fornecedor_normalizada
            )
            entrada["anotacoes_de_link_pdf"] = anotacoes_de_link_pdf

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

            # BL-427/C3 (L1, décima primeira auditoria,
            # docs/auditorias/2026-09-20-dl-029-rodada-11.md) — DE-060:
            # este trecho fazia DUAS perguntas coladas, e a segunda
            # (infraestrutura) sempre vencia a primeira (conteúdo) antes
            # desta correção. `filhos` (acima, do seletor `.timbre-
            # impressao p` sondado por `sonda_visibilidade`) e `fonte_das_
            # linhas` (abaixo, MESMO seletor, MESMO DOM, MESMA página —
            # ver o comentário de `js_fonte_das_linhas` em
            # `_SCRIPT_DO_SUBPROCESSO`) vêm da MESMA fonte: por construção,
            # `len(filhos) != len(linhas_esperadas)` implica SEMPRE
            # `len(fonte_das_linhas) != len(linhas_esperadas)`. A versão
            # anterior deste código recusava (código 2, infraestrutura)
            # nesse caso — e `_recusar` ENCERRA o processo imediatamente —
            # antes de o `motivos.append` da divergência de contagem
            # (conteúdo, código 1) chegar à saída. MEDIDO: um timbre com
            # 2 das 3 linhas declaradas (a linha do registro profissional
            # some) saía como "FALHA DE INFRAESTRUTURA — não é um veredito
            # sobre o produto", mandando quem lê o job procurar o defeito
            # no navegador, quando o defeito estava no timbre. A frase do
            # C3 nunca era impressa, em NENHUM caminho de execução.
            #
            # A propriedade que C3 promete medir é "quantas linhas o
            # papel carrega" — e o substituto usado (contagem de `<p>` do
            # DOM) É a mesma consulta que decidia a recusa de
            # infraestrutura logo abaixo, o que fazia as duas perguntas
            # colidirem. Separadas agora em DUAS perguntas distintas, na
            # ORDEM que o auditor recomendou:
            #
            # 1. `fonte_das_linhas is None` — a sonda NÃO devolveu a
            #    medição nenhuma (subprocesso antigo, sem esse campo; ver
            #    `_SCRIPT_DO_SUBPROCESSO`) — infraestrutura DE VERDADE:
            #    sem ela não há como aplicar o piso de contraste do WCAG
            #    para NENHUMA linha, existente ou não. Continua `_recusar`
            #    (código 2) — preservar isto é o critério 12 da rodada 2.
            # 2. Contagem divergente (`filhos` != `linhas_esperadas`) — é
            #    CONTEÚDO: o documento saiu com o timbre incompleto (ou
            #    com linha extra), e é EXATAMENTE o caso que o C3 existe
            #    para nomear. Reprova (código 1, mais abaixo) com a frase
            #    de divergência — e o piso de contraste, logo depois,
            #    calcula a razão mínima só para as linhas que EXISTEM
            #    (`indice < len(fonte_das_linhas)`), sem tentar adivinhar
            #    tamanho/peso de uma linha que não está lá.
            fonte_das_linhas = medida.get("fonte_das_linhas")
            if fonte_das_linhas is None:
                _recusar(
                    f"{nome}: a medição de tamanho/peso de fonte por linha "
                    "('fonte_das_linhas') veio ausente — sonda desatualizada ou "
                    "subprocesso sem esse campo; não é possível aplicar o piso de "
                    "contraste do WCAG 2.2 para NENHUMA linha desta tela."
                )

            if len(filhos) != len(linhas_esperadas):
                # C3 ("comparação de CONJUNTOS: faltar OU sobrar linha
                # reprova"): o número de `<p>` que o navegador viu dentro
                # do timbre diverge do número de linhas que o servidor
                # declarou (`Escritorio.linhas_do_timbre`) — um `<p>` a
                # mais ou a menos no template/CSS, sem precisar adivinhar
                # QUAL. Esta é a frase que o L1 mediu como código
                # INALCANÇÁVEL — agora chega à saída em TODOS os casos,
                # porque não depende mais de `fonte_das_linhas` bater a
                # mesma contagem.
                motivos.append(
                    f"número de linhas do timbre no papel ({len(filhos)}) diverge do "
                    f"número declarado pelo servidor ({len(linhas_esperadas)})"
                )

            # C2 da DL-029: o piso de contraste é POR LINHA, do tamanho e
            # peso REALMENTE renderizados (`medida["fonte_das_linhas"]`,
            # perguntado ao navegador em `_SCRIPT_DO_SUBPROCESSO` — nunca
            # deduzido de token CSS). BL-436: o TAMANHO usado para
            # classificar "texto grande" é o EFETIVO
            # (`tamanho_efetivo_px`, já com `escala_acumulada` aplicada),
            # não o declarado — ver o comentário de `_razao_minima_wcag_
            # para_linha`. Só as linhas que EXISTEM no DOM (`indice <
            # len(fonte_das_linhas)`) têm essa medição — uma linha
            # AUSENTE (BL-427) não tem tamanho/peso renderizado nenhum
            # para medir, então recebe o piso mais ESTRITO (texto normal,
            # 4,5:1) por padrão; isso é inofensivo, porque uma linha
            # ausente não tem bbox no papel
            # (`_localizar_linhas_do_timbre_no_documento` devolve
            # `pixels_com_contraste=0` para `bbox=None`) — o piso usado
            # aqui nunca decide o veredito de uma linha que já reprova por
            # estar ausente (ver `presente_no_pdf`, abaixo).
            razoes_minimas = [
                _razao_minima_wcag_para_linha(
                    fonte_das_linhas[indice]["tamanho_efetivo_px"],
                    fonte_das_linhas[indice]["peso"],
                )
                if indice < len(fonte_das_linhas)
                else RAZAO_MINIMA_WCAG_TEXTO_NORMAL
                for indice in range(len(linhas_esperadas))
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

                localizacao = localizacoes_no_pdf[indice]
                folha_da_linha = localizacao["folha"]
                # BL-430/C1-C3 (L4, décima primeira auditoria) — DE-060:
                # "a linha está no papel" tinha como substituto uma
                # SUBSTRING do texto de `pdftotext -layout`
                # (`linha in texto_pdf`) — mais barato de obter que a
                # propriedade, e diverge exatamente quando o CSS de
                # impressão usa `letter-spacing` (ou qualquer construção
                # que mude o espaçamento visual entre glifos): a
                # heurística de RECONSTRUÇÃO DE COLUNA do `-layout`
                # insere espaços ESPÚRIOS dentro da palavra, e a
                # substring exata deixa de casar. MEDIDO: `letter-spacing:
                # 0.2em` no tamanho REAL do produto (14px — não só em
                # "fontes extremas", a afirmação que o BL-425 fazia e que
                # a mesma auditoria mediu como falsa: DE-058, escopo de
                # medição também é afirmação) produzia "AUSENTE do texto
                # do PDF" sobre uma linha com 306 pixels de tinta medidos
                # NA MESMA execução — a saída se contradizia.
                #
                # A propriedade que C1/C3 promete medir é "esta linha
                # está no papel" — e a resposta correta já existe no
                # próprio `localizacao`, calculada por
                # `_localizar_linhas_do_timbre_no_documento` via
                # `pdftotext -bbox` (`_bbox_da_linha`/`_localizar_bloco_
                # do_timbre`): esse mecanismo concatena as palavras SEM
                # espaço dos dois lados antes de comparar, então não
                # sofre a mesma heurística de reconstrução de coluna do
                # `-layout` — é a medida que este instrumento JÁ
                # CALCULAVA (para achar a faixa de contraste) e
                # DESCARTAVA para a pergunta de presença. Usá-la aqui
                # fecha `letter-spacing` sem lista nenhuma, e sem
                # depender de tamanho de fonte algum.
                #
                # `_texto_do_pdf`/`-layout` CONTINUA sendo usado — só
                # para o C5 (ausência do identificador do FORNECEDOR),
                # onde a normalização (`_normalizar_para_busca_do_
                # fornecedor`) já descarta espaço espúrio antes de
                # comparar, então a divergência medida aqui não o alcança.
                presente_no_pdf = localizacao["bbox"] is not None
                pixels_com_contraste = localizacao["pixels_com_contraste"]
                contraste_maximo_medido = localizacao["contraste_maximo_medido"]
                razao_minima_exigida = razoes_minimas[indice]

                # BL-428 (L2, décima primeira auditoria) — DE-060: o
                # "tamanho renderizado" era a fonte DECLARADA
                # (`getComputedStyle().fontSize`), mais barata de obter
                # que a propriedade ("que tamanho a linha TEM NO
                # PAPEL"), e divergia com `transform`/`zoom`.
                #
                # BL-437 (verificação independente, rodada 3): a
                # correção da rodada 2 (dividir a altura do bbox do
                # papel por uma razão MEDIDA numa família tipográfica
                # só) não generalizava entre famílias — REMOVIDA, ver o
                # comentário de `TAMANHO_MINIMO_RENDERIZADO_PX`.
                #
                # CORREÇÃO ATUAL: `tamanho_efetivo_px`, calculado no
                # NAVEGADOR (`escala_acumulada = getBoundingClientRect().
                # height / offsetHeight`, ver `js_fonte_das_linhas` em
                # `_SCRIPT_DO_SUBPROCESSO`) — geometria de LAYOUT, não
                # métrica de fonte, então correta para QUALQUER família
                # tipográfica, sem constante nenhuma para medir de novo
                # se a família mudar. MEDIDO que captura corretamente
                # `transform` próprio, `zoom` próprio, transform de
                # ANCESTRAL, e a combinação dos dois (5 cenários,
                # inclusive controle) antes de adotar.
                #
                # Só linhas que EXISTEM no DOM (`indice <
                # len(fonte_das_linhas)`) têm essa medição — uma linha
                # ausente do DOM não tem `tamanho_efetivo_px` nenhum;
                # isso raramente alcança a mensagem de tamanho, porque
                # `presente_no_pdf` (checado ANTES, no `if/elif` abaixo)
                # já reprova a esmagadora maioria desses casos primeiro.
                tamanho_renderizado_px = (
                    fonte_das_linhas[indice]["tamanho_efetivo_px"]
                    if indice < len(fonte_das_linhas)
                    else None
                )
                # Mantido só como DIAGNÓSTICO (nunca decide veredito) — o
                # valor que `getComputedStyle` relatou (sem a escala
                # acumulada), para quem for investigar uma divergência
                # grande entre os dois.
                tamanho_declarado_px = (
                    fonte_das_linhas[indice]["tamanho_px"]
                    if indice < len(fonte_das_linhas)
                    else None
                )
                # BL-424: TAMANHO é a TERCEIRA causa distinguível de
                # reprovação, ao lado de contraste e contagem — ver o
                # comentário completo de TAMANHO_MINIMO_RENDERIZADO_PX
                # sobre por que a contagem sozinha não bastava mais
                # (font-size: 8px passava com contraste altíssimo e
                # contagem acima do piso).
                # `tamanho_renderizado_px` só é `None` quando a linha não
                # existe no DOM (`indice >= len(fonte_das_linhas)`) — e
                # esse caso quase sempre já reprova por `presente_no_pdf`
                # antes de chegar aqui (ver o `if/elif` abaixo). O `is
                # not None` é defensivo: evita `TypeError` no raro caso
                # em que a linha some do DOM mas um decoy no PDF faz
                # `presente_no_pdf` sair `True` mesmo assim (limite
                # declarado de `_localizar_linhas_do_timbre_no_
                # documento`, camada 2 — ver a docstring dela).
                tamanho_insuficiente = (
                    tamanho_renderizado_px is not None
                    and tamanho_renderizado_px < TAMANHO_MINIMO_RENDERIZADO_PX
                )
                # C2, regra TRIPLA e DISTINGUÍVEL (exigência do
                # arquiteto-senior): três causas de reprovação diferentes,
                # nunca a mesma mensagem para duas delas.
                # - TAMANHO insuficiente: o texto foi renderizado menor
                #   que o piso declarado — nem contraste nem contagem
                #   decidem isso (ver TAMANHO_MINIMO_RENDERIZADO_PX).
                # - CONTRASTE insuficiente: o pixel mais escuro da faixa já
                #   fica abaixo do piso WCAG desta linha — nenhuma
                #   quantidade de pixels ajudaria (a tinta é CLARA demais).
                # - CONTAGEM insuficiente: sanidade residual — contraste E
                #   tamanho passam, mas poucos pixels alcançam esse nível
                #   mesmo assim (ex.: um glifo com buracos, letras muito
                #   finas). NÃO é mais a guarda do tamanho — essa função
                #   passou para a checagem acima.
                contraste_insuficiente = contraste_maximo_medido < razao_minima_exigida
                tinta_visivel_no_papel = (
                    not tamanho_insuficiente
                    and not contraste_insuficiente
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
                        "tamanho_renderizado_px": tamanho_renderizado_px,
                        "tamanho_declarado_px": tamanho_declarado_px,
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
                    # BL-430: a mensagem nomeia "no papel" (bbox não
                    # localizado via `pdftotext -bbox`), não mais "no
                    # texto do PDF" (`-layout`) — ver o comentário de
                    # `presente_no_pdf`, acima, sobre a troca de mecanismo.
                    motivos.append(f"linha do timbre AUSENTE do papel (PDF exportado): {linha!r}")
                elif folha_da_linha is not None and folha_da_linha != 1:
                    # C1/K7 (BL-410): a linha ESTÁ no papel, só que NÃO na
                    # primeira folha — nomeia PAGINAÇÃO, nunca "0 pixels
                    # escuros" (a mensagem que a rodada 10 flagrou como
                    # culpando a tinta por um problema de layout).
                    motivos.append(
                        f"linha do timbre está na folha {folha_da_linha}, não na folha 1: {linha!r}"
                    )
                elif tamanho_insuficiente:
                    # BL-424: TAMANHO, não contraste nem contagem — o
                    # texto foi renderizado menor que o piso declarado
                    # (TAMANHO_MINIMO_RENDERIZADO_PX — escolha do
                    # projeto, não do WCAG; ver o comentário completo).
                    motivos.append(
                        f"linha do timbre renderizada a {tamanho_renderizado_px:g}px, "
                        f"abaixo do mínimo de {TAMANHO_MINIMO_RENDERIZADO_PX}px: {linha!r}"
                    )
                elif contraste_insuficiente:
                    # C2: CONTRASTE, não tamanho nem contagem — a tinta é
                    # clara demais para o tamanho/peso REAL desta linha,
                    # medido contra o piso do WCAG 2.2 (empréstimo
                    # declarado — ver o comentário de
                    # RAZAO_MINIMA_WCAG_TEXTO_NORMAL).
                    motivos.append(
                        f"linha do timbre com CONTRASTE insuficiente contra o papel: {linha!r} — "
                        f"{contraste_maximo_medido:.2f}:1 medido, mínimo exigido "
                        f"{razao_minima_exigida:.1f}:1 (WCAG 2.2, 1.4.3)"
                    )
                elif not tinta_visivel_no_papel:
                    # C2/BL-424: CONTAGEM — sanidade residual. Tamanho E
                    # contraste passam, mas poucos pixels alcançam o
                    # contraste exigido mesmo assim (ex.: glifo com muitos
                    # "buracos" — não é mais a guarda de "ficou pequeno
                    # demais", ver o comentário de
                    # TAMANHO_MINIMO_RENDERIZADO_PX).
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
            if anotacao_com_marca is not None:
                # M2/BL-444: nomeia "anotação de link" explicitamente — é o
                # texto que a verificação da correção (M2, "Como verificar")
                # exige aparecer na mensagem, para quem lê o job distinguir
                # este canal dos outros dois (tinta/metadado).
                motivos.append(
                    f"identificador do fornecedor ({marca_do_fornecedor!r}) presente em "
                    f"anotação de link do PDF (alvo: {anotacao_com_marca!r}) — não é tinta na "
                    "folha nem metadado clássico, mas é identificação de quem vende o software "
                    "no ARQUIVO que o escritório entrega ao cliente, clicável"
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

        total_telas_consideradas_timbre = len(nomes_para_medir) + len(telas_do_piso_ausentes)

    # ------------------------------------------------------------------
    # BL-501 (achado A3): o bloco do item 51 (`.identificacao-do-
    # documento`), por PÁGINA, nas telas de CLASSE 2 — ver o comentário
    # completo no topo da seção de derivação, acima de
    # `_descobrir_telas_com_identificacao_do_documento`. Bloco SEPARADO,
    # DEPOIS do `with` do timbre (não dentro): o achado que motivou esta
    # extensão é justamente que os dois critérios (RC-97 do escritório,
    # RC-95 da entidade) são INDEPENDENTES — a reprovação de um nunca deve
    # impedir a MEDIÇÃO do outro nem esconder o relatório dele.
    reprovacoes_documento = []
    relatorio_documento = {}
    # Empresa PRÓPRIA (não a `empresa` da base padrão) — ver a docstring
    # de `_preparar_empresa_classe_2` sobre por quê: a base padrão nunca
    # classifica conta nenhuma em circulante/não circulante, então o
    # Balanço dela nunca sai do estado de pendência.
    empresa_classe_2, conta_classe_2 = _preparar_empresa_classe_2(escritorio)
    telas_documento = _descobrir_telas_com_identificacao_do_documento(
        cliente, empresa_classe_2, conta_classe_2
    )
    telas_documento_do_piso_ausentes = sorted(
        TELAS_MINIMAS_COM_IDENTIFICACAO_DO_DOCUMENTO_ESPERADAS - telas_documento.keys()
    )
    for nome in telas_documento_do_piso_ausentes:
        reprovacoes_documento.append(
            f"{nome}: tela de CLASSE 2 do piso mínimo (BL-501) NÃO encontrada pela "
            "varredura — o bloco do item 51 pode ter sido removido inteiro do template, "
            "não só escondido por CSS"
        )
        relatorio_documento[nome] = {
            "url": None,
            "veredito": "AUSENTE (piso mínimo)",
            "motivos": ["tela do piso mínimo (BL-501) não encontrada pela varredura"],
        }

    if telas_documento:
        print(
            "telas derivadas com identificação do documento (classe 2, "
            f"{len(telas_documento)}): {', '.join(sorted(telas_documento))}",
            file=sys.stderr,
        )
        with tempfile.TemporaryDirectory(prefix="dl-medir-documento-") as pasta_temp_doc:
            pasta_html_doc = Path(pasta_temp_doc) / "html"
            pasta_html_doc.mkdir()
            nomes_documento = sorted(telas_documento)
            for nome in nomes_documento:
                (pasta_html_doc / f"{nome.replace(':', '_')}.html").write_text(
                    telas_documento[nome]["html"], encoding="utf-8"
                )

            pasta_saida_doc = (
                (pasta_informada / "identificacao-do-documento")
                if pasta_informada
                else (Path(pasta_temp_doc) / "pdfs")
            )
            pasta_saida_doc.mkdir(parents=True, exist_ok=True)

            resultados_navegador_doc = _medir_no_navegador(
                pasta_html_doc,
                pasta_saida_doc,
                nomes_documento,
                seletor_container=SELETOR_IDENTIFICACAO_DO_DOCUMENTO,
                seletor_filhos=SELETOR_IDENTIFICACAO_DO_DOCUMENTO_FILHOS,
            )

            for nome in nomes_documento:
                medida = resultados_navegador_doc.get(nome, {})
                entrada = {"url": telas_documento[nome]["url"], "medicao_navegador": medida}
                relatorio_documento[nome] = entrada

                if "erro" in medida:
                    # BL-378 (mesmo raciocínio do bloco do timbre, acima):
                    # falha de NAVEGAÇÃO/MEDIÇÃO é infraestrutura, nunca
                    # veredito sobre o produto.
                    _recusar(f"{nome}: erro de navegação/medição — {medida['erro']}")

                motivos = []
                if not medida.get("encontrado"):
                    motivos.append(
                        "container '.identificacao-do-documento' não encontrado no HTML "
                        "(folha 1 — antes mesmo de checar as demais páginas)"
                    )
                elif not medida.get("visivel"):
                    motivos.append(
                        "container '.identificacao-do-documento' NÃO visível sob impressão "
                        "(folha 1)"
                    )

                caminho_pdf = pasta_saida_doc / f"{nome.replace(':', '_')}.pdf"
                entrada["pdf"] = str(caminho_pdf)

                if not motivos and caminho_pdf.exists():
                    # O TEXTO esperado em CADA página vem do que o
                    # PRÓPRIO SERVIDOR escreveu para esta tela (nunca um
                    # literal da norma reescrito aqui — ver a docstring
                    # de `_derivar_texto_da_identificacao_do_documento`).
                    texto_esperado = _derivar_texto_da_identificacao_do_documento(
                        telas_documento[nome]["html"]
                    )
                    if not texto_esperado:
                        # O marcador de DESCOBERTA (regex de classe, em
                        # `_descobrir_telas_com_identificacao_do_
                        # documento`) e o marcador de EXTRAÇÃO (o `<div
                        # class="identificacao-do-documento">...</div>`
                        # inteiro, aqui) são DOIS padrões — MEDIDAMENTE
                        # diferentes (BL-425/C1: dois mecanismos podem
                        # divergir). Se o primeiro achou a tela mas o
                        # segundo não extraiu texto nenhum, o template
                        # mudou de forma que este instrumento não
                        # reconhece mais — infraestrutura do PRÓPRIO
                        # instrumento, não veredito sobre o produto (ele
                        # pode estar certo ou errado; este script não
                        # sabe dizer).
                        _recusar(
                            f"{nome}: '.identificacao-do-documento' foi ENCONTRADO pela "
                            "varredura (marcador de classe), mas este instrumento não "
                            "conseguiu extrair o TEXTO de dentro do bloco (padrão de "
                            "_derivar_texto_da_identificacao_do_documento desatualizado "
                            "em relação ao template) — atualize o padrão junto com o "
                            "template, nunca volte a um literal fixo aqui."
                        )

                    # ⚠️ LIMITE DECLARADO (não fechado por esta correção,
                    # mesmo padrão de honestidade que `sonda_
                    # visibilidade.py` já assume para `.timbre-impressao`):
                    # esta checagem confirma que o TEXTO do bloco existe
                    # como objeto de texto em cada página — `pdftotext`
                    # extrai o CONTEÚDO do fluxo, não o pixel pintado, então
                    # `color: transparent` (tinta da MESMA cor do papel)
                    # continuaria sendo extraída aqui como "presente", sem
                    # ficar LEGÍVEL. O bloco do timbre fecha esse caso com
                    # `_localizar_linhas_do_timbre_no_documento` (bbox +
                    # contraste, por LINHA); estender a MESMA análise de
                    # contraste ao bloco do item 51 por página é escopo
                    # maior do que esta correção comprou — fica registrado,
                    # não escondido. A verificação de VISIBILIDADE no
                    # navegador (`medida.get("visivel")`, acima, via
                    # `checkVisibility({checkOpacity: true, ...})`) já
                    # cobre `opacity: 0`/`display: none`/`visibility:
                    # hidden`, que é a classe de sabotagem que o critério de
                    # aceite 1 desta correção exige reprovar — só
                    # `color: transparent` fica fora, hoje.
                    total_paginas = _total_de_paginas(caminho_pdf)
                    folhas_sem_bloco = [
                        pagina
                        for pagina in range(1, total_paginas + 1)
                        if texto_esperado not in _texto_da_pagina_sem_espaco(caminho_pdf, pagina)
                    ]
                    entrada["total_paginas"] = total_paginas
                    entrada["folhas_sem_bloco_do_item_51"] = folhas_sem_bloco
                    if folhas_sem_bloco:
                        # BL-501/A3 — a REPROVAÇÃO que a sabotagem do
                        # auditor (o `@media print { display: none }` no
                        # critério de aceite 1) tem que produzir: o bloco
                        # do item 51 (RC-95) sumiu de pelo menos uma
                        # página do documento exportado.
                        motivos.append(
                            f"bloco do item 51 (RC-95) AUSENTE em {len(folhas_sem_bloco)} de "
                            f"{total_paginas} página(s): folha(s) {folhas_sem_bloco} — "
                            "medido no TEXTO do PDF exportado, não só no HTML servido"
                        )

                entrada["veredito"] = "PASSOU" if not motivos else "REPROVADO"
                entrada["motivos"] = motivos
                if motivos:
                    reprovacoes_documento.append(f"{nome}: {'; '.join(motivos)}")
    else:
        print(
            "AVISO: nenhuma tela de classe 2 (identificação do documento, BL-501) "
            "encontrada pela varredura — ver os nomes do piso mínimo abaixo, se algum "
            "estiver ausente.",
            file=sys.stderr,
        )

    print(json.dumps(relatorio_documento, ensure_ascii=False, indent=2))
    for nome, entrada in relatorio_documento.items():
        print(f"{nome}: {entrada['veredito']} — {entrada.get('url')}")

    # ------------------------------------------------------------------
    # Veredito ÚNICO, combinando os DOIS critérios independentes (timbre
    # do escritório, RC-97; identificação do documento, RC-95/BL-501) — a
    # reprovação de qualquer um dos dois reprova o job inteiro, mas as
    # DUAS medições sempre rodam e sempre aparecem no relatório, mesmo
    # quando uma delas já teria motivo de sobra para reprovar sozinha.
    reprovacoes_totais = reprovacoes + reprovacoes_documento
    if reprovacoes_totais:
        total_telas_consideradas = (
            total_telas_consideradas_timbre
            + len(telas_documento_do_piso_ausentes)
            + len(telas_documento)
        )
        detalhe = "\n".join(f"  - {linha}" for linha in reprovacoes_totais)
        _reprovar_por_conteudo(
            f"{len(reprovacoes_totais)} de {total_telas_consideradas} tela(s) sem "
            f"identificação completa (emitente e/ou documento) no papel:\n{detalhe}"
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
