# DL-048 — Contabilidade anual: estrutura de demonstração ligada à conta (CTB-12 a CTB-17)

**Estado:** em desenvolvimento
**Nível de risco:** 1 — são demonstrações contábeis entregues ao cliente (dinheiro, livro e documento).
**Origem:** ordem direta do Fred em 2026-09-28, escolhendo a **opção A** do mapa de
paridade ([DL-047](DL-047-mapa-de-paridade-funcional.md)) — fechar a Contabilidade anual
antes de abrir o Fiscal.
**Itens do plano de paridade:** [contabilidade.md](../projeto/paridade/contabilidade.md),
CTB-12 a CTB-17.

## Decisões do Fred (2026-09-28, registradas antes de qualquer código)

| # | Decisão | Consequência |
| --- | --- | --- |
| 1 | **DLPA isolada E DMPL** — as duas demonstrações saem como documentos próprios, cada uma com sua tela. | CTB-13 (DLPA) e CTB-14 (DMPL) são entregas separadas, não uma derivada da outra. A DLPA deixa de ser "recorte da DMPL" e ganha estrutura própria. |
| 2 | **Fonte normativa confirmada pelo agente** antes de codificar. | A NBC TG 26 / Lei 6.404/76 deve ser lida em Planalto/CFC, a fonte registrada em [requisitos.md](../projeto/requisitos.md) com **data de consulta**, e só então o código nasce. Nenhum número ou linha de demonstração vira constante sem isso (AGENTS.md §10). |

## Respostas do Fred (2026-09-28) — desbloqueiam CTB-13 a CTB-17

### RC-137 · Tipos de reserva (define colunas da DMPL e linhas da DLPA)

**Reservas de LUCROS** — constituídas a partir do lucro líquido:

| Reserva | Origem / critério |
| --- | --- |
| **Legal** | Obrigatória por lei (Lei 6.404/76 art. 193) — já confirmada na fonte oficial |
| **Estatutária** | Regras do próprio estatuto: finalidade, critério de cálculo e limite máximo |
| **Para Contingências** | Compensar perda provável em exercício futuro (perda esperada, processo judicial iminente) — não distribuir dividendos que farão falta depois |
| **De Incentivos Fiscais** | Parcela do lucro decorrente de doações ou subvenções governamentais para investimento (isenções estaduais e federais) |
| **De Retenção de Lucros** (ou para Expansão) | Projeto de investimento ou orçamento de capital previamente aprovado pela assembleia — retém o lucro para financiar crescimento |
| **De Lucros a Realizar** | Lucro contábil sem realização financeira (venda a prazo de longo prazo, equivalência patrimonial) — adia o pagamento de dividendos obrigatórios sobre lucro ainda não realizado |

**Reservas de CAPITAL** — **não** vêm do lucro operacional, entram direto no PL e **não transitam pela DLPA** (não passam pelo lucro líquido do exercício):

| Reserva | Origem |
| --- | --- |
| **Ágio na Emissão de Ações** | Valor pago acima do valor nominal das ações emitidas |
| **Alienação de Partes Beneficiárias / Bônus de Subscrição** | Valores recebidos na venda desses títulos mobiliários |

**Estrutura de apresentação, definida pelo Fred:**

| | Como aparece | Função técnica |
| --- | --- | --- |
| **DMPL** | Cada tipo de reserva tem **coluna própria** (ex.: "Reserva Legal", "Reserva Estatutária") | Mostra saldo inicial, mutações (aumentos/reduções) e saldo final de cada conta do PL |
| **DLPA** | Aparecem como **linhas de destinação do lucro** (ex.: "(-) Transferência para Reserva Estatutária") | Demonstam como o saldo de Lucros Acumulados foi distribuído para abastecer as colunas de reservas do PL |

⚠️ **Consequência de modelagem:** o "tipo de evento" da DLPA nasce da **destinação** e a coluna da DMPL é a **contrapartida** — são o mesmo fato visto por dois lados. Implementar com a MESMA leitura estruturada de eventos, que é justamente o que mitiga o risco de "duas lógicas divergentes" apontado pelo plano de paridade.

### RC-138 · DFC — **os dois métodos** (direto e indireto)

⚠️ O método **direto** depende de extrato/conciliação bancária (**CTB-40/CTB-41**), que **não existe** e está fora desta etapa. Entregar o **indireto** agora e abrir CTB-40/41 como dependência declarada para o direto. Nunca inferir "é banco, então é caixa" — lançamento de ajuste, provisão e reclassificação passa pela conta banco sem ser fluxo real.

