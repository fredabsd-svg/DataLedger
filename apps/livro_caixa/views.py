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

import re
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
from apps.livro_caixa.carne_leao import (
    DependentesCarneLeaoInvalido,
    TabelaCarneLeaoNaoConfigurada,
    apurar_carne_leao_anual,
    apurar_carne_leao_mensal,
    registrar_dependentes_carne_leao,
    retificar_dependentes_carne_leao,
)
from apps.livro_caixa.carne_leao_arquivos import (
    GeracaoArquivoCarneLeaoBloqueada,
    PeriodoInvalidoParaArquivoCarneLeaoWeb,
    conferencia_sem_movimento,
    gerar_arquivos_carne_leao,
)
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    DependentesCarneLeaoCliente,
    LancamentoCaixa,
    OrigemRecebimento,
)
from apps.livro_caixa.permissoes import (
    papel_pode_fechar_mes_caixa,
    papel_pode_ler_livro_caixa,
)
from apps.livro_caixa.serializers import (
    ContaLivroCaixaSerializer,
    DependentesCarneLeaoClienteSerializer,
    LancamentoCaixaSerializer,
)
from apps.livro_caixa.services import (
    ChaveIdempotenciaConflitanteCaixa,
    FechamentoMesCaixaInvalido,
    FechamentoMesCaixaRecusado,
    LancamentoCaixaInvalido,
    MesCaixaEncerrado,
    ReaberturaExigeCascata,
    apurar_livro_caixa,
    criar_conta_livro_caixa,
    criar_lancamento_caixa,
    encerrar_mes_caixa,
    estado_dos_meses_caixa,
    estornar_lancamento_caixa,
    reabrir_mes_caixa,
    reabrir_mes_caixa_em_cascata,
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
    campos={"codigo", "nome", "natureza", "codigo_carne_leao", "codigo_ocupacao", "ativa"},
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
        # DL-046, fatia 3 (RC-127): IRRF retido (só rendimento de PJ) e
        # competência/multa/juros do pagamento de previdência oficial.
        "valor_irrf",
        "competencia_previdencia",
        "multa_previdencia",
        "juros_previdencia",
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

        # DL-046, fatia 3 (RC-127/HI-34): sobreposição opcional do código de
        # ocupação — mesma checagem de tipo de `codigo`/`nome`, acima.
        codigo_ocupacao = dados.get("codigo_ocupacao", "")
        if codigo_ocupacao is not None and not isinstance(codigo_ocupacao, str):
            raise DRFValidationError("O campo 'codigo_ocupacao' deve ser texto.")

        try:
            conta = criar_conta_livro_caixa(
                empresa=self.get_empresa(),
                codigo=codigo,
                nome=nome,
                natureza=dados.get("natureza"),
                codigo_carne_leao=dados.get("codigo_carne_leao"),
                codigo_ocupacao=(codigo_ocupacao or "").strip(),
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

        # DL-046, fatia 3 (RC-127): três valores monetários OPCIONAIS —
        # mesma regra de 'valor' (DE-030): só TEXTO, nunca número JSON (que
        # perderia precisão binária antes de qualquer checagem). Ausente ou
        # `None` é aceito (campo opcional); a CONVERSÃO para `Decimal` e a
        # coerência com o código da conta ficam no serviço/modelo.
        valores_monetarios_opcionais = {}
        for campo in ("valor_irrf", "multa_previdencia", "juros_previdencia"):
            valor_campo = dados.get(campo)
            if valor_campo is not None and not isinstance(valor_campo, str):
                raise DRFValidationError(
                    f"'{campo}' inválido: {valor_campo!r} precisa ser enviado como TEXTO "
                    '(ex.: "100.00"), nunca como número JSON.'
                )
            valores_monetarios_opcionais[campo] = valor_campo

        # Competência da previdência oficial — mesmo formato de 'data'
        # (AAAA-MM-DD), sempre o primeiro dia do mês (checado no modelo).
        competencia_bruta = dados.get("competencia_previdencia")
        competencia_previdencia = None
        if competencia_bruta is not None:
            try:
                competencia_previdencia = para_data(competencia_bruta)
            except DataInvalida as exc:
                raise DRFValidationError(f"'competencia_previdencia' inválida: {exc}") from exc

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
                valor_irrf=valores_monetarios_opcionais["valor_irrf"],
                competencia_previdencia=competencia_previdencia,
                multa_previdencia=valores_monetarios_opcionais["multa_previdencia"],
                juros_previdencia=valores_monetarios_opcionais["juros_previdencia"],
                criado_por=request.user,
                chave_idempotencia=chave_idempotencia,
                request=request,
            )
        except ChaveIdempotenciaConflitanteCaixa as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except MesCaixaEncerrado as exc:
            # DL-053: mês encerrado — o corpo é válido, o ESTADO do mês é que
            # recusa. 409 (não 400): o cliente não corrige o corpo, reabre o
            # mês ou lança em outro. Nada foi gravado (a trava roda antes do
            # INSERT, dentro da transação do serviço).
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
        except MesCaixaEncerrado as exc:
            # DL-053, critério 2: estornar lançamento de mês encerrado exige
            # reabrir o mês (RC-130) — 409, nada gravado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
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


# ---------------------------------------------------------------------------
# DL-053 — fechamento de mês do livro-caixa (RC-145, RC-146).


# RC-146 = RC-102: quem fecha e reabre é a MESMA lista da contabilidade
# (`apps.core.papeis_de_fechamento`), lida por `papel_pode_fechar_mes_caixa`
# — aqui só a adaptação para permissão do DRF, sem segunda lista de papéis.
class PodeFecharMesCaixa(BasePermission):
    message = "Papel sem permissão para encerrar ou reabrir mês do livro-caixa."

    def has_permission(self, request, view):
        return papel_pode_fechar_mes_caixa(getattr(request, "papel", None))


# Encerrar é rota de AÇÃO: o mês vem da URL, sem corpo — mesmo desenho do
# fechamento de competência. Reabrir tem dois campos: `motivo` (obrigatório) e
# `cascata` (DL-054, booleano opcional, padrão falso).
CONTRATO_POST_ENCERRAR_MES_CAIXA = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no encerramento de mês do livro-caixa",
)
CONTRATO_POST_REABRIR_MES_CAIXA = ContratoDeRequisicao(
    campos={"motivo", "cascata"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura de mês do livro-caixa",
)


def _validar_ano_mes_da_url(ano, mes):
    """Recusa (400) `ano`/`mes` fora da faixa das `CheckConstraint` de
    `FechamentoMesCaixa`. `<int:...>` no urlconf já recusou texto (404)."""
    if not (1 <= mes <= 12):
        raise DRFValidationError(f"'mes' inválido: {mes} — deve estar entre 1 e 12.")
    if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO} e {_ANO_MAXIMO}."
        )


