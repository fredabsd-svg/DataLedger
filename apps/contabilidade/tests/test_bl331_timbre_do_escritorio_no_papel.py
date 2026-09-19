"""BL-331 (achado A1 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): a guarda do BL-329
(`test_bl329_marca_fora_do_papel.py`) prova só METADE do critério 9 da
DL-026 — "impressão... com a identidade do ESCRITÓRIO". Ela deriva a
propriedade *"a marca do FORNECEDOR não sai no papel"*, mas o requisito tem
DUAS metades: a marca do fornecedor SAI **e** a do escritório ENTRA. A
segunda metade não tinha guarda nenhuma — só um comentário em
`static/css/base.css` dizendo que esconder uma sem repor a outra seria
"pior que o defeito original".

**Medido pelo auditor:** acrescentando `body .timbre-impressao { display:
none }` ao fim do `@media print`, a suíte inteira ficava verde
(`1715 passed`) com o relatório saindo **sem identificação nenhuma** — nem
do fornecedor, nem do escritório.

Este arquivo fecha essa lacuna com a propriedade SIMÉTRICA à do BL-329:
*"o elemento que carrega as linhas de `Escritorio.linhas_do_timbre`
(`.timbre-impressao` em `templates/contabilidade/balancete.html`) tem
`display` efetivo DIFERENTE de `none` sob impressão"* — usando o MESMO
motor de cascata CSS do BL-329 (`_algum_ancestral_removido_do_papel` e
companhia, importados daquele módulo, nunca reescritos aqui: duas cópias
do mesmo motor divergem assim que uma for corrigida sem a outra — a lição
do BL-333, aplicada aqui por composição em vez de repetição).

**Cadeia derivada, não retypada:** o `.timbre-impressao` vive dentro de
`templates/contabilidade/balancete.html`, que é injetado em
`{% block content %}` de `templates/base.html`, dentro de
`<main id="conteudo" class="conteudo-principal">`. Este arquivo deriva a
cadeia REAL combinando as duas árvores — ancestrais de `<main>` em
`base.html` seguidos das ancestrais LOCAIS do `.timbre-impressao` dentro
de `balancete.html` (hoje nenhuma: é filho direto do bloco de conteúdo) —
em vez de presumir ou copiar a estrutura à mão.

⚠️ **BL-362 (BLOQUEADOR H1 da auditoria DL-026, rodada 8,
docs/auditorias/2026-09-19-dl-026-rodada-8.md): a cadeia acima TERMINAVA
no próprio `.timbre-impressao`, e a rodada 12 a estende.** O TEXTO do
timbre mora nos `<p>` FILHOS (`{% for linha in timbre_linhas %}<p>{{
linha }}</p>{% endfor %}`), não no `<div>` que os envolve. Esconder só os
filhos (`.timbre-impressao p { display: none }`) deixava o `<div>`
intacto — a cadeia antiga nunca via essa regra, porque não tinha nó
NENHUM com `tag == "p"` para ela casar (`_no_com_texto_mais_profundo`,
abaixo, resolve isso: desce até o descendente mais profundo que carrega
texto de verdade). Ver o comentário completo junto à função.

**BL-363 (ALTA H2 da mesma auditoria): a cadeia era derivada só de
`balancete.html`.** `diario.html` e `razao.html` têm o MESMO
`.timbre-impressao`, com a MESMA estrutura (filho direto do bloco de
conteúdo), e nunca eram lidos — a cadeia coincidia por COINCIDÊNCIA DE
ESTADO entre os três templates, não por derivação. `_cadeia_do_timbre_
do_escritorio` agora recebe o CAMINHO do template como parâmetro, e
`_templates_com_timbre_impressao` deriva o CONJUNTO de templates a
verificar por VARREDURA de `templates/**` — nenhum nome escrito à mão:
se amanhã o Fiscal ganhar uma tela com timbre, ela entra na guarda
sozinha, sem precisar editar este arquivo.

⚠️ **LEIA ISTO ANTES DE CONFIAR NUM VERDE (rodada 12, decisão do
arquiteto-senior sobre o BL-362): este arquivo responde a condição
NECESSÁRIA, não a SUFICIENTE.** A guarda central
(`test_timbre_do_escritorio_continua_visivel_sob_impressao`) prova
*"nenhum nó da cadeia do timbre tem `display: none` efetivo sob
impressão"* — e prova isso por CONSTRUÇÃO, barato, em toda execução do
`pytest`. Ela NÃO prova *"o timbre está visível de verdade no papel"*:
essa segunda pergunta só o NAVEGADOR responde, e é o instrumento da
[DL-028](../../../docs/planos/DL-028-o-juiz-aponta-para-o-produto.md)
(fatia 2, em construção) que a coloca na integração contínua. Enquanto
essa fatia não existir, seis das onze construções do §H1 da auditoria
rodada 8 (`visibility`, `font-size`, `color`, `position`, `overflow`,
`content-visibility`) passam por ESTE arquivo sem serem pegas — não por
descuido, mas porque **está provado por medição** (ver o comentário de
`_alguma_declaracao_alem_de_display_reduz_visibilidade`, mais abaixo) que
não existe uma extensão do motor simulado que pegue essas seis sem
também acusar CSS real, correto, do próprio timbre. Quem mexer aqui
precisa saber disso antes de declarar a suíte verde como garantia
completa do critério 9.

**O que este arquivo NÃO verifica**, pela mesma razão declarada na
docstring do `test_bl329_marca_fora_do_papel.py`: se o CONTADOR vê o
timbre de verdade (motor de layout real, Chromium) é responsabilidade do
`juiz.py` de bancada — ver `SELETOR_TIMBRE_DO_ESCRITORIO` e o uso dela em
`SONDA_IMPRESSAO_TIMBRE`, extensão desta etapa ao mesmo mecanismo do
BL-329 — e, a partir da DL-028, também da integração contínua.

Dados: nenhum. Este arquivo não usa banco de dados — só lê
`templates/base.html`, `templates/**/*.html` (varredura BL-363) e
`static/css/base.css`, e simula CSS em memória ou em cópias dentro de
`tmp_path` (BL-311: nunca no arquivo real).
"""

import pytest

from apps.contabilidade.tests.test_bl329_marca_fora_do_papel import (
    _BASE_CSS,
    _BASE_HTML,
    _RAIZ,
    _algum_ancestral_removido_do_papel,
    _cadeia_de_ancestrais,
    _escrever_css_mutado,
    _EventoBloco,
    _eventos_de_nivel_superior,
    _extrair_bloco_media_print,
    _identificadores_de_interesse,
    _identificadores_do_seletor,
    _parsear_html,
    _percorrer,
    _remover_comentarios,
    _seletor_bruto_tem_construcao_nao_modelada,
    _seletor_casa_com_no,
    _tem_timbre_impressao,
)

