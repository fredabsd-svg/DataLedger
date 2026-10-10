# DL-089 (BL-72 e BL-73), migração ADITIVA: origem e documento de origem no lançamento
# contábil. Hoje `LancamentoContabil` não diz de onde veio; sem isto não há como distinguir
# lançamento digitado de lançamento gerado, nem chegar do documento ao lançamento (BL-66 e a
# integração fiscal → contábil dependem disso).
#
# O QUE ESTA MIGRAÇÃO FAZ, em ordem:
#
# 1. `AddField` de `origem` (default `manual`), `documento_origem_tipo` e
#    `documento_origem_id` (nulos). O default resolve os lançamentos que já existem SEM
#    UPDATE: o PostgreSQL preenche o `ADD COLUMN` com o default constante, sem reescrever a
#    tabela e sem disparar gatilho de linha. Por isso NÃO há RunPython de backfill: um UPDATE
#    em lançamento efetivado seria recusado pelo gatilho de imutabilidade (DL-052), e o
#    backfill da DL-016 F5 só é possível porque tem exceção explícita para `competencia_id`.
#    Efeito declarado: lançamento que a importação da DL-077 efetivou ANTES desta migração
#    fica `manual` na coluna. Ele continua automático para o ESTORNO, porque
#    `exige_permissao_de_estorno_automatico` (services) lê a chave `importacao:` e o vínculo em
#    `LancamentoImportado` (DL-089, A1). Reclassificar a coluna exigiria uma exceção nova no
#    gatilho, e não foi feito: é decisão do responsável, não desta migração.
#
# 2. Quatro `CheckConstraint`: origem válida; tipo de documento válido; documento consistente
#    (ou não há documento, ou há tipo e identificador sem espaço nas pontas e não vazio após
#    aparar, e a origem não é `manual`); e origem pareada ao tipo de documento (DL-089, A6:
#    `importacao` só com `importacao_lancamentos`; `escrita_fiscal` só com NF-e ou NFS-e).
#    Valem em SQLite e PostgreSQL; em PostgreSQL também protegem `bulk_create` e SQL direto.
#    A 0026 ainda não está na `main`, então estas CHECKs entram nela, e não numa 0027.
#
# 3. SÓ EM POSTGRESQL (RunPython com guarda de `connection.vendor`, mesmo padrão das
#    migrações 0013 e 0017): `CREATE OR REPLACE` da função
#    `contabilidade_recusar_alteracao_do_livro`, que o gatilho `trg_lancamento_contabil_imutavel`
#    já chama. A função passa a recusar, ANTES da exceção do backfill, qualquer UPDATE que
#    altere `origem`, `documento_origem_tipo` ou `documento_origem_id`, com o nome estável
#    `lancamento_origem_imutavel`. Vale para `QuerySet.update()` e SQL direto.
#    Nota de fato: o corpo anterior (0017) já recusava estes campos, porque sua comparação é
#    genérica (`to_jsonb` sem `competencia_id`). A regra nova é explícita: ela nomeia o motivo
#    e não depende de um campo ficar de fora da comparação no futuro. A exceção do backfill
#    da competência continua igual, e só ela.
#
# 4. A reversão RECUSA se houver lançamento de origem diferente de `manual` (ou com documento).
#    Por isso o RunPython de checagem é a ÚLTIMA operação da lista: a reversão executa as
#    operações de trás para frente, então ela roda primeiro, antes de qualquer `RemoveField`.
#    Com a recusa, a transação inteira é desfeita e nenhum dado muda. Sem essa checagem, a
#    reversão apagaria a origem de lançamentos que a versão anterior não sabe representar.
#
# Reversão sem dado de origem automática: `migrate contabilidade 0025` restaura a função de
# imutabilidade da 0017 e remove as colunas e as constraints. Sem perda de dado.

from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q, Value
from django.db.models.expressions import NegatedExpression
from django.db.models.functions import Trim
from django.db.models.lookups import Exact

_LIMITE_DE_IDS_NA_MENSAGEM = 20

