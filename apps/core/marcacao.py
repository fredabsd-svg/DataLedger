"""Funções compartilhadas de leitura de marcação HTML já renderizada —
usadas pelas guardas de teste que precisam confirmar que uma tag carrega um
determinado TOKEN (de `class` ou de outro atributo tokenizado por espaço),
nunca por substring nem por igualdade do valor inteiro.

BL-295/BL-296/BL-297 (rodada 4 da auditoria da DL-026,
docs/auditorias/2026-09-18-dl-024-rodada-2.md, achados M4 e M6): a mesma
lógica de "casar por TOKEN, nunca por substring nem por igualdade do valor
inteiro" tinha sido escrita, de forma independente, em pelo menos três
lugares:

1. `apps.core.tests.test_dl024_varredura_de_interface._tem_classe`
   (a versão original, correta — casa por token).
2. `apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade.
   PADRAO_TECLA`, que casava `class="tecla"` por IGUALDADE do valor
   inteiro: `class="tecla destaque"` escapava (M4/BL-295), e o mesmo valia
   para `PADRAO_ACCESSKEY`, que só reconhecia um `accesskey` de UMA letra —
   um valor com mais de um token (`accesskey="c d"`) escapava por INTEIRO
   de todas as guardas de coerência e duplicidade, em vez de ser
   reprovado.
3. `apps.contabilidade.tests.test_dl017_rodada2_frontend.
   descricoes_de_data_sem_defesa`, que casava `"texto-apoio" in atributos`
   por SUBSTRING: `class="texto-apoio-legenda"` (uma classe CSS DIFERENTE,
   que o seletor `.texto-apoio` não alcança) passava (M6/BL-297).

Três implementações da mesma regra divergem assim que uma delas é
corrigida sem as outras (AGENTS.md §8, "evitar duplicação de regras" —
DE-026/DE-030 aplicam o mesmo raciocínio a regra de negócio). Este módulo
existe para que exista uma implementação só, importada por quem precisar —
inclusive `apps.core.tests.test_dl024_varredura_de_interface`, que **agora
importa `tem_classe` daqui** (BL-310, auditoria DL-026 rodada 3, M1): antes
desta correção este parágrafo prometia isso e a varredura continuava com a
cópia local (`_tem_classe`/`_PADRAO_ATRIBUTO_CLASS`) — comentário
prometendo o que o código não fazia é o mesmo defeito que o AGENTS.md §9
proíbe para regra de negócio, só que na PRÓPRIA descrição deste módulo. A
duplicação nº 2 (`PADRAO_TECLA`/`PADRAO_ACCESSKEY`, em
`apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade`) continua
fora daqui: esse arquivo é do `especialista-frontend` nesta etapa, e a
correção do casamento sem aspas (achado M1 da rodada 3) não se estende a
ele por decisão de escopo, não por esquecimento — fica registrada para a
próxima rodada de quem for dono do arquivo.

Nenhuma função aqui depende de Django nem de banco de dados: são funções
puras sobre uma STRING de tag HTML já aberta (ex.: o texto de uma tag de
abertura como `<td class="a valor-monetario b">` ou `<kbd class="tecla"
aria-hidden="true">`), nunca um parser de HTML completo — mesma limitação,
documentada, de todo o resto da varredura de interface deste projeto.

**BL-322 (M4 da auditoria DL-026 rodada 4) — limitação do BL-317 CORRIGIDA,
não só documentada.** A versão anterior deste módulo (`_padrao_atributo`)
buscava `\\s<nome>\\s*=\\s*...` em QUALQUER posição da string da tag —
inclusive DENTRO do valor entre aspas de um OUTRO atributo. O comentário
registrado então (BL-317) afirmava que essa busca era sempre PERMISSIVA
("aceita de mais, nunca recusa de menos... nunca produz um FALSO alarme").
Medido pelo auditor: `<td title="use class=nenhum" class="valor-monetario">`
devolvia `tem_classe(tag, "valor-monetario") == False` — a célula TEM a
classe de verdade, e a guarda acusava marcação CORRETA. A causa era
`re.search` devolver a PRIMEIRA ocorrência da substring `class=` na tag
inteira — quando o texto-isca (`title="...class=..."`) vem ANTES do
atributo `class` real (a ordem mais comum, já que `title`/`alt`/
`aria-label` costumam vir antes de `class` em marcação escrita à mão), a
busca "encontrava" o `class=` de dentro do `title` e nunca chegava ao
`class` de verdade. A direção do erro era as DUAS, não uma: o texto do
BL-317 descrevia metade do comportamento real e usava a metade ausente
como justificativa para não corrigir (AGENTS.md §9: "o comentário deve
explicar... qual condição precisa preservar" — uma declaração que afirma
mais do que a defesa entrega é o mesmo defeito que este projeto reprova em
toda parte).

A correção ANCORA o casamento a partir do NOME DA TAG, em vez de buscar um
nome de atributo em qualquer posição: `atributos_da_tag` anda pela string,
atributo por atributo, e PULA o valor INTEIRO de cada um (aspas duplas,
aspas simples ou sem aspas) antes de procurar o próximo nome — o texto
dentro do valor de `title` nunca é reexaminado como se fosse um atributo
novo. Isso fecha as DUAS direções de uma vez: uma tag com `class` real
continua reconhecida (independente do que outro atributo contenha no seu
valor), e uma tag SEM `class` real não é mais confundida por um atributo
vizinho que só MENCIONA a palavra "class=" em prosa. `test_marcacao.py`
fixa as duas direções (achado do BL-322).
"""

