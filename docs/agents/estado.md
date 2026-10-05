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
| [DL-066](../planos/DL-066-dfc.md) | DFC — Demonstração dos Fluxos de Caixa, direto e indireto (CTB-15 da DL-048) | Situação em **[Próximo passo](#próximo-passo)** |
| [DL-067](../planos/DL-067-plano-do-modulo-fiscal.md) | Plano do módulo fiscal de out/2026 a 2028, com a reforma tributária, conciliado com a paridade fiscal | Planejada |
| [DL-057](../planos/DL-057-ip-real-na-trilha.md) | IP real na trilha atrás de proxy (BL-553) | Integrada (PR #68) — auditoria aprovada com ressalvas; BL-577 obrigatória antes da implantação |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa. A F3 (encerramento de
competência) tem só o plano, na branch `claude/dl-016-f3-encerramento-competencia`,
não integrada — por isso a DL-016 aponta para o Próximo passo.

## Próximo passo

**AGORA, em 05/10/2026: [DL-066](../planos/DL-066-dfc.md) — a DFC, etapa
CTB-15 da DL-048**, o último item da Onda 1 depois da DLPA (CTB-13) e da DMPL
(CTB-14). O plano está escrito e revisado contra o texto integral do
[CPC 03 (R2)](https://www.normasbrasil.com.br/norma/?id=306227), item a item.

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

⚠️ **Lacuna declarada, e ela é de fonte:** a obrigatoriedade vem da
Lei 6.404/76, art. 176, IV, com a **§ 6 isentando a companhia fechada com
patrimônio líquido abaixo de R$ 2.000.000,00** — e o texto compilado no
Planalto **não foi obtido** neste ambiente. O plano traz quatro perguntas
com recomendação para o Fred, das quais duas mudam o que o produto exige:
o que conta como **equivalente de caixa** (item 7, três meses ou menos) e se
a DFC deve ser exigida da empresa ou apenas oferecida.

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

**31 testes da demanda; `apps/contabilidade` com 1.857 aprovados e os mesmos
8 reprovados** de antes da mudança. (O 1.839 que este arquivo trazia era o de
antes do merge da DL-063, que entrou no meio da verificação; a **verificação
dirigida** mediu 1.856 e a medição de hoje, já com o teste do segundo eixo do
custo, dá 1.857. Um nono reprovado apareceu numa rodada e **não se
reproduziu**: era o PostgreSQL local caindo, não o código.)

**A verificação dirigida dos achados N1, N2 e N3 saiu
[APROVADA COM RESSALVAS](../auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md).**
As três correções fazem o que prometem, medido: sob `FOR UPDATE` concorrente
com `lock_timeout` de 200 ms, a **API responde 409** nas duas demonstrações
(era a porta que a reconferência deixara de fora), a tela 200 com recusa e
valor intacto, o `ModelForm` do admin recusa sem degradar a validação de
constraint, e a transação volta a servir depois do savepoint. O custo ficou
**constante em 8 consultas** de 0 a 480 períodos — contra 486 medidos antes.

⚠️ **Mas a ressalva de custo era séria, e eu a tratei como defeito.** A
primeira correção do N2 trocou o eixo do crescimento sem eliminá-lo: ela
iterava os **meses com movimento** perguntando se cada um estava aberto, e a
verificação mediu 39 consultas com 36 meses — que é justamente a empresa real,
já que quase todo mês tem movimento. Pior: cada trava buscava a FK `empresa`
da competência, que não vem em cache, e o teste que escrevi chegou a medir
**152 consultas com 37 meses**. As duas causes foram corrigidas — itera-se o
lado pequeno (as abertas da empresa, uma ou duas) e a empresa vem da conta —
e o segundo eixo ganhou **teste próprio**, porque o teste anterior só pegava
o primeiro.

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

**Em andamento: DL-062 — o sinal da conta-RAIZ retificadora no Balanço**
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
aberto com os quatro checks verdes** em PostgreSQL 16. A CI foi o que achou o
que o SQLite local não via: o teste do BL-516 exigia o Balanço **vetado** por
um resíduo de 200,00 que **era o próprio defeito** — a "(-) PDD" cadastrada
como raiz inflava o Ativo, e o resíduo aritmético era a única rede que pegava
a conta.

**Em andamento: DL-063 — fecha a leva da DL-061** (BL-606, BL-607 e BL-625),
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
5. **Módulo fiscal — [DL-067](../planos/DL-067-plano-do-modulo-fiscal.md).**
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
