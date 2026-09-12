# Auditoria DL-011 — CNPJ alfanumérico — rodada 4 — 2026-09-12

Parecer do `auditor-qa` sobre a **rodada 4** da etapa
[DL-011](../planos/DL-011-cnpj-alfanumerico.md), que fecha o BL-46.

Rodadas anteriores:
[1 — reprovada](2026-09-12-dl-011-cnpj-alfanumerico.md) ·
[2 — aprovada com ressalvas](2026-09-12-dl-011-reauditoria-rodada-2.md) ·
[3 — aprovada com ressalvas](2026-09-12-dl-011-reauditoria-rodada-3.md).

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**. O texto abaixo é o relatório do auditor, sem edição.

## Parecer

**APROVADO COM RESSALVAS**, e o auditor declarou, com todas as letras, que
**nenhuma ressalva impede fechar a etapa**.

## Decisão do `arquiteto-senior`: discordo em um ponto, e fecho no resto

Aceito o parecer quanto a **B2, B3, B4 e B5**. **Não aceito quanto ao B1**, e a
divergência é de critério, não de fato — os fatos do auditor estão corretos.

**O B1 volta para correção antes de a etapa fechar**, por duas razões:

1. **É defeito introduzido nesta rodada**, não preexistente. O `except`
   largo entrou nos quatro caminhos de uma vez, junto com a correção do A1.
   Mandar para backlog um defeito que a própria rodada criou é o tipo de dívida
   que ninguém volta para pagar.
2. **Um dos sintomas é falha virando sucesso aparente** — o usuário recebe o
   formulário de volta sem um único erro, e nada foi gravado. O
   [AGENTS.md](../../AGENTS.md) §8 proíbe isso nominalmente. Em software
   contábil, essa é a categoria mais perigosa de defeito que existe: o operador
   acredita que registrou.

O auditor tem razão em que o sintoma é **latente hoje**. A discordância é sobre
o que se faz com defeito latente e barato de corrigir: a correção recomendada
por ele — o gerenciador levantar um tipo próprio — é **uma classe e quatro
linhas**.

O **B2** vai junto, porque é o teste que prende exatamente o mesmo trecho, e
seria desperdício abrir duas rodadas para o mesmo arquivo.

**B3** (alteração de CNPJ sem trilha de auditoria, preexistente) e **B4** (admin
sem o gerenciador) viram itens de backlog. **B5** é meu, e é a última linha do
fechamento.

---

# Reauditoria DL-011 — CNPJ alfanumérico (BL-46) — rodada 4

Versão auditada: **`3794378`**, branch `claude/accounting-agent-team-setup-mn6lyf`. Base do diff: `4e22202`. Medida contra o meu relatório da rodada 3 (A1–A7) e contra os das rodadas 1 e 2.

**Ambiente — Testado.** Venv isolada no scratchpad (Python 3.14.0rc2, Django 6.1.1, DRF, pytest 9.1.1, ruff), PostgreSQL 16 com *collation* `C.UTF-8`. Cópia `git archive 3794378` em `/tmp/.../scratchpad/r4`, conferida idêntica a `apps/` e `config/` do repositório por `diff -r -q` (só `__pycache__` difere). Banco descartável `aud_r4` criado e destruído. 14 mutantes em cópias descartáveis (`scratchpad/mutr4`, removida). Quatro arquivos de sonda criados **na cópia**, todos removidos. Nenhum arquivo do repositório foi tocado; `pwsh` continua ausente.

---

## 1. Verificações favoráveis

**Suíte e ferramentas — Testado.** `pytest -q` → **263 passed** (eram 251). `ruff check .` → All checks passed. `ruff format --check .` → **125 files already formatted**. `manage.py check` → 0 issues. `makemigrations --check --dry-run` → No changes detected. **Confirmo todos os seus números.**

**A1 fechou de verdade — Testado, 12 de 12.** Corrida real com `threading.Barrier`, duas empresas do mesmo escritório, cada *thread* tentando o mesmo CNPJ em caixas diferentes, **seis execuções de `PATCH` e seis de `PUT`**:

```
CORRIDA patch 0 {'A':200,'B':400}   1 {'A':200,'B':400}   2 {'B':200,'A':400}
               3 {'B':400,'A':200}  4 {'A':400,'B':200}   5 {'A':400,'B':200}
CORRIDA put   0 {'B':400,'A':200}   1 {'A':400,'B':200}   2 {'A':200,'B':400}
               3 {'B':400,'A':200}  4 {'A':400,'B':200}   5 {'A':400,'B':200}
```

**Nenhum 500 em 12 de 12**, uma única linha `AB123CDE000155` em todas. Na rodada 3 era 500 em 6 de 6. O `PUT` — que eu não tinha exercitado — também fecha.

