# Auditoria DL-011 — CNPJ alfanumérico — 2026-09-12

Parecer do `auditor-qa` sobre a **primeira rodada** da etapa
[DL-011](../planos/DL-011-cnpj-alfanumerico.md), que fecha o BL-46.

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**. O texto abaixo é o relatório do auditor, sem edição.

## Parecer

**REPROVADO.** Sete achados, dois de gravidade alta. O algoritmo do dígito
verificador passou com folga; o que falhou foi o que está **em volta** dele —
canonização antes de gravar, remoção de máscara no fluxo real da tela e da API,
e conjunto de caracteres aceito.

O achado 1 é **regressão introduzida por esta etapa** e passou também pela
revisão do `arquiteto-senior`.

---

## Auditoria DL-011 — CNPJ alfanumérico (BL-46)

### Verificação do algoritmo (favorável)

Comparei linha a linha com a especificação transcrita no plano: pesos `[6,5,4,3,2,9,8,7,6,5,4,3,2]`; DV1 usa `_PESOS[1:]` (= `pesos[i+1]`); DV2 usa `base + dv1` contra `_PESOS` completo, o que equivale a `Σ c[i]·pesos[i] + dv1·pesos[12]`; valor base `ord(c) - 48`; regra `resto < 2 → "0"` nos dois dígitos. **Confere.**

Testei com implementações independentes que escrevi por fora: **200.000** CNPJs numéricos válidos gerados pelo algoritmo clássico — **zero recusados**; 100.000 com DV errado — **zero aceitos**; 100.000 alfanuméricos NT válidos — zero recusados, e 100.000 com DV errado — zero aceitos. Nenhuma das 36 sequências de caractere repetido é aceita. Letras `I/O/U/Q/F` continuam aceitas, como o plano determina. Suíte completa: **200 passed**; `ruff check`, `ruff format --check`, `manage.py check` e `makemigrations --check` limpos.

### Achados

**1 — ALTA. CNPJ não é canonizado antes de persistir; minúscula cria duplicata silenciosa.**
Requisito: critério 8 e 10; BL-46 ("aceito e **persistido**"). Local: `/home/user/DataLedger/apps/empresas/validators.py:39-48` (normaliza só para validar, descarta o resultado) e `/home/user/DataLedger/apps/empresas/models.py:53,109`.
Reprodução (executada, banco real): `Empresa(cnpj="ab123cde000155").full_clean()` passa e grava `'ab123cde000155'`; em seguida `Empresa(cnpj="AB123CDE000155")` também passa → **2 registros para o mesmo CNPJ** (`unique=True` é sensível a caixa no PostgreSQL). `filter(cnpj="AB123CDE000155")` devolve 0 para o registro minúsculo, e a tela exibe `ab.123.cde/0001-55`.
Impacto: duplicidade cadastral silenciosa, busca/conciliação por CNPJ falhando, e valor não canônico que quebrará a chave de acesso da DL-010. Regressão **introduzida por esta etapa** (antes, letras eram recusadas).
Correção: normalizar na fronteira de gravação (`clean`/`save` do modelo ou `clean_cnpj`/`to_internal_value`), gravando sempre sem máscara e em maiúsculas.
Verificar: criar via form e via API com minúscula e conferir `Empresa.objects.get(cnpj="AB123CDE000155")`; tentar a duplicata e esperar `IntegrityError`/erro de unicidade.

**2 — ALTA. Critério 7 (máscara) não vale no fluxo real.**
Local: `apps/empresas/forms.py:6-9`, `apps/empresas/serializers.py:32-37`, `models.py:53`.
Reprodução: `EmpresaForm(data={"cnpj": "AB.123.CDE/0001-55", ...}).is_valid()` → **False**, erro `"Certifique-se de que o valor tenha no máximo 14 caracteres (ele possui 18)"`. A máscara só é removida dentro de `validar_cnpj`, depois do `MaxLengthValidator`.
Impacto: o usuário que digita CNPJ mascarado (uso normal) é bloqueado; o critério declarado está provado apenas por teste unitário da função isolada, que dá falsa confiança.
Correção: remover máscara antes da validação de campo (mesma normalização do achado 1).
Verificar: teste de view/API POST com `AB.123.CDE/0001-55` resultando em `201`/redirect e valor gravado `AB123CDE000155`.

