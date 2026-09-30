# RC-144 / DL-052 (decisão do Fred, 30/09/2026): usuário se desativa, não se apaga.
# `RegistroAuditoria.usuario` passa de SET_NULL para PROTECT.
# `on_delete` é comportamento do ORM: nenhuma SQL é emitida; reversível sem perda.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0002_alter_registroauditoria_escritorio_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="registroauditoria",
            name="usuario",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="registros_auditoria",
                to=settings.AUTH_USER_MODEL,
                verbose_name="usuário",
            ),
        ),
    ]
