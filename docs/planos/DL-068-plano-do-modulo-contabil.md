# DL-068 — Plano do módulo Contabilidade: roteiro de out/2026 a 2028

**Demanda:** ordem direta do Fred em 05/10/2026 — analisar com cuidado, como
contador sênior, e montar o plano do módulo Contabilidade do DataLedger: todos
os aspectos e relatórios, com os manuais do sistema de referência tratados
**só como exemplo**, e pesquisa na internet das novidades, das obrigações
acessórias novas e da legislação. **Estado:** [fonte única](../agents/estado.md).
**Branch:** `ccr-3ba75539-29vqwn` → `main`. **Risco:** esta etapa é **só
documentação** — nenhum código, dado, contrato ou migração. Cada fatia de
código que sair daqui terá **DL própria** e o nível do
[AGENTS.md §3.1](../../AGENTS.md): lançamento, saldo, demonstração, livro e
arquivo de obrigação são **nível 1**; tela de trabalho, importador e relatório
de conferência são **nível 2**.

> Auditoria de software não substitui a validação profissional das regras
> contábeis e legais. Toda regra deste plano marcada como hipótese, e toda
> fonte marcada "só fonte secundária", precisa da validação do Fred antes de
> virar comportamento definitivo.

## Decisões do Fred que valem aqui

