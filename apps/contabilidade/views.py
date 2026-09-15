import hashlib
import re
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoPartida
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.contabilidade.serializers import ContaSerializer, LancamentoContabilSerializer
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    HierarquiaInconsistente,
    LancamentoInvalido,
    apurar_balancete,
    apurar_razao,
    criar_lancamento,
    estornar_lancamento,
    listar_diario,
    localizar_contas_que_aceitam_lancamento_e_tem_subordinadas,
    localizar_contas_sinteticas_com_movimento,
    localizar_inconsistencias_de_hierarquia,
    localizar_lancamentos_com_data_fora_da_faixa,
    localizar_lotes_desbalanceados,
    movimento_fora_do_periodo,
)
from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.escolhas import EscolhaInvalida, para_escolha
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_campos_nao_contratados,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import RestricaoViolada, mensagens_de, restricao_como_400
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

# Formato ESTRITO aceito para `nivel` (achado 12): um ou mais dígitos ASCII
# (`[0-9]`, não `\d` — mesmo motivo do padrão de data acima, achado novo 11),
# sem sinal, sem espaço e sem "_" como separador. Verificado ANTES de
# `int()`, que aceita "1_0" (convertido para 10), " 2 " e "+2" sem avisar —
# mesma classe de reinterpretação silenciosa que a checagem acima evita para
# data. Também aceitaria QUALQUER dígito Unicode ("٢") se usássemos `\d`.
_PADRAO_NIVEL_SIMPLES = re.compile(r"^[0-9]+$")

# Teto superior para `nivel` (achado novo 11): nenhum plano de contas real
# chega a esta profundidade — é só para recusar um valor absurdo como
# "999999999999999999999999999999" (que o Python aceitaria como inteiro de
# precisão arbitrária sem erro nenhum) em vez de deixá-lo percorrer o
# cálculo de nível sem produzir efeito útil. Generoso o bastante para não
# incomodar nenhum plano de contas real (a hierarquia mais profunda do
# domínio contábil, no material de referência do projeto, tem poucos
# níveis — ver docs/projeto/mapa-funcional-contabil.md).
NIVEL_MAXIMO = 50

# Achado R5-6 da auditoria DL-017 rodada 5 (BL-145, minha parte — a
# política combinada com o especialista-frontend, que já aplica a mesma
# recusa na tela): campo desconhecido no corpo do POST de lançamento era
# aceito e IGNORADO em silêncio (`empresa`, `id`, `criado_por`,
# `estornado` no topo; `xpto` dentro de um item) — enquanto a tela já
# recusa (medido pelo auditor: `valor_total`/`estorno` → 400). É a MESMA
# classe do achado 5 (BL-116, "nenhum dado enviado numa requisição deixa
# de ser lido ou recusado"), só que pela superfície da API. O agravante
# concreto: quem manda `chave_idempotencia` NO CORPO (em vez do cabeçalho
# `Idempotency-Key`, o único contrato válido) não era avisado e recebia a
# DUPLICIDADE que a chave existe para impedir — `chave_idempotencia` no
# corpo é, por construção, um "campo desconhecido" e cai nesta mesma
# recusa, fechando o buraco sem precisar de um caso especial.
CAMPOS_PERMITIDOS_LANCAMENTO = frozenset({"data", "historico", "itens"})
CAMPOS_PERMITIDOS_ITEM = frozenset({"conta", "tipo", "valor"})

# BL-149 / achado R6-2 (rodada 6): a política dos cinco dicionários passou a
# morar em `apps.core.requisicao` e vale para as SETE superfícies de escrita,
# não só para o POST de lançamento. O que sobrava, medido pelo auditor, era
# tudo o que NÃO é o corpo: querystring num POST (201 com um par de partidas
# completo pendurado na URL, nem lido nem recusado), `request.FILES` e
# cabeçalho não contratado. Cada view abaixo declara o seu contrato; nenhuma
# reimplementa a subtração de conjuntos.
#
# `aceita_querystring=False` em todas: nenhuma rota de ESCRITA desta API tem
# contrato de querystring — o recorte de período é das rotas de LEITURA
# (`_periodo_obrigatorio`), que não passam por aqui.
#
# Cabeçalhos: a API de lançamento USA `Idempotency-Key` (BL-41), então ela
# não o declara como ignorado. As outras rotas de escrita NÃO têm contrato de
# idempotência nenhum, e quem manda a chave nelas precisa saber que ela não
# tem efeito — é o mesmo defeito da tela (R5-6), na direção oposta: lá o
# cabeçalho era ignorado, aqui ele seria ignorado em rotas que não o
# implementam.
CONTRATO_POST_CONTA = ContratoDeRequisicao(
    campos={"codigo", "nome", "tipo", "natureza", "conta_pai", "aceita_lancamento", "ativo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta",
)
CONTRATO_POST_LANCAMENTO = ContratoDeRequisicao(
    campos=CAMPOS_PERMITIDOS_LANCAMENTO,
    contexto="no lançamento",
)
# Estorno é rota de AÇÃO: o que estornar vem da URL, e o corpo não tem
# contrato nenhum. `campos=frozenset()` é "nenhum campo aceito" — diferente
# de não declarar, que seria "não julgo o corpo".
CONTRATO_POST_ESTORNO = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno",
)


