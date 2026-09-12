# Reauditoria DL-011 — CNPJ alfanumérico — rodada 3 — 2026-09-12

Parecer do `auditor-qa` sobre a **rodada 3** da etapa
[DL-011](../planos/DL-011-cnpj-alfanumerico.md), que fecha o BL-46.

Rodadas anteriores:
[rodada 1 — reprovada](2026-09-12-dl-011-cnpj-alfanumerico.md) ·
[rodada 2 — aprovada com ressalvas](2026-09-12-dl-011-reauditoria-rodada-2.md).

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**. O texto abaixo é o relatório do auditor, sem edição.

## Parecer

**APROVADO COM RESSALVAS.** Oito dos dez achados da rodada 2 fechados, dois
deles resolvidos na raiz. Sete achados novos, nenhum bloqueador, nenhum de
gravidade alta.

### Separação pedida pelo `arquiteto-senior`, e acatada

| Situação | Achados |
| --- | --- |
| **Entra antes de a etapa fechar** | **A1** (o R4 continua aberto no `PUT`/`PATCH`), **A2** (a correção do R1 não tem teste), **A4** (o plano afirma que a etapa não cria migração, e ela cria) |
| Vai para backlog próprio | A3, A5, A6, A7 |
| Preexistente, decisão do Fred | R5 |

**A4 é do `arquiteto-senior`** — é o R6 reaparecendo por caminho novo, no
documento que eu mesmo escrevi.

**Sobre o A1, e é o que mais importa:** um achado já reportado e **declarado
corrigido** continua vivo num caminho vizinho. Fechar a etapa com ele aberto
tornaria falso o registro da rodada 2. Por isso entra, apesar de gravidade
média.

---

# Reauditoria DL-011 — CNPJ alfanumérico (BL-46) — rodada 3

Versão auditada: **`6ae84e5`**, branch `claude/accounting-agent-team-setup-mn6lyf`. Base de comparação: `6e6e088`. Medida contra o meu relatório da rodada 2 (`docs/auditorias/2026-09-12-dl-011-reauditoria-rodada-2.md`, R1–R10) e contra o da rodada 1.

**Ambiente:** venv isolada no scratchpad (Python 3.14.0rc2, Django 6.1.1, DRF, pytest, ruff), PostgreSQL 16.13, banco `C.UTF-8` (igual ao `postgres:16-alpine` do `docker-compose.yml` e da CI). Cópia `git archive 6ae84e5` no scratchpad, conferida idêntica a `apps/` e `config/` por `diff -r`. Banco descartável `aud_r3` criado e destruído. Mutação em cópias descartáveis. Nenhum arquivo do repositório foi tocado.

---

## 1. Verificações favoráveis

**Suíte e ferramentas — Testado.** `pytest -q` → **251 passed**. `ruff check .` → All checks passed. `ruff format --check .` → **123 files already formatted**. `manage.py check` → 0 issues. `makemigrations --check --dry-run` → No changes detected. **Confirmo todos os seus números.**

**Migração `0002` em banco vazio e reversibilidade — Testado.** Aplicou limpa; `migrate empresas 0001` remove as duas `CheckConstraint` (`pg_constraint` volta a zero *checks*); reaplicar funciona. A migração é atômica: quando falha, nada fica meio aplicado e `django_migrations` permanece em `0001`.

**A `CheckConstraint` não tem falso positivo nem falso negativo nos casos que consegui construir — Testado.** Avaliei a condição diretamente em SQL, sob a *collation* do banco (`C.UTF-8`) **e** sob `pt-BR-x-icu`, para simular implantação com *locale* brasileiro:

| valor | `= upper()` | `~ '[^A-Z0-9]'` (C) | idem (ICU pt-BR) | passa |
| --- | --- | --- | --- | --- |
| `AB123CDE000155` | t | f | f | **sim** |
| `ab123cde000155` | f | t | t | não |
| `ÇB123CDE00015` / `ÁB123CDE00015` | t | **t** | **t** | não |
| `ßB123CDE00015` | t | t | t | não |
| `ıB…` / `ſB…` (dobra de caixa) | f | t | t | não |
| `AB123CDE00015５` (fullwidth) | t | t | t | não |
| com máscara, com espaço, com `_` | — | t | t | não |

O range `[A-Z]` **não** absorveu minúsculas nem acentuados em nenhuma das duas *collations*. Divergência real entre `upper()` do Postgres e `.upper()` do Python existe (`ß` → `ß` no PG, `SS` no Python), mas é irrelevante porque o ramo do regex barra antes. **Nenhum valor que o Python canoniza é rejeitado pelo banco**; o inverso tem lacuna (achado A5).

