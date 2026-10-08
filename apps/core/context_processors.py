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

import functools
import hashlib

from django.contrib.staticfiles import finders
from django.urls import reverse

from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.empresas.models import Empresa
from apps.empresas.permissoes import papel_pode_ler_carteira
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
    # DL-077, fatia 1 (frente C): as telas do plano em arquivo. A aplicação responde
    # com a própria tela de importação quando recusa, por isso o mesmo rótulo.
    ("contabilidade_web", "plano_importar"): "Importar plano de contas",
    ("contabilidade_web", "plano_importar_aplicar"): "Importar plano de contas",
    ("contabilidade_web", "plano_exportar"): "Exportar plano de contas",
    ("contabilidade_web", "plano_modelo_excel"): "Modelo da planilha do plano",
    # DL-077, fatia 2: a conferência e o download da exportação de lançamentos.
    ("contabilidade_web", "lancamentos_exportar"): "Exportar lançamentos",
    ("contabilidade_web", "lancamentos_exportar_arquivo"): "Exportar lançamentos",
    # DL-077, fatia 3 (frente B): a importação de lançamentos com área de conferência. As ações
    # (só POST) voltam para a conferência ou para a lista, e por isso levam o mesmo rótulo.
    ("contabilidade_web", "lancamentos_importacoes"): "Importações de lançamentos",
    ("contabilidade_web", "lancamentos_importar"): "Importar lançamentos",
    ("contabilidade_web", "lancamentos_importar_modelo_excel"): "Modelo da planilha de lançamentos",
    ("contabilidade_web", "lancamentos_importacao"): "Conferência da importação",
    ("contabilidade_web", "lancamentos_importacao_depara"): "Conferência da importação",
    ("contabilidade_web", "lancamentos_importacao_avisos"): "Conferência da importação",
    ("contabilidade_web", "lancamentos_importacao_reconferir"): "Conferência da importação",
    ("contabilidade_web", "lancamentos_importacao_efetivar"): "Conferência da importação",
    ("contabilidade_web", "lancamentos_importacao_descartar"): "Conferência da importação",
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
    # B8 (rodada 1 da auditoria da DL-046): antes desta correção
    # `livro_caixa_web` não tinha NENHUMA entrada aqui — toda tela do
    # livro-caixa renderizava sem o último degrau da trilha nomeado
    # (não quebrava, só ficava incompleta: "Livro-caixa › empresa" sem
    # dizer qual tela).
    ("livro_caixa_web", "plano_de_contas"): "Plano de contas",
    ("livro_caixa_web", "conta_nova"): "Nova conta",
    ("livro_caixa_web", "lancamento_novo"): "Novo lançamento",
    ("livro_caixa_web", "lancamentos"): "Lançamentos",
    ("livro_caixa_web", "lancamento_estornar"): "Estornar lançamento",
    ("livro_caixa_web", "relatorio"): "Livro Caixa",
    ("livro_caixa_web", "fechamento_mes"): "Fechamento de mês",
    ("livro_caixa_web", "mes_encerrar"): "Encerrar mês",
    ("livro_caixa_web", "mes_reabrir"): "Reabrir mês",
    ("fiscal_web", "recepcao"): "Recepção",
    ("fiscal_web", "relatorio_envio"): "Relatório do envio",
    ("fiscal_web", "documentos_lista"): "Documentos",
    ("fiscal_web", "documento_detalhe"): "Documento",
    # DL-072 (frente B): escrituração das NFS-e prestadas.
    ("fiscal_web", "notas_a_escriturar"): "Notas a escriturar",
    ("fiscal_web", "conferencia_escrituracao"): "Conferência da escrituração",
    ("fiscal_web", "escriturar_nota"): "Escriturar nota",
    ("fiscal_web", "escrituracao_detalhe"): "Escrituração",
    ("fiscal_web", "escrituracao_estornar"): "Estornar escrituração",
    # DL-074 (frente B): receita mensal do Simples Nacional e suas telas de ação.
    ("fiscal_web", "receita_do_mes"): "Receita do mês",
    ("fiscal_web", "receita_informada_nova"): "Lançar receita informada",
    ("fiscal_web", "receita_informada_estornar"): "Estornar receita informada",
    ("fiscal_web", "receita_mes_reabrir"): "Reabrir receita do mês",
    ("fiscal_web", "regime_caixa"): "Regime de caixa (Simples)",
    # DL-075 (frente B): pré-DAS para conferência, atividades e folha para o fator r.
    ("fiscal_web", "pre_das"): "Pré-DAS do Simples",
    ("fiscal_web", "atividades"): "Atividades do Simples",
    ("fiscal_web", "atividade_nova"): "Nova atividade",
    ("fiscal_web", "atividade_editar"): "Alterar atividade",
    ("fiscal_web", "atividade_encerrar"): "Encerrar atividade",
    ("fiscal_web", "folhas_fator_r"): "Folha para o fator r",
    ("fiscal_web", "folha_nova"): "Lançar folha",
    ("fiscal_web", "folha_estornar"): "Estornar folha",
    # DL-076 (frente B): ISS por município — apuração, relatórios, alíquotas, regime e regras.
    ("fiscal_web", "iss_apuracao"): "ISS próprio (apuração)",
    ("fiscal_web", "iss_retido_sofrido"): "ISS retido sofrido",
    ("fiscal_web", "iss_outros_municipios"): "ISS devido a outros municípios",
    ("fiscal_web", "iss_aliquotas"): "Alíquotas do ISS",
    ("fiscal_web", "iss_aliquota_nova"): "Nova alíquota do ISS",
    ("fiscal_web", "iss_aliquota_editar"): "Alterar alíquota do ISS",
    ("fiscal_web", "iss_aliquota_encerrar"): "Encerrar vigência da alíquota",
    ("fiscal_web", "iss_regimes"): "Regime do ISS",
    ("fiscal_web", "iss_regime_novo"): "Novo regime do ISS",
    ("fiscal_web", "iss_regime_editar"): "Alterar regime do ISS",
    ("fiscal_web", "iss_regras_municipio"): "Regras do ISS por município",
    # DL-073: conformidade IBS/CBS das NFS-e recebidas (modo aviso).
    ("fiscal_web", "conformidade_ibscbs"): "Conformidade IBS/CBS",
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
    elif namespace == "livro_caixa_web":
        # B8: MESMO desenho de `contabilidade_web`, acima — "Livro-caixa
        # › <empresa> › <tela>", com o Plano de contas como página de
        # entrada do módulo (mesmo papel que "Contabilidade" tem para o
        # ramo de cima). Namespace SEPARADO, nunca reaproveitando o ramo
        # `contabilidade_web` por cima: os dois módulos têm rótulo de
        # entrada diferente ("Livro-caixa" vs. "Contabilidade") mesmo
        # quando o `url_name` da tela é igual (ex.: "plano_de_contas").
        url_plano_de_contas_caixa = (
            reverse("livro_caixa_web:plano_de_contas", args=[empresa_atual.id])
            if empresa_atual
            else None
        )
        if url_name == "plano_de_contas":
            trilha.append(("Livro-caixa", None))
            if empresa_atual:
                trilha.append((empresa_atual.razao_social, None))
        else:
            trilha.append(("Livro-caixa", url_plano_de_contas_caixa))
            if empresa_atual:
                trilha.append((empresa_atual.razao_social, url_plano_de_contas_caixa))
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
        # DL-055: o servidor recusa (403) o cadastro de empresas a quem não lê
        # a carteira (hoje, o CLIENTE). Esta flag só evita CONVIDAR a uma
        # tela que o usuário não pode abrir — mesma função que a API usa
        # (`apps.empresas.permissoes`), nunca uma lista de papéis no template.
        "pode_ler_carteira_no_menu": papel_pode_ler_carteira(papel),
        # Reaproveita a MESMA permissão DRF que `apps.empresas.views.
        # criar_empresa` já usa (`PodeGerenciarEmpresa`, definida ali) —
        # traduzida para fora do protocolo DRF com `.has_permission(request,
        # None)`, o mesmo padrão que `apps.contabilidade.views_web` já usa
        # para `PodeEscriturar`. Nunca uma segunda lista de papéis.
        "pode_cadastrar_empresa_no_menu": PodeGerenciarEmpresa().has_permission(request, None),
        "empresa_atual": None,
        "trilha_padrao": [],
        "modulos_home_menu": [],
    }

    usuario = getattr(request, "user", None)
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None or usuario is None or not usuario.is_authenticated:
        return contexto

    empresa_atual = _empresa_atual(request, resolver_match)
    contexto["empresa_atual"] = empresa_atual
    contexto["trilha_padrao"] = _trilha_padrao(resolver_match, empresa_atual)
    # DL-049: a troca de módulo recebe URLs e permissões, nunca a lista
    # plural de clientes ou consultas de totais nas telas globais/403.
    from apps.core.module_homes import menu_modulos

    contexto["modulos_home_menu"] = menu_modulos(request, empresa_atual)
    home = getattr(request, "_module_home_context", None)
    if home is not None:
        contexto["modulos_home_menu"] = home["modulos_navigation"]
    return contexto


