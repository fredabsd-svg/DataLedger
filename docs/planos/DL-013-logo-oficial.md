# DL-013 — Atualizar marca visual do DataLedger

**Estado:** integrada na `main`, mas **reprovada pelo Fred** em 2026-09-13 ("tá feio"). Novo logo em elaboração pelo `especialista-frontend`; o caminho `docs/assets/logo-dataledger.svg` é preservado.

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
