# Reconferência DL-043: parâmetros contábeis por empresa e zeramento do resultado

**Data:** 2026-09-26
**Auditor:** `auditor-qa`. Trabalhei de forma independente: não corrigi nada e não alterei testes.
**Nível de risco:** 1 (AGENTS.md §3.1). Esta é a reconferência única depois da correção da [rodada 1](2026-09-26-dl-043-rodada-1.md).
**Parecer:** **REPROVADA**. A correção introduziu uma regressão de gravidade **alta** (achado R1): a trava por empresa usa `FOR UPDATE` e entra em deadlock com o `criar_lancamento` comum. Na medição por HTTP real, isso deu **HTTP 500 em 16 de 30 rodadas concorrentes**. Os dez achados B1–B10 da rodada 1 estão fechados.

## Revisão auditada

- Worktree `wt-dl043c`, branch local `dl043-correcao`, **HEAD `80ac46f`**, conferido antes e depois da auditoria.
- Commits cobertos desde a rodada 1:
  - `636b44b`: correção de B1–B10.
  - `10e4e64`: merge das telas `06840b1`.
  - `33284f1`: integração entre tela e serviço.
  - `80ac46f`: zeramento posterior estornado deixa de bloquear.
- Banco PostgreSQL 16 próprio: `dataledger_qa43` e os respectivos `test_*`.
- Mutações e experimentos rodaram em **cópias descartáveis** extraídas por `git archive 80ac46f` (`qa43mut` e `qa43exp`), com bancos próprios (`dataledger_qa43m` e `dataledger_qa43x`).
- Limpeza: bancos, cópias e arquivos temporários foram removidos no fim.
- Efeitos colaterais na versão auditada: `git status --short` e `git diff --stat` saíram **vazios** no início e no fim. Havia um `db.sqlite3` de 0 byte na worktree, com data de 11:35, anterior a esta auditoria e ignorado pelo `.gitignore`. Não fui eu que criei e não mexi nele.

## Comandos executados (critério 9)

| Comando | Resultado |
| --- | --- |
| `pytest --create-db -q` (suíte completa, PostgreSQL 16) | `1 failed, 2807 passed, 45 skipped, 2 warnings, 4 subtests passed in 118.26s` |
| Falha isolada | `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É falha **de ambiente e preexistente**: o `.venv` local é Python 3.13 e a CI usa 3.14. Não tem relação com a DL-043. |
| `pytest` nos cinco arquivos `test_dl043_*.py` | `121 passed in 12.07s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `282 files already formatted` (só a variante `--check`; o formatador não foi rodado) |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `migrate` em PostgreSQL vazio | OK até `contabilidade.0009_gatilho_sem_sobreposicao_de_vigencia`, `fiscal.0001` e `sessions.0001`. O gatilho `trg_parametro_contabil_sem_sobreposicao` está presente em `pg_trigger`. |
| `migrate` em SQLite limpo (arquivo no scratchpad) | OK até `sessions.0001` |
| Linha de base na cópia de mutação (`apps/contabilidade/tests/`) | `1196 passed, 2 skipped in 64.12s` |
| `pwsh ./scripts/validate-docs.ps1` | **Não testado**: `pwsh` não está instalado neste ambiente. |

## Achados da rodada 1: estado

