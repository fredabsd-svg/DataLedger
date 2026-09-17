# DL-025 — Ordens diretas do responsável pelo produto

**Estado:** em validação.

## Origem

Fred determinou em 2026-09-17 que o `AGENTS.md` deve permitir que os agentes
executem o que ele ordenar. A demanda nasceu depois de uma resposta recusar
operações de Git sob o argumento de que não existia “demanda formal”, embora o
próprio Fred estivesse conduzindo a conversa.

## Objetivo

Deixar explícito que uma ordem direta de Fred é uma demanda formal e define o
escopo autorizado, sem eliminar controles de teste, rastreabilidade, segurança
ou integridade contábil.

## Escopo

- Definir no `AGENTS.md` a autoridade de Fred sobre prioridade e escopo.
- Mapear verbos de leitura, alteração, merge e implantação para as ações que
  autorizam.
- Impedir pedido de confirmação repetida quando a ordem já for explícita.
- Permitir que o agente atribua o próximo identificador `DL-xxx` sem devolver
  essa tarefa a Fred.
- Preservar confirmação específica para operação destrutiva ou de alto impacto
  quando a ordem não identificar operação e alvo.

## Fora do escopo

- Reduzir requisitos de teste, revisão, CI ou rastreabilidade.
- Autorizar implantação em produção como consequência automática de edição ou
  merge.
- Contornar restrições técnicas, credenciais ausentes, segurança, sigilo,
  legislação ou invariantes contábeis.

## Critérios de aceite

1. O texto declara que uma solicitação direta de Fred é demanda formal.
2. Uma ordem para alterar ou implementar autoriza branch, edição, testes,
   documentação, commit, push e PR quando houver acesso configurado.
3. Uma ordem explícita para merge autoriza o merge depois das verificações
   obrigatórias, sem segunda confirmação.
4. Implantação em produção continua exigindo que o ambiente seja indicado.
5. Operações destrutivas ou de alto impacto exigem operação e alvo explícitos.
6. Falta de credencial é relatada como limitação técnica, não como proibição do
   projeto.
7. O `AGENTS.md` permanece abaixo do limite de 30.000 bytes do RC-84.
8. A documentação passa nas verificações disponíveis e o diff não introduz
   links quebrados nem espaços finais.

## Testes e evidências

- `git diff --check`.
- Validação dos links relativos e das regras de Markdown do repositório.
- `wc -c AGENTS.md`, com resultado menor que 30.000 bytes.
- Revisão do diff completo.

## Riscos e reversão

O principal risco é interpretar uma ordem genérica como autorização para uma
ação irreversível. A mitigação é separar operações comuns das destrutivas e
exigir, nestas últimas, operação e alvo explícitos. A reversão consiste em
reverter o commit documental; não há migração nem alteração de dados.

## Git

- **Branch de trabalho:** `docs/ordens-diretas-do-responsavel`.
- **Branch de destino:** `main`.
