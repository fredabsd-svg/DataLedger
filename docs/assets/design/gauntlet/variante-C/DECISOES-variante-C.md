# DECISÕES — Variante C — "Confiança de banco"

## Personalidade em uma frase

Uma moldura escura e imóvel (grafite quase preto, nunca azul) segura uma folha
clara e densa de números alinhados — a sensação de abrir o cofre de um
escritório sério, não o painel de um SaaS.

## Paleta e contraste medido (fórmula WCAG relativa de luminância, calculada à mão em Python, não estimada)

Cor institucional própria: **grafite quente** (`#1C221C`, quase preto com
leve matiz verde) para a moldura fixa (topo + barra lateral), e **bronze**
(`#8A5A24`) como único acento de ação — a cor que carrega decisão (botão
primário, link, item de navegação ativo). Nenhuma das duas é o azul-corporativo
que o brief pediu para evitar; o grafite evoca cofre/couro, o bronze evoca
metal de banco físico, sem repetir o clichê "verde = dinheiro" nem o
vermelho/verde que a pesquisa já sinalizou como armadilha.

| Par (texto sobre fundo) | Contraste | Exigência | OK? |
| --- | --- | --- | --- |
| `#1B1F1A` texto sobre `#EDEAE2` fundo (papel) | 13,89:1 | 4,5:1 | sim |
| `#1B1F1A` texto sobre `#FFFFFF` painel | 16,70:1 | 4,5:1 | sim |
| `#1B1F1A` texto sobre `#F6F4EF` painel-alt | 15,19:1 | 4,5:1 | sim |
| `#52564C` texto secundário sobre fundo | 6,25:1 | 4,5:1 | sim |
| `#52564C` texto secundário sobre painel | 7,52:1 | 4,5:1 | sim |
| `#F5F3EC` texto invertido sobre `#1C221C` institucional | 14,61:1 | 4,5:1 | sim |
| `#C9C4B3` texto invertido secundário sobre institucional | 9,29:1 | 4,5:1 | sim |
| `#C9C4B3` sobre `#262E24` institucional-2 (item ativo) | 8,03:1 | 4,5:1 | sim |
| `#8A5A24` bronze (link) sobre painel branco | 5,88:1 | 4,5:1 | sim |
| `#8A5A24` bronze sobre fundo papel | 4,89:1 | 4,5:1 | sim |
| Branco sobre `#8A5A24` (botão primário) | 5,88:1 | 4,5:1 | sim |
| Branco sobre `#6E4419` (botão primário :hover) | 8,39:1 | 4,5:1 | sim |
| `#1B1F1A` sobre `#F0E3CC` acento-suave (linha selecionada/hover) | 13,17:1 | 4,5:1 | sim |
| `#8A2A20` erro-texto sobre `#FBEAE6` erro-fundo | 7,40:1 | 4,5:1 | sim |
| `#1E5E3B` sucesso-texto sobre `#E6F2EA` sucesso-fundo | 6,71:1 | 4,5:1 | sim |
| `#7A5A10` aviso-texto sobre `#FAF0D6` aviso-fundo | 5,61:1 | 4,5:1 | sim |
| Branco sobre `#1E5E3B` (selo "Fecha") | 7,72:1 | 4,5:1 | sim |
| Branco sobre `#B23B2B` (selo "Não fecha") | 5,91:1 | 4,5:1 | sim |

Descoberta durante o trabalho, registrada por honestidade: a primeira versão
usava `#3F8F62` (verde mais claro) como fundo sólido do selo "Fecha" com texto
branco — dava **3,95:1**, abaixo de 4,5:1. Troquei o fundo sólido para
`#1E5E3B` (o mesmo tom já usado como `--cor-sucesso-texto`) e voltou a passar
(7,72:1). Fica como prova de que os números acima foram calculados de verdade,
não copiados de um design system genérico.

**Bordas de componente (exigência ≥3:1, não 4,5:1):**

| Par | Contraste | OK? |
| --- | --- | --- |
| `#6E6656` borda-interativa (campo, botão) vs painel branco | 5,68:1 | sim |
| `#6E6656` vs fundo papel | 4,72:1 | sim |
| `#1B1F1A` anel de foco vs painel/fundo | 16,70:1 / 13,89:1 | sim |
| `#F5F3EC` anel de foco (sobre moldura escura) vs institucional | 14,61:1 | sim |
| `#B23B2B` borda do alerta de erro vs seu próprio fundo | 5,07:1 | sim |
| `#3F8F62` borda do alerta de sucesso vs seu próprio fundo | 3,43:1 | sim |

