"""Contexto de navegação global do menu e da trilha (DL-040).

Injeta, em TODA renderização de template (via `TEMPLATES[...]["OPTIONS"]
["context_processors"]`, `config/settings.py`), o que a moldura
(`templates/base.html`) precisa decidir SEM reimplementar regra de
negócio nem sem espalhar a mesma lógica por dezenas de templates:

- se o papel ativo pode ver os itens de Contabilidade/Fiscal do menu —
  reaproveitando as MESMAS funções de permissão do domínio
  (`apps.contabilidade.permissoes.papel_pode_ler_contabilidade`,
  `apps.fiscal.permissoes.papel_pode_consultar_documentos`), nunca uma
  lista nova de papéis (AGENTS.md §8/§11);
- a EMPRESA da tela atual (`empresa_atual`), derivada da própria URL
  (`request.resolver_match`), para a trilha de navegação nomear a
  empresa sem cada view precisar expor uma variável nova;
- a TRILHA padrão (`trilha_padrao`) de qualquer tela que não declare a
  sua própria (`{% block trilha %}`) — pedido do Fred na segunda rodada
  da DL-040: trilha em TODA tela autenticada abaixo de "Início", não só
  nas secundárias. Constrói-se aqui, uma vez, porque replicar esta
  lógica (namespace → módulo → empresa → rótulo da tela) em cada
  template seria exatamente a duplicação que o AGENTS.md pede para
  evitar — e o formato de saída (lista de `(rótulo, url_ou_none)`) deixa
  o template quase burro: só percorre e marca o último item como
  `aria-current`.

O menu só decide o que CONVIDA a ver; a recusa de verdade continua sendo a
do servidor em cada view (esta função nunca autoriza nada, só informa a
apresentação).

**Isolamento: `empresa_atual` nunca lista outras empresas.** Só resolve
a ÚNICA empresa que a URL atual já identifica (`empresa_id` no
`resolver_match.kwargs`, escopada ao escritório ativo) — o mesmo dado
que a própria tela já mostra em `.cabecalho__contexto`. Uma primeira
versão desta função chegou a expor a LISTA de empresas do escritório
para um seletor embutido em toda tela — e isso vazava a razão social de
OUTRA empresa na tela de uma empresa específica, medido por
`apps.contabilidade.tests.test_dl031_fechamento_de_competencia.
test_isolamento_painel_de_uma_empresa_nao_mostra_competencia_de_outra`.
Não repetir esse erro: nunca uma queryset de várias empresas aqui.
"""

from django.urls import reverse

from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.empresas.models import Empresa
from apps.empresas.views import PodeGerenciarEmpresa
from apps.fiscal.permissoes import papel_pode_consultar_documentos

# Rótulo de exibição por (namespace, url_name) — única fonte, usada pela
# trilha PADRÃO (abaixo). Rota sem entrada aqui simplesmente não ganha um
# rótulo de "tela" na trilha (o módulo ainda aparece, quando aplicável) —
# nunca um erro: rota nova, sem entrada aqui, ainda renderiza a tela
# normalmente, só sem o último degrau da trilha nomeado.
ROTULOS_DE_TELA = {
    ("empresas", "lista"): "Empresas",
    ("empresas", "criar"): "Nova empresa",
    ("contabilidade_web", "plano_de_contas"): "Plano de contas",
    ("contabilidade_web", "conta_nova"): "Nova conta",
    ("contabilidade_web", "lancamento_novo"): "Novo lançamento",
    ("contabilidade_web", "lancamento_detalhe"): "Lançamento",
    ("contabilidade_web", "diario"): "Diário",
    ("contabilidade_web", "razao"): "Razão",
    ("contabilidade_web", "balancete"): "Balancete",
    ("contabilidade_web", "balanco"): "Balanço",
    ("contabilidade_web", "conferencia"): "Conferência",
    ("contabilidade_web", "fechamento"): "Fechamento",
    ("contabilidade_web", "competencia_fechar"): "Fechar competência",
    ("contabilidade_web", "competencia_reabrir"): "Reabrir competência",
    ("contabilidade_web", "competencia_entregar"): "Marcar como entregue",
    ("fiscal_web", "recepcao"): "Recepção",
    ("fiscal_web", "relatorio_envio"): "Relatório do envio",
    ("fiscal_web", "documentos_lista"): "Documentos",
    ("fiscal_web", "documento_detalhe"): "Documento",
    ("tenancy", "bootstrap-primeiro-acesso"): "Criar escritório",
    ("tenancy", "aceitar-convite"): "Aceitar convite",
}


