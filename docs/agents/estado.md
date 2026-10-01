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

Medido em 25/09/2026 no código e no Git, não copiado de documento anterior; remedido em 30/09/2026 (análise do repositório que originou a DL-052).

| Área | O que existe hoje |
| --- | --- |
| Plataforma | Escritórios isolados entre si, usuários, papéis, entrada pública, cadastro de novo escritório, primeiro acesso e convite; página inicial por módulo com filtros persistentes (DL-049, DL-051) |
| Cadastro | Empresas e estabelecimentos, CNPJ alfanumérico, histórico de regime tributário, NIRE |
| Contabilidade | Plano de contas hierárquico com circulante/não circulante e **linha da DRE (art. 187, propriedade de apresentação — pode mudar com movimento, DE-086)**; lançamento por partidas dobradas, imutável depois de gravado; estorno; idempotência; competência com encerrar, reabrir e marcar como entregue; Diário, Razão, Balancete e **Balanço Patrimonial**; conferências de lote; parâmetros contábeis por empresa com vigência e **zeramento do resultado** em duas etapas (DL-043); **apuração e tela da DRE** (mês e acumulado do exercício), servidor e formulário de classificação (DL-045 fatias 1 a 3); **DLPA — Demonstração dos Lucros ou Prejuízos Acumulados** (art. 186): classificação ligada à conta, apuração pelo movimento com conciliação ao Balanço, veto que nomeia o que falta e telas de emissão/classificação (DL-048, fatia CTB-12 + CTB-13), com API própria (fatia D8) |
| Documento emitido | Identificação obrigatória por classe de documento; veto de emissão do Balancete e do Balanço que não fecham; critério de apuração impresso |
| Trilha de auditoria | Na mesma transação da gravação, imutável, cobrindo também o admin |
| Fiscal | Recepção e consulta de NFS-e nacional (DL-010 fatia 1): XML e ZIP, deduplicação, cancelamento por evento, isolamento por escritório |
| Cadastro de cliente pessoa física | CPF e modo de escrituração livro-caixa (DL-038); CNPJ e CPF únicos por escritório (DL-041) |
| **Não existe** | Compensação de lucros e prejuízos acumulados (HI-26/PE-38); as demonstrações anuais da DL-048 depois da DLPA (**DMPL, DFC, DRA e DVA**); escrituração fiscal e apuração; módulos Folha, Honorários e Processos/Paralegal; assistente de IA; servidor MCP |

**Verificação de 30/09/2026** (contêiner Linux do Claude Code na web, Python
3.13.12, PostgreSQL 16.13 local, sobre a `main` depois do PR #65, antes da
DL-052):

- `ruff check` limpo; `ruff format --check` com 318 arquivos já formatados;
  `manage.py check` sem problema; `makemigrations --check` sem mudança;
  `migrate` em banco vazio sem erro.
- `pytest` completo: **3.591 aprovados, 1 reprovado, 50 pulados**, em 245 s.
  A reprovação é
  `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`,
  que exige Python 3.14 (a CI usa 3.14; não foi rodado em 3.14 aqui). Os 50
  pulados são de ambiente: `poppler-utils`, fontes e Chromium.
- `gerar_agentes.py --verificar` OK. `validate-docs.ps1` **não executado**
  (sem `pwsh` neste contêiner); roda oficial na CI.
