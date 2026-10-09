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

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.empresas.models import Empresa
from apps.fiscal import presumido_tabelas as _tabelas_presumido
from apps.fiscal.cfop import cfop as consultar_cfop_oficial
from apps.tenancy.models import Escritorio


class EscrituracaoImutavel(Exception):
    """Escrituração efetivada ou estornada não se altera nem se apaga por
    `save()`/`delete()` fora dos serviços. A correção é estorno com motivo
    (`apps.fiscal.escrituracao.estornar_escrituracao`). Mesma ideia de
    `LancamentoImutavelError` da contabilidade (DL-052); o banco também
    recusa (gatilho da migração `0002_dl072_escrituracao_fiscal`)."""

    mensagem_padrao = (
        "Escrituração efetivada não pode ser alterada nem excluída; "
        "estorne com motivo para corrigir."
    )

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)
        self.mensagem = mensagem or self.mensagem_padrao


class TipoDocumentoFiscal(models.TextChoices):
    """Tipo de NFS-e, o único de `DocumentoFiscal`. A NF-e (55 e 65) não usa este
    enum: ela tem tabelas próprias desde a DL-080 (`DocumentoNFe`, `EventoNFe`),
    e o leitor a despacha para `apps.fiscal.leitor_nfe`."""

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
        Escritorio,
        verbose_name="escritório",
        on_delete=models.PROTECT,
        related_name="lotes_de_recepcao",
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
        Escritorio,
        verbose_name="escritório",
        on_delete=models.PROTECT,
        related_name="documentos_fiscais",
    )
    tipo = models.CharField(
        "tipo",
        max_length=20,
        choices=TipoDocumentoFiscal.choices,
        default=TipoDocumentoFiscal.NFSE_NACIONAL,
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
    tomador_documento = models.CharField(
        "documento do tomador", max_length=40, blank=True, default=""
    )
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

    documento = models.ForeignKey(
        DocumentoFiscal, on_delete=models.CASCADE, related_name="vinculos"
    )
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
        Escritorio,
        verbose_name="escritório",
        on_delete=models.PROTECT,
        related_name="eventos_fiscais",
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
    # DL-080 (frente A): NF-e e NFC-e ficam em `DocumentoNFe`, e eventos de NF-e
    # em `EventoNFe`. Uma linha tem no máximo um dos quatro vínculos preenchido.
    documento_nfe = models.ForeignKey(
        "DocumentoNFe",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resultados",
    )
    evento_nfe = models.ForeignKey(
        "EventoNFe",
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


# ---------------------------------------------------------------------------
# DL-080 (frente A): NF-e modelo 55 e NFC-e modelo 65 — tabelas PRÓPRIAS.
#
# Não reutilizam `DocumentoFiscal`, `VinculoDocumentoEmpresa` nem `EventoFiscal`:
# essas são da NFS-e (competência, valor do serviço e retenção são obrigatórios),
# e receita, ISS, pré-DAS e tomadas as consultam presumindo NFS-e. Uma NF-e
# aqui nunca aparece por engano num cálculo de NFS-e (pesquisa, seção 7).
#
# Imutabilidade: a fatia 1 (NFS-e) NÃO tem gatilho no banco nem `save()` que
# impeça alteração de `DocumentoFiscal` ou `EventoFiscal`; só o serviço não
# altera. A NF-e segue o mesmo padrão, sem gatilho. Limite declarado.
# ---------------------------------------------------------------------------


class ModeloNFe(models.TextChoices):
    """`ide/mod`: 55 (NF-e) e 65 (NFC-e). Mesmo esquema, MOC 7.0, TB:359-367."""

    NFE = "55", "NF-e"
    NFCE = "65", "NFC-e"


class TipoParticipanteNFe(models.TextChoices):
    """Como emitente, destinatário ou autor de evento foi identificado no XML:
    xs:choice CNPJ|CPF, e idEstrangeiro só no destinatário."""

    CNPJ = "CNPJ", "CNPJ"
    CPF = "CPF", "CPF"
    ID_ESTRANGEIRO = "idEstrangeiro", "Identificação de estrangeiro"


class PapelNFe(models.TextChoices):
    """Papel da EMPRESA na nota. O sentido para o cliente (entrada ou saída) sai do
    papel combinado com `tpNF`, nunca de `tpNF` sozinho (ver `apps.fiscal.api_nfe`)."""

    EMITENTE = "emitente", "Emitente"
    DESTINATARIO = "destinatario", "Destinatário"


class DocumentoNFe(models.Model):
    """NF-e (55) ou NFC-e (65) autorizada, recebida. Campos extraídos do XML; o
    original fica em `xml_original`, íntegro (DE-074 item 1).

    A unicidade é por `(escritorio, chave)`: a mesma chave de acesso é a mesma nota
    para o escritório, qualquer que seja a pasta de onde veio. Escritórios diferentes
    nunca compartilham a linha (mesmo CNPJ em dois escritórios, DL-041).
    """

    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        on_delete=models.PROTECT,
        related_name="documentos_nfe",
    )
    modelo = models.CharField("modelo (mod)", max_length=2, choices=ModeloNFe.choices)
    # TVerNFe: "4.00" (leiauteNFe_v4.00.xsd:7561-7569). Só o 4.00 entra (HI-110).
    versao = models.CharField("versão do leiaute", max_length=4)
    # TChNFe (tiposBasico_v4.00.xsd:49-58): 44 posições, com CNPJ alfanumérico.
    chave = models.CharField("chave de acesso", max_length=44)
    xml_original = models.BinaryField("XML original", editable=False)
    sha256_arquivo = models.CharField("SHA-256 do arquivo", max_length=64)
    # Série: "0" ou 1 a 3 dígitos (TB:384). Número: 1 a 9 dígitos (TB:375). Texto,
    # nunca inteiro: o zero à esquerda da chave é parte do dado.
    serie = models.CharField("série (serie)", max_length=3)
    numero = models.CharField("número (nNF)", max_length=9)
    # dhEmi com fuso (leiauteNFe_v4.00.xsd:66).
    dh_emissao = models.DateTimeField("data/hora de emissão (dhEmi)")
    # Sentido do ponto de vista do EMITENTE: 0 entrada, 1 saída (XSD:81-92).
    tp_nf = models.CharField("tipo de operação (tpNF)", max_length=1)
    fin_nfe = models.CharField("finalidade (finNFe)", max_length=1)
    # Notas de débito e de crédito (opcionais). Vazios quando não vêm.
    tp_nf_debito = models.CharField(
        "finalidade de débito (tpNFDebito)", max_length=2, blank=True, default=""
    )
    tp_nf_credito = models.CharField(
        "finalidade de crédito (tpNFCredito)", max_length=2, blank=True, default=""
    )
    id_dest = models.CharField("local de destino (idDest)", max_length=1)
    c_uf = models.CharField("UF do emitente (cUF)", max_length=2)
    # Emitente: CNPJ (alfanumérico, 14) ou CPF (11 dígitos), sempre TEXTO.
    emitente_tipo_documento = models.CharField(
        "tipo de documento do emitente", max_length=14, choices=TipoParticipanteNFe.choices
    )
    emitente_documento = models.CharField("documento do emitente", max_length=14)
    # xNome: 2 a 60 caracteres (TString, maxLength 60, leiauteNFe_v4.00.xsd:537-545).
    emitente_nome = models.CharField("nome do emitente", max_length=60, blank=True, default="")
    emitente_crt = models.CharField(
        "regime tributário do emitente (CRT)", max_length=1, blank=True, default=""
    )
    # Destinatário é OPCIONAL (XSD:734; a NFC-e normalmente não o traz). Vazio = ausente.
    destinatario_tipo_documento = models.CharField(
        "tipo de documento do destinatário",
        max_length=14,
        choices=TipoParticipanteNFe.choices,
        blank=True,
        default="",
    )
    destinatario_documento = models.CharField(
        "documento do destinatário", max_length=20, blank=True, default=""
    )
    destinatario_nome = models.CharField(
        "nome do destinatário", max_length=60, blank=True, default=""
    )
    # Totais do ICMSTot (XSD:5333-5480) em Decimal 15,2, pelo padrão TDec_1302
    # (13 inteiros + 2 casas). `None` = o campo não veio no XML: ausente, nunca zero.
    v_nf = models.DecimalField(
        "valor total da nota (vNF)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_prod = models.DecimalField(
        "valor dos produtos (vProd)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_icms = models.DecimalField(
        "ICMS (vICMS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_st = models.DecimalField(
        "ICMS-ST (vST)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_ipi = models.DecimalField(
        "IPI (vIPI)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_pis = models.DecimalField(
        "PIS (vPIS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_cofins = models.DecimalField(
        "COFINS (vCOFINS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_desc = models.DecimalField(
        "desconto (vDesc)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_frete = models.DecimalField(
        "frete (vFrete)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # Protocolo de autorização (protNFe/infProt). Só 100 e 150 chegam aqui (HI-109).
    c_stat = models.CharField("status do protocolo (cStat)", max_length=4)
    n_prot = models.CharField("número do protocolo (nProt)", max_length=17, blank=True, default="")
    dh_recbto = models.DateTimeField("data/hora de recebimento (dhRecbto)")
    # Só a contagem de `det` e a presença de IBS/CBS (política da fatia 1, PE-39).
    quantidade_itens = models.PositiveIntegerField("quantidade de itens")
    tem_ibscbs_total = models.BooleanField("traz total IBS/CBS (IBSCBSTot)", default=False)
    tem_ibscbs_item = models.BooleanField("traz IBS/CBS em algum item", default=False)
    # Emitente e destinatário são a mesma empresa (HI-111): um vínculo só, como emitente.
    transferencia_entre_estabelecimentos = models.BooleanField(
        "transferência entre estabelecimentos", default=False
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "documento de NF-e"
        verbose_name_plural = "documentos de NF-e"
        ordering = ["-dh_emissao"]
        constraints = [
            models.UniqueConstraint(
                fields=["escritorio", "chave"],
                name="documento_nfe_unico_por_escritorio",
            ),
        ]

    def __str__(self):
        return f"{self.get_modelo_display()} {self.chave} ({self.escritorio})"


class VinculoNFeEmpresa(models.Model):
    """Liga um `DocumentoNFe` a uma `Empresa` do MESMO escritório, num papel.

    Uma nota com emitente e destinatário clientes distintos gera DOIS vínculos. Se
    os dois lados forem a mesma empresa (transferência entre estabelecimentos), o
    vínculo é um só, como emitente, com `transferencia_entre_estabelecimentos`.
    """

    documento = models.ForeignKey(DocumentoNFe, on_delete=models.CASCADE, related_name="vinculos")
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="vinculos_nfe")
    papel = models.CharField("papel", max_length=12, choices=PapelNFe.choices)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vínculo de NF-e com empresa"
        verbose_name_plural = "vínculos de NF-e com empresa"
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "empresa"],
                name="vinculo_nfe_empresa_unico",
            ),
        ]

    def __str__(self):
        return f"{self.documento_id} — {self.empresa} ({self.get_papel_display()})"


