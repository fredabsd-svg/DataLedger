# DL-061 — DMPL: Demonstração das Mutações do Patrimônio Líquido (CTB-14)

**Demanda:** etapa CTB-14 da [DL-048](DL-048-contabilidade-anual-demonstracoes.md),
escolhida pelo Fred em 01/10/2026 (*"Dmpl"*). **Estado:** [fonte única](../agents/estado.md).
**Branch:** `claude/zealous-goldberg-jr5ggu` → `main`. **Risco:** nível 1 — demonstração
contábil entregue ao cliente; exige auditoria independente.

## Decisões do Fred que valem aqui

| Origem | Decisão |
| --- | --- |
| DL-048, decisão 1 | DLPA e DMPL são documentos separados, cada um com sua tela. |
| RC-137 | Uma coluna por **tipo** de reserva na DMPL. |
| 29/09/2026 | O item normativo citado **varia com a data de início do exercício** e o produto **prevê a adoção antecipada** da NBC TG 51. |
| **RC-151** (01/10/2026) | A linha (evento) da DMPL é descoberta **automaticamente** pela outra ponta do lançamento, como na DLPA; marcação manual só na exceção; quando o sistema não souber decidir, **recusa emitir** e lista o que falta. O escritório hoje deixa o padrão do sistema de referência e não reparte à mão. |

## Rotina de referência (manual do sistema de referência, lido em 01/10/2026)

Paráfrase, sem cópia (regras em [fontes-de-referencia.md](../projeto/fontes-de-referencia.md)):

- **p. 122:** a conta analítica recebe um "grupo DMPL" — é a coluna.
- **p. 620–622:** o escritório monta grupos e subgrupos (colunas); cada grupo tem uma
  lista de tipos de lançamento (as linhas), um deles marcado como padrão; um relatório
  confere as contas ligadas a cada grupo.
- **p. 192–194:** no lançamento, o valor vai sozinho para o tipo padrão do grupo da
  conta; o usuário só reparte à mão se quiser.
- **p. 773–774:** utilitário que refaz a classificação da DMPL num período.
- **p. 616–619:** emissão por período, valores negativos entre parênteses, opção de
  imprimir a estrutura sem movimento e de comparar com o período anterior.

**Diferença deliberada:** lá o padrão é **um por coluna**; aqui a linha sai da
**contrapartida**, como já faz a DLPA. Com isso, um dividendo debitado em lucros
acumulados vira "dividendos" sem ninguém repartir.

## Decisões de desenho (`arquiteto-senior`, reversíveis)

### E1 — Coluna: campo novo na conta exata

`Conta.classificacao_dmpl`, só para conta de tipo PL, **sem herança** (mesma regra D5
da DLPA). Enum, na ordem do item 111A da NBC TG 51 (106B da R5):

| Grupo do 111A | Membros (colunas) |
| --- | --- |
| Capital social | `capital_social` (inclui a retificadora "capital a integralizar") |
| Reservas de capital | `agio_na_emissao_de_acoes`; `alienacao_de_partes_beneficiarias_e_bonus_de_subscricao` |
| Ajustes de avaliação patrimonial | `ajustes_de_avaliacao_patrimonial` |
| Reservas de lucros | as seis da RC-137: legal, estatutária, para contingências, de incentivos fiscais, de retenção de lucros, de lucros a realizar |
| Ações ou quotas em tesouraria | `acoes_ou_quotas_em_tesouraria` |
| Lucros ou prejuízos acumulados | `lucros_ou_prejuizos_acumulados` |

- **Consistência com a DLPA:** conta com `classificacao_dlpa` de reserva de lucros ou de
  lucros/prejuízos acumulados tem de ter a mesma coluna na DMPL. `clean()` recusa a
  divergência e a apuração a acusa como pendência.
- **Fora das colunas:** a conta "Resultado do exercício" (`classificacao_dlpa =
  resultado_do_exercicio`) é conta de passagem do zeramento.
- **Reservas de capital do art. 182, §1º, "c" e "d":** **não** viram coluna. Foram
  revogadas pelo art. 10 da Lei 11.638/2007, como o Fred confirmou em 01/10/2026
  (RC-152, em [requisitos.md](../projeto/requisitos.md)).
- **Dividendo adicional proposto (RC-153):** o Fred confirmou que há cliente com essa
  conta no PL. A coluna entra **logo depois da fatia 1**, com linha própria e
  identidade com a DLPA (BL-603). Até lá, a emissão para esse cliente fica vetada,
  com a pendência explicando o motivo.
- **Correção monetária do capital realizado (art. 182, §2º):** não vira coluna, mesmo
  fundamento da DLPA (Lei 9.249/95, art. 4º, p.ú.).
- Só aparecem no documento as colunas com conta classificada.

### E2 — Linha: regra determinística por item

Para cada item de lançamento numa conta com coluna, olhar as **outras** partidas do
mesmo lançamento:

| Contrapartida | Linha |
| --- | --- |
| Conta "resultado do exercício" (zeramento) | Resultado do exercício |
| `classificacao_dlpa = dividendo` | Dividendos |
| `classificacao_dlpa = ajuste_de_exercicio_anterior` | Ajustes de exercícios anteriores |
| Outra coluna do PL | Movimento interno, pelo par de colunas: lucros acumulados → reserva de lucros = constituição de reservas; reserva → lucros acumulados = reversão de reservas; reservas ou lucros → capital = aumento de capital com reservas e lucros. Par sem regra = pendência. |
| Mesma coluna | Efeito líquido zero na coluna (ex.: subscrição contra capital a integralizar). |
| Fora do PL, sem classificação DLPA | Decidido pela coluna e pela direção: capital (crédito = aumento de capital; débito = redução); reserva de capital (crédito = constituição); ajustes de avaliação (outros resultados abrangentes); tesouraria (débito = aquisição; crédito = alienação ou cancelamento). Em reserva de lucros ou em lucros acumulados vira **pendência**, como a D3 da DLPA. |

