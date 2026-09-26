"""Varredura de interface — o mecanismo que transforma a direção de arte em
regra, e não em pedido.

**Por que este arquivo existe.** A [direção de arte](docs/projeto/direcao-de-arte.md)
foi escolhida por medição, num gauntlet de três variantes (DE-053/RC-90). Mas o
produto vai ganhar Fiscal, Folha, Honorários, Paralegal e Lalur, e **um sistema
contábil que muda de cara a cada módulo obriga o usuário a reaprender a ler**.
Documento de padrão que ninguém verifica vira decoração em seis meses — este
projeto já viu isso acontecer com o estado, que precisou de
``test_documentacao_do_estado.py`` para parar de divergir.

**O que esta varredura NÃO faz, e é importante dizer.** Ela é estática: lê
template e folha de estilo. Ela **não** renderiza, não mede contraste, não mede
densidade e não sabe se a tela é bonita. O que se mede em navegador está no
juiz do gauntlet (``docs/assets/design/gauntlet/juiz.py``), que roda fora da
integração contínua porque exige Chromium. Aqui ficam só as regras que dá para
provar lendo o arquivo — e cada uma delas nasceu de um defeito real.

**Cada guarda tem controle positivo.** O projeto aprendeu na marra (BL-271) que
teste que não morre quando a defesa é removida não é guarda, é enfeite: um
teste da DL-023 comparava dois literais entre si e passaria igual com o defeito
de volta. Por isso, aqui, cada detector é exercitado contra uma entrada
propositalmente inválida no mesmo arquivo.

**Rodada 2 (BL-274, achado A1 da auditoria de 2026-09-18).** O auditor atacou
esta própria varredura por sabotagem, em cópia, e seis formas de violação
passaram batido: cor nomeada (`red`, `white`); CSS em subpasta de
`static/css/`; CSS fora de `static/css/`; `style='...'` com aspas simples e
`<style>` embutido; valor que chega à célula por `{% include %}` sem o sufixo
`_ptbr` literal no texto do template chamador; e módulo cuja linha sumiu da
tabela do §3 enquanto o nome sobrevivia em prosa em outro lugar do documento.
Mais o detector de medida literal que o critério 13 prometia e nunca existiu.
Cada uma virou detector nomeado abaixo, com controle positivo **e** negativo —
a mesma exigência que este arquivo já fazia de si mesmo.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.conf import settings as django_settings

from apps.core.marcacao import atributos_da_tag
from apps.core.marcacao import tem_classe as _tem_classe

RAIZ = Path(__file__).resolve().parents[3]
# BL-309 (A3 da auditoria DL-026 rodada 3): `TEMPLATES = RAIZ / "templates"`
# existia aqui e alimentava só a guarda do "momento da verdade" — a única
# que ainda enumerava a pasta antiga em vez de `_templates(RAIZ)`. Sem mais
# usos depois da correção (ver `_pastas_de_modulo_com_tela`), removida:
# mantê-la seria código morto e um convite a alguém voltar a usá-la por
# engano no lugar de `_templates`.
ESTILOS = RAIZ / "static" / "css"
DIRECAO_DE_ARTE = RAIZ / "docs" / "projeto" / "direcao-de-arte.md"

# Pastas de `templates/` que NÃO são módulo de negócio e por isso não precisam
# de linha na tabela do "momento da verdade". Cada uma com o motivo escrito: a
# lição da DL-023 é que superfície sem decisão registrada é o defeito, e
# "estava lá antes" não é decisão.
PASTAS_QUE_NAO_SAO_MODULO = {
    "erros": "páginas de erro do próprio sistema, sem documento de negócio",
    "registration": "entrada no sistema (login), fornecida pelo Django",
    "tenancy": "escritório e vínculo de usuário: infraestrutura de isolamento",
    "empresas": "cadastro central compartilhado, não é módulo de rotina",
}

# Pastas do repositório que NUNCA guardam CSS do produto, mesmo quando têm
# `.css` de verdade dentro — cada uma com o motivo, no mesmo padrão de
# `PASTAS_QUE_NAO_SAO_MODULO`. Sem esta lista, a varredura recursiva (BL-274
# #2/#3) sairia catalogando o admin do Django coletado em `staticfiles/`.
#
# O ambiente virtual Python NÃO está aqui por NOME (ver `_dentro_de_ambiente_virtual`
# abaixo) — achado do arquiteto-senior na revisão desta etapa: o `.gitignore`
# do projeto autoriza `.venv/` **e** `venv/` (linhas 6-7), e uma lista de
# nomes só resolve o apelido que alguém já viu. `staticfiles/` e `.git/` não
# têm um marcador de comportamento equivalente a `pyvenv.cfg`, por isso
# continuam aqui, por nome, com o motivo.
PASTAS_SEM_CSS_DO_PROJETO = {
    "staticfiles": "saída do collectstatic — cópia GERADA, gitignored; não é a fonte",
    ".git": "metadados do controle de versão",
}

# Convenção do projeto: valor formatado em pt-BR chega ao template com sufixo
# `_ptbr`. Nem todo `_ptbr` é dinheiro — data também usa —, por isso a regra
# vale dentro de CÉLULA DE TABELA, que é onde a coluna de valor mora.
#
# BL-274 #1/#5: antes o padrão só via `{{ ..._ptbr }}` interpolado direto na
# célula. `templates/contabilidade/_saldo.html` (parcial reaproveitada pelo
# Razão) mostrou a rota de fuga real: o valor viaja como
# `{% include "_saldo.html" with valor=item.saldo_ptbr %}` — o `_ptbr` está no
# texto do template chamador (como argumento do `with`), só que fora de
# `{{ }}`. Reduzir o padrão a "existe `_ptbr` em algum lugar do texto" cobre
# os dois casos com a mesma regra, sem precisar resolver o `{% include %}`
# de verdade: o que importa é que remover a classe da célula QUE CHAMA o
# parcial continue reprovando, e com o padrão antigo isso nunca disparava,
# porque a célula do Razão nunca continha um `{{ ..._ptbr }}` literal.
PADRAO_VALOR = re.compile(r"_ptbr\b")
PADRAO_CELULA = re.compile(r"<(td|th)\b[^>]*>", re.IGNORECASE)

# BL-319 (M1 da auditoria DL-026 rodada 4): esta lista era fechada em TRÊS
# famílias de função (`rgba?`/`hsla?`/hex) — a MESMA lista fechada que o
# detector IRMÃO, de medida (logo abaixo, `_PADRAO_MEDIDA_LITERAL`),
# abandonou NESTA MESMA rodada (BL-313), com o comentário dizendo, com
# todas as letras, que "um detector que ENUMERA casos relatados está
# condenado a ficar sempre uma auditoria atrás". `oklch()`/`lab()`/
# `hwb()` passavam batido — `oklch()`, em particular, não é caso exótico:
# é a notação RECOMENDADA hoje para paleta perceptualmente uniforme, e é
# o que a próxima pessoa que mexer no `base.css` vai escrever.
#
# A correção, no mesmo espírito da inversão do lado da medida: em vez de
# lembrar cada função relatada, enumerar a lista COMPLETA e ESTÁVEL das
# funções de cor do CSS Color Module Level 4/5
# (w3.org/TR/css-color-4, w3.org/TR/css-color-5) — a mesma classe de
# "enumeração que não fica atrás" que `_PADRAO_MEDIDA_LITERAL` já usa para
# as UNIDADES. `(?<![\w-])` evita casar uma função de cor no MEIO de um
# nome maior (o mesmo cuidado de `PADRAO_ESTILO_EMBUTIDO`, abaixo) — por
# exemplo, uma variável `--acento-oklch-alt` não pode disparar o detector
# só por conter a substring "oklch".
PADRAO_COR = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|(?<![\w-])rgba?\([^)]*\)"
    r"|(?<![\w-])hsla?\([^)]*\)"
    r"|(?<![\w-])hwb\([^)]*\)"
    r"|(?<![\w-])lab\([^)]*\)"
    r"|(?<![\w-])lch\([^)]*\)"
    r"|(?<![\w-])oklab\([^)]*\)"
    r"|(?<![\w-])oklch\([^)]*\)"
    r"|(?<![\w-])color-mix\([^)]*\)"
    r"|(?<![\w-])color-contrast\([^)]*\)"
    r"|(?<![\w-])device-cmyk\([^)]*\)"
    r"|(?<![\w-])color\([^)]*\)"
)

# Rodada 3 (BL-286, achado do arquiteto-senior): a exigência de
# `valor-monetario` não pode ficar presa à CÉLULA — o BL-286 misturou frase
# e número na mesma célula do veredito de fechamento ("Não fecha, faltam X
# no crédito"), e marcar a célula inteira com a classe alinharia a FRASE
# toda à direita, em fonte tabulada, o que é absurdo (a classe existe para
# tabular ALGARISMO, não texto corrido). A tabulação pertence ao NÚMERO:
# um invólucro em linha (`<span class="valor-monetario">`) só ao redor do
# valor passa a satisfazer a regra também. `PADRAO_TAG_ABERTURA` localiza
# qualquer tag de abertura genérica (não só `td`/`th`) para procurar esse
# invólucro — ver `_involucro_cobre_valor` abaixo.
PADRAO_TAG_ABERTURA = re.compile(r"<([a-zA-Z][\w-]*)\b[^>]*>")

# Sabotagem 3 da rodada 3 (BL-286): a checagem original, escrita na rodada 2
# (revisão `3941452`) e copiada hoje para o caminho do invólucro, era
# `"valor-monetario" in tag` — SUBSTRING pura sobre o texto inteiro da tag.
# `class="valor-monetario-legenda"` CONTÉM a string `valor-monetario` e
# passava, sendo uma classe CSS diferente (o seletor `.valor-monetario` do
# CSS não casa `.valor-monetario-legenda` — são duas classes distintas). É
# a MESMA família de defeito do BL-274 #6 (substring no lugar de casamento
# de TOKEN) — ali era o nome do módulo num documento inteiro, aqui é o nome
# da classe dentro do atributo `class`.
#
# BL-310 (M1 da auditoria DL-026 rodada 3): `_tem_classe` (e o padrão que a
# alimentava) era uma cópia local de `apps.core.marcacao.tem_classe`,
# criado exatamente para acabar com essa duplicação (ver o docstring
# daquele módulo) — o próprio docstring dele PROMETIA que "a varredura vai
# passar a importar daqui" e a cópia local continuava, sem que ninguém
# tivesse ligado os dois. Agora importa de verdade (topo do arquivo): um
# defeito de casamento de atributo corrigido em `apps.core.marcacao` (como
# o de atributo SEM ASPAS, achado nesta mesma rodada) passa a valer aqui
# também, sem precisar de uma segunda correção manual.


# Mesma família, no atributo `scope` do `<th>` (`_cabecalhos_sem_escopo`
# abaixo): a checagem original era `"scope=" not in tag`, e um atributo
# como `data-scope="x"` ou `aria-scope="x"` CONTÉM a substring `scope=` e
# fazia a guarda pensar que o `<th>` tinha declarado `scope` de verdade.
# `\s` obrigatório antes de `scope` garante que é o NOME do atributo, não
# o final de um nome maior conectado por hífen.
_PADRAO_ATRIBUTO_SCOPE = re.compile(r"\sscope\s*=", re.IGNORECASE)

# Achado 2 da revisão do arquiteto-senior sobre o `PADRAO_VALOR` acima: a
# amplitude fica (ela é o que fecha a cegueira do `{% include %}`), mas a
# MENSAGEM não pode instruir alguém a colocar `valor-monetario` numa DATA.
# `_ptbr` não é exclusivo de dinheiro — `lancamento_form.html:80` já formata
# data com esse sufixo, hoje fora de célula. No dia em que um módulo novo
# puser `<td>{{ nota.emissao_ptbr }}</td>`, a guarda vai acusar de verdade
# (correto: é `_ptbr` dentro de célula sem a classe) e a mensagem tem de
# oferecer as DUAS saídas certas, não só "adicione a classe".
MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE = (
    "Se a célula é dinheiro, acrescente a classe 'valor-monetario'. Se NÃO é "
    "(ex.: data formatada com o sufixo _ptbr, que a convenção também usa), "
    "ela não devia carregar um valor com sufixo _ptbr dentro de célula de "
    "tabela — repense a variável, ou traga o caso ao arquiteto-senior como "
    "exceção nomeada, com o motivo."
)

# Cores nomeadas do CSS Color Module (níveis 3/4) — lista fechada, em
# minúsculas. BL-274 #2: `PADRAO_COR` só via `#hex`/`rgb()`/`hsl()`; `color:
# red;` e `background: white;` eram invisíveis.
CORES_NOMEADAS_CSS = frozenset(
    """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black
    blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse
    chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta
    darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet
    deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite
    forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray grey green
    greenyellow honeydew hotpink indianred indigo ivory khaki lavender
    lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink
    lightsalmon lightseagreen lightskyblue lightslategray lightslategrey
    lightsteelblue lightyellow lime limegreen linen magenta maroon
    mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
    mediumslateblue mediumspringgreen mediumturquoise mediumvioletred
    midnightblue mintcream mistyrose moccasin navajowhite navy oldlace
    olive olivedrab orange orangered orchid palegoldenrod palegreen
    paleturquoise palevioletred papayawhip peachpuff peru pink plum
    powderblue purple rebeccapurple red rosybrown royalblue saddlebrown
    salmon sandybrown seagreen seashell sienna silver skyblue slateblue
    slategray slategrey snow springgreen steelblue tan teal thistle tomato
    turquoise violet wheat white whitesmoke yellow yellowgreen
    """.split()
)

# Palavras-chave de CSS que PARECEM cor mas não são tinta — exceção nomeada,
# com o motivo, como o projeto já faz em `PASTAS_QUE_NAO_SAO_MODULO`.
NOMES_QUE_NAO_SAO_TINTA = {
    "transparent": "ausência de cor, não uma tinta — usado no próprio base.css",
    "currentcolor": "referência à cor de texto já resolvida, não uma tinta nova",
    "inherit": "herda o valor do elemento pai; não introduz cor",
    "initial": "volta ao valor inicial da propriedade; não introduz cor",
    "unset": "remove a declaração; não introduz cor",
    "revert": "volta ao estilo do navegador/UA; não introduz cor",
}

# BL-335 (M3 da auditoria DL-026 rodada 5): a lição do BL-319 ("um detector
# de cor não pode ficar preso a uma lista de casos relatados") tinha sido
# aplicada só às FUNÇÕES de cor (`PADRAO_COR`, acima) — o lado das cores
# NOMEADAS continuava usando `CORES_NOMEADAS_CSS`, que é o vocabulário do
# CSS Color Module Level **3**. `Canvas`, `ButtonFace`, `AccentColor`,
# `LinkText`... são do Level **4**, seção "CSS System Colors"
# (w3.org/TR/css-color-4/#css-system-colors), e não estavam em NENHUM dos
# dois padrões. `.sabotagem { color: Canvas; }` dava "1715 passed".
#
# Por que isto continua sendo LISTA e não INVERSÃO (ao contrário do que
# `PADRAO_COR`/`_PADRAO_MEDIDA_LITERAL` fizeram com as funções/unidades): a
# seção 8.1 do CSS Color Level 4 é um vocabulário FECHADO e ENUMERADO por
# especificação — dezenove palavras-chave, nem uma a mais —, ao contrário de
# uma função de cor (que aceita qualquer combinação de números: não há como
# "inverter o lado" de um domínio contínuo). Enumerar aqui é o que a própria
# especificação faz. O que MUDA quando o Level 5 (ou uma revisão do Level 4)
# acrescentar palavras-chave novas: esta lista fica desatualizada como
# `CORES_NOMEADAS_CSS` já fica hoje para o Level 4 — a mesma classe de
# limitação, sempre existiu, sempre vai existir para vocabulário fechado por
# nome. Quando isso acontecer, a entrada nasce aqui, nomeada, com a data e a
# seção da especificação — nunca por engano.
#
# F4 da auditoria DL-026 rodada 6 (docs/auditorias/2026-09-19-dl-026-rodada-6.md):
# a exclusão do §8.2 era mesmo DECISÃO DELIBERADA, com o motivo CERTO —
# risco de colidir com um IDENTIFICADOR legítimo do projeto
# (`animation-name: menu-open` tokeniza em "menu" e "menu" bateria) — mas
# aplicada só ao conjunto que ficou de FORA. O auditor mediu: o MESMO risco
# já valia para palavra do §8.1 que já estava DENTRO — `highlight`
# (`animation-name: highlight-row`), `mark` (`animation-name: mark-in`,
# `view-transition-name: mark`), `canvas` (`grid-area: canvas`), `field`
# (`font-family: Field Sans`) — cinco falsos alarmes REAIS, porque o
# detector varria QUALQUER declaração `propriedade: valor`, nunca só as que
# aceitam cor. `highlight`/`mark`/`field`/`canvas` são tão palavra do inglês
# comum quanto `menu`/`window`; a diferença nunca esteve na PALAVRA, esteve
# em ONDE ela aparece — e essa segunda pergunta não estava sendo feita.
#
# A correção (`_propriedade_aceita_cor`, logo abaixo de `MOTIVO_COR_DE_
# SISTEMA`): restringir a varredura às propriedades que aceitam cor —
# `color`, `background` e derivadas, `border-*-color`, `outline-color`,
# `fill`, `stroke`, `caret-color`, `text-decoration-color`,
# `column-rule-color`, `accent-color`, `box-shadow`, `text-shadow`, entre
# outras justificadas ali. Isso elimina os cinco falsos alarmes SEM lista de
# exceção de PALAVRA — e com isso o motivo para excluir o §8.2 desaparece:
# `Menu`/`Window`/`ActiveBorder`/`InactiveCaptionText`/`ThreeDFace`
# renderizam no navegador com o MESMO contraste não calculável do §8.1, e só
# entram na varredura onde `color`/`background`/`border-color`/
# `outline-color` etc. os declaram — nunca em `animation-name`/`grid-area`/
# `font-family`/`view-transition-name`. O §8.2 entra INTEIRO abaixo.
CORES_DE_SISTEMA_ATUAIS_CSS = frozenset(
    """
    accentcolor accentcolortext activetext buttonborder buttonface
    buttontext canvas canvastext field fieldtext graytext highlight
    highlighttext linktext mark marktext selecteditem selecteditemtext
    visitedtext
    """.split()
)

# §8.2 "Deprecated System Colors" (w3.org/TR/css-color-4/#deprecated-
# system-colors) — vinte e três palavras-chave, o mesmo vocabulário FECHADO
# e ENUMERADO por especificação que já justificava `CORES_DE_SISTEMA_
# ATUAIS_CSS` ser lista em vez de inversão (ver o comentário do BL-335,
# acima: um domínio contínuo se inverte, um vocabulário fechado por
# especificação se enumera). "Deprecated" aqui é a especificação marcando o
# uso como desaconselhado em página pública nova — não removendo a
# palavra-chave da linguagem: todo navegador atual continua resolvendo
# `Menu`/`Window`/... para uma cor de tema real, com o MESMO problema de
# contraste não calculável do §8.1.
CORES_DE_SISTEMA_DEPRECIADAS_CSS = frozenset(
    """
    activeborder activecaption appworkspace background buttonhighlight
    buttonshadow captiontext inactiveborder inactivecaption
    inactivecaptiontext infobackground infotext menu menutext scrollbar
    threeddarkshadow threedface threedhighlight threedlightshadow
    threedshadow window windowframe windowtext
    """.split()
)

CORES_DE_SISTEMA_CSS = CORES_DE_SISTEMA_ATUAIS_CSS | CORES_DE_SISTEMA_DEPRECIADAS_CSS

# Mensagem da CATEGORIA PRÓPRIA (não "mais uma cor proibida"): o motivo pelo
# qual cor de sistema é pior que hex errado é que ela não tem valor fixo, e
# por isso o par texto/fundo que ela forma não é MEDÍVEL — quem ler a
# reprovação daqui a seis meses precisa entender a diferença, não só saber
# que `Canvas` está numa lista.
MOTIVO_COR_DE_SISTEMA = (
    "é uma cor de SISTEMA (CSS Color Level 4, seção 'CSS System Colors'): o "
    "valor dela é decidido pelo sistema operacional e pelo tema do usuário, "
    "não pelo projeto. Diferente de um hexadecimal errado (que é medível), o "
    "par texto/fundo que ela forma não tem contraste CALCULÁVEL — o critério "
    "de contraste da DE-053 deixa de valer para aquele par, sem que nada "
    "avise. Substitua por um token de tinta do :root."
)

# F4 da auditoria DL-026 rodada 6: o filtro que faltava em
# `_cores_de_sistema_fora_dos_tokens` — cor de sistema só pode aparecer onde
# a propriedade ACEITA cor. Sem isto, `re.findall(r"[a-zA-Z]+", valor)`
# lia QUALQUER declaração (`animation-name: highlight-row`, `grid-area:
# canvas`, `font-family: Field Sans`, `view-transition-name: mark`) como se
# fosse uma lista de cores candidatas.
#
# `PROPRIEDADES_ATALHO_QUE_ACEITAM_COR` é a lista NOMEADA e comentada — no
# padrão de `NOMES_QUE_NAO_SAO_TINTA`/`PASTAS_QUE_NAO_SAO_MODULO` deste
# arquivo — dos atalhos que aceitam cor SEM terminar em "color" no nome:
# `background`/`border`(+ quatro lados + dois eixos lógicos)/`outline`/
# `column-rule` são propriedades de ATALHO cujo valor mistura largura,
# estilo de linha E cor no mesmo lugar; `box-shadow`/`text-shadow` têm cor
# como o ÚLTIMO componente da lista de valores; `text-decoration`/
# `text-emphasis` são atalho da variante `-color`; `fill`/`stroke` são a
# pintura do SVG (w3.org/TR/SVG2/, "Presentation attributes"). Tudo o que
# TERMINA em "color" (`color`, `background-color`, `border-color` e as oito
# variantes por lado/eixo lógico, `outline-color`, `caret-color`,
# `accent-color`, `text-decoration-color`, `text-emphasis-color`,
# `column-rule-color`, `scrollbar-color`, e as três de pintura do SVG —
# `stop-color`/`flood-color`/`lighting-color`) é reconhecido por SUFIXO, sem
# precisar enumerar cada combinação — e sem casar `color-scheme`,
# `forced-color-adjust` nem `print-color-adjust`, que CONTÊM "color" mas não
# TERMINAM com ele, e nenhuma delas aceita uma palavra-chave de cor de
# sistema como valor.
PROPRIEDADES_ATALHO_QUE_ACEITAM_COR = frozenset(
    """
    background border border-top border-right border-bottom border-left
    border-block border-block-start border-block-end
    border-inline border-inline-start border-inline-end
    outline column-rule box-shadow text-shadow text-decoration text-emphasis
    fill stroke
    """.split()
)


def _propriedade_aceita_cor(nome):
    """`True` se a propriedade CSS `nome` aceita um valor de cor — o filtro
    da correção do achado F4 (auditoria DL-026 rodada 6): termina em
    "color" (ver o comentário de `PROPRIEDADES_ATALHO_QUE_ACEITAM_COR` para
    a lista coberta por sufixo) ou está na lista NOMEADA de atalhos que
    aceitam cor sem "color" no nome."""
    nome = nome.strip().lower()
    return nome.endswith("color") or nome in PROPRIEDADES_ATALHO_QUE_ACEITAM_COR


# Estilo embutido: `style="..."` (aspas duplas), `style='...'` (BL-274 #5,
# aspas simples escapavam), `style=valor-sem-aspas` (M1/BL-292, auditoria
# DL-026 rodada 2 — HTML5 aceita atributo sem aspas desde que o valor não
# tenha espaço, aspas, `=`, `<`, `>` nem crase, e o Chromium aplica: `<td
# style=color:red;font-size:22px>` renderizava vermelho de verdade e
# escapava, ao mesmo tempo, deste detector, do de cor e do de medida — a
# tríade inteira do critério 13, com uma sabotagem só) e `<style>...</style>`
# embutido no template.
#
# `(?<![\w-])` na frente de `style` fecha o FALSO POSITIVO que o commit
# `d8ec169` registrou como impossível e não era: sem o lookbehind, o padrão
# batia dentro de `data-style="cor"` (a substring `style="cor"` está
# LITERALMENTE contida em `data-style="cor"`) porque `re.search` não exige
# que o casamento comece no início do atributo. O lookbehind nega qualquer
# caractere de palavra ou hífen imediatamente antes de `style`, então
# `data-style=`/`aria-style=` (terminam em "-style") não casam, mas
# `style=` no início de atributo (depois de espaço, `<` ou início da
# string) casa normalmente.
PADRAO_ESTILO_EMBUTIDO = re.compile(
    r"""
    (?<![\w-]) style \s* = \s* (?: "[^"]*" | '[^']*' | [^\s"'=<>`]+ )
    | <style\b[^>]*>.*?</style>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# Recorte da seção "## 3." da direção de arte, até o próximo "## " — BL-274