# Corpo da função de imutabilidade ACRESCIDO da regra de origem. As demais linhas são as da
# 0017, sem alteração. Trocar aqui qualquer coisa que não seja a regra de origem exige nova
# migração, não edição desta.
_NOVA_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_recusar_alteracao_do_livro()
RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_lancamentocontabil' THEN
        -- DL-089: origem e documento de origem são gravados na criação e não mudam.
        -- Vem ANTES da exceção do backfill, que nunca deve cobrir estes campos.
        IF TG_OP = 'UPDATE'
           AND (NEW.origem IS DISTINCT FROM OLD.origem
                OR NEW.documento_origem_tipo IS DISTINCT FROM OLD.documento_origem_tipo
                OR NEW.documento_origem_id IS DISTINCT FROM OLD.documento_origem_id)
        THEN
            RAISE EXCEPTION
                'Origem ou documento de origem de lançamento contábil não pode ser alterado (lançamento %); '
                'registre um estorno.', OLD.id
                USING ERRCODE = '23514',
                      CONSTRAINT = 'lancamento_origem_imutavel';
        END IF;

        -- ÚNICA exceção: o backfill da competência (comando de gerência
        -- `backfill_lancamento_competencia`, DL-016 F5) preenche
        -- `competencia_id` de NULL para um valor e NÃO toca em mais nada.
        -- NOT NULL -> outro valor continua recusado.
        IF TG_OP = 'UPDATE'
           AND OLD.competencia_id IS NULL
           AND NEW.competencia_id IS NOT NULL
           AND (to_jsonb(NEW) - 'competencia_id') = (to_jsonb(OLD) - 'competencia_id')
           -- DL-052 rodada 1 (D3): a competência nova tem de ser da MESMA
           -- empresa do lançamento; o backfill filtra por empresa, e agora o
           -- banco também exige (uma competência de outra empresa prenderia
           -- o lançamento ao fechamento de outro cliente).
           AND EXISTS (
               SELECT 1 FROM contabilidade_competencia c
                WHERE c.id = NEW.competencia_id AND c.empresa_id = OLD.empresa_id
           )
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'Lançamento contábil efetivado não pode ser alterado nem excluído (% do lançamento %); '
            'registre um estorno.', TG_OP, OLD.id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_contabil_imutavel';
    END IF;

    RAISE EXCEPTION
        'Item de lançamento efetivado não pode ser alterado nem excluído (% do item %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'item_lancamento_imutavel';
END;
$$ LANGUAGE plpgsql;
"""

# Corpo ANTERIOR, exatamente como está na migração 0017 (reversão).
_ANTIGA_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_recusar_alteracao_do_livro()
RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_lancamentocontabil' THEN
        -- ÚNICA exceção: o backfill da competência (comando de gerência
        -- `backfill_lancamento_competencia`, DL-016 F5) preenche
        -- `competencia_id` de NULL para um valor e NÃO toca em mais nada.
        -- NOT NULL -> outro valor continua recusado.
        IF TG_OP = 'UPDATE'
           AND OLD.competencia_id IS NULL
           AND NEW.competencia_id IS NOT NULL
           AND (to_jsonb(NEW) - 'competencia_id') = (to_jsonb(OLD) - 'competencia_id')
           -- DL-052 rodada 1 (D3): a competência nova tem de ser da MESMA
           -- empresa do lançamento; o backfill filtra por empresa, e agora o
           -- banco também exige (uma competência de outra empresa prenderia
           -- o lançamento ao fechamento de outro cliente).
           AND EXISTS (
               SELECT 1 FROM contabilidade_competencia c
                WHERE c.id = NEW.competencia_id AND c.empresa_id = OLD.empresa_id
           )
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'Lançamento contábil efetivado não pode ser alterado nem excluído (% do lançamento %); '
            'registre um estorno.', TG_OP, OLD.id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_contabil_imutavel';
    END IF;

    RAISE EXCEPTION
        'Item de lançamento efetivado não pode ser alterado nem excluído (% do item %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'item_lancamento_imutavel';
END;
$$ LANGUAGE plpgsql;
"""


def _aplicar_gatilho_de_origem(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_NOVA_SQL, params=None)


def _restaurar_gatilho_anterior(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ANTIGA_SQL, params=None)


