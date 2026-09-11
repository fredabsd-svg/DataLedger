from django.urls import path

from apps.tenancy.views import (
    EscritorioAtivoView,
    MeusEscritoriosView,
    ativar_escritorio,
    painel,
)

app_name = "tenancy"

urlpatterns = [
    path("", painel, name="painel"),
    path("ativar/", ativar_escritorio, name="ativar"),
    path("api/escritorios/", MeusEscritoriosView.as_view(), name="api-escritorios"),
    path(
        "api/escritorio-ativo/",
        EscritorioAtivoView.as_view(),
        name="api-escritorio-ativo",
    ),
]
