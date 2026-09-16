from django.urls import path

from apps.tenancy.views import (
    EscritorioAtivoView,
    MeusEscritoriosView,
    aceitar_convite,
    ativar_escritorio,
    bootstrap_primeiro_acesso,
    emitir_convite,
    painel,
)

app_name = "tenancy"

urlpatterns = [
    path("", painel, name="painel"),
    path("ativar/", ativar_escritorio, name="ativar"),
    path("bootstrap/", bootstrap_primeiro_acesso, name="bootstrap-primeiro-acesso"),
    path("convites/emitir/", emitir_convite, name="emitir-convite"),
    path("convite/<str:token>/", aceitar_convite, name="aceitar-convite"),
    path("api/escritorios/", MeusEscritoriosView.as_view(), name="api-escritorios"),
    path(
        "api/escritorio-ativo/",
        EscritorioAtivoView.as_view(),
        name="api-escritorio-ativo",
    ),
]
