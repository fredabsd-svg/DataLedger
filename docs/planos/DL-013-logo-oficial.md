# DL-013 — Atualizar marca visual do DataLedger

**Estado:** **substituída** em 2026-09-13. O Fred reprovou o laço infinito com cubos ("tá feio") e o `arquiteto-senior` encomendou três variantes ao `especialista-frontend`, com restrições: relação com contabilidade, sem letra inventada, flat, sem filtro, legível em 32 px e 128 px, em fundo claro e escuro.

Escolhida a **variante A — monograma DL**: as letras D e L com o mesmo peso, sobre uma linha verde de equilíbrio. Lê o nome do produto sem ambiguidade (o logo anterior tinha um "G" que não existe em DataLedger) e evoca as partidas dobradas — duas colunas de peso igual. As variantes B (livro-razão aberto) e C (grade de razão formando um D) foram descartadas por colapsarem em 32 px; as três estão preservadas, na versão final e com as renderizações de revisão, no commit `bfff79c` para consulta. O caminho `docs/assets/logo-dataledger.svg` foi mantido.

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