import re

# Nome de atributo: qualquer sequência sem espaço, aspas, `=`, `<`, `>` nem
# crase — a mesma restrição de caractere que HTML5 já impõe ao NOME de um
# atributo (e que o valor sem aspas, abaixo, também respeita).
#
# Valor: aspas duplas, aspas simples, SEM aspas (HTML5 válido — M1/BL-310,
# auditoria DL-026 rodada 3: `<kbd class=tecla>` é HTML5 válido e o
# Chromium aplica; a busca antiga só reconhecia aspas) ou AUSENTE (atributo
# booleano, ex.: `<input disabled>` — sem `=`, sem valor).
#
# BL-322 (M4, auditoria DL-026 rodada 4): `\s+` OBRIGATÓRIO antes do nome é
# o que ANCORA cada atributo ao início da tag em vez de deixar o casamento
# começar em QUALQUER posição da string — combinado com o valor sendo
# CONSUMIDO por inteiro (inclusive as aspas), `re.finditer` nunca reexamina
# o conteúdo de um valor já consumido como se fosse um nome de atributo
# novo. É essa combinação — âncora + consumo do valor inteiro — que torna
# impossível o defeito do BL-317: o texto `class='valor-monetario'` dentro
# do VALOR de `title="ver class='valor-monetario' aqui"` nunca vira uma
# posição de início válida, porque a busca já consumiu o valor de `title`
# inteiro (da aspa de abertura até a de fechamento) num único passo antes
# de procurar o atributo seguinte.
_PADRAO_INICIO_DE_ATRIBUTO = re.compile(
    r"""
    \s+(?P<nome>[^\s"'=<>`]+)
    (?:\s*=\s*
        (?:"(?P<valor_aspas_duplas>[^"]*)"
         |'(?P<valor_aspas_simples>[^']*)'
         |(?P<valor_sem_aspas>[^\s"'=<>`]+))
    )?
    """,
    re.VERBOSE,
)


