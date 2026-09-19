"""BL-338 (achado B2 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): sob impressão, o papel
começava por "USUÁRIO <quem operou a tela>" — ANTES até do timbre do
escritório (BL-282/BL-331) — com o nome do escritório aparecendo DE NOVO
logo depois (a faixa de contexto de tela, "Escritório ativo", e o timbre,
que também traz o nome do escritório). Texto medido pelo auditor, sob
mídia de impressão:

    ['USUÁRIO', 'medicao', 'ESCRITÓRIO ATIVO', '<escritório>', 'EMPRESA',
     '<empresa>', 'PERÍODO', '01/03/2026 a 31/03/2026', '<escritório>',
     'Balancete de verificação', ...]

DECISÃO (Fred, 2026-09-19, RC-97), com fundamento NORMATIVO, não estético:
o documento impresso identifica o ESCRITÓRIO e o PROFISSIONAL responsável,
não o usuário que operou a tela — NBC ITG 2000, item 12: "a escrituração
contábil e a emissão de relatórios [...] são de atribuição e de
responsabilidade EXCLUSIVAS do profissional da contabilidade legalmente
habilitado". Quem operou a tela é trilha de auditoria (`apps/auditoria/`),
não identificação do documento. O comentário completo da correção está em
templates/base.html, sobre o item "Usuário" e "Escritório ativo" da faixa
`.cabecalho__contexto` (classe `contexto-item--somente-tela`, oculta sob
impressão em static/css/base.css).

O QUE ESTE ARQUIVO VERIFICA, com o MESMO motor de cascata CSS do BL-329
(`_algum_ancestral_removido_do_papel` e companhia, importados de
test_bl329_marca_fora_do_papel.py — nunca reescritos aqui: duas cópias do
mesmo motor divergem assim que uma for corrigida sem a outra, a lição do
BL-333 aplicada por composição):

1. O item "Usuário" (nome de quem operou a tela) tem `display` efetivo
   `none` sob impressão — CONTROLE POSITIVO da correção.
2. O item "Escritório ativo" (a faixa de CONTEXTO DE TELA, não o timbre)
   também tem `display` efetivo `none` sob impressão — fecha a metade do
   achado B2 sobre a DUPLICIDADE: o escritório passa a aparecer uma única
   vez no papel, só no timbre (BL-282/BL-331).
3. CONTROLE NEGATIVO, exigido pelo próprio pedido desta etapa: "Empresa" e
   "Período" (`{% block contexto_extra %}`, preenchido por
   balancete.html/diario.html/razao.html) — identificação OBRIGATÓRIA do
   documento (RC-93) — NÃO têm `display: none` efetivo sob impressão. Uma
   correção apressada que escondesse `.contexto-item` inteiro (em vez de
   só os DOIS itens de tela) apagaria Empresa e Período do papel junto —
   e é exatamente essa forma de erro que a sabotagem 2, abaixo, prova que
   este arquivo pega.

**Cadeia derivada, não retypada** — mesma técnica de
test_bl331_timbre_do_escritorio_no_papel.py: "Usuário" e "Escritório
ativo" vivem inteiramente em `templates/base.html` (não precisam de
combinação entre arquivos); "Empresa"/"Período" vivem em
`templates/contabilidade/<tela>.html`, injetados em `{% block
contexto_extra %}` dentro de `.cabecalho__contexto` — a cadeia real
combina as ancestrais de `.cabecalho__contexto` (base.html) com as
ancestrais LOCAIS do item dentro da tela.

Os nós são localizados pelo RÓTULO em texto ("Usuário", "Escritório
ativo", "Empresa", "Período") — o mesmo texto que a PESSOA lê na tela —
não pela classe CSS que ESTA correção introduziu
(`contexto-item--somente-tela`): amarrar a busca à própria classe que a
correção criou provaria a correção contra si mesma, não contra o
REQUISITO (que é sobre o que aparece no papel, não sobre o nome interno
da classe).

⚠️ Nunca escreva a palavra "title" (nem outra) entre sinais de menor/maior
nos textos deste módulo ou nos templates que ele lê — ver a docstring de
BL-332 em templates/base.html: o parser tolerante a HTML usado aqui trata
"title"/"textarea" como conteúdo RCDATA de verdade (Python stdlib) e
engole, em silêncio, todo o resto do arquivo sem fechamento correspondente.

O QUE ESTE ARQUIVO NÃO VERIFICA — mesmo limite de
test_bl329_marca_fora_do_papel.py/test_bl331_timbre_do_escritorio_no_papel.
py: se o CONTADOR vê isso de verdade no papel (motor de layout real,
Chromium) é responsabilidade de ferramenta de bancada
(scripts/medir_impressao.py); este arquivo simula a cascata CSS em
memória/`tmp_path`, sem banco de dados.
"""

