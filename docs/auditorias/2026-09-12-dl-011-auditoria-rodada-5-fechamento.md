# Auditoria de fechamento DL-011 — CNPJ alfanumérico — rodada 5 — 2026-09-12

Parecer do `auditor-qa` sobre a **quinta e última rodada** da etapa
[DL-011](../planos/DL-011-cnpj-alfanumerico.md), que fecha o BL-46.

Rodadas anteriores:
[1 — reprovada](2026-09-12-dl-011-cnpj-alfanumerico.md) ·
[2 — aprovada com ressalvas](2026-09-12-dl-011-reauditoria-rodada-2.md) ·
[3 — aprovada com ressalvas](2026-09-12-dl-011-reauditoria-rodada-3.md) ·
[4 — aprovada com ressalvas](2026-09-12-dl-011-auditoria-rodada-4.md).

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**. O texto abaixo é o relatório do auditor, sem edição.

## Parecer

**APROVADO COM RESSALVAS.** O auditor declarou que a etapa **pode ser encerrada
e integrada à `main`**, condicionada à atualização da documentação e à
confirmação da integração contínua.

## Erro de leitura do `arquiteto-senior`, e é o achado mais instrutivo da etapa

O achado **C1** nasceu de uma medição **minha**, que eu reportei com confiança:

> *"Apontando os quatro `except` de volta ao tipo genérico, falham exatamente os
> dois testes do B1, nenhum a mais."*

Os números estavam corretos. **A leitura estava errada.**

> Quatro pontos revertidos, dois testes disparando, significa que **dois pontos
> não estão protegidos por nada**.

Era resultado para desconfiar, não para confirmar. O auditor mutou **um `except`
por vez** e provou: revertendo isoladamente o de criação de `Empresa`, ou o de
criação de `Estabelecimento`, a suíte fica **268 verde** enquanto o defeito
volta.

Regra de método que fica registrada para a equipe: **quando se muta N pontos e
morrem menos de N testes, a diferença não é redundância — é buraco.**

## A divergência sobre o B1 foi julgada

Na rodada 4 o auditor aprovou e declarou que nada impedia fechar. O
`arquiteto-senior` **discordou** e mandou corrigir o B1. Nesta rodada o auditor
avaliou a divergência e concluiu: **foi acerto**, e acrescentou uma terceira
razão que o `arquiteto-senior` não tinha — corrigir na raiz **trouxe cobertura
de brinde**, porque o `except` largo não era só defeito latente, era trecho
**intestável**: não havia nada de específico para prender.

## Decisão do `arquiteto-senior` sobre o C1

**C1 entra antes de fechar**, aplicando o mesmo critério que usei contra o
parecer da rodada 4: não se manda para o backlog a cobertura ausente da correção
que a própria rodada produziu. **C2, C5, C6 e C7** vão junto, por serem baratos
e nos mesmos arquivos.

---

## Nota de formatação, para não parecer edição

O relatório abaixo contém um bloco com os dois testes que o auditor propôs. A
marcação desse bloco foi trocada de ```` ```python ```` para ```` ```text ````,
e **só isso**.

Motivo: o `ruff` formata blocos de código Python **dentro de arquivos
Markdown**, e `ruff format --check .` roda na integração contínua. Manter a
marcação original faria a verificação reprovar — e a alternativa, deixar o
`ruff` reformatar, **alteraria o texto do auditor**, o que a regra de
preservação integral dos achados proíbe.

Nenhum caractere do conteúdo foi alterado. A mesma armadilha já derrubou a CI
uma vez, no plano da DL-008, e está registrada lá.

---

# Auditoria de fechamento — DL-011 (BL-46), rodada 5

Versão auditada: **`40c61c6`**, branch `claude/accounting-agent-team-setup-mn6lyf`, base do diff `7e92b18`. Medida contra os quatro relatórios anteriores, o `AGENTS.md`, o plano e DE-008/DE-013.

