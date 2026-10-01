# Auditoria DL-060 — reconferência

**Demanda:** DL-060, a reabertura em cascata confirma exatamente os meses mostrados. Ela fecha os achados H1 e H2 da [auditoria da DL-054](2026-10-01-dl-054-rodada-1.md).
**Nível de risco:** 1, conforme a §3.1 do [AGENTS.md](../../AGENTS.md).
**Auditor:** `auditor-qa`. Esta é a reconferência única, e o parecer decide (não há terceira rodada).
**Relatório anterior:** [rodada 1](2026-10-01-dl-060-rodada-1.md), achados L1 a L5.
**Data:** 2026-10-01.

## 1. Versão e método

- **Versão auditada:** commit `2734b74`, HEAD da worktree `/home/user/DataLedger/.claude/worktrees/agent-a0d7b4f451cc80155`.
  - Conferido com `git rev-parse --short HEAD`, que devolveu `2734b74`.
- **Diff da correção (`444b28a..2734b74`):** 3 arquivos, 222 inserções e 30 remoções.

  | Arquivo | Mudança |
  | --- | --- |
  | `apps/livro_caixa/views_web.py` | +11 e -3 (faixa de anos do campo oculto) |
  | `apps/livro_caixa/tests/test_dl054_encadeamento.py` | +92 e -30 (teste P2 novo, teste antigo renomeado) |
  | `apps/livro_caixa/tests/test_dl060_confirmacao_da_cascata.py` | +149 (P1, casos de L3 e de L4) |

- **`services.py` não mudou:** `git diff --stat 444b28a..2734b74 -- apps/livro_caixa/services.py` saiu vazio. Na cópia, `diff` contra `git show 2734b74:apps/livro_caixa/services.py` confirmou o arquivo idêntico antes da suíte.
- **Método:**
  - `git archive 2734b74` extraído em cópia descartável (`scratchpad/rec060`), com `git init` e commit próprio.
  - Banco PostgreSQL local, com o nome do banco da `DATABASE_URL` sufixado `_rec060`.
  - As mutações foram aplicadas por mim nessa cópia e revertidas. Depois de cada uma, `git status --porcelain` da cópia voltou vazio.
- **Não houve delegação.**

## 2. Comandos e saídas reais

Todos rodaram na cópia `rec060`.

| Comando | Saída real |
| --- | --- |
| `pytest` nos 3 arquivos da cascata (`test_dl054_encadeamento`, `test_dl054_tela_cascata`, `test_dl060_confirmacao_da_cascata`) | `216 passed in 37.12s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `345 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` (com o mesmo aviso inofensivo de histórico, pois o banco `_rec060` não existe fora do pytest) |
| `python -m pytest -q -p no:cacheprovider` (suíte completa) | `1 failed, 4269 passed, 50 skipped, 2 warnings, 4 subtests passed in 363.93s (0:06:03)` |

- A linha declarada (4269 aprovados, 50 pulados, 1 falha) **foi reproduzida exatamente**.
- **A única falha** é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`.
  - Causa: o ambiente roda Python 3.13.12 e o teste faz `ast.parse(..., feature_version=(3, 14))`.
  - É a falha conhecida e preexistente. Não decorre da DL-060.
- Os 2 avisos são `RemovedInDjango70Warning: savepoint() is deprecated`, em `apps/contabilidade/tests/test_dl016_f6_check_empresa_not_null.py:101` e `:139`. São preexistentes.

**Efeitos colaterais:**
- `git -C /home/user/DataLedger status --porcelain` ficou com 0 linhas, e `git diff --stat` também.
- A worktree `agent-a0d7b4f451cc80155` ficou limpa, em `2734b74`.

## 3. Tabela dos achados anteriores

| Achado | Veredito | Evidência |
| --- | --- | --- |
| L1 (média) | **Fechado** | Os dois testes P1 existem e reprovam sob M1, aplicada por mim. Detalhe na seção 4.1. |
| L2 (baixa) | **Fechado** | P2 existe com a âncora `_esperar(cascata_b)`, reprova sob M3b e passa sem mutação. O teste antigo foi renomeado e não promete mais do que afirma. Seção 4.2. |
| L3 (baixa) | **Fechado** | `0000-01`, `9999-12`, `1969-12` e `3000-01` dão 400 sem efeito. A faixa vem de `_ANO_MINIMO` e `_ANO_MAXIMO` da API. Seção 4.3. |
| L4 (baixa) | **Fechado**, com a observação M1 abaixo | Os casos novos estão presentes e verdes. Seção 4.4. |
| L5 (baixa, processo) | **Pendente do arquiteto** | Permanece. Seção 4.5. |

## 4. Verificação item a item

