"""BL-329 (achado do arquiteto-senior sobre o BL-282, docs/projeto/backlog.md):
guarda que morre quando a marca do FORNECEDOR ("DataLedger.") volta a sair no
papel — o defeito original do BL-282, que os dez testes de
`test_bl282_timbre_de_impressao.py` não cobrem.

POR QUE OS TESTES DO BL-282 NÃO COBREM ISTO — a causa exata que este arquivo
existe para fechar: aqueles dez testes afirmam sobre o **HTML renderizado**
(o bloco `.timbre-impressao` existe, tem as linhas certas, na ordem certa, e
não contém "DataLedger"). Mas a marca do fornecedor **também** está no HTML
de toda página (vem de `templates/base.html`, sempre) — o que decide se ela
sai no PAPEL é o **CSS de impressão** (`@media print` em
`static/css/base.css`), e nenhum teste do BL-282 pergunta isso.

O QUE ESTE ARQUIVO VERIFICA (roda no `pytest`, portanto na integração
contínua — primeira metade da garantia):

Deriva a cadeia de ancestrais do elemento que carrega o NOME DO PRODUTO —
lido de `templates/base.html`, nunca retypado como literal Python neste
arquivo (lição do BL-296: uma cópia do texto diverge do original assim que
alguém o renomeia) — e exige que ELE, ou algum ancestral seu, tenha
`display: none` **efetivo** sob impressão: não "o seletor aparece dentro do
bloco `@media print`" (guarda de LISTA, que o arquiteto pediu para eu não
escrever), e sim o resultado de simular a CASCATA CSS real (especificidade +
ordem de declaração, entre TODAS as regras do arquivo que se aplicariam
durante a impressão — as de fora de `@media print`, que valem sempre, e as
de dentro, que só valem ao imprimir) para a propriedade `display` de cada nó
da cadeia. É a mesma distinção que `MOMENTO_DA_VERDADE_SELETORES` faz em
`docs/assets/design/gauntlet/juiz.py`: nomear O QUE checar (um elemento da
tela), não enumerar COMO alguém poderia escondê-lo.

Um motor de cascata CSS genérico de verdade é responsabilidade de um motor de
layout — não deste arquivo. O que existe abaixo (`_ConstrutorDeArvore`,
`_extrair_regras_flat`, `_especificidade`, `_seletor_casa_com_no`, etc.) é
uma SIMULAÇÃO DELIBERADAMENTE LIMITADA À FORMA REAL deste projeto: um nível
de `@media print` (sem aninhamento), seletores compostos por tipo e classe
combinados só por combinador descendente (espaço) — a única forma usada em
`static/css/base.css` — e nenhum suporte a `id`, atributo, pseudo-elemento
ou `>`/`+`/`~`. Os limites estão testados por CONSTRUÇÃO (as sabotagens
abaixo cobrem exatamente as formas de escape que o arquiteto listou), não
por auditoria posterior.

DECISÃO MINHA, que o arquiteto deveria revisar: a guarda exige
especificamente `display: none` — NÃO aceita `visibility: hidden` como
equivalente, mesmo que `visibility: hidden` também impeça a tinta de sair no
papel (nenhum leitor humano veria "DataLedger." impresso de qualquer jeito).
Escolhi `display: none` porque (a) é o padrão que este arquivo já usa,
consistentemente, para TODOS os outros elementos da mesma lista de ocultos
(navegação, botões, atalho de teclado); e (b) `visibility: hidden` NÃO tira o
elemento do fluxo — o papel ganharia um bloco em branco no lugar da marca,
um defeito de densidade que a direção de arte trata como problema também
(§4.8: "filtro não come a tela" é o mesmo princípio aplicado à tela; um bloco
em branco não come a tela, mas come o PAPEL). A sabotagem C, abaixo, prova
que a guarda morre nesse caso — é uma escolha DELIBERADAMENTE mais estrita
que "a marca não é visível", e o arquiteto pode preferir a leitura mais
frouxa.

O QUE ESTE ARQUIVO NÃO VERIFICA — a segunda metade, que só um motor de
layout real decide, e que a integração contínua deste projeto NÃO RODA
(§4.8 da direção de arte: sem Chromium na CI):

- Se o CONTADOR **vê** a marca no papel de verdade. `display: none`
  calculado por este arquivo é a MESMA pergunta que o CSS real responde,
  mas por uma simulação escrita por mim, não pelo motor de layout do
  navegador — sempre existe a chance de uma forma de esconder/reexibir um
  elemento que meu motor simplificado não modela corretamente (herança de
  `display` em `contents`, `@supports`, `:is()`/`:where()`, seletores com
  `id`, etc. — nenhum usado hoje em `static/css/base.css`, mas se alguém
  usar, este arquivo pode julgar errado).
- Isto é medido por fora, com Chromium de verdade e
  `page.emulate_media(media="print")` — ver
  `docs/assets/design/gauntlet/juiz.py`, `SELETOR_MARCA_DO_FORNECEDOR` e
  `SONDA_IMPRESSAO` (extensão desta etapa, BL-329, ao mesmo mecanismo que já
  existia para `MOMENTO_DA_VERDADE_SELETORES` — ver o comentário lá). É
  ferramenta de BANCADA (não roda no `pytest`), com a mesma obrigação que o
  BL-314 já registrou: quem fecha uma etapa que mexa neste CSS roda o juiz
  manualmente antes de declarar pronto.

Dados: nenhum. Este arquivo não usa banco de dados (não há
`pytest.mark.django_db`) — ele só lê `templates/base.html` e
`static/css/base.css`, e simula CSS/HTML em memória ou em cópias dentro de
`tmp_path` (BL-311: nunca no arquivo real).
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]
_BASE_HTML = _RAIZ / "templates" / "base.html"
_BASE_CSS = _RAIZ / "static" / "css" / "base.css"

_ELEMENTOS_VAZIOS = {
    "meta",
    "link",
    "input",
    "img",
    "br",
    "hr",
    "area",
    "base",
    "col",
    "embed",
    "source",
    "track",
    "wbr",
}


# ---------------------------------------------------------------------------
# Árvore mínima de `templates/base.html`: só o suficiente para achar o link
# que carrega o nome do produto e subir pelos ancestrais dele. Tags Django
# (`{% %}`/`{{ }}`) não começam com `<`, então `html.parser.HTMLParser` as
# trata como texto inerte — não como marcação — e não precisa de nenhum
# tratamento especial aqui.
# ---------------------------------------------------------------------------


@dataclass
class _No:
    tag: str
    classes: tuple
    filhos: list = field(default_factory=list, repr=False)
    pai: object = field(default=None, repr=False)
    texto_proprio: str = ""


class _ConstrutorDeArvore(HTMLParser):
    """Constrói a árvore. Tolerante a HTML malformado (o `handle_endtag`
    desempilha até achar a tag correspondente em vez de exigir aninhamento
    perfeito) — necessário porque elementos vazios sem `/>` explícito
    (`<meta>`, `<link>`) não são reconhecidos como tal pelo parser padrão, e
    essa tolerância AUTOCORRIGE a pilha assim que a próxima tag de
    fechamento real aparece, sem exigir uma lista de "elementos vazios"
    exaustiva (a lista abaixo existe só para o caso comum, não é o que
    garante a correção)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = _No(tag="#raiz", classes=())
        self._pilha = [self.raiz]

    @staticmethod
    def _classes_de(attrs):
        for nome, valor in attrs:
            if nome == "class" and valor:
                return tuple(valor.split())
        return ()

    def handle_starttag(self, tag, attrs):
        no = _No(tag=tag, classes=self._classes_de(attrs), pai=self._pilha[-1])
        self._pilha[-1].filhos.append(no)
        if tag not in _ELEMENTOS_VAZIOS:
            self._pilha.append(no)

    def handle_startendtag(self, tag, attrs):
        no = _No(tag=tag, classes=self._classes_de(attrs), pai=self._pilha[-1])
        self._pilha[-1].filhos.append(no)

    def handle_endtag(self, tag):
        for i in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[i].tag == tag:
                del self._pilha[i:]
                break

    def handle_data(self, data):
        texto = data.strip()
        if texto:
            self._pilha[-1].texto_proprio += texto


