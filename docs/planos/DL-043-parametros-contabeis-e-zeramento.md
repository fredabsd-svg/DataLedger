# DL-043 — Parâmetros contábeis por empresa e zeramento do resultado

**Demanda:** fila aprovada pelo Fred (plano mestre §16; RC-88) e ordem de
26/09/2026 de *"seguir para a próxima etapa sem parar para perguntar"*. Regras
de negócio confirmadas pelo Fred em 2026-09-20: **RC-104** (zeramento por
lançamento, em duas etapas, destino pelo sinal) e **RC-105** (periodicidade
alternativa e por empresa). Resolve o **BL-474**.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — lançamento, saldo, competência e documento entregue.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** `claude/vigilant-bardeen-jo12l4` → `main`, depois do merge da DL-042.

O plano antigo `DL-016-F3` (branch `claude/dl-016-f3-encerramento-competencia`,
nunca integrada) tratava do **fechamento da competência mensal**, que já existe
(DL-016 fatia 1 e DL-031). Ele não é a base desta etapa e fica superado.

## Problema

Sem zeramento, as contas de receita e despesa acumulam saldo indefinidamente, o
Balanço só fecha mostrando o resultado não transferido (pergunta ainda aberta de
21/09) e o escritório não consegue encerrar o exercício pelo produto. Não existe
lugar para guardar parâmetro contábil por empresa.

## Fatia 1 — Parâmetros contábeis por empresa, com vigência

- Conceito próprio (não campos soltos em `Empresa`), no molde do
  `HistoricoRegimeTributario` (DE-039): **periodicidade do zeramento**
  (mensal, trimestral, anual) e **três contas de destino** — resultado do
  exercício, lucros acumulados, (-) prejuízos acumulados — com `vigencia_inicio`
  e `vigencia_fim`.
- Uma única vigência aberta por empresa; vigências não se sobrepõem; no banco.
- As três contas são analíticas, da mesma empresa e do grupo do Patrimônio
  Líquido; a de prejuízos é retificadora (natureza devedora dentro do PL, RC-61).
- Empresa em modo livro-caixa não recebe parâmetro contábil (DL-038).
- API e admin; tela na fatia 3.

## Fatia 2 — Zeramento

- Serviço que, para um período da periodicidade vigente, gera **dois
  lançamentos** na data final do período:
  1. contas de receita e despesa (analíticas, com saldo no período) contra a
     conta de resultado do exercício;
  2. saldo da conta de resultado do exercício contra lucros acumulados (credor)
     ou (-) prejuízos acumulados (devedor), pelo sinal.
- Valores em `Decimal`, partidas dobradas iguais, dentro de **uma** transação.
- **Idempotente:** repetir o zeramento do mesmo período não duplica; se houve
  lançamento novo no período depois do zeramento (competência ainda aberta),
  um novo pedido gera só o **complemento** da diferença, também idempotente.
- Recusado em competência encerrada (RC-57); a correção segue o estorno
  (RC-103).
- Só ADMINISTRADOR e GESTOR (mesma regra do fechamento, RC-102), verificado no
  servidor; trilha de auditoria na mesma transação.
- Lançamentos identificáveis como zeramento (histórico padronizado e chave de
  idempotência determinística), para o Razão e a conferência.

## Fatia 3 — Telas

Parâmetros na empresa; ação "Zerar resultado do período" na tela do fechamento,
com prévia dos valores antes de gravar e mensagem do que foi gerado.

## Critérios de aceite

1. Parâmetro com vigência: sobreposição e segunda vigência aberta recusadas no
   banco; contas de destino inválidas recusadas com mensagem.
2. Casos de referência calculados à mão: lucro, prejuízo, resultado zero,
   só receitas, só despesas, conta retificadora de receita (devoluções), centavos.
3. Depois do zeramento, receitas e despesas analíticas ficam com saldo zero no
   período, e o resultado aparece em lucros ou prejuízos acumulados pelo sinal.
4. Balancete antes e depois concilia: soma dos débitos igual à dos créditos, e a
   variação do PL igual ao resultado apurado.
5. Repetição e complemento sem duplicidade; concorrência de dois pedidos no
   PostgreSQL resulta num único zeramento.
6. Competência encerrada recusa; papel sem permissão recebe 403 sem gravar.
7. Periodicidade trimestral e anual zeram só no último mês do período; a
   mensal, todo mês.
8. Isolamento entre empresas e escritórios em todas as portas.
9. Suíte completa, lint, formatação, `check`, `makemigrations --check`,
   migração em banco vazio e em SQLite.

## Pendências e hipóteses

- **HI-24:** o zeramento é disparado pelo usuário na tela do fechamento, e não
  automaticamente ao encerrar a competência. Reversível; confirmar com o Fred.
- A destinação do lucro (dividendos, reservas) fica fora: é outra etapa, com
  fonte normativa (Lei 6.404/76) levantada antes.
- Validação profissional dos casos de referência é do Fred.

## Rodada 1 da auditoria

[Relatório integral](../auditorias/2026-09-26-dl-043-rodada-1.md) em `c021436`:
**REPROVADA**. Bloqueadores B1 (conta com filhas conta o resultado em dobro) e B2
(zeramento fora de ordem, complemento tardio ou meses concorrentes contam em
dobro); alta B3 (erros previsíveis viram 500; 200 contas não zeram); médias B4
(chave de zeramento forjável), B5 (cálculo quadrático), B6 (mutantes
sobreviventes); baixas B7, B8, B10. Decisões da correção em **DE-078** e
**HI-25**; B9 (sem admin) decidido na DE-078. P1 (meses alternados de lucro e
prejuízo inflam as duas contas do PL) em consulta ao manual do sistema de
referência antes de ir ao Fred. Correção única em andamento, depois uma
reconferência.