### 4.1 L1 — comparação sob lock guardada por teste

**Testes presentes** em `apps/livro_caixa/tests/test_dl060_confirmacao_da_cascata.py`:
- `test_encerramento_de_abril_em_andamento_faz_a_cascata_esperar_e_depois_divergir`
- `test_reabertura_de_marco_em_andamento_faz_a_cascata_esperar_e_depois_divergir_a_menos`

Ambos usam duas conexões reais (`transaction=True`). A operação concorrente segura o lock numa pausa, a cascata chega durante a pausa e a asserção `cascata.is_alive()` exige que ela espere. Só depois de liberada a cascata lê o estado comitado, diverge e não altera nada.

**M1 aplicada por mim** na cópia:
- Movi a leitura e a comparação dos encerrados posteriores para **antes** de `_travar_meses_do_ano_para_reabertura`. A leitura saiu sem lock e a comparação sob lock foi desativada, com `if False:`.
- Rodei os 3 arquivos da cascata (216 testes).
- Resultado: `3 failed, 213 passed`. As 3 reprovações:
  - `test_duas_cascatas_com_fevereiro_pausado_terminam_em_estado_unico` (o P2)
  - `test_encerramento_de_abril_em_andamento_faz_a_cascata_esperar_e_depois_divergir`
  - `test_reabertura_de_marco_em_andamento_faz_a_cascata_esperar_e_depois_divergir_a_menos`
- Na rodada 1, a mesma mutação passava em todos os 199 testes do repositório. Agora a suíte a acusa.
- A saída de uma das falhas mostra o dano do H1 pela janela de corrida: a cascata retornou `{'valor': [01/2026 (Aberto), 02/2026 (Aberto)]}` em vez do erro `ReaberturaExigeCascata`.

**Sem mutação (repetidas):** os três testes novos de concorrência (os dois P1 e o P2) passaram em 5 de 5 repetições isoladas (`3 passed` cada) e dentro da execução completa dos 3 arquivos (216 passaram) e da suíte completa.

### 4.2 L2 — P2 determinístico e teste antigo

- **P2 presente:** `test_duas_cascatas_com_fevereiro_pausado_terminam_em_estado_unico`, em `apps/livro_caixa/tests/test_dl054_encadeamento.py:1159`.
  - Tem a âncora `_esperar(cascata_b)` (termina enquanto fevereiro e janeiro esperam).
  - Acrescenta `assert cascata_a.is_alive() and fechar.is_alive()` antes de liberar.
  - Afirma `res_a["erro"].meses == (2,)`, o estado final único `{1: encerrado, 2: encerrado, 3: aberto, 5: aberto}` e a trilha `[3, 5]`.
- **M3b aplicada por mim:** a reabertura passou a tomar o lock consultivo só do próprio mês e deixou de travar as linhas dos posteriores (sem `select_for_update`).
  - O P2 **reprovou nas 3 repetições**. A falha é `AssertionError: a cascata de janeiro deveria esperar o lock de fevereiro`, ou seja, `is_alive()` falso (thread `stopped`).
  - O teste antigo `test_duas_cascatas_e_um_fechamento_simultaneos_terminam_sem_deadlock` continuou verde (1 passed em cada repetição). Isso é o comportamento esperado depois da renomeação, e mostra que ele não protege a regra.
  - Rodando o arquivo `test_dl054_encadeamento.py` inteiro sob M3b: 5 falhas, entre elas o P2, os testes de ordem de lock e os dois de reabrir simples × encerrar posterior.
- **Sem mutação:** P2 passou em 5 de 5 repetições.
- **Teste antigo renomeado:** o nome saiu de `..._terminam_sem_deadlock_e_sem_estado_misto` para `..._terminam_sem_deadlock`.
  - A docstring diz explicitamente que ele só prova a ausência de deadlock e de estouro de lock, e remete o estado final ao P2.
  - As asserções de estado final foram removidas dele e movidas para o P2 (que é determinístico). Os acréscimos do teste antigo (`erro` de `r3` e ausência de `FechamentoMesCaixaTravado`) permanecem. Não houve perda de proteção, porque o P2 as cobre de forma discriminante.

### 4.3 L3 — campo oculto com ano fora da faixa

- **Código:** `apps/livro_caixa/views_web.py`, função `_meses_confirmados_do_formulario` (linha 2460). A condição passou a ser `item is None or item in confirmados or not (_ANO_MINIMO <= item[0] <= _ANO_MAXIMO)`.
- **Mesma faixa da API:** `_ANO_MINIMO` e `_ANO_MAXIMO` são importados de `apps.livro_caixa.views` (linha 104 de `views_web.py`). A definição única está em `apps/livro_caixa/views.py:790` (`1970, 2999`). A API usa as mesmas constantes em `views.py:564` e `:595`. Não foi acrescentada segunda faixa literal para o campo oculto.
  - Observação: `views_web.py` já tinha outras constantes literais `1970, 2999` (`_ANO_MINIMO_CARNE_LEAO` e `_ANO_MINIMO_FECHAMENTO_MES`, linhas 1101 e 2095), anteriores à DL-060 e para outras telas. Não pertencem à correção e não a contradizem.
