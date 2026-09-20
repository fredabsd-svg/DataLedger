# DL-016 — Competência e fechamento de período

**Estado:** o estado desta etapa **não é descrito aqui** — ele está em
[`docs/agents/estado.md`](../agents/estado.md), que é a fonte única. Descrever
estado em dois lugares é a duplicação que a instrução permanente do Fred, de
2026-09-13, proíbe. ⚠️ **Esta linha dizia "planejada em 2026-09-13, não
iniciada" até 2026-09-20, e era falso**: a F1 e a F2 estão na `main` há semanas
— ver a tabela *"O que JÁ EXISTE"* mais abaixo, que é medição, não memória.

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

⚠️ **Este parágrafo dizia "Nada" e envelheceu.** A medição de 2026-09-20 está na
tabela **"O que JÁ EXISTE, medido antes de escrever esta fatia"**, mais abaixo —
e é o único lugar deste plano que descreve o código existente, para não haver
duas versões divergindo.

**O que continua verdadeiro da redação original, e é o que justifica a etapa:**
qualquer lançamento pode ser gravado em qualquer data, inclusive num mês cujo
balancete já foi entregue ao cliente. O campo `Competencia.estado` existe e
**nenhum código de produção o lê**.

## Dois controles distintos, e a diferença importa

Levantado no [mapa funcional contábil](../projeto/mapa-funcional-contabil.md).
Confundi-los é erro caro:

| Controle | O que é | O que faz |
| --- | --- | --- |
| **Período de trabalho** | A janela em que o operador está digitando agora | Evita erro de digitação (lançar 2025 em vez de 2026). Por empresa, com política: livre, avisar ou bloquear |
| **Fechamento** | O ato formal de encerrar a competência | Garantia contábil. Depois dele, alterar exige reabertura autorizada e auditada |

O primeiro protege o operador de si mesmo; o segundo protege o cliente.

## O TERCEIRO fato, respondido pelo Fred em 2026-09-20

Eu perguntei o que o escritório faz quando um mês **já fechado** precisa de
correção, com três opções. **A resposta foi (c): depende de o documento já ter
ido ao cliente.**

Isso não é detalhe de fluxo — **muda o modelo**, e é caro de acrescentar depois:

| Situação | O que o sistema faz |
| --- | --- |
| Competência **aberta** | Lança livremente |
| Competência **encerrada**, ainda **não entregue** | **Reabre**, com motivo obrigatório, autorização e trilha. Corrige, fecha de novo |
| Competência **encerrada e ENTREGUE** ao cliente | **Não reabre.** A correção vai por **ajuste no mês aberto**, com histórico apontando para a competência de origem |

**Decisão de modelagem, minha:** *"entregue"* **não é um quarto estado** — é um
**fato datado** sobre a competência (`entregue_em`, `entregue_por`). Estado e
entrega são coisas diferentes: um mês pode estar encerrado e não entregue, e a
entrega pode repetir-se (balancete ao cliente, depois ECD transmitida). Começar
com um par de campos é o mais barato; se um dia precisar de lista de entregas,
vira modelo próprio sem refazer a trava.

⚠️ **Por que isto protege o cliente, e não só o processo:** um balancete que o
cliente já recebeu, arquivou e talvez levou ao banco **não pode mudar por baixo
dele**. Se mudar, o papel na mão dele deixa de bater com o sistema — e o projeto
exige que relatório e saldo sejam conciliáveis com os lançamentos de origem
(RC-19).

## Escopo

- Competência (mês de referência) como conceito de primeira classe, vinculada ao
  lançamento.
- Fechamento por empresa e competência, com autor, data e situação.
- Reabertura autorizada, com motivo obrigatório e registro na trilha.
- Recusa, **no servidor**, de lançamento em competência encerrada.
- Período de trabalho por empresa, com a política de três estados.
- Filtro de competência nas saídas da DL-015.
- **Origem e documento de origem no lançamento** (BL-72). Entra aqui por
  economia de migração: esta etapa já altera o modelo, e separar as duas daria
  duas migrações sobre a mesma tabela. É pré-requisito da regeração de
  lançamentos derivados (BL-66, DE-018) e da integração fiscal→contábil.

Fora do escopo: alteração em massa (BL-65), regeração de derivados (BL-66),
centro de custo (BL-67 a BL-69), numeração de livros (BL-70), interface (BL-62).

## Decisão de modelagem, já tomada

**DE-019**: a competência é o **mês da data do lançamento**, não um campo
próprio. Dois campos poderiam discordar, e a partir daí Diário e Balancete
contariam histórias diferentes.

O caso "lançamento de dezembro digitado em janeiro" é atendido sem campo novo:
é um lançamento **com data de dezembro**. Aberto o mês, grava-se; fechado, vale
RC-57 — reabre, lança, fecha, com rastro.

Decisão reversível enquanto não houver dado real, e registrada agora justamente
porque depois fica cara.

## Fatia 1 — o que trava o livro (NÍVEL 1)

Sob a **§3.1 do `AGENTS.md`** (regra de 2026-09-20), esta fatia é **nível 1** e
paga cerimônia completa. **O resto do escopo acima fica para depois** — período
de trabalho, filtro nas saídas, origem do lançamento (BL-72) e interface são
fatias próprias, e nenhuma delas trava o livro.

**O que entra, e só isto:**

1. **Fechar** competência (`aberta → encerrada`), com autor, data e motivo na
   trilha.
2. **Recusar lançamento em competência encerrada — NO SERVIDOR.** É a garantia
   inteira desta fatia; esconder o botão na tela não conta.
3. **Reabrir** com motivo obrigatório e trilha — **recusado se a competência já
   foi entregue**.
4. **Marcar como entregue**, com autor e data.