# BL-351 (bloqueador G1 da auditoria DL-026, rodada 7,
# docs/auditorias/2026-09-19-dl-026-rodada-7.md): `_algum_ancestral_
# removido_do_papel` passou a classificar bloco aninhado por CONTEÚDO —
# reprova só quando o bloco menciona algum identificador da CADEIA
# recebida. A assinatura pública da função não mudou (continua
# `(cadeia, css_texto)`); o que muda é que este arquivo agora precisa
# das DUAS construções "escondendo o timbre" do achado F1 (BL-343), que
# antes viviam em test_bl329_marca_fora_do_papel.py testadas contra a
# cadeia da MARCA — sem sentido depois da correção por CONTEÚDO, porque
# `.timbre-impressao` não é identificador daquela cadeia. Movidas para
# cá, contra `_cadeia_do_timbre_do_escritorio()` — a cadeia que elas de
# fato afetam.

_BALANCETE_HTML = _RAIZ / "templates" / "contabilidade" / "balancete.html"
_TEMPLATES_DIR = _RAIZ / "templates"


# BL-363 (ALTA H2 da auditoria DL-026, rodada 8): conjunto de templates a
# verificar, derivado por VARREDURA — nunca uma lista de nomes escrita à
# mão (a mesma lição do BL-352: "derivação compartilhada, domínio
# duplicado" — aqui a lista tinha UM elemento e nem parecia lista, era uma
# constante). Reusa `_tem_timbre_impressao` (test_bl329), a MESMA pergunta
# que já se faz sobre HTML RENDERIZADO — aqui aplicada ao TEXTO FONTE de
# cada template: como o parser deste módulo trata tag Django como texto
# inerte, a estrutura HTML real de um template já aparece na árvore sem
# precisar renderizar nada (a mesma técnica que `_cadeia_da_marca` já usa
# sobre `templates/base.html`).
def _templates_com_timbre_impressao():
    """Devolve, em ordem determinística, o caminho de cada `.html` de
    `templates/**` cuja árvore (fonte, tolerante a Django) tem algum nó de
    classe `timbre-impressao`. Roda na COLETA do pytest (usada em
    `parametrize`) — varredura de arquivo, não de banco, então é barata e
    não precisa de fixture."""
    encontrados = []
    for caminho in sorted(_TEMPLATES_DIR.rglob("*.html")):
        raiz = _parsear_html(caminho.read_text(encoding="utf-8"))
        if _tem_timbre_impressao(raiz):
            encontrados.append(caminho)
    return encontrados


def _id_do_template(caminho):
    """Rótulo do `parametrize` — caminho relativo à raiz do repositório,
    com barras, para o nome do teste NOMEAR a tela (BL-363: "a guarda
    precisa morrer NOMEANDO A TELA", não só "algum teste, em algum
    lugar")."""
    return caminho.relative_to(_RAIZ).as_posix()


def _no_do_conteudo_principal():
    """Localiza `<main id="conteudo" class="conteudo-principal">` em
    `templates/base.html` — o contêiner onde TODO `{% block content %}` é
    injetado (inclusive o de `balancete.html`). O parser deste módulo
    (`_ConstrutorDeArvore`, importado de `test_bl329_marca_fora_do_papel`)
    nunca trata `{% block %}`/`{% endblock %}` como marcação — são tags
    Django, texto inerte para `html.parser.HTMLParser` — então a cadeia de
    ancestrais REAIS de qualquer elemento do bloco de conteúdo continua
    naturalmente a partir daqui."""
    html_bruto = _BASE_HTML.read_text(encoding="utf-8")
    raiz = _parsear_html(html_bruto)
    for no in _percorrer(raiz):
        if no.tag == "main" and "conteudo-principal" in no.classes:
            return no
    raise AssertionError(
        'controle: não achei <main class="conteudo-principal"> em '
        "templates/base.html — a estrutura que este teste espera mudou; "
        "ajuste _no_do_conteudo_principal antes de confiar no resto"
    )


def _no_do_timbre_do_escritorio(caminho_template):
    """Localiza `<div class="timbre-impressao">` em `caminho_template`
    (BL-363: qualquer template da varredura, não só o Balancete) — a mesma
    técnica de `_achar_no_da_marca` (test_bl329_marca_fora_do_papel.py):
    por ESTRUTURA (a classe que `static/css/base.css` e o template já usam
    para o mesmo conceito), nunca pelo TEXTO das linhas do timbre — essas
    vêm de `Escritorio.linhas_do_timbre`, do banco, e nunca aparecem
    literalmente no template nem neste arquivo Python."""
    html_bruto = caminho_template.read_text(encoding="utf-8")
    raiz = _parsear_html(html_bruto)
    for no in _percorrer(raiz):
        if "timbre-impressao" in no.classes:
            return no
    raise AssertionError(
        f"controle: não achei, em {caminho_template}, nenhum elemento de "
        f"classe 'timbre-impressao' — a estrutura que este teste espera "
        f"mudou; ajuste _no_do_timbre_do_escritorio antes de confiar no resto"
    )


# BL-362 (BLOQUEADOR H1, item 1, da auditoria DL-026, rodada 8): a cadeia
# ANTIGA parava no próprio `.timbre-impressao` — mas o TEXTO do timbre
# mora nos `<p>` FILHOS (`{% for linha in timbre_linhas %}<p>{{ linha
# }}</p>{% endfor %}`, ver `templates/contabilidade/balancete.html`), não
# no `<div>` que os envolve. `.timbre-impressao p { display: none }`
# esconde exatamente o que o cliente lê — e a cadeia antiga NUNCA via essa
# regra, porque não tinha nó nenhum com `tag == "p"` para ela casar
# (`_seletor_casa_com_no` exige que o COMPOSTO MAIS À DIREITA do seletor
# case com o ÚLTIMO nó da cadeia — sem um nó "p" na lista, nenhum seletor
# terminado em "p" pode casar NUNCA, não importa o que o CSS diga).
#
# A correção: descer, a partir do `.timbre-impressao`, até o descendente
# MAIS PROFUNDO que carrega TEXTO PRÓPRIO — a mesma convenção que
# `_achar_no_da_marca` já usa para achar o `<a>` da marca "pelo texto que
# ele carrega", generalizada para qualquer profundidade (não só filho
# direto). Hoje isso alcança o `<p>` (texto = o literal `{{ linha }}`, que
# `HTMLParser.handle_data` captura como texto comum — Django não é
# marcação para este parser). Se amanhã alguém envolver o texto num
# `<span>` dentro do `<p>`, esta função desce até LÁ sozinha — não é uma
# lista de tags conhecidas, é a MESMA busca em profundidade percorrendo o
# que a árvore tiver.
def _no_com_texto_mais_profundo(no):
    """Busca em profundidade, a partir de `no` (inclusive), o descendente
    que carrega texto próprio (`texto_proprio` não vazio) na MAIOR
    profundidade. Nunca `None`: se nenhum descendente tiver texto, cai de
    volta no próprio `no` (comportamento idêntico ao de antes desta
    correção — nunca uma regressão para quem não tem filho com texto)."""
    melhor = no if no.texto_proprio else None
    melhor_profundidade = 0 if melhor is not None else -1

    def _visitar(atual, profundidade):
        nonlocal melhor, melhor_profundidade
        if atual.texto_proprio and profundidade > melhor_profundidade:
            melhor = atual
            melhor_profundidade = profundidade
        for filho in atual.filhos:
            _visitar(filho, profundidade + 1)

    _visitar(no, 0)
    return melhor if melhor is not None else no


