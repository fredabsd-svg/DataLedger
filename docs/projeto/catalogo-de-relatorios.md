# Catálogo de relatórios contábeis — cruzamento honesto com o DataLedger

**Origem:** o Fred entregou, em 2026-09-20, um **manual técnico de 120
relatórios contábeis** (edição de 20/09/2026), logo depois de eu lhe devolver a
pergunta *"qual das três ausências de relatório entra primeiro?"*. Este
documento é **a minha análise do catálogo contra o código que existe** — não uma
cópia dele.

## ⚠️ Regra de uso, e ela vem antes de tudo

**O manual NÃO entra no repositório**, pela mesma regra que vale para qualquer
material de terceiro ([fontes-de-referencia.md](fontes-de-referencia.md)). O que
fica aqui é **cruzamento e decisão nossos**.

E o próprio manual é honesto sobre o que é — copio a ressalva dele porque ela
protege o Fred:

> *"não existe uma lista oficial de '120 demonstrações obrigatórias'. Este manual
> reúne 120 tipos, formatos e aplicações de relatórios. (…) A obrigatoriedade
> depende da entidade, da norma, do porte, do setor e do exercício."*

E, no fecho:

> *"este é um manual técnico-funcional e **não um leiaute oficial** de cada
> obrigação **nem uma opinião profissional** para uma empresa específica."*

⚠️ **Portanto: o catálogo responde ROTINA e ESCOPO; ele NÃO é fundamento
normativo.** Para item, vigência, prazo, alíquota ou leiaute, a fonte continua
sendo **oficial** (CFC, CPC, Receita), com item e data de consulta citados — é o
que **RC-95** e **RC-96** já fazem. O manual **cita** as fontes certas (Lei
6.404/76, CPC, NBC, SPED, eSocial), o que o torna um bom **índice**; usá-lo como
norma seria violar a regra de não inventar leiaute.

## 1. O achado que vale mais que a lista

Está no fecho do manual, e é **arquitetura**, não contabilidade:

> *"**Separação das bases:** documentos e transações operacionais → módulos
> financeiro/fiscal/folha/estoque/patrimônio → lançamentos, plano de contas,
> Diário e Razão → saldos e conciliações → demonstrações, indicadores e
> relatórios. **Não são necessárias 120 bases de dados independentes.**"*

⚠️ **Isso reformula a pergunta que eu levei ao Fred.** Eu ofereci três opções
soltas — exportação, livro, demonstrações — como se fossem alternativas de
gosto. **Não são:** a cadeia acima diz em que ordem elas se tornam **possíveis**.

**Onde o DataLedger está nessa cadeia, medido em 2026-09-20:**

| Elo da cadeia | Estado |
| --- | --- |
| Documentos e transações operacionais | **Não existe** (é Fiscal, Folha, Financeiro, Estoque, Patrimônio) |
| Lançamentos e plano de contas | ✅ **Existe**, com partida dobrada garantida e trilha |
| Diário e Razão | ✅ **Existem** como relatório de conferência |
| **Saldos e conciliações** | ⚠️ **PARCIAL** — o Balancete calcula saldo por período, mas **não há camada de saldos consolidada** que outra coisa consuma |
| Demonstrações, indicadores e relatórios | **Não existe** |

**A consequência é a única recomendação técnica desta análise:** o elo que falta
e que **destrava mais coisa por unidade de esforço** é a **camada de saldos**.
Balanço, DRE, DMPL, DLPA, análise vertical e horizontal, e a maior parte dos
indicadores são **derivações dela** — não módulos novos. Enquanto ela não
existir, cada demonstração nova custa o preço cheio; depois dela, custa o preço
de uma consulta e de um layout.

## 2. O que o DataLedger atende HOJE, do catálogo

Medido no código em 2026-09-20 (`apps/contabilidade/services.py`,
`urls_web.py`, `templates/contabilidade/`), não estimado:

| # do catálogo | Relatório | Situação no DataLedger |
| --- | --- | --- |
| 11 | Balancete de Verificação | ✅ **Atende** — `apurar_balancete(empresa, inicio, fim, nivel)` |
| 14 | Balancete Mensal | ✅ **Atende** — período livre cobre o mês |
| 17 | Livro Diário | ⚠️ **Relatório sim, LIVRO não** — falta a forma prescrita (ver §3) |
| 18 | Livro Razão | ⚠️ **Idem** |
| 24 | Relatório de Inconsistências Contábeis | ✅ **Atende, e é o ponto mais forte** — seis verificações (§4) |
| 12 / 13 | Balancete Analítico / Sintético | ⚠️ **Parcial** — o filtro por `nivel` dá as duas vistas, sem serem relatórios nomeados |
| 15 | Balancete Acumulado | ⚠️ **Parcial** — período livre permite acumular; não há o conceito de "desde o início do exercício" |
| 21 | Relatório de Lançamentos Contábeis | ⚠️ **Parcial** — o Diário serve, sem os filtros do item |
| 22 | Relatório de Partidas Dobradas | ⚠️ **Parcial** — a Conferência detecta lote desbalanceado |
| 16 | Balancete Comparativo | ❌ **Não atende** — não há duas colunas de período |
| 19 | Razão Analítico | ❌ **Não atende** — depende de origem e documento no lançamento (**BL-72**) |
| 20 | Razão por Centro de Custo | ❌ **Não atende** — não há centro de custo (**BL-67 a BL-69**) |
| 23 | Contas sem Movimentação | ❌ **Não atende** — e é **barato** |
| 25 | Encerramento do Exercício | ❌ **Não atende** — temos fechamento de **competência**, não de **exercício** |

