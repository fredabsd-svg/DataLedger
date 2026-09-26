from django.urls import path

from apps.livro_caixa.views_web import (
    conta_caixa_nova,
    lancamento_caixa_estornar,
    lancamento_caixa_novo,
    lancamentos_caixa_lista,
    livro_caixa_relatorio,
    plano_de_contas_caixa,
)

# Prefixo esperado ao costurar esta rota em config/urls.py: "livro-caixa/
# painel/" — DISTINTO de "livro-caixa/" (a API, apps.livro_caixa.urls),
# mesma razão de apps.contabilidade.urls_web (DL-017): alguns nomes de
# rota AQUI (ex.: "contas/", "lancamentos/") são iguais aos da API sob o
# MESMO empresa_id — sob o mesmo prefixo, a segunda inclusão nunca seria
# alcançada.
app_name = "livro_caixa_web"

urlpatterns = [
    path(
        "empresas/<int:empresa_id>/plano-de-contas/",
        plano_de_contas_caixa,
        name="plano_de_contas",
    ),
    path(
        "empresas/<int:empresa_id>/plano-de-contas/nova/",
        conta_caixa_nova,
        name="conta_nova",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/novo/",
        lancamento_caixa_novo,
        name="lancamento_novo",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/",
        lancamentos_caixa_lista,
        name="lancamentos",
    ),
    path(
        "empresas/<int:empresa_id>/lancamentos/<int:lancamento_id>/estornar/",
        lancamento_caixa_estornar,
        name="lancamento_estornar",
    ),
    path(
        "empresas/<int:empresa_id>/livro-caixa/",
        livro_caixa_relatorio,
        name="relatorio",
    ),
]
