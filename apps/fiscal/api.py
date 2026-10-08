"""API REST da escrituração das NFS-e prestadas — DL-072, frente A.

Rotas em `apps/fiscal/urls_api.py`, montadas em `config/urls.py` sob
`fiscal/api/`. Toda a regra de negócio fica em `apps/fiscal/escrituracao.py`;
aqui só há autorização, isolamento, validação da entrada e tradução de erro.

Autorização (AGENTS.md §11, verificada NO SERVIDOR):
- consultar (lista e conferência): `papel_pode_consultar_documentos`, que
  exclui CLIENTE;
- efetivar e estornar: `papel_pode_escriturar_fiscal` (mesmos papéis que
  escrituram na contabilidade).
Ambos recebem o papel de `request.papel`, resolvido pelo middleware a partir
do vínculo com o escritório ATIVO — nunca de um campo enviado pelo cliente.

Isolamento: a empresa vem de `EmpresaEscopadaMixin`, que filtra pelo escritório
ativo e responde 404 para empresa de outro escritório. O vínculo e a
escrituração são buscados DENTRO dessa empresa, então um id de outra empresa
do mesmo escritório também responde 404.
"""

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.fiscal import escrituracao as servico
from apps.fiscal import folha_fator_r as folha_servico
from apps.fiscal import iss_municipal as iss_servico
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as receita_servico
from apps.fiscal import retencoes as retencoes_servico
from apps.fiscal import tomadas as tomadas_servico
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    AtividadeEmpresa,
    EnquadramentoAtividade,
    EscrituracaoFiscal,
    EscrituracaoTomada,
    FolhaFatorR,
    MercadoReceita,
    NaturezaOperacao,
    NaturezaTomada,
    OrigemReceitaInformada,
    ReceitaInformada,
    RegimeIss,
    RegimeIssEmpresa,
    RegraIssMunicipio,
    SituacaoIssReceitaInformada,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.permissoes import (
    papel_pode_consultar_documentos,
    papel_pode_escriturar_fiscal,
)
from apps.tenancy.permissions import TemEscritorioAtivo

# Política de dados não contratados (apps.core.requisicao, BL-196): toda
# superfície de ESCRITA declara o que aceita, e campo fora disso vira 400 com o
# nome da chave. Aceitar e ignorar um valor enviado (ex.: `valor_servico` no
# corpo de efetivar) faria o cliente acreditar que escolheu o valor, quando o
# valor é o do documento. `Idempotency-Key` é nomeado porque esta API não o usa
# para idempotência: falha alto em vez de parecer protegida.
CONTRATO_POST_EFETIVAR = ContratoDeRequisicao(
    campos={"natureza"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na efetivação da escrituração",
)
CONTRATO_POST_ESTORNAR = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração",
)

# Limite de ano igual ao de `Competencia` da contabilidade; fora dele a
# consulta recusa com 400 em vez de devolver lista vazia silenciosa.
_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999


class PodeConsultarFiscal(BasePermission):
    message = "Papel sem permissão para consultar documentos fiscais."

    def has_permission(self, request, view):
        return papel_pode_consultar_documentos(getattr(request, "papel", None))


class PodeEscriturarFiscal(BasePermission):
    message = "Papel sem permissão para escriturar ou estornar documentos fiscais."

    def has_permission(self, request, view):
        return papel_pode_escriturar_fiscal(getattr(request, "papel", None))


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class EscrituracaoSerializer(serializers.ModelSerializer):
    """Saída. Sem ids de usuário: quem fez cada ato está na trilha de auditoria,
    com o contexto completo, e não precisa vazar pela resposta."""

    natureza_descricao = serializers.CharField(source="get_natureza_display", read_only=True)

    class Meta:
        model = EscrituracaoFiscal
        fields = [
            "id",
            "vinculo",
            "empresa",
            "natureza",
            "natureza_descricao",
            "estado",
            "data_emissao",
            "data_competencia",
            "valor_servico",
            "valor_liquido",
            "iss_retido",
            "efetivada_em",
            "estornada_em",
            "motivo_estorno",
            "criado_em",
        ]
        read_only_fields = fields


class NotaPrestadaSerializer(serializers.Serializer):
    """Saída de uma linha da lista "a escriturar" (somente leitura)."""

    vinculo_id = serializers.IntegerField(source="vinculo.pk", read_only=True)
    identificador = serializers.CharField(source="documento.identificador", read_only=True)
    numero = serializers.CharField(source="documento.numero", read_only=True)
    dh_emissao = serializers.DateTimeField(source="documento.dh_emissao", read_only=True)
    data_emissao = serializers.DateField(read_only=True)
    data_competencia = serializers.DateField(source="documento.d_competencia", read_only=True)
    valor_servico = serializers.DecimalField(
        source="documento.v_serv", max_digits=17, decimal_places=2, read_only=True
    )
    valor_liquido = serializers.DecimalField(
        source="documento.v_liq", max_digits=17, decimal_places=2, read_only=True
    )
    tp_ret_issqn = serializers.CharField(source="documento.tp_ret_issqn", read_only=True)
    situacao = serializers.CharField(read_only=True)
    # Nulo quando o XML indica não incidência: não há sugestão, e o contador escolhe.
    natureza_sugerida = serializers.CharField(read_only=True, allow_null=True)
    competencia_difere_da_emissao = serializers.BooleanField(read_only=True)
    escrituracao_id = serializers.SerializerMethodField()
    estado_escrituracao = serializers.SerializerMethodField()

    def get_escrituracao_id(self, obj):
        return obj.escrituracao.pk if obj.escrituracao is not None else None

    def get_estado_escrituracao(self, obj):
        return obj.escrituracao.estado if obj.escrituracao is not None else None


class EfetivarEntradaSerializer(serializers.Serializer):
    # Mesmas mensagens da tela (auditoria A5). `allow_blank` deixa "" chegar até
    # `validate_natureza`: sem isso o DRF responderia "valor inválido" para o vazio.
    natureza = serializers.ChoiceField(
        choices=NaturezaOperacao.choices,
        allow_blank=True,
        error_messages={
            "required": servico.MENSAGEM_NATUREZA_VAZIA,
            "invalid_choice": servico.MENSAGEM_NATUREZA_FORA_DO_CATALOGO,
        },
    )

    def validate_natureza(self, valor):
        if not valor:
            raise serializers.ValidationError(servico.MENSAGEM_NATUREZA_VAZIA)
        return valor


class EstornarEntradaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=servico.MOTIVO_MAXIMO, trim_whitespace=True)


# ---------------------------------------------------------------------------
# Helpers de entrada e de erro
# ---------------------------------------------------------------------------


def _ano_e_mes_da_consulta(request):
    """Lê `ano` e `mes` da querystring. Ausente ou fora da faixa → 400."""
    try:
        ano = int(request.query_params["ano"])
        mes = int(request.query_params["mes"])
    except (KeyError, ValueError) as exc:
        raise DRFValidationError("Informe 'ano' e 'mes' como números inteiros.") from exc
    if not (1 <= mes <= 12):
        raise DRFValidationError(f"'mes' inválido: {mes} — deve estar entre 1 e 12.")
    if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO} e {_ANO_MAXIMO}."
        )
    return ano, mes


