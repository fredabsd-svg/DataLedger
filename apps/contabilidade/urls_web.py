from django.urls import path

from apps.contabilidade.views_web import (
    balancete,
    balanco,
    competencia_entregar,
    competencia_fechar,
    competencia_reabrir,
    conferencia,
    # DL-048/CTB-12: tela irmã de `conta_classificacao_dre` — classificar
    # (ou reclassificar, ou remover) a Linha da DLPA de uma conta existente.
    conta_classificacao_dlpa,
    # DL-061/CTB-14: idem para a Coluna da DMPL (só conta de patrimônio líquido).
    conta_classificacao_dmpl,
    conta_classificacao_dre,
    conta_nova,
    diario,
    # DL-048/CTB-13: a própria demonstração.
    dlpa,
    # DL-061/CTB-14: a própria demonstração.
    dmpl,
    dre,
    fechamento,
    lancamento_detalhe,
    # DL-061, fatia 2 (BL-605): a guia "DMPL" do lançamento — grava o
    # CONJUNTO de marcações manuais (POST) e limpa com "Remover marcações";
    # GET renderiza a guia dentro do detalhe.
    lancamento_marcacao_dmpl,
    lancamento_novo,
    parametro_contabil_encerrar,
    parametros_contabeis,
    plano_de_contas,
    razao,
    relatorios,
    zeramento_do_periodo,
)

# DL-017, fase B: prefixo esperado ao costurar esta rota em config/urls.py
# é "contabilidade/painel/" — DISTINTO do prefixo "contabilidade/" já usado
# por apps.contabilidade.urls (a API). É necessário porque alguns nomes de
# rota AQUI (ex.: "diario/", "balancete/") são iguais aos da API sob o
# mesmo empresa_id: sob o MESMO prefixo, a segunda das duas inclusões
# nunca seria alcançada (o Django resolve pela ORDEM de registro, e a
# primeira que casar com o caminho "ganha" para sempre). Ver
# docs/planos/DL-017-interface-da-contabilidade.md, seção "Onde é fácil
# errar".
app_name = "contabilidade_web"

