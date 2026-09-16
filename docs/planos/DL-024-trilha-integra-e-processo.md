# DL-024 — Trilha íntegra e processo: log à prova de desvio e processo à prova de descuido

**Estado:** **em planejamento, aguardando início**, aberto em 2026-09-16 a
partir da `main` em `1b828e7` (PR #27 integrado — DL-018 + rodadas 4 e 6 da
DL-023). Pacote 3 da fila do plano mestre (seção 16, item 3):
"BL-14/16/57, proteção da main e decisão do suporte SQLite".
Situação atual, sempre, em [docs/agents/estado.md](../agents/estado.md).

## Problema que esta etapa fecha

Quatro itens vivem em três lugares diferentes — `apps/auditoria/services.py`,
`apps/empresas/views.py`, `apps/contabilidade/views.py`, `apps/auditoria/admin.py`
— e eles juntos formam uma só **promessa**: **a trilha de auditoria é parte da
operação, não um detalhe paralelo.** Hoje:

- **BL-14 — auditoria fora da transação**: `apps/empresas/views.py:195` chama
  `registrar(acao="empresa.criada", ...)` **depois** do bloco `transaction.atomic()`.
  Se o `registrar()` falhar (unique constraint, FK violada, banco desconectou
  no meio), o `Empresa` foi gravada mas a trilha **não foi**. Mesma armadilha em
  `apps/contabilidade/views.py:444` (`conta.criada`), `:670` (`lancamento.criado`)
  e `apps/contabilidade/views_web.py:690` / `:1657`. Reproduzido pelo auditor
  com `IntegrityError` simulada em `mock.patch` no `RegistroAuditoria.objects.create`:
  a operação passa, o log não aparece, **a contabilidade diz uma coisa, a
  trilha diz outra**.
- **BL-16 — exclusão do log via massa**: `apps/auditoria/admin.py` recusa a
  exclusão individual pelo admin, mas **não** recusa `RegistroAuditoria.objects.all().delete()`
  nem `RegistroAuditoria.objects.filter(...).update(...)`. O caminho está
  fechado na interface, **aberto** no shell e em qualquer `management command`.
  Auditor provou: `RegistroAuditoria.objects.all().delete()` retorna `(N,)` e
  a tabela fica vazia em silêncio. Sem `delete()` também o `update()` apaga
  sem tocar em linha: `RegistroAuditoria.objects.filter(acao='login.sucesso').update(acao='foo')`
  retorna `3` e a história mudou sem deixar rastro da mudança.
- **BL-57 — PUT/PATCH não gera trilha**: `apps/empresas/views.py:229` tem
  `perform_update` que **não** chama `registrar(...)`. `EmpresaDetailView.put()`
  e `.patch()` silenciam qualquer alteração — mudar o **CNPJ** de uma empresa,
  trocar `razao_social`, alterar `regime_tributario`, mover de escritório: **nada**
  aparece em `RegistroAuditoria`. A vista `/auditoria/` continua dizendo "tudo
  certo" porque não há nada para mostrar. Auditor confirmou: dois PUT
  sucessivos mudando campos diferentes geram **zero** registros novos.
- **BL-50 (teste automatizado do gate SQLite)**: `config/settings.py:92–141`
  já implementa o gate ("com `DEBUG=False`, recusa subir sem PostgreSQL"),
  mas **não há teste** garantindo o comportamento. Reverter o `if DEBUG`
  para `if False` não falha em nada da suíte atual.

## Itens fora do escopo desta etapa

- **BL-02 — proteção da `main` no GitHub**: é **ação administrativa do Fred**
  (consulta à API em 2026-09-16 confirmou `protected: False`, ver tabela de
  "afirmações desmentidas" no plano mestre). Nenhum agente pode fechar.
  A DL-024 **não toca** nela — e **não pode** fingir que fecha.
- **BL-242 — registro de `permission_denied`**: decisão aberta se vai registrar
  tentativas negadas (audit de segurança) ou só as concretizadas. Decisão do
  Fred. Se sair "sim", vira DL-025.
- **BL-50 fora do recorte automatizado**: o aviso amarelo no startup já
  existe. O **teste** é o que entra; a **mensagem** segue como está
  (decisão do Fred mudar a copy, se quiser).

## Decisões de fora que precisam estar resolvidas antes da rodada 2