def _recusar_dado_nao_contratado(request, contrato):
    # Ponte de UMA linha entre o módulo de política (que não responde HTTP) e
    # o DRF: a recusa sai como 400 em JSON, igual às demais APIs do projeto.
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _resposta_de_conflito(exc):
    # 409 = o estado atual não permite a operação; nada foi gravado.
    return Response({"detail": exc.mensagem}, status=status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class NotasPrestadasView(EmpresaEscopadaMixin, APIView):
    """GET — notas em que a empresa é prestadora, com competência `ano/mes`."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        notas = servico.notas_a_escriturar(empresa, ano, mes)
        return Response(
            {
                "ano": ano,
                "mes": mes,
                "notas": NotaPrestadaSerializer(notas, many=True).data,
            }
        )


class EfetivarNotaPrestadaView(EmpresaEscopadaMixin, APIView):
    """POST — efetiva a nota (vínculo de prestador) com a natureza confirmada.

    201 quando cria ou transforma um rascunho; 200 quando a mesma natureza já
    estava efetivada (idempotente: nada gravado, nada novo na trilha).
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, vinculo_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_EFETIVAR)
        empresa = self.get_empresa()
        vinculo = get_object_or_404(
            VinculoDocumentoEmpresa,
            pk=vinculo_id,
            empresa=empresa,
            documento__escritorio=request.escritorio,
        )
        entrada = EfetivarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            escrituracao = servico.efetivar_escrituracao(
                vinculo,
                entrada.validated_data["natureza"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)

        codigo = status.HTTP_201_CREATED if escrituracao.criada_agora else status.HTTP_200_OK
        return Response(EscrituracaoSerializer(escrituracao).data, status=codigo)


class EstornarEscrituracaoView(EmpresaEscopadaMixin, APIView):
    """POST — estorna escrituração efetivada, com motivo obrigatório."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNAR)
        empresa = self.get_empresa()
        escrituracao = get_object_or_404(EscrituracaoFiscal, pk=escrituracao_id, empresa=empresa)
        entrada = EstornarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estornada = servico.estornar_escrituracao(
                escrituracao,
                entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)
        return Response(EscrituracaoSerializer(estornada).data, status=status.HTTP_200_OK)


class ConferenciaView(EmpresaEscopadaMixin, APIView):
    """GET — recebidas × escrituradas × pendentes, com bloqueios e avisos."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        resultado = servico.conferencia(empresa, ano, mes)
        return Response(
            {
                "ano": resultado.ano,
                "mes": resultado.mes,
                "recebidas": resultado.recebidas,
                "escrituradas": resultado.escrituradas,
                "pendentes": resultado.pendentes,
                "bloqueios": NotaPrestadaSerializer(resultado.bloqueios, many=True).data,
                "avisos": NotaPrestadaSerializer(resultado.avisos, many=True).data,
            }
        )


# ---------------------------------------------------------------------------
# DL-074 (frente A): receita mensal por mercado, confirmação do mês, receita
# informada e RBT12. Mesmas regras da DL-072 nesta API: autorização no servidor
# (consultar = `papel_pode_consultar_documentos`; confirmar, reabrir, lançar,
# confirmar e estornar receita = `papel_pode_escriturar_fiscal`), isolamento pela
# `EmpresaEscopadaMixin` (404 para empresa de outro escritório) e 400 para campo
# fora do contrato. A regra de negócio fica em `apps.fiscal.receita` e
# `apps.fiscal.rbt12`; aqui há só autorização, validação de entrada e tradução de erro.
# ---------------------------------------------------------------------------

CONTRATO_POST_RECEITA_INFORMADA = ContratoDeRequisicao(
    campos={
        "ano",
        "mes",
        "mercado",
        "valor",
        "origem",
        "motivo",
        "documento_suporte",
        "atividade",
        "situacao_iss",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento da receita informada",
)
CONTRATO_POST_CONFIRMAR_MES = ContratoDeRequisicao(
    campos={"ano", "mes"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na confirmação do mês",
)
CONTRATO_POST_REABRIR_MES = ContratoDeRequisicao(
    campos={"ano", "mes", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura do mês",
)
CONTRATO_POST_ESTORNAR_RECEITA = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da receita informada",
)
# Rota de ação sem corpo: qualquer campo enviado é recusado (frozenset vazio).
CONTRATO_POST_SEM_CORPO = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na confirmação da receita informada",
)
CONTRATO_POST_REGIME_CAIXA = ContratoDeRequisicao(
    campos={"ano"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na opção pelo regime de caixa",
)


class ReceitaInformadaSerializer(serializers.ModelSerializer):
    """Saída. Sem ids de usuário: quem fez cada ato está na trilha."""

    class Meta:
        model = ReceitaInformada
        fields = [
            "id",
            "ano",
            "mes",
            "mercado",
            "valor",
            "origem",
            "motivo",
            "documento_suporte",
            "atividade",
            "situacao_iss",
            "estado",
            "confirmada_em",
            "estornada_em",
            "motivo_estorno",
            "criado_em",
        ]
        read_only_fields = fields


class ValorMonetarioEntrada(serializers.DecimalField):
    """Valor monetário de entrada (A11 da auditoria DL-075).

    Aceita texto ou inteiro. Recusa número JSON com ponto flutuante: ele chega como binário,
    e 0.1 não é 0,1. Recusa também notação científica ("1E+3"), que o DRF aceitaria como
    1000,00. A regra de casas e de sinal continua no `DecimalField` e no serviço.
    """

    def to_internal_value(self, data):
        if isinstance(data, float):
            raise serializers.ValidationError(
                "Valor em ponto flutuante não é aceito: envie o valor como texto, "
                'por exemplo "1234.56".'
            )
        if isinstance(data, str) and "e" in data.lower():
            raise serializers.ValidationError(
                'Notação científica não é aceita: envie o valor por extenso, por exemplo "1000.00".'
            )
        # R5 (reconferência DL-075): o DRF converte com Decimal(), que aceita "1_000" e dígitos
        # Unicode. O formato é checado no texto, com o mesmo strip() que o DRF faz antes.
        if isinstance(data, str) and not receita_servico.FORMATO_VALOR.fullmatch(data.strip()):
            raise serializers.ValidationError(
                'Valor inválido: use só dígitos e ponto decimal, por exemplo "1234.56".'
            )
        return super().to_internal_value(data)


class ReceitaInformadaEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(
        min_value=receita_servico.ANO_MINIMO, max_value=receita_servico.ANO_MAXIMO
    )
    mes = serializers.IntegerField(min_value=1, max_value=12)
    mercado = serializers.ChoiceField(choices=MercadoReceita.choices)
    valor = ValorMonetarioEntrada(max_digits=17, decimal_places=2, min_value=Decimal("0.01"))
    origem = serializers.ChoiceField(choices=OrigemReceitaInformada.choices)
    motivo = serializers.CharField(max_length=receita_servico.MOTIVO_MAXIMO, trim_whitespace=True)
    documento_suporte = serializers.CharField(
        max_length=receita_servico.DOCUMENTO_SUPORTE_MAXIMO, trim_whitespace=True
    )
    # DL-075: atividade opcional (sem ela, vale a padrão do mês). Id de atividade da
    # MESMA empresa; outra empresa responde 404 na view, nunca vaza o registro.
    atividade = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # DL-075 (HI-80): situação do ISS. Obrigatória no mercado interno e vazia na exportação;
    # a regra é do serviço (`lancar_receita_informada`), com recusa nomeada. Sem valor padrão.
    situacao_iss = serializers.ChoiceField(
        choices=SituacaoIssReceitaInformada.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )


class MesEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(
        min_value=receita_servico.ANO_MINIMO, max_value=receita_servico.ANO_MAXIMO
    )
    mes = serializers.IntegerField(min_value=1, max_value=12)


class ReabrirMesEntradaSerializer(MesEntradaSerializer):
    motivo = serializers.CharField(max_length=receita_servico.MOTIVO_MAXIMO, trim_whitespace=True)


class MotivoEntradaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=receita_servico.MOTIVO_MAXIMO, trim_whitespace=True)


class RegimeCaixaEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField()


def _iso_ou_none(valor):
    return valor.isoformat() if valor is not None else None


def _mes_payload(empresa, ano: int, mes: int) -> dict:
    """Receita do mês: composição por mercado, situação e receitas informadas do mês."""
    dados = receita_servico.receita_do_mes(empresa, ano, mes)
    confirmacao = dados.confirmacao
    por_mercado = {}
    for mercado in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO):
        composicao = dados.composicao.de(mercado)
        por_mercado[mercado] = {
            "documento": str(composicao.documento),
            "informado": str(composicao.informado),
            "total": str(composicao.total),
        }
    return {
        "ano": ano,
        "mes": mes,
        "situacao": dados.situacao,
        "confirmada_em": _iso_ou_none(confirmacao.confirmada_em) if confirmacao else None,
        "a_retificar": bool(confirmacao and confirmacao.a_retificar),
        "motivo_reabertura": confirmacao.motivo_reabertura if confirmacao else "",
        "por_mercado": por_mercado,
        "receitas_informadas": ReceitaInformadaSerializer(
            dados.receitas_informadas, many=True
        ).data,
    }


def _rbt12_payload(resultado: apuracao.Rbt12) -> dict:
    def mes(m):
        return {"ano": m[0], "mes": m[1], "situacao": m[2]}

    por_mercado = {}
    for mercado, apurado in resultado.por_mercado.items():
        por_mercado[mercado] = {
            "apurado": str(apurado.apurado) if apurado.apurado is not None else None,
            "soma_janela": str(apurado.soma),
            "divisor": apurado.divisor,
            "acumulado_no_ano": (
                str(apurado.acumulado_no_ano) if apurado.acumulado_no_ano is not None else None
            ),
            "teto_limite": str(apurado.teto_limite) if apurado.teto_limite is not None else None,
            "teto_sublimite": (
                str(apurado.teto_sublimite) if apurado.teto_sublimite is not None else None
            ),
        }
    return {
        "ano": resultado.ano,
        "mes": resultado.mes,
        "data_abertura": resultado.data_abertura.isoformat(),
        "ano_opcao": resultado.ano_opcao,
        "regra": resultado.regra,
        "apuravel": resultado.apuravel,
        "modo_limite": resultado.modo_limite,
        "janela": [
            {
                "ano": m.ano,
                "mes": m.mes,
                "na_atividade": m.na_atividade,
                "situacao": m.situacao,
                "interno": str(m.interno),
                "externo": str(m.externo),
            }
            for m in resultado.janela
        ],
        "meses_pendentes": [mes(m) for m in resultado.pendentes_da_janela],
        "meses_pendentes_do_ano": [mes(m) for m in resultado.pendentes_do_ano],
        "por_mercado": por_mercado,
        "avisos": [
            {
                "codigo": aviso.codigo,
                "mercado": aviso.mercado,
                "mensagem": aviso.mensagem,
                "dispositivo": aviso.dispositivo,
            }
            for aviso in resultado.avisos
        ],
    }


class ReceitaDoMesView(EmpresaEscopadaMixin, APIView):
    """GET — receita do mês por mercado (documento × informado), situação e receitas informadas."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        return Response(_mes_payload(empresa, ano, mes))


class ConfirmarMesView(EmpresaEscopadaMixin, APIView):
    """POST — "receita de MM/AAAA completa", para os dois mercados. 409 se já confirmado."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_CONFIRMAR_MES)
        empresa = self.get_empresa()
        entrada = MesEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ano, mes = entrada.validated_data["ano"], entrada.validated_data["mes"]
        try:
            receita_servico.confirmar_mes(empresa, ano, mes, usuario=request.user, request=request)
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(_mes_payload(empresa, ano, mes), status=status.HTTP_200_OK)


class ReabrirMesView(EmpresaEscopadaMixin, APIView):
    """POST — reabre o mês confirmado. O motivo é obrigatório e fica na trilha."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_REABRIR_MES)
        empresa = self.get_empresa()
        entrada = ReabrirMesEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ano, mes = entrada.validated_data["ano"], entrada.validated_data["mes"]
        try:
            receita_servico.reabrir_mes(
                empresa,
                ano,
                mes,
                entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(_mes_payload(empresa, ano, mes), status=status.HTTP_200_OK)


class ReceitasInformadasView(EmpresaEscopadaMixin, APIView):
    """POST — lança receita informada em RASCUNHO (não entra na receita até confirmar)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_RECEITA_INFORMADA)
        empresa = self.get_empresa()
        entrada = ReceitaInformadaEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        atividade = None
        if dados.get("atividade") is not None:
            atividade = get_object_or_404(AtividadeEmpresa, pk=dados["atividade"], empresa=empresa)
        try:
            receita = receita_servico.lancar_receita_informada(
                empresa,
                dados["ano"],
                dados["mes"],
                dados["mercado"],
                dados["valor"],
                dados["origem"],
                dados["motivo"],
                dados["documento_suporte"],
                usuario=request.user,
                request=request,
                atividade=atividade,
                situacao_iss=dados.get("situacao_iss"),
            )
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(ReceitaInformadaSerializer(receita).data, status=status.HTTP_201_CREATED)