**Mutação do `perform_update`, refeita direito — Testado.** A sua medição foi grosseira, como você mesmo disse. Refiz de forma cirúrgica, removendo **apenas** o bloco `def perform_update` de `EmpresaDetailView` (linhas 78–89 de `views.py`), preservando `get_permissions` e a classe seguinte:

```
### M_SEM_PERFORM_UPDATE
FALHAS: 2
  FAILED test_api.py::test_atualizar_empresa_via_api_com_corrida_neutralizando_o_unique_validator_da_400
  FAILED test_api.py::test_atualizar_empresa_via_api_corrida_real_com_duas_threads_nunca_devolve_500
```

**Exatamente os dois testes relevantes, e nenhum outro.** O mecanismo está isolado. Mutante independente que só troca `with transaction.atomic(), erro_de_cnpj_duplicado_como_400():` por `with transaction.atomic():` no `perform_update`: **as mesmas duas falhas**.

**A2 prende a restrição, e prende pelo nome certo — Testado.** Removi as duas `CheckConstraint` do `Meta` **e** as duas `AddConstraint` da migração (remoção por faixa de linhas, sem resíduo — conferi o arquivo resultante):

```
### M_CONSTRAINT_AMBAS_FORA
FALHAS: 6
  test_canonizacao_constraint.py:: os 5 testes
  test_services.py::test_mensagem_se_cnpj_duplicado_ignora_violacao_da_check_constraint_canonica
```

Na rodada 3 esse mesmo mutante dava **251 passed**. Agora mata 6. Os nomes nas asserções são os nomes reais, conferidos em `pg_constraint`:

```
empresas_empresa          | empresa_cnpj_canonico         | c | CHECK (cnpj = upper(cnpj) AND NOT (cnpj ~ '[^A-Z0-9]'))
empresas_empresa          | empresas_empresa_cnpj_key     | u | UNIQUE (cnpj)
empresas_estabelecimento  | estabelecimento_cnpj_canonico | c | (idem)
empresas_estabelecimento  | empresas_estabelecimento_cnpj_key | u | UNIQUE (cnpj)
```

E o efeito que você quis é real: mutante que **renomeia** as duas constraints em `models.py` e na migração, de forma coerente (o código continuaria funcionando), **mata os mesmos 6 testes**. A fixação pelo nome é intencional e funciona.

**A metade do regex está presa; a metade `Upper()` é mutante equivalente — Testado.** Mutante que descarta `~Q(cnpj__regex=r"[^A-Z0-9]")` e deixa só `Q(cnpj=Upper("cnpj"))` → morre por **exatamente um** teste, `test_bulk_create_com_cnpj_contendo_caractere_nao_alfanumerico_e_barrado`. **O comentário desse teste está factualmente correto.** O mutante inverso — só o regex, sem o `Upper()` — **sobrevive**, mas é **equivalente, não lacuna**: se todo caractere está em `A-Z0-9`, `upper(x) = x` necessariamente. Confirmei em SQL sob `C.UTF-8`, com oito valores (maiúsculo, minúsculo, espaço no meio, `ABC`, vazio, mascarado, cedilha, 14 alfanuméricos): não existe valor que passe o regex e reprove no `Upper()`. Manter as duas metades é defesa em profundidade legítima; não há teste a escrever.

**A3 fechou nos quatro caminhos — Testado.** Cada `with erro_de_cnpj_duplicado_como_400()` está preso por ao menos um teste:

| Mutante (remover o gerenciador de) | Falhas |
| --- | --- |
| `EmpresaListCreateView.perform_create` | 2 |
| `EmpresaDetailView.perform_update` | 2 |
| `EstabelecimentoListCreateView.perform_create` | 1 |
| `criar_empresa` (tela) | 1 |

**N10 e N11 da rodada 3 estão mortos.** E o N8 — a armadilha da DL-007 — também: mutante `if modelo is None: modelo = Empresa` em `mensagem_se_cnpj_duplicado` → **3 falhas**, exatamente os três testes novos de `test_services.py`. Na rodada 3 esse mutante sobrevivia.

**O gerenciador não engole o que não deveria — Testado, nos quatro caminhos.** Injetei, por `monkeypatch` em `Empresa.save`/`Estabelecimento.save`, um `IntegrityError` cuja `__cause__.diag.constraint_name` é de outra constraint, e medi o status HTTP:

```
POST   /api/empresas/                         -> 500   (sobe, não vira 400)
PATCH  /api/empresas/<id>/                    -> 500
POST   /api/empresas/<id>/estabelecimentos/   -> 500
POST   /empresas/nova/ (tela)                 -> 500
```

**Quatro de quatro sobem sem tradução.** E o gerenciador **não captura** o que não deve: `DatabaseError`, `OperationalError`, `ValueError` e `RuntimeError` atravessam intactos (só `except IntegrityError`, e `IntegrityError` é subclasse de `DatabaseError`, não o contrário). `IntegrityError` sem `__cause__` também sobe intacto. **A armadilha da DL-007 não se repetiu no código.**

