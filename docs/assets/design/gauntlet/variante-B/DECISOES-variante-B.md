# Decisões — Variante B, "instrumento de precisão"

## Personalidade em uma frase

Um instrumento de contabilidade de alta frequência — denso, previsível e
operável de cabo a rabo pelo teclado — que continua legível e confiável no
segundo em que o Fred vira a tela para o cliente.

## Contraste medido (fórmula WCAG de luminância relativa, script `contraste.py`)

Todos os pares abaixo foram calculados, não estimados a olho. Texto exige
≥4,5:1; borda/UI exige ≥3:1. Nenhum par ficou abaixo do limite.

**Tema claro** — texto principal/fundo 16,31:1 · texto secundário/fundo
8,04:1 · texto/painel branco 17,79:1 · acento (link/botão)/branco 7,61:1 ·
texto sobre botão primário 7,61:1 · âmbar-crédito/branco 5,93:1 ·
azul-débito/branco 7,61:1 · erro/branco 7,19:1 · erro/faixa-erro 9,02:1 ·
sucesso/faixa-sucesso 7,12:1 · borda de componente/branco 3,09:1 ·
placeholder/campo 4,83:1.

**Tema escuro** — texto principal/fundo 15,02:1 · texto secundário/fundo
8,28:1 · texto/painel 13,89:1 · acento/painel 7,73:1 · texto sobre botão
primário 8,56:1 · âmbar-crédito/painel 8,68:1 · azul-débito/painel 7,73:1 ·
erro/painel 7,40:1 · erro/faixa-erro 9,59:1 · sucesso/faixa-sucesso 9,04:1 ·
borda de componente/painel 3,15:1 (a primeira tentativa, `#4b525f`, deu
2,15:1 — reprovada e trocada por `#636b7a` antes de fechar o arquivo) ·
placeholder/campo 5,76:1.

O foco de teclado usa contorno de 2px na cor de acento **fora** do
elemento (`outline-offset` positivo) mais um halo na cor do fundo do
painel — porque um contorno para *dentro* de um botão do segmento já
selecionado (fundo azul) ficava da mesma cor do próprio fundo e
desaparecia. Encontrei isso testando Tab de verdade no Chromium, não
inspecionando o CSS: o script `_tmp` que usei tabulou o documento inteiro e
fotografou cada parada — recomendo esse método a quem revisar.

## Paleta e por que não é vermelho/verde

D é azul (`#0b4fb0` claro / `#7db1ff` escuro), C é âmbar
(`#8a5a00` / `#e3b341`) — nenhum dos dois depende do eixo
vermelho-verde, o mais afetado por deuteranopia (~8% dos homens). Vermelho
e verde ficam reservados só para erro e sucesso, nunca para D/C, e mesmo
ali o texto e um ícone (✕/✓) sempre acompanham a cor — a régua deste
projeto proíbe cor como único canal e eu segui à risca. Não rodei um
simulador de daltonismo de verdade (tipo Coblis); a escolha é informada
pela literatura, não testada com ferramenta — registro a diferença.

## Tipografia

Texto corrido: pilha do sistema (`-apple-system, Segoe UI, Roboto...`) —
zero licença, zero download, sempre disponível. Números e código de conta:
**JetBrains Mono** (SIL Open Font License 1.1), auto-hospedada em
`fontes/JetBrainsMono-Regular.ttf` e `-Bold.ttf`, com `JetBrainsMono-OFL.txt`
copiado junto. Não converti para `.woff2` — não havia ferramenta de
conversão disponível sem passo de build nesta entrega; em produção,
`fonttools` reduziria os ~115KB por peso. `font-variant-numeric:
tabular-nums` fica como reforço defensivo mesmo com fonte monoespaçada.

Escala (`rem`, não trava o zoom do navegador): xs 11px, sm 13px (padrão da
tabela), base 14px, md 16px, lg 19px (título de tela), xl 24px (marca).

## Espaçamento

Base 4px: 2 · 4 · 8 · 12 · 16 · 24 · 32 · 48px (`--esp-1` a `--esp-8`).
Nenhuma medida solta fora dessas variáveis nas três telas.

## Densidade — número medido, não prometido

