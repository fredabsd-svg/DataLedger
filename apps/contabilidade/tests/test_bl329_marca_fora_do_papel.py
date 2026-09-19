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

BL-333 (M1 da auditoria DL-026, rodada 5, docs/auditorias/2026-09-19-dl-026-
rodada-5.md): o auditor mediu a simulação de cascata errando DENTRO do
limite que ela mesma declara, nas DUAS direções — falso "escondido" (uma
regra `:hover`/`@media screen`/`@supports` fazia a guarda achar que a marca
tinha sumido, quando na verdade ela continuava saindo no papel) e falso
"reprovado" (uma `@media (min-width: 80rem)` legítima, acrescentada DEPOIS
do `@media print` já correto, fazia a guarda reprovar código que não tinha
defeito nenhum). Duas decisões novas, e as duas são MINHAS, para o
arquiteto revisar:

1. **At-rule aninhada FORA do único `@media print` tratado** (outro
   `@media`, `@supports`, etc., com bloco de seletor DENTRO do seu próprio
   bloco — não confundir com `@page`/`@font-face`, que têm conteúdo FLAT e
   já eram descartados corretamente): se o PRELÚDIO dela não menciona
   "print", ela é REMOVIDA do texto antes da extração de regras — decisão
   deliberada de que um `@media screen`/`@supports (...)`/`@media
   (min-width: ...)` sem a palavra "print" NUNCA se aplica durante a
   impressão, então hospedar `display: none` ali dentro NUNCA prova
   ocultação, e hospedar `display` diferente de `none` ali dentro NUNCA
   ameaça a marca de verdade — pode ser IGNORADA com segurança. Se o
   prelúdio MENCIONA "print" (por exemplo, um segundo `@media print`
   solto no arquivo, ou `@media print and (...)`), a simulação NÃO sabe
   avaliar essa condição — em vez de adivinhar, o teste REPROVA pedindo
   extensão explícita (`assert` com mensagem própria), a mesma escolha
   de "reprovar pedindo extensão em vez de julgar errado em silêncio".
   At-rule aninhada DENTRO do próprio `@media print` (ex.: um `@supports`
   aninhado ali dentro) recebe o mesmo tratamento — a simulação também
   não sabe resolvê-la — mesmo que mencione "print" (dentro de um
   `@media print` já não faz sentido mencionar de novo, e a presença
   sozinha já é sinal de que o motor precisa crescer).

   ⚠️ **BL-343 (F1 da auditoria DL-026, rodada 6,
   docs/auditorias/2026-09-19-dl-026-rodada-6.md): esta decisão 1 estava
   ERRADA, e a rodada 6 a substitui pela de baixo.** "Sem a palavra
   'print' no prelúdio" NÃO é a mesma coisa que "nunca se aplica na
   impressão" — é FALSO: uma media query SEM tipo de mídia vale para
   `all` (que inclui `print`); `@supports` e `@layer` não falam de mídia
   NENHUMA e valem SEMPRE, em qualquer mídia. O auditor MEDIU, em
   Chromium e em PDF A4 reais, `@media (min-width: 20rem) { .cabecalho__
   topo { display: flex } }` devolvendo a marca do fornecedor ao papel, e
   `@supports (display: grid) { .timbre-impressao { display: none } }`
   apagando o timbre do escritório — as duas com `1775 passed`. Uma LISTA
   de uma palavra ("print") não deriva a propriedade "esta condição pode
   valer durante a impressão"; ela só parece derivá-la até alguém escrever
   a primeira at-rule cujo prelúdio não contém a palavra E cuja condição,
   mesmo assim, vale ao imprimir — que é a maioria das media queries
   responsivas do CSS real, o tipo de código mais banal que existe.

   **A correção (F1): inverter o lado seguro.** Toda at-rule aninhada
   (fora do `@media print` tratado, antes ou depois dele) REPROVA pedindo
   extensão, SEMPRE — com uma única EXCEÇÃO NOMEADA, e só ela:
   `@media screen`, puro (sem combinar com outro tipo de mídia por `,`/
   `and`). `screen` EXCLUI `print` por definição (CSS Media Queries:
   `screen` e `print` são tipos de mídia mutuamente exclusivos quando
   usados sozinhos) — hospedar QUALQUER `display` ali dentro nunca pode
   provar nem derrubar ocultação sob impressão, então pode ser removida
   com segurança, exatamente como antes. `@supports`, `@layer`,
   `@container`, `@scope` e qualquer media query SEM tipo de mídia (que
   vale para `all`) NÃO são irrelevantes — não têm mais o benefício da
   dúvida: reprovam pedindo extensão, mesmo sem mencionar "print", porque
   a simulação não sabe (e nunca soube) se elas se aplicam à impressão —
   o que mudou é só que agora ela ADMITE isso em vez de assumir que não.

   **Agravante, registrado pelo próprio auditor contra mim:**
   `test_media_query_responsiva_legitima_depois_do_media_print_nao_
   reprova`, o teste que prova o lado "aprova" desta decisão, usava até
   esta correção `@media (min-width: 80rem)` como exemplo de "código
   legítimo" — um exemplo que EU dei ao arquiteto-senior, na rodada 5. O
   auditor MEDIU que esse exemplo não é inofensivo: sob
   `emulate_media(media="print")` a 1280px, ele reexibe
   `.cabecalho__topo` mesmo imprimindo — só parecia inofensivo no PDF A4
   do `juiz.py` por COINCIDÊNCIA de largura de página (~49,6rem). O
   exemplo foi trocado por `@media screen`, o único caso realmente
   inofensivo, porque exclui impressão por definição, não por sorte de
   largura.
