# Hand-written para a F1 do DL-016 — escrita à mão porque o ambiente de
# desenvolvimento deste agente não tem Python 3.12+ nem Django 6.1.1
# disponíveis (o sandbox roda Python 3.11; `makemigrations` não roda). O
# conteúdo desta migração foi produzido revisando o estado final dos modelos
# `Competencia` (apps/contabilidade/models.py) e o campo `competencia` em
# `LancamentoContabil` (mesmo arquivo), e espelhando o estilo das migrações
# 0001_initial, 0002 e 0003 (mesmo app).
#
# Esta migração deve ser REGENERADA com `python manage.py makemigrations`
# no primeiro `migrate` em ambiente com Python 3.12+ e Django 6.1.1, e o
# diff comparado item a item com o escrito abaixo. Se `makemigrations`
# não produzir mudanças, este arquivo está correto. Se produzir, vale
# revisar e atualizar — não dar `makemigrations --merge` cegamente.
#
# Em particular, o Django 6.1 tende a ordenar operações em uma sequência
# específica (criar a tabela nova ANTES de adicionar a FK para ela) e a
# representar `CheckConstraint` e `UniqueConstraint` em blocos separados
# dentro de `CreateModel`. O que está abaixo segue essa convenção.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidade", "0003_alter_lancamentocontabil_data"),
        ("empresas", "0001_initial"),
    ]

    operations = [
        # 1) Cria `Competencia`. `LancamentoContabil.competencia` (passo 2)
        # depende desta tabela existir, por isso vem primeiro.
        migrations.CreateModel(
            name="Competencia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("ano", models.IntegerField(verbose_name="ano")),
                ("mes", models.IntegerField(verbose_name="mês")),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("aberta", "Aberta"),
                            ("em_encerramento", "Em encerramento"),
                            ("encerrada", "Encerrada"),
                        ],
                        default="aberta",
                        max_length=20,
                        verbose_name="estado",
                    ),
                ),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="competencias",
                        to="empresas.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "competência",
                "verbose_name_plural": "competências",
                "ordering": ["-ano", "-mes"],
            },
        ),
        # 2) `UniqueConstraint` do `Competencia.Meta` — uma linha por
        # (empresa, ano, mês). Vai no final do CreateModel em geral; o
        # Django 6.1 às vezes separa do bloco de fields.
        migrations.AddConstraint(
            model_name="competencia",
            constraint=models.UniqueConstraint(
                fields=("empresa", "ano", "mes"),
                name="competencia_unica_por_empresa_ano_mes",
            ),
        ),
        migrations.AddConstraint(
            model_name="competencia",
            constraint=models.CheckConstraint(
                condition=models.Q(mes__gte=1) & models.Q(mes__lte=12),
                name="competencia_mes_entre_1_e_12",
            ),
        ),
        migrations.AddConstraint(
            model_name="competencia",
            constraint=models.CheckConstraint(
                condition=models.Q(ano__gte=1970) & models.Q(ano__lte=2999),
                name="competencia_ano_entre_1970_e_2999",
            ),
        ),
        # 3) Adiciona o campo `competencia` (FK nullable) em
        # `LancamentoContabil`. Nullable porque D1 = "deixar nulo até F5"
        # (decisão do Fred na rodada 7 da DL-016).
        migrations.AddField(
            model_name="lancamentocontabil",
            name="competencia",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lancamentos",
                to="contabilidade.competencia",
                verbose_name="competência",
            ),
        ),
    ]
