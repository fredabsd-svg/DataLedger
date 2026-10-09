# DL-080 (frente A): recepção de NF-e modelo 55 e NFC-e modelo 65. Aditiva: cria três tabelas
# (`DocumentoNFe`, `VinculoNFeEmpresa`, `EventoNFe`) e acrescenta duas colunas nulas a
# `ResultadoDoArquivo` (`documento_nfe_id`, `evento_nfe_id`). Nenhuma tabela existente muda de dado
# nem de regra; a NFS-e continua gravando onde gravava. Reverter é reverter esta migração e o merge.
#
# DEPENDÊNCIA: `fiscal 0009` e só `empresas 0007_bl54_cnpj_check_constraint_formato` (mesma escolha
# da 0009): as tabelas novas precisam só de `empresas_empresa` e da chave dela. Depender da última
# `empresas` faria reverter `empresas` desfazer esta tabela.
#
# Sem gatilho de PostgreSQL: a NFS-e da fatia 1 também não tem, e o contrato desta frente é não
# inventar mecanismo. Limite declarado: registro de NF-e recebido pode ser alterado por SQL direto.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("empresas", "0007_bl54_cnpj_check_constraint_formato"),
        ("fiscal", "0009_dl079_presumido"),
        ("tenancy", "0003_escritorio_endereco_no_timbre_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoNFe",
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
                    "modelo",
                    models.CharField(
                        choices=[("55", "NF-e"), ("65", "NFC-e")],
                        max_length=2,
                        verbose_name="modelo (mod)",
                    ),
                ),
                (
                    "versao",
                    models.CharField(max_length=4, verbose_name="versão do leiaute"),
                ),
                (
                    "chave",
                    models.CharField(max_length=44, verbose_name="chave de acesso"),
                ),
                ("xml_original", models.BinaryField(verbose_name="XML original")),
                (
                    "sha256_arquivo",
                    models.CharField(max_length=64, verbose_name="SHA-256 do arquivo"),
                ),
                ("serie", models.CharField(max_length=3, verbose_name="série (serie)")),
                ("numero", models.CharField(max_length=9, verbose_name="número (nNF)")),
                (
                    "dh_emissao",
                    models.DateTimeField(verbose_name="data/hora de emissão (dhEmi)"),
                ),
                (
                    "tp_nf",
                    models.CharField(
                        max_length=1, verbose_name="tipo de operação (tpNF)"
                    ),
                ),
                (
                    "fin_nfe",
                    models.CharField(max_length=1, verbose_name="finalidade (finNFe)"),
                ),
                (
                    "tp_nf_debito",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2,
                        verbose_name="finalidade de débito (tpNFDebito)",
                    ),
                ),
                (
                    "tp_nf_credito",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=2,
                        verbose_name="finalidade de crédito (tpNFCredito)",
                    ),
                ),
                (
                    "id_dest",
                    models.CharField(
                        max_length=1, verbose_name="local de destino (idDest)"
                    ),
                ),
                (
                    "c_uf",
                    models.CharField(max_length=2, verbose_name="UF do emitente (cUF)"),
                ),
                (
                    "emitente_tipo_documento",
                    models.CharField(
                        choices=[
                            ("CNPJ", "CNPJ"),
                            ("CPF", "CPF"),
                            ("idEstrangeiro", "Identificação de estrangeiro"),
                        ],
                        max_length=14,
                        verbose_name="tipo de documento do emitente",
                    ),
                ),
                (
                    "emitente_documento",
                    models.CharField(
                        max_length=14, verbose_name="documento do emitente"
                    ),
                ),
                (
                    "emitente_nome",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=60,
                        verbose_name="nome do emitente",
                    ),
                ),
                (
                    "emitente_crt",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=1,
                        verbose_name="regime tributário do emitente (CRT)",
                    ),
                ),
                (
                    "destinatario_tipo_documento",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("CNPJ", "CNPJ"),
                            ("CPF", "CPF"),
                            ("idEstrangeiro", "Identificação de estrangeiro"),
                        ],
                        default="",
                        max_length=14,
                        verbose_name="tipo de documento do destinatário",
                    ),
                ),
                (
                    "destinatario_documento",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=20,
                        verbose_name="documento do destinatário",
                    ),
                ),
                (
                    "destinatario_nome",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=60,
                        verbose_name="nome do destinatário",
                    ),
                ),
                (
                    "v_nf",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="valor total da nota (vNF)",
                    ),
                ),
                (
                    "v_prod",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="valor dos produtos (vProd)",
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
                    "v_st",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="ICMS-ST (vST)",
                    ),
                ),
                (
                    "v_ipi",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="IPI (vIPI)",
                    ),
                ),
                (
                    "v_pis",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="PIS (vPIS)",
                    ),
                ),
                (
                    "v_cofins",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="COFINS (vCOFINS)",
                    ),
                ),
                (
                    "v_desc",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="desconto (vDesc)",
                    ),
                ),
                (
                    "v_frete",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        verbose_name="frete (vFrete)",
                    ),
                ),
                (
                    "c_stat",
                    models.CharField(
                        max_length=4, verbose_name="status do protocolo (cStat)"
                    ),
                ),
                (
                    "n_prot",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=17,
                        verbose_name="número do protocolo (nProt)",
                    ),
                ),
                (
                    "dh_recbto",
                    models.DateTimeField(
                        verbose_name="data/hora de recebimento (dhRecbto)"
                    ),
                ),
                (
                    "quantidade_itens",
                    models.PositiveIntegerField(verbose_name="quantidade de itens"),
                ),
                (
                    "tem_ibscbs_total",
                    models.BooleanField(
                        default=False, verbose_name="traz total IBS/CBS (IBSCBSTot)"
                    ),
                ),
                (
                    "tem_ibscbs_item",
                    models.BooleanField(
                        default=False, verbose_name="traz IBS/CBS em algum item"
                    ),
                ),
                (
                    "transferencia_entre_estabelecimentos",
                    models.BooleanField(
                        default=False,
                        verbose_name="transferência entre estabelecimentos",
                    ),
                ),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "escritorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="documentos_nfe",
                        to="tenancy.escritorio",
                        verbose_name="escritório",
                    ),
                ),
            ],
            options={
                "verbose_name": "documento de NF-e",
                "verbose_name_plural": "documentos de NF-e",
                "ordering": ["-dh_emissao"],
            },
        ),
        migrations.AddField(
            model_name="resultadodoarquivo",
            name="documento_nfe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resultados",
                to="fiscal.documentonfe",
            ),
        ),
        migrations.CreateModel(
            name="EventoNFe",
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
                    "identificador",
                    models.CharField(
                        max_length=54, verbose_name="identificador (Id) do evento"
                    ),
                ),
                (
                    "tp_evento",
                    models.CharField(
                        max_length=6, verbose_name="tipo do evento (tpEvento)"
                    ),
                ),
                (
                    "n_seq_evento",
                    models.PositiveSmallIntegerField(
                        verbose_name="sequência do evento (nSeqEvento)"
                    ),
                ),
                (
                    "chave",
                    models.CharField(
                        max_length=44, verbose_name="chave de acesso da nota (chNFe)"
                    ),
                ),
                (
                    "dh_evento",
                    models.DateTimeField(verbose_name="data/hora do evento (dhEvento)"),
                ),
                (
                    "autor_tipo_documento",
                    models.CharField(
                        choices=[
                            ("CNPJ", "CNPJ"),
                            ("CPF", "CPF"),
                            ("idEstrangeiro", "Identificação de estrangeiro"),
                        ],
                        max_length=14,
                        verbose_name="tipo de documento do autor",
                    ),
                ),
                (
                    "autor_documento",
                    models.CharField(max_length=14, verbose_name="documento do autor"),
                ),
                (
                    "c_stat",
                    models.CharField(
                        blank=True,
                        max_length=4,
                        null=True,
                        verbose_name="status do retorno (cStat)",
                    ),
                ),
                ("xml_original", models.BinaryField(verbose_name="XML original")),
                (
                    "sha256_arquivo",
                    models.CharField(max_length=64, verbose_name="SHA-256 do arquivo"),
                ),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eventos_nfe",
                        to="empresas.empresa",
                        verbose_name="empresa (quando identificável)",
                    ),
                ),
                (
                    "escritorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="eventos_nfe",
                        to="tenancy.escritorio",
                        verbose_name="escritório",
                    ),
                ),
            ],
            options={
                "verbose_name": "evento de NF-e",
                "verbose_name_plural": "eventos de NF-e",
                "ordering": ["-dh_evento"],
            },
        ),
        migrations.AddField(
            model_name="resultadodoarquivo",
            name="evento_nfe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resultados",
                to="fiscal.eventonfe",
            ),
        ),
        migrations.CreateModel(
            name="VinculoNFeEmpresa",
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
                    "papel",
                    models.CharField(
                        choices=[
                            ("emitente", "Emitente"),
                            ("destinatario", "Destinatário"),
                        ],
                        max_length=12,
                        verbose_name="papel",
                    ),
                ),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vinculos",
                        to="fiscal.documentonfe",
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="vinculos_nfe",
                        to="empresas.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name": "vínculo de NF-e com empresa",
                "verbose_name_plural": "vínculos de NF-e com empresa",
            },
        ),
        migrations.AddConstraint(
            model_name="documentonfe",
            constraint=models.UniqueConstraint(
                fields=("escritorio", "chave"),
                name="documento_nfe_unico_por_escritorio",
            ),
        ),
        migrations.AddIndex(
            model_name="eventonfe",
            index=models.Index(
                fields=["escritorio", "chave"], name="evento_nfe_escritorio_chave"
            ),
        ),
        migrations.AddConstraint(
            model_name="eventonfe",
            constraint=models.UniqueConstraint(
                fields=("escritorio", "identificador", "sha256_arquivo"),
                name="evento_nfe_unico_por_identificador_e_conteudo",
            ),
        ),
        migrations.AddConstraint(
            model_name="vinculonfeempresa",
            constraint=models.UniqueConstraint(
                fields=("documento", "empresa"), name="vinculo_nfe_empresa_unico"
            ),
        ),
    ]
