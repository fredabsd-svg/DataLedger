"""Testes de `apps.core.marcacao` (BL-310, M1 da auditoria DL-026 rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md).

Este módulo foi criado na rodada 4 (BL-295/BL-296/BL-297) para unificar três
implementações independentes de "casar atributo HTML por TOKEN, nunca por
substring nem por igualdade do valor inteiro" — e, apesar disso, nunca teve
arquivo de teste próprio. A auditoria registrou isso como agravante do
achado M1: "um defeito nele erra nos dois consumidores de uma vez". Este
arquivo fecha a lacuna: cada comportamento documentado nas funções públicas
(`valor_de_atributo`, `tokens_de_atributo`, `tem_classe`) tem um teste
próprio aqui, independente de quem consome o módulo.

Funções puras sobre STRING — sem Django, sem banco de dados.
"""

import pytest

from apps.core.marcacao import tem_classe, tokens_de_atributo, valor_de_atributo

# ---------------------------------------------------------------------------
# `valor_de_atributo` — as três formas de aspas que o HTML5 aceita
# ---------------------------------------------------------------------------


def test_valor_de_atributo_com_aspas_duplas():
    assert valor_de_atributo('<kbd class="tecla">', "class") == "tecla"


def test_valor_de_atributo_com_aspas_simples():
    assert valor_de_atributo("<kbd class='tecla'>", "class") == "tecla"


def test_valor_de_atributo_sem_aspas():
    """BL-310 (M1): a forma que faltava. HTML5 aceita atributo sem aspas
    quando o valor não tem espaço, aspas, `=`, `<`, `>` nem crase — e o
    Chromium aplica. Antes desta correção, `valor_de_atributo` devolvia
    `None` aqui (a busca só reconhecia aspas), e um `<kbd class=tecla>`
    real do produto perdia a classe para toda guarda que dependesse deste
    módulo."""
    assert valor_de_atributo("<kbd class=tecla>", "class") == "tecla"


def test_valor_de_atributo_sem_aspas_para_no_primeiro_delimitador():
    """O valor sem aspas termina no primeiro espaço, `>` ou `/` — nunca
    "vaza" para o resto da tag. `<kbd class=tecla aria-hidden="true">`
    não pode virar `class` = `"tecla aria-hidden=true"` nem coisa
    parecida."""
    assert valor_de_atributo('<kbd class=tecla aria-hidden="true">', "class") == "tecla"


def test_valor_de_atributo_ignora_maiusculas_no_nome_do_atributo():
    """HTML não distingue maiúsculas de minúsculas no NOME do atributo —
    `CLASS="tecla"` é o mesmo atributo que `class="tecla"`."""
    assert valor_de_atributo('<kbd CLASS="tecla">', "class") == "tecla"
    assert valor_de_atributo('<kbd Class="tecla">', "class") == "tecla"


def test_valor_de_atributo_aceita_espaco_ao_redor_do_igual():
    assert valor_de_atributo('<kbd class = "tecla">', "class") == "tecla"


def test_valor_de_atributo_ausente_e_none():
    assert valor_de_atributo("<kbd>", "class") is None
    assert valor_de_atributo('<kbd aria-hidden="true">', "class") is None


def test_valor_de_atributo_vazio_e_string_vazia_nao_none():
    """`class=""` existe (o atributo está lá), só que vazio — diferente de
    o atributo não existir. A distinção importa para `tokens_de_atributo`
    (lista vazia) e para qualquer chamador que precise saber se o atributo
    foi declarado."""
    assert valor_de_atributo('<kbd class="">', "class") == ""
    assert valor_de_atributo("<kbd class=''>", "class") == ""


def test_valor_de_atributo_nao_casa_atributo_com_sufixo_igual():
    """`\\s` obrigatório antes do nome do atributo: `data-class="x"` não é
    o atributo `class` — é `data-class`, que contém a SUBSTRING "class="
    mas é outro atributo inteiramente. Acerto que a rodada 3 (BL-286) já
    exigia de `scope=`/`style=`, preservado aqui."""
    assert valor_de_atributo('<td data-class="x">', "class") is None


