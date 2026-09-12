# Estado atual da equipe de agentes

Atualizado em **2026-09-12**, na revisão `31c3047`, branch
`claude/accounting-agent-team-setup-mn6lyf`.

Este documento existe para que outra sessão retome o trabalho sem reconstruir o
contexto. **Processos de agentes não sobrevivem ao encerramento da sessão** —
só os arquivos deste repositório garantem continuidade. Mantenha-o atualizado a
cada etapa.

## Resumo em uma linha

A equipe está **configurada, carregada e validada por execução** como
subagentes; o que **não** existe é uma equipe com três integrantes de fato, por
exigir sessão interativa.

## O que foi feito nesta sessão

Configuração da equipe de agentes e diagnóstico inicial. **Nenhum arquivo de
código de negócio foi alterado.**

### Arquivos criados

| Arquivo | Conteúdo |
| --- | --- |
| `.claude/settings.json` | `agent`, `teammateMode` e as duas variáveis de ambiente. |
| `.claude/agents/arquiteto-senior.md` | Líder, `opus`, esforço `high`, memória de projeto. |
| `.claude/agents/desenvolvedor-pleno.md` | Implementação, `sonnet`, `high`, memória de projeto. |
| `.claude/agents/especialista-frontend.md` | Interface, `sonnet`, `high`, memória de projeto. |
| `.claude/agents/auditor-qa.md` | Auditoria, `opus`, `high`, **sem escrita e sem memória**. |
| `.claude/agents/auxiliar-pesquisa.md` | Auxiliar somente leitura, sem delegação. |
| `.claude/agents/auxiliar-implementacao.md` | Auxiliar com escrita, sem delegação. |
| `.claude/agents/auxiliar-verificacao.md` | Auxiliar de verificação, sem escrita, sem delegação. |
| `CLAUDE.md` | Resumo operacional, apontando para o `AGENTS.md`. |
| `docs/agents/equipe.md` | Papéis, delegação, permissões e limitações reais. |
| `docs/agents/estado.md` | Este arquivo. |
| `docs/projeto/requisitos.md` | Confirmados, hipóteses e pendências. |
| `docs/projeto/backlog.md` | Tarefas priorizadas com critérios de aceite. |
| `docs/projeto/decisoes.md` | Decisões DE-001 a DE-007. |
| `docs/auditorias/2026-09-11-diagnostico-inicial.md` | Diagnóstico dos três papéis, com os achados preservados. |

