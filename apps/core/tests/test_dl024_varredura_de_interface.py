"""Varredura de interface — o mecanismo que transforma a direção de arte em
regra, e não em pedido.

**Por que este arquivo existe.** A [direção de arte](docs/projeto/direcao-de-arte.md)
foi escolhida por medição, num gauntlet de três variantes (DE-042/RC-89). Mas o
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

RAIZ = Path(__file__).resolve().parents[3]
TEMPLATES = RAIZ / "templates"
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
# #2/#3) sairia catalogando o Bootstrap do DRF e o admin do Django.
PASTAS_SEM_CSS_DO_PROJETO = {
    ".venv": "dependências Python de terceiros (Django, DRF); nunca é o CSS do produto",
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
PADRAO_COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)")

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

# Qualquer declaração `propriedade: valor;` do CSS, para procurar cor nomeada
# dentro do VALOR — precisa de contexto de declaração para não confundir a
# palavra "gray" com o nome de uma classe ou de um comentário.
_PADRAO_DECLARACAO = re.compile(r":\s*([^;{}]+)[;}]")

# Estilo embutido: `style="..."` (aspas duplas), `style='...'` (BL-274 #5,
# aspas simples escapavam) e `<style>...</style>` embutido no template.
PADRAO_ESTILO_EMBUTIDO = re.compile(
    r"""style\s*=\s*"[^"]*" | style\s*=\s*'[^']*' | <style\b[^>]*>.*?</style>""",
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# Recorte da seção "## 3." da direção de arte, até o próximo "## " — BL-274
# #6: a guarda antiga fazia busca de substring no DOCUMENTO INTEIRO, e
# "Fiscal" sobrevivia em outras quatro frases fora da tabela.
PADRAO_SECAO_MOMENTO_DA_VERDADE = re.compile(r"^## 3\..*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)

# Nome do MÓDULO como ele aparece na tabela do §3, por pasta de `templates/`.
# "contabilidade" é a única pasta real hoje (as demais ainda não existem —
# Fora do escopo da DL-024); as outras chaves são a melhor aproximação do
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

# Propriedades de medida cobertas pelo critério 13 ("cor, tamanho ou
# espaçamento fora dos tokens") — BL-274, o detector que nunca existiu.
# `(?:-[a-z]+)*` cobre as variantes de lado/eixo com SUFIXO citadas na tarefa
# (`padding-left`, `margin-top`, `border-bottom-width`, e também as formas de
# propriedade lógica de dois segmentos como `margin-inline-start`). `gap` é o
# único caso real de PREFIXO no CSS (`row-gap`, `column-gap`).
_PADRAO_PROPRIEDADE_DE_MEDIDA = re.compile(
    r"(?<![\w-])("
    r"(?:row-|column-)?gap"
    r"|padding(?:-[a-z]+)*"
    r"|margin(?:-[a-z]+)*"
    r"|font-size"
    r"|border(?:-[a-z]+)*-width"
    r")\s*:\s*([^;{}]+)[;}]",
    re.IGNORECASE,
)
# `\d*\.?\d+` cobre inteiro e decimal (`4px`, `0.4em`); a unidade é literal,
# nunca `var(...)`. Valores sem unidade (`0`), percentuais (`100%`), `auto`,
# `1fr` e o que estiver dentro do próprio bloco `:root` (onde o token NASCE)
# não caem aqui por construção — nenhuma exceção adicional foi necessária.
_PADRAO_MEDIDA_LITERAL = re.compile(r"(?<![\w.-])\d*\.?\d+(?:px|rem|em)\b", re.IGNORECASE)


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def _e_parcial(caminho):
    """Trecho reaproveitado (`_nome.html`) não estende moldura: ele é incluído."""
    return caminho.name.startswith("_")


def _sem_comentarios_css(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _texto_sem_root(texto):
    """Remove comentários e o bloco `:root` — é onde os tokens NASCEM (DE-042);
    cor ou medida literal ali é a própria definição do token, não violação.
    Compartilhado pelos detectores de cor e de medida (mesma regra, mesma
    exceção)."""
    limpo = _sem_comentarios_css(texto)
    for bloco in re.finditer(r":root\s*\{.*?\}", limpo, flags=re.S):
        limpo = limpo.replace(bloco.group(0), "")
    return limpo


def _cores_fora_dos_tokens(texto):
    """Cores declaradas fora do bloco `:root`, em hex/rgb/hsl **ou nomeadas**
    (BL-274 #2: `red`, `white`... eram invisíveis).

    O `:root` é onde os tokens moram (DE-042). Cor escrita direto numa regra de
    tela é o começo da divergência: a próxima tela copia, a terceira erra o
    tom, e seis meses depois existem quatro azuis.
    """
    limpo = _texto_sem_root(texto)
    achados = PADRAO_COR.findall(limpo)
    for declaracao in _PADRAO_DECLARACAO.finditer(limpo):
        # `var(...)` pode conter qualquer coisa no NOME da variável
        # (`var(--cor-red-alerta)`) sem que isso seja uma cor nomeada de
        # verdade; remove antes de tokenizar. String e `url()` também não são
        # cor nomeada literal.
        valor = re.sub(r"var\([^)]*\)", "", declaracao.group(1))
        if "url(" in valor or '"' in valor or "'" in valor:
            continue
        for token in re.findall(r"[a-zA-Z]+", valor):
            nome = token.lower()
            if nome in CORES_NOMEADAS_CSS and nome not in NOMES_QUE_NAO_SAO_TINTA:
                achados.append(nome)
    return achados


def _medidas_literais_fora_dos_tokens(texto):
    """`px`/`rem`/`em` literais em propriedade de espaço/tipo/borda, fora do
    `:root`. Devolve `"propriedade: valor"` para cada ofensor.

    O detector que o critério 13 prometia ("cor, TAMANHO ou ESPAÇAMENTO fora
    dos tokens") e nunca existia — BL-274, achado A1 da rodada 1.
    """
    limpo = _texto_sem_root(texto)
    achados = []
    for declaracao in _PADRAO_PROPRIEDADE_DE_MEDIDA.finditer(limpo):
        propriedade, valor = declaracao.group(1), declaracao.group(2)
        valor_sem_var = re.sub(r"var\([^)]*\)", "", valor)
        for literal in _PADRAO_MEDIDA_LITERAL.finditer(valor_sem_var):
            achados.append(f"{propriedade}: {literal.group(0)}")
    return achados


def _folhas_de_estilo_do_projeto(raiz):
    """Todo `.css` do projeto, em qualquer subpasta — não só `static/css/`.

    BL-274 #2/#3: o `glob("*.css")` não era recursivo (`static/css/modulos/`
    escapava) e só olhava `static/css/` (`static/tema.css` escapava). Varre o
    repositório inteiro e exclui só as pastas de dependência/build, cada uma
    com o motivo em `PASTAS_SEM_CSS_DO_PROJETO` — sem a exclusão, o Bootstrap
    do DRF e o admin do Django (em `staticfiles/` e `.venv/`) entrariam na
    varredura do produto.
    """
    achadas = []
    for caminho in sorted(raiz.rglob("*.css")):
        partes = caminho.relative_to(raiz).parts
        if partes[0] in PASTAS_SEM_CSS_DO_PROJETO:
            continue
        achadas.append(caminho)
    return achadas


def _estilos_embutidos(texto):
    """`style="..."`, `style='...'` (BL-274 #5) e `<style>` embutido no
    template — todos escapam do sistema de tokens e da auditoria de
    contraste: ninguém encontra aquele valor depois."""
    return [m.group(0)[:60] for m in PADRAO_ESTILO_EMBUTIDO.finditer(texto)]


def _valores_sem_classe(texto):
    """Valores `_ptbr` dentro de célula de tabela que não usam a classe do
    sistema. Devolve a lista dos trechos ofensores."""
    ofensores = []
    for valor in PADRAO_VALOR.finditer(texto):
        anteriores = list(PADRAO_CELULA.finditer(texto, 0, valor.start()))
        if not anteriores:
            continue  # o valor não está dentro de célula: fora do alcance da regra
        celula = anteriores[-1]
        # A célula só vale se o valor estiver antes do próximo fechamento dela.
        fechamento = texto.find(f"</{celula.group(1)}>", celula.end())
        if fechamento != -1 and fechamento < valor.start():
            continue
        if "valor-monetario" not in celula.group(0):
            ofensores.append((celula.group(0)[:70], valor.group(0)[:40]))
    return ofensores


def _cabecalhos_sem_escopo(texto):
    achados = re.finditer(r"<th\b[^>]*>", texto)
    return [m.group(0)[:70] for m in achados if "scope=" not in m.group(0)]


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
# implementação real da DL-024 (DE-042) nesta etapa — `strict=True` fez
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
    """
    fora = [
        str(t.relative_to(RAIZ))
        for t in _templates()
        if t.name != "base.html"
        and not _e_parcial(t)
        and "{% extends" not in t.read_text(encoding="utf-8")
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
    """
    faltando = []
    for t in _templates():
        texto = t.read_text(encoding="utf-8")
        tabelas = len(re.findall(r"<table\b", texto, re.IGNORECASE))
        legendas = len(re.findall(r"<caption\b", texto, re.IGNORECASE))
        if tabelas > legendas:
            faltando.append(f"{t.relative_to(RAIZ)} ({tabelas} tabelas, {legendas} legendas)")
    assert not faltando, "Tabelas sem <caption>: " + "; ".join(faltando)


def test_todo_cabecalho_de_tabela_declara_escopo():
    """`<th>` sem `scope` faz o leitor de tela ler "1.234,56" sem dizer de qual
    coluna e de qual conta. Em tabela contábil, é o mesmo que não ler nada."""
    faltando = []
    for t in _templates():
        for cabecalho in _cabecalhos_sem_escopo(t.read_text(encoding="utf-8")):
            faltando.append(f"{t.relative_to(RAIZ)}: {cabecalho}")
    assert not faltando, "Cabeçalhos de tabela sem scope: " + "; ".join(faltando)


def test_todo_valor_em_celula_usa_a_classe_do_sistema():
    """Coluna de valor sem a classe do sistema perde a tabulação de algarismos.

    O efeito é o que o gauntlet mediu e nomeou: as colunas **dançam**, porque
    `1` e `8` têm larguras diferentes em fonte proporcional, e o olho perde a
    referência vertical justamente onde a conferência acontece.
    """
    ofensores = []
    for t in _templates():
        for celula, valor in _valores_sem_classe(t.read_text(encoding="utf-8")):
            ofensores.append(f"{t.relative_to(RAIZ)}: {valor} em {celula}")
    assert not ofensores, (
        "Valores em célula de tabela sem a classe 'valor-monetario': " + "; ".join(ofensores)
    )


def test_a_classe_de_valor_tabula_algarismos():
    """A classe existe — mas ela precisa **fazer** o que promete.

    Guarda contra o defeito exato da BL-271: o nome certo no lugar certo, e a
    propriedade que importa removida sem ninguém perceber.
    """
    css = (ESTILOS / "base.css").read_text(encoding="utf-8")
    bloco = re.search(r"\.valor-monetario\s*\{(.*?)\}", css, flags=re.S)
    assert bloco, "A classe .valor-monetario sumiu de static/css/base.css"
    corpo = bloco.group(1)
    assert "tabular-nums" in corpo or "mono" in corpo.lower(), (
        "A classe .valor-monetario existe mas não tabula algarismos. "
        "Sem isso as colunas de valor voltam a dançar: " + corpo.strip()[:120]
    )


def test_nenhuma_cor_declarada_fora_dos_tokens():
    """Cor solta é o começo de quatro azuis diferentes (DE-042). Cobre
    hex/rgb/hsl e cor NOMEADA (BL-274 #2), em todo `.css` do projeto, não só
    `static/css/*.css` de primeiro nível (BL-274 #3)."""
    soltas = []
    for folha in _folhas_de_estilo_do_projeto(RAIZ):
        for cor in _cores_fora_dos_tokens(folha.read_text(encoding="utf-8")):
            soltas.append(f"{folha.relative_to(RAIZ)}: {cor}")
    assert not soltas, (
        "Cores declaradas fora do :root (tokens da DE-042): "
        + "; ".join(soltas)
        + ". Se a cor é nova, ela nasce como token com o contraste medido."
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
        "border-width, critério 13 da DL-024): " + "; ".join(soltas)
    )


def test_nenhum_estilo_embutido_no_template():
    """`style="..."`, `style='...'` e `<style>` embutido escapam do sistema de
    tokens e da auditoria de contraste: ninguém encontra aquele valor depois."""
    embutidos = []
    for t in _templates():
        for achado in _estilos_embutidos(t.read_text(encoding="utf-8")):
            embutidos.append(f"{t.relative_to(RAIZ)}: {achado}")
    assert not embutidos, "Estilo embutido em template: " + "; ".join(embutidos)


def test_modulo_novo_declara_o_seu_momento_da_verdade():
    """Módulo sem a sua pergunta escrita — numa LINHA DE TABELA do §3, não em
    prosa solta em qualquer lugar do documento (BL-274 #6) — não devia ter
    tela desenhada.

    O "momento da verdade" é a pergunta que a tela responde **antes de gravar**
    — no Contábil, "débito é igual a crédito?". Quem não sabe responder pelo
    Fiscal, pela Folha ou pelo Lalur tem um problema de entendimento do
    domínio, e a hora de descobrir é antes da tela, não depois.
    """
    secao = _secao_do_momento_da_verdade(DIRECAO_DE_ARTE.read_text(encoding="utf-8"))
    assert secao, "A seção '## 3.' sumiu de docs/projeto/direcao-de-arte.md"
    sem_linha = []
    for pasta in sorted(p for p in TEMPLATES.iterdir() if p.is_dir()):
        nome = pasta.name
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
    limpo = ".bloco { padding: var(--esp-3); margin: 0; width: 100%; height: 12px; }"
    achados = _medidas_literais_fora_dos_tokens(limpo)
    assert achados == [], (
        "token via var(), valor sem unidade, percentual e propriedade fora da "
        f"lista (height) não podiam ter sido acusados: {achados}"
    )
    # Dentro do :root é a própria definição do token — não é violação.
    token = ":root { --esp-3: 12px; --tipo-lg: 1.2rem; }"
    assert _medidas_literais_fora_dos_tokens(token) == []


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


def test_controle_negativo_detector_de_css_ignora_pastas_de_dependencia_e_build(tmp_path):
    (tmp_path / ".venv" / "pacote").mkdir(parents=True)
    (tmp_path / ".venv" / "pacote" / "vendor.css").write_text(".x{color:red}", encoding="utf-8")
    (tmp_path / "staticfiles").mkdir()
    (tmp_path / "staticfiles" / "coletado.css").write_text(".x{color:red}", encoding="utf-8")
    achadas = _folhas_de_estilo_do_projeto(tmp_path)
    assert achadas == [], "CSS de dependência/build entrou na varredura do produto"


def test_controle_positivo_detector_de_estilo_embutido():
    """BL-274 #5: aspas simples e `<style>` embutido escapavam."""
    assert _estilos_embutidos("<div style='color: red'>x</div>"), "aspas simples não detectadas"
    assert _estilos_embutidos('<div style="color: red">x</div>'), "aspas duplas não detectadas"
    assert _estilos_embutidos("<style>.x{color:red}</style>"), "<style> embutido não detectado"


def test_controle_negativo_detector_de_estilo_embutido_ignora_atributos_comuns():
    limpo = '<div class="valor-monetario" data-style-alvo="x">y</div>'
    assert _estilos_embutidos(limpo) == []


def test_controle_positivo_detector_de_valor_sem_classe():
    ruim = '<table><tr><td class="numero">{{ linha.saldo_ptbr }}</td></tr></table>'
    bom = '<table><tr><td class="valor-monetario">{{ linha.saldo_ptbr }}</td></tr></table>'
    fora_de_tabela = '<p class="texto-apoio">{{ data_minima_ptbr }}</p>'
    assert _valores_sem_classe(ruim), "o detector deixou passar valor sem a classe"
    assert not _valores_sem_classe(bom)
    assert not _valores_sem_classe(fora_de_tabela), (
        "data em prosa não é coluna de valor; a regra vale dentro de célula de tabela"
    )


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
