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
    iss_aliquota_editar,
    iss_aliquota_encerrar,
    iss_aliquota_nova,
    iss_aliquotas,
    iss_apuracao,
    iss_outros_municipios,
    iss_regime_editar,
    iss_regime_novo,
    iss_regimes,
    iss_regras_municipio,
    iss_retido_a_recolher,
    iss_retido_sofrido,
    nfe_a_escriturar,
    nfe_conferencia,
    nfe_detalhe,
    nfe_escriturar,
    nfe_estornar,
    nfe_eventos_orfaos,
    nfe_recebidas,
    nfe_reclassificar,
    notas_a_escriturar,
    pre_das,
    presumido_apuracao,
    presumido_atividade_encerrar,
    presumido_atividade_nova,
    presumido_atividades,
    presumido_criterio,
    presumido_criterio_gravar,
    presumido_integrais_declarar,
    presumido_limite,
    presumido_medida_nova,
    presumido_medida_revogar,
    presumido_medidas,
    presumido_receita_estornar,
    presumido_receita_nova,
    presumido_receitas,
    presumido_retencao_confirmar,
    presumido_retencoes,
    receita_do_mes,
    receita_informada_confirmar,
    receita_informada_estornar,
    receita_informada_nova,
    receita_mes_confirmar,
    receita_mes_reabrir,
    recepcao,
    regime_caixa,
    relatorio_envio,
    retencoes_federais,
    tomada_data_pagamento,
    tomada_data_pagamento_limpar,
    tomada_escriturar,
    tomada_estornar,
    tomadas_lista,
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
    # DL-080 (frente B): NF-e e NFC-e recebidas, só leitura. A lista pede a empresa na querystring
    # (`?empresa=`), como Serviços tomados. O detalhe leva a empresa no caminho e busca a nota
    # DENTRO do vínculo com ela (404 fora). Eventos sem nota é por escritório, com filtro opcional
    # de empresa.
    path("nfe/", nfe_recebidas, name="nfe_recebidas"),
    path("nfe/eventos-sem-nota/", nfe_eventos_orfaos, name="nfe_eventos_orfaos"),
    path(
        "nfe/empresas/<int:empresa_id>/notas/<int:documento_id>/",
        nfe_detalhe,
        name="nfe_detalhe",
    ),
    # DL-081 (frente B): escrituração das NF-e de saída e da devolução de venda. A lista, a
    # conferência e a reclassificação pedem a empresa na querystring ou no formulário (sem
    # empresa, a tela pede a escolha). A escrituração de UMA nota e o estorno levam a empresa no
    # caminho, e a nota ou a escrituração é buscada DENTRO dela (404 fora, IDOR).
    path("nfe/escrituracao/", nfe_a_escriturar, name="nfe_a_escriturar"),
    path("nfe/escrituracao/conferencia/", nfe_conferencia, name="nfe_conferencia"),
    path("nfe/escrituracao/reclassificar/", nfe_reclassificar, name="nfe_reclassificar"),
    path(
        "nfe/escrituracao/empresas/<int:empresa_id>/notas/<int:vinculo_id>/",
        nfe_escriturar,
        name="nfe_escriturar",
    ),
    path(
        "nfe/escrituracao/empresas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/estornar/",
        nfe_estornar,
        name="nfe_estornar",
    ),
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
    # DL-076 (frente B): ISS por município. A apuração e os relatórios levam a empresa na
    # querystring (mesmo critério das telas do Simples); alíquota é do escritório ativo, e o
    # regime leva a empresa no caminho, com o registro buscado DENTRO dela (404 fora).
    path("iss/apuracao/", iss_apuracao, name="iss_apuracao"),
    path("iss/retido-sofrido/", iss_retido_sofrido, name="iss_retido_sofrido"),
    path("iss/outros-municipios/", iss_outros_municipios, name="iss_outros_municipios"),
    path("iss/aliquotas/", iss_aliquotas, name="iss_aliquotas"),
    path("iss/aliquotas/nova/", iss_aliquota_nova, name="iss_aliquota_nova"),
    path("iss/aliquotas/<int:aliquota_id>/", iss_aliquota_editar, name="iss_aliquota_editar"),
    path(
        "iss/aliquotas/<int:aliquota_id>/encerrar/",
        iss_aliquota_encerrar,
        name="iss_aliquota_encerrar",
    ),
    path("iss/regimes/", iss_regimes, name="iss_regimes"),
    path(
        "iss/empresas/<int:empresa_id>/regimes/nova/",
        iss_regime_novo,
        name="iss_regime_novo",
    ),
    path(
        "iss/empresas/<int:empresa_id>/regimes/<int:regime_id>/",
        iss_regime_editar,
        name="iss_regime_editar",
    ),
    path("iss/regras-municipio/", iss_regras_municipio, name="iss_regras_municipio"),
    # DL-078 (frente B): serviços TOMADOS. Escriturar, ISS retido a recolher e retenções federais.
    path("tomadas/", tomadas_lista, name="tomadas_lista"),
    path("tomadas/iss-retido/", iss_retido_a_recolher, name="iss_retido_a_recolher"),
    path("tomadas/retencoes-federais/", retencoes_federais, name="retencoes_federais"),
    path(
        "tomadas/<int:empresa_id>/<int:vinculo_id>/",
        tomada_escriturar,
        name="tomada_escriturar",
    ),
    path(
        "tomadas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/estornar/",
        tomada_estornar,
        name="tomada_estornar",
    ),
    path(
        "tomadas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/data-pagamento/",
        tomada_data_pagamento,
        name="tomada_data_pagamento",
    ),
    path(
        "tomadas/<int:empresa_id>/escrituracoes/<int:escrituracao_id>/data-pagamento/limpar/",
        tomada_data_pagamento_limpar,
        name="tomada_data_pagamento_limpar",
    ),
    # DL-079 (frente B): Lucro Presumido, IRPJ e CSLL. Consulta por ?empresa= (como o Simples);
    # cadastro, confirmação, estorno e revogação com a empresa no caminho.
    path("presumido/atividades/", presumido_atividades, name="presumido_atividades"),
    path("presumido/criterio/", presumido_criterio, name="presumido_criterio"),
    path("presumido/receitas/", presumido_receitas, name="presumido_receitas"),
    path("presumido/retencoes/", presumido_retencoes, name="presumido_retencoes"),
    path("presumido/medidas/", presumido_medidas, name="presumido_medidas"),
    path("presumido/apuracao/", presumido_apuracao, name="presumido_apuracao"),
    path("presumido/limite/", presumido_limite, name="presumido_limite"),
    path(
        "presumido/empresas/<int:empresa_id>/atividades/nova/",
        presumido_atividade_nova,
        name="presumido_atividade_nova",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/atividades/<int:atividade_id>/encerrar/",
        presumido_atividade_encerrar,
        name="presumido_atividade_encerrar",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/criterio/",
        presumido_criterio_gravar,
        name="presumido_criterio_gravar",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/receitas/nova/",
        presumido_receita_nova,
        name="presumido_receita_nova",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/receitas/<int:receita_id>/estornar/",
        presumido_receita_estornar,
        name="presumido_receita_estornar",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/integrais/",
        presumido_integrais_declarar,
        name="presumido_integrais_declarar",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/retencoes/<int:escrituracao_id>/confirmar/",
        presumido_retencao_confirmar,
        name="presumido_retencao_confirmar",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/medidas/nova/",
        presumido_medida_nova,
        name="presumido_medida_nova",
    ),
    path(
        "presumido/empresas/<int:empresa_id>/medidas/<int:medida_id>/revogar/",
        presumido_medida_revogar,
        name="presumido_medida_revogar",
    ),
]
