# DL-048 — Contabilidade anual: estrutura de demonstração ligada à conta (CTB-12 a CTB-17)

**Estado:** em desenvolvimento
**Nível de risco:** 1 — são demonstrações contábeis entregues ao cliente (dinheiro, livro e documento).
**Origem:** ordem direta do Fred em 2026-09-28, escolhendo a **opção A** do mapa de
paridade ([DL-047](DL-047-mapa-de-paridade-funcional.md)) — fechar a Contabilidade anual
antes de abrir o Fiscal.
**Itens do plano de paridade:** [contabilidade.md](../projeto/paridade/contabilidade.md),
CTB-12 a CTB-17.

## Decisões do Fred (2026-09-28, registradas antes de qualquer código)

| # | Decisão | Consequência |
| --- | --- | --- |
| 1 | **DLPA isolada E DMPL** — as duas demonstrações saem como documentos próprios, cada uma com sua tela. | CTB-13 (DLPA) e CTB-14 (DMPL) são entregas separadas, não uma derivada da outra. A DLPA deixa de ser "recorte da DMPL" e ganha estrutura própria. |
| 2 | **Fonte normativa confirmada pelo agente** antes de codificar. | A NBC TG 26 / Lei 6.404/76 deve ser lida em Planalto/CFC, a fonte registrada em [requisitos.md](../projeto/requisitos.md) com **data de consulta**, e só então o código nasce. Nenhum número ou linha de demonstração vira constante sem isso (AGENTS.md §10). |

## Respostas do Fred (2026-09-28) — desbloqueiam CTB-13 a CTB-17

### RC-137 · Tipos de reserva (define colunas da DMPL e linhas da DLPA)

**Reservas de LUCROS** — constituídas a partir do lucro líquido:

| Reserva | Origem / critério |
| --- | --- |
| **Legal** | Obrigatória por lei (Lei 6.404/76 art. 193) — já confirmada na fonte oficial |
| **Estatutária** | Regras do próprio estatuto: finalidade, critério de cálculo e limite máximo |
| **Para Contingências** | Compensar perda provável em exercício futuro (perda esperada, processo judicial iminente) — não distribuir dividendos que farão falta depois |
| **De Incentivos Fiscais** | Parcela do lucro decorrente de doações ou subvenções governamentais para investimento (isenções estaduais e federais) |
| **De Retenção de Lucros** (ou para Expansão) | Projeto de investimento ou orçamento de capital previamente aprovado pela assembleia — retém o lucro para financiar crescimento |
| **De Lucros a Realizar** | Lucro contábil sem realização financeira (venda a prazo de longo prazo, equivalência patrimonial) — adia o pagamento de dividendos obrigatórios sobre lucro ainda não realizado |

**Reservas de CAPITAL** — **não** vêm do lucro operacional, entram direto no PL e **não transitam pela DLPA** (não passam pelo lucro líquido do exercício):

| Reserva | Origem |
| --- | --- |
| **Ágio na Emissão de Ações** | Valor pago acima do valor nominal das ações emitidas |
| **Alienação de Partes Beneficiárias / Bônus de Subscrição** | Valores recebidos na venda desses títulos mobiliários |

**Estrutura de apresentação, definida pelo Fred:**

| | Como aparece | Função técnica |
| --- | --- | --- |
| **DMPL** | Cada tipo de reserva tem **coluna própria** (ex.: "Reserva Legal", "Reserva Estatutária") | Mostra saldo inicial, mutações (aumentos/reduções) e saldo final de cada conta do PL |
| **DLPA** | Aparecem como **linhas de destinação do lucro** (ex.: "(-) Transferência para Reserva Estatutária") | Demonstam como o saldo de Lucros Acumulados foi distribuído para abastecer as colunas de reservas do PL |

⚠️ **Consequência de modelagem:** o "tipo de evento" da DLPA nasce da **destinação** e a coluna da DMPL é a **contrapartida** — são o mesmo fato visto por dois lados. Implementar com a MESMA leitura estruturada de eventos, que é justamente o que mitiga o risco de "duas lógicas divergentes" apontado pelo plano de paridade.

### RC-138 · DFC — **os dois métodos** (direto e indireto)

⚠️ O método **direto** depende de extrato/conciliação bancária (**CTB-40/CTB-41**), que **não existe** e está fora desta etapa. Entregar o **indireto** agora e abrir CTB-40/41 como dependência declarada para o direto. Nunca inferir "é banco, então é caixa" — lançamento de ajuste, provisão e reclassificação passa pela conta banco sem ser fluxo real.

### RC-139 · ORA e DVA — **exige os dois**

