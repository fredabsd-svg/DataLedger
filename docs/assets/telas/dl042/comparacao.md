# DL-042 — telas antes e depois do redesenho global

Capturas para o Fred aprovar a DL-042 antes da integração. Dados sintéticos
(escritório, empresa, 73 contas/60 lançamentos de
`scripts/semear_base_de_medicao.py`, e documentos fiscais sintéticos de
`apps/fiscal/tests/xml_sinteticos.py` — nenhum dado real), Chromium,
26/09/2026. **Antes** é a versão da DL-040 já integrada (commit `41b28f2`,
ponto de partida desta etapa) — não recapturado na 2ª passada, por pedido do
arquiteto-senior ("antes continua o de 41b28f2"). **Depois** é a proposta da
DL-042 completa (2ª passada), recapturada depois de:

1. Moldura em "L invertido": barra SUPERIOR da DL-040 vira barra LATERAL
   esquerda, recolhível para ícones (raciocínio completo em
   [direção de arte §8](../../../projeto/direcao-de-arte.md) e
   [mapa de telas, "Revisão DL-042"](../../../projeto/mapa-de-telas.md)).
2. Landing, login e cadastro redesenhados pela referência `fluxos-saas.md`
   da skill — ver a seção própria ao fim (não são mais pixel-idênticas ao
   "antes": a 1ª passada desta etapa tinha deixado essas três telas de
   fora por engano, corrigido nesta rodada).
3. "Início" como fila do que precisa de atenção (painel) — visível na
   captura do Painel, abaixo.
4. Botões e cabeçalho de página padronizados em toda tela do mapa (achados
   e correções no diagnóstico, mapa-de-telas.md).
5. Distância do título a 390×844 recuperada para ≤230px sem esconder
   empresa/período (visível nas capturas de celular do Balancete/Diário/
   Plano de contas).

## Painel (Início)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_1440x900.png) | ![Depois](depois_painel_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_390x844.png) | ![Depois](depois_painel_390x844.png) |

## Lista de empresas

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_empresas_lista_1440x900.png) | ![Depois](depois_empresas_lista_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_empresas_lista_390x844.png) | ![Depois](depois_empresas_lista_390x844.png) |

## Nova empresa

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_empresa_nova_1440x900.png) | ![Depois](depois_empresa_nova_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_empresa_nova_390x844.png) | ![Depois](depois_empresa_nova_390x844.png) |

## Plano de contas

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_plano_de_contas_1440x900.png) | ![Depois](depois_plano_de_contas_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_plano_de_contas_390x844.png) | ![Depois](depois_plano_de_contas_390x844.png) |

## Novo lançamento

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_1440x900.png) | ![Depois](depois_lancamento_novo_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_390x844.png) | ![Depois](depois_lancamento_novo_390x844.png) |

## Diário

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_diario_1440x900.png) | ![Depois](depois_diario_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_diario_390x844.png) | ![Depois](depois_diario_390x844.png) |

## Razão

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_razao_1440x900.png) | ![Depois](depois_razao_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_razao_390x844.png) | ![Depois](depois_razao_390x844.png) |

## Balancete

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balancete_1440x900.png) | ![Depois](depois_balancete_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balancete_390x844.png) | ![Depois](depois_balancete_390x844.png) |

## Balanço Patrimonial

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balanco_1440x900.png) | ![Depois](depois_balanco_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balanco_390x844.png) | ![Depois](depois_balanco_390x844.png) |

## Fechamento

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fechamento_1440x900.png) | ![Depois](depois_fechamento_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fechamento_390x844.png) | ![Depois](depois_fechamento_390x844.png) |

## Recepção fiscal

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_recepcao_1440x900.png) | ![Depois](depois_fiscal_recepcao_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_recepcao_390x844.png) | ![Depois](depois_fiscal_recepcao_390x844.png) |

## Documentos fiscais (lista)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_documentos_lista_1440x900.png) | ![Depois](depois_fiscal_documentos_lista_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_documentos_lista_390x844.png) | ![Depois](depois_fiscal_documentos_lista_390x844.png) |

## Detalhe do documento fiscal

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_documento_detalhe_1440x900.png) | ![Depois](depois_fiscal_documento_detalhe_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_fiscal_documento_detalhe_390x844.png) | ![Depois](depois_fiscal_documento_detalhe_390x844.png) |

## Landing

Reescrita completa pela referência `fluxos-saas.md`: proposta em 5 segundos
(o que o DataLedger faz HOJE), uma ação primária ("Configurar meu
ambiente") mais a secundária ("Entrar"), captura REAL do Balancete no
herói (nunca ilustração abstrata), seção "O que já funciona hoje", grade
de módulos com selo Disponível/Planejado, seção "Concebido para IA" com
assistente/MCP marcados Planejados, e FAQ nativa. Paleta "papel e tinta" —
igual à do produto autenticado — no lugar do painel escuro decorativo da
DL-034/037.

Computador (1440 × 900):

| Antes (DL-040/041, não redesenhada) | Depois (DL-042) |
| --- | --- |
| ![Antes](antes_landing_1440x900.png) | ![Depois](depois_landing_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_landing_390x844.png) | ![Depois](depois_landing_390x844.png) |

## Login

Cartão único centralizado sobre o fundo "papel" do produto, no lugar do
painel escuro decorativo — preserva o link para cadastro e o texto "Criar
ambiente para meu escritório" (contrato de
`apps/accounts/tests/test_signup.py`).

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_login_1440x900.png) | ![Depois](depois_login_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_login_390x844.png) | ![Depois](depois_login_390x844.png) |

## Cadastro

Mesmo cartão único; o formulário continua percorrendo
`form.visible_fields` sem hardcodar campo — nenhuma mudança de contrato.

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_cadastro_1440x900.png) | ![Depois](depois_cadastro_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_cadastro_390x844.png) | ![Depois](depois_cadastro_390x844.png) |