class ConfirmarReceitaInformadaView(EmpresaEscopadaMixin, APIView):
    """POST — rascunho → confirmada. Recusado se o mês já está confirmado."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, receita_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_SEM_CORPO)
        empresa = self.get_empresa()
        receita = get_object_or_404(ReceitaInformada, pk=receita_id, empresa=empresa)
        try:
            confirmada = receita_servico.confirmar_receita_informada(
                receita, usuario=request.user, request=request
            )
        except receita_servico.EntradaInvalidaReceita as exc:
            # A8 (auditoria DL-075): receita interna sem situação do ISS é dado inválido para
            # confirmar, e não conflito de estado: 400, com a mensagem nomeada.
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(ReceitaInformadaSerializer(confirmada).data, status=status.HTTP_200_OK)


class EstornarReceitaInformadaView(EmpresaEscopadaMixin, APIView):
    """POST — confirmada → estornada, com motivo. Mês confirmado fica "a retificar"."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, receita_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNAR_RECEITA)
        empresa = self.get_empresa()
        receita = get_object_or_404(ReceitaInformada, pk=receita_id, empresa=empresa)
        entrada = MotivoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estornada = receita_servico.estornar_receita_informada(
                receita, entrada.validated_data["motivo"], usuario=request.user, request=request
            )
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(ReceitaInformadaSerializer(estornada).data, status=status.HTTP_200_OK)


class Rbt12View(EmpresaEscopadaMixin, APIView):
    """GET — RBT12 do PA por mercado, com a regra usada, a janela, os meses pendentes e os avisos.

    Recusa nomeada (409) quando não há como apurar; "não apurável" (200, `apuravel=false`)
    quando falta mês confirmado na janela.
    """

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        try:
            resultado = apuracao.rbt12(empresa, ano, mes)
        except apuracao.ApuracaoRecusada as exc:
            return _resposta_de_conflito(exc)
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        return Response(_rbt12_payload(resultado))


