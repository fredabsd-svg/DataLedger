# DL-062 — O sinal da conta-RAIZ retificadora no Balanço Patrimonial (BL-604)

**Estado:** em desenvolvimento
**Nível de risco (§3.1 do [AGENTS.md](../../AGENTS.md)):** **1 — o dinheiro e
o livro.** O Balanço Patrimonial é documento entregue ao cliente, e a correção
mexe no total por tipo que alimenta a equação contábil.
**Branch de trabalho:** `fix/dl-062-sinal-da-raiz-retificadora`
**Branch de destino:** `main`
**Origem:** BL-604, aberto pela DL-061 (fase 1, auditoria de 01/10/2026) e
levado pelo [estado do projeto](../agents/estado.md) como ponto aberto de
04/10/2026.

---

## 1. O problema, medido

Conta **retificadora** de Patrimônio Líquido — "(-) Ações em Tesouraria",
"(-) Prejuízos Acumulados" — cadastrada como **RAIZ** do plano de contas
(`conta_pai is None`, sem ancestral do grupo "Patrimônio Líquido") é **SOMADA**
pelo Balanço Patrimonial quando contábilmente tem de **SUBTRAIR**.

O sinal de um saldo vem da natureza da conta que o consolida (regra única de
saldo, DE-020, `services.py:3316`): a raiz do grupo aplica a natureza do
**grupo**. Quando a retificadora **é** a raiz, não há grupo — a natureza
**dela** (devedora) assina o próprio saldo, e `totais_por_tipo` soma esse
valor com o sinal que a contabilidade não lhe dá
(`services.py:3954-3961`).

### 1.1 Evidência executada (sonda, 04/10/2026, Python 3.14.7, SQLite)

Cenário: caso A da DL-061 (capital 100.000,00; lucro 25.000,00; reserva legal
1.250,00; dividendos 10.000,00) **mais** a conta "9 Ações em tesouraria"
(PL, **DEVEDORA**, `conta_pai is None`, coluna da DMPL
`acoes_ou_quotas_em_tesouraria`) com débito de 2.000,00 contra Caixa.

```
=== BALANCO ===
totais_por_tipo[PL]      = 117000          ← o certo é 113000
equacao                  = {'ativo': 123000, 'passivo': 10000,
                           'patrimonio_liquido': 117000,
                           'resultado_nao_transferido': 0,
                           'diferenca': Decimal('-4000')}   ← o certo é 0

=== O BALANCO E EMITIVEL? ===
pode_emitir              = True            ← ⚠️ SEM VETO
residuo_pendente         = {}
listas_pendentes         = {}
listas_informativas      = {}

=== DMPL ===
pendencias.diferenca     = [{'coluna': 'total',
                             'saldo_na_dmpl': 113000.00,
                             'saldo_no_balanco': 117000,
                             'diferenca': -4000.00}]
pode_emitir              = False
```

**Três consequências, na ordem do dano:**

1. **O Balanço é emitido errado e ninguém impede.** `pode_emitir = True`,
   resíduo zero, todas as listas de declaração vazias — e o Patrimônio
   Líquido sai **4.000,00 acima** do correto. O contador entrega ao cliente um
   Balanço com o PL inflado.
2. **A equação contábil não fecha**, e o próprio código a chama de "momento
   da verdade" (`services.py:3644`): `ativo ≠ passivo + PL`.
3. **A DMPL acerta e veta**, porque recalcula por conta
   (`_contribuicao_no_balanco`, `services.py:7108-7116`, devolve `−saldo`
   para conta não credora). Quem impede é a DMPL, **não o Balanço**.

### 1.2 Não é caso de PL: é uma CLASSE (mesma sonda, 04/10/2026)

Três contas-RAIZ com movimento, cada uma com natureza **oposta** à natural do
seu tipo, todas as três somando em vez de subtrair:

```
  ativo                -100
  passivo                 0
  patrimonio_liquido   100     ← devedora na raiz: somou
  receita              100     ← "(-) Devoluções" devedora na raiz: somou
  despesa              100     ← "(-) Descontos Obtidos" credora na raiz: somou
  DIFERENCA           -200     ← tem de ser 0
```