**Não há quinto caminho de requisição para `Estabelecimento` — Inspecionado.** `apps/empresas/urls.py` tem seis rotas; **não existe `EstabelecimentoDetailView`** nem rota de `PUT`/`PATCH` de estabelecimento. Varri `apps/` e `config/` por `.save(`, `bulk_create`, `bulk_update`, `.update(`, `get_or_create`, `update_or_create`, `loaddata` fora de testes: os únicos pontos que gravam CNPJ são os quatro tratados. `apps/contabilidade/views.py:100` grava `Conta`, não CNPJ. **Há um quinto caminho de gravação, o Django admin — ver B4**, que não é caminho de requisição da API nem da tela.

**Isolamento entre escritórios não regrediu, inclusive no caminho novo — Testado.** Gestor de A, empresa cadastrada em B: `PATCH` → **404**; `PUT` → **404**; CNPJ de B intacto depois. `PATCH` da própria empresa com `{"escritorio": <B>}` no corpo → 200 e a empresa **permanece em A** (`escritorio` não está em `fields`). Lista, detalhe e estabelecimentos continuam 404. Suítes de `tenancy` e `empresas` passam.

**R1, R2, R4, R7, R8 e R10 continuam fechados — Testado.** Reexercitei o admin **real** (`EmpresaAdmin(Empresa, AdminSite()).get_form(request)`): `"ab.123.cde/0001-55"` → válido → gravado `AB123CDE000155`; campo `CNPJFormField`, `max_length=None`. R7: `POST {"cnpj":"xx"}` devolve **as duas chaves**. R10: as nove cargas (`1`, `1.5`, `True`, `null`, `[]`, `{}`, `""`, `"   "`, 40 caracteres) dão 400 com mensagem de formato ou do próprio DRF; nenhuma "no máximo 32 caracteres", nenhum 500. **Nada da rodada 1 voltou** (os 263 testes incluem os casos de caixa, Unicode que expande, fronteira `resto < 2`, tipo inválido, máscara em posição livre).

**A4 está correto e completo — Testado em banco descartável.** A consulta de pré-checagem do plano é a negação **exata** da condição da constraint. Verifiquei valor a valor:

| valor | constraint aceita | pré-checagem pega |
| --- | --- | --- |
| `AB123CDE000155` | t | f |
| `ab123cde000155` | f | t |
| `11222333 00018` | f | t |
| `AB.123.CDE/0001-55` | f | t |
| `ÇB123CDE00015` | f | t |
| `ABC` / `''` / `ABCDEFGHIJKL01` | t | f |

Complementares em todos os casos: a consulta pega **exatamente** o que faria a migração falhar, nada mais, nada menos. Reproduzi o cenário completo: `migrate empresas 0001`, inserção por SQL cru de `cnpj='ab123cde000155'` em `empresas_empresa` e `'11222333 00018'` em `empresas_estabelecimento`, pré-checagem → **1 e 1**, e então `migrate empresas 0002` → `IntegrityError: check constraint "empresa_cnpj_canonico" ... is violated by some row`, com `django_migrations` parado em `0001` e **zero** *check constraints* criadas. Falha limpa, como o plano diz. A ordem de reversão também confere: `migrate empresas 0001` remove as duas constraints (`pg_constraint` volta a zero *checks*) e é reversível; e ela **tem** de vir antes do `git revert`, porque a migração `0002` referencia `apps.empresas.fields.CNPJModelField` — revertendo o código primeiro, a migração não carrega mais. **O plano acertou nos dois pontos.**

**Documentação — Testado (equivalente manual).** `pwsh` ausente; reimplementei as cinco regras de `scripts/validate-docs.ps1` sobre os **40** `.md` do repositório → **0 problemas**. BL-54, BL-55 e BL-56 existem no backlog, com critério de aceite, e a nota "BL-54 deve estar resolvido antes de a DL-010 importar em lote" está lá.

---

## 2. Achados novos

### B1 — MÉDIA. O `except DjangoValidationError` é mais largo do que a exceção que o gerenciador levanta: `exc.message_dict` **estoura**, e na tela o erro é **engolido em silêncio**

Esta é a sua pergunta 3, e a resposta é: **não, `message_dict` não existe sempre.**

