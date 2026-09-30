"""Apoio aos testes que precisam gravar dado INVÁLIDO de propósito (DL-052).

Desde a migração 0013, em PostgreSQL o banco recusa o que estes testes
montavam por `.update()`/SQL: lote desbalanceado, lançamento sem partidas,
UPDATE/DELETE de lançamento e item. Para um teste que precisa EXATAMENTE
desse dado (p.ex. provar que a Conferência acusa lote desbalanceado),
`gatilho_desligado` desliga o gatilho por nome, SÓ dentro do bloco e SÓ na
transação do teste (`ALTER TABLE ... DISABLE TRIGGER` é transacional), e o
religa no `finally`.

Regras de uso, para não virar brecha:

- desligue o gatilho MÍNIMO que o teste precisa, nunca `DISABLE TRIGGER ALL`;
- a asserção do teste NÃO muda — só a montagem do dado;
- qualquer erro de banco dentro do bloco deve ficar dentro de um
  `transaction.atomic()` (savepoint): depois de erro sem savepoint a transação
  está abortada e o `ENABLE` do `finally` também falharia;
- em SQLite não há gatilho (migração 0013 é no-op lá), então é no-op.

Por que `check_constraints()` antes de cada `ALTER TABLE`: o PostgreSQL recusa
`ALTER TABLE` numa tabela com eventos de gatilho PENDENTES na transação
("cannot ALTER TABLE ... because it has pending trigger events"), e toda
gravação com FK deixa evento pendente (as FKs do Django são adiadas).
`check_constraints()` emite `SET CONSTRAINTS ALL IMMEDIATE` (julga e descarta
os eventos pendentes) e volta a `DEFERRED`. Consequência desejada: dado
inválido gravado ANTES do bloco, com os gatilhos ligados, reprova aqui.
"""

from contextlib import contextmanager

import pytest
from django.db import connection

TABELA_LANCAMENTO = "contabilidade_lancamentocontabil"
TABELA_ITEM = "contabilidade_itemlancamento"

# Imutabilidade (BEFORE UPDATE OR DELETE).
IMUTAVEL_LANCAMENTO = (TABELA_LANCAMENTO, "trg_lancamento_contabil_imutavel")
IMUTAVEL_ITEM = (TABELA_ITEM, "trg_item_lancamento_imutavel")
# Partidas dobradas, julgadas no COMMIT (CONSTRAINT TRIGGER adiado).
BALANCEADO_ITEM = (TABELA_ITEM, "trg_item_lancamento_balanceado")
BALANCEADO_LANCAMENTO = (TABELA_LANCAMENTO, "trg_lancamento_contabil_balanceado")


@contextmanager
def gatilho_desligado(*gatilhos):
    """Desliga cada `(tabela, gatilho)` dentro do bloco e religa no fim."""
    if connection.vendor != "postgresql":
        yield
        return
    connection.check_constraints()
    with connection.cursor() as cursor:
        for tabela, nome in gatilhos:
            cursor.execute(f"ALTER TABLE {tabela} DISABLE TRIGGER {nome}")
    try:
        yield
    finally:
        connection.check_constraints()
        with connection.cursor() as cursor:
            for tabela, nome in gatilhos:
                cursor.execute(f"ALTER TABLE {tabela} ENABLE TRIGGER {nome}")


@pytest.fixture
def sem_julgamento_de_partidas(db):
    """Fixture de opt-in: o teste grava, de propósito, lançamento sem partidas
    ou desbalanceado (é isso que ele testa — Conferência, fechamento recusado
    por lote torto, unicidade de estorno sobre lançamento "nu" etc.). Desliga
    SÓ os dois gatilhos adiados de partidas dobradas, durante o teste; os de
    imutabilidade e o CHECK de valor seguem ligados. A asserção do teste não
    muda. Uso: `@pytest.mark.usefixtures("sem_julgamento_de_partidas")`."""
    with gatilho_desligado(BALANCEADO_LANCAMENTO, BALANCEADO_ITEM):
        yield