- **BL-57 estende a outros campos?** O título diz "altera CNPJ", mas o
  achado é genérico (PUT/PATCH inteiro). Vou propor a redação para
  `detalhes = {campo: {antes: x, depois: y}}` para **todos** os campos
  alterados, não só CNPJ, e a auditoria rodada 1 confirma se cabe. Se o
  Fred preferir CNPJ-só, a DL-024 fecha só o subconjunto.
- **Quem pode ver o `detalhes`?** O admin Django hoje é staff do escritório.
  Trilha com CNPJ/razão social antigos é dado sensível (LGPD). Auditoria
  rodada 1 pergunta ao Fred se o filtro atual (qualquer usuário do
  escritório vê tudo) é o desejado.

## Critérios de aceite

### CA-1 — BL-14, atomicidade entre operação e trilha

- Toda chamada de `registrar()` que **reflete uma gravação já confirmada**
  mora dentro do mesmo `transaction.atomic()` que chamou `serializer.save()`
  / `model.save()`. Cobertura: `apps/empresas/views.py:162` e `:229`,
  `apps/contabilidade/views.py:444` e `:670`, `apps/contabilidade/views_web.py:690`
  e `:1657`, `apps/tenancy/views.py:255` (`escritorio.ativado` — verificar
  se já está ou não).
- **Teste de mutação por falha induzida**: `mock.patch` em
  `RegistroAuditoria.objects.create` levantando `IntegrityError`. A operação
  que chamou o serviço **não** é gravada. Sem o `try/except` o teste morre
  (prova de que a falha era silenciada antes).
- `apps/empresa/tests/test_dl024_atomicidade_trilha.py` reúne os seis casos,
  com `pytest.mark.django_db(transaction=True)` onde o teste exige rollback
  parcial (não o default `pytest.mark.django_db`).

### CA-2 — BL-16, imutabilidade do `RegistroAuditoria`

- `RegistroAuditoria.Meta` ganha `delete_enabled = False` E
  `update_enabled = False` (ou sinal equivalente). Se Django não suportar
  nativo, um `pre_delete` / `pre_save` em `apps/auditoria/signals.py`
  levanta `PermissionDenied("registro de auditoria é imutável")`.
- **Teste de mutação em massa**: cada um dos quatro caminhos abaixo levanta
  a exceção esperada, **não** retorna contagem de linhas afetadas:
  - `RegistroAuditoria.objects.all().delete()`
  - `RegistroAuditoria.objects.filter(acao='login.sucesso').delete()`
  - `RegistroAuditoria.objects.filter(...).update(acao='foo')`
  - `RegistroAuditoria.objects.get(pk=1).delete()` (o caminho admin já
    bloqueado; este garante que a defesa é no modelo, não só na interface)
- O sinal NÃO bloqueia `RegistroAuditoria.objects.create()` — novos
  registros continuam entrando normalmente.

### CA-3 — BL-57, PUT/PATCH gera trilha com delta

- `apps/empresas/views.py:EmpresaDetailView.perform_update` chama
  `registrar(acao='empresa.atualizada', objeto=instance, detalhes={...})`
  **dentro do mesmo `transaction.atomic()`** do BL-14.
- `detalhes` tem a forma `{"alteracoes": {campo: {"antes": x, "depois": y}}}`
  para **cada campo cujo valor mudou**. Campos não alterados não aparecem.
- Lista de campos auditados: `cnpj`, `razao_social`, `nome_fantasia`,
  `escritorio_id`, `regime_tributario`, e qualquer outro que esteja no
  serializer e tenha regra de negócio crítica. Decisão final na auditoria
  rodada 1.
- **Teste**: dois PUT sucessivos mudando `cnpj` e `razao_social`
  produzem **um único** `RegistroAuditoria` (o segundo) com
  `detalhes["alteracoes"]` contendo **só** `razao_social`. O primeiro PUT
  produz outro registro com **só** `cnpj`. Sem o diff, o teste morre.
- **Teste de não-duplicação**: PUT que **não** altera nada (mesmo payload
  reenviado) **não** gera registro. Esse é o anti-P8 que apareceu na
  DL-011 rodada 3.

### CA-4 — BL-50, teste do gate SQLite/PostgreSQL

- `apps/core/tests/test_dl024_gate_db.py` cobre:
  - `DEBUG=False` + `DATABASE_URL` apontando para SQLite explícito → `manage.py check`
    falha com a mensagem do gate.
  - `DEBUG=False` sem `DATABASE_URL` → falha com a mensagem sem PostgreSQL.
  - `DEBUG=False` + `DATABASE_URL=postgres://...` → passa.
  - `DEBUG=True` sem `DATABASE_URL` → passa (SQLite de desenvolvimento
    permitido, warning amarelo).