class RegimeCaixaView(EmpresaEscopadaMixin, APIView):
    """POST — registra a opção pelo regime de caixa no Simples, por ano (só até 2026)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_REGIME_CAIXA)
        empresa = self.get_empresa()
        entrada = RegimeCaixaEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ano = entrada.validated_data["ano"]
        try:
            opcao = receita_servico.registrar_opcao_regime_caixa(
                empresa, ano, usuario=request.user, request=request
            )
        except receita_servico.EntradaInvalidaReceita as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except receita_servico.ReceitaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(
            {"empresa_id": empresa.pk, "ano_calendario": opcao.ano_calendario},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# DL-075 (frente A): pré-DAS, atividades e folha para o fator r.
#
# Autorização como nas demais rotas: ler (pré-DAS, listas) exige
# `papel_pode_consultar_documentos`; cadastrar, alterar, lançar, confirmar e estornar
# exigem `papel_pode_escriturar_fiscal`. Isolamento: `EmpresaEscopadaMixin` + busca
# DENTRO da empresa (404 para registro de outra empresa, mesmo do mesmo escritório).
# Recusa do pré-DAS é 409 com a LISTA de bloqueios (critério 7). Sem persistência do
# pré-DAS: é cálculo sob demanda (a memória vai na resposta).
# ---------------------------------------------------------------------------

_CAMPOS_ATIVIDADE = {"descricao", "codigo_subitem", "enquadramento", "inicio", "fim", "padrao"}
CONTRATO_ATIVIDADE = ContratoDeRequisicao(
    campos=_CAMPOS_ATIVIDADE,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro da atividade",
)
CONTRATO_FOLHA = ContratoDeRequisicao(
    campos={"ano", "mes", "documento_suporte", *FolhaFatorR.COMPONENTES},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento da folha",
)
CONTRATO_POST_ESTORNAR_FOLHA = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da folha",
)


def _ano_e_mes_da_consulta_so_ano(request):
    """Ano da querystring (filtro da lista de folhas). Inválido → 400, nunca lista vazia muda."""
    try:
        ano = int(request.query_params["ano"])
    except (KeyError, ValueError) as exc:
        raise DRFValidationError("Informe 'ano' como número inteiro.") from exc
    if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO} e {_ANO_MAXIMO}."
        )
    return ano, None


class AtividadeSerializer(serializers.ModelSerializer):
    enquadramento_descricao = serializers.CharField(
        source="get_enquadramento_display", read_only=True
    )

    class Meta:
        model = AtividadeEmpresa
        fields = [
            "id",
            "descricao",
            "codigo_subitem",
            "enquadramento",
            "enquadramento_descricao",
            "inicio",
            "fim",
            "padrao",
        ]
        read_only_fields = fields


class AtividadeEntradaSerializer(serializers.Serializer):
    descricao = serializers.CharField(max_length=200, trim_whitespace=True)
    codigo_subitem = serializers.CharField(
        max_length=20, required=False, allow_blank=True, trim_whitespace=True
    )
    enquadramento = serializers.ChoiceField(choices=EnquadramentoAtividade.choices)
    inicio = serializers.DateField()
    fim = serializers.DateField(required=False, allow_null=True)
    padrao = serializers.BooleanField(required=False, default=False)


class FolhaSerializer(serializers.ModelSerializer):
    """Saída. O total vem calculado; sem ids de usuário (a trilha guarda o ator)."""

    total = serializers.SerializerMethodField()

    class Meta:
        model = FolhaFatorR
        fields = [
            "id",
            "ano",
            "mes",
            "estado",
            *FolhaFatorR.COMPONENTES,
            "total",
            "documento_suporte",
            "confirmada_em",
            "estornada_em",
            "motivo_estorno",
            "criado_em",
        ]
        read_only_fields = fields

    def get_total(self, obj):
        return str(obj.total)


class FolhaEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(
        min_value=receita_servico.ANO_MINIMO, max_value=receita_servico.ANO_MAXIMO
    )
    mes = serializers.IntegerField(min_value=1, max_value=12)
    remuneracao_empregados_avulsos = ValorMonetarioEntrada(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    pro_labore_autonomos = ValorMonetarioEntrada(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    decimo_terceiro = ValorMonetarioEntrada(max_digits=17, decimal_places=2, min_value=Decimal("0"))
    cpp_recolhida = ValorMonetarioEntrada(max_digits=17, decimal_places=2, min_value=Decimal("0"))
    fgts_recolhido = ValorMonetarioEntrada(max_digits=17, decimal_places=2, min_value=Decimal("0"))
    documento_suporte = serializers.CharField(
        max_length=folha_servico.DOCUMENTO_SUPORTE_MAXIMO, trim_whitespace=True
    )


def _bloqueio_payload(bloqueio) -> dict:
    return {
        "codigo": bloqueio.codigo,
        "mensagem": bloqueio.mensagem,
        "dispositivo": bloqueio.dispositivo,
    }


def _pre_das_payload(resultado: pre_das_servico.PreDas) -> dict:
    """Pré-DAS em texto. Os números são strings exatas (sem float); a alíquota efetiva
    sai com a precisão total do cálculo, e a memória traz cada passo com o dispositivo."""

    def dec(valor):
        return str(valor) if valor is not None else None

    fator = resultado.fator_r
    return {
        "ano": resultado.ano,
        "mes": resultado.mes,
        "total": str(resultado.total),
        "total_por_tributo": {nome: str(valor) for nome, valor in resultado.total_por_tributo},
        "rbt12": {mercado: dec(valor) for mercado, valor in resultado.rbt12.items()},
        "fator_r": (
            {
                "fs12": dec(fator.fs12),
                "rbt12_conjunto": dec(fator.rbt12_conjunto),
                "valor": dec(fator.valor),
                "regra_de_zero": fator.regra_zero,
            }
            if fator is not None
            else None
        ),
        "anexos": [
            {
                "mercado": anexo.mercado,
                "anexo": anexo.anexo,
                "rbt12": dec(anexo.rbt12),
                "faixa": anexo.faixa,
                "limite_superior": dec(anexo.limite_superior),
                "aliquota_nominal": dec(anexo.aliquota_nominal),
                "parcela_a_deduzir": dec(anexo.parcela_a_deduzir),
                "aliquota_efetiva": dec(anexo.aliquota_efetiva),
                "teto_iss_aplicado": anexo.teto_iss_aplicado,
                "diferenca_centesimal": dec(anexo.diferenca),
                "tributo_da_diferenca": anexo.tributo_da_diferenca,
                "total": str(anexo.total),
                "segmentos": [
                    {
                        "segmento": seg.segmento,
                        "receita": str(seg.receita),
                        "total": str(seg.total),
                        "tributos": [
                            {
                                "tributo": linha.tributo,
                                "percentual": dec(linha.percentual),
                                "valor": str(linha.valor),
                                "desconsiderado": linha.desconsiderado,
                            }
                            for linha in seg.linhas
                        ],
                    }
                    for seg in anexo.segmentos
                ],
            }
            for anexo in resultado.anexos
        ],
        "memoria": [
            {
                "ordem": passo.ordem,
                "descricao": passo.descricao,
                "valor": passo.valor,
                "dispositivo": passo.dispositivo,
            }
            for passo in resultado.memoria
        ],
    }


class PreDasView(EmpresaEscopadaMixin, APIView):
    """GET — pré-DAS do mês (ano/mes). 409 com a lista de bloqueios quando não calcula.

    Formato dos números (R2c da reconferência DL-075):
    - Campos estruturados (`total`, `total_por_tributo`, `rbt12`, `fator_r`, aliquotas e
      percentuais) são strings em ponto decimal, exatas, sem float.
    - `memoria[].valor` é TEXTO PARA LEITURA, não campo de cálculo. Dinheiro sai em pt-BR
      ("8.080,00", "300.000,00"); percentuais e alíquotas continuam com ponto decimal e a
      precisão de cálculo ("0.080800000000"). Quem precisar de número usa os campos
      estruturados, nunca `memoria[].valor`.
    """

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        try:
            resultado = pre_das_servico.pre_das(empresa, ano, mes)
        except pre_das_servico.PreDasRecusado as exc:
            return Response(
                {
                    "detail": str(exc),
                    "bloqueios": [_bloqueio_payload(b) for b in exc.bloqueios],
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_pre_das_payload(resultado))


class AtividadesView(EmpresaEscopadaMixin, APIView):
    """GET — atividades da empresa, com vigência e enquadramento."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        atividades = AtividadeEmpresa.objects.filter(empresa=empresa).order_by("inicio", "id")
        return Response(AtividadeSerializer(atividades, many=True).data)