def _cadeia_do_timbre_do_escritorio(caminho_template):
    """Cadeia raiz→nó do timbre do escritório no documento RENDERIZADO
    real, para `caminho_template` (BL-363: parametrizada — Balancete,
    Diário, Razão hoje; qualquer tela nova com timbre amanhã, sem editar
    este arquivo): as ancestrais de `<main id="conteudo">` em `base.html`
    (onde `{% block content %}` injeta o conteúdo do template, incluindo o
    próprio `<main>`) seguidas das ancestrais LOCAIS do descendente MAIS
    PROFUNDO do `.timbre-impressao` que carrega texto (BL-362, item 1:
    `_no_com_texto_mais_profundo` — hoje isso é o `<p>` de cada linha; sem
    esta extensão a cadeia parava no próprio `<div>` e nunca via uma regra
    que escondesse só os `<p>`). Devolve `(cadeia, no_timbre)` — `no_timbre`
    continua sendo o CONTÊINER (`.timbre-impressao`), não o descendente,
    porque é ele que as mensagens de erro devem nomear."""
    no_conteudo = _no_do_conteudo_principal()
    ancestrais_do_conteudo = _cadeia_de_ancestrais(no_conteudo)

    no_timbre = _no_do_timbre_do_escritorio(caminho_template)
    no_mais_profundo = _no_com_texto_mais_profundo(no_timbre)
    ancestrais_locais_do_timbre = _cadeia_de_ancestrais(no_mais_profundo)

    return ancestrais_do_conteudo + ancestrais_locais_do_timbre, no_timbre


# ---------------------------------------------------------------------------
# Guarda central — propriedade SIMÉTRICA à do BL-329.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caminho_template", _templates_com_timbre_impressao(), ids=_id_do_template)
def test_timbre_do_escritorio_continua_visivel_sob_impressao(caminho_template):
    """A metade do critério 9 que faltava: nenhum nó da cadeia do timbre
    do escritório (do descendente com texto mais profundo — BL-362, item 1
    — até `<html>`) pode ter `display: none` EFETIVO sob impressão — senão
    o papel sai sem identificação nenhuma, nem do fornecedor (já coberto
    pelo BL-329) nem do escritório.

    BL-363: parametrizada sobre TODO template com `.timbre-impressao`
    (`_templates_com_timbre_impressao`, por varredura) — hoje Balancete,
    Diário e Razão; o `ids=_id_do_template` faz o `pytest` NOMEAR A TELA no
    identificador do teste, então uma falha aponta direto para o template
    culpado."""
    cadeia, no_timbre = _cadeia_do_timbre_do_escritorio(caminho_template)
    escondido, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert not escondido, (
        f"{_id_do_template(caminho_template)}: o elemento que carrega "
        f"Escritorio.linhas_do_timbre (cadeia: "
        f"{[(n.tag, n.classes) for n in cadeia]}) tem display:none EFETIVO "
        f"sob impressão, resolvido em "
        f"{(no_que_esconde.tag, no_que_esconde.classes) if no_que_esconde else None} "
        f"— o timbre do escritório NÃO sai no papel"
    )
    assert no_timbre is not None


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA dentro de `tmp_path`).
# As duas sabotagens abaixo reproduzem as DUAS formas que o auditor mediu
# contra o achado A1: (1) a reprodução EXATA do relatório — uma regra MAIS
# ESPECÍFICA, depois, escondendo o timbre; (2) remover a regra que TORNA o
# timbre visível na impressão (o "tripwire por acidente" que o auditor
# apontou: antes desta correção, isto só derrubava o CONTROLE da mutação,
# não a PROPRIEDADE — agora precisa derrubar a propriedade).
# ---------------------------------------------------------------------------


def test_sabotagem_mandatoria_esconder_timbre_por_especificidade_mata_a_guarda(tmp_path):
    """Reprodução EXATA da sabotagem do achado A1: acrescenta, dentro do
    `@media print`, `body .timbre-impressao { display: none; }` — mais
    específica (tipo + classe) que a regra original (só classe), então
    vence a cascata mesmo sem `!important` e sem alterar a ordem relativa
    a favor dela por acidente. No produto medido pelo auditor
    (`53388c8`), essa sabotagem deixava a suíte inteira verde."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    escondido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert not escondido_antes, "controle: o CSS real precisa passar ANTES da sabotagem"

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    body .timbre-impressao {\n        display: none;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
    )
    escondido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois, (
        "a sabotagem mandatória (body .timbre-impressao { display: none }) deveria ter "
        "feito a guarda MORRER (o timbre do escritório escondido), e ela continuou aprovando"
    )


def test_sabotagem_remover_regra_que_reexibe_o_timbre_mata_a_guarda_pela_propriedade(tmp_path):
    """A segunda forma que o auditor mediu: remover a regra inteira que
    torna `.timbre-impressao` visível dentro do `@media print`. Antes
    desta correção, isso só derrubava o CONTROLE de
    `_escrever_css_mutado` do BL-329 quando aplicado à marca (o
    "tripwire por acidente" do achado A1) — aqui a asserção que precisa
    morrer é a da PROPRIEDADE (`escondido_depois`), não a do controle da
    mutação: sem a regra de `@media print`, só resta a regra
    INCONDICIONAL `.timbre-impressao { display: none; }` (fora de
    qualquer `@media`, escondendo na TELA por padrão — ver
    `static/css/base.css`), que passa a valer também na impressão."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    alvo = (
        "    .timbre-impressao {\n"
        "        display: block;\n"
        "        margin-bottom: var(--esp-4);\n"
        "    }"
    )
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, "")
    escondido_depois, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois, (
        "remover a regra que reexibe o timbre na impressão deveria ter feito a guarda "
        "MORRER PELA PROPRIEDADE (nenhuma regra reexibe o timbre sob impressão, e a "
        "regra incondicional de tela — display:none — volta a valer), e ela continuou "
        "aprovando"
    )
    assert no_que_esconde is not None


