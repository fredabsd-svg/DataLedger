# DL-012 — Redesign visual do README e identidade pública

**Estado:** integrada na `main` pelo PR #13. Corrigida em 2026-09-13 pelo `arquiteto-senior` após revisão do Fred — ver o commit de correção do README.

## Objetivo

Transformar o `README.md` na porta de entrada pública do DataLedger, com identidade visual própria, conteúdo fiel ao estado real do repositório e navegação direta para a documentação operacional.

## Escopo

- Redesenhar o README sem referências a produtos ou empresas externas usadas anteriormente como comparação.
- Criar identidade visual própria do DataLedger em `docs/assets/`.
- Adicionar logo, hero, diagrama de arquitetura, visual do ciclo de qualidade e ilustração de contribuição.
- Adicionar ícones SVG próprios para módulos e capacidades descritas no README.
- Substituir afirmações desatualizadas do README pelo estado real após a DL-011.
- Não alterar código de aplicação, modelos, migrações, dependências ou regras de negócio.

## Entregáveis

- `README.md` redesenhado.
- `docs/assets/logo-dataledger.svg`.
- `docs/assets/hero.svg`.
- `docs/assets/architecture.svg`.
- `docs/assets/gauntlet-loop.svg`.
- `docs/assets/contributing.svg`.
- Ícones em `docs/assets/icons/`.

## Critérios de aceite

1. O README possui um único H1 e renderiza sem depender de HTML/CSS não suportado pelo GitHub.
2. Não há menção a "Domínio Sistemas" nem a marca usada como referência no README anterior.
3. Não são anunciadas como prontas funcionalidades que permanecem planejadas.
4. Links relativos apontam para arquivos ou diretórios existentes na mesma branch.
5. Assets SVG são autocontidos, sem scripts, fontes externas ou conteúdo remoto embutido.
6. O estado do projeto informa a fundação entregue, contabilidade básica, DL-011 e a suíte de 272 testes sem inventar cobertura percentual, versão de produto ou licença inexistente.
7. O README destaca o processo de qualidade, arquitetura, roadmap e regras para contribuição.
8. O workflow de documentação do GitHub deve permanecer verde antes da integração.

## Validação

- Executar/confirmar o workflow `documentation.yml` no PR.
- Revisar o diff completo para verificar caminhos, texto, caracteres inválidos e referências indevidas.
- Fazer inspeção visual dos SVGs e do README renderizado no GitHub.
- Testes de backend não são exigidos para esta etapa documental, salvo se a CI do repositório os executar por política geral.

## Impacto

- **Segurança:** nenhum impacto no runtime; nenhum dado, segredo ou credencial é adicionado.
- **Dados:** nenhum impacto em banco ou migrações.
- **Cálculos:** nenhum impacto.
- **Contratos/API:** nenhum impacto.
- **Desempenho:** apenas assets SVG leves exibidos na página do repositório.

## Reversão

Reverter o commit da DL-012 restaura o README e remove os assets sem efeito no sistema executável.

## Git

- **Branch de trabalho:** `docs/dl-012-readme-visual`
- **Branch de destino:** `main`

## Evidências

Preencher após push/PR e resultado da CI.
