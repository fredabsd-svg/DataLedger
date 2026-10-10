# Reconferência da DL-089 — 10/10/2026

## Parecer

**APROVADA COM RESSALVAS.**

- Não encontrei achado bloqueador nem de alta gravidade.
- Os oito achados da rodada 1 (A1 a A8) estão resolvidos ou tratados por decisão registrada no plano. A4 e A7 não têm código.
- Os 8 testes antigos alterados mantêm a expectativa; só o papel mudou.
- A migração 0026 foi aplicada, revertida e reaplicada com dados no formato da main, sem reprovar nenhum.
- Dos 26 mutantes, 25 morreram com os testes do desenvolvedor. O m15 só morreu com um teste meu (R2).
- Ressalvas (gravidade baixa):
  - R1: origem automática ainda é aceita sem documento de origem. A 0026 ainda pode ser editada e depois da main isso exigirá a 0027. Recomendo decidir antes do merge.
  - R2: o isolamento entre empresas do seletor do Diário não tem teste.
  - R3: a mensagem do 403 e o campo `origem` da trilha enganam quando o alvo é zeramento ou importação legada.
  - R4: a documentação ainda contradiz o código.
- As cinco limitações declaradas pelo desenvolvedor foram conferidas e são reais. A limitação 1 tem efeito concreto: o banco `dev_dl089` já aplicou a 0026 antiga (R5).
- A suíte completa não foi rodada, por instrução.

## Versão e ambiente

