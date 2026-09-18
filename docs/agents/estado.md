# Estado atual da equipe de agentes

Atualizado em **2026-09-17**, a partir da `main` em **`c7346e6`** (BL-261
integrada — guard em `Conta.clean()` + 4 testes em
`test_dl023_conta_nao_muda_de_empresa_ou_natureza.py`). Branch de trabalho
`main`, limpa. DL-024 encerrada via DE-043 (CA-4 reconciliada).

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
| [DL-014](../planos/DL-014-guardas-de-processo.md) | Guardas de processo: gancho de sessão, workflow de atestado no PR, proteção da `main` | Integrada (PR #15). **BL-02 segue pendente**: a proteção da `main` é ação administrativa do Fred. **PR #32 (`docs/fix-gate-regex`):** correção estrutural do regex do gate que exigia `**` literal dentro do texto que o humano escreve — ver [DE-044](../projeto/decisoes.md). Aguarda auditoria independente antes do merge. |
| [DL-015](../planos/DL-015-contabilidade-utilizavel.md) | Contabilidade utilizável: Diário, Razão e Balancete por período, conciliáveis, e conferência de lotes | **Onda 1 integrada (PR #17)**, aprovada com ressalvas na [rodada 4](../auditorias/2026-09-14-dl-015-rodada-4.md) após três reprovações. Ressalvas em BL-83 a BL-86. **Onda 2 (interface, BL-62) executada como [DL-017](../planos/DL-017-interface-da-contabilidade.md)** |
| [DL-016](../planos/DL-016-competencia-e-fechamento.md) | Competência e fechamento de período, com reabertura autorizada e auditada | **Onda 1 (F1 + F2) INTEGRADA em `main` (PR #31 mergeado em `fa15cf1`, squash).** Modelo `Competencia` com `EstadoCompetencia` (aberta, em_encerramento, encerrada), `UniqueConstraint(empresa, ano, mes)` e checks de faixa (mês 1..12, ano 1970..2999). FK `LancamentoContabil.competencia` (PROTECT, nullable até F5) preenchida por `get_or_create` em `services.criar_lancamento` com savepoint próprio. 7 testes do modelo. **Auditoria rodada 1 APROVADA** com 1 achado menor (A2) corrigido no próprio PR ([parecer](../auditorias/2026-09-18-dl-016-rodada-1.md)) — `RESTRICOES_CONFERIDAS` da DL-019 expandida de 7 para 10 entradas. CI VERDE em `a0e0859` (após resolução do conflict com o PR #32 já em main). **Pendências declaradas:** migration 0004 precisa ser regenerada por `makemigrations` no primeiro deploy Python 3.12+ (cabeçalho da migration declara). **F3, F4, F5 voltam para o backlog como sub-DLs dependentes da próxima onda** — ver DE-050 |
| [DL-017](../planos/DL-017-interface-da-contabilidade.md) | Interface da contabilidade: plano de contas, lançamento, Diário, Razão, Balancete e conferência no navegador | **Integrada (PR #19, `60cbcff`)**, aprovada com ressalvas na [rodada 6](../auditorias/2026-09-15-dl-017-rodada-6.md) depois de cinco reprovações. As ressalvas foram encaminhadas à DL-020 |
| [DL-020](../planos/DL-020-consolidacao-pos-auditoria.md) | Consolidação pós-auditoria: as dez ressalvas da rodada 6 e as regras contábeis confirmadas pelo Fred | **Integrada (PR #21, `0dd07b4`)** — quatro rodadas de auditoria, fechamento do BL-242 com renumeração para `RC-85`, `RC-86`, `PE-46`, e conferência de encerramento. Resumo do auditor: *"Quatro rodadas, quatro achados no meu mecanismo de medição, zero no produto."* Itens abertos preservados: **BL-211** (dois defeitos do admin — não devem atravessar a DL-010), **BL-229** (medições de CSS que pulam na CI), **BL-235, BL-236, BL-237, BL-238, BL-239, BL-241** |
| [DL-021](../planos/DL-021-robustez-do-gerador-no-windows.md) | Robustez do gerador de papéis em ambiente Windows: `write_text → write_bytes` para gravar LF sempre, e `.gitattributes` neutralizando `core.autocrlf=true` | **Integrada (PR #22, `b8c66a6`)** — o verificador byte-strict (achado 9 do DL-019) continua intacto. ⚠️ **Limitação declarada e ainda aberta:** o que fechou foi a **quebra de linha**; rodar `--verificar` no Windows continua reportando `permissão 0o666` nos 14 derivados, por motivo independente ligado ao achado A3 (**BL-175**). Não ler como "compatibilidade Windows comprovada". Este arquivo e o próprio plano diziam "planejada, não iniciada" **depois** da integração; quem mediu a divergência foi o plano mestre, e a correção é a DL-022 |
| [DL-023](../planos/DL-023-integridade-administrativa.md) | Integridade administrativa: fechar **BL-83** (conta com movimento muda de empresa e de natureza pelo admin) e os dois casos vivos da **BL-211** (empresa inteira muda de escritório; inline de regime abre dois períodos ao mesmo tempo), com a defesa no **modelo** e não só na porta | **Integrada (PR #27, `1b828e7`)** + **BL-261 integrada (`c7346e6`, bugfix `30924ca`)** — guarda em `Conta.clean()` recusa reparentar conta com movimento para grupo de natureza oposta; 4 testes cobrindo recusa + 3 controles positivos. Ressalvas contábeis abertas: **BL-262** (admin sem isolamento por escritório em nenhuma superfície — etapa própria), **BL-263** (caixa do PR marcada com estado desatualizado), **BL-267** (add de conta cria em empresa de outro escritório — depende de BL-262), **BL-264, BL-265, BL-266, BL-268, BL-269, BL-270, BL-271, BL-272** (backlog, baixa/ressalva). |
| [DL-024](../planos/DL-024-trilha-integra-e-processo.md) | Trilha íntegra e processo: `registrar()` dentro da mesma transação que grava; `RegistroAuditoria` imutável contra `update()`/`delete()` em massa; PUT/PATCH com diff dos campos alterados; teste automatizado do gate SQLite/PostgreSQL | **Integrada (PR #28 + PR #29, `f9ee6c5`, DE-043)** — BL-14 (atomicidade), BL-16 (manager imutável), BL-57 (PUT/PATCH com diff), BL-244 (signal admin para 6 modelos via lista explícita `MODELOS_DA_TRILHA_DO_ADMIN`), BL-50 (gate SQLite/PostgreSQL, 5/5), CA-6 (matriz de acesso fixada). CI: 1.345 testes, 2 pulados. CA-4 reconciliada: plano listava 6 ModelAdmin mas registry tem 4; `Estabelecimento` é inline de Empresa, `HistoricoRegimeTributario` removido pelo admin na DL-023. DE-043: o plano é artefato derivado do código, não o contrário. [Auditoria rodada 1](../auditorias/2026-09-16-dl-024-rodada-1.md). **Fora do escopo:** BL-02 (proteção da main, ação do Fred), BL-242, criptografia em repouso, logs externos |
| [DL-025](../planos/DL-025-ordens-diretas-do-responsavel.md) | Reconhecer ordens diretas de Fred como demanda formal e autorização para executar o escopo pedido | **Integrada (PR #29, `f9ee6c5`)** — alteração documental, sem código de produto ou migração. Formaliza ordens diretas de Fred como demanda legítima, com processo de registro e validação |
| [DL-022](../planos/DL-022-plano-mestre-e-reconciliacao.md) | Plano mestre de evolução por módulos, incorporado sem edição, com a análise do arquiteto depois dele; e reconciliação da documentação que estava se contradizendo | **Integrada (PR #23, `24f6bbc`)** — etapa **documental**, nenhuma linha de código de produto. Entregou [`docs/projeto/plano-mestre.md`](../projeto/plano-mestre.md), a desduplicação da DL-020 no README, a DL-021 corrigida nos três lugares errados, a nota de precisão da **BL-211** (o plano mestre corrigiu uma descrição minha de defeito), **DE-041**, **RC-87**, **PE-47** e **BL-243** |
| [DL-018](../planos/DL-018-primeiro-acesso.md) | Primeiro acesso de uma instalação nova: criar o primeiro escritório e o primeiro vínculo **pelo produto**, sem admin técnico | **Integrada (PR #27, `1b828e7`)** — autocadastro assistido do primeiro escritório + primeiro usuário vira ADMINISTRADOR + convite por e-mail para o segundo funcionário (papel ANALISTA). Três contratos expostos em `apps/tenancy/services/primeiro_acesso.py` (`criar_primeiro_escritorio_e_vinculo_admin`, `emitir_convite_para_escritorio`, `aceitar_convite_e_criar_vinculo`), com a exceção `ConviteTokenColidiu` traduzida por handler na view. **17 testes novos** (14 service + 3 view-por-POST real para a BL-218); recusa de `chave não contratada` aplicada nas três views. **Fora do escopo declarado:** SMTP real (etapa posterior), papéis GESTOR/FINANCEIRO/PARALEGAL/CLIENTE no convite inicial, e PE-36 (vínculo usuário-empresa) |
| [DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md) | Portabilidade entre ferramentas de IA: os sete papéis passam a ter **uma fonte** em `docs/agents/papeis/` e arquivos **gerados** para Claude Code e Codex CLI | **Integrada (PR #20, `7e9dc56`)**, encerrada reprovada sob a régua da DE-038, com as pendências de baixa gravidade preservadas no backlog |

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

**AGORA, em 2026-09-16: DL-024 em validação, com a rodada 1 validada
pela CI e CA-4 ainda bloqueada por divergência de superfície.** Branch
`claude/dl-024-execucao` aberta a partir de `1b828e7`. Implementado até
agora:

| Item | Commit | Status local |
| --- | --- | --- |
| **BL-14** atomicidade | `ed861d8` | ✅ 7/7 estáticos + 2 runtime (CI) |
| **BL-16** imutabilidade do `RegistroAuditoria` | `5c86e3f` | ✅ 5/5 estáticos + 5 runtime (CI) |
| **BL-57** trilha PUT/PATCH com diff derivado do contrato | `ed8d829` | ✅ 2/2 estáticos + 3 runtime (CI) |
| **BL-244** trilha do painel administrativo (signal genérico) | `8338037` | ✅ 5/5 estáticos + 2 runtime (CI) |
| **CA-6** matriz de acesso de `/auditoria/` FIXADA por teste | `1671415` | 0/0 estáticos + 8 runtime (CI) |
| **BL-50** teste do gate SQLite/PostgreSQL | já passa (test_configuracao_producao.py — fixado pelo bug do `.env`) | ✅ 5/5 passam |
| **correções da rodada 1** | `febdc9f`, `2613343`, `da59b19`, `5af2c19` | ✅ 1.345 testes na CI, 2 pulados por navegador; migração em banco vazio, lint, formatação e checks verdes |
| **docs** rodada 1 + auditoria | `7b11f90`, `973250b` | ✅ guardas de documentação e Regras do projeto verdes; PR #28 em rascunho |

Branch `claude/dl-024-execucao` está pushed em
`1671415..973250b`. **Pendências da DL-024 que entram na rodada 1 da
auditoria e validação (próximo passo):**

- BL-57 cobre todos os campos derivados de `_campos_gravaveis`, não só
  CNPJ — decisão já tomada, falta confirmar que o auditor valida o
  conjunto exato `{razao_social, nome_fantasia, cnpj, ativo}`.
- Quem vê `detalhes` em `/auditoria/` continua sendo ADMINISTRADOR e
  GESTOR (PE-36/BAS-01 segue com o Fred; CA-6 FIXA esse estado, não
  decide).
- O signal do admin detecta admin por `request.path.startswith("/admin/")` —
  cobertura explícita dos 6 modelos (sem ancorar em `sender=Model`).
  A revisão encontrou que a lista de seis modelos do plano não corresponde
  ao registro atual: `Estabelecimento` só aparece como inline e
  `HistoricoRegimeTributario` não tem ModelAdmin desde a DL-023. A auditoria
  registra a divergência; não se reabre o inline removido nem se cria uma
  porta administrativa sem decisão do responsável.
- A prova runtime local ficou limitada pela indisponibilidade do Docker, mas
  a CI executou a cópia limpa com PostgreSQL no head `5af2c19`: 1.345 testes
  passaram e 2 foram pulados por exigirem navegador real. O bloqueio de
  infraestrutura está encerrado; não confundir os 2 pulos de navegador com
  aprovação de uma verificação não executada.
- O plano documenta alguns caminhos de teste em `apps/empresas/tests/`, mas
  os testes DL-024 efetivos que existem estão em `apps/core/tests/`; a
  validação executada usou os caminhos reais e a divergência fica registrada.

**Falhas pré-existentes registradas, fora do escopo da DL-024:**

- `test_agentes_multiplataforma.py` (10): arquivos em `.claude/agents/`
  estão com modo `0o666` (writable por todos); o gerador deveria
  garantir modo estável independente do umask. Item separado.
- `test_dl019_elo_de_execucao.py::test_o_embrulho_esta_aplicado_em_toda_superficie_que_importou_a_politica`:
  contagem de superfícies que envolvem `recusar_dado_nao_contratado`
  é 1, esperava ≥4. Item separado.

Relatórios integrais e preservados:
[rodada 1](../auditorias/2026-09-16-dl-023-rodada-1.md) e
[rodada 3](../auditorias/2026-09-16-dl-023-rodada-3.md) e
[rodada 5](../auditorias/2026-09-16-dl-023-rodada-5.md) e
[rodada 7](../auditorias/2026-09-16-dl-023-rodada-7.md) — nesta etapa o
número conta **rodadas de trabalho**, não auditorias, e por isso não
existe arquivo de "rodada 2" nem de "rodada 4" nem de "rodada 6".

Para a execução atual da DL-024, o relatório da auditoria de integração está
em [DL-024 rodada 1](../auditorias/2026-09-16-dl-024-rodada-1.md), baseado em
`5af2c19` (código validado na CI) e no registro documental final `973250b`.

**Correção factual, em 2026-09-16, do que escrevi acima ao fechar a DL-018:**
eu disse que "as correções das rodadas 4 e 6 continuam **só na branch**",
e isso estava errado. As duas vieram no mesmo PR #27 que trouxe a
DL-018, porque a branch `claude/dl-018-primeiro-acesso` foi aberta
sobre `bfe9814` (que já tinha `edae1bf`) e o `f23484a` foi commitado
na mesma branch antes do merge. A `main` está, portanto, em
`1b828e7` = merge de `edae1bf + f23484a + (DL-018) + docs`. O que
**falta** é a **medição** dessas duas como integradas — e essa é a
etapa que abre agora.

**A lição é minha, e é sobre mecanismo:** eu abri o PR #24 como **rascunho**, com
o corpo dizendo com todas as letras *"este PR NÃO deve ser mesclado como está"*.
Rascunho no GitHub **não impede merge**, e a palavra do dono do produto vale mais
que a minha marcação. Enquanto a **BL-02** (proteção da `main`) não for fechada
pelo Fred — e ela é ação administrativa dele —, **PR aberto é PR mesclável**, e
eu escrevo os corpos partindo disso.

**O que a rodada 3 mediu, e vale como estado atual:** suíte **1269 passed, 0
falhas, 0 pulados** em cópia limpa; prova por mutação **11 de 11**, com mutantes
escritos pelo auditor; as cinco verificações da integração contínua verdes em
`a612604`, **incluindo "Regras do projeto"** — os três mecanismos impostos
rodaram, contra dois na rodada 1. **Os dois achados altos estão fechados**, e os
dois foram reprovados por execução, não por leitura: a sintética com filha
movimentada agora recebe `200` com a linha do grupo intacta, e a corrida que
dava **500 em 6 de 8** deu **zero 5xx em 12 rodadas**.

**As ressalvas, e a mais importante não é de engenharia:** **BL-261 — integrada (`c7346e6`):** Fred decidiu BLOQUEAR. `Conta.clean()` recusa reparentar conta com movimento para grupo de natureza oposta. Controles positivos preservados: conta livre pode reclassificar para qualquer grupo; conta com movimento pode reparentar para grupo da mesma natureza. **BL-262** — o admin não tem isolamento por escritório em **nenhuma**
superfície; a DL-023 fechou uma de seis, e o `/admin/autocomplete/` é
estruturalmente inalcançável pela camada instalada. Vira etapa própria.

**Como ler essa reprovação, sem eufemismo.** A etapa **entregou** a restrição de
banco (um período de regime aberto por empresa), e o auditor confirmou por
execução própria que ela resiste a ORM direto, `bulk_create` e SQL cru; que a
troca de ordem da exclusão é atômica e sem janela, com trilha correta até sob
falha induzida; e que as 9 defesas novas matam teste, 9 de 9. **O que reprova
são dois casos que a defesa não alcança**, e os dois estão dentro do que a etapa
existe para fechar:

- **BL-245 (ALTA):** conta **sintética** com filha movimentada ainda troca
  natureza e tipo pelo admin. A linha do grupo no Balancete vai de `+1000` para
  `-1000` **com o rodapé continuando a fechar**. O requisito dizia "conta com
  movimento", e a sintética não tem movimento próprio — escrevi a regra pelo
  mecanismo em vez do efeito proibido, contra a **DE-032**. O requisito mudou:
  movimento **próprio ou de descendente**.
- **BL-246 (ALTA):** a etapa **introduziu** um 5xx. `DELETE` de regime sob
  concorrência com o `POST` devolve **500**, em 6 execuções de 8. Não corrompe
  nada (reverte inteiro), mas é a classe da **BL-144** que esta própria etapa
  declarava fechada — e o comentário que eu escrevi em `apps/core/restricoes.py`
  afirmava cobertura que o auditor mediu não existir.

**Dois achados são contra o `arquiteto-senior`, e ficam registrados nesses
termos:** **BL-254** — eu aprovei catorze testes de admin que passam com um
formulário deliberadamente inválido, porque aceitam `status in (200, 302)` e
depois afirmam "nada mudou"; as duas metades são satisfeitas por formulário
quebrado. E **BL-260** — eu declarei a revisão entregue **sem PR**, então dos
três mecanismos que o `AGENTS.md` impõe rodaram dois: a verificação "Regras do
projeto" só roda em `pull_request` e **não foi exercitada**. Quarta ocorrência
da família da BL-147.

A ordem interna da etapa continua **obrigatória**: restrição de banco primeiro,
defesas de modelo depois, admin em terceiro, varredura e prova por mutação no
fim.

**Antes dela, e já integrada:
[DL-022](../planos/DL-022-plano-mestre-e-reconciliacao.md) (PR #23,
`24f6bbc`).** O plano mestre entrou preservado, com a análise do arquiteto
depois dele, e a documentação divergente foi reconciliada. Etapa **documental**:
nenhuma linha de código de produto. As **cinco** verificações da integração
contínua ficaram verdes em `40bc0c2` e de novo em `42951b4` — lidas pelos
`check-runs` da revisão exata, não por suposição (é a regra da BL-137, e o
mecanismo que falta é a BL-236).

**O Fred aprovou duas coisas em 2026-09-16, com a resposta literal *"Sim para os
dois"*:** mesclar o PR #23, e a **fila de execução da seção 16 do plano mestre
como ordem aprovada** (**RC-88**, que fecha a **PE-47**). A consequência prática:
os dois bloqueadores do admin vêm **antes** de DL-016, DL-018 e DL-010, mesmo os
três já tendo plano escrito. O Fred
entregou um plano mestre de evolução por módulos medido sobre `b8c66a6` e pediu
análise mais publicação; o documento está preservado **sem edição** em
[`docs/projeto/plano-mestre.md`](../projeto/plano-mestre.md), com a análise do
`arquiteto-senior` **depois** dele.

**O que o plano mestre mediu e estava errado aqui, agora corrigido:** o README
duplicava a DL-020 com marcações contraditórias; a DL-021 estava descrita como
"planejada, não iniciada" **depois** de integrada, neste arquivo e no plano dela;
e a descrição do defeito da **BL-211** dizia `.first()` "sem `order_by`" quando
existe `Meta.ordering` — o risco real é **sobreposição e falta de desempate**.
Registros novos: **DE-041** (o plano mestre é mapa, não fonte de estado),
**RC-87**, **PE-47** e **BL-243**.

**O que decide a próxima etapa de código é a PE-47:** se a "primeira fila de
execução" da seção 16 do plano mestre é ordem aprovada pelo Fred. Enquanto ela
não for respondida, a sequência que vale é a deste arquivo — e ela **coincide**
com a fila nos dois primeiros itens: fechar **BL-83** e **BL-211** (bloqueadores
de implantação no admin) vem antes de qualquer módulo novo.

0. **[DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md) —
   ENCERRADA em 2026-09-15, reprovada em três rodadas, por decisão do Fred.**

   **Como ler esse encerramento, sem eufemismo:** a etapa **não foi aprovada**.
   A [rodada 3](../auditorias/2026-09-15-dl-019-rodada-3.md) reprovou por um
   achado alto — o marcador ainda perdia conteúdo e vazava texto de controle,
   por uma sintaxe que a correção anterior não previu. Esse achado **foi
   corrigido** antes do encerramento, com prova por mutação. Os outros oito são
   de gravidade baixa; quatro foram corrigidos e **quatro ficam abertos**, em
   BL-190 a BL-194. Nada disso corrompe dado, erra cálculo, vaza entre
   empresas, desbalanceia lançamento, altera período encerrado ou derruba
   servidor — que é a régua da [DE-038](../projeto/decisoes.md), escrita nesta
   etapa justamente porque ela consumiu horas do Fred sem precisar.

   **O que o Fred tem funcionando:** os sete papéis em `.claude/agents/` e
   `.codex/agents/`, fonte única com gerador e guarda de sincronia, o
   `AGENTS.md` apresentando a equipe a qualquer ferramenta, procedimento de
   criar papel executado do zero pelo próprio auditor, guarda contra
   truncamento silencioso do `AGENTS.md` no Codex, e **849 testes**.

   **A frase que resume a etapa inteira, do auditor:** *"O transporte está
   sólido. O que reprova, outra vez, é o conteúdo que viaja."*

   **A lição mais dura, e ela é sobre mim:** implementei as correções da rodada
   2 e o auditor mediu que eu tinha corrigido **contra a lista de exemplos
   dele**, não contra a propriedade que a lista ilustrava — por isso o nono
   caso passou. Nas palavras dele: *"Não digo que foi deliberado; digo que o
   resultado é indistinguível."* É o argumento empírico a favor de o
   implementador e o auditor não serem a mesma cabeça, produzido dentro da
   própria etapa.

   **Histórico das três rodadas:** [Rodada
   1](../auditorias/2026-09-15-dl-019-rodada-1.md) em `ab1ec4e`: 12 achados
   (BL-162 a BL-173). [Rodada
   2](../auditorias/2026-09-15-dl-019-rodada-2.md) em `6667db1`: 10 achados
   (BL-174 a BL-183). **Dos 12 da rodada 1, seis fecharam e nenhum voltou** —
   o que reprova agora são **defeitos criados pelas próprias correções**,
   terceira ocorrência do padrão BL-115.

   **O resultado mais importante da rodada 2 não é achado, é medição:** o
   auditor removeu **15 defesas, uma por vez**, e contou quais testes morriam.
   **14 das 15 mataram teste.** Os testes desta etapa exercitam o defeito que
   dizem cobrir — pergunta que este projeto já errou antes. A única exceção
   virou BL-180.

   **O auditor deu razão ao implementador numa discordância e declarou a
   própria recomendação errada** (achado 9 da rodada 1, sobre `newline=""`),
   com um argumento melhor que o do implementador: `\r` isolado é caractere
   ilegal em string TOML, então a recomendação original teria **criado** uma
   falha de geração. Registro porque auditoria que nunca volta atrás vira
   carimbo.

   **Dimensão indicada para a rodada 3:** o **efeito colateral de cada
   correção**. As rodadas 1 e 2 mediram o conteúdo e a mentira; a 3 mede o
   troco. De cada correção: *o que ela passa a reprovar que antes passava, e o
   que passa a aceitar que antes reprovava?* O A3 é o caso exemplar — um guarda
   que reprova clone limpo em máquina de usuário comum, com remediação que não
   converge.

   **BLOQUEIO OPERACIONAL EM 2026-09-15, e não é falha técnica:** o
   `desenvolvedor-pleno` foi interrompido pelo **limite de uso da plataforma**
   (HTTP 429, `claude-sonnet-5`) **antes de começar** as correções da rodada 3.
   Nada foi alterado por ele; a árvore estava no estado de `500dbee`. Os
   auxiliares usam o mesmo modelo e estavam sob o mesmo limite. **O Fred
   autorizou que eu assumisse a implementação**, e assumi: as nove correções
   dos achados da rodada 2 são minhas. A separação essencial permanece — a
   independência que importa é a do `auditor-qa`, que não escreveu nada disto e
   é quem valida. Registrado para não virar decisão silenciosa: **nesta rodada,
   quem implementou foi o líder.**

   **Correções da rodada 2, concluídas em 2026-09-15.** Nove achados fechados
   (BL-174 a BL-180, BL-182, BL-183); BL-181 fica como **pendência declarada**,
   porque exige confirmar em documentação oficial quais nomes de ferramenta o
   Claude Code aceita — e o projeto não valida contra lista inventada. A suíte
   foi de **817 para 846 testes**.

   **Prova por mutação, feita por mim antes de devolver à auditoria:** removi
   uma a uma as nove defesas novas e medi quais testes morriam. Oito mataram de
   imediato. **A nona não matou nenhum** — e isso virou BL-185: ao corrigir o
   A3, o `chmod` que fixa o modo do arquivo não tinha teste próprio, porque os
   testes de `umask` passavam só pela tolerância do verificador. Era o **padrão
   do achado A7 se repetindo dentro da correção do A3**. Corrigido, e agora
   mutar o `chmod` mata o teste. Registro porque é o argumento inteiro desta
   etapa: *sem a mutação, eu teria entregado a mesma classe de defeito que
   estava corrigindo.*

   **Achado meu, encontrado depois das duas auditorias (BL-184):** varri o
   repositório **inteiro** em vez da lista de arquivos de cada achado, e
   encontrei três afirmações desmentidas ainda vivas — `CLAUDE.md` dizendo que
   geramos formatos para Copilot e Gemini (terceira ocorrência do mesmo erro
   meu), e dois arquivos afirmando que o **Gemini CLI lê `AGENTS.md`
   nativamente**, o que é falso e foi escrito na DL-014 **sem fonte**. A
   [DE-034](../projeto/decisoes.md) já mandava varrer pela **classe** e não pela
   linha; levei três repetições para aplicar a regra que o projeto já tinha
   escrito, agora também para documentação.

   **A dimensão medida foi a viagem do conteúdo**, e o veredito separa bem as
   duas metades: *"a promessa de fonte única é sólida na mecânica de geração e
   frágil na honestidade do texto gerado. O que reprova é o conteúdo que viaja,
   não o transporte."*

   **Passou:** fidelidade do TOML sob `"""`, emoji, BOM e linha de 600
   caracteres; idempotência; ordem estável; critério 1 confirmado de forma
   independente; procedimento de criar papel executado do zero pelo auditor,
   sem resíduo; suíte sem rastro na árvore.

   **Reprovou:** os arquivos do Codex afirmam `Essa restrição é **técnica**`
   sobre restrição que lá não existe (BL-162), e o gerador aceitava `nome` sem
   validação, gravando fora do destino (BL-163).

   **Dimensão indicada para a rodada 2:** o **caminho inverso** — não se o
   conteúdo chega íntegro, mas se o que chega **mente**. Cruzar cada afirmação
   de mecanismo dos derivados com a ferramenta de destino, e cada campo
   declarado na fonte com o que o arquivo gerado realmente concede.

   **Três defeitos achados por três caminhos diferentes, que é o argumento da
   equipe existir:** o órfão não removido, pelo **desenvolvedor ao executar** o
   procedimento em vez de só escrevê-lo; a suíte sujando a árvore, por **mim na
   revisão do diff**; e a mentira no texto gerado, pelo **auditor**, que é o
   único que não participou de escrever nada disso. Nenhum dos três apareceria
   pelos outros dois caminhos.

1. **[DL-017](../planos/DL-017-interface-da-contabilidade.md) — APROVADA COM
   RESSALVAS na [rodada 6](../auditorias/2026-09-15-dl-017-rodada-6.md).**
   Primeira aprovação em seis rodadas. O auditor escreveu como ela deve ser
   lida, e vale citar: *"não é 'está pronto', é 'está certo o suficiente para
   integrar, com dez coisas nomeadas que ainda faltam, nenhuma delas capaz de
   corromper dado, vazar entre empresas, desbalancear um lançamento ou derrubar
   o servidor'."*

1. **[DL-020](../planos/DL-020-consolidacao-pos-auditoria.md) — consolidação,
   INTEGRADA em 2026-09-15 (PR #21, `0dd07b4`).** Catorze itens: as dez
   ressalvas da rodada 6 (BL-195 a BL-204) e as quatro regras que o Fred
   confirmou (BL-205 a BL-208). A
   [DL-017](../planos/DL-017-interface-da-contabilidade.md) está **integrada na
   `main`** (PR #19, `60cbcff`).

   **Por que esta etapa veio antes da DL-010**, e o motivo é um só: **BL-198 — um
   lançamento com a data errada não aparece em nenhuma tela de operação
   normal**, e o balancete do período concilia, então nenhuma conferência acusa.
   É o único item aberto em que o usuário **não consegue conferir o que não
   aparece**. Decisão apresentada ao Fred com as três opções e o trade-off; ele
   mandou seguir a recomendação.

   **A renumeração do BL-242 fechou o último bloqueador.** `RC-81`, `RC-82` e
   `PE-44` tinham dois significados nas DL-019 e DL-020. Renumerados para
   `RC-85`, `RC-86` e `PE-46`, com tradução registrada no plano, e o teste de
   unicidade agora impede a recorrência. Os quatro relatórios de auditoria da
   DL-020 e os três da DL-019 ficam preservados sem edição; nenhum dos sete foi
   descartado.

   **Itens abertos que atravessam etapas seguintes, sem afetar o
   encerramento:** **BL-211** (os dois defeitos do admin — não devem atravessar
   a DL-010), **BL-229** (medições de CSS que pulam na CI, registrado pelo
   auditor), **BL-235, BL-236, BL-237, BL-238, BL-239, BL-241**. A linha da
   BL-211 é a próxima entrada da sequência recomendada.

2. **[DL-021](../planos/DL-021-robustez-do-gerador-no-windows.md) — robustez do
   gerador de papéis em ambiente Windows, INTEGRADA em 2026-09-15 pelo PR #22
   (`main` em `b8c66a6`).** O que fechou foi a **quebra de linha**; a pendência
   de **permissão `0o666` no Windows** continua aberta, declarada no plano e
   ligada ao achado A3 (BL-175). Identificada na retomada da DL-020, em
   2026-09-15, quando o verificador byte-strict (achado 9 do DL-019) reportou
   14 derivados "fora de sincronia". Diagnóstico: o gerador grava via
   `Path.write_text` que, em Windows, converte `\n` em `\r\n` na escrita, e o
   `core.autocrlf=true` do clone do Fred normaliza o `git diff` em silêncio,
   escondendo o problema. Correção: trocar a escrita para `write_bytes(...)
   com a codificação UTF-8 explícita, e adicionar `.gitattributes` com
   `*.md text eol=lf` e `*.toml text eol=lf` como rede de segurança.
   **Porque entra agora, antes do Passo 1 (BL-83 + BL-211):** rodar
   `--verificar` no Windows depois de mesclar a DL-020 é **necessidade
   operacional**, não cosmético. O Fred registrou a regra em 2026-09-15 —
   *"guarda que grita sem motivo é pior que guarda nenhuma, porque quando
   gritar com motivo ninguém olha. E há o cenário pior — numa máquina com outra
   configuração, o CRLF entra no repositório."* — e ela vale também como
   guarda contra um arquivo CRLF versionado por engano.

   **⚠️ BL-195 tem ordem obrigatória:** tirar o descarte do perfil da região
   julgada **antes** de mexer no timeout. O contrário reabre o bloqueador da
   rodada 5 — medido 3 de 3 pelo auditor.

   **Distribuída em 2026-09-15, a partir da revisão `cb08fb7`**, com os dois
   implementadores trabalhando em paralelo na mesma árvore e conjuntos de
   arquivos disjuntos:

   | Responsável | Itens | Pode editar |
   | --- | --- | --- |
   | `desenvolvedor-pleno` | BL-196 (módulo e API), BL-198(b), BL-200, BL-204, BL-205, BL-206, BL-207 no domínio | `apps/core/**`, `apps/contabilidade/views.py`, `serializers.py`, `services.py`, `models.py` e migração, `apps/tenancy/**`, `apps/empresas/**`, testes `test_dl019_*` que não terminem em `_frontend` |
   | `especialista-frontend` | BL-195, BL-196 nas telas, BL-197, BL-198(b) na renderização, BL-199, BL-203, BL-207, BL-208 | `views_web.py`, `urls_web.py`, `templates/**`, `static/**`, `test_dl017_*`, `test_dl019_frontend*`, `docs/assets/telas/*.png` |
   | `arquiteto-senior` | documentação, `.github/workflows/**`, integração e commit | os demais |

   Nenhum dos dois commita: a integração é do `arquiteto-senior`, porque dois
   agentes mexendo no índice ao mesmo tempo corrompem o commit.

   **⚠️ O contêiner da sessão reiniciou em 2026-09-15 e matou os dois
   implementadores no meio do trabalho, sem relatório.** O sistema de arquivos
   sobreviveu, então o código está todo no repositório (commits de preservação),
   mas **a declaração de o que estava pronto, não**. Isso foi resolvido por
   **inventário por execução**, não por confiança. Estado medido pelo
   `arquiteto-senior`, sozinho na máquina, na revisão de integração:

   | Verificação | Resultado |
   | --- | --- |
   | `ruff check .` | 0 |
   | `ruff format --check .` | 0 |
   | `python manage.py check` | 0, sem problemas |
   | `python manage.py makemigrations --check --dry-run` | `No changes detected` |
   | `pytest -q -rs` | **907 passed**, 0 falhas, 0 pulos |

   A suíte era de **766** testes quando a DL-017 foi integrada. **`pwsh` não
   existe neste contêiner**, então `scripts/validate-docs.ps1` está
   **Bloqueado** e só a CI o executa.

   **O que o inventário mediu, item por item** (a etiqueta é do inventário, não
   minha): **Testados** — BL-195, BL-200, BL-205, BL-206, BL-207, BL-209.
   **Parciais** — BL-196, BL-198, BL-204. **Código sem teste** — BL-199, BL-203,
   BL-208. **Testado com a defesa demonstrada** — só a **BL-197**. A evidência
   de cada um está no próprio item do [backlog](../projeto/backlog.md), com
   arquivo e linha.

   **Dois erros meus nesta etapa, registrados porque são a classe que ela
   ataca:**

   1. **Afirmei ao Fred que o admin do Django permitia criar lançamento datado
      `9999-12-31`**, e chamei isso de "o mais grave" na BL-211. **É falso.**
      `LancamentoContabilAdmin.has_add_permission` devolve `False`
      (`apps/contabilidade/admin.py:83`), e já era assim em `60cbcff`. Eu inferi
      o buraco de "o admin registra o modelo" **sem abrir o `ModelAdmin`** —
      afirmar sem medir, no item mais sensível da etapa. Corrigido no backlog.
   2. **Lancei um agente que escrevia e outro que media ao mesmo tempo, na mesma
      árvore e no mesmo banco.** "Medição concorrente não é medição" já estava
      registrado neste projeto e eu o repeti. O inventário salvou o resultado
      porque detectou a árvore se movendo e separou duas medições (estado A,
      `1 failed, 894 passed`; estado B, `907 passed`) — mas isso foi mérito dele,
      não desenho meu. **Corrigido por mecanismo na rodada 2:** cada
      implementador recebeu um banco próprio (`DATABASE_URL` apontando para
      `dataledger_b` no segundo), verificado antes de distribuir. O Django cria
      o banco de teste sozinho, então o segundo nem precisa existir.

   ### Rodada 2 da DL-020 — o que ela entregou

   Medido por mim, sozinho na máquina, na revisão `a497046`: `ruff check` **0**,
   `ruff format --check` **0**, `manage.py check` **0**, `pytest -q -rs` →
   **1027 passed, 0 falhas, 0 pulos**. Eram **766** na integração da DL-017 e
   **907** no começo desta rodada.

   **Backend, entregue e fechado:** BL-204, BL-214 e BL-196 (partes a e c). As
   duas varreduras prometidas passam a existir e **foram vistas reprovar**.

   **O mecanismo funcionou no primeiro uso:** a varredura de contratos acusou
   `apps.empresas.views.criar_empresa` — a tela de cadastro de empresa era a
   **única** superfície de escrita do repositório sem a política dos cinco
   dicionários, e **seis rodadas de auditoria não a tinham visto**. Não entrou
   como exceção: a política foi aplicada e testada, e os dois registros de
   exceção ficaram **vazios**.

   **Mutantes de backend: 6 aplicados, 6 mortos, 0 sobreviventes** — entre eles
   o **M16**, o mutante do estorno que sobreviveu a 766 testes.

   **Frontend: entregue, com uma ressalva que vai para o auditor.** O primeiro
   agente foi morto por **limite de sessão** no meio da rodada de mutantes,
   dizendo *"dois sobreviventes — os dois são achados"* e **sem dizer quais**.
   Entregou BL-199, BL-215 e 27 testes novos (BL-149b, BL-198 nas telas, BL-203,
   BL-208, BL-213). A rodada foi **refeita do zero**, não presumida:
   **13 mutantes aplicados, 13 mortos, 0 sobreviventes** — os 11 que eu listei
   mais **2 que o implementador acrescentou** ao ler o código, nos vizinhos de
   campo que a DE-034 aponta. Cada um com a **previsão escrita de qual teste
   deveria matá-lo antes de rodar**, e cada um morreu no teste previsto. Nenhum
   teste precisou ser reforçado: já eram fortes.

   ⚠️ **A ressalva fica aberta e vai para o auditor.** Os dois sobreviventes que
   o agente morto declarou **não foram reproduzidos**, e há duas explicações que
   eu **não consigo distinguir**: (a) ele já havia reforçado os testes antes de
   morrer, e a mensagem precedeu esse trabalho; (b) eram mutantes **diferentes**
   dos 13 tentados. **Não se declara resolvido o que não se sabe** — quem tem de
   provar é o auditor, não eu.

   Registrado junto um ponto fraco medido: o mutante "mostrar o aviso sempre"
   morreu por `AttributeError`, não por asserção, porque a consulta devolve
   `None` e não dicionário vazio. O teste pega o defeito **por acidente de
   tipo**. Morte por erro é morte mais frágil que morte por asserção.
   **O auditor atacou esse ponto com a forma que não estoura** — um dicionário
   fabricado com os dois lados nulos, truthy, que renderiza a caixa vazia — e
   ela **morreu por asserção, em três testes**. Julgou a defesa suficiente.

   ### Duas auditorias reprovaram, e o estado medido hoje

   **Rodada 1 (`b13d41a`): REPROVADO**, 9 achados. **Rodada 2 (`d97a188`):
   REPROVADO**, 8 achados novos, dois bloqueadores. Os dois relatórios estão em
   [docs/auditorias/](../auditorias/), **preservados integralmente**.

   **O pior achado foi contra mim, e não foi um caso: foi um método.** Eu aprovei
   a correção do bloqueador da rodada 1 **depois de verificá-la com as minhas
   mãos** — construí a superfície desprotegida e vi a varredura acusar. O que eu
   não vi é que estava olhando o **mapa fixo de retaguarda** funcionar, e não o
   mecanismo que eu tinha aprovado no plano: `initkwargs["actions"]` **nunca
   executou**, porque o DRF põe `actions` como atributo próprio da view. A minha
   superfície de teste por acaso usava os nomes do mapa. *Verifiquei a coisa
   certa pelo caminho errado, e declarei o caminho.*

   **Estado em `685abf3`, medido nas duas árvores e com a CI lida:**

   | Onde | Resultado |
   | --- | --- |
   | Árvore de trabalho | 1077 passed, exit 0 |
   | **Cópia limpa da revisão commitada** (`git status` vazio, **zero** arquivos ignorados) | **1077 passed, exit 0** |
   | **CI, `check-runs` da revisão exata** | `Lint e testes = success`, `Validar documentação = success` |
   | **CI, log do job** | **1075 passed, 2 skipped**, 59,89 s |

   **A linha `BL-218: toda superfície de escrita da varredura foi exercitada`
   aparece no log da CI** — o mecanismo que estava desligado lá (sessão vermelha
   fazia a conferência sair cedo) voltou a rodar.

   **Os 2 pulos são as medições de CSS**, com motivo declarado no log:
   `/usr/bin/chromium: timeout de 30s`. O critério 3 da etapa está atendido pelo
   ramo "pula com motivo", **não** pelo ramo "roda". Eu havia dito que elas
   "rodaram e passaram" — verdade **na minha árvore**, falso na CI. Virou
   **BL-229**: o runner tem `google-chrome` fora de snap e a seleção tenta o
   chromium primeiro.

   **Duas retratações ficam registradas, a minha e a do auditor.** Ele mediu a
   rodada 1 numa árvore contaminada, declarou *"nenhum número declarado estava
   errado"*, e **retratou por escrito antes de me cobrar**. Eu repeti "1058
   passed" ao Fred **quatro vezes** enquanto a CI dizia `1 failed, 1055 passed,
   2 skipped`. A regra que decorre disso vale para os dois papéis: **declaração
   de suíte verde diz em que árvore foi medida, e a árvore que vale é a limpa.**
   Mecanismo em **BL-227**, cumprida pela primeira vez nesta revisão.

   ### Rodada 3 e a correção — estado em `2d1bc37`

   **Rodada 3 (`05c2a6d`): REPROVADO**, um achado ALTA (C1) e seis menores.
   **B1 a B8 fechados**, todos verificados pelo auditor com mutante próprio.

   **O padrão que três rodadas revelaram, e que vale mais que os três achados:**
   as três fugas moram **no mesmo lugar** — a fronteira entre o que a varredura
   **lê** e o que o framework **faz em tempo de execução**. `getattr(classe,
   "post")` em vez do que o roteador liga; `initkwargs["actions"]` em vez de
   `callback.actions`; `http_method_names` da classe em vez do da rota.
   **Exigência permanente que decorre disso:** toda leitura estática de
   comportamento de framework precisa de **teste de precedência** — dois valores
   que existem, divergem, e o teste prova qual vence **por comportamento**.

   **Estado em `2d1bc37`:**

   | Onde | Resultado |
   | --- | --- |
   | Cópia limpa da revisão gravada (`git status` vazio, **zero** ignorados) | **1105 passed, exit 0** |
   | **CI, `check-runs` da revisão exata** | `Lint e testes = success`, `Validar documentação = success` |
   | **CI, log do job** | **1103 passed, 2 skipped**, 62,68 s |

   Eram 1077. Os 2 pulos continuam sendo as medições de CSS (BL-229).

   **Uma quebra de regra declarada pelo implementador**, e verificada por mim:
   ele rodou `ruff format` sem `--check`, o que é proibido. Peguei o arquivo na
   revisão anterior e rodei `ruff format --check` nele — *"1 file already
   formatted"*. Como a base já estava formatada, o comando **só pôde tocar
   linhas dele**. Dano nulo, e o registro fica porque ele registrou em vez de
   esconder.

   ### Rodada 4, a renumeração e o estado final desta etapa

   **Rodada 4 (`b2f6112`): REPROVADO — e com recomendação de ENCERRAR.** O
   auditor entregou as duas metades sem arredondar uma na outra: *"reprovar aqui
   não é dizer 'faça de novo'; é dizer **não integre assim**"*. Motivo da
   reprovação: **D4**, a colisão de numeração — **não o código**.

   **C1, C2, C3, C5 e C7 fechados**, verificados por ele. A frase dele que
   resume o custo e a entrega da etapa:

   > **"Quatro rodadas, quatro achados no meu mecanismo de medição, zero no
   > produto."**

   #### A renumeração (D4), autorizada pelo Fred

   Duas sessões partiram de `60cbcff` usando **DL-019**. A outra integrou
   primeiro (PR #20), então **esta se moveu**: `DL-019` → **`DL-020`**,
   `BL-148..BL-193` → **`BL-195..BL-240`** (some 47), `DE-035` → **`DE-039`**,
   e os quatro relatórios renomeados. Tabela de correspondência no fim do
   [plano](../planos/DL-020-consolidacao-pos-auditoria.md).

   **O auditor detectou a colisão sozinho, sem ser informado**, e chegou à mesma
   recomendação. E viu a metade que eu **não** tinha visto: os `BL-xxx` citados
   **dentro do código de teste** — *"essa metade é silenciosa: o Git não
   avisa"*. Eu tratava como higiene; é rastreabilidade.

   **A `main` foi integrada ANTES do PR**, como ele exigiu. Dois conflitos, os
   dois em documentação, **resolvidos mantendo os dois lados**. O `backlog.md`
   **mesclou sozinho** — a renumeração pagando o próprio custo. **Os sete
   relatórios sobreviveram**: três da outra etapa, quatro desta. Nenhum
   descartado, **nenhum editado**.

   #### Estado medido em `deacd1d`

   | Onde | Resultado |
   | --- | --- |
   | Cópia limpa da revisão gravada (`git status` vazio, **zero** ignorados) | **1196 passed, exit 0** |
   | **CI, `check-runs` da revisão exata** | `Lint e testes = success`, `Validar documentação = success` |
   | **CI, log do job** | **1194 passed, 2 skipped**, 62,69 s |

   Os 2 pulos continuam sendo as medições de CSS (**BL-229**).

   **BL-237/D1 fechada na parte que era condição** — a fronteira do despacho
   deixou de ser silenciosa, com tabela de efeito medido e três testes que
   **medem o silêncio**. O mecanismo segue **opcional e aberto**, por decisão
   declarada do auditor.

   **Aberto e nomeado:** BL-235 (a antiga A9), BL-236 (o mecanismo da leitura da
   CI — **ato, não mecanismo**), BL-238, BL-239, BL-237 na parte opcional,
   BL-229, e **BL-211 com A2 e A3**, que *não devem atravessar a DL-010*.

   ### A DE-034 percorrida item por item — achado A4 da auditoria

   Este é o **critério 2 da etapa**, que eu escrevi e **não cumpri**: o auditor
   mediu por `grep` que o `estado.md` citava a DE-034 duas vezes, ambas de
   passagem, sem percorrer nenhum dos três itens numerados. *"Regra numerada que
   se cumpre por leitura vira regra cumprida em dois terços"* é frase do próprio
   auditor, de uma rodada anterior, e ela se cumpriu em cima de mim.

   Os campos que a DL-020 corrigiu são **quatro**: `data` de lançamento (RC-77),
   `vigencia_inicio` de regime (RC-85), o número de partidas (RC-79) e o
   conjunto inteiro que a política dos cinco dicionários julga.

   **Item 1 — os demais campos do mesmo dicionário da requisição.**
   *Percorrido.* No POST de lançamento, `data` vizinha de `historico`,
   `chave_idempotencia`, `num_linhas` e das chaves `conta_*`/`tipo_*`/`valor_*`:
   todas passam por julgador próprio (`para_data`, `para_decimal`, `para_id`,
   `_inteiro_de_cliente`), e a política dos cinco dicionários recusa qualquer
   chave fora do contrato. No POST de regime, `vigencia_inicio` vizinha de
   `regime`, que tem gramática de escolha desde a BL-141. *O que ficou:* nada
   neste item.

   **Item 2 — o mesmo campo nas outras superfícies.** *Percorrido em parte, e
   foi aqui que ficaram os dois achados.* Para `data` de lançamento, percorri
   serviço, API, tela, estorno **e admin** — e o admin foi o achado do
   `desenvolvedor-pleno` que virou a BL-211. Para `vigencia_inicio`, percorri
   API e admin, e o validador de modelo faz a **faixa** valer nas duas.
   *O que ficou, e o auditor mediu:* **(a)** a faixa valeu no admin mas a
   **vigência crescente não** — pelo inline nascem dois períodos abertos ao
   mesmo tempo, e o estado não se cura sozinho (A2); **(b)** eu tratei
   "superfície" como "as superfícies que existem hoje" e não como "as que podem
   nascer", e por isso a varredura foi aceita com uma fronteira que não cumpre o
   que declara (A1). **Os dois achados moram neste item.** Não é coincidência: é
   o item que a rodada 6 também não executou, pela segunda vez.

   **Item 3 — as demais restrições do mesmo `Meta`.** *Percorrido, e virou
   mecanismo.* Era a origem da BL-204 (duas `CheckConstraint` de CNPJ sem
   tradução, a outra metade do `Meta` que a BL-144 fechou). Deixou de ser
   conferência manual e virou a varredura de restrições, que percorre **todos**
   os modelos e foi vista reprovar. *O que ficou:* a fronteira dela também está
   declarada como completa sem ser — `unique_together` é invisível (A6), e três
   índices implícitos estão presos na lista sem razão escrita (A7).

   **A lição, para a DL-010 não repetir:** os três itens não têm o mesmo custo.
   O item 1 se resolve olhando a função; o item 3 virou mecanismo e agora se
   resolve sozinho; **o item 2 é o caro**, porque exige perguntar "por onde mais
   este dado entra" incluindo portas que ainda não existem. Duas rodadas
   seguidas de auditoria acharam o resíduo exatamente nele.

   **Um critério meu foi retirado por inexequível**, e a razão fica: eu exigira
   "varredura provando que cada view de POST tem **teste** dos cinco
   dicionários". Amarrar superfície a arquivo de teste exigiria casamento de
   nome por heurística — **exatamente o erro da BL-213**. A varredura prova que
   a política é **chamada**, e não finge provar mais.

   **Três contratos que eu fixei na distribuição**, para os dois não negociarem
   no meio do caminho — e para nenhum número de negócio ficar declarado em dois
   lugares, que é como a documentação divergiu três vezes:

   1. A política dos cinco dicionários (BL-196) mora em `apps/core/requisicao.py`,
      escrita pelo `desenvolvedor-pleno`: uma função que recebe a requisição e a
      declaração do que a view aceita, e levanta **uma** exceção carregando a
      razão e a lista de chaves ofensoras em separado. Quem responde é a view.
   2. A faixa de data do RC-77 e o teto de 200 do RC-79 têm fonte única em
      `apps/contabilidade/services.py` — mínima como constante, máxima como
      **função** (é "hoje + 30 dias", que se move). O teto de 200 deixa de ser
      número de tela e passa a ser regra de domínio no serviço de criação, para
      que a **API também o herde** (item 2 da DE-034: o mesmo campo nas outras
      superfícies).
   3. No BL-198(b), a consulta "há movimento fora do período consultado" é do
      `desenvolvedor-pleno`, em `services.py`; a renderização do aviso nas
      quatro saídas é do `especialista-frontend`.

   **Correção do contrato 2, em 2026-09-15, por um achado do
   `desenvolvedor-pleno`:** o **admin do Django** também grava, sem passar pelo
   serviço — ele encontrou `HistoricoRegimeTributarioInline` escrevendo
   `vigencia_inicio` por fora de `registrar_regime_tributario`, e eu conferi que
   `LancamentoContabilAdmin` tem o mesmo problema para a data. Consequência:
   **pelo admin dá para criar lançamento datado `9999-12-31`, invisível nas
   quatro saídas** — o BL-198 por uma porta que ninguém tinha olhado. Logo a
   faixa do RC-77 precisa existir no **modelo**, e `models.py` não pode importar
   de `services.py` (import circular). O lugar canônico da faixa passa a ser um
   módulo **puro, sem ORM**, com `services.py` importando de lá e mantendo
   reexport para não quebrar o `especialista-frontend` no meio do trabalho. A
   varredura completa do admin é a **BL-211**, e **não** é desta etapa.

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
8. **Quatro decisões contábeis respondidas pelo Fred em 2026-09-15**, e que
   viram código na rodada seguinte: faixa de data de lançamento de 01/01/2000 a
   hoje + 30 dias (**RC-77**); estorno nunca anterior ao original, recusar
   (**RC-78**); teto de 200 partidas com recusa explícita (**RC-79**); conta sem
   contas-mãe avisa e deixa criar (**RC-80**). Fecham PE-42 e PE-43. As três que
   não eram de sim ou não foram reescritas por mim como proposta concreta antes
   de perguntar — presumir regra contábil é o que o projeto proíbe.

   **Quinta decisão, no mesmo dia: RC-85** — o escritório **não** registra
   regime tributário com vigência futura, então `vigencia_inicio` nunca é
   posterior a hoje. Fecha a alínea (a) da PE-46 e, com ela, a "porta de mão
   única" do achado R6-6 **por construção**: com o teto em "hoje", `date.max`
   nunca entra e amanhã sempre existe data posterior à última registrada — a
   regra de vigência crescente deixa de poder travar a empresa para sempre.
   O **piso** de `01/01/2000` é **HI-07**, hipótese minha herdada do RC-77, que
   fala de data de lançamento e não de regime. Declarada como tal no código.

   **Sexta decisão, também em 2026-09-15: RC-86** — regime tributário errado se
   corrige **apagando** o registro, não registrando uma correção que o
   substitui. O Fred escolheu isso **contra a minha recomendação**, e a escolha
   dele é a que vale: regime é dado **cadastral**, não escrituração, e é ele
   quem precisa provar coisas a cliente e a fisco. **Fecha a PE-46 por
   completo.** O alcance técnico é meu e está em **DE-039**: apaga-se só o
   **último** período, a exclusão devolve o anterior à condição de vigente, e o
   **evento** de exclusão é gravado em `RegistroAuditoria`. O registro sai do
   histórico do produto; a trilha técnica fica, porque o `AGENTS.md` a torna
   obrigatória e ela não é o que ele estava escolhendo. Virou **BL-209**, e a
   guarda para quando existir apuração fiscal virou **BL-210** — registrada
   antes de a apuração existir, de propósito. **Nada disso vale para lançamento
   efetivado:** ali a correção segue por estorno e apagar continua proibido.
9. **Decisões que dependem do Fred:** **HI-07** (o piso de `01/01/2000` para
   vigência de regime é hipótese minha, não confirmação dele — a PE-46 está
   fechada nas duas alíneas, por RC-85 e RC-86, mas o piso nunca foi
   perguntado), PE-36 (quem lê contabilidade e se há vínculo usuário-empresa), PE-38 (lucros
   e prejuízos acumulados na implantação), PE-20, PE-21, PE-22, PE-23, PE-25,
   PE-30 a PE-35.
10. **BL-02 — proteção da branch `main`.** Ação administrativa no GitHub: a API
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

**Três itens acrescentados pelo `auditor-qa` na rodada 6**, que julgou a lista
acima *"correta em tudo o que afirma, e incompleta em três pontos"*:

7. **Há portas que aceitam e descartam sem avisar.** Enviar um campo do
   formulário como **arquivo**, na tela de conta, grava a conta na **raiz do
   plano** com mensagem de sucesso — muda a indentação, o nível e o Balancete
   por nível. Querystring num POST e campo desconhecido no corpo são ignorados
   em silêncio em 5 das 7 superfícies de escrita; só a tela de lançamento
   recusa.
8. **Registrar regime tributário com vigência no ano 9999 é irreversível pelo
   produto.** Nenhum regime pode mais ser registrado para aquela empresa, e não
   há edição nem exclusão — só acesso direto ao banco desfaz.
9. **A chave de idempotência nunca expira.** Reusar a mesma chave meses depois
   devolve o lançamento antigo em vez de criar um novo. É coerente com o
   desenho; **não está decidido nem documentado como decisão**.

E dois itens da lista ficaram **incompletos**, não errados:

- **Item 2, faixa de data:** falta o **efeito**, que é o que importa. Um ano
  digitado errado (um `9` no lugar de um `2`) põe o lançamento em `9999-12-31`,
  e ele **não aparece em nenhuma tela de operação normal** — nem Diário, nem
  Razão, nem Balancete, nem Conferência — e **nada avisa que existe movimento
  fora do período**. O balancete do período concilia, então nenhuma conferência
  aponta. Para achar, é preciso suspeitar e alargar o período até o ano 9999.
- **Item 3, estorno:** o estorno recebe **sempre a data de hoje**, nunca a do
  original, e **pode ficar anterior ao lançamento que estorna** — sem aviso e
  sem teste.

O auditor declarou, e eu subscrevo: **ninguém aqui afirma que o sistema está
livre de defeitos, que é seguro, ou que está em conformidade legal.** Afirmamos
o que medimos, e está registrado o que não medimos.

## Estado do repositório

- **`main` em `24f6bbc`**, medida por consulta ao remoto em 2026-09-16: DL-017
  pelo PR #19, DL-019 pelo PR #20, **DL-020 pelo PR #21** (`0dd07b4`),
  **DL-021 pelo PR #22** (`b8c66a6`) e **DL-022 pelo PR #23**.
- **Suíte na CI de `b8c66a6`:** **1200 passed, 2 skipped**, Python 3.14 e
  PostgreSQL 16. Os 2 pulados são as medições de CSS que exigem navegador
  (**BL-229**). Registro honesto: essa contagem é a da **integração contínua**,
  não a de uma árvore de trabalho — foi justamente declarar suíte verde medindo
  na árvore suja que produziu um relatório errado quatro vezes na DL-020.
- **Branch de trabalho `claude/accounting-agent-team-setup-mn6lyf`**, reiniciada
  a partir de `origin/main` para a **DL-022**. A etapa anterior dessa mesma
  branch (DL-020) já está mesclada; nada foi empilhado sobre histórico
  mesclado.
- **Histórico:** antes disso, a retomada da DL-020 corrigiu o bloqueador BL-242,
  acrescentou a guarda de unicidade de `RC-xx`/`PE-xx` e registrou a orientação
  de produto DE-040, com **1194 passed, 2 skipped** medidos em cópia limpa.
- A verificação que vale é em **árvore limpa**: `git archive <hash> | tar -x` em
  diretório vazio, e rodar ali (BL-81). Medir na árvore de trabalho já produziu
  um relatório errado. Nesta retomada o transporte Windows→Linux converteu
  finais de linha e levou `__pycache__` com caminhos absolutos; esses artefatos
  foram removidos **somente do snapshot temporário**, os derivados foram
  regenerados pelo script oficial e `--verificar` confirmou 7 papéis/14
  arquivos antes da execução válida.
- Pendência herdada da DL-002: a proteção da branch `main` nunca foi
  configurada. **Medido outra vez em 2026-09-16**, por consulta à API do GitHub:
  `protected: false`, sem rulesets. **BL-02** continua aberta e é ação
  administrativa do Fred — nenhum agente pode fechá-la.
- **Onde ler para onde o projeto vai:**
  [`docs/projeto/plano-mestre.md`](../projeto/plano-mestre.md). Ele é **mapa de
  decomposição, não fonte de estado** (**DE-041**): estado é aqui.

### Sobre os commits marcados como "preservação, não entrega"

O histórico tem vários. Eles existem porque este ambiente é **efêmero** e um
gancho exige árvore limpa ao fim de cada turno: commitar protege o trabalho de
um agente que ainda está executando, mas **não** o aprova. Cada um desses
commits declara, na própria mensagem, o que foi verificado e o que não foi, e
qual é a última revisão com auditoria completa. Não confunda com entrega.

## Ambiente de verificação

Registrado para quem for reproduzir:

- Windows 11, Python 3.14.7 em `.venv`, pip 26.2.1, Ruff 0.16.7 e pytest 9.1.1.
- Docker Desktop 4.90.0, engine 29.7.2 e PostgreSQL 16 em contêiner descartável.
- `scripts/validate-docs.ps1` foi executado no PowerShell local e aprovou os 79
  arquivos Markdown; a CI do novo commit ainda é evidência pendente.
