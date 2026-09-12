# Reauditoria DL-011 — CNPJ alfanumérico — rodada 2 — 2026-09-12

Parecer do `auditor-qa` sobre a **rodada 2** da etapa
[DL-011](../planos/DL-011-cnpj-alfanumerico.md), que fecha o BL-46. A rodada 1
foi **reprovada**; ver
[o relatório anterior](2026-09-12-dl-011-cnpj-alfanumerico.md).

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**. O texto abaixo é o relatório do auditor, sem edição.

## Parecer

**APROVADO COM RESSALVAS.** Dez achados, nenhum bloqueador e nenhum de
gravidade alta. Os sete achados da rodada 1 foram atacados; dois voltaram por
caminho diferente.

### Decisão do `arquiteto-senior` sobre a calibração do R2

O auditor deixou explícito que o R2 — CNPJ mascarado recusado no Django admin,
com a mensagem literal do achado 2 da rodada 1 — **seria de gravidade alta, e o
parecer seria REPROVADO**, caso o admin seja considerado superfície de cadastro
de produção. Ele se recusou, corretamente, a decidir isso por conta própria.

**Decisão: corrigir o R2 nesta etapa, sem submeter a pergunta.** O motivo é que
a resposta não muda o trabalho. `Estabelecimento` **não tem tela própria**, logo
o *inline* do admin é hoje a única interface humana desse modelo — o que torna a
pergunta acadêmica. Corrigir custa pouco e remove a dúvida; perguntar custaria
uma rodada de espera para chegar ao mesmo lugar.

### Distribuição

| Achado | Encaminhado a |
| --- | --- |
| R1, R2, R3, R4, R7, R8, R9, R10 | `desenvolvedor-pleno` |
| R6 (plano, backlog e decisões sem registro) | `arquiteto-senior` — é falha minha |
| R5 (unicidade global de CNPJ como oráculo entre escritórios) | backlog próprio; **decisão do Fred** |
| `ativo: false` em POST *form-encoded* | backlog próprio; preexistente |

---

# Reauditoria DL-011 — CNPJ alfanumérico (BL-46) — rodada 2

Versão auditada: `fe5387d`, branch `claude/accounting-agent-team-setup-mn6lyf`. Base de comparação: `f65d418` e `fd41aba` (commit da auditoria da rodada 1).

**Ambiente:** venv isolada no scratchpad (Python 3.14.0rc2, Django 6.1.1, DRF 3.18.1, pytest 9.1.1, ruff 0.16.7), PostgreSQL 16 em `localhost:5432`, `DEBUG=True` (igual ao que `.github/workflows/backend.yml` define). Mutação e sondas rodaram em cópias `git archive fe5387d` dentro do scratchpad; nenhum arquivo do repositório foi alterado.

---

## 1. Verificação favorável

**Algoritmo do DV — Testado, com implementação independente minha.** Escrevi do zero uma segunda implementação (formulação clássica de peso 2..9 da direita para a esquerda, `ord(c)-48`) e confirmei, sem reaproveitar nada do código auditado:

- Os cinco CNPJs da tabela de compatibilidade do plano: DV calculado igual ao informado, 5/5.
- Das 36 sequências de 14 caracteres repetidos (0-9, A-Z), **só `00000000000000`** tem DV coerente. **Seu número está certo.**
- Os quatro casos de fronteira do achado 4 têm de fato resto 0/1: `72981506162202` (resto1=1), `11070434192580` (resto2=1), `24365234257800` (resto 0 nos dois), `CR6G1EWE2BK600` (resto 1 nos dois). **Seus quatro casos conferem.**
- Os CNPJs de `Escritorio` que você citou em `models.py:87-89` são mesmo inválidos pelo DV oficial (`11111111000111` → DV calculado 91, informado 11; idem os outros quatro). **A justificativa de não estender a canonização a `Escritorio` está factualmente correta.**

**Verificações obrigatórias — Testado.** `pytest -q` → **225 passed**. `ruff check .` → All checks passed. `ruff format --check .` → 120 files already formatted. `manage.py check` → 0 issues. `makemigrations --check --dry-run` → No changes detected. Confirmo seus números.

**Achado 1 está morto em todos os caminhos de requisição que consegui encontrar — Testado.** Tentei criar duplicata por caixa e por máscara em: API JSON, API form-encoded (`QueryDict` imutável), API multipart, `PATCH`, `PUT`, formulário da tela, `.objects.create()`, `get_or_create()`, `update_or_create()`, API de `Estabelecimento` e `Estabelecimento.objects.create()`. **Em nenhum deles o banco ficou com duas linhas.** Respostas: `400 {"cnpj":["empresa com este CNPJ já existe."]}` nos caminhos HTTP, `IntegrityError` no ORM direto. O `.copy()` funciona nos três tipos de `data`.

