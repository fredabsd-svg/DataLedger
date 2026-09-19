# DL-016 — Plano de execução proposto

**Estado do plano oficial:** `docs/planos/DL-016-competencia-e-fechamento.md`, planejada em 2026-09-13, **não iniciada**.
**Estado deste plano de execução:** proposto em 2026-09-18, aguardando revisão do Fred.

## Decisões de produto a confirmar antes de codar

Sem confirmação destas, **não escrevo código**. Estão listadas na ordem em que travam o desenho:

### D1. Política padrão de período de trabalho para empresa nova

O plano diz "livre, avisar ou bloquear" mas não diz o padrão. Opções:
- **LIVRE** — grava sem mensagem.
- **AVISAR** — grava e devolve aviso na resposta.
- **BLOQUEAR** — recusa com 400.

**Proposta minha (registrada, sujeita a revisão):** AVISAR. É o meio termo do plano e o que menos quebra fluxo do operador em empresa nova. Pode ser mudado por empresa depois, sem migração.

### D2. Papel autorizado a fechar e reabrir competência

O plano diz "papel autorizado" sem nomear. Hoje existem 6 papéis: ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO, PARALEGAL, CLIENTE (`apps/tenancy/models.py:36-41`).

**Proposta minha:** ADMINISTRADOR e GESTOR podem fechar e reabrir. Os demais não. Decisão alinhada com o desenho atual: GESTOR é o papel que opera a contabilidade; ADMINISTRADOR tem o mais alto e por ele passa qualquer ato formal; ANALISTA opera mas não formaliza (analogia: separar quem digita de quem fecha). **Se quiser incluir só ADMINISTRADOR, ou todos, troca agora.**

### D3. Onde mora o "documento de origem" da BL-72

O `LancamentoContabil` hoje não tem campo de origem nem de documento de origem. A DL-010 (planejada, não iniciada) vai criar "documento fiscal", mas o modelo concreto ainda não existe.

**Proposta minha:** usar `GenericForeignKey` (Django content types) — `content_type` + `object_id` + tipo discriminado por `CharField` com choices `MANUAL`/`AUTOMATICA_FISCAL`/`AUTOMATICA_OUTRA`. Permite que qualquer modelo futuro (DocumentoFiscal, DocumentoInterno, etc.) seja referenciado sem migração no `LancamentoContabil`. Custo: uma tabela `django_content_type` precisa estar populada (já está, é Django nativo).

A `origem` (campo discriminado, não o documento) tem valor padrão `MANUAL` na migração de dados existentes — o CA 11 exige isso.

### D4. Conferência como pré-condição do fechamento (CA 5)

O plano diz "a conferência da DL-015 é pré-condição". A conferência tem 4 categorias hoje (achado da BL-84 vai criar a 5ª). Quero confirmação: **fecha-se com QUALQUER inconsistência, ou só com algumas?**

**Proposta minha:** QUALQUER inconsistência. Lógica: se o contador fecha um mês com 1 centavo de diferença, vai descobrir tarde demais. Se a conferência acuse e for ele próprio que decida ignorar, ele reabre e fecha de novo. **Se quiser exceção para "diferença que não afeta soma" ou coisa parecida, declare.**

### D5. Quem pode criar `PeriodoTrabalho` (política)

Vai ser por empresa. Modelo separado ou campo em `Empresa`?

**Proposta minha:** modelo separado `PeriodoTrabalho(empresa, competencia, politica)` — mais flexível, e não obriga migração quando o Fred quiser permitir política diferente por competência. Política padrão por empresa: `AVISAR` (decisão D1). Permite override por competência (ex.: dezembro sempre BLOQUEAR).

### D6. Granularidade

Plano diz "competência (mês de referência)". Vou seguir **mês/ano** como competência. Não fecha por dia dentro do mês. Se houver caso "fechar 1 a 15 e manter 16-30 aberto", fica para versão futura.

### D7. Branch de trabalho

O plano oficial (linha 118) diz `claude/accounting-agent-team-setup-mn6lyf`. Essa branch já foi usada para DL-022 e está reciclada na `main`. **Proposta:** criar `claude/dl-016-competencia-e-fechamento`, fresca da `main`. Mais limpa, mais rastreável.

