---
name: regras-do-projeto
description: Aponta para as regras obrigatórias de desenvolvimento do DataLedger e para o estado atual do projeto, sem copiá-las.
---

# Regras do projeto DataLedger

Este arquivo existe para o Codex CLI, que varre `.agents/skills/` de cada
diretório até a raiz do repositório em busca de fluxos reutilizáveis. As
regras do projeto **não** moram aqui — no mesmo espírito de
[`.github/copilot-instructions.md`](../../../.github/copilot-instructions.md),
que já faz isso desde a DL-014.

**Antes de alterar qualquer arquivo, leia integralmente
[`AGENTS.md`](../../../AGENTS.md)** na raiz do repositório. Ele é a regra
obrigatória de desenvolvimento, testes, Git e pull request, e prevalece
sobre qualquer instrução deste arquivo.

Depois, leia [`docs/agents/estado.md`](../../../docs/agents/estado.md), que é
a fonte única do estado do projeto: o que está pronto, o que é o próximo
passo e o que depende de decisão do responsável pelo produto.

Resumo do que é imposto tecnicamente, e não só pedido — detalhes em
`AGENTS.md`, seção "Como estas regras são impostas":

- Pull request sem a caixa "Li o AGENTS.md" marcada e sem plano `DL-xxx`
  citado **reprova** na integração contínua.
- Etapa com plano em `docs/planos/` que não apareça no README e em
  `docs/agents/estado.md` **reprova** na integração contínua.
- A branch `main` só recebe alteração por pull request com as verificações
  verdes.

## Os papéis da equipe

Os papéis configurados para este projeto (arquiteto, desenvolvedor,
frontend, auditor e auxiliares) estão descritos, para o Codex, em
[`.codex/agents/`](../../../.codex/agents/) — um arquivo `.toml` por papel,
gerado a partir de [`docs/agents/papeis/`](../../../docs/agents/papeis/). Para
criar um papel novo, siga
[`docs/agents/como-criar-um-papel.md`](../../../docs/agents/como-criar-um-papel.md)
(ou use a skill `criar-um-papel`).
