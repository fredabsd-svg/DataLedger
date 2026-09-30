# DL-052, rodada 1 de auditoria, achado D1 — `ItemLancamento.tipo` só pode ser
# `debito` ou `credito`, no BANCO.
#
# Por quê: o gatilho de partidas dobradas (0013) soma `valor` só dos tipos
# `'debito'` e `'credito'`. Um item com tipo fora deles (`"lixo"`, `"DEBITO"`)
# passava por todos os gatilhos e desconciliava Razão e Balancete (medido pelo
# auditor: 5.000,00 de diferença). Corrige-se em migração NOVA, sem editar a
# 0013 já aplicada.
#
# Pré-conferência (todos os bancos): se já houver item com tipo inválido, a
# migração FALHA ALTO nomeando os lotes e NÃO corrige dado — mesma política da
# 0013. Reversão: remove a constraint, sem perda.

from django.db import migrations, models

_LIMITE_DE_LOTES_NA_MENSAGEM = 20


def _recusar_item_com_tipo_invalido(apps, schema_editor):
    Item = apps.get_model("contabilidade", "ItemLancamento")
    lotes = sorted(
        set(
            Item.objects.using(schema_editor.connection.alias)
            .exclude(tipo__in=["debito", "credito"])
            .values_list("lancamento_id", flat=True)
        )
    )
    if lotes:
        raise RuntimeError(
            "DL-052: a migração 0015 não pode ser aplicada porque o banco já contém "
            "item de lançamento com tipo diferente de 'debito'/'credito' (nenhum dado "
            f"foi alterado). {len(lotes)} lote(s): {lotes[:_LIMITE_DE_LOTES_NA_MENSAGEM]} "
            "(números são o id do lançamento, o 'lote'). Corrija por estorno/ajuste "
            "rastreável e repita."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0014_dl052_autoria_protegida"),
    ]

    operations = [
        migrations.RunPython(_recusar_item_com_tipo_invalido, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="itemlancamento",
            constraint=models.CheckConstraint(
                condition=models.Q(("tipo__in", ["debito", "credito"])),
                name="ck_itemlancamento_tipo_valido",
            ),
        ),
    ]