def _mes_caixa_como_dict(mes):
    """Um mês no formato da API. Datas em ISO; ids dos usuários e nome para
    exibição. Mês sem registro vem como `aberto` com os demais campos nulos."""
    return {
        "ano": mes["ano"],
        "mes": mes["mes"],
        "estado": mes["estado"],
        "fechado_em": mes["fechado_em"].isoformat() if mes["fechado_em"] else None,
        "fechado_por": mes["fechado_por"],
        "fechado_por_nome": mes["fechado_por_nome"],
        "reaberto_em": mes["reaberto_em"].isoformat() if mes["reaberto_em"] else None,
        "reaberto_por": mes["reaberto_por"],
        "reaberto_por_nome": mes["reaberto_por_nome"],
        "motivo_reabertura": mes["motivo_reabertura"],
    }


def _mes_caixa_depois_da_transicao(empresa, ano, mes):
    """Estado do mês lido de novo do banco, no mesmo formato da consulta —
    a resposta de encerrar/reabrir é o que ficou gravado, não o objeto em
    memória."""
    return _mes_caixa_como_dict(estado_dos_meses_caixa(empresa=empresa, ano=ano)[mes - 1])


class MesesCaixaView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """`GET .../meses/?ano=AAAA` — estado dos 12 meses do ano para a empresa
    (`ano` opcional: padrão, o ano corrente). Mês sem registro é `aberto`.
    Só LEITURA; empresa de outro escritório é 404 (isolamento pelo mixin)."""

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        if request.query_params.get("ano"):
            ano = _extrair_ano_da_querystring(request)
        else:
            ano = timezone.localdate().year
        meses = estado_dos_meses_caixa(empresa=empresa, ano=ano)
        return Response(
            {"empresa": empresa.id, "ano": ano, "meses": [_mes_caixa_como_dict(m) for m in meses]},
            status=status.HTTP_200_OK,
        )