### RC-139 · ORA e DVA — **exige os dois**

CTB-16 (DRA) e CTB-17 (DVA) **entram na etapa**, não ficam em espera. DVA é obrigatória para companhia aberta (Lei 6.404/76 art. 176, V) e a carteira tem quem exija.

### RC-140 · Compensação de lucros e prejuízos acumulados — **SIM, o escritório compensa**

⚠️ **Falta um detalhe antes de implementar a linha:** a resposta confirma que a compensação existe, mas não diz **como** — a PE-38 pergunta se é todo mês, no encerramento anual, ou lançamento à mão. Esse detalhe define quando a linha aparece na DLPA e como se liga ao CTB-24 (encerramento do exercício). **Confirmar o mecanismo antes**; em caso de dúvida, entregar a linha declarada como pendência em vez de presumir (regra do CTB-12).

## Por que a ordem é esta

O mapa de paridade diz que a Onda 1 é a **estrutura de demonstração ligada à conta**:
DRE, DLPA, DMPL, DFC e DVA não são relatórios com fórmula fixa — são estruturas de
grupos, e a conta é **vinculada** a esses grupos. O DataLedger já aplica isso para o
Balanço (`classificacao_patrimonial`, CTB-09) e para a DRE (`classificacao_dre`,
CTB-10). CTB-12 é repetir esse padrão; CTB-13 a CTB-17 são cada um com seu próprio
enum de linhas.

## Etapas

### 1. CTB-12 — Estrutura de demonstração ligada à conta (base)

O mecanismo comum reaproveitado pelos itens seguintes: campo fixo na conta (como
`classificacao_patrimonial` e `classificacao_dre` já são), apuração que soma pela
estrutura, e tela que **declara** o que falta classificar em vez de presumir.

- **Regra que vira teste:** nenhuma conta é classificada por inferência de código ou
  nome; a apuração relata pendência em vez de presumir.
- **Não copiar:** a estrutura totalmente configurável por empresa (do sistema de
  referência) **substitui** este padrão se um dia for pedida — não conviver com os dois
  (AGENTS.md §8).
- **Critério de aceite:** cada item seguinte define os seus; o comum é "nenhuma conta
  classificada sem ação explícita do usuário, e a apuração sempre relata o que falta".

### 2. CTB-13 — DLPA (Demonstração dos Lucros ou Prejuízos Acumulados)

Movimentação da conta de lucros/prejuízos acumulados no período: saldo inicial +
lucro do exercício − destinações (reservas, dividendos) = saldo final.

- **Fonte normativa:** confirmar a NBC TG 26 item 106 e a Lei 6.404/76 na fonte
  oficial **antes** de escrever o enum de linhas. Registrar em `requisitos.md`.
- **Dados:** a demonstração é uma **leitura estruturada** dos lançamentos já
  existentes (o zeramento gera o "lucro do período") — não um modelo de armazenamento
  novo, mesmo espírito da DRE.
- **Regra que vira teste:** saldo final = saldo inicial + lucro do exercício −
  destinações; cada linha precisa vir de lançamento identificável.
- ⚠️ **Não implementar o cálculo da reserva legal** sem conferir a Lei 6.404/76
  art. 193 na fonte oficial e validar com o Fred (limite de 20% do capital social,
  5% do lucro líquido).
- **Critério de aceite:** saldo final da DLPA bate com o saldo da conta de
  lucros/prejuízos acumulados no Balanço da mesma data; emissão recusada enquanto
  houver movimento não classificado (mesmo padrão de CTB-09/CTB-10).
- **Classe do documento:** demonstração — identificação obrigatória em **cada página**
  (NBC TG 26 item 52).

### 3. CTB-14 — DMPL (Demonstração das Mutações do Patrimônio Líquido)

Uma coluna por conta do PL, uma linha por tipo de evento (saldo inicial, aumento de
capital, lucro do exercício, constituição de reserva, distribuição, saldo final).

- **Critério de aceite:** o total da DMPL bate com o Patrimônio Líquido do Balanço da
  mesma data. É a conciliação que impede a demonstração de "fechar sozinha" errada.
- **Classe do documento:** demonstração.

### 4. CTB-15 — DFC (Demonstração dos Fluxos de Caixa)

Direto e indireto, por atividade.

