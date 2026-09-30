# Auditoria DL-052 — reconferência

## 1. Escopo e commit auditado

- Demanda: DL-052 (nível 1), plano em [DL-052](../planos/DL-052-integridade-do-livro-e-do-acesso.md). Reconferência única, pedida pelo AGENTS.md §3.1: não haverá terceira rodada. Este parecer decide.
- Relatório anterior: [rodada 1](2026-09-30-dl-052-rodada-1.md) (achados D1 a D9).
- Branch `claude/zealous-goldberg-jr5ggu`. `git rev-parse HEAD` devolveu `d847e7557f682211534849dc31b3c845c03f0800` (confere com o pedido, d847e75).
- Diff da correção: `git diff 1e53bc8..d847e75` (13 arquivos, +874/−4; o commit 29b4263 só traz documentação). Migrações novas: `0015_dl052_r1_tipo_do_item_valido`, `0016_dl052_r1_item_so_em_lancamento_da_transacao`, `0017_dl052_r1_backfill_so_na_mesma_empresa`.
- Ambiente: contêiner Linux, Python 3.13.12, PostgreSQL 16 local. A CI usa Python 3.14, que NÃO foi rodado aqui.
- Método:
  - suíte completa e verificações estáticas no repositório, em banco próprio `dataledger_reconf052`;
  - experimentos de burla, migração, dump e mutação só numa cópia descartável (`git archive d847e75`) em `/tmp/claude-0/.../scratchpad/rec/copia*` e em bancos com sufixo `_reconf052_*`, todos removidos no fim;
  - nenhum arquivo versionado foi criado, editado ou apagado;
  - nenhum auxiliar foi acionado.
- Fora do alcance: Python 3.14; `pwsh` (ausente, então o `validate-docs.ps1` oficial não rodou); concorrência entre transações simultâneas nos gatilhos adiados; `TRUNCATE` e dono da tabela desligando gatilho (declarados pelo plano).

## 2. Comandos executados e saídas reais