**Caminhos de gravação em massa agora fecham — Testado.** Em `bulk_create`, `bulk_update` e `QuerySet.update`, com minúscula, com máscara, com cedilha, com espaço e com `_`: **todos** `IntegrityError` em `empresa_cnpj_canonico`. Confirmo suas medições.

**R2 fechado, e melhor do que eu recomendei — Testado.** Não me contentei com `modelform_factory`: exercitei o **admin real** (`EmpresaAdmin(Empresa, AdminSite()).get_form(request)`) e o **inline real** (`EstabelecimentoInline.get_formset(request)`, com POST de formset e `save()`).

```
ADMIN REAL Empresa "11.122.233/0001-83" valido: True  → gravado 11122233000183
  campo: CNPJFormField  max_length: None  widget: AdminTextInputWidget
INLINE Estabelecimento "ab.123.cde/0001-55" valido: True → gravado AB123CDE000155
```

Varri as combinações que você pediu: `fields="__all__"`, `exclude=[...]`, `widgets={...}` customizado, `inlineformset_factory`, `formfield_overrides` do admin (o `AdminTextInputWidget` entra pelo MRO sem substituir `form_class`). **Todas herdam `CNPJFormField`.** `readonly_fields` não gera campo de formulário. A única combinação que escapa é `field_classes={"cnpj": forms.CharField}` — que é substituição explícita e deliberada de quem escreve o formulário, não vazamento da abstração; e mesmo aí `Model.save()` canoniza. Ganho colateral que o R2 não pediu: o `max_length=None` removeu o atributo `maxlength="14"` do HTML, que truncava a digitação no navegador antes de qualquer validação.

**`CNPJModelField` não vazou na camada de banco — Inspecionado + Testado.** `deconstruct()` → `('cnpj', 'apps.empresas.fields.CNPJModelField', [], {...max_length: 14...})`; `db_type()` → `varchar(14)`. A coluna não mudou. Confirmo seu `sqlmigrate`.

**R7 fechado — Testado.** Prova contrastiva refeita: `POST {"cnpj":"xx"}` sem `razao_social` agora devolve **as duas chaves**. Varri 13 cargas (`int`, `float`, `bool`, `null`, lista, dict, `""`, `"   "`, 40 caracteres): **nenhum 500, nenhum `AttributeError`**, erro agregado em todas.

**R10 fechado — Testado.** A mensagem "no máximo 32 caracteres" desapareceu; 40 caracteres na tela dão a mensagem de formato. `""`/`"   "` dão "Este campo é obrigatório." na tela e "Este campo pode não estar em branco." na API (texto do próprio DRF, não do projeto).

**Tratamento do `IntegrityError` não engoliu defeito de sistema — Testado.** Esta é a sua pergunta 4, a armadilha da DL-007. `mensagem_se_cnpj_duplicado` devolve `None` — e portanto o erro **sobe** — para: `uma_matriz_por_empresa`, `empresa_cnpj_canonico` (a própria CheckConstraint nova) e violação de chave estrangeira. Devolve a mensagem apenas para `empresas_empresa_cnpj_key` / `empresas_estabelecimento_cnpj_key`. Conferi os dois nomes contra `pg_constraint`: **corretos**. `exc.__cause__` ausente também devolve `None`. **A armadilha não se repetiu.**

**Isolamento entre escritórios não regrediu — Testado.** Gestor de A, com empresa cadastrada em B: lista → `[]`; detalhe → 404; `PATCH` → 404; estabelecimentos → 404; `POST` forçando `"escritorio": B` → 201 **no escritório A** (o `create` do serializer continua impondo o escritório da requisição). Suíte de `tenancy` e `empresas` passa.

**As duas afirmações do `desenvolvedor-pleno` são verdadeiras — Testado, replantando os mutantes.**

- **M8** (`_REGEX_SEM_MASCARA` → `\w{14}`): morre, e morre por **exatamente um** teste — `test_regex_sem_mascara_recusa_letra_unicode_de_largura_variavel`. Os três casos `parametrize` de `test_cnpj_com_letra_unicode_de_14_caracteres_e_invalido` de fato **não** o matam. **O relato dele está certo, e o comentário no teste explica o motivo correto.**
- **M15** (apagar a canonização de `Estabelecimento.save()`): morre por **exatamente um** teste — `test_estabelecimento_persiste_cnpj_canonico_via_objects_create`, via `DataError` da coluna. E confirmei o mecanismo que ele alegou: removendo também a `CheckConstraint`, o teste de duplicidade **volta a falhar**. Ou seja, é verdade que hoje quem barra o teste de duplicidade é a constraint, não o `save()`. **O relato está certo nas duas metades.**
- **M10** (separadores livres na máscara): morre, pelos dois casos novos `11-122-233.0001/83` e `11/122/233-0001.83`.
- **M18** (recusar CNPJ enviado como número JSON): morre, por `test_criar_empresa_via_api_com_cnpj_numerico_enviado_como_numero_json`. O contrato agora está fixado e documentado em `fields.py`.
- **M14** (canonização de `Empresa.save()`): morre.

