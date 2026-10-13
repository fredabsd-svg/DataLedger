# DL-087 (corte 1, frente A): regras de classificação de NF-e do escritório e da empresa.
#
# Migração ADITIVA: uma tabela nova, sem tocar em dado existente. As naturezas gravadas nos itens
# continuam as mesmas chaves de `NaturezaOperacaoNFe`; nada da escrituração efetivada muda.
#
# Reversão (`migrate fiscal 0018`): RECUSA, sem alterar nada, enquanto houver regra gravada. Regra
# é dado do escritório (quem criou, quando, por quê); reverter a apagaria. A guarda é a ÚLTIMA
# operação da lista, então na reversão roda PRIMEIRO, antes de o gatilho ou a tabela saírem.
#
# Correção da rodada 1 (A1 e A13), editada na própria 0019 porque ela não está na `main`:
# - DESATIVAR é REVOGAR. O único UPDATE permitido grava `vigencia_fim` = véspera do início
#   (`vigencia_revogada`, em `apps.fiscal.classificacao`). Vigência vazia: nenhuma nota casa, nem
#   pendente nem futura. Outro fim, por SQL, é recusado.
# - TRUNCATE de tabela COM regra é recusado. Tabela vazia pode ser truncada: é o que o `flush` dos
#   testes transacionais faz em todas as tabelas, e não apaga dado de ninguém. Limite declarado: quem
#   é dono da tabela pode removê-la com DROP, e isso o banco não impede sozinho.
#   Reconferência, R3: por isso um teste `django_db(transaction=True)` que GRAVA regra falha no
#   `flush` do fim. Esse teste precisa revogar e apagar as regras antes de terminar, ou usar o
#   `django_db` comum (transação desfeita, sem flush). O `manage.py flush` também recusa com regra.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_SQL_FUNCAO_REGRA = """
CREATE OR REPLACE FUNCTION fiscal_regra_classificacao_nfe_imutavel()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'regra de classificação de NF-e não pode ser excluída: revogue-a com motivo'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    -- UPDATE só serve à desativação, e só uma vez: a regra desativada não muda mais.
    IF OLD.desativada_em IS NOT NULL THEN
        RAISE EXCEPTION 'regra de classificação de NF-e já desativada não pode ser alterada'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    IF NEW.desativada_em IS NULL THEN
        RAISE EXCEPTION 'regra de classificação de NF-e só pode ser alterada para desativá-la'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    IF (NEW.escritorio_id, NEW.empresa_id, NEW.tipo, NEW.cfop, NEW.ncm, NEW.ncm_modo,
        NEW.cst_csosn, NEW.id_dest, NEW.natureza, NEW.vigencia_inicio, NEW.criada_por_id,
        NEW.criada_em)
       IS DISTINCT FROM
       (OLD.escritorio_id, OLD.empresa_id, OLD.tipo, OLD.cfop, OLD.ncm, OLD.ncm_modo,
        OLD.cst_csosn, OLD.id_dest, OLD.natureza, OLD.vigencia_inicio, OLD.criada_por_id,
        OLD.criada_em) THEN
        RAISE EXCEPTION 'critério, natureza e vigência de regra de classificação não mudam'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    -- A desativação é REVOGAÇÃO (A1): o fim gravado é a véspera do início, e não outra data.
    -- A mesma conta está em `vigencia_revogada` (Python). Se mudar, mude os dois.
    IF NEW.vigencia_fim IS DISTINCT FROM (
        CASE WHEN OLD.vigencia_inicio > DATE '0001-01-01'
             THEN OLD.vigencia_inicio - 1
             ELSE OLD.vigencia_inicio
        END
    ) THEN
        RAISE EXCEPTION 'regra de classificação de NF-e só pode ser desativada por revogação'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_regra_classificacao_nfe_imutavel
    BEFORE UPDATE OR DELETE ON fiscal_regraclassificacaonfe
    FOR EACH ROW EXECUTE FUNCTION fiscal_regra_classificacao_nfe_imutavel();