| Achado | Estado | Evidência (Testado, salvo indicação) |
| --- | --- | --- |
| **B1** hierarquia dobra o resultado | **Fechado** | Plano "7" → "7.1" → "7.1.01", todas aceitando lançamento, com 100,00, 200,00 e 300,00. A prévia gera três itens pelo saldo **próprio** (100, 200, 300) e contrapartida de 600,00. Depois do zeramento, o balancete em 31/03 fica `{'1.1': 600.00, '2.9.2': 600.00}` e as três contas de receita ficam zeradas. A sintética legada é recusada: o mutante M14 morre (ver abaixo). |
| **B2** fora de ordem, complemento tardio e concorrência | **Fechado** | **Fora de ordem:** zerar abril e depois março dá `ZeramentoForaDeOrdem` no POST e na prévia, com banco inalterado. Em 30/04, Lucros ficam em 150,00 e a receita zerada. **Complemento tardio** (sequência original com 30,00 em 20/03): o complemento de março é recusado; em 31/05, Lucros ficam em 180,00 e a receita zerada. **Concorrência março × abril:** o teste do desenvolvedor, com 15 rodadas e `threading.Barrier`, passou na suíte completa. |
| **B3** quatro 500 previsíveis | **Fechado** (os quatro casos originais) | **205 contas:** API 200 e tela 200. A etapa 1 é dividida em 2 lançamentos balanceados, e Lucros = 205,00. **Caso misto com 260 contas** (receitas de 1,01 e despesas de 2,37): 2 partes, cada uma com D = C e no máximo 200 partidas; prejuízo de 31,46 igual ao da prévia. **Mês futuro:** API 400. Na tela, para 09, 10 e 11/2026, a prévia mostra mensagem (200) e o POST redireciona com mensagem (302); nenhum lançamento é gravado. **Chave ocupada:** 409 (só alcançável forçando a situação com `monkeypatch`). **`lock_timeout`:** 409. ⚠️ Surgiu um **500 novo** por outro caminho: ver R1. |
| **B4** chave `zeramento:` forjada | **Fechado no PostgreSQL** | API com ANALISTA: 400 e banco inalterado (teste do desenvolvedor). Tela `lancamento_novo` com o campo `chave_idempotencia=zeramento:…`: **400**, 0 lançamento gravado. Não existe importação de lançamento contábil: `criar_lancamento` só é chamado de `services.py`, `views.py` e `views_web.py`. Ressalva em SQLite: ver R4. |
| **B5** custo quadrático | **Fechado** | Prévia: **8 consultas** com 10, 300 e 1.000 contas (0,012 s, 0,019 s e 0,041 s). Execução: 57, 360 e 1.112 consultas (0,047 s, 0,153 s e 0,619 s), ou seja, linear e não mais quadrática. Com 800 contas, 0,476 s e 5 partes. |
| **B6** mutantes sobreviventes | **Parcial** | Os oito mutantes da rodada 1 morrem, mas as validações novas do B7 e a trava do B10 não têm teste que as proteja. Ver a seção **Mutações**. |
| **B7** destino devedor, inativo ou com filhas | **Fechado no código, sem teste** | HTTP com ADMINISTRADOR: Lucros devedora dá 400 ("precisa ter natureza credora"); resultado inativa dá 400; resultado com filha dá 400. Banco inalterado nos três casos. Porém os mutantes N14, N15 e N16 **sobrevivem à suíte inteira**. O plano afirma que "Coberto pelos testes de `test_dl043_parametro_contabil.py`", e isso **não se confirma**. |
| **B8** trilha sem IP | **Fechado** (API e tela) | API: teste do desenvolvedor. Tela: POST com `REMOTE_ADDR=10.9.8.7` grava `endereco_ip = 10.9.8.7` no `RegistroAuditoria` `zeramento.resultado`. Os mutantes N10 e N11b morrem. |
| **B9** sem admin | **Fechado** (Inspecionado) | Decisão registrada na DE-078, item 7. |
| **B10** corrida entre vigência e zeramento | **Fechado** | Três rodadas com threads: zeramento de março segurando a transação e, em paralelo, `registrar_parametro_contabil` com início em 01/03. As três terminaram com `VigenciaParametroContabilConflitante`, sem nenhuma dupla aceitação. O mutante N6 (tirar a trava) **sobrevive**: não há teste. |
| **P1** | Pendência de domínio | Registrada como HI-26 e ampliação da PE-38. **Não verificada** por mim; a decisão é do Fred. |

## Mutações