**Corrida real no `POST`, 6 execuções com `threading.Barrier` — Testado.** `{A:201, B:400}` ou `{A:400, B:201}` em **6 de 6**, uma única linha gravada em todas. **O 500 do R4 sumiu do caminho de criação.** Não virou 409 nem exceção silenciosa; virou 400 com mensagem de campo. Mesmo resultado no `POST` de `Estabelecimento` e na tela.

**Documentação — Testado (equivalente manual).** `pwsh` continua ausente; reimplementei as cinco regras de `scripts/validate-docs.ps1` sobre os **39** `.md` do repositório → **0 problemas**. DE-013 existe e registra a máscara estrita com a consequência para a DL-010; o plano ganhou a seção "Decisões tomadas durante a execução". **R6 está atendido para a rodada 2.**

---

## 2. Situação de cada achado da rodada 2

| # | Rodada 2 | Situação | Base |
| --- | --- | --- | --- |
| **R1** | canonização fora da camada 1; comentário falso | **Corrigido** | Testado: `CheckConstraint` nas duas tabelas barra `bulk_create`/`bulk_update`/`QuerySet.update` em 5 formas; comentários de `save()` reescritos e agora **factualmente corretos**. Resíduo: sem teste (**A2**) e sem cobertura de formato (**A5**) |
| **R2** | admin recusa CNPJ mascarado | **Corrigido**, estruturalmente | Testado: admin real, inline real, `__all__`, `exclude`, widget custom, `inlineformset_factory`. `admin.py` intocado, como você descreveu |
| **R3** | `Estabelecimento` sem teste | **Corrigido** | Testado: M15 morre; 3 testes novos. Mas o **padrão do R3 reincide** no código novo → **A3** |
| **R4** | corrida devolve 500 | **Corrigido parcialmente** | Testado: criação (API Empresa, API Estabelecimento, tela) resolvida, 6/6. **`EmpresaDetailView` PUT/PATCH continua devolvendo 500, 6/6** → **A1** |
| **R5** | oráculo de unicidade entre escritórios | **Não corrigido, por decisão sua** (backlog do Fred) | Testado: ainda reproduz, agora também explicitamente em `Estabelecimento` |
| **R6** | plano/backlog/decisões sem registro | **Corrigido para a rodada 2**; **novo lapso na rodada 3** → **A4** | Inspecionado: DE-013 criada, seção de decisões no plano, BL-46 atualizado. Mas o plano ainda afirma "nenhuma migração" |
| **R7** | API não agrega erros de campo | **Corrigido** | Testado: 13 cargas, erros agregados |
| **R8** | comentário do `strip` incorreto | **Corrigido** | Inspecionado + Testado: comentário exato; NBSP/`\t`/`\n` no `parametrize` e `\u200b` como caso negativo |
| **R9** | testes não isolam o mecanismo | **Corrigido** | Testado: M8, M10 e M18 morrem, pelos testes exatos que os comentários alegam |
| **R10** | mensagens | **Corrigido** | Testado |

**Nada da rodada 1 voltou.** Refiz os sete: duplicidade por caixa (11 caminhos, incluindo agora os de massa), máscara no fluxo real (agora inclusive no admin), Unicode que expande no `.upper()`, fronteira `resto < 2`, tipo inválido, máscara em posição livre, e teste vacuoso. Todos continuam fechados.

---

## 3. Achados novos

### A1 — MÉDIA. **R4 reaberto**: `PUT`/`PATCH` de CNPJ ainda devolve **HTTP 500** sob corrida

O achado que mais importa nesta rodada. Você pediu certeza sobre a pergunta 5; a resposta é "sumiu na criação, ficou na alteração".

