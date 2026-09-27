# Plano de paridade — Lalur

## Introdução

O Lalur (Livro de Apuração do Lucro Real) é o livro fiscal em que a
empresa tributada pelo **lucro real** parte do resultado **contábil**
(lucro ou prejuízo apurado na Contabilidade) e chega ao **lucro real**
— a base de cálculo do IRPJ e da CSLL —, somando **adições** (despesas
contabilizadas que a lei fiscal não deixa deduzir, como multas
indedutíveis) e subtraindo **exclusões** (receitas contabilizadas que a
lei fiscal não tributa, como a equivalência patrimonial), além de
controlar, em uma parte própria (Parte B), diferenças que só se resolvem
em exercícios futuros — como a diferença entre depreciação fiscal e
societária apurada no Patrimônio — e o prejuízo fiscal acumulado que pode
compensar lucro de anos seguintes, com limite legal. No dia a dia do
escritório, é o módulo que o contador abre uma vez por trimestre (ou por
ano, conforme o regime de apuração) para calcular quanto de IRPJ e CSLL a
empresa deve, com toda a memória de cálculo documentada — hoje entregue à
Receita Federal como bloco da **ECF**.

**Escopo.** Este plano cobre a paridade funcional do Lalur com o sistema
de referência: parâmetros de apuração, adições e exclusões, Parte A (o
cálculo do período) e Parte B (o controle que atravessa exercícios) e
base negativa da CSLL, guias de recolhimento (DARF normal, quotas, ajuste
anual), regimes de estimativa e de balanço de redução/suspensão,
incentivos fiscais, lucro da exploração, Sociedade em Conta de
Participação (SCP), eventos societários (cisão, incorporação) e a
integração contábil. O Livro Lalur digital **dentro da ECF** é tratado
como item de fronteira com a Contabilidade (LAL-26, cruzado com
[CTB-52](contabilidade.md#ctb-52--ecf-escrituração-contábil-fiscal-e-ajustes)),
porque depende da estratégia de ECD/ECF que é da Contabilidade.

**Fontes.**

- **Rotina:** manual do sistema de referência entregue pelo Fred em
  2026-09-27 (Domínio Lalur, 291 páginas). Páginas citadas por item; o
  manual **não** entra no repositório
  ([fontes-de-referencia.md](../fontes-de-referencia.md)).
- **Norma:** cada item cita a fonte oficial a consultar antes de
  qualquer alíquota, percentual de limite ou leiaute virar código.
  Nenhuma alíquota de IRPJ/CSLL, nenhum percentual de limite de
  compensação de prejuízo, e nenhum leiaute deste plano foi conferido em
  fonte primária nesta sessão — todos estão marcados **a confirmar**.
- **Inventário-base:**
  [mapa-funcional-patrimonio-lalur.md](../mapa-funcional-patrimonio-lalur.md),
  produzido na [DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md).

**Convenções.** Mesmo modelo de item do
[README.md](README.md#modelo-de-cada-item) deste diretório. IDs `LAL-NN`.
Classe de documento conforme
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md):
**cadastro**, **conferência**, **demonstração**, **livro** ou **guia**. As
regras gerais do [AGENTS.md](../../../AGENTS.md) — `Decimal`, efetivado
imutável, autorização no servidor, isolamento por empresa, trilha de
auditoria — valem em todo item deste plano, mesmo quando não repetidas.

**Estado atual: inexistente.** Não há cadastro de adição, de exclusão,
de Parte B, de base negativa nem cálculo de IRPJ/CSLL em nenhum lugar do
código — confirmado em `apps/` (só existem `accounts`, `auditoria`,
`contabilidade`, `core`, `documentos`, `empresas`, `fiscal`,
`livro_caixa`, `tenancy`; não há `patrimonio` nem `lalur`). Já existe,
porém, a base de que o Lalur depende: a **DRE**
(`apurar_dre`, [DL-045](../../planos/DL-045-demonstracao-do-resultado.md)),
que devolve `resultado_antes_dos_tributos_sobre_o_lucro` — exatamente o
"lucro antes da CSLL e do IRPJ" que este módulo importa como ponto de
partida.

⚠️ **Achado preventivo que governa a modelagem deste módulo, já registrado
em [contabilidade.md#ctb-74](contabilidade.md#ctb-74--lalur-parte-b-referência-cruzada--módulo-próprio)
(BL-398):** a **Parte B** do Lalur é um **razão de controle fiscal**, não
partida dobrada — acumula diferenças temporárias com saldo que atravessa
exercícios, sem o par débito/crédito nem a hierarquia sintética/analítica
que `Conta` (da Contabilidade) carrega. **Não generalizar `Conta` para
cobrir a Parte B** — o modelo correto é um "razão memorando" próprio,
descrito em LAL-09/LAL-10.

## Mapa de dependências e ordem

```
LAL-01 Parâmetros do Lalur
  ├─> LAL-02 Cadastro de adições ──┐
  ├─> LAL-03 Cadastro de exclusões ─┼─> LAL-05 Lançamentos de adições/exclusões
  └─> LAL-04 Lucro antes da CSLL/IRPJ (importado da DRE — CTB-10/apurar_dre)
                                          │
       ┌──────────────────────────────────┘
       ▼
LAL-06 Apuração trimestral/anual do IRPJ e CSLL ──> LAL-07 Livro Lalur Parte A
       │                                        └─> LAL-08 Demonstrativos de apuração
       ├─> LAL-09 Cadastro de contas da Parte B e Base Negativa
       │     └─> LAL-10 Lançamentos da Parte B
       │           └─> LAL-11 Base negativa da CSLL e compensação de prejuízo (30%)
       │                 └─> LAL-12 Saldo inicial da Parte B e da base negativa
       ├─> LAL-13 Compensação de impostos federais (DComp)
       ├─> LAL-14 Parcelamento de impostos
       ├─> LAL-15 Pagamento de impostos, com baixa
       │     └─> LAL-16 Guias DARF (normal, quotas, ajuste anual)
       ├─> LAL-17 Receita bruta e operações de receita (base da estimativa)
       │     └─> LAL-18 Ganhos (base do lucro estimado)
       │           └─> LAL-19 Ajuste anual e comparativo real × estimado
       │                 └─> LAL-20 Balanço de redução e suspensão
       ├─> LAL-21 Incentivos fiscais
       ├─> LAL-22 Lucro da exploração
       ├─> LAL-23 Sociedade em Conta de Participação (SCP)
       ├─> LAL-24 Eventos societários (cisão, incorporação) — sobre a Parte B
       └─> LAL-25 Integração contábil (provisão de IRPJ/CSLL)
             └─> LAL-26 Livro Lalur digital dentro da ECF (cruza com CTB-52)
```

**Ondas**, seguindo a recomendação de
[mapa-funcional-patrimonio-lalur.md](../mapa-funcional-patrimonio-lalur.md#ondas-recomendadas)
e o pedido do Fred (Parte A, Parte B, guias, estimativa/suspensão,
incentivos, lucro da exploração, SCP, eventos societários, ECF):

1. **Parte A e apuração sobre a DRE** — LAL-01 a LAL-08: o núcleo do
   módulo. Depende só da Contabilidade que já existe (DRE, DL-045).
2. **Parte B e base negativa** — LAL-09 a LAL-12: o controle que
   atravessa exercícios. Depende do Patrimônio (diferença fiscal ×
   societária de depreciação, PAT-19) para o caso de uso mais comum, mas
   pode nascer só com lançamento manual da diferença.
3. **Guias DARF e quotas** — LAL-13 a LAL-16: compensação, parcelamento,
   pagamento, emissão da guia.
4. **Estimativa e balanço de redução/suspensão** — LAL-17 a LAL-20: o
   regime alternativo de apuração mensal, com receita bruta e ganhos.
5. **Incentivos** — LAL-21.
6. **Lucro da exploração** — LAL-22.
7. **SCP** — LAL-23.
8. **Eventos societários** — LAL-24.
9. **Lalur dentro da ECF** — LAL-25 e LAL-26, junto da estratégia de
   ECD/ECF já registrada em CTB-50 a CTB-52.

**O que este módulo importa de fora dele**, e é preciso ter pronto antes:

| Dado do Lalur | Vem de |
| --- | --- |
| Lucro antes da CSLL e do IRPJ (LAL-04) | `apurar_dre`, campo `resultado_antes_dos_tributos_sobre_o_lucro` ([DL-045](../../planos/DL-045-demonstracao-do-resultado.md)) |
| Diferença entre depreciação fiscal e societária (adição/exclusão temporária, LAL-11) | PAT-19, [patrimonio.md](patrimonio.md#pat-19--comparativo-fiscal--societário-e-subcontas-da-lei-129732014) |
| Ganho/perda de capital na baixa de bem (adição, LAL-05) | PAT-11, [patrimonio.md](patrimonio.md#pat-11--baixa-total-ou-parcial-com-ganho-ou-perda-de-capital) |
| Retenções na fonte (dedução, LAL-13) | Módulo Fiscal (FIS-14, a confirmar quando planejado) |
| Receita bruta (base da estimativa, LAL-17) | Módulo Fiscal (acumuladores/apuração, FIS-07/FIS-23) |
| Provisão de IRPJ/CSLL (integração contábil, LAL-25) | `criar_lancamento` (CTB-02) |

## Onda 1 — Parte A e apuração sobre a DRE

### LAL-01 — Parâmetros do Lalur

**O que é.** A configuração, por empresa e por **vigência**, de como o
módulo apura: o tipo de cálculo (trimestral, anual por estimativa, ou
anual por balanço de redução e suspensão), o tipo de atividade (geral,
rural ou ambas), a qualificação da pessoa jurídica (regra geral,
instituição financeira, seguradora), e as opções de registro automático
na Parte B e na base negativa.

**Exemplo.** Empresa "Indústria Alfa Ltda.", tipo de cálculo
"Trimestral", atividade "Geral", com "Registrar automaticamente na Base
Negativa e Parte B os prejuízos apurados" **marcado**: ao apurar
prejuízo em um trimestre, o sistema já lança o valor na base negativa e
na Parte B sem digitação extra.

**Referência de rotina.** Manual, páginas 57-87 (guias Geral/Cálculo,
Geral/Configurações, Geral/Opções, Geral/Contabilidade — Impostos,
Compensações, Deduções, Incentivos Fiscais, Pagamentos —, Geral/Impostos,
Geral/Lançamentos, Geral/Parte B, Saldo Inicial e Assinaturas).

**Fonte normativa.** **A confirmar** — o tipo de cálculo (trimestral,
estimativa mensal, balanço de redução/suspensão) é regido pela **Lei
9.430/1996** (arts. 1º a 2º e 35) e pela **IN RFB 1.700/2017**; a
qualificação da pessoa jurídica (regra geral × instituição financeira)
afeta a base de cálculo da CSLL (**Lei 7.689/1988** e alterações).

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01 (contas contábeis referenciadas pelos parâmetros),
CTB-07 (competência/vigência).

**Dados.** Modelo novo: parâmetro do Lalur por empresa e por
**vigência**: tipo de cálculo (trimestral / anual-estimativa /
anual-balanço-de-redução-e-suspensão), tipo de atividade
(geral/rural/ambas), qualificação da pessoa jurídica, opção de calcular
lucro estimado, opção "menor valor a recolher entre real e estimado",
registro automático de prejuízo e de incentivo PAT na Parte B, contas
contábeis de importação do lucro/prejuízo operacional e não operacional
(geral e rural), amarração contábil por tipo de lançamento (recolhimento,
compensação, dedução, incentivo, pagamento — cada um com conta débito,
conta crédito e histórico), flag de SCP.

**Regras.** Vigência sem sobreposição (mesmo padrão de FIS-07/FIS-08);
**um único tipo de cálculo vigente por vez**, por empresa (o tipo de
cálculo não pode ser trimestral e anual simultaneamente, mesma lógica de
RC-105 para a periodicidade de zeramento contábil); mudança de tipo de
cálculo no meio do ano-calendário é operação sensível e **exige
confirmação explícita**, nunca implícita por vigência retroativa.

**Telas e documentos.** Tela de parâmetros — classe **cadastro**.

**Critérios de aceite.** Parâmetro por vigência sem sobreposição; recusa
de dois tipos de cálculo vigentes na mesma data para a mesma empresa;
trilha de quem alterou o parâmetro e quando.

**Não copiar/riscos.** O manual permite trocar o tipo de cálculo a
qualquer momento por vigência nova — o DataLedger precisa decidir se
replica essa liberdade ou se exige confirmação adicional (o tipo de
cálculo é decisão que, uma vez tomada para o ano-calendário, normalmente
não muda por opção do contribuinte — **a confirmar na Lei 9.430/1996**).

**Perguntas.** Qual regime de apuração a carteira do Fred usa hoje —
trimestral, estimativa mensal, ou balanço de redução/suspensão — e há
clientes com mais de um regime?

### LAL-02 — Cadastro de adições

**O que é.** O catálogo das adições que a legislação permite (ou exige)
somar ao lucro contábil para chegar ao lucro real — cada adição é ligada
a uma ou mais contas contábeis de origem (o "gatilho" que identifica o
valor a adicionar) e ao imposto que afeta (CSLL, IRPJ, ou ambos).

**Exemplo.** Adição "Multas de trânsito indedutíveis", ligada ao imposto
"Ambos" (CSLL e IRPJ), vinculada à conta contábil "Multas e Penalidades" —
todo valor lançado nessa conta durante o período vira candidato a adição.

**Referência de rotina.** Manual, páginas 101-106 (guia Geral: adicionar a
CSLL/IRPJ/ambos/lucro da exploração; guia Grupo: pessoa jurídica em
geral, componente do sistema financeiro, seguradoras; guia Contas: contas
contábeis vinculadas; guia Base Negativa e Parte B: registro automático).

**Fonte normativa.** **A confirmar** — o rol de adições é dado pelo
**RIR/2018 (Decreto 9.580/2018)**, arts. 260 e seguintes, e pela **IN RFB
1.700/2017**, Anexo I (Lalur/ECF). Não há lista fechada única e estável —
cada adição tem seu próprio dispositivo legal, e o DataLedger **não deve
pré-cadastrar um catálogo fixo de adições sem conferência item a item**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-01, CTB-01 (contas de origem).

**Dados.** Modelo novo `Adicao`: empresa, código, descrição, imposto
afetado (CSLL/IRPJ/ambos, e lucro da exploração quando aplicável), grupo
(pessoa jurídica geral / componente do sistema financeiro / seguradora,
cada um com sua conta de agrupamento), contas contábeis de origem
vinculadas (N:N), registro automático em Parte B (conta destino,
histórico) e em base negativa (conta destino, histórico).

**Regras.** Adição sem conta de origem vinculada não pode ser usada em
lançamento automático (só manual); toda adição usada em cálculo carrega,
na memória de cálculo, o dispositivo legal de origem, quando cadastrado
(rastreabilidade — AGENTS.md).

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** Adição vinculada a conta contábil aparece como
candidata no lançamento do período correspondente (LAL-05); adição sem
conta de origem não trava a apuração, mas fica marcada como lançamento
manual.

**Não copiar/riscos.** **Não copiar o catálogo do manual como se fosse
lista oficial fechada.** O manual documenta *campos e mecânica* de
cadastro — o **conteúdo** de cada adição (que despesa é, de fato,
indedutível) é matéria de direito tributário, e cada uma precisa de
fundamento próprio antes de virar cadastro padrão do produto.

**Perguntas.** O escritório do Fred tem um catálogo próprio de adições já
usado no sistema de referência hoje, que possa servir de ponto de
partida (sujeito a conferência), ou o cadastro nasce vazio, por cliente?

### LAL-03 — Cadastro de exclusões

**O que é.** O espelho de LAL-02 para exclusões: receitas contabilizadas
que a legislação não tributa, ou deduções específicas permitidas na
apuração do lucro real.

**Exemplo.** Exclusão "Resultado positivo de equivalência patrimonial",
ligada ao imposto "Ambos", vinculada à conta "Resultado de Equivalência
Patrimonial" (a mesma linha que a DRE já classifica como
`RESULTADO_EQUIVALENCIA_PATRIMONIAL`) — o ganho de equivalência é
tributado apenas na distribuição, não no resultado contábil, então é
excluído do lucro real no período em que apurado (mecânica geral;
**a confirmar dispositivo exato**).

**Referência de rotina.** Manual, páginas 106-111 (mesma estrutura de
LAL-02, com "percentual limite para importação dos saldos das contas"
como campo próprio da exclusão).

**Fonte normativa.** **A confirmar** — **RIR/2018** e **IN RFB
1.700/2017**, mesma ressalva de LAL-02: sem catálogo fechado, cada
exclusão com fundamento próprio. A equivalência patrimonial, em
particular, tem base no **art. 389 do RIR/2018** (exclusão do valor do
resultado positivo, a confirmar).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-01, CTB-01.

**Dados.** Modelo novo `Exclusao`, espelhando `Adicao` (LAL-02), com o
campo adicional "percentual limite para importação dos saldos das
contas" (permite excluir só uma fração do saldo da conta vinculada,
quando a regra exigir).

**Regras.** Mesmas de LAL-02, com o percentual limite aplicado **antes**
de compor o valor da exclusão do período (memória de cálculo mostra o
saldo bruto da conta e o valor limitado).

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** Exclusão com percentual limite de 50%, por
exemplo, sobre uma conta com saldo de R$ 10.000,00, produz exclusão de
exatamente R$ 5.000,00 (teste de referência).

**Não copiar/riscos.** Mesma ressalva de LAL-02.

**Perguntas.** Mesma de LAL-02.

### LAL-04 — Lucro antes da CSLL e do IRPJ (importado da DRE)

**O que é.** O ponto de partida do cálculo: o resultado contábil (lucro
ou prejuízo) do período, importado da Contabilidade, separado — quando
aplicável — em operacional e não operacional, e em geral e rural.

**Exemplo.** DRE do 1º trimestre de 2026 (via `apurar_dre`) devolve
`resultado_antes_dos_tributos_sobre_o_lucro = R$ 500.000,00`. Esse valor
é importado como "Lucro Operacional Geral" do trimestre no Lalur —
**é o ponto de partida do exemplo de LAL-06**.

**Referência de rotina.** Manual, páginas 201-204 (janela Lucro Antes da
CSLL e IRPJ: filtro por competência, opção "Importar o lucro/prejuízo
considerando a diferença do saldo das contas de resultado devedoras e
credoras", botão "Importar saldo").

**Fonte normativa.** Não se aplica ao mecanismo de importação; o
resultado contábil como ponto de partida do lucro real é **Decreto-Lei
1.598/1977, art. 6º** (a confirmar).

**Situação no DataLedger.** **Não existe** — mas a fonte de dados (a DRE)
já existe.

**Depende de.** LAL-01, CTB-10 (DRE, `apurar_dre`).

**Dados.** Modelo novo `LucroAntesDosTributos`: empresa, competência,
lucro/prejuízo operacional geral, lucro/prejuízo não operacional geral
(quando `apurar_lucro_prejuizo_nao_operacional` estiver ligado),
equivalentes rurais quando aplicável, origem (importado da DRE ou
digitado manualmente).

**Regras.** Quando importado, o valor **vem exatamente** de
`resultado_antes_dos_tributos_sobre_o_lucro` da competência
correspondente — nunca recalculado por fórmula paralela; reimportação da
mesma competência **não duplica** o lançamento (idempotência,
AGENTS.md); alteração manual depois de importado é trilhada, com o valor
original preservado para conferência.

**Telas e documentos.** Tela de importação/lançamento — classe
**conferência**.

**Critérios de aceite.** Teste de integração: `apurar_dre` de uma
competência com resultado antes dos tributos de R$ 500.000,00 produz,
após importação, `LucroAntesDosTributos` com o mesmo valor, em `Decimal`,
sem arredondamento adicional.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** O DataLedger separa "lucro/prejuízo não operacional" da
mesma forma que o sistema de referência (uma tela própria, distinta do
operacional), ou o Fred prefere que essa distinção fique dentro da
própria estrutura da DRE?

### LAL-05 — Lançamentos de adições e exclusões da CSLL e do IRPJ

**O que é.** O lançamento efetivo, período a período, das adições e
exclusões cadastradas (LAL-02/LAL-03) — separadamente para CSLL e para
IRPJ, e (quando aplicável) para atividade geral e rural.

**Exemplo — o do pedido do Fred.** Lucro contábil (LAL-04) **R$
500.000,00** + adição "Multa indedutível" **R$ 20.000,00** − exclusão
"Resultado positivo de equivalência patrimonial" **R$ 30.000,00** =
**lucro real do período: R$ 490.000,00** (500.000,00 + 20.000,00 −
30.000,00).

**Referência de rotina.** Manual, páginas 137-201 (as telas de
Lançamentos de Adições e Exclusões, por imposto — CSLL, IRPJ — e por
atividade — geral, rural, lucro da exploração —, cada uma com grupo,
complemento, e detalhamento opcional).

**Fonte normativa.** Mesma de LAL-02/LAL-03 — cada adição/exclusão tem
fundamento próprio; a **mecânica de soma** (lucro contábil + adições −
exclusões = lucro real) é do **Decreto-Lei 1.598/1977, art. 6º**, e da
**IN RFB 1.700/2017**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-02, LAL-03, LAL-04.

**Dados.** Modelo novo `LancamentoDeAjuste`: empresa, competência,
imposto (CSLL/IRPJ), tipo (adição/exclusão), referência ao cadastro
(LAL-02 ou LAL-03), valor, grupo, complemento, detalhamento por conta
contábil (quando o parâmetro LAL-01 "Lançar adições e exclusões
detalhando os lançamentos contábeis" estiver ligado).

**Regras.** `Decimal` em todo valor; lançamento efetivado (dentro de
apuração encerrada) é imutável, corrigido por procedimento rastreável
(mesma regra geral do lançamento contábil); soma de adições/exclusões do
período é auditável linha a linha até a conta de origem.

**Telas e documentos.** Tela de lançamento — classe **conferência**.

**Critérios de aceite.** Teste de referência com o exemplo do Fred (lucro
real de R$ 490.000,00) provando a soma exata em `Decimal`; lançamento
detalhado por conta soma exatamente o valor do lançamento agregado.

**Não copiar/riscos.** Nenhum específico além do já registrado em
LAL-02/LAL-03.

**Perguntas.** Nenhuma além das já registradas.

### LAL-06 — Apuração trimestral ou anual do IRPJ e da CSLL, com adicional

**O que é.** O motor que, a partir do lucro real do período (LAL-05),
calcula o IRPJ (com **adicional** sobre a parcela que exceder o limite),
a CSLL, e o saldo a pagar (ou a compensar) de cada um.

**Exemplo — o do pedido do Fred.** Lucro real do trimestre **R$
490.000,00**, sem prejuízo fiscal a compensar neste exemplo (compensação
tratada em LAL-11). IRPJ: alíquota de **15% sobre o lucro real** ("da
legislação vigente, a confirmar" — Lei 9.249/1995, art. 3º) = R$
73.500,00; **adicional de 10%** sobre o que exceder R$ 60.000,00 no
trimestre (limite mensal de R$ 20.000,00 × 3 — "da legislação vigente, a
confirmar", mesma Lei 9.249/1995) = 10% × (490.000,00 − 60.000,00) = R$
43.000,00; **IRPJ total R$ 116.500,00**. CSLL: alíquota de **9%** ("da
legislação vigente, a confirmar" — Lei 7.689/1988 e alterações) = R$
44.100,00. **Nenhum destes percentuais deve entrar em código sem
confirmação da vigência aplicável à competência calculada.**

**Referência de rotina.** Manual, páginas 135-137 (janela Calcular:
período, trimestre/ano, resultado por imposto) e 76-77 (parâmetros:
código de recolhimento, alíquota do imposto — campo do cadastro, não
constante do sistema —, forma e dia de vencimento).

**Fonte normativa.** **A confirmar** — **Lei 9.249/1995, art. 3º**
(alíquota do IRPJ e adicional); **Lei 7.689/1988** e alterações
(alíquota da CSLL, que já teve mais de um percentual ao longo do tempo,
inclusive por tipo de pessoa jurídica — o próprio manual, página 75,
mostra opções históricas de 17% e 20% para instituições financeiras);
**IN RFB 1.700/2017** para a mecânica de apuração trimestral × anual.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-05, LAL-01 (tipo de cálculo, qualificação da pessoa
jurídica).

**Dados.** Resultado por imposto e período: lucro real (ou base de
cálculo da CSLL, que pode diferir do IRPJ por adições/exclusões
específicas), alíquota aplicada, adicional (quando IRPJ), valor apurado,
com memória de cálculo rastreável até LAL-05.

**Regras.** Cálculo **determinístico e reprodutível** (mesmo padrão de
FIS-23/PAT-07); `Decimal` com escala e arredondamento explícitos;
alíquota e limite do adicional **vigentes na competência calculada**,
nunca os atuais do cadastro; competência encerrada exige reabertura
explícita para recalcular.

**Telas e documentos.** Tela de cálculo — classe **conferência**;
consolida no Livro Lalur (LAL-07) e nos demonstrativos (LAL-08).

**Critérios de aceite.** Teste de referência com o exemplo do Fred (IRPJ
R$ 116.500,00, CSLL R$ 44.100,00) provando o cálculo exato — **usando
valores de alíquota marcados como ilustrativos até confirmação
normativa**, nunca como caso de aceite definitivo sem essa confirmação;
recálculo duas vezes sobre os mesmos dados produz resultado idêntico.

**Não copiar/riscos.** **Não inventar alíquota nem limite do adicional.**
O exemplo acima usa valores históricos amplamente conhecidos só para
ilustrar a mecânica — **qualquer caso de teste real precisa da alíquota
confirmada em fonte oficial vigente na competência**, nunca copiada do
manual (que é de 2018 e já mostra, ele mesmo, mudanças de alíquota ao
longo do tempo).

**Perguntas.** A carteira do Fred tem cliente sujeito a adicional de
IRPJ hoje (lucro trimestral acima do limite)? E instituição financeira,
sujeita à alíquota diferenciada de CSLL?

### LAL-07 — Livro Lalur Parte A

**O que é.** O relatório/livro que consolida o cálculo do período no
formato do Livro de Apuração do Lucro Real, Parte A: lucro contábil,
adições, exclusões, lucro real, com as assinaturas do contador e do
responsável legal.

**Exemplo.** Livro Lalur do 1º trimestre de 2026, com a mecânica de
LAL-05/LAL-06 impressa em ordem: lucro contábil R$ 500.000,00, adições R$
20.000,00, exclusões R$ (30.000,00), lucro real R$ 490.000,00.

**Referência de rotina.** Manual, páginas 224-227 (janela Livro de
Apuração do Lucro Real: guia Geral com período por trimestre/ano).

**Fonte normativa.** **A confirmar** — hoje entregue dentro da **ECF**
(bloco M/N, a confirmar leiaute no **Manual de Orientação da ECF**,
Receita Federal/Sped); a forma impressa "avulsa" do Lalur, fora da ECF,
não é mais a obrigação principal desde a digitalização, mas pode
continuar como relatório de apoio do escritório.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-05, LAL-06.

**Dados.** Agregação formatada de LAL-05/LAL-06.

**Regras.** O livro reproduz **exatamente** o resultado do cálculo, sem
recalcular; período encerrado é imutável.

**Telas e documentos.** Relatório — classe **livro** (se numerado e
assinado; como relatório de apoio interno, pode nascer como
**demonstração**, a confirmar com o Fred qual é o uso real, já que a
obrigação oficial hoje é a ECF, LAL-26).

**Critérios de aceite.** Soma do livro bate exatamente com LAL-05/LAL-06
da mesma competência.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** O escritório do Fred ainda emite o Lalur "avulso" para
algum uso (arquivo interno, auditoria), ou hoje é só o bloco da ECF que
importa?

### LAL-08 — Demonstrativos de apuração de CSLL e IRPJ

**O que é.** A memória de cálculo detalhada de cada imposto, separada do
livro — o que o contador usa para conferir, linha a linha, como chegou
ao valor apurado.

**Exemplo.** Demonstrativo de IRPJ do 1º trimestre de 2026: lucro real,
alíquota, valor até o limite, excedente, adicional, dedução de incentivo
(quando houver, LAL-21), valor final a recolher.

**Referência de rotina.** Manual, páginas 228-231.

**Fonte normativa.** Mesma de LAL-06.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06.

**Dados.** Detalhamento de LAL-06.

**Regras.** Reproduz exatamente o cálculo, sem recálculo paralelo.

**Telas e documentos.** Relatório — classe **demonstração**.

**Critérios de aceite.** Soma do demonstrativo bate com LAL-06.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

## Onda 2 — Parte B e base negativa

### LAL-09 — Cadastro de contas da Parte B e da Base Negativa

**O que é.** O catálogo das "contas" de controle fiscal — não confundir
com `Conta` da Contabilidade (ver aviso na introdução, BL-398) — que
recebem os valores das diferenças temporárias (Parte B) e do prejuízo
fiscal acumulado (Base Negativa), cada uma com sua regra de compensação.

**Exemplo.** Conta de Parte B "Excesso de depreciação fiscal sobre a
societária — Veículos", tipo "Parte B", forma de compensação "Automática
quando a diferença se reverter" (ou "Manual", a confirmar as opções
suportadas).

**Referência de rotina.** Manual, páginas 120-121 (janela Base Negativa e
Parte B: identificador SPED ECF, descrição, tipo — Base Negativa ou
Parte B —, forma de compensar, "considerar o saldo desta conta por
lançamento").

**Fonte normativa.** **A confirmar** — a Parte B é estrutura do **Livro
de Apuração do Lucro Real**, formalizada hoje nos registros da **ECF**
(Manual de Orientação da ECF, blocos M) — o "identificador SPED ECF" do
manual sinaliza exatamente esse vínculo.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-01.

**Dados.** Modelo novo `ContaDeControleFiscal` (nome deliberadamente
diferente de `Conta`, para não confundir com a Contabilidade — ver
BL-398): empresa, código, identificador para a ECF, descrição, tipo
(base_negativa/parte_b), forma de compensação, data de cadastro, opção
"considerar o saldo desta conta por lançamento" (quando `compensar =
não_compensar`).

**Regras.** Isolamento por empresa; identificador da ECF **único por
empresa e tipo** (não pode haver duas contas de Parte B com o mesmo
identificador SPED); este modelo **não** herda de `Conta` nem reusa sua
hierarquia sintética/analítica (guarda de arquitetura, BL-398).

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** Teste que **prova a separação de modelo**: uma
`ContaDeControleFiscal` não possui `natureza`, `aceita_lancamento` nem
qualquer campo de partida dobrada — impedindo a extensão indevida que o
BL-398 previne.

**Não copiar/riscos.** **Este é o item mais sensível de arquitetura do
módulo inteiro:** implementar a Parte B como um caso especial de `Conta`
"resolveria rápido", mas quebraria a guarda de partida dobrada da
Contabilidade (débito = crédito, natureza fixa) para um dado que **não**
segue essa regra — a Parte B pode ter saldo só devedor, existir por anos
sem contrapartida, e não fazer parte de nenhum Balanço.

**Perguntas.** O identificador SPED ECF (bloco M) precisa ser confirmado
em fonte oficial antes de fixar o formato do campo — qual o leiaute
exato desses códigos no Manual de Orientação da ECF vigente?

### LAL-10 — Lançamentos da Parte B

**O que é.** O registro, período a período, dos valores que entram e
saem de cada conta de Parte B — tipicamente a contrapartida de uma
adição ou exclusão **temporária** (que se reverte no futuro), como a
diferença de depreciação.

**Exemplo — o do pedido do Fred (Patrimônio → Lalur).** Diferença de
depreciação de PAT-19: fiscal R$ 2.000,04, societária R$ 1.041,67,
diferença **R$ 958,37** no mês. Se a depreciação fiscal for maior (regra
geral quando a taxa fiscal é mais acelerada), essa diferença é **adição**
no Lalur (reduz o lucro contábil que já a "pagou antes da hora" na
Contabilidade, então soma de volta na base fiscal) e, simultaneamente,
**lançada na Parte B** como saldo a controlar — o saldo credor de R$
958,37 na conta "Excesso de depreciação fiscal — Veículos" que, quando a
depreciação societária ultrapassar a fiscal (ao fim da vida útil fiscal),
vira **exclusão** para reverter o controle (mecânica geral; sinal exato
a confirmar caso a caso na IN RFB 1.700/2017).

**Referência de rotina.** Manual, páginas 78-85 (registro automático via
parâmetro, guias Prejuízo geral, Prejuízo rural, Incentivo fiscal da
Parte B), e o registro automático citado no cadastro de cada
adição/exclusão (LAL-02/LAL-03, guia "Base Negativa e Parte B").

**Fonte normativa.** **A confirmar** — **IN RFB 1.700/2017**, arts. que
tratam do controle de diferenças temporárias na Parte B; para a
depreciação especificamente, cruza com a **Lei 12.973/2014** (mesma
fonte de PAT-19).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-09, LAL-05 (a adição/exclusão que origina o
lançamento), PAT-19 (quando a origem for depreciação).

**Dados.** Modelo novo `LancamentoDeControleFiscal`: conta de controle
(LAL-09), competência, valor, tipo de movimento (lançamento/compensação),
histórico, origem (referência à adição/exclusão de LAL-05, quando
automática).

**Regras.** Saldo da conta de controle é **acumulado ao longo do
tempo**, não zerado por competência (diferente do zeramento periódico da
Contabilidade); `Decimal` em todo valor; lançamento efetivado é imutável,
corrigido por procedimento rastreável; **nunca** soma-se este saldo a
nenhum saldo de `Conta` contábil — são domínios separados (BL-398).

**Telas e documentos.** Tela de lançamento — classe **conferência**.

**Critérios de aceite.** Teste de referência com o exemplo do Fred (saldo
acumulando R$ 958,37 por mês) provando que o saldo da conta de controle
soma corretamente ao longo de vários períodos, sem interferência do
zeramento contábil.

**Não copiar/riscos.** Mesmo risco de arquitetura de LAL-09.

**Perguntas.** Qual o sinal exato da adição/exclusão de depreciação em
cada situação (fiscal > societária vs. fiscal < societária) — precisa de
confirmação na IN RFB 1.700/2017 antes de qualquer caso de teste real.

### LAL-11 — Base negativa da CSLL e compensação de prejuízo fiscal (limite de 30%)

**O que é.** O controle do prejuízo fiscal (para IRPJ) e da base negativa
(para CSLL) apurados em períodos anteriores, e a **compensação** desse
saldo contra o lucro real de períodos seguintes, limitada a um percentual
da base do período — a regra que impede a empresa de zerar o imposto de
um ano lucrativo só com prejuízo acumulado de anos ruins.

**Exemplo — o do pedido do Fred.** Lucro real do trimestre (LAL-05) **R$
490.000,00**; saldo de prejuízo fiscal acumulado de períodos anteriores:
R$ 800.000,00. **Compensação limitada a 30% do lucro real do período**
("da Lei 9.065/1995, a confirmar", art. 15 e 16): 30% × 490.000,00 =
**R$ 147.000,00** — é esse o valor máximo compensável neste período,
mesmo o saldo acumulado sendo maior. **Base de cálculo do IRPJ após
compensação: R$ 490.000,00 − R$ 147.000,00 = R$ 343.000,00.** O saldo
remanescente de prejuízo (R$ 800.000,00 − R$ 147.000,00 = R$ 653.000,00)
permanece na base negativa/Parte B para compensar períodos futuros, **sem
prazo de prescrição** (regra geral do prejuízo fiscal no Brasil, a
confirmar que continua vigente sem alteração).

**Referência de rotina.** Manual, páginas 120-121 (cadastro da conta de
base negativa), 77-78 (parâmetros: "Registrar automaticamente na Base
Negativa e Parte B os prejuízos apurados", campos "Prejuízo apurados" e
"Compensação de prejuízos").

**Fonte normativa.** **A confirmar** — **Lei 9.065/1995, arts. 15 e 16**
(limite de 30% para compensação de prejuízo fiscal do IRPJ e da base
negativa da CSLL); **IN RFB 1.700/2017** para a mecânica de apuração.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-09, LAL-10, LAL-06 (lucro real do período, base do
limite de 30%).

**Dados.** Saldo acumulado de prejuízo fiscal (IRPJ) e de base negativa
(CSLL), por empresa, com histórico de compensação por período —
rastreável até o saldo remanescente após cada compensação.

**Regras.** Compensação **nunca excede 30% do lucro real do período**
(guarda que vira teste de limite, não só de sucesso); compensação nunca
excede o saldo acumulado disponível (o menor entre os dois limites);
saldo remanescente é preservado exatamente (sem arredondamento que
"perca" centavos ao longo de vários períodos — `Decimal` com escala
explícita).

**Telas e documentos.** Tela de compensação — classe **conferência**,
integrada ao cálculo (LAL-06).

**Critérios de aceite.** Teste de referência com o exemplo do Fred
(compensação de R$ 147.000,00, saldo remanescente de R$ 653.000,00)
provando os dois limites (30% do período e saldo disponível) em casos
separados — inclusive o caso em que o saldo acumulado é **menor** que
30% do lucro do período (a compensação usa o saldo todo, não o limite
cheio).

**Não copiar/riscos.** **Não inventar o percentual nem presumir que ele
nunca mudou** — 30% é a regra amplamente conhecida desde 1995, mas a
confirmação em fonte oficial vigente é obrigatória antes de fixar
qualquer constante no código (AGENTS.md).

**Perguntas.** Há cliente na carteira com prejuízo fiscal acumulado
relevante hoje, que dependa desta compensação no primeiro caso real de
uso?

### LAL-12 — Saldo inicial da Parte B e da Base Negativa

**O que é.** A implantação do saldo de Parte B e de base negativa que a
empresa já tinha **antes** de começar a usar o DataLedger — equivalente
ao lançamento de saldos iniciais da Contabilidade (RC-53/RC-62), mas para
este razão de controle fiscal.

**Exemplo.** Empresa migra para o DataLedger em 01/2026, com saldo de
base negativa de CSLL de R$ 653.000,00 acumulado até 12/2025 (o
remanescente do exemplo de LAL-11) — esse saldo entra como implantação,
datado de 31/12/2025, sem afetar nenhuma apuração de competência anterior
no sistema novo.

**Referência de rotina.** Manual, páginas 82-85 (guia Saldo Inicial:
Parte B e Base Negativa CSLL e Incentivos Fiscais, com SCP quando
aplicável, conta, valor, tipo credor/devedor, histórico).

**Fonte normativa.** Não se aplica ao mecanismo de implantação; o saldo
implantado é o resultado de apurações anteriores, já regidas pelas fontes
de LAL-10/LAL-11.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-09.

**Dados.** Lançamento de abertura por conta de controle fiscal: valor,
tipo (credor/devedor), histórico, data de implantação.

**Regras.** Implantação é **um evento datado**, não retroage sobre
competências já calculadas no sistema; mesma cautela de RC-53/RC-62
(procedimento de implantação de saldos iniciais da Contabilidade) —
adaptada para não ser partida dobrada (não exige "fechar" contra
nenhuma outra conta, porque a Parte B não é balanço).

**Telas e documentos.** Tela de implantação — classe **cadastro**.

**Critérios de aceite.** Saldo implantado aparece corretamente como
ponto de partida da primeira compensação calculada no sistema (teste de
integração com LAL-11).

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além da confirmação de que a migração de clientes
existentes precisará deste procedimento (decisão de produto, não
normativa).

## Onda 3 — Guias DARF e quotas

### LAL-13 — Compensação de impostos federais (DComp)

**O que é.** O registro de valores de IRPJ/CSLL compensados com créditos
próprios (retenções, pagamentos indevidos, outros tributos federais),
formalizados perante a Receita Federal por DComp (Declaração de
Compensação) ou processo.

**Exemplo.** IRPJ a recolher do trimestre R$ 116.500,00, compensado com
crédito de R$ 30.000,00 de IRRF retido sobre aplicação financeira,
formalizado por DComp nº 12345.678901/2026-11 — saldo a recolher após
compensação: R$ 86.500,00.

**Referência de rotina.** Manual, páginas 207-210 (janela Compensações de
Impostos Federais: data, valor, operação, tipo de crédito, formalização
do pedido, nº DComp/processo, guia Compensação, guia Contabilidade).

**Fonte normativa.** **A confirmar** — **IN RFB 1.717/2017** (compensação
tributária federal) e legislação correlata do DComp/PER-DCOMP.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06.

**Dados.** Modelo novo `CompensacaoDeImposto`: empresa, competência,
imposto compensado, valor, tipo de crédito, número do DComp/processo,
observação, lançamento contábil associado.

**Regras.** Compensação nunca excede o valor devido do imposto no
período; lançamento contábil associado fecha em débitos = créditos.

**Telas e documentos.** Tela de compensação — classe **conferência**.

**Critérios de aceite.** Compensação registrada reduz exatamente o saldo
a pagar do imposto correspondente, sem alterar o valor apurado (LAL-06),
só o saldo a recolher.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** A carteira do Fred compensa IRPJ/CSLL com créditos
próprios hoje? Com que frequência?

### LAL-14 — Parcelamento de impostos

**O que é.** A divisão do valor a recolher em parcelas, quando o valor
ultrapassa o limite mínimo para parcela única (o manual documenta 2 ou 3
parcelas conforme faixa de valor).

**Exemplo.** IRPJ do ajuste anual de R$ 9.000,00, parcelado em 3 vezes de
R$ 3.000,00 (valor acima do limite mínimo do manual, "R$ 3.000,00 para 3
parcelas" — **valor histórico do manual, a confirmar na legislação
vigente do imposto específico antes de virar regra do produto**).

**Referência de rotina.** Manual, páginas 212-213 (janela Parcelamento de
Impostos: filtro por trimestre/ano, lista de impostos parceláveis,
parcelas geradas).

**Fonte normativa.** **A confirmar** — regra de parcelamento do IRPJ por
estimativa/ajuste é dada pela **Lei 9.430/1996** (arts. 5º e 6º); os
valores mínimos por parcela e o número de parcelas variam por norma e por
tipo de apuração.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06.

**Dados.** Modelo novo `ParcelaDeImposto`: empresa, imposto, competência,
número da parcela, valor, vencimento.

**Regras.** Soma das parcelas geradas é **exatamente** igual ao valor a
recolher do imposto (sem perda de centavo por arredondamento — a última
parcela absorve o resíduo, mesma prática de outras rotinas de
parcelamento do domínio); número de parcelas obedece ao limite mínimo por
valor, **confirmado em fonte oficial antes de virar regra**.

**Telas e documentos.** Tela de parcelamento — classe **conferência**.

**Critérios de aceite.** Teste de referência com soma das parcelas =
valor total, incluindo o caso de resíduo de centavos na última parcela.

**Não copiar/riscos.** Não copiar os valores mínimos do manual (2018)
sem conferência de vigência.

**Perguntas.** Nenhuma além da confirmação normativa.

### LAL-15 — Pagamento de impostos, com baixa

**O que é.** O registro de que uma guia (ou parcela) foi efetivamente
paga, com data, valor, juros e multa quando em atraso — a baixa que
fecha o ciclo entre "apurado" e "pago".

**Exemplo.** IRPJ do 1º trimestre, R$ 116.500,00, vencimento 30/04/2026,
pago em 30/04/2026 sem atraso — baixa integral, sem juros nem multa.

**Referência de rotina.** Manual, páginas 213-217 (janela Pagamento de
Impostos: competência, situação, consulta e-CAC para importar baixa —
funcionalidade de integração externa, tratada como referência, não como
requisito deste plano).

**Fonte normativa.** Não se aplica ao mecanismo; juros e multa de mora
seguem a **Lei 9.430/1996** (taxa Selic) e normas de cobrança vigentes —
**a confirmar se e quando o DataLedger calcula isso automaticamente ou
só registra o valor informado pelo contador**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06, LAL-14, LAL-16.

**Dados.** Modelo novo `PagamentoDeImposto`: empresa, imposto,
competência/parcela, data de pagamento, valor principal, juros, multa,
lançamento contábil associado.

**Regras.** Pagamento não pode exceder o valor devido da parcela/guia sem
justificativa explícita (juros e multa são campos separados, não somados
ao "principal" sem distinção); lançamento contábil associado fecha em
débitos = créditos.

**Telas e documentos.** Tela de pagamento — classe **conferência**.

**Critérios de aceite.** Baixa registrada marca a parcela/guia como paga,
sem permitir dupla baixa da mesma parcela (idempotência).

**Não copiar/riscos.** A **importação automática do e-CAC** (consulta ao
portal da Receita Federal) é integração externa com credenciais reais —
**fora de escopo deste plano** até haver decisão própria de produto sobre
integrações oficiais (mesma cautela que vale para qualquer integração
homologada, AGENTS.md §7).

**Perguntas.** O escritório do Fred hoje registra pagamento manualmente,
ou usa alguma integração com banco/Receita que precise ser mapeada à
parte?

### LAL-16 — Guias DARF (normal, quotas, ajuste anual)

**O que é.** A emissão da guia de recolhimento (DARF) para CSLL e/ou
IRPJ, nas três variações do sistema de referência: normal (pagamento
integral), quotas (parcelado) e ajuste anual (regime de estimativa).

**Exemplo.** DARF Normal do IRPJ do 1º trimestre, código de recolhimento
próprio do imposto, valor R$ 116.500,00, vencimento conforme regra do
imposto (**a confirmar prazo exato na Lei 9.430/1996**), com juros e
multa preenchidos apenas se a data de recolhimento for posterior ao
vencimento.

**Referência de rotina.** Manual, páginas 239-244 (DARF Normal, DARF
Quotas com Taxa Selic para a 3ª parcela, DARF Ajuste Anual).

**Fonte normativa.** **A confirmar** — código de recolhimento e leiaute
da guia DARF: **Receita Federal, Manual de Preenchimento do DARF**;
prazos de vencimento: **Lei 9.430/1996**; taxa Selic para atraso:
divulgação mensal do Banco Central/Receita Federal (nunca fixa no
código, sempre por competência).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06, LAL-14 (quotas), LAL-19 (ajuste anual).

**Dados.** Guia formatada: código de recolhimento, período de apuração,
valor principal, juros, multa, valor total, CNPJ e razão social.

**Regras.** Valor da guia bate exatamente com o valor apurado (LAL-06)
menos compensações (LAL-13) já registradas; juros/multa calculados só
quando a data de recolhimento informada for posterior ao vencimento, e
nunca com taxa fixa no código (Selic muda mês a mês).

**Telas e documentos.** Guia — classe **guia**.

**Critérios de aceite.** Valor total da guia = valor apurado − compensado
+ juros + multa, testado com e sem atraso.

**Não copiar/riscos.** Não copiar código de recolhimento do manual sem
confirmar que ainda é o vigente (código de recolhimento de DARF pode
mudar).

**Perguntas.** Quais códigos de recolhimento a carteira do Fred usa hoje
(regime trimestral, estimativa, ajuste anual)?

## Onda 4 — Estimativa e balanço de redução/suspensão

### LAL-17 — Receita bruta e operações de receita (base da estimativa)

**O que é.** O cadastro das "operações de receita" da empresa (vendas,
serviços, não operacional), cada uma ligada a acumuladores da Escrita
Fiscal, e o lançamento mensal da receita bruta que serve de base ao
cálculo do lucro estimado.

**Exemplo.** Operação de receita "Venda de Mercadorias", tipo "Vendas",
alíquota de base de cálculo do IRPJ **8%** e da CSLL **12%** ("da
legislação vigente, a confirmar" — percentuais de presunção do lucro
estimado, **Lei 9.249/1995, art. 15/20**), vinculada ao acumulador fiscal
"Venda de Mercadorias" — a receita do mês, importada do Fiscal, vira base
de cálculo automaticamente.

**Referência de rotina.** Manual, páginas 111-113 (cadastro de Operação
de Receita: tipo, alíquotas de base de cálculo, acumuladores) e 204-207
(lançamento de Receita Bruta: importação em grupo, importação por
acumulador).

**Fonte normativa.** **A confirmar** — percentuais de presunção do lucro
estimado (que, apesar do nome parecido, são **os mesmos** do Lucro
Presumido): **Lei 9.249/1995, arts. 15 (IRPJ) e 20 (CSLL)** — variam por
atividade (comércio, indústria, serviço, com faixas diferentes).

**Situação no DataLedger.** **Não existe** — **depende do Fiscal**
(acumuladores, FIS-07, e apuração, FIS-23).

**Depende de.** LAL-01 (só quando "Calcular Lucro Estimado" estiver
ligado), FIS-07.

**Dados.** Modelo novo `OperacaoDeReceita`: empresa, código, descrição,
tipo (vendas/serviços/não operacional), alíquota de base de cálculo do
IRPJ e da CSLL, acumuladores fiscais vinculados, contas contábeis de
dedução; `ReceitaBrutaLancada`: competência, operação de receita, valor
da receita, deduções, base de cálculo calculada.

**Regras.** Percentual de presunção **vigente na competência calculada**,
nunca o atual do cadastro; importação da receita do Fiscal não duplica se
repetida (idempotência).

**Telas e documentos.** Tela de cadastro (classe **cadastro**) e tela de
lançamento (classe **conferência**).

**Critérios de aceite.** A definir junto do plano de etapa, com caso de
referência confirmado em fonte oficial.

**Não copiar/riscos.** Não inventar percentual de presunção por
atividade.

**Perguntas.** A carteira do Fred usa o regime de estimativa mensal
(diferente do trimestral por lucro real "cheio")? Para quais atividades?

### LAL-18 — Ganhos (base do lucro estimado)

**O que é.** O cadastro de contas contábeis de **ganhos** (não
operacionais, financeiros) que compõem a base do lucro estimado, além da
receita bruta operacional de LAL-17.

**Exemplo.** Conta contábil "Ganho na Venda de Imobilizado" (a mesma
origem de PAT-11) vinculada ao cadastro de ganho "Ganhos de Capital" —
soma-se à base do lucro estimado do mês em que ocorreu.

**Referência de rotina.** Manual, páginas 113-114 (cadastro de Ganhos:
descrição, contas contábeis vinculadas).

**Fonte normativa.** **A confirmar** — **Lei 9.249/1995, art. 15, § 1º**
e **IN RFB 1.700/2017** (acréscimo de ganhos de capital e demais
receitas à base do lucro estimado).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-17, PAT-11 (ganho de capital como origem comum).

**Dados.** Modelo novo `Ganho`: empresa, código, descrição, contas
contábeis vinculadas.

**Regras.** Mesmas de LAL-17.

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além das já registradas em LAL-17.

### LAL-19 — Ajuste anual e comparativo real × estimado

**O que é.** No regime de estimativa (ou balanço de redução/suspensão com
estimativa), o fechamento de dezembro que compara o total pago mês a mês
por estimativa com o valor apurado pelo lucro real do ano inteiro,
gerando saldo a pagar (ajuste) ou a restituir/compensar. O "comparativo
real × estimado" apoia a **escolha** do regime mais vantajoso.

**Exemplo.** Total pago por estimativa ao longo do ano: R$ 100.000,00.
Apurado pelo lucro real anual: R$ 116.500,00. **Ajuste anual a recolher:
R$ 16.500,00** (LAL-16, guia DARF Ajuste Anual).

**Referência de rotina.** Manual, páginas 136-137 (janela Ajuste Anual:
dedução do CSLL/IRPJ pago por estimativa em dezembro) e 217-219 (janela
Opção de Cálculo: saldo real × estimado lado a lado, escolha do mais
vantajoso).

**Fonte normativa.** **A confirmar** — **Lei 9.430/1996, art. 2º**
(ajuste anual do regime de estimativa).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06, LAL-15 (pagamentos já efetuados no ano), LAL-17.

**Dados.** Agregação anual: total apurado por estimativa mês a mês, total
pago, total apurado pelo lucro real anual, diferença (ajuste).

**Regras.** Ajuste = apurado pelo lucro real anual − total já pago no
ano, nunca recalculado com fórmula divergente entre telas.

**Telas e documentos.** Tela de cálculo — classe **conferência**.

**Critérios de aceite.** Teste de referência com o exemplo acima (ajuste
de R$ 16.500,00).

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além das já registradas em LAL-17.

### LAL-20 — Balanço de redução e suspensão

**O que é.** Uma variação do regime de estimativa em que a empresa
**reduz ou suspende** o pagamento mensal quando um balanço/balancete
intermediário demonstra que o lucro real acumulado até aquele mês é menor
que a soma das estimativas já calculadas — em vez de pagar a estimativa
cheia, paga só o que o balanço de suspensão indica.

**Exemplo.** Estimativa de julho seria R$ 10.000,00 pela regra padrão;
balanço de redução e suspensão de janeiro a julho aponta lucro real
acumulado que resultaria em apenas R$ 7.000,00 de IRPJ acumulado — a
empresa recolhe R$ 7.000,00 (ou menos, dependendo do que já foi pago nos
meses anteriores) em vez dos R$ 10.000,00 da estimativa cheia.

**Referência de rotina.** Manual, página 62 (parâmetro: tipo de cálculo
"Anual/Balanço de Redução e Suspensão") e as diversas opções que só se
habilitam para esse tipo de cálculo, espalhadas pelas páginas 62-63 e
77-78 (dedução automática de valores apurados em meses anteriores,
consideração de deduções lançadas só na competência do cálculo).

**Fonte normativa.** **A confirmar** — **Lei 9.430/1996, art. 35**
(suspensão ou redução do pagamento mensal por balanço ou balancete).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-01, LAL-06, LAL-17.

**Dados.** Resultado do balanço/balancete de redução e suspensão por
competência, comparado ao acumulado das estimativas.

**Regras.** O pagamento do mês **nunca é negativo** (se o balanço indicar
valor menor que zero, o recolhimento do mês é suspenso, não vira crédito
automático sem base normativa confirmada); cálculo determinístico e
reprodutível.

**Telas e documentos.** Tela de cálculo — classe **conferência**.

**Critérios de aceite.** A definir junto do plano de etapa, com caso de
referência confirmado em fonte oficial — este é um dos regimes mais
complexos do módulo e não deve ser o primeiro a ser implementado.

**Não copiar/riscos.** Regime avançado e menos comum — risco de
implementar uma mecânica que a carteira do Fred nunca usa. Confirmar
demanda real antes de priorizar.

**Perguntas.** A carteira do Fred tem cliente que usa balanço de redução
e suspensão hoje?

## Onda 5 — Incentivos

### LAL-21 — Incentivos fiscais

**O que é.** O cadastro e o aproveitamento de incentivos que reduzem o
IRPJ (e, em menor número, a CSLL) devido — Programa de Alimentação do
Trabalhador (PAT), incentivo cultural, desenvolvimento tecnológico,
atividade audiovisual, fundos da criança/idoso, entre outros —, cada um
com **alíquota de aproveitamento** e **limite** próprios.

**Exemplo.** Incentivo "PAT" informado por "Número de refeições": 2.000
refeições/mês a R$ 12,00 cada = R$ 24.000,00 de gasto; alíquota de
aproveitamento e limite "da legislação vigente, a confirmar" (o PAT tem
regra histórica de dedução de até 4% do IRPJ devido, calculada sobre um
valor de refeição limitado por norma própria — **nenhum destes números
deve virar constante sem confirmação**).

**Referência de rotina.** Manual, páginas 119-120 (janela Incentivos
Fiscais: tipo, PAT sim/não, informado por número de refeições ou valor,
alíquota, limite de aproveitamento, "aproveitar o valor excedido nos
períodos subsequentes") e 70-73 (parâmetros: contas contábeis por tipo de
incentivo — alimentação do trabalhador, cultura, vale-cultura,
desenvolvimento tecnológico, audiovisual, fundos da criança/idoso,
esporte, oncologia, deficiência, licença-maternidade).

**Fonte normativa.** **A confirmar** — cada incentivo tem lei própria:
PAT (**Lei 6.321/1976**), cultura (**Lei 8.313/1991 — Rouanet**),
audiovisual (**Lei 8.685/1993**), desenvolvimento tecnológico (**Lei
11.196/2005 — Lei do Bem**), entre outras — **nenhuma alíquota nem
limite entra em código sem confirmação item a item**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06 (o incentivo reduz o imposto apurado), LAL-09
(registro automático em Parte B, quando o incentivo gera saldo a
aproveitar em períodos futuros).

**Dados.** Modelo novo `IncentivoFiscal`: empresa, código, descrição,
tipo, alíquota de aproveitamento, limite de aproveitamento (percentual),
opção de aproveitar excedente em períodos subsequentes; lançamento
mensal: valor informado (refeições ou valor gasto, conforme o tipo),
valor calculado, valor aproveitado, valor excedente.

**Regras.** Valor aproveitado nunca excede o limite de aproveitamento
calculado sobre a base do período; excedente, quando a opção estiver
ligada, é controlado como saldo que atravessa competências (mesma
mecânica de razão de controle da Parte B, LAL-09/LAL-10, nunca como
`Conta` contábil).

**Telas e documentos.** Tela de cadastro (classe **cadastro**) e de
lançamento (classe **conferência**).

**Critérios de aceite.** A definir junto do plano de etapa, por
incentivo, com fonte legal confirmada antes de cada um entrar em código.

**Não copiar/riscos.** **Não copiar alíquota nem limite de nenhum
incentivo do manual** — cada um tem legislação própria, com vigência que
muda.

**Perguntas.** Quais incentivos, exatamente, a carteira do Fred usa hoje?
Implementar o catálogo inteiro sem essa resposta seria desproporcional.

## Onda 6 — Lucro da exploração

### LAL-22 — Lucro da exploração

**O que é.** Um cálculo específico para empresas com incentivo fiscal
regional (áreas da SUDAM/SUDENE, por exemplo) que apuram um "lucro da
exploração" separado do lucro real geral, usado como base para o
benefício de redução ou isenção do IRPJ.

**Exemplo.** Empresa industrial na área de atuação da SUDENE com
incentivo de redução de 75% do IRPJ sobre o lucro da exploração ("da
legislação vigente, a confirmar") — o lucro da exploração apurado
separadamente determina a parcela do IRPJ beneficiada pela redução.

**Referência de rotina.** Manual, referências ao "Lucro da Exploração"
espalhadas pelos cadastros de adição/exclusão (páginas 102, 107) e pelos
parâmetros (página 62, "Calcular Lucro da Exploração").

**Fonte normativa.** **A confirmar** — incentivos de redução/isenção do
IRPJ por lucro da exploração em área incentivada: **art. 1º e seguintes
da Lei 8.167/1991**, e regulamentação da SUDAM/SUDENE — **matéria
específica, sem dispositivo único simples, exige levantamento próprio
antes de qualquer implementação**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-02, LAL-03 (adições/exclusões específicas do lucro da
exploração), LAL-06.

**Dados.** Cálculo paralelo ao de LAL-06, com o conjunto próprio de
adições/exclusões marcadas "Lucro da Exploração".

**Regras.** Mesmas de LAL-06, aplicadas ao subconjunto de lançamentos do
lucro da exploração.

**Telas e documentos.** Relatório — classe **demonstração**.

**Critérios de aceite.** A definir junto do plano de etapa — item
avançado, provavelmente de baixa prioridade sem cliente com incentivo
regional confirmado.

**Não copiar/riscos.** Matéria de incentivo regional é complexa e pouco
usual — risco real de implementar sem demanda.

**Perguntas.** A carteira do Fred tem cliente com incentivo fiscal
regional (SUDAM/SUDENE) que dependa deste cálculo?

## Onda 7 — SCP

### LAL-23 — Sociedade em Conta de Participação (SCP)

**O que é.** A apuração **separada** do IRPJ/CSLL da SCP (uma sociedade
sem personalidade jurídica própria, em que um sócio ostensivo opera em
nome da sociedade) — o Lalur da SCP roda com seus próprios parâmetros,
adições, exclusões e apuração, distintos dos da empresa (sócio
ostensivo) que a controla.

**Exemplo.** Empresa "Construtora Beta Ltda." (sócio ostensivo) com uma
SCP "Empreendimento Alfa" para um projeto específico — a apuração de
IRPJ/CSLL da SCP é calculada e controlada separadamente, com seu próprio
Lalur, embora o recolhimento seja feito pelo sócio ostensivo.

**Referência de rotina.** Manual, páginas 114-119 (cadastro de SCP: CNPJ,
nome, data de abertura, situação, vigência, guias Geral, Lucro/Prejuízo,
Opções — espelhando os parâmetros da empresa, mas por SCP).

**Fonte normativa.** **A confirmar** — **RIR/2018, arts. 254 a 257** (SCP
como contribuinte do IRPJ equiparado a pessoa jurídica, com apuração
distinta da do sócio ostensivo).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-01 (a flag "Possui SCP" habilita este item para a
empresa).

**Dados.** Modelo novo `SociedadeEmContaDeParticipacao`: sócio ostensivo
(empresa), CNPJ, nome, data de abertura, situação (ativa/inativa),
parâmetros próprios (mesma estrutura de LAL-01, mas por SCP): tipo de
cálculo, atividade, contas de lucro/prejuízo, opções de cálculo estimado.
Todos os demais modelos deste plano (adição, exclusão, lançamento,
apuração) ganham um campo opcional `scp` para segregar o cálculo quando
aplicável.

**Regras.** Isolamento **dentro da mesma empresa**: a apuração da SCP
nunca se mistura com a apuração geral do sócio ostensivo, mesmo
pertencendo à mesma empresa/tenant; SCP inativa não recebe novo
lançamento.

**Telas e documentos.** Tela de cadastro (classe **cadastro**); demais
telas do módulo ganham filtro/seleção de SCP.

**Critérios de aceite.** Apuração de uma empresa com SCP produz dois
resultados **distintos e não somados automaticamente** — o da empresa e
o da SCP — cada um auditável separadamente.

**Não copiar/riscos.** Nenhum específico além do cuidado de isolamento já
descrito.

**Perguntas.** A carteira do Fred tem cliente com SCP hoje?

## Onda 8 — Eventos societários

### LAL-24 — Cisão parcial e incorporação, sobre a Parte B

**O que é.** O tratamento do saldo da Parte B e da base negativa quando a
empresa passa por um evento societário — cisão parcial (parte do
patrimônio vai para outra empresa, proporcionalmente) ou incorporação (a
empresa é absorvida por outra) — que decide o que acontece com os saldos
acumulados de diferenças temporárias e de prejuízo fiscal.

**Exemplo.** Cisão parcial com 30% do patrimônio transferido para outra
empresa: saldo de base negativa de R$ 653.000,00 (do exemplo de LAL-11)
é reduzido proporcionalmente, salvo as contas marcadas como "não
sofrerão impacto com a cisão" — **regra exata de proporcionalidade e de
quais saldos são ou não afetados precisa de confirmação normativa**.

**Referência de rotina.** Manual, páginas 219-221 (janela Cisão Parcial:
percentual do patrimônio transferido, contas da Parte B excluídas da
proporcionalidade; janela Incorporação: contas da Base Negativa e Parte B
que não são finalizadas no evento).

**Fonte normativa.** **A confirmar** — **RIR/2018** e **Lei 9.532/1997**
tratam da compensação de prejuízos fiscais em eventos de cisão,
incorporação e fusão, com **restrições específicas** (a regra geral é
que prejuízo fiscal **não se transfere** para a sucessora, mas o
tratamento do saldo remanescente na cindida/incorporada tem mecânica
própria) — **matéria de maior risco normativo deste plano, junto de
PAT-24, e não deve virar código sem validação profissional específica**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-09, LAL-10, LAL-11.

**Dados.** Modelo novo `EventoSocietario`: empresa, tipo (cisão
parcial/incorporação), data, percentual de patrimônio transferido (cisão),
contas de controle fiscal excluídas do impacto proporcional.

**Regras.** A definir junto do plano de etapa, **após** confirmação
normativa — nenhuma regra de proporcionalidade entra em código por
inferência do manual.

**Telas e documentos.** Tela de evento societário — classe
**conferência**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Não copiar/riscos.** **Risco normativo alto:** eventos societários e
compensação de prejuízo fiscal têm regra restritiva específica (Lei
9.532/1997) que pode contradizer a mecânica "proporcional" sugerida pelo
manual — **validação profissional do Fred obrigatória antes de
qualquer implementação**.

**Perguntas.** A carteira do Fred tem cliente em processo de cisão ou
incorporação que dependa deste item no curto prazo? Dado o risco
normativo, este item deveria ficar represado até haver caso real.

## Onda 9 — Lalur dentro da ECF

### LAL-25 — Integração contábil (provisão de IRPJ e CSLL)

**O que é.** A geração, para a Contabilidade, do lançamento de provisão
do IRPJ e da CSLL apurados no período — a contrapartida contábil que fecha
o ciclo entre o cálculo fiscal (Lalur) e o livro contábil.

**Exemplo.** IRPJ do trimestre R$ 116.500,00: débito "Provisão para IRPJ e
CSLL" (despesa, a mesma linha `PROVISAO_IRPJ_CSLL` que a DRE já
classifica), crédito "IRPJ a Recolher" (passivo) — lançamento criado via
`criar_lancamento`, dentro da competência do cálculo.

**Referência de rotina.** Manual, páginas 221-223 (janela Integração
Contábil: período, "Todos" vs. "Somente períodos não gerados", opção de
gerar pelo valor devido antes ou depois de deduções e incentivos).

**Fonte normativa.** Não se aplica ao mecanismo; débito = crédito é regra
de partida dobrada (regra geral, AGENTS.md).

**Situação no DataLedger.** **Não existe.**

**Depende de.** LAL-06, LAL-13 (compensações), LAL-21 (incentivos), CTB-02
(`criar_lancamento`), CTB-07 (competência/período encerrado).

**Dados.** Nenhum modelo novo além de marcar o `LancamentoContabil`
gerado para cada apuração.

**Regras.** Toda geração cria lançamento com débitos = créditos
(AGENTS.md); competência encerrada recusa nova integração sem reabertura
explícita; **"Regerar" só vale sobre lançamento ainda não efetivado** —
lançamento já efetivado se corrige por estorno, nunca por sobrescrita
(mesma regra geral já registrada em PAT-15); integração dupla do mesmo
período é recusada (idempotência).

**Telas e documentos.** Tela de integração — classe **conferência**.

**Critérios de aceite.** Rodar a integração duas vezes sobre a mesma
competência não duplica lançamento; lançamento gerado tem débitos e
créditos iguais; competência encerrada recusa integração sem reabertura.

**Não copiar/riscos.** Mesmo já registrado no mapa funcional: "Regerar"
que apaga e refaz lote só vale para rascunho no DataLedger.

**Perguntas.** O lançamento é gerado pelo valor bruto (antes de
deduções/incentivos) ou líquido — qual o padrão que o escritório do Fred
usa hoje?

### LAL-26 — Livro Lalur digital dentro da ECF

**O que é.** A entrega oficial de hoje: o Lalur não é mais um livro
avulso — é um **conjunto de blocos dentro da ECF** (Escrituração Contábil
Fiscal), que integra a apuração do IRPJ/CSLL à escrituração contábil
digital. Este item é o ponto de encontro final entre este plano e
[CTB-52](contabilidade.md#ctb-52--ecf-escrituração-contábil-fiscal-e-ajustes),
que já registra a dependência.

**Exemplo.** Bloco M da ECF de 2026, com os registros M010 (identificação
das contas da Parte B), M300/M305 (lançamentos das adições e exclusões),
M350 (Parte B) — **estrutura exata a confirmar no Manual de Orientação da
ECF vigente**, não inferida do manual do sistema de referência.

**Referência de rotina.** Todo este plano (LAL-01 a LAL-25) é, em
conjunto, a referência de rotina deste item — a ECF **consome** o que
todos os itens anteriores calculam.

**Fonte normativa.** **A confirmar** — **Manual de Orientação da ECF**,
publicado pela Receita Federal/Sped, com leiaute e regras de validação
próprias. **Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe** — **depende de CTB-51** (ECD,
pré-requisito da ECF) e **CTB-52** (ECF), nenhum dos dois existente.

**Depende de.** Todo este plano (LAL-01 a LAL-25), CTB-50, CTB-51,
CTB-52.

**Dados.** Depende inteiramente do leiaute oficial da ECF, a confirmar.

**Regras.** Geração recusada sem a base toda (ECD, plano de contas
referencial, apuração do Lalur completa); arquivo gerado é rastreável até
os lançamentos e cálculos de origem.

**Telas e documentos.** Classe **livro** (digital) — arquivo regulatório
com leiaute oficial, zero margem de personalização de conteúdo
obrigatório.

**Critérios de aceite.** A definir junto do plano de etapa, com validação
contra o validador oficial do Sped antes de qualquer entrega real.

**Não copiar/riscos.** Mesmo já registrado em CTB-52: o Lalur Parte B é
sub-livro que **não é partida dobrada** — generalizar `Conta` para
cobri-lo é erro (BL-398, já evitado pelo desenho de LAL-09/LAL-10).

**Perguntas.** O escritório do Fred transmite ECF hoje, para quais
clientes, e com qual periodicidade (a ECF é anual)?

## Fora de escopo ou dependente de confirmação

| Item | Motivo |
| --- | --- |
| LAL-17 a LAL-20 | Regime de estimativa e balanço de redução/suspensão dependem do Fiscal (acumuladores, FIS-07/FIS-23), inexistente; sem confirmação de uso real na carteira. |
| LAL-20 | Balanço de redução e suspensão é o regime mais complexo do módulo — não deve ser o primeiro a ser implementado. |
| LAL-21 | Cada incentivo fiscal tem legislação própria; nenhum entra em código sem confirmação item a item e sem confirmação de uso real na carteira. |
| LAL-22 | Lucro da exploração depende de incentivo regional (SUDAM/SUDENE), matéria específica sem levantamento normativo nesta sessão. |
| LAL-23 | SCP depende de confirmação de uso real na carteira. |
| LAL-24 | **Maior risco normativo do plano** junto de PAT-24: eventos societários e compensação de prejuízo fiscal têm restrição legal específica (Lei 9.532/1997) que precisa de validação profissional antes de qualquer código. |
| LAL-26 | Depende de CTB-51/CTB-52 (ECD/ECF), inexistentes; leiaute da ECF não conferido em fonte oficial. |

## Glossário

| Termo | Significado |
| --- | --- |
| **Lalur** | Livro de Apuração do Lucro Real — parte do cálculo do IRPJ/CSLL para empresas no regime de lucro real. |
| **Parte A** | A seção do Lalur com o cálculo do período: lucro contábil + adições − exclusões = lucro real (LAL-05 a LAL-08). |
| **Parte B** | O razão de controle fiscal (não partida dobrada) que acumula diferenças temporárias com saldo que atravessa exercícios (LAL-09/LAL-10) — ver aviso BL-398. |
| **Adição** | Valor somado ao lucro contábil por não ser dedutível fiscalmente (LAL-02). |
| **Exclusão** | Valor subtraído do lucro contábil por não ser tributável fiscalmente (LAL-03). |
| **Base negativa** | O prejuízo fiscal acumulado que compensa lucro de períodos futuros, com limite de 30% por período (LAL-11). |
| **Lucro real** | A base de cálculo do IRPJ/CSLL depois de adições e exclusões sobre o lucro contábil. |
| **Estimativa** | Regime de apuração mensal por percentual de presunção sobre a receita bruta, com ajuste anual (LAL-17/LAL-19). |
| **Balanço de redução e suspensão** | Variação da estimativa em que um balanço intermediário reduz ou suspende o pagamento mensal (LAL-20). |
| **SCP** | Sociedade em Conta de Participação — apurada separadamente do sócio ostensivo (LAL-23). |
| **Lucro da exploração** | Base específica para incentivo fiscal regional (SUDAM/SUDENE) (LAL-22). |
| **ECF** | Escrituração Contábil Fiscal — hoje o veículo de entrega oficial do Lalur (LAL-26, cruzado com CTB-52). |
| **Classe de documento** | Cadastro, conferência, demonstração, livro ou guia — de [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md). |

## Perguntas abertas consolidadas

1. **LAL-01** — Qual regime de apuração a carteira do Fred usa hoje, e há
   clientes com mais de um regime?
2. **LAL-02/LAL-03** — Há catálogo próprio de adições e exclusões já
   usado no sistema de referência que sirva de ponto de partida (sujeito
   a conferência)?
3. **LAL-04** — A separação operacional × não operacional deve ficar em
   tela própria do Lalur, ou dentro da estrutura da DRE?
4. **LAL-06** — Há cliente sujeito a adicional de IRPJ hoje? E
   instituição financeira, com alíquota diferenciada de CSLL?
5. **LAL-07** — O escritório ainda emite o Lalur "avulso", ou hoje é só o
   bloco da ECF que importa?
6. **LAL-10** — Qual o sinal exato da adição/exclusão de depreciação em
   cada situação (fiscal > societária vs. o inverso)?
7. **LAL-11** — Há cliente com prejuízo fiscal acumulado relevante hoje?
8. **LAL-13** — A carteira compensa IRPJ/CSLL com créditos próprios hoje?
9. **LAL-15** — O escritório usa alguma integração de pagamento (e-CAC,
   banco) que precise ser mapeada à parte?
10. **LAL-16** — Quais códigos de recolhimento a carteira usa hoje?
11. **LAL-17/LAL-18** — A carteira usa o regime de estimativa mensal? Para
    quais atividades?
12. **LAL-20 (central)** — Há cliente que usa balanço de redução e
    suspensão hoje?
13. **LAL-21** — Quais incentivos fiscais, exatamente, a carteira usa?
14. **LAL-22** — Há cliente com incentivo fiscal regional (SUDAM/SUDENE)?
15. **LAL-23** — Há cliente com SCP hoje?
16. **LAL-24 (risco normativo alto)** — Há cliente em cisão ou
    incorporação no curto prazo? A mecânica de proporcionalidade precisa
    de validação profissional antes de qualquer código.
17. **LAL-25** — O lançamento de provisão é gerado pelo valor bruto ou
    líquido de deduções/incentivos?
18. **LAL-26** — O escritório transmite ECF hoje, para quais clientes?
