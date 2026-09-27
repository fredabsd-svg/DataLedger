from django.urls import path

from apps.livro_caixa.views import (
    ContaLivroCaixaListCreateView,
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
]
