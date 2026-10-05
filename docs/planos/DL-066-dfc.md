# DL-066 — DFC: Demonstração dos Fluxos de Caixa, direto e indireto (CTB-15)

**Demanda:** etapa CTB-15 da [DL-048](DL-048-contabilidade-anual-demonstracoes.md),
escolhida pelo Fred em 05/10/2026, na esteira da DL-061 (DMPL). **Estado:**
[fonte única](../agents/estado.md).
**Branch:** `feat/dl-066-dfc` → `main`. **Risco:** **nível 1** — demonstração
contábil entregue ao cliente, com conciliação obrigatória com o Balanço
(CPC 03, item 45). Exige plano, critérios de aceite, testes de sucesso, erro e
limite, e **auditoria independente**.

## Decisões do Fred que valem aqui

| Origem | Decisão |
| --- | --- |
| **05/10/2026** | O escritório quer o método **direto e o indireto**, não um só. Registrado no mapa de paridade como pergunta em aberto; a resposta fecha o escopo. |
| DL-047, recomendação A | Fechar a **Onda 1** usa uma base que já existe (saldos, DRE, Balanço) e entrega o pacote de demonstrações que o escritório emite todo ano. A DLPA e a DMPL já estão; falta a DFC. |
| RC-137 / RC-151 (padrão das etapas anteriores) | A mesma postura das outras demonstrações: o sistema **propõe** pelo movimento, o contador corrige só na exceção, e quando não dá para decidir o produto **recusa emitir** e **nomeia** o que falta. |

## Base normativa — conferida nesta sessão, item a item

