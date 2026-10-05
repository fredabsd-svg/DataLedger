# Reconferência da auditoria — DL-062 (BL-604), 04/10/2026

**Auditor:** `auditor-qa` (independente, somente leitura) · **Ciclo:** §3.1 do AGENTS.md — uma
auditoria, uma correção, uma reconferência. **Esta é a última.**
**Objeto:** commit `589652c` sobre `c48e3eb`, branch `fix/dl-062-sinal-da-raiz-retificadora`.
**Árvore auditada:** `589652c` (commit criado **durante** esta reconferência, 13:07; a árvore
mudou sob a medição, como na auditoria anterior). Nenhum arquivo foi alterado por mim.

## Veredito da reconferência

**APROVADO** — os oito achados estão **FECHADOS** por medição, a reescrita do BL-516 é
**honesta** e o novo número do Balanço está **CORRETO**; nenhum defeito novo.

## Achados

| id | estado | evidência medida |
|---|---|---|
| A1 | **FECHADO** | `views_web.py:3617` (título) e `:3809` (ação), `_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA:3701`, `_ENUM_DO_CAMPO_DE_PENDENCIA:3723`. Renderizei a função de produção `_lista_de_pendencia_para_contexto` sobre o item real: título humano, linhas `Tipo cadastrado: Ativo; Natureza cadastrada: Credora; Natureza natural do tipo da conta: Devedora`, ação que **confirma** ("Nada precisa ser corrigido para emitir"). Os dois fallbacks (`views_web.py:3838`, `:3846`) **não disparam**; nenhum Decimal cru no corpo. |
| A2 | **FECHADO** | `services.py:3999` — `if linha["saldo_final"] != zero:` antes do `append`. `saldo` e `contribuicao_no_total` saíram do item (`services.py:4000-4007`); varredura em todo o repositório: **nenhum** outro consumidor (nem template, nem serviço). `test_raiz_retificadora_com_saldo_zero_nao_gera_aviso` verde. |
| A3 | **FECHADO** | `docs/auditorias/2026-10-04-dl-062-auditoria.md` existe (187 linhas, versionada em `589652c`). `pwsh ./scripts/validate-docs.ps1` → `Documentação válida: 220 arquivos Markdown verificados.` (exit 0). |
| A4 | **FECHADO** | `services.py:4396-4397` — "`_LISTAS_QUE_SO_AVISAM` (dois nomes — o segundo entrou na DL-062, BL-604)". Confere com as duas entradas medidas de `_LISTAS_QUE_SO_AVISAM`. |
| A5 | **FECHADO** | `views_web.py:3928` — `natureza_esperada = NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO[tipo_do_grupo]`; o ternário sumiu. Importado em `views_web.py:59`. |
| A6 | **FECHADO** | `test_dl034_balanco_patrimonial.py:903-910` compara `informativas == _LISTAS_INFORMATIVAS_DE_CONTRATO` (constante **tupla**, `:883`). **Contraprova medida:** a tupla rejeita REORDENAÇÃO e DUPLICATA; a guarda antiga `set(...) == set(...)` **aceitaria as duas** (retorna `True`). O teste passa (1 passed). |
| A7 | **FECHADO** | **Cinco** funções de teste novas (o commit diz "quatro" sob A7; medi cinco no total), em `test_dl062_sinal_da_raiz_retificadora.py`: `:333` seção impressa do PL, `:375` grande total, `:389` subtotal lido do mapa, `:410` raiz sem movimento, `:437` nome/ação. As duas primeiras montam o Balanço por `_montar_grupos_do_balanco`. Arquivo inteiro: **18 passed** (13 antes + 5). |
| A8 | **FECHADO** | `Test-Path .dsh-body.md` → `False`; `git ls-tree -r HEAD` → vazio; `git log --all -- .dsh-body.md` → vazio (nunca versionado). `validate-docs.ps1` limpo. |

## Julgamento do BL-516

