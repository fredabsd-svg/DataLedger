from django.urls import path

from apps.contabilidade.views import (
    BalanceteView,
    ConferenciaLotesDesbalanceadosView,
    ContaListCreateView,
    DiarioView,
    EncerrarCompetenciaView,
    EncerrarVigenciaParametroContabilView,
    EntregarCompetenciaView,
    EstornarLancamentoView,
    LancamentoListCreateView,
    ParametrosContabeisListCreateView,
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
]