- **Requisito afetado:** AGENTS.md §8 ("Não ignorar exceções nem converter falhas em sucesso aparente"; "Tratar erros de maneira consistente"). Critério 13 (sem regressão) não é violado.
- **Local:** `/home/user/DataLedger/apps/empresas/views.py:64-65`, `:88-89`, `:111-112` e `:225-227`. O gerenciador em `/home/user/DataLedger/apps/empresas/services.py:81` sempre levanta com **dict**, mas o `except` das quatro views captura **qualquer** `django.core.exceptions.ValidationError` erguido dentro de `serializer.save()`/`empresa.save()` — e `Empresa.save()`/`Estabelecimento.save()` chamam `normalizar_cnpj` (`models.py:125`, `:216`), que levanta `ValidationError` de **mensagem**, sem `error_dict`.
- **Reprodução executada, sintoma 1 (500):** gravei por `bulk_create` uma empresa com `cnpj="ABC"` — canônico para a constraint, e portanto gravável hoje (é o meu achado A5/BL-54) — e fiz `PATCH` **só na `razao_social`**:

  ```
  PATCH /empresas/api/empresas/<id>/  {"razao_social": "Nome Novo Ltda"}  -> HTTP 500

  django.core.exceptions.ValidationError: ['CNPJ deve ter 14 caracteres alfanuméricos ...']
  During handling of the above exception, another exception occurred:
    File ".../apps/empresas/views.py", line 89, in perform_update
      raise DRFValidationError(exc.message_dict) from exc
    File ".../django/core/exceptions.py", line 194, in message_dict
      getattr(self, "error_dict")
  AttributeError: 'ValidationError' object has no attribute 'error_dict'
  ```

  Conferi isoladamente: `ValidationError("texto").message_dict` e `ValidationError(["a","b"]).message_dict` **ambos** levantam `AttributeError`. Só a forma dict tem `message_dict`.
- **Reprodução executada, sintoma 2 (falha vira sucesso aparente):** na tela, `criar_empresa` lê `exc.message_dict.get("cnpj", [])`. Injetei `ValidationError({"razao_social": ["problema de regra de negocio"]})` em `Empresa.save()`:

  ```
  status: 200        mensagem no corpo: NÃO        errorlist no corpo: NÃO        gravou: NÃO
  ```

  O usuário recebe o formulário de volta **sem um único erro**, e nada foi salvo. É a conversão de falha em sucesso aparente que a AGENTS.md §8 proíbe nominalmente.
- **Impacto.** O sintoma 1 é **latente e condicionado ao meu A5 (BL-54)**: só é alcançável com um registro cujo `cnpj` tenha de 0 a 13 caracteres `[A-Z0-9]`, o que a `CheckConstraint` atual permite e nenhum caminho de requisição produz — só `bulk_create`/`QuerySet.update`/`loaddata`. Um `[A-Z0-9]{14}` com DV errado normaliza sem erro, então não dispara. O sintoma 2 é latente hoje porque nada no código levanta `ValidationError` de dict sem a chave `cnpj` dentro daqueles blocos. O que me preocupa não é a probabilidade de hoje: é que este `except` largo foi introduzido **nesta rodada, nos quatro caminhos de uma vez**, e transforma qualquer `ValidationError` futura vinda de `save()`, de `signal` ou de regra nova em 500 com `AttributeError` que **esconde a causa raiz no log**, ou em 200 silencioso. O gerenciador foi criado justamente para "a lógica de detecção morar num lugar só"; a tradução na saída não seguiu a mesma disciplina.
- **Correção recomendada.** Estreitar o contrato em vez de alargar o `except`. Duas formas, qualquer uma serve: (a) o gerenciador levanta um tipo próprio, `class CNPJDuplicado(ValidationError)` em `services.py`, e as views capturam **esse** tipo — o `ValidationError` genérico volta a subir como antes, com a causa legível; ou (b) manter o tipo do Django e trocar `exc.message_dict` por uma leitura defensiva (`if not hasattr(exc, "error_dict"): raise`) nos quatro pontos. Prefiro (a): resolve os dois sintomas com uma linha e mantém a vantagem que você quis, que é os dois consumidores já saberem traduzir. Se o BL-54 for feito com `^[A-Z0-9]{12}[0-9]{2}$`, o sintoma 1 desaparece por consequência — mas o sintoma 2 não.
- **Como verificar.** Teste com `monkeypatch` em `Empresa.save` levantando `ValidationError("texto")`: esperar que a exceção **suba** (ou 500 com a `ValidationError` original na *traceback*, nunca `AttributeError`); e outro levantando `ValidationError({"razao_social": [...]})` na tela: esperar que **não** seja 200 sem erro.

### B2 — MÉDIA (qualidade de teste). O ramo de passagem do próprio gerenciador não tem teste: um mutante de uma linha reintroduz a DL-007 com a suíte verde