- Cópia destacada `/home/user/wt-rc089`, commit `bab28e7`. Não troquei de commit, não criei branch, não fiz commit nem push.
- Python 3.13.16 local (a integração contínua usa 3.14), PostgreSQL 16, Django 6.1.2.
- Bancos descartáveis `aud_rc089`, `aud_rc089p` e `aud_rc089m`, mais os `test_*` do pytest. Todos foram removidos.
- Não precisei do `.env`: a `DATABASE_URL` já vinha do ambiente.
- Scripts e sondas ficaram em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud089rc/`. Os mutantes rodaram em cópias de `git archive HEAD` (`clean/` e `mut_copy/`), nunca na cópia de trabalho.
- Dados da main: extraí o commit `3f3206c` (merge-base com `origin/main`) para `main_copy/` e semeei um banco na 0025 com os helpers da própria main.
  - Manual, estorno, chave `zeramento:`, duas importações efetivadas pelo serviço real e chave `api:abc-123`.
- Efeitos colaterais:
  - A execução de `apps/core` criou um `db.sqlite3` vazio e ignorado pelo Git na cópia. Removi.
  - No fim, `git status --short` está vazio e `git diff --stat` não mostra nada em `/home/user/wt-rc089`.

## Tabela A1 a A8

| # | Situação | Evidência | Classe |
|---|---|---|---|
| A1 (importação anterior à 0026 escapava da BL-73) | **Resolvido** | No banco migrado da 0025 para a 0026, os lançamentos 8 e 9 (chave `importacao:`, origem `manual`) deram NEGADO para ANALISTA, FINANCEIRO, PARALEGAL, CLIENTE e sem papel, e passaram para ADMINISTRADOR e GESTOR. `services.py:1267-1291`. O vínculo com `LancamentoImportado` é sinal independente da chave e tem teste (`test_a1_lancamento_vinculado...`). Os mutantes m03, m04 e m01 morreram. | Testado |
| A2 (zeramento estornável por quem só escritura) | **Resolvido pela decisão do plano** | Lançamento 7 (`zeramento:`, origem `manual`): NEGADO para ANALISTA e FINANCEIRO, aceito para ADMINISTRADOR e GESTOR. API: 403 sem gravar nada, 201 para gestor e administrador. O mutante m02 morreu. | Testado |
| A3 (T1 a T4) | **Resolvido** | T1 (`db_default`), T2 (backfill combinado, origem e documento), T3 (identificador vazio ou com espaço) e T4 (dado gravado no estado 0025) existem e rodam. Os mutantes que sobreviveram na rodada 1 agora morrem: m17 virou m24, m23 virou m25 e m27 virou m26. | Testado |
| A4 (documento → lançamentos sem consumidor) | **Tratado por decisão** (rota fica para a integração fiscal) | Está no plano, mas não em `backlog.md` (ver R4). Sem código nesta correção. | Inspecionado |
| A5 (Diário filtrado, Razão, rótulo) | **Resolvido** | Cabeçalho "Origem" e mensagem de vazio citam a origem. "Escrita fiscal" só aparece quando a empresa tem lançamento dessa origem (ou quando é o filtro pedido), sem "(reservado)". DE-101 registra o Razão sem filtro. Os mutantes m13, m14, m16, m17 e m18 morreram. | Testado |
| A6 (pareamento origem × tipo; identificador) | **Parcialmente resolvido** | O pareamento está no serviço e na CHECK nova. Espaço nas pontas e vazio são recusados. Continua aceita a origem automática sem documento algum, no serviço e no banco (R1). | Testado |
| A7 (alcance do "automático") | **Resolvido (sem código)** | BL-66 já diz `origem == escrita_fiscal`, nunca "não manual". | Inspecionado |
| A8 (403 sem rastro) | **Resolvido** | `lancamento.estorno_negado` é gravado fora do `atomic` (`views.py:1044-1058`). Em 6 execuções, `detalhes` tinha só `papel`, `origem` e `motivo`. Os mutantes m11, m12 e m21 morreram. PARALEGAL e CLIENTE recebem 403 de `PodeEscriturar` antes do serviço, então não geram trilha. É coerente com a BL-73, que trata do serviço. | Testado |

### Os 8 testes antigos alterados

- **Conferência:** li o diff dos cinco arquivos. Nos 10 pontos de chamada de `estornar_lancamento` (8 testes) só entrou `papel=Papel.GESTOR`, e dois arquivos ganharam o import de `Papel`. Há reformatação de linha, e nenhuma asserção, dado ou expectativa mudou.
- **Passam hoje:** `pytest apps/contabilidade` inteiro passou.
- **Coerência com a decisão A2:** o zeramento é criado por `PodeFecharCompetencia` (ADMINISTRADOR e GESTOR). O estorno dele agora exige a mesma matriz (`PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA`).
- **Fluxos legítimos de quem fecha:**
  - Quem fecha continua zerando.
  - `estornar_lancamento` só é chamado em `views.py:1024`. Nem `zerar_resultado` nem a reabertura estornam sozinhos.
  - Nenhum fluxo de fechamento foi quebrado.
- **Botão que daria 403:** não existe. Nenhum template ou JS oferece estorno de lançamento contábil (`grep` em `templates/` e `static/`). Os "Estornar" do fiscal são estornos de escrituração, outra operação. A API é o único caminho.

## Limitações declaradas

1. **Banco local que aplicou a 0026 antiga precisa ser recriado.** Confirmada, com efeito real.
   - O `django_migrations` do `dev_dl089` registra a 0026 e o banco não tem `ck_lancamentocontabil_origem_pareada_ao_documento`. A `documento_consistente` dele é a antiga.
   - O `migrate` não reaplica, então haveria deriva silenciosa. O `dev_dl089_c` já tem a CHECK nova.
   - A 0026 não está na main, então só afeta bancos de desenvolvimento. Antes do merge, confirme que nenhum ambiente compartilhado a aplicou. Foi uma consulta só de leitura.
2. **Estorno de legado sai com origem `manual`.** Confirmada: `origem=manual` no estorno dos lançamentos 7, 8 e 9. O estorno perde o elo de origem e de documento. É coerente com o original ser `manual`, e o desenvolvedor documentou isso. Não afeta a regeração, que só alcança `escrita_fiscal`.
3. **A CHECK aparar só espaço ASCII.** Confirmada por INSERT em SQL: `'12\t'` e `'12\n'` passam na CHECK. O serviço recusa os dois (`"1\t"` recusado). O banco é só o piso, como o desenvolvedor disse.
4. **O detalhe do lançamento mostra "(reservado)".** Confirmada: `views_web.py:3164` usa `OrigemLancamento(...).label` ("Escrita fiscal (reservado)"). O documento NF-e/NFS-e também carrega "(reservado)" (`models.py:2306-2307`). Cosmético. Nenhuma origem `escrita_fiscal` existe hoje, e o jargão só aparece quando existir.
5. **Suíte completa local 9.236/1/55.** **Não testado**, porque não rodei a suíte inteira. A falha de ambiente que ele cita apareceu na minha execução de `apps/core`. É `test_versao_minima_python` (sintaxe do Python 3.14).

## Achados novos

### R1 (baixa) — Origem automática sem documento de origem ainda é aceita

- **Requisito:** escopo 2 do plano (documento por tipo e identificador estável); chave natural da BL-66. É o que sobrou do A6.
- **Local:**
  - `apps/contabilidade/services.py:739-745` (`_origem_e_documento_validos` devolve `(origem, None, None)` quando `documento_origem is None`).
  - CHECK `ck_lancamentocontabil_origem_pareada_ao_documento`, que começa com `tipo IS NULL OR ...`.
  - `models.py:~2587`.
- **Evidência executada:**
  - `criar_lancamento(origem=IMPORTACAO)` e `criar_lancamento(origem=ESCRITA_FISCAL)` sem `documento_origem` foram gravados com `doc=None/None`.
  - O INSERT em SQL `('importacao', NULL, NULL)` e `('escrita_fiscal', NULL, NULL)` também passou.
- **Impacto:** pode entrar lançamento automático sem identificador estável. Nenhum produtor atual faz isso. A integração fiscal pode produzir um por engano. Depois da main, corrigir exige a 0027 sobre dado existente.
- **Correção recomendada:**
  - No serviço, exigir `documento_origem` quando a origem não é `manual`.
  - Na CHECK, acrescentar `origem = 'manual' OR documento_origem_tipo IS NOT NULL`.
  - Editar a própria 0026 (a mesma regra de A6) e ajustar os testes que criam lançamento automático sem documento.
  - Se o Fred preferir permitir, registrar a decisão em `decisoes.md`.
- **Verificação:**
  - `criar_lancamento(origem=IMPORTACAO)` sem documento levanta `LancamentoInvalido`.
  - O INSERT em SQL com `('importacao', NULL, NULL)` é recusado pela CHECK.

### R2 (baixa) — O isolamento por empresa do seletor do Diário não tem teste (mutante m15 sobrevive)

- **Requisito:** isolamento entre empresas.
- **Local:** `services.py` (`existe_lancamento_de_origem`, o `filter(empresa=empresa, origem=origem)`) e `views_web.py` (`_opcoes_de_origem_do_diario`).
- **Evidência:** com o `filter` sem `empresa=`, os 150 testes do `test_dl089_*` passaram. O mutante só morreu com a minha sonda `test_diario_seletor_isolado_por_empresa`.
- **Impacto:** se alguém tirar o filtro, o seletor mostra "Escrita fiscal" quando outra empresa, de outro escritório, tem lançamento dessa origem. O vazamento seria só um booleano, mas é entre clientes.
- **Correção recomendada:** acrescentar o teste abaixo em `test_dl089_correcao_diario.py`.
  ```python
  def test_a5_seletor_nao_ve_escrita_fiscal_de_outra_empresa(client, cenario):
      # cenario: empresa A sem lançamento fiscal; empresa B (outro escritório)
      # com um lançamento origem=ESCRITA_FISCAL, documento=(ESCRITURACAO_NFE, "k1")
      assert existe_lancamento_de_origem(empresa=A, origem=ESCRITA_FISCAL) is False
      sel = seletor(client.get(url(A), PERIODO).content.decode())
      assert 'value="escrita_fiscal"' not in sel
  ```
- **Verificação:** o mutante m15 passa a falhar.

### R3 (baixa) — Mensagem do 403 e trilha enganosas para zeramento e importação legada

- **Local:**
  - `services.py:~1334-1339`, mensagem "(escrita fiscal ou importação)".
  - `views.py:1051-1057`, `detalhes.origem = lancamento.origem`.
- **Evidência:** ANALISTA tentando estornar o zeramento (lançamento 7) recebe NEGADO. Na API, a mensagem fala em "escrita fiscal ou importação", e a trilha grava `origem: "manual"` junto com `motivo: "origem_automatica_sem_permissao"`.
- **Impacto:** quem lê a trilha ou a tela vê "automático" e "manual" juntos. Não afeta a segurança.
- **Correção recomendada:** mensagem genérica ("lançamento gerado pelo sistema"). Gravar na trilha o critério que ativou a regra (`origem`, `chave_importacao`, `chave_zeramento` ou `vinculo_importacao`).
- **Verificação:** teste da mensagem e do `detalhes` para cada critério.

### R4 (baixa, documentação) — Texto de estado contradiz o código

- **Local:**
  - `docs/projeto/requisitos.md` HI-150 diz "O zeramento do resultado continua `manual`" e o estorno é "verificado ... na tela". Não há tela de estorno de lançamento contábil. HI-150 também não cita A1 nem A2 como decisão.
  - `docs/projeto/decisoes.md` só tem DE-101 sobre esta etapa. A1 e A2 estão no plano, e a rodada 1 pediu registro em `decisoes.md`.
  - A4 (rota documento → lançamentos para a integração fiscal) está só no plano, sem item no backlog.
- **Correção recomendada:** o arquiteto atualiza HI-150, acrescenta uma DE para A1 e A2 e abre um item de backlog para A4. O commit não toca `docs/`.

### R5 (baixa) — Deriva silenciosa em bancos que aplicaram a 0026 antiga

- Registrada na limitação 1. A recomendação é recriar os bancos de desenvolvimento afetados e confirmar que nenhum ambiente compartilhado a aplicou.

## Mutantes

26 mutantes sobre `git archive HEAD`, nas cópias `clean/` e `mut_copy/`, com `mutate.py` e `run.sh`. A suíte alvo foi `test_dl089_*.py` mais a sonda. Nenhum mutante foi aplicado na cópia de trabalho; o `git status` dela segue vazio.

| # | Mutante | Resultado |
|---|---|---|
| m01 | tira o `lower()` da chave | morreu (`test_a1_a2_predicado_compara_prefixo...[IMPORTACAO:...]`) |
| m02 | tira o prefixo `zeramento:` | morreu |
| m03 | tira o prefixo `importacao:` | morreu |
| m04 | tira o vínculo `LancamentoImportado` | morreu |
| m05 | serviço sem o pareamento | morreu (`...[importacao-escrituracao_nfe]`) |
| m06 | pareamento invertido (`IMPORTACAO` → NF-e) | morreu, mas incidentalmente (quebra a importação legítima) |
| m07 | CHECK sem NFS-e | morreu (`...coerente_passa_pela_check[escrita_fiscal-escrituracao_nfse]`) |
| m08 | CHECK pareada com `isnull False` | morreu, mas incidentalmente |
| m09 | CHECK sem `btrim = id` | morreu (T3 `[ 12]`) |
| m10 | serviço aceita espaço nas pontas | morreu |
| m11 | trilha da negativa removida | morreu (`test_a8_tentativa_negada...`) |
| m12 | trilha dentro do `atomic` | morreu (`RegistroAuditoria.DoesNotExist`: a trilha é desfeita) |
| m13 | seletor sempre com escrita fiscal | morreu |
| m14 | seletor sem a exceção do filtro pedido | morreu |
| m15 | `existe_lancamento_de_origem` sem `empresa` | **sobreviveu** aos testes do desenvolvedor (150 passed). Morreu só com a minha sonda (R2). |
| m16 | cabeçalho sem a origem | morreu |
| m17 | mensagem de vazio sem a origem | morreu |
| m18 | rótulo "(reservado)" volta | morreu |
| m19 | predicado só olha a origem (comportamento da rodada 1) | morreu |
| m20 | estorno sem checar a permissão | morreu |
| m21 | trilha grava o corpo da requisição | morreu |
| m22 | serviço aceita escrita fiscal com lote | morreu (`...[escrita_fiscal-importacao_lancamentos]`) |
| m23 | CHECK pareada frouxa (aceita qualquer origem com lote) | morreu |
| m24 | sem `db_default` (m17 da rodada 1) | morreu (T1) |
| m25 | backfill ignora origem e documento (m23 da rodada 1) | morreu (2 testes T2) |
| m26 | CHECK sem a cláusula "não vazio" (m27 da rodada 1) | morreu (T3 `[]`) |

Os mutantes m06 e m08 foram substituídos por m22 e m23, que são mais precisos.

## Verificações

| Comando | Resultado real |
|---|---|
| `ruff check --no-cache .` | `All checks passed!` |
| `ruff format --check --no-cache .` | `625 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `pytest apps/contabilidade -q` (uma invocação) | `3121 passed, 5 skipped, 2 warnings, 4 subtests passed in 439.40s` |
| `pytest apps/core apps/auditoria -q` | `1 failed, 1169 passed, 12 skipped in 68.99s`. A falha é `test_versao_minima_python` (Python 3.13). |
| `pytest test_restricoes + test_dl019_varredura_de_restricoes + test_dl023_varredura_admin + test_documentacao_do_estado` | `289 passed` |
| `pytest test_aud089rc_sonda.py` (minhas 6 sondas) | `6 passed` |