**Ambiente — Testado.** Venv isolada em `…/scratchpad/venv` (Python 3.14.0rc2 via `uv`, Django 6.1.1, DRF 3.18.1, pytest 9.1.1, ruff 0.16.7), PostgreSQL 16 local. Cópias `git archive` de `40c61c6` e de `7e92b18` fora do repositório, conferidas por `diff -r -q` contra `apps/` e `config/`. 13 mutantes em cópia descartável (removida). Três arquivos de sonda criados **na cópia** e removidos; cópia reconferida por `diff -r` depois. Banco `dataledger` usado só como destino do `test_…` do pytest-django, sem sobras. `DEBUG=True` (como a CI — com `DEBUG=False` o `SECURE_SSL_REDIRECT` redireciona tudo e 106 testes falham; é comportamento esperado, não achado). `pwsh` continua ausente.

---

## 1. Verificações favoráveis

**Suíte e ferramentas — Testado.** `pytest -q` → **268 passed** (eram 263). `ruff check .` → All checks passed. `ruff format --check .` → **126 files already formatted**. `manage.py check` → 0 issues. `makemigrations --check --dry-run` → No changes detected. **Confirmo todos os seus números.**

**Pergunta 1 — o B1 fechou na raiz, e a herança não quebra nada — Inspecionado + Testado.**

- `erro_de_cnpj_duplicado_como_400` tem **exatamente quatro** usos (`views.py:65, :89, :112, :226`), e **exatamente quatro** capturas (`:67, :91, :114, :228`). Não existe caminho em que `CNPJDuplicado` seja levantada e não capturada: ela só é construída em `services.py:112`.
- Entre o `raise` e o `except` não há frame do Django nem do DRF que capture `ValidationError`: só `contextlib._GeneratorContextManager.__exit__` (que reergue porque `exc is not value`), `Atomic.__exit__` (que faz rollback e reergue) e o `with` da própria view. `Serializer.save()`, `ModelSerializer.create/update` não capturam `ValidationError`.
- `full_clean()`, `form.is_valid()` e `serializer.is_valid()` **rodam fora do bloco** — nunca veem o tipo novo. E se um dia vissem, a conversão que fariam (erro do campo `cnpj`) é justamente a desejada: herdar de `ValidationError` é benigno aqui.
- Confirmado por execução: `CNPJDuplicado.__mro__` = `[CNPJDuplicado, ValidationError, Exception, …]`; um `except ValidationError` genérico a captura e `message_dict` funciona. E o gerenciador continua deixando passar intactos `DatabaseError`, `OperationalError`, `ValueError`, `RuntimeError` e `IntegrityError` sem `__cause__` (6/6 conferidos).
- Mutante **M3** (`class CNPJDuplicado(Exception)`) mata **7 testes**: a herança está presa, não é acidente.

**Pergunta 2 — os dois sintomas originais morreram, nos quatro caminhos — Testado.** Reproduzi os **cenários originais**, não os testes novos: sintoma 1 pelo caminho real do A5/BL-54 (`bulk_create` com `cnpj="ABC"`, depois `PATCH` só da `razao_social`) e sintoma 2 por **receptor de `pre_save`** (mecanismo diferente do `monkeypatch` dos testes novos).

| sonda | cenário | em `7e92b18` | em `40c61c6` |
| --- | --- | --- | --- |
| 1 | `PATCH` razão social em registro com `cnpj="ABC"` | 500, `AttributeError: 'ValidationError' object has no attribute 'error_dict'` **escondendo** a causa | 500 com a `ValidationError` **original** na cadeia |
| 2 | tela, `pre_save` levanta `ValidationError({"razao_social": [...]})` | **200**, sem um único erro no formulário, nada gravado | **500**, nada gravado |
| 3 | tela, `pre_save` levanta `ValidationError("texto")` | 500 com `AttributeError` | 500 com a original |
| 4 | `POST /api/empresas/`, idem | 500 com `AttributeError` | 500 com a original |
| 5 | `POST …/estabelecimentos/`, idem | 500 com `AttributeError` | 500 com a original |

**A falha virando sucesso aparente está morta.** O `AttributeError` que escondia a causa raiz no log está morto nos quatro caminhos.

