# Auditoria e reconferência — DL-065 (BL-550)

**Auditor:** `auditor-qa`, somente leitura, sondas fora do repositório.
**Rodada:** 1 de no máximo 2 (AGENTS.md §3.1: a terceira é proibida).
**Objeto:** commit `c979162`, branch `fix/dl-065-reclassificacao-em-competencia-encerrada`.
**Ambiente:** PostgreSQL 16.15 na porta 5433, Django 6.1.1, Python 3.14.7.
**Fora do escopo:** a suíte fora de `apps/contabilidade`, o `pytest` do
repositório inteiro, a CI remota e a porta do MCP (que não existe neste
repositório).

---

# PARECER: APROVADO COM RESSALVAS

Os treze critérios de aceite são verdadeiros e todos foram verificados por
execução própria do auditor, sem regressão. Restam três achados de gravidade
média — ponto cego da guarda, corrida entre reclassificar e fechar o mês, e
uma mensagem que manda o contador para um caminho que o próprio produto
recusa — e quatro de baixa.

**Nenhum bloqueador.**

## Critérios 1 a 13

| # | Veredito | Como o auditor verificou |
| --- | --- | --- |
| 1 | Verdadeiro | `test_criterio1_...` — 200, trilha com antes/depois |
| 2 | Verdadeiro | `test_criterio2_...`; sonda S8 imprime `...na competência 03/2026, que está encerrada...` |
| 3 | Verdadeiro | `test_criterio3_...`; **sonda S8**: remover a coluna da DMPL em março encerrado → recusado, valor intacto |
| 4 | Verdadeiro | `test_criterio4_...` — primeira classificação grava com o mês encerrado |
| 5 | Verdadeiro | `test_criterio5_...` (DLPA) + **sonda S8** (DMPL, que a suíte não cobria) |
| 6 | Verdadeiro | `test_criterio6_...` (DMPL) + **sonda S9** (descendente bloqueando a linha da **DLPA** do grupo) |
| 7 | Verdadeiro | `test_criterio7_...`; **sonda S4** imprime `...que está entregue...` |
| 8 | Verdadeiro | `test_criterio8_*`; a mutação imprime os campos do `ModelForm`: `(...;classificacao_dre;classificacao_dlpa;classificacao_dmpl;...)` |
| 9 | Verdadeiro | `test_criterio9_...` + **sonda S7**: trilha `2 → 2 → 2` nas três portas (API 409, tela 200, admin inválido) |
| 10 | Verdadeiro | `test_criterio10_...` + **sonda S3**: DRE trocada pelo **ModelForm do admin** com movimento em mês encerrado → `form.is_valid() True`, gravada. A DE-086 está intacta inclusive no caminho que o plano não cita |
| 11 | Verdadeiro (escopo: API) | `test_criterio11_...` → 404. A porta de **tela** não tinha teste (achado **A7**) |
| 12 | Verdadeiro | `pytest apps/contabilidade` → **8 failed, 1830 passed**, exatamente a linha de base |
| 13 | Verdadeiro | `ruff check` limpo; `ruff format --check` 356 arquivos; `manage.py check` sem problema; `makemigrations --check` sem mudança; `validate-docs.ps1` 223 md; `test_documentacao_do_estado.py` 19 passed |

⚠️ A **primeira** execução do auditor deu 23 failed e 35 errors: foi caused
pelo próprio auditor, que rodou outra `pytest` contra o mesmo banco de
teste em paralelo. Resultado descartado e reexecutado limpo.

## Mutação — os testes provam a regra?

- Guarda removida **em memória** (patch de
  `Conta._competencia_fechada_com_movimento`): **13 dos 21 testes falham**.
  Nenhum mutante sobrevive.
- `code` do modelo diferente do que o serviço reconhece: **11 falham**,
  incluindo os dois 409 da API. O vazamento do `code` está preso por teste.

## Achados

### A1 — **média** — a guarda é cega a lançamento com `competencia` nula

**Requisito afetado:** critério 2 e 3 (o período encerrado precisa barrar).
**Local:** `apps/contabilidade/models.py`, guarda de período fechado.
**Evidência:** lançamento legado criado com `competencia=None` mais itens na
conta, `encerrar_competencia`, depois `classificar_conta_na_dlpa` → **ACATA e
grava** (`reserva_legal`). O gatilho do banco recusa desfazer o vínculo
(`IntegrityError ... não pode ser alterado`), mas `criar_lancamento` sempre
grava a competência e existe o backfill da DL-016 F5 — o estado é de dado
pré-DL-016, alcançável, e nada impede fechar o mês assim.
**Impacto:** período encerrado cuja DLPA/DMPL é reescrita — exatamente o dano
que a trava existe para impedir.
**Correção recomendada:** filtrar o movimento pela faixa de datas da
competência, que é o critério que a apuração usa.
**Forma de verificar:** teste com lançamento sem competência e período
encerrado, esperando a recusa.