- **Lançamento ambíguo vira pendência:** mais de uma coluna tocada e contrapartidas
  externas de classificações diferentes, de modo que a regra não atribui cada valor a uma
  linha só. Nunca há rateio presumido.
- O efeito de cada item na coluna é crédito − débito, como a D2 da DLPA.

### E3 — Uma leitura só para DLPA e DMPL

A coluna `lucros_ou_prejuizos_acumulados` da DMPL é apurada pela **mesma função** que
alimenta a DLPA. A lógica por item hoje embutida em `apurar_dlpa` é extraída para essa
função compartilhada **sem mudar o comportamento da DLPA**: os testes da DLPA passam sem
alteração de expectativa.

Teste de identidade obrigatório entre as duas demonstrações: mesmo saldo inicial, mesmo
saldo final e cada linha da DLPA no evento correspondente da DMPL.

| DLPA | DMPL |
| --- | --- |
| transferência para reserva | constituição de reservas |
| reversão de reserva | reversão de reservas |
| dividendo | dividendos |
| lucro incorporado ao capital | aumento de capital com reservas e lucros |
| resultado do exercício | resultado do exercício |
| ajuste de exercício anterior | ajustes de exercícios anteriores |

### E4 — Ordem das linhas

A norma não fixa a ordem (NBC TG 26 R5, itens 106(d) e 108). Adotamos esta, apoiada no
modelo do ITG 1000, Anexo 4:

1. Saldo no início do exercício
2. Ajustes de exercícios anteriores
3. Aumento de capital
4. Redução de capital
5. Aquisição de ações ou quotas em tesouraria
6. Alienação ou cancelamento de ações ou quotas em tesouraria
7. Constituição de reservas de capital
8. Resultado do exercício
9. Outros resultados abrangentes
10. Constituição de reservas
11. Reversão de reservas
12. Aumento de capital com reservas e lucros
13. Dividendos
14. Saldo no fim do período

Coluna "Total" à direita. Linha sem movimento em nenhuma coluna não é impressa.

### E5 — Conciliação com o Balanço, como exigência derivada

- Cada coluna: saldo final = saldo, no Balancete (`apurar_saldos`) da data final, das
  contas da coluna, com o sinal pela natureza.
- Total: total da DMPL + saldo das contas de passagem = PL do Balanço
  (`totais_por_tipo[PL]`).
- Divergência **veta a emissão** e nomeia as colunas.
- Saldo em "resultado do exercício" vira **aviso** de resultado não transferido, como na
  DLPA, e não veta.
- O texto do código descreve a conciliação como exigência **derivada** do item 106(d) da
  R5 (107(c) da TG 51), **não** como citação literal. Nenhum item manda isso em letra
  (ver requisitos, 29/09/2026).

### E6 — Período

Exercício de 01/01 até o fim do mês pedido, saldo inicial em 31/12 do ano anterior,
navegação por mês: mesma gramática da DLPA (D6). O comparativo com o exercício anterior
fica fora desta etapa.

### E7 — Norma por vigência, com adoção antecipada

- Exercício iniciado em ou após 01/01/2027 cita a **NBC TG 51**: itens 107 a 112 e 111A,
  identificação no item 27.
- Exercício anterior cita a **NBC TG 26 (R5)**: itens 106 a 110 e 106B, identificação no
  item 51.
- Campo novo `adota_nbc_tg_51_antecipadamente` (booleano) no `ParametroContabilEmpresa`
  vigente na data de início do exercício, alterado com trilha. Se marcado, um exercício
  anterior a 2027 cita a TG 51.
- A escolha fica numa função única (`norma_das_demonstracoes`), testada nas três
  situações. **Não** reutiliza o DE-010, que trata de arredondamento.

### E8 — Dividendo por ação

A NBC TG 26 (R5), item 107 (TG 51, item 110) aceita o dado na DMPL **ou** nas notas.
O produto não tem dado de ações nem módulo de notas. O documento declara, em rodapé, que
o valor por ação não é apresentado. Isso fica como limitação visível, não escondida.

### E9 — Fatias

1. **Fatia 1 (esta):** coluna na conta, apuração, emissão com veto, tela, classificação
   na tela do plano de contas, parâmetro de adoção antecipada e medição no navegador.
2. **Fatia 2:** marcação manual por lançamento para as exceções (a "guia DMPL" do
   sistema de referência), guardada fora do livro e com trilha; API de leitura e de
   classificação.

## Caso de referência (calculado à mão)

**Caso A**, o exemplo do Fred no plano de paridade: capital 100.000,00; lucro 25.000,00;
reserva legal 1.250,00; dividendos 10.000,00.

| Linha | Capital | Reserva legal | Lucros acum. | Total |
| --- | --- | --- | --- | --- |
| Saldo inicial | 100.000,00 | 0,00 | 0,00 | 100.000,00 |
| Resultado do exercício | — | — | 25.000,00 | 25.000,00 |
| Constituição de reservas | — | 1.250,00 | (1.250,00) | 0,00 |
| Dividendos | — | — | (10.000,00) | (10.000,00) |
| **Saldo final** | **100.000,00** | **1.250,00** | **13.750,00** | **115.000,00** |

