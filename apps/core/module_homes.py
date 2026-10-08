"""Consultas somente de leitura para as homes operacionais (DL-049).

Nenhum GET cria competência, acompanha tratamento que não existe ou faz
apuração monetária. Os modelos existentes delimitam os indicadores: Fiscal
mostra ocorrências registradas; Livro-caixa não ganha um fechamento fictício.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from urllib.parse import urlencode

from django.db.models import Exists, OuterRef, Prefetch, Q, Value
from django.db.models.functions import Concat
from django.http import Http404
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.contabilidade.models import Competencia, Conta, EstadoCompetencia
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.contabilidade.services import localizar_lotes_desbalanceados
from apps.contabilidade.views import PodeEscriturar, PodeFecharCompetencia
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.fiscal.models import (
    DocumentoFiscal,
    EventoFiscal,
    ResultadoDoArquivo,
    TipoResultadoArquivo,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.permissoes import papel_pode_consultar_documentos, papel_pode_receber_documentos
from apps.fiscal.services import documentos_do_escritorio
from apps.livro_caixa.models import ContaLivroCaixa, LancamentoCaixa
from apps.livro_caixa.permissoes import (
    papel_pode_escriturar_livro_caixa,
    papel_pode_ler_livro_caixa,
)

SESSION_KEY = "module_home_context"
# Preferência é conveniência de navegação, não histórico de operação.
# Conservam-se os 16 escritórios usados mais recentemente na sessão para
# permitir ida e volta sem crescimento ilimitado do payload.
LIMITE_PREFERENCIAS_ESCRITORIOS = 16
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
# DL-051: Vendas não pertence ao aplicativo contábil. Estoque e inventário
# são rotinas de Fiscal (FIS-39/FIS-47), sem módulo independente ou placeholder.
MODULOS = {
    "contabilidade": {
        "slug": "contabilidade",
        "titulo": "Contabilidade",
        "disponibilidade": "disponivel",
    },
    "fiscal": {"slug": "fiscal", "titulo": "Fiscal", "disponibilidade": "parcial"},
    "livro-caixa": {
        "slug": "livro-caixa",
        "titulo": "Livro-caixa",
        "disponibilidade": "disponivel",
    },
    "financeiro": {"slug": "financeiro", "titulo": "Financeiro", "disponibilidade": "indisponivel"},
    "folha": {"slug": "folha", "titulo": "Folha", "disponibilidade": "indisponivel"},
}


class FiltroHomeInvalido(ValueError):
    """Filtro não contratual; a view responde 400 sem expor o valor bruto."""


def modulo_conhecido(slug):
    """Resolve somente módulos declarados, nunca um nome de template recebido."""
    if slug not in MODULOS:
        raise Http404
    return MODULOS[slug]


def pode_ler_modulo(papel, slug):
    """Reusa as decisões do domínio antes de consultar empresas ou totais."""
    if slug == "fiscal":
        return papel_pode_consultar_documentos(papel)
    if slug == "livro-caixa":
        return papel_pode_ler_livro_caixa(papel)
    # Os módulos ainda indisponíveis não têm matriz fina de autorização.
    # Sua página informativa fica restrita à leitura interna já existente,
    # sem inventar um papel DP nem expor clientes a quem o núcleo recusa.
    return papel_pode_ler_contabilidade(papel)


def numero_ptbr(numero):
    return f"{numero:,}".replace(",", ".")


def _id_valido(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", valor):
        raise FiltroHomeInvalido("Selecione uma empresa válida deste escritório.")
    identificador = int(valor)
    if identificador > 9223372036854775807:
        raise FiltroHomeInvalido("Selecione uma empresa válida deste escritório.")
    return identificador


def competencia_valida(valor):
    """Gramática limitada, igual à faixa 1970–2999 do domínio contábil."""
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", valor):
        raise FiltroHomeInvalido("Informe a competência no formato mês/ano.")
    ano, mes = (int(parte) for parte in valor.split("-"))
    if not 1970 <= ano <= 2999:
        raise FiltroHomeInvalido("A competência deve estar entre jan/1970 e dez/2999.")
    return ano, mes


def empresa_elegivel(empresa, slug):
    if slug == "contabilidade":
        return empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE
    if slug == "livro-caixa":
        return (
            empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA
            and empresa.tipo_inscricao == TipoInscricao.CPF
        )
    return True


def _contextos_da_sessao(request):
    """Preferências limitadas por escritório, aceitando o formato anterior.

    Não consulta vínculos nem empresas: esses controles continuam no
    middleware e em resolver_escopo. O formato antigo é lido como uma
    entrada do próprio escritório, e migrado na próxima seleção válida.
    """
    bruto = getattr(request, "session", {}).get(SESSION_KEY, {})
    if not isinstance(bruto, dict):
        return {}
    contextos = bruto.get("escritorios")
    if not isinstance(contextos, dict):
        escritorio_id = bruto.get("escritorio_id")
        contextos = {str(escritorio_id): bruto} if escritorio_id is not None else {}
    resultado = {}
    for chave, contexto in list(contextos.items())[-LIMITE_PREFERENCIAS_ESCRITORIOS:]:
        if not isinstance(contexto, dict):
            continue
        try:
            _id_valido(chave)
            competencia_valida(contexto.get("competencia"))
        except FiltroHomeInvalido:
            continue
        empresa = contexto.get("empresa", "")
        empresas = contexto.get("empresas", [])
        if not isinstance(empresa, str) or len(empresa) > 19:
            continue
        if not isinstance(empresas, list) or sum(len(str(valor)) for valor in empresas) > 10000:
            continue
        resultado[chave] = {
            "empresa": empresa,
            "empresas": empresas,
            "competencia": contexto["competencia"],
        }
    return resultado


def _preferencia_do_escritorio(request):
    escritorio = getattr(request, "escritorio", None)
    if escritorio is None:
        return {}
    return _contextos_da_sessao(request).get(str(escritorio.pk), {})


def _memorizar_preferencia(request, escopo):
    contextos = _contextos_da_sessao(request)
    chave = str(escopo.escritorio.pk)
    # Remover e reinserir atualiza a ordem de uso conservada pelo JSON da
    # sessão; só a entrada corrente é alterada, nunca a de outro escritório.
    contextos.pop(chave, None)
    contextos[chave] = {
        "empresa": escopo.empresa,
        "empresas": [str(pk) for pk in escopo.empresas_ids] if escopo.empresa == "grupo" else [],
        "competencia": escopo.competencia,
    }
    request.session[SESSION_KEY] = {
        "escritorios": dict(list(contextos.items())[-LIMITE_PREFERENCIAS_ESCRITORIOS:])
    }


@dataclass
class EscopoHome:
    modulo: str
    escritorio: object
    empresa: str
    empresas_ids: list[int]
    empresas: list
    opcoes: list
    ano: int
    mes: int
    selecao_automatica: bool = False
    inaplicavel: bool = False

    @property
    def competencia(self):
        return f"{self.ano:04d}-{self.mes:02d}"

    @property
    def competencia_rotulo(self):
        return f"{MESES[self.mes - 1]}/{self.ano}"

    @property
    def inicio(self):
        return date(self.ano, self.mes, 1)

    @property
    def fim(self):
        return date(self.ano, self.mes, calendar.monthrange(self.ano, self.mes)[1])

    @property
    def parametros(self):
        parametros = {"empresa": self.empresa, "competencia": self.competencia}
        if self.empresa == "grupo":
            parametros["empresas"] = ",".join(str(pk) for pk in self.empresas_ids)
        return parametros

    def url(self, nome="home", **extras):
        parametros = {**self.parametros, **extras}
        if str(parametros.get("empresa")) != "grupo":
            parametros.pop("empresas", None)
        return reverse(f"module_home:{nome}", args=[self.modulo]) + "?" + urlencode(parametros)


def resolver_escopo(request, slug):
    """Valida filtros contra o escritório antes de memorizar a seleção.

    A sessão guarda preferência por escritório, não autorização. Os IDs
    recuperados são revalidados contra o escritório ativo; mudar módulo
    mantém uma empresa incompatível explicitamente selecionada e mostra
    inaplicabilidade, em vez de ampliar para a carteira.
    """
    if set(request.GET) - {"empresa", "empresas", "competencia", "estado", "pagina"}:
        raise FiltroHomeInvalido("Há um filtro não reconhecido nesta página.")
    for campo in ("empresa", "competencia", "estado", "pagina"):
        if len(request.GET.getlist(campo)) > 1:
            raise FiltroHomeInvalido("Informe cada filtro apenas uma vez.")
    anterior = _preferencia_do_escritorio(request)
    hoje = timezone.localdate()
    periodo = request.GET.get("competencia", anterior.get("competencia", f"{hoje:%Y-%m}"))
    ano, mes = competencia_valida(periodo)
    # Essa é a única consulta plural do seletor; só roda dentro da view já
    # autorizada. O context processor global jamais recebe essa lista.
    opcoes = list(
        Empresa.objects.filter(escritorio=request.escritorio)
        .only("id", "razao_social", "ativo", "modo_escrituracao", "tipo_inscricao")
        .order_by("razao_social", "id")
    )
    por_id = {empresa.pk: empresa for empresa in opcoes}
    empresa_bruta = request.GET.get("empresa", anterior.get("empresa", ""))
    automatica = False
    if not empresa_bruta or (
        "empresa" not in request.GET
        and empresa_bruta not in {"grupo", "todas"}
        and str(empresa_bruta) not in {str(pk) for pk in por_id}
    ):
        primeira = next((empresa for empresa in opcoes if empresa_elegivel(empresa, slug)), None)
        # Recusas e eventos fiscais podem existir antes do primeiro cliente.
        # Sem empresas para selecionar, a entrada Fiscal consulta o escritório
        # explicitamente como carteira, preservando os registros sem atribuição.
        empresa_bruta = str(primeira.pk) if primeira else "todas" if slug == "fiscal" else ""
        automatica = primeira is not None
    ids = []
    if empresa_bruta == "grupo":
        brutos = (
            request.GET.getlist("empresas")
            if "empresas" in request.GET
            else anterior.get("empresas", [])
        )
        if isinstance(brutos, str):
            brutos = [brutos]
        if not isinstance(brutos, list) or sum(len(str(valor)) for valor in brutos) > 10000:
            raise FiltroHomeInvalido("Selecione as empresas do grupo novamente.")
        valores = [parte for bruto in brutos for parte in str(bruto).split(",") if parte]
        ids = sorted({_id_valido(valor) for valor in valores})
        if not ids:
            raise FiltroHomeInvalido("Selecione ao menos uma empresa para o grupo.")
        if any(pk not in por_id for pk in ids):
            raise Http404
        selecionadas = [por_id[pk] for pk in ids]
    elif empresa_bruta == "todas":
        selecionadas = opcoes
        ids = list(por_id)
    elif empresa_bruta:
        pk = _id_valido(str(empresa_bruta))
        if pk not in por_id:
            raise Http404
        ids = [pk]
        selecionadas = [por_id[pk]]
    else:
        selecionadas = []
    empresas = [empresa for empresa in selecionadas if empresa_elegivel(empresa, slug)]
    escopo = EscopoHome(
        slug,
        request.escritorio,
        str(empresa_bruta),
        ids,
        empresas,
        opcoes,
        ano,
        mes,
        automatica,
        bool(selecionadas and not empresas),
    )
    _memorizar_preferencia(request, escopo)
    request._module_home_scope = escopo
    return escopo


def menu_modulos(request, empresa_atual=None):
    """URLs e permissões somente: nenhuma consulta, nome ou total global."""
    # Algumas portas legadas têm URLConf próprio em testes/integrações.
    # A moldura precisa continuar utilizável mesmo sem a inclusão das homes.
    try:
        reverse("module_home:home", args=["contabilidade"])
    except NoReverseMatch:
        return []
    papel = getattr(request, "papel", None)
    anterior = _preferencia_do_escritorio(request)
    parametros = {}
    if anterior:
        try:
            competencia_valida(anterior.get("competencia"))
        except FiltroHomeInvalido:
            pass
        else:
            parametros["competencia"] = anterior["competencia"]
        empresa = str(anterior.get("empresa", ""))
        if empresa in {"todas", "grupo"} or re.fullmatch(r"[1-9][0-9]{0,18}", empresa):
            parametros["empresa"] = empresa
        if empresa == "grupo" and isinstance(anterior.get("empresas"), list):
            parametros["empresas"] = ",".join(str(pk) for pk in anterior["empresas"])
    if empresa_atual is not None:
        parametros["empresa"] = str(empresa_atual.pk)
        parametros.pop("empresas", None)
    atual = getattr(request, "resolver_match", None)
    slug_atual = atual.kwargs.get("modulo") if atual else None
    if atual and slug_atual is None:
        slug_atual = {
            "contabilidade_web": "contabilidade",
            "fiscal_web": "fiscal",
            "livro_caixa_web": "livro-caixa",
        }.get(atual.namespace)
    return [
        {
            **modulo,
            "url": reverse("module_home:home", args=[slug])
            + (("?" + urlencode(parametros)) if parametros else ""),
            "ativo": slug == slug_atual,
            "permitido": pode_ler_modulo(papel, slug),
            "grave_count": None,
        }
        for slug, modulo in MODULOS.items()
    ]


@dataclass
class FonteFila:
    estado: str
    rotulo: str
    registros: object
    construir: object
    quantidade: int


def _lista_da_fila(fontes, estado, pagina, tamanho):
    """Pagina fontes já ordenadas, sem materializar toda a carteira.

    Os grupos seguem prioridade fixa; cada grupo ordena data, empresa e ID.
    O offset atravessa contagens no banco, buscando apenas as linhas visíveis.
    """
    selecionadas = [fonte for fonte in fontes if not estado or fonte.estado == estado]
    total = sum(fonte.quantidade for fonte in selecionadas)
    paginas = max(1, (total + tamanho - 1) // tamanho)
    if pagina > paginas:
        raise Http404
    offset = (pagina - 1) * tamanho
    restante = tamanho
    linhas = []
    for fonte in selecionadas:
        if offset >= fonte.quantidade:
            offset -= fonte.quantidade
            continue
        limite = min(restante, fonte.quantidade - offset)
        linhas.extend(
            fonte.construir(registro) for registro in fonte.registros[offset : offset + limite]
        )
        restante -= limite
        offset = 0
        if restante == 0:
            break
    return linhas, total, paginas


def _linha(
    empresa,
    objeto,
    motivo,
    referencia,
    url,
    *,
    estado,
    status="warning",
    cta="Conferir",
    historico=False,
):
    return {
        "empresa_nome": empresa.razao_social if empresa else "Empresa não identificada",
        "empresa_id": empresa.pk if empresa else None,
        "objeto": objeto,
        "motivo": motivo,
        "referencia": referencia,
        "vencimento": "Não há prazo cadastrado",
        "url": url,
        "cta": cta,
        "estado": estado,
        "status": status,
        "status_rotulo": "Histórico"
        if historico
        else {"danger": "Bloqueio", "warning": "Conferir", "muted": "Informação"}.get(
            status, "Conferir"
        ),
        "historico": historico,
    }


def _kpi(escopo, estado, numero, rotulo, status, descricao, *, status_rotulo=None):
    return {
        "estado": estado,
        "numero": numero_ptbr(numero),
        "quantidade": numero,
        "rotulo": rotulo,
        "status": status,
        "status_rotulo": status_rotulo
        or {
            "danger": "Bloqueia fechamento",
            "warning": "Conferir",
            "muted": "Informação",
            "ok": "Apurado",
        }[status],
        "descricao": descricao,
        "cta": "Ver lista",
        "url": escopo.url("pendencias", estado=estado),
    }


def _url_empresa(rota, empresa, **parametros):
    return reverse(rota, args=[empresa.pk]) + (("?" + urlencode(parametros)) if parametros else "")


def _banner(titulo, texto, status="warning", url=None, cta=None):
    return {"titulo": titulo, "texto": texto, "status": status, "url": url, "cta": cta}


def _dados_contabilidade(request, escopo):
    empresas = escopo.empresas
    por_id = {empresa.pk: empresa for empresa in empresas}
    competencias = list(
        Competencia.objects.filter(empresa__in=empresas, ano=escopo.ano, mes=escopo.mes)
    )
    por_empresa = {competencia.empresa_id: competencia for competencia in competencias}
    abertas = [
        empresa
        for empresa in empresas
        if por_empresa.get(empresa.pk)
        and por_empresa[empresa.pk].estado == EstadoCompetencia.ABERTA
    ]
    fechadas = [
        empresa
        for empresa in empresas
        if por_empresa.get(empresa.pk)
        and por_empresa[empresa.pk].estado == EstadoCompetencia.ENCERRADA
    ]
    sem_registro = [empresa for empresa in empresas if empresa.pk not in por_empresa]
    configuradas = set(
        Conta.objects.filter(empresa__in=empresas).values_list("empresa_id", flat=True).distinct()
    )
    sem_plano = [empresa for empresa in empresas if empresa.pk not in configuradas]
    lotes = localizar_lotes_desbalanceados(empresas=empresas).order_by(
        "data", "empresa__razao_social", "id"
    )
    quantidade_lotes = lotes.count()
    # A subconsulta mantém a agregação POR LOTE do serviço. Agrupar essa
    # mesma queryset diretamente por empresa poderia esconder lotes cujas
    # diferenças se anulam; o conjunto de empresas só é extraído por fora.
    com_lote = set(
        Empresa.objects.filter(pk__in=lotes.values("empresa_id")).values_list("pk", flat=True)
    )
    anteriores = (
        Competencia.objects.filter(empresa__in=empresas, estado=EstadoCompetencia.ABERTA)
        .filter(
            # Comparação lexicográfica do mês, sem inventar um vencimento legal.
            Q(ano__lt=escopo.ano) | Q(ano=escopo.ano, mes__lt=escopo.mes)
        )
        .order_by("ano", "mes", "empresa__razao_social", "id")
    )
    quantidade_anteriores = anteriores.count()
    com_anterior = set(
        Empresa.objects.filter(pk__in=anteriores.values("empresa_id")).values_list("pk", flat=True)
    )
    periodo = {"ano": escopo.ano, "mes": escopo.mes}
    fontes = [
        FonteFila(
            "lotes-desbalanceados",
            "Lotes desbalanceados",
            lotes,
            lambda lote: _linha(
                por_id[lote.empresa_id],
                f"Lançamento {lote.pk}",
                (
                    "Menos de duas partidas ou débitos e créditos diferentes. A base inteira "
                    "bloqueia o fechamento."
                ),
                f"Origem: {lote.data:%d/%m/%Y}",
                reverse("contabilidade_web:lancamento_detalhe", args=[lote.empresa_id, lote.pk]),
                estado="lotes-desbalanceados",
                status="danger",
                cta="Ver lançamento",
            ),
            quantidade_lotes,
        ),
        FonteFila(
            "competencias-anteriores",
            "Competências anteriores abertas",
            anteriores,
            lambda competencia: _linha(
                por_id[competencia.empresa_id],
                f"Competência {MESES[competencia.mes - 1]}/{competencia.ano}",
                "Competência anterior permanece aberta; não há prazo legal cadastrado.",
                f"{MESES[competencia.mes - 1]}/{competencia.ano}",
                _url_empresa("contabilidade_web:fechamento", por_id[competencia.empresa_id]),
                estado="competencias-anteriores",
                cta="Conferir fechamento",
            ),
            quantidade_anteriores,
        ),
        FonteFila(
            "competencias-abertas",
            "Empresas com competência aberta",
            abertas,
            lambda empresa: _linha(
                empresa,
                f"Competência {escopo.competencia_rotulo}",
                "Conferir origem, partidas, conciliação e relatórios antes de fechar.",
                escopo.competencia_rotulo,
                _url_empresa("contabilidade_web:fechamento", empresa),
                estado="competencias-abertas",
                cta="Conferir fechamento",
            ),
            len(abertas),
        ),
        FonteFila(
            "sem-plano",
            "Empresas sem plano de contas",
            sem_plano,
            lambda empresa: _linha(
                empresa,
                "Plano de contas",
                "Esta empresa ainda não tem contas cadastradas. A escrituração depende do plano.",
                "Cadastro atual",
                _url_empresa("contabilidade_web:plano_de_contas", empresa),
                estado="sem-plano",
                cta="Configurar plano",
            ),
            len(sem_plano),
        ),
        FonteFila(
            "sem-registro",
            "Competência sem registro",
            sem_registro,
            lambda empresa: _linha(
                empresa,
                f"Competência {escopo.competencia_rotulo}",
                (
                    "Ainda não há registro desta competência. Isso não comprova abertura nem "
                    "fechamento."
                ),
                escopo.competencia_rotulo,
                _url_empresa("contabilidade_web:fechamento", empresa),
                estado="sem-registro",
                status="muted",
                cta="Ver competências",
            ),
            len(sem_registro),
        ),
        FonteFila(
            "historico",
            "Competências encerradas",
            fechadas,
            lambda empresa: _linha(
                empresa,
                f"Competência {escopo.competencia_rotulo}",
                "Encerrada e entregue ao cliente; a reabertura está impedida."
                if por_empresa[empresa.pk].entregue_em
                else (
                    "Competência encerrada. Consulte o histórico antes de decidir por uma "
                    "reabertura."
                ),
                escopo.competencia_rotulo,
                _url_empresa("contabilidade_web:competencia_reabrir", empresa, **periodo)
                if PodeFecharCompetencia().has_permission(request, None)
                and not por_empresa[empresa.pk].entregue_em
                else _url_empresa("contabilidade_web:fechamento", empresa),
                estado="historico",
                status="muted",
                historico=True,
                cta="Reabrir"
                if PodeFecharCompetencia().has_permission(request, None)
                and not por_empresa[empresa.pk].entregue_em
                else "Ver histórico",
            ),
            len(fechadas),
        ),
    ]
    kpis = [
        _kpi(
            escopo,
            "lotes-desbalanceados",
            quantidade_lotes,
            "Lotes desbalanceados",
            "danger" if quantidade_lotes else "ok",
            "Base inteira, inclusive lançamentos de outras competências.",
        ),
        _kpi(
            escopo,
            "competencias-anteriores",
            quantidade_anteriores,
            "Competências anteriores abertas",
            "warning" if quantidade_anteriores else "ok",
            "Registros anteriores ao mês selecionado; sem vencimento legal presumido.",
        ),
        _kpi(
            escopo,
            "competencias-abertas",
            len(abertas),
            "Empresas com competência aberta",
            "warning" if abertas else "muted",
            (
                f"{numero_ptbr(len(sem_registro))} empresa(s) sem registro desta competência; "
                f"apuração de fechamento incompleta."
            )
            if sem_registro
            else "Abertura registrada na competência selecionada.",
        ),
        _kpi(
            escopo,
            "sem-plano",
            len(sem_plano),
            "Empresas sem plano de contas",
            "warning" if sem_plano else "ok",
            "Sem nenhuma conta cadastrada; contas inativas continuam sendo um plano existente.",
        ),
    ]
    motivos = {}
    for ids, motivo in (
        (com_lote, "Lote desbalanceado bloqueia o fechamento"),
        (com_anterior, "Competência anterior aberta"),
        ({empresa.pk for empresa in abertas}, "Competência selecionada aberta"),
        ({empresa.pk for empresa in sem_plano}, "Plano de contas não configurado"),
    ):
        for pk in sorted(ids, key=lambda pk: (por_id[pk].razao_social, pk)):
            motivos.setdefault(pk, motivo)
    banners = []
    if sem_registro:
        banners.append(
            _banner(
                "Fechamento ainda não apurado",
                (
                    f"{numero_ptbr(len(sem_registro))} empresa(s) sem registro para "
                    f"{escopo.competencia_rotulo}. Esta consulta não cria competências."
                ),
                url=escopo.url("pendencias", estado="sem-registro"),
                cta="Ver empresas sem registro",
            )
        )
    if fechadas:
        banners.append(
            _banner(
                "Competência encerrada"
                if len(fechadas) == len(empresas)
                else "Carteira com competências abertas e encerradas",
                (
                    f"{numero_ptbr(len(fechadas))} empresa(s) com competência encerrada. As "
                    f"entregues ao cliente não podem ser reabertas."
                ),
                status="muted",
                url=escopo.url("pendencias", estado="historico"),
                cta="Ver histórico",
            )
        )
    unica = empresas[0] if len(empresas) == 1 else None
    atalhos = []
    novos = []
    if unica:
        atalhos = [
            {"rotulo": rotulo, "url": _url_empresa(rota, unica, **params)}
            for rotulo, rota, params in (
                ("Plano de contas", "contabilidade_web:plano_de_contas", {}),
                (
                    "Conferência",
                    "contabilidade_web:conferencia",
                    {},
                ),
                (
                    "Balancete",
                    "contabilidade_web:balancete",
                    {"inicio": str(escopo.inicio), "fim": str(escopo.fim)},
                ),
                ("Fechamento", "contabilidade_web:fechamento", {}),
            )
        ]
        if PodeEscriturar().has_permission(request, None) and unica not in fechadas:
            novos = [
                {
                    "rotulo": "Novo lançamento",
                    "url": _url_empresa("contabilidade_web:lancamento_novo", unica),
                },
                {
                    "rotulo": "Nova conta",
                    "url": _url_empresa("contabilidade_web:conta_nova", unica),
                },
            ]
    return {
        "fontes": fontes,
        "kpis": kpis,
        "motivos": motivos,
        "sem_setup": {empresa.pk for empresa in sem_plano},
        "banners": banners,
        "atalhos": atalhos,
        "novos": novos,
        "estado": "competencia_fechada"
        if empresas and len(fechadas) == len(empresas)
        else "default",
        "fila_titulo": "Histórico da competência"
        if empresas and len(fechadas) == len(empresas)
        else "Fila de trabalho",
        "fila_descricao": (
            "Conferir origem → partidas → conciliação contábil → relatórios → fechar. O "
            "painel de fechamento valida os bloqueios antes da ação."
        ),
        "vazio": {
            "titulo": f"Nenhum item nesta fila para {escopo.competencia_rotulo}.",
            "texto": "Consulte as competências e os registros antes de concluir o fechamento.",
        },
    }


def _dados_fiscal(request, escopo):
    empresas = escopo.empresas
    por_id = {empresa.pk: empresa for empresa in empresas}
    # Documento usa sua competência; recepção usa data de chegada. Não
    # misturar os dois eixos nem atribuir uma recusa sem vínculo a uma
    # empresa só porque o mesmo ZIP continha um arquivo aceito dela.
    inicio = timezone.make_aware(datetime.combine(escopo.inicio, time.min))
    fim = timezone.make_aware(datetime.combine(escopo.fim, time.max))
    documentos = (
        documentos_do_escritorio(
            escopo.escritorio, competencia=(escopo.ano, escopo.mes), situacao="cancelada"
        )
        .filter(vinculos__empresa__in=empresas)
        .distinct()
    )
    eventos = (
        EventoFiscal.objects.filter(escritorio=escopo.escritorio, criado_em__range=(inicio, fim))
        .annotate(
            nota_no_acervo=Exists(
                DocumentoFiscal.objects.filter(
                    escritorio_id=OuterRef("escritorio_id"),
                    identificador=Concat(Value("NFS"), OuterRef("chave_nfse")),
                )
            )
        )
        .filter(nota_no_acervo=False)
    )
    if escopo.empresa != "todas":
        eventos = eventos.filter(empresa__in=empresas)
    eventos = eventos.defer("xml_original").order_by("criado_em", "empresa__razao_social", "id")
    total_eventos = eventos.count()
    total_documentos = documentos.count()
    kpis = []
    fontes = []
    pode_receber = papel_pode_receber_documentos(getattr(request, "papel", None))
    if escopo.empresa == "todas" and pode_receber:
        recusas = ResultadoDoArquivo.objects.filter(
            lote__escritorio=escopo.escritorio,
            lote__criado_em__range=(inicio, fim),
            resultado=TipoResultadoArquivo.RECUSADO,
        ).order_by("lote__criado_em", "id")
        total_recusas = recusas.count()
        kpis.append(
            _kpi(
                escopo,
                "arquivos-recusados",
                total_recusas,
                "Arquivos recusados",
                "warning" if total_recusas else "ok",
                (
                    f"Envios em {escopo.competencia_rotulo}; empresa e competência da nota "
                    f"não identificadas."
                ),
                status_rotulo="Ocorrência registrada",
            )
        )
        fontes.append(
            FonteFila(
                "arquivos-recusados",
                "Arquivos recusados nos envios do escritório",
                recusas.select_related("lote"),
                lambda resultado: _linha(
                    None,
                    resultado.caminho_no_zip or "Arquivo do envio",
                    resultado.motivo or "Arquivo recusado na recepção.",
                    f"Envio: {timezone.localtime(resultado.lote.criado_em):%d/%m/%Y}",
                    reverse("fiscal_web:relatorio_envio", args=[resultado.lote_id]),
                    estado="arquivos-recusados",
                    cta="Revisar ocorrência",
                ),
                total_recusas,
            )
        )
    kpis.append(
        _kpi(
            escopo,
            "eventos-sem-nota",
            total_eventos,
            "Eventos sem nota no acervo",
            "warning" if total_eventos else "ok",
            (
                f"Eventos recebidos em {escopo.competencia_rotulo}; data de recepção, não "
                f"competência da nota."
            ),
            status_rotulo="Ocorrência registrada",
        )
    )
    fontes.append(
        FonteFila(
            "eventos-sem-nota",
            "Eventos sem nota no acervo",
            eventos,
            lambda evento: _linha(
                por_id.get(evento.empresa_id),
                f"Evento {evento.codigo}",
                (
                    "A nota referenciada ainda não está no acervo. O tratamento não é "
                    "acompanhado nesta versão."
                ),
                f"Recebido: {timezone.localtime(evento.criado_em):%d/%m/%Y}",
                reverse("fiscal_web:evento_xml", args=[evento.pk]),
                estado="eventos-sem-nota",
                cta="Consultar XML",
            ),
            total_eventos,
        )
    )
    kpis.append(
        _kpi(
            escopo,
            "notas-canceladas",
            total_documentos,
            "NFS-e canceladas",
            "muted",
            (
                "Situação conhecida da nota nesta competência; cancelamento não é uma "
                "pendência aberta."
            ),
            status_rotulo="Histórico",
        )
    )
    # Prefetch só dos vínculos do escopo, sem nome da contraparte que não
    # foi selecionada. O documento original não é carregado na home.
    documentos = documentos.defer("xml_original").prefetch_related(
        Prefetch(
            "vinculos",
            queryset=VinculoDocumentoEmpresa.objects.filter(empresa__in=empresas),
            to_attr="vinculos_home",
        )
    )

    def linha_documento(documento):
        ids = sorted({vinculo.empresa_id for vinculo in documento.vinculos_home})
        empresa = por_id[ids[0]] if ids else None
        linha = _linha(
            empresa,
            f"NFS-e {documento.identificador}",
            "Cancelamento registrado por evento do mesmo escritório; consulte o documento.",
            f"Competência: {documento.d_competencia:%d/%m/%Y}",
            reverse("fiscal_web:documento_detalhe", args=[documento.pk]),
            estado="notas-canceladas",
            status="muted",
            historico=True,
            cta="Ver documento",
        )
        linha["empresa_nome"] = " · ".join(por_id[pk].razao_social for pk in ids)
        return linha

    fontes.append(
        FonteFila(
            "notas-canceladas",
            "NFS-e canceladas",
            documentos.order_by("d_competencia", "id"),
            linha_documento,
            total_documentos,
        )
    )
    banners = [
        _banner(
            "Recepção de NFS-e disponível",
            (
                "Esta versão recebe e consulta XML de NFS-e nacional. Emissão, obrigações, "
                "certificado e apuração fiscal ainda não estão disponíveis."
            ),
            "muted",
        )
    ]
    if escopo.empresa != "todas":
        banners.append(
            _banner(
                "Recusas dos envios não são atribuídas a esta seleção",
                (
                    "Um arquivo recusado não registra empresa nem competência da nota. "
                    "Consulte os envios de todas as empresas para revisar essas ocorrências."
                ),
                "muted",
                escopo.url(empresa="todas") if pode_receber else None,
                "Ver envios do escritório" if pode_receber else None,
            )
        )
    atalhos = [
        {
            "rotulo": "Documentos da competência",
            "url": reverse("fiscal_web:documentos_lista")
            + "?"
            + urlencode(
                {
                    "ano": escopo.ano,
                    "mes": escopo.mes,
                    **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                }
            ),
        }
    ]
    if escopo.empresa == "grupo" and len(empresas) > 1:
        # A lista fiscal legada admite uma empresa, não um grupo. Não
        # perder o filtro silenciosamente ao entrar por um atalho.
        atalhos[0] = {"rotulo": "Ocorrências deste grupo", "url": escopo.url("pendencias")}
    if pode_receber:
        atalhos.append({"rotulo": "Receber XML ou ZIP", "url": reverse("fiscal_web:recepcao")})
    if papel_pode_consultar_documentos(getattr(request, "papel", None)):
        # DL-072 (frente B): a lista de notas a escriturar pede UMA empresa e
        # a competência do escopo; sem empresa única, a própria tela pede a
        # escolha (nunca um filtro silencioso sobre várias empresas).
        atalhos.append(
            {
                "rotulo": "Notas a escriturar",
                "url": reverse("fiscal_web:notas_a_escriturar")
                + "?"
                + urlencode(
                    {
                        "ano": escopo.ano,
                        "mes": escopo.mes,
                        **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                    }
                ),
            }
        )
        # DL-074 (frente B): receita mensal do Simples. Mesma permissão de consulta; o
        # painel pede UMA empresa, e sem ela a própria tela pede a escolha.
        atalhos.append(
            {
                "rotulo": "Receita do mês (Simples)",
                "url": reverse("fiscal_web:receita_do_mes")
                + "?"
                + urlencode(
                    {
                        "ano": escopo.ano,
                        "mes": escopo.mes,
                        **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                    }
                ),
            }
        )
        # DL-075 (frente B): pré-DAS para conferência. Mesma permissão de consulta; a tela
        # pede UMA empresa, e sem ela a própria tela pede a escolha.
        atalhos.append(
            {
                "rotulo": "Pré-DAS do Simples (conferência)",
                "url": reverse("fiscal_web:pre_das")
                + "?"
                + urlencode(
                    {
                        "ano": escopo.ano,
                        "mes": escopo.mes,
                        **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                    }
                ),
            }
        )
        # DL-078 (frente B): serviços tomados. Mesma permissão de consulta; a tela pede UMA empresa,
        # e sem ela a própria tela pede a escolha.
        atalhos.append(
            {
                "rotulo": "Serviços tomados",
                "url": reverse("fiscal_web:tomadas_lista")
                + "?"
                + urlencode(
                    {
                        "ano": escopo.ano,
                        "mes": escopo.mes,
                        **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                    }
                ),
            }
        )
        # DL-076 (frente B): apuração do ISS próprio do município. Mesma permissão de consulta; a
        # tela pede UMA empresa, e sem ela a própria tela pede a escolha.
        atalhos.append(
            {
                "rotulo": "ISS do município (apuração)",
                "url": reverse("fiscal_web:iss_apuracao")
                + "?"
                + urlencode(
                    {
                        "ano": escopo.ano,
                        "mes": escopo.mes,
                        **({"empresa": empresas[0].pk} if len(empresas) == 1 else {}),
                    }
                ),
            }
        )
    return {
        "fontes": fontes,
        "kpis": kpis,
        "motivos": {},
        "sem_setup": set(),
        "banners": banners,
        "atalhos": atalhos,
        "novos": [],
        "estado": "default",
        "pendencias_desconhecidas": True,
        "setup_desconhecido": True,
        "fila_titulo": "Ocorrências para conferir",
        "fila_descricao": (
            "Situações registradas; o tratamento não é acompanhado nesta versão. Notas usam "
            "competência; envios e eventos usam o mês de recepção."
        ),
        "vazio": {
            "titulo": (
                f"Nenhuma ocorrência registrada nesta seleção para {escopo.competencia_rotulo}."
            ),
            "texto": (
                "A ausência de ocorrências não comprova que todas as obrigações fiscais foram "
                "cumpridas."
            ),
        },
    }


def _dados_livro_caixa(request, escopo):
    empresas = escopo.empresas
    configuradas = set(
        ContaLivroCaixa.objects.filter(empresa__in=empresas)
        .values_list("empresa_id", flat=True)
        .distinct()
    )
    sem_plano = [empresa for empresa in empresas if empresa.pk not in configuradas]
    com_movimento = set(
        LancamentoCaixa.objects.filter(
            empresa__in=empresas, data__range=(escopo.inicio, escopo.fim)
        )
        .values_list("empresa_id", flat=True)
        .distinct()
    )
    sem_movimento = [
        empresa
        for empresa in empresas
        if empresa.pk in configuradas and empresa.pk not in com_movimento
    ]
    fontes = [
        FonteFila(
            "sem-plano",
            "Clientes sem plano de contas",
            sem_plano,
            lambda empresa: _linha(
                empresa,
                "Plano de contas do livro-caixa",
                "Ainda não há contas cadastradas; configure o plano antes de lançar.",
                "Cadastro atual",
                _url_empresa("livro_caixa_web:plano_de_contas", empresa),
                estado="sem-plano",
                cta="Configurar plano",
            ),
            len(sem_plano),
        ),
        FonteFila(
            "sem-movimento",
            "Clientes sem movimento registrado",
            sem_movimento,
            lambda empresa: _linha(
                empresa,
                f"Movimentação de {escopo.competencia_rotulo}",
                (
                    "Nenhum lançamento registrado neste mês. Confira com o cliente; ausência "
                    "de movimento não prova pendência."
                ),
                escopo.competencia_rotulo,
                _url_empresa(
                    "livro_caixa_web:lancamentos",
                    empresa,
                    inicio=str(escopo.inicio),
                    fim=str(escopo.fim),
                ),
                estado="sem-movimento",
                status="muted",
                cta="Conferir movimentação",
            ),
            len(sem_movimento),
        ),
    ]
    kpis = [
        _kpi(
            escopo,
            "sem-plano",
            len(sem_plano),
            "Clientes sem plano de contas",
            "warning" if sem_plano else "ok",
            (
                "Sem nenhuma conta no livro-caixa; contas inativas não são tratadas como "
                "plano ausente."
            ),
        ),
        _kpi(
            escopo,
            "sem-movimento",
            len(sem_movimento),
            "Clientes sem movimento registrado",
            "muted",
            (
                "Clientes com plano cadastrado, sem lançamento no mês. Conferência factual, "
                "não atraso presumido."
            ),
        ),
    ]
    unica = empresas[0] if len(empresas) == 1 else None
    atalhos = (
        [
            {"rotulo": rotulo, "url": _url_empresa(rota, unica, **params)}
            for rotulo, rota, params in (
                ("Plano de contas", "livro_caixa_web:plano_de_contas", {}),
                (
                    "Lançamentos",
                    "livro_caixa_web:lancamentos",
                    {"inicio": str(escopo.inicio), "fim": str(escopo.fim)},
                ),
                (
                    "Livro Caixa",
                    "livro_caixa_web:relatorio",
                    {"inicio": str(escopo.inicio), "fim": str(escopo.fim)},
                ),
                (
                    "Arquivos do Carnê-Leão",
                    "livro_caixa_web:arquivos_carne_leao",
                    {"inicio": str(escopo.inicio), "fim": str(escopo.fim)},
                ),
            )
        ]
        if unica
        else []
    )
    novos = (
        [
            {
                "rotulo": "Novo lançamento",
                "url": _url_empresa("livro_caixa_web:lancamento_novo", unica),
            },
            {"rotulo": "Nova conta", "url": _url_empresa("livro_caixa_web:conta_nova", unica)},
        ]
        if unica and papel_pode_escriturar_livro_caixa(request.papel)
        else []
    )
    return {
        "fontes": fontes,
        "kpis": kpis,
        "motivos": {empresa.pk: "Plano de contas não configurado" for empresa in sem_plano},
        "sem_setup": {empresa.pk for empresa in sem_plano},
        "banners": [
            _banner(
                "Regime de caixa",
                (
                    "A fila usa clientes pessoa física em modo livro-caixa. Não há fechamento "
                    "de competência neste módulo; apuração e arquivos permanecem nas telas "
                    "próprias."
                ),
                "muted",
            )
        ],
        "atalhos": atalhos,
        "novos": novos,
        "estado": "default",
        "fila_titulo": "Fila de conferência",
        "fila_descricao": (
            "Configure o plano e confira a movimentação; as informações desta home não "
            "substituem a apuração do Carnê-Leão."
        ),
        "vazio": {
            "titulo": f"Nenhum item de conferência nesta seleção para {escopo.competencia_rotulo}.",
            "texto": "Consulte os lançamentos e o Livro Caixa para conferir o período.",
        },
    }


def montar_home(request, escopo, *, estado="", pagina=1, tamanho=8):
    """Monta o contrato de apresentação sem valores, arquivos XML ou efeitos contábeis."""
    modulo = {
        **MODULOS[escopo.modulo],
        "descricao": {
            "contabilidade": "Conferência e fechamento por competência",
            "fiscal": "Recepção e conferência de NFS-e nacional",
            "livro-caixa": "Conferência do livro-caixa de pessoa física",
        }.get(escopo.modulo, "Módulo ainda não disponível"),
    }
    empresas = escopo.empresas
    apura_sem_empresas = escopo.modulo == "fiscal" and escopo.empresa == "todas"
    sem_apuracao = modulo["disponibilidade"] == "indisponivel" or (
        not empresas and not apura_sem_empresas
    )
    # Listas sem fonte apurável não possuem um estado válido nem segunda
    # página. O contrato de erro independe da quantidade de clientes.
    if sem_apuracao:
        if estado:
            raise FiltroHomeInvalido("Escolha um estado disponível para este módulo e escopo.")
        if pagina != 1:
            raise Http404
    escopo_rotulo = (
        "Todas as empresas"
        if escopo.empresa == "todas"
        else f"Grupo: {len(escopo.empresas_ids)} empresa(s)"
        if escopo.empresa == "grupo"
        else empresas[0].razao_social
        if empresas
        else "Nenhuma empresa aplicável"
    )
    home = {
        "modulo": modulo,
        "filtros": {
            "empresa": escopo.empresa,
            "empresas_ids": escopo.empresas_ids,
            "competencia": escopo.competencia,
            "competencia_rotulo": escopo.competencia_rotulo,
            "competencias_opcoes": opcoes_competencia(escopo),
            "escopo_rotulo": escopo_rotulo,
            "empresas_opcoes": [
                {
                    "id": empresa.pk,
                    "nome": empresa.razao_social,
                    # O select é de escolha ÚNICA: carteira e grupo têm
                    # opções próprias. Membership dos checkboxes usa
                    # empresas_ids; marcar todos aqui estreitaria o
                    # escopo para a última empresa ao reenviar o formulário.
                    "selecionada": escopo.empresa == str(empresa.pk),
                    "elegivel": empresa_elegivel(empresa, escopo.modulo),
                }
                for empresa in escopo.opcoes
            ],
            "query": urlencode(escopo.parametros),
        },
        "estado": "default",
        "kpis": [],
        "carteira": None,
        "fila": [],
        "fila_total": 0,
        "fila_total_rotulo": "0",
        "fila_url": escopo.url("pendencias"),
        "home_url": escopo.url(),
        "atalhos": [],
        "acoes": [],
        "novos": [],
        "banners": [],
        "estado_filtro": estado,
        "estados_opcoes": [],
        "atualizado_em": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        "modulos_navigation": menu_modulos(request),
    }
    if modulo["disponibilidade"] == "indisponivel":
        home.update(
            estado="indisponivel",
            vazio={
                "titulo": f"{modulo['titulo']} ainda não está disponível.",
                "texto": (
                    "Este módulo ainda não possui operação nem apuração de pendências no "
                    "DataLedger. Escolha um módulo disponível para continuar."
                ),
            },
        )
        return home
    if not empresas and not apura_sem_empresas:
        home.update(
            estado="inaplicavel" if escopo.inaplicavel else "sem_empresas",
            vazio={
                "titulo": "Esta seleção não se aplica ao módulo."
                if escopo.inaplicavel
                else "Nenhuma empresa aplicável neste módulo.",
                "texto": (
                    "Selecione uma empresa com o modo de escrituração adequado. O escopo não "
                    "foi ampliado automaticamente."
                ),
            },
        )
        return home
    dados = {
        "contabilidade": _dados_contabilidade,
        "fiscal": _dados_fiscal,
        "livro-caixa": _dados_livro_caixa,
    }[escopo.modulo](request, escopo)
    fontes = dados.pop("fontes")
    codigos = {fonte.estado for fonte in fontes}
    if estado and estado not in codigos:
        raise FiltroHomeInvalido("Escolha um estado disponível para este módulo e escopo.")
    filtro_da_fila = estado or ("historico" if dados["estado"] == "competencia_fechada" else "")
    fila, total, paginas = _lista_da_fila(fontes, filtro_da_fila, pagina, tamanho)
    motivos = dados.pop("motivos")
    sem_setup = dados.pop("sem_setup")
    criticas = [
        {
            "nome": next(empresa.razao_social for empresa in empresas if empresa.pk == pk),
            "motivo": motivo,
            "url": escopo.url(empresa=pk),
            "cta": "Abrir empresa",
        }
        for pk, motivo in list(motivos.items())[:5]
    ]
    home.update(dados)
    home.update(
        fila=fila,
        fila_total=total,
        fila_total_rotulo=numero_ptbr(total),
        carteira={
            "cadastradas": numero_ptbr(len(empresas)),
            "ativas": numero_ptbr(sum(empresa.ativo for empresa in empresas)),
            "com_pendencia": "—"
            if dados.get("pendencias_desconhecidas")
            else numero_ptbr(len(motivos)),
            "setup_incompleto": "—"
            if dados.get("setup_desconhecido")
            else numero_ptbr(len(sem_setup)),
            "criticas": criticas,
            "descricao": (
                "Os conjuntos se sobrepõem. Ativas usa o cadastro atual, não a situação "
                "histórica. O tratamento e o setup fiscal não são acompanhados nesta versão."
            )
            if dados.get("pendencias_desconhecidas")
            else (
                "Os conjuntos se sobrepõem. Ativas usa o cadastro atual, não a situação "
                "histórica. Pendências são apenas as situações verificáveis nesta versão."
            ),
        },
        estados_opcoes=[
            {
                "codigo": fonte.estado,
                "rotulo": fonte.rotulo,
                "quantidade": fonte.quantidade,
                "quantidade_rotulo": numero_ptbr(fonte.quantidade),
            }
            for fonte in fontes
        ],
        paginacao={
            "numero": pagina,
            "total_paginas": paginas,
            "anterior_url": escopo.url("pendencias", estado=estado, pagina=pagina - 1)
            if pagina > 1
            else None,
            "proxima_url": escopo.url("pendencias", estado=estado, pagina=pagina + 1)
            if pagina < paginas
            else None,
        },
    )
    if sem_setup and home["estado"] == "default":
        home["banners"].insert(
            0,
            _banner(
                "Configuração incompleta",
                (
                    f"{numero_ptbr(len(sem_setup))} empresa(s) sem plano de contas. Configure "
                    f"o plano para iniciar a escrituração."
                ),
                url=escopo.url("pendencias", estado="sem-plano"),
                cta="Ver configuração",
            ),
        )
    if escopo.selecao_automatica:
        home["banners"].append(
            _banner(
                "Empresa selecionada",
                (
                    "A primeira empresa aplicável foi selecionada. Use o filtro para escolher "
                    "outra empresa ou a carteira."
                ),
                "muted",
            )
        )
    if home["estado"] == "default" and not total:
        home["estado"] = "vazio"
    grave = next(
        (kpi["quantidade"] for kpi in home["kpis"] if kpi["estado"] == "lotes-desbalanceados"), None
    )
    for item in home["modulos_navigation"]:
        if item["ativo"]:
            item["grave_count"] = grave
    return home


def opcoes_competencia(escopo):
    """Meses próximos em pt-BR, mantendo qualquer mês histórico selecionado."""
    hoje = timezone.localdate()
    indice_atual = hoje.year * 12 + hoje.month - 1
    indices = set(range(indice_atual - 12, indice_atual + 13))
    indices.add(escopo.ano * 12 + escopo.mes - 1)
    opcoes = []
    for indice in sorted(indices, reverse=True):
        ano, mes_zero = divmod(indice, 12)
        if 1970 <= ano <= 2999:
            valor = f"{ano:04d}-{mes_zero + 1:02d}"
            opcoes.append(
                {
                    "valor": valor,
                    "rotulo": f"{MESES[mes_zero]}/{ano}",
                    "selecionada": valor == escopo.competencia,
                }
            )
    return opcoes
