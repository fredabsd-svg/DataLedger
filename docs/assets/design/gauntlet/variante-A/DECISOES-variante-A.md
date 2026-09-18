# DECISOES.md — variante A, "Papel e tinta"

## Personalidade em uma frase

A interface herda a autoridade editorial do impresso — tipografia serifada
para a prosa, algarismos monoespaçados para as colunas de números, cor quase
ausente, e uma única tinta azul para ação e foco — não a estética de
software que o Domínio e o admin do Django já ocupam.

## Paleta e contraste medido

Cálculo por luminância relativa (fórmula WCAG, `L = 0,2126R+0,7152G+0,0722B`
em sRGB linearizado), script em Python, não estimativa visual. Todos os pares
usados em **texto real** ficam acima de 4,5:1; o único par abaixo disso é um
botão **desabilitado**, isento pelo próprio critério 1.4.3 do WCAG.

| Par | Uso | Contraste |
| --- | --- | --- |
| `#FAF8F3` / `#1C1A16` | Texto principal sobre papel | **16,37:1** |
| `#FAF8F3` / `#55504A` | Texto secundário (`--cor-tinta-suave`) | **7,52:1** |
| `#FAF8F3` / `#6E695F` | Texto auxiliar (`--cor-tinta-media`) sobre papel | **5,14:1** |
| `#F1EDE3` / `#6E695F` | Mesmo auxiliar sobre painel alternativo (rodapé da tabela) | **4,67:1** |
| `#FAF8F3` / `#1D3A6E` | Link / acento sobre papel | **10,51:1** |
| `#FFFFFF` / `#1D3A6E` | Texto do botão primário sobre acento | **11,15:1** |
| `#FAF8F3` / `#7A2618` | Texto de alerta sobre papel | **9,34:1** |
| `#F7E8E4` / `#7A2618` | Texto de alerta sobre fundo de alerta | **8,32:1** |
| `#FAF8F3` / `#285C3A` | Texto de sucesso sobre papel | **7,38:1** |
| `#E7EFE8` / `#285C3A` | Texto de sucesso sobre fundo de sucesso | **6,68:1** |
| `#F1EDE3` / `#1C1A16` | Texto sobre painel alternativo (cabeçalho/rodapé de tabela) | **14,86:1** |
| `#FAF8F3` / `#8A8375` | Borda funcional de campo (mínimo 3:1 exigido) | **3,54:1** |
| `#FAF8F3` / `#8A8375` | Botão **desabilitado**: texto papel sobre fundo borda-input | 3,54:1 — abaixo de 4,5:1, mas isento (WCAG 1.4.3, componente inativo) |

Pares **não usados** de propósito por ficarem abaixo do necessário: uma
"tinta-fraca" mais clara (`#7A756C`, 4,31:1) foi descartada nos primeiros
testes e substituída por `#6E695F`; nenhum texto do sistema usa a versão
descartada.

A régua de linhas entre contas (`--cor-borda-hairline`, `#D9D2C2` sobre
papel, 1,42:1) é **decorativa**, não um componente que precise dos 3:1 do
critério 1.4.11 — a separação de linhas já é redundante com o espaçamento
vertical e a mudança de peso tipográfico. Bordas que *são* componente
funcional (campo de formulário, botão de contorno) usam `--cor-borda-input`
(3,54:1) ou a própria tinta.

## Tipografia

- **`--fonte-editorial`**: `Georgia, "Iowan Old Style", "Noto Serif",
  "Liberation Serif", "Times New Roman", serif` — pilha do sistema, **sem
  arquivo de fonte**, sem licença a declarar porque nada é distribuído pelo
  projeto (R4 do brief permite explicitamente "pilha do sistema" como
  alternativa a auto-hospedar).
- **`--fonte-numerica`**: `ui-monospace, "SFMono-Regular", Menlo, Consolas,
  "Liberation Mono", "DejaVu Sans Mono", monospace` — também pilha do
  sistema. Todo código de conta, data em tabela e valor monetário usa esta
  família: a largura fixa do glifo garante tabulação de algarismos **por
  construção**, não por esperança de que o navegador suporte
  `font-variant-numeric: tabular-nums` (que também está declarado, como
  reforço, mas não é do que a interface depende).
- Escala: `11 / 12 / 13 / 14 / 16 / 20 / 28 / 36px` (`--tipo-2xs` a
  `--tipo-2xl`), todas em `rem`. Corpo de tabela em 13px (denso, mas dentro
  do que Georgia — desenhada para telas — ainda entrega com boa forma em
  x-height).

### Por que não as fontes OFL sugeridas pela pesquisa

