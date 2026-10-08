"""Rotas das telas de recepção e conferência de documentos fiscais (DL-010,
fatia 1, etapa 2 — `especialista-frontend`).

Molde: `apps.contabilidade.urls_web` (DL-017, fase B) — mesmo padrão de
`app_name` próprio (para `reverse("fiscal_web:...")` nunca colidir com
outro namespace) e de views de FUNÇÃO, não baseadas em classe.

Prefixo escolhido no plano (docs/planos/DL-010-F1-recepcao-nfse.md):
"fiscal/", costurado em `config/urls.py`. Diferente da contabilidade, o
Fiscal NÃO tem uma API REST desta fatia (declarado fora do escopo no
plano) — não existe colisão de caminho a evitar aqui, mas o padrão de
`app_name` próprio é mantido mesmo assim, por consistência com o resto do
produto (DE-053: "um sistema contábil que muda de cara a cada módulo
obriga o usuário a reaprender").
"""

from django.urls import path

from apps.fiscal.views_conformidade import conformidade_ibscbs
from apps.fiscal.views_web import (
    atividade_editar,
    atividade_encerrar,
    atividade_nova,
    atividades,
    conferencia_escrituracao,
    documento_detalhe,
    documento_xml,
    documentos_lista,
    escrituracao_detalhe,
    escrituracao_estornar,
    escriturar_nota,
    evento_xml,
    folha_confirmar,
    folha_estornar,
    folha_nova,
    folhas_fator_r,
    notas_a_escriturar,
    pre_das,
    receita_do_mes,
    receita_informada_confirmar,
    receita_informada_estornar,
    receita_informada_nova,
    receita_mes_confirmar,
    receita_mes_reabrir,
    recepcao,
    regime_caixa,
    relatorio_envio,
)

app_name = "fiscal_web"

urlpatterns = [
    path("recepcao/", recepcao, name="recepcao"),
    path("recepcao/<int:lote_id>/", relatorio_envio, name="relatorio_envio"),
    path("documentos/", documentos_lista, name="documentos_lista"),
    path("conformidade/", conformidade_ibscbs, name="conformidade_ibscbs"),
    path("documentos/<int:documento_id>/", documento_detalhe, name="documento_detalhe"),
    # Download do XML original (critério 29): rota PRÓPRIA, sem overlap com
    # a de detalhe — o Content-Type de resposta é application/xml, nunca
    # HTML, então não pode ser uma variação por querystring da mesma rota
    # (um crawler ou um link direto precisa reconhecer, pela própria URL,
    # que aquilo é um anexo).
    path("documentos/<int:documento_id>/xml/", documento_xml, name="documento_xml"),
    # Idem para o XML de um evento (critério 29, "idem para evento, se
    # oferecer" — plano da etapa) — mesmo motivo: o evento também guarda o
    # XML original byte a byte (DE-074 item 1) e o detalhe do documento
    # (`documento_detalhe`) lista os eventos com link para este download.
    path("eventos/<int:evento_id>/xml/", evento_xml, name="evento_xml"),
    # DL-072 (frente B): escrituração das NFS-e prestadas. A lista é por
    # querystring (`?empresa=&ano=&mes=`) porque o menu do módulo não conhece
    # uma empresa; as telas de UMA nota ou de UMA escrituração levam a empresa
    # no caminho, e o vínculo/a escrituração é buscado DENTRO dela (404 fora).
    path("escrituracao/", notas_a_escriturar, name="notas_a_escriturar"),
    path(
        "escrituracao/conferencia/",
        conferencia_escrituracao,
        name="conferencia_escrituracao",
    ),
    path(
        "escrituracao/empresas/<int:empresa_id>/notas/<int:vinculo_id>/",
        escriturar_nota,
        name="escriturar_nota",
    ),
    path(
        "escrituracao/empresas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/",
        escrituracao_detalhe,
        name="escrituracao_detalhe",
    ),
    path(
        "escrituracao/empresas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/estornar/",
        escrituracao_estornar,
        name="escrituracao_estornar",
    ),
    # DL-074 (frente B): receita mensal do Simples Nacional. Mesmo critério das rotas
    # da DL-072: o painel leva empresa e competência na querystring; as ações levam a
    # empresa no caminho, e o mês/a receita são buscados DENTRO dela (404 fora).
    path("simples/receita/", receita_do_mes, name="receita_do_mes"),
    path(
        "simples/empresas/<int:empresa_id>/competencias/<int:ano>/<int:mes>/confirmar/",
        receita_mes_confirmar,
        name="receita_mes_confirmar",
    ),
    path(
        "simples/empresas/<int:empresa_id>/competencias/<int:ano>/<int:mes>/reabrir/",
        receita_mes_reabrir,
        name="receita_mes_reabrir",
    ),
    path(
        "simples/empresas/<int:empresa_id>/receitas/nova/",
        receita_informada_nova,
        name="receita_informada_nova",
    ),
    path(
        "simples/empresas/<int:empresa_id>/receitas/<int:receita_id>/confirmar/",
        receita_informada_confirmar,
        name="receita_informada_confirmar",
    ),
    path(
        "simples/empresas/<int:empresa_id>/receitas/<int:receita_id>/estornar/",
        receita_informada_estornar,
        name="receita_informada_estornar",
    ),
    path(
        "simples/empresas/<int:empresa_id>/regime-caixa/",
        regime_caixa,
        name="regime_caixa",
    ),
    # DL-075 (frente B): pré-DAS para conferência, atividades da empresa e folha para o fator
    # r. Mesmo critério das rotas da DL-074: a tela de consulta leva a empresa na querystring
    # (`?empresa=`), e as ações levam a empresa no caminho, com o registro buscado DENTRO dela.
    path("simples/pre-das/", pre_das, name="pre_das"),
    path("simples/atividades/", atividades, name="atividades"),
    path(
        "simples/empresas/<int:empresa_id>/atividades/nova/",
        atividade_nova,
        name="atividade_nova",
    ),
    path(
        "simples/empresas/<int:empresa_id>/atividades/<int:atividade_id>/",
        atividade_editar,
        name="atividade_editar",
    ),
    path(
        "simples/empresas/<int:empresa_id>/atividades/<int:atividade_id>/encerrar/",
        atividade_encerrar,
        name="atividade_encerrar",
    ),
    path("simples/folha/", folhas_fator_r, name="folhas_fator_r"),
    path(
        "simples/empresas/<int:empresa_id>/folha/nova/",
        folha_nova,
        name="folha_nova",
    ),
    path(
        "simples/empresas/<int:empresa_id>/folha/<int:folha_id>/confirmar/",
        folha_confirmar,
        name="folha_confirmar",
    ),
    path(
        "simples/empresas/<int:empresa_id>/folha/<int:folha_id>/estornar/",
        folha_estornar,
        name="folha_estornar",
    ),
]
