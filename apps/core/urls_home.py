"""Entrada e lista da home operacional dos módulos (DL-049)."""

from django.urls import path

from apps.core.views_home import home_modulo, pendencias_modulo

app_name = "module_home"

urlpatterns = [
    path("<slug:modulo>/", home_modulo, name="home"),
    path("<slug:modulo>/pendencias/", pendencias_modulo, name="pendencias"),
]
