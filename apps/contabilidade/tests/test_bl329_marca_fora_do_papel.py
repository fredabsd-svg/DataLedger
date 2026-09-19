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

⚠️ **BL-351 (bloqueador G1 + MÉDIA G3 da auditoria DL-026, rodada 7,
docs/auditorias/2026-09-19-dl-026-rodada-7.md): o BL-343 corrigiu COMO
decidir sobre uma at-rule aninhada; não corrigiu O QUE o detector VÊ.** O
laço que encontrava blocos aninhados só abria em `if texto[i] == "@"` — e
`.cabecalho { .cabecalho__topo { display: flex } }` (CSS Nesting nativo,
a forma recomendada de escrever CSS hoje) nunca começa com `@`, então
NUNCA era visto: o bloco era içado pela extração flat como se fosse uma
regra comum, e a marca do fornecedor voltava ao papel com `1844 passed`
(medido pelo auditor em Chromium e PDF A4 reais). Pelo OUTRO lado
(G3/BL-353): o lado seguro invertido do BL-343 reprovava QUALQUER at-rule
aninhada que não fosse `@media screen` puro — inclusive uma media query
legítima que não menciona marca nem timbre nenhum (`@media (max-width:
48rem) { .tabela-dados { display: block } }`), produzindo 19 falsos
alarmes. Duas correções, uma raiz comum:

1. **Generalizar o DETECTOR** (`_spans_de_at_rule_com_bloco_aninhado` →
   renomeada `_spans_de_bloco_com_bloco_aninhado`, sobre
   `_eventos_de_nivel_superior`): o laço abre em QUALQUER prelúdio que
   preceda um `{` de nível superior, comece com `@` ou não — a mesma
   técnica de contagem de profundidade de chaves, só que sem a suposição
   de que "bloco perigoso" e "começa com @" são a mesma coisa.
2. **Classificar por CONTEÚDO, não pelo prelúdio**
   (`_identificadores_mencionados_no_bloco`/`_identificadores_de_
   interesse`, usadas por `_preparar_para_simulacao`): depois da exceção
   nomeada `@media screen` (que continua sendo removida sem olhar para
   dentro — é a única condição comprovadamente irrelevante, não uma
   heurística), cada bloco aninhado restante é examinado por dentro,
   RECURSIVAMENTE: os identificadores (classe/tipo) que o prelúdio e todo
   seletor aninhado mencionam são comparados com os da `cadeia` de
   interesse que a guarda chamadora já deriva do HTML renderizado. Casou
   com ALGUM → reprova pedindo extensão, nomeando o prelúdio (a
   simulação não sabe avaliar aquele bloco). Não casou com NENHUM → o
   bloco é comprovadamente irrelevante PARA ESTA CADEIA, e é removido
   com segurança — isso mata o falso alarme do G3 sem alargar a exceção
   nomeada, porque a decisão não depende mais de quantas palavras o
   prelúdio contém.
3. **At-rule de DECLARAÇÃO** (`@import url(...);`, sem bloco) também
   reprova SEMPRE, em vez de ser colada ao seletor seguinte pela regex de
   `_extrair_regras_flat` e desaparecer em silêncio — detectada por
   `_eventos_de_nivel_superior` como um evento PRÓPRIO (`_EventoDeclaracao`),
   isolado do texto ANTES da extração flat correr.

A ASSINATURA pública que outros arquivos importam
(`_algum_ancestral_removido_do_papel(cadeia, css_texto)`) não mudou — a
`cadeia` já estava disponível ali; só passou a ser propagada para dentro
de `_preparar_para_simulacao`, de onde a classificação por conteúdo deriva
os identificadores de interesse. Nenhuma lista de nomes de classe foi
escrita à mão para isso: uma lista literal de `.marca`/`.timbre-impressao`
reintroduziria exatamente o defeito que esta correção existe para fechar.

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


# BL-351 (bloqueador G1 da auditoria DL-026, rodada 7,
# docs/auditorias/2026-09-19-dl-026-rodada-7.md): os dois tipos de evento de
# NÍVEL SUPERIOR que `_eventos_de_nivel_superior` (abaixo) produz — um
# bloco (`prelúdio { corpo }`, comece o prelúdio com '@' ou não) ou uma
# at-rule de DECLARAÇÃO (`@regra ...;`, sem bloco nenhum). Duas classes
# distintas, nunca um único formato "genérico", porque o CHAMADOR precisa
# tratá-las de formas incompatíveis: um bloco pode, às vezes, ser removido
# com segurança (exceção nomeada, ou irrelevância comprovada por
# conteúdo); uma declaração NUNCA pode — não há corpo nenhum para provar
# irrelevância, e ela pode mudar o significado do que vem depois dela
# (`@import`, por exemplo).
@dataclass
class _EventoBloco:
    prelude: str
    inicio: int
    fim: int
    corpo: str
    aninhado: bool


@dataclass
class _EventoDeclaracao:
    prelude: str
    inicio: int
    fim: int


