# DL-046, fatia 2 — correção da rodada 1 da auditoria (M-5): semeia a
# tabela progressiva mensal vigente de JANEIRO a ABRIL de 2025 — antes
# desta migração, `apurar_carne_leao_mensal`/`apurar_carne_leao_anual`
# recusavam qualquer mês de 2025 anterior a maio (a primeira vigência
# gravada, migração 0004, começava em 2025-05-01), com uma mensagem que
# não deixava claro que a causa era "tabela não semeada" e não "fora do
# escopo" — a auditoria mediu isso como M-5.
#
# Fonte: Perguntas e Respostas IRPF 2026 v1.00 (23/04/2026), pergunta 267:
# "A tabela progressiva mensal para fatos geradores ocorridos no
# ano-calendário de 2025, durante os meses de janeiro a abril, é a
# seguinte: até R$ 2.259,20 — 0%; de R$ 2.259,21 até R$ 2.826,65 — 7,5%,
# parcela a deduzir R$ 169,44; de R$ 2.826,66 até R$ 3.751,05 — 15,0%, R$
# 381,44; de R$ 3.751,06 até R$ 4.664,68 — 22,5%, R$ 662,77; acima de R$
# 4.664,68 — 27,5%, R$ 896,00" — texto bruto conferido pelo
# `desenvolvedor-pleno` em scratchpad/pr_irpf_2026.txt (linhas 7931-7940).
# A mesma pergunta cita como base legal a Lei nº 9.250/1995, art. 4º; a
# Lei nº 11.482/2007, art. 1º (na redação vigente entre 01/2025 e
# 04/2025, ANTERIOR à alteração da Lei nº 15.191/2025, que só passou a
# valer "a partir do mês de maio do ano-calendário de 2025" — RC-131); o
# RIR/2018, art. 121; e a IN RFB nº 1.500/2014, arts. 53 a 57.
#
# Sem vigência de REDUÇÃO antes de 2026-01-01: ausência LEGÍTIMA (a Lei
# 15.270/2025 só produz efeitos "a partir do mês de janeiro do
# ano-calendário de 2026", art. 8º) — `apps.livro_caixa.carne_leao` passa
# a tratar a ausência de vigência de redução para um mês de 2025 como
# "sem redução", não como erro de configuração (DE-091 item 5). Anos
# ANTERIORES a 2025 continuam fora do escopo desta fatia, com mensagem
# clara (nenhuma tabela é semeada antes de 2025-01-01).
#
# Percentual do desconto simplificado: 0,25 (25%), MESMA fonte e vigência
# da tabela de maio/2025 em diante (Lei nº 9.250/1995, art. 4º, § 2º,
# redação da Lei nº 14.663/2023) — não mudou entre janeiro e dezembro de
# 2025.
from decimal import Decimal

from django.db import migrations

FONTE_TABELA_2025_01 = (
    "Perguntas e Respostas IRPF 2026 v1.00 (23/04/2026), pergunta 267: "
    "'tabela progressiva mensal para fatos geradores ocorridos no "
    "ano-calendário de 2025, durante os meses de janeiro a abril'; "
    "Lei nº 9.250/1995, art. 4º; Lei nº 11.482/2007, art. 1º (redação "
    "anterior à alteração da Lei nº 15.191/2025); RIR/2018, art. 121; "
    "IN RFB nº 1.500/2014, arts. 53 a 57."
)

_FAIXAS_TABELA_2025_01 = [
    # (ordem, limite_inferior, limite_superior, aliquota, parcela_a_deduzir)
    (1, Decimal("0.00"), Decimal("2259.20"), Decimal("0.0000"), Decimal("0.00")),
    (2, Decimal("2259.21"), Decimal("2826.65"), Decimal("0.0750"), Decimal("169.44")),
    (3, Decimal("2826.66"), Decimal("3751.05"), Decimal("0.1500"), Decimal("381.44")),
    (4, Decimal("3751.06"), Decimal("4664.68"), Decimal("0.2250"), Decimal("662.77")),
    (5, Decimal("4664.69"), None, Decimal("0.2750"), Decimal("896.00")),
]

PERCENTUAL_DESCONTO_SIMPLIFICADO_2025_01 = Decimal("0.25")


def semear_tabela_jan_abr_2025(apps, schema_editor):
    VigenciaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "VigenciaTabelaProgressivaCarneLeao"
    )
    FaixaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "FaixaTabelaProgressivaCarneLeao"
    )

    vigencia = VigenciaTabelaProgressivaCarneLeao.objects.create(
        vigencia_inicio="2025-01-01",
        fonte=FONTE_TABELA_2025_01,
        percentual_desconto_simplificado=PERCENTUAL_DESCONTO_SIMPLIFICADO_2025_01,
    )
    for ordem, limite_inferior, limite_superior, aliquota, parcela in _FAIXAS_TABELA_2025_01:
        FaixaTabelaProgressivaCarneLeao.objects.create(
            vigencia=vigencia,
            ordem=ordem,
            limite_inferior=limite_inferior,
            limite_superior=limite_superior,
            aliquota=aliquota,
            parcela_a_deduzir=parcela,
        )


def remover_tabela_jan_abr_2025(apps, schema_editor):
    VigenciaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "VigenciaTabelaProgressivaCarneLeao"
    )
    FaixaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "FaixaTabelaProgressivaCarneLeao"
    )
    FaixaTabelaProgressivaCarneLeao.objects.filter(vigencia__vigencia_inicio="2025-01-01").delete()
    VigenciaTabelaProgressivaCarneLeao.objects.filter(vigencia_inicio="2025-01-01").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("livro_caixa", "0005_correcao_rodada1_percentual_dia1_mensagens"),
    ]

    operations = [
        migrations.RunPython(semear_tabela_jan_abr_2025, remover_tabela_jan_abr_2025),
    ]