class CadastrarAtividadeView(EmpresaEscopadaMixin, APIView):
    """POST — cadastra atividade com enquadramento e vigência."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ATIVIDADE)
        empresa = self.get_empresa()
        entrada = AtividadeEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            atividade = pre_das_servico.cadastrar_atividade(
                empresa, dict(entrada.validated_data), usuario=request.user, request=request
            )
        except pre_das_servico.EntradaInvalidaAtividade as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except pre_das_servico.AtividadeConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(AtividadeSerializer(atividade).data, status=status.HTTP_201_CREATED)


class AtividadeDetalheView(EmpresaEscopadaMixin, APIView):
    """PATCH — altera atividade (vigência, padrão, enquadramento). DELETE — exclui se não usada."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def patch(self, request, empresa_id, atividade_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ATIVIDADE)
        empresa = self.get_empresa()
        atividade = get_object_or_404(AtividadeEmpresa, pk=atividade_id, empresa=empresa)
        entrada = AtividadeEntradaSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        try:
            alterada = pre_das_servico.alterar_atividade(
                atividade, dict(entrada.validated_data), usuario=request.user, request=request
            )
        except pre_das_servico.EntradaInvalidaAtividade as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except pre_das_servico.AtividadeConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(AtividadeSerializer(alterada).data, status=status.HTTP_200_OK)

    def delete(self, request, empresa_id, atividade_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_SEM_CORPO)
        empresa = self.get_empresa()
        atividade = get_object_or_404(AtividadeEmpresa, pk=atividade_id, empresa=empresa)
        try:
            pre_das_servico.excluir_atividade(atividade, usuario=request.user, request=request)
        except pre_das_servico.AtividadeConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FolhasFatorRView(EmpresaEscopadaMixin, APIView):
    """GET — folhas da empresa (opcional `ano`). Leitura: papel que consulta documentos."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        folhas = FolhaFatorR.objects.filter(empresa=empresa).order_by("ano", "mes", "id")
        if "ano" in request.query_params:
            ano, _mes = _ano_e_mes_da_consulta_so_ano(request)
            folhas = folhas.filter(ano=ano)
        return Response(FolhaSerializer(folhas, many=True).data)


class LancarFolhaView(EmpresaEscopadaMixin, APIView):
    """POST — lança a folha do mês em RASCUNHO. É escrita: exige papel que escritura."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_FOLHA)
        empresa = self.get_empresa()
        entrada = FolhaEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        componentes = {nome: dados[nome] for nome in FolhaFatorR.COMPONENTES}
        try:
            folha = folha_servico.lancar_folha(
                empresa,
                dados["ano"],
                dados["mes"],
                componentes,
                dados["documento_suporte"],
                usuario=request.user,
                request=request,
            )
        except folha_servico.EntradaInvalidaFolha as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except folha_servico.FolhaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(FolhaSerializer(folha).data, status=status.HTTP_201_CREATED)