CREATE OR REPLACE FUNCTION fiscal_regra_classificacao_nfe_sem_truncate()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM fiscal_regraclassificacaonfe) THEN
        RAISE EXCEPTION 'regras de classificação de NF-e gravadas não podem ser truncadas'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_regra_classificacao_nfe_sem_truncate
    BEFORE TRUNCATE ON fiscal_regraclassificacaonfe
    FOR EACH STATEMENT EXECUTE FUNCTION fiscal_regra_classificacao_nfe_sem_truncate();
"""

_SQL_REVERSO_REGRA = """
DROP TRIGGER IF EXISTS trg_regra_classificacao_nfe_sem_truncate ON fiscal_regraclassificacaonfe;
DROP FUNCTION IF EXISTS fiscal_regra_classificacao_nfe_sem_truncate();
DROP TRIGGER IF EXISTS trg_regra_classificacao_nfe_imutavel ON fiscal_regraclassificacaonfe;
DROP FUNCTION IF EXISTS fiscal_regra_classificacao_nfe_imutavel();
"""


def _criar_gatilho_regra(apps, schema_editor):
    """Gatilho em PL/pgSQL: só no PostgreSQL. Fora dele (SQLite de teste de migração) é no-op, como
    as migrações de gatilho de empresas (0010), fiscal (0011) e livro_caixa (0011)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_FUNCAO_REGRA)


def _desfazer_gatilho_regra(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_REVERSO_REGRA)


