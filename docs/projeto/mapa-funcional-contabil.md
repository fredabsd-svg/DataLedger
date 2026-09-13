# Mapa funcional — Contabilidade

Levantamento das **capacidades** que um módulo de contabilidade precisa ter num
escritório brasileiro, derivado da análise de um manual de referência de sistema
comercial, no diretório público indicado pelo Fred (RC-45), analisado em
2026-09-13 a pedido dele.

Companheiro do [mapa funcional fiscal](mapa-funcional-fiscal.md). Mesmas regras
de uso, mesma ressalva de data.

## O que este documento é, e o que não é

**É** um mapa de capacidades do domínio contábil: o que um escritório executa,
que dados sustentam cada saída e que regras verificáveis decorrem disso.

**Não é** cópia de sistema algum. Não foram transcritos texto, telas,
nomenclatura de menus nem estrutura de interface. O material é protegido por
direito autoral e **não está versionado neste repositório**, nem em trechos: foi
baixado para área temporária, lido, e o entendimento reescrito em nossas
palavras. Orientação do Fred: *"não faça igual"*.

O material é de **2018**. Nenhuma obrigação acessória aqui listada é requisito
enquanto o Fred não confirmar a vigência.

## Como o levantamento foi feito

O manual tem 856 páginas. Foi convertido em texto na área temporária
(`pdftotext`; a camada de texto é nativa, então OCR não foi necessário) e lido
por **dois auxiliares de pesquisa em paralelo, com fatias disjuntas** —
cadastros e movimentos de um lado, saídas e utilitários do outro. Nenhum dos
dois tem permissão de escrita; a árvore do repositório foi conferida limpa ao
fim. Cada um devolveu capacidades classificadas como *confirmado pelo domínio*,
*hipótese* ou *a conferir*.

O cruzamento com o que o DataLedger já tem foi feito por mim, `arquiteto-senior`,
lendo o código — não o `README`.

## As seis ideias estruturais

Mais importante que a lista de funcionalidades é entender **como as peças se
sustentam**. Seis decisões de arquitetura aparecem no domínio e mudam o nosso
desenho:

### 1. O lote é a unidade que fecha, não a partida

Débito igual a crédito é regra **do lote**, não de cada linha. Um lote pode ser
um débito para vários créditos, vários para vários, e o sistema precisa conhecer
essa topologia. Consequência direta: existe uma rotina de conferência dedicada a
**encontrar lotes cuja soma não fecha** — é a própria partida dobrada exposta
como ferramenta de diagnóstico.

Nosso `LancamentoContabil` já é o lote, e o serviço já valida a igualdade. O que
não temos é a **conferência**: uma consulta que varra a base e mostre o que está
torto. Sem isso, a invariante só existe no caminho feliz de quem usa a API.

### 2. Período de trabalho e fechamento são coisas diferentes

- **Período de trabalho** é a janela em que se está digitando agora. Lançar fora
  dela pode ser livre, gerar aviso ou ser bloqueado — é escolha por empresa.
- **Fechamento** é o ato formal de encerrar a competência. Depois dele, alterar
  exige controle explícito.

São dois controles distintos, e confundi-los é erro caro. O primeiro evita erro
de digitação (lançar 2025 em vez de 2026). O segundo é a garantia contábil.

Há ainda um terceiro, mais fino: **conta conciliada até uma data** não aceita
lançamento retroativo nem alteração antes dessa data, mesmo com o período
aberto.

### 3. A conta da empresa aponta para uma conta padronizada

O plano de contas da empresa é dela. Mas as obrigações digitais exigem que cada
conta analítica seja **amarrada a uma conta de um plano referencial oficial**,
por vigência. É um vínculo separado, cadastrado uma vez e replicável entre
empresas — não um campo dentro da conta.

Pré-condição verificável: sem 100% das contas movimentadas vinculadas, a
escrituração digital do período não pode ser gerada. Isso tem de bloquear ou
sinalizar, nunca sair em silêncio com conta faltando.

### 4. Demonstrativo é estrutura configurável ligada às contas

DRE, DLPA, DMPL, DFC, DVA não são relatórios com fórmula fixa no código. Cada um
tem uma **estrutura de grupos** e as contas da empresa são **vinculadas** a esses
grupos. Conta não vinculada simplesmente não entra na soma — o demonstrativo
sai, e sai errado, sem reclamar.

Mesma lógica dos índices de análise: quais contas compõem cada indicador é
configuração, não dedução automática do plano de contas.