class ConfirmarFolhaView(EmpresaEscopadaMixin, APIView):
    """POST — rascunho → confirmada. A folha confirmada entra no FS12 e não muda mais."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, folha_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_SEM_CORPO)
        empresa = self.get_empresa()
        folha = get_object_or_404(FolhaFatorR, pk=folha_id, empresa=empresa)
        try:
            confirmada = folha_servico.confirmar_folha(folha, usuario=request.user, request=request)
        except folha_servico.FolhaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(FolhaSerializer(confirmada).data, status=status.HTTP_200_OK)


class EstornarFolhaView(EmpresaEscopadaMixin, APIView):
    """POST — confirmada → estornada, com motivo. Lança-se outro lançamento para o mês."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, folha_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNAR_FOLHA)
        empresa = self.get_empresa()
        folha = get_object_or_404(FolhaFatorR, pk=folha_id, empresa=empresa)
        entrada = MotivoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estornada = folha_servico.estornar_folha(
                folha, entrada.validated_data["motivo"], usuario=request.user, request=request
            )
        except folha_servico.EntradaInvalidaFolha as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except folha_servico.FolhaErro as exc:
            return _resposta_de_conflito(exc)
        return Response(FolhaSerializer(estornada).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# DL-076 (frente A): ISS por município — alíquota por escritório (HI-82), regime por
# empresa e exercício (HI-84), regra do município (HI-83, só leitura) e as três
# apurações e relatórios (HI-82, HI-85, HI-86). Regra de negócio fica em
# apps.fiscal.iss_municipal; aqui: autorização, isolamento, entrada e tradução de erro.
#
# Autorização: ler é `PodeConsultarFiscal` (exclui CLIENTE); escrever é
# `PodeEscriturarFiscal`. Alíquota é do ESCRITÓRIO ATIVO (`request.escritorio`), e
# qualquer id de outro escritório responde 404. Regime e apurações são por empresa, com
# `EmpresaEscopadaMixin`.
# ---------------------------------------------------------------------------

CONTRATO_ALIQUOTA_ISS = ContratoDeRequisicao(
    campos={
        "municipio_ibge",
        "subitem",
        "percentual",
        "fonte",
        "inicio_vigencia",
        "fim_vigencia",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro da alíquota do ISS",
)
CONTRATO_REGIME_ISS = ContratoDeRequisicao(
    campos={"exercicio", "regime", "municipio_ibge"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no regime do ISS da empresa",
)


class AliquotaIssSerializer(serializers.ModelSerializer):
    """Saída. `percentual` sai como texto com 4 casas (sem float)."""

    class Meta:
        model = AliquotaIssMunicipal
        fields = [
            "id",
            "municipio_ibge",
            "subitem",
            "percentual",
            "fonte",
            "inicio_vigencia",
            "fim_vigencia",
        ]
        read_only_fields = fields


class AliquotaIssEntradaSerializer(serializers.Serializer):
    municipio_ibge = serializers.CharField(max_length=7, trim_whitespace=True)
    subitem = serializers.CharField(max_length=5, trim_whitespace=True)
    # Até 4 casas, na mesma escala da coluna. A regra de 2% a 5% é do serviço, que recusa
    # com a mensagem da LC 116, não do serializer.
    percentual = serializers.DecimalField(max_digits=7, decimal_places=4)
    fonte = serializers.CharField(max_length=1000, trim_whitespace=True)
    inicio_vigencia = serializers.DateField()
    fim_vigencia = serializers.DateField(required=False, allow_null=True)


class RegimeIssSerializer(serializers.ModelSerializer):
    regime_descricao = serializers.CharField(source="get_regime_display", read_only=True)

    class Meta:
        model = RegimeIssEmpresa
        fields = ["id", "exercicio", "regime", "regime_descricao", "municipio_ibge"]
        read_only_fields = fields


class RegimeIssEntradaSerializer(serializers.Serializer):
    exercicio = serializers.IntegerField()
    regime = serializers.ChoiceField(choices=RegimeIss.choices)
    municipio_ibge = serializers.CharField(max_length=7, trim_whitespace=True)


class RegraIssSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegraIssMunicipio
        fields = [
            "id",
            "municipio_ibge",
            "nome",
            "dia_vencimento_proprio",
            "dia_vencimento_retido",
            "regra_dia_nao_util",
            "fonte",
            "inicio_vigencia",
            "fim_vigencia",
        ]
        read_only_fields = fields


def _aviso_iss_payload(aviso) -> dict:
    return {"codigo": aviso.codigo, "mensagem": aviso.mensagem, "dispositivo": aviso.dispositivo}


def _data_iso(valor):
    return valor.isoformat() if valor is not None else None


def _texto_decimal(valor):
    return str(valor) if valor is not None else None


def _nota_apurada_payload(nota) -> dict:
    return {
        "identificador": nota.identificador,
        "numero": nota.numero,
        "data_competencia": _data_iso(nota.data_competencia),
        "c_loc_incid": nota.c_loc_incid,
        "subitem": nota.subitem,
        "v_bc": _texto_decimal(nota.v_bc),
        "v_iss_qn": _texto_decimal(nota.v_iss_qn),
        "aliquota_cadastrada": _texto_decimal(nota.aliquota_cadastrada),
        "esperado": _texto_decimal(nota.esperado),
        "diferenca": _texto_decimal(nota.diferenca),
        "conferida": nota.conferida,
        "avisos": list(nota.avisos),
    }


def _nota_relatorio_payload(nota) -> dict:
    return {
        "identificador": nota.identificador,
        "numero": nota.numero,
        "data_competencia": _data_iso(nota.data_competencia),
        "cancelada": nota.cancelada,
        "tomador_documento": nota.tomador_documento,
        "tomador_nome": nota.tomador_nome,
        "c_loc_incid": nota.c_loc_incid,
        "subitem": nota.subitem,
        "v_bc": _texto_decimal(nota.v_bc),
        "p_aliq_aplic": _texto_decimal(nota.p_aliq_aplic),
        "v_iss_qn": _texto_decimal(nota.v_iss_qn),
        "tp_ret_issqn": nota.tp_ret_issqn,
        "ausentes": list(nota.ausentes),
    }


def _grupo_payload(grupo) -> dict:
    return {
        "municipio_ibge": grupo.municipio_ibge,
        "total": str(grupo.total),
        "incompletas": list(grupo.incompletas),
        "vencimento_retido": _data_iso(grupo.vencimento_retido),
        "aviso": grupo.aviso,
    }


def _apuracao_iss_payload(resultado: iss_servico.ApuracaoIss) -> dict:
    return {
        "ano": resultado.ano,
        "mes": resultado.mes,
        "municipio_ibge": resultado.municipio_ibge,
        "nome_municipio": resultado.nome_municipio,
        "regime": resultado.regime,
        "total": str(resultado.total),
        "vencimento_proprio": _data_iso(resultado.vencimento_proprio),
        "vencimento_retido": _data_iso(resultado.vencimento_retido),
        "regra_dia_nao_util": resultado.regra_dia_nao_util,
        "aviso_multa": resultado.aviso_multa,
        "notas": [_nota_apurada_payload(n) for n in resultado.notas],
        "pendencias": [_nota_apurada_payload(n) for n in resultado.pendencias],
        "avisos": [_aviso_iss_payload(a) for a in resultado.avisos],
        "memoria": [
            {
                "ordem": passo.ordem,
                "descricao": passo.descricao,
                "valor": passo.valor,
                "dispositivo": passo.dispositivo,
            }
            for passo in resultado.memoria
        ],
    }


class AliquotasIssView(APIView):
    """GET — aliquotas do ISS do escritório ativo (opcional `municipio`)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request):
        aliquotas = AliquotaIssMunicipal.objects.filter(escritorio=request.escritorio)
        if "municipio" in request.query_params:
            aliquotas = aliquotas.filter(municipio_ibge=request.query_params["municipio"])
        aliquotas = aliquotas.order_by("municipio_ibge", "subitem", "inicio_vigencia", "id")
        return Response(AliquotaIssSerializer(aliquotas, many=True).data)


class CadastrarAliquotaIssView(APIView):
    """POST — cadastra alíquota do escritório. Recusa fora de 2% a 5% (exceção com aviso)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request):
        _recusar_dado_nao_contratado(request, CONTRATO_ALIQUOTA_ISS)
        entrada = AliquotaIssEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            aliquota, avisos = iss_servico.cadastrar_aliquota(
                request.escritorio,
                dict(entrada.validated_data),
                usuario=request.user,
                request=request,
            )
        except iss_servico.EntradaInvalidaIss as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except iss_servico.IssConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(
            {
                **AliquotaIssSerializer(aliquota).data,
                "avisos": [_aviso_iss_payload(a) for a in avisos],
            },
            status=status.HTTP_201_CREATED,
        )


class AliquotaIssDetalheView(APIView):
    """PATCH — altera a alíquota (inclusive o fim da vigência, que a encerra). Sem exclusão."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def patch(self, request, aliquota_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ALIQUOTA_ISS)
        aliquota = get_object_or_404(
            AliquotaIssMunicipal, pk=aliquota_id, escritorio=request.escritorio
        )
        entrada = AliquotaIssEntradaSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        try:
            alterada, avisos = iss_servico.alterar_aliquota(
                aliquota,
                dict(entrada.validated_data),
                usuario=request.user,
                request=request,
            )
        except iss_servico.EntradaInvalidaIss as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except iss_servico.IssConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(
            {
                **AliquotaIssSerializer(alterada).data,
                "avisos": [_aviso_iss_payload(a) for a in avisos],
            },
            status=status.HTTP_200_OK,
        )


class RegrasIssMunicipioView(APIView):
    """GET — regras do ISS por município (leitura; o cadastro não tem rota de API)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request):
        regras = RegraIssMunicipio.objects.all()
        if "municipio" in request.query_params:
            regras = regras.filter(municipio_ibge=request.query_params["municipio"])
        return Response(
            RegraIssSerializer(regras.order_by("municipio_ibge", "inicio_vigencia"), many=True).data
        )


class RegimesIssView(EmpresaEscopadaMixin, APIView):
    """GET — regimes do ISS da empresa, por exercício."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        regimes = RegimeIssEmpresa.objects.filter(empresa=empresa).order_by("exercicio", "id")
        return Response(RegimeIssSerializer(regimes, many=True).data)


class CadastrarRegimeIssView(EmpresaEscopadaMixin, APIView):
    """POST — regime do ISS da empresa no exercício (um por exercício)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_REGIME_ISS)
        empresa = self.get_empresa()
        entrada = RegimeIssEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            regime = iss_servico.cadastrar_regime(
                empresa, dict(entrada.validated_data), usuario=request.user, request=request
            )
        except iss_servico.EntradaInvalidaIss as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except iss_servico.IssConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(RegimeIssSerializer(regime).data, status=status.HTTP_201_CREATED)