A pesquisa de mercado recomendou Inter, IBM Plex Sans/Mono, Public Sans,
Source Sans 3 e JetBrains Mono — todas OFL, auto-hospedáveis. Nenhuma delas é
serifada; a tese "papel e tinta" depende de uma serifada para a prosa. Eu
optei por **não** embutir um arquivo de fonte (nem via `static/`, nem como
`data:` URI no próprio HTML) porque, neste ambiente, eu não tenho como buscar
o binário de uma fonte de um CDN confiável e verificar a licença exata
embutida — fazer isso às cegas seria pior que declarar honestamente a pilha
de sistema. **Registro para quem implementar em produção**: se o
`especialista-frontend` decidir por uma serifada real (ex.: alguma serifada
OFL) para reforçar a identidade em máquinas sem Georgia instalada
(principalmente Linux), o caminho é auto-hospedar em `static/fonts/` com o
arquivo de licença ao lado — o token `--fonte-editorial` já isola essa
troca para um único lugar.

## Espaçamento

Escala de 4px em `rem`: `--esp-1` a `--esp-8` = `4 / 8 / 12 / 16 / 24 / 32 /
48 / 64px`. Nenhuma medida de espaçamento solta fora da escala nos três
arquivos — inclusive o recuo hierárquico da tabela (`calc(var(--n) *
1.1rem)`) é uma fórmula, não uma medida fixa por nível, então não presume um
número máximo de níveis (achado 9 da pesquisa: um plano de contas pode ter
3 ou 6 níveis, não só 4 — a fórmula escala para qualquer profundidade sem
alterar CSS).

## Convenções contábeis aplicadas

- **Débito à esquerda, crédito à direita**, sempre — nas três tabelas
  (balancete, totais do balancete, partidas do lançamento).
- **D/C nunca sozinho como cor**: é letra, ao lado do valor, em todas as
  telas — inclusive nos exemplos de estado.
- **Parênteses para negativo**, seguindo a sugestão da pesquisa de mercado:
  usados no único saldo invertido do balancete (Banco do Brasil C/C,
  `(4.156,00) C`) e na diferença do exemplo de lançamento que não fecha
  (`(10,00)`). Não uso parênteses em todo saldo credor — isso confundiria
  D/C (que já é a informação de lado) com valor negativo (que é uma
  anomalia). Parênteses aparecem só quando o saldo é **contrário à natureza
  esperada da conta**, o gesto tipográfico correto para essa situação
  específica.
- **Conta sintética não recebe lançamento**: no balancete, isso é peso
  tipográfico + recuo, sem legenda obrigatória para entender a distinção à
  distância (peso 3 do brief). No formulário de lançamento, a mesma regra
  vira **estrutural**: o `<select>` de conta só lista contas analíticas —
  não é possível escolher uma sintética, o que é mais forte que qualquer
  aviso visual.
- **Totalizador sempre alcançável**: ver seção de arquitetura abaixo.
- **Diferença de arredondamento**: os valores desta maquete foram gerados em
  centavos inteiros (sem operação de ponto flutuante) e batem exatamente —
  não há diferença de arredondamento para mostrar. Se houvesse, o padrão
  desenhado é o mesmo da linha "Diferença" na barra de conferência: sempre
  visível, mesmo quando zero, nunca escondida por estar "batendo".

## Arquitetura da tabela densa (por que não uso `<tfoot>` fixo)

Minha primeira tentativa usou `position: sticky` diretamente em células de
`<tfoot>`. **Não funcionou**: no Chromium deste ambiente, a linha de totais
"grudava" perto do topo da tabela em vez de ficar no rodapé — o suporte de
`sticky` em `table-footer-group` é inconsistente entre navegadores e motores.
Troquei para a solução robusta e amplamente suportada: duas tabelas
**irmãs**, com o mesmo `<colgroup>` (larguras explícitas, `table-layout:
fixed`) para colunas pixel-a-pixel alinhadas — uma rola (`overflow-y: auto`,
com cabeçalho `sticky` dentro dela, esse uso *é* bem suportado), a outra
(totais) fica fora da área de rolagem, sempre visível. A moldura inteira usa
`calc(100vh - 22.5rem)`, então em qualquer altura de viewport o totalizador
termina dentro da primeira tela — não é preciso rolar a tabela inteira para
alcançá-lo (K8), e ele também é o segundo elemento de peso que o olho
encontra, logo abaixo do título (peso 3, "fecha ou não fecha").

Troca-off medido: em 1280×800 essa prioridade custa densidade inicial — só
~14 das 52 linhas cabem antes de precisar rolar a área interna da tabela
(as outras 38 continuam a um scroll de distância, sem perder o cabeçalho
nem o totalizador). Em 1920×1080 — o monitor mais realista para 6-8h de uso
diário — cabem **21 linhas visíveis** sem rolar nada, bem acima das 10
linhas do QuickBooks Online que a pesquisa citou como antipadrão medido.
Prefiro essa assimetria a esconder o totalizador em qualquer resolução.

## O que eu deliberadamente NÃO fiz, e por quê

1. **Não repliquei as colunas "débitos/créditos próprios"** que a versão
   atual do balancete tem além de "débitos/créditos" (consolidados). Isso
   estreita a tabela e mantém o foco na régua saldo→movimento→saldo, mas é
   uma **simplificação de dado real**, não só de estilo — se um contador
   precisa da distinção entre movimento próprio e consolidado no dia a dia,
   isso volta como coluna, não como decisão só minha. Fica registrado para o
   `desenvolvedor-pleno` e para o Fred confirmarem.