CTB-16 (DRA) e CTB-17 (DVA) **entram na etapa**, não ficam em espera. DVA é obrigatória para companhia aberta (Lei 6.404/76 art. 176, V) e a carteira tem quem exija.

### RC-140 · Compensação de lucros e prejuízos acumulados — **SIM, o escritório compensa**

⚠️ **Falta um detalhe antes de implementar a linha:** a resposta confirma que a compensação existe, mas não diz **como** — a PE-38 pergunta se é todo mês, no encerramento anual, ou lançamento à mão. Esse detalhe define quando a linha aparece na DLPA e como se liga ao CTB-24 (encerramento do exercício). **Confirmar o mecanismo antes**; em caso de dúvida, entregar a linha declarada como pendência em vez de presumir (regra do CTB-12).

## Por que a ordem é esta

O mapa de paridade diz que a Onda 1 é a **estrutura de demonstração ligada à conta**:
DRE, DLPA, DMPL, DFC e DVA não são relatórios com fórmula fixa — são estruturas de
grupos, e a conta é **vinculada** a esses grupos. O DataLedger já aplica isso para o
Balanço (`classificacao_patrimonial`, CTB-09) e para a DRE (`classificacao_dre`,
CTB-10). CTB-12 é repetir esse padrão; CTB-13 a CTB-17 são cada um com seu próprio
enum de linhas.

## Etapas

### 1. CTB-12 — Estrutura de demonstração ligada à conta (base)

O mecanismo comum reaproveitado pelos itens seguintes: campo fixo na conta (como
`classificacao_patrimonial` e `classificacao_dre` já são), apuração que soma pela
estrutura, e tela que **declara** o que falta classificar em vez de presumir.

- **Regra que vira teste:** nenhuma conta é classificada por inferência de código ou
  nome; a apuração relata pendência em vez de presumir.
- **Não copiar:** a estrutura totalmente configurável por empresa (do sistema de
  referência) **substitui** este padrão se um dia for pedida — não conviver com os dois
  (AGENTS.md §8).
- **Critério de aceite:** cada item seguinte define os seus; o comum é "nenhuma conta
  classificada sem ação explícita do usuário, e a apuração sempre relata o que falta".

### 2. CTB-13 — DLPA (Demonstração dos Lucros ou Prejuízos Acumulados)

Movimentação da conta de lucros/prejuízos acumulados no período: saldo inicial +
lucro do exercício − destinações (reservas, dividendos) = saldo final.

- **Fonte normativa:** confirmar a NBC TG 26 item 106 e a Lei 6.404/76 na fonte
  oficial **antes** de escrever o enum de linhas. Registrar em `requisitos.md`.
- **Dados:** a demonstração é uma **leitura estruturada** dos lançamentos já
  existentes (o zeramento gera o "lucro do período") — não um modelo de armazenamento
  novo, mesmo espírito da DRE.
- **Regra que vira teste:** saldo final = saldo inicial + lucro do exercício −
  destinações; cada linha precisa vir de lançamento identificável.
- ⚠️ **Não implementar o cálculo da reserva legal** sem conferir a Lei 6.404/76
  art. 193 na fonte oficial e validar com o Fred (limite de 20% do capital social,
  5% do lucro líquido).
- **Critério de aceite:** saldo final da DLPA bate com o saldo da conta de
  lucros/prejuízos acumulados no Balanço da mesma data; emissão recusada enquanto
  houver movimento não classificado (mesmo padrão de CTB-09/CTB-10).
- **Classe do documento:** demonstração — identificação obrigatória em **cada página**
  (NBC TG 26 item 52).

### 3. CTB-14 — DMPL (Demonstração das Mutações do Patrimônio Líquido)

➡️ **Planejada e em execução como [DL-061](DL-061-dmpl.md)** (01/10/2026), com a RC-151
(linha automática pela contrapartida) e a HI-50 (alíneas "c" e "d" do art. 182, §1º).

Uma coluna por conta do PL, uma linha por tipo de evento (saldo inicial, aumento de
capital, lucro do exercício, constituição de reserva, distribuição, saldo final).

- **Critério de aceite:** o total da DMPL bate com o Patrimônio Líquido do Balanço da
  mesma data. É a conciliação que impede a demonstração de "fechar sozinha" errada.
- **Classe do documento:** demonstração.

#### ⚠️ Base normativa CORRIGIDA em 29/09/2026 — a premissa desta seção estava errada

A versão anterior citava o **art. 176 da Lei 6.404/76** como a base da DMPL. **A fonte
oficial desmente isso**, e o AGENTS.md §3.1 manda reabrir o critério de aceite com o
Fred em vez de comprar mais uma rodada de auditoria — foi o que fizemos, antes de
codificar.

