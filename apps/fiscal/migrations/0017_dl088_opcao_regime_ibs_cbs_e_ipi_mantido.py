# DL-088 (frente A2): o dado da empresa que libera a virada de 2027 — a opção de regime de IBS/CBS
# por semestre (Res. CGSN 190/2026, art. 22-A; HI-148) e o IPI mantido da Zona Franca (art. 25,
# § 1º, II; HI-152). Duas tabelas novas, aditivas: nada de dado existente é tocado.
#
# Reversão (`migrate fiscal 0016`): RECUSA, sem alterar nada, enquanto houver opção registrada ou
# dado de IPI mantido gravado — são dados do contador, e a reversão apagaria a única memória da
# escolha do semestre (que decide se CBS e IBS entram no DAS) e da Zona Franca (que decide o Anexo
# II de 2027). Sem esses dados, a reversão só tira as duas tabelas e volta a valer como antes: o
# pré-DAS de 2027 volta a recusar por falta da opção. A checagem é a ÚLTIMA operação da lista,
# então na reversão roda PRIMEIRO, mesmo padrão das guardas das migrações 0015 e 0016.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _recusar_reversao_com_dado_da_virada(apps, schema_editor):
    """Guarda da reversão da 0017 (DL-088, frente A2).

    Conta as DUAS classes de dado da virada de 2027: a opção de regime de IBS/CBS do semestre e o
    IPI mantido (Zona Franca). Com qualquer uma gravada, a reversão é recusada ANTES de qualquer
    tabela sair — "sem alterar nada" é o que a operação garante.
    """
    pendencias = []
    opcoes = apps.get_model("fiscal", "OpcaoRegimeIbsCbsSimples").objects.count()
    if opcoes:
        pendencias.append(f"{opcoes} opção(ões) de regime de IBS/CBS registrada(s)")
    ipi = apps.get_model("fiscal", "IpiMantidoZfmEmpresa").objects.count()
    if ipi:
        pendencias.append(f"{ipi} dado(s) de IPI mantido (Zona Franca) gravado(s)")
    if pendencias:
        raise RuntimeError(
            "Reversão da DL-088 recusada, sem alterar nada: "
            + "; ".join(pendencias)
            + ". São dados do contador: registre-os ou trate-os antes de reverter. Reverter "
            "apagaria a opção do semestre (que decide se CBS e IBS entram no DAS) e o dado de IPI "
            "mantido (que decide o Anexo II de 2027)."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        ("fiscal", "0016_dl084_escopo_do_escritorio_feriados"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IpiMantidoZfmEmpresa",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "situacao",
                    models.CharField(
                        choices=[
                            ("ipi_mantido", "IPI mantido (indústria da Zona Franca)"),
                            ("sem_ipi_mantido", "Sem IPI mantido (produção própria fora da ZFM)"),
                        ],
                        max_length=20,
                        verbose_name="situação do IPI mantido",
                    ),
                ),
                (
                    "fonte",
                    models.TextField(
                        help_text=(
                            "Onde o dado foi confirmado (declaração do cliente, ato de "
                            "incentivo, etc.)."
                        ),
                        verbose_name="fonte ou justificativa",
                    ),
                ),
                (
                    "registrada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="registrada em"),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ipi_mantido_zfm",
                        to="empresas.empresa",
                        verbose_name="empresa",
                    ),
                ),
                (
                    "registrada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="registrada por",
                    ),
                ),
            ],
            options={
                "verbose_name": "IPI mantido (Zona Franca) da empresa",
                "verbose_name_plural": "IPI mantido (Zona Franca) das empresas",
                "ordering": ["empresa_id"],
                "constraints": [
                    models.UniqueConstraint(fields=("empresa",), name="ipi_mantido_unico_por_empresa")
                ],
            },
        ),
        migrations.CreateModel(
            name="OpcaoRegimeIbsCbsSimples",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("ano", models.PositiveSmallIntegerField(verbose_name="ano")),
                ("semestre", models.PositiveSmallIntegerField(verbose_name="semestre")),
                (
                    "regime",
                    models.CharField(
                        choices=[
                            ("regime_unico", "Regime único (CBS e IBS no DAS)"),
                            ("regime_regular", "Regime regular de IBS/CBS (art. 22-A)"),
                        ],
                        max_length=20,
                        verbose_name="regime escolhido",
                    ),
                ),
                (
                    "registrada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="registrada em"),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="opcoes_regime_ibs_cbs_simples",
                        to="empresas.empresa",
                        verbose_name="empresa",
                    ),
                ),
                (
                    "registrada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="registrada por",
                    ),
                ),
            ],
            options={
                "verbose_name": "opção de regime de IBS/CBS (Simples)",
                "verbose_name_plural": "opções de regime de IBS/CBS (Simples)",
                "ordering": ["empresa_id", "ano", "semestre"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("empresa", "ano", "semestre"),
                        name="opcao_regime_ibs_cbs_unica_por_semestre",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("ano__gte", 2027)),
                        name="opcao_regime_ibs_cbs_so_desde_2027",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("semestre__gte", 1), ("semestre__lte", 2)),
                        name="opcao_regime_ibs_cbs_semestre_valido",
                    ),
                ],
            },
        ),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de qualquer tabela sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_dado_da_virada),
    ]
