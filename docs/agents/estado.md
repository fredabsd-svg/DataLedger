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
| [DL-048](../planos/DL-048-contabilidade-anual-demonstracoes.md) | Contabilidade anual: estrutura de demonstração ligada à conta, com DLPA, DMPL, DFC, DRA e DVA (CTB-12 a CTB-17) | **Fatia CTB-12 + CTB-13 (a DLPA) integrada pelo PR #59** — com auditoria reprovada e achados corrigidos; CTB-14 a CTB-17 em **[Próximo passo](#próximo-passo)** |
| [DL-049](../planos/DL-049-home-por-modulo.md) | Página inicial por módulo, filtros persistentes e fila operacional multiempresa | Situação em **[Próximo passo](#próximo-passo)** |

A DL-016 foi entregue em fatias: F1 (trava de competência) e F2 pelo PR #31,
F5 (backfill) pelo PR #33, F6 (restrição `NOT NULL`) pelo PR #34 e a tela do
fechamento como DL-031. Rastreabilidade: DL-028 a DL-034 entraram juntas pelo
merge do PR #38, sem commit individual por etapa.

## Próximo passo

**DL-049 — Home por módulo (30/09/2026). Estado da entrega no
[PR #63](https://github.com/fredabsd-svg/DataLedger/pull/63): em revisão
enquanto aberto; integrada após o merge confirmado nesse PR.** Demanda direta
do Fred para aplicar a especificação, comparar variantes, revisar e mesclar.
Escolha de interface autorizada sem nova pergunta. Contábil, recepção Fiscal
e Livro-caixa possuem consulta operacional; módulos futuros permanecem
identificados como indisponíveis. Sem migração ou transmissão.
Plano: [DL-049](../planos/DL-049-home-por-modulo.md).
Roteiro de navegador aprovado com dados fictícios: filtros, lista por indicador,
carteira sem JavaScript, permissão e larguras de 1.440, 1.280 e 390 px. A
primeira linha crítica ficou inteira até 898,16 px no cenário 1.440 × 900.
Telefone físico, leitor de tela e teste com operadores permanecem não executados.
Na revisão local `9f9c2a5`, a suíte PostgreSQL registrou **3.573 aprovados,
19 pulados e 2 avisos**. A [auditoria independente](../auditorias/2026-09-30-dl-049-rodada-1.md)
reprovou três comportamentos: Fiscal sem empresas escondia ocorrências;
retorno a um escritório perdia filtros; listas sem fonte aceitavam estado
inválido. A correção conserva ocorrências sem cliente, preferências dos 16
escritórios recentes e valida filtros também nos retornos antecipados.
Os **351 testes do recorte de regressão, incluindo 71 da home**, passaram
em SQLite temporário após a correção, com 31 avisos existentes de ambiente;
esse recorte não comprova concorrência nem agregação monetária. A política
atual do ambiente impede reutilizar o PostgreSQL local via rede.
A [reconferência única](../auditorias/2026-09-30-dl-049-reconferencia.md)
aprovou a correção na árvore `f1d7592`, com 138 testes próprios, navegador e
inspeção da CI do commit remoto `280873b`. Os quatro jobs passaram; Backend
em PostgreSQL 16.15 registrou **3.563 aprovados, 50 pulados e 2 avisos**;
o instrumento de documentos registrou **139 aprovados**, mais a medição real.
Relatórios e apontadores são a única alteração posterior à árvore auditada;
a CI do último HEAD do PR deve passar antes de integrar.

**AGORA — sessão de 2026-09-29 (3ª rodada). O Fred revisou o relatório e corrigiu
**quatro pontos**; todos foram **verificados na fonte** antes de entrar no repositório,
e **dois deles corrigem erro meu**. As decisões que faltavam foram dadas. A DMPL (CTB-14)
pode ser implementada; a D8 (API da DLPA) também.**

### Correções do Fred (29/09/2026) — as quatro verificadas

| # | Correção | Verificação na fonte |
| --- | --- | --- |
| 1 | A NBC TG 26 (R5) **não** está revogada "para 2026" | ✅ **CONFIRMADO** — o ato é de **13/11/2025** (cabeçalho e fecho da cláusula de vigência do PDF oficial) e a aplicabilidade é **exercícios iniciados a partir de 01/01/2027**. **Exercícios 2025/2026 seguem ancorados na R5.** A data 25/02/2026 é o campo "publicação no DOU" da ficha do CFC, **não a do ato** — a afirmação anterior neste arquivo e no plano **corrigida**. ⚠️ A data do DOU em si está em divergência entre o CFC (25/02/2026) e o Fred (22/12/2025): **registrada como divergência, sem efeito em conclusão alguma.** |
| 2 | A reserva de lucros a realizar **tem** lastro: art. 197 LSA | ✅ **CONFIRMADO — e eu estava ERRADO.** O art. 197 (redação da Lei 10.303/2001) institui exatamente essa reserva, e o **art. 199** também a nomeia. A afirmação anterior ("não existe na LSA") saiu. **O erro foi meu** — veio do relatório de pesquisa, que reportou ausência como fato sem segunda fonte. Rótulo trocado para **"art. 197 LSA"** (S/A; Ltda por regência supletiva, art. 1.069 CC). |
| 3 | A conciliação DMPL ↔ Balanço não é só invariante | ✅ **CONFIRMADO** — o **item 106(d) da R5 / 107(c) da TG 51** exige, para **cada componente do PL**, a conciliação entre o valor contábil no início e no final; esse saldo final é o do Balanço na mesma data. Reescrito como **exigência derivada do item 106(d) e da consistência do conjunto** — não como citação literal. |
| 4 | O item 52 **já** exigia julgamento; não mudou | ✅ **CONFIRMADO — e eu estava ERRADO.** O item 52 diz *"é necessário o exercício de julgamento"*; o B10 diz *"É exigido julgamento"*. **Não houve mudança de prescrição para julgamento.** A única diferença material: a expressão ***"em cada página"*** está no 52 e **não aparece no B10** — mas o B10 nomeia *"títulos apropriados para as páginas"*, então **repetir em cada página continua cumprindo** a norma em 2027. **Logo o documento do cliente NÃO muda**; muda a justificativa interna e a citação (52 → B10). |

### Decisões do Fred, agora fechadas

1. ✅ **Versionamento por data de início do exercício: APROVADO, e é OBRIGATÓRIO** —
   não opcional. O item citado varia com a vigência, e o produto **deve prever a adoção
   antecipada** da NBC TG 51 antes de 01/01/2027.
2. ✅ **Item 52 / B10: resolvido** pelo ponto 4 acima. Documento do cliente **não** muda.
3. ✅ **Base da DMPL: encerrada a busca em diploma.** A Lei 11.638/2007 **não** criou a
   DMPL (trocou a DOAR pela DFC e criou a DVA). A base é: **competência** = DL 9.295/46,
   art. 6º, alínea "f" (redação da Lei 12.249/2010) — confirmada no **préâmbulo da
   própria NBC TG 51**, verbatim; **obrigação** = NBC TG 26 (R5) item 10 e, de 2027 em
   diante, NBC TG 51; **PMEs** = NBC TG 1000 (admite a DLPA no lugar da DMPL em certas
   condições); **microempresas** = ITG 1000, **não obrigatória**.
   ⚠️ **Única lacuna que resta:** para **companhias abertas**, o **ato da CVM que
   aprovou o CPC 26** não foi lido em fonte oficial — declarado, não inventado.

### O que mais mudou nesta rodada

- **Repositório movido para fora do OneDrive** → **`C:\src\DataLedger`**. O OneDrive era
  a causa do I/O-bound, não o SQLite. Copiado, verificado (mesmo commit, `manage.py
  check` limpo) e é o novo local de trabalho.
- **Módulo que travava a suíte: ACHADO — e é SISTÊMICO, não um ponto.** Três
  execuções de `pytest` terminaram em silêncio (sem traceback, sem timeout do pytest).
  O `faulthandler` mostrou a causa: **espera infinita** — `barreira.wait()` e
  `t.join()` **sem timeout**. Se uma thread morre antes da barreira, as outras
  esperam para sempre. ⚠️ A descrição antiga deste arquivo mandava deselecionar
  `test_restricoes_contabilidade.py::test_bl144_codigo_conta_duplicado`, **caminho
  errado** — por isso a deseleção anterior não funcionou.
  - ✅ **Corrigido (commit `bc52c5b`):** `test_bl144_codigo_conta_duplicado.py`,
    `test_api.py` (1º teste de concorrência) e `test_dl043_correcao_rodada1.py`
    (incluindo dois `join()` sem timeout adicionais no mesmo arquivo, nas linhas 476-477 e 686-687). Todas as
    esperas ganharam timeout e uma asserção de `is_alive()`. **Nenhuma guarda foi
    afrouxada** — `resultados` incompleto reprova, porque as asserções de baixo exigem
    o código de resposta de todas as threads.
  - ⚠️ **NÃO CORRIGIDO — e é o que trava a suíte ainda:** a varredura do repositório
    encontrou **cerca de 30 esperas infinitas em 13 arquivos de teste**. Depois da
    correção acima, `test_api.py` **continua travando no teste de concorrência
    seguinte do mesmo arquivo** (linhas 378-400) — o que confirma que o alcance é
    maior. Arquivos com o padrão: `test_dl016_fatia1_*.py` (8 pontos),
    `test_dl046_livro_caixa.py` (3), `test_bl40_bl41.py` (2),
    `test_dl023_regime_tributario_periodo_unico.py` (3),
    `test_bl144_matriz_duplicada.py`, `test_dl043_zeramento_concorrencia_e_permissoes.py`,
    `fiscal/tests/test_concorrencia.py` (2), `fiscal/tests/test_dl076_um_envio_por_vez.py` (3),
    entre outros.
    **Não foi feito num commit só de propósito:** são testes que guardam invariantes
    de concorrência de CNPJ, lançamento e zeramento — nível 1. Mexer em 13 arquivos
    desses exige etapa própria, com verificação própria. **Ordem a definir pelo Fred.**
  - ⚠️ **Consequência prática:** a suíte `pytest` **completa não termina localmente**
    no Windows. A CI (Linux + PostgreSQL) roda tudo verde em ~4m35s. Para medir
    localmente, usar recorte de módulo.

- **PowerShell 7 instalado (7.6.6)**; `scripts/validate-docs.ps1` **original** executado
  e **verde** (*"Documentação válida: 187 arquivos Markdown verificados"*, exit 0). A
  **réplica em Python foi descartada**, para não haver dois validadores.
- **Reserva de lucros a realizar** deixa de ser "escolha de desenho" e passa a ter
  fundamentação legal — ver o ponto 2 acima.
- **A decisão de 29/09 sobre a correção monetária se confirma** com base oficial: Lei
  9.249/95, art. 4º, p.ú. veda *"qualquer sistema de correção monetária de demonstrações
  financeiras, inclusive para fins societários"*. ⚠️ A referência a "**Lei 9.492/95**"
  que circulou é **ERRADA** (a 9.492 é de 1997, protesto de títulos).
- **RC-137 omitiu três reservas de capital** do art. 182 (§1º "c" e "d", §2º). As duas
  primeiras entram na DMPL; a terceira é letra morta (mesma vedação da Lei 9.249/95).
- **Branch de trabalho:** `docs/dl-048-premissa-normativa`.
- ✅ **RESOLVIDO — as ~30 esperas infinitas foram eliminadas** (branch
  `test/esperas-limitadas`). A varredura achou **9 arquivos** com `join()` e
  `barreira.wait()` **sem timeout**: `test_bl40_bl41.py`,
  `test_dl016_fatia1_fechamento_reabertura_entrega.py`,
  `test_dl043_zeramento_concorrencia_e_permissoes.py`, `empresas/test_api.py`,
  `test_bl144_matriz_duplicada.py`, `test_dl023_regime_tributario_periodo_unico.py`,
  `fiscal/test_concorrencia.py`, `fiscal/test_dl076_um_envio_por_vez.py` e
  `test_dl046_livro_caixa.py`. Todas as esperas ganharam **`join(timeout=60)`** e
  **`wait(timeout=30)`**, e **47 asserções de `is_alive()`** exigem que as threads
  tenham concluído.
  ⚠️ **O timeout sozinho seria perigoso**: sem a asserção, uma thread que não
  concluísse deixaria o teste *seguir* com resultados incompletos, e uma
  verificação que só confere "não levantou exceção" passaria — **falso positivo
  silencioso**, pior que travar. Por isso a asserção veio junto, e é o que garante
  que a guarda fica **mais forte**, não mais frouxa.
  **Efeito medido:** os 9 arquivos passaram a **terminar em 4min20s**; antes,
  terminavam em silêncio, sem traceback e sem timeout do próprio pytest.
  ⚠️ **As 30 falhas restantes são a lacuna SQLite × PostgreSQL já conhecida**
  (`database is locked`, `no such table: pg_indexes`, `UNIQUE constraint failed`) —
  **nenhuma** delas é *"thread não concluiu"*, o que prova que os timeouts são
  folgados e não estão mascarando nada. **O veredouro é a CI em Linux +
  PostgreSQL**, onde a suíte completa roda verde.
  ⚠️ **Dois erros meus nesta etapa, ambos corrigidos antes de seguir:** o script
  de transformação emitting a asserção **dentro** do `for` e sobre a variável de
  loop em vez da coleção; e, na correção seguinte, emitindo os **nomes como
  strings** (`for t in ("thread_a", "thread_b")`), o que quebrava com
  `AttributeError: 'str' object has no attribute 'is_alive'`. Os dois foram
  encontrados **rodando os testes**, não por leitura do diff — e é por isso que
  a primeira versão não foi commitada.

### Próximo passo, agora sem decisão pendente

1. ✅ **D8 (API da DLPA) — ENTREGUE.** `DlpaView` + `ContaClassificacaoDlpaView` +
   `ContaSerializer.classificacao_dlpa`, **projetadas prevendo que a DLPA pode estar
   embutida na DMPL** (art. 186, §2º) e não só como peça autônoma. Nível 2.
   Plano de uma página em
   [DL-048-fatia-d8-api-da-dlpa.md](../planos/DL-048-fatia-d8-api-da-dlpa.md).
   **25 testes novos**; a guarda de contagem de rotas foi de **15 para 17** na API.
   **O §2º é DECLARADO na resposta** (chave `paragrafo_2`, sempre presente, com a
   pendência do dividendo por ação e o motivo), em vez de omitido — é o achado 11 da
   auditoria visível para quem consome. E **a `chave` de cada linha é o contrato com a
   CTB-14**: a linha da DLPA é a DESTINAÇÃO e a coluna da DMPL é a CONTRAPARTIDA
   (RC-137), então a DMPL vai ler `transferencia:<reserva>` × `reversao:<reserva>`
   (decisão D4) como movimento de coluna, sem segunda lógica.
   A API **não escolhe** entre DLPA autônoma e embutida: é faculdade da lei, e a
   escolha é da emissão — por isso a resposta **não tem** campo "modo".
2. **CTB-14 (DMPL)** — nível 1, com auditoria independente obrigatória. Aplica as duas
   normas por data de início do exercício, com adoção antecipada prevista.
3. **As ~30 esperas infinitas restantes** em 13 arquivos de teste (achado sistêmico
   acima) — etapa própria, com verificação própria, porque guardam invariantes de
   concorrência de CNPJ, lançamento e zeramento. Ordem a definir pelo Fred.


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

   Estado verificado em 29/09/2026: o conserto foi o **PR #59**, aberto da
   branch de trabalho direto para a `main` (o merge `main ←
   feat/dl-048-dlpa` foi conferido **limpo** com `git merge-tree`, sem
   conflito). Nível 1 — **a auditoria independente foi EXECUTADA e
   REPROVOU** ([rodada 1](../auditorias/2026-09-29-dl-048-dlpa-rodada-1.md),
   16 achados: 2 de alta, 9 de média, 5 de baixa). Os achados de alta e de
   média foram corrigidos em **duas rodadas** — a primeira por conta própria,
   a segunda por ordem do Fred, que optou por não mesclar antes de corrigir o
   restante. ⚠️ O `AGENTS.md` §3.1 diz que a **terceira** rodada é proibida;
   a segunda não é, e foi pedida.

   ✅ **INTEGRADA pelo PR #59**, mesclado na `main` em 29/09/2026 às 17:43
   (squash, `7761ea5`), com os **quatro jobs verdes** no commit `f831dad` e
   **conferência de conteúdo**: `git diff origin/main origin/feat/dl-048-dlpa`
   sai **vazio** — a `main` tem exatamente o mesmo conteúdo da branch (23
   arquivos, +3.909/−82 contra o ponto de partida da fatia).

   ⚠️ **O que a integração NÃO resolve: a conformidade normativa é NÃO
   CONCLUÍDA.** Sem rede nesta máquina, nem a implementação nem a auditoria
   leram Planalto/CFC, e **nenhuma** linha do art. 186 — nem a Lei 6.404/76,
   nem a Lei 9.249/95 (base da remoção da rubrica de correção monetária) —
   foi confirmada em fonte oficial. Isto é do Fred, com o texto na mão.
   Depois disso: fatia de paridade de API (`DlpaView` +
   `ContaClassificacaoDlpaView`, decisão D8) e o CTB-14
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
