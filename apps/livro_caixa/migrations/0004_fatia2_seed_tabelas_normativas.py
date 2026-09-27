# DL-046, fatia 2 — carga inicial dos valores normativos do carnê-leão
# (RC-131, PE-71 respondida em docs/planos/DL-046-livro-caixa-e-carne-leao.md).
#
# ⚠️ Critério 5 do plano: "nenhum número normativo no código: teste que
# falha se a tabela vier de constante". Os números abaixo são a ÚNICA
# gravação destes valores em todo o repositório — `apps.livro_caixa.
# carne_leao` (o motor de cálculo) NUNCA os repete como literal Python; ele
# só lê estas quatro tabelas pelo ORM. Uma vigência NOVA (mudança de tabela,
# de redução ou do valor por dependente) entra por uma migração de dados
# NOVA, revisada e versionada — nunca por edição desta aqui, nem por admin
# (este app não registra `ModelAdmin` para estes quatro modelos nesta
# fatia — ver o comentário de `VigenciaTabelaProgressivaCarneLeao`, em
# apps/livro_caixa/models.py).
from decimal import Decimal

from django.db import migrations

# ---------------------------------------------------------------------------
# 1. Tabela progressiva mensal vigente desde maio/2025 (mantida em 2026).
#
# Fonte: Lei nº 15.191/2025, art. 2º, que dá nova redação ao art. 1º, XII,
# da Lei nº 11.482/2007, "a partir do mês de maio do ano-calendário de
# 2025" (texto bruto conferido pelo arquiteto-senior depois de a pesquisa
# ter indicado, por erro, parcelas de tabela ANTIGA — R$ 636,13/R$ 869,36 —
# ver docs/planos/DL-046-livro-caixa-e-carne-leao.md, "Erro da pesquisa,
# corrigido antes do registro"). Confirmada também no Perguntas e Respostas
# IRPF 2026 v1.00 (23/04/2026), pergunta 267.
FONTE_TABELA_PROGRESSIVA_2025_05 = (
    "Lei nº 15.191/2025, art. 2º (nova redação ao art. 1º, XII, da Lei nº "
    "11.482/2007), 'a partir do mês de maio do ano-calendário de 2025'; "
    "conferida no texto bruto da lei pelo arquiteto-senior (RC-131, "
    "requisitos.md) — a pesquisa original indicou, por erro, parcelas de "
    "tabela antiga (R$ 636,13/R$ 869,36), corrigidas antes deste registro."
)

_FAIXAS_TABELA_2025_05 = [
    # (ordem, limite_inferior, limite_superior, aliquota, parcela_a_deduzir)
    (1, Decimal("0.00"), Decimal("2428.80"), Decimal("0.0000"), Decimal("0.00")),
    (2, Decimal("2428.81"), Decimal("2826.65"), Decimal("0.0750"), Decimal("182.16")),
    (3, Decimal("2826.66"), Decimal("3751.05"), Decimal("0.1500"), Decimal("394.16")),
    (4, Decimal("3751.06"), Decimal("4664.68"), Decimal("0.2250"), Decimal("675.49")),
    (5, Decimal("4664.69"), None, Decimal("0.2750"), Decimal("908.73")),
]

# ---------------------------------------------------------------------------
# 2. Redução mensal da Lei nº 15.270/2025 (Lei nº 9.250/1995, art. 3º-A),
# vigente desde janeiro/2026 — "a partir do mês de janeiro do ano-
# calendário de 2026" (texto bruto da lei). Aplicação ao carnê-leão
# confirmada no Perguntas e Respostas IRPF 2026 v1.00 (23/04/2026),
# perguntas 266 e 267 (RC-131/PE-71).
FONTE_REDUCAO_2026_01 = (
    "Lei nº 15.270/2025 (inclui o art. 3º-A na Lei nº 9.250/1995), 'a "
    "partir do mês de janeiro do ano-calendário de 2026'; Lei nº "
    "9.250/1995, art. 3º-A, caput e §§1º/2º; aplicação ao carnê-leão "
    "confirmada no Perguntas e Respostas IRPF 2026 v1.00 (23/04/2026), "
    "perguntas 266 e 267 (RC-131, requisitos.md)."
)
LIMITE_FAIXA_PLENA_REDUCAO_2026_01 = Decimal("5000.00")
REDUCAO_MAXIMA_2026_01 = Decimal("312.89")
CONSTANTE_FORMULA_REDUCAO_2026_01 = Decimal("978.62")
COEFICIENTE_REDUCAO_2026_01 = Decimal("0.133145")
LIMITE_SUPERIOR_REDUCAO_2026_01 = Decimal("7350.00")

