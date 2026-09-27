# DL-046, fatia 2 — correção da reconferência (DE-092, item 3/R-M2): a
# mensagem de duplicidade de competência dos dependentes ("use a
# retificação (PATCH)") citava jargão de HTTP que o usuário não reconhece.
# Só o TEXTO da `violation_error_message` muda — a mesma correção do
# `apps/core/restricoes.py` (caminho residual de corrida) e do
# `Meta.constraints` (caminho sequencial, `full_clean()`/`validate_unique()`)
# — nenhuma mudança de esquema, por isso `AlterConstraint` (Django 5+), não
# `RemoveConstraint`/`AddConstraint`.
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        # Mesmo motivo/mesma correção de `0001_inicial.py`/
        # `0005_correcao_rodada1_percentual_dia1_mensagens.py`: esta
        # migração não depende de nenhum campo específico da migração mais
        # recente de `empresas` no momento da geração.
        ("empresas", "0001_initial"),
        ("livro_caixa", "0006_correcao_rodada1_tabela_jan_abr_2025"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterConstraint(
            model_name="dependentescarneleaocliente",
            name="dependentes_carne_leao_competencia_unica_por_empresa",
            constraint=models.UniqueConstraint(
                fields=("empresa", "competencia_inicio"),
                name="dependentes_carne_leao_competencia_unica_por_empresa",
                violation_error_message=(
                    "Já existe uma quantidade de dependentes registrada para esta "
                    "empresa a partir deste mês — use Retificar para corrigir o "
                    "valor, em vez de um novo registro."
                ),
            ),
        ),
    ]
