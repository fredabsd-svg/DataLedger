# DL-083 (frente A), migração ADITIVA: a natureza `combustivel_revenda` (HI-118; PE-85.1).
#
# A natureza "combustível" se divide em "revenda para consumo" (`combustivel`, 1,6% no IRPJ) e
# "revenda para revenda" (`combustivel_revenda`, 8%). Esta migração acrescenta o valor novo em dois
# lugares:
#
# 1. O CHECK `natureza_item_nfe_valida`, criado pela 0011 com a lista fechada. Sem o valor novo, o
#    banco recusaria a natureza que o Python aceita. A lista é a da 0011 mais `combustivel_revenda`.
# 2. As `choices` do campo (`AlterField`): só estado de migração, sem DDL.
#
# Reversão: a migração NÃO apaga dado. Se existir item com `combustivel_revenda`, a reversão RECUSA
# com a mensagem, e nada muda no banco. A recusa é a PRIMEIRA coisa que a reversão faz (é a última
# operação da ida). Itens de escrituração efetivada só mudam depois de estornada, então o contador
# reclassifica por estorno e nova escrituração, e só depois reverte. Sem a recusa, o CHECK antigo
# seria recriado sobre uma linha que ele não aceita.
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
    "remessa_retorno",
    "transferencia",
    "bonificacao",
    "cupom_nfce",
    "servico_conjugada",
    "ajuste",
)


def _sql_do_check(naturezas):
    lista = ", ".join(f"'{n}'" for n in naturezas)
    return (
        "ALTER TABLE fiscal_naturezaitemnfe DROP CONSTRAINT IF EXISTS natureza_item_nfe_valida; "
        "ALTER TABLE fiscal_naturezaitemnfe ADD CONSTRAINT natureza_item_nfe_valida "
        f"CHECK (natureza IN ('', {lista}));"
    )


def _trocar_check_para_a_lista_nova(apps, schema_editor):
    # O CHECK é do PostgreSQL. Em outro banco, vale só a guarda do Python (como na 0011).
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_sql_do_check(_NATUREZAS_NOVAS))


def _restaurar_check_da_lista_antiga(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_sql_do_check(_NATUREZAS_ANTIGAS))


def _recusar_reversao_com_combustivel_revenda(apps, schema_editor):
    """Recusa a reversão se algum item já usa a natureza nova. Não apaga nem altera nada."""
    NaturezaItemNFe = apps.get_model("fiscal", "NaturezaItemNFe")
    quantidade = NaturezaItemNFe.objects.filter(natureza="combustivel_revenda").count()
    if quantidade:
        raise RuntimeError(
            "Reversão da migração 0012 recusada (DL-083): "
            f"{quantidade} item(ns) de NF-e com a natureza 'combustivel_revenda'. "
            "Reclassifique esses itens antes de reverter. Itens de escrituração efetivada só mudam "
            "depois de estornada. Nenhum dado foi apagado."
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
        migrations.AlterField(
            model_name="naturezaitemnfe",
            name="natureza",
            field=models.CharField(
                blank=True,
                choices=[
                    ("revenda", "Venda de mercadoria adquirida de terceiros (revenda)"),
                    ("producao_propria", "Venda de produção própria"),
                    ("revenda_st_substituido", "Revenda com ICMS-ST, substituído"),
                    ("substituto_st", "Venda como substituto tributário (ST retida na saída)"),
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
                max_length=24,
                verbose_name="natureza confirmada",
            ),
        ),
        # Por último na ida, portanto PRIMEIRO na volta: a recusa roda antes de qualquer DDL.
        migrations.RunPython(
            migrations.RunPython.noop,
            _recusar_reversao_com_combustivel_revenda,
        ),
    ]