@functools.lru_cache(maxsize=None)
def _impressao_digital_do_estatico(caminho_relativo):
    """Primeiros 12 caracteres do SHA-256 do CONTEÚDO do arquivo estático,
    localizado pelo mesmo finder que o `runserver` e o `collectstatic` usam.
    Calculado uma vez por processo (o arquivo não muda sem reiniciar o
    servidor, que é quando uma versão nova sobe). Arquivo não encontrado
    devolve "" — o link continua funcionando, só sem a versão.
    """
    caminho = finders.find(caminho_relativo)
    if not caminho:
        return ""
    with open(caminho, "rb") as arquivo:
        return hashlib.sha256(arquivo.read()).hexdigest()[:12]


def versao_dos_estaticos(request):
    """Versão das folhas de estilo para o link `?v=` do `<head>`.

    Achado do Fred em 2026-09-26: depois do merge da DL-044 as telas
    apareceram com a ESTRUTURA nova e a folha de estilo ANTIGA (fonte
    serifada, ícones gigantes, links sublinhados). O link é um caminho
    fixo (`/static/css/base.css`, ver o comentário em `templates/base.html`
    sobre por que não se usa a tag `static` com manifesto), então o
    navegador e qualquer cache no caminho não tinham como saber que o
    arquivo mudou. A impressão digital do conteúdo no `?v=` muda sozinha a
    cada versão nova da folha — sem depender de lembrar de trocar um
    número à mão.
    """
    return {
        "versao_css_base": _impressao_digital_do_estatico("css/base.css"),
        "versao_css_publico": _impressao_digital_do_estatico("css/public.css"),
        "versao_css_module_home": _impressao_digital_do_estatico("css/module-home.css"),
        "versao_js_module_home": _impressao_digital_do_estatico("js/module-home.js"),
    }