Para nós, isso confirma a linha da DE-010: **regra é dado versionado, não
código**. E acrescenta um requisito de conferência: toda conta movimentada
precisa estar em alguma estrutura, ou o sistema avisa.

### 5. O lançamento carrega mais dimensões do que conta, valor e data

O que aparece no domínio, além do essencial:

| Dimensão | Para que serve |
| --- | --- |
| Centro de custo e departamento | Resultado por unidade; exige rateio que fecha com o valor da partida |
| Origem | Distinguir lançamento digitado de lançamento gerado por outro processo |
| Histórico padronizado | Texto montado a partir de modelo com variáveis, em vez de digitação livre |
| Participante | Terceiro envolvido, quando a obrigação exige |
| Localizador | Referência externa para reencontrar o lançamento depois |
| Conciliado | Estado que **trava** alteração e regeração |

### 6. Dado derivado precisa ser regerável, e conciliado trava regeração

Lançamento gerado a partir de outro (rateio, contabilização de extrato,
mutação do patrimônio líquido) precisa poder ser **refeito** quando a origem
muda. E a regeração **não pode** passar por cima do que já foi conciliado ou
ajustado à mão sem autorização explícita.

É o mesmo princípio que já adotamos para estorno: dado derivado não se edita, se
refaz — de forma rastreável.

## Capacidades mapeadas

Resumo. A classificação é a dos auxiliares, revisada por mim.

### Cadastros que sustentam a escrituração

| Capacidade | Situação no domínio |
| --- | --- |
| Empresa com histórico de alteração cadastral | Confirmada |
| Quadro societário com vigência | Confirmada |
| Contador responsável técnico, com registro no conselho | Confirmada |
| Plano de contas com máscara, sintéticas e analíticas | Confirmada |
| Conta com vigência e situação (evita uso de conta encerrada) | Confirmada |
| Vínculo com plano de contas referencial, por vigência | Confirmada |
| Estrutura de demonstrativos vinculada às contas | Confirmada |
| Histórico padronizado com variáveis | Confirmada |
| Departamento e centro de custo, com rateio | Confirmada |
| Lançamento padrão (modelo reutilizável de partidas) | Confirmada |
| Regra de contabilização de extrato bancário | Confirmada |
| Notas explicativas ligadas a contas e ao período | Confirmada |
| Participantes e responsáveis por obrigação | A conferir — depende da obrigação |
| Plano de contas compartilhado entre empresas do mesmo grupo | Decisão do Fred |
| Perfil de empresa (modelo para abrir cliente novo) | Hipótese |
| Matriz e filial com escrituração centralizada | Decisão do Fred |
| Conglomerado econômico, sociedade em conta de participação | A conferir — nicho |

### Movimento

| Capacidade | Situação no domínio |
| --- | --- |
| Lançamento por partidas dobradas, com topologia de lote | Confirmada |
| Livro caixa (escrituração simplificada) | Confirmada |
| Consulta e lançamento na mesma tela, com filtros amplos | Confirmada |
| Importação de extrato bancário com área intermediária | Confirmada |
| Conciliação bancária 1:1, 1:N e N:1, e desconciliação | Confirmada |
| Conciliação de conta até uma data, travando o retroativo | Confirmada |
| Lançamento orçado por competência, e comparação com o realizado | Confirmada |
| Rateio por centro de custo, que fecha com o valor | Confirmada |
| Rateio gerencial (segunda dimensão paralela) | Decisão do Fred |

### Saídas

| Capacidade | Situação no domínio |
| --- | --- |
| Diário, Razão, Balancete, Balanço, Livro Caixa | Confirmadas |
| Termo de abertura e encerramento, termo de transferência | Confirmadas |
| Emissão consolidada de livros com paginação amarrada | Confirmada |
| Carta de responsabilidade da administração | Confirmada |
| DRE, DLPA, DMPL, DFC, DVA, notas explicativas | Confirmadas |
| Análise vertical, horizontal e índices configuráveis | Confirmadas |
| Escrituração contábil digital e escrituração contábil fiscal | Existência confirmada; **leiaute e vigência a conferir** |

### Operação e conferência

