# Reconferência DL-046, fatia 2: apuração do carnê-leão, servidor e tela integrados

**Parecer: REPROVADO.** Um achado ALTO novo, na tela: o demonstrativo anual impresso corta a coluna "Imposto devido" e deixa "Valor a pagar" fora do papel. Há também cinco achados MÉDIOS novos. Os dois ALTOS e a maior parte dos MÉDIOS da rodada 1 estão fechados conforme a DE-091. O M-4 está **Parcial** e o M-8 está fechado para a lista da rodada 1, com lacunas novas registradas em R-M5.

- **Data:** 2026-09-27. **Auditor:** `auditor-qa`. **Nível de risco:** 1.
- **Versão auditada:** branch `dl046-f2-tela`, commit `bdc38da`, worktree `scratchpad/wt-dl046f2t`.
  - O worktree não foi modificado: `git status --short` e `git diff --stat` saíram vazios ao final.
- **Ambiente descartável:**
  - Clones `scratchpad/rec46f2` (suíte e mutantes) e `scratchpad/rec46f2i` (instrumento, PDF, lint e migrações), os dois com checkout em `bdc38da`.
  - Bancos descartáveis: `rec46f2i` (instrumento), `rec46f2p` (PDF), `rec46f2v` (migrações). A suíte, os mutantes e os experimentos rodaram no banco de teste do pytest-django (`test_rec46f2`, `test_rec46f2m`, `test_rec46f2x`, `test_rec46f2t`), criado e destruído pelo próprio pytest.
  - Clones e bancos foram apagados ao final (consulta a `pg_database` com `like '%rec46f2%'` → 0).
- **Evidências guardadas em `scratchpad/`:**
  - experimentos: `rec46f2_exp/test_rec_carne_leao.py`;
  - executor de mutantes: `rec46f2_mut.py` e resultado em `rec46f2_mut_dev.txt`;
  - PDFs: `rec46f2_pdfs/`, gerados por `rec46f2_pdf.py` com a base `rec46f2_seed_pdf.py`;
  - logs: `rec46f2-suite.txt`, `rec46f2_medir.log`, `rec46f2_testmedir.txt`.
- **Fontes conferidas no texto bruto:**
  - `pr_irpf_2026.txt`: tabela de jan–abr/2025 nas linhas 7930–7939; compensação do exterior nas linhas 4108–4121 e 4545–4562 (itens b/d e I–IV); P&R 427, linha 11477;
  - `exemplos15270_extraido.txt`, linha 412 ("mais vantajoso").

Auditoria de software não substitui a validação profissional do Fred.

---

## 1. Achados da rodada 1: situação