def _percorrer(no):
    yield no
    for filho in no.filhos:
        yield from _percorrer(filho)


def _achar_no_da_marca(raiz):
    """Localiza o `<a>` filho direto do `<div class="marca">` — o link que
    carrega o NOME DO PRODUTO. Encontrado pela ESTRUTURA (classe `marca`,
    convenção já documentada em `static/css/base.css` e
    `templates/base.html` como "a marca do fornecedor"), não pelo TEXTO: o
    texto "DataLedger" nunca é escrito neste arquivo Python — é lido do nó
    encontrado, então se o produto for renomeado só em `templates/base.html`,
    este teste acompanha a mudança sem precisar ser editado."""
    for no in _percorrer(raiz):
        if "marca" in no.classes:
            for filho in no.filhos:
                if filho.tag == "a" and filho.texto_proprio:
                    return filho
    return None


def _cadeia_de_ancestrais(no):
    """Do próprio nó até a raiz do documento, na ordem raiz→nó — é o mesmo
    caminho que os seletores descendentes do CSS percorrem."""
    cadeia = []
    atual = no
    while atual is not None and atual.tag != "#raiz":
        cadeia.append(atual)
        atual = atual.pai
    cadeia.reverse()
    return cadeia


def _cadeia_da_marca():
    html_bruto = _BASE_HTML.read_text(encoding="utf-8")
    construtor = _ConstrutorDeArvore()
    construtor.feed(html_bruto)
    no_marca = _achar_no_da_marca(construtor.raiz)
    assert no_marca is not None, (
        "controle: não achei, em templates/base.html, nenhum <a> dentro de um "
        "elemento de classe 'marca' — a estrutura que este teste espera "
        "mudou; ajuste _achar_no_da_marca antes de confiar no resto"
    )
    assert no_marca.texto_proprio, "controle: o link da marca não tem texto"
    return no_marca, _cadeia_de_ancestrais(no_marca)


