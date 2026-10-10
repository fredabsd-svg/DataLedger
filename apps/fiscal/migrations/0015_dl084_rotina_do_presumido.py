# DL-084 (rotina do Presumido), migração ADITIVA e reversível. Gerada pelo Django e completada à mão
# com a carga inicial, o gatilho do encerramento e a guarda de reversão.
#
# - `fiscal_receitatrimestralpresumido.competencia`: texto, vazio = não informado (HI-135).
# - `fiscal_parametrospresumidoempresa`: uma linha por empresa; sem linha vale o padrão do
# escritório
#   (três quotas, sem padrão de combustível; HI-136).
# - `fiscal_feriadolocal` e `fiscal_excecaoferiadolocal`: feriados de Palmas e do Tocantins
# (HI-137),
#   com a lei e a data da leitura de cada linha. A carga é deste arquivo, com a fonte escrita.
# - `fiscal_encerramentomedidajudiciallc224`: ato de encerramento de medida (BL-680, item 1). Tem
#   gatilho que impede UPDATE e DELETE. A medida em si continua como estava (só a revogação a muda).
#
# Reversão (`migrate fiscal 0014`): RECUSA, sem alterar nada, se houver competência preenchida,
# parâmetro gravado ou encerramento de medida. São dados do contador. A checagem é a ÚLTIMA operação
# da lista, então na reversão roda PRIMEIRO. Sem esses dados, a reversão remove o que esta migração
# criou, na ordem inversa.

