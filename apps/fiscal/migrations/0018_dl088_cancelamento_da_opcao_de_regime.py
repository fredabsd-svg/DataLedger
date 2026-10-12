# DL-088 (correção da auditoria rodada 1, achado A1): a opção de regime de IBS/CBS do semestre
# ganha o CANCELAMENTO, que a Res. CGSN 194/2026 prevê. Os três campos novos são anuláveis (a opção
# ativa os tem vazios) e a unicidade `opcao_regime_ibs_cbs_unica_por_semestre` vira PARCIAL em
# `cancelada_em__isnull=True`: duas opções ATIVAS do mesmo (empresa, ano, semestre) continuam
# impossíveis, e a opção CANCELADA libera o semestre para novo registro. Nada de dado existente é
# tocado.
#
# Reversão (`migrate fiscal 0017`): RECUSA, sem alterar nada, enquanto houver dado do contador —
# opção registrada (ativa ou cancelada) ou dado de IPI mantido gravado. A checagem é a ÚLTIMA
# operação da lista, então na reversão roda PRIMEIRO, mesmo padrão das guardas das migrações 0015,
# 0016 e 0017. A guarda é ampliada como a da 0016 (que contou as cinco classes da DL-084): as duas
# migrações da DL-088 se revertem juntas em `migrate fiscal 0016`, cada migração tem a sua própria
# transação, e sem contar também as classes da 0017 a 0018 sairia (com os campos de cancelamento)
# ANTES de a guarda da 0017 ver a opção gravada — "sem alterar nada" seria mentira, e a opção
# cancelada voltaria a valer como ativa. A guarda da 0017 continua, como contra-seguro.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _recusar_reversao_com_dados_do_contador(apps, schema_editor):
    """Guarda da reversão da 0018, que protege também a reversão conjunta com a 0017.

    Três classes de dado do contador: a opção de regime de IBS/CBS registrada (a reversão apagaria
    os campos de cancelamento e restauraria a unicidade total), o cancelamento em si (quem, quando e
    por quê — a reversão o apagaria e a opção cancelada voltaria a valer) e o IPI mantido (Zona
    Franca), que a reversão conjunta com a 0017 apagaria junto com as tabelas. Com qualquer uma
    gravada, a reversão é recusada ANTES de qualquer campo ou tabela sair — "sem alterar nada" é o
    que a operação garante.
    """
    pendencias = []
    opcoes = apps.get_model("fiscal", "OpcaoRegimeIbsCbsSimples").objects.count()
    if opcoes:
        canceladas = (
            apps.get_model("fiscal", "OpcaoRegimeIbsCbsSimples")
            .objects.exclude(cancelada_em=None)
            .count()
        )
        pendencias.append(
            f"{opcoes} opção(ões) de regime de IBS/CBS registrada(s), {canceladas} cancelada(s)"
        )
    ipi = apps.get_model("fiscal", "IpiMantidoZfmEmpresa").objects.count()
    if ipi:
        pendencias.append(f"{ipi} dado(s) de IPI mantido (Zona Franca) gravado(s)")
    if pendencias:
        raise RuntimeError(
            "Reversão da DL-088 recusada, sem alterar nada: "
            + "; ".join(pendencias)
            + ". São dados do contador: registre-os ou trate-os antes de reverter. Reverter "
            "apagaria o cancelamento da opção do semestre (que decide se CBS e IBS entram no DAS) "
            "e faria a opção cancelada voltar a valer como ativa."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        ("fiscal", "0017_dl088_opcao_regime_ibs_cbs_e_ipi_mantido"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="opcaoregimeibscbssimples",
            name="opcao_regime_ibs_cbs_unica_por_semestre",
        ),
        migrations.AddField(
            model_name="opcaoregimeibscbssimples",
            name="cancelada_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelada em"),
        ),
        migrations.AddField(
            model_name="opcaoregimeibscbssimples",
            name="cancelada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="cancelada por",
            ),
        ),
        migrations.AddField(
            model_name="opcaoregimeibscbssimples",
            name="motivo_cancelamento",
            field=models.TextField(blank=True, null=True, verbose_name="motivo do cancelamento"),
        ),
        migrations.AddConstraint(
            model_name="opcaoregimeibscbssimples",
            constraint=models.UniqueConstraint(
                condition=models.Q(("cancelada_em__isnull", True)),
                fields=("empresa", "ano", "semestre"),
                name="opcao_regime_ibs_cbs_unica_por_semestre",
            ),
        ),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de qualquer campo ou tabela sair.
        migrations.RunPython(
            migrations.RunPython.noop, _recusar_reversao_com_dados_do_contador
        ),
    ]
