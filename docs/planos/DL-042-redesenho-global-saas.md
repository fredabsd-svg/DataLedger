# DL-042 — Redesenho global da interface com a skill de design de SaaS

**Demanda:** Fred, 26/09/2026: *"Use a skill saas-design-excellence […] e melhore o
layout do sistema como um todo: landing page e telas de navegação, botões,
módulos, tudo."* A ordem é posterior à DL-040 e a amplia; onde a skill e a
direção de arte divergirem, esta etapa **atualiza a direção de arte** (AGENTS.md
§0, regra 2) em vez de ignorar uma das duas.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 2** — o que o contador usa. Permissões, isolamento, regras
contábeis e o **documento impresso** não mudam. **Branch:**
`claude/vigilant-bardeen-jo12l4` → `main`, sobre a DL-040 já integrada.

## Direção decidida pelo arquiteto

- **Moldura em "L invertido"** (referência `shell-navegacao` da skill): barra
  lateral com o seletor de empresa no topo, até 5–7 áreas (Início, Empresas,
  Contabilidade, Fiscal e, no rodapé, Conta), **recolhível** para ícones — o que
  devolve largura às tabelas contábeis, motivo pelo qual a DL-040 tinha ficado
  com a barra superior. Cabeçalho da página com título, trilha e uma ação
  primária à direita.
- **Tokens** a partir do `tokens-starter` da skill (cores OKLCH, neutros
  tingidos pela marca, semânticas, escala tipográfica, espaço em base 4,
  densidade), preservando a identidade existente (logo, marca, tipografia da
  DL-026) e conferindo contraste com o `check_contrast.py` da skill.
- **Landing, entrada e cadastro** refeitos pela referência `fluxos-saas`, sem
  prometer o que não existe (IA, MCP, Folha e Honorários continuam "planejados").
- **Início** como fila do que precisa de atenção (anti-padrão "dashboard de KPI"
  da skill), só com dados que o produto já tem.
- Componentes padronizados em todas as telas: botões, tabelas, formulários,
  estados vazio, erro, sem permissão e conteúdo extremo.

## Restrições que não mudam

Sem JavaScript obrigatório, sem CDN e sem passo de build (DE-011): recolher a
lateral e os menus funciona sem script; script, se houver, é só melhoria
progressiva. O documento impresso não muda (job "Identificação do emitente" e
testes da DL-027). Acessibilidade WCAG 2.2 AA e suítes de guarda existentes
verdes, sem enfraquecer. Nada de dado real nas capturas.

## Critérios de aceite

1. Diagnóstico no modo revisão da skill, por severidade, registrado no
   [mapa de telas](../projeto/mapa-de-telas.md).
2. Moldura, tokens e componentes aplicados a **todas** as telas do mapa, e a
   [direção de arte](../projeto/direcao-de-arte.md) atualizada com o que mudou.
3. Portão de qualidade da skill percorrido e registrado: contraste, teclado,
   alvos, 360 px, estados, formatos pt-BR, impressão.
4. Capturas antes e depois de todas as telas principais, em computador e
   celular, publicadas em `docs/assets/telas/dl042/` para o Fred aprovar antes
   do PR.
5. Suíte completa, lint, formatação, `manage.py check`.

Reversão: revert dos commits de interface; nenhum dado ou migração.
