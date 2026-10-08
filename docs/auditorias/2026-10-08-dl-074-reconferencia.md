# Reconferência da DL-074 — 08/10/2026

**Auditor:** `auditor-qa` (Sonnet) · **Risco:** nível 1 (§3.1) · **Rodada:** última permitida (auditoria, uma correção, uma reconferência)

## Parecer: APROVADA COM RESSALVAS

- **A1 (bloqueador) e A2 (alta) estão fechados**, confirmados por execução e por contas feitas à mão, independentes do código.
- Não encontrei nenhum achado bloqueador ou de alta gravidade. A suíte completa dá o esperado (1 reprovação conhecida de ambiente).
- Ficam **ressalvas explícitas**, todas para o backlog:
  - **R1 (média):** a tela ainda grava e confirma "10,000" como R$ 10,00. É a mesma classe do A4.
  - **R2 (média):** o código novo do A3 tem duas lacunas de teste, isolamento entre empresas e concorrência.
  - R3 a R6 (baixas).
- **A validação normativa de HI-76 e HI-77 segue pendente.** Minha leitura do art. 22 da Res. CGSN 140 coincide com a implementação, mas só consultei fontes secundárias nesta rodada. HI-77 o próprio requisito já declara como "a confirmar". O Fred ou o contador-senior devem confirmar as duas antes de o pré-DAS (DL-075) consumir o resultado.

## Revisão auditada e ambiente

| Item | Valor |
| --- | --- |
| Cópia auditada | `/home/user/wt-audit074`, HEAD `71f371de0602d78496346847fbd03f6171cff5e8` (confere com `71f371d`) |
| Commits da correção | `644f488`, `2f452a7`, `71f371d` |
| `git status --porcelain` / `git diff --stat` ao final | 0 linhas / vazio |
| Ambiente | Python 3.13.16, PostgreSQL 16 local, sem `pwsh`, sem xdist |
| Onde rodaram sondas e mutantes | Em cópia extraída por `git archive` no scratchpad, com banco próprio. A cópia auditada ficou intacta. |
| Bancos criados | Todos removidos ao final |
| Não toquei | `/home/user/DataLedger` nem `/home/user/wt-dl075` |

**Commit `2f452a7`.** Confirmei que ele deixou `test_dl074_telas.py::test_rbt12_mostra_a_regra_aplicada_e_os_meses_pendentes` reprovando: 1 falhou e 40 passaram, e o teste ainda esperava o rótulo antigo do § 3º. O `71f371d` corrigiu o teste. O HEAD está verde. Só o commit intermediário quebra o build.

## Achados da rodada 1

| # | Gravidade original | Situação | Evidência executada |
| --- | --- | --- | --- |
| A1 | Bloqueador | **Fechado** | Sondas minhas, com esperado calculado à mão, todas conferem (tabela abaixo). Em C9, T1 e T2 o código devolvia 100.000, 30.000 e 11.000; agora devolve 300.000, 180.000 e 12.000. |
| A2 | Alta | **Fechado** | Ver abaixo. |
| A3 | Média | **Fechado** (lacunas de teste em R2) | Serviço, tela e API recusam o segundo lançamento igual: o serviço levanta `ReceitaErro`, a tela devolve 200 com mensagem e a API devolve 409. A mensagem nomeia a receita existente. Quatro threads simultâneas deram 1 `ok`, 3 `ReceitaErro` e 1 linha gravada, nas 3 rodadas. Receita igual em `empresa_a2` e em outro escritório é aceita. |
| A4 | Média | **Parcial** | O caso reportado ("10.000", "1.500", "1.234.567") é recusado na tela, com sugestão de vírgula. Formas corretas gravam o valor certo. Resíduo em R1. |
| A5 | Média | **Fechado**, sujeito à confirmação de HI-77 | Abertura 01/12/2026 com 100 mil e abertura 05/10/2026 com 150 mil não geram mais o aviso. Com RBT12 de 5,4 mi e acumulado dentro do teto, o aviso sai. |
| A6 | Média | **Fechado** (resíduos em R2 e R3) | Os 9 mutantes que estavam vivos agora morrem. O exemplo do Manual tem teste (`test_exemplo_do_manual_abertura_12_02_2018...`) e minha sonda M1 confere. |
| A7 | Baixa | **Fechado** | Confirmar mês futuro ou anterior à abertura é recusado na tela e na API. O mês corrente é aceito. O aviso `receita_antes_da_abertura` aparece no RBT12 e no painel. |
| A8 | Baixa | **Fechado** | O limite está declarado na migração `0003` e no docstring de `ConfirmacaoReceitaMensal`. |
| A9 | Baixa | **Parcial** | Ver R5. |

