# DL-016 — Competência e fechamento de período

**Estado:** planejada em 2026-09-13. Não iniciada.

## Por que esta etapa vem agora

Três coisas que o Fred pediu dependem dela, e nenhuma pode ser feita antes:

- **Alteração em massa** (RC-51, DE-017): o comportamento muda conforme o
  período esteja aberto ou encerrado. Sem fechamento, só existiria a versão
  permissiva — alterar o passado sempre.
- **Eliminação de período** (RC-52, DE-018): só de período encerrado.
- **Lançamento de abertura** (RC-53): implantar uma empresa é declarar que tudo
  antes daquela data está fechado.

Fecha **BL-11** e **BL-15**.

## O que existe hoje

Nada. Verificado: `competencia` não aparece em `apps/`, `config/` nem
`templates/`. Qualquer lançamento pode ser gravado em qualquer data, inclusive
num mês cujo balancete já foi entregue ao cliente.

## Dois controles distintos, e a diferença importa

Levantado no [mapa funcional contábil](../projeto/mapa-funcional-contabil.md).
Confundi-los é erro caro:

| Controle | O que é | O que faz |
| --- | --- | --- |
| **Período de trabalho** | A janela em que o operador está digitando agora | Evita erro de digitação (lançar 2025 em vez de 2026). Por empresa, com política: livre, avisar ou bloquear |
| **Fechamento** | O ato formal de encerrar a competência | Garantia contábil. Depois dele, alterar exige reabertura autorizada e auditada |

O primeiro protege o operador de si mesmo; o segundo protege o cliente.

## Escopo

- Competência (mês de referência) como conceito de primeira classe, vinculada ao
  lançamento.
- Fechamento por empresa e competência, com autor, data e situação.
- Reabertura autorizada, com motivo obrigatório e registro na trilha.
- Recusa, **no servidor**, de lançamento em competência encerrada.
- Período de trabalho por empresa, com a política de três estados.
- Filtro de competência nas saídas da DL-015.

Fora do escopo: alteração em massa (BL-65), eliminação (BL-66), centro de custo
(BL-67 a BL-69), numeração de livros (BL-70), interface (BL-62).

## Decisão de modelagem, já tomada

**DE-019**: a competência é o **mês da data do lançamento**, não um campo
próprio. Dois campos poderiam discordar, e a partir daí Diário e Balancete
contariam histórias diferentes.

O caso "lançamento de dezembro digitado em janeiro" é atendido sem campo novo:
é um lançamento **com data de dezembro**. Aberto o mês, grava-se; fechado, vale
RC-57 — reabre, lança, fecha, com rastro.

Decisão reversível enquanto não houver dado real, e registrada agora justamente
porque depois fica cara.

## Critérios de aceite

1. Lançar em competência encerrada é recusado **no servidor**, com 409 e
   mensagem que diz qual competência está fechada — não 500, não silêncio.
2. O mesmo vale para estorno: estornar lançamento de período encerrado é
   recusado, porque gera lançamento naquele período. **Confirmado pelo Fred**
   (RC-57): período fechado não se mexe, só reabrindo.
3. Reabertura exige papel autorizado; usuário sem o papel recebe 403 e **nada
   muda**.
4. Reabertura grava na trilha: quem, quando, qual competência, qual motivo.
   Motivo vazio é recusado.
5. Fechar uma competência com lote desbalanceado na base é recusado — a
   conferência da DL-015 é pré-condição do fechamento. **Confirmado pelo Fred**
   (RC-58).
6. Fechamento é idempotente: fechar duas vezes a mesma competência não duplica
   registro nem muda o autor do primeiro fechamento.
7. Concorrência: duas requisições simultâneas de fechamento da mesma competência
   produzem um único registro. Teste concorrente.
8. Competência encerrada de uma empresa **não** afeta outra empresa, nem outro
   escritório. Teste de isolamento.
9. Lançamento fora do período de trabalho segue a política da empresa: livre
   (grava), avisar (grava e devolve aviso na resposta), bloquear (recusa com
   400). Teste para os três estados.
10. As saídas da DL-015 aceitam competência como forma de informar o período, sem
    perder o intervalo de datas livre.
11. Sem regressão: suíte, lint, formatação, `manage.py check` e migrações em
    banco vazio limpos.

## Riscos

- **Migração sobre base existente**: definir o que acontece com lançamentos já
  gravados quando o fechamento passa a existir. Nenhuma competência nasce
  fechada — o estado inicial é tudo aberto, e o Fred fecha o que já entregou.
- **Interação com a imutabilidade**: o fechamento não altera lançamento nenhum;
  só passa a recusar novos. Nenhum dado existente é tocado.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` | `apps/contabilidade/**` (modelos, migração, serviços, views, testes) |
| `arquiteto-senior` | documentação e a decisão de modelagem |

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`
- **Branch de destino:** `main`