**`max_length=32` não abre porta — Testado.** Entrada de 32 caracteres chega a `normalizar_cnpj` e é recusada com a mensagem de formato; a coluna do banco continua `varchar(14)` e `normalizar_cnpj` só devolve 14 caracteres. Nada estoura antes (confirmei também que `bulk_create` com máscara morre no `DataError` do Postgres, ou seja, a coluna é a última linha de defesa e ela existe).

**`_normalizar_cnpj_do_payload` — Testado.** `cnpj` como `int` → 201 (DRF converte); `None` → 400 "não pode ser nulo"; lista/dict/bool → 400 "Não é uma string válida"; `float` → 400 de formato; `PATCH` parcial sem `cnpj` → 200 sem tocar no campo; corpo JSON como lista → 400 tratado. **Nenhum 500, nenhum `AttributeError`.**

**Achado 3 fechado de verdade — Testado.** Recusou todos os casos Unicode que consegui construir, em 13, 14 e 15 caracteres: `ß123CDE0001177`, `ıB123CDE000155` (dotless i → `I`, sem mudar comprimento), `ſB123CDE000155`, `AB123CDE00015５` (dígito fullwidth), `11222333000181\u200b` (zero-width space).

**Máscara estrita funciona — Testado.** Sete leiautes recusados, só o exato aceito: `11-122-233.0001/83`, `11/122/233-0001.83`, `11.122.233-0001/83`, `11.122.233/0001.83`, `11122.233/0001-83`, `1.1122.233/0001-83` — todos recusados; `11.122.233/0001-83` aceito.

**Isolamento entre escritórios não regrediu — Testado.** Suíte de isolamento de `empresas` e de `tenancy` passa; `EmpresaSerializer.create` continua forçando `escritorio` da requisição; listagem do gestor de A com empresa de B cadastrada devolve `[]`; empresa de outro escritório em `PATCH`/detalhe dá 404. Nenhuma consulta nova por CNPJ foi introduzida.

**Mutação — Testado, 20 mutantes, 14 mortos.** Morreram: remoção do `.strip()`, `.upper()` antes da checagem de conjunto, remoção do `isinstance`, `_FORMATO_CNPJ` permissivo no DV, remoção do `.upper()` na saída, `resto < 1`, remoção da rejeição do CNPJ zerado, `Empresa.save()` sem canonizar, volta ao campo automático do form, `clean_cnpj` sem normalizar, e a remoção do `to_internal_value` de cada serializer. Os seis sobreviventes estão tratados abaixo (três são equivalentes por causa de `fullmatch`; três são achados).

---

## 2. Achados

### R1 — MÉDIA. A canonização **não** fecha todos os caminhos de gravação; o comentário afirma que fecha

- **Requisito afetado:** critério 10; DE-008 (ordem de preferência das camadas); AGENTS.md §9 (comentário não pode ficar incorreto).
- **Local:** `/home/user/DataLedger/apps/empresas/models.py:63-64` — o comentário diz "antes de gravar, **em todo caminho de ORM**". `models.py:94` e `models.py:172`.
- **Reprodução executada** (cópia isolada, banco de teste, sonda `test_probe_escape.py`):
  - `Empresa.objects.bulk_create([...cnpj="ab123cde000155"])` grava `'ab123cde000155'`; um segundo `bulk_create` com `"AB123CDE000155"` **grava a segunda linha** → `['ab123cde000155', 'AB123CDE000155']`, duas empresas para o mesmo CNPJ. Exatamente o achado 1 da rodada 1.
  - `Empresa.objects.all().update(cnpj="ab123cde000155")` → grava minúsculo.
  - `Empresa.objects.bulk_update([e], ["cnpj"])` → grava minúsculo.
  - Desserialização de fixture (`serializers.deserialize("json", ...)` + `obj.save()`, o caminho do `loaddata`, que usa `save_base`) → grava `'ab123cde000155'`.
  - `Estabelecimento.objects.bulk_create(...)` → idem.
  - `get_or_create`, `update_or_create` e `save(update_fields=...)` **passam** por `save()` e canonizam corretamente.
- **Impacto:** hoje nenhum desses métodos é usado em código de produção (verifiquei: `grep` por `bulk_create|bulk_update|\.update(|loaddata|save_base` fora de testes não retorna nada), então **não há defeito alcançável por requisição**. O risco é latente e o comentário do código induz o próximo desenvolvedor ao erro: quem ler "em todo caminho de ORM" vai usar `bulk_create` numa importação da DL-010 achando que está protegido. DE-008 diz textualmente que a restrição de banco é a camada mais forte porque "sobrevive a shell, ORM, admin e corrida entre requisições" — a escolha feita aqui (`Model.save()`) não está em nenhuma das três camadas que DE-008 lista.
- **Correção recomendada:** subir a canonização para a camada 1. Duas opções, ambas compatíveis com dados existentes por serem no-op sobre valor já canônico: `CheckConstraint(condition=Q(cnpj=Upper("cnpj")) & ~Q(cnpj__regex=r"[^A-Z0-9]"), name="cnpj_canonico")` em `Empresa` e `Estabelecimento`; ou índice único funcional sobre `Upper("cnpj")`. Manter o `save()` como conveniência. Enquanto isso não existir, **corrigir o comentário** para dizer exatamente quais caminhos cobre e quais não cobre.
- **Como verificar:** com a constraint, os cinco casos reproduzidos acima devem virar `IntegrityError`; e a migração deve aplicar em banco com os dados atuais sem violação.

