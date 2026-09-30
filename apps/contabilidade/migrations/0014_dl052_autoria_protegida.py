# DL-052 — decisão do Fred (30/09/2026): usuário se DESATIVA, não se apaga.
# A autoria de lançamento efetivado (`criado_por`) e do fechamento/entrega de
# competência (`fechada_por`, `entregue_por`) passa de SET_NULL para PROTECT:
# apagar um usuário que escriturou é recusado (ProtectedError) em vez de
# apagar a autoria — e o UPDATE que o SET_NULL emitiria em lançamento seria
# recusado de qualquer forma pelo gatilho de imutabilidade da 0013.
#
# `on_delete` é comportamento do ORM, não de esquema: esta migração não emite
# SQL (nenhuma coluna, constraint ou índice muda), e é reversível sem perda.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0013_dl052_invariantes_do_livro_no_banco"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="competencia",
            name="entregue_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuário que marcou a competência como entregue.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="entregue por",
            ),
        ),
        migrations.AlterField(
            model_name="competencia",
            name="fechada_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuário que fechou a competência (RC do DL-016, critério 3 da fatia 1).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="fechada por",
            ),
        ),
        migrations.AlterField(
            model_name="lancamentocontabil",
            name="criado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