- **Requisito afetado:** AGENTS.md §7 (concorrência) e §8 (não ignorar exceções); R4 da rodada 2.
- **Local:** `/home/user/DataLedger/apps/empresas/views.py:71-78` — `EmpresaDetailView(generics.RetrieveUpdateAPIView)` **não** tem `perform_update`. O `try/except IntegrityError` foi posto em `perform_create` (`:60-67`), em `EstabelecimentoListCreateView.perform_create` (`:97-104`) e em `criar_empresa` (`:214-221`), e só lá.
- **Reprodução executada, duas formas:**
  - **Corrida real, 6 execuções com `threading.Barrier`**, duas empresas do mesmo escritório recebendo `PATCH` simultâneo para o mesmo CNPJ em caixas diferentes:
    ```
    rodada 0 {'A': 500, 'B': 200}     rodada 3 {'A': 500, 'B': 200}
    rodada 1 {'A': 500, 'B': 200}     rodada 4 {'A': 500, 'B': 200}
    rodada 2 {'A': 500, 'B': 200}     rodada 5 {'B': 500, 'A': 200}
    ```
    **6 de 6.** É mais reprodutível do que a corrida do `POST` que originou o R4, porque nenhum dos dois valores existe no banco quando os dois `UniqueValidator` fazem o seu `SELECT`.
  - **Determinística**, com `UniqueValidator.__call__` neutralizado por `monkeypatch`: `PATCH /empresas/api/empresas/<id>/` com CNPJ de outra empresa → **500**, corpo HTML de erro do Django.
- **Impacto:** dado íntegro (a *unique* segura, nenhuma duplicata persistiu). O que se perde é o mesmo do R4: 500 na cara do usuário, entrada de erro falso-positiva no log, e — pior — um achado declarado corrigido que continua vivo num caminho vizinho. A tela não tem edição hoje, então a superfície é a API; mas a API é contrato público do produto.
- **Correção recomendada:** `perform_update` em `EmpresaDetailView` com o mesmo `try/except IntegrityError` + `transaction.atomic()` + `mensagem_se_cnpj_duplicado`. Como o mesmo bloco já aparece três vezes e passaria a quatro, vale extraí-lo para um *mixin* ou um gerenciador de contexto em `services.py` (`with erro_de_cnpj_duplicado_como_400():`), para que o próximo caminho de gravação não seja esquecido de novo.
- **Como verificar:** teste determinístico com `UniqueValidator` neutralizado esperando 400 no `PATCH`; e teste de duas *threads* com barreira sobre o `PATCH`, aceitando `{200, 400}` como único par admissível.

### A2 — MÉDIA. A `CheckConstraint` — a correção inteira do R1 — **não tem um único teste**

- **Requisito afetado:** AGENTS.md §7 ("Toda alteração DEVE ter validação executada e registrada"); o "Como verificar" que o próprio R1 escreveu.
- **Local:** `/home/user/DataLedger/apps/empresas/models.py:17`, `:74-79`, `:190-206`; `apps/empresas/migrations/0002_alter_empresa_cnpj_alter_estabelecimento_cnpj_and_more.py:34-57`.
- **Reprodução executada:** removi as duas `CheckConstraint` **do `Meta` dos dois modelos e as duas `AddConstraint` da migração** — ou seja, desfiz a correção do R1 por inteiro — em cópia isolada:
  ```
  251 passed
  makemigrations --check --dry-run → No changes detected
  ```
  **A suíte inteira passa e a CI fica verde com o R1 desfeito.** Mutantes parciais também sobrevivem: `_CNPJ_E_CANONICO` só com `Q(cnpj=Upper("cnpj"))` (N13) → 93 passed; só com `~Q(cnpj__regex=...)` (N14) → 93 passed. Nenhuma das duas metades da condição está presa por teste.
  `grep` em `apps/empresas/tests/`: **nenhum** `bulk_create`, `bulk_update`, `QuerySet.update`, `loaddata` ou `deserialize`.
- **Impacto:** é exatamente a situação que eu descrevi no R3 da rodada anterior, agora aplicada à correção do R1. O código funciona — eu verifiquei —, mas isso é verificação minha, não teste versionado. A DL-010 vai importar em lote; se alguém remover ou afrouxar a constraint numa refatoração, nada acusa, e o defeito que volta é duplicata cadastral silenciosa no CNPJ que identifica a empresa perante a Receita.
- **Casos de teste propostos** (texto, para o `desenvolvedor-pleno` implementar):
  1. `test_bulk_create_com_cnpj_minusculo_e_barrado_pelo_banco` — `pytest.raises(IntegrityError)` em `transaction.atomic()` com `Empresa.objects.bulk_create([Empresa(..., cnpj="ab123cde000155")])`; e `assert "empresa_cnpj_canonico" in str(exc.value)` para prender a constraint pelo nome.
  2. Idem para `Estabelecimento`, com `estabelecimento_cnpj_canonico`.
  3. `test_queryset_update_para_cnpj_minusculo_e_barrado` e `test_bulk_update_para_cnpj_minusculo_e_barrado`.
  4. `test_bulk_create_com_cnpj_contendo_caractere_nao_alfanumerico_e_barrado` — `cnpj="11222333 00018"` (14 caracteres, com espaço): mata a metade do regex, que `Upper()` sozinho não pega.

