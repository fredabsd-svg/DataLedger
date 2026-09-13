import hashlib
from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.contabilidade.models import Conta, LancamentoContabil, TipoPartida
from apps.contabilidade.serializers import ContaSerializer, LancamentoContabilSerializer
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    LancamentoInvalido,
    apurar_balancete,
    apurar_razao,
    criar_lancamento,
    estornar_lancamento,
    listar_diario,
    localizar_lotes_desbalanceados,
)
from apps.core.dinheiro import PADRAO_VALOR_DECIMAL_SIMPLES
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido

# Mesmo limite do CharField `chave_idempotencia` (models.py). Validado aqui,
# na fronteira da API, para que um cabeçalho longo demais vire 400 (entrada
# do cliente) em vez de vazar como 500 do banco (`DataError: value too long
# for type character varying(255)` — achado A3 da auditoria).
TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA = 255

# Mesmo limite do CharField `historico` (LancamentoContabil.historico,
# max_length=300). Validado aqui pelo mesmo motivo do limite acima (BL-44 /
# achado N3): sem esta checagem, um histórico longo demais só falharia no
# INSERT do Postgres (`DataError: value too long for type character
# varying(300)`), vazando como 500 em vez de 400.
TAMANHO_MAXIMO_HISTORICO = 300

# Maior valor absoluto que cabe em `ItemLancamento.valor` (DecimalField
# max_digits=18, decimal_places=2): com 2 casas decimais fixas, a parte
# inteira suporta no máximo 18 - 2 = 16 dígitos, então qualquer valor cujo
# módulo alcance 10**16 já não cabe na coluna. Verificado aqui, na fronteira
# da API (BL-44 / achado N3), para que o excesso vire 400 (entrada do
# cliente) em vez de `DataError` do Postgres vazando como 500. Não cobre
# ESCALA (casas decimais) — essa é uma regra do domínio contábil, aplicada
# por `criar_lancamento` com sua própria mensagem, que informa o valor
# recebido e a escala aceita (DE-010) — duplicar a checagem aqui com uma
# mensagem genérica escondia a mensagem de domínio, mais útil ao contador.
LIMITE_MAGNITUDE_VALOR = Decimal(10) ** (18 - 2)


def _como_moeda(valor):
    """Formata um Decimal monetário como string com duas casas.

    SQLite (usado em desenvolvimento local) não preserva a escala de um
    DecimalField em agregações (`Sum`) como o PostgreSQL faz; sem esta
    normalização, um saldo exato como 1000.00 poderia virar "1000" só por
    causa do banco usado no ambiente, mascarando o valor real.
    """
    return str(Decimal(valor).quantize(Decimal("0.01")))


def _periodo_obrigatorio(request):
    """Extrai e valida `inicio`/`fim` da querystring das saídas com período.

    DE-016: o período passa a ser OBRIGATÓRIO no Diário, Razão e Balancete —
    quebra deliberada do contrato anterior. Ausente, malformado (formato
    diferente de AAAA-MM-DD) ou invertido (`inicio > fim`) sempre vira 400
    com mensagem útil, nunca 500 nem um período implícito (critério 2 do
    plano DL-015).
    """
    bruto_inicio = request.query_params.get("inicio")
    bruto_fim = request.query_params.get("fim")
    if not bruto_inicio or not bruto_fim:
        raise DRFValidationError("Informe 'inicio' e 'fim' (formato AAAA-MM-DD) na querystring.")

    try:
        inicio = date.fromisoformat(bruto_inicio)
    except ValueError as exc:
        raise DRFValidationError(
            f"'inicio' inválido: '{bruto_inicio}' não é uma data no formato AAAA-MM-DD."
        ) from exc
    try:
        fim = date.fromisoformat(bruto_fim)
    except ValueError as exc:
        raise DRFValidationError(
            f"'fim' inválido: '{bruto_fim}' não é uma data no formato AAAA-MM-DD."
        ) from exc

    if inicio > fim:
        raise DRFValidationError(
            f"'inicio' ({inicio.isoformat()}) não pode ser posterior a 'fim' ({fim.isoformat()})."
        )
    return inicio, fim


