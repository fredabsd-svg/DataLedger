# DL-046 — Livro-caixa e carnê-leão do cliente pessoa física

**Demanda:** fila aprovada pelo Fred (RC-113: o escritório faz livro-caixa e
carnê-leão para os clientes pessoa física). Respostas dele em 2026-09-26
(RC-127 a RC-129).
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — cálculo de imposto e livro entregue ao cliente.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** worktree `dl046-livro-caixa`, integrada por PR depois da DL-044
(PR #50) e da DL-045.

## Problema

O cliente pessoa física já existe no cadastro, em modo livro-caixa (DL-038),
e o produto recusa a contabilidade por partidas dobradas para ele. Mas não há
onde escriturar o livro-caixa nem apurar o carnê-leão.

## Fontes (consultadas em 2026-09-26)

- **Norma — RIR/2018 (Decreto 9.580/2018)**, texto consolidado na Câmara dos
  Deputados (o Planalto não respondeu):
  - **arts. 68 e 69 — livro-caixa:** quem escritura (trabalhador não
    assalariado, titular de serviço notarial e de registro, leiloeiro); o que
    se deduz (remuneração e encargos de empregado, emolumentos pagos a
    terceiros, despesas de custeio necessárias à receita); o que não se deduz
    (depreciação, arrendamento, locomoção — salvo representante comercial
    autônomo); a dedução não excede a receita do mês e o excesso passa aos
    meses seguintes **até dezembro**, sem ir ao ano seguinte; escrituração com
    documentação idônea; o livro **independe de registro**.
  - **arts. 118 a 125 — recolhimento mensal obrigatório (carnê-leão):** quem
    recolhe, base de cálculo (art. 121: rendimentos menos as deduções dos
    arts. 67, 68 e 70 a 72; a do livro-caixa só contra rendimento do trabalho
    não assalariado), tabela mensal (art. 122) e prazo (art. 123).
- **Receita Federal (gov.br):** tabela progressiva mensal de 2026 (Lei
  15.191/2025); redução da Lei 15.270/2025 a partir de 01/2026; pagamento até o
  último dia útil do mês seguinte, DARF código 0190, valor abaixo de R$ 10,00
  acumula para o mês seguinte.
- **Receita Federal — leiaute público de importação do Carnê-Leão Web**
  (arquivo `escrituracao-carne-leao.zip`, instruções de 2025): CSV com `;`,
  datas `DD/MM/AAAA`, valores com vírgula, rendimentos por código
  (`R01.xxx.xxx`) e pagamentos por código (`P10` dedutível, `P11` não
  dedutível, `P20` imposto pago, pensão, previdência).
- **Rotina — manual do sistema de referência (Contabilidade e Folha):**
  carnê-leão habilitado só para inscrição diferente de CNPJ em modo
  livro-caixa; grupo do carnê-leão em cada conta; lançamento de caixa com CPF do
  titular do pagamento e do beneficiário; relatórios Livro Caixa e demonstrativo
  mensal e anual; controle de excesso de deduções do mês anterior e para o mês
  seguinte; CAEPF no cadastro de pessoa física.

## Fatia 1 — Livro-caixa

- Plano de contas do livro-caixa por cliente (receitas e despesas), cada conta
  com o **código do Carnê-Leão Web** que corresponde a ela (rendimento
  `R01...` ou pagamento `P10`/`P11`/`P20`), e a dedutibilidade decorrendo
  desse código.
- Lançamento de caixa (entrada ou saída): data, conta, valor em `Decimal`,
  histórico, documento de origem, CPF do titular do pagamento e do beneficiário
  quando o código exigir, recebido de PF/PJ/exterior. Todos os tipos de receita
  (RC-128): lançamento manual é a porta principal.
- Só para empresa em modo livro-caixa; isolamento, autorização no servidor,
  trilha de auditoria, idempotência, correção por estorno (mesmo padrão da
  contabilidade).
- Cadastro: CAEPF opcional no cliente pessoa física (RC-129).
- Relatório **Livro Caixa** do período, conferível com os lançamentos.

## Fatia 2 — Apuração mensal do carnê-leão

- Tabela progressiva e redução **como dado com vigência**, nunca no código;
  valores de 2026 com a fonte citada.
- Base: rendimentos do mês menos deduções (livro-caixa limitado à receita do
  trabalho não assalariado, previdência oficial, dependentes, pensão), com o
  **excesso de deduções** levado aos meses seguintes até dezembro (art. 69).
- Demonstrativo mensal e anual, com memória de cálculo; valor abaixo de
  R$ 10,00 acumulado.
- **Antes de codificar a redução da Lei 15.270/2025 no carnê-leão**, confirmar
  na fonte integral que ela se aplica ao recolhimento mensal (PE-71).

## Fatia 3 — Arquivo para o Carnê-Leão Web (RC-127)

- Geração dos CSV no leiaute oficial (rendimentos e pagamentos), com os códigos
  vindos das contas; conferência de que o arquivo gerado bate com o
  livro-caixa do mês.

## Critérios de aceite

1. Lançamento só em cliente em modo livro-caixa; recusa em modo contabilidade.
2. Casos de referência calculados à mão: mês com lucro, com dedução maior que a
   receita (excesso carregado), excesso em dezembro que não passa para janeiro,
   dependentes, faixa isenta, cada faixa da tabela, centavos.
3. Livro Caixa do período concilia com os lançamentos; estorno rastreável.
4. Tabela e redução versionadas por vigência; mudança de tabela não altera
   apuração já feita.
5. CSV gerado no leiaute oficial, validado contra os modelos da Receita.
6. Isolamento entre clientes e escritórios; autorização no servidor.
7. Suíte completa, lint, formatação, `check`, migrações.

## Hipóteses e pendências

- **HI-30:** a dedutibilidade de cada conta decorre do código do Carnê-Leão Web
  associado a ela (`P10` dedutível, `P11` não dedutível), como no plano de
  contas padrão da Receita. O escritório pode associar outro código.
- **PE-71:** confirmar na fonte integral a aplicação da redução da Lei
  15.270/2025 ao carnê-leão, e obter a tabela completa de códigos de
  rendimento, pagamento e ocupação (página de ajuda da Receita bloqueada à
  leitura automática em 2026-09-26).
- **Fora desta etapa:** carnê-leão do **empregador** pessoa física calculado a
  partir da folha (no sistema de referência fica no módulo Folha, que ainda
  não existe aqui); DARF (o Carnê-Leão Web gera a guia); integração automática
  com NFS-e recebida.
- Validação profissional dos casos de referência é do Fred.