class EventoNFe(models.Model):
    """Evento de NF-e (procEventoNFe), inclusive ÓRFÃO: sem a nota no acervo.

    `chave` é a chave de acesso da nota referenciada (44 posições, a mesma de
    `DocumentoNFe.chave`). O evento só tem efeito sobre a situação com o status do
    retorno em `services.CODIGOS_EFETIVOS_NFE` (135 ou 155; o 136 não cancela, HI-116).

    Unicidade por (escritório, identificador, sha256). O mesmo evento reimportado (mesmo Id e
    mesmo conteúdo) é duplicado. O mesmo Id com CONTEÚDO diferente é um registro novo, e não
    se perde: um retorno rejeitado seguido de um cancelamento aceito, com o mesmo Id, tem que
    cancelar a nota. A situação consulta todos os registros com `Exists`, então a ordem de
    chegada não importa.
    """

    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        on_delete=models.PROTECT,
        related_name="eventos_nfe",
    )
    # "ID" + tpEvento(6) + chave(44) + nSeqEvento(2) = 54 posições. A pesquisa
    # escreveu 52; a conta do padrão do XSD (leiauteEvento_v1.00.xsd:136) dá 54.
    identificador = models.CharField("identificador (Id) do evento", max_length=54)
    tp_evento = models.CharField("tipo do evento (tpEvento)", max_length=6)
    n_seq_evento = models.PositiveSmallIntegerField("sequência do evento (nSeqEvento)")
    chave = models.CharField("chave de acesso da nota (chNFe)", max_length=44)
    dh_evento = models.DateTimeField("data/hora do evento (dhEvento)")
    autor_tipo_documento = models.CharField(
        "tipo de documento do autor", max_length=14, choices=TipoParticipanteNFe.choices
    )
    autor_documento = models.CharField("documento do autor", max_length=14)
    # Status do retorno (retEvento/infEvento/cStat). `None` quando o retorno não vem:
    # sem retorno, o evento não tem efeito sobre a situação.
    c_stat = models.CharField("status do retorno (cStat)", max_length=4, null=True, blank=True)
    xml_original = models.BinaryField("XML original", editable=False)
    sha256_arquivo = models.CharField("SHA-256 do arquivo", max_length=64)
    # Empresa do escritório que é o autor do evento, quando o CNPJ/CPF casa com ela.
    # NULL é o caso normal do órfão (autor de outro escritório, ou nenhum cliente).
    empresa = models.ForeignKey(
        Empresa,
        verbose_name="empresa (quando identificável)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eventos_nfe",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "evento de NF-e"
        verbose_name_plural = "eventos de NF-e"
        ordering = ["-dh_evento"]
        constraints = [
            models.UniqueConstraint(
                fields=["escritorio", "identificador", "sha256_arquivo"],
                name="evento_nfe_unico_por_identificador_e_conteudo",
            ),
        ]
        indexes = [
            # A situação "cancelada" consulta por (escritório, chave) a cada lista.
            models.Index(fields=["escritorio", "chave"], name="evento_nfe_escritorio_chave"),
        ]

    def __str__(self):
        return f"{self.tp_evento} — {self.identificador} ({self.escritorio})"


# ---------------------------------------------------------------------------
# DL-072 (frente A): escrituração das NFS-e prestadas.
#
# O catálogo de natureza é FECHADO e vive em código (HI-56): é o contador
# quem escolhe, entre estas seis, a natureza de cada nota prestada. Nenhuma
# delas carrega alíquota nesta etapa — alíquota, imposto e guia ficam para as
# etapas seguintes, cada uma com fonte oficial e vigência.
#
# A antiga "sem incidência de ISS" foi DESDOBRADA (HI-67): exportação, ISS
# imune/isento/reduzido e serviço fora da lista da LC 116 têm tratamentos
# diferentes (mercado, base, RBT12 e ISS), e um valor único os misturava.
# ---------------------------------------------------------------------------


class NaturezaOperacao(models.TextChoices):
    PRESTADO_ISS_DEVIDO_PRESTADOR = (
        "prestado_iss_devido_prestador",
        "Serviço prestado — ISS devido pelo prestador",
    )
    PRESTADO_ISS_RETIDO = (
        "prestado_iss_retido",
        "Serviço prestado — ISS retido pelo tomador ou pelo intermediário",
    )
    PRESTADO_ISS_OUTRO_MUNICIPIO = (
        "prestado_iss_outro_municipio",
        "Serviço prestado — ISS devido a outro município",
    )
    PRESTADO_EXPORTACAO_SERVICO = (
        "prestado_exportacao_servico",
        "Serviço prestado — exportação de serviço (mercado externo)",
    )
    PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO = (
        "prestado_iss_imune_isento_reduzido",
        "Serviço prestado — ISS imune, isento ou reduzido por lei do ente",
    )
    PRESTADO_FORA_LISTA_LC116 = (
        "prestado_fora_lista_lc116",
        "Serviço prestado — fora da lista da LC 116 (sem ISS)",
    )


# Naturezas de mercado EXTERNO. Só a exportação é externa; as outras cinco
# são mercado interno. Esta é a ÚNICA definição do mercado de uma natureza:
# a escrituração e, depois, a apuração do Simples (bases, RBT12 e limites
# separados por mercado, HI-67) devem consultá-la, nunca repetir a regra.
#
# Por que só a exportação: a definição de exportação de serviço é a da Res.
# CGSN 140 art. 25 § 4º (que repete LC 116 art. 2º, parágrafo único), e a
# separação dos mercados para alíquota, base e limites está em LC 123 art. 3º
# §§ 14 e 15. ISS imune/isento/reduzido por lei do ente e serviço fora da lista
# continuam no mercado INTERNO: a lei municipal afeta só a parcela do ISS, não
# a origem da receita (Res. CGSN 140 art. 25 § 10). Fonte: HI-67 (requisitos.md).
_NATUREZAS_DE_MERCADO_EXTERNO = frozenset({NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO})


def mercado_da_natureza(natureza: str) -> str:
    """Mercado da natureza: "externo" para exportação de serviço, "interno" para as demais.

    Recusa valor fora do catálogo com `ValueError`: um valor desconhecido
    NÃO vira "interno" em silêncio, porque isso mudaria a base do Simples.
    """
    if natureza not in NaturezaOperacao.values:
        raise ValueError(f"natureza fora do catálogo: {natureza!r}")
    if natureza in _NATUREZAS_DE_MERCADO_EXTERNO:
        return "externo"
    return "interno"


class EstadoEscrituracao(models.TextChoices):
    """Rascunho e efetivada são estados DIFERENTES e distinguíveis (regra
    do CLAUDE.md): só a efetivada conta na apuração. A estornada fica no
    histórico, nunca é reaproveitada."""

    RASCUNHO = "rascunho", "Rascunho"
    EFETIVADA = "efetivada", "Efetivada"
    ESTORNADA = "estornada", "Estornada"


class EscrituracaoFiscal(models.Model):
    """Escrituração de UMA NFS-e prestada por UMA empresa cliente (DL-072).

    Uma linha por vínculo e por tentativa de escrituração: uma efetivada
    estornada não é reaberta — um novo ato cria OUTRA linha, e a trilha
    guarda as duas. Por isso a unicidade é PARCIAL: no banco, no máximo uma
    linha NÃO estornada (rascunho ou efetivada) por vínculo.

    Valores (`data_emissao`, `data_competencia`, `valor_servico`,
    `valor_liquido`, `iss_retido`) são COPIADOS do `DocumentoFiscal` no ato
    de efetivar: a escrituração não recalcula imposto e não depende de o
    documento continuar sendo lido igual (o XML original fica no documento).
    `data_competencia` é `dCompet` — define o mês da escrituração (HI-57);
    `data_emissao` é o DIA ESCRITO no `dhEmi`, no fuso do emitente (HI-72), só
    para o aviso de competência diferente da emissão e para a exibição.

    Imutabilidade, em três camadas (DE-008):
    1. `save()` recusa alterar linha que já está efetivada ou estornada
       (`EscrituracaoImutavel`). `delete()` recusa linha que não seja rascunho.
    2. Os serviços mudam estado com `QuerySet.update()` condicionado ao
       estado anterior, e o BANCO (gatilho da migração 0002) só aceita as
       transições rascunho→efetivada e efetivada→estornada, e só alterando
       as colunas do ato.
    3. A coerência entre estado e colunas preenchidas é `CheckConstraint`.

    Limite declarado: `TRUNCATE` não aciona gatilho de linha (mesmo limite da
    DL-052); quem tem privilégio de dono da tabela está fora do que o banco
    impede sozinho.
    """

    vinculo = models.ForeignKey(
        VinculoDocumentoEmpresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_fiscais",
        verbose_name="vínculo documento-empresa",
    )
    # Redundante com `vinculo.empresa`, de propósito: a consulta "as
    # escriturações desta empresa" e o isolamento por empresa não precisam
    # atravessar o vínculo. A igualdade é garantida em `save()` e pelo
    # gatilho do banco (`escrituracao_vinculo_prestador_da_empresa`).
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_fiscais",
        verbose_name="empresa",
    )
    natureza = models.CharField(
        "natureza da operação", max_length=40, choices=NaturezaOperacao.choices
    )
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoEscrituracao.choices,
        default=EstadoEscrituracao.RASCUNHO,
    )
    data_emissao = models.DateField("data de emissão (dia do dhEmi)", null=True, blank=True)
    data_competencia = models.DateField("data de competência (dCompet)", null=True, blank=True)
    # DE-010: Decimal com a MESMA escala do documento (max_digits=17, 2 casas).
    valor_servico = models.DecimalField(
        "valor do serviço", max_digits=17, decimal_places=2, null=True, blank=True
    )
    valor_liquido = models.DecimalField(
        "valor líquido", max_digits=17, decimal_places=2, null=True, blank=True
    )
    # True quando tpRetISSQN é 2 (tomador) ou 3 (intermediário). Copiado do
    # documento; a natureza escolhida pelo contador pode divergir disso e
    # isso fica registrado na trilha, não é bloqueado.
    iss_retido = models.BooleanField("ISS retido (tpRetISSQN 2 ou 3)", null=True, blank=True)
    efetivada_em = models.DateTimeField("efetivada em", null=True, blank=True)
    efetivada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="efetivada por",
    )
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "escrituração fiscal"
        verbose_name_plural = "escriturações fiscais"
        ordering = ["id"]
        constraints = [
            # HI/DL-072 critério 6: no máximo UMA escrituração não estornada
            # por vínculo, no banco. Uma efetivação concorrente que passe pela
            # trava de `select_for_update` ainda assim não cria duplicata.
            models.UniqueConstraint(
                fields=["vinculo"],
                condition=Q(estado__in=["rascunho", "efetivada"]),
                name="escrituracao_ativa_unica_por_vinculo",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["rascunho", "efetivada", "estornada"]),
                name="escrituracao_estado_valido",
            ),
            # Coerência entre estado e colunas do ato. Cada ramo é um estado:
            # - rascunho: nada de efetivação nem de estorno;
            # - efetivada: efetivação completa (quem, quando, valores copiados)
            #   e nenhum estorno;
            # - estornada: tudo da efetivação mais quem/quando/por que estornou.
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="rascunho",
                        efetivada_em__isnull=True,
                        efetivada_por__isnull=True,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        estado="efetivada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        data_emissao__isnull=False,
                        data_competencia__isnull=False,
                        valor_servico__isnull=False,
                        valor_liquido__isnull=False,
                        iss_retido__isnull=False,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        ~Q(motivo_estorno=""),
                        estado="estornada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        data_emissao__isnull=False,
                        data_competencia__isnull=False,
                        valor_servico__isnull=False,
                        valor_liquido__isnull=False,
                        iss_retido__isnull=False,
                        estornada_em__isnull=False,
                        estornada_por__isnull=False,
                    )
                ),
                name="escrituracao_campos_coerentes_com_o_estado",
            ),
        ]

    def __str__(self):
        return f"Escrituração {self.pk} — vínculo {self.vinculo_id} ({self.get_estado_display()})"

    def _estado_gravado(self):
        # Lê o estado GRAVADO, não o do objeto em memória: o objeto pode ter
        # sido alterado em Python (ou estar desatualizado) antes do save/delete.
        return (
            EscrituracaoFiscal.objects.filter(pk=self.pk).values_list("estado", flat=True).first()
        )

    def save(self, *args, **kwargs):
        # Regra de papel e de empresa, também no modelo: só o vínculo de
        # PRESTADOR da MESMA empresa pode ser escriturado (DL-072, plano). O
        # serviço já recusa antes; isto impede que um `objects.create()` ou
        # um `save()` direto contorne a regra.
        if self.vinculo.papel != PapelDocumento.PRESTADOR:
            raise ValidationError("Só a nota em que a empresa é prestadora pode ser escriturada.")
        if self.empresa_id != self.vinculo.empresa_id:
            raise ValidationError("A escrituração deve ser da mesma empresa do vínculo.")
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel(
                "Escrituração efetivada ou estornada não pode ser excluída; "
                "o histórico é preservado pelo estorno."
            )
        return super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# DL-078 (frente A): escrituração das NFS-e TOMADAS. Registro PRÓPRIO, separado da
# `EscrituracaoFiscal` (HI-93): a nota tomada nunca aparece em receita, RBT12, pré-DAS nem no
# ISS próprio, porque esses leem só as escriturações prestadas. Plano: DL-078 e consulta de
# 08/10/2026 (docs/projeto/consultas/2026-10-08-contador-senior-servicos-tomados.md).


class NaturezaTomada(models.TextChoices):
    """Catálogo FECHADO das naturezas de serviço TOMADO (HI-93; consulta, item 1).

    T4 (importação de serviço) NÃO está aqui: o emissor nacional ainda não gera o XML
    desse caso (P&R 7.8). A nota com tpEmit 2 ou 3 é recusada antes de qualquer natureza
    (`apps.fiscal.tomadas`), porque tpEmit 2 não é só importação (cMotivoEmisTI).
    """

    TOMADO_ISS_RETIDO_PELO_CLIENTE = (
        "tomado_iss_retido_pelo_cliente",
        "Tomado — ISS retido pelo cliente tomador (T1)",
    )
    TOMADO_SEM_RETENCAO = ("tomado_sem_retencao", "Tomado — ISS do prestador, sem retenção (T2)")
    TOMADO_PRESTADOR_OUTRO_MUNICIPIO = (
        "tomado_prestador_outro_municipio",
        "Tomado — prestador de outro município (T3)",
    )
    TOMADO_DE_MEI = ("tomado_de_mei", "Tomado de MEI (T5)")
    TOMADO_DE_SIMPLES = ("tomado_de_simples", "Tomado de ME/EPP do Simples Nacional (T6)")
    TOMADO_DE_PESSOA_FISICA = ("tomado_de_pessoa_fisica", "Tomado de pessoa física (T7)")


class EscrituracaoTomada(models.Model):
    """Escrituração de UMA NFS-e tomada por UMA empresa cliente, como TOMADORA (DL-078).

    Mesmo desenho da `EscrituracaoFiscal` (DL-072): uma linha por vínculo e por tentativa;
    uma efetivada estornada não é reaberta; no máximo uma linha não estornada por vínculo,
    no banco. Os valores são COPIADOS do documento e do XML guardado no ato de efetivar, para
    que o registro reproduza a escrituração sem reler o XML.

    A DATA DE PAGAMENTO (`data_pagamento`) é a única coluna que muda depois de efetivada. Ela
    é informada pelo contador, com quem e quando informou e motivo, e é o que agrupa o IRRF e
    a CSRF (HI-96). Sem ela, a retenção fica pendente, nunca presumida.

    Imutabilidade, em três camadas, como a DL-072:
    1. `save()` recusa alterar linha efetivada ou estornada; `delete()` recusa linha que não
       seja rascunho (`EscrituracaoImutavel`).
    2. Os serviços mudam estado com `QuerySet.update()` condicionado ao estado anterior. O
       BANCO (gatilhos da migração 0008) só aceita as transições rascunho→efetivada,
       efetivada→estornada e a alteração das colunas de pagamento numa efetivada.
    3. A coerência entre estado e colunas é `CheckConstraint`.

    Limite declarado: `TRUNCATE` não aciona gatilho de linha (mesmo limite da DL-052 e da
    DL-072); quem tem privilégio de dono da tabela está fora do que o banco impede sozinho.
    """

    vinculo = models.ForeignKey(
        VinculoDocumentoEmpresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_tomadas",
        verbose_name="vínculo documento-empresa",
    )
    # Redundante com `vinculo.empresa`, como na escrituração prestada: a consulta por empresa
    # não atravessa o vínculo. A igualdade é garantida em `save()` e pelo gatilho do banco.
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_tomadas",
        verbose_name="empresa",
    )
    natureza = models.CharField(
        "natureza da operação", max_length=40, choices=NaturezaTomada.choices
    )
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoEscrituracao.choices,
        default=EstadoEscrituracao.RASCUNHO,
    )
    # Copiados do documento e do XML guardado na efetivação. Nulos enquanto for rascunho.
    # `data_emissao` é o dia do dhEmi (HI-72); `data_competencia` é o dCompet (HI-94/HI-96).
    data_emissao = models.DateField("data de emissão (dia do dhEmi)", null=True, blank=True)
    data_competencia = models.DateField("data de competência (dCompet)", null=True, blank=True)
    prestador_tipo_documento = models.CharField(
        "tipo de documento do prestador", max_length=20, blank=True, default=""
    )
    tp_emit = models.CharField("emitente da DPS (tpEmit)", max_length=1, null=True, blank=True)
    tp_ret_issqn = models.CharField(
        "tipo de retenção do ISSQN (tpRetISSQN)", max_length=1, null=True, blank=True
    )
    c_loc_incid = models.CharField(
        "município de incidência (cLocIncid)", max_length=7, null=True, blank=True
    )
    op_simp_nac = models.CharField(
        "situação no Simples Nacional (opSimpNac)", max_length=1, null=True, blank=True
    )
    reg_ap_trib_sn = models.CharField(
        "regime de apuração no Simples (regApTribSN)", max_length=1, null=True, blank=True
    )
    # Valores em Decimal com a escala do documento (TSDec15V2, duas casas). NULO é "não
    # destacado no XML", e nunca zero (ausência ≠ zero).
    valor_servico = models.DecimalField(
        "valor do serviço (vServ)", max_digits=17, decimal_places=2, null=True, blank=True
    )
    valor_liquido = models.DecimalField(
        "valor líquido (vLiq)", max_digits=17, decimal_places=2, null=True, blank=True
    )
    v_desc_incond = models.DecimalField(
        "desconto incondicionado (vDescIncond)",
        max_digits=17,
        decimal_places=2,
        null=True,
        blank=True,
    )
    v_desc_cond = models.DecimalField(
        "desconto condicionado (vDescCond)", max_digits=17, decimal_places=2, null=True, blank=True
    )
    v_iss_qn = models.DecimalField(
        "ISSQN destacado (vISSQN)", max_digits=17, decimal_places=2, null=True, blank=True
    )
    v_ret_cp = models.DecimalField(
        "contribuição previdenciária retida (vRetCP)",
        max_digits=17,
        decimal_places=2,
        null=True,
        blank=True,
    )
    v_ret_irrf = models.DecimalField(
        "IRRF retido (vRetIRRF)", max_digits=17, decimal_places=2, null=True, blank=True
    )
    v_ret_csll = models.DecimalField(
        "CSLL retida, com PIS e COFINS somados (vRetCSLL)",
        max_digits=17,
        decimal_places=2,
        null=True,
        blank=True,
    )
    tp_ret_pis_cofins = models.CharField(
        "tipo de retenção do PIS/COFINS (tpRetPisCofins)", max_length=1, null=True, blank=True
    )
    # vPis e vCofins são débito PRÓPRIO do prestador (não retenção). Não entram no total.
    v_pis = models.DecimalField(
        "PIS, débito próprio do prestador (vPis)",
        max_digits=17,
        decimal_places=2,
        null=True,
        blank=True,
    )
    v_cofins = models.DecimalField(
        "COFINS, débito próprio do prestador (vCofins)",
        max_digits=17,
        decimal_places=2,
        null=True,
        blank=True,
    )
    efetivada_em = models.DateTimeField("efetivada em", null=True, blank=True)
    efetivada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="efetivada por",
    )
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")
    # Data em que o contador informou que o valor foi pago ou creditado (HI-96). Opcional.
    # Alterável depois de efetivada, e só ela: `pagamento_informado_*` e `motivo_pagamento`
    # acompanham a alteração, e a trilha guarda o antes e o depois.
    data_pagamento = models.DateField("data de pagamento informada", null=True, blank=True)
    pagamento_informado_em = models.DateTimeField(
        "data de pagamento informada em", null=True, blank=True
    )
    pagamento_informado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="pagamento informado por",
    )
    motivo_pagamento = models.CharField(
        "motivo da data de pagamento", max_length=500, blank=True, default=""
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "escrituração de nota tomada"
        verbose_name_plural = "escriturações de notas tomadas"
        ordering = ["id"]
        constraints = [
            # DL-078 critério 2: no máximo UMA escrituração não estornada por vínculo, no banco.
            models.UniqueConstraint(
                fields=["vinculo"],
                condition=Q(estado__in=["rascunho", "efetivada"]),
                name="escrituracao_tomada_ativa_unica_por_vinculo",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["rascunho", "efetivada", "estornada"]),
                name="escrituracao_tomada_estado_valido",
            ),
            # Coerência entre estado e colunas do ato. Efetivada exige os campos copiados que o
            # relatório usa: data, competência, valores, tpRetISSQN e tpEmit.
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="rascunho",
                        efetivada_em__isnull=True,
                        efetivada_por__isnull=True,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        estado="efetivada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        data_emissao__isnull=False,
                        data_competencia__isnull=False,
                        valor_servico__isnull=False,
                        valor_liquido__isnull=False,
                        tp_ret_issqn__isnull=False,
                        tp_emit__isnull=False,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        ~Q(motivo_estorno=""),
                        estado="estornada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        data_emissao__isnull=False,
                        data_competencia__isnull=False,
                        valor_servico__isnull=False,
                        valor_liquido__isnull=False,
                        tp_ret_issqn__isnull=False,
                        tp_emit__isnull=False,
                        estornada_em__isnull=False,
                        estornada_por__isnull=False,
                    )
                ),
                name="escrituracao_tomada_campos_coerentes_com_o_estado",
            ),
            # Data de pagamento só com quem informou, quando e por quê (trilha no próprio registro).
            models.CheckConstraint(
                condition=(
                    Q(data_pagamento__isnull=True)
                    | (
                        Q(data_pagamento__isnull=False)
                        & Q(pagamento_informado_em__isnull=False)
                        & Q(pagamento_informado_por__isnull=False)
                        & ~Q(motivo_pagamento="")
                    )
                ),
                name="escrituracao_tomada_pagamento_com_informante",
            ),
        ]

    def __str__(self):
        return (
            f"Escrituração de tomada {self.pk} — vínculo {self.vinculo_id} "
            f"({self.get_estado_display()})"
        )

    def _estado_gravado(self):
        # Lê o estado GRAVADO, não o do objeto em memória (mesma regra da escrituração prestada).
        return (
            EscrituracaoTomada.objects.filter(pk=self.pk).values_list("estado", flat=True).first()
        )

    def save(self, *args, **kwargs):
        # Só o vínculo de TOMADOR da MESMA empresa pode ser escriturado aqui. O serviço já recusa
        # antes; isto impede que um `objects.create()` contorne a regra.
        if self.vinculo.papel != PapelDocumento.TOMADOR:
            raise ValidationError(
                "Só a nota em que a empresa é tomadora pode ser escriturada aqui."
            )
        if self.empresa_id != self.vinculo.empresa_id:
            raise ValidationError("A escrituração deve ser da mesma empresa do vínculo.")
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel(
                "Escrituração de nota tomada efetivada ou estornada não pode ser excluída; "
                "o histórico é preservado pelo estorno."
            )
        return super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# DL-074 (frente A): receita mensal do Simples Nacional por mercado.
