# Reconferência da DL-083 — 09/10/2026

**Parecer: REPROVADA.** Há uma falha de alta gravidade (R1): a natureza nova `devolucao_combustivel_consumo`, peça central da correção do A1, não pode ser confirmada pela tela nem pela API. A tela e a API recusam a natureza com HTTP 400, porque o limite de tamanho do campo continuou em 24 caracteres e o nome tem 29. O conserto é pequeno (duas constantes e um teste) e vem abaixo. Só com ele corrigido e verificado o parecer pode subir para APROVADA COM RESSALVAS.

## Versão e ambiente

- **Versão:** cópia destacada `/home/user/wt-rc083`, commit `8ff03e8`, branch `ccr-bf4b4a55-hpqgbp`.
- **Ambiente:** Python 3.13.16, PostgreSQL 16 local, `DATABASE_URL=.../aud_dl083_rc`.
- **Árvore auditada:** `git status` e `git diff --stat` vazios antes e depois.
- **Mutantes e testes meus:** rodaram em cópias em `scratchpad/rc083/` (`copia`, `mut1`, `mut2`), com `PYTHONDONTWRITEBYTECODE=1`. Conferi com `diff -r` que `mut1` e `mut2` voltaram idênticas à árvore auditada, sem arquivo `.orig`.

## Situação dos achados da rodada 1

| # | Situação | Evidência executada |
| --- | --- | --- |
| A1 | **Parcialmente fechado (R1 aberto)** | O núcleo funciona; o caminho de confirmação pela tela e pela API não. |
| A2 | **Fechado** | Reversão pelo `migrate` real nos três cenários, abaixo. |
| A3 | **Fechado** (com R2 e R3 como efeitos novos) | E1, E2, rateio, bloqueios e W16 aleatório, abaixo. |
| A4 | **Fechado** | Os oito sobreviventes da rodada 1 morreram. |
| A5 | **Fechado como registro** | Está no BL-688 (`backlog.md:2253`). A leitura de `retTrib` segue fora do escopo. |
| A6 | **Fechado** | NCM conferido contra o JSON oficial, abaixo. |
| A7 | **Fechado** | `receita_de_nfe_no_mes` e `_nfe_do_mes` removidas. Grep em `apps/` e `templates/` não acha mais nenhuma. |
| A8 | **Fechado** | Recusa `nfe_2027_pendente` e botão desabilitado, abaixo. |
| A9 | **Aberto** | Nem o plano nem o backlog tratam de nota efetivada com `combustivel` anterior à DL-083. Faltam consulta de dados antes de ativar e registro. |
| A10 | **Fechado como registro** | Está no BL-688. |

### A1 em detalhe

- **Reconhecimento:** `e_devolucao_de_combustivel` cobre 5.660 a 5.662, 6.660 a 6.662, 1.660 a 1.662 e 2.660 a 2.662. Testei os 12 CFOP, nos papéis certos (destinatário para 5.xxx e 6.xxx, emitente para 1.xxx e 2.xxx). Todos viram `TipoEscrituracaoNFe.DEVOLUCAO` e `recusas == []`.
- **Sugestão:** 72 combinações de CFOP × NCM (gasolina, álcool, diesel B, lubrificante, cerveja, NCM ausente), todas conforme a regra:
  - x.662 com NCM de combustível sugere `devolucao_combustivel_consumo`; sem NCM de combustível, não sugere.
  - x.660 e x.661 sugerem `devolucao_venda`.
  - NCM de lubrificante sugere `devolucao_venda`.
  - CFOP genérico (1.202, 5.202) com gasolina fica sem sugestão.
- **Caso 3.6** (5.661 emitida pela própria empresa, tpNF 1, finNFe 4):
  - `tipo_da_nota` devolve `None`.
  - `criar_rascunho` recusa com "saída que não é venda própria nem ajuste (finNFe 4): fora desta escrituração".
  - A apuração fica com `devolucao_deduzida == 0` e sem recusa. **Não vira dedução nem receita.**
