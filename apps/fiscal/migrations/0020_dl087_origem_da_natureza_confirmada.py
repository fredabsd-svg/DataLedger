# DL-087, item 6: de onde veio cada natureza CONFIRMADA (regra, produto, padrão da empresa ou
# manual).
#
# Tabela NOVA e aditiva, 1:1 com `NaturezaItemNFe` (FK + UniqueConstraint), e não colunas nela: a
# tabela de naturezas tem gatilhos e é lida pelas reversões de outras migrações (DL-082). Linhas
# anteriores à DL-087 não têm origem gravada (sem linha, sem reescrita).
#
# Reversão (`migrate fiscal 0019`): recusa, sem alterar nada, enquanto houver REGRA de classificação
# (a guarda da 0019, reusada aqui e rodada PRIMEIRO). Sem regra, a tabela de origens é descartada:
# ela é procedência do item, não o valor confirmado. Decisão a validar pelo arquiteto: uma reversão
# recusada MAIS ABAIXO (outra migração) já terá descartado a origem; nenhuma regra se perde.

from importlib import import_module

import django.db.models.deletion
from django.db import migrations, models

_guarda_da_0019 = import_module(
    "apps.fiscal.migrations.0019_dl087_regra_de_classificacao_nfe"
)._recusar_reversao_com_regras


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0019_dl087_regra_de_classificacao_nfe"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrigemNaturezaItemNFe",
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
                (
                    "origem",
                    models.CharField(
                        choices=[
                            (
                                "regra",
                                "Regra de classificação do escritório ou da empresa",
                            ),
                            ("produto", "Sugestão embutida do produto"),
                            ("padrao_empresa", "Padrão de combustível da empresa"),
                            (
                                "manual",
                                "Escolha do contador (diferente da sugestão, ou sem sugestão)",
                            ),
                        ],
                        max_length=16,
                        verbose_name="origem da natureza confirmada",
                    ),
                ),
                (
                    "gravada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="gravada em"),
                ),
                (
                    "natureza_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="origem_da_natureza",
                        to="fiscal.naturezaitemnfe",
                        verbose_name="natureza do item",
                    ),
                ),
                (
                    "regra_classificacao",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="itens_confirmados",
                        to="fiscal.regraclassificacaonfe",
                        verbose_name="regra que produziu a natureza",
                    ),
                ),
            ],
            options={
                "verbose_name": "origem da natureza de item de NF-e",
                "verbose_name_plural": "origens das naturezas de itens de NF-e",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("natureza_item",), name="origem_natureza_item_unica"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("origem", "regra"),
                                ("regra_classificacao__isnull", False),
                            ),
                            models.Q(
                                models.Q(("origem", "regra"), _negated=True),
                                ("regra_classificacao__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="origem_natureza_item_regra_coerente",
                    ),
                ],
            },
        ),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de a tabela sair.
        migrations.RunPython(migrations.RunPython.noop, _guarda_da_0019),
    ]