def atributos_da_tag(tag):
    """Lista de `(nome, valor)` de cada atributo da tag de abertura `tag`,
    na ORDEM em que aparecem — nome sempre em minúsculas (HTML não
    distingue maiúsculas de minúsculas no nome), valor `None` quando o
    atributo é booleano (sem `=`, ex.: `disabled`).

    Não precisa da tag de abertura INTEIRA (`<td ...>`): como o casamento
    exige `\\s+` antes do nome, um `<tagname` inicial sem espaço interno
    nunca produz um "atributo" falso — o primeiro `\\s+` válido só ocorre
    no espaço real antes do primeiro atributo. Por isso esta função (e,
    por extensão, `valor_de_atributo`/`tem_classe`) também aceita um
    TRECHO de tag que comece só nos atributos (sem o nome da tag) — usado
    por `apps.contabilidade.tests.test_dl017_rodada2_frontend`, que passa
    o grupo capturado de atributos diretamente, sem o `<nome-da-tag`.

    Função PÚBLICA (BL-305, auditoria DL-026 rodada 4): reaproveitada por
    `apps.core.tests.test_dl024_varredura_de_interface` para varrer COR e
    MEDIDA literal em atributo de apresentação de template — a mesma razão
    de existir deste módulo (AGENTS.md §8: não duplicar a lógica de andar
    atributo por atributo uma segunda vez).
    """
    atributos = []
    for casamento in _PADRAO_INICIO_DE_ATRIBUTO.finditer(tag):
        nome = casamento.group("nome").lower()
        valor = casamento.group("valor_aspas_duplas")
        if valor is None:
            valor = casamento.group("valor_aspas_simples")
        if valor is None:
            valor = casamento.group("valor_sem_aspas")
        atributos.append((nome, valor))
    return atributos


def valor_de_atributo(tag, nome_atributo):
    """Valor bruto (string, sem dividir por espaço) do atributo
    `nome_atributo` na tag de abertura `tag`, ou `None` se o atributo não
    existir. Aceita aspas simples, aspas duplas ou SEM aspas (HTML5 válido
    — ver o comentário de `_PADRAO_INICIO_DE_ATRIBUTO`). Não distingue
    maiúsculas de minúsculas no NOME do atributo; o VALOR é devolvido como
    está, sem normalização. Usa o PRIMEIRO atributo com esse nome, na
    ordem em que aparece na tag (HTML não permite o mesmo nome duas vezes
    numa tag válida; se acontecer, o primeiro vence — mesmo critério que
    navegadores aplicam).
    """
    nome_normalizado = nome_atributo.lower()
    for nome, valor in atributos_da_tag(tag):
        if nome == nome_normalizado:
            # `class=""` existe (o atributo está lá), só que vazio —
            # diferente de o atributo não existir. `valor` já é `""` nesse
            # caso (não `None`), então este `return` preserva a distinção.
            return valor if valor is not None else ""
    return None


def tokens_de_atributo(tag, nome_atributo):
    """Lista de tokens (separados por espaço) do atributo `nome_atributo`
    em `tag` — lista vazia se o atributo não existir ou estiver vazio.
    Válido tanto para `class` (tokens = nomes de classe CSS) quanto para
    `accesskey` (tokens = teclas alternativas, cada uma de um caractere,
    conforme a HTML Living Standard) ou qualquer outro atributo cujo valor
    seja uma lista separada por espaço.
    """
    valor = valor_de_atributo(tag, nome_atributo)
    return valor.split() if valor else []


def tem_classe(tag, classe):
    """`True` se `classe` está entre os nomes de classe CSS do atributo
    `class` de `tag` — casada como TOKEN inteiro, separado por espaço,
    NUNCA como substring do atributo nem por igualdade do valor inteiro.

    Três classes de defeito que esta função fecha (ver o docstring do
    módulo para os achados que motivaram cada uma):

    - substring: `"texto-apoio" in atributos` casaria com
      `class="texto-apoio-legenda"`, que é uma classe CSS DIFERENTE
      (M6/BL-297).
    - igualdade do valor inteiro: `class="tecla"` (comparação exata do
      valor completo do atributo) deixaria de casar assim que o elemento
      ganhasse uma segunda classe, `class="tecla destaque"` (M4/BL-295).
    - atributo VIZINHO cujo VALOR só menciona a palavra "class=" em prosa
      (`title="ver class='x' aqui"`) não pode ser confundido com o
      atributo `class` de verdade — nas duas direções: nem aceitar de mais
      (achar uma classe que não existe) nem acusar de menos (não achar uma
      classe que existe, só porque outro atributo, escrito ANTES, também
      menciona a palavra) — BL-322/M4, auditoria DL-026 rodada 4.
    """
    return classe in tokens_de_atributo(tag, "class")
