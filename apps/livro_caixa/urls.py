from django.urls import path

from apps.livro_caixa.views import (
    ArquivoCarneLeaoPagamentosDownloadView,
    ArquivoCarneLeaoRendimentosDownloadView,
    ArquivosCarneLeaoPendenciasView,
    CarneLeaoAnualView,
    CarneLeaoMensalView,
    ContaLivroCaixaListCreateView,
    DependentesCarneLeaoListCreateView,
    DependentesCarneLeaoRetificarView,
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
        "empresas/<int:empresa_id>/dependentes-carne-leao/<int:dependente_id>/",
        DependentesCarneLeaoRetificarView.as_view(),
        name="dependentes-carne-leao-retificar",
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
    # DL-046, fatia 3 — arquivos de importação do Carnê-Leão Web (RC-127).
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/pendencias/",
        ArquivosCarneLeaoPendenciasView.as_view(),
        name="carne-leao-arquivos-pendencias",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/rendimentos/",
        ArquivoCarneLeaoRendimentosDownloadView.as_view(),
        name="carne-leao-arquivo-rendimentos",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/pagamentos/",
        ArquivoCarneLeaoPagamentosDownloadView.as_view(),
        name="carne-leao-arquivo-pagamentos",
    ),
]
