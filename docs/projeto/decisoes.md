# Decisões do DataLedger

Registro das decisões arquiteturais e de processo, com a justificativa e o que
foi descartado. Uma decisão só entra aqui depois de tomada; alternativa ainda
em estudo pertence a [requisitos.md](requisitos.md) como hipótese ou pendência.

Formato: identificador, data, decisão, motivo, alternativas descartadas e
consequência.

## DE-001 — Sessão principal roda como `arquiteto-senior`

**Data:** 2026-09-11

**Decisão:** a chave `agent` em `.claude/settings.json` aponta para
`arquiteto-senior`. Não existe um quinto papel de líder.

**Motivo:** o Fred quer conversar principalmente com o líder técnico. Fazer da
sessão principal o próprio arquiteto elimina uma camada de intermediação e
garante que quem responde ao Fred é quem detém o contexto de arquitetura.

**Alternativas descartadas:** um agente coordenador separado acima dos quatro
papéis — acrescentaria repasse de contexto sem ganho, e o Fred pediu
explicitamente que não houvesse um quinto líder.

**Consequência:** a sessão precisa ser reiniciada para que a chave `agent`
tenha efeito. Ver [docs/agents/estado.md](../agents/estado.md).

## DE-002 — Modo de exibição dos integrantes: `in-process`

**Data:** 2026-09-11

**Decisão:** `teammateMode` igual a `in-process`.

**Motivo:** funciona em qualquer terminal, sem depender de tmux ou iTerm2, e é
o padrão da plataforma desde a versão 2.1.179. O ambiente remoto deste projeto
não garante um terminal com painéis divididos.

**Alternativas descartadas:** `auto` e `tmux`, que abrem painéis divididos —
exigem tmux ou iTerm2 com o utilitário `it2`, e falham silenciosamente para
`in-process` quando indisponíveis.

**Consequência:** integrantes aparecem no painel abaixo do campo de entrada da
sessão principal. Subagente de integrante roda em primeiro plano.

## DE-003 — Profundidade de aninhamento de subagentes igual a 2

**Data:** 2026-09-11

**Decisão:** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` igual a `"2"`.

**Motivo:** permite que os quatro papéis acionem um auxiliar, e impede que o
auxiliar acione outro. É a camada de profundidade exatamente necessária ao
desenho da equipe.

**Alternativas descartadas:** `1` desligaria o aninhamento e impediria os
papéis de delegar; `3` ou mais abriria cadeias longas de delegação, difíceis de
auditar e de custo imprevisível.

**Consequência:** combinada com a ausência da ferramenta `Agent` nos três
auxiliares, há **duas** barreiras contra delegação em cadeia: uma por
profundidade e outra por ferramenta.

## DE-004 — Independência do auditor por ferramenta, não por promessa

**Data:** 2026-09-11

**Decisão:** `auditor-qa` não recebe `Write`, `Edit` nem `NotebookEdit`, e não
recebe memória automática de projeto. Os relatórios são registrados em
`docs/auditorias/` pelo `arquiteto-senior`.

**Motivo:** a independência da auditoria precisa de barreira técnica, não
apenas de instrução. Memória automática criaria um diretório persistente de
escrita para o auditor, ampliando indevidamente seu alcance.

**Alternativas descartadas:** dar `Write` ao auditor restrito a
`docs/auditorias/` — a plataforma não restringe `Write` por caminho na
definição do agente, então a restrição seria apenas verbal.

**Consequência conhecida e assumida:** o auditor mantém `Bash`, porque precisa
executar testes. **Terminal permite escrita mesmo sem `Write`/`Edit`.** Logo, a
independência do auditor é **parcialmente técnica e parcialmente
comportamental**, e isso está documentado como tal em
[docs/agents/equipe.md](../agents/equipe.md). Mitigação: inspecionar scripts
antes de executar, evitar comandos que reescrevem arquivos, e conferir
`git status` e `git diff --stat` após os testes.

## DE-005 — Restrição de delegação do auditor é comportamental

**Data:** 2026-09-11

**Decisão:** a regra "o auditor delega apenas a `auxiliar-pesquisa` e
`auxiliar-verificacao`" fica registrada como instrução de comportamento no
prompt do agente e em [docs/agents/equipe.md](../agents/equipe.md).

**Motivo:** a sintaxe `Agent(tipo)` só funciona como lista de permissão para um
agente rodando como **thread principal**. Dentro de uma definição de subagente,
listar `Agent` permite delegar e a lista entre parênteses é **ignorada** pela
plataforma.

**Alternativas descartadas:** usar `permissions.deny` com
`Agent(auxiliar-implementacao)` — a regra valeria para a sessão inteira e
bloquearia também o `desenvolvedor-pleno` e o `especialista-frontend`, que
legitimamente precisam desse auxiliar.

**Consequência:** a restrição é real como instrução e frágil como garantia.
Está declarada honestamente em vez de apresentada como isolamento de segurança.

## DE-006 — CLAUDE.md enxuto, AGENTS.md como fonte das regras

**Data:** 2026-09-11

**Decisão:** o `AGENTS.md` já existente continua sendo a regra obrigatória de
desenvolvimento. O `CLAUDE.md` criado é um resumo operacional que aponta para
ele e prevalece o `AGENTS.md` em caso de conflito.

**Motivo:** o repositório já tinha um documento de regras maduro, de 285
linhas, citado pelo README e pelo modelo de pull request. Duplicá-lo criaria
duas fontes divergentes.

**Alternativas descartadas:** mover as regras para `CLAUDE.md` — quebraria
referências existentes e o hábito já estabelecido no projeto.

**Consequência:** agentes leem `CLAUDE.md` automaticamente e são direcionados
ao `AGENTS.md` antes de qualquer edição.

## DE-007 — Ambiente de desenvolvimento exige Python 3.12 ou superior

**Data:** 2026-09-11

**Decisão:** registrar que o projeto não instala em Python 3.11.

**Motivo:** verificado nesta máquina. `requirements/base.txt` fixa
`Django==6.1.1`, que exige `Requires-Python >=3.12`. O `python3` padrão do
contêiner é 3.11.15, e a instalação falha com "No matching distribution found
for Django==6.1.1". Com `python3.13` a instalação conclui e a suíte roda.

**Alternativas descartadas:** rebaixar o Django para uma versão compatível com
3.11 — contraria o `pyproject.toml`, que já define `target-version = "py314"`,
e a integração contínua, que usa Python 3.14.

**Consequência:** quem for rodar o projeto localmente precisa de Python 3.12+.
Isso deve ser documentado no README como pré-requisito — pendência registrada
no [backlog](backlog.md).