# ---------------------------------------------------------------------------
# Motor de cascata CSS mínimo — só a propriedade `display`, só a forma real
# de `static/css/base.css` (ver limites na docstring do módulo).
# ---------------------------------------------------------------------------

_PROPRIEDADES_DE_INTERESSE = ("display",)


@dataclass
class _Declaracao:
    valor: str
    importante: bool


@dataclass
class _Regra:
    compostos: list
    ordem: int
    declaracoes: dict


def _remover_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _extrair_bloco_media_print(css):
    """Devolve (antes, dentro, depois) do ÚNICO `@media print { ... }` do
    arquivo — contagem de chaves, não regex gulosa, porque o conteúdo tem
    chaves aninhadas (cada regra de seletor, dentro do media). `antes` e
    `depois` não têm chave aninhada nenhuma (todo o resto do arquivo é
    `seletor { declarações }` de nível único, incluindo `@font-face`/`@page`,
    que `_extrair_regras_flat` descarta por começarem com `@`)."""
    css = _remover_comentarios(css)
    marcador = re.search(r"@media\s+print\s*\{", css)
    assert marcador, "controle: @media print não encontrado em base.css"
    inicio_chaves = marcador.end() - 1
    profundidade = 0
    fim = None
    for i in range(inicio_chaves, len(css)):
        if css[i] == "{":
            profundidade += 1
        elif css[i] == "}":
            profundidade -= 1
            if profundidade == 0:
                fim = i
                break
    assert fim is not None, "controle: fechamento do @media print não encontrado"
    return css[: marcador.start()], css[inicio_chaves + 1 : fim], css[fim + 1 :]


def _extrair_regras_flat(texto, offset):
    """`texto` sem chave aninhada. `offset` é a posição absoluta no arquivo
    original — preserva a ORDEM verdadeira de declaração, que a cascata CSS
    usa para desempatar especificidade igual. Só guarda regras que declarem
    `display` — o resto não importa para esta guarda."""
    regras = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", texto):
        seletor_bruto = m.group(1).strip()
        if seletor_bruto.startswith("@"):
            continue
        declaracoes = {}
        for decl in m.group(2).split(";"):
            decl = decl.strip()
            if not decl or ":" not in decl:
                continue
            prop, _, valor = decl.partition(":")
            prop = prop.strip().lower()
            if prop not in _PROPRIEDADES_DE_INTERESSE:
                continue
            valor = valor.strip()
            importante = valor.lower().endswith("!important")
            if importante:
                valor = valor[: valor.lower().rindex("!important")].strip()
            declaracoes[prop] = _Declaracao(valor=valor.lower(), importante=importante)
        if not declaracoes:
            continue
        for seletor in seletor_bruto.split(","):
            compostos = [c for c in seletor.split() if c]
            if not compostos:
                continue
            regras.append(
                _Regra(compostos=compostos, ordem=offset + m.start(), declaracoes=declaracoes)
            )
    return regras