# #6: a guarda antiga fazia busca de substring no DOCUMENTO INTEIRO, e
# "Fiscal" sobrevivia em outras quatro frases fora da tabela.
PADRAO_SECAO_MOMENTO_DA_VERDADE = re.compile(r"^## 3\..*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)

# Nome do MÓDULO como ele aparece na tabela do §3, por pasta de `templates/`.
# "contabilidade" é a única pasta real hoje (as demais ainda não existem —
# Fora do escopo da DL-026); as outras chaves são a melhor aproximação do
# nome que os módulos futuros devem usar. Pasta sem entrada aqui cai no
# `.capitalize()` — aproximação, não garantia; quem criar o módulo confere a
# tabela manualmente contra o nome real da pasta.
NOME_DO_MODULO_NA_TABELA = {
    "contabilidade": "Contábil",
    "fiscal": "Fiscal",
    "folha": "Folha",
    "honorarios": "Honorários",
    "paralegal": "Processos/Paralegal",
    "processos": "Processos/Paralegal",
    "lalur": "Lalur/ECF",
    "ecf": "Lalur/ECF",
}

# BL-313 (M4 da auditoria DL-026 rodada 3): até esta correção, o detector só
# acusava dentro de uma LISTA FECHADA de propriedades (`_PADRAO_PROPRIEDADE_
# DE_MEDIDA`, removida nesta rodada). Cada rodada de auditoria encontrava
# propriedades novas fora da lista — `max-width`/`min-width`/`max-height`/
# `min-height` (o `(?<![\w-])` era negado pelo próprio hífen do prefixo
# `max-`/`min-`), `box-shadow`, `flex-basis`, `text-indent`, `column-width`
# — e a correção de cada rodada só acrescentava os nomes relatados,
# deixando a PRÓXIMA propriedade esquecida de fora. O auditor apontou a
# direção certa e o arquiteto concordou: um detector que ENUMERA casos
# relatados está condenado a ficar sempre uma auditoria atrás.
#
# A inversão: qualquer declaração `propriedade: valor;` fora do `:root`
# entra na varredura (a mesma extração de "propriedade: valor" usada pelo
# detector de cor, `_PADRAO_DECLARACAO_COM_PROPRIEDADE` abaixo) — o que
# decide se é achado é só o VALOR conter uma unidade de comprimento
# literal. Propriedades como
# `color`/`content`/`font-family` nunca são acusadas não porque estão fora
# de uma lista, mas porque o VALOR delas não bate com `_PADRAO_MEDIDA_
# LITERAL` — o mesmo raciocínio que já valia para `border-color`/
# `border-style` na lista antiga ("uma cor ou `solid` sozinhos nunca casam
# com `_PADRAO_MEDIDA_LITERAL`"), agora aplicado a TODA propriedade, não só
# às que alguém lembrou de nomear.
#
# `PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL` é o escape nomeado e comentado
# — no padrão de `NOMES_QUE_NAO_SAO_TINTA`/`PASTAS_QUE_NAO_SAO_MODULO` — para
# a propriedade que precisar, de fato, de um valor literal (`static/css/
# base.css` declara, no próprio topo do arquivo, que NENHUMA medida solta
# é aceita fora do `:root`; o auditor confirmou ZERO ocorrências com um
# detector totalmente irrestrito). Vazia por enquanto: se um caso legítimo
# aparecer, ele nasce aqui, nomeado e com o motivo — nunca por engano.
PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL = {}

# Extração de `propriedade: valor;`, capturando os dois grupos (nome e
# valor) — usada pelos detectores de MEDIDA e de COR (BL-321/M3): o nome é
# necessário para consultar `PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL`, para
# reconhecer uma CUSTOM PROPERTY (`--nome`, nunca uma violação — ver o
# docstring de `_cores_fora_dos_tokens`) e para compor a mensagem
# `"propriedade: valor"` que o achado de medida devolve.
_PADRAO_DECLARACAO_COM_PROPRIEDADE = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;{}]+)[;}]")

# `\d*\.?\d+` cobre inteiro e decimal (`4px`, `0.4em`); a unidade é literal,
# nunca `var(...)`. Valores sem unidade (`0`), percentuais (`100%`), `auto`,
# `1fr` e o que estiver dentro do próprio bloco `:root` (onde o token NASCE)
# não caem aqui por construção — nenhuma exceção adicional foi necessária.
#
# M4/BL-313 (auditoria DL-026 rodada 3): a lista de unidades ainda estava
# incompleta — `lh`/`rlh`/`cap`/`ic`/`rex`/`rch` passavam batido. Em vez de
# só acrescentar essas seis (o mesmo erro de "lista que fica atrás" do lado
# da propriedade), a lista abaixo é a enumeração COMPLETA das unidades de
# comprimento do CSS Values and Units Module Level 4 (w3.org/TR/css-values-4,
# §6-7) mais as unidades de consulta de contêiner (CSS Containment/
# Conditional Rules) — absolutas, relativas a fonte (incluindo as
# relativas à RAIZ, prefixo `r`: `rem`/`rex`/`rcap`/`rch`/`ric`/`rlh`),
# relativas a viewport (com os quatro prefixos de viewport dinâmico:
# nenhum/`s`/`l`/`d`) e relativas a contêiner (`cq*`). Fora, por decisão
# deliberada (não esquecimento): unidades de ângulo/tempo/frequência/
# resolução, que não medem TELA.
_PADRAO_MEDIDA_LITERAL = re.compile(
    r"(?<![\w.-])\d*\.?\d+(?:"
    # Absolutas (§6.2)
    r"px|cm|mm|q|in|pt|pc"
    # Relativas a fonte, incluindo as relativas à raiz (§6.1/§6.3)
    r"|rem|em|rex|ex|rcap|cap|rch|ch|ric|ic|rlh|lh"
    # Relativas a viewport, com os quatro prefixos (§6.4)
    r"|svw|lvw|dvw|vw|svh|lvh|dvh|vh"
    r"|svi|lvi|dvi|vi|svb|lvb|dvb|vb"
    r"|svmin|lvmin|dvmin|vmin|svmax|lvmax|dvmax|vmax"
    # Relativas a contêiner (CSS Containment/Conditional Rules)
    r"|cqw|cqh|cqi|cqb|cqmin|cqmax"
    r")\b",
    re.IGNORECASE,
)


def _sem_variavel_css_preservando_fallback(valor):
    """Remove só a REFERÊNCIA `var(--nome, fallback)`, preservando o
    FALLBACK — M2/BL-293 (auditoria DL-026 rodada 2): `re.sub(r"var\\(
    [^)]*\\)", "", valor)` apagava a variável E o fallback JUNTOS, então
    `var(--x, 37px)` e `var(--x, red)` desapareciam inteiros e a medida (ou
    cor) de reserva — o valor que o NAVEGADOR usa de verdade quando o token
    não existe — escapava tanto do detector de medida quanto do de cor.

    `var(--nome)` sem fallback continua virando string vazia (nada a
    preservar). O nome da variável CSS custom property sempre começa com
    `--`; exigir isso evita tratar uma função qualquer chamada `var(...)`
    (não existe no CSS real, mas closes a mesma classe de suposição
    implícita que já motivou outras guardas deste arquivo) como referência
    de token.
    """

    def _troca(m):
        return m.group(1) if m.group(1) is not None else ""

    return re.sub(r"var\(\s*--[\w-]+\s*(?:,\s*([^)]*))?\)", _troca, valor)


def _arquivos_do_projeto(raiz, padrao_glob):
    """Todo arquivo que bate com `padrao_glob` (ex.: `"*.css"`, `"*.html"`)
    sob `raiz`, em QUALQUER subpasta — excluindo só o que nunca é o
    PRODUTO: as pastas nomeadas em `PASTAS_SEM_CSS_DO_PROJETO` (o nome
    ficou da época em que só servia a CSS; ver o comentário de
    `_folhas_de_estilo_do_projeto`) e qualquer ambiente virtual Python
    (`_dentro_de_ambiente_virtual`).

    Extraído aqui pelo A3/BL-291 (auditoria DL-026 rodada 2): o mecanismo de
    exclusão já existia neste arquivo, mas só do lado do CSS
    (`_folhas_de_estilo_do_projeto`) — `_templates()` fazia
    `TEMPLATES.rglob("*.html")`, olhando SÓ `templates/` na raiz, enquanto
    `config/settings.py` declara `"APP_DIRS": True` e o Django resolve
    `apps/<app>/templates/<app>/*.html` normalmente. O auditor criou
    `apps/fiscal/templates/fiscal/apuracao.html` violando seis guardas de
    uma vez — extends ausente, caption ausente, `<th>` sem `scope`, valor
    sem a classe, estilo embutido e cor solta — e a suíte deu `1363 passed`
    porque a varredura nunca lia o arquivo que o Django já servia. Não é
    variante de regex: é a mesma cegueira ESTRUTURAL do `_folhas_de_estilo_
    do_projeto` antes do BL-274 #2/#3, agora do lado dos templates.
    """
    achados = []
    for caminho in sorted(raiz.rglob(padrao_glob)):
        partes = caminho.relative_to(raiz).parts
        if partes[0] in PASTAS_SEM_CSS_DO_PROJETO:
            continue
        if _dentro_de_ambiente_virtual(caminho, raiz):
            continue
        achados.append(caminho)
    return achados


def _templates(raiz):
    """Todo `.html` de TEMPLATE do projeto, em qualquer subpasta de `raiz`
    — não só `templates/` (ver o docstring de `_arquivos_do_projeto` para o
    achado que motivou isto, BL-291). `raiz` é parâmetro explícito (não o
    global `RAIZ`) para que o controle positivo abaixo possa provar o
    alcance em `tmp_path`, sem depender de nada existir ou deixar de
    existir na árvore real."""
    return _arquivos_do_projeto(raiz, "*.html")


def _pasta_pai_dos_apps_instalados():
    """Nome(s) da(s) pasta(s) que hoje ABRIGAM os apps Django deste projeto
    (ex.: `"apps"`), derivado dos apps REALMENTE registrados em
    `INSTALLED_APPS` — nunca um literal escrito à mão.

    BL-320 (M2, auditoria DL-026 rodada 4): a versão anterior desta guarda
    reconhecia a convenção `apps/<modulo>/templates/<modulo>/...` por um
    prefixo de caminho LITERAL (`partes[0] == "apps"`). Derivar o nome real
    da pasta a partir de `AppConfig.path` (relativo a `settings.BASE_DIR`)
    é o que faz a convenção sobreviver a uma reorganização do projeto
    (`src/<app>/`, por exemplo) sem precisar editar este arquivo — cada app
    fora da árvore do projeto (dependência instalada, `django.contrib.*`)
    é ignorado (`relative_to` levanta `ValueError`)."""
    base_dir = Path(django_settings.BASE_DIR).resolve()
    pastas = set()
    for config_do_app in django_apps.get_app_configs():
        caminho = Path(config_do_app.path).resolve()
        try:
            relativo = caminho.relative_to(base_dir)
        except ValueError:
            continue  # app de fora da árvore do projeto (dependência instalada)
        if len(relativo.parts) >= 2:
            pastas.add(relativo.parts[0])
    return pastas


def _raizes_de_template(raiz):
    """Pastas onde o Django procura TEMPLATE, derivadas de
    `django.conf.settings.TEMPLATES` — nunca de dois prefixos de caminho
    escritos à mão. `raiz` é parâmetro explícito (como em `_templates`/
    `_arquivos_do_projeto`): cada origem é expressa RELATIVA a
    `settings.BASE_DIR` e reancorada em `raiz`, para que os controles em
    `tmp_path` continuem provando o alcance sem depender da árvore real.

    BL-320 (M2, auditoria DL-026 rodada 4): a versão anterior reconhecia só
    DUAS formas de caminho ("apps/" e "templates/", escritas à mão) — um
    terceiro `DIRS` em `settings.TEMPLATES` (`BASE_DIR / "ui"`, por
    exemplo) devolvia a guarda à cegueira sem que ninguém precisasse tocar
    neste arquivo. As origens, as MESMAS que o Django resolve:

    - cada diretório de `TEMPLATES[*]["DIRS"]` — explícito, pode haver mais
      de um, e um novo passa a valer sem editar este módulo;
    - se `APP_DIRS` estiver ligado, a pasta `templates/` dentro de CADA
      pasta que hoje abriga um app Django deste projeto
      (`_pasta_pai_dos_apps_instalados`) — não só os apps JÁ registrados em
      `INSTALLED_APPS`: o propósito desta guarda (BL-309) é pegar um módulo
      ANTES de alguém lembrar de registrá-lo, não depois.
    """
    base_dir = Path(django_settings.BASE_DIR).resolve()
    raizes = []
    tem_app_dirs = False
    for motor in django_settings.TEMPLATES:
        for dir_configurado in motor.get("DIRS", []):
            caminho = Path(dir_configurado).resolve()
            try:
                relativo = caminho.relative_to(base_dir)
            except ValueError:
                continue  # DIRS fora da árvore do projeto: nada para reancorar em `raiz`
            raizes.append(raiz / relativo)
        if motor.get("APP_DIRS"):
            tem_app_dirs = True
    if tem_app_dirs:
        for pasta_de_apps in _pasta_pai_dos_apps_instalados():
            raiz_de_apps = raiz / pasta_de_apps
            if not raiz_de_apps.is_dir():
                continue
            for pasta_do_app in sorted(p for p in raiz_de_apps.iterdir() if p.is_dir()):
                raizes.append(pasta_do_app / "templates")
    return raizes


# A MOLDURA (`base.html`) não é módulo — mas a exclusão precisa ser por
# NOME, não por profundidade de caminho (ver o docstring de
# `_pastas_de_modulo_com_tela`).
NOME_DA_MOLDURA = "base.html"


def _pastas_de_modulo_com_tela(raiz):
    """Nome de cada pasta de MÓDULO que tem pelo menos um template, nas
    origens que `_raizes_de_template(raiz)` deriva de `settings.TEMPLATES`.

    BL-309 (A3 da auditoria DL-026 rodada 3): até aquela correção, a guarda
    do "momento da verdade" (`test_modulo_novo_declara_o_seu_momento_da_
    verdade`) enumerava `TEMPLATES.iterdir()` — só a origem `templates/` na
    raiz — CINCO rodadas depois de o BL-291 já ter ligado as outras cinco
    guardas de CONTEÚDO deste arquivo (extends, caption, scope, valor,
    estilo) a `_templates()`, que enxerga as duas origens. O mesmo
    template, bem formado, reprovava as cinco guardas de conteúdo em
    `apps/cobranca/templates/cobranca/titulos.html` E em `templates/
    cobranca/titulos.html` — mas só a sexta guarda, a desta função, era
    cega para a primeira origem.

    BL-320 (M2, auditoria DL-026 rodada 4): a correção do BL-309 trocou a
    cegueira de PASTA pela cegueira de FORMA DE CAMINHO — as duas origens
    continuavam reconhecidas por dois prefixos ESCRITOS À MÃO
    (`partes[0] == "apps"` / `partes[0] == "templates"`), e a exclusão de
    `base.html` era feita por PROFUNDIDADE (`len(partes) >= 3`), não por
    ele SER a moldura. Efeito colateral não documentado: `templates/
    cobranca.html` (módulo de tela ÚNICA, sem subpasta) tinha a MESMA
    profundidade de `templates/base.html` e escapava pelo mesmo motivo —
    o auditor mediu esse caso exato passando com `96 passed`. Esta versão
    deriva as ORIGENS de `settings.TEMPLATES` (`_raizes_de_template`) e
    exclui a moldura por NOME (`NOME_DA_MOLDURA`), nunca por profundidade:
    um `.html` direto numa raiz de template, sem subpasta, vira um módulo
    de tela única nomeado pelo PRÓPRIO ARQUIVO (`cobranca.html` →
    "cobranca") — a menos que seja, pelo nome, a moldura.
    """
    pastas = set()
    for raiz_de_template in _raizes_de_template(raiz):
        if not raiz_de_template.is_dir():
            continue
        for caminho in sorted(raiz_de_template.rglob("*.html")):
            partes = caminho.relative_to(raiz_de_template).parts
            if len(partes) == 1:
                if partes[0] == NOME_DA_MOLDURA:
                    continue
                pastas.add(Path(partes[0]).stem)
            else:
                pastas.add(partes[0])
    return pastas