#
# A receita bruta do Simples é a receita TOTAL da empresa (Res. CGSN 140 art.
# 2º, II e §§ 4º a 8º; HI-64): a soma das notas escrituradas não basta. O mês
# entra no RBT12 por três peças, todas aqui:
#
# 1. escriturações efetivadas (DL-072), com o mercado dado pela natureza;
# 2. receitas informadas CONFIRMADAS (`ReceitaInformada`), com origem fechada;
# 3. a CONFIRMAÇÃO do mês (`ConfirmacaoReceitaMensal`), ato do contador que
#    declara "receita de MM/AAAA completa". Só mês confirmado conta no RBT12.
#
# O mercado (interno/externo) é a segunda base do Simples: exportação e
# mercado interno têm RBT12 e limites separados (HI-67). Por isso TODA receita
# informada carrega mercado, e a exportação nunca soma no interno.
#
# Valores monetários: `DecimalField(17, 2)`, o mesmo do documento (DE-010).
# Nenhum cálculo aqui arredonda; o RBT12 fica em `apps.fiscal.rbt12`.
# ---------------------------------------------------------------------------


class MercadoReceita(models.TextChoices):
    INTERNO = "interno", "Mercado interno"
    EXTERNO = "externo", "Mercado externo (exportação de serviço)"


class OrigemReceitaInformada(models.TextChoices):
    """Catálogo FECHADO de origem (plano DL-074, item 2). Só alterado por
    decisão do Fred. "Histórico" tem regra própria: só vale antes do início de
    uso do sistema pela empresa (ver `apps.fiscal.receita.inicio_de_uso`)."""

    HISTORICO_PRE_SISTEMA = "historico_pre_sistema", "Histórico anterior ao uso do sistema"
    MERCADORIA_NAO_ESCRITURADA = (
        "mercadoria_nao_escriturada",
        "Venda de mercadoria ainda não escriturada",
    )
    SERVICO_DOCUMENTO_NAO_INTEGRADO = (
        "servico_documento_nao_integrado",
        "Serviço com documento de município não integrado",
    )
    OUTRAS_RECEITAS_ATIVIDADE = (
        "outras_receitas_atividade",
        "Outras receitas da atividade (Res. CGSN 140, art. 2º, § 4º)",
    )
    AJUSTE = "ajuste", "Ajuste ou retificação"


class EstadoReceitaInformada(models.TextChoices):
    """Rascunho, confirmada e estornada são estados distintos: só a confirmada
    conta na receita do mês (regra do CLAUDE.md: rascunho é distinguível)."""

    RASCUNHO = "rascunho", "Rascunho"
    CONFIRMADA = "confirmada", "Confirmada"
    ESTORNADA = "estornada", "Estornada"


class SituacaoIssReceitaInformada(models.TextChoices):
    """Situação do ISS de uma receita informada de serviço no mercado INTERNO (HI-80).

    Obrigatória no mercado interno e proibida na exportação. Sem ela o pré-DAS não
    sabe se o ISS é do DAS, de outro município ou retido, e a regra não presume:
    presumir "próprio município" duplica o ISS retido ou o destina ao ente errado
    (LC 123, art. 18, § 4º-A; Res. CGSN 140, art. 25, § 9º; consulta de 08/10/2026,
    item 4). Os valores são o catálogo do PGDAS-D (Manual, itens 6.5 e 6.6).
    """

    PROPRIO_MUNICIPIO = "proprio_municipio", "ISS devido ao próprio município"
    OUTRO_MUNICIPIO = "outro_municipio", "ISS devido a outro município"
    RETIDO = "retido", "ISS retido ou substituído pelo tomador"


class EstadoConfirmacaoMes(models.TextChoices):
    CONFIRMADA = "confirmada", "Confirmada"
    # Reaberta: o mês voltou a não estar completo. `a_retificar=True` quando a
    # reabertura veio de estorno de escrituração/receita (Res. 140 art. 18).
    REABERTA = "reaberta", "Reaberta"


class ReceitaInformadaImutavel(Exception):
    """Receita informada confirmada ou estornada não se altera nem se exclui por
    `save()`/`delete()`. A correção é estorno com motivo. Mesma ideia de
    `EscrituracaoImutavel` (DL-072); o banco também recusa (migração 0003)."""

    mensagem_padrao = (
        "Receita informada confirmada não pode ser alterada nem excluída; "
        "estorne com motivo para corrigir."
    )

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)
        self.mensagem = mensagem or self.mensagem_padrao


class ConfirmacaoImutavel(Exception):
    """A confirmação de um mês só muda pelos serviços de `apps.fiscal.receita`,
    por `QuerySet.update()` condicionado ao estado. `save()` em linha existente
    e `delete()` são recusados aqui e pelo banco (migração 0003)."""

    mensagem_padrao = (
        "A confirmação de receita mensal só muda pelos serviços de confirmação e "
        "reabertura, com trilha; não é alterada nem excluída diretamente."
    )

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)
        self.mensagem = mensagem or self.mensagem_padrao


class ReceitaInformada(models.Model):
    """Receita que NÃO veio de uma escrituração: histórico, mercadoria, serviço
    sem documento integrado, outras receitas da atividade, ajuste (DL-074, item 2).

    `motivo` e `documento_suporte` são obrigatórios: a receita informada é
    declaração do contador, e o RBT12 a usa. Exemplo de suporte: "extrato
    PGDAS-D PA 03/2026". `valor` é positivo, em reais, com 2 casas.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="receitas_informadas",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano da competência")
    mes = models.PositiveSmallIntegerField("mês da competência")
    mercado = models.CharField("mercado", max_length=10, choices=MercadoReceita.choices)
    valor = models.DecimalField("valor da receita", max_digits=17, decimal_places=2)
    origem = models.CharField("origem", max_length=40, choices=OrigemReceitaInformada.choices)
    motivo = models.CharField("motivo", max_length=500)
    documento_suporte = models.CharField("documento de suporte", max_length=300)
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoReceitaInformada.choices,
        default=EstadoReceitaInformada.RASCUNHO,
    )
    criado_em = models.DateTimeField("criada em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )
    confirmada_em = models.DateTimeField("confirmada em", null=True, blank=True)
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="confirmada por",
    )
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")
    # DL-075 (HI-68): atividade que a receita descreve. Opcional; sem ela, vale a
    # atividade padrão vigente no mês (apps.fiscal.pre_das). Não muda o RBT12 nem
    # o total do mês: só o anexo em que o pré-DAS aplica a receita.
    atividade = models.ForeignKey(
        "AtividadeEmpresa",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="receitas_informadas",
        verbose_name="atividade",
    )
    # DL-075 (HI-80): situação do ISS. Obrigatória no mercado interno e NULA na exportação,
    # imposta pelo serviço (`apps.fiscal.receita.lancar_receita_informada`) e pelas duas
    # restrições abaixo. `null=True` porque a migração 0005 não reescreve linhas antigas:
    # uma receita interna confirmada sem situação é recusada pelo pré-DAS, nomeada, e o
    # estorno com novo lançamento é o caminho (a receita confirmada é imutável).
    situacao_iss = models.CharField(
        "situação do ISS",
        max_length=20,
        choices=SituacaoIssReceitaInformada.choices,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "receita informada"
        verbose_name_plural = "receitas informadas"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ano__gte=1970, ano__lte=2999, mes__gte=1, mes__lte=12),
                name="receita_informada_mes_valido",
            ),
            models.CheckConstraint(
                condition=Q(valor__gt=0), name="receita_informada_valor_positivo"
            ),
            models.CheckConstraint(
                condition=Q(
                    mercado__in=MercadoReceita.values,
                    origem__in=OrigemReceitaInformada.values,
                    estado__in=EstadoReceitaInformada.values,
                ),
                name="receita_informada_catalogos_validos",
            ),
            models.CheckConstraint(
                condition=~Q(motivo="") & ~Q(documento_suporte=""),
                name="receita_informada_campos_obrigatorios",
            ),
            # HI-80: a situação do ISS, quando há, é do catálogo fechado; e a exportação não
            # tem situação de ISS (o PGDAS-D não oferece essa opção na atividade de exportação).
            models.CheckConstraint(
                condition=Q(situacao_iss__isnull=True)
                | Q(situacao_iss__in=SituacaoIssReceitaInformada.values),
                name="receita_informada_situacao_iss_valida",
            ),
            models.CheckConstraint(
                condition=Q(mercado=MercadoReceita.INTERNO) | Q(situacao_iss__isnull=True),
                name="receita_informada_iss_so_no_interno",
            ),
            # Coerência entre estado e colunas do ato, como em
            # `escrituracao_campos_coerentes_com_o_estado` (DL-072).
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="rascunho",
                        confirmada_em__isnull=True,
                        confirmada_por__isnull=True,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        estado="confirmada",
                        confirmada_em__isnull=False,
                        confirmada_por__isnull=False,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | (
                        Q(
                            estado="estornada",
                            confirmada_em__isnull=False,
                            confirmada_por__isnull=False,
                            estornada_em__isnull=False,
                            estornada_por__isnull=False,
                        )
                        & ~Q(motivo_estorno="")
                    )
                ),
                name="receita_informada_campos_coerentes_com_o_estado",
            ),
        ]

    def __str__(self):
        return (
            f"Receita informada {self.pk} — {self.ano}-{self.mes:02d} "
            f"{self.get_mercado_display()} ({self.get_estado_display()})"
        )

    def _estado_gravado(self):
        # Lê o estado GRAVADO: o objeto em memória pode estar desatualizado.
        return ReceitaInformada.objects.filter(pk=self.pk).values_list("estado", flat=True).first()

    def save(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() != EstadoReceitaInformada.RASCUNHO:
            raise ReceitaInformadaImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() != EstadoReceitaInformada.RASCUNHO:
            raise ReceitaInformadaImutavel(
                "Receita informada confirmada ou estornada não pode ser excluída; "
                "o histórico é preservado pelo estorno."
            )
        return super().delete(*args, **kwargs)


class ConfirmacaoReceitaMensal(models.Model):
    """Ato "receita de MM/AAAA completa" da empresa, para os DOIS mercados (DL-074,
    item 4). Uma linha por empresa e mês; o histórico de atos fica na trilha.

    `valor_confirmado_interno`/`_externo` são o total do mês NO INSTANTE da
    confirmação. Comparado com o total atual, mostra se a receita mudou depois
    por um caminho que não passou pelos ganchos de serviço (estorno e efetivação
    em mês confirmado reabrem a confirmação com trilha — `marcar_a_retificar` em
    `apps/fiscal/receita.py`). Mudou → o mês é "a retificar" e não entra no
    RBT12: é a segunda camada, para o que escapar dos ganchos.

    Limite declarado (A8, auditoria DL-074 rodada 1): na transição reaberta -> confirmada,
    o gatilho da migração 0003 aceita novos totais. Um UPDATE SQL direto nessa transição
    pode regravar `valor_confirmado_interno`/`_externo`, porque o banco não confere o total
    com a composição do mês. Os serviços não fazem isso. É o mesmo limite do TRUNCATE.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="confirmacoes_receita_mensal",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano da competência")
    mes = models.PositiveSmallIntegerField("mês da competência")
    estado = models.CharField(
        "estado",
        max_length=10,
        choices=EstadoConfirmacaoMes.choices,
        default=EstadoConfirmacaoMes.CONFIRMADA,
    )
    valor_confirmado_interno = models.DecimalField(
        "receita confirmada — interno", max_digits=17, decimal_places=2
    )
    valor_confirmado_externo = models.DecimalField(
        "receita confirmada — externo", max_digits=17, decimal_places=2
    )
    confirmada_em = models.DateTimeField("confirmada em")
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="confirmada por",
    )
    a_retificar = models.BooleanField("a retificar", default=False)
    reaberta_em = models.DateTimeField("reaberta em", null=True, blank=True)
    reaberta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="reaberta por",
    )
    motivo_reabertura = models.CharField(
        "motivo da reabertura", max_length=500, blank=True, default=""
    )
    criado_em = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "confirmação de receita mensal"
        verbose_name_plural = "confirmações de receita mensal"
        ordering = ["empresa_id", "ano", "mes"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "ano", "mes"],
                name="confirmacao_mes_unica_por_empresa",
            ),
            models.CheckConstraint(
                condition=Q(ano__gte=1970, ano__lte=2999, mes__gte=1, mes__lte=12),
                name="confirmacao_mes_valido",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoConfirmacaoMes.values),
                name="confirmacao_estado_valido",
            ),
            models.CheckConstraint(
                condition=Q(valor_confirmado_interno__gte=0, valor_confirmado_externo__gte=0),
                name="confirmacao_valores_nao_negativos",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="confirmada",
                        reaberta_em__isnull=True,
                        reaberta_por__isnull=True,
                        motivo_reabertura="",
                        a_retificar=False,
                    )
                    | (
                        Q(
                            estado="reaberta",
                            reaberta_em__isnull=False,
                            reaberta_por__isnull=False,
                        )
                        & ~Q(motivo_reabertura="")
                    )
                ),
                name="confirmacao_campos_coerentes_com_o_estado",
            ),
        ]

    def __str__(self):
        return (
            f"Confirmação {self.ano}-{self.mes:02d} — empresa {self.empresa_id} "
            f"({self.get_estado_display()})"
        )

    def save(self, *args, **kwargs):
        # Só a criação passa por `save()`; a mudança de estado é `update()` nos serviços.
        if self.pk is not None:
            raise ConfirmacaoImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ConfirmacaoImutavel(
            "A confirmação de receita mensal não é excluída; a reabertura, com motivo, "
            "fica na trilha."
        )


