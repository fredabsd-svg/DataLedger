# DL-048 — Contabilidade anual: estrutura de demonstração ligada à conta (CTB-12 a CTB-17)

**Estado:** planejada
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