def _recusar_reversao_com_origem_automatica(apps, schema_editor):
    """Recusa a reversão se houver lançamento que a versão anterior não sabe representar.

    Roda como reverso da ÚLTIMA operação, então é a primeira a executar na reversão. Só
    leitura: ou a reversão passa sem perda, ou falha com a lista de ids e nada é alterado.
    """
    banco = schema_editor.connection.alias
    Lancamento = apps.get_model("contabilidade", "LancamentoContabil")
    automaticos = Lancamento.objects.using(banco).filter(
        ~Q(origem="manual") | Q(documento_origem_tipo__isnull=False)
    )
    total = automaticos.count()
    if total:
        ids = list(
            automaticos.order_by("id").values_list("id", flat=True)[:_LIMITE_DE_IDS_NA_MENSAGEM]
        )
        raise RuntimeError(
            "DL-089: a migração 0026 não pode ser revertida porque o banco tem "
            f"{total} lançamento(s) de origem automática (importação ou escrita fiscal) "
            "ou com documento de origem, que a versão anterior não representa; a reversão "
            "perderia essa informação. Nenhum dado foi alterado. "
            f"Ids (até {_LIMITE_DE_IDS_NA_MENSAGEM}): {ids}."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0025_dl077_correcao_auditoria_rodada_1"),
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lancamentocontabil",
            name="documento_origem_id",
            field=models.CharField(
                blank=True,
                help_text="Identificador estável do documento no app de origem, em texto.",
                max_length=64,
                null=True,
                verbose_name="identificador do documento de origem",
            ),
        ),
        migrations.AddField(
            model_name="lancamentocontabil",
            name="documento_origem_tipo",
            field=models.CharField(
                blank=True,
                choices=[
                    ("importacao_lancamentos", "Lote de importação de lançamentos"),
                    ("escrituracao_nfe", "Escrituração de NF-e (reservado)"),
                    ("escrituracao_nfse", "Escrituração de NFS-e (reservado)"),
                ],
                max_length=40,
                null=True,
                verbose_name="tipo do documento de origem",
            ),
        ),
        migrations.AddField(
            model_name="lancamentocontabil",
            name="origem",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("importacao", "Importação de lançamentos"),
                    ("escrita_fiscal", "Escrita fiscal (reservado)"),
                ],
                db_default="manual",
                default="manual",
                help_text="De onde veio o lançamento. Gravada na criação e imutável. Só o servidor a define, pelo caminho que cria o lançamento.",
                max_length=20,
                verbose_name="origem",
            ),
        ),
        migrations.AddConstraint(
            model_name="lancamentocontabil",
            constraint=models.CheckConstraint(
                condition=models.Q(("origem__in", ["manual", "importacao", "escrita_fiscal"])),
                name="ck_lancamentocontabil_origem_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="lancamentocontabil",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("documento_origem_tipo__isnull", True),
                    (
                        "documento_origem_tipo__in",
                        [
                            "importacao_lancamentos",
                            "escrituracao_nfe",
                            "escrituracao_nfse",
                        ],
                    ),
                    _connector="OR",
                ),
                name="ck_lancamentocontabil_documento_tipo_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="lancamentocontabil",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("documento_origem_tipo__isnull", True),
                        ("documento_origem_id__isnull", True),
                    ),
                    models.Q(
                        ("documento_origem_tipo__isnull", False),
                        ("documento_origem_id__isnull", False),
                        Exact(
                            Trim("documento_origem_id"), F("documento_origem_id")
                        ),
                        NegatedExpression(
                            Exact(Trim("documento_origem_id"), Value(""))
                        ),
                        models.Q(("origem", "manual"), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="ck_lancamentocontabil_documento_consistente",
            ),
        ),
        migrations.AddConstraint(
            model_name="lancamentocontabil",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("documento_origem_tipo__isnull", True),
                    models.Q(
                        ("documento_origem_tipo", "importacao_lancamentos"),
                        ("origem", "importacao"),
                    ),
                    models.Q(
                        ("documento_origem_tipo__in", ["escrituracao_nfe", "escrituracao_nfse"]),
                        ("origem", "escrita_fiscal"),
                    ),
                    _connector="OR",
                ),
                name="ck_lancamentocontabil_origem_pareada_ao_documento",
            ),
        ),
        migrations.RunPython(_aplicar_gatilho_de_origem, _restaurar_gatilho_anterior),
        # Última da lista = primeira a ser revertida. Ver o comentário 4 no topo.
        migrations.RunPython(
            migrations.RunPython.noop,
            _recusar_reversao_com_origem_automatica,
        ),
    ]