### Casos de referência (esperado à mão × obtido)

| Caso | Entrada | Esperado | Obtido |
| --- | --- | --- | --- |
| C9 | Abertura e opção 15/10/2025. Out 10 mil, nov 20 mil, dez 30 mil, jan 40 mil. | PA 02/26 (n=5) = 100.000/4×12 = **300.000**, § 3º, divisor 4. PA 01/26 = 60.000/3×12 = 240.000. PA 12/25 = 30.000/2×12 = 180.000. PA 10/25 = 10.000×12 = 120.000, § 2º. | Conferem |
| T1 | Abertura 03/11/2025. Nov 10 mil, dez 20 mil. PA 01/26. | 30.000/2×12 = **180.000** | Confere |
| T2 | Abertura 15/06/2025. 1.000 por mês de jun/25 a mai/26. | PA 05/26 (n=12) = 11.000/11×12 = **12.000**, § 3º. PA 06/26 (n=13) = 12.000, § 1º. PA 07/26 = 11.000. | Conferem |
| M1 (Manual) | Abertura 12/02/2018. Fev 10 mil, mar 0, abr 590 mil, mai 50 mil. | PA 02/18 = 120.000. PA 05/18 = 600.000/3×12 = **2.400.000**. | Conferem |
| Consulta | Abertura 10/03/2026. Mar 20 mil, abr 30 mil, mai 25 mil. | 240.000; 240.000; 300.000; 300.000. | Os literais do teste do desenvolvedor batem com a minha conta. O teste passa. |
| § 4º | Abertura 05/03/2025, opção 01/01/2026, 1.000 por mês. | PA 01/26 (n=11) e PA 02/26 (n=12) = 12.000, § 4º. PA 03/26 (n=13) = 12.000, § 1º. | Conferem |
| Abertura 31/12/2025 | Opção igual, 500 por mês. | PA 01/26 e PA 11/26 em § 3º; PA 12/26 (n=13) em § 1º. Todos 6.000. | Conferem |
| Abertura 2024-10, opção 2026 | 100 por mês. | PA 01/26 em § 1º = 1.200 | Confere |
| Mercado externo na virada | Abertura 15/10/2025. Ext 7.000,25 em nov/25, int 100 em jan/26. PA 02/26. | Ext 7.000,25/4×12 = 21.000,75. Int 300. Sem mistura. | Conferem |

Na tela, o painel do C9 mostra "§ 3º (2º ao 12º mês de atividade, abertura no ano da opção)", divisor 4 e RBT12 300.000,00. A API devolve `regra: § 3º`, `ano_opcao: 2025`, `apuravel: true`.

### A2 em detalhe

- `PATCH` de `data_abertura_cnpj`: **gestor 200 e administrador 200**, com a data gravada.
- Analista, paralegal e cliente recebem 403 e nada é gravado. Gestor de outro escritório recebe 404.
- Data futura, "31/12/2020", "2020-02-30", string vazia e datetime recebem 400.
- `PATCH` com `nome_fantasia` junto grava e a trilha guarda `valores_anteriores` e `valores_novos` em ISO.
- Os testes do desenvolvedor cobrem também `PUT`, limpar a data (null) e reenviar a mesma data.
- Observação: a data "1899-01-01" é aceita. Sem impacto de cálculo.

## Mutantes

Os mutantes rodaram sobre os 218 testes DL-074 (eram 165 na rodada 1; todos passam no HEAD). Foram 52 mutantes executados; um deles (R20) ficou **inconclusivo** e não conta. Dos 51 conclusivos, **44 morreram** e **7 sobreviveram**. Seis dos sobreviventes são lacunas de teste; N9c é praticamente equivalente.