### R2 — MÉDIA. Achado 2 **reapareceu por outro caminho**: o Django admin ainda recusa CNPJ mascarado com a mesma mensagem da rodada 1

Este é o achado que você pediu que eu destacasse.

- **Requisito afetado:** critérios 7 e 9; achado 2 da rodada 1.
- **Local:** `/home/user/DataLedger/apps/empresas/admin.py:16-21` (`EmpresaAdmin`) e `:6-8` (`EstabelecimentoInline`). Nenhum dos dois usa `EmpresaForm`; o admin gera o `ModelForm` automático a partir de `models.py:53` / `:144`, com `max_length=14`.
- **Reprodução executada** (sonda `test_probe_admin.py`, `modelform_factory(Empresa, ...)`, que é o que o admin usa):
  ```
  max_length do campo cnpj gerado: 14
  ADMIN Empresa '11.122.233/0001-83' valido= False
    <li>Certifique-se de que o valor tenha no máximo 14 caracteres (ele possui 18).</li>
  ```
  É a **mesma mensagem literal** que a rodada 1 registrou como achado 2 de gravidade alta. `ab123cde000155` (minúsculo, sem máscara) é aceito e canonizado pelo `save()`, então a parte de caixa está boa; só a máscara falha.
- **Impacto:** um usuário de staff que cadastre ou corrija empresa/estabelecimento pelo admin — e digitar CNPJ com máscara é hábito universal no Brasil — é bloqueado com uma mensagem que não explica nada. `Estabelecimento` **não tem tela própria** (conferi `templates/`: só `empresas/form.html`, `lista.html`, `sem_escritorio.html`), então o admin inline é a única interface humana desse modelo, e é justamente a que ficou de fora.
- **Correção recomendada:** `EmpresaAdmin.form = EmpresaForm`; e um `EstabelecimentoForm` equivalente (campo `cnpj` declarado com folga e `clean_cnpj` chamando `normalizar_cnpj`) em `EstabelecimentoInline.form`. Alternativa mais estrutural, que resolve as duas de uma vez sem duplicar código: criar um `CNPJFormField(forms.CharField)` com `to_python` chamando `normalizar_cnpj`, e apontar `Empresa.cnpj`/`Estabelecimento.cnpj` para um `CNPJModelField` cujo `formfield()` devolva esse campo — aí todo `ModelForm`, inclusive o do admin, herda o comportamento.
- **Como verificar:** teste com o form do admin (`modelform_factory` ou `admin.site._registry[Empresa].get_form(request)`) postando `"11.122.233/0001-83"` e `"ab.123.cde/0001-55"`, esperando `is_valid() is True` e valor gravado canônico; idem para o inline de `Estabelecimento`.
- **Calibração, para você decidir:** graduei em média porque o admin é superfície de staff e existe tela dedicada de cadastro. **Se o Fred considerar o admin uma superfície de cadastro de produção, isto é alta e o parecer vira REPROVADO.** Registro a dependência explicitamente em vez de decidir por ele.

### R3 — MÉDIA. A extensão a `Estabelecimento` não tem **nenhum** teste que a proteja; o mutante sobrevive à suíte inteira