| Capacidade | Situação no domínio |
| --- | --- |
| Consulta de saldo com rastreio até o lançamento de origem | Confirmada |
| Conferência de lotes com diferença entre débito e crédito | Confirmada |
| Apuração de custo de mercadoria e de produto vendido | Fórmula agregada confirmada; **critério de custeio a conferir** |
| Zeramento das contas de resultado no encerramento | Confirmada |
| Importação com validação em camadas antes de gravar | Confirmada |
| Regeração de lançamento derivado, preservando o conciliado | Confirmada |
| Alteração de lançamentos em massa | **Em tensão com as nossas regras — ver abaixo** |
| Exclusão em massa e eliminação de período | **Em tensão com as nossas regras — ver abaixo** |
| Cópia de configuração entre empresas do escritório | Confirmada |
| Backup, inclusive antes de operação destrutiva | Confirmada |

## Duas capacidades que entram em choque com as nossas regras

Este é o achado que mais importa para o desenho, e não é uma funcionalidade
faltando — é uma que **não devemos copiar como está**.

> **Atualização de 2026-09-13, depois da resposta do Fred.** Ele pediu as duas:
> alteração em massa (RC-51) e eliminação de período (RC-52). As duas serão
> implementadas, com desenho próprio — **DE-017** e **DE-018**. A recomendação
> abaixo de fazer *toda* correção por estorno estava errada por excesso, e o
> pedido dele me obrigou a rever: corrigir classificação antes de fechar o mês
> não é fato contábil novo, e transformar isso em estorno polui o livro. O que
> permanece é a exigência de **rastro** e a ordem de implantação: eliminar dado
> de cliente só depois de haver restauração provada.

### Alteração de lançamentos em massa

Localizar lançamentos por filtro amplo e sobrescrever campos de todos de uma vez.
O auxiliar registrou honestamente que **não encontrou descrição de rastro do
valor anterior** na parte que leu.

Nossa regra é explícita: lançamento efetivado não se altera; corrige-se por
procedimento rastreável. O `LancamentoContabil` impede alteração no próprio
`save()`.

**Recomendação:** oferecer a capacidade — a dor é real, corrigir 300 lançamentos
com a classificação errada à mão é inviável — mas implementá-la como **lote de
ajuste rastreável**: um conjunto de estornos e relançamentos vinculados ao
original, com autor, data e motivo, e não como `UPDATE` em cima do efetivado.
Custa mais linhas e preserva a contabilidade.

### Eliminação de período

Descartar lançamentos anteriores a uma data para reduzir volume. O próprio
material recomenda backup antes — indício de que não há como desfazer.

**Recomendação:** não implementar por ora. Se um dia houver demanda real de
volume, tratar como **arquivamento** (mover para armazenamento frio, com
inventário do que saiu e como voltar), nunca como exclusão, e condicionado a
período encerrado sem obrigação pendente, com papel autorizado e registro.

A mesma lógica vale para exclusão em massa. Onde o sistema de referência
apagaria, nós registramos.

## Conta retificadora, apresentação de saldo e implantação

Levantado em 2026-09-13 com material enviado pelo Fred — um balanço patrimonial
e o lançamento de implantação que o originou. Resolveu PE-37 e detalhou RC-53.

### O caso de referência que temos, com números conferidos

O balanço enviado traz o grupo do imobilizado assim:

| Classificação | Conta | Saldo |
| --- | --- | --- |
| `1.2.3.03.001` | Máquinas e equipamentos | 1.437,50 **D** |
| `1.2.3.04.001` | Veículos | 29.900,00 **D** |
| `1.2.3.07.003` | **(-)** Depreciações de máquinas e equipamentos | 2.074,18 **C** |
| `1.2.3` | **Imobilizado** | **29.263,32 D** |

Conferi por cálculo: `1.437,50 + 29.900,00 − 2.074,18 = 29.263,32`. Bate.

Isso é **caso de referência com resultado esperado**, e vale mais que qualquer
descrição: vira teste. É exatamente o cenário do achado 3 da auditoria, onde o
código atual produziria 33.411,68 em vez de 29.263,32.

### As três regras que esse caso estabelece

1. **A retificadora é conta de natureza contrária dentro do grupo.** Não é um
   valor negativo: é uma conta credora classificada dentro de um grupo devedor.
   O modelo atual já permite isso de propósito.
2. **O grupo soma pela natureza dele**, não pela dos filhos. Grupo devedor:
   débitos menos créditos das descendentes. É a correção de DE-020, agora com
   número de referência para provar.