| Achado | Situação | Evidência (antes → depois) |
| --- | --- | --- |
| **A-1** notarial sem livro-caixa | **Fechado** | Emolumentos PF 20.000 com P10 12.000. Antes: dedução 0,00, excesso 12.000, imposto 4.424,29. Depois: dedução 12.000,00, excesso 0,00, forma real, **1.291,27**. O mutante N2 (tira o notarial do limite) morre. |
| **A-2** PJ fora do limite | **Fechado** | Jan: PJ 10.000 e P10 3.000; fev: PF 6.000. Antes: excesso de jan 3.000 e imposto de fev 0,00. Depois: excesso 0,00 e fev **394,54**. Casos meus que bateram: PJ 1.000 com P10 3.000 → excesso 2.000, fev 44,76; PJ com aluguel PF → dedução do livro-caixa 0,00. Mutantes N1, N3 e N4 morrem. |
| **M-1** escolha da forma | **Fechado** | Exemplos 1 e 2 pelo ORM. Antes: `real 2778.27` e `real 3626.59`. Depois: simplificado, base 2.428,80 e IR 0,00; simplificado, base 3.392,80 e IR 114,76. Empate (previdência 607,20) → simplificado, com "Deduções iguais…". Com 607,21 → real, 1.124,29. N5 e N6 morrem. Ressalva documental em R-B5. |
| **M-2** totais e rendimentos por código | **Fechado** | As chaves do anual passaram de `ano, empresa_id, meses` para `ano, empresa_id, meses, totais`. O mês ganhou `rendimentos`, `imposto_com_exterior`/`imposto_sem_exterior`, `vencimento`, `alertas` e `criterio_escolha_forma`. Com 12 meses de 2025, os oito totais são iguais à soma exata dos meses. N19 e N20 morrem. Ressalva em R-B5: a dedução aplicada por mês não vem do motor. |
| **M-3** exterior | **Fechado conforme DE-091** | EX 3.000, PF 6.000 e crédito 1.200: limite 1.004,75, compensação 1.004,75, devido 394,54, saldo **0,00** (antes 195,25). Maio sem pagamento: devido 1.399,29 (antes 1.204,04). Imposto pago sem rendimento do exterior → recusa (antes: compensação zero em silêncio). Afirmação do desenvolvedor: **verdadeira** (seção 3). Efeito colateral em R-M4. |
| **M-4** estorno | **Parcial** | Recebimento de jan/2026 estornado em 10/03: antes, `jan 6000/394,54, mar −6000/0,00`; depois, a recusa aparece (`LancamentoCaixaInvalido`), o estorno padrão sai datado de 10/01 e janeiro fica em 0,00. **Mas:** o alerta de defesa está errado (R-M1), e a recusa por mês diferente não tem teste (o mutante N9 sobrevive à suíte do desenvolvedor; R-M5). |
| **M-5** 2025 | **Fechado** | Tabela de jan–abr/2025 idêntica à P&R, linhas 7935–7939, com percentual 0,2500. Fev/2025 com 5.000: desconto 564,80, base 4.435,20 × 22,5% − 662,77 = **335,15**. Jun/2025 com 5.000: 312,89, sem redução. 2024 → mensagem explícita de fora do escopo. N11 e N12 morrem. Guarda perdida em R-B3. |
| **M-6** retificar dependentes | **Fechado** | Resultados da API (PATCH): 200 com trilha {antes 2, depois 3}; texto, número fracionário, booleano, negativo, 40000, 10³⁰, campo extra, corpo vazio, lista e não-JSON → 400; outra empresa do mesmo escritório, outro escritório e id inexistente → 404; PUT/DELETE → 405; PARALEGAL/CLIENTE → 403; empresa em modo contabilidade → 400. Na tela: sucesso e erros → 302 com mensagem; outro escritório e outra empresa → 404; GET → 405; PARALEGAL/CLIENTE → 403. Nenhum 500. A retificação muda a apuração (1.077,00 → 1.024,86). N14 a N18 e N22 morrem; N13 é equivalente (o `Model.clean()` também recusa). |
| **M-7** aluguel | **Fechado conforme DE-091** | O aviso do art. 42 aparece quando há `R01.003.001` no mês. N24 morre. HI-39 registrada. |
| **M-8** lacunas de teste | **Fechado para a lista da rodada 1** | Os 15 sobreviventes da rodada 1 (A2, A6, A8–A15, A17, A19, A21–A23) agora morrem na suíte do desenvolvedor. Há lacunas novas (R-M5). |
| **B-1** números no código | **Fechado** | Percentual gravado na vigência (migração 0005); N29 morre. `_LIMITE_DARF` registrado como exceção na DE-091, item 9. |
| **B-2** HI-36 | **Fechado** | Frase retirada em `requisitos.md` e na docstring. |
| **B-3** documentação | **Fechado** | DE-089 corrigida; HI-40 criada; frase "SEMPRE" corrigida no plano; `estado.md` alterado. |
| **B-4** mensagem de duplicidade | **Fechado**, com efeito colateral | A mensagem própria agora sai nos dois caminhos, mas diz "use a retificação (PATCH)" também na tela web (R-M2). |
| **B-5** vigência no dia 1 | **Fechado** | Cinco `CheckConstraint` presentes no banco (`pg_constraint`). |
| **B-6** vencimento | **Fechado** | Aparece "Último dia útil de 05/2026" para abril; dezembro de 2025 → 01/2026. N25 morre. |

