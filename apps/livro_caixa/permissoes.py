"""Fonte única de "este papel pode ler o livro-caixa?" — mesmo desenho de
`apps.contabilidade.permissoes.papel_pode_ler_contabilidade` (DE-026): uma
função sem DRF, para a API (`views.py`) e uma futura tela chamarem a MESMA
decisão, sem cada lado ter sua própria cópia da lista de papéis.

Instrução da tarefa (DL-046): "mesma matriz da contabilidade: escritura quem
escritura, lê quem lê" — por isso os papéis autorizados aqui são
INTENCIONALMENTE os mesmos de `PAPEIS_QUE_LEEM_CONTABILIDADE`/
`PodeEscriturar` (apps/contabilidade), copiados por VALOR (a tupla, não uma
referência à outra) porque livro-caixa e contabilidade são regimes de
escrituração DIFERENTES (RC-113/RC-114) e não devem compartilhar a mesma
fonte de regra — mudar quem escreve/lê UM dos dois módulos não deve, por
acidente de referência compartilhada, mudar o outro.
"""

from apps.tenancy.models import Papel

PAPEIS_QUE_ESCRITURAM_LIVRO_CAIXA = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
)

PAPEIS_QUE_LEEM_LIVRO_CAIXA = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
)


def papel_pode_escriturar_livro_caixa(papel):
    """`None` (sem papel resolvido) sempre devolve `False`."""
    return papel in PAPEIS_QUE_ESCRITURAM_LIVRO_CAIXA


def papel_pode_ler_livro_caixa(papel):
    """`None` (sem papel resolvido) sempre devolve `False`."""
    return papel in PAPEIS_QUE_LEEM_LIVRO_CAIXA