- **Requisito afetado:** AGENTS.md §7 ("Toda alteração DEVE ter validação executada e registrada"; "Correção de defeito: teste de regressão que reproduza a falha").
- **Local:** `/home/user/DataLedger/apps/empresas/models.py:168-173`.
- **Reprodução executada:** mutante **M15** — apagar `self.cnpj = normalizar_cnpj(self.cnpj)` de `Estabelecimento.save()`, deixando `Empresa.save()` intacto → **225 testes continuam passando** (`67 passed` em `apps/empresas`). O mutante equivalente em `Empresa.save()` (M14) mata 2 testes. O único teste de `Estabelecimento` da entrega (`apps/empresas/tests/test_api.py:104-117`) usa `"11.122.233/0001-83"`, cuja normalização acontece no `to_internal_value` do serializer — o `save()` fica irrelevante para ele.
- **Sobre o seu número:** sua mutação "removi a canonização dos dois `save()` e dois testes falharam" está tecnicamente correta, mas **as duas falhas vêm inteiramente de `Empresa`**. A metade `Estabelecimento` da correção — que é uma decisão sua, tomada além do escopo da rodada 1 — está a zero de cobertura. Confirmei por sonda que o código **funciona** (`Estabelecimento.objects.create(cnpj="ab123cde000155")` depois de um `"AB123CDE000155"` → `IntegrityError`; `create(cnpj="ab.123.cde/0001-55")` grava `'AB123CDE000155'`), mas isso é minha verificação, não um teste versionado.
- **Impacto:** a proteção de `Estabelecimento` pode ser removida por refatoração futura sem que nada acuse. Como `Estabelecimento.cnpj` também é `unique=True` global, o efeito seria o mesmo do achado 1: duplicata cadastral silenciosa, agora no CNPJ que identifica a filial perante a Receita.
- **Casos de teste propostos** (para `desenvolvedor-pleno` implementar; entrego como texto, não implemento):
  1. `test_estabelecimento_com_cnpj_em_caixas_diferentes_nao_duplica_registro` — criar estabelecimento com `"AB123CDE000155"` e, em `pytest.raises(IntegrityError)` dentro de `transaction.atomic()`, tentar `"ab123cde000155"`; ao final `count() == 1`.
  2. `test_estabelecimento_persiste_cnpj_canonico_via_objects_create` — `Estabelecimento.objects.create(cnpj="ab.123.cde/0001-55")`, `refresh_from_db()`, esperar `"AB123CDE000155"`.
  3. No teste de API existente, trocar `"11.122.233/0001-83"` por um alfanumérico minúsculo e mascarado, para que o teste de ponta a ponta exercite caixa além de máscara.

### R4 — MÉDIA. Corrida na unicidade do CNPJ devolve **HTTP 500**, não erro tratado

Responde diretamente à sua pergunta 5: **a constraint resolve — nenhuma duplicata é persistida — mas aparece 500.**

- **Requisito afetado:** AGENTS.md §7 ("Testar repetição de operações, concorrência e recuperação quando houver risco de duplicidade") e §8 ("Tratar erros de maneira consistente, com mensagens úteis"; "Não ignorar exceções").
- **Local:** `apps/empresas/views.py:37-49` (`EmpresaListCreateView.perform_create`) e `:142-176` (`criar_empresa`); `apps/empresas/serializers.py:72-76`.
- **Reprodução executada** (`test_probe_corrida2.py`, duas threads reais com `threading.Barrier`, `django_db(transaction=True)`, `Client(raise_request_exception=False)`, três execuções):
  ```
  {'A': 201, 'B': 400}   gravado: ['AB123CDE000155']
  {'A': 201, 'B': 500}   gravado: ['AB123CDE000155']
  {'B': 201, 'A': 500}   gravado: ['AB123CDE000155']
  ```
  Nas duas execuções em que as duas requisições entraram na janela, o perdedor recebeu **500**. O `UniqueValidator` do DRF faz `SELECT` e depois `INSERT`; entre os dois, o concorrente comita, e o `IntegrityError` sai sem tratamento. Confirmei o mecanismo também de forma determinística, neutralizando o `UniqueValidator` (API) e o `validate_unique` (formulário): nos dois caminhos a exceção que escapa é `IntegrityError: duplicate key value violates unique constraint "empresas_empresa_cnpj_key"`.
- **Impacto:** dado íntegro (a constraint segura), experiência ruim e log de erro falso-positivo. Esta etapa **aumenta** a probabilidade de acontecer: antes, dois operadores colando o mesmo CNPJ alfanumérico em caixas diferentes geravam duas linhas sem colidir; agora colidem — a troca é boa, mas o tratamento do erro não acompanhou.
- **Correção recomendada:** envolver a criação em `try/except IntegrityError` na `perform_create`/`create` (e na view de tela), convertendo em `ValidationError` de campo com a mesma mensagem do `UniqueValidator`, ou em 409. Vale para `Empresa` e `Estabelecimento`.
- **Como verificar:** teste com duas threads e barreira (como o meu), aceitando `{201, 400}` como o único par de status admissível, executado algumas vezes; e teste determinístico com o `UniqueValidator` neutralizado por `monkeypatch`, esperando 400.

### R5 — MÉDIA (preexistente). `unique=True` global no CNPJ transforma o cadastro em oráculo de existência entre escritórios

- **Requisito afetado:** AGENTS.md §11 ("Aplicar isolamento também a arquivos, buscas, cache, filas, relatórios e registros"); contradiz a regra que o próprio projeto escreveu em `apps/empresas/mixins.py:10-12` ("404, não 403: não confirma nem a existência do registro para quem não tem acesso").
- **Local:** `apps/empresas/models.py:53` e `:144` (`unique=True` sem escopo de escritório).
- **Reprodução executada:** empresa `AB123CDE000155` cadastrada no **escritório B**; gestor do **escritório A**, autenticado, envia o mesmo CNPJ:
  - API → `400 {"cnpj":["empresa com este CNPJ já existe."]}`
  - Tela → 200 com "já existe" no corpo
  - `GET` da lista do gestor A → `[]` (o isolamento de leitura está correto)