# ---------------------------------------------------------------------------
# BL-343/F1 (auditoria DL-026, rodada 6) + BL-351 (rodada 7): as DUAS
# construções "escondendo o timbre" da tabela do achado F1 — MOVIDAS de
# test_bl329_marca_fora_do_papel.py para cá (ver comentário junto ao
# import, no topo deste arquivo). `.timbre-impressao` É identificador da
# cadeia do TIMBRE (`_cadeia_do_timbre_do_escritorio`), então a
# classificação por CONTEÚDO (BL-351) reprova corretamente as duas —
# ao contrário do que aconteceria se continuassem testadas contra a
# cadeia da marca, em test_bl329.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "at_rule",
    ["@media (min-width: 20rem)", "@supports (display: grid)"],
)
def test_f1_construcoes_que_escondem_o_timbre_reprovam_pedindo_extensao(tmp_path, at_rule):
    """BL-343/F1, movida pelo BL-351: `{at_rule} { .timbre-impressao {
    display: none; } }`, acrescentada ao FIM de uma CÓPIA do `base.css`
    real (o `@media print` original intocado — exatamente como o auditor
    mediu). Precisa reprovar PEDINDO EXTENSÃO: a simulação não sabe se
    `{at_rule}` se aplica à impressão, e o bloco MENCIONA
    `.timbre-impressao` — identificador da cadeia de interesse deste
    arquivo."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = f"{at_rule} {{\n    .timbre-impressao {{\n        display: none;\n    }}\n}}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


# ---------------------------------------------------------------------------
# BL-351 (bloqueador G1 da auditoria DL-026, rodada 7,
# docs/auditorias/2026-09-19-dl-026-rodada-7.md): a construção EXATA do
# relatório do auditor que esconde o TIMBRE via CSS Nesting nativo, e a
# variante de DOIS níveis de aninhamento (DE-055) que só a RECURSÃO da
# classificação por conteúdo alcança.
# ---------------------------------------------------------------------------


def test_sabotagem_css_nesting_nativo_esconde_o_timbre_mata_a_guarda(tmp_path):
    """G1 — a construção EXATA que o auditor mediu: `.conteudo-principal
    { .timbre-impressao { display: none } }`, CSS Nesting NATIVO. Antes
    do BL-351, o detector só abria o laço em `if texto[i] == "@"` — este
    bloco nunca era visto, era içado como regra comum, e o timbre do
    escritório saía apagado (folha sem emitente nenhum). Precisa
    REPROVAR: `.timbre-impressao` é identificador da cadeia do timbre."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = ".conteudo-principal {\n    .timbre-impressao {\n        display: none;\n    }\n}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_sabotagem_css_nesting_dois_niveis_esconde_o_timbre_mata_a_guarda(tmp_path):
    """DE-055 — construção MINHA: aninhamento de DOIS níveis
    (`.conteudo-principal { .rodape { .timbre-impressao { display: none }
    } }`), com a relevância só no bloco MAIS INTERNO — `.rodape` não é
    identificador de interesse nenhum; só `.timbre-impressao`, dois
    níveis abaixo do prelúdio externo, é. Prova que
    `_identificadores_mencionados_no_bloco` de fato RECURSA (chama a si
    mesma sobre cada bloco de nível superior do corpo) em vez de olhar só
    um nível — se parasse no primeiro nível, veria só `conteudo-
    principal`/`rodape` e classificaria o bloco como irrelevante por
    engano, deixando o timbre desaparecer em silêncio."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = (
        ".conteudo-principal {\n"
        "    .rodape {\n"
        "        .timbre-impressao {\n"
        "            display: none;\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


# ---------------------------------------------------------------------------
# BL-348 (F6 da auditoria DL-026, rodada 6,
# docs/auditorias/2026-09-19-dl-026-rodada-6.md): o parser tolerante
# (`_parsear_html`, test_bl329_marca_fora_do_papel.py) TRUNCAVA em silêncio
# quando um comentário de gabarito continha uma palavra entre "<" e ">"
# que colidisse com "title"/"textarea" (html.parser.HTMLParser.
# RCDATA_CONTENT_ELEMENTS) — e, quando reclamava (por ACIDENTE, via outro
# controle), a mensagem mandava "ajustar `_no_do_timbre_do_escritorio`",
# apontando para este arquivo em vez de para o TEMPLATE. Duas provas, nas
# MESMAS duas posições que o auditor mediu (antes e depois do
# `.timbre-impressao`):
#
# 1. A sabotagem EXATA que o auditor reproduziu — a palavra dentro de um
#    `{% comment %}` de verdade — agora é NEUTRALIZADA: comentário de
#    gabarito nunca chega ao HTML entregue, `_parsear_html` remove o
#    bloco INTEIRO antes do parse, e a mesma sabotagem fica sem efeito
#    algum (nem trunca, nem precisa reprovar — não há mais defeito).
# 2. O CONTROLE DE NÃO-TRUNCAMENTO segura o que a remoção de comentários
#    NÃO cobre, de propósito: a mesma palavra FORA de qualquer
#    `{% comment %}` — marcação malformada de verdade, não comentário —,
#    reprovando com mensagem que nomeia o TEMPLATE como causa.
# ---------------------------------------------------------------------------


def _balancete_mutado(tmp_path, *, sabotagem_antes="", sabotagem_depois=""):
    """Cópia de `templates/contabilidade/balancete.html` (BL-311: nunca o
    arquivo real) com texto arbitrário inserido imediatamente ANTES e/ou
    DEPOIS do `<div class="timbre-impressao">`."""
    conteudo = _BALANCETE_HTML.read_text(encoding="utf-8")
    alvo = '<div class="timbre-impressao">'
    assert alvo in conteudo, "controle: marcador do timbre não encontrado em balancete.html"
    mutado = conteudo.replace(alvo, sabotagem_antes + alvo + sabotagem_depois, 1)
    assert mutado != conteudo, "controle: a mutação precisa mudar o conteúdo"
    caminho = tmp_path / "balancete-mutado.html"
    caminho.write_text(mutado, encoding="utf-8")
    return caminho


@pytest.mark.parametrize("posicao", ["antes", "depois"])
def test_palavra_entre_menor_e_maior_dentro_de_comment_de_gabarito_e_neutralizada(
    tmp_path, posicao
):
    """Reprodução EXATA de S5a/S5c do achado F6: um bloco `{% comment %}`
    contendo a palavra "title" entre "<" e ">", nas DUAS posições que o
    auditor testou. ANTES desta correção: "depois" truncava a árvore em
    silêncio (`1775 passed`, nada reclamava); "antes" reprovava só por
    ACIDENTE, via outro controle não relacionado, com mensagem que mandava
    mexer neste arquivo. Agora `_parsear_html` remove o bloco de
    comentário INTEIRO antes do parse — comentário de gabarito nunca
    chega ao HTML entregue —, então a MESMA sabotagem fica sem efeito
    nenhum: o timbre continua sendo encontrado normalmente, nas duas
    posições."""
    comentario = "{% comment %}\nver <title> aqui\n{% endcomment %}\n"
    caminho_mutado = _balancete_mutado(
        tmp_path,
        sabotagem_antes=comentario if posicao == "antes" else "",
        sabotagem_depois=comentario if posicao == "depois" else "",
    )
    raiz = _parsear_html(caminho_mutado.read_text(encoding="utf-8"))
    tem_timbre = any("timbre-impressao" in no.classes for no in _percorrer(raiz))
    assert tem_timbre, (
        f"posição {posicao!r}: o comentário de gabarito com uma palavra entre "
        f"'<' e '>' NÃO deveria mais afetar o parse — e o timbre sumiu da árvore"
    )


# ---------------------------------------------------------------------------
# BL-363 (ALTA H2 da auditoria DL-026, rodada 8): a sabotagem do achado H2
# — agrupar o timbre num contêiner (`.cabecalho-do-documento`) e escondê-lo
# no `@media print` — reproduzida em RAZÃO e DIÁRIO, exigindo que a guarda
# morra NOMEANDO A TELA (o `ids=_id_do_template` do teste parametrizado
# central já faz isso; aqui é a SABOTAGEM que precisa produzir o mesmo
# resultado nos dois templates, não só no Balancete). Controle negativo:
# o MESMO contêiner, SEM a regra de impressão que o esconde, continua
# aprovando — prova de que "ganhar um contêiner novo" sozinho não é
# suficiente para reprovar (só "ganhar um contêiner ESCONDIDO" é).
# ---------------------------------------------------------------------------


def _template_com_timbre_envolto_em_cabecalho_do_documento(tmp_path, caminho_template):
    """Cópia de `caminho_template` (BL-311: nunca o arquivo real) com
    `.timbre-impressao` envolvida por um NOVO contêiner
    `<div class="cabecalho-do-documento">` — a mesma reprodução do achado
    H2 (docs/auditorias/2026-09-19-dl-026-rodada-8.md, §H2), generalizada
    para qualquer template com timbre em vez de reescrita à mão para cada
    tela."""
    conteudo = caminho_template.read_text(encoding="utf-8")
    alvo = '<div class="timbre-impressao">'
    assert alvo in conteudo, (
        f"controle: marcador do timbre não encontrado em {caminho_template.name}"
    )
    idx_abertura = conteudo.index(alvo)
    idx_fechamento = conteudo.index("</div>", idx_abertura)
    fim_do_fechamento = idx_fechamento + len("</div>")
    mutado = (
        conteudo[:idx_abertura]
        + '<div class="cabecalho-do-documento">\n    '
        + conteudo[idx_abertura:fim_do_fechamento]
        + "\n</div>"
        + conteudo[fim_do_fechamento:]
    )
    assert mutado != conteudo, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado = tmp_path / caminho_template.name
    caminho_mutado.write_text(mutado, encoding="utf-8")
    return caminho_mutado


@pytest.mark.parametrize(
    "caminho_template",
    [
        _RAIZ / "templates" / "contabilidade" / "razao.html",
        _RAIZ / "templates" / "contabilidade" / "diario.html",
    ],
    ids=_id_do_template,
)
def test_sabotagem_h2_cabecalho_do_documento_oculto_mata_a_guarda_nomeando_a_tela(
    tmp_path, caminho_template
):
    """H2/BL-363: reproduz a sabotagem do achado — agrupar o timbre num
    contêiner e escondê-lo no `@media print` — contra RAZÃO e DIÁRIO, não
    só o Balancete (que já tinha cobertura equivalente por outro caminho).
    Precisa morrer PELA PROPRIEDADE, e o parâmetro `caminho_template` (via
    `ids=_id_do_template`) já nomeia a tela no identificador do teste."""
    caminho_template_mutado = _template_com_timbre_envolto_em_cabecalho_do_documento(
        tmp_path, caminho_template
    )
    cadeia, _ = _cadeia_do_timbre_do_escritorio(caminho_template_mutado)

    css_original = _BASE_CSS.read_text(encoding="utf-8")
    caminho_css_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    .cabecalho-do-documento {\n        display: none;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
        nome="base-mutado-h2.css",
    )
    escondido, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_css_mutado.read_text(encoding="utf-8")
    )
    assert escondido, (
        f"{_id_do_template(caminho_template)}: a sabotagem do cabeçalho do "
        f"documento (H2) deveria ter feito a guarda MORRER PELA PROPRIEDADE, "
        f"e ela continuou aprovando"
    )


@pytest.mark.parametrize(
    "caminho_template",
    [
        _RAIZ / "templates" / "contabilidade" / "razao.html",
        _RAIZ / "templates" / "contabilidade" / "diario.html",
    ],
    ids=_id_do_template,
)
def test_cabecalho_do_documento_sem_regra_de_impressao_continua_aprovando(
    tmp_path, caminho_template
):
    """Controle NEGATIVO do H2/BL-363: o MESMO contêiner novo
    (`.cabecalho-do-documento`), SEM nenhuma regra de CSS que o esconda —
    só ganhar um contêiner não é, sozinho, motivo para a guarda reprovar;
    só ganhar um contêiner ESCONDIDO é (teste acima). Sem isto, a
    generalização da cadeia (BL-362/BL-363) poderia estar reprovando por
    QUALQUER contêiner novo, o falso alarme que o BL-321 já apontou como
    mais corrosivo que o falso negativo."""
    caminho_template_mutado = _template_com_timbre_envolto_em_cabecalho_do_documento(
        tmp_path, caminho_template
    )
    cadeia, _ = _cadeia_do_timbre_do_escritorio(caminho_template_mutado)
    escondido, _ = _algum_ancestral_removido_do_papel(cadeia, _BASE_CSS.read_text(encoding="utf-8"))
    assert not escondido, (
        f"{_id_do_template(caminho_template)}: um contêiner novo SEM regra de "
        f"impressão que o esconda não deveria fazer a guarda reprovar — e ela "
        f"reprovou (falso alarme)"
    )


@pytest.mark.parametrize("posicao", ["antes", "depois"])
def test_palavra_entre_menor_e_maior_fora_de_comment_reprova_nomeando_o_template(tmp_path, posicao):
    """Controle de NÃO-TRUNCAMENTO (BL-348/F6): a MESMA palavra, agora
    FORA de qualquer bloco `{% comment %}` — marcação malformada de
    VERDADE, o caso que a remoção de comentários não cobre, de propósito
    (não é comentário de gabarito; é erro real de template) —, nas
    mesmas duas posições. `_parsear_html` precisa REPROVAR (nunca truncar
    em silêncio), com mensagem que NOMEIE o template como causa provável
    — não "ajuste este arquivo de teste"."""
    sabotagem = "texto solto <title> sem fechamento\n"
    caminho_mutado = _balancete_mutado(
        tmp_path,
        sabotagem_antes=sabotagem if posicao == "antes" else "",
        sabotagem_depois=sabotagem if posicao == "depois" else "",
    )
    with pytest.raises(AssertionError, match="CONFIRA O TEMPLATE"):
        _parsear_html(caminho_mutado.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# BL-362 (BLOQUEADOR H1 da auditoria DL-026, rodada 8) — as ONZE construções
# do §H1 do relatório, cada uma como teste. Nove são "falso conforme" que a
# guarda antiga aprovava; duas são controle (uma recusa por outro mecanismo
# já existente — BL-360 —, a outra é `!important`, que precisa continuar
# fazendo a guarda enxergar a ocultação de verdade, não "passar"). Usa a
# tabela do §H1 do relatório, não reescrita de memória.
#
# Depois da correção dos itens 1 (cadeia estendida aos descendentes com
# texto) e 3 (pseudo-classe estrutural recusa, não é descartada), TRÊS das
# nove são cobertas por ESTE arquivo sozinho: a que esconde os `<p>`
# filhos (item 1) e as duas com pseudo-classe estrutural (item 3). As
# outras SEIS dependem do item 2 (qualquer propriedade além de display, em
# regra que casa com a cadeia, recusa) — ver a seção "item 2" mais abaixo
# nesta mesma tabela, e o comentário sobre por que ele NÃO está ligado ao
# veredito da guarda hoje.
# ---------------------------------------------------------------------------


def test_h1_esconder_os_filhos_p_mata_a_guarda_pela_propriedade(tmp_path):
    """H1, construção 1 — a PRIMEIRA causa do bloqueador: a cadeia antiga
    parava no `.timbre-impressao`, e o TEXTO mora nos `<p>` filhos.
    `.timbre-impressao p { display: none; }` apagava o timbre com
    `1871 passed` porque nenhum nó da cadeia tinha `tag == "p"` para essa
    regra casar. BL-362, item 1 (`_no_com_texto_mais_profundo`) estende a
    cadeia até o `<p>` — agora esta regra CASA e vence a cascata (mais
    específica que `.timbre-impressao p { margin: ... }`, que não declara
    display)."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao p {\n        margin: 0 0 var(--esp-1);\n    }",
        "    .timbre-impressao p {\n        margin: 0 0 var(--esp-1);\n"
        "        display: none;\n    }",
        nome="base-mutado-h1-filhos.css",
    )
    escondido, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido, (
        "H1/construção 1 (.timbre-impressao p { display: none }) deveria ter "
        "feito a guarda MORRER PELA PROPRIEDADE, e ela continuou aprovando"
    )