A retificadora na raiz é a **manifestação no PL** de um defeito de sinal que
atinge os cinco `TipoConta`.

---

## 2. Decisão de desenho (`arquiteto-senior`, reversível)

**D1 — O sinal da contribuição de uma RAIZ passa a ser o da natureza NATURAL
do seu `TipoConta`, nunca o da natureza cadastrada da própria conta.**

É a MESMA regra que a função já aplica, dois blocos abaixo, à soma por
classificação patrimonial (`services.py:4101-4108`, BL-496) e a mesma que a
DRE aplica ao resíduo por tipo (`NATUREZA_NATURAL_DO_TIPO_DRE`,
`models.py:660`). O Balanço ficava de fora dela; a correção é **levar a regra
existente até o total**, não inventar uma nova.

**D2 — Um mapa declarado, do tamanho do `TipoConta`, e não um `if` por tipo.**

`NATUREZA_NATURAL_DO_TIPO` (`models.py:317`) tem entrada só para Ativo e
Passivo, **de propósito** (`models.py:310-316`): ele responde "qual o lado
natural deste tipo, para a classificação circulante/não circulante", e
estendê-lo quebraria o teste derivado que confere as chaves
(`test_dl033_classificacao_patrimonial.py:137`). Nasce então
`NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO`, com os **cinco** `TipoConta`, mais um
teste derivado exigindo `chaves == TipoConta.values` — o molde que o projeto
já usa duas vezes. Um `TipoConta` novo aparece com zero, em vez de ficar de
fora em silêncio.

**D3 — A correção é POR NATUREZA, nunca pela coluna da DMPL.**

A coluna (`classificacao_dmpl`) é `null=True` por padrão, não tem direção
declarada em lugar nenhum do código (verificado: nenhum símbolo mapeia coluna
→ direção), e o caminho do sinal do Balanço tem de ser o mesmo da equação
contábil. Implementar por coluna criaria a **segunda fonte de verdade** que
esta etapa existe para remover.

**D4 — A anomalia é DECLARADA, nunca corrigida em silêncio.**

A soma deixa de ser ingênua, então o produto passa a **nomear** cada RAIZ cuja
contribuição entrou com sinal invertido, em `contas_retificadoras_rais`, e a
Balanço a expõe em `listas_informativas` (avisa, **não** veta): depois da
correção o número está certo, e a topologia é incomum — o contador merece
saber que existe uma conta assim, não que o sistema esconda que mexeu nela.

**D5 — O invariante documentado é REESCRITO, não contornado.**

`test_raiz_de_cada_linha_e_exatamente_nivel_igual_a_um`
(`test_dl032_camada_de_saldos.py:1077-1093`) afirma que
`Σ(saldo das raízes) == totais_por_tipo`. Ele **continua verdadeiro** e passa a
ser reproduzido com a normalização do sinal. O contrato muda de forma
(documentado no próprio teste), não de verdade: a soma ingênua deixa de ser a
leitura certa — que é exatamente o que `services.py:3754-3761` já advertia.

**D6 — A apresentação impressa NÃO muda, e não precisa.**

`_linha_de_conta_do_balanco` (`views_web.py:3855-3871`) imprime o valor
**absoluto com a letra** D/C, nunca o sinal (RC-61/BL-77), e
`_subtotal_do_balanco` (`views_web.py:3874-3888`) já usa a natureza CREDORA
para o PL. Depois da correção a conta devedora aparece "2.000,00 **D**" sob
"115.000,00 **C**", com subtotal "113.000,00 **C**" — que é a apresentação
correta de linha de dedução, sem número negativo e sem sinal inventado.

### 2.1 A opção que foi DEIXADA de fora, e por quê

O backlog aceitava "Balanço e DMPL coerentes com retificadora na raiz, **ou
recusa do cadastro**". A recusa do cadastro foi **avaliada e descartada**:

- não corrige dado **já gravado** — a base que tem a conta continua divergindo
  e continua emitindo Balanço errado, e `Conta.clean()` não roda na leitura
  (medido: a apuração não levanta `ValidationError`);
- colide com a decisão de produto **RC-80** (`views_web.py:961-999`), que hoje
  **avisa** e deixa criar conta sem conta-mãe;
