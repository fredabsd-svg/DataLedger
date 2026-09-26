from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

# BL-217/A1 (auditoria DL-020 rodada 1): as views de FUNÇÃO deste módulo
# declaram os métodos HTTP que aceitam. É esta declaração — fato do objeto,
# não substring do fonte — que a varredura de contratos
# (`apps/core/tests/test_dl019_varredura_de_contratos.py`) lê para saber se a
# view é superfície de escrita. A classificação textual anterior
# (`"request.method" in fonte`) foi contornada pelo auditor com uma view que
# grava lendo `json.loads(request.body)`, com a suíte inteira verde.
from django.views.decorators.http import require_http_methods, require_safe
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.contabilidade.models import Competencia, Conta, EstadoCompetencia
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.fiscal.models import LoteDeRecepcao
from apps.fiscal.permissoes import (
    papel_pode_consultar_documentos,
    papel_pode_receber_documentos,
)
from apps.fiscal.services import documentos_do_escritorio
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    Papel,
    VinculoUsuarioEscritorio,
)
from apps.tenancy.services.primeiro_acesso import (
    ConvidanteNaoEhAdministrador,
    ConviteInvalido,
    ConviteTokenColidiu,
    PrimeiroEscritorioJaExiste,
    aceitar_convite_e_criar_vinculo,
    criar_primeiro_escritorio_e_vinculo_admin,
    emitir_convite_para_escritorio,
)