Cada mutação foi aplicada na cópia descartável e revertida com `git checkout` (`git status` limpo no fim). Primeiro rodei `apps/contabilidade/tests/` com `-x`. Os sobreviventes foram depois rodados contra `apps/` inteiro, que tem 2.687 testes. Os 166 testes de `scripts/` ficaram de fora dessa segunda rodada e não tocam a contabilidade. O teste de ambiente foi desmarcado com `--deselect`.

### Mutantes da rodada 1

| Mutante | Resultado | Teste que matou |
| --- | --- | --- |
| M4: sem checagem de competência ABERTA | morto | `test_m4_competencia_encerrada_sem_movimento_recusa_sem_trilha_nem_gravacao` |
| M12: vigência ignorando `vigencia_fim` | morto | `test_m12_zerar_apos_vigencia_fim_sem_sucessora_e_recusado` |
| M14a: sintética com saldo não recusada (`if False`) | morto | `test_b1_sintetica_legada_com_saldo_proprio_recusa_sem_gravar` |
| M14b: sintética com saldo pulada em silêncio (`continue`) | morto | `test_b1_sintetica_legada_com_saldo_proprio_recusa_sem_gravar` |
| M16: sem `registrar()` no zeramento | morto | `test_b8_trilha_do_zeramento_tem_ip_usuario_e_escritorio` |
| M17: sem `registrar()` no parâmetro | morto | `test_m17_trilha_do_parametro_contabil_e_gravada` |
| M20: encerrar vigência com início futuro | morto | `test_m20_encerrar_vigencia_com_inicio_futuro_e_409_sem_gravar` |
| M22: anual aceitando junho | morto | `test_m22_anual_recusa_cada_mes_diferente_de_dezembro[6]` |
| M24: `_conta_da_empresa_ou_400` sem filtro de empresa | morto | `test_m24_conta_de_outra_empresa_tem_a_mesma_mensagem_que_conta_inexistente` |

### Mutantes novos, sobre as mudanças recentes

| Mutante | Resultado | Teste que matou |
| --- | --- | --- |
| N1: sem o filtro `estornos__isnull=True` | morto | `test_integracao_zeramento_fora_de_ordem_recupera_com_estorno_e_refazer` |
| N2: filtro invertido (`estornos__isnull=False`) | morto | `test_b2_zerar_fora_de_ordem_e_recusado_sem_gravar` |
| N3: divisão RC-79 sem reservar a vaga da contrapartida | morto | `test_b3_5a_duzentas_contas_de_resultado_divide_a_etapa1_sem_500` |
| N4: contrapartida do grupo com lado invertido | morto | `test_b1_hierarquia_zera_pelo_saldo_proprio_sem_dobrar` |
| N5: sem trava de empresa em `zerar_resultado` | morto | `test_b2_concorrencia_entre_meses_diferentes_nunca_conta_em_dobro` |
| N6: sem trava de empresa em `registrar_parametro_contabil` | **sobreviveu (2672 passed)** | nenhum (B10 sem teste) |
| N7: `data__gt` trocado por `data__gte` na ordem cronológica | morto | `test_integracao_novo_zeramento_de_abril_e_idempotente` |
| N8: tela sem `CompetenciaOperacaoRecusada` | morto | `test_recusas_novas_do_zeramento_viram_mensagem_na_tela_sem_gravar[EmpresaTravadaPorOutraOperacao]` |
| N9: tela sem `LancamentoInvalido` | morto | `test_recusas_novas_do_zeramento_viram_mensagem_na_tela_sem_gravar[LancamentoInvalido]` |
| N10: tela sem `request=request` | morto | `test_zeramento_pela_tela_grava_ip_na_trilha` |
| N11b: API sem `request=request` | morto | `test_b8_trilha_do_zeramento_tem_ip_usuario_e_escritorio` |
| N12: sem a recusa do prefixo reservado | morto | `test_b4_chave_reservada_e_400_e_nao_bloqueia_o_gestor` |
| N13: sem a checagem HI-25 | morto | `test_b3_5b_mes_futuro_e_400_sem_gravar` |
| N14: sem exigir Lucros credora | **sobreviveu (2672 passed)** | nenhum |
| N15: sem exigir destino ativo | **sobreviveu (2672 passed)** | nenhum |
| N16: sem exigir destino folha | **sobreviveu (2672 passed)** | nenhum |
| N17: saldo consolidado no lugar do próprio (volta do B1) | morto | `test_b1_hierarquia_zera_pelo_saldo_proprio_sem_dobrar` |
| N18: complemento por contagem de lançamentos | sobreviveu | **Equivalente, não é lacuna.** Por construção, a contagem é sempre maior ou igual ao maior complemento mais um, então nunca colide. |
| N19: prévia sem a recusa de fora de ordem | morto | `test_previa_fora_de_ordem_mostra_a_recusa_sem_botao_de_gravar` |