@pytest.mark.parametrize(
    "rotulo,bloco_css",
    [
        (
            "H1/construção 9 — pseudo-classe estrutural no PRÓPRIO seletor",
            ".timbre-impressao:first-child {\n        display: none;\n    }",
        ),
        (
            "H1/construção 10 — pseudo-classe estrutural num ANCESTRAL",
            "main:first-of-type .timbre-impressao {\n        display: none;\n    }",
        ),
    ],
)
def test_h1_pseudo_classe_estrutural_recusa_julgar(tmp_path, rotulo, bloco_css):
    """H1, construções 9 e 10 — a TERCEIRA causa do bloqueador: o descarte
    de pseudo-classe condicional (BL-333, decisão 2) tratava
    `:first-child`/`:first-of-type` como se fossem `:hover`, descartando a
    candidata `display:none` como se a interação nunca ocorresse — quando,
    na verdade, é ESTRUTURAL e ocorre no papel igual à tela. BL-362, item 3
    corrige: RECUSA JULGAR (o motor não simula posição entre irmãos, não
    pode fingir que sabe se `:first-of-type` casa)."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        f"    {bloco_css}\n\n    .timbre-impressao {{\n        display: block;",
        nome="base-mutado-h1-pseudo.css",
    )
    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, caminho_mutado.read_text(encoding="utf-8"))


def test_h1_controle_universal_dentro_do_timbre_recusa_por_bl360(tmp_path):
    """H1 — controle de recusa (`.timbre-impressao * { display: none }`,
    linha 11 da sondagem do relatório): precisa RECUSAR, pelo mecanismo já
    existente do BL-360 (`*` é gramática não modelada declarando `display`)
    — não é um comportamento NOVO desta rodada, é a confirmação de que ele
    continua funcionando depois das mudanças dos itens 1 e 3."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    .timbre-impressao * {\n        display: none;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
        nome="base-mutado-h1-universal.css",
    )
    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, caminho_mutado.read_text(encoding="utf-8"))


