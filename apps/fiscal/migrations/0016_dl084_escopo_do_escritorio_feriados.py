# DL-084 (correção da auditoria rodada 1, DE-106): o feriado local ganha o escopo do escritório.
#
# A carga do produto (lei, data da leitura e fonte bancária) é a BASE e continua global e somente
# leitura: `escritorio` vazio. As linhas e exceções que as telas gravam nascem escopadas ao
# escritório que agiu (`escritorio` preenchido) e afetam só as empresas dele. A empresa herda a base
# da praça mais as linhas do escritório dela; no mesmo dia a linha do escritório substitui a da base,
# e no mesmo ano a exceção do escritório substitui a da base
# (`apps.fiscal.presumido_calculo.linhas_efetivas`).
#
# Migração ADITIVA e reversível: só acrescenta as duas colunas anuláveis, sem tocar em dado
# existente. Reversão (`migrate fiscal 0015`, ou `migrate fiscal 0014` que também reverte a 0015):
# RECUSA, sem alterar nada, enquanto houver dado do contador — competência informada, parâmetro
# gravado, encerramento de medida, feriado ou exceção do escritório. Sem esses dados, a reversão só
# remove as colunas: o que sobra é a base, e volta a valer como antes. A checagem é a ÚLTIMA
# operação da lista, então na reversão roda PRIMEIRO, mesmo padrão da guarda da 0015.

import django.db.models.deletion
from django.db import migrations, models


def _recusar_reversao_com_dados_do_contador(apps, schema_editor):
    """Guarda da reversão da 0016, que é também a da DL-084 inteira.

    As duas migrações da DL-084 se revertem juntas em `migrate fiscal 0014`, e cada migração tem a
    sua própria transação: sem esta guarda ampliada, a 0016 sairia (com as colunas do escopo) ANTES
    de a guarda da 0015 ver o parâmetro gravado — e "sem alterar nada" seria mentira. Por isso aqui
    se contam as CINCO classes de dado do contador; a guarda da 0015 continua, com as mesmas
    classes, como contra-seguro.
    """
    pendencias = []
    competencias = (
        apps.get_model("fiscal", "ReceitaTrimestralPresumido")
        .objects.exclude(competencia="")
        .count()
    )
    if competencias:
        pendencias.append(f"{competencias} receita(s) com competência ou parcela informada")
    parametros = apps.get_model("fiscal", "ParametrosPresumidoEmpresa").objects.count()
    if parametros:
        pendencias.append(f"{parametros} empresa(s) com parâmetros do presumido gravados")
    encerramentos = apps.get_model("fiscal", "EncerramentoMedidaJudicialLC224").objects.count()
    if encerramentos:
        pendencias.append(f"{encerramentos} medida(s) encerrada(s)")
    feriados = apps.get_model("fiscal", "FeriadoLocal").objects.exclude(escritorio=None).count()
    if feriados:
        pendencias.append(f"{feriados} feriado(s) local(is) do escritório")
    excecoes = (
        apps.get_model("fiscal", "ExcecaoFeriadoLocal").objects.exclude(escritorio=None).count()
    )
    if excecoes:
        pendencias.append(f"{excecoes} exceção(ões) de feriado do escritório")
    if pendencias:
        raise RuntimeError(
            "Reversão da DL-084 recusada, sem alterar nada: "
            + "; ".join(pendencias)
            + ". São dados do contador: estorne-os ou trate-os antes de reverter. Reverter faria a "
            "linha do escritório virar linha da base e valer para todos os escritórios."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0015_dl084_rotina_do_presumido"),
        ("tenancy", "0003_escritorio_endereco_no_timbre_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="feriadolocal",
            name="escritorio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="feriados_locais",
                to="tenancy.escritorio",
                verbose_name="escritório (vazio = linha da base)",
            ),
        ),
        migrations.AddField(
            model_name="excecaoferiadolocal",
            name="escritorio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="excecoes_feriado_local",
                to="tenancy.escritorio",
                verbose_name="escritório (vazio = linha da base)",
            ),
        ),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de qualquer coluna sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_dados_do_contador),
    ]