import pytest

from apps.contabilidade.tests.test_bl329_marca_fora_do_papel import (
    _BASE_CSS,
    _BASE_HTML,
    _RAIZ,
    _algum_ancestral_removido_do_papel,
    _cadeia_de_ancestrais,
    _ConstrutorDeArvore,
    _escrever_css_mutado,
    _percorrer,
)

_BALANCETE_HTML = _RAIZ / "templates" / "contabilidade" / "balancete.html"
_DIARIO_HTML = _RAIZ / "templates" / "contabilidade" / "diario.html"
_RAZAO_HTML = _RAIZ / "templates" / "contabilidade" / "razao.html"

_TELAS_COM_CONTEXTO_EXTRA = {
    "balancete": _BALANCETE_HTML,
    "diario": _DIARIO_HTML,
    "razao": _RAZAO_HTML,
}


def _arvore_de(caminho):
    construtor = _ConstrutorDeArvore()
    construtor.feed(caminho.read_text(encoding="utf-8"))
    return construtor.raiz


def _no_por_rotulo(raiz, texto_rotulo):
    """Localiza `<span class="contexto-rotulo">` cujo texto PRÓPRIO é
    EXATAMENTE `texto_rotulo` e devolve o PAI dele (o `<span
    class="contexto-item...">` que carrega o valor) — a mesma estrutura
    de `.contexto-item`/`.contexto-rotulo` usada em toda a faixa de
    contexto (base.html e os três `contexto_extra`)."""
    for no in _percorrer(raiz):
        if (
            no.tag == "span"
            and "contexto-rotulo" in no.classes
            and no.texto_proprio.strip() == texto_rotulo
        ):
            assert no.pai is not None, f"controle: rótulo {texto_rotulo!r} sem pai"
            return no.pai
    raise AssertionError(
        f'controle: não achei <span class="contexto-rotulo"> com o texto '
        f"{texto_rotulo!r} — a estrutura que este teste espera mudou"
    )


def _no_do_cabecalho_contexto():
    """Localiza `<div class="cabecalho__contexto">` em `templates/base.html`
    — o contêiner onde `{% block contexto_extra %}` é injetado, e onde os
    itens "Usuário"/"Escritório ativo" já vivem diretamente."""
    for no in _percorrer(_arvore_de(_BASE_HTML)):
        if "cabecalho__contexto" in no.classes:
            return no
    raise AssertionError(
        'controle: não achei <div class="cabecalho__contexto"> em '
        "templates/base.html — a estrutura que este teste espera mudou"
    )


def _cadeia_em_base_html(texto_rotulo):
    """Cadeia raiz→nó para um item que vive inteiramente em
    `templates/base.html` (Usuário, Escritório ativo) — sem precisar
    combinar árvores de dois arquivos."""
    raiz = _arvore_de(_BASE_HTML)
    no = _no_por_rotulo(raiz, texto_rotulo)
    return _cadeia_de_ancestrais(no), no


def _cadeia_no_contexto_extra(caminho_template, texto_rotulo):
    """Cadeia raiz→nó combinando as ancestrais de `.cabecalho__contexto`
    (base.html, onde `{% block contexto_extra %}` é injetado) com as
    ancestrais LOCAIS do item dentro da tela — mesma técnica de
    `_cadeia_do_timbre_do_escritorio` em
    test_bl331_timbre_do_escritorio_no_papel.py."""
    no_contexto = _no_do_cabecalho_contexto()
    ancestrais_do_contexto = _cadeia_de_ancestrais(no_contexto)

    no_item = _no_por_rotulo(_arvore_de(caminho_template), texto_rotulo)
    ancestrais_locais = _cadeia_de_ancestrais(no_item)

    return ancestrais_do_contexto + ancestrais_locais, no_item


# ---------------------------------------------------------------------------
# Guarda central.
# ---------------------------------------------------------------------------


def test_item_usuario_tem_display_none_efetivo_na_impressao():
    """CONTROLE POSITIVO do achado B2: o nome de quem operou a tela não sai
    mais no papel."""
    cadeia, no = _cadeia_em_base_html("Usuário")
    escondido, _ = _algum_ancestral_removido_do_papel(cadeia, _BASE_CSS.read_text(encoding="utf-8"))
    assert escondido, (
        f"o item 'Usuário' (cadeia: {[(n.tag, n.classes) for n in cadeia]}) NÃO tem "
        f"display:none efetivo sob impressão — o nome de quem operou a tela ainda "
        f"sai no papel"
    )
    assert no is not None


