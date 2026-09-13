# DL-013 — Logo oficial do DataLedger

**Estado:** quarta execução, **aguardando aprovação do Fred** (2026-09-13).

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
   [docs/assets/propostas-logo/README.md](../assets/propostas-logo/README.md).

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
  conferência; **sai antes da integração à `main`**.
- Não alterar código, dependências, modelos, migrações ou regras de negócio.

## Critérios de aceite

1. O símbolo renderiza em fundo claro e escuro, em 128 px e em 32 px.
   **Verificado** por renderização em Chromium (prancha
   `simbolo-128px-e-32px.png`) e conferência a olho.
2. A fita verde não vaza para dentro do laço esquerdo nem termina em corte
   reto visível. **Verificado** na renderização em 360 px
   (`variantes-sem-e-com-barra.png`); a v3 tinha o vazamento e foi refeita.
3. Os assets não contêm scripts, fontes externas nem links remotos.
   **Verificado**: o único URL nos três SVGs é o `xmlns` do SVG.
4. O README continua apontando para um arquivo existente e o texto
   alternativo descreve o desenho atual.
5. Os workflows de documentação e backend permanecem verdes.
6. **O Fred aprova o desenho.** Pendente.

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