### Migração 0026

- **Com dados da main (0025):**
  - `migrate` até a 0026: `Applying contabilidade.0026_dl089_origem_do_lancamento... OK`. Os 11 lançamentos ficaram `manual`, com documento nulo e chaves intactas.
  - `migrate contabilidade 0025`: `Unapplying ... OK`, e as colunas de origem desapareceram.
  - Nova ida: `OK`, `manual|11`.
- **Reversão com dado automático:** `RuntimeError: ... não pode ser revertida porque o banco tem 1 lançamento(s) de origem automática ...`. As colunas e as 5 CHECKs permaneceram, e a migração ficou na 0026.
- **Recusa pelas CHECKs (INSERT em SQL):**
  - Espaço nas pontas, `''` e `'   '`.
  - Pares incompatíveis: `importacao` + NF-e e `escrita_fiscal` + lote.
  - `manual` + documento e origem `lixo`.
- **Passam:** os pares coerentes, `'12\t'` e `'12\n'` (limitação 3).
- **Dado legítimo da main:** nada foi reprovado, porque todo dado legado vira `manual` com documento nulo.

### Isolamento e autorização no servidor (sondas, `test_aud089rc_sonda.py`)

- ANALISTA do escritório A recebeu 404 nos três casos de URL cruzada. Foram eles: lançamento do escritório B com a empresa B; com a empresa A1; e lançamento da empresa A1 pela URL da A2.
- Em nenhum dos casos houve trilha `estorno_negado` nem estorno gravado.
- Negativas de ANALISTA: 2 registros, com o escritório e o usuário certos, `detalhes` só com `{papel, origem, motivo}`, e nenhum corpo da requisição nem dado de outra empresa.
- PARALEGAL e CLIENTE recebem 403 sem trilha de negativa.
- Estorno de estorno de legado dá 400, sem trilha.
- O seletor do Diário é isolado por empresa na tela; ver R2 para o que falta na suíte oficial.