- A análise achou defeitos de nível 1 no convite e nas invariantes do livro:
  ver [Próximo passo](#próximo-passo) e o backlog (BL-544 a BL-559).
- O conteúdo anterior deste bloco (verificação de 29/09 no Windows) está em
  [historico-do-estado.md](historico-do-estado.md).

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
| [DL-047](../planos/DL-047-mapa-de-paridade-funcional.md) | Mapa de paridade funcional e plano detalhado por módulo | Integrada (PR #55) — só documentação; seis planos em [paridade/](../projeto/paridade/README.md) |
| [DL-048](../planos/DL-048-contabilidade-anual-demonstracoes.md) | Contabilidade anual: estrutura de demonstração ligada à conta, com DLPA, DMPL, DFC, DRA e DVA (CTB-12 a CTB-17) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-049](../planos/DL-049-home-por-modulo.md) | Página inicial por módulo, filtros persistentes e fila operacional multiempresa | Integrada (PR #63) — auditoria e reconferência em `docs/auditorias/` |
| [DL-050](../planos/DL-050-esperas-de-thread-com-timeout.md) | Toda espera de thread em teste ganha timeout, com asserção de que a thread concluiu | Integrada (PR #64) — nível 3 |
| [DL-051](../planos/DL-051-correcao-dos-modulos.md) | Correção dos módulos: Vendas fora do produto; inventário dentro de Fiscal | Integrada (PR #65) |
| [DL-052](../planos/DL-052-integridade-do-livro-e-do-acesso.md) | Integridade do livro e do acesso: convite com validade, invariantes do lançamento no banco, estorno atômico | Integrada (PR #66) — auditoria e reconferência aprovadas com ressalvas; limite aceito no BL-569 |
| [DL-053](../planos/DL-053-fechamento-do-livro-caixa.md) | Fechamento de mês do livro-caixa (RC-145, RC-146, RC-147) | Integrada (PR #67) — auditoria aprovada com ressalvas; limite do encadeamento fechado pela DL-054 |
| [DL-054](../planos/DL-054-encadeamento-do-fechamento.md) | Mês encerrado congelado contra o encadeamento do carnê-leão (RC-148) | Integrada (PR #70) — auditoria aprovada com ressalvas; H1 e H2 na DL-060 |
| [DL-055](../planos/DL-055-cliente-nao-ve-a-carteira.md) | O papel Cliente não vê o cadastro de empresas (BL-549) | Integrada (PR #69) — auditoria aprovada com ressalvas; BL-584 a BL-587; DE-095 |
| [DL-056](../planos/DL-056-limite-de-tentativas.md) | Limite de tentativas no login e no cadastro (BL-552) | Integrada (PR #71) — nível 2; limites são hipótese a validar |
| [DL-058](../planos/DL-058-pequenas-fugas-de-informacao.md) | Pequenas fugas de informação (BL-554, BL-555) | Integrada (PR #72) — auditoria aprovada com ressalvas; BL-592 a BL-596; DE-096 |
| [DL-059](../planos/DL-059-trilha-do-convite-e-eventos-sem-ip.md) | Trilha do convite e eventos sem IP (BL-560, BL-566, BL-579) | Integrada (PR #73) — auditoria aprovada com ressalvas; BL-597 a BL-601 |
| [DL-060](../planos/DL-060-confirmacao-da-cascata.md) | A reabertura em cascata confirma exatamente os meses mostrados (BL-588, BL-589) | Integrada (PR #74) — reconferência aprovada com ressalvas; BL-602 |
| [DL-061](../planos/DL-061-dmpl.md) | DMPL, etapa CTB-14 da DL-048 (RC-151) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-057](../planos/DL-057-ip-real-na-trilha.md) | IP real na trilha atrás de proxy (BL-553) | Integrada (PR #68) — auditoria aprovada com ressalvas; BL-577 obrigatória antes da implantação |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa. A F3 (encerramento de
competência) tem só o plano, na branch `claude/dl-016-f3-encerramento-competencia`,
não integrada — por isso a DL-016 aponta para o Próximo passo.

## Próximo passo

**Leva de 30/09 a 01/10/2026 concluída: DL-052 a DL-060 integradas**
(PR #66 a #74). Desenvolvidas em até 4 cópias isoladas em paralelo (RC-149)
e integradas **uma por vez** na branch `claude/zealous-goldberg-jr5ggu` →
`main`, cada uma com auditoria aprovada e os quatro checks verdes (RC-150).

**Em andamento: DL-061 — DMPL** (CTB-14 da DL-048), escolhida pelo Fred em
01/10/2026. Linha automática pela contrapartida, como na DLPA (RC-151); manual do
sistema de referência lido (p. 122, 192–194, 616–622, 773–774). Fatia 1
(servidor e tela) integrada na branch; [auditoria rodada 1](../auditorias/2026-10-01-dl-061-rodada-1.md)
**reprovou** (N1 e N2 altas: evento errado em vez de veto); rodada única de correção
integrada (`40e47f5`), em **reconferência final**;
merge só depois da auditoria e da CI verde. Pontos abertos: BL-603 a BL-607.
Logo depois da fatia 1: coluna de dividendo adicional proposto (RC-153,
BL-603). HI-50 confirmada pelo Fred (RC-152): alíneas "c" e "d" revogadas.

- **DL-054** — **integrada pelo PR #70** (squash `e7b85aa`).
- **DL-055** — **integrada pelo PR #69** (squash `9ceda53`).
- **DL-056** — **integrada pelo PR #71** (squash `25c37ba`).
- **DL-058** — **integrada pelo PR #72** (squash `dd745a4`). Fechou um
  canal real: o login Basic autenticava em duas rotas da API, fora do limite
  de tentativas.
- **DL-059** — **integrada pelo PR #73** (squash `5149cc4`).
- **DL-060** — **integrada pelo PR #74** (squash `8a9a45b`). A API de
  reabrir em cascata passou a exigir `meses_confirmados`.
- **DL-057** — **integrada pelo PR #68** (squash `49f118d`). Antes da
  implantação: BL-577 (recusar `0.0.0.0/0`).

**DL-053 — integrada pelo [PR #67](https://github.com/fredabsd-svg/DataLedger/pull/67)**
em 30/09/2026 (squash `0d68949`), com os quatro checks verdes no último
commit e ordem do Fred. Fechamento de mês do livro-caixa com trava de
lançamento, estorno e dependentes; papéis de fechamento num ponto só; tela
de encerrar e reabrir. [Auditoria](../auditorias/2026-09-30-dl-053-rodada-1.md)
aprovada com ressalvas. **Limite conhecido até a DL-054:** lançamento em
mês aberto anterior ainda pode mudar o carnê-leão de mês posterior encerrado
do mesmo ano (BL-572). Observação de CI: pelo evento `pull_request`, o job
de identificação do emitente roda a bateria do instrumento (~9 min); pelo
`push`, não — a diferença de duração não indica travamento.
Incidente de 01/10/2026 (PR #73): o passo de testes do instrumento foi
cancelado aos 6 min sem saída do pytest nem autor identificado, e a execução
ficou presa como "em andamento" na API (reexecutar respondeu "já está
rodando"; cancelar, "não está em andamento"). Saída adotada: novo commit com
conteúdo real, que dispara execução nova; nunca commit vazio.

**DL-052 — integrada pelo [PR #66](https://github.com/fredabsd-svg/DataLedger/pull/66)**
em 30/09/2026 (squash `258e413`), com os quatro checks verdes no último
commit e ordem do Fred para integrar. Convite com validade e amarrado ao
e-mail; débito = crédito, valor positivo, tipo válido e imutabilidade do
lançamento garantidos também pelo PostgreSQL; estorno e criação atômicos com
a trilha; usuário se desativa, não se apaga (RC-144).
[Rodada 1](../auditorias/2026-09-30-dl-052-rodada-1.md) e
[reconferência](../auditorias/2026-09-30-dl-052-reconferencia.md) aprovadas
com ressalvas. Limite aceito: a trava de partida nova protege contra escrita
acidental, não contra quem escreve SQL direto (BL-569).

**Decisões abertas desta leva (só o Fred):**

- Manter ou rever a DE-086 (reclassificação da DRE em mês encerrado, BL-550).
- Confirmar os limites da DL-056 (5 por usuário e 20 por IP em 15 min; 5
  cadastros por IP por hora) — hoje são hipótese.
- Texto do Início do papel Cliente (BL-586).

**Antes da implantação:** BL-577 (recusar `0.0.0.0/0` nos proxies
confiáveis) e PE-07 (backup e restauração).

**Fila seguinte, sujeita ao Fred:**

1. **DL-048, CTB-14 (DMPL)** — nível 1. A DLPA (CTB-12 + CTB-13) está
   integrada pelo PR #59 e a API dela (D8) pelo PR #62. Decisões do Fred de
   29/09 já fechadas: versionar pela data de início do exercício, com adoção
   antecipada da NBC TG 51 prevista. Lacuna declarada: o ato da CVM que
   aprovou o CPC 26 não foi lido em fonte oficial.
2. **Reclassificação em período encerrado** (BL-550) e a titularidade do
   CNPJ no cadastro (resto do BL-552, depende do Fred).
3. **DL-016 F3** (encerramento de competência) — só o plano existe.
4. **DL-027 fatias C e D** — logotipo e pré-visualização; PE-48, PE-50,
   PE-51 e PE-52 abertas.

**Decisões com o Fred:**

- Balanço emitido sem o zeramento (três caminhos apresentados em 21/09).
- Quem vê a contabilidade de quais empresas (PE-36).
- Pendências do carnê-leão: HI-32, HI-37, HI-38, HI-39; importação real no
  Carnê-Leão Web (HI-41 a HI-43) só o escritório confere.
- Compensação de prejuízos (PE-38/HI-26) e validação do art. 193 antes do
  cálculo da reserva legal.
- Manuais do sistema de referência em repositório privado separado: falta o
  Fred criar e informar o nome. Este repositório é **público**.
- **Proteção da `main` (BL-02):** só o Fred liga. Os quatro nomes de checagem
  estão no fim do [AGENTS.md](../../AGENTS.md).

**Antes de pôr dado real de cliente:** backup e restauração nunca planejados
nem verificados (PE-07); contêiner Docker não executado nas últimas entregas;
residência do dado na nuvem (PE-25).

O relato das sessões de 29 e 30/09 que estava aqui (correções normativas do
Fred sobre a DMPL, esperas de thread, PR #58 mesclado sem chegar à `main`)
está preservado em [historico-do-estado.md](historico-do-estado.md); as
fontes normativas estão em [requisitos.md](../projeto/requisitos.md).

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

Sessão de 30/09/2026: contêiner Linux do Claude Code na web, Python 3.13.12 em
`.venv`, PostgreSQL 16 local iniciado pelo gancho de sessão, sem `pwsh` e sem
Docker. A CI usa Python 3.14 e PostgreSQL 16 — é a evidência que vale para
merge. Agentes em paralelo usam **banco de teste próprio** (nome do banco
trocado no `DATABASE_URL`).