class OpcaoRegimeCaixaSimples(models.Model):
    """Opção pelo regime de CAIXA no Simples Nacional, por ano-calendário (HI-66).

    Escolha: uma tabela pequena, não um campo no `HistoricoRegimeTributario`.
    Motivo: a opção é anual e irretratável no ano (Res. CGSN 140 art. 16 § 1º,
    hipótese), e o histórico de regime é por vigência de dias. Gravar o ano no
    histórico obrigaria a mexer no serviço e no admin do regime, que são de outro
    módulo. Linha existente = empresa optou pelo caixa naquele ano; sem linha = competência.
    Só até 2026: a opção acaba no PA 12/2026 (HI-66; LC 214/2025, art. 517 c/c 544, III).
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="opcoes_regime_caixa_simples",
        verbose_name="empresa",
    )
    ano_calendario = models.PositiveSmallIntegerField("ano-calendário")
    registrada_em = models.DateTimeField("registrada em", auto_now_add=True)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="registrada por",
    )

    class Meta:
        verbose_name = "opção pelo regime de caixa (Simples)"
        verbose_name_plural = "opções pelo regime de caixa (Simples)"
        ordering = ["empresa_id", "ano_calendario"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "ano_calendario"],
                name="opcao_caixa_unica_por_ano",
            ),
            models.CheckConstraint(
                condition=Q(ano_calendario__gte=2000, ano_calendario__lte=2026),
                name="opcao_caixa_so_ate_2026",
            ),
        ]

    def __str__(self):
        return f"Regime de caixa em {self.ano_calendario} — empresa {self.empresa_id}"


# ---------------------------------------------------------------------------
# DL-075 (frente A): atividades da empresa e folha para o fator r.
#
# Atividade (HI-68): o pré-DAS aplica cada receita a um ANEXO, e o anexo depende
# da atividade que a receita descreve. O catálogo do enquadramento é FECHADO e
# vem do contador, com dispositivo citado em `apps.fiscal.simples_tabelas`.
# O código do subitem (LC 116 / cTribNac) é só informativo: NÃO deriva o
# enquadramento (a norma enquadra por atividade, não por código; consulta
# contador-senior, item 5).
#
# Folha (HI-69): o fator r usa a folha de salários dos 12 meses anteriores
# (LC 123 art. 18 §§ 5º-K e 24). Cada mês é um lançamento com componentes
# separados, confirmado como a receita informada e imutável depois de confirmado.
# ---------------------------------------------------------------------------


class EnquadramentoAtividade(models.TextChoices):
    ANEXO_III = "anexo_iii", "Anexo III (sem fator r)"
    ANEXO_III_OU_V_FATOR_R = "anexo_iii_ou_v_fator_r", "Anexo III ou V, pelo fator r"
    ANEXO_IV = "anexo_iv", "Anexo IV (CPP fora do DAS)"


class AtividadeEmpresa(models.Model):
    """Atividade que a empresa presta, com enquadramento e vigência (DL-075, item 2).

    `padrao=True` marca a atividade que a escrituração usa (por nota fica para
    depois). Só pode haver UMA padrão em aberto por empresa, garantido no banco
    pela constraint `atividade_padrao_unica_em_aberto`. Padrões com vigência
    fechada não se sobrepõem por constraint: o serviço recusa a sobreposição.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="atividades_fiscais",
        verbose_name="empresa",
    )
    descricao = models.CharField("descrição da atividade", max_length=200)
    codigo_subitem = models.CharField(
        "código do subitem (LC 116 / cTribNac), informativo",
        max_length=20,
        blank=True,
        default="",
    )
    enquadramento = models.CharField(
        "enquadramento", max_length=32, choices=EnquadramentoAtividade.choices
    )
    inicio = models.DateField("início da vigência")
    fim = models.DateField("fim da vigência", null=True, blank=True)
    padrao = models.BooleanField("atividade padrão da empresa", default=False)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "atividade da empresa (Simples)"
        verbose_name_plural = "atividades da empresa (Simples)"
        ordering = ["empresa_id", "inicio", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__isnull=True) | Q(fim__gte=F("inicio")),
                name="atividade_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=Q(enquadramento__in=EnquadramentoAtividade.values),
                name="atividade_enquadramento_valido",
            ),
            models.UniqueConstraint(
                fields=["empresa"],
                condition=Q(padrao=True, fim__isnull=True),
                name="atividade_padrao_unica_em_aberto",
            ),
        ]

    def __str__(self):
        return f"Atividade {self.pk} — {self.descricao} ({self.get_enquadramento_display()})"

    def cobre_o_mes(self, ano: int, mes: int) -> bool:
        """True se a vigência cobre o mês INTEIRO (1º ao último dia).

        Mês parcialmente coberto não conta: a apuração é mensal e uma troca de
        atividade no meio do mês não tem anexo único para o mês (o pré-DAS recusa).
        """
        primeiro = date(ano, mes, 1)
        ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
        return self.inicio <= primeiro and (self.fim is None or self.fim >= ultimo)


class EstadoFolhaFatorR(models.TextChoices):
    """Rascunho, confirmada e estornada são estados distintos. Só a confirmada
    entra no FS12 do fator r (regra do CLAUDE.md: rascunho é distinguível)."""

    RASCUNHO = "rascunho", "Rascunho"
    CONFIRMADA = "confirmada", "Confirmada"
    ESTORNADA = "estornada", "Estornada"


class FolhaImutavel(Exception):
    """Folha confirmada ou estornada não se altera nem se exclui por `save()`/`delete()`.
    A correção é estorno com motivo. O banco também recusa (migração 0004)."""

    mensagem_padrao = (
        "Folha confirmada não pode ser alterada nem excluída; estorne com motivo para corrigir."
    )

    def __init__(self, mensagem=None):
        super().__init__(mensagem or self.mensagem_padrao)
        self.mensagem = mensagem or self.mensagem_padrao


class FolhaFatorR(models.Model):
    """Folha de UM mês de UMA empresa, para o fator r (DL-075, item 3; HI-69).

    Componentes (LC 123 art. 18 § 24; Res. CGSN 140 art. 26 § 2º, II, pelo consulta
    contador-senior, item 6): remuneração base INSS de empregados e avulsos;
    pró-labore e autônomos; 13º na competência da incidência; CPP recolhida
    (inclusive a dentro do DAS); FGTS recolhido. Fora: aluguéis e lucros.

    Valores em `DecimalField(17, 2)`, o mesmo da receita (DE-010). `documento_suporte`
    é a fonte (ex.: "GFIP/eSocial 03/2026; guias da CPP e do FGTS").
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="folhas_fator_r",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano da competência")
    mes = models.PositiveSmallIntegerField("mês da competência")
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoFolhaFatorR.choices,
        default=EstadoFolhaFatorR.RASCUNHO,
    )
    remuneracao_empregados_avulsos = models.DecimalField(
        "remuneração base INSS — empregados e avulsos", max_digits=17, decimal_places=2
    )
    pro_labore_autonomos = models.DecimalField(
        "pró-labore e autônomos", max_digits=17, decimal_places=2
    )
    decimo_terceiro = models.DecimalField("13º salário", max_digits=17, decimal_places=2)
    cpp_recolhida = models.DecimalField(
        "CPP recolhida (inclusive a do DAS)", max_digits=17, decimal_places=2
    )
    fgts_recolhido = models.DecimalField("FGTS recolhido", max_digits=17, decimal_places=2)
    documento_suporte = models.CharField("documento de suporte", max_length=300)
    criado_em = models.DateTimeField("criada em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )
    confirmada_em = models.DateTimeField("confirmada em", null=True, blank=True)
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="confirmada por",
    )
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")

    COMPONENTES = (
        "remuneracao_empregados_avulsos",
        "pro_labore_autonomos",
        "decimo_terceiro",
        "cpp_recolhida",
        "fgts_recolhido",
    )

    class Meta:
        verbose_name = "folha mensal para o fator r"
        verbose_name_plural = "folhas mensais para o fator r"
        ordering = ["empresa_id", "ano", "mes", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ano__gte=1970, ano__lte=2999, mes__gte=1, mes__lte=12),
                name="folha_mes_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(remuneracao_empregados_avulsos__gte=0)
                    & Q(pro_labore_autonomos__gte=0)
                    & Q(decimo_terceiro__gte=0)
                    & Q(cpp_recolhida__gte=0)
                    & Q(fgts_recolhido__gte=0)
                ),
                name="folha_valores_nao_negativos",
            ),
            models.CheckConstraint(
                condition=~Q(documento_suporte=""),
                name="folha_campos_obrigatorios",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoFolhaFatorR.values),
                name="folha_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="rascunho",
                        confirmada_em__isnull=True,
                        confirmada_por__isnull=True,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        estado="confirmada",
                        confirmada_em__isnull=False,
                        confirmada_por__isnull=False,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | (
                        Q(
                            estado="estornada",
                            confirmada_em__isnull=False,
                            confirmada_por__isnull=False,
                            estornada_em__isnull=False,
                            estornada_por__isnull=False,
                        )
                        & ~Q(motivo_estorno="")
                    )
                ),
                name="folha_campos_coerentes_com_o_estado",
            ),
            # No máximo um lançamento NÃO estornado por empresa e mês: rascunho ou
            # confirmada. Estornada fica no histórico e não bloqueia um novo lançamento.
            models.UniqueConstraint(
                fields=["empresa", "ano", "mes"],
                condition=~Q(estado="estornada"),
                name="folha_mes_unica_ativa_por_empresa",
            ),
        ]

    def __str__(self):
        return (
            f"Folha {self.ano}-{self.mes:02d} — empresa {self.empresa_id} "
            f"({self.get_estado_display()})"
        )

    @property
    def total(self):
        """Folha do mês: soma dos componentes (LC 123 art. 18 § 24, com CPP e FGTS)."""
        return sum((getattr(self, nome) for nome in self.COMPONENTES), Decimal("0.00"))

    def _estado_gravado(self):
        # Lê o estado GRAVADO: o objeto em memória pode estar desatualizado.
        return FolhaFatorR.objects.filter(pk=self.pk).values_list("estado", flat=True).first()

    def save(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() != EstadoFolhaFatorR.RASCUNHO:
            raise FolhaImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() != EstadoFolhaFatorR.RASCUNHO:
            raise FolhaImutavel(
                "Folha confirmada ou estornada não pode ser excluída; o histórico é preservado "
                "pelo estorno."
            )
        return super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# DL-076 (frente A): ISS por município, começando por Palmas (HI-82 a HI-86).
#
# Três tabelas de CONFIGURAÇÃO. Nenhuma guarda o resultado da apuração: o total do
# ISS é calculado sob demanda, a partir das notas escrituradas, como o pré-DAS.
#
# - RegraIssMunicipio: regra LEGAL do município (dias de vencimento, regra do dia não
#   útil, dispositivo). É GLOBAL, sem escritório: a norma é a mesma para todos os
#   escritórios, e uma regra por escritório abriria a divergência entre eles sobre
#   um dado que não é escolha de ninguém. Quem grava é a migração 0006 (Palmas) e o
#   serviço `cadastrar_regra_municipio`, sem rota de cliente.
# - AliquotaIssMunicipal: alíquota por município e subitem, INFORMADA pelo escritório
#   (HI-82). O produto não traz percentual de município algum: a tabela vigente de
#   Palmas não foi achada (consulta de 08/10/2026, item 1).
# - RegimeIssEmpresa: regime do ISS da empresa no exercício (HI-84) e município do
#   estabelecimento, que é o local de incidência da apuração própria.
#
# Alteração e encerramento de alíquota e de regime são feitos com trilha (antes e
# depois). Não há exclusão: a vigência se encerra.
# ---------------------------------------------------------------------------


class RegimeIss(models.TextChoices):
    """Regime do ISS da empresa no exercício (HI-84).

    Fixos (autônomo e sociedade de profissionais) não têm apuração por alíquota: o
    produto identifica e recusa a apuração, listando as notas para conferência.
    """

    ALIQUOTA = "aliquota", "Alíquota (apuração por nota)"
    FIXO_AUTONOMO = "fixo_autonomo", "Fixo de autônomo"
    FIXO_SOCIEDADE_PROFISSIONAIS = (
        "fixo_sociedade_profissionais",
        "Fixo de sociedade de profissionais",
    )


class RegraIssMunicipio(models.Model):
    """Regra do ISS de um município, com vigência e fonte (HI-83).

    Palmas (IBGE 1721000): dia 10 (próprio) e dia 15 (retido), dia não útil → primeiro
    dia útil seguinte, Decreto 1.667/2018, art. 86 § 3º e Anexo I (cópia de legisweb,
    consultada em 08/10/2026). O dia é limitado a 1..28: nenhum dia de vencimento
    de município depende de mês curto, e o produto não calcula feriado.
    """

    municipio_ibge = models.CharField("código IBGE do município", max_length=7)
    nome = models.CharField("município", max_length=120)
    dia_vencimento_proprio = models.PositiveSmallIntegerField(
        "dia do vencimento do ISS próprio (mês seguinte)"
    )
    dia_vencimento_retido = models.PositiveSmallIntegerField(
        "dia do vencimento do ISS retido (mês seguinte)"
    )
    regra_dia_nao_util = models.TextField("regra do dia não útil")
    fonte = models.TextField("dispositivo e fonte")
    inicio_vigencia = models.DateField("início da vigência")
    fim_vigencia = models.DateField("fim da vigência", null=True, blank=True)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "regra do ISS por município"
        verbose_name_plural = "regras do ISS por município"
        ordering = ["municipio_ibge", "inicio_vigencia", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(municipio_ibge__regex=r"^[0-9]{7}$"),
                name="regra_iss_codigo_ibge",
            ),
            models.CheckConstraint(
                condition=Q(dia_vencimento_proprio__gte=1, dia_vencimento_proprio__lte=28)
                & Q(dia_vencimento_retido__gte=1, dia_vencimento_retido__lte=28),
                name="regra_iss_dias_entre_1_e_28",
            ),
            models.CheckConstraint(
                condition=Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=F("inicio_vigencia")),
                name="regra_iss_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=~Q(fonte=""),
                name="regra_iss_fonte_preenchida",
            ),
            models.UniqueConstraint(
                fields=["municipio_ibge", "inicio_vigencia"],
                name="regra_iss_unica_por_inicio",
            ),
        ]

    def __str__(self):
        return f"Regra do ISS — {self.nome} ({self.municipio_ibge})"


class AliquotaIssMunicipal(models.Model):
    """Alíquota do ISS por município e subitem, informada pelo escritório (HI-82).

    Por escritório: é dado que o escritório conhece (a alíquota que o município aplica
    aos clientes dele), e o isolamento vale também para ela. O subitem é "II.SS" da
    lista da LC 116 (o código de tributação nacional de 6 dígitos, cTribNac, tem
    item(2)+subitem(2)+desdobro(2)). O percentual é em pontos (5 = 5%), com 4 casas.

    O limite de 2% a 5% (LC 116, art. 8º, II, e art. 8º-A) é conferido pelo serviço, na
    entrada, e também pelo banco (teto e piso, CHECK abaixo), para o caso de o ORM ser usado
    direto. A exceção do § 1º do art. 8º-A (subitens 7.02, 7.05 e 16.01 abaixo de 2%) entra
    com aviso no serviço; o banco a deixa passar pela mesma lista.
    """

    escritorio = models.ForeignKey(
        Escritorio,
        on_delete=models.PROTECT,
        related_name="aliquotas_iss_municipal",
        verbose_name="escritório",
    )
    municipio_ibge = models.CharField("código IBGE do município", max_length=7)
    subitem = models.CharField("subitem da LC 116 (II.SS)", max_length=5)
    percentual = models.DecimalField("alíquota (%)", max_digits=5, decimal_places=4)
    fonte = models.TextField("fonte (dispositivo, documento e data de consulta)")
    inicio_vigencia = models.DateField("início da vigência")
    fim_vigencia = models.DateField("fim da vigência", null=True, blank=True)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )
    alterada_em = models.DateTimeField("alterada em", auto_now=True)
    alterada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="alterada por",
    )

    class Meta:
        verbose_name = "alíquota do ISS por município"
        verbose_name_plural = "alíquotas do ISS por município"
        ordering = ["escritorio_id", "municipio_ibge", "subitem", "inicio_vigencia", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(municipio_ibge__regex=r"^[0-9]{7}$"),
                name="aliquota_iss_codigo_ibge",
            ),
            # Item 01 a 40 da lista da LC 116; subitem 01 a 99.
            models.CheckConstraint(
                condition=Q(subitem__regex=r"^(0[1-9]|[12][0-9]|3[0-9]|40)\.(0[1-9]|[1-9][0-9])$"),
                name="aliquota_iss_subitem_valido",
            ),
            models.CheckConstraint(
                condition=Q(percentual__gt=0) & Q(percentual__lte=5),
                name="aliquota_iss_percentual_ate_5",
            ),
            # Piso de 2% (art. 8º-A), salvo a exceção do § 1º para estes subitens (A9 da DL-076).
            models.CheckConstraint(
                condition=Q(percentual__gte=2) | Q(subitem__in=["07.02", "07.05", "16.01"]),
                name="aliquota_iss_piso_2_salvo_excecao",
            ),
            models.CheckConstraint(
                condition=~Q(fonte=""),
                name="aliquota_iss_fonte_preenchida",
            ),
            models.CheckConstraint(
                condition=Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=F("inicio_vigencia")),
                name="aliquota_iss_fim_depois_do_inicio",
            ),
        ]

    def __str__(self):
        return f"Alíquota ISS {self.subitem} — {self.percentual}% (município {self.municipio_ibge})"


class RegimeIssEmpresa(models.Model):
    """Regime do ISS da empresa em um exercício, e município do estabelecimento (HI-84).

    Uma linha por empresa e exercício. Sem linha, a apuração própria recusa: o produto
    não presume regime nem município. Empresa do Simples não tem apuração aqui (o ISS
    dela está no pré-DAS, DL-075), e o regime fica registrado mesmo assim.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="regimes_iss",
        verbose_name="empresa",
    )
    exercicio = models.PositiveSmallIntegerField("exercício (ano-calendário)")
    regime = models.CharField("regime do ISS", max_length=32, choices=RegimeIss.choices)
    municipio_ibge = models.CharField("código IBGE do município do estabelecimento", max_length=7)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criado por",
    )
    alterado_em = models.DateTimeField("alterado em", auto_now=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="alterado por",
    )

    class Meta:
        verbose_name = "regime do ISS da empresa"
        verbose_name_plural = "regimes do ISS das empresas"
        ordering = ["empresa_id", "exercicio", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "exercicio"],
                name="regime_iss_unico_por_empresa_exercicio",
            ),
            models.CheckConstraint(
                condition=Q(exercicio__gte=2000, exercicio__lte=2999),
                name="regime_iss_exercicio_valido",
            ),
            models.CheckConstraint(
                condition=Q(regime__in=RegimeIss.values),
                name="regime_iss_regime_valido",
            ),
            models.CheckConstraint(
                condition=Q(municipio_ibge__regex=r"^[0-9]{7}$"),
                name="regime_iss_codigo_ibge",
            ),
        ]

    def __str__(self):
        return (
            f"Regime do ISS {self.exercicio} — empresa {self.empresa_id} "
            f"({self.get_regime_display()})"
        )


