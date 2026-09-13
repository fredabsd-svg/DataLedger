# Estado atual da equipe de agentes

Atualizado em **2026-09-12**, na revisão `44f9fe6`, branch
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

Duas fases. Primeiro a **configuração da equipe** e o diagnóstico inicial, sem
tocar em código de negócio. Depois, com a equipe funcionando, **cinco etapas de
produto** — ver "Trabalho de produto" mais abaixo.

### Arquivos criados na fase de configuração

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

Nenhum arquivo preexistente foi modificado **nessa fase**. Verificado com
`git status` à época: a árvore continha apenas adições.
`~/.claude/settings.json` não existia e **não foi criado**; não há
configuração administrativa nesta máquina
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

## Todas as etapas do projeto

Tabela completa, porque este documento é a **fonte única do estado** — o
[README](../../README.md) aponta para cá em vez de repetir a informação. Essa
decisão veio de um achado do Fred em 2026-09-13: o estado estava duplicado em
quatro lugares do README e tinha divergido. Verdade espalhada é verdade que
diverge.

| Etapa | Entrega | Situação |
| --- | --- | --- |
| [DL-001](../planos/DL-001-documentacao-inicial.md) | Documentação inicial, escopo, regras e modelo de PR | Integrada |
| [DL-002](../planos/DL-002-arquitetura-fundacao.md) | Arquitetura e fundação técnica: Django, DRF, PostgreSQL, CI | Integrada |
| [DL-003](../planos/DL-003-fundacao-multiempresa.md) | Autenticação e isolamento entre escritórios | Integrada |
| [DL-004](../planos/DL-004-cadastro-empresas.md) | Cadastro central de empresas e estabelecimentos | Integrada |
| [DL-005](../planos/DL-005-permissoes-auditoria.md) | Permissões por papel e trilha de auditoria | Integrada |
| [DL-006](../planos/DL-006-contabilidade-basica.md) | Contabilidade básica: plano de contas, partidas dobradas, Diário, Razão, Balancete | Integrada |
| [DL-007](../planos/DL-007-correcao-bloqueadores-contabilidade.md) | Correção dos dois bloqueadores da auditoria inicial | Integrada (PR #11) |
| [DL-008](../planos/DL-008-politica-monetaria-e-validacao-de-escala.md) | Política monetária explícita e módulo de arredondamento | Integrada (PR #11) |
| [DL-009](../planos/DL-009-fundacao-de-interface.md) | Fundação de interface, estados de erro, acessibilidade | Integrada (PR #11) |
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção de documentos fiscais: XML, ZIP e SPED | **Planejada — próxima** |
| [DL-011](../planos/DL-011-cnpj-alfanumerico.md) | CNPJ alfanumérico (NT 2025.001 / IN RFB 2.229) | Integrada (PR #12) |
| [DL-012](../planos/DL-012-readme-identidade-visual.md) | Redesenho do README e identidade visual (`docs/assets/`) | Integrada (PR #13), por outra sessão |
| [DL-013](../planos/DL-013-logo-oficial.md) | Logo oficial — **em revisão**: o Fred reprovou o resultado e pediu novo desenho | Integrada na `main`; substituição em curso |

**Módulos Fiscal, Folha, Honorários e Processos/Paralegal: não iniciados.**

## Trabalho de produto entregue nesta sessão

Todas as etapas seguiram o mesmo ciclo: o `arquiteto-senior` escreve o plano com
critérios de aceite numerados, o implementador executa, o arquiteto revisa o
diff, o `auditor-qa` audita a **versão integrada** com teste de mutação, os
achados voltam ao responsável, e só então há commit.

| Etapa | Conteúdo | Parecer da auditoria |
| --- | --- | --- |
| [DL-007](../planos/DL-007-correcao-bloqueadores-contabilidade.md) | BL-40 (isolamento de `conta_pai`) e BL-41 (estorno duplicado) | Aprovado após 2 rodadas e verificação dirigida |
| [DL-008](../planos/DL-008-politica-monetaria-e-validacao-de-escala.md) | `apps/core/dinheiro.py`, política de arredondamento (DE-010) | Aprovado com ressalvas, corrigidas |
| [DL-009](../planos/DL-009-fundacao-de-interface.md) | Template base, mensagens, estados de erro, acessibilidade | Aprovado com ressalvas, corrigidas |
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção de documentos fiscais (XML, ZIP, SPED bloco C) | **Planejada, não iniciada** |
| [DL-011](../planos/DL-011-cnpj-alfanumerico.md) | CNPJ alfanumérico (BL-46) | **Cinco rodadas.** 1 reprovada; 2 a 4 aprovadas com ressalvas; 5 **liberada para encerramento** |

A suíte foi de **55 para 200 testes**. O PR #11 levou DL-007 a DL-009 à `main`,
com as quatro verificações da integração contínua verdes.

Registro honesto de erros do próprio `arquiteto-senior`, já corrigidos e
documentados nas auditorias: um critério de aceite que não exercitava o defeito
que dizia cobrir, uma instrução que levou a um desenho pior (converter todo
`IntegrityError` em erro 400, mascarando defeito de sistema como erro do
cliente), e uma decisão que afirmava funcionar em produção sem que o
`collectstatic` existisse no `Dockerfile`. Os três foram encontrados pela
auditoria independente — que é exatamente o motivo de ela existir.

## Próximo passo

1. **Integrar a DL-011 à `main`.** A etapa está fechada na branch de trabalho,
   commit `44f9fe6`, com parecer de encerramento do `auditor-qa`. Falta
   confirmar a integração contínua no remoto e abrir a integração.
2. **[DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) — recepção de
   documentos fiscais.** É a prioridade de negócio confirmada pelo Fred (RC-40).
   O plano já tem os leiautes de NF-e e de SPED levantados em fonte oficial.
   Antes de começar, ler a seção de pendências: **BL-52** (fila de tarefas em
   segundo plano) mudou o desenho da etapa, e **BL-54** deve estar resolvido
   antes de gravar CNPJ em lote.
3. **P0 de implantação (DE-014):** BL-33 (cópia de segurança com restauração
   testada), BL-50, BL-51, BL-52 e BL-53. Nenhum urgente hoje, todos
   pré-condição para existir dado real de cliente.
4. **Decisões que dependem do Fred:** PE-20 (escritório com CNPJ inválido),
   PE-21 (escopo da unicidade de CNPJ), PE-22 (documento não eletrônico nos
   períodos a migrar), PE-23 (o sistema de XML entrega os eventos?), PE-25
   (residência do dado e LGPD).
5. **BL-02** — proteção da branch `main`. Ação administrativa no GitHub, que
   nenhum agente pode executar.

## Estado do repositório

- `main` contém DL-002 a DL-009.
- A branch de trabalho é `claude/accounting-agent-team-setup-mn6lyf`,
  sincronizada com o remoto. Último commit: `44f9fe6`.
- **Suíte: 272 testes** (eram 55 no início da sessão).
- A DL-011 está **completa e auditada** na branch, aguardando integração.
- Pendência herdada da DL-002: a proteção da branch `main` nunca foi
  configurada.

### Sobre os commits marcados como "preservação, não entrega"

O histórico tem vários. Eles existem porque este ambiente é **efêmero** e um
gancho exige árvore limpa ao fim de cada turno: commitar protege o trabalho de
um agente que ainda está executando, mas **não** o aprova. Cada um desses
commits declara, na própria mensagem, o que foi verificado e o que não foi, e
qual é a última revisão com auditoria completa. Não confunda com entrega.

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