from datetime import date

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Data em que a lei, o decreto e a lista bancária foram lidos (consulta de 09/10/2026, RC-173 e
# RC-174).
_DATA_LEITURA = date(2026, 10, 9)
_FONTE_FEBRABAN = (
    "Febraban, feriados estaduais e municipais de Palmas/TO (CAF501 v.007541 de 07/10/2026; lista"
    "de"
    "01/10/2026 a 29/09/2027, impressa em 09/10/2026; RC-174)"
)
_LEI_BONFIM = (
    "Lei nº 4.509, de 25/09/2024, art. 1º (DOE nº 6.664, de 26/09/2024); vigência pelo art. 3º, "
    "primeiro ano observado: 2025"
)
_LEI_NATIVIDADE = "Lei nº 627, de 28/12/1993, arts. 1º e 2º (DOE nº 298)"
_LEI_CRIACAO_ESTADO = "Lei nº 098, de 17/11/1989, art. 1º (DOE nº 23)"
_LEI_SAO_JOSE = "Lei municipal de Palmas nº 577, de 02/04/1996, art. 1º, III"
_LEI_ANIVERSARIO = (
    "Lei municipal de Palmas nº 108, de 15/05/1991, art. 1º, mantida pela Lei nº 577/1996, art. 2º"
)
_DECRETO_2026 = (
    "Decreto estadual nº 7.238, de 23/09/2026 (DOE ed. 7.149), com base na Lei nº 1.088/1999, art."
    "1º;"
    "citado no Decreto municipal de Palmas nº 2.993/2026 (texto estadual não lido)"
)

# (UF, município chave, esfera, mês, dia, descrição, lei, vigência inicial, fonte bancária)
# Município vazio = estadual para todo o Tocantins (só a lei). Município PALMAS = linha da praça:
# traz
# a confirmação da lista bancária e substitui a linha da UF no mesmo dia.
_FERIADOS_INICIAIS = (
    ("TO", "", "estadual", 8, 15, "Dia do Senhor do Bonfim", _LEI_BONFIM, date(2024, 9, 26), ""),
    (
        "TO",
        "",
        "estadual",
        9,
        8,
        "Nossa Senhora da Natividade, padroeira do Estado",
        _LEI_NATIVIDADE,
        date(1993, 12, 28),
        "",
    ),
    (
        "TO",
        "",
        "estadual",
        10,
        5,
        "Criação do Estado e promulgação da primeira Constituição Estadual",
        _LEI_CRIACAO_ESTADO,
        date(1989, 11, 17),
        "",
    ),
    (
        "TO",
        "PALMAS",
        "estadual",
        8,
        15,
        "Dia do Senhor do Bonfim",
        _LEI_BONFIM,
        date(2024, 9, 26),
        _FONTE_FEBRABAN,
    ),
    (
        "TO",
        "PALMAS",
        "estadual",
        9,
        8,
        "Nossa Senhora da Natividade, padroeira do Estado",
        _LEI_NATIVIDADE,
        date(1993, 12, 28),
        _FONTE_FEBRABAN,
    ),
    (
        "TO",
        "PALMAS",
        "estadual",
        10,
        5,
        "Criação do Estado e promulgação da primeira Constituição Estadual",
        _LEI_CRIACAO_ESTADO,
        date(1989, 11, 17),
        # A lista da Febraban não traz 05/10 para Palmas em 2027: fica sem fonte bancária (aviso
        # fraco).
        "",
    ),
    (
        "TO",
        "PALMAS",
        "municipal",
        3,
        19,
        "São José, padroeiro de Palmas",
        _LEI_SAO_JOSE,
        date(1996, 4, 2),
        _FONTE_FEBRABAN,
    ),
    (
        "TO",
        "PALMAS",
        "municipal",
        5,
        20,
        "Aniversário de Palmas (Lançamento da Pedra Fundamental)",
        _LEI_ANIVERSARIO,
        date(1991, 5, 15),
        _FONTE_FEBRABAN,
    ),
)

# (UF, município chave, mês, dia, ano, data observada, ato, fonte bancária). Exceção por ano
# (HI-137).
# O 05/10/2026 foi observado em 09/10: vale para o estado (linha da UF) e, com a confirmação
# bancária
# de Palmas, para a linha da praça. Sem a linha da praça, o aviso bancário não sairia em Palmas.
_EXCECOES_INICIAIS = (
    ("TO", "", 10, 5, 2026, date(2026, 10, 9), _DECRETO_2026, ""),
    ("TO", "PALMAS", 10, 5, 2026, date(2026, 10, 9), _DECRETO_2026, _FONTE_FEBRABAN),
)


def _so_postgresql(schema_editor) -> bool:
    # O gatilho é plpgsql. Em outro banco (o teste de migração em SQLite roda a cadeia inteira), a
    # migração só cria as tabelas e as colunas. Mesmo padrão da 0014.
    return schema_editor.connection.vendor == "postgresql"


def _criar_gatilho_encerramento(apps, schema_editor):
    if _so_postgresql(schema_editor):
        schema_editor.execute(_SQL_FUNCAO_ENCERRAMENTO + _SQL_GATILHO_ENCERRAMENTO)


def _remover_gatilho_encerramento(apps, schema_editor):
    if _so_postgresql(schema_editor):
        schema_editor.execute(_SQL_REVERSO_ENCERRAMENTO)


def _carregar_feriados_locais(apps, schema_editor):
    FeriadoLocal = apps.get_model("fiscal", "FeriadoLocal")
    ExcecaoFeriadoLocal = apps.get_model("fiscal", "ExcecaoFeriadoLocal")
    por_chave = {}
    for uf, municipio, esfera, mes, dia, descricao, lei, vigencia, fonte in _FERIADOS_INICIAIS:
        por_chave[(uf, municipio, mes, dia)] = FeriadoLocal.objects.create(
            uf=uf,
            municipio=municipio,
            esfera=esfera,
            mes=mes,
            dia=dia,
            descricao=descricao,
            fundamento=lei,
            data_leitura=_DATA_LEITURA,
            fonte_bancaria=fonte,
            vigencia_inicio=vigencia,
            vigencia_fim=None,
        )
    for uf, municipio, mes, dia, ano, observada, ato, fonte in _EXCECOES_INICIAIS:
        ExcecaoFeriadoLocal.objects.create(
            feriado=por_chave[(uf, municipio, mes, dia)],
            ano=ano,
            data_observada=observada,
            fundamento=ato,
            data_leitura=_DATA_LEITURA,
            fonte_bancaria=fonte,
        )


def _descarregar_feriados_locais(apps, schema_editor):
    # Só a carga do produto: a tabela não tem caminho de escrita pelo cliente, e a guarda da
    # reversão
    # (última operação) já recusou se houvesse algo além dela.
    apps.get_model("fiscal", "ExcecaoFeriadoLocal").objects.all().delete()
    apps.get_model("fiscal", "FeriadoLocal").objects.all().delete()


def _recusar_reversao_com_dados_do_contador(apps, schema_editor):
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
    if pendencias:
        raise RuntimeError(
            "Reversão da DL-084 recusada, sem alterar nada: "
            + "; ".join(pendencias)
            + ". São dados do contador: estorne-os ou trate-os antes de reverter."
        )


# Gatilho: o encerramento de medida é um ato gravado. Não muda nem se apaga (BL-680, item 1).
_SQL_FUNCAO_ENCERRAMENTO = """
CREATE OR REPLACE FUNCTION fiscal_presumido_encerramento_guarda()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'encerramento de medida judicial não muda nem se apaga; é um ato gravado'
        USING ERRCODE = '23514', CONSTRAINT = 'presumido_encerramento_imutavel';
END;
$$ LANGUAGE plpgsql;
"""

_SQL_GATILHO_ENCERRAMENTO = """
CREATE TRIGGER trg_presumido_encerramento_guarda
BEFORE UPDATE OR DELETE ON fiscal_encerramentomedidajudiciallc224
FOR EACH ROW EXECUTE FUNCTION fiscal_presumido_encerramento_guarda();
"""

_SQL_REVERSO_ENCERRAMENTO = """
DROP TRIGGER IF EXISTS trg_presumido_encerramento_guarda
    ON fiscal_encerramentomedidajudiciallc224;
DROP FUNCTION IF EXISTS fiscal_presumido_encerramento_guarda();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        ("fiscal", "0014_dl082_pre_das_comercio"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EncerramentoMedidaJudicialLC224",
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
                    "ano",
                    models.PositiveSmallIntegerField(
                        verbose_name="ano do último trimestre coberto"
                    ),
                ),
                (
                    "trimestre",
                    models.PositiveSmallIntegerField(
                        verbose_name="último trimestre coberto (1 a 4)"
                    ),
                ),
                (
                    "motivo",
                    models.CharField(max_length=500, verbose_name="motivo do encerramento"),
                ),
                (
                    "encerrada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="encerrada em"),
                ),
            ],
            options={
                "verbose_name": "encerramento de medida judicial contra a LC 224",
                "verbose_name_plural": "encerramentos de medidas judiciais contra a LC 224",
                "ordering": ["medida_id", "id"],
            },
        ),
        migrations.CreateModel(
            name="ExcecaoFeriadoLocal",
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
                ("ano", models.PositiveSmallIntegerField(verbose_name="ano")),
                (
                    "data_observada",
                    models.DateField(verbose_name="data observada no ano"),
                ),
                (
                    "fundamento",
                    models.CharField(max_length=300, verbose_name="ato que moveu o feriado"),
                ),
                (
                    "data_leitura",
                    models.DateField(verbose_name="data da leitura da fonte"),
                ),
                (
                    "fonte_bancaria",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=300,
                        verbose_name="fonte bancária (Febraban), quando houver",
                    ),
                ),
            ],
            options={
                "verbose_name": "exceção de feriado local por ano",
                "verbose_name_plural": "exceções de feriado local por ano",
                "ordering": ["feriado_id", "ano"],
            },
        ),
        migrations.CreateModel(
            name="FeriadoLocal",
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
                ("uf", models.CharField(max_length=2, verbose_name="UF")),
                (
                    "municipio",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=100,
                        verbose_name="município (vazio = estadual)",
                    ),
                ),
                (
                    "esfera",
                    models.CharField(
                        choices=[("estadual", "Estadual"), ("municipal", "Municipal")],
                        max_length=10,
                        verbose_name="esfera",
                    ),
                ),
                ("mes", models.PositiveSmallIntegerField(verbose_name="mês")),
                ("dia", models.PositiveSmallIntegerField(verbose_name="dia")),
                (
                    "descricao",
                    models.CharField(max_length=200, verbose_name="descrição"),
                ),
                (
                    "fundamento",
                    models.CharField(
                        max_length=300, verbose_name="lei ou ato que declara o feriado"
                    ),
                ),
                (
                    "data_leitura",
                    models.DateField(verbose_name="data da leitura da fonte"),
                ),
                (
                    "fonte_bancaria",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=300,
                        verbose_name="fonte bancária (Febraban), quando houver",
                    ),
                ),
                (
                    "vigencia_inicio",
                    models.DateField(verbose_name="início da vigência"),
                ),
                (
                    "vigencia_fim",
                    models.DateField(blank=True, null=True, verbose_name="fim da vigência"),
                ),
            ],
            options={
                "verbose_name": "feriado local",
                "verbose_name_plural": "feriados locais",
                "ordering": ["uf", "municipio", "mes", "dia"],
            },
        ),
        migrations.CreateModel(
            name="ParametrosPresumidoEmpresa",
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
                    "forma_recolhimento",
                    models.CharField(
                        choices=[
                            ("quota_unica", "Quota única"),
                            ("duas_quotas", "Duas quotas"),
                            ("tres_quotas", "Três quotas"),
                        ],
                        default="tres_quotas",
                        max_length=12,
                        verbose_name="forma de recolhimento padrão",
                    ),
                ),
                (
                    "padrao_combustivel",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "Sem padrão"),
                            ("posto", "Posto de combustível"),
                            ("trr", "Transportador-revendedor-retalhista (TRR)"),
                            ("distribuidora", "Distribuidora"),
                        ],
                        default="",
                        max_length=14,
                        verbose_name="padrão de combustível",
                    ),
                ),
                (
                    "atualizado_em",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
            ],
            options={
                "verbose_name": "parâmetros do presumido da empresa",
                "verbose_name_plural": "parâmetros do presumido das empresas",
            },
        ),
        migrations.AddField(
            model_name="receitatrimestralpresumido",
            name="competencia",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="competência ou parcela",
            ),
        ),
        migrations.AddConstraint(
            model_name="receitatrimestralpresumido",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("competencia", ""),
                    (
                        "competencia__regex",
                        "^([0-9]{4}-(0[1-9]|1[0-2])|parcela [1-9][0-9]?)$",
                    ),
                    _connector="OR",
                ),
                name="presumido_receita_competencia_valida",
            ),
        ),
        migrations.AddField(
            model_name="encerramentomedidajudiciallc224",
            name="encerrada_por",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="encerrada por",
            ),
        ),
        migrations.AddField(
            model_name="encerramentomedidajudiciallc224",
            name="medida",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="encerramentos",
                to="fiscal.medidajudiciallc224",
                verbose_name="medida",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.UniqueConstraint(
                fields=("uf", "municipio", "mes", "dia", "vigencia_inicio"),
                name="feriado_local_unico",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(("uf__regex", "^[A-Z]{2}$")),
                name="feriado_local_uf_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(("esfera__in", ["estadual", "municipal"])),
                name="feriado_local_esfera_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("esfera", "estadual"),
                    models.Q(("municipio", ""), _negated=True),
                    _connector="OR",
                ),
                name="feriado_local_municipal_tem_municipio",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("dia__gte", 1), ("dia__lte", 31), ("mes__gte", 1), ("mes__lte", 12)
                ),
                name="feriado_local_data_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(("fundamento", ""), _negated=True),
                name="feriado_local_fundamento_obrigatorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="feriadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("vigencia_fim__isnull", True),
                    ("vigencia_fim__gte", models.F("vigencia_inicio")),
                    _connector="OR",
                ),
                name="feriado_local_vigencia_coerente",
            ),
        ),
        migrations.AddField(
            model_name="excecaoferiadolocal",
            name="feriado",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="excecoes",
                to="fiscal.feriadolocal",
                verbose_name="feriado",
            ),
        ),
        migrations.AddField(
            model_name="parametrospresumidoempresa",
            name="atualizado_por",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="atualizado por",
            ),
        ),
        migrations.AddField(
            model_name="parametrospresumidoempresa",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parametros_presumido",
                to="empresas.empresa",
                verbose_name="empresa",
            ),
        ),
        migrations.AddConstraint(
            model_name="encerramentomedidajudiciallc224",
            constraint=models.UniqueConstraint(
                fields=("medida",), name="presumido_encerramento_unico_por_medida"
            ),
        ),
        migrations.AddConstraint(
            model_name="encerramentomedidajudiciallc224",
            constraint=models.CheckConstraint(
                condition=models.Q(("trimestre__gte", 1), ("trimestre__lte", 4)),
                name="presumido_encerramento_trimestre_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="encerramentomedidajudiciallc224",
            constraint=models.CheckConstraint(
                condition=models.Q(("motivo", ""), _negated=True),
                name="presumido_encerramento_motivo_obrigatorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="excecaoferiadolocal",
            constraint=models.UniqueConstraint(
                fields=("feriado", "ano"), name="excecao_feriado_unica_por_ano"
            ),
        ),
        migrations.AddConstraint(
            model_name="excecaoferiadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(("ano__gte", 1970), ("ano__lte", 2999)),
                name="excecao_feriado_ano_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="excecaoferiadolocal",
            constraint=models.CheckConstraint(
                condition=models.Q(("fundamento", ""), _negated=True),
                name="excecao_feriado_fundamento_obrigatorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="parametrospresumidoempresa",
            constraint=models.UniqueConstraint(
                fields=("empresa",), name="presumido_parametros_unico_por_empresa"
            ),
        ),
        migrations.AddConstraint(
            model_name="parametrospresumidoempresa",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "forma_recolhimento__in",
                        ["quota_unica", "duas_quotas", "tres_quotas"],
                    )
                ),
                name="presumido_parametros_forma_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="parametrospresumidoempresa",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("padrao_combustivel__in", ["", "posto", "trr", "distribuidora"])
                ),
                name="presumido_parametros_combustivel_valido",
            ),
        ),
        migrations.RunPython(_criar_gatilho_encerramento, _remover_gatilho_encerramento),
        migrations.RunPython(_carregar_feriados_locais, _descarregar_feriados_locais),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de qualquer tabela ou coluna sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_dados_do_contador),
    ]