def test_h1_controle_important_mata_a_guarda_de_verdade(tmp_path):
    """H1 — controle de detecção (`.timbre-impressao { display: none
    !important }`, linha 12 da sondagem do relatório): a guarda precisa
    ENXERGAR a ocultação real — `!important` vence a cascata sobre
    QUALQUER outra declaração de display, então `escondido` precisa ser
    `True`. Não é um "falso conforme": é o comportamento CORRETO diante de
    um CSS que de fato apaga o timbre."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    .timbre-impressao {\n        display: none !important;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
        nome="base-mutado-h1-important.css",
    )
    escondido, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido, (
        "!important escondendo o timbre de verdade precisa fazer a guarda "
        "enxergar a ocultação (escondido=True) — ela não enxergou"
    )


def test_item3_hover_continua_sendo_descartado_como_seguro(tmp_path):
    """Regressão do BL-362, item 3: `:hover` (pseudo-classe de INTERAÇÃO)
    continua sendo DESCARTADA como candidata de `display:none` — nunca
    RECUSA julgar, porque o motor SABE que ela não ocorre no papel (ao
    contrário de `:first-of-type`, que ele não sabe avaliar). Sem esta
    prova, a correção do item 3 poderia ter virado "toda pseudo-classe
    recusa", o que reintroduziria o falso alarme que o BL-333 já tinha
    fechado para `:hover`."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    .timbre-impressao:hover {\n        display: none;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
        nome="base-mutado-item3-hover.css",
    )
    escondido, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert not escondido, (
        ":hover é pseudo-classe de INTERAÇÃO — nunca ocorre no papel; a "
        "guarda não deveria recusar julgar nem considerar o timbre escondido "
        "por causa dela, e um dos dois aconteceu"
    )