## Casos de referência recalculados à mão (Testado)

Todos rodaram com zeramento mensal em 06/2026, conferindo o balancete em 30/06 e D = C em cada lançamento de zeramento.

| Caso | Conta à mão | Gravado |
| --- | --- | --- |
| Lucro | 10.000,00 − 4.000,00 | Lucros 6.000,00 |
| Prejuízo | 3.000,00 − 5.000,00 | (-) Prejuízos 2.000,00 |
| Zero | 5.000 − 5.000 | Etapa 1 sem contrapartida; sem etapa 2; PL intocado |
| Só receitas | 777,77 | Lucros 777,77 |
| Só despesas | 333,33 | (-) Prejuízos 333,33 |
| Retificadora | 10.000 − 1.000 (devolução devedora) − 3.000 | Lucros 6.000,00 |
| Centavos | 100,01 − 33,34 | Lucros 66,67 |

Em todos os casos, receita, despesa, retificadora e "resultado do exercício" terminam com saldo zero.

## Brechas do filtro `estornos__isnull=True` (Testado)

- Estornar **só a etapa 2** de abril: março continua recusado. Correto.
- Estornar **só a etapa 1** de abril: março continua recusado. Correto.
- Estornar **só a parte 0** de uma etapa 1 dividida: o mês anterior continua recusado. Correto.
- **Estorno do estorno:** recusado por `estornar_lancamento` ("já é um estorno"). A brecha não existe.
- Caminho de recuperação **pela porta do produto**: tem problema, ver R2.

## Travas, deadlock e fechamento de competência (Testado)

| Cenário | Resultado |
| --- | --- |
| `encerrar_competencia(abril)` segurando a transação, com `zerar_resultado(abril)` em paralelo (3 rodadas) | Serializa corretamente: zerar recebe `CompetenciaEncerrada` (409). **Sem deadlock.** |
| `zerar_resultado(abril)` e depois `encerrar_competencia(abril)` (3 rodadas) | Serializa: os dois concluem, com 3 lançamentos. **Sem deadlock.** |
| `criar_lancamento(abril)` e `zerar_resultado(abril)` concorrentes | **Deadlock**: ver R1. |

## Telas (Testado)

Matriz de papéis. Colunas: GET parâmetros / POST parâmetros / POST encerrar / GET prévia / POST zerar. Banco inalterado em todas as linhas (contagens de lançamento, item, trilha, competência e parâmetro).

| Papel | Resultado |
| --- | --- |
| ANALISTA | 200 / 403 / 403 / 403 / 403 |
| FINANCEIRO | 200 / 403 / 403 / 403 / 403 |
| PARALEGAL | 200 / 403 / 403 / 403 / 403 |
| CLIENTE | 403 / 403 / 403 / 403 / 403 |
| Sem vínculo | 200 nas cinco (página "sem escritório"), banco inalterado |