def _remover_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _extrair_bloco_media_print(css):
    """Devolve (antes, dentro, depois) do ÚNICO `@media print { ... }` do
    arquivo — contagem de chaves, não regex gulosa, porque o conteúdo tem
    chaves aninhadas (cada regra de seletor, dentro do media). `antes` e
    `depois` PODEM ter bloco aninhado de verdade (outro `@media`,
    `@supports`, ou CSS Nesting nativo sem `@` nenhum — BL-351) — ver
    `_spans_de_bloco_com_bloco_aninhado` e o uso dela em
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


# ---------------------------------------------------------------------------
# BL-360 (ALTA da auditoria DL-026, rodada 8 — a nona ocorrência da classe
# desta etapa: prelúdio (BL-343) → caractere de abertura (BL-351) →
# GRAMÁTICA DO SELETOR, agora). O auditor furou a correção do BL-351 por um
# eixo novo: seletor que CASA com a cadeia sem MENCIONAR identificador
# nenhum dela — `[class]` (seletor de atributo, especificidade real (0,1,0),
# que `_especificidade` pontuava (0,0)) e `*` (universal) fazem a marca
# voltar ao papel de verdade (medido em Chromium 1194 + `emulate_media
# ("print")`) enquanto a guarda aprovava — porque `_composto_casa_com_no`
# não achava tipo nem classe e `all([])` devolvia verdadeiro por "acaso
# certo", e `_especificidade` pontuava (0,0) por não saber que `[...]`
# conta como classe. `:is(...)`/`:where(...)` já reprovavam, mas por
# ACIDENTE aritmético (`composto.count(":")` contando o `:` de dentro do
# parêntese como pseudo-classe), não por saber o que `:is` faz.
#
# A CORREÇÃO (pedida pelo arquiteto, e é a mesma virada do BL-355): em vez
# de enumerar o que o motor NÃO sabe ler (lista que cresce para sempre —
# amanhã alguém escreve `:has(...)` e a lista fica uma auditoria atrás),
# aparar do composto o que a gramática RECONHECE (tipo, classe,
# pseudo-classe SIMPLES sem parênteses — a MESMA gramática que
# `_composto_casa_com_no`/`_especificidade` já assumem) e, se sobrar
# QUALQUER caractere, recusar julgar. A recusa é ESCOPADA por propriedade
# de interesse (`_PROPRIEDADES_DE_INTERESSE`): um seletor de atributo que
# não declara `display` continua irrelevante para esta guarda, do mesmo
# jeito que sempre foi — o motor nunca precisou entendê-lo.
# ---------------------------------------------------------------------------


def _residuo_nao_reconhecido_do_composto(composto):
    """Apara de `composto` o que a gramática deste motor RECONHECE — um
    tipo opcional no início, seguido de qualquer quantidade de `.classe`
    e `:pseudo-classe-simples` (sem `(` logo depois, que indicaria uma
    pseudo-classe FUNCIONAL: `:is(`, `:where(`, `:not(`, `:has(`... — este
    motor não resolve o que está DENTRO dos parênteses, e fingir que sabe
    seria voltar ao julgamento por acidente que o BL-360 mediu). O que
    SOBRAR depois de aparar é a resposta: não-vazio significa construção
    que o motor não sabe LER — seletor de atributo (`[...]`), universal
    (`*`), pseudo-classe funcional, combinador que não seja espaço
    (`>`/`+`/`~`, que aparece como um composto próprio depois do
    `seletor.split()` de `_extrair_regras_flat`/`_identificadores_do_
    seletor`, ou colado a outro composto sem espaço) — qualquer coisa que
    a linguagem CSS ganhe amanhã e que ninguém tenha ensinado a este
    motor hoje."""
    residuo = re.sub(r"^[a-zA-Z][\w-]*", "", composto, count=1)
    anterior = None
    while anterior != residuo:
        anterior = residuo
        residuo = re.sub(r"^\.[\w-]+", "", residuo)
        residuo = re.sub(r"^:[a-zA-Z-][\w-]*(?!\()", "", residuo)
    return residuo


def _seletor_bruto_tem_construcao_nao_modelada(seletor_bruto):
    """Verdadeiro se ALGUM composto de `seletor_bruto` (dividido em lista
    por vírgula, depois em compostos por espaço — a MESMA divisão que
    `_extrair_regras_flat` já faz) tiver resíduo depois de
    `_residuo_nao_reconhecido_do_composto`."""
    for seletor in seletor_bruto.split(","):
        for composto in seletor.split():
            if _residuo_nao_reconhecido_do_composto(composto):
                return True
    return False


def _corpo_declara_propriedade_de_interesse(corpo):
    """Verdadeiro se `corpo` (texto de declarações, `prop: valor;
    prop2: valor2;`, SEM chave aninhada — chamar sobre `_texto_de_
    declaracoes_diretas`, nunca sobre um corpo com bloco dentro) tiver
    alguma declaração cuja propriedade esteja em `_PROPRIEDADES_DE_
    INTERESSE`. Mesma leitura de `;`/`:` que `_extrair_regras_flat` já
    usa — não reescrita aqui como uma segunda fonte da verdade sobre o
    que é uma declaração; só a pergunta booleana que falta para decidir
    se vale a pena checar a gramática do SELETOR."""
    for decl in corpo.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, _ = decl.partition(":")
        if prop.strip().lower() in _PROPRIEDADES_DE_INTERESSE:
            return True
    return False


def _texto_de_declaracoes_diretas(corpo):
    """`corpo` menos todo evento de nível superior (bloco OU declaração —
    `_eventos_de_nivel_superior`) — o que SOBRA é só o texto de
    declaração DIRETA deste nível (CSS Nesting permite um bloco ter
    declaração direta E regra aninhada ao mesmo tempo, ex. `.cabecalho[x]
    { display: block; .topo { color: red; } }` — a declaração `display`
    pertence ao PRELÚDIO externo, não à regra aninhada, e só este recorte
    a isola corretamente)."""
    eventos = _eventos_de_nivel_superior(corpo)
    partes = []
    cursor = 0
    for evento in eventos:
        partes.append(corpo[cursor : evento.inicio])
        cursor = evento.fim
    partes.append(corpo[cursor:])
    return "".join(partes)


def _extrair_regras_flat(texto, offset):
    """`texto` sem chave aninhada. `offset` é a posição absoluta no arquivo
    original — preserva a ORDEM verdadeira de declaração, que a cascata CSS
    usa para desempatar especificidade igual. Só guarda regras que declarem
    `display` — o resto não importa para esta guarda.

    BL-360: antes de aceitar uma regra que declara propriedade de
    interesse, valida que o SELETOR é feito só de construções que a
    gramática deste motor reconhece (`_seletor_bruto_tem_construcao_nao_
    modelada`) — senão reprova pedindo extensão, nomeando o seletor, em
    vez de pontuar `_especificidade`/`_composto_casa_com_no` errado (ou
    "por acaso certo") sobre uma construção que eles não sabem ler."""
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
        assert not _seletor_bruto_tem_construcao_nao_modelada(seletor_bruto), (
            f"a simulação de cascata (BL-329/BL-360) encontrou um seletor com "
            f"construção que ela não sabe LER, declarando propriedade de interesse "
            f"({', '.join(sorted(declaracoes))}): {seletor_bruto!r} — ela PRECISA SER "
            f"ESTENDIDA antes de confiar no resultado, em vez de julgar (por acaso "
            f"certo ou errado) uma gramática que ela não reconhece"
        )
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


def _eventos_de_nivel_superior(texto):
    """BL-351 (bloqueador G1 da auditoria DL-026, rodada 7,
    docs/auditorias/2026-09-19-dl-026-rodada-7.md): percorre `texto` (uma
    folha de estilo, ou o CORPO já isolado de um bloco) e devolve, na
    ORDEM em que aparecem, todo evento de NÍVEL SUPERIOR — nunca desce
    dentro de um bloco para relatar o que tem lá dentro (quem quiser
    recursão chama de novo sobre `evento.corpo`; ver
    `_identificadores_mencionados_no_bloco`). Por CONTAGEM DE PROFUNDIDADE
    de chaves — a mesma técnica de `_extrair_bloco_media_print` — nunca
    regex gulosa, que erra na presença de chave aninhada.

    Dois tipos de evento, e o motivo de serem DUAS classes em vez de uma:

    - `_EventoBloco`: um prelúdio seguido de `{ ... }` balanceado.
      `aninhado` é verdadeiro quando `corpo` contém pelo menos uma chave
      própria. **A generalização central desta correção**: o laço abre em
      QUALQUER caractere que preceda um `{` de nível superior — comece o
      prelúdio com `@` ou não. Antes desta correção
      (`_spans_de_at_rule_com_bloco_aninhado`, o nome antigo, ainda mais
      estreito que o do BL-343), o laço só abria em `if texto[i] == "@"`
      — e `.cabecalho { .cabecalho__topo { display: flex } }` (CSS
      Nesting nativo, a forma recomendada de escrever CSS hoje) nunca
      começa com `@`, então NUNCA era visto: o bloco era içado pela
      extração flat como se fosse uma regra comum, e a marca do
      fornecedor voltava ao papel com `1844 passed`. Generalizar o
      CARACTERE de abertura (de `"@"` para `"{"`, olhando para trás até o
      prelúdio) fecha essa classe de escape por CONSTRUÇÃO, não por mais
      um caso na lista.
    - `_EventoDeclaracao`: um prelúdio terminado por `;` ANTES de
      qualquer `{` — sempre começa com `@` em CSS válido (`@import`,
      `@charset`, `@namespace`...). Detectada por um motivo PRÓPRIO,
      independente do anterior: sem isto, uma regex gulosa como a de
      `_extrair_regras_flat` (`([^{}]+)\\{([^{}]*)\\}`) cola
      `@import url(...);` ao SELETOR SEGUINTE — o resultado colado
      começa com `@` e a regra inteira (a de verdade, que talvez
      escondesse ou reexibisse algo relevante) desaparece, sem aviso
      nenhum, duas vezes. Isolar o `;` aqui, ANTES da extração flat,
      impede a colagem: o próximo prelúdio começa limpo, depois do `;`."""
    eventos = []
    n = len(texto)
    inicio_prelude = 0
    i = 0
    while i < n:
        if texto[i] == ";":
            prelude = texto[inicio_prelude : i + 1].strip()
            if prelude.startswith("@"):
                eventos.append(_EventoDeclaracao(prelude, inicio_prelude, i + 1))
            inicio_prelude = i + 1
            i += 1
            continue
        if texto[i] == "{":
            prelude = texto[inicio_prelude:i].strip()
            profundidade = 1
            aninhado = False
            fim = None
            j = i + 1
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
                corpo = texto[i + 1 : fim - 1]
                eventos.append(_EventoBloco(prelude, inicio_prelude, fim, corpo, aninhado))
                inicio_prelude = fim
                i = fim
                continue
        i += 1
    return eventos


def _spans_de_bloco_com_bloco_aninhado(texto):
    """BL-351: nome HONESTO do que a função devolve, depois da
    generalização — não é mais só "at-rule com bloco aninhado" (o nome
    antigo, `_spans_de_at_rule_com_bloco_aninhado`), porque CSS Nesting
    nativo produz a MESMA forma perigosa sem nenhuma at-rule envolvida.
    Devolve lista de `(prelúdio, inicio, fim)` com `fim` EXCLUSIVO —
    pronto para fatiar `texto[inicio:fim]` fora — filtrando
    `_eventos_de_nivel_superior` para só os blocos ANINHADOS; blocos FLAT
    (`.foo { color: red; }`, `@page { size: A4; }`) não entram aqui:
    `_extrair_regras_flat` já os trata corretamente sozinha."""
    return [
        (evento.prelude, evento.inicio, evento.fim)
        for evento in _eventos_de_nivel_superior(texto)
        if isinstance(evento, _EventoBloco) and evento.aninhado
    ]


def _identificadores_do_seletor(seletor_bruto):
    """Nomes de CLASSE e de TIPO que `seletor_bruto` menciona — mesma
    gramática que o resto deste motor entende (tipo + classe, combinador
    descendente por espaço, lista separada por vírgula; ver limites na
    docstring do módulo). Serve tanto para um SELETOR de verdade quanto
    para um prelúdio de bloco de CSS Nesting (`.cabecalho`, `&
    .cabecalho__topo` — o `&` é ignorado: não é letra nem começa com
    ponto, então nenhuma das duas regras o casa, e ele não introduz
    identificador nenhum por si só). Usada para decidir, por CONTEÚDO
    (BL-351), se um bloco que a simulação não sabe avaliar por outro
    caminho ainda assim PODE afetar a cadeia de interesse — nunca para
    casar seletor com nó (isso é `_seletor_casa_com_no`)."""
    identificadores = set()
    for seletor in seletor_bruto.split(","):
        for composto in seletor.split():
            sem_pseudo = composto.split(":")[0]
            identificadores.update(re.findall(r"\.([\w-]+)", sem_pseudo))
            tag_m = re.match(r"^[a-zA-Z][\w-]*", sem_pseudo)
            if tag_m:
                identificadores.add(tag_m.group())
    return identificadores


def _identificadores_mencionados_no_bloco(prelude, corpo):
    """BL-351: o CORAÇÃO da classificação por conteúdo. Devolve
    `(identificadores, seletor_nao_modelado)`.

    `identificadores` — classe e tipo que ESTE bloco — prelúdio MAIS todo
    seletor aninhado dentro do corpo, em QUALQUER profundidade — pode
    afetar. O prelúdio só contribui identificadores quando NÃO é uma
    at-rule (não começa com `@`): o prelúdio de uma at-rule (`@media
    (...)`, `@supports (...)`, `@layer nome`) é uma CONDIÇÃO, não um
    seletor — não referencia nó nenhum da árvore por si só. Já o
    prelúdio de um bloco de CSS Nesting (`.cabecalho`, `&
    .cabecalho__topo`) É um seletor de verdade, e conta. A RECURSÃO
    (chamando a si mesma sobre cada bloco de nível superior do `corpo`,
    via `_eventos_de_nivel_superior`) é o que cobre aninhamento de mais
    de um nível — ex. `.conteudo-principal { .rodape { .timbre-impressao
    { display: none } } }`: o identificador `timbre-impressao` só existe
    no nível MAIS interno, e só chega até aqui porque cada chamada desce
    mais um nível em vez de examinar só o prelúdio externo.

    `seletor_nao_modelado` — BL-360 (achado ALTA da auditoria DL-026,
    rodada 8): o primeiro seletor, entre este nível e QUALQUER nível
    aninhado abaixo dele, que (a) não é prelúdio de at-rule, (b) DECLARA
    diretamente alguma propriedade de interesse (`_corpo_declara_
    propriedade_de_interesse` sobre `_texto_de_declaracoes_diretas` — não
    sobre `corpo` inteiro, que pode ter regra aninhada misturada com
    declaração direta) e (c) tem construção que a gramática deste motor
    não reconhece (`_seletor_bruto_tem_construcao_nao_modelada`) — ou
    `None` se nenhum existir. Um bloco com `seletor_nao_modelado`
    NÃO PODE ser provado irrelevante por identificador: o motor não sabe
    LER aquele seletor, então não pode afirmar que ele não afeta a
    cadeia — a mesma razão pela qual `_extrair_regras_flat` reprova a
    forma FLAT do mesmo problema."""
    identificadores = set()
    seletor_nao_modelado = None
    if prelude and not prelude.startswith("@"):
        identificadores |= _identificadores_do_seletor(prelude)
        if _corpo_declara_propriedade_de_interesse(
            _texto_de_declaracoes_diretas(corpo)
        ) and _seletor_bruto_tem_construcao_nao_modelada(prelude):
            seletor_nao_modelado = prelude
    for evento in _eventos_de_nivel_superior(corpo):
        if isinstance(evento, _EventoBloco):
            sub_identificadores, sub_residuo = _identificadores_mencionados_no_bloco(
                evento.prelude, evento.corpo
            )
            identificadores |= sub_identificadores
            if seletor_nao_modelado is None:
                seletor_nao_modelado = sub_residuo
        # _EventoDeclaracao aninhada (@import/@charset dentro de um
        # bloco — inválido em CSS de verdade, mas não é este motor quem
        # valida sintaxe) não tem seletor para contribuir; o CHAMADOR de
        # nível superior já reprova qualquer declaração encontrada em
        # `_preparar_para_simulacao`, então uma declaração aninhada nunca
        # chega a decidir relevância sozinha.
    return identificadores, seletor_nao_modelado


def _identificadores_de_interesse(cadeia):
    """Identificadores (classe e tipo) de TODOS os nós de `cadeia` — a
    cadeia de ancestrais que a guarda que chama este motor está mesmo
    verificando (a marca do fornecedor, o timbre do escritório, "Usuário",
    "Empresa"/"Período" — cada guarda deriva a SUA cadeia do HTML
    renderizado, nunca deste módulo). NUNCA uma lista de nomes de classe
    escrita à mão aqui — BL-351: uma lista literal de `.marca`/`.timbre-
    impressao` reintroduziria exatamente o defeito que esta correção
    existe para fechar (a próxima classe de interesse, de uma guarda
    futura, ficaria fora da lista até alguém lembrar de atualizá-la)."""
    identificadores = set()
    for no in cadeia:
        identificadores.add(no.tag)
        identificadores.update(no.classes)
    return identificadores


def _prelude_e_media_screen_puro(prelude):
    """BL-343/F1: a ÚNICA exceção nomeada — `@media screen`, sozinho, sem
    combinar com outro tipo de mídia (`,`/`and`, ex. `@media screen and
    (min-width: 20rem)` NÃO entra aqui: a condição extra pode, em tese,
    valer também para `print` combinado com outro tipo por engano de
    quem escreve — a exceção só é segura na forma mais estrita). `screen`
    exclui `print` por definição (CSS Media Queries: os dois são tipos de
    mídia mutuamente exclusivos quando usados sozinhos) — é a ÚNICA
    condição deste motor que é comprovadamente irrelevante para a
    impressão, nunca "parece" irrelevante por coincidência, e por isso é
    a única removida SEM olhar para o conteúdo (BL-351: a classificação
    por conteúdo, abaixo, só entra em jogo DEPOIS desta exceção nomeada)."""
    normalizado = re.sub(r"\s+", " ", prelude).strip().lower()
    return normalizado == "@media screen"


def _preparar_para_simulacao(texto, *, onde, exigir_ausencia_total, cadeia):
    """BL-333, decisão 1, CORRIGIDA pelo BL-343/F1 e, agora, pelo BL-351
    (bloqueador G1/G3 da rodada 7 — ver docstring do módulo): valida a
    premissa que antes só existia em prosa — que `texto` não tem
    construção de nível superior que a extração flat não saiba tratar —
    e, quando (e só quando) é SEGURO, remove essa construção em vez de
    deixá-la ser içada ou colada por engano.

    Ordem de decisão, para cada bloco aninhado encontrado (BL-351,
    pedido do arquiteto — nunca pule etapa nem troque a ordem):

    1. At-rule de DECLARAÇÃO (`@import`/`@charset`/`@namespace`...,
       `_EventoDeclaracao`) — SEMPRE reprova pedindo extensão, em
       QUALQUER um dos três trechos (`onde`). Não há corpo para provar
       irrelevância, e a simulação não sabe se ela muda o significado do
       que vem depois — nunca descartada só por começar com `@`.
    2. `exigir_ausencia_total=True` (uso: DENTRO do `@media print` já
       extraído) — QUALQUER bloco aninhado reprova pedindo extensão,
       sempre; a simulação não tenta adivinhar dentro do contexto de
       impressão.
    3. `exigir_ausencia_total=False` (fora do `@media print`) — para
       cada bloco aninhado, NESTA ordem:
       a. Exceção NOMEADA primeiro: `@media screen` puro
          (`_prelude_e_media_screen_puro`) é removido com segurança, sem
          olhar para dentro — é a ÚNICA condição comprovadamente
          irrelevante para impressão.
       b. Classificação por CONTEÚDO (BL-351, o que fecha o G1 e o G3
          juntos): extrai os identificadores que o prelúdio e TODO
          seletor aninhado dentro do bloco mencionam
          (`_identificadores_mencionados_no_bloco`) e compara com os da
          `cadeia` de interesse (`_identificadores_de_interesse`). Se
          ALGUMA regra interna puder casar (interseção não vazia) →
          reprova pedindo extensão, nomeando o prelúdio — a simulação
          não sabe avaliar aquele bloco e não pode fingir que sabe. Se
          NENHUMA puder → o bloco é COMPROVADAMENTE irrelevante para
          esta cadeia específica: remove-o e segue — é isto que mata o
          falso alarme do BL-353 (`@media (max-width: 48rem) {
          .tabela-dados { display: block } }`, que não menciona marca
          nem timbre) sem alargar exceção nenhuma.
       c. BL-360: mesmo sem interseção de identificadores, um bloco cujo
          `seletor_nao_modelado` não é `None` (alguma regra interna
          declara propriedade de interesse com um seletor que a
          gramática deste motor não sabe ler — `[atributo]`, `*`,
          `:is(`/`:where(`/`:not(`, combinador diferente de espaço)
          TAMBÉM reprova pedindo extensão: "não menciona identificador
          conhecido" não é a mesma coisa que "comprovadamente
          irrelevante" quando o motor não sabe LER o seletor em primeiro
          lugar — ele pode CASAR com a cadeia sem MENCIONAR nada dela
          (`[class]` casa com todo elemento que tenha alguma classe,
          sem nomear nenhuma).

    Um bloco com uma regra irrelevante E uma relevante é RELEVANTE —
    basta uma casar (por identificador OU por seletor não modelado) para
    reprovar."""
    eventos = _eventos_de_nivel_superior(texto)

    declaracoes = [e for e in eventos if isinstance(e, _EventoDeclaracao)]
    assert not declaracoes, (
        f"a simulação de cascata (BL-329/BL-333/BL-351) encontrou at-rule(s) de "
        f"DECLARAÇÃO (sem bloco — ex. @import/@charset/@namespace) {onde}: "
        f"{[d.prelude for d in declaracoes]!r} — ela não sabe se isso muda o "
        f"significado do que vem DEPOIS, e nunca as descarta em silêncio só por "
        f"começarem com '@'; ela PRECISA SER ESTENDIDA antes de confiar no resultado"
    )

    blocos_aninhados = [e for e in eventos if isinstance(e, _EventoBloco) and e.aninhado]
    if not blocos_aninhados:
        return texto

    if exigir_ausencia_total:
        assert not blocos_aninhados, (
            f"a simulação de cascata (BL-329/BL-333) encontrou bloco(s) aninhado(s) "
            f"{onde}, e não sabe avaliá-lo(s): "
            f"{[b.prelude for b in blocos_aninhados]!r} — ela PRECISA SER ESTENDIDA "
            f"antes de confiar no resultado, em vez de julgar (silenciosamente) errado"
        )
        return texto

    identificadores_de_interesse = _identificadores_de_interesse(cadeia)
    a_reprovar = []
    limpo = texto
    for evento in reversed(blocos_aninhados):
        if _prelude_e_media_screen_puro(evento.prelude):
            limpo = limpo[: evento.inicio] + limpo[evento.fim :]
            continue
        identificadores_do_bloco, seletor_nao_modelado = _identificadores_mencionados_no_bloco(
            evento.prelude, evento.corpo
        )
        if seletor_nao_modelado is not None:
            a_reprovar.append(
                f"{evento.prelude!r} (seletor não modelado: {seletor_nao_modelado!r})"
            )
            continue
        if identificadores_do_bloco & identificadores_de_interesse:
            a_reprovar.append(evento.prelude)
            continue
        limpo = limpo[: evento.inicio] + limpo[evento.fim :]

    assert not a_reprovar, (
        f"a simulação de cascata (BL-329/BL-333/BL-343/BL-351/BL-360) encontrou "
        f"bloco(s) aninhado(s) {onde} que não são a exceção nomeada '@media screen' "
        f"e que, ou MENCIONAM identificador(es) da cadeia de interesse, ou declaram "
        f"propriedade de interesse com um seletor que a gramática não sabe LER: "
        f"{a_reprovar!r} — ela PRECISA SER ESTENDIDA antes de confiar no resultado, "
        f"em vez de assumir (silenciosamente) que são irrelevantes"
    )
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
    Devolve (removido: bool, nó_que_resolveu_ou_None).

    BL-351: `cadeia` agora também é propagada para `_preparar_para_
    simulacao` — é dela que a classificação por CONTEÚDO deriva os
    identificadores de interesse (`_identificadores_de_interesse`), em
    vez de uma lista de nomes escrita à mão. A ASSINATURA desta função
    não mudou (continua `(cadeia, css_texto)`) — a informação já estava
    disponível aqui, só precisava ser repassada adiante."""
    antes, dentro, depois = _extrair_bloco_media_print(css_texto)
    antes_limpo = _preparar_para_simulacao(
        antes, onde="antes do @media print", exigir_ausencia_total=False, cadeia=cadeia
    )
    depois_limpo = _preparar_para_simulacao(
        depois, onde="depois do @media print", exigir_ausencia_total=False, cadeia=cadeia
    )
    _preparar_para_simulacao(
        dentro, onde="dentro do @media print", exigir_ausencia_total=True, cadeia=cadeia
    )
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
# (acréscimo ao FIM do arquivo, com o @media print original intocado).
#
# ⚠️ BL-351 (rodada 7): das seis construções que MUDAM o papel, as
# QUATRO que reexibem a MARCA continuam aqui — `.cabecalho__topo` é um
# identificador da CADEIA DA MARCA (`_cadeia_da_marca`), então a
# classificação por CONTEÚDO as considera relevantes e reprova, como
# antes. As DUAS que escondem o TIMBRE DO ESCRITÓRIO foram MOVIDAS para
# `test_bl331_timbre_do_escritorio_no_papel.py`
# (`test_f1_construcoes_que_escondem_o_timbre_reprovam_pedindo_extensao`):
# `.timbre-impressao` não é identificador da cadeia da MARCA — testá-las
# aqui, contra `_cadeia_da_marca()`, deixou de fazer sentido depois que a
# guarda passou a decidir por CONTEÚDO (antes, QUALQUER at-rule aninhada
# fora da exceção nomeada reprovava, não importava o que tivesse dentro;
# hoje, um bloco que só menciona `.timbre-impressao` é comprovadamente
# irrelevante para a cadeia da marca, e a guarda certa PRECISA deixar de
# reprovar por essa cadeia — a propriedade "o timbre não pode ser
# escondido" continua garantida, só que pela guarda que de fato verifica
# essa cadeia). Mover a cobertura para a cadeia CERTA, em vez de manter
# uma asserção que passaria a ser FALSA sob a nova classificação, é
# consequência direta da correção do bloqueador G1 — não perda de
# cobertura: as duas construções continuam obrigatoriamente testadas, só
# que no arquivo cuja cadeia elas de fato afetam.
#
# A sétima (`@media screen`) é a ÚNICA exceção nomeada e continua
# aprovando — coberta acima por
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
    ],
)
def test_f1_construcoes_que_mudam_o_papel_reprovam_pedindo_extensao(
    tmp_path, rotulo, at_rule, seletor, declaracao
):
    """BL-343/F1: as QUATRO construções da tabela do achado (Chromium
    1194 + PDF A4 reais, docs/auditorias/2026-09-19-dl-026-rodada-6.md)
    que reexibem a MARCA DO FORNECEDOR — a guarda ANTIGA tratava como
    "nunca se aplicam à impressão" só porque o prelúdio não continha a
    palavra "print"; a guarda BL-351 (por CONTEÚDO) reprova porque
    `.cabecalho__topo` é identificador da cadeia da marca. Reproduzidas
    sobre uma CÓPIA do `base.css` real (acréscimo ao FIM, o `@media
    print` original intocado — exatamente como o auditor mediu)."""
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