| O que se acreditava | O que a fonte diz (Planalto, consolidado, 29/09/2026) |
| --- | --- |
| A DMPL é exigida pelo art. 176 | **O art. 176 não lista a DMPL.** Inciso III é a DRE; inciso V é a DVA (*"se companhia aberta"*). A expressão *"demonstração das mutações do patrimônio líquido"* aparece **uma única vez** em todo o diploma: no **art. 186, §2º** — e como **faculdade**: a DLPA *"poderá ser incluída"* nela. |
| A estrutura da DMPL está no art. 178, §2º ou no art. 179 | **Não.** Ambos são do **Balanço Patrimonial** (grupos do passivo e classificação do ativo). |

**A base real, em três peças — corrigida em 29/09/2026 por ordem do Fred:**

- **Competência para editar a norma:** o próprio preâmbulo da NBC TG 51 traz o
  fundamento, e ele é a chave de todo o arcabouço — *"com fundamento no disposto na
  alínea **"f" do Art. 6º do Decreto-Lei n.º 9.295**, de 27 de março de 1946,
  alterado pela Lei n.º 12.249, de 11 de junho de 2010"* (texto do PDF oficial do
  CFC, lido nesta sessão).
- **Obrigação:** norma técnica. A DMPL integra o conjunto completo de demonstrações
  contábeis — **NBC TG 26 (R5), item 10**, e a partir de 01/01/2027 a **NBC TG 51**.
  ⚠️ **A Lei 11.638/2007 NÃO criou a DMPL** — ela trocou a DOAR pela DFC e criou a DVA.
  A Lei 6.404/76 desonera expressamente a DFC (art. 176, §6º) e a DVA (item V) e
  **nunca** desonera a DMPL.
- **Estrutura:** norma técnica. Itens **106 a 110 e 106B** da NBC TG 26 (R5), ou
  **107 a 112 e 111A** da NBC TG 51, conforme a vigência.

**Quem deve emitir a DMPL, por porte:**

| Entidade | Situação |
| --- | --- |
| Companhia fechada e aberta | obrigatória — NBC TG 26 (R5) item 10; a partir de 2027, NBC TG 51 |
| Pequena empresa | NBC TG 1000 — **admite a DLPA no lugar da DMPL** em certas condições |
| Microempresa | ITG 1000 — **não obrigatória** |

⚠️ **Lacuna declarada, não preenchida:** para **companhias abertas**, além da norma
técnica, incide o **ato da CVM que aprovou o CPC 26**, que **não foi lido em fonte
oficial** nesta sessão. Registrar como pendência — **não inventar** o número do ato.

#### A conciliação com o Balanço: exigência DERIVADA do item 106(d), não citação literal

A versão anterior desta seção dizia que a conciliação *"não é uma citação de norma"*.
**Isso era incompleto, e foi corrigido em 29/09/2026.**

O **item 106(d) da NBC TG 26 (R5)** — e o **107(c) da TG 51**, seu equivalente — exige,
para **cada componente do patrimônio líquido**, *"uma conciliação entre o valor contábil
no início e no final do período"*. O saldo final dessa conciliação é, por definição, **o
saldo contábil do componente** — que é o mesmo número que o Balanço Patrimonial
apresenta na mesma data. A reconciliação entre demonstrações não é preferência do
produto: é **exigência derivada do item 106(d)** somada à **consistência do conjunto**,
já que duas demonstrações que discorrem não formam o conjunto completo de que fala o
item 10.

⚠️ **O que continua verdadeiro:** nenhum item diz, em letra, *"o saldo final da DMPL
deve ser igual ao do Balanço"*. A reconciliação é **derivada**, e o código deve
descrevê-la exatamente assim — como exigência decorrente do 106(d) e da consistência
do conjunto, **não** como citação literal de um item que não existe.

#### ⚠️ Uma coluna por TIPO de reserva é escolha de desenho, não obrigação

A RC-137 do Fred define uma coluna por tipo de reserva. A reconferência mostra que:

- **A lei** (art. 178, §2º, III) e **as normas** (item 106B da R5 / **111A** da TG 51)
  mandam **seis GRUPOS genéricos**: capital social; reservas de capital; ajustes de
  avaliação patrimonial; reservas de lucros; ações ou quotas em tesouraria;
  prejuízos acumulados; e, *"se legalmente admitidos"*, os lucros acumulados.
- **O item 106(d) da R5 / 107(c) da TG 51 diz "no mínimo"** — é o que abre a janela
  para rubricas extras, como uma coluna por tipo de reserva.