**Os experimentos salvos da rodada 1, reexecutados em `bdc38da`:** 36 passaram e 4 falharam. As quatro falhas são exatamente as mudanças decididas na DE-091:
- saldo de 195,25 → 0,00;
- exterior sem rendimento → recusa;
- estorno em outro mês → recusa;
- 2025 → apura.

## 2. `carne_leao.py` reconstruído: leitura integral

Não achei trecho duplicado nem regra dos testes perdida. Comparei com `5ed0e5e`: o antigo `_limite_compensacao_exterior` virou `_imposto_sem_rendimento_exterior`, com o mesmo resultado. A checagem de tabela e dependente vigentes, o snapshot, o isolamento e a trilha de registro foram preservados.

Divergências encontradas:
- **R-B3:** a ausência de vigência de redução virou "legítima" para **qualquer** mês, não só 2025. A docstring do módulo (linhas 58–61) ainda diz que a ausência levanta erro.
- **R-M1:** o alerta não implementa o que o item 4 da DE-091 descreve.
- **R-B5:** a citação "P&R 267 … mais vantajoso" (linhas 547–550) é, na verdade, do documento "Exemplos de Aplicação da Lei 15.270/2025". No texto da P&R a frase não aparece.

## 3. M-3: a afirmação do desenvolvedor

**É verdadeira.**
- O crédito do mês é `min(pago, L)`, com `L = com − sem`.
- Como `sem ≥ 0`, vale `L ≤ com`.
- Com saldo inicial zero, então, compensação = crédito ≤ imposto do mês, e o saldo novo é sempre 0,00.
- Conferido por **20.000 casos aleatórios** em `_apurar_um_mes` (`test_rec_m3_saldo_sempre_zero_propriedade`): saldo sempre 0,00 e compensação sempre igual a `min(pago, limite)`.

Lógica e testes são coerentes. O `if mes == 12` só é alcançável com saldo forçado (`test_aud_a14…`), e o mutante A14 morre.

**Consequência a registrar:**
- A frase do item 3 da DE-091 ("só a parte compensável que exceder o imposto do mês passa aos meses seguintes") é **vazia** sob a própria definição.
- A regra de transporte da P&R (itens d/IV) só ganha efeito no caso de imposto pago em mês **posterior** ao rendimento (item II, linhas 4555–4557). É justamente o caso que a HI-38 recusa.
- A linha "Saldo de crédito do exterior levado ao mês seguinte" da tela é sempre 0,00 (R-B4).

---

## 4. Achados novos

### R-A1 — ALTO — O demonstrativo anual impresso corta "Imposto devido" e deixa "Valor a pagar" fora do papel

- **Requisito:** documento imprimível íntegro. A instrução desta reconferência já diz: "valor cortado é defeito, não limite". Afeta também o M-2, já que o total impresso precisa ser legível.
- **Local:**
  - `templates/livro_caixa/carne_leao_anual.html:84-91` (tabela de 10 colunas dentro de `.tabela-com-rolagem-horizontal`);
  - `static/css/base.css:3470` e `:3491` (`@media print`, que limita só a identificação);
  - `@page { size: A4 }`, em retrato.
- **Evidência:**
  - Base sintética de 12 meses de 2025 (`rec46f2_seed_pdf.py`), impressa pelo Chromium com `emulate_media("print")` em A4.
  - A tabela mede **1.197 px**, independentemente dos valores. A página A4 mede 794 px e a área útil com margem de 12,7 mm é de cerca de 698 px.
  - **Margem de 12,7 mm (impressão comum):** a coluna "Imposto devido" sai cortada no meio: `2.57` no lugar de 2.574,06 e `78.30` no total no lugar de 78.306,88. "Valor a pagar" some por inteiro: `pdftotext` não acha o cabeçalho nem o total. Captura: `rec46f2_pdfs/p_emp1_anual-1.png`.
  - **Margem 0 (o que o instrumento usa):** "Valor a pagar" sai `202.969,` e `5.042.937,` (sem centavos). Captura: `p_emp2_anual0-1.png`.
  - Medição no DOM sob mídia de impressão, em 794 px: fora da página ficam "Redução…", "Compensação exterior", "Imposto devido" e "Valor a pagar", com os valores e os totais.
  - O PDF tem 1 folha: não há continuação das colunas em outra página.
  - `scripts/medir_identificacao_do_emitente.py` **PASSA** (saída 0) porque mede só o timbre e a identificação, não as células de dados. A base dele também não tem carnê-leão.
