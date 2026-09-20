# Reconferência do BL-470 — DL-031, rodada final (2)

> **Nota do `arquiteto-senior`, e é só esta:** relatório do `auxiliar-verificacao`,
> preservado **integralmente**. Eu não edito, não suavizo e não omito achado
> nenhum.
>
> ⚠️ **O item 1 existe porque eu o pedi, e ele não estava no relatório de
> ninguém:** para corrigir o BL-470, o implementador **mudou a assinatura** de
> uma função e, por isso, **editou três testes que já existiam** — justamente os
> que o `auditor-qa` havia validado **por mutação** na reconferência da fatia 1.
> Editar teste para acompanhar mudança de código é legítimo e corriqueiro; **é
> também o jeito mais discreto de cegar uma guarda**, porque o teste continua
> verde, o nome continua lá, e ninguém nota que ele parou de detectar. Por isso
> mandei **refazer a prova de mutação depois da edição**. Os três continuam
> reprovando.

---

**Revisão reconferida:** `206f4b1` (`claude/accounting-agent-team-setup-mn6lyf`)
**Revisão anterior:** `0e6651f` ([verificação dirigida 1](2026-09-20-dl-031-verificacao-dirigida-1.md))
**Data:** 2026-09-20 · **Verificador:** `auxiliar-verificacao` · **Nível de risco:** 2 (§3.1 do [AGENTS.md](../../AGENTS.md))

## Parecer em uma frase

O BL-470 fecha — reproduzi o cenário de concorrência real com instrumento próprio (não o teste dele) e obtive `CompetenciaOcupada`/409 em português nunca 500; a prova de mutação refeita depois da mudança de assinatura mostra que os três testes `test_bl456_*` continuam reprovando a regressão (a guarda não foi cegada); a varredura R2 é verdadeira em todos os cinco pontos, incluindo a afirmação mais sutil sobre `ROLLBACK TO SAVEPOINT`, que medi diretamente pelo log SQL; não-regressão bate exatamente com o declarado (2008 passed, 14 skipped) e todas as verificações estáticas passam; e o único chamador da função com assinatura nova passa os três parâmetros corretos.

### 1. Prova de mutação (item mais crítico) — **Testado**

Worktree isolado (`git worktree add --detach 206f4b1`), banco próprio (`verif_bl456_mutacao`). Mutação aplicada em `apps/contabilidade/services.py`, exatamente a pedida:

```python
# antes (linhas 764-766)
estado_travado, entregue_em_travado = _travar_competencia_em_modo_compartilhado(
    competencia, ano=data.year, mes=data.month, empresa=empresa
)
# depois (mutação)
estado_travado, entregue_em_travado = competencia.estado, competencia.entregue_em
```

```
pytest -q apps/contabilidade/tests/test_dl016_fatia1_fechamento_reabertura_entrega.py -k test_bl456
→ 3 failed, 49 deselected in 11.59s
FAILED ...::test_bl456_for_share_bloqueia_encerrar_competencia_ate_o_lancamento_commitar
FAILED ...::test_bl456_lancamento_concorrente_e_recusado_quando_o_fechamento_ja_commitou
FAILED ...::test_bl456_reproducao_2_lancamento_concorrente_recusado_em_competencia_entregue
```

**Resultado: atende.** Os três testes determinísticos continuam reprovando a mutação — a edição de assinatura (`*, ano, mes, empresa` + adaptação dos `monkeypatch` com `**kwargs`) **não** cegou a guarda do BL-456. Mutação desfeita (`git checkout --`), worktree removido, banco `verif_bl456_mutacao` apagado.

### 2. R1 — o BL-470 está fechado — **Testado** (instrumento próprio, não o teste do desenvolvedor)

Script isolado (não usa `test_dl016_..._bl470_*`), banco próprio (`verif_bl470_r2`), duas conexões PostgreSQL reais (uma segurando `FOR UPDATE` 2s > `lock_timeout=1210ms`):

```
RESULTADO SERVICO: {'tipo': 'CompetenciaOcupada', 'mensagem': 'A competência 03/2021 de Empresa R1 Instrumento Ltda está sendo fechada por outra operação agora; não foi possível confirmar o estado dela a tempo. Tente gravar este lançamento novamente em instantes.', 'duracao': 1.225s}
RESULTADO API: {'logado': True, 'status': 409, 'corpo': {'detail': 'A competência 04/2021 de Empresa R1 Instrumento Ltda está sendo fechada por outra operação agora; ...'}}
```

**Resultado: atende.** Pelo serviço: `CompetenciaOcupada` com mensagem legível, nunca `InternalError`. Pela API: 409 em português, nunca 500. Também rodei os dois testes novos dele (`test_bl470_*`) — `2 passed in 5.27s` — batendo com o meu instrumento.

### 3. R2 — a varredura declarada — **Testado/Inspecionado**, item por item

