from django.urls import path

from apps.auditoria.views import RegistroAuditoriaListView

app_name = "auditoria"

urlpatterns = [
    path("", RegistroAuditoriaListView.as_view(), name="api-lista"),
]
