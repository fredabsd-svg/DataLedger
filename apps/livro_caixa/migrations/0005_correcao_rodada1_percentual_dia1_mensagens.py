# DL-046, fatia 2 — correção da rodada 1 da auditoria (B-1, B-4, B-5):
#
# - B-1: `percentual_desconto_simplificado` passa a morar na vigência da
#   tabela, com fonte — antes era `Decimal("0.25")` literal em
#   `carne_leao.py`, violando o critério 5 do plano ("nenhum número
#   normativo no código"). Valor de BACKFILL para a vigência JÁ gravada
#   (2025-05-01, migração 0004): 0,25 (25%), fonte Lei nº 9.250/1995, art.
#   4º, § 2º (redação da Lei nº 14.663/2023): "25% (vinte e cinco por
#   cento) do valor máximo da faixa com alíquota zero da tabela
#   progressiva mensal". `preserve_default=False` (abaixo): o valor serve
#   SÓ para preencher a linha já existente — o campo do modelo não tem
#   `default=`, então uma vigência NOVA precisa informar o percentual
#   explicitamente, nunca por acidente de valor implícito.
# - B-5: toda vigência normativa (e a competência dos dependentes) passa a
#   exigir dia 1 no banco (`CheckConstraint`), defesa em profundidade da
#   validação já feita nos dois pontos de escrita (migração de dados, para
#   as três tabelas globais; `clean()`, para os dependentes).
# - B-4: a `UniqueConstraint` da competência dos dependentes ganha
#   `violation_error_message` própria — sem isso, `full_clean()`/
#   `validate_unique()` devolvia a mensagem PADRÃO do Django antes de
#   qualquer `INSERT`, e a mensagem registrada em `apps/core/restricoes.py`
#   só valia para o caminho residual de corrida (`IntegrityError`).
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Mesmo motivo/mesma correção de `0001_inicial.py`/
        # `0003_fatia2_tabelas_normativas.py`: esta migração não depende
        # de nenhum campo específico da migração mais recente de
        # `empresas` no momento da geração.
        ("empresas", "0001_initial"),
        ("livro_caixa", "0004_fatia2_seed_tabelas_normativas"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="vigenciatabelaprogressivacarneleao",
            name="percentual_desconto_simplificado",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0.25"),
                max_digits=6,
                verbose_name="percentual do desconto simplificado (fração)",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="dependentescarneleaocliente",
            constraint=models.CheckConstraint(
                condition=models.Q(("competencia_inicio__day", 1)),
                name="dependentes_carne_leao_competencia_dia_1",
            ),
        ),
        migrations.AddConstraint(
            model_name="vigenciadependentecarneleao",
            constraint=models.CheckConstraint(
                condition=models.Q(("vigencia_inicio__day", 1)),
                name="vigencia_dependente_carne_leao_inicio_dia_1",
            ),
        ),
        migrations.AddConstraint(
            model_name="vigenciareducaocarneleao",
            constraint=models.CheckConstraint(
                condition=models.Q(("vigencia_inicio__day", 1)),
                name="vigencia_reducao_carne_leao_inicio_dia_1",
            ),
        ),
        migrations.AddConstraint(
            model_name="vigenciatabelaprogressivacarneleao",
            constraint=models.CheckConstraint(
                condition=models.Q(("vigencia_inicio__day", 1)),
                name="vigencia_tabela_carne_leao_inicio_dia_1",
            ),
        ),
        migrations.AddConstraint(
            model_name="vigenciatabelaprogressivacarneleao",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("percentual_desconto_simplificado__gte", 0),
                    ("percentual_desconto_simplificado__lte", 1),
                ),
                name="vigencia_tabela_carne_leao_percentual_simplificado_valido",
            ),
        ),
        migrations.AlterConstraint(
            model_name="dependentescarneleaocliente",
            name="dependentes_carne_leao_competencia_unica_por_empresa",
            constraint=models.UniqueConstraint(
                fields=("empresa", "competencia_inicio"),
                name="dependentes_carne_leao_competencia_unica_por_empresa",
                violation_error_message="Já existe uma quantidade de dependentes registrada para esta empresa a partir deste mês — use a retificação (PATCH) para corrigir o valor, em vez de um novo registro.",
            ),
        ),
    ]