**A tela vem na fatia 2**, depois que o servidor estiver certo. Ordem
deliberada: a trava tem de existir antes de haver botão para acioná-la.

## O que JÁ EXISTE, medido antes de escrever esta fatia

Escrevo isto porque metade da F1/F2 original já está na `main`, e mandar
implementar de novo seria desperdício:

| Peça | Estado medido |
| --- | --- |
| Modelo `Competencia` (`empresa`, `ano`, `mes`, `estado`, `criado_em`) | **Existe**, com `UniqueConstraint(empresa, ano, mes)` e duas `CheckConstraint` de faixa |
| `EstadoCompetencia` com `aberta → em_encerramento → encerrada` | **Existe** |
| `LancamentoContabil.competencia` (FK, `PROTECT`, `null=True`) | **Existe** |
| Criação automática da competência dentro de `criar_lancamento` | **Existe** (`apps/contabilidade/services.py`, `get_or_create` na mesma transação, com tratamento de corrida) |
| Comando `backfill_lancamento_competencia` | **Existe** |
| **Qualquer código de produção que LEIA `Competencia.estado`** | ⚠️ **NÃO EXISTE.** `grep '\.estado\b'` fora de testes não devolve nada. O campo é decorativo: hoje nada impede lançar em mês "encerrado" |

**É esse buraco que a fatia 1 fecha, e só ele.**

## Critérios de aceite da FATIA 1

1. **Lançar em competência encerrada é recusado NO SERVIDOR**, com **409** e
   mensagem que diz **qual** competência está fechada — não 500, não silêncio.
   A recusa vive no **serviço** (`criar_lancamento`), não na view: qualquer
   porta que chame o serviço herda a trava.
2. **Estorno também é recusado** quando cairia em competência encerrada, porque
   estorno é lançamento novo. ⚠️ **Atenção à data:** o estorno hoje recebe a
   data de **hoje**, não a do original — então o que decide é a competência do
   **estorno**, e o caso em que o original está em mês fechado e o estorno em
   mês aberto **passa**. ✅ **CONFIRMADO PELO FRED em 2026-09-20 — é o RC-103**,
   resposta literal *"o estorno de mês fechado pode passar direto mesmo"*. Eu
   levei o caso a ele **como dúvida**, porque a leitura apressada do RC-57 diz o
   contrário; ele confirmou que passa. **Não trate isso como lacuna do plano: é
   requisito.** O sub-caso que segue recusado é o estorno com **data explícita**
   caindo em mês fechado — aí é lançamento em mês fechado como outro qualquer.
3. **Fechar** grava autor, data e registro na trilha. Fechar competência com
   **lote desbalanceado** na base é **recusado** — a conferência da DL-015 é
   pré-condição (**RC-58**). Use `localizar_lotes_desbalanceados`, que já existe.
4. **Fechamento é idempotente**: fechar duas vezes não duplica registro nem
   troca o autor do primeiro fechamento.
5. **Reabrir exige motivo não vazio** e grava na trilha quem, quando, qual
   competência e qual motivo. Motivo em branco ou só espaços é recusado.
6. **Reabrir competência JÁ ENTREGUE é recusado** (**RC-101**), com **409** e
   mensagem que diz a data da entrega e orienta o ajuste no mês aberto. Este é
   o critério que nasceu da resposta do Fred, e é o que nenhum plano anterior
   tinha.
7. **Marcar como entregue** grava `entregue_em` e `entregue_por`. Só competência
   **encerrada** pode ser entregue — entregar mês aberto é recusado.
8. **Autorização é verificada no servidor.** Fechar, reabrir e entregar exigem
   papel autorizado; usuário sem o papel recebe **403** e **nada muda** no banco.
   ✅ **CONFIRMADO pelo Fred em 2026-09-20 — é o RC-102, não é mais hipótese:**
   *"Administrador e gestor pode, analista não"*. Os papéis autorizados são
   **ADMINISTRADOR** e **GESTOR**; `ANALISTA` lança e **não** fecha;
   `FINANCEIRO`, `PARALEGAL` e `CLIENTE` não alcançam a operação. ⚠️ **Teste os
   três lados**: quem pode (passa), o analista (403 **e banco intacto**), e um
   papel de fora (403). Nasceu como HI-17 e foi validada no mesmo dia, **antes
   de virar código**.
9. **Isolamento.** Competência encerrada de uma empresa não afeta outra empresa
   nem outro escritório. Teste com duas empresas de escritórios diferentes.
10. **Concorrência.** Duas requisições simultâneas de fechamento da mesma
    competência produzem **um** registro. Teste concorrente em PostgreSQL.
11. **Migração sobre base COM DADOS**: nenhuma competência existente nasce
    encerrada nem entregue. O estado inicial é tudo aberto.
12. **Sem regressão:** suíte, `ruff check`, `ruff format --check`,
    `manage.py check` e migrações em banco vazio limpos, com os números
    declarados.

⚠️ **O que NÃO é critério desta fatia, e não deve aparecer no diff:** tela,
botão, filtro de competência nas saídas da DL-015, política de três estados do
período de trabalho, origem do lançamento (BL-72). Isso é fatia 2 em diante.

## Critérios das fatias seguintes (NÃO implementar agora)

Preservados do plano original para não se perderem:

- Lançamento fora do **período de trabalho** segue a política da empresa: livre,
  avisar ou bloquear. Teste para os três estados.
- As saídas da DL-015 aceitam **competência** como forma de informar o período,
  sem perder o intervalo de datas livre.
- **Origem do lançamento** (BL-72) gravada com valores controlados, não
  alterável depois, com caminho do documento de origem para os lançamentos que
  ele gerou e o inverso, respeitando o isolamento.
- **Tela** de fechamento, reabertura e entrega.

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