def _especificidade(composto):
    """(classes+pseudo-classes, tipo) — sem `id` (nenhum usado nos seletores
    relevantes deste arquivo). Pseudo-classes contam como classe (regra da
    especificação); pseudo-elementos/atributos não são suportados."""
    sem_pseudo = composto.split(":")[0]
    n_classes = len(re.findall(r"\.[\w-]+", sem_pseudo))
    n_pseudo = composto.count(":")
    tem_tipo = bool(re.match(r"^[a-zA-Z][\w-]*", sem_pseudo))
    return (n_classes + n_pseudo, 1 if tem_tipo else 0)


def _especificidade_seletor(compostos):
    total = (0, 0)
    for c in compostos:
        e = _especificidade(c)
        total = (total[0] + e[0], total[1] + e[1])
    return total


def _composto_casa_com_no(composto, no):
    composto = composto.split(":")[0]
    tag_m = re.match(r"^[a-zA-Z][\w-]*", composto)
    if tag_m and no.tag != tag_m.group():
        return False
    classes_exigidas = re.findall(r"\.([\w-]+)", composto)
    return all(c in no.classes for c in classes_exigidas)


def _seletor_casa_com_no(compostos, indice_no, cadeia):
    """Combinador DESCENDENTE (espaço) — o único usado neste arquivo. O
    composto mais à direita precisa casar com o próprio nó; cada composto
    anterior precisa casar com ALGUM ancestral (não necessariamente o pai
    direto) mais acima na cadeia — a mesma regra do combinador `' '` do
    CSS."""
    if not _composto_casa_com_no(compostos[-1], cadeia[indice_no]):
        return False
    if len(compostos) == 1:
        return True
    for j in range(indice_no - 1, -1, -1):
        if _seletor_casa_com_no(compostos[:-1], j, cadeia):
            return True
    return False


def _display_efetivo(indice_no, cadeia, regras):
    """Vencedor da cascata para `display` no nó `cadeia[indice_no]`: entre
    as regras cujo seletor casa com ele, `!important` vence sobre normal;
    dentro do mesmo grupo, maior especificidade vence; empate, a de MAIOR
    ordem (mais tardia no arquivo) vence — a regra padrão do CSS."""
    candidatas = []
    for regra in regras:
        if _seletor_casa_com_no(regra.compostos, indice_no, cadeia):
            decl = regra.declaracoes.get("display")
            if decl:
                candidatas.append((regra, decl, _especificidade_seletor(regra.compostos)))
    if not candidatas:
        return None
    importantes = [c for c in candidatas if c[1].importante]
    grupo = importantes or candidatas
    grupo.sort(key=lambda c: (c[2], c[0].ordem))
    return grupo[-1][1].valor


def _algum_ancestral_removido_do_papel(cadeia, css_texto):
    """Propriedade central desta guarda: existe, na cadeia (do link da marca
    até a raiz), algum nó cujo `display` efetivo sob impressão é `none`?
    Devolve (removido: bool, nó_que_resolveu_ou_None)."""
    antes, dentro, depois = _extrair_bloco_media_print(css_texto)
    regras = (
        _extrair_regras_flat(antes, 0)
        + _extrair_regras_flat(dentro, len(antes))
        + _extrair_regras_flat(depois, len(antes) + len(dentro))
    )
    for i in range(len(cadeia)):
        if _display_efetivo(i, cadeia, regras) == "none":
            return True, cadeia[i]
    return False, None


# ---------------------------------------------------------------------------
# Guarda central.
# ---------------------------------------------------------------------------