# BL-196 / achado R6-2 (rodada 6): a política dos cinco dicionários também
# nas duas superfícies de troca de escritório ativo. Medido pelo auditor:
# `ativar_escritorio` aceitava querystring, campo desconhecido e
# `request.FILES` — **302 nos três**, ignorando em silêncio —, e
# `POST /api/escritorio-ativo/` com `xpto` respondia **200**.
#
# As duas aceitam UM campo só (`escritorio_id`) e nenhum cabeçalho de
# idempotência: trocar de escritório é operação idempotente por natureza (o
# resultado de fazer duas vezes é o mesmo), então quem envia
# `Idempotency-Key` aqui está usando um contrato que não existe e precisa
# ouvir isso — é o mesmo erro do R5-6 na tela de lançamento, onde a chave
# ignorada produzia duplicidade.
CONTRATO_ESCRITORIO_ATIVO = ContratoDeRequisicao(
    campos={"escritorio_id"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na troca de escritório ativo",
)


# DL-018 — contratos do fluxo de bootstrap e convite (DL-018).
# Os campos `csrfmiddlewaretoken` aparecem no `request.POST` das views
# de função porque o Django injeta o token CSRF como campo do form
# automaticamente — não é dado de cliente, é mecanismo de defesa contra
# CSRF. Por isso ele entra em `campos` aqui: o `recusar_dado_nao_contratado`
# confere a forma do payload como um todo, e este campo é parte esperada
# do form.
CONTRATO_BOOTSTRAP_PRIMEIRO_ESCRITORIO = ContratoDeRequisicao(
    campos={"nome", "cnpj", "csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no bootstrap do primeiro escritório (DL-018)",
)


CONTRATO_EMITIR_CONVITE = ContratoDeRequisicao(
    campos={"escritorio_id", "email", "csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na emissão de convite por ADMINISTRADOR (DL-018)",
)


CONTRATO_ACEITAR_CONVITE = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no aceite de convite por usuário autenticado (DL-018)",
)


class MeusEscritoriosView(APIView):
    """Lista os escritórios aos quais o usuário autenticado tem vínculo ativo.

    Isolamento: o filtro é sempre por vínculo do usuário autenticado, nunca
    por um identificador recebido do cliente.

    `permission_classes` DECLARADO explicitamente (achado R3-10, auditoria
    DL-017 rodada 3): antes, esta view (e `EscritorioAtivoView`, abaixo) não
    declarava nada e dependia só de `REST_FRAMEWORK.DEFAULT_PERMISSION_
    CLASSES` (`config/settings.py`) para exigir autenticação — as ÚNICAS
    duas `APIView` do repositório nessa situação. Não havia vazamento (o
    padrão global já é `IsAuthenticated`), mas o risco é de MANUTENÇÃO:
    relaxar o padrão global para acrescentar uma rota pública no futuro
    tiraria a autenticação destas duas sem que nenhuma linha delas mudasse.
    `TemEscritorioAtivo` (usada no resto do projeto) NÃO serve aqui: as duas
    rotas existem justamente para o usuário CONSULTAR seus escritórios e
    definir/consultar o ativo — exigir um escritório já ativo seria
    impossível de satisfazer na primeira visita. `IsAuthenticated` é o
    mínimo correto, agora fixado na própria classe.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        escritorios = Escritorio.objects.filter(
            vinculos__usuario=request.user, vinculos__ativo=True
        ).distinct()
        return Response([{"id": e.id, "nome": e.nome, "cnpj": e.cnpj} for e in escritorios])


class EscritorioAtivoView(APIView):
    """Consulta ou define o escritório ativo na sessão do usuário.

    `permission_classes` declarado explicitamente pelo mesmo motivo de
    `MeusEscritoriosView` (achado R3-10) — ver o docstring dela.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.escritorio is None:
            return Response({"escritorio_ativo": None})
        return Response(
            {
                "escritorio_ativo": {
                    "id": request.escritorio.id,
                    "nome": request.escritorio.nome,
                    "papel": request.papel,
                }
            }
        )

    def post(self, request):
        # BL-196: a política vem de `apps.core.requisicao`; aqui só a
        # tradução para o protocolo desta superfície. 400 (entrada que o
        # contrato não aceita), não 403 — o 403 abaixo é para vínculo
        # inexistente, que é outra coisa e não deve ser confundida.
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ESCRITORIO_ATIVO)
        except DadoNaoContratado as exc:
            return Response({"detail": exc.mensagem}, status=400)

        escritorio_id_bruto = request.data.get("escritorio_id")

        # `para_id` (achado A2 da auditoria DL-017 rodada 4, BL-127, e o
        # gêmeo encontrado nesta mesma correção): antes, `escritorio_id`
        # ia direto para o `filter()` sem checagem nenhuma — um
        # identificador em texto com milhares de dígitos (`"9" * 6000`)
        # levantava `ValueError` DENTRO do ORM ao montar o filtro
        # (`Field 'id' expected a number but got ...`), 500 cru; e um
        # `int` JSON igualmente grande estourava o mesmo limite ao ser
        # comparado. `para_id` aceita as duas formas (texto da querystring/
        # formulário, número JSON) com o MESMO julgador, e nunca deixa um
        # identificador fora do formato chegar ao ORM.
        try:
            escritorio_id = para_id(escritorio_id_bruto)
        except IdentificadorInvalido:
            return Response({"detail": "Escritório inválido ou sem vínculo ativo."}, status=403)

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado.
        tem_vinculo = request.user.vinculos.filter(escritorio_id=escritorio_id, ativo=True).exists()
        if not tem_vinculo:
            return Response({"detail": "Escritório inválido ou sem vínculo ativo."}, status=403)

        # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava o `RegistroAuditoria`. Antes, se
        # o INSERT da trilha falhasse, a troca de escritório ativo
        # continuava válida e a auditoria ficava silenciosamente vazia.
        # **Limitação:** a `request.session` não reverte por
        # `transaction.atomic()` (ver comentário equivalente em
        # `ativar_escritorio`). A defesa cobre o RegistroAuditoria.
        with transaction.atomic():
            # request.escritorio ainda reflete o valor de antes da troca (o
            # middleware já rodou nesta requisição): busca o novo explicitamente.
            escritorio = Escritorio.objects.get(pk=escritorio_id)
            registrar(
                acao="escritorio.ativado",
                usuario=request.user,
                escritorio=escritorio,
            )
        request.session["escritorio_id"] = escritorio_id
        return Response({"status": "ok"})


# ---------------------------------------------------------------------------
# DL-042 (2ª passada): "Início" como fila do que precisa de atenção — o
# anti-padrão que a skill saas-design-excellence nomeia é o "dashboard de
# KPI vazio" (quatro caixinhas com número colorido, sem dizer que decisão o
# usuário toma). Aqui, cada categoria só aparece com dado REAL do produto
# (nunca uma métrica inventada), sempre filtrada pelo ESCRITÓRIO ATIVO
# (nunca uma consulta sem esse filtro — isolamento entre escritórios,
# AGENTS.md) e só para quem o SERVIDOR já deixaria ler aquele domínio — as
# MESMAS funções de permissão que as telas de contabilidade/fiscal usam
# (`papel_pode_ler_contabilidade`/`papel_pode_consultar_documentos`), nunca
# uma lista de papéis própria desta view (mesma disciplina do context
# processor `apps.core.context_processors.navegacao_do_menu`).
#
# Cada categoria devolve `None` quando não há nada pendente (a função
# `_fila_de_atencao` descarta), para o template distinguir "esta categoria
# está zerada" (não aparece) de "nenhuma categoria pendente" (estado vazio
# "tudo em dia"). O papel sem NENHUMA permissão relevante (ex.: CLIENTE)
# recebe `fila_de_atencao=None` do view — o template não renderiza a seção
# inteira, porque a fila não é "vazia para ele", é "não é dele".
# ---------------------------------------------------------------------------

LIMITE_ITENS_POR_CATEGORIA_DA_FILA = 8
JANELA_FISCAL_RECENTE = timedelta(days=30)


def _empresas_sem_plano_de_contas(escritorio):
    """Empresas em contabilidade por partidas dobradas sem NENHUMA conta
    cadastrada — não têm como lançar. Livro-caixa fica de fora: a
    contabilidade por partidas dobradas não se aplica a elas (mesmo
    critério já usado em templates/base.html, dropdown de Contabilidade)."""
    tem_conta = Conta.objects.filter(empresa_id=OuterRef("pk"))
    qs = (
        Empresa.objects.filter(
            escritorio=escritorio, modo_escrituracao=ModoEscrituracao.CONTABILIDADE
        )
        .annotate(tem_conta=Exists(tem_conta))
        .filter(tem_conta=False)
        .order_by("razao_social")
    )
    total = qs.count()
    if not total:
        return None
    return {
        "chave": "empresas-sem-plano-de-contas",
        "titulo": "Empresas sem plano de contas",
        "descricao": (
            "Em contabilidade por partidas dobradas, sem nenhuma conta cadastrada — "
            "não há como lançar ainda."
        ),
        "total": total,
        "itens": [
            {
                "titulo": empresa.razao_social,
                "url": reverse("contabilidade_web:plano_de_contas", args=[empresa.id]),
            }
            for empresa in qs[:LIMITE_ITENS_POR_CATEGORIA_DA_FILA]
        ],
    }


def _filtro_competencia_de_mes_anterior(hoje):
    """`Q` de "ano/mês estritamente anterior a `hoje`" — extraído de
    `_competencias_abertas_de_meses_anteriores` (DL-044, 2ª iteração) para
    ser a MESMA regra usada pela fila de atenção (lista completa) e pelo
    indicador do topo do Início (só a contagem) — nunca duas cópias do
    mesmo critério "o que é uma competência atrasada" (AGENTS.md, seção
    de duplicação)."""
    return Q(ano__lt=hoje.year) | (Q(ano=hoje.year) & Q(mes__lt=hoje.month))


def _competencias_abertas_de_meses_anteriores(escritorio):
    """Competências (meses com lançamento) de meses ANTERIORES ao atual,
    ainda no estado 'aberta' — candidatas a fechamento atrasado. Uma
    `Competencia` só existe quando o mês teve ao menos um lançamento
    (apps.contabilidade.models.Competencia, docstring), então isto nunca
    aponta mês sem movimento nenhum."""
    hoje = timezone.localdate()
    qs = (
        Competencia.objects.filter(empresa__escritorio=escritorio, estado=EstadoCompetencia.ABERTA)
        .filter(_filtro_competencia_de_mes_anterior(hoje))
        .select_related("empresa")
        .order_by("ano", "mes")
    )
    total = qs.count()
    if not total:
        return None
    return {
        "chave": "competencias-abertas",
        "titulo": "Competências de meses anteriores ainda abertas",
        "descricao": "Meses com lançamento que já passaram e continuam sem fechar.",
        "total": total,
        "itens": [
            {
                "titulo": (
                    f"{competencia.empresa.razao_social} — {competencia.mes:02d}/{competencia.ano}"
                ),
                "url": reverse("contabilidade_web:fechamento", args=[competencia.empresa_id]),
            }
            for competencia in qs[:LIMITE_ITENS_POR_CATEGORIA_DA_FILA]
        ],
    }


def _lotes_fiscais_com_recusa_recente(escritorio):
    """Lotes de recepção fiscal dos últimos 30 dias com pelo menos um
    arquivo recusado — a "conferência" que a Recepção já registra, trazida
    para o Início em vez de exigir visita à tela para descobrir."""
    corte = timezone.now() - JANELA_FISCAL_RECENTE
    qs = LoteDeRecepcao.objects.filter(
        escritorio=escritorio, total_recusados__gt=0, criado_em__gte=corte
    ).order_by("-criado_em")
    total = qs.count()
    if not total:
        return None
    return {
        "chave": "lotes-fiscais-com-recusa",
        "titulo": "Envios fiscais com recusas recentes",
        "descricao": "Últimos 30 dias, com pelo menos um arquivo recusado no envio.",
        "total": total,
        "itens": [
            {
                "titulo": f"{lote.nome_arquivo} — {lote.total_recusados} recusado(s)",
                "url": reverse("fiscal_web:relatorio_envio", args=[lote.id]),
            }
            for lote in qs[:LIMITE_ITENS_POR_CATEGORIA_DA_FILA]
        ],
    }


def _notas_canceladas_recentes(escritorio):
    """NFS-e recebidas nos últimos 30 dias cuja situação (derivada dos
    eventos — apps.fiscal.services.situacao_do_documento) é 'cancelada'.
    Reusa `documentos_do_escritorio`, que já anota a situação com UMA
    consulta (Exists/OuterRef), nunca N+1 por documento."""
    corte = timezone.now() - JANELA_FISCAL_RECENTE
    qs = documentos_do_escritorio(escritorio, situacao="cancelada").filter(criado_em__gte=corte)
    total = qs.count()
    if not total:
        return None
    return {
        "chave": "notas-canceladas",
        "titulo": "Notas canceladas recebidas",
        "descricao": "Últimos 30 dias, com evento de cancelamento identificado.",
        "total": total,
        "itens": [
            {
                "titulo": f"NFS-e {documento.numero or documento.identificador[-6:]} — "
                f"{documento.tomador_nome or documento.prestador_nome or 'sem nome'}",
                "url": reverse("fiscal_web:documento_detalhe", args=[documento.id]),
            }
            for documento in qs[:LIMITE_ITENS_POR_CATEGORIA_DA_FILA]
        ],
    }


def _empresas_cpf_em_livro_caixa(escritorio):
    """Informativo (não é uma pendência a resolver): empresas CPF em
    livro-caixa, para lembrar que a contabilidade por partidas dobradas
    não se aplica a elas — mesmo aviso que o dropdown de Contabilidade
    (templates/base.html) já mostra tela a tela, reunido aqui."""
    qs = (
        Empresa.objects.filter(
            escritorio=escritorio, modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA
        )
        .exclude(cpf="")
        .order_by("razao_social")
    )
    total = qs.count()
    if not total:
        return None
    return {
        "chave": "empresas-cpf-livro-caixa",
        "titulo": "Empresas CPF em livro-caixa",
        "descricao": (
            "Informativo — a contabilidade por partidas dobradas não se aplica a estas empresas."
        ),
        "total": total,
        "informativo": True,
        "itens": [
            {"titulo": empresa.razao_social, "url": None}
            for empresa in qs[:LIMITE_ITENS_POR_CATEGORIA_DA_FILA]
        ],
        "url_ver_todos": reverse("empresas:lista"),
    }


# ---------------------------------------------------------------------------
# DL-044 (2ª iteração, Fred via arquiteto-senior): "o Início continua 60%
# vazio". Autorização explícita do arquiteto-senior para consulta NOVA de
# APRESENTAÇÃO neste arquivo — faixa de indicadores (contagem grande,
# clicável) e tabela "Empresas da carteira", sempre filtradas pelo
# ESCRITÓRIO ATIVO, com a mesma disciplina de isolamento e permissão da
# fila de atenção acima (nunca uma segunda lista de papéis própria desta
# view). Nenhuma REGRA nova: os indicadores reaproveitam o MESMO critério
# já usado pela fila (`_filtro_competencia_de_mes_anterior`, os mesmos
# filtros de `LoteDeRecepcao`/`documentos_do_escritorio`), só a FORMA de
# apresentação muda (contagem em vez de lista de itens).
# ---------------------------------------------------------------------------


def _url_opcional(nome_de_rota, *args):
    """`reverse(nome_de_rota, args=args)`, ou `None` quando a rota não
    existe no urlconf ATUAL — mesmo cuidado que `templates/base.html` já
    aplica ao link do módulo Fiscal na barra lateral (`{% url
    'fiscal_web:recepcao' as url_fiscal %}`, que não lança exceção): esta
    view roda por trás de `tenancy:painel`, que pode ser exercitada sob um
    urlconf ESPELHO de outro app (`@pytest.mark.urls`, vários arquivos de
    teste do produto) sem `apps.fiscal.urls_web` incluído — sem esta
    função, `reverse` levantaria `NoReverseMatch` e devolveria 500 numa
    tela que deveria simplesmente omitir o módulo que não existe ali."""
    try:
        return reverse(nome_de_rota, args=list(args))
    except NoReverseMatch:
        return None


def _indicadores_do_painel(*, escritorio, papel):
    """Faixa de indicadores do topo do Início — números grandes,
    clicáveis, cada um levando à tela que resolve ou explica o número
    (nunca um número solto sem ação, o anti-padrão "dashboard de KPI"
    que a DL-042 já evitava na fila de atenção — aqui o mesmo princípio
    se aplica ao indicador). "Empresas ativas" não depende de papel
    (visível a qualquer um que veja o Início); os outros três seguem a
    MESMA permissão que a fila de atenção já aplica a cada domínio.
    """
    indicadores = [
        {
            "chave": "empresas-ativas",
            "titulo": "Empresas ativas",
            "total": Empresa.objects.filter(escritorio=escritorio, ativo=True).count(),
            "url": reverse("empresas:lista"),
        }
    ]

    if papel_pode_ler_contabilidade(papel):
        hoje = timezone.localdate()
        total_competencias_atrasadas = (
            Competencia.objects.filter(
                empresa__escritorio=escritorio, estado=EstadoCompetencia.ABERTA
            )
            .filter(_filtro_competencia_de_mes_anterior(hoje))
            .count()
        )
        indicadores.append(
            {
                "chave": "competencias-atrasadas",
                "titulo": "Competências de meses anteriores ainda abertas",
                "total": total_competencias_atrasadas,
                "url": reverse("tenancy:painel") + "#fila-de-atencao",
            }
        )

    if papel_pode_consultar_documentos(papel):
        corte = timezone.now() - JANELA_FISCAL_RECENTE
        total_lotes_com_recusa = LoteDeRecepcao.objects.filter(
            escritorio=escritorio, total_recusados__gt=0, criado_em__gte=corte
        ).count()
        total_notas_canceladas = (
            documentos_do_escritorio(escritorio, situacao="cancelada")
            .filter(criado_em__gte=corte)
            .count()
        )
        indicadores.append(
            {
                "chave": "envios-com-recusa",
                "titulo": "Envios com recusa (30 dias)",
                "total": total_lotes_com_recusa,
                "url": reverse("tenancy:painel") + "#fila-de-atencao",
            }
        )
        indicadores.append(
            {
                "chave": "notas-canceladas",
                "titulo": "Notas canceladas (30 dias)",
                "total": total_notas_canceladas,
                "url": reverse("tenancy:painel") + "#fila-de-atencao",
            }
        )
    return indicadores


def _empresas_da_carteira(escritorio):
    """Tabela "Empresas da carteira" do Início — CNPJ/CPF, modo de
    escrituração, última competência fechada e pendências (competências
    atrasadas), com ação "Abrir". Consulta de tamanho CONSTANTE: uma para
    as empresas, e duas agregações (`values().annotate()`, agrupadas por
    empresa) para "última competência fechada" e "pendências" — nunca uma
    consulta POR empresa (o teto de consultas é medido em
    apps/tenancy/tests/test_dl044_painel_carteira_e_indicadores.py).

    Reaproveita `_mascara_cnpj`/`_mascara_cpf`
    (`apps.empresas.views`, mesmo padrão já usado nesta base de código
    para importar um auxiliar de apresentação com nome "privado" de outro
    módulo — ver `apps.contabilidade.views_web` importando
    `_saldo_absoluto_com_natureza` de `apps.contabilidade.views`) — nunca
    uma segunda função de máscara de CNPJ/CPF.
    """
    from apps.empresas.views import _mascara_cnpj, _mascara_cpf  # noqa: PLC0415

    empresas = list(Empresa.objects.filter(escritorio=escritorio).order_by("razao_social"))
    if not empresas:
        return []

    # "Última competência fechada": ano/mês codificados como `ano*100+mes`
    # (um inteiro só cresce na ordem certa: 202603 > 202512) para o Max()
    # do banco escolher a competência mais RECENTE por empresa numa única
    # consulta agrupada — nunca uma sub-consulta por linha.
    ultimas = (
        Competencia.objects.filter(
            empresa__escritorio=escritorio, estado=EstadoCompetencia.ENCERRADA
        )
        .values("empresa_id")
        .annotate(chave=Max(F("ano") * 100 + F("mes")))
    )
    mapa_ultima_fechada = {linha["empresa_id"]: divmod(linha["chave"], 100) for linha in ultimas}

    hoje = timezone.localdate()
    pendencias = (
        Competencia.objects.filter(empresa__escritorio=escritorio, estado=EstadoCompetencia.ABERTA)
        .filter(_filtro_competencia_de_mes_anterior(hoje))
        .values("empresa_id")
        .annotate(total=Count("id"))
    )
    mapa_pendencias = {linha["empresa_id"]: linha["total"] for linha in pendencias}

    linhas = []
    for empresa in empresas:
        em_livro_caixa = empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA
        if empresa.tipo_inscricao == TipoInscricao.CPF:
            rotulo_inscricao, inscricao_formatada = "CPF", _mascara_cpf(empresa.cpf)
        else:
            rotulo_inscricao, inscricao_formatada = "CNPJ", _mascara_cnpj(empresa.cnpj)
        ultima = mapa_ultima_fechada.get(empresa.id)
        linhas.append(
            {
                "empresa": empresa,
                "rotulo_inscricao": rotulo_inscricao,
                "inscricao_formatada": inscricao_formatada,
                "em_livro_caixa": em_livro_caixa,
                "ultima_competencia_fechada": f"{ultima[1]:02d}/{ultima[0]}" if ultima else None,
                "pendencias": mapa_pendencias.get(empresa.id, 0),
                "url_abrir": (
                    None
                    if em_livro_caixa
                    else reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
                ),
            }
        )
    return linhas


def _acoes_rapidas_do_painel(*, papel, empresas_da_carteira):
    """Ações rápidas do Início — botões (item 3 da 2ª iteração: "botões
    com ícone onde fizer sentido", nunca link solto para uma ação
    primária). "Novo lançamento" pede empresa quando precisa: vai direto
    à empresa quando há exatamente uma candidata elegível (não
    livro-caixa) na carteira; leva à lista de empresas (que já oferece
    "Lançar" por linha, DL-017) quando há mais de uma. Reaproveita
    `empresas_da_carteira` — já calculada por `_empresas_da_carteira` —
    então esta função não soma nenhuma consulta nova.

    Mesma permissão por ação que a tela de destino já exige no servidor
    (`papel_pode_ler_contabilidade`, `papel_pode_receber_documentos`, e o
    mesmo par ADMINISTRADOR/GESTOR que `lista_empresas` usa para
    `pode_cadastrar`) — o botão só aparece quando a ação seria aceita.
    """
    acoes = []
    if papel_pode_ler_contabilidade(papel):
        elegiveis = [linha for linha in empresas_da_carteira if not linha["em_livro_caixa"]]
        if len(elegiveis) == 1:
            url_lancamento = reverse(
                "contabilidade_web:lancamento_novo", args=[elegiveis[0]["empresa"].id]
            )
        else:
            url_lancamento = reverse("empresas:lista")
        acoes.append(
            {
                "chave": "novo-lancamento",
                "rotulo": "Novo lançamento",
                "url": url_lancamento,
                "icone": "mais",
            }
        )
    url_recepcao = (
        _url_opcional("fiscal_web:recepcao") if papel_pode_receber_documentos(papel) else None
    )
    if url_recepcao is not None:
        acoes.append(
            {
                "chave": "receber-nfse",
                "rotulo": "Receber NFS-e",
                "url": url_recepcao,
                "icone": "envio",
            }
        )
    if papel in (Papel.ADMINISTRADOR, Papel.GESTOR):
        acoes.append(
            {
                "chave": "cadastrar-empresa",
                "rotulo": "Cadastrar empresa",
                "url": reverse("empresas:criar"),
                "icone": "empresa",
            }
        )
    return acoes


def _modulos_do_painel(*, papel, empresas_da_carteira):
    """Tiles de MÓDULO do Início (DL-044, 3ª iteração — retorno do Fred,
    referência Conta Azul: "módulos no Início também como tiles com
    ícone"). Reaproveita `empresas_da_carteira` — mesma lógica de destino
    de `_acoes_rapidas_do_painel` — nenhuma consulta nova.

    "Planejado" para Folha/Honorários só porque a landing pública já os
    lista como planejados (templates/registration/landing.html, seção
    "Evolução por módulos") — nunca um rótulo inventado aqui; a mesma
    palavra, o mesmo estado, para não afirmar duas coisas diferentes em
    duas telas do produto."""
    elegiveis = [linha for linha in empresas_da_carteira if not linha["em_livro_caixa"]]
    url_contabilidade = (
        reverse("contabilidade_web:relatorios", args=[elegiveis[0]["empresa"].id])
        if len(elegiveis) == 1
        else reverse("empresas:lista")
    )
    modulos = []
    if papel_pode_ler_contabilidade(papel):
        modulos.append(
            {
                "chave": "contabilidade",
                "icone": "contabilidade",
                "titulo": "Contabilidade",
                "descricao": "Lançamentos, relatórios e fechamento de competência.",
                "url": url_contabilidade,
                "planejado": False,
            }
        )
    url_fiscal = (
        _url_opcional("fiscal_web:recepcao") if papel_pode_consultar_documentos(papel) else None
    )
    if url_fiscal is not None:
        modulos.append(
            {
                "chave": "fiscal",
                "icone": "fiscal",
                "titulo": "Fiscal",
                "descricao": "Recepção e consulta de NFS-e nacional.",
                "url": url_fiscal,
                "planejado": False,
            }
        )
    modulos.append(
        {
            "chave": "empresas",
            "icone": "empresas",
            "titulo": "Empresas",
            "descricao": "Cadastro e carteira do escritório.",
            "url": reverse("empresas:lista"),
            "planejado": False,
        }
    )
    modulos.append(
        {
            "chave": "folha",
            "icone": "conta",
            "titulo": "Folha de pagamento",
            "descricao": "Planejado — ainda não iniciado.",
            "url": None,
            "planejado": True,
        }
    )
    modulos.append(
        {
            "chave": "honorarios",
            "icone": "conta",
            "titulo": "Honorários",
            "descricao": "Planejado — ainda não iniciado.",
            "url": None,
            "planejado": True,
        }
    )
    return modulos


def _fila_de_atencao(*, escritorio, papel):
    """`None` quando o papel não lê NEM contabilidade NEM fiscal (a fila
    não é "vazia" para ele, é "não é dele" — o template não desenha a
    seção). Lista (possivelmente vazia) quando ao menos uma permissão
    existe — lista vazia é o estado "tudo em dia", desenhado no template."""
    pode_contabilidade = papel_pode_ler_contabilidade(papel)
    pode_fiscal = papel_pode_consultar_documentos(papel)
    if not pode_contabilidade and not pode_fiscal:
        return None

    categorias = []
    if pode_contabilidade:
        categorias.append(_empresas_sem_plano_de_contas(escritorio))
        categorias.append(_competencias_abertas_de_meses_anteriores(escritorio))
        categorias.append(_empresas_cpf_em_livro_caixa(escritorio))
    if pode_fiscal:
        categorias.append(_lotes_fiscais_com_recusa_recente(escritorio))
        categorias.append(_notas_canceladas_recentes(escritorio))
    return [categoria for categoria in categorias if categoria is not None]


@require_safe
def painel(request):
    """Página inicial pós-login: mostra o escritório ativo, permite trocar,
    e — DL-042 — a fila do que precisa de atenção no escritório ATIVO.

    Fluxo simples com formulário HTML padrão nesta etapa; HTMX/Alpine
    entram quando houver necessidade real de atualização parcial de
    página, evitando complexidade sem uso imediato.
    """
    if not request.user.is_authenticated:
        return render(request, "registration/landing.html")
    escritorios = Escritorio.objects.filter(
        vinculos__usuario=request.user, vinculos__ativo=True
    ).distinct()
    fila_de_atencao = None
    indicadores = None
    empresas_da_carteira = None
    acoes_rapidas = None
    modulos = None
    if request.escritorio is not None:
        papel = getattr(request, "papel", None)
        fila_de_atencao = _fila_de_atencao(escritorio=request.escritorio, papel=papel)
        indicadores = _indicadores_do_painel(escritorio=request.escritorio, papel=papel)
        # BL-042 (achado desta iteração, apps/tenancy/tests/
        # test_dl042_fila_de_atencao.py::test_papel_cliente_nao_ve_a_fila_
        # de_atencao): "Empresas da carteira" mostra pendência e situação
        # OPERACIONAL de cada empresa — a MESMA classe de informação que a
        # fila de atenção já restringe a quem lê contabilidade. Sem este
        # `if`, um papel CLIENTE (fora de PAPEIS_QUE_LEEM_CONTABILIDADE)
        # via a fila corretamente OCULTA continuava vendo a razão social e
        # a pendência de outra empresa do escritório nesta tabela nova —
        # a MESMA fuga de informação que a fila já existia para impedir,
        # só que por uma porta que esta iteração abriu. `[]`, não `None`,
        # para as duas funções abaixo (que já filtram por papel sozinhas)
        # nunca ficarem sem lista para iterar.
        pode_ver_carteira = papel_pode_ler_contabilidade(papel)
        empresas_da_carteira_lista = (
            _empresas_da_carteira(request.escritorio) if pode_ver_carteira else []
        )
        acoes_rapidas = _acoes_rapidas_do_painel(
            papel=papel, empresas_da_carteira=empresas_da_carteira_lista
        )
        modulos = _modulos_do_painel(papel=papel, empresas_da_carteira=empresas_da_carteira_lista)
        empresas_da_carteira = empresas_da_carteira_lista if pode_ver_carteira else None
    return render(
        request,
        "tenancy/painel.html",
        {
            "escritorios": escritorios,
            "escritorio_ativo": request.escritorio,
            "fila_de_atencao": fila_de_atencao,
            "indicadores": indicadores,
            "empresas_da_carteira": empresas_da_carteira,
            "acoes_rapidas": acoes_rapidas,
            "modulos": modulos,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def ativar_escritorio(request):
    if request.method == "POST":
        # BL-196: mesma política da view irmã acima, mesma fonte única, e
        # aqui na forma que esta superfície usa para dizer "não" — mensagem
        # de erro e volta ao painel, o padrão que o BL-23 instituiu para
        # todo caminho que NÃO ativa. O auditor mediu 302 silencioso para
        # querystring, campo desconhecido e arquivo: a troca não acontecia
        # (ou acontecia com dado ignorado) e o usuário não era avisado de
        # nada.
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ESCRITORIO_ATIVO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect("tenancy:painel")

        escritorio_id = request.POST.get("escritorio_id")

        # BL-23: antes, um vínculo inexistente (ou um valor não numérico)
        # caía direto no redirecionamento sem avisar nada — o usuário achava
        # que a troca tinha funcionado. Agora todo caminho que não ativa
        # termina em mensagem de erro explícita.
        #
        # `para_id` (achado A2 da auditoria DL-017 rodada 4, BL-127):
        # SUBSTITUI a validação por `str(escritorio_id).isdigit()` +
        # `int(escritorio_id)` que havia aqui. O comentário que justificava
        # essa escolha ("evita depender de exceção para um caso de entrada
        # tão comum") é exatamente o que causava o defeito: `.isdigit()`
        # aceita QUALQUER dígito Unicode (`"２"`.isdigit()` é `True`,
        # reinterpretado em silêncio para `2`) e não impõe limite de
        # comprimento (`"9" * 6000` passa em `.isdigit()`, e só o `int()`
        # seguinte estourava com `ValueError` cru — 500). `para_id` aplica
        # as duas defesas de uma vez, com o mesmo julgador usado em
        # `EscritorioAtivoView.post` (view irmã, mesmo arquivo) — nunca
        # reimplementado aqui.
        try:
            escritorio_id_valido = para_id(escritorio_id)
        except IdentificadorInvalido:
            messages.error(request, "Escritório inválido.")
            return redirect("tenancy:painel")

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado (mesma
        # regra de isolamento aplicada em EscritorioAtivoView.post).
        tem_vinculo = request.user.vinculos.filter(
            escritorio_id=escritorio_id_valido, ativo=True
        ).exists()
        if not tem_vinculo:
            messages.error(request, "Escritório inválido ou sem vínculo ativo com o seu usuário.")
            return redirect("tenancy:painel")

        # BL-14 (DL-024): `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava o `RegistroAuditoria`. Antes, se
        # o INSERT da trilha falhasse, a troca de escritório ativo
        # continuava válida e a auditoria ficava silenciosamente vazia —
        # a sessão dizia uma coisa, a trilha dizia outra. Agora ambos
        # são uma só operação atômica; qualquer exceção do `registrar()`
        # propaga e a transação reverte. **Limitação:** a `request.session`
        # não é revertida por `transaction.atomic()` — a troca fica
        # registrada no cookie mesmo se a trilha falhar. Quem precisa de
        # reversão completa da sessão precisa de abordagem diferente
        # (fora do escopo do BL-14, registro como pendência para DL futura).
        with transaction.atomic():
            escritorio = Escritorio.objects.get(pk=escritorio_id_valido)
            registrar(acao="escritorio.ativado", usuario=request.user, escritorio=escritorio)
        request.session["escritorio_id"] = escritorio_id_valido
        messages.success(request, f"Escritório ativo: {escritorio.nome}.")
    else:
        # BL-23/A9: GET nesta URL (link direto, favorito, back do navegador)
        # também voltava em silêncio — mesmo problema do POST inválido, só
        # que pelo método errado em vez do ID errado. O formulário do
        # painel só envia POST; chegar aqui por GET não troca nada e
        # precisa dizer isso.
        messages.error(request, "Use o formulário do painel para trocar de escritório.")
    return redirect("tenancy:painel")


# ---------------------------------------------------------------------------
# DL-018 — primeiro acesso via produto (DE-042)
# ---------------------------------------------------------------------------
#
# Três superfícies novas:
#
# - `bootstrap_primeiro_acesso` (GET/POST): tela para o usuário sem
#   vínculo criar o primeiro escritório. Renderiza um formulário
#   simples (nome + CNPJ). POST cria escritório e vincula o usuário
#   como ADMINISTRADOR — redireciona para o painel.
# - `emitir_convite` (POST): API para o ADMINISTRADOR do escritório
#   cadastrar o e-mail do segundo funcionário.
# - `aceitar_convite` (GET/POST): tela para o convidado apresentar o
#   token recebido (em geral via link), autenticado, e virar
#   ANALISTA do escritório.
#
# A defesa é no serviço (`primeiro_acesso.py`), não nas views — aqui só
# tradução HTTP. As exceções de domínio viram 400/403/409/410 conforme o
# contrato.


@login_required
@require_http_methods(["GET", "POST"])
def bootstrap_primeiro_acesso(request):
    """DL-018 critério 1: primeira superfície para o usuário sem
    vínculo. Renderiza formulário no GET e cria escritório + vínculo
    ADMINISTRADOR no POST.

    O ponto-chave é a `PrimeiroEscritorioJaExiste` no serviço: se o
    usuário JÁ tem escritório, o caminho `bootstrap` não é o dele —
    redirecionar para o painel. Defesa contra o caso "duas abas
    abertas de bootstrap no mesmo usuário": o segundo POST cai no
    painel com mensagem de erro, e não em 500."""
    if VinculoUsuarioEscritorio.objects.filter(usuario=request.user, ativo=True).exists():
        messages.info(
            request,
            "Você já tem escritório. Use o painel para gerenciar.",
        )
        return redirect("tenancy:painel")

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_BOOTSTRAP_PRIMEIRO_ESCRITORIO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return render(request, "tenancy/primeiro_acesso.html", {})

        nome = (request.POST.get("nome") or "").strip()
        cnpj = (request.POST.get("cnpj") or "").strip()
        if not nome or not cnpj:
            messages.error(request, "Nome e CNPJ são obrigatórios.")
            return render(
                request,
                "tenancy/primeiro_acesso.html",
                {"nome": nome, "cnpj": cnpj},
            )

        try:
            resultado = criar_primeiro_escritorio_e_vinculo_admin(
                usuario=request.user,
                nome=nome,
                cnpj=cnpj,
            )
        except PrimeiroEscritorioJaExiste:
            messages.error(request, "Você já tem escritório ativo.")
            return redirect("tenancy:painel")

        messages.success(
            request,
            f"Escritório criado: {resultado.escritorio.nome}. "
            "Você é o ADMINISTRADOR. Convide o segundo funcionário pela tela de escritório.",
        )
        return redirect("tenancy:painel")

    return render(request, "tenancy/primeiro_acesso.html", {})


@login_required
@require_http_methods(["POST"])
def emitir_convite(request):
    """DL-018 critério 3: ADMINISTRADOR do escritório convida o
    segundo funcionário por e-mail. Token opaco devolvido na resposta
    — a próxima etapa que envia por e-mail de verdade (SMTP) entra
    aqui.
    """
    try:
        recusar_dado_nao_contratado(request, CONTRATO_EMITIR_CONVITE)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect("tenancy:painel")

    escritorio_id_raw = request.POST.get("escritorio_id")
    email = (request.POST.get("email") or "").strip()

    try:
        escritorio_id = para_id(escritorio_id_raw)
    except IdentificadorInvalido:
        messages.error(request, "Escritório inválido.")
        return redirect("tenancy:painel")

    try:
        escritorio = Escritorio.objects.get(pk=escritorio_id)
    except Escritorio.DoesNotExist:
        messages.error(request, "Escritório inválido.")
        return redirect("tenancy:painel")

    if not email:
        messages.error(request, "E-mail do convidado é obrigatório.")
        return redirect("tenancy:painel")

    try:
        convite = emitir_convite_para_escritorio(
            escritorio=escritorio,
            email_convidado=email,
            convidador=request.user,
        )
    except ConvidanteNaoEhAdministrador:
        messages.error(
            request,
            "Apenas ADMINISTRADOR ativo pode convidar. "
            "Se você é o segundo funcionário, aguarde o convite.",
        )
        return redirect("tenancy:painel")
    except ConviteTokenColidiu:
        # Provavelmente impossível (~1 em 2^190). Tentar de novo — o
        # `save()` do modelo vai gerar outro token. Não é 5xx: o cliente
        # PODE retentar com o mesmo payload.
        messages.warning(
            request,
            "Colisão rara de token. Tente novamente — o sistema gerou outro token automaticamente.",
        )
        return redirect("tenancy:painel")

    messages.success(
        request,
        f"Convite emitido para {convite.email}. A próxima etapa envia por e-mail de verdade.",
    )
    return redirect("tenancy:painel")


@login_required
@require_http_methods(["GET", "POST"])
def aceitar_convite(request, token: str):
    """DL-018 critério 3: usuário autenticado apresenta o token de
    convite e vira ANALISTA (ou o `papel_inicial` do convite) do
    escritório. Token está no path da URL para simplicidade da etapa
    — quando SMTP entrar, o token vem por link no e-mail, e esta
    rota permanece a mesma.
    """
    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ACEITAR_CONVITE)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect("tenancy:painel")

        try:
            aceitar_convite_e_criar_vinculo(token=token, usuario=request.user)
        except ConviteInvalido:
            messages.error(
                request,
                "Convite inexistente, expirado ou já consumido.",
            )
            return redirect("tenancy:painel")

        messages.success(
            request,
            "Vínculo criado. Use o painel para começar.",
        )
        return redirect("tenancy:painel")

    convite = ConviteEscritorio.objects.filter(token=token).first()
    return render(
        request,
        "tenancy/aceitar_convite.html",
        {"token": token, "convite": convite},
    )
