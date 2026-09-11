from django.urls import path

from apps.contabilidade.views import (
    BalanceteView,
    ContaListCreateView,
    EstornarLancamentoView,
    LancamentoListCreateView,
    RazaoView,
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
    path(
        "empresas/<int:empresa_id>/razao/<int:conta_id>/",
        RazaoView.as_view(),
        name="razao",
    ),
    path("empresas/<int:empresa_id>/balancete/", BalanceteView.as_view(), name="balancete"),
]
