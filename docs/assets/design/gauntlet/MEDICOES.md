# Gauntlet DL-026 — medições da rodada 1

Tudo aqui foi **medido** por um programa que abre cada tela num Chromium real,
em 1280×800 e 1920×1080. Nada foi estimado no olho. O programa está em
`scratchpad/gauntlet/juiz.py` e vai para o repositório junto com a etapa.

## O placar mecânico

| | Linhas visíveis 1280 | Linhas 1920 | Números tabulados (balancete) | Contraste reprovado | Dependência externa | JavaScript | Cabeçalho/rodapé fixos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Estado atual** | ~8 | ~8 | 0 | — | 0 | 0 | não |
| **A — Papel e tinta** | **15** | **25** | 210/210 | **1** (`—` a 3,54:1) | 0 | 0 | sim |
| **B — Instrumento de precisão** | 10 | 23 | 135/135 | **0** | 0 | 0 | sim |
| **C — Confiança de banco** | 9 | 18 | 113/113 | **0** | 0 | 0 | sim |

Foco de teclado muda de estilo de fato nas três — medido comparando o estilo
calculado antes e depois de focar, não pela presença de regra no CSS.

## Quatro defeitos do instrumento, e por que eles estão escritos aqui

O juiz errou **quatro vezes** antes de acertar, e **cada erro teria produzido um
veredito falso**. Ficam registrados porque a régua deste projeto vale para quem
mede, não só para quem é medido.

| # | O que ele fazia de errado | O que teria acontecido |
| --- | --- | --- |
| 1 | Lia a tabulação de algarismos no estilo da **célula**, e o número mora num elemento-folha dentro dela | Acusaria 210 células "sem tabulação" na variante A, onde as 210 estão corretas — **eliminaria a mais densa por defeito meu** |
| 2 | Aplicava foco **antes** de fotografar | As capturas saíam com o atalho "Pular para o conteúdo" cobrindo o menu — defeito criado pela ferramenta e atribuído ao desenho |
| 3 | Parava no primeiro fundo não transparente, tratando um branco de **6% de opacidade** como cor final | Acusou 1,11:1 num link creme sobre verde escuro que, conferido **pixel a pixel na captura**, tem contraste alto. Eliminaria a variante C |
| 4 | Amostrava elementos cujo texto vem de um **filho** (um `li` que contém um `a`) | Acusou 1,19:1 numa cor que **nenhum pixel da tela usa** |

A correção do defeito 1 trocou heurística por comportamento: o juiz não pergunta
mais qual fonte foi declarada, ele mede se `111111` e `888888` têm a mesma
largura. **Declaração não prova tabulação; largura igual prova.**

## Limites declarados desta medição

- **Campos de formulário não entram na contagem de tabulação.** O detector lê
  texto, e valor de `<input>` é atributo. Por isso a tela de lançamento aparece
  como `0/0` nas variantes B e C: elas põem os valores em campos. **Não é
  defeito delas; é cegueira da ferramenta**, e essa comparação específica não
  vale entre as três até alguém corrigir.
- **Nenhum leitor de tela real foi usado.** As três declararam o mesmo limite.
- **Só Chromium.** Firefox e Safari não foram testados por ninguém.
- Contraste de **texto** foi medido; contraste de **borda de componente**
  (WCAG 1.4.11, mínimo 3:1) **não** foi medido por este juiz.

## Divergência entre o declarado e o medido

A variante B declarou "15 a 17 linhas totalmente visíveis em 1280×800". O juiz
mediu **10**, e a captura publicada mostra 10 inteiras mais uma cortada. Não há
acusação de má-fé — pode ter sido medição em outra condição —, mas **o número
que vale para a régua é o reproduzível**, e ele está na imagem ao lado.

A causa aparece na captura, e é o anti-padrão que o próprio brief nomeou: o
bloco de filtros (duas datas com duas linhas de ajuda cada, mais o seletor de
nível com texto explicativo, mais o botão) empurra a tabela para baixo. É o
defeito do QuickBooks — barras demais antes do dado — na variante cuja tese era
densidade.
