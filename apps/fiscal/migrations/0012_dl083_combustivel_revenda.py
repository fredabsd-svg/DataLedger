# DL-083 (frente A), migração ADITIVA: as naturezas de combustível (HI-118, HI-140; PE-85.1).
#
# A natureza "combustível" se divide em "revenda para consumo" (`combustivel`, 1,6% no IRPJ) e
# "revenda para revenda" (`combustivel_revenda`, 8%). A devolução de combustível para consumo ganha
# a
# natureza `devolucao_combustivel_consumo` (deduz do 1,6%, HI-140). Esta migração acrescenta os
# valores novos em três lugares:
#
# 1. O CHECK `natureza_item_nfe_valida`, criado pela 0011 com a lista fechada. Sem os valores
# novos, o
#    banco recusaria a natureza que o Python aceita.
# 2. O tamanho da coluna: "devolucao_combustivel_consumo" tem 29 caracteres, e a 0011 criou
#    `varchar(24)`. O `ALTER` é só de alargamento (PostgreSQL não reescreve a tabela).
# 3. As `choices` do campo (`AlterField`, só estado de migração, sem DDL).
#
# Reversão, em ordem (a última operação da ida é a primeira da volta):
#
# a) RECUSA, sem alterar nada, se houver item com `combustivel_revenda` ou
#    `devolucao_combustivel_consumo` em escrituração em RASCUNHO ou EFETIVADA. Itens de efetivada só
#    mudam depois de estornada, então o contador reclassifica por estorno e nova escrituração, e
#    só depois reverte. Linhas de escrituração ESTORNADA não entram na contagem: são imutáveis pelo
#    gatilho `natureza_item_nfe_so_em_rascunho`, e nunca mais mudam.
# b) Se só houver estornadas com os valores novos, o CHECK antigo é recriado como `NOT VALID`: ele
#    passa a valer para linhas NOVAS e atualizações, e as estornadas (que não podem mudar) ficam
# como
#    estão. Sem nenhuma linha nova, o CHECK antigo é recriado validado, como antes.
# c) A coluna NÃO volta para `varchar(24)`: o `ALTER` de encolhimento falharia com a estornada de
#    29 caracteres. Ela fica `varchar(29)`, e a 0011 aceita isso sem mudança de comportamento. O
#    estado da migração volta a 24 e às choices antigas, sem DDL.
#
# Reaplicação (`migrate fiscal 0012` de novo): recria o CHECK com a lista nova, validado. As linhas
# estornadas cabem nela.
#
# Literais aqui, como na 0011: a migração não importa o código da aplicação.

from django.db import migrations, models

_NATUREZAS_ANTIGAS = (
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
_NATUREZAS_NOVAS = (
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
# Só existem na lista nova: são os que a reversão precisa tratar.
_SO_NA_LISTA_NOVA = ("combustivel_revenda", "devolucao_combustivel_consumo")
_NOME_CHECK = "natureza_item_nfe_valida"
_TABELA = "fiscal_naturezaitemnfe"


def _sql_do_check(naturezas, nao_valido=False):
    lista = ", ".join(f"'{n}'" for n in naturezas)
    sufixo = " NOT VALID" if nao_valido else ""
    return (
        f"ALTER TABLE {_TABELA} DROP CONSTRAINT IF EXISTS {_NOME_CHECK}; "
        f"ALTER TABLE {_TABELA} ADD CONSTRAINT {_NOME_CHECK} "
        f"CHECK (natureza IN ('', {lista})){sufixo};"
    )


def _trocar_check_para_a_lista_nova(apps, schema_editor):
    # O CHECK é do PostgreSQL. Em outro banco, vale só a guarda do Python (como na 0011).
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_sql_do_check(_NATUREZAS_NOVAS))


def _restaurar_check_da_lista_antiga(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    lista_sql = ", ".join(f"'{n}'" for n in _SO_NA_LISTA_NOVA)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {_TABELA} WHERE natureza IN ({lista_sql}))")
        (ha_linha_nova,) = cursor.fetchone()
    # Com linha nova (só estornada chega aqui, a recusa veio antes), o CHECK antigo vale para linhas
    # novas e não revalida as estornadas.
    schema_editor.execute(_sql_do_check(_NATUREZAS_ANTIGAS, nao_valido=ha_linha_nova))


def _alargar_coluna(apps, schema_editor):
    # 24 para 29 caracteres: alargar `varchar` não reescreve a tabela no PostgreSQL.
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE {_TABELA} ALTER COLUMN natureza TYPE varchar(29);")


def _manter_coluna_larga(apps, schema_editor):
    # Reversão do alargamento: NÃO encolhe a coluna (ver o cabeçalho, item c).
    return


def _recusar_reversao_com_natureza_nova(apps, schema_editor):
    """Recusa a reversão se algum item de escrituração não estornada usa uma natureza nova."""
    NaturezaItemNFe = apps.get_model("fiscal", "NaturezaItemNFe")
    nao_estornadas = NaturezaItemNFe.objects.filter(
        escrituracao__estado__in=["rascunho", "efetivada"],
        natureza__in=_SO_NA_LISTA_NOVA,
    )
    quantidade = nao_estornadas.count()
    if quantidade:
        por_natureza = {
            natureza: nao_estornadas.filter(natureza=natureza).count()
            for natureza in _SO_NA_LISTA_NOVA
        }
        detalhe = ", ".join(f"{n} em {q}" for n, q in por_natureza.items() if q)
        raise RuntimeError(
            "Reversão da migração 0012 recusada (DL-083): "
            f"{quantidade} item(ns) de escrituração em rascunho ou efetivada com natureza nova "
            f"({detalhe}). Reclassifique esses itens (estorne a efetivada e escriture de novo) "
            "antes de reverter. Nenhum dado foi apagado."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0011_dl081_escrituracao_nfe"),
    ]

    operations = [
        migrations.RunPython(
            _trocar_check_para_a_lista_nova,
            _restaurar_check_da_lista_antiga,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
                            ("ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"),
                        ],
                        default="",
                        max_length=29,
                        verbose_name="natureza confirmada",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_alargar_coluna, _manter_coluna_larga),
            ],
        ),
        # Por último na ida, portanto PRIMEIRO na volta: a recusa roda antes de qualquer DDL.
        migrations.RunPython(
            migrations.RunPython.noop,
            _recusar_reversao_com_natureza_nova,
        ),
    ]