- **Impacto:**
  - A coluna que o cliente paga não aparece.
  - Um valor truncado como `2.57` se lê como um valor válido (R$ 2,57), quando o certo é R$ 2.574,06.
  - O total do ano fica ilegível.
- **Correção recomendada** (decisão da `especialista-frontend`): folha em paisagem só para o anual (`@page` nomeada), ou largura mínima de coluna e tipografia próprias de impressão que caibam em 184,6 mm. Nunca esconder coluna.
- **Verificação:**
  - Gerar o PDF do anual com 12 meses e valores ≥ 1.000.000,00, com margem 0 e com 12,7 mm.
  - `pdftotext` precisa conter todas as células e totais das 10 colunas.
  - No DOM sob impressão, `max(td.right) ≤ largura útil`.
- **Teste proposto:** `test_carne_leao_anual_impresso_todas_as_colunas_cabem_na_folha`. Com Playwright, na mesma infraestrutura do instrumento: semear 12 meses; para cada `td`/`th` da tabela sob `emulate_media("print")` em viewport de 698 px, afirmar `getBoundingClientRect().right ≤ 698`; e afirmar que o texto do PDF contém `totais.valor_a_pagar` formatado. Idealmente, estender o instrumento para medir células de dados, não só a identificação.

### R-M1 — MÉDIO — O alerta de "rendimento líquido negativo" dispara em todo mês com rendimento menor que o desconto simplificado, inclusive mês vazio

- **Requisito:** DE-091, item 4 ("sinaliza mês com rendimento líquido negativo, como defesa" do M-4).
- **Local:** `apps/livro_caixa/carne_leao.py:624-632`. O código compara `rendimento − dedução escolhida`, e a dedução escolhida pode ser o simplificado.
- **Evidência:**
  - Mês sem lançamento: `alertas = ['… foi negativo (R$ -607,20) …']`.
  - Rendimento de 500,00: alerta de R$ -107,20.
  - Estorno correto no mesmo mês: rendimento 0,00, imposto 0,00, e o alerta aparece mesmo assim.
  - Ano com um único mês de receita: **11 de 12 meses** com alerta.
  - Na tela, o mês vazio mostra o "Aviso:" (`role="alert"`) junto com a mensagem de "Nenhum rendimento".
  - O teste `test_aud_m4_alerta_rendimento_liquido_negativo` fixa exatamente esse comportamento (400 de rendimento com 1.200 de previdência).
- **Impacto:** alerta falso crônico. O contador aprende a ignorar o aviso, e o caso que ele deveria sinalizar (rendimento sujeito negativo) não se distingue do ruído. O texto também escreve negativo como "R$ -607,20", fora da convenção do produto de negativo entre parênteses (RC-90).
- **Correção recomendada:** alertar só quando `rendimento_total_sujeito < 0` (o caso do M-4). Se o arquiteto quiser avisar "dedução real maior que o rendimento", usar outra mensagem, restrita às deduções reais e fora do mês sem movimento.
- **Teste proposto:** mês vazio → `alertas == []`; 500,00 → `[]`; estorno no mesmo mês → `[]`; rendimento sujeito negativo forçado por agregados → 1 alerta.

### R-M2 — MÉDIO — Identificadores internos do projeto no documento impresso e nas mensagens ao usuário