# ---------------------------------------------------------------------------
# BL-351 (bloqueador G1 + MÉDIA G3 da auditoria DL-026, rodada 7,
# docs/auditorias/2026-09-19-dl-026-rodada-7.md): as construções que o
# auditor MEDIU em Chromium/PDF A4 reais fazendo a marca voltar ao papel
# apesar de `1844 passed` — e o falso alarme oposto (G3) que a inversão do
# lado seguro produzia. Reproduzidas sobre uma CÓPIA do `base.css` real
# (acréscimo ao FIM, o `@media print` original intocado — mesmo padrão do
# BL-343/F1), exceto onde o próprio DEFEITO exige alterar texto já
# existente (a lista de ocultos, para o CSS Nesting reexibir por
# especificidade — igual a `test_sabotagem_regra_mais_especifica_depois_
# reexibindo_mata_a_guarda`).
# ---------------------------------------------------------------------------


def test_sabotagem_css_nesting_nativo_sem_arroba_reexibe_a_marca_mata_a_guarda(tmp_path):
    """G1 — a construção EXATA que o auditor mediu: `.cabecalho {
    .cabecalho__topo { display: flex } }`, CSS Nesting NATIVO (sem `@`
    nenhum, a forma recomendada de escrever CSS hoje). Antes do BL-351, o
    detector só abria o laço em `if texto[i] == "@"` — este bloco nunca
    era visto, era içado pela extração flat como regra comum, e a marca
    voltava ao papel com `1844 passed`. Acrescentado ao FIM do arquivo
    (fora do `@media print`, que continua intocado) — precisa REPROVAR
    pedindo extensão: `.cabecalho`/`.cabecalho__topo` são identificadores
    da cadeia da marca, e a simulação não sabe avaliar aninhamento nenhum
    fora da exceção nomeada."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = ".cabecalho {\n    .cabecalho__topo {\n        display: flex;\n    }\n}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_sabotagem_css_nesting_com_e_comercial_reexibe_a_marca_mata_a_guarda(tmp_path):
    """DE-055 — construção MINHA, que o relatório do auditor NÃO nomeou:
    a MESMA reexibição da marca, mas escrita com o combinador `&`
    explícito (`.cabecalho { & .cabecalho__topo { display: flex } }`) —
    a forma que ferramentas de build/linters de CSS Nesting costumam
    preferir, e que é semanticamente IDÊNTICA à forma nua acima. Precisa
    MATAR pela MESMA razão: `_identificadores_do_seletor` ignora o `&`
    (não é letra nem começa com `.`) e ainda assim encontra
    `cabecalho__topo` no restante do composto."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = ".cabecalho {\n    & .cabecalho__topo {\n        display: flex;\n    }\n}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_sabotagem_layer_reexibe_a_marca_mata_a_guarda(tmp_path):
    """DE-055 — construção MINHA: `@layer tardio { .cabecalho__topo {
    display: flex } }`. `@layer` nomeada não fala de mídia NENHUMA — vale
    SEMPRE, inclusive ao imprimir (BL-343 já reprova `@layer` sem nome;
    esta prova a variante COM nome, que muda o PRELÚDIO mas não a
    conclusão: nem a exceção nomeada nem a classificação por conteúdo
    dependem do nome da camada, só do que está DENTRO do bloco)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = "@layer tardio {\n    .cabecalho__topo {\n        display: flex;\n    }\n}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_sabotagem_import_antes_de_regra_relevante_reprova_pedindo_extensao(tmp_path):
    """G1 — a terceira construção que o relatório nomeou: `@import
    url(...)` ANTES de uma regra relevante. Reproduz o defeito EXATO: a
    regex gulosa de `_extrair_regras_flat` (`([^{}]+)\\{([^{}]*)\\}`)
    colava `@import url(...);` ao seletor SEGUINTE — aqui,
    `.cabecalho__topo { display: flex; }`, que REEXIBE a marca — e a
    regra colada começava com `@`, então `_extrair_regras_flat` a
    descartava por INTEIRO, em silêncio: a regra que reexibia a marca
    desaparecia junto, e a guarda aprovava por engano (falso "escondido").
    Com `_eventos_de_nivel_superior` isolando o `@import ...;` como um
    evento PRÓPRIO (`_EventoDeclaracao`) ANTES da extração flat rodar,
    `_preparar_para_simulacao` reprova pedindo extensão assim que encontra
    a declaração — nunca deixa a regra seguinte, relevante, desaparecer
    sem aviso."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = '@import url("outro.css");\n.cabecalho__topo {\n    display: flex;\n}\n'
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_media_screen_puro_com_marca_dentro_continua_aprovando(tmp_path):
    """Do relatório do auditor — precisa PASSAR: `@media screen {
    .cabecalho__topo { display: flex } }`. `screen` exclui `print` por
    definição — a ÚNICA exceção nomeada, removida sem olhar para dentro,
    mesmo mencionando um identificador da cadeia de interesse (a exceção
    nomeada vem ANTES da classificação por conteúdo, nunca depois — ver a
    ordem na docstring de `_preparar_para_simulacao`)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = "@media screen {\n    .cabecalho__topo {\n        display: flex;\n    }\n}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    removido, _ = _algum_ancestral_removido_do_papel(cadeia, css_mutado)
    assert removido is True, (
        "@media screen legítimo, mencionando .cabecalho__topo, não deveria fazer a "
        "guarda reprovar nem deixar de detectar a ocultação real (do @media print "
        "intocado) — e ela deveria continuar vendo a marca escondida"
    )


@pytest.mark.parametrize(
    "rotulo,at_rule,seletor,declaracao",
    [
        (
            "media query real e irrelevante (G3, do relatório)",
            "@media (max-width: 48rem)",
            ".tabela-dados",
            "display: block;",
        ),
        (
            "media query irrelevante (DE-055)",
            "@media (min-width: 60rem)",
            ".grade-formulario",
            "display: grid;",
        ),
    ],
)
def test_bloco_irrelevante_por_conteudo_nao_reprova(tmp_path, rotulo, at_rule, seletor, declaracao):
    """G3 (BL-353): o lado seguro invertido do BL-343 reprovava QUALQUER
    at-rule aninhada fora de `@media screen`, sem olhar para dentro —
    `@media (max-width: 48rem) { .tabela-dados { display: block } }`
    (que não menciona marca nem timbre) produzia 19 `failed`. A
    classificação por CONTEÚDO (BL-351) resolve o G1 e o G3 pela MESMA
    mudança: nenhum identificador de `.tabela-dados`/`.grade-formulario`
    está na cadeia da marca, então os dois blocos são comprovadamente
    IRRELEVANTES e são removidos — a guarda PASSA, e continua detectando
    a ocultação real (do `@media print` intocado)."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = f"{at_rule} {{\n    {seletor} {{\n        {declaracao}\n    }}\n}}\n"
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    removido, _ = _algum_ancestral_removido_do_papel(cadeia, css_mutado)
    assert removido is True, (
        f"{rotulo}: bloco irrelevante por conteúdo não deveria fazer a guarda "
        f"reprovar nem deixar de detectar a ocultação real da marca"
    )