## O que não foi testado

- A suíte completa (por instrução). Não confirmei os números 9.236/1/55 do desenvolvedor.
- SQLite. A etapa é PostgreSQL-first.
- `scripts/validate-docs.ps1`: o commit não toca `docs/`.
- Impressão real do Diário filtrado, em papel ou PDF. Só li o HTML e o cabeçalho.
- Concorrência de estornos sob o novo predicado. O predicado é só leitura, depois de `select_for_update`.
- Migração sobre tabela grande, e `pg_restore --disable-triggers`.
- Zeramento real via `zerar_resultado` na empresa semeada (faltava parâmetro contábil). Usei o lançamento com a chave `zeramento:` e, nos testes do desenvolvedor, o `zerar_resultado` real.
- Validação profissional das regras contábeis: esta auditoria não a substitui.

## Arquivos relevantes

- `/home/user/wt-rc089/apps/contabilidade/services.py` (predicado em 1267-1291; pareamento em 739-745; identificador em ~765-790)
- `/home/user/wt-rc089/apps/contabilidade/models.py` (`TIPOS_DE_DOCUMENTO_POR_ORIGEM`, CHECKs, `db_default`)
- `/home/user/wt-rc089/apps/contabilidade/migrations/0026_dl089_origem_do_lancamento.py`
- `/home/user/wt-rc089/apps/contabilidade/views.py` (1010-1062, estorno e trilha da negativa)
- `/home/user/wt-rc089/apps/contabilidade/views_web.py` (3441-3475, seletor do Diário; 3164, rótulo do detalhe)
- `/home/user/wt-rc089/templates/contabilidade/diario.html`
- `/home/user/wt-rc089/apps/contabilidade/permissoes.py`
- `/home/user/wt-rc089/apps/contabilidade/tests/test_dl089_correcao_{estorno,banco,migracao,servico,diario}.py`
- `/home/user/wt-rc089/docs/projeto/requisitos.md` (HI-150, R4)
- `/home/user/wt-rc089/docs/projeto/decisoes.md` (DE-101)
- Sondas, mutantes e resultados em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud089rc/`:
  - `test_aud089rc_sonda.py`
  - `probe_legacy.py`, `probe_servico.py`, `probe_reverse.py`, `seed_main.py`
  - `mut/mutate.py`, `mut/run.sh`
  - `mut/resultado*.txt`
  - `pytest_contab.log`

Auditoria de software não substitui validação profissional das regras contábeis e legais. Este relatório não declara ausência de defeitos, apenas os que as verificações acima alcançaram.
