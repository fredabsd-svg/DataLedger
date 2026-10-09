# DL-081 (frente A), migração ADITIVA: tabelas da escrituração das NF-e de saída e da devolução.
#
# Criação das quatro tabelas novas (escrituração, itens, leitura dos itens e natureza por item)
# e, em seguida, GATILHOS de PostgreSQL com o mesmo desenho da DL-072 (migração 0002):
#
# 1. `fiscal_escrituracao_nfe_imutavel`: transições permitidas, e só estas: rascunho -> rascunho
#    ou efetivada; efetivada -> estornada, e então SÓ as colunas do estorno mudam. Estornada não
#    muda mais. DELETE só de rascunho. Além disso, rascunho -> efetivada exige que TODO item tenha
#    natureza (nenhuma linha vazia) e que exista ao menos uma: a efetivação sem natureza é recusada
#    pelo banco, mesmo que o Python falhe.
# 2. `fiscal_natureza_item_nfe_so_em_rascunho`: INSERT, UPDATE e DELETE de natureza por item só
#    quando a escrituração-pai está em rascunho. Efetivada ou estornada: nada muda,
#    nem por SQL direto.
# 3. CHECK de domínio: a natureza por item e o tipo da escrituração só aceitam valores do catálogo.
# 4. `fiscal_itens_nfe_imutaveis` (correção da rodada 1, A3): INSERT, UPDATE e DELETE em
#    `fiscal_itemnfe` e em `fiscal_leituraitensnfe` são recusados quando a NOTA tem escrituração
#    efetivada ou estornada. A receita do Simples e o RBT12 leem `ItemNFe.receita_bruta_item` ao
#    vivo, então o item é o dado que o banco precisa proteger. Sem escrituração assim, a releitura
#    da leitura (troca de versão do leitor) continua possível.
#
# Limite declarado (como na DL-052 e na DL-072): TRUNCATE não aciona gatilho de linha, e quem é
# dono da tabela está fora do que o banco impede sozinho. Só PostgreSQL: em outro banco, vale a
# guarda do Python, e a migração não cria os gatilhos.
#
# Reversão: `migrate fiscal 0010` remove as tabelas e as funções (ver `_desfazer_gatilhos`).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Valores do catálogo de natureza e de tipo. Espelham `NaturezaOperacaoNFe` e
# `TipoEscrituracaoNFe` (models.py). Ficam literais aqui: a migração não importa o código da
# aplicação, que pode mudar depois.
_NATUREZAS = (
    "revenda",
    "producao_propria",
    "revenda_st_substituido",
    "substituto_st",
    "monofasico",
    "combustivel",
    "exportacao_direta",
    "comercial_exportadora",
    "devolucao_venda",
    "remessa_retorno",
    "transferencia",
    "bonificacao",
    "cupom_nfce",
    "servico_conjugada",
    "ajuste",
)
_TIPOS = ("saida_propria", "devolucao", "ajuste")


_LISTA_NATUREZAS = ", ".join(f"'{n}'" for n in _NATUREZAS)
_LISTA_TIPOS = ", ".join(f"'{t}'" for t in _TIPOS)