class EncerrarMesCaixaView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """`POST .../meses/<ano>/<mes>/encerrar/` — encerra o mês (DL-053,
    critério 3). Sem corpo. 200 com o estado do mês; 409 se já encerrado."""

    permission_classes = [TemEscritorioAtivo, PodeFecharMesCaixa]

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ENCERRAR_MES_CAIXA)
        empresa = self.get_empresa()
        _validar_ano_mes_da_url(ano, mes)
        try:
            encerrar_mes_caixa(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except FechamentoMesCaixaInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except FechamentoMesCaixaRecusado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            _mes_caixa_depois_da_transicao(empresa, ano, mes), status=status.HTTP_200_OK
        )


class ReabrirMesCaixaView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """`POST .../meses/<ano>/<mes>/reabrir/` — reabre o mês (DL-053, critérios
    3 e 4; cascata: DL-054, RC-148).

    Corpo: `{"motivo": "<texto, obrigatório>", "cascata": <bool, opcional,
    padrão false>}`. Só esses dois campos; qualquer outro é 400.

    - `cascata=false`: reabre só o mês. Se houver mês ENCERRADO depois dele no
      mesmo ano, responde 409 sem alterar nada, com `detail` (mensagem
      legível) e `meses_encerrados_posteriores` (`[{"ano": 2026, "mes": 2},
      ...]`, crescente) — a tela usa a lista para oferecer a cascata.
    - `cascata=true`: reabre o mês e TODOS os encerrados posteriores do ano,
      numa transação, com o mesmo motivo e um registro de trilha por mês.

    200: o estado do mês pedido (mesmo formato de `GET .../meses/`) mais
    `meses_reabertos`, lista desse mesmo formato com todos os meses reabertos
    pelo ato, em ordem crescente (um item na reabertura simples).
    400: corpo inválido (motivo vazio/longo/com caractere nulo/não texto,
    `cascata` que não seja booleano, campo desconhecido), `ano`/`mes` fora da
    faixa, empresa fora do modo livro-caixa. 403: papel sem permissão de
    fechar mês. 404: empresa de outro escritório. 409: o mês pedido não está
    encerrado; ou exige cascata (acima); ou a espera pelo lock estourou.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharMesCaixa]

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_REABRIR_MES_CAIXA)
        empresa = self.get_empresa()
        _validar_ano_mes_da_url(ano, mes)
        dados = request.data if isinstance(request.data, dict) else {}
        motivo = dados.get("motivo")
        if motivo is not None and not isinstance(motivo, str):
            raise DRFValidationError("O campo 'motivo' deve ser texto.")
        # `cascata` só aceita booleano JSON verdadeiro/falso: "true", 1 ou null
        # seriam uma reabertura em lote decidida por coerção — a cascata reabre
        # vários meses encerrados, então a intenção tem de ser inequívoca.
        cascata = dados.get("cascata", False)
        if not isinstance(cascata, bool):
            raise DRFValidationError("O campo 'cascata' deve ser verdadeiro ou falso.")
        reabrir = reabrir_mes_caixa_em_cascata if cascata else reabrir_mes_caixa
        try:
            resultado = reabrir(
                empresa=empresa,
                ano=ano,
                mes=mes,
                usuario=request.user,
                motivo=motivo,
                request=request,
            )
        except FechamentoMesCaixaInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except ReaberturaExigeCascata as exc:
            return Response(
                {
                    "detail": str(exc),
                    "meses_encerrados_posteriores": [{"ano": exc.ano, "mes": m} for m in exc.meses],
                },
                status=status.HTTP_409_CONFLICT,
            )
        except FechamentoMesCaixaRecusado as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        reabertos = resultado if isinstance(resultado, list) else [resultado]
        # Relido do banco, no formato da consulta: a resposta é o que ficou
        # gravado, não os objetos em memória.
        estado_do_ano = estado_dos_meses_caixa(empresa=empresa, ano=ano)
        corpo = _mes_caixa_como_dict(estado_do_ano[mes - 1])
        corpo["meses_reabertos"] = [
            _mes_caixa_como_dict(estado_do_ano[linha.mes - 1]) for linha in reabertos
        ]
        return Response(corpo, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# DL-046, fatia 2 — apuração mensal do carnê-leão (RC-131 a RC-134).


def _json_seguro(valor):
    """Converte `Decimal`/`date` para os tipos que o JSON do DRF aceita sem
    perder precisão — `Decimal` como TEXTO (nunca número JSON, DE-030),
    `date` em ISO — recursivamente sobre `dict`/`list`, para servir tanto o
    resultado de um mês quanto o de `apurar_carne_leao_anual` (lista de
    meses) sem duplicar a conversão em duas views."""
    if isinstance(valor, dict):
        return {chave: _json_seguro(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_seguro(item) for item in valor]
    if isinstance(valor, date):
        return valor.isoformat()
    # `Decimal` não é `int`/`float`/`str`/`bool`/`None` — cobre pelo `else`.
    if isinstance(valor, (int, float, bool, str)) or valor is None:
        return valor
    return str(valor)


# Querystring: mesmo raciocínio de `_validar_ano_mes` (apps.contabilidade.
# views) — dígitos ASCII estritos, nunca `\d` (R2-7/R3-6), antes de `int()`.
_PADRAO_ANO_MES_SIMPLES = re.compile(r"^[0-9]{1,4}$")
_MES_MINIMO, _MES_MAXIMO = 1, 12
_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999


def _extrair_ano_da_querystring(request):
    bruto = request.query_params.get("ano")
    if not bruto or not _PADRAO_ANO_MES_SIMPLES.fullmatch(bruto):
        raise DRFValidationError("Informe 'ano' (dígitos) na querystring.")
    ano = int(bruto)
    if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO} e {_ANO_MAXIMO}."
        )
    return ano


def _extrair_mes_da_querystring(request):
    bruto = request.query_params.get("mes")
    if not bruto or not _PADRAO_ANO_MES_SIMPLES.fullmatch(bruto):
        raise DRFValidationError("Informe 'mes' (dígitos, 1 a 12) na querystring.")
    mes = int(bruto)
    if not (_MES_MINIMO <= mes <= _MES_MAXIMO):
        raise DRFValidationError(
            f"'mes' inválido: {mes} — deve estar entre {_MES_MINIMO} e {_MES_MAXIMO}."
        )
    return mes


class CarneLeaoMensalView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """Demonstrativo mensal do carnê-leão — `?ano=AAAA&mes=M` (querystring).
    Só LEITURA: nunca grava resultado (RC-130) — recalculado sempre a
    partir dos lançamentos de caixa e das tabelas normativas vigentes."""

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano = _extrair_ano_da_querystring(request)
        mes = _extrair_mes_da_querystring(request)
        try:
            resultado = apurar_carne_leao_mensal(empresa=empresa, ano=ano, mes=mes)
        except TabelaCarneLeaoNaoConfigurada as exc:
            raise DRFValidationError(str(exc)) from exc
        return Response(_json_seguro(resultado), status=status.HTTP_200_OK)


class CarneLeaoAnualView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """Demonstrativo anual do carnê-leão — `?ano=AAAA` (querystring), os 12
    meses do ano-calendário. Mesmas garantias de `CarneLeaoMensalView`."""

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano = _extrair_ano_da_querystring(request)
        try:
            resultado = apurar_carne_leao_anual(empresa=empresa, ano=ano)
        except TabelaCarneLeaoNaoConfigurada as exc:
            raise DRFValidationError(str(exc)) from exc
        return Response(_json_seguro(resultado), status=status.HTTP_200_OK)


CONTRATO_POST_DEPENDENTES_CARNE_LEAO = ContratoDeRequisicao(
    campos={"quantidade", "competencia_inicio"},
    contexto="no registro de dependentes do carnê-leão",
)


class DependentesCarneLeaoListCreateView(
    EmpresaEscopadaLivroCaixaMixin, generics.ListCreateAPIView
):
    """`GET` lista as vigências de quantidade de dependentes da empresa;
    `POST` registra uma nova, a partir de um mês (HI-35)."""

    permission_classes = [TemEscritorioAtivo]
    serializer_class = DependentesCarneLeaoClienteSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturarLivroCaixa())
        else:
            permissions.append(PodeLerLivroCaixa())
        return permissions

    def get_queryset(self):
        return DependentesCarneLeaoCliente.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_DEPENDENTES_CARNE_LEAO)
        dados = request.data if isinstance(request.data, dict) else {}
        empresa = self.get_empresa()

        quantidade_bruta = dados.get("quantidade")
        if not isinstance(quantidade_bruta, int) or isinstance(quantidade_bruta, bool):
            raise DRFValidationError("O campo 'quantidade' deve ser um número inteiro (JSON).")
        if quantidade_bruta < 0:
            raise DRFValidationError("O campo 'quantidade' não pode ser negativo.")

        bruto_competencia = dados.get("competencia_inicio")
        if not isinstance(bruto_competencia, str):
            raise DRFValidationError("Informe 'competencia_inicio' no formato AAAA-MM-DD.")
        try:
            competencia_inicio = para_data(bruto_competencia)
        except DataInvalida as exc:
            raise DRFValidationError(f"'competencia_inicio' inválida: {exc}") from exc

        try:
            registro = registrar_dependentes_carne_leao(
                empresa=empresa,
                quantidade=quantidade_bruta,
                competencia_inicio=competencia_inicio,
                criado_por=request.user,
                request=request,
            )
        except MesCaixaEncerrado as exc:
            # RC-147: a alteração mudaria o carnê-leão de um mês encerrado —
            # 409, nada gravado; reabrir o mês é o caminho.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DependentesCarneLeaoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except RestricaoViolada as exc:
            raise DRFValidationError({"competencia_inicio": [str(exc)]}) from exc

        serializer = self.get_serializer(registro)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


CONTRATO_PATCH_DEPENDENTES_CARNE_LEAO = ContratoDeRequisicao(
    campos={"quantidade"},
    contexto="na retificação de dependentes do carnê-leão",
)


class DependentesCarneLeaoRetificarView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """DE-091 item 6 (M-6, correção da rodada 1 da auditoria da fatia 2):
    `PATCH` retifica a QUANTIDADE de um registro já existente — nunca um
    novo registro (a `UniqueConstraint` de `competencia_inicio` por empresa
    já recusaria isso), e sempre com trilha de auditoria ANTES/DEPOIS (ver
    `apps.livro_caixa.carne_leao.retificar_dependentes_carne_leao`)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarLivroCaixa]

    def patch(self, request, empresa_id, dependente_id):
        _recusar_dado_nao_contratado(request, CONTRATO_PATCH_DEPENDENTES_CARNE_LEAO)
        empresa = self.get_empresa()
        registro = get_object_or_404(DependentesCarneLeaoCliente, pk=dependente_id, empresa=empresa)

        dados = request.data if isinstance(request.data, dict) else {}
        quantidade_bruta = dados.get("quantidade")
        if not isinstance(quantidade_bruta, int) or isinstance(quantidade_bruta, bool):
            raise DRFValidationError("O campo 'quantidade' deve ser um número inteiro (JSON).")
        if quantidade_bruta < 0:
            raise DRFValidationError("O campo 'quantidade' não pode ser negativo.")

        try:
            registro = retificar_dependentes_carne_leao(
                registro,
                quantidade=quantidade_bruta,
                retificado_por=request.user,
                request=request,
            )
        except MesCaixaEncerrado as exc:
            # RC-147: idem registro — retificar alteraria mês encerrado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DependentesCarneLeaoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = DependentesCarneLeaoClienteSerializer(registro)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# DL-046, fatia 3 (RC-127) — arquivos de importação do Carnê-Leão Web.