### Os 9 sobreviventes da rodada 1

| Mutante | Resultado | Teste que mata |
| --- | --- | --- |
| M10a, M10b, M10c (filtro de empresa removido) | Morto (os três) | `test_composicao_e_confirmacao_isolam_empresas` |
| M05b (ignora o total guardado) | Morto | `test_insert_sql_de_receita_confirmada_em_mes_confirmado_vira_a_retificar` |
| M09 (`<=` virou `<` nos 20%) | Morto | `test_fronteiras_de_20_por_cento...` [4320000.00, 5760000.00] |
| M09b (`>` virou `>=`, limite) | Morto | mesmo teste [4800000.00] |
| M09c (`>` virou `>=`, sublimite) | Morto | mesmo teste [3600000.00] |
| T03 (estorno pode mudar `valor`) | Morto | `test_estorno_sql_que_tambem_troca_o_valor_e_recusado_pelo_banco` |
| T04 (DELETE de confirmação liberado) | Morto | `test_delete_de_confirmacao_pelo_queryset...` e `test_delete_sql_de_confirmacao...` |

### Mutantes novos

| Mutante | Resultado | Teste que mata |
| --- | --- | --- |
| N1: proporcional volta a exigir `ano_opcao == ano` (regressão do A1) | Morto | C9, T1 e T2 no teste parametrizado da virada |
| N2: rótulo § 3º decidido pelo ano do PA | Morto | C9, T1, T2 |
| N2b: rótulos § 3º e § 4º trocados | Morto (8) | consulta, § 4º, virada, Manual, tela |
| N3a e N3b: fronteira n≤13 e n≤11 | Mortos (2 cada) | `..._usa_s4_ate_o_12_mes_e_s1_no_13`, T2 |
| N4a: remove o § 4º | Morto | `..._usa_s4_ate_o_12_mes...` |
| **N4c**: abertura posterior ao ano da opção entra na proporcional | **Vivo** | Nenhum. Ver R4. |
| N12: `ano_opcao` igual ao ano do PA | Morto | C9, T1, T2 |
| N14: janela sem o 1º mês | Morto (17) | |
| N5a: § 5º compara com o teto proporcional (regressão do A5) | Morto | `test_a5_abertura_01_12_2026...` e `test_a5_abertura_05_10_2026...` |
| **N5b**: acumulado comparado com o teto cheio no § 5º | **Vivo** | Meu probe mata. Ver R3. |
| **N5c**: § 5º com `>=` | **Vivo** | Meu probe mata. Ver R3. |
| N13: teto cheio lido do sublimite | Morto | `test_a5_rbt12_acima_do_limite_cheio...` |
| N6a: efetivação reabre o mês errado (HI-75) | Morto (8) | |
| N6b: efetivação não reabre (HI-75) | Morto (7) | |
| N6d: reabertura sem `a_retificar` | Morto (11) | |
| N7 e N7b: trilha com `date` cru (regressão do A2) | Mortos | 4 e 2 testes de `test_dl074_data_abertura.py` |
| N8a: duplicata conta a receita estornada | Morto | |
| N8b, N8c, N8f: identidade sem suporte, sem valor ou sem mercado | Mortos | |
| **N8d**: duplicata sem filtro de empresa | **Vivo** | Meu probe mata. Ver R2. |
| **N8e**: sem trava da empresa antes da checagem | **Vivo** | Meu probe mata. Ver R2. |
| N9a e N9b: A4 desligado, ou regex com 4 dígitos | Mortos | |
| **N9c**: regex sem o `(?!\d)` | **Vivo** | Praticamente equivalente: só muda "10.0000", que o serviço trata igual. |
| N10a, N10b, N10c, N10d: variações da recusa do A7(b) | Mortos | |
| N11a, N11c, N11d: variações do aviso do A7(a) | Mortos | |
| **N11b**: varredura do aviso com `max` em vez de `min` | **Vivo** | Meu probe mata. Ver R3. |
| Regressões | Mortos | M13 (2027 no RBT12) em 3 testes; M12 (valor zero) em 2; M15 (rascunho entra) em 4; M16 (escrituração não efetivada entra) em 4; R17 (receita confirmada editável) em 1; R18 (tela de lançar sem checar papel) em 1; R19 (API de lançar sem checar papel) em 1 |
| R20 (troca de empresa na API) | Inconclusivo | O mutante era fraco: só há uma empresa na fixture. Não conta. |