- **Testes:** os 4 valores (`0000-01`, `9999-12`, `1969-12`, `3000-01`) entraram na parametrização de `test_campo_oculto_malformado_da_400_e_nao_altera_nada`, e todos passam (400 e banco inalterado).
- **Mutação:** removi a condição de faixa por `sed` na cópia. Resultado: exatamente os 4 casos novos reprovaram (`4 failed, 92 passed`) e o restante do arquivo seguiu verde. Revertido.

### 4.4 L4 — casos novos na API

- **Presentes e verdes** (29 passaram ao filtrar `campo_oculto_malformado or proprio_mes or inteiro_gigante`):
  - `test_api_lista_forjada_com_proprio_mes_ou_anterior_da_409_e_nao_altera_nada`: 5 casos (`proprio_mes_e_posterior`, `so_o_proprio_mes`, `anterior_do_ano`, `anterior_2025`, `ano_2027`). Todos esperam 409, `meses_encerrados_posteriores` com a lista atual e banco inalterado.
  - `test_api_inteiro_gigante_ou_negativo_da_400_sem_500_e_nao_altera_nada`: 5 casos (`10**40` em ano e em mês, `2**70`, `-1` em ano e em mês). Todos esperam 400 e banco inalterado.
- **Mutação independente** (mutante que ignora da lista confirmada tudo que não seja posterior de M, `x[1] > mes`): reprovam `anterior_do_ano` e `anterior_2025`. Revertida.
- **Observação sobre a força dos casos "próprio M"** (ver achado M1 na seção 5): o mutante que remove só o próprio mês da lista confirmada antes de comparar (`confirmados - {(ano, mes)}`) **sobreviveu**, com `96 passed`.

### 4.5 L5 — documental, permanece

Registrado, sem ação minha. Na versão `2734b74`:
- `docs/planos/` não tem `DL-060-*` (`ls docs/planos | grep 060` vazio).
- `docs/agents/estado.md` ainda trata a DL-060 como etapa futura (linhas 138 e 151), e o plano da DL-054 ainda descreve a API sem `meses_confirmados`.
- A decisão extra do desenvolvedor (`meses_confirmados` sem `cascata: true` dá 400) segue sem registro no plano.
- Responsável: `arquiteto-senior`, na integração. Verificação: `pwsh ./scripts/validate-docs.ps1` e `pytest apps/core/tests/test_documentacao_do_estado.py`.

## 5. Achados novos

### M1 — Caso "próprio M" não discrimina a mutação "ignorar o próprio mês na lista" (baixa)

- **Gravidade:** baixa. O comportamento está correto, e a lacuna é só de força do teste.
- **Requisito afetado:** critério 2 (lista forjada), item "lista com o próprio M" do L4.
- **Arquivo e localização:** `apps/livro_caixa/tests/test_dl060_confirmacao_da_cascata.py`, parametrização de `test_api_lista_forjada_com_proprio_mes_ou_anterior_da_409_e_nao_altera_nada` (casos `proprio_mes_e_posterior` e `so_o_proprio_mes`).
- **Evidência:**
  - Os dois casos mandam `{1,2}` e `{1}` para `M=1` com encerrados `{2,3}`. As listas já divergem de `{2,3}` por faltar o mês 3, então 409 sai mesmo que o servidor ignorasse o próprio mês.
  - Mutante `confirmados = frozenset(confirmados) - {(ano, mes)}` antes da comparação: 96 passed.
  - Experimento direto (arquivo temporário na cópia, removido): `{1,2,3}` para `M=1` devolve **409** com a mensagem "Confirmado: 01/2026, 02/2026, 03/2026. Agora: 02/2026, 03/2026", e o banco ficou idêntico. O código está correto.
- **Impacto:** quem passar a descartar o próprio mês da lista aceitaria uma confirmação com mês a mais sem que a suíte acuse. Dano limitado: o mês M já está em reabertura, então o efeito prático é só de contrato.
- **Correção recomendada:** trocar o caso `so_o_proprio_mes` por `(1, _meses(1, 2, 3))`, a lista exata mais o próprio M.
- **Forma de verificar:** aplicar o mutante acima. O caso novo deve reprovar, e passar sem mutação.
- **Responsável:** `desenvolvedor-pleno`. Pode ser feito na integração ou tratado como dívida. Não impede o parecer.