Nenhum arquivo preexistente foi modificado. Verificado com `git status`: a
árvore contém apenas adições. `~/.claude/settings.json` não existia e **não foi
criado**; não há configuração administrativa nesta máquina
(`claude doctor`: "Managed settings (remote): none configured for this
organization"), logo não houve conflito com restrição administrativa.

## O que foi realmente validado

| Item | Resultado |
| --- | --- |
| `.claude/settings.json` é JSON válido | **Sim**, verificado. |
| Frontmatter dos 7 agentes | **Válido.** Nome único, igual ao do arquivo, com `description` preenchida em todos. |
| Campos usados existem na documentação oficial | **Sim.** `agent`, `teammateMode`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` e `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` foram conferidos na documentação. |
| Auxiliares não delegam | **Sim, por restrição técnica**: `disallowedTools: Agent` nos três. |
| Auditor sem escrita | **Sim, por restrição técnica**: sem `Write`/`Edit`/`NotebookEdit` e sem `memory`. |
| Regras da validação de documentação | **Aprovado.** Título, UTF-8, sem espaço final, nova linha final e links relativos conferidos em 25 arquivos `.md`. |
| Teste real de delegação | **Sim.** Três agentes independentes em paralelo produziram o diagnóstico, sem alterar código. |
| Suíte do projeto | **Aprovada**: 55 testes, lint, formatação, `manage.py check` e migrações em banco vazio. |
| Equipe ativa com três integrantes | **Não.** Ver a seção seguinte. |

### Validações confirmadas por execução em 2026-09-12

Depois de a sessão recarregar as configurações, os sete agentes passaram a
existir como tipos acionáveis e foi possível verificar por execução o que antes
só havia sido validado por sintaxe:

| Verificação | Como foi comprovada | Resultado |
| --- | --- | --- |
| Variáveis de Agent Teams aplicadas | Leitura do ambiente da sessão | **Sim.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` e `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`, contra `unset` e `1` antes. |
| Lista de permissão do `arquiteto-senior` é imposta | Tipos acionáveis oferecidos à sessão principal | **Sim.** Só os seis papéis da equipe (mais `Explore` e `Plan`); `claude`, `general-purpose`, `claude-code-guide` e `statusline-setup` deixaram de ser oferecidos. |
| `auxiliar-pesquisa` não delega e não escreve | O próprio agente relatou suas ferramentas reais | **Sim.** Recebeu exatamente `Read, Glob, Grep, Bash, WebFetch, WebSearch`. Sem `Agent`, sem `Write`, sem `Edit`. |
| `auditor-qa` não escreve | O próprio agente relatou suas ferramentas reais | **Sim.** Sem `Write`, `Edit` nem `NotebookEdit`. |
| A restrição de delegação do auditor é só comportamental | O próprio auditor listou os tipos que enxerga | **Confirmado como esperado.** Ele vê `auxiliar-implementacao`, `desenvolvedor-pleno` e `especialista-frontend` — todos com `Write`/`Edit`. A plataforma não o bloqueia. Ver DE-005. |
| Auditor não alterou nada ao ser exercitado | `git status --short` e `git diff --stat` pelo próprio auditor | **Árvore limpa**, sem saída em nenhum dos dois. |

**Achado da própria configuração, corrigido na documentação:** o `auditor-qa`
declara `TaskCreate`, `TaskGet`, `TaskList` e `TaskUpdate`, mas **não as recebeu**
ao rodar como subagente comum. A plataforma concede a interseção entre o
declarado e o disponível, descartando o resto em silêncio. As ferramentas de
tarefa são acrescentadas automaticamente a um **integrante** `in-process`, não a
um subagente. As declarações foram mantidas e o comportamento está documentado em
[equipe.md](equipe.md); não conte com a lista compartilhada de tarefas quando um
papel roda como subagente.

### Modelos e esforço

Os modelos pedidos (`opus` para líder e auditor, `sonnet` para pleno e
frontend) foram configurados **sem substituição**. Nenhuma restrição
administrativa de modelo foi encontrada nesta máquina. Se em outro ambiente um
apelido for bloqueado, a plataforma substitui automaticamente e a troca deve
ser registrada aqui.

O esforço `high` está declarado nos quatro papéis e em dois auxiliares
(`auxiliar-pesquisa` usa `medium`, por ser tarefa de leitura).

## O que depende de reinício, e por quê

Os itens 1 a 4 abaixo valiam quando os arquivos foram criados e **foram
resolvidos** quando a sessão recarregou as configurações, em 2026-09-12.
Ficam registrados porque descrevem o que exige reinício em qualquer ambiente:

1. **A chave `agent` é lida na inicialização da sessão.** Uma sessão iniciada
   antes de o arquivo existir não roda como `arquiteto-senior`.
2. **As definições em `.claude/agents/` são carregadas no início da sessão.**
   Antes disso valem apenas por sintaxe, não por acionamento.
3. **Agent Teams depende da variável estar no ambiente da sessão.**
4. **`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` idem**: enquanto valer `1`, o
   aninhamento está desligado e nenhum papel consegue acionar auxiliar.

**O que continua não validado, e não deve ser apresentado como funcionando:**

5. **Os três integrantes de equipe nunca foram criados.** Eles existem como
   tipos acionáveis e funcionam como **subagentes**; não foram exercitados como
   integrantes de uma equipe, com lista compartilhada de tarefas e mensagens
   diretas entre si.

### Limitação adicional deste ambiente

Esta sessão é **remota e não interativa** (`CLAUDE_CODE_ENTRYPOINT` igual a
`remote_mobile`, sem terminal associado). A documentação oficial de Agent Teams
afirma que **criar integrantes exige sessão interativa**: em modo não
interativo, um subagente nomeado roda como subagente comum, e nenhum integrante
é criado.

**Consequência honesta:** os três papéis (`desenvolvedor-pleno`,
`especialista-frontend`, `auditor-qa`) funcionam como **subagentes reais** —
foram acionados, executaram e devolveram resultado, em paralelo e sem alterar
código. O que não existe aqui é o modo **integrante de equipe**: lista
compartilhada de tarefas, mensagens diretas entre eles e painel de seleção.

Sintoma observável desta limitação: a ferramenta de acionamento desta sessão
**não oferece o parâmetro de nome** para o agente. É nomear um subagente que o
faz subir como integrante; sem esse parâmetro, nenhuma equipe se forma.

Para ter os três como integrantes de fato, abra uma sessão **interativa** no
terminal, dentro do projeto.

## Como retomar

```bash
cd /home/user/DataLedger
claude
```

A sessão passa a rodar como `arquiteto-senior`, com Agent Teams habilitado.
Confirme antes de prosseguir:

1. `/agents` lista os sete agentes.
2. `/status` ou `/model` mostra o agente da sessão como `arquiteto-senior`.
3. Peça ao líder, em português:

   > Crie três integrantes usando os tipos `desenvolvedor-pleno`,
   > `especialista-frontend` e `auditor-qa`, com esses mesmos nomes.

4. Os três devem aparecer no painel abaixo do campo de entrada. Setas
   selecionam, Enter abre a conversa do integrante, Esc limpa a seleção.

Se os integrantes não aparecerem, a sessão provavelmente não é interativa —
ver a limitação acima. Nesse caso, o trabalho continua por subagentes, que
funcionam normalmente.

Para uma sessão avulsa em outro papel: `claude --agent auditor-qa`.

## Próximo passo

**Priorização com o Fred.** O backlog está ordenado por dependência técnica,
não por valor de negócio — e só o Fred pode corrigir isso.

Ordem sugerida:

1. **BL-01** — responder as pendências PE-01 a PE-08 de
   [../projeto/requisitos.md](../projeto/requisitos.md). As mais urgentes são
   PE-01 (qual rotina do escritório tem prioridade) e PE-02 (política de
   arredondamento).
2. **BL-40 e BL-41** — os dois achados bloqueadores da auditoria. Precisam de
   correção e teste antes de qualquer funcionalidade nova.
3. **BL-02** — proteção da branch `main`. É **ação administrativa no GitHub**:
   nenhum agente pode executá-la.

## Estado do repositório

- A `main` **já contém** DL-002 a DL-006. Os PRs #7, #8 e #9 foram mesclados —
  verificado no GitHub e no histórico local.
- A seção "Estado atual e continuidade" do `README.md` ainda descreve esses PRs
  como pendentes. **O README não foi alterado nesta sessão**, porque o PR #10,
  já aberto, corrige exatamente essa seção.
- Pendência herdada da DL-002, ainda aberta: a proteção da branch `main` nunca
  foi configurada. É o controle que teria evitado o encadeamento indevido de
  PRs que motivou os PRs #7 a #9.
- Commit `31c3047` criado localmente com toda a configuração da equipe.
  **Nenhum push foi feito**, porque o Fred pediu explicitamente que não houvesse
  push nem publicação nesta execução. A branch está um commit à frente do
  remoto, sem nada a puxar: o envio seria avanço direto, quando autorizado.

## Ambiente de verificação

Registrado para quem for reproduzir:

- O contêiner padrão traz `python3` 3.11, e **o projeto não instala nele**:
  `Django==6.1.1` exige 3.12 ou superior. Use `python3.13` (ou 3.12/3.14).
- PostgreSQL 16 está disponível localmente; o Docker está instalado mas **sem
  daemon em execução**. A suíte foi rodada contra um cluster PostgreSQL
  descartável iniciado à mão.
- PowerShell **não** está instalado, então `scripts/validate-docs.ps1` não pôde
  ser executado aqui. As mesmas regras foram verificadas por uma
  reimplementação equivalente; a execução oficial é a da integração contínua.