- O **ITG 1000, Anexo 4** (modelo de DMPL da **pequena empresa**; a microempresa tem
  DLPA, Anexo 10) traz **uma coluna por GRUPO**, não por tipo.

⚠️ A coluna por tipo de reserva é, portanto, **desenho permitido e boa prática de
mercado — não derivação normativa**. No código ela é `permissiva`; a exigência de
apresentar os sete itens acima é que é `obrigatoria` (item 111A da TG 51). Promover a
primeira ao posto da segunda é a mesma classe de defeito do BL-514: garantia que o
produto não dá, descrita como se desse.

#### Colunas de reservas de CAPITAL que a RC-137 não listou

⚠️ **CORRIGIDO em 01/10/2026 (RC-152):** "prêmio na emissão de debêntures" e "doações e
subvenções para investimento" foram **revogadas** pelo art. 10 da Lei 11.638/2007 e
**não** entram na DMPL. A afirmação "as duas primeiras entram", abaixo, está errada.

⚠️ **Pendência para a DMPL.** A RC-137 lista ágio na emissão de ações e
alienação de partes beneficiárias/bônus de subscrição. A lei tem **três** reservas de
capital que ficaram de fora, e são coluna da DMPL por norma (item 111A):

| Reserva | Dispositivo |
| --- | --- |
| Prêmio na emissão de debêntures | LSA art. 182, §1º, "c" |
| Doações e subvenções para investimento | LSA art. 182, §1º, "d" |
| Correção monetária do capital realizado | LSA art. 182, §2º |

⚠️ A terceira é **letra morta pelo mesmo fundamento** que tirou a correção monetária
da DLPA (Lei 9.249/95, art. 4º, p.ú.) e **não deve virar coluna** sem o mesmo
raciocínio ser escrito. As duas primeiras entram.

#### Vigência: a DMPL tem DUAS versões de fonte

Texto da cláusula de vigência da NBC TG 51, **verbatim do PDF oficial do CFC**
(consultado em 29/09/2026):

> *"Esta norma entra em vigor na data de sua publicação, aplicando-se aos exercícios
> iniciados a partir de 1º de janeiro de 2027, e revoga a NBC TG 26, aprovada pela
> Resolução CFC n.º 1.185/2009, a NBC TG 26 (R1), a NBC TG 26 (R2), a NBC TG 26 (R3),
> a NBC TG 26 (R4) e a NBC TG 26 (R5)… Brasília, 13 de novembro de 2025."*

E o item C1, sobre o alinhamento pleno ao IFRS:

> *"C1 A vigência desta Norma será estabelecida pelos órgãos reguladores que o
> aprovarem, sendo que, para o pleno atendimento às normas internacionais de
> contabilidade, a entidade deve aplicar esta Norma para períodos anuais com início
> em ou após 1º de janeiro de 2027."*

⚠️ **Datas — o que está confirmado e o que ainda não está:**

| Data | Valor | Situação |
| --- | --- | --- |
| Ato (resolução) | **13/11/2025** | ✅ **CONFIRMADO** — cabeçalho do PDF oficial e fecho da cláusula de vigência |
| Aplicabilidade | **exercícios iniciados a partir de 01/01/2027** | ✅ **CONFIRMADO** — cláusula de vigência e item C1 |
| Publicação no DOU | ⚠️ **em divergência** | ver abaixo |

⚠️ **Divergência registrada, não resolvida por escolha:** o campo *"Data de Publicação
no Diário Oficial da União"* da ficha da resolução no Sistema de Resoluções do CFC
(`www2.cfc.org.br/sisweb/sre/detalhes_sre.aspx?Codigo=2025/NBCTG51`) registra
**25/02/2026**; o Fred indicou **22/12/2025** em 29/09/2026. **Nenhuma das duas foi
confirmada em segunda fonte oficial.** Como a cláusula diz *"entra em vigor na data de
sua publicação"*, a data importa — mas **não altera nenhuma conclusão**: em qualquer
das duas, a aplicabilidade é **01/01/2027**. Pendente de conferência no DOU; não
influir no código.

⚠️ **Correção registrada:** a versão anterior desta seção afirmava *"revogada em
25/02/2026"* como se essa fosse a data do ato. **Não é** — o ato é de **13/11/2025**;
25/02/2026 é, no que foi lido, a data de publicação no DOU. O que a revogação
significa, em_si, e a data a partir da qual a nova norma se aplica, estão confirmados
acima e **não mudam**.

