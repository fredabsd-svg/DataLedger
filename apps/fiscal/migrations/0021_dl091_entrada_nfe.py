# DL-091 (frente A1): escrituração das NF-e de ENTRADA (compras), corte 1. Migração ADITIVA.
#
# O que entra:
# - tipo `entrada` na escrituração, com `data_entrada` obrigatória (CHECK
#   `escrituracao_nfe_entrada_com_data_de_entrada`, HI-158);
# - 12 naturezas novas por item (E1 a E11, e `devolucao_compra` de SAÍDA): os CHECKs de SQL
#   `natureza_item_nfe_valida` e `escrituracao_nfe_tipo_valido` são recriados com a lista nova, como
#   na 0012 (CHECK de domínio do banco, além do Python);
# - `cfop_entrada` na natureza do item, com CHECK de que só natureza de entrada o tem;
# - `MemoriaEntradaItemNFe`: a memória de crédito e de impostos de cada item, gravada na efetivação.
#   Gatilho próprio (como a origem da 0020): INSERT só com a escrituração em rascunho; UPDATE nunca;
#   DELETE só com rascunho. A efetivação grava a memória ANTES de mudar o estado.
#
# Reversão (`migrate fiscal 0020`): RECUSA, sem alterar nada, enquanto houver escrituração de
# entrada
# (qualquer estado) ou natureza de entrada / devolução de compra gravada. A guarda roda PRIMEIRO na
# reversão (é a última operação da ida), como nas 0019 e 0020. Sem linha nova, a reversão restaura
# os CHECKs antigos e remove o gatilho, a tabela e as colunas.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from importlib import import_module

# Guardas de reversão das migrações de BAIXO, na ordem em que a reversão delas rodaria (de cima para
# baixo). Cada uma recusa com o próprio motivo. Todas são chamadas ANTES de qualquer alteração desta
# migração. O Django reverte cada migração em transação própria: sem isto, a 0021 desfazia o esquema
# (colunas, CHECKs, gatilho) e só depois uma guarda de baixo recusava, e o banco ficava inconsistente
# com o código. (Correção da rodada 1 da DL-091: os testes de reversão das 0013 e 0014 pegaram isso.)
_GUARDAS_DE_BAIXO = (
    ("0020_dl087_origem_da_natureza_confirmada", "_recusar_reversao_com_origens"),
    ("0019_dl087_regra_de_classificacao_nfe", "_recusar_reversao_com_regras"),
    ("0018_dl088_cancelamento_da_opcao_de_regime", "_recusar_reversao_com_dados_do_contador"),
    ("0017_dl088_opcao_regime_ibs_cbs_e_ipi_mantido", "_recusar_reversao_com_dado_da_virada"),
    ("0016_dl084_escopo_do_escritorio_feriados", "_recusar_reversao_com_dados_do_contador"),
    ("0015_dl084_rotina_do_presumido", "_recusar_reversao_com_dados_do_contador"),
    ("0014_dl082_pre_das_comercio", "_conferir_reversao"),
    ("0012_dl083_combustivel_revenda", "_recusar_reversao_com_natureza_nova"),
)

# Lista de naturezas ANTES desta migração (17 valores de `NaturezaOperacaoNFe`), e a lista de tipos.
# Fixas aqui: migração não importa o modelo vivo, que pode mudar depois.
_NATUREZAS_ANTES = (
    "revenda",
    "producao_propria",
    "revenda_st_substituido",
    "substituto_st",
    "monofasico",
    "combustivel",
    "combustivel_revenda",
    "exportacao_direta",
    "comercial_exportadora",
    "devolucao_venda",
    "devolucao_combustivel_consumo",
    "remessa_retorno",
    "transferencia",
    "bonificacao",
    "cupom_nfce",
    "servico_conjugada",
    "ajuste",
)
_NATUREZAS_NOVAS_DA_0021 = (
    "entrada_comercializacao",
    "entrada_industrializacao",
    "entrada_st",
    "entrada_uso_consumo",
    "entrada_ativo",
    "entrada_combustivel_revenda",
    "entrada_combustivel_consumo",
    "entrada_transferencia",
    "entrada_bonificacao",
    "entrada_remessa_retorno",
    "entrada_servico",
    "devolucao_compra",
)
_TIPOS_ANTES = ("saida_propria", "devolucao", "ajuste")
_TIPOS_DEPOIS = _TIPOS_ANTES + ("entrada",)