### A3 — MÉDIA. Três partes do tratamento do R4 não têm teste, inclusive a guarda contra a armadilha da DL-007

- **Requisito afetado:** AGENTS.md §7; instrução explícita sua de não repetir a DL-007.
- **Local:** `apps/empresas/services.py:38-42`; `apps/empresas/views.py:97-104`; `apps/empresas/views.py:214-221`.
- **Reprodução executada, mutantes sobreviventes à suíte inteira:**
  - **N8** — trocar `if modelo is None: return None` por `if modelo is None: modelo = Empresa`, isto é, **traduzir todo `IntegrityError` em "CNPJ já existe"** — a repetição literal do erro da DL-007 → **93 passed, sobrevive**.
  - **N11** — apagar o `try/except` de `EstabelecimentoListCreateView.perform_create` → **93 passed, sobrevive**.
  - **N10** — apagar o `try/except` de `criar_empresa` (a tela) → **93 passed, sobrevive**.
  Só o caminho `POST /api/empresas/` está protegido, pelos dois testes novos (`..._neutralizando_o_unique_validator_da_400` e `..._corrida_real_com_duas_threads_nunca_devolve_500`), que matam N9.
- **Impacto:** o N8 é o mais sério dos três. O código está certo hoje — verifiquei que FK, `uma_matriz_por_empresa` e `empresa_cnpj_canonico` sobem sem tradução —, mas a guarda que impede mascarar defeito de sistema como erro de cliente pode ser apagada sem nenhuma falha. É a garantia que você pediu que eu conferisse, e ela existe **só como código**.
- **Casos de teste propostos:**
  1. `test_integrityerror_de_outra_constraint_nao_vira_erro_de_cnpj` — criar duas matrizes para a mesma empresa dentro de `pytest.raises(IntegrityError)`, e `assert mensagem_se_cnpj_duplicado(exc) is None`; repetir para violação de FK e para `empresa_cnpj_canonico`.
  2. `test_criar_estabelecimento_via_api_com_corrida_neutralizando_o_unique_validator_da_400` — espelho exato do teste de `Empresa`.
  3. `test_criar_empresa_pela_tela_com_corrida_neutralizando_o_validate_unique_da_erro_de_campo` — `monkeypatch` em `BaseModelForm.validate_unique`, esperando 200 com "já existe" no corpo e uma única linha no banco. Reproduzi os três por sonda; os três passam no código atual.

### A4 — MÉDIA (documentação). O plano afirma que a etapa **não cria migração**, e a rodada 3 criou uma que **falha em base com dado não canônico**

- **Requisito afetado:** AGENTS.md §3 (o plano DEVE conter estratégia de reversão e evidências) e §5.4; é o R6 reaparecendo por caminho novo, que é justamente o que você pediu que eu vigiasse.
- **Local:** `docs/planos/DL-011-cnpj-alfanumerico.md:16` — *"A etapa não cria migração de dados. Reverter é `git revert` dos commits de código; nenhum dado gravado precisa ser desfeito."* — e `:189` — *"**Dados:** nenhum. Compatibilidade retroativa verificada; nenhuma migração."* As linhas `:12`, `:13` e `:15` também continuam apontando para a rodada 2 (`fe5387d`, base `f65d418`, "225 testes", "120 arquivos").
- **Reprodução executada:** em banco descartável, apliquei `migrate empresas 0001`, inseri por SQL cru uma empresa com `cnpj='ab123cde000155'`, e apliquei a `0002`:
  ```
  MIGRACAO FALHOU: IntegrityError
  check constraint "empresa_cnpj_canonico" of relation "empresas_empresa" is violated by some row
  ```
  A falha é **limpa** (transação atômica; `django_migrations` continua em `0001`, nenhuma constraint parcial), o que é bom. Mas o *deploy* para.