def _recusar_dado_nao_contratado(request, contrato):
    """Aplica a política de `apps.core.requisicao` e traduz o veredito para o
    protocolo desta superfície (400 em JSON do DRF).

    A tradução é de UMA linha de propósito: o módulo julga e não sabe
    responder HTTP; esta função é a única ponte entre ele e o DRF nesta API.
    """
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _sem_campos_desconhecidos(dados, campos_permitidos, *, contexto):
    """Recusa (`DRFValidationError`, nomeando a chave) se `dados` for um
    `dict` com alguma chave fora de `campos_permitidos`.

    Delega o julgamento a `apps.core.requisicao.recusar_campos_nao_
    contratados` (BL-149) — a subtração de conjuntos e o texto da mensagem
    moram lá, num lugar só. Esta função continua existindo porque o corpo da
    API é ANINHADO: cada item da lista de partidas é um dicionário próprio,
    que o contrato do topo não alcança."""
    try:
        recusar_campos_nao_contratados(dados, campos_permitidos, contexto=contexto)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _como_moeda(valor):
    """Formata um Decimal monetário como string com duas casas.

    SQLite (usado em desenvolvimento local) não preserva a escala de um
    DecimalField em agregações (`Sum`) como o PostgreSQL faz; sem esta
    normalização, um saldo exato como 1000.00 poderia virar "1000" só por
    causa do banco usado no ambiente, mascarando o valor real.
    """
    return str(Decimal(valor).quantize(Decimal("0.01")))


def _aviso_de_movimento_fora_do_periodo(*, empresa, inicio, fim, conta=None):
    """Serializa `movimento_fora_do_periodo` para a resposta JSON (BL-151).

    Devolve `None` quando não há nada fora do período — a chave existe SEMPRE
    na resposta, com `null`, porque um cliente que só a veja quando há
    movimento não tem como distinguir "não há" de "esta versão do servidor
    não responde isso".

    Por que a API também recebe o aviso, e não só a tela (item 2 da DE-034):
    o fato invisível é invisível pela porta da API do mesmo jeito. Um cliente
    que pede o Diário de janeiro recebe um total que CONCILIA e nenhuma pista
    de que existe um lançamento de 5.000,00 em `9999-12-31` — foi exatamente
    isso que o auditor mediu, e fechar só na tela repetiria o vício que o
    R6-2 nomeou.

    As datas saem em `isoformat()` (AAAA-MM-DD), como todas as outras datas
    desta API — nunca `date` cru, que o encoder JSON do DRF converteria por
    conta própria.
    """
    fora = movimento_fora_do_periodo(empresa=empresa, inicio=inicio, fim=fim, conta=conta)
    if fora is None:
        return None

    def _lado(dados):
        if dados is None:
            return None
        return {
            "quantidade": dados["quantidade"],
            "data_extrema": dados["data_extrema"].isoformat(),
        }

    return {"anteriores": _lado(fora["anteriores"]), "posteriores": _lado(fora["posteriores"])}


def _saldo_absoluto_com_natureza(saldo_assinado, natureza_cadastrada):
    """Converte um saldo ASSINADO (a convenção interna de `services.py`:
    positivo quando o saldo está do mesmo lado da natureza CADASTRADA da
    conta — ver `_saldo_por_natureza`/`_sinal_do_item`) para o par que a
    apresentação contábil exige (RC-61 / BL-77, critério 5 do plano
    DL-017): `(valor_absoluto: Decimal, letra: "D" | "C" | None)`. O valor
    NUNCA é negativo — quem consome (a resposta HTTP hoje, a tela na fase B)
    mostra a letra ao lado do número, nunca o sinal.

    A natureza APURADA (a letra devolvida aqui) não é a mesma coisa que a
    natureza CADASTRADA da conta (`Conta.natureza`, o parâmetro
    `natureza_cadastrada`): uma conta DEVEDORA cujo movimento do período
    pesa mais para o crédito apura saldo CREDOR — mesmo continuando
    cadastrada como devedora. É o coração do caso de referência do Fred
    (docs/projeto/mapa-funcional-contabil.md, "Conta retificadora,
    apresentação de saldo e implantação"): a conta retificadora de
    depreciação é cadastrada com natureza CONTRÁRIA à do grupo de
    propósito, e o GRUPO (que tem natureza própria, devedora) apura saldo
    devedor mesmo absorvendo o crédito da retificadora — a natureza apurada
    do grupo vem do SINAL do resultado, nunca copiada de um filho.
    A mesma lógica vale para uma conta isolada, sem filhos: se o crédito do
    período supera o débito de uma conta cadastrada devedora, ela apura
    saldo credor, ponto.

    Saldo exatamente ZERO não tem lado — não existe "meio D, meio C" nem um
    lado mais correto que o outro para apresentar. Decisão explícita deste
    módulo (não há regra contábil que escolha um lado para zero): devolve
    `letra=None`. Quem for renderizar (a fase B) não deve mostrar indicador
    nenhum quando `letra` vier `None` — mostrar "D" ou "C" para saldo zero
    seria inventar uma informação que os dados não sustentam.
    """
    if saldo_assinado == 0:
        return saldo_assinado, None

    letra_cadastrada = "D" if natureza_cadastrada == NaturezaConta.DEVEDORA else "C"
    if saldo_assinado > 0:
        return saldo_assinado, letra_cadastrada

    # Negativo, na convenção assinada dos serviços: o saldo apurado está do
    # lado CONTRÁRIO ao cadastrado. Inverte o sinal (nunca devolve negativo)
    # e a letra.
    letra_apurada = "C" if letra_cadastrada == "D" else "D"
    return -saldo_assinado, letra_apurada