def test_valor_de_atributo_nao_confunde_prefixo_de_nome_maior():
    """`classroom="x"` também não é `class` — o `\\s` na frente evita casar
    NO MEIO do nome de um atributo mais longo que começa com as mesmas
    letras."""
    assert valor_de_atributo('<div classroom="x">', "class") is None


def test_valor_de_atributo_atributo_booleano_sem_igual_nao_e_confundido_com_o_seguinte():
    """Caso NÃO coberto pelos testes anteriores: um atributo BOOLEANO (sem
    `=`, ex.: `disabled`) não pode "roubar" o valor do atributo seguinte —
    `_atributos_da_tag` grava `None` para ele e continua a busca a partir
    dali, nunca associando o valor de `class` ao atributo anterior."""
    assert valor_de_atributo('<input disabled class="valor-monetario">', "class") == (
        "valor-monetario"
    )


def test_valor_de_atributo_aceita_trecho_sem_o_nome_da_tag():
    """Contrato entre módulos: `apps.contabilidade.tests.
    test_dl017_rodada2_frontend._elemento_por_id` passa a `tem_classe` só o
    TRECHO de atributos capturado por regex (sem o `<nome-da-tag` na
    frente) — ver o docstring de `_atributos_da_tag`. Como o casamento
    exige `\\s+` antes do nome, o trecho funciona igual à tag completa,
    desde que comece com o espaço que sempre precede o primeiro
    atributo."""
    trecho_de_atributos = ' id="x" class="valor-monetario"'
    assert valor_de_atributo(trecho_de_atributos, "class") == "valor-monetario"
    assert tem_classe(trecho_de_atributos, "valor-monetario") is True


# ---------------------------------------------------------------------------
# `tokens_de_atributo` — divisão por espaço, para `class` e para qualquer
# outro atributo com valor em lista (ex.: `accesskey`)
# ---------------------------------------------------------------------------


def test_tokens_de_atributo_divide_por_espaco():
    assert tokens_de_atributo('<td class="a valor-monetario b">', "class") == [
        "a",
        "valor-monetario",
        "b",
    ]


def test_tokens_de_atributo_colapsa_espacos_repetidos():
    assert tokens_de_atributo('<td class="a   b">', "class") == ["a", "b"]


def test_tokens_de_atributo_atributo_ausente_e_lista_vazia():
    assert tokens_de_atributo("<td>", "class") == []


def test_tokens_de_atributo_atributo_vazio_e_lista_vazia():
    assert tokens_de_atributo('<td class="">', "class") == []


def test_tokens_de_atributo_serve_a_accesskey_tambem():
    """Não é exclusivo de `class` — qualquer atributo cujo valor seja uma
    lista separada por espaço, como `accesskey` (HTML Living Standard:
    mais de uma tecla alternativa é válido)."""
    assert tokens_de_atributo('<a accesskey="c d">', "accesskey") == ["c", "d"]
    assert tokens_de_atributo('<a accesskey="c">', "accesskey") == ["c"]


# ---------------------------------------------------------------------------
# `tem_classe` — casamento por TOKEN, nunca substring nem igualdade do
# valor inteiro. Os dois achados que motivaram a função (ver o docstring do
# módulo), mais o achado desta rodada (atributo sem aspas).
# ---------------------------------------------------------------------------


def test_tem_classe_caso_simples():
    assert tem_classe('<kbd class="tecla">', "tecla") is True
    assert tem_classe('<kbd class="outra">', "tecla") is False


def test_tem_classe_nao_casa_por_substring():
    """M6/BL-297: `class="texto-apoio-legenda"` é uma classe CSS DIFERENTE
    de `texto-apoio` — o seletor `.texto-apoio` do CSS não a alcança."""
    assert tem_classe('<td class="texto-apoio-legenda">', "texto-apoio") is False
    assert tem_classe('<td class="valor-monetario-legenda">', "valor-monetario") is False


def test_tem_classe_nao_exige_igualdade_do_valor_inteiro():
    """M4/BL-295: `class="tecla destaque"` continua tendo a classe `tecla`
    — perder isso por comparar o ATRIBUTO INTEIRO por igualdade fazia a
    guarda parar de reconhecer um elemento assim que ele ganhava uma
    segunda classe."""
    assert tem_classe('<kbd class="tecla destaque">', "tecla") is True
    assert tem_classe('<kbd class="destaque tecla">', "tecla") is True


