# Estado atual da equipe de agentes

A DL-023 entrou na `main` pela rodada 2, após auditoria reprovada na rodada 1;
o que mudou entre uma e outra está na tabela de etapas e no histórico.

> ⚠️ **Este parágrafo já afirmou a revisão exata da `main`, e a afirmação
> nasceu falsa.** Dizia `8235635`; quando o auditor conferiu (achado B1 da
> [rodada 3](../auditorias/2026-09-18-dl-024-rodada-3.md)) a `main` estava em
> `bfe9814` — mesclado **22 minutos depois**, pelo PR que integrou *este
> próprio arquivo*. Quando fui corrigir, já estava em `b588af9`.
>
> A lição não é "manter atualizado": é que **SHA da `main` não se escreve
> aqui**. Ele muda a cada merge, inclusive pelo merge deste documento, e
> qualquer valor escrito envelhece antes de ser lido. Quem precisa da revisão
> lê do Git, que é a fonte que não diverge: `git rev-parse origin/main`.

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
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção e conferência de documentos fiscais | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, por decisão: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe, e foi assim que a DL-026 divergiu dentro do próprio arquivo (BL-324) |
| [DL-011](../planos/DL-011-cnpj-alfanumerico.md) | CNPJ alfanumérico (NT 2025.001 / IN RFB 2.229) | Integrada (PR #12) |
| [DL-012](../planos/DL-012-readme-identidade-visual.md) | Redesenho do README e identidade visual (`docs/assets/`) | Integrada (PR #13), por outra sessão |
| [DL-013](../planos/DL-013-logo-oficial.md) | Logo oficial — três desenhos reprovados pelo Fred; o quarto é o **conceito do próprio Fred em vetor limpo** | **Integrada (PR #17)** |
| [DL-014](../planos/DL-014-guardas-de-processo.md) | Guardas de processo: gancho de sessão, workflow de atestado no PR, proteção da `main` | Integrada (PR #15). **BL-02 segue pendente**: a proteção da `main` é ação administrativa do Fred. **PR #32 (`docs/fix-gate-regex`):** correção estrutural do regex do gate que exigia `**` literal dentro do texto que o humano escreve — ver [DE-044](../projeto/decisoes.md). Aguarda auditoria independente antes do merge. |
| [DL-015](../planos/DL-015-contabilidade-utilizavel.md) | Contabilidade utilizável: Diário, Razão e Balancete por período, conciliáveis, e conferência de lotes | **Onda 1 integrada (PR #17)**, aprovada com ressalvas na [rodada 4](../auditorias/2026-09-14-dl-015-rodada-4.md) após três reprovações. Ressalvas em BL-83 a BL-86. **Onda 2 (interface, BL-62) executada como [DL-017](../planos/DL-017-interface-da-contabilidade.md)** |
| [DL-016](../planos/DL-016-competencia-e-fechamento.md) | Competência e fechamento de período, com reabertura autorizada e auditada | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, por decisão: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe, e foi assim que a DL-026 divergiu dentro do próprio arquivo (BL-324) |
| [DL-017](../planos/DL-017-interface-da-contabilidade.md) | Interface da contabilidade: plano de contas, lançamento, Diário, Razão, Balancete e conferência no navegador | **Integrada (PR #19, `60cbcff`)**, aprovada com ressalvas na [rodada 6](../auditorias/2026-09-15-dl-017-rodada-6.md) depois de cinco reprovações. As ressalvas foram encaminhadas à DL-020 |
| [DL-020](../planos/DL-020-consolidacao-pos-auditoria.md) | Consolidação pós-auditoria: as dez ressalvas da rodada 6 e as regras contábeis confirmadas pelo Fred | **Integrada (PR #21, `0dd07b4`)** — quatro rodadas de auditoria, fechamento do BL-242 com renumeração para `RC-85`, `RC-86`, `PE-46`, e conferência de encerramento. Resumo do auditor: *"Quatro rodadas, quatro achados no meu mecanismo de medição, zero no produto."* Itens abertos preservados: **BL-211** (dois defeitos do admin — não devem atravessar a DL-010), **BL-229** (medições de CSS que pulam na CI), **BL-235, BL-236, BL-237, BL-238, BL-239, BL-241** |
| [DL-021](../planos/DL-021-robustez-do-gerador-no-windows.md) | Robustez do gerador de papéis em ambiente Windows: `write_text → write_bytes` para gravar LF sempre, e `.gitattributes` neutralizando `core.autocrlf=true` | **Integrada (PR #22, `b8c66a6`)** — o verificador byte-strict (achado 9 do DL-019) continua intacto. ⚠️ **Limitação declarada e ainda aberta:** o que fechou foi a **quebra de linha**; rodar `--verificar` no Windows continua reportando `permissão 0o666` nos 14 derivados, por motivo independente ligado ao achado A3 (**BL-175**). Não ler como "compatibilidade Windows comprovada". Este arquivo e o próprio plano diziam "planejada, não iniciada" **depois** da integração; quem mediu a divergência foi o plano mestre, e a correção é a DL-022 |
| [DL-023](../planos/DL-023-integridade-administrativa.md) | Integridade administrativa: fechar **BL-83** (conta com movimento muda de empresa e de natureza pelo admin) e os dois casos vivos da **BL-211** (empresa inteira muda de escritório; inline de regime abre dois períodos ao mesmo tempo), com a defesa no **modelo** e não só na porta | **Integrada (PR #27, `1b828e7`)** + **BL-261 integrada (`c7346e6`, bugfix `30924ca`)** — guarda em `Conta.clean()` recusa reparentar conta com movimento para grupo de natureza oposta; 4 testes cobrindo recusa + 3 controles positivos. Ressalvas contábeis abertas: **BL-262** (admin sem isolamento por escritório em nenhuma superfície — etapa própria), **BL-263** (caixa do PR marcada com estado desatualizado), **BL-267** (add de conta cria em empresa de outro escritório — depende de BL-262), **BL-264, BL-265, BL-266, BL-268, BL-269, BL-270, BL-271, BL-272** (backlog, baixa/ressalva). |
| [DL-024](../planos/DL-024-trilha-integra-e-processo.md) | Trilha íntegra e processo: `registrar()` dentro da mesma transação que grava; `RegistroAuditoria` imutável contra `update()`/`delete()` em massa; PUT/PATCH com diff dos campos alterados; teste automatizado do gate SQLite/PostgreSQL | **Integrada (PR #28 + PR #29, `f9ee6c5`, DE-043)** — BL-14 (atomicidade), BL-16 (manager imutável), BL-57 (PUT/PATCH com diff), BL-244 (signal admin para 6 modelos via lista explícita `MODELOS_DA_TRILHA_DO_ADMIN`), BL-50 (gate SQLite/PostgreSQL, 5/5), CA-6 (matriz de acesso fixada). CI: 1.345 testes, 2 pulados. CA-4 reconciliada: plano listava 6 ModelAdmin mas registry tem 4; `Estabelecimento` é inline de Empresa, `HistoricoRegimeTributario` removido pelo admin na DL-023. DE-043: o plano é artefato derivado do código, não o contrário. [Auditoria rodada 1](../auditorias/2026-09-16-dl-024-rodada-1.md). **Fora do escopo:** BL-02 (proteção da main, ação do Fred), BL-242, criptografia em repouso, logs externos |
| [DL-025](../planos/DL-025-ordens-diretas-do-responsavel.md) | Reconhecer ordens diretas de Fred como demanda formal e autorização para executar o escopo pedido | **Integrada (PR #29, `f9ee6c5`)** — alteração documental, sem código de produto ou migração. Formaliza ordens diretas de Fred como demanda legítima, com processo de registro e validação |
| [DL-026](../planos/DL-026-identidade-visual-e-interface.md) | Identidade visual e redesenho da interface: o produto é funcional e acessível, e **não tem identidade nenhuma** — parece o admin do Django. Método: **gauntlet** — três direções cegas em paralelo, juiz **mecânico** medindo contraste, densidade e dependência externa antes de qualquer julgamento de gosto, eliminação e enxerto | **O estado desta etapa NÃO é descrito aqui.** Ele muda a cada rodada, e descrevê-lo em dois lugares foi exatamente o defeito que o auditor achou (B1 da [rodada 3](../auditorias/2026-09-18-dl-024-rodada-3.md)): esta célula parou na rodada 1 enquanto o "Próximo passo" já registrava a rodada 4. Leia **[Próximo passo](#próximo-passo)**, que é o único lugar onde o estado da DL-026 mora. Relatórios preservados: [rodada 1](../auditorias/2026-09-18-dl-024-rodada-1.md), [rodada 2](../auditorias/2026-09-18-dl-024-rodada-2.md), [rodada 3](../auditorias/2026-09-18-dl-024-rodada-3.md). ⚠️ **Não estava na fila do RC-88**: o pacote 3 (trilha íntegra, BL-14/16/57) era o próximo e volta a ser quando esta fechar — registrar o desvio é o que impede a fila de virar ficção |
| [DL-027](../planos/DL-027-documento-emitido-e-personalizacao.md) | O documento emitido: identificação obrigatória por **classe de documento** e personalização do que é legítimo personalizar. Mecanismo de **plataforma**, não da Contabilidade — vale para todos os módulos (RC-94) | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, por decisão: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe, e foi assim que a DL-026 divergiu dentro do próprio arquivo (BL-324) |
| [DL-028](../planos/DL-028-o-juiz-aponta-para-o-produto.md) | O juiz aponta para o produto: a pergunta *"o documento sai identificado?"* passa a ser respondida pelo **navegador**, em job delimitado por caminho, e o motor de cascata simulado é rebaixado de única garantia para primeira linha barata | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, pelo mesmo motivo da DL-027: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe |
| [DL-029](../planos/DL-029-a-frase-executavel-do-criterio-9.md) | A frase executável do critério 9: o critério inteiro passa a ser escrito **uma vez**, como frase verificável, e o instrumento passa a ser julgado por ela — cinco cláusulas que fecham BL-404, BL-405, BL-406 e BL-407 **juntos**, em vez de achado a achado (DE-059) | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, pelo mesmo motivo da DL-027 e da DL-028: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe |
| [DL-030](../planos/DL-030-a-trilha-cobre-o-admin.md) | A trilha de auditoria cobre o **admin**: quem alterou, quando, e **com que valor antes e depois**. Cobertura **derivada** de `admin.site._registry`, não de lista nossa. **Remendo declarado**, não o histórico com vigência que o BL-396 vai exigir | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, pelo mesmo motivo das demais: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe |
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
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção de documentos fiscais (XML, ZIP, SPED bloco C) | Situação em **[Próximo passo](#próximo-passo)** — esta célula não descreve estado, por decisão: descrever em dois lugares é a duplicação que a instrução permanente de 2026-09-13 proíbe, e foi assim que a DL-026 divergiu dentro do próprio arquivo (BL-324) |
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

### ⚠️ MUDANÇA DE PROCESSO, 2026-09-20 — leia isto antes de qualquer coisa

**Ordem do Fred**, com medição dele: *"estamos girando no mesmo lugar e gastando
tokens à toa … preciso codar mais. Sei que os testes e a auditoria são
necessários, mas do jeito que está está travando o processo."*

Duas coisas mudaram, e as duas estão no `AGENTS.md`:

1. **[§3.1 — níveis de risco](../../AGENTS.md).** A cerimônia passa a ser
   proporcional ao dano. **Nível 1** (dinheiro, livro, documento do cliente):
   tudo, auditoria inclusive. **Nível 2** (o que o contador usa): plano de uma
   página, auditoria só na primeira entrega do módulo. **Nível 3** (andaime):
   **sem plano, sem auditoria, sem registro de decisão**.
2. **A regra de parada, obrigatória.** Auditoria é **por etapa**, não por
   rodada: uma auditoria, uma correção, uma reconferência. **A terceira rodada é
   PROIBIDA** — ela significa que o **critério** estava errado, e o critério
   reabre com o Fred. E **guarda que falha duas vezes é apagada**, não corrigida
   pela terceira vez.

⚠️ **E o dado que corrige a intuição de todos, inclusive a minha:** cortar linha
de teste **quase não economiza token**. As 5.290 linhas que eu apaguei estavam
paradas em disco. **O que consumiu foi a RODADA** — doze auditorias, cada uma
com agente próprio, mais a correção e a integração de cada uma. **A regra de
parada vale muito mais que o corte.**

**O corte executado:** 5.290 linhas, 142 testes — a família do motor de CSS
simulado, que a DE-057 já havia rebaixado quando o navegador real entrou.
Proporção **3,9 : 1 → 3,5 : 1**, suíte **1917 passed**. Registrado em
**[DE-063](../projeto/decisoes.md)**.

⚠️ **Os outros três candidatos que eu propus NÃO qualificaram, e eu os
examinei antes de cortar:** `test_agentes_multiplataforma` guarda um gerador com
`--escrever` destrutivo e codifica defeitos reais já ocorridos (BL-177);
`test_dl024_varredura_de_interface` e `test_dl019_varredura_de_contratos` são
**derivadas**, não enumerações, e existem porque o produto vai ganhar cinco
módulos. **Eu havia proposto cortá-los pelo TAMANHO do arquivo — que é um
substituto, não a propriedade.** DE-060 aplicada a mim mais uma vez.

### ➡️ O TRABALHO DE PRODUTO EM CURSO: DL-016, fatia 1 — a trava da competência

**Aberto em 2026-09-20**, logo depois da mudança de processo, porque o Fred
pediu *"vamos codar produto"*. É a primeira etapa a nascer sob a
[§3.1 do AGENTS.md](../../AGENTS.md), classificada **NÍVEL 1** — mexe no livro.

**O fato que faltava**, respondido pelo Fred na mesma conversa, à pergunta
*"quando um mês já fechado precisa de correção, o que vocês fazem?"*:

> **(c) Depende — reabrem antes da entrega ao cliente, ajustam depois dela.**

Vira três comportamentos, e o terceiro é o que nenhum plano anterior tinha:

| Situação | O que o sistema faz |
| --- | --- |
| Competência **aberta** | Lança livremente |
| **Encerrada**, ainda **não entregue** | **Reabre**, com motivo obrigatório, autorização e trilha |
| **Encerrada e ENTREGUE** | **Não reabre.** O ajuste vai no mês aberto, apontando para a competência de origem |

**Decisão minha, de modelagem:** *"entregue"* **não** é um quarto estado da
competência — é um **fato datado** (`entregue_em`, `entregue_por`). Estado
descreve o que se pode fazer; entrega descreve o que já saiu porta afora, e as
duas coisas evoluem separado.

**O que a fatia 1 entrega, e ela é de servidor:**

1. Fechar a competência.
2. **Recusar lançamento em competência encerrada — NO SERVIDOR.**
3. Reabrir com motivo, **recusado se já entregue**.
4. Marcar como entregue.

⚠️ **A tela fica para a fatia 2, e é de propósito:** a trava tem de existir
**antes** de haver botão para acioná-la. Hoje `Competencia.estado` existe no
modelo (`aberta → em_encerramento → encerrada`) e **ninguém lê**: `grep '\.estado\b'`
fora de testes não devolve nada. É campo decorativo até esta fatia.

Plano: [DL-016](../planos/DL-016-competencia-e-fechamento.md).

#### A fatia 1 ENTREGOU (`16b9ec4`) e a auditoria REPROVOU — o bloqueador é uma CORRIDA

**Relatório integral:**
[2026-09-20-dl-016-fatia-1-rodada-1.md](../auditorias/2026-09-20-dl-016-fatia-1-rodada-1.md).
Números que o **auditor** mediu (não os que o implementador reportou, embora
confiram): **1962 passed, 14 skipped**, `ruff check` e `ruff format --check`
limpos, `manage.py check` limpo, migrações em banco vazio limpas.

**Onze dos doze critérios passam**, e dois resistiram melhor do que eu esperava:
a autorização do **RC-102** recusa cinco papéis **e o superusuário sem vínculo**,
com o banco intacto; e o isolamento entre escritórios devolve **404**, sem
confirmar existência.

⚠️ **O BLOQUEADOR, e ele derruba uma decisão declarada por escrito — [BL-456](../projeto/backlog.md).**
O implementador escreveu, em comentário, que não travar a competência na leitura
era *"risco residual proporcional, janela estreita"*. Eu mandei **medir** em vez
de aceitar o argumento, pela [DE-058](../projeto/decisoes.md). A reprodução
**natural** — sem instrumentação, sem espião, só duas threads com a que fecha
começando **0,6 ms** depois — gravou lançamento em competência encerrada **30
vezes em 30**. E o auditor reproduziu o caso que fere o cliente: **lançamento
entrando em competência já ENTREGUE**.

**A "janela estreita" é, na prática, toda a duração da transação de lançamento.**
É o fim de mês do escritório: o analista lança enquanto o gestor fecha.

⚠️ **E a construção que nem o plano nem o relatório nomearam ([DE-055](../projeto/decisoes.md)) — [BL-457](../projeto/backlog.md):**
a tela de **lançamento** devolve **HTTP 500** quando a trava dispara. Nada é
gravado — a trava do servidor funciona —, mas o contador vê página de erro em vez
da mensagem que diz para reabrir. O plano dizia *"a tela vem na fatia 2"*, e isso
valia para a tela **de fechamento**; a de lançamento está em produção desde a
DL-017 e, pela DE-026, chama o serviço **direto**, sem API no meio.

**Achados abertos:** [BL-456](../projeto/backlog.md) (bloqueador),
[BL-457](../projeto/backlog.md) (alta), [BL-458](../projeto/backlog.md) (média —
a trilha mora na view, não no serviço), [BL-455](../projeto/backlog.md) (média,
**pré-existente**, confirmada de forma independente),
[BL-459](../projeto/backlog.md), [BL-460](../projeto/backlog.md) e
[BL-461](../projeto/backlog.md) (baixas). O **BL-462** (este arquivo não
atualizado pela entrega) era meu e está fechado por esta seção.

⚠️ **Uma hipótese MINHA que a auditoria NÃO confirmou, registrada para não se
repetir:** eu suspeitava que reabrir **perdesse** quem assinou o fechamento
anterior. Não perde — a trilha preserva o autor ao longo de fechar → reabrir →
fechar. O que falta é contexto no registro (BL-459), não a identidade.

#### A RECONFERÊNCIA APROVOU (`d1da551`) — e o achado principal é do AUDITOR, sobre ele mesmo

**Relatório integral:**
[2026-09-20-dl-016-fatia-1-rodada-2.md](../auditorias/2026-09-20-dl-016-fatia-1-rodada-2.md).
**Parecer: APROVADO COM RESSALVAS.** **A fatia 1 está fechada em duas rodadas** —
a primeira vez que a regra de parada da §3.1 governa uma etapa inteira.

Números que o **auditor** mediu: **1973 passed, 14 skipped**; `ruff check`,
`ruff format --check` e `manage.py check` limpos; migrações limpas; e
`makemigrations --check` agora **exit 0**, que era exit 1 (BL-455 fechado).

⚠️ **O ACHADO PRINCIPAL DESTA RODADA É DO AUDITOR, SOBRE O PRÓPRIO AUDITOR.**
O oráculo que ele exigiu na rodada 1 — *"a reprodução natural tem de devolver 0
em 30"* — era **não-discriminante**. Ele mesmo mediu: o predicado acusa
**20/30 no código CORRIGIDO**, porque *"lançou E o mês terminou fechado"* é o
desfecho **legítimo** de qualquer correção certa. **O implementador recusou a
régua, argumentou, e tinha razão.**

**O que cai e o que fica, e a distinção importa:** cai o número que eu e ele
transformamos em manchete. **Fica o bloqueador** — ele nunca dependeu daquele
número: as reproduções R1 e R1b da rodada 1 eram **deterministas**, impunham a
ordem *"fechamento commitou, depois o lançamento inseriu"*, e o lançamento
entrou assim mesmo, inclusive em competência **já entregue**.

**Frase do auditor que vale guardar:** *"a conclusão da rodada 1 estava certa, e
uma das três evidências que usei para sustentá-la era imprestável. Eu a destaquei
como manchete, e foi a pior escolha editorial possível — dei o holofote à medição
fraca."*

⚠️ **E ele não parou no reconhecimento: construiu o oráculo CERTO e mediu.** Dois
instrumentos independentes, que não usam nenhuma função exclusiva da revisão
corrigida, rodados nas **duas** revisões: **violam em `16b9ec4`, não violam em
`d1da551`**. E **matou o mutante**: revertida **uma linha** da correção, três dos
quatro testes do implementador reprovam. *"Um instrumento que acusa no código
defeituoso e não acusa no corrigido é um instrumento; o meu da rodada 1 não
era."*

**Fechados:** BL-455, BL-456, BL-457, BL-458, BL-459, BL-460, BL-461.

**Ressalvas declaradas, nenhuma tocando valor contábil:**
[BL-463](../projeto/backlog.md) (média — o fechamento segura o lock durante a
varredura da base inteira, e não há `lock_timeout`; é **disponibilidade**, não
correção), [BL-464](../projeto/backlog.md), [BL-465](../projeto/backlog.md),
[BL-466](../projeto/backlog.md), [BL-467](../projeto/backlog.md) e
[BL-468](../projeto/backlog.md).

**Decisão minha sobre o BL-467:** o teste que não mata o mutante **fica, com o
nome corrigido**. Ele não guarda o BL-456 — e o nome não pode prometer que
guarda —, mas guarda o que nenhum outro cobre: que a corrida natural não produz
exceção inesperada, deadlock nem estado inconsistente. **Guarda de robustez é
guarda; guarda mal nomeada é armadilha.**

**Próximo passo:** a **fatia 2 — a tela** ([DE-065](../projeto/decisoes.md)),
levando junto BL-463 a BL-468. Hoje o contador **não consegue fechar o mês**: a
trava existe e não há porta.

**AGORA, em 2026-09-20:
[DL-026](../planos/DL-026-identidade-visual-e-interface.md) — identidade visual —
e [DL-028](../planos/DL-028-o-juiz-aponta-para-o-produto.md). Em
desenvolvimento, com uma DECISÃO MATERIAL no colo do Fred.**

➡️ **DECIDIDO em 2026-09-20, e a decisão é a [DE-059](../projeto/decisoes.md).**
O Fred delegou com uma frase — *"Você decide"* — depois de eu levar os dois lados
com o custo de cada um (PE-56). A resposta é **as duas coisas**, porque elas
respondem a perguntas diferentes:

1. **Comprar a frase executável** do critério 9 inteiro. É a
   **[DL-029](../planos/DL-029-a-frase-executavel-do-criterio-9.md)**, e ela
   fecha BL-404, BL-405, BL-406 e BL-407 **juntos**.
2. **Declarar hoje a verdade de hoje:** DL-026 e DL-028 **NÃO estão fechadas**.
   O que existe é **produto bom, garantia parcial**, com **BL-404** nomeado como
   o buraco aberto. Vale enquanto a DL-029 não entrar, e vale independentemente
   dela.

⚠️ **O que NÃO é defensável, e o auditor foi explícito:** fechar dizendo que o
critério 9 está garantido. Não está.

➡️ **Leia a seção "A décima auditoria" mais abaixo** para o porquê, com os
números.

### Onde a DL-029 parou — para quem retomar amanhã

**Nada está solto: árvore limpa, local e remoto iguais.** A revisão de
referência desta anotação é `59b6499`; o `git log` da branch
`claude/accounting-agent-team-setup-mn6lyf` é a autoridade sobre o que veio
depois — **não** descreva revisão nova aqui sem conferir lá.

| Cláusula | Estado | Observação |
| --- | --- | --- |
| **C5** — fornecedor fora do papel (**BL-404**, o bloqueador) | **Fechada e medida** | Identificador **derivado** de `templates/base.html`, de **duas** fontes, com **recusa (código 2)** se divergirem; busca normalizada sobre **todas** as páginas; e a checagem alcança também os **metadados do PDF** nos campos que o produto controla |
| **C4** — cada linha no seu lugar (**BL-405**) | **Fechada e medida** | Âncora por **ocorrência**, não por texto |
| **C3** — exatamente as linhas declaradas | **Fechada e medida** | Comparação de **conjuntos**: faltar **e** sobrar reprovam |
| **C1** — toda folha, toda tela (**BL-406**, **BL-410**) | **Parcial** | `lancamento_id` entrou e a tela é medida; paginação passa a ser **nomeada**. Falta o tratamento das rotas com `pk`/`token` genéricos, hoje **limite declarado** |
| **C2** — tinta que contrasta (**BL-407**) | **Limiar PROVISÓRIO no código** | A decisão já está tomada e escrita no critério 7 do plano: o piso é **derivado do WCAG 2.2**, por linha. O código ainda carrega o valor provisório |

⚠️ **ATUALIZAÇÃO da mesma madrugada — `3fd1384`: as CINCO cláusulas estão
fechadas e medidas.** O C2 fechou com o piso do **WCAG 2.2 (1.4.3, AA)**
aplicado **por linha**, a partir do tamanho e peso **realmente renderizados**
(pedidos ao navegador via `getComputedStyle`, nunca deduzidos de token CSS). O
limiar provisório de 2,4 **saiu do código**. Números medidos: controle limpo
**21,0:1** nas três telas, com **8,1×** de margem em pixels; penhasco entre
`opacity` **0,55** (reprova) e **0,60** (passa); e as duas causas de reprovação
ficaram **estruturalmente distinguíveis** — *"CONTRASTE insuficiente — X:1
medido, mínimo exigido 4,5:1"* contra *"POUCOS PIXELS de tinta visível"*. Suíte
inteira: **2016 passed, 15 skipped**.

⚠️ **E um quase-erro que virou registro, a [BL-423](../projeto/backlog.md):** a
conversão pt→px do piso nasceu **invertida**, e o implementador a achou e
corrigiu **antes** de reportar. Importa pela **direção**: invertida, ela fazia o
instrumento exigir **3:1** onde o devido é **4,5:1** nas linhas reais do timbre —
ou seja, **afrouxava a guarda e continuava verde**. É a assinatura do defeito
mais caro desta etapa inteira.

**A etapa NÃO está declarada pronta.** Está em **verificação independente**, por
quem não escreveu a correção (DE-055), em quatro regiões que **nenhum critério de
aceite exercitou**: (R1) o vão entre *"texto ilegível"* e *"pixels de menos"* —
os casos de `1px`/`3px` reprovam por uma checagem **anterior** (*"ausente do
texto do PDF"*), então a regra nova de contagem nunca foi exercitada com texto
extraível e tinta preta; (R2) o corte de *"negrito"* do WCAG; (R3) as quatro
fronteiras da conversão pt→px, que é onde a BL-423 se escondia; (R4) papel que
não é branco. **Só depois disso vai ao `auditor-qa`.**

**A verificação independente VOLTOU, e o resultado está abaixo.**

#### O que a verificação independente achou (2026-09-20, sobre `3fd1384`)

**Três das quatro regiões estão limpas**, e duas delas confirmam o trabalho:

- **R2 — sem achado.** `PESO_MINIMO_NEGRITO = 700` está certo: `font-weight: 600`
  exige **4,5:1** e `700` exige **3:1**. A hipótese de guarda frouxa não se
  confirmou.
- **R3 — sem achado.** As **quatro** fronteiras pt→px batem exatamente (18pt→3,0;
  17,9pt→4,5; 14pt negrito→3,0; 13,9pt negrito→4,5). A correção da BL-423 está
  certa **onde erro de conversão se esconde**.
- **R4 — o instrumento acerta nos dois regimes**, e o que falta é premissa
  escrita: **BL-426**.

⚠️ **R1 achou o que eu procurava, e é a [BL-424](../projeto/backlog.md):
`PISO_PIXELS_ESCUROS_POR_LINHA = 40` é o ÚLTIMO número mágico do instrumento.**
Com `font-size: 8px` no timbre, o instrumento **PASSA** — contraste 19,8:1, e
contagem de **57–58** pixels contra piso 40 — enquanto o produto real mede
**324–773**. O piso admite linha com **1/6 da tinta** do normal. Em 7px reprova,
em 8px passa, e **ninguém decidiu isso**.

**A observação de forma é a que importa:** o C2 trocou o limiar de luminância por
propriedade derivada de padrão externo; o piso de **contagem** ficou para trás. É
a mesma forma de `MARCA_DO_FORNECEDOR` e de `_PROPRIEDADES_DE_INTERESSE` — o
resto do arquivo virou propriedade e **esta constante sobreviveu**. E a pergunta
que ela responde **mudou de dona**: depois que o contraste passou a pegar tinta
apagada, a única coisa que a contagem ainda guarda é *"o texto foi renderizado em
tamanho legível?"* — pergunta de **tamanho**, que o instrumento **já sabe
responder** porque pede o tamanho ao navegador.

⚠️ **E eu NÃO afirmo que 8px é ilegível.** Pela **BL-422**, juízo visual de
agente não vale perto do limiar. Afirmo o medido. A pergunta *"qual é o tamanho
mínimo aceitável para o timbre do documento que vai ao cliente?"* é do Fred e
está registrada como **PE-58** — ele responde olhando uma folha impressa, que é
coisa que nenhum de nós consegue fazer.

**Mais dois limites a declarar, ambos achados não pedidos:** **BL-425** —
`presente_no_pdf` (`-layout` + substring) e a localização por `-bbox` são **dois
mecanismos distintos que divergem** em tamanhos pequenos, então o veredito pode
dizer *"ausente do papel"* sobre linha que **está** no papel; e **BL-426** — a
folha medida é **sempre branca** hoje, porque nenhum CSS usa
`print-color-adjust: exact` e `print_background` nunca é passado ao Playwright.

#### `100140e` — as três tratadas, e a DL-029 foi PARA A AUDITORIA

**BL-424 fechada.** `TAMANHO_MINIMO_RENDERIZADO_PX = 11`, terceira causa de
reprovação distinguível de contraste e de contagem, com mensagem própria
(*"renderizada a Npx, abaixo do mínimo de Mpx"*), lida do mesmo
`getComputedStyle` que já alimenta o piso do WCAG.

⚠️ **E o valor não foi inventado, que era o risco:** vem de `--tipo-2xs`, token
que o **próprio produto** já documenta como piso legível (BL-283), fixado por um
teste que **lê `static/css/base.css` de verdade** — não um número solto.
`8px` passa a reprovar **nomeando tamanho**; 16px e 14px, que é o produto real,
continuam passando. `PISO_PIXELS_ESCUROS_POR_LINHA` fica como sanidade residual:
não guarda mais nem tamanho nem contraste, os dois com checagem própria.

**BL-425 e BL-426 declaradas**, com a medição ao lado, não fechadas.

**Conferido por mim nesta revisão, com banco próprio (`arq_dl029`):**
`pytest` → **2017 passed, 15 skipped, 4 subtests**, 67,48 s; `ruff check .`
limpo; `ruff format --check .` 210 arquivos; `manage.py check` limpo.

#### A DÉCIMA PRIMEIRA AUDITORIA voltou — REPROVADO, e o achado MUDOU DE CLASSE

Relatório integral em
[2026-09-20-dl-029-rodada-11.md](../auditorias/2026-09-20-dl-029-rodada-11.md).
**Preservado sem uma palavra minha.** Cinco achados **ALTA**, quatro dentro do
instrumento que a etapa entregou.

**Não houve o K12 que ele mesmo previu.** A régua foi a **frase**, e o achado
subiu de *"o instrumento não faz a pergunta"* para *"o instrumento faz a pergunta
contra um **substituto**"*. Isso virou a [DE-060](../projeto/decisoes.md), e é a
primeira formulação **finita** em doze rodadas: o instrumento faz **cinco**
medições, e a pergunta *"isto é a propriedade ou um substituto dela?"* tem cinco
respostas — três delas corrigíveis com dado que o arquivo **já calcula e
descarta** (o `bbox` real).

| Achado | O que fura |
| --- | --- |
| **BL-427** | Timbre com **2 das 3** linhas declaradas sai como *"FALHA DE INFRAESTRUTURA — não é um veredito sobre o produto"*. O código da cláusula C3 é **inalcançável** |
| **BL-428** | `transform: scale(0.6)` e `zoom: 0.6` **passam** com o glifo a 9,1 px, enquanto `font-size: 8px` (8,7 px) reprova |
| **BL-429** | `color: #FF0000` mede **8,45:1** e passa; a razão WCAG real é **4,00:1**. O número rotulado *"WCAG 2.2"* não é o do WCAG |
| **BL-430** | `letter-spacing: 0.2em`, no tamanho real do produto, diz *"AUSENTE do texto do PDF"* sobre linha com **306 px de tinta** medidos na mesma execução |
| **BL-431** | O `AGENTS.md` mandava o Fred marcar `Backend` e `Documentação`; os contextos reais são `Lint e testes` e `Validar documentação` |

⚠️ **O BL-431 eu corrigi imediatamente**, em `AGENTS.md` e `CLAUDE.md`, com os
quatro nomes exatos e o comando que **busca** em vez de afirmar. **O dano do nome
errado é o oposto do esperado: contexto obrigatório que nunca reporta TRAVA a
`main` para sempre**, com o PR em *"pendente"* e nenhum erro para investigar.

⚠️ **E eu corrijo o relatório num ponto, com evidência, sem tocar nele:** o
auditor infere que o `AGENTS.md` foi *"com grande probabilidade"* a causa do erro
do Fred hoje, *"exatamente os dois"*. **Não foram.** Eu vi a tela: os erros do
Fred foram `tanto fazer projeto` e `emissor` — os **outros** dois, por corretor
de celular. O achado é real; a atribuição de causa não se sustenta. Registrado em
**BL-431**.

#### Ele mediu a PRÓPRIA FRASE e achou que ela promete o impossível

Exportando com as **opções padrão** do diálogo de impressão, a faixa que o
navegador acrescenta por fora carrega a **URL** — que em produção **é** o
identificador do fornecedor, em toda folha. E o `base.css` já declarava (BL-332)
que nenhuma folha de estilo a suprime. **O produto está certo; a frase é que
prometia o que ninguém entrega.** Corrigida na
[DE-061](../projeto/decisoes.md), com a fronteira nomeada — *"no conteúdo que o
documento controla"*. Isso não é afrouxar: é parar de chamar de garantia o
impossível, que é o defeito de 2026-09-13.

#### O que ele reafirma, e eu não quero que se perca

**BL-404 fechou de verdade** — refeito por um canal que ele não usava,
`::after { content: ... }` com `DATALEDGER` em caixa alta e o domínio, e o
instrumento reprovou nomeando a normalização. **C4 e C5 aguentaram tudo.** A
cobertura de **metadados do PDF alarga** o critério além da frase original e é
*"o sinal mais forte de que comprar a frase valeu"*. A paginação **erra para o
lado seguro** (medido: a exportação padrão do navegador é **mais** permissiva que
a do instrumento). Os quatro números **conferem**, e o custo do critério 9 é real:
**4 s** de medição, com cinco cláusulas a mais. **Terceira rodada seguida em que
ele não recomenda reverter o caminho A.**

#### E ele venceu uma discussão comigo, a meu pedido

Eu pedi que atacasse o meu argumento do **BL-419** (parar de escrever guarda). Ele
mostrou que o argumento publicado **expira** no dia em que o BL-373 for fechado,
que o ataque que eu descrevi **se autodestrói** com proteção ligada, e que o meu
modelo de ameaça era *"atacante"* quando o risco real é **acidente** — e que os
dois **não têm a mesma detectabilidade**. **Adotei a formulação dele**, que não
expira: *"toda guarda que eu escrever mora no mesmo YAML que ela guarda; a
regressão é infinita por construção, e o único lugar em que ela pode terminar é
fora do repositório"*. A decisão continua a mesma; a razão publicada era mais
fraca que a verdadeira.

#### Onde isso deixa o fechamento

**Em termos da frase, não de achados:** **C1, C4 e C5 fecham** (com limites
declarados). **C2 e C3 NÃO fecham.** Continua valendo **produto bom, garantia
parcial** — mas o **nome do buraco muda**: BL-404 fechou, e o que está aberto
agora são **C2** e **C3**. É uma frase muito mais curta de carregar do que uma
lista de achados.

⚠️ **E ele declarou o critério de parada, que é o que eu mais queria:** se
depois desta rodada aparecer um **sexto** eixo, a conversa deixa de ser de
engenharia e passa a ser *"quanta garantia o produto precisa"* — **pergunta do
Fred**.

#### DL-030 em execução — o Fred autorizou o remendo da trilha

*"Pode encaminhar o remendo da trilha"*, 2026-09-20, depois de eu levar a ele o
**BL-435** com a medição.

⚠️ **E o plano nasceu de uma premissa MINHA que estava ERRADA — corrigida no
mesmo dia, antes de virar código.** Eu afirmei que *"a razão social é apagada no
ato e não fica em lugar nenhum"*. **É falso.** A trilha **cobre** o admin desde a
DL-024/BL-244, por **signal genérico** em `apps/auditoria/signals.py`, e há teste
que prova exatamente o cenário que eu disse não existir. Conferido por mim:
`pytest apps/core/tests/test_dl024_trilha_admin.py` → **`7 passed`**; e
`git merge-base --is-ancestor febdc9f ab35715` → **verdadeiro**, o código já
estava lá quando eu "medi".

**A classe do meu erro é a [DE-060](../projeto/decisoes.md), aplicada a mim:** eu
rodei `grep "registrar(" apps/empresas/admin.py`, não achei, e conclui *"a trilha
não cobre o admin"*. A **medição era literalmente verdadeira e a conclusão era
falsa** — medi um **substituto** no lugar da **propriedade**, sem declarar que era
substituto, e publiquei ao Fred **como fato**. Registrado em **BL-435**, que
deixou de ser achado e virou o registro do erro. **Quem o encontrou foi o
`desenvolvedor-pleno`, medindo antes de escrever, porque o plano mandava parar se
a premissa não batesse — terceira vez na semana que essa regra evita um
defeito.**

**O escopo está no nome: é REMENDO.** Plano em
[DL-030](../planos/DL-030-a-trilha-cobre-o-admin.md), e a seção *"O que esta
etapa NÃO é"* vem **antes** dos requisitos, de propósito:

1. **Não** é o `HistoricoCadastralEmpresa` com vigência que o BL-396 vai exigir —
   esse depende da **PE-60**, cuja metade normativa eu **ainda não levantei** em
   fonte oficial.
2. **Não** fecha BL-244, BL-14, BL-16 nem BL-57. A trilha completa continua sendo
   o **pacote 3**.
3. **Não** promete dado recuperável em forma de cadastro: fica em `detalhes`, como
   **prova de que existiu e qual era**.

⚠️ **O valor é exatamente esse, e é grande: depois dela a informação EXISTE.
Antes, não existia.**

**As duas exigências de forma**, e são a lição da semana: a cobertura é
**derivada de `admin.site._registry`** (enumerar os `ModelAdmin` seria a décima
sétima ocorrência da classe), e a **guarda da cobertura também é derivada** — um
teste anda pelo registro e reprova se alguma `ModelAdmin` ficar de fora, de modo
que modelo novo entre **sozinho** ou o build fique vermelho.

**Duas frentes em paralelo, em arquivos disjuntos:** `scripts/**` com a rodada 2
da DL-029; `apps/**` com a DL-030.

#### A RODADA 2 da DL-029 ENTREGOU — `92679e0`, C2 e C3 fechados

**Os quatro substitutos viraram propriedade**, e é a DE-060 sendo aplicada em vez
de citada:

| A propriedade | Antes | Agora |
| --- | --- | --- |
| Quantas linhas o papel carrega | contagem colada à recusa de infraestrutura | **contagem própria**, código **1** com a frase do C3; `None` continua recusando (código 2) |
| Que tamanho a linha tem no papel | `getComputedStyle().fontSize` | **altura do bbox no papel**, com fator **medido** (1,088 idêntico em 4 tamanhos × 2 pesos) |
| A razão de contraste do WCAG | luminância de raster em **cinza** | **cor**, luminância de **três canais** |
| A linha está no papel | substring do `pdftotext -layout` | **o bbox foi localizado** |

**Medido no produto real:** `transform: scale(0.6)` e `zoom: 0.6` reprovam
nomeando **tamanho** (9,60 px e 8,40 px); `color: #FF0000` reprova relatando
**4,00:1** — que é a razão WCAG real e **bate com o cálculo à mão do auditor**;
`letter-spacing: 0.2em` a 14 px **passa**; timbre com 2 de 3 linhas sai com
código **1** dizendo *"número de linhas no papel (2) diverge do declarado (3)"*,
não mais *"falha de infraestrutura"*.

**O BL-434 saiu de zero para 14 testes ponta a ponta**, com Django, subprocesso,
Chromium e `poppler` **reais**, um por cláusula, afirmando **código de saída** e
**substring da mensagem**. Era o teste que teria pegado o BL-427.

**Custo, que era o meu ponto de parada:** 3,4–3,7 s antes, **3,5–3,6 s depois**.
A rasterização em cor **não** custou o que eu temia.

**Conferido por mim, com banco próprio (`arq_r2`):** `pytest` → **2045 passed,
15 skipped, 4 subtests**, 88,65 s; `ruff check` limpo; `ruff format --check` 210
arquivos; árvore limpa.

⚠️ **E o implementador declarou quatro achados próprios, dois deles contra a
própria entrega** — [BL-436](../projeto/backlog.md) a **BL-439**. O **BL-436** é
o substituto que **sobrou**: a classificação *"texto grande"* do WCAG ainda lê o
tamanho **declarado**. Ele argumenta que a checagem de tamanho mascara isso na
prática; **eu acho que o mascaramento não é completo** e mandei medir —
`font-size: 24px` com `scale(0.6)` dá 14,4 px, **acima** do mínimo de 11, e a
classificação continuaria exigindo 3:1 quando o devido seria 4,5:1.
**Registrei a hipótese ANTES do resultado, e ela pode estar errada** — hoje eu já
publiquei uma conclusão falsa por não medir (BL-435).

#### A DL-030 ENTREGOU — `8de86a7`, e a cobertura virou propriedade

**Conferido por mim, com banco próprio (`arq_dl030v`):** `pytest` → **2054
passed, 15 skipped, 4 subtests**, 90,75 s; `ruff check` limpo;
`ruff format --check` **211** arquivos; árvore limpa.

| Gap | Como fechou |
| --- | --- |
| `escritorio` vinha da **sessão** | Passa a ser **derivado do objeto** por inspeção do modelo (FK direta ou um nível de indireção), com `request.escritorio` como segunda opção. **Era o mais grave, e não era nenhum dos meus** |
| `Usuario` sem cobertura | Coberto, com a senha **redigida** — e a redação vem do **widget**, não de lista de nomes |
| Tupla de seis modelos | Vira *"todo modelo concreto de `apps.*`"* menos uma exclusão **pequena**, com motivo **por item** |
| Atomicidade **afirmada** | **Medida**: `IntegrityError` forçado em `RegistroAuditoria.objects.create` e a alteração **não persiste** |
| Inline, delete, DE-060 | Provados por **requisição**, inclusive o `delete`, que **não tinha teste no repositório** |

**A guarda do R2 foi provada com força:** um `ModelAdmin` de mentira **sem**
cobertura é registrado dentro do próprio teste, e a varredura **reprova
nomeando-o**. Modelo novo amanhã entra sozinho, ou o build fica vermelho.

⚠️ **E ele declarou o substituto que sobrou, sem eu perguntar:** a redação por
widget é estruturalmente um substituto de *"este valor é secreto"*, e ele nomeou
a divergência **com exemplo concreto do projeto** — `ConviteEscritorio.token`, um
`CharField` opaco que hoje não tem `ModelAdmin`; se ganhar um, sem widget de
senha, este mecanismo não o protege.

**Dois achados meus na integração:** [BL-441](../projeto/backlog.md) — o prefixo
`"/admin/"` está escrito duas vezes, no `urls.py` e no `signals.py`, sem
derivação; **gravidade BAIXA, e eu medi o modo de falha antes de classificar**:
os nove testes usam caminhos literais, então mover o admin faz **todos irem a
vermelho**. É falha **barulhenta**, não silenciosa. O que fica ruim é a
**mensagem**, que acusaria *"trilha não gravada"* quando a causa é *"o admin
mudou de endereço"*.

⚠️ **E [BL-442](../projeto/backlog.md), que é contra MIM e é o segundo do dia:**
pela **segunda vez** eu publiquei uma **razão** mais fraca que a verdadeira, e as
duas eram **verificáveis e falsas**. Aqui eu escrevi que *"o signal cobre
qualquer caminho de escrita"* para recusar a troca por `save_model`. **Medido:
falso** — ele sai cedo se a origem não é o admin, e isso é **deliberado e certo**
(as views já fazem o próprio `registrar()`; cobrir os dois lados duplicaria a
trilha). **A decisão continua certa; a razão era outra:** *o signal pode crescer
afrouxando um `if`; o `save_model` não pode, por construção.*

**E é isso que torna o padrão perigoso: razão errada com conclusão certa não é
corrigida por ninguém, porque o resultado parece bom.** Virou regra minha —
argumento verificável que eu publique vai **verificado**, ou vai marcado como
**não medido**.

#### A verificação independente voltou: a minha hipótese estava CERTA, e havia mais dois

**R1 — [BL-436](../projeto/backlog.md), falso conforme reproduzido.** Com o
instrumento ponta a ponta: `font-size: 24px` + `transform: scale(0.6)` + tinta
`#D0D0D0` → **`CODIGO=0`**, `"veredito": "PASSOU"`, `"motivos": []`. E o JSON
entrega a contradição na mesma linha — `declarado: 24`, `renderizado: 14.40`,
`razao_minima_wcag_exigida: 3.0`, `contraste_medido: 4.174`. **14,4 px é texto
normal e exigiria 4,5:1.** São **dois pipelines de tamanho que nunca se cruzam**.

⚠️ **E a lição é mais fina que *"sobrou um substituto"*:** o argumento do
implementador — *"a checagem de tamanho dispara antes, mascarando a divergência
na prática"* — é **afirmação de comportamento escrita no código e não medida**.
É a forma que a **DE-058** proíbe, e medida ela é **falsa**.

**R2 — [BL-437](../projeto/backlog.md), e é FALSO ALARME hoje, não limite
teórico.** Sem sabotagem nenhuma — só `font-family: monospace` com
`font-size: 11px`, que é **exatamente o piso** — a linha **reprova**:
`renderizado: 9.85`, `CODIGO=1`. Razão real medida: **0,9743** em `monospace`,
**0,9269** em `serif`, **0,9351** em `sans-serif`, contra o **1,088** da
constante. **O piso efetivo vira ~12,3–12,9 px.** É o **BL-321** dentro da
verificação que o Fred escolheu tornar obrigatória.

⚠️ **[BL-440](../projeto/backlog.md) — o achado NÃO PEDIDO, e é o que pode
derrubar a cláusula C2 inteira.** A tinta rasterizada **não é** a tinta
declarada: `#898989` no CSS, confirmada por `getComputedStyle`, mede como
**(53, 53, 53)** no papel — reproduzido em **quatro DPIs**, com o próprio
rasterizador do instrumento. O contraste relatado (12,266:1) **bate com
precisão** com um cinza efetivo de 53: a conta está certa, **a entrada é que não
é a cor declarada**.

**A direção do erro é a perigosa:** tinta medida **mais escura** do que é
significa relatar **mais** contraste do que existe — o lado do **falso
conforme**, o mesmo do BL-429 que acabou de ser fechado.

⚠️ **O verificador NÃO diagnosticou a causa e se recusou a afirmá-la.** Está
registrado como **pergunta aberta** — Chromium na exportação, poppler na
rasterização, ou a nossa leitura do PPM —, e continua assim até alguém medir.

➡️ **Rodada 3 delegada, e com ordem explícita: DIAGNOSTICAR o BL-440 ANTES de
corrigir qualquer coisa.** Escolher a correção sem saber onde a cor muda seria
adivinhar. Os BL-436 e BL-437 fecham **juntos**, por uma propriedade que dispensa
o fator de fonte: pedir ao navegador a **escala acumulada**
(`getBoundingClientRect().height / offsetHeight`, que inclui `transform`, `zoom`
e ancestrais) e usar `declarado × escala` nas **duas** leituras. ⚠️ **E mandei
medir a minha própria proposta antes de aceitá-la** — hoje eu já errei uma
premissa por não medir.

**Depois desta, auditoria, e eu vou cumprir — já adiei uma vez.**

#### A rodada 3 entregou — `9b14e20`, e o BL-440 mudou de natureza

**BL-436 e BL-437 fechados**, os dois pela mesma propriedade. ⚠️ **E a minha
proposta foi REJEITADA por medição, pela terceira vez hoje:**
`getBoundingClientRect().height / offsetHeight` passou em **5 casos sintéticos**
e **falhou contra o produto real** — `offsetHeight` é **inteiro**, e `serif` a
exatos 11 px dava escala 0,9961 → 10,957 px → **falso alarme no próprio piso que
a correção existe para fechar**. A versão que ficou decompõe a escala da matriz
de `transform` (`√(c²+d²)`) × `zoom`, por todos os ancestrais, **sem caixa de
layout arredondada**.

**Suíte: 2058 passed**, custo 3,7 s, dentro do orçamento.

⚠️ **E o [BL-440](../projeto/backlog.md) mudou de natureza duas vezes numa
tarde.** O implementador determinou o **local** por inspeção dos **bytes** do
PDF — descompressão dos fluxos, operadores `rg`, sem PIL e sem PNG no caminho: o
fluxo já traz `.2078 … rg`, e `.5373` (137/255) **não aparece em lugar nenhum**.
**A transformação está na exportação do Chromium, não no `pdftoppm`.** E ele foi
honesto no limite: *"determinei o LOCAL com certeza; não determinei o
MECANISMO"*.

**Aí eu fiz a conta que ele não fez, e ela derruba a família inteira de
hipóteses:** as diferenças da tabela são **84, 84, 84, 84, 84, 84, 84, 85, 85** —
**subtração CONSTANTE**, com identidade abaixo de ~106. Gestão de cor, perfil
ICC, gama e conversão de espaço são **multiplicativas ou potências**; **nenhuma é
aditiva com descontinuidade**. Degrau seco mais offset fixo **não é transformação
de cor** — é aritmética de outra coisa.

**Sobram três causas muito diferentes:** leitura do fluxo pegando o número
errado; um **segundo objeto de desenho** cuja cor foi lida no lugar; ou
deslocamento real do escritor de PDF. Pedi **três medições**, e a que pode
**eliminar** o achado vem primeiro: cor **assimétrica** `rgb(137,138,139)` — se
sair `(53,54,55)`, o deslocamento é real; qualquer outra coisa prova que a
leitura pega o número errado.

#### BL-440 RESOLVIDO — e a medição que eu desenhei derrubou a MINHA explicação

**Não é defeito do instrumento.** É fato de produto, e está registrado onde vai
ser lido: na [direção de arte](../projeto/direcao-de-arte.md), §7.

**O que ficou determinado:** a exportação de **texto** do Chromium/Skia distorce
cor clara com **múltiplos canais RGB elevados** — `rgb(137,138,139)` vira
`(54,54,55)`. **Cor de canal único passa intacta**; **forma vetorial SVG é
fiel** (o mesmo cinza num `<rect>` exporta exato); a **captura de tela é fiel**.
**Só o texto no PDF diverge.**

⚠️ **E a minha aritmética de *"subtração constante de 84"* estava ERRADA — foi o
teste que EU pedi que a derrubou.** Eu a deduzi de uma tabela **só de cinzas**;
com cor assimétrica, R e G **colapsam no mesmo valor**, o que nenhuma subtração
por canal produz. **A medição que eu desenhei para *"eliminar o achado"* não o
eliminou: refinou o achado e eliminou a minha explicação dele.**

**É o quarto enquadramento meu que a medição derruba no mesmo dia.** As outras
duas hipóteses que eu levantei — leitura errada do fluxo e segundo objeto de
desenho — **também foram descartadas por medição**: o operador de cor é **único**
e imediatamente anterior ao `Tj`, e há **um só** bloco `BT…ET` por elemento.

**O mecanismo interno continua NÃO DETERMINADO**, e fica escrito assim: o
implementador recusou-se a afirmá-lo sem acesso ao código do Chromium, e está
certo.

**Por que não é defeito:** o instrumento mede o **artefato** — o PDF que o
escritório entrega. Tinta mais escura é **mais** contraste: a direção do desvio é
a **segura**. **Nenhuma linha de código foi alterada.** **Por que importa mesmo
assim:** a **DL-027** deixa cada escritório escolher a cor do timbre, e *a cor
escolhida na tela não é a que sai no papel*.

⚠️ **E eu corrijo o meu próprio enquadramento, que é o TERCEIRO que a medição
derruba hoje.** Eu havia escrito que a direção do erro é *"o lado do falso
conforme"*. **Não é.** O instrumento mede o **artefato** — o PDF, que é o que o
escritório entrega. Se a tinta no PDF é **de fato** 53, a folha **tem** tinta
escura e a medição está **certa sobre o documento**. O que diverge é o **CSS**,
que é intenção, não entrega. Se confirmar, o achado **muda de dono**: vira fato
de **produto** — *"a tinta na tela não é a tinta no papel"* —, assunto da direção
de arte e da **DL-027**.

Delegada sobre `2f1e596`, com os critérios **11 a 20** escritos na seção
*"Rodada 2"* do
[plano](../planos/DL-029-a-frase-executavel-do-criterio-9.md). Ordem de ataque
por **custo do erro**, não por número: **BL-427** primeiro (documento sem o
registro profissional do contador rotulado como falha de infraestrutura),
depois BL-430 (é de uma linha), BL-428 e BL-429.

⚠️ **Decisão minha, tomada com a delegação para o implementador não ter de
tomá-la:** o **BL-429** exige escolher entre medir a folha em **cinza** ou em
**cor**, e a **PE-59** (a pergunta do Fred sobre impressão monocromática) ainda
não tem resposta. **Decidi medir em COR**, e a razão é de **risco**, não de
gosto: a medida em cor é a **mais estrita** das duas e cobre os dois usos — o PDF
na tela do cliente, onde a cor existe, e a impressora monocromática, onde ela
vira cinza e o critério só fica **mais folgado**. Escolher o inverso aprovaria
folha que o próprio piso adotado reprova, que é o BL-429 exatamente.
**A impressão monocromática fica declarada como cenário mais permissivo, e o
lado seguro não espera pela resposta do Fred.**

⚠️ **E pedi para o implementador PARAR e avisar em um ponto concreto:** raster em
cor é 3× os bytes do cinza; se o passo de medição passar de **~10 s**, eu quero
saber **antes** da entrega. O custo do job é critério declarado desde a rodada 1,
e descobrir regressão de custo na auditoria seria repetir o **BL-411**.

**A frase do critério 9, no plano, já está na redação corrigida da DE-061** — com
a fronteira *"no conteúdo que o documento controla"* e a exclusão nomeada da
faixa que o navegador imprime por fora (BL-332).

⚠️ **Duas coisas que NÃO são de engenharia e não se resolvem no código:**

1. **A ação do Fred no GitHub (BL-373).** Em 2026-09-20 ele chegou a criar a
   regra, e **dois dos quatro nomes de verificação saíram errados** —
   `tanto fazer projeto` no lugar de `Regras do projeto`, e
   `…identificação do **emissor**…` no lugar de `…do **emitente**…`. Conferi
   contra os nomes reais dos jobs e avisei antes de ele salvar. ⚠️ **Exigir uma
   verificação que não existe é pior que não exigir nada: ela nunca reporta, e
   o repositório trava — nenhum PR consegue ser mesclado.** Os quatro nomes
   corretos são `Lint e testes`, `Validar documentação`, `Regras do projeto` e
   `Medir identificação do emitente no navegador`. **Quando ele salvar, confira
   por API — não pela tela.**
2. **A PE-57**, que nasceu hoje: existe piso normativo de **legibilidade** para
   documento contábil? Sem consequência hoje (o produto imprime ~21:1), com
   consequência na **DL-027**.

**E a lição do dia, que vale para quem retomar:** a mesma classe apareceu
**quatro** vezes em uma tarde — BL-415, BL-416, BL-418 e o nome digitado pelo
Fred na tela do GitHub —, todas da forma *"valor copiado à mão em vez de
derivado da fonte"*. **Onde a guarda derivou de uma propriedade, ela aguentou.**

**A revisão viva é `920822a`, na `main`, mesclada pelo PR #36** — a rodada 9 da
etapa. Antes dela, o PR #35 (`d22c580`) levou a rodada 5. Quem quiser conferir o
que está no ar lê essas duas.

**A etapa NÃO está fechada, e o merge não a fechou.** São duas perguntas
diferentes desde a [DE-054](../projeto/decisoes.md): *"isto melhora o produto?"*
decide o merge; *"isto está garantido?"* decide a etapa. O Fred respondeu a
primeira em 2026-09-19, escolhendo a opção A — mesclar e auditar em paralelo —
depois de perguntar se a auditoria era necessária e de ouvir o custo medido:
**35 commits com melhoria pronta parados numa branch** enquanto as rodadas
poliam **guardas**.

**A sétima auditoria (`920822a`) REPROVOU o fechamento**, com um **bloqueador** e
um alto. Relatório integral em
[2026-09-19-dl-026-rodada-7.md](../auditorias/2026-09-19-dl-026-rodada-7.md).
Ele é explícito sobre o merge não ter sido erro — mediu o produto mais a fundo
que em qualquer rodada anterior e o encontrou **correto em tudo que conseguiu
medir**. O que falta é **garantia**: três construções banais de CSS, uma delas a
forma recomendada de se escrever CSS hoje, devolvem a marca do fornecedor ao
papel ou apagam o timbre do escritório **com a suíte inteira verde**.

⚠️ **O que está em vigor na `main`, portanto:** o produto certo, e a guarda que
aprovaria o produto errado. **BL-351**, **BL-352**, **BL-353**, **BL-360** e
**BL-361** estão corrigidos na branch e **ainda não na `main`**; **BL-354** a
**BL-359** seguem como ressalvas declaradas, com dono e momento no backlog.

## A oitava auditoria, e a decisão de instrumento que está com o Fred

**A oitava auditoria (`55d5d63`, PR #37) REPROVOU o fechamento**, com um
**bloqueador** e um alto. Relatório integral em
[2026-09-19-dl-026-rodada-8.md](../auditorias/2026-09-19-dl-026-rodada-8.md).

**Os cinco itens das rodadas 10 e 11 FECHARAM**, e o auditor fechou os cinco
**por execução**: BL-351, BL-352, BL-353, BL-360 e BL-361. Os números conferem,
o produto continua correto em tudo que ele conseguiu medir, e a conciliação bate
em três fontes independentes.

⚠️ **O que reprova é um eixo novo, e é o eixo ANTERIOR ao que onze rodadas
percorreram.** Não *o que o motor consegue ler* — esse está fechado —, mas **o
conjunto de propriedades que ele considera** e **onde a cadeia termina**.
`_PROPRIEDADES_DE_INTERESSE = ("display",)` é uma lista de **um item**, a quinze
linhas de um motor reescrito **três vezes**, e ela sobreviveu às três porque as
três atacaram o **seletor**. Resultado medido em Chromium e em PDF A4 do produto:
**dez construções banais apagam a identificação do escritório da folha que o
contador entrega ao cliente, com a suíte inteira verde** (BL-362, bloqueador), e
a cadeia do timbre é derivada só do Balancete — Diário e Razão são cobertos por
uma cadeia que não é a deles (BL-363, alto). BL-364 e BL-365 ficam como
ressalvas declaradas.

**A causa de a lista ter sobrevivido não foi descuido, e isso importa:** ela
está **declarada** na docstring, com justificativa **boa** — boa para a guarda
da **marca**, cuja propriedade é *"esconda-se"*. A guarda do **timbre** reusou o
mesmo motor por composição (decisão de engenharia correta) para a propriedade
**oposta**, *"apareça"* — e o oposto lógico de uma regra estreita é uma regra
**frouxa**. A simetria era de mecanismo; ninguém reavaliou a estreiteza. Virou a
[DE-056](../projeto/decisoes.md): *limite declarado não é limite fechado*, e a
construção nova de toda verificação passa a mirar também um eixo que o relatório
**não** discutiu.

### A decisão que está com o Fred, e ela não é de engenharia

O auditor **não recomenda mais uma rodada de polimento do motor simulado**, e o
argumento dele é medido, não estético: `test_bl329_marca_fora_do_papel.py` tem
**1803 linhas** para responder a uma pergunta que o navegador responde com uma
chamada; a linguagem que ele simula **cresce todo ano**; e **todo bloqueador
desta etapa foi encontrado abrindo um Chromium e olhando o PDF**. O sinal
"os achados estão encolhendo" era artefato do lugar onde se procurava — bastou
olhar o eixo ao lado para o achado voltar ao tamanho de bloqueador.

Ele recomenda **trocar o instrumento**, e metade da troca já está escrita e
paga: `visivelDeVerdade` (`scripts/juiz.py`, que em 2026-09-20 morava em
`docs/assets/design/gauntlet/` — ver BL-408) já é a
derivação certa — três medições gerais, limites medidos e declarados — e cobre
as dez construções **sem saber que elas existem**; `scripts/medir_impressao.py`
já sobe o produto real e gera PDF A4. O que falta é **apontar o juiz para o
produto em vez de para os protótipos** e pôr a medição no ciclo.

**São três caminhos, e os três custam:**

1. **Navegador na integração contínua** — contraria a decisão deliberada de não
   ter essa dependência, e o Chromium de caminho fixo é acidente deste ambiente,
   não configuração do projeto.
2. **Medição de bancada obrigatória com evidência registrada**, por etapa que
   toque `static/css/base.css` ou crie tela imprimível — é **disciplina**, que é
   exatamente o que o projeto decidiu não usar como garantia quando criou as
   guardas.
3. **Continuar polindo o motor simulado** — que nunca vai estar completo.

**O que não é defensável é a quarta:** declarar a etapa fechada afirmando que o
critério 9 está garantido, quando construções banais o derrubam com a suíte
verde.

### A decisão do Fred, em 2026-09-19: caminho A

**O Fred escolheu A — navegador de verdade na integração contínua.** A
delimitação por caminho é minha: o job roda quando muda `static/css/**`,
`templates/**` ou as guardas de impressão, nunca em alteração só de
documentação. Registrada como [DE-057](../projeto/decisoes.md), com plano de
execução em [DL-028](../planos/DL-028-o-juiz-aponta-para-o-produto.md).

O que decide entre A e B é o princípio que já governa este projeto: **mecanismo
em vez de disciplina**. A instrução permanente do Fred de 2026-09-13 virou
teste, não lembrete. Escolher B seria voltar a apostar em alguém lembrar,
justamente na propriedade cuja falha chega ao cliente **em papel**.

### O que está em vigor agora, e onde

**A revisão viva é `7c5b1d4`, na `main`, mesclada pelo PR #37** — as rodadas 10
e 11. Antes dela, o PR #36 (`920822a`) levou a rodada 9, e o #35 (`d22c580`) a
rodada 5.

O merge foi decisão minha, operacional e reversível, e informo o critério:
alteração **só de guarda**, sem uma linha de produto, com a integração contínua
verde nas três verificações e sem conflito; o buraco que a oitava auditoria
achou (BL-362) **já existia na `main`** e não foi introduzido por este PR, que
fecha outros cinco. Reverter é no-op para dados. **O merge não fechou a etapa** —
são duas perguntas diferentes desde a [DE-054](../projeto/decisoes.md).

**Duas frentes em paralelo, em arquivos disjuntos:**

| Frente | Responsável | Escopo | Arquivos |
| --- | --- | --- | --- |
| **DL-026 rodada 12** | `especialista-frontend` | BL-362 (bloqueador) e BL-363 — o conserto barato do motor simulado, para ele parar de estar simplesmente errado enquanto o instrumento novo é construído | `apps/contabilidade/tests/**` |
| **DL-028 fatia 1** | `desenvolvedor-pleno` | Apontar `visivelDeVerdade` e as sondas de impressão para o **produto** em vez dos protótipos do gauntlet | `scripts/**` (inclusive `scripts/juiz.py`, movido para lá pelo BL-408), `.github/workflows/**`, `requirements/**` |

**Proibido às duas:** `static/css/base.css` e `templates/**`. Nenhuma das duas
frentes muda produto.

### O que as duas frentes trouxeram, e o BL-362 continua ABERTO

**A fatia 1 da DL-028 está entregue e medida:** existe um instrumento que, sobre
o **produto real**, sobe o servidor com banco descartável, deriva sozinho as
telas que têm timbre (achou as três — Balancete, Diário, Razão — sem nenhuma
escrita à mão), mede no navegador sob `emulate_media("print")` e confere o PDF
A4 com `pdftotext`. **Ele pega as dez construções do BL-362**, mais quatro que eu
escolhi e que o relatório não nomeou. Roda em **3,5 s**.

⚠️ **Achado do `desenvolvedor-pleno` construindo, e ele corrige o meu plano:** a
`visivelDeVerdade` cobre **nove** das dez, não as dez. A décima é `color:
transparent`, e ela escapa por **dois** caminhos ao mesmo tempo —
`checkVisibility` não muda com a tinta, e o `pdftotext` lê o **objeto** de texto,
não o pixel. Ele mediu, fechou o buraco **fora** da função geral e não
contaminou o que o gauntlet também usa.

**A rodada 12 fechou três dos quatro itens:** a cadeia do timbre passou a
incluir os descendentes que carregam o texto; pseudo-classe fora do conjunto
**fechado** de interação passou a **recusar julgar** em vez de ser tratada como
`:hover`; e o BL-363 foi resolvido por **varredura de `templates/**`** — as três
telas entram sozinhas, e a sabotagem morre **nomeando a tela**. BL-365 também.

⚠️ **O quarto item não fechou, e o defeito era do meu pedido — [BL-367](../projeto/backlog.md).**
Eu especifiquei a recusa como *"qualquer declaração que não seja `display`, em
regra que case com a cadeia"*. Medido pelo implementador: dispara **9 vezes** no
`base.css` real **sem sabotagem nenhuma**, porque a cadeia inclui
`<html>`/`<body>`. Ele **parou antes de integrar**, como eu havia exigido, e
registrou o conflito em vez de inventar exceção.

**E a medição dele provou o que o §7 do auditor só argumentava:** o motor
simulado **não consegue** responder *"o timbre aparece"* sem construir uma lista
(que cresce com a linguagem) ou produzir falso alarme. Tentei formulação mais
estreita e não existe — restringir às regras que alvejam o timbre ainda deixa
três declarações de layout legítimas disparando.

**Decisão minha, e o enquadramento é o que muda:** o motor simulado responde a
condição **necessária** (*nenhum nó da cadeia com `display: none` sob
impressão*); o **navegador** responde a **suficiente**. Isso deixa de ser
pendência e passa a ser **limite declarado com prova medida**, escrito no
próprio código.

⚠️ **Consequência que não disfarço: o BL-362 continua ABERTO.** As construções 2
a 8 do §H1 não são pegas pela suíte, e só ficam cobertas quando a **fatia 2** da
DL-028 puser o instrumento de navegador na integração contínua — em construção
agora. O implementador classificou essas seis como **Bloqueado**, não como
corrigido, e eu preservo a classificação dele.

### A DL-028 entregou as três fatias, e o navegador está no ciclo

**Fatia 2 entregue e VERDE**, verificada por mim **por disparo real** — não por
leitura do `yaml`, que é a única forma que valeria aqui:

| Caso | Medido por disparo real |
| --- | --- |
| Commit tocando caminho vigiado (`c26f5d8`) | job roda **inteiro**, `0 de 11` passos caros pulados, **54 s**, verde |
| Commit só de documentação (`7d6b60f`) | job roda, **`11 de 11`** passos caros **pulados**, **23 s**, verde |
| A medição em si, dentro dos 54 s | **3 s** |

O caminho longo custa 54 s: containers 12 s, Chromium **20 s**, `poppler-utils`
4 s, dependências 7 s. **Três segundos** é o que custa responder à pergunta; o
resto é montar a bancada.

⚠️ **Dois achados meus na verificação, os dois por disparo real:**

- **[BL-370](../projeto/backlog.md) — o job reprovava**: faltava `poppler-utils`
  no runner. Mas o **modo** como ele falhou é o melhor resultado do dia: disse
  literalmente *"FALHA DE INFRAESTRUTURA — não é um veredito sobre o produto"*.
  Sem essa distinção eu teria lido o vermelho como regressão do balancete. E o
  instrumento **recusou** em vez de medir só metade e devolver verde.
- **[BL-371](../projeto/backlog.md) — job que roda mas não é EXIGIDO é conselho,
  não trava.** E marcá-lo como obrigatório com `paths:` no gatilho criaria a
  armadilha inversa: checagem que **não reporta** num PR de documentação fica
  **pendente para sempre**, travando o merge sem erro para investigar. Corrigido
  tirando os `paths:` do gatilho e pondo a decisão **dentro** do job, com a
  lista de padrões passando a viver **num lugar só** — antes eram duas, ligadas
  por âncora YAML, que é o BL-352 esperando para acontecer.

**Fatia 3 entregue:** a docstring de `test_bl329_marca_fora_do_papel.py` deixou
de se apresentar como a garantia. Ela agora declara que responde à condição
**necessária**, nomeia quem responde à **suficiente**, e sustenta o argumento com
os **números medidos** (9 disparos pela cadeia inteira, 3 restritos ao timbre) e
com os **dois testes** que os fixam. Também deixa escrito que o BL-362 **não**
fecha por ela sozinha.

**Medição minha, com a máquina livre:** `1910 passed, 15 skipped` em 69,9s;
`ruff check` limpo; `ruff format --check` 206 arquivos; `manage.py check` limpo.
Refiz as dezessete construções que eu havia guardado nas rodadas 10 e 11:
**sem regressão** — as sete continuam corretas, o cruzamento com o navegador dá
**zero falsos conformes**, e as dez da segunda leva continuam 9 recusas + 1
aprovação.

### A nona auditoria REPROVOU as duas etapas, com dois bloqueadores

Relatório integral em
[2026-09-19-dl-026-dl-028-rodada-9.md](../auditorias/2026-09-19-dl-026-dl-028-rodada-9.md).

**[BL-372](../projeto/backlog.md) — a décima primeira ocorrência, DENTRO do
instrumento criado para fechar a décima.** Uma linha de CSS com **token legítimo
do projeto** — `.conteudo-principal { color: var(--papel-elevado) }` — apaga o
timbre do papel com `1910 passed` **e** com o job de navegador **verde**. Folha
A4 rasterizada a 96 dpi: **0 pixels escuros** na faixa do timbre (o controle tem
1.558), e o corpo do documento intacto com 7.595. As **duas** camadas são cegas à
mesma classe: a barata por construção declarada, e a caríssima porque
`pdftotext` lê o **objeto** de texto — tinta branca é um glifo pintado. E o
limite estava **declarado** em `sonda_visibilidade.py` e foi **herdado em
silêncio**: a DE-056 item 3 violada no arquivo que nasceu da DE-056.

**[BL-373](../projeto/backlog.md) — a `main` NÃO TEM PROTEÇÃO NENHUMA.** Medido
pelo auditor em três endpoints. Isso não afeta só o job novo: `Backend`,
`Documentação` e `Regras do projeto` — inclusive o atestado *"Li o AGENTS.md"* e
o teste que reprova estado divergente — **também são conselho**. A linha da
tabela do `AGENTS.md` que afirmava o contrário estava **factualmente falsa**.
**Corrigi imediatamente** a metade documental, sem esperar nada: a tabela ganhou
uma coluna **"Impede o merge?"** com **NÃO** onde é NÃO, a evidência dos três
endpoints, e como ligar e conferir. O `CLAUDE.md` idem.

⚠️ **Mais três ALTAS, todas no item 5 da DE-054:** BL-374 (o nome curto de rota
não é único — uma tela homônima **desloca** o Balancete real e o job fica
verde), BL-375 (a base semeada tem **uma** linha de timbre, então o diferencial
"identificação parcial conta como falha" é um **no-op** na CI) e BL-376
(`CAMINHOS_VIGIADOS` não cobre `apps/<modulo>/templates/`, que é onde a DL-027
vai nascer — e as **duas** camadas desligam juntas). Mais BL-377 a BL-385.

**A tese da DL-028 está CONFIRMADA, e o auditor é explícito:** três medições
**gerais** pegam **nove das dez** construções *sem saber que elas existem*; 3,5 s
para responder o que 1.800 linhas respondiam pela metade; e ele **não recomenda
reverter** o caminho A.

### A regra de parada, pela primeira vez em doze rodadas

O auditor aponta uma formulação que, segundo ele, **não tem eixo ao lado**:

> **O oráculo tem de ser o papel, rasterizado.** Não *"está visível segundo o
> CSS"*, não *"está no texto do PDF"*, não *"o alfa não é zero"* — **tem tinta
> escura na faixa onde o timbre deveria estar?**

Não existe construção CSS futura que apague tinta do papel e passe por uma
contagem de pixel. Ele implementou em **12 linhas** para produzir a evidência do
BL-372. E generaliza: para cada propriedade dos cinco itens da DE-054, escolher
**um oráculo que não seja derivável do código que ele julga** — é por isso que
*"débito igual a crédito"* nunca gerou doze rodadas: o oráculo dela é o agregado
no banco, e sempre foi.

### ⚠️ Falta UMA ação, e ela é do Fred, na interface do GitHub

**Settings → Branches → regra da `main` → Require status checks**, acrescentar:

> **Identificação do emitente**

Enquanto isso não for feito, o job roda e avisa, mas **não impede** que alguém
mescle por cima dele vermelho — o BL-362 fecha **pela combinação**, e só
enquanto a exigência existir. **Não consigo ler nem escrever essa configuração**
(a API devolve `403 Resource not accessible by integration`), e registro isso
como **não verificado** em vez de presumir que está feito.

**A rodada 10 está integrada em `20da1fa`**, na branch
`claude/accounting-agent-team-setup-mn6lyf` — **ainda não na `main`**, e sem PR
aberto até a rodada 11 fechar. Duas correções de **guarda**, nenhuma mudança de
produto (`static/css/base.css` e `templates/**` intocados): **BL-351** junto com
**BL-353** (o detector passa a decidir pelo **conteúdo** do bloco, não pelo
prelúdio nem pelo caractere de abertura — CSS Nesting nativo passa a ser visto, e
media query irrelevante deixa de dar falso alarme) e **BL-352** (o universo de
telas vira módulo compartilhado, `universo_de_telas.py`, e cada guarda declara o
seu recorte com motivo próprio em vez de herdar por acidente o da vizinha).

Medição minha, com banco próprio: **1861 passed, 14 skipped** em 66,9s; `ruff
check` limpo; `ruff format --check` 204 arquivos; `manage.py check` limpo.

**A [DE-055](../projeto/decisoes.md) entrou em vigor e valeu a pena.** Entreguei
ao implementador quatro construções que o relatório da auditoria **não** nomeou,
e **guardei sete** para medir sozinho na integração. As sete passaram — sete de
sete. É a primeira vez nesta etapa que uma correção sobrevive às construções que
o autor dela não conhecia.

⚠️ **E a oitava construção, de outro eixo, furou:** registrei o **BL-360**
(ALTA), achado meu na integração. O motor de cascata **julga seletor que não sabe
ler**, e sempre para o lado de aprovar — a gramática que ele modela é tipo +
classe + combinador descendente, e diante de `[class]` ele conclui "casa com
tudo, especificidade zero" quando o valor real é o de uma classe. Medido em
Chromium com `emulate_media("print")` sobre o `base.css` real: **duas
construções devolvem a marca do fornecedor ao papel com a guarda aprovando**. O
caso principal é **anterior** à rodada 10 e nunca esteve no escopo do BL-351 —
não é regressão. É a **nona** ocorrência de "lista em vez de propriedade" nesta
etapa: prelúdio (BL-343) → caractere de abertura (BL-351) → gramática do seletor.

**A rodada 11 fechou os dois**, na mesma branch. O BL-360 foi corrigido pela
**recusa**, não pela extensão da gramática: regra que declare propriedade de
interesse com seletor que o motor não sabe ler faz a guarda **recusar julgar** —
o mesmo mecanismo que o arquivo já usava para at-rule. O conjunto do que se
recusa é **derivado do que o motor sabe ler**, não uma lista do que ele não sabe:
apara tipo, classe e pseudo-classe simples, e o que sobrar recusa. A linguagem
cresce; a lista do que ele sabe ler, não. O **BL-361** tirou a última lista do
caminho: a guarda de título roda sobre o universo inteiro e pula, **nomeando a
rota e o código**, só quando a resposta é redirecionamento.

Custo da recusa, **medido por mim antes de pedi-la**: o `base.css` real tem 5
seletores de atributo e 1 universal, e **nenhum declara `display`** — a recusa,
delimitada por propriedade de interesse, dispara **zero** vezes hoje. Não é falso
alarme (BL-321); é recusa onde o motor de fato não sabe.

**Verificação minha da rodada 11, com a máquina livre:** os dois falsos conformes
viraram recusa; o controle **sem** sabotagem continua aprovando; as sete
construções que eu guardara na rodada 10 continuam corretas; e **dez construções
novas**, que nenhuma das duas rodadas conhecia, saíram **dez de dez** — quatro
delas mirando especificamente a divergência entre as **duas** noções de *"declara
propriedade de interesse"*, que é a classe do BL-352. Suíte: **1871 passed, 15
skipped** em 67,2s; `ruff check` limpo; `ruff format --check` 204 arquivos;
`manage.py check` limpo.

**Decisão do Fred em 2026-09-19, depois de eu recomendar esperar:** nenhum
trabalho novo que toque `static/css/base.css`, ou que crie tela imprimível fora
da contabilidade, começa antes de BL-351 e BL-352 estarem corrigidos. Custa uma
rodada; a alternativa era apostar em disciplina, que é justamente o que
decidimos não fazer quando criamos as proteções.

### A rodada 13 está integrada em `240fb0d`, PR #38

Fechou **BL-372**, **BL-374**, **BL-375**, **BL-376**, **BL-377**, **BL-378**,
**BL-379**, **BL-381**, **BL-382** e **BL-385**. A correção central é o **oráculo
do pixel**: `pdftotext -bbox` para achar onde a linha do timbre realmente está na
folha, `pdftoppm -gray` para rasterizar, e contagem de pixels escuros na faixa.
Não pergunta mais *"o CSS diz que está visível?"* nem *"o texto está no PDF?"* —
pergunta **se há tinta no papel**.

O job de navegador foi **verificado por disparo real**, não por leitura de YAML:
caminho longo 54 s (medição em 4 s), caminho curto 24 s com 11 de 11 passos
pulados. Suíte: **1975 passed, 15 skipped**; lint, formatação e `manage.py check`
limpos.

### A décima auditoria REPROVOU, e trouxe uma decisão de CUSTO para o Fred

Relatório integral em
[2026-09-20-dl-026-dl-028-rodada-10.md](../auditorias/2026-09-20-dl-026-dl-028-rodada-10.md).
**Preservado sem uma palavra minha.**

**[BL-404](../projeto/backlog.md) — BLOQUEADOR, e é a décima segunda ocorrência
da classe da etapa.** `MARCA_DO_FORNECEDOR = "DataLedger"` é uma **lista de um
item**, a quinze linhas do topo do instrumento novo — a mesma forma de
`_PROPRIEDADES_DE_INTERESSE = ("display",)` que reprovou a rodada 8. É comparação
**literal e sensível a caixa** sobre o texto do PDF, então
`Relatorio gerado por DATALEDGER - dataledger.com.br` sai impresso em preto no
Balancete que o escritório entrega ao cliente, com `1975 passed` **e** com o job
de navegador dizendo `PASSOU`.

⚠️ **A assimetria estava à vista e ninguém a discutiu:** a metade *"o escritório
entra no papel"* ganhou um oráculo de **pixel**; a metade *"o fornecedor sai do
papel"* continuou uma **busca de substring**. A própria docstring do arquivo diz
que as duas metades *"só se provam JUNTAS"*.

**Mais quatro ALTAS, três delas dentro do instrumento:** **BL-405** (o oráculo
ancora por **texto**, então mede a tinta do primeiro texto igual da folha, não a
do timbre — 820 → 384 px; e a **DL-027** é literalmente a etapa que vai repetir
esse texto), **BL-406** (tela nova com timbre em rota que peça outro parâmetro
**nunca é medida**, e o job fica verde), **BL-407** (`opacity: 0.4` — timbre
perfeitamente legível — mede **zero** e reprova, e a justificativa escrita no
código é **falsificada por medição**) e **BL-408** (`docs/**` esconde 789 linhas
de Python executável do `ruff`, do `pytest` **e** do job — o defeito que o BL-379
existia para fechar, no arquivo de que a correção depende). **BL-409** a
**BL-411** são ressalvas com dono.

**O auditor retirou uma afirmação própria, medindo-a.** Ele havia escrito na
rodada 9 que *"tem tinta escura na faixa onde o timbre deveria estar"* não tem
eixo ao lado. Tem três — **onde** é a faixa, **o que** é tinta, **em qual folha**
— mais o quarto, que é o pior: **o oráculo cobre metade do critério**. A lição
que ele tira contra si mesmo: *"eu nomeei o **oráculo** e não o **requisito**.
Oráculo para metade de um requisito gera rodada para sempre."*

**E ele julgou o meu método.** *"Contar na fonte"* continua sendo **disciplina**,
e a prova é contra a minha própria correção do BL-380: eu contei na fonte e
publiquei *"11 de 11 pulados, 24 s"* — certo e **incompleto**, porque na mesma
revisão havia uma segunda execução, de `pull_request`, com **0 pulados e 63 s**
(**BL-411**, **BL-412**). E a correção do BL-388 é *"suficiente para o caso,
insuficiente para a classe"*: conferência por **contagem** prova cardinalidade,
não conteúdo — tem de comparar **conjuntos de identificadores** (**BL-413**).

#### ⚠️ A decisão que está com o Fred, e é de custo, não de engenharia

O auditor **não recomenda mais uma rodada desta forma**, e diz por que medindo:
*"o produto está certo em tudo que eu consegui medir, de novo, pela quarta rodada
seguida; o que se poliu foi a **garantia**; e a garantia continua descrita por uma
lista de achados em vez de por um enunciado do critério … se a rodada 11 for
escrita contra os meus K1–K4, eu prevejo K12 na rodada 11."*

As duas saídas que ele põe na mesa estão registradas em **BL-414**:

1. **Comprar uma frase executável** para o critério 9 inteiro, escrita **uma
   vez**, e fazer o instrumento ser julgado por ela — os quatro achados caem
   juntos porque todos são consequência de a frase não existir.
2. **Não declarar DL-026 e DL-028 fechadas** e sim declarar, como a
   [DE-054](../projeto/decisoes.md) já permite, **produto bom, garantia
   parcial**, com BL-404 nomeado como o buraco aberto. *"Isso custa zero e é
   verdadeiro. O que não é defensável é fechar dizendo que o critério 9 está
   garantido."*

**O que ele reafirma, e não pode se perder na reprovação:** os números declarados
**conferem um a um**; o controle limpo mede **348** px contra piso de **40**
(razão 8,7×) e toda sabotagem que apaga tinta mede **zero**; quebra de linha do
timbre, fonte de 1 px e de 3 px **não** passam; a camada barata pegou o que é
dela (12 e 17 reprovações nas duas sabotagens dele). **A tese do caminho A está
confirmada pela segunda rodada seguida, e ele não recomenda revertê-la.** O que
não está funcionando é o **processo de fechamento**, não o instrumento.

**E o BL-373 segue aberto, reconferido hoje nos três endpoints:** a `main`
continua **sem proteção**. Enquanto essa ação do Fred não for feita, tudo nesta
auditoria — inclusive o job novo — é **conselho**.

#### O que já andou, porque não depende da decisão

**BL-408 e BL-409 estão corrigidos em `a8cebd0`**, na mesma branch. Os dois `.py`
do gauntlet saíram de `docs/` e foram para `scripts/` — `git ls-files
'docs/**/*.py'` devolve **vazio** —, e o `extend-exclude` de `docs/**` **ficou**,
mas com justificativa **medida**: removê-lo reformataria 7 arquivos de
`docs/auditorias/`, todos por causa de bloco de código **citado verbatim** de um
relatório. É a DE-058 funcionando no primeiro uso: a justificativa antiga
(*"não há código Python de produção sob `docs/`"*) era falsa, e a nova é uma
medição com o comando ao lado. Suíte: **1976 passed, 15 skipped**.

⚠️ **E eu achei o eixo ao lado na integração — [BL-415](../projeto/backlog.md),
a décima terceira ocorrência.** O teste de propriedade que fechou o BL-409 é ele
próprio uma **lista**: pergunta *"a extensão está em `{py, css, html, yml, yaml,
toml}`?"*. Medido por mim em cópia isolada: três arquivos executáveis sob
`docs/` — um `.sh`, um `.ps1` e um `.js` — ficam escondidos com a suíte do
decisor em **`31 passed`**. Não é hipótese: `scripts/validate-docs.ps1` roda na
CI e `.claude/hooks/session-start.sh` roda em toda sessão. A correção pedida é
**inverter para o lado seguro** — enumerar o que pode ficar escondido (prosa e
imagem) e recusar o resto, inclusive arquivo sem extensão.

**Isto é a DE-055 funcionando como foi desenhada:** quem verificou não foi quem
escreveu a correção, e a construção não estava em relatório nenhum.

**O BL-415 foi corrigido em `81b8f0f`** — o teste passa a enumerar o que **pode**
ficar escondido (`.md`, `.png`, `.svg`) e recusa o resto, inclusive arquivo sem
extensão. Reprova os três executáveis do meu achado e o arquivo sem extensão;
zero ofensores hoje entre os 158 arquivos escondidos.

⚠️ **E na conferência seguinte eu achei o [BL-416](../projeto/backlog.md), a
décima quarta ocorrência — que é o BL-415 um nível acima.** A guarda nova vigia
**uma** das duas listas de exclusão, e a própria décima auditoria tinha nomeado
as duas: *"nenhuma das duas sabe da outra, e as duas erram junto"*. Medido em
cópia isolada: um arquivo com **quatro erros reais de `ruff`** mais **uma**
entrada no `extend-exclude` do `pyproject.toml` dão `All checks passed!` e
`31 passed`. Corrigimos o **efeito** nas duas listas e pusemos guarda só numa —
a guarda herdou em silêncio a cegueira que o relatório já descrevia.

A correção pedida é a forma de **propriedade**: o conjunto escondido vira a
**união** das fontes de exclusão, lidas de onde elas moram (`tomllib` lê o
`pyproject.toml`; o decisor exporta a sua lista), e a lista segura se aplica à
união.

**O implementador parou e perguntou, e foi o certo.** Medindo **antes** de
escrever, ele bateu no aviso que eu tinha deixado: as **22 migrações** do projeto
aparecem como as únicas ofensoras da união, e pôr `.py` na lista segura anularia
o teste inteiro.

**Decisão minha, em 2026-09-20 — o desenho é categoria com PROVA, não dispensa
por caminho.** `*/migrations/*` fica de fora do teste, mas o motivo **não** é
*"é código gerado"* nem *"é convenção da indústria"* — nenhum dos dois é
verificável, e justificativa não verificável é o que a DE-058 acabou de proibir.
O motivo é uma propriedade que se mede: **migração excluída do `ruff` continua
sendo EXECUTADA** — roda em `manage.py migrate` sobre banco vazio na CI e em toda
execução da suíte —, enquanto o `sonda_visibilidade.py` sob `docs/` não era
alcançado por mecanismo nenhum. A categoria não é *"migração"*; é **"escondido do
lint, mas alcançado pela execução"**.

⚠️ **E a dispensa não pode ser "o caminho contém `migrations/`"** — seria porta
aberta: bastaria criar `apps/qualquer/migrations/utilitario.py`. A dispensa é
provada **contra o Django**: todo arquivo dispensado tem de estar no grafo do
`MigrationLoader`, e arquivo sob `migrations/` que o Django não reconheça
**reprova, nomeado**. Propriedade derivada de quem manda — não lista nossa.

⚠️ **[BL-417](../projeto/backlog.md), achado do implementador na mesma medição, e
eu confirmei:** `padrao_para_regex('*/migrations/*')` devolve **`False`** para
`apps/contabilidade/migrations/0001_initial.py` (semântica do `paths:` do GitHub
Actions, onde `*` não cruza `/`), enquanto o `ruff` **exclui** o arquivo
(`ruff check --show-files . | grep -c migrations/` → **0**). Reusar o matcher
errado faria o teste **mentir para o lado de deixar passar**. Ele mediu **antes
de escrever**, e por isso o erro nunca entrou no código.

⚠️ **Leia isto junto com a PE-56.** Em uma tarde, a mesma lição apareceu **três**
vezes seguidas, nos três casos numa guarda escrita **para fechar a ocorrência
anterior**. É o argumento vivo a favor de escrever o critério uma vez, em vez de
comprar rodada atrás de rodada: *onde a guarda derivou de uma **propriedade**,
ela aguentou; onde derivou de uma **lista**, o item seguinte apareceu em menos de
uma hora*.

### O BL-418 é a DE-057 de novo, um nível abaixo — e é onde eu parei de comprar

O BL-416 foi corrigido em `40d8329`, e bem: a união das duas listas está feita, e
a dispensa da migração é **provada contra o Django** (`MigrationLoader`, isolado
por arquivo — o implementador mediu que `load_disk()` derrubaria as cinco
migrações boas junto, e resolveu sem isso).

Aí eu medi de novo. **Sem tocar** no `extend-exclude`, acrescentei a **chave
irmã**, na mesma tabela `[tool.ruff]` do mesmo arquivo:

```toml
exclude = ["ferramentas/**"]
```

com um arquivo versionado de **4 erros reais**. `ruff check .` → `All checks
passed!`; teste do decisor → `31 passed`. **Décima quinta ocorrência.**

**E aqui eu parei de pedir "leia também essa chave".** O quinto item eu já sei
qual é — `ruff.toml` e `.ruff.toml` na raiz **substituem** o `pyproject.toml`
inteiro — e o sexto também. O defeito de forma é outro:

> Nós estamos **reimplementando a configuração da ferramenta** para adivinhar o
> que ela enxerga. É **exatamente** o que o motor de cascata fazia com o
> navegador, e é por isso que a [DE-057](../projeto/decisoes.md) mandou abrir um
> Chromium de verdade. Descemos um nível e repetimos o erro.

O `fnmatch`, a questão de matcher do BL-417 e os quatro limites declarados
existem **todos** só porque estamos simulando o `ruff`.

**A correção é derivar da ferramenta:** *"escondido do `ruff`"* passa a ser o
código versionado **menos** o que `ruff check --show-files .` devolve — medido
hoje, **217** `.py` versionados contra **196** vistos. Isso fecha `exclude`,
`extend-exclude`, `ruff.toml`, `.ruff.toml`, `respect-gitignore` e configuração
por subdiretório **de uma vez, sem lista nenhuma**. O lado da CI não muda: ali o
código é nosso, e importar a lista do decisor **é** perguntar à fonte.

**Corrigido em `9cdcb32`**, e provado do jeito certo: um `ruff.toml` na raiz, com
o `pyproject.toml` **intacto**, reprova — que é a prova de que a derivação é da
ferramenta e não da nossa leitura. Custo do subprocesso: **11 ms**,
indistinguível do ruído. Com o `ruff` ausente, o teste **pula nomeando o
motivo** — nunca passa calado, que seria o BL-375 outra vez.

### E aqui a cadeia termina: [BL-419](../projeto/backlog.md) e por que eu NÃO escrevi mais uma guarda

Conferindo o `9cdcb32`, medi o espelho do BL-418 do outro lado. **Sem tocar** em
`CAMINHOS_NAO_RELEVANTES` nem em nenhum `.py`, acrescentei três linhas ao
`.github/workflows/identificacao-do-emitente.yml`:

```yaml
  pull_request:
    paths-ignore:
      - '**'
```

Suíte de `scripts/`: **`65 passed`**. O módulo Python que o BL-379 extraiu para
ficar ao alcance do `ruff` e do `pytest` continua perfeito — e o arquivo que
decide se ele **chega a rodar** não é lido por ninguém.

⚠️ **Eu parei de escrever guarda aqui, e é decisão declarada, não cansaço.**
Quem pode editar o workflow para desligar a verificação **também pode mesclar por
cima dela vermelha**: a `main` não tem proteção (**BL-373**, remedido pelo
auditor na décima rodada nos três endpoints). Uma guarda nova contra edição de
workflow seria a **décima sexta** ocorrência e **não fecharia nada**, porque quem
ela vigia tem a permissão que a torna irrelevante.

> **A cadeia de guardas termina em proteção de branch com status check
> obrigatório, e em nenhum outro lugar.**

Então o BL-419 fica como **limite declarado** (DE-056), a correção real é a ação
do Fred no GitHub (**BL-373**), e a guarda barata — conferir que o workflow não
tem `paths`/`paths-ignore` — vale **depois** da proteção, nunca antes: antes,
seria teatro. Enfileirado **atrás da DL-029**.

### O que a rodada 6 encontrou sobre o papel que sai da impressora

Duas descobertas sobre o que o contador **recebe de fato** ao apertar Ctrl+P:

- **BL-331**: existe guarda para a marca do fornecedor **sair** do papel e
  nenhuma para o timbre do escritório **entrar**. Apagando a regra do timbre,
  o relatório sai sem identificação nenhuma e a suíte fica verde.
- **BL-332**: com as opções **padrão** do navegador, o `<title>` da página vai
  para o cabeçalho de toda folha — e o `<title>` termina em "DataLedger".
  As duas medições (a do implementador e a do auditor) estão certas; elas
  medem **artefatos diferentes**, e a que o contador produz é a do auditor.

**Dois deles dependem de decisão do Fred** e estão com ele: o texto que
substitui o nome do fornecedor no cabeçalho do documento (BL-332) e se o nome
do **operador** deve sair na folha que vai para o cliente (BL-338).

### A rodada 6, que originou o que hoje está na `main`

Ela teve duas partes: as correções da quarta auditoria (BL-305, BL-314, BL-318
a BL-325) e, por pedido do Fred em 2026-09-19 — *"agora resolve os itens que
ficaram abertos no backlog"* —, os quatro itens de produto que as rodadas
anteriores tinham deixado abertos **por decisão declarada** (BL-277, BL-281,
BL-282, BL-287).

**Medição minha, com a máquina livre:** `1715 passed, 12 skipped` em 48,8s;
`ruff check` limpo; `ruff format --check` 199 arquivos; `manage.py check`
limpo.

**Dez sabotagens refeitas por mim**, sempre em cópia isolada da árvore (nunca
no repositório — BL-311), e **uma delas encontrou defeito**: devolver a marca
do fornecedor ao relatório impresso deixava a suíte inteira verde (**BL-329**,
quinta ocorrência da guarda posta um passo antes da entrega). Reprovei,
devolvi ao responsável com o requisito escrito como **propriedade** em vez do
caso que eu tinha achado, e a guarda nova morre nas quatro saídas — três
provadas por ele, a quarta por mim.

Dois achados novos que não vieram de auditoria: **BL-328** (a integração
contínua não pode ligar `makemigrations --check`, e por isso nada impede o
esquema do banco de divergir do código) e **BL-330** (um invariante **contábil**
— a conciliação do balancete — depende hoje de espaço em branco no HTML).

Registro honesto: **BL-327**, a credencial do banco de desenvolvimento exposta
três vezes no mesmo dia, por três mecanismos diferentes, a terceira por mim,
depois de eu ter proibido exatamente isso a dois agentes. A causa é do
ambiente, não da disciplina de ninguém, e a regra foi reescrita para uma que
seja cumprível.

Sete auditorias, **as sete REPROVARAM**, e as sete acharam coisa real:

| Auditoria | Revisão | Parecer | Achados |
| --- | --- | --- | --- |
| [Rodada 1](../auditorias/2026-09-18-dl-024-rodada-1.md) | `5c7303e` | REPROVADO | 3 altos, 6 médios, 4 baixos |
| [Rodada 2](../auditorias/2026-09-18-dl-024-rodada-2.md) | `c71bd55` | REPROVADO | 3 altos, 7 médios, 5 baixos |
| [Rodada 3](../auditorias/2026-09-18-dl-024-rodada-3.md) | `23c6ac8` | REPROVADO | 3 altos, 5 médios, 3 baixos |
| [Rodada 4](../auditorias/2026-09-19-dl-024-rodada-4.md) | `8235635` | REPROVADO | 1 alto, 5 médios, 2 baixos |
| [Rodada 5](../auditorias/2026-09-19-dl-026-rodada-5.md) | `53388c8` | REPROVADO | 2 altos, 5 médios, 3 baixos |
| [Rodada 6](../auditorias/2026-09-19-dl-026-rodada-6.md) | `8aa84b6` | REPROVADO | 2 altos, 4 médios, 4 baixos |
| [Rodada 7](../auditorias/2026-09-19-dl-026-rodada-7.md) | `920822a` | REPROVADO | 1 bloqueador, 1 alto, 4 médios, 3 baixos |

⚠️ **Os quatro relatórios dizem "DL-024" e continuam dizendo**: são documento
histórico, e a etapa foi renumerada para DL-026 depois de eles existirem. O
plano da etapa explica a renumeração.

### A causa das três reprovações, e ela é de distribuição

O auditor nomeou o que eu não tinha conseguido nomear:

> *"A distância entre isto e a aprovação não é de esforço. É de **onde a guarda
> é posta**: três vezes nesta rodada ela foi posta contra a frase do meu
> relatório em vez de contra o requisito."*

Eu vinha entregando aos implementadores **o achado**, com reprodução e "como
verificar". A correção nascia do **tamanho exato do achado** — fechava aquele
caso e nada mais, e a defesa ficava sempre uma auditoria atrás.

**A rodada 5 entregou o REQUISITO**, com o achado como ilustração, e a ordem de
serviço dizia: *"se a sua guarda fecha exatamente os casos citados e nada
além, ela está errada mesmo passando"*. O resultado apareceu — os dois
especialistas acharam, cada um, uma ocorrência que **ninguém tinha pedido**:

- o `desenvolvedor-pleno` mediu que a causa do BL-307 era mais funda que a
  relatada: passar `linhas_excluidas_do_total` fecharia só **2 dos 4** casos, e
  os outros dois balanceiam as partidas válidas perfeitamente. Criou uma quinta
  condição e quatro casos novos;
- o `especialista-frontend` descobriu que a **soma por coluna** do balancete
  também é igual por partida dobrada — uma troca em *todas* as linhas seria
  invisível.

### Medição da rodada 5, feita pelo `arquiteto-senior` com a máquina livre

`1525 passed, 12 skipped` em 57,08s; `ruff check` limpo; `ruff format --check`
178 arquivos; `manage.py check` limpo; `git diff -- templates/ static/` vazio.

**As quatro sabotagens, refeitas pelo arquiteto em cópia da árvore:**

| Sabotagem | Resultado |
| --- | --- |
| BL-307 — neutralizar a quinta condição do veredito | **6 failed** |
| BL-308 — trocar o crédito da faixa pelo débito | **4 failed** |
| BL-309 — módulo novo **bem formado** em `apps/<mod>/templates/`, sem linha no §3 | **1 failed** |
| BL-313 — `max-width`, `min-height`, `box-shadow`, `2lh`, `1.5cap`, `translateX` | **1 failed** |

A terceira é a que mais importa para a evolução por módulos: a tela **estende a
moldura, tem legenda, escopo e classe de valor** — e reprova assim mesmo,
porque o módulo não declarou a pergunta que ela responde antes de gravar.

Distribuição da rodada 4, arquivos disjuntos, contrato de contexto fixado por
mim **antes** para os dois trabalharem em paralelo sem esperar um pelo outro:

| Frente | Responsável | Itens |
| --- | --- | --- |
| Servidor e mecanismo | `desenvolvedor-pleno` | BL-289 (a decisão na view), BL-291, BL-292, BL-293, BL-294, BL-298 |
| Telas e guardas de tela | `especialista-frontend` | BL-289 (o ramo do template), BL-290, BL-295, BL-296, BL-297, BL-301, BL-302 |
| Documentação e processo | `arquiteto-senior` | BL-299, BL-300, BL-303, BL-304 — **concluídos** em `7720e5f` |

**Contrato de contexto** (nomes fixos, não negociáveis sozinho):
`veredito_fechamento` ∈ `fecha` / `nao_fecha` / `nao_conferido` no lançamento;
`veredito_balancete` ∈ `fecha` / `nao_fecha` / `nada_a_conferir`. **Nenhuma
comparação de valor no template** — foi comparar texto que produziu o BL-289.

Decisões de coordenação que continuam valendo desde a rodada 2:

1. **Os conjuntos de arquivos não se tocam.**
2. **Os especialistas não commitam.** A integração e a medição solo são minhas.
3. **Medição concorrente não vira relatório** (**BL-273**): resultado anômalo
   em massa se repete sozinho antes de ser reportado. Já aconteceu — `1279
   errors` numa revisão que, sozinha, deu `1279 passed`.
4. **Preservação adiciona arquivo por caminho, nunca `git add -A`** — um
   retrato meu já levou junto trabalho alheio sem descrever (registrado em
   `c71bd55`).
5. **Pedido de auditoria leva o SHA e o `git status` conferidos na hora**
   (**BL-304**, e a regra está em [equipe.md](equipe.md)).

**Decisão do Fred, 2026-09-18, sobre quando mesclar.** Ele pediu "commitar
tudo, abrir os PR e mesclar para não perdermos nada", ouviu a recomendação
contrária e **aprovou esperar**. O que está registrado, porque a distinção é o
ponto: **commitar e publicar é o que preserva; mesclar é declarar pronto.** A
preservação já está garantida e medida (HEAD local e `origin` no mesmo SHA).
Mesclar antes da auditoria levaria para a `main` um veredito de fechamento que
mente na tela vazia. **Sequência aprovada:** integrar → medir sozinho →
auditar → abrir o PR → merge do Fred com o parecer em mãos.

Precedente que motivou a recomendação: o **PR #24 foi mesclado** estando
marcado como rascunho e com "não deve ser mesclado" escrito no corpo —
rascunho no GitHub **não impede** merge, e a `main` carrega a DL-023 com três
pendências abertas por causa disso.

Ficaram fora das rodadas anteriores, por decisão registrada: **BL-277** (o
filtro do balancete), **BL-281** (parênteses no balancete — muda a view),
**BL-282** (timbre do escritório na impressão) e **BL-287** (a ajuda de data
unificada só no balancete; Diário, Razão e Lançamento seguem duplicando).

**Em 2026-09-19 o Fred mandou fechá-los** — *"agora resolve os itens que
ficaram abertos no backlog"* —, então os quatro entraram na rodada 6. Dois
deles são contábeis de verdade, não cosméticos: o parênteses de saldo
invertido é a convenção que faz o contador enxergar anomalia no balancete, e o
timbre é o que impede o relatório de sair com a marca do fornecedor em vez da
do escritório.

Distribuição da rodada 6, conjuntos de arquivos disjuntos e **um banco de
dados por frente** (BL-273: duas execuções de `pytest` no mesmo banco produzem
falha falsa):

| Frente | Responsável | Itens | Banco |
| --- | --- | --- | --- |
| Varredura e marcação | `desenvolvedor-pleno` | BL-305, BL-319, BL-320, BL-321, BL-322 | `ci_r6` |
| Telas e visibilidade | `especialista-frontend` | BL-314 (juiz), BL-323, BL-325 — entregues em `df711c7` | — |
| Servidor dos itens de produto | `desenvolvedor-pleno` | BL-281 (contexto da view), BL-282 (timbre no modelo) | `ag_bal` |
| Telas dos itens de produto | `especialista-frontend` | BL-287 agora; BL-277 e a renderização de BL-281/282 na onda seguinte | `ag_tela` |
| Guardas do estado e redação | `arquiteto-senior` | BL-324, BL-326 (`de10963`), BL-314 redação (`eb62482`) | — |

**Decisão de arquitetura tomada por mim nesta rodada, para não travar o
BL-282:** o timbre do escritório é **texto**, não imagem. Upload de logotipo
traz armazenamento de mídia, validação de tipo de arquivo e isolamento de
mídia entre escritórios — três problemas que não cabem num item de backlog e
que precisam de etapa própria. É limitação declarada, não esquecimento, e é
reversível.

**Antes, em 2026-09-16:
[DL-023](../planos/DL-023-integridade-administrativa.md) — integridade
administrativa, PRIMEIRA ETAPA DE CÓDIGO da fila aprovada. Rodada 1
REPROVADA em `96284a4`; rodada 2 corrigiu os dez itens; RODADA 3 — a segunda
auditoria — APROVOU COM RESSALVAS na revisão `a612604`.** Rodada 4, curta, em
curso: três itens baratos (**BL-264**, **BL-265**, **BL-266**). Relatórios
integrais e preservados:
[rodada 1](../auditorias/2026-09-16-dl-023-rodada-1.md) e
[rodada 3](../auditorias/2026-09-16-dl-023-rodada-3.md) — nesta etapa o número
conta **rodadas de trabalho**, não auditorias, e por isso não existe arquivo de
"rodada 2".

---

> **Duas frentes conviveram.** O que segue veio pela `main`, de outra linha
> de trabalho, e está aqui porque o estado é fonte única — não porque seja o
> passo desta branch. ⚠️ A etapa citada abaixo como DL-024 é a **trilha
> íntegra**; a identidade visual, que nasceu com o mesmo número, foi
> renumerada para **DL-026** na junção de 2026-09-19 (ver o plano dela para
> o motivo).

**EM OUTRA FRENTE, desde 2026-09-16 (trabalho que chegou pela `main`, não desta branch): DL-024 — trilha íntegra e processo — em validação, com a rodada 1 validada
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