- ⚠️ **O método direto depende de extrato/conciliação bancária (CTB-40/CTB-41), que
  não existem.** Conferir no item o que é viável agora; o restante entra como
  limitação declarada, nunca como número inventado.

### 5. CTB-16 — DRA (Demonstração do Resultado Abrangente)

Lucro líquido + outros resultados abrangentes.

### 6. CTB-17 — DVA (Demonstração do Valor Adicionado)

Riqueza gerada e distribuída; fecha em si mesma. É o item de menor urgência contábil
da onda.

## Restrições que valem em toda a etapa (AGENTS.md)

- Dinheiro em `Decimal`, nunca float; escala e arredondamento explícitos.
- Demonstração é documento **classe demonstração**: o bloco de identificação do
  emitente é obrigação (NBC TG 26 item 51) e repete em cada página (item 52).
- Nenhuma linha de demonstração nasce de inferência — o que não está classificado é
  **declarado como pendência**, e a emissão é recusada.
- Autorização no servidor; isolamento por empresa e escritório; trilha de auditoria.
- Teste de regra contábil não se corta (DE-063); caso de referência calculado à mão
  para cada demonstração.

## Critérios de aceite da etapa inteira

1. Cada demonstração tem apuração determinística, conciliável com os lançamentos.
2. As conciliações cruzadas batem: DLPA ↔ Balanço, DMPL ↔ PL do Balanço,
   DRA ↔ DRE, DVA fecha em si mesma.
3. Emissão recusada com a lista do que falta classificar (nunca esconde).
4. Identificação do emitente medida no navegador pela CI (job `Medir identificação do
   emitente no navegador`).
5. Isolamento entre empresas testado nos dois sentidos.
6. Casos de referência com valores calculados à mão, aprovados pelo Fred.

## Bloqueio antes do código

A fonte normativa da DLPA e da DMPL precisa ser confirmada e registrada em
`requisitos.md` **antes** do primeiro commit funcional. É a primeira tarefa desta
etapa.

✅ **Cumprida em 28/09/2026** — ver "Fontes normativas das demonstrações
contábeis — DL-048" em [requisitos.md](../projeto/requisitos.md), com a
descoberta de que a base da DLPA é a Lei 6.404/76 (art. 176, II e art. 186),
não a NBC TG 26 item 106 nem a Lei 11.941/2009.

## Fatia CTB-12 + CTB-13 (DLPA) — codada e testada em 2026-09-28

Branch `feat/dl-048-dlpa`. **Nível 1:** o que falta para a etapa fechar, nesta
ordem: (a) **auditoria independente** (obrigatória — não foi executada nesta
sessão); (b) correção da auditoria e reconferência; (c) revisão e merge do
**PR #58** (aberto contra `docs/dl-048-plano`, encadeado no PR #57 do plano —
mesclar o #57 primeiro; depois disso o GitHub reaponta a base quando a
branch do plano for apagada). ✅ **CI do #58 VERDE** no commit `5edb3e7`
(Lint e testes, Medir identificação do emitente no navegador, Regras do
projeto e Validar documentação). Enquanto (a)–(c) não acontecem, a etapa
NÃO é "integrada".

### Decisões de implementação (registradas para revisão; todas reversíveis)