**Consequência para o código (decisão do Fred, 29/09/2026 — OBRIGATÓRIA):** o item
citado no código **varia com a data de início do exercício**, e o produto **deve
prever a adoção antecipada** da NBC TG 51. É o DE-010 (norma versionada por vigência)
aplicado ao enum de linhas da DMPL.

### 4. CTB-15 — DFC (Demonstração dos Fluxos de Caixa)

Direto e indireto, por atividade.

- ⚠️ **O método direto depende de extrato/conciliação bancária (CTB-40/CTB-41), que
  não existem.** Conferir no item o que é viável agora; o restante entra como
  limitação declarada, nunca como número inventado.

### 5. CTB-16 — DRA (Demonstração do Resultado Abrangente)

Lucro líquido + outros resultados abrangentes.

### 6. CTB-17 — DVA (Demonstração do Valor Adicionado)

Riqueza gerada e distribuída; fecha em si mesma. É o item de menor urgência contábil
da onda.

## Restrições que valem em toda a etapa (AGENTS.md)

- Dinheiro em `Decimal`, nunca float; escala e arredondamento explícitos.
- Demonstração é documento **classe demonstração**: o bloco de identificação do
  emitente é obrigação (NBC TG 26 item 51) e repete em cada página (item 52).
- Nenhuma linha de demonstração nasce de inferência — o que não está classificado é
  **declarado como pendência**, e a emissão é recusada.
- Autorização no servidor; isolamento por empresa e escritório; trilha de auditoria.
- Teste de regra contábil não se corta (DE-063); caso de referência calculado à mão
  para cada demonstração.

## Critérios de aceite da etapa inteira

1. Cada demonstração tem apuração determinística, conciliável com os lançamentos.
2. As conciliações cruzadas batem: DLPA ↔ Balanço, DMPL ↔ PL do Balanço,
   DRA ↔ DRE, DVA fecha em si mesma.
3. Emissão recusada com a lista do que falta classificar (nunca esconde).
4. Identificação do emitente medida no navegador pela CI (job `Medir identificação do
   emitente no navegador`).
5. Isolamento entre empresas testado nos dois sentidos.
6. Casos de referência com valores calculados à mão, aprovados pelo Fred.

## Bloqueio antes do código

A fonte normativa da DLPA e da DMPL precisa ser confirmada e registrada em
`requisitos.md` **antes** do primeiro commit funcional. É a primeira tarefa desta
etapa.

✅ **Cumprida em 28/09/2026** — ver "Fontes normativas das demonstrações
contábeis — DL-048" em [requisitos.md](../projeto/requisitos.md), com a
descoberta de que a base da DLPA é a Lei 6.404/76 (art. 176, II e art. 186),
não a NBC TG 26 item 106 nem a Lei 11.941/2009.