**Pergunta 4 — o B2 fechou nos quatro caminhos — Testado.** A lógica de passagem mora só no gerenciador, e o gerenciador agora está preso diretamente: **M4** (`mensagem_se_cnpj_duplicado(exc) or "CNPJ ja existe."`, a armadilha da DL-007) e **M5** (`raise` → `return`, engolir em silêncio o `IntegrityError` alheio) morrem **cada um por 2 testes** — o de unidade com constraint real (`uma_matriz_por_empresa`) e o de requisição. E que **cada um dos quatro caminhos passa pelo gerenciador** está preso de forma independente: **M2** (`CNPJDuplicado` sem dict) e **M6** (mensagem trocada) matam testes espalhados pelos **quatro** caminhos (criação de Empresa, `PUT`/`PATCH`, criação de Estabelecimento e tela). **M8** (o N8) mata 5, contra 3 na rodada 4.

| mutante | falhas |
| --- | --- |
| M2 `CNPJDuplicado(mensagem)` sem dict | 7 |
| M3 `CNPJDuplicado(Exception)` | 7 |
| M4 armadilha da DL-007 no gerenciador | 2 |
| M5 gerenciador silencia `IntegrityError` alheio | 2 |
| M6 mensagem de duplicidade trocada | 5 |
| M7 tela deixa de adicionar o erro ao formulário | 1 |
| M8 `modelo = Empresa` para qualquer constraint (N8) | 5 |

**Pergunta 5 — nada das rodadas 1 a 4 voltou — Testado.** A1: corrida real de `PUT` em **6 de 6** execuções em `{200, 400}`, uma única linha `AB123CDE000155`; os dois testes versionados de corrida rodados 5 vezes seguidas, 6/6 estáveis, sem intermitência. A2: as cinco asserções de constraint passam. R2 (a que já reincidiu por caminho novo): admin **real** — `EmpresaAdmin.get_form()` devolve `CNPJFormField` com `max_length=None`, `"ab.123.cde/0001-55"` é válido e gravado `AB123CDE000155`; o *inline* idem. R4: fechado nos quatro caminhos. R7: `POST {"cnpj":"xx"}` devolve **as duas chaves**. R10: onze cargas (`1`, `1.5`, `True`, `null`, `[]`, `{}`, `""`, `"   "`, 40 caracteres, 14 × U+200B, 14 × `ç`) → 400 em todas, nenhuma "32 caracteres", nenhum 500.

**Pergunta 6 — isolamento entre escritórios — Testado.** Gestor de A contra empresa de B: `PATCH` → 404, `PUT` → 404, `GET` detalhe → 404, `GET` estabelecimentos → 404, `POST` estabelecimento → 404; CNPJ e razão social de B intactos depois. `PATCH` da própria empresa com `{"escritorio": <B>}` no corpo → 200 e a empresa **permanece em A**. R5 (oráculo de existência) inalterado e já coberto pelo **BL-48**.

**Documentação — Testado (equivalente manual, não o script).** `pwsh` ausente; reimplementei as cinco regras de `scripts/validate-docs.ps1` sobre os **41** `.md` → **0 problemas**. A execução oficial continua **Bloqueada** aqui; quem a faz é a CI.

**Integridade da árvore — Testado.** `git status --short` vazio; `git diff --stat` e `--cached` vazios; `git stash list` vazio; `HEAD` = `40c61c6950e86733dca9e440a67199b5c9eb0ada`, branch como recebida, e `origin/claude/accounting-agent-team-setup-mn6lyf` aponta para o mesmo commit. Nenhum banco `test%`/`aud%` sobrou. Nenhum `ruff format` sem `--check`, nenhum commit, nenhum push, nenhuma delegação.

---

## 2. Achados

### C1 — MÉDIA (qualidade de teste). A correção do B1 está presa em **2 dos 4** `except`: os dois caminhos de **criação** sobrevivem intactos ao mutante que os devolve ao tipo genérico

