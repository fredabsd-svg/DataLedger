# Auditoria DL-061 — reconferência

**Demanda:** DL-061, fatia 1 — DMPL (CTB-14 da DL-048). **Nível de risco:** 1. **Auditor:** `auditor-qa`, independente.
**Data:** 2026-10-01. **Rodada:** 2 de 2 (AGENTS.md §3.1: não há terceira rodada). Relatório da rodada 1: `docs/auditorias/2026-10-01-dl-061-rodada-1.md`.

## PARECER FINAL: APROVADO COM RESSALVAS

Os dois achados de gravidade alta da rodada 1 (N1 e N2) estão **fechados** com evidência executada, e os nove restantes (N3 a N11) também. Não encontrei falha bloqueadora nem de alta gravidade na versão reconferida. Encontrei quatro achados novos (M1 a M4), todos de gravidade média ou baixa, que ficam como **ressalvas explícitas** (seção 7), mais as decisões de contabilidade que dependem do Fred (seção 5). A ressalva mais relevante é a **M3**: o veto da DMPL não sai com estorno, e a mensagem manda fazer algo que não resolve. Fundamento completo na seção 10.

Auditoria de software não substitui a validação contábil do Fred. Este relatório não declara ausência de defeitos, segurança absoluta nem conformidade legal.

---

## 1. Versão e método

| Item | Valor |
| --- | --- |
| Commit reconferido | `805444277428789cb6cd436ce09b740ac1cc87da`, branch `claude/zealous-goldberg-jr5ggu` (confirmado por `git rev-parse HEAD`) |
| Versão da rodada 1 | `ebc8bdf`; plano `1209334` |
| Diff da correção | `git diff ebc8bdf..8054442`: 16 arquivos, +2.961 / −104 (`services.py` +403, `views_web.py` +171, dois arquivos de teste novos de 1.037 e 843 linhas) |
| Cópias descartáveis | `.../scratchpad/rec061` (mutação, ensaios e cenários; `git init` próprio) e `.../scratchpad/rec061_suite` (suíte completa e medição, sem mutação), ambas de `git archive 8054442` |
| Bancos | `dataledger_rec061`, `_rec061c` (suíte completa), `_rec061d`, `_rec061_web`, `_rec061_dif`, `_rec061_med` e os `test_…` derivados |
| Checkout principal | **não alterado**: `git status --short` e `git diff --stat` vazios depois de tudo (verificado) |
| Ambiente | Python 3.13.12, Django 6.1.1, PostgreSQL 16, Chromium 1194 (`/opt/pw-browsers`), poppler-utils |

**Método.** (1) Releitura do meu relatório da rodada 1, do plano (incluindo "Evidências e integração") e do AGENTS.md. (2) Leitura do diff de `services.py`, `models.py`, `views_web.py`, templates e CSS. (3) Reexecução dos meus cenários da rodada 1 contra a versão nova. (4) Dois ensaios aleatórios, o meu da rodada 1 e um novo com propriedades mais estritas que a P4 do implementador. (5) Diferencial da DLPA em três versões. (6) Matriz HTTP por papel e trilha. (7) Medição real no Chromium: impressão em PDF, rolagem em 390 px e o script do projeto. (8) Mutação: 28 mutantes novos sobre a correção. (9) Suíte completa e verificações do repositório.

Os arquivos que escrevi ficam só nas cópias descartáveis (`test_aud061_*.py`, `mutar_rec.py`, `rec_*.py`). Não implementei nem corrigi nada.

---

## 2. Comandos e saídas reais