# ---------------------------------------------------------------------------
# DL-079 (frente A): Lucro Presumido, IRPJ e CSLL trimestrais com o acréscimo da LC 224.
# Plano: docs/planos/DL-079-lucro-presumido-irpj-csll.md. Catálogo, alíquotas e fontes:
# apps/fiscal/presumido_tabelas.py (fonte única: as opções abaixo saem de lá). Cálculo:
# apps/fiscal/presumido_calculo.py.
# Sem ModelAdmin (BL-262). A escrita passa por `apps.fiscal.presumido`, que grava a trilha.
# Gatilhos de imutabilidade no banco: migração fiscal 0009 (mesmo desenho da DL-078).
# ---------------------------------------------------------------------------

OPCOES_ATIVIDADE_PRESUMIDA = [
    (atividade.codigo, atividade.rotulo) for atividade in _tabelas_presumido.CATALOGO_ATIVIDADES
]
CODIGOS_ATIVIDADE_PRESUMIDA = [codigo for codigo, _ in OPCOES_ATIVIDADE_PRESUMIDA]
SERVICOS_HOSPITALARES_PRESUMIDO = _tabelas_presumido.SERVICOS_HOSPITALARES


class AtividadePresuncaoEmpresa(models.Model):
    """Atividade de presunção da empresa, com vigência (DL-079, item 2; HI-101).

    `padrao=True` é a atividade que a NFS-e recebe na `dCompet` em que está vigente. Só pode
    haver UMA padrão em aberto por empresa (restrição do banco); padrões com vigência fechada
    não se sobrepõem, e isso o serviço recusa. Atividades não padrão ficam para a receita
    informada, que nomeia a atividade.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="atividades_presuncao",
        verbose_name="empresa",
    )
    atividade = models.CharField(
        "atividade de presunção", max_length=40, choices=OPCOES_ATIVIDADE_PRESUMIDA
    )
    inicio = models.DateField("início da vigência")
    fim = models.DateField("fim da vigência", null=True, blank=True)
    padrao = models.BooleanField("atividade padrão das NFS-e", default=False)
    # Serviço hospitalar só vale com os dois requisitos legais confirmados pelo contador
    # (Lei 9.249, art. 15, § 1º, III, "a"; HI-101). Não se infere a partir do código do serviço.
    requisitos_hospitalares_confirmados = models.BooleanField(
        "requisitos do serviço hospitalar confirmados pelo contador", default=False
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "atividade de presunção da empresa"
        verbose_name_plural = "atividades de presunção da empresa"
        ordering = ["empresa_id", "inicio", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__isnull=True) | Q(fim__gte=F("inicio")),
                name="presumido_atividade_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=Q(atividade__in=CODIGOS_ATIVIDADE_PRESUMIDA),
                name="presumido_atividade_valida",
            ),
            models.CheckConstraint(
                condition=~Q(atividade=SERVICOS_HOSPITALARES_PRESUMIDO)
                | Q(requisitos_hospitalares_confirmados=True),
                name="presumido_hospitalar_exige_requisitos",
            ),
            models.UniqueConstraint(
                fields=["empresa"],
                condition=Q(padrao=True, fim__isnull=True),
                name="presumido_padrao_unica_em_aberto",
            ),
        ]

    def __str__(self):
        return f"Atividade de presunção {self.pk} — {self.get_atividade_display()}"


OPCOES_CRITERIO_RECEITA = [
    ("competencia", "Competência"),
    ("caixa", "Caixa"),
]


class CriterioReceitaPresumido(models.Model):
    """Critério de reconhecimento da receita do ano (competência ou caixa), por empresa e ano.

    Uma linha por empresa e ano; definido uma vez (HI-66 e consulta, item 9). O caixa é recusado
    pela apuração (IN 1.700, art. 223), e não existe meio-termo.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="criterios_receita_presumido",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano-calendário")
    criterio = models.CharField("critério", max_length=12, choices=OPCOES_CRITERIO_RECEITA)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criado por",
    )

    class Meta:
        verbose_name = "critério de receita do presumido"
        verbose_name_plural = "critérios de receita do presumido"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "ano"],
                name="presumido_criterio_unico_por_ano",
            ),
            models.CheckConstraint(
                condition=Q(criterio__in=["competencia", "caixa"]),
                name="presumido_criterio_valido",
            ),
            models.CheckConstraint(
                condition=Q(ano__gte=1970, ano__lte=2999),
                name="presumido_criterio_ano_valido",
            ),
        ]

    def __str__(self):
        return f"Critério {self.ano} — empresa {self.empresa_id} ({self.get_criterio_display()})"


OPCOES_TIPO_RECEITA_PRESUMIDO = [
    ("presuncao", "Sujeita à presunção"),
    ("integral", "Integral (art. 25, II da Lei 9.430/1996)"),
]
OPCOES_ESTADO_RECEITA_PRESUMIDO = [
    ("ativa", "Ativa"),
    ("estornada", "Estornada"),
]


class ReceitaTrimestralPresumido(models.Model):
    """Receita informada do trimestre: presunção (com atividade) ou integral (sem atividade).

    Imutável depois de criada, exceto pelo estorno (ativa → estornada, com motivo). O banco
    recusa o resto por gatilho (migração fiscal 0009), como na DL-078. Estornar é o único
    caminho para corrigir: a linha original fica na trilha.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="receitas_trimestrais_presumido",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano-calendário")
    trimestre = models.PositiveSmallIntegerField("trimestre (1 a 4)")
    tipo = models.CharField("tipo da receita", max_length=10, choices=OPCOES_TIPO_RECEITA_PRESUMIDO)
    atividade = models.ForeignKey(
        AtividadePresuncaoEmpresa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="receitas_trimestrais",
        verbose_name="atividade de presunção",
    )
    descricao = models.CharField("descrição", max_length=300)
    valor = models.DecimalField("valor", max_digits=15, decimal_places=2)
    suporte = models.CharField("documento de suporte", max_length=300)
    estado = models.CharField(
        "estado", max_length=10, choices=OPCOES_ESTADO_RECEITA_PRESUMIDO, default="ativa"
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "receita trimestral do presumido"
        verbose_name_plural = "receitas trimestrais do presumido"
        ordering = ["empresa_id", "ano", "trimestre", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(trimestre__gte=1, trimestre__lte=4),
                name="presumido_receita_trimestre_valido",
            ),
            models.CheckConstraint(
                condition=Q(ano__gte=1970, ano__lte=2999),
                name="presumido_receita_ano_valido",
            ),
            models.CheckConstraint(
                condition=Q(tipo="presuncao", atividade__isnull=False)
                | Q(tipo="integral", atividade__isnull=True),
                name="presumido_receita_atividade_conforme_tipo",
            ),
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name="presumido_receita_valor_positivo",
            ),
            models.CheckConstraint(
                condition=~Q(suporte=""),
                name="presumido_receita_suporte_obrigatorio",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="ativa",
                        motivo_estorno="",
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                    )
                    | Q(
                        ~Q(motivo_estorno=""),
                        estado="estornada",
                        estornada_em__isnull=False,
                        estornada_por__isnull=False,
                    )
                ),
                name="presumido_receita_estado_coerente",
            ),
        ]

    def __str__(self):
        return f"Receita {self.pk} — {self.ano}/T{self.trimestre} ({self.get_tipo_display()})"


class DeclaracaoReceitasIntegrais(models.Model):
    """Declaração do contador: as receitas integrais do trimestre estão declaradas (HI-104).

    `total` é o SNAPSHOT das receitas integrais ativas no instante da declaração. A declaração
    só vale enquanto o total atual for igual a esse snapshot; se mudar, a apuração volta a
    "parcial". Declarar de novo cria um registro novo, e vale o mais recente. Nunca se altera.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="declaracoes_integrais_presumido",
        verbose_name="empresa",
    )
    ano = models.PositiveSmallIntegerField("ano-calendário")
    trimestre = models.PositiveSmallIntegerField("trimestre (1 a 4)")
    total = models.DecimalField("total das integrais declaradas", max_digits=15, decimal_places=2)
    observacao = models.CharField("observação", max_length=500, blank=True, default="")
    declarada_em = models.DateTimeField("declarada em", auto_now_add=True)
    declarada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="declarada por",
    )

    class Meta:
        verbose_name = "declaração de receitas integrais"
        verbose_name_plural = "declarações de receitas integrais"
        ordering = ["empresa_id", "ano", "trimestre", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(trimestre__gte=1, trimestre__lte=4),
                name="presumido_declaracao_trimestre_valido",
            ),
            models.CheckConstraint(
                condition=Q(total__gte=0),
                name="presumido_declaracao_total_nao_negativo",
            ),
        ]

    def __str__(self):
        return f"Declaração {self.pk} — {self.ano}/T{self.trimestre}"


OPCOES_ESTADO_CONFIRMACAO_RETENCAO = [
    ("ativa", "Ativa"),
    ("substituida", "Substituída"),
]


class ConfirmacaoRetencaoPresumido(models.Model):
    """Retenção confirmada pelo contador para uma escrituração (HI-102, HI-103).

    Só a confirmação ATIVA entra na apuração. Confirmar de novo substitui a anterior (que fica
    como `substituida`, na trilha). `irrf_confirmado` e `csll_confirmada` são nulos quando o
    contador não confirma aquele tributo. A empresa é a da escrituração (sem campo próprio).
    """

    escrituracao = models.ForeignKey(
        EscrituracaoFiscal,
        on_delete=models.PROTECT,
        related_name="confirmacoes_retencao_presumido",
        verbose_name="escrituração prestada",
    )
    irrf_confirmado = models.DecimalField(
        "IRRF confirmado", max_digits=15, decimal_places=2, null=True, blank=True
    )
    csll_confirmada = models.DecimalField(
        "CSLL confirmada", max_digits=15, decimal_places=2, null=True, blank=True
    )
    motivo = models.CharField(
        "motivo (obrigatório quando o valor difere do proposto)",
        max_length=500,
        blank=True,
        default="",
    )
    estado = models.CharField(
        "estado", max_length=12, choices=OPCOES_ESTADO_CONFIRMACAO_RETENCAO, default="ativa"
    )
    confirmada_em = models.DateTimeField("confirmada em", auto_now_add=True)
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="confirmada por",
    )

    class Meta:
        verbose_name = "confirmação de retenção do presumido"
        verbose_name_plural = "confirmações de retenção do presumido"
        ordering = ["escrituracao_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["escrituracao"],
                condition=Q(estado="ativa"),
                name="presumido_confirmacao_ativa_unica_por_escrituracao",
            ),
            models.CheckConstraint(
                condition=Q(irrf_confirmado__isnull=True) | Q(irrf_confirmado__gte=0),
                name="presumido_confirmacao_irrf_nao_negativo",
            ),
            models.CheckConstraint(
                condition=Q(csll_confirmada__isnull=True) | Q(csll_confirmada__gte=0),
                name="presumido_confirmacao_csll_nao_negativa",
            ),
            models.CheckConstraint(
                condition=Q(irrf_confirmado__isnull=False) | Q(csll_confirmada__isnull=False),
                name="presumido_confirmacao_ao_menos_um_valor",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["ativa", "substituida"]),
                name="presumido_confirmacao_estado_valido",
            ),
        ]

    def __str__(self):
        return f"Confirmação {self.pk} — escrituração {self.escrituracao_id} ({self.estado})"


OPCOES_TRIBUTO_MEDIDA = [
    ("irpj", "IRPJ"),
    ("csll", "CSLL"),
    ("ambos", "IRPJ e CSLL"),
]


