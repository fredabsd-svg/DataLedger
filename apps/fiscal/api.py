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
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import (
    EscrituracaoFiscal,
    MercadoReceita,
    NaturezaOperacao,
    OrigemReceitaInformada,
    ReceitaInformada,
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
    campos={"ano", "mes", "mercado", "valor", "origem", "motivo", "documento_suporte"},
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
            "estado",
            "confirmada_em",
            "estornada_em",
            "motivo_estorno",
            "criado_em",
        ]
        read_only_fields = fields


class ReceitaInformadaEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(
        min_value=receita_servico.ANO_MINIMO, max_value=receita_servico.ANO_MAXIMO
    )
    mes = serializers.IntegerField(min_value=1, max_value=12)
    mercado = serializers.ChoiceField(choices=MercadoReceita.choices)
    valor = serializers.DecimalField(max_digits=17, decimal_places=2, min_value=Decimal("0.01"))
    origem = serializers.ChoiceField(choices=OrigemReceitaInformada.choices)
    motivo = serializers.CharField(max_length=receita_servico.MOTIVO_MAXIMO, trim_whitespace=True)
    documento_suporte = serializers.CharField(
        max_length=receita_servico.DOCUMENTO_SUPORTE_MAXIMO, trim_whitespace=True
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