**Caso B**, o A acrescido de:
- aumento de capital em dinheiro de 20.000,00;
- ajuste de avaliação patrimonial de +3.000,00;
- aquisição de ações em tesouraria de 2.000,00.

Saldo final:
- capital 120.000,00;
- reserva legal 1.250,00;
- ajustes de avaliação 3.000,00;
- tesouraria (2.000,00);
- lucros acumulados 13.750,00;
- total 136.000,00.

Conferência: 100.000 + 20.000 + 25.000 − 10.000 + 3.000 − 2.000 = 136.000.

## Critérios de aceite (fatia 1)

1. Casos A e B reproduzidos ao centavo, por emissão real com lançamentos e zeramento.
2. A coluna de lucros acumulados é idêntica à DLPA (saldo inicial, cada evento, saldo
   final) no cenário da DLPA e nos casos A e B. Toda a suíte da DLPA passa sem mudar
   nenhuma expectativa.
3. Conciliação por coluna e do total com o Balanço; divergência veta e nomeia as colunas.
4. Pendências que vetam, cada uma com teste e com link de correção para quem escritura:
   - conta PL com movimento ou saldo e sem coluna;
   - contrapartida sem classificação em reserva de lucros ou em lucros acumulados;
   - par de colunas sem regra;
   - lançamento ambíguo;
   - DLPA e DMPL divergentes na mesma conta;
   - valor fora do enum.
5. Norma citada: 2026 cita a R5; 2027 cita a TG 51; 2026 com adoção antecipada cita a
   TG 51.
6. Bloco de identificação do emitente repetido por página. A DMPL entra no piso de
   classe 2 da medição no navegador, com o cenário semeado emitível nos dois ramos.
7. Permissões e trilha:
   - leitura pelos papéis que leem a contabilidade; CLIENTE recebe 403;
   - classificar e marcar a adoção antecipada só quem escritura (o parâmetro, como hoje);
   - trilha em cada mudança.
8. Isolamento entre empresas nos dois sentidos: conta e lançamento de outra empresa nunca
   entram, e empresa alheia dá 404.
9. `Decimal` em todo o cálculo; negativo entre parênteses no documento.
10. Suíte completa, `ruff`, `check` e `makemigrations --check` limpos; contagens de rotas
    e varreduras de restrição e de admin atualizadas.

## Equipe e arquivos

1. `desenvolvedor-pleno`, primeiro. Arquivos:
   - `apps/contabilidade/models.py` (campo, enum, `clean`, parâmetro);
   - migrações 0018 em diante;
   - `apps/contabilidade/services.py` (leitura compartilhada, `apurar_dmpl`,
     `avaliar_emissao_da_dmpl`, `classificar_conta_na_dmpl`, `norma_das_demonstracoes`);
   - `apps/contabilidade/admin.py`;
   - `apps/core/restricoes.py`;
   - testes de serviço.
2. `especialista-frontend`, depois, sobre o contrato entregue. Arquivos:
   - `views_web.py`, `urls_web.py` e templates;
   - hub e menu;
   - tela do plano de contas e dos parâmetros;
   - `scripts/medir_identificacao_do_emitente.py`;
   - universo de telas e contagens de rotas.
3. `auditor-qa`, auditoria nível 1 sobre a versão integrada.

## Fora do escopo

- Marcação manual por lançamento e API: ficam para a fatia 2.
- Comparativo com o exercício anterior.
- Participação de não controladores e DMPL consolidada.
- Detalhamento dos outros resultados abrangentes por item (depende da DRA, CTB-16).
- Dividendo por ação (E8).
- Reservas de capital "c" e "d": revogadas (RC-152).

## Evidências e integração (fatia 1)

- **Servidor** (`desenvolvedor-pleno`, cópia isolada): campo e enum da coluna,
  migração 0018, leitura compartilhada extraída de `apurar_dlpa` sem mudar a DLPA,
  `apurar_dmpl`, `avaliar_emissao_da_dmpl`, `classificar_conta_na_dmpl`,
  `norma_das_demonstracoes` e `definir_adocao_antecipada_da_nbc_tg_51`, todos com
  trilha. Os casos A e B fecham ao centavo e a identidade com a DLPA vale nos
  casos A e B e no cenário da DLPA.
- **Tela** (`especialista-frontend`, cópia isolada):
  - a DMPL com identificação do emitente e a norma por vigência;
  - colunas agrupadas pelo item 111A;
  - origem de cada célula e conferência com o Balanço, só na tela;
  - impressão em paisagem com mais de 4 colunas;
  - classificação da coluna no plano de contas;
  - marca de adoção antecipada na tela de parâmetros;
  - hub e menu;
  - medição no navegador (piso de classe 2), emitível nos dois ramos da semente.
- **Decisões tomadas na implementação e aceitas pelo `arquiteto-senior`:**
  - pendência `nenhuma_coluna_classificada`, para não emitir DMPL vazia;
  - tabela de consistência DLPA × DMPL mais ampla que o E1:
    - resultado, dividendo e ajuste não admitem coluna;
    - lucro incorporado ao capital só combina com capital social;
  - reservas de capital → capital vira "aumento de capital com reservas e lucros",
    permitido pelo art. 200, IV, da Lei 6.404/76;
  - débito em reserva de capital contra conta de fora vira pendência;
  - lançamento com duas ou mais colunas exige uma "âncora" (um lado com um único
    nó). Se lucros acumulados participa, ele é a âncora; sem âncora, é pendência.
    É o que mantém a identidade com a DLPA;
  - a marca de adoção antecipada vale para a vigência inteira do parâmetro, e
    vigência nova herda a marca;
  - a marca fica com ADMINISTRADOR e GESTOR, a mesma regra da tela de parâmetros
    (RC-102), e não com todos os papéis que escrituram;
  - célula sem movimento sai "—".
