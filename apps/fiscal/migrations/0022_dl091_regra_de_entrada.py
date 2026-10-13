# DL-091 (frente A2): regras da DL-087 para ENTRADAS (compra), com CRT e UF do emitente e CFOP de
# entrada fixado pela regra.
#
# Migração ADITIVA: três colunas novas (com valor vazio por padrão), um tipo novo no CHECK de `tipo`
# e cinco CHECKs novos. Nenhuma regra existente muda, e nenhuma escrituração é tocada.
#
# Gatilho de imutabilidade (0019): o gatilho passa a conferir os três campos novos como critério, e
# a substituição da função é feita aqui (`CREATE OR REPLACE`). A 0019 não é editada, porque já está
# aplicada em ambientes compartilhados. A função da reversão é a da 0019, copiada abaixo.
#
# Reversão (`migrate fiscal 0021`): RECUSA, sem alterar nada, se houver regra de entrada (`tipo` =
# entrada) ou regra com CRT, UF ou CFOP de entrada gravado: o CHECK antigo não os aceita, e apagá-
# los
# perderia quem criou a regra e por quê. A guarda é a ÚLTIMA operação da lista, então na reversão
# roda PRIMEIRO, antes de qualquer coluna ou CHECK sair.

from importlib import import_module

from django.db import migrations, models
from django.db.models import Q

_SQL_FUNCAO_NOVA = """
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
        NEW.cst_csosn, NEW.id_dest, NEW.crt_emitente, NEW.uf_emitente, NEW.cfop_entrada,
        NEW.natureza, NEW.vigencia_inicio, NEW.criada_por_id, NEW.criada_em)
       IS DISTINCT FROM
       (OLD.escritorio_id, OLD.empresa_id, OLD.tipo, OLD.cfop, OLD.ncm, OLD.ncm_modo,
        OLD.cst_csosn, OLD.id_dest, OLD.crt_emitente, OLD.uf_emitente, OLD.cfop_entrada,
        OLD.natureza, OLD.vigencia_inicio, OLD.criada_por_id, OLD.criada_em) THEN
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
"""

# Cópia da função da 0019, para a reversão. Sem os três campos novos, como antes desta migração.
_SQL_FUNCAO_ANTIGA = """
CREATE OR REPLACE FUNCTION fiscal_regra_classificacao_nfe_imutavel()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'regra de classificação de NF-e não pode ser excluída: revogue-a com motivo'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'regra_classificacao_nfe_imutavel';
    END IF;
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
"""

_NATUREZAS_DE_ENTRADA = [
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
]

_SIGLAS_UF = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
    "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]  # fmt: skip

_TIPOS_DEPOIS = ["saida_propria", "devolucao", "entrada"]


def _trocar_gatilho(apps, schema_editor):
    """Só PostgreSQL: o gatilho é PL/pgSQL. Fora dele, a imutabilidade fica no `save()`."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_FUNCAO_NOVA)


def _restaurar_gatilho(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_SQL_FUNCAO_ANTIGA)


def _recusar_reversao_com_regra_de_entrada(apps, schema_editor):
    """Guarda da reversão: regra de entrada, ou com CRT, UF ou CFOP de entrada, não reverte.

    A conferência própria é só leitura, e vem PRIMEIRO, para dar a mensagem específica da entrada.
    Depois chama a guarda da 0021, que encadeia as das migrações de baixo (0020, 0019...). O Django
    reverte cada migração em transação própria: a cadeia é o que impede a reversão de alterar o
    esquema antes de a 0019 recusar (DL-087, A9). A 0019 recusa QUALQUER regra gravada, então a
    cadeia cobre também a saída.
    """
    regra = apps.get_model("fiscal", "RegraClassificacaoNFe")
    gravadas = regra.objects.filter(
        Q(tipo="entrada") | ~Q(crt_emitente="", uf_emitente="", cfop_entrada="")
    ).count()
    if gravadas:
        raise RuntimeError(
            f"Reversão da DL-091 (A2) recusada, sem alterar nada: {gravadas} regra(s) de "
            "classificação de entrada, ou com CRT, UF ou CFOP de entrada, gravada(s). O CHECK "
            "antigo não as aceita. São dados do escritório: registre-as ou trate-as antes de "
            "reverter."
        )
    guarda_da_0021 = import_module("apps.fiscal.migrations.0021_dl091_entrada_nfe")
    guarda_da_0021._recusar_reversao_com_entrada(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0021_dl091_entrada_nfe"),
    ]

    operations = [
        # Primeiro o gatilho: a função nova lê as colunas novas, e o PL/pgSQL as resolve só depois.
        migrations.RunPython(_trocar_gatilho, _restaurar_gatilho),
        migrations.AlterField(
            model_name="regraclassificacaonfe",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("saida_propria", "Saída própria (finNFe 1)"),
                    ("devolucao", "Devolução de venda recebida (finNFe 4)"),
                    ("entrada", "Entrada de compra (NF-e de terceiro, finNFe 1)"),
                ],
                max_length=16,
                verbose_name="tipo da nota",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="regraclassificacaonfe",
            name="regra_classificacao_nfe_tipo_valido",
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=Q(tipo__in=_TIPOS_DEPOIS),
                name="regra_classificacao_nfe_tipo_valido",
            ),
        ),
        migrations.AddField(
            model_name="regraclassificacaonfe",
            name="crt_emitente",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "1 (Simples Nacional)"),
                    ("2", "2 (Simples Nacional, excesso de sublimite)"),
                    ("3", "3 (regime normal)"),
                    ("4", "4 (MEI)"),
                ],
                default="",
                max_length=1,
                verbose_name="CRT do emitente",
            ),
        ),
        migrations.AddField(
            model_name="regraclassificacaonfe",
            name="uf_emitente",
            field=models.CharField(
                blank=True, default="", max_length=2, verbose_name="UF do emitente"
            ),
        ),
        migrations.AddField(
            model_name="regraclassificacaonfe",
            name="cfop_entrada",
            field=models.CharField(
                blank=True, default="", max_length=4, verbose_name="CFOP de entrada"
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=Q(crt_emitente__in=["", "1", "2", "3", "4"]),
                name="regra_classificacao_nfe_crt_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=Q(uf_emitente__in=["", *_SIGLAS_UF]),
                name="regra_classificacao_nfe_uf_valida",
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=Q(cfop_entrada="") | Q(cfop_entrada__regex=r"^[1-3][0-9]{3}$"),
                name="regra_classificacao_nfe_cfop_entrada_valido",
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=(Q(tipo="entrada") | Q(crt_emitente="", uf_emitente="", cfop_entrada="")),
                name="regra_classificacao_nfe_criterio_de_entrada_so_na_entrada",
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=~Q(tipo="entrada") | Q(natureza__in=_NATUREZAS_DE_ENTRADA),
                name="regra_classificacao_nfe_entrada_so_natureza_de_entrada",
            ),
        ),
        migrations.AddConstraint(
            model_name="regraclassificacaonfe",
            constraint=models.CheckConstraint(
                condition=Q(tipo="entrada") | ~Q(natureza__in=_NATUREZAS_DE_ENTRADA),
                name="regra_classificacao_nfe_saida_sem_natureza_de_entrada",
            ),
        ),
        # ÚLTIMA operação: na reversão roda PRIMEIRO, antes de qualquer coluna ou CHECK sair.
        migrations.RunPython(migrations.RunPython.noop, _recusar_reversao_com_regra_de_entrada),
    ]