**Não medido / decorativo, dito com todas as letras:** a borda fina interna
dos selos D/C (`--cor-acento-suave-borda` sobre `--cor-acento-suave`, ~1,5:1)
não atinge 3:1. Não conserto isso fingindo que não vi: deixei porque essa
borda é puro acabamento — quem identifica o selo é o texto "D"/"C" em negrito
com 13–15:1 de contraste, não o traço ao redor. Se um avaliador achar que
mesmo assim conta como "borda de componente", é meia hora de trabalho trocar
a cor da borda; preferi ser transparente a preencher a tabela com um número
que não bate com o que está no arquivo.

## Tipografia

**Pilha do sistema, deliberadamente, sem fonte auto-hospedada.** O ambiente de
trabalho não tinha nenhuma fonte OFL (Inter, IBM Plex, Public Sans, Source
Sans 3) disponível como arquivo para embutir sem rede — e regra R4/K5 proíbe
buscar em CDN em runtime. Embutir por *data URI* base64 era tecnicamente
possível, mas eu não tinha o arquivo `.woff2` de nenhuma fonte permitida para
verificar a licença linha a linha antes de embutir; declarar "uso Inter" sem
ter o arquivo na mão seria inventar prova. O brief prevê exatamente esse caso
("use a pilha do sistema como alternativa declarada") — uso isso conscientemente,
não por preguiça:

```css
--fonte-base: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
  Arial, "Noto Sans", sans-serif;
```

Números usam `font-variant-numeric: tabular-nums` com
`font-feature-settings: "tnum" 1, "lnum" 1` em vez de depender de uma fonte
monoespaçada — a maioria das pilhas de sistema (Segoe UI, San Francisco,
Roboto, Arial) já expõe algarismos tabulares via OpenType. **Não medi** se
100% das plataformas honram esse recurso; testei apenas no Chromium deste
ambiente.

**Escala tipográfica** (`rem`, acompanha o zoom/preferência do usuário):

| Token | Valor | Uso |
| --- | --- | --- |
| `--texto-2xs` | 11px | rótulo de selo, meta mínima |
| `--texto-xs` | 12px | ajuda, cabeçalho de coluna |
| `--texto-sm` | 13px | corpo denso de tabela e formulário |
| `--texto-base` | 14px | corpo padrão |
| `--texto-md` | 16px | rótulo de campo, valor em destaque |
| `--texto-lg` | 20px | título de seção |
| `--texto-xl` | 28px | título de página |

## Escala de espaçamento

Base 4px, sem valor solto fora da escala: `--espaco-1` a `--espaco-7` = 4, 8,
12, 16, 24, 32, 48px. Raio: `--raio-sm` 3px (campos, botões, selos),
`--raio-md` 5px (painéis). Duas sombras só: `--sombra-painel` (1px, quase
imperceptível, só separa painel de fundo) e `--sombra-flutuante` (reservada
para menu suspenso, não usada nas três telas entregues porque nenhuma abre
um overlay de verdade).

## O que eu deliberadamente NÃO fiz, e por quê

1. **Sem overlay/menu suspenso real para os botões "Empresa" e "Período".**
   Eles estão desenhados como botões (`<button>`, clicáveis, com foco visível),
   mas a troca de contexto abriria um painel ou navegaria para outra tela — isso
   é decisão de fluxo do `arquiteto-senior`, não do desenho visual. Deixei o
   token `--sombra-flutuante` pronto para quando esse componente existir.
2. **Sem link de detalhe por conta no balancete.** O estado atual linka cada
   conta ao razão dela; eu não recriei isso para não ampliar escopo além das
   três telas pedidas. É perda real de funcionalidade se comparado à tela
   atual — registro para não esconder.
3. **Filtro "Nível" virou `<select>` com 4 opções fixas nesta tela**, porque os
   dados de exemplo têm 4 níveis. O comentário no HTML e neste documento deixam
   claro que, na implementação real, essa lista tem de ser gerada a partir do
   nível mais profundo *presente na consulta*, nunca hardcoded — é exatamente
   o erro do concorrente citado no achado 9 do brief.
4. **`onclick="window.print()"` no botão Imprimir é a única linha de JavaScript
   do conjunto.** Não hidrata dado nenhum (R6/K4): sem JS, o botão simplesmente
   não faz nada, e a pessoa ainda imprime pelo menu nativo do navegador
   (Ctrl+P). Não existe alternativa 100% sem-JS para disparar a caixa de
   diálogo de impressão a partir de um clique — é uma conveniência, não uma
   estrutura.
5. **`:has()`, `@layer`, container queries e `subgrid` não foram usados em
   lugar nenhum**, nem em caminho secundário. O recuo hierárquico do balancete
   usa `calc((var(--nivel) - 1) * 0.9rem)` com uma custom property por linha
   (`style="--nivel: N"`) — funciona em qualquer navegador com suporte a
   variáveis CSS, sem depender de seletor não confirmado.
