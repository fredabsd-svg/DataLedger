# DL-082 (frente A), migração ADITIVA e reversível: marca de monofásico por item (HI-128) e segmento
# CONFIRMADO da devolução de venda (HI-129), ambos em `fiscal_naturezaitemnfe`.
#
# - `monofasico`: booleano, padrão falso. Sem marca o item é normal (lado conservador).
# - `segmento_devolucao`: texto vazio = sem confirmação (o pré-DAS do mês recusa). Um CHECK no banco
#   aceita só os valores do catálogo (`SegmentoDevolucao`), como a DL-081 faz com a natureza.
#
# Não há gatilho novo: `fiscal_natureza_item_nfe_so_em_rascunho` (DL-081, migração 0011) já recusa
# INSERT, UPDATE e DELETE em QUALQUER coluna de `fiscal_naturezaitemnfe` quando a escrituração-pai
# não é rascunho. A marca e o segmento ficam imutáveis depois da efetivação pelo mesmo gatilho.
#
# Reversão: `migrate fiscal 0013` remove o CHECK e as duas colunas. Nenhum dado de outra tabela
# muda.

from django.db import migrations, models

_SEGMENTOS_DEVOLUCAO = (
    "revenda",
    "producao",
    "revenda_st",
    "producao_st",
    "revenda_monofasico",
    "producao_monofasico",
    "revenda_st_monofasico",
    "producao_st_monofasico",
    "revenda_exportacao",
    "producao_exportacao",
)
_LISTA_SEGMENTOS = ", ".join(f"'{s}'" for s in _SEGMENTOS_DEVOLUCAO)

_SQL_CHECK = (
    "ALTER TABLE fiscal_naturezaitemnfe ADD CONSTRAINT natureza_item_nfe_segmento_devolucao_valido "
    f"CHECK (segmento_devolucao IN ('', {_LISTA_SEGMENTOS}))"
)
# Antes de qualquer ALTER TABLE, as checagens adiadas (FK de Django são DEFERRABLE) são executadas.
# Sem isto, numa transação com linhas novas em `fiscal_naturezaitemnfe`, o PostgreSQL recusa o ALTER
# com "pending trigger events". As checagens que ficam pendentes já deveriam valer: nada muda nos
# dados.
_SQL_DESCARREGAR_CHECAGENS = "SET CONSTRAINTS ALL IMMEDIATE"
_SQL_DESFAZER_CHECK = (
    "ALTER TABLE fiscal_naturezaitemnfe "
    "DROP CONSTRAINT IF EXISTS natureza_item_nfe_segmento_devolucao_valido"
)


def _so_postgresql(schema_editor) -> bool:
    # O CHECK e o descarregamento de checagens são SQL de PostgreSQL. Em outro banco (o teste de
    # migração em SQLite roda a cadeia inteira), a migração só cria as colunas.
    return schema_editor.connection.vendor == "postgresql"


def _descarregar_checagens(apps, schema_editor):
    if _so_postgresql(schema_editor):
        schema_editor.execute(_SQL_DESCARREGAR_CHECAGENS)


def _aplicar_check(apps, schema_editor):
    if _so_postgresql(schema_editor):
        schema_editor.execute(_SQL_CHECK)


def _desfazer_check(apps, schema_editor):
    if _so_postgresql(schema_editor):
        schema_editor.execute(_SQL_DESFAZER_CHECK)


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0013_dl085_lote_escrituracao_nfe"),
    ]

    operations = [
        migrations.RunPython(_descarregar_checagens, migrations.RunPython.noop),
        migrations.AddField(
            model_name="naturezaitemnfe",
            name="monofasico",
            field=models.BooleanField(
                default=False,
                verbose_name="monofásico de PIS e Cofins (marca do contador)",
            ),
        ),
        migrations.AddField(
            model_name="naturezaitemnfe",
            name="segmento_devolucao",
            field=models.CharField(
                blank=True,
                choices=[
                    ("revenda", "Devolução de revenda, Anexo I, sem ST nem monofásico"),
                    (
                        "producao",
                        "Devolução de produção própria, Anexo II, sem ST nem monofásico",
                    ),
                    ("revenda_st", "Devolução de revenda com ST substituído, Anexo I"),
                    (
                        "producao_st",
                        "Devolução de produção com ST substituído, Anexo II",
                    ),
                    ("revenda_monofasico", "Devolução de revenda monofásica, Anexo I"),
                    (
                        "producao_monofasico",
                        "Devolução de produção monofásica, Anexo II",
                    ),
                    (
                        "revenda_st_monofasico",
                        "Devolução de revenda com ST e monofásico, Anexo I",
                    ),
                    (
                        "producao_st_monofasico",
                        "Devolução de produção com ST e monofásico, Anexo II",
                    ),
                    ("revenda_exportacao", "Devolução de revenda exportada, Anexo I"),
                    (
                        "producao_exportacao",
                        "Devolução de produção exportada, Anexo II",
                    ),
                ],
                default="",
                max_length=24,
                verbose_name="segmento da devolução (confirmado)",
            ),
        ),
        migrations.RunPython(_aplicar_check, _desfazer_check),
        # Na reversão, este é o PRIMEIRO passo (operações revertem na ordem inversa).
        migrations.RunPython(migrations.RunPython.noop, _descarregar_checagens),
    ]