- A **mensagem** do gate não é alterada por esta etapa.

### CA-5 — varredura de contratos e restrições (declarada antes de escrever)

- Mesma postura das DL-017/018: a cada função nova ou alterada,
  `apps/{x}/services/` expõe o contrato com `@dataclass(frozen=True)` ou
  nome explícito, e o `views.py` recusa `chave não contratada` via
  `_campos_gravaveis` + `_recusar_dado_nao_contratado_na_atualizacao`.
- Nenhuma view ganha parâmetro novo sem teste que prova a recusa.

### CA-6 — disciplina de redação

- Toda a documentação nova (esta etapa, decisão nova se houver, plano
  mestre se for tocado) em português brasileiro, sem inventar alíquota,
  prazo, fórmula ou leiaute oficial.
- Nenhuma referência à DL-024 fora de `docs/`, `README.md` e `apps/` —
  testes de guarda `apps/core/tests/test_documentacao_do_estado.py`
  continuam verdes (8/8).

## Fora do escopo declarado

- **Mudanças em regra de negócio contábil ou fiscal**. Esta etapa é
  **processo**: tornar a trilha íntegra, não ampliar o que ela registra.
- **Auditoria de `permission_denied`** (BL-242). Decisão do Fred primeiro.
- **Criptografia do `detalhes`**. Hoje vai como JSON em `JSONField` plain.
  Se o Fred quiser criptografia em repouso, é etapa própria.
- **Logs estruturados para fora do Django** (Sentry, ELK). Não decidido.

## Auditoria rodada 1 (a que abre com a primeira execução)

- Provar, mutação por mutação, cada um dos quatro CA-1 a CA-4.
- Responder às duas perguntas do Fred:
  1. BL-57 cobre só CNPJ ou **todos** os campos?
  2. Quem vê o `detalhes` na vista `/auditoria/`?
- Confirmar que a `apps/auditoria/admin.py` segue recusando exclusão
  individual (a defesa de BL-16 não conflita com a BL-16-parcial-que-já-tinha).
- **Não pode** reabrir BL-261 (decisão contábil), BL-262 (etapa própria),
  BL-263 (BL-249 do arquiteto), nem tocar em BL-02.

## Git

- **Branch de trabalho:** `claude/dl-024-trilha-integra-e-processo`, aberta
  a partir de `1b828e7`.
- **Branch de destino:** `main`, por PR. **O PR é parte da entrega** (achado
  A7/BL-260 herdado da DL-023): sem ele, o workflow "Regras do projeto" não
  roda, e dos três mecanismos impostos só dois são exercitados.
- **Mensagens de commit**:Conventional Commits, em português, com a
  sequência:
  1. `feat(DL-024): atomicidade entre operação e registro de auditoria` (BL-14)
  2. `feat(DL-024): imutabilidade do RegistroAuditoria contra update/delete em massa` (BL-16)
  3. `feat(DL-024): trilha de PUT/PATCH com diff dos campos alterados` (BL-57)
  4. `test(DL-024): cobrir o gate DEBUG=False sem PostgreSQL` (BL-50)
  5. `docs(DL-024): plano, decisão de BL-57 (campos cobertos) e auditoria rodada 1`
- **Validação local obrigatória antes do push**: `ruff check .`,
  `ruff format --check .`, `pytest apps/core/tests/test_documentacao_do_estado.py
  apps/auditoria/tests/ apps/empresas/tests/test_dl024_atomicidade_trilha.py
  apps/empresas/tests/test_dl024_trilha_update.py`. Suíte completa **só na CI**.

## Hipóteses e pendências a registrar

- **Hipótese:** a redação `detalhes["alteracoes"][campo]["antes|depois"]` é
  legível por humanos e por máquina (front + API). Se o front da
  `/auditoria/` pedir formato diferente, vira DL-025.
- **Hipótese:** Django permite trancar `delete()` e `update()` no `Meta` ou
  via `signals` sem custo de performance perceptível. Medir no fim.
- **Pendência:** a auditoria rodada 1 precisa do Fred responder às duas
  perguntas (campos cobertos, quem vê o `detalhes`). Sem resposta, fecha-se
  a DL-024 com a proposta-padrão e a DL-025 reabre se o Fred mudar de ideia.

## Histórico

- 2026-09-16: plano redigido, em planejamento, aguardando início.