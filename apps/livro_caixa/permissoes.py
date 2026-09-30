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

from apps.core.papeis_de_fechamento import PAPEIS_QUE_FECHAM_PERIODO
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


# DL-053 / RC-146 (= RC-102): fechar e reabrir o mês do livro-caixa é de
# ADMINISTRADOR ou GESTOR, "a mesma regra da contabilidade" (Fred,
# 2026-09-30). Ao contrário das duas tuplas acima — copiadas por VALOR de
# propósito, porque escrita e leitura são regimes distintos —, esta é a MESMA
# tupla da contabilidade, por REFERÊNCIA: a regra pedida é uma só, e
# `apps.core.papeis_de_fechamento` é o único lugar onde ela está escrita.
PAPEIS_QUE_FECHAM_MES_CAIXA = PAPEIS_QUE_FECHAM_PERIODO


def papel_pode_fechar_mes_caixa(papel):
    """`None` (sem papel resolvido) sempre devolve `False`. Mesma decisão
    para a API e para a tela — nenhuma segunda lista."""
    return papel in PAPEIS_QUE_FECHAM_MES_CAIXA
