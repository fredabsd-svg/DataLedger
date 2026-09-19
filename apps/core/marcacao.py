"""Funções compartilhadas de leitura de marcação HTML já renderizada —
usadas pelas guardas de teste que precisam confirmar que uma tag carrega um
determinado TOKEN (de `class` ou de outro atributo tokenizado por espaço),
nunca por substring nem por igualdade do valor inteiro.

BL-295/BL-296/BL-297 (rodada 4 da auditoria da DL-024,
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
importa `tem_classe` daqui** (BL-310, auditoria DL-024 rodada 3, M1): antes
desta correção este parágrafo prometia isso e a varredura continuava com a
cópia local (`_tem_classe`/`_PADRAO_ATRIBUTO_CLASS`) — comentário
prometendo o que o código não fazia é o mesmo defeito que o AGENTS.md §9
proíbe para regra de negócio, só que na PRÓPRIA descrição deste módulo. A
duplicação nº 2 (`PADRAO_TECLA`/`PADRAO_ACCESSKEY`, em
`apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade`) continua
fora daqui: esse arquivo é do `especialista-frontend` nesta etapa, e a
correção do casamento sem aspas (achado M1 abaixo) não se estende a ele por
decisão de escopo, não por esquecimento — fica registrada para a próxima
rodada de quem for dono do arquivo.

Nenhuma função aqui depende de Django nem de banco de dados: são funções
puras sobre uma STRING de tag HTML já aberta (ex.: o texto de uma tag de
abertura como `<td class="a valor-monetario b">` ou `<kbd class="tecla"
aria-hidden="true">`), nunca um parser de HTML completo — mesma limitação,
documentada, de todo o resto da varredura de interface deste projeto.

**Limitação aceita, registrada (BL-317, B3 da auditoria DL-024 rodada 3):**
`_padrao_atributo` casa `\s<nome>\s*=\s*...` em QUALQUER posição da string
da tag — inclusive DENTRO do valor entre aspas de um OUTRO atributo. Uma
tag como `<td title="ver class='valor-monetario' aqui">{{ x_ptbr }}</td>`
faz `tem_classe(tag, "valor-monetario")` devolver `True` mesmo sem a célula
ter, de fato, a classe — o texto `class='valor-monetario'` está dentro do
VALOR de `title`, não é um atributo `class` de verdade. Corrigir isto de
verdade exige rastrear o estado de aspas desde o início da tag (saber que a
posição do casamento está dentro de uma string já aberta por outro
atributo) — a fronteira exata entre "expressão regular sobre texto de tag"
e "parser de atributos HTML", que este módulo decide, por documento, NÃO
cruzar (mesma linha do parágrafo anterior). Auditado como contrivado (sem
caso real na base de templates deste projeto — nenhum atributo de texto
livre como `title`/`alt` contém a palavra "class=" hoje) e na direção
PERMISSIVA (aceita de mais, nunca recusa de menos, então nunca produz um
FALSO alarme — o risco é o oposto, deixar passar uma célula sem a classe):
decisão do `desenvolvedor-pleno` (BL-317) de REGISTRAR a limitação em vez
de escrever um parser de atributos para um caso sem ocorrência real,
documentada aqui e coberta por teste que fixa o comportamento atual em
`apps/core/tests/test_marcacao.py` — para que uma correção futura precise
atualizar o teste conscientemente, não descobrir a limitação de novo por
auditoria.
"""

import re


# `\s` OBRIGATÓRIO antes do nome do atributo: evita casar um atributo com
# outro NOME que só termina com o mesmo sufixo (ex.: `data-class="x"`
# contém a substring "class=", mas não é o atributo `class`) — a mesma
# prevenção que `apps.core.tests.test_dl024_varredura_de_interface` já
# aplica a `scope=`/`style=`.
#
# M1/BL-310 (auditoria DL-024 rodada 3): a TERCEIRA alternativa —
# `[^\s"'=<>`]+`, valor SEM aspas — faltava aqui, embora `PADRAO_ESTILO_
# EMBUTIDO` (test_dl024_varredura_de_interface.py) já a tivesse, corrigida
# NO MESMO DIA, para `style=`. HTML5 aceita atributo sem aspas desde que o
# valor não tenha espaço, aspas, `=`, `<`, `>` nem crase (a mesma restrição
# do padrão de estilo, reaproveitada aqui) — e o Chromium aplica de verdade:
# `<kbd class=tecla>` estilizava igual a `<kbd class="tecla">`, mas
# `tem_classe(tag, "tecla")` devolvia `False`, porque a busca só reconhecia
# aspas. Medido: cinco `<kbd class="tecla" ...>` trocados por `class=tecla`
# em `_navegacao_empresa.html` — suíte inteira `1451 passed` — e a árvore de
# acessibilidade do Chromium confirmando o vazamento do atalho para o nome
# do link (`'Plano de contas Alt+C'` em vez de `'Plano de contas'` com
# `keyshortcuts=['Alt+C']` separado). A lição já estava escrita para
# `style=` no mesmo commit; não tinha atravessado para este módulo, criado
# justamente para que uma correção de casamento de atributo não precisasse
# ser feita duas vezes.
def _padrao_atributo(nome_atributo):
    return re.compile(
        rf'\s{re.escape(nome_atributo)}\s*=\s*'
        rf"(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+))",
        re.IGNORECASE,
    )


_PADRAO_ATRIBUTO_CLASS = _padrao_atributo("class")


def valor_de_atributo(tag, nome_atributo):
    """Valor bruto (string, sem dividir por espaço) do atributo
    `nome_atributo` na tag de abertura `tag`, ou `None` se o atributo não
    existir. Aceita aspas simples, aspas duplas ou SEM aspas (HTML5 válido
    — ver o comentário de `_padrao_atributo`). Não distingue maiúsculas de
    minúsculas no NOME do atributo (HTML não distingue); o VALOR é
    devolvido como está, sem normalização.
    """
    atributo = _padrao_atributo(nome_atributo).search(tag)
    if not atributo:
        return None
    # Exatamente um dos três grupos captura (aspas duplas, aspas simples ou
    # sem aspas) — os outros dois ficam `None`. `next(..., "")` cobre o
    # único caso em que NENHUM captura texto: `nome=""` com aspas duplas
    # vazias, onde o grupo 1 é `""` (não `None`) e já é achado primeiro.
    return next((g for g in atributo.groups() if g is not None), "")


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

    Duas classes de defeito que esta função fecha (ver o docstring do
    módulo para os achados que motivaram cada uma):

    - substring: `"texto-apoio" in atributos` casaria com
      `class="texto-apoio-legenda"`, que é uma classe CSS DIFERENTE
      (M6/BL-297).
    - igualdade do valor inteiro: `class="tecla"` (comparação exata do
      valor completo do atributo) deixaria de casar assim que o elemento
      ganhasse uma segunda classe, `class="tecla destaque"` (M4/BL-295).
    """
    return classe in tokens_de_atributo(tag, "class")