# ---------------------------------------------------------------------------
# BL-360 (ALTA da auditoria DL-026, rodada 8,
# docs/auditorias/2026-09-19-dl-026-rodada-8.md): o auditor furou o BL-351
# por outro eixo — seletor que CASA com a cadeia sem MENCIONAR
# identificador nenhum dela. Medido em Chromium 1194 real, com
# `emulate_media("print")`, sobre a cadeia real da marca e o `base.css`
# real: `[class] { display: block }` e `@media (min-width: 1px) { [class]
# { display: block } }` faziam a marca voltar ao PAPEL DE VERDADE enquanto
# a guarda aprovava. A correção: `_residuo_nao_reconhecido_do_composto`
# apara do composto o que a gramática RECONHECE e recusa julgar sobre o
# que sobra — nunca enumera o que ela NÃO reconhece.
# ---------------------------------------------------------------------------


def test_bl360_sem_sabotagem_continua_aprovando():
    """Controle (linha 1 da tabela do BL-360, sem sabotagem nenhuma): a
    guarda continua aprovando o `base.css` real — prova de que a recusa
    por gramática não modelada não virou falso alarme."""
    _, cadeia = _cadeia_da_marca()
    removido, _ = _algum_ancestral_removido_do_papel(cadeia, _BASE_CSS.read_text(encoding="utf-8"))
    assert removido is True, (
        "controle: o CSS real precisa continuar aprovando SEM sabotagem nenhuma"
    )


