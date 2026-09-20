# DL-016, fatia 1 — fechamento, reabertura e entrega de competência.
#
# Gerada por `python manage.py makemigrations contabilidade` (Django 6.1.1,
# Python 3.14) e revisada linha a linha: SÓ quatro `AddField`, todos
# `null=True`/`blank=True`, sem `RunPython`, sem `AlterField` e sem tocar
# nenhuma linha existente — nenhuma competência gravada antes desta migração
# muda de valor (critério 11 do plano). Aplicada e verificada em banco vazio
# e em banco com dados sintéticos (ver o relatório de entrega da etapa).
#
# ⚠️ A primeira geração deste `makemigrations` também propôs
# `RemoveConstraint(ck_lancamentocontabil_empresa_not_null)` — um achado
# PRÉ-EXISTENTE, sem relação com esta trava de competência, e NÃO CORRIGIDO
# nesta migração de propósito: aquela `CheckConstraint` foi adicionada ao
# BANCO pela migração 0005 (hand-written, `AddConstraint` avulso) mas nunca
# tinha sido declarada em `LancamentoContabil.Meta.constraints` — a
# divergência já reprova `manage.py makemigrations --check` em HEAD limpo,
# ANTES de qualquer edição desta etapa (medido). A operação
# `RemoveConstraint` foi DESCARTADA manualmente desta migração — nunca
# aplicada — porque dropar aquela constraint em silêncio removeria uma
# defesa de banco real (DE-051). Corrigir a DECLARAÇÃO exigiria também
# registrar a constraint em `apps/core/restricoes.py`, arquivo fora do
# escopo desta etapa (`apps/contabilidade/**`) — achado registrado em
# `docs/projeto/backlog.md` para o arquiteto-senior decidir quem corrige.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0005_check_lancamento_empresa_not_null"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="competencia",
            name="entregue_em",
            field=models.DateTimeField(
                blank=True,
                help_text="Data/hora em que o documento desta competência (balancete, ECD etc.) foi entregue ao cliente. Uma vez preenchido, a reabertura da competência é sempre recusada (RC-101) — o ajuste passa a ser feito no mês aberto.",
                null=True,
                verbose_name="entregue em",
            ),
        ),
        migrations.AddField(
            model_name="competencia",
            name="entregue_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuário que marcou a competência como entregue.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="entregue por",
            ),
        ),
        migrations.AddField(
            model_name="competencia",
            name="fechada_em",
            field=models.DateTimeField(
                blank=True,
                help_text="Preenchido quando o estado passa a 'encerrada'. Limpo se a competência for reaberta.",
                null=True,
                verbose_name="fechada em",
            ),
        ),
        migrations.AddField(
            model_name="competencia",
            name="fechada_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuário que fechou a competência (RC do DL-016, critério 3 da fatia 1).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="fechada por",
            ),
        ),
    ]