**3 — MÉDIA. `.upper()` altera o comprimento e admite caractere fora de `[A-Z0-9./-]`.**
Local: `validators.py:48`.
Reprodução: `validar_cnpj("ß123CDE000117")` — **13 caracteres**, com `ß` — é **ACEITO**, porque `"ß".upper() == "SS"`. Viola os critérios 5 e 9 simultaneamente; o valor gravado seria a string original de 13 caracteres.
Correção: validar o conjunto de caracteres antes de `.upper()`, ou usar tradução A-Z restrita a ASCII.
Verificar: `validar_cnpj("ß123CDE000117")` deve levantar `ValidationError`.

**4 — MÉDIA. Teste de mutação sobrevivente: o limite `resto < 2` não é exercido.**
Alterando `return "0" if resto < 2` para `resto < 1` (cópia isolada em scratchpad), **os 42 testes de `apps/empresas` continuam passando**, embora a mutação recuse CNPJs válidos. Nenhum caso de teste tem `soma % 11 ∈ {0,1}`.
Casos de teste propostos (calculados e confirmados como aceitos hoje): `72981506162202` (resto 1 no DV1), `11070434192580` (resto 1 no DV2), `24365234257800` (resto 0 nos dois), `CR6G1EWE2BK600` (alfanumérico, resto 1 nos dois).

**5 — BAIXA.** `validar_cnpj(None)` e `validar_cnpj(11222333000181)` levantam `AttributeError`, não `ValidationError` (`validators.py:70`). Converter/`raise ValidationError`.

**6 — BAIXA.** Máscara aceita em qualquer posição: `"../-11222333000181"` e `"11222333000181."` são aceitos. A NT define as posições da máscara; a remoção cega é permissiva.

**7 — BAIXA (qualidade de teste).** Mutação `[A-Z0-9]{12}[0-9]{2}` → `[A-Z0-9]{14}` também sobrevive: a restrição numérica do DV é redundante (o DV calculado é sempre numérico), então o teste do critério 4 não isola o mecanismo que afirma testar. Além disso, `test_cnpj_numerico_em_minusculas_nao_levanta_erro` é vacuoso (`"11.122.233/0001-83".lower()` é idêntico à origem).

### Critérios

| # | Resultado |
| --- | --- |
| 1 | Atende (testado, 5/5) |
| 2 | Atende |
| 3 | Atende (100 mil casos) |
| 4 | Atende no comportamento; mecanismo não provado (achado 7) |
| 5 | **Não atende** — achado 3 |
| 6 | Atende |
| 7 | **Não atende no fluxo real** — achado 2 |
| 8 | **Não atende** — normaliza só para validar (achado 1) |
| 9 | **Não atende** — achado 3 |
| 10 | Atende na literal: varredura de `apps/`, `templates/`, `config/` e migrações não achou terceiro ponto que descarte letras; a lacuna é falta de canonização (achado 1) |
| 11 | Atende (testado com banco) |
| 12 | Atende (`validators.py:5-7`) |
| 13 | Atende (200 passed; lint, format, check e makemigrations limpos) |

Não foi avaliada a conformidade jurídica da NT; isso exige validação profissional. Não afirmo ausência de outros defeitos.

### Integridade da árvore

`git status --short` e `git diff --stat` ao final: os mesmos 4 arquivos modificados do início, sem arquivos novos. Mutações e testes rodaram em cópia isolada no scratchpad e em banco de teste próprio; nada do repositório foi alterado.

## REPROVADO
