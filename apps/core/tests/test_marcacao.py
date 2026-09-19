"""Testes de `apps.core.marcacao` (BL-310, M1 da auditoria DL-024 rodada 3,
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
# Limitação aceita e REGISTRADA (BL-317, B3 da auditoria DL-024 rodada 3):
# o casamento por regex sobre a STRING inteira da tag não distingue um
# atributo `class` real de um atributo `class` que aparece, por acidente,
# dentro do VALOR de outro atributo. Este teste fixa o comportamento ATUAL
# — não é uma expectativa desejável, é a documentação de uma cegueira
# conhecida, para que uma correção futura precise decidir conscientemente
# mudar este teste, em vez de descobrir a limitação de novo por auditoria.
# ---------------------------------------------------------------------------


def test_limitacao_conhecida_classe_dentro_do_valor_de_outro_atributo():
    """`<td title="ver class='valor-monetario' aqui">` — a classe aparece
    dentro do VALOR de `title`, não é um atributo `class` de verdade, mas
    `tem_classe` não distingue os dois casos (ela não rastreia estado de
    aspas desde o início da tag). Direção PERMISSIVA (aceita de mais, nunca
    recusa de menos): o risco é deixar passar uma célula que na verdade não
    tem a classe — nunca acusar uma célula que a tem. Sem caso real na base
    de templates deste projeto hoje (nenhum `title`/`alt` contém a palavra
    "class=")."""
    tag = "<td title=\"ver class='valor-monetario' aqui\">"
    assert tem_classe(tag, "valor-monetario") is True, (
        "se este teste começar a falhar, é porque a limitação foi CORRIGIDA — "
        "atualize também o docstring do módulo (apps/core/marcacao.py) e o "
        "achado BL-317 no backlog, em vez de só ajustar a asserção"
    )
