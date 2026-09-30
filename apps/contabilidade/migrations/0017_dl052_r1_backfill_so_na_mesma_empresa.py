# DL-052, rodada 1 de auditoria, achado D3 — a exceção do backfill
# (`competencia_id` NULL -> valor, isolada) só vale se a competência nova for da
# MESMA empresa do lançamento. Antes, o banco aceitava a competência de outra
# empresa (o lançamento ficaria preso ao fechamento de outro cliente e, depois
# disso, "selado" pelo gatilho). Só a função muda (CREATE OR REPLACE); o
# gatilho da 0013 continua o mesmo. Só PostgreSQL. A reversão restaura o corpo
# da função como estava na 0013.

from django.db import migrations

_NOVA_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_recusar_alteracao_do_livro()
RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_lancamentocontabil' THEN
        -- ÚNICA exceção: o backfill da competência (comando de gerência
        -- `backfill_lancamento_competencia`, DL-016 F5) preenche
        -- `competencia_id` de NULL para um valor e NÃO toca em mais nada.
        -- NOT NULL -> outro valor continua recusado.
        IF TG_OP = 'UPDATE'
           AND OLD.competencia_id IS NULL
           AND NEW.competencia_id IS NOT NULL
           AND (to_jsonb(NEW) - 'competencia_id') = (to_jsonb(OLD) - 'competencia_id')
           -- DL-052 rodada 1 (D3): a competência nova tem de ser da MESMA
           -- empresa do lançamento; o backfill filtra por empresa, e agora o
           -- banco também exige (uma competência de outra empresa prenderia
           -- o lançamento ao fechamento de outro cliente).
           AND EXISTS (
               SELECT 1 FROM contabilidade_competencia c
                WHERE c.id = NEW.competencia_id AND c.empresa_id = OLD.empresa_id
           )
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'Lançamento contábil efetivado não pode ser alterado nem excluído (% do lançamento %); '
            'registre um estorno.', TG_OP, OLD.id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_contabil_imutavel';
    END IF;

    RAISE EXCEPTION
        'Item de lançamento efetivado não pode ser alterado nem excluído (% do item %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'item_lancamento_imutavel';
END;
$$ LANGUAGE plpgsql;
"""

_ANTIGA_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_recusar_alteracao_do_livro()
RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_lancamentocontabil' THEN
        -- ÚNICA exceção: o backfill da competência (comando de gerência
        -- `backfill_lancamento_competencia`, DL-016 F5) preenche
        -- `competencia_id` de NULL para um valor e NÃO toca em mais nada.
        -- NOT NULL -> outro valor continua recusado.
        IF TG_OP = 'UPDATE'
           AND OLD.competencia_id IS NULL
           AND NEW.competencia_id IS NOT NULL
           AND (to_jsonb(NEW) - 'competencia_id') = (to_jsonb(OLD) - 'competencia_id')
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'Lançamento contábil efetivado não pode ser alterado nem excluído (% do lançamento %); '
            'registre um estorno.', TG_OP, OLD.id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_contabil_imutavel';
    END IF;

    RAISE EXCEPTION
        'Item de lançamento efetivado não pode ser alterado nem excluído (% do item %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'item_lancamento_imutavel';
END;
$$ LANGUAGE plpgsql;
"""


def _aplicar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_NOVA_SQL, params=None)


def _reverter(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ANTIGA_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0016_dl052_r1_item_so_em_lancamento_da_transacao"),
    ]

    operations = [
        migrations.RunPython(_aplicar, _reverter),
    ]