class MedidaJudicialLC224(models.Model):
    """Medida judicial contra o acréscimo da LC 224, por empresa, tributo e período (HI-106).

    Com medida ativa cobrindo o tributo e o trimestre, "a recolher" usa a coluna SEM o
    acréscimo, e a parcela aparece como suspensa (ou "depositar", com depósito judicial). Sem
    medida, nunca se escolhe a coluna sem o acréscimo por padrão. A revogação é um ato com
    motivo; a medida não se apaga.
    """

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="medidas_judiciais_lc224",
        verbose_name="empresa",
    )
    tributo = models.CharField("tributo", max_length=10, choices=OPCOES_TRIBUTO_MEDIDA)
    ano_inicial = models.PositiveSmallIntegerField("ano inicial")
    trimestre_inicial = models.PositiveSmallIntegerField("trimestre inicial (1 a 4)")
    ano_final = models.PositiveSmallIntegerField("ano final", null=True, blank=True)
    trimestre_final = models.PositiveSmallIntegerField(
        "trimestre final (1 a 4)", null=True, blank=True
    )
    numero_processo = models.CharField("número do processo", max_length=60)
    orgao = models.CharField("órgão judicial", max_length=200)
    data_decisao = models.DateField("data da decisão")
    deposito_judicial = models.BooleanField("depósito judicial", default=False)
    suporte = models.CharField("documento de suporte", max_length=300)
    ativa = models.BooleanField("ativa", default=True)
    revogada_em = models.DateTimeField("revogada em", null=True, blank=True)
    motivo_revogacao = models.CharField(
        "motivo da revogação", max_length=500, blank=True, default=""
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "medida judicial contra a LC 224"
        verbose_name_plural = "medidas judiciais contra a LC 224"
        ordering = ["empresa_id", "ano_inicial", "trimestre_inicial", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(trimestre_inicial__gte=1, trimestre_inicial__lte=4),
                name="presumido_medida_trimestre_inicial_valido",
            ),
            models.CheckConstraint(
                condition=Q(trimestre_final__isnull=True)
                | Q(trimestre_final__gte=1, trimestre_final__lte=4),
                name="presumido_medida_trimestre_final_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(ano_final__isnull=True, trimestre_final__isnull=True)
                    | Q(ano_final__isnull=False, trimestre_final__isnull=False)
                ),
                name="presumido_medida_fim_completo_ou_indeterminado",
            ),
            models.CheckConstraint(
                condition=Q(ano_final__isnull=True)
                | Q(ano_final__gt=F("ano_inicial"))
                | Q(ano_final=F("ano_inicial"), trimestre_final__gte=F("trimestre_inicial")),
                name="presumido_medida_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=Q(tributo__in=["irpj", "csll", "ambos"]),
                name="presumido_medida_tributo_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(ativa=True, revogada_em__isnull=True, motivo_revogacao="")
                    | Q(
                        ~Q(motivo_revogacao=""),
                        ativa=False,
                        revogada_em__isnull=False,
                    )
                ),
                name="presumido_medida_ativa_coerente",
            ),
        ]

    def __str__(self):
        return f"Medida {self.pk} — {self.numero_processo} ({self.get_tributo_display()})"


# ---------------------------------------------------------------------------
# DL-081 (frente A): escrituração das NF-e de saída e da devolução de venda.
#
# Plano: docs/planos/DL-081-escrituracao-das-nfe-de-saida.md. Fonte normativa: consulta de
# 09/10/2026 (docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md), itens 2 a 5.
# Desenho da DL-072: rascunho, efetivada e estornada; gatilhos do banco; trilha na mesma transação.
#
# O catálogo de natureza é FECHADO e vive em código (HI-118): são as quatorze naturezas da
# consulta, mais "ajuste" (finNFe 2, 3, 5 e 6). A natureza é por ITEM, porque uma NF-e mistura
# CFOP e CST. O mercado (interno ou externo) é a ÚNICA definição em `mercado_da_natureza_nfe`;
# a composição da receita e o RBT12 consultam-na, sem repetir a regra.
# ---------------------------------------------------------------------------


class NaturezaOperacaoNFe(models.TextChoices):
    REVENDA = "revenda", "Venda de mercadoria adquirida de terceiros (revenda)"
    PRODUCAO_PROPRIA = "producao_propria", "Venda de produção própria"
    REVENDA_ST_SUBSTITUIDO = "revenda_st_substituido", "Revenda com ICMS-ST, substituído"
    SUBSTITUTO_ST = "substituto_st", "Venda como substituto tributário (ST retida na saída)"
    MONOFASICO = "monofasico", "Venda de produto monofásico de PIS/Cofins"
    COMBUSTIVEL = "combustivel", "Revenda de combustíveis para consumo (1,6% no IRPJ)"
    COMBUSTIVEL_REVENDA = "combustivel_revenda", "Revenda de combustíveis para revenda (8% no IRPJ)"
    EXPORTACAO_DIRETA = "exportacao_direta", "Exportação direta"
    COMERCIAL_EXPORTADORA = "comercial_exportadora", "Venda a comercial exportadora"
    DEVOLUCAO_VENDA = "devolucao_venda", "Devolução de venda recebida"
    # Devolução de combustível destinado a consumo: deduz do 1,6% (HI-140). A venda original estava
    # no 1,6%, então a devolução deduz da mesma atividade (Lei 9.249, art. 15, caput e § 2º, lida).
    DEVOLUCAO_COMBUSTIVEL_CONSUMO = (
        "devolucao_combustivel_consumo",
        "Devolução de venda de combustível para consumo (deduz do 1,6%)",
    )
    REMESSA_RETORNO = "remessa_retorno", "Remessa, retorno, demonstração, conserto ou mostruário"
    TRANSFERENCIA = "transferencia", "Transferência entre estabelecimentos"
    BONIFICACAO = "bonificacao", "Bonificação, doação, brinde ou amostra (incondicional)"
    CUPOM_NFCE = "cupom_nfce", "Operação já registrada em NFC-e ou cupom"
    SERVICO_CONJUGADA = "servico_conjugada", "Prestação de serviço em NF-e conjugada"
    AJUSTE = "ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"


@dataclass(frozen=True)
class NaturezaNFeInfo:
    """O que cada natureza significa para a receita.

    `papel`: "receita" (soma na receita bruta), "deducao" (subtrai no mês da devolução) ou
    "nao_receita" (soma zero). `mercado`: "interno" ou "externo". `segregacao` (Simples):
    "normal", "sujeita_st", "monofasico", "exportacao" ou None quando não compõe receita.
    `anexo_simples` é INFORMAÇÃO para o contador, não cálculo: o pré-DAS ainda não trata
    mercadoria (HI-122).

    `atividade_presumido` é o CÓDIGO da atividade de presunção (`presumido_tabelas`), e é a ÚNICA
    fonte desse mapeamento (DL-083, HI-134). `None` quando a natureza não entra no Presumido (não
    é receita nem dedução) ou não tem atividade a informar (serviço conjugado, recusado na
    apuração). Cada devolução deduz da atividade da venda que ela devolve (HI-140): a de venda
    comum, de comércio e indústria; a de combustível para consumo, de revenda de combustíveis.
    """

    papel: str
    mercado: str
    segregacao: str | None
    anexo_simples: str
    atividade_presumido: str | None


_NAO_RECEITA = "nao_receita"
_COMERCIO = _tabelas_presumido.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
_REVENDA_COMBUSTIVEIS = _tabelas_presumido.REVENDA_COMBUSTIVEIS

CATALOGO_NATUREZA_NFE: dict[str, NaturezaNFeInfo] = {
    NaturezaOperacaoNFe.REVENDA: NaturezaNFeInfo(
        "receita", "interno", "normal", "Anexo I (LC 123, art. 18, § 4º, I)", _COMERCIO
    ),
    NaturezaOperacaoNFe.PRODUCAO_PROPRIA: NaturezaNFeInfo(
        "receita", "interno", "normal", "Anexo II (LC 123, art. 18, § 4º, II)", _COMERCIO
    ),
    NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO: NaturezaNFeInfo(
        "receita",
        "interno",
        "sujeita_st",
        "Anexo I ou II, segregada 'sujeita a ST' (Res. CGSN 140, art. 25, § 8º, I)",
        _COMERCIO,
    ),
    NaturezaOperacaoNFe.SUBSTITUTO_ST: NaturezaNFeInfo(
        "receita",
        "interno",
        "normal",
        "Anexo I ou II; operação própria tributada, vST fora (Res. CGSN 140, art. 28, § 4º)",
        _COMERCIO,
    ),
    NaturezaOperacaoNFe.MONOFASICO: NaturezaNFeInfo(
        "receita",
        "interno",
        "monofasico",
        "Segregada: PIS e Cofins desconsiderados (Res. CGSN 140, art. 25, §§ 6º e 7º)",
        _COMERCIO,
    ),
    # Combustível em duas naturezas (HI-118, PE-85.1): a alíquota do IRPJ depende da operação
    # (Lei 9.249, art. 15, § 1º, I). Consumo: 1,6%. Revenda: 8%, comércio e indústria. A CSLL é 12%
    # nas duas. A sugestão pelo CFOP está em `escrituracao_nfe`, com os CFOP citados.
    NaturezaOperacaoNFe.COMBUSTIVEL: NaturezaNFeInfo(
        "receita",
        "interno",
        "normal",
        "ICMS monofásico/ST fora do DAS (LC 123, art. 13, § 1º, XIII, a)",
        _REVENDA_COMBUSTIVEIS,
    ),
    NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA: NaturezaNFeInfo(
        "receita",
        "interno",
        "normal",
        "ICMS monofásico/ST fora do DAS (LC 123, art. 13, § 1º, XIII, a)",
        _COMERCIO,
    ),
    NaturezaOperacaoNFe.EXPORTACAO_DIRETA: NaturezaNFeInfo(
        "receita",
        "externo",
        "exportacao",
        "Segregada: Cofins, PIS, IPI, ICMS e ISS desconsiderados (Res. CGSN 140, art. 25, § 3º)",
        _COMERCIO,
    ),
    NaturezaOperacaoNFe.COMERCIAL_EXPORTADORA: NaturezaNFeInfo(
        "receita",
        "externo",
        "exportacao",
        "Mesma segregação da exportação (LC 123, art. 18, § 4º-A, IV)",
        _COMERCIO,
    ),
    NaturezaOperacaoNFe.DEVOLUCAO_VENDA: NaturezaNFeInfo(
        "deducao",
        "interno",
        None,
        "Deduz no mês da devolução (Res. CGSN 140, art. 17)",
        _COMERCIO,
    ),
    # Devolução de combustível para consumo (HI-140): deduz da atividade de revenda de combustível,
    # 1,6%, a mesma da venda que ela devolve. O Simples não trata combustível (HI-132).
    NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO: NaturezaNFeInfo(
        "deducao",
        "interno",
        None,
        "Deduz no mês da devolução (Res. CGSN 140, art. 17)",
        _REVENDA_COMBUSTIVEIS,
    ),
    NaturezaOperacaoNFe.REMESSA_RETORNO: NaturezaNFeInfo(
        _NAO_RECEITA, "interno", None, "fora da base", None
    ),
    NaturezaOperacaoNFe.TRANSFERENCIA: NaturezaNFeInfo(
        _NAO_RECEITA, "interno", None, "fora da base", None
    ),
    NaturezaOperacaoNFe.BONIFICACAO: NaturezaNFeInfo(
        _NAO_RECEITA,
        "interno",
        None,
        "fora, se incondicional (Res. CGSN 140, art. 2º, § 5º, III)",
        None,
    ),
    NaturezaOperacaoNFe.CUPOM_NFCE: NaturezaNFeInfo(
        _NAO_RECEITA,
        "interno",
        None,
        "fora: a receita já entrou pela NFC-e (risco de duplicidade)",
        None,
    ),
    NaturezaOperacaoNFe.SERVICO_CONJUGADA: NaturezaNFeInfo(
        "receita",
        "interno",
        None,
        "serviço (Anexo III, IV ou V e ISS); fora do pré-DAS deste corte",
        None,
    ),
    NaturezaOperacaoNFe.AJUSTE: NaturezaNFeInfo(
        _NAO_RECEITA, "interno", None, "fora da receita (ajuste)", None
    ),
}


def mercado_da_natureza_nfe(natureza: str) -> str:
    """Mercado da natureza de NF-e.

    Recusa valor fora do catálogo: nunca vira "interno" em silêncio.
    """
    if natureza not in CATALOGO_NATUREZA_NFE:
        raise ValueError(f"natureza de NF-e fora do catálogo: {natureza!r}")
    return CATALOGO_NATUREZA_NFE[natureza].mercado


def mercado_do_item_nfe(natureza: str, cfop: str) -> str:
    """Mercado de UM item de NF-e: o da natureza, salvo a devolução de exportação.

    A devolução de venda (natureza `devolucao_venda`, ou `devolucao_combustivel_consumo`, HI-140)
    deduz do mercado da venda que ela devolve. A tabela oficial de CFOP marca como devolução de
    exportação os códigos 3.201, 3.202, 3.211, 3.212, 3.503 e 3.553 (todos com o primeiro dígito 3,
    que é entrada de fora do país). Essa devolução deduz o EXTERNO (correção da rodada 1, A8). A
    natureza sozinha não diz isso, por isso o CFOP entra.
    """
    devolucoes = (
        NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
    )
    if natureza in devolucoes and cfop.startswith("3"):
        return MercadoReceita.EXTERNO
    return mercado_da_natureza_nfe(natureza)


def papel_da_natureza_nfe(natureza: str) -> str:
    """Papel da natureza: receita, dedução ou não receita. Recusa valor fora do catálogo."""
    if natureza not in CATALOGO_NATUREZA_NFE:
        raise ValueError(f"natureza de NF-e fora do catálogo: {natureza!r}")
    return CATALOGO_NATUREZA_NFE[natureza].papel


# ---------------------------------------------------------------------------
# Anexo e segmento da mercadoria no Simples (DL-082, HI-125, HI-127, HI-128, HI-129).
#
# Fonte única da classificação de MERCADORIA. O anexo vem da natureza do item (revenda → Anexo I;
# produção própria → Anexo II), nunca da atividade padrão da empresa. O segmento diz quais tributos
# saem do DAS (Res. CGSN 140, art. 25, §§ 3º, 6º a 8º, em cópia): ICMS-ST substituído tira o ICMS;
# monofásico tira PIS e Cofins; exportação tira Cofins, PIS, IPI, ICMS e ISS. Combinações tiram a
# união dos conjuntos (o pré-DAS faz a união; aqui só se diz o segmento).
#
# Anexo da mercadoria (DL-082, decisão do arquiteto): o catálogo tem UMA natureza por item, e
# algumas naturezas não dizem se a venda é de PRODUÇÃO (Anexo II) ou de REVENDA (Anexo I). Por isso:
# - `revenda` → Anexo I e `producao_propria` → Anexo II, pela própria natureza (HI-125);
# - `revenda_st_substituido`, `substituto_st`, `monofasico`, `exportacao_direta` e
#   `comercial_exportadora` → o anexo vem da DESCRIÇÃO OFICIAL do CFOP do item (tabela de
#   `apps.fiscal.cfop`, Informe 2023.002 v2.10). Veja `anexo_pelo_cfop`.
# Se a descrição não decidir, o anexo fica `None` e o pré-DAS recusa o mês ("anexo da mercadoria a
# confirmar"): nunca se presume produção nem revenda.
# ---------------------------------------------------------------------------

ANEXO_I = "I"
ANEXO_II = "II"

SEGMENTO_NORMAL = "normal"
SEGMENTO_SUJEITA_ST = "sujeita_st"
SEGMENTO_MONOFASICO = "monofasico"
SEGMENTO_ST_MONOFASICO = "st_monofasico"
SEGMENTO_EXPORTACAO = "exportacao"


class SegmentoDevolucao(models.TextChoices):
    """Anexo e segmento de UMA devolução de venda, confirmados pelo contador (HI-129).

    Cada valor é um par (anexo, segmento) fixo. A devolução deduz SÓ dentro do mesmo par. Ver
    `ANEXO_E_SEGMENTO_DA_DEVOLUCAO`.
    """

    REVENDA = "revenda", "Devolução de revenda, Anexo I, sem ST nem monofásico"
    PRODUCAO = "producao", "Devolução de produção própria, Anexo II, sem ST nem monofásico"
    REVENDA_ST = "revenda_st", "Devolução de revenda com ST substituído, Anexo I"
    PRODUCAO_ST = "producao_st", "Devolução de produção com ST substituído, Anexo II"
    REVENDA_MONOFASICO = "revenda_monofasico", "Devolução de revenda monofásica, Anexo I"
    PRODUCAO_MONOFASICO = "producao_monofasico", "Devolução de produção monofásica, Anexo II"
    REVENDA_ST_MONOFASICO = (
        "revenda_st_monofasico",
        "Devolução de revenda com ST e monofásico, Anexo I",
    )
    PRODUCAO_ST_MONOFASICO = (
        "producao_st_monofasico",
        "Devolução de produção com ST e monofásico, Anexo II",
    )
    REVENDA_EXPORTACAO = "revenda_exportacao", "Devolução de revenda exportada, Anexo I"
    PRODUCAO_EXPORTACAO = "producao_exportacao", "Devolução de produção exportada, Anexo II"


