"""Rotas da API de escrituração das NFS-e prestadas (DL-072, frente A).

Montadas em `config/urls.py` sob `fiscal/api/`. Todas exigem escritório ativo
e papel autorizado; o detalhe de cada permissão está em `apps.fiscal.api`.
"""

from django.urls import path

from apps.fiscal.api import (
    ConferenciaView,
    ConfirmarMesView,
    ConfirmarReceitaInformadaView,
    EfetivarNotaPrestadaView,
    EstornarEscrituracaoView,
    EstornarReceitaInformadaView,
    NotasPrestadasView,
    Rbt12View,
    ReabrirMesView,
    ReceitaDoMesView,
    ReceitasInformadasView,
    RegimeCaixaView,
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
    # DL-074 (frente A): receita mensal, confirmação, receita informada, RBT12.
    path(
        "empresas/<int:empresa_id>/receita/",
        ReceitaDoMesView.as_view(),
        name="receita_do_mes",
    ),
    path(
        "empresas/<int:empresa_id>/receita/confirmar/",
        ConfirmarMesView.as_view(),
        name="confirmar_mes",
    ),
    path(
        "empresas/<int:empresa_id>/receita/reabrir/",
        ReabrirMesView.as_view(),
        name="reabrir_mes",
    ),
    path(
        "empresas/<int:empresa_id>/receitas-informadas/",
        ReceitasInformadasView.as_view(),
        name="receitas_informadas",
    ),
    path(
        "empresas/<int:empresa_id>/receitas-informadas/<int:receita_id>/confirmar/",
        ConfirmarReceitaInformadaView.as_view(),
        name="confirmar_receita_informada",
    ),
    path(
        "empresas/<int:empresa_id>/receitas-informadas/<int:receita_id>/estornar/",
        EstornarReceitaInformadaView.as_view(),
        name="estornar_receita_informada",
    ),
    path(
        "empresas/<int:empresa_id>/rbt12/",
        Rbt12View.as_view(),
        name="rbt12",
    ),
    path(
        "empresas/<int:empresa_id>/regime-caixa/",
        RegimeCaixaView.as_view(),
        name="regime_caixa",
    ),
]