def _lista(valores) -> str:
    return ", ".join(f"'{v}'" for v in valores)


_SQL_CHECKS_NOVOS = f"""
ALTER TABLE fiscal_naturezaitemnfe DROP CONSTRAINT IF EXISTS natureza_item_nfe_valida;
ALTER TABLE fiscal_naturezaitemnfe ADD CONSTRAINT natureza_item_nfe_valida
    CHECK (natureza IN ('', {_lista(_NATUREZAS_ANTES + _NATUREZAS_NOVAS_DA_0021)}));
ALTER TABLE fiscal_escrituracaonfe DROP CONSTRAINT IF EXISTS escrituracao_nfe_tipo_valido;
ALTER TABLE fiscal_escrituracaonfe ADD CONSTRAINT escrituracao_nfe_tipo_valido
    CHECK (tipo IN ({_lista(_TIPOS_DEPOIS)}));
"""

_SQL_CHECKS_ANTIGOS = f"""
ALTER TABLE fiscal_naturezaitemnfe DROP CONSTRAINT IF EXISTS natureza_item_nfe_valida;
ALTER TABLE fiscal_naturezaitemnfe ADD CONSTRAINT natureza_item_nfe_valida
    CHECK (natureza IN ('', {_lista(_NATUREZAS_ANTES)}));
ALTER TABLE fiscal_escrituracaonfe DROP CONSTRAINT IF EXISTS escrituracao_nfe_tipo_valido;
ALTER TABLE fiscal_escrituracaonfe ADD CONSTRAINT escrituracao_nfe_tipo_valido
    CHECK (tipo IN ({_lista(_TIPOS_ANTES)}));
"""

# Gatilho da memória. Só PostgreSQL (PL/pgSQL): fora dele, vale a regra do serviço, como nas outras.
_SQL_FUNCAO_MEMORIA = """
CREATE OR REPLACE FUNCTION fiscal_memoria_entrada_imutavel()
RETURNS trigger AS $$
DECLARE
    v_estado text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'memória de entrada de NF-e não muda depois de gravada'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'memoria_entrada_imutavel_depois_de_efetivada';
    END IF;
    IF TG_OP = 'INSERT' THEN
        SELECT e.estado INTO v_estado
          FROM fiscal_naturezaitemnfe n
          JOIN fiscal_escrituracaonfe e ON e.id = n.escrituracao_id
         WHERE n.id = NEW.natureza_item_id;
        IF v_estado IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'memória de entrada só é gravada com a escrituração em rascunho'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'memoria_entrada_imutavel_depois_de_efetivada';
        END IF;
        RETURN NEW;
    END IF;
    -- DELETE: a cascata de uma escrituração em rascunho passa; fora de rascunho, não.
    SELECT e.estado INTO v_estado
      FROM fiscal_naturezaitemnfe n
      JOIN fiscal_escrituracaonfe e ON e.id = n.escrituracao_id
     WHERE n.id = OLD.natureza_item_id;
    IF v_estado IS NOT NULL AND v_estado <> 'rascunho' THEN
        RAISE EXCEPTION 'memória de entrada de NF-e efetivada ou estornada não pode ser excluída'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'memoria_entrada_imutavel_depois_de_efetivada';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_memoria_entrada_imutavel
    BEFORE INSERT OR UPDATE OR DELETE ON fiscal_memoriaentradaitemnfe
    FOR EACH ROW EXECUTE FUNCTION fiscal_memoria_entrada_imutavel();
"""

_SQL_DESFAZER_MEMORIA = """
DROP TRIGGER IF EXISTS trg_memoria_entrada_imutavel ON fiscal_memoriaentradaitemnfe;
DROP FUNCTION IF EXISTS fiscal_memoria_entrada_imutavel();
"""