- **Requisito:** o documento emitido ao cliente cita a norma, não o backlog (`personalizacao-de-relatorio.md` e direção de arte). Achado trazido pelo `arquiteto-senior`; confirmado e ampliado pela varredura.
- **Local e evidência** (texto visível do HTML e `pdftotext` do PDF):
  - `carne_leao_mensal.html:150` mostra "(RC-132)"; `:195` mostra "(DE-091)"; `:304` mostra "(RC-133)". Os três saem no PDF.
  - Mensagem do motor em `carne_leao.py:481`: "(HI-38, requisitos.md)". Aparece no estado de erro da tela mensal e da anual (409) e na API.
  - `services.py:503`: "(RC-130)" na recusa do estorno. Hoje só pela API, porque a tela não envia data.
  - `dependentes_carne_leao.html:28`: "HI-35 … nesta fatia"; texto de ajuda em `views_web.py:1265`: "(HI-35)"; `models.py:754`: "(HI-35)" no erro de dia ≠ 1.
  - Mensagem de duplicidade (`restricoes.py:131`, `models.py:726`): "use a retificação (**PATCH**)". Aparece no formulário web, onde o botão se chama "Retificar".
  - Tela anual em estado normal: nenhum identificador.
- **Contexto:** o padrão já existe em telas de trabalho da contabilidade (RC-58, RC-101 a RC-104 em `fechamento.html`, `balanco.html` e outras). Fica registrado como observação fora desta fatia. Esta é a primeira vez que um número de **decisão** (DE-) sai impresso.
- **Impacto:** o documento do cliente cita referências que ninguém fora do projeto consegue abrir, e "PATCH" é jargão de HTTP.
- **Correção recomendada:** trocar pelo fundamento normativo (RIR/2018, P&R) ou por texto simples, e tirar "PATCH" e "nesta fatia" do que o usuário vê.
- **Teste proposto:** renderizar mensal, anual, dependentes e os estados de erro (HI-38, duplicidade, dia ≠ 1); no texto visível, sem comentários, afirmar a ausência de `\b(RC|HI|DE|PE|BL|DL)-\d+` e de "PATCH".

### R-M3 — MÉDIO — A memória de cálculo rotula dois valores diferentes como "limite da dedução do livro-caixa"

- **Requisito:** A-1/A-2 e DE-091, item 1 (o limite é a receita da atividade de qualquer origem).
- **Local:** `carne_leao_mensal.html:154` e `:158` ("— do qual, trabalho não assalariado (**limite da dedução do livro-caixa**)"), contra `:193-197` ("Receita da atividade … Limite da dedução do livro-caixa").
- **Evidência:** PF 6.000, PJ 2.000 e EX 3.000. A linha 154 mostra 6.000,00 como limite; a linha da receita da atividade mostra 8.000,00 como limite.
- **Impacto:** o documento de conferência contradiz a si mesmo exatamente na regra que motivou os dois achados ALTOS.
- **Correção recomendada:** os rótulos 154 e 158 viram "(integra a base)", sem mencionar o limite.
- **Teste proposto:** o texto "limite da dedução do livro-caixa" aparece uma única vez na memória.

### R-M4 — MÉDIO — A recusa da HI-38 bloqueia o resto do ano inteiro, não "este mês"

- **Requisito:** DE-091, item 3 e HI-38; P&R, item II (linhas 4555–4557: pagamento no exterior posterior ao rendimento, no mesmo ano, é compensável no mês do pagamento).
- **Local:** `carne_leao.py:477-483`. A exceção sobe dentro de `_apurar_ano_calendario`, que encadeia desde janeiro.
- **Evidência:** P20.01.00003 de 100,00 em maio, sem rendimento EX.
  - O mensal de **maio e o de setembro** levantam a exceção.
  - O anual de 2026 inteiro levanta a exceção.
  - Na tela: mensal 409, anual 409; na API: 400.
  - A mensagem diz "a apuração recusa **este mês**".
