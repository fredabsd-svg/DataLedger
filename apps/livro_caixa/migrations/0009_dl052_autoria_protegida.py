# RC-144 / DL-052 (decisão do Fred, 30/09/2026): usuário se desativa, não se apaga.
# `LancamentoCaixa.criado_por` e `DependentesCarneLeaoCliente.criado_por` passam de SET_NULL para PROTECT.
# `on_delete` é comportamento do ORM: nenhuma SQL é emitida; reversível sem perda.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("livro_caixa", "0008_dl046_fatia3_campos_arquivo_carne_leao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="dependentescarneleaocliente",
            name="criado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="lancamentocaixa",
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