def _e_parcial(caminho):
    """Trecho reaproveitado (`_nome.html`) não estende moldura: ele é incluído."""
    return caminho.name.startswith("_")


def _sem_comentarios_css(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _sem_comentarios_de_template(texto):
    """Remove `{% comment %}...{% endcomment %}` e `<!-- ... -->` antes de
    qualquer varredura de marcação.

    Achado descoberto ao endurecer `PADRAO_VALOR` (Achado 2 da revisão do
    arquiteto-senior): `templates/contabilidade/lancamento_form.html` tem um
    `{% comment %}` que EXPLICA esta própria guarda em prosa e cita, dentro
    do comentário, o texto literal `` `<td>` `` — sem remover o comentário
    primeiro, `PADRAO_CELULA` lia essa prosa como uma abertura de célula de
    verdade, e tudo até o próximo `</td>` real (inclusive `_ptbr` de
    comentários e de `{% if %}` seguintes) virava "dentro de uma célula sem
    classe". Comentário de documentação não é marcação; sem esta limpeza,
    documentar o comportamento da guarda quebra a guarda.
    """
    sem_django = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", texto, flags=re.S)
    return re.sub(r"<!--.*?-->", "", sem_django, flags=re.S)


# BL-321 (M3 da auditoria DL-026 rodada 4): a inversão do detector de MEDIDA
# (BL-313, rodada 3) acusava CSS legítimo — `@media print { .folha { --espaco:
# 2mm } }` e `@page { margin: 15mm }` — porque a única exceção de BLOCO era o
# `:root`, casado só quando `{` vinha IMEDIATAMENTE depois (`:root, ::backdrop
# { ... }`, o padrão para tornar tokens visíveis ao `::backdrop`, perdia a
# isenção INTEIRA). É consequência de uma decisão do `arquiteto-senior`: a
# inversão foi mandada sem mandar a contrapartida — falso positivo em CI é
# mais corrosivo que falso negativo, ele ensina que a guarda erra.
#
# `_PADRAO_REGRA_DE_NIVEL_SUPERIOR` extrai toda regra `seletor { corpo }` do
# texto (mesma limitação de sempre: não resolve chaves ANINHADAS de verdade,
# mas isso não importa aqui — só precisamos identificar seletores isentos,
# nunca reconstruir a árvore de um `@media`).
_PADRAO_REGRA_DE_NIVEL_SUPERIOR = re.compile(r"([^{}]+)\{(.*?)\}", re.S)


def _e_bloco_isento_de_cor_e_medida(selecionador):
    """`True` se `selecionador` (o texto ANTES do `{` de uma regra CSS) for
    isento da varredura de cor/medida literal: o `:root` — sozinho ou dentro
    de um SELETOR AGRUPADO, em QUALQUER posição do grupo, com ou sem
    pseudo-classe encadeada (`:root, ::backdrop`, `::backdrop, :root`,
    `:root:not(.compacto)`) — ou o bloco `@page` (com ou sem pseudo-página,
    `@page :first`).

    `@page` é isento como BLOCO, nunca por nome de propriedade: indexar a
    exceção em `PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL` por `margin`
    liberaria `margin` na folha INTEIRA, não só dentro de `@page` — e `@page`
    é a ÚNICA forma de declarar margem de impressão em CSS (o suporte a
    `var()` ali não é confiável)."""
    selecionador = selecionador.strip()
    if selecionador.startswith("@page"):
        return True
    for token in selecionador.split(","):
        token = token.strip()
        if token == ":root" or token.startswith(":root:"):
            return True
    return False


def _texto_sem_root(texto):
    """Remove comentários e os blocos ISENTOS (`:root`, inclusive em seletor
    AGRUPADO, e `@page`) — é onde os tokens NASCEM (DE-053) e onde a folha de
    impressão declara margem; cor ou medida literal ali é a própria definição
    do token, ou uma restrição da própria plataforma, nunca violação.
    Compartilhado pelos detectores de cor e de medida (mesma regra, mesma
    exceção) — BL-321 acrescentou `@page` e o seletor agrupado aqui, uma vez
    só, para valer nos dois detectores sem duplicar a regra."""
    limpo = _sem_comentarios_css(texto)
    for regra in _PADRAO_REGRA_DE_NIVEL_SUPERIOR.finditer(limpo):
        if _e_bloco_isento_de_cor_e_medida(regra.group(1)):
            limpo = limpo.replace(regra.group(0), "")
    return limpo


def _cores_fora_dos_tokens(texto):
    """Cores declaradas fora do `:root`/`@page`, em hex/rgb/hsl **ou
    nomeadas** (BL-274 #2: `red`, `white`... eram invisíveis) — cobrindo as
    funções COMPLETAS do CSS Color Level 4/5 (BL-319/M1, ver `PADRAO_COR`).

    O `:root` é onde os tokens moram (DE-053). Cor escrita direto numa regra de
    tela é o começo da divergência: a próxima tela copia, a terceira erra o
    tom, e seis meses depois existem quatro azuis.

    BL-321 (M3, auditoria DL-026 rodada 4): reescrita para varrer
    DECLARAÇÃO POR DECLARAÇÃO (mesma forma de `_medidas_literais_fora_dos_
    tokens`, com a MESMA regex `_PADRAO_DECLARACAO_COM_PROPRIEDADE`) em vez de
    um `findall` cego sobre o texto inteiro — é o que permite pular uma
    CUSTOM PROPERTY (`--nome: valor;`) sem importar em que bloco ela está: ela
    é a DEFINIÇÃO de um token, onde quer que esteja escrita (`.folha
    { --acento-oklch: oklch(0.6 0.2 30); }` dentro de `@media print`, por
    exemplo), nunca uma violação — o mesmo raciocínio do `:root`, generalizado
    para qualquer escopo em que o projeto decida nomear um token.
    """
    limpo = _texto_sem_root(texto)
    achados = []
    for declaracao in _PADRAO_DECLARACAO_COM_PROPRIEDADE.finditer(limpo):
        propriedade, valor_bruto = declaracao.group(1), declaracao.group(2)
        if propriedade.strip().startswith("--"):
            # BL-321: custom property é a DEFINIÇÃO do token, em qualquer
            # bloco — nunca o VALOR de tinta que a varredura precisa cobrar.
            continue
        # `var(...)` pode conter qualquer coisa no NOME da variável
        # (`var(--cor-red-alerta)`) sem que isso seja uma cor nomeada de
        # verdade; remove a REFERÊNCIA antes de tokenizar, preservando o
        # FALLBACK (M2/BL-293 — ver o docstring de
        # `_sem_variavel_css_preservando_fallback`: `var(--x, red)` tinha a
        # cor de reserva apagada junto com a variável e escapava).
        valor = _sem_variavel_css_preservando_fallback(valor_bruto)
        achados.extend(PADRAO_COR.findall(valor))
        # String e `url()` também não são cor nomeada literal.
        if "url(" in valor or '"' in valor or "'" in valor:
            continue
        for token in re.findall(r"[a-zA-Z]+", valor):
            nome = token.lower()
            if nome in CORES_NOMEADAS_CSS and nome not in NOMES_QUE_NAO_SAO_TINTA:
                achados.append(nome)
    return achados


def _cores_de_sistema_fora_dos_tokens(texto):
    """Cor de SISTEMA (`CORES_DE_SISTEMA_CSS`) declarada fora do `:root`/
    `@page`, numa propriedade que ACEITA cor — categoria PRÓPRIA (BL-335/M3,
    auditoria DL-026 rodada 5), separada de `_cores_fora_dos_tokens`: uma
    cor de sistema não é uma tinta que o projeto ERROU (como um `red`
    solto), é uma tinta que o projeto NÃO CONTROLA — o motivo está em
    `MOTIVO_COR_DE_SISTEMA`, e é ele que a mensagem de reprovação precisa
    repetir, não só "cor fora dos tokens".

    F4 da auditoria DL-026 rodada 6: até essa correção, a varredura lia
    QUALQUER declaração `propriedade: valor`, e uma palavra do inglês comum
    fora de contexto de cor virava falso alarme — `animation-name:
    highlight-row`, `animation-name: mark-in`, `grid-area: canvas`,
    `font-family: Field Sans`, `view-transition-name: mark`, medido pelo
    auditor com `1 failed` numa mudança que não tem cor nenhuma. Agora só a
    declaração cuja PROPRIEDADE aceita cor (`_propriedade_aceita_cor`) é
    examinada — o mesmo raciocínio que já valia para `PROPRIEDADES_QUE_
    ACEITAM_MEDIDA_LITERAL` do lado da medida, aplicado aqui do lado
    contrário (uma lista de propriedades que ENTRAM, não que escapam).

    Mesma estrutura de `_cores_fora_dos_tokens` (declaração por declaração,
    custom property sempre isenta por ser a DEFINIÇÃO do token — BL-321 —,
    `var()` sem o fallback removido antes de tokenizar — M2/BL-293), porque a
    forma de escapar dos tokens é a mesma; só a categoria do achado muda.
    Devolve a grafia ORIGINAL encontrada (`"Canvas"`, não `"canvas"`), porque
    é assim que ela aparece no CSS sabotado e é o que a mensagem de erro deve
    mostrar a quem for corrigir.
    """
    limpo = _texto_sem_root(texto)
    achados = []
    for declaracao in _PADRAO_DECLARACAO_COM_PROPRIEDADE.finditer(limpo):
        propriedade, valor_bruto = declaracao.group(1), declaracao.group(2)
        if propriedade.strip().startswith("--"):
            # BL-321: custom property é a DEFINIÇÃO do token, em qualquer
            # bloco — mesmo quando o valor dela É uma cor de sistema (caso
            # hipotético, nunca visto no projeto: alguém amarrando um token
            # do :root a `Canvas` de propósito). A definição não é o que
            # esta varredura precisa cobrar; o USO fora do token, sim.
            continue
        if not _propriedade_aceita_cor(propriedade):
            # F4 (rodada 6): fora de uma propriedade que aceita cor, uma
            # palavra do inglês comum (`highlight`, `mark`, `canvas`,
            # `field`...) não é cor nenhuma — é nome de animação, área de
            # grid, família de fonte, nome de view-transition.
            continue
        valor = _sem_variavel_css_preservando_fallback(valor_bruto)
        if "url(" in valor or '"' in valor or "'" in valor:
            continue
        for token in re.findall(r"[a-zA-Z]+", valor):
            if token.lower() in CORES_DE_SISTEMA_CSS:
                achados.append(token)
    return achados


def _medidas_literais_fora_dos_tokens(texto):
    """Unidade de comprimento literal (`px`/`rem`/`em`/... — lista completa
    em `_PADRAO_MEDIDA_LITERAL`) em QUALQUER propriedade, fora do `:root`/
    `@page`. Devolve `"propriedade: valor"` para cada ofensor.

    O detector que o critério 13 prometia ("cor, TAMANHO ou ESPAÇAMENTO fora
    dos tokens") e nunca existia — BL-274, achado A1 da rodada 1.

    BL-313 (M4 da auditoria DL-026 rodada 3): INVERTIDO — não filtra mais por
    uma lista fechada de propriedades (ver o comentário de
    `PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL` para a classe de defeito que
    isto fecha). Toda declaração `propriedade: valor;` fora do `:root`/`@page`
    é examinada; só escapa a que estiver na lista de exceções NOMEADAS, cujo
    NOME comece com `--` (custom property — BL-321/M3, ver o docstring de
    `_cores_fora_dos_tokens`), ou cujo valor genuinamente não contenha
    unidade de comprimento nenhuma (uma cor, `solid`, `auto`, um
    percentual...).
    """
    limpo = _texto_sem_root(texto)
    achados = []
    for declaracao in _PADRAO_DECLARACAO_COM_PROPRIEDADE.finditer(limpo):
        propriedade, valor = declaracao.group(1), declaracao.group(2)
        if propriedade.strip().startswith("--"):
            # BL-321 (M3): custom property é a DEFINIÇÃO do token, em
            # QUALQUER bloco — nunca uma medida solta para a varredura cobrar.
            continue
        if propriedade.lower() in PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL:
            continue
        # M2/BL-293: preserva o FALLBACK do `var()` em vez de apagá-lo junto
        # com a variável — ver o docstring de
        # `_sem_variavel_css_preservando_fallback`.
        valor_sem_var = _sem_variavel_css_preservando_fallback(valor)
        for literal in _PADRAO_MEDIDA_LITERAL.finditer(valor_sem_var):
            achados.append(f"{propriedade}: {literal.group(0)}")
    return achados


def _dentro_de_ambiente_virtual(caminho, raiz):
    """`caminho` mora dentro de um ambiente virtual Python, qualquer que
    seja o NOME da pasta.

    Detecção por comportamento, não por nome — achado do arquiteto-senior na
    revisão desta etapa: o `.gitignore` autoriza `.venv/` **e** `venv/`
    (linhas 6-7), e uma lista de nomes nunca cobre o próximo apelido (`env/`,
    `.direnv/`, o ambiente que alguém chamou de jeito nenhum a ver com
    "venv"). `pyvenv.cfg` é o marcador: todo ambiente virtual criado por
    `venv`/`virtualenv` tem esse arquivo na sua raiz, e só ele. Sobe os
    ancestrais entre o arquivo e a raiz do projeto procurando o marcador;
    para em `raiz` (inclusive) para não escapar do repositório.
    """
    atual = caminho.parent
    while True:
        if (atual / "pyvenv.cfg").is_file():
            return True
        if atual == raiz:
            return False
        proximo = atual.parent
        if proximo == atual:  # chegou na raiz do sistema de arquivos
            return False
        atual = proximo


def _folhas_de_estilo_do_projeto(raiz):
    """Todo `.css` do projeto, em qualquer subpasta — não só `static/css/`.

    BL-274 #2/#3: o `glob("*.css")` não era recursivo (`static/css/modulos/`
    escapava) e só olhava `static/css/` (`static/tema.css` escapava). Varre o
    repositório inteiro e exclui as pastas de dependência/build nomeadas em
    `PASTAS_SEM_CSS_DO_PROJETO`, mais qualquer ambiente virtual Python
    detectado por `_dentro_de_ambiente_virtual` — sem essas duas exclusões,
    o admin do Django coletado e o Bootstrap do DRF entrariam na varredura
    do produto. Mesmo mecanismo agora compartilhado com `_templates()` via
    `_arquivos_do_projeto` (BL-291, auditoria DL-026 rodada 2).
    """
    return _arquivos_do_projeto(raiz, "*.css")


def _estilos_embutidos(texto):
    """`style="..."`, `style='...'` (BL-274 #5) e `<style>` embutido no
    template — todos escapam do sistema de tokens e da auditoria de
    contraste: ninguém encontra aquele valor depois."""
    limpo = _sem_comentarios_de_template(texto)
    return [m.group(0)[:60] for m in PADRAO_ESTILO_EMBUTIDO.finditer(limpo)]


# ---------------------------------------------------------------------------
# BL-305 (achado do arquiteto-senior, confirmado na §3 da auditoria DL-026
# rodada 4): o enunciado do critério 13 é "quando um TEMPLATE usa cor,
# tamanho ou espaçamento fora dos tokens" — sem distinguir CSS de atributo.
# A varredura cobria `style=`/`<style>` (CSS embutido em template) e NADA
# além. O auditor mediu `<svg><rect fill="#ff0000" width="10" height="10">`
# passando batido: cor num atributo de APRESENTAÇÃO (`fill`), e "não é só
# cor, medida em atributo de apresentação também passa" (`width`/`height`,
# SEM unidade — em SVG, um número sem unidade É um comprimento, em "user
# units", o equivalente a pixel). Os dois defeitos são o MESMO enunciado; a
# correção trata os dois com a MESMA função.
#
# Dois sinais, nenhum deles uma lista de CASOS RELATADOS (a lição do
# BL-313/BL-319, aplicada aqui):
#
# 1. Cor/medida com marcação EXPLÍCITA (`#ff0000`, `oklch(...)`, `12px`) —
#    aplicada ao VALOR de QUALQUER atributo, em QUALQUER tag do template.
#    Não precisa de lista de nomes de atributo: um valor que CASA com
#    `PADRAO_COR`/`_PADRAO_MEDIDA_LITERAL` é, na prática esmagadora dos
#    casos, sempre cor ou medida de verdade — o mesmo raciocínio que already
#    vale para o valor de uma declaração CSS.
# 2. Medida SEM unidade explícita, só para o caso em que a especificação
#    garante o significado: um valor puramente numérico num atributo de
#    APRESENTAÇÃO do SVG (lista FECHADA e ESTÁVEL, `w3.org/TR/SVG2/`,
#    "Presentation attributes" — não uma lista de relatos, uma enumeração
#    de especificação, como as unidades de `_PADRAO_MEDIDA_LITERAL`),
#    restrito a texto DENTRO de um bloco `<svg>...</svg>`: é SÓ ali que a
#    especificação garante que um número sem unidade é um comprimento —
#    fora do SVG, `width`/`height` têm outros usos herdados do HTML
#    (`<canvas width="600">`, por exemplo) que este projeto não pode
#    confundir com a mesma classe de defeito.
ATRIBUTOS_SVG_DE_COMPRIMENTO = frozenset(
    "width height x y cx cy r rx ry x1 y1 x2 y2 stroke-width font-size".split()
)

_PADRAO_NUMERO_PURO = re.compile(r"^-?\d*\.?\d+$")

_PADRAO_BLOCO_SVG = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)

# DL-042 (especialista-frontend): ícones SVG embutidos (barra lateral
# recolhível, templates/base.html) definem o GLIFO dentro de `<symbol>`, num
# sistema de coordenadas LOCAL fixo (`viewBox="0 0 24 24"`) — os números em
# `x`/`y`/`width`/`height`/`cx`/`cy`/`r`/`stroke-width` ALI são geometria do
# desenho (onde a linha do ícone passa dentro do quadrado 24×24), nunca um
# TAMANHO renderizado que possa vazar do sistema de tokens: o tamanho REAL
# na tela vem de CSS tokenizado (`.icone-menu`, `--tamanho-icone-menu`,
# static/css/base.css) aplicado ao `<svg>` que usa o ícone (`<use
# href="#icone-x">`), nunca ao `<symbol>` em si — o `<symbol>` nem chega a
# ser desenhado sozinho (é um "molde", só existe para o `<use>` referenciar,
# como confirma o `display: none` do `<svg>` que os agrupa). Sem esta
# exceção, TODO ícone vetorial embutido — não só os desta etapa — seria
# proibido por construção, mesmo sem duplicar nenhum valor de DESIGN: um
# `viewBox="0 0 24 24"` não é um `width: 24px` fora do token, é a definição
# da forma.
#
# A exceção é ESTREITA e continua provando a mesma coisa que o BL-305 media:
# 1. Só isenta o que está DENTRO de `<symbol>...</symbol>` — um `<rect
#    width="10">` solto, fora de um `<symbol>`, continua reprovando (ver
#    `test_controle_positivo_atributo_de_apresentacao_reproducao_literal_do_achado`,
#    que usa exatamente essa forma, sem `<symbol>`, e continua vermelho).
# 2. Só isenta o sinal de MEDIDA sem unidade (`ATRIBUTOS_SVG_DE_COMPRIMENTO`
#    dentro do bloco `<svg>`) — o sinal de COR (a varredura de cima, que
#    cobre QUALQUER tag do documento, símbolo incluso) continua ativo: um
#    ícone que declarasse `fill="#ff0000"` dentro do `<symbol>` ainda seria
#    acusado (ver o controle abaixo,
#    `test_controle_positivo_cor_dentro_de_symbol_continua_acusada`) — é
#    exatamente essa combinação que preserva a PROPRIEDADE que o BL-305
#    protege (nenhuma cor de design bypassa os tokens), estreitando só o
#    falso positivo de geometria de glifo que a regra antiga não previa.
_PADRAO_BLOCO_SYMBOL = re.compile(r"<symbol\b.*?</symbol>", re.IGNORECASE | re.DOTALL)


