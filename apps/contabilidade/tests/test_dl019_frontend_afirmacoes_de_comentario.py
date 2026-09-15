"""BL-150 / R6-3 — a família "comentário que afirma que X usa o julgador Y".

A BL-146 criou UM teste para esta família e ele não conseguia falhar: a
linha que decidia era

    api_de_fato_usa = "para_id" in inspect.getsource(views_api)

e `para_id` aparece em **dois comentários** de `apps/contabilidade/views.py`.
Removendo o import E a chamada, a string continua no fonte — o valor é
permanentemente `True`, e o mutante M17 do auditor (a situação R5-3
inteira) mata 7 testes do BL-142 e **passa** justamente no teste que existe
para pegá-lo. Décimo-primeiro caso registrado nesta etapa de "teste que não
consegue falhar".

O que este arquivo faz, e é a diferença que importa:

1. A pergunta "X de fato usa Y?" é respondida contra o **código** de X, com
   comentários e literais de texto **removidos por `tokenize`** — não
   contra o fonte bruto. Um comentário nunca mais responde por si mesmo.
2. O escopo é a **função/classe citada pela frase**, não o módulo inteiro
   (molde de `test_extrair_itens_usa_para_id`, que é quem realmente pegou o
   M17).
3. A verificação deixa de ser de UMA frase e passa a ser de uma **tabela**
   com as **nove** frases desta família que existem hoje no repositório
   (as 7 que o auditor catalogou, mais as 2 do mesmo padrão que vivem no
   mesmo bloco). Cada linha falha por dois motivos diferentes: a frase
   sumiu/mudou (a tabela virou mentira sobre o repositório) ou a frase
   passou a ser falsa (o julgador citado não é mais usado onde ela diz).

Nada aqui depende de banco de dados. Sem dado de cliente.
"""

import importlib
import inspect
import io
import re
import textwrap
import tokenize

import pytest

# Tipos de token que NÃO são código: comentário e literal de texto
# (inclusive docstring). `FSTRING_MIDDLE` só existe a partir do Python
# 3.12 e é a parte LITERAL de uma f-string — as expressões dentro dela vêm
# como tokens próprios e continuam contando como código, que é o que
# queremos.
_TIPOS_QUE_NAO_SAO_CODIGO = {tokenize.COMMENT, tokenize.STRING}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    _TIPOS_QUE_NAO_SAO_CODIGO.add(tokenize.FSTRING_MIDDLE)


def codigo_sem_comentarios_nem_textos(fonte):
    """Devolve `fonte` com comentários e literais de texto substituídos por
    espaços, **preservando posições** — linhas e colunas continuam as
    mesmas, então `"para_id("` continua grudado se for uma chamada de
    verdade.

    Substituir por espaço (em vez de remover) é deliberado: remover juntaria
    tokens vizinhos e criaria casamentos que não existem no código.
    """
    fonte = textwrap.dedent(fonte)
    linhas = fonte.splitlines(keepends=True)
    editaveis = [list(linha) for linha in linhas]
    for token in tokenize.generate_tokens(io.StringIO(fonte).readline):
        if token.type not in _TIPOS_QUE_NAO_SAO_CODIGO:
            continue
        (linha_inicial, coluna_inicial), (linha_final, coluna_final) = token.start, token.end
        for numero in range(linha_inicial, linha_final + 1):
            alvo = editaveis[numero - 1]
            inicio = coluna_inicial if numero == linha_inicial else 0
            fim = coluna_final if numero == linha_final else len(alvo)
            for coluna in range(inicio, min(fim, len(alvo))):
                if alvo[coluna] != "\n":
                    alvo[coluna] = " "
    return "".join("".join(linha) for linha in editaveis)


