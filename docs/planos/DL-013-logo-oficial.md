# DL-013 — Logo oficial do DataLedger

**Estado:** **encerrada em 2026-09-14.** O Fred autorizou a integração à `main`
junto do restante da branch. A pasta temporária de pranchas saiu do repositório,
como previsto no escopo.

## Histórico honesto

1. **Laço infinito com cubos, primeira execução** (por outra sessão, na
   DL-012): reprovado pelo Fred ("tá feio"). Diagnóstico da época: pesado de
   gradientes, sombra e brilho.
2. **Monograma "DL"**: reprovado ("ficou horrível, você pode fazer bem
   melhor"). Correto e sem alma — duas letras e um traço.
3. **Razonete** (conta T): reprovado ("esse T ficou horrível, tente algo
   novo"). Chegou a ser integrado à `main` pelo PR #16 antes da reprovação.
   Uma prancha com quatro direções novas (selo, balança, fita de somar, livro
   aberto) foi preparada, mas o Fred não escolheu nenhuma: mandou o **seu
   próprio logo original** — laço azul e verde, fita, cubos e assinatura — e
   pediu "algo assim, melhore esse".
4. **Conceito do Fred, executado em vetor limpo** — esta versão. Mesmas
   cores, composição e assinatura; o que mudou está descrito em
   descrito abaixo, em "O que mudou em relação ao original do Fred".

O caminho `docs/assets/logo-dataledger.svg` foi preservado nas quatro trocas.

## Objetivo

Adotar como marca oficial o conceito criado pelo Fred, em vetor plano e
autocontido, legível em 128 px e em 32 px, em fundo claro e escuro, com a
assinatura ("DataLedger" + "SISTEMA CONTÁBIL") também em vetor.

## Escopo

- `docs/assets/logo-dataledger.svg` — símbolo.
- `docs/assets/logo-dataledger-assinatura.svg` e
  `docs/assets/logo-dataledger-assinatura-escura.svg` — assinatura completa.
- Texto alternativo do logo no `README.md`.
- Pasta temporária `docs/assets/propostas-logo/` com as pranchas de
  conferência; **removida em 2026-09-14, antes da integração**, como previsto.
- Não alterar código, dependências, modelos, migrações ou regras de negócio.

## Critérios de aceite

1. O símbolo renderiza em fundo claro e escuro, em 128 px e em 32 px.
   **Verificado** por renderização em Chromium nos dois tamanhos e nos dois
   fundos, conferida a olho. A prancha usada saiu do repositório junto da pasta
   temporária; a evidência é a verificação, não o arquivo.
2. A fita verde não vaza para dentro do laço esquerdo nem termina em corte
   reto visível. **Verificado** em renderização a 360 px; a terceira execução tinha o
   vazamento e foi refeita por isso.
3. Os assets não contêm scripts, fontes externas nem links remotos.
   **Verificado**: o único URL nos três SVGs é o `xmlns` do SVG.
4. O README continua apontando para um arquivo existente e o texto
   alternativo descreve o desenho atual.
5. Os workflows de documentação e backend permanecem verdes.
6. **O Fred aprova o desenho.** **Atendido por autorização de integração**, em
   2026-09-14 — ele mandou integrar a branch à `main`, e o logo ia nela. Não é
   aprovação estética declarada item a item; é autorização de integração, e
   registro assim para não inflar. Trocar o SVG depois custa um commit.

## Fonte da assinatura

"DataLedger" em Sora ExtraBold e "SISTEMA CONTÁBIL" em Sora Medium com
espaçamento 0,24 em, ambas convertidas em traçados com fontTools. Sora é
distribuída sob a SIL Open Font License 1.1, que permite a conversão em
contornos para uso em logotipo. Nenhum arquivo de fonte foi versionado.

## Impacto

Exclusivamente visual/documental. Sem impacto em banco, API, segurança,
cálculos ou runtime da aplicação.

## Reversão

Reverter o commit da DL-013 restaura o logo anterior.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`
- **Branch de destino:** `main`

## O que mudou em relação ao original do Fred

Registrado aqui porque a pasta temporária que trazia esta comparação saiu do
repositório na integração.

- **Mesmo conceito, mesmas cores, mesma composição:** dois laços azuis, fita
  verde atravessando, cubos isométricos no laço direito, nome em negrito
  azul-marinho e a linha "SISTEMA CONTÁBIL" em caixa alta espaçada.
- **Vetor plano:** dois gradientes suaves, sem sombra, brilho ou filtro. O
  símbolo tem 2,2 KB, sem fonte externa e sem nenhum recurso remoto.
- **O entrelaçado é de verdade**, pela ordem de desenho: a fita nasce escondida
  na faixa do laço esquerdo, emerge por baixo dele na junção e passa por cima do
  laço direito, terminando em ponta redonda.
- **Os sete cubos** têm o mesmo tamanho e a mesma luz, e continuam legíveis em
  32 px como um bloco.
- **A assinatura** usa a fonte Sora convertida em traçados, para não depender de
  fonte instalada em quem abre o arquivo.

Arquivos definitivos: `docs/assets/logo-dataledger.svg` (símbolo),
`docs/assets/logo-dataledger-assinatura.svg` e
`docs/assets/logo-dataledger-assinatura-escura.svg` (assinatura completa, para
fundo claro e escuro).