def _cores_e_medidas_em_atributos_de_template(texto):
    """Cor OU medida literal escrita direto num ATRIBUTO de apresentação de
    template (fora de CSS) — ver o comentário acima (BL-305). Devolve a
    lista de ofensores, como `"fill=#ff0000"`/`"width=10"`."""
    limpo = _sem_comentarios_de_template(texto)
    achados = []

    for tag in PADRAO_TAG_ABERTURA.finditer(limpo):
        for nome, valor in atributos_da_tag(tag.group(0)):
            if not valor:
                continue
            for cor in PADRAO_COR.findall(valor):
                achados.append(f"{nome}={cor}")
            valor_normalizado = valor.strip().lower()
            if (
                valor_normalizado in CORES_NOMEADAS_CSS
                and valor_normalizado not in NOMES_QUE_NAO_SAO_TINTA
            ):
                achados.append(f"{nome}={valor}")
            for medida in _PADRAO_MEDIDA_LITERAL.finditer(valor):
                achados.append(f"{nome}={medida.group(0)}")

    # Medida SEM unidade, só dentro de <svg> e só nos atributos de
    # apresentação de comprimento do SVG — ver o comentário acima.
    # DL-042: conteúdo dentro de <symbol> (a DEFINIÇÃO do glifo do ícone,
    # nunca um elemento renderizado por si só) é removido ANTES desta
    # varredura — ver o comentário de `_PADRAO_BLOCO_SYMBOL`, acima, para o
    # raciocínio completo e os dois controles que provam que a exceção é
    # estreita (não isenta cor, não isenta geometria FORA de <symbol>).
    for bloco in _PADRAO_BLOCO_SVG.finditer(limpo):
        bloco_sem_simbolos = _PADRAO_BLOCO_SYMBOL.sub("", bloco.group(0))
        for tag in PADRAO_TAG_ABERTURA.finditer(bloco_sem_simbolos):
            for nome, valor in atributos_da_tag(tag.group(0)):
                if not valor:
                    continue
                if nome in ATRIBUTOS_SVG_DE_COMPRIMENTO and _PADRAO_NUMERO_PURO.match(
                    valor.strip()
                ):
                    achados.append(f"{nome}={valor}")

    return achados


def _cores_de_sistema_em_atributos_de_template(texto):
    """Cor de SISTEMA (`CORES_DE_SISTEMA_CSS`) escrita direto num ATRIBUTO
    de apresentação de template — o mesmo caminho do BL-305
    (`_cores_e_medidas_em_atributos_de_template`, acima), separado numa
    função própria pela MESMA razão do lado CSS
    (`_cores_de_sistema_fora_dos_tokens`): categoria com motivo próprio, não
    mais um item de `CORES_NOMEADAS_CSS`.

    Igual ao caminho de `atributos_da_tag`, sem lista de nomes de atributo
    (`fill`, `stroke`, `color`, qualquer um): o valor de QUALQUER atributo
    que bater EXATAMENTE (não substring — `atributos_da_tag` já devolve o
    valor sem aspas, comparado inteiro) com uma palavra-chave de
    `CORES_DE_SISTEMA_CSS`, em QUALQUER tag, é ofensor. Devolve
    `"atributo=valor"`, no mesmo formato dos demais detectores de atributo
    deste arquivo.
    """
    limpo = _sem_comentarios_de_template(texto)
    achados = []
    for tag in PADRAO_TAG_ABERTURA.finditer(limpo):
        for nome, valor in atributos_da_tag(tag.group(0)):
            if not valor:
                continue
            if valor.strip().lower() in CORES_DE_SISTEMA_CSS:
                achados.append(f"{nome}={valor}")
    return achados


# M3/BL-294 (auditoria DL-026 rodada 2): elementos VAZIOS do HTML5 — nunca
# têm tag de fechamento, por definição da especificação (WHATWG "void
# elements"). `_involucro_cobre_valor` (abaixo) tratava a AUSÊNCIA de
# `</tag>` como "invólucro ainda aberto, cobre o valor" — para um elemento
# vazio isso é SEMPRE verdadeiro e SEMPRE errado: `<br class="valor-
# monetario">{{ x_ptbr }}</td>` não pode envolver nada, porque não tem
# conteúdo entre abertura e o (inexistente) fechamento. Medido pelo
# auditor: a coluna perdia `tabular-nums` — o defeito exato que esta guarda
# existe para impedir — com `61 passed`.
ELEMENTOS_VAZIOS_HTML = frozenset(
    "area base br col embed hr img input link meta source track wbr".split()
)


def _involucro_cobre_valor(texto, inicio, fim):
    """`True` se existir, entre as posições `inicio` e `fim` de `texto`, um
    elemento ABERTO com a classe `valor-monetario` que ainda não tenha sido
    fechado antes de `fim` — o invólucro em linha (ex.: `<span
    class="valor-monetario">`) que a rodada 3 do BL-286 passou a aceitar
    como alternativa à classe na própria célula, quando a célula mistura
    texto corrido (rótulo, frase de veredito) com o número.

    `inicio` é o fim da tag de ABERTURA da célula (`<td ...>`/`<th ...>`);
    `fim` é a posição do PRÓPRIO valor `_ptbr` — nunca o começo da célula,
    porque o que importa é se o invólucro ainda está aberto QUANDO o valor
    aparece, não se ele existe em algum lugar da célula (um invólucro que
    já fechou antes do valor não cobre nada — ver o teste de controle
    correspondente).

    Um elemento VAZIO (`ELEMENTOS_VAZIOS_HTML` acima) nunca conta como
    invólucro, mesmo que carregue a classe: ele não tem conteúdo para
    envolver, então nunca "cobre" o valor que vem depois dele no texto
    (M3/BL-294).

    Não é um parser de HTML completo (mesma limitação, já documentada,
    deste arquivo inteiro): olha o PRIMEIRO invólucro com a classe
    encontrado na janela e confere se o seu fechamento (`</mesma-tag>`, a
    primeira ocorrência depois da abertura) vem depois de `fim`.
    Suficiente para o padrão real deste projeto — um `<span>` simples
    envolvendo só o número —, sem resolver aninhamento arbitrário de
    marcação.
    """
    for abertura in PADRAO_TAG_ABERTURA.finditer(texto, inicio, fim):
        if not _tem_classe(abertura.group(0), "valor-monetario"):
            continue
        tag = abertura.group(1)
        if tag.lower() in ELEMENTOS_VAZIOS_HTML:
            continue
        fechamento = texto.find(f"</{tag}>", abertura.end())
        if fechamento == -1 or fechamento >= fim:
            return True
    return False


def _valores_sem_classe(texto):
    """Valores `_ptbr` dentro de célula de tabela que não usam a classe do
    sistema — nem na própria célula, nem num invólucro em linha ao redor
    do número (rodada 3, BL-286: a tabulação pertence ao NÚMERO, não
    necessariamente à célula inteira). Devolve a lista dos trechos
    ofensores."""
    limpo = _sem_comentarios_de_template(texto)
    ofensores = []
    for valor in PADRAO_VALOR.finditer(limpo):
        anteriores = list(PADRAO_CELULA.finditer(limpo, 0, valor.start()))
        if not anteriores:
            continue  # o valor não está dentro de célula: fora do alcance da regra
        celula = anteriores[-1]
        # A célula só vale se o valor estiver antes do próximo fechamento dela.
        fechamento = limpo.find(f"</{celula.group(1)}>", celula.end())
        if fechamento != -1 and fechamento < valor.start():
            continue
        if _tem_classe(celula.group(0), "valor-monetario"):
            continue
        if _involucro_cobre_valor(limpo, celula.end(), valor.start()):
            continue
        ofensores.append((celula.group(0)[:70], valor.group(0)[:40]))
    return ofensores


def _cabecalhos_sem_escopo(texto):
    limpo = _sem_comentarios_de_template(texto)
    achados = re.finditer(r"<th\b[^>]*>", limpo)
    return [m.group(0)[:70] for m in achados if not _PADRAO_ATRIBUTO_SCOPE.search(m.group(0))]


def _secao_do_momento_da_verdade(texto_direcao_de_arte):
    """Recorta só a seção '## 3.' da direção de arte, até o próximo '## '.

    BL-274 #6: a guarda antiga fazia substring no DOCUMENTO INTEIRO. Recortar
    a seção primeiro é o que torna a checagem seguinte (linha de tabela)
    honesta — "Fiscal" pode sobreviver em outras quatro frases do documento,
    fora desta seção, sem que isso conte.
    """
    m = PADRAO_SECAO_MOMENTO_DA_VERDADE.search(texto_direcao_de_arte)
    return m.group(0) if m else ""


def _tem_linha_na_tabela(secao, nome_do_modulo):
    """Existe uma linha de tabela markdown `| **Nome** | ... |` com este nome
    exato dentro da seção — não basta o nome aparecer em prosa."""
    padrao = re.compile(r"^\|\s*\*\*" + re.escape(nome_do_modulo) + r"\*\*\s*\|", re.MULTILINE)
    return bool(padrao.search(secao))


# As duas dívidas que este bloco registrava (DIVIDA_VALOR: 4 células de
# totalizador fora da classe do sistema em lancamento_form.html e razao.html;
# DIVIDA_COR: 5 cores soltas em static/css/base.css) foram FECHADAS pela
# implementação real da DL-026 (DE-053) nesta etapa — `strict=True` fez
# exatamente o que o comentário original previa: "no instante em que a
# implementação consertar, o teste passa a REPROVAR POR PASSAR, e quem
# estiver aqui é obrigado a apagar a marca". As duas marcas de
# `xfail` saíram das guardas abaixo; elas agora correm como guarda normal,
# sem rede de segurança para a dívida — porque a dívida não existe mais.

# ---------------------------------------------------------------------------
# As guardas
# ---------------------------------------------------------------------------


def test_toda_tela_estende_a_moldura_comum():
    """Tela que não estende `base.html` nasce fora do sistema visual.

    É assim que um módulo novo começa a divergir: alguém copia um HTML inteiro
    "só para testar" e ele fica. A moldura carrega marca, contexto de empresa e
    competência, navegação e os tokens — sair dela é sair da direção de arte.

    Achado da inspeção da rodada 3 (BL-286, mesma família da sabotagem 3):
    esta checagem lia `t.read_text(...)` CRU, sem `_sem_comentarios_de_
    template` — um `{% comment %}` que mencionasse `` `{% extends
    "base.html" %}` `` em PROSA (documentando a própria tela, como o
    `lancamento_form.html` já faz para outras marcas) faria a tela passar
    mesmo SEM a tag `{% extends %}` real. Mesmo mecanismo do achado que
    motivou `_sem_comentarios_de_template` (docstring dela, achado descoberto
    ao endurecer `PADRAO_VALOR`) — só que este caminho nunca tinha recebido
    a mesma correção.
    """
    fora = [
        str(t.relative_to(RAIZ))
        for t in _templates(RAIZ)
        if t.name != "base.html"
        and not _e_parcial(t)
        and "{% extends" not in _sem_comentarios_de_template(t.read_text(encoding="utf-8"))
    ]
    assert not fora, (
        "Telas que não estendem a moldura comum: "
        + ", ".join(fora)
        + ". Trecho reaproveitado começa com '_'; tela estende base.html."
    )


def test_toda_tabela_declara_legenda():
    """`<caption>` é o que diz ao leitor de tela o que a tabela contém.

    Sem ela, quem usa leitor de tela cai numa grade de números sem saber se está
    no Balancete ou no Razão. É requisito da própria W3C para tabela de dados, e
    o projeto já a tem em todas — esta guarda impede o próximo módulo de chegar
    sem.

    Mesmo achado da inspeção da rodada 3 (BL-286): a contagem de `<table`/
    `<caption` lia o texto CRU do template, sem tirar `{% comment %}`
    primeiro — um comentário que citasse `` `<table>` `` ou `` `<caption>`
    `` em prosa inflava a contagem de LEGENDAS sem existir tabela nem
    legenda real nenhuma ali, mascarando uma tabela de verdade sem
    `<caption>` em outro lugar do mesmo arquivo.
    """
    faltando = []
    for t in _templates(RAIZ):
        texto = _sem_comentarios_de_template(t.read_text(encoding="utf-8"))
        tabelas = len(re.findall(r"<table\b", texto, re.IGNORECASE))
        legendas = len(re.findall(r"<caption\b", texto, re.IGNORECASE))
        if tabelas > legendas:
            faltando.append(f"{t.relative_to(RAIZ)} ({tabelas} tabelas, {legendas} legendas)")
    assert not faltando, "Tabelas sem <caption>: " + "; ".join(faltando)


def test_todo_cabecalho_de_tabela_declara_escopo():
    """`<th>` sem `scope` faz o leitor de tela ler "1.234,56" sem dizer de qual
    coluna e de qual conta. Em tabela contábil, é o mesmo que não ler nada."""
    faltando = []
    for t in _templates(RAIZ):
        for cabecalho in _cabecalhos_sem_escopo(t.read_text(encoding="utf-8")):
            faltando.append(f"{t.relative_to(RAIZ)}: {cabecalho}")
    assert not faltando, "Cabeçalhos de tabela sem scope: " + "; ".join(faltando)


def test_todo_valor_em_celula_usa_a_classe_do_sistema():
    """Coluna de valor sem a classe do sistema perde a tabulação de algarismos.

    O efeito é o que o gauntlet mediu e nomeou: as colunas **dançam**, porque
    `1` e `8` têm larguras diferentes em fonte proporcional, e o olho perde a
    referência vertical justamente onde a conferência acontece.

    A mensagem de erro orienta as DUAS saídas possíveis (classe, ou remover o
    sufixo `_ptbr` de valor de uma célula que não é dinheiro) — ver
    `MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE`, achado 2 da revisão do
    arquiteto-senior: `_ptbr` também é usado em data, e a guarda não pode
    instruir alguém a tabular algarismos de uma data.
    """
    ofensores = []
    for t in _templates(RAIZ):
        for celula, valor in _valores_sem_classe(t.read_text(encoding="utf-8")):
            ofensores.append(f"{t.relative_to(RAIZ)}: {valor} em {celula}")
    assert not ofensores, (
        "Valores em célula de tabela sem a classe 'valor-monetario': "
        + "; ".join(ofensores)
        + ". "
        + MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE
    )


def test_a_classe_de_valor_tabula_algarismos():
    """A classe existe — mas ela precisa **fazer** o que promete.

    Guarda contra o defeito exato da BL-271: o nome certo no lugar certo, e a
    propriedade que importa removida sem ninguém perceber.

    Mesma família do achado da inspeção da rodada 3 (BL-286): o corpo do
    bloco `.valor-monetario` era lido SEM tirar comentário CSS primeiro —
    um comentário `/* tabular-nums */` sobrevivendo sozinho, com a
    declaração REAL já removida, teria enganado esta guarda. `_sem_
    comentarios_css` (já usada pelos detectores de cor/medida) fecha o
    mesmo buraco aqui.
    """
    css = (ESTILOS / "base.css").read_text(encoding="utf-8")
    bloco = re.search(r"\.valor-monetario\s*\{(.*?)\}", css, flags=re.S)
    assert bloco, "A classe .valor-monetario sumiu de static/css/base.css"
    corpo = _sem_comentarios_css(bloco.group(1))
    assert "tabular-nums" in corpo or "mono" in corpo.lower(), (
        "A classe .valor-monetario existe mas não tabula algarismos. "
        "Sem isso as colunas de valor voltam a dançar: " + corpo.strip()[:120]
    )


def test_nenhuma_cor_declarada_fora_dos_tokens():
    """Cor solta é o começo de quatro azuis diferentes (DE-053). Cobre
    hex/rgb/hsl e cor NOMEADA (BL-274 #2), em todo `.css` do projeto, não só
    `static/css/*.css` de primeiro nível (BL-274 #3)."""
    soltas = []
    for folha in _folhas_de_estilo_do_projeto(RAIZ):
        for cor in _cores_fora_dos_tokens(folha.read_text(encoding="utf-8")):
            soltas.append(f"{folha.relative_to(RAIZ)}: {cor}")
    assert not soltas, (
        "Cores declaradas fora do :root (tokens da DE-053): "
        + "; ".join(soltas)
        + ". Se a cor é nova, ela nasce como token com o contraste medido."
    )


def test_nenhuma_cor_de_sistema_declarada_fora_dos_tokens():
    """BL-335 (M3 da auditoria DL-026 rodada 5): cor de sistema é uma
    CATEGORIA PRÓPRIA de violação, não mais um nome esquecido na lista de
    `test_nenhuma_cor_declarada_fora_dos_tokens` — ver `MOTIVO_COR_DE_
    SISTEMA`. Reprodução da sabotagem exata do auditor
    (`docs/auditorias/2026-09-19-dl-026-rodada-5.md`, achado M3):
    `.sabotagem { color: Canvas; background: ButtonFace; border-color:
    AccentColor; outline-color: LinkText; }` fora do `:root`."""
    soltas = []
    for folha in _folhas_de_estilo_do_projeto(RAIZ):
        for cor in _cores_de_sistema_fora_dos_tokens(folha.read_text(encoding="utf-8")):
            soltas.append(f"{folha.relative_to(RAIZ)}: {cor}")
    assert not soltas, (
        "Cor de sistema declarada fora do :root: "
        + "; ".join(soltas)
        + ". "
        + MOTIVO_COR_DE_SISTEMA
    )


def test_nenhuma_medida_literal_fora_dos_tokens():
    """`px`/`rem`/`em` literais em padding/margin/gap/font-size/border-width —
    o detector que o critério 13 prometia ("cor, TAMANHO ou ESPAÇAMENTO fora
    dos tokens") e nunca existiu (BL-274, achado A1).

    Sem `xfail`: a dívida que este detector cobre é o BL-279 (M3 da rodada 1
    — 7 medidas soltas e ~15 larguras de borda literais em `base.css`,
    medidas pelo auditor em `5c7303e`). No momento em que este teste foi
    escrito, `static/css/base.css` já estava com working tree modificada e
    ZERO medida literal nas propriedades cobertas — o especialista-frontend
    fechou o BL-279 em paralelo, na mesma rodada. Não há dívida para marcar;
    se ela reaparecer (aqui ou numa reversão futura), esta guarda reprova
    normalmente, sem rede de segurança — como já aconteceu com as duas
    dívidas de cor e de valor registradas no bloco de comentário acima."""
    soltas = []
    for folha in _folhas_de_estilo_do_projeto(RAIZ):
        for achado in _medidas_literais_fora_dos_tokens(folha.read_text(encoding="utf-8")):
            soltas.append(f"{folha.relative_to(RAIZ)}: {achado}")
    assert not soltas, (
        "Medidas literais fora dos tokens (padding/margin/gap/font-size/"
        "border-width, critério 13 da DL-026): " + "; ".join(soltas)
    )


def test_nenhum_estilo_embutido_no_template():
    """`style="..."`, `style='...'` e `<style>` embutido escapam do sistema de
    tokens e da auditoria de contraste: ninguém encontra aquele valor depois."""
    embutidos = []
    for t in _templates(RAIZ):
        for achado in _estilos_embutidos(t.read_text(encoding="utf-8")):
            embutidos.append(f"{t.relative_to(RAIZ)}: {achado}")
    assert not embutidos, "Estilo embutido em template: " + "; ".join(embutidos)


def test_nenhuma_cor_ou_medida_em_atributo_de_apresentacao_do_template():
    """Critério 13: "quando um template usa cor, tamanho ou espaçamento
    fora dos tokens" — o enunciado não distingue CSS de ATRIBUTO. BL-305
    (achado do arquiteto-senior, confirmado na §3 da auditoria DL-026
    rodada 4): a varredura cobria `style=`/`<style>` e nada além; um `fill`/
    `width` de SVG embutido bypassava o sistema de tokens sem passar por
    nenhuma das guardas de CSS."""
    ofensores = []
    for t in _templates(RAIZ):
        for achado in _cores_e_medidas_em_atributos_de_template(t.read_text(encoding="utf-8")):
            ofensores.append(f"{t.relative_to(RAIZ)}: {achado}")
    assert not ofensores, (
        "Cor ou medida literal em atributo de apresentação de template "
        "(critério 13 da DL-026): " + "; ".join(ofensores)
    )


