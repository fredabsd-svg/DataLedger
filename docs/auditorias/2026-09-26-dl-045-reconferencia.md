# Reconferência da DL-045 (DRE): correção do servidor e fatia 3

**Data:** 2026-09-26
**Auditor:** `auditor-qa`. Trabalhei de forma independente. Não corrigi nada e não alterei nenhum teste do projeto.
**Nível de risco:** 1 (AGENTS.md §3.1). Esta é a reconferência única.
**Parecer:** **REPROVADA**

Há um achado **alto**, o R1. A correção do A6 (guarda de reparentamento) fechou a única saída do veto que o A2 criou. Com isso, uma conta patrimonial com movimento pendurada sob uma linha de resultado deixa a DRE inemitível até o fim do exercício. Deixa também o **Balanço** (DL-034) inemitível sem prazo: isso é regressão. Só SQL direto resolve.

Há ainda seis achados médios e cinco baixos:

- **Médios:**
  - R2: classificação desconhecida veta, mas não pode ser corrigida pelo produto.
  - R3: o PATCH devolve 500.
  - R4: corrida na classificação.
  - R5: a navegação sai impressa no documento.
  - R6: a tela mostra como "linha atual" o valor que acabou de ser recusado.
  - R7: 17 mutantes sobrevivem, entre eles os de isolamento e autorização. A alegação de que o M27 é equivalente é **falsa**.
- **Baixos:** R8 a R12.

Os A1 a A10 da rodada 1 estão fechados ou fechados em parte, conforme a tabela abaixo. Na aritmética não achei defeito.

## Revisão auditada

- Worktree `wt-dl045t`, branch local `dl045-tela`, HEAD **`1e472c232711e6d236ccca419c03fb675b19fa7b`**, conferido com `git rev-parse` no início e no fim. A árvore estava limpa.
- Ambiente: Python 3.13.12 e PostgreSQL local.
- A suíte completa rodou na própria worktree, com banco `dataledger_qa45r`.
- Mutações e experimentos rodaram em duas cópias descartáveis feitas com `git archive 1e472c2`, com os bancos `dataledger_qa45rx`, `dataledger_qa45ry` e `dataledger_qa45rm`. A medição do emitente e o servidor de desenvolvimento usaram o `dataledger_qa45rm`.
- **Limpeza:** apaguei as cópias, o SQLite e todos os bancos. A contagem em `pg_database` com `LIKE '%qa45%'` deu `0`.
  - Antes de apagar, comparei a cópia mutada com um `git archive` novo por `diff -rq`: nenhuma diferença, ou seja, toda mutação foi revertida.
  - Na worktree auditada e em `/home/user/DataLedger`, `git status --short` e `git diff --stat` saíram vazios. O HEAD continua `1e472c2`.

## Comandos e números exatos (critério 9)