- **Verificação dos implementadores:**
  - suíte completa: 4.450 aprovados, só com a falha conhecida de Python 3.13 local;
  - medição real no Chromium: `contabilidade_web:dmpl` passou nos dois ramos da semente;
  - 390 px sem rolagem horizontal da página;
  - impressão em 1 página A4 paisagem com 12 colunas.
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-061-rodada-1.md): **REPROVADA**. N1 e
  N2 (alta) atribuíam evento errado em vez de vetar; N3 a N11, de média e baixa
  gravidade.
- **Rodada única de correção** (servidor e tela em paralelo, em cópias isoladas;
  integrada em `40e47f5`). Decisões do `arquiteto-senior`, reversíveis:
  - **N1:** na coluna única, as contrapartidas sem classificação decisiva são somadas,
    e o líquido vira uma linha só, pela coluna e pela direção;
  - **N2:**
    - a classificação da DLPA só decide a linha onde faz sentido: resultado e ajuste
      só em lucros acumulados; dividendo só em lucros e nas reservas de lucros;
    - dividendo positivo em reserva vira pendência, salvo estorno;
  - **N3:** aviso de saldo na conta de passagem, na tela, e **nota no papel** com o
    valor e a diferença para o PL do Balanço;
  - **N4:** a pendência diz se a conta aceita coluna e orienta quando não aceita;
  - **N6:** a marca de adoção antecipada é recusada quando não teria efeito;
  - **N7:** débito e crédito na mesma coluna com outra partida é vetado **só nas
    reservas de lucros**, onde a DLPA detalha item a item. Nas demais colunas vale o
    líquido (ex.: subscrição com integralização parcial = aumento de capital);
  - **N8:** cancelamento de ações em tesouraria contra capital ou reservas usa a linha
    "alienação ou cancelamento";
  - **N5:** margem de 8 mm na paisagem, com a tabela de 12 colunas cabendo sem
    reduzir a letra;
  - **N10** e **N11** ajustados na tela.
- **Verificação na integração** (Python 3.13 local):
  - suíte completa com 4.513 aprovados;
  - 2 falhas conhecidas desta máquina: a de Python 3.13 e a soma de AGENTS.md das
    cópias de trabalho dos agentes;
  - os 317 testes da DMPL e da DLPA verdes;
  - propriedade P4 e ensaio diferencial DLPA × DMPL versionados.
- **Limite novo registrado:** em paisagem, o Chromium não repete a identificação do
  emitente numa segunda folha. Hoje a DMPL cabe numa folha (BL-621).
- [Reconferência](../auditorias/2026-10-01-dl-061-reconferencia.md): **APROVADA COM
  RESSALVAS**, parecer final. N1 a N11 fechados com evidência executada; DLPA idêntica
  em três versões; ensaio estrito com 870 DMPL emitidas sem violação. Ressalvas: BL-622
  a BL-625 (M1 a M4) e a validação contábil do Fred (BL-626).

## Fatia 2 — marcação manual por lançamento e API da DMPL (BL-605)

**Escopo:** a exceção prevista desde a RC-151 — quando a regra não decide, hoje a
emissão fica vetada e as mensagens dizem que a saída é "a marcação manual do
lançamento (fatia 2)". Esta fatia entrega essa saída, em **duas fatias internas**:
servidor (E15–E18, auditado em nível 1) e tela (E19, testes de comportamento).
**Nível 1** (muda número de documento entregue ao cliente): critérios de aceite,
testes de sucesso/erro/limite e auditoria independente, com UMA correção (§3.1).
**Branch:** `feat/dl-061-fatia-2` → `main`.

### Rotina de referência

O sistema de referência tem uma "guia DMPL" no lançamento (manual, p. 193–194):
o usuário reparte o valor à mão entre eventos, inclusive valores parciais em
lançamentos com vários débitos e créditos. A diferença deliberada continua a da
E1: aqui a marcação é a **exceção**, nunca o caminho normal.

### Decisões de desenho (arquiteto-senior, reversíveis)

**E15 — Marcação guardada fora do livro.** Modelo `MarcacaoDmpl` (app
contabilidade): lançamento (FK, `PROTECT` — o livro efetivado não se apaga),
empresa, `linha` (chave de `_TITULOS_DAS_LINHAS_DA_DMPL`), `coluna`
(`ClassificacaoDmpl`) e `valor` (`Decimal`), com autoria protegida e trilha na
mesma transação da gravação (padrão DL-052). Nada é gravado no lançamento: o
livro continua imutável, e a marcação é reclassificação da leitura.

**E16 — Contrato da marcação (o que mantém os números corretos).** O conjunto
das marcações de UM lançamento tem de reproduzir **exatamente** o efeito líquido
de cada coluna daquele lançamento (o `movimento` que a apuração já calcula):
Σ `valor` por coluna = efeito da coluna. Recusa fora disso, e recusa linha ou
coluna fora dos enums. Por construção, `saldo_final = saldo_inicial + movimento`
e a conciliação com o Balanço continuam valendo — a marcação muda AONDE o valor
aparece, nunca QUANTO existe.

**E17 — Só na exceção (RC-151 como propriedade).** A marcação só é aceita para
lançamento cuja atribuição automática produz **problema** (linha indefinida, par
sem regra ou lançamento ambíguo). Se a regra decide, o servidor recusa — o
escritório deixa o padrão, e "repartir à mão" não vira caminho normal. O
lançamento marcado usa as células da marcação **no lugar** das automáticas, e
os problemas dele deixam de vetar; o `movimento` continua o mesmo.