- **Isolamento:** ADMINISTRADOR de outro escritório recebe **404 nas cinco rotas**, banco inalterado.
- **Prévia não grava:** as contagens ficam iguais depois do GET.
- **Confirmação grava o que a prévia mostrou:** receita 100,00 e despesa 33,34. A prévia mostra 100,00, 33,34 e 66,66, e o POST grava Lucros 66,66.
- **Competência entregue:** a prévia aparece sem o botão de gravar, e o POST redireciona com mensagem (302).
- **Nenhuma recusa vira 500:** vale para as recusas mapeadas. **Não vale** para o deadlock de R1 (3 de 30 rodadas com 500 na própria tela de zeramento).

## Achados novos

### R1. ALTA: a trava por empresa (`FOR UPDATE`) entra em deadlock com `criar_lancamento` e devolve HTTP 500, na API e na tela (regressão da correção)

1. **Gravidade:** alta.
2. **Requisito afetado:** DE-078, item 5 ("nenhum erro previsível vira 500"); critério 6; o próprio B3; e a porta de escrituração comum (lançamento), que é anterior à DL-043.
3. **Onde:** `apps/contabilidade/services.py`, l. 1522–1523 (`Empresa.objects.select_for_update().get(pk=empresa.pk)`) e l. 2356–2369 (ordem: empresa primeiro, competência depois).
4. **Evidência (Testado, PostgreSQL):**
   - **Mecanismo** (confirmado em `pg_constraint`):
     - As FKs do Django são `DEFERRABLE INITIALLY DEFERRED`. No COMMIT, o `criar_lancamento` faz `SELECT … FROM empresas_empresa … FOR KEY SHARE`.
     - `FOR KEY SHARE` conflita com o `FOR UPDATE` da trava de empresa.
     - Sequência do deadlock:
       - T1 (`criar_lancamento` de abril) segura `FOR SHARE` na competência de abril.
       - T2 (`zerar_resultado` de abril) pega `FOR UPDATE` na empresa e espera a competência.
       - T1, no commit, espera `KEY SHARE` na empresa, que está com T2.
   - **HTTP real, sem espera artificial:** 30 rodadas com `Barrier`. ANALISTA faz `POST /lancamentos/` em 20/04; GESTOR faz `POST /zeramento/2026/4/`. Resultado: **16 de 30 rodadas com 500** (`OperationalError: deadlock detected`): 8 no lançamento e 8 no zeramento.
   - **Tela de zeramento com lançamento pela API:** **16 de 30**: 13 no lançamento e 3 na tela.
   - **Serviço, com a janela alargada em 0,3 s:** 5 de 5 com deadlock.
   - **Efeito correlato:** com o zeramento segurando a empresa por 1,5 s (plano grande ou banco lento), `criar_lancamento` em **outro mês** falha no COMMIT com `canceling statement due to lock timeout … FOR KEY SHARE OF x` em 3 de 3 rodadas, como `OperationalError` cru, sem tradução. Qualquer INSERT com FK para a empresa (conta, competência, nota fiscal) espera o zeramento.
   - Antes da correção isso não acontecia: a trava era só de competência, e `KEY SHARE` é compatível com ela.
5. **Impacto:**
   - O analista que lança no mês em que o gestor zera recebe erro 500, e o lançamento não é gravado.
   - O gestor recebe 500 no zeramento.
   - Não há dano contábil (rollback). Mas é 500 imprevisível na porta principal de escrituração, e a DE-078 pedia exatamente o contrário.
6. **Correção recomendada:**
   - Usar `select_for_update(no_key=True)` (`FOR NO KEY UPDATE`), que continua serializando zeramento, vigência e encerramento de vigência entre si, mas não conflita com `FOR KEY SHARE`.
   - **Experimento na cópia descartável, com só essa troca:**
     - race HTTP: **0 de 30** rodadas com 500;
     - serviço com janela alargada: 5 de 5 sem erro;
     - outro mês com 1,5 s: 3 de 3 sem erro;
     - `test_b2_concorrencia_entre_meses_diferentes_nunca_conta_em_dobro` e `test_b3_5d_lock_timeout_real_na_empresa_e_409_sem_500` continuam passando (12 passed na seleção).
   - Defesa em profundidade: traduzir SQLSTATE 40P01 para 409 onde `_e_estouro_de_lock_timeout` já traduz 55P03.
   - Responsável sugerido: `desenvolvedor-pleno`.