Esta é a sua pergunta 3, e é a quarta vez que a resposta é "havia algo".

1. **Gravidade:** média. Não é defeito hoje; é a cobertura da própria correção desta rodada.
2. **Requisito afetado:** AGENTS.md §7 ("Correção de defeito: teste de regressão que reproduza a falha"), §14. Nenhum critério de aceite do plano é violado.
3. **Local:** `/home/user/DataLedger/apps/empresas/views.py:67` (`EmpresaListCreateView.perform_create`) e `:114` (`EstabelecimentoListCreateView.perform_create`).
4. **Evidência — mutação cirúrgica, um `except` por vez, trocando só `CNPJDuplicado` por um alias do `ValidationError` genérico:**

   | mutante | falhas |
   | --- | --- |
   | **M1a — só `perform_create` de Empresa (`:67`)** | **0 — sobrevive, 268 passed** |
   | M1b — só `perform_update` (`:91`) | 1 |
   | **M1c — só `perform_create` de Estabelecimento (`:114`)** | **0 — sobrevive, 268 passed** |
   | M1d — só a tela (`:228`) | 1 |
   | M1 — os quatro juntos | 2 |

   E a regressão é **comportamental, não teórica**: com M1a+M1c aplicados, as sondas 4 e 5 voltam a dar `AttributeError: 'ValidationError' object has no attribute 'error_dict'` mascarando a causa raiz, com a suíte **inteiramente verde**.

   **Aqui está a releitura que eu te devo:** a sua medição ("apontando os quatro `except` de volta ao genérico, falham exatamente os dois testes do B1, nenhum a mais") está correta nos números — e é exatamente esse número que denuncia o problema. Quatro sítios revertidos, dois testes disparando: **dois sítios não estão protegidos por nada**. Era um resultado para desconfiar, não para confirmar.
5. **Impacto.** Metade da correção do B1 pode ser desfeita — por refatoração, por `git revert` parcial, por alguém "simplificando" o import — sem que um único teste acuse. O sintoma que volta é o pior dos dois para diagnóstico: o log passa a mostrar `AttributeError` no lugar da regra de negócio que realmente falhou.
6. **Correção recomendada.** Dois testes, espelhos exatos dos dois que já existem. Entrego como texto, para o `desenvolvedor-pleno` implementar:

   ```text
   # apps/empresas/tests/test_api.py — junto do bloco B1 existente

   def test_criar_empresa_via_api_com_validationerror_de_mensagem_simples_sobe_sem_attributeerror(
       client, gestor, monkeypatch
   ):
       def _save(self, *args, **kwargs):
           raise DjangoValidationError("erro de regra de negocio, sem error_dict")

       monkeypatch.setattr(Empresa, "save", _save)
       client.login(username="gestor", password="senha-forte-123")

       with pytest.raises(DjangoValidationError) as excinfo:
           client.post(
               reverse("empresas:api-lista"),
               data=json.dumps({"razao_social": "Empresa Nova Ltda", "cnpj": "11122233000183"}),
               content_type="application/json",
           )

       assert type(excinfo.value) is DjangoValidationError   # nunca CNPJDuplicado
       assert "erro de regra de negocio" in str(excinfo.value)


   def test_criar_estabelecimento_via_api_com_validationerror_de_mensagem_simples_sobe_sem_attributeerror(
       client, gestor, escritorio, monkeypatch
   ):
       empresa = Empresa.objects.create(
           escritorio=escritorio, razao_social="Empresa Base Ltda", cnpj="11122233000183"
       )

       def _save(self, *args, **kwargs):
           raise DjangoValidationError("erro de regra de negocio, sem error_dict")

       monkeypatch.setattr(Estabelecimento, "save", _save)
       client.login(username="gestor", password="senha-forte-123")

       with pytest.raises(DjangoValidationError) as excinfo:
           client.post(
               reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
               data=json.dumps({"tipo": "matriz", "nome": "Matriz", "cnpj": "44455566000183"}),
               content_type="application/json",
           )

       assert type(excinfo.value) is DjangoValidationError
       assert "erro de regra de negocio" in str(excinfo.value)
   ```