# ---------------------------------------------------------------------------
# 3. Valor por dependente — RIR/2018 (Decreto 9.580/2018), art. 71, VI:
# "R$ 189,59 ... para os meses de abril a dezembro do ano-calendário de
# 2015". HI-32 (requisitos.md): nenhuma norma posterior encontrada que
# altere o valor; nenhuma fonte confirma literalmente que ele continua
# vigente em 2026 — inferência por ausência de alteração, registrada como
# hipótese. Validação profissional do Fred antes de uso com cliente real.
FONTE_DEPENDENTE_2015_04 = (
    "RIR/2018 (Decreto 9.580/2018), art. 71, VI: 'R$ 189,59 ... para os "
    "meses de abril a dezembro do ano-calendário de 2015'. HI-32 "
    "(requisitos.md): sem confirmação literal para 2026, sem norma "
    "posterior encontrada que altere — validação profissional do Fred "
    "pendente antes de uso com cliente real."
)
VALOR_POR_DEPENDENTE_2015_04 = Decimal("189.59")


def semear_tabelas_normativas(apps, schema_editor):
    VigenciaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "VigenciaTabelaProgressivaCarneLeao"
    )
    FaixaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "FaixaTabelaProgressivaCarneLeao"
    )
    VigenciaReducaoCarneLeao = apps.get_model("livro_caixa", "VigenciaReducaoCarneLeao")
    VigenciaDependenteCarneLeao = apps.get_model("livro_caixa", "VigenciaDependenteCarneLeao")

    vigencia_tabela = VigenciaTabelaProgressivaCarneLeao.objects.create(
        vigencia_inicio="2025-05-01", fonte=FONTE_TABELA_PROGRESSIVA_2025_05
    )
    for ordem, limite_inferior, limite_superior, aliquota, parcela in _FAIXAS_TABELA_2025_05:
        FaixaTabelaProgressivaCarneLeao.objects.create(
            vigencia=vigencia_tabela,
            ordem=ordem,
            limite_inferior=limite_inferior,
            limite_superior=limite_superior,
            aliquota=aliquota,
            parcela_a_deduzir=parcela,
        )

    VigenciaReducaoCarneLeao.objects.create(
        vigencia_inicio="2026-01-01",
        fonte=FONTE_REDUCAO_2026_01,
        limite_faixa_plena=LIMITE_FAIXA_PLENA_REDUCAO_2026_01,
        reducao_maxima=REDUCAO_MAXIMA_2026_01,
        constante_formula=CONSTANTE_FORMULA_REDUCAO_2026_01,
        coeficiente=COEFICIENTE_REDUCAO_2026_01,
        limite_superior=LIMITE_SUPERIOR_REDUCAO_2026_01,
    )

    VigenciaDependenteCarneLeao.objects.create(
        vigencia_inicio="2015-04-01",
        fonte=FONTE_DEPENDENTE_2015_04,
        valor_por_dependente=VALOR_POR_DEPENDENTE_2015_04,
    )


def remover_tabelas_normativas(apps, schema_editor):
    # Reversão completa: as três vigências semeadas por esta migração
    # (as faixas somem sozinhas, `on_delete=PROTECT` na FK não impede a
    # exclusão da vigência quando ela mesma é a dona das faixas — é
    # `CASCADE` implícito do lado inverso? NÃO: `PROTECT` é do lado da
    # FAIXA para a VIGÊNCIA, então apagar a vigência com faixas ainda
    # PROTEGIDAS levantaria `ProtectedError`. Por isso as faixas são
    # apagadas primeiro, explicitamente.
    VigenciaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "VigenciaTabelaProgressivaCarneLeao"
    )
    FaixaTabelaProgressivaCarneLeao = apps.get_model(
        "livro_caixa", "FaixaTabelaProgressivaCarneLeao"
    )
    VigenciaReducaoCarneLeao = apps.get_model("livro_caixa", "VigenciaReducaoCarneLeao")
    VigenciaDependenteCarneLeao = apps.get_model("livro_caixa", "VigenciaDependenteCarneLeao")

    FaixaTabelaProgressivaCarneLeao.objects.filter(vigencia__vigencia_inicio="2025-05-01").delete()
    VigenciaTabelaProgressivaCarneLeao.objects.filter(vigencia_inicio="2025-05-01").delete()
    VigenciaReducaoCarneLeao.objects.filter(vigencia_inicio="2026-01-01").delete()
    VigenciaDependenteCarneLeao.objects.filter(vigencia_inicio="2015-04-01").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("livro_caixa", "0003_fatia2_tabelas_normativas"),
    ]

    operations = [
        migrations.RunPython(semear_tabelas_normativas, remover_tabelas_normativas),
    ]