| Comando | Resultado real |
| --- | --- |
| `ruff check .` (no checkout) | `All checks passed!` |
| `ruff format --check .` | `349 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate` (bancos vazios, três vezes) | sem erro |
| `pytest -q --create-db -rs` (suíte COMPLETA, cópia limpa `rec061_suite`) | `1 failed, 4514 passed, 53 skipped, 2 warnings, 4 subtests passed in 423.21s` |
| a falha | só `test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (`except TypeError, ValueError:` → `SyntaxError`; Python 3.13 local, falha aceita) |
| `test_agents_md_nao_ultrapassa_a_margem_de_seguranca_do_codex` | **Passou na cópia limpa.** No checkout (que tem `.claude/worktrees/`) reprova com a mensagem: `Soma de 4 AGENTS.md (['.claude/worktrees/agent-a09b1c85061b909b9/AGENTS.md', '.claude/worktrees/agent-a8d9c08b4c4684b8b/AGENTS.md', '.claude/worktrees/agent-aed572db2cfee16f8/AGENTS.md', 'AGENTS.md']) = 119920 bytes`. Confirma o artefato local; `wc -c AGENTS.md` = **29.980 bytes** |
| os 53 skips | 35 linhas de motivo: Chromium do `/usr/bin/python3` (medição ponta a ponta), fontes Inter/Segoe UI/Arial ausentes, e 3 testes de navegador da tela (veja a próxima linha) |
| `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/chrome pytest test_dl061_tela_dmpl_correcoes.py test_dl061_tela_dmpl.py` | `113 passed` (0 skipped): os testes de navegador de N5 e N10 **rodam e passam** |
| Medição real `python scripts/medir_identificacao_do_emitente.py <pasta>` (`DL_PYTHON_DO_SISTEMA` = python da venv, `DL_CHROMIUM_EXECUTAVEL`, banco semeado `dataledger_rec061_med`) | `exit 0`; `contabilidade_web:dmpl: PASSOU` nas duas fases (`/empresas/1/dmpl/` com veto; `/empresas/3/dmpl/` emitida); piso de classe 2: `balanco, dlpa, dmpl, dre` |
| `pwsh ./scripts/validate-docs.ps1` | **Não executado** (`pwsh` ausente). Substituí por verificação parcial em Python dos 6 `.md` alterados (título, nova linha final, espaço no fim, links relativos): todos `ok`. O teste `test_documentacao_do_estado` passou na suíte |
| `git status` / `git diff --stat` no checkout | vazios |

---

## 3. Achados N1 a N11

Veredito: **Fechado**, **Parcial** ou **Aberto**. Classificação: Testado (executei), Inspecionado (li, não executei).

| ID | Gravidade original | Veredito | Evidência executada |
| --- | --- | --- | --- |
| **N1** | alta | **Fechado** | **Testado.** Caso 1 (tesouraria): compra 1.500 em jan e `D Caixa 1.800 / C Tesouraria 1.500 / C Receita 300` em fev. Agora: aquisição **(1.500,00)** e alienação **1.500,00** (antes (1.800) e 1.800). Caso do capital `D Caixa 150 / C Capital 100 / C Receita 50`: "Aumento de capital" **100,00** e nenhuma "Redução de capital" (antes 150 e (50)). Meu ensaio da rodada 1 (12 sementes): **0 achados em 67 emitidos** (antes 9 em 75). Ensaio novo mais estrito (seção 4): 24 sementes × 160 lançamentos, 870 DMPL emitidas, **0 violações** de P4/Q4, Q1, Q3, Q5, Q8, P1. Mutantes R01, R21 mortos |
| **N2** | alta | **Fechado** | **Testado.** Caso 2 sobre o caso A: `D Dividendos a Pagar / C Capital 4.000` → "Aumento de capital" **+4.000,00**, "Dividendos" segue **(10.000,00)**, saldo final do capital 104.000,00 (antes: Dividendos +4.000 no capital, total (6.000)). Variante `C Reserva legal 1.000` → **pendência** (`contrapartidas_sem_classificacao`, `pode_emitir=False`), nenhum "Dividendos" positivo. Estorno de dividendo pago com reserva continua em "Dividendos" nos dois sinais. Mutantes R03 a R07 mortos |
| **N3** | média | **Fechado** | **Testado.** Caso 3: estorno da transferência para lucros (`pode_emitir=True`, **`avisos.resultado_na_conta_de_passagem` = 25.000,00**, conta 3.0 listada, conciliação do total com `saldo_contas_de_passagem` = 25.000,00). Na tela: faixa "Com ressalva: há resultado ainda não transferido…" com âncora e bloco de aviso com links para Diário e Fechamento. **Nota no papel:** no PDF (Chromium) da DMPL de 12 colunas, com o estorno aplicado, o texto extraído traz "Há saldo de R$ 200.000,00 na conta de resultado do exercício, ainda não transferido para lucros ou prejuízos acumulados. Por isso o total desta demonstração difere do patrimônio líquido do Balanço Patrimonial de 31/03/2026 nesse valor." e a DMPL continua em **1 folha** (yMax 563,5 de 595 pt). Mutantes R13, R14, R24, R25, R28 mortos |
| **N4** | média | **Fechado** | **Testado.** Conta de PL "Dividendos Propostos (PL)" (DLPA = dividendo) com movimento: `classificavel=False`, `orientacao` = "…ainda não tem coluna na DMPL, e a classificação da DLPA dela não admite nenhuma. Mova-a para o passivo, se for dividendo a pagar, ou aguarde a coluna de dividendo adicional proposto (BL-603)". Na tela (Playwright, gestor) aparece "Como resolver: …" **sem link** de coluna, e a ação genérica "Dê uma coluna…" foi substituída. Teste derivado do mapa de consistência cobre todas as classificações da DLPA. O comentário de `models.py:838-844` foi corrigido (BL-603 está só no backlog). Mutantes R19, R20 mortos |
| **N5** | média/baixa | **Fechado** | **Testado.** PDF do Chromium, A4 paisagem, 841,92 pt, `pdftotext -bbox`: 12 colunas **xMax = 813,0** (limite largura − 23 pt = 818,9); com a nota do N3: 813,0; caso B (5 colunas): 813,0; 12 colunas com valores de 9 dígitos (R$ 296 milhões): 813,8. Sempre **1 página**. `xMin` = 25,5 pt. Letra de corpo ~9,3 pt, cabeçalho 10,7 pt (não foi reduzida). Teste de navegador do projeto passou. Mutante R26 morto |
| **N6** | baixa | **Fechado** | **Testado.** Caso 6 (vigência de 01/03/2026 em diante, `adota=True`): `ParametroContabilInvalido: "Nenhum exercício anterior a 2027 começa (em 01/01) dentro da vigência de 01/03/2026 em diante…"`. Meu teste da rodada 1 agora falha **por esse motivo** (a recusa é o comportamento novo). A view captura a exceção e mostra a mensagem (inspecionado). Desligar nunca é recusado. Mutantes R15 a R18 mortos |
| **N7** | baixa | **Fechado, com ressalvas M1 e M2** | **Testado.** O caso 7 (`D Reserva legal 3.300 / C Reserva legal 1.300 / C Lucros 2.000`) e o das duas contas da mesma reserva agora vetam (`lancamentos_ambiguos`, mensagem atualizada). Diferencial DLPA × DMPL: 24 sementes × 160 lançamentos, **870 emitidos, 853 com a DLPA também emissível: 852 idênticos linha a linha, 1 divergência** (M1, que **não** é a divergência do N7). Mutantes R08, R09, R10 mortos |
| **N8** | baixa | **Fechado** | **Testado.** `D Capital 2.000 / C Tesouraria 2.000` → "Alienação ou cancelamento" com capital (2.000,00) e tesouraria +2.000,00, total da linha 0,00, `pode_emitir=True`; idem reservas de lucros e de capital; lucros acumulados → tesouraria continua **sem regra** (pendência `pares_de_colunas_sem_regra`). Mutantes R11, R12 mortos. Ver a avaliação da decisão na seção 5 |
| **N9** | baixa | **Fechado** | **Testado.** Mutante N02 (R23, reservas de capital fora das origens): **morto** por `test_n9_agio_incorporado_ao_capital…`. Mutante N10 (R22, links sem filtro de empresa): **morto** por `test_links_de_origem_omitem_o_lancamento_de_outra_empresa`. A P4 virou teste versionado (3 sementes × 90) e o diferencial também |
| **N10** | baixa | **Fechado** | **Testado.** Chromium, 390 px: `/parametros-contabeis/` `scrollWidth` = **390** (antes 849); plano de contas 390; DMPL 390 (12 colunas) e DMPL vetada 390. Medi o mutante sem `position: relative`: **739** (a correção é a causa). Teste de navegador do projeto passa com Chromium e o mutante R27 morre quando ele roda (sobrevive só onde o teste é pulado) |
| **N11** | baixa | **Fechado (nota M4)** | **Testado.** A mensagem de `diferenca_de_fechamento` agora diz "Causa mais provável: conta retificadora do patrimônio líquido… cadastrada FORA do grupo "Patrimônio Líquido"…", e só depois "dado inconsistente". Nota M4 abaixo |

Mutantes: dos 28 novos, **26 mortos, 2 sobreviventes**: **R02** (remover o `continue` do líquido zero das livres): **equivalente por raciocínio** — com contrapartidas sem classificação decisiva o líquido delas na coluna é `−efeito da coluna ≠ 0` no ramo de uma coluna, e no ramo de várias colunas todos os nós do outro lado da âncora têm o mesmo sinal; não consegui construir lançamento que o alcance (Inspecionado, não provado por teste). **R27** (N10): sobrevive apenas quando o teste de navegador é pulado; morto com `DL_CHROMIUM_EXECUTAVEL` definido.

---

## 4. Ensaios que executei

**Cenários da rodada 1 (28 testes, `test_aud061_cenarios*.py`, `extra*.py`, `http.py`).** Todos passam, mas vários só **imprimem**. Li a saída de cada um: caso B (capital 120.000, reserva legal 1.250, ajustes 3.000, tesouraria (2.000), lucros 13.750, total 136.000), prejuízo com reversão, capital a integralizar, tesouraria com ganho em reserva de capital (aquisição (1.500), alienação 1.500, reserva de capital 300), N:M de lucros em três destinos, mês intermediário, abril sem zerar, estorno de dividendo, ágio → capital.

**Ensaio novo `test_aud061_fuzz2.py`** (cópia descartável; proposta de teste na seção 8). Para cada lançamento aleatório de partidas dobradas válidas (1 a 3 débitos, 1 a 3 créditos, contas repetidas nos dois lados, plano com 15 contas), isolado e desfeito por rollback, nas DMPL emitidas confere:

- **P1:** soma das células por coluna = efeito líquido.
- **Q4 (P4 estrita, sem exceção para linhas decididas por classificação):** toda célula de linha de evento tem o sinal do efeito líquido da coluna; só `resultado_do_exercicio`, `dividendos` e `ajustes_de_exercicios_anteriores` ficam fora.
- **Q1:** `dividendos` só em lucros acumulados ou reserva de lucros; resultado e ajuste só em lucros.
- **Q3:** essas três linhas só existem se o lançamento tem conta com a classificação correspondente.
- **Q5:** nunca "Dividendos" positivo em reserva de lucros (os lançamentos são isolados, nunca estorno).
- **Q8 (oráculo):** lançamento que toca uma só coluna entre capital, tesouraria, ágio e ajustes, com contrapartidas sem classificação: uma única linha de evento, de valor igual ao líquido; líquido zero, nenhuma linha.
- **P3:** identidade com a DLPA linha a linha quando as duas emitem.

Resultado: 24 sementes × 160 = 3.840 lançamentos, **870 emitidos**, 853 comparados com a DLPA, **0 violações de P1, Q1, Q3, Q4, Q5, Q8; 1 violação de P3 (M1)**. O harness discrimina: o P4 original deste ensaio reprovava 9 de 75 na versão `ebc8bdf`, e os mutantes R01, R03, R04, R06 e R21 são mortos pelas propriedades da suíte do projeto.

**Diferencial da DLPA.** Reconstruí a base (a de 1.056 combinações da rodada 1 foi descartada): 101 empresas sintéticas (40 + 60 de lançamentos aleatórios, a do caso B de 12 colunas e outras) × 2025/2026 × 12 meses = **2.424 combinações, 1.190 com movimento, sem exceção de apuração**. `apurar_dlpa` serializada em `1209334`, `ebc8bdf` e `8054442`: **as três saídas são idênticas byte a byte** (`rec == ebc: True`, `rec == 1209334: True`). `git diff ebc8bdf..8054442` não toca nenhum teste `test_dl048_*`. A suíte da DLPA passa sem alteração de expectativa.

---

## 5. Verificação das decisões da correção

Avaliação de cada decisão do `arquiteto-senior` quanto a **criar evento errado em vez de vetar**. "Muda o que o Fred aprovou?" refere-se a RC-151, RC-152 e RC-137.

| Decisão | Avaliação | Muda o aprovado? |
| --- | --- | --- |
| **Líquido na coluna única (N1)** | Elimina as linhas infladas e o evento oposto inexistente (provado em N1 e no ensaio). **Mas** o líquido também apaga o bruto quando o mesmo lançamento tem eventos legítimos de sentidos opostos na mesma coluna com contrapartidas distintas: compra de ações em tesouraria de 1.500 e venda de 1.000 num só lançamento saem como "Aquisição (500,00)", e redução de capital de 200 mais aumento de 1.000 saem como "Aumento 800,00" (reproduzido, seção 7, **M2**). O valor líquido está certo e o saldo fecha, mas a linha mostra um número que não é nenhum dos eventos. É coerente com a decisão da subscrição parcial e, para o Fred, é escolha contábil | Não contradiz RC-151 em letra (a regra decide pelo líquido), mas amplia o "decide" sem decisão dele. **Pedir confirmação ao Fred** |
| **Restrição do N7 às seis reservas de lucros** | Sólida onde a DLPA detalha item a item (o veto sai e o caso 7 não diverge mais). Para capital, reservas de capital, ajustes e tesouraria o líquido vale; **a subscrição com integralização parcial vira "Aumento de capital" líquido** (30.000 no meu cenário de capital a integralizar; teste do implementador `test_n7_subscricao_com_integralizacao_no_mesmo_lancamento_e_aumento_de_capital_liquido`). Contabilmente defensável (capital realizado), com o limite da M2. Para lucros acumulados a premissa "a DLPA também soma os itens" **não vale com contrapartidas classificadas** (M1) | Não muda; é desenho. Mesma ressalva da M2 |
| **Pendência de dividendo positivo em reserva, salvo estorno** | Cumpre a RC-151 (na dúvida, recusa). `e_estorno` vem de `LancamentoContabil.estorno_de`, preenchido só por `estornar_lancamento` (inversão exata dos itens; o serializador expõe o campo só de leitura, não há como forjar). Verifiquei os dois lados: pagamento com reserva (−300) + estorno (+300) → "Dividendos" líquido zero e emissão liberada; lançamento manual `D Dividendos a pagar / C Reserva legal` → pendência. **Mas** a orientação da mensagem ("estorne o dividendo original ou divida o lançamento") não resolve o veto na prática (M3) | Não muda (reforça a RC-151) |
| **Cancelamento de tesouraria (N8)** | Cria evento com regra nova, não presumida: capital ou reservas (de capital ou de lucros) → tesouraria = "alienação ou cancelamento", com a coluna de origem negativa e a tesouraria positiva (total da linha 0,00). Direção contrária e lucros acumulados continuam **vetados**. O caso `D Capital 1.000 / C Tesouraria 800 / C Reserva de capital 200` (diferença do cancelamento) veta por par sem regra, correto. Não encontrei evento errado; a validade contábil de classificar o cancelamento sob a mesma linha da alienação é do Fred | Não contradiz RC-151/152/137. **Validação contábil do Fred** |
| **Exceção de P4 para linhas decididas por classificação** | Justificada para a identidade com a DLPA (dividendo e ajuste no mesmo lançamento têm sinais diferentes na coluna de lucros). **Não é furo na prática**: a exceção só cobre três linhas, e meu ensaio as vigia à parte (Q1, Q3, Q5) sem encontrar violação. Fica, porém, uma única superfície sem guarda de sinal: "Dividendos" **positivo nos lucros acumulados** (estorno de dividendo, idêntico à DLPA, **aceito por design**) | Não muda |

**Dívida de decisão para o Fred:** a nota **impressa** do N3 (aviso no papel, não só na tela) foi decisão do `arquiteto-senior`; era exatamente a pergunta aberta da rodada 1 (seção 5, item 3). Funciona e cabe numa folha, mas só o Fred diz se o documento entregue ao cliente deve levar essa frase.

**HI-50 / RC-152 / RC-153.** `requisitos.md` registra agora que o Fred confirmou em 01/10/2026 a revogação das alíneas "c" e "d" (RC-152) e a existência de cliente com "dividendo adicional proposto" no PL (RC-153, BL-603 planejada). **Não consigo verificar a fonte dessas confirmações** (são mensagens do Fred, fora do repositório); registro apenas que a documentação as cita, e que o texto do art. 10 da Lei 11.638/2007 não foi reaberto por mim. Enquanto a coluna da RC-153 não existe, o cliente com essa conta tem a emissão **vetada** (N4 deixa isso claro).

---

## 6. Regressão

| Item | Resultado |
| --- | --- |
| Casos A e B ao centavo (emissão real) | **Testado.** Caso B: capital 120.000,00, reserva legal 1.250,00, ajustes 3.000,00, tesouraria (2.000,00), lucros 13.750,00, total 136.000,00; caso A total 115.000,00. Σ das células por coluna + saldo inicial = saldo final em todos os cenários e em todas as DMPL emitidas do ensaio |
| DLPA inalterada | **Testado.** 2.424 combinações idênticas nas três versões; nenhum `test_dl048_*` alterado; suíte verde |
| Isolamento entre empresas e escritórios | **Testado.** Empresa de outro escritório: 404 em `dmpl`, classificação e marca; conta e vigência de empresa irmã: 404; filtro de empresa dos links de origem agora tem teste (R22 morto) |
| Permissões (matriz HTTP, GET dmpl / GET cls / POST cls / POST marca / empresa fora / conta fora) | **Testado, idêntica à rodada 1.** administrador e gestor: 200, 200, 302, 302, 404, 404; analista e financeiro: 200, 200, 302, **403**, 404, 404; paralegal: 200, 403, 403, 403, 404, 403; cliente: **403**, 403, 403, 403, 404, 403; anônimo: 302 para `/login/?next=…` |
| Link de correção só para quem escritura | **Testado.** Analista vê "definir a coluna da DMPL" e "definir a linha da DLPA"; paralegal não vê nenhum |
| Trilha | **Testado.** `parametro_contabil.adocao_antecipada_nbc_tg_51_alterada` e `conta.classificacao_dmpl_alterada` com antes/depois, `escritorio_id` preenchido (14), sem segredo |
| Norma por vigência | **Testado.** 01/01/2026 e 31/12/2026 → NBC TG 26 (R5); 01/01/2027 → NBC TG 51; adoção antecipada → TG 51 (testes e meus cenários passam; mutantes R15 a R18 mortos) |
| Medição real no Chromium | **Testado.** `contabilidade_web:dmpl: PASSOU` nos dois ramos (veto e emissão) |
| Sabotagem do instrumento de medição | **Não repetida** nesta rodada (feita e reprovando na rodada 1; o instrumento e `scripts/` não foram alterados pela correção) |
| Snapshot `REPEATABLE READ` | **Testado** apenas a emissão da instrução (13 consultas, `REPEATABLE READ` presente); duas conexões simultâneas **Não testado** (BL-607, declarado) |
| Migrações | `makemigrations --check` limpo; a migração 0018 não mudou nesta rodada |

---

## 7. Achados novos

### M1 — BAIXA — A identidade DLPA × DMPL (critério 2) não vale quando um lançamento debita e credita as contas de lucros e de prejuízos junto de contrapartidas classificadas; a DLPA fabrica linhas e a DMPL está correta

- **Requisito afetado:** plano E3 e critério 2 (coluna de lucros idêntica à DLPA).
- **Arquivo e linha:** `apps/contabilidade/services.py:6440-6445` (o veto N7 de coluna mista só vale para `RESERVAS_DE_LUCROS_DA_DMPL`; "Lucros acumulados fica de fora" porque "a DLPA também soma os itens") e a leitura item a item da DLPA em `apurar_dlpa` (inalterada). O teste `test_n7_lucros_e_prejuizos_na_mesma_coluna_no_mesmo_lancamento_nao_divergem_da_dlpa` (`test_dl061_dmpl_correcao_rodada1.py:882`) cobre só o caso sem contrapartida classificada.
- **Evidência (reproduzida: `test_aud061_div.py`, e achada pelo ensaio, semente 105):** plano do ensaio, um lançamento `D (-) Prejuízos Acumulados 2.700 / D Dividendos a Pagar 1.500 / C Lucros Acumulados 2.700 / C Capital Social 1.500` (compensação de prejuízo com lucro e capitalização de dividendos a pagar). **DMPL:** "Aumento de capital" 1.500,00 no capital e nenhuma linha nos lucros (líquido zero) — correto. **DLPA:** "dividendo **+1.500,00**" e "lucro incorporado ao capital **(1.500,00)**", líquido zero, mas duas linhas que não representam evento algum. Pré-existente: **idêntico na `ebc8bdf`** (lá a DMPL mostrava "Dividendos +1.500" no capital) e a DLPA é a mesma nas três versões. Frequência no ensaio: 1 em 853 comparações.
- **Impacto:** duas demonstrações do mesmo conjunto discordam na decomposição, sem aviso; o erro está na DLPA (fora do escopo desta etapa), mas o plano promete "cada linha da DLPA no evento correspondente da DMPL" e a justificativa do N7 ("a DLPA também soma os itens") não vale nesse caso.
- **Correção recomendada:** abrir BL para a DLPA (contrapartida classificada com itens opostos nas contas da coluna de lucros) e documentar a exceção do critério 2; alternativa, vetar na DMPL o lançamento com a coluna de lucros debitada e creditada junto de contrapartidas classificadas.
- **Forma de verificar:** proposta de teste na seção 8 (M1); incluir o ensaio P3 com 24 sementes como teste de regressão.
- **Responsável:** `desenvolvedor-pleno` (BL da DLPA); decisão de escopo do `arquiteto-senior`.

### M2 — BAIXA (decisão do Fred) — O líquido por coluna apaga o bruto quando o mesmo lançamento tem eventos legítimos de sentidos opostos em capital, tesouraria ou reservas de capital

- **Requisito afetado:** RC-151 ("quando a regra não decide, a emissão é recusada, nunca presumida"); decisões N1 e N7 do plano.
- **Arquivo e linha:** `apps/contabilidade/services.py:6413-6445` (veto de coluna mista só nas reservas de lucros) em conjunto com `:6473-6481` (`_resolver_as_contrapartidas_livres`, linha pelo líquido).
- **Evidência (`test_aud061_misto.py`, executada):** `D Tesouraria 1.500 / D Caixa 1.000 / C Caixa 1.500 / C Tesouraria 1.000` → `pode_emitir=True`, **"Aquisição de ações … (500,00)"**, saldo final (500,00). `D Capital 200 / D Caixa 800 / C Capital 1.000` → "Aumento de capital" 800,00, sem "Redução". Em ambos o saldo e a conciliação fecham e o líquido está correto.
- **Impacto:** a linha publica um valor que não corresponde a nenhum evento (a compra foi de 1.500 e a venda de 1.000). Rara na prática, mas é o mesmo tipo de comportamento que a RC-151 proíbe (decidir sem poder decidir), aceito aqui por analogia com a subscrição parcial.
- **Correção recomendada:** o Fred decide. Opção A: manter o líquido e declarar a limitação no plano e na tela. Opção B: vetar (`lancamentos_ambiguos`) o lançamento que debita e credita a mesma coluna de capital, tesouraria ou reserva de capital **com contrapartidas externas diferentes**, e manter o líquido apenas para a subscrição pura contra a retificadora (sem externa).
- **Forma de verificar:** proposta de teste na seção 8 (M2).
- **Responsável:** `arquiteto-senior` e Fred (decisão); `desenvolvedor-pleno` (se opção B).

### M3 — MÉDIA — O estorno do lançamento vetado não libera a DMPL, e a orientação ("estorne o dividendo original ou divida o lançamento") manda fazer algo que não resolve

- **Requisito afetado:** RC-151 ("lista o que falta"); critério 4 (pendências com saída); coerência com a regra de correção rastreável do projeto (lançamento efetivado é imutável; correção é estorno).
- **Arquivo e linha:** `apps/contabilidade/services.py:6301-6307` (mensagem da pendência de dividendo positivo em reserva) e `:6905-6911` (mensagem de `lancamentos_ambiguos`: "Divida o lançamento em um por evento"). O veto é por lançamento e não considera que um estorno o neutraliza.
- **Evidência (`test_aud061_est.py`, executada):** (a) `D Dividendos a Pagar / C Reserva legal 1.000` → pendência; depois `estornar_lancamento(...)` na mesma data → **`pode_emitir=False` com a mesma pendência**, e ainda aparece "Dividendos (1.000,00)" na reserva. (b) Lançamento ambíguo `D Reserva legal 300 / D Lucros 200 / C Capital 500`, estornado → `lancamentos_ambiguos` **persiste**. Dividir "o lançamento" é impossível (efetivado é imutável). Pré-existente para o ambíguo; **ampliado nesta rodada**: N7 passou a vetar combinações de reserva que antes emitiam, e N2 criou a pendência de dividendo positivo em reserva.
- **Impacto:** o contador que cair nessas situações segue as instruções da tela e continua sem poder emitir a DMPL do exercício até a fatia 2 (marcação manual). O desenho (exceção na fatia 2) é o aprovado na RC-151; o defeito é a **orientação falsa** e a ausência de qualquer aviso de que o veto é definitivo no exercício até a fatia 2.
- **Correção recomendada:** corrigir os dois textos para dizer a verdade ("o lançamento efetivado não se altera; o estorno não libera esta emissão; a exceção será a marcação manual da fatia 2 — BL-xxx"); registrar o BL; avaliar se a fatia 2 deve vir logo, ou se o estorno com par exato deve ser reconhecido (decisão de produto).
- **Forma de verificar:** teste em que, após estornar o lançamento vetado, a mensagem não manda estornar nem dividir; e (se a opção de reconhecer o par for adotada) a emissão é liberada.
- **Responsável:** `desenvolvedor-pleno` (texto), `arquiteto-senior` (decisão).

### M4 — BAIXA — A nova dica do N11 aponta para a retificadora fora do grupo mesmo quando a causa da diferença é uma conta de PL sem coluna

- **Arquivo e linha:** `apps/contabilidade/views_web.py:4746-4757`.
- **Evidência:** cenário do N4 (conta "Dividendos Propostos (PL)" movimentada, empresa 2 da base de medição, tela real): aparecem juntas a pendência da conta sem coluna e "Diferença entre a DMPL e o Balanço … diferença (100,00)" com o texto "Causa mais provável: conta retificadora do patrimônio líquido… cadastrada FORA do grupo…". Aqui a diferença é **a própria conta sem coluna** (a outra pendência já a explica), e a dica envia o contador a procurar a causa errada.
- **Impacto:** orientação enganosa em um caso comum (é o caso do N4).
- **Correção recomendada:** quando `contas_do_patrimonio_liquido_sem_coluna` também está presente, o texto da diferença deve dizer "provavelmente decorre da conta listada acima"; a dica da retificadora só quando ela é a única pendência.
- **Forma de verificar:** teste de tela com as duas pendências.
- **Responsável:** `especialista-frontend`.

### Observações (sem gravidade)

- **Equivalente provável R02:** `if liquido_da_coluna == zero: continue` não mudou nenhum teste; por raciocínio é inalcançável (Inspecionado).
- **Dispensa de nova medição do bloco de identificação em 2ª folha:** continua **Não testado** (a DMPL cabe em 1 folha; BL-621 declarado, com o limite de que em paisagem o Chromium não repete o `<thead>` alto).
- **Itens de rodada 1 que seguem abertos por serem pré-existentes e do Fred:** admin sem trilha (BL-619), reclassificação reescreve período passado (BL-620), número dos itens da norma (não reaberto o PDF do CFC).

---

## 8. Casos de teste propostos (texto; o responsável implementa)

Helpers são os de `test_dl061_dmpl.py` e `test_dl061_dmpl_correcao_rodada1.py`.

**M1.** Plano do ensaio (`_plano_do_ensaio`). Lançamento `D prejuizos 2.700 / D dividendos 1.500 / C lucros 2.700 / C capital 1.500`. Esperado, escolhendo uma das opções: ou DMPL e DLPA com as mesmas linhas de lucros, ou a DMPL vetada, ou o teste documenta a exceção. Hoje: DMPL sem linhas nos lucros e DLPA com `dividendo +1.500` e `lucro_incorporado_ao_capital (1.500)`. Incluir a propriedade P3 do `test_aud061_fuzz2.py` (24 sementes × 160) como teste de regressão.

**M2.**

```python
def test_compra_e_venda_de_acoes_em_tesouraria_no_mesmo_lancamento():
    empresa, contas = ...  # caso A + contas do caso B
    _lancar_itens(empresa, date(2026, 2, 5), "Permuta", [
        (contas["tesouraria"], "D", "1500.00"),
        (contas["caixa"], "D", "1000.00"),
        (contas["caixa"], "C", "1500.00"),
        (contas["tesouraria"], "C", "1000.00"),
    ])
    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    # Decisão do Fred. Opção A: afirmar e documentar o líquido (-500).
    # Opção B: exigir veto.
    assert emissao["pode_emitir"] is False
    assert "lancamentos_ambiguos" in emissao["listas_pendentes"]
