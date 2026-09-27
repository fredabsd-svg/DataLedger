"""API do livro-caixa (DL-046, fatia 1) — servidor + API; a tela vem depois
pelo frontend.

Mesmo desenho geral de `apps.contabilidade.views`: um mixin único traduz a
recusa por modo de escrituração (aqui, o INVERSO — recusa quem NÃO está em
livro-caixa) para 400 do DRF; a criação de conta e de lançamento passa pelo
SERVIÇO (`apps.livro_caixa.services`), nunca por `serializer.save()` direto,
porque é o serviço que aplica `full_clean()`, idempotência e trilha de
auditoria na mesma transação; a política dos cinco dicionários (BL-196) é
aplicada em toda rota de escrita, com o contrato dela declarado ao lado.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.escolhas import EscolhaInvalida, para_escolha
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import RestricaoViolada
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.models import ContaLivroCaixa, LancamentoCaixa, OrigemRecebimento
from apps.livro_caixa.permissoes import papel_pode_ler_livro_caixa
from apps.livro_caixa.serializers import ContaLivroCaixaSerializer, LancamentoCaixaSerializer
from apps.livro_caixa.services import (
    ChaveIdempotenciaConflitanteCaixa,
    LancamentoCaixaInvalido,
    apurar_livro_caixa,
    criar_conta_livro_caixa,
    criar_lancamento_caixa,
    estornar_lancamento_caixa,
)
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido


class EmpresaEscopadaLivroCaixaMixin(EmpresaEscopadaMixin):
    """`EmpresaEscopadaMixin` + a recusa do livro-caixa para empresa em modo
    contabilidade — o ESPELHO de `apps.contabilidade.views.
    EmpresaEscopadaContabilMixin` (DL-038/DE-075), PONTO ÚNICO desta recusa
    para toda rota de API do livro-caixa. A REGRA mora só em `apps.empresas.
    services.recusar_se_nao_livro_caixa`; este método só chama e traduz para
    o formato do DRF (400, nunca 403 — não é falta de permissão, é o TIPO de
    escrituração da empresa que não comporta a operação).
    """

    def get_empresa(self):
        empresa = super().get_empresa()
        try:
            recusar_se_nao_livro_caixa(empresa)
        except EmpresaNaoEmModoLivroCaixa as exc:
            raise DRFValidationError({"empresa": [exc.mensagem]}) from exc
        return empresa


def _recusar_dado_nao_contratado(request, contrato):
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _erro_de_validacao_como_drf(exc):
    """Traduz `django.core.exceptions.ValidationError` (de `full_clean()`)
    para `rest_framework.exceptions.ValidationError`, preservando o campo de
    cada erro quando `full_clean()` já os separou por campo
    (`exc.message_dict`) — nunca um texto único que esconda QUAL campo
    falhou."""
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError(exc.messages)


# Mesma matriz de papéis da contabilidade (instrução da tarefa DL-046):
# escritura quem escritura, lê quem lê — ver `apps.livro_caixa.permissoes`
# para o motivo de a tupla ser copiada por VALOR, não referenciada.
PodeEscriturarLivroCaixa = papel_permitido(
    Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO
)


class PodeLerLivroCaixa(BasePermission):
    message = "Papel sem permissão para ler o livro-caixa."

    def has_permission(self, request, view):
        return papel_pode_ler_livro_caixa(getattr(request, "papel", None))


CONTRATO_POST_CONTA_CAIXA = ContratoDeRequisicao(
    campos={"codigo", "nome", "natureza", "codigo_carne_leao", "ativa"},
    contexto="no cadastro de conta do livro-caixa",
)

CONTRATO_POST_LANCAMENTO_CAIXA = ContratoDeRequisicao(
    campos={
        "conta",
        "data",
        "valor",
        "historico",
        "documento_origem",
        "recebido_de",
        "cpf_titular_pagamento",
        "cpf_beneficiario_servico",
        "cpf_beneficiario_nao_informado",
        "cnpj_pagador",
    },
    contexto="no lançamento de caixa",
)

# Estorno é rota de AÇÃO: o que estornar vem da URL, sem corpo — mesmo
# desenho de `CONTRATO_POST_ESTORNO` (contabilidade).
CONTRATO_POST_ESTORNO_CAIXA = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno de caixa",
)

TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA_CAIXA = 255


class PaginacaoLancamentoCaixa(PageNumberPagination):
    """B6 (rodada 1 de auditoria): a lista de lançamentos não tinha
    paginação — 14 consultas com 5 lançamentos, 59 com 50, crescendo sem
    teto. `page_size` generoso o bastante para não incomodar o uso comum
    (um mês de movimento cabe numa página), com `page_size_query_param`
    para o cliente pedir menos quando quiser."""

    page_size = 100
    page_size_query_param = "tamanho_pagina"
    max_page_size = 500


class ContaLivroCaixaListCreateView(EmpresaEscopadaLivroCaixaMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = ContaLivroCaixaSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturarLivroCaixa())
        else:
            permissions.append(PodeLerLivroCaixa())
        return permissions

    def get_queryset(self):
        return ContaLivroCaixa.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        # BL-196: a política dos cinco dicionários ANTES de qualquer
        # gravação — mesmo raciocínio de `ContaListCreateView`
        # (contabilidade): um `empresa`/`id` no corpo, ignorado em
        # silêncio, sugeriria ao cliente ter escolhido o que na verdade o
        # servidor decide.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_CONTA_CAIXA)
        dados = request.data if isinstance(request.data, dict) else {}

        # B3 (rodada 1 de auditoria): `codigo` e `nome` só são aceitos como
        # TEXTO — sem esta checagem, `{"codigo": ["X1"]}` gravava o texto
        # `"['X1']"` (o `str()` do Python sobre a lista, dentro do
        # `CharField`), e um `codigo`/`nome` só de espaços passava (o
        # `CharField` do modelo aceita, `blank=False` só recusa STRING
        # vazia, não string em branco). `strip()` — mesmo padrão de
        # `historico` (contabilidade) — para "  " não contar como um
        # código/nome preenchido.
        codigo = dados.get("codigo")
        nome = dados.get("nome")
        if not isinstance(codigo, str):
            raise DRFValidationError("O campo 'codigo' deve ser texto.")
        if not isinstance(nome, str):
            raise DRFValidationError("O campo 'nome' deve ser texto.")
        codigo = codigo.strip()
        nome = nome.strip()
        if not codigo:
            raise DRFValidationError("O campo 'codigo' não pode ficar em branco.")
        if not nome:
            raise DRFValidationError("O campo 'nome' não pode ficar em branco.")

        try:
            conta = criar_conta_livro_caixa(
                empresa=self.get_empresa(),
                codigo=codigo,
                nome=nome,
                natureza=dados.get("natureza"),
                codigo_carne_leao=dados.get("codigo_carne_leao"),
                ativa=dados.get("ativa", True),
                criado_por=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise _erro_de_validacao_como_drf(exc) from exc
        except RestricaoViolada as exc:
            raise DRFValidationError({"codigo": [str(exc)]}) from exc

        serializer = self.get_serializer(conta)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _extrair_conta(dados, empresa):
    try:
        conta_bruta = dados["conta"]
    except (KeyError, TypeError) as exc:
        raise DRFValidationError("Informe 'conta'.") from exc
    try:
        conta_id = para_id(conta_bruta)
    except IdentificadorInvalido as exc:
        raise DRFValidationError(f"Conta inválida para esta empresa: {exc}") from exc
    try:
        return ContaLivroCaixa.objects.get(pk=conta_id, empresa=empresa)
    except ContaLivroCaixa.DoesNotExist as exc:
        raise DRFValidationError("Conta inválida para esta empresa.") from exc


class LancamentoCaixaListCreateView(EmpresaEscopadaLivroCaixaMixin, generics.ListAPIView):
    """Lista os lançamentos de caixa da empresa; `POST` cria um novo."""

    permission_classes = [TemEscritorioAtivo]
    serializer_class = LancamentoCaixaSerializer
    pagination_class = PaginacaoLancamentoCaixa

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturarLivroCaixa())
        else:
            permissions.append(PodeLerLivroCaixa())
        return permissions

    def get_queryset(self):
        return LancamentoCaixa.objects.filter(empresa=self.get_empresa()).select_related("conta")

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        # BL-196: mesmo raciocínio de `LancamentoListCreateView`
        # (contabilidade) — a idempotência usa CABEÇALHO
        # (`Idempotency-Key`), então este contrato não a declara como
        # ignorada.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_LANCAMENTO_CAIXA)
        dados = request.data if isinstance(request.data, dict) else {}

        conta = _extrair_conta(dados, empresa)

        try:
            data_bruta = dados["data"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Informe 'data' no formato AAAA-MM-DD.") from exc
        try:
            data_lancamento = para_data(data_bruta)
        except DataInvalida as exc:
            raise DRFValidationError(f"'data' inválida: {exc}") from exc

        try:
            valor_bruto = dados["valor"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Informe 'valor'.") from exc
        # DE-030: `valor` só é aceito como TEXTO — um número JSON perderia
        # precisão binária ao ser decodificado pelo parser, ANTES de
        # qualquer checagem (mesmo raciocínio de `_extrair_itens`,
        # contabilidade).
        if not isinstance(valor_bruto, str):
            raise DRFValidationError(
                f"'valor' inválido: {valor_bruto!r} precisa ser enviado como TEXTO "
                '(ex.: "100.00"), nunca como número JSON.'
            )
        try:
            para_decimal(valor_bruto)
        except ValorMonetarioInvalido as exc:
            raise DRFValidationError(f"'valor' inválido: {exc}") from exc

        historico = dados.get("historico", "")
        if not isinstance(historico, str):
            raise DRFValidationError("O campo 'historico' deve ser texto.")

        recebido_de_bruto = dados.get("recebido_de")
        recebido_de = None
        if recebido_de_bruto is not None:
            try:
                recebido_de = para_escolha(
                    recebido_de_bruto, OrigemRecebimento.values, nome_campo="recebido_de"
                )
            except EscolhaInvalida as exc:
                raise DRFValidationError(str(exc)) from exc

        for campo in (
            "documento_origem",
            "cpf_titular_pagamento",
            "cpf_beneficiario_servico",
            "cnpj_pagador",
        ):
            valor_campo = dados.get(campo, "")
            if valor_campo is not None and not isinstance(valor_campo, str):
                raise DRFValidationError(f"O campo '{campo}' deve ser texto.")

        cpf_beneficiario_nao_informado = dados.get("cpf_beneficiario_nao_informado", False)
        if not isinstance(cpf_beneficiario_nao_informado, bool):
            raise DRFValidationError("O campo 'cpf_beneficiario_nao_informado' deve ser booleano.")

        chave_idempotencia = (request.headers.get("Idempotency-Key") or "").strip() or None
        if chave_idempotencia and len(chave_idempotencia) > TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA_CAIXA:
            raise DRFValidationError(
                "O cabeçalho Idempotency-Key não pode ter mais de "
                f"{TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA_CAIXA} caracteres."
            )

        try:
            lancamento = criar_lancamento_caixa(
                empresa=empresa,
                conta=conta,
                data=data_lancamento,
                valor=valor_bruto,
                historico=historico,
                documento_origem=dados.get("documento_origem", "") or "",
                recebido_de=recebido_de,
                cpf_titular_pagamento=dados.get("cpf_titular_pagamento", "") or "",
                cpf_beneficiario_servico=dados.get("cpf_beneficiario_servico", "") or "",
                cpf_beneficiario_nao_informado=cpf_beneficiario_nao_informado,
                cnpj_pagador=dados.get("cnpj_pagador", "") or "",
                criado_por=request.user,
                chave_idempotencia=chave_idempotencia,
                request=request,
            )
        except ChaveIdempotenciaConflitanteCaixa as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LancamentoCaixaInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        status_code = status.HTTP_201_CREATED if lancamento.criado_agora else status.HTTP_200_OK
        serializer = self.get_serializer(lancamento)
        return Response(serializer.data, status=status_code)


class EstornarLancamentoCaixaView(EmpresaEscopadaLivroCaixaMixin, APIView):
    permission_classes = [TemEscritorioAtivo, PodeEscriturarLivroCaixa]

    def post(self, request, empresa_id, lancamento_id):
        # A data do estorno é decidida pelo SERVIDOR (mesmo RC-78 aplicado
        # por analogia, ver `services.estornar_lancamento_caixa`) — corpo
        # com `data` sugeriria ao cliente ter escolhido o que o servidor
        # decide.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNO_CAIXA)
        empresa = self.get_empresa()
        lancamento = get_object_or_404(LancamentoCaixa, pk=lancamento_id, empresa=empresa)

        try:
            estorno = estornar_lancamento_caixa(
                lancamento, criado_por=request.user, request=request
            )
        except LancamentoCaixaInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = LancamentoCaixaSerializer(estorno)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LivroCaixaView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """Relatório "Livro Caixa" do período `inicio`/`fim` (querystring),
    CONCILIÁVEL com os lançamentos de origem (critério 5 do plano) —
    `apps.livro_caixa.services.apurar_livro_caixa` faz a apuração; esta
    view só extrai o período e serializa a resposta.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()

        bruto_inicio = request.query_params.get("inicio")
        bruto_fim = request.query_params.get("fim")
        if not bruto_inicio or not bruto_fim:
            raise DRFValidationError(
                "Informe 'inicio' e 'fim' (formato AAAA-MM-DD) na querystring."
            )
        try:
            inicio = para_data(bruto_inicio)
        except DataInvalida as exc:
            raise DRFValidationError(f"'inicio' inválido: {exc}") from exc
        try:
            fim = para_data(bruto_fim)
        except DataInvalida as exc:
            raise DRFValidationError(f"'fim' inválido: {exc}") from exc
        if inicio > fim:
            raise DRFValidationError(
                f"'inicio' ({inicio.isoformat()}) não pode ser posterior a 'fim' "
                f"({fim.isoformat()})."
            )

        apuracao = apurar_livro_caixa(empresa=empresa, inicio=inicio, fim=fim)

        return Response(
            {
                "empresa": apuracao["empresa_id"],
                "data_inicio": apuracao["data_inicio"].isoformat(),
                "data_fim": apuracao["data_fim"].isoformat(),
                "itens": [
                    {
                        "lancamento_id": item["lancamento_id"],
                        "data": item["data"].isoformat(),
                        "conta": item["conta"],
                        "conta_nome": item["conta_nome"],
                        "natureza": item["natureza"],
                        "grupo": item["grupo"],
                        "valor": str(item["valor"]),
                        "historico": item["historico"],
                        "documento_origem": item["documento_origem"],
                        "estorno_de_id": item["estorno_de_id"],
                        "e_estorno": item["e_estorno"],
                    }
                    for item in apuracao["itens"]
                ],
                "total_entradas": str(apuracao["total_entradas"]),
                # D3 (rodada 1 de auditoria, DE-087 item 13): `P20` (imposto
                # pago, previdência oficial, pensão alimentícia) em grupo
                # PRÓPRIO, separado das despesas de custeio — são deduções
                # do carnê-leão (art. 68, RIR/2018), não despesas do
                # livro-caixa. `total_saidas` continua a SOMA dos dois
                # grupos, mantido por compatibilidade; o saldo de caixa não
                # muda (as duas saídas reduzem o caixa igualmente).
                "total_saidas_custeio": str(apuracao["total_saidas_custeio"]),
                "total_saidas_deducao_carne_leao": str(apuracao["total_saidas_deducao_carne_leao"]),
                "total_saidas": str(apuracao["total_saidas"]),
                "saldo": str(apuracao["saldo"]),
            },
            status=status.HTTP_200_OK,
        )