- **Impacto:** um escritório consegue descobrir, um CNPJ por tentativa, se determinada empresa já é cliente de **outro** escritório do mesmo DataLedger. Em produto multiempresa para mercado concorrencial, isso é informação comercial. Não revela razão social nem qual escritório.
- **É preexistente** (vem da DL-004, não desta etapa) e portanto **não é motivo de reprovação da DL-011**. Registro aqui porque você pediu certeza sobre isolamento e porque a DL-011 é a etapa que mexe no campo de identificação: a canonização **amplia** o alcance do oráculo, que antes podia ser driblado por diferença de caixa.
- **Correção recomendada:** decisão do Fred, em item próprio de backlog. As saídas usuais são: unicidade por `(escritorio, cnpj)` com verificação global só em fluxo administrativo; ou mensagem genérica ("não foi possível cadastrar este CNPJ; fale com o suporte") quando o conflito for fora do escritório ativo, mantendo a mensagem específica quando for dentro.
- **Como verificar:** teste de isolamento que cadastre o CNPJ no escritório B e verifique que a resposta ao escritório A **não** afirma existência; e que o cadastro dentro do próprio escritório continue com a mensagem específica.

### R6 — MÉDIA (processo e documentação). Plano e backlog não foram atualizados na rodada 2, e três decisões de engenharia ficaram sem registro

- **Requisito afetado:** AGENTS.md §3 (o plano DEVE conter branch de trabalho/destino, estratégia de reversão, evidências, commit e PR; estados `em validação`/`em revisão`/`integrada`), §5.4 ("Atualizar a documentação e o registro da etapa"), §15.
- **Local:** `docs/planos/DL-011-cnpj-alfanumerico.md:6` — **"Estado: em desenvolvimento"**. `docs/projeto/backlog.md:38` — BL-46 ainda em "**em desenvolvimento** — rodada 1 reprovada pela auditoria, correções em curso".
- **Reprodução executada:** `git log --name-only fd41aba..fe5387d` — os commits `fc36f4c`, `6ddc201` e `fe5387d` tocam **exclusivamente** `apps/empresas/`. Nenhum arquivo em `docs/planos/` foi alterado na rodada 2. O plano não tem seção de branch, reversão nem evidências.
- **O que ficou sem registro, e por que importa:**
  1. **Extensão a `Estabelecimento`** — decisão sua, correta, e invisível no plano. O escopo do plano fala de "campo do modelo" no singular.
  2. **Aceitação de espaço em branco na borda** (`validators.py:95`) — ampliação de contrato não prevista no plano.
  3. **Estreitamento do critério 7** — e este é o mais relevante. O plano diz, na especificação transcrita: "Caracteres de máscara removidos antes de validar: `.` `/` `-`", e o critério 7 diz "Máscara `.` `/` `-` é aceita e removida". A implementação passou a aceitar **só o leiaute exato** `XX.XXX.XXX/XXXX-XX` (correção do achado 6). É a decisão certa para digitação humana, mas é **mais restritiva do que a letra do plano**, e cria risco declarado para a DL-010: arquivo de terceiro que traga CNPJ com separação parcial (ex.: `11222333/0001-81`) será recusado na importação. Isso precisa estar escrito antes de alguém depender do contrário.
- **Correção recomendada:** atualizar o plano com estado, branch, commit, evidências e as três decisões acima; atualizar BL-46; e registrar em `docs/projeto/decisoes.md` a política de máscara estrita, com a consequência para entrada automatizada da DL-010.
- **Como verificar:** leitura do plano e do backlog; `scripts/validate-docs.ps1` limpo.

### R7 — BAIXA. A API deixou de agregar erros de campo quando o CNPJ é inválido

- **Requisito afetado:** critério 9 ("mensagem útil"); AGENTS.md §8.
- **Local:** `apps/empresas/serializers.py:22-25` — o `raise` acontece dentro de `_normalizar_cnpj_do_payload`, chamado **antes** de `super().to_internal_value()`, então a coleta de erros do DRF nunca roda.
- **Reprodução executada** (prova contrastiva, o mesmo endpoint):
  ```
  {"cnpj": "xx"}   → 400 {"cnpj":[...formato...]}
  {"cnpj": 12345}  → 400 {"razao_social":["Este campo é obrigatório."],"cnpj":[...formato...]}
  ```
  Os dois payloads têm os mesmos dois defeitos. O segundo devolve os dois erros porque `12345` não é `str` e escapa do `raise` antecipado. Prova que a perda de agregação é causada pelo novo código, e não é comportamento normal do DRF.
- **Impacto:** cliente de API (ou SPA futura) recebe os erros de cadastro um por vez; quem digita corrige, reenvia e descobre o próximo. Sem risco de dado.
- **Correção recomendada:** não levantar em `to_internal_value`. Ou normalizar sem validar ali (deixando o `ValidationError` para o validador de campo `validar_cnpj`, que já roda na fase certa), ou mover a normalização para `EmpresaSerializer.validate_cnpj`/um `CNPJSerializerField` com `to_internal_value` próprio — aí o erro entra no `ErrorDetail` do campo e é agregado com os demais.
- **Como verificar:** `POST {"cnpj": "xx"}` sem `razao_social` deve devolver as duas chaves no corpo.

