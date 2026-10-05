# DL-065 — Reclassificação de conta com movimento em competência fechada (BL-550)

**Demanda:** [BL-550](../projeto/backlog.md) do backlog, escolhida pelo Fred em
05/10/2026 como primeiro item da leva do módulo de Contabilidade.
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `fix/dl-065-reclassificacao-em-competencia-encerrada` → `main`.
**Risco:** **nível 1** — a regra toca *conta*, *competência e fechamento* e *o
documento entregue ao cliente* (AGENTS.md §3.1, pergunta única: "se isto
estiver errado, o contador entrega documento errado?" — sim). Exige plano,
critérios de aceite, testes de sucesso/erro/limite e **auditoria independente**.

## O defeito, medido no código

`Conta` tem quatro classificações. Duas delas são **linha de demonstração
entregue ao cliente**: `classificacao_dlpa` (CTB-13) e `classificacao_dmpl`
(CTB-14). Hoje **nenhuma** das duas consulta a competência antes de gravar:

- `classificar_conta_na_dlpa` (`services.py`) e `classificar_conta_na_dmpl`
  fazem `select_for_update()` na conta, `full_clean()` e `save()` — nenhuma
  das duas menciona `competencia`;
- `Conta.clean()` tem uma única guarda de transição, e ela cobre **só**
  `classificacao_patrimonial`;
- o `ContaAdmin` não declara `fields`, e o `ModelForm` grava os quatro campos
  **por fora dos três serviços** — sem `select_for_update` e sem a trilha
  `conta.classificacao_*_alterada`, só o diff genérico `conta.admin_atualizado`.

Efeito: trocar a linha da DLPA ou a coluna da DMPL de uma conta com movimento
em uma competência **encerrada** — ou **entregue**, que é o estado em que o
documento já foi ao cliente — reescreve, sem aviso e sem veto, a demonstração
daquele período. É a mesma classe de dano da guarda que a DL-033 já criou
para a classificação patrimonial, que existe exatamente porque *"editar uma
conta já movimentada reescreveria, em silêncio, Balanços já entregues ao
cliente"*.

## Decisões do Fred que valem aqui

| Origem | Decisão |
| --- | --- |
| **BL-550** | *"M3 (média) — reclassificar conta na DRE/DLPA altera demonstração de competência encerrada ou entregue; analista consegue"*. Critério aceito no backlog: *reclassificação com movimento em competência encerrada → 409, ou classificação por vigência*. |
| **05/10/2026** (esta demanda) | A trava vale para a **DLPA e a DMPL**. A **DRE continua livre**, como está desde a **DE-086**. A trava tem de fechar também o **admin**, que hoje escapa por fora dos serviços. |
| **DE-086** (26/09/2026, mantida) | A classificação da **DRE** é propriedade de apresentação: pode mudar com movimento, sempre, com trilha antes/depois. A consequência aceita é a DRE de um período passado refletir a classificação vigente no momento da emissão. **Esta demanda não toca na DRE.** |
| **RC-101** (DL-016) | "Entregue" é fato datado, e a reabertura de competência entregue é **sempre** recusada: *o ajuste passa a ser feito no mês aberto*. Esta é a regra que a trava estende das competências para a classificação da conta. |

## Base normativa — o que é norma e o que é decisão de produto

⚠️ **Esta demanda NÃO cita item de norma como fundamento, e essa é a
declaração correta.** O que ela corrige não é uma exigência de divulgação:
é a **coerência interna** do produto — a mesma coerência que a RC-101 já
estabeleceu para a competência e que a DL-033 já estabeleceu para a
classificação patrimonial. Nenhum item de NBC TG ou de lei foi lido para
autorizar esta trava, e **nenhum é inventado aqui**. Se um dia a regra
precisar de fundamento normativo, ele vem na nota explicativa (CTB-18), não
aqui.

A **rotina de referência** (manual do sistema de referência) **não foi lida
para esta demanda** — declarada como pendência, não como conformidade: a
pergunta feita ao manual seria "o sistema de referência trava a reclassificação
em período fechado?", e a resposta esperada ("não, o campo é livre") **não
autorizaria nem refutaria** esta regra, porque a trava é decisão de produto
do DataLedger, não reprodução de rotina. O que a DE-086 já registrou do
mesmo manual continua valendo para a DRE: lá o "Grupo DRE" é campo simples
do cadastro, sem restrição por movimento.

## A regra, em uma frase

> **Trocar** (inclusive remover) a classificação da DLPA ou da DMPL de uma
> conta que tem movimento próprio ou de descendente em competência
> **encerrada ou entregue** é recusado; a **primeira** classificação é
> sempre livre.

## Decisões de desenho (`arquiteto-senior`, reversíveis)

### E1 — A guarda mora em `Conta.clean()`, não em cada serviço

A regra é implementada **uma vez**, no `clean()` do modelo, com um `code`
de erro próprio. Isso é o que fecha o admin: o `ModelForm` do Django chama
`full_clean()`, e `Conta.clean()` é o ponto de passagem de **todo** caminho
validado — serviço, admin, serializer. Um guard nos três serviços deixaria o
admin exatamente como está hoje, que é o furo que o levantamento mediu.

### E2 — 409 no serviço, 400 do Django no admin: uma regra, duas traduções

`Conta.clean()` levanta `ValidationError` com `code` próprio. Os dois serviços
de classificação leem esse `code` e relançam como exceção de domínio
(`ClassificacaoAlteraPeriodoFechado`), que a API traduz para **409** e a tela
mostra como recusa de formulário. A **mensagem é uma só**, escrita no modelo:
duas mensagens para a mesma regra divergem assim que alguém edita uma.

Por que 409 e não 400: é conflito de **estado** (o período está fechado), não
entrada inválida — o mesmo tratamento de `CompetenciaEncerrada` em
`criar_lancamento` e em `zerar_resultado`.

### E3 — Sem consulta duplicada, e com o custo medido

A guarda roda dentro do `full_clean()` que o serviço já fazia, e só quando a
classificação **de fato** mudou (curto-circuito, como o BL-245 já mediu no
guard de natureza/tipo). Não há segunda consulta para "descobrir" o período:
a função devolve a competência junto com a recusa.

⚠️ **Duas retificações, ambas da auditoria.**

**A5** — a primeira versão deste texto afirmava que "conta sem movimento não
paga nada". **Não é verdade**, e a medição do auditor refutou: a guarda roda
sempre que a classificação muda, e uma troca em conta **sem** movimento paga
a consulta da árvore. O que o curto-circuito de fato evita é só a
**primeira** classificação (gravado `None` → valor) e a gravação que não muda
nada.

**N2 (reconferência)** — a versão seguinte trocou uma consulta por um laço
`EXISTS` sobre as competências fechadas, e o auditor mediu **507 consultas e
393 ms** com 480 períodos, dentro de uma transação que segura o `FOR SHARE` e
portanto bloqueia o fechamento durante todo esse tempo. A pergunta correta é
uma **interseção de conjuntos** — "algum mês com movimento está fechado?" — e
passou a ser feita como tal: uma consulta traz os `(ano, mês)` com movimento
da subárvore, e o cruzamento acontece em memória. O número de consultas é
**constante**, e o teste de regressão mede a mesma empresa com 1 e com 480
competências para exigir que ele **não cresça** — o defeito era o
crescimento, não o total.

### E4 — Nomear o período é obrigatório

A mensagem nomeia **qual** competência impede a troca, no formato
`mm/aaaa`, e diz se ela foi encerrada ou entregue. Recusa que não nomeia o
arquivo que precisa ser reaberto (ou o período em que o ajuste deve ser
lançado) devolve o trabalho ao usuário sem caminho.

### E5 — Recusa não grava nada

A verificação vem **antes** de qualquer `save()` e dentro da transação do
serviço, então a recusa não deixa rastro: nem valor alterado, nem registro na
trilha. Um `registrar()` de recusa seria novidade no módulo e criaria ruído
na trilha — a trilha registra o que **mudou**, e aqui nada mudou.

### E6 — Descendente conta, como nas guardas que já existem

A consulta sobe a subárvore inteira com `WITH RECURSIVE`, o mesmo desenho de
`_tem_movimento_proprio_ou_de_descendente` (BL-245): reclassificar um grupo
sintético com movimento herdado reescreveria a demonstração do grupo do mesmo
jeito.

### E7 — A DRE não entra, e um teste garante que não entre

A DE-086 continua valendo. O risco real desta demanda é **vazamento**: um
`code` mal copiado para o campo da DRE fecharia, sozinho, a única saída do
veto do A2 e tornaria a DRE do período inemitível. O critério 10 do plano é
exatamente esse teste.

### E8 — O movimento é lido por DATA, e é o que amarra a guarda à apuração

**Achado A1 da auditoria, confirmado por medição no banco.** A primeira
versão filtrava o movimento por `LancamentoContabil.competencia`; a guarda
ficava cega ao lançamento sem competência gravada — e `competencia_id` é
**anulável** (`information_schema` medido: `is_nullable = YES`; a restrição
`NOT NULL` da DL-016 F6 cobre `empresa_id`). Toda a camada de apuração lê o
movimento por `lancamento__data__gte/__lte` e nunca pela FK, então esse
lançamento entrava normalmente na DLPA do período encerrado.

A regra passou a filtrar por data, com a mesma aritmética de calendário que
os três pontos de apuração já usam (`calendar.monthrange`), escrita uma vez
em `_faixa_de_datas_da_competencia`. **Princípio:** guarda que filtra por um
critério diferente do que a apuração filtra é guarda que pode ser
contornada.

### E9 — A trava vem do módulo, e é `FOR SHARE`

**Achado A2 da auditoria, demonstrado com duas threads.** A guarda lia o
estado da competência sem lock, e o `encerrar_competencia` podía commitar
entre essa leitura e o commit da reclassificação — o mês terminava
encerrado com a classificação já trocada.

A correção **reusa o primitivo do módulo**,
`_travar_competencia_em_modo_compartilhado`, em vez de escrever um lock
novo: ele já sabe das três coisas que importam (que `FOR SHARE` é
PostgreSQL, que fora dele a degradação tem de ser avisada e não silenciosa, e
que o estouro de `lock_timeout` vira erro de domínio). Django **não expõe**
`FOR SHARE` por `QuerySet` — só `FOR UPDATE`/`FOR NO KEY UPDATE` —, o que
explica o SQL cru dele e o meu. O `FOR SHARE` não impede o fechamento:
impede que ele passe **por cima** da reclassificação, e qualquer ordem passa
a ser legítima.

## Fora do escopo

- **A classificação da DRE** — decisão do Fred, DE-086 mantida.
- **`classificacao_patrimonial`** — já tem guarda **mais forte** (bloqueia
  com movimento em qualquer competência, inclusive aberta). Não é tocada, e
  as duas regras convivem porque respondem a perguntas diferentes.
- **Classificação por vigência** — a alternativa que o backlog aceitava
  ("reclassificar com movimento em competência encerrada → 409, **ou**
  classificação por vigência"). Não escolhida: vigência exigiria versionar as
  quatro classificações da conta e recontar demonstrações já emitidas, que é
  um projeto da Onda 2 e muda a natureza do dado. A trava é reversível
  (E1–E7 são locais), então a decisão pode ser reaberta.
- **Demonstração já emitida que diverge** — a DFC e as demais virão com a
  conciliação própria; aqui a regra é só não deixar a reclassificação entrar.

## Critérios de aceite

| # | Critério | Onde é testado |
| --- | --- | --- |
| 1 | Trocar a linha da DLPA com movimento em competência **aberta** é aceito, e a trilha registra antes/depois | `test_dl065_dlpa.py` |
| 2 | Trocar a linha da DLPA com movimento em competência **encerrada** é recusado com **409**, e a mensagem nomeia `mm/aaaa` | `test_dl065_dlpa.py` |
| 3 | O mesmo para a coluna da DMPL (encerrada) | `test_dl065_dmpl.py` |
| 4 | A **primeira** classificação é livre mesmo com movimento em competência encerrada | `test_dl065_dlpa.py` |
| 5 | **Remover** a classificação é troca e é recusado no mesmo caso | `test_dl065_dmpl.py` |
| 6 | Movimento de **descendente** bloqueia a conta sintética | `test_dl065_dlpa.py` |
| 7 | Competência **entregue** produz mensagem própria, dizendo entregue | `test_dl065_dlpa.py` |
| 8 | O **admin** não escapa: `full_clean()` recusa e o `ModelForm` mostra o erro | `test_dl065_admin.py` |
| 9 | A recusa **não grava**: valor anterior intacto e **nenhum** registro na trilha | `test_dl065_dlpa.py` |
| 10 | A **DRE continua livre** com movimento em competência encerrada (a DE-086 não foi revogada) | `test_dl065_dre_livre.py` |
| 11 | Isolamento: conta de **outro escritório** dá 404 e **não** dispara a guarda | `test_dl065_dlpa.py` |
| 12 | Sem regressão: `apps/contabilidade` completo igual à linha de base | suíte |
| 13 | `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check` limpos | comandos do projeto |

### Cenários de teste obrigatórios

- **Sucesso:** primeira classificação; troca com período aberto; conta sem
  movimento em período fechado (troca livre, porque nada muda).
- **Erro:** competência encerrada; competência entregue; descendente com
  movimento; remoção.
- **Limite:** competência do **mês seguinte** ao movimento (é o caso que a
  reclassificação de hoje quebra sem ninguém perceber); mais de uma
  competência fechada com movimento (a mensagem nomeia a mais recente);
  período reaberto depois (a trava **deixa de existir** — a regra acompanha o
  estado, não um registro de que houve recusa).

## Impacto, riscos e reversão

- **Dados:** nenhuma migração, nenhum backfill, nenhuma reescrita. O
  `Meta.constraints` do modelo não muda.
- **Cálculo:** nenhuma fórmula muda. A trava age antes do `save()`.
- **Contrato:** a API ganha um 409 novo **na mesma rota** que já existia; quem
  recebia 200 passa a receber 409 com `detail` — é a mudança de comportamento
  que o BL-550 pede, e ela é o objeto da demanda.
- **Desempenho:** três consultas, **independentes de quantos meses a empresa
  já fechou** (achado N2). O atalho é: conta sem movimento nenhum sai em duas;
  conta com movimento paga a travagem e a verificação, e para na competência
  mais recente que fecha o cruzamento. É o preço de uma regra que decide por
  período — o mesmo que a classificação patrimonial já pagava.
- **Permissões e isolamento:** nada muda. `PodeEscriturar` continua decidindo
  a porta; o filtro `empresa=empresa` continua decidindo a visibilidade, e a
  guarda só roda **depois** do `get_object_or_404`.
- **Reversão:** apagar o bloco de `clean()` e os dois `except` das views
  restaura o comportamento anterior. Não há dado, migração ou estado
  compartilhado para desfazer.

## Equipe e arquivos

| Papel | Arquivos |
| --- | --- |
| `desenvolvedor-pleno` | `apps/contabilidade/models.py`, `services.py`, `views.py`, `views_web.py` |
| `desenvolvedor-pleno` (testes) | `apps/contabilidade/tests/test_dl065_*.py` |
| `auditor-qa` | `docs/auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md` — **sem escrita de código** |

## Evidências e integração

| Item | Classificação | Onde |
| --- | --- | --- |
| Defeito medido antes da correção | Inspecionado | este plano, "O defeito, medido no código" |
| Ambiente de verificação | Testado | PostgreSQL 16.15 local; ver estado do projeto |
| `competencia_id` anulável no banco | Testado | `information_schema.columns` → `is_nullable = YES` (confirma o A1) |
| Critérios 1 a 11 | Testado | `apps/contabilidade/tests/test_dl065_*.py` |
| Correções A1, A2, A3, A4, A5 e A7 | Testado | regressões `test_a1_*`, `test_a2_*`, `test_a4_*`, `test_a7_*` |
| Correções N1, N2 e N3 da reconferência | Testado | regressões `test_n1_*`, `test_n2_*`, `test_n3_*` — **sem** auditoria independente, ver o relatório |
| Critérios 12 e 13 | Testado | suíte e comandos do projeto |
| Auditoria independente | Testado | [rodada 1 e reconferência](../auditorias/2026-10-05-dl-065-auditoria-e-reconferencia.md): **APROVADA COM RESSALVAS** e depois **REPROVADA** |
| A6 — script de medição grava a coluna da DMPL sem a guarda | **Fora do escopo, aceito** | `scripts/medir_identificacao_do_emitente.py:883-885`; BL-628 |
| Teste do desfecho final da corrida (A2) | **Não testado** | ver o docstring de `test_a2_a_guarda_segura_a_competencia_aberta` — sem ponto de pausa dentro da guarda, o desfecho dependeria do agendamento; o auditor mediu 8/8 com o fechamento vencendo, e o outro ramo é legítimo por desenho |
| Porta HTTP real sob `lock_timeout` | **Não testado** | o auditor mediu o serviço e o `ModelForm`, que é o que as duas portas encapsulam; a requisição em si ficou de fora |

**Custo medido da guarda (achado A5):** troca em conta **sem** movimento
paga a consulta da árvore; o que o curto-circuito evita é a primeira
classificação e a gravação que não muda nada. Registrado porque a primeira
versão deste plano afirmava o contrário.

⚠️ **Nota de ambiente, declarada e não explicada:** nesta máquina o
`DATABASE_URL` do `.env` aponta para **SQLite**, que produz 64 reprovações
falsas em `apps/contabilidade` (o projeto exige PostgreSQL para verificação
de número — DE-020). Um cluster **PostgreSQL 16.15** foi criado em
`C:\Users\conta\AppData\Local\PostgreSQL\dataledger` na porta 5433 para as
verificações desta demanda. **A `.env` do repositório não foi alterada.**