def _periodo_obrigatorio(request):
    """Extrai e valida `inicio`/`fim` da querystring das saídas com período.

    DE-016: o período passa a ser OBRIGATÓRIO no Diário, Razão e Balancete —
    quebra deliberada do contrato anterior. Ausente, malformado (formato
    diferente de AAAA-MM-DD) ou invertido (`inicio > fim`) sempre vira 400
    com mensagem útil, nunca 500 nem um período implícito (critério 2 do
    plano DL-015).

    A conversão em si é delegada a `apps.core.datas.para_data` (BL-133,
    achado A9 da auditoria DL-017 rodada 4 / DE-030 estendida a dado
    tipado): antes, este módulo tinha seu PRÓPRIO `_PADRAO_DATA_SIMPLES` e
    sua própria chamada a `date.fromisoformat`, e `apps.empresas.views`
    não tinha proteção nenhuma — duas cópias da mesma regra (uma delas
    frouxa) é exatamente o que a DE-026 existe para impedir.
    """
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
    if not _PADRAO_NIVEL_SIMPLES.fullmatch(bruto):
        # Recusa ANTES de `int()` (achado 12): "1_0" seria interpretado como
        # 10 (separador de dígitos do Python, PEP 515), e " 2 "/"+2" seriam
        # aceitos em silêncio — reinterpretação que o contrato não promete.
        raise DRFValidationError(f"'nivel' inválido: '{bruto}' não é um número inteiro.")
    try:
        nivel = int(bruto)
    except ValueError as exc:
        raise DRFValidationError(f"'nivel' inválido: '{bruto}' não é um número inteiro.") from exc
    if nivel < 1 or nivel > NIVEL_MAXIMO:
        # achado novo 11: limite SUPERIOR explícito, além do mínimo já
        # existente — sem ele, um valor absurdo como
        # "999999999999999999999999999999" (inteiro Python válido, sem
        # limite de tamanho) seria aceito sem recusa nenhuma.
        raise DRFValidationError(
            f"'nivel' deve ser um número inteiro entre 1 e {NIVEL_MAXIMO} "
            "(a raiz do plano de contas é o nível 1)."
        )
    return nivel


# Consulta é liberada a qualquer papel vinculado ao escritório ativo;
# lançar/editar o plano de contas ou a escrituração é restrito a quem
# efetivamente cuida da contabilidade do escritório.
PodeEscriturar = papel_permitido(
    Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO
)


# Leitura das quatro saídas contábeis com período (Diário, Razão, Balancete,
# conferência) — e, desde o achado novo 2 da rodada 2, TAMBÉM o `GET` de
# `ContaListCreateView` (plano de contas) e de `LancamentoListCreateView`
# (Diário "crú", sem período): DE-020 §4, corrigida. Decisão imediata e
# conservadora do arquiteto-senior: o papel CLIENTE deixa de ler a
# contabilidade — antes, qualquer usuário com vínculo de papel CLIENTE no
# escritório lia o Diário (com histórico), o Razão e o Balancete completos
# de TODOS os outros clientes do mesmo escritório, o que é sigilo de
# cliente contra cliente, não apenas permissão fina.
#
# A DE-020 §4 original listava só as QUATRO rotas criadas por esta etapa
# (Diário, Razão, Balancete, conferência) — e ficou pela metade: o CLIENTE
# continuava lendo a MESMA escrituração completa por `GET .../lancamentos/`
# (sem período, com histórico e partidas) e o plano de contas por
# `GET .../contas/`. O critério correto, daqui em diante: NENHUMA rota
# devolve escrituração, plano de contas ou saldo a quem não pode ler
# contabilidade — independentemente de quando a rota foi criada. As rotas de
# ESCRITURAÇÃO (POST das duas views abaixo) continuam usando `PodeEscriturar`,
# sem mudança — só a LEITURA passou a exigir este papel.
#
# Os demais papéis vinculados ao escritório seguem lendo, até uma matriz fina
# por módulo (PE-36).
#
# DE-026 / DL-017 fase A, critério 1: esta classe NÃO decide mais nada
# sozinha — ela só traduz `apps.contabilidade.permissoes.
# papel_pode_ler_contabilidade` (a fonte única da regra, sem depender de
# DRF) para o protocolo de permissão do DRF. A tela (fase B) vai chamar a
# MESMA função diretamente, sem passar pelo DRF. Ver o docstring de
# `permissoes.py` para o contrato completo, e
# `tests/test_permissoes_contabilidade.py` para o teste que prova que os
# dois lados decidem igual.
class PodeLerContabilidade(BasePermission):
    message = "Papel sem permissão para ler a contabilidade."

    def has_permission(self, request, view):
        return papel_pode_ler_contabilidade(getattr(request, "papel", None))


