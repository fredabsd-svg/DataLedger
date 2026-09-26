# DL-044 — pesquisa de referências (telas de trabalho)

Pesquisa pedida pelo Fred ("dê mais uma revisada, pesquisa e modelos da
internet") depois de reprovar o aspecto das telas de trabalho da DL-042/
DL-043 — "aspecto de vazio", "botões [...] parecendo botão de link", "muito
amador". Seis referências públicas (mínimo pedido pelo plano: cinco),
consultadas em 2026-09-26, via busca na web (skill `saas-design-excellence` +
busca direta). **Inspiração de padrão, nunca cópia de marca, texto ou
imagem** — nenhuma URL abaixo foi capturada, baixada nem reproduzida; só o
PADRÃO (estrutura, comportamento, hierarquia) foi levado para o produto, com
os próprios tokens e o próprio vocabulário visual do DataLedger.

## 1. Stripe Dashboard

**URL:** https://www.925studios.co/blog/stripe-dashboard-design-breakdown
(análise pública do padrão de dashboard da Stripe) e
https://docs.stripe.com/stripe-apps/design — **consultado em 2026-09-26**.

**Padrão observado:** densidade de DADO alta (tabela compacta), mas CASCA
generosa ao redor dela — espaçamento largo entre o cabeçalho de página, a
barra de ferramentas (busca/filtro/ação primária) e a tabela. Hierarquia
visual por TIPOGRAFIA e espaço em branco, nunca por cor (a cor fica reservada
para estado/risco). A barra de ferramentas acima da tabela concentra a ação
primária ("Add row" equivalente).

**Padrão adotado:** `.cabecalho-pagina` com linha divisória (nunca o título
flutuando solto), e o formulário de filtro/ação continua ACIMA da tabela, sem
disputar espaço com ela — já era assim no produto; o reforço desta etapa é a
BORDA que separa cabeçalho de conteúdo.

## 2. IBM Carbon Design System

**URL:** https://carbondesignsystem.com/components/button/accessibility/ e
https://carbondesignsystem.com/components/data-table/usage/ — **consultado
em 2026-09-26**.

**Padrão observado:** todo componente interativo (botão, linha de tabela)
documenta os QUATRO estados — repouso, hover, foco, desabilitado — como parte
do próprio contrato do componente, nunca como "detalhe visual opcional". A
linha de tabela tem hover sempre ativo, mesmo quando não é clicável, para
ajudar a leitura horizontal.

**Padrão adotado:** os quatro tons de `.botao` (primário/secundário/perigoso/
fantasma) e o `<button>` nativo ganharam os quatro estados explícitos —
`:hover` (sombra mais funda), `:active` (achatado, um passo abaixo), e
`:disabled`/`[aria-disabled]` (opaco, sem sombra). `:focus-visible` já
existia (regra global, critério 7 da DL-026) e não foi duplicado. `.tabela-
dados tbody tr:hover` já existia no produto — mantido, sem mudança.

## 3. Shopify Polaris

**URL:** https://polaris-react.shopify.com/components/navigation/tabs —
**consultado em 2026-09-26**.

**Padrão observado:** o componente "Tabs" é indicado especificamente para
"alternar entre visões relacionadas do MESMO contexto" — exatamente o caso de
Plano de contas/Diário/Balancete/Conferência/Fechamento de uma empresa, hoje
uma linha de links sublinhados (`_navegacao_empresa.html`). Rótulos curtos e
"scanneáveis"; a aba ATUAL se distingue por um traço de cor sob o rótulo, não
por estar sublinhada como um link comum.

**Padrão adotado:** `.navegacao-empresa` virou uma faixa de abas — a MARCAÇÃO
não mudou (nenhum `accesskey`/`aria-current`/`kbd` foi tocado, as guardas
automatizadas continuam medindo o mesmo HTML), só a CSS: padding, borda
inferior colorida no item atual, sem sublinhado nos demais.

## 4. Atlassian Design System

**URL:** https://atlassian.design/foundations/elevation e
https://atlassian.design/foundations/tokens/design-tokens — **consultado em
2026-09-26**.

**Padrão observado:** modelo de elevação em tokens (`elevation.surface.*`,
`elevation.shadow.*`) — cada NÍVEL de superfície (padrão, elevado, flutuante)
tem sombra própria, sempre como TOKEN, nunca valor solto por componente; os
estados de interação (hover/pressed) SOMAM à elevação, não a substituem.

**Padrão adotado:** dois tokens novos, `--sombra-cartao` (repouso) e
`--sombra-botao`/`--sombra-botao-hover` (interação) — mesmo princípio: o
valor mora SÓ no `:root` (regra já vigente do projeto, DL-026 §1), os
componentes só referenciam o token.

## 5. Nielsen Norman Group — usabilidade de formulário

**URL:** https://www.nngroup.com/videos/better-forms-visual-organization/ —
**consultado em 2026-09-26**.

**Padrão observado:** agrupar campos relacionados (fieldset/cartão visual)
ajuda quem preenche a entender o que pertence junto; formulário de largura
total sem agrupamento obriga o olho a "resetar" a cada campo, sem hierarquia.

**Padrão adotado:** o cabeçalho do formulário de lançamento (Data +
Histórico) ganhou um painel próprio (`.painel-etapa`), mais estreito que a
tabela de partidas — os dois campos não competem mais por uma linha inteira
de 1440px cada um.

## 6. Mercado brasileiro de gestão contábil/financeira (Conta Azul, Omie,
   Nibo)

**URL:** https://blog.bpospace.com.br/post/melhor-erp-para-bpo-financeiro-5-
dicas (comparativo independente) e https://data4company.com/contaazul —
**consultado em 2026-09-26**.

**Padrão observado** (via descrição pública, sem captura de imagem — nenhum
destes três produtos tem tela de trabalho publicamente acessível sem login
para inspeção direta): dashboards com indicador em destaque no topo (saldo,
pendência) e decisão possível "numa tela só", sem abrir módulo separado —
mesma direção que o "Início como fila de atenção" da DL-042 já tomou (cada
categoria já é acionável, não um número decorativo).

**Padrão adotado:** nenhuma mudança estrutural ao Início nesta fase (a fila
de atenção já segue esse princípio desde a DL-042) — só a superfície visual
dos cartões (`.fila-categoria`: sombra, raio maior) para os fazer ler como
PAINEL, não como texto solto.

## O que NÃO foi copiado

Nenhuma cor, ícone, texto, imagem ou nome de produto de nenhuma das seis
referências entrou no DataLedger. A tipografia nova (IBM Plex Sans) já é a
MESMA família da serifada já em uso (IBM Plex Serif, DL-026), não veio de
nenhuma das referências de pesquisa — é a continuação de uma decisão de
identidade já tomada, resolvendo o problema apontado pela pesquisa (nenhuma
referência usa serifa na casca de trabalho) com uma fonte que o produto já
tinha adotado, auto-hospedada, mesma licença já auditada.
