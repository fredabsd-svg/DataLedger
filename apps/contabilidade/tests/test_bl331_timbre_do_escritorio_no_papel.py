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

**O que este arquivo NÃO verifica**, pela mesma razão declarada na
docstring do `test_bl329_marca_fora_do_papel.py`: se o CONTADOR vê o
timbre de verdade (motor de layout real, Chromium) é responsabilidade do
`juiz.py` de bancada — ver `SELETOR_TIMBRE_DO_ESCRITORIO` e o uso dela em
`SONDA_IMPRESSAO_TIMBRE`, extensão desta etapa ao mesmo mecanismo do
BL-329.

Dados: nenhum. Este arquivo não usa banco de dados — só lê
`templates/base.html`, `templates/contabilidade/balancete.html` e
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
    _parsear_html,
    _percorrer,
)

_BALANCETE_HTML = _RAIZ / "templates" / "contabilidade" / "balancete.html"


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


def _no_do_timbre_do_escritorio():
    """Localiza `<div class="timbre-impressao">` em
    `templates/contabilidade/balancete.html` — a mesma técnica de
    `_achar_no_da_marca` (test_bl329_marca_fora_do_papel.py): por
    ESTRUTURA (a classe que `static/css/base.css` e este template já usam
    para o mesmo conceito), nunca pelo TEXTO das linhas do timbre — essas
    vêm de `Escritorio.linhas_do_timbre`, do banco, e nunca aparecem
    literalmente no template nem neste arquivo Python."""
    html_bruto = _BALANCETE_HTML.read_text(encoding="utf-8")
    raiz = _parsear_html(html_bruto)
    for no in _percorrer(raiz):
        if "timbre-impressao" in no.classes:
            return no
    raise AssertionError(
        "controle: não achei, em templates/contabilidade/balancete.html, "
        "nenhum elemento de classe 'timbre-impressao' — a estrutura que "
        "este teste espera mudou; ajuste _no_do_timbre_do_escritorio antes "
        "de confiar no resto"
    )


def _cadeia_do_timbre_do_escritorio():
    """Cadeia raiz→nó do timbre do escritório no documento RENDERIZADO
    real: as ancestrais de `<main id="conteudo">` em `base.html` (onde
    `{% block content %}` injeta o conteúdo de `balancete.html`, incluindo
    o próprio `<main>`) seguidas das ancestrais LOCAIS do
    `.timbre-impressao` dentro do `balancete.html` isolado (hoje só ele
    mesmo — é filho direto do bloco de conteúdo, sem nenhum contêiner
    envolvendo-o antes do `<main>`)."""
    no_conteudo = _no_do_conteudo_principal()
    ancestrais_do_conteudo = _cadeia_de_ancestrais(no_conteudo)

    no_timbre = _no_do_timbre_do_escritorio()
    ancestrais_locais_do_timbre = _cadeia_de_ancestrais(no_timbre)

    return ancestrais_do_conteudo + ancestrais_locais_do_timbre, no_timbre


# ---------------------------------------------------------------------------
# Guarda central — propriedade SIMÉTRICA à do BL-329.
# ---------------------------------------------------------------------------


def test_timbre_do_escritorio_continua_visivel_sob_impressao():
    """A metade do critério 9 que faltava: nenhum nó da cadeia do timbre
    do escritório (do próprio `.timbre-impressao` até `<html>`) pode ter
    `display: none` EFETIVO sob impressão — senão o papel sai sem
    identificação nenhuma, nem do fornecedor (já coberto pelo BL-329) nem
    do escritório."""
    cadeia, no_timbre = _cadeia_do_timbre_do_escritorio()
    escondido, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert not escondido, (
        f"o elemento que carrega Escritorio.linhas_do_timbre "
        f"(cadeia: {[(n.tag, n.classes) for n in cadeia]}) tem display:none "
        f"EFETIVO sob impressão, resolvido em "
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
    cadeia, _ = _cadeia_do_timbre_do_escritorio()
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
    cadeia, _ = _cadeia_do_timbre_do_escritorio()
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