### R8 — BAIXA. O comentário sobre o `.strip()` está incorreto

- **Requisito afetado:** AGENTS.md §9 ("Não deixar comentários desatualizados"; o comentário deve explicar qual condição preserva).
- **Local:** `apps/empresas/validators.py:92-94` — "Só espaço comum (`str.strip()` sem argumento); **não é tratamento de caractere invisível exótico**."
- **Reprodução executada:** `normalizar_cnpj("\xa011222333000181")` → `'11222333000181'`. `str.strip()` sem argumento remove toda a classe `str.isspace()`, o que inclui NBSP (`\xa0`), `\n`, `\t`, `\r`, `\v`, `\f`, `\u2000`–`\u200a`, `\u2028`, `\u2029`, `\u3000`. Confirmei também que `\u200b` (zero-width space, que **não** é whitespace) é corretamente recusado.
- **Impacto:** o comportamento real é mais permissivo do que o comentário afirma — e, na minha leitura, é o comportamento **desejável** (CNPJ colado de HTML costuma vir com NBSP). O defeito é o comentário dizer o contrário, num arquivo que é justamente a fonte única de canonização. Nenhum teste cobre NBSP, `\n` ou `\t`.
- **Correção recomendada:** corrigir o comentário para declarar que remove qualquer whitespace Unicode da borda (e que caractere de largura zero **não** é removido, sendo recusado), e acrescentar os casos ao `parametrize` de `test_cnpj_com_espaco_na_borda_nao_levanta_erro`: `"\xa011222333000181"`, `"11222333000181\n"`, `"\t11222333000181\t"`, mais um caso negativo `"11222333000181\u200b"` esperando `ValidationError`.
- **Como verificar:** os testes acima.

### R9 — BAIXA (qualidade de teste). Os novos testes dos achados 3 e 6 não isolam o mecanismo que afirmam testar — a mesma crítica do achado 7

- **Local:** `apps/empresas/tests/test_validators.py` — `test_cnpj_com_caractere_unicode_que_expande_no_upper_e_invalido` e `test_cnpj_com_mascara_mal_formada_e_invalido`.
- **Reprodução executada, mutantes sobreviventes:**
  - **M8**: `_REGEX_SEM_MASCARA = re.compile(r"^\w{14}$")` (aceita letra Unicode) → **67 passed, sobrevive**. O teste do achado 3 usa `"ß123CDE000117"`, de **13** caracteres, então é recusado por comprimento, não por conjunto de caracteres. Casos de 14 caracteres que distinguiriam: `"ıB123CDE000155"`, `"ſB123CDE000155"`, `"AB123CDE00015５"` — todos casam `\w{14}` e são corretamente recusados pelo código real.
  - **M10**: `_REGEX_MASCARA` com separadores livres (`^(..)[./-]?(...)[./-]?(...)[./-]?(....)[./-]?(..)$`) → **67 passed, sobrevive**. As duas strings do teste do achado 6 (`"../-11222333000181"` e `".1122.2330/00181-"`) são recusadas até pelo mutante. Casos que distinguiriam: `"11-122-233.0001/83"` e `"11/122/233-0001.83"` — separadores nas posições certas, tipos trocados; recusados pelo código real, aceitos pelo mutante.
  - M5, M7 e M9 (remoção das âncoras `^$`) também sobrevivem, mas são **mutantes equivalentes**: o código usa `fullmatch`, que já ancora. Não são achado; as âncoras são redundância inofensiva.
  - **M18**: trocar `isinstance(data.get("cnpj"), str)` por `data.get("cnpj") is not None` em `serializers.py:19` → sobrevive. O mutante muda comportamento real (`{"cnpj": 11222333000181}` passaria de 201 para 400), ou seja, **o contrato "CNPJ numérico enviado como número JSON é aceito" não está fixado por teste algum**. Decida qual é o desejado e teste-o.
- **Impacto:** nenhum no comportamento atual; os testes dão mais confiança do que sustentam, que é exatamente o problema que o achado 7 apontou.
- **Como verificar:** acrescentar os casos acima e reconfirmar que M8, M10 e M18 morrem.

### R10 — BAIXA. Mensagens de erro nos casos mais prováveis de escritório

Você pediu que eu olhasse o dia a dia. Testei as entradas que um contador realmente produz:

| Entrada | Resultado | Avaliação |
| --- | --- | --- |
| `11.122.233/0001-83` | aceito, grava `11122233000183` | bom |
| `ab.123.cde/0001-55` | aceito, grava `AB123CDE000155` | bom |
| ` 11.222.333/0001-81 ` (colado de planilha) | aceito | bom |
| DV errado | "CNPJ inválido: dígitos verificadores não conferem." | **ótimo** — diz o que está errado |
| letra no DV, com e sem máscara | "...12 alfanuméricos (A-Z, 0-9) seguidos de 2 dígitos verificadores numéricos." | **ótimo**, e o ajuste 2 de fato uniformizou as duas formas |
| caractere inválido (`#`) | "CNPJ deve ter 14 caracteres alfanuméricos (A-Z, 0-9), com ou sem a máscara XX.XXX.XXX/XXXX-XX." | aceitável — não aponta o caractere, mas ensina o formato |
| 13/15 caracteres | mesma mensagem acima | aceitável |
| máscara mal formada (`11-122-233.0001/83`) | mesma mensagem acima | aceitável |
| **33+ caracteres, na tela** | "Certifique-se de que o valor tenha no máximo **32** caracteres (ele possui 33)." | **ruim** — "32" não significa nada para quem digita CNPJ |
| **`""` ou `"   "`, pela API** | mensagem de formato | **inconsistente** — na tela dá "Este campo é obrigatório."; pela API a mensagem de obrigatoriedade/branco do DRF é substituída pela de formato |

- **Local:** `apps/empresas/forms.py:19`; `apps/empresas/serializers.py:19-25`.
- **Correção recomendada:** no formulário, passar `error_messages={"max_length": "CNPJ deve ter 14 caracteres, ou 18 com a máscara XX.XXX.XXX/XXXX-XX."}` (ou reduzir o `max_length` para 18–20, que é o máximo semanticamente possível, e ajustar a mensagem); no serializer, não normalizar string vazia/só-espaço, deixando o `required`/`allow_blank` do DRF responder.
- **Como verificar:** testes de mensagem para `""`, `"   "` e 33 caracteres, na tela e na API, comparando os textos.

### Observação fora do escopo da DL-011 (preexistente, confirmada)

`POST` **form-encoded ou multipart** na API de empresas cria a empresa com `ativo: false`, mesmo com `default=True` no modelo — é o tratamento de HTML-input do `BooleanField` do DRF. Reproduzi **também em `fd41aba`**, antes das correções da rodada 2, então **não é efeito desta etapa** e o `.copy()` do `QueryDict` não tem parte nisso (`QueryDict.copy()` devolve `QueryDict`, e `html.is_html_input` continua verdadeiro). Merece item próprio de backlog: empresa nasce inativa por caminho de requisição legítimo.

---

## 3. Situação de cada achado da rodada 1

| # | Rodada 1 | Situação | Base |
| --- | --- | --- | --- |
| 1 | ALTA — sem canonização; minúscula duplica | **Corrigido** nos caminhos de requisição (todos os que testei). Mecanismo residual em gravação em massa → **R1** | Testado: 11 caminhos de gravação, nenhuma duplicata; mutante M14 morre |
| 2 | ALTA — máscara não vale no fluxo real | **Corrigido parcialmente** — tela e API sim; **Django admin reproduz a falha com a mesma mensagem** → **R2** | Testado: view 200 + API 201; `modelform_factory` do admin recusa 18 caracteres |
| 3 | MÉDIA — `.upper()` muda comprimento | **Corrigido** | Testado: 5 casos Unicode recusados; mutante M2 morre. Teste fraco → R9 |
| 4 | MÉDIA — fronteira `resto < 2` não exercida | **Corrigido** | Testado: mutante `resto < 1` mata 3 testes; os 4 casos conferidos por implementação independente |
| 5 | BAIXA — `AttributeError` em tipo inválido | **Corrigido** | Testado: 6 tipos → `ValidationError`; mutante M3 morre |
| 6 | BAIXA — máscara em qualquer posição | **Corrigido** | Testado: 7 leiautes, só o exato aceito. Teste fraco → R9 |
| 7 | BAIXA — teste não isola mecanismo; teste vacuoso | **Corrigido** no que foi apontado; a **mesma falha se repetiu nos testes novos dos achados 3 e 6** → **R9** | Testado: mutantes M4 e M11 morrem; M8 e M10 sobrevivem |

---

## 4. Critérios de aceite