- precisaria da regra em três portas (`clean()`, serializer, formulário),
  contra o §8 do AGENTS.md ("evitar duplicação de regras").

---

## 3. Critérios de aceite

1. `totais_por_tipo[PATRIMONIO_LIQUIDO]` = **113.000,00** no cenário de §1.1
   (hoje 117.000,00) e **não** 115.000,00 — a soma ingênua.
2. `equacao["diferenca"]` = **0,00** no mesmo cenário (hoje −4.000,00).
3. A classe inteira: RAIZ devedora de RECEITA e RAIZ credora de DESPESA também
   subtraem, e a equação fecha (hoje −200,00).
4. **`avaliar_emissao_do_balanco` continua devolvendo `pode_emitir = True` no
   cenário corrigido** — a correção é do número, não um veto novo.
5. **A DMPL passa a ser aprovada** no cenário: `pode_emitir is True` e
   `pendencias["diferenca_de_fechamento"] == []`.
6. **Controle positivo obrigatório:** a retificadora aninhada
   (`test_retificadora_dentro_do_patrimonio_liquido_subtrai_nunca_soma`,
   `test_dl032_camada_de_saldos.py:904`) **continua verde e com o mesmo
   valor** — sem ele a suíte não distingue "corrigiu" de "inverteu tudo".
7. `contas_retificadoras_rais` nomeia a conta, e a lista entra em
   `listas_informativas` (avisa) **sem** entrar em `listas_pendentes`.
8. `NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO` tem **exatamente** as chaves de
   `TipoConta.values`, por teste derivado.
9. O mapa novo **não** altera `NATUREZA_NATURAL_DO_TIPO` nem
   `NATUREZA_NATURAL_DO_TIPO_DRE`, e os testes derivados dos dois continuam
   verdes.

## 4. Cenários de teste obrigatórios

| # | Cenário | O que prova |
| --- | --- | --- |
| 1 | RAIZ PL devedora com movimento | critérios 1, 2, 4 |
| 2 | Mesma raiz, com a DMPL apurada | critério 5 (defeito fechado, não só número) |
| 3 | RAIZ RECEITA devedora e RAIZ DESPESA credora | critério 3 (a classe) |
| 4 | Retificadora **aninhada** (o caso do projeto) | critério 6 (no-op na árvore correta) |
| 5 | Árvore sem anomalia nenhuma | nenhum total muda |
| 6 | `contas_retificadoras_rais` nomeada e informativa | critério 7 |
| 7 | Derivado das chaves do mapa | critério 8 e 9 |
| 8 | Malteus: inverter tudo; normalizar pela coluna; normalizar por `if` de tipo | o teste falha |

## 5. Fora do escopo

- Corrigir, por migração, base que já tenha a retificadora na raiz. A
  correção faz o número sair certo; **reorganizar o plano de contas é decisão
  do escritório**, e o produto passa a dizer na tela que existe a anomalia.
- BL-606, BL-607 e BL-625: medidos em 04/10/2026, os três são **triviais**
  (dois pontos em um arquivo, um arquivo de teste, um arquivo de tela) e
  **não cabem nesta etapa** — que é de nível 1 e muda o total do Balanço.
  Seguem abertos, com o escopo medido.
- BL-627 e BL-626: decisão e validação do Fred.

## 6. Reversão

Reverter o commit de `services.py` e `models.py` restaura o comportamento
anterior. **Não há migração**: nenhum schema muda, nenhum dado é gravado. A
mudança é de leitura, e a reversão é um `git revert` do PR.

## 7. Riscos declarados

| Risco | Mitigação |
| --- | --- |
| Inverter o sinal de toda raiz, não só da retificadora | critério 6 + cenário 5: a árvore normal não tem raiz de natureza oposta, e o controle positivo fixa o valor |
| Total corrigido, linha impressa não | critério 4 e D6: a linha já imprime valor absoluto com letra D/C; o subtotal já é CREDORA |
| Duas fontes de verdade do sinal | D3: por natureza, o mesmo referencial da equação e da DMPL |
| Regressão na DLPA/DRE/DMPL | suíte completa + os testes derivados dos outros dois mapas (critério 9) |