# Tamanho do campo: cabe o maior valor de `SegmentoDevolucao` ("producao_st_monofasico", 22).
TAMANHO_SEGMENTO_DEVOLUCAO = 24

ANEXO_E_SEGMENTO_DA_DEVOLUCAO: dict[str, tuple[str, str]] = {
    SegmentoDevolucao.REVENDA: (ANEXO_I, SEGMENTO_NORMAL),
    SegmentoDevolucao.PRODUCAO: (ANEXO_II, SEGMENTO_NORMAL),
    SegmentoDevolucao.REVENDA_ST: (ANEXO_I, SEGMENTO_SUJEITA_ST),
    SegmentoDevolucao.PRODUCAO_ST: (ANEXO_II, SEGMENTO_SUJEITA_ST),
    SegmentoDevolucao.REVENDA_MONOFASICO: (ANEXO_I, SEGMENTO_MONOFASICO),
    SegmentoDevolucao.PRODUCAO_MONOFASICO: (ANEXO_II, SEGMENTO_MONOFASICO),
    SegmentoDevolucao.REVENDA_ST_MONOFASICO: (ANEXO_I, SEGMENTO_ST_MONOFASICO),
    SegmentoDevolucao.PRODUCAO_ST_MONOFASICO: (ANEXO_II, SEGMENTO_ST_MONOFASICO),
    SegmentoDevolucao.REVENDA_EXPORTACAO: (ANEXO_I, SEGMENTO_EXPORTACAO),
    SegmentoDevolucao.PRODUCAO_EXPORTACAO: (ANEXO_II, SEGMENTO_EXPORTACAO),
}

# Naturezas de mercadoria cujo anexo é FIXO pela natureza (HI-125, consulta de 09/10/2026, item 1).
_ANEXO_FIXO_DA_NATUREZA = {
    NaturezaOperacaoNFe.REVENDA: ANEXO_I,
    NaturezaOperacaoNFe.PRODUCAO_PROPRIA: ANEXO_II,
}

# Naturezas de mercadoria cujo anexo vem do CFOP do item (DL-082, decisão do arquiteto).
_ANEXO_PELO_CFOP_DA_NATUREZA = frozenset(
    {
        NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO,
        NaturezaOperacaoNFe.SUBSTITUTO_ST,
        NaturezaOperacaoNFe.MONOFASICO,
        NaturezaOperacaoNFe.EXPORTACAO_DIRETA,
        NaturezaOperacaoNFe.COMERCIAL_EXPORTADORA,
    }
)

# Descrições oficiais que decidem o anexo (Informe 2023.002 v2.10, em `apps/fiscal/dados`).
# Produção do estabelecimento: 5.101 "Venda de produção do estabelecimento."; 5.401 "... em operação
# com produto sujeito ao regime de substituição tributária"; 7.101 "Venda de produção do
# estabelecimento."; 5.501 "Remessa de produção do estabelecimento, com fim específico de
# exportação."
# Mercadoria de terceiros: 5.102 e 7.102 "Venda de mercadoria adquirida ou recebida de terceiros";
# 5.403 e 5.405 (ST) "Venda de mercadoria adquirida ou recebida de terceiros em operação com
# mercadoria sujeita ao regime de substituição tributária"; 5.502 "Remessa de mercadoria adquirida
# ou recebida de terceiros, com fim específico de exportação." Qualquer outra descrição não decide.
_PREFIXOS_PRODUCAO = (
    "Venda de produção do estabelecimento",
    "Remessa de produção do estabelecimento",
)
_PREFIXOS_REVENDA = (
    "Venda de mercadoria adquirida ou recebida de terceiros",
    "Remessa de mercadoria adquirida ou recebida de terceiros",
)

# Naturezas de mercadoria: as que têm anexo e aceitam a marca de monofásico (DL-082).
NATUREZAS_DE_MERCADORIA = frozenset(_ANEXO_FIXO_DA_NATUREZA) | _ANEXO_PELO_CFOP_DA_NATUREZA


def anexo_pelo_cfop(cfop: str) -> str | None:
    """Anexo que a descrição oficial do CFOP decide, ou `None` se ela não decide.

    Consulta a tabela oficial (`apps.fiscal.cfop`). CFOP fora da tabela não decide.
    """
    info = consultar_cfop_oficial(cfop)
    if info is None:
        return None
    if info.descricao.startswith(_PREFIXOS_PRODUCAO):
        return ANEXO_II
    if info.descricao.startswith(_PREFIXOS_REVENDA):
        return ANEXO_I
    return None


def anexo_da_mercadoria(natureza: str, cfop: str) -> str | None:
    """Anexo de um item de mercadoria. `None` = a natureza e o CFOP não decidem (recusa do pré-DAS).

    Para natureza que não é de mercadoria, devolve `None` também: quem chama confere
    `NATUREZAS_DE_MERCADORIA` antes.
    """
    if natureza in _ANEXO_FIXO_DA_NATUREZA:
        return _ANEXO_FIXO_DA_NATUREZA[natureza]
    if natureza in _ANEXO_PELO_CFOP_DA_NATUREZA:
        return anexo_pelo_cfop(cfop)
    return None


def segmento_da_mercadoria(*, st: bool, monofasico: bool, exportacao: bool) -> str:
    """Segmento pela união dos tributos que saem (Res. CGSN 140, art. 25, §§ 3º, 6º a 8º).

    Exportação já tira PIS, Cofins, IPI, ICMS e ISS: com ela, ST e monofásico não acrescentam nada
    e o segmento é `exportacao` (§ 3º, "tão somente").
    """
    if exportacao:
        return SEGMENTO_EXPORTACAO
    if st and monofasico:
        return SEGMENTO_ST_MONOFASICO
    if st:
        return SEGMENTO_SUJEITA_ST
    if monofasico:
        return SEGMENTO_MONOFASICO
    return SEGMENTO_NORMAL


def classificacao_da_venda(
    natureza: str, monofasico_marcado: bool, cfop: str
) -> tuple[str | None, str] | None:
    """(anexo, segmento) de um item de VENDA de mercadoria; `None` se a natureza não é de
    mercadoria.

    O anexo pode ser `None` (CFOP que não decide): o pré-DAS recusa, nomeando natureza e CFOP.
    `monofasico` vale pela natureza `monofasico` OU pela marca do contador no item (HI-128). Sem
    marca e sem natureza monofásica, o item é normal (lado conservador: paga a mais, nunca a menos).
    """
    if natureza not in NATUREZAS_DE_MERCADORIA:
        return None
    segmento = segmento_da_mercadoria(
        st=natureza == NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO,
        monofasico=monofasico_marcado or natureza == NaturezaOperacaoNFe.MONOFASICO,
        exportacao=natureza
        in (NaturezaOperacaoNFe.EXPORTACAO_DIRETA, NaturezaOperacaoNFe.COMERCIAL_EXPORTADORA),
    )
    return anexo_da_mercadoria(natureza, cfop), segmento


def classificacao_da_devolucao(segmento_confirmado: str) -> tuple[str, str] | None:
    """(anexo, segmento) de uma devolução com segmento CONFIRMADO. `None` se não há confirmação."""
    return ANEXO_E_SEGMENTO_DA_DEVOLUCAO.get(segmento_confirmado)


class TipoEscrituracaoNFe(models.TextChoices):
    """Tipo da nota para a escrituração, decidido na criação pela regra de elegibilidade."""

    SAIDA_PROPRIA = "saida_propria", "Saída própria (finNFe 1)"
    DEVOLUCAO = "devolucao", "Devolução de venda recebida (finNFe 4)"
    AJUSTE = "ajuste", "Ajuste (finNFe 2, 3, 5 ou 6)"


class EscrituracaoNFe(models.Model):
    """Escrituração de UMA NF-e ou NFC-e para UMA empresa (DL-081, frente A).

    Uma linha por vínculo (documento x empresa) e por tentativa: uma efetivada estornada não é
    reaberta; um novo ato cria OUTRA linha, e a trilha guarda as duas. Por isso a unicidade é
    PARCIAL: no máximo uma linha NÃO estornada (rascunho ou efetivada) por vínculo.

    Os totais (`valor_nf`, `receita_bruta`, `devolucao`, `soma_itens`) são copiados na efetivação,
    a partir dos itens lidos do XML guardado. A composição da receita lê as naturezas por item
    (`NaturezaItemNFe`) e a receita de cada item (`itens_nfe.receita_do_item`, DL-083), não estes
    totais.

    Imutabilidade, em três camadas (como na DL-072): `save()` recusa alterar linha efetivada ou
    estornada; os serviços mudam estado com `update()` condicionado; e o BANCO (gatilhos da
    migração 0011) aceita só rascunho->efetivada, efetivada->estornada, e só as colunas do ato.
    Os itens (`ItemNFe`) e a leitura (`LeituraItensNFe`) da NOTA ficam imutáveis no banco enquanto
    ela tiver escrituração efetivada ou estornada (gatilhos `trg_item_nfe_imutavel` e
    `trg_leitura_itens_nfe_imutavel`, correção da rodada 1, A3). As naturezas por item seguem
    imutáveis pelo gatilho próprio, como acima.

    Limite declarado: `TRUNCATE` não aciona gatilho de linha (mesmo limite da DL-052 e da DL-072).
    """

    vinculo = models.ForeignKey(
        VinculoNFeEmpresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_nfe",
        verbose_name="vínculo de NF-e com empresa",
    )
    # Redundante com `vinculo.empresa`, de propósito, como na DL-072: a consulta por empresa e o
    # isolamento não precisam atravessar o vínculo. A igualdade é garantida em `save()`.
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="escrituracoes_nfe",
        verbose_name="empresa",
    )
    tipo = models.CharField(
        "tipo da escrituração", max_length=16, choices=TipoEscrituracaoNFe.choices
    )
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoEscrituracao.choices,
        default=EstadoEscrituracao.RASCUNHO,
    )
    # Competência = primeiro dia do mês de `dhEmi` no fuso de São Paulo (consulta, item 1).
    competencia = models.DateField("competência (mês de dhEmi)", null=True, blank=True)
    # Dia escrito no dhEmi, no fuso de São Paulo. Só exibição e o aviso de competência.
    data_emissao = models.DateField("data de emissão", null=True, blank=True)
    valor_nf = models.DecimalField(
        "valor da nota (vNF)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # Soma da receita de TODOS os itens (`receita_do_item`, DL-083), de qualquer natureza. É a
    # conferência com o vNF: vNF − vST − vFCPST − vIPI − vII − vIPIDevol.
    soma_itens = models.DecimalField(
        "soma da receita dos itens", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # Receita bruta (naturezas de receita) e devolução (natureza de dedução), sempre positivas.
    receita_bruta = models.DecimalField(
        "receita bruta da escrituração", max_digits=15, decimal_places=2, null=True, blank=True
    )
    devolucao = models.DecimalField(
        "devolução de venda", max_digits=15, decimal_places=2, null=True, blank=True
    )
    efetivada_em = models.DateTimeField("efetivada em", null=True, blank=True)
    efetivada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="efetivada por",
    )
    estornada_em = models.DateTimeField("estornada em", null=True, blank=True)
    estornada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estornada por",
    )
    motivo_estorno = models.CharField("motivo do estorno", max_length=500, blank=True, default="")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="criada por",
    )

    class Meta:
        verbose_name = "escrituração de NF-e"
        verbose_name_plural = "escriturações de NF-e"
        ordering = ["id"]
        constraints = [
            # No máximo UMA escrituração não estornada por vínculo, no banco (corrida que a trava
            # de `select_for_update` não cobre).
            models.UniqueConstraint(
                fields=["vinculo"],
                condition=Q(estado__in=["rascunho", "efetivada"]),
                name="escrituracao_nfe_ativa_unica_por_vinculo",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["rascunho", "efetivada", "estornada"]),
                name="escrituracao_nfe_estado_valido",
            ),
            # Coerência entre estado e colunas do ato, como na DL-072.
            models.CheckConstraint(
                condition=(
                    Q(
                        estado="rascunho",
                        efetivada_em__isnull=True,
                        efetivada_por__isnull=True,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        estado="efetivada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        competencia__isnull=False,
                        data_emissao__isnull=False,
                        valor_nf__isnull=False,
                        soma_itens__isnull=False,
                        receita_bruta__isnull=False,
                        devolucao__isnull=False,
                        estornada_em__isnull=True,
                        estornada_por__isnull=True,
                        motivo_estorno="",
                    )
                    | Q(
                        ~Q(motivo_estorno=""),
                        estado="estornada",
                        efetivada_em__isnull=False,
                        efetivada_por__isnull=False,
                        competencia__isnull=False,
                        data_emissao__isnull=False,
                        valor_nf__isnull=False,
                        soma_itens__isnull=False,
                        receita_bruta__isnull=False,
                        devolucao__isnull=False,
                        estornada_em__isnull=False,
                        estornada_por__isnull=False,
                    )
                ),
                name="escrituracao_nfe_campos_coerentes_com_o_estado",
            ),
        ]

    def __str__(self):
        return (
            f"Escrituração NF-e {self.pk} — vínculo {self.vinculo_id} ({self.get_estado_display()})"
        )

    def _estado_gravado(self):
        return EscrituracaoNFe.objects.filter(pk=self.pk).values_list("estado", flat=True).first()

    def save(self, *args, **kwargs):
        # Só o vínculo da MESMA empresa. A regra de elegibilidade está no serviço; isto impede que
        # um `objects.create()` troque a empresa do vínculo.
        if self.empresa_id != self.vinculo.empresa_id:
            raise ValidationError("A escrituração deve ser da mesma empresa do vínculo.")
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk is not None and self._estado_gravado() in (
            EstadoEscrituracao.EFETIVADA,
            EstadoEscrituracao.ESTORNADA,
        ):
            raise EscrituracaoImutavel(
                "Escrituração efetivada ou estornada não pode ser excluída; "
                "o histórico é preservado pelo estorno."
            )
        return super().delete(*args, **kwargs)