7. **Como verificar.** Replantar M1a e M1c **isoladamente** (só a linha 67; só a linha 114) e exigir que cada um mate ao menos um teste. Hoje matam zero.

### C2 — BAIXA. A docstring de `CNPJDuplicado` atribui o sintoma errado à forma errada da exceção — comentário que contradiz o teste que o acompanha

1. **Gravidade:** baixa (precisão de comentário; nenhum efeito em execução).
2. **Requisito afetado:** AGENTS.md §9 ("Não deixar comentários desatualizados"; o comentário deve explicar a condição que o código preserva).
3. **Local:** `/home/user/DataLedger/apps/empresas/services.py:36-43`.
4. **Evidência.** O texto diz, com um sujeito só para as duas orações: *"uma `ValidationError` de mensagem vinda de `save()` … virava `AttributeError` sem tratamento …, **e na tela virava 200 sem nenhum erro no formulário e nada gravado**"*. Medido em `7e92b18`: na tela, `ValidationError` **de mensagem** dava **500 com `AttributeError`** (sonda 3), não 200. O **200 silencioso** exigia `ValidationError` **de dict sem a chave `"cnpj"`** (sonda 2) — que é exatamente a forma que o teste versionado usa (`test_views.py:275-305`). Código e comentário discordam sobre qual forma produz qual sintoma.
5. **Impacto.** Quem for diagnosticar o próximo caso desses vai procurar o sintoma errado. É o comentário que serve de memória da decisão; ele precisa estar certo mais do que precisa estar longo.
6. **Correção recomendada.** Separar as duas orações: *"… de mensagem virava `AttributeError` (500 escondendo a causa raiz); e uma `ValidationError` de **dict sem a chave `cnpj`** virava, na tela, 200 sem nenhum erro no formulário e nada gravado."* De passagem: a docstring de `CNPJDuplicado` (22 linhas) e a de `erro_de_cnpj_duplicado_como_400` repetem a mesma explicação do B1; uma delas pode apontar para a outra.
7. **Como verificar.** Leitura, contra as duas sondas acima.

### C3 — BAIXA (documentação). `docs/agents/estado.md` está gravemente desatualizado no exato momento de fechar a etapa

1. **Gravidade:** baixa em risco técnico; relevante porque é **o documento de retomada de contexto**.
2. **Requisito afetado:** AGENTS.md §5.4 e §14 ("Documentação e evidências atualizadas"); e a instrução do próprio arquivo: *"Mantenha-o atualizado a cada etapa"*.
3. **Local:** `/home/user/DataLedger/docs/agents/estado.md` — cabeçalho ("revisão `d5dddb6`", 19 commits atrás), tabela de produto ("DL-011 — **Reprovado na rodada 1**; correções em curso"), "Próximo passo: **DL-011, rodada 2**", "O trabalho da DL-011 está **na árvore, sem commit**".
4. **Evidência.** Leitura em `40c61c6`; `git log` mostra `d5dddb6` como o 18.º commit anterior.
5. **Impacto.** Outra sessão que retome pelo caminho documentado no `CLAUDE.md` vai começar a rodada 2 de uma etapa que está na rodada 5.
6. **Correção recomendada.** Atualizar revisão, a linha da DL-011 (cinco rodadas, parecer final), o próximo passo (DL-010) e a seção "Estado do repositório".
7. **Como verificar.** Leitura; validação de documentação limpa.

### C4 — BAIXA (documentação). O **B5** continua aberto, e agora com duas rodadas de atraso