Em 1280×800, sem rolar nada, o balancete mostra cabeçalho do app, contexto
de empresa/período, navegação, filtros, o resumo "fecha/não fecha" **e
15 a 17 linhas de conta** (variei a régua de medição duas vezes durante o
ajuste; o script que conta via `getBoundingClientRect` está em
`_tmp` do processo de build, não entregue). O rodapé de total é sticky
dentro da própria caixa de rolagem da tabela — está sempre visível, mesmo
rolando as 44 contas, sem depender de JS.

## O que fiz diferente do pedido literal, e por quê

Removi as colunas "Débitos/Créditos próprios" do desenho original. Eu
cheguei nelas por eliminação: conta sintética nunca tem valor próprio (por
definição — regra do domínio), então a coluna é sempre "—"; conta
analítica não tem filhos, então "próprio" é sempre igual ao "total". As
duas colunas extras não carregavam informação nenhuma além do que o
marcador Σ/• já mostra. O rodapé soma só as 4 contas de nível 1
("Ativo, Passivo, Receitas, Despesas") — elas particionam todas as
folhas sem sobreposição, então o total bate sem contar nada em dobro, e eu
não preciso da coluna redundante para provar isso.

## Sem `light-dark()`, `:has()`, `@layer`, container queries, subgrid

Nenhum confirmado por fonte primária nesta rodada — usei só
`@media (prefers-color-scheme: dark)` trocando variáveis em `:root`, que é
suporte antigo e testado. Zebra forte também ficou de fora: listras fortes
brigam com foco/seleção/hover, que são estados que esta direção usa muito;
troquei por borda inferior sutil e reservei contraste forte para hover,
seleção de linha (`tr:focus-within`) e foco.

## O que deliberadamente NÃO fiz

- **Zero JavaScript**, em qualquer um dos três arquivos. "Enter avança
  para a próxima linha" e recálculo ao vivo do total ficaram de fora —
  isso exigiria script estrutural. Em vez disso mostrei os dois estados
  (fecha / não fecha) como duas respostas estáticas do servidor, que é
  como o Django realmente devolveria a página depois de um POST.
- **Não travei o plano de contas em 4 níveis.** O nível vem da contagem
  de segmentos do código (`--nivel` calculado por linha), não de um enum
  fixo. Os botões de filtro de nível (1 a 4, nesta empresa) são os níveis
  que existem nos dados de exemplo — numa empresa com 3 ou 6 o servidor
  geraria outra quantidade de botões.
- Não implementei drill-down de conta, Diário, Plano de contas nem
  Empresas — fora do escopo dos 3 arquivos pedidos; os links existem,
  focáveis, apontando para "#".
- Não testei com leitor de tela real (NVDA/VoiceOver) — só inspecionei
  semântica (`label`, `scope`, `aria-current`, `aria-invalid`,
  `role="alert/status"`, `sr-only`) e ordem de tabulação via automação.
- Exportação leva a marca do Escritório Demonstração, não do DataLedger
  (texto ao lado do botão Exportar) — resposta direta ao achado de mercado
  sobre concorrente que carimba o fornecedor em vez do escritório; não há
  exportação de verdade nesta entrega, é só o texto de intenção.

## Onde esta variante é fraca

- A ajuda do campo de data (explicando que o formato é do navegador) fez
  a barra de filtros do balancete crescer para duas linhas — para uma
  tela que se vende pela densidade, isso é uma concessão que eu faria
  diferente com mais tempo (tooltip via `aria-describedby` em vez de texto
  sempre visível).
- Busca nativa do navegador (Ctrl+F) não é garantida dentro da caixa de
  rolagem interna da tabela em todos os navegadores — é uma tensão real
  entre "tabela contida e elegante" e "tudo pesquisável nativamente" que
  não resolvi.
- Trocar "D/C + Valor" por duas colunas "Débito/Crédito" no lançamento é
  mais fiel à convenção do domínio, mas quem vem do Domínio (sistema
  legado, um campo de valor + tipo) tem meio segundo de estranhamento até
  entender o padrão nesta tela — mitigado pela legenda, não eliminado.
- Dados fictícios (Padaria Aurora) não foram revisados por um contador
  quanto a plausibilidade fiscal completa; servem ao layout, não a uma
  auditoria de regra tributária.