**E18 — API, no padrão das existentes.** `empresas/<id>/dmpl/<ano>/<mes>/`
(GET: a apuração inteira, o mesmo contrato da tela); `empresas/<id>/contas/
<conta_id>/classificacao-dmpl/` (PATCH: coluna da conta, espelho do D8 da DLPA,
com trilha); `empresas/<id>/lancamentos/<lancamento_id>/marcacao-dmpl/` (GET,
PUT com o conjunto completo — substituição atômica — e DELETE para limpar).
Permissões no servidor: quem lê a contabilidade lê; quem escritura marca;
CLIENTE 403; isolamento por escritório/empresa em todas as rotas.

**E19 — Tela.** Guia "DMPL" no detalhe do lançamento (as marcações dele, o
conjunto é gravado de uma vez) e o veto da DMPL passa a linkar para essa guia em
cada lançamento listado — as mensagens que hoje dizem "aguardar a fatia 2" ficam
com o caminho real. Identidade visual e permissões como as telas atuais.

### Decisões tomadas na implementação e aceitas pelo arquiteto-senior

- **Linhas de saldo não aceitam marcação** (`saldo_inicial`/`saldo_final`): são
  calculadas, não distribuídas — uma célula marcada ali sumiria do documento.
- **Marcação em coluna sem conta classificada é recusada**: a célula não
  renderiza no documento, e aceitar seria guardar decisão invisível.
- **O contrato E16 é por coluna**: um conjunto que reproduz o Σ por coluna é
  aceito, mesmo que distribua o valor em uma linha só onde a regra teria usado
  duas (ex.: −500 em "aquisição" no lugar do par bruto). É a marcação quem
  decide o par linha × coluna; o que não pode mudar é o QUANTO.
- **Defesa de leitura:** marcação que deixa de reproduzir o `movimento` (a
  classificação da conta mudou depois) volta para a regra automática e o veto
  acende — o documento nunca publica eventos que não fecham com o saldo.
- **Toda coluna marcada é movimentada pelo lançamento** (correção do achado A1
  da auditoria da fatia 2): um par líquido zero em coluna que o lançamento não
  move publicaria evento sem lastro no livro. A propriedade é derivada dos
  ITENS — não do efeito ≠ 0, porque a compra e venda de tesouraria de valores
  iguais no mesmo lançamento tem efeito zero e itens reais.
- **Residual declarado (achado A3, texto corrigido pelo achado N1 da
  reconferência):** a marcação gravada por ORM/SQL direto **vale na leitura
  mesmo em lançamento que a regra decide — o E17 NÃO é reaplicado na leitura**.
  É residual da classe "só ORM/SQL direto", como as constraints; o caminho
  normal (serviço/API) recusa esse caso (E17), e a defesa de leitura cobre A1
  (coluna movimentada), o Σ por coluna e a coluna não renderizável — não este.

### Critérios de aceite (fatia 2)

1. Um lançamento hoje vetado (`lancamentos_ambiguos`, eventos opostos, par sem
   regra ou contrapartida sem linha) **emite** depois de marcado, com as células
   exatas da marcação e o saldo/conciliação inalterados.
2. A marcação que não reproduz os efeitos por coluna é **recusada** (sucesso,
   erro e limites testados); lançamento que a regra decide **não** aceita marcação.
3. Marcar e desmarcar são atômicos, com trilha (atores e valores antes/depois),
   e nada muda no lançamento (imutabilidade preservada).
4. API: GET da DMPL igual ao contrato da tela; PATCH da coluna com trilha;
   PUT/DELETE da marcação; CLIENTE 403; empresa alheia 404; autorização no servidor.
5. Tela: guia do lançamento grava o conjunto e o veto da DMPL linka até ela;
   sem marcação, o comportamento atual não muda em nada. **Verificado na
   integração da fatia de tela (E19)**, que faz parte desta etapa (registro do
   achado A4 da auditoria: o critério não fica em aberto — ele é a tela).
6. Identidade DLPA × DMPL continua valendo com marcação na coluna de lucros
   (a marcação decide o par linha × coluna; o teste de identidade cobre o caso).
7. `ruff`, `check`, `makemigrations --check`, suíte completa e `validate-docs`
   limpos; migração nova criada e aplicada em banco vazio.

### Cenários de teste obrigatórios

- Marcação devolvendo o caso M3 (dividendo pago com reserva, estornado): o par
  marcado líquido zero libera a emissão e a linha mostra o líquido do par.
- Eventos opostos em tesouraria marcados em DUAS linhas (aquisição e alienação)
  com os valores brutos — a emissão sai e mostra os dois eventos.
- Marcação parcial inválida (Σ por coluna errado), linha/coluna fora do enum,
  marcação em lançamento de outra empresa, marcação em lançamento decidido pela
  regra, e marcação de CLIENTE: todos recusados, com a mensagem que diz o que falta.
- Desmarcar volta exatamente ao comportamento anterior (o veto retorna).

### Fora do escopo desta etapa

- Reconhecimento automático do par estornado (E14): a marcação manual é a saída
  prevista; a automação fica como melhoria futura registrada.
- Marcação por ITEM (repartição parcial dentro de um mesmo lançamento em mais de
  uma coluna além do efeito real): o contrato é por lançamento × coluna × linha.
- Comparativo com exercício anterior e dividendo por ação (E8).

### Evidências e integração (fatia 2)

