from django.urls import path

from apps.empresas.views import (
    EmpresaDetailView,
    EmpresaListCreateView,
    EstabelecimentoListCreateView,
    HistoricoRegimeTributarioDetailView,
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
    # BL-209 (RC-86/DE-039): exclusão do ÚLTIMO período de regime tributário,
    # o caminho de correção que faltava (achado R6-6 — sem ele, um dígito
    # errado em `vigencia_inicio` congelava o histórico para sempre).
    path(
        "api/empresas/<int:empresa_id>/regime-tributario/<int:registro_id>/",
        HistoricoRegimeTributarioDetailView.as_view(),
        name="api-regime-tributario-detalhe",
    ),
]
