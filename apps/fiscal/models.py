"""Modelos da recepção de documentos fiscais — DL-010, fatia 1 (NFS-e nacional).

Contrato e decisões: docs/planos/DL-010-F1-recepcao-nfse.md e DE-074
(docs/projeto/decisoes.md). Cinco escolhas de DE-074 que explicam por que
estes modelos são como são:

1. O XML original é guardado BYTE A BYTE (BinaryField) com SHA-256 — o bloco
   IBS/CBS já chega em 12% das NFS-e (RC-76) e ainda não tem regra
   confirmada (PE-39); guardar o original permite interpretá-lo depois sem
   pedir o arquivo de novo ao cliente.
2. Leitura por `defusedxml` (apps/fiscal/leitor.py), nunca `xml.etree`
   puro — arquivo de terceiro é a superfície de ataque mais comum de um
   importador.
3. Deduplicação por `(escritorio, identificador)` — nunca identificador
   sozinho: um identificador único GLOBAL revelaria a um escritório que
   outro já recebeu aquela nota (mesmo defeito do BL-48 com CNPJ).
4. Situação (cancelada/válida) é DERIVADA dos eventos, nunca gravada no
   documento — ver `apps.fiscal.services.situacao_do_documento`.
5. Sem admin do Django para estes modelos: o admin não isola por
   escritório (BL-262), decisão do plano da etapa.

Nenhum destes modelos é registrado em `apps/fiscal/admin.py` — não existe
esse arquivo de propósito.
"""

from django.db import models

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio


class TipoDocumentoFiscal(models.TextChoices):
    """Só `NFSE_NACIONAL` é alcançável nesta fatia. Os demais tipos que o
    leitor RECONHECE (NF-e) são recusados antes de qualquer gravação — ver
    `apps.fiscal.leitor.ler_arquivo` — e por isso nunca aparecem aqui. O
    enum já existe pronto para a fatia 2 (NF-e modelo 55, DL-010 mãe)."""

    NFSE_NACIONAL = "nfse_nacional", "NFS-e nacional"


class TipoDocumentoParticipante(models.TextChoices):
    """Como o prestador ou o tomador foram identificados no XML (TCEmitente/
    TCInfoPessoa/TCInfoPrestador, tiposComplexos_v1.0x.xsd, xs:choice CNPJ|
    CPF|NIF|cNaoNIF). O prestador (infNFSe/emit) só admite CNPJ ou CPF no
    esquema; o tomador (DPS/infDPS/toma) admite os quatro."""

    CNPJ = "CNPJ", "CNPJ"
    CPF = "CPF", "CPF"
    NIF = "NIF", "NIF (identificação fiscal estrangeira)"
    NAO_INFORMADO = "nao_informado", "Não informado (cNaoNIF)"


class PapelDocumento(models.TextChoices):
    PRESTADOR = "prestador", "Prestador"
    TOMADOR = "tomador", "Tomador"


class TipoResultadoArquivo(models.TextChoices):
    RECEBIDO = "recebido", "Recebido"
    DUPLICADO = "duplicado", "Duplicado"
    RECUSADO = "recusado", "Recusado"


class LoteDeRecepcao(models.Model):
    """Um envio (um XML solto ou um ZIP) processado por `services.receber_envio`.

    As contagens (`total_*`) são um resumo desnormalizado, calculado ao
    final do processamento — o detalhe arquivo a arquivo vive em
    `ResultadoDoArquivo`. Guardamos as duas coisas porque o resumo é o que
    a tela de relatório do envio (etapa 2, especialista-frontend) exibe
    primeiro, sem percorrer as linhas.
    """

    escritorio = models.ForeignKey(
        Escritorio, verbose_name="escritório", on_delete=models.PROTECT, related_name="lotes_de_recepcao"
    )
    usuario = models.ForeignKey(
        # PROTECT, não CASCADE/SET_NULL: um lote de recepção é trilha —
        # quem enviou não pode desaparecer do registro por ter sido
        # removido depois (mesma razão de RegistroAuditoria.usuario).
        "accounts.Usuario",
        verbose_name="usuário",
        on_delete=models.PROTECT,
        related_name="lotes_de_recepcao",
    )
    nome_arquivo = models.CharField("nome do arquivo enviado", max_length=255)
    sha256_arquivo = models.CharField("SHA-256 do arquivo enviado", max_length=64)
    tamanho_bytes = models.PositiveIntegerField("tamanho do arquivo enviado (bytes)")
    total_arquivos = models.PositiveIntegerField("total de arquivos no envio", default=0)
    total_recebidos = models.PositiveIntegerField("total recebidos", default=0)
    total_duplicados = models.PositiveIntegerField("total duplicados", default=0)
    total_recusados = models.PositiveIntegerField("total recusados", default=0)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "lote de recepção"
        verbose_name_plural = "lotes de recepção"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Lote {self.pk} — {self.nome_arquivo} ({self.escritorio})"


