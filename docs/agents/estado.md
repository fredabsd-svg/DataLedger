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

Medido em 25/09/2026 no código e no Git, não copiado de documento anterior; atualizado em 26/09/2026 com as DL-010 F1, DL-038, DL-041, DL-043 e DL-045 (fatias 1 e 2).

| Área | O que existe hoje |
| --- | --- |
| Plataforma | Escritórios isolados entre si, usuários, papéis, entrada pública, cadastro de novo escritório, primeiro acesso e convite |
| Cadastro | Empresas e estabelecimentos, CNPJ alfanumérico, histórico de regime tributário, NIRE |
| Contabilidade | Plano de contas hierárquico com circulante/não circulante e **linha da DRE (art. 187, propriedade de apresentação — pode mudar com movimento, DE-086)**; lançamento por partidas dobradas, imutável depois de gravado; estorno; idempotência; competência com encerrar, reabrir e marcar como entregue; Diário, Razão, Balancete e **Balanço Patrimonial**; conferências de lote; parâmetros contábeis por empresa com vigência e **zeramento do resultado** em duas etapas (DL-043); **apuração e tela da DRE** (mês e acumulado do exercício), servidor e formulário de classificação (DL-045 fatias 1 a 3); **DLPA — Demonstração dos Lucros ou Prejuízos Acumulados** (art. 186): classificação ligada à conta, apuração pelo movimento com conciliação ao Balanço, veto que nomeia o que falta e telas de emissão/classificação (DL-048, fatia CTB-12 + CTB-13) |
| Documento emitido | Identificação obrigatória por classe de documento; veto de emissão do Balancete e do Balanço que não fecham; critério de apuração impresso |
| Trilha de auditoria | Na mesma transação da gravação, imutável, cobrindo também o admin |
| Fiscal | Recepção e consulta de NFS-e nacional (DL-010 fatia 1): XML e ZIP, deduplicação, cancelamento por evento, isolamento por escritório |
| Cadastro de cliente pessoa física | CPF e modo de escrituração livro-caixa (DL-038); CNPJ e CPF únicos por escritório (DL-041) |
| **Não existe** | Compensação de lucros e prejuízos acumulados (HI-26/PE-38); as demonstrações anuais da DL-048 depois da DLPA (**DMPL, DFC, DRA e DVA**); escrituração fiscal e apuração; módulos Folha, Honorários e Processos/Paralegal; assistente de IA; servidor MCP |

**Verificação local em 29/09/2026** (Windows, Python 3.14.7, SQLite, branch
`feat/dl-048-dlpa`; o pytest desta máquina precisa do contorno de ambiente
`PYTEST_PLUGINS=dsh_tmp_fix` com `PYTHONPATH` apontando para
`Harness/.dsh-tmp/` e `TMPDIR` fora do repositório — sem isso o pytest morre
com `PermissionError` no `tmp_path_factory`, defeito do sandbox deste Windows,
não do projeto):

- `ruff check` **limpo**; `ruff format --check` **313 arquivos** já
  formatados; `manage.py check` **sem problema**; `makemigrations --check`
  **sem mudanças**.
- **A fatia não introduz NENHUMA falha de regressão** — medido por
  comparação nominal da lista de testes que falham em `apps/contabilidade`,
  na branch da fatia e num *worktree* limpo de `origin/main`, com o mesmo
  comando e o mesmo recorte: **54 failed nos dois, e os 54 são os MESMOS
  testes** (`Compare-Object` sem diferença), com **1269 → 1310 passed**
  (**+41** = os 39 da DLPA + 2 casos parametrizados de acessibilidade das
  duas rotas novas). `apps/core` idem: **13 failed nos dois, os mesmos 13**,
  **685 → 686 passed** (+1, a varredura de restrições com a constraint nova).
  As 67 falhas são **pré-existentes e alheias à DL-048**.
- Deselecionados por travarem neste Windows/SQLite (a CI em Linux +
  PostgreSQL é quem roda a classe): `test_bl144_codigo_conta_duplicado` e
  tudo casando com `concorrent`/`thread`.
- **Não executado localmente:** a medição no navegador real
  (`scripts/medir_identificacao_do_emitente.py`), o `validate-docs.ps1`
  (exige PowerShell 7; só 5.1 instalada) e `gerar_agentes --verificar`
  (reprova só pelas permissões 0o666 do Windows, BL-175, pré-existente).
  Os três rodam oficiais na CI.
