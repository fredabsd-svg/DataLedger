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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.empresas.models import Empresa
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
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "resultado de arquivo"
        verbose_name_plural = "resultados de arquivo"
        ordering = ["id"]

    def __str__(self):
        return f"{self.caminho_no_zip or '(arquivo solto)'} — {self.get_resultado_display()}"


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
    (por exemplo, uma escrituração efetivada no mês confirmado, que não passa
    pelo estorno). Mudou → o mês é "a retificar" e não entra no RBT12.
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
