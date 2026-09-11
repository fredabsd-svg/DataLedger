from django.urls import path

from apps.empresas.views import (
    EmpresaDetailView,
    EmpresaListCreateView,
    EstabelecimentoListCreateView,
    HistoricoRegimeTributarioListCreateView,
    criar_empresa,
    lista_empresas,
)

app_name = "empresas"

urlpatterns = [
    path("", lista_empresas, name="lista"),
    path("nova/", criar_empresa, name="criar"),
    path("api/empresas/", EmpresaListCreateView.as_view(), name="api-lista"),
    path("api/empresas/<int:pk>/", EmpresaDetailView.as_view(), name="api-detalhe"),
    path(
        "api/empresas/<int:empresa_id>/estabelecimentos/",
        EstabelecimentoListCreateView.as_view(),
        name="api-estabelecimentos",
    ),
    path(
        "api/empresas/<int:empresa_id>/regime-tributario/",
        HistoricoRegimeTributarioListCreateView.as_view(),
        name="api-regime-tributario",
    ),
]