def prosa_normalizada(fonte):
    """Devolve a PROSA de `fonte` (comentários e docstrings) numa linha só,
    sem os marcadores `#` e com espaços colapsados.

    Existe para que uma frase catalogada na tabela abaixo possa ser escrita
    como o contador a leria, sem depender de onde o `ruff format` quebrou a
    linha — a quebra muda a cada reformatação, e uma tabela que dependesse
    dela viraria manutenção pura.
    """
    linhas = []
    for linha in fonte.splitlines():
        sem_indentacao = linha.strip()
        if sem_indentacao.startswith("#"):
            sem_indentacao = sem_indentacao[1:].strip()
        linhas.append(sem_indentacao)
    return re.sub(r"\s+", " ", " ".join(linhas)).strip()


def _objeto(caminho):
    """Resolve "pacote.modulo:Classe.metodo" (ou "pacote.modulo") para o
    objeto, para `inspect.getsource` poder recortar o escopo citado pela
    frase — nunca o módulo inteiro quando a frase nomeia uma função.
    """
    if ":" not in caminho:
        return importlib.import_module(caminho)
    modulo, resto = caminho.split(":", 1)
    objeto = importlib.import_module(modulo)
    for parte in resto.split("."):
        objeto = getattr(objeto, parte)
    return objeto


# Cada linha: (apelido, módulo que AFIRMA, frase como o leitor a lê,
# [(escopo que precisa usar, agulha que só o USO produz), ...]).
#
# A agulha tem parênteses (`para_id(`) ou ponto (`_PADRAO_NIVEL_SIMPLES.`)
# de propósito: é o que distingue a CHAMADA/USO da menção em prosa. O
# recorte por `codigo_sem_comentarios_nem_textos` já removeria a prosa, e a
# agulha com parêntese é a segunda metade da mesma defesa — as duas se
# reforçam, como o par estrutural+comportamental do gate de navegador.
AFIRMACOES = [
    (
        "views_web:9 — permissão de escrita da tela é a da API",
        "apps.contabilidade.views_web",
        "reaproveita a MESMA classe de permissão que a API já usa para escrever",
        [("apps.contabilidade.views", "PodeEscriturar")],
    ),
    (
        "views_web:335 — gramática de nível é a da API",
        "apps.contabilidade.views_web",
        "mesmo padrão que a API já usa, não uma segunda cópia",
        [("apps.contabilidade.views", "_PADRAO_NIVEL_SIMPLES.")],
    ),
    (
        "views_web:107 — para_id na API de contabilidade (a frase da BL-146)",
        "apps.contabilidade.views_web",
        "**e para a API de contabilidade**",
        [("apps.contabilidade.views:_extrair_itens", "para_id(")],
    ),
    (
        "views_web:858 — conta_id usa o julgador da API e do tenancy",
        "apps.contabilidade.views_web",
        "o mesmo julgador (`para_id`) que a API e `apps.tenancy` já usam",
        [
            ("apps.contabilidade.views:_extrair_itens", "para_id("),
            ("apps.tenancy.views", "para_id("),
        ],
    ),
    (
        "views_web:883 — teto de magnitude é o que a API já verifica",
        "apps.contabilidade.views_web",
        "Mesmo teto de MAGNITUDE que a API já verifica em `_extrair_itens`",
        [("apps.contabilidade.views:_extrair_itens", "LIMITE_MAGNITUDE_VALOR")],
    ),
    (
        "views_web:1271 — data do lançamento usa o julgador do período",
        "apps.contabilidade.views_web",
        "mesmo julgador partilhado do período",
        [("apps.contabilidade.views_web:_periodo_do_formulario", "para_data(")],
    ),
    (
        "tenancy/views:137 — trocar escritório usa o julgador da view irmã",
        "apps.tenancy.views",
        "com o mesmo julgador usado em `EscritorioAtivoView.post`",
        [("apps.tenancy.views:EscritorioAtivoView.post", "para_id(")],
    ),
    (
        "permissoes:28 — a tela de lançamento usa PodeEscriturar",
        "apps.contabilidade.permissoes",
        "usa a regra de `PodeEscriturar` em `views.py`",
        [("apps.contabilidade.views_web", "PodeEscriturar")],
    ),
    (
        "permissoes:36 — a fonte do papel é a mesma que a API usa",
        "apps.contabilidade.permissoes",
        "mesma fonte que `apps.tenancy.permissions.papel_permitido` já usa na API",
        # A agulha aqui NÃO pode conter `"papel"`: o nome do atributo está
        # num literal de texto (`getattr(request, "papel", None)`), e
        # literal de texto é exatamente o que esta varredura apaga. Sobram
        # as duas metades que são código de verdade — ler de `request` por
        # `getattr` e decidir contra a lista de papéis.
        [
            ("apps.tenancy.permissions:papel_permitido", "getattr(request,"),
            ("apps.tenancy.permissions:papel_permitido", "in papeis"),
        ],
    ),
]