def test_item_escritorio_ativo_da_faixa_de_tela_tem_display_none_efetivo_na_impressao():
    """Fecha a metade do achado B2 sobre DUPLICIDADE: o "Escritório ativo"
    da faixa de CONTEXTO DE TELA some do papel — o escritório continua
    identificado, mas só uma vez, no timbre (BL-282/BL-331)."""
    cadeia, no = _cadeia_em_base_html("Escritório ativo")
    escondido, _ = _algum_ancestral_removido_do_papel(cadeia, _BASE_CSS.read_text(encoding="utf-8"))
    assert escondido, (
        f"o item 'Escritório ativo' (cadeia: {[(n.tag, n.classes) for n in cadeia]}) NÃO "
        f"tem display:none efetivo sob impressão — o escritório continua saindo "
        f"DUAS vezes no papel"
    )
    assert no is not None


@pytest.mark.parametrize("tela", sorted(_TELAS_COM_CONTEXTO_EXTRA))
@pytest.mark.parametrize("rotulo", ["Empresa", "Período"])
def test_empresa_e_periodo_continuam_visiveis_sob_impressao(tela, rotulo):
    """CONTROLE NEGATIVO exigido pelo pedido desta etapa: a correção do
    achado B2 não pode apagar a identificação OBRIGATÓRIA do documento
    (RC-93) — Empresa e Período continuam sem `display: none` efetivo sob
    impressão, nas três telas que preenchem `{% block contexto_extra %}`."""
    caminho = _TELAS_COM_CONTEXTO_EXTRA[tela]
    cadeia, no = _cadeia_no_contexto_extra(caminho, rotulo)
    escondido, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert not escondido, (
        f"o item {rotulo!r} de {tela} (cadeia: {[(n.tag, n.classes) for n in cadeia]}) TEM "
        f"display:none efetivo sob impressão, resolvido em "
        f"{(no_que_esconde.tag, no_que_esconde.classes) if no_que_esconde else None} — "
        f"identificação OBRIGATÓRIA (RC-93) sumiu do papel"
    )
    assert no is not None


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA dentro de `tmp_path`,
# nunca no arquivo real). Controle POSITIVO (sabotagem 1: reverter a
# correção faz o operador voltar) e NEGATIVO (sabotagem 2: uma correção
# larga demais que apaga Empresa/Período junto tem que ser pega pelo teste
# de controle negativo acima).
# ---------------------------------------------------------------------------


def test_sabotagem_remover_a_regra_que_esconde_o_operador_mata_a_guarda(tmp_path):
    """Sabotagem 1 — CONTROLE POSITIVO: remove, de uma CÓPIA de
    `static/css/base.css`, a regra `.contexto-item--somente-tela { display:
    none; }` inteira — reproduz o estado ANTES desta correção, em que
    "Usuário" (e "Escritório ativo") continuavam saindo no papel. A guarda
    do item "Usuário" PRECISA morrer (deixar de reportar `escondido`)."""
    cadeia, _ = _cadeia_em_base_html("Usuário")
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    escondido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert escondido_antes, "controle: o CSS real precisa passar ANTES da sabotagem"

    alvo = "    .contexto-item--somente-tela {\n        display: none;\n    }"
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, "")
    escondido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois is False, (
        "remover a regra que esconde 'Usuário' na impressão deveria ter feito a guarda "
        "MORRER, e ela continuou aprovando"
    )


def test_sabotagem_esconder_todo_contexto_item_mata_a_guarda_de_empresa_e_periodo(tmp_path):
    """Sabotagem 2 — CONTROLE NEGATIVO: troca o seletor
    `.contexto-item--somente-tela` por `.contexto-item` (uma correção
    LARGA DEMAIS, plausível se alguém "simplificar" a regra sem notar que
    ela passa a casar com TODOS os itens da faixa) — Empresa e Período
    passam a ter `display: none` efetivo também, e a guarda de controle
    negativo (`test_empresa_e_periodo_continuam_visiveis_sob_impressao`)
    PRECISA morrer (reportar `escondido`, o que ela recusa por padrão)."""
    caminho_balancete = _TELAS_COM_CONTEXTO_EXTRA["balancete"]
    cadeia, _ = _cadeia_no_contexto_extra(caminho_balancete, "Empresa")
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    escondido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert escondido_antes is False, "controle: Empresa precisa estar VISÍVEL antes da sabotagem"

    alvo = "    .contexto-item--somente-tela {\n        display: none;\n    }"
    substituto = "    .contexto-item {\n        display: none;\n    }"
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    escondido_depois, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois, (
        "a sabotagem que amplia o seletor para TODO '.contexto-item' deveria ter feito "
        "a guarda de Empresa/Período MORRER (Empresa escondida junto com Usuário), e ela "
        "continuou aprovando"
    )
    assert no_que_esconde is not None