### A2 — **média** — corrida entre reclassificar e fechar a competência

**Requisito afetado:** o mesmo critério 2, agora sob concorrência.
**Local:** a mesma guarda; `encerrar_competencia` (`services.py`) trava a
competência, e ninguém travava a conta no caminho da classificação.
**Evidência:** duas threads com barreira — `estado da competencia: encerrada |
classificacao: reserva_legal`, zero erros. A guarda rodou com o mês aberto, o
fechamento commitou, e a reclassificação **commitou depois**.
**Impacto:** a regra é contornável na janela entre a leitura e o commit.
**Correção recomendada:** ler a competência no modo compartilhado antes de
gravar, reaproveitando `_travar_competencia_em_modo_compartilhado`.
**Forma de verificar:** teste de duas threads.

### A3 — **média** — a mensagem manda para um caminho que o produto recusa

**Requisito afetado:** critério 7 e a honestidade da recusa (BL-142, mesma
classe de "mensagem que não corresponde ao produto").
**Local:** a mensagem do achado A1/A2.
**Evidência (S4):** para competência **entregue** a mensagem diz *"Reabra a
competência para corrigir a classificação"*, e `reabrir_competencia` na mesma
competência responde *"não é possível reabrir... a correção vai no mês
aberto"*. A mesma frase afirma *"a correção de período encerrado nunca é uma
reclassificação de conta"*, quando a frase anterior — e
`test_limite_periodo_reaberto_deixa_de_barrar` — provam que, reaberta, a
correção **é** a reclassificação.
**Impacto:** instrução falsa ao contador em recusa de nível 1.
**Correção recomendada:** bifurcar a mensagem por `entregue`, como o BL-468
fez em `criar_lancamento`, e dizer o ajuste real.
**Forma de verificar:** asserção de que a mensagem de `entregue` não manda
reabrir.

### A4 — **baixa** — `EM_ENCERRAMENTO` reportado como "que está encerrada"

O estado gravado não é a palavra da mensagem. Alcançável só por ORM direto,
mas o texto fixo mente sobre o registro.

### A5 — **baixa** — o plano afirma que conta sem movimento não paga consulta

**Medido (S6b):** 22 consultas, uma delas recursiva — a troca em conta
**sem** movimento paga a recursiva. Só a primeira classificação é
curto-circuitada. A afirmação do plano estava errada.

### A6 — **baixa** — script de medição grava a coluna da DMPL sem a guarda

`scripts/medir_identificacao_do_emitente.py:883-885` escreve
`classificacao_dmpl` por fora de `full_clean()`. Risco aceito (DE-008), mas é
o único caminho do repositório que escreve o campo sem a guarda.

### A7 — **baixa** — cobertura faltando

A tela da DMPL (`conta_classificacao_dmpl`) e a recusa do admin para
`classificacao_dmpl` não tinham teste; o critério 11 só era testado na API.

## Vazamentos procurados e **não** achados

Nenhuma porta validada grava `classificacao_dlpa`/`dmpl` sem `full_clean()`:
só existe rota de **criação** de conta (sem rota de atualização), o admin usa
`ModelForm`, não há *management command* nem importador que toque o campo, e
não há MCP neste repositório. Os dois serviços de classificação só têm dois
chamadores, e ambos tratam a nova exceção. O `code` real confere com
`django/core/exceptions.py` do Django 6.1.1: o `hasattr(exc, "error_dict")` de
`_codigos_da_validacao` é o mesmo protocolo que o próprio Django usa.

## Cenários que o auditor tentou quebrar

| Tentativa | Resultado |
| --- | --- |
| Lançamento com `competencia` nula + mês encerrado | **Vazou** (A1) |
| Concorrência reclassificar × `encerrar_competencia` | **Vazou** (A2) |
| `EM_ENCERRAMENTO` | Barrou, mas chamou de "encerrada" (A4) |
| DRE pelo admin com mês encerrado | Gravou — **a DE-086 está intacta**, e por um caminho mais forte que o teste do critério 10 |
| Remover DMPL / descendente na DLPA (não cobertos pela suíte) | Barraram (S8/S9) |
| Destravar a guarda e o `code` em memória | 13 e 11 testes caíram — a cobertura é real |
| Isolar a empresa; recusa por API, tela e admin deixando rastro | 404 e trilha inalterada |

