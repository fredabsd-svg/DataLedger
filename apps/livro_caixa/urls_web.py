from django.urls import path

from apps.livro_caixa.views_web import (
    arquivo_pagamentos_carne_leao,
    arquivo_rendimentos_carne_leao,
    arquivos_carne_leao,
    carne_leao_anual,
    carne_leao_mensal,
    conta_caixa_nova,
    dependentes_carne_leao,
    dependentes_carne_leao_retificar,
    fechamento_mes_caixa,
    lancamento_caixa_estornar,
    lancamento_caixa_novo,
    lancamentos_caixa_lista,
    livro_caixa_relatorio,
    mes_caixa_encerrar,
    mes_caixa_reabrir,
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
    # DL-046, fatia 2 — carnê-leão. "carne-leao/" (mensal) antes de
    # "carne-leao/anual/" e "carne-leao/dependentes/": os dois sufixos
    # não colidem com nenhum outro padrão aqui (mesma ordem que as outras
    # rotas deste arquivo já seguem, sem exigir cuidado extra).
    path(
        "empresas/<int:empresa_id>/carne-leao/",
        carne_leao_mensal,
        name="carne_leao_mensal",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/anual/",
        carne_leao_anual,
        name="carne_leao_anual",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/dependentes/",
        dependentes_carne_leao,
        name="dependentes_carne_leao",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/dependentes/<int:dependente_id>/retificar/",
        dependentes_carne_leao_retificar,
        name="dependentes_carne_leao_retificar",
    ),
    # DL-046, fatia 3 (RC-127) — arquivos de importação do Carnê-Leão Web.
    # "carne-leao/arquivos/" e os dois sufixos dele ("rendimentos/",
    # "pagamentos/") não colidem com "carne-leao/anual/" nem com
    # "carne-leao/dependentes/": são prefixos distintos, e o Django casa
    # cada padrão com o caminho INTEIRO (a rota de download nunca cai na
    # da tela, nem o contrário).
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/",
        arquivos_carne_leao,
        name="arquivos_carne_leao",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/rendimentos/",
        arquivo_rendimentos_carne_leao,
        name="arquivo_rendimentos",
    ),
    path(
        "empresas/<int:empresa_id>/carne-leao/arquivos/pagamentos/",
        arquivo_pagamentos_carne_leao,
        name="arquivo_pagamentos",
    ),
    # DL-053 — fechamento de mês do livro-caixa. O painel lê "?ano=" e as duas
    # telas de ação leem "ano"/"mes" (querystring no GET, campos ocultos no
    # POST), mesmo desenho do fechamento de competência da contabilidade.
    path(
        "empresas/<int:empresa_id>/fechamento-de-mes/",
        fechamento_mes_caixa,
        name="fechamento_mes",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento-de-mes/encerrar/",
        mes_caixa_encerrar,
        name="mes_encerrar",
    ),
    path(
        "empresas/<int:empresa_id>/fechamento-de-mes/reabrir/",
        mes_caixa_reabrir,
        name="mes_reabrir",
    ),
]