2. **Pseudo-classe condicional** (`:hover`, `:focus`, `:active`, etc. — o
   mesmo padrão que `_especificidade` já usa para "qualquer `:`", porque
   este motor não distingue pseudo-classes estruturais das de interação)
   não pode ser usada para SATISFAZER a propriedade: uma regra assim com
   `display: none` é DESCARTADA do grupo de candidatas, porque a
   interação do ponteiro nunca ocorre no papel — contar com ela seria
   assumir que o elemento está escondido quando, na falta de qualquer
   OUTRA regra, ele está visível o tempo todo. A mesma regra com
   `display` diferente de `none` continua valendo normalmente — pode
   REEXIBIR o elemento (o lado seguro: melhor a guarda reprovar demais
   por uma reexibição hipotética do que aprovar de menos por confiar
   numa ocultação que só ocorre com o mouse sobre o elemento, o que nunca
   é o caso ao imprimir).

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

import pytest

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


# BL-348 (F6 da auditoria DL-026, rodada 6,
# docs/auditorias/2026-09-19-dl-026-rodada-6.md): comentário de gabarito
# (`{% comment %}...{% endcomment %}`) NUNCA chega ao HTML entregue — o
# Django os descarta ao renderizar, e a varredura ESTÁTICA
# (apps/core/tests/test_dl024_varredura_de_interface.py:622) já os remove
# antes de varrer. Removidos AQUI, antes de alimentar o parser, em vez de
# deixar o parser tolerante lidar com o texto bruto: uma palavra entre
# "<" e ">" dentro de um desses blocos (nunca intenção de marcação) pode
# colidir com "title"/"textarea" — os dois nomes de
# `html.parser.HTMLParser.RCDATA_CONTENT_ELEMENTS` (stdlib) — e fazer o
# parser tratar TUDO que vem depois como conteúdo de RCDATA sem
# fechamento correspondente, descartando o resto do arquivo em silêncio.
# Medido pelo auditor: com a palavra ANTES do bloco do timbre, a árvore
# truncava sem nenhum teste reclamar (1775 passed).
_PADRAO_BLOCO_COMMENT_DE_GABARITO = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)