class DocumentoFiscal(models.Model):
    """NFS-e nacional recebida. Campos extraídos do XML — o original fica em
    `xml_original`, íntegro (DE-074 item 1).

    A unicidade é por `(escritorio, identificador)` (DE-074 item 3): a MESMA
    nota vista em duas pastas de clientes do mesmo escritório (RC-69) é UM
    documento com DOIS vínculos (`VinculoDocumentoEmpresa`), um por empresa e
    papel. Escritórios diferentes NUNCA compartilham a linha.
    """

    escritorio = models.ForeignKey(
        Escritorio, verbose_name="escritório", on_delete=models.PROTECT, related_name="documentos_fiscais"
    )
    tipo = models.CharField(
        "tipo", max_length=20, choices=TipoDocumentoFiscal.choices, default=TipoDocumentoFiscal.NFSE_NACIONAL
    )
    # TVerNFSe (tiposSimples_v1.0x.xsd): "1.00" ou "1.01" — RC-72.
    versao = models.CharField("versão do leiaute", max_length=4)
    # TSIdNFSe: "NFS" + 50 dígitos = 53 posições (RC-74). Formato conferido
    # pelo leitor; o dígito verificador NÃO é conferido (limite declarado no
    # plano da etapa — o XSD não documenta o algoritmo do DV do Id).
    identificador = models.CharField("identificador (Id)", max_length=53)
    xml_original = models.BinaryField("XML original", editable=False)
    sha256_arquivo = models.CharField("SHA-256 do arquivo", max_length=64)
    # TSNNFSe: 1 a 13 dígitos, SEM padronização de zero à esquerda — NUNCA é
    # chave (RC-74, RC-75, critério 16 do plano). Texto, nunca inteiro.
    numero = models.CharField("número (nNFSe)", max_length=13, blank=True, default="")
    dh_emissao = models.DateTimeField("data/hora de emissão (dhEmi)")
    d_competencia = models.DateField("data de competência (dCompet)")
    prestador_tipo_documento = models.CharField(
        "tipo de documento do prestador", max_length=20, choices=TipoDocumentoParticipante.choices
    )
    # CNPJ, CPF ou NIF do prestador/tomador, SEMPRE texto — nunca convertido
    # para número (RC-75: 553 CNPJ com zero à esquerda no acervo real).
    # max_length=40 acomoda TSNIF (identificação fiscal estrangeira, até 40
    # posições) — o maior dos quatro formatos possíveis.
    prestador_documento = models.CharField("documento do prestador", max_length=40)
    prestador_nome = models.CharField("nome do prestador", max_length=300, blank=True, default="")
    # Tomador é OPCIONAL no esquema (DPS/infDPS/toma, minOccurs="0") — os
    # três campos ficam em branco quando o documento não o traz. Isso é
    # DIFERENTE de "tomador com cNaoNIF" (tipo NAO_INFORMADO, documento
    # vazio, mas o bloco existiu no XML).
    tomador_tipo_documento = models.CharField(
        "tipo de documento do tomador",
        max_length=20,
        choices=TipoDocumentoParticipante.choices,
        blank=True,
        default="",
    )
    tomador_documento = models.CharField("documento do tomador", max_length=40, blank=True, default="")
    tomador_nome = models.CharField("nome do tomador", max_length=300, blank=True, default="")
    # DE-010: Decimal a partir de TEXTO, nunca float. TSDec15V2 permite até
    # 15 dígitos inteiros + 2 decimais — max_digits=17.
    v_serv = models.DecimalField("valor do serviço (vServ)", max_digits=17, decimal_places=2)
    v_liq = models.DecimalField("valor líquido (vLiq)", max_digits=17, decimal_places=2)
    # RC-110: 1 não retido, 2 retido pelo tomador, 3 retido pelo
    # intermediário. Código LIDO e EXIBIDO, nunca interpretado nesta etapa
    # (plano: "a retenção de ISS é lida e exibida, não interpretada nem
    # calculada").
    tp_ret_issqn = models.CharField("tipo de retenção do ISSQN (tpRetISSQN)", max_length=1)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "documento fiscal"
        verbose_name_plural = "documentos fiscais"
        ordering = ["-dh_emissao"]
        constraints = [
            models.UniqueConstraint(
                fields=["escritorio", "identificador"],
                name="documento_fiscal_unico_por_escritorio",
            ),
        ]

    def __str__(self):
        return f"{self.identificador} ({self.escritorio})"