_SQL_FUNCAO_ESCRITURACAO = """
CREATE OR REPLACE FUNCTION fiscal_escrituracao_nfe_imutavel()
RETURNS trigger AS $$
DECLARE
    colunas_do_estorno text[] := ARRAY[
        'estado', 'estornada_em', 'estornada_por_id', 'motivo_estorno'
    ];
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.estado <> 'rascunho' THEN
            RAISE EXCEPTION 'escrituração de NF-e efetivada ou estornada não pode ser excluída'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'escrituracao_nfe_imutavel_depois_de_efetivada';
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.estado = 'rascunho' AND NEW.estado = 'rascunho' THEN
        RETURN NEW;
    END IF;

    IF OLD.estado = 'rascunho' AND NEW.estado = 'efetivada' THEN
        -- Efetivar exige itens e natureza confirmada em TODOS os itens (HI-118). A conferência de
        -- valores (receita x vNF) é do Python, com a mensagem dos valores; aqui fica a invariante.
        IF NOT EXISTS (
               SELECT 1 FROM fiscal_naturezaitemnfe WHERE escrituracao_id = NEW.id
           ) OR EXISTS (
               SELECT 1 FROM fiscal_naturezaitemnfe
                WHERE escrituracao_id = NEW.id AND natureza = ''
           ) THEN
            RAISE EXCEPTION 'escrituração de NF-e sem natureza confirmada em todos os itens'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'escrituracao_nfe_natureza_em_todos_os_itens';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.estado = 'efetivada' AND NEW.estado = 'estornada' THEN
        IF (to_jsonb(NEW) - colunas_do_estorno)
           IS DISTINCT FROM (to_jsonb(OLD) - colunas_do_estorno) THEN
            RAISE EXCEPTION
                'escrituração de NF-e efetivada só pode ser estornada; os dados do ato não mudam'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'escrituracao_nfe_imutavel_depois_de_efetivada';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.estado = 'efetivada' AND NEW.estado = 'efetivada' THEN
        IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
            RAISE EXCEPTION
                'escrituração de NF-e efetivada não pode ser alterada; estorne com motivo'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'escrituracao_nfe_imutavel_depois_de_efetivada';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'transição de estado da escrituração de NF-e não permitida: % -> %',
        OLD.estado, NEW.estado
        USING ERRCODE = '23514',
              CONSTRAINT = 'escrituracao_nfe_imutavel_depois_de_efetivada';
END;
$$ LANGUAGE plpgsql;
"""

_SQL_GATILHO_ESCRITURACAO = """
CREATE TRIGGER trg_escrituracao_nfe_imutavel
BEFORE UPDATE OR DELETE ON fiscal_escrituracaonfe
FOR EACH ROW EXECUTE FUNCTION fiscal_escrituracao_nfe_imutavel();
"""

_SQL_FUNCAO_NATUREZA_ITEM = """
CREATE OR REPLACE FUNCTION fiscal_natureza_item_nfe_so_em_rascunho()
RETURNS trigger AS $$
DECLARE
    v_estado text;
BEGIN
    -- UPDATE e DELETE conferem o pai ANTIGO; INSERT e UPDATE conferem o pai NOVO.
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT estado INTO v_estado FROM fiscal_escrituracaonfe WHERE id = OLD.escrituracao_id;
        IF v_estado IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION
                'natureza de item de escrituração de NF-e efetivada ou estornada não muda'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'natureza_item_nfe_so_em_rascunho';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT estado INTO v_estado FROM fiscal_escrituracaonfe WHERE id = NEW.escrituracao_id;
        IF v_estado IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION
                'natureza de item de escrituração de NF-e efetivada ou estornada não muda'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'natureza_item_nfe_so_em_rascunho';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
"""

_SQL_GATILHO_NATUREZA_ITEM = """
CREATE TRIGGER trg_natureza_item_nfe_so_em_rascunho
BEFORE INSERT OR UPDATE OR DELETE ON fiscal_naturezaitemnfe
FOR EACH ROW EXECUTE FUNCTION fiscal_natureza_item_nfe_so_em_rascunho();
"""

_SQL_FUNCAO_ITENS_NFE = """
CREATE OR REPLACE FUNCTION fiscal_itens_nfe_imutaveis()
RETURNS trigger AS $$
BEGIN
    -- UPDATE confere a nota ANTIGA e a NOVA: trocar o documento de um item também é alteração.
    IF TG_OP IN ('UPDATE', 'DELETE') AND EXISTS (
           SELECT 1
             FROM fiscal_escrituracaonfe e
             JOIN fiscal_vinculonfeempresa v ON v.id = e.vinculo_id
            WHERE v.documento_id = OLD.documento_id
              AND e.estado IN ('efetivada', 'estornada')
       ) THEN
        RAISE EXCEPTION
            'item ou leitura de NF-e com escrituração efetivada ou estornada não pode ser alterada'
            USING ERRCODE = '23514',
                  CONSTRAINT = TG_TABLE_NAME || '_imutavel_depois_de_efetivada';
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
           SELECT 1
             FROM fiscal_escrituracaonfe e
             JOIN fiscal_vinculonfeempresa v ON v.id = e.vinculo_id
            WHERE v.documento_id = NEW.documento_id
              AND e.estado IN ('efetivada', 'estornada')
       ) THEN
        RAISE EXCEPTION
            'item ou leitura de NF-e com escrituração efetivada ou estornada não pode ser alterada'
            USING ERRCODE = '23514',
                  CONSTRAINT = TG_TABLE_NAME || '_imutavel_depois_de_efetivada';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_SQL_GATILHOS_ITENS_NFE = """