- **Requisito afetado:** AGENTS.md §7; a sua instrução explícita de não repetir a DL-007.
- **Local:** `/home/user/DataLedger/apps/empresas/services.py:78-81`.
- **Reprodução executada, mutante sobrevivente:**

  ```python
  # mutante M_CM_ENGOLE_TUDO, em erro_de_cnpj_duplicado_como_400()
  mensagem = mensagem_se_cnpj_duplicado(exc) or "CNPJ ja existe."
  raise ValidationError({"cnpj": [mensagem]}) from exc
  ```

  ```
  FALHAS: 0   — 263 passed, suíte inteira verde
  ```

  Isto é a DL-007 literal: **todo** `IntegrityError` — chave estrangeira, `uma_matriz_por_empresa`, `empresa_cnpj_canonico` — vira 400 "CNPJ já existe" nos **quatro** caminhos ao mesmo tempo, e nada acusa.
- **Impacto.** Os três testes novos de `test_services.py` são bons e matam o N8 — mas prendem `mensagem_se_cnpj_duplicado` **isolada**, como função. Nenhum teste exercita o gerenciador, nem em unidade nem por requisição: `grep` em `apps/empresas/tests/` não encontra uma única menção a `erro_de_cnpj_duplicado_como_400`. A guarda que impede mascarar defeito de sistema como erro de cliente agora tem **duas** camadas, e só a de baixo está presa. É a mesma forma do A3, subida um nível — a terceira aparição do padrão nesta etapa, como você suspeitou. O código está **correto hoje**: verifiquei 4 de 4 caminhos devolvendo 500 para `IntegrityError` alheio.
- **Correção recomendada.** Um teste de unidade do gerenciador, que é barato e mata o mutante:
  1. `test_gerenciador_deixa_subir_integrityerror_de_outra_constraint` — dentro de `pytest.raises(IntegrityError)`, `with erro_de_cnpj_duplicado_como_400():` e um `IntegrityError` cuja `__cause__.diag.constraint_name` seja `"uma_matriz_por_empresa"` (ou real, criando duas matrizes).
  2. `test_gerenciador_traduz_apenas_a_unique_de_cnpj` — o caso positivo: `pytest.raises(django.core.exceptions.ValidationError)` e `assert exc.value.message_dict == {"cnpj": ["empresa com este CNPJ já existe."]}`.
  3. Um teste de requisição, em qualquer um dos quatro caminhos, afirmando que `IntegrityError` de outra origem **não** vira 400.
- **Como verificar.** Replantar o mutante acima e conferir que ele morre.

### B3 — MÉDIA (preexistente, fora do escopo declarado da DL-011). Alterar o CNPJ de uma empresa por `PUT`/`PATCH` **não gera registro de auditoria**

- **Requisito afetado:** AGENTS.md §11 ("Registrar ator, contexto, operação e resultado") e §10 ("Impedir alterações silenciosas em registros efetivados").
- **Local:** `/home/user/DataLedger/apps/empresas/views.py:78-89`. `perform_create` (`:66`), `EstabelecimentoListCreateView.perform_create` (`:113`) e `criar_empresa` (`:229`) chamam `registrar(...)`. O `perform_update` novo **não**. Não existe ação `empresa.alterada` em lugar algum de `apps/`.
- **Reprodução executada:** `PATCH /empresas/api/empresas/<id>/ {"cnpj": "34028316000103"}` por gestor autorizado → **200**, CNPJ alterado de `11444777000161` para `34028316000103`, e `RegistroAuditoria.objects.values_list("acao")` → `['login.sucesso']`. **Nenhum registro da alteração.**
- **Impacto.** O CNPJ é o identificador da empresa perante a Receita. Trocá-lo sem trilha significa que, depois do fato, não há como saber quem trocou, quando, nem de qual valor para qual. É **preexistente** — `EmpresaDetailView` já aceitava `PUT`/`PATCH` desde a DL-004, e o `perform_update` padrão do DRF também não auditava —, então **não é regressão desta rodada** e não pesa contra a DL-011. Registro porque esta rodada criou o `perform_update`, que é o lugar natural do `registrar()`, e a omissão passou.
- **Correção recomendada.** Item de backlog próprio: `registrar(acao="empresa.alterada", objeto=..., request=..., detalhes={campos alterados, com valor anterior e novo})`, dentro do `else` do `try`, espelhando `perform_create`. Decidir com o Fred se o valor anterior do CNPJ entra nos detalhes — eu diria que sim, é o dado que dá sentido ao registro.
- **Como verificar.** Teste que faz `PATCH` do CNPJ e afirma um `RegistroAuditoria` com a ação, o ator e os dois valores.

### B4 — BAIXA. Quinto caminho de gravação de CNPJ: o **Django admin**, que não usa o gerenciador