def _empresa_atual(request, resolver_match):
    """Resolve a empresa da URL atual, SEM consulta extra sempre que a
    view já resolveu a mesma empresa antes.

    `apps.contabilidade.views_web._empresa_do_escritorio_ativo` já
    memoriza o resultado por REQUISIÇÃO, em
    `request._dl038_cache_empresa_do_escritorio_ativo` — porque uma
    consulta a mais por requisição já estourou o teto de consultas da
    DL-015/DL-019 uma vez (ver o docstring daquela função). Este context
    processor roda DEPOIS da view (na renderização do template, com o
    MESMO objeto `request`), então o cache — quando a view já rodou —
    já está pronto para reaproveitar, sem soma nenhuma. Só cai para uma
    consulta própria quando o cache não existir (view que resolve
    `empresa_id` sem passar por aquele helper — hoje, nenhuma; defensivo
    para o futuro, nunca um 500 por cache ausente).
    """
    escritorio = getattr(request, "escritorio", None)
    empresa_id = resolver_match.kwargs.get("empresa_id")
    if empresa_id is None or escritorio is None:
        return None

    cache = getattr(request, "_dl038_cache_empresa_do_escritorio_ativo", None)
    if cache is not None and empresa_id in cache:
        return cache[empresa_id]

    return Empresa.objects.filter(pk=empresa_id, escritorio=escritorio).first()


def _trilha_padrao(resolver_match, empresa_atual):
    """Lista de `(rótulo, url_ou_None)` — `None` marca o degrau ATUAL (a
    tela nunca linka para si mesma, mesma convenção de
    `_navegacao_empresa.html`). Vazia quando a tela é o próprio "Início"
    (`tenancy:painel`) ou quando o namespace não é reconhecido (admin,
    por exemplo — não é tela do produto)."""
    namespace = resolver_match.namespace
    url_name = resolver_match.url_name
    if resolver_match.view_name == "tenancy:painel":
        return []

    rotulo_tela = ROTULOS_DE_TELA.get((namespace, url_name))
    trilha = []

    if namespace == "empresas":
        if url_name == "lista":
            trilha = [("Empresas", None)]
        elif rotulo_tela:
            trilha = [("Empresas", reverse("empresas:lista")), (rotulo_tela, None)]
    elif namespace == "contabilidade_web":
        url_plano_de_contas = (
            reverse("contabilidade_web:plano_de_contas", args=[empresa_atual.id])
            if empresa_atual
            else None
        )
        if url_name == "plano_de_contas":
            trilha.append(("Contabilidade", None))
            if empresa_atual:
                trilha.append((empresa_atual.razao_social, None))
        else:
            trilha.append(("Contabilidade", url_plano_de_contas))
            if empresa_atual:
                trilha.append((empresa_atual.razao_social, url_plano_de_contas))
            if rotulo_tela:
                trilha.append((rotulo_tela, None))
    elif namespace == "fiscal_web":
        url_recepcao = reverse("fiscal_web:recepcao")
        if url_name == "recepcao":
            trilha = [("Fiscal", None)]
        else:
            trilha.append(("Fiscal", url_recepcao))
            if rotulo_tela:
                trilha.append((rotulo_tela, None))
    elif namespace == "tenancy" and rotulo_tela:
        trilha = [(rotulo_tela, None)]

    return trilha


def navegacao_do_menu(request):
    papel = getattr(request, "papel", None)
    contexto = {
        "pode_ler_contabilidade_no_menu": papel_pode_ler_contabilidade(papel),
        "pode_consultar_fiscal_no_menu": papel_pode_consultar_documentos(papel),
        # Reaproveita a MESMA permissão DRF que `apps.empresas.views.
        # criar_empresa` já usa (`PodeGerenciarEmpresa`, definida ali) —
        # traduzida para fora do protocolo DRF com `.has_permission(request,
        # None)`, o mesmo padrão que `apps.contabilidade.views_web` já usa
        # para `PodeEscriturar`. Nunca uma segunda lista de papéis.
        "pode_cadastrar_empresa_no_menu": PodeGerenciarEmpresa().has_permission(request, None),
        "empresa_atual": None,
        "trilha_padrao": [],
    }

    usuario = getattr(request, "user", None)
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None or usuario is None or not usuario.is_authenticated:
        return contexto

    empresa_atual = _empresa_atual(request, resolver_match)
    contexto["empresa_atual"] = empresa_atual
    contexto["trilha_padrao"] = _trilha_padrao(resolver_match, empresa_atual)
    return contexto