| # | Decisão | Por quê |
| --- | --- | --- |
| D1 | **Conta sujeito = `classificacao_dlpa = "lucros_ou_prejuizos_acumulados"`; podem ser VÁRIAS contas** (o caso "Lucros Acumulados" + "(-) Prejuízos Acumulados" em plano separado). | CTB-12 manda campo fixo na conta (molde `classificacao_patrimonial`/`classificacao_dre`), não parâmetro do zeramento: a demonstração não depende de quem configurou o zeramento, e as duas contas somam pelo mesmo lado (D2). |
| D2 | **Efeito de um item sobre o resultado acumulado = crédito − débito, independente da natureza cadastrada.** | É idêntico para a credora (cr − db) e para a retificadora devedora (o −(db − cr) do PL é cr − db): as duas formas da conta existir convergem sem regra de translação. |
| D3 | **A linha vem da `classificacao_dlpa` da CONTRAPARTIDA do lançamento** — sem classificação, a apuração declara pendência e a emissão é recusada. | "Nenhuma conta classificada por inferência" (CTB-12): a contrapartida é quem diz que evento moveu os lucros (zeramento, reserva, dividendo…); o produto não adivinha. |
| D4 | **A DIREÇÃO do movimento decide reversão (art. 186, II) × transferência (art. 186, III)** para a MESMA conta de reserva. | O cadastro só diz "é reserva"; reduzir lucros é destinação, aumentar é reversão. Guarda derivada de uma propriedade do movimento, não de lista (AGENTS.md §8). |
| D5 | **Sem herança: a classificação vale para a conta EXATA que participa do lançamento** (diferente da DRE). | Subconta sem classificação vira pendência nomeada, com link para classificar — nunca valor presumido do ancestral. Se a herança for pedida, ela SUBSTITUI esta regra (AGENTS.md §8). |
| D6 | **Período = EXERCÍCIO (01/01, ano civil, HI-28) até a competência pedida**; saldo inicial em 31/12 do ano anterior; navegação por mês, mesma gramática da DRE. | A DLPA é demonstração do exercício; o seletor de mês controla "até quando", nunca um período livre. |
| D7 | **A compensação de lucros/prejuízos (PE-38/HI-26, ainda com o Fred) não é presumida.** Lançamento entre as DUAS contas sujeito tem efeito líquido ZERO e some da demonstração. | A leitura é neutra ao mecanismo que o escritório venha a usar: não inventa transferência que não foi lançada, nem esconde a que foi. |
| D8 | **Tela primeiro, API depois.** Nesta fatia: `dlpa` e `conta_classificacao_dlpa` (2 rotas web); `DlpaView` (GET) + `ContaClassificacaoDlpaView` (PATCH) + `ContaSerializer.classificacao_dlpa` são a fatia seguinte. | Mantém o escopo da fatia revisável; as contagens de rota de `test_dl038_recusa_livro_caixa.py` já registram 21 web / 15 API com o histórico. |
| D9 | **Conciliação DLPA ↔ Balanço por caminho independente**: a apuração soma `ItemLancamento` por conta exata; a conferência usa o `saldo` do motor do Balancete (`apurar_saldos`) em `data_fim`, credora `+`/devedora `−`. Conta sujeito deve ser FOLHA. | É a comparação entre dois caminhos que prova o número (critério de aceite); filhas movimentadas geram diferença e vetam, corretamente. |

### Critérios cobertos e evidência (2026-09-28)

Testes novos: `apps/contabilidade/tests/test_dl048_dlpa.py` — **39 testes**:
caso de referência do plano (13.750,00), identidade
`saldo inicial + Σ linhas = saldo final`, conciliação com o Balanço, ordem dos
incisos do art. 186, rastreabilidade (cada linha com seus lançamentos),
estorno, compensação neutra, isolamento, as três pendências (sem conta sujeito;
movimento sem classificação; classificação fora do enum) e o aviso de
resultado não zerado, cadeia `zerar_resultado` → linha da DLPA, permissão 403,
isolamento 404, veto com link só para quem escritura, identificação do item 51
na página emitida, hub/menu/plano de contas e as duas telas de classificação
com trilha.

Guardas existentes re-executadas nesta sessão: `test_dl019_varredura_de_
restricoes` (constraint `ck_conta_classificacao_dlpa_nao_vazia` registrada),
`test_dl038_recusa_livro_caixa` (21/15), `test_documentacao_do_estado`,
`test_dl024_atalhos_e_acessibilidade` (cobertura das duas rotas novas).
`ruff check`, `ruff format --check`, `manage.py check` e
`makemigrations --check` aprovados.

⚠️ **Não executado nesta sessão:** a medição no navegador real
(`scripts/medir_identificacao_do_emitente.py` — a DLPA entrou no piso de
classe 2 e o cenário de medição semeia a conta sujeito) e o
`validate-docs.ps1`; os dois rodam na CI.

### Limitações declaradas da fatia

- API sem a DLPA (D8) — paridade é a próxima fatia.
- Sem herança de classificação (D5); conta sujeito deve ser folha (D9).
- Linha "Correção monetária do saldo inicial" existe e sai zerada: é conteúdo
  do art. 186, I — a norma não a revogou do rol, e não há movimento que a
  alimente hoje.
- Rótulo do enum "Reserva de contingências" (RC-137 escreve "Para
  Contingências") — mesma reserva; a frase invertida não cabe no título
  "Transferência para reserva …" sem soar errado.
- Dividendos só aparecem na DLPA quando o lançamento movimenta a conta
  sujeito; escrituração que distribui sem tocar os lucros acumulados não gera
  a linha (o saldo continua conciliado — a apuração cobre todo o movimento da
  conta sujeito).
