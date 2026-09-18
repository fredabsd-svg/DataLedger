# DL-016-F5 — Backfill da FK `LancamentoContabil.competencia`

**Estado:** planejada em 2026-09-18. Não iniciada.

**Pré-requisito de:** DL-016-F3 (encerramento de competência). Sem F5, F3
encerraria competências que ainda têm lançamentos com `competencia_id
IS NULL`, quebrando a invariante "ao encerrar, todos os lançamentos
do mês estão vinculados à competência". F4 depende de F3.

**Onde esta DL se encaixa na DL-016:** é a Onda 2 da DL-016. Onda 1
(F1 + F2) está em `main` desde 2026-09-18 (PR #31, commit `fa15cf1`).
Onda 3 (F3 encerramento) e Onda 4 (F4 reabertura) dependem desta.

## Por que esta etapa vem agora

- DL-010 (importador em massa) está planejada mas parada; ela vai
  consumir competências existentes. Se F5 rodar antes, os lançamentos
  antigos já nascem com FK preenchida; se rodar depois, o importador
  precisa lidar com uma coluna parcialmente nula.
- F3 (encerramento) **não pode** rodar sem F5 — bloquearia o
  encerramento invocando "competência tem lançamentos sem FK". F3 está
  pronta para entrar no backlog depois que F5 fechar.
- A coluna `competencia` está como `null=True` no banco desde 2026-09-18.
  O plano original era "virar `null=False` em uma DL-XXX de aperto",
  mas isso só faz sentido **depois** de F5 rodar e o relatório
  mostrar zero órfãos.

## O que existe hoje

Tudo de F1 e F2 já está em `main`:

- `apps/contabilidade/models.py:Competencia` — modelo com 3 invariantes
- `apps/contabilidade/services.py:criar_lancamento.materializa_competencia` —
  `get_or_create` em savepoint próprio
- FK `LancamentoContabil.competencia` (PROTECT, `null=True`)
- 7 testes em `apps/contabilidade/tests/test_competencia.py`
- Migration `0004_competencia_e_competencia_no_lancamento.py`

O que falta: **preencher a FK nos lançamentos antigos** — todos aqueles
gravados antes de F2 entrar em produção. Eles continuam com
`competencia_id = NULL`.

## Escopo

Uma management command `backfill_lancamento_competencia` que:

1. Itera sobre `LancamentoContabil.objects.filter(competencia__isnull=True)`
   em batches via `.iterator(chunk_size=2000)`.
2. Para cada lançamento, deriva `(empresa_id, ano, mes)` a partir de
   `lancamento.empresa_id` e `lancamento.data` (já existente desde
   DL-006).
3. Faz `Competencia.objects.get_or_create(empresa_id=..., ano=..., mes=...)`
   — a `UniqueConstraint` existente cobre a invariante de não-duplicar.
4. Atribui o `competencia_id` em batch (`UPDATE ... WHERE competencia_id
   IS NULL`) para reduzir locks.
5. Re-roda o passo 3-4 uma segunda vez, curto, para pegar lançamentos
   que entraram durante a primeira passada (criados por `criar_lancamento`
   em concorrência).
6. Reporta no stdout os totais: lidos, competências criadas, FKs
   atribuídas, duração.

**Argumentos da command:**

- `--dry-run` (default `True`): não altera o banco, apenas conta e
  loga. Por padrão é seguro rodar sem medo.
- `--apply`: marca explicitamente que o operador entende o que está
  fazendo e quer efetivar.
- `--batch-size`: default 2000.
- `--max-passes`: default 2 (uma passada longa + uma curta para
  concorrência).

**Fora do escopo:**

- Não vira `null=False` na FK — isso é uma DL separada (DL-016-F6,
  não nomeada ainda) que depende do relatório desta command mostrar
  zero órfãos em produção real.
- Não fecha competências — isso é F3.
- Não reabre — isso é F4.
- Não migra competências entre empresas — `(empresa, ano, mes)` é
  uma chave natural aqui, e mudar isso exigiria o DE-019 reverso,
  que está fora do escopo.

## Decisão de modelagem, já tomada

**DE-019** (já em vigor): a competência é o **mês da data do
lançamento**, não um campo separado. Esta DL-016-F5 segue o mesmo
princípio: para descobrir a que competência um lançamento antigo
pertence, basta ler `lancamento.data.year` e `lancamento.data.month`
— não precisa de migração de dados nem de inferência por outro
campo.

## Critérios de aceite

1. **Idempotência:** rodar a command duas vezes seguidas não altera
   nada na segunda passada. Coberto por `WHERE competencia_id IS NULL`.
2. **Concorrência segura:** novos lançamentos criados durante o
   backfill por `criar_lancamento` (que já preenche a FK) ficam de
   fora naturalmente. Coberto por `.filter(competencia__isnull=True)`.
   A segunda passada curta serve apenas para reduzir a janela em que
   isso pode acontecer.
3. **Órfãos são pulados, não falham:** se um lançamento tiver
   `empresa_id` nula por INSERT direto no banco (burlando o ORM), a
   `IntegrityError` na FK do `get_or_create` de `Competencia` aparece
   visível no log — a command não mascara essa exception. Não há
   branch de "orfao" no código por design: `LancamentoContabil.empresa`
   é NOT NULL por schema desde DL-006 (FK com `on_delete=PROTECT` sem
   `null=True`), então o cenário é inalcançável via ORM. Antes do
   `--apply` em produção real, rodar
   `SELECT COUNT(*) FROM contabilidade_lancamentocontabil WHERE empresa_id IS NULL`
   e abortar se vier > 0 — esse procedimento é parte do runbook de
   deploy do F5 (rede de segurança operacional).
4. **Dry-run não toca o banco:** testado em CI com `pytest` que
   conta `Competencia.objects.count()` antes e depois, e afirma que
   o número é igual após `--dry-run`. (Aplicar essa invariante é
   simples: na flag `--dry-run`, a command não chama `update()` nem
   `get_or_create`, apenas conta.)
5. **Logs estruturados:** cada passada imprime totais em formato
   legível (não JSON; é para humano ler via terminal durante deploy).
6. **CI verde:** suíte de testes nova em
   `apps/contabilidade/tests/test_management_backfill.py` cobre
   os 5 cenários abaixo.

## Cenários de teste

| Cenário                          | Setup                                                                    | Expectativa                                          |
| -------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------- |
| **Competência já existe**        | `Competencia(2026, 9)` já criada; lançamento de set/2026 sem FK          | `Competencia` count não muda; FK atribuída           |
| **Competência a criar**          | Lançamento de ago/2026 sem FK                                            | `Competencia(2026, 8)` criada, FK atribuída          |
| **Dry-run não altera**           | Lançamento sem FK, rodar com `--dry-run` (default)                       | `Competencia` count não muda, FK permanece `None`    |
| **Idempotência**                 | Rodar `--apply` duas vezes seguidas                                      | 2ª passada não cria nada nem altera FK               |
| **Concorrência**                 | Lançamento criado entre duas passadas                                    | 2ª passada pega e atribui FK                         |

Não há teste de órfão: o cenário é fisicamente impossível pelo ORM
(`LancamentoContabil.empresa` é NOT NULL por schema desde DL-006),
e o branch de tratamento de órfão foi removido do código por
design (código morto = acoplamento ruim + complexidade sem
benefício). A defesa contra INSERT direto fica na verificação
operacional descrita no critério de aceite #3 acima.

## Riscos principais a vigiar

1. **Volume / lock contention.** UPDATE em tabela grande pode segurar
   locks se rodado em horário de pico. Mitigar com `--batch-size`
   baixo (default 2000, configurável) e recomendação operacional
   "rodar em janela de baixo tráfego". Em escala de 100k-1M de
   lançamentos, o esperado é alguns minutos; em escala maior,
   particionar a janela.
2. **Corrida com `criar_lancamento`.** Lançamentos criados durante
   o backfill podem ficar de fora se a iteração usar snapshot fixo.
   A cláusula `WHERE competencia_id IS NULL` no `update()` + uma
   segunda passada curta resolve.
3. **Reversibilidade.** Aplicada a FK não volta atrás com a command
   (ela só roda pra frente). Antes do `--apply` em produção, rodar
   `--dry-run` em staging idêntico, conferir diff, e ter plano de
   rollback documentado (ex.: script que salva os IDs antigos antes
   do apply).
4. **Orfão por INSERT direto no banco.** O caminho oficial (ORM)
   garante `empresa_id` NOT NULL. Um UPDATE/INSERT direto no
   banco que burla essa garantia resulta em `IntegrityError` na
   FK de `Competencia` — visível no log, não silenciado. A rede
   de segurança está em (a) CHECK constraint em `empresa_id IS NOT
   NULL` que vai entrar em DL-016-F6, e (b) verificação operacional
   `SELECT COUNT(*) ... WHERE empresa_id IS NULL` no runbook.

## Ondas

| Onda | Conteúdo | Status |
|---|---|---|
| F1 | Modelo `Competencia` + migration + admin | ✅ integrada (`fa15cf1`) |
| F2 | Vinculação automática em `criar_lancamento` | ✅ integrada (`fa15cf1`) |
| **F5** | **Backfill da FK (esta DL)** | 🟡 **em execução** |
| F3 | Encerramento de competência | ⏳ depende de F5 |
| F4 | Reabertura autorizada e auditada | ⏳ depende de F3 |
| F6 (sem nome) | Aperto: `competencia` vira `null=False` | ⏳ depende de relatório de F5 sem órfãos |

## Dependências externas

- Nenhuma. Esta DL é puramente uma management command de dados + sua
  suíte de testes. Não toca `services.py`, `models.py` (só leitura),
  `admin.py`, nem `restricoes.py`.
- DL-010 (importador em massa) **continua dependente** da DL-016
  estar fechada de ponta a ponta (F5 + F3 + F4) — mas pode começar
  a planejar a interface com a Competência enquanto F5 roda, desde
  que use apenas os caminhos oficiais (`Competencia.objects.get_or_create`).

## Auditoria

DE-004 obriga auditoria independente antes do merge. A rodada 1 da
DL-016 (e seu fechamento em DE-050) já cobre o lado "modelo e
service" da DL-016. Esta DL-016-F5 introduz **código novo** (a
management command e os testes dela) — portanto precisa de rodada
de auditoria própria. Estimativa: 1 rodada, com 5-7 pontos de
inspeção.

## Pendências conhecidas (de DE-050)

- Migration `0004` ainda precisa ser regenerada por `makemigrations`
  no primeiro deploy Python 3.12+. Esta DL-016-F5 não muda o schema,
  então não interfere nem depende disso.
