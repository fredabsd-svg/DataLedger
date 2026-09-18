# DL-016-F6 — CHECK constraint garantindo LancamentoContabil.empresa_id NOT NULL
# no nível do banco, como rede de segurança contra INSERT direto via shell-admin
# que burle o ORM (cenário que motivou a remoção do branch defensivo de "órfão"
# em DL-016-F5 — ver DE-051).
#
# Hand-written seguindo o mesmo padrão da migration 0004 (sandbox Python 3.11
# sem Django 6.1.1, `makemigrations` não roda). Regenerar com
# `python manage.py makemigrations` no primeiro `migrate` em ambiente Python
# 3.12+ e comparar diff item a item.
#
# Decisão de escopo: a coluna `empresa_id` já é NOT NULL no schema atual
# porque `ForeignKey(Empresa, ...)` sem `null=True` gera coluna NOT NULL
# (default do Django). O CHECK constraint é defesa em profundidade —
# garante a invariante explicitamente e protege contra:
#   - INSERT direto via psql/shell-admin que burle o ORM (DE-051 A1)
#   - ALTER TABLE manual futuro que tente DROP NOT NULL
#   - Bypass via raw SQL com constraint adiado (não se aplica a CHECK em PG
#     sem DEFERRABLE, mas a documentação fica explícita)
#
# Por que AddConstraint separado (e não dentro de Meta.constraints do model):
# ALTER table-level constraint não exige recriar a tabela, e é a forma
# idiomática de adicionar CHECK pós-criação no Django 5/6.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0004_competencia_e_competencia_no_lancamento"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="lancamentocontabil",
            constraint=models.CheckConstraint(
                condition=models.Q(empresa_id__isnull=False),
                name="ck_lancamentocontabil_empresa_not_null",
            ),
        ),
    ]