3. **O saldo é apresentado em valor absoluto com indicador `D` ou `C`.** Nunca
   como número negativo. Um saldo credor de 2.074,18 se escreve `2.074,18 C`, e
   o nome da conta carrega o prefixo `(-)`.

A terceira regra é mudança de contrato para nós: hoje as saídas devolvem um
número que pode vir negativo. Vira **BL-77**.

### Implantação de saldos, o procedimento real

Um **único lançamento**, do tipo vários débitos para vários créditos, datado
**na data de encerramento do balanço do escritório anterior** — tipicamente
31/12. Cada conta de saldo devedor entra a débito, cada conta de saldo credor
entra a crédito, com histórico dizendo de que data é o saldo. A retificadora
entra pelo lado da natureza dela. O lançamento fecha como qualquer outro.

Duas consequências para o nosso desenho:

- A implantação **não precisa de modelo novo**. É um lançamento comum, com o
  cuidado de ser identificável como abertura.
- A validação certa **não** é "ativo igual a passivo mais patrimônio líquido"
  calculada por fora: é a igualdade entre débitos e créditos do próprio
  lançamento, que o sistema já exige de todo lançamento. O que falta é o
  assistente que evite digitar dezenas de linhas na mão e que recuse conta de
  resultado.

**Cuidado registrado pelo Fred:** lucros e prejuízos acumulados exigem tratamento
próprio, com um passo de transferência do resultado do período, e isso afeta
quem transmite a escrituração digital. É **PE-38** — regra contábil que precisa
vir dele com fonte, porque implantar errado contamina a primeira demonstração do
cliente novo.

### Outras confirmações das mesmas telas

- A conta é vinculada a **grupos de cada demonstração**, e a ausência de vínculo
  é **declarada** ("não faz parte"), não um campo vazio. A diferença importa:
  campo vazio é esquecimento, valor declarado é decisão.
- A conta tem **tipo explícito** (analítica ou sintética) além da hierarquia, e
  a **classificação contábil** é distinta do código de cadastro. Hoje nosso
  `Conta.codigo` acumula os dois papéis, e a classificação analítica/sintética é
  inferida do campo que autoriza lançamento — o que o achado 2 da auditoria
  mostrou ser frágil.
- Existe **origem própria** para o lançamento de transferência de resultado.
  Reforça BL-72.

## Integração fiscal → contábil: como a nota vira lançamento

Levantado em 2026-09-13 no manual público de escrita fiscal, a pedido do Fred,
depois de ele explicar que o caso real da regeração (RC-59) é este. É o desenho
que a DL-010 (fiscal) vai precisar, e por isso fica registrado aqui e não só lá.

### A amarração das contas

**A conta não está no produto nem no participante.** Ela vem de **duas**
configurações que se somam:

| Configuração | Define |
| --- | --- |
| **Classificação da operação** (o *acumulador* da tela que o Fred enviou) | As contas de débito e crédito do valor principal da nota, e as de frete, seguro, despesas acessórias, pedágio e parcelas |
| **Cadastro de cada imposto** | As contas de "a recolher" e "a recuperar" daquele imposto, com histórico próprio, mais devoluções e ajustes |

Isso confirma, do lado contábil, o que o [mapa fiscal](mapa-funcional-fiscal.md)
já dizia do lado do cálculo: **a classificação da operação é o centro do motor**.
A mesma escolha que determina o tratamento tributário determina a contabilização.

### O histórico é modelo, não texto

O texto do lançamento gerado vem de um **modelo com variáveis**, preenchidas com
dados do documento (número, participante, valor, data). Para nós: histórico não
é `CharField` copiado, é um serviço que resolve o modelo no momento da geração.

### Dois momentos, não um

1. Ao gravar a nota, monta-se a **prévia** do lançamento, visível e editável
   dentro da própria nota — é a aba Contabilidade da tela do Fred.
2. A **efetivação na contabilidade** é rotina em lote, por período.

Separar os dois importa: a prévia permite conferir antes de a contabilidade ser
tocada, e o lote permite reprocessar um período inteiro.

### A regeração, e o que faremos diferente

O sistema de referência regera por período e por tipo de movimento, com duas
proteções — não regerar o que foi alterado à mão e não regerar o que está
conciliado. **As duas são opção do usuário, não obrigação.**

Onde vamos divergir, deliberadamente:

| Ponto | Referência | DataLedger |
| --- | --- | --- |
| Preservar lançamento alterado à mão | Opção | **Padrão**, e desligar exige ato explícito |
| Preservar conciliado | Opção | **Padrão** |
| Período encerrado | Aviso | **Recusa** (RC-57) |
| Duplicidade | Confiada à rotina | **Chave natural** (documento de origem + tipo), para que reprocessar não duplique nem que a rotina falhe no meio |

A diferença toda está numa frase: no sistema de referência, o usuário desmarcar
uma caixa por engano custa a correção manual que ele fez. Aqui, não.

### Exclusão de nota contabilizada

Excluir a nota oferece, como **escolha explícita**, excluir também o lançamento
gerado — nunca implicitamente. Para nós, essa escolha fica condicionada às
mesmas regras: período aberto, lançamento não conciliado, com rastro.

### O que não foi possível confirmar

- O mecanismo pelo qual o sistema sabe que um lançamento foi alterado à mão.
  Nós resolveremos com campo próprio, não por inferência.
- A navegação do lançamento **de volta** à nota. Só a ida está documentada. Nós
  faremos os dois sentidos (BL-72) — sem a volta, uma conferência de balancete
  não chega ao documento que a originou.

## O que já existe no DataLedger

Cruzamento honesto, verificado por leitura de código em 2026-09-13
(`apps/contabilidade/`), não pelo README:

| Capacidade | Situação real |
| --- | --- |
| Plano de contas por empresa, hierárquico, com natureza e tipo | **Pronto** (`Conta`) |
| Distinção sintética/analítica | **Pronto**, pelo campo que autoriza lançamento |
| Lançamento por partidas dobradas, com igualdade validada | **Pronto** (`criar_lancamento`) |
| Imutabilidade do efetivado, com estorno único e rastreável | **Pronto e auditado** |
| Idempotência na criação, com impressão digital do conteúdo | **Pronto e auditado** |
| Precisão monetária e política de arredondamento | **Pronto** (DE-010) |
| Isolamento entre empresas | **Pronto e auditado** |
| Razão por conta | **Parcial** — existe, mas **sem filtro de período**: devolve tudo desde o primeiro lançamento |
| Balancete | **Parcial** — uma coluna de saldo acumulado; **sem período**, sem saldo anterior, sem débitos e créditos do período, sem totalização das sintéticas |
| Diário | **Não existe como livro.** O que há é a listagem cronológica da API, sem numeração, sem termo, sem totais por lote |
| Interface de contabilidade | **Não existe.** Só API: os templates cobrem empresas, login, painel e erros |
| Competência | **Não existe** — BL-15 |
| Rascunho x efetivado | **Não existe** — BL-10. Todo lançamento nasce efetivado |
| Período encerrado e reabertura | **Não existe** — BL-11 |
| Centro de custo, departamento, rateio | Não existe |
| Histórico padronizado, lançamento padrão | Não existe |
| Plano referencial e estrutura de demonstrativos | Não existe |
| Balanço, DRE e demais demonstrações | Não existe |
| Termos de abertura e encerramento, livros numerados | Não existe |
| Conciliação bancária e importação de extrato | Não existe |
| Conferência de lotes com diferença | Não existe |
| Saldo inicial de implantação | Não existe |

**Leitura desta tabela.** O núcleo — partida dobrada correta, imutável, isolada
por empresa e com precisão decimal — está sólido e auditado. É a parte difícil de
consertar depois, e está certa. O que falta é quase tudo que transforma esse
núcleo em **rotina de escritório**: período, saídas conciliáveis com a origem, e
uma tela para operar.

A lacuna mais desconfortável não é técnica: **não dá para usar a contabilidade
sem programar**. Enquanto isso for verdade, o Fred não consegue sequer testar o
sistema com um caso real.

## Obrigações e informativos citados pelo material (vigência a conferir)

Lista de nomes encontrados no material de **2018**, registrada como pendência,
**não** como requisito: escrituração contábil digital (ECD), escrituração
contábil fiscal (ECF), FCONT, balancetes setoriais de agências reguladoras,
arquivo para o Banco Central, arquivo de operadoras de saúde, prestação de contas
de partidos políticos, arquivo de tribunal de contas estadual, Sinco, rendimentos
e deduções de carnê-leão.

Várias provavelmente mudaram ou deixaram de existir. **Não afirmo quais**, porque
isso exige conferência em fonte oficial vigente, e essa conferência é do
responsável técnico.

> Este documento não constitui homologação contábil ou fiscal. Cálculo, leiaute
> ou obrigação só entram em código com regra confirmada em texto oficial
> vigente, caso de referência e validação profissional, conforme AGENTS.md §10.