def _recusar_reversao_com_regras(apps, schema_editor):
    """Guarda da reversão: com regra gravada, a 0019 não reverte (nada sai)."""
    total = apps.get_model("fiscal", "RegraClassificacaoNFe").objects.count()
    if total:
        raise RuntimeError(
            f"Reversão da DL-087 recusada, sem alterar nada: {total} regra(s) de classificação de "
            "NF-e gravada(s). São dados do escritório: registre-os ou trate-os antes de reverter. "
            "Reverter apagaria quem criou cada regra, quando, e a vigência que a desativação fixou."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        ("fiscal", "0018_dl088_cancelamento_da_opcao_de_regime"),
        ("tenancy", "0003_escritorio_endereco_no_timbre_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegraClassificacaoNFe",
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
                    "tipo",
                    models.CharField(
                        choices=[
                            ("saida_propria", "Saída própria (finNFe 1)"),
                            ("devolucao", "Devolução de venda recebida (finNFe 4)"),
                        ],
                        max_length=16,
                        verbose_name="tipo da nota",
                    ),
                ),
                ("cfop", models.CharField(max_length=4, verbose_name="CFOP")),
                (
                    "ncm",
                    models.CharField(blank=True, default="", max_length=8, verbose_name="NCM"),
                ),
                (
                    "ncm_modo",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("exato", "NCM exato (8 dígitos)"),
                            ("prefixo", "NCM por prefixo (2 a 7 dígitos)"),
                        ],
                        default="",
                        max_length=8,
                        verbose_name="modo do NCM",
                    ),
                ),
                (
                    "cst_csosn",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=3,
                        verbose_name="CST ou CSOSN do ICMS",
                    ),
                ),
                (
                    "id_dest",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("1", "1 (operação interna)"),
                            ("2", "2 (interestadual)"),
                            ("3", "3 (exterior)"),
                        ],
                        default="",
                        max_length=1,
                        verbose_name="local de destino (idDest)",
                    ),
                ),
                (
                    "natureza",
                    models.CharField(
                        choices=[
                            (
                                "revenda",
                                "Venda de mercadoria adquirida de terceiros (revenda)",
                            ),
                            ("producao_propria", "Venda de produção própria"),
                            (
                                "revenda_st_substituido",
                                "Revenda com ICMS-ST, substituído",
                            ),
                            (
                                "substituto_st",
                                "Venda como substituto tributário (ST retida na saída)",
                            ),
                            ("monofasico", "Venda de produto monofásico de PIS/Cofins"),
                            (
                                "combustivel",
                                "Revenda de combustíveis para consumo (1,6% no IRPJ)",
                            ),
                            (
                                "combustivel_revenda",
                                "Revenda de combustíveis para revenda (8% no IRPJ)",
                            ),
                            ("exportacao_direta", "Exportação direta"),
                            ("comercial_exportadora", "Venda a comercial exportadora"),
                            ("devolucao_venda", "Devolução de venda recebida"),
                            (
                                "devolucao_combustivel_consumo",
                                "Devolução de venda de combustível para consumo (deduz do 1,6%)",
                            ),
                            (
                                "remessa_retorno",
                                "Remessa, retorno, demonstração, conserto ou mostruário",
                            ),
                            ("transferencia", "Transferência entre estabelecimentos"),
                            (
                                "bonificacao",
                                "Bonificação, doação, brinde ou amostra (incondicional)",
                            ),
                            ("cupom_nfce", "Operação já registrada em NFC-e ou cupom"),
                            (
                                "servico_conjugada",
                                "Prestação de serviço em NF-e conjugada",
                            ),
                            ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                        ],
                        max_length=29,
                        verbose_name="natureza resultante",
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
                (
                    "criada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criada em"),
                ),
                (
                    "desativada_em",
                    models.DateTimeField(blank=True, null=True, verbose_name="desativada em"),
                ),
                (
                    "motivo_desativacao",
                    models.TextField(blank=True, default="", verbose_name="motivo da desativação"),
                ),
                (
                    "criada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criada por",
                    ),
                ),
                (
                    "desativada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="desativada por",
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="regras_de_classificacao_nfe",
                        to="empresas.empresa",
                        verbose_name="empresa (vazio = regra do escritório)",
                    ),
                ),
                (
                    "escritorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="regras_de_classificacao_nfe",
                        to="tenancy.escritorio",
                        verbose_name="escritório",
                    ),
                ),
            ],
            options={
                "verbose_name": "regra de classificação de NF-e",
                "verbose_name_plural": "regras de classificação de NF-e",
                "ordering": ["id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("tipo__in", ["saida_propria", "devolucao"])),
                        name="regra_classificacao_nfe_tipo_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("cfop__regex", "^[0-9]{4}$")),
                        name="regra_classificacao_nfe_cfop_de_4_digitos",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("ncm", ""), ("ncm_modo", "")),
                            models.Q(("ncm_modo", "exato"), ("ncm__regex", "^[0-9]{8}$")),
                            models.Q(("ncm_modo", "prefixo"), ("ncm__regex", "^[0-9]{2,7}$")),
                            _connector="OR",
                        ),
                        name="regra_classificacao_nfe_ncm_coerente",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("cst_csosn", ""),
                            ("cst_csosn__regex", "^[0-9]{2,3}$"),
                            _connector="OR",
                        ),
                        name="regra_classificacao_nfe_cst_csosn_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("id_dest__in", ["", "1", "2", "3"])),
                        name="regra_classificacao_nfe_id_dest_valido",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("natureza", ""), _negated=True),
                            models.Q(("natureza", "ajuste"), _negated=True),
                        ),
                        name="regra_classificacao_nfe_natureza_sem_ajuste",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("desativada_em__isnull", True),
                                ("desativada_por__isnull", True),
                                ("motivo_desativacao", ""),
                            ),
                            models.Q(
                                ("desativada_em__isnull", False),
                                ("desativada_por__isnull", False),
                                ("vigencia_fim__isnull", False),
                                models.Q(("motivo_desativacao", ""), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="regra_classificacao_nfe_desativacao_completa",
                    ),
                ],
            },
        ),
        # Gatilho de imutabilidade: a regra não muda nem se apaga; a desativação (uma única vez) é a
        # única alteração. `save()` já recusa, mas `update()` não passa por ele: o banco é a defesa.
        migrations.RunPython(_criar_gatilho_regra, _desfazer_gatilho_regra),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de a tabela sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_regras),
    ]
