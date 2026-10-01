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
- **Reconferência:** pendente.

