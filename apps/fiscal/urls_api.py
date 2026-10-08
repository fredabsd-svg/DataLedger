"""Rotas da API de escrituração das NFS-e prestadas (DL-072, frente A).

Montadas em `config/urls.py` sob `fiscal/api/`. Todas exigem escritório ativo
e papel autorizado; o detalhe de cada permissão está em `apps.fiscal.api`.
"""

from django.urls import path

from apps.fiscal.api import (
    ConferenciaView,
    EfetivarNotaPrestadaView,
    EstornarEscrituracaoView,
    NotasPrestadasView,
)

app_name = "fiscal_api"

urlpatterns = [
    path(
        "empresas/<int:empresa_id>/notas-prestadas/",
        NotasPrestadasView.as_view(),
        name="notas_prestadas",
    ),
    path(
        "empresas/<int:empresa_id>/notas-prestadas/<int:vinculo_id>/efetivar/",
        EfetivarNotaPrestadaView.as_view(),
        name="efetivar",
    ),
    path(
        "empresas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/estornar/",
        EstornarEscrituracaoView.as_view(),
        name="estornar",
    ),
    path(
        "empresas/<int:empresa_id>/conferencia/",
        ConferenciaView.as_view(),
        name="conferencia",
    ),
]