✅ **Reconferida em 29/09/2026, agora COM rede** (o bloqueio anterior — "sem rede
nesta máquina" — deixou de existir). Duas frentes de pesquisa em fonte oficial, com
os textos baixados por download direto e transcritos, mais verificação independente
própria no cadastro de resoluções do CFC:

- **Vigência fechada:** a NBC TG 26 (R5) está **revogada** desde 25/02/2026 pela
  **NBC TG 51** (DOU 25/02/2026, correlata ao IFRS 18), que se aplica a períodos
  anuais com início **em ou após 01/01/2027** (item C1). Verificado nos **dois
  sentidos** no sistema de resoluções do CFC: a ficha da TG 51 lista a revogação da
  R5, e a ficha da R5 registra `em vigor: NAO` / `revogada: SIM`.
- **A pendência "mapear os itens da TG 51" está FECHADA** (ver [requisitos.md](../projeto/requisitos.md)):
  identificação = **item 27**, (a)–(e) idênticos; DMPL = **itens 107 a 112 e 111A**.
- **Lei 6.404/76:** art. 186, I–III e §§1º/2º **confirmados verbatim**, sem nota de
  alteração desde 1976; art. 176, 178, 179, 187, 193 e a Lei 9.249/95 (art. 4º, p.ú.)
  também.
- **A decisão de 29/09 sobre a correção monetária se CONFIRMA** com fundamento
  oficial: a Lei 9.249/95, art. 4º, parágrafo único, veda *"qualquer sistema de
  correção monetária de demonstrações financeiras, inclusive para fins societários"*;
  e a **mesma lei**, no art. 5º, retirou a conta da DRE (art. 187, IV) sem tocar no
  art. 186 — descuido legislativo, não opção do produto. ⚠️ **Correção**: a referência
  a "Lei 9.492/95" que circulava na sessão anterior é **errada** (a Lei 9.492 é de
  1997, sobre protesto de títulos); o parágrafo único **nunca foi alterado**.
- ⚠️ **Ressalva que o texto acima não faz e o produto precisa saber:** a vedação é sobre
  **nova atualização**. Saldo histórico de 31/12/1995 pode e deve ser **carregado e
  apresentado dentro do "saldo do início do período"** (art. 186, I) — **não** em
  linha própria, e **não zerado**.
- **Quatro premissas foram desmentidas** e estão corrigidas nas seções acima: a DMPL
  não está no art. 176; o §2º do art. 187 está revogado (Lei 11.638/2007) e não serve
  de requisito; "reserva de lucros a realizar" não tem lastro normativo; e a
  RC-137 omitiu três reservas de capital do art. 182.

## Fatia CTB-12 + CTB-13 (DLPA) — codada e testada em 2026-09-28

Branch `feat/dl-048-dlpa`. **Nível 1:** o que falta para a etapa fechar, nesta
ordem: (a) **auditoria independente** (obrigatória — **em curso** desde
29/09/2026); (b) correção da auditoria e reconferência; (c) **entrega do
conteúdo na `main`** e merge.

⚠️ **O PR #58 foi MESCLADO e o conteúdo NÃO está na `main`** (medido em
29/09/2026). O #57 (plano) foi mesclado na `main` às 11:17:33 e o #58 foi
mesclado na base `docs/dl-048-plano` às 11:17:52, 19 segundos depois — o
caso que o `AGENTS.md` §6 descreve: *encadeado não se mescla na branch
intermediária depois de a dependência já ter entrado*. O GitHub diz
"MERGED"; a `main` não tem nenhum dos 3 commits da fatia. A CI do #58 ficou
VERDE nos 4 jobs (commit `7e78c8f`) **contra a branch do plano**, o que
confirma o defeito: ela mediu o código, não o destino. A CI é verde **e o
produto não mudou na `main`** — é o exemplo mais limpo de por que "CI verde"
e "entregue" não são a mesma coisa. Enquanto (a)–(c) não acontecem, a
etapa **NÃO** é "integrada".

### Entrega na `main` (29/09/2026)

