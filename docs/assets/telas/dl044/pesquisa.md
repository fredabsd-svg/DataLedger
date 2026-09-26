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

## 7. Conta Azul — referência ESCOLHIDA PELO FRED (2026-09-26)

Depois da primeira rodada de correções (itens 1-6, acima), o Fred viu as
capturas "depois" e definiu uma referência PRÓPRIA: "Gosto do visual do
Conta Azul [...] não é para fazer igual, apenas um modelo". Quatro imagens
enviadas por ele (upload local, `/root/.claude/uploads/.../*.{gif,png,jpg}`)
foram inspecionadas com a ferramenta de leitura — **não copiadas para o
repositório**, por serem tela de produto de terceiro: painel inicial,
"Contas a receber" com submenu aberto, portal do contador, e uma versão mais
antiga com barra superior. Consulta adicional à Central de Ajuda oficial
(busca web, **2026-09-26**):

- https://ajuda.contaazul.com/hc/pt-br/articles/36995310423565-Dashboard-da-Conta-Azul-Mais-vis%C3%B5es-dispon%C3%ADveis
- https://ajuda.contaazul.com/hc/pt-br/articles/115007759147-Vis%C3%A3o-geral
- https://ajuda.contaazul.com/hc/pt-br/articles/15695093299853-Lan%C3%A7amentos-financeiros-como-filtrar-o-que-est%C3%A1-em-aberto
- https://contaazul.com/funcionalidades/gestao-financeira/

**Padrão observado** (estrutura e comportamento, nunca a marca): barra
lateral em azul sólido, texto branco, ícone + rótulo, seta de submenu; ao
entrar num módulo, o item ativo ganha destaque com fundo mais claro dentro
da própria barra. Cabeçalho branco com o título da tela grande à esquerda
e a identificação do usuário/conta num "chip" arredondado à direita — nunca
uma faixa de texto solta. Fundo cinza-azulado claro por trás de cartões
BRANCOS com sombra suave — o cartão é a unidade visual, não a página
inteira. Faixa de indicadores com números grandes no topo do painel
financeiro, cada um levando à lista filtrada correspondente. Barra de ações
da tela com UM botão preenchido (a ação primária) e os demais em contorno.
Tabela com cabeçalho claro, linha espaçada, valor à direita, selo de
situação, ação por linha num botão pequeno de contorno, rodapé com total.

**Padrão adotado** (com tokens e cores PRÓPRIOS — nunca o hex do Conta
Azul, nunca o logotipo nem texto de interface deles):

- Azul de aplicativo próprio (`--app-acento`, `#0A58CA` — 6,44:1 sobre
  branco, contraste calculado, script em scratchpad desta etapa),
  substituindo o azul-marinho editorial (`--acento-escuro`) como fundo da
  barra lateral e dos botões primários DENTRO do app logado. `--acento`
  original (editorial, mais escuro) continua reservado a link de prosa,
  foco padrão fora da barra e a TODO o site público/landing — por
  instrução explícita do Fred, "a landing [...] pode manter a identidade
  atual; a casca do app muda". As duas escalas nunca aparecem na MESMA
  superfície (direção de arte §1, "uma tinta de acento só" — lida aqui
  como "por superfície": landing e documento impresso são uma identidade,
  o app logado é outra, e cada uma usa só a sua).
- Fundo cinza-azulado claro (`--app-fundo`, `#E3E9F2`) atrás da área de
  conteúdo (`.area-principal`) do app — cartões continuam BRANCOS
  (`--papel-elevado`, já existente), a diferença de tom é só o suficiente
  para o cartão se destacar (1,22:1 fundo×branco — não é par sujeito a
  mínimo de contraste do WCAG, é separação decorativa de superfície,
  igual à distinção `--papel`/`--papel-elevado` que o produto já usava).
- `.cabecalho-pagina` virou CARTÃO branco com sombra (era só uma borda
  inferior sobre o mesmo fundo do restante da página) — mesmo módulo
  visual que `.painel-etapa`/`.tabela-dados` já usavam.
- Faixa de indicadores do Início (`.indicadores-do-painel`, construída
  nesta mesma iteração para o retorno anterior do Fred) já seguia este
  padrão antes de ele nomear o Conta Azul como referência — mantida.
- Hub de Relatórios (Diário/Razão/Balancete/Balanço/Conferência) em
  cartões grandes com ícone, nome e ação "Abrir" — troca do "botão que
  parece link" que o Fred apontou como amador pelo mesmo tipo de cartão
  clicável do painel inicial do Conta Azul, com o VOCABULÁRIO deste
  produto (Diário/Razão/Balancete/Balanço/Conferência, não "vendas" nem
  "financeiro").
- "Chip"/pílula para a identificação de escritório/usuário no topo
  (`.cabecalho__contexto`), no lugar da faixa de texto em caixa-alta.

**O que NÃO foi adotado, e por quê:** o trilho de ícones + painel de
segundo nível mais escuro (imagem "Contas a receber", submenu aberto) não
entrou — o produto já tinha um menu em acordeão (`<details>`/`<summary>`,
sem JavaScript, testado e com guarda de acessibilidade própria) que
resolve o MESMO problema (navegar dentro de um módulo) com uma estrutura
já validada; trocar de arquitetura de navegação inteira, nesta rodada,
trocaria risco de regressão por ganho estético incerto — decisão registrada
para o arquiteto-senior avaliar como fatia separada, se ele concordar que
vale o risco. A fonte (Nunito Sans/Inter, sugerida como alternativa) NÃO
foi trocada — decisão registrada e justificada na seção seguinte.

## O que NÃO foi copiado

Nenhuma cor, ícone, texto, imagem ou nome de produto de nenhuma das sete
referências entrou no DataLedger — inclusive o azul do Conta Azul (item 7):
o hex adotado (`--app-acento`) é OUTRO, calculado e verificado por
contraste, nunca o do produto de referência. A tipografia nova (IBM Plex
Sans) já é a MESMA família da serifada já em uso (IBM Plex Serif, DL-026),
não veio de nenhuma das referências de pesquisa — é a continuação de uma
decisão de identidade já tomada, resolvendo o problema apontado pela
pesquisa (nenhuma referência usa serifa na casca de trabalho) com uma fonte
que o produto já tinha adotado, auto-hospedada, mesma licença já auditada.

**Decisão sobre a fonte, pedida pelo Fred na 3ª rodada:** avaliada a troca
para Nunito Sans/Inter (as duas OFL, auto-hospedáveis, mais "arredondadas"
que a Plex Sans). Decisão: MANTER IBM Plex Sans. Razão: o Fred nunca citou
a fonte como problema em nenhuma das três rodadas de retorno ("vazio",
"botão parece link", "tudo junto", "arcaico", "cartões brancos", "cor
cinza-azulada" — nenhuma menção a tipografia); a Plex Sans já está
integrada, licenciada e auditada (@font-face, OFL.txt verificado por
`strings` no binário) nesta mesma etapa; trocar a fonte de novo, sem pedido
específico, gastaria o orçamento desta rodada em risco de licenciamento e
integração por um ganho estético não pedido, enquanto cor/fundo/navegação
(que ELE pediu) ainda precisavam de todo o tempo disponível. Registrado
aqui para o arquiteto-senior decidir se vale uma fatia própria.