def test_bl360_base_css_real_nao_tem_seletor_nao_modelado_com_display():
    """Confirmação PRÓPRIA (o arquiteto pediu: "confira esse número você
    mesmo antes de confiar nele") de que a recusa por gramática não
    modelada dispara ZERO vezes sobre o `static/css/base.css` REAL hoje —
    os cinco seletores de atributo (`[tabindex]`, `a[aria-current=...]`,
    `th[scope=...]`, `input[type="date"]`, `input[name^="valor_"]`) e o
    universal (`*`) que o arquivo tem HOJE não declaram `display` nenhum.
    Varre TODO bloco do arquivo (dentro e fora do `@media print`,
    recursivamente) e conta quantas regras declaram propriedade de
    interesse com seletor de gramática não reconhecida — precisa ser
    ZERO. Se este teste um dia falhar, é porque `base.css` mudou, não
    porque a guarda está errada; PARE e avise, não alargue a recusa."""
    css_texto = _remover_comentarios(_BASE_CSS.read_text(encoding="utf-8"))

    def _contar_seletores_nao_modelados_com_interesse(texto):
        total = 0
        for evento in _eventos_de_nivel_superior(texto):
            if isinstance(evento, _EventoBloco):
                if (
                    not evento.prelude.startswith("@")
                    and _corpo_declara_propriedade_de_interesse(
                        _texto_de_declaracoes_diretas(evento.corpo)
                    )
                    and _seletor_bruto_tem_construcao_nao_modelada(evento.prelude)
                ):
                    total += 1
                total += _contar_seletores_nao_modelados_com_interesse(evento.corpo)
        return total

    total = _contar_seletores_nao_modelados_com_interesse(css_texto)
    assert total == 0, (
        f"esperava ZERO seletores não modelados declarando propriedade de interesse "
        f"no base.css real, e achei {total} — o número mudou; confira ANTES de "
        f"confiar nele, não alargue a recusa por conveniência"
    )