⚠️ **Afontes oficial que declarei aberta está fechada.** A verificação anterior
havia lido o CPC 03 de fonte secundária. O texto integral do
[CPC 03 (R2)](https://www.normasbrasil.com.br/norma/?id=306227) foi lido nesta
seção, e cada afirmação abaixo aponta o item. A NBC TG 03 (R3) do CFC é a
versão nacional do mesmo pronunciamento.

| Item | O que a norma exige | Onde entra nesta demanda |
| --- | --- | --- |
| **6** | *Caixa* é numerário e depósitos bancários disponíveis; *equivalentes de caixa* são aplicações financeiras de curto prazo, prontamente conversíveis, de insignificante risco; define as **três atividades** (operacional, investimento, financiamento) | A classificação de atividade da conta, e a lista de "caixa e equivalentes" |
| **7** | Equivalente de caixa é, em regra, vencimento de **três meses ou menos** | Pergunta 1: o que o produto declara como equivalente |
| **9** | **"Os fluxos de caixa excluem movimentos entre itens que constituem caixa ou equivalentes de caixa"** | A regra que separa "transferência entre contas da empresa" de fluxo de caixa — e a resposta ao risco apontado no mapa de paridade |
| **10** | A DFC apresenta os fluxos do período **classificados** pelas três atividades | A linha estrutural da demonstração |
| **12** | Uma única transação pode ter fluxos em **mais de uma** atividade (principal e juros de um empréstimo) | A marcação manual por lançamento |
| **13 a 15** | Operacional: as principais atividades geradoras de receita e as que não são investimento nem financiamento | A classe das contas de resultado |
| **16, 17** | Investimento e financiamento, com os exemplos da norma | A classe das contas patrimoniais e do PL |
| **18** | O método **direto ou o indireto**, alternativamente | Os dois, como o Fred pediu |
| **20** | Indireto: lucro líquido ajustado por (a) variações de estoques e contas operacionais a receber e a pagar, (b) itens que não afetam caixa, (c) itens tratados como investimento ou financiamento | As três famílias de ajuste |
| **20A** | ⚠️ **A conciliação entre o lucro líquido e o fluxo de caixa líquido das atividades operacionais é obrigatória para quem usa o método direto** | **É o que amarra os dois métodos**: o direto sem esta conciliação não conforma |
| **21** | Investimento e financiamento, **separadamente**, por principais classes de recebimentos e pagamentos brutos | As duas seções |
| **22, 23** | Base líquida em casos específicos; **23(a) é exatamente a movimentação em contas de depósito à vista de banco** | Pergunta 3: se o produto oferece a opção |
| **43, 44** | Transações que não envolvem caixa ficam **fora** da DFC e vão para as notas explicativas | Pergunta 4, e a pendência CTB-18 |
| **45** | ⚠️ **Divulgar os componentes de caixa e equivalentes e apresentar conciliação dos montantes com os itens do Balanço Patrimonial** | **O critério de aceite desta demanda** |
| **52A** | As demonstrações **não** devem divulgar fluxo de caixa por ação | Restrição: nenhum campo "por ação" na DFC (o oposto do item E8 pendente da DMPL) |

⚠️ **Lacuna declarada, e ela é de fonte e não de conteúdo:** a obrigatoriedade
veio da [Lei 6.404/76, art. 176, IV](https://www.planalto.gov.br/ccivil_03/leis/l6404compilada.htm)
(introduzido pela Lei 11.638/2007), com a **§ 6 isentando a companhia fechada
com patrimônio líquido inferior a R$ 2.000.000,00**. O texto compilado no
Planalto **não foi obtido** neste ambiente (a requisição falhou), e as fontes
que responderam foram secundárias. **Conferir no Planalto antes de colocar a
obrigatoriedade como regra de produto** — e a pergunta 2 abaixo é justamente
sobre isso, porque a resposta muda o que o produto exige.

**Nota de contexto (NE2, do próprio pronunciamento):** o item 18 **não dá
preferência** ao método direto nem ao indireto — a escolha é da entidade. Por
isso "os dois" é decisão de produto legítima, e não um acréscimo de escopo sem
fundamento.

## O caso de referência, calculado à mão

Os mesmos números do [mapa de paridade](../projeto/paridade/contabilidade.md)
(manual do sistema de referência, páginas 622-631), para que os dois documentos
concordem e o cálculo possa ser conferido contra a tela:

| Linha | Valor |
| --- | --- |
| Lucro líquido do exercício | 90.000,00 |
| (+) Depreciação — não afeta caixa | 15.000,00 |
| (−) Aumento de Contas a Receber | (20.000,00) |
| **= Caixa gerado nas operações** | **85.000,00** |
| Caixa usado em investimentos | (30.000,00) |
| Caixa gerado em financiamentos | 10.000,00 |
| **= Variação líquida do caixa** | **65.000,00** |
| Caixa inicial | 40.000,00 |
| **= Caixa final** | **105.000,00** |

Conferência: 40.000,00 + 65.000,00 = 105.000,00, e esse 105.000,00 tem de ser
**o saldo das contas de caixa e equivalentes no Balanço na mesma data** — é o
item 45 e é o critério de aceite.

## A regra que o produto implementa, em uma frase

> **Todo** lançamento que mexe uma conta de caixa e equivalentes e uma conta
> **de fora** da lista de caixa é um fluxo, classificado pela atividade da
> conta de fora; movimento entre duas contas de caixa **não** é fluxo (item 9);
> e a soma das três atividades é, **por construção**, a variação do saldo de
> caixa e equivalentes do período.

## Decisões de desenho (`arquiteto-senior`, reversíveis)

### E1 — As atividades saem dos LANÇAMENTOS, e o indireto é uma apresentação

A forma ingênua de calcular a DFC pelo método indireto é somar "depreciação" e
"variação de contas" e torcer para fechar. Isso é frágil pelo motivo que a
própria norma nomeia no item 20: a mesma despesa pode ter contrapartida em
conta operacional, de investimento ou de financiamento, e a resposta muda o
número.

Esta demanda faz o contrário. O **fato** é o lançamento: caixa contra uma
conta de fora. A atividade vem da conta de fora. A soma das três atividades é
a variação do caixa **por construção** — não por conciliação posterior. O
método indireto passa a ser a **apresentação** do mesmo número, com os
ajustes do item 20 **derivados** e nomeados, e um **veto** quando a
decomposição não fecha.

**Por que isso importa:** com o número derivado do lançamento, o critério de
aceite do item 45 é uma **identidade que precisa valer**, e qualquer erro de
classificação aparece como **veto** — nunca como número errado publicado. É a
mesma postura que a DLPA e a DMPL já seguem, e o oposto de "ajustar para
fechar".

### E2 — "Caixa e equivalentes" é campo da conta, não nome de conta

O item 45 exige conciliar com o Balanço, e a conciliação **não existe** sem
saber quais contas entram. O campo é da conta (`caixa_e_equivalentes`), nunca
inferido do nome ou do código — inferir de "1.1 Caixa" erra em toda conta
chamada "Banco Conta Corrente" que a empresa usa para Adjustes de
Regularização, e erra em conta de aplicação que não é equivalente.

### E3 — Atividade e "não caixa" são campos da conta, com o mesmo molde da CTB-12

`classificacao_dfc` (operacional/investimento/financiamento) e
`item_nao_caixa` (item de resultado que não movimenta caixa: depreciação,
amortização, provisões). Mesmo padrão dos outros campos de `Conta` —
`CheckConstraint` contra `""`, normalização, guarda de tipo, serviço com
`select_for_update` e trilha, serializer de PATCH, tela de classificação.

### E4 — A marcação manual por lançamento, para os casos que a regra não decide

O item 12 (uma transação, mais de uma atividade) e o item 19(b)(ii) (item
que não envolve caixa) não são decididos por conta: são decididos por
lançamento. `MarcacaoDfc`, no **molde exato** de `MarcacaoDmpl`: fora do
livro, com `PROTECT` nos dois lados, `UniqueConstraint` e `CheckConstraint`
como defesa de banco, gravação só por serviço, trilha com antes/depois, e
**recusa quando a regra automática já decide**.

⚠️ **O limite declarado, e ele é o ponto que o mapa de paridade já apontava:**
o método direto exige saber, por lançamento, se ele representa caixa de fato.
Sem a marcação, o padrão é "conta marcada como caixa e equivalentes" — e o
risco é herdar do produto a fragilidade de tratar como fluxo real o que é
ajuste. O item 9 mitiga o caso mais comum (transferência entre contas da
própria empresa), e a marcação cobre o resto. O que **não** fica coberto, e
segue declarado: **um lançamento que mexe a conta de caixa sem mover dinheiro
de verdade e sem contrapartida na lista de caixa entra como fluxo**. É a
mesma classe de limite que o mapa de paridade nomeou, e precisa estar escrito
no relatório de entrega, não descoberto depois.

### E5 — O item 20A amarra os dois métodos, e isso define a entrega

O item 20A obriga a conciliação lucro líquido × fluxo das operações **para
quem usa o método direto**, e a nota explicativa NE3 diz que essa exigência é
brasileira e não existe no IAS 7. Ou seja: **o método direto sem a conciliação
do indireto não conforma no Brasil**. É por isso que "os dois" não é escopo
dobrado: é a norma exigindo que o direto traga consigo a conciliação.

### E6 — A conciliação do item 45 veta, e o veto nomeia a diferença

Mesmo padrão de `avaliar_emissao_do_balanco`: a apuração **declara** a
diferença entre a variação do caixa apurada e a variação dos saldos de caixa e
equivalentes no Balanço, e a emissão é **recusada** com a diferença nomeada.
Nenhum saldo é ajustado para fechar.

## Perguntas para o Fred — e a recomendação de cada uma

1. **O que conta como "equivalentes de caixa"?** A norma diz aplicação de
   curto prazo, três meses ou menos (item 7). O produto precisa de um padrão
   que o escritório use, e a resposta muda o que a conciliação do item 45
   compara. **Recomendação:** campo por conta, com o padrão do produto
   sugerindo ausência de equivalente por omissão — quem tiver aplicação
   curta marca a conta. Declarar um padrão automático seria inventar
   política de tesouraria alheia.
2. **A empresa é obrigada a elaborar a DFC?** A Lei 6.404/76, art. 176, IV,
   com a § 6 isentando a companhia fechada com PL abaixo de R$ 2.000.000,00.
   O produto atende escritório de contabilidade, com carteira heterogênea.
   **Recomendação:** a DFC é emitida por empresa que a pedir, sem TRAVAR
   nenhuma; a pergunta da obrigatoriedade é do cliente, não do produto. E
   nenhuma nota de rodapé legal entra antes de o texto do Planalto ser
   lido — a lacuna está declarada.
3. **O produto oferece a apresentação em base líquida?** O item 22 lista os
   casos, e o 23(a) é a movimentação em conta de depósito à vista — exatamente
   o caso do escritório brasileiro. **Recomendação:** não nesta primeira
   entrega. É uma opção de apresentação que só faz sentido depois que a
   conta de caixa está classificada, e ela polui a leitura de quem está
   aprendendo. Registrar como pendência.
4. **Onde entram os juros e os dividendos?** O item 34A **encoraja
   fortemente** classificar juros recebidos e pagos e dividendos recebidos
   como operacionais, e dividendos e JCP pagos como de financiamento — e
   exige que a escolha diferente venha com nota. **Recomendação:** seguir a
   34A como padrão do produto, e deixar a conta marcável para o caso
   diferente, que a norma já autoriza desde que declarado.

## Critérios de aceite

| # | Critério | Como é verificado |
| --- | --- | --- |
| 1 | O caso de referência reproduz a tabela acima **ao centavo**, nos dois métodos | `test_criterio1_*` |
| 2 | **Caixa final da DFC = saldo de caixa e equivalentes no Balanço na mesma data** (item 45), por identidade, nos dois métodos | `test_criterio2_*` |
| 3 | Movimentos entre duas contas de caixa e equivalentes **não** entram como fluxo (item 9) | `test_criterio3_*` |
| 4 | Lançamento com **duas** atividades, uma de cada lado, é aceito e nomeia as duas (item 12) | `test_criterio4_*` |
| 5 | Classificação de atividade **ausente** numa conta de movimento veta a emissão e **nomeia a conta** | `test_criterio5_*` |
| 6 | Conta de resultado marcada como **não caixa** aparece no ajuste do item 20(b) e **não** na variação de contas operacionais | `test_criterio6_*` |
| 7 | Conta marcada como caixa e equivalentes **sem** movimento no período não entra no saldo conciliado | `test_criterio7_*` |
| 8 | O **método direto traz a conciliação** do lucro líquido (item 20A) — sem ela, a emissão é recusada | `test_criterio8_*` |
| 9 | A conciliação que **não fecha** veta, nomeando a diferença, e **nenhum saldo é ajustado** | `test_criterio9_*` |
| 10 | Isolamento entre empresas nos dois sentidos | `test_criterio10_*` |
| 11 | A DFC **não** tem campo de valor por ação (item 52A) | `test_criterio11_*` |
| 12 | `Decimal` em todo o cálculo, escala explícita, sem ponto flutuante | `test_criterio12_*` |
| 13 | Sem regressão em `apps/contabilidade`; lint, formatação, Django e migrações limpos | suíte e comandos |

### Cenários de teste obrigatórios

- **Sucesso:** o caso de referência; atividade operacional, de investimento e
  de financiamento; período com mais de um mês; empresa sem movimento.
- **Erro:** conta sem classificação de atividade; marcação que não reproduz o
  movimento do lançamento; conciliação que não fecha; caixa e equivalentes
  declarado em conta que não é de caixa.
- **Limite:** transferência entre contas de caixa; lançamento de uma atividade
  só, pelo valor total; **fevereiro de ano bissexto**; virada de ano
  (31/12 → 01/01); competência **encerrada** — e aqui a trava da DL-065
  precisa ser respeitada: reclassificar atividade de conta com movimento em
  período fechado é recusado, e o veto tem de dizer o que fazer; lançamento de
  **zeramento** do resultado, que a DRE exclui e a DLPA inclui (a mesma
  armadilha que a DL-061 já registrou).

## Fatias

| Fatia | Entrega | Nível |
| --- | --- | --- |
| **1** | `caixa_e_equivalentes` e `classificacao_dfc` na conta, serviço de classificação com trilha, tela e API; `apurar_dfc` com o **indireto** e a conciliação do item 45; caso de referência; veto nomeando o que falta | 1 |
| **2** | **Método direto**, com a reconciliação obrigatória do item 20A e a marcação manual por lançamento (`MarcacaoDfc`) | 1 |
| **3** | Comparativo com o exercício anterior e a componente de caixa e equivalentes detalhada (itens 45 e 50), se a fatia 1 já não trouxer | 2 |

⚠️ **A fatia 1 é grande** e é o tamanho real desta demonstração: três campos
novos na conta, duas portas, uma apuração e uma tela. Ela vai para a
**auditoria independente** antes da fatia 2 — a auditoria da fatia 2 é sobre
o que ela acrescenta, não sobre a base de novo.

## Fora do escopo

- **Base líquida** (itens 22 e 23) — pergunta 3, recomendada para depois.
- **Notas explicativas** das transações sem caixa (itens 43 e 44) — é a
  **CTB-18**, que não existe.
- **Valor por ação** — o item 52A **proíbe** na DFC; a necessidade é o
  inverso, na DLPA e na DMPL (pendência E8 da DL-061, BL-603).
- **Demonstração segmentada** (item 50(b) a (e)) — não há_segments no
  produto.
- **Estrutura de demonstração genérica** — a ONDA continua com campos
  discretos na conta (CTB-12). Mudar para tabela genérica é decisão de
  arquitetura (CTB-54), e não entra aqui.

## Equipe e arquivos

| Papel | Arquivos |
| --- | --- |
| `desenvolvedor-pleno` | `apps/contabilidade/models.py`, `services.py`, `views.py`, `views_web.py`, `urls_web.py`, `urls.py`, `serializers.py` |
| `desenvolvedor-pleno` (testes) | `apps/contabilidade/tests/test_dl066_*.py` |
| `especialista-frontend` | `templates/contabilidade/dfc.html`, `tests/universo_de_telas.py` |
| `auditor-qa` | `docs/auditorias/AAAA-MM-DD-dl-066-*.md` — **sem escrita de código** |

## Evidências e integração

| Item | Classificação |
| --- | --- |
| Base normativa do CPC 03 (itens 6 a 52A) | **Testado** — texto integral lido nesta sessão |
| Texto do art. 176 da Lei 6.404/76 | **Não testado** — Planalto inacessível neste ambiente; **lacuna declarada** |
| Manual do sistema de referência (p. 622-631 e 666-667) | **Não lido** — declarado, não conformidade; a rotina do manual não autoriza nem refuta a regra |
| Implementação | Pendente |

> A nota de ambiente (`.env` apontando para SQLite, cluster PostgreSQL criado
> na porta 5433, linha de base honesta de 8 reprovados) está em
> [`estado.md`](../agents/estado.md) e vale para todas as etapas desta leva.