- `services.py:288` (`except IntegrityError` de `obter_ou_criar_competencia`): mensagem usa só `ano`/`mes` (parâmetros em memória). **Inspecionado, seguro.**
- `services.py:458` (`except OperationalError` de `_travar_competencia_em_modo_compartilhado`, o próprio ponto corrigido): já confirmado em R1. **Testado, seguro.**
- `services.py:502` (`except OperationalError` de `_travar_competencia_para_transicao`): mensagem usa só `mes`/`ano`/`empresa` (parâmetros), nunca `competencia.*`. **Inspecionado, seguro.**
- `services.py:812` (`except IntegrityError` do bloco de idempotência de `criar_lancamento`) — **a afirmação mais sutil, medida diretamente**, não só lida. Escrevi um script que provoca a corrida real (duas threads, mesma `chave_idempotencia`) com `settings.DEBUG=True` e capturei `connection.queries` de cada thread. Log real da thread que perdeu a corrida:

  ```
  SAVEPOINT "...x1"
  ...
  INSERT INTO "contabilidade_lancamentocontabil" (...)
  ROLLBACK TO SAVEPOINT "...x1"
  RELEASE SAVEPOINT "...x1"
  SELECT "contabilidade_lancamentocontabil"."id" ... WHERE ...   <- esta é a consulta do `except IntegrityError` (busca do registro existente)
  COMMIT
  ```

  Confirma, por medição direta (não só leitura do código), que o `ROLLBACK TO SAVEPOINT` do `with transaction.atomic()` aninhado acontece **antes** de qualquer consulta subsequente no `except`, deixando a transação saudável — a alegação do desenvolvedor sobre o comportamento do Django está correta. **Testado.**
- `services.py:937` (`except IntegrityError` de `estornar_lancamento`): a mensagem é uma string estática (`"Este lançamento já foi estornado."`), sem nenhum acesso a atributo de `lancamento`/`competencia` dentro do `except` — mais seguro ainda que o caso anterior, e `estornar_lancamento` também tem sua própria `with transaction.atomic()` externa, então o `IntegrityError` vindo de `criar_lancamento` (que tem `@transaction.atomic` próprio) já passou pelo mesmo mecanismo de savepoint antes de chegar aqui. **Inspecionado, seguro.**

**Resultado: a varredura é verdadeira** — nenhum outro ponto tem o padrão do BL-470, e a afirmação sobre savepoint/rollback automático do Django foi medida, não só presumida.

### 4. R3 — não-regressão — **Testado**

Banco próprio (`verif_bl470_r2`), árvore limpa:

| Comando | Resultado medido |
|---|---|
| `pytest -q` | `2008 passed, 14 skipped, 2 warnings, 4 subtests passed in 101.58s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `209 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced)` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`, exit 0 |
| `python manage.py migrate` (banco vazio) | todas as migrações aplicadas sem erro |

Bate exatamente com o declarado (2006 + 2 novos = 2008 passed, 14 skipped).

### 5. R4 — a mudança de assinatura não vazou — **Inspecionado**

```
$ grep -n "_travar_competencia_em_modo_compartilhado(" apps/contabilidade/services.py
354: def _travar_competencia_em_modo_compartilhado(competencia, *, ano, mes, empresa):
764:     estado_travado, entregue_em_travado = _travar_competencia_em_modo_compartilhado(
765:         competencia, ano=data.year, mes=data.month, empresa=empresa
766:     )
```

Único chamador de produção é `criar_lancamento` (linhas 764-766), e passa `ano=data.year`, `mes=data.month`, `empresa=empresa` — os três parâmetros corretos, batendo com a competência que está de fato sendo travada. **Resultado: atende.** (Os demais usos do nome, em `test_dl016_..._bl464_*`, também passam `ano`/`mes`/`empresa` corretos, batendo com a competência criada em cada teste — conferido por leitura do diff.)

---

### Achados

Nenhum. Todos os itens desta rodada atendem.

### O que não consegui medir, e por quê

- Não reproduzi a comparação "código antes do BL-470 vs. depois" em termos de tempo/performance — não fazia parte do escopo pedido (só a correção funcional e a prova de mutação do BL-456).
- Não testei a colisão de nomes/edge cases fora do escopo (BL-471, BL-472, os oito critérios da tela) — explicitamente fora do escopo desta rodada, conforme instrução.
- Não fiz uma segunda repetição estatística da prova de mutação (rodei uma vez, determinística, sem `time.sleep` variável nos três testes `test_bl456_*`) — não considerei necessário porque a saída do `pytest` é determinística (mesma asserção falhando pelo mesmo motivo estrutural, não por timing), mas registro que não repeti em múltiplas execuções.

Arquivos relevantes: `apps/contabilidade/services.py` (linhas 284-953), `apps/contabilidade/tests/test_dl016_fatia1_fechamento_reabertura_entrega.py` (testes `test_bl456_*` e `test_bl470_*`), `apps/contabilidade/tests/test_bl40_bl41.py` (`test_corrida_real_de_idempotencia_produz_um_unico_lancamento`, usado como referência do mecanismo de savepoint), commit `206f4b1`.
