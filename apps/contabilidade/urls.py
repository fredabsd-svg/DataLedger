from django.urls import path

from apps.contabilidade.views import (
    BalanceteView,
    ConferenciaLotesDesbalanceadosView,
    ContaClassificacaoDfcView,
    ContaClassificacaoDlpaView,
    ContaClassificacaoDmplView,
    ContaClassificacaoDreView,
    ContaListCreateView,
    DeParaContaLancamentosView,
    DfcView,
    DiarioView,
    DlpaView,
    DmplView,
    DreView,
    EncerrarCompetenciaView,
    EncerrarVigenciaParametroContabilView,
    EntregarCompetenciaView,
    EstornarLancamentoView,
    ImportacaoLancamentosAvisosView,
    ImportacaoLancamentosDescartarView,
    ImportacaoLancamentosDetalheView,
    ImportacaoLancamentosEfetivarView,
    ImportacaoLancamentosListarEnviarView,
    ImportacaoLancamentosReconferirView,
    LancamentoListCreateView,
    LancamentosExportacaoView,
    MarcacaoDmplView,
    ParametrosContabeisListCreateView,
    PlanoDeContasExportacaoView,
    PlanoDeContasImportacaoAplicarView,
    PlanoDeContasImportacaoPreviaView,
    PlanoDeContasModeloExcelView,
    RazaoView,
    ReabrirCompetenciaView,
    ZerarResultadoView,
)

app_name = "contabilidade"

