# Estado atual da equipe de agentes

Atualizado em **2026-09-14**, com a `main` em `9b22b03` (PR #18 integrado).
Branch de trabalho `claude/accounting-agent-team-setup-mn6lyf`, recriada a
partir da `main` depois da integração.

> **Correção de um erro do `arquiteto-senior`, registrada aqui porque é a regra
> que o Fred transformou em instrução permanente.** O achado 7 da [auditoria
> DL-017 rodada 1](../auditorias/2026-09-14-dl-017-rodada-1.md) encontrou este
> arquivo afirmando "DL-017 em execução — fase A delegada" e "DL-015 onda 2 não
> iniciada" **enquanto o commit auditado continha as seis telas prontas e
> integradas**. Repetido no `README.md`. Corrigido nesta entrega. O guarda de
> integração contínua não pega este caso: ele exige que cada `DL-xxx` apareça
> aqui e no README, não que a descrição esteja correta.

> **Este cabeçalho ficou dois dias desatualizado** e foi encontrado assim pelo
> `auditor-qa` (achado novo 8 da [rodada 2 da
> DL-015](../auditorias/2026-09-14-dl-015-rodada-2.md)), junto com o restante do
> estado. O teste de integração contínua não pega isso: ele exige que cada
> identificador `DL-xxx` apareça aqui e no README, não que o texto esteja
> atual. Quem atualiza este arquivo confere **a revisão e a contagem de
> testes**, não só a lista de etapas.
>
> **Armadilha descoberta ao corrigir isso, registrada para a próxima sessão:**
> um arquivo **não consegue citar o hash do commit que o contém** — o hash só
> existe depois de o conteúdo estar fechado, e qualquer `--amend` o muda de
> novo. Tentei e gravei um hash que nunca chegou a existir na branch. A
> convenção que passa a valer: citar a revisão **anterior** ("logo após
> `<hash>`"), que é verificável, em vez de fingir citar a própria.

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
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção e conferência de documentos fiscais | **Plano revisado em 2026-09-14** pelo acervo real: a primeira fatia passa a ser **NFS-e** (85% do movimento), não NF-e. Foco confirmado pelo Fred |
| [DL-011](../planos/DL-011-cnpj-alfanumerico.md) | CNPJ alfanumérico (NT 2025.001 / IN RFB 2.229) | Integrada (PR #12) |
| [DL-012](../planos/DL-012-readme-identidade-visual.md) | Redesenho do README e identidade visual (`docs/assets/`) | Integrada (PR #13), por outra sessão |
| [DL-013](../planos/DL-013-logo-oficial.md) | Logo oficial — três desenhos reprovados pelo Fred; o quarto é o **conceito do próprio Fred em vetor limpo** | **Integrada (PR #17)** |
| [DL-014](../planos/DL-014-guardas-de-processo.md) | Guardas de processo: gancho de sessão, workflow de atestado no PR, proteção da `main` | Integrada (PR #15). **BL-02 segue pendente**: a proteção da `main` é ação administrativa do Fred |
| [DL-015](../planos/DL-015-contabilidade-utilizavel.md) | Contabilidade utilizável: Diário, Razão e Balancete por período, conciliáveis, e conferência de lotes | **Onda 1 integrada (PR #17)**, aprovada com ressalvas na [rodada 4](../auditorias/2026-09-14-dl-015-rodada-4.md) após três reprovações. Ressalvas em BL-83 a BL-86. **Onda 2 (interface, BL-62) executada como [DL-017](../planos/DL-017-interface-da-contabilidade.md)** |
| [DL-016](../planos/DL-016-competencia-e-fechamento.md) | Competência e fechamento de período, com reabertura autorizada e auditada | **Planejada** — destrava BL-65 (alteração em massa) e BL-66 (eliminação) |
| [DL-017](../planos/DL-017-interface-da-contabilidade.md) | Interface da contabilidade: plano de contas, lançamento, Diário, Razão, Balancete e conferência no navegador | **Fases A e B integradas (PR #18)** e **reprovadas em três rodadas** ([1](../auditorias/2026-09-14-dl-017-rodada-1.md), [2](../auditorias/2026-09-14-dl-017-rodada-2.md), [3](../auditorias/2026-09-14-dl-017-rodada-3.md)). O bloqueador do `1.000` **fechou** na rodada 3, medido em 55 textos — mas **continua vivo na `main`**, que ainda é `9b22b03`. A rodada 3 achou BL-115 (ALTA, negação de serviço) **criada pela correção da rodada 2**. **Reprovada em 4 rodadas** ([1](../auditorias/2026-09-14-dl-017-rodada-1.md), [2](../auditorias/2026-09-14-dl-017-rodada-2.md), [3](../auditorias/2026-09-14-dl-017-rodada-3.md), [4](../auditorias/2026-09-14-dl-017-rodada-4.md)). **Reprovada em 5 rodadas.** A [rodada 5](../auditorias/2026-09-14-dl-017-rodada-5.md) fechou **os 12 achados da rodada 4** e varreu **concorrência real**, que passou inteira — mas trouxe um **bloqueador que eu criei** (a CI está vermelha: a instalação de navegador que eu fiz transformou 2 testes pulados em 2 falhando) e dois achados ALTA. Correção em curso, BL-140 a BL-147 |
| [DL-018](../planos/DL-018-primeiro-acesso.md) | Primeiro acesso de uma instalação nova: criar o primeiro escritório e o primeiro vínculo **pelo produto**, sem admin técnico | **Planejada, não iniciada** — BL-125, encontrada pelo Fred ao subir o sistema, não por auditoria. Depende de a DL-017 fechar e de três respostas dele |

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

A suíte foi de **55 para 402 testes** (211 só em contabilidade), e passou a rodar em **12 s** em vez de 199 s, depois de BL-80. O PR #11 levou DL-007 a DL-009 à `main`,
com as quatro verificações da integração contínua verdes.

Registro honesto de erros do próprio `arquiteto-senior`, já corrigidos e
documentados nas auditorias: um critério de aceite que não exercitava o defeito
que dizia cobrir, uma instrução que levou a um desenho pior (converter todo
`IntegrityError` em erro 400, mascarando defeito de sistema como erro do
cliente), e uma decisão que afirmava funcionar em produção sem que o
`collectstatic` existisse no `Dockerfile`. Os três foram encontrados pela
auditoria independente — que é exatamente o motivo de ela existir.

## Próximo passo

1. **[DL-017](../planos/DL-017-interface-da-contabilidade.md) — corrigir a
   rodada 5 e reauditar.** A [rodada 5](../auditorias/2026-09-14-dl-017-rodada-5.md)
   **reprovou**, e o auditor fez questão de registrar que *"o parecer negativo
   esconde o tamanho do avanço: esta é, de longe, a melhor entrega das cinco"*.

   **O que fechou:** os 12 achados da rodada 4, todos, medidos por mutação dele
   — inclusive dois que sobreviviam havia três rodadas. E **concorrência real
   foi varrida pela primeira vez e a contabilidade passou inteira**: 8
   requisições simultâneas com a mesma chave produzem 1 lançamento; 2 estornos
   simultâneos, 1 estorno; 10 lançamentos concorrentes fecham o balancete em
   100,00 exatos; 4 duplos cliques na tela, 1 lançamento.

   **O que reprova:** um **bloqueador que eu criei** — a instalação de navegador
   no workflow puxou o snap, que roda confinado e não lê `/tmp`, transformando 2
   testes pulados em 2 **falhando** (BL-140, workflow já corrigido nesta
   entrega) — e dois achados **ALTA**: o campo `regime` aceita lixo e grava
   (BL-141), e o `conta` do item na API vai direto ao ORM, gravando `1.9` na
   conta 1 e `"٢"` na conta 2 com HTTP 201 (BL-142).

   **A regra que fica, e é a sucessora da DE-032:** a varredura de uma classe
   começa no **CAMPO**, não na linha. Os três resíduos estavam, todos, a **um
   campo de distância** do que foi consertado. Virou **DE-034**.

2. **BL-125 — o primeiro acesso de uma instalação nova só existe pelo admin
   técnico.** Encontrado pelo Fred ao subir o sistema: sem escritório e sem
   vínculo, a tela explica corretamente e a única saída é o admin do Django.
   Nenhuma das três auditorias viu, porque todas partem de cenário já montado.
   **Estado inicial de instalação é um estado da interface.**

3. **BL-83 — bloqueador de implantação.** Pelo Django admin ainda é possível
   mover conta **com movimento** para outra empresa; o balancete da origem
   deixa de fechar e a conferência não acusa. Precisa estar fechado **antes de
   existir dado real de cliente**. BL-84, BL-85 e BL-86 completam as ressalvas
   da auditoria.
4. **[DL-016](../planos/DL-016-competencia-e-fechamento.md) — competência e
   fechamento de período.** Planejada e com contrato escrito. Destrava a
   alteração em massa (DE-017) e a regeração de lançamentos derivados (DE-018),
   as duas pedidas pelo Fred.
5. **[DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) — importação
   e conferência de documentos fiscais.** O Fred confirmou o foco em
   2026-09-14: *"foca na importação e conferência"*. O plano foi **revisado**
   pela medição do acervo real — primeira fatia é **NFS-e**, não NF-e, porque
   85% do movimento dele é nota de serviço prestado. Os 22 critérios de aceite
   têm número medido por trás. Começa quando a DL-017 (telas) for auditada.
6. **BL-100 — aguardando confirmação do Fred.** `docker compose up --build`
   falhava na máquina dele com "container dataledger-db-1 is unhealthy", num
   banco perfeitamente saudável: a verificação de saúde não tinha
   `start_period` e se esgotava durante o `initdb` (22 s lá, ~1 s na CI). Junto,
   nenhuma migração rodava ao subir. Corrigido em `docker-compose.yml` (DE-028)
   e no README. **Não testado aqui** — não existe daemon Docker neste ambiente;
   só `docker compose config` e leitura. Só o Fred pode fechar este item.
7. **P0 de implantação (DE-014):** BL-33 (cópia de segurança com restauração
   testada), BL-50, BL-51, BL-52 e BL-53.
8. **Decisões que dependem do Fred:** PE-36 (quem lê contabilidade e se há
   vínculo usuário-empresa), PE-38 (lucros e prejuízos acumulados na
   implantação), PE-20, PE-21, PE-22, PE-23, PE-25, PE-30 a PE-35.
9. **BL-02 — proteção da branch `main`.** Ação administrativa no GitHub: a API
   de proteção respondeu 403 à sessão de agente. Em Settings → Rules →
   Rulesets, exigindo PR com as verificações "Lint e testes", "Validar
   documentação" e "Regras do projeto", e bloqueando force push e exclusão.

## O que o Fred opera sem cobertura, mesmo quando a DL-017 for aprovada

Levantado pelo `auditor-qa` na
[rodada 5](../auditorias/2026-09-14-dl-017-rodada-5.md), a pedido meu, e
reproduzido aqui porque é o que ele precisa saber **antes** de pôr dado de
cliente — não depois.

1. **Não existe rascunho, não existe período encerrado, não existe bloqueio de
   reabertura.** Todo lançamento gravado é efetivado, e nada impede lançar em
   competência já fechada. Está no backlog (BL-10, BL-11), não na entrega.
2. **Data de lançamento não tem faixa.** `0001-01-01` e `9999-12-31` são
   aceitos.
3. **Estorno é o único caminho de correção**, e funciona — inclusive sob
   concorrência, medido. Não há edição, e isso é **decisão de produto**, não
   limitação temporária.
4. **Backup e restauração não foram planejados nem verificados** nesta etapa.
5. **Validação HTML5 completa e percurso manual por uma pessoa** não foram
   feitos. As capturas são evidência de tela, não de uso.
6. **Nada disso substitui a validação profissional do Fred** sobre o que a
   legislação exige de um Diário, de um Razão e de um Balancete; sobre o teto de
   partidas (PE-42); sobre conta sem pai tratada como raiz (PE-43); e sobre a
   apresentação de uma conta devedora com **saldo credor**, que aparece na
   captura do Balancete sem nenhuma sinalização.

O auditor declarou, e eu subscrevo: **ninguém aqui afirma que o sistema está
livre de defeitos, que é seguro, ou que está em conformidade legal.** Afirmamos
o que medimos, e está registrado o que não medimos.

## Estado do repositório

- **`main` em `9b22b03`**, com DL-002 a DL-009, DL-011 a DL-015 e **DL-017 fases
  A e B** — esta última integrada por autorização expressa do Fred **antes** de
  a auditoria voltar, e depois reprovada. Não repetir: a ordem do projeto é
  auditar e só então integrar.
- **Suíte: 683 testes** na branch de trabalho (446 na `main`), rodando em ~35 s
  em árvore limpa. **Suíte verde não é sistema correto**, e esta etapa tem a
  série completa como prova: 487 testes passavam com o bloqueador do `1.000` em
  vigor; 559 passavam com a negação de serviço em vigor; 608 passavam com a API
  gravando data errada em silêncio. O que encontra defeito não é contagem, é
  **variar a dimensão medida** — rodada 2 variou o texto do valor; rodada 3
  cronometrou o tempo e variou a forma do nome do campo; rodada 4 variou o
  **transporte** da requisição e o **comprimento** de um identificador. Achou
  nas três. **A dimensão indicada para a rodada 5 é concorrência real** — duas
  conexões simultâneas sobre a mesma chave de idempotência e a mesma conta,
  que segue verificada só por requisições sequenciais.
- A verificação que vale é em **árvore limpa**: `git archive <hash> | tar -x` em
  diretório vazio, e rodar ali (BL-81). Medir na árvore de trabalho já produziu
  um relatório errado.
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