def test_nenhuma_cor_de_sistema_em_atributo_de_apresentacao_do_template():
    """BL-335 (M3, rodada 5): a mesma categoria própria do detector de CSS
    (ver `test_nenhuma_cor_de_sistema_declarada_fora_dos_tokens`), agora no
    caminho de ATRIBUTO que o BL-305 abriu — o item 2 do que este item
    precisava entregar."""
    ofensores = []
    for t in _templates(RAIZ):
        for achado in _cores_de_sistema_em_atributos_de_template(t.read_text(encoding="utf-8")):
            ofensores.append(f"{t.relative_to(RAIZ)}: {achado}")
    assert not ofensores, (
        "Cor de sistema em atributo de apresentação de template: "
        + "; ".join(ofensores)
        + ". "
        + MOTIVO_COR_DE_SISTEMA
    )


def test_modulo_novo_declara_o_seu_momento_da_verdade():
    """Módulo sem a sua pergunta escrita — numa LINHA DE TABELA do §3, não em
    prosa solta em qualquer lugar do documento (BL-274 #6) — não devia ter
    tela desenhada.

    O "momento da verdade" é a pergunta que a tela responde **antes de gravar**
    — no Contábil, "débito é igual a crédito?". Quem não sabe responder pelo
    Fiscal, pela Folha ou pelo Lalur tem um problema de entendimento do
    domínio, e a hora de descobrir é antes da tela, não depois.

    BL-309 (A3 da auditoria DL-026 rodada 3): a enumeração de módulos vem de
    `_pastas_de_modulo_com_tela(RAIZ)` — que lê os arquivos que `_templates`
    de fato encontra, nas DUAS origens (`templates/<modulo>/` e
    `apps/<modulo>/templates/<modulo>/`) — nunca de `TEMPLATES.iterdir()`
    (só a primeira origem, a cegueira que sobreviveu cinco rodadas depois de
    as outras cinco guardas de conteúdo já terem sido corrigidas pelo
    BL-291. Ver o docstring de `_pastas_de_modulo_com_tela`.
    """
    secao = _secao_do_momento_da_verdade(DIRECAO_DE_ARTE.read_text(encoding="utf-8"))
    assert secao, "A seção '## 3.' sumiu de docs/projeto/direcao-de-arte.md"
    sem_linha = []
    for nome in sorted(_pastas_de_modulo_com_tela(RAIZ)):
        if nome in PASTAS_QUE_NAO_SAO_MODULO:
            continue
        nome_na_tabela = NOME_DO_MODULO_NA_TABELA.get(nome, nome.capitalize())
        if not _tem_linha_na_tabela(secao, nome_na_tabela):
            sem_linha.append(f"{nome} (procurado na tabela como '{nome_na_tabela}')")
    assert not sem_linha, (
        "Módulos com tela mas sem LINHA NA TABELA do 'momento da verdade' (§3) de "
        f"docs/projeto/direcao-de-arte.md: {', '.join(sem_linha)}. "
        "Escreva a linha '| **Nome** | pergunta |' na tabela do §3 — ou declare a "
        "pasta em PASTAS_QUE_NAO_SAO_MODULO, com o motivo."
    )


# ---------------------------------------------------------------------------
# Controles positivos: cada detector precisa saber reprovar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        (":root { --a: #fff; }\n.botao { color: #123456; }", "#123456"),
        (":root { --a: #fff; }\n.aviso { background: rgb(1, 2, 3); }", "rgb(1, 2, 3)"),
    ],
)
def test_controle_positivo_detector_de_cor_solta(css_ruim, esperado):
    assert esperado in _cores_fora_dos_tokens(css_ruim)


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        (":root { --a: #fff; }\n.teste { color: red; }", "red"),
        (":root { --a: #fff; }\n.teste { background: white; }", "white"),
        (":root { --a: #fff; }\n.teste { border-color: red solid; }", "red"),
    ],
)
def test_controle_positivo_detector_de_cor_nomeada(css_ruim, esperado):
    """BL-274 #2: `red`/`white` eram invisíveis — só hex/rgb/hsl eram vistos."""
    achados = _cores_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"o detector deixou passar a cor nomeada '{esperado}'"


def test_controle_negativo_detector_de_cor_nomeada_ignora_palavra_chave_que_nao_e_tinta():
    css = ":root { --a: #fff; }\n.teste { background: transparent; color: var(--a); }"
    assert _cores_fora_dos_tokens(css) == [], (
        "'transparent'/var() não são tinta e não podiam ter sido acusados"
    )


def test_controle_positivo_detector_de_cor_ignora_o_que_esta_no_token():
    assert (
        _cores_fora_dos_tokens(":root {\n  --cor-texto: #1a1a1a;\n  --cor-fundo: white;\n}\n") == []
    )


# ---------------------------------------------------------------------------
# BL-319 (M1 da auditoria DL-026 rodada 4): o detector de cor mantinha a
# lista fechada (`rgba?`/`hsla?`/hex) que o detector de MEDIDA (BL-313,
# mesma rodada) já tinha abandonado — `oklch()`/`lab()`/`hwb()` passavam
# com `96 passed`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # Reprodução EXATA da sabotagem do M1.
        (":root { --a: #fff; }\n.x { color: oklch(0.7 0.2 20); }", "oklch(0.7 0.2 20)"),
        (":root { --a: #fff; }\n.x { background: lab(50% 40 30); }", "lab(50% 40 30)"),
        (":root { --a: #fff; }\n.x { border-color: hwb(120 10% 20%); }", "hwb(120 10% 20%)"),
        # Casos NÃO citados pelo relatório — provam que a correção enumera a
        # lista COMPLETA da especificação (CSS Color Level 4/5), não a lista
        # de três funções do achado.
        (":root { --a: #fff; }\n.x { color: lch(52% 40 30); }", "lch(52% 40 30)"),
        (":root { --a: #fff; }\n.x { color: oklab(0.5 0.1 0.05); }", "oklab(0.5 0.1 0.05)"),
        (":root { --a: #fff; }\n.x { color: color(display-p3 1 0 0); }", "color(display-p3 1 0 0)"),
        (
            ":root { --a: #fff; }\n.x { background: color-mix(in srgb, red, blue); }",
            "color-mix(in srgb, red, blue)",
        ),
        (
            ":root { --a: #fff; }\n.x { color: device-cmyk(0 1 1 0); }",
            "device-cmyk(0 1 1 0)",
        ),
    ],
)
def test_controle_positivo_detector_de_cor_funcoes_do_css_color_level_4(css_ruim, esperado):
    """Enunciado geral (BL-319): nenhuma cor escapa da varredura, em nenhuma
    notação — provado com a reprodução do achado (`oklch`/`lab`/`hwb`) e com
    funções que NEM o relatório do auditor NEM a lista fechada antiga sequer
    mencionavam (`lch`, `oklab`, `color()`, `color-mix()`, `device-cmyk()`)."""
    achados = _cores_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"a função de cor '{esperado}' escapou do detector: {achados}"


def test_controle_negativo_detector_de_cor_ignora_funcoes_sem_relacao_com_cor():
    """Controle negativo do M1: a lista COMPLETA de funções de cor não pode
    virar uma lista tão ampla que acuse função de LAYOUT/transformação sem
    relação nenhuma com tinta."""
    css = (
        ":root { --a: #fff; }\n"
        ".x { transform: translateX(4px); width: minmax(4px, 1fr); "
        "padding: calc(4px + 1px); color: var(--a); }"
    )
    assert _cores_fora_dos_tokens(css) == [], (
        "funções sem relação com cor (transform/minmax/calc/var) não podiam ter sido acusadas"
    )


# ---------------------------------------------------------------------------
# BL-335 (M3 da auditoria DL-026 rodada 5): "o detector de cor AINDA
# enumera" — `CORES_NOMEADAS_CSS` é o vocabulário do CSS Color Level 3; as
# cores de SISTEMA (`Canvas`, `ButtonFace`, `AccentColor`, `LinkText`...) são
# do Level 4 e não estavam em nenhum dos dois padrões. A correção não
# acrescenta nomes a `CORES_NOMEADAS_CSS` — cria a categoria própria
# `CORES_DE_SISTEMA_CSS`/`_cores_de_sistema_fora_dos_tokens`, com o motivo
# em `MOTIVO_COR_DE_SISTEMA`: o valor de uma cor de sistema é decidido pelo
# SO e pelo tema do usuário, então o par texto/fundo que ela forma não tem
# contraste CALCULÁVEL — diferente de um hexadecimal errado, que é medível.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # As QUATRO propriedades da sabotagem exata do auditor (M3).
        (":root { --a: #fff; }\n.x { color: Canvas; }", "Canvas"),
        (":root { --a: #fff; }\n.x { background: ButtonFace; }", "ButtonFace"),
        (":root { --a: #fff; }\n.x { border-color: AccentColor; }", "AccentColor"),
        (":root { --a: #fff; }\n.x { outline-color: LinkText; }", "LinkText"),
        # Casos NÃO citados pelo relatório — provam que a categoria cobre a
        # seção INTEIRA da especificação (§8.1), não as quatro palavras do
        # achado (a mesma exigência que o BL-319 já fez do lado das funções).
        (":root { --a: #fff; }\n.x { color: Field; }", "Field"),
        (":root { --a: #fff; }\n.x { color: Mark; }", "Mark"),
        (":root { --a: #fff; }\n.x { color: SelectedItem; }", "SelectedItem"),
        (":root { --a: #fff; }\n.x { color: GrayText; }", "GrayText"),
    ],
)
def test_controle_positivo_detector_de_cor_de_sistema(css_ruim, esperado):
    achados = _cores_de_sistema_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"cor de sistema '{esperado}' escapou do detector: {achados}"


def test_controle_positivo_deteccao_de_cor_de_sistema_em_copia_do_base_css(tmp_path):
    """Critério de aceite 1: a sabotagem EXATA do auditor, aplicada a uma
    CÓPIA do `static/css/base.css` REAL do projeto — não um CSS sintético
    qualquer. BL-311 proíbe mutar o repositório para testar; a sabotagem
    acontece só na cópia, em `tmp_path`. Ler o arquivo real (não escrevê-lo)
    é permitido: este arquivo é `apps/core/tests/test_dl024_varredura_de_
    interface.py`, que já lê `static/css/base.css` em outras guardas
    (`ESTILOS`, topo do arquivo) — só nunca o edita."""
    original = (ESTILOS / "base.css").read_text(encoding="utf-8")
    sabotado = original + (
        "\n.sabotagem-cor-de-sistema {\n"
        "    color: Canvas;\n"
        "    background: ButtonFace;\n"
        "    border-color: AccentColor;\n"
        "    outline-color: LinkText;\n"
        "}\n"
    )
    copia = tmp_path / "base.css"
    copia.write_text(sabotado, encoding="utf-8")

    achados = _cores_de_sistema_fora_dos_tokens(copia.read_text(encoding="utf-8"))
    for esperado in ("Canvas", "ButtonFace", "AccentColor", "LinkText"):
        assert esperado in achados, (
            f"a sabotagem exata do auditor (M3, rodada 5) não foi detectada na cópia do "
            f"base.css REAL do projeto: '{esperado}' ausente de {achados}"
        )


def test_controle_positivo_deteccao_de_cor_de_sistema_em_copia_do_base_css_minusculas(tmp_path):
    """Critério de aceite 2 do BL-346: a MESMA sabotagem, em minúsculas —
    nome de CSS não diferencia caixa (o navegador resolve `color: canvas;`
    exatamente como `color: Canvas;`), variante que o arquiteto-senior
    acrescentou à rodada anterior de auditoria."""
    original = (ESTILOS / "base.css").read_text(encoding="utf-8")
    sabotado = original + (
        "\n.sabotagem-cor-de-sistema-minuscula {\n"
        "    color: canvas;\n"
        "    background: buttonface;\n"
        "    border-color: accentcolor;\n"
        "    outline-color: linktext;\n"
        "}\n"
    )
    copia = tmp_path / "base.css"
    copia.write_text(sabotado, encoding="utf-8")

    achados = _cores_de_sistema_fora_dos_tokens(copia.read_text(encoding="utf-8"))
    for esperado in ("canvas", "buttonface", "accentcolor", "linktext"):
        assert esperado in achados, (
            f"a sabotagem em minúsculas não foi detectada na cópia do base.css REAL do "
            f"projeto: '{esperado}' ausente de {achados}"
        )


def test_controle_positivo_deteccao_de_cor_de_sistema_em_atributo_de_template():
    """Critério de aceite 2: a mesma categoria, no caminho de ATRIBUTO que o
    BL-305 abriu — `fill="Canvas"` num elemento de apresentação, sem CSS
    envolvido nenhum."""
    template = '<rect fill="Canvas" stroke="ButtonFace" width="10" height="10"></rect>'
    achados = _cores_de_sistema_em_atributos_de_template(template)
    assert "fill=Canvas" in achados, achados
    assert "stroke=ButtonFace" in achados, achados


def test_controle_negativo_detector_de_cor_de_sistema_token_do_projeto_continua_aprovando():
    """Critério de aceite 3: `var(--tinta-principal)` — um token de verdade
    — não pode ser confundido com cor de sistema."""
    css = ":root { --tinta-principal: #1a1a1a; }\n.x { color: var(--tinta-principal); }"
    assert _cores_de_sistema_fora_dos_tokens(css) == [], (
        "um token do projeto (var(--tinta-principal)) não podia ter sido acusado de cor de sistema"
    )


def test_controle_negativo_detector_de_cor_de_sistema_ignora_cor_nomeada_comum():
    """`red`/`white`/`blue` não são cor de SISTEMA — continuam sendo
    responsabilidade de `_cores_fora_dos_tokens` (`CORES_NOMEADAS_CSS`), não
    desta categoria. As duas guardas não podem se sobrepor nem se confundir
    na mensagem de erro."""
    css = ":root { --a: #fff; }\n.x { color: red; background: white; }"
    assert _cores_de_sistema_fora_dos_tokens(css) == [], (
        "cor nomeada comum (Level 3) não é cor de SISTEMA e não podia ter sido acusada aqui"
    )


def test_controle_negativo_detector_de_cor_de_sistema_respeita_a_definicao_de_token_bl321():
    """Não quebra o BL-321: `--*` continua sendo definição de token onde
    quer que esteja (mesmo hipoteticamente amarrada a uma cor de sistema), e
    `@page` continua isento como bloco — a mesma exceção COMPARTILHADA
    (`_texto_sem_root`) que os outros dois detectores já usam, nunca uma
    reimplementação paralela que pudesse divergir dela."""
    custom_property = ".x { --acento-especial: Canvas; }"
    assert _cores_de_sistema_fora_dos_tokens(custom_property) == [], (
        "custom property é a DEFINIÇÃO do token, em qualquer bloco — nunca uma violação (BL-321)"
    )
    dentro_do_root = ":root { --fundo: Canvas; }\n.x { color: var(--fundo); }"
    assert _cores_de_sistema_fora_dos_tokens(dentro_do_root) == [], (
        "cor de sistema DENTRO do :root é a definição do token, não uma fuga dele"
    )
    dentro_do_page = "@page { margin: 15mm; }\n.x { color: Canvas; }"
    achados = _cores_de_sistema_fora_dos_tokens(dentro_do_page)
    assert "Canvas" in achados, (
        "@page é isento — mas a regra FORA dele (.x) continua sob a varredura normalmente"
    )


# ---------------------------------------------------------------------------
# F4 da auditoria DL-026 rodada 6 (docs/auditorias/2026-09-19-dl-026-rodada-6.md):
# as DEZ linhas exatas que o auditor mediu — cinco declarações de PROPRIEDADE
# QUE ACEITA COR com palavra do §8.2 (Deprecated System Colors), que agora
# reprovam porque o motivo para excluir o §8.2 (risco de falso alarme)
# desapareceu com a restrição de propriedade; e as cinco declarações que
# eram FALSO ALARME antes desta correção (propriedade que NUNCA aceita cor),
# que agora aprovam. Cada linha é a reprodução literal da tabela do achado.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        (":root { --a: #fff; }\n.aviso-do-sistema { color: Menu; }", "Menu"),
        (":root { --a: #fff; }\n.aviso-do-sistema { background: Window; }", "Window"),
        (
            ":root { --a: #fff; }\n.aviso-do-sistema { border-color: ActiveBorder; }",
            "ActiveBorder",
        ),
        (
            ":root { --a: #fff; }\n.aviso-do-sistema { outline-color: InactiveCaptionText; }",
            "InactiveCaptionText",
        ),
        (":root { --a: #fff; }\n.aviso-do-sistema { color: ThreeDFace; }", "ThreeDFace"),
    ],
)
def test_controle_positivo_detector_de_cor_de_sistema_secao_8_2_depreciada(css_ruim, esperado):
    """F4 (rodada 6): as CINCO reprovações da tabela do auditor — palavra do
    §8.2 (`Menu`/`Window`/`ActiveBorder`/`InactiveCaptionText`/`ThreeDFace`)
    numa propriedade que aceita cor de verdade (`color`/`background`/
    `border-color`/`outline-color`). O motivo que excluía o §8.2 no BL-335
    (risco de colidir com identificador legítimo) não se aplica aqui: nestas
    quatro propriedades a palavra SÓ pode ser cor."""
    achados = _cores_de_sistema_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"cor de sistema depreciada '{esperado}' escapou: {achados}"


@pytest.mark.parametrize(
    "css_bom",
    [
        ":root { --a: #fff; }\n.linha-destacada { animation-name: highlight-row; "
        "animation-duration: 1s; }",
        ":root { --a: #fff; }\n.marcador { animation-name: mark-in; }",
        ":root { --a: #fff; }\n.layout { grid-area: canvas; }",
        ":root { --a: #fff; }\n.titulo { font-family: Field Sans; }",
        ":root { --a: #fff; }\n.transicao { view-transition-name: mark; }",
    ],
)
def test_controle_negativo_detector_de_cor_de_sistema_ignora_palavra_fora_de_propriedade_de_cor(
    css_bom,
):
    """F4 (rodada 6): as CINCO aprovações da tabela do auditor — a
    reprodução exata do falso alarme medido na CI
    (`printf '\\n.linha-destacada {\\n    animation-name: highlight-row;\\n'`
    ..., `1 failed`). `highlight`/`mark`/`canvas`/`Field` são tão palavra do
    inglês comum quanto `menu`/`window` já eram — a diferença é que
    `animation-name`, `grid-area`, `font-family` e `view-transition-name`
    NUNCA aceitam cor, então a palavra ali nunca podia ter sido lida como
    tinta de sistema."""
    achados = _cores_de_sistema_fora_dos_tokens(css_bom)
    assert achados == [], f"falso alarme (F4): {achados}"


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("color", True),
        ("background", True),
        ("background-color", True),
        ("border-color", True),
        ("border-top-color", True),
        ("border-inline-end-color", True),
        ("outline-color", True),
        ("outline", True),
        ("fill", True),
        ("stroke", True),
        ("caret-color", True),
        ("text-decoration-color", True),
        ("column-rule-color", True),
        ("accent-color", True),
        ("box-shadow", True),
        ("text-shadow", True),
        ("COLOR", True),  # nome de propriedade não diferencia caixa
        ("animation-name", False),
        ("grid-area", False),
        ("font-family", False),
        ("view-transition-name", False),
        ("color-scheme", False),  # contém "color" mas não TERMINA com ele
        ("forced-color-adjust", False),
        ("print-color-adjust", False),
    ],
)
def test_propriedade_aceita_cor_classifica_corretamente(nome, esperado):
    """Controle direto do filtro que a correção do F4 introduziu — cada
    entrada da tabela é uma decisão que a função precisa acertar, não só o
    resultado agregado dos detectores acima."""
    assert _propriedade_aceita_cor(nome) is esperado, (
        f"'{nome}' deveria classificar como aceita-cor={esperado}"
    )


