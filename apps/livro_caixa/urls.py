from django.urls import path

from apps.livro_caixa.views import (
    CarneLeaoAnualView,
    CarneLeaoMensalView,
    ContaLivroCaixaListCreateView,
    DependentesCarneLeaoListCreateView,
    EstornarLancamentoCaixaView,
    LancamentoCaixaListCreateView,
    LivroCaixaView,
)

app_name = "livro_caixa"

urlpatterns = [
    path(
        "empresas/<int:empresa_id>/contas/",
        ContaLivroCaixaListCreateView.as_view(),
        name="contas",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/",
        LancamentoCaixaListCreateView.as_view(),
        name="lancamentos",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/<int:lancamento_id>/estornar/",
        EstornarLancamentoCaixaView.as_view(),
        name="estornar",
    ),
    path(
        "empresas/<int:empresa_id>/livro-caixa/",
        LivroCaixaView.as_view(),
        name="livro-caixa",
    ),
    # DL-046, fatia 2 — carnê-leão.
    path(
        "empresas/<int:empresa_id>/dependentes-carne-leao/",
        DependentesCarneLeaoListCreateView.as_view(),
        name="dependentes-carne-leao",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/mensal/",
        CarneLeaoMensalView.as_view(),
        name="carne-leao-mensal",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/anual/",
        CarneLeaoAnualView.as_view(),
        name="carne-leao-anual",
    ),
]