- **Impacto:** um caso previsto na P&R deixa o cliente sem nenhum carnê-leão de maio a dezembro. A única saída é estornar o pagamento, e aí o crédito some do carnê-leão.
- **Correção recomendada** (decisão do `arquiteto-senior` e do Fred): no mínimo, a mensagem deve dizer que os meses seguintes e o anual ficam bloqueados. De preferência, recusar só a **compensação** do mês, com alerta e sem crédito (leitura conservadora), sem interromper o encadeamento.
- **Teste proposto:** com o cenário acima, fixar o comportamento decidido para maio, setembro e o anual.

### R-M5 — MÉDIO — Lacunas de teste em regras de nível 1

- **N9:** retirar a recusa de estorno com data de outro mês → **sobrevive** a toda a suíte de `apps/livro_caixa/tests` (292 testes). A regra do item 4 da DE-091, que o plano diz testada, não tem teste. Morre com o meu `test_rec_m4_estorno`.
- **N21:** fazer a coluna "Dedução aplicada" da tela anual usar sempre as deduções reais → **sobrevive**. Morre com o meu `test_rec_tela_anual_deducao_da_forma_aplicada` (fev/2026: 6.000 com previdência de 100 → célula 607,20).
- **Correção:** implementar os dois casos (texto dos testes na seção 6).

### R-B1 — BAIXO — "4.664,69 a sem limite"

`carne_leao_mensal.html:239` e `:259`. A P&R escreve "Acima de 4.664,68" (linha 7939). Recomendação: "acima de 4.664,68" ou "a partir de 4.664,69".

### R-B2 — BAIXO — CAEPF sem máscara

`_identificacao_do_documento_carne_leao.html:25` imprime "CAEPF 11144477735001". O mesmo acontece em `_identificacao_do_documento.html:32` (Livro Caixa, fatia 1, já existente). Recomendação: máscara `999.999.999/999-99`, com teste.

### R-B3 — BAIXO — A guarda da vigência de redução se perdeu para 2026 em diante

- **Local:** `carne_leao.py:260-261` e `:776`.
- **Evidência:** apaguei `VigenciaReducaoCarneLeao` e apurei mar/2026 com 5.000. O resultado foi **312,89 sem erro**; com a vigência, o resultado é 0,00.
- **Divergência:** a docstring do módulo (linhas 58–61) e a de `_reducao_bruta` falam só de 2025.
- **Correção:** aceitar `None` só para competência anterior a 2026-01-01 e levantar `TabelaCarneLeaoNaoConfigurada` depois disso.

### R-B4 — BAIXO — Memória incompleta

- A parte do imposto pago no exterior que passa do limite (195,25 no caso de referência) some sem rótulo. A linha de saldo é sempre 0,00.
- A linha de dependentes não mostra o valor por dependente (189,59) nem a vigência.
- Com a redução ausente em 2025, a linha da redução não diz "sem vigência".

### R-B5 — BAIXO — Documentação e duplicação

- Citação da P&R 267 para "mais vantajoso": a fonte certa são os Exemplos (`carne_leao.py:547-550`; plano, item 2 da correção).
- Docstring de `carne_leao_anual` (`views_web.py:1189`) cita `_totais_anuais_carne_leao`, que foi removida.
- O plano diz que a tela devolve 400 para a HI-38; o código devolve 409.
- `_deducao_aplicada_do_mes_para_tela` (`views_web.py:1137`) repete a regra de `_deducao_aplicada_do_mes`. O motor deveria devolver `deducao_aplicada` por mês; é por essa repetição que N21 escapou.

### R-B6 — BAIXO — A retificação não trava a linha da empresa

`retificar_dependentes_carne_leao` verifica o modo por `Model.clean()`, mas sem `select_for_update` na `Empresa`. É a mesma corrida N6 que `registrar_dependentes_carne_leao` já fecha.

## 5. Mutantes

Executor em `scratchpad/rec46f2_mut.py`. Cada mutante foi aplicado no clone, rodado com `pytest -x apps/livro_caixa/tests` e revertido com `git checkout`.