- **Não reconferido nesta sessão:** a fonte normativa. Não houve acesso à
  rede (`planalto.gov.br` e a busca web falharam), então a conformidade com
  o art. 186 **não foi revalidada por mim** — a confirmação de 28/09/2026
  continua registrada em
  [requisitos.md](../projeto/requisitos.md) e segue de pé por ser de sessão
  anterior, não por ter sido reconferida agora.
- ✅ **Resolvido em 29/09/2026 (decisão do Fred):** a rubrica "Correção
  monetária do saldo inicial" (art. 186, I) foi **removida** do enum, da
  apuração e do texto emitido — a Lei 9.249/95, art. 4º, p.ú., vedou a
  correção monetária da moeda e a linha é letra morta em exercício de 2026.
  Membro removido inteiro (a migração 0012 nunca entrou na `main`), dois
  testes novos de contrato, nota registrada em
  [requisitos.md](../projeto/requisitos.md) sem corrigir o sentido do texto
  normativo. A Lei 9.249/95 **não foi reconferida na fonte oficial** (sem
  rede nesta máquina) — pendente de leitura no Planalto.

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
| [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) | Recepção e conferência de documentos fiscais | Integrada (fatia 1, NFS-e nacional, PR #47) — fatias 2 (NF-e) e 3 ainda não planejadas em detalhe |
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
| [DL-038](../planos/DL-038-cliente-pessoa-fisica.md) | Cliente pessoa física no cadastro de empresas: CPF e modo de escrituração | Integrada (PR #47) |
| [DL-039](../planos/DL-039-ressalvas-recepcao-e-pessoa-fisica.md) | Ressalvas da reconferência da DL-010 F1 e da DL-038 (BL-526 a BL-529) | Integrada (PR #47) |
| [DL-040](../planos/DL-040-navegacao-e-arquitetura-de-informacao.md) | Navegação e arquitetura de informação: mapa de telas, menu principal, trilha e padrão de página | Integrada (PR #48) |
| [DL-042](../planos/DL-042-redesenho-global-saas.md) | Redesenho global da interface com a skill de design de SaaS | Integrada (PR #48) |
| [DL-043](../planos/DL-043-parametros-contabeis-e-zeramento.md) | Parâmetros contábeis por empresa e zeramento do resultado (RC-104, RC-105, BL-474) | Integrada (PR #49) |
| [DL-041](../planos/DL-041-unicidade-por-escritorio.md) | Unicidade de CNPJ e CPF por escritório (RC-115) | Integrada (PR #48) |
| [DL-044](../planos/DL-044-telas-de-trabalho.md) | Telas de trabalho com aspecto de produto profissional (RC-116, RC-117) | Integrada (PR #50 e #51) |
| [DL-045](../planos/DL-045-demonstracao-do-resultado.md) | Demonstração do Resultado do Exercício: classificação (art. 187) e apuração pelo movimento (RC-118 a RC-120) | Integrada (PR #52) |
| [DL-046](../planos/DL-046-livro-caixa-e-carne-leao.md) | Livro-caixa e carnê-leão do cliente pessoa física (RC-127 a RC-129) | **Integrada (PR #53, #54 e #56)** — fatias 1, 2 e 3; a auditoria da fatia 3 não consta em `docs/auditorias/` |
| [DL-047](../planos/DL-047-mapa-de-paridade-funcional.md) | Mapa de paridade funcional e plano detalhado por módulo | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-048](../planos/DL-048-contabilidade-anual-demonstracoes.md) | Contabilidade anual: estrutura de demonstração ligada à conta, com DLPA, DMPL, DFC, DRA e DVA (CTB-12 a CTB-17) | Em desenvolvimento |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa.

## Próximo passo

**AGORA — sessão de 2026-09-29. DL-048: auditoria executada e **REPROVADA**,
achados de alta corrigidos, PR #59 aberto e verde na `main`; falta o merge:**

1. **DL-048 (Contabilidade anual — CTB-12 + CTB-13, a DLPA) — em
   desenvolvimento; a fatia está CODE E TESTADA na branch
   `feat/dl-048-dlpa`.** Entregue nesta sessão: campo `classificacao_dlpa`
   na conta (molde CTB-12, migração 0012), `apurar_dlpa` /
   `avaliar_emissao_da_dlpa` / `classificar_conta_na_dlpa`, as telas
   `dlpa` e `conta_classificacao_dlpa`, ícone/menu/hub, a DLPA no piso de
   classe 2 da medição de identificação e **39 testes novos**
   (`apps/contabilidade/tests/test_dl048_dlpa.py`). Decisões D1–D9,
   critérios cobertos e limitações declaradas no
   [plano](../planos/DL-048-contabilidade-anual-demonstracoes.md);
   fontes normativas em [requisitos.md](../projeto/requisitos.md)
   (RC-137 a RC-140).

   ⚠️ **O PR #58 foi MESCLADO e o conteúdo NÃO chegou à `main`** — o
   defeito de encadeamento que o `AGENTS.md` §6 descreve, medido nesta
   sessão. O #57 (plano) foi mesclado na `main` às 11:17:33 e o #58 foi
   mesclado na branch intermediária `docs/dl-048-plano` às 11:17:52,
   **19 segundos depois**, quando a base já não carregaria mais o
   conteúdo para a `main`. O GitHub mostra "MERGED"; a `main` **não tem
   nenhum dos 3 commits da fatia**. A frase que este arquivo fazia até
   28/09 — *"depois o GitHub reaponta a base quando a branch do plano for
   apagada"* — **é falsa** e foi removida: apagar a branch não entrega o
   conteúdo, apenas o deixa inacessível. O conserto é um PR novo da
   branch de trabalho direto para a `main`.

   Estado verificado em 29/09/2026: o conserto é o **PR #59**, aberto da
   branch de trabalho direto para a `main` (o merge `main ←
   feat/dl-048-dlpa` foi conferido **limpo** com `git merge-tree`, sem
   conflito). Nível 1 — **a auditoria independente foi EXECUTADA e
   REPROVOU** ([rodada 1](../auditorias/2026-09-29-dl-048-dlpa-rodada-1.md),
   16 achados: 2 de alta, 9 de média, 5 de baixa). Os achados de alta e de
   média prioritária foram **corrigidos e reconferidos** nesta mesma
   rodada — uma auditoria, uma correção, uma reconferência, como o
   `AGENTS.md` §3.1 exige; o restante está **declarado como limitação** no
   plano, não escondido. O PR #59 está **CLEAN** com os quatro jobs
   verdes. ⚠️ **Falta o merge**, e a **conformidade normativa segue NÃO
   CONCLUÍDA**: sem rede nesta máquina, nem a implementação nem a auditoria
   leram Planalto/CFC, e **nenhuma** linha do art. 186 foi confirmada em
   fonte oficial. Depois disso: fatia de paridade de API
   (`DlpaView` + `ContaClassificacaoDlpaView`, decisão D8) e o CTB-14
   (DMPL), que reusa a MESMA leitura de eventos (RC-137). Pendências do
   Fred que seguem abertas: PE-38/HI-26 (mecanismo de compensação — a
   leitura D7 é neutra a ela) e a validação do art. 193 antes de
   implementar o cálculo da reserva legal.
2. **DL-046 fatia 3 — INTEGRADA pelo PR #56 (28/09, 09:02).** O relato
   anterior ("falta (c) auditoria e (d) PR") era o estado da branch antes
   do merge: o PR existe e está mesclado; **a auditoria independente da
   fatia 3 não consta em [`docs/auditorias/`](../auditorias/)** (lá só
   estão rodada 1 e reconferência das fatias 1 e 2) — se o Fred exigir a
   rodada, ela ainda não aconteceu. A importação real no Carnê-Leão Web
   (HI-41, HI-42, HI-43) só o escritório pode conferir.
3. **DL-047 — integrada pelo PR #55** (só documentação): seis planos de
   paridade item por item em
   [docs/projeto/paridade/](../projeto/paridade/README.md) — Contabilidade
   (74), Fiscal (91), Folha e Ponto (80), Honorários (59), Patrimônio (26)
   e Lalur (26). A opção A escolhida pelo Fred virou a DL-048, acima.
4. **Manuais do sistema de referência:** o Fred escolheu guardá-los num
   **repositório privado separado**. Pendente: ele criar o repositório e
   informar o nome. Enquanto isso, nada deles entra aqui — este repositório
   é **público** (conferido na API em 2026-09-27); o Fred ainda vai decidir
   se o DataLedger continua público.

- **DL-040, DL-041 e DL-042**: integradas à `main` pelo PR #48.
- **DL-043** (parâmetros contábeis e zeramento): integrada à `main` pelo PR
  #49, fechada sem terceira rodada de auditoria (verificação descrita no
  [plano](../planos/DL-043-parametros-contabeis-e-zeramento.md)). Pendências
  do Fred: HI-24, HI-25, HI-26/PE-38 e PE-69.
- **DL-044** (telas de trabalho, nível 2): **aprovada pelo Fred** (RC-117) com
  o Conta Azul como referência de padrão (RC-116). Todas as telas autenticadas
  migradas: casca azul, barra lateral como navegação única (sem linha de abas
  na Contabilidade nem no Fiscal), título e ações no topo branco, cartões,
  tabelas com superfície, ações de linha como botão, Início com indicadores e
  carteira, hub de relatórios. Capturas em
  [dl044/comparacao.md](../assets/telas/dl044/comparacao.md). Identificação do
  emitente e densidade do Balancete medidas antes e depois. A parcial sem
  uso das antigas abas do Fiscal foi apagada com autorização do Fred (26/09).
  Integrada pelo PR #50; o PR #51 corrigiu a folha de estilo servida em cache
  depois do merge (versão do arquivo no link).
- **DL-045** (DRE, nível 1): integrada pelo PR #52, fechada sem
  terceira rodada de auditoria (verificação descrita no
  [plano](../planos/DL-045-demonstracao-do-resultado.md)). Ressalva: mover
  conta de grupo só pelo admin até existir tela de editar conta (BL-541).
- **DL-046** (livro-caixa e carnê-leão, nível 1): fatia 1 (livro-caixa)
  integrada pelo PR #53; fatia 2 (apuração) integrada pelo PR #54. Plano com fontes (RIR/2018 arts. 68-69 e 118-125, Receita
  Federal, leiaute público do Carnê-Leão Web, manual do sistema de
  referência) e respostas do Fred (RC-127 a RC-130). Rodada 1 da auditoria
  ([relatório](../auditorias/2026-09-26-dl-046-rodada-1.md)) e
  [reconferência](../auditorias/2026-09-27-dl-046-reconferencia.md)
  reprovaram; a DE-088 reabriu a regra de CPF/CNPJ, que passou a seguir o
  modelo do leiaute oficial. Fechamento **sem terceira rodada**, por
  verificação independente descrita no
  [plano](../planos/DL-046-livro-caixa-e-carne-leao.md) — ela achou o
  instrumento de medição do N3 quebrado, corrigido e medido de novo. A
  **fatia 2** (apuração mensal e
  anual do carnê-leão, PE-71 respondida em fonte oficial — RC-131) foi
  **integrada pelo PR #54**: a [rodada 1](../auditorias/2026-09-27-dl-046-fatia2-rodada-1.md) e a
  [reconferência](../auditorias/2026-09-27-dl-046-fatia2-reconferencia.md)
  reprovaram; as correções seguiram a DE-091 e a DE-092 (a RC-132 estava
  errada no limite do livro-caixa, conferido nas perguntas 427 a 429 do
  Perguntas e Respostas IRPF 2026). Fechamento **sem terceira rodada**, por
  verificação independente descrita no
  [plano](../planos/DL-046-livro-caixa-e-carne-leao.md). Pendências do Fred:
  validar a leitura literal da compensação do exterior (HI-38), o aluguel
  lançado sem as parcelas do art. 42 (HI-39), o resíduo abaixo de R$ 10,00
  em dezembro (HI-37) e o valor por dependente de 2026 (HI-32).
- Agentes em paralelo usam **banco de teste próprio** (nome do banco trocado no
  `DATABASE_URL`).
- Commits `wip: preservação, não entrega` na branch protegem trabalho em
  andamento neste ambiente efêmero; **não** são entrega.

Fila depois da DL-045, em ordem recomendada e sujeita ao Fred:

1. **DL-027 fatias C e D** — logotipo e pré-visualização; PE-48, PE-50, PE-51
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