## Achados novos

Nenhum é bloqueador ou de alta gravidade. Todos vão para o backlog.

### R1 — Média — A tela ainda aceita "1,000" ou "10,000" como R$ 1,00 ou R$ 10,00 e confirma

- **Requisito:** exatidão monetária; resíduo do A4.
- **Local:**
  - `apps/fiscal/receita.py:292-312` (`_valor_positivo` normaliza zeros à direita: `Decimal("10.000").normalize().as_tuple().exponent` é 1, então passa).
  - `apps/fiscal/views_web.py:1439-1459` (`_valor_do_formulario` só protege o ramo sem vírgula).
- **Reprodução** (`POST` na tela de lançar, `acao=confirmar`, gestor):

  | Digitado | Resultado |
  | --- | --- |
  | "1,000" | 302, gravado R$ 1,00, receita confirmada |
  | "10,000" | 302, gravado R$ 10,00, confirmada |
  | "1.000,000" | 302, gravado R$ 1.000,00 |

- **Limitação declarada do implementador.** O serviço, chamado direto, devolve "10.000" como 10,00 e "1.500" como 1,50. Percorri todas as portas de entrada:
  - **Tela:** protegida para "10.000" e similares. **Não** protegida para o formato com vírgula e 3 casas (a tabela acima).
  - **API:** protegida. O `DecimalField(decimal_places=2)` do DRF devolve 400 para "10.000", "1.500", "10,000" e "1.234.567".
  - **Outro código chamando o serviço:** hoje só existem a tela e a API como chamadoras (`grep` em `apps`). O risco é **latente** para chamadores futuros (importação, comando de gestão).
- **Impacto:** receita subdimensionada por fator 1.000 e confirmada em uma etapa. Quem copia valor de planilha em formato inglês ("10,000") cai nisso.
- **Correção recomendada:** em `_valor_positivo`, rejeitar mais de 2 casas decimais sem normalizar antes. Isso fecha a tela e o serviço de uma vez e torna o regex da tela redundante.
- **Verificação:** "1,000", "10,000", "1.000,000", "10.000" e "1.500" devem ser recusados no serviço, na tela e na API. "1.000,50", "10000" e "10,5" continuam aceitos.

### R2 — Média — O código novo do A3 tem duas lacunas de teste: isolamento entre empresas e concorrência

- **Requisito:** isolamento entre empresas; "requisição repetida não gera duplicidade silenciosa".
- **Local:** `apps/fiscal/receita.py` (checagem de duplicata em `lancar_receita_informada`).
- **Evidência:**
  - N8d (sem `empresa=travada` na checagem) e N8e (sem `travar_empresa` antes da checagem) sobrevivem a todos os testes.
  - Meu probe mata os dois.
  - O código real está correto: receita igual em `empresa_a2` e em outro escritório é aceita, e 4 threads iguais geram 1 linha.
- **Impacto:** uma regressão faria o lançamento de uma empresa ser recusado por receita de **outra empresa ou de outro escritório**, vazando o número e a data dessa receita na mensagem. Sem a trava, haveria duplicidade em concorrência.
- **Correção recomendada:** implementar os testes abaixo.
- **Verificação:** N8d e N8e passam a morrer.

```python
def test_receita_igual_em_outra_empresa_ou_escritorio_nao_bloqueia(empresa_a, empresa_a2, empresa_b, usuario_gestor_a, gestor_b):
    for e in (empresa_a, empresa_a2, empresa_b): fixar_inicio_de_uso(e, 2024, 1)
    _l(empresa_a, usuario_gestor_a); _l(empresa_a2, usuario_gestor_a); _l(empresa_b, gestor_b)
    assert ReceitaInformada.objects.count() == 3
# Mais um com transaction=True: 4 threads com Barrier chamando _l(empresa_a); exatamente 1 "ok", 3 ReceitaErro, 1 linha.
```