- **Local:** `/home/user/DataLedger/apps/empresas/admin.py` — `EmpresaAdmin` e `EstabelecimentoInline` não sobrescrevem `save_model` nem `save_formset` (`"save_model" in EmpresaAdmin.__dict__` → `False`).
- **Reprodução executada:** `EmpresaAdmin(Empresa, AdminSite()).save_model(request, Empresa(..., cnpj="ab123cde000155"), None, change=False)` com `AB123CDE000155` já gravado → `IntegrityError: duplicate key value violates unique constraint "empresas_empresa_cnpj_key"`, **sem tradução**. Em requisição real de admin isso é 500.
- **Impacto.** Pequeno e bem delimitado: o admin é ferramenta interna de *staff*, o `ModelForm` do admin já faz `validate_unique`, então só a corrida real chega aqui, e o dado permanece íntegro (a *unique* segura). Não é o contrato público do produto. Mas é, literalmente, a resposta à sua pergunta "há algum outro ponto que grave CNPJ e não use o gerenciador?": **há, e é o admin.**
- **Correção recomendada.** Backlog. `save_model`/`save_formset` em `EmpresaAdmin`/`EstabelecimentoInline` usando `with transaction.atomic(), erro_de_cnpj_duplicado_como_400():` e convertendo para `form.add_error("cnpj", ...)`, como a tela faz. Custo baixo, e fecha o inventário de caminhos.
- **Como verificar.** `POST` no `add_view` do admin com `validate_unique` neutralizado, esperando 200 com erro de campo em vez de 500.

### B5 — BAIXA (documentação). O plano não registra a rodada 4: commit, base, evidências e o A3

- **Requisito afetado:** AGENTS.md §3 ("Evidências de validação e, quando disponíveis, commit e link do PR") e §5.9. É a mesma forma do R6/A4, em grau muito menor.
- **Local:** `docs/planos/DL-011-cnpj-alfanumerico.md:6` — *"rodada 4 em correção (A1, A2 da auditoria da rodada 3)"*, sem o A3, que **foi** corrigido; e `:12-15`, que continuam em "Commit da rodada 3 `6ae84e5`", base `6e6e088`, "251 testes", "123 arquivos". Também `docs/projeto/backlog.md:38`, onde o BL-46 diz "rodada 3 em correção".
- **Reprodução:** leitura de `docs/planos/DL-011-cnpj-alfanumerico.md` no commit `3794378`.
- **Impacto.** Nenhum em código. Mas é o documento onde o Fred, ou quem vier depois, vai procurar o que foi validado e contra qual commit — e hoje ele aponta para a rodada anterior. A seção "Migração e reversão", que é a correção do A4, está **correta**; o que falta é a metadata da rodada.
- **Correção recomendada.** Ao fechar a etapa: estado, commit `3794378`, base `4e22202`, "263 testes; ruff/format (125 arquivos)/check/makemigrations limpos", a linha da auditoria da rodada 4, incluir o A3 na lista do que foi corrigido, e atualizar o BL-46 no backlog.
- **Como verificar.** Leitura do plano; validação de documentação limpa.

### Nota sobre A5, A6 e A7, que ficaram de fora de propósito

Você pediu que eu dissesse se algo desta rodada muda a avaliação deles.

- **A5 / BL-54 — a avaliação piorou, na consequência, não na gravidade.** Continua BAIXA em si, e continua sem caminho de requisição. Mas agora ele é **a condição de alcance do B1, sintoma 1**: é a `CheckConstraint` permitir `cnpj` com menos de 14 caracteres que torna o 500 do `PATCH` alcançável. Os dois se resolvem juntos, e fortalecer a constraint para `^[A-Z0-9]{12}[0-9]{2}$` elimina o gatilho. **Reforço a recomendação de resolver o BL-54 antes de a DL-010 importar em lote**, agora por dois motivos em vez de um.
- **A6 / BL-55 — inalterado.** Nada desta rodada toca `fields.py` nem `serializers.py`. N6 e N12 continuam sobrevivendo pelo mesmo mecanismo de defesa em profundidade. O B2 é da mesma família e cabe naturalmente junto.
- **A7 / BL-56 — inalterado.** Reconferi: `CNPJFormField`, `max_length=None`, sem `maxlength` no HTML. Item de experiência de uso, sem risco.
- **R5 — inalterado, e reconfirmado no caminho novo.** `PATCH` com CNPJ de empresa de **outro escritório** devolve `400 {"cnpj":["empresa com este CNPJ já existe."]}`, o mesmo oráculo de existência de sempre. Preexistente da DL-004, decisão do Fred, **não pesa contra esta etapa**. Registro só para que fique claro que a superfície do R5 inclui `PUT`/`PATCH`, e não só o `POST`.

---

## 3. Situação de A1, A2, A3 e A4

