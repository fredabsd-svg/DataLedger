# DL-052, rodada 1 de auditoria, achado D2 — partida nova só entra em
# lançamento que nasceu NA MESMA TRANSAÇÃO.
#
# Brecha medida: os gatilhos da 0013 recusam UPDATE e DELETE, mas não INSERT;
# um par balanceado de itens inserido numa transação POSTERIOR passava pelo
# gatilho de partidas dobradas e alterava o movimento de lançamento já
# efetivado (inclusive de competência encerrada), sem estorno nem trilha.
#
# Desenho (aprovado pelo arquiteto-senior): um marcador LOCAL À TRANSAÇÃO.
#
# - `BEFORE INSERT` no lançamento acrescenta `NEW.id` ao marcador
#   `dataledger.lancamentos_da_transacao` (`set_config(..., is_local => true)`,
#   lista no formato `,12,15,`).
# - `BEFORE INSERT` no item recusa se `NEW.lancamento_id` não estiver no
#   marcador (`CONSTRAINT = 'item_lancamento_em_lancamento_efetivado'`).
#
# Por que o marcador, e não `xmin = txid_current()`: a linha do lançamento é
# inserida em SUBTRANSAÇÃO quando o serviço usa `atomic()` aninhado (savepoint),
# e `xmin` passa a ser o xid da subtransação, não o `txid_current()` — falso
# positivo para o caminho normal do produto. O marcador `SET LOCAL` se comporta
# certo nos três casos que importam:
#   * dura até o fim da transação externa (itens entram depois de o savepoint
#     do lançamento ser liberado);
#   * some no COMMIT/ROLLBACK (uma transação posterior não herda nada);
#   * é revertido com `ROLLBACK TO SAVEPOINT` (id de lançamento desfeito não
#     deixa "fantasma" que permita inserir item depois).
#
# `NEW.id` já está atribuído num gatilho BEFORE INSERT de linha (mesma
# observação da 0009).
#
# Custo: a busca no marcador é linear no número de lançamentos criados NA MESMA
# transação (importação em lote grande); aceito por simplicidade.
#
# Limite operacional declarado: restauração de backup por `pg_restore` insere
# itens em transação separada da do lançamento; ela precisa de
# `--disable-triggers` (superusuário) ou carga numa única transação — assunto
# do plano de backup/restauração (PE-07), não desta migração.
#
# Só PostgreSQL (no-op em SQLite, limite aceito como na 0009). Reversão remove
# os dois gatilhos e as duas funções.

from django.db import migrations

_CRIAR_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_marcar_lancamento_da_transacao()
RETURNS trigger AS $$
BEGIN
    PERFORM set_config(
        'dataledger.lancamentos_da_transacao',
        COALESCE(NULLIF(current_setting('dataledger.lancamentos_da_transacao', true), ''), ',')
            || NEW.id || ',',
        true
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lancamento_contabil_marca_transacao
    BEFORE INSERT ON contabilidade_lancamentocontabil
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_marcar_lancamento_da_transacao();

CREATE OR REPLACE FUNCTION contabilidade_item_so_em_lancamento_da_transacao()
RETURNS trigger AS $$
BEGIN
    IF position(
        ',' || NEW.lancamento_id || ',' IN
        COALESCE(current_setting('dataledger.lancamentos_da_transacao', true), '')
    ) = 0 THEN
        RAISE EXCEPTION
            'O lançamento % já está efetivado: partida nova só entra no lançamento criado '
            'na mesma transação. Registre um estorno.', NEW.lancamento_id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'item_lancamento_em_lancamento_efetivado';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_item_lancamento_so_em_lancamento_novo
    BEFORE INSERT ON contabilidade_itemlancamento
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_item_so_em_lancamento_da_transacao();
"""

_REMOVER_SQL = """
DROP TRIGGER IF EXISTS trg_item_lancamento_so_em_lancamento_novo ON contabilidade_itemlancamento;
DROP TRIGGER IF EXISTS trg_lancamento_contabil_marca_transacao ON contabilidade_lancamentocontabil;
DROP FUNCTION IF EXISTS contabilidade_item_so_em_lancamento_da_transacao();
DROP FUNCTION IF EXISTS contabilidade_marcar_lancamento_da_transacao();
"""


def _criar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_SQL, params=None)


def _remover(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0015_dl052_r1_tipo_do_item_valido"),
    ]

    operations = [
        migrations.RunPython(_criar, _remover),
    ]