@pytest.mark.parametrize(
    "css_ruim, propriedade",
    [
        (":root { --esp-3: 12px; }\n.bloco { padding: 12px; }", "padding"),
        (".bloco { margin-top: 0.5rem; }", "margin-top"),
        (".bloco { border-bottom-width: 2px; }", "border-bottom-width"),
        (".bloco { gap: 4px; }", "gap"),
        (".bloco { row-gap: 0.4em; }", "row-gap"),
        (".titulo { font-size: 1.2em; }", "font-size"),
    ],
)
def test_controle_positivo_detector_de_medida_literal(css_ruim, propriedade):
    """O detector que o critério 13 prometia e nunca existiu (BL-274)."""
    achados = _medidas_literais_fora_dos_tokens(css_ruim)
    assert achados, f"o detector deixou passar '{propriedade}' com medida literal"
    assert any(a.startswith(propriedade + ":") for a in achados), achados


def test_controle_negativo_detector_de_medida_literal():
    # M2/BL-293 ACRESCENTOU `width`/`height` à lista de propriedades — este
    # controle negativo não pode mais usar nenhuma das duas como exemplo de
    # "propriedade fora da lista" (era o caso antes da correção, com
    # `height: 12px` propositalmente fora do alcance); `color` continua
    # genuinamente fora, porque não é medida.
    limpo = ".bloco { padding: var(--esp-3); margin: 0; width: 100%; color: red; }"
    achados = _medidas_literais_fora_dos_tokens(limpo)
    assert achados == [], (
        "token via var() sem fallback, valor sem unidade, percentual e "
        f"propriedade que não é medida (color) não podiam ter sido acusados: {achados}"
    )
    # Dentro do :root é a própria definição do token — não é violação.
    token = ":root { --esp-3: 12px; --tipo-lg: 1.2rem; }"
    assert _medidas_literais_fora_dos_tokens(token) == []


# ---------------------------------------------------------------------------
# M2/BL-293 (auditoria DL-026 rodada 2): as CINCO linhas de sabotagem do
# relatório, cada uma reproduzida aqui isolada — cada uma dava "61 passed"
# ANTES desta correção, sozinha em static/css/base.css. Ver a tabela do
# achado M2 em docs/auditorias/2026-09-18-dl-024-rodada-2.md.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # Unidades fora de px/rem/em — pt/cm são justamente o que aparece
        # em folha de impressão (BL-282), que este produto tem.
        (".sab { padding: 12pt; }", "padding: 12pt"),
        (".sab { gap: 3ch; }", "gap: 3ch"),
        (".sab { font-size: 4vh; }", "font-size: 4vh"),
        (".sab { margin: 2cm; }", "margin: 2cm"),
    ],
)
def test_controle_positivo_detector_de_medida_literal_cobre_unidades_do_m2(css_ruim, esperado):
    achados = _medidas_literais_fora_dos_tokens(css_ruim)
    assert esperado in achados, (
        f"medida '{esperado}' escapou do detector (unidade fora de px/rem/em): {achados}"
    )


def test_controle_positivo_detector_de_medida_literal_preserva_fallback_do_var():
    """`var(--nao-existe, 37px)` tinha a variável E o fallback apagados
    juntos por `re.sub(r"var\\([^)]*\\)", "", valor)` — o valor que o
    navegador usa de verdade quando o token não existe escapava por
    inteiro."""
    css = ".sab { padding: var(--nao-existe, 37px); gap: var(--tb, 9px); }"
    achados = _medidas_literais_fora_dos_tokens(css)
    assert "padding: 37px" in achados, achados
    assert "gap: 9px" in achados, achados


def test_controle_positivo_detector_de_medida_literal_cobre_propriedades_novas_do_m2():
    """`width`/`line-height`/`letter-spacing`/`border-radius`/`inset`/`top`
    não estavam na lista de propriedades — nenhuma das seis dava achado."""
    css = (
        ".sab { width: 517px; line-height: 31px; letter-spacing: 0.37em; "
        "border-radius: 9px; inset: 13px; top: 7rem; }"
    )
    achados = _medidas_literais_fora_dos_tokens(css)
    for esperado in (
        "width: 517px",
        "line-height: 31px",
        "letter-spacing: 0.37em",
        "border-radius: 9px",
        "inset: 13px",
        "top: 7rem",
    ):
        assert esperado in achados, f"'{esperado}' escapou do detector: {achados}"


def test_controle_positivo_detector_de_medida_literal_cobre_atalho_border_e_outline():
    """`border: 3px solid ...`/`outline: 5px solid ...` são o ATALHO mais
    comum de escrever largura de borda — a lista antiga só tinha
    `border(?:-[a-z]+)*-width`, que não casa o atalho sem sufixo."""
    css = ".sab { border: 3px solid var(--cor-borda); outline: 5px solid var(--cor-borda); }"
    achados = _medidas_literais_fora_dos_tokens(css)
    assert "border: 3px" in achados, achados
    assert "outline: 5px" in achados, achados


# ---------------------------------------------------------------------------
# BL-313 (M4 da auditoria DL-026 rodada 3): o detector, ANTES da inversão,
# fechava as CINCO sabotagens do relatório da rodada 2 e continuava cego
# para a FAMÍLIA — a tabela abaixo é a reprodução literal das duas linhas
# que o auditor mediu passando (`74 passed`), mais casos que o relatório
# NÃO citou, para provar que a guarda agora está presa ao REQUISITO
# ("nenhuma propriedade, nenhuma unidade escapa"), não à lista do achado.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # Reprodução EXATA da primeira linha do achado M4: `(?<![\w-])`
        # antes de `width`/`height` era negado pelo próprio hífen de
        # `max-`/`min-` — as quatro combinações citadas pelo auditor.
        (".sab { max-width: 517px; }", "max-width: 517px"),
        (".sab { min-width: 42px; }", "min-width: 42px"),
        (".sab { max-height: 300px; }", "max-height: 300px"),
        (".sab { min-height: 42px; }", "min-height: 42px"),
        # Segunda linha do achado: propriedades inteiramente FORA da lista
        # antiga (não eram variante de prefixo/sufixo de nada que já
        # existisse lá).
        (".sab { box-shadow: 0 0 7px var(--c); }", "box-shadow: 7px"),
        (".sab { flex-basis: 250px; }", "flex-basis: 250px"),
        (".sab { text-indent: 19px; }", "text-indent: 19px"),
        (".sab { column-width: 12em; }", "column-width: 12em"),
    ],
)
def test_controle_positivo_detector_de_medida_literal_cobre_a_familia_de_propriedades(
    css_ruim, esperado
):
    achados = _medidas_literais_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"'{esperado}' escapou do detector invertido: {achados}"


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # Reprodução exata da segunda linha do achado M4: as seis unidades
        # que a lista antiga não tinha.
        (".sab { font-size: 2lh; }", "font-size: 2lh"),
        (".sab { gap: 3rlh; }", "gap: 3rlh"),
        (".sab { padding: 1.5cap; }", "padding: 1.5cap"),
        (".sab { margin: 4ic; }", "margin: 4ic"),
        (".sab { font-size: 1rex; }", "font-size: 1rex"),
        (".sab { width: 5rch; }", "width: 5rch"),
    ],
)
def test_controle_positivo_detector_de_medida_literal_cobre_as_unidades_do_m4(css_ruim, esperado):
    achados = _medidas_literais_fora_dos_tokens(css_ruim)
    assert esperado in achados, f"'{esperado}' escapou do detector invertido: {achados}"


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        # CASOS NÃO CITADOS pelo relatório do auditor — provam que a
        # inversão cobre a CLASSE, não a lista literal do achado. Nenhuma
        # destas seis (nem a propriedade, nem a unidade) aparece na tabela
        # do M4.
        (".sab { transform: translateX(7px); }", "transform: 7px"),
        (".sab { scroll-margin-top: 3em; }", "scroll-margin-top: 3em"),
        (".sab { aspect-ratio: 16 / 9; }", None),  # controle negativo: sem unidade, não acusa
        (".sab { grid-template-columns: 12rem 1fr; }", "grid-template-columns: 12rem"),
        (".sab { background-position: 4px 9px; }", "background-position: 4px"),
        (".sab { width: 3cqw; }", "width: 3cqw"),  # unidade de container query
    ],
)
def test_controle_positivo_detector_de_medida_literal_cobre_casos_alem_do_relatorio(
    css_ruim, esperado
):
    """Enunciado geral (BL-313): nenhuma medida literal escapa, em nenhuma
    propriedade e nenhuma unidade — provado com propriedades e unidades
    que NEM o relatório do auditor nem a lista antiga sequer mencionavam
    (`transform`, `scroll-margin-top`, `grid-template-columns`,
    `background-position`, e a unidade de consulta de contêiner `cqw`)."""
    achados = _medidas_literais_fora_dos_tokens(css_ruim)
    if esperado is None:
        assert achados == [], f"valor sem unidade de medida não devia ter sido acusado: {achados}"
    else:
        assert esperado in achados, f"'{esperado}' escapou do detector invertido: {achados}"


def test_controle_negativo_detector_de_medida_literal_respeita_a_lista_de_excecoes():
    """`PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL` é o escape nomeado — uma
    propriedade nela declarada não é acusada, mesmo com unidade literal no
    valor. O teste usa `monkeypatch` sobre a lista real (hoje vazia por
    decisão: `static/css/base.css` não tem exceção nenhuma) para provar
    que o MECANISMO de exceção funciona, sem depender de uma exceção real
    existir hoje."""
    import apps.core.tests.test_dl024_varredura_de_interface as modulo

    original = dict(modulo.PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL)
    try:
        modulo.PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL["propriedade-de-teste"] = (
            "exceção sintética só deste teste, nunca usada em produção"
        )
        achados = _medidas_literais_fora_dos_tokens(".sab { propriedade-de-teste: 12px; }")
        assert achados == [], f"a exceção nomeada não impediu o achado: {achados}"
        # Controle: a mesma unidade, em propriedade FORA da lista de
        # exceções, continua sendo acusada — a exceção é NOMEADA, não
        # afrouxa o detector inteiro.
        achados_normais = _medidas_literais_fora_dos_tokens(".sab { padding: 12px; }")
        assert achados_normais == ["padding: 12px"]
    finally:
        modulo.PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL.clear()
        modulo.PROPRIEDADES_QUE_ACEITAM_MEDIDA_LITERAL.update(original)


# ---------------------------------------------------------------------------
# BL-321 (M3 da auditoria DL-026 rodada 4): a inversão do detector de
# MEDIDA (BL-313) acusava CSS legítimo — falso positivo em mecanismo de CI,
# mais corrosivo que falso negativo, porque ensina que a guarda erra. Os
# dois blocos exatos que o auditor mediu reprovando, mais casos que o
# relatório NÃO cita.
# ---------------------------------------------------------------------------


def test_controle_negativo_custom_property_fora_do_root_nao_e_violacao():
    """Reprodução EXATA do primeiro bloco do M3: `--espaco-de-impressao`
    definida DENTRO de `@media print { .folha { ... } }`, fora do `:root`.
    Uma custom property é a DEFINIÇÃO de um token onde quer que esteja
    escrita — escopar um token a uma classe (modo de impressão, densidade
    alternativa) é a forma padrão de fazer isso em CSS."""
    css = "@media print {\n  .folha { --espaco-de-impressao: 2mm; }\n}\n"
    assert _medidas_literais_fora_dos_tokens(css) == [], (
        "custom property fora do :root foi acusada de medida literal solta"
    )
    assert _cores_fora_dos_tokens(css) == []


def test_controle_negativo_at_page_nao_e_violacao():
    """Reprodução EXATA do segundo bloco do M3: `@page` é a ÚNICA forma de
    declarar margem de impressão em CSS — isento como BLOCO, não só a
    propriedade `margin` (isso liberaria `margin` na folha inteira)."""
    css = "@page { size: A4; margin: 15mm; }\n"
    assert _medidas_literais_fora_dos_tokens(css) == [], (
        "@page foi acusado de medida literal — a única forma de declarar margem de impressão"
    )


def test_controle_negativo_at_page_isento_e_bloco_nao_so_a_propriedade_margin():
    """Caso NÃO citado pelo relatório: se a isenção de `@page` fosse por
    NOME de propriedade (`margin`), qualquer OUTRA propriedade com medida
    literal dentro de `@page` continuaria escapando por acidente — mas
    também `margin` fora de `@page`, na folha inteira, deixaria de ser
    fiscalizada. Prova as duas metades: dentro de `@page`, `size`/`margin`
    E uma terceira propriedade nunca vista antes (`marks`, layout de
    impressão) não são acusadas; fora de `@page`, `margin` continua
    reprovando normalmente."""
    dentro = "@page { size: A4; margin: 15mm; marks: crop 4mm; }\n"
    assert _medidas_literais_fora_dos_tokens(dentro) == []

    fora = ".bloco { margin: 15mm; }\n"
    achados = _medidas_literais_fora_dos_tokens(fora)
    assert achados == ["margin: 15mm"], (
        "isentar @page por nome de propriedade vazaria a isenção para a folha inteira: "
        + repr(achados)
    )


def test_controle_negativo_root_em_seletor_agrupado_continua_isento():
    """Terceiro caso do M3, registrado como "anterior à inversão e agora
    amplificado": `:root, ::backdrop { ... }` (o padrão recomendado para
    tornar tokens visíveis ao `::backdrop`) perdia a isenção do `:root`
    INTEIRA, nos DOIS detectores, porque a isenção exigia `{` imediatamente
    depois de `:root`."""
    css_medida = ":root, ::backdrop { --tinta: #1d3a6e; --espaco: 4px; }\n"
    assert _medidas_literais_fora_dos_tokens(css_medida) == []
    assert _cores_fora_dos_tokens(css_medida) == []

    # Caso NÃO citado pelo relatório: a mesma isenção, com o `:root` em
    # SEGUNDA posição do grupo (o achado só media a ordem "root primeiro").
    css_ordem_invertida = "::backdrop, :root { --espaco: 4px; }\n"
    assert _medidas_literais_fora_dos_tokens(css_ordem_invertida) == []

    # Caso NÃO citado: pseudo-classe encadeada direto no :root, sem vírgula.
    css_encadeado = ":root:not(.compacto) { --espaco: 4px; }\n"
    assert _medidas_literais_fora_dos_tokens(css_encadeado) == []


def test_controle_negativo_custom_property_com_cor_fora_do_root_nao_e_violacao():
    """Caso NÃO citado pelo relatório (o M3 só exemplificou com MEDIDA): a
    MESMA regra vale para o detector de COR — uma custom property que
    define uma cor (inclusive com a notação nova do BL-319, `oklch()`)
    fora do `:root` é a definição do token, nunca uma violação."""
    css = "@media print {\n  .folha { --acento-oklch: oklch(0.6 0.2 30); }\n}\n"
    assert _cores_fora_dos_tokens(css) == [], (
        "custom property de cor fora do :root foi acusada: " + repr(_cores_fora_dos_tokens(css))
    )


def test_controle_negativo_seletor_parecido_com_root_nao_e_isento():
    """Controle de que a isenção não é enganada por SUBSTRING: um seletor
    de classe chamado `.root-like` (contém "root" mas não É `:root`) não
    pode ficar isento — a MEDIDA solta dentro dele continua reprovando,
    mesmo que a CUSTOM PROPERTY vizinha, na mesma regra, continue isenta
    por ser custom property (não por o bloco estar isento)."""
    css = ".root-like { --x: 12px; padding: 12px; }\n"
    achados = _medidas_literais_fora_dos_tokens(css)
    assert achados == ["padding: 12px"], (
        "um seletor só PARECIDO com :root não pode herdar a isenção do bloco: " + repr(achados)
    )


def test_controle_positivo_detector_de_cor_preserva_fallback_do_var():
    """Mesma causa do M2 acima, no detector de COR: `color: var(--x, red)`
    tinha a cor de reserva apagada junto com a variável."""
    css = (
        ":root { --a: #fff; }\n.sab { color: var(--nao-existe, red); background: var(--x, white); }"
    )
    achados = _cores_fora_dos_tokens(css)
    assert "red" in achados, achados
    assert "white" in achados, achados


def test_controle_positivo_detector_de_css_em_qualquer_subpasta(tmp_path):
    """BL-274 #2/#3: `static/css/modulos/x.css` e `static/tema.css` escapavam."""
    (tmp_path / "static" / "css" / "modulos").mkdir(parents=True)
    (tmp_path / "static" / "css" / "modulos" / "fiscal.css").write_text(
        ":root { --a: #fff; }\n.x { color: #ff0000; }", encoding="utf-8"
    )
    (tmp_path / "static" / "tema.css").write_text(
        ":root { --a: #fff; }\n.y { color: #00ff00; }", encoding="utf-8"
    )
    (tmp_path / "static" / "css").mkdir(parents=True, exist_ok=True)
    (tmp_path / "static" / "css" / "base.css").write_text(
        ":root { --a: #fff; }\n.z { color: var(--a); }", encoding="utf-8"
    )
    achadas = {str(p.relative_to(tmp_path)) for p in _folhas_de_estilo_do_projeto(tmp_path)}
    assert "static/css/modulos/fiscal.css" in achadas, "CSS em subpasta de static/css/ escapou"
    assert "static/tema.css" in achadas, "CSS fora de static/css/ escapou"
    assert "static/css/base.css" in achadas


# ---------------------------------------------------------------------------
# A3/BL-291 (auditoria DL-026 rodada 2): a varredura de TEMPLATES só olhava
# `templates/` na raiz, cega para `apps/<app>/templates/` — que
# `config/settings.py` (`"APP_DIRS": True`) faz o Django resolver
# normalmente. Reprodução da sabotagem exata do auditor, isolada em
# `tmp_path`.
# ---------------------------------------------------------------------------


def test_controle_positivo_detector_de_templates_em_apps_do_projeto(tmp_path):
    """`apps/fiscal/templates/fiscal/apuracao.html` — a tela exata que o
    auditor criou, resolvida pelo Django e nunca lida pela varredura.
    Confirma que `_templates()` agora ALCANÇA o arquivo e que, alcançado,
    cada guarda de conteúdo aplicável reprova nomeando-o: sem `{% extends
    %}`, sem `<caption>`, `<th>` sem `scope`, valor `_ptbr` em célula sem a
    classe do sistema, e estilo embutido.

    BL-309 (A3 da auditoria DL-026 rodada 3): a SEXTA guarda — a de
    EXISTÊNCIA de módulo (`test_modulo_novo_declara_o_seu_momento_da_
    verdade`) — não estava neste controle, e era exatamente a única que
    continuava cega para `apps/<app>/templates/`. Acrescenta um segundo
    template, `apps/cobranca/templates/cobranca/titulos.html` — o caso
    exato que o auditor mediu (`74 passed` nesta origem, `1 failed` na
    origem antiga, para o MESMO arquivo) —, e prova que
    `_pastas_de_modulo_com_tela` agora enxerga as duas pastas de módulo
    desta árvore, apps-based e legada."""
    pasta = tmp_path / "apps" / "fiscal" / "templates" / "fiscal"
    pasta.mkdir(parents=True)
    arquivo = pasta / "apuracao.html"
    arquivo.write_text(
        '<html><body style="color:#ff0000">\n'
        "<table>\n"
        "<tr><th>Doc</th><th>Valor</th></tr>\n"
        "<tr><td>NF</td><td>{{ nota.valor_ptbr }}</td></tr>\n"
        "</table>\n"
        "</body></html>",
        encoding="utf-8",
    )

    achados = {str(p.relative_to(tmp_path)) for p in _templates(tmp_path)}
    caminho_relativo = "apps/fiscal/templates/fiscal/apuracao.html"
    assert caminho_relativo in achados, (
        "a varredura de templates continua cega para apps/<app>/templates/"
    )

    texto = arquivo.read_text(encoding="utf-8")

    # 1) extends ausente
    assert "{% extends" not in _sem_comentarios_de_template(texto)
    # 2) caption ausente (tem <table>, não tem <caption>)
    limpo = _sem_comentarios_de_template(texto)
    assert len(re.findall(r"<table\b", limpo, re.IGNORECASE)) > len(
        re.findall(r"<caption\b", limpo, re.IGNORECASE)
    )
    # 3) <th> sem scope
    assert _cabecalhos_sem_escopo(texto), "os dois <th> sem scope não foram detectados"
    # 4) valor _ptbr em célula sem a classe do sistema
    assert _valores_sem_classe(texto), (
        "a célula com {{ nota.valor_ptbr }} sem classe não foi detectada"
    )
    # 5) estilo embutido
    assert _estilos_embutidos(texto), "o style embutido no <body> não foi detectado"

    # E o relato, quando esta guarda roda de verdade contra a árvore, NOMEIA
    # o arquivo — mesmo formato que `test_controle_involucro_nao_afrouxa_o_
    # relato_por_arquivo` já prova para o detector de valor sem classe.
    ofensores_valor = [
        f"{arquivo.relative_to(tmp_path)}: {valor} em {celula}"
        for celula, valor in _valores_sem_classe(texto)
    ]
    assert ofensores_valor and caminho_relativo in ofensores_valor[0]

    # 6) EXISTÊNCIA de módulo — a guarda que faltava neste controle. Um
    # segundo módulo, "Cobrança", nascendo SÓ na origem apps-based: sem
    # esta correção, `_pastas_de_modulo_com_tela` (herdeira de `TEMPLATES.
    # iterdir()`) devolveria só o que existisse em `templates/` na raiz —
    # neste `tmp_path`, nada — e "cobranca" nunca chegaria a ser cobrado
    # pela guarda real.
    pasta_cobranca = tmp_path / "apps" / "cobranca" / "templates" / "cobranca"
    pasta_cobranca.mkdir(parents=True)
    (pasta_cobranca / "titulos.html").write_text(
        '{% extends "base.html" %}\n'
        "{% block conteudo %}\n"
        "<table><caption>Títulos</caption>\n"
        '<tr><th scope="col">Valor</th></tr>\n'
        '<tr><td class="valor-monetario">{{ titulo.valor_ptbr }}</td></tr>\n'
        "</table>\n"
        "{% endblock %}",
        encoding="utf-8",
    )
    pastas = _pastas_de_modulo_com_tela(tmp_path)
    assert pastas == {"fiscal", "cobranca"}, (
        "a existência de módulo continua cega para apps/<app>/templates/: " + repr(pastas)
    )


