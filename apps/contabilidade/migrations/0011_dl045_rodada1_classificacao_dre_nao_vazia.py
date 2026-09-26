# DL-045, correção da rodada 1 de auditoria — achado A4.
#
# `classificacao_dre=""` (string vazia, diferente de `NULL`) era um estado
# alcançável pela API antes desta correção: o `ChoiceField` que o DRF gera
# por padrão para um campo com `blank=True` aceitava `""` e gravava; a
# guarda de transição de `Conta.clean()` tratava `""` como "já classificada"
# (`is not None`), o que travava a conta para sempre — a primeira
# classificação REAL, depois do `""`, era recusada como reclassificação, e
# o único conserto possível era SQL direto.
#
# Esta migração faz DUAS coisas, NESTA ordem (RunPython antes do
# AddConstraint, de propósito — a constraint reprovaria a normalização se
# viesse primeiro e algum registro legado já tivesse `""` gravado):
#
# 1. Normaliza qualquer `classificacao_dre=""` já gravado para `NULL` — o
#    código (serializer e `Conta.clean()`) já faz essa normalização na
#    ENTRADA desde esta mesma correção; esta migração cobre o que já
#    estivesse gravado ANTES dela.
# 2. Acrescenta a `CheckConstraint` (`ck_conta_classificacao_dre_nao_vazia`)
#    que impede `""` de voltar a ser gravado por qualquer caminho que não
#    passe pelo código (ORM direto, importação, migração de dado futura).
from django.db import migrations, models


def normalizar_classificacao_dre_vazia(apps, schema_editor):
    Conta = apps.get_model("contabilidade", "Conta")
    Conta.objects.filter(classificacao_dre="").update(classificacao_dre=None)


def reverter_normalizacao(apps, schema_editor):
    # NO-OP de propósito: `""` e `NULL` colapsam no mesmo significado ("sem
    # classificação") — não há dado a "restaurar". Reverter esta migração
    # remove a `CheckConstraint` (abaixo); não desfaz a normalização.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0010_dl045_conta_classificacao_dre"),
    ]

    operations = [
        migrations.RunPython(normalizar_classificacao_dre_vazia, reverter_normalizacao),
        migrations.AddConstraint(
            model_name="conta",
            constraint=models.CheckConstraint(
                condition=models.Q(("classificacao_dre", ""), _negated=True),
                name="ck_conta_classificacao_dre_nao_vazia",
            ),
        ),
    ]