1. **Local:** `/home/user/DataLedger/docs/planos/DL-011-cnpj-alfanumerico.md:6` (*"rodada 4 em correção (A1, A2 da auditoria da rodada 3)"*) e `:12-15` (commit `6ae84e5`, base `6e6e088`, "251 testes", "123 arquivos"); `/home/user/DataLedger/docs/projeto/backlog.md:38` (BL-46, *"rodada 3 em correção"*).
2. **Evidência.** `git diff 7e92b18..40c61c6` não toca `docs/`.
3. **Impacto.** O plano aponta para a rodada 3 quando a etapa está fechando na 5. Sem efeito em código; com efeito em rastreabilidade (§3).
4. **Correção recomendada.** Fechar com: estado `integrada`, commit `40c61c6`, base `7e92b18`, "268 testes; `ruff`/`format --check` (126 arquivos)/`check`/`makemigrations --check` limpos", links das **cinco** auditorias, a lista do que foi corrigido em cada rodada (incluindo A3, B1 e B2), e o BL-46 no backlog.
5. **Como verificar.** Leitura; validação de documentação.

### C5 — BAIXA. Comentário conta cinco testes como quatro

- **Local:** `/home/user/DataLedger/apps/empresas/tests/test_canonizacao_constraint.py:9` — *"Os quatro casos abaixo são os que ele especificou"*. O arquivo tem **cinco** testes. Introduzido na rodada 4. Correção: trocar para "cinco", ou tirar o número.

### C6 — BAIXA (qualidade de teste). Os dois testes do B1 não discriminam o **tipo exato** da exceção, e um deles tem uma asserção tautológica

- **Local:** `/home/user/DataLedger/apps/empresas/tests/test_api.py:421-449` e `/home/user/DataLedger/apps/empresas/tests/test_views.py:276-305`.
- **Evidência.** `pytest.raises(DjangoValidationError)` é satisfeito por `CNPJDuplicado`, que é subclasse. Uma regressão futura que **envelopasse** a `ValidationError` genérica em `CNPJDuplicado` preservando a mensagem passaria nos dois testes — e reintroduziria o defeito em outra forma (erro de outra regra reportado como erro do campo `cnpj`). Correção: `assert type(excinfo.value) is DjangoValidationError` (ou `not isinstance(..., CNPJDuplicado)`).
- Em `test_views.py:305`, `assert not Empresa.objects.filter(...).exists()` é vacuoso: `Empresa.save` está monkeypatchado para levantar, então nada poderia ter sido gravado. Inofensivo, mas dá impressão de cobrir persistência sem cobrir.

### C7 — BAIXA (cobertura). Não há teste versionado de isolamento no caminho de **escrita**

- **Local:** `/home/user/DataLedger/apps/empresas/tests/test_isolamento.py:77` cobre `GET` do detalhe. Não há teste de `PUT`/`PATCH` de empresa de outro escritório, nem de `POST` de estabelecimento em empresa de outro escritório — e o `perform_update` é criação desta etapa.
- **Mitigação real:** o 404 vem do `EmpresaQuerySetMixin.get_queryset` compartilhado com o `GET`, que **está** preso; e eu verifiquei 404 em 5 de 5 rotas. Por isso é baixa, não média. Recomendação: acrescentar os dois casos ao `test_isolamento.py`.

### Observações que **não** são achados, mas precisam ficar ditas

- **O 500 do sintoma 1 do B1 continua existindo.** O que a correção fez foi trocar `AttributeError` opaco pela `ValidationError` original legível. Isso é exatamente o que o meu "Como verificar" do B1 pedia — mas ninguém deve ler "B1 corrigido" como "o `PATCH` em registro com CNPJ herdado não estoura". Quem apaga esse 500 é o **BL-54**, e a nota do backlog na linha 129 continua correta.
- **Mudança de contrato observada, defensável.** `POST /api/empresas/` com uma `ValidationError` de **dict** vinda de `save()` referindo outro campo devolvia **400 com aquele erro de campo** antes; agora devolve **500**. O 400 anterior era coincidência do `except` largo, não contrato; o 500 é a falha honesta. Registro para não virar surpresa.
- **CI do commit `40c61c6`: Não testado.** `gh` não existe neste ambiente e eu não tenho como consultar o resultado das verificações obrigatórias. `40c61c6` **está** no remoto.

---

## 3. Critérios de aceite

