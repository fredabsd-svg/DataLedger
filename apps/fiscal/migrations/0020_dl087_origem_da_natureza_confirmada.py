# DL-087, item 6: de onde veio cada natureza CONFIRMADA (regra, produto, padrão da empresa ou
# manual).
#
# Tabela NOVA e aditiva, 1:1 com `NaturezaItemNFe` (FK + UniqueConstraint), e não colunas nela: a
# tabela de naturezas tem gatilhos e é lida pelas reversões de outras migrações (DL-082). Linhas
# anteriores à DL-087 não têm origem gravada (sem linha, sem reescrita).
#
# Correção da rodada 1 (A8 e A9), editada na própria 0020 porque ela não está na `main`:
# - Gatilho de imutabilidade: a origem só muda enquanto a escrituração da natureza está em rascunho,
#   com a mesma regra da natureza (DL-081). Efetivada ou estornada, nem UPDATE, nem INSERT, nem
#   DELETE. Como a natureza, a origem é o que a auditoria lê para dizer "de onde veio".
# - TRUNCATE da origem NÃO é recusado: o `flush` dos testes transacionais trunca todas as tabelas, e
#   um gatilho de instrução que recusa com linha quebrava a limpeza de testes de outras demandas (que
#   gravam confirmações). Limite declarado, como o das demais tabelas fiscais (TRUNCATE não aciona
#   gatilho de linha). A regra de classificação (0019) mantém a recusa, que o A13 pediu.
# - Reversão (`migrate fiscal 0019`): recusa, sem alterar nada, enquanto houver REGRA de
#   classificação (guarda da 0019) OU origem de nota EFETIVADA (A9; origem de rascunho não recusa).
#   Ambas as guardas rodam PRIMEIRO na reversão.

from importlib import import_module

import django.db.models.deletion
from django.db import migrations, models

_guarda_da_0019 = import_module(
    "apps.fiscal.migrations.0019_dl087_regra_de_classificacao_nfe"
)._recusar_reversao_com_regras

_SQL_FUNCAO_ORIGEM = """
CREATE OR REPLACE FUNCTION fiscal_origem_natureza_item_imutavel()
RETURNS trigger AS $$
DECLARE
    v_estado text;
BEGIN
    -- UPDATE e DELETE conferem o pai ANTIGO; INSERT e UPDATE conferem o pai NOVO. Pai inexistente
    -- (cascata de uma exclusão que já passou pela natureza, que só muda em rascunho) não é recusado
    -- aqui: a natureza já recusou a exclusão se a escrituração não estivesse em rascunho.
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT e.estado INTO v_estado
          FROM fiscal_naturezaitemnfe n
          JOIN fiscal_escrituracaonfe e ON e.id = n.escrituracao_id
         WHERE n.id = OLD.natureza_item_id;
        IF v_estado IS NOT NULL AND v_estado <> 'rascunho' THEN
            RAISE EXCEPTION
                'origem da natureza de escrituração de NF-e efetivada ou estornada não muda'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'origem_natureza_item_imutavel_depois_de_efetivada';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT e.estado INTO v_estado
          FROM fiscal_naturezaitemnfe n
          JOIN fiscal_escrituracaonfe e ON e.id = n.escrituracao_id
         WHERE n.id = NEW.natureza_item_id;
        IF v_estado IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION
                'origem da natureza de escrituração de NF-e efetivada ou estornada não muda'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'origem_natureza_item_imutavel_depois_de_efetivada';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_origem_natureza_item_imutavel
    BEFORE INSERT OR UPDATE OR DELETE ON fiscal_origemnaturezaitemnfe
    FOR EACH ROW EXECUTE FUNCTION fiscal_origem_natureza_item_imutavel();

"""

_SQL_REVERSO_ORIGEM = """
DROP TRIGGER IF EXISTS trg_origem_natureza_item_imutavel ON fiscal_origemnaturezaitemnfe;
DROP FUNCTION IF EXISTS fiscal_origem_natureza_item_imutavel();
"""


def _criar_gatilhos_origem(apps, schema_editor):
    """Só PostgreSQL: a função é PL/pgSQL. Fora dele, vale a guarda do Python (como na 0019)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_FUNCAO_ORIGEM)


def _desfazer_gatilhos_origem(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_REVERSO_ORIGEM)


def _recusar_reversao_com_origens(apps, schema_editor):
    """Guarda da reversão (A9): origem de nota EFETIVADA é fato de auditoria, e a reversão a apagaria.

    Só a efetivada recusa (formulação do plano, A9). Origem de rascunho é provisória: a natureza ainda
    pode ser trocada, e a reversão a descarta sem perda de fato. Estornada também não recusa, como a
    escrituração estornada não recusa a reversão das demais tabelas da DL-082.
    """
    total = (
        apps.get_model("fiscal", "OrigemNaturezaItemNFe")
        .objects.filter(natureza_item__escrituracao__estado="efetivada")
        .count()
    )
    if total:
        raise RuntimeError(
            f"Reversão da DL-087 recusada, sem alterar nada: {total} origem(ns) de natureza de "
            "NF-e de escrituração efetivada. Elas dizem de onde veio cada natureza confirmada: "
            "registre-as ou trate-as antes de reverter."
        )


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
        # Gatilho de imutabilidade (A8). A reversão o remove antes da tabela.
        migrations.RunPython(_criar_gatilhos_origem, _desfazer_gatilhos_origem),
        # As duas guardas de reversão são as ÚLTIMAS operações: na reversão rodam PRIMEIRO, antes de
        # a tabela sair. A da origem (A9) e a da regra (0019).
        migrations.RunPython(migrations.RunPython.noop, _guarda_da_0019),
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_origens),
    ]