Não encontrei nenhum outro achado. Os experimentos não revelaram 500, nem efeito colateral em 400 ou 409.

## 6. Classificação

| Item | Classificação |
| --- | --- |
| Testes P1 sob M1 (reprovam) e sem mutação (passam, repetidos) | **Testado** (mutação aplicada por mim) |
| Teste P2 sob M3b (reprova) e sem mutação (passa, repetido) | **Testado** (mutação aplicada por mim) |
| Renomeação do teste antigo e remoção das asserções de estado | **Inspecionado** e **Testado** (continua verde sob M3b, como o nome agora admite) |
| L3, faixa de anos no campo oculto | **Inspecionado** e **Testado** (4 casos novos; mutação por `sed`) |
| L3, constantes compartilhadas com a API | **Inspecionado** |
| L4, casos novos da API | **Testado** (verdes; mutantes parciais) |
| `services.py` inalterado | **Testado** (`diff --stat` vazio e `diff` do arquivo) |
| Suíte completa em PostgreSQL | **Testado** (4269, 50, 1 falha conhecida de Python 3.13) |
| Lint, formatação, `check`, `makemigrations --check` | **Testado** |
| L5, documentação (plano e `estado.md`) | **Pendente do arquiteto** |
| Navegador, tela em 1.440 e 390 px | **Não retestado**: a mudança de tela é só validação no servidor, e o fluxo foi medido na rodada 1 |
| Python 3.14 (integração contínua) | **Não testado** (ambiente local é 3.13.12) |
| Conformidade contábil e legal da regra de reabrir em cascata | **Fora do escopo** (validação do Fred) |

## 7. Parecer

**APROVADO COM RESSALVAS**

**Fundamento:**
- Os achados de código da rodada 1 (L1 a L4) estão fechados. As lacunas de proteção por teste foram sanadas, e eu as comprovei por mutação:
  - M1 (comparação antes dos locks) agora derruba 3 testes, os dois P1 e o P2. Na rodada 1 derrubava nenhum.
  - M3b agora derruba o P2.
  - A remoção da faixa de anos derruba exatamente os 4 casos novos de L3.
- Não há falha bloqueadora ou de alta gravidade, nem critério essencial sem atendimento.
- A correção se limita a `views_web.py` (validação do campo oculto) e a testes. `services.py` não mudou, portanto o comportamento já aprovado do serviço não foi alterado.
- A suíte completa reproduz a linha declarada, sem regressão: apenas a falha conhecida de Python 3.13.

**Ressalvas explícitas (nenhuma esconde falha essencial):**
1. **L5 (baixa, processo), pendente do `arquiteto-senior`:** gravar o plano da DL-060 em `docs/planos/` com a decisão `meses_confirmados` sem `cascata: true` dá 400, atualizar `docs/agents/estado.md` e anotar no plano da DL-054 que o contrato da API mudou. A regra permanente do Fred no `CLAUDE.md` exige isso ao concluir a etapa.
2. **M1 (baixa):** o caso "só o próprio mês" da API não discrimina o mutante que ignora o próprio mês. Correção de uma linha, na seção 5.
3. **Escopo de verificação:** Python 3.14 (versão da integração contínua) não foi testado. A acessibilidade fina (teclado e leitor de tela) da tela do 409 também não foi testada, como na rodada 1.

**Sobre a regra de parada (§3.1):** esta foi a reconferência única, e o parecer é final. Não há terceira rodada.

**O que este parecer não declara:** ausência de bugs, segurança absoluta ou conformidade legal. A auditoria de software não substitui a validação profissional das regras contábeis e legais. As mutações cobrem as regressões que testei, não todas as possíveis.

## 8. Arquivos relevantes

Caminhos no repositório principal, na versão `2734b74`:
- `/home/user/DataLedger/apps/livro_caixa/views_web.py` (linhas 104, 2440-2462)
- `/home/user/DataLedger/apps/livro_caixa/views.py` (linha 790, constantes da faixa de anos)
- `/home/user/DataLedger/apps/livro_caixa/services.py` (inalterado; locks em `:1345`, comparação em `:1384-1385`)
- `/home/user/DataLedger/apps/livro_caixa/tests/test_dl060_confirmacao_da_cascata.py` (P1 ao fim do arquivo; L3 e L4 na parametrização e na seção da API)
- `/home/user/DataLedger/apps/livro_caixa/tests/test_dl054_encadeamento.py` (linhas 1050-1160 e P2 a partir de 1159)

Os arquivos de mutação e experimento ficaram só na cópia `scratchpad/rec060` e não pertencem ao repositório.