- **Aviso de x.662 deduzida a 8%:** dispara em 5.662 e 6.662 com a natureza `devolucao_venda`, não dispara em 5.661, e some quando a natureza é de consumo. Aparece na tela e em `ap.avisos`. Falso positivo no R4.
- **Saldo por atividade:** o oráculo está abaixo e bate ao centavo.

### A2 em detalhe

Rodei com `call_command("migrate")` e `transaction=True`:

- **Cenário 1, rascunho com a natureza nova** (as duas naturezas testadas): a reversão recusa com `RuntimeError`, e CHECK, coluna e dados ficam como estavam. Depois de reclassificar, a reversão passa, o CHECK volta validado e a reaplicação restaura a lista nova.
- **Cenário 2, só estornada com a natureza nova:** a reversão passa e o CHECK antigo fica `convalidated = False` (NOT VALID). O INSERT de linha nova com a natureza nova é recusado pelo CHECK. A reaplicação valida o CHECK (`convalidated = True`) com a estornada dentro da lista nova.
- **Cenário 3, efetivada:** a reversão recusa; depois do estorno passa; ida, volta e ida de novo funcionam.
- **Coluna:** `varchar(29)` depois da reversão. `migrate` em banco vazio e `migrate fiscal 0011` seguido de `migrate fiscal` também passam.

### A3 em detalhe

- **E1:** a nota efetiva com receita 90,00.
- **E2:** a nota efetiva com receita 150,00.
- **Rateio:** três itens iguais de 100,00 mais frete de 10,00 em item de bonificação dão 103,34, 103,33 e 103,33. O resíduo de arredondamento vai para o primeiro item (o de menor `nItem`) quando há empate de valor.
- **Nota só de remessa com frete:** bloqueia, com `indTot` 0 e com `indTot` 1.
- **Remessa pura `indTot` 1 sem frete:** efetiva.
- **Devolução com frete:** efetiva nos dois papéis; a devolução vale 115,00, igual à soma dos itens.
- **Resíduo negativo maior que a receita:** bloqueia. Se for igual, efetiva com receita zero.
- **D2** (resíduo positivo sem base de rateio): bloqueia.
- **Uso da atribuição:** confirmei por grep e por cenário que a conferência, a efetivação, a conferência do mês, a segregação, `linhas_nfe_do_periodo` (Simples, RBT12 e Presumido), a tela e a API usam a atribuição. Em empresa do Simples, uma nota com revenda 600, monofásico 400 e frete líquido de 90 dá:
  - composição 1.090,00;
  - segregação normal 654,00 e monofásico 436,00;
  - RBT12 do mês igual a 1.090,00;
  - conferência 654,00 e 436,00.
- **W16 aleatório:** três sementes × 70 notas, com itens de receita e de não-receita (`indTot` 0 e 1), frete, seguro, outras despesas, desconto e ICMS desonerado. Foram 163 efetivadas e 47 bloqueadas. Em todas, o produto bateu ao centavo com o meu oráculo (que reimplementa a regra, o rateio proporcional com `ROUND_HALF_UP` e o resíduo no item de maior valor). Em todas as efetivadas, `soma_itens` foi igual ao `vNF` da fórmula do MOC. Em todas as bloqueadas, a mensagem era a esperada.

### A6 em detalhe

Conferi `apps/fiscal/ncm_combustivel.py` contra `scratchpad/tipi/ncm.json`:

- **JSON:** sha256 `4ca9f857…de59b`, "Vigente em 09/10/2026, Resolução Gecex nº 926/2026".
- **19 códigos:** todos existem, estão vigentes (início 01/04/2022, fim 31/12/9999) e a descrição bate com a classe.
  - 10 de combustível (gasolinas 2710.12.51 e .59, querosenes 2710.19.11 e .19, óleos combustíveis 2710.19.21, .22 e .29, gás natural 2711.11 e 2711.21, GLP 2711.19.10);
  - 5 de álcool e diesel B;
  - 4 de lubrificante.
- **Folhas fora das listas** (2711.12, 2711.13, 3403.11 e 3403.91, 3826, entre outras): ficam sem sugestão, o lado seguro.
- **GLP:** o desenvolvedor o incluiu como combustível. Isso é decisão dele, não verifiquei se há norma específica.
- **Normalização:** aceita o NCM com e sem pontos (mutante G09 morreu).