urlpatterns = [
    path(
        "empresas/<int:empresa_id>/plano-de-contas/",
        plano_de_contas,
        name="plano_de_contas",
    ),
    path(
        "empresas/<int:empresa_id>/plano-de-contas/nova/",
        conta_nova,
        name="conta_nova",
    ),
    # DL-045, correção da rodada 1 de auditoria (A7): classificar (ou
    # reclassificar, ou remover) a Linha da DRE de uma conta EXISTENTE —
    # a porta de TELA que faltava; a API já tinha `ContaClassificacaoDreView`
    # (PATCH) desde a correção do servidor. "plano-de-contas/<conta_id>/
    # classificacao-dre/" — mesmo prefixo de `conta_nova`, mesmo padrão de
    # caminho curto da API (`contas/<conta_id>/classificacao-dre/`).
    path(
        "empresas/<int:empresa_id>/plano-de-contas/<int:conta_id>/classificacao-dre/",
        conta_classificacao_dre,
        name="conta_classificacao_dre",
    ),
    path(
        "empresas/<int:empresa_id>/lancamento/novo/",
        lancamento_novo,
        name="lancamento_novo",
    ),
    path(
        "empresas/<int:empresa_id>/lancamento/<int:lancamento_id>/",
        lancamento_detalhe,
        name="lancamento_detalhe",
    ),
    # DL-061, fatia 2 (BL-605): a guia "DMPL" do lançamento. Caminho no
    # mesmo formato da API da marcação (`apps.contabilidade.urls`,
    # `empresas/<id>/lancamentos/<id>/marcacao-dmpl/`, E18) — a diferença de
    # número (`lancamentos/`, plural, contra o `lancamento/` do detalhe
    # acima) é a do pedido desta etapa; o prefixo `contabilidade/painel/`
    # já separa as duas pontas (ver o comentário no topo deste arquivo).
    path(
        "empresas/<int:empresa_id>/lancamentos/<int:lancamento_id>/marcacao-dmpl/",
        lancamento_marcacao_dmpl,
        name="lancamento_marcacao_dmpl",
    ),
    path("empresas/<int:empresa_id>/diario/", diario, name="diario"),
    path(
        "empresas/<int:empresa_id>/razao/<int:conta_id>/",
        razao,
        name="razao",
    ),
    path("empresas/<int:empresa_id>/balancete/", balancete, name="balancete"),
    # DL-034: "balanco", não "balanco-patrimonial" — mesmo padrão curto de
    # "balancete"/"diario"/"razao" já usados nesta urlconf; o nome completo
    # do documento aparece no <h1>/<title> da tela, não na URL.
    path("empresas/<int:empresa_id>/balanco/", balanco, name="balanco"),
    # DL-045 fatia 3: mesmo padrão curto de "balanco"/"balancete" acima —
    # o nome completo ("Demonstração do Resultado do Exercício") aparece
    # no <h1>/<title>, não na URL. 'ano'/'mes' viajam por querystring
    # (GET), mesmo padrão de "fechamento/" (ver `_competencia_pedida`) —
    # NUNCA no caminho da URL, porque a navegação "‹ anterior/seguinte ›"
    # muda a competência sem trocar de rota.
    path("empresas/<int:empresa_id>/dre/", dre, name="dre"),
    # DL-048/CTB-13: mesmo padrão curto de "dre"/"balanco" — o nome completo
    # ("Demonstração dos Lucros ou Prejuízos Acumulados") fica no
    # <h1>/<title>. 'ano'/'mes' viajam por querystring (GET), mesma
    # gramática da DRE — nunca no caminho da URL.
    path("empresas/<int:empresa_id>/dlpa/", dlpa, name="dlpa"),
    # DL-048/CTB-12: classificar a Linha da DLPA de uma conta existente —
    # mesmo prefixo e mesmo padrão de caminho curto da tela irmã
    # (`classificacao-dre/`, acima).
    path(
        "empresas/<int:empresa_id>/plano-de-contas/<int:conta_id>/classificacao-dlpa/",
        conta_classificacao_dlpa,
        name="conta_classificacao_dlpa",
    ),
    # DL-061/CTB-14: mesmo padrão curto de "dlpa" — o nome completo
    # ("Demonstração das Mutações do Patrimônio Líquido") fica no
    # <h1>/<title>. 'ano'/'mes' viajam por querystring (GET), mesma gramática
    # da DRE e da DLPA — nunca no caminho da URL.
    path("empresas/<int:empresa_id>/dmpl/", dmpl, name="dmpl"),
    # DL-061/CTB-14: classificar a Coluna da DMPL de uma conta existente —
    # mesmo prefixo e mesmo padrão de caminho curto das telas irmãs.
    path(
        "empresas/<int:empresa_id>/plano-de-contas/<int:conta_id>/classificacao-dmpl/",
        conta_classificacao_dmpl,
        name="conta_classificacao_dmpl",
    ),
    path("empresas/<int:empresa_id>/conferencia/", conferencia, name="conferencia"),
    # DL-044 (3ª iteração): hub de relatórios (Diário/Razão/Balancete/
    # Balanço/Conferência) em cartões — SEGUNDO caminho para as mesmas
    # cinco rotas acima, aditivo (nenhuma delas foi removida da barra
    # lateral). "relatorios/", plural, mesmo padrão curto do resto desta
    # urlconf.
    path("empresas/<int:empresa_id>/relatorios/", relatorios, name="relatorios"),
    # DL-016 fatia 1 no servidor; DL-031 é a PORTA (fatia 2 — painel e as
    # três ações de fechamento). 'ano'/'mes' viajam por querystring (GET,
    # para montar cada tela de ação) ou por campo oculto do formulário
    # (POST) — nunca no caminho da URL, para o mesmo padrão de
    # 'inicio'/'fim' do Diário/Razão/Balancete (ver _periodo_do_formulario).
    path("empresas/<int:empresa_id>/fechamento/", fechamento, name="fechamento"),
    path(
        "empresas/<int:empresa_id>/fechamento/fechar/",
        competencia_fechar,
        name="competencia_fechar",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento/reabrir/",
        competencia_reabrir,
        name="competencia_reabrir",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento/entregar/",
        competencia_entregar,
        name="competencia_entregar",
    ),
    # DL-043 fatia 3: parâmetro contábil (fatia 1) — vigência de
    # periodicidade/contas de destino do zeramento — e zeramento do
    # resultado (fatia 2). "empresas/<id>/parametros-contabeis/", não
    # "contabilidade/parametros/", pelo mesmo padrão curto do resto desta
    # urlconf; "zerar-resultado" mora sob "fechamento/" porque é ação da
    # MESMA tela de competência, disparada por ela (ver fechamento.html).
    path(
        "empresas/<int:empresa_id>/parametros-contabeis/",
        parametros_contabeis,
        name="parametros_contabeis",
    ),
    path(
        "empresas/<int:empresa_id>/parametros-contabeis/encerrar/",
        parametro_contabil_encerrar,
        name="parametro_contabil_encerrar",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento/zerar-resultado/",
        zeramento_do_periodo,
        name="zerar_resultado",
    ),
]