urlpatterns = [
    path("empresas/<int:empresa_id>/contas/", ContaListCreateView.as_view(), name="contas"),
    path(
        "empresas/<int:empresa_id>/lancamentos/",
        LancamentoListCreateView.as_view(),
        name="lancamentos",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/<int:lancamento_id>/estornar/",
        EstornarLancamentoView.as_view(),
        name="estornar",
    ),
    path("empresas/<int:empresa_id>/diario/", DiarioView.as_view(), name="diario"),
    path(
        "empresas/<int:empresa_id>/razao/<int:conta_id>/",
        RazaoView.as_view(),
        name="razao",
    ),
    path("empresas/<int:empresa_id>/balancete/", BalanceteView.as_view(), name="balancete"),
    # DL-016 fatia 1: fechamento, reabertura e entrega de competência. `ano`
    # e `mes` como segmentos próprios (não querystring) porque identificam
    # o RECURSO (a competência), não um filtro sobre uma listagem — mesmo
    # padrão de `razao/<int:conta_id>/`, acima.
    path(
        "empresas/<int:empresa_id>/competencias/<int:ano>/<int:mes>/encerrar/",
        EncerrarCompetenciaView.as_view(),
        name="encerrar-competencia",
    ),
    path(
        "empresas/<int:empresa_id>/competencias/<int:ano>/<int:mes>/reabrir/",
        ReabrirCompetenciaView.as_view(),
        name="reabrir-competencia",
    ),
    path(
        "empresas/<int:empresa_id>/competencias/<int:ano>/<int:mes>/entregar/",
        EntregarCompetenciaView.as_view(),
        name="entregar-competencia",
    ),
    path(
        "empresas/<int:empresa_id>/conferencia/lotes-desbalanceados/",
        ConferenciaLotesDesbalanceadosView.as_view(),
        name="conferencia-lotes-desbalanceados",
    ),
    # DL-043 fatia 1: parâmetro contábil por empresa, com vigência.
    path(
        "empresas/<int:empresa_id>/parametros-contabeis/",
        ParametrosContabeisListCreateView.as_view(),
        name="parametros-contabeis",
    ),
    path(
        "empresas/<int:empresa_id>/parametros-contabeis/encerrar/",
        EncerrarVigenciaParametroContabilView.as_view(),
        name="parametros-contabeis-encerrar",
    ),
    # DL-043 fatia 2: zeramento do resultado — `ano`/`mes` identificam o
    # RECURSO (o período cuja competência final é ano/mes), mesmo padrão
    # das rotas de competência acima.
    path(
        "empresas/<int:empresa_id>/zeramento/<int:ano>/<int:mes>/",
        ZerarResultadoView.as_view(),
        name="zeramento",
    ),
    # DL-045 fatia 2: Demonstração do Resultado do Exercício — `ano`/`mes`
    # identificam o RECURSO (o período cuja competência final é ano/mes),
    # mesmo padrão de `zeramento/<int:ano>/<int:mes>/`, acima.
    path(
        "empresas/<int:empresa_id>/dre/<int:ano>/<int:mes>/",
        DreView.as_view(),
        name="dre",
    ),
    # A7 (auditoria DL-045, rodada 1): porta operacional para classificar
    # (ou reclassificar, ou remover a classificação de) a linha da DRE de
    # uma conta já existente — `conta_id` identifica o RECURSO, mesmo
    # padrão de `razao/<int:conta_id>/`.
    path(
        "empresas/<int:empresa_id>/contas/<int:conta_id>/classificacao-dre/",
        ContaClassificacaoDreView.as_view(),
        name="conta-classificacao-dre",
    ),
    # DL-048 (fatia D8): porta de API da DLPA — `ano`/`mes` identificam o
    # RECURSO (o exercício até a competência pedida), mesmo padrão de
    # `dre/<int:ano>/<int:mes>/`, acima.
    path(
        "empresas/<int:empresa_id>/dlpa/<int:ano>/<int:mes>/",
        DlpaView.as_view(),
        name="dlpa",
    ),
    # DL-048 (fatia D8): classificar/reclassificar/remover a linha da DLPA de
    # uma conta existente — `conta_id` identifica o RECURSO, mesmo padrão de
    # `conta-classificacao-dre/`, acima.
    path(
        "empresas/<int:empresa_id>/contas/<int:conta_id>/classificacao-dlpa/",
        ContaClassificacaoDlpaView.as_view(),
        name="conta-classificacao-dlpa",
    ),
    # DL-061 (fatia 2, BL-605): a porta de API da DMPL — o mesmo padrão das
    # duas rotas D8 da DLPA acima. `ano`/`mes` identificam o RECURSO (o
    # exercício até a competência pedida), como em `dlpa/`.
    path(
        "empresas/<int:empresa_id>/dmpl/<int:ano>/<int:mes>/",
        DmplView.as_view(),
        name="dmpl",
    ),
    # DL-061 (fatia 2): classificar/reclassificar/remover a COLUNA da DMPL de
    # uma conta existente — espelho de `conta-classificacao-dlpa/`.
    path(
        "empresas/<int:empresa_id>/contas/<int:conta_id>/classificacao-dmpl/",
        ContaClassificacaoDmplView.as_view(),
        name="conta-classificacao-dmpl",
    ),
    # DL-066 (etapa 2): a porta de API da DFC — o mesmo padrão das rotas D8
    # das irmãs. `ano`/`mes` identificam o RECURSO (o exercício até a
    # competência pedida), como em `dmpl/`.
    path(
        "empresas/<int:empresa_id>/dfc/<int:ano>/<int:mes>/",
        DfcView.as_view(),
        name="dfc",
    ),
    # DL-066 (etapa 2): classificar/reclassificar os TRÊS campos da DFC de
    # uma conta existente — espelho de `conta-classificacao-dmpl/`, com o
    # PATCH aceitando qualquer subconjunto dos três.
    path(
        "empresas/<int:empresa_id>/contas/<int:conta_id>/classificacao-dfc/",
        ContaClassificacaoDfcView.as_view(),
        name="conta-classificacao-dfc",
    ),
    # DL-061 (fatia 2, BL-605): a marcação manual da DMPL de UM lançamento
    # (GET/PUT/DELETE — ler, substituir o conjunto, limpar). `lancamento_id`
    # identifica o RECURSO, mesmo padrão de `lancamentos/<id>/estornar/`.
    path(
        "empresas/<int:empresa_id>/lancamentos/<int:lancamento_id>/marcacao-dmpl/",
        MarcacaoDmplView.as_view(),
        name="marcacao-dmpl",
    ),
    # DL-077 (fatia 1): plano de contas em arquivo. A prévia lê e confere; a
    # aplicação grava só o que a prévia revisou; a exportação devolve o arquivo.
    path(
        "empresas/<int:empresa_id>/plano-de-contas/importacao/previa/",
        PlanoDeContasImportacaoPreviaView.as_view(),
        name="plano-importacao-previa",
    ),
    path(
        "empresas/<int:empresa_id>/plano-de-contas/importacao/aplicar/",
        PlanoDeContasImportacaoAplicarView.as_view(),
        name="plano-importacao-aplicar",
    ),
    path(
        "empresas/<int:empresa_id>/plano-de-contas/exportacao/",
        PlanoDeContasExportacaoView.as_view(),
        name="plano-exportacao",
    ),
    # DL-077, frente B (RC-167): modelo `.xlsx` para a importação por planilha. Só
    # download; a planilha preenchida volta pela prévia e pela aplicação acima.
    path(
        "empresas/<int:empresa_id>/plano-de-contas/importacao/modelo-excel/",
        PlanoDeContasModeloExcelView.as_view(),
        name="plano-modelo-excel",
    ),
    # DL-077 (fatia 2): exportação de lançamentos e saldos, com o relatório de conferência
    # nos cabeçalhos `X-DataLedger-*`. Não é a ECD (ver `intercambio/lancamentos.py`).
    path(
        "empresas/<int:empresa_id>/lancamentos/exportacao/",
        LancamentosExportacaoView.as_view(),
        name="lancamentos-exportacao",
    ),
    # DL-077 (fatia 3, frente A): importação de lançamentos com área de conferência. Nada
    # aqui grava no Diário além da efetivação (ver `intercambio/importacao_lancamentos.py`).
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/",
        ImportacaoLancamentosListarEnviarView.as_view(),
        name="lancamentos-importacao",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/<int:importacao_id>/",
        ImportacaoLancamentosDetalheView.as_view(),
        name="lancamentos-importacao-detalhe",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/<int:importacao_id>/reconferir/",
        ImportacaoLancamentosReconferirView.as_view(),
        name="lancamentos-importacao-reconferir",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/<int:importacao_id>/avisos/",
        ImportacaoLancamentosAvisosView.as_view(),
        name="lancamentos-importacao-avisos",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/<int:importacao_id>/efetivar/",
        ImportacaoLancamentosEfetivarView.as_view(),
        name="lancamentos-importacao-efetivar",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/<int:importacao_id>/descartar/",
        ImportacaoLancamentosDescartarView.as_view(),
        name="lancamentos-importacao-descartar",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/importacao/de-para/",
        DeParaContaLancamentosView.as_view(),
        name="lancamentos-importacao-de-para",
    ),
]
