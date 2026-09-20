from django.urls import path

from apps.contabilidade.views_web import (
    balancete,
    competencia_entregar,
    competencia_fechar,
    competencia_reabrir,
    conferencia,
    conta_nova,
    diario,
    fechamento,
    lancamento_detalhe,
    lancamento_novo,
    plano_de_contas,
    razao,
)

# DL-017, fase B: prefixo esperado ao costurar esta rota em config/urls.py
# é "contabilidade/painel/" — DISTINTO do prefixo "contabilidade/" já usado
# por apps.contabilidade.urls (a API). É necessário porque alguns nomes de
# rota AQUI (ex.: "diario/", "balancete/") são iguais aos da API sob o
# mesmo empresa_id: sob o MESMO prefixo, a segunda das duas inclusões
# nunca seria alcançada (o Django resolve pela ORDEM de registro, e a
# primeira que casar com o caminho "ganha" para sempre). Ver
# docs/planos/DL-017-interface-da-contabilidade.md, seção "Onde é fácil
# errar".
app_name = "contabilidade_web"

urlpatterns = [
    path(
        "empresas/<int:empresa_id>/plano-de-contas/",
        plano_de_contas,
        name="plano_de_contas",
    ),
    path(
        "empresas/<int:empresa_id>/plano-de-contas/nova/",
        conta_nova,
        name="conta_nova",
    ),
    path(
        "empresas/<int:empresa_id>/lancamento/novo/",
        lancamento_novo,
        name="lancamento_novo",
    ),
    path(
        "empresas/<int:empresa_id>/lancamento/<int:lancamento_id>/",
        lancamento_detalhe,
        name="lancamento_detalhe",
    ),
    path("empresas/<int:empresa_id>/diario/", diario, name="diario"),
    path(
        "empresas/<int:empresa_id>/razao/<int:conta_id>/",
        razao,
        name="razao",
    ),
    path("empresas/<int:empresa_id>/balancete/", balancete, name="balancete"),
    path("empresas/<int:empresa_id>/conferencia/", conferencia, name="conferencia"),
    # DL-016 fatia 1 no servidor; DL-031 é a PORTA (fatia 2 — painel e as
    # três ações de fechamento). 'ano'/'mes' viajam por querystring (GET,
    # para montar cada tela de ação) ou por campo oculto do formulário
    # (POST) — nunca no caminho da URL, para o mesmo padrão de
    # 'inicio'/'fim' do Diário/Razão/Balancete (ver _periodo_do_formulario).
    path("empresas/<int:empresa_id>/fechamento/", fechamento, name="fechamento"),
    path(
        "empresas/<int:empresa_id>/fechamento/fechar/",
        competencia_fechar,
        name="competencia_fechar",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento/reabrir/",
        competencia_reabrir,
        name="competencia_reabrir",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento/entregar/",
        competencia_entregar,
        name="competencia_entregar",
    ),
]