2. **Não linkei cada linha de conta na tabela do balancete** para um
   drill-down, como a versão atual faz. Com 50+ linhas, isso multiplicaria
   as paradas de tab por algo que a busca por código já resolve mais rápido
   para quem usa teclado o dia inteiro. Trade-off consciente de teclado
   sobre navegação por clique.
3. **Não implementei tema escuro** nem usei `light-dark()`, `:has()`,
   `@layer` ou container queries — a pesquisa apontou suporte não confirmado
   por fonte primária para vários desses recursos, e nenhum era necessário
   para as três telas pedidas. CSS deliberadamente conservador: seletores de
   classe e atributo, flexbox, grid básico, `position: sticky` só onde
   comprovadamente funciona.
4. **Não desenhei um modal de confirmação real para "Efetivar lançamento"**
   — são páginas estáticas, sem JavaScript estrutural, então não há como
   simular a abertura de um diálogo de verdade. O botão primário existe, o
   texto já é explícito ("Efetivar lançamento", não "Salvar"), e o
   `DECISOES` registra que a confirmação e a checagem de saldo batendo
   **precisam** ser reforçadas no servidor — a tela nunca é a autoridade.
5. **Não usei nenhuma fonte OFL auto-hospedada** — ver seção de tipografia.
6. **Não mostrei o estado "carregando" com qualquer animação** — é uma
   barra estática (esqueleto), porque JavaScript não pode ser estrutural e
   eu não ia fingir uma animação CSS-only que sugerisse comportamento vivo
   que a maquete não tem.
7. **Zebra em linhas de tabela**: não usei. A pesquisa apontou conflito de
   zebra forte com estados de foco/hover/seleção; a hierarquia já vem de
   peso e recuo, então listras seriam redundantes e brigariam com a tese de
   "cor quase ausente".

## Verificação feita

- **Contraste**: calculado por script Python com a fórmula de luminância
  relativa do WCAG, não estimado a olho — tabela completa acima.
- **Renderização real**: Chromium via Playwright (`PLAYWRIGHT_BROWSERS_PATH`
  deste ambiente), capturas em 1280×800 e 1920×1080 para as três telas.
  Conferido visualmente: sem rolagem horizontal em nenhuma resolução
  (`document.documentElement.scrollWidth` == `clientWidth` nas seis
  combinações testadas).
- **Teclado**: percorrido com `Tab` automatizado (Playwright) nas telas de
  balancete e lançamento — ordem de foco segue a ordem visual, nenhum foco
  ficou fora do viewport, nenhuma armadilha. Não testei leitor de tela de
  verdade (não há um disponível neste ambiente) — os `aria-label`,
  `aria-describedby`, `scope="col"`, `<caption>` e textos "somente-leitor"
  foram revisados por leitura do HTML, não ouvidos.
- **Nenhum JavaScript, nenhuma dependência externa**: confirmado por busca
  textual nos três arquivos (`<script`, `http://`, `https://`, `cdn.`,
  `fonts.googleapis` — nenhuma ocorrência).
- **Não testado**: comportamento real em Safari/Firefox (só verifiquei
  Chromium); leitor de tela real (NVDA/VoiceOver/JAWS); impressão física
  (`@media print`) — as telas não têm folha de estilo de impressão, e o
  botão "Exportar em PDF" é só a intenção de tela, sem geração real.

## Onde esta variante é mais fraca

- **Densidade em 1280×800 no balancete** fica abaixo do que um leitor
  exigente pode esperar de "25+ linhas visíveis": são ~14 sem rolar, versus
  as 52 da tabela inteira. Escolhi isso conscientemente para nunca esconder
  o totalizador, mas um avaliador que pesar densidade inicial mais que
  robustez do totalizador vai marcar isso contra.
- **Dependência de fonte serifada de sistema**: em uma máquina Linux sem
  Georgia (comum fora de Windows/macOS), a pilha cai para `Liberation
  Serif`/`DejaVu Serif` — ainda serifada, ainda com números razoáveis, mas
  com métricas um pouco mais largas; não testei como isso se comporta em
  telas mais estreitas que 1280px (fora do escopo pedido, mas é o tipo de
  coisa que só aparece em produção real).
- **O formulário de lançamento entrega só duas linhas de exemplo** no
  arquivo final. Testei à parte (cópia temporária, não incluída na entrega)
  com 8 linhas de partida para verificar se a barra de conferência fixa
  aguentaria uma tabela de partidas mais alta — funcionou: a barra continua
  presa ao fundo da viewport, a página rola normalmente por trás dela, e o
  veredito permanece visível o tempo todo. Não teste com mais que isso (por
  exemplo, 20+ linhas de um rateio grande), nem em telas menores que
  1280px.
- **Nenhum teste com leitor de tela real**, como já registrado — é a maior
  lacuna de verificação desta entrega, e eu não quero maquiar isso como
  "acessível" sem tê-lo ouvido de verdade.