- `origin/main` tem **1 commit** a mais que a branch (o merge do #57); a
  branch da fatia tem **3 commits** fora da `main`.
- O merge `main ← feat/dl-048-dlpa` é **limpo** (`git merge-tree`, sem
  conflito) e o diff são exatamente as **19 arquivos** da fatia — nenhum
  arquivo alheio entra com ele.
- Regressão **medida por comparação nominal** contra um *worktree* limpo de
  `origin/main`, mesmo comando e mesmo recorte: `apps/contabilidade` dá
  **54 failed nos dois, os mesmos 54**, com **+41 passed**; `apps/core` dá
  **13 failed nos dois, os mesmos 13**, com **+1 passed**. A fatia não
  introduz nenhuma falha. `ruff check`, `ruff format --check` (313
  arquivos), `manage.py check` e `makemigrations --check` limpos.
- ⚠️ **A fonte normativa não foi reconferida em 29/09**: sem rede nesta
  máquina, a conformidade com o art. 186 **não foi revalidada**. A
  confirmação de 28/09/2026 em [requisitos.md](../projeto/requisitos.md)
  segue de pé por ser de sessão anterior, não por ter sido checada agora.
- ✅ **Resolvido em 29/09/2026 (decisão do Fred): a rubrica "Correção
  monetária do saldo inicial" (art. 186, I) foi REMOVIDA** do enum, da
  apuração e do texto emitido. Fundamento: a Lei 9.249/95, art. 4º, p.ú.,
  vedou o sistema de correção monetária da moeda — em exercício de 2026 a
  linha é letra morta, e linha que não recebe movimento só ocupa espaço no
  documento do cliente. O membro saiu inteiro (a migração 0012 nunca entrou
  na `main`, então não há valor gravado em ambiente compartilhado) e a
  guarda `contas_com_classificacao_dlpa_desconhecida` garante que um valor
  órfão **vete a emissão** em vez de sumir em silêncio. A nota está em
  [requisitos.md](../projeto/requisitos.md), sem corrigir o sentido do texto
  normativo. **Dois testes novos** cobrem o contrato: a rubrica ausente do
  enum, das linhas e do texto, com a identidade fechando **sem** a chave; e
  o valor órfão vetando a emissão.

### Decisões de implementação (registradas para revisão; todas reversíveis)

| # | Decisão | Por quê |
| --- | --- | --- |
| D1 | **Conta sujeito = `classificacao_dlpa = "lucros_ou_prejuizos_acumulados"`; podem ser VÁRIAS contas** (o caso "Lucros Acumulados" + "(-) Prejuízos Acumulados" em plano separado). | CTB-12 manda campo fixo na conta (molde `classificacao_patrimonial`/`classificacao_dre`), não parâmetro do zeramento: a demonstração não depende de quem configurou o zeramento, e as duas contas somam pelo mesmo lado (D2). |
| D2 | **Efeito de um item sobre o resultado acumulado = crédito − débito, independente da natureza cadastrada.** | É idêntico para a credora (cr − db) e para a retificadora devedora (o −(db − cr) do PL é cr − db): as duas formas da conta existir convergem sem regra de translação. |
| D3 | **A linha vem da `classificacao_dlpa` da CONTRAPARTIDA do lançamento** — sem classificação, a apuração declara pendência e a emissão é recusada. | "Nenhuma conta classificada por inferência" (CTB-12): a contrapartida é quem diz que evento moveu os lucros (zeramento, reserva, dividendo…); o produto não adivinha. |
| D4 | **A DIREÇÃO do movimento decide reversão (art. 186, II) × transferência (art. 186, III)** para a MESMA conta de reserva. | O cadastro só diz "é reserva"; reduzir lucros é destinação, aumentar é reversão. Guarda derivada de uma propriedade do movimento, não de lista (AGENTS.md §8). |
| D5 | **Sem herança: a classificação vale para a conta EXATA que participa do lançamento** (diferente da DRE). | Subconta sem classificação vira pendência nomeada, com link para classificar — nunca valor presumido do ancestral. Se a herança for pedida, ela SUBSTITUI esta regra (AGENTS.md §8). |
| D6 | **Período = EXERCÍCIO (01/01, ano civil, HI-28) até a competência pedida**; saldo inicial em 31/12 do ano anterior; navegação por mês, mesma gramática da DRE. | A DLPA é demonstração do exercício; o seletor de mês controla "até quando", nunca um período livre. |
| D7 | **A compensação de lucros/prejuízos (PE-38/HI-26, ainda com o Fred) não é presumida.** Lançamento entre as DUAS contas sujeito tem efeito líquido ZERO e some da demonstração. | A leitura é neutra ao mecanismo que o escritório venha a usar: não inventa transferência que não foi lançada, nem esconde a que foi. |
| D8 | **Tela primeiro, API depois.** Nesta fatia: `dlpa` e `conta_classificacao_dlpa` (2 rotas web); `DlpaView` (GET) + `ContaClassificacaoDlpaView` (PATCH) + `ContaSerializer.classificacao_dlpa` são a fatia seguinte. | Mantém o escopo da fatia revisável; as contagens de rota de `test_dl038_recusa_livro_caixa.py` já registram 21 web / 15 API com o histórico. |
| D9 | **Conciliação DLPA ↔ Balanço por caminho independente**: a apuração soma `ItemLancamento` por conta exata; a conferência usa o `saldo` do motor do Balancete (`apurar_saldos`) em `data_fim`, credora `+`/devedora `−`. | É a comparação entre dois caminhos que prova o número (critério de aceite). ⚠️ **Reescrita em 29/09/2026** (achado 9 da auditoria): a versão original dizia "conta sujeito deve ser FOLHA" como se fosseimposta, e não é — `Conta.clean()` aceita classificar uma conta que já tem filha, e **a estrutura que o próprio `zerar_resultado` cria tem sujeito com subconta** (a conta "3" dos lucros acumulados com a "3.1" do resultado abaixo). Prometer a restrição num texto que o produto não aplica é pior que não prometer. O que o produto **faz** é detectar a consequência: subconta que se move faz a conta exata divergir da consolidada, a `diferenca_de_fechamento` acende e **veta a emissão** — coberto por teste. Subconta parada não diverge e emite com o número certo. |

### Critérios cobertos e evidência (2026-09-28)

Testes novos: `apps/contabilidade/tests/test_dl048_dlpa.py` — **39 testes**:
caso de referência do plano (13.750,00), identidade
`saldo inicial + Σ linhas = saldo final`, conciliação com o Balanço, ordem dos
incisos do art. 186, rastreabilidade (cada linha com seus lançamentos),
estorno, compensação neutra, isolamento, as três pendências (sem conta sujeito;
movimento sem classificação; classificação fora do enum) e o aviso de
resultado não zerado, cadeia `zerar_resultado` → linha da DLPA, permissão 403,
isolamento 404, veto com link só para quem escritura, identificação do item 51
na página emitida, hub/menu/plano de contas e as duas telas de classificação
com trilha.

Guardas existentes re-executadas nesta sessão: `test_dl019_varredura_de_
restricoes` (constraint `ck_conta_classificacao_dlpa_nao_vazia` registrada),
`test_dl038_recusa_livro_caixa` (21/15), `test_documentacao_do_estado`,
`test_dl024_atalhos_e_acessibilidade` (cobertura das duas rotas novas).
`ruff check`, `ruff format --check`, `manage.py check` e
`makemigrations --check` aprovados.

⚠️ **Não executado nesta sessão:** a medição no navegador real
(`scripts/medir_identificacao_do_emitente.py` — a DLPA entrou no piso de
classe 2 e o cenário de medição semeia a conta sujeito) e o
`validate-docs.ps1`; os dois rodam na CI.

### Limitações declaradas da fatia

- API sem a DLPA (D8) — paridade é a próxima fatia.
- Sem herança de classificação (D5); conta sujeito deve ser folha (D9).
- A rubrica "Correção monetária do saldo inicial" (art. 186, I) **não é
  emitida** — decisão do Fred em 29/09/2026, com a Lei 9.249/95, art. 4º,
  p.ú., como fundamento (moeda vedada; letra morta em exercício posterior).
- Rótulo do enum "Reserva de contingências" (RC-137 escreve "Para
  Contingências") — mesma reserva; a frase invertida não cabe no título
  "Transferência para reserva …" sem soar errado.
- Dividendos só aparecem na DLPA quando o lançamento movimenta a conta
  sujeito; escrituração que distribui sem tocar os lucros acumulados não gera
  a linha (o saldo continua conciliado — a apuração cobre todo o movimento da
  conta sujeito).

### Limitações que a auditoria de 29/09/2026 deixou em aberto

A [rodada 1 da auditoria](../auditorias/2026-09-29-dl-048-dlpa-rodada-1.md)
reprovou. Os achados de **alta** foram corrigidos (o gate da conciliação com o
Balanço ganhou quatro testes; o diagnóstico de classificação órfã na conta
sujeito foi corrigido; os dois testes fracos foram reescritos) e **o restante
também**, por ordem do Fred em 29/09/2026: o veto da conciliação passou a
nomear as contas, a tela discrimina a origem de cada linha (achado 5), o
formulário de conta nova ganhou cobertura (achado 16) e a decisão D9 foi
reescrita para dizer o que o produto faz em vez do que ele não impõe
(achado 9). Ficam declarados, e não escondidos:

- **Achado 8 — o snapshot `REPEATABLE READ` não tem teste.** O comando só é
  emitido fora de transação aberta, e `pytest.mark.django_db` abre uma: a
  proteção existe no código e **nenhum teste** a exercita. O modelo a portar é
  `test_a5_com_o_wrapper_o_snapshot_protege_do_lucro_fantasma` (DL-045) — que
  exige PostgreSQL e por isso não pôde ser escrito e executado nesta máquina.
- **Achado 11 — o §2º (dividendo por ação) não existe no enum.** Ele consta
  como exigido em [requisitos.md](../projeto/requisitos.md) e não está nem na
  apuração nem no documento. Declarado, não implementado às cegas: a rubrica
  pede valor por ação e a DLPA **não tem dado de ações** — a base de cálculo é
  do DMPL (CTB-14). ⚠️ O auditor **também não pôde** confirmar o §2º em fonte
  oficial (sem rede).
- **Achado 13 — `data_inicio_exercicio` vai ao contexto e não é usado.** O
  template repete `01/01/{{ ano }}` em três lugares. Inofensivo enquanto o
  exercício é o ano civil (D6); vira divergência silenciosa no documento se
  HI-28 mudar.
- **Achado 15 — um ajuste de exercício anterior lançado em 31/12 cai no saldo
  inicial** e a linha sai zerada; o mesmo ajuste em 02/01 aparece na linha. O
  filtro é só por data, e o produto não controla nem sinaliza a data digitada.
- **Achado 12 — o rollback da 0012 perde as classificações** gravadas (o
  `RemoveField` não as preserva). A trilha registra cada mudança, mas só a
  partir de quando existe.
- **Achado 14 — `mes` fora da faixa 1–12** levanta exceção crua
  (`IllegalMonthError`/`TypeError`) em vez de erro de domínio. Hoje nenhum
  caminho erre (a view valida), e a correção pertence à fatia de API (D8).
- **Conformidade normativa: NÃO CONCLUÍDA.** Nem a auditoria nem a
  implementação puderam ler Planalto/CFC nesta máquina: **nenhuma** linha do
  art. 186, nem a Lei 6.404/76, nem a Lei 9.249/95 foi reconferida em fonte
  oficial. A verificação normativa é do Fred, com o texto na mão.