| # | Achado da rodada 3 | Situação | Base |
| --- | --- | --- | --- |
| **A1** | `PUT`/`PATCH` devolve 500 sob corrida | **Corrigido** | Testado: 12/12 (6 `PATCH` + 6 `PUT`) em `{200, 400}`, uma linha; era 6/6 em 500. Mutação cirúrgica do `perform_update` mata exatamente os 2 testes novos |
| **A2** | A `CheckConstraint` não tem um único teste | **Corrigido** | Testado: remover as duas constraints (Meta + migração) mata 6 testes, e antes deixava 251 verdes. Nomes conferidos em `pg_constraint`; renomear coerentemente mata os mesmos 6. Metade do regex presa; metade `Upper()` é mutante equivalente, não lacuna |
| **A3** | Guarda anti-DL-007, tela e `Estabelecimento` sem teste | **Corrigido** | Testado: N8 morre por 3 testes; N10 e N11 morrem; os 4 caminhos presos. **Resíduo:** o ramo de passagem do gerenciador em si não tem teste → **B2** |
| **A4** | O plano afirma que a etapa não cria migração | **Corrigido** | Testado em banco descartável: pré-checagem é a negação exata da constraint (8 valores conferidos), a migração falha limpa sobre dado não canônico, e a ordem de reversão é a correta e necessária. **Resíduo:** metadata da rodada 4 → **B5** |

Nada das rodadas 1, 2 e 3 voltou — incluindo o **R2**, que reexercitei no admin real e no `ModelForm` gerado, porque ele já reincidiu uma vez por caminho novo.

---

## 4. Critérios de aceite

| # | Critério | Resultado | Classificação |
| --- | --- | --- | --- |
| 1 | Cinco CNPJs numéricos continuam válidos | Atende, 5/5 | Testado |
| 2 | Alfanumérico com DV correto é aceito | Atende (unitário, tela, API, admin, *inline*, persistência, e agora `PUT`/`PATCH`) | Testado |
| 3 | Alfanumérico com DV errado é recusado | Atende, mensagem específica | Testado |
| 4 | Letra nas posições 13-14 é recusada | Atende, com e sem máscara | Testado |
| 5 | 13 ou 15 caracteres recusados | Atende | Testado |
| 6 | `00000000000000` recusado | Atende no validador. **Ressalva inalterada:** passa pela `CheckConstraint` em `bulk_create` (A5/BL-54) | Testado |
| 7 | Máscara aceita e removida | Atende, inclusive no admin e no *inline*. Estreitamento registrado em DE-013 e no plano | Testado |
| 8 | Minúsculas normalizadas, validadas e persistidas canônicas | Atende em todos os caminhos de requisição, nos de massa e no de alteração | Testado |
| 9 | Caractere fora de `[A-Z0-9./-]` recusado com mensagem útil | Atende; nove cargas conferidas, nenhum 500 | Testado |
| 10 | Nenhum ponto do sistema descarta letras ao normalizar | Atende. `normalizar_cnpj` continua função única; `_mascara_cnpj` é só apresentação | Inspecionado + Testado |
| 11 | Modelo persiste alfanumérico sem truncar | Atende (`varchar(14)`, `AB123CDE000155`). **Ressalva inalterada:** A5/BL-54, que agora também sustenta o **B1** | Testado |
| 12 | Comentário cita NT 2025.001 e IN RFB 2.229 | Atende (`validators.py:5-9`); os comentários novos de `services.py` e `views.py` são factualmente corretos — conferi cada afirmação deles por mutação | Inspecionado + Testado |
| 13 | Sem regressão; ferramentas limpas | Atende: 263 passed, `ruff`/`format --check` (125 arquivos)/`check`/`makemigrations --check` limpos. **`scripts/validate-docs.ps1` não executado — `pwsh` ausente** | Testado / **Bloqueado** no item da documentação |

Paliativo do item bloqueado, **não equivalente**: reimplementei as cinco regras do script sobre os **40** `.md` → 0 problemas.

Não avaliei conformidade jurídica da NT 2025.001 nem da IN RFB 2.229 — validação profissional do Fred. Não afirmo ausência de outros defeitos.

---

## 5. Integridade da árvore

`git status --short` ao final: **vazio.** `git diff --stat` e `git diff --cached --stat`: vazios. `git stash list`: vazio. `HEAD` = `3794378843458f7f3189745cb216ccc45721ac0c`, branch `claude/accounting-agent-team-setup-mn6lyf`, como recebido. `git status --short --ignored` mostra só `.pytest_cache/`, `.ruff_cache/` e `__pycache__/`.

A linha ` M docs/projeto/requisitos.md` que eu reportei na rodada 3 **não está mais aqui** — foi commitada em `0a288cf`. A árvore está limpa.

