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
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import (
    AtividadeEmpresa,
    EnquadramentoAtividade,
    EscrituracaoFiscal,
    FolhaFatorR,
    MercadoReceita,
    NaturezaOperacao,
    OrigemReceitaInformada,
    ReceitaInformada,
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
    remuneracao_empregados_avulsos = serializers.DecimalField(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    pro_labore_autonomos = serializers.DecimalField(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    decimo_terceiro = serializers.DecimalField(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    cpp_recolhida = serializers.DecimalField(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
    fgts_recolhido = serializers.DecimalField(
        max_digits=17, decimal_places=2, min_value=Decimal("0")
    )
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
    """GET — pré-DAS do mês (ano/mes). 409 com a lista de bloqueios quando não calcula."""

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