# ---------------------------------------------------------------------------
# BL-362, item 2 — LIMITE DECLARADO DO MOTOR SIMULADO, COM PROVA MEDIDA.
#
# O pedido original (rodada 12) dizia: "para o lado 'apareça', qualquer
# declaração que possa REDUZIR visibilidade — não só display — faz a guarda
# recusar julgar [...] o motor sabe julgar display e mais nada; então
# qualquer declaração que não seja display, dentro de regra que case com a
# cadeia do timbre, faz recusar." A função abaixo implementa essa frase
# LITERALMENTE — sem lista de propriedades "perigosas" e sem lista de
# valores "seguros": QUALQUER declaração cuja propriedade não seja
# `display`, numa regra FLAT cujo seletor casa com algum nó da cadeia do
# timbre (mesma técnica de `_seletor_casa_com_no`; para seletor de
# gramática NÃO MODELADA, a mesma aproximação por IDENTIFICADOR que o resto
# do motor já usa para bloco aninhado — nunca confiar em
# `_seletor_casa_com_no` sobre uma gramática que ele não entende, a razão
# do BL-360), faz RECUSAR.
#
# ⚠️ **ESTA FUNÇÃO NÃO ESTÁ LIGADA a `_algum_ancestral_removido_do_papel`
# NEM à guarda central deste arquivo — E O ARQUITETO-SENIOR CONFIRMOU QUE
# NÃO PODE ESTAR, DEPOIS DE MEDIR AS ALTERNATIVAS.** Não é mais uma
# pendência a integrar "depois": é um LIMITE do instrumento, provado por
# CONSTRUÇÃO, não por falta de esforço. Três medições, nesta ordem:
#
# 1. **Pela CADEIA inteira** (a leitura literal do pedido — qualquer nó,
#    de `<html>` ao `<p>` do timbre): dispara **9 vezes** no `base.css`
#    real, sem sabotagem nenhuma — 5 regras "antes" do `@media print`
#    (`:root`, `html`, `body`, `p`, `.conteudo-principal` — a cadeia
#    inclui `<html>`/`<body>`, topo de QUALQUER documento, então
#    praticamente toda a folha de tokens de `:root` e os estilos-base
#    casam) e 4 "dentro" (`.timbre-impressao` — `margin-bottom`;
#    `.timbre-impressao p` — `margin`; `.timbre-impressao p:first-child`
#    — `font-weight`/`font-size`; `body` — `background`/`color`).
# 2. **Restringindo a regras que MENCIONAM o identificador `timbre-
#    impressao`** (não "casam estruturalmente com algum nó da cadeia" —
#    a mesma técnica de `_identificadores_do_seletor`, aplicada ao NOME
#    da classe, não à estrutura): elimina as 5 "antes" (`:root` só
#    "casa" por acidente aritmético — `all([])` — e `p`/`html`/`body`
#    nunca MENCIONAM `timbre-impressao`) — mas **sobram as 3 de dentro do
#    `@media print`**, que são declarações de LAYOUT perfeitamente
#    legítimas sobre o timbre (margem entre linhas, peso da primeira
#    linha). Não é zero. Ver
#    `test_item2_restrito_ao_identificador_timbre_impressao_ainda_dispara_tres_vezes`,
#    abaixo, que fixa esta medição.
# 3. **Restringindo por PROPRIEDADE** ("declarações que podem afetar
#    visibilidade": `visibility`, `opacity`, `clip-path`, `font-size`,
#    `color`, `position`, `overflow`, `content-visibility`, `transform`,
#    `height`/`width`...) — **é voltar a escrever a lista que o pedido
#    original mandou não escrever**, e que cresce com a linguagem todo
#    ano (a mesma classe de defeito do BL-355, já corrigida nesta etapa
#    invertendo o lado seguro).
#
# **Conclusão, confirmada pelo arquiteto-senior depois de tentar as duas
# alternativas acima: não existe formulação mais estreita do item 2 que
# sobreviva sem lista OU sem falso alarme.** Não é limitação de esforço —
# é do INSTRUMENTO (o argumento do §7 do auditor da rodada 8, agora
# provado por construção, não só por argumento). Por isso a divisão de
# trabalho passou a ser esta, e precisa continuar assim até a DL-028
# entregar a fatia 2:
#
#   | Pergunta                                              | Quem responde |
#   |--------------------------------------------------------|---------------|
#   | "Nenhum nó da cadeia do timbre tem `display:none`      | Este motor    |
#   |  sob impressão?" (condição NECESSÁRIA, barata,         | simulado —    |
#   |  toda execução do `pytest`)                             | SEMPRE roda   |
#   | "O timbre está visível de verdade no papel?"           | O NAVEGADOR,  |
#   |  (condição SUFICIENTE)                                  | pelo          |
#   |                                                          | instrumento   |
#   |                                                          | da DL-028     |
#
# A função abaixo continua IMPLEMENTADA e TESTADA (contra CSS SINTÉTICO
# isolado, para a demonstração não ficar contaminada pelas declarações
# reais do timbre, que são legítimas) — ela prova que o MECANISMO
# funciona (opacity/transform/clip-path recusam de verdade) e prova, por
# medição, POR QUE ele não pode virar o veredito obrigatório. Ver
# `test_o_motor_simulado_nao_consegue_decidir_visibilidade_sem_falso_alarme`,
# mais abaixo, que fixa a medição #1 desta lista.
# ---------------------------------------------------------------------------


def _declaracoes_de_regra_flat(corpo):
    """(propriedade, valor) de CADA declaração em `corpo` (texto de um
    `_EventoBloco` FLAT — sem bloco aninhado dentro) — TODAS as
    propriedades, ao contrário de `_extrair_regras_flat`
    (test_bl329_marca_fora_do_papel.py), que filtra por
    `_PROPRIEDADES_DE_INTERESSE`. Usada só pelo mecanismo do item 2, que
    precisa examinar QUALQUER declaração para decidir se há alguma além
    de `display`."""
    declaracoes = []
    for decl in corpo.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, valor = decl.partition(":")
        declaracoes.append((prop.strip().lower(), valor.strip()))
    return declaracoes


def _regras_flat_relevantes_com_propriedade_alem_de_display(texto, cadeia):
    """Regras FLAT (sem bloco aninhado dentro — at-rule aninhada fica de
    FORA do escopo desta função, uma limitação CONHECIDA e documentada,
    não uma pretensão de cobrir tudo: nenhuma das construções que este
    item precisa cobrir usa at-rule aninhada) de `texto` cujo seletor é
    RELEVANTE para `cadeia`, com as declarações que não são `display`.

    "Relevante" por dois caminhos, na MESMA ordem de confiança que o
    resto do motor já usa: (a) gramática RECONHECIDA
    (`_seletor_bruto_tem_construcao_nao_modelada` diz que não) — usa
    `_seletor_casa_com_no` de verdade, casamento seletor↔nó; (b) gramática
    NÃO reconhecida — nunca confia em `_seletor_casa_com_no` sobre ela (a
    razão do BL-360: `[class]`/`*` "casam" com QUALQUER nó por `all([])`,
    um acidente aritmético, não uma leitura), então cai para a MESMA
    aproximação por IDENTIFICADOR que `_identificadores_mencionados_no_
    bloco` já usa para bloco aninhado: relevante se o seletor MENCIONA
    (classe ou tipo) algum identificador da cadeia de interesse."""
    identificadores_de_interesse = _identificadores_de_interesse(cadeia)
    achados = []
    for evento in _eventos_de_nivel_superior(texto):
        if not isinstance(evento, _EventoBloco) or evento.aninhado:
            continue
        seletor_bruto = evento.prelude.strip()
        if not seletor_bruto or seletor_bruto.startswith("@"):
            continue
        outras = [
            (prop, valor)
            for prop, valor in _declaracoes_de_regra_flat(evento.corpo)
            if prop != "display"
        ]
        if not outras:
            continue
        for seletor in seletor_bruto.split(","):
            seletor = seletor.strip()
            compostos = [c for c in seletor.split() if c]
            if not compostos:
                continue
            if _seletor_bruto_tem_construcao_nao_modelada(seletor):
                identificadores_do_seletor = _identificadores_do_seletor(seletor)
                relevante = bool(identificadores_do_seletor & identificadores_de_interesse)
            else:
                relevante = any(
                    _seletor_casa_com_no(compostos, i, cadeia) for i in range(len(cadeia))
                )
            if relevante:
                achados.append((seletor, outras))
    return achados