class ItemNFe(models.Model):
    """Um `det` da NF-e, lido do XML guardado (DL-081, item 2).

    Cada campo é o do XSD do PL 010f, citado em `apps/fiscal/itens_nfe.py` com a linha. Campo
    ausente no XML é `None`, nunca zero. O produto LÊ esses campos e não os interpreta: a
    apuração do ICMS (etapa própria) vai ler daqui, sem reabrir o XML.

    Valores em `Decimal`, com a escala do padrão TDec do XSD (ver `itens_nfe`). Os totais de
    item são gravados com a escala do próprio campo (DE-010).

    `receita_bruta_item` é o VALOR BRUTO do item (vProd − vDesc + vFrete + vSeg + vOutro), gravado
    como derivado. NÃO é a receita: ela depende de `indTot` e de `vICMSDeson` e sai de
    `apps.fiscal.itens_nfe.receita_do_item` (DL-083). O nome do campo fica por compatibilidade, e a
    versão do leitor não sobe (decisão do arquiteto, DL-083).
    """

    documento = models.ForeignKey(
        DocumentoNFe, on_delete=models.CASCADE, related_name="itens", verbose_name="documento"
    )
    n_item = models.PositiveSmallIntegerField("número do item (nItem)")
    c_prod = models.CharField("código do produto (cProd)", max_length=60)
    x_prod = models.CharField("descrição do produto (xProd)", max_length=120)
    ncm = models.CharField("NCM", max_length=8)
    cest = models.CharField("CEST", max_length=7, blank=True, default="")
    cfop = models.CharField("CFOP", max_length=4)
    u_com = models.CharField("unidade comercial (uCom)", max_length=6)
    q_com = models.DecimalField("quantidade comercial (qCom)", max_digits=15, decimal_places=4)
    v_un_com = models.DecimalField(
        "valor unitário comercial (vUnCom)", max_digits=21, decimal_places=10
    )
    v_prod = models.DecimalField("valor do item (vProd)", max_digits=15, decimal_places=2)
    v_desc = models.DecimalField(
        "desconto do item (vDesc)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_frete = models.DecimalField(
        "frete do item (vFrete)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_seg = models.DecimalField(
        "seguro do item (vSeg)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_outro = models.DecimalField(
        "outras despesas (vOutro)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    ind_tot = models.CharField("compõe o total da NF-e (indTot)", max_length=1)
    c_benef = models.CharField(
        "código de benefício fiscal (cBenef)", max_length=10, blank=True, default=""
    )
    # ICMS (grupo do det/imposto/ICMS; cada campo existe só em alguns grupos).
    orig = models.CharField("origem da mercadoria (orig)", max_length=1, null=True, blank=True)
    cst = models.CharField("CST do ICMS", max_length=2, null=True, blank=True)
    csosn = models.CharField("CSOSN", max_length=3, null=True, blank=True)
    mod_bc = models.CharField(
        "modalidade da BC do ICMS (modBC)", max_length=1, null=True, blank=True
    )
    v_bc = models.DecimalField(
        "BC do ICMS (vBC)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    p_icms = models.DecimalField(
        "alíquota do ICMS (pICMS)", max_digits=7, decimal_places=4, null=True, blank=True
    )
    v_icms = models.DecimalField(
        "ICMS (vICMS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_icms_deson = models.DecimalField(
        "ICMS desonerado (vICMSDeson)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # indDeduzDeson (grupo ICMS do item, leiauteNFe_v4.00.xsd:2586): "1" = o vICMSDeson deduz do
    # total da NF-e. A receita do item deduz esse valor (DL-083, `itens_nfe.receita_do_item`).
    ind_deduz_deson = models.CharField(
        "indicador de dedução do ICMS desonerado (indDeduzDeson)",
        max_length=1,
        null=True,
        blank=True,
    )
    mot_des_icms = models.CharField(
        "motivo da desoneração (motDesICMS)", max_length=2, null=True, blank=True
    )
    mod_bc_st = models.CharField(
        "modalidade da BC do ST (modBCST)", max_length=1, null=True, blank=True
    )
    v_bc_st = models.DecimalField(
        "BC do ICMS-ST (vBCST)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    p_icms_st = models.DecimalField(
        "alíquota do ICMS-ST (pICMSST)", max_digits=7, decimal_places=4, null=True, blank=True
    )
    v_icms_st = models.DecimalField(
        "ICMS-ST (vICMSST)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_bc_st_ret = models.DecimalField(
        "BC do ST retido (vBCSTRet)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_icms_st_ret = models.DecimalField(
        "ICMS-ST retido (vICMSSTRet)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    p_cred_sn = models.DecimalField(
        "alíquota do crédito do Simples (pCredSN)",
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
    )
    v_cred_icms_sn = models.DecimalField(
        "crédito do Simples (vCredICMSSN)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_fcp = models.DecimalField(
        "fundo de combate à pobreza (vFCP)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_fcp_st = models.DecimalField(
        "FCP do ST (vFCPST)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_icms_ufdest = models.DecimalField(
        "partilha do ICMS, UF de destino (vICMSUFDest)",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cst_ipi = models.CharField("CST do IPI", max_length=2, null=True, blank=True)
    v_ipi = models.DecimalField(
        "IPI do item (vIPI)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    cst_pis = models.CharField("CST do PIS", max_length=2, null=True, blank=True)
    v_pis = models.DecimalField(
        "PIS do item (vPIS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    cst_cofins = models.CharField("CST da Cofins", max_length=2, null=True, blank=True)
    v_cofins = models.DecimalField(
        "Cofins do item (vCOFINS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_issqn = models.DecimalField(
        "ISSQN do item (vISSQN)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_ii = models.DecimalField(
        "imposto de importação do item (vII)",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    # IBS/CBS: só a presença e o XML bruto do grupo. Nada é interpretado (HI-123).
    tem_ibscbs = models.BooleanField("traz grupo IBS/CBS", default=False)
    ibscbs_xml = models.TextField("grupo IBS/CBS, XML bruto", blank=True, default="")
    receita_bruta_item = models.DecimalField(
        "receita bruta do item (derivada)", max_digits=15, decimal_places=2
    )

    class Meta:
        verbose_name = "item de NF-e"
        verbose_name_plural = "itens de NF-e"
        ordering = ["documento_id", "n_item"]
        constraints = [
            models.UniqueConstraint(fields=["documento", "n_item"], name="item_nfe_unico_por_nota"),
            models.CheckConstraint(condition=Q(n_item__gte=1), name="item_nfe_n_item_positivo"),
        ]

    def __str__(self):
        return f"Item {self.n_item} da NF-e {self.documento_id}"


class LeituraItensNFe(models.Model):
    """Resultado da leitura dos itens de uma NF-e, gravado UMA vez (DL-081, item 2).

    `lida`: os itens estão em `ItemNFe`. `ilegivel`: algum valor está fora do padrão do XSD;
    `motivo` nomeia o campo, nenhum item é gravado, e a escrituração fica bloqueada. Gravar o
    resultado (inclusive o de ilegível) torna a leitura idempotente: o mesmo XML dá a mesma
    resposta, sem reler a cada consulta. Os totais que a conferência e os avisos usam ficam aqui,
    porque o `DocumentoNFe` da DL-080 não os guarda (DE-074).

    Imutabilidade (correção da rodada 1, A3): gatilhos da migração 0011 recusam INSERT, UPDATE e
    DELETE nesta tabela quando a nota tem escrituração efetivada ou estornada. Sem escrituração
    assim, a leitura pode ser refeita (troca de versão do leitor).
    """

    ESTADO_LIDA = "lida"
    ESTADO_ILEGIVEL = "ilegivel"

    documento = models.OneToOneField(
        DocumentoNFe,
        on_delete=models.CASCADE,
        related_name="leitura_itens",
        verbose_name="documento",
    )
    estado = models.CharField(
        "estado da leitura",
        max_length=10,
        choices=[("lida", "Lida"), ("ilegivel", "Itens ilegíveis")],
    )
    motivo = models.CharField("motivo (quando ilegível)", max_length=500, blank=True, default="")
    quantidade_itens = models.PositiveIntegerField("quantidade de itens lidos", default=0)
    # Versão do leitor que gerou esta leitura (`itens_nfe.VERSAO_LEITOR_ITENS`). Leitura de versão
    # anterior é refeita na próxima tentativa, se a nota não tem escrituração efetivada ou
    # estornada.
    # O padrão 1 é a versão da rodada 1: o valor sem marcação nunca passa por leitura atual.
    versao_leitor = models.PositiveSmallIntegerField("versão do leitor", default=1)
    # ICMSTot/vII e ICMSTot/vIPIDevol (XSD:5450, 5460), para a conferência da receita.
    v_ii = models.DecimalField(
        "total do II (vII)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_ipi_devol = models.DecimalField(
        "IPI devolvido (vIPIDevol)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # total/vNFTot (XSD:5627), total/IBSCBSTot/gIBS/vIBS, total/IBSCBSTot/gCBS/vCBS
    # e total/ISTot/vIS.
    v_nf_tot = models.DecimalField(
        "valor total com IBS, CBS e IS (vNFTot)",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    v_ibs = models.DecimalField(
        "total do IBS (vIBS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_cbs = models.DecimalField(
        "total da CBS (vCBS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    v_is = models.DecimalField(
        "total do IS (vIS)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    # ICMSTot/vFCPST (leiauteNFe_v4.00.xsd, grupo ICMSTot). É o total DECLARADO, lido do XML, e não
    # a
    # soma dos itens: a conferência com o vNF (regra W16 do MOC 7.0) usa o que a nota declara.
    v_fcp_st_total = models.DecimalField(
        "total do FCP-ST (vFCPST)", max_digits=15, decimal_places=2, null=True, blank=True
    )
    lida_em = models.DateTimeField("lida em", auto_now_add=True)

    class Meta:
        verbose_name = "leitura de itens de NF-e"
        verbose_name_plural = "leituras de itens de NF-e"
        constraints = [
            models.CheckConstraint(
                condition=(Q(estado="lida", motivo="") | Q(~Q(motivo=""), estado="ilegivel")),
                name="leitura_itens_nfe_motivo_coerente",
            ),
        ]

    def __str__(self):
        return f"Leitura de itens da NF-e {self.documento_id} ({self.get_estado_display()})"


class NaturezaItemNFe(models.Model):
    """Natureza confirmada de UM item de uma escrituração (DL-081, item 3).

    `natureza` vazia é "ainda não confirmada": a sugestão nunca grava aqui sozinha. A efetivação
    exige todos os itens com natureza, e o banco recusa a efetivação com vazio (gatilho).
    Depois de efetivada a escrituração, nenhuma linha destas muda (gatilho).
    """

    escrituracao = models.ForeignKey(
        EscrituracaoNFe, on_delete=models.CASCADE, related_name="naturezas_dos_itens"
    )
    item = models.ForeignKey(ItemNFe, on_delete=models.CASCADE, related_name="naturezas")
    natureza = models.CharField(
        "natureza confirmada",
        # 29 caracteres: "devolucao_combustivel_consumo" (DL-083, HI-140).
        max_length=29,
        choices=NaturezaOperacaoNFe.choices,
        blank=True,
        default="",
    )
    # Marca de monofásico de PIS e Cofins dada pelo contador (DL-082, HI-128). Separada da natureza
    # de ICMS, para permitir "ST e monofásico" no mesmo item. Sem marca, o item é normal. Só vale
    # para natureza de mercadoria, e só enquanto a escrituração é rascunho (gatilho da DL-081).
    monofasico = models.BooleanField(
        "monofásico de PIS e Cofins (marca do contador)", default=False
    )
    # Segmento CONFIRMADO de uma devolução de venda (DL-082, HI-129). Vazio = sem confirmação: o
    # pré-DAS do mês recusa. Só vale para `devolucao_venda`, e só em rascunho.
    segmento_devolucao = models.CharField(
        "segmento da devolução (confirmado)",
        max_length=TAMANHO_SEGMENTO_DEVOLUCAO,
        choices=SegmentoDevolucao.choices,
        blank=True,
        default="",
    )
    atualizada_em = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "natureza de item de NF-e"
        verbose_name_plural = "naturezas de itens de NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["escrituracao", "item"], name="natureza_item_nfe_unica_por_item"
            ),
        ]

    def __str__(self):
        return f"Natureza do item {self.item_id} na escrituração {self.escrituracao_id}"


class EstadoLoteEscrituracaoNFe(models.TextChoices):
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDO = "concluido", "Concluído"


class EstadoNotaDoLoteNFe(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EFETIVADA = "efetivada", "Efetivada pelo lote"
    JA_EFETIVADA = "ja_efetivada", "Já efetivada (pulada)"
    FALHOU = "falhou", "Falhou"


class LoteEscrituracaoNFe(models.Model):
    """Lote de escrituração de NF-e e NFC-e de UM mês de UMA empresa (DL-085, frente A).

    Guarda o CONJUNTO de notas que o contador confirmou, com a assinatura da prévia. Sem o lote,
    a parte seguinte não sabe quais notas eram as confirmadas: depois da primeira parte, elas saem
    da prévia (já estão efetivadas), e a assinatura da prévia muda. Por isso o conjunto é gravado
    na confirmação, em `LoteEscrituracaoNFeNota`, e as partes seguintes o referem pelo id.

    Um lote em andamento por empresa e mês, no máximo: o banco recusa o segundo (a trava de
    `select_for_update` no serviço é a primeira defesa, esta é a segunda).

    `escolhas` são as trocas de natureza feitas na confirmação, por grupo: já validadas contra a
    prévia e contra o tipo de nota. A trilha de cada efetivação é a da escrituração individual.
    """

    escritorio = models.ForeignKey(
        Escritorio, on_delete=models.PROTECT, related_name="lotes_escrituracao_nfe"
    )
    # Redundante com `empresa.escritorio`, como na escrituração: a consulta por escritório não
    # precisa atravessar a empresa. A igualdade é garantida em `save()`.
    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="lotes_escrituracao_nfe"
    )
    competencia = models.DateField("competência (primeiro dia do mês)")
    assinatura = models.CharField("assinatura da prévia", max_length=64)
    escolhas = models.JSONField("escolhas de natureza por grupo", default=dict, blank=True)
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoLoteEscrituracaoNFe.choices,
        default=EstadoLoteEscrituracaoNFe.EM_ANDAMENTO,
    )
    quantidade_notas = models.PositiveIntegerField("notas confirmadas", default=0)
    quantidade_itens = models.PositiveIntegerField("itens confirmados", default=0)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="confirmado por",
    )
    concluido_em = models.DateTimeField("concluído em", null=True, blank=True)

    class Meta:
        verbose_name = "lote de escrituração de NF-e"
        verbose_name_plural = "lotes de escrituração de NF-e"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "competencia"],
                condition=Q(estado="em_andamento"),
                name="lote_nfe_em_andamento_unico_por_mes",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["em_andamento", "concluido"]),
                name="lote_nfe_estado_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(estado="em_andamento", concluido_em__isnull=True)
                    | Q(estado="concluido", concluido_em__isnull=False)
                ),
                name="lote_nfe_concluido_tem_data",
            ),
        ]

    def save(self, *args, **kwargs):
        # Isolamento: um lote de um escritório nunca aponta para empresa de outro (AGENTS.md §11).
        if self.escritorio_id != self.empresa.escritorio_id:
            raise ValidationError("O lote deve ser do escritório da empresa.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Lote de NF-e {self.pk} — empresa {self.empresa_id} ({self.get_estado_display()})"


class LoteEscrituracaoNFeNota(models.Model):
    """Uma nota do conjunto confirmado de um lote, com as naturezas FIXADAS na confirmação.

    `itens` é a lista de `[item_id, natureza_sugerida, natureza_escolhida]`, na ordem do nItem. A
    parte que efetiva compara a sugestão de hoje com a gravada: se a nota mudou desde a
    confirmação (itens lidos de novo, sugestão diferente), a nota falha com motivo, e não é
    efetivada com a natureza de uma leitura que o contador não viu.

    `escrituracao` é preenchida quando a nota é efetivada pelo lote (ou quando já estava efetivada,
    caso em que a nota é "pulada" e não se cria escrituração nova).
    """

    lote = models.ForeignKey(
        LoteEscrituracaoNFe, on_delete=models.PROTECT, related_name="notas", verbose_name="lote"
    )
    vinculo = models.ForeignKey(
        VinculoNFeEmpresa,
        on_delete=models.PROTECT,
        related_name="notas_de_lote_nfe",
        verbose_name="vínculo de NF-e com empresa",
    )
    chave_grupo = models.CharField("grupo da prévia", max_length=40)
    itens = models.JSONField("itens com natureza fixada", default=list)
    estado = models.CharField(
        "estado",
        max_length=12,
        choices=EstadoNotaDoLoteNFe.choices,
        default=EstadoNotaDoLoteNFe.PENDENTE,
    )
    motivo = models.CharField("motivo (quando falhou)", max_length=500, blank=True, default="")
    escrituracao = models.ForeignKey(
        EscrituracaoNFe,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="escrituração",
    )
    processada_em = models.DateTimeField("processada em", null=True, blank=True)

    class Meta:
        verbose_name = "nota de lote de escrituração de NF-e"
        verbose_name_plural = "notas de lote de escrituração de NF-e"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lote", "vinculo"], name="lote_nfe_nota_unica_por_lote"
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["pendente", "efetivada", "ja_efetivada", "falhou"]),
                name="lote_nfe_nota_estado_valido",
            ),
        ]

    def __str__(self):
        return f"Nota {self.vinculo_id} do lote {self.lote_id} ({self.get_estado_display()})"