| # | Critério | Resultado | Classificação |
| --- | --- | --- | --- |
| 1 | Cinco CNPJs numéricos continuam válidos | Atende, 5/5, conferido por implementação independente | Testado |
| 2 | Alfanumérico com DV correto é aceito | Atende (unitário, tela, API, persistência) | Testado |
| 3 | Alfanumérico com DV errado é recusado | Atende | Testado |
| 4 | Letra nas posições 13-14 é recusada | Atende, e agora o **mecanismo** está isolado (M4 morre) | Testado |
| 5 | 13 ou 15 caracteres recusados | Atende, inclusive nos casos Unicode que a rodada 1 explorou | Testado |
| 6 | `00000000000000` recusado | Atende (M13 morre) | Testado |
| 7 | Máscara aceita e removida | **Atende com ressalva dupla**: só o leiaute exato (estreitamento não registrado, R6) e **não vale no admin** (R2) | Testado |
| 8 | Minúsculas normalizadas e validadas | Atende, e agora **persistidas** canonizadas | Testado |
| 9 | Caractere fora de `[A-Z0-9./-]` recusado com mensagem útil | Atende; mensagem genérica em alguns casos e ruim acima de 32 caracteres (R10) | Testado |
| 10 | Nenhum ponto do sistema descarta letras ao normalizar | Atende na literal — `normalizar_cnpj` é função única; `_mascara_cnpj` é só apresentação e trata letras; busca do admin é `icontains`. Ressalva: caminhos em massa **não canonizam** (R1) | Inspecionado + Testado |
| 11 | Modelo persiste alfanumérico sem truncar | Atende | Testado |
| 12 | Comentário cita NT 2025.001 e IN RFB 2.229 | Atende (`validators.py:5-9`) | Inspecionado |
| 13 | Sem regressão; `ruff`, `format --check`, `check`, `makemigrations --check` limpos | Atende: 225 passed, lint e formato limpos (120 arquivos), check 0 issues, sem migração pendente. **`scripts/validate-docs.ps1` não executado — `pwsh` ausente no ambiente** | Testado / **Bloqueado** no item da documentação |

Substituto do item bloqueado, como paliativo e **não** como equivalente: implementei manualmente as quatro regras que o script verifica (título `# `, UTF-8 válido, sem espaço no fim de linha, nova linha final, links relativos existentes) sobre **todos** os `.md` do repositório → **0 problemas**. Nenhum `.md` foi alterado pelos commits de código da rodada 2.

Não avaliei conformidade jurídica da NT 2025.001 nem da IN RFB 2.229 — isso é validação profissional do Fred. Não afirmo ausência de outros defeitos.

---

## 5. Integridade da árvore

`git status --short` ao final: **vazio**. `git diff --stat` e `git diff --cached --stat`: **vazios**. `HEAD` = `fe5387df9df01456a0bf647412ba06311aa66b59`, como recebido.

`git status --short --ignored` mostra apenas caches ignorados (`.pytest_cache/`, `.ruff_cache/`, `**/__pycache__/`), criados por uma execução de `pytest` na raiz do repositório para confirmar os 225 testes. **Nenhum arquivo versionado foi alterado, criado ou removido.**

Tudo o mais rodou fora do repositório, no scratchpad: cópia da versão auditada via `git archive fe5387d` (conferida como idêntica a `apps/` e `config/` da árvore por `diff -r`), cópia de `fd41aba` para a prova contrastiva do `ativo:false`, e 20 cópias descartáveis para mutação. Nenhum `ruff format` sem `--check`. Nenhum commit, nenhum push. Banco de teste `test_dataledger`, criado e destruído pelo pytest.

---

# APROVADO COM RESSALVAS

As sete falhas da rodada 1 foram atacadas de frente e o núcleo da etapa está sólido: o algoritmo resiste a verificação independente, a canonização fecha todos os caminhos de requisição que consegui achar, a máscara funciona de ponta a ponta na tela e na API, e 14 dos 20 mutantes que plantei morrem. Nenhum achado desta rodada é bloqueador ou de gravidade alta, e o isolamento entre escritórios não regrediu.

As ressalvas, explícitas e sem esconder nada:

1. **R2 — o achado 2 reapareceu no Django admin**, com a mensagem literal da rodada 1. É a ressalva mais importante e a única que expõe usuário real a recusa de entrada legítima hoje. Graduei média porque o admin é superfície de staff e existe tela dedicada; **se o Fred tratar o admin como cadastro de produção, é alta e o parecer correto passa a ser REPROVADO.** Essa decisão é dele, não minha.
2. **R3 — a extensão a `Estabelecimento` não pode ser declarada testada.** Funciona (verifiquei), mas o mutante sobrevive à suíte inteira. AGENTS.md §7 não está cumprido para essa parte da entrega.
3. **R1 — a canonização não está na camada que DE-008 recomenda**, e o comentário do código afirma cobertura que não tem. Latente hoje; armadilha para a DL-010.
4. **R4 — corrida na unicidade devolve 500.** O dado fica íntegro; o tratamento do erro não acompanhou a mudança.
5. **R6 — o plano e o backlog não foram atualizados,** e três decisões de engenharia da rodada 2 — inclusive um **estreitamento do critério 7** — não estão registradas em lugar algum. AGENTS.md §3 e §5 usam "DEVE" aqui; a etapa não deve ser declarada concluída antes disso.
6. **R5** é preexistente e não pesa contra a DL-011, mas é um vazamento entre escritórios que merece item próprio de backlog.
7. R7, R8, R9 e R10 são de baixa gravidade e podem ir na mesma passada de correção.

Encaminhar R1, R2, R3, R4, R7, R8, R9 e R10 ao `desenvolvedor-pleno`; R5 e R6 dependem de decisão sua e do Fred.