7. **Como verificar:** teste `django_db(transaction=True)` com duas threads e `Barrier`: `POST /lancamentos/` em abril contra `POST /zeramento/2026/4/`, pelo menos 30 rodadas. Esperado:
   - nenhum 500;
   - lançamento 201;
   - zeramento 200 ou 409;
   - Lucros iguais à soma das receitas zeradas.

   Variante: thread que segura a transação de `criar_lancamento` por 0,3 s antes do commit, esperando zero `OperationalError`.

### R2. MÉDIA: o caminho de recuperação recomendado ("estorne o zeramento posterior e refaça na ordem") não é executável pelo produto, e seguir a porta real distorce o resultado dos períodos

1. **Gravidade:** média.
2. **Requisito afetado:** DE-078, item 2; RC-101/RC-103; RC-78 (data do estorno decidida pelo servidor); critério 4 (variação do PL igual ao resultado **do período**).
3. **Onde:**
   - A mensagem de `ZeramentoForaDeOrdem` (`services.py`, l. 1576–1584) manda datar o estorno "até o último dia do período estornado".
   - `EstornarLancamentoView` (`views.py`, l. 858–873) recusa `data` no corpo, e **não há estorno pela tela** (`views_web.py` não chama `estornar_lancamento`).
   - O teste `test_integracao_zeramento_fora_de_ordem_recupera_com_estorno_e_refazer` só passa porque chama `estornar_lancamento(..., data=date(2026, 4, 30))` direto no serviço.
4. **Evidência (Testado):**
   - `POST /estornar/` com `{"data": "2026-04-30"}` responde **400** ("Campo(s) não reconhecido(s) no estorno: data").
   - Cenário pela porta real:
     - Receita de 300,00 em 31/03 e de 200,00 em 30/04.
     - Zerar abril (500,00).
     - Estornar as duas etapas pela API: os estornos ficam datados em **26/09/2026**.
     - Zerar março e depois abril.
   - Resultado:
     - O abril refeito grava **prejuízo de 300,00** (C receita 300, D resultado 300, destino `prejuizos_acumulados`), quando o resultado real de abril é lucro de 200,00.
     - Balancete em 30/04 e 31/08: `2.9.2` (Lucros) 800,00 e `2.9.3` (Prejuízos) 300,00. O líquido de 500,00 está certo, mas as duas contas estão infladas.
     - Em 26/09: receita `3.1` com **500,00 credores** vindos do estorno. O zeramento de setembro vai tratá-los como resultado de setembro.
5. **Impacto:**
   - Sem contagem em dobro no acumulado.
   - Mas o resultado de abril (−300 no lugar de +200) e o de setembro (+500 fictícios) ficam errados, e as duas contas do PL ficam infladas.
   - A mensagem orienta uma ação que o produto não permite. O próprio desenvolvedor registrou a ressalva como "não decidida" no plano (l. 240).
6. **Correção recomendada** (decisão do `arquiteto-senior` e, no que é rotina, do Fred):
   - Ou oferecer um estorno **específico de zeramento**, datado na data do zeramento estornado, com competência aberta e trilha.
   - Ou mudar a orientação: nunca estornar, e deixar o resíduo ser absorvido pelo próximo período.
   - Ou recusar zerar um mês posterior enquanto o anterior não foi zerado.
   - Em qualquer caso, a mensagem não pode pedir uma data que nenhuma porta aceita.
