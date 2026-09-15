---
name: criar-um-papel
description: Aponta para o procedimento de criar ou alterar um papel da equipe de agentes do DataLedger a partir da fonte única.
---

# Criar um papel novo na equipe do DataLedger

Este arquivo é um **ponteiro**, não uma cópia do procedimento. Ele existe
para que o Codex CLI — que varre `.agents/skills/` em busca de fluxos
reutilizáveis — também saiba que a equipe de agentes pode ganhar papéis
novos, e onde está o passo a passo.

O procedimento completo — criar o arquivo na fonte, preencher o frontmatter,
rodar o gerador, rodar o teste de sincronia e pedir ao `arquiteto-senior`
para atualizar a documentação da equipe — está em
[`docs/agents/como-criar-um-papel.md`](../../../docs/agents/como-criar-um-papel.md).
Leia-o antes de criar ou alterar qualquer papel; não edite os arquivos
gerados em [`.claude/agents/`](../../../.claude/agents/) ou
[`.codex/agents/`](../../../.codex/agents/) diretamente — a próxima geração
sobrescreve.