| # | Mutação | Suíte do desenvolvedor | Meus casos |
| --- | --- | --- | --- |
| A2, A6, A8–A15, A17, A19, A21–A23 | Os 15 sobreviventes da rodada 1, readaptados ao código novo | **todos mortos** | — |
| N1 | Limite do livro-caixa sem PJ | morto | — |
| N2 | Limite do livro-caixa sem notarial | morto | — |
| N3 | Carrega a parte do limite sem base | morto | — |
| N4 | Livro-caixa deduz de qualquer base | morto | — |
| N5 | Empate vai para "real" | morto | — |
| N6 | Escolha pelo imposto final (critério antigo) | morto | — |
| N7 | Compensa acima do limite | morto | — |
| N8 | Sem a recusa da HI-38 | morto | — |
| **N9** | Estorno aceita data de outro mês | **sobreviveu** | morto |
| N10 | Estorno padrão no dia 28 | morto | — |
| N11 | Ausência de redução em 2025 vira erro | morto | — |
| N12 | Primeiro ano passa a ser 2024 | morto | — |
| N13 | PATCH sem o mixin do livro-caixa | sobreviveu | **equivalente** (`Model.clean()` recusa com 400) |
| N14 | PATCH com permissão de leitura | morto | — |
| N15 | PATCH na API sem isolamento | morto | — |
| N16 | Retificar na tela sem isolamento | morto | — |
| N17 | Retificação sem trilha | morto | — |
| N18 | Trilha com o "antes" errado | morto | — |
| N19 | Totais sem dezembro | morto | — |
| N20 | Total de deduções sempre pelas reais | morto | — |
| **N21** | Tela: coluna de dedução sempre pelas reais | **sobreviveu** | morto |
| N22 | Tela: retificar sem checar escrita | morto | — |
| N23 | Tela: critério fixo | morto | — |
| N24 | Tela: sem o aviso do aluguel | morto | — |
| N25 | Vencimento de dezembro no ano errado | morto | — |
| N26 | Alerta nunca emitido | morto | — |
| N27 | Tela anual sem checar leitura e modo | morto | — |
| N28 | Aluguel do exterior fora do exterior | morto | — |
| N29 | Percentual de 25% escrito no código | morto | — |

A24 (concorrência) não foi reaplicado; segue a limitação declarada.

## 6. Casos de teste propostos (texto, para o responsável implementar)

- **`estorno_em_outro_mes_recusado`:** receita de 10/01/2026, 6.000; `estornar_lancamento_caixa(l, data=date(2026,3,10))` → `LancamentoCaixaInvalido`. Sem data explícita → estorno datado de 10/01, e janeiro com rendimento e imposto 0,00. Mata N9.
- **`tela_anual_deducao_da_forma_aplicada`:** fev/2026: trabalho PF 6.000 e previdência 100 → na linha de fevereiro, a célula "Dedução aplicada" mostra 607,20. Mata N21.
- **`alerta_so_para_rendimento_negativo`:** os casos listados em R-M1.
- **`sem_identificador_interno`:** o caso descrito em R-M2.
- **`anual_impresso_cabe_na_folha`:** o caso descrito em R-A1.
- **`reducao_ausente_em_2026_levanta`:** sem vigência de redução, apurar mar/2026 → `TabelaCarneLeaoNaoConfigurada`.
- **`hi38_efeito_nos_meses_seguintes`:** fixar o que for decidido para maio, setembro e o anual (R-M4).

## 7. Testado, Inspecionado e Não testado

**Testado:**
- Suíte completa no clone: **`1 failed, 3293 passed, 46 skipped, 4 subtests passed`**. A única falha é `test_versao_minima_python.py` (Python 3.13 local), já conhecida.
- `ruff check`: "All checks passed!".
- `ruff format --check`: "305 files already formatted".
- `manage.py check`: 0 problemas.
- `makemigrations --check --dry-run`: "No changes detected".
- `migrate` em banco vazio: OK.
- Reversão das migrações do `livro_caixa` 0006 → 0005 → 0004 → 0003 → 0002 e reaplicação:
  - 2 tabelas/10 faixas → 1/5 → 1/5 → 0/0 → tabelas removidas;
  - reaplicado → 2/10, percentual 0,2500 nas duas vigências, restrições de dia 1 e de percentual presentes.
