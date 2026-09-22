"""Testes para a enumeração ClasseDocumento.

A enum tem TRÊS valores, fixados pela descoberta do
`docs/projeto/personalizacao-de-relatorio.md` (seção 1) e pela
`HI-11` do `docs/projeto/requisitos.md` (três classes de documento,
não uma lista única, porque cada uma tem forma fixada por norma
distinta):

  1. CONFERENCIA — relatório de apoio (balancete de verificação, razão de
     conferência, listagens). Nenhuma norma contábil fixa o cabeçalho.
  2. DEMONSTRACAO — balanço, DRE, DMPL, DFC, notas. NBC TG 26 (R5) item 51
     fixa a identificação obrigatória; item 52 diz que se cumpre "em cada
     página".
  3. LIVRO — diário e razão NA FORMA DE LIVRO. NBC ITG 2000 (R1) itens 5,
     9, 10, 13.

A regra estruturante do DL-027 é que o sistema **não emite** documentos de
classe LIVRO até `PE-52` ser respondida (legislação específica que exige
autenticação do livro digital). A enum existe agora para poder ser
**proibida**: a guarda da `views.py` recusa personalização em documento
declarado como livro. Desenhar a fronteira agora é barato; descobrir
que a personalização já estava ligada lá dentro, depois, não é.

Os testes aqui cobrem só o **contrato da enum** — não a guarda, que mora
no teste da fatia seguinte. Este arquivo existe para documentar o
vocabulário em código e para fixar o invariante "três valores, e não
mais, e não menos" como teste de regressão.
"""

from __future__ import annotations

import pytest

from apps.core.escolhas import EscolhaInvalida, para_escolha
from apps.documentos.escolhas import ClasseDocumento


def test_os_tres_valores_sao_os_esperados_e_nenhum_mais():
    """O vocabulário da enumeração é **três** valores, e não mais nem menos.

    Adicionar uma classe nova é decisão de produto — não cabe como
    refatoração. Este teste é a trava contra a classe "a mais" ou "a
    menos" silenciosa, que apareceria sem aviso.
    """
    # `TextChoices.values` no Django devolve `list`, não `tuple` — casar
    # com `set` (mais barato) para o teste ser estável contra a
    # representação serializada, e `frozenset` também elimina ordem como
    # detalhe do contrato.
    assert frozenset(ClasseDocumento.values) == frozenset({"conferencia", "demonstracao", "livro"})
    assert len(ClasseDocumento.values) == 3


def test_a_label_humana_de_cada_classe():
    """O `label` da `TextChoices` vira texto da interface; precisa
    ser legível, não o slug."""
    assert ClasseDocumento.CONFERENCIA.label == "Conferência"
    assert ClasseDocumento.DEMONSTRACAO.label == "Demonstração"
    assert ClasseDocumento.LIVRO.label == "Livro"


def test_cada_valor_e_uma_string_exata():
    """`TextChoices` tem armadilhas conhecidas: comparar `ClasseDocumento.
    CONFERENCIA == "conferencia"` funciona, mas `str(ClasseDocumento.
    CONFERENCIA)` é a *member*, não o valor. O `value` é o que vai para
    o banco — e precisa ser a string exata, sem espaços nem variações
    de caixa."""
    assert ClasseDocumento.CONFERENCIA.value == "conferencia"
    assert ClasseDocumento.DEMONSTRACAO.value == "demonstracao"
    assert ClasseDocumento.LIVRO.value == "livro"


def test_para_escolha_aceita_os_tres_valores():
    """A função de julgamento compartilhada (`apps.core.escolhas`) tem
    que tratar a enum como uma lista de strings válida — é o que a
    `views.py` usa para validar entrada de usuário."""
    for classe in ClasseDocumento.values:
        assert para_escolha(classe, ClasseDocumento.values, nome_campo="classe") == classe


def test_para_escolha_recusa_string_desconhecida():
    """A mensagem cita o nome do campo E os valores válidos — é o que
    o cliente da API usa para saber o que devolver."""
    with pytest.raises(EscolhaInvalida) as exc_info:
        para_escolha("ata", ClasseDocumento.values, nome_campo="classe")
    mensagem = str(exc_info.value)
    assert "classe" in mensagem
    # A mensagem lista os valores válidos sem aspas (formato atual do
    # `apps.core.escolhas.para_escolha`); o teste continua verificando
    # que cada um aparece, porque o cliente da API precisa ver a lista
    # para corrigir a requisição.
    for valor_valido in ClasseDocumento.values:
        assert valor_valido in mensagem


def test_para_escolha_recusa_variacao_de_caixa():
    """A enumeração não normaliza — `"LIVRO"` é tão inválido quanto
    `"livro digital"`. Política do módulo: nunca corrigir entrada em
    silêncio."""
    with pytest.raises(EscolhaInvalida):
        para_escolha("LIVRO", ClasseDocumento.values, nome_campo="classe")


@pytest.mark.parametrize(
    ("valor_invalido", "motivo"),
    [
        (None, "None não é escolha"),
        (0, "inteiro não é escolha"),
        (1, "mesmo inteiro que parece valor"),
        (-1, "negativo não é escolha"),
        (3, "fora da faixa"),
        ([], "lista não é escolha"),
        ({}, "dicionário não é escolha"),
        (["conferencia"], "lista dentro de outra lista não é a string"),
        (True, "True não é string"),
        (False, "False não é string"),
        ("", "string vazia não é escolha"),
        (" ", "espaço não é escolha"),
        ("livro digital", "subclasse não é escolha"),
        ("livros", "plural não é escolha"),
    ],
)
def test_para_escolha_recusa_tipos_e_valores_fora_do_vocabulario(valor_invalido, motivo):
    """A enumeração é `str` e é **fechada** — qualquer outro tipo, e
    qualquer string fora dos três valores, é inválido. O `motivo` no
    `parametrize` documenta a intenção de cada caso, para a próxima
    pessoa que olhar não precisar adivinhar o que se está provando."""
    with pytest.raises(EscolhaInvalida):
        para_escolha(valor_invalido, ClasseDocumento.values, nome_campo="classe")