def _alguma_declaracao_alem_de_display_reduz_visibilidade(cadeia, css_texto):
    """BL-362, item 2 — ver o comentário completo acima sobre por que esta
    função existe, foi testada, e NÃO está ligada ao veredito obrigatório
    da guarda. Devolve `(recusa: bool, motivo: str | None)`, examinando os
    três trechos que `_extrair_bloco_media_print` já separa (antes/dentro/
    depois do único `@media print`)."""
    antes, dentro, depois = _extrair_bloco_media_print(css_texto)
    for trecho in (antes, dentro, depois):
        achados = _regras_flat_relevantes_com_propriedade_alem_de_display(
            _remover_comentarios(trecho), cadeia
        )
        if achados:
            seletor, outras = achados[0]
            motivo = (
                f"a simulação (BL-362, item 2) encontrou, numa regra que casa com a "
                f"cadeia do timbre, declaração(ões) além de display: {seletor!r} "
                f"declara {outras!r} — o motor só sabe julgar display; PRECISA SER "
                f"ESTENDIDA antes de confiar no resultado"
            )
            return True, motivo
    return False, None


# CSS sintético MÍNIMO e ISOLADO (não é o base.css real) — evita que a
# demonstração do item 2 fique contaminada pelo conflito, já documentado
# acima, entre a regra REAL `.timbre-impressao { margin-bottom: ... }` e a
# leitura literal do item 2. Usa a CADEIA real (derivada de
# `templates/contabilidade/balancete.html` de verdade — só o CSS é
# sintético), então ainda é uma prova sobre a estrutura real do produto.
_CSS_SINTETICO_TIMBRE_MINIMO = (
    "@media print {\n    .timbre-impressao {\n        display: block;\n    }\n}\n"
)


@pytest.mark.parametrize(
    "rotulo,declaracao",
    [
        ("DE-056 — opacity: 0", "opacity: 0;"),
        ("DE-056 — transform: scale(0)", "transform: scale(0);"),
        ("DE-056 — clip-path: inset(100%)", "clip-path: inset(100%);"),
    ],
)
def test_item2_declaracao_que_reduz_visibilidade_recusa_julgar(rotulo, declaracao):
    """DE-056: três construções que MIRAM um eixo que o relatório do
    auditor não discutiu por nome — `opacity`/`transform`/`clip-path`, não
    `display` nem `visibility`. Sobre o CSS SINTÉTICO isolado (não o
    base.css real — ver o comentário acima sobre o conflito conhecido),
    acrescentando a declaração DENTRO da mesma regra `.timbre-impressao`
    que já declara `display: block`: precisa RECUSAR julgar."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_sintetico = _CSS_SINTETICO_TIMBRE_MINIMO.replace(
        "display: block;", f"display: block;\n        {declaracao}"
    )
    recusa, motivo = _alguma_declaracao_alem_de_display_reduz_visibilidade(cadeia, css_sintetico)
    assert recusa, f"{rotulo}: deveria ter recusado julgar, e não recusou"
    assert motivo is not None


def test_item2_tabela_dados_fora_da_cadeia_do_timbre_nao_recusa():
    """DE-056, controle: `.tabela-dados { visibility: hidden }` — FORA da
    cadeia do timbre (nenhum identificador em comum). A recusa do item 2 é
    ESCOPADA por relevância — do mesmo jeito que o resto do motor sempre
    foi —, então isto não pode virar falso alarme."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_sintetico = _CSS_SINTETICO_TIMBRE_MINIMO[:-1] + (
        "\n.tabela-dados {\n    visibility: hidden;\n}\n"
    )
    recusa, motivo = _alguma_declaracao_alem_de_display_reduz_visibilidade(cadeia, css_sintetico)
    assert not recusa, (
        f".tabela-dados está FORA da cadeia do timbre — não deveria recusar, e recusou ({motivo})"
    )


def test_item2_color_na_regra_do_timbre_tambem_recusa_e_isso_diverge_da_de056():
    """⚠️ Este teste documenta um CONFLITO, não uma correção fechada — ver
    o comentário completo acima e o relatório desta rodada.

    A DE-056 pede que `.timbre-impressao { color: var(--tinta-principal)
    }` PASSE ("declaração que não reduz visibilidade nenhuma não pode
    virar falso alarme"). A LEITURA LITERAL do item 2 ("qualquer
    declaração que não seja display, em regra que casa, recusa") não abre
    exceção nenhuma para `color` — e a regra REAL `.timbre-impressao {
    margin-bottom: var(--esp-4); }` já teria o mesmo problema (ver medição
    no relatório). Este teste registra o comportamento ATUAL (recusa
    também) em vez de forçar silenciosamente uma exceção sem derivação —
    a decisão de como reconciliar os dois pedidos fica para o
    arquiteto-senior confirmar."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    css_sintetico = _CSS_SINTETICO_TIMBRE_MINIMO.replace(
        "display: block;", "display: block;\n        color: var(--tinta-principal);"
    )
    recusa, motivo = _alguma_declaracao_alem_de_display_reduz_visibilidade(cadeia, css_sintetico)
    assert recusa, (
        "comportamento ATUAL (documentado, não o desejado pela DE-056): a leitura "
        "literal do item 2 recusa também para 'color', por não haver uma forma "
        "DERIVADA (sem lista) de excluir só esta propriedade"
    )


def test_item2_base_css_real_dispara_hoje_sem_sabotagem_nenhuma():
    """Medição OBRIGATÓRIA (pedido do arquiteto-senior: "meça você mesmo
    antes de confiar") — quantas vezes a leitura literal do item 2 dispara
    contra o `static/css/base.css` REAL de hoje, sem nenhuma sabotagem.
    Fixa o número MEDIDO (não zero) como uma PINAGEM CONHECIDA — se este
    teste um dia falhar porque o número MUDOU, é sinal para reler o
    relatório desta rodada antes de alargar ou estreitar qualquer coisa,
    não para ajustar o número às cegas.

    Por isso a função do item 2 NÃO está ligada ao veredito da guarda:
    ligá-la faria a suíte ficar vermelha SEM sabotagem nenhuma, o oposto
    do que a guarda deveria fazer."""
    cadeia, _ = _cadeia_do_timbre_do_escritorio(_BALANCETE_HTML)
    recusa, motivo = _alguma_declaracao_alem_de_display_reduz_visibilidade(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert recusa, (
        "esperava que o base.css REAL de hoje já disparasse o item 2 (regras "
        "conhecidas: margin-bottom em .timbre-impressao, margin/font-weight/"
        "font-size em .timbre-impressao p) — se isto passou a False, o CSS real "
        "mudou; confira ANTES de supor que o conflito com a DE-056 sumiu"
    )
    assert motivo is not None