## Decisões técnicas já tomadas (não precisam de confirmação)

### T1. DE-019 — competência é mês da data

Já decidido pelo plano. Não crio campo `competencia` em `LancamentoContabil`. Derivo de `data` em tempo de execução via `competencia_da_data(d) -> (ano, mes)`.

### T2. Modelo só para fechamento, não para competência

`Fechamento(empresa, ano, mes, situacao, autor, data_fechamento, motivo_reabertura, reaberto_por, reaberto_em)` — uma linha por (empresa, ano, mês). `UNIQUE` em `(empresa, ano, mes)`. `situacao` é `choices(ABERTO, FECHADO)` mas o estado natural é derivado: existe linha → fechado; não existe linha → aberto. Linha só nasce por ação de fechar.

### T3. Recusa por competência (CA 1, CA 2)

No `criar_lancamento` (serviço já existente) e na view de estorno, ANTES de gravar: verifica se existe `Fechamento` para `(empresa, ano, mes)` da data. Se existir, `ValidationError` com mensagem nomeando a competência. View devolve 409 com a mensagem.

### T4. Recusa por período de trabalho (CA 9)

Mesma camada, mas por `PeriodoTrabalho.politica`. Se `LIVRE`: passa silencioso. Se `AVISAR`: passa e adiciona warning ao contexto da resposta. Se `BLOQUEAR`: `ValidationError`, view devolve 400.

### T5. Filtro de competência nas saídas (CA 10)

Adiciona parâmetro `competencia=YYYY-MM` em Diário, Razão, Balancete (e nas APIs). Internamente traduz para `[primeiro dia, último dia]`. Não substitui `data_inicio`/`data_fim` — é uma forma a mais.

### T6. Origem não alterável (CA 11)

`LancamentoContabil.origem` é set no `save()` e nunca mais alterado. `update()` via ORM pode, mas a BL-247 (gatilho DL-010) é que vai fechar essa porta com camada de banco.

## Sequência de execução em 6 fatias

Cada fatia termina com:
- Código + testes.
- `pytest apps/contabilidade` verde, em árvore limpa (procedimento BL-81).
- Commit declarando o que foi verificado e o que não foi.

### F1 — Modelo `Fechamento` e idempotência/concorrência/isolamento (CA 6, 7, 8)

**Escopo:**
- `apps/contabilidade/models.py`: nova classe `Fechamento`.
- Migração que cria a tabela sem popular.
- Testes:
  - Fechar duas vezes a mesma competência: 1 linha, autor original.
  - Duas requisições simultâneas: 1 linha (teste concorrente com `select_for_update` ou `INSERT ... ON CONFLICT DO NOTHING`).
  - Fechamento de empresa A não afeta empresa B.
  - Fechamento de empresa em escritório X não afeta escritório Y.

**Não escopo:** nada de UI, nada de recusa de lançamento ainda.

### F2 — Recusa de lançamento e estorno em competência fechada (CA 1, 2, 5)

**Escopo:**
- Serviço `competencia_da_data(d) -> (ano, mes)`.
- Em `criar_lancamento`: checar `Fechamento.objects.filter(empresa=..., ano=..., mes=...).exists()` antes de gravar.
- Em `estornar_lancamento`: mesma checagem para a data do lançamento original.
- View de estorno: 409 com mensagem.
- View de criar lançamento: 409 com mensagem.
- Migração: nenhum dado existente é alterado.
- Testes:
  - Lançar em competência fechada: 409, nada gravado.
  - Estornar em competência fechada: 409, sem novo lançamento.
  - Lançar em competência aberta: passa.
  - Fechar com conferência acusando: recusado (precisa F3 primeiro para ter `conferencia` funcional).

**Não escopo:** período de trabalho, trilha de reabertura.

### F3 — Período de trabalho (CA 9)

**Escopo:**
- Modelo `PeriodoTrabalho(empresa, ano, mes, politica)`.
- Migração cria tabela; não popula nada (sem política = LIVRE por ausência de registro, ou AVISAR se você confirmar D1).
- Em `criar_lancamento`: aplicar política. Se AVISAR, contexto da resposta inclui warning.
- Testes: 3 cenários × gravar, 3 × recusar.