def _remover_comentarios_de_gabarito(texto):
    """Remove todo bloco `{% comment %}...{% endcomment %}` de `texto` —
    ver o comentário acima para o porquê. Aplicado tanto a TEXTO DE
    TEMPLATE (fonte em disco) quanto a HTML JÁ RENDERIZADO: no segundo
    caso é sempre uma operação NULA (o Django já removeu os comentários
    ao renderizar), então aplicar sempre, sem distinguir os dois casos
    no chamador, é seguro."""
    return _PADRAO_BLOCO_COMMENT_DE_GABARITO.sub("", texto)


def _parsear_html(texto):
    """Ponto ÚNICO de entrada para transformar `texto` (fonte de
    template OU HTML renderizado) em árvore: remove comentários de
    gabarito (`_remover_comentarios_de_gabarito`) e alimenta
    `_ConstrutorDeArvore`, com um CONTROLE DE NÃO-TRUNCAMENTO (BL-348/
    F6): se o `feed` terminar com o parser ainda DENTRO de um elemento
    RCDATA (`cdata_elem` não-`None` — `title`/`textarea` sem fechamento
    correspondente ENCONTRADO, não sem fechamento nenhum: o atributo só
    fica não-`None` quando o parser NUNCA achou a tag de fechamento até o
    fim do texto), o parse foi truncado e tudo que vem depois do ponto de
    truncamento foi descartado em silêncio — reprova nomeando O TEMPLATE
    como a causa provável, não pedindo para mexer neste arquivo."""
    construtor = _ConstrutorDeArvore()
    construtor.feed(_remover_comentarios_de_gabarito(texto))
    assert construtor.cdata_elem is None, (
        f"o parse deste template TRUNCOU dentro de <{construtor.cdata_elem}> sem "
        f"fechamento correspondente encontrado — isto quase sempre significa uma "
        f"palavra entre '<' e '>' no TEMPLATE fonte, fora de um bloco "
        f"{{% comment %}}/{{% endcomment %}} bem formado (que já é removido antes "
        f"do parse), colidindo com 'title' ou 'textarea'. CONFIRA O TEMPLATE — "
        f"tudo que vem depois do ponto de truncamento foi descartado da árvore em "
        f"silêncio, e os testes deste arquivo não podem ver o que não está na árvore"
    )
    return construtor.raiz


