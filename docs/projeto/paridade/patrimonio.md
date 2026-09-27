# Plano de paridade — Patrimônio

## Introdução

O módulo Patrimônio controla o **ativo imobilizado** do cliente do
escritório: o cadastro de cada bem (máquina, veículo, móvel, imóvel,
computador), o cálculo mensal da **depreciação** — fiscal (a que a Receita
Federal aceita como dedutível) e, quando o cliente exige, **societária**
(a que a norma contábil manda usar) —, a baixa do bem por venda ou perda,
sua transferência entre contas e locais, e a integração desses eventos com
a Contabilidade e com o Fiscal. No dia a dia do escritório, é o módulo que
garante que "Imobilizado, R$ 145.000,00" no Balanço tenha, por trás, uma
lista de bens que soma exatamente esse valor, com a depreciação acumulada
de cada um rastreável até a nota de compra.

**Escopo.** Este plano cobre a paridade funcional do Patrimônio com o
sistema de referência: cadastro do bem e da conta patrimonial, cálculo de
depreciação (fiscal e societária), ciclo do bem (baixa, transferência,
avaliação a valor justo), integração contábil e fiscal, e os relatórios e
documentos do módulo. Não cobre o Lalur (a diferença fiscal × societária de
depreciação e o ganho de capital **alimentam** o Lalur, mas a apuração do
IRPJ/CSLL é de [lalur.md](lalur.md)).

**Fontes.**

- **Rotina:** manual do sistema de referência entregue pelo Fred em
  2026-09-27 (Domínio Patrimônio, 389 páginas). Páginas citadas por item;
  o manual **não** entra no repositório
  ([fontes-de-referencia.md](../fontes-de-referencia.md)).
- **Norma:** cada item cita a fonte oficial a consultar antes de qualquer
  alíquota, taxa ou leiaute virar código. Nenhuma taxa de depreciação,
  percentual de crédito ou leiaute deste plano foi conferido em fonte
  primária nesta sessão — todos estão marcados **a confirmar**.
- **Inventário-base:**
  [mapa-funcional-patrimonio-lalur.md](../mapa-funcional-patrimonio-lalur.md),
  produzido na [DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md).

**Convenções.** Mesmo modelo de item do
[README.md](README.md#modelo-de-cada-item) deste diretório. IDs `PAT-NN`.
Classe de documento conforme
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md):
**cadastro**, **conferência**, **demonstração**, **livro** ou **guia**. As
regras gerais do [AGENTS.md](../../../AGENTS.md) — `Decimal`, efetivado
imutável, autorização no servidor, isolamento por empresa, trilha de
auditoria — valem em todo item deste plano, mesmo quando não repetidas.

**Estado atual: inexistente.** Não há cadastro de bem, de conta
patrimonial, de centro de custo, nem cálculo de depreciação em nenhum
lugar do código — confirmado em `apps/` (só existem `accounts`,
`auditoria`, `contabilidade`, `core`, `documentos`, `empresas`, `fiscal`,
`livro_caixa`, `tenancy`; não há `patrimonio` nem `lalur`).

## Mapa de dependências e ordem

O Patrimônio nasce **em cima** da Contabilidade que já existe
(`apps/contabilidade`: `Conta`, `LancamentoContabil`, `Competencia`,
`criar_lancamento`, `estornar_lancamento`, `apurar_saldos`,
`apurar_balanco_patrimonial`) e, mais adiante, do Fiscal (para CIAP e
créditos de PIS/COFINS). A cadeia, resumida:

```
PAT-01 Parâmetros da empresa
  └─> PAT-02 Cadastro do bem ──┬─> PAT-03 Parâmetros de depreciação do bem
                                ├─> PAT-04 Documento de origem
                                └─> PAT-06 Centro de custo do bem (opcional, RC-54)
  └─> PAT-05 Conta patrimonial (taxa fiscal por vigência + amarração contábil)
       └─> PAT-07 Cálculo periódico (depreciação fiscal)
            ├─> PAT-08 Relatório de depreciação fiscal
            ├─> PAT-09 Resumo da depreciação fiscal
            ├─> PAT-10 Ficha do bem
            ├─> PAT-11 Baixa (ganho/perda) ──> PAT-12 Relatório de baixas
            ├─> PAT-13 Transferências ──> PAT-14 Relatório de transferências
            ├─> PAT-15 Integração contábil ──> PAT-16 Acompanhamento patrimonial × Balanço
            ├─> PAT-17 Depreciação societária (Lei 12.973/2014)
            │     ├─> PAT-18 Resumo/acompanhamento societário
            │     ├─> PAT-19 Comparativo fiscal × societário e subcontas
            │     └─> PAT-20 Depreciação sobre custo atribuído
            ├─> PAT-24 Avaliação a valor justo e impairment (depende de PAT-17)
            └─> PAT-25 Razão auxiliar da ECD (depende da malha toda + CTB-50/51)
  └─> [depois do Fiscal] PAT-21 CIAP (parâmetros e cálculo)
       ├─> PAT-22 Ficha CIAP, termos e integração fiscal (crédito/débito ICMS)
       └─> PAT-23 Crédito de PIS/COFINS do imobilizado
  └─> PAT-26 Relatórios cadastrais (a qualquer momento, é listagem)
```