- **Impacto:** baixo em probabilidade, alto em custo se acontecer. Base de produção anterior à DL-011 dificilmente tem CNPJ não canônico (o validador recusava letras e a coluna é `varchar(14)`), então o risco real é pequeno — mas é uma afirmação minha, não um fato verificado contra a base do Fred, e ninguém que leia o plano hoje saberia que precisa verificar. Segundo ponto, independente: `git revert` dos commits **não desfaz a constraint no banco**; depois de reverter o código, o banco continua recusando o que o código revertido volta a produzir. A estratégia de reversão escrita no plano está incorreta para esta rodada.
- **Correção recomendada:** atualizar o plano com estado, commit (`6ae84e5`), base (`6e6e088`), evidências da rodada 3, e reescrever as duas afirmações: a etapa **cria** a migração `0002`, de esquema, com duas `CheckConstraint` **validantes**; reverter exige `python manage.py migrate empresas 0001` **antes** do `git revert`; e antes de aplicar em base existente, rodar `SELECT count(*) FROM empresas_empresa WHERE cnpj <> upper(cnpj) OR cnpj ~ '[^A-Z0-9]'` (e o equivalente em `empresas_estabelecimento`), esperando zero.
- **Como verificar:** leitura do plano; `scripts/validate-docs.ps1` limpo; a consulta de pré-checagem executada e registrada.

### A5 — BAIXA. A `CheckConstraint` garante **canonicidade**, não **formato**: `bulk_create` grava CNPJ vazio, curto ou com DV errado

- **Requisito afetado:** critério 11; DE-008 (camada 1); o comentário de `models.py:92-96`, que aponta a constraint como "a garantia real" para a importação em lote da DL-010.
- **Local:** `apps/empresas/models.py:17`.
- **Reprodução executada** (`bulk_create`, cópia isolada, banco de teste):
  ```
  cnpj='ABC'            → PASSOU        cnpj='00000000000000' → PASSOU
  cnpj='AB123CDE000199' → PASSOU (DV errado)
  cnpj='AB123CDE0001AA' → PASSOU (letra no DV)
  cnpj=''               → PASSOU  ← CNPJ VAZIO gravado
  ```
  Todos são recusados por `normalizar_cnpj`/`validar_cnpj`, e todos passam pela constraint.
- **Impacto:** latente, sem caminho de requisição hoje. Mas o comentário nomeia a DL-010 e o `bulk_create` como o motivo de a constraint existir; quem ler isso e importar em lote vai gravar lixo no campo que identifica a empresa perante a Receita, com a proteção que o comentário prometeu. A frase "é *no-op* sobre valor já canônico: não rejeita nenhum dado que `normalizar_cnpj` já aceitaria" é verdadeira, mas é a direção que não interessa.
- **Correção recomendada:** trocar a condição por `~Q(cnpj__regex=r"^[A-Z0-9]{12}[0-9]{2}$")` negado — isto é, `Q(cnpj__regex=r"^[A-Z0-9]{12}[0-9]{2}$")` — que impõe caixa, conjunto, comprimento e DV numérico numa expressão só, e é exatamente a regex oficial do Anexo I citada em `validators.py:14`. O DV calculado continua fora do alcance do banco, e isso deve ficar escrito. Conferi que todos os CNPJs de `Empresa`/`Estabelecimento` na suíte satisfazem essa regex, então a migração continuaria aplicando sem violação. **Não avaliei se alguma base real do Fred a satisfaz** — a pré-checagem do A4 cobriria isso.
- **Como verificar:** `bulk_create` com `""`, `"ABC"` e `"AB123CDE0001AA"` esperando `IntegrityError`; e o comentário de `models.py` declarando explicitamente que o DV **não** é verificado pelo banco.

### A6 — BAIXA (qualidade de teste). A normalização do `CNPJSerializerField` e o `UniqueValidator` reposto à mão não estão presos por teste

- **Local:** `apps/empresas/fields.py:99-102`; `apps/empresas/serializers.py:24-35` e `:57-63`.
- **Reprodução executada, mutantes sobreviventes:**
  - **N6** — `to_internal_value` validar mas **não** normalizar (`return data`) → **93 passed, sobrevive**.
  - **N12** — remover o `UniqueValidator` de `EmpresaSerializer.cnpj` → **93 passed, sobrevive**.
  - **N4** — remover `"max_length": None` de `CNPJModelField.formfield` → sobrevive, mas é **mutante equivalente**: `to_python` normaliza antes do `MaxLengthValidator`, exatamente como a *docstring* explica. Não é achado.
- **Impacto:** N6 e N12 são hoje equivalentes na prática, e por um bom motivo: `Model.save()` canoniza depois, e o `IntegrityError` traduzido devolve a mesma mensagem que o `UniqueValidator` devolveria. É defesa em profundidade funcionando. O problema é que isso significa que **cada camada só está protegida pela existência da outra** — e a tradução do `IntegrityError` também não tem teste em dois dos três caminhos (A3). Se duas caírem juntas numa refatoração, nada acusa. Vale um teste que prenda a camada do serializer sozinha: `EmpresaSerializer(data={"cnpj": "ab.123.cde/0001-55", ...})`, `is_valid()`, e `assert serializer.validated_data["cnpj"] == "AB123CDE000155"` — sem passar por `save()`.