class VinculoDocumentoEmpresa(models.Model):
    """Liga um `DocumentoFiscal` a uma `Empresa` do MESMO escritório, no papel
    de prestador ou tomador. Uma nota com os dois lados clientes do mesmo
    escritório gera DOIS vínculos (critério "os dois clientes" do plano).
    """

    documento = models.ForeignKey(DocumentoFiscal, on_delete=models.CASCADE, related_name="vinculos")
    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="vinculos_documento_fiscal"
    )
    papel = models.CharField("papel", max_length=10, choices=PapelDocumento.choices)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vínculo documento-empresa"
        verbose_name_plural = "vínculos documento-empresa"
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "empresa"],
                name="vinculo_documento_empresa_unico",
            ),
        ]

    def __str__(self):
        return f"{self.documento_id} — {self.empresa} ({self.get_papel_display()})"


class EventoFiscal(models.Model):
    """Evento de NFS-e (cancelamento, confirmação, rejeição...), inclusive
    ÓRFÃO — sem a nota correspondente no acervo (RC-70: é o caso NORMAL, não
    a exceção; 29 de 29 cancelamentos medidos no acervo real vieram assim).

    `chave_nfse` referencia a nota pelos 50 dígitos NUMÉRICOS da chave
    (TSChaveNFSe), SEM o prefixo "NFS" que `DocumentoFiscal.identificador`
    tem — os dois formatos coexistem no próprio XSD (infNFSe/@Id = "NFS" +
    50 dígitos; evento/infEvento/pedRegEvento/infPedReg/chNFSe = só os 50
    dígitos). A comparação entre os dois vive em UM lugar só:
    `apps.fiscal.services.situacao_do_documento`.
    """

    escritorio = models.ForeignKey(
        Escritorio, verbose_name="escritório", on_delete=models.PROTECT, related_name="eventos_fiscais"
    )
    # TSIdEvento: "EVT" + chave(50) + tipo do evento(6) + nPedRegEvento(3) =
    # 62 posições.
    identificador = models.CharField("identificador (Id) do evento", max_length=62)
    # Nome do elemento escolhido no xs:choice de TCInfPedReg — "e" + 6
    # dígitos (ex.: "e101101"). É o próprio CÓDIGO do evento (HI-20).
    codigo = models.CharField("código do evento", max_length=7)
    # TSChaveNFSe: 50 dígitos, sem prefixo — ver docstring da classe.
    chave_nfse = models.CharField("chave da NFS-e referenciada (chNFSe)", max_length=50)
    data_evento = models.DateTimeField("data/hora do evento (dhEvento)")
    xml_original = models.BinaryField("XML original", editable=False)
    sha256_arquivo = models.CharField("SHA-256 do arquivo", max_length=64)
    # Empresa do escritório identificada como autora do evento (CNPJAutor/
    # CPFAutor), quando um CNPJ do autor casar com empresa/estabelecimento
    # do escritório — ver apps.fiscal.services.localizar_empresa_do_escritorio.
    # NULL é o caso normal: autor com CPF, ou CNPJ que não é de nenhum
    # cliente deste escritório (ex.: o próprio prestador de OUTRO
    # escritório, ou a prefeitura).
    empresa = models.ForeignKey(
        Empresa,
        verbose_name="empresa (quando identificável)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eventos_fiscais",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "evento fiscal"
        verbose_name_plural = "eventos fiscais"
        ordering = ["-data_evento"]
        constraints = [
            models.UniqueConstraint(
                fields=["escritorio", "identificador"],
                name="evento_fiscal_unico_por_escritorio",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.identificador} ({self.escritorio})"


class ResultadoDoArquivo(models.Model):
    """Uma linha por arquivo processado dentro de um `LoteDeRecepcao` — a
    "conferência" que o plano pede: o que entrou, o que já existia, o que
    foi recusado e por quê (RC-11 do plano-mãe).
    """

    lote = models.ForeignKey(LoteDeRecepcao, on_delete=models.CASCADE, related_name="resultados")
    # Só para EXIBIÇÃO (nome/caminho dentro do ZIP, ou o nome do arquivo
    # solto) — a classificação e a deduplicação NUNCA usam este campo
    # (RC-71, critério 18: classificação é pelo CONTEÚDO).
    caminho_no_zip = models.CharField("caminho no envio", max_length=500, blank=True, default="")
    resultado = models.CharField("resultado", max_length=10, choices=TipoResultadoArquivo.choices)
    motivo = models.CharField("motivo", max_length=500, blank=True, default="")
    documento = models.ForeignKey(
        DocumentoFiscal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resultados",
    )
    evento = models.ForeignKey(
        EventoFiscal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resultados",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "resultado de arquivo"
        verbose_name_plural = "resultados de arquivo"
        ordering = ["id"]

    def __str__(self):
        return f"{self.caminho_no_zip or '(arquivo solto)'} — {self.get_resultado_display()}"