- **Servidor (E15–E18):** modelo `MarcacaoDmpl` com migração `0020` (só criação
  — banco vazio e base anterior inalterada), serviços `salvar_marcacoes_da_dmpl`
  / `remover_marcacoes_da_dmpl` (transação única, trilha antes/depois,
  `select_for_update` como mutex), gancho em `apurar_dmpl` com defesa de leitura
  e API no padrão D8 (GET da DMPL, PATCH da coluna, PUT/DELETE da marcação).
  34 testes no arquivo da marcação.
- **Tela (E19):** guia "DMPL" no detalhe do lançamento (marcações, efeito por
  coluna, formulário do conjunto, remover), rota web nova, textos do veto
  apontando a guia, universo de telas e guardas de rota atualizados, 23 testes
  de comportamento. Sem CSS novo; sem JavaScript (direção de arte).
- **Testado:** 57 testes das duas fatias verificados no terreno; afetados com
  419–439 passed; `ruff check .` / `ruff format --check .` (353 arquivos) /
  `manage.py check` / `makemigrations --check` / `validate-docs` limpos; suíte
  completa com as falhas ambientais preexistentes (faixa 158–165, medido), sem
  nenhuma no escopo.
- [Auditoria independente e reconferência](../auditorias/2026-10-03-dl-061-fatia-2-auditoria-e-reconferencia.md):
  rodada única **APROVADA COM RESSALVAS** (A1 evento sem lastro, A2 chave
  extra, A3 residual, A4 processo), **correção única** (A1/A2 fechados nos dois
  lados, gêmeo legítimo preservado) e reconferência **APROVADA COM RESSALVAS** —
  ciclo do §3.1 encerrado; a ressalva N1 (texto do residual) foi corrigida na
  integração, como autorizado. A tela (E19) não foi auditada: nível 2, com
  testes de comportamento (§3.1 — auditoria só na primeira entrega do módulo).

## Consulta ao manual sobre as ressalvas da reconferência (01/10/2026)

Paráfrase, sem cópia. O manual responde **rotina**; norma continua com o Fred.

| Ressalva | O que o sistema de referência faz | Consequência aqui |
| --- | --- | --- |
| M2 — eventos opostos no mesmo lançamento (BL-623) | Sem ajuste manual, o valor inteiro vai para o tipo **padrão** do grupo. Não veta e não mostra o líquido por evento. A saída é repartir o valor à mão na guia DMPL do lançamento, que aceita valores parciais em lançamentos com vários débitos e créditos (p. 193–194). | A saída real é a marcação manual da fatia 2. Até lá, recusar é mais fiel à RC-151 do que publicar o líquido. Recomendação ao Fred: vetar. |
| M3 — o estorno não libera (BL-624) | O lançamento pode ser consultado, editado e excluído (p. 775). A classificação da DMPL pode ser refeita por utilitário (p. 773–774). | Aqui o livro é imutável. A correção é a marcação guardada fora do livro (fatia 2), e o texto atual, que manda estornar ou dividir, está errado. |
| Nota impressa do resultado não transferido (BL-626) | A DMPL aceita uma "declaração final" configurada pelo escritório, com variáveis, impressa no fim ou em todas as folhas (p. 619; parâmetros, p. 344). | Imprimir texto explicativo no documento é prática do sistema de referência. A nossa nota é automática e só aparece quando há saldo. |
| Ordem das linhas e colunas (BL-626) | Grupos, subgrupos e tipos de lançamento são montados pelo escritório. Não há ordem fixa. Há opção de imprimir a estrutura sem movimento e o saldo do período anterior (p. 616–622). | A ordem fixa do E4 é escolha de produto, a validar pelo Fred. |
| Lucros e prejuízos na mesma coluna (BL-626) | A estrutura da DLPA tem um tipo único "lucros/prejuízos", com rótulo diferente para lucro e para prejuízo (p. 609–610). | Apoia a coluna única. |
| Documento emitido congelado (BL-620) | A DMPL pode sair como anexo do Diário, do Razão ou do Balanço, com número do livro e folha (p. 301–306). O documento fica fixado no livro. | O congelamento vem com o módulo de livros, que ainda não existe. |
| Identidade DLPA × DMPL (M1, BL-622) | A DLPA tem estrutura própria, ligada a contas ou com valores informados à mão (p. 606–608). Não há garantia de identidade com a DMPL. | A identidade daqui é mais forte que a do sistema de referência. A M1 é defeito da nossa DLPA. |

Cancelamento de ações em tesouraria e reserva de capital incorporada ao capital: o
manual não define, porque a estrutura é livre. Ficam com o Fred.

## Etapa 2 — ressalvas da reconferência e a coluna da RC-153 (BL-603, BL-623, BL-624)

**Escopo:** a etapa curta prevista depois da fatia 1. **Nível 1** (demonstração
entregue ao cliente): critérios de aceite, testes de sucesso/erro/limite e
auditoria independente, com UMA rodada de correção (§3.1 do AGENTS.md).
**Branch:** `feat/dl-061-ressalvas` → `main`.

| Item | Origem | O que entrega |
| --- | --- | --- |
| BL-603 | RC-153 | Coluna "dividendo adicional proposto" na DMPL, linha da destinação e da aprovação, identidade com a DLPA |
| BL-623 | RC-155 (M2) | Lançamento com eventos opostos na mesma coluna é recusado; subscrição com integralização parcial continua como aumento líquido |
| BL-624 | M3 | Texto verdadeiro do veto (a saída é a marcação manual da fatia 2), com teste; avaliação do estorno com par exato |

### Base normativa (PE-75), consultada em 02/10/2026