def test_algum_ancestral_da_marca_tem_display_none_efetivo_na_impressao():
    """A guarda que o arquiteto pediu: morre quando a marca do fornecedor
    volta ao papel, por QUALQUER seletor/regra que produza esse efeito — não
    só pela lista de hoje. Ver as provas por mutação abaixo."""
    no_marca, cadeia = _cadeia_da_marca()
    removido, no_vencedor = _algum_ancestral_removido_do_papel(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert removido, (
        f"nenhum ancestral do link '{no_marca.texto_proprio}' "
        f"(cadeia: {[(n.tag, n.classes) for n in cadeia]}) tem display:none "
        f"EFETIVO sob impressão — a marca do fornecedor volta a sair no papel"
    )
    assert no_vencedor is not None


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA dentro de `tmp_path`,
# nunca no arquivo real). As três sabotagens abaixo cobrem: (1) a sabotagem
# EXATA que o arquiteto-senior reproduziu contra o BL-282 — remover o
# seletor da lista de ocultos; (2) uma das quatro saídas que ele listou como
# capazes de defeituar uma guarda de LISTA — regra mais específica, depois,
# reexibindo o elemento; (3) outra das quatro — `display: none` trocado por
# `visibility: hidden` (não tira do fluxo). As outras duas saídas da lista
# do arquiteto (envolver a marca em outro contêiner; renderizar por outro
# template) mexem em `templates/base.html`, não em `static/css/base.css` —
# ver o relatório da etapa para por que este arquivo não testa as duas: a
# cadeia é sempre RE-DERIVADA de `templates/base.html` a cada execução
# (`_cadeia_da_marca`, acima), então essas duas formas de sabotagem já
# seriam refletidas na cadeia ANTES de chegar à checagem de CSS — é
# raciocínio, não medição, e está declarado como tal no relatório.
# ---------------------------------------------------------------------------


def _escrever_css_mutado(tmp_path, css_original, alvo, substituto, *, nome="base-mutado.css"):
    mutado, n = re.subn(re.escape(alvo), substituto, css_original, count=1)
    assert n == 1, f"controle: a sabotagem não achou o texto esperado em base.css: {alvo!r}"
    assert mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho = tmp_path / nome
    caminho.write_text(mutado, encoding="utf-8")
    return caminho


def test_sabotagem_mandatoria_remover_cabecalho_topo_da_lista_de_ocultos_mata_a_guarda(tmp_path):
    """Reproduz a sabotagem exata que o arquiteto-senior fez para provar o
    defeito do BL-329: remove a linha `.cabecalho__topo,` da lista de
    seletores ocultos dentro de `@media print` — restaura literalmente o
    defeito original do BL-282 (marca do fornecedor volta a sair no papel)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    removido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert removido_antes, "controle: o CSS real precisa passar ANTES da sabotagem"

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .pular-para-conteudo,\n    .cabecalho__topo,\n    .navegacao-empresa,\n",
        "    .pular-para-conteudo,\n    .navegacao-empresa,\n",
    )
    removido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert removido_depois is False, (
        "a sabotagem mandatória deveria ter feito a guarda MORRER (nenhum "
        "ancestral com display:none efetivo), e ela continuou aprovando"
    )


def test_sabotagem_regra_mais_especifica_depois_reexibindo_mata_a_guarda(tmp_path):
    """Saída nº 2 da lista do arquiteto: alguém acrescenta, DEPOIS do bloco
    de ocultos, uma regra mais específica que reexibe o elemento —
    `header.cabecalho .cabecalho__topo { display: flex; }` tem
    especificidade (2 classes/tipo somados, 1 tipo) contra (1, 0) do
    seletor `.cabecalho__topo` sozinho na lista de ocultos: vence mesmo sem
    `!important`. Uma guarda que só checasse "o seletor `.cabecalho__topo`
    está na lista de ocultos" não veria nada de errado aqui — o seletor
    continua lá; só deixou de ser o VENCEDOR da cascata."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = _escrever_css_mutado(
        tmp_path,
        css_original,
        "    .timbre-impressao {\n        display: block;",
        "    header.cabecalho .cabecalho__topo {\n        display: flex;\n    }\n\n"
        "    .timbre-impressao {\n        display: block;",
    )
    removido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert removido_depois is False, (
        "a sabotagem de especificidade deveria ter feito a guarda MORRER, e ela continuou aprovando"
    )


def test_sabotagem_visibility_hidden_no_lugar_de_display_none_mata_a_guarda(tmp_path):
    """Saída nº 4 da lista do arquiteto: o seletor continua na lista, mas a
    declaração muda de `display: none` para `visibility: hidden` — que NÃO
    tira o elemento do fluxo (o papel ganharia um bloco em branco no lugar
    da marca, em vez do timbre do escritório ocupar aquele espaço). Uma
    guarda que procurasse só a STRING `.cabecalho__topo` dentro do bloco
    `@media print` não veria nada de errado — o seletor está lá. Esta guarda
    vê, porque exige `display: none` especificamente (decisão registrada na
    docstring do módulo)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    alvo = (
        "    .pular-para-conteudo,\n    .cabecalho__topo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    substituto = alvo.replace("display: none;", "visibility: hidden;")
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    removido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert removido_depois is False, (
        "a sabotagem visibility:hidden deveria ter feito a guarda MORRER, e ela continuou aprovando"
    )