**Ondas**, como já recomendado em
[mapa-funcional-patrimonio-lalur.md](../mapa-funcional-patrimonio-lalur.md#ondas-recomendadas):

1. **Núcleo** — PAT-01 a PAT-10: bem, conta patrimonial com amarração
   contábil, depreciação fiscal linear por vigência, ficha do bem,
   relatório de depreciação. Depende só da Contabilidade que já existe.
2. **Ciclo do bem e integração contábil** — PAT-11 a PAT-16: baixa com
   ganho/perda, transferências, lançamentos ao Diário, acompanhamento
   conciliado com o Balanço. PAT-06 (centro de custo) é **opcional dentro
   desta onda**: só entra se o cliente usar centro de custo (RC-54,
   CTB-33 — que também não existe ainda).
3. **Critério societário e comparativo** — PAT-17 a PAT-20: depreciação
   pela norma contábil (NBC TG 27), o comparativo com a fiscal e as
   subcontas da Lei 12.973/2014, que é o que **alimenta o Lalur**
   (LAL-11, diferença temporária de depreciação).
4. **CIAP e créditos de PIS/COFINS** — PAT-21 a PAT-23: **depois** do
   Fiscal (depende de acumulador, imposto e apuração — FIS-07, FIS-08,
   FIS-23 — que também não existem) e da confirmação de quais UFs a
   carteira do escritório atende (o CIAP é regulado por legislação
   **estadual**, uma por UF).
5. **Valor justo e impairment** — PAT-24: reavaliação e perda por não
   recuperabilidade, avançado, poucos clientes usam.
6. **Razão auxiliar da ECD** — PAT-25: escrituração auxiliar do
   imobilizado dentro do SPED Contábil, junto da estratégia de ECD/ECF já
   registrada em CTB-50 a CTB-52.

**O que a base do Patrimônio destrava fora dele:** PAT-11 (baixa, com
ganho/perda de capital) e PAT-17/PAT-19 (diferença fiscal × societária)
são a fonte de duas adições/exclusões inteiras do Lalur — ver LAL-05 e
LAL-11 em [lalur.md](lalur.md).

## Onda 1 — Núcleo

### PAT-01 — Parâmetros da empresa no Patrimônio

**O que é.** A configuração, por empresa, de como o módulo se comporta:
máscara do código do bem, se o valor do ICMS e do PIS/COFINS é deduzido do
valor original do bem ao cadastrar, se a depreciação do mês de aquisição
ou baixa conta todos os dias do mês, a partir de quando existe cálculo
societário, e as opções gerais de geração de lançamento contábil (guia
Contabilidade) e de crédito de imposto (guia Impostos). É o mesmo papel
que `ParametroContabilEmpresa` já cumpre na Contabilidade, mas para este
módulo — parâmetro por **vigência**, nunca constante global.

**Exemplo.** Empresa "Metalúrgica Vale Ltda." parametrizada com: máscara
de código `#####`, "Deduzir valor do ICMS do valor original" **marcada**,
"Calcular a depreciação considerando todos os dias do mês" **marcada**,
"Calcular a depreciação societária a partir de" `01/2024`. Um veículo
comprado em 15/03/2024 por R$ 120.000,00 com ICMS de R$ 12.000,00
destacado na nota entra no cadastro com valor original de R$
108.000,00 (120.000,00 − 12.000,00), e a depreciação de março considera o
mês cheio, não os 17 dias restantes.

**Referência de rotina.** Manual, páginas 58-71 (guias Geral, Impostos —
ICMS, PIS e COFINS, Ganhos de Capital — e Contabilidade — Geral, Tipos de
Lançamentos, Impostos).

**Fonte normativa.** Não se aplica ao parâmetro em si (é configuração de
produto); os efeitos que ele liga (dedução de imposto do custo do bem,
Lei 12.973/2014 para subcontas) têm fonte própria nos itens que os usam.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01 (plano de contas, para as contas que os parâmetros
apontam), CTB-07 (competência).

**Dados.** Modelo novo: parâmetro do Patrimônio por empresa e por
**vigência** (mesmo padrão de `ParametroContabilEmpresa`, RC do módulo
contábil): máscara do código, dedução de ICMS/PIS-COFINS do valor
original, cálculo por dias corridos no mês de aquisição/baixa, data de
início do cálculo societário, dedução da depreciação fiscal acumulada da
base societária, geração de Razão Auxiliar da ECD (liga PAT-25), flag de
SCP.

**Regras.** Vigência sem sobreposição (mesmo padrão de FIS-07/FIS-08);
alteração de parâmetro não reprocessa competência encerrada sem ato
explícito; campo "início do cálculo societário" é **imutável depois do
primeiro cálculo societário rodado** (o manual documenta isso como regra
do próprio sistema de referência — página 59, "somente poderá ser alterado
se a empresa não possuir nenhum cálculo... realizado").

**Telas e documentos.** Tela de parâmetros — classe **cadastro**.

**Critérios de aceite.** Parâmetro por vigência sem sobreposição
(teste de referência análogo ao de FIS-07); mudança de parâmetro registra
quem mudou e quando (trilha de auditoria); dedução de ICMS/PIS-COFINS do
valor original é **aplicada na gravação do bem**, não recalculada depois
silenciosamente se o parâmetro mudar.

**Não copiar/riscos.** O manual permite "Deduzir valor do ICMS do valor
original" e, separadamente, o crédito de ICMS/PIS-COFINS calculado sobre
o **mesmo** bem (PAT-21, PAT-23) — as duas coisas juntas descontam o
imposto duas vezes se a regra de composição não for explícita. A
implementação precisa declarar, em teste, que o valor depreciável já
líquido de imposto não volta a ser base de novo desconto de imposto.

**Perguntas.** A carteira do Fred tem cliente que deduz ICMS/PIS-COFINS do
valor original do bem, ou todos mantêm o bem pelo valor cheio da nota?

### PAT-02 — Cadastro do bem

**O que é.** O registro de cada item do ativo imobilizado: identificação,
tipo (bem adquirido, bem transferido, componente de bem em construção),
classificação (individual ou resultante de um processo produtivo), conta
patrimonial e centro de custo a que pertence, e se é um componente
vinculado a outro bem (para imobilizado em andamento que vira bem
concluído).

**Exemplo.** Bem código `00123`, "Caminhão Volvo FH 540, placa ABC-1234",
tipo "Bem adquirido", classificação "Bem individual", conta patrimonial
"Veículos", data de aquisição 15/03/2024, valor de aquisição
R$ 120.000,00.

**Referência de rotina.** Manual, páginas 84-86 (guia Geral do cadastro do
bem: código, identificador, nome, data de aquisição, conta patrimonial,
centro de custo, tipo, classificação, vínculo a outro bem).

**Fonte normativa.** Não há leiaute oficial para o cadastro em si; a
classificação contábil do bem (o que é "imobilizado") segue a **Lei
6.404/1976, art. 178, §1º, II** e a **NBC TG 27** (Ativo Imobilizado), já
referenciadas em `ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO`
na Contabilidade.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-01, PAT-05 (conta patrimonial), CTB-33 (centro de
custo, opcional — PAT-06).

**Dados.** Modelo novo `Bem`: empresa, código, identificador (alfanumérico
livre), nome, data de aquisição, conta patrimonial (FK), centro de custo
(FK, opcional), tipo (`bem_adquirido`, `bem_transferido`,
`componente_adquirido`, `componente_transferido`), classificação
(`bem_individual`, `bem_resultante`, e — só para componente —
`imobilizado_em_andamento`/`imobilizado_concluido`), vínculo a outro bem
(FK opcional, auto-relacionamento), valor de aquisição, histórico
(texto livre de anotação, distinto do histórico contábil).

**Regras.** Isolamento por empresa; `Decimal` para todo valor monetário e
para taxa/percentual; bem com componente vinculado só pode apontar para
outro bem **da mesma empresa**; código único por empresa (o manual gera
sequencial automático, alterável).

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** Bem gravado com conta patrimonial obrigatória;
recusa vínculo a bem de outra empresa (teste de isolamento); recusa
gravação sem conta patrimonial válida na vigência da data de aquisição.

**Não copiar/riscos.** O botão "Multiplicar..." do manual (duplicar um
cadastro N vezes gerando códigos sequenciais) é utilidade de digitação —
pode ser adotado como atalho de tela, mas **cada bem multiplicado é uma
linha própria e independente** desde a criação, nunca um "grupo" que
compartilha estado.

**Perguntas.** O escritório do Fred cadastra bem por bem, ou importa de
planilha/nota fiscal? Se houver importação, ela precisa da mesma guarda de
duplicidade das demais importações do produto (AGENTS.md, regra de
domínio "importação repetida não duplica").

### PAT-03 — Parâmetros de depreciação do bem

**O que é.** Os dados, por bem, que controlam se ele deprecia, com que
taxa (a da conta patrimonial, ou uma taxa alternativa só dele), a partir
de quando, e — para bem que já vinha sendo usado antes de entrar no
sistema — a depreciação acumulada informada manualmente.

**Exemplo.** Caminhão do PAT-02: "Deprecia" = Sim, taxa alternativa em
branco (usa a taxa da conta patrimonial "Veículos" — 20% a.a., **a
confirmar na IN RFB 1.700/2017**), data de início 15/03/2024, sem
depreciação acumulada informada (bem novo).

**Referência de rotina.** Manual, páginas 96-100 (guia
Cálculo/Depreciação: Deprecia, Depreciar 100% no mês de início, Taxa
alternativa, Data de início, Informar depreciação acumulada até).

**Fonte normativa.** **A confirmar** — taxas de depreciação fiscal: **IN
RFB 1.700/2017, Anexo III**, e atualizações; o manual traz uma tabela de
taxas históricas (móveis e utensílios 10% a.a., veículos 20% a.a.,
edificações 4% a.a.) que **não deve entrar em código sem conferência na
IN vigente**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-05 (taxa da conta patrimonial, usada quando
não há taxa alternativa).

**Dados.** Campos do `Bem`: deprecia (booleano), taxa alternativa
(`Decimal`, opcional), data de início do cálculo fiscal, depreciação fiscal
acumulada informada (valor e data-limite, para bem que entra no sistema já
em uso), dados equivalentes para o cálculo societário (ligados a PAT-17).

**Regras.** Bem com `deprecia = Não` nunca gera linha de depreciação;
depreciação acumulada informada **não pode exceder** o valor depreciável
do bem (valor de aquisição menos valor residual); taxa alternativa, se
preenchida, prevalece sobre a taxa da conta patrimonial **só para aquele
bem**, sem alterar a taxa da conta.

**Telas e documentos.** Parte da tela de cadastro do bem — classe
**cadastro**.

**Critérios de aceite.** Bem sem taxa alternativa usa a taxa vigente da
conta patrimonial na competência do cálculo (nunca a taxa atual, se a
competência calculada for anterior a uma mudança de taxa); depreciação
acumulada informada maior que o depreciável é recusada.

**Não copiar/riscos.** Nenhum específico além dos já registrados no
AGENTS.md.

**Perguntas.** Nenhuma além da já registrada em PAT-08 sobre a taxa
oficial.

### PAT-04 — Documento de origem do bem

**O que é.** O vínculo do bem à nota fiscal (ou conhecimento de transporte)
de aquisição, para rastrear de onde ele veio.

**Exemplo.** Caminhão do PAT-02 vinculado à NF-e nº 45123, série 1, chave
de 44 dígitos, fornecedor "Volvo Caminhões do Brasil Ltda.".

**Referência de rotina.** Manual, páginas 100-102 (guia Documentos
Fiscais: número, série, data de emissão, espécie, chave da NF-e/CT-e,
fornecedor, produto).

**Fonte normativa.** Não se aplica — é vínculo interno de rastreabilidade,
sem leiaute próprio.

**Situação no DataLedger.** **Não existe** — depende também de FIS-36
(lançamento de nota de entrada), que também não existe.

**Depende de.** PAT-02, FIS-36 (nota de entrada, quando o bem vier de uma
nota já lançada no Fiscal).

**Dados.** Modelo novo (ou campo do `Bem`): número, série, data de
emissão, espécie do documento, chave de acesso (NF-e/CT-e), fornecedor,
produto/item, vínculo opcional ao lançamento fiscal de origem (FIS-36).

**Regras.** Se vinculado a um lançamento fiscal existente, os dados vêm
**dele**, não são redigitados; alteração manual depois do vínculo é
trilhada.

**Telas e documentos.** Parte da tela de cadastro do bem — classe
**cadastro**.

**Critérios de aceite.** Bem vinculado a uma nota já lançada no Fiscal
preenche os campos automaticamente e sem duplicidade.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além da ordem de implementação (este item é
naturalmente posterior a FIS-36, mas pode nascer com preenchimento manual
antes disso, sem o vínculo automático).

### PAT-05 — Conta patrimonial com amarração contábil e taxa por vigência

**O que é.** O agrupamento de bens com a mesma natureza (ex.: "Veículos",
"Máquinas e Equipamentos", "Móveis e Utensílios"), que carrega a **taxa de
depreciação fiscal por vigência** (pode mudar ao longo do tempo, sem
afetar o passado) e a **amarração** com as contas contábeis de
aquisição, depreciação acumulada, depreciação do período, avaliação e
baixa — é o que faz o cálculo do bem virar lançamento na Contabilidade sem
o contador escolher conta a cada evento.

**Exemplo.** Conta patrimonial "Veículos", natureza devedora, taxa de
depreciação fiscal 20,00% a.a. (**a confirmar na IN RFB 1.700/2017**)
vigente desde 01/2020; amarração: aquisição → débito "1.2.3.01 Veículos",
crédito "1.1.1.01 Caixa"; depreciação do período → débito "4.1.2.05
Depreciação — Veículos" (despesa), crédito "1.2.3.02 (-) Depreciação
Acumulada — Veículos" (retificadora, credora, dentro do grupo Imobilizado
— mesmo padrão de **RC-61**).

**Referência de rotina.** Manual, páginas 108-118 (guia Geral: taxa e
taxas variáveis por vigência; guia Contabilidade: Geral, Depreciação,
Avaliação, Baixa, Crédito de ICMS).

**Fonte normativa.** **A confirmar** — taxa: IN RFB 1.700/2017, Anexo III.
A retificadora "(-) Depreciação Acumulada" dentro do grupo Imobilizado é
prática já confirmada no produto por **RC-61**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01 (as contas contábeis que a amarração aponta), CTB-07
(vigência por competência).

**Dados.** Modelo novo `ContaPatrimonial`: empresa, código, descrição,
natureza (devedora/credora), taxa de depreciação fiscal por **vigência**
(tabela `TaxaDepreciacaoPorVigencia`: conta patrimonial, data de início,
percentual), amarração contábil (contas de aquisição/caixa, depreciação
acumulada, depreciação do período, subconta Lei 12.973/2014 quando
houver diferença fiscal × societária, avaliação — ganho e perda —, baixa —
caixa, receita de alienação, custo de alienação —, crédito de ICMS curto e
longo prazo), cada uma com histórico contábil padrão vinculado (mesmo
padrão de FIS-09).

**Regras.** Taxa por vigência sem sobreposição, mesmo padrão de
FIS-07/FIS-08; taxa alterada não reprocessa depreciação de competência já
calculada e encerrada, sem ato explícito; conta de depreciação acumulada é
sempre **retificadora dentro do mesmo grupo** do ativo (RC-61) —
guarda equivalente à de `Conta.clean()` na Contabilidade.

**Telas e documentos.** Tela de cadastro — classe **cadastro**.

**Critérios de aceite.** Cálculo de depreciação de uma competência usa a
taxa vigente **naquela** competência, nunca a taxa atual; teste de
referência com duas vigências de taxa provando que o valor calculado
difere corretamente entre os dois períodos.

**Não copiar/riscos.** Nenhum além dos já gerais de amarração contábil
(mesma cautela que FIS-09 já registra para histórico com variáveis).

**Perguntas.** Nenhuma além da confirmação normativa da taxa (item
PAT-08).

### PAT-06 — Centro de custo do bem e integração por centro de custo

**O que é.** Uma segunda classificação do bem (além da conta patrimonial):
o departamento ou filial ao qual ele pertence, usada para que a
contabilização do Patrimônio saia **por centro de custo**, quando o
cliente usa essa dimensão.

**Exemplo.** Caminhão do PAT-02 no centro de custo "Frota — Filial Zona
Sul"; a depreciação de março gera lançamento debitando "Depreciação —
Veículos" **rateado** para o centro de custo "Frota — Filial Zona Sul",
em vez de um lançamento único sem dimensão.

**Referência de rotina.** Manual, páginas 119-124.

**Fonte normativa.** Não se aplica — dimensão gerencial, sem leiaute
oficial (mesma conclusão de **CTB-33**).

**Situação no DataLedger.** **Não existe** — e **depende de CTB-33**
(centro de custo e departamento), que também não existe no DataLedger.

**Depende de.** PAT-02, PAT-15 (integração contábil), CTB-33.

**Dados.** Campo `centro_de_custo` (FK opcional) no `Bem`; parâmetro em
PAT-01 que decide se a contabilização usa a conta patrimonial ou o rateio
por centro de custo (mutuamente exclusivos, conforme o manual: "a opção
Gerar lançamentos por centros de custos conforme informado no cadastro do
bem somente estará habilitada... quando a opção Gerar lançamentos
contábeis dos valores de transferência de conta patrimonial não estiver
selecionada").

**Regras.** Isolamento entre empresas (mesma regra de CTB-33); item
**bloqueado** até CTB-33 existir — não faz sentido implementar antes.

**Telas e documentos.** Campo dentro da tela de cadastro do bem — classe
**cadastro**.

**Critérios de aceite.** A definir junto de CTB-33 e desta etapa.

**Não copiar/riscos.** Nenhum.

**Perguntas.** A carteira do Fred usa centro de custo (RC-54, ainda em
aberto na Contabilidade)? Se a resposta for não, este item fica adiado
sem prejuízo do resto do módulo.

### PAT-07 — Cálculo periódico da depreciação fiscal

**O que é.** O motor que, para uma competência (ou faixa de
competências), calcula a depreciação **fiscal** de todos os bens
depreciáveis da empresa — o coração do módulo.

**Exemplo.** Caminhão de R$ 120.000,00 (já líquido de ICMS, PAT-01),
depreciação fiscal linear a 20,00% a.a. (**a confirmar**) = 1,6667% a.m.
Depreciação de março/2024 (mês de aquisição, dia cheio por parâmetro):
R$ 120.000,00 × 1,6667% = **R$ 2.000,04**. Em fevereiro/2025 (12º mês), a
depreciação acumulada soma **R$ 24.000,48**; em março/2029 (61 meses),
a depreciação acumulada atinge o valor depreciável e o cálculo **para**
(não deprecia além de 100% do valor depreciável).

**Referência de rotina.** Manual, páginas 209-220 (menu Processos,
"Calcular": competência inicial/final, seleção de empresas, SCP e bens,
janela de resultado com saldo e base por bem).

**Fonte normativa.** **A confirmar** — método linear e taxas: IN RFB
1.700/2017, Anexo III; a fórmula "valor depreciável ÷ vida útil" em si é
prática consolidada (RIR/2018).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-03, PAT-05.

**Dados.** Resultado por bem e competência: base de cálculo, taxa
aplicada, valor da depreciação do período, depreciação acumulada — tudo
com **memória de cálculo** rastreável (AGENTS.md, regra de auditoria).

**Regras.** Cálculo **determinístico e reprodutível** (rodar duas vezes
sobre os mesmos dados dá o mesmo resultado, byte a byte, mesmo padrão de
FIS-23); `Decimal` com escala e arredondamento explícitos (nunca ponto
flutuante binário); depreciação nunca ultrapassa o valor depreciável;
competência encerrada exige reabertura explícita para recalcular
(mesma trava de CTB-07); "Todos" vs. "Somente períodos não gerados" do
manual é aceitável **só para rascunho** — recálculo que sobrescreveria
depreciação já integrada à Contabilidade (lançamento efetivado) é
regeração proibida (ver PAT-15).

**Telas e documentos.** Tela de cálculo — classe **conferência** (o
resultado bruto do cálculo é conferência; o relatório formatado é
PAT-08/PAT-09).

**Critérios de aceite.** Depreciação de um bem, recalculada duas vezes
sobre os mesmos dados de entrada, produz o mesmo valor centavo a centavo;
bem com `deprecia = Não` nunca aparece no resultado; depreciação
acumulada nunca excede o valor depreciável (teste de limite).

**Não copiar/riscos.** Não inventar taxa nem regra de arredondamento sem
confirmação (AGENTS.md).

**Perguntas.** Qual é a **taxa oficial vigente** para os bens mais comuns
da carteira (veículos, máquinas, móveis, computadores) — precisa de
conferência na IN RFB 1.700/2017 antes do primeiro caso de referência.

## Onda 1 (continuação) — Relatórios de depreciação fiscal

### PAT-08 — Relatório de depreciação fiscal

**O que é.** A memória de cálculo impressa, bem a bem, da depreciação
fiscal do período: base, taxa, valor do período e acumulada.

**Exemplo.** Ver PAT-07. O relatório de março/2024 mostra, para o
caminhão: base R$ 120.000,00; taxa 1,6667% a.m.; depreciação do mês
R$ 2.000,04; acumulada R$ 2.000,04.

**Referência de rotina.** Manual, páginas 254-256.

**Fonte normativa.** Não se aplica ao relatório em si; os valores vêm de
PAT-07.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-07.

**Dados.** Nenhum além do resultado de PAT-07, formatado.

**Regras.** O relatório reproduz **exatamente** o resultado do cálculo —
nunca recalcula com regra diferente da que gerou o número gravado; período
encerrado emite sempre o mesmo valor (imutabilidade do efetivado).

**Telas e documentos.** Relatório — classe **conferência** (se numerado e
com termo, pode virar **livro**, caso o escritório o use para esse fim —
a confirmar com o Fred).

**Critérios de aceite.** Soma das linhas do relatório bate com o total
apurado por PAT-07 para a mesma competência e empresa.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além das já registradas em PAT-07.

### PAT-09 — Resumo da depreciação fiscal

**O que é.** A versão sintética do PAT-08: um total por conta patrimonial,
sem o detalhe bem a bem — o que o contador usa para conferir o total antes
de olhar o detalhe.

**Exemplo.** Conta patrimonial "Veículos": depreciação do período
R$ 8.400,00 (soma de 4 bens); "Máquinas e Equipamentos": R$ 3.200,00.

**Referência de rotina.** Manual, páginas 261-263.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-07, PAT-05.

**Dados.** Agregação de PAT-08 por conta patrimonial.

**Regras.** Soma do resumo bate exatamente com a soma do detalhe (PAT-08)
para a mesma competência.

**Telas e documentos.** Relatório — classe **conferência**.

**Critérios de aceite.** Teste de reconciliação: resumo por conta
patrimonial = soma dos bens daquela conta no relatório detalhado.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

### PAT-10 — Ficha do bem

**O que é.** O histórico individual e completo de um bem: aquisição,
todas as depreciações mês a mês, avaliações, transferências e baixa —
o "extrato" do bem, equivalente ao Razão de uma conta contábil.

**Exemplo.** Ficha do caminhão do PAT-02, de 03/2024 a 12/2024: linha de
aquisição (R$ 120.000,00), 10 linhas de depreciação mensal (R$ 2.000,04
cada), saldo em 12/2024 (custo R$ 120.000,00, depreciação acumulada
R$ 20.000,40, valor contábil R$ 99.999,60).

**Referência de rotina.** Manual, páginas 263-265.

**Fonte normativa.** Não se aplica ao relatório; os eventos que ele lista
vêm de cada item próprio (PAT-07, PAT-11, PAT-13, PAT-24).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-07, PAT-11, PAT-13, PAT-24.

**Dados.** Agregação cronológica dos eventos do bem.

**Regras.** Ordem cronológica; nenhum evento pode ser omitido (a ficha
tem de bater com a soma dos relatórios individuais de cada tipo de
evento).

**Telas e documentos.** Relatório — classe **conferência**.

**Critérios de aceite.** Saldo final da ficha (custo − depreciação
acumulada ± ajustes) bate com o valor contábil do bem calculado
independentemente.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

## Onda 2 — Ciclo do bem e integração contábil

### PAT-11 — Baixa total ou parcial, com ganho ou perda de capital

**O que é.** O registro de que um bem saiu do patrimônio — por venda,
perda, doação, sinistro — total (o bem inteiro) ou parcial (por valor ou
por quantidade, para bens cadastrados em lote), com o cálculo automático
do **ganho ou perda de capital**: valor de venda menos valor contábil
(custo menos depreciação acumulada).

**Exemplo.** O caminhão do PAT-02, com depreciação fiscal acumulada de
R$ 40.000,08 em 12/2025 (valor contábil R$ 79.999,92), é vendido por
**R$ 70.000,00** em 15/12/2025. **Ganho/perda de capital = 70.000,00 −
79.999,92 = − R$ 9.999,92 (perda)**. Se tivesse sido vendido por
R$ 90.000,00, o resultado seria **+ R$ 10.000,08 (ganho)**.

**Referência de rotina.** Manual, páginas 224-231 (janela Baixas: tipo
total/parcial, posição do bem antes da baixa, dados da baixa, documento
fiscal de saída, guia Contabilidade).

**Fonte normativa.** O ganho/perda de capital na alienação de bem do
ativo não circulante é fato gerador de adição ao lucro real (ver LAL-05,
Lalur) — **RIR/2018** e **Decreto-Lei 1.598/1977**, a confirmar.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-07 (depreciação acumulada até a data da
baixa), PAT-05 (contas de caixa, receita e custo de alienação).

**Dados.** Modelo novo `BaixaDeBem`: bem, data, tipo (total/parcial),
critério de baixa parcial (valor ou quantidade), valor de venda, valor
contábil na data (calculado), ganho/perda de capital (calculado),
histórico, documento fiscal de saída vinculado (opcional).

**Regras.** Ganho/perda = valor de venda − valor contábil (nunca
recalculado com fórmula diferente entre telas); baixa não pode exceder o
saldo disponível do bem (quantidade ou valor); baixa de bem já totalmente
baixado é recusada; **uma única baixa por bem e competência**, salvo tipo
de baixa diferente da primeira (regra do próprio manual, página 227,
adotada como regra de negócio, não só de UI); baixa em lote/lançamento
gera débito e crédito que fecham (débitos = créditos, mesmo em lote de
vários bens).

**Telas e documentos.** Tela de baixa — classe **conferência**, com
lançamento contábil associado (PAT-15).

**Critérios de aceite.** Teste de referência com o exemplo acima (perda de
R$ 9.999,92) provando o cálculo exato em `Decimal`; baixa que excede o
saldo do bem é recusada; baixa efetivada é imutável (correção só por
estorno rastreável, mesmo padrão de `estornar_lancamento`).

**Não copiar/riscos.** Nenhum copiado; a regra "não é possível mais de uma
baixa do mesmo bem na mesma competência com tipo diferente" é do sistema
de referência e **precisa de decisão própria** se o DataLedger vai
replicá-la ou permitir múltiplas baixas parciais no mesmo mês — marcado
como pergunta.

**Perguntas.** O DataLedger deve permitir mais de uma baixa parcial do
mesmo bem na mesma competência (o manual restringe isso)? Decisão de
produto, não normativa.

### PAT-12 — Relatório de baixas

**O que é.** A listagem dos bens baixados no período, com o ganho ou
perda apurado em cada um.

**Exemplo.** Relatório de dezembro/2025: caminhão, baixa total,
15/12/2025, valor de venda R$ 70.000,00, valor contábil R$ 79.999,92,
perda de R$ 9.999,92.

**Referência de rotina.** Manual, páginas 269-271.

**Fonte normativa.** Não se aplica ao relatório; a fonte do ganho/perda é
a de PAT-11.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-11.

**Dados.** Agregação de PAT-11 por competência.

**Regras.** Soma do relatório bate com a soma dos lançamentos de baixa do
período; período encerrado é imutável.

**Telas e documentos.** Relatório — classe **conferência**.

**Critérios de aceite.** Teste de reconciliação entre o relatório e as
baixas gravadas na competência.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

### PAT-13 — Transferências (conta patrimonial, centro de custo, matriz/filial)

**O que é.** A movimentação de um bem entre classificações — troca de
conta patrimonial, de centro de custo, ou entre empresas do grupo
(matriz e filiais) — preservando o histórico de depreciação já
acumulado.

**Exemplo.** O caminhão do PAT-02 é transferido, em 01/2026, da conta
patrimonial "Veículos" para "Veículos — Frota Pesada" (reclassificação
interna, sem mudar valor nem depreciação acumulada).

**Referência de rotina.** Manual, páginas 231-241 (transferência de conta
patrimonial, de centro de custo, e entre matriz/filiais, cada uma com sua
guia Contabilidade).

**Fonte normativa.** Não se aplica ao evento em si; quando a transferência
é entre empresas (matriz/filial) e envolve crédito de ICMS remanescente,
a fonte é a mesma de PAT-21/PAT-22 (legislação estadual do CIAP).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-05, PAT-06 (centro de custo, se aplicável).

**Dados.** Modelo novo `TransferenciaDeBem`: bem, data, tipo (conta
patrimonial / centro de custo / matriz-filial), origem, destino,
histórico; para matriz/filial: empresa destino e regra de transferência
(ou não) do crédito de ICMS remanescente.

**Regras.** Transferência **não** altera valor de aquisição nem
depreciação acumulada do bem — só a classificação; transferência entre
empresas preserva isolamento (cada lado vê seu próprio lançamento, nunca
um lançamento cruzado sem os dois lados registrados).

**Telas e documentos.** Tela de transferência — classe **conferência**,
com lançamento contábil associado quando parametrizado (PAT-15).

**Critérios de aceite.** Transferência não altera a depreciação acumulada
do bem (teste de regressão); transferência entre empresas gera registro
em ambas, sem duplicar nem perder o bem.

**Não copiar/riscos.** Transferência entre matriz e filiais do sistema de
referência **processa várias empresas de uma vez** — no DataLedger, a
autorização é conferida **empresa por empresa no servidor**, nunca pela
seleção da tela (regra geral já registrada no mapa funcional).

**Perguntas.** A carteira do Fred tem clientes com matriz e filiais que
transferem bens entre si?

### PAT-14 — Relatório de transferências

**O que é.** A listagem das transferências do bem (ou de todos os bens no
período), mostrando de onde e para onde cada um foi.

**Exemplo.** Relatório de janeiro/2026: caminhão, transferido de
"Veículos" para "Veículos — Frota Pesada" em 01/01/2026.

**Referência de rotina.** Manual, páginas 271-275.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-13.

**Dados.** Agregação de PAT-13.

**Regras.** Mesma imutabilidade de período encerrado das demais listas.

**Telas e documentos.** Relatório — classe **conferência**.

**Critérios de aceite.** Teste de reconciliação com as transferências
gravadas na competência.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

### PAT-15 — Integração contábil

**O que é.** A geração, para a Contabilidade, dos lançamentos de
aquisição, depreciação, baixa e transferência do período — o ponto em que
o Patrimônio deixa de ser um controle isolado e vira Diário e Razão.

**Exemplo.** Março/2024: débito "Depreciação — Veículos" (despesa) R$
2.000,04, crédito "(-) Depreciação Acumulada — Veículos" R$ 2.000,04 —
lançamento criado via `criar_lancamento`, dentro da competência 03/2024,
com débitos = créditos.

**Referência de rotina.** Manual, páginas 246-248 (janela Integração
Contábil: competência, "Todos" vs. "Somente períodos não gerados",
prévia dos lançamentos antes de gravar).

**Fonte normativa.** Não se aplica ao mecanismo; o **débito = crédito** de
cada lançamento é regra de partida dobrada (regra geral de domínio,
AGENTS.md).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-07, PAT-11, PAT-13, PAT-05 (amarração contábil),
CTB-02 (`criar_lancamento`), CTB-07 (competência/período encerrado).

**Dados.** Nenhum modelo novo além de marcar, em cada evento (depreciação,
baixa, transferência), o `LancamentoContabil` gerado (relação 1:1 ou
1:N conforme granularidade escolhida — por bem ou por competência,
espelhando a opção do manual "Crédito PIS e COFINS: Por bem / Por
competência", ver PAT-23).

**Regras.** Toda geração cria lançamento com débitos = créditos
(AGENTS.md); competência encerrada recusa nova integração sem reabertura
explícita (CTB-07); **"Regerar" do manual só vale sobre lançamento ainda
não efetivado** — lançamento já efetivado se corrige por **estorno**
(`estornar_lancamento`), nunca por sobrescrita (regra geral do mapa
funcional, "o que não copiar"); integração dupla do mesmo evento é
recusada (idempotência — mesma classe de proteção que FIS-19 usa para a
integração fiscal).

**Telas e documentos.** Tela de integração — classe **conferência**.

**Critérios de aceite.** Rodar a integração duas vezes sobre a mesma
competência não duplica lançamento; lançamento gerado tem débitos e
créditos iguais (mesmo padrão de `criar_lancamento`); competência
encerrada recusa integração sem reabertura.

**Não copiar/riscos.** **Já registrado no mapa funcional:** o
"Regerar" do sistema de referência apaga e refaz lote — no DataLedger
isso só vale para rascunho.

**Perguntas.** A granularidade do lançamento (por bem, por conta
patrimonial, ou um lançamento único por competência) — qual o escritório
do Fred prefere para não poluir o Diário?

### PAT-16 — Acompanhamento patrimonial, conciliado com o Balanço

**O que é.** O relatório que mostra, por conta patrimonial e por
competência, o custo, a depreciação acumulada e o saldo (valor contábil)
ao longo do tempo — o relatório que **precisa bater** com o grupo
Imobilizado do Balanço Patrimonial.

**Exemplo.** Conta patrimonial "Veículos", em 12/2024: custo
R$ 480.000,00 (4 veículos), depreciação acumulada R$ 96.001,92, saldo
R$ 383.998,08 — que precisa ser **exatamente** o valor que aparece no
grupo "Ativo não circulante — imobilizado" do Balanço da mesma empresa e
competência (`apurar_balanco_patrimonial`).

**Referência de rotina.** Manual, páginas 265-267 (Acompanhamento
Patrimonial Fiscal e Societário: competência, detalhamento por
competência, detalhamento por grupo contábil).

**Fonte normativa.** A conciliação entre relatório auxiliar e Balanço é
regra geral do domínio (AGENTS.md: "relatórios e saldos conciliáveis com
os lançamentos de origem").

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-15 (os lançamentos já integrados), CTB-09 (Balanço
Patrimonial), `ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO`.

**Dados.** Agregação de custo, depreciação acumulada e saldo por conta
patrimonial e competência.

**Regras.** O saldo do acompanhamento **bate exatamente** com o saldo da
conta contábil correspondente no Balanço da mesma competência — teste de
reconciliação obrigatório (mesma exigência que já vale para o Razão × o
Balancete na Contabilidade).

**Telas e documentos.** Relatório — classe **demonstração de apoio**
(não é a demonstração oficial, mas sustenta a conferência dela).

**Critérios de aceite.** Diferença entre o acompanhamento patrimonial e o
saldo do Balanço para a mesma conta e competência é **sempre zero**;
teste de regressão cobrindo pelo menos uma conta patrimonial com bem
adquirido, depreciado e baixado no mesmo período.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

## Onda 3 — Critério societário e comparativo (Lei 12.973/2014)

### PAT-17 — Depreciação societária

**O que é.** O cálculo da depreciação pelo critério **contábil** (NBC TG
27: vida útil econômica real do bem, valor residual, revisão periódica),
que pode divergir da depreciação **fiscal** (taxa fixa da Receita
Federal). Só se aplica a partir da data que o parâmetro PAT-01 define.

**Exemplo.** O mesmo caminhão de R$ 120.000,00: pela fiscal, 20% a.a.
(5 anos de vida útil "fiscal"); pela societária, o contador estima a
vida útil real em **8 anos**, com valor residual de R$ 20.000,00 —
depreciação societária mensal = (120.000,00 − 20.000,00) ÷ 96 meses =
**R$ 1.041,67**, contra R$ 2.000,04 pela fiscal. A diferença mensal de
R$ 958,37 é o que alimenta a comparação de PAT-19 e, no Lalur, a adição
temporária (LAL-11).

**Referência de rotina.** Manual, páginas 96-100 (guia Cálculo/Depreciação,
quadro Societária: data de início, taxa inicial, depreciação acumulada) e
97-98 (valor residual e base de cálculo da depreciação societária).

**Fonte normativa.** **A confirmar** — **NBC TG 27** (Ativo Imobilizado,
CFC): vida útil econômica, valor residual, depreciação pelo método que
melhor reflita o padrão de consumo dos benefícios econômicos. **NBC TG
01** para redução ao valor recuperável (relacionado a PAT-24).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-03, PAT-05, PAT-01 (data de início do cálculo
societário).

**Dados.** Campos adicionais do `Bem`: valor residual, vida útil
econômica (ou taxa societária equivalente), data de início do cálculo
societário, depreciação societária acumulada informada (para bem que já
existia antes da adoção do critério societário).

**Regras.** Base de cálculo societária = valor original + correção
monetária acumulada − valor residual (fórmula do manual, adotada como
regra de negócio); depreciação societária nunca excede a base calculada
dessa forma; mudança de estimativa de vida útil é **prospectiva**, nunca
retroativa (prática consolidada da NBC TG 27 — a confirmar o item exato).

**Telas e documentos.** Parte da tela de cadastro do bem (dados) e tela de
cálculo (resultado) — classe **cadastro** e **conferência**.

**Critérios de aceite.** Teste de referência com o exemplo acima (R$
1.041,67 mensal) provando o cálculo exato em `Decimal`; depreciação
societária nunca gerada para bem sem "cálculo societário a partir de"
definido em PAT-01.

**Não copiar/riscos.** Nenhum além dos já gerais.

**Perguntas.** A carteira do Fred tem clientes obrigados a demonstração
contábil "cheia" (grande porte, ou que apresentam a terceiros — banco,
sócio) que precisem de depreciação societária divergente da fiscal, ou
todos usam a mesma taxa nas duas colunas?

### PAT-18 — Resumo e acompanhamento da depreciação societária

**O que é.** Os equivalentes societários de PAT-09 (resumo por conta) e
PAT-16 (acompanhamento conciliado), mas pelo critério contábil.

**Exemplo.** Ver PAT-09/PAT-16, com os valores da depreciação societária
em vez da fiscal.

**Referência de rotina.** Manual, páginas 262-263 (resumo) e 266-267
(acompanhamento societário).

**Fonte normativa.** Mesma de PAT-17.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-17, PAT-09, PAT-16.

**Dados.** Mesma estrutura de PAT-09/PAT-16, filtrada pelo critério
societário.

**Regras.** Mesmas de PAT-09/PAT-16.

**Telas e documentos.** Relatórios — classe **conferência** e
**demonstração de apoio**.

**Critérios de aceite.** Mesmos de PAT-09/PAT-16, aplicados ao critério
societário.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma além das já registradas em PAT-17.

### PAT-19 — Comparativo fiscal × societário e subcontas da Lei 12.973/2014

**O que é.** O relatório que mostra, lado a lado, a depreciação fiscal e a
societária de cada bem, com a **diferença** — que é exatamente o dado que
alimenta o ajuste do Lalur (LAL-11) — e, quando o parâmetro está ligado, o
lançamento contábil da diferença em **subcontas** específicas, conforme a
Lei 12.973/2014 (regime que "neutraliza" na apuração do IRPJ/CSLL os
efeitos contábeis que a lei fiscal não reconhece).

**Exemplo.** Março/2024, caminhão: depreciação fiscal R$ 2.000,04,
depreciação societária R$ 1.041,67, **diferença R$ 958,37** — lançada,
quando parametrizado, em subconta "(-) Depreciação Acumulada — Veículos
— Subconta Lei 12.973" (crédito), com contrapartida na despesa
correspondente. Essa diferença é o valor que, se a depreciação
**fiscal** for a dedutível, vira **exclusão** no Lalur (porque a fiscal é
maior que a societária, e é ela que reduz a base — mecânica exata a
confirmar caso a caso, conforme LAL-11).

**Referência de rotina.** Manual, páginas 259-261 (relatório
Comparativo) e 68 (parâmetro "Gerar lançamentos em subcontas conforme Lei
nº 12.973/2014") e 112-115 (amarração das subcontas na conta
patrimonial).

**Fonte normativa.** **A confirmar** — **Lei 12.973/2014**, arts. 2º a
5º (regime de subcontas para diferença entre depreciação/amortização
fiscal e societária) e **IN RFB 1.700/2017**, que a regulamenta.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-07, PAT-17, PAT-05 (subconta na amarração).

**Dados.** Diferença calculada (fiscal − societária) por bem e
competência; lançamento em subconta quando parametrizado.

**Regras.** Diferença = depreciação fiscal − depreciação societária,
sempre em `Decimal`, sinal preservado (positivo quando fiscal > societária,
negativo no caso inverso); lançamento em subconta, quando gerado, também
fecha em débitos = créditos.

**Telas e documentos.** Relatório — classe **conferência**; lançamento
associado (PAT-15).

**Critérios de aceite.** Teste de referência com o exemplo acima (R$
958,37 de diferença) provando o cálculo exato; soma das diferenças do
período bate com a soma das duas colunas (fiscal e societária) separadas.

**Não copiar/riscos.** A Lei 12.973/2014 é assunto técnico com
jurisprudência e interpretação próprias — **nenhuma regra de composição
das subcontas entra em código sem confirmação da fonte oficial e,
idealmente, validação profissional do Fred**.

**Perguntas.** O escritório do Fred já opera com subcontas da Lei
12.973/2014 em algum cliente hoje, ou este é um recurso avançado sem uso
imediato?

### PAT-20 — Depreciação sobre custo atribuído

**O que é.** O cálculo da depreciação quando o bem foi reavaliado a
"custo atribuído" (*deemed cost*) na adoção inicial das normas contábeis
atuais — situação de transição, rara em carteira nova.

**Exemplo.** Bem com custo histórico R$ 50.000,00, custo atribuído na
adoção inicial de R$ 80.000,00 (avaliação a valor justo na data de
transição) — a depreciação societária passa a incidir sobre R$ 80.000,00
a partir daquela data.

**Referência de rotina.** Manual, páginas 268-269.

**Fonte normativa.** **A confirmar** — CPC 27/NBC TG 27 e o CPC
específico de adoção inicial (regra de transição, tipicamente pontual e
já ultrapassada para a maioria das empresas — a confirmar se ainda tem
uso prático em 2026).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-17.

**Dados.** Nenhum modelo novo além de um valor de "custo atribuído" e
data de atribuição, associados ao bem.

**Regras.** Mesmas de PAT-17, com base substituída pelo custo atribuído a
partir da data de transição.

**Telas e documentos.** Relatório — classe **conferência**.

**Critérios de aceite.** A definir junto do plano de etapa, se
priorizado.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** A carteira do Fred tem algum cliente com custo atribuído
registrado? Se não, este item pode ficar em "fora de escopo por ora" (ver
seção própria abaixo).

## Onda 4 — CIAP e créditos de PIS/COFINS (depois do Fiscal)

### PAT-21 — Parâmetros e cálculo do crédito de ICMS do imobilizado (CIAP)

**O que é.** O **Controle de Crédito de ICMS do Ativo Permanente**: o
direito de a empresa se creditar, em **48 parcelas mensais** (regra
geral), do ICMS pago na aquisição de um bem do ativo imobilizado usado na
atividade tributada — cada UF tem sua própria regulamentação de detalhe
(pro rata die, parcela única em casos especiais, postergação quando não
há saída tributada).

**Exemplo.** Bem com ICMS destacado de R$ 12.000,00 na nota de aquisição.
Regra geral (1/48): crédito mensal de **R$ 250,00**, por 48 meses, desde
que haja saída tributada suficiente no período (senão, pode ser postergado
conforme a UF).

**Referência de rotina.** Manual, páginas 61-63 (parâmetros da empresa,
guia Impostos/ICMS: pro rata die, postergação, período de curto prazo,
regras específicas por UF — RS, SC, PR, SP, MG, BA) e 90-96 (parâmetros
por bem: crédito de ICMS pró-cargas, 1/42 ou 1/36 conforme UF, parcela
única, mês de início efetivo das atividades).

**Fonte normativa.** **A confirmar** — **LC 87/1996 (Lei Kandir), art.
20, § 5º** (regra geral do CIAP: 1/48, proporcional à saída tributada) e a
**legislação de cada UF** que regulamenta o detalhe (o CIAP tem forma
**estadual**, não federal única — cada estado publica seu próprio modelo
de escrituração).

**Situação no DataLedger.** **Não existe** — **depende do Fiscal**
(apuração de ICMS, que também não existe: FIS-08, FIS-23, FIS-46).

**Depende de.** PAT-02, PAT-05, FIS-08 (imposto ICMS cadastrado), FIS-23
(apuração do ICMS do período, para saber se há saída tributada
suficiente).

**Dados.** Modelo novo: parâmetro de CIAP por empresa e por UF (pro rata
die sim/não, postergação, período de curto/longo prazo), parâmetro de
CIAP por bem (base do crédito, número de parcelas conforme a regra
estadual aplicável, mês de início), tabela de valores creditados por
competência (1/48 apropriado a cada mês).

**Regras.** Crédito nunca excede o valor total do ICMS destacado na nota;
apropriação mensal é rastreável até a competência e o bem de origem
(memória de cálculo); regra de proporcionalidade à saída tributada, **por
UF**, não inventada sem confirmação da legislação estadual específica.

**Telas e documentos.** Tela de cálculo — classe **conferência**;
consolida no livro CIAP (PAT-22).

**Critérios de aceite.** A definir junto do plano de etapa, com pelo
menos um caso de referência **por UF atendida pela carteira** (não um
caso genérico — o CIAP não é uniforme entre estados).

**Não copiar/riscos.** **Risco central deste item:** implementar CIAP
"genérico" sem UF é implementar uma ficção — o manual documenta ao menos
seis regimes estaduais diferentes (RS, SC, PR, SP, MG, BA) só nas páginas
lidas. Nenhuma regra de UF entra em código sem a legislação daquele
estado confirmada.

**Perguntas.** **Pergunta central deste plano, levada explicitamente ao
Fred:** a carteira dele tem cliente no lucro real (ou lucro presumido com
direito a crédito de ICMS) sujeito a CIAP? **Em quais UFs?** Sem essa
resposta, não há como priorizar nem confirmar a legislação estadual
correta — implementar todas as UFs de uma vez seria desproporcional ao
uso real.

### PAT-22 — Ficha CIAP, termos e integração com a escrita fiscal (crédito e débito de ICMS)

**O que é.** O livro fiscal auxiliar (Ficha de Controle de Crédito de ICMS
do Ativo Permanente — "Ficha CIAP"), na forma que a legislação de cada UF
exige, e a integração que lança, na escrita fiscal, o crédito apurado
(PAT-21) e o eventual **débito** de ICMS (diferencial de alíquota, na
compra de outra UF; ou importação).

**Exemplo.** Ficha CIAP do caminhão, mês a mês: coeficiente de
apropriação, valor a creditar, valor já creditado, saldo a creditar —
até o 48º mês, quando o saldo chega a zero.

**Referência de rotina.** Manual, páginas 277-280 (Ficha CIAP e termos),
280-282 (ICMS creditado e resumo), 282-285 (débito de ICMS — importação e
diferencial de alíquotas), 248-251 (integração: crédito e débito de
ICMS para a Escrita Fiscal).

**Fonte normativa.** **A confirmar** — mesma base de PAT-21 (LC 87/1996 e
legislação estadual); o **modelo da Ficha CIAP** é definido por convênio
e por cada UF (não há modelo único nacional — **a confirmar por UF**).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-21, FIS-46 (livros de apuração — a Ficha CIAP se
relaciona com o Livro de Apuração do ICMS).

**Dados.** Livro/relatório derivado de PAT-21, no leiaute que a UF exigir;
lançamento fiscal de crédito e de débito, cada um rastreável até o bem e a
competência de origem.

**Regras.** Igual a FIS-46: imutável para período encerrado; bate
exatamente com o valor apurado em PAT-21.

**Telas e documentos.** Ficha CIAP — classe **livro** (a forma é
prescrita por UF); demonstrativo de crédito/débito — classe
**conferência**.

**Critérios de aceite.** A definir junto do plano de etapa, com validação
por UF.

**Não copiar/riscos.** O manual lista **códigos de ajuste da escrita
fiscal** específicos do sistema de referência — não copiar a
codificação do concorrente; o DataLedger define seus próprios códigos,
mapeados para o leiaute oficial de cada UF quando aplicável.

**Perguntas.** Mesma de PAT-21 (UFs atendidas pela carteira).

### PAT-23 — Crédito de PIS e COFINS sobre o imobilizado

**O que é.** O crédito de PIS e COFINS (regime não cumulativo) sobre a
aquisição — ou sobre a depreciação — de bem do ativo imobilizado usado na
produção de bens ou prestação de serviços.

**Exemplo.** Máquina de R$ 100.000,00, crédito calculado sobre a
**depreciação** (uma das duas formas permitidas pela legislação, a
confirmar qual se aplica ao caso): depreciação mensal de R$ 833,33
(10% a.a.) × alíquotas de PIS (**a confirmar**, ilustrativamente 1,65%) e
COFINS (**a confirmar**, ilustrativamente 7,6%) = crédito mensal de PIS
R$ 13,75 e de COFINS R$ 63,33 (**valores ilustrativos, não usar sem
confirmação de alíquota e de qual base de cálculo se aplica ao caso
concreto**).

**Referência de rotina.** Manual, páginas 64-65 (parâmetros da empresa:
crédito sobre depreciação × crédito sobre valor de aquisição, MP 540/11,
dedução do crédito de ICMS da base), 87-89 (parâmetros por bem: base do
crédito, período de cálculo, CST, vínculo do crédito), 285-287 (relatório
do crédito de PIS/COFINS), 251-252 (integração com a Escrita Fiscal).

**Fonte normativa.** **A confirmar** — **Leis 10.637/2002 (PIS não
cumulativo)** e **10.833/2003 (COFINS não cumulativo)**, com as
alterações que regulam o crédito sobre bens do ativo imobilizado
(inclusive a forma "sobre a depreciação" versus "sobre o valor de
aquisição, em 1/48" — regras que mudaram ao longo do tempo e **precisam
de conferência de vigência**, não do histórico do manual, que é de 2018).

**Situação no DataLedger.** **Não existe** — **depende do Fiscal**
(regime de PIS/COFINS, FIS-29 a FIS-34).

**Depende de.** PAT-02, PAT-07 (base de depreciação, se essa for a forma
de cálculo), FIS-08, FIS-23.

**Dados.** Modelo novo: parâmetro de crédito de PIS/COFINS por empresa
(forma de cálculo — depreciação ou aquisição) e por bem (base do crédito,
período de cálculo, CST); tabela de crédito apurado por competência,
rastreável até a base e a alíquota aplicada.

**Regras.** Crédito calculado com alíquota **vigente na competência**
(nunca a alíquota atual do cadastro, mesma regra de FIS-08); memória de
cálculo obrigatória; a forma de cálculo (depreciação × aquisição) é
parâmetro da empresa, não escolha ad hoc por lançamento.

**Telas e documentos.** Relatório — classe **conferência**; lançamento
associado (integração fiscal).

**Critérios de aceite.** A definir junto do plano de etapa, com caso de
referência confirmado em fonte oficial (nenhum dos números ilustrativos
acima entra em teste como valor esperado sem essa confirmação).

**Não copiar/riscos.** **Não inventar alíquota nem forma de cálculo** — a
legislação de PIS/COFINS sobre imobilizado teve mudanças relevantes desde
2008 (inclusive a MP 540/11 citada pelo próprio manual, que é histórica);
usar o texto do manual como se fosse a regra vigente seria o erro que o
AGENTS.md proíbe.

**Perguntas.** Qual é a forma de crédito que a carteira do Fred usa hoje
(sobre depreciação ou sobre aquisição) e desde quando — histórico
necessário para não reprocessar competência já apurada com regra errada.

## Onda 5 — Valor justo e impairment

### PAT-24 — Avaliação a valor justo e perda por não recuperabilidade

**O que é.** A reavaliação periódica do bem pelo seu **valor justo** de
mercado (quando maior que o valor contábil, ganho; quando menor, perda por
"não recuperabilidade" — o *impairment* da norma contábil), usada por
empresas que adotam a contabilidade societária plena.

**Exemplo.** Imóvel com valor contábil (custo − depreciação acumulada) de
R$ 300.000,00, avaliado a valor justo de mercado em R$ 350.000,00: sem
perda (o manual não registra ganho automático além do valor contábil,
salvo avaliação superior expressa — mecânica exata a confirmar na NBC TG
01/27). Se avaliado em R$ 260.000,00: **perda por não recuperabilidade de
R$ 40.000,00**, lançada a débito de despesa e a crédito de conta
retificadora do ativo.

**Referência de rotina.** Manual, páginas 241-246 (janela Avaliações pelo
Valor Justo: valor original/avaliado, depreciação acumulada, perdas
anteriores, valor contábil, valor justo/avaliado, perda por não
recuperável, guia Contabilidade).

**Fonte normativa.** **A confirmar** — **NBC TG 01** (Redução ao Valor
Recuperável de Ativos) para a perda por não recuperabilidade; a
reavaliação a valor justo do imobilizado, no Brasil, é **vedada como
prática obrigatória** e tratada com cautela na norma vigente (revogada
como opção geral) — **este ponto precisa de confirmação normativa
específica antes de qualquer implementação**, porque a prática permitida
hoje é mais restrita do que "reavaliar livremente" (o manual, de 2018,
pode refletir regra anterior).

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-17 (depreciação societária acumulada, base do
cálculo), PAT-05 (contas de avaliação).

**Dados.** Modelo novo `AvaliacaoAValorJusto`: bem, competência, valor
contábil na data, valor justo/avaliado, perda por não recuperável
(calculada), valor residual, taxa de depreciação após a avaliação.

**Regras.** Perda = valor contábil − valor justo, apenas quando positivo
(nunca gera "ganho" negativo sem base normativa confirmada); lançamento
associado fecha em débitos = créditos.

**Telas e documentos.** Tela de avaliação — classe **conferência**, com
lançamento associado.

**Critérios de aceite.** A definir junto do plano de etapa, **após**
confirmação normativa específica (este item tem risco normativo maior que
os demais do módulo).

**Não copiar/riscos.** **Risco maior deste item:** implementar
"reavaliação a valor justo" sem confirmar se a norma brasileira vigente
permite essa prática, e em que condições, seria inventar exigência ou
faculdade contábil — proibido pelo AGENTS.md. Levar ao Fred antes de
qualquer código.

**Perguntas.** A carteira do Fred tem cliente que pratica avaliação a
valor justo do imobilizado hoje? Se não, este item deveria ficar
represado até haver demanda real, dado o risco normativo.

## Onda 6 — Razão auxiliar da ECD

### PAT-25 — Razão auxiliar do imobilizado para a ECD (SPED Contábil)

**O que é.** Um arquivo auxiliar do SPED Contábil (distinto da ECD
principal) que detalha a movimentação do imobilizado — bem a bem — dentro
da escrituração contábil digital, quando a empresa opta por essa
granularidade.

**Exemplo.** Arquivo "Razão Auxiliar" de 2024, listando, para a conta
"Veículos", cada bem com seu saldo inicial, movimento do exercício e
saldo final — nível de detalhe que a ECD principal (por conta, não por
bem) não têm.

**Referência de rotina.** Manual, páginas 287-294 (janela SPED Contábil –
Razão Auxiliar: período, entidades com acesso, seleção de contas
patrimoniais, indicadores de situação especial/início de período/NIRE,
finalidade da escrituração, HASH de substituição, signatários adicionais,
escrituração principal vinculada).

**Fonte normativa.** **A confirmar** — mesmo leiaute-base do **Manual de
Orientação do Leiaute da ECD** (Receita Federal/Sped) já referenciado em
**CTB-51**; o Razão Auxiliar do imobilizado é um bloco/arquivo
complementar, cuja obrigatoriedade e leiaute específico **não foram
conferidos nesta sessão**.

**Situação no DataLedger.** **Não existe** — **depende de CTB-50, CTB-51**
(plano de contas referencial e ECD), que também não existem.

**Depende de.** PAT-15 (todos os lançamentos do módulo já integrados),
PAT-16, CTB-50, CTB-51.

**Dados.** Depende inteiramente do leiaute oficial, a confirmar; a favor
do DataLedger, todo o dado de origem (bem, movimento, saldo) já existe nas
ondas 1-3 deste plano.

**Regras.** Geração recusada sem plano de contas referencial vinculado
(mesma regra de CTB-50); arquivo gerado é rastreável até os lançamentos
de origem (conciliação obrigatória, AGENTS.md).

**Telas e documentos.** Classe **livro** (digital) — arquivo regulatório
com leiaute oficial, zero margem de personalização de conteúdo
obrigatório.

**Critérios de aceite.** A definir junto do plano de etapa, com validação
contra o validador oficial do Sped antes de qualquer entrega real.

**Não copiar/riscos.** Idêntico ao já registrado em CTB-51: retificação de
entrega substitui o **documento**, não corrige o **fato contábil** — o
padrão `estorno_de` do lançamento não se aplica direto aqui.

**Perguntas.** O escritório do Fred transmite Razão Auxiliar hoje, para
quais clientes, e com que periodicidade?

## Relatórios cadastrais

### PAT-26 — Relatórios cadastrais

**O que é.** As listagens de apoio dos cadastros do módulo: bens, contas
patrimoniais, centros de custo, parâmetros — sem cálculo, só conferência
do que foi digitado.

**Exemplo.** Listagem de todos os bens ativos da empresa, com código,
nome, conta patrimonial e data de aquisição.

**Referência de rotina.** Manual, páginas 294-320.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** PAT-02, PAT-05, PAT-06.

**Dados.** Nenhum além dos já cadastrados.

**Regras.** Isolamento por empresa; sem regra de cálculo.

**Telas e documentos.** Relatórios — classe **conferência**.

**Critérios de aceite.** Listagem reflete exatamente os cadastros
gravados, sem campo calculado incorreto.

**Não copiar/riscos.** Nenhum específico.

**Perguntas.** Nenhuma.

## Fora de escopo ou dependente de confirmação

| Item | Motivo |
| --- | --- |
| PAT-06 | Depende de CTB-33 (centro de custo), que não existe na Contabilidade — sem dono definido até lá. |
| PAT-20 | Custo atribuído é regra de transição pontual; sem confirmação de uso real na carteira, fica represado. |
| PAT-21, PAT-22 | CIAP depende do Fiscal (FIS-08, FIS-23, FIS-46, nenhum existente) e de legislação **estadual** por UF, não levantada nesta sessão — **onda 4, explicitamente "depois do Fiscal"**. |
| PAT-23 | Depende do regime de PIS/COFINS do Fiscal (FIS-29 a FIS-34), inexistente. |
| PAT-24 | Risco normativo maior do plano: a permissão e a forma de reavaliação a valor justo do imobilizado no Brasil precisam de confirmação em fonte oficial antes de qualquer linha de código. |
| PAT-25 | Depende de CTB-50/CTB-51 (plano de contas referencial e ECD), inexistentes; leiaute do Razão Auxiliar não conferido em fonte oficial. |

## Glossário

| Termo | Significado |
| --- | --- |
| **Bem** | Um item do ativo imobilizado, unidade de controle do módulo (PAT-02). |
| **Conta patrimonial** | Agrupamento de bens de mesma natureza, com taxa de depreciação fiscal por vigência e amarração contábil (PAT-05) — não confundir com `Conta` da Contabilidade, embora se relacione com ela via amarração. |
| **Depreciação fiscal** | A depreciação pela taxa que a Receita Federal aceita como dedutível (IN RFB 1.700/2017, Anexo III, a confirmar). |
| **Depreciação societária** | A depreciação pelo critério contábil (NBC TG 27): vida útil econômica real, valor residual. |
| **Valor depreciável** | Valor de aquisição (ou avaliado) menos valor residual — a base sobre a qual a depreciação incide. |
| **Valor contábil** | Custo (ou avaliado) menos depreciação acumulada — o que resta do bem nos livros. |
| **Ganho/perda de capital** | Diferença entre o valor de venda e o valor contábil na baixa de um bem (PAT-11); alimenta o Lalur. |
| **CIAP** | Controle de Crédito de ICMS do Ativo Permanente — direito de crédito do ICMS pago na aquisição de bem do imobilizado, em regra 1/48, com forma definida por cada UF (PAT-21/PAT-22). |
| **Custo atribuído** | Valor de reavaliação do bem na adoção inicial das normas contábeis vigentes, usado como nova base de depreciação societária (PAT-20). |
| **Valor justo** | Valor de mercado do bem numa data de avaliação, usado para apurar ganho ou perda por não recuperabilidade (PAT-24). |
| **Lei 12.973/2014** | Regime de subcontas que neutraliza, na apuração fiscal, a diferença entre a contabilidade societária e a fiscal (PAT-19). |
| **Classe de documento** | Cadastro, conferência, demonstração, livro ou guia — de [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md). |

## Perguntas abertas consolidadas

1. **PAT-01** — Há cliente na carteira que deduz ICMS/PIS-COFINS do valor
   original do bem?
2. **PAT-02** — O cadastro de bem é digitado um a um, ou precisa de
   importação (planilha/nota fiscal)?
3. **PAT-06** — A carteira usa centro de custo (mesma pergunta em aberto na
   Contabilidade, RC-54)?
4. **PAT-08** — Qual a taxa oficial vigente de depreciação fiscal para os
   bens mais comuns da carteira (precisa de conferência na IN RFB
   1.700/2017)?
5. **PAT-11** — O DataLedger deve permitir mais de uma baixa parcial do
   mesmo bem na mesma competência?
6. **PAT-13** — Há clientes com matriz e filiais que transferem bens entre
   si?
7. **PAT-17** — A carteira tem cliente que precisa de depreciação
   societária divergente da fiscal?
8. **PAT-19** — Já há uso de subcontas da Lei 12.973/2014 em algum cliente?
9. **PAT-21/PAT-22 (central)** — Há cliente sujeito a CIAP? **Em quais
   UFs?** Sem resposta, a onda 4 não pode ser priorizada nem a legislação
   estadual confirmada.
10. **PAT-23** — Qual a forma de crédito de PIS/COFINS sobre imobilizado
    que a carteira usa hoje (depreciação ou aquisição), e desde quando?
11. **PAT-24** — Há cliente que pratica avaliação a valor justo do
    imobilizado? A norma brasileira vigente permite essa prática, e em
    que condições — precisa de confirmação em fonte oficial antes de
    qualquer código.
12. **PAT-25** — O escritório transmite Razão Auxiliar da ECD hoje, para
    quais clientes?