@pytest.mark.parametrize(
    "rotulo,bloco_css",
    [
        (
            "universal dentro de @layer nomeada (relatório do auditor)",
            "@layer tardio {\n    * {\n        display: block;\n    }\n}\n",
        ),
        (
            "seletor de atributo, nível superior (relatório do auditor)",
            "[class] {\n    display: block;\n}\n",
        ),
        (
            "pseudo-classe funcional :where (relatório do auditor)",
            ":where(.cabecalho__topo) {\n    display: block;\n}\n",
        ),
        (
            "pseudo-classe funcional :is (relatório do auditor)",
            ":is(.cabecalho__topo, .rodape) {\n    display: block;\n}\n",
        ),
        (
            "seletor de atributo dentro de @media real (relatório do auditor)",
            "@media (min-width: 1px) {\n    [class] {\n        display: block;\n    }\n}\n",
        ),
        (
            "combinador filho '>' (DE-055)",
            ".cabecalho > .cabecalho__topo {\n    display: flex;\n}\n",
        ),
        (
            "pseudo-classe funcional :not (DE-055)",
            ".cabecalho__topo:not(.oculto) {\n    display: flex;\n}\n",
        ),
    ],
)
def test_bl360_seletor_nao_modelado_com_propriedade_de_interesse_reprova(
    tmp_path, rotulo, bloco_css
):
    """BL-360: as CINCO construções da tabela do achado (Chromium 1194 +
    `emulate_media("print")` reais) mais as DUAS de DE-055 — todas
    declaram `display` com um seletor que a gramática deste motor não
    reconhece (seletor de atributo, universal, pseudo-classe funcional,
    combinador diferente de espaço). Precisam recusar julgar (`PRECISA
    SER ESTENDIDA`), nomeando o seletor — nunca aprovar por acidente
    aritmético nem por `all([])` de uma lista vazia de exigências."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    assert css_mutado != css_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    with pytest.raises(AssertionError, match="PRECISA SER ESTENDIDA"):
        _algum_ancestral_removido_do_papel(cadeia, css_mutado)


def test_bl360_seletor_de_atributo_sem_propriedade_de_interesse_nao_reprova(tmp_path):
    """DE-055 — construção MINHA: `.tabela-dados input[type="date"] {
    border: 0 }` tem seletor de atributo (gramática não modelada), mas
    NÃO declara `display`. A recusa é ESCOPADA por propriedade de
    interesse (item 4 do pedido do arquiteto): este seletor continua
    irrelevante para a guarda, do jeito que sempre foi — ela nunca
    precisou entender a gramática de uma propriedade que não julga.
    Prova de que a correção não vira o `base.css` real vermelho."""
    _, cadeia = _cadeia_da_marca()
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    bloco_css = '.tabela-dados input[type="date"] {\n    border: 0;\n}\n'
    caminho_mutado = tmp_path / "base-mutado.css"
    css_mutado = css_original + "\n\n" + bloco_css
    caminho_mutado.write_text(css_mutado, encoding="utf-8")

    removido, _ = _algum_ancestral_removido_do_papel(cadeia, css_mutado)
    assert removido is True, (
        "seletor de atributo que NÃO declara propriedade de interesse não deveria "
        "fazer a guarda recusar julgar nem deixar de detectar a ocultação real"
    )