| Comando | Saída |
| --- | --- |
| `git rev-parse HEAD` | `d847e7557f682211534849dc31b3c845c03f0800` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `326 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python scripts/gerar_agentes.py --verificar` | `OK: 7 papéis, todos os derivados sincronizados.` |
| `pytest -p no:cacheprovider -q` completo (DATABASE_URL em `dataledger_reconf052`) | `1 failed, 3681 passed, 50 skipped, 2 warnings, 4 subtests passed in 263.73s (0:04:23)` |
| Falha única | `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (a conhecida, exige Python 3.14) |
| `python manage.py migrate` em banco vazio (cópia de d847e75) | todas as migrações `OK`, inclusive `contabilidade.0015`, `0016`, `0017` e `livro_caixa.0009` |
| `migrate contabilidade 0014` | `Unapplying contabilidade.0017... OK`, `0016... OK`, `0015... OK`. Após a reversão `pg_trigger`: `trg_item_lancamento_balanceado`, `trg_item_lancamento_imutavel`, `trg_lancamento_contabil_balanceado`, `trg_lancamento_contabil_imutavel`, `trg_parametro_contabil_sem_sobreposicao`. Sumiram `trg_item_lancamento_so_em_lancamento_novo`, `trg_lancamento_contabil_marca_transacao` e `ck_itemlancamento_tipo_valido`. O corpo de `contabilidade_recusar_alteracao_do_livro` voltou ao da 0013 (sem `EXISTS`). |
| `migrate` (volta a 0017) | `Applying contabilidade.0015... OK`, `0016... OK`, `0017... OK`; gatilhos e constraint reapareceram. |
| Pré-conferência da 0015 (banco em 0014 com item `tipo='lixo'` dentro de lote que tem débito e crédito válidos) | `RuntimeError: DL-052: a migração 0015 não pode ser aplicada porque o banco já contém item de lançamento com tipo diferente de 'debito'/'credito' (nenhum dado foi alterado). 1 lote(s): [1] ...`. `showmigrations`: parou em `0014`; constraint ausente; 3 itens intactos. |
| `git status --porcelain` no fim | vazio (0 linhas) |

Linha anterior: 3.658 aprovados, 50 pulados, 1 reprovado. Agora: 3.681 aprovados (+23 testes novos), os mesmos 50 pulados e a mesma reprovação conhecida. Sem regressão.

## 3. D1 a D9 — situação

| # | Achado da rodada 1 | Situação | Evidência |
| --- | --- | --- | --- |
| D1 | `tipo` fora de débito/crédito passa e desconcilia Razão e Balancete | **Fechado** | Ver 4.1. `CheckConstraint ck_itemlancamento_tipo_valido` em `models.py` e na 0015. Em commit real (`transaction=True`), `bulk_create` de 3 itens (débito 10, crédito 10, terceiro de 5.000) com o terceiro `tipo` = `lixo`, `DEBITO`, vazio, `Credito`, `" debito"` ou `"debito "` foi recusado nos 6 casos, sempre com constraint `ck_itemlancamento_tipo_valido` e 0 lançamentos gravados. SQL cru com `'xx'` e com `NULL` também recusados. A pré-conferência da 0015 falha alto, nomeando o lote, sem alterar dado. |
| D2 | Par balanceado entra em lançamento já efetivado | **Fechado para os caminhos do produto e para o ORM comum; brecha residual em R1** | Ver 4.2. Par posterior, autocommit e savepoint revertido foram recusados; `criar_lancamento`, estorno, zeramento e bulk seguem. A burla por `INSERT ... ON CONFLICT DO NOTHING` com `id` explícito existe (R1). |
| D3 | Backfill aceitava competência de outra empresa | **Fechado** | Ver 4.3. |
| D4 | Recusa de convite sem rastro na trilha | **No backlog** | BL-566 (aberta) em [backlog.md](../projeto/backlog.md), com critério de aceite. Não cobrado como defeito da etapa. |
| D5 | Usuário já vinculado recebe 500 | **Fechado** | Ver 4.4. |
| D6 | Testes não isolavam `PROTECT` de `fechada_por`/`entregue_por` | **Fechado** | Ver 4.5. Mutação reprova. |
| D7 | `estado.md` dizia "duas exceções" | **Fechado** | `docs/agents/estado.md:135` diz "com uma exceção declarada". |
| D8 | `empresa_escritorio_imutavel` sem mensagem nem guarda | **No backlog** | BL-567 (aberta). |
| D9 | `casefold()` iguala e-mails distintos | **No backlog** | BL-568 (aberta), depende do BL-548. |

BL-561 a BL-565 (D1, D2, D3, D5, D6) constam como "em validação (DL-052, reconferência)". Cabe ao `arquiteto-senior` movê-los conforme este parecer. BL-561, BL-563, BL-564 e BL-565 podem ir a concluída. O BL-562 deve seguir a decisão sobre R1.

## 4. Verificações pedidas, uma a uma

Todos os experimentos de gatilho usaram `@pytest.mark.django_db(transaction=True)`, portanto o COMMIT é real. Os scripts ficaram na cópia descartável (`scratchpad/rec/copia/apps/contabilidade/tests/test_rec_exp.py`, `test_rec_tempo.py` e `apps/tenancy/tests/test_rec_d5.py`), fora do repositório.

### 4.1 D1 — tipo inválido

- 6 variantes de tipo: todas recusadas, constraint correta, nada gravado (tabela na seção 3).
- SQL cru: `INSERT ... tipo 'xx'` e `INSERT ... tipo NULL`, ambos recusados (`IntegrityError`/`DatabaseError`). Nenhum lançamento restou.
- Pré-conferência da 0015: mensagem da seção 2, atômica, banco permaneceu em 0014.
- `ck_itemlancamento_tipo_valido` está mapeado em `RESTRICOES_SEM_CAMINHO_DE_CLIENTE` (`apps/core/restricoes.py`).

### 4.2 D2 — migração 0016 (marcador local à transação). Tentativas de burla

| Tentativa | Resultado |
| --- | --- |
| Par balanceado inserido em transação posterior a um lançamento já comitado | Recusado. Constraint `item_lancamento_em_lancamento_efetivado`; o lançamento continua com 2 itens. |
| Mesmo caso em autocommit (cada `ItemLancamento.objects.create` como transação própria) | Recusado nos dois inserts. |
| Transação que cria o lançamento L1 (aceito) e tenta inserir item num lançamento efetivado L0 | L0 recusado; a transação inteira reverte (L1 some). |
| Savepoint revertido (id fantasma), 1 nível | `,id,` estava no marcador dentro do savepoint e **saiu** após o rollback; o item no lançamento efetivado foi recusado. |
| Savepoint aninhado de 2 níveis revertido, depois de um lançamento válido da transação externa | O marcador ficou só com o id válido (`,l_ok,` presente, `,f,` ausente). |
| Lançamento criado em savepoint e itens inseridos depois do RELEASE, na mesma transação externa | Aceito (4 itens), o caminho legítimo do produto. Depois do commit, partida nova é recusada. |
| Conexão reaproveitada: transação 1 cria e comita; transação 2 na mesma conexão | Marcador vazio no início da transação 2; item no lançamento da transação 1 recusado. Marcador vazio também após ROLLBACK. |
| `set_config(..., true)` fora de transação e após commit | `current_setting` devolve nulo ou vazio depois: o valor é local e **não vaza** para a sessão. |
| Prefixo comum de ids (lançamentos efetivados 1, 2, 12 e 121; transação cria 21, 212 e 1212, e depois 11) | 12 combinações (id efetivado × id novo) recusadas, todas com `item_lancamento_em_lancamento_efetivado`. Nenhum falso casamento por substring; os delimitadores `,id,` funcionam. |
| `criar_lancamento` (com `chave_idempotencia` repetida, dentro de `atomic` externa com 5 lançamentos) | Funciona; idempotência devolve o mesmo lançamento com 2 itens. |
| `estornar_lancamento` | Funciona (2 itens). |
| `zerar_resultado` (lucro de 6.000,00 do caso de referência da DL-043, mês 1/2026) | Funciona: `criado_etapa1`, `criado_etapa2` e 3 itens na etapa 1. |
| `bulk_create` de lançamentos e itens na mesma transação | Funciona. |
| **`INSERT ... ON CONFLICT DO NOTHING` com `id` de lançamento já efetivado** | **BURLA ACEITA. Ver R1.** |

Custo em transação com muitos lançamentos (`bulk_create` de N lançamentos mais 2N itens, tempo total incluindo commit, com a 0016 e sem os dois gatilhos dela, mesma máquina, suíte parada):

| N | Com a 0016 | Sem a 0016 |
| --- | --- | --- |
| 500 | 0,11 s | 0,10 s |
| 2.000 | 0,41 s | 0,35 s |
| 5.000 | 1,34 s | 1,08 s |
| 20.000 | 9,64 s | 3,67 s |
| 50.000 | 51,51 s | 9,32 s |

- Para 2.000 lançamentos o acréscimo é desprezível. A curva é quadrática (a busca e a concatenação no marcador são lineares no número de ids já marcados), o que só importa acima de alguns milhares por transação. Ver R3.
- `criar_lancamento` 2.000 vezes numa só `atomic`: 12,9 s com a 0016 e 13,0 s sem ela. O custo do serviço é dominado pelo próprio serviço.

`pg_dump`/`pg_restore` com 31 lançamentos e 62 itens, banco migrado pela cópia:

| Modo | Resultado |
| --- | --- |
| `pg_dump -Fc` + `pg_restore` padrão | Restaurou 31/62 e os 6 gatilhos. |
| `pg_restore --single-transaction --exit-on-error` | Idem. |
| `pg_dump` em texto + `psql -f` com `ON_ERROR_STOP` | Idem. |
| `pg_dump` em texto + `psql -1` (transação única) | Idem. |
| `pg_restore --data-only` em esquema vazio, sem `--disable-triggers` | FALHA: `O lançamento 1 já está efetivado: partida nova só entra no lançamento criado na mesma transação.` (na primeira tentativa a falha veio antes, por ordem de chave estrangeira em `auth_permission`; na segunda, com `--single-transaction`, veio a mensagem acima). |
| `pg_restore --data-only --disable-triggers` como usuário comum | Falha: `permission denied: "RI_ConstraintTrigger_..." is a system trigger`. |
| Mesmo comando como superusuário (`postgres`) | Restaurou 31/62. |

- O restore padrão (completo) continua funcionando, como o implementador declarou.
- O limite declarado vale, mas a saída alternativa "ou uma transação única" não funciona (R2).

### 4.3 D3 — competência de outra empresa

Em commit real:

- `update(competencia=<de outra empresa>)` recusado (`DatabaseError`), `competencia_id` continua NULL.
- `update(competencia=<própria>, historico="y")`, isto é, competência mais outra coluna, recusado.
- `update(competencia_id=10**9)` recusado.
- **Backfill legítimo** (`NULL` para competência da mesma empresa, isolado): 1 linha atualizada, `competencia_id` preenchido.
- Selagem preservada: valor→outro valor e valor→NULL recusados.
- Na suíte completa, `test_management_backfill` e `test_dl052_invariantes_no_banco::test_d3_*` passaram.

### 4.4 D5 — usuário já vinculado

Via cliente HTTP (POST em `tenancy:aceitar-convite`), e-mail do convite em caixa alta e o do usuário em minúsculas:

- Vínculo ativo: **302** para `/`, mensagem "Sua conta já tem vínculo com este escritório; este convite não é necessário. Use o painel para acessá-lo.", `consumido_em` continua `None`, vínculo inalterado (papel e `ativo` iguais), exatamente 1 vínculo do usuário. Sem 500.
- Vínculo inativo: mesmo resultado, e **o vínculo não foi reativado**.
- Usuário vinculado só a OUTRO escritório continua aceitando: 302, convite consumido, vínculo criado.
- Observação de texto, sem defeito: para o vínculo inativo a mensagem manda "usar o painel", mas o vínculo está inativo. A mensagem é correta como recusa, porém imprecisa como orientação. Baixa e cosmética, não virou achado.
- Limite conhecido: a checagem é "existe, então recusa", seguida de `create`. Dois aceites simultâneos do mesmo usuário com dois convites distintos do mesmo escritório ainda poderiam cair no `IntegrityError`. O caso é muito estreito e não foi exercitado.

### 4.5 D6 — mutação

Na cópia, troquei `Competencia.fechada_por` e `Competencia.entregue_por` de `PROTECT` para `SET_NULL` (`models.py` linhas 119 e 143; `diff` confirmou só essas duas linhas). Resultado: `4 failed, 12 passed`. Falharam `test_d6_os_seis_campos_de_autoria_sao_protect[...fechada_por]` e `[...entregue_por]`, e `test_d6_apagar_usuario_autor_da_competencia_e_recusado_sem_depender_da_trilha[fechada_por]` e `[entregue_por]`. Sem a mutação: `16 passed`. O teste por ORM monta a `Competencia` sem `encerrar_competencia`, portanto sem trilha, e isola o campo.

## 5. Achados novos

### R1 — Burla do marcador da 0016 por `INSERT ... ON CONFLICT DO NOTHING` com `id` explícito

- **Gravidade:** baixa a média. Eu classifico como **média-baixa, não bloqueante**:
  - nenhum caminho do produto usa `ignore_conflicts` nem `ON CONFLICT` com lançamento (`grep` em código não-teste: sem resultado em `contabilidade`);
  - quem escreve SQL cru já forja o marcador com `SELECT set_config('dataledger.lancamentos_da_transacao', ',1,', true)` em uma linha;
  - ainda assim o mecanismo é vendido como "trava" e este é um caminho em que ele passa sem querer.
- **Requisito afetado:** critério da correção de D2 ("INSERT de item em lançamento de transação anterior recusado"); AGENTS.md §10 (correção só por estorno).
- **Local:** `apps/contabilidade/migrations/0016_dl052_r1_item_so_em_lancamento_da_transacao.py`, gatilho `trg_lancamento_contabil_marca_transacao` (`BEFORE INSERT`, linhas ~62-66 da migração).
- **Causa:** o gatilho `BEFORE INSERT` dispara antes de o PostgreSQL verificar o conflito de chave. Com `ON CONFLICT DO NOTHING` a linha não é inserida (`INSERT 0 0`), mas o id do lançamento JÁ existente foi acrescentado ao marcador, que vale até o fim da transação.
- **Reprodução (SQL puro, banco migrado com lançamento 1 efetivado de 2 itens, `psql`):**
  ```sql
  BEGIN;
  INSERT INTO contabilidade_lancamentocontabil (id, empresa_id, data, historico, criado_em,
                                               chave_idempotencia, chave_idempotencia_fingerprint)
    SELECT id, empresa_id, data, 'dup', now(), '', ''
      FROM contabilidade_lancamentocontabil WHERE id = 1
    ON CONFLICT (id) DO NOTHING;                    -- INSERT 0 0
  SELECT current_setting('dataledger.lancamentos_da_transacao', true);   -- ,1,
  INSERT INTO contabilidade_itemlancamento (lancamento_id, conta_id, tipo, valor)
    SELECT 1, conta_id, tipo, 777 FROM contabilidade_itemlancamento WHERE lancamento_id = 1;   -- INSERT 0 2
  COMMIT;                                            -- aceito
  SELECT count(*) FROM contabilidade_itemlancamento WHERE lancamento_id = 1;   -- 4
  ```
  Pelo ORM: `LancamentoContabil.objects.bulk_create([LancamentoContabil(id=efetivado.pk, ...)], ignore_conflicts=True)` seguido de `ItemLancamento.objects.bulk_create(par balanceado de 777)` na mesma `atomic` foi aceito (`BURLA_ACEITA: itens 4`, valores finais `[100.00, 100.00, 777.00, 777.00]`).
- **Impacto:** é possível acrescentar um par balanceado a um lançamento efetivado (inclusive de competência encerrada), sem estorno nem trilha. É o mesmo dano de D2, agora só por quem escreve `ON CONFLICT`.
- **Correção recomendada (validada em banco descartável):** mover o gatilho de marcação para `AFTER INSERT FOR EACH ROW`. Com isso, a linha ignorada pelo `ON CONFLICT` não dispara o gatilho. Experimento no banco descartável: `DROP TRIGGER` e `CREATE TRIGGER ... AFTER INSERT ...` com a mesma função. Repetindo o script acima, o marcador ficou nulo e o item foi recusado com `O lançamento 1 já está efetivado: partida nova só entra no lançamento criado na mesma transação. Registre um estorno.`. Ressalva: uma instrução única com CTE que insira lançamento e itens ao mesmo tempo seria recusada, porque o gatilho `AFTER` só roda ao fim do comando. O ORM e os serviços não fazem isso. Correção em migração nova (0018), sem editar a 0016. Alternativa mínima: `IF EXISTS (SELECT 1 FROM contabilidade_lancamentocontabil WHERE id = NEW.id) THEN RETURN NEW; END IF;` antes do `set_config`. Se o `arquiteto-senior` preferir não corrigir, registrar como limite aceito com BL próprio e acrescentar ao plano a frase de que o marcador não impede quem escreve SQL cru.
- **Como verificar (teste proposto, `transaction=True`):**
  ```python
  @so_postgresql
  @pytest.mark.django_db(transaction=True)
  def test_r1_on_conflict_do_nothing_nao_abre_o_lancamento_efetivado(cenario):
      efetivado = _lancamento_valido(cenario)
      with pytest.raises(IntegrityError) as erro:
          with transaction.atomic():
              LancamentoContabil.objects.bulk_create(
                  [LancamentoContabil(id=efetivado.pk, empresa=cenario["empresa"],
                                      data=date(2026, 3, 10), historico="dup")],
                  ignore_conflicts=True,
              )
              _bulk_itens(cenario, efetivado,
                          [(TipoPartida.DEBITO, "7.00"), (TipoPartida.CREDITO, "7.00")])
      assert _nome_da_restricao(erro) == "item_lancamento_em_lancamento_efetivado"
      assert efetivado.itens.count() == 2
  ```
  O teste reprova hoje (a transação é aceita) e passa com a correção.
- **Responsável:** `desenvolvedor-pleno`, via `arquiteto-senior`.

### R2 — O plano e a 0016 dizem que "transação única" basta para carga só de dados; isso é falso

- **Gravidade:** baixa (documentação; o limite em si está declarado).
- **Local:** `docs/planos/DL-052-integridade-do-livro-e-do-acesso.md:129` ("precisa de `--disable-triggers` ou de uma transação única") e `apps/contabilidade/migrations/0016_dl052_r1_item_so_em_lancamento_da_transacao.py:36` (comentário "ou carga numa única transação").
- **Evidência:** medido em 4.2. `pg_restore --data-only --single-transaction --exit-on-error` falhou com `O lançamento 1 já está efetivado...`. A ordem das tabelas num `--data-only` não garante lançamento antes do item (as chaves estrangeiras do Django são `DEFERRABLE`, então não há dependência imposta). O `--disable-triggers` só funcionou como superusuário (como usuário comum: `permission denied ... is a system trigger`).
- **Impacto:** o plano de backup PE-07 poderia herdar uma instrução que não funciona.
- **Correção recomendada:** ajustar as duas frases para "carga só de dados exige `--disable-triggers` com superusuário; transação única NÃO basta". Registrar no PE-07 que o restore completo (esquema e dados) funciona sem ajuste.
- **Como verificar:** `grep "transação única" docs apps` sem a afirmação.

### R3 — Custo quadrático do marcador em transações com dezenas de milhares de lançamentos

- **Gravidade:** baixa (observação).
- **Local:** `0016`, função `contabilidade_marcar_lancamento_da_transacao` (concatenação) e `contabilidade_item_so_em_lancamento_da_transacao` (`position` sobre o texto inteiro).
- **Evidência:** tabela da seção 4.2: 2.000 lançamentos por transação custam ~17% a mais; 20.000 custam 2,6 vezes; 50.000 custam 5,5 vezes (51,5 s contra 9,3 s). A migração já declara o custo linear por item; na prática, com N lançamentos e 2N itens, o total é quadrático.
- **Impacto:** nenhum caminho do produto cria mais que alguns lançamentos por transação hoje (não há importação contábil em lote). Passa a importar se uma importação em massa for feita numa transação única.
- **Correção recomendada:** não agir agora. Registrar no backlog que, se surgir importação de volume, o marcador deve virar estrutura indexada (tabela temporária `ON COMMIT DROP`) ou a importação deve comitar em lotes.
- **Como verificar:** repetir a medição da seção 4.2 após qualquer mudança.

## 6. Classificação

- **Testado:** suíte completa (3.681 aprovados, 50 pulados, 1 reprovado conhecido); `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check --dry-run`, `gerar_agentes.py --verificar`; migração em banco vazio; `migrate contabilidade 0014` e volta, com listagem de gatilhos e constraints; pré-conferência da 0015 com dado ruim; D1 (6 tipos mais SQL cru); D2 (tentativas de burla da seção 4.2, prefixo de ids, serviços, custo, `pg_dump`/`pg_restore` em 4 modos completos e 3 modos só-dados); D3 (recusas, backfill legítimo, selagem); D5 (ativo, inativo, outro escritório, 302, sem consumo); D6 por mutação; verificação de que BL-566 a BL-568 estão registrados; `estado.md:135` corrigido.
- **Inspecionado:** diff completo de `1e53bc8..d847e75` (migrações 0015 a 0017, `models.py`, `restricoes.py`, `primeiro_acesso.py`, testes novos), seção "Evidências" do plano, backlog BL-560 a BL-568.
- **Não testado:** Python 3.14 (CI); `pwsh ./scripts/validate-docs.ps1` oficial (sem `pwsh`); concorrência entre transações simultâneas nos gatilhos da 0016 (o marcador é local à transação, portanto não compartilha estado, mas não foi exercitado com duas conexões); `TRUNCATE` e desligamento de gatilho pelo dono da tabela (declarados pelo plano); corrida de dois aceites do mesmo usuário com convites distintos.
- **Bloqueado:** nada.
- **Fora do escopo:** BL-547 a BL-558; D4, D8 e D9 (BL-566 a BL-568).

## 7. Parecer

**APROVADO COM RESSALVAS.**

Justificativa:

- D1, D3, D5, D6 e D7 estão fechados com evidência medida e, no D6, com mutação que agora reprova.
- D4, D8 e D9 estão no backlog (BL-566 a BL-568), como decidido.
- D2 está fechado para os caminhos do produto e para as tentativas previstas (par posterior, savepoint revertido, conexão reaproveitada, prefixo de ids, `criar_lancamento`, estorno, zeramento, carga em lote, restore completo). O custo para 2.000 lançamentos é desprezível.
- A suíte completa bate com a linha anterior, com +23 testes, os mesmos 50 pulados e a mesma falha única conhecida de Python 3.13.
- Não encontrei falha bloqueadora nem de alta gravidade.

Ressalvas explícitas, que o `arquiteto-senior` deve tratar antes ou junto do merge:

- **R1 (média-baixa):** o marcador da 0016 é burlável por `INSERT ... ON CONFLICT DO NOTHING` com id explícito. Recomendo corrigir na 0018 (gatilho `AFTER INSERT`, validado em banco descartável) e manter o BL-562 aberto até lá. Se preferir não corrigir, registre limite aceito em BL e no plano, sem declarar que o banco impede inserção de partida em lançamento efetivado.
- **R2 (baixa):** corrigir a afirmação "ou transação única" no plano e no comentário da 0016; levar ao PE-07.
- **R3 (baixa):** registrar no backlog o custo quadrático do marcador para o caso de importação em massa.

Esta auditoria não declara ausência de bugs nem segurança absoluta, e não substitui validação profissional das regras contábeis e legais. O marcador da 0016 é defesa em profundidade contra escrita acidental fora do serviço, não barreira contra quem tem acesso a SQL. A CI em Python 3.14 segue sendo a evidência que vale para o merge.

## 8. Arquivos citados

- `/home/user/DataLedger/apps/contabilidade/migrations/0015_dl052_r1_tipo_do_item_valido.py`
- `/home/user/DataLedger/apps/contabilidade/migrations/0016_dl052_r1_item_so_em_lancamento_da_transacao.py`
- `/home/user/DataLedger/apps/contabilidade/migrations/0017_dl052_r1_backfill_so_na_mesma_empresa.py`
- `/home/user/DataLedger/apps/contabilidade/models.py`
- `/home/user/DataLedger/apps/core/restricoes.py`
- `/home/user/DataLedger/apps/tenancy/services/primeiro_acesso.py`
- `/home/user/DataLedger/apps/contabilidade/tests/test_dl052_invariantes_no_banco.py`
- `/home/user/DataLedger/apps/tenancy/tests/test_dl052_convite.py`
- `/home/user/DataLedger/apps/accounts/tests/test_dl052_usuario_nao_se_apaga.py`
- `/home/user/DataLedger/docs/planos/DL-052-integridade-do-livro-e-do-acesso.md`
- `/home/user/DataLedger/docs/projeto/backlog.md`
- `/home/user/DataLedger/docs/agents/estado.md`

Scripts de experimento (fora do repositório): `/tmp/claude-0/-home-user-DataLedger/f87afd18-c419-55b8-b66f-f612e14081e2/scratchpad/rec/`. Os bancos `dataledger_reconf052*` foram removidos. O `git status --porcelain` do repositório ficou vazio.
