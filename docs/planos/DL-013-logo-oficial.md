# DL-013 — Atualizar marca visual do DataLedger

**Estado:** **substituída duas vezes** e fechada em 2026-09-13.

1. O laço infinito com cubos foi reprovado pelo Fred ("tá feio"): sem relação com contabilidade, com um "G" que não existe em DataLedger, sobrecarregado de gradientes, sombra e brilho.
2. O monograma "DL" que o substituiu foi reprovado de novo ("ficou horrível, você pode fazer bem melhor"). Diagnóstico: correto e sem alma — duas letras e um traço, indistinguível de qualquer sigla.
3. O símbolo atual é o **razonete** — a conta T, que todo contador reconhece antes de ler qualquer letra. Débito à esquerda, crédito à direita; os lançamentos têm larguras diferentes mas **somam o mesmo nos dois lados** (84 + 60 + 92 em cada); a barra verde é o fechamento — a conta bateu. Uma cor primária (azul-marinho), um acento (esmeralda), sem filtro, 1,5 KB. Desenhado pelo `arquiteto-senior` em três execuções renderizadas em 128 px e 32 px, fundo claro e escuro, e conferidas a olho; a regra dupla de fechamento (variante A) foi descartada por virar borrão em 32 px, e o T verde (variante C) por perder o significado do fechamento.

O caminho `docs/assets/logo-dataledger.svg` foi preservado nas três trocas.

## Objetivo

Substituir o símbolo anterior exibido no topo do `README.md` pela nova identidade aprovada: laço azul e verde inspirado em infinito/G, com cubos de dados no núcleo.

## Escopo

- Atualizar `docs/assets/logo-dataledger.svg`.
- Preservar o caminho já usado pelo README para evitar quebra de referência.
- Usar SVG transparente, autocontido e sem dependências externas.
- Não alterar código, dependências, modelos, migrações ou regras de negócio.

## Critérios de aceite

1. O logo renderiza em fundo claro e escuro.
2. O símbolo permanece legível no tamanho atual do cabeçalho do README.
3. O asset não contém scripts, fontes externas ou links remotos.
4. O README continua apontando para um arquivo existente.
5. O workflow de documentação permanece verde.
6. O backend permanece verde por regressão da CI do repositório.

## Validação

- Revisão visual do SVG.
- Workflow `documentation.yml`.
- Workflow `backend.yml` executado pela política do repositório.

## Impacto

Exclusivamente visual/documental. Sem impacto em banco, API, segurança, cálculos ou runtime da aplicação.

## Reversão

Reverter o commit da DL-013 restaura o logo anterior.

## Git

- **Branch de trabalho:** `docs/dl-013-logo-oficial`
- **Branch de destino:** `main`