def _extrair_periodo_arquivo_carne_leao(request):
    """`inicio`/`fim` da querystring — mesmo contrato de `LivroCaixaView`
    (AAAA-MM-DD). A ordenação e a checagem de ano-calendário único ficam no
    SERVIÇO (`gerar_arquivos_carne_leao`), para a mensagem de erro nunca
    divergir entre esta view e as duas de download, abaixo — as três
    chamam a mesma função."""
    bruto_inicio = request.query_params.get("inicio")
    bruto_fim = request.query_params.get("fim")
    if not bruto_inicio or not bruto_fim:
        raise DRFValidationError("Informe 'inicio' e 'fim' (formato AAAA-MM-DD) na querystring.")
    try:
        inicio = para_data(bruto_inicio)
    except DataInvalida as exc:
        raise DRFValidationError(f"'inicio' inválido: {exc}") from exc
    try:
        fim = para_data(bruto_fim)
    except DataInvalida as exc:
        raise DRFValidationError(f"'fim' inválido: {exc}") from exc
    return inicio, fim


def _pendencias_para_json(pendencias):
    return [
        {"lancamento_id": p.lancamento_id, "campo": p.campo, "motivo": p.motivo} for p in pendencias
    ]


class ArquivosCarneLeaoPendenciasView(EmpresaEscopadaLivroCaixaMixin, APIView):
    """`GET .../carne-leao/arquivos/pendencias/?inicio=...&fim=...` — só
    LEITURA (nunca grava nada): roda a MESMA geração que os dois downloads,
    abaixo, e devolve as pendências (se houver) ou a conferência (se não
    houver) — a tela decide se oferece os botões de download a partir desta
    resposta, sem precisar baixar o arquivo primeiro para descobrir se ele
    existe."""

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _extrair_periodo_arquivo_carne_leao(request)
        try:
            _, _, conferencia = gerar_arquivos_carne_leao(
                empresa=empresa, inicio=inicio, fim=fim, usuario=request.user, request=request
            )
        except PeriodoInvalidoParaArquivoCarneLeaoWeb as exc:
            raise DRFValidationError(str(exc)) from exc
        except GeracaoArquivoCarneLeaoBloqueada as exc:
            return Response(
                {"pendencias": _pendencias_para_json(exc.pendencias), "gerar_disponivel": False},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "pendencias": [],
                "gerar_disponivel": True,
                "conferencia": _json_seguro(conferencia),
            },
            status=status.HTTP_200_OK,
        )


def _nome_arquivo_carne_leao(prefixo, inicio, fim):
    return f"carne-leao-{prefixo}-{inicio:%Y-%m}-a-{fim:%Y-%m}.csv"


def _resposta_de_download_csv(conteudo, nome_arquivo):
    resposta = HttpResponse(conteudo, content_type="text/csv; charset=ISO-8859-1")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    return resposta


class _ArquivoCarneLeaoDownloadViewBase(EmpresaEscopadaLivroCaixaMixin, APIView):
    """Base comum aos dois downloads, abaixo — só o PREFIXO do nome do
    arquivo e qual dos dois `bytes` devolver mudam entre eles; o resto
    (autorização, extração do período, tratamento de pendência/período
    inválido) é idêntico, e fica aqui para não duplicar."""

    permission_classes = [TemEscritorioAtivo, PodeLerLivroCaixa]
    prefixo_do_nome = None  # definido nas subclasses

    def _bytes_do_arquivo(self, rendimentos_bytes, pagamentos_bytes):
        raise NotImplementedError

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _extrair_periodo_arquivo_carne_leao(request)
        try:
            rendimentos_bytes, pagamentos_bytes, conferencia = gerar_arquivos_carne_leao(
                empresa=empresa,
                inicio=inicio,
                fim=fim,
                usuario=request.user,
                request=request,
                # Os bytes VÃO para o cliente aqui: a trilha registra
                # "carne_leao_arquivo.gerado". A rota de pendências, que
                # chama a mesma geração só para conferir, fica com o padrão
                # "conferido" (achado 5 da rodada 1 da auditoria).
                para_download=True,
            )
        except PeriodoInvalidoParaArquivoCarneLeaoWeb as exc:
            raise DRFValidationError(str(exc)) from exc
        except GeracaoArquivoCarneLeaoBloqueada as exc:
            return Response(
                {"pendencias": _pendencias_para_json(exc.pendencias)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Achado 4 da rodada 1 da auditoria: sem movimento no período não há
        # arquivo a importar — a MESMA regra de estado vazio da tela. Antes,
        # um GET direto aqui devolvia CSV vazio com 200, contradizendo o que
        # a tela mostrava para o mesmo período.
        if conferencia_sem_movimento(conferencia):
            raise DRFValidationError(
                "Não há lançamentos neste período para exportar — o arquivo do "
                "Carnê-Leão Web só é gerado quando existe movimento a importar."
            )
        conteudo = self._bytes_do_arquivo(rendimentos_bytes, pagamentos_bytes)
        nome_arquivo = _nome_arquivo_carne_leao(self.prefixo_do_nome, inicio, fim)
        return _resposta_de_download_csv(conteudo, nome_arquivo)


class ArquivoCarneLeaoRendimentosDownloadView(_ArquivoCarneLeaoDownloadViewBase):
    """`GET .../carne-leao/arquivos/rendimentos/?inicio=...&fim=...` —
    download do CSV de rendimentos, nome neutro (sem CPF/CNPJ), pronto para
    importar no Carnê-Leão Web."""

    prefixo_do_nome = "rendimentos"

    def _bytes_do_arquivo(self, rendimentos_bytes, pagamentos_bytes):
        return rendimentos_bytes


class ArquivoCarneLeaoPagamentosDownloadView(_ArquivoCarneLeaoDownloadViewBase):
    """`GET .../carne-leao/arquivos/pagamentos/?inicio=...&fim=...` —
    download do CSV de pagamentos."""

    prefixo_do_nome = "pagamentos"

    def _bytes_do_arquivo(self, rendimentos_bytes, pagamentos_bytes):
        return pagamentos_bytes
