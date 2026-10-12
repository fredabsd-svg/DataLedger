# DL-087 — Fiscal: classificação fiscal versionada e regras de importação (corte 1)

**Demanda:** ordem do Fred de 09/10/2026 (RC-175): entender os acumuladores do
sistema de referência e codar o que falta. **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1), porque a classificação dirige a receita, o
pré-DAS e o Presumido. A auditoria faz uma rodada, uma correção e uma
reconferência. As DL-085 e DL-082 já estão na `main` (PR #108).

## Base

- [Pesquisa sobre os acumuladores](../projeto/pesquisa-acumuladores-2026-10-09.md),
  de 09/10/2026, no manual e na central de soluções. É rotina, não norma.
- [Consulta ao contador-senior sobre a classificação fiscal](../projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md),
  itens 1 e 2: HI-141 e HI-142.
- [Revisão do módulo fiscal](../projeto/revisao-do-fiscal-2026-10-09.md),
  lacuna A1.

## O problema

Hoje a classificação que dirige o cálculo está **no código**: três catálogos
fechados (`NaturezaOperacao`, `NaturezaTomada` e `NaturezaOperacaoNFe` com
`CATALOGO_NATUREZA_NFE`), sem vigência, sem regra por tributo e sem conta. A
sugestão também está no código, como `if` em Python.

- Cada imposto novo (ICMS, PIS/Cofins, IBS/CBS) reabre o catálogo no código.
- O escritório não consegue ensinar ao produto uma regra nova, como "este
  CFOP com este NCM é combustível para consumo".

## Revisão do plano (12/10/2026, arquiteto)

O Fred passou a DL-087 a esta sessão (RC-177). O plano foi relido contra a
`main` depois do PR #108, e o corte 1 foi **reordenado**. É decisão do
arquiteto, reversível.

- **O que mudou no código desde o plano:** a DL-084 criou o padrão de
  combustível por empresa (`sugerir_natureza_com_padrao`), já ligado à
  conferência, ao lote e à API. A DL-088 trouxe o anexo do Simples por
  vigência no `pre_das.py`.
- **Por que reordenar:** a sugestão embutida
  (`escrituracao_nfe.sugerir_natureza_item`) é lógica fina:
  - combustível pela descrição oficial do CFOP e pelo NCM;
  - lubrificante fora do 1,6%;
  - devolução pela coluna indDevol;
  - conflito entre sinais;
  - ajuste do CSOSN 500 do posto.

  Convertê-la em linhas de tabela com "a mesma resposta" é o maior risco da
  etapa e não muda nada que o escritório veja: a camada global é imutável
  para ele de qualquer jeito (HI-141). O que o escritório precisa já é
  **ensinar regra nova** e **ver o que ficou sem classificação**.
- **Novo corte 1:** regras do escritório e da empresa como dado, por cima da
  sugestão embutida, mais a fila "a classificar" e as telas.
- **Corte 2:** a sugestão embutida vira linhas do pacote global, as naturezas
  viram tabela e entram as regras tributárias por natureza × regime × tributo
  × vigência.

## Escopo do corte 1

Só **NF-e e NFC-e de saída própria e de devolução de venda** (a escrituração
das DL-081 e DL-085). NFS-e prestada e tomada ficam como estão.

1. **Regra de classificação** (modelo novo, `RegraClassificacaoNFe`).
   - **Escopo:** escritório (vale para todas as empresas dele) ou empresa.
   - **Tipo de nota:** saída ou devolução. Ajuste (`finNFe` 2, 3, 5 ou 6)
     nunca recebe regra.
   - **Critérios:**
     - CFOP de 4 dígitos, **obrigatório** e existente na tabela oficial;
     - NCM opcional, exato ou por prefixo de 2 a 7 dígitos;
     - CST ou CSOSN do ICMS, opcional, comparado como está na nota;
     - `idDest` opcional (1, 2 ou 3).
   - **Resultado:** uma natureza de `NaturezaOperacaoNFe` permitida para o
     tipo (`naturezas_permitidas`).
   - **Vigência:** início obrigatório e fim opcional, comparados com a data
     de emissão da nota.
   - **Imutável depois de criada.** Para mudar, desativa-se (fim da vigência,
     com motivo) e cria-se outra. Criar e desativar vão para a trilha.
   - Duas regras ativas com o mesmo escopo, os mesmos critérios e vigências
     que se cruzam: a segunda é recusada (409), sem duplicidade silenciosa.
2. **Resolução da sugestão** (módulo novo `apps/fiscal/classificacao.py`,
   função única). Para cada item:
   1. a nota de ajuste, o CFOP fora da tabela e o item sem leitura seguem a
      sugestão embutida, sem consultar regra;
   2. as regras **vigentes** do escritório e da empresa que casam com o item;
   3. entre elas, vence a de **maior especificidade**. Os pesos são publicados
      no código e na tela: CFOP 8 (sempre), NCM exato 4, NCM por prefixo 2,
      CST/CSOSN 2, `idDest` 1;
   4. empate de especificidade: vence o escopo **empresa** sobre o escritório;
   5. empate de escopo: **conflito**. O item fica sem sugestão, e o motivo
      nomeia as regras;
   6. nenhuma regra casa: a sugestão embutida de hoje, **inalterada**, e depois
      o padrão de combustível da DL-084, como hoje.

   A precedência por pesos é a proposta da HI-142; a escolha entre pesos e
   ordem manual continua com o Fred (PE-91). A sugestão passa a dizer **de
   onde veio**: regra n.º X (escopo), sugestão do produto ou padrão da
   empresa.
3. **Sem consulta por item.** As regras vigentes são carregadas **uma vez por
   chamada**, no mesmo ponto em que hoje se lê o padrão de combustível
   (conferência, lote, API de escrituração, tela). O orçamento de tempo do
   lote da DL-085 continua valendo (BL-698).
4. **A regra só muda sugestão.**
   - Nunca altera escrituração efetivada.
   - Nunca altera a natureza já escolhida num rascunho.
   - Muda o que é sugerido nas notas a escriturar, nos itens ainda sem
     natureza dos rascunhos e na prévia do lote.
   - A assinatura do grupo do lote inclui a regra que produziu a sugestão:
     criar ou desativar uma regra muda a prévia, e uma confirmação baseada na
     prévia antiga recebe 409, como já acontece hoje.
5. **Fila "a classificar"** por empresa e mês.
   - Contém os itens das notas a escriturar (lidas e não efetivadas) **sem
     sugestão** ou **em conflito**.
   - Os itens são **agrupados** por tipo, CFOP, NCM, CST/CSOSN, `idDest` e
     motivo, com quantidade de notas, de itens e valor. Um posto com
     milhares de NFC-e vê grupos, não milhares de linhas.
   - Cada grupo traz a ação "criar regra" pré-preenchida com os critérios do
     grupo. A regra criada reaplica sozinha, porque a sugestão é calculada na
     hora.
6. **Permissões no servidor:**
   - regra de **empresa**: quem escritura no fiscal
     (`PAPEIS_QUE_ESCRITURAM_FISCAL`);
   - regra de **escritório**: só ADMINISTRADOR e GESTOR, porque vale para
     todos os clientes;
   - leitura: quem lê o fiscal;
   - isolamento: a regra de um escritório nunca casa com a nota de outro.
7. **API e telas:**
   - lista e cadastro de regras, com filtro por escopo e situação, e ação de
     desativar;
   - a fila "a classificar";
   - a página "regras do produto", só leitura: descreve em palavras a
     sugestão embutida, com a fonte de cada linha;
   - a sugestão mostrada na escrituração e no lote diz a origem.

**Fica fora do corte 1:**
- conversão da sugestão embutida em linhas do pacote global;
- naturezas como tabela;
- regras tributárias por tributo e vigência (ICMS, IPI, PIS/Cofins,
  IBS/CBS, retenções);
- CST do PIS, lista nomeada de NCM, equivalência CST × CSOSN, CRT e
  participante como critério;
- modelo contábil (integração fiscal → contábil);
- NFS-e prestada e tomada;
- reprocessamento de efetivadas por mudança de regra.

## Ajustes pela consulta ao contador-senior (12/10/2026)

[Consulta](../projeto/consultas/2026-10-12-contador-senior-dl087-regras.md)
feita por ordem do Fred (RC-178). A resposta é decisão delegada, reversível
pelo Fred. Ela **substitui** o escopo acima nestes pontos, e os ajustes foram
repassados à frente A em desenvolvimento:

1. **Precedência por pesos fixos, não por ordem manual** (PE-91, item 1). Os
   pesos passam a ser potências de dois, para que conjuntos diferentes de
   critérios nunca empatem: CFOP 16, NCM exato 8, NCM por prefixo 4,
   CST/CSOSN 2, `idDest` 1. Os pesos não são configuráveis por escritório.
2. Entre prefixos de NCM, vence o **mais longo**.
3. **Conflito é só natureza diferente.** Empate de regras que apontam a mesma
   natureza dá a sugestão, e o motivo nomeia as regras.
4. **Regra com resultado de combustível exige NCM** (exato ou prefixo). Se o
   NCM alcança lubrificante, a criação vem com aviso. É a HI-139 em forma de
   dado.
5. Regra de escritório com CST de regime normal vem com o aviso de que não
   alcança clientes do Simples, que emitem CSOSN.
6. **A origem da sugestão aceita fica gravada** na natureza confirmada:
   regra, produto, padrão da empresa ou escolha manual. A lista de regras
   mostra quantos itens cada uma alcançou.
7. **Prévia de impacto** antes de salvar a regra, sem gravar nada.
8. A fila e a regra respeitam o mês que não aceita mais escrituração.
9. Sem aprovação prévia de regra: a natureza já é confirmada pelo contador.
   A revisão posterior é feita pela lista, pela trilha e pela origem gravada.
   Sem "duplicar regra".

Mutantes acrescentados ao critério 8: pesos que empatam conjuntos distintos;
conflito com a mesma natureza; combustível sem NCM aceito.

## Entrega da frente A (12/10/2026)

Integrada na branch. Migrações `fiscal 0019` (regra) e `0020` (origem da
natureza confirmada, em tabela própria 1:1). Medido pelo desenvolvedor, num
banco próprio: suíte completa 9.983/1/56 (a falha é a de ambiente). 126
testes novos; nove mutantes derrubam testes.

- Volume com 10.000 NFC-e: média das partes de confirmação +5,8% sem regra
  e +8,2% com 50 regras, depois de indexar as regras por CFOP. Sem o
  índice, 50 regras estouravam o teto de 10 s da chamada. A margem até os
  10% do critério 7 é pequena, e o ruído do ambiente é alto.
- **Mês já confirmado (ajuste 8):** o fiscal permite escriturar nota de mês
  confirmado e reabre a confirmação como "a retificar" (DL-074). Por isso a
  fila **avisa** e não bloqueia. Bloquear seria mais restritivo que a própria
  escrituração. Decisão do arquiteto.
- **Conflito entre regras quase não ocorre:** com pesos em potências de dois,
  regras de critérios diferentes nunca empatam, e a regra repetida no mesmo
  escopo é recusada (409) na criação. O conflito aparece no cadastro, e não
  na fila.
- Desativar fixa o fim da vigência no dia anterior.
- A reversão da 0020 recusa só se houver regra; sem regra, a tabela de
  origens é descartada. A auditoria deve avaliar isso.
- A reclassificação em massa grava a origem, mas não tem teste próprio.

Próximo: frente B (telas), depois a auditoria.

## Entrega da frente B (12/10/2026)

Integrada na branch. São cinco telas:
- regras da empresa, com a ordem de decisão e os pesos publicados;
- nova regra, com prévia de alcance com e sem cada critério opcional;
- desativar, com motivo obrigatório;
- fila "a classificar" do mês;
- regras do produto.

A origem da sugestão aparece na escrituração e no lote, e a lista "NF-e a
escriturar" e o lote ganharam link para a fila. Medido pelo desenvolvedor:
78 testes novos.

Ajustes de integração do arquiteto:
- as cinco rotas entraram no teste de cobertura de telas;
- "Regras do produto" entrou no menu. As regras de cada empresa e a fila
  pedem a empresa e são abertas a partir da lista.

Limitações declaradas:
- a origem no lote não separa sugestão do produto de padrão da empresa;
- a prévia chama o serviço até quatro vezes;
- sem verificação em navegador real.

## Decisões para a correção (rodada 1)

A [rodada 1](../auditorias/2026-10-12-dl-087-rodada-1.md) foi **reprovada**:
A1 é alto, A2 a A8 são médios e A9 a A13 são baixos. O que se sustenta:
- sem regra, a sugestão é idêntica à anterior em 2.852.352 combinações;
- precedência, vigência, isolamento, permissões e imutabilidade no banco;
- 30 de 35 mutantes morrem.

Decisões do arquiteto para a correção única (§3.1), reversíveis pelo Fred:

- **A1 (alta): desativar passa a ser revogar.** A regra desativada deixa de
  casar com **qualquer** nota, pendente ou futura. A escrituração efetivada
  guarda a origem que teve, e nada nela muda. Não há "encerrar vigência" no
  corte 1: quem quer uma regra com fim cria-a já com o fim. A assinatura do
  lote muda, e a confirmação com a prévia antiga recebe 409. Os rótulos de
  origem marcam "desativada", e os textos da tela de desativação dizem o
  novo efeito. Isso substitui a frase do escopo 4 sobre o histórico.
- **A2:** a prévia verifica a duplicidade antes de calcular e responde 409
  com a mensagem; a ordenação tolera regra ainda sem número.
- **A3:** a contagem de itens confirmados é filtrada pela empresa da URL, na
  API, na lista e na desativação.
- **A4:** identificador de assinatura malformado responde 400.
- **A5:** NCM só com dígitos ASCII (e pontos); qualquer outro caractere é
  recusado com 400 e mensagem.
- **A6:** o índice das regras passa a separar NCM exato, prefixos e regras
  sem NCM, para que 50 regras no **mesmo** CFOP das notas não custem 50
  comparações por item. A prévia da tela calcula todas as variantes numa
  passada só. A medida de volume é refeita com as regras nos CFOP reais das
  notas, e o número vai para o plano. Se os 10% do critério 7 não forem
  alcançáveis, o desenvolvedor informa a medida, e o arquiteto decide.
- **A7:** fica a decisão de **avisar** e não bloquear o mês confirmado,
  registrada na DE-108. O aviso passa a aparecer também na prévia do lote e
  na prévia de impacto.
- **A8:**
  - a nota efetivada mostra a **origem gravada**, com a regra e a marca de
    desativada, e não a sugestão de hoje;
  - a lista de regras ganha "ver notas", com as notas e os itens confirmados
    a partir de cada regra, filtrados pela empresa;
  - a tabela de origem ganha gatilho de imutabilidade para escrituração
    efetivada.
- **A9:** a reversão da 0020 também recusa quando houver origem gravada.
- **A10:** o teste de equivalência usa CFOP sem ponto e inclui regras que não
  casam.
- **A11:** testes da origem na reclassificação em massa e da natureza
  escolhida que continua selecionada na tela.
- **A12:** o texto das regras do produto é corrigido (sufixos x.501, x.502,
  x.910, x.911) e a referência ao teste inexistente sai.
- **A13:**
  - Enter no formulário não dispara "atualizar";
  - "Criar regra" na fila vira botão secundário pequeno;
  - a lista de regras pagina;
  - o gatilho recusa TRUNCATE e desativação por SQL que não seja revogação.

## Decisões tomadas na correção

Correção única integrada. Medido pelo desenvolvedor, numa única invocação:
10.113 passaram, com 2 falhas. Uma é a de ambiente; a outra foi resolvida
pelo arquiteto (item abaixo). Os 19 mutantes da correção morrem.

- **Desativar = revogar:** o fim da vigência vai para a véspera do início, e
  o gatilho do banco recusa qualquer outro fim na desativação.
- **Volume com 10.000 NFC-e e 50 regras nos CFOP reais das notas:**
  - a prévia do lote, a fila, a prévia de impacto e a confirmação ficaram
    dentro de ±5% de nenhuma regra;
  - a prévia da tela com variantes caiu de 7,3 s para 2,8 s.

  O pior caso, com regras que casam todo item, não foi medido.
- **TRUNCATE:** a recusa ficou só na tabela de regras. Na tabela de origens
  ela quebrava a limpeza dos testes transacionais de outras etapas.
- **A reversão da 0020 recusa com origem de nota efetivada.** Como a 0020 é
  revertida antes da 0014, a recusa dela vem primeiro. O teste da DL-082 que
  reverte com nota efetivada passou a aceitar a recusa de qualquer uma das
  duas e continua exigindo que nada mude. A mensagem da DL-082 segue testada
  nos casos de rascunho. Ajuste do arquiteto.
- **Limitações:**
  - a API da lista de regras não pagina; a tela e "ver notas" paginam;
  - o aviso do mês está no serviço e nas telas, mas não na API do lote.

## Critérios de aceite

1. **Sem regra cadastrada, nada muda.**
   - A suíte inteira passa sem mudar expectativa.
   - Um teste de equivalência compara, sem regra, a sugestão nova com a de
     `sugerir_natureza_com_padrao` sobre todos os CFOP da tabela oficial (com
     NCM de combustível, de lubrificante e comum; CST/CSOSN de ST e comum;
     `idDest` 1 e 3; saída e devolução).
2. A precedência segue a ordem declarada, com testes escritos à mão para
   cada degrau: especificidade, escopo e conflito com as duas regras
   nomeadas.
3. A vigência é respeitada nas duas pontas, contra a data de emissão da nota.
4. Uma regra:
   - muda a sugestão das notas a escriturar e da prévia do lote;
   - não muda efetivada nem natureza já escolhida em rascunho;
   - tem trilha de criação e de desativação;
   - respeita o isolamento por escritório e empresa e a permissão no servidor
     (403 e 404 testados).
5. Regra com natureza incompatível com o tipo, CFOP fora da tabela, ajuste
   ou duplicada é recusada com mensagem.
6. A fila agrupa e lista cada item sem sugestão ou em conflito, com o motivo.
   Criar a regra pela fila esvazia o grupo.
7. O lote da DL-085 continua equivalente ao individual, e a medida de volume
   (10.000 NFC-e) não piora mais que 10% com 50 regras cadastradas.
8. **Mutação:** cada um destes defeitos derruba teste:
   - inverter a precedência de escopo;
   - ignorar a vigência;
   - regra que altera efetivada ou natureza escolhida em rascunho;
   - padrão silencioso quando há conflito;
   - regra de outro escritório que casa.
9. Regressão completa numa única invocação, em banco próprio. Migração
   aditiva e reversível; a reversão recusa se houver regra.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — modelo, migração, `classificacao.py`, ligação nos pontos de sugestão, fila (serviço), API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/models.py`, migração nova, `apps/fiscal/classificacao.py`, `escrituracao_nfe.py`, `escrituracao_nfe_lote.py`, API e `urls_api.py`, `apps/core/restricoes.py`; testes `test_dl087_*` |
| B — telas: regras, fila, regras do produto, origem da sugestão | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `urls_web.py`, `templates/fiscal/`; testes `test_dl087_telas*` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Corte 2 (adiado)

O que o plano original punha no corte 1 e saiu na revisão de 12/10/2026:

- naturezas como tabela com vigência;
- regras tributárias por natureza × regime × tributo × vigência;
- conversão da sugestão embutida em pacote global de regras, com o teste de
  equivalência sobre o corpus;
- critérios adicionais da HI-142.

## Reversão

Reverter o merge volta a sugestão ao código. As tabelas novas saem com a
reversão da migração; as naturezas gravadas nos itens são as mesmas chaves de
antes e continuam válidas.