### A7 — BAIXA (informativo, não é defeito). O campo de CNPJ perdeu o `maxlength` no HTML

`<input type="text" name="cnpj" required id="id_cnpj">` — sem `maxlength`. Foi consequência necessária e correta da correção do R2 (o `maxlength="14"` truncava a máscara no navegador). O servidor recusa qualquer coisa fora do formato, então não há risco. Se o `especialista-frontend` quiser dica de digitação, `maxlength="18"` é o máximo semanticamente possível. Item de UX para backlog, não para esta etapa.

### Observações preexistentes, reconfirmadas, fora do escopo da DL-011

- **R5 continua valendo** e agora aparece também em `Estabelecimento`, com `UniqueValidator(queryset=Estabelecimento.objects.all())` explícito em `serializers.py:29`. Reproduzido: gestor de A recebe `400 {"cnpj":["empresa com este CNPJ já existe."]}` para CNPJ cadastrado em B. Preexistente da DL-004, decisão do Fred, **não pesa contra esta etapa**.
- `POST` *form-encoded* criando empresa com `ativo: false` — não reexaminei nesta rodada; permanece como registrei.
- `apps/tenancy/models.py:14` — `Escritorio.cnpj` continua sem validação e sem canonização (BL-47). A justificativa de não estendê-lo aqui está correta e agora bem documentada em `models.py:113-124`.

---

## 4. Critérios de aceite

| # | Critério | Resultado | Classificação |
| --- | --- | --- | --- |
| 1 | Cinco CNPJs numéricos continuam válidos | Atende, 5/5 | Testado |
| 2 | Alfanumérico com DV correto é aceito | Atende (unitário, tela, API, admin, inline, persistência) | Testado |
| 3 | Alfanumérico com DV errado é recusado | Atende, com mensagem específica | Testado |
| 4 | Letra nas posições 13-14 é recusada | Atende, mensagem específica com e sem máscara | Testado |
| 5 | 13 ou 15 caracteres recusados | Atende | Testado |
| 6 | `00000000000000` recusado | Atende no validador. **Ressalva:** passa pela `CheckConstraint` em `bulk_create` (A5) | Testado |
| 7 | Máscara aceita e removida | **Atende, e agora também no admin e no inline** — a ressalva dupla da rodada 2 caiu. Permanece o estreitamento, agora **registrado** em DE-013 e no plano | Testado |
| 8 | Minúsculas normalizadas, validadas e persistidas canônicas | Atende, em todos os caminhos de requisição e agora também nos de massa | Testado |
| 9 | Caractere fora de `[A-Z0-9./-]` recusado com mensagem útil | Atende; a mensagem ruim acima de 32 caracteres sumiu (R10) | Testado |
| 10 | Nenhum ponto do sistema descarta letras ao normalizar | Atende. `normalizar_cnpj` continua função única; `_mascara_cnpj` é só apresentação; a busca do admin é `icontains`. A ressalva de massa do R1 caiu | Inspecionado + Testado |
| 11 | Modelo persiste alfanumérico sem truncar | Atende (`varchar(14)`, `AB123CDE000155`). **Ressalva:** A5 | Testado |
| 12 | Comentário cita NT 2025.001 e IN RFB 2.229 | Atende (`validators.py:5-9`); `fields.py` e `models.py` referenciam corretamente os achados | Inspecionado |
| 13 | Sem regressão; ferramentas limpas | Atende: 251 passed, ruff/format (123 arquivos)/check/makemigrations limpos. **`scripts/validate-docs.ps1` não executado — `pwsh` ausente** | Testado / **Bloqueado** no item da documentação |

Paliativo do item bloqueado, **não equivalente**: reimplementei as cinco regras do script sobre os 39 `.md` → 0 problemas.

Não avaliei conformidade jurídica da NT 2025.001 nem da IN RFB 2.229 — validação profissional do Fred. Não afirmo ausência de outros defeitos.

---

## 5. Integridade da árvore

`git status --short` ao final: **uma linha, que não é minha** —

```
 M docs/projeto/requisitos.md
```

O conteúdo é a inclusão de **RC-48** (implantação em nuvem, servidor único) e **RC-49** (cerca de 50 usuários simultâneos), mais a marcação de **PE-04** como parcialmente resolvida. É trabalho de requisitos, sem relação com a DL-011, não toca `apps/` e **não afeta nada do que auditei**. Registro porque a árvore não estava limpa quando terminei, e você precisa saber de onde veio antes de commitar.