### F4 — Filtro de competência nas saídas (CA 10)

**Escopo:**
- Diário, Razão, Balancete e APIs: parâmetro `competencia`.
- View aceita `competencia=YYYY-MM`, traduz internamente.
- Testes: para cada saída, com e sem `competencia`, conferindo que o intervalo derivado é igual ao manual.

### F5 — BL-72 origem e documento (CA 11, 12)

**Escopo:**
- `LancamentoContabil.origem` (CharField, choices) e `documento_origem` (GenericForeignKey).
- Migração popula `origem='MANUAL'` em todos os lançamentos existentes.
- `criar_lancamento` aceita `origem` e `documento_origem` como parâmetro; padrão MANUAL.
- Origem não é alterável: `save()` checa se já tem valor e ignora nova tentativa; mensagem clara no comentário.
- View de criar lançamento: não expõe `origem` (é sempre MANUAL pela UI).
- API: aceita `origem` se for MANUAL (rejeita AUTOMATICA_* até existir gerador).
- Consulta reversa: `lancamentos_do_documento(doc)` e `documento_do_lancamento(lanc)`.
- Teste de isolamento: documento de empresa A não aparece nos lançamentos de empresa B.

### F6 — Fechar e reabrir com trilha (CA 3, 4, BL-244 já integrada)

**Escopo:**
- View POST `/empresas/<id>/competencias/<YYYY-MM>/fechar/`: chama `fechar_competencia(empresa, ano, mes, autor)`.
- View POST `/empresas/<id>/competencias/<YYYY-MM>/reabrir/`: chama `reabrir_competencia(empresa, ano, mes, autor, motivo)`. Requer papel ADMINISTRADOR ou GESTOR.
- View confere `conferencia` antes de fechar (passa resultado da DL-015; recusa se houver acusação).
- Trilha: `RegistroAuditoria` (já na DL-024) registra quem, quando, motivo.
- Motivo vazio → 400.
- Tela: por empresa, lista de competências, com botão fechar/reabrir conforme papel.
- Testes: fechamento autorizado, fechamento não autorizado, reabertura autorizada, reabertura sem motivo, reabertura não autorizada, trilha gravada.

## Auditoria

Auditoria dedicada no fim de F6, antes do merge. Rodada 1 cobre todas as 13 CA + cenários adjacentes (regressão, concorrência, isolamento, integridade de banco).

## Riscos que vou registrar e medir

- **Migração com GenericForeignKey em SQLite (teste) e PostgreSQL (produção):** verificar comportamento idêntico.
- **Constraint `UNIQUE (empresa, ano, mes)` em Fechamento:** em concorrência, capturar `IntegrityError` e devolver "já fechado" — não 500.
- **Custo da consulta extra em `criar_lancamento`:** uma query por gravação, índice composto `(empresa, ano, mes)` cobre.
- **Período de trabalho vazio vs LIVRE:** cuidado para "ausência de PeriodoTrabalho" não ser ambígua com "política LIVRE". Vou explicitar no serviço.

## Não vou fazer nesta etapa

Por desenho, mesmo que o plano deixe em aberto:
- Alteração em massa (BL-65) — depende do fechamento, mas é etapa separada.
- Regeração de derivados (BL-66) — depende do fechamento E da BL-72 (feita em F5), mas é etapa separada.
- Numeração de livros (BL-70) — não relacionada.
- Interface completa (BL-62) — faço o mínimo para o fechamento/reabertura ser operável; a tela rica fica para DL-017 ou nova etapa.

## Pedido ao Fred

**Antes de eu codar:** leia as decisões D1–D7 e me diga:
1. D1 (AVISAR) confirmado, ou outro?
2. D2 (ADMINISTRADOR+GESTOR) confirmado, ou outro?
3. D3 (GenericForeignKey) confirmado, ou prefere FK nullable agora e migração na DL-010?
4. D4 (QUALQUER inconsistência bloqueia fechamento) confirmado?
5. D5 (modelo separado) confirmado?
6. D6 (mês/ano) confirmado?
7. D7 (branch nova) confirmado?

Qualquer "outro" me dá trabalho de reescrever parte do desenho. Se concordar com tudo, começo por F1 (modelo `Fechamento`).