| # | Critério | Resultado | Classificação |
| --- | --- | --- | --- |
| 1 | Cinco CNPJs numéricos continuam válidos | Atende | Testado |
| 2 | Alfanumérico com DV correto é aceito | Atende (tela, API, admin, *inline*, `PUT`/`PATCH`, persistência) | Testado |
| 3 | DV errado é recusado | Atende | Testado |
| 4 | Letra nas posições 13-14 recusada | Atende | Testado |
| 5 | 13 ou 15 caracteres recusados | Atende | Testado |
| 6 | `00000000000000` recusado | Atende no validador. **Ressalva inalterada:** passa pela `CheckConstraint` em `bulk_create` (A5/BL-54) | Testado |
| 7 | Máscara aceita e removida | Atende; estreitamento em DE-013 | Testado |
| 8 | Minúsculas normalizadas e persistidas canônicas | Atende em todos os caminhos | Testado |
| 9 | Caractere fora de `[A-Z0-9./-]` recusado com mensagem útil | Atende; 11 cargas, nenhum 500 | Testado |
| 10 | Nenhum ponto descarta letras ao normalizar | Atende | Inspecionado + Testado |
| 11 | Modelo persiste alfanumérico sem truncar | Atende. **Ressalva inalterada:** A5/BL-54 | Testado |
| 12 | Comentário cita NT 2025.001 e IN RFB 2.229 | Atende (`validators.py:5-9`). **Ressalva nova:** o comentário de `services.py:36-43` tem um erro de fato — **C2** | Inspecionado + Testado |
| 13 | Sem regressão; ferramentas limpas | Atende: 268 passed; `ruff`/`format --check` (126)/`check`/`makemigrations --check` limpos. **`scripts/validate-docs.ps1` não executado — `pwsh` ausente** | Testado / **Bloqueado** no item da documentação |

Paliativo do item bloqueado, **não equivalente**: reimplementação das cinco regras sobre os 41 `.md` → 0 problemas.

Não avaliei conformidade jurídica da NT 2025.001 nem da IN RFB 2.229 — validação profissional do Fred. Não afirmo ausência de outros defeitos, segurança absoluta nem conformidade garantida.

---

## 4. Sua divergência sobre o B1: foi **acerto**, e eu errei

Você estava certo, e a minha recomendação da rodada 4 (mandar o B1 para o BL-54) era a mais fraca das duas. Pelas suas duas razões, e por uma terceira que só apareceu agora:

1. **A razão 1 se provou empiricamente nesta rodada.** "Dívida que ninguém volta para pagar" não é retórica: a própria correção do B1 saiu com **metade dos sítios sem teste** (C1), e ela é o item mais quente da etapa, feito na rodada em que todos estavam olhando para ele. Se o item quente sai pela metade, o item mandado para o backlog sai por zero.
2. **A razão 2 se sustenta contra o fato medido.** O 200 silencioso não era hipótese: reproduzi-o em `7e92b18` — formulário devolvido sem um único erro, nada gravado. Em software contábil isso é o operador acreditando que registrou. O §8 nomeia.
3. **A terceira razão, que eu não tinha.** Corrigir na raiz **trouxe cobertura de brinde**: o tipo próprio permitiu mutantes que antes não existiam (M2 e M3, 7 mortes cada). O `except` largo não era só um defeito latente — era um trecho *intestável*, porque não havia nada de específico para prender. Estreitar o contrato virou teste. Isso não estava na minha conta de custo-benefício, e devia estar.

**O custo foi proporcional?** Foi: 41 linhas em `services.py`, 15 em `views.py`, 5 testes, uma rodada. E o B2 junto foi a decisão certa — ele fechou limpo, mata M4 e M5 por dois testes cada.

**O que eu te devo em honestidade, e não é ressalva à sua decisão:** a correção **não elimina o 500** do sintoma 1, só o torna legível; e a rodada entregou a correção sem a metade da cobertura. Sua estimativa "uma classe e quatro linhas" estava certa sobre o código e otimista sobre o teste que ele exigia — que é, aliás, o mesmo padrão que apareceu no A3, no B2 e agora no C1: a guarda é escrita nos N lugares e presa em alguns.