**A reescrita é HONESTA, e o novo comportamento do Balanço está CORRETO.** Medi o cenário exato
da fixture (`test_dl034_tela_do_balanco.py:885`) chamando `apurar_saldos` e
`avaliar_emissao_do_balanco` direto — o teste de tela em si só a CI executa (em SQLite ele
falha com `sqlite3.OperationalError: near "SET": syntax error`, em
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`; limitação conhecida e declarada).

| medido | **antes** (correção desligada em memória) | **agora** (código de `589652c`) |
|---|---|---|
| `totais_por_tipo[ativo]` | **1.100,00** | **900,00** |
| `totais_por_classificacao[ativo_circulante]` | 900,00 | 900,00 |
| `residuo_por_tipo[ativo]` | **200,00** | **0** |
| `equacao["diferenca"]` | **200,00** (1.100 ≠ 0 + 900) | **0** (900 = 0 + 900) |
| `pode_emitir` / `residuo_pendente` | `False` / `{ativo: 200}` | `True` / `{}` |
| impresso | — | 1.000,00 **D** + 100,00 **C** → subtotal **900,00 D**; PL **900,00 C**; "Total do Ativo" **900,00**; "Total do Passivo + PL" **900,00** |

**O 200,00 era o defeito, exatamente como a mensagem do commit afirma.** "(-) PDD Raiz" é
retificadora na raiz do Ativo: o Balanço somava o crédito dela como acréscimo (1.100,00) e a
soma por classificação o subtraía (900,00). O resíduo aritmético era a única rede que pegava
a conta. Corrigido, o Ativo é 1.000 − 100 = **900,00**, a equação fecha com PL 900,00 e o
documento emite.

**Por que a reescrita não é afrouxamento.** O teste manteve **todas** as afirmações que o
BL-516 pedia — aviso visível, `<strong>Aviso:</strong>`, as duas raízes nomeadas
("Conta 1 — Clientes Raiz", "Conta 2 — (-) PDD Raiz"), "sem ancestral comum", e a varredura de
nome cru no corpo. Inverteu **apenas** as quatro afirmações do veto, e a inversão está
sustentada por número medido, não por conveniência. O teste **discrimina**: medido que com o
código antigo `pode_emitir=False`, a view não monta a tabela — logo
`assert "Total do Ativo" in conteudo` **reprovaria** no código antigo.

⚠️ **Uma ressalva de precisão (não de honestidade).** `assert "900,00" in conteudo` não
distingue o Ativo do PL, porque **nesta fixture os dois são 900,00** — a asserção passaria
mesmo se o Ativo saísse errado. A afirmação do docstring ("o Ativo correto é 1.000,00 −
100,00 = 900,00") é verdadeira e eu a medi; a asserção é apenas mais frouxa que ela. As
afirmações que carregam a regressão (`"Total do Ativo" in`, as três `not in` do veto) todas
discriminam. Não é defeito; registrei porque a próxima leitura pode tratar "900,00" como
prova do Ativo quando ele é prova do PL.

## Defeitos novos

**Nenhum.** Os dois pontos que o pedido mandou conferir, medidos:

- **O item da lista ficou com informação suficiente para o contador agir?** Sim. Campos
  restantes: `conta`, `nome`, `tipo`, `natureza`, `natureza_natural_do_tipo` — o contador lê
  "Conta 2 — (-) PDD Raiz / Tipo cadastrado: Ativo; Natureza cadastrada: Credora; Natureza
  natural do tipo da conta: Devedora", que é **exatamente** a informação para decidir se
  reorganiza o plano de contas, e a ação diz o que fazer e o que **não** precisa ser feito.
  Perder `saldo`/`contribuicao_no_total` não tira nada: o valor já está impresso na linha da
  conta e nenhum consumidor lia esses campos.
- **O `_subtotal_do_balanco` lendo o mapa mudou algo para quem já o chamava?** Não. Medi
  ternário antigo × mapa tipo a tipo: **concordam** em `ativo`, `passivo`,
  `patrimonio_liquido` e `receita`; **divergem só em `despesa`** (mapa `devedora`, ternário
  `credora`). Os tipos que a tela realmente entrega são medidos em `views_web.py:3979` (via
  `TIPO_DA_CLASSIFICACAO_PATRIMONIAL` → `ATIVO`/`PASSIVO`), `:4013` (`ATIVO`), `:4022` (`PL`),
  `:4027` (`ATIVO`) e `:4030` (`PASSIVO`) — **nunca Despesa**. Logo Ativo, Passivo e PL
  imprimem exatamente a mesma letra de antes. E o mapa cobre **os cinco** `TipoConta.values`
  (`types sem chave = []`), então não há `KeyError` possível; a troca troca um
  "cai silenciosamente em CREDORA" por um "reprova por `KeyError`" — o lado certo de errar.

**Observação de nível 3 (andaime — não é achado, não pede rodada).** O fragmento
`"natureza_natural_do_tipo:"` não entrou em `_FRAGMENTOS_CRUS_PROIBIDOS_NO_CORPO`
(`test_dl034_tela_do_balanco.py:740-752`), e `test_a_lista_nova_tem_nome_humano_e_acao_na_tela`
não exige o rótulo nem o enum. **Contraprova:** removendo as duas entradas em memória, o
contador leria `natureza_natural_do_tipo: devedora` — mas a guarda de tela **ainda pegaria**,
incidentalmente, pelo fragmento `"tipo:"` (que é substring de `..._do_tipo:`). Hoje está
correto e guardado; é dívida de guarda, não defeito.

**Nenhum achado original continua aberto. Não há o que reabrir com o Fred, e esta reconferência
não abre uma terceira rodada.**

## Verificações executadas

```
$ .\.venv\Scripts\python.exe -m ruff check .
All checks passed!                                              [exit 0]

$ .\.venv\Scripts\python.exe -m ruff format --check .
354 files already formatted                                     [exit 0]

$ .\.venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).                 [exit 0]