class RegimeIssDetalheView(EmpresaEscopadaMixin, APIView):
    """PATCH — altera o regime do ISS da empresa no exercício."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def patch(self, request, empresa_id, regime_id):
        _recusar_dado_nao_contratado(request, CONTRATO_REGIME_ISS)
        empresa = self.get_empresa()
        regime = get_object_or_404(RegimeIssEmpresa, pk=regime_id, empresa=empresa)
        entrada = RegimeIssEntradaSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        try:
            alterado = iss_servico.alterar_regime(
                regime, dict(entrada.validated_data), usuario=request.user, request=request
            )
        except iss_servico.EntradaInvalidaIss as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except iss_servico.IssConflito as exc:
            return _resposta_de_conflito(exc)
        return Response(RegimeIssSerializer(alterado).data, status=status.HTTP_200_OK)


class ApuracaoIssView(EmpresaEscopadaMixin, APIView):
    """GET — ISS próprio do mês (`ano`, `mes`). 409 com TODOS os bloqueios quando não sai."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        try:
            resultado = iss_servico.apuracao_iss_proprio(empresa, ano, mes)
        except iss_servico.IssRecusado as exc:
            return Response(
                {
                    "detail": str(exc),
                    "bloqueios": [_bloqueio_payload(b) for b in exc.bloqueios],
                    "notas": [_nota_relatorio_payload(n) for n in exc.notas],
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_apuracao_iss_payload(resultado))


class RetidoSofridoIssView(EmpresaEscopadaMixin, APIView):
    """GET — ISS retido sofrido do mês (HI-86), para empresa de qualquer regime."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        relatorio = iss_servico.relatorio_iss_retido_sofrido(empresa, ano, mes)
        return Response(
            {
                "ano": relatorio.ano,
                "mes": relatorio.mes,
                "notas": [_nota_relatorio_payload(n) for n in relatorio.notas],
                "grupos": [_grupo_payload(g) for g in relatorio.grupos],
                "avisos": [_aviso_iss_payload(a) for a in relatorio.avisos],
            }
        )


class OutrosMunicipiosIssView(EmpresaEscopadaMixin, APIView):
    """GET — ISS devido a outros municípios do mês (HI-85), sem cálculo."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        relatorio = iss_servico.relatorio_iss_outros_municipios(empresa, ano, mes)
        return Response(
            {
                "ano": relatorio.ano,
                "mes": relatorio.mes,
                "notas": [_nota_relatorio_payload(n) for n in relatorio.notas],
                "grupos": [_grupo_payload(g) for g in relatorio.grupos],
                "avisos": [_aviso_iss_payload(a) for a in relatorio.avisos],
            }
        )


# ---------------------------------------------------------------------------
# DL-078 (frente A): escrituração das NFS-e TOMADAS, ISS retido a recolher e retenções
# federais. Mesma regra da DL-072 nesta API: consultar = `papel_pode_consultar_documentos`
# (exclui CLIENTE; PARALEGAL lê); escriturar, estornar e informar a data de pagamento =
# `papel_pode_escriturar_fiscal`. Autorização no servidor. Isolamento pelo escritório ativo
# e por `EmpresaEscopadaMixin`: empresa de outro escritório responde 404.
# A regra de negócio fica em `apps.fiscal.tomadas` e `apps.fiscal.retencoes`.
# ---------------------------------------------------------------------------

CONTRATO_POST_RASCUNHO_TOMADA = ContratoDeRequisicao(
    campos={"natureza"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no rascunho da escrituração de tomada",
)
CONTRATO_POST_EFETIVAR_TOMADA = ContratoDeRequisicao(
    campos={"natureza"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na efetivação da escrituração de tomada",
)
CONTRATO_POST_ESTORNAR_TOMADA = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração de tomada",
)
CONTRATO_POST_DATA_PAGAMENTO = ContratoDeRequisicao(
    campos={"data_pagamento", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na informação da data de pagamento",
)


class EscrituracaoTomadaSerializer(serializers.ModelSerializer):
    """Saída. Sem ids de usuário: quem fez cada ato está na trilha de auditoria."""

    natureza_descricao = serializers.CharField(source="get_natureza_display", read_only=True)

    class Meta:
        model = EscrituracaoTomada
        fields = [
            "id",
            "vinculo",
            "empresa",
            "natureza",
            "natureza_descricao",
            "estado",
            "data_emissao",
            "data_competencia",
            "tp_ret_issqn",
            "c_loc_incid",
            "valor_servico",
            "valor_liquido",
            "v_iss_qn",
            "v_ret_cp",
            "v_ret_irrf",
            "v_ret_csll",
            "data_pagamento",
            "motivo_pagamento",
            "efetivada_em",
            "estornada_em",
            "motivo_estorno",
            "criado_em",
        ]
        read_only_fields = fields


class NaturezaTomadaEntradaSerializer(serializers.Serializer):
    natureza = serializers.ChoiceField(
        choices=NaturezaTomada.choices,
        allow_blank=True,
        error_messages={
            "required": tomadas_servico.MENSAGEM_NATUREZA_VAZIA,
            "invalid_choice": tomadas_servico.MENSAGEM_NATUREZA_FORA_DO_CATALOGO,
        },
    )

    def validate_natureza(self, valor):
        if not valor:
            raise serializers.ValidationError(tomadas_servico.MENSAGEM_NATUREZA_VAZIA)
        return valor


class DataPagamentoEntradaSerializer(serializers.Serializer):
    data_pagamento = serializers.DateField(
        error_messages={
            "required": "Informe a data de pagamento.",
            "invalid": "Data de pagamento inválida: use o formato AAAA-MM-DD.",
        }
    )
    motivo = serializers.CharField(
        max_length=tomadas_servico.MOTIVO_MAXIMO, trim_whitespace=True, allow_blank=True
    )


def _nota_tomada_payload(nota) -> dict:
    documento = nota.documento
    escrituracao = nota.escrituracao
    return {
        "vinculo_id": nota.vinculo.pk,
        "identificador": documento.identificador,
        "numero": documento.numero,
        "dh_emissao": documento.dh_emissao.isoformat(),
        "data_emissao": _data_iso(nota.data_emissao),
        "data_competencia": _data_iso(documento.d_competencia),
        "valor_servico": _texto_decimal(documento.v_serv),
        "valor_liquido": _texto_decimal(documento.v_liq),
        "tp_ret_issqn": documento.tp_ret_issqn,
        "situacao": nota.situacao,
        "natureza_sugerida": nota.natureza_sugerida,
        "bloqueio": nota.bloqueio,
        "escrituracao_id": escrituracao.pk if escrituracao is not None else None,
        "estado_escrituracao": escrituracao.estado if escrituracao is not None else None,
        "avisos": [_aviso_tomada_payload(a) for a in nota.avisos],
    }


def _aviso_tomada_payload(aviso) -> dict:
    return {"codigo": aviso.codigo, "texto": aviso.texto, "fundamento": aviso.fundamento}


def _nota_escriturada_payload(escrituracao) -> dict:
    return {
        "escrituracao_id": escrituracao.pk,
        "identificador": escrituracao.vinculo.documento.identificador,
        "natureza": escrituracao.natureza,
        "data_emissao": _data_iso(escrituracao.data_emissao),
        "data_competencia": _data_iso(escrituracao.data_competencia),
        "data_pagamento": _data_iso(escrituracao.data_pagamento),
    }


def _par_avisos_payload(pares) -> list[dict]:
    return [
        {"escrituracao_id": escrituracao.pk, **_aviso_tomada_payload(aviso)}
        for escrituracao, aviso in pares
    ]


def _iss_retido_payload(resultado: retencoes_servico.IssRetidoAReceber) -> dict:
    return {
        "ano": resultado.ano,
        "mes": resultado.mes,
        "grupos": [
            {
                "municipio": grupo.municipio,
                "total": _texto_decimal(grupo.total),
                "vencimento": _data_iso(grupo.vencimento),
                "vencimento_texto": grupo.vencimento_texto,
                "regra_dia_nao_util": grupo.regra_dia_nao_util,
                "notas": [_nota_escriturada_payload_com_iss(e) for e in grupo.notas],
                "sem_valor_destacado": [_nota_escriturada_payload(e) for e in grupo.sem_valor],
            }
            for grupo in resultado.grupos
        ],
        "fora_do_total": [_nota_escriturada_payload(e) for e in resultado.fora_do_total],
        "canceladas": [_nota_escriturada_payload(e) for e in resultado.canceladas],
        "avisos": _par_avisos_payload(resultado.avisos),
    }


def _nota_escriturada_payload_com_iss(escrituracao) -> dict:
    payload = _nota_escriturada_payload(escrituracao)
    payload["v_iss_qn"] = _texto_decimal(escrituracao.v_iss_qn)
    return payload


def _pagamentos_payload(grupos) -> list[dict]:
    return [
        {
            "data_pagamento": _data_iso(grupo.data_pagamento),
            "total": _texto_decimal(grupo.total),
            "notas": [_nota_escriturada_payload(e) for e in grupo.notas],
        }
        for grupo in grupos
    ]


def _retencoes_federais_payload(resultado: retencoes_servico.RetencoesFederais) -> dict:
    return {
        "ano": resultado.ano,
        "mes": resultado.mes,
        "inss": {
            "rotulo": "INSS retido (contribuição previdenciária, vRetCP), mês de emissão",
            "total": _texto_decimal(resultado.inss_total),
            "vencimento": _data_iso(resultado.inss_vencimento),
            "vencimento_texto": resultado.inss_vencimento_texto,
            "notas": [_nota_escriturada_payload_com_iss(e) for e in resultado.inss_notas],
        },
        "irrf": {
            "rotulo": "IRRF retido (vRetIRRF), por data de pagamento",
            "total": _texto_decimal(resultado.irrf_total),
            "por_pagamento": _pagamentos_payload(resultado.irrf_por_pagamento),
        },
        "csrf": {
            "rotulo": "CSRF retida (PIS + COFINS + CSLL, vRetCSLL), por data de pagamento",
            "total": _texto_decimal(resultado.csrf_total),
            "por_pagamento": _pagamentos_payload(resultado.csrf_por_pagamento),
        },
        "pendentes_de_pagamento": [
            _nota_escriturada_payload(e) for e in resultado.pendentes_de_pagamento
        ],
        "canceladas": [_nota_escriturada_payload(e) for e in resultado.canceladas],
        "avisos": _par_avisos_payload(resultado.avisos),
    }


class NotasTomadasView(EmpresaEscopadaMixin, APIView):
    """GET — notas em que a empresa é TOMADORA, com competência `ano/mes` (lista a escriturar)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        notas = tomadas_servico.notas_tomadas(empresa, ano, mes)
        return Response(
            {
                "ano": ano,
                "mes": mes,
                "notas": [_nota_tomada_payload(n) for n in notas],
            }
        )


class RascunhoTomadaView(EmpresaEscopadaMixin, APIView):
    """POST — grava a natureza de uma nota tomada como rascunho (ainda não efetivada)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, vinculo_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_RASCUNHO_TOMADA)
        empresa = self.get_empresa()
        vinculo = get_object_or_404(
            VinculoDocumentoEmpresa,
            pk=vinculo_id,
            empresa=empresa,
            documento__escritorio=request.escritorio,
        )
        entrada = NaturezaTomadaEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            escrituracao = tomadas_servico.salvar_rascunho(
                vinculo,
                entrada.validated_data["natureza"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)
        return Response(EscrituracaoTomadaSerializer(escrituracao).data, status=status.HTTP_200_OK)


class EfetivarTomadaView(EmpresaEscopadaMixin, APIView):
    """POST — efetiva a nota tomada com a natureza confirmada.

    201 quando cria ou transforma um rascunho; 200 quando a mesma natureza já estava efetivada.
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, vinculo_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_EFETIVAR_TOMADA)
        empresa = self.get_empresa()
        vinculo = get_object_or_404(
            VinculoDocumentoEmpresa,
            pk=vinculo_id,
            empresa=empresa,
            documento__escritorio=request.escritorio,
        )
        entrada = NaturezaTomadaEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            escrituracao = tomadas_servico.efetivar_escrituracao_tomada(
                vinculo,
                entrada.validated_data["natureza"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)
        codigo = status.HTTP_201_CREATED if escrituracao.criada_agora else status.HTTP_200_OK
        return Response(EscrituracaoTomadaSerializer(escrituracao).data, status=codigo)


class EstornarTomadaView(EmpresaEscopadaMixin, APIView):
    """POST — estorna a escrituração de tomada efetivada, com motivo obrigatório."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNAR_TOMADA)
        empresa = self.get_empresa()
        escrituracao = get_object_or_404(EscrituracaoTomada, pk=escrituracao_id, empresa=empresa)
        entrada = EstornarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estornada = tomadas_servico.estornar_escrituracao_tomada(
                escrituracao,
                entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)
        return Response(EscrituracaoTomadaSerializer(estornada).data, status=status.HTTP_200_OK)


class DataPagamentoTomadaView(EmpresaEscopadaMixin, APIView):
    """POST — informa ou corrige a data de pagamento de uma escrituração de tomada efetivada."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_DATA_PAGAMENTO)
        empresa = self.get_empresa()
        escrituracao = get_object_or_404(EscrituracaoTomada, pk=escrituracao_id, empresa=empresa)
        entrada = DataPagamentoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            informada = tomadas_servico.informar_data_pagamento(
                escrituracao,
                entrada.validated_data["data_pagamento"],
                entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaEscrituracao as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoErro as exc:
            return _resposta_de_conflito(exc)
        codigo = status.HTTP_201_CREATED if informada.criada_agora else status.HTTP_200_OK
        return Response(EscrituracaoTomadaSerializer(informada).data, status=codigo)


class IssRetidoTomadoView(EmpresaEscopadaMixin, APIView):
    """GET — ISS retido a recolher pelo cliente tomador, por município, na competência."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        resultado = retencoes_servico.iss_retido_a_recolher(empresa, ano, mes)
        return Response(_iss_retido_payload(resultado))


class RetencoesFederaisTomadoView(EmpresaEscopadaMixin, APIView):
    """GET — retenções federais destacadas nas notas tomadas, por tributo, na competência."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        resultado = retencoes_servico.retencoes_federais(empresa, ano, mes)
        return Response(_retencoes_federais_payload(resultado))