class ContaListCreateView(EmpresaEscopadaMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = ContaSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        else:
            # achado novo 2: leitura do plano de contas segue a MESMA regra
            # das outras saídas contábeis — o papel CLIENTE não lê.
            permissions.append(PodeLerContabilidade())
        return permissions

    def get_queryset(self):
        return Conta.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        # BL-149: a política dos cinco dicionários ANTES de qualquer
        # gravação. Medido pelo auditor nesta rota: querystring em POST,
        # `empresa: 999`, `xpto` e `id: 4242` no corpo → **201 em todos**,
        # ignorados em silêncio. `id` é especialmente ruim: quem o envia
        # acredita ter escolhido o identificador do registro.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_CONTA)
        return super().post(request, *args, **kwargs)

    def get_serializer_context(self):
        # A empresa do contexto vem do escopo da URL, já revalidada contra o
        # escritório ativo (EmpresaEscopadaMixin.get_empresa()) — nunca de um
        # campo enviado pelo cliente. É o que permite ao serializer recusar
        # `conta_pai` de outra empresa (BL-40) sem confiar no payload.
        context = super().get_serializer_context()
        context["empresa"] = self.get_empresa()
        return context

    def perform_create(self, serializer):
        # `restricao_como_400` (achado R5-5 da auditoria DL-017 rodada 5,
        # BL-144 / DE-034): antes, esta view não tinha `try` nenhum —
        # `codigo` repetido na mesma empresa (`Conta.Meta.constraints`,
        # `codigo_unico_por_empresa`) derrubava com `IntegrityError` cru,
        # 500. Medido sob concorrência (4 POSTs simultâneos com o mesmo
        # código): `500, 201, 500, 500` — a integridade do dado nunca foi
        # violada (a constraint segurou), só a RESPOSTA quebrava. O
        # `transaction.atomic()` isola o `IntegrityError` num savepoint,
        # para a conexão continuar utilizável para o `registrar()` abaixo
        # (mesmo desenho de `erro_de_cnpj_duplicado_como_400`, em
        # `apps.empresas.services`, que já faz isto para CNPJ).
        try:
            # A mensagem vem do registro único `apps.core.restricoes.
            # MENSAGENS_DE_RESTRICAO` (BL-157): antes era um literal aqui, e
            # literal espalhado por view é exatamente como as duas
            # `CheckConstraint` de CNPJ ficaram sem tradução — não havia lugar
            # nenhum onde alguém pudesse ver a lista inteira e notar a falta.
            with (
                transaction.atomic(),
                restricao_como_400(mensagens_de("codigo_unico_por_empresa")),
            ):
                conta = serializer.save(empresa=self.get_empresa())
        except RestricaoViolada as exc:
            raise DRFValidationError({"codigo": [str(exc)]}) from exc
        registrar(acao="conta.criada", objeto=conta, request=self.request)


def _extrair_itens(payload_itens, empresa):
    """Valida e converte os itens recebidos da API em dados prontos para o serviço."""
    if not isinstance(payload_itens, list) or len(payload_itens) < 2:
        raise DRFValidationError("Informe ao menos duas partidas (itens).")

    itens = []
    for item in payload_itens:
        _sem_campos_desconhecidos(item, CAMPOS_PERMITIDOS_ITEM, contexto="em um item")

        try:
            conta_bruta = item["conta"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            # `para_id` (achado R5-3 da auditoria DL-017 rodada 5, BL-142 /
            # DE-034): antes, `item["conta"]` ia direto para `.get(pk=...)`,
            # protegido só pelo `except (..., TypeError, ValueError)`
            # abaixo — o que barra texto não numérico, mas NÃO barra
            # reinterpretação silenciosa: `1.9` (número JSON) gravava na
            # conta 1 (Postgres/psycopg truncam o float ao comparar com a
            # coluna inteira), `true` gravava na conta 1 (`bool` é `int` em
            # Python), `" 1 "`/`"+1"` gravavam na conta 1, e `"٢"`/`"２"`
            # (dígito Unicode) gravavam na conta 2 — sempre HTTP 201, sem
            # aviso. É a MESMA classe que a tela e `apps.tenancy` já
            # fecham com `para_id` — só a API de contabilidade não usava
            # (dois comentários de `views_web.py` afirmavam que usava; não
            # usava — ver a correção desses comentários, pedida ao
            # `especialista-frontend`).
            conta_id = para_id(conta_bruta)
        except IdentificadorInvalido as exc:
            raise DRFValidationError(f"Conta inválida para esta empresa: {exc}") from exc

        try:
            conta = Conta.objects.get(pk=conta_id, empresa=empresa)
        except Conta.DoesNotExist as exc:
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            valor_bruto = item["valor"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Valor inválido em um dos itens.") from exc

        # DE-030 (achado R3-3, auditoria DL-017 rodada 3): esta view NÃO
        # constrói `Decimal` por conta própria — entrega TEXTO a
        # `apps.core.dinheiro.para_decimal`, o único julgador de formato
        # monetário do sistema (mesmo módulo que a tela usa, DE-027/DE-029).
        # Antes desta correção, o código fazia `str(valor_bruto)` e depois
        # `Decimal(texto)`: um `valor` enviado como NÚMERO JSON (não texto)
        # virava `float` de precisão binária ao ser decodificado pelo
        # parser de JSON, ANTES de qualquer checagem — e para magnitudes
        # grandes (medido: acima de ~7×10¹³) o `float` já tinha perdido a
        # última casa decimal. `str()` desse float reproduzia o valor JÁ
        # CORROMPIDO, não o texto que o cliente pretendia enviar, e a
        # recusa de notação científica que este arquivo anuncia era
        # contornada simplesmente trocando aspas por número (`1e3` como
        # texto: 400; `1e3` como número JSON: aceito, virava 1000,00). Por
        # isso `valor` que não chegue como `str` é recusado AQUI, antes de
        # qualquer conversão — nunca convertido para texto e reinterpretado.
        if not isinstance(valor_bruto, str):
            raise DRFValidationError(
                f"Valor inválido em um dos itens: {valor_bruto!r} precisa ser "
                'enviado como TEXTO (ex.: "100.00"), nunca como número JSON — '
                "um número perde precisão ao ser decodificado pelo parser JSON, "
                "antes mesmo de chegar a este servidor."
            )
        try:
            valor = para_decimal(valor_bruto)
        except ValorMonetarioInvalido as exc:
            # `para_decimal` já recusa: formato fora do decimal simples
            # (sinal opcional, dígitos, ponto decimal opcional — sem
            # espaços, "_" como separador de dígitos ou notação científica,
            # achado 7 da auditoria de 2026-09-12) e valor não finito
            # (`NaN`/`Infinity`/`-Infinity`, achado BL-44/N3). A mensagem do
            # próprio módulo monetário já é específica; só acrescenta o
            # contexto de que é um item do lote.
            raise DRFValidationError(f"Valor inválido em um dos itens: {exc}") from exc

        if abs(valor) >= LIMITE_MAGNITUDE_VALOR:
            raise DRFValidationError(
                f"Valor {valor} é grande demais para um item de lançamento; o "
                f"módulo deve ser menor que {LIMITE_MAGNITUDE_VALOR}."
            )

        try:
            # `para_escolha` (achado R5-2, BL-141 / DE-034): esta checagem
            # já era segura por acidente de forma (pertencimento a uma
            # lista fechada nunca levanta exceção, seja qual for o tipo do
            # valor testado) — mas era uma segunda cópia manual do mesmo
            # padrão que `regime`, em `apps.empresas.views`, não tinha.
            # Migrada para o módulo compartilhado para não deixar um
            # terceiro campo de `choices` reinventar a checagem por conta
            # própria no futuro.
            tipo = para_escolha(item.get("tipo"), TipoPartida.values, nome_campo="tipo")
        except EscolhaInvalida as exc:
            raise DRFValidationError(str(exc)) from exc

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
        else:
            # achado novo 2: esta rota devolvia a escrituração completa
            # (histórico, valores, partidas) a qualquer papel vinculado ao
            # escritório, inclusive CLIENTE — era o "caminho fácil" que
            # continuava aberto depois da DE-020 §4 original, porque a
            # decisão citava só as quatro rotas novas (Diário, Razão,
            # Balancete, conferência) e não esta, que já existia antes.
            permissions.append(PodeLerContabilidade())
        return permissions

    def get_queryset(self):
        return LancamentoContabil.objects.filter(empresa=self.get_empresa()).prefetch_related(
            "itens__conta"
        )

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        dados = request.data
        # BL-149: o corpo já era julgado aqui (R5-6/BL-145); o que faltava
        # eram os OUTROS dicionários da mesma requisição — o auditor mediu
        # `POST .../lancamentos/?conta_3=…&xpto=1` devolvendo **201**, com o
        # par de partidas da querystring nem lido nem recusado. A política
        # inteira agora vem de um lugar só (`apps.core.requisicao`), com o
        # MESMO contrato de campos de antes.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_LANCAMENTO)
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
            data_bruta = dados["data"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Informe 'data' no formato AAAA-MM-DD.") from exc
        try:
            # `para_data` (achado A9 da auditoria DL-017 rodada 4, BL-133):
            # antes, este trecho chamava `date.fromisoformat` direto, sem a
            # gramática estrita que `_periodo_obrigatorio` já aplicava a
            # `inicio`/`fim` — o mesmo módulo tinha a defesa certa num lugar
            # e não noutro. Sem ela, uma data de semana ISO
            # ("2026-W01-1") era aceita e REINTERPRETADA em silêncio para
            # outro ano/mês/dia (medido: grava "2025-12-29" para quem
            # digitou "2026-W01-1") — corrupção silenciosa da DATA de um
            # lançamento contábil, pior que o 500 que o `except` antigo já
            # evitava para tipo errado (`TypeError`, número JSON etc., que
            # `para_data` também recusa, com `DataInvalida`, não mais
            # deixando vazar cru).
            data_lancamento = para_data(data_bruta)
        except DataInvalida as exc:
            raise DRFValidationError(f"'data' inválida: {exc}") from exc

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
        # BL-149: rota de ação, e mesmo assim entra na política — um corpo
        # com `data` ou `historico` aqui sugere ao cliente que ele está
        # escolhendo a data do estorno, e ela é decidida pelo servidor
        # (RC-78). Aceitar e ignorar seria a mesma classe de defeito de
        # sempre, com consequência contábil: o cliente acreditaria ter
        # datado o estorno.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNO)
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

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

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
                # BL-151: o Diário do período pode conciliar perfeitamente e
                # ainda assim haver escrituração fora dele. Ver
                # `_aviso_de_movimento_fora_do_periodo`.
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim
                ),
            }
        )


class RazaoView(EmpresaEscopadaMixin, APIView):
    """Razão de uma conta no período: saldo anterior, itens e saldo final (BL-60, DL-015).

    Consolidação (achado 8 / DE-020, corrigida pela DE-022): o extrato
    CONSOLIDA sempre que a conta TIVER DESCENDENTES — a resposta declara
    `"analitica": false` e `"consolidado": true` para que quem lê saiba que
    está vendo o grupo, não uma conta com movimento próprio. `"analitica"`
    é sempre o NEGATIVO de `"consolidado"` (as duas descrevem a mesma
    pergunta — "esta conta tem descendentes?" — só que em polaridades
    opostas): antes da correção do achado novo 1, este campo vinha de
    `conta.aceita_lancamento`, um critério DIFERENTE do que decidia a
    consolidação, e uma conta que aceita lançamento e tem filhas aparecia
    marcada `"analitica": true` com o Razão zerado, enquanto o Balancete da
    MESMA conta trazia o total consolidado.

    Saldo com natureza (RC-61 / BL-77, critério 5 do plano DL-017):
    `saldo_anterior`, `saldo_final` e a coluna `saldo` de cada item de
    `itens` NUNCA vêm negativos — são o valor ABSOLUTO, acompanhados do
    campo irmão `<campo>_natureza` ("D", "C" ou `None` para saldo zero — ver
    `_saldo_absoluto_com_natureza`). A natureza aplicada é sempre a da
    CONTA CONSULTADA (`conta`, inclusive quando consolidado — o grupo), a
    mesma que já decide o sinal interno em `apurar_razao`/`_sinal_do_item`;
    nunca a de uma conta descendente.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        inicio, fim = _periodo_obrigatorio(request)

        try:
            apuracao = apurar_razao(conta=conta, empresa=empresa, inicio=inicio, fim=fim)
        except HierarquiaInconsistente as exc:
            # Ciclo ou conta_pai de outra empresa na hierarquia (achado 6):
            # resposta controlada, nomeando a conta, nunca um 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        itens = []
        for linha in apuracao["itens"]:
            # RC-61 / BL-77: a coluna "saldo" de cada linha do Razão também
            # vira valor absoluto + natureza apurada — sempre pela natureza
            # da conta CONSULTADA (`conta`), nunca a do item individual (ver
            # docstring da classe e de `apurar_razao`).
            saldo_abs, saldo_natureza = _saldo_absoluto_com_natureza(linha["saldo"], conta.natureza)
            itens.append(
                {
                    "lancamento_id": linha["lancamento_id"],
                    "data": linha["data"].isoformat(),
                    "historico": linha["historico"],
                    "conta": linha["conta"],
                    "nome": linha["conta_nome"],
                    "tipo": linha["tipo"],
                    # Decimal como string: o encoder JSON padrão do DRF
                    # converte Decimal para float fora de um DecimalField de
                    # serializer, o que quebraria a precisão decimal exigida
                    # para valores monetários (AGENTS.md, seção 10).
                    "valor": _como_moeda(linha["valor"]),
                    "saldo": _como_moeda(saldo_abs),
                    "saldo_natureza": saldo_natureza,
                }
            )

        saldo_anterior_abs, saldo_anterior_natureza = _saldo_absoluto_com_natureza(
            apuracao["saldo_anterior"], conta.natureza
        )
        saldo_final_abs, saldo_final_natureza = _saldo_absoluto_com_natureza(
            apuracao["saldo_final"], conta.natureza
        )

        return Response(
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                # DE-022 (achado novo 1): "analitica" é o NEGATIVO de
                # "consolidado" — o mesmo critério ("tem descendentes?"),
                # nunca mais `conta.aceita_lancamento`. Ver docstring da
                # classe.
                "analitica": not apuracao["consolidado"],
                "consolidado": apuracao["consolidado"],
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "saldo_anterior": _como_moeda(saldo_anterior_abs),
                "saldo_anterior_natureza": saldo_anterior_natureza,
                "total_debito": _como_moeda(apuracao["total_debito"]),
                "total_credito": _como_moeda(apuracao["total_credito"]),
                "saldo_final": _como_moeda(saldo_final_abs),
                "saldo_final_natureza": saldo_final_natureza,
                "itens": itens,
                # BL-151, recortado pela CONTA consultada (e pelas
                # descendentes, o mesmo conjunto que `apurar_razao` usa): o
                # aviso do Razão fala da conta que está na tela, não da
                # empresa inteira.
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim, conta=conta
                ),
            }
        )


class BalanceteView(EmpresaEscopadaMixin, APIView):
    """Balancete de verificação da empresa no período, com 4 colunas por conta
    (saldo anterior, débitos, créditos, saldo final) — BL-61, DL-015.

    Saldo com natureza (RC-61 / BL-77, critério 5 do plano DL-017):
    `saldo_anterior` e `saldo_final`, em cada linha, NUNCA vêm negativos —
    são o valor ABSOLUTO, acompanhados do campo irmão `<campo>_natureza`
    ("D", "C" ou `None` para saldo zero — ver `_saldo_absoluto_com_natureza`
    em `views.py`). A natureza é a APURADA daquela linha, não a CADASTRADA
    da conta (`linha["natureza"]`, que `apurar_balancete` devolve só para
    esta conversão): o caso de referência é o grupo Imobilizado do Fred
    (docs/projeto/mapa-funcional-contabil.md) — devedor, cadastrado como
    tal — que segue apurando saldo DEVEDOR mesmo absorvendo o crédito da
    retificadora (natureza cadastrada oposta) entre suas descendentes.
    `debitos`/`creditos`/`debitos_proprios`/`creditos_proprios` continuam
    como somas BRUTAS (sempre ≥ 0 por construção): não precisam de
    indicador de natureza, só o saldo tem lado.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _periodo_obrigatorio(request)
        nivel = _nivel_opcional(request)

        try:
            apuracao = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim, nivel=nivel)
        except HierarquiaInconsistente as exc:
            # Ciclo ou conta_pai de outra empresa na hierarquia (achado 6):
            # resposta controlada, nomeando a conta, nunca um 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        contas = []
        for linha in apuracao["contas"]:
            # RC-61 / BL-77: `linha["natureza"]` é a natureza CADASTRADA da
            # conta (adicionada por `apurar_balancete` só para esta
            # conversão) — a natureza APURADA de cada saldo é derivada do
            # SINAL do valor assinado, não copiada dela. Ver docstring da
            # classe e de `_saldo_absoluto_com_natureza`.
            saldo_anterior_abs, saldo_anterior_natureza = _saldo_absoluto_com_natureza(
                linha["saldo_anterior"], linha["natureza"]
            )
            saldo_final_abs, saldo_final_natureza = _saldo_absoluto_com_natureza(
                linha["saldo_final"], linha["natureza"]
            )
            contas.append(
                {
                    "conta": linha["conta"],
                    "nome": linha["nome"],
                    "nivel": linha["nivel"],
                    "analitica": linha["analitica"],
                    "saldo_anterior": _como_moeda(saldo_anterior_abs),
                    "saldo_anterior_natureza": saldo_anterior_natureza,
                    "debitos": _como_moeda(linha["debitos"]),
                    "creditos": _como_moeda(linha["creditos"]),
                    # Achado novo 3 / DE-024 §2: movimento PRÓPRIO da conta (o
                    # que foi lançado DIRETO nela, sem o das descendentes) — é
                    # sobre estes dois campos, não sobre "debitos"/"creditos"
                    # (consolidados), que a soma das linhas reconcilia com
                    # total_debitos/total_creditos abaixo. Sempre ≥ 0: não
                    # levam indicador de natureza (ver docstring da classe).
                    "debitos_proprios": _como_moeda(linha["debitos_proprios"]),
                    "creditos_proprios": _como_moeda(linha["creditos_proprios"]),
                    "saldo_final": _como_moeda(saldo_final_abs),
                    "saldo_final_natureza": saldo_final_natureza,
                }
            )

        return Response(
            {
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "contas": contas,
                "total_debitos": _como_moeda(apuracao["total_debitos"]),
                "total_creditos": _como_moeda(apuracao["total_creditos"]),
                # BL-151: é no Balancete que a invisibilidade dói mais, porque
                # ele é a saída que o contador usa para CONCILIAR — e ele
                # concilia, com o valor de fora do período ausente dos dois
                # lados. Ver `_aviso_de_movimento_fora_do_periodo`.
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim
                ),
            }
        )