7. **Como verificar:** teste de ponta a ponta **só pelas portas HTTP** (zerar, estornar, refazer), conferindo que o resultado de cada período e os saldos de Lucros e Prejuízos em 30/04 e no fim do mês corrente batem com os lançamentos de origem.

### R3. BAIXA: validações do B7 e trava do B10 sem nenhum teste

1. **Gravidade:** baixa.
2. **Requisito afetado:** AGENTS.md (toda regra aplicável vira teste); B6.
3. **Onde:**
   - `services.py`, l. 1673–1682 (folha e ativa), l. 1702–1705 (Lucros credora) e l. 1707–1708 (trava).
   - Plano, l. 165–170, que afirma cobertura inexistente.
4. **Evidência:** N6, N14, N15 e N16 sobrevivem a `apps/` inteiro (`2672 passed`).
5. **Impacto:** uma regressão silenciosa reabre B7 e B10.
6. **Correção recomendada:** acrescentar os testes 3 e 4 propostos abaixo e corrigir a frase do plano. Responsável sugerido: `desenvolvedor-pleno`.
7. **Como verificar:** refazer N6, N14, N15 e N16; os quatro devem morrer.

### R4. BAIXA: em SQLite, o prefixo reservado é contornável com maiúsculas

1. **Gravidade:** baixa. O produto roda em PostgreSQL; o SQLite é usado em desenvolvimento e nas verificações de migração.
2. **Requisito afetado:** DE-078, item 6 (B4).
3. **Onde:**
   - `services.py`, l. 690–699: a recusa usa `startswith` do Python, que diferencia maiúsculas.
   - l. 1568–1573 e l. 1726–1730: as buscas usam `chave_idempotencia__startswith`, e em SQLite o `LIKE` não diferencia maiúsculas.
4. **Evidência (Testado):** chave `ZERAMENTO:<id>:2026-09:etapa2:0` aceita por `criar_lancamento`.
   - Em SQLite: zerar março é recusado como "fora de ordem" e a vigência de 01/09 é recusada.
   - Em PostgreSQL: as duas operações passam normalmente.
5. **Impacto:** o ataque do B4 volta em SQLite.
6. **Correção recomendada:** recusar o prefixo sem diferenciar maiúsculas (`chave.lower().startswith("zeramento:")`), ou identificar o zeramento por campo estruturado (CON-02).
7. **Como verificar:** o mesmo teste com `ZERAMENTO:` e `Zeramento:`, esperando 400.

### R5. BAIXA: a tela de resultado mostra só o primeiro lançamento da etapa 1 quando ela é dividida

1. **Gravidade:** baixa.
2. **Requisito afetado:** plano, "mensagem do que foi gerado"; rastreabilidade.
3. **Onde:** `templates/contabilidade/zerar_resultado.html`, l. 49–57 (usa `resultado.lancamento_etapa1`, e não `lancamentos_etapa1`).
4. **Evidência (Testado):** com 205 contas, gravou os lançamentos 216 e 217 na etapa 1; o HTML cita só o "nº 216".
5. **Impacto:** o contador não vê pela tela o lançamento das partes 2 a N.
6. **Correção recomendada:** listar `resultado.lancamentos_etapa1`. Responsável sugerido: `especialista-frontend`.
7. **Como verificar:** teste de tela com 205 contas, esperando os dois números no HTML.

### R6. BAIXA: documentação interna e nome de teste contradizem a permissão da prévia

1. **Gravidade:** baixa.
2. **Onde:**
   - O comentário de bloco em `views_web.py`, l. 3803, diz que a prévia exige só `_pode_ler`.
   - O teste `test_analista_le_previa_mas_nao_confirma` (`test_dl043_fatia3_telas.py`, l. 515) afirma **403** no GET.
3. **Evidência:** o ANALISTA recebe 403 na prévia. Isso está coerente com a API (`PodeFecharCompetencia`) e com o `mapa-de-telas.md` ("ADMINISTRADOR, GESTOR").
4. **Impacto:** engana o próximo leitor sobre quem lê a prévia.
5. **Correção recomendada:** alinhar o comentário e o nome do teste.
6. **Como verificar:** inspeção.

