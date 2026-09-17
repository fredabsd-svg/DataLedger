# DL-024 — Trilha íntegra e processo: log à prova de desvio e processo à prova de descuido

**Estado:** **integrada (PR #28, `5af2c19`)**, encerrada em 2026-09-17
com a decisão DE-043 (CA-4: plano reconciliado com o registry real). A
integração foi na `main` em `f9ee6c5` via PR #29 que a subiu. Os critérios
de aceite abaixo permanecem intactos.
Pacote 3 da fila do plano mestre (seção 16, item 3):
"BL-14/16/57, proteção da main e decisão do suporte SQLite". Inclui
**BL-244** (trilha do painel administrativo) por correção do Fred em
2026-09-16, e mantém **BL-50** (teste do gate SQLite/PostgreSQL).
Situação atual, sempre, em [docs/agents/estado.md](../agents/estado.md).

## Problema que esta etapa fecha

Cinco itens vivem em quatro lugares diferentes — `apps/auditoria/services.py`,
`apps/empresas/views.py`, `apps/contabilidade/views.py`,
`apps/auditoria/admin.py`, **e todos os `apps/*/admin.py`** — e eles juntos
formam uma só **promessa**: **a trilha de auditoria é parte da operação,
não um detalhe paralelo.** Hoje:

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
- **BL-244 — painel administrativo sem trilha**: **nenhum** `apps/*/admin.py`
  chama `registrar()`, nenhum sobrescreve `save_model`, `delete_model` ou
  `save_formset`, e não existe signal genérico de `post_save`/`pre_delete` —
  o único signal do projeto (`apps/accounts/signals.py:7-25`) cobre login,
  logout e falha de login, ou seja, a **entrada** no admin e não o que se
  faz depois dela. Consequência: alterar `Empresa`, `Conta`, `Estabelecimento`,
  `HistoricoRegimeTributario`, `Escritorio`, `VinculoUsuarioEscritorio` ou
  `Usuario` pelo admin **não deixa rastro na trilha do produto** — só, no
  máximo, no `LogEntry` interno do Django, que é log de framework e não
  trilha de negócio (e cuja gravação efetiva **não** foi medida).
  Medido, não deduzido.
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

**Nenhuma das duas hipóteses que eu havia proposto segue em aberto**, depois
do Fred em 2026-09-16:

- **BL-57 cobre quais campos? — DECIDIDO: todos os graváveis do serializer,
  derivados do contrato.** Medido em `apps/empresas/serializers.py:69`,
  `EmpresaSerializer.Meta.fields = ["id", "razao_social", "nome_fantasia",
  "cnpj", "ativo", "regime_atual"]`. Tirando `id` (PK, não editável) e
  `regime_atual` (read-only `SerializerMethodField`), os graváveis são
  exatamente quatro: `razao_social`, `nome_fantasia`, `cnpj`, `ativo`.
  `escritorio` **não** está no serializer (forçado a partir da requisição
  no `create` e travado pelo modelo desde a DL-023 BL-211/A3) e
  `regime_tributario` tem rota própria com trilha desde o RC-86/DE-039 —
  registrar um deles ali seria mentir sobre o que aquela porta fez.
  A lista **não é escrita à mão**; vem de
  `apps/empresas/views.py:72`, que é o `_campos_gravaveis(serializer)` e
  já governa o contrato da requisição (BL-196/DE-034). A trilha passa a
  derivar do contrato — campo novo no serializer amanhã entra na trilha
  sozinho, e o teste de mutação é direto.
- **Quem vê o `detalhes` em `/auditoria/`? — DECIDIDO: ninguém mexe
  nesta etapa, e acrescenta-se um teste que fixa a matriz atual.**
  Medido em `apps/auditoria/views.py:17`:
  `permission_classes = [TemEscritorioAtivo, papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)]`.
  Hoje **só ADMINISTRADOR e GESTOR** recebem 200; ANALISTA, FINANCEIRO
  e PARALEGAL recebem 403. (A) da minha proposta descrevia errado o
  estado atual; (B) faria duas mudanças silenciosas ao mesmo tempo
  (tira GESTOR, dá FINANCEIRO); (C) resolveria transparência de um
  papel que não tem acesso nenhum para preservar, e mascaramento é a
  defesa mais fraca das três. Mudar a matriz é **PE-36** (pendência
  aberta do Fred desde a DL-015, "quem, no escritório, pode ler a
  contabilidade de uma empresa? existe usuário que só vê algumas
  empresas da carteira?"), o **BAS-01** do plano mestre, e decidir
  isso dentro de uma etapa sobre integridade de trilha seria
  exatamente o que a DE-041 proíbe: resolver por tabela lateral o que
  tem dono.

**O que a etapa leva ao Fred, junto com a pergunta contábil que já está
com ele:** a trilha da BL-57 passa a conter CNPJ anterior e novo, que é
dado de cliente. Minha leitura: trilha de auditoria existe para isso, e o
acesso já está em need-to-know com dois papéis. Quem confirma é ele.

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
- `detalhes` é um par de dicts no **mesmo formato** de
  `valores_antigos` (usado por `excluir_ultimo_regime_tributario`,
  `apps/empresas/services.py:305`):
  - `valores_anteriores: {campo: valor_antes}` — só os campos que mudaram.
  - `valores_novos: {campo: valor_depois}` — só os campos que mudaram.
  - Os campos que **não** mudaram **não** aparecem nos dois dicts (diff,
    não retrato inteiro).
- **A lista de campos é derivada do contrato, não escrita à mão.**
  `apps/empresas/views.py:72` (`_campos_gravaveis`) já é a fonte única do
  contrato da requisição (BL-196/DE-034): `frozenset(nome for nome, campo
  in serializer.fields.items() if not campo.read_only)`. O diff só olha
  para campos deste `frozenset`. Hoje isso é exatamente
  `{razao_social, nome_fantasia, cnpj, ativo}` (`id` não é gravável e
  `regime_atual` é `SerializerMethodField`; `escritorio` não está no
  serializer — é forçado pela requisição e travado pelo modelo desde a
  DL-023 BL-211/A3). Campo novo no serializer amanhã entra na trilha
  sozinho.
- **`ativo: true → false` é material** — o diff trata a desativação de
  empresa como qualquer outra mudança, e isso aparece naturalmente
  porque a comparação é por valor, não por tipo de campo. Quem
  precisar explicar depois "por que esta empresa está inativa?" tem
  a resposta.
- **Teste**: dois PUT sucessivos mudando `cnpj` e `razao_social`
  produzem **dois** `RegistroAuditoria`. O primeiro tem
  `valores_anteriores = {"cnpj": "11111..."}` e
  `valores_novos = {"cnpj": "22222..."}`. O segundo tem só
  `razao_social` nos dois dicts. Sem o diff, o teste morre.
- **Teste de derivação do contrato**: `monkeypatch.setattr`
  adicionando um campo gravável ao `EmpresaSerializer` (por exemplo
  `apelido`) **sem editar a lista** — o PUT desse campo aparece na
  trilha e o teste passa. Se o código tiver lista hardcoded, o teste
  falha, e o mutante morre.
- **Teste de não-duplicação**: PUT que **não** altera nada (mesmo payload
  reenviado) **não** gera registro. Anti-P8 da DL-011 rodada 3.

### CA-4 — BL-244, painel administrativo gera trilha

**Status: integrada — reconciliada por DE-043.**

O plano original listava 6 ModelAdmin. O registry real do Django contém 4
registrados diretamente (`EmpresaAdmin`, `ContaAdmin`, `EscritorioAdmin`,
`VinculoUsuarioEscritorioAdmin`). Os dois restantes:

- **EstabelecimentoAdmin** — não existe como ModelAdmin registrado; o
  modelo é inline de `EmpresaAdmin` no admin. O signal BL-244 cobre
  `Estabelecimento` na lista explícita, e a criação por inline gera
  trilha. Teste end-to-end: criar empresa com estabelecimento via
  `/admin/empresas/empresa/add/` e verificar `RegistroAuditoria` para
  `empresas.estabelecimento.admin_criado`.

- **HistoricoRegimeTributarioAdmin** — removido do admin pela DL-023.
  Não há porta administrativa para esse modelo. O signal BL-244 continua
  cobrindo o modelo na lista explícita — se amanhã voltar a ter
  ModelAdmin, a trilha é gerada automaticamente. Teste: criação via
  ORM (`HistoricoRegimeTributario.objects.create(...)` com request fake)
  verifica que `registrar()` é chamado; ausência de porta admin é
  documentada como consequência da DL-023, não lacuna.

O teste `test_signals_de_admin_existem_e_cobrem_os_seis_modelos` em
`apps/core/tests/test_dl024_trilha_admin.py` é **ajustado** para
verificar que `MODELOS_DA_TRILHA_DO_ADMIN` contém os 6 modelos da lista
explícita — não 4, não o que está no registry. A lista explícita é o
contrato, o registry é衍 生.

| Modelo | Porta admin | Cobertura da trilha |
|---|---|---|
| Empresa | `EmpresaAdmin` | E2E via admin |
| Conta | `ContaAdmin` | E2E via admin |
| Estabelecimento | inline de Empresa | E2E via inline (empresa + estabelecimento) |
| HistoricoRegimeTributario | nenhum (removido DL-023) | ORM + request fake |
| Escritorio | `EscritorioAdmin` | E2E via admin |
| VinculoUsuarioEscritorio | `VinculoUsuarioEscritorioAdmin` | E2E via admin |

Decisão DE-043: CA-4 mede o que existe, não o que o plano imaginou.
O plano é artefato derivado do código, não o contrário.
Implementação em `apps/auditoria/signals.py` — BL-244 conecta
`post_save` e `pre_delete` nos 6 modelos via lista explícita
`MODELOS_DA_TRILHA_DO_ADMIN`. Detecção do caminho admin via
`_current_request` thread-local. Snapshot de valores anteriores guardado
em `pre_save` para `pre_delete`. Signal roda dentro da transação (sem
`on_commit`). Lista de exceções documentada no signal (LogEntry,
ContentType, Permission, Group, Session, accounts). Views continuam
responsáveis pelo `registrar()` próprio. Teste em
`apps/core/tests/test_dl024_trilha_admin.py`.

### CA-5 — BL-50, teste do gate SQLite/PostgreSQL

- `apps/core/tests/test_dl024_gate_db.py` cobre:
  - `DEBUG=False` + `DATABASE_URL` apontando para SQLite explícito → `manage.py check`
    falha com a mensagem do gate.
  - `DEBUG=False` sem `DATABASE_URL` → falha com a mensagem sem PostgreSQL.
  - `DEBUG=False` + `DATABASE_URL=postgres://...` → passa.
  - `DEBUG=True` sem `DATABASE_URL` → passa (SQLite de desenvolvimento
    permitido, warning amarelo).
- A **mensagem** do gate não é alterada por esta etapa.

### CA-6 — matriz de acesso de `/auditoria/` FIXADA por teste

- Estado atual preservado em teste, **não** alterado:
  `apps/auditoria/views.py:17` — `permission_classes = [TemEscritorioAtivo,
  papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)]`.
- `apps/auditoria/tests/test_dl024_matriz_acesso.py`:
  - ADMINISTRADOR e GESTOR: 200 em `GET /auditoria/`.
  - ANALISTA, FINANCEIRO, PARALEGAL: 403 em `GET /auditoria/`.
  - usuário sem `escritorio` ativo: 403.
- O teste é o **anti-P8 da matriz**: reverter o `papel_permitido(...)`
  para incluir um papel que hoje não tem acesso **falha** o teste;
  tirar um papel que hoje tem acesso **falha** o teste. A próxima
  etapa que mexer nisso tem de mexer de propósito, atualizando o
  teste junto, e não de passagem.
- Esta etapa **não** abre PE-36 nem toma decisão de quem pode ler o quê.
  PE-36 segue como **BAS-01** do plano mestre, com dono (Fred).

### CA-7 — varredura de contratos e restrições (declarada antes de escrever)

- Mesma postura das DL-017/018: a cada função nova ou alterada,
  `apps/{x}/services/` expõe o contrato com `@dataclass(frozen=True)` ou
  nome explícito, e o `views.py` recusa `chave não contratada` via
  `_campos_gravaveis` + `_recusar_dado_nao_contratado_na_atualizacao`.
- A BL-57 **herda** o contrato: o diff é construído sobre o
  `frozenset` que `_campos_gravaveis` devolve, não sobre uma cópia.
- Nenhuma view ganha parâmetro novo sem teste que prova a recusa.

### CA-8 — disciplina de redação

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

- Provar, mutação por mutação, cada um dos **oito** CA-1 a CA-8.
- Confirmar o **ponto de partida** que ficou medido:
  - `apps/empresas/views.py:72` é a fonte única dos campos graváveis do
    serializer (BL-196/DE-034), e o diff da BL-57 passa a derivar dela.
  - `apps/auditoria/views.py:17` continua restrito a ADMINISTRADOR e
    GESTOR; o teste da CA-6 fixa isso.
  - Nenhum `apps/*/admin.py` chama `registrar()` nem sobrescreve
    `save_model`/`delete_model`/`save_formset`; nenhum signal genérico
    `post_save`/`pre_delete` existe (a CA-4 fecha isso).
- A pergunta contábil que o Fred leva junto — CNPJ anterior e novo na
  trilha, com `acesso` em need-to-know de dois papéis — **não** é
  respondida pela DL-024. Ela volta como decisão dele, possivelmente
  com uma etapa própria.
- **Não pode** reabrir BL-261 (decisão contábil), BL-262 (etapa própria),
  BL-263 (BL-249 do arquiteto), nem tocar em BL-02 ou PE-36.

## Git

- **Branch de trabalho:** `claude/dl-024-execucao`, aberta
  a partir de `1b828e7`.
- **Branch de destino:** `main`, por PR. **O PR é parte da entrega** (achado
  A7/BL-260 herdado da DL-023): sem ele, o workflow "Regras do projeto" não
  roda, e dos três mecanismos impostos só dois são exercitados.
- **Ordem dos commits** (a do Fred: **atomicidade primeiro, gravações
  novas depois**; o signal do admin e a imutabilidade do log entram entre
  a BL-57 e a BL-50 para que a trilha nova já nasça à prova de
  `update()`/`delete()`):
  1. `feat(DL-024): atomicidade entre operação e registro de auditoria` — BL-14, base.
  2. `feat(DL-024): imutabilidade do RegistroAuditoria contra update/delete em massa` — BL-16, o log fica à prova de desvio antes de qualquer gravação nova.
  3. `feat(DL-024): trilha de PUT/PATCH com diff derivado do contrato` — BL-57, dentro do `transaction.atomic()` da BL-14 e respeitando a imutabilidade da BL-16.
  4. `feat(DL-024): trilha do painel administrativo via signal genérico` — BL-244, dentro da mesma transação, com lista explícita de modelos cobertos e exceções justificadas.
  5. `test(DL-024): fixar a matriz de acesso de /auditoria/` — CA-6, três papéis recebem 403, dois recebem 200, sem mexer no código de produção.
  6. `test(DL-024): cobrir o gate DEBUG=False sem PostgreSQL` — BL-50, quatro casos (gate ativo, sem URL, com URL PostgreSQL, `DEBUG=True`).
  7. `docs(DL-024): plano, decisão de BL-57 (campos derivados do contrato) e auditoria rodada 1`.
- **Validação local obrigatória antes do push**: `ruff check .`,
  `ruff format --check .`, `pytest apps/core/tests/test_documentacao_do_estado.py
  apps/auditoria/tests/ apps/empresas/tests/test_dl024_atomicidade_trilha.py
  apps/empresas/tests/test_dl024_trilha_update.py
  apps/empresas/tests/test_dl024_trilha_admin.py
  apps/core/tests/test_dl024_gate_db.py`. Suíte completa **só na CI**.

## Hipóteses e pendências a registrar

- **Hipótese:** o par `valores_anteriores` / `valores_novos` (mesmo
  padrão de `valores_antigos` da `excluir_ultimo_regime_tributario`,
  `apps/empresas/services.py:305`) é legível por humanos e por máquina
  (front + API), e a serialização do `RegistroAuditoria` aceita o par
  sem quebra. Se o front da `/auditoria/` pedir formato diferente, vira
  DL-025.
- **Hipótese:** Django permite trancar `delete()` e `update()` no `Meta` ou
  via `signals` sem custo de performance perceptível. Medir no fim.
- **Hipótese:** o signal genérico do admin (`post_save`/`pre_delete`) é
  ligado pelo nome da `class` do `ModelAdmin` (via `_meta.label`),
  não por uma lista literal de modelos — assim, novo `ModelAdmin`
  amanhã entra na trilha sozinho, na mesma postura da BL-57. Teste de
  derivação cobre.
- **Pendência:** o Fred leva a pergunta sobre CNPJ anterior/novo na
  trilha (dado de cliente em `/auditoria/`) junto com a pergunta
  contábil que já está com ele. Resposta dele fecha ou abre DL-025.
- **Pendência:** PE-36 (BAS-01) segue em aberto com o Fred. Esta
  etapa **não** a toca, e a CA-6 é o cinto de segurança: se alguém
  mudar a matriz de acesso de `/auditoria/` sem atualizar o teste,
  a suíte quebra.

## Histórico

- 2026-09-16: plano redigido, em planejamento, aguardando início. Corrigido
  em 2026-09-16 após medição do Fred: BL-57 deriva de
  `_campos_gravaveis(serializer)` (`apps/empresas/views.py:72`), formato
  é `valores_anteriores` / `valores_novos` (não aninhado), matriz de
  acesso de `/auditoria/` fica FIXADA por teste e não mexida; **BL-244**
  entra no pacote.
- 2026-09-16: execução retomada na branch `claude/dl-024-execucao`.
  `febdc9f` corrige dois desvios encontrados na revisão da rodada 1:
  `QuerySet.update()`/`delete()`/`bulk_update()` agora são bloqueados no
  manager de `RegistroAuditoria`, com limpeza referencial `SET_NULL`
  preservada por migração; e as gravações de estabelecimento e regime
  tributário passaram a compartilhar a transação com sua trilha. Foram
  acrescentados os testes de mutação correspondentes e os casos faltantes
  da CA-3. A prova runtime local ficou pendente, mas foi fechada pela CI
  posterior; a conciliação da lista de ModelAdmin da CA-4 continua pendente;
  ver a [auditoria rodada 1]
  (../auditorias/2026-09-16-dl-024-rodada-1.md).
- 2026-09-16: o PR #28 executou a suíte completa no head `5af2c19`.
  Após as correções dos cenários runtime (`2613343`, `da59b19` e
  `5af2c19`), o Backend passou com 1.345 testes e 2 pulados; Documentação e
  Regras do projeto também passaram. A validação runtime está fechada na CI;
  a etapa segue em validação pela divergência de CA-4 e pela revisão humana.