def _nivel_opcional(request):
    """Extrai e valida o parâmetro opcional `nivel` do Balancete.

    Ausente (ou vazio), devolve `None` — sem recorte de hierarquia. Presente
    e malformado (não inteiro, ou menor que 1) vira 400: a raiz do plano de
    contas é o nível 1, não existe nível zero ou negativo.
    """
    bruto = request.query_params.get("nivel")
    if not bruto:
        return None
    try:
        nivel = int(bruto)
    except ValueError as exc:
        raise DRFValidationError(f"'nivel' inválido: '{bruto}' não é um número inteiro.") from exc
    if nivel < 1:
        raise DRFValidationError("'nivel' deve ser maior ou igual a 1 (a raiz é o nível 1).")
    return nivel


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
        except (Conta.DoesNotExist, KeyError, TypeError, ValueError) as exc:
            # `ValueError` cobre `pk` textual não numérico (ex.: "abc", "1x"):
            # o backend do Postgres levanta `ValueError: Field 'id' expected
            # a number but got 'abc'` ao tentar comparar o filtro, e sem essa
            # captura o erro do cliente vazava como 500 (achado 1 da
            # auditoria de 2026-09-12) — mesma classe de defeito que esta
            # etapa existe para fechar.
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            valor_bruto = item["valor"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Valor inválido em um dos itens.") from exc

        texto_valor = str(valor_bruto)
        if not PADRAO_VALOR_DECIMAL_SIMPLES.fullmatch(texto_valor):
            # Mais estrito que o construtor `Decimal`, que aceita espaços em
            # volta, "_" como separador de dígitos (PEP 515) e notação
            # científica: "1_000" convertido em silêncio para 1000
            # reinterpreta o que o cliente digitou, e "  100.00  " aceito em
            # silêncio esconde um erro de origem (achado 7 da auditoria de
            # 2026-09-12) — um sistema contábil não pode reinterpretar a
            # entrada. Este mesmo padrão também recusa "NaN"/"Infinity"/
            # "-Infinity" (não são dígitos), substituindo a checagem
            # separada de `valor.is_finite()` que existia aqui antes (BL-44 /
            # achado N3): depois deste padrão, `Decimal(texto_valor)` NUNCA
            # levanta `InvalidOperation` nem produz um resultado não finito.
            raise DRFValidationError(
                f"Valor inválido em um dos itens: '{texto_valor}' precisa ser um "
                "número decimal simples (sinal opcional, dígitos, ponto decimal "
                "opcional) — sem espaços, separador de milhar ou notação científica."
            )
        valor = Decimal(texto_valor)

        if abs(valor) >= LIMITE_MAGNITUDE_VALOR:
            raise DRFValidationError(
                f"Valor {valor} é grande demais para um item de lançamento; o "
                f"módulo deve ser menor que {LIMITE_MAGNITUDE_VALOR}."
            )

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

        historico = dados.get("historico", "")
        if not isinstance(historico, str):
            # `len()` funciona para list/dict/etc. (devolveria uma contagem
            # sem sentido, nunca um erro) e explode com `TypeError` para
            # número ou `None` — em qualquer um dos dois casos o valor
            # seguiria para `criar_lancamento` e para o INSERT do Postgres
            # com um tipo que a coluna não aceita, virando 500 em vez de 400
            # (mesma classe de defeito do BL-44 / achado N3: tipo de entrada
            # inesperado não capturado na fronteira da API).
            raise DRFValidationError("O campo 'historico' deve ser texto.")
        if len(historico) > TAMANHO_MAXIMO_HISTORICO:
            # Sem esta checagem, o texto seguiria até o INSERT e o Postgres
            # rejeitaria com `DataError: value too long for type character
            # varying(300)` — 500 em vez de 400 (BL-44 / achado N3).
            raise DRFValidationError(
                f"O histórico não pode ter mais de {TAMANHO_MAXIMO_HISTORICO} caracteres."
            )

        try:
            data_lancamento = date.fromisoformat(dados["data"])
        except (KeyError, ValueError, TypeError) as exc:
            # `date.fromisoformat` também recusa ano fora da faixa suportada
            # por `datetime.date` (1-9999) com `ValueError` — por exemplo
            # "99999-01-01" ou "0000-01-01" — então uma data fora de faixa já
            # cai neste mesmo 400, sem precisar de checagem adicional (BL-44).
            # `TypeError` cobre 'data' que não seja string (número, lista,
            # null): `fromisoformat` exige `str` e levanta `TypeError`, não
            # `ValueError`, para qualquer outro tipo — sem capturá-lo aqui o
            # 400 vira 500 pela mesma classe de defeito do achado N3.
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
                historico=historico,
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


class DiarioView(EmpresaEscopadaMixin, APIView):
    """Diário: lançamentos da empresa no período, em ordem cronológica (BL-59, DL-015)."""

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _periodo_obrigatorio(request)

        lancamentos = []
        total_debito = Decimal("0")
        total_credito = Decimal("0")
        # `listar_diario` já faz prefetch de itens+conta em consultas de
        # tamanho constante; iterar `lancamento.itens.all()` aqui usa o
        # cache do prefetch, sem gerar uma consulta por lançamento (N+1).
        for lancamento in listar_diario(empresa=empresa, inicio=inicio, fim=fim):
            debito_lancamento = Decimal("0")
            credito_lancamento = Decimal("0")
            itens = []
            for item in lancamento.itens.all():
                if item.tipo == TipoPartida.DEBITO:
                    debito_lancamento += item.valor
                else:
                    credito_lancamento += item.valor
                itens.append(
                    {
                        "conta": item.conta.codigo,
                        "nome": item.conta.nome,
                        "tipo": item.tipo,
                        "valor": _como_moeda(item.valor),
                    }
                )
            total_debito += debito_lancamento
            total_credito += credito_lancamento
            lancamentos.append(
                {
                    "id": lancamento.id,
                    "data": lancamento.data.isoformat(),
                    "historico": lancamento.historico,
                    "total_debito": _como_moeda(debito_lancamento),
                    "total_credito": _como_moeda(credito_lancamento),
                    "itens": itens,
                }
            )

        return Response(
            {
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "lancamentos": lancamentos,
                "total_debito": _como_moeda(total_debito),
                "total_credito": _como_moeda(total_credito),
            }
        )


class RazaoView(EmpresaEscopadaMixin, APIView):
    """Razão de uma conta no período: saldo anterior, itens e saldo final (BL-60, DL-015)."""

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        inicio, fim = _periodo_obrigatorio(request)

        apuracao = apurar_razao(conta=conta, inicio=inicio, fim=fim)

        itens = [
            {
                "lancamento_id": linha["lancamento_id"],
                "data": linha["data"].isoformat(),
                "historico": linha["historico"],
                "tipo": linha["tipo"],
                # Decimal como string: o encoder JSON padrão do DRF
                # converte Decimal para float fora de um DecimalField de
                # serializer, o que quebraria a precisão decimal exigida
                # para valores monetários (AGENTS.md, seção 10).
                "valor": _como_moeda(linha["valor"]),
                "saldo": _como_moeda(linha["saldo"]),
            }
            for linha in apuracao["itens"]
        ]

        return Response(
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "saldo_anterior": _como_moeda(apuracao["saldo_anterior"]),
                "total_debito": _como_moeda(apuracao["total_debito"]),
                "total_credito": _como_moeda(apuracao["total_credito"]),
                "saldo_final": _como_moeda(apuracao["saldo_final"]),
                "itens": itens,
            }
        )


class BalanceteView(EmpresaEscopadaMixin, APIView):
    """Balancete de verificação da empresa no período, com 4 colunas por conta
    (saldo anterior, débitos, créditos, saldo final) — BL-61, DL-015."""

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _periodo_obrigatorio(request)
        nivel = _nivel_opcional(request)

        apuracao = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim, nivel=nivel)

        contas = [
            {
                "conta": linha["conta"],
                "nome": linha["nome"],
                "nivel": linha["nivel"],
                "analitica": linha["analitica"],
                "saldo_anterior": _como_moeda(linha["saldo_anterior"]),
                "debitos": _como_moeda(linha["debitos"]),
                "creditos": _como_moeda(linha["creditos"]),
                "saldo_final": _como_moeda(linha["saldo_final"]),
            }
            for linha in apuracao["contas"]
        ]

        return Response(
            {
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "contas": contas,
                "total_debitos": _como_moeda(apuracao["total_debitos"]),
                "total_creditos": _como_moeda(apuracao["total_creditos"]),
            }
        )


class ConferenciaLotesDesbalanceadosView(EmpresaEscopadaMixin, APIView):
    """Lotes (lançamentos) cuja soma de débitos difere da de créditos (BL-64, DL-015).

    Sem período: uma base torta é torta em qualquer recorte. Em operação
    normal isto não deveria existir — `criar_lancamento` impede a gravação
    de um lançamento desbalanceado; esta rota existe para achar o que foi
    gravado por outro caminho (ex.: acesso direto ao ORM).
    """

    permission_classes = [TemEscritorioAtivo]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()

        lotes = [
            {
                "id": lancamento.id,
                "data": lancamento.data.isoformat(),
                "historico": lancamento.historico,
                "total_debito": _como_moeda(lancamento.total_debito),
                "total_credito": _como_moeda(lancamento.total_credito),
                "diferenca": _como_moeda(lancamento.total_debito - lancamento.total_credito),
            }
            for lancamento in localizar_lotes_desbalanceados(empresa=empresa)
        ]

        return Response({"lotes": lotes})