def _criar_checks_e_gatilho(apps, schema_editor):
    """Só PostgreSQL: CHECKs e gatilho são SQL de PostgreSQL. Fora dele, vale o serviço."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_CHECKS_NOVOS)
    schema_editor.execute(_SQL_FUNCAO_MEMORIA)


def _desfazer_checks_e_gatilho(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_DESFAZER_MEMORIA)
    schema_editor.execute(_SQL_CHECKS_ANTIGOS)


def _recusar_reversao_com_entrada(apps, schema_editor):
    """Guarda da reversão (DL-091): compra escriturada é fato de auditoria, e a reversão a apagaria.

    Primeiro chama as guardas da 0020 e da 0019, na mesma ordem em que a reversão delas rodaria. O
    Django reverte cada migração em transação própria: sem isto, a 0021 desfaria o esquema (coluna
    `data_entrada`, CHECKs) e só depois a 0020 recusaria, deixando o banco inconsistente com o código.
    Com as guardas antes, a recusa acontece antes de qualquer alteração (como a DL-087 exige).
    """
    for modulo, nome in _GUARDAS_DE_BAIXO:
        guarda = getattr(import_module(f"apps.fiscal.migrations.{modulo}"), nome)
        guarda(apps, schema_editor)
    # Depois das guardas da 0019 e da 0020: esta é a própria recusa da DL-091. Recusa por QUALQUER
    # estado da escrituração de entrada (rascunho inclusive: a compra já foi recebida e classificada).
    # Também recusa natureza de entrada ou de devolução de compra gravada, porque o CHECK antigo não
    # a aceita.
    escrituracoes = (
        apps.get_model("fiscal", "EscrituracaoNFe").objects.filter(tipo="entrada").count()
    )
    naturezas = (
        apps.get_model("fiscal", "NaturezaItemNFe")
        .objects.filter(natureza__in=_NATUREZAS_NOVAS_DA_0021)
        .count()
    )
    if escrituracoes or naturezas:
        raise RuntimeError(
            "Reversão da DL-091 recusada, sem alterar nada: "
            f"{escrituracoes} escrituração(ões) de entrada e {naturezas} natureza(s) de entrada ou "
            "de devolução de compra gravada(s). Elas dizem de onde veio cada compra escriturada: "
            "registre-as ou trate-as antes de reverter."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0016_dl074_data_abertura_cnpj"),
        ("fiscal", "0020_dl087_origem_da_natureza_confirmada"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemoriaEntradaItemNFe",
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
                    "marca_credito",
                    models.CharField(
                        choices=[
                            (
                                "credito_destacado",
                                "Crédito destacado: elegível (LC 87, art. 20)",
                            ),
                            (
                                "credito_limitado_ao_informado",
                                "Crédito limitado ao vCredICMSSN informado pelo fornecedor do "
                                "Simples (LC 123, art. 23)",
                            ),
                            (
                                "sem_credito_sem_pcredsn",
                                "Sem crédito: fornecedor do Simples sem pCredSN "
                                "(LC 123, art. 23, § 4º)",
                            ),
                            (
                                "vedado_ate_2032",
                                "Crédito vedado até 31/12/2032 (LC 87, art. 33, I)",
                            ),
                            (
                                "um_quarenta_oitavo",
                                "Ativo: 1/48 por mês, CIAP (LC 87, art. 20, § 5º): etapa do ICMS",
                            ),
                            (
                                "st_retido_sem_credito",
                                "ICMS-ST retido: sem crédito, compõe o custo",
                            ),
                            (
                                "monofasico_sem_credito",
                                "ICMS monofásico (LC 192): sem crédito nem débito",
                            ),
                            ("nao_se_credita", "A natureza não gera crédito"),
                            ("sem_destaque", "A nota não destaca ICMS próprio"),
                            (
                                "sem_credito_pleno_pelo_cst",
                                "CST/CSOSN sem direito a crédito pleno: conferir "
                                "(LC 87, art. 20, § 1º)",
                            ),
                            (
                                "a_conferir",
                                "A conferir: a regra do caso não foi lida ou falta o dado",
                            ),
                        ],
                        max_length=32,
                        verbose_name="marca de crédito",
                    ),
                ),
                (
                    "credito_elegivel",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="crédito elegível (valor que a regra admite)",
                    ),
                ),
                (
                    "cst",
                    models.CharField(
                        blank=True, default="", max_length=2, verbose_name="CST do ICMS"
                    ),
                ),
                (
                    "csosn",
                    models.CharField(blank=True, default="", max_length=3, verbose_name="CSOSN"),
                ),
                (
                    "v_bc",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="BC do ICMS (vBC)",
                    ),
                ),
                (
                    "p_icms",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=7,
                        null=True,
                        verbose_name="alíquota do ICMS (pICMS)",
                    ),
                ),
                (
                    "v_icms",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS destacado (vICMS)",
                    ),
                ),
                (
                    "p_cred_sn",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=7,
                        null=True,
                        verbose_name="alíquota do crédito do Simples (pCredSN)",
                    ),
                ),
                (
                    "v_cred_icms_sn",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="crédito do Simples (vCredICMSSN)",
                    ),
                ),
                (
                    "v_bc_st_ret",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="BC do ICMS-ST retido (vBCSTRet)",
                    ),
                ),
                (
                    "v_icms_st_ret",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS-ST retido (vICMSSTRet)",
                    ),
                ),
                (
                    "v_fcp",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="FCP (vFCP)",
                    ),
                ),
                (
                    "cst_ipi",
                    models.CharField(
                        blank=True, default="", max_length=2, verbose_name="CST do IPI"
                    ),
                ),
                (
                    "v_ipi",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="IPI (vIPI)",
                    ),
                ),
                (
                    "cst_pis",
                    models.CharField(
                        blank=True, default="", max_length=2, verbose_name="CST do PIS"
                    ),
                ),
                (
                    "v_pis",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="PIS (vPIS)",
                    ),
                ),
                (
                    "cst_cofins",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2,
                        verbose_name="CST da Cofins",
                    ),
                ),
                (
                    "v_cofins",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="Cofins (vCOFINS)",
                    ),
                ),
                (
                    "avisos",
                    models.JSONField(blank=True, default=list, verbose_name="avisos da entrada"),
                ),
                (
                    "gravada_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="gravada em"),
                ),
            ],
            options={
                "verbose_name": "memória de entrada de item de NF-e",
                "verbose_name_plural": "memórias de entrada de itens de NF-e",
            },
        ),
        migrations.AddField(
            model_name="escrituracaonfe",
            name="data_entrada",
            field=models.DateField(blank=True, null=True, verbose_name="data de entrada"),
        ),
        migrations.AddField(
            model_name="naturezaitemnfe",
            name="cfop_entrada",
            field=models.CharField(
                blank=True,
                default="",
                max_length=4,
                verbose_name="CFOP de entrada (confirmado)",
            ),
        ),
        migrations.AlterField(
            model_name="escrituracaonfe",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("saida_propria", "Saída própria (finNFe 1)"),
                    ("devolucao", "Devolução de venda recebida (finNFe 4)"),
                    ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                    ("entrada", "Entrada de compra (NF-e de terceiro, finNFe 1)"),
                ],
                max_length=16,
                verbose_name="tipo da escrituração",
            ),
        ),
        migrations.AlterField(
            model_name="naturezaitemnfe",
            name="natureza",
            field=models.CharField(
                blank=True,
                choices=[
                    ("revenda", "Venda de mercadoria adquirida de terceiros (revenda)"),
                    ("producao_propria", "Venda de produção própria"),
                    ("revenda_st_substituido", "Revenda com ICMS-ST, substituído"),
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
                    ("servico_conjugada", "Prestação de serviço em NF-e conjugada"),
                    ("entrada_comercializacao", "E1 · Compra para comercialização"),
                    ("entrada_industrializacao", "E2 · Compra para industrialização"),
                    ("entrada_st", "E3 · Compra com ICMS-ST (substituído)"),
                    ("entrada_uso_consumo", "E4 · Compra para uso ou consumo"),
                    ("entrada_ativo", "E5 · Compra para o ativo imobilizado"),
                    (
                        "entrada_combustivel_revenda",
                        "E6 · Compra de combustível ou lubrificante para revenda",
                    ),
                    (
                        "entrada_combustivel_consumo",
                        "E7 · Combustível ou lubrificante para consumo próprio",
                    ),
                    ("entrada_transferencia", "E8 · Transferência recebida"),
                    (
                        "entrada_bonificacao",
                        "E9 · Bonificação, doação ou amostra recebida",
                    ),
                    (
                        "entrada_remessa_retorno",
                        "E10 · Remessa, retorno, consignação ou conserto",
                    ),
                    ("entrada_servico", "E11 · Compra para prestação de serviço"),
                    (
                        "devolucao_compra",
                        "Devolução de compra (saída própria, indDevol 1)",
                    ),
                    ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                ],
                default="",
                max_length=29,
                verbose_name="natureza confirmada",
            ),
        ),
        migrations.AlterField(
            model_name="regraclassificacaonfe",
            name="natureza",
            field=models.CharField(
                choices=[
                    ("revenda", "Venda de mercadoria adquirida de terceiros (revenda)"),
                    ("producao_propria", "Venda de produção própria"),
                    ("revenda_st_substituido", "Revenda com ICMS-ST, substituído"),
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
                    ("servico_conjugada", "Prestação de serviço em NF-e conjugada"),
                    ("entrada_comercializacao", "E1 · Compra para comercialização"),
                    ("entrada_industrializacao", "E2 · Compra para industrialização"),
                    ("entrada_st", "E3 · Compra com ICMS-ST (substituído)"),
                    ("entrada_uso_consumo", "E4 · Compra para uso ou consumo"),
                    ("entrada_ativo", "E5 · Compra para o ativo imobilizado"),
                    (
                        "entrada_combustivel_revenda",
                        "E6 · Compra de combustível ou lubrificante para revenda",
                    ),
                    (
                        "entrada_combustivel_consumo",
                        "E7 · Combustível ou lubrificante para consumo próprio",
                    ),
                    ("entrada_transferencia", "E8 · Transferência recebida"),
                    (
                        "entrada_bonificacao",
                        "E9 · Bonificação, doação ou amostra recebida",
                    ),
                    (
                        "entrada_remessa_retorno",
                        "E10 · Remessa, retorno, consignação ou conserto",
                    ),
                    ("entrada_servico", "E11 · Compra para prestação de serviço"),
                    (
                        "devolucao_compra",
                        "Devolução de compra (saída própria, indDevol 1)",
                    ),
                    ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                ],
                max_length=29,
                verbose_name="natureza resultante",
            ),
        ),
        migrations.AddConstraint(
            model_name="escrituracaonfe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("tipo", "entrada"), _negated=True),
                    ("data_entrada__isnull", False),
                    _connector="OR",
                ),
                name="escrituracao_nfe_entrada_com_data_de_entrada",
            ),
        ),
        migrations.AddConstraint(
            model_name="naturezaitemnfe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("cfop_entrada", ""),
                    (
                        "natureza__in",
                        [
                            "entrada_ativo",
                            "entrada_bonificacao",
                            "entrada_combustivel_consumo",
                            "entrada_combustivel_revenda",
                            "entrada_comercializacao",
                            "entrada_industrializacao",
                            "entrada_remessa_retorno",
                            "entrada_servico",
                            "entrada_st",
                            "entrada_transferencia",
                            "entrada_uso_consumo",
                        ],
                    ),
                    _connector="OR",
                ),
                name="natureza_item_nfe_cfop_entrada_so_na_entrada",
            ),
        ),
        migrations.AddField(
            model_name="memoriaentradaitemnfe",
            name="natureza_item",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="memoria_de_entrada",
                to="fiscal.naturezaitemnfe",
                verbose_name="natureza do item",
            ),
        ),
        migrations.AddConstraint(
            model_name="memoriaentradaitemnfe",
            constraint=models.UniqueConstraint(
                fields=("natureza_item",), name="memoria_entrada_unica_por_item"
            ),
        ),
        # CHECKs de domínio (listas novas) e gatilho da memória. Depois das tabelas e colunas.
        migrations.RunPython(_criar_checks_e_gatilho, _desfazer_checks_e_gatilho),
        # A guarda é a ÚLTIMA: na reversão roda PRIMEIRO, antes de qualquer coluna ou tabela sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_entrada),
    ]