| Comando | Resultado |
| --- | --- |
| `pytest --create-db -q`, suíte completa, na worktree | `1 failed, 2921 passed, 45 skipped, 3 warnings, 4 subtests passed in 135.12s` |
| A falha | `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É **preexistente e de ambiente**: local 3.13, CI 3.14. |
| Avisos | 3 `RemovedInDjango70Warning: savepoint() is deprecated`. Um deles é **novo**, de `test_dl045_dre.py:2270` (ver R11). |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` (sempre com `--check`) | `285 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `migrate` em PostgreSQL vazio | OK até `contabilidade.0011_dl045_rodada1_classificacao_dre_nao_vazia` |
| 0011 com dado `""`, PostgreSQL | Voltei para a 0010 e gravei `classificacao_dre=''` por ORM. Ao reaplicar, o `''` vira `NULL`, e a restrição `ck_conta_classificacao_dre_nao_vazia` existe. Um `UPDATE ... SET classificacao_dre=''` é recusado com `violates check constraint`. |
| Reversão da 0011, PostgreSQL | `migrate contabilidade 0010`: a restrição some (contagem 0) e o dado fica. Em seguida, `migrate contabilidade 0009` e reaplicação: OK. |
| SQLite vazio, mesmo roteiro | `''` vira `None` na 0011, e a gravação de `''` depois dela dá `CHECK constraint failed: ck_conta_classificacao_dre_nao_vazia`. Reversão para 0009 e reaplicação: OK. |
| `scripts/medir_identificacao_do_emitente.py` (base semeada, Chromium do Playwright) | **exit 0.** Mediu 5 telas com timbre e 2 de classe 2 (`balanco`, `dre`). DRE: `PASSOU`, `total_paginas: 1`, `folhas_sem_bloco_do_item_51: []`. |
| `pwsh ./scripts/validate-docs.ps1` | **Não testado**: `pwsh` não existe no ambiente. |

## A1 a A10: estado

| Achado | Estado | Evidência |
| --- | --- | --- |
| **A1** aninhada com linha diferente | **Fechado** | **Cenário:** filha `4.1.01` em DESPESAS_COM_VENDAS sob o grupo em CUSTO, com 500,00. **API:** `409`, com a conta em `listas_pendentes.coluna_mes.contas_com_classificacao_dre_aninhada_linha_diferente`. **Tela:** 200 com veto; lista a conta e não monta a tabela. **Mutantes:** N01 (lista movida para "só avisa") e N20 (toda aninhada tratada como mesma linha) morrem. |
| **A2** tipo divergente | **Fechado quanto ao veto. A correção criou o R1.** | O ATIVO `3.1.99` sob receita bruta e a DESPESA `3.1.90` sob receita bruta dão os dois `409`, com `contas_com_tipo_divergente_da_linha`. N02 e N07 morrem. **Mas a saída do veto está bloqueada (R1).** |
| **A3** estorno de zeramento | **Fechado** | **Cenário:** receita de 1.000,00 em 15/01; zeramento de janeiro; estorno das duas etapas em 10/02; 200,00 em 20/02. **DRE:** janeiro, mês = 1.000,00; fevereiro, mês = **200,00**; fevereiro, acumulado = **1.200,00**. **Conciliação:** o zeramento de fevereiro transfere 1.200,00, e a divergência do mês é declarada na API (`listas_informativas`, os dois estornos, datados em 10/02) e na tela ("estorno do zeramento"). **Mutantes:** N04 morre. N05 (isolamento da lista) e N06 (datas da lista) sobrevivem, ver R7. |
| **A4** `""` | **Fechado** | `POST` com `""` devolve `201` e o banco grava `None`. `PATCH` com `""` também grava `None`. A primeira classificação depois disso, com movimento, é aceita com `200`. A tela "Sem classificação" grava `None` (teste do desenvolvedor). A restrição de banco vale em PostgreSQL e SQLite, e a 0011 normaliza o legado. Resíduo novo e distinto: R3. |
| **A5** snapshot | **Fechado** | Inspecionado: `apurar_dre` tem o `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` do Balanço. `ATOMIC_REQUESTS` está desligado, então a tela e a API chamam fora de `atomic` e o snapshot vale. O par `test_a5_*` (sem e com o wrapper) passa na suíte. Não refiz uma corrida própria: o par reproduz a minha da rodada 1. |
| **A6** guarda contornável | **Fechado (a) e (b)**, com efeito colateral no R1 | Os cenários (a) e (b) são recusados (testes `test_a6a_*` e `test_a6b_*`). Os mutantes N17 (reparentamento desligado) e N18 (subárvore desligada) morrem. A guarda (b), porém, bloqueia a correção do A2 (R1), e a gravação não tem trava (R4). |
| **A7** porta de classificação | **Fechado em parte** | **API e tela, por papel:** ADMINISTRADOR, GESTOR, ANALISTA e FINANCEIRO gravam (tela `302`, API `200`). PARALEGAL e CLIENTE recebem `403` nas duas portas, sem gravar nada. Anônimo recebe `302` para o login, sem gravar. **Isolamento, conta de outra empresa do mesmo escritório:** API `404`, tela GET `404` e POST `404`; nada gravado, nenhuma trilha. **Recusa com movimento na tela:** o banco continua em `custo`, nenhuma trilha, a seleção fica preservada e a mensagem fala em "movimento do exercício". **Admin:** `classificacao_dre` está em `list_display` e `list_filter`, com `EmptyFieldListFilter`. **Resíduos:** R2, R3, R4 e R6, e os testes de autorização e isolamento que faltam (R7). |
| **A8** mutantes | **Fechado em parte** | Dos 12 sobreviventes da rodada 1, 11 morrem agora: M04, M05, M06, M08, M12, M13, M14, M21, M25, M28 e M30. O **M27 sobrevive**, e a alegação de equivalência não se sustenta (ver a seção de mutantes). Há sobreviventes novos (R7). |
| **A9** documentação | **Fechado para os seis pontos** | O `estado.md` não traz mais a pendência revogada. O comentário "Escopada à coluna do MÊS" saiu. `_LINHAS_ANTES_DO_FINANCEIRO` foi corrigido. O plano diz "10 → 50" e traz a partição correta. A DE-085, item 1, formaliza as decisões. Há documentação nova defasada (R11). |
| **A10** totais | **Fechado em parte** | **Medido:** débitos 1.000,00 (01/03) e 400,00 (31/03), dedução de 50,00, e depois o zeramento. A DRE dá `total_debitos 450.00` e `total_creditos 1050.00`, que é a soma das contas de resultado no Balancete sem o zeramento (400 + 50; 1.000 + 50). **Falta:** o teste de conciliação com o Balancete, prometido na DE-085, item 9, não existe (`grep balancete` em `test_dl045_dre.py` volta vazio). |

## Mutantes

Cada mutante foi aplicado sozinho numa cópia descartável e revertido, com a restauração conferida. A primeira bateria rodou com `-x` sobre `test_dl045_dre.py`, `test_dl045_fatia3_tela_da_dre.py` e `test_dl038_recusa_livro_caixa.py` (124 testes). Os sobreviventes foram reconfirmados contra **todo `apps/`**: `2786 passed, 14 skipped`, com `test_versao_minima_python` desmarcado.

**Resumo:** 47 mutantes aplicados e mais 1 que não casou com o texto (N23, descartado). **30 morreram e 17 sobreviveram.**

### Os sobreviventes da rodada 1

| # | Resultado | Teste que mata |
| --- | --- | --- |
| M04 | morto | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M05 | morto | `test_caso1_…` |
| M06 | morto | `test_caso1_…` |
| M12 | morto | `test_caso1_…` |
| M13 | morto | `test_caso1_…` |
| M14 | morto | `test_caso1_…` |
| M08 | morto | `test_caso2_raiz_despesa_sem_classificacao_com_movimento_veta_pelo_residuo` |
| M21 | morto | `test_m21_deducoes_da_receita_recusa_conta_de_tipo_despesa` |
| M25 | morto | `test_caso4_…` (500 em `/dre/2026/13/`) |
| M28 | morto | `test_caso5_…` (500) |
| M30 | morto | `test_caso3_…` |
| **M27** (tira os dois filtros de empresa da agregação) | **sobrevive** a `apps/` inteiro | nenhum |
| **M27b** (tira só `lancamento__empresa`) | **sobrevive** a `apps/` inteiro | nenhum |

**Sobre a alegação de que o M27 virou mutante equivalente: não é verdade.** A equivalência só vale se todo item de lançamento tiver `conta.empresa == lancamento.empresa`. Esse invariante é garantido por `criar_lancamento`, **não pelo banco**: não há restrição nem gatilho.

O próprio projeto trata o dado corrompido como cenário de teste. É o achado 10 da DL-015, `test_dl015_saidas_com_periodo.py::test_item_de_lancamento_de_outra_empresa_nao_aparece_no_razao_nem_no_balancete`.

Sonda que rodei:

1. Lançamento legítimo da empresa A de 100,00.
2. Por ORM, um item extra de **crédito de 7,00 na receita bruta da empresa B**.
3. DRE da empresa B:
   - código original: receita bruta `0`, `total_creditos 0`;
   - **M27:** `7.00` e `7.00`;
   - **M27b:** `7.00` e `7.00`.

Os dois mutantes são, portanto, **mortais por um teste de isolamento**, que falta. O risco real hoje é baixo, porque os dois filtros estão no código e o cenário exige dado corrompido. Mas "equivalente" é afirmação falsa, e o isolamento da DRE diante de dado corrompido fica sem prova, ao contrário do Balancete e do Razão.

### Mutantes novos (mudanças recentes)

| # | Mutação | Resultado |
| --- | --- | --- |
| N01 | aninhada com linha diferente movida para "só avisa" | morto (`test_a1_…`) |
| N02 | tipo divergente movido para "só avisa" | morto (`test_a2a_…`) |
| **N03** | **classificação desconhecida movida para "só avisa"** (a partição continua válida) | **sobrevive** |
| N04 | sem a exclusão dos estornos de zeramento | morto (`test_a3_…`) |
| **N05** | **`_estornos_de_zeramento_na_coluna` sem `empresa=empresa`** (isolamento) | **sobrevive** |
| **N06** | lista de estornos sem `data__gte=inicio` | **sobrevive** |
| N07 | tipo divergente só para RECEITA e DESPESA (ignora patrimonial) | morto (`test_a2a_…`) |
| N08 | serviço sem `full_clean()` | morto |
| N09 | serviço sem `registrar()` | morto |
| N10 | tela de classificação sem `_pode_escriturar` | morto |
| N11 | tela de classificação: `get_object_or_404` sem `empresa` | morto |
| **N12** | **API PATCH: `get_object_or_404(Conta, pk=conta_id)` sem empresa** | **sobrevive**. O único teste de isolamento usa `999999`. |
| N13 | migração 0011: `RunPython` virando `pass` | sobrevive. Nenhum teste migra com dado. Conferi a migração à mão (ver os comandos acima). |
| N14 | serializer sem normalizar `""` | morto (500 no POST) |
| N15 | links do veto sem filtro de empresa | morto |
| N16 | tela monta a DRE mesmo com veto | morto |
| N17 | guarda de reparentamento desligada | morto |
| N18 | guarda da subárvore desligada | morto |
| N19 | totais somam todas as contas | morto (`test_caso6_…`) |
| N20 | toda aninhada vira "mesma linha" | morto |
| **N22** | bloco do item 51 imprime `data_inicio_mes` como fim do acumulado | **sobrevive** |
| N24 | `clean()` sem normalizar `""` | sobrevive. **Equivalente na prática**: o serializer, o formulário, o serviço e a restrição cobrem. |
| N25 | guarda sem `or None` no valor gravado | sobrevive. **Equivalente**: `""` não pode ser gravado. |
| **T01** | receita bruta e deduções trocadas de linha na tela | **sobrevive** |
| **T02** | coluna Mês mostra o acumulado | **sobrevive** (a fixture tem mês = acumulado) |
| **T03** | negativo sem parênteses | **sobrevive** |
| **T04** | "Resultado financeiro" mostra o lucro bruto | **sobrevive** |
| **T05** | **API PATCH com `PodeLerContabilidade`, deixando o PARALEGAL gravar** | **sobrevive** |
| **T06** | **tela de classificação com `_pode_ler`, deixando o PARALEGAL gravar** | **sobrevive** |
| T07 | tela: conta do mesmo escritório, de outra empresa | morto |
| **T08** | **API: conta de outra empresa do mesmo escritório** | **sobrevive** |
| T09 | tela de classificação sem a recusa de livro-caixa | morto (varredura da DL-038) |
| T10 | tela da DRE sem a recusa de livro-caixa | morto |
| T11 | navegação avança 2 meses | morto |

## Achados

### R1 — ALTA — A guarda de reparentamento do A6 bloqueia a única correção do veto do A2; a DRE fica inemitível no exercício, e o Balanço sem prazo (regressão da DL-034)

1. **Gravidade:** alta. É o mesmo tipo de dano que tornou o A4 alto: demonstração inemitível, com SQL como única saída.
2. **Requisito afetado:**
   - RC-120 e critério 6: corrigir a pendência tem de ser possível;
   - DE-085, itens 3 e 7;
   - DL-034 (Balanço, `contas_com_tipo_divergente_da_raiz`);
   - o docstring de `avaliar_emissao_da_dre`: "corrigir a pendência é sempre possível".
3. **Local:**
   - `apps/contabilidade/models.py:1256-1280`: o bloco `if not self.classificacao_dre:` compara `linha_antes` com `linha_depois` para qualquer tipo de conta;
   - a recusa na entrada continua em backlog (DE-085, item 3), e a tela `conta_nova` aceita criar a conta ATIVO sob receita bruta (medido: `302`, criada).
4. **Reprodução** (cenário do `test_a2a`):
   - Conta `3.1.99`, tipo ATIVO, sob receita bruta, com débito de 300,00 em 10/03.
   - Tentativas de saída:
     - **Reparentar** para uma raiz ATIVO: `ValidationError` "Não é possível reparentar esta conta … a linha da DRE herdada mudaria…".
     - **Estornar** o movimento em 20/03: continua `pode_emitir=False`, porque débito e crédito ficam diferentes de zero na coluna.
     - **Trocar o tipo:** recusado ("Não é possível mudar a natureza e o tipo…").
     - **Classificar a própria conta:** recusado, porque nenhuma linha aceita tipo patrimonial.
     - **Transferir** o saldo para uma conta ATIVO correta em 05/04: a DRE continua vetada em abril, maio e dezembro, e só volta a `True` em janeiro de 2027.
   - O **Balanço** em 31/03 e em 30/04, com saldo zero depois da transferência, continua `pode_emitir=False`, com `contas_com_tipo_divergente_da_raiz`. A régua dele é o movimento, e o reparentamento, que era a saída antes da DL-045, agora é recusado.
   - Antes desta correção, a guarda de reparentamento (BL-261) só olhava a natureza, e ATIVO devedora para raiz ATIVO devedora passava. **Inspecionado no código, não executado na base antiga.**
5. **Impacto:** um erro de cadastro que o produto aceita pela tela torna o Balanço da empresa inemitível para sempre e a DRE inemitível até o fim do exercício. Só SQL direto resolve.
6. **Correção recomendada** (decisão do `arquiteto-senior`):
   - (a) Aplicar a guarda do A6(b) só quando a conta, ou a subárvore com movimento, tinha tipo **aceito** pela `linha_antes`. Assim, tirar de uma linha de resultado uma conta que nunca poderia estar nela é correção e deve ser livre.
   - (b) Trazer para esta etapa a recusa na entrada de conta patrimonial com pai de resultado. Isso impede o estado, mas não resolve o dado já gravado, então (a) continua necessária.
7. **Como verificar:**
   - O cenário acima: o reparentamento para uma raiz ATIVO é aceito.
   - Em seguida, a DRE de março e o Balanço de 31/03 voltam a emitir, e o A6(b) continua recusando o cenário original dele.

### R2 — MÉDIA — Classificação "desconhecida" veta, mas a conta com movimento não pode ser corrigida por nenhuma porta do produto

1. **Gravidade:** média.
2. **Requisito afetado:** DE-085, item 2 ("classificação desconhecida veta"), critério 6 e o mesmo princípio do A4.
3. **Local:** `models.py:1106-1113` (`classificacao_dre_gravada` com valor fora de `ClassificacaoDre` é tratada como "já classificada") e `services.py:4804`.
4. **Evidência:**
   - Conta DESPESA `4.9` com 40,00 de movimento e `classificacao_dre` gravada por ORM como `"linha_antiga_renomeada"`.
   - O POST na tela com `outras_despesas` volta `200` com a recusa, e o banco fica com o valor antigo.
   - O PATCH na API com `null` devolve `400`.
   - A DRE de dezembro dá `pode_emitir=False`.
5. **Impacto:** hoje exige dado gravado por fora. O caminho realista é o futuro: renomear ou fundir uma linha, o que o RC-121 e a HI-29 declaram reversível. Toda conta com a linha antiga e movimento ficaria travada, e a DRE inemitível até o fim do exercício.
6. **Correção recomendada:** na guarda de transição, tratar como "não classificada" também a gravada que não esteja em `ClassificacaoDre.values`, como foi feito com `""`.
7. **Como verificar:** o cenário acima grava `outras_despesas` pela tela e pela API, e a DRE passa a emitir.

### R3 — MÉDIA — `PATCH .../classificacao-dre/` devolve 500 com valor que não é texto ou com corpo em lista

1. **Gravidade:** média. Viola a regra do projeto "erro de entrada nunca é 500".
2. **Requisito afetado:** A7 e a robustez da API.
3. **Local:**
   - `apps/contabilidade/views.py:1767`: `request.data.get(...)` em corpo que é lista dá `AttributeError`;
   - `models.py:822`: `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE.get(<dict|list>)` dá `TypeError: unhashable`. O `full_clean()` roda `clean()` mesmo depois que `clean_fields()` falha.
4. **Evidência:**

   | Corpo | Resultado |
   | --- | --- |
   | `{"classificacao_dre": {"a": 1}}` | **500** |
   | `{"classificacao_dre": ["receita_bruta"]}` | **500** |
   | `["x"]` | **500** |
   | `123`, `true`, `"RECEITA_BRUTA"` | 400, correto |

   Nada é gravado nos casos de 500.
5. **Impacto:** 500 mudo para entrada malformada, na porta que o A7 abriu.
6. **Correção recomendada:** validar que o corpo é dicionário e que o valor é `str` ou `None` antes do serviço, por exemplo com um `ChoiceField` do DRF. Na guarda de tipo do `clean()`, só consultar o mapa quando o valor for `str`.
7. **Como verificar:** os três corpos acima devolvem 400, com mensagem, e nada gravado.

### R4 — MÉDIA — Corrida em `classificar_conta_na_dre`: duas "primeiras classificações" simultâneas reclassificam conta com movimento, e a trilha mente

1. **Gravidade:** média.
2. **Requisito afetado:** a guarda de transição (RC-118), a trilha de auditoria e a atomicidade.
3. **Local:** `services.py:5229-5232`. É `@transaction.atomic` sem `select_for_update`, e a guarda lê o valor gravado sob READ COMMITTED.
4. **Evidência:** teste `transaction=True`, com duas threads e uma barreira logo depois do `full_clean()`, sobre uma conta DESPESA com 100,00 de movimento. As threads gravam CUSTO e DESPESAS_COM_VENDAS. Resultado:
   - valor final: `despesas_com_vendas`, sem erro nenhum;
   - trilha: `[{antes: None, depois: custo}, {antes: None, depois: despesas_com_vendas}]`.
5. **Impacto:** conta com movimento trocou de linha, que é o que a guarda proíbe. A trilha registra "antes: None" num momento em que o valor gravado era `custo`.
6. **Correção recomendada:** reler a conta com `select_for_update()` dentro da transação do serviço antes do `full_clean()`, ou gravar com `UPDATE` condicional ao valor lido. Mais o teste de corrida.
7. **Como verificar:** o mesmo teste termina com uma gravação aceita e a outra recusada pela guarda, e a trilha fica coerente.

### R5 — MÉDIA — O documento impresso da DRE leva os controles "‹ Mês anterior / Setembro de 2026 / Mês seguinte ›"

1. **Gravidade:** média. Afeta o documento formal entregue ao cliente (RC-120, classe 2).
2. **Requisito afetado:** RC-120, critério 7 e a regra do `@media print` do projeto ("controle de NAVEGAÇÃO, nunca conteúdo do documento").
3. **Local:**
   - `templates/contabilidade/dre.html:54-66` (`<nav class="navegacao-competencia">` com `<a class="botao">`);
   - `static/css/base.css:3398-3412`, lista de ocultação na impressão: não inclui `.navegacao-competencia`, e os links não são `button`.
4. **Evidência:**
   - Emulei `print` e gerei PDF A4 da DRE da base de medição.
   - O `pdftotext` e a imagem rasterizada mostram os dois botões e o mês entre o timbre e o bloco do item 51.
   - O Balanço esconde o seletor dele (`.formulario-periodo`).
   - O job do emitente não mede isso: saiu com exit 0.
5. **Impacto:** controle de tela impresso na demonstração formal.
6. **Correção recomendada:** acrescentar `.navegacao-competencia` à lista de ocultação no `@media print`.
7. **Como verificar:** o PDF da DRE não contém "Mês anterior" nem "Mês seguinte". Serve um teste de CSS simulado no molde do `test_bl329`, ou a sonda de impressão.

### R6 — MÉDIA — Depois de uma recusa, a tela de classificação mostra como "Linha atual" o valor recusado

1. **Gravidade:** média. A interface afirma um estado que não foi gravado.
2. **Requisito afetado:** A7 ("recusa preserva formulário, nada gravado") e a regra de que a tela funcione de verdade, e não só aparente.
3. **Local:**
   - `services.py:5230` muta a instância (`conta.classificacao_dre = classificacao`) antes do `full_clean()`;
   - `views_web.py:1036-1053` re-renderiza com a mesma `conta`;
   - o template mostra `conta.get_classificacao_dre_display`.
4. **Evidência:** a conta CUSTO tem movimento, e envio `despesas_com_vendas`. A resposta traz o alerta de recusa **e** "Linha atual: **Despesas com vendas**", enquanto o banco diz `custo`.
5. **Impacto:** quem lê pode entender que a troca foi gravada.
6. **Correção recomendada:** `conta.refresh_from_db()` no ramo de erro, ou fazer o serviço trabalhar numa cópia.
7. **Como verificar:** depois da recusa, o HTML mostra "Linha atual: Custo".

### R7 — MÉDIA — Testes insuficientes: 17 mutantes sobrevivem, entre eles isolamento e autorização

1. **Gravidade:** média, como o A8.
2. **Requisito afetado:** critérios 6, 7 e 8; DE-085, itens 9 e 10; AGENTS.md (toda regra vira teste).
3. **Local:** `test_dl045_dre.py` e `test_dl045_fatia3_tela_da_dre.py`.
4. **Evidência:**
   - **Isolamento:** M27, M27b (sonda com item forjado: vazam 7,00), N05 (lista de estornos sem filtro de empresa), N12 e T08 (API PATCH em conta de outra empresa, inclusive do mesmo escritório).
   - **Autorização:** T05 e T06 (PARALEGAL passa a gravar, porque os testes só usam CLIENTE).
   - **Veto:** N03 (desconhecida deixa de vetar; nenhum teste cobre essa lista).
   - **Documento e tela:** T01 (ordem das linhas), T02 (mês contra acumulado: a fixture tem os dois iguais), T03 (parênteses do negativo), T04 (subtotal trocado) e N22 (data do fim do acumulado no bloco do item 51). O teste da tela conta ocorrências com `count(valor) >= 2` e não confere linha, coluna nem ordem.
   - **Outros:** N06 (datas da lista de estornos) e N13 (migração com dado).
   - **Promessa não cumprida:** o teste de conciliação com o Balancete prometido pela DE-085, item 9.
5. **Impacto:** regressões de isolamento, de papel e de apresentação do documento passariam pela CI.
6. **Correção recomendada:** acrescentar os casos da seção "Casos de teste propostos".
7. **Como verificar:** rodar de novo M27, M27b, N03, N05, N06, N12, N22, T01 a T06 e T08: todos morrem.

### R8 — BAIXA — Mensagem de veto fixa e links "classificar esta conta" que não levam a lugar nenhum

1. **Gravidade:** baixa.
2. **Requisito afetado:** critério 6 (explicar o veto).
3. **Local:** `templates/contabilidade/dre.html:103-104` e `:149-154`.
4. **Evidência:**
   - O texto é sempre "há conta de resultado com movimento sem linha da DRE", mesmo quando o veto é por tipo divergente, aninhada, desconhecida ou resíduo.
   - O PARALEGAL vê os links e recebe `403` ao segui-los.
   - A conta ATIVO do tipo divergente recebe o link, mas qualquer linha que se escolha lá é recusada.
   - Conferi: todas as listas que vetam (sem classificação, tipo divergente, aninhada com linha diferente, desconhecida) e o resíduo aparecem juntos, cada conta com link.
5. **Impacto:** orientação errada ou inútil.
6. **Correção recomendada:** texto genérico ("há pendência que impede a emissão"); link só quando `_pode_escriturar` e só para conta de resultado; para conta patrimonial, apontar a correção real, que depende do R1.
7. **Como verificar:** renderizar o veto para PARALEGAL e para tipo divergente.

### R9 — BAIXA — A tabela da DRE transborda 6 px em 390 px

1. **Gravidade:** baixa.
2. **Requisito afetado:** direção de arte da DL-044 (sem rolagem horizontal da página).
3. **Local:** `table.tabela-dados` da DRE emitida.
4. **Evidência:**
   - Largura de 390: `scrollWidth 396`, com `TABLE.tabela-dados right=396`.
   - O Balanço, na mesma largura, fica em 390.
   - Em 1440 não há transbordo, e as colunas Mês e Acumulado alinham à direita (`['left','right','right']`).
5. **Impacto:** rolagem horizontal no celular, que cresce com valores maiores.
6. **Correção recomendada:** o mesmo tratamento responsivo da tabela do Balanço.
7. **Como verificar:** `scrollWidth == 390`.

### R10 — BAIXA — Os links de navegação nos limites levam a erro 400

1. **Gravidade:** baixa.
2. **Local:** `views_web.py:3514-3525` e `dre.html:55-65`.
3. **Evidência:**
   - Em `ano=2999&mes=12`, o link "seguinte" aponta para `3000/1`, que devolve 400.
   - Em `ano=1970&mes=1`, o link "anterior" aponta para `1969/12`, que devolve 400.
   - A virada de ano está correta: 2026/12 vai a 2027/1, e 2026/1 vai a 2025/12.
   - As entradas inválidas (`13`, `0`, só `ano`, só `mes`, `abc`, dígitos arábicos, `3000`, `1969`) devolvem 400 com saída navegável.
4. **Correção recomendada:** omitir o link fora da faixa.
5. **Como verificar:** GET nos dois limites não traz o link para fora da faixa.

### R11 — BAIXA — Documentação defasada ou contraditória

1. **Gravidade:** baixa.
2. **Requisito afetado:** CLAUDE.md, "estado num lugar só", e honestidade da documentação.
3. **Local e evidência:**
   - **`docs/agents/estado.md`:**
     - a linha 30 diz "só servidor/API … sem tela ainda";
     - a linha 35 diz "**Não existe:** Tela da DRE (DL-045 fatia 3)";
     - as duas são falsas nesta branch.
   - **Plano:** não tem seção de implementação da fatia 3. As decisões de parênteses para negativo, 200 no veto, tela de classificação e piso da medição estão só nos commits.
   - **Tela de classificação:** o docstring de `conta_classificacao_dre` (`views_web.py:1000`) diz "RE-renderiza o formulário com 400", mas a recusa e o valor inválido devolvem **200**.
   - **DE-085, item 9:** promete teste de conciliação com o Balancete, que não existe.
   - **Aviso novo na suíte:** `test_dl045_dre.py:2270` usa `transaction.savepoint()`, que dispara `RemovedInDjango70Warning`.
4. **Correção recomendada:** atualizar os pontos acima.
5. **Como verificar:** busca pelos termos citados, e a suíte sem o aviso novo.

### R12 — BAIXA — "Critério de apuração impresso", prometido no plano da fatia 3, não existe no documento

1. **Gravidade:** baixa. Não é critério numerado.
2. **Requisito afetado:** plano DL-045, fatia 3 ("como o Balanço (DL-034): identificação do emitente em toda página, critério de apuração impresso").
3. **Local:** `templates/contabilidade/dre.html`. O Balancete imprime "Critério de apuração" (`balancete.html:154`).
4. **Evidência:**
   - O PDF não diz que a DRE exclui os lançamentos de zeramento e os estornos deles, nem que o exercício é o ano civil (HI-28).
   - A lista de estornos de zeramento é só de tela (`mensagem--somente-tela`), então o documento de um mês com estorno diverge do zeramento sem explicação no papel.
5. **Correção recomendada:** o arquiteto decide se imprime a nota ou se retira a promessa do plano.
6. **Como verificar:** o PDF traz a nota, ou o plano registra a decisão.

## Regressões

- **DL-043 (zeramento):** a suíte está verde. O zeramento e o estorno de zeramento se comportam como a DE-085 decidiu, conferido no cenário do A3.
- **DL-044 (telas):** a suíte está verde. A DRE entra pelo hub de Relatórios e pelo submenu (testes do desenvolvedor), e o alinhamento à direita foi conferido no navegador. O transbordo em 390 px é o R9.
- **DL-034 (Balanço):** **regressão funcional no R1.** A saída por reparentamento da pendência `contas_com_tipo_divergente_da_raiz` foi fechada pela guarda nova. Nenhum teste existente acusa.

## Casos de teste propostos, para o responsável implementar

1. **R1:** a conta ATIVO `3.1.99` sob receita bruta, com 300,00. O reparentamento para uma raiz ATIVO é aceito. Depois dele, a DRE de março e o Balanço de 31/03 emitem.
2. **R2:** conta com movimento e `classificacao_dre` desconhecida, gravada por ORM. A primeira classificação válida é aceita pela tela e pela API.
3. **R3:** os PATCHs com `{"classificacao_dre": {…}}`, `[…]` e o corpo `["x"]` devolvem 400, sem gravar nada.
4. **R4:** corrida com barreira depois do `full_clean()`. Uma gravação é aceita, a outra é recusada, e a trilha fica coerente.
5. **R5:** o PDF, ou a cascata simulada, da DRE não contém "Mês anterior" nem "Mês seguinte".
6. **R6:** depois da recusa, o HTML mostra a linha gravada.
7. **Isolamento, M27 e M27b:** item forjado por ORM, com conta de B dentro de lançamento de A. A DRE de B continua com receita bruta 0 e `total_creditos` 0.
8. **Isolamento, N05:** estorno de zeramento na empresa B não aparece em `estornos_de_zeramento_na_coluna` da empresa A.
9. **Isolamento, N12 e T08:** PATCH `/empresas/<A>/contas/<id de conta de B do MESMO escritório>/classificacao-dre/` devolve 404, e a conta de B fica intacta.
10. **Autorização, T05 e T06:** o PARALEGAL recebe 403 na API e na tela de classificação, sem gravar.
11. **N03:** conta com classificação desconhecida e movimento devolve 409, com a conta em `listas_pendentes.*.contas_com_classificacao_dre_desconhecida`.
12. **N06:** um estorno datado em fevereiro não aparece na coluna do mês de março.
13. **Tela, T01 a T04 e N22:**
    - fixture com **mês ≠ acumulado**, com movimento em janeiro e em março;
    - pelo menos um subtotal negativo;
    - valores distintos por linha;
    - ler a tabela **linha a linha**, conferindo título, valor do mês e valor do acumulado, com parênteses no negativo;
    - conferir "01/01/AAAA a <último dia do mês>" no bloco do item 51.
14. **A10:** `total_debitos` e `total_creditos` de março iguais à soma das contas de resultado do Balancete do mesmo período, sem os lançamentos de zeramento.

## Dúvidas contábeis, para o Fred (não são defeitos de software)

- **F1.** Os rótulos "Lucro bruto" e "Lucro líquido do período" são fixos, e o negativo sai entre parênteses. O art. 187, VII fala em "lucro ou prejuízo líquido do exercício". Fica a dúvida se o rótulo deve mudar para "Prejuízo" quando negativo.
- **F2.** No mês de um estorno de zeramento, a DRE e o valor transferido pelo zeramento divergem (DE-085, item 4). A explicação existe só na tela. Fica a dúvida se o documento deve trazer uma nota (ver R12).
- **F3.** Continua aberta a pergunta do A7: a linha da DRE deve mesmo ser imutável com movimento, sendo propriedade de apresentação? Ela condiciona a gravidade prática do R1 e do R2.

## Não testado

- `validate-docs.ps1`: `pwsh` ausente.
- DRE de mais de uma página impressa: a medição tem 1 página. A estrutura tem 19 linhas fixas, e cabeçalho repetido em várias folhas não foi exercitado.
- O job de CI em si: rodei o instrumento localmente, com exit 0.
- Comportamento do reparentamento na base anterior à DL-045 (R1): **inspecionado** no código (BL-261), não executado.
- Corrida entre a primeira classificação de um grupo (guarda A6a) e um lançamento concorrente numa descendente.
- Acessibilidade por teclado e leitor de tela da tela de classificação.
- Admin no navegador.
- Conciliação com zeramento trimestral ou anual: fora do escopo (RC-126).

## Classificação dos itens

| Item | Situação |
| --- | --- |
| A1 a A10 | Testado (ver tabela). A5: inspecionado, mais o par de testes da suíte. |
| Veto na tela: todas as listas, link, nada montado | Testado |
| Documento: item 51 e timbre | Testado (instrumento, exit 0, 1 página) |
| Documento sem controles de tela | Testado: defeito R5 |
| Tela de classificação: papéis, isolamento, recusa, nada gravado | Testado. Defeitos R3 e R6. |
| Navegação de competência | Testado. Defeito baixo R10. |
| Migração 0011: PostgreSQL, SQLite, dado `""`, reversão | Testado |
| Suíte, ruff, check, makemigrations | Testado |
| Mutação (47 aplicados) | Testado |
| Validação profissional contábil | Fora do escopo do auditor: é do Fred |

Esta reconferência não afirma ausência de outros defeitos nem conformidade legal. Ela registra o que foi medido na revisão `1e472c2`.

**Parecer final: REPROVADA.** O motivo é o R1 (alto): a correção do A6 fecha a única saída do veto do A2 e torna o Balanço (regressão da DL-034) e a DRE inemitíveis sem SQL. A isso se somam seis achados médios (R2 a R7) e cinco baixos (R8 a R12). A correção cabe ao `desenvolvedor-pleno` (R1 a R4, R7 no servidor) e ao `especialista-frontend` (R5, R6, R8 a R10, R7 na tela), encaminhada pelo `arquiteto-senior`. O R1(b) e o R12 dependem de decisão do arquiteto. Como AGENTS.md §3.1 não prevê terceira rodada, a forma de fechar isso é decisão do arquiteto.

Arquivos citados (caminhos absolutos na worktree auditada):

- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/models.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/services.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/views.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/views_web.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/templates/contabilidade/dre.html
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/static/css/base.css
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/tests/test_dl045_dre.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/apps/contabilidade/tests/test_dl045_fatia3_tela_da_dre.py
- /tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl045t/docs/agents/estado.md