CREATE TRIGGER trg_item_nfe_imutavel
BEFORE INSERT OR UPDATE OR DELETE ON fiscal_itemnfe
FOR EACH ROW EXECUTE FUNCTION fiscal_itens_nfe_imutaveis();
CREATE TRIGGER trg_leitura_itens_nfe_imutavel
BEFORE INSERT OR UPDATE OR DELETE ON fiscal_leituraitensnfe
FOR EACH ROW EXECUTE FUNCTION fiscal_itens_nfe_imutaveis();
"""

_SQL_CHECKS = (
    "ALTER TABLE fiscal_naturezaitemnfe ADD CONSTRAINT natureza_item_nfe_valida "
    f"CHECK (natureza IN ('', {_LISTA_NATUREZAS}))",
    "ALTER TABLE fiscal_escrituracaonfe ADD CONSTRAINT escrituracao_nfe_tipo_valido "
    f"CHECK (tipo IN ({_LISTA_TIPOS}))",
)

_SQL_DESFAZER = """
ALTER TABLE fiscal_escrituracaonfe DROP CONSTRAINT IF EXISTS escrituracao_nfe_tipo_valido;
ALTER TABLE fiscal_naturezaitemnfe DROP CONSTRAINT IF EXISTS natureza_item_nfe_valida;
DROP TRIGGER IF EXISTS trg_natureza_item_nfe_so_em_rascunho ON fiscal_naturezaitemnfe;
DROP TRIGGER IF EXISTS trg_escrituracao_nfe_imutavel ON fiscal_escrituracaonfe;
DROP TRIGGER IF EXISTS trg_item_nfe_imutavel ON fiscal_itemnfe;
DROP TRIGGER IF EXISTS trg_leitura_itens_nfe_imutavel ON fiscal_leituraitensnfe;
DROP FUNCTION IF EXISTS fiscal_itens_nfe_imutaveis();
DROP FUNCTION IF EXISTS fiscal_natureza_item_nfe_so_em_rascunho();
DROP FUNCTION IF EXISTS fiscal_escrituracao_nfe_imutavel();
"""


def _criar_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in (
        _SQL_FUNCAO_ESCRITURACAO,
        _SQL_GATILHO_ESCRITURACAO,
        _SQL_FUNCAO_NATUREZA_ITEM,
        _SQL_GATILHO_NATUREZA_ITEM,
        _SQL_FUNCAO_ITENS_NFE,
        _SQL_GATILHOS_ITENS_NFE,
        *_SQL_CHECKS,
    ):
        schema_editor.execute(sql, params=None)


def _desfazer_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_DESFAZER, params=None)


class Migration(migrations.Migration):
    dependencies = [
        # 0007 e não a última (0016): as tabelas da NF-e só precisam de `empresas_empresa` e da
        # chave dela (mesmo critério da `fiscal.0002`). Depender da última faz QUALQUER migração de
        # teste que reverta `empresas` abaixo dela (test_dl038, test_dl039, test_dl041,
        # test_dl076_b8) desfazer estas tabelas, e elas não voltam. Medido na suíte completa: os
        # testes de concorrência da receita, que vinham depois, falharam com "relation does not
        # exist", porque a composição passou a ler a NF-e em todo cálculo.
        ("empresas", "0007_bl54_cnpj_check_constraint_formato"),
        ("fiscal", "0010_dl080_nfe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EscrituracaoNFe",
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
                            ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                        ],
                        max_length=16,
                        verbose_name="tipo da escrituração",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("rascunho", "Rascunho"),
                            ("efetivada", "Efetivada"),
                            ("estornada", "Estornada"),
                        ],
                        default="rascunho",
                        max_length=12,
                        verbose_name="estado",
                    ),
                ),
                (
                    "competencia",
                    models.DateField(
                        blank=True, null=True, verbose_name="competência (mês de dhEmi)"
                    ),
                ),
                (
                    "data_emissao",
                    models.DateField(blank=True, null=True, verbose_name="data de emissão"),
                ),
                (
                    "valor_nf",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="valor da nota (vNF)",
                    ),
                ),
                (
                    "soma_itens",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="soma da receita dos itens",
                    ),
                ),
                (
                    "receita_bruta",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="receita bruta da escrituração",
                    ),
                ),
                (
                    "devolucao",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="devolução de venda",
                    ),
                ),
                (
                    "efetivada_em",
                    models.DateTimeField(blank=True, null=True, verbose_name="efetivada em"),
                ),
                (
                    "estornada_em",
                    models.DateTimeField(blank=True, null=True, verbose_name="estornada em"),
                ),
                (
                    "motivo_estorno",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="motivo do estorno",
                    ),
                ),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criada por",
                    ),
                ),
                (
                    "efetivada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="efetivada por",
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="escrituracoes_nfe",
                        to="empresas.empresa",
                        verbose_name="empresa",
                    ),
                ),
                (
                    "estornada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="estornada por",
                    ),
                ),
                (
                    "vinculo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="escrituracoes_nfe",
                        to="fiscal.vinculonfeempresa",
                        verbose_name="vínculo de NF-e com empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "escrituração de NF-e",
                "verbose_name_plural": "escriturações de NF-e",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="ItemNFe",
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
                    "n_item",
                    models.PositiveSmallIntegerField(verbose_name="número do item (nItem)"),
                ),
                (
                    "c_prod",
                    models.CharField(max_length=60, verbose_name="código do produto (cProd)"),
                ),
                (
                    "x_prod",
                    models.CharField(max_length=120, verbose_name="descrição do produto (xProd)"),
                ),
                ("ncm", models.CharField(max_length=8, verbose_name="NCM")),
                (
                    "cest",
                    models.CharField(blank=True, default="", max_length=7, verbose_name="CEST"),
                ),
                ("cfop", models.CharField(max_length=4, verbose_name="CFOP")),
                (
                    "u_com",
                    models.CharField(max_length=6, verbose_name="unidade comercial (uCom)"),
                ),
                (
                    "q_com",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=15,
                        verbose_name="quantidade comercial (qCom)",
                    ),
                ),
                (
                    "v_un_com",
                    models.DecimalField(
                        decimal_places=10,
                        max_digits=21,
                        verbose_name="valor unitário comercial (vUnCom)",
                    ),
                ),
                (
                    "v_prod",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        verbose_name="valor do item (vProd)",
                    ),
                ),
                (
                    "v_desc",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="desconto do item (vDesc)",
                    ),
                ),
                (
                    "v_frete",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="frete do item (vFrete)",
                    ),
                ),
                (
                    "v_seg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="seguro do item (vSeg)",
                    ),
                ),
                (
                    "v_outro",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="outras despesas (vOutro)",
                    ),
                ),
                (
                    "ind_tot",
                    models.CharField(max_length=1, verbose_name="compõe o total da NF-e (indTot)"),
                ),
                (
                    "c_benef",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=10,
                        verbose_name="código de benefício fiscal (cBenef)",
                    ),
                ),
                (
                    "orig",
                    models.CharField(
                        blank=True,
                        max_length=1,
                        null=True,
                        verbose_name="origem da mercadoria (orig)",
                    ),
                ),
                (
                    "cst",
                    models.CharField(
                        blank=True, max_length=2, null=True, verbose_name="CST do ICMS"
                    ),
                ),
                (
                    "csosn",
                    models.CharField(blank=True, max_length=3, null=True, verbose_name="CSOSN"),
                ),
                (
                    "mod_bc",
                    models.CharField(
                        blank=True,
                        max_length=1,
                        null=True,
                        verbose_name="modalidade da BC do ICMS (modBC)",
                    ),
                ),
                (
                    "v_bc",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="BC do ICMS (vBC)",
                    ),
                ),
                (
                    "p_icms",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=7,
                        null=True,
                        verbose_name="alíquota do ICMS (pICMS)",
                    ),
                ),
                (
                    "v_icms",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS (vICMS)",
                    ),
                ),
                (
                    "v_icms_deson",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS desonerado (vICMSDeson)",
                    ),
                ),
                (
                    "ind_deduz_deson",
                    models.CharField(
                        blank=True,
                        max_length=1,
                        null=True,
                        verbose_name="indicador de dedução do ICMS desonerado (indDeduzDeson)",
                    ),
                ),
                (
                    "mot_des_icms",
                    models.CharField(
                        blank=True,
                        max_length=2,
                        null=True,
                        verbose_name="motivo da desoneração (motDesICMS)",
                    ),
                ),
                (
                    "mod_bc_st",
                    models.CharField(
                        blank=True,
                        max_length=1,
                        null=True,
                        verbose_name="modalidade da BC do ST (modBCST)",
                    ),
                ),
                (
                    "v_bc_st",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="BC do ICMS-ST (vBCST)",
                    ),
                ),
                (
                    "p_icms_st",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=7,
                        null=True,
                        verbose_name="alíquota do ICMS-ST (pICMSST)",
                    ),
                ),
                (
                    "v_icms_st",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS-ST (vICMSST)",
                    ),
                ),
                (
                    "v_bc_st_ret",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="BC do ST retido (vBCSTRet)",
                    ),
                ),
                (
                    "v_icms_st_ret",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS-ST retido (vICMSSTRet)",
                    ),
                ),
                (
                    "p_cred_sn",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=7,
                        null=True,
                        verbose_name="alíquota do crédito do Simples (pCredSN)",
                    ),
                ),
                (
                    "v_cred_icms_sn",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="crédito do Simples (vCredICMSSN)",
                    ),
                ),
                (
                    "v_fcp",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="fundo de combate à pobreza (vFCP)",
                    ),
                ),
                (
                    "v_fcp_st",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="FCP do ST (vFCPST)",
                    ),
                ),
                (
                    "v_icms_ufdest",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="partilha do ICMS, UF de destino (vICMSUFDest)",
                    ),
                ),
                (
                    "cst_ipi",
                    models.CharField(
                        blank=True, max_length=2, null=True, verbose_name="CST do IPI"
                    ),
                ),
                (
                    "v_ipi",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="IPI do item (vIPI)",
                    ),
                ),
                (
                    "cst_pis",
                    models.CharField(
                        blank=True, max_length=2, null=True, verbose_name="CST do PIS"
                    ),
                ),
                (
                    "v_pis",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="PIS do item (vPIS)",
                    ),
                ),
                (
                    "cst_cofins",
                    models.CharField(
                        blank=True,
                        max_length=2,
                        null=True,
                        verbose_name="CST da Cofins",
                    ),
                ),
                (
                    "v_cofins",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="Cofins do item (vCOFINS)",
                    ),
                ),
                (
                    "v_issqn",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ISSQN do item (vISSQN)",
                    ),
                ),
                (
                    "v_ii",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="imposto de importação do item (vII)",
                    ),
                ),
                (
                    "tem_ibscbs",
                    models.BooleanField(default=False, verbose_name="traz grupo IBS/CBS"),
                ),
                (
                    "ibscbs_xml",
                    models.TextField(
                        blank=True, default="", verbose_name="grupo IBS/CBS, XML bruto"
                    ),
                ),
                (
                    "receita_bruta_item",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=15,
                        verbose_name="receita bruta do item (derivada)",
                    ),
                ),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="itens",
                        to="fiscal.documentonfe",
                        verbose_name="documento",
                    ),
                ),
            ],
            options={
                "verbose_name": "item de NF-e",
                "verbose_name_plural": "itens de NF-e",
                "ordering": ["documento_id", "n_item"],
            },
        ),
        migrations.CreateModel(
            name="LeituraItensNFe",
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
                    "estado",
                    models.CharField(
                        choices=[("lida", "Lida"), ("ilegivel", "Itens ilegíveis")],
                        max_length=10,
                        verbose_name="estado da leitura",
                    ),
                ),
                (
                    "motivo",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="motivo (quando ilegível)",
                    ),
                ),
                (
                    "quantidade_itens",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantidade de itens lidos"
                    ),
                ),
                (
                    "versao_leitor",
                    models.PositiveSmallIntegerField(
                        default=1,
                        verbose_name="versão do leitor",
                    ),
                ),
                (
                    "v_ii",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="total do II (vII)",
                    ),
                ),
                (
                    "v_ipi_devol",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="IPI devolvido (vIPIDevol)",
                    ),
                ),
                (
                    "v_nf_tot",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="valor total com IBS, CBS e IS (vNFTot)",
                    ),
                ),
                (
                    "v_ibs",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="total do IBS (vIBS)",
                    ),
                ),
                (
                    "v_cbs",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="total da CBS (vCBS)",
                    ),
                ),
                (
                    "v_is",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="total do IS (vIS)",
                    ),
                ),
                (
                    "v_fcp_st_total",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="total do FCP-ST (vFCPST)",
                    ),
                ),
                (
                    "lida_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="lida em"),
                ),
                (
                    "documento",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leitura_itens",
                        to="fiscal.documentonfe",
                        verbose_name="documento",
                    ),
                ),
            ],
            options={
                "verbose_name": "leitura de itens de NF-e",
                "verbose_name_plural": "leituras de itens de NF-e",
            },
        ),
        migrations.CreateModel(
            name="NaturezaItemNFe",
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
                    "natureza",
                    models.CharField(
                        blank=True,
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
                            ("combustivel", "Revenda de combustíveis"),
                            ("exportacao_direta", "Exportação direta"),
                            ("comercial_exportadora", "Venda a comercial exportadora"),
                            ("devolucao_venda", "Devolução de venda recebida"),
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
                        default="",
                        max_length=24,
                        verbose_name="natureza confirmada",
                    ),
                ),
                (
                    "atualizada_em",
                    models.DateTimeField(auto_now=True, verbose_name="atualizada em"),
                ),
                (
                    "escrituracao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="naturezas_dos_itens",
                        to="fiscal.escrituracaonfe",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="naturezas",
                        to="fiscal.itemnfe",
                    ),
                ),
            ],
            options={
                "verbose_name": "natureza de item de NF-e",
                "verbose_name_plural": "naturezas de itens de NF-e",
            },
        ),
        migrations.AddConstraint(
            model_name="escrituracaonfe",
            constraint=models.UniqueConstraint(
                condition=models.Q(("estado__in", ["rascunho", "efetivada"])),
                fields=("vinculo",),
                name="escrituracao_nfe_ativa_unica_por_vinculo",
            ),
        ),
        migrations.AddConstraint(
            model_name="escrituracaonfe",
            constraint=models.CheckConstraint(
                condition=models.Q(("estado__in", ["rascunho", "efetivada", "estornada"])),
                name="escrituracao_nfe_estado_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="escrituracaonfe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("efetivada_em__isnull", True),
                        ("efetivada_por__isnull", True),
                        ("estado", "rascunho"),
                        ("estornada_em__isnull", True),
                        ("estornada_por__isnull", True),
                        ("motivo_estorno", ""),
                    ),
                    models.Q(
                        ("competencia__isnull", False),
                        ("data_emissao__isnull", False),
                        ("devolucao__isnull", False),
                        ("efetivada_em__isnull", False),
                        ("efetivada_por__isnull", False),
                        ("estado", "efetivada"),
                        ("estornada_em__isnull", True),
                        ("estornada_por__isnull", True),
                        ("motivo_estorno", ""),
                        ("receita_bruta__isnull", False),
                        ("soma_itens__isnull", False),
                        ("valor_nf__isnull", False),
                    ),
                    models.Q(
                        models.Q(("motivo_estorno", ""), _negated=True),
                        ("competencia__isnull", False),
                        ("data_emissao__isnull", False),
                        ("devolucao__isnull", False),
                        ("efetivada_em__isnull", False),
                        ("efetivada_por__isnull", False),
                        ("estado", "estornada"),
                        ("estornada_em__isnull", False),
                        ("estornada_por__isnull", False),
                        ("receita_bruta__isnull", False),
                        ("soma_itens__isnull", False),
                        ("valor_nf__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="escrituracao_nfe_campos_coerentes_com_o_estado",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemnfe",
            constraint=models.UniqueConstraint(
                fields=("documento", "n_item"), name="item_nfe_unico_por_nota"
            ),
        ),
        migrations.AddConstraint(
            model_name="itemnfe",
            constraint=models.CheckConstraint(
                condition=models.Q(("n_item__gte", 1)), name="item_nfe_n_item_positivo"
            ),
        ),
        migrations.AddConstraint(
            model_name="leituraitensnfe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("estado", "lida"), ("motivo", "")),
                    models.Q(models.Q(("motivo", ""), _negated=True), ("estado", "ilegivel")),
                    _connector="OR",
                ),
                name="leitura_itens_nfe_motivo_coerente",
            ),
        ),
        migrations.AddConstraint(
            model_name="naturezaitemnfe",
            constraint=models.UniqueConstraint(
                fields=("escrituracao", "item"), name="natureza_item_nfe_unica_por_item"
            ),
        ),
        migrations.RunPython(_criar_gatilhos, _desfazer_gatilhos),
    ]
