# DL-045 — Demonstração do Resultado do Exercício (DRE)

**Demanda:** fila aprovada pelo Fred (CON-12 do plano mestre; próximo item depois
da DL-043). Decisões dele em 2026-09-26, ao aceitar a recomendação: *"Pode
seguir com a sua recomendação"* — RC-118, RC-119 e RC-120.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — demonstração contábil entregue ao cliente.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** worktree `dl045-dre`, integrada por PR depois da DL-043 (PR #49).

## Problema

O escritório não consegue emitir a DRE pelo produto. A camada de saldos (DL-032)
declara por escrito que não serve para a DRE (`apurar_saldos`, docstring): a DRE
se constrói pelo **movimento** do período, não pelo saldo de uma data. E há um
risco novo, medido no código pela pesquisa: o zeramento (DL-043) é gravado no
**último dia do próprio período**. Uma DRE de março emitida depois de zerar
março somaria o lançamento de zeramento e sairia zerada. A DRE precisa excluir
os lançamentos de zeramento.

## Fontes

- **Norma — Lei 6.404/76, art. 187 e art. 175**, lidos no Planalto e na Câmara
  em 2026-09-26, texto idêntico (PE-70).
- **NBC TG 26 (R5) item 82, NBC TG 1000 (R1) item 5.7 e ITG 1000 (2022)**, lidos
  nos PDFs do CFC em 2026-09-26: fundamentam a posição do resultado financeiro e
  a linha de equivalência patrimonial (HI-29).
- **Rotina — manual do sistema de referência:** DRE por estrutura de grupos
  associada a contas, emissão por período livre, uma única linha "antes do IR".
  Usado como rotina, nunca como norma.

## Fatia 1 — Linha da DRE na conta (RC-118)

- Campo de classificação na conta de resultado, no molde do circulante × não
  circulante da DL-033: uma das linhas do art. 187 —
  receita bruta; deduções da receita (impostos, devoluções e abatimentos);
  custo (CMV/CPV/CSP); despesas com vendas; despesas gerais e administrativas;
  receitas financeiras; despesas financeiras; outras despesas operacionais;
  outras receitas; outras despesas; resultado de equivalência patrimonial;
  provisão para IRPJ e CSLL; participações (HI-29).
- Só conta de resultado recebe a classificação; conta patrimonial com ela é
  recusada. Herança pela hierarquia no mesmo desenho da DL-033 (o
  desenvolvedor confirma o precedente e registra).
- Conta retificadora dentro do grupo segue o RC-61 (ex.: devoluções dentro das
  deduções).
- API e plano de contas; a tela entra na fatia 3.

## Fatia 2 — Apuração

- Serviço de apuração da DRE para `[inicio, fim]` pelo **movimento** do período
  (`apurar_balancete` ou consulta própria), **excluindo** os lançamentos de
  zeramento (prefixo reservado `zeramento:`, DL-043).
- Duas colunas (RC-119): **mês** e **acumulado do exercício** (do início do
  exercício até o fim do mês). Exercício = ano civil (HI-28).
- Subtotais: receita líquida, lucro bruto, **resultado antes das receitas e
  despesas financeiras**, resultado financeiro, resultado antes dos tributos
  sobre o lucro, lucro ou prejuízo líquido (NBC TG 26 item 82 e NBC TG 1000
  item 5.7, HI-29).
- Valores em `Decimal`, conciliáveis: o lucro líquido da DRE do período é igual
  ao resultado que o zeramento do mesmo período transfere (etapa 2), e igual à
  soma das contas de resultado no Balancete sem os lançamentos de zeramento.
- Isolamento por empresa e escritório; leitura consistente sob snapshot, como o
  Balanço (DE-067).

## Fatia 3 — Emissão (demonstração formal, RC-120)

- Tela e documento imprimível na classe 2 de
  [personalizacao-de-relatorio.md](../projeto/personalizacao-de-relatorio.md),
  como o Balanço (DL-034): identificação do emitente em toda página, critério de
  apuração impresso.
- **Emissão recusada** enquanto houver conta de resultado analítica com
  movimento no período **sem classificação** — a tela lista as pendências, no
  mesmo desenho do veto do Balanço.
- Tela no padrão visual da DL-044; entra pelo hub de Relatórios.

## Critérios de aceite

1. Classificação: só em conta de resultado; recusa com mensagem; herança
   documentada e testada.
2. Casos de referência calculados à mão: lucro, prejuízo, só receita, com
   deduções e devoluções (retificadora), com resultado financeiro negativo,
   com IRPJ/CSLL, centavos.
3. **DRE de período já zerado é igual à DRE antes do zeramento** (o lançamento
   de zeramento não entra), no mês e no acumulado com vários zeramentos
   mensais.
4. Conciliação: lucro líquido da DRE = resultado transferido pelo zeramento do
   mesmo período; soma de débitos e créditos conferida.
5. Acumulado do exercício = soma das DREs mensais do exercício.
6. Emissão recusada com conta sem classificação, listando as contas; nada
   emitido.
7. Documento emitido com identificação do emitente em toda página, medido no
   navegador pelo job de CI existente.
8. Autorização no servidor; isolamento entre empresas e escritórios em todas
   as portas.
9. Suíte completa, lint, formatação, `check`, `makemigrations --check`,
   migração em banco vazio e em SQLite.

## Hipóteses e pendências

- **HI-28:** exercício social = ano civil. Reversível; o estatuto pode fixar
  outra data (Lei 6.404, art. 175).
- **HI-29 (revista depois da PE-70):** resultado financeiro destacado e
  equivalência patrimonial em linha própria, como a NBC TG 26, a NBC TG 1000 e
  os modelos da ITG 1000. A letra do art. 187, III embute o financeiro no
  operacional; o Fred confirma a apresentação.
- **PE-70 respondida** por fonte primária em 2026-09-26 (ver requisitos.md).
- Comparativo com o exercício anterior: fora desta etapa.
- Validação profissional da estrutura e dos casos de referência é do Fred.