## Regras verificáveis colhidas (candidatas a teste)

1. Lote com soma de débitos diferente da soma de créditos é recusado, e existe
   consulta que encontra qualquer lote torto já gravado.
2. Conta sintética nunca recebe lançamento direto.
3. Lançamento em competência encerrada é recusado no servidor; a reabertura
   exige papel autorizado e gera registro de auditoria.
4. Lançamento fora do período de trabalho segue a política configurada da
   empresa — nunca é aceito sem checagem.
5. Conta conciliada até uma data recusa inclusão, alteração e exclusão anteriores
   a essa data.
6. Rateio por centro de custo fecha exatamente com o valor da partida rateada.
7. O saldo de uma conta no Razão bate com a linha dela no Balancete do mesmo
   período — mesma origem, agregações diferentes.
8. Balancete e Balanço na mesma data de corte contam a mesma história, com o
   efeito do zeramento explicitado.
9. Escrituração digital só é gerada com 100% das contas movimentadas vinculadas
   ao plano referencial vigente; falta de vínculo bloqueia ou sinaliza.
10. Conta com lançamento não pode ser excluída.
11. Reclassificação de conta sintética propaga para as filhas, sem órfãs.
12. Apuração de custo satisfaz `estoque inicial + compras − estoque final`, e o
    lançamento gerado bate com o valor apurado.
13. Regeração de lançamento derivado não altera o que está conciliado sem
    autorização explícita.
14. Importação não grava registro classificado como erro, e reimportar o mesmo
    conteúdo não duplica.
15. Toda operação em massa registra quem fez, quando, sobre quantos itens, e é
    reversível ou reconstruível.

## Proposta de fatiamento

Ordem técnica sugerida, para o Fred ordenar por valor:

1. **Competência e período** (BL-15, BL-11) — nada de contabilidade séria
   funciona sem isso, e é pré-condição de qualquer fechamento.
2. **Saídas com período e conciliáveis** — Razão e Balancete com intervalo,
   saldo anterior, movimento e saldo final; Diário com totais por lote. É o que
   permite conferir o sistema contra a realidade.
3. **Tela de contabilidade** — plano de contas, lançamento, Razão e Balancete no
   navegador. Sem isso o sistema não sai do papel.
4. **Saldo inicial de implantação** — sem ele não se migra empresa nenhuma.
5. **Rascunho e efetivação** (BL-10) — o contador precisa digitar, conferir e só
   então efetivar.
6. **Conferência de lotes e consulta de saldo com rastreio**.
7. **Balanço e DRE**, com estrutura vinculada às contas.
8. Depois, por demanda: centro de custo, extrato e conciliação bancária,
   lançamento padrão, plano referencial e escrituração digital.

Os itens 1 a 4 formam uma fatia coerente: **é o mínimo para o Fred lançar uma
empresa real e conferir o resultado**. Recomendo que seja a próxima etapa de
contabilidade.

## Perguntas que dependem do Fred

### Respondidas em 2026-09-13

| Pergunta | Resposta | Onde virou requisito |
| --- | --- | --- |
| Fiscal ou contabilidade primeiro? | Contabilidade | RC-50 |
| Como entram os saldos iniciais? | Por lançamento dos saldos do balanço patrimonial | RC-53, BL-63 |
| Centro de custo é usado? | Sim, por parte das empresas; precisa cadastro | RC-54, RC-55, BL-67 a BL-69 |
| Livros precisam de numeração? | Sim | RC-56, BL-70 |
| Alteração em massa? | Implementar | RC-51, DE-017, BL-65 |
| Eliminação de período? | Implementar | RC-52, DE-018, BL-66 |

### Ainda abertas

1. Como é o fechamento e a reabertura de período no escritório hoje: quem
   autoriza, o que é exigido, com que frequência acontece? (PE-05)
2. Para que serve a eliminação de período: volume, empresa que saiu da carteira,
   ou exclusão por LGPD? (PE-34)
3. Na alteração em massa, quais campos precisam ser corrigidos na prática, e com
   que frequência? (PE-35)
4. Existe empresa na carteira com matriz e filiais em escrituração centralizada?
   (PE-30)
5. Plano de contas compartilhado entre empresas do mesmo grupo é necessário?
   (PE-31)
6. Quais das obrigações listadas o escritório **de fato entrega** hoje? (PE-32)
