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
| **Não existe** | Compensação de lucros e prejuízos acumulados (HI-26/PE-38); as demonstrações anuais da DL-048 depois da DMPL (**DFC, DRA e DVA**); escrituração fiscal e apuração; módulos Folha, Honorários, Patrimônio e Lalur; assistente de IA; servidor MCP |

⚠️ **Corrigido em 04/10/2026 (DL-064).** Esta linha listava a **DMPL** como
inexistente, e a linha da tabela de etapas a registrava como **Integrada** —
o próprio estado do projeto, que é a fonte única, se contradizendo a 90
linhas de distância. Foi esse o defeito que quase fez planejar contra um
mapa que afirma que a DMPL não existe.

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
| [DL-061](../planos/DL-061-dmpl.md) | DMPL, etapa CTB-14 da DL-048 (RC-151) | Integrada (PR #76, #77 e #79) — fatias 1, etapa 2 e fatia 2; pontos abertos BL-606, BL-607, BL-622, BL-625, BL-626 e BL-627 |
| [DL-062](../planos/DL-062-sinal-da-raiz-retificadora.md) | Sinal da conta-RAIZ retificadora no Balanço Patrimonial (BL-604) | Integrada (PR #81, squash `46d80a1`) — auditoria aprovada com ressalvas, reconferência aprovada; ciclo do §3.1 encerrado |
| [DL-063](../planos/DL-063-fecha-a-leva-da-dl-061.md) | Fecha a leva da DL-061: coluna da DMPL nas duas portas, teste do snapshot e dica condicionada (BL-606, BL-607, BL-625) | **Integrada (PR #84, squash `c32cfe6`)** — o conteúdo **não tinha chegado à `main`** (o PR #82 foi mesclado na branch intermediária `fix/dl-062-…`); recuperado com a `base` reapontada para o destino real |
| [DL-065](../planos/DL-065-reclassificacao-em-periodo-fechado.md) | Reclassificar conta com movimento em competência encerrada ou entregue não pode reescrever DLPA nem DMPL já apuradas (BL-550) | **Integrada (PR #85, squash `012a759`)** — ciclo de auditoria encerrado no veredito **REPROVADO** da reconferência; N1, N2 e N3 corrigidos depois, sem terceira rodada |
| [DL-066](../planos/DL-066-dfc.md) | DFC — Demonstração dos Fluxos de Caixa, direto e indireto (CTB-15 da DL-048) | Situação em **[Próximo passo](#próximo-passo)** — **fatia 1 integrada pelo PR #89** (núcleo da apuração; auditoria e reconferência aprovadas com ressalvas, N1 e N2 corrigidos) e **fechada pelo PR #90** (porta de classificação, telas, API e método indireto); a fatia 2, método direto, está na fila |
| [DL-067](../planos/DL-067-plano-do-modulo-fiscal.md) | Plano do módulo fiscal de out/2026 a 2028, com a reforma tributária, conciliado com a paridade fiscal | Planejada |
| [DL-057](../planos/DL-057-ip-real-na-trilha.md) | IP real na trilha atrás de proxy (BL-553) | Integrada (PR #68) — auditoria aprovada com ressalvas; BL-577 tratada na DL-068 |
| [DL-068](../planos/DL-068-prontidao-para-implantacao.md) | Prontidão para implantação: Django 6.1.2, limite no login do admin, `.dockerignore`, `DJANGO_AMBIENTE` (BL-82) e proxies `/0` (BL-577) | **Integrada (PR #91, squash `7c23894`, merge feito pelo Fred em 07/10/2026)** — auditoria e reconferência aprovadas com ressalvas; R1 com o Fred (BL-642) |
| [DL-069](../planos/DL-069-travas-no-banco.md) | Travas no banco: livro-caixa imutável, período encerrado recusa INSERT, trilha imutável | Situação em **[Próximo passo](#próximo-passo)** — fatias 1 e 2 integradas (PR #92 e #93); fatia 3 bloqueada na PE-77 |
| [DL-070](../planos/DL-070-melhorias-com-equipe-multiagente.md) | Melhorias do repositório com equipe multiagente (RC-160): entradas do acesso, consultas por linha, testes que faltavam | Integrada (PR #94, squash `76cb92a`) — auditoria e reconferência aprovadas com ressalvas; BL-652 a BL-654 abertos |
| [DL-071](../planos/DL-071-marcacao-da-dmpl-em-periodo-fechado.md) | A marcação manual da DMPL respeita o período fechado (BL-655) | Integrada (PR #95, squash `389aafe`) — auditoria e reconferência aprovadas com ressalvas; BL-656 a BL-659 abertos |
| [DL-072](../planos/DL-072-escrituracao-das-nfse-prestadas.md) | Fiscal F1: escrituração das NFS-e prestadas (natureza, competência, estorno, conferência) | Integrada (PR #96, squash `8f36cd4`) — auditoria e reconferência aprovadas com ressalvas |
| [DL-073](../planos/DL-073-validador-ibscbs.md) | Fiscal: validador de conformidade IBS/CBS das NFS-e recebidas (modo aviso, HI-61) | Integrada (PR #96, squash `8f36cd4`) — auditoria e reconferência aprovadas com ressalvas |
| [DL-074](../planos/DL-074-receita-e-rbt12-do-simples.md) | Fiscal: receita mensal, receita informada, confirmação e RBT12 do Simples por mercado | Integrada (PR #97, squash `ebc40a3`) — rodada 1 reprovada, reconferência aprovada com ressalvas |
| [DL-075](../planos/DL-075-pre-das-do-simples.md) | Fiscal: pré-DAS do Simples para prestadores de serviço (Anexos I a V como dado, fator r, teto do ISS, segregação) | Integrada (PR #98, squash `05668d4`) — rodada 1 reprovada, reconferência aprovada com ressalvas |
| [DL-076](../planos/DL-076-iss-por-municipio-palmas.md) | Fiscal: ISS por município, começando por Palmas (alíquota informada, conferência por nota, apuração fora do Simples, retido sofrido, outros municípios) | Integrada (PR #99, squash `6c2baf7`) — rodada 1 e reconferência aprovadas com ressalvas |
| [DL-077](../planos/DL-077-importacao-e-exportacao-contabil-em-txt.md) | Contabilidade: importar e exportar plano de contas e lançamentos em TXT e Excel | Integrada (PR #100, squash `929a79a`; PR #101, squash `b60560b`) — efetivação parcial suspensa (BL-676) |
| [DL-078](../planos/DL-078-servicos-tomados-e-retencoes.md) | Fiscal: serviços tomados, ISS retido pelo tomador e retenções federais | Integrada (PR #102, squash `49eacba`) — rodada 1 e reconferência aprovadas com ressalvas |
| [DL-079](../planos/DL-079-lucro-presumido-irpj-csll.md) | Fiscal: Lucro Presumido, IRPJ e CSLL trimestrais com o acréscimo da LC 224 | Integrada (PR #103, squash `6eb922e`) — rodada 1 e reconferência aprovadas com ressalvas |
| [DL-080](../planos/DL-080-recepcao-de-nfe.md) | Fiscal: recepção de NF-e (modelo 55) e NFC-e (modelo 65), fatia 2 da DL-010 | Integrada (PR #104, squash `c01b451`) — rodada 1 reprovada, reconferência aprovada com ressalvas |
| [DL-081](../planos/DL-081-escrituracao-das-nfe-de-saida.md) | Fiscal: escrituração das NF-e de saída e da devolução de venda | Integrada (PR #105, squash `2911eb6`) — rodada 1 reprovada, reconferência aprovada com ressalvas |
| [DL-082](../planos/DL-082-pre-das-de-comercio-e-industria.md) | Fiscal: pré-DAS de comércio e indústria (Anexos I e II) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-083](../planos/DL-083-receita-de-nfe-no-presumido.md) | Fiscal: receita de NF-e no Lucro Presumido e regras de receita da RC-172 | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-084](../planos/DL-084-rotina-do-presumido.md) | Fiscal: rotina do Lucro Presumido (RC-172) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-085](../planos/DL-085-escrituracao-de-nfe-em-volume.md) | Fiscal: escrituração de NF-e e NFC-e em volume (RC-173) | Situação em **[Próximo passo](#próximo-passo)** |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa. A F3 (encerramento de
competência) tinha só o plano, na branch `claude/dl-016-f3-encerramento-competencia`,
que não existe mais no remoto (medido em 07/10/2026), e não foi integrada — por isso a DL-016 aponta para o Próximo passo.

## Próximo passo

**Ordem permanente do Fred desde 08/10/2026 (RC-164):** depois da DL-071,
construir o **módulo fiscal por completo**, sem parar; dúvidas de domínio vão
ao `contador-senior` (Fable) antes do Fred; Opus coordena, Haiku programa,
Sonnet audita. O que a IA responde é **hipótese** (HI-54) até o Fred validar;
nada de alíquota, prazo ou leiaute sem fonte oficial; nenhuma transmissão,
publicação ou exclusão (HI-55). Roteiro de execução no fim do
[DL-067](../planos/DL-067-plano-do-modulo-fiscal.md); consulta registrada em
[consultas/](../projeto/consultas/2026-10-08-contador-senior-fiscal.md);
hipóteses HI-56 a HI-63 em [requisitos.md](../projeto/requisitos.md).

**AGORA, em 08/10/2026:**

1. **[DL-071](../planos/DL-071-marcacao-da-dmpl-em-periodo-fechado.md) — a
   marcação manual da DMPL respeita o período fechado (BL-655): INTEGRADA**
   pelo [PR #95](https://github.com/fredabsd-svg/DataLedger/pull/95), squash
   `389aafe`, em 08/10/2026, com os quatro checks verdes em todas as
   execuções do último commit; merge feito pelo arquiteto sob a RC-164.
   Nível 1.
   [Rodada 1](../auditorias/2026-10-08-dl-071-rodada-1.md) **APROVADA COM
   RESSALVAS**; correção única (`f4f2a72`, Haiku);
   [reconferência](../auditorias/2026-10-08-dl-071-reconferencia.md)
   **APROVADA COM RESSALVAS** — ciclo do §3.1 encerrado. O teste proposto na
   R1 da reconferência entrou depois, com o mutante conferido pelo arquiteto.
   Abertos: **BL-656 (alta)** — a reclassificação de conta da DL-065 tem o
   mesmo furo (só olha os meses com movimento; DMPL e DLPA acumulam o
   exercício e o saldo inicial), em etapa própria, com a parte do saldo de
   exercícios anteriores para o Fred; BL-657 (limite aceito: competência sem
   linha não é travada); BL-658 e BL-659 (baixos).
2. **[DL-072](../planos/DL-072-escrituracao-das-nfse-prestadas.md) — Fiscal
   F1, escrituração das NFS-e prestadas — e
   [DL-073](../planos/DL-073-validador-ibscbs.md) — validador de
   conformidade IBS/CBS: INTEGRADAS** pelo
   [PR #96](https://github.com/fredabsd-svg/DataLedger/pull/96), squash
   `8f36cd4`, em 08/10/2026, com os quatro checks verdes; merge feito pelo
   arquiteto sob a RC-164. Ciclo do §3.1:
   [rodada 1](../auditorias/2026-10-08-dl-072-dl-073-rodada-1.md) e
   [reconferência](../auditorias/2026-10-08-dl-072-dl-073-reconferencia.md),
   aprovadas com ressalvas; R1, R2, R4 e R5 corrigidos depois. Abertos:
   BL-660 a BL-666.
3. **[DL-074](../planos/DL-074-receita-e-rbt12-do-simples.md) — receita
   mensal, confirmação e RBT12 do Simples por mercado: INTEGRADA** pelo
   [PR #97](https://github.com/fredabsd-svg/DataLedger/pull/97), squash
   `ebc40a3`, em 08/10/2026, com os quatro checks verdes; merge feito pelo
   arquiteto sob a RC-164. Ciclo do §3.1:
   [rodada 1](../auditorias/2026-10-08-dl-074-rodada-1.md) **REPROVADA** (A1
   bloqueador: RBT12 de empresa nova errado na virada do ano, para menos; A2
   alta: `PATCH` da data de abertura dava 500), correção única e
   [reconferência](../auditorias/2026-10-08-dl-074-reconferencia.md)
   **APROVADA COM RESSALVAS**; R1 a R5 corrigidas depois, com testes que
   derrubam os mutantes apontados. HI-76 conferida e HI-77 **ajustada** pelo
   contador-senior
   ([consulta](../projeto/consultas/2026-10-08-contador-senior-hi76-hi77.md)).
   Abertos: PE-78 (não bloqueia), BL-666, BL-669.
4. **[DL-075](../planos/DL-075-pre-das-do-simples.md) — pré-DAS do Simples:
   INTEGRADA** pelo [PR #98](https://github.com/fredabsd-svg/DataLedger/pull/98),
   squash `05668d4`, em 08/10/2026, com os quatro checks verdes; merge
   autorizado pelo Fred (RC-165). Os exemplos 2, 4 e 5 do Manual do PGDAS-D
   batem centavo a centavo; tabelas idênticas ao Planalto por script. Ciclo
   do §3.1: [rodada 1](../auditorias/2026-10-08-dl-075-rodada-1.md)
   **REPROVADA** (A1 alta: dependência da migração `fiscal 0005`), correção
   única e [reconferência](../auditorias/2026-10-08-dl-075-reconferencia.md)
   **APROVADA COM RESSALVAS**; R1 a R5 corrigidas depois. Abertos: BL-667,
   BL-668, BL-670, PE-78; HI-71 e HI-79 a conciliar com o extrato do
   PGDAS-D.
5. **[DL-076](../planos/DL-076-iss-por-municipio-palmas.md) — ISS por
   município, começando por Palmas: INTEGRADA** pelo
   [PR #99](https://github.com/fredabsd-svg/DataLedger/pull/99), squash
   `6c2baf7`, em 08/10/2026; merge autorizado pelo Fred (RC-168). Os quatro
   checks tiveram execução verde no último commit; duas execuções duplicadas
   foram **canceladas** no meio, sem falha no log, e a causa não foi
   identificada (o workflow não tem `concurrency`). Ciclo do §3.1:
   [rodada 1](../auditorias/2026-10-08-dl-076-rodada-1.md) e
   [reconferência](../auditorias/2026-10-08-dl-076-reconferencia.md),
   aprovadas com ressalvas. A tabela de alíquotas de Palmas não foi achada:
   o escritório cadastra (HI-82). **PE-79 com o Fred.** Abertos: BL-668,
   BL-671, BL-672.
6. **[DL-077](../planos/DL-077-importacao-e-exportacao-contabil-em-txt.md) —
   importar e exportar plano de contas e lançamentos em TXT e Excel (RC-166,
   RC-167).** Três leiautes de TXT (registros da ECD, leiaute do sistema de
   referência e formato próprio) e importação por Excel
   ([consulta](../projeto/consultas/2026-10-08-contador-senior-txt-contabil.md);
   [casas do 6100](../projeto/consultas/2026-10-08-casas-decimais-6100.md)).
   - **Fatia 1 — plano de contas: INTEGRADA** pelo
     [PR #100](https://github.com/fredabsd-svg/DataLedger/pull/100), squash
     `929a79a`, mesclado **pelo Fred** em 08/10/2026, com os quatro checks
     verdes em todas as execuções. Ciclo do §3.1:
     [rodada 1](../auditorias/2026-10-08-dl-077-fatia-1-rodada-1.md) e
     [reconferência](../auditorias/2026-10-08-dl-077-fatia-1-reconferencia.md)
     reprovadas (a reconferência só pelo leitor Excel); pela regra de parada,
     sem terceira rodada — correções aceitas pelos testes do próprio auditor.
     Abertos: BL-673, BL-674 (leitor de planilha próprio), BL-675, PE-81.
   - **Achado de CI:** o job "Lint e testes" tinha limite de 10 min e a suíte
     já leva cerca de 11 min no executor; execuções do evento `pull_request`
     dos PRs #99 e #100 foram **canceladas por tempo**. Limite subido para
     20 min no PR #100; desde então, todas as execuções verdes.
   - **Fatias 2 e 3 — exportar lançamentos e saldos; importar lançamentos
     com área de conferência, de-para e efetivação: INTEGRADAS** pelo
     [PR #101](https://github.com/fredabsd-svg/DataLedger/pull/101), squash
     `b60560b`, em 08/10/2026, com os quatro checks verdes em todas as
     execuções; merge autorizado pelo Fred (RC-169).
     [Rodada 1](../auditorias/2026-10-08-dl-077-fatias-2-3-rodada-1.md):
     **REPROVADA** — A1 (alta: "só os válidos" ignorava erro do arquivo
     inteiro e gravou lançamentos de outra empresa no Diário), A2 a A7
     (byte nulo dava 500; teto não limitava o custo; mais de 200 partidas
     travava a efetivação; exportar e reimportar dobrava o Diário sem aviso;
     histórico fora do Latin-1 impedia exportar o período; soma da
     efetivação parcial). Exportação e conciliação com o balancete,
     atomicidade, imutabilidade e isolamento aprovados. Correção única
     (`6e164da`) e [reconferência](../auditorias/2026-10-08-dl-077-fatias-2-3-reconferencia.md):
     os doze achados fechados, mas **REPROVADA** por R1 (alta: no TXT
     próprio e no Excel, partida com número ilegível sumia e "só os válidos"
     efetivava o lançamento incompleto) e R2 (média: registro ilegível no fim
     do lote do leiaute de referência sumia em silêncio). Regra de parada do
     §3.1: sem terceira rodada — **a efetivação parcial foi suspensa**
     (BL-676; só "tudo ou nada", que estava protegido), R2 vira erro, e o
     aceite é pelos testes do próprio auditor. Feito (`5a84b27`): T-R1 do
     auditor passando nas duas políticas, cada mutante derrubando o seu
     teste, e os fuzzers do auditor com **0 violações** nos quatro leitores
     (inclusive linhas em branco, que o fuzzer original não sorteava).
     HI-92 e BL-677 registrados.
     Suíte completa: 7.091 aprovados, 1 reprovado (ambiente). Teto de 2.000
     lançamentos por arquivo (efetivar 2.000 leva ~21 s; o servidor padrão
     corta em 30 s).

7. **[DL-078](../planos/DL-078-servicos-tomados-e-retencoes.md) — serviços
   tomados, ISS retido pelo cliente tomador e retenções federais: INTEGRADA**
   pelo PR #102 (squash `49eacba`), com os quatro checks verdes em todas as
   execuções do último commit. [Rodada 1](../auditorias/2026-10-08-dl-078-rodada-1.md)
   e [reconferência](../auditorias/2026-10-08-dl-078-reconferencia.md)
   aprovadas com ressalvas; R4 e R5 fechados com os testes do auditor; R2
   declarado na migração. Escrituração das tomadas com natureza, rascunho,
   efetivação, estorno e imutabilidade no banco (`fiscal 0008`); ISS retido a
   recolher de toda tomada com retenção (HI-94); retenções federais pelos
   três relógios, com data de pagamento numa janela e limpável (HI-96,
   HI-98). Abertos: HI-93 a HI-99 e **PE-82 com o Fred**; BL-678, BL-679.

8. **[DL-079](../planos/DL-079-lucro-presumido-irpj-csll.md) — Lucro
   Presumido, IRPJ e CSLL trimestrais com o acréscimo da LC 224: INTEGRADA**
   pelo PR #103 (squash `6eb922e`), com os quatro checks verdes em todas as
   execuções do último commit (RC-171). [Rodada 1](../auditorias/2026-10-09-dl-079-rodada-1.md)
   e [reconferência](../auditorias/2026-10-09-dl-079-reconferencia.md)
   aprovadas com ressalvas; o cálculo bate ao centavo com a implementação
   independente do auditor. Tabelas com fonte, controle do limite da LC 224
   com sobra e os casos I a III, três colunas (sem LC 224, com, parcela),
   retenções confirmadas, medida judicial, quotas e vencimentos; 11 rotas de
   API e 16 telas. Abertos: HI-100 a HI-108, HI-114, HI-115; BL-680, BL-682.
   A PE-83 foi respondida por delegação (RC-172); as mudanças estão na DL-084.

9. **[DL-080](../planos/DL-080-recepcao-de-nfe.md) — recepção de NF-e e
   NFC-e: INTEGRADA** pelo PR #104 (squash `c01b451`), com os quatro checks
   verdes em todas as execuções do último commit (RC-171).
   [Rodada 1](../auditorias/2026-10-09-dl-080-rodada-1.md) reprovada (data
   absurda travava telas); [reconferência](../auditorias/2026-10-09-dl-080-reconferencia.md)
   aprovada com ressalvas. Tabelas próprias para a NF-e; leitura pelo XSD do
   PL 010f com recusas nomeadas; empresa só por emitente e destinatário;
   cancelamento só com retorno 135 ou 155; exceção da chave só nas séries
   890 a 899 (MOC 7.0, Tabela 2-4); telas e API de conferência. Abertos:
   HI-109 a HI-113, HI-116; BL-681, BL-683, BL-684. A PE-84 foi respondida
   por delegação (RC-172); as mudanças do leitor estão no BL-687.

10. **[DL-081](../planos/DL-081-escrituracao-das-nfe-de-saida.md) —
    escrituração das NF-e de saída e da devolução de venda: INTEGRADA** pelo
    PR #105 (squash `2911eb6`), com os quatro checks verdes em todas as
    execuções do último commit (RC-171). [Rodada 1](../auditorias/2026-10-09-dl-081-rodada-1.md)
    reprovada (leitura de itens, Presumido dos trimestres seguintes, itens
    sem gatilho); [reconferência](../auditorias/2026-10-09-dl-081-reconferencia.md)
    aprovada com ressalvas. Tabela oficial de CFOP como dado com fonte;
    itens lidos pelo XSD; natureza por item; receita por item com
    conferência W16; NF-e na receita do Simples e no RBT12; devolução no mês
    da devolução; pré-DAS recusa e Presumido parcial com NF-e. Abertos:
    HI-117 a HI-124; BL-685, BL-686 (resolver antes de subir a versão do
    leitor). A PE-85 foi respondida por delegação (RC-172): os dois bloqueios
    conservadores saem na DL-083.

11. **[DL-082](../planos/DL-082-pre-das-de-comercio-e-industria.md) — pré-DAS
    de comércio e indústria (Anexos I e II): planejada.**
    [Consulta ao contador-senior](../projeto/consultas/2026-10-09-contador-senior-pre-das-comercio.md):
    exemplos 1, 2, 3 e 6 do Manual do PGDAS-D batem ao centavo com as tabelas
    do repositório; um RBT12 para todos os anexos; segregação sem
    redistribuição; devolução por segmento. HI-125 a HI-132; PE-86
    (benefício de ICMS do Tocantins), PE-87 (conciliação real). **Executa
    depois da DL-083.**

12. **Respostas da PE-83, da PE-84 e da PE-85 (RC-172, 09/10/2026):
    registradas.** O Fred delegou as três ao `contador-senior` (Fable). A
    [consulta](../projeto/consultas/2026-10-09-contador-senior-pe83-pe84-pe85.md)
    leu na fonte oficial as Leis 9.430, 9.249, 9.779, 9.093, 14.759 e 10.833,
    a LC 87, o DL 1.598, o MOC 7.0 e as NT 2026.008 e 2026.009. As hipóteses
    afetadas foram atualizadas em [requisitos.md](../projeto/requisitos.md):
    HI-102 a HI-107, HI-109, HI-111, HI-113 e HI-117 a HI-124. Também entraram
    as novas HI-133 a HI-136. A fonte do limite por pessoa jurídica foi
    corrigida: é a Lei 9.430 e a LC 224, e não a Lei 9.779. Os fatos que só a
    carteira do Fred responde estão na **PE-88**, que não bloqueia nada. Três
    destinos:
    - [DL-083](../planos/DL-083-receita-de-nfe-no-presumido.md): receita de
      NF-e no Presumido; os dois bloqueios conservadores saem pela fórmula do
      MOC; combustível em duas naturezas; receita de 2027 bloqueada.
      **Frentes A e B integradas na branch** (`6f86f7f`, `7c25044` com o
      ajuste de integração da sugestão de combustível, `e1a0d67`).
      [Rodada 1](../auditorias/2026-10-09-dl-083-rodada-1.md) **reprovada**:
      - A1 (alta): a devolução de combustível recebida (CFOP 5.66x e
        6.66x) escapa da recusa e deduz a 8%;
      - A2: a reversão da migração 0012 fica impossível depois de um
        estorno;
      - A3: frete ou desconto em item que não é receita;
      - A4: cinco mutantes sobreviventes;
      - A5 a A10: baixos.

      Cálculo do Presumido ao centavo em quatro cenários independentes.
      [Consulta](../projeto/consultas/2026-10-09-contador-senior-frete-lubrificante-devolucao.md)
      sobre A1, A3 e A6, que gerou HI-138 a HI-140. A tabela de NCM vem do
      Portal Único Siscomex. **Correção única em andamento** (Haiku, cópia
      `dl083c` sobre `c66125a`). A5 e A10 foram para o BL-688.
    - [DL-084](../planos/DL-084-rotina-do-presumido.md): rotina do Presumido,
      depois da DL-082.
    - BL-687: mudanças do leitor de NF-e, que dependem do BL-686.

13. **Respostas do Fred à PE-88 (RC-173, 09/10/2026):**
    - há cliente com medida judicial;
    - NFC-e em **alto volume**;
    - há os três clientes de combustível;
    - devoluções também como nota própria de entrada;
    - a grande maioria paga em quotas;
    - o escritório já antecipou DARF por feriado municipal;
    - há muitos clientes do Presumido com NF-e em 2026.

    Consequências:
    - nova [DL-085](../planos/DL-085-escrituracao-de-nfe-em-volume.md), a
      escrituração em lote, porque nota a nota não fecha o mês de um posto;
    - a DL-084 ganha três quotas como padrão, feriados de Palmas e do
      Tocantins com lei lida, padrão de combustível por tipo de cliente e o
      encerramento da medida judicial (BL-680).

    **Ordem de execução:** DL-083 → DL-085 → DL-082 → DL-084.

**Linha de base vigente (09/10/2026, contêiner Linux, Python 3.13.16,
PostgreSQL 16 local, sobre `578ce9e` — conteúdo da `main` em `2911eb6` —,
medida pelo arquiteto numa única invocação, sem a variável dos XSD):**
`pytest` completo **8.558 aprovados, 1 reprovado, 53 pulados**; a reprovação
é a conhecida de ambiente (`test_versao_minima_python.py`, exige Python
3.14). `ruff`, `check` e `makemigrations --check` limpos (569 arquivos). A
suíte leva cerca de 13 min: o job "Lint e testes" tem limite de 20 min. Lição
da DL-075: a suíte **em fatias** esconde interação entre migrações — só vale
a invocação única.

**Também achado em 08/10/2026:** o diagnóstico da DFC fatia 2 levantou, no
texto oficial do CPC 03 (R2), Rev. 24, que a norma **não define "classe"** de
recebimento e pagamento — só dá exemplos (item 14) — e que o item 19(b)(ii)
não é regra de marcação por lançamento. A DFC fatia 2 volta à fila depois do
fiscal ou quando o Fred decidir as classes.

**[DL-070](../planos/DL-070-melhorias-com-equipe-multiagente.md) — melhorias
do repositório com equipe multiagente: INTEGRADA** pelo
[PR #94](https://github.com/fredabsd-svg/DataLedger/pull/94), squash
`76cb92a`, em 08/10/2026, com os quatro checks verdes nas duas execuções do
último commit e merge feito pelo arquiteto por autorização do Fred (RC-162).
Ordem do Fred (RC-160): orquestrador em Opus, desenvolvedores em Haiku em
paralelo, auditor em Sonnet.

O que entrou:
- entradas do `/bootstrap/` e do convite que davam 500 ou gravavam lixo
  (BL-645 a BL-647), oráculo de existência de escritório (BL-651), e a tela do
  primeiro acesso aceitando CNPJ com máscara e alfanumérico como o cadastro
  público (A3);
- consultas por linha eliminadas na lista de empresas e na trilha da API
  (BL-648, BL-649);
- testes que faltavam (BL-600, BL-602, BL-619 — este último provou que o
  defeito já não existia) e comentários corrigidos (BL-575, BL-591).

Nenhuma regra contábil mudou. Dois itens tocam nível 1 do §3.1 (isolamento e
trilha), e o controle foi a auditoria independente.

**Ciclo do §3.1 encerrado:**
[rodada 1](../auditorias/2026-10-08-dl-070-rodada-1.md) **APROVADA COM
RESSALVAS** (A1 a A7, todas baixas), correção única, e
[reconferência](../auditorias/2026-10-08-dl-070-reconferencia.md) **APROVADA
COM RESSALVAS** — A1, A2, A3, A5, A6 e A7 fechados por execução do auditor;
na reconferência o auditor reconheceu que a premissa dele no A6(c) estava
errada e o desenvolvedor, certo. Ficam abertos: BL-652 (enumeração de CNPJ
sem limite de tentativas no `/bootstrap/`, risco aceito por ora), BL-653
(corrida do mesmo usuário criando dois escritórios, preexistente) e BL-654
(parte local do e-mail, decisão do Fred).

**Linha de base medida na DL-070 (08/10/2026, contêiner Linux, Python 3.13.16,
PostgreSQL 16 local, sobre `25fe182`, medida pelo auditor):** `ruff check` e
`ruff format --check` limpos (380 arquivos), `manage.py check` e
`makemigrations --check` sem mudança; `pytest` completo **5.021 aprovados, 1
reprovado, 53 pulados**. A reprovação é a conhecida de ambiente
(`test_versao_minima_python.py`, que exige Python 3.14). Antes da DL-070,
sobre `79ff2e5`: 4.987/1/53. A CI (Python 3.14) do PR #94 ficou verde nos
quatro checks.

**Achado de processo desta etapa:** as cópias isoladas criadas pela
ferramenta de agentes (`isolation: worktree`) partiram de `d5cc6bf`, quatro
commits **atrás** da revisão pedida. Os quatro desenvolvedores pararam sem
editar porque o pedido mandava conferir a base com `git log -1` — **mantenha
essa conferência em todo pedido com worktree**. As cópias foram refeitas à
mão a partir da revisão certa.

**[DL-069](../planos/DL-069-travas-no-banco.md) — travas no banco.** Origem:
ordem do Fred, *"Próxima etapa"* (RC-158). A interpretação é do arquiteto: é
a etapa que a análise do dia recomendou depois da DL-068.

**Fatias:**
1. **Livro-caixa imutável no PostgreSQL — INTEGRADA** pelo
   [PR #92](https://github.com/fredabsd-svg/DataLedger/pull/92), merge
   `a610c70` feito em 07/10/2026. Padrão da `0013` da contabilidade. A
   [auditoria](../auditorias/2026-10-07-dl-069-fatia-1-rodada-1.md) saiu
   **APROVADA COM RESSALVAS**, sem achado grave: nenhum caminho legítimo foi
   recusado, inclusive tela e API de ponta a ponta. A correção única tratou
   A1 (texto, BL-644), A2 (8 testes; a mutação que sobrevivia agora morre) e
   A3 (limite declarado). A
   [reconferência](../auditorias/2026-10-07-dl-069-fatia-1-reconferencia.md)
   saiu **APROVADA COM RESSALVAS** (R1 e R2 corrigidas sem terceira rodada);
   o ciclo do §3.1 está encerrado.
2. **Período encerrado recusa INSERT no banco — INTEGRADA** pelo PR #93,
   merge `79ff2e5` em 07/10/2026 (conferido no Git em 08/10/2026; até então
   este arquivo a dizia "em validação"). O commit cita a correção dos achados
   A1, R1 e R2 da auditoria da fatia 2, mas **o relatório dessa auditoria não
   está em `docs/auditorias/`** — lacuna de registro. Critérios no
   [plano](../planos/DL-069-travas-no-banco.md). A competência é achada pela
   data; a entrega da competência não se desfaz (RC-101); o ponto de risco —
   refazer no gatilho a leitura protegida contra corrida que o serviço faz
   (BL-456) — está resolvido por `FOR SHARE` na contabilidade e pelo lock
   consultivo do mês no livro-caixa, com a decisão e o limite restante
   documentados nas migrações 0023 (contabilidade) e 0012 (livro-caixa).
3. **Trilha imutável no banco.** A PE-76 foi respondida pelo Fred em
   07/10/2026 (RC-159): a trilha é **preservada** mesmo quando o escritório é
   excluído, inclusive por pedido de LGPD. A fatia continua bloqueada pela
   PE-77 (prazo de retenção), com o Fred.

A linha de base vigente para não regressão é a de 08/10/2026, acima, já com
a fatia 2 integrada e com os gatilhos rodando em PostgreSQL local. As medidas
anteriores (07/10, Windows/SQLite) estão no histórico do Git deste arquivo.

**DL-068 — prontidão para implantação: integrada** pelo
[PR #91](https://github.com/fredabsd-svg/DataLedger/pull/91), squash
`7c23894`. O Fred fez o merge em 07/10/2026, com os quatro checks verdes.
Entregou:
- Django 6.1.2;
- limite de tentativas no login do admin;
- `.dockerignore` (e `.gitignore`) com segredos em qualquer pasta e caixa;
- `DJANGO_AMBIENTE` (BL-82, DE-100);
- recusa de proxies que cobrem a internet inteira (BL-577).

[Rodada 1](../auditorias/2026-10-07-dl-068-rodada-1.md) e
[reconferência](../auditorias/2026-10-07-dl-068-reconferencia.md) saíram
aprovadas com ressalvas. Ficaram com o Fred:
- BL-642 (piso de rede, HI-51);
- backup e restauração (PE-07);
- residência do dado (PE-25);
- os achados baixos BL-635 a BL-641.

**Em 06/10/2026: a fatia 1 da [DL-066](../planos/DL-066-dfc.md) está
FECHADA** — a etapa 2 desta data completou o que o PR #89 deixou em aberto,
na branch `feat/dl-066-portas-e-indireto`, pelo
[PR #90](https://github.com/fredabsd-svg/DataLedger/pull/90):

- **Porta de classificação** `classificar_conta_na_dfc` (os três campos da
  conta, `select_for_update`, trilha antes/depois na mesma transação) e a
  **trava da DL-065 estendida** aos três campos em `Conta.clean()` (recusa
  com movimento em competência encerrada/entregue, primeira marcação livre,
  mensagem bifurcada por `entregue`);
- **Método indireto** (`_apurar_operacional_indireto`): lucro do motor da DRE
  + ajustes do item 20 (20(a) variação patrimonial operacional, 20(b) item
  sem caixa, 20(c) resultado de outra atividade), zeramento excluído, e a
  identidade com o direto virando a pendência `indireto_nao_fecha` quando não
  fecha;
- **API** GET `empresas/<id>/dfc/<ano>/<mes>/` e PATCH
  `contas/<id>/classificacao-dfc/` (padrão D8, espelho das irmãs);
- **Telas** `dfc.html` (classe Demonstração: direto resumido + indireto +
  conciliação do item 45; veto sem documento impresso; sem "por ação") e
  `conta_classificacao_dfc.html`, mais menu, plano de contas, universo de
  telas e o piso do instrumento de identificação;
- **BL-629 fechada** — o inventário de pendências da DFC deixou de ser
  tautológico.

**Ciclo de auditoria (nível 1, §3.1) — encerrado no veredito REPROVADO da
reconferência, com as correções finais entrando sem terceira rodada**, como
na DL-065: a [rodada 1](../auditorias/2026-10-06-dl-066-etapa-2-auditoria.md)
achou **1 GRAVE** (o teste do PATCH parcial era cego — a mutação destrutiva
sobrevivia e derrubava zero testes), 4 MÉDIO e 2 BAIXO; a correção única
(`c59f809`) refez o teste com cenário real e matou as mutações de permissão e
de descarte mudo; a
[reconferência](../auditorias/2026-10-06-dl-066-etapa-2-reconferencia.md)
fechou **6 de 7** e apontou **N1** — o teste de corrida sem
`django_db(transaction=True)` reprovaria na CI sem medir a trava; N1 e a
observação menor da A2 (a pendência não dizia qual marcação manter) foram
corrigidos em `e889b72`. A prova de corrida real é da **CI** (PostgreSQL):
em SQLite ela reprova pela classe de ambiente, como o R4 da DRE.

**Limites declarados nesta entrega:** a medição de impressão no navegador
real fica para o job de CI (Chromium não roda nesta máquina); o
`ContaSerializer` não grava os três campos no POST/PUT — a chave é **recusada
por nome** (BL-196), e a extensão da decisão D2 da DL-063 ficou como
**BL-631**, decisão do Fred; **BL-630** (escopo da pendência
`conta_com_dois_papeis`) segue com o Fred.

**O número da DFC sai do lançamento, não de soma de ajustes.** Caixa contra
uma conta de fora da lista de caixa é um fluxo, classificado pela atividade
dessa conta; movimento entre duas contas de caixa **não** é fluxo (item 9, e é
a resposta ao risco que o mapa de paridade apontava); e a soma das três
atividades é a variação do caixa **por construção**. O método indireto passa a
ser a apresentação do mesmo número, com os ajustes do item 20 derivados — o
que faz da conciliação do item 45 uma identidade que precisa valer, e vira
**veto** quando não vale, em vez de número errado publicado.

**O item 20A é o que amarra os dois métodos que o Fred pediu**, e é bom que
tenha vindo da norma e não da preferência: no Brasil a conciliação entre o
lucro líquido e o fluxo das operações é **obrigatória para quem usa o método
direto** (e a nota NE3 do próprio pronunciamento diz que essa exigência não
existe no IAS 7). Ou seja, "os dois" não é escopo dobrado — é a norma
exigindo que o direto traga a conciliação do indireto.

**Lacuna de fonte fechada em 06/10/2026:** a obrigatoriedade vem da Lei
6.404/76, art. 176, IV, com o **§ 6º isentando a companhia fechada com
patrimônio líquido abaixo de R$ 2.000.000,00** — texto obtido em duas fontes
oficiais concordantes (Câmara dos Deputados, PDF da norma atualizada, e o
próprio Planalto por download direto) e registrado no
[plano](../planos/DL-066-dfc.md). As quatro perguntas do plano foram
respondidas por pesquisa e decididas (DE-098 e DE-099): equivalente de caixa
é campo por conta (critério do item 7 no `help_text`), e a DFC é **oferecida**
pela empresa, não exigida nem impedida pelo produto.

**Leva da DL-065 concluída e integrada.** [DL-065](../planos/DL-065-reclassificacao-em-periodo-fechado.md)
— BL-550, a trava de reclassificação em competência fechada — escolhida pelo
Fred como primeiro item. O recorte foi decidido **depois de medida a colisão
com a DE-086**: a trava vale para a **DLPA e a DMPL**, e a **DRE continua
livre** — a DE-086, de 26/09/2026, foi mantida. O caminho "classificação por
vigência", que o backlog aceitava como alternativa, foi **descartado**: ele
exigiria versionar as quatro classificações da conta e recontar demonstrações
já emitidas, que é trabalho de Onda 2.

O que a meditura encontrou antes de qualquer linha de código: nenhuma das
duas classificação de demonstração anual consulta a competência antes de
gravar, e o `ContaAdmin` grava os quatro campos **por fora** dos três
serviços — uma trava colocada só nos serviços deixaria o admin funcionando
como estava. Por isso a regra mora em `Conta.clean()`, que é o ponto de
passagem de todo caminho validado, e a tradução para **409** acontece nos
serviços, por um `code` de erro que só eles conhecem.

**21 testes novos na primeira entrega, 30 depois das duas correções** — todos
executados em PostgreSQL 16.15 (critérios 1 a 11 do plano, mais quatro
limites: competência do mês seguinte, a mais recente quando há duas, período
reaberto e conta sem movimento no período fechado). A suíte de
`apps/contabilidade` deu **1.839 aprovados e os mesmos 8 reprovados de antes
da mudança** — nenhuma regressão.

**[Auditoria independente](../auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md):
APROVADA COM RESSALVAS, nenhum bloqueador**, com os treze critérios verificados
por execução do próprio auditor e **mutação em memória** — sem a guarda, 13
dos 21 testes caem. Três achados médios, corrigidos numa **rodada única**
(§3.1):

- **A1 — a guarda lia o movimento pela FK `competencia`, e as apurações leem
  por `data`.** O auditor mediu `competencia_id` como **anulável** no banco
  (a restrição F6 da DL-016 cobre `empresa_id`), então um lançamento legado
  sem competência gravada entrava na DLPA do período encerrado sem a trava o
  ver. A guarda passou a filtrar por data, com a mesma aritmética de
  calendário das apurações. *Princípio: guarda que filtra por critério
  diferente do que a apuração filtra é guarda que pode ser contornada.*
- **A2 — corrida entre reclassificar e fechar o mês**, demonstrada com duas
  threads: o fechamento commita entre a leitura do estado e o commit da
  reclassificação, e o período terminava encerrado com a classificação trocada.
  A trava agora **reusa o primitivo do módulo**,
  `_travar_competencia_em_modo_compartilhado` (`FOR SHARE`), que impede o
  fechamento de passar por cima sem impedir o fechamento. No caminho, ficou
  registrado que o Django **não expõe** `FOR SHARE` em `QuerySet` — quase
  escrevi uma checagem de feature que não existe.
- **A3 — a mensagem mandava "reabra a competência"** para competência
  **entregue**, que `reabrir_competencia` recusa sempre (RC-101): instrução
  falsa ao contador, a mesma classe do BL-142. Bifurcada por `entregue`, com
  teste de regressão que proíbe a frase.

**A5 corrigiu o próprio plano:** ele afirmava que conta sem movimento não
paga consulta, e o auditor mediu que paga — o texto foi corrigido e o custo
real ficou registrado. **A6** (o script de medição grava a coluna da DMPL
sem a guarda) foi **aceito como limite** e registrado no backlog como
**BL-628**. **A7** — faltavam a tela da DMPL e o admin da coluna da DMPL —
foi coberto.

⚠️ **[Reconferência: REPROVADA](../auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md).**
A1, A3, A4, A6 e A7 fecharam; **A2 não** — a corrida fecha (o auditor mediu
8 de 8 com o fechamento vencendo e o vazamento da rodada 1 não reproduz),
mas a tradução prometida do `lock_timeout` não acontecia. E a correção
**introduziu dois defeitos**, um deles médio: **N1**, em que o `FOR SHARE`
estourado aborta a transação e o `full_clean` do Django continua acumulando
erro e consultando, de modo que a recusa virava **500 na porta de nível 1** —
a mesma patologia que o docstring de BL-470 diz ter eliminado; e **N2**, em
que a troca de uma consulta por um laço levou a guarda a **507 consultas e
393 ms** com 480 períodos fechados, com o `FOR SHARE` segurado durante todo
esse tempo, bloqueando o fechamento junto. Mais **N3** (baixa), em que
estado fora do enum virava `ValueError` cru.

**As três foram corrigidas sem terceira rodada de auditoria** — e é preciso
dizer por quê: o §3.1 proíbe comprar outra rodada, e ela existe para parar
quem tenta provar uma frase que promete mais do que o instrumento aguenta, não
para deixar passar um 500 conhecido em porta de nível 1 e uma regressão de 1
para 507 consultas. O ciclo fica **encerrado no veredito REPROVADO**. N1 virou
um **savepoint** em torno da tentativa de lock, para o `ValidationError`
chegar inteiro ao acumulador; N2 virou a **interseção de conjuntos** que a
pergunta sempre foi — quantas consultas são constantes, não crescem com o
histórico; N3 ganhou rótulo com reserva. Cada uma com teste de regressão
próprio. **O que fica de decisão do Fred:** essas três correções não passaram
por auditoria independente, e a forma honesta de tê-las seria um papel
diferente do mesmo §3.1, não uma terceira rodada deste ciclo.

**A verificação dirigida dos achados N1, N2 e N3 da DL-065 saiu
[APROVADA COM RESSALVAS](../auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md).**
Sob `FOR UPDATE` concorrente com `lock_timeout` de 200 ms, a **API responde
409** nas duas demonstrações (era a porta que a reconferência deixara de
fora), a tela 200 com recusa e valor intacto, o `ModelForm` do admin recusa
sem degradar a validação de constraint, e a transação volta a servir depois
do savepoint. O custo ficou **constante em 8 consultas** de 0 a 480 períodos,
contra 486 medidos antes — e a ressalva de que ainda crescia no **segundo**
eixo (meses com movimento, não períodos fechados) foi corrigida em seguida,
com teste próprio, depois de eu escrever um teste que media **152 consultas
com 37 meses** por buscar a FK `empresa` a cada trava.

**Auditoria da DL-066, fatia 1 (DFC): rodada 1 APROVADA COM RESSALVAS,
correção, e reconferência rodada 2 APROVADA COM RESSALVAS — os sete achados
FECHADOS.** A execução que vale é a da **CI**: **4.688 aprovados, 53 pulados,
zero reprovados**, no commit `7c0eae7`.

⚠️ **Os dois achados graves da rodada 1 eram meus, e um deles tinha por base a
própria premissa do desenho.** O **A1**: eu filtrava as contrapartes sem
classificação **antes** de avaliar, e uma contraparte classificada sozinha
decidia o lançamento inteiro — o auditor reproduziu **número errado com
`pode_emitir=True` e zero pendências**, porque a identidade do item 45
continua fechando. Ou seja: a identidade, que era a rede de segurança do
desenho, **não** pegava o defeito. O **A2**: `atividades[chave] += fluxo` lê
antes de escrever em Python, então atividade fora do enum subia `KeyError`
cru — 500 sem nomear nada, contra o padrão do módulo (BL-476/BL-493) de
nomear valor ilegível.

⚠️ **A reconferência encontrou três coisas minhas novas, e uma delas é sobre
honestidade do registro.** O **N1** (média): a caminhada de árvore que
escrevi para a deduplicação era a **única** do módulo **sem guarda de
ciclo**, e as outras quatro estão defendidas exatamente por isso, com
justificativa escrita. Ciclo alcançável por ORM direto seria **travamento**
de worker. O **N2** (média): a guarda de modelo que escrevi só olhava o pai
**direto**, enquanto a mensagem dizia "uma conta acima dela" e o serviço sobe
a cadeia inteira — as "duas metades da mesma defesa" mediam coisas diferentes.
E o **N3** (média): **o plano e o PR afirmavam números que nenhuma execução
havia medido** — "em PostgreSQL 16.15 na porta 5433" e "8 reprovados de
ambiente", quando o cluster local está bloqueado por política de Controle de
Aplicativo e esses 8 **não são reproduzíveis** aqui. Número que ninguém mediu
é tão grave quanto número medido errado. Os três foram corrigidos nesta
entrega, e o registro passa a citar a CI pelo identificador do run.

⚠️ **Sobre o §3.1 e o que eu fiz:** a regra proíbe uma **terceira rodada de
auditoria**, e não proíbe corrigir defeito conhecido. Corrigir um travamento e
uma afirmação sem medição no registro não é comprar rodada — é terminar o
trabalho. O que **não** houve, e não vai haver, é nova auditoria para avaliar
estas correções: a verificação delas é da CI e dos testes de regressão, e o
parecer do ciclo continua sendo o da rodada 2.

⚠️ **Achado de ambiente que mudou a forma de verificar nesta máquina:** o
`DATABASE_URL` do `.env` apontava para **SQLite**, e o cluster do PostgreSQL
16 estava desligado. Isso produzia **64 reprovações falsas** só em
`apps/contabilidade` — número que, lido sem verificação, pareceria regressão.
O cluster **PostgreSQL 16.15** foi criado em
`C:\Users\conta\AppData\Local\PostgreSQL\dataledger`, porta **5433**, e é
ele que produz todas as evidências desta seção. **A `.env` do repositório não
foi alterada.** Com o motor certo, a linha de base honesta é
**8 reprovados** (1 de constraint de banco e 7 de Chromium/timeout de thread,
todos de ambiente), e é ela que vale como comparação.

🔴 **O cluster local voltou a ficar indisponível, e agora por política da
máquina, não por configuração.** Em 05/10/2026, no meio da auditoria da
fatia 1 da DL-066, o `postmaster` caiu e **não voltou**: uma **política de
Controle de Aplicativo do Windows passou a bloquear a execução do
`postgres.exe`** (*"Este comando não pode ser executado devido ao erro: uma
política de Controle de Aplicativo bloqueou este arquivo"*). Nem `pg_ctl` nem
o binário direto sobem; o `postmaster.pid` obsoleto que sobrou era sintoma, e
removê-lo não resolveu. **Não há como contornar isso, e não deve haver.**

**Consequência para a verificação, e ela é a mesma que o projeto já tinha
antes:** a **CI é a evidência que vale para merge** — Python 3.14 e
PostgreSQL 16. Rodada local que dependa do cluster está **Bloqueado**, com o
motivo objetivo acima, e o número dela não entra em relatório nenhum. O
`.env` continua apontando para SQLite e **não foi alterado**.

⚠️ **O sintoma de banco morto tem forma própria, e ela engana:** com o
cluster fora, o Django avisa que *"unable to create a connection to the
'postgres' database and will use the first PostgreSQL database instead"* e
cada teste passa a demorar segundos. A rodada de `apps/core` medida com ele
assim deu **14 reprovados e 100 erros** em 573 s — número que, sem a causa,
pareceria regressão séria. Nenhum deles foi usado para afirmar nada.

**Antes de continuar a leva, uma pendência de repositório:** o PR #82
(DL-063) foi mesclado na branch intermediária e **não chegou à `main`**.
Recuperado pelo **PR #84**, aberto a partir da `main` com a `base` reapontada
para o destino real. Na integração do **PR #83** (DL-064, documentos
defasados), a `main` foi incorporada à branch de trabalho por merge, sem
reescrever o histórico. O conflito de acréscimos em `backlog.md` foi resolvido
preservando os registros da DL-062, DL-064 e DL-065; este estado mantém também
os registros posteriores da DL-063, DL-066 e DL-067.

**Leva de 30/09 a 01/10/2026 concluída: DL-052 a DL-060 integradas**
(PR #66 a #74). Desenvolvidas em até 4 cópias isoladas em paralelo (RC-149)
e integradas **uma por vez** na branch `claude/zealous-goldberg-jr5ggu` →
`main`, cada uma com auditoria aprovada e os quatro checks verdes (RC-150).

**Em andamento: DL-061 — DMPL** (CTB-14 da DL-048), escolhida pelo Fred em
01/10/2026. Linha automática pela contrapartida, como na DLPA (RC-151); manual
do sistema de referência lido (p. 122, 192–194, 616–622, 773–774). Fatia 1
integrada pelo **PR #76** (auditoria rodada 1 reprovou, rodada única de
correção `40e47f5`, reconferência aprovada com ressalvas BL-622 a BL-626; merge
autorizado pelo Fred, RC-154). **Etapa 2 concluída em 02/10/2026** — a etapa
curta prevista depois da fatia 1, na branch `feat/dl-061-ressalvas`: coluna de
dividendo adicional proposto (RC-153, BL-603), veto dos lançamentos com eventos
opostos na mesma coluna (RC-155, BL-623) e texto verdadeiro do veto (M3,
BL-624). [Auditoria independente e
reconferência](../auditorias/2026-10-02-dl-061-etapa-2-auditoria-e-reconferencia.md):
rodada única com correção, **APROVADA**. **Integrada pelo PR #77** (squash
`5a999b5`, os quatro checks verdes, merge autorizado pelo Fred — RC-156).
**Fatia 2 (BL-605) entregue em 03/10/2026** — marcação manual por lançamento
para as exceções e API da DMPL, em duas fatias internas: **servidor** (modelo
`MarcacaoDmpl` fora do livro, contrato por efeito de coluna, marcação só quando
a regra não decide, API no padrão da D8 — auditado com ciclo do §3.1 encerrado,
[relatório](../auditorias/2026-10-03-dl-061-fatia-2-auditoria-e-reconferencia.md))
e **tela** (guia "DMPL" do lançamento; os vetos da DMPL apontam para ela).
**Integrada pelo PR #79** (squash `1a0bdc9`, os quatro checks verdes, merge
feito pelo Fred em 04/10/2026). Pontos abertos: BL-606, BL-607, BL-622, BL-625, **BL-627**
(residual da propriedade de eventos opostos no capital — validação do Fred) e
a validação contábil **BL-626**. HI-50 confirmada pelo Fred (RC-152): alíneas
"c" e "d" revogadas. **BL-604 fechado pela DL-062** (abaixo).

**Concluída e integrada (PR #81, squash `46d80a1`): DL-062 — o sinal da conta-RAIZ retificadora no Balanço**
(BL-604), escolhida por ser o ponto aberto **de nível 1** da leva: é o único
em que o produto entrega documento errado ao cliente. Diagnóstico medido em
04/10/2026, antes da correção: a retificadora de PL cadastrada na raiz do
plano era **somada** pelo Balanço em vez de subtraída — PL publicado em
117.000,00 quando o correto é 113.000,00, equação `ativo = passivo + PL` em
−4.000,00, e `avaliar_emissao_do_balanco` devolvendo **`pode_emitir = True`**:
o Balanço saía errado e nada impedia. A DMPL era a única que acusava, porque
recalcula por conta. A correção leva ao total do Balanço a MESMA normalização
de sinal que o módulo já aplicava à soma por classificação (BL-496) e que a
DRE aplica ao resíduo por tipo — a contribuição de uma raiz entra com a
natureza **natural** do seu `TipoConta`. Medido que **não era caso do PL e sim
uma classe**: a mesma falha atingia RAIZ devedora de RECEITA e RAIZ credora
de DESPESA (equação em −200,00 com as três), então a regra cobre os cinco
tipos. A "recusa do cadastro", que o backlog aceitava como alternativa, foi
avaliada e deixada de fora por medida: não corrige dado já gravado, colide
com o RC-80 e precisaria da regra em três portas. As raízes assim tratadas
passam a ser **declaradas** na lista informativa `contas_retificadoras_rais`
(avisa, não veta — depois da correção o número está certo). **Ciclo do §3.1
encerrado:** [auditoria
independente](../auditorias/2026-10-04-dl-062-auditoria.md) **APROVADA COM
RESSALVAS** (os 9 critérios de aceite SEDE, zero regressão, 8 achados de tela
e documento), **correção única** e [reconferência](../auditorias/2026-10-04-dl-062-reconferencia.md)
**APROVADA** com os oito achados fechados e sem terceira rodada. **PR #81
integrado com os quatro checks verdes** em PostgreSQL 16. A CI foi o que achou o
que o SQLite local não via: o teste do BL-516 exigia o Balanço **vetado** por
um resíduo de 200,00 que **era o próprio defeito** — a "(-) PDD" cadastrada
como raiz inflava o Ativo, e o resíduo aritmético era a única rede que pegava
a conta.

**Concluída e integrada (PR #84, squash `c32cfe6`): DL-063 — fecha a leva da DL-061** (BL-606, BL-607 e BL-625),
combinada pelo Fred em 04/10/2026 e com a decisão de que a coluna da DMPL
passasse a ser aceita **pela API como já era pela DRE e pela DLPA** — a
assimetria de ficar gravável só pela web não era desejada. O campo existia no
modelo e era lido pela apuração, mas nenhuma das duas portas de cadastro o
aceitava: quem integrava por API **não tinha porta nenhuma**, e a recusa por
contrato nem nomeava o campo. A dica da divergência de fechamento, que era um
dicionário estático, passou a apontar a causa que a apuração realmente
encontrou (conta de PL com saldo e sem coluna) em vez de mandar conferir a
classificação; **os dois lados têm teste de tela**, porque um teste só do caso
"tem causa" passaria mesmo com a genérica nunca aparecendo. O teste do
snapshot `REPEATABLE READ` da DMPL foi entregue, mas **não roda localmente**:
exige PostgreSQL 16, e o `SET TRANSACTION ISOLATION LEVEL` não existe no
SQLite — a prova dele é a CI. ⚠️ **O que aconteceu com o PR #82, medido em
05/10/2026:** ele foi mesclado na branch **intermediária**
`fix/dl-062-sinal-da-raiz-retificadora` — que já tinha sido integrada — e
**não na `main`**. O GitHub o reporta como `MERGED` e o conteúdo está a um
`git merge-base --is-ancestor` de distância da `main`: é a segunda ocorrência
do modo de falha que o [AGENTS.md](../../AGENTS.md) §6 já descreve — *mesclar
direto na branch intermediária faz o conteúdo integrado não chegar à branch
de destino, mesmo aparecendo como mesclado*. O delta real contra a `main`
era de **1.502 linhas**, das quais 909 são de teste, 279 o plano e 119 a
auditoria; o código são 96 linhas em `serializers.py`, 57 em `views_web.py`
e 8 em `views.py`. Verificado por execução nesta máquina, em **PostgreSQL
16.15** — o cluster local estava desligado e o `.env` apontava para SQLite, o
que produzia 64 falhas falsas só na contabilidade: a branch da DL-063 rodou
`apps/contabilidade` + `apps/core` com **2.596 aprovados e 21 reprovados**, e
os **21 são idênticos aos da `main`** (13 de permissão POSIX/umask, que não
existem no Windows, e 8 de Chromium e de timeout de thread).
**Nenhuma regressão introduzida.** A recuperação vem por este PR, com a
`base` reapontada para a `main`, como manda a mesma regra do AGENTS.md.

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

1. **DL-066, fatia 2 — o método direto da DFC**: recebimentos/pagamentos
   brutos por atividade (item 21), a marcação manual por lançamento
   (`MarcacaoDfc`, itens 12 e 19(b)(ii)) que substitui o veto interino do
   item 12, e o item 20A como bloco próprio. Nível 1.
2. **DL-016 F3** (encerramento de competência) — o plano ficou numa branch que
   não existe mais; ver *Estado do repositório*.
3. **DL-027 fatias C e D** — logotipo e pré-visualização; PE-48, PE-50,
   PE-51 e PE-52 abertas.
4. **Módulo fiscal — [DL-067](../planos/DL-067-plano-do-modulo-fiscal.md).**
   Plano versionado em 05/10/2026 e conciliado com a
   [paridade fiscal](../projeto/paridade/fiscal.md): ela diz o quê, ele diz
   quando e o que mudou com a reforma tributária. Nada implementado. Sete
   divergências esperam o Fred, e a primeira é a ordem de prioridade: a RFB
   apresenta a primeira apuração assistida da CBS até 15/02/2027. Primeira
   fatia candidata: o validador de conformidade IBS/CBS sobre as NFS-e que o
   sistema já recebe (PE-39).

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
- Branches remotas, medidas em 07/10/2026 com `git branch -r`: só a `main` e
  a branch de sessão `ccr-9e799dfb-48okf5`. As seis branches antigas listadas
  aqui até 06/10 (cinco superadas e `claude/dl-016-f3-encerramento-competencia`)
  **não existem mais no remoto**. Consequência medida: o plano da DL-016 F3,
  que só existia nesta última, **não está na `main` nem em branch remota
  nenhuma**. Se não houver cópia na máquina do Fred, será refeito quando a F3
  for priorizada.
- Equipe de agentes: papéis, permissões e limitações em
  [equipe.md](equipe.md). Nesta plataforma os papéis rodam como **subagentes**,
  não como integrantes de equipe com lista compartilhada de tarefas.

## Ambiente de verificação

Sessão de 30/09/2026: contêiner Linux do Claude Code na web, Python 3.13.12 em
`.venv`, PostgreSQL 16 local iniciado pelo gancho de sessão, sem `pwsh` e sem
Docker. A CI usa Python 3.14 e PostgreSQL 16 — é a evidência que vale para
merge. Agentes em paralelo usam **banco de teste próprio** (nome do banco
trocado no `DATABASE_URL`).