Você não exagerou. Registre a divergência como resolvida a seu favor.

---

## 5. Parecer de fechamento

# APROVADO COM RESSALVAS

**A DL-011 pode ser encerrada e integrada à `main`** — com todas as letras, e com duas condições que são checklist do `AGENTS.md`, não preferência minha:

**Falta, antes de declarar a etapa concluída (AGENTS.md §5.4, §14):**

1. **Atualizar a documentação** — o plano e o BL-46 (**C4**, o antigo B5) e o `estado.md` (**C3**). Enquanto o plano disser "rodada 4 em correção" com o commit da rodada 3, a etapa não cumpre o §3. É trabalho seu, e você já o faz ao registrar esta auditoria.
2. **Confirmar a CI verde no commit `40c61c6`** (§5.8). Não tive como verificar — `gh` não existe aqui. Não é ressalva contra o código; é verificação obrigatória que eu deixo explicitamente **pendente**, não presumida.

**Minha recomendação, que não é condição de merge mas eu faria antes dele:** fechar o **C1**. São os dois testes que entreguei prontos acima, ~25 linhas, espelhos de testes que já existem no mesmo arquivo. Aplicando o seu próprio critério da rodada 4 — "não mandar para o backlog o que a própria rodada criou" —, o C1 qualifica: é a cobertura ausente da correção desta rodada. Se você preferir mandá-lo ao backlog, a decisão é defensável (não há defeito hoje), mas então registre-a como decisão, e não como esquecimento.

**Vai para o backlog, para não parecer esquecido:**

| item | onde | quem |
| --- | --- | --- |
| **BL-54** — fortalecer a restrição para `^[A-Z0-9]{12}[0-9]{2}$`. **Antes de a DL-010 importar em lote**, e é ela que apaga o 500 remanescente do B1 | já existe, com a nota dos dois motivos | `desenvolvedor-pleno` |
| **BL-55** — prender a camada do serializer sozinha (N6, N12) | já existe | `desenvolvedor-pleno` |
| **BL-56** — dica de digitação no campo de CNPJ | já existe | `especialista-frontend` |
| **BL-57** — alteração de CNPJ por `PUT`/`PATCH` sem trilha de auditoria (B3) | já existe | `desenvolvedor-pleno` |
| **BL-58** — Django admin grava CNPJ sem o gerenciador (B4) | já existe | `desenvolvedor-pleno` |
| **BL-48** — escopo da unicidade de CNPJ / oráculo de existência (R5), agora também por `PUT`/`PATCH` | já existe, bloqueada em PE-21 | Fred decide |
| **C1** — dois testes que prendem o `except` estreito nos caminhos de criação | **novo** | `desenvolvedor-pleno` |
| **C2, C5** — dois comentários com erro de fato | **novo** | `desenvolvedor-pleno` |
| **C6** — discriminar o tipo exato nos dois testes do B1; tirar a asserção vacuosa | **novo** | `desenvolvedor-pleno` |
| **C7** — isolamento no caminho de escrita em `test_isolamento.py` | **novo** | `desenvolvedor-pleno` |
| **C3, C4** — plano, BL-46 e `estado.md` | **novo/B5** | `arquiteto-senior` |

Arquivos que importam para quem for corrigir: `/home/user/DataLedger/apps/empresas/views.py` (C1: linhas 67 e 114), `/home/user/DataLedger/apps/empresas/services.py` (C2: linhas 36-43), `/home/user/DataLedger/apps/empresas/tests/test_api.py` (C1, C6), `/home/user/DataLedger/apps/empresas/tests/test_views.py` (C6), `/home/user/DataLedger/apps/empresas/tests/test_canonizacao_constraint.py` (C5), `/home/user/DataLedger/apps/empresas/tests/test_isolamento.py` (C7), `/home/user/DataLedger/docs/planos/DL-011-cnpj-alfanumerico.md` e `/home/user/DataLedger/docs/agents/estado.md` (C3, C4).

Auditoria de software não substitui validação profissional das regras contábeis e legais.