### R3 — Baixa — Fronteiras do § 5º e a varredura do aviso pré-abertura sem teste

Os mutantes N5b, N5c e N11b sobrevivem. Os testes abaixo, que rodei, os matam.

- **N5c:** abertura 05/01/2026, receita 400.000 em jan/26. O RBT12 é exatamente 4.800.000 e **não** deve haver aviso `rbt12_acima_do_limite_ano_dentro`.
- **N5b:** abertura 01/11/2026, nov 450.000 e dez 400.000. PA 12/26: RBT12 5.400.000, acumulado 850.000 contra teto proporcional de 800.000. **Não** deve haver aviso do § 5º (o aviso de limite excedido cobre o caso).
- **N11b:** abertura 10/02/2026, receita confirmada de 1.000 em nov/2025 (anterior à abertura), PA 10/2026. Deve haver `receita_antes_da_abertura` citando "11/2025".

### R4 — Baixa — Período do Simples iniciado em ano anterior ao da abertura cai em § 1º, apurável e sem aviso

- **Local:** `apps/fiscal/rbt12.py:294` (`abertura.year in (ano_opcao, ano_opcao - 1)`).
- **Reprodução:** Simples desde 01/01/2025, abertura 10/03/2026, mar 20 mil e abr 30 mil, PA 05/2026.
  - Obtido: § 1º, apurável, **50.000**, aviso só `limites_nao_apurados`.
  - Com a regra proporcional seria 25.000×12 = 300.000.
  - O mutante N4c sobrevive.
- **Impacto:** exige dado inconsistente (o período do Simples começa antes de a empresa existir). O erro seria silencioso e para menos. Não é regressão: antes da correção também caía em § 1º.
- **Correção recomendada:** recusar ou avisar quando `vigencia_inicio` do período for anterior à abertura (ano ou data), e testar.

### R5 — Baixa — Documentação ainda defasada (resíduo do A9)

- **`docs/agents/estado.md:192-209`:** diz "em correção" e "Correção única em andamento". A linha de base cita 5.638 aprovados e 408 arquivos, sobre `33972fc`. Hoje: 5.691 aprovados e 409 arquivos no `ruff format --check`. A regra do CLAUDE.md pede atualizar ao concluir a etapa.
- **`docs/planos/DL-074-receita-e-rbt12-do-simples.md:81-82` e `apps/fiscal/rbt12.py:361-362`:** ainda dizem que a faixa de 20% do sublimite cita o art. 81 "por analogia" e "hipótese HI-70, a conferir". O HI-70 em `requisitos.md` já foi corrigido (art. 12, §§ 1º e 4º), mas o plano e o texto do aviso não.
- **`apps/fiscal/tests/test_dl074_rbt12_referencia.py:13-14`:** o docstring diz que o exemplo do Manual **não** está no arquivo, mas ele está (`test_exemplo_do_manual...`, linha 749).
- **`docs/planos/DL-074-...md`:** não descreve os comportamentos novos do A3 (recusa de receita igual), do A4 (pedido de vírgula) e do A7 (mês futuro ou anterior à abertura recusado; aviso pré-abertura).
- Nada afirmado que o código não faça. É defasagem, não falsidade.
- **Verificação:** `apps/core/tests/test_documentacao_do_estado.py` verde (já passa) e leitura do estado.

### R6 — Baixa — Commit intermediário `2f452a7` deixou um teste reprovando

Corrigido pelo `71f371d`. O HEAD está verde; o problema só afeta bisect e leitura da história.

## Verificações executadas