6. **Não usei `light-dark()`** apesar de ter ~90% de suporte confirmado: as
   três telas são pensadas para um único tema (o institucional descrito
   acima), e a persona (analista 6–8h/dia, escritório) não pediu modo escuro.
   Um tema escuro de verdade exigiria revisar todos os pares de contraste
   deste documento — não fingi que "só trocar uma variável" resolveria.
7. **Não recriei os módulos "Empresas", "Plano de contas", "Diário",
   "Conferência" do menu lateral.** Eles existem como link no HTML (para a
   barra lateral não parecer incompleta) mas apontam para `#`, âncoras mortas.
   Só as três telas pedidas foram desenhadas de verdade.

## Onde esta variante é fraca (dito antes que o júri ache sozinho)

- **Densidade vertical do formulário de lançamento.** As 4 linhas + rodapé de
  conferência cabem bem em 900px de altura, mas o segundo exemplo (estado de
  erro) empurra a página para baixo o suficiente para exigir rolagem em
  1280×800. Um analista lançando dezenas de documentos por dia sentiria essa
  altura se cada lançamento tivesse 8+ linhas — não testei esse caso extremo.
- **O bronze do acento e o grafite institucional são ambos escuros.** Em
  monitor mal calibrado ou luz de sala muito forte, a diferença entre "botão
  secundário com borda" e "botão primário bronze" pode ficar mais sutil do
  que eu gostaria. Compensei com contraste de texto alto nos dois (o número
  garante a leitura), mas a *distinção entre os dois botões* não é uma medida
  de contraste WCAG — é julgamento visual meu, não verificado por fórmula.
- **Nunca testei com leitor de tela de verdade** (NVDA/VoiceOver/JAWS). Usei
  `aria-label`, `aria-hidden`, `scope`, `<caption>`, `role="status"`/`role="alert"`
  e `<label>` em todo campo pela regra e pela leitura da especificação, mas
  "segue a especificação" não é o mesmo que "testado com tecnologia assistiva
  real" — classifico isso como **Inspecionado**, não **Testado**.
- **O selo "Não fecha" desabilita o botão "Gravar lançamento" com o atributo
  `disabled` (não só `aria-disabled`).** Isso é mais forte para mouse, mas um
  `disabled` de verdade sai da ordem de tabulação — coerente com "não deixe
  gravar mesmo", mas significa que quem navega só por teclado não encontra o
  botão pelo Tab para saber *por que* ele sumiu da sequência; a mensagem de
  erro acima explica, mas não teste isso com um usuário real de teclado.
- **Paginação/volume do balancete.** Testei com 52 contas (4 níveis, soma
  interna conferida por script Python, ver abaixo). Não sei como esta mesma
  tabela se comporta com 300+ contas — nem se o cabeçalho fixo em duas linhas
  continua legível numa tela de 1280×720 com barra lateral aberta.

## Verificação que eu de fato rodei (Chromium local, `/opt/pw-browsers`)

- Renderizei as três páginas em 1280×800 e 1920×1080, tirei captura e olhei.
- `document.documentElement.scrollWidth === clientWidth` nas três páginas em
  1280px — confirmado por script, sem rolagem horizontal.
- Simulei `Tab` várias vezes com Playwright e capturei o estado de foco:
  encontrei e corrigi **dois bugs reais de foco invisível** (não hipotéticos):
  o item da barra lateral e os botões "Empresa"/"Período" tinham
  `overflow: hidden` no contêiner pai cortando o anel de foco com deslocamento
  positivo; o alternador D/C tinha o mesmo problema. Troquei por raio de borda
  nos elementos extremos (sem `overflow:hidden`) ou por `outline-offset`
  negativo. Isso está documentado como comentário no CSS de cada arquivo, não
  só aqui.
- Gerei o PDF de `02-balancete.html` de verdade (`page.pdf()` do Chromium, não
  só `@media print` no navegador) e conferi as três páginas resultantes:
  cabeçalho com a marca do escritório (não do DataLedger) no topo, tabela em
  paisagem sem sobreposição de coluna, cabeçalho e rodapé de totais repetidos
  em cada página impressa, crédito "Gerado com DataLedger" pequeno e só uma
  vez, no fim.
- Os saldos do balancete (52 contas, 4 níveis) foram calculados por um script
  Python que soma cada nó a partir dos filhos e verifica
  `total de débitos == total de créditos` antes de eu escrever o HTML — o
  balancete desta variante **fecha de verdade em 139.238,00 = 139.238,00**,
  não é um número de mentira digitado direto no HTML.
- **Não rodei** `ruff`, `python manage.py check` nem `pytest` — não fazem
  sentido aqui, não existe app Django nestes três arquivos autocontidos.
