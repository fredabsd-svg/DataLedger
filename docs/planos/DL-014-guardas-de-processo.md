# DL-014 — Guardas de processo: regras impostas, não só pedidas

**Estado:** em validação na branch de trabalho.

| Item | Valor |
| --- | --- |
| Branch de trabalho | `claude/accounting-agent-team-setup-mn6lyf` |
| Branch de destino | `main` |
| Origem | Pedido do Fred em 2026-09-13: *"sempre que algum dev ou modelo de IA for mexer no código ele deve prioritariamente analisar as regras do projeto — consegue resolver isso para que não aconteça mais?"* |

## O problema que motivou

Um redesenho do README e um logo entraram na `main` por outra sessão, **sem
passar pela revisão que o [AGENTS.md](../../AGENTS.md) exige**, anunciando
tecnologias que o projeto não usa. Não foi má-fé: foi ausência de barreira. A
proteção da branch `main` nunca tinha sido configurada (BL-02), e ler as regras
era um pedido escrito num arquivo que ninguém é obrigado a abrir.

Pedido escrito é **comportamental**: depende de o agente — pessoa ou modelo —
resolver ler. Esta etapa troca pedido por **mecanismo** onde isso é possível, e
declara com honestidade onde não é.

## O que passa a ser imposto tecnicamente

| Guarda | Mecanismo | O que impede |
| --- | --- | --- |
| **Regras na frente do agente** | Gancho `SessionStart` em `.claude/hooks/session-start.sh`, registrado em `.claude/settings.json`. Tudo o que ele imprime entra no contexto da sessão do Claude Code **antes da primeira ação**. Ele imprime o `AGENTS.md` inteiro e o "Próximo passo" de `docs/agents/estado.md`. | Sessão do Claude Code na web começar sem as regras carregadas. |
| **Ambiente pronto** | O mesmo gancho instala as dependências em `.venv` e sobe o PostgreSQL local com usuário e banco de desenvolvimento. | Agente improvisar ambiente à parte e pular os testes por não conseguir rodá-los. |
| **Atestado no PR** | Workflow `.github/workflows/regras-do-projeto.yml`: reprova o PR se a caixa "Li o AGENTS.md" não estiver marcada, se a caixa de estado do projeto não estiver marcada, ou se nenhum plano `DL-xxx` for citado. | Integrar sem ao menos atestar que leu as regras e sem plano da etapa. |
| **Estado não diverge** | `apps/core/tests/test_documentacao_do_estado.py` (já existia): etapa com plano ausente do README ou de `estado.md` reprova o build. | README e estado ficarem para trás. |
| **`main` só por PR** | Proteção da branch `main` exigindo pull request e as três verificações verdes (`Lint e testes`, `Validar documentação`, `Regras do projeto`), sem push direto, sem *force push*, sem apagar. | O caminho que a outra sessão usou. |
| **Outras ferramentas de IA** | `.github/copilot-instructions.md` apontando para o `AGENTS.md`. Cursor, Codex e Gemini CLI leem `AGENTS.md` nativamente. | Ferramenta que não é o Claude Code ignorar as regras por não saber onde estão. |

## O que continua sendo só instrução — declarado, não escondido

- **Ler de verdade.** O gancho coloca as regras no contexto; o workflow exige o
  atestado. Nenhum dos dois consegue provar que alguém **entendeu**. Um agente
  pode marcar a caixa sem ler. O que impede isso é a auditoria independente de
  cada etapa e a revisão do diff — processo, não mecanismo.
- **Sessão interativa local.** O gancho roda só no Claude Code na web
  (`CLAUDE_CODE_REMOTE=true`). Em terminal local, o `CLAUDE.md` continua sendo
  carregado automaticamente e aponta para o `AGENTS.md` — instrução, não
  imposição.
- **Ferramentas que não leem `AGENTS.md` nem `copilot-instructions.md`.** Não há
  como obrigar. A proteção da `main` é a última linha: o que quer que a
  ferramenta faça, não entra sem PR verde.
- **Revisão humana obrigatória.** Exigir aprovação de revisor no GitHub
  **bloquearia o próprio Fred**, porque o autor de um PR não pode aprová-lo e
  hoje ele é a única pessoa. Fica de fora até haver um segundo revisor.

## Critérios de aceite

| # | Critério | Como se verifica |
| --- | --- | --- |
| 1 | Gancho executa sem erro em ambiente remoto e imprime o `AGENTS.md` e o próximo passo | Execução com `CLAUDE_CODE_REMOTE=true`, saída conferida |
| 2 | Depois do gancho, `ruff` e `pytest` funcionam com o `.venv` que ele criou | Um arquivo lintado e um teste executado |
| 3 | Gancho é idempotente | Segunda execução conclui sem erro |
| 4 | Workflow reprova PR sem atestado e aprova PR com atestado | Lógica testada localmente com corpos de PR de exemplo, e execução real no PR desta etapa |
| 5 | `main` protegida: push direto recusado, PR exige os três checks | Configuração conferida na API ou na tela do GitHub |
| 6 | `AGENTS.md` e `CLAUDE.md` declaram o que é imposto e o que é instrução | Leitura |
| 7 | Sem regressão; suíte, lint, formatação e validação de documentação limpos | Execução |

## Reversão

Remover o gancho de `.claude/settings.json` e o workflow devolve o
comportamento anterior sem efeito no sistema executável. A proteção da `main` é
configuração do GitHub, desfeita na mesma tela em que se cria.
