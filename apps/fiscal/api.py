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
from apps.fiscal.models import (
    EscrituracaoFiscal,
    NaturezaOperacao,
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
    natureza_sugerida = serializers.CharField(read_only=True)
    competencia_difere_da_emissao = serializers.BooleanField(read_only=True)
    escrituracao_id = serializers.SerializerMethodField()
    estado_escrituracao = serializers.SerializerMethodField()

    def get_escrituracao_id(self, obj):
        return obj.escrituracao.pk if obj.escrituracao is not None else None

    def get_estado_escrituracao(self, obj):
        return obj.escrituracao.estado if obj.escrituracao is not None else None


class EfetivarEntradaSerializer(serializers.Serializer):
    natureza = serializers.ChoiceField(choices=NaturezaOperacao.choices)


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