## 8. Evidências e integração

### 8.1 Diagnóstico (04/10/2026, antes da correção)

Sonda temporária, já removida do repositório, com o cenário de §1.1 e o da
§1.2. Saída real transcrita em §1.1 e §1.2.

### 8.2 Prova de que os testes reprovam sem a correção

| Teste | Sem a correção | Com a correção |
| --- | --- | --- |
| `test_dl062_...` (arquivo novo, 13 testes) | **erro de coleta** — `NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO` não existe | 13 passed |
| `test_a_retificadora_de_pl_fora_do_grupo_nao_veta_mais_a_dmpl` (tela, ponta a ponta) | **FAILED** | passed |
| `test_a_diferenca_de_fechamento_nao_aponta_uma_causa_que_deixou_de_existir` | passed (é teste de texto) | passed |

O primeiro é fraco como prova (falha por importação, não por comportamento);
o **segundo** é a prova comportamental: usa só imports que já existiam, falha
porque a DMPL **veta** o cenário e deixa de vetar com a correção.

### 8.3 Verificações executadas (04/10/2026, Python 3.14.7, SQLite local)

```
test_dl062_sinal_da_raiz_retificadora.py                13 passed
test_dl061_tela_dmpl_correcoes.py + test_dl034 + test_dl032
  + test_dl033 + test_dl061_dmpl.py                     194 passed, 3 failed*, 3 skipped
apps/core                                                767 passed, 16 failed*
apps/contabilidade + apps/core                           80 failed (base: 81)
apps (suíte inteira)                                     161 failed (faixa ambiental registrada: 160–165)
ruff check .                                             All checks passed!
ruff format --check .                                    354 files already formatted
manage.py check                                          System check identified no issues
manage.py makemigrations --check                         No changes detected
scripts/validate-docs.ps1                                Documentação válida: 219 arquivos
```

\* **Falhas pré-existentes, não desta etapa.** Comparadas item a item contra
uma execução da MESMA seleção **sem** a mudança: em `apps/contabilidade` +
`apps/core` são **80 com a correção contra 81 na base** — a etapa **removeu**
uma falha (a do veto da DMPL, agora com o comportamento correto) e **não
acrescentou nenhuma**. Em `apps/core` as 16 são exatamente as da base. As três
falhas da lista acima (`test_precisao_decimal_com_valores_que_quebram_float`,
`test_apurar_balanco_patrimonial_devolve_os_tres_ingredientes`,
`test_dl034_com_o_wrapper_o_snapshot_protege_da_diferenca_fantasma`) estão na
base.

⚠️ **`test_b2_concorrencia_entre_meses_diferentes_nunca_conta_em_dobro`**
(`test_dl043_correcao_rodada1.py`) aparece ora e ora não nos dois lados: é
**flaky de ambiente** (`database table is locked` do SQLite com 15 threads).
Medido **sem** a mudança, em 4 execuções: **3 falhas** — não é regressão. A CI
roda PostgreSQL 16.

### 8.4 O que mudou fora do escopo declarado, e por quê

Um item: **o texto da dica da divergência de fechamento**
(`views_web.py`, `ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA`). Ele
afirmava que a causa mais provável da divergência era a retificadora de PL
fora do grupo — causa que **esta etapa elimina**. Deixar o texto seria
entregar ao contador uma afirmação falsa, mandando-o procurar um defeito que
o produto não tem mais. O texto passou a dizer o que continua sendo verdade
(as duas peças leram as mesmas contas de formas diferentes; a diferença nunca
é ajustada para fechar). **O BL-625 segue aberto** — ele pede *condicionar* a
dica ao caso real, o que é mais do que esta correção de texto.

### 8.5 Contrato alterado, de propósito

`apurar_saldos` ganhou a chave `contas_retificadoras_rais`, na lista
`_LISTAS_QUE_SO_AVISAM`. Três testes de contrato foram atualizados, como o
**próprio docstring do BL-492** determina quando `apurar_saldos` ganha uma
chave: `test_bl492_congelamento_das_chaves_de_apurar_saldos`,
`test_bl515_a_tupla_de_veto_preserva_as_travas_revisadas` e o par
`test_de070_*`/`test_residuo_sozinho_*` (via o inventário mínimo). Nenhuma
expectativa de **número** foi tocada.