def test_tem_classe_aceita_atributo_sem_aspas():
    """BL-310 (M1, achado desta rodada): `<kbd class=tecla>` é HTML5
    válido e o Chromium aplica o estilo — a auditoria mediu a árvore de
    acessibilidade do navegador anunciando o atalho colado ao nome do
    link (`'Plano de contas Alt+C'` em vez de `'Plano de contas'` com
    `keyshortcuts` separado) justamente porque `tem_classe` devolvia
    `False` para esta forma."""
    assert tem_classe("<kbd class=tecla>", "tecla") is True
    assert tem_classe('<kbd class=tecla aria-hidden="true">', "tecla") is True


def test_tem_classe_sem_atributo_class_e_false():
    assert tem_classe("<kbd>", "tecla") is False


# ---------------------------------------------------------------------------
# BL-322 (M4 da auditoria DL-026 rodada 4): a limitação antes REGISTRADA
# como "sempre permissiva" (BL-317, B3 da rodada 3) foi CORRIGIDA — o
# casamento agora ANCORA cada atributo pelo nome, a partir do início da
# tag, e CONSOME o valor inteiro de cada um antes de procurar o próximo
# nome (ver `_atributos_da_tag`, `apps/core/marcacao.py`). O auditor mediu
# que a limitação, na verdade, também errava na direção RESTRITIVA — o
# texto do BL-317 descrevia só a metade permissiva. Os testes abaixo fixam
# as DUAS direções, como o achado exige.
# ---------------------------------------------------------------------------


def test_bl322_nao_confunde_classe_dentro_do_valor_de_outro_atributo_com_classe_real():
    """`<td title="ver class='valor-monetario' aqui">` — a classe aparece
    só dentro do VALOR de `title`, não é um atributo `class` de verdade, e
    a célula NÃO tem a classe. Antes do BL-322, `tem_classe` devolvia
    `True` aqui (direção PERMISSIVA do defeito, registrada no BL-317);
    agora que o casamento ancora por atributo (não por substring em
    qualquer posição), o texto dentro do valor de `title` nunca é
    reexaminado como se fosse o atributo `class`."""
    tag = "<td title=\"ver class='valor-monetario' aqui\">"
    assert tem_classe(tag, "valor-monetario") is False, (
        "o texto 'class=...' dentro do VALOR de outro atributo não pode ser "
        "confundido com o atributo class real"
    )


@pytest.mark.parametrize(
    "tag",
    [
        # As três formas exatas medidas pelo achado M4: o texto-isca
        # "class=..." aparece ANTES do atributo class REAL — a ordem mais
        # natural de marcação escrita à mão (title/alt/aria-label antes de
        # class). Direção RESTRITIVA do defeito: `tem_classe` acusava
        # marcação CORRETA (devolvia False para uma célula que TEM a
        # classe).
        '<td title="use class=nenhum" class="valor-monetario">',
        "<td title='ver class=\"x\" aqui' class='valor-monetario'>",
        '<td data-x="a class=b" class="valor-monetario">',
        # Controle: a ordem original do relatório (isca DEPOIS do atributo
        # real) já funcionava antes do BL-322 e continua funcionando.
        '<td class="valor-monetario" title="class=nenhum">',
    ],
)
def test_bl322_nao_acusa_marcacao_correta_quando_o_texto_isca_vem_antes_do_atributo_real(tag):
    """Achado M4 (auditoria DL-026 rodada 4): a causa do defeito era
    `re.search` devolver a PRIMEIRA ocorrência da substring `class=` na tag
    — quando o texto-isca vem ANTES do atributo `class` real, a busca
    antiga "encontrava" o `class=` de dentro do outro atributo e nunca
    chegava ao real, devolvendo `False` para uma célula que TEM a classe.
    As quatro tags acima têm, de fato, `class="valor-monetario"` — as
    quatro têm que devolver `True`."""
    assert tem_classe(tag, "valor-monetario") is True, (
        f"a tag TEM a classe 'valor-monetario' de verdade — não pode ser acusada: {tag}"
    )