### Observação (Inspecionado, sem gravidade atribuída)

A confirmação não fica vinculada à prévia: o POST recalcula, e o contrato só leva `ano`, `mes` e `confirmar_zeramento`. Um lançamento gravado entre a prévia e a confirmação muda o que é gravado sem aviso, e a tela de resultado não mostra os valores. Isso já está documentado como leitura "best-effort". Fica o registro para decisão.

## Casos de teste propostos (para o responsável implementar)

1. **R1, deadlock:** o descrito em R1.7 (30 rodadas HTTP, zero 500), mais a variante com a janela de `criar_lancamento` alargada.
2. **R2, recuperação pela porta HTTP:** o descrito em R2.7.
3. **B7 via HTTP:** Lucros devedora, destino inativo e destino com filha. Esperado: 400 com mensagem e banco inalterado (mata N14, N15 e N16).
4. **B10, concorrência:** zeramento de março segurando a transação por 0,3 s contra registro de vigência com início em 01/03. Esperado: `VigenciaParametroContabilConflitante` em todas as rodadas (mata N6).
5. **R4:** chave com `ZERAMENTO:` e `Zeramento:`. Esperado: 400.
6. **R5:** resultado na tela com etapa dividida, listando todos os lançamentos.

## O que ficou Não testado

- `scripts/validate-docs.ps1` (sem `pwsh` no ambiente).
- Comportamento em SQLite além de `migrate` e do experimento de R4.
- Volume real: acima de 1.000 contas de resultado, ou muitos lançamentos por conta.
- Deadlock entre zeramento e `estornar_lancamento`. É o mesmo padrão de R1 (`FOR SHARE` na competência seguido de FK no commit), avaliado só por inspeção.
- Validação profissional contábil dos casos, de P1/HI-26 e de R2. Auditoria de software não substitui essa validação.
- HI-24 e HI-25 seguem como hipóteses, sem confirmação do Fred.

## Parecer

**REPROVADA.**

- Os dez achados da rodada 1 estão fechados: B1, B2, B3, B4, B5, B7, B8, B9 e B10 reproduzidos e fechados. B6 está parcial, porque as regras novas do B7 e a trava do B10 não têm teste.
- Os casos de referência batem à mão.
- As telas respeitam permissão e isolamento.
- A correção, porém, introduziu **R1 (alta)**: a trava por empresa em `FOR UPDATE` produz deadlock e HTTP 500 em 16 de 30 rodadas concorrentes, inclusive na porta comum de lançamento.
- A correção indicada tem uma linha (`no_key=True`) e foi validada em cópia descartável: 0 de 30.
- **R2 (média)** exige decisão sobre o caminho de recuperação antes de a mensagem continuar orientando o usuário a fazer algo que o produto não permite.

Encaminhamento: R1, R3 e R4 ao `desenvolvedor-pleno`, e R5 ao `especialista-frontend`, pelo `arquiteto-senior`. R2 e R6 são decisão do `arquiteto-senior`, e R2 inclui pergunta de rotina ao Fred depois de consultar o manual. Pelo §3.1 não há terceira rodada: cabe ao `arquiteto-senior` decidir como tratar R1, que é regressão de uma correção.

Arquivos relevantes (versão auditada):

- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/apps/contabilidade/services.py`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/apps/contabilidade/views.py`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/apps/contabilidade/views_web.py`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/templates/contabilidade/zerar_resultado.html`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/apps/contabilidade/tests/test_dl043_correcao_rodada1.py`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/apps/contabilidade/tests/test_dl043_fatia3_telas.py`
- `/tmp/claude-0/-home-user-DataLedger/75bf546e-56e5-5716-b925-854d35be8a0d/scratchpad/wt-dl043c/docs/planos/DL-043-parametros-contabeis-e-zeramento.md`