```

Variante do capital: `D capital 200 / D caixa 800 / C capital 1.000`.

**M3.** Após `estornar_lancamento(l, ...)` do lançamento `D dividendos / C reserva_legal`, assertar o texto da pendência: não contém "estorne" nem "divida o lançamento", e diz que a exceção é a marcação manual da fatia 2.

**M4.** Cenário do N4 + diferença de fechamento: a mensagem de `diferenca_de_fechamento` não pode citar a retificadora como causa mais provável enquanto `contas_do_patrimonio_liquido_sem_coluna` estiver presente.

**Propriedades do ensaio estrito (para versionar).** As Q1, Q3, Q4, Q5, Q8 de `test_aud061_fuzz2.py` (cópia em `.../scratchpad/rec061/apps/contabilidade/tests/test_aud061_fuzz2.py`): o projeto já tem P1/P4 e P3 em 3 sementes × 90; propor 24 sementes × 160 (ou separar um teste lento) e acrescentar Q1/Q3/Q5/Q8, que vigiam as três linhas hoje isentas da P4.

---

## 9. Classificação geral

| Item | Classificação |
| --- | --- |
| N1 a N11 | **Testado** (seção 3). N6 pela view: **Inspecionado** (a exceção é capturada em `views_web.py:6150`) |
| `apurar_dmpl` (casos A, B, 28 cenários, 2 ensaios, 28 mutantes) | **Testado** |
| Leitura compartilhada e DLPA inalterada | **Testado** (2.424 combinações, 3 versões) |
| Autorização e isolamento (web) | **Testado** |
| Trilha | **Testado** |
| Norma por vigência | **Testado** |
| Medição no Chromium real (script do projeto) | **Testado** (passou); sabotagem **não repetida** |
| Impressão em PDF (N5, N3) | **Testado** (5, 12 e 12 colunas com valores de 9 dígitos) |
| Rolagem a 390 px (N10) | **Testado** |
| Suíte completa | **Testado**: 4.514 passaram, 1 falha aceita (Python 3.13) |
| Repetição do bloco de identificação em 2ª folha | **Não testado** (DMPL cabe em 1 folha; BL-621) |
| Concorrência / snapshot com duas conexões | **Não testado** (BL-607, declarado) |
| `validate-docs.ps1` | **Não testado** (sem `pwsh`); substituído por verificação parcial em Python |
| Itens da norma no texto do CFC e do art. 10 da Lei 11.638/2007 | **Não testado** (validação do Fred) |
| Marcação manual por lançamento, API, comparativo, dividendo por ação | **Fora do escopo** (fatia 2 / E8) |

**Separação do que muda ou não o que o Fred aprovou.**

*Não muda:* RC-151 (linha pela contrapartida, veto com lista do que falta; a correção a **restaura** onde N1 e N2 a violavam), RC-137 (uma coluna por tipo de reserva de lucros), RC-152 (alíneas "c" e "d" fora das colunas), decisão 1 da DL-048 (telas separadas), norma por vigência e adoção antecipada (29/09).

*Exige o Fred (decisão ou validação, nada foi alterado por mim):* (1) M2: manter o líquido ou vetar o lançamento com eventos opostos na mesma coluna; (2) cancelamento de tesouraria sob "alienação ou cancelamento"; (3) a nota **impressa** do N3; (4) a restrição do N7 e a tratativa da subscrição parcial como aumento líquido; (5) a orientação "mova a conta para o passivo" do N4; (6) RC-153: a coluna do dividendo adicional proposto e o veto até lá; (7) lucros e prejuízos na mesma coluna, ordem das linhas, "aumento de capital com reservas e lucros" com reservas de capital (art. 200, IV): escolhas contábeis a validar.

---

## 10. Parecer e fundamento

**APROVADO COM RESSALVAS.**

- **O que fecha o parecer:** os dois achados altos (N1, N2) deixam de existir na versão reconferida: casos 1 e 2 reproduzidos, P4 como teste, meu ensaio da rodada 1 sem achados (0/67 contra 9/75) e um ensaio mais estrito sem violação em 870 DMPL emitidas; cinco mutantes sobre N1/N2 mortos. N3 a N11 estão fechados com evidência executada (aviso na tela e nota no papel, margem de 8 mm medida em PDF, 390 px sem rolagem, cancelamento de tesouraria, recusa da marca sem efeito). Casos A e B ao centavo, DLPA idêntica em três versões, isolamento, permissões e trilha sem regressão, medição real no Chromium aprovada. Suíte completa com a única falha aceita.
- **Por que não é APROVADO simples:** (1) **M3 (média):** o veto não sai com estorno e a mensagem orienta para uma saída que não existe; (2) **M2:** o líquido mostra um número que não é evento em lançamentos de eventos opostos na mesma coluna, decisão que cabe ao Fred; (3) **M1:** a identidade com a DLPA tem uma exceção não documentada (defeito da DLPA, pré-existente); (4) **M4:** dica enganosa em caso comum; (5) verificações pendentes declaradas (2ª folha, concorrência, `validate-docs.ps1`, sabotagem do instrumento) e validações do Fred (norma, escolhas contábeis).
- **Condição das ressalvas:** M2 a M4 e M1 devem ir ao backlog com responsável antes do merge; as validações contábeis da seção 9 ficam registradas como pendência do Fred, não como defeito resolvido. Esta é a última rodada (AGENTS.md §3.1).
- **Documentação a atualizar pelo `arquiteto-senior`:** `docs/agents/estado.md` e o backlog (BL-608 a BL-618 passam a "corrigido e reconferido"; abrir BL para M1 a M4), conforme a regra do CLAUDE.md.

Auditoria de software não substitui a validação profissional das regras contábeis e legais. Este relatório não declara ausência de defeitos além dos testados.

---

## 11. Arquivos de referência (todos na cópia descartável)

`...` = `/tmp/claude-0/-home-user-DataLedger/f87afd18-c419-55b8-b66f-f612e14081e2/scratchpad`

- `.../rec061/apps/contabilidade/tests/test_aud061_*.py` (cenários, ensaio antigo, ensaio estrito `fuzz2`, M1 `div`, M3 `est`, M2 `misto` em `.../rec061_suite/...`, matriz HTTP, norma).
- `.../mutar_rec.py`, `.../mutacoes_rec.log` (28 mutantes).
- `.../rec_imprimir.py`, `rec_d12.pdf`, `rec_d12nota.pdf`, `rec_casoB.pdf`, `rec_grande.pdf` (PDFs e medida da margem), `rec_tela.py`, `rec_n10.py`, `rec_dmpl12_1440.png`.
- `.../dif_rec061.json`, `dif_aud061.json`, `dif_aud061_base.json` (diferencial da DLPA).
- `.../rec061_suite.log` (suíte completa), `.../medicao_rec.out` e `.../medicao_rec_pdfs/` (medição do projeto).