- Página oficial do CPC da **ICPC 08 (R1) — Contabilização da Proposta de
  Pagamento de Dividendos** (aprovação 01/06/2012; aprovada pela CVM 683/12 e pelo
  CFC como ITG 08):
  <https://www.cpc.org.br/CPC/Documentos-Emitidos/Interpretacoes/Interpretacao?Id=17>.
- A interpretação trata o dividendo proposto **além do mínimo obrigatório** como
  valor que **permanece no patrimônio líquido, em conta específica do tipo
  "dividendo adicional proposto", até a deliberação dos acionistas** — paráfrase
  lida em fonte secundária que reproduz o ato da CVM; o texto oficial é PDF e
  **não foi lido integralmente** nesta etapa.
- Por isso **nenhum item numerado é citado** no código nem no documento
  (regra da PE-75). A PE-75 continua aberta só para a leitura do texto integral;
  a citação permitida aqui é por NOME da interpretação, com a fonte acima.

### Decisões de desenho (arquiteto-senior, reversíveis)

**E10 — Coluna nova fora dos grupos do item 111A.**
`ClassificacaoDmpl.DIVIDENDO_ADICIONAL_PROPOSTO` ("Dividendo adicional proposto"),
última da ordem do enum (após `lucros_ou_prejuizos_acumulados`), num grupo próprio
`GrupoDaDmpl.FORA_DO_ITEM_111A` ("Fora dos grupos do item 111A"): a coluna não é
membro dos grupos do 111A/106B e nasce de conta específica prevista pela ICPC 08
(R1) (RC-153), não de uma linha da norma de apresentação. Só conta de
Patrimônio Líquido (regra geral das colunas).

**E11 — Linha da destinação e da aprovação (com identidade por construção).**
Nova classificação `ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO`
("Dividendo adicional proposto"), só para conta de PL, e par obrigatório
DLPA `dividendo_adicional_proposto` × DMPL `dividendo_adicional_proposto`
(`COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA`); `dividendo` continua
admitindo nenhuma coluna.

| Evento | Lançamento | Linha da DMPL | Células | Linha da DLPA |
| --- | --- | --- | --- | --- |
| Destinação (proposta) | `D lucros acumulados / C dividendo adicional proposto` | "Dividendo adicional proposto" (novo par `_linha_do_par_de_colunas`, nos DOIS sentidos) | lucros `(X)`, coluna nova `+X`, total 0,00 | "Dividendo adicional proposto" (X) |
| Aprovação (transferência ao passivo) | `D dividendo adicional proposto / C dividendos a pagar` | "Dividendos" | coluna nova `(X)`, total `(X)` | nada (não toca a conta sujeito) |

- A aprovação chega à linha "Dividendos" por **dois caminhos que concordam**:
  contrapartida classificada `dividendo` (aceita em conta de PASSIVO) decide a
  linha, como na DLPA; contrapartida **sem** classificação cai na regra por
  direção da coluna nova (`_linha_pela_coluna_e_direcao`): débito = "Dividendos"
  (o proposto sai do PL); crédito livre **não** tem regra e vira pendência
  (a única fonte decidida de crédito é o par com os lucros acumulados).
- A reversão da destinação (`D dividendo adicional proposto / C lucros`) é o
  mesmo evento com sinal trocado (linha "Dividendo adicional proposto" positiva),
  como já vale para "dividendos".
- Ordem das linhas: a nova linha entra **antes** de "Dividendos" na DMPL e antes
  de "Dividendos distribuídos" na DLPA (a proposta precede a distribuição);
  na DLPA a linha só é impressa com movimento (como as de reserva).
- Identidade com a DLPA: `_LINHA_DA_DMPL_DAS_LINHAS_FIXAS_DA_DLPA` ganha o par
  `dividendo_adicional_proposto → dividendo_adicional_proposto`, e o critério 2
  vale por construção (mesma chave nas duas apurações).

**E12 — Eventos opostos na mesma coluna (BL-623, RC-155).**
O veto de coluna mista (N7) deixa de ser só das reservas de lucros:

- **Reservas de lucros:** continua como hoje — debitada e creditada no mesmo
  lançamento, com outra partida, é ambígua (a DLPA detalha item a item, M1).
- **Capital, reservas de capital, ajustes de avaliação, tesouraria e a coluna
  nova:** o lançamento que debita e credita a mesma coluna com outra partida
  fora dela é recusado **quando os dois lados têm contas de MESMA natureza
  cadastrada** — é o sinal de eventos opostos (aquisição × alienação de
  tesouraria; redução × aumento de capital): o líquido publicaria um número que
  não é evento nenhum.
- **Naturezas opostas nos dois lados não vetam:** é o par conta principal ×
  retificadora do MESMO evento — a subscrição com integralização parcial
  (`D capital a integralizar` devedora × `C capital social` credora) continua
  saindo como "Aumento de capital" pelo valor integralizado, e a subscrição pura
  continua com efeito zero.
- **Lucros acumulados continua de fora** (a DLPA também soma os itens; a exceção
  da identidade é o M1, BL-622).
- O veto cai em `lancamentos_ambiguos`, com motivo "eventos_opostos" nomeando a
  coluna, e a mensagem diz a verdade (E13).
- **Endurecimento da correção (achado A2 da auditoria da etapa 2):** na coluna
  de tesouraria o veto vale SEMPRE para débito e crédito com outra partida — a
  direção define eventos opostos por construção (débito = aquisição, crédito =
  alienação) e não existe par conta × retificadora de um mesmo evento ali (a E1
  não tem membro contra). O capital continua julgando pela natureza, porque a
  subscrição contra a retificadora é exatamente o par que a RC-155 manda manter
  líquido; o residual de natureza cadastrada fora do padrão no capital está
  registrado como BL-627, para validação do Fred.