@pytest.mark.parametrize(
    "apelido, modulo_que_afirma, frase, alvos",
    AFIRMACOES,
    ids=[linha[0] for linha in AFIRMACOES],
)
def test_frase_sobre_julgador_partilhado_e_verdadeira(apelido, modulo_que_afirma, frase, alvos):
    """Para cada frase catalogada: ela ainda está escrita onde a tabela diz
    (do contrário a tabela virou mentira e alguém precisa decidir), e o
    julgador que ela promete é DE FATO usado no escopo citado, medido no
    código com a prosa removida.
    """
    fonte_que_afirma = inspect.getsource(importlib.import_module(modulo_que_afirma))
    assert prosa_normalizada(frase) in prosa_normalizada(fonte_que_afirma), (
        f"A frase catalogada não está mais em {modulo_que_afirma}: "
        "atualize a tabela AFIRMACOES (se o comentário foi reescrito) ou "
        "recoloque a afirmação. Uma tabela que não bate com o repositório "
        "não defende nada."
    )
    for caminho_do_alvo, agulha in alvos:
        codigo = codigo_sem_comentarios_nem_textos(inspect.getsource(_objeto(caminho_do_alvo)))
        assert agulha in codigo, (
            f"{modulo_que_afirma} afirma «{frase}», mas {caminho_do_alvo} não usa "
            f"{agulha!r} no CÓDIGO (comentários e textos removidos). "
            "Ou o uso voltou a não existir, ou a frase precisa deixar de prometê-lo."
        )


def test_a_medicao_ignora_comentario_e_texto_e_ve_a_chamada():
    """O instrumento desta varredura, medido — sem ele, todo o resto é
    afirmação de forma outra vez.

    Reproduz o M17 em miniatura: um fonte onde o julgador aparece **só** em
    comentário e em literal de texto não pode contar como uso; um fonte
    onde ele é chamado, sim. É o teste que impede esta tabela inteira de
    virar o décimo-segundo teste que não consegue falhar.
    """
    so_prosa = '# aqui a gente usa para_id( de verdade\nx = "para_id("\n'
    assert "para_id(" not in codigo_sem_comentarios_nem_textos(so_prosa)

    com_chamada = "# nada a declarar\nconta_id = para_id(bruto)\n"
    assert "para_id(" in codigo_sem_comentarios_nem_textos(com_chamada)

    # E a posição não se desloca: a prosa vira espaço, nunca desaparece.
    assert len(codigo_sem_comentarios_nem_textos(so_prosa)) == len(so_prosa)


def test_a_normalizacao_de_prosa_nao_depende_de_onde_a_linha_foi_quebrada():
    """Controle do outro instrumento: a mesma frase, quebrada em duas
    linhas de comentário, normaliza para o mesmo texto de uma linha. Sem
    isto, a tabela quebraria a cada `ruff format` e a reação natural seria
    afrouxar a busca — que é exatamente como o `"para_id"` sem parêntese
    apareceu.
    """
    quebrada = "    # o mesmo julgador (`para_id`) que a API e\n    # `apps.tenancy` já usam\n"
    assert (
        prosa_normalizada("o mesmo julgador (`para_id`) que a API e `apps.tenancy` já usam")
        in prosa_normalizada(quebrada)
    )