| Origem | Decisão |
| --- | --- |
| **05/10/2026** | O plano nasce de pesquisa normativa atual; os manuais do sistema de referência "são apenas exemplos". Nenhum texto deles entra no repositório ([fontes-de-referencia.md](../projeto/fontes-de-referencia.md)). |
| DL-048, 28/09/2026 (registradas aqui como RC-157 a RC-160) | DLPA **e** DMPL como documentos próprios; seis reservas de lucros e as de capital como colunas; DFC nos **dois** métodos; DRA e DVA **exigidas**, não em espera; o escritório **compensa** lucros e prejuízos acumulados (mecanismo ainda em aberto, PE-38). |
| Requisitos, 29/09/2026 | Demonstração versionada por vigência: NBC TG 26 (R5) até exercícios iniciados em 31/12/2026, NBC TG 51 a partir de 01/01/2027, com **opção de adoção antecipada** prevista no produto. |
| RC-118 | Classificação de demonstração é **campo fixo na conta**, conjunto de linhas definido no código, nunca inferido de código ou nome. |
| DE-086, DL-065 | A classificação da DRE pode mudar com movimento; a da DLPA e a da DMPL travam em competência encerrada ou entregue. |
| RC-101 a RC-103 | Nada se grava em período fechado; competência entregue não reabre; estorno de mês fechado nasce em mês aberto; só ADMINISTRADOR ou GESTOR fecha e reabre. |
| RC-119 | A DRE sai com o mês e o acumulado do exercício; comparativo com o exercício anterior ficou fora da **primeira versão** — este plano propõe revê-lo (ver [Decisões que dependem do Fred](#decisões-que-dependem-do-fred)). |

## Relação com o que o repositório já tem

**Conclusão: este plano complementa a paridade; não a substitui.**

- [paridade/contabilidade.md](../projeto/paridade/contabilidade.md) (DL-047,
  27/09/2026, remedido em 04/10/2026) diz **o quê**: 74 itens CTB com
  dependência, dado, regra, tela e critério de aceite.
- Este plano diz **quando**, **por quê nesta ordem** e **o que mudou** em 2026
  e 2027: NBC TG 51, normas por porte (NBC TG 1001 e 1002), comparativo
  obrigatório, Lei 15.270/2025 (dividendos), LC 224/2025, Lei 14.789/2023,
  Orientação Técnica CFC nº 1/2026 (IBS e CBS na contabilidade), leiaute 9 da
  ECD e leiaute 12 da ECF, fim da DIRF e da DCTF clássica.
- O fiscal tem o seu: [DL-067](DL-067-plano-do-modulo-fiscal.md). A fronteira
  está em [Integração com os módulos vizinhos](#integração-com-os-módulos-vizinhos).
- Item vira código só com **plano DL próprio** (regra da paridade e do
  [AGENTS.md](../../AGENTS.md) §3).

### O que já existe e não se refaz

Medido no código em 05/10/2026, por símbolo (as linhas mudam a cada entrega).

| Capacidade | Onde | Situação |
| --- | --- | --- |
| Plano de contas hierárquico, com classificação patrimonial, DRE, DLPA e DMPL na conta | `Conta` em `apps/contabilidade/models.py` | Existe |
| Lançamento por partidas dobradas, imutável, idempotente, com estorno | `criar_lancamento`, `estornar_lancamento`; gatilhos de banco da DL-052 (`trg_item_lancamento_balanceado`, `trg_lancamento_contabil_imutavel`) | Existe — débito = crédito e imutabilidade garantidos **também no PostgreSQL** |
| Competência: encerrar, reabrir, marcar como entregue | `Competencia`, `encerrar_competencia`, `reabrir_competencia`, `marcar_competencia_como_entregue` | Existe |
| Diário, Razão, Balancete por período | `listar_diario`, `apurar_razao`, `apurar_balancete` | Existe, como relatório de **conferência** |
| Seis conferências de integridade | `localizar_*`, `movimento_fora_do_periodo` | Existe |
| Balanço Patrimonial e DRE com veto de emissão | `apurar_balanco_patrimonial`, `apurar_dre`, `avaliar_emissao_*` | Existe |
| Parâmetro contábil por vigência e zeramento | `ParametroContabilEmpresa`, `zerar_resultado` | Existe |
| DLPA e DMPL, conciliadas entre si e com o Balanço | `apurar_dlpa`, `apurar_dmpl`, `MarcacaoDmpl` | Existe |
| Trilha de auditoria na mesma transação, imutável, cobrindo o admin | `RegistroAuditoria` em `apps/auditoria/` | Existe — consulta **só pela API**; não há tela |
| Livro-caixa e carnê-leão da pessoa física | `apps/livro_caixa/` | Existe (módulo adjacente, CTB-63) |

**O que não existe** e pesa neste plano: DFC (planejada, DL-066), DRA, DVA,
notas explicativas, comparativo com o exercício anterior, encerramento do
exercício, sócios, contador responsável, origem do lançamento, implantação de
saldos, escopo de acesso por empresa, plano referencial, ECD e ECF.

### Correções que este plano faz aos documentos (fatia 0)

A análise de 05/10/2026 encontrou, na paridade e no estado, afirmações que
levariam a planejar errado. Elas **não** são corrigidas no corpo de cada
documento nesta etapa — ficam listadas aqui, e a paridade ganha um aviso no
topo apontando para esta lista. **Onde divergirem, vale este plano.**

| # | Documento e item | O que diz | O que é |
| --- | --- | --- | --- |
| F0-1 | Paridade, CTB-02 | Constraint de banco de débito = crédito "adiada" | Entregue pela DL-052 (migração `0013_dl052_invariantes_do_livro_no_banco`); a empresa da conta da partida segue validada só em Python (BL-84 continua válido) |
| F0-2 | Paridade, CTB-14 | Fonte da DMPL "a confirmar": art. 186, parágrafo único, e Lei 11.941 | Já conferida em [requisitos.md](../projeto/requisitos.md): NBC TG 26 (R5) itens 106 a 110 e NBC TG 51; competência do CFC no DL 9.295/46, art. 6º, "f" |
| F0-3 | Paridade, CTB-15 | Método direto depende de extrato e conciliação (CTB-40/41) | A [DL-066](DL-066-dfc.md) tira o fluxo do lançamento contra as contas de caixa. A troca de premissa precisa de decisão do Fred (ver decisões) |
| F0-4 | Paridade, CTB-17 | DVA no "art. 176, §4º" | **Art. 176, V** — o §4º é o das notas explicativas (Planalto, lido em 05/10/2026) |
| F0-5 | Paridade, CTB-13, 14, 15, 16, 17 e perguntas 3 a 5 | Perguntam o que a DL-048 já respondeu (DLPA isolada, reservas, métodos da DFC, DRA e DVA) | Respondido em 28/09/2026 — RC-157 a RC-160 |
| F0-6 | Paridade, todas as demonstrações | Citam NBC TG 26 (R5) sem a vigência | R5 vale para exercícios iniciados até 31/12/2026; NBC TG 51 depois |
| F0-7 | Paridade, CTB-25 e CTB-26 | Dependência circular (termo depende de livro, livro depende de termo) | O livro contém os termos: CTB-26 depende de CTB-25, não o contrário |
| F0-8 | Paridade, Onda 0 | "Dez" itens, lista onze | CTB-08 não existe; sai da Onda 0 |
| F0-9 | Paridade, CTB-50 a CTB-52 | Leiaute e prazo "a confirmar" | ECD: IN RFB 2.003/2021, leiaute 9 (ADE Cofis 01/2026), último dia útil de junho. ECF: IN RFB 2.004/2021, leiaute 12 (ADE Cofis 02/2026), último dia útil de julho |
| F0-10 | [paridade/lalur.md](../projeto/paridade/lalur.md), LAL-26 | "M350 (Parte B)" | M350 é a **Parte A do e-Lacs**; a Parte B está em M010, M410 e M500 |
| F0-11 | [requisitos.md](../projeto/requisitos.md), fontes da DL-048 | "PMEs = NBC TG 1000; microempresas = ITG 1000, não obrigatória" | Microentidade: **NBC TG 1002**; pequena empresa: **NBC TG 1001**; média: NBC TG 1000 (R1); a ITG 1000 de 2012 foi revogada e a vigente é a de 15/12/2022 |
| F0-12 | requisitos.md e DL-048 | RC-137 a RC-140 definidos só no plano; RC-138 e RC-139 já eram outra coisa | Registrados como RC-157 a RC-160 nesta etapa |
| F0-13 | [estado.md](../agents/estado.md), "Fila seguinte" | DMPL e reclassificação como próximos | Já integradas (DL-061 e DL-065) |
| F0-14 | DL-067, linhas da EFD-Contribuições e da Reinf | "encerra" a EFD-Contribuições; Reinf "prorroga" | A NT EFD-Contribuições 011/2026 a mantém por no mínimo 5 anos para saldos e retificação; o vencimento da Reinf **antecipa** para o dia útil anterior (manual 2.1.2.1) |

### Vocabulário deste documento

| Termo | Sentido aqui |
| --- | --- |
| **Porte** | Microentidade, pequena empresa ou média empresa da ITG 1000 (itens 5 e 11), pela receita bruta do exercício anterior. Decide o conjunto mínimo de demonstrações. |
| **Natureza** | Sociedade anônima aberta ou fechada, limitada, empresário individual, entidade sem fins lucrativos, pessoa física. |
| **Perfil contábil** | Porte + natureza + regime tributário + vigência normativa. É a entrada da matriz de demonstrações e da matriz de obrigações. |
| **Livro digital** | A ECD: o recibo de transmissão é o termo de autenticação (Decretos 8.683/2016 e 9.555/2018). |
| **Cruzamento** | Conferência entre duas fontes que precisam contar a mesma história (contabilidade × obrigação, obrigação × obrigação). |

## Esta etapa (DL-068)

| Campo | Conteúdo |
| --- | --- |
| Objetivo | Plano do módulo Contabilidade, com calendário regulatório, ordem de entregas, catálogo de relatórios e requisitos, conciliado com a paridade, com o estado e com o plano fiscal |
| Entregáveis | Este plano; aviso e itens CTB-75 a CTB-84 na paridade; RC-157 a RC-160, HI-51 a HI-56 e PE-76 a PE-82 em `requisitos.md`; linha no README e no estado |
| Critérios de aceite | (1) toda afirmação normativa cita ato, item e situação da fonte (confirmada, só secundária, não encontrada); (2) nenhuma hipótese aparece como requisito confirmado; (3) cada frente nomeia o nível de risco e o item CTB; (4) links relativos existem; (5) o teste de documentação do estado passa |
| Testes | `pytest apps/core/tests/test_documentacao_do_estado.py`; verificação de links, título, espaço no fim de linha e nova linha final dos arquivos alterados |
| Reversão | Reverter o commit — só documentação |
| Estado | em validação |

## Plano

### Diagnóstico em três frases

1. O **núcleo do livro é sólido** (partida dobrada garantida no banco,
   imutabilidade, fechamento, trilha) e as **demonstrações avançaram** (BP,
   DRE, DLPA, DMPL); o que falta para o escritório usar o produto num cliente
   real **não é relatório novo**, é o **ciclo anual**: implantar saldos,
   encerrar o exercício, emitir o conjunto completo de demonstrações com
   comparativo, e gerar a ECD.
2. Três mudanças externas **têm data** e passam por cima da ordem da
   paridade: a **Lei 15.270/2025** já exige, desde janeiro de 2026, saber de
   que exercício vem cada lucro distribuído; a **reforma** troca PIS e Cofins
   por CBS em **janeiro de 2027**; e a **NBC TG 51** muda a DRE e a DFC dos
   exercícios iniciados a partir de **01/01/2027**.
3. O que mais arrisca o escritório **não é cálculo**: é o **sigilo entre
   clientes** (hoje todo usuário do escritório enxerga todas as empresas —
   CTB-54) e a **falta de backup verificado** (PE-07). Os dois vêm antes de
   qualquer dado real.

### Decisões-chave de arquitetura

| # | Decisão | Por quê |
| --- | --- | --- |
| A1 | **Matriz de demonstrações por perfil contábil**: o produto calcula quais demonstrações a empresa deve emitir (porte, natureza, regime, exercício) e veta a emissão de um conjunto incompleto, em vez de oferecer menu livre | O conjunto exigido muda por porte (NBC TG 1002 item 3.6, NBC TG 1001 item 3.5), por natureza (LSA art. 176; ITG 1000 item 10) e por exercício (TG 26 R5 → TG 51). É a mesma ideia da matriz de obrigações (OBR-01 do [plano mestre](../projeto/plano-mestre.md)) |
| A2 | **Demonstração versionada por vigência normativa**, com as duas versões convivendo: exercício de 2026 pela R5, exercício de 2027 pela TG 51, comparativo de 2026 **reapresentado** pela TG 51 com conciliação por rubrica | NBC TG 51, apêndice C2 e C3 (aplicação retrospectiva e conciliação do comparativo) |
| A3 | **Comparativo com o exercício anterior** em toda demonstração anual | LSA art. 176, §1º (lido no Planalto em 05/10/2026). Hoje nenhuma demonstração o tem |
| A4 | **Um só leitor de eventos de PL**: DLPA, DMPL, encerramento do exercício, controle de lucros por exercício de apuração e reserva de incentivos fiscais leem os **mesmos** lançamentos, classificados uma vez | Já é a regra da DL-048 (RC-157) e da DL-061; estendê-la aos novos controles evita lógicas divergentes sobre o mesmo saldo |
| A5 | **O livro oficial é a ECD**; o Diário e o Razão em PDF são conferência | ITG 2000 (R1), item 17: livro digital não se imprime nem se encaderna; o recibo da ECD é o termo de autenticação. Livro em papel numerado (CTB-26) só para quem não entrega ECD e autentica na Junta (CC art. 1.181) |
| A6 | **Gerar não é entregar**: o produto prepara, valida e guarda o arquivo da ECD e da ECF; a transmissão é ato do usuário autorizado, com aprovação vinculada ao conteúdo exato | [AGENTS.md](../../AGENTS.md) §11 e OBR-10 do plano mestre |
| A7 | **Cruzamento é conferência, não cálculo paralelo**: a ECF recupera a ECD; o produto confere, não recalcula a mesma base por dois motores | Manual da ECF leiaute 12, item 1.3; regra de responsabilidade dos dados do plano mestre §9 |
| A8 | **Escopo de acesso por empresa no servidor** antes de qualquer cliente real | CTB-54, PE-36; [AGENTS.md](../../AGENTS.md) §11 |

### Calendário regulatório

Datas "derivadas" são aplicação da regra do ato ao calendário, não texto do
ato.

| Quando | O que muda | Fonte | Situação da fonte |
| --- | --- | --- | --- |
| 01/01/2026 | IRRF de 10% sobre lucros e dividendos acima de R$ 50 mil por mês, da mesma PJ para a mesma PF; isenção de transição para lucros apurados até 2025 com distribuição aprovada até 31/12/2025, pagos de 2026 a 2028 nos termos do ato | Lei 15.270/2025 (Lei 9.250/95, art. 6º-A; Lei 9.249/95, art. 10) | Confirmada no Planalto |
| 01/01/2026 | Recolhimento sob código 1841; declaração no R-4010 da Reinf | Perguntas e Respostas RFB de 19/12/2025; NT EFD-Reinf 02/2026 | Confirmada (código e evento); data da NT só secundária |
| 01/01/2026 | IRRF de 17,5% sobre JCP | LC 224/2025, art. 8º, e art. 14 | Confirmada; vigência por inferência da regra geral do art. 14 |
| 01/01/2026 | DECORE só por sistema do CFC, com e-CPF | Resolução CFC 1.777/2025 | Confirmada |
| 2026 inteiro | CBS 0,9% e IBS 0,1% em teste; dispensa de recolhimento para quem cumpre as obrigações acessórias | LC 214/2025, arts. 343, 346 e 348 | Confirmada no Planalto |
| Jul/2026 | IBS e CBS **fora da receita**; passivo e crédito reconhecidos por competência; política do teste de 2026 por julgamento da entidade, divulgada em nota | Orientação Técnica CFC nº 1/2026 (não vinculante) | Confirmada no PDF do CFC; data exata do ato não encontrada |
| 30/06/2026 | ECD do ano-calendário 2025 | IN RFB 2.003/2021, art. 5º (prazo da IN RFB 2.142/2023) | Confirmada |
| 31/07/2026 | ECF do ano-calendário 2025, leiaute 12 | IN RFB 2.004/2021; ADE Cofis 02/2026 | Confirmada |
| 01/2027 | CBS substitui PIS e Cofins (bases revogadas); EFD-Contribuições deixa de receber fatos geradores novos | LC 214/2025, arts. 542 e 544, III; NT EFD-Contribuições 011/2026 | Confirmada |
| 01/01/2027 | NBC TG 51 para exercícios iniciados a partir desta data; revoga a NBC TG 26 (R1 a R5) | NBC TG 51, de 13/11/2025 | Confirmada no PDF do CFC |
| 15/02/2027 | Primeira apuração assistida da CBS (competência 01/2027), para quem não entrega a DeRE | Decreto 12.955/2026, art. 46 (alterado pelo Decreto 13.075/2026) | Confirmada a regra; data derivada |
| 31/03/2027 | DEFIS do ano-calendário 2026 | LC 123/2006; Resoluções CGSN 140/2018 e 183/2025 | Data derivada |
| 30/06/2027 | ECD do ano-calendário 2026 | IN RFB 2.003/2021, art. 5º | Data derivada; leiaute para o AC 2026 **não publicado** até hoje |
| 30/07/2027 | ECF do ano-calendário 2026 (31/07 é sábado) | IN RFB 2.004/2021 | Data derivada |
| 1º trim/2028 | Primeiras demonstrações anuais pela NBC TG 51 (exercício 2027, com 2026 reapresentado) | NBC TG 51, apêndice C | Confirmada |

### Perfil contábil e conjunto de demonstrações

Esta é a matriz da decisão A1. **Hipótese HI-51** até o Fred validá-la contra a
carteira real: o enquadramento e o conjunto foram lidos na norma, mas a
aplicação a cada cliente é julgamento profissional dele.

| Perfil | Norma | Conjunto mínimo | Fonte |
| --- | --- | --- | --- |
| Microentidade (receita bruta do exercício anterior até R$ 4,8 mi) | NBC TG 1002 | BP, DRE e DLPA; DMPL opcional (a DLPA pode ser coluna dela); notas não obrigatórias, mas as **declarações do item 3.2** são | TG 1002, itens 3.6, 3.7 e 6.2 |
| Pequena empresa (R$ 4,8 mi a R$ 78 mi) | NBC TG 1001 | BP, DRE, DMPL, DFC e notas; DLPA no lugar da DMPL quando o PL só movimenta lucros ou prejuízos acumulados | TG 1001, itens 3.5 e 6.2; ITG 1000, itens 16 e 18 |
| Média empresa (R$ 78 mi a R$ 300 mi) | NBC TG 1000 (R1) | Conjunto da TG 1000 | ITG 1000, item 7 |
| Micro ou pequena que seja **companhia fechada** ou tributada pelo **lucro real** | Lei 6.404/76 | BP, DLPA, DRE, DFC (dispensada se PL < R$ 2 mi), notas | ITG 1000, item 10; LSA art. 176, I a IV e §6º |
| Companhia aberta ou grande porte | NBC TG completas (TG 26 R5 → TG 51) | BP, DRE, DRA, DMPL, DFC, **DVA**, notas | LSA art. 176, V; TG 26 (R5) item 10 |
| Optante do Simples | LC 123/2006 | Contabilidade simplificada **opcional** (art. 27); livro-caixa obrigatório para quem não a mantém (art. 26, §2º). A Lei 15.270 também alcança o dividendo pago pelo Simples | Planalto; Perguntas e Respostas RFB |
| Pessoa física (livro-caixa) | — | Livro-caixa e carnê-leão (CTB-63, já existe) | DL-046 |

**Reflexo que o contador sênior não pode perder:** o redutor do imposto mínimo
da pessoa física (Lei 15.270/2025, art. 16-B, §4º) depende de a empresa
pagadora apresentar **demonstrações financeiras "na forma de regulamento"** —
o regulamento não foi encontrado (PE-78). Se vier como se lê, o sócio de
empresa do Presumido ou do Simples com distribuição alta passa a **precisar**
de contabilidade completa da empresa. É argumento de produto e de honorário,
e o DataLedger precisa estar pronto para ele.

### Arquitetura funcional

```
CADASTRO        empresa · perfil contábil (porte, natureza, regime, vigência)
                sócios e participações · contador responsável (CRC) · signatários
                histórico cadastral por data
PLANO           plano de contas · código reduzido · classificações de demonstração
                plano referencial por ano · subcontas correlatas · correspondência entre exercícios
LIVRO           lançamento (origem, documento, rascunho → efetivado) · implantação de saldos
                competência · exercício · período de trabalho
SALDOS          camada de saldos (existe) · saldos antes do encerramento (I355)
DEMONSTRAÇÕES   BP · DRE · DRA · DLPA · DMPL · DFC · DVA · notas — por vigência e com comparativo
                matriz de demonstrações por perfil · veto de conjunto incompleto
ENCERRAMENTO    zeramento (existe) · encerramento do exercício · compensação · reservas
                destinação e dividendos · lucros por exercício de apuração · carta de responsabilidade
OBRIGAÇÕES      ECD (gera, valida, guarda) · ECF (recupera ECD + Lalur) · substituição e retificação
CONFERÊNCIA     integridade (existe) · riscos contábeis-fiscais · cruzamentos com obrigações
                trilha consultável · pré-validação antes do programa oficial
ANÁLISE         vertical/horizontal · índices · comparativos · gráficos
```

### Frente 1 — Fundamentos do livro e segurança

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| Escopo de acesso por empresa | Associação usuário × empresa verificada no servidor em toda view, API, relatório e exportação; migração dos vínculos existentes; tela de gestão | CTB-54 | 1 |
| Backup e restauração verificados | Procedimento executado e medido, inclusive antes de operação destrutiva (zeramento, substituição de ECD) | CTB-49 | 1 (operação) |
| Origem e documento de origem | Origem obrigatória (manual, fiscal, folha, zeramento, encerramento, implantação, ajuste) e vínculo ao documento | CTB-32 | 1 |
| Implantação de saldos | Assistente de lançamento único do balanço anterior, com retificadoras, resultado anterior e **lucros acumulados por exercício de apuração**; conciliação com o balanço aprovado | **CTB-76** (novo) | 1 |
| Rascunho → efetivado | Preparação, conferência e efetivação; rascunho fora do saldo oficial | BL-10 | 1 |
| Período de trabalho | Janela de digitação por empresa, livre/aviso/bloqueio | CTB-08 | 2 — **só se o Fred confirmar uso** |
| Tela da trilha | Consulta da trilha por empresa, usuário, operação e período; hoje só API | CTB-61 | 2 |

**Não copiar do sistema de referência:** iniciar e parar a auditoria, filtrar
quais tabelas são auditadas e **excluir períodos auditados**. No DataLedger a
trilha é sempre ligada, na mesma transação, e imutável (DL-024, DL-030); a
retenção é política de dados, nunca botão.

### Frente 2 — Cadastros societários e responsáveis

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| Sócios e quadro societário com vigência | Pessoa (CPF/CNPJ), participação, cargo, entrada e saída; a mesma pessoa em vários papéis (CTB-58) decidida **antes** | CTB-28, CTB-58 | 2 (cadastro) com efeito nível 1 (dividendos) |
| Contador responsável e signatários | Contador com CRC e UF, vínculo por vigência; responsável legal; signatários da ECD (registro J930) e das demonstrações (CC art. 1.184, §2º; ITG 2000 item 13; ITG 1000 item 23) | CTB-29 | 2; veto de emissão sem responsável é nível 1 |
| Histórico cadastral por data | Razão social e endereço como eram no período, para termos e identificação | CTB-30 | 2 |
| Perfil contábil da empresa | Porte, natureza e regime por exercício, alimentando a matriz A1 | **CTB-77** (novo) | 1 (decide o conjunto entregue) |
| Modelo para cliente novo | Plano de contas e parâmetros padrão aplicáveis a empresa sem lançamento | CTB-31, CTB-62 | 2 |

### Frente 3 — Plano de contas

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| Editar conta pela interface | Mover de grupo, renomear, desativar, com as travas que já existem em `Conta.clean()` | BL-541, CTB-60 | 2 |
| Código reduzido | Número de digitação, distinto do código estruturado | CTB-01 (RC-99) | 2 |
| Plano referencial por ano e por forma de tributação | Tabela dinâmica da RFB versionada por ano-calendário; vínculo de 100% das analíticas; decisão 1:1 ou N antes do código | CTB-50, CTB-56 | 1 |
| Subcontas correlatas | Vínculo de subconta de ajuste a valor justo, mais e menos-valia e ágio à conta principal (Lei 12.973/2014), exigido na ECD | **CTB-75** (novo) | 1 — só para Lucro Real; prioridade depende da carteira |
| Correspondência entre exercícios | Registrar no ato da reorganização quem virou quem, com saldo transferido (registro I157 da ECD) | CTB-55 | 1 |

### Frente 4 — Demonstrações contábeis

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| DFC direta e indireta | Já planejada — [DL-066](DL-066-dfc.md) | CTB-15 | 1 |
| Comparativo com o exercício anterior | Coluna do exercício anterior em BP, DRE, DLPA, DMPL, DFC, DRA e DVA, pelo **mesmo critério** de apuração; conta nova declarada | **CTB-78** (novo) | 1 |
| Matriz de demonstrações e veto de conjunto incompleto | Ver decisão A1 | CTB-77 | 1 |
| DRA | Resultado líquido + outros resultados abrangentes, classificação própria na conta | CTB-16 | 1 |
| DVA | Riqueza gerada e distribuída; fecha em si mesma | CTB-17 | 1 |
| Notas explicativas | Versão simples: notas numeradas por exercício, ligadas a conta ou demonstração; para microentidade, as declarações do item 3.2 da TG 1002 | CTB-18 | 1 (compõe a demonstração) |
| NBC TG 51 | Versão paralela da DRE com cinco categorias e três subtotais (lucro operacional; lucro antes de financiamento e tributos; lucro líquido), MPM em nota, despesas por natureza ou função; DFC partindo do lucro operacional; conciliação de transição do comparativo | **CTB-82** (novo) | 1 |
| IBS e CBS na DRE | Contas padrão de IBS/CBS a recolher, a recuperar e a apropriar; IBS e CBS **fora da receita bruta** (Orientação Técnica CFC 1/2026, item 16.2); PIS, Cofins, ICMS e ISS continuam como dedução enquanto existirem; nota da política do teste de 2026 | **CTB-83** (novo) | 1 |
| Vedação de designação genérica | Conferência que aponta "diversas contas" ou "contas-correntes" e agregação acima de 0,1 do grupo | (dentro de CTB-06) | 2 |

⚠️ **Atenção ao RC-123** ("deduções só em conta de receita"): com a
orientação do CFC, IBS e CBS **não** são dedução da receita bruta — a receita
já nasce líquida deles. A linha de deduções da DRE continua servindo a PIS,
Cofins, ICMS e ISS até a extinção de cada um. Isto é **HI-53**: a orientação
não é vinculante, e a política contábil é do Fred.

### Frente 5 — Encerramento do exercício e patrimônio líquido

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| Encerramento do exercício | Ato anual distinto do zeramento: saldos antes do encerramento (base do I355 da ECD), zeramento anual, abertura do exercício seguinte, trava do exercício | CTB-24 | 1 |
| Compensação e absorção de prejuízo | Ordem legal de absorção: lucros acumulados, reservas de lucros, reserva legal (LSA art. 189, **parágrafo único**); mecanismo do escritório (PE-38) | CTB-24 (RC-160) | 1 |
| Reserva legal e destinação | 5% do lucro líquido até 20% do capital, dispensa acima de 30% com reservas de capital (LSA art. 193); dividendo mínimo (art. 202); proposta da administração nas demonstrações (art. 176, §3º); excedente distribuído (art. 202, §6º) | CTB-24 | 1 |
| Lucros por exercício de apuração | Saldo de lucros disponíveis **por ano de apuração**, deliberações datadas, dividendos a pagar por sócio; marca dos lucros até 2025 aprovados até 31/12/2025 (transição da Lei 15.270) | **CTB-79** (novo) | 1 |
| Reserva de incentivos fiscais | Controle por origem; uso só para absorver prejuízo, depois de esgotadas as demais reservas de lucros, ou para aumentar capital; recomposição obrigatória (Lei 14.789/2023, art. 16); fora da base do JCP (art. 18) | **CTB-84** (novo) | 1 — só para quem tem subvenção |
| Carta de responsabilidade da administração | Obtida ao término de cada exercício (ITG 1000, itens 12 a 15 e Anexo 1) | CTB-27 | 2 |
| Desfazer zeramento com parâmetro errado | Procedimento rastreável, por estorno | PE-69 | 1 |

**Reflexo cruzado (Lei 4.357/1964, art. 32, lido no Planalto em 05/10/2026;
a redação posterior da multa não foi conferida):** empresa em débito não
garantido com a União não pode dar participação de lucros a sócios. O encerramento deve
**avisar** quando o controle de lucros registrar distribuição — a situação
fiscal vem do módulo Fiscal ou da conferência manual, nunca presumida. É
**HI-55**.

### Frente 6 — Livros e termos

| Item | O que entregar | CTB | Nível |
| --- | --- | --- | --- |
| Diário e Razão com o critério e a identificação | Já existem como conferência; completar o critério de apuração impresso (RC-97) | CTB-03, CTB-04 | 2 |
| Livro na forma de livro, termos | Só para empresa sem ECD que autentica na Junta: numeração sem buraco, termos, assinaturas (ITG 2000 itens 5, 9, 10, 13) | CTB-25, CTB-26 | 1 — **prioridade baixa** (decisão A5) |
| Razão auxiliar e Diário resumido | Livros A, R e Z da ECD | dentro de CTB-51 | 1 |

### Frente 7 — Obrigações acessórias

| Obrigação | O que o módulo faz | Base | CTB |
| --- | --- | --- | --- |
| **ECD** | Gera os livros G (ou R + A/Z) com I050/I051 (plano e referencial), I150/I155 (saldos periódicos), I157 (transferência de plano), I200/I250 (lançamentos), I355 (antes do encerramento), J100/J150/J210 (BP, DRE, DLPA ou DMPL), J800 (notas e outras informações), J930 (signatários); substituta com J801 (termo de verificação) | IN RFB 2.003/2021; leiaute 9; manual de maio/2026 | CTB-51 |
| **ECF** | Recupera a ECD (blocos C, J, K) e recebe do Lalur a Parte A (M300, M350) e a Parte B (M010, M410, M500); no Presumido sem ECD, `TIP_ESC_PRE = "L"`; LC 224 já no leiaute 12 (0020, M300, M350, N620, N630, N670, P200 a P500) | IN RFB 2.004/2021; leiaute 12 (ADE Cofis 02/2026) | CTB-52, [paridade/lalur.md](../projeto/paridade/lalur.md) |
| Obrigados | ECD: Lucro Real; Presumido sem livro-caixa; Presumido que distribui, sem IRRF, acima da base presumida (art. 3º, §3º); imunes e isentas acima de R$ 4,8 mi; SCP em livro próprio. Dispensados: Simples (salvo aporte de investidor-anjo), inativas. ECF: todas, salvo Simples, órgãos públicos e inativas | IN 2.003 art. 3º; IN 2.004 | CTB-77 (perfil) |
| Multas | ECD: Lei 8.218/91, art. 12; ECF: DL 1.598/77, art. 8º-A (Real) e Lei 8.218/91, art. 12 (demais) | Manuais oficiais | — |
| Substituição | ECD substituta só para erro que não se corrige por lançamento extemporâneo, até o prazo da ECD do ano seguinte, com J801; ECD substituta que altera saldos recuperados exige ECF retificadora | IN 2.003 art. 8º, §4º; manual da ECF item 1.14 | CTB-51 |

⚠️ **Alerta para o Fred (HI-56):** a obrigatoriedade da ECD para o Presumido
que distribui lucro acima da base usa a condição "sem incidência de IRRF". Com
a retenção de 10% desde 2026, a leitura dessa condição para o ano-calendário
2026 pode mudar. Nenhuma IN tratou disso até hoje.

**Fora do módulo Contabilidade**, mas lido por ele nos cruzamentos: DCTFWeb
com MIT (IN RFB 2.237/2024; tributos da antiga DCTF desde 2025), EFD-Reinf
(dia 15, antecipa), EFD-Contribuições (até 12/2026), DEFIS. Pertencem ao
[DL-067](DL-067-plano-do-modulo-fiscal.md) e à frente OBR do plano mestre.

**Não copiar:** cruzamentos "DIRF × DCTF" e "ECF × DIRF" do manual de 2018. A
DIRF não existe para fatos geradores desde 01/01/2025 (IN RFB 2.043/2021,
art. 3º, §1º), e a DCTF clássica foi substituída pela DCTFWeb com MIT.
Validação de arquivo do Distrito Federal e de Pernambuco também fica fora.

### Frente 8 — Conferência, auditoria e cruzamentos

O manual do "auditor fiscal" do sistema de referência mostra a **ideia** certa
— conferir antes do programa oficial e cruzar declarações — com cruzamentos
que já não existem. O DataLedger faz isso por regra própria, versionada.

| Conferência | O que confere | Base | CTB | Nível |
| --- | --- | --- | --- | --- |
| Pré-validação da ECD | Referencial 100% vinculado, I355 coerente com o zeramento, J100 = saldos, J150 = DRE, signatários presentes, partidas da mesma empresa | Leiaute 9 | **CTB-80** | 1 |
| ECD × ECF | Saldos recuperados × ECD ativa; ECD substituta pede ECF retificadora | Manual ECF itens 1.3 e 1.14 | **CTB-81** | 2 |
| ECF × DCTFWeb/MIT | IRPJ e CSLL apurados × débitos declarados | Manual ECF item 1.14 | CTB-81 | 2 |
| Reinf R-4010 × DARF 1841 × razão | IRRF de dividendos retido, pago e contabilizado | NT EFD-Reinf 02/2026 | CTB-81 | 2 |
| EFD-Contribuições × ECD | Receita e créditos de PIS/Cofins × razão, até 12/2026; saldos credores remanescentes | NT 011/2026 | CTB-81 | 2 |
| Tributos a recolher × declarado | Saldo contábil de cada tributo × DCTFWeb e guias | Prática de encerramento | CTB-81 | 2 |
| Riscos contábeis-fiscais | Caixa com saldo credor; conta com saldo de natureza invertida; contas de sócios sem contrato (mútuo, distribuição disfarçada); AFAC no PL sem condição de capitalização; lucros acumulados positivos em S/A ao fim do exercício (art. 202, §6º); distribuição acima do lucro disponível | Lei 9.430/96, art. 42; DL 1.598/77, art. 60; LSA art. 202 | **CTB-80** | 2 |
| Contas sem movimentação | No período e desde sempre | — | CTB-23 | 2 |

### Frente 9 — Análise e relatórios gerenciais

| Item | CTB | Nível | Observação |
| --- | --- | --- | --- |
| Balancete comparativo e acumulado do exercício | CTB-05, CTB-21 | 2 | Barato: duas chamadas de `apurar_balancete` |
| Análise vertical e horizontal | CTB-19 | 2 | Com pelo menos dois períodos |
| Índices e EBITDA | CTB-20 | 2 | Composição configurável, nunca por nome de conta; EBITDA sempre conciliado com o lucro líquido |
| Gráficos | CTB-22 | 2 | Sempre ao lado da tabela |
| Comparativo de regimes tributários | — | Fora do módulo | Consultoria do Fiscal (DL-067) |

### Frente 10 — Produtividade e integrações

Ordem pela rotina mais cara do escritório, que é **importar e conferir**
(RC-40, RC-41): integração fiscal → contábil (CTB-48, depende do DL-067 e de
CTB-32), extrato e conciliação bancária (CTB-40, CTB-41), histórico e
lançamento padrão (CTB-37, CTB-38), participantes e conciliação de clientes e
fornecedores (CTB-39, CTB-42), importação e exportação (CTB-43, CTB-44),
alteração em massa e regeração (CTB-45 a CTB-47), centro de custo (CTB-33 a
CTB-35), orçamento (CTB-36), consolidação (CTB-59). Todos nível 2, salvo a
integração e a regeração, que gravam lançamento (nível 1).

### Fora do escopo do módulo

| Capacidade do sistema de referência | Por quê |
| --- | --- |
| Conteúdo editorial (novidades legais, mapa de ICMS, tributação por CNAE e NCM, modelos de contrato, perguntas e respostas) | É serviço de conteúdo licenciado, não escrituração. O que o DataLedger precisa é o **registro interno de vigências** com fonte, que já é regra (DE-010) |
| Agenda de obrigações | Pertence à central de obrigações (OBR-02 do plano mestre), compartilhada entre módulos |
| Simulação de contratação (CLT × autônomo × PJ) | Folha e consultoria |
| FCONT, balanço fiscal, DOAR, balancetes setoriais | Extintos ou nicho (CTB-71 a CTB-73) |
| Validação de arquivos estaduais (Livro Eletrônico do DF, SEF de PE) | Fiscal e fora da UF do escritório |

### Catálogo de relatórios

Classe de documento: C conferência, D demonstração, L livro, R arquivo
regulatório ([personalizacao-de-relatorio.md](../projeto/personalizacao-de-relatorio.md)).

| Relatório | Classe | Hoje | Onda |
| --- | --- | --- | --- |
| Diário, Razão, Balancete por período | C | Existe | — |
| Conferência de integridade (seis categorias) | C | Existe | — |
| Balanço Patrimonial | D | Existe, **sem comparativo** | A |
| DRE (mês e acumulado) | D | Existe, **sem comparativo** | A |
| DLPA, DMPL | D | Existe, **sem comparativo** | A |
| DFC direta e indireta | D | Planejada (DL-066) | A |
| DRA, DVA, notas explicativas | D | Não existe | B |
| Carta de responsabilidade | D | Não existe | B |
| Balancete comparativo, contas sem movimento | C | Não existe | A |
| Riscos contábeis-fiscais e pré-validação da ECD | C | Não existe | C |
| Cruzamentos com obrigações | C | Não existe | C |
| ECD, ECF | R | Não existe | C |
| DRE e DFC pela NBC TG 51 | D | Não existe | D |
| Trilha de auditoria consultável | C | Só API | B |
| Análise vertical/horizontal, índices, gráficos | C | Não existe | D |
| Livro numerado com termos (sem ECD) | L | Não existe | D |
| Razão analítico, por centro de custo | C | Não existe | D |

### Roadmap

| Onda | Janela | Objetivo | Entregas, em ordem |
| --- | --- | --- | --- |
| **A** | out–dez/2026 | Poder usar num cliente real e fechar 2026 | Fatia 0 (documentos); DFC (DL-066); escopo de acesso por empresa (CTB-54) e backup verificado (PE-07); origem do lançamento (CTB-32); implantação de saldos (CTB-76); perfil contábil e matriz de demonstrações (CTB-77); comparativo (CTB-78); balancete comparativo e contas sem movimento |
| **B** | jan–mar/2027 | Encerrar o exercício de 2026 e entrar em 2027 | Contas e tratamento de IBS/CBS (CTB-83) **antes do primeiro lançamento de 2027**; sócios e contador (CTB-28, CTB-29, CTB-58); encerramento do exercício com reservas, compensação e destinação (CTB-24); lucros por exercício de apuração (CTB-79); DRA, DVA, notas e carta de responsabilidade; reserva de incentivos (CTB-84) se a carteira tiver; tela da trilha |
| **C** | abr–jul/2027 | Obrigações do ano-calendário 2026 | Plano referencial (CTB-50, CTB-56); correspondência entre exercícios (CTB-55); ECD com pré-validação (CTB-51, CTB-80) até 30/06/2027; ECF do Presumido recuperando a ECD (CTB-52) até 30/07/2027; cruzamentos (CTB-81). **Em paralelo** com o sistema atual (HI-54) |
| **D** | ago/2027–2028 | NBC TG 51 e produtividade | DRE e DFC pela TG 51 com reapresentação de 2026 (CTB-82), a tempo das demonstrações de 2027 no 1º trimestre de 2028; integração fiscal → contábil (CTB-48); extrato e conciliação; histórico e lançamento padrão; análise; Lucro Real com Lalur e subcontas correlatas (CTB-75), conforme a carteira |

**Por que esta ordem e não a da paridade:** a paridade ordena por dependência
técnica; este roadmap ordena pelo **calendário do escritório**. O exercício de
2026 fecha em dezembro, a CBS começa em janeiro, a ECD vence em junho — e um
produto que entrega DVA antes de conseguir implantar o saldo de um cliente
novo não é usado.

### Migração do sistema atual e validação em paralelo

1. **Implantação por saldo**, não por histórico: balanço de abertura aprovado,
   lucros acumulados separados por exercício de apuração (exigência que a Lei
   15.270 criou), conferido contra o balanço do sistema atual (CTB-76).
2. **Mês em paralelo**: o mesmo mês lançado nos dois sistemas, e balancete,
   DRE e Balanço comparados linha a linha antes de qualquer documento sair só
   do DataLedger.
3. **ECD do AC 2026 em paralelo** (HI-54): gerada e validada no programa
   oficial pelo DataLedger, **transmitida** pelo sistema atual; a primeira
   transmissão própria fica para o AC 2027, salvo ordem diferente do Fred.

### Integração com os módulos vizinhos

| Vizinho | Quem é dono de quê |
| --- | --- |
| Fiscal ([DL-067](DL-067-plano-do-modulo-fiscal.md)) | Fiscal é dono da classificação tributária e das apurações (inclusive Presumido com LC 224, CBS e IBS); a Contabilidade recebe lançamentos com origem (CTB-48) e confere (CTB-81). A política contábil do IBS/CBS (CTB-83) é da Contabilidade |
| Lalur ([paridade/lalur.md](../projeto/paridade/lalur.md)) | Lalur é dono das adições, exclusões e Parte B; recebe o resultado contábil antes dos tributos e devolve a provisão de IRPJ e CSLL |
| Folha | Dona da remuneração e dos encargos; integra depois, sem bloquear o primeiro ciclo (CON-08) |
| Patrimônio | Dono da depreciação; diferenças fiscais vão ao Lalur |
| Livro-caixa PF | Adjacente (CTB-63); não é partida dobrada |

### Decisões que dependem do Fred

Uma de cada vez, na ordem em que bloqueiam. Cada uma com a recomendação.

1. **Comparativo com o exercício anterior (revê RC-119; PE-79).** O art. 176, §1º,
   da LSA o exige na publicação da S/A, e a norma de apresentação exige
   informação comparativa. **Recomendação:** obrigatório em toda demonstração
   anual, e opcional nas mensais.
2. **Escopo de acesso por empresa antes de dado real (PE-36).**
   **Recomendação:** sim, na Onda A, como nível 1.
3. **Método direto da DFC** (F0-3; PE-82): aceitar o fluxo tirado das contas de caixa
   com o limite que a DL-066 declara, ou esperar a conciliação bancária.
   **Recomendação:** aceitar, com o lançamento de ajuste que passe pelo caixa
   marcado para fora do fluxo.
4. **Perfil da carteira (PE-77):** quantas micro, pequenas e médias; quantas
   S/A; quantas no Lucro Real; quem recebe subvenção. Decide CTB-75, CTB-84 e a
   ordem da Onda D.
5. **ECD do AC 2026 em paralelo (HI-54).** **Recomendação:** paralelo, com
   transmissão pelo sistema atual.
6. **Política do teste de IBS/CBS de 2026 (PE-76):** reconhecer ou não o
   passivo do teste, por cliente. **Recomendação:** não reconhecer quando há
   dispensa de recolhimento (art. 348, §1º), divulgando em nota — mas é
   julgamento do contador por entidade, como diz a orientação do CFC.
7. **Adoção antecipada da NBC TG 51 (PE-80):** a norma não traz cláusula
   expressa de antecipação. **Recomendação:** manter a opção como decisão de
   produto, registrada como tal, e não como exigência normativa.
8. **Mecanismo da compensação (PE-38):** todo mês, no encerramento anual, ou
   lançamento à mão.

## Catálogo de requisitos

Identificadores `MC-` são deste plano; cada um vira critério de aceite da DL
que o implementar.

### Fundamentos e segurança

| ID | Requisito | Origem |
| --- | --- | --- |
| MC-SEG-01 | Usuário sem vínculo com a empresa recebe 403 ou 404 em toda rota, relatório, exportação e arquivo daquela empresa | CTB-54, PE-36 |
| MC-SEG-02 | Restauração de backup executada e medida antes do primeiro cliente real | PE-07 |
| MC-LIV-01 | Todo lançamento tem origem; lançamento automático tem documento de origem navegável nos dois sentidos | CTB-32 |
| MC-LIV-02 | Implantação de saldos fecha com o balanço aprovado, inclusive retificadoras e resultado anterior, e separa lucros acumulados por exercício de apuração | CTB-76 |
| MC-LIV-03 | Rascunho não entra no saldo oficial; efetivar duas vezes não duplica | BL-10 |

### Cadastros e perfil

| ID | Requisito | Origem |
| --- | --- | --- |
| MC-CAD-01 | Sócio com participação e vigência sem sobreposição; a mesma pessoa pode ter mais de um papel | CTB-28, CTB-58 |
| MC-CAD-02 | Demonstração formal e ECD vetadas sem contador responsável vigente e sem signatário | CTB-29; CC art. 1.184, §2º |
| MC-CAD-03 | Perfil contábil por exercício; porte calculado pela receita bruta do exercício anterior | CTB-77; ITG 1000 itens 5 e 11 |

### Demonstrações

| ID | Requisito | Origem |
| --- | --- | --- |
| MC-DEM-01 | O produto lista o conjunto exigido pelo perfil e veta a emissão do conjunto incompleto, nomeando o que falta | CTB-77; HI-51 |
| MC-DEM-02 | Toda demonstração anual traz o exercício anterior pelo mesmo critério; conta sem saldo anterior aparece com zero declarado | CTB-78; LSA art. 176, §1º; HI-52 |
| MC-DEM-03 | Exercício iniciado a partir de 01/01/2027 sai pela NBC TG 51; o comparativo de 2026 é reapresentado e conciliado por rubrica | CTB-82; TG 51 apêndice C |
| MC-DEM-04 | IBS e CBS não compõem a receita bruta da DRE; crédito vedado vai a custo ou despesa | CTB-83; HI-53 |
| MC-DEM-05 | DRA, DVA e DFC conciliam com DRE e Balanço; a DVA fecha em si mesma | CTB-15 a CTB-17 |
| MC-DEM-06 | Nota explicativa referenciada na demonstração existe; microentidade traz as declarações do item 3.2 da TG 1002 | CTB-18 |

### Encerramento e PL

| ID | Requisito | Origem |
| --- | --- | --- |
| MC-ENC-01 | Encerramento do exercício reproduzível, sem duplicação, com saldos antes do encerramento preservados | CTB-24 |
| MC-ENC-02 | Absorção de prejuízo na ordem do art. 189, parágrafo único, da LSA | LSA (Planalto, 05/10/2026) |
| MC-ENC-03 | Reserva legal calculada pelo art. 193, com o teto e a dispensa | LSA art. 193 |
| MC-ENC-04 | Cada distribuição aponta o exercício de apuração do lucro e a deliberação datada; lucro até 2025 aprovado até 31/12/2025 fica marcado para a transição | CTB-79; Lei 15.270/2025 |
| MC-ENC-05 | Reserva de incentivos fiscais só é usada nos casos do art. 16 da Lei 14.789/2023, com recomposição controlada | CTB-84 |

### Obrigações e conferência

| ID | Requisito | Origem |
| --- | --- | --- |
| MC-OBR-01 | ECD gerada pelo leiaute vigente do ano-calendário, validada no programa oficial antes de ser oferecida para transmissão | CTB-51; IN RFB 2.003/2021 |
| MC-OBR-02 | ECD substituta exige termo de verificação e sinaliza a ECF retificadora | IN 2.003 art. 8º; manual ECF item 1.14 |
| MC-OBR-03 | ECF recupera a ECD ativa; o produto não recalcula a mesma base por outro caminho | CTB-52; decisão A7 |
| MC-OBR-04 | Transmissão só por usuário autorizado, com aprovação vinculada ao conteúdo exato; mudança de conteúdo invalida a aprovação | AGENTS.md §11 |
| MC-CON-01 | Cada cruzamento nomeia as duas fontes, o valor de cada uma e a diferença; nunca "há divergência" sem número | CTB-81 |
| MC-CON-02 | Conferência de riscos aponta conta e lançamento, sem bloquear o lançamento | CTB-80 |

## Pendências e fontes

### Pontos não confirmados

| Ponto | Situação |
| --- | --- |
| Número de Resolução CFC da NBC TG 51 | Não encontrado: o ato se chama "NBC TG 51, de 13/11/2025". O CFC noticia o DOU de 22/12/2025, e a própria lista do CFC mostra 25/02/2026 |
| Conteúdo da Revisão CPC 28 sobre a DFC (ponto de partida no lucro operacional; classificação de juros e dividendos) | Só fonte secundária |
| Retificação da NBC TG 03 (R3), DOU de 26/05/2026; Revisão NBC 33, DOU de 17/04/2026 | Só fonte secundária |
| Adoção antecipada da NBC TG 51 | Não há cláusula expressa (PE-80) |
| NBC TG 1000 (R2), terceira edição do IFRS for SMEs | Não adotada no Brasil até 05/10/2026 |
| OCPC ou CTG sobre IBS/CBS | Não encontrado; só a Orientação Técnica CFC nº 1/2026 |
| Leiaute da ECD para o AC 2026 | Não publicado; o leiaute 9 vale "enquanto não editado novo leiaute" (PE-81) |
| Regulamento das demonstrações do art. 16-B, §4º, da Lei 15.270/2025 | Não encontrado (PE-78) |
| IN RFB 2.299/2025 (dividendos) e IN RFB 2.319/2026 (adicional da CSLL) | Só fonte secundária |
| Norma do CFC sobre assinatura de demonstrações | Não encontrada; a exigência vem do CC art. 1.184, §2º, da ITG 2000 e da ITG 1000 |
| Item da norma de apresentação que exige comparativo | LSA art. 176, §1º, confirmado; o item da TG 26 (R5) e o da TG 51 ficam a conferir no PDF antes do código |

### Fontes

Consultadas em 05/10/2026. Situação: **C** confirmada no texto oficial; **S**
só fonte secundária.

| Fonte | Ato | Situação |
| --- | --- | --- |
| CFC, PDF oficial | NBC TG 51, de 13/11/2025 (itens 47, 69 a 81, 117 a 125, apêndice C) | C |
| CFC | NBC TG 1001 e NBC TG 1002, de 18/11/2021; ITG 1000, de 15/12/2022; NBC TG 1000 (R1) | C |
| CFC | ITG 2000 (R1), itens 10, 12, 13, 17, 31 e 32; CTG 2001 (R3) | C (CTG só título) |
| CFC | NBC TG 09 (R1), DOU de 08/03/2024; Revisão NBC 26 | C |
| CFC | Orientação Técnica CFC nº 1/2026 (IBS e CBS), itens 3 a 31 | C |
| CFC | Resolução CFC 1.777/2025 (DECORE) | C |
| CVM | Resolução CVM 244/2026 (sustentabilidade passa a voluntária) | C |
| Planalto | Lei 6.404/76, arts. 176, 189, 193, 195-A e 202 (compilado) | C |
| Planalto | Código Civil, arts. 1.179 a 1.195; LC 123/2006, arts. 26 e 27; DL 9.295/46, arts. 12, 25 e 26 | C |
| Planalto | Lei 15.270/2025; LC 224/2025 e Decreto 12.808/2025; Lei 14.789/2023 | C |
| Planalto | LC 214/2025, arts. 343 a 348, 542 e 544; LC 227/2026; Decreto 12.955/2026, arts. 44 a 46 | C |
| RFB, portal SPED | Manual da ECD, leiaute 9, maio/2026 (IN RFB 2.003/2021 transcrita) | C |
| RFB, portal SPED | Manual da ECF, leiaute 12, abril/2026 (IN RFB 2.004/2021 transcrita) | C |
| RFB | Manual da DCTFWeb (jan/2025) e Perguntas e Respostas (23/09/2025); Perguntas e Respostas da DIRF 2025 e de lucros e dividendos (19/12/2025) | C |
| RFB, portal SPED | Manual da EFD-Reinf 2.1.2.1; NT EFD-Reinf 02/2026; NT EFD-Contribuições 011/2026 | C |
| Simples Nacional | Notícia de 09/12/2025 sobre DEFIS e Resolução CGSN 183/2025 | C |
| Sistema de referência | Manuais de Contabilidade, Lalur, Auditoria, Auditor Fiscal e Conteúdo Contábil Tributário (2018) — **rotina, nunca norma**; não versionados | Rotina |