**E13 — Texto verdadeiro do veto (BL-624).** As três mensagens
(`services.py` do dividendo positivo em reserva e dos lançamentos ambíguos;
ação da lista em `views_web.py`) deixam de mandar "estornar" ou "dividir o
lançamento" — o lançamento efetivado não se altera e o estorno não libera a
emissão. A saída dita é a **marcação manual por lançamento (fatia 2, BL-605)**.

**E14 — Estorno com par exato: avaliado, fica para a fatia 2.** Reconhecer o par
lançamento + estorno exigiria netting entre lançamentos em TODOS os vetos
(ambíguo, eventos opostos, dividendo em reserva) para o comportamento ficar
coerente, e hoje as células do par também não se completam — é exatamente o
mecanismo da marcação manual (BL-605), que é a exceção aprovada na RC-151.
Registrado como decisão; a BL-605 continua sendo a saída.

### Critérios de aceite (etapa 2)

1. **BL-603:** o cenário do cliente da RC-153 (conta de PL "dividendo adicional
   proposto" movimentada) passa de **emissão vetada** a emitível, com as duas
   linhas acima e valores ao centavo; destinação e aprovação aparecem em linhas
   DIFERENTES (o bruto não é apagado).
2. Identidade DLPA × DMPL mantida: mesmo saldo inicial, mesmo saldo final e cada
   linha da DLPA no evento correspondente da DMPL, agora incluindo a linha nova;
   a suíte da DLPA passa sem mudar expectativa.
3. Conciliação com o Balanço fecha com a coluna nova (saldo final por coluna e
   total); divergência veta e nomeia.
4. Padrão de consistência: DLPA `dividendo_adicional_proposto` só combina com a
   coluna `dividendo_adicional_proposto`; tipo fora de PL é recusado no
   `clean()`; divergência veta a emissão nomeando a conta.
5. **BL-623:** os dois cenários da M2 (compra e venda de tesouraria; redução e
   aumento de capital) são **recusados** (`lancamentos_ambiguos`, motivo
   eventos opostos), com o movimento líquido da coluna ainda correto; a
   subscrição com integralização parcial continua como "Aumento de capital" pelo
   valor integralizado e a subscrição pura continua sem pendência.
6. **BL-624:** após estornar o lançamento vetado, a mensagem não contém
   "estorne" nem "divida o lançamento" e diz que a saída é a marcação manual da
   fatia 2 (BL-605); a ação da tela também; os textos antigos não voltam.
7. Permissões, isolamento entre empresas e trilha: inalterados (a coluna usa os
   mesmos caminhos); `Decimal` em todo o cálculo; negativo entre parênteses.
8. `ruff`, `manage.py check`, `makemigrations --check`, suíte completa e
   `validate-docs.ps1` limpos; migração nova só de `choices`, se o Django gerar.

### Cenários de teste obrigatórios

- Destinação e aprovação (as duas linhas), aprovação com contrapartida
  classificada `dividendo` e com contrapartida sem classificação; crédito livre
  na coluna nova vira pendência; par sem regra envolvendo a coluna nova veta;
  reversão da destinação com sinal trocado; conta reclassificada libera a
  emissão do cenário da N4.
- M2: tesouraria comprada e vendida no mesmo lançamento (veto); capital reduzido
  e aumentado no mesmo lançamento (veto); subscrição com integralização parcial
  (líquido); subscrição pura (efeito zero); duas contas da mesma natureza nos
  dois lados (veto); conta principal × retificadora (não veta).
- M3: estorno do dividendo positivo em reserva e estorno do lançamento ambíguo —
  a mensagem diz a verdade; literal dos textos novos.

### Fora do escopo desta etapa

- Marcação manual por lançamento e API da DMPL (fatia 2, BL-605) — incluído o
  reconhecimento de par estornado (E14).
- BL-622 (M1, defeito da DLPA), BL-625 (M4), BL-604, BL-606, BL-607, BL-620,
  BL-621 seguem abertas, com responsável no backlog.
- Comparativo com exercício anterior, dividendo por ação (E8), fatias C e D da
  DL-027: inalterados.

### Evidências e integração (etapa 2)

- **Implementado** em `feat/dl-061-ressalvas`: coluna e linha novas (DLPA e
  DMPL), par exato de classificações, regra de eventos opostos (BL-623) com o
  endurecimento da tesouraria, textos verdadeiros do veto (BL-624), migração
  `0019_dl061_etapa2_dividendo_adicional_proposto` (só `choices`), 22 testes
  novos e 4 expectativas atualizadas (cada uma porque o comportamento pedido
  mudou, todas listadas na auditoria).
- **Testado:** 314 aprovados e 3 pulados (PDF/navegador, preexistentes) nos 7
  arquivos afetados; suíte completa com 4.321 aprovados e as 165 falhas
  **idênticas às da cópia limpa da `main`** (ambiente: SQLite em vez de
  PostgreSQL, Windows, poppler ausente — comparação registrada na entrega);
  migração aplicada em banco vazio; `ruff check`, `ruff format --check`,
  `manage.py check`, `makemigrations --check` e `validate-docs` limpos.
- [Auditoria independente e reconferência](../auditorias/2026-10-02-dl-061-etapa-2-auditoria-e-reconferencia.md):
  rodada única **APROVADA COM RESSALVAS** (A1 formato, A2 limite da
  propriedade, A3 guarda de texto), correção única aplicada e reconferência
  **APROVADA** — ciclo do §3.1 encerrado. Os números da RC-153 conferiram ao
  centavo com o cálculo à mão do auditor (sondas S1–S6).