### A8 em detalhe

- **Nota de 2027 sem rascunho:** `apurar_trimestre(2027)` e `controle_limite_ano(2027)` trazem `nfe_2027_pendente` e não trazem `nfe_nao_escriturada`.
- **Nota de 2027 em rascunho:** botão "Efetivar" desabilitado com o motivo, e o servidor recusa o POST. Isso eu li no teste do desenvolvedor (`test_dl083_telas.py`, `test_dl083_conferencia_e_2027.py`); os mutantes Y03 e Y04 morreram por esses testes.

## Achados novos

### R1 — alta — a natureza `devolucao_combustivel_consumo` não passa no limite de 24 caracteres da tela e da API

- **Requisito:** A1, HI-140, critério 6.
- **Local:**
  - `apps/fiscal/views_web.py:6812` (`_TAMANHO_NATUREZA_NFE = 24`), usado em `:7437` (natureza do item), `:7443` (sinal do bloco) e `:7594` (reclassificação).
  - `apps/fiscal/api_escrituracao_nfe.py:54` (`_TAMANHO_NATUREZA = 24`), usado nos serializers das linhas `:139-140` (`DefinirNaturezasView`) e `:156-157` (`ReclassificarNFeView`).
- **Evidência** (`test_rc083_limite24.py`; devolução 5.662 recebida, gasolina, rascunho criado):

  | Caminho | Resultado |
  | --- | --- |
  | POST web `acao=item` com `devolucao_combustivel_consumo` | 400, natureza vazia |
  | POST web `acao=bloco`, `sinal=devolucao_combustivel_consumo` | 400 |
  | API `.../naturezas/` | 400, "Certifique-se de que este campo não tenha mais de 24 caracteres." |
  | API `.../reclassificar/` | 400, mesma mensagem |
  | Reclassificação pela tela | 400 |

  Na cópia, com as duas constantes em 29, a tela grava a natureza (302) e a API devolve 200 nos dois endpoints. Os testes do desenvolvedor passam porque gravam a natureza por `QuerySet.update` e nunca pelo canal real.
- **Impacto:** a sugestão x.662 → consumo aparece, mas o contador não consegue confirmá-la. Sobra a `devolucao_venda`, que deduz a 8%. Para uma venda a 1,6%, o IRPJ sai a menor: no exemplo do A1, R$ 96,00 por R$ 10.000,00 devolvidos. O único amortecedor é o aviso de "deduzida a 8%". O A1 só está fechado no serviço, não no produto.
- **Correção recomendada:** derivar os dois limites de `NaturezaItemNFe._meta.get_field("natureza").max_length`, em vez de repetir o literal.
- **Verificação:** teste parametrizado sobre `NaturezaOperacaoNFe.values` que confirme `len(valor) <= limite` na tela e na API, mais POST ponta a ponta (tela `item` e `bloco`, API `naturezas` e `reclassificar`) com `devolucao_combustivel_consumo`.

### R2 — média — nota efetivada antes da DL-083, que a atribuição recusa, derruba a receita do mês