def _tem_timbre_impressao(raiz):
    """Verdadeiro se ALGUM nó da árvore `raiz` (já parseada) tiver a
    classe `timbre-impressao` — presença ESTRUTURAL no HTML, nunca uma
    lista de nomes de tela escrita à mão. Responde "esta página é um
    DOCUMENTO?" (BL-282: só telas com timbre de impressão são documentos
    que saem do escritório para o cliente) — a MESMA pergunta que
    test_bl332_titulo_sem_marca_do_fornecedor.py (BL-344/F2) e
    test_bl338_operador_fora_do_papel.py (BL-338) precisam responder,
    cada um sobre uma consequência diferente da mesma propriedade;
    compartilhada AQUI, no módulo-base que os dois já importam, em vez de
    duplicada nos dois — a lição do BL-296/BL-325 (uma cópia diverge do
    original assim que ele mudar), aplicada pelo auditor a este par de
    guardas (F2)."""
    return any("timbre-impressao" in no.classes for no in _percorrer(raiz))


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
    raiz = _parsear_html(html_bruto)
    no_marca = _achar_no_da_marca(raiz)
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
    `depois` PODEM ter at-rule aninhada de verdade (outro `@media`,
    `@supports`) — ver `_spans_de_at_rule_com_bloco_aninhado` e o uso dela em
    `_algum_ancestral_removido_do_papel`, que valida essa premissa em vez de
    presumi-la (BL-333). At-rule de conteúdo FLAT (`@font-face`/`@page`)
    continua fora dessa checagem: `_extrair_regras_flat` já a descarta
    corretamente por começar com `@`."""
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


def _regra_tem_pseudo_classe_condicional(regra):
    """BL-333, decisão 2 (ver docstring do módulo): verdadeiro se ALGUM
    composto do seletor da regra tiver pseudo-classe — qualquer `:`, a
    mesma leitura que `_especificidade` já usa, porque este motor não
    distingue pseudo-classes estruturais (`:first-child`) das de
    INTERAÇÃO (`:hover`, `:focus`, `:active`), que nunca ocorrem no papel."""
    return any(":" in composto for composto in regra.compostos)


def _display_efetivo(indice_no, cadeia, regras):
    """Vencedor da cascata para `display` no nó `cadeia[indice_no]`: entre
    as regras cujo seletor casa com ele, `!important` vence sobre normal;
    dentro do mesmo grupo, maior especificidade vence; empate, a de MAIOR
    ordem (mais tardia no arquivo) vence — a regra padrão do CSS.

    BL-333, decisão 2: uma regra com pseudo-classe condicional
    (`_regra_tem_pseudo_classe_condicional`) e `display: none` é
    DESCARTADA do grupo de candidatas — ela não pode SATISFAZER a
    ocultação (a interação nunca ocorre ao imprimir). A MESMA regra com
    `display` diferente de `none` continua candidata normalmente — pode
    DERRUBAR uma ocultação (o lado seguro: ver a docstring do módulo)."""
    candidatas = []
    for regra in regras:
        if _seletor_casa_com_no(regra.compostos, indice_no, cadeia):
            decl = regra.declaracoes.get("display")
            if decl:
                if decl.valor == "none" and _regra_tem_pseudo_classe_condicional(regra):
                    continue
                candidatas.append((regra, decl, _especificidade_seletor(regra.compostos)))
    if not candidatas:
        return None
    importantes = [c for c in candidatas if c[1].importante]
    grupo = importantes or candidatas
    grupo.sort(key=lambda c: (c[2], c[0].ordem))
    return grupo[-1][1].valor


def _spans_de_at_rule_com_bloco_aninhado(texto):
    """Localiza, por PROFUNDIDADE de chaves (a mesma técnica de
    `_extrair_bloco_media_print` — nunca regex gulosa, que erra na
    presença de chave aninhada), todo at-rule de NÍVEL SUPERIOR de `texto`
    cujo bloco contém pelo menos uma chave ANINHADA. Devolve lista de
    `(prelúdio, inicio, fim)` com `fim` EXCLUSIVO — pronto para fatiar
    `texto[inicio:fim]` fora. At-rule de conteúdo FLAT (`@page { size: A4;
    }`, sem chave dentro) não entra aqui: `_extrair_regras_flat` já a
    descarta corretamente (seletor começa com `@`) — só a forma que ELA
    erra (içar o conteúdo aninhado para fora) é o alvo desta função."""
    achados = []
    i = 0
    n = len(texto)
    while i < n:
        if texto[i] == "@":
            m = re.match(r"@[\w-]+[^{}]*\{", texto[i:])
            if m:
                inicio = i
                inicio_chaves = i + m.end() - 1
                profundidade = 0
                aninhado = False
                fim = None
                j = inicio_chaves
                while j < n:
                    if texto[j] == "{":
                        profundidade += 1
                        if profundidade >= 2:
                            aninhado = True
                    elif texto[j] == "}":
                        profundidade -= 1
                        if profundidade == 0:
                            fim = j + 1
                            break
                    j += 1
                if fim is not None:
                    if aninhado:
                        achados.append((m.group(0).strip(), inicio, fim))
                    i = fim
                    continue
        i += 1
    return achados


def _prelude_e_media_screen_puro(prelude):
    """BL-343/F1: a ÚNICA exceção nomeada — `@media screen`, sozinho, sem
    combinar com outro tipo de mídia (`,`/`and`, ex. `@media screen and
    (min-width: 20rem)` NÃO entra aqui: a condição extra pode, em tese,
    valer também para `print` combinado com outro tipo por engano de
    quem escreve — a exceção só é segura na forma mais estrita). `prelude`
    vem de `_spans_de_at_rule_com_bloco_aninhado` com a chave de abertura
    ainda no fim (`"@media screen {"`); removida aqui antes de comparar.
    `screen` exclui `print` por definição (CSS Media Queries: os dois são
    tipos de mídia mutuamente exclusivos quando usados sozinhos) — é a
    ÚNICA condição deste motor que é comprovadamente irrelevante para a
    impressão, nunca "parece" irrelevante por coincidência."""
    sem_chave = prelude.rsplit("{", 1)[0]
    normalizado = re.sub(r"\s+", " ", sem_chave).strip().lower()
    return normalizado == "@media screen"


def _preparar_para_simulacao(texto, *, onde, exigir_ausencia_total):
    """BL-333, decisão 1, CORRIGIDA pelo BL-343/F1 (ver docstring do
    módulo — a decisão original estava ERRADA e por quê): valida a
    premissa que antes só existia em prosa — que `texto` não tem at-rule
    aninhada que a extração flat não saiba tratar — e, quando (e só
    quando) é SEGURO, remove essa at-rule em vez de deixá-la ser içada
    por engano.

    - `exigir_ausencia_total=True` (uso: DENTRO do próprio `@media print`
      já extraído): QUALQUER at-rule aninhada ali reprova pedindo extensão
      — a simulação não tenta adivinhar se ela se aplica ou não quando já
      está dentro do contexto de impressão.
    - `exigir_ausencia_total=False` (uso: fora do `@media print`, antes ou
      depois dele): LADO SEGURO INVERTIDO (F1) — toda at-rule aninhada
      REPROVA pedindo extensão, SEMPRE, EXCETO a única exceção NOMEADA e
      comprovadamente irrelevante para impressão (`_prelude_e_media_
      screen_puro`): essa é removida do texto (nunca pode provar nem
      derrubar ocultação, então pode ser descartada com segurança). Não
      existe mais a ideia de "prelúdio sem a palavra 'print' = nunca se
      aplica" — essa premissa era FALSA (media query sem tipo de mídia
      vale para `all`, que inclui `print`; `@supports`/`@layer` valem
      sempre) e o auditor mediu o efeito real dela em Chromium/PDF."""
    spans = _spans_de_at_rule_com_bloco_aninhado(texto)
    if not spans:
        return texto
    if exigir_ausencia_total:
        assert not spans, (
            f"a simulação de cascata (BL-329/BL-333) encontrou at-rule(s) aninhada(s) "
            f"{onde}, e não sabe avaliá-la(s): {[p for p, *_ in spans]!r} — ela PRECISA "
            f"SER ESTENDIDA antes de confiar no resultado, em vez de julgar "
            f"(silenciosamente) errado"
        )
        return texto
    nao_isentas = [(p, i, f) for p, i, f in spans if not _prelude_e_media_screen_puro(p)]
    assert not nao_isentas, (
        f"a simulação de cascata (BL-329/BL-333/BL-343) encontrou at-rule(s) aninhada(s) "
        f"{onde} que NÃO são a exceção nomeada '@media screen' (a ÚNICA condição "
        f"comprovadamente irrelevante para impressão), e não sabe avaliá-la(s): "
        f"{[p for p, *_ in nao_isentas]!r} — ela PRECISA SER ESTENDIDA antes de confiar "
        f"no resultado, em vez de assumir (silenciosamente) que são irrelevantes"
    )
    limpo = texto
    for _prelude, inicio, fim in reversed(spans):
        limpo = limpo[:inicio] + limpo[fim:]
    return limpo


# Bases de ordem bem separadas para os três trechos (antes/dentro/depois do
# @media print) — BL-333: usar CONSTANTES em vez de `len(antes)`/
# `len(antes) + len(dentro)` desacopla a ORDEM relativa entre os três
# trechos de quaisquer caracteres removidos por `_preparar_para_simulacao`
# (que muda o comprimento de `antes`/`depois`). O que a cascata precisa é
# só que toda regra de `antes` ordene ANTES de toda regra de `dentro`, que
# ordene ANTES de toda regra de `depois` — a MESMA garantia de antes, sem
# depender do comprimento pós-limpeza.
_ORDEM_BASE_ANTES = 0
_ORDEM_BASE_DENTRO = 1_000_000
_ORDEM_BASE_DEPOIS = 2_000_000


def _algum_ancestral_removido_do_papel(cadeia, css_texto):
    """Propriedade central desta guarda: existe, na cadeia (do link da marca
    até a raiz), algum nó cujo `display` efetivo sob impressão é `none`?
    Devolve (removido: bool, nó_que_resolveu_ou_None)."""
    antes, dentro, depois = _extrair_bloco_media_print(css_texto)
    antes_limpo = _preparar_para_simulacao(
        antes, onde="antes do @media print", exigir_ausencia_total=False
    )
    depois_limpo = _preparar_para_simulacao(
        depois, onde="depois do @media print", exigir_ausencia_total=False
    )
    _preparar_para_simulacao(dentro, onde="dentro do @media print", exigir_ausencia_total=True)
    regras = (
        _extrair_regras_flat(antes_limpo, _ORDEM_BASE_ANTES)
        + _extrair_regras_flat(dentro, _ORDEM_BASE_DENTRO)
        + _extrair_regras_flat(depois_limpo, _ORDEM_BASE_DEPOIS)
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


# ---------------------------------------------------------------------------
# BL-333 (M1 da auditoria DL-026, rodada 5): as quatro sabotagens que o
# auditor reproduziu IMPORTANDO estas mesmas funções — a simulação de
# cascata errava DENTRO do limite que ela mesma declara, nas duas direções.
# As três primeiras (S6/S7/S8) fazem a marca SAIR no papel enquanto a guarda
# antiga aprovava (falso "escondido"); a quarta (S9) é código CORRETO que a
# guarda antiga reprovava (falso "reprovado"). As quatro têm de produzir o
# resultado CERTO agora: as três primeiras MORREM, a quarta PASSA.
# ---------------------------------------------------------------------------


def test_sabotagem_hover_dentro_do_media_print_mata_a_guarda(tmp_path):
    """S6 do achado M1: substitui a regra incondicional que esconde
    `.cabecalho__topo` por uma condicionada a `:hover` — que NUNCA ocorre
    no papel (não há ponteiro na impressão). Antes da correção BL-333, o
    motor tratava `:hover` como se valesse sempre e a guarda continuava
    aprovando; agora `_display_efetivo` descarta candidata condicional com
    `display: none` (decisão 2 da docstring do módulo)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    alvo = (
        "    .pular-para-conteudo,\n    .cabecalho__topo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    substituto = (
        "    .pular-para-conteudo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }\n\n"
        "    .cabecalho__topo:hover {\n        display: none;\n    }"
    )
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    removido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert removido_depois is False, (
        "a sabotagem :hover deveria ter feito a guarda MORRER, e ela continuou aprovando"
    )