$ .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
No changes detected                                            [exit 0]

$ pwsh ./scripts/validate-docs.ps1
Documentação válida: 220 arquivos Markdown verificados.          [exit 0]

$ pytest apps/contabilidade/tests/test_dl062_sinal_da_raiz_retificadora.py -q
18 passed, 12 warnings in 2.09s

$ pytest "...test_dl034_balanco_patrimonial.py::test_bl515_a_tupla_de_veto_preserva_as_travas_revisadas" -q
1 passed in 1.26s                                             # A6

$ pytest apps/contabilidade/tests/test_dl062_... test_dl034_balanco_patrimonial.py \
         test_dl032_camada_de_saldos.py test_dl033_classificacao_patrimonial.py test_dl045_dre.py -q
5 failed, 160 passed in 18.37s
  # as 5: test_precisao_decimal_com_valores_que_quebram_float (flaky SQLite, já apontada
  # na auditoria), 2 de test_dl034_balanco_patrimonial e 2 de test_dl045_dre — as quatro
  # últimas morrem em `SET TRANSACTION ISOLATION LEVEL` (SQLite), verificado no traceback

$ pytest apps/contabilidade apps/core -q
77 failed, 2496 passed, 65 skipped, 4 subtests passed in 215.68s (0:03:35)

$ pytest apps/contabilidade/tests/test_dl034_tela_do_balanco.py -q
14 failed, 3 passed in 7.20s
  # limitação ambiental CONHECIDA e DECLARADA: sqlite3.OperationalError near "SET":
  # syntax error (SET TRANSACTION ISOLATION LEVEL REPEATABLE READ). Só a CI roda este arquivo.
```

**As 77 falhas são ambientais e pré-existentes** (SQLite sem `SET TRANSACTION ISOLATION LEVEL`,
concorrência com thread em SQLite, permissões/umask de `apps/core` no Windows, detector CSS da
DL-024). Nenhuma está em `test_dl062_*`; o único arquivo tocado pela correção que aparece na
lista é `test_dl034_balanco_patrimonial.py`, com 2 falhas de isolamento de transação. As
sondas foram feitas em `%TEMP%` (`dl062_reconf_sonda{,2,3,4}.py`), sem tocar no repositório.

## Fontes citadas

- `apps/contabilidade/views_web.py:3617`, `:3701`, `:3723`, `:3809` — A1 (as quatro entradas)
- `apps/contabilidade/views_web.py:3838`, `:3846` — os fallbacks que A1 acionava
- `apps/contabilidade/views_web.py:3928` — A5, leitura do mapa
- `apps/contabilidade/views_web.py:3979`, `:4013`, `:4022`, `:4027`, `:4030` — todos os
  chamadores de `_subtotal_do_balanco` (a lista de tipos alcançáveis)
- `apps/contabilidade/services.py:3999-4007` — A2 (filtro e item enxuto)
- `apps/contabilidade/services.py:4231-4242` — `residuo_por_tipo`, a origem dos 200,00
- `apps/contabilidade/services.py:4257` — `diferenca = ativo − (passivo + PL + resultado)`
- `apps/contabilidade/services.py:4396-4397` — A4, "(dois nomes …)"
- `apps/contabilidade/models.py:352-358` — `NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO` (5 chaves)
- `apps/contabilidade/tests/test_dl034_balanco_patrimonial.py:883`, `:903-910` — A6
- `apps/contabilidade/tests/test_dl034_tela_do_balanco.py:885-926` — a fixture do BL-516
- `apps/contabilidade/tests/test_dl034_tela_do_balanco.py:740-752`, `:755-758` — a guarda de
  nome cru e sua lista de fragmentos
- `apps/contabilidade/tests/test_dl062_sinal_da_raiz_retificadora.py:333`, `:375`, `:389`,
  `:410`, `:437` — os cinco testes novos (13 → 18 casos)
- `docs/auditorias/2026-10-04-dl-062-auditoria.md` — a auditoria reconferida (A1-A8)
- `AGENTS.md:3.1` — níveis de risco e a regra de parada (uma auditoria, uma correção, uma
  reconferência; a terceira rodada é proibida); `AGENTS.md:8` — a guarda derivada de lista