- **Requisito:** critério 7 (regressão) e A3.
- **Local:** `apps/fiscal/receita.py:318`, `apps/fiscal/escrituracao_nfe.py:414` (`segregacao_da_escrituracao`) e `:1362` (`_preencher_receita`). Nenhuma das três trata `ResiduoNaoAtribuivel`. Os comentários dizem que "a nota que a atribuição recusa não pode estar efetivada", o que é falso para dado anterior à regra.
- **Evidência:**
  - Em `148be40` (a base, integrada na `main` como PR #105), rodei uma remessa pura `indTot` 1, vProd 300,00 mais vFrete 50,00. Ela efetivou com `receita_bruta` 0,00.
  - Reproduzi o estado em `8ff03e8` com monkeypatch só na efetivação. Com essa nota efetivada ao lado de uma revenda de 1.000,00, `composicao_do_mes`, `conferencia_do_mes`, `apurar_trimestre` e `controle_limite_ano` levantam `ResiduoNaoAtribuivel`.
  - Telas: conferência, receita do mês, apuração e a própria tela da nota dão 500. A lista "a escriturar" dá 200.
  - O estorno pelo serviço funciona; depois dele a composição volta a 1.000,00.
- **Impacto:** se existir dado assim, a receita do mês fica indisponível (Simples e Presumido) até alguém estornar a nota. O erro é alto, não silencioso. Depende de haver tal dado; no dev não há nada efetivado. Isto tem a mesma natureza do A9.
- **Correção recomendada:** ou uma consulta de pré-ativação ("quantas efetivadas a atribuição recusa"), ou tratar a recusa nas três leituras (valor cru dos itens de receita mais aviso "efetivada antes da HI-138").
- **Verificação:** o teste `test_rc083_legado.py` (nota efetivada com atribuição neutralizada na efetivação, depois as quatro funções e as telas) deve passar sem exceção.

### R3 — baixa a média — nota sem item de receita e com frete, seguro ou outras despesas em item `indTot` 1 deixou de efetivar e não tem saída correta

- **Requisito:** HI-138, bloqueio (b).
- **Evidência:**
  - Nota de ajuste (finNFe 2, tpNF 1) com vFrete 5,00: bloqueia com a mensagem "escolha uma natureza de receita". Com vOutro 5,00, igual. Sem despesa, efetiva. Em `148be40`, as duas efetivavam, porque a guarda só valia para `indTot` 0.
  - `naturezas_permitidas(AJUSTE)` aceita só `ajuste`, então o contador não tem natureza de receita para escolher.
  - Para remessa `indTot` 1 com frete, a única saída é uma natureza de receita, que leva o vProd inteiro (300,00) para a receita.
  - Enquanto a nota fica a escriturar, o trimestre fica parcial por `nfe_nao_escriturada`.
- **Impacto:** frequência provavelmente baixa. É decisão de produto, e o Fred a aceitou na HI-138. Registro porque a mensagem sugere uma saída que, para `indTot` 1, distorce a receita.
- **Correção recomendada:** tirar `ajuste` do resíduo, ou mensagem específica para `indTot` 1, ou registrar no BL-688.
- **Verificação:** `test_rc083_ajuste.py`.

### R4 — baixa — falso positivo do aviso de x.662 deduzida a 8% para lubrificante

- **Local:** `apps/fiscal/presumido.py:999-1003`.
- **Evidência:** x.662 com NCM de lubrificante e `devolucao_venda`, que é a natureza certa para lubrificante, gera o aviso "confira a natureza (NF-e nº 102)". A linha de NF-e não carrega o NCM.
- **Impacto:** ruído na memória, sem efeito no cálculo.
- **Correção recomendada:** levar o NCM à `LinhaNFe` e condicionar o aviso ao NCM de combustível.

### R5 — baixa — nome da D8

`devolucao_por_atividade` na API é o valor deduzido, não a devolução recebida. Opino que o nome engana, e que renomear para `devolucao_deduzida_por_atividade` é barato agora e caro depois de haver consumidor. A tela já é clara: "Devolução de NF-e deduzida neste trimestre (atividade)".

### R6 — baixa — desconto maior que o vProd em item de não-receita `indTot` 1 não reduz a receita

- **Evidência** (`test_vdesc_maior_que_vprod_em_item_indtot1_nao_receita`): revenda 100,00, bonificação `indTot` 1 com vProd 10,00 e vDesc 25,00, remessa de 40,00. O vNF é 125,00 e a `receita_bruta` fica em 100,00. Os 15,00 de desconto excedente se perdem, o que dá receita a maior (a favor do fisco).
- **Limite:** não verifiquei se o MOC admite vDesc maior que vProd. D1 cobre o desconto só até o vProd.

### R7 — baixa — comentário desatualizado

`templates/fiscal/presumido_apuracao.html:19` ainda cita a recusa de devolução de combustível, que não existe mais. É comentário `{% comment %}`, não aparece na página.

### R8 — informativo — falha intermitente fora da DL-083

- Na primeira execução completa, `apps/fiscal/tests/test_concorrencia.py::test_corrida_real_de_evento_produz_um_unico_evento` falhou (`resultados == [1, 0]`).
- Ela rodou com dois mutantes consumindo CPU ao mesmo tempo e passou 5 em 5 isolada.
- Na segunda execução completa, com a máquina livre, passou.
- A DL-083 não tocou nem o teste nem `services.py`. Fica registrado como flakiness sob carga, não como defeito da entrega.

## Cálculos independentes

Oráculo meu, que não chama código de produção (`aud083_oraculo.py`). Empresa no Presumido 2026, critério de competência, atividade padrão de serviços a 32%.

**S5, duas atividades e saldo transportado.** Comparei ao centavo IRPJ e CSLL sem e com LC 224, parcela, dedução do 4º trimestre, `devolucao_por_atividade`, `saldo_por_atividade` e os totais.

| Trimestre | Fatos | IRPJ | CSLL |
| --- | --- | --- | --- |
| T1 | comércio 200.000, combustível 150.000, serviços 300.000, devolução de consumo 20.000, devolução de venda 15.000 | 22.220,00 | 12.042,00 |
| T2 | comércio 50.000, serviços 100.000, devolução de consumo 80.000 (sem receita de combustível, vira saldo), devolução de venda 10.000 | 5.280,00 | 3.312,00 |
| T3 | combustível 30.000 absorve 30.000 do saldo; devolução de comércio 25.000 sem receita de comércio | 0,00 | 0,00 |
| T4 | combustível 20.000 absorve 20.000; comércio 8.000 absorve 8.000; serviços 900.000 | 66.000,00 | 25.920,00 |

- **T1 à mão:** 185.000 × 8% = 14.800; 130.000 × 1,6% = 2.080; 300.000 × 32% = 96.000; base 112.880; principal 16.932; adicional (112.880 − 60.000) × 10% = 5.288; total 22.220,00. A CSLL é 133.800 × 9% = 12.042,00.
- **Saldos finais** (o oráculo e o produto coincidem): combustível 30.000,00 e comércio 17.000,00, os dois com aviso no 4º trimestre, "(Revenda de combustíveis)" e "(Comércio, indústria e transporte de cargas)".
- **Deduzido por atividade:** o produto coincide com o oráculo em cada trimestre. Em T2, combustível 0 e comércio 10.000; em T3, combustível 30.000 e comércio 0.

**S6, acima do limite da LC 224** (comércio 1.500.000, combustível 1.000.000 e devolução de consumo de 100.000 no T1, mais T2, T3 e T4):
- T1 com excedente de 1.150.000: IRPJ sem LC 224 27.600,00, com LC 224 29.210,00, parcela 1.610,00.
- T2: 3.960,00; T3: 10.000,00; T4: 13.200,00. Caso II no IRPJ, com dedução de 700,00. Caso I na CSLL.
- O produto bate com o oráculo ao centavo, inclusive o rateio do excedente entre as duas atividades.

A fórmula da LC 224 é a do docstring de `presumido_calculo.py`. Não a reconferi contra a lei nesta rodada.

## Mutantes

71 mutantes, em duas camadas.

**Camada 1, dos mutantes de 14 itens.** Anel 0 são os `test_dl083_*` (12 arquivos). Anel 1 são os `test_dl081_*` e `test_dl079_*`. O anel 2 (`test_dl074_*` e `test_dl075_*`) foi rodado só nos 29 primeiros mutantes. Depois cortei, porque na rodada 1 nenhum mutante chegou a ele.

- **Resultado:** 61 mortos, 10 sobreviventes, 0 inaplicáveis.
- **Sobreviventes da rodada 1** (M25, N03, N06, M07b, N02, M11b, M11c, N10): **todos morreram** nos testes `test_dl083_*`.
- **Mortos no anel 0:** M25, N01 a N03, N06, N10, M07b/M07c, M11b, M11c e N02.

**Sobreviventes novos** (nos anéis 0 e 1; anel 2 só nos três primeiros):

| Mutante | Leitura |
| --- | --- |
| A03 peso negativo pesa no rateio | Gap real: não há teste com item de receita de valor negativo entre positivos. |
| A04 `ROUND_DOWN` no lugar de `HALF_UP` | Gap real: nenhum teste fixa o arredondamento. |
| A16 segregação pelo valor cru | Gap real: não há teste de segregação com rateio. |
| A18 `linhas_nfe_do_periodo` pelo valor cru | Gap real e relevante: é o caminho do Simples, do RBT12 e do Presumido. |
| A19 tela mostra a receita crua | Gap real: a tela não tem teste do valor atribuído. |
| R01 reversão recusa só rascunho | Gap real: nenhum teste do desenvolvedor reverte com nota efetivada. |
| R05 CHECK antigo sempre NOT VALID | Gap menor (efeito sem linha nova). |
| S12 `_primeiro_mes_com_devolucao` ignora a de consumo | Gap pequeno: afeta o saldo do Simples, que não trata combustível (D9). |
| G16 NCM 3403 fora da lista de lubrificante | Gap real: nenhum teste usa NCM 3403. |
| S02 receita negativa vira dedução negativa | Código defensivo; provável equivalente de fato. |

**Meus testes matam** A03, A04, A16, A18, A19, R01 e R05. **S12, G16 e S02 sobrevivem a eles também.**

Sem reexecução do anel 2 nos 42 mutantes restantes. Nenhum teste de DL-074 ou DL-075 é afetado pela correção (o desenvolvedor não os tocou).

## Testes alterados na correção

Os seis arquivos listados são **legítimos** e não enfraquecem a cobertura:

- `test_dl081_conferencia_w16.py`: o `vdesc` de volta à lista, que a rodada 1 apontou como enfraquecimento.
- `test_dl081_receita.py`: saem só as asserções de `receita_de_nfe_no_mes`, que foi removida (A7).
- `test_dl081_sugestao.py`: o item ganha NCM padrão, porque a sugestão passou a ler o NCM; a lista de devolução ganha a nova natureza.
- `test_dl083_combustivel.py`: 5.660 passa de False para True (agora devolução de compra, A1); a recusa vira o teste de aviso.
- `test_dl083_presumido_nfe.py`: o teste da recusa de devolução de combustível vira teste de aviso e de dedução na atividade certa.
- `test_dl083_telas.py`: o bloqueio de item fora do total vira teste de atribuição com aviso, e a recusa de combustível vira aviso.

Nenhum teste de DL-074, DL-075 ou DL-079 mudou.

## Verificações com números reais

| Verificação | Resultado |
| --- | --- |
| `ruff check --no-cache .` | "All checks passed!" |
| `ruff format --check --no-cache .` | "582 files already formatted" |
| `python manage.py check` | "System check identified no issues (0 silenced)" |
| `makemigrations --check --dry-run` | "No changes detected" |
| `migrate` em banco vazio; `migrate fiscal 0011`; `migrate fiscal` | OK; CHECK validado depois da reaplicação |
| `pytest`, 1ª invocação completa | `2 failed, 8764 passed, 53 skipped, 2 warnings, 4 subtests passed in 933.35s`. Falhas: a de ambiente (Python 3.13) e `test_concorrencia.py::test_corrida_real_de_evento_produz_um_unico_evento` (R8, sob carga). |
| `pytest`, 2ª invocação completa, máquina livre | `1 failed, 8765 passed, 53 skipped, 2 warnings, 4 subtests passed in 868.60s`. Falha única: `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, de ambiente. |
| A/B contra `148be40` (Simples e Presumido sem NF-e) | Simples **idêntico**. No Presumido, nenhuma linha removida ou alterada; só as cinco chaves novas (`devolucao_deduzida`, `devolucao_por_atividade`, `nfe`, `saldo_devolucao_transportado`, `saldo_por_atividade`), com valor vazio ou 0,00. |
| Consultas com 20 e 200 notas (3 itens, rateio ativo) | Iguais, sem N+1: `apurar_trimestre` T1 15 e T4 42; `controle_limite_ano` 40; `conferencia_do_mes` 4; `composicao_do_mes` 4; tela da apuração 20; tela da receita do mês 11. A tela da conferência deu 17 e 14, e cai com mais notas (efeito de sessão da primeira chamada). |
| Isolamento e permissões | Em API e tela: gestor, analista e paralegal leem (200); cliente 403; outro escritório 404; anônimo 403 na API e 302 nas telas. POST de estorno: cliente 403, outro escritório 404. |
| `pwsh ./scripts/validate-docs.ps1` | **Não testado**: `pwsh` não existe neste ambiente. |
| `git status` e `git diff --stat` da árvore auditada | Vazios. |

## O que não foi testado

- `validate-docs.ps1` (ver acima).
- Python 3.14, que é o da integração contínua; aqui rodou o 3.13.
- Concorrência de efetivações simultâneas (código não alterado).
- A fórmula da LC 224 contra a lei, e a conformidade jurídica da regra de saldo de devolução transportado entre trimestres, que o plano já declara como regra de produto.
- O enquadramento normativo de GLP, biodiesel e lubrificante no 1,6%. É o que o contador-senior registrou nas HI-139 e HI-140, com a SC Cosit 42/2026 lida só em fonte secundária.
- Navegador real e impressão.
- Anel 2 de mutação nos 42 mutantes finais.
- Se o MOC admite vDesc maior que vProd (R6).

Esta auditoria é de software e não substitui a validação profissional das regras contábeis e fiscais pelo contador.

## Casos de teste propostos

1. **R1:** `parametrize("natureza", NaturezaOperacaoNFe.values)` conferindo o limite na tela e na API. POST ponta a ponta da natureza `devolucao_combustivel_consumo` (tela `item` e `bloco`, API `naturezas` e `reclassificar`). Esperado: 302 e 200.
2. **R2:** `test_rc083_legado.py::test_remessa_pura_com_frete_efetivada_antes`. Esperado: as quatro funções e as telas sem exceção.
3. **R3:** `test_rc083_ajuste.py`, conforme a decisão do Fred.
4. **A04:** três itens iguais de revenda de 100,00 mais bonificação `indTot` 0 com frete de 0,02. Esperado: acréscimos de 0,00, 0,01 e 0,01.
5. **A03:** item de receita com `vDesc` maior que `vProd` (valor negativo) entre dois positivos, com resíduo positivo.
6. **A16, A18, A19:** `test_rc083_simples.py` (composição 1.090,00, segregação 654,00 e 436,00, RBT12) e `test_rc083_tela.py::test_tela_de_escriturar_mostra_a_receita_atribuida` (esperado "1.100,00" e "550,00" na tela).
7. **R01 e R05:** `test_rc083_migracao.py`, cenários 1 e 3 (reversão com efetivada recusa; sem linha nova, o CHECK volta validado).
8. **G16, S12, S02:** NCM 3403.19.00 com CFOP 5.656 (esperado revenda com aviso); devolução de consumo no Simples com `_primeiro_mes_com_devolucao`; receita negativa na atividade.

## Arquivos relevantes

- **Código auditado** (`/home/user/wt-rc083/apps/fiscal/`):
  - `itens_nfe.py`
  - `escrituracao_nfe.py`
  - `receita.py`
  - `presumido.py`
  - `cfop.py`
  - `ncm_combustivel.py`
  - `models.py`
  - `views_web.py` (limite de 24 em `:6812`)
  - `api_escrituracao_nfe.py` (limite de 24 em `:54`)
  - `migrations/0012_dl083_combustivel_revenda.py`
- **Meus testes e oráculo, descartáveis:** `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc083/copia/apps/fiscal/tests/` — `aud083_oraculo.py`, `rc083_base.py`, `test_rc083_atribuicao.py`, `test_rc083_devolucao.py`, `test_rc083_migracao.py`, `test_rc083_limite24.py`, `test_rc083_legado.py`, `test_rc083_ajuste.py`, `test_rc083_simples.py`, `test_rc083_tela.py`, `test_rc083_consultas.py`, `test_rc083_permissoes.py`, `test_rc083_2027.py`.
- **Mutantes:** `rc083/gerar_mutantes.py`, `rc083/mutantes_rc.json`, `rc083/mutar.py`, `rc083/mut_meus.py`, `rc083/todos.log`.
- **Logs:** `rc083/pytest_full.log`, `rc083/pytest_full2.log`.