Sobre o que é meu: **nada**. Não tenho `Write` nem `Edit`; todo comando que executei escreveu apenas sob o scratchpad. `git diff --cached --stat`: vazio. `HEAD` = `6ae84e5`, como recebido. `git status --short --ignored` mostra só `.pytest_cache/`, `.ruff_cache/` e `__pycache__/`, todos com data anterior a esta sessão.

Fora do repositório, no scratchpad: cópia `git archive 6ae84e5` (conferida por `diff -r`), 20 cópias descartáveis de mutação (todas removidas), três sondas em `apps/empresas/tests/` **da cópia** (todas removidas), e o banco `aud_r3`, criado e destruído. Nenhum `ruff format` sem `--check`. Nenhum commit, nenhum push. Não deleguei a ninguém.

---

# APROVADO COM RESSALVAS

A rodada 3 é a melhor das três. Oito dos dez achados estão fechados, e dois deles — R1 e R2 — foram resolvidos na raiz, não remendados: a canonização subiu para a camada 1 da DE-008 e a normalização de formulário passou a viver no campo do modelo, o que fez o admin, o *inline*, o `inlineformset_factory` e qualquer `ModelForm` futuro herdarem o comportamento certo sem uma linha em `admin.py`. A `CheckConstraint` resiste a acento, cedilha, dobra de caixa e caractere de largura variável, sob *collation* `C` e ICU `pt-BR`. A tradução do `IntegrityError` não caiu na armadilha da DL-007. As duas autodenúncias do `desenvolvedor-pleno` sobre M8 e M15 são **verdadeiras nas duas metades** — replantei os dois mutantes e confirmei o mecanismo que ele descreveu, inclusive removendo a constraint para provar a explicação dele. Isso é honestidade de relatório do tipo que a AGENTS.md pede, e merece registro.

Nenhum achado desta rodada é bloqueador ou de gravidade alta, nenhum critério de aceite deixou de ser atendido, e o isolamento entre escritórios não regrediu.

**Separação que você pediu, para decidir se fecha a etapa.**

**Tem de entrar antes de a etapa fechar** (três itens):

1. **A1 — o R4 continua aberto no `PUT`/`PATCH`.** 500 reproduzido 6 de 6 com *threads* e de forma determinística. É um achado que já foi reportado uma vez e declarado corrigido; fechar a etapa com ele vivo torna o registro da rodada 2 falso. Graduei média, e não alta, por consistência: é o mesmo sintoma que graduei média na criação, num caminho estritamente menos provável. Mas a gravidade menor não muda que é um item **reaberto**, e é por isso que ele entra aqui e não no backlog.
2. **A2 — a correção do R1 não tem teste.** Desfiz a `CheckConstraint` por inteiro, em modelo e migração, e a suíte passa com 251 e a CI fica verde. AGENTS.md §7 não está cumprido para a principal mudança estrutural da rodada. É literalmente a mesma situação que me levou a abrir o R3 na rodada passada.
3. **A4 — o plano afirma que a etapa não cria migração, e ela cria uma que pode falhar no *deploy*.** Correção de documento, custo de minutos, e é a diferença entre saber e descobrir em produção. Inclui reescrever a estratégia de reversão, que hoje está incorreta.

**Pode ir para backlog próprio** (quatro itens):

4. **A3 — testes para a guarda anti-DL-007, para a tela e para `Estabelecimento`.** O código está certo; verifiquei os três. É dívida de cobertura, não defeito. Se preferir agrupar com o teste do A1 numa passada só, melhor ainda — mas não trava o fechamento.
5. **A5 — fortalecer a `CheckConstraint` para `^[A-Z0-9]{12}[0-9]{2}$`.** Latente, sem caminho de requisição hoje. **Deve estar resolvido antes de a DL-010 importar em lote**, e é natural que vá para lá.
6. **A6 — prender a camada do serializer sozinha.** Qualidade de teste.
7. **A7 — `maxlength` no HTML.** UX, para o `especialista-frontend`.

**R5** permanece como estava: preexistente, decisão do Fred, item próprio.

Encaminhar A1, A2, A3, A5 e A6 ao `desenvolvedor-pleno`; A4 é seu; A7 ao `especialista-frontend`.

Por fim, os arquivos que importam para quem for corrigir: `/home/user/DataLedger/apps/empresas/views.py` (A1, linha 71), `/home/user/DataLedger/apps/empresas/models.py` (A2 e A5, linha 17), `/home/user/DataLedger/apps/empresas/services.py` (A3, linhas 38-42), `/home/user/DataLedger/docs/planos/DL-011-cnpj-alfanumerico.md` (A4, linhas 16 e 189) e `/home/user/DataLedger/apps/empresas/fields.py` (A6, linhas 99-102).
