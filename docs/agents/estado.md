# Estado do projeto

Este é o **único** lugar onde o estado do DataLedger é descrito (instrução
permanente do Fred, 2026-09-13). O `README.md` aponta para cá e não repete o
estado. **Ao concluir qualquer etapa, atualize este arquivo** — faz parte da
entrega, como teste e commit.

Regras deste arquivo, aprendidas com defeito:

- **Enxuto.** Até 25/09/2026 ele tinha 3.457 linhas e ficou duas entregas
  atrasado (dizia a DL-037 "em validação" depois do merge do PR #46). O relato
  de cada rodada de auditoria mora nos relatórios de
  [`docs/auditorias/`](../auditorias/) e nos planos; o conteúdo anterior está
  preservado sem edição em [`historico-do-estado.md`](historico-do-estado.md).
- **Revisão da `main` não se escreve aqui:** muda a cada merge, inclusive o
  deste arquivo. Leia do Git: `git rev-parse origin/main`.
- **A seção "Próximo passo" é lida pelo gancho de início de sessão**
  (`.claude/hooks/session-start.sh` imprime de `## Próximo passo` até
  `## Estado do repositório`). Não renomeie nenhuma das duas. Até 25/09/2026 a
  seção não existia e o gancho não injetava nada.

## Resumo

Medido em 25/09/2026 no código e no Git, não copiado de documento anterior.

| Área | O que existe hoje |
| --- | --- |
| Plataforma | Escritórios isolados entre si, usuários, papéis, entrada pública, cadastro de novo escritório, primeiro acesso e convite |
| Cadastro | Empresas e estabelecimentos, CNPJ alfanumérico, histórico de regime tributário, NIRE |
| Contabilidade | Plano de contas hierárquico com circulante/não circulante; lançamento por partidas dobradas, imutável depois de gravado; estorno; idempotência; competência com encerrar, reabrir e marcar como entregue; Diário, Razão, Balancete e **Balanço Patrimonial**; conferências de lote |
| Documento emitido | Identificação obrigatória por classe de documento; veto de emissão do Balancete e do Balanço que não fecham; critério de apuração impresso |
| Trilha de auditoria | Na mesma transação da gravação, imutável, cobrindo também o admin |
| **Não existe** | **DRE**; **encerramento do exercício (zeramento)**; recepção de documentos fiscais; módulos Fiscal, Folha, Honorários e Processos/Paralegal; assistente de IA; servidor MCP |

**Verificação local em 25/09/2026** (PostgreSQL 16, Python 3.13.12, commit do
merge do PR #46): `ruff check`, `ruff format --check`, `manage.py check`,
`migrate` em banco vazio e `gerar_agentes.py --verificar` aprovados;
`pytest`: **2191 passed, 1 failed, 45 skipped**. A falha é de ambiente:
`test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`
exige Python 3.14, que é o da CI, e a máquina tinha 3.13. `validate-docs.ps1`
**não executado** localmente (sem `pwsh`); roda na CI.

## Todas as etapas

A tabela diz o que cada etapa é e, para as concluídas, por onde entrou. Etapa
em andamento **aponta** para o Próximo passo em vez de descrever o estado aqui
(guarda em `apps/core/tests/test_documentacao_do_estado.py`).

| Etapa | Entrega | Situação |
| --- | --- | --- |
| [DL-001](../planos/DL-001-documentacao-inicial.md) | Documentação inicial, escopo, regras e modelo de PR | Integrada |
| [DL-002](../planos/DL-002-arquitetura-fundacao.md) | Arquitetura e fundação: Django, DRF, PostgreSQL, CI | Integrada |
| [DL-003](../planos/DL-003-fundacao-multiempresa.md) | Autenticação e isolamento entre escritórios | Integrada |
| [DL-004](../planos/DL-004-cadastro-empresas.md) | Cadastro central de empresas e estabelecimentos | Integrada |
| [DL-005](../planos/DL-005-permissoes-auditoria.md) | Permissões por papel e trilha de auditoria | Integrada |
| [DL-006](../planos/DL-006-contabilidade-basica.md) | Contabilidade básica: plano de contas, partidas dobradas, Diário, Razão, Balancete | Integrada |
| [DL-007](../planos/DL-007-correcao-bloqueadores-contabilidade.md) | Correção dos bloqueadores da auditoria inicial | Integrada (PR #11) |
| [DL-008](../planos/DL-008-politica-monetaria-e-validacao-de-escala.md) | Política monetária e módulo de arredondamento | Integrada (PR #11) |
| [DL-009](../planos/DL-009-fundacao-de-interface.md) | Fundação de interface, estados de erro, acessibilidade | Integrada (PR #11) |
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção e conferência de documentos fiscais | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-011](../planos/DL-011-cnpj-alfanumerico.md) | CNPJ alfanumérico (NT 2025.001 / IN RFB 2.229) | Integrada (PR #12) |
| [DL-012](../planos/DL-012-readme-identidade-visual.md) | README e identidade visual | Integrada (PR #13) |
| [DL-013](../planos/DL-013-logo-oficial.md) | Logo oficial (conceito do Fred em vetor) | Integrada (PR #17) |
| [DL-014](../planos/DL-014-guardas-de-processo.md) | Guardas de processo: gancho de sessão, atestado no PR | Integrada (PR #15) — a proteção da `main` (BL-02) é ação do Fred e segue pendente |
| [DL-015](../planos/DL-015-contabilidade-utilizavel.md) | Diário, Razão e Balancete por período, conciliáveis | Integrada (PR #17) |
| [DL-016](../planos/DL-016-competencia-e-fechamento.md) | Competência e fechamento de período | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-017](../planos/DL-017-interface-da-contabilidade.md) | Interface da contabilidade no navegador | Integrada (PR #19) |
| [DL-018](../planos/DL-018-primeiro-acesso.md) | Primeiro acesso: primeiro escritório e convite pelo produto | Integrada (PR #27) |
| [DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md) | Papéis dos agentes com fonte única, gerados para Claude Code e Codex | Integrada (PR #20) |
| [DL-020](../planos/DL-020-consolidacao-pos-auditoria.md) | Consolidação pós-auditoria e regras contábeis confirmadas | Integrada (PR #21) |
| [DL-021](../planos/DL-021-robustez-do-gerador-no-windows.md) | Gerador de papéis robusto no Windows (quebra de linha) | Integrada (PR #22) — permissão de arquivo no Windows segue aberta (BL-175) |
| [DL-022](../planos/DL-022-plano-mestre-e-reconciliacao.md) | Plano mestre e reconciliação da documentação | Integrada (PR #23) |
| [DL-023](../planos/DL-023-integridade-administrativa.md) | Integridade administrativa (BL-83, BL-211) | Integrada (PR #27) |
| [DL-024](../planos/DL-024-trilha-integra-e-processo.md) | Trilha íntegra: auditoria na mesma transação, imutável, com diff | Integrada (PR #28) |
| [DL-025](../planos/DL-025-ordens-diretas-do-responsavel.md) | Ordem direta do Fred é demanda formal | Integrada (PR #29) |
| [DL-026](../planos/DL-026-identidade-visual-e-interface.md) | Identidade visual e redesenho da interface | Integrada (PR #35, #36 e #38) |
| [DL-027](../planos/DL-027-documento-emitido-e-personalizacao.md) | Documento emitido: identificação por classe e personalização | Integrada (fatias A, B.1, B.2 e B.3 — PR #39 a #42) — fatias C (logotipo) e D (pré-visualização) **não iniciadas** |
| [DL-028](../planos/DL-028-o-juiz-aponta-para-o-produto.md) | Identificação do emitente medida no navegador real, na CI | Integrada (PR #38) |
| [DL-029](../planos/DL-029-a-frase-executavel-do-criterio-9.md) | Frase executável do critério 9 | Integrada (PR #38) |
| [DL-030](../planos/DL-030-a-trilha-cobre-o-admin.md) | Trilha de auditoria cobre o admin, com antes e depois | Integrada (PR #38) |
| [DL-031](../planos/DL-031-fatia-2-a-tela-do-fechamento.md) | Tela do fechamento de competência (fatia 2 da DL-016) | Integrada (PR #38) |
| [DL-032](../planos/DL-032-a-camada-de-saldos.md) | Camada de saldos | Integrada (PR #38) |
| [DL-033](../planos/DL-033-circulante-e-nao-circulante.md) | Circulante e não circulante | Integrada (PR #38) |
| [DL-034](../planos/DL-034-a-tela-do-balanco.md) | Tela do Balanço Patrimonial | Integrada (PR #38) |
| [DL-035](../planos/DL-035-as-guardas-da-demonstracao.md) | Guardas da demonstração (BL-514 a BL-519) | Integrada (PR #43 e #44) |
| [DL-036](../planos/DL-036-entrada-e-cadastro.md) | Página inicial pública e cadastro de novo escritório | Integrada (PR #45) |
| [DL-037](../planos/DL-037-entrada-visual.md) | Redesenho visual da entrada pública | Integrada (PR #46) |
| [DL-038](../planos/DL-038-cliente-pessoa-fisica.md) | Cliente pessoa física no cadastro de empresas: CPF e modo de escrituração | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-039](../planos/DL-039-ressalvas-recepcao-e-pessoa-fisica.md) | Ressalvas da reconferência da DL-010 F1 e da DL-038 (BL-526 a BL-529) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-040](../planos/DL-040-navegacao-e-arquitetura-de-informacao.md) | Navegação e arquitetura de informação: mapa de telas, menu principal, trilha e padrão de página | Em desenvolvimento |
| [DL-041](../planos/DL-041-unicidade-por-escritorio.md) | Unicidade de CNPJ e CPF por escritório (RC-115) | Planejada |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa.

## Próximo passo

**AGORA — DL-039: ressalvas da recepção de NFS-e e do cliente pessoa física.**
[Plano](../planos/DL-039-ressalvas-recepcao-e-pessoa-fisica.md). A BL-526 (erro
de sistema do banco aparecendo como nota recusada) precisa estar corrigida antes
do primeiro uso real da recepção.

Situação das duas etapas que a antecedem, na branch `claude/vigilant-bardeen-jo12l4`
(ainda não integradas à `main`):

- **DL-010 fatia 1** (recepção de NFS-e nacional) e **DL-038** (cliente pessoa
  física): auditoria independente **reprovou** na
  [rodada 1](../auditorias/2026-09-25-dl-010-f1-dl-038-rodada-1.md) e
  **aprovou com ressalvas** na
  [reconferência](../auditorias/2026-09-25-dl-010-f1-dl-038-reconferencia.md) em
  `88e7ac5`. Correções decididas em DE-076 (um envio por vez por escritório,
  2.000 arquivos por envio). Verificação do arquiteto nessa revisão: suíte
  completa 2582 aprovados, 45 pulados, 1 falha preexistente de ambiente.
- Ressalvas no backlog, BL-526 a BL-535. A **PE-68** foi respondida pelo Fred em
  26/09 (por escritório, RC-115) e virou a DL-041.
- Falta: PR para a `main` e CI verde (Python 3.14) no commit mais recente.
- Commits `wip: preservação, não entrega` na branch protegem trabalho em
  andamento neste ambiente efêmero; **não** são entrega.

Fila depois dela, em ordem recomendada e sujeita ao Fred:

0. **DL-040 — navegação e arquitetura de informação** (Fred, 26/09): mapa de
   telas e menu principal, em desenvolvimento pelo `especialista-frontend` numa
   worktree isolada; integração só depois de o Fred ver as capturas.
0. **DL-041 — unicidade de CNPJ e CPF por escritório** (Fred, 26/09, RC-115):
   [plano](../planos/DL-041-unicidade-por-escritorio.md), logo depois da correção
   da DL-039.
1. **Encerramento do exercício (DL-016 F3)** — zeramento das contas de resultado
   por lançamento em duas etapas (RC-104), periodicidade alternativa por empresa
   (RC-105). Só o **plano** existe, na branch não integrada
   `claude/dl-016-f3-encerramento-competencia`; revisar antes de reaproveitar.
   Depende de onde guardar **parâmetro contábil por empresa** (BL-474).
2. **DRE** (CON-12 do plano mestre) — pelo movimento do período, não pela
   camada de saldos (limite declarado no próprio código). Depende do mesmo
   BL-474.
3. **Livro-caixa e carnê-leão** (RC-113) — módulo novo sobre a DL-038, com
   regras levantadas em fonte oficial da Receita antes de qualquer cálculo.
4. **DL-027 fatias C e D** — logotipo e pré-visualização; PE-48, PE-50, PE-51
   e PE-52 abertas.

**Cliente pessoa física** — o escritório atende (RC-112) e faz carnê-leão e
livro-caixa para esses clientes (RC-113). A DL-038 os cadastra na própria
`Empresa`, com tipo de inscrição e modo de escrituração (RC-114); a recepção
vincula as notas de CPF cadastrado. Livro-caixa e carnê-leão são módulo novo, com
regras ainda a levantar em fonte oficial.

Decisões que estão com o Fred e afetam a fila:

- O Balanço pode ser emitido sem o zeramento? Três caminhos apresentados em
  21/09; recomendação: mostrar o resultado do período dentro do PL.
- Quem vê a contabilidade de quais empresas (PE-36).
- Unicidade do CNPJ global ou por escritório (PE-21).
- Proteção da `main` (BL-02): só o Fred pode ligar, nas configurações do
  GitHub. Os quatro nomes de checagem estão no fim do [AGENTS.md](../../AGENTS.md).

O que o escritório **não** tem, antes de pôr dado real de cliente: backup e
restauração nunca planejados nem verificados (PE-07); contêiner Docker não
executado nas duas últimas entregas; decisão de residência do dado na nuvem
(PE-25).

## Estado do repositório

- A `main` recebe tudo por PR; a revisão atual se lê com
  `git rev-parse origin/main`.
- **Proteção da `main`: ausente** na última medição registrada (auditorias 9 a
  12, até 2026-09-20). Não remedida nesta atualização.
- Branches remotas antigas, conferidas em 25/09/2026: cinco estão **superadas**
  (o conteúdo já está na `main` por outro caminho) —
  `claude/dl-016-competencia-e-fechamento`,
  `claude/multi-model-ia-structure-k1um7i`,
  `docs/dl-atualizar-estado-continuidade`, `docs/fix-gate-regex` e
  `fix/bl-261-keyerror-conta-pai-id`. Uma tem conteúdo **não integrado**:
  `claude/dl-016-f3-encerramento-competencia` (só o plano da F3). Apagar
  branches é ação que depende de ordem do Fred.
- Equipe de agentes: papéis, permissões e limitações em
  [equipe.md](equipe.md). Nesta plataforma os papéis rodam como **subagentes**,
  não como integrantes de equipe com lista compartilhada de tarefas.

## Ambiente de verificação

Sessão de 25/09/2026: contêiner Linux do Claude Code na web, Python 3.13.12 em
`.venv`, PostgreSQL 16 local iniciado pelo gancho de sessão, sem `pwsh` e sem
Docker. A CI usa Python 3.14 e PostgreSQL 16 — é a evidência que vale para
merge.