**Contagem honesta: 3 atendidos, 6 parciais, 5 ausentes — dentro do grupo em que
o produto atua.** Do catálogo inteiro de 120, isso é **menos de 5%**.

⚠️ **E o número 5% é verdadeiro e enganoso ao mesmo tempo**, por isso não o deixo
sozinho: **80 dos 120 itens dependem de módulos que o DataLedger não tem** —
Financeiro e tesouraria (12 itens), Custos e estoques (12), Fiscal (12),
Trabalhista (10), além de patrimônio e consolidação. **Não são relatórios que
faltam: são módulos.** Medir o produto contra os 120 sem dizer isso seria a
mesma classe de erro que a **[DE-060](decisoes.md)** descreve — comparar contra
um substituto e não declarar.

## 3. As três classes já explicam a ordem, e o catálogo confirma

A [personalizacao-de-relatorio.md](personalizacao-de-relatorio.md) já havia
separado **relatório de conferência**, **demonstração contábil** e **livro**. Os
dez grupos do manual caem exatamente nessa divisão — **confirmação independente,
por outro caminho**, do que já estava decidido aqui.

| Classe | Grupos do catálogo | O que falta no DataLedger |
| --- | --- | --- |
| **Conferência** | Parte II (escrituração), Parte X (controle) | Pouco: itens baratos e bem definidos |
| **Demonstração** | Parte I, e parte da V | **A camada de saldos** — é o gargalo |
| **Livro** | Parte II, itens 17 e 18 **na forma de livro** | Numeração de folha, termo de abertura e de encerramento, assinatura, ausência de espaço em branco (**RC-96**) |

## 4. O que já é bom, e vale registrar antes da lista de faltas

O item **24 do catálogo** (Inconsistências Contábeis) pede *"validações
essenciais"*. A tela de Conferência do DataLedger implementa **seis**, medidas:
lote desbalanceado, lançamento com data fora da faixa, movimento fora do período
consultado, conta sintética com movimento, conta que aceita lançamento tendo
subordinadas, e inconsistência de hierarquia.

E os **controles de consistência essenciais** que o manual lista no fecho já
estão cobertos nos dois primeiros itens:

| Controle exigido pelo manual | Estado |
| --- | --- |
| *"débitos e créditos de cada lançamento efetivo devem ser iguais"* | ✅ garantido no modelo |
| *"Razão e balancete devem conciliar"* | ✅ é a base da DL-015 |
| *"fechamentos devem preservar históricos e proibir alterações não autorizadas; correções exigem rastreabilidade"* | ✅ **fechado hoje**, DL-016 fatias 1 e 2 |
| *"o Balanço deve fechar e manter correspondência com composições analíticas e DMPL"* | ❌ não há Balanço |
| *"a DFC deve reconciliar caixa do início e do fim"* | ❌ não há DFC |

## 5. O que fica para o Fred decidir, e por quê

**Não é decisão de engenharia.** A cadeia do §1 diz o que é **possível**; o que
é **prioritário** depende do que o cliente dele cobra e do que o fisco pede
primeiro. As opções, com o trade-off real:

| Caminho | Custo | Destrava | Risco |
| --- | --- | --- | --- |
| **Camada de saldos** | Alto | Balanço, DRE, DMPL, DLPA, análise vertical e horizontal, indicadores | Nenhum dado existente é tocado; é leitura |
| **Livro com forma prescrita** | Médio | Cumprimento formal de Diário e Razão | Norma citada (RC-96); **exige validação profissional do Fred** |
| **Exportação em arquivo** | Baixo | Nada de novo, mas melhora tudo o que existe | Baixo |
| **Itens baratos de conferência** (23, 16) | Baixo | Dois itens do catálogo | Baixo |

**Recomendação do `arquiteto-senior`:** a **camada de saldos**, porque é o único
caminho em que o esforço é pago mais de uma vez. Mas **eu não tenho os dois
dados que decidem**: o que o escritório do Fred entrega ao cliente com mais
frequência, e se há obrigação com prazo pressionando.

⚠️ **Auditoria de software não substitui a validação profissional das regras
contábeis e legais** — o enquadramento de cada entidade, a obrigatoriedade de
cada demonstração e a forma de cada livro cabem ao Fred.