class ConferenciaLotesDesbalanceadosView(EmpresaEscopadaMixin, APIView):
    """Conferência de inconsistências da base contábil da empresa (BL-64, DL-015).

    Sem período: uma base torta é torta em qualquer recorte. Em operação
    normal nada disto deveria existir — `criar_lancamento` impede a
    gravação de um lançamento desbalanceado, e `Conta.clean()` impede a
    reclassificação de uma conta com movimento e o ciclo na hierarquia
    (achados 2 e 6); esta rota existe para achar o que foi gravado ou
    alterado por outro caminho (ex.: acesso direto ao ORM).

    Quatro categorias, cada uma reportada mesmo que as outras estejam vazias:

    - `lotes`: lançamentos com menos de duas partidas — `motivo`
      "sem_partidas" (zero itens) ou "partida_unica" (exatamente um item) —
      ou com débito diferente de crédito (`motivo` "desbalanceado") —
      achado 9, rótulo de três vias corrigido pelo achado novo 12 (antes,
      um lote com UMA partida de 5,00 aparecia como "sem_partidas" na MESMA
      linha em que o total mostrava 5,00 — a própria ferramenta de
      diagnóstico se contradizia).
    - `contas_sinteticas_com_movimento`: contas marcadas como sintéticas que
      já têm itens de lançamento próprios — achado 2.
    - `contas_que_aceitam_lancamento_e_tem_subordinadas`: quarta categoria
      (DE-022, achado novo 1) — conta que aceita lançamento direto E tem
      contas subordinadas. NÃO é erro nem é bloqueado (a DE-022 explica por
      quê); é só para o contador enxergar o caso.
    - `hierarquia_inconsistente`: mensagens descrevendo ciclo ou
      `conta_pai` de outra empresa no plano de contas — achado 6, agora
      acumulando TODAS as inconsistências encontradas, não só a primeira
      (achado novo 13).
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()

        def _motivo(lancamento):
            # Achado novo 12: três motivos, não dois — "sem_partidas" (zero
            # itens) e "partida_unica" (um item) são casos DIFERENTES de
            # "desbalanceado" (duas ou mais partidas cuja soma não fecha), e
            # confundi-los fazia a própria conferência se contradizer (uma
            # linha dizendo "sem_partidas" ao lado de um total de 5,00).
            if lancamento.quantidade_itens == 0:
                return "sem_partidas"
            if lancamento.quantidade_itens == 1:
                return "partida_unica"
            return "desbalanceado"

        lotes = [
            {
                "id": lancamento.id,
                "data": lancamento.data.isoformat(),
                "historico": lancamento.historico,
                "total_debito": _como_moeda(lancamento.total_debito),
                "total_credito": _como_moeda(lancamento.total_credito),
                "diferenca": _como_moeda(lancamento.total_debito - lancamento.total_credito),
                "motivo": _motivo(lancamento),
            }
            for lancamento in localizar_lotes_desbalanceados(empresa=empresa)
        ]

        contas_sinteticas_com_movimento = [
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                "debitos": _como_moeda(conta.debitos),
                "creditos": _como_moeda(conta.creditos),
            }
            for conta in localizar_contas_sinteticas_com_movimento(empresa=empresa)
        ]

        contas_que_aceitam_lancamento_e_tem_subordinadas = [
            {"conta": conta.codigo, "nome": conta.nome}
            for conta in localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(empresa=empresa)
        ]

        # BL-151, quinta categoria: a Conferência não tem período — uma base
        # torta é torta em qualquer recorte —, então aqui o equivalente ao
        # aviso das outras três saídas é listar o que está FORA DA FAIXA
        # PLAUSÍVEL (RC-77). É a única saída em que o `9999-12-31` já gravado
        # aparece sem o contador precisar suspeitar primeiro: validar a
        # entrada fecha a porta, e isto acende a luz sobre o que já entrou
        # (a DL-019 declara o reparo de dado já gravado fora de escopo).
        lancamentos_com_data_fora_da_faixa = [
            {
                "id": lancamento.id,
                "data": lancamento.data.isoformat(),
                "historico": lancamento.historico,
            }
            for lancamento in localizar_lancamentos_com_data_fora_da_faixa(empresa=empresa)
        ]

        return Response(
            {
                "lotes": lotes,
                "lancamentos_com_data_fora_da_faixa": lancamentos_com_data_fora_da_faixa,
                "contas_sinteticas_com_movimento": contas_sinteticas_com_movimento,
                "contas_que_aceitam_lancamento_e_tem_subordinadas": (
                    contas_que_aceitam_lancamento_e_tem_subordinadas
                ),
                "hierarquia_inconsistente": localizar_inconsistencias_de_hierarquia(
                    empresa=empresa
                ),
            }
        )