- `scripts/medir_identificacao_do_emitente.py`, em banco descartável semeado por `semear_base_de_medicao.py`: **saída 0**, todas as telas PASSOU, inclusive `carne_leao_mensal` e `carne_leao_anual`. Esse PASSOU não cobre as colunas de dados (R-A1).
- `pytest scripts/test_medir_identificacao_do_emitente.py`, com as variáveis pedidas: **136 passed**.
- Réplica em Python da validação de documentação: 173 arquivos válidos.
- Experimentos da rodada 1 (antes → depois) e 38 experimentos meus: casos à mão, propriedade de 20.000 casos do exterior, 2025, PATCH na API e na tela, papéis, isolamento, modo contabilidade.
- Tela:
  - critério impresso igual ao de `criterio_escolha_forma` do motor;
  - rendimentos por código e origem, com motivo de exclusão;
  - faixa e vigência;
  - vencimento;
  - alerta;
  - aviso do aluguel;
  - HI-38 como erro legível (409, sem 500);
  - estorno pela tela: 302, datado no mês do original.
- PDFs do mensal e do anual com 12 meses, com margem 0 e 12,7 mm.

**Inspecionado:**
- `carne_leao.py` inteiro, `views.py`, `views_web.py` (bloco do carnê-leão), três templates, o partial de identificação, `base.css` (impressão), `services.py` (estorno), `models.py`, `restricoes.py`.
- `views_web.py` e os templates não fazem soma nem cálculo tributário. As exceções são apresentacionais: alíquota × 100, flags `ha_*` e `sem_movimento`, e a seleção da dedução por mês (R-B5).

**Não testado ou bloqueado:**
- `pwsh ./scripts/validate-docs.ps1`: `pwsh` não existe no ambiente.
- Concorrência real (A24, R-B6).
- Firefox/Safari e leitor de tela.
- Comportamento real do Carnê-Leão Web.
- Validação profissional dos textos e das leituras da DE-091 (Fred).

## 8. Parecer

**REPROVADO.**

Não há terceira rodada. O fechamento por verificação independente exige, **no mínimo**:

1. **R-A1:** o anual impresso com as 10 colunas e os totais inteiros dentro da folha A4.
   - Refazer com `scratchpad/rec46f2_pdf.py` e a base `rec46f2_seed_pdf.py`, com margem 0 e 12,7 mm.
   - `pdftotext` precisa conter "Valor a pagar", "5.042.937,01", "78.306,88" e "2.574,06".
   - Nenhuma célula com `right` maior que a largura útil.
   - Teste automatizado correspondente.
2. **R-M1:** alerta corrigido e com teste. Mês vazio, 500,00 e estorno no mesmo mês sem alerta.
3. **R-M2:** nenhum identificador interno, nem "PATCH", no texto visível das três telas, dos estados de erro e do PDF, com teste de varredura.
4. **R-M3:** rótulos das linhas 154 e 158 corrigidos.
5. **R-M5:** testes que matem N9 e N21, conferidos com o executor `rec46f2_mut.py N9 N21`.
6. **R-M4:** decisão registrada pelo `arquiteto-senior` (e pelo Fred) sobre o bloqueio dos meses seguintes. No mínimo, uma mensagem que diga o alcance real do bloqueio.

R-B1 a R-B6 podem seguir como ressalvas registradas.

**Encaminhamento pelo `arquiteto-senior`:**
- `especialista-frontend`: R-A1, R-M2 (parte da tela), R-M3, R-B1, R-B2 e N21;
- `desenvolvedor-pleno`: R-M1, R-M2 (mensagens do motor e do serviço), R-M4 (depois da decisão), N9, R-B3 a R-B6.