### 8.6 Auditoria independente

Obrigatória por ser nível 1 (§3.1). Relatório em
[`docs/auditorias/2026-10-04-dl-062-auditoria.md`](../auditorias/2026-10-04-dl-062-auditoria.md):
**APROVADO COM RESSALVAS**, os **9 critérios de aceite SEDE**, nenhum
bloqueador, **zero regressão** medida pelo próprio auditor (63 falhas com a
correção contra 74 sem, num par de suites de `apps/contabilidade`).

Oito achados, todos de tela/documento ou de verificação: **A1** (média) e
**A2** (média) — a lista informativa nova não tinha nome humano nem ação na
tela, e nomeava raiz retificadora com saldo zero; **A3** (baixa) — o plano
linkava um relatório que ainda não existia; **A4** (baixa) — docstring dizendo
"um nome" para uma tupla de dois; **A5** (baixa) — segunda fonte de verdade
para o sinal, no ternário do subtotal impresso; **A6** (baixa) — o teste de
contrato do BL-515 tinha sidorelaxado para comparação de conjunto; **A7**
(baixa) — a apresentação impressa não tinha guarda; **A8** (baixa) — arquivo
de artefato na raiz do repositório.

**O ciclo do §3.1 encerrou com UMA correção**, aplicando A1 a A8 — a regra
proíbe terceira rodada, e nenhum deles exigia reabrir critério.

### 8.6.1 O que a CI encontrou e o SQLite local não conseguia ver

A **primeira execução da CI (PostgreSQL 16)** reprovou **um** teste:
`test_dl034_tela_do_balanco.py::test_bl516_duas_raizes_de_mesmo_tipo_exibem
_aviso_generico_sem_ancestral_comum`, que exigia que o Balanço fosse **vetado**
por resíduo de 200,00.

O arquivo inteiro não roda localmente (14 falhas idênticas com e sem a
mudança: `SET TRANSACTION ISOLATION LEVEL` não existe no SQLite), então a
verificação local **não podia** ver isso — e a suíte local "verde" era
enganosa nesse ponto. A medição do cenário mostrou que o 200,00 **era o
defeito**: "(-) PDD Raiz" é uma retificadora na raiz do Ativo, e o Balanço
somava o crédito dela como acréscimo (Ativo em 1.100,00 quando o correto é
900,00). O resíduo aritmético era, sem querer, a **única rede** que pegava a
conta — exatamente o mesmo defeito do BL-604, no Ativo. Corrigido, o resíduo
zera, a equação fecha e o Balanço emite com o número certo; o teste foi
reescrito para afirmar o comportamento corrigido, mantendo o que o BL-516
pedia: o aviso **continua visível** e nomeando as duas raízes.

### 8.6.2 Correção única (A1 a A8)

| Achado | Correção |
| --- | --- |
| A1 | Nome humano e ação (de **confirmação**, não de correção) em `NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO` e `ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA`; campo `natureza_natural_do_tipo` com rótulo e enum |
| A2 | A lista nomeia só a raiz com saldo **diferente de zero**; `saldo`/`contribuicao_no_total` saíram do item (o valor já está impresso na linha do Balanço) |
| A3 | Resolvido pela existência do relatório de auditoria |
| A4 | Docstring corrigido ("dois nomes") |
| A5 | `_subtotal_do_balanco` passa a ler `NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO` — mesma declaração de `apurar_saldos` |
| A6 | O teste do BL-515 voltou a comparar a **tupla**, não o conjunto |
| A7 | Quatro testes novos, entre eles a montagem **impressa** do Balanço com a retificadora na raiz (`115.000,00 C` + `2.000,00 D` = `113.000,00 C`) e o grande total impresso batendo |
| A8 | Arquivo de artefato removido da raiz |

Depois da correção: `apps/contabilidade` + `apps/core` com **79 falhas**
contra **81** da base original — nenhuma regressão e mais uma falha resolvida
pela própria correção.

### 8.7 Integração

Commit, push e PR: pendentes.

