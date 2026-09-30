# DL-051 — Corrigir os módulos da navegação

**Demanda:** Fred, 30/09/2026: Vendas não pertence ao DataLedger;
inventário é rotina de Fiscal, sem módulo próprio. Correção da DL-049,
com autorização de commit, push e merge mantida na conversa.
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `fix/dl-051-modulos-contabeis` → `main`.
**Risco:** nível 2, correção de navegação de módulo já entregue.

## Objetivo e entregáveis

Retirar Vendas e Estoque da seleção de módulos e de suas páginas
informativas. O prompt original era uma referência de interface, não uma
autorização para ampliar o escopo funcional do sistema. Documentar que
estoque e Livro de Registro de Inventário permanecem em Fiscal, como já
previsto em FIS-39/FIS-47. Essas rotinas ainda não estão implementadas;
não criar atalhos ou resultados fictícios para elas.

## Critérios de aceite e testes

- A navegação renderizada não oferece Vendas, Estoque ou Inventário como
  módulos independentes, inclusive fora das homes.
- Acesso autenticado às antigas homes e listas de Vendas/Estoque retorna
  404; não anuncia domínio disponível ou planejado.
- Contabilidade, Fiscal e Livro-caixa mantêm destinos, contexto e
  permissões. As páginas informativas de Financeiro e Folha não mudam.
- Testar a regressão, executar os testes das homes e de navegação, lint,
  formatação, Django check e validação documental. Conferir visualmente a
  barra lateral no navegador e as quatro checagens da CI antes do merge.

## Impacto, dependências e reversão

Sem mudança em dados, cálculos, documentos emitidos, permissões ou
migrações. As duas URLs informativas indevidas deixam de existir; não são
contratos de operação. Base: `main` após os PRs #63 e #62, preservando a
API da DLPA. Reversão por revert deste PR, sem operação no banco.

## Evidências

Resultados executados e link do PR serão registrados na entrega e no
[estado](../agents/estado.md). Não exige nova auditoria de domínio segundo
AGENTS.md §3.1: é correção de interface de módulo já auditado, sem alteração
de agregações ou regras contábeis.

- Antes: regressões novas → `6 failed, 2 passed, 65 deselected in 11.01s`.
- Depois: homes → `73 passed in 38.97s`; painel/estado →
  `23 passed, 1 warning in 2.95s`; navegação/troca de empresa →
  `11 passed, 1 warning in 2.55s`, em SQLite temporário.
- Ruff check limpo, format check com 318 arquivos já formatados;
  Django check sem problemas e diff check sem apontamento.
- `pwsh -NoProfile -File scripts/validate-docs.ps1` →
  `Documentação válida: 193 arquivos Markdown verificados.`, exit 0.
- Navegador real sobre dados fictícios: menu corrigido na home Contabilidade,
  home Fiscal e Início; seis URLs 404; contexto histórico conservado e
  nenhum erro JavaScript ou rolagem horizontal em 1.440/390 px.
- A validação integral PostgreSQL e as demais checagens obrigatórias
  serão conferidas na CI antes de integrar. Não houve teste com operadores
  nem dispositivo físico nesta correção.
