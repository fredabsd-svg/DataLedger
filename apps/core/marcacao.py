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
inclusive, depois desta etapa, pela própria varredura de interface
(`apps.core.tests.test_dl024_varredura_de_interface`), que hoje já tem a
versão correta escrita localmente e vai passar a importar daqui.

Nenhuma função aqui depende de Django nem de banco de dados: são funções
puras sobre uma STRING de tag HTML já aberta (ex.: o texto de uma tag de
abertura como `<td class="a valor-monetario b">` ou `<kbd class="tecla"
aria-hidden="true">`), nunca um parser de HTML completo — mesma limitação,
documentada, de todo o resto da varredura de interface deste projeto.
"""

import re

# `\s` OBRIGATÓRIO antes do nome do atributo: evita casar um atributo com
# outro NOME que só termina com o mesmo sufixo (ex.: `data-class="x"`
# contém a substring "class=", mas não é o atributo `class`) — a mesma
# prevenção que `apps.core.tests.test_dl024_varredura_de_interface` já
# aplica a `scope=`/`style=`.
def _padrao_atributo(nome_atributo):
    return re.compile(
        rf'\s{re.escape(nome_atributo)}\s*=\s*(?:"([^"]*)"|\'([^\']*)\')',
        re.IGNORECASE,
    )


_PADRAO_ATRIBUTO_CLASS = _padrao_atributo("class")


def valor_de_atributo(tag, nome_atributo):
    """Valor bruto (string, sem dividir por espaço) do atributo
    `nome_atributo` na tag de abertura `tag`, ou `None` se o atributo não
    existir. Aceita aspas simples ou duplas. Não distingue maiúsculas de
    minúsculas no NOME do atributo (HTML não distingue); o VALOR é
    devolvido como está, sem normalização.
    """
    atributo = _padrao_atributo(nome_atributo).search(tag)
    if not atributo:
        return None
    return atributo.group(1) if atributo.group(1) is not None else atributo.group(2)


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