def test_controle_a_existencia_de_modulo_reconhece_as_duas_origens_do_mesmo_nome(tmp_path):
    """BL-309: o par exato que o auditor mediu — o MESMO módulo, "Cobrança",
    servido pelas duas origens que o Django resolve. Reprodução literal da
    tabela do achado A3 (`docs/auditorias/2026-09-18-dl-024-rodada-3.md`):
    `apps/cobranca/templates/cobranca/titulos.html` (74 passed) contra
    `templates/cobranca/titulos.html` (1 failed, MESMO arquivo). Prova as
    duas metades: cada origem sozinha já basta para `_pastas_de_modulo_com_
    tela` reconhecer "cobranca", e as duas JUNTAS não duplicam o módulo
    (continua um `{"cobranca"}`, não `{"cobranca", "cobranca"}` — óbvio para
    um `set`, mas é a garantia de que um módulo migrando de origem não vira
    dois módulos na tabela)."""
    conteudo = (
        '{% extends "base.html" %}\n'
        "{% block conteudo %}<table><caption>Títulos</caption>"
        '<tr><th scope="col">Valor</th></tr>'
        '<tr><td class="valor-monetario">{{ titulo.valor_ptbr }}</td></tr>'
        "</table>{% endblock %}"
    )

    so_origem_nova = tmp_path / "nova"
    pasta_nova = so_origem_nova / "apps" / "cobranca" / "templates" / "cobranca"
    pasta_nova.mkdir(parents=True)
    (pasta_nova / "titulos.html").write_text(conteudo, encoding="utf-8")
    assert _pastas_de_modulo_com_tela(so_origem_nova) == {"cobranca"}

    so_origem_legada = tmp_path / "legada"
    pasta_legada = so_origem_legada / "templates" / "cobranca"
    pasta_legada.mkdir(parents=True)
    (pasta_legada / "titulos.html").write_text(conteudo, encoding="utf-8")
    assert _pastas_de_modulo_com_tela(so_origem_legada) == {"cobranca"}

    ambas = tmp_path / "ambas"
    pasta_ambas_nova = ambas / "apps" / "cobranca" / "templates" / "cobranca"
    pasta_ambas_nova.mkdir(parents=True)
    (pasta_ambas_nova / "titulos.html").write_text(conteudo, encoding="utf-8")
    pasta_ambas_legada = ambas / "templates" / "cobranca"
    pasta_ambas_legada.mkdir(parents=True)
    (pasta_ambas_legada / "titulos.html").write_text(conteudo, encoding="utf-8")
    assert _pastas_de_modulo_com_tela(ambas) == {"cobranca"}


# ---------------------------------------------------------------------------
# BL-320 (M2 da auditoria DL-026 rodada 4): a guarda do "momento da verdade"
# reconhecia só DUAS formas de caminho, escritas à mão ("apps/" e
# "templates/") — o auditor mediu uma TERCEIRA forma escapando
# (`templates/cobranca.html`, sem subpasta), porque a exclusão de
# `base.html` era feita por PROFUNDIDADE de caminho, não por NOME de
# moldura. As três linhas da tabela do achado, reproduzidas abaixo, mais
# casos que a tabela do relatório NÃO cita.
# ---------------------------------------------------------------------------


def test_controle_as_tres_formas_da_tabela_do_achado_m2(tmp_path):
    """Requisito do enunciado do BL-320 (o texto do critério 13, última
    cláusula): toda tela que o Django resolve está sujeita à guarda do
    "momento da verdade" — as TRÊS linhas exatas medidas pelo auditor: o
    MESMO módulo "Cobrança", em três caminhos diferentes. As duas primeiras
    já funcionavam desde o BL-309; a terceira (sem subpasta) é o achado
    desta rodada."""
    via_apps = tmp_path / "via_apps"
    (via_apps / "apps" / "cobranca" / "templates" / "cobranca").mkdir(parents=True)
    (via_apps / "apps" / "cobranca" / "templates" / "cobranca" / "titulos.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    assert "cobranca" in _pastas_de_modulo_com_tela(via_apps), (
        "apps/cobranca/templates/cobranca/titulos.html deixou de ser reconhecido"
    )

    via_templates_com_subpasta = tmp_path / "via_templates_com_subpasta"
    (via_templates_com_subpasta / "templates" / "cobranca").mkdir(parents=True)
    (via_templates_com_subpasta / "templates" / "cobranca" / "titulos.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    assert "cobranca" in _pastas_de_modulo_com_tela(via_templates_com_subpasta), (
        "templates/cobranca/titulos.html deixou de ser reconhecido"
    )

    via_templates_sem_subpasta = tmp_path / "via_templates_sem_subpasta"
    (via_templates_sem_subpasta / "templates").mkdir(parents=True)
    (via_templates_sem_subpasta / "templates" / "cobranca.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    assert "cobranca" in _pastas_de_modulo_com_tela(via_templates_sem_subpasta), (
        "templates/cobranca.html (SEM subpasta) é a terceira forma de caminho "
        "medida pelo auditor — continua escapando"
    )


def test_controle_negativo_moldura_excluida_por_nome_nao_por_profundidade(tmp_path):
    """`base.html` não é módulo — mas a exclusão precisa ser por NOME, não
    por profundidade de caminho (era essa a causa do achado M2: a mesma
    condição `len(partes) >= 3` que excluía `base.html` também excluía
    QUALQUER outra tela de módulo único no mesmo nível). Prova as duas
    metades na MESMA pasta e profundidade: `base.html` é excluído,
    `cobranca.html` (vizinho, mesmo nível) não é."""
    pasta = tmp_path / "templates"
    pasta.mkdir(parents=True)
    (pasta / "base.html").write_text("<html></html>", encoding="utf-8")
    (pasta / "cobranca.html").write_text("<html></html>", encoding="utf-8")
    pastas = _pastas_de_modulo_com_tela(tmp_path)
    assert "base" not in pastas, "base.html não pode virar um módulo chamado 'base'"
    assert pastas == {"cobranca"}, (
        "a exclusão de base.html não pode arrastar uma tela vizinha do mesmo nível: " + repr(pastas)
    )


def test_controle_novo_dir_em_settings_templates_e_reconhecido_sem_editar_este_arquivo(
    tmp_path, settings
):
    """Requisito do BL-320: "derivar as origens de settings.TEMPLATES", não
    de dois prefixos de caminho escritos à mão. Caso NÃO citado pelo
    relatório do auditor (que só recomendou o experimento em prosa — "um
    controle em tmp_path com um DIRS adicional" — sem caso concreto): um
    TERCEIRO `DIRS` (`ui/`), que nenhum módulo do projeto usa hoje, precisa
    ser reconhecido pela guarda sem que este arquivo seja editado — prova
    de que a derivação é de verdade a partir da CONFIGURAÇÃO, não de uma
    lista fechada de nomes de pasta. `BASE_DIR` é sobrescrito junto com
    `TEMPLATES` para que os DIRS (sempre absolutos, como a configuração
    real) apontem para dentro de `tmp_path`, no mesmo padrão em que
    `raiz` já representa "uma cópia de BASE_DIR" nos outros controles
    deste arquivo."""
    settings.BASE_DIR = tmp_path
    settings.TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [tmp_path / "templates", tmp_path / "ui"],
            "APP_DIRS": False,
            "OPTIONS": {},
        }
    ]
    pasta = tmp_path / "ui" / "honorarios"
    pasta.mkdir(parents=True)
    (pasta / "resumo.html").write_text("<html></html>", encoding="utf-8")

    pastas = _pastas_de_modulo_com_tela(tmp_path)
    assert "honorarios" in pastas, (
        "um DIRS novo em settings.TEMPLATES continua invisível para a guarda: " + repr(pastas)
    )


def test_controle_negativo_detector_de_css_ignora_pastas_de_dependencia_e_build(tmp_path):
    (tmp_path / ".venv" / "pacote").mkdir(parents=True)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (tmp_path / ".venv" / "pacote" / "vendor.css").write_text(".x{color:red}", encoding="utf-8")
    (tmp_path / "staticfiles").mkdir()
    (tmp_path / "staticfiles" / "coletado.css").write_text(".x{color:red}", encoding="utf-8")
    achadas = _folhas_de_estilo_do_projeto(tmp_path)
    assert achadas == [], "CSS de dependência/build entrou na varredura do produto"