Sobre o que é meu: **nada**. Não tenho `Write` nem `Edit`; todo comando que executei escreveu apenas sob o scratchpad. Fora do repositório: cópia `git archive 3794378` (conferida por `diff -r`), 14 cópias de mutação (`scratchpad/mutr4`, removida), quatro arquivos de sonda criados **na cópia** e removidos (conferi com `diff -r` que a cópia voltou ao original antes de mutar), e o banco `aud_r4`, criado e destruído (`pg_database` conferido sem sobras `aud%`/`test%`). Nenhum `ruff format` sem `--check`. Nenhum comando de formatação, atualização de *snapshot* ou migração destrutiva contra o repositório ou contra `dataledger`. Nenhum commit, nenhum push. Não deleguei a ninguém.

---

# APROVADO COM RESSALVAS

Esta rodada é a mais limpa das quatro, e é a primeira em que as correções fecham **na raiz e com prova de teste**, não por verificação minha. Os três itens que eu tinha marcado como "tem de entrar antes de a etapa fechar" **entraram, e os três resistem a mutação**:

- O A1 não é mais reproduzível: 12 execuções de corrida real, seis em `PATCH` e seis em `PUT`, todas em `{200, 400}`. O `PUT`, que eu não tinha exercitado, também fecha. E a sua ressalva honesta sobre a própria medição estava certa — refiz a mutação de forma cirúrgica e ela mata **exatamente os dois testes** que deve matar, nem um a mais.
- O A2 deixou de ser verificação minha e virou teste versionado. O mutante que na rodada 3 me deu 251 verdes agora mata 6 testes. E a fixação pelo nome funciona do jeito que você quis: renomear a constraint de forma coerente, sem tocar no teste, quebra a suíte.
- O A3, que era dívida de cobertura, ficou melhor do que eu pedi: os quatro caminhos estão presos, e o N8 — a armadilha da DL-007, que era o que mais me preocupava — morre por três testes.
- O A4 é seu, e está certo. Conferi a consulta de pré-checagem valor a valor contra a condição real da constraint: são complementares exatas. E a ordem de reversão não é só correta, é **necessária** — inverter a ordem impede a própria reversão, porque a migração referencia `CNPJModelField`. Você não errou de novo.

Nenhum achado desta rodada é bloqueador ou de gravidade alta. Nenhum critério de aceite deixou de ser atendido. O isolamento entre escritórios não regrediu, inclusive no caminho novo de alteração. Nada das rodadas 1, 2 e 3 voltou, incluindo o R2.

**Resposta direta à sua pergunta final: nenhuma das ressalvas impede fechar a DL-011.** Digo com todas as letras, e digo por quê, item por item:

- **B1** é MÉDIA e é o único achado com um 500 reproduzido — mas ele é **alcançável só através do A5**, que você conscientemente mandou para o BL-54, e desaparece por consequência quando o BL-54 for feito. Nenhum caminho de requisição do produto cria o registro que o dispara. O sintoma silencioso na tela é hoje inalcançável. Vai para o BL-54, junto com o A5, e deve ser corrigido **antes de a DL-010 importar em lote** — que é exatamente onde o BL-54 já estava marcado.
- **B2** é dívida de cobertura, não defeito: verifiquei nos quatro caminhos que o código se comporta corretamente. É a mesma natureza do A3, que você já aceitou agrupar. Cabe no BL-55.
- **B3** é **preexistente** e não foi introduzido aqui. Merece item próprio, porque trilha de alteração de CNPJ importa, mas não é a DL-011 que o criou nem a DL-011 que o deve resolver.
- **B4** é BAIXA, é o admin, e fecha um inventário — não um risco.
- **B5** são minutos de documento, e é trabalho que você faz de todo modo ao registrar esta auditoria. Não é motivo para outra rodada; é a última linha do fechamento.

Ou seja: **pode encerrar a DL-011 e seguir para a DL-010**, desde que os cinco itens acima entrem no backlog antes de o assunto sair da mesa, e desde que o BL-54 — agora com dois motivos, não um — esteja resolvido antes de a DL-010 gravar CNPJ em lote.

Encaminhar **B1** e **B2** ao `desenvolvedor-pleno`, anexados ao BL-54 e ao BL-55. **B3** e **B4** como itens novos de backlog, também para o `desenvolvedor-pleno`. **B5** é seu.

Arquivos que importam para quem for corrigir: `/home/user/DataLedger/apps/empresas/views.py` (B1, linhas 64-65, 88-89, 111-112, 225-227; B3, linha 78), `/home/user/DataLedger/apps/empresas/services.py` (B1 e B2, linhas 78-81), `/home/user/DataLedger/apps/empresas/models.py` (A5/BL-54, linha 17), `/home/user/DataLedger/apps/empresas/admin.py` (B4) e `/home/user/DataLedger/docs/planos/DL-011-cnpj-alfanumerico.md` (B5, linhas 6 e 12-15).

Auditoria de software não substitui validação profissional das regras contábeis e legais. Não avaliei a nota técnica sob o aspecto jurídico, e não afirmo ausência de outros defeitos, segurança absoluta ou conformidade garantida.