| Verificação | Resultado |
| --- | --- |
| `pytest` completo (HEAD, Python 3.13.16) | **1 failed, 5691 passed, 53 skipped, 2 warnings, 4 subtests passed in 497,49 s.** A única reprovação é a conhecida de ambiente: `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. As 2 warnings são `RemovedInDjango2028Warning` em `test_dl016_f6_check_empresa_not_null.py`, preexistentes. |
| Testes DL-074 (fiscal e empresas) | 218 passaram em cerca de 20 s |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 409 files already formatted |
| `manage.py check` | no issues |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate` em banco vazio | OK |
| `migrate fiscal 0002` (reverte 0003) e `migrate fiscal` | OK. As tabelas somem e os dois gatilhos `trg_receita_informada_imutavel` e `trg_confirmacao_mes_imutavel` somem e voltam. |
| `migrate empresas 0015` (reverte 0016) e `migrate` | OK. A coluna `data_abertura_cnpj` some e volta. `migrate --check` dá rc=0. |
| Checagem equivalente a `validate-docs` nos 4 `.md` alterados | Título, nova linha final, espaços no fim e links: OK |

## Regressões da correção

Verificadas por sondas na tela e na API, com os resultados abaixo (inclui também mutantes R17 a R19).

| Papel | API: GET receita e RBT12 | API: POST lançar, confirmar mês, estornar | Tela: painel | Tela: POST lançar e confirmar |
| --- | --- | --- | --- | --- |
| Cliente | 403 | 403 | 403 | 403 |
| Paralegal | 200 | 403 | 200 | 403 |
| Analista | 200 | passa para o serviço (201/200) | 200 | 302 |
| Gestor de outro escritório | 404 | 404 | 404 | 404 |
| Gestor | 200 | segue o serviço | 200 | 302 |

- Isolamento: receita igual em outra empresa ou escritório é aceita (probe). Sem vazamento na mensagem.
- Imutabilidade da receita confirmada: o mutante R17 morre (`test_save_de_receita_confirmada_e_recusado_e_nada_muda`), e os gatilhos T01 a T04 estão cobertos.
- 2027: recusado no RBT12 e na tela (M13 morto).

## Classificação dos itens

| Item | Classe |
| --- | --- |
| A1, A2, A3, A5, A6, A7, A8 | Implementado, Inspecionado e Testado (executei) |
| A4 | Testado; resíduo em R1 |
| A9 | Inspecionado; parcial (R5) |
| Mutantes e probes (51 conclusivos) | Testado, em cópia descartável |
| Suíte completa, linters, migrações e reversões | Testado |
| Concorrência do A3 | Testado com threads (3 rodadas); depende de temporização |
| Texto oficial do art. 22 da Res. CGSN 140 | **Não testado.** Vi apenas fontes secundárias nesta rodada; a rodada 1 leu o PDF consolidado. |
| HI-76 e HI-77, validação profissional | **Não verificado** (cabe ao Fred ou contador-senior) |
| Suíte em Python 3.14 | Não testado (só 3.13) |
| `pwsh ./scripts/validate-docs.ps1` | Não testado (sem `pwsh`); substituído pela checagem equivalente |
| Jobs do GitHub e proteção de branch | Não testado (fora do alcance) |
| Interface em navegador real (contraste, teclado) | Não testado; só HTML via cliente de teste |
| Backup e restauração | Fora do escopo |

## Arquivos relevantes

- `/home/user/wt-audit074/apps/fiscal/rbt12.py` (linhas 284-299, 403-436, 516-585)
- `/home/user/wt-audit074/apps/fiscal/receita.py` (linhas 292-312, 390-411, 628-690)
- `/home/user/wt-audit074/apps/fiscal/views_web.py` (linhas 1431-1459, 1806-1822)
- `/home/user/wt-audit074/apps/empresas/views.py` (linhas 95-132)
- `/home/user/wt-audit074/docs/agents/estado.md` (linhas 192-209)
- `/home/user/wt-audit074/docs/planos/DL-074-receita-e-rbt12-do-simples.md` (linhas 81-82)
- `/home/user/wt-audit074/apps/fiscal/tests/test_dl074_rbt12_referencia.py` (linhas 13-14)

Os artefatos descartáveis (probes, specs de mutantes e log da suíte) estão no scratchpad, em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/`.

Este parecer é de software. Não substitui a validação contábil e legal das regras HI-76 e HI-77.
