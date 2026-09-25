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

from apps.fiscal.views_web import (
    documento_detalhe,
    documento_xml,
    documentos_lista,
    evento_xml,
    recepcao,
    relatorio_envio,
)

app_name = "fiscal_web"

urlpatterns = [
    path("recepcao/", recepcao, name="recepcao"),
    path("recepcao/<int:lote_id>/", relatorio_envio, name="relatorio_envio"),
    path("documentos/", documentos_lista, name="documentos_lista"),
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
]
