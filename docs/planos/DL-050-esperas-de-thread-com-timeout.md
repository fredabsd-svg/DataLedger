# DL-050 — Toda espera de thread tem timeout, com asserção de que concluiu

**Estado:** em validação
**Nível de risco:** 3 — andaime (guardas, varreduras, ferramenta interna, CI), pelo
§3.1 do `AGENTS.md`. **Sem auditoria e sem registro de decisão**, como o nível 3 manda.

**Origem:** achado sistêmico medido em 29/09/2026, durante o trabalho da DL-048, e
registrado no [`docs/agents/estado.md`](../agents/estado.md) como pendência 3.

## Problema

`join()` e `barreira.wait()` **sem timeout** em 9 arquivos de teste. Se uma thread
morre antes de chegar à barreira, as outras esperam para sempre.

O sintoma medido é o pior possível para um processo: **a suíte termina em silêncio**.
Três execuções de `pytest` terminaram sem traceback, sem timeout do próprio pytest e
sem nada que dissesse qual teste era. Só o `faulthandler` mostrou a causa.

## Escopo

26 `join()` e 11 `barreira.wait()` sem timeout → `join(timeout=60)` e
`wait(timeout=30)`, mais 47 asserções de `is_alive()`.

**Fora do escopo:** qualquer arquivo de produção, qualquer migração, qualquer regra
contábil, qualquer asserção de invariante existente.

## Por que a asserção vem junto, e não só o timeout

**Timeout sozinho seria pior do que travar.** Sem a asserção, uma thread que não
concluísse deixa o teste **seguir** com resultados incompletos, e uma verificação que
só confere *"não levantou exceção"* **passaria** — falso positivo silencioso. É a mesma
razão pela qual o `AGENTS.md` diz *"falha visível: erro nunca vira sucesso aparente"*.

Com a asserção, a guarda fica **mais forte**: resultado incompleto **reprova**.

O tempo é generoso de propósito (60s/30s contra execuções de segundos na CI). Timeout
curto mascararia lentidão como falha — trocaria um defeito por outro.

## Critérios de aceite

1. Nenhuma asserção de invariante afrouxada, removida ou alterada.
2. Nenhum arquivo de produção alterado.
3. Nenhuma espera infinita restante no repositório.
4. Todo `join()` com timeout.
5. Os 9 arquivos executam de primeiro a último, sem travar.

## Evidência (29/09/2026)

- Os 9 arquivos passaram a **terminar em 4min20s**; antes terminavam em silêncio.
- As 30 falhas restantes são a lacuna SQLite × PostgreSQL já conhecida
  (`database is locked`, `no such table: pg_indexes`, `UNIQUE constraint failed`).
  **Nenhuma delas é a nova asserção** — o que prova que os timeouts não estão
  disparando nem mascarando nada.
- **A CI em Linux + PostgreSQL é o veredouro:** `Lint e testes` verde.
- `ruff check` limpo, 318 arquivos formatados, `validate-docs.ps1` verde.

## Risco declarado

A mudança é de nível 3, mas os **testes** alterados guardam invariantes de nível 1
(unicidade de CNPJ, lançamento, zeramento, estorno). A classificação vem do **efeito
da mudança** — que não toca regra contábil — e não de o código sob teste ser simples.
Daí a exigência explícita de que nenhuma asserção seja afrouxada.

Se algum teste dependia **implicitamente** de esperar indefinidamente, ele passa a
falhar. É o comportamento desejado; a CI confirma que nenhum dos 30 falha por isso.

## Reversão

`git revert` do commit. Sem migração e sem dado gravado.