## O que o auditor NÃO verificou

A suíte **fora** de `apps/contabilidade` e o `pytest` do repositório inteiro;
a CI remota e o estado do PR; a corrida entre **duas** classificações
concorrentes da mesma conta (o `select_for_update` na conta existe e é o
mesmo molde da DRE, mas o auditor não montou essa corrida); o comportamento
de `FOR SHARE` sob o `lock_timeout` real do banco; e a inalcançabilidade de
`EM_ENCERRAMENTO` por serviços (declarada no modelo, não testada por ele).

**Nenhum arquivo do repositório foi escrito ou editado** pelo auditor: as
sondas e o plugin de mutação viveram em `%TEMP%` e foram removidos.

---

# RECONFERÊNCIA — rodada 2 de 2 (AGENTS.md §3.1: não há terceira rodada)

**Auditor:** `auditor-qa`, somente leitura, sondas em `%TEMP%\dl065_rod2\`.
**Objeto:** commit `c72c14f` (a correção única da rodada 1).
**Ambiente:** PostgreSQL 16.15 na porta 5433, Django 6.1.1, Python 3.14.7.

## Parecer da reconferência: **REPROVADO**

A1, A3, A4, A6 e A7 **FECHADOS**. **A2 NÃO FECHADO** — a corrida fecha (o
desfecho é coerente em 8 de 8 e o vazamento da rodada 1 não reproduz), mas a
tradução prometida do `lock_timeout` não acontece. E a correção **introduziu
dois defeitos**, um deles médio, com 500 em porta de nível 1.

## Estado de cada achado

| Achado | Veredito | Evidência do auditor |
| --- | --- | --- |
| A1 — guarda cega a lançamento sem competência | **FECHADO** | Sonda própria (`competencia=None`, março encerrado): `ClassificacaoAlteraPeriodoFechado`, mensagem nomeia `03/2026`, valor intacto |
| A2 — corrida reclassificar × encerrar | **NÃO FECHADO** | Desfecho coerente em 8/8; mas `lock_timeout` não vira 409 — ver **N1** |
| A3 — mensagem mandava reabrir competência entregue | **FECHADO** | Mensagem medida sem "Reabra a competência", apontando lançamento de ajuste |
| A4 — `EM_ENCERRAMENTO` como "encerrada" | **FECHADO** | `"...que está em encerramento —..."` |
| A5 — custo real registrado | **FECHADO** (texto) | Plano retificado em `:100-107` e `:259-262`; a imprecisão de número restou — ver **N2** |
| A6 — script grava a coluna da DMPL sem guarda | **FECHADO** | `backlog.md:2128` registra **BL-628** |
| A7 — cobertura faltando | **FECHADO** | Os três testes existem e passam |

## Defeitos novos introduzidos pela correção

### N1 — média — o `lock_timeout` vira **500**, não 409, na porta de serviço

`models.py`, a trava dentro de `Conta.clean()`. Com `FOR UPDATE` concorrente
e `lock_timeout = 120ms`, `classificar_conta_na_dlpa` devolveu
`InternalError('transação atual foi interrompida...')`, com a pilha
`services.py → full_clean() → validate_constraints → InternalError`.

**Causa:** o `FOR SHARE` estourado **aborta** a transação; `clean()` levanta o
`ValidationError` certo, mas o `Model.full_clean` do Django **acumula** o
erro e **continua** para `validate_unique()`/`validate_constraints()` — consultas
novas numa transação abortada. O `InternalError` **substitui** a recusa. É a
patologia que o docstring de BL-470 diz ter eliminado, reaberta num caminho em
que o Django garante a consulta posterior.

### N2 — média — a guarda foi de **1 consulta** para **N+1**

| períodos fechados | guarda isolada (com movimento) | serviço completo |
| --- | --- | --- |
| 0 | 7 consultas / 3,4 ms | — |
| 12 | 19 / 8,9 ms | 40 / 17,7 ms |
| 120 | 127 / 66,3 ms | 148 / 110,7 ms |
| 480 | 486 / 395,2 ms | **507 / 393,0 ms** |

Crescimento **linear** no histórico. Agravante: a travagem vinha **antes** da
varredura, então os ~400 ms eram **retidos com o `FOR SHARE` segurado** — a
janela em que a reclassificação bloqueia o fechamento cresceu na mesma
proporção.

### N3 — baixa — estado fora do enum vira `ValueError` cru

`Competencia.estado` não tem `CheckConstraint`, então `EstadoCompetencia(estado)`
estoura `ValueError` fora do `try/except` do serviço — 500. Gatilho alcançável
só por ORM direto; herança de um padrão preexistente (`services.py`).

## Eixos de defeito que o auditor MEDIU e **não** considerou defeito

- **Deadlock:** 4 threads, 12 voltas, 0,4 s — nenhum `OperationalError`,
  `InternalError` ou `DatabaseError`. Ordem `-ano`,`-mes` determinística e sem
  inversão contra `encerrar_competencia` nem `criar_lancamento`.
- **`FOR SHARE` fora de transação:** degrada sem estourar.
- **`RuntimeWarning` do SQLite:** emite; a regra continua valendo sem lock.
- **Calendário:** fevereiro de 2000 (29 dias) e 2100 (28, gregoriano), virada
  12→1, 31/03 bloqueia, 01/04 não contamina março. `data` é `DateField`, sem
  hora.
- **A2 depende do agendamento:** 8/8 o fechamento venceu; o outro ramo é
  legítimo por desenho e não foi provocado.

## Execução da reconferência

| Comando | Saída |
| --- | --- |
| `pytest apps/contabilidade` | **8 failed, 1836 passed, 6 skipped** — a linha de base exata |
| `pytest` dos dois arquivos da demanda | **27 passed** |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `356 files already formatted` |
| `manage.py check` | `System check identified no issues` |
| `manage.py makemigrations --check --dry-run` | `No changes detected` |
| `pwsh ./scripts/validate-docs.ps1` | `223 arquivos Markdown verificados` |
| `pytest apps/core/tests/test_documentacao_do_estado.py` | `19 passed` |

## O que a reconferência NÃO verificou

A porta **HTTP** real sob `lock_timeout` (mediu o serviço e o `ModelForm`, que
é o que as duas portas encapsulam); concorrência com `zerar_resultado`; o
comportamento com **múltiplas** competências abertas com movimento; o ramo "a
reclassificação vence a corrida" do A2; `EM_ENCERRAMENTO` por serviço; a suíte
**fora** de `apps/contabilidade`; a CI remota e o estado do PR; e o plano de
execução das consultas — mediu **contagem**, não `EXPLAIN`.

---

# Correção dos achados N1, N2 e N3

⚠️ **Isto NÃO é uma terceira rodada de auditoria, e é preciso dizer o que é.**
O §3.1 proíbe comprar outra rodada de auditoria: ela existe para parar quem
tenta provar uma frase que promete mais do que o instrumento aguenta, não para
permitir que um defeito médio conhecido — **um 500 em porta de nível 1** e uma
regressão de 1 para 507 consultas — siga para a `main`. O ciclo de auditoria
**está encerrado** no veredito **REPROVADO** acima, e assim fica registrado.

O que foi feito foi terminar a correção, não reabrir o processo:

- **N1** — a tentativa de lock passou a rodar dentro de
  `with transaction.atomic()`, que abre um **savepoint**. O `FOR SHARE`
  estourado volta até ele e a transação volta a servir, então o
  `ValidationError` chega inteiro ao acumulador do `full_clean` em vez de ser
  substituído por `InternalError`. Regressão: `test_n1_lock_timeout_vira_409_e_nao_500`,
  com duas threads e `lock_timeout` de 200 ms.
- **N2** — a pergunta "algum mês com movimento está fechado?" é uma
  **interseção de conjuntos**, e foi feita como tal: uma consulta traz os
  `(ano, mês)` com movimento da subárvore, e o cruzamento com as competências
  acontece em memória. O número de consultas passou a ser **constante**,
  independente de quantos meses a empresa já fechou. Regressão:
  `test_n2_o_custo_da_guarda_nao_cresce_com_o_historico`, que mede a mesma
  empresa com 1 e com 480 competências e exige que o número **não cresça** —
  o defeito era o crescimento, não o total.
- **N3** — o rótulo do estado vem de `dict(EstadoCompetencia.choices).get(...)`
  com o valor gravado como reserva, então nenhum estado fora do enum vira
  `ValueError`. Regressão: `test_n3_estado_fora_do_enum_nao_vira_valueerror`.

Os dois helpers que a versão intermediária criou e que a interseção tornou
sem uso (`_tem_movimento_nas_datas` e `_faixa_de_datas_da_competencia`) foram
**removidos** — código morto não fica.

**O que fica em aberto para o Fred:** estas três correções **não passaram por
auditoria independente**, porque o §3.1 proíbe a terceira rodada. Elas estão
verificadas por teste de regressão próprio e pela CI. Se ele quiser a
verificação independente delas, a decisão é dele — e a forma honesta seria um
papel diferente do mesmo `§3.1`, não uma terceira rodada deste ciclo.
