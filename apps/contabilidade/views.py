import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoPartida,
)
from apps.contabilidade.serializers import ContaSerializer, LancamentoContabilSerializer
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    LancamentoInvalido,
    criar_lancamento,
    estornar_lancamento,
)
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido

# Mesmo limite do CharField `chave_idempotencia` (models.py). Validado aqui,
# na fronteira da API, para que um cabeçalho longo demais vire 400 (entrada
# do cliente) em vez de vazar como 500 do banco (`DataError: value too long
# for type character varying(255)` — achado A3 da auditoria).
TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA = 255


def _como_moeda(valor):
    """Formata um Decimal monetário como string com duas casas.

    SQLite (usado em desenvolvimento local) não preserva a escala de um
    DecimalField em agregações (`Sum`) como o PostgreSQL faz; sem esta
    normalização, um saldo exato como 1000.00 poderia virar "1000" só por
    causa do banco usado no ambiente, mascarando o valor real.
    """
    return str(Decimal(valor).quantize(Decimal("0.01")))


# Consulta é liberada a qualquer papel vinculado ao escritório ativo;
# lançar/editar o plano de contas ou a escrituração é restrito a quem
# efetivamente cuida da contabilidade do escritório.
PodeEscriturar = papel_permitido(
    Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO
)


class ContaListCreateView(EmpresaEscopadaMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = ContaSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        return permissions

    def get_queryset(self):
        return Conta.objects.filter(empresa=self.get_empresa())

    def get_serializer_context(self):
        # A empresa do contexto vem do escopo da URL, já revalidada contra o
        # escritório ativo (EmpresaEscopadaMixin.get_empresa()) — nunca de um
        # campo enviado pelo cliente. É o que permite ao serializer recusar
        # `conta_pai` de outra empresa (BL-40) sem confiar no payload.
        context = super().get_serializer_context()
        context["empresa"] = self.get_empresa()
        return context

    def perform_create(self, serializer):
        conta = serializer.save(empresa=self.get_empresa())
        registrar(acao="conta.criada", objeto=conta, request=self.request)


def _extrair_itens(payload_itens, empresa):
    """Valida e converte os itens recebidos da API em dados prontos para o serviço."""
    if not isinstance(payload_itens, list) or len(payload_itens) < 2:
        raise DRFValidationError("Informe ao menos duas partidas (itens).")

    itens = []
    for item in payload_itens:
        try:
            conta = Conta.objects.get(pk=item["conta"], empresa=empresa)
        except (Conta.DoesNotExist, KeyError, TypeError) as exc:
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            valor = Decimal(str(item["valor"]))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise DRFValidationError("Valor inválido em um dos itens.") from exc

        tipo = item.get("tipo")
        if tipo not in TipoPartida.values:
            raise DRFValidationError("Tipo de partida inválido (use debito ou credito).")

        itens.append({"conta": conta, "tipo": tipo, "valor": valor})
    return itens


class LancamentoListCreateView(EmpresaEscopadaMixin, generics.ListAPIView):
    """Diário: lista cronológica dos lançamentos da empresa; POST cria um novo."""

    permission_classes = [TemEscritorioAtivo]
    serializer_class = LancamentoContabilSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        return permissions

    def get_queryset(self):
        return LancamentoContabil.objects.filter(empresa=self.get_empresa()).prefetch_related(
            "itens__conta"
        )

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        dados = request.data
        itens = _extrair_itens(dados.get("itens"), empresa)

        try:
            data_lancamento = date.fromisoformat(dados["data"])
        except (KeyError, ValueError) as exc:
            raise DRFValidationError("Informe 'data' no formato AAAA-MM-DD.") from exc

        # Idempotência opcional (BL-41): o cliente decide quando quer garantia
        # de não duplicar em caso de repetição de rede ou duplo clique,
        # enviando um cabeçalho próprio. Sem o cabeçalho, o comportamento é
        # exatamente o de antes (cada POST cria um lançamento) — contrato
        # compatível, nada muda para quem não envia a chave.
        #
        # `strip()` + tratar string vazia como ausente (achado A4): " " e "  "
        # não podem contar como duas chaves DISTINTAS — um cliente que só
        # envia espaço em branco não pretendia usar idempotência nenhuma.
        chave_idempotencia = (request.headers.get("Idempotency-Key") or "").strip() or None
        if chave_idempotencia and len(chave_idempotencia) > TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA:
            raise DRFValidationError(
                f"O cabeçalho Idempotency-Key não pode ter mais de "
                f"{TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA} caracteres."
            )

        try:
            lancamento = criar_lancamento(
                empresa=empresa,
                data=data_lancamento,
                historico=dados.get("historico", ""),
                itens=itens,
                criado_por=request.user,
                chave_idempotencia=chave_idempotencia,
            )
        except ChaveIdempotenciaConflitante as exc:
            # Conflito de estado (a chave já existe com outro conteúdo), não
            # entrada inválida: 409, não 400 — e nada foi gravado (achado A2).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LancamentoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        # O serviço informa se de fato criou ou reaproveitou um lançamento
        # existente (mesma Idempotency-Key). A trilha de auditoria e o
        # status HTTP precisam refletir o resultado real, nunca "criado" por
        # padrão: um registro de auditoria que afirma criação que não
        # aconteceu deixa de sustentar prova (AGENTS.md §11), e 201 numa
        # repetição afirmaria um fato falso. Repetição não é erro — é
        # informação útil (duplo clique, tempestade de retentativa) e por
        # isso vira uma ação própria, rastreável, em vez de ficar oculta
        # atrás de "lancamento.criado". `lancamento.criado_agora` é acessado
        # direto (sem `getattr(..., True)`): `criar_lancamento` sempre define
        # este atributo antes de devolver o objeto, e um padrão "True" por
        # omissão falharia ABERTO exatamente no mesmo sentido do defeito que
        # esta correção existe para fechar (achado A7).
        if lancamento.criado_agora:
            registrar(acao="lancamento.criado", objeto=lancamento, request=request)
            status_code = status.HTTP_201_CREATED
        else:
            registrar(
                acao="lancamento.criacao_repetida",
                objeto=lancamento,
                request=request,
                # Só um hash curto da chave, nunca a chave crua (achado A8):
                # é uma string arbitrária vinda do cliente, e `registrar()`
                # só deve receber dados não sensíveis. O hash ainda permite
                # correlacionar repetições da MESMA chave entre registros.
                detalhes={
                    "chave_idempotencia_hash": hashlib.sha256(
                        chave_idempotencia.encode("utf-8")
                    ).hexdigest()[:12]
                },
            )
            status_code = status.HTTP_200_OK

        serializer = self.get_serializer(lancamento)
        return Response(serializer.data, status=status_code)


class EstornarLancamentoView(EmpresaEscopadaMixin, APIView):
    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def post(self, request, empresa_id, lancamento_id):
        empresa = self.get_empresa()
        lancamento = get_object_or_404(LancamentoContabil, pk=lancamento_id, empresa=empresa)

        try:
            estorno = estornar_lancamento(lancamento, criado_por=request.user)
        except LancamentoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        registrar(
            acao="lancamento.estornado",
            objeto=estorno,
            request=request,
            detalhes={"lancamento_original_id": lancamento.pk},
        )
        serializer = LancamentoContabilSerializer(estorno)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RazaoView(EmpresaEscopadaMixin, APIView):
    """Razão de uma conta: itens de lançamento em ordem cronológica com saldo acumulado."""

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

        itens = (
            ItemLancamento.objects.filter(conta=conta)
            .select_related("lancamento")
            .order_by("lancamento__data", "lancamento__criado_em", "id")
        )

        saldo = Decimal("0")
        linhas = []
        for item in itens:
            sinal = 1 if item.tipo == TipoPartida.DEBITO else -1
            if conta.natureza == NaturezaConta.CREDORA:
                sinal *= -1
            saldo += sinal * item.valor
            linhas.append(
                {
                    "lancamento_id": item.lancamento_id,
                    "data": item.lancamento.data,
                    "historico": item.lancamento.historico,
                    "tipo": item.tipo,
                    # Decimal como string: o encoder JSON padrão do DRF
                    # converte Decimal para float fora de um DecimalField de
                    # serializer, o que quebraria a precisão decimal exigida
                    # para valores monetários (AGENTS.md, seção 10).
                    "valor": _como_moeda(item.valor),
                    "saldo": _como_moeda(saldo),
                }
            )

        return Response({"conta": conta.codigo, "saldo_final": _como_moeda(saldo), "itens": linhas})


class BalanceteView(EmpresaEscopadaMixin, APIView):
    """Saldo atual de cada conta que aceita lançamento, considerando sua natureza."""

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        linhas = []
        for conta in Conta.objects.filter(empresa=empresa, aceita_lancamento=True):
            total_debito = conta.itens_lancamento.filter(tipo=TipoPartida.DEBITO).aggregate(
                total=Sum("valor")
            )["total"] or Decimal("0")
            total_credito = conta.itens_lancamento.filter(tipo=TipoPartida.CREDITO).aggregate(
                total=Sum("valor")
            )["total"] or Decimal("0")
            saldo = (
                total_debito - total_credito
                if conta.natureza == NaturezaConta.DEVEDORA
                else total_credito - total_debito
            )
            linhas.append({"conta": conta.codigo, "nome": conta.nome, "saldo": _como_moeda(saldo)})

        return Response(linhas)