@pytest.mark.parametrize("nome_da_pasta", [".venv", "venv", "env", "ambiente-xyz"])
def test_controle_positivo_detector_de_css_ignora_ambiente_virtual_de_nome_qualquer(
    tmp_path, nome_da_pasta
):
    """Achado 1 da revisão do arquiteto-senior: o `.gitignore` autoriza
    `.venv/` **e** `venv/` (linhas 6-7), e uma lista de nomes só cobre o
    apelido já visto — `ambiente-xyz` e `env` provam que a exclusão não
    depende de nenhum nome específico, só da presença real de `pyvenv.cfg`
    (`_dentro_de_ambiente_virtual`)."""
    ambiente = tmp_path / nome_da_pasta / "lib" / "site-packages" / "django" / "contrib" / "admin"
    ambiente.mkdir(parents=True)
    (tmp_path / nome_da_pasta / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (ambiente / "base.css").write_text(".x{color:#79aec8}", encoding="utf-8")
    achadas = _folhas_de_estilo_do_projeto(tmp_path)
    assert achadas == [], (
        f"CSS dentro de ambiente virtual chamado '{nome_da_pasta}' entrou na varredura do produto"
    )


def test_controle_negativo_detector_de_css_nao_exclui_por_substring_venv_no_caminho(tmp_path):
    """Pasta do PRODUTO cujo nome contém a substring 'venv' não pode ser
    excluída por coincidência de texto — sem `pyvenv.cfg` de verdade, ela
    continua sendo varrida."""
    pasta = tmp_path / "static" / "css"
    pasta.mkdir(parents=True)
    (pasta / "venv-tema.css").write_text(
        ":root { --a: #fff; }\n.z { color: red; }", encoding="utf-8"
    )
    achadas = {str(p.relative_to(tmp_path)) for p in _folhas_de_estilo_do_projeto(tmp_path)}
    assert "static/css/venv-tema.css" in achadas, (
        "CSS do produto foi excluído só por ter 'venv' no nome do arquivo, sem pyvenv.cfg"
    )


def test_controle_positivo_detector_de_estilo_embutido():
    """BL-274 #5: aspas simples e `<style>` embutido escapavam."""
    assert _estilos_embutidos("<div style='color: red'>x</div>"), "aspas simples não detectadas"
    assert _estilos_embutidos('<div style="color: red">x</div>'), "aspas duplas não detectadas"
    assert _estilos_embutidos("<style>.x{color:red}</style>"), "<style> embutido não detectado"


# ---------------------------------------------------------------------------
# M1/BL-292 (auditoria DL-026 rodada 2): as QUATRO amostras exatas do
# relatório — `style=` sem aspas é HTML5 válido (sem espaço/aspas/=/<>/
# crase) e o Chromium aplica; `<div data-style="cor">` continha a
# substring `style="cor"` e era um falso POSITIVO real. Confirmado pelo
# auditor: `<td id=alvo style=color:red;font-size:22px>` renderizava
# `rgb(255, 0, 0)` no Chromium 1194.
# ---------------------------------------------------------------------------


def test_controle_negativo_detector_de_estilo_embutido_ignora_atributos_comuns():
    """`data-style="x"` (não `data-style-alvo`, que NUNCA disparava o
    defeito e por isso não provava nada) é o caso que o commit `d8ec169`
    errou: a substring `style="x"` está contida em `data-style="x"`, e sem
    o lookbehind `(?<![\\w-])` a guarda achava que era um `style=` real."""
    limpo = '<div class="valor-monetario" data-style="x">y</div>'
    assert _estilos_embutidos(limpo) == [], (
        "falso positivo: 'data-style=\"x\"' foi confundido com 'style=\"x\"' real"
    )


def test_controle_positivo_detector_de_estilo_embutido_sem_aspas():
    """`<td style=color:red>` era um falso NEGATIVO real: valor de atributo
    sem aspas é HTML5 válido, e escapava ao mesmo tempo do detector de
    estilo, do de cor e do de medida — a tríade inteira do critério 13."""
    assert _estilos_embutidos("<td style=color:red>1</td>"), "style sem aspas não detectado"
    assert _estilos_embutidos('<td STYLE="color:red">1</td>'), "STYLE maiúsculo não detectado"
    assert _estilos_embutidos('<td style = "color:red">1</td>'), (
        "style com espaço ao redor do '=' não detectado"
    )
    assert _estilos_embutidos("<td style=color:red;font-size:22px>1</td>"), (
        "a amostra exata confirmada no Chromium pelo auditor não foi detectada"
    )


# ---------------------------------------------------------------------------
# BL-305 (§3 da auditoria DL-026 rodada 4): a varredura não tinha detector
# de cor/medida em ATRIBUTO de template. Reprodução literal da sabotagem do
# auditor, mais casos que o relatório NÃO cita.
# ---------------------------------------------------------------------------


def test_controle_positivo_atributo_de_apresentacao_reproducao_literal_do_achado():
    """Reprodução EXATA da sabotagem medida na §3: `<svg><rect
    fill="#ff0000" width="10" height="10">` num template — "não é só cor,
    medida em atributo de apresentação também passa"."""
    html = '<svg><rect fill="#ff0000" width="10" height="10"></rect></svg>'
    achados = _cores_e_medidas_em_atributos_de_template(html)
    assert any(a.startswith("fill=") for a in achados), (
        f"cor no atributo 'fill' do SVG não foi detectada: {achados}"
    )
    assert any(a.startswith("width=") for a in achados), (
        f"medida (sem unidade) no atributo 'width' do SVG não foi detectada: {achados}"
    )
    assert any(a.startswith("height=") for a in achados), (
        f"medida (sem unidade) no atributo 'height' do SVG não foi detectada: {achados}"
    )


def test_controle_positivo_atributo_de_apresentacao_cor_com_unidade_explicita_fora_do_svg():
    """Caso NÃO citado pelo relatório: cor com NOTAÇÃO EXPLÍCITA (hex,
    função CSS Color Level 4 — BL-319) num atributo de apresentação FORA de
    qualquer `<svg>` também é achado — o sinal de cor não depende de estar
    dentro de SVG, só o sinal de MEDIDA SEM unidade depende."""
    html = '<div data-cor="oklch(0.7 0.2 20)"></div>'
    achados = _cores_e_medidas_em_atributos_de_template(html)
    assert any("oklch(0.7 0.2 20)" in a for a in achados), achados


def test_controle_positivo_atributo_de_apresentacao_cor_nomeada():
    """Caso NÃO citado pelo relatório: cor NOMEADA (`red`) como valor
    inteiro de um atributo de apresentação também é achado — o mesmo
    critério (BL-274 #2) que já vale para CSS."""
    html = '<rect fill="red"></rect>'
    achados = _cores_e_medidas_em_atributos_de_template(html)
    assert any(a.startswith("fill=") for a in achados), achados


def test_controle_positivo_atributo_de_apresentacao_medida_com_unidade_explicita():
    """Caso NÃO citado pelo relatório: medida com UNIDADE explícita
    (`12px`) num atributo de apresentação também é achado, mesmo fora de
    `<svg>` — o sinal de medida COM unidade não depende de contexto SVG."""
    html = '<div data-largura="12px"></div>'
    achados = _cores_e_medidas_em_atributos_de_template(html)
    assert any("12px" in a for a in achados), achados


def test_controle_negativo_atributo_de_apresentacao_numero_puro_fora_do_svg_nao_e_acusado():
    """Controle contra falso positivo: um número puro (sem unidade) em
    `width`/`height` FORA de um bloco `<svg>` não é acusado — fora do SVG a
    especificação não garante que o número seja um comprimento (ex.:
    `<canvas width="600">`, uma dimensão técnica real de superfície de
    desenho, não uma medida que deveria vir de token)."""
    html = '<canvas width="600" height="400"></canvas>'
    assert _cores_e_medidas_em_atributos_de_template(html) == []


def test_controle_negativo_atributo_de_apresentacao_numeros_comuns_de_html_nao_sao_acusados():
    """Controle contra falso positivo: atributos numéricos comuns de HTML
    (`colspan`, `rowspan`, `tabindex`, `maxlength`) não estão na lista
    FECHADA de atributos de comprimento do SVG e não são acusados, mesmo
    dentro de uma tabela real do produto."""
    html = (
        '<table><tr><td colspan="2" rowspan="1">x</td></tr></table>'
        '<input tabindex="0" maxlength="255">'
    )
    assert _cores_e_medidas_em_atributos_de_template(html) == []


def test_controle_negativo_atributo_de_apresentacao_classe_do_sistema_nao_e_acusada():
    """Controle contra falso positivo: o próprio atributo `class` do
    sistema de tokens (`valor-monetario`, `linha-total__veredito`) não pode
    disparar o detector."""
    html = '<td class="valor-monetario linha-total__veredito">{{ x_ptbr }}</td>'
    assert _cores_e_medidas_em_atributos_de_template(html) == []


def test_controle_negativo_geometria_de_symbol_nao_e_acusada():
    """DL-042: geometria (sem unidade) DENTRO de `<symbol>` — a definição do
    glifo de um ícone embutido, nunca um elemento renderizado por conta
    própria — não é acusada como medida solta. O tamanho REAL do ícone na
    tela vem de CSS tokenizado (`.icone-menu`), aplicado ao `<svg>` que usa
    o ícone via `<use>`, nunca ao `<symbol>`."""
    html = (
        '<svg style="display: none">'
        '<symbol id="icone-exemplo" viewBox="0 0 24 24">'
        '<rect x="4" y="9" width="7" height="11" stroke-width="1.5"></rect>'
        '<circle cx="12" cy="8.5" r="3.25"></circle>'
        "</symbol>"
        "</svg>"
    )
    assert _cores_e_medidas_em_atributos_de_template(html) == []


def test_controle_positivo_cor_dentro_de_symbol_continua_acusada():
    """DL-042: a exceção de geometria (acima) NÃO isenta cor — um ícone que
    declarasse uma cor de DESIGN literal dentro do `<symbol>` (em vez de
    `currentColor`, que herda do texto ao lado, tokenizado por definição)
    continua reprovando. Prova que a exceção é estreita, não um buraco
    genérico em "qualquer coisa dentro de symbol"."""
    html = '<svg><symbol id="icone-mau"><rect fill="#ff0000" width="10"></rect></symbol></svg>'
    achados = _cores_e_medidas_em_atributos_de_template(html)
    assert any(a.startswith("fill=") for a in achados), (
        f"cor de design dentro de <symbol> deveria continuar acusada: {achados}"
    )
    # A geometria (width) desta MESMA tag, ao lado da cor sabotada, continua
    # isenta — controle de que as duas checagens são independentes.
    assert not any(a.startswith("width=") for a in achados), (
        f"geometria dentro de <symbol> não deveria ser acusada: {achados}"
    )


def test_controle_negativo_atributo_de_apresentacao_ignora_prosa_dentro_de_comentario():
    """Mesma família dos outros detectores deste arquivo: um comentário de
    template que MENCIONA `fill="#ff0000"` em prosa não pode ser lido como
    marcação real."""
    com_comentario = '{% comment %}Nunca escreva fill="#ff0000" aqui.{% endcomment %}<div>x</div>'
    assert _cores_e_medidas_em_atributos_de_template(com_comentario) == []


def test_controle_positivo_detector_de_valor_sem_classe():
    ruim = '<table><tr><td class="numero">{{ linha.saldo_ptbr }}</td></tr></table>'
    bom = '<table><tr><td class="valor-monetario">{{ linha.saldo_ptbr }}</td></tr></table>'
    fora_de_tabela = '<p class="texto-apoio">{{ data_minima_ptbr }}</p>'
    assert _valores_sem_classe(ruim), "o detector deixou passar valor sem a classe"
    assert not _valores_sem_classe(bom)
    assert not _valores_sem_classe(fora_de_tabela), (
        "data em prosa não é coluna de valor; a regra vale dentro de célula de tabela"
    )


def test_controle_a_mudanca_do_involucro_nao_afrouxa_o_caso_original():
    """Rodada 3 (BL-286): aceitar um invólucro em volta do número não pode
    afrouxar o caso ORIGINAL — célula sem a classe e SEM nenhum invólucro
    continua reprovando exatamente como antes."""
    ruim = "<table><tr><td>{{ linha.saldo_ptbr }}</td></tr></table>"
    assert _valores_sem_classe(ruim), (
        "célula sem classe e sem invólucro parou de reprovar depois da mudança"
    )


def test_controle_negativo_detector_de_valor_aceita_involucro_com_a_classe():
    """BL-286: a célula do veredito de fechamento mistura frase e número
    ("Não fecha, faltam X no crédito") — marcar a CÉLULA inteira com
    `valor-monetario` alinharia a frase toda à direita, em fonte tabulada,
    o que não faz sentido para texto corrido. Um `<span
    class="valor-monetario">` só em volta do número passa a ser aceito.
    """
    bom = (
        '<table><tr><td class="linha-total__veredito">'
        "Não fecha, faltam "
        '<span class="valor-monetario">{{ diferenca_fechamento_ptbr }}</span>'
        " no crédito</td></tr></table>"
    )
    assert not _valores_sem_classe(bom), "invólucro com a classe não foi aceito"


def test_controle_negativo_detector_de_involucro_que_ja_fechou_nao_cobre_o_valor():
    """Controle dentro do controle: um invólucro com a classe que já FECHOU
    antes do valor aparecer não pode cobri-lo — só protege o número
    enquanto está ABERTO no ponto exato onde o `_ptbr` aparece."""
    fechado_antes_do_valor = (
        "<table><tr><td>"
        '<span class="valor-monetario">rótulo</span> {{ diferenca_fechamento_ptbr }}'
        "</td></tr></table>"
    )
    assert _valores_sem_classe(fechado_antes_do_valor), (
        "um invólucro já fechado antes do valor não pode cobrir o valor"
    )


# ---------------------------------------------------------------------------
# M3/BL-294 (auditoria DL-026 rodada 2): elemento VAZIO (`<br>`, `<img>`,
# `<input>`, `<hr>` — nunca têm tag de fechamento) tratado como "invólucro
# que nunca fecha, então cobre tudo". Introduzido pela mudança da rodada 3
# que passou a aceitar invólucro em linha; os três controles daquela rodada
# cobrem o invólucro que fecha CEDO DEMAIS, nenhum cobre o que NÃO FECHA
# NUNCA.
# ---------------------------------------------------------------------------


def test_controle_negativo_involucro_vazio_nao_cobre_nada():
    """`<td><br class="valor-monetario">{{ x_ptbr }}</td>` tem de reprovar —
    `<br>` não tem `</br>`, e `find` devolvia `-1`, que a checagem antiga
    lia como "ainda aberto, cobre o valor". Medido pelo auditor: a coluna
    perdia `tabular-nums` com `61 passed`."""
    com_br = '<table><tr><td><br class="valor-monetario">{{ linha.saldo_ptbr }}</td></tr></table>'
    assert _valores_sem_classe(com_br), (
        "invólucro <br> (elemento vazio) cobriu o valor por engano — a coluna perderia tabular-nums"
    )


def test_controle_negativo_involucro_vazio_img_nao_cobre_nada():
    com_img = (
        '<table><tr><td><img class="valor-monetario" src="x" alt="">'
        "{{ linha.saldo_ptbr }}</td></tr></table>"
    )
    assert _valores_sem_classe(com_img), (
        "invólucro <img> (elemento vazio) cobriu o valor por engano"
    )


def test_controle_positivo_involucro_real_continua_protegendo_o_valor():
    """Controle de que a correção do M3 não afrouxou o caso que a rodada 3
    introduziu: um invólucro de VERDADE (`<span>`, que tem fechamento)
    continua protegendo o valor."""
    com_span = (
        "<table><tr><td>"
        '<span class="valor-monetario">{{ linha.saldo_ptbr }}</span>'
        "</td></tr></table>"
    )
    assert not _valores_sem_classe(com_span), "invólucro real (<span>) parou de proteger o valor"


def test_controle_involucro_nao_afrouxa_o_relato_por_arquivo(tmp_path):
    """BL-286: a mudança que aceita invólucro não pode enfraquecer o relato
    que NOMEIA o arquivo ofensor — o mesmo formato de mensagem que
    `test_todo_valor_em_celula_usa_a_classe_do_sistema` usa contra a árvore
    real de templates, aqui provado contra um arquivo sintético isolado em
    `tmp_path` (nunca a árvore real, para não depender de nada existir ou
    deixar de existir em `templates/`)."""
    pasta = tmp_path / "templates" / "modulo_sintetico"
    pasta.mkdir(parents=True)
    arquivo = pasta / "tela_ruim.html"
    arquivo.write_text("<table><tr><td>{{ linha.saldo_ptbr }}</td></tr></table>", encoding="utf-8")

    ofensores = [
        f"{arquivo.relative_to(tmp_path)}: {valor} em {celula}"
        for celula, valor in _valores_sem_classe(arquivo.read_text(encoding="utf-8"))
    ]
    assert ofensores, "a varredura deixou de reprovar o arquivo sintético"
    assert "tela_ruim.html" in ofensores[0], "a mensagem de erro parou de nomear o arquivo"


# ---------------------------------------------------------------------------
# Sabotagem 3 da rodada 3 (BL-286): `"valor-monetario" in tag` era SUBSTRING,
# não TOKEN — `class="valor-monetario-legenda"` continha a string certa e
# passava, sendo uma classe CSS diferente. Bateria nos DOIS caminhos (célula
# e invólucro), pedida pelo arquiteto-senior: a classe "parecida" tem de
# reprovar nos dois, a classe exata (sozinha, com vizinhas, ou com aspas
# simples) tem de continuar passando nos dois.
# ---------------------------------------------------------------------------


def _celula_com_classe(classe_do_atributo):
    return (
        '<table><tr><td class="' + classe_do_atributo + '">{{ linha.saldo_ptbr }}</td></tr></table>'
    )


@pytest.mark.parametrize(
    "classe_do_atributo, deve_reprovar",
    [
        # A sabotagem em si: classe PARECIDA, não a classe certa.
        ("valor-monetario-legenda", True),
        # A classe certa, sozinha — já valia antes, continua valendo.
        ("valor-monetario", False),
        # A classe certa entre outras — `class="celula valor-monetario
        # destaque"` é o formato real que o produto já usa (ex.: `<td
        # class="valor-monetario">` puro é raro; células combinam classes).
        ("celula valor-monetario destaque", False),
    ],
)
def test_controle_classe_da_celula_casa_como_token_nao_como_substring(
    classe_do_atributo, deve_reprovar
):
    """Achado do arquiteto-senior (rodada 3, sabotagem 3): a checagem tem
    de casar `valor-monetario` como NOME DE CLASSE inteiro dentro do
    atributo `class`, nunca como substring da tag inteira."""
    ofensores = _valores_sem_classe(_celula_com_classe(classe_do_atributo))
    if deve_reprovar:
        assert ofensores, f"classe '{classe_do_atributo}' deveria reprovar e passou"
    else:
        assert not ofensores, f"classe '{classe_do_atributo}' deveria passar e reprovou"


def test_controle_classe_da_celula_aceita_aspas_simples():
    """A sabotagem de aspas simples já pegou o detector de estilo embutido
    (BL-274 #5) — confirmando aqui que `_tem_classe` não repete o erro."""
    html = "<table><tr><td class='valor-monetario'>{{ linha.saldo_ptbr }}</td></tr></table>"
    assert not _valores_sem_classe(html), "classe com aspas simples não foi reconhecida"


def _involucro_com_classe(classe_do_atributo):
    return (
        '<table><tr><td class="linha-total__veredito">texto '
        '<span class="' + classe_do_atributo + '">{{ diferenca_fechamento_ptbr }}</span>'
        " fim</td></tr></table>"
    )


@pytest.mark.parametrize(
    "classe_do_atributo, deve_reprovar",
    [
        ("valor-monetario-legenda", True),
        ("valor-monetario", False),
        ("celula valor-monetario destaque", False),
    ],
)
def test_controle_classe_do_involucro_casa_como_token_nao_como_substring(
    classe_do_atributo, deve_reprovar
):
    """Mesma sabotagem, mesmo achado, no SEGUNDO caminho (o invólucro que a
    própria rodada 3 introduziu) — a checagem original copiou o defeito de
    origem (`"valor-monetario" not in abertura.group(0)`) para cá."""
    ofensores = _valores_sem_classe(_involucro_com_classe(classe_do_atributo))
    if deve_reprovar:
        assert ofensores, f"invólucro com classe '{classe_do_atributo}' deveria reprovar e passou"
    else:
        assert not ofensores, (
            f"invólucro com classe '{classe_do_atributo}' deveria passar e reprovou"
        )


def test_controle_classe_do_involucro_aceita_aspas_simples():
    html = (
        '<table><tr><td class="linha-total__veredito">texto '
        "<span class='valor-monetario'>{{ diferenca_fechamento_ptbr }}</span>"
        " fim</td></tr></table>"
    )
    assert not _valores_sem_classe(html), "invólucro com aspas simples não foi reconhecido"


# ---------------------------------------------------------------------------
# Mesma família, achada na mesma inspeção: o atributo `scope` do `<th>`
# também era casado por substring (`"scope=" not in tag`) — `data-scope=`/
# `aria-scope=` continham a substring certa e a guarda achava que o `<th>`
# tinha declarado `scope` de verdade.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "atributo, deve_reprovar",
    [
        ('<th data-scope="x">Conta</th>', True),
        ('<th aria-scope="x">Conta</th>', True),
        ("<th>Conta</th>", True),
        ('<th scope="col">Conta</th>', False),
        ("<th scope='col'>Conta</th>", False),
    ],
)
def test_controle_atributo_scope_casa_como_atributo_nao_como_substring(atributo, deve_reprovar):
    """`data-scope`/`aria-scope` são atributos DIFERENTES de `scope` — um
    `<th>` que só tem um deles não declarou o `scope` que o leitor de tela
    precisa, e a guarda não pode achar que declarou."""
    achados = _cabecalhos_sem_escopo(atributo)
    if deve_reprovar:
        assert achados, f"'{atributo}' deveria reprovar (sem scope real) e passou"
    else:
        assert not achados, f"'{atributo}' deveria passar (scope real presente) e reprovou"


# ---------------------------------------------------------------------------
# Mesma inspeção: três checagens que liam texto CRU (template ou CSS) sem
# tirar comentário primeiro — a MESMA classe de defeito que motivou
# `_sem_comentarios_de_template` (docstring dela), só que aplicada só a
# `PADRAO_CELULA`/`PADRAO_VALOR` e nunca generalizada para estes três
# lugares vizinhos.
# ---------------------------------------------------------------------------


def test_controle_extends_ignora_prosa_dentro_de_comentario():
    """Um `{% comment %}` que MENCIONA `{% extends %}` em prosa (documentando
    a própria tela) não pode contar como a tela realmente estendendo
    `base.html` — só a tag REAL, fora de comentário."""
    so_em_comentario = (
        '{% comment %}Esta tela deveria ter {% extends "base.html" %} no topo, '
        "mas alguém removeu.{% endcomment %}<html></html>"
    )
    assert "{% extends" not in _sem_comentarios_de_template(so_em_comentario), (
        "a prosa dentro do comentário sobreviveu à limpeza"
    )
    tag_real = '{% extends "base.html" %}<html></html>'
    assert "{% extends" in _sem_comentarios_de_template(tag_real)


def test_controle_caption_ignora_prosa_dentro_de_comentario():
    """Um comentário que cita `<table>`/`<caption>` em prosa não pode contar
    como tabela nem como legenda de verdade — só a marcação REAL."""
    texto = (
        "{% comment %}Toda <table> precisa de <caption>.{% endcomment %}"
        "<table><tr><td>1</td></tr></table>"
    )
    limpo = _sem_comentarios_de_template(texto)
    tabelas = len(re.findall(r"<table\b", limpo, re.IGNORECASE))
    legendas = len(re.findall(r"<caption\b", limpo, re.IGNORECASE))
    assert tabelas == 1, "a tabela real não foi contada"
    assert legendas == 0, "a prosa do comentário foi contada como <caption> real"


def test_controle_tabular_nums_ignora_comentario_css():
    """Um comentário CSS que CITA `tabular-nums` sem a declaração real ao
    lado não pode fazer a guarda pensar que a classe tabula algarismos."""
    corpo_so_com_comentario = "/* deveria ter tabular-nums aqui, mas sumiu */"
    limpo = _sem_comentarios_css(corpo_so_com_comentario)
    assert "tabular-nums" not in limpo, "o comentário sobreviveu à limpeza"
    corpo_real = "font-variant-numeric: tabular-nums;"
    assert "tabular-nums" in _sem_comentarios_css(corpo_real)


def test_controle_negativo_detector_de_valor_ignora_prosa_dentro_de_comentario():
    """Bug descoberto ao rodar o Achado 2 contra a árvore real:
    `lancamento_form.html` tem um `{% comment %}` que EXPLICA esta guarda em
    prosa e cita, entre crases, o texto `` `<td>` `` — sem limpar o
    comentário primeiro, essa prosa era lida como abertura de célula real, e
    tudo até o próximo `</td>` (inclusive `_ptbr` de outros comentários e de
    `{% if %}`) virava falso positivo. O comentário reproduz a estrutura
    exata: `<td>` em prosa dentro do comentário, seguido de uma célula REAL
    sem classe mais adiante — só a real pode reprovar."""
    com_comentario_inofensivo = (
        "<table><tr>"
        "{% comment %}"
        "A comparação fica fora de qualquer `<td>` de propósito, e não exibe "
        "total_debito_ptbr diretamente."
        "{% endcomment %}"
        '<td class="valor-monetario">{{ linha.saldo_ptbr }}</td>'
        "</tr></table>"
    )
    assert not _valores_sem_classe(com_comentario_inofensivo), (
        "texto de comentário foi lido como célula real"
    )

    com_comentario_e_celula_real_sem_classe = (
        "<table><tr>"
        "{% comment %}"
        "A comparação fica fora de qualquer `<td>` de propósito."
        "{% endcomment %}"
        "<td>{{ linha.saldo_ptbr }}</td>"
        "</tr></table>"
    )
    assert _valores_sem_classe(com_comentario_e_celula_real_sem_classe), (
        "a célula REAL sem classe, depois do comentário, tem de continuar reprovando"
    )


def test_controle_negativo_detector_de_escopo_ignora_prosa_dentro_de_comentario():
    com_comentario = (
        '{% comment %}Todo `<th>` precisa de scope.{% endcomment %}<th scope="col">Conta</th>'
    )
    assert not _cabecalhos_sem_escopo(com_comentario)


def test_controle_positivo_detector_de_valor_que_chega_por_include():
    """BL-274 #1/#5 — a cegueira real, aberta pelo próprio `_saldo.html`: o
    valor chega como `{% include ... with valor=item.saldo_ptbr %}`, sem
    `{{ ..._ptbr }}` literal na célula. Remover a classe da célula QUE CHAMA
    o parcial tem de reprovar."""
    ruim = (
        "<table><tr><td>"
        '{% include "contabilidade/_saldo.html" with valor=item.saldo_ptbr '
        "natureza=item.saldo_natureza conta=conta %}"
        "</td></tr></table>"
    )
    bom = ruim.replace("<td>", '<td class="valor-monetario">')
    assert _valores_sem_classe(ruim), (
        "o detector não viu o valor que chega por {% include %} com kwarg _ptbr"
    )
    assert not _valores_sem_classe(bom)


def test_mensagem_de_valor_sem_classe_orienta_o_caso_que_nao_e_dinheiro():
    """Achado 2 da revisão do arquiteto-senior: `_ptbr` não é exclusivo de
    dinheiro (`lancamento_form.html:80` já usa em data, hoje fora de
    célula). Se um módulo novo puser data com `_ptbr` DENTRO de uma célula,
    a mensagem de erro não pode instruir a colocar 'valor-monetario' numa
    data — precisa oferecer a saída certa."""
    assert "data" in MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE
    assert "valor-monetario" in MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE
    assert "exceção nomeada" in MENSAGEM_ORIENTACAO_VALOR_SEM_CLASSE


def test_controle_positivo_detector_de_escopo():
    assert _cabecalhos_sem_escopo("<th>Conta</th>")
    assert not _cabecalhos_sem_escopo('<th scope="col">Conta</th>')


# Documento sintético que reproduz a sabotagem exata do auditor: "Fiscal"
# sobrevive em prosa dentro E fora da seção 3, mas a linha da tabela sumiu.
_DOC_SINTETICO_SEM_LINHA_FISCAL = """\
# Direção de arte

## 2. Arquétipos

A tela Fiscal precisa responder à pergunta certa. O módulo Fiscal ainda não
existe, mas quando o Fiscal nascer, a tabela abaixo é onde ele documenta a
pergunta — "Fiscal" aparece aqui, de propósito, para provar que substring no
documento inteiro não basta.

## 3. O "momento da verdade" de cada módulo

| Módulo | A pergunta que a tela responde antes de gravar |
| --- | --- |
| **Contábil** | Débito é igual a crédito? |

Ainda na seção 3, mas fora da tabela: "Fiscal" aparece de novo aqui.

## 4. Outra seção

Mais uma menção a Fiscal aqui, fora da seção 3 inteira.
"""

_DOC_SINTETICO_COM_LINHA_FISCAL = _DOC_SINTETICO_SEM_LINHA_FISCAL.replace(
    "| **Contábil** | Débito é igual a crédito? |",
    "| **Contábil** | Débito é igual a crédito? |\n| **Fiscal** | O documento é elegível? |",
)


def test_controle_positivo_detector_de_linha_na_tabela_do_modulo():
    """BL-274 #6 — a sabotagem exata: "Fiscal" sobrevive em prosa, a linha da
    tabela some, e a guarda antiga (substring no documento inteiro) passava."""
    secao = _secao_do_momento_da_verdade(_DOC_SINTETICO_SEM_LINHA_FISCAL)
    assert "Fiscal" in secao, "a palavra precisa sobreviver na seção para o teste valer algo"
    assert not _tem_linha_na_tabela(secao, "Fiscal"), (
        "o detector aceitou 'Fiscal' em prosa como se fosse linha de tabela"
    )


def test_controle_negativo_detector_de_linha_na_tabela_do_modulo():
    secao = _secao_do_momento_da_verdade(_DOC_SINTETICO_COM_LINHA_FISCAL)
    assert _tem_linha_na_tabela(secao, "Fiscal")


def test_controle_a_secao_do_3_nao_vaza_para_fora():
    """A menção fora da seção 3 (no "## 4.") não pode contar como parte dela."""
    secao = _secao_do_momento_da_verdade(_DOC_SINTETICO_SEM_LINHA_FISCAL)
    assert "Outra seção" not in secao
    assert "## 4" not in secao