def test_sabotagem_regra_dentro_de_media_screen_mata_a_guarda(tmp_path):
    """S7 do achado M1: a mesma remoção de `.cabecalho__topo` da lista de
    ocultos, mas com a regra de reocultação escrita dentro de `@media
    screen` (o OPOSTO de impressão) — o mesmo defeito que `:hover`, só que
    por at-rule aninhada em vez de pseudo-classe. Antes da correção, o
    motor içava o conteúdo do `@media screen` para o conjunto incondicional
    e a guarda aprovava; agora `_preparar_para_simulacao` REMOVE esse
    at-rule (prelúdio sem 'print') antes de extrair regras — decisão 1 da
    docstring do módulo."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    alvo = (
        "    .pular-para-conteudo,\n    .cabecalho__topo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    substituto = (
        "    .pular-para-conteudo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    css_mutado = caminho_mutado.read_text(encoding="utf-8")
    # A regra de reocultação entra DEPOIS do @media print inteiro, dentro de
    # @media screen — nunca se aplica ao imprimir, e a marca fica sem
    # NENHUMA regra que a esconda sob impressão.
    css_mutado += "\n\n@media screen {\n    .cabecalho__topo {\n        display: none;\n    }\n}\n"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    removido_depois, _ = _algum_ancestral_removido_do_papel(cadeia, css_mutado)
    assert removido_depois is False, (
        "a sabotagem @media screen deveria ter feito a guarda MORRER, e ela continuou aprovando"
    )


def test_sabotagem_regra_dentro_de_supports_mata_a_guarda(tmp_path):
    """S8 do achado M1: a mesma sabotagem de S7, agora dentro de `@supports
    (display: grid)` — outra at-rule aninhada, condição diferente (suporte
    de funcionalidade, não mídia), mesmo defeito.

    ⚠️ Resultado ATUALIZADO pelo BL-343/F1: antes, `@supports` sem a
    palavra "print" era silenciosamente IGNORADA (mesmo tratamento de
    `@media screen`) e a guarda morria por retornar `removido_depois is
    False`. Desde F1, `@supports` NÃO é mais a exceção nomeada (só
    `@media screen` é — `@supports` não fala de mídia e vale SEMPRE,
    inclusive ao imprimir) — a guarda continua MORRENDO, mas agora por
    REPROVAR PEDINDO EXTENSÃO (a simulação recusa julgar em vez de supor
    que é irrelevante), a mesma escolha de "reprovar pedindo extensão em
    vez de aprovar por engano"."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    alvo = (
        "    .pular-para-conteudo,\n    .cabecalho__topo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    substituto = (
        "    .pular-para-conteudo,\n    .navegacao-empresa,\n"
        "    .formulario-periodo,\n    .mensagens,\n    kbd.tecla,\n    button {\n"
        "        display: none;\n    }"
    )
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    css_mutado = caminho_mutado.read_text(encoding="utf-8")
    css_mutado += (
        "\n\n@supports (display: grid) {\n"
        "    .cabecalho__topo {\n        display: none;\n    }\n"
        "}\n"
    )
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_media_query_responsiva_legitima_depois_do_media_print_nao_reprova(tmp_path):
    """S9 do achado M1, CORRIGIDO pelo BL-343/F1 (ver docstring do módulo).

    O exemplo original deste teste usava `@media (min-width: 80rem)` como
    "código legítimo" — um exemplo que o `arquiteto-senior` deu, na
    rodada 5. O auditor da rodada 6 MEDIU que esse exemplo NÃO é
    inofensivo: sob `emulate_media(media="print")` a 1280px, ele reexibe
    `.cabecalho__topo` mesmo imprimindo (media query sem tipo de mídia
    vale para `all`, que inclui `print`) — só parecia inofensivo no PDF
    A4 do `juiz.py` por COINCIDÊNCIA de largura de página (~49,6rem), não
    por propriedade. Era, portanto, uma aprovação ERRADA fixada em teste
    obrigatório.

    O caso legítimo de VERDADE é `@media screen`, acrescentado DEPOIS do
    `@media print` já correto e INTACTO: `screen` EXCLUI `print` por
    definição, então nada ali dentro pode provar ou derrubar ocultação
    sob impressão — `_preparar_para_simulacao` remove essa at-rule (a
    ÚNICA exceção nomeada) antes da extração, o `@media print` original
    continua decidindo sozinho, e a guarda PASSA.

    ⚠️ Falso alarme na CI é, pelo argumento do BL-321, mais corrosivo que
    falso negativo: ensina que a guarda erra."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + (
        "\n\n@media screen {\n    .cabecalho__topo {\n        display: flex;\n    }\n}\n"
    )
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    removido_depois, _ = _algum_ancestral_removido_do_papel(cadeia, css_mutado)
    assert removido_depois is True, (
        "a media query @media screen legítima, com o @media print intacto, NÃO deveria "
        "fazer a guarda reprovar — e ela reprovou"
    )


def test_at_rule_mencionando_print_fora_do_bloco_tratado_reprova_pedindo_extensao():
    """BL-333, decisão 1: um SEGUNDO `@media print` (ou `@media print and
    (...)`) solto no arquivo, fora do primeiro bloco já tratado por
    `_extrair_bloco_media_print`, não pode ser silenciosamente ignorado —
    a simulação não sabe se ele reforça ou desfaz o resultado do primeiro.
    Em vez de adivinhar, `_preparar_para_simulacao` reprova pedindo
    extensão — continua valendo depois do BL-343/F1 (um `@media print
    and (...)` não é `@media screen` puro, então nunca seria a exceção
    nomeada de qualquer forma; só a MENSAGEM da falha mudou de texto).
    Sobre CSS sintético em memória — não precisa de `tmp_path` porque não
    mexe no arquivo real, só chama a função pura."""
    css_sintetico = (
        "@media print {\n    .cabecalho__topo {\n        display: none;\n    }\n}\n\n"
        "@media print and (min-width: 40rem) {\n"
        "    .cabecalho__topo {\n        display: flex;\n    }\n"
        "}\n"
    )
    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(_cadeia_da_marca()[1], css_sintetico)


# ---------------------------------------------------------------------------
# BL-343 (F1 da auditoria DL-026, rodada 6): a tabela de sete construções
# que o auditor mediu em Chromium/PDF A4 reais — reproduzidas aqui sobre
# uma CÓPIA do `base.css` REAL (BL-311), do jeito EXATO que ele mediu
# (acréscimo ao FIM do arquivo, com o @media print original intocado). As
# SEIS primeiras MUDAM o papel de verdade e precisam matar a suíte —
# agora reprovando PEDINDO EXTENSÃO, o lado seguro invertido — em vez de
# serem silenciosamente ignoradas. A sétima (`@media screen`) é a ÚNICA
# exceção nomeada e continua aprovando — coberta acima por
# `test_media_query_responsiva_legitima_depois_do_media_print_nao_reprova`
# e por `test_sabotagem_regra_dentro_de_media_screen_mata_a_guarda`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rotulo,at_rule,seletor,declaracao",
    [
        ("reexibindo a marca", "@media (min-width: 20rem)", ".cabecalho__topo", "display: flex;"),
        ("reexibindo a marca", "@supports (display: grid)", ".cabecalho__topo", "display: flex;"),
        ("reexibindo a marca", "@media all", ".cabecalho__topo", "display: flex;"),
        ("reexibindo a marca", "@layer", ".cabecalho__topo", "display: flex;"),
        ("escondendo o timbre", "@media (min-width: 20rem)", ".timbre-impressao", "display: none;"),
        ("escondendo o timbre", "@supports (display: grid)", ".timbre-impressao", "display: none;"),
    ],
)
def test_f1_construcoes_que_mudam_o_papel_reprovam_pedindo_extensao(
    tmp_path, rotulo, at_rule, seletor, declaracao
):
    """BL-343/F1: as SEIS construções da tabela do achado (Chromium 1194 +
    PDF A4 reais, docs/auditorias/2026-09-19-dl-026-rodada-6.md) que a
    guarda ANTIGA tratava como "nunca se aplicam à impressão" só porque o
    prelúdio não continha a palavra "print" — e que, medidas de verdade,
    mudam o papel (a marca do fornecedor reaparece, ou o timbre do
    escritório some). Reproduzidas sobre uma CÓPIA do `base.css` real
    (acréscimo ao FIM, o `@media print` original intocado — exatamente
    como o auditor mediu). Precisam reprovar PEDINDO EXTENSÃO agora, não
    ser silenciosamente descartadas nem aprovadas por engano."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = f"{at_rule} {{\n    {seletor} {{\n        {declaracao}\n    }}\n}}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_at_rule_aninhada_dentro_do_media_print_reprova_pedindo_extensao():
    """BL-333, decisão 1: uma at-rule aninhada DENTRO do próprio `@media
    print` (aqui, `@supports`) também reprova pedindo extensão — mesmo
    sem mencionar 'print' — porque `exigir_ausencia_total=True` se aplica
    a esse trecho: a simulação já está no contexto de impressão e não sabe
    resolver a condição adicional."""
    css_sintetico = (
        "@media print {\n"
        "    @supports (display: grid) {\n"
        "        .cabecalho__topo {\n            display: none;\n        }\n"
        "    }\n"
        "}\n"
    )
    with pytest.raises(AssertionError, match="dentro do @media print"):
        _algum_ancestral_removido_do_papel(_cadeia_da_marca()[1], css_sintetico)
