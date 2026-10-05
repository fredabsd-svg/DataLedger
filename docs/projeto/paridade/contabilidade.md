# Plano de paridade — Contabilidade

> ⚠️ **Como ler a situação de um item (DL-064, 04/10/2026).** Este mapa foi
> escrito em 27/09/2026 e **não foi atualizado** depois da leva DL-061, DL-062
> e DL-063. A varredura de 04/10 encontrou **todas** as citações
> `arquivo:linha` dos itens marcados "Existe" **deslocadas** (medido: `Conta`
> citado em `models.py:527`, real em 976; `apurar_balancete` citado em 3025,
> real em 3065). **Nenhuma delas serve para abrir o código hoje**, e por isso
> este mapa passa a ser lido assim:
>
> 1. A **prova de existência** é o **símbolo** (`apurar_dmpl`, `Conta`) e o
>    **plano** (`docs/planos/DL-xxx.md`) — nunca o número da linha.
> 2. A **situação** ("Existe" / "Parcial" / "Não existe") é a do documento e
>    **pode estar velha**. Antes de planejar contra ela, confirme no código.
> 3. Quando um item for entregue, corrija a situação **na mesma etapa**, como
>    a DL-061 fez com o CTB-14. Uma planilha que diz que a DMPL não existe
>    quase fez planejar contra ela.
>
> Medir de novo: `python scripts/gerar_planilha_de_paridade.py` (quando
> versionado), ou a varredura manual dos blocos `**Situação no DataLedger.**`.

> ⚠️ **Leia também a [DL-068](../../planos/DL-068-plano-do-modulo-contabil.md)
> (05/10/2026).** Ela diz **quando** cada item entra e **o que mudou** em 2026
> e 2027, e lista na seção "Correções que este plano faz aos documentos" as
> afirmações deste mapa que estão superadas (constraint de banco do CTB-02,
> fontes do CTB-14 e do CTB-17, premissa do método direto do CTB-15, perguntas
> já respondidas na DL-048, vigência da NBC TG 26 (R5), leiautes da ECD e da
> ECF). **Onde divergirem, vale a DL-068.** Os itens novos CTB-75 a CTB-84
> estão no fim deste documento.

## Introdução

### Escopo

Este documento lista, **item por item**, tudo o que o manual de referência do
sistema de mercado (Domínio Contabilidade, versão 10.1A-12, 856 páginas, 2018)
descreve como capacidade do módulo de Contabilidade, cruzado com o que o
DataLedger tem **hoje**, medido em código. É o plano detalhado que a
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md) pediu para o módulo
Contabilidade. Cobre relatórios e funções — **inclusive os que já existem**,
marcados como tal, com o que falta para paridade plena; e os que não existem,
com dependência, dado, regra, tela e critério de aceite.

Não é plano de etapa. Cada item vira um plano `DL-xxx` próprio quando for
priorizado; este documento é o mapa que evita que esse plano comece do zero ou
esqueça uma dependência.

### Fontes

- [mapa-funcional-contabil.md](../mapa-funcional-contabil.md) — inventário do
  manual (seção "Inventário completo — manual 10.1A-12"), as seis ideias
  estruturais do domínio, e o cruzamento com o código já feito pelo
  `arquiteto-senior`.
- [catalogo-de-relatorios.md](../catalogo-de-relatorios.md) — os 120
  relatórios de um segundo manual (edição de 20/09/2026), cruzados com o
  código; usado para confirmar prioridade e para os itens que o primeiro
  manual não nomeia com a mesma clareza (ex.: Contas sem Movimentação).
- [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) — as
  três classes de documento (conferência, demonstração, livro) que decidem o
  que cada relatório deste plano pode e não pode ter de personalização.
- [requisitos.md](../requisitos.md) e [backlog.md](../backlog.md) — RC, HI, PE
  e BL já existentes são **reaproveitados e citados**, nunca duplicados.
- [decisoes.md](../decisoes.md) — decisões de arquitetura (DE) que já resolvem
  parte do desenho de vários itens deste plano.
- Código real de `apps/contabilidade/` (`models.py`, `services.py`,
  `views_web.py`, `urls_web.py`), lido nesta sessão para descrever com
  precisão o que existe — não o que o README diz que existe.

O manual do sistema de referência **não está e nunca estará neste
repositório**. Nada do texto dele foi copiado; o que está aqui é entendimento
nosso, em nossas palavras, com a página citada para quem quiser conferir a
rotina.

### Convenções

- **ID:** `CTB-NN`, sequencial, sem reuso.
- **Classe de documento** (de
  [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md)): **C**
  = relatório de conferência (forma livre, decisão do escritório); **D** =
  demonstração contábil (NBC TG 26 (R5), item 51/52, identificação obrigatória
  em cada página); **L** = livro contábil (NBC ITG 2000 (R1), forma quase
  totalmente prescrita); **R** = arquivo regulatório/obrigação acessória
  (leiaute oficial, sem margem de personalização nenhuma).
- **Fonte normativa "a confirmar":** significa que esta sessão **não conferiu**
  o dispositivo na fonte oficial vigente. É citação preliminar, baseada no
  conhecimento geral do domínio e no que já está registrado em
  [requisitos.md](../requisitos.md), **nunca** uma alegação de vigência. Antes
  de qualquer linha de código que implemente cálculo ou leiaute, a fonte
  precisa ser lida na íntegra e validada pelo Fred (AGENTS.md §10).
- **"Existe"** significa que há código de produção fazendo aquilo, não que a
  tela está bonita ou que não falta nada — o campo "Situação no DataLedger" diz
  exatamente o que falta.
- Todo valor monetário de exemplo é sintético, sem relação com cliente real
  (AGENTS.md §7).

### Estado atual medido no código (remedido em 04/10/2026)

⚠️ **Remedido na DL-064.** A medição original era de 27/09/2026 e já não
servia. O número que importa é que o módulo **cresceu 26%** desde então — e
é por isso que nenhuma linha deste mapa deve ser tomada como medida de hoje.

`apps/contabilidade/` tem **18.995 linhas** de Python (sem migrações nem
testes), contra 15.045 na medição de 27/09. Os arquivos principais:
`models.py` (2.046), `services.py` (7.200), `views_web.py` (6.264),
`views.py` (2.087), `serializers.py` (374) e `urls_web.py` (181).

**Como volver a medir** (é o que vale, não o número):
`Get-ChildItem apps\contabilidade -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch "migrations|tests|__pycache__" }`

Os modelos da listagem original — `Competencia`, `Conta`,
`LancamentoContabil`, `ItemLancamento`, `ParametroContabilEmpresa` —
continuam válidos, e `Conta` ganhou **dois** campos de classificação desde
então: `classificacao_dlpa` (CTB-13) e `classificacao_dmpl` (CTB-14).

Modelos existentes: `Competencia`, `Conta` (com `classificacao_patrimonial` e
`classificacao_dre` como campos fixos, não estrutura configurável à parte),
`LancamentoContabil` (imutável, com `estorno_de`, `chave_idempotencia`,
`competencia`), `ItemLancamento` (débito/crédito, `Decimal` 18,2),
`ParametroContabilEmpresa` (periodicidade de zeramento e três contas de
destino, com vigência). Serviços existentes cobrem: criação e estorno de
lançamento; fechamento, reabertura e entrega de competência; registro e
encerramento de vigência de parâmetro contábil; zeramento do resultado (prévia
e execução); Diário, Razão, Balancete; apuração de saldos consolidados
(`apurar_saldos`); Balanço Patrimonial e DRE, cada um com avaliação de
pendência que veta a emissão; e cinco funções de conferência (lote
desbalanceado, data fora da faixa, movimento fora do período, conta sintética
com movimento, conta com filhas que aceita lançamento, inconsistência de
hierarquia). Não existe interface de personalização de relatório própria do
módulo — o mecanismo de identificação e timbre é de plataforma (RC-94), fora
de `apps/contabilidade`. O módulo `apps/livro_caixa/` implementa carnê-leão e
livro-caixa de pessoa física ([DL-046](../../planos/DL-046-livro-caixa-e-carne-leao.md)),
regime de caixa, **não** partida dobrada — é adjacente, não é este módulo; ver
CTB-63.

### Como ler

1. Comece pela seção "Mapa de dependências e ondas" para saber a ordem.
2. Cada item é autossuficiente: um desenvolvedor pode abrir só o item que lhe
   foi atribuído e encontrar tudo que precisa, inclusive o que ele depende e o
   que ele destrava.
3. Onde a fonte normativa não foi conferida, **isso está escrito
   explicitamente** — não implemente cálculo, alíquota ou leiaute a partir
   deste documento sem antes ler a fonte oficial vigente e obter validação do
   Fred.
4. A seção final "Fora de escopo ou dependente de confirmação" não é lista de
   itens a ignorar para sempre: é lista de itens que **precisam de uma decisão
   do Fred antes** de virar código, ou que a decisão de produto já foi "não
   agora".

## Mapa de dependências e ondas

A ordem segue a [DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md):
Onda 1 é a estrutura de demonstração ligada à conta (destrava DLPA, DMPL, DFC,
análise vertical/horizontal e o resto da Parte I do catálogo); Onda 2 é o
encerramento do exercício, termos, livro Diário/Razão encadernável, sócios e
contador responsável; depois vem centro de custo, histórico/lançamento padrão,
participantes, extrato/conciliação, importação/exportação, plano referencial,
ECD/ECF.

Este plano acrescenta uma **Onda 0**, que a DL-047 não precisava nomear porque
falava do que falta — mas um plano para "outro dev não se perder" precisa
descrever também a base que já existe, porque tudo o resto se apoia nela.

```
ONDA 0 — núcleo já entregue (marcar Existe, completar paridade)
  CTB-01 Plano de contas
    └─> CTB-02 Lançamento por partidas dobradas
          ├─> CTB-03 Diário           ─┐
          ├─> CTB-04 Razão             ├─ saídas de conferência (existem)
          ├─> CTB-05 Balancete        ─┘
          ├─> CTB-06 Conferência de lotes e inconsistências
          └─> CTB-07 Competência e fechamento do período
                └─> CTB-08 Período de trabalho (janela de digitação)
  CTB-01 + CTB-02 ──> CTB-09 Balanço Patrimonial
  CTB-01 + CTB-02 ──> CTB-10 Demonstração do Resultado do Exercício (DRE)
  CTB-07 ──> CTB-11 Parâmetro contábil por empresa e zeramento periódico

ONDA 1 — estrutura de demonstração ligada à conta
  CTB-09 + CTB-10 ──> CTB-12 Estrutura de demonstração ligada à conta (base)
    ├─> CTB-13 DLPA ───────────────────┐ (compensação de lucro/prejuízo: ver CTB-24)
    ├─> CTB-14 DMPL ────────────────── ┤
    ├─> CTB-15 DFC (depende também de CTB-40/CTB-41 para o método direto)
    ├─> CTB-16 DRA
    ├─> CTB-17 DVA
    └─> CTB-18 Notas explicativas
  camada de saldos (CTB-09/apurar_saldos, já existe) ──>
    CTB-19 Análise vertical e horizontal
    CTB-20 Coeficientes de análise (índices) e EBITDA
    CTB-21 Comparativo de movimento entre períodos / Balancete comparativo
    CTB-22 Gráficos
  sem dependência, barato: CTB-23 Contas sem movimentação

ONDA 2 — encerramento do exercício, termos, livro encadernável, sócios/contador
  CTB-07 + CTB-13(DLPA) ──> CTB-24 Encerramento do exercício (formal)
  CTB-24 ──> CTB-25 Termos de abertura, encerramento e transferência
  CTB-03 + CTB-04 + CTB-25 + CTB-30 ──> CTB-26 Livro contábil encadernável
  CTB-28 + CTB-29 ──> CTB-27 Carta de responsabilidade da administração
  CTB-28 Sócios e quadro societário
  CTB-29 Contador responsável técnico (CRC)
  CTB-30 Histórico cadastral da empresa consultável por data
  CTB-31 Perfis de empresa (modelo para cliente novo)

DEPOIS — grupos paralelos, cada um com sua própria cadeia
  CTB-32 Origem e documento de origem no lançamento
    ├─> CTB-45 Alteração de lançamentos em massa
    ├─> CTB-46 Regeração de lançamentos derivados
    ├─> CTB-47 Permissão própria p/ alterar lançamento de origem automática
    └─> CTB-48 Integração fiscal → contábil
  CTB-33 Centro de custo e departamento
    └─> CTB-34 Rateio por centro de custo
          └─> CTB-35 Saídas filtráveis por centro de custo
  CTB-37 Histórico padronizado ──> CTB-38 Lançamento padrão
  CTB-39 Participantes ──> CTB-42 Conciliação de clientes e fornecedores
  CTB-40 Extrato bancário ──> CTB-41 Conciliação bancária ──> alimenta CTB-15 (DFC método direto)
  CTB-36 Lançamentos orçados e orçamento × realizado (depende de CTB-33 opcionalmente)
  CTB-50 Plano de contas referencial ──> CTB-51 ECD ──> CTB-52 ECF (+ ajustes)
  CTB-53 Apuração de CMV e CPV (depende de módulo de estoque, inexistente)
  CTB-54 Autorização com escopo de empresa — atravessa TODO o módulo, decisão de arquitetura
  CTB-55, CTB-56, CTB-57 — decisões de modelagem a registrar cedo (custo de errar é alto)
  CTB-58 Sócio/contador/responsável como mesma pessoa entre papéis
  CTB-59 Consolidação entre empresas / plano de contas compartilhado
  CTB-60 Alteração da estrutura do plano de contas em massa
  CTB-61 Registro de atividades — já coberto pela trilha de auditoria
  CTB-62 Cópia de configuração entre empresas do escritório
  CTB-63 Carnê-leão e livro-caixa PF — módulo adjacente, já existe (DL-046)

FORA DE ESCOPO OU DEPENDENTE DE CONFIRMAÇÃO
  CTB-64 a CTB-74 — ver seção final
```

Consequência prática desta ordem, no mesmo espírito da recomendação da
DL-047: quem só tem tempo para uma fatia deve fechar a **Onda 1** (DLPA, DMPL,
DFC, análise vertical/horizontal), porque ela usa uma base que já existe
(saldos, DRE, Balanço) e entrega o pacote de demonstrações que o escritório
emite todo ano — a mesma recomendação **A** da DL-047.

## Onda 0 — Núcleo já entregue

Estes **dez** itens já têm código de produção. Estão aqui porque o pedido do
Fred foi "todas as funções", e porque quem for construir a Onda 1 precisa
saber exatamente o que a base oferece e o que falta nela — vários itens das
ondas seguintes têm "o que falta para paridade" destes como pré-requisito.

⚠️ **Corrigido em 04/10/2026 (DL-064):** este texto dizia "onze". O décimo
primeiro, **CTB-08 (período de trabalho)**, está marcado "**Não existe**"
no item dele: o que existe é o fechamento de competência (CTB-07), que não
é a mesma coisa. A lista de Onda 0 deve dizer **dez**, ou o item CTB-08 sair
daqui.

### CTB-01 — Plano de contas

**O que é.** A lista de todas as contas que uma empresa usa para registrar
seus fatos contábeis, organizada em árvore (grupos e subgrupos, até a conta
que efetivamente recebe lançamento). É o vocabulário fechado com que a
contabilidade fala.

**Exemplo.** `1` Ativo (sintética) → `1.2` Ativo não circulante (sintética) →
`1.2.3` Imobilizado (sintética) → `1.2.3.03.001` Máquinas e equipamentos
(analítica, devedora) e `1.2.3.07.003` (-) Depreciações de máquinas e
equipamentos (analítica, **credora**, retificadora dentro do grupo devedor).

**Referência de rotina.** Manual, "Plano de contas com vínculos (referencial,
demonstrativos, carnê-leão)", páginas 120-143.

**Fonte normativa.** Não há leiaute oficial de plano de contas para empresas
em geral (cada empresa define o seu); a separação circulante × não circulante
que classifica os grupos vem da **Lei 6.404/1976, art. 178, §1º e §2º**
(redação da Lei 11.941/2009) e da **NBC TG 26 (R5), item 60** — já **conferida
na fonte primária** e registrada como **RC-106**.

**Situação no DataLedger.** **Existe.** `Conta` (`apps/contabilidade/models.py:527`):
hierarquia por `conta_pai`, `tipo`, `natureza`, `classificacao_patrimonial`
(RC-106/DL-033), `classificacao_dre` (RC-118/DL-045), `aceita_lancamento`
(distingue sintética de analítica — DE-022 redefiniu "analítica" como "conta
sem descendentes" para as saídas, e a permissão de lançar ficou como campo
próprio, não critério de apresentação), `ativo`. Código único por empresa
(`codigo_unico_por_empresa`). Conta retificadora é suportada por natureza
contrária dentro do mesmo grupo (RC-61), e o grupo soma pela **sua própria**
natureza (DE-020 §2) — o caso de referência do Fred (1.437,50 D + 29.900,00 D
− 2.074,18 C = 29.263,32 D) está coberto. Conta com lançamento não pode ser
apagada (`on_delete=PROTECT`, confirma RC-100).

**O que falta para paridade:**
- **Código reduzido** (RC-99): número inteiro que o contador digita para
  lançar e conferir, distinto do código estruturado. **Não existe** — é
  campo novo, com unicidade e reaproveitamento quando a conta sem lançamento
  é apagada (RC-100).
- **Classificação distinta do código de cadastro** (RC-64): hoje `codigo`
  acumula os dois papéis. O manual trata "código de cadastro" e
  "classificação hierárquica" como conceitos separados.
- Unicidade de classificação **condicional**, não absoluta — ver CTB-57.
- Vínculo ao plano de contas **referencial** por vigência — ver CTB-50.
- Vínculo às estruturas de **outras** demonstrações (DLPA, DMPL, DFC, DVA) —
  ver CTB-12.

**Depende de.** — (é a base).

**Dados.** `Conta`: `empresa`, `conta_pai`, `codigo`, `nome`, `tipo`,
`natureza`, `classificacao_patrimonial`, `classificacao_dre`,
`aceita_lancamento`, `ativo`.

**Regras.**
- Conta sintética (com descendentes) nunca recebe lançamento direto quando
  `aceita_lancamento=False`; quando aceita e tem filhas, o saldo soma o
  próprio movimento mais o das descendentes (DE-020 §1, DE-022).
- Troca de empresa, de natureza ou de tipo em conta com movimento é recusada
  (`Conta.clean()`, fecha BL-83/BL-245).
- Reclassificação de conta sintética propaga para as filhas, sem órfãs.

**Telas e documentos.** Tela de plano de contas e cadastro de conta
(`plano_de_contas.html`, `conta_form.html`) — classe **C** (cadastral, sem
norma de forma). Falta a tela de **editar** conta existente (mover de grupo)
pela interface do produto — hoje só pelo admin do Django (**BL-541**).

**Critérios de aceite.** Já cobertos pelos testes existentes de
`apps/contabilidade/tests/`; novos critérios entram junto de cada item que
completa a paridade (código reduzido, referencial etc.).

**Perguntas.** Nenhuma nova — as pendentes (PE-54/RC-100, código reduzido)
já estão registradas em [requisitos.md](../requisitos.md).

### CTB-02 — Lançamento por partidas dobradas

**O que é.** O registro de um fato contábil: um conjunto de débitos e créditos
que, somados, fecham em zero. É o "lote" do domínio — a unidade que precisa
fechar, não a partida isolada (ideia estrutural 1 do mapa funcional).

**Exemplo.** Pagamento de aluguel de R$ 2.000,00: débito em "Despesas com
aluguel" R$ 2.000,00, crédito em "Bancos — conta movimento" R$ 2.000,00. Um
lançamento de folha pode ter um débito (despesa com salários) para vários
créditos (salário líquido, INSS a recolher, IRRF a recolher) — é a topologia
N:1, M:N que o domínio exige.

**Referência de rotina.** Manual, "Lançamento com dimensões (centro de custo,
referencial, participante, DMPL, DFC)", páginas 180-197; "Lançamento e
consulta na mesma tela", páginas 199-217.

**Fonte normativa.** Partida dobrada é princípio contábil geral (não há um
único artigo de lei a citar); a igualdade débito=crédito por lançamento é
regra de engenharia do próprio projeto (AGENTS.md §10, RC-11).

**Situação no DataLedger.** **Existe e é a parte mais sólida do produto.**
`criar_lancamento` (`apps/contabilidade/services.py:583`): valida igualdade
de débitos e créditos, cria competência automaticamente
(`obter_ou_criar_competencia`), impede lançamento fora da faixa de data
(RC-77), aplica teto de 200 partidas com recusa explícita (RC-79, nunca
truncamento), é idempotente por `Idempotency-Key` com impressão digital do
conteúdo (`chave_idempotencia_fingerprint`, recusa 409 em reaproveitamento
com conteúdo diferente). `LancamentoContabil.save()` e `.delete()` levantam
`LancamentoImutavelError` em qualquer segunda gravação — imutabilidade
garantida no próprio modelo, não só por convenção. `estornar_lancamento`
(linha 998) cria o reverso, com `estorno_de_unico` como `UniqueConstraint` de
banco (um lançamento só pode ser estornado uma vez) e recusa de data anterior
ao original (RC-78).

**O que falta para paridade:**
- Rascunho distinto de efetivado (RC-12) — **não existe**: todo lançamento
  nasce efetivado. É invariante declarada e não implementada (BL-10).
- Dimensões do lançamento que o manual lista e o DataLedger ainda não tem:
  centro de custo (CTB-33/34), participante (CTB-39), origem e documento de
  origem (CTB-32), histórico como modelo (CTB-37/48), vínculo ao referencial
  na própria partida (CTB-56).
- "Lançamento e consulta na mesma tela" (páginas 199-217) é padrão de
  interface — a tela atual (`lancamento_form.html`) separa lançar de
  consultar; unificar é melhoria de UX sem mudança de modelo, avaliada pelo
  `especialista-frontend` quando a tela for revisitada.
- "Consultas rápidas" (saldos, contas × lançamentos, movimento mensal,
  páginas 710-714): parcialmente cobertas pela API (`apurar_saldos`,
  `apurar_razao`); falta a tela dedicada de consulta rápida fora do fluxo de
  emissão de relatório.

**Depende de.** CTB-01.

**Dados.** `LancamentoContabil`: `empresa`, `data`, `historico`,
`estorno_de`, `criado_por`, `chave_idempotencia`,
`chave_idempotencia_fingerprint`, `competencia`. `ItemLancamento`:
`lancamento`, `conta`, `tipo` (débito/crédito), `valor` (`Decimal` 18,2, mín.
0,01).

**Regras.**
- Débitos = créditos em todo lançamento efetivado (RC-11) — validação de
  serviço; constraint de banco avaliada e adiada por DE-021/BL-13/BL-78 até
  haver migração de esquema que valha a pena acumular com outras.
- Data de lançamento entre 01/01/2000 e hoje+30 dias (RC-77).
- Até 200 partidas por lançamento; acima disso, recusa explícita (RC-79).
- Estorno nunca tem data anterior à do lançamento original (RC-78); estorno
  de lançamento de mês fechado é permitido, desde que o estorno em si caia em
  mês aberto (RC-103).
- Reaproveitar a mesma chave de idempotência para conteúdo diferente é
  recusado com 409, nunca aceito silenciosamente como o conteúdo antigo.

**Telas e documentos.** `lancamento_novo`/`lancamento_form.html`,
`lancamento_detalhe`/`lancamento_detalhe.html` — classe **C** (tela de
trabalho, sem exigência normativa de forma).

**Critérios de aceite.** Já cobertos pelos testes existentes; o item de
rascunho/efetivação (BL-10) precisa de critérios próprios quando priorizado:
rascunho editável e excluível; efetivação é transição explícita e auditada;
efetivado permanece imutável mesmo depois de ter sido rascunho.

**Não copiar / riscos.** O manual permite **alteração em massa** que
sobrescreve lançamento efetivado sem rastro visível do valor anterior — ver
CTB-45, onde o desenho diverge deliberadamente.

### CTB-03 — Diário

**O que é.** A listagem cronológica de todos os lançamentos de um período,
com os totais de débito e crédito. É o relatório mais básico de conferência:
"o que foi lançado, em ordem, neste intervalo".

**Exemplo.** Diário de janeiro/2026 de uma empresa: cada lançamento aparece
com data, número, histórico e as partidas (conta, débito ou crédito, valor);
no fim, o total de débitos do período é igual ao total de créditos.

**Referência de rotina.** Manual, páginas 248-253; item 17 do catálogo de 120
relatórios (Livro Diário).

**Fonte normativa.** Como relatório de **conferência** (classe C), nenhuma
norma fixa seu cabeçalho ([personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md),
HI-11). Como **livro** (classe L), a forma vem da **NBC ITG 2000 (R1)**, itens
5, 9, 10, 13 — já **conferida na fonte primária** e registrada como RC-96. A
forma de livro é tratada separadamente em CTB-26.

**Situação no DataLedger.** **Existe, como relatório de conferência, com
período.** `listar_diario` (`apps/contabilidade/services.py:2764`) e a tela
`diario`/`diario.html`. O achado antigo do mapa funcional de que faltava
filtro de período estava **desatualizado** — já foi corrigido (DL-015) e a
correção foi conferida por leitura direta do código nesta sessão.

**O que falta para paridade:** a **forma de livro** (numeração de folha,
termo de abertura/encerramento, ausência de espaço em branco) — ver CTB-26;
filtro por centro de custo — ver CTB-35; origem/documento de origem em cada
lançamento listado — ver CTB-32.

**Depende de.** CTB-01, CTB-02.

**Dados.** Mesmos de `LancamentoContabil`/`ItemLancamento`, agregados por
lote e por período.

**Regras.** O total de débitos do Diário do período é igual ao total de
créditos do mesmo período (é a mesma invariante do lançamento, agregada); o
total do Diário do período é igual ao total de movimento do Balancete do
mesmo período (mesma origem, agregações diferentes — regra 7 do mapa
funcional).

**Telas e documentos.** `diario`/`diario.html` — classe **C** hoje; a mesma
tela, com forma de livro ligada, vira classe **L** (CTB-26).

**Critérios de aceite.** Intervalo obrigatório de datas; total de débitos
igual ao de créditos no rodapé; teste que compara o total do Diário com o
total de movimento do Balancete do mesmo período.

### CTB-04 — Razão

**O que é.** O extrato de uma conta específica: todos os lançamentos que a
tocaram num período, com saldo anterior, movimento e saldo final. É "o que
aconteceu nesta conta".

**Exemplo.** Razão da conta "Bancos — conta movimento" de janeiro/2026: saldo
anterior R$ 5.000,00 D; lançamentos do mês (recebimentos a crédito,
pagamentos a débito); saldo final = saldo anterior + créditos − débitos (para
conta de natureza devedora, a leitura é invertida).

**Referência de rotina.** Manual, páginas 258-263; item 18 do catálogo (Livro
Razão), item 19 (Razão Analítico), item 20 (Razão por Centro de Custo).

**Fonte normativa.** Mesma distinção de CTB-03: conferência (C) sem norma de
forma; livro (L) pela NBC ITG 2000 (R1) — RC-96.

**Situação no DataLedger.** **Existe, por período.** `apurar_razao`
(`apps/contabilidade/services.py:2891`) e a tela `razao`/`razao.html`.
Consolida automaticamente quando a conta tem descendentes, com a resposta
declarando que o extrato é consolidado (DE-020 §3, DE-022) — nunca "some" ou
"recusa" quando o contador abre o Razão de um grupo.

**O que falta para paridade:** Razão **Analítico** com origem e documento de
origem (catálogo item 19, depende de CTB-32); Razão **por Centro de Custo**
(catálogo item 20, depende de CTB-33/34/35); forma de livro (CTB-26).

**Depende de.** CTB-01, CTB-02.

**Dados.** Mesmos de `ItemLancamento`, filtrados por `conta` (e descendentes)
e por período.

**Regras.** O saldo de uma conta no Razão bate com a linha dela no Balancete
do mesmo período — mesma origem, agregações diferentes (regra 7 do mapa
funcional, já coberta por teste).

**Telas e documentos.** `razao`/`razao.html` — classe **C**; título traz a
razão social da empresa, não o nome da conta (RC-98).

**Critérios de aceite.** Já cobertos; novos critérios entram com CTB-32 e
CTB-33/34/35.

### CTB-05 — Balancete de verificação

**O que é.** A lista de todas as contas de uma empresa com, para cada uma,
saldo anterior, débitos do período, créditos do período e saldo final — o
"resumo de tudo" que o contador confere antes de fechar o mês.

**Exemplo.** Balancete de janeiro/2026, nível 2: cada grupo sintético mostra a
soma das suas analíticas; o total geral de débitos do período é igual ao
total de créditos.

**Referência de rotina.** Manual, páginas 264-270; itens 11 a 16 do catálogo
(Balancete de Verificação, Analítico, Sintético, Mensal, Acumulado,
Comparativo).

**Fonte normativa.** Relatório de conferência (classe C) — nenhuma norma fixa
seu cabeçalho (HI-11).

**Situação no DataLedger.** **Existe.** `apurar_balancete`
(`apps/contabilidade/services.py:3025`), com `nivel` e `criterio_de_apuracao`
como parâmetros explícitos, e `avaliar_emissao_do_balancete` (linha 3472) que
avalia pendências antes da emissão. Totaliza sintéticas somando as
descendentes (DE-020 §1, BL-60 integrado); total de débitos = total de
créditos independentemente do arranjo da hierarquia.

**O que falta para paridade:** Balancete **Comparativo** (catálogo item 16 —
duas colunas de período lado a lado, hoje **não existe**, é item barato de
adicionar sobre `apurar_balancete` chamado duas vezes); Balancete
**Acumulado** "desde o início do exercício" como conceito nomeado (hoje o
período livre permite acumular, mas não há o rótulo nem o atalho); critério
de apuração impresso no documento (já recomendado em RC-97, DL-027 — conferir
se chegou a este relatório especificamente).

**Depende de.** CTB-01, CTB-02.

**Dados.** Agregação de `ItemLancamento` por `conta` e período, com
hierarquia.

**Regras.** Nenhum arranjo de plano de contas pode fazer valor sumir ou
aparecer duas vezes (DE-020 §1); conta que aceita lançamento e tem
subordinadas é apontada pela conferência (CTB-06), não escondida.

**Telas e documentos.** `balancete`/`balancete.html`,
`balancete_emissao_recusada.html` — classe **C**.

**Critérios de aceite.** Já cobertos; Comparativo entra com critério próprio
(duas colunas somando ao total correto cada uma) quando priorizado.

### CTB-06 — Conferência de lotes e inconsistências contábeis

**O que é.** A ferramenta de diagnóstico que varre a base procurando o que
está torto: lote cuja soma de débitos não fecha com créditos, lançamento com
data fora da faixa aceitável, movimento fora do período consultado, conta
sintética com movimento próprio, conta que aceita lançamento e ainda assim
tem subordinadas, inconsistência de hierarquia.

**Referência de rotina.** Manual, páginas 779-780; item 24 do catálogo
(Relatório de Inconsistências Contábeis) — o próprio catálogo pede
"validações essenciais", e o DataLedger já entrega **seis**, mais do que o
mínimo do catálogo pede.

**Fonte normativa.** Não há norma que descreva este relatório — é ferramenta
de conferência interna, classe **C**.

**Situação no DataLedger.** **Existe e é o ponto mais forte do módulo,
medido.** Seis funções em `services.py`: `localizar_lancamentos_com_data_fora_da_faixa`
(5380), `localizar_lotes_desbalanceados` (5411),
`localizar_contas_sinteticas_com_movimento` (5465),
`localizar_contas_que_aceitam_lancamento_e_tem_subordinadas` (5502),
`localizar_inconsistencias_de_hierarquia` (5527), e
`movimento_fora_do_periodo` (5284). Tela `conferencia`/`conferencia.html`.

**O que falta para paridade:** a categoria "partida cuja conta é de outra
empresa" (**BL-84**, ainda `planejada`) — é justamente o estado que a garantia
de banco de CTB-32/DE-021 deveria tornar impossível, mas enquanto ela não
existir a conferência precisa apontar o caso pelo caminho de código.

**Depende de.** CTB-01, CTB-02.

**Dados.** Consulta agregada sobre `LancamentoContabil`/`ItemLancamento`/
`Conta`, sem modelo novo.

**Regras.** Toda categoria de inconsistência precisa nomear a conta ou o
lançamento envolvido, nunca só "há um problema"; a conferência é o mecanismo
que garante que a invariante débito=crédito, se algum caminho a violar (
migração, importação futura, ORM direto), fica visível em vez de silenciosa.

**Telas e documentos.** `conferencia`/`conferencia.html` — classe **C**.

**Critérios de aceite.** Teste que grava um lote torto por caminho alternativo
(fora do serviço) e prova que a consulta o encontra — já existe para as seis
categorias atuais; o mesmo padrão vale para BL-84 quando implementado.

### CTB-07 — Competência e fechamento do período

**O que é.** O controle formal de que um mês contábil está "aberto"
(aceitando lançamento livremente) ou "fechado" (só se mexe com reabertura
autorizada). É a garantia de que o balancete entregue ao cliente em fevereiro
não muda silenciosamente em março.

**Exemplo.** Janeiro/2026 é fechado em 05/02/2026 por um Gestor. A partir daí,
lançar em 15/01/2026 é recusado. Se o mês ainda **não foi entregue** ao
cliente, o Gestor pode **reabrir** com motivo registrado, corrigir, e fechar
de novo. Se **já foi entregue**, a reabertura é recusada — o ajuste vai no mês
aberto corrente, apontando para a competência de origem (RC-101).

**Referência de rotina.** Manual, "Fechamento de competência", página 108;
item 25 do catálogo (Encerramento do Exercício, que é o formal — ver CTB-24
para a distinção entre este e aquele).

**Fonte normativa.** Não há uma norma única que descreva "fechamento de
competência" como procedimento de sistema; é prática contábil e decisão
operacional do escritório (RC-101/RC-102/RC-103, confirmadas pelo Fred).

**Situação no DataLedger.** **Existe.** `Competencia`
(`apps/contabilidade/models.py:46`) com `estado`, `fechada_em`/`fechada_por`,
`entregue_em`/`entregue_por` (fato datado, nunca um quarto estado — decisão
do `arquiteto-senior`, RC-101). Serviços: `encerrar_competencia` (linha 1115),
`reabrir_competencia` (1239), `marcar_competencia_como_entregue` (1343).
Autorização: Administrador ou Gestor fecham/reabrem/entregam; Analista não
(RC-102, verificado no servidor). Não se fecha competência com lote
desbalanceado na base (RC-58).

**O que falta para paridade:** nada do fechamento **mensal** em si; o que
falta é o **encerramento do exercício** (formal, anual, com termos e
compensação de lucros/prejuízos) — ver CTB-24, que é conceito **diferente**
deste, apesar do nome parecido no catálogo.

**Depende de.** CTB-01, CTB-02.

**Dados.** `Competencia`: `empresa`, `ano`, `mes`, `estado`, `fechada_em`,
`fechada_por`, `entregue_em`, `entregue_por`.

**Regras.** Lançamento em competência encerrada é recusado no servidor;
reabertura exige papel autorizado (Administrador/Gestor) e gera registro de
auditoria; competência entregue nunca reabre (RC-101); estorno de lançamento
de mês fechado é aceito se o próprio estorno cair em mês aberto (RC-103).

**Telas e documentos.** `fechamento`/`fechamento.html`,
`competencia_fechar.html`, `competencia_reabrir.html`,
`competencia_entregar.html` — classe **C** (tela de operação).

**Critérios de aceite.** Já cobertos pelos testes da DL-016/DL-031.

### CTB-08 — Período de trabalho

**O que é.** Diferente do fechamento formal: é a janela em que o contador
está digitando **agora** — por exemplo, "só aceito lançamento de
setembro/2026 e outubro/2026 nesta tela, hoje". Lançar fora dela pode ser
livre, gerar aviso, ou ser bloqueado, por escolha da empresa (ideia estrutural
2 do mapa funcional). É controle **diferente** do fechamento: evita erro de
digitação (lançar 2025 quando a intenção era 2026), não é a garantia contábil
formal.

**Referência de rotina.** Manual, páginas 106-108.

**Fonte normativa.** Não há norma — é controle operacional de produto.

**Situação no DataLedger.** **Não existe.** O que existe é só o fechamento de
competência (CTB-07); não há conceito de "janela de trabalho corrente" por
empresa, distinto do que está fechado.

**Depende de.** CTB-07.

**Dados.** Provável campo por empresa: período de trabalho corrente (ano/mês
inicial e final) e política (livre/aviso/bloqueio) — molde semelhante ao de
`ParametroContabilEmpresa` (CTB-11), que já resolve "parâmetro que muda no
tempo, com vigência" para este domínio.

**Regras.** Lançamento fora do período de trabalho segue a política
configurada da empresa — nunca é aceito sem checagem (regra 4 do mapa
funcional, ainda sem implementação).

**Telas e documentos.** Parte da tela de lançamento e de parâmetros
contábeis — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa: teste de
lançamento dentro da janela (aceita), fora dela com política "aviso" (aceita
com sinalização) e fora dela com política "bloqueio" (recusa).

**Perguntas.** O escritório do Fred usa esse controle hoje, ou o fechamento
mensal (CTB-07) já é suficiente para a rotina dele? Se a resposta for "o
fechamento basta", este item pode ficar em espera indefinida sem prejuízo —
ele é o único item da Onda 0 sem uso confirmado.

### CTB-09 — Balanço Patrimonial

**O que é.** A fotografia da posição patrimonial da empresa numa data: o que
ela tem (Ativo), o que ela deve (Passivo) e o que sobra para os sócios
(Patrimônio Líquido), com Ativo sempre igual a Passivo + Patrimônio Líquido.

**Exemplo.** Data-base 31/12/2025: Ativo Circulante (Caixa, Bancos, Clientes)
+ Ativo Não Circulante (Imobilizado líquido de depreciação) = Passivo
Circulante (Fornecedores) + Passivo Não Circulante (Financiamentos) +
Patrimônio Líquido (Capital Social + Lucros Acumulados).

**Referência de rotina.** Manual, páginas 271-279; item 1 do catálogo
(implícito na Parte I — Demonstrações).

**Fonte normativa.** **Lei 6.404/1976, art. 178, §1º e §2º** (redação da Lei
11.941/2009) e **NBC TG 26 (R5), itens 60, 66, 68, 69** — **já conferidas na
fonte primária** (Planalto e Câmara dos Deputados, texto idêntico; CFC),
registradas como **RC-106**.

**Situação no DataLedger.** **Existe, com veto de emissão.**
`apurar_balanco_patrimonial` (`apps/contabilidade/services.py:4430`) e
`avaliar_emissao_do_balanco` (4256): recusa emitir enquanto houver conta
movimentada sem `classificacao_patrimonial`. `classificacao_patrimonial` é
campo fixo da conta (`null=True`), nunca inferido do código ou do nome
(decisão HI-18, evita o defeito do achado A2/BL-475 que classificava por
posição na árvore). Saldo em valor absoluto com indicador D/C — a confirmar
uniformidade em todas as saídas (RC-61/**BL-77**, que segue `planejada` no
backlog apesar de o Balanço já implementar a regra).

**O que falta para paridade:** apresentação D/C uniforme e explícita em
**todas** as saídas, não só no Balanço (fechar BL-77 de fato); "Balanço em
forma de demonstração" (catálogo, páginas 642-645) — já é vertical hoje,
então este ponto é nota, não lacuna; reclassificação de longo→curto prazo por
lançamento (CTB-55 trata a correspondência entre exercícios, matéria
correlata).

**Depende de.** CTB-01, CTB-02.

**Dados.** `Conta.classificacao_patrimonial`, agregados via `apurar_saldos`.

**Regras.** Ativo = Passivo + Patrimônio Líquido na data-base; grupo soma
débitos e créditos brutos das descendentes e aplica a natureza do próprio
grupo uma única vez (DE-020 §2); conta sem classificação bloqueia a emissão,
com a lista de pendentes explícita, nunca em silêncio.

**Telas e documentos.** `balanco`/`balanco.html` — classe **D**, identificação
obrigatória em cada página (NBC TG 26 item 51/52, RC-95).

**Critérios de aceite.** Já cobertos pelos testes das DL-032/033/034; caso de
referência obrigatório do Fred (1.437,50 D + 29.900,00 D − 2.074,18 C =
29.263,32 D) já é teste existente.

### CTB-10 — Demonstração do Resultado do Exercício (DRE)

**O que é.** O relatório que mostra como a empresa chegou do total vendido
até o lucro ou prejuízo do período: receita, menos deduções, menos custos e
despesas, mais/menos resultado financeiro, até o resultado líquido.

**Exemplo.** Receita bruta 500.000,00 − Deduções 50.000,00 = Receita líquida
450.000,00 − Custo 200.000,00 = Lucro bruto 250.000,00 − Despesas
operacionais 120.000,00 = Resultado antes do financeiro 130.000,00 +
Receitas financeiras 5.000,00 − Despesas financeiras 15.000,00 = Resultado
antes dos tributos 120.000,00 − IRPJ/CSLL 30.000,00 = Lucro líquido
90.000,00.

**Referência de rotina.** Manual, páginas 583-593; Parte I do catálogo.

**Fonte normativa.** **Lei 6.404/76, art. 187** e **art. 175**; **NBC TG 26
(R5) item 82**; **NBC TG 1000 (R1) item 5.7**; **ITG 1000 (2022)** — **já
conferidas na fonte primária** (Planalto, Câmara, PDFs do CFC), registradas
como **RC-118 a RC-126**.

**Situação no DataLedger.** **Existe (DL-045).** `apurar_dre`
(`apps/contabilidade/services.py:4984`) e `avaliar_emissao_da_dre` (5125):
treze linhas fixas (`ClassificacaoDre`), resultado financeiro destacado
(RC-121/HI-29), participações depois do IRPJ/CSLL (RC-122), deduções só em
conta de receita (RC-123), duas colunas — mês e acumulado do exercício
(RC-119) —, mesmo com zeramento trimestral/anual (RC-126, soma dos meses).
`classificar_conta_na_dre` (5192) é o serviço de classificação.

**O que falta para paridade:** operações descontinuadas (NBC TG 26 item
82(ea)) — adiado por decisão de escopo, RC-124; DRE por **período livre**
(sem colunas fixas mês/acumulado) — RC-126 já identifica isso como a próxima
evolução natural, porque é a rotina padrão do sistema de referência; DRE
comparativa com exercício anterior — fora da primeira versão (RC-119).

**Depende de.** CTB-01, CTB-02.

**Dados.** `Conta.classificacao_dre`, movimento por conta e por período.

**Regras.** Toda conta de receita/despesa movimentada precisa de
classificação antes da emissão (mesmo padrão do Balanço); a linha "resultado
de equivalência patrimonial" aceita conta de tipo receita **ou** despesa, com
o sinal sempre seguindo a natureza natural da **linha**, não do tipo da conta
(decisão do `arquiteto-senior`, 2026-09-26).

**Telas e documentos.** `dre`/`dre.html` — classe **D**.

**Critérios de aceite.** Já cobertos pelos testes da DL-045.

### CTB-11 — Parâmetro contábil por empresa e encerramento periódico do resultado (zeramento)

**O que é.** O mecanismo que zera as contas de receita e despesa no fim de
cada período (mensal, trimestral ou anual, à escolha da empresa) e transfere
o resultado para o Patrimônio Líquido: para "Lucros Acumulados" se deu lucro,
para "(-) Prejuízos Acumulados" (retificadora) se deu prejuízo.

**Exemplo.** Empresa com zeramento mensal: em 31/01/2026, o saldo líquido de
todas as contas de resultado (R$ 12.000,00 de lucro) é lançado contra a conta
"Resultado do Exercício" (etapa 1); em seguida, o saldo desta é transferido
para "Lucros Acumulados" (etapa 2, porque o resultado foi positivo).

**Referência de rotina.** Manual, "Zeramento", páginas 92-95 e 840-841;
"Parâmetros da empresa" (zeramento é uma das oito abas), páginas 67-105.

**Fonte normativa.** Não há um dispositivo único que descreva "zeramento" como
procedimento de sistema — é técnica contábil de apuração periódica de
resultado, decorrente da própria definição de conta de resultado. A
compensação entre lucros e prejuízos acumulados **não está conferida** em
fonte oficial (ver "O que falta").

**Situação no DataLedger.** **Existe (DL-043).** `ParametroContabilEmpresa`
(`apps/contabilidade/models.py:1397`), com periodicidade alternativa por
empresa (RC-105, `UniqueConstraint` + gatilho de banco impedindo vigências
sobrepostas) e três contas de destino. Serviços: `registrar_parametro_contabil`
(1683), `zerar_resultado` (2517), `pre_visualizar_zeramento` (2483). Usa saldo
**próprio** de cada conta (nunca consolidado com filhas — DE-078), é
cronológico (não zera fora de ordem, DE-078 adendo), trava por empresa contra
concorrência, e período ainda não terminado não é zerado (HI-25).

**O que falta para paridade:** compensação de lucros e prejuízos acumulados
entre períodos (**HI-26/PE-38**, aberta — "fica para uma etapa própria, ligada
à DLPA"); desfazer um zeramento feito com parâmetro errado (**PE-69**, aberta);
as demais sete abas de "Parâmetros da empresa" que o manual descreve (geral,
natureza das contas, CMV, CPV, livro caixa, assinaturas, cliente) — hoje só a
de zeramento tem um lugar para morar (`ParametroContabilEmpresa` é o molde
para as próximas, não um armário genérico).

**Depende de.** CTB-07.

**Dados.** `ParametroContabilEmpresa`: `empresa`, `periodicidade_zeramento`,
`conta_resultado_do_exercicio`, `conta_lucros_acumulados`,
`conta_prejuizos_acumulados`, `vigencia_inicio`, `vigencia_fim`.

**Regras.** Periodicidade é alternativa, nunca duas simultâneas na mesma
empresa (RC-105, garantida em banco); as três contas de destino são folhas
ativas, e lucros acumulados é credora (validado no serviço); zeramento é
dividido em vários lançamentos balanceados quando passa do teto de 200
partidas (RC-79), com chave determinística por parte.

**Telas e documentos.** `parametros_contabeis.html`, `zerar_resultado.html`
— classe **C** (operação), o resultado do zeramento é lançamento comum,
visível no Diário.

**Critérios de aceite.** Já cobertos pelos testes da DL-043 e da
reconferência (R1-R6 do DE-078 adendo).

**Perguntas.** Como o escritório do Fred compensa lucros e prejuízos
acumulados entre meses (todo mês, só no fechamento anual, ou lançamento à mão
do contador)? — pergunta já registrada como parte da PE-38/HI-26, repetida
aqui porque destrava a paridade deste item e da CTB-13 (DLPA).

## Onda 1 — Estrutura de demonstração ligada à conta

A ideia estrutural 4 do mapa funcional: DRE, DLPA, DMPL, DFC e DVA não são
relatórios com fórmula fixa isolada — são estruturas de grupos, e a conta é
**vinculada** a esses grupos. O DataLedger já aplica essa ideia de forma
simplificada para o Balanço (`classificacao_patrimonial`) e a DRE
(`classificacao_dre`): um campo fixo por conta, nunca inferido, com apuração
que declara o que falta classificar em vez de presumir. Este é o padrão que
os itens desta onda **repetem**, cada um com seu próprio enum de linhas.

### CTB-12 — Estrutura de demonstração ligada à conta (base)

**O que é.** O mecanismo comum que os itens seguintes desta onda reaproveitam:
um campo fixo na conta (como `classificacao_patrimonial` e `classificacao_dre`
já são), uma apuração que soma pela estrutura, e uma tela que declara — nunca
esconde — o que ainda não tem classificação.

**O que é, em mais detalhe.** O manual do sistema de referência implementa
isto como uma **estrutura configurável por empresa**, com telas de cadastro de
grupos e vínculo em lote. O DataLedger, por decisão já tomada (RC-118, sobre a
DRE), escolheu o desenho **mais simples**: campo fixo por conta, com o
conjunto de linhas definido no código (`TextChoices`), não editável pelo
usuário. A estrutura totalmente configurável "fica para depois, se houver
necessidade" (RC-118) — este item não propõe reabrir essa decisão, só registra
que ela é a base de todos os itens seguintes.

**Referência de rotina.** Manual, "Vínculo às estruturas de demonstração",
páginas 769-771.

**Fonte normativa.** Não se aplica isoladamente — cada demonstração tem a sua
(ver os itens seguintes).

**Situação no DataLedger.** **Parcial.** O padrão existe para
`classificacao_patrimonial` (CTB-09) e `classificacao_dre` (CTB-10), e
**também** para `classificacao_dlpa` (CTB-13) e `classificacao_dmpl` (CTB-14) —
ambos entregues. **DFC e DVA ainda não têm o campo**; serão criados junto dos
itens CTB-15 e CTB-17.

⚠️ **Corrigido em 04/10/2026 (DL-064).** Este texto dizia que "DLPA, DMPL,
DFC, DVA ainda não existem", quarenta e nove linhas **acima** de o CTB-13
dizer que a DLPA existe. Um documento que se contradiz a 49 linhas de
distância não serve para planejar.

**Depende de.** CTB-09, CTB-10 (são os precedentes que provam o padrão).

**Dados.** Nenhum novo aqui — cada item declara o seu enum e seu campo.

**Regras.** Nenhuma conta é classificada por inferência de código ou nome
(regra já estabelecida para CTB-09/CTB-10, repetida para cada novo campo);
apuração declara pendência em vez de presumir.

**Telas e documentos.** Reaproveita o padrão de `conta_classificacao_dre`
(tela de classificar/reclassificar/remover uma linha de uma conta existente)
para cada nova estrutura.

**Critérios de aceite.** Cada item seguinte define os seus; o critério comum
é "nenhuma conta classificada sem ação explícita do usuário, e a apuração
sempre relata o que falta".

**Não copiar / riscos.** Se um dia a estrutura totalmente configurável (por
empresa, com grupos definidos pelo usuário) for pedida, ela **substitui** este
padrão em vez de conviver com ele — ter os dois ao mesmo tempo duplicaria a
regra "de onde vem a classificação desta conta", o que o AGENTS.md §8 proíbe.

### CTB-13 — DLPA (Demonstração dos Lucros ou Prejuízos Acumulados)

**O que é.** Mostra a movimentação da conta de lucros/prejuízos acumulados no
período: saldo inicial, mais lucro do exercício, menos destinações
(reservas, dividendos), saldo final. É mais simples que a DMPL (CTB-14):
olha só essa conta, não o Patrimônio Líquido inteiro.

**Exemplo.** Saldo inicial de Lucros Acumulados: 0,00. Lucro do exercício:
25.000,00. Constituição de reserva legal (5%): (1.250,00). Distribuição de
dividendos: (10.000,00). Saldo final: 13.750,00.

**Referência de rotina.** Manual, páginas 604-611.

**Fonte normativa.** **Confirmada** em 28/09/2026 — ver
["Fontes normativas das demonstrações contábeis"](../requisitos.md#fontes-normativas-das-demonstrações-contábeis--dl-048-consultadas-em-28092026).
**A premissa que este bloco trazia antes estava ERRADA e foi desmentida pela
fonte:** (a) *"o item 106 da NBC TG 26 permite DLPA em vez de DMPL"* — o item
106 define o conteúdo da **DMPL** e a norma não menciona DLPA em lugar nenhum
(busca textual = 0 ocorrências); (b) *"a Lei 11.941/2009 substituiu a DLPA pela
DMPL em companhias abertas"* — a lei não menciona DMPL e o seu **art. 42 é
VETADO**, não pode ser fundamento. A base real é a **Lei 6.404/76, art. 176,
II** (obrigatoriedade, inciso não revogado) e o **art. 186, I–III**.

**Situação no DataLedger.** **Existe** — entregue pela
[DL-048](../../planos/DL-048-contabilidade-anual-demonstracoes.md), fatia
CTB-12 + CTB-13: campo `classificacao_dlpa` ligado à conta, apuração
`apurar_dlpa`, conciliação com o Balanço e as telas `dlpa` e
`conta_classificacao_dlpa`. Ver também
[`mapa-funcional-contabil.md`](../mapa-funcional-contabil.md).

**Depende de.** CTB-09 (Balanço, para o saldo de PL), CTB-10 (DRE, para o
lucro do exercício), CTB-11 (zeramento, cuja etapa 2 já transfere o resultado
para lucros/prejuízos acumulados — a DLPA é a demonstração **desse**
movimento), e a resposta de HI-26/PE-38 (compensação entre lucros e
prejuízos).

**Dados.** Possível novo campo/estrutura: movimentação da conta de
lucros/prejuízos acumulados por tipo de evento (lucro do período, reserva
constituída, dividendo distribuído, reversão de reserva, ajuste de exercício
anterior) — cada evento é um lançamento já existente (o zeramento gera o
"lucro do período"); a demonstração é uma **leitura estruturada** desses
lançamentos, não um modelo de dado novo de armazenamento (mesmo espírito da
DRE, que lê o movimento por classificação, sem duplicar o lançamento).

**Regras.** Saldo final = saldo inicial + lucro do exercício − destinações
(regra de soma simples, mas cada linha precisa vir de lançamento
identificável); reserva legal, quando existir, seguiria **Lei 6.404/76, art.
193** (a confirmar: limite de 20% do capital social, 5% do lucro líquido do
exercício) — **não implementar o cálculo da reserva legal sem conferir este
artigo na fonte oficial e validar com o Fred**.

**Telas e documentos.** Nova tela, no padrão de `dre.html`/`balanco.html` —
classe **D** (demonstração formal, identificação obrigatória em cada página).

**Critérios de aceite.** Saldo final da DLPA bate com o saldo da conta de
lucros/prejuízos acumulados no Balanço da mesma data (teste de conciliação,
no espírito da regra 7 do mapa funcional); emissão recusada enquanto houver
movimento não classificado (mesmo padrão de CTB-09/CTB-10).

**Perguntas.** O escritório emite DLPA isolada para algum cliente, ou sempre
DMPL (que a supera)? Determina se este item entra como demonstração própria
ou só como uma coluna extraída da DMPL (CTB-14).

### CTB-14 — DMPL (Demonstração das Mutações do Patrimônio Líquido)

**O que é.** Mostra como **cada** conta do Patrimônio Líquido (não só lucros
acumulados) mudou no período: capital social, reservas, lucros acumulados —
uma coluna por conta, uma linha por tipo de evento (saldo inicial, aumento de
capital, lucro do exercício, constituição de reserva, distribuição, saldo
final).

**Exemplo pedido pelo Fred, com números sintéticos.** Capital social
100.000,00; lucro do exercício 25.000,00; distribuição de dividendos
10.000,00; reserva legal 5% do lucro (1.250,00).

| Evento | Capital social | Reserva legal | Lucros acumulados | Total |
| --- | --- | --- | --- | --- |
| Saldo inicial | 100.000,00 | 0,00 | 0,00 | 100.000,00 |
| Lucro do exercício | — | — | 25.000,00 | 25.000,00 |
| Constituição de reserva legal | — | 1.250,00 | (1.250,00) | 0,00 |
| Distribuição de dividendos | — | — | (10.000,00) | (10.000,00) |
| **Saldo final** | **100.000,00** | **1.250,00** | **13.750,00** | **115.000,00** |

Confere: 100.000,00 + 25.000,00 − 10.000,00 = 115.000,00 — a constituição de
reserva é reclassificação interna do PL, não muda o total.

**Referência de rotina.** Manual, páginas 616-622.

**Fonte normativa.** **A confirmar** — preliminar: **Lei 6.404/76, art. 186,
parágrafo único** (introduzido pela Lei 11.941/2009), e **NBC TG 26 (R5),
itens 106-110**, que descrevem o conteúdo mínimo da demonstração das
mutações do PL. **Não conferido em fonte oficial nesta sessão** — conferir
antes de implementar.

**Situação no DataLedger.** **Existe.** Entregue em três etapas da
[DL-061](../../planos/DL-061-dmpl.md): fatia 1 (`apurar_dmpl`,
`ClassificacaoDmpl`, tela `dmpl.html` e classificação por conta — PR #76), a
etapa 2 (coluna de dividendo adicional proposto, evento oposto e texto do
veto — PR #77) e a fatia 2 (marcação manual por lançamento e a API da DMPL —
PR #79). Emitir, conciliar com a DLPA e vetar por divergência já funcionam.

⚠️ **Corrigido em 04/10/2026 (DL-064).** Este item dizia "**Não existe**"
desde 27/09/2026, depois de a DMPL ter sido integrada — e foi por isso que
quase se planejou contra ele. **Nenhum item deste mapa deve carregar
`arquivo:linha` como prova de existência**: as linhas mudam a cada entrega e
todas as citações deste arquivo ficaram deslocadas. A prova é o **símbolo e
o plano**.

**Falta o que a DL-061 registrou como pendência:** comparativo com o
exercício anterior (E6), valor por ação em notas (E8) e a validação
contábil do Fred das escolhas de linha e coluna (BL-626, BL-627).

**Depende de.** CTB-09, CTB-10, CTB-11, CTB-13 (a DLPA é, essencialmente, a
coluna "lucros/prejuízos acumulados" desta demonstração — implementar as duas
juntas, com a mesma leitura estruturada de eventos, evita duas lógicas
divergentes para o mesmo dado).

**Dados.** Mesmo padrão de CTB-13, generalizado para **todas** as contas do
Patrimônio Líquido, não só lucros acumulados: capital social, reservas
(legal, estatutária, de lucros), ajustes de avaliação patrimonial (se
houver), lucros/prejuízos acumulados.

**Regras.** Cada coluna soma corretamente do saldo inicial ao final; o total
geral da última linha bate com o Patrimônio Líquido do Balanço na mesma data
(regra de conciliação, RC-19).

**Telas e documentos.** Nova tela — classe **D**.

**Critérios de aceite.** Teste com o exemplo sintético acima (capital
100.000,00, lucro 25.000,00, distribuição 10.000,00, reserva legal 5%)
produzindo exatamente as linhas e o total de 115.000,00; conciliação com o
Patrimônio Líquido do Balanço.

**Perguntas.** Quais tipos de reserva o escritório usa na prática, além da
legal (estatutária, de lucros a realizar, de incentivos fiscais)? Determina
o conjunto de colunas necessário além do mínimo (capital, reserva legal,
lucros acumulados).

### CTB-15 — DFC (Demonstração dos Fluxos de Caixa, direto e indireto) e acompanhamento

**O que é.** Mostra de onde veio e para onde foi o caixa da empresa no
período, separado em três atividades: operacionais, de investimento e de
financiamento. O **método direto** lista os recebimentos e pagamentos
efetivos; o **método indireto** parte do lucro líquido e ajusta pelos itens
que não movimentam caixa (depreciação, variações de contas a receber/pagar).

**Exemplo (indireto, resumido).** Lucro líquido 90.000,00 + Depreciação
15.000,00 (não afeta caixa) − Aumento de Contas a Receber 20.000,00 = Caixa
gerado nas operações 85.000,00; Caixa usado em investimentos (30.000,00);
Caixa gerado em financiamentos 10.000,00; Variação líquida do caixa
65.000,00; Caixa inicial 40.000,00; Caixa final 105.000,00.

**Referência de rotina.** Manual, páginas 622-631 (DFC) e 666-667
(acompanhamento).

**Fonte normativa.** **A confirmar** — preliminar: **Lei 6.404/76, art. 176,
IV** (introduzido pela Lei 11.638/2007, obrigatória para companhias abertas
e sociedades de grande porte) e **NBC TG 03 (R3)** (Demonstração dos Fluxos
de Caixa, equivalente ao CPC 03). **Não conferido em fonte oficial nesta
sessão.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-09 (Balanço, para as variações patrimoniais), CTB-10
(DRE, para o lucro líquido do método indireto), e — para o **método
direto**, que lista recebimentos/pagamentos efetivos — CTB-40/CTB-41 (extrato
bancário e conciliação), porque sem eles a separação entre "o que é caixa" e
"o que é apenas lançamento contábil" depende de inferência pela conta, que é
frágil.

**Dados.** Classificação de cada conta (ou de cada lançamento) por atividade
(operacional, investimento, financiamento) — novo campo, mesmo padrão de
CTB-12; para o método indireto, identificação de quais contas de resultado
são "não caixa" (depreciação, amortização, provisões).

**Regras.** Caixa inicial + variação líquida = caixa final, e esse caixa
final bate com o saldo de Caixa e Equivalentes de Caixa do Balanço na mesma
data (regra de "acompanhamento da DFC" que o próprio manual nomeia, páginas
666-667 — é a mesma exigência que o [catalogo-de-relatorios.md](../catalogo-de-relatorios.md)
já registra: *"a DFC deve reconciliar caixa do início e do fim"*).

**Telas e documentos.** Nova tela — classe **D**.

**Critérios de aceite.** Caixa final da DFC igual ao saldo de Caixa e
Equivalentes do Balanço na mesma data, em teste que gera lançamentos
sintéticos e confere os dois relatórios.

**Não copiar / riscos.** O método direto exige saber, por lançamento, se ele
representa caixa de fato — sem uma dimensão própria para isso (ou sem
depender do extrato bancário conciliado), o risco é **inferir** pela conta
("é banco, então é caixa"), o que erra sistematicamente com lançamentos de
ajuste, provisão e reclassificação que passam pela conta banco sem ser fluxo
de caixa real.

**Perguntas.** O escritório precisa do método direto, do indireto, ou dos
dois? O indireto é mais barato (não depende de CTB-40/41) e é o mais comum na
prática brasileira — mas a decisão é do Fred.

### CTB-16 — DRA (Demonstração do Resultado Abrangente)

**O que é.** Mostra o lucro líquido do período mais os "outros resultados
abrangentes" — ganhos e perdas que a norma manda reconhecer diretamente no
Patrimônio Líquido, sem passar pela DRE (ex.: ajuste de avaliação
patrimonial, variação cambial de investimento no exterior).

**Exemplo.** Lucro líquido do exercício 90.000,00 + Ajuste de avaliação
patrimonial (ganho não realizado) 8.000,00 = Resultado abrangente total
98.000,00.

**Referência de rotina.** Manual, páginas 593-599.

**Fonte normativa.** **A confirmar** — preliminar: **NBC TG 26 (R5), itens
81-105** (resultado abrangente) e o **CPC 26**. **Não conferido nesta
sessão.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-10 (DRE, ponto de partida do lucro líquido).

**Dados.** Novo campo de classificação para contas de "outros resultados
abrangentes" (mesmo padrão de CTB-12), tipicamente contas de Patrimônio
Líquido que recebem lançamento direto sem passar por conta de resultado.

**Regras.** Resultado abrangente total = lucro líquido da DRE + outros
resultados abrangentes do período (soma simples, mas cada componente precisa
de classificação explícita).

**Telas e documentos.** Nova tela — classe **D**.

**Critérios de aceite.** A definir junto do plano de etapa; conciliação com o
lucro líquido da DRE como piso mínimo.

**Perguntas.** Algum cliente da carteira tem operação que gera "outros
resultados abrangentes" (ajuste a valor justo de instrumento financeiro,
investimento no exterior, plano de benefício definido)? Se nenhum tiver, este
item pode ficar em espera — é o tipo de demonstração que só se aplica a
poucas empresas, tipicamente maiores.

### CTB-17 — DVA (Demonstração do Valor Adicionado)

**O que é.** Mostra quanto de riqueza a empresa gerou no período (receita
menos insumos adquiridos de terceiros) e para quem essa riqueza foi
distribuída: empregados, governo (impostos), financiadores (juros), sócios
(lucros retidos e distribuídos).

**Exemplo (resumido).** Valor adicionado a distribuir: 300.000,00.
Distribuição: Pessoal e encargos 150.000,00 (50%); Impostos, taxas e
contribuições 70.000,00 (23%); Remuneração de capital de terceiros (juros)
15.000,00 (5%); Remuneração de capital próprio (lucros) 65.000,00 (22%).

**Referência de rotina.** Manual, páginas 599-604.

**Fonte normativa.** **A confirmar** — preliminar: **Lei 6.404/76, art. 176,
§4º** (obrigatória para companhias abertas) e **NBC TG 09** (equivalente ao
CPC 09). **Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-10 (DRE, para receita e insumos), CTB-12.

**Dados.** Classificação de conta por tipo de distribuição de valor
adicionado (pessoal, impostos, juros, aluguéis, lucros) — novo campo, mesmo
padrão de CTB-12.

**Regras.** Valor adicionado total distribuído = valor adicionado a
distribuir (a demonstração **tem** que fechar em si mesma, é a sua própria
partida dobrada conceitual).

**Telas e documentos.** Nova tela — classe **D**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Perguntas.** Algum cliente da carteira é companhia aberta ou de porte que
exija DVA na prática? É demonstração de uso mais restrito que Balanço/DRE.

### CTB-18 — Notas explicativas

**O que é.** Textos que complementam as demonstrações contábeis, explicando
critérios de avaliação, detalhando composição de contas, ou informando fatos
relevantes não visíveis nos números (ex.: "nota 5 — composição do
imobilizado", "nota 12 — processos judiciais em curso").

**Referência de rotina.** Manual, "Configuração de notas explicativas",
páginas 162-166 (cadastro) e 645-646 (emissão).

**Fonte normativa.** **NBC TG 26 (R5), itens 112-138**, que exigem notas como
parte integrante das demonstrações — **já citada em geral em requisitos.md**
(RC-95 cobre o cabeçalho, não o conteúdo das notas); conteúdo específico
**a confirmar** por nota, caso a caso, conforme a operação de cada empresa.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-09, CTB-10 (as notas remetem a valores dessas
demonstrações).

**Dados.** Modelo novo: nota (número, título, texto), vinculável a uma
competência/exercício e, opcionalmente, a uma conta ou grupo específico.
Texto pode ser modelo com variáveis (mesmo padrão de histórico do CTB-37) ou
livre.

**Regras.** Nota numerada sequencialmente por demonstração/exercício; nota
referenciada no corpo da demonstração (ex.: "ver nota 5") precisa existir.

**Telas e documentos.** Nova tela de cadastro e emissão — classe **D**
(compõe a demonstração formal).

**Critérios de aceite.** A definir junto do plano de etapa: nota sem
numeração é recusada; referência cruzada entre demonstração e nota é
verificável.

**Não copiar / riscos.** O mapa funcional já registrou (categoria "Não
adotar" de [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md)):
"biblioteca ampla de notas explicativas com visibilidade nota a nota" é
funcionalidade que pressupõe rotina de demonstração formal extensa, fora do
que o escritório emite no dia a dia — implementar uma versão simples primeiro
e ampliar só sob demanda real.

**Perguntas.** O escritório do Fred emite notas explicativas hoje, para quais
clientes e com que conteúdo típico? Sem essa resposta, o conjunto de
"variáveis" do modelo de texto fica no vazio.

### CTB-19 — Análise vertical e horizontal

**O que é.** A análise vertical mostra cada conta como percentual do total do
seu grupo (ex.: "Custo é 44% da Receita Líquida"); a horizontal mostra a
variação de cada conta entre dois períodos (ex.: "Receita cresceu 12% em
relação ao ano anterior").

**Exemplo.** Vertical: Receita líquida 450.000,00 (100%); Custo 200.000,00
(44,4%); Lucro bruto 250.000,00 (55,6%). Horizontal: Receita líquida 2025
400.000,00 → 2026 450.000,00 (+12,5%).

**Referência de rotina.** Manual, páginas 568-577.

**Fonte normativa.** Não é exigência normativa — é técnica de análise
financeira, sem leiaute oficial. Classe **C** ou **D** conforme for anexada a
uma demonstração formal ou emitida solta.

**Situação no DataLedger.** **Não existe.** A base que destrava este item —
`apurar_saldos` (CTB-09) — **já existe**, o que torna este item
predominantemente uma questão de **cálculo sobre dado já apurado**, não de
captura de dado novo.

**Depende de.** CTB-09, CTB-10 (fornecem os totais e os movimentos que a
análise divide).

**Dados.** Nenhum modelo novo — cálculo sobre `apurar_saldos`/`apurar_dre` de
dois períodos.

**Regras.** Percentual vertical usa como base 100% o total do grupo (Ativo
total, Receita líquida, conforme a demonstração); percentual horizontal
recusa divisão por zero (conta que não existia no período anterior é
declarada como "nova", não como "infinito%" ou erro silencioso.

**Telas e documentos.** Colunas adicionais nas telas de Balanço/DRE já
existentes, ou relatório próprio — classe **C**/**D** conforme o caso.

**Critérios de aceite.** Soma dos percentuais verticais de um grupo bate com
100% (± arredondamento, com a política declarada); teste com conta nova no
período (sem base de comparação) tratado explicitamente.

### CTB-20 — Coeficientes de análise (índices) e EBITDA

**O que é.** Indicadores financeiros calculados a partir do Balanço e da DRE:
liquidez corrente, liquidez seca, endividamento, margem líquida, EBITDA
(lucro antes de juros, impostos, depreciação e amortização) e outros.

**Exemplo.** Liquidez corrente = Ativo Circulante ÷ Passivo Circulante. Com
Ativo Circulante 180.000,00 e Passivo Circulante 90.000,00, o índice é 2,00
— a empresa tem R$ 2,00 de recursos de curto prazo para cada R$ 1,00 de
dívida de curto prazo.

**Referência de rotina.** Manual, páginas 352-355 (cadastro dos índices),
577-582 e 637-642 (emissão, incluindo EBITDA).

**Fonte normativa.** Não é exigência normativa; EBITDA em particular não tem
definição legal única no Brasil — a **Instrução CVM 527/2012** disciplina a
divulgação voluntária de EBITDA/LAJIDA para companhias abertas. **A
confirmar** se aplicável à carteira do escritório (provavelmente não, se a
carteira é de empresas fechadas).

**Situação no DataLedger.** **Não existe.** Mesma observação de CTB-19: a
base (saldos e DRE) já existe.

**Depende de.** CTB-09, CTB-10.

**Dados.** Igual à ideia estrutural 4 do mapa funcional: **quais contas
compõem cada índice é configuração, não dedução automática do plano de
contas** — precisa de um cadastro de fórmula/composição por índice, não de
um cálculo fixo que presuma nomes de conta.

**Regras.** Fórmula de cada índice é explícita e versionada (nunca hardcoded
com nome de conta assumido); divisão por zero (ex.: Passivo Circulante zerado)
é tratada e declarada, nunca gera erro cru nem "infinito" silencioso.

**Telas e documentos.** Nova tela — classe **C**/**D** conforme uso.

**Critérios de aceite.** A definir junto do plano de etapa: cada índice tem
teste com valores sintéticos conferidos à mão.

### CTB-21 — Comparativo de movimento entre períodos / Balancete comparativo

**O que é.** Duas (ou mais) colunas lado a lado, cada uma de um período, para
o mesmo conjunto de contas — permite ver "quanto mudou" sem abrir dois
relatórios.

**Referência de rotina.** Manual, páginas 356-358 (cadastro) e 657-660
(emissão); item 16 do catálogo (Balancete Comparativo).

**Fonte normativa.** Relatório de conferência — classe **C**, sem norma de
forma.

**Situação no DataLedger.** **Não existe**, mas é **barato**: `apurar_balancete`
já aceita `inicio`/`fim` como parâmetros; comparar dois períodos é chamar a
função duas vezes e juntar o resultado por conta.

**Depende de.** CTB-05.

**Dados.** Nenhum modelo novo.

**Regras.** As duas colunas usam o **mesmo** critério de apuração (RC-97 —
sem isso, "comparar" dois números que vêm de critérios diferentes é enganoso);
conta que só existe num dos dois períodos aparece com zero declarado no outro,
não omitida.

**Telas e documentos.** Nova visão da tela de Balancete — classe **C**.

**Critérios de aceite.** A soma de cada coluna bate com o Balancete do
período respectivo, emitido isoladamente (teste de conciliação cruzada).

### CTB-22 — Gráficos

**O que é.** Representação visual (barras, pizza, linha) de saldos, evolução
de receita/despesa, composição do Ativo, etc.

**Referência de rotina.** Manual, páginas 646-650.

**Fonte normativa.** Não se aplica — recurso de interface.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-09, CTB-10, CTB-19 (a mesma base de dados que alimenta a
análise vertical/horizontal alimenta gráficos).

**Dados.** Nenhum modelo novo — camada de apresentação sobre dado já
existente.

**Regras.** Gráfico nunca é a única forma de acesso ao dado (acessibilidade —
sempre ao lado da tabela numérica que o gerou); nenhuma regra contábil nova.

**Telas e documentos.** Complemento visual das telas já existentes — classe
**C**.

**Critérios de aceite.** A definir junto do `especialista-frontend` quando
priorizado; é o item de menor urgência contábil de toda a Onda 1.

### CTB-23 — Contas sem movimentação

**O que é.** Relatório que lista contas do plano que não tiveram nenhum
lançamento no período (ou desde sempre) — útil para limpeza de plano de
contas e para conferir se uma conta esperada realmente não foi usada.

**Referência de rotina.** Item 23 do catálogo de 120 relatórios (Contas sem
Movimentação) — não aparece nomeado assim no manual de 856 páginas, mas é
capacidade trivial sobre dado já existente.

**Fonte normativa.** Relatório de conferência — classe **C**.

**Situação no DataLedger.** **Não existe**, e é **barato**: consulta direta
sobre `Conta` e `ItemLancamento` (contas sem nenhum `ItemLancamento` no
período, ou sem nenhum desde a criação).

**Depende de.** CTB-01, CTB-02 — nenhuma outra dependência; pode ser feito a
qualquer momento.

**Dados.** Nenhum modelo novo.

**Regras.** Distinguir "sem movimento no período consultado" (pode ter
movimento em outro período) de "sem movimento desde sempre" (candidata a
revisão/desativação) — são perguntas diferentes.

**Telas e documentos.** Nova aba na tela de Conferência (CTB-06) — classe
**C**.

**Critérios de aceite.** Lista bate com a diferença entre "todas as contas
ativas" e "contas com ao menos um `ItemLancamento` no período".

## Onda 2 — Encerramento do exercício, termos, livro encadernável, sócios e contador

### CTB-24 — Encerramento do exercício (formal) e compensação de lucros/prejuízos acumulados

**O que é.** Diferente do fechamento **mensal** de competência (CTB-07) e do
zeramento **periódico** de resultado (CTB-11, que já existe e roda todo mês,
trimestre ou ano conforme o parâmetro): o encerramento do exercício é o ato
**anual** formal que consolida o ano inteiro, prepara as demonstrações
definitivas e — quando aplicável — compensa lucros e prejuízos acumulados de
anos diferentes.

**Referência de rotina.** Manual, item 25 do catálogo (Encerramento do
Exercício); páginas 92-95, 840-841 (mesmas do zeramento — o manual trata os
dois como a mesma tela com parâmetro de periodicidade, mas a rotina do
**exercício** especificamente inclui os termos, que o zeramento mensal não
gera).

**Fonte normativa.** **A confirmar.** A compensação de prejuízos fiscais tem
regra própria (Lei 9.065/1995, limite de 30% do lucro real — **isso é matéria
de Lalur/ECF, fora deste módulo**, ver CTB-74); a compensação **contábil**
(não fiscal) de lucros e prejuízos acumulados entre exercícios não tem um
dispositivo único identificado nesta sessão.

**Situação no DataLedger.** **Não existe** como ato distinto — o zeramento
periódico (CTB-11) já existe e, com periodicidade "anual", produz o efeito
aritmético do encerramento, mas **sem** os termos (CTB-25), sem compensação
entre exercícios (HI-26/PE-38 seguem abertas) e sem o desfazimento de
zeramento com parâmetro errado (PE-69, aberta).

**Depende de.** CTB-07, CTB-11, CTB-13 (DLPA, que é a demonstração natural
desse movimento).

**Dados.** Nenhum modelo necessariamente novo — pode reaproveitar
`ParametroContabilEmpresa`/`zerar_resultado` com periodicidade anual; a
compensação entre exercícios, se vier a existir, é um novo tipo de
lançamento com origem própria (mesmo padrão de CTB-32).

**Regras.** A definir com o Fred (HI-26/PE-38/PE-69) antes de qualquer
implementação de compensação — implementar sem essa resposta arrisca
inventar procedimento contábil.

**Telas e documentos.** Estende `fechamento.html`/`zerar_resultado.html` —
classe **C** (operação) com efeito em demonstração **D** (DLPA/DMPL).

**Critérios de aceite.** A definir junto do plano de etapa, depois da
resposta às perguntas abertas.

**Perguntas.** As três já registradas em [requisitos.md](../requisitos.md):
HI-26 (o zeramento compensa lucros com prejuízos acumulados, ou é lançamento
separado?), PE-38 (tratamento de lucros/prejuízos acumulados na implantação
de saldos) e PE-69 (como desfazer um zeramento feito com parâmetro errado).

### CTB-25 — Termos de abertura, encerramento e transferência

**O que é.** Textos formais que abrem e fecham um livro contábil (Diário,
Razão): declaram quantas folhas o livro tem, o período que cobre, e são
assinados pelo titular/representante legal e pelo contabilista habilitado. O
termo de transferência documenta a passagem de saldo de um livro para o
seguinte.

**Referência de rotina.** Manual, páginas 290-293.

**Fonte normativa.** **NBC ITG 2000 (R1), itens 9 e 10** — livro não digital:
encadernado, folhas numeradas sequencialmente, termo de abertura e de
encerramento assinados pelo titular e pelo profissional da contabilidade
habilitado no CRC; livro digital: assinado digitalmente pelos dois, e
autenticado no registro público quando exigido por legislação específica —
**já conferida na fonte primária**, registrada como **RC-96**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-26 (o termo só existe amarrado a um livro), CTB-28
(sócio/titular que assina), CTB-29 (contador que assina).

**Dados.** Modelo novo: termo (tipo — abertura/encerramento/transferência,
livro vinculado, número de folhas, período, data, signatários).

**Regras.** Termo referencia número do livro, período e páginas consistentes
com o próprio livro; não existe termo sem livro correspondente (BL-71).

**Telas e documentos.** Parte da emissão do livro (CTB-26) — classe **L**.

**Critérios de aceite.** Teste de coerência entre termo e livro (mesmo
período, mesma contagem de páginas).

**Perguntas.** **PE-52**, já registrada: qual é a legislação específica que
exige autenticação do livro contábil digital, e o que ela impõe ao arquivo —
a NBC ITG 2000 item 10(b) remete a ela sem nomeá-la.

### CTB-26 — Livro contábil na forma de livro (Diário/Razão numerados e encadernáveis)

**O que é.** A emissão do Diário e do Razão **não** como relatório de
conferência solto, mas como **livro** formal: folhas numeradas
sequencialmente, sem espaço em branco onde se possa inserir algo depois, com
termo de abertura e encerramento.

**Referência de rotina.** Manual, páginas 299-358 (a maior seção do manual
inteiro dedicada a um único assunto — 60 páginas).

**Fonte normativa.** **NBC ITG 2000 (R1), item 5(d)**: escrituração "com
ausência de espaços em branco, entrelinhas, borrões, rasuras ou emendas";
itens 9, 10, 12, 13 — **já conferida na fonte primária**, registrada como
**RC-96**.

**Situação no DataLedger.** **Não existe.** O Diário (CTB-03) e o Razão
(CTB-04) existem como relatório de conferência; a forma de livro (numeração
sem buraco, termo, ausência de espaço em branco) não existe.

**Depende de.** CTB-03, CTB-04, CTB-25, CTB-29 (Diário transcreve as
demonstrações contábeis com a assinatura do contabilista — NBC ITG 2000 item
13).

**Dados.** Modelo novo: `LivroContabil` — empresa, tipo (Diário/Razão),
número sequencial, período coberto, data de emissão. `UniqueConstraint` por
empresa e tipo garantindo sequência sem buraco e sem repetição, inclusive
sob concorrência (BL-70 já descreve o critério de aceite).

**Regras.** Número atribuído na emissão, nunca antes (evita número "gasto"
por emissão cancelada); um livro emitido não muda de número; recusa de dois
livros com o mesmo número testada sob concorrência (BL-70).

**Telas e documentos.** Nova tela de emissão de livro — classe **L**,
**quase sem margem de personalização** (RC-96 — forma, numeração, termos e
assinaturas são prescritos).

**Critérios de aceite.** Já descritos em **BL-70**/**BL-71**: sequência sem
buraco e sem repetição sob concorrência; termo coerente com o livro; teste de
recusa de reuso de número.

**Não copiar / riscos.** Este é o documento onde a personalização de
relatório (RC-97, DL-027) **não pode** entrar — a matriz de caixinhas
"imprimir CNPJ no Diário? no Balanço?" é vetada justamente porque a forma do
livro é prescrita, não escolhida ([personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md),
categoria "Não adotar").

**Perguntas.** **PE-60** e **PE-61**, já registradas: o termo precisa dos
dados cadastrais da empresa **como eram na data**, ou os atuais? E o que
precisa sair em cada folha (não só a primeira) — nome da empresa, período,
número de folha?

### CTB-27 — Carta de responsabilidade da administração

**O que é.** Documento em que a administração da empresa declara que as
demonstrações contábeis apresentadas são de sua responsabilidade e refletem
adequadamente a situação patrimonial — assinado pelo titular/sócios e pelo
contador.

**Referência de rotina.** Manual, páginas 296-298.

**Fonte normativa.** Não é exigência legal obrigatória para todas as
empresas — é prática de boa governança e, em auditoria externa, é peça
padrão pedida pelo auditor independente (**NBC TA 580**, a confirmar se
aplicável fora do contexto de auditoria).

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-28 (sócios), CTB-29 (contador).

**Dados.** Modelo simples: texto-modelo com variáveis (razão social, período,
signatários) — mesmo padrão de histórico modelo (CTB-37).

**Regras.** Nenhuma regra contábil própria; é documento textual.

**Telas e documentos.** Nova tela de emissão — classe **D** (acompanha
demonstração formal).

**Critérios de aceite.** A definir junto do plano de etapa.

**Perguntas.** O escritório do Fred usa este documento na prática, para quais
clientes (só os que têm auditoria externa, ou todos)?

### CTB-28 — Sócios e quadro societário

**O que é.** O cadastro de quem são os sócios/acionistas de cada empresa
cliente, com participação percentual e **vigência** (quem entrou, quem saiu,
quando).

**Referência de rotina.** Manual, páginas 48-61.

**Fonte normativa.** Não há leiaute único — dado cadastral. A composição
societária é relevante para a ECD (CTB-51) e para a assinatura de termos
(CTB-25) e da carta de responsabilidade (CTB-27).

**Situação no DataLedger.** **Não existe.** `Empresa` (`apps/empresas/models.py`)
não tem quadro societário.

**Depende de.** — (é cadastral, como `Empresa`).

**Dados.** Modelo novo: sócio (pessoa física ou jurídica, CPF/CNPJ, nome),
vínculo com a empresa (percentual de participação, cargo/função, vigência de
início e fim) — mesmo padrão de vigência de `HistoricoRegimeTributario`
(DE-039), já aceito no projeto para "parâmetro que muda no tempo".

**Regras.** Soma dos percentuais de participação vigentes não deveria
ultrapassar 100% (a confirmar se o produto **recusa** ou só **avisa** — cotas
em usufruto, condomínio de ações e outras situações societárias podem fugir
da soma simples); vigência não sobreposta por sócio.

**Telas e documentos.** Nova tela de cadastro — classe **C** (cadastral).

**Critérios de aceite.** A definir junto do plano de etapa; teste de
vigência não sobreposta.

**Não copiar / riscos.** **BL-393**, já registrado: sócio, contador e
responsável podem ser a **mesma pessoa física** em papéis diferentes — ver
CTB-58, decisão de modelagem que precisa ser tomada **antes** deste item
nascer, porque decidir depois do primeiro cadastro custa deduplicação manual.

### CTB-29 — Contador responsável técnico (CRC)

**O que é.** O cadastro do profissional de contabilidade habilitado
(registro no CRC) responsável técnico por cada empresa cliente — o nome que
assina as demonstrações, os termos de livro e a carta de responsabilidade.

**Referência de rotina.** Manual, páginas 62-65.

**Fonte normativa.** **NBC ITG 2000 (R1), item 12**: "a escrituração contábil
e a emissão de relatórios, peças, análises, demonstrativos e demonstrações
contábeis são de atribuição e de responsabilidade exclusivas do profissional
da contabilidade legalmente habilitado" — **já conferida na fonte primária**,
registrada como **RC-96**. A obrigação de registro no CRC vem do
**Decreto-Lei 9.295/1946** (que criou o CFC e os CRCs) — **a confirmar** o
dispositivo exato.

**Situação no DataLedger.** **Não existe** como cadastro; a **identificação
do profissional responsável** já é obrigação do documento emitido (RC-97,
DL-027 — "o documento identifica o escritório e o profissional responsável,
não o usuário operador"), mas o **cadastro estruturado** (nome, CRC, vínculo
com cada empresa, vigência) não existe.

**Depende de.** — (é cadastral).

**Dados.** Modelo novo: contador (nome, número de registro CRC, UF do
registro), vínculo com a empresa (vigência de início e fim, no molde de
CTB-28).

**Regras.** Toda empresa ativa tem, no mínimo, um contador responsável
vigente antes de poder emitir demonstração formal (classe D) ou livro (classe
L) — é o mesmo espírito da recusa de emissão por pendência de classificação
(CTB-09/CTB-10), aplicado a um dado cadastral em vez de um saldo.

**Telas e documentos.** Nova tela de cadastro — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; emissão de
demonstração/livro sem contador responsável vigente é recusada com mensagem
clara (mesmo padrão de `avaliar_emissao_do_balanco`/`avaliar_emissao_da_dre`).

### CTB-30 — Histórico cadastral da empresa consultável por data

**O que é.** A capacidade de responder "como era o cadastro desta empresa
(razão social, endereço) **na data X**", não só "como é hoje" — necessária
para o termo do livro (CTB-25), que precisa mostrar o cadastro como era no
período coberto pelo livro, não o cadastro atual se ele mudou depois.

**Referência de rotina.** Não é item nomeado isoladamente no manual — é
achado da leitura integral registrado como **BL-396**.

**Fonte normativa.** Não se aplica diretamente — é capacidade de dado, não
regra de cálculo.

**Situação no DataLedger.** **Parcial, e a diferença importa.** O valor
**anterior** de um campo alterado pelo admin **fica registrado** em
`RegistroAuditoria.detalhes` (trilha desde a DL-024/BL-244, confirmado por
execução: `test_dl024_trilha_admin.py` → `7 passed`) — mas como **prova de
que existiu**, não como um cadastro que o produto consiga **ler por data**.
Não existe `HistoricoCadastralEmpresa` consultável.

**Depende de.** — (é sobre `Empresa`, cadastral).

**Dados.** Modelo novo: histórico de alteração cadastral, com vigência (mesmo
padrão de `HistoricoRegimeTributario`) — para os campos que a identificação
do documento usa (razão social, endereço, e o que RC-93 vier a exigir).

**Regras.** Consulta "cadastro da empresa na data X" nunca lê o registro de
auditoria (que é trilha técnica, não fonte de leitura estruturada) — lê a
tabela de histórico própria.

**Telas e documentos.** Nenhuma tela nova diretamente — é dado consumido por
CTB-25 (termo do livro).

**Critérios de aceite.** A definir junto do plano de etapa (é pré-requisito
de CTB-25, não item isolado de alto valor por si).

**Perguntas.** **PE-60**, já registrada: o termo precisa do cadastro **como
era** na data do período, ou do cadastro **atual**? E, na prática, com que
frequência um cliente muda de razão social a ponto de isso importar?

### CTB-31 — Perfis de empresa (modelo para cliente novo)

**O que é.** Um "molde" de configuração (plano de contas padrão, parâmetros
contábeis, estrutura de demonstrações) que pode ser aplicado de uma vez ao
abrir uma empresa cliente nova, em vez de configurar tudo do zero.

**Referência de rotina.** Manual, páginas 46-48.

**Fonte normativa.** Não se aplica — é recurso de produtividade do
escritório, sem regra contábil própria.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01 (plano de contas), CTB-11 (parâmetro contábil) — o
perfil é, essencialmente, um conjunto desses dados marcado como "modelo" em
vez de pertencer a uma empresa real.

**Dados.** Modelo novo: perfil (nome, plano de contas de referência,
parâmetros padrão) e o serviço de "aplicar perfil a empresa nova" (copia a
estrutura, sem criar vínculo permanente — depois de aplicado, a empresa tem
seu próprio plano, independente).

**Regras.** Aplicar um perfil nunca sobrescreve configuração já existente de
uma empresa que já tem dado — só faz sentido em empresa recém-criada, sem
lançamento.

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; teste de que
aplicar o mesmo perfil a duas empresas produz planos de contas
**independentes** (edição num não afeta o outro).

**Não copiar / riscos.** Relaciona-se com **CTB-62** (cópia de configuração
entre empresas do escritório) — são capacidades próximas; avaliar se um
"perfil" é só um caso especial de "copiar de uma empresa-modelo" antes de
construir os dois separadamente.

## Depois

Itens sem urgência de onda fixa — cada um forma sua própria cadeia, priorizável
por demanda real do escritório, não por dependência técnica entre si.

### CTB-32 — Origem e documento de origem no lançamento contábil

**O que é.** Dois campos que `LancamentoContabil` **não tem** hoje: de onde o
lançamento veio (digitado manualmente, gerado pela escrita fiscal, gerado
pela folha) e, quando aplicável, qual documento o originou (qual nota fiscal,
qual folha de pagamento). Sem isso, não há como distinguir lançamento
manual de lançamento derivado, nem navegar do documento ao lançamento e
vice-versa.

**Referência de rotina.** Não é item isolado do manual — é achado do mapa
funcional (ideia estrutural 5, "Origem: distinguir lançamento digitado de
lançamento gerado por outro processo") e do mapa de integração fiscal→contábil.

**Fonte normativa.** Não se aplica — é decisão de modelagem interna.

**Situação no DataLedger.** **Não existe** (**BL-72**, `planejada`).

**Depende de.** CTB-02.

**Dados.** Campo `origem` (valores controlados: manual, escrita fiscal,
folha, importação, zeramento — este último já usa prefixo de chave
reservado, DE-078 §6) e `documento_origem_id`/`documento_origem_tipo`
(referência genérica ao documento de outro app) em `LancamentoContabil`.

**Regras.** Origem não é alterável depois de gravada; consulta que parte do
documento e chega aos lançamentos, e o caminho inverso, isolada por empresa
(BL-72).

**Telas e documentos.** Campo visível em `lancamento_detalhe.html` — classe
**C**.

**Critérios de aceite.** Já descritos em **BL-72**: campo de origem com
valores controlados; referência ao documento de origem quando houver;
consulta bidirecional testada; teste de isolamento entre empresas.

**Não copiar / riscos.** Entra junto de uma migração que também resolve a
constraint de banco pendente (item, conta e lançamento da mesma empresa —
DE-021), para não gerar duas migrações do mesmo modelo (nota já registrada
em **BL-72**).

### CTB-33 — Centro de custo e departamento (cadastro e habilitação)

**O que é.** Uma segunda dimensão de classificação do lançamento, além da
conta: "esta despesa foi da filial Centro ou da filial Zona Sul?", "este
custo foi do departamento Comercial ou de Produção?". Usado por **parte**
das empresas do escritório, não por todas (RC-54).

**Referência de rotina.** Manual, páginas 160-161 (cadastro), 692-696
(relatórios).

**Fonte normativa.** Não se aplica — é dimensão gerencial, sem leiaute
oficial.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01.

**Dados.** Modelo novo: departamento (empresa, nome), centro de custo
(departamento, código, nome), habilitação por empresa **a partir de uma
data** (RC-55 — habilitar não altera lançamento já gravado).

**Regras.** Isolamento entre empresas; lançamento anterior à data de
habilitação não é afetado retroativamente (RC-55).

**Telas e documentos.** Nova tela de cadastro — classe **C**.

**Critérios de aceite.** Já descritos em **BL-67**: departamento e centro de
custo por empresa; parâmetro de habilitação com data de início; lançamento
anterior à data não é afetado; isolamento testado.

### CTB-34 — Rateio por centro de custo (conta e partida)

**O que é.** Percentuais de distribuição, definidos na **conta** contábil,
que se propõem automaticamente quando o contador lança naquela conta — por
exemplo, "Aluguel" sempre rateado 60% Comercial / 40% Produção — e que o
contador confere e pode ajustar em cada lançamento.

**Referência de rotina.** Manual, RC-55 (rotina confirmada pelo Fred em
2026-09-13, com base em material público).

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-33.

**Dados.** Percentual de rateio vinculado à conta (por centro de custo), e o
rateio efetivamente **materializado** na partida (`ItemLancamento`) — ver o
achado **BL-401**/**BL-394**: o campo pertence à **partida** (`ItemLancamento`),
não ao lote (`LancamentoContabil`), porque duas linhas do mesmo lançamento
podem ir a centros diferentes.

**Regras.** Percentuais da conta somam exatamente 100%; o rateio gravado no
lançamento soma **exatamente** o valor da partida, sem centavo perdido — a
diferença de arredondamento tem destino definido e testado (DE-010); alterar
o percentual da conta **não** altera lançamento já gravado (BL-68).

**Telas e documentos.** Parte da tela de lançamento — classe **C**.

**Critérios de aceite.** Já descritos em **BL-68**.

**Não copiar / riscos.** O mapa funcional registra "rateio gerencial (segunda
dimensão paralela)" como **decisão do Fred**, não confirmada — ver CTB-59
para a fronteira entre isso e consolidação entre empresas.

### CTB-35 — Saídas filtráveis por centro de custo

**O que é.** Diário, Razão, Balancete e — quando existirem — Balanço e DRE,
todos com a opção de filtrar por um ou vários centros de custo.

**Referência de rotina.** Manual, RC-55.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-34.

**Dados.** Nenhum modelo novo — filtro sobre o campo de CTB-34.

**Regras.** A soma dos valores de todos os centros de custo de um período é
igual ao total do mesmo período sem filtro; contas sem rateio têm tratamento
explícito e declarado na resposta, nunca omitidas em silêncio (BL-69).

**Telas e documentos.** Filtro adicional nas telas existentes de CTB-03,
CTB-04, CTB-05 — classe **C**.

**Critérios de aceite.** Já descritos em **BL-69**.

### CTB-36 — Lançamentos orçados e orçamento × realizado

**O que é.** Registrar, por competência, quanto **se espera** movimentar em
cada conta (o orçamento), e comparar depois com o que **de fato** foi
lançado (o realizado) — "orçamos 10.000,00 de Marketing em março; gastamos
8.500,00".

**Referência de rotina.** Manual, páginas 236-238 (lançamentos orçados),
696-703 (orçamento × realizado).

**Fonte normativa.** Não se aplica — ferramenta gerencial.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-07; opcionalmente CTB-33 (orçamento por centro de
custo).

**Dados.** Modelo novo: lançamento orçado (conta, competência, valor
esperado, opcionalmente centro de custo) — **não** é `LancamentoContabil` (não
é fato contábil efetivado, é expectativa), então não compete com a
imutabilidade do lançamento real.

**Regras.** Orçado nunca soma no Balancete/Razão real — é comparação lado a
lado, nunca mistura de dado.

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa: comparação
orçado × realizado bate exatamente com o Balancete real do mesmo período.

### CTB-37 — Histórico padronizado (catálogo por empresa)

**O que é.** Um catálogo de textos de histórico prontos, por empresa, que o
contador seleciona por código ao lançar — sem abrir mão de digitar um
histórico livre quando quiser.

**Exemplo.** Código `10` → "Recebimento de duplicata". O contador digita `10`
e o texto aparece pronto; se aceitar complemento, pode digitar
"Recebimento de duplicata nº 4521" (complemento acrescentado ao fim — HI-19,
hipótese ainda não confirmada quanto à posição).

**Referência de rotina.** Manual, página 144.

**Fonte normativa.** Não se aplica — é recurso de produtividade.

**Situação no DataLedger.** **Não existe.** `LancamentoContabil.historico` é
`CharField(300)` de texto livre — o caminho livre já está pronto; falta o
catálogo.

**Depende de.** CTB-01 (é por empresa).

**Dados.** Modelo novo: histórico padronizado (empresa, código, texto,
aceita complemento) — **confirmado pelo Fred**: de cada empresa, com código
digitável, aceitando complemento (**RC-109**). O texto gravado no lançamento
é o **resultado montado** no momento do lançamento, nunca uma referência ao
catálogo que mudaria retroativamente o Diário se o catálogo fosse editado
depois (**RC-108** — o mesmo cuidado que RC-107 já aplicou à classificação
circulante/não circulante).

**Regras.** Código único dentro da empresa; unicidade vale também na
**edição**, não só na criação (a lição da HI-15 sobre o código reduzido de
conta se aplica aqui). Padrão + complemento pode ultrapassar os 300
caracteres de `historico` — **truncar em silêncio é proibido**; a etapa
precisa escolher entre recusar com mensagem ou truncar com marca explícita, e
declarar qual (**RC-109**, ressalva já registrada).

**Telas e documentos.** Nova tela de cadastro + seletor na tela de lançamento
— classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa: histórico
gravado no lançamento é imutável mesmo que o catálogo mude depois (teste que
edita o catálogo e confere que lançamentos antigos não mudam).

**Perguntas.** **HI-19**, ainda hipótese: o complemento é sempre acrescentado
ao fim, ou há históricos com uma lacuna no meio da frase (ex.: "Recebimento
de duplicata nº ___ referente a ___")?

### CTB-38 — Lançamento padrão (modelo reutilizável de partidas)

**O que é.** Um modelo de lançamento completo (não só o histórico) —
conjunto de contas e proporções — que o contador aplica repetidamente. Por
exemplo, "rateio mensal de aluguel entre três centros de custo" como um
modelo de 1 débito para 3 créditos, sempre com as mesmas contas.

**Referência de rotina.** Manual, páginas 172-175.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-37 (reaproveita o histórico padronizado).

**Dados.** Modelo novo: lançamento padrão (empresa, nome, itens — conta,
tipo, percentual ou valor fixo).

**Regras.** Aplicar o modelo gera um lançamento comum, sujeito a todas as
regras de CTB-02 (igualdade débito=crédito, competência, teto de partidas);
editar o modelo **não** altera lançamentos já gerados a partir dele (mesmo
princípio de CTB-34/CTB-37).

**Telas e documentos.** Nova tela de cadastro + atalho na tela de lançamento
— classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa.

### CTB-39 — Participantes (terceiros) amarrados à partida

**O que é.** O cadastro de terceiros (clientes, fornecedores, funcionários)
que participam de um lançamento, quando a obrigação ou a conciliação exigir
saber **quem** está do outro lado — por exemplo, para conciliar contas a
receber por cliente.

**Referência de rotina.** Manual, páginas 177-178.

**Fonte normativa.** Não se aplica diretamente — é dado cadastral que
suporta CTB-42 (conciliação de clientes e fornecedores).

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01.

**Dados.** Modelo novo: participante (empresa, tipo — cliente/fornecedor/
funcionário/outro, identificação). Campo de participante na **partida**
(`ItemLancamento`), não no lote (**BL-394**, achado da leitura integral: o
nível certo é a partida, porque duas linhas do mesmo lançamento podem
envolver participantes diferentes).

**Regras.** Isolamento entre empresas; participante não é obrigatório em toda
partida — só quando a conta/obrigação exigir.

**Telas e documentos.** Nova tela de cadastro + campo na tela de lançamento —
classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Não copiar / riscos.** **BL-394** já avisa: se este campo nascer no lote em
vez da partida, corrigir depois é migração de coluna **e** de dado,
"adivinhando a que item pertencia" — decidir o nível **antes** da primeira
linha de código é o que este item existe para garantir.

### CTB-40 — Extrato bancário: importação e regra de contabilização

**O que é.** Importar o extrato de uma conta bancária (arquivo do banco) e
transformar cada linha em lançamento contábil, usando uma **regra** que o
contador cadastra (ex.: "toda linha com a palavra 'TARIFA' vai para a conta
Despesas Bancárias").

**Referência de rotina.** Manual, páginas 167-171 (regra de contabilização),
234-236 (importação e lançamento).

**Fonte normativa.** Não há leiaute oficial único de extrato bancário — cada
banco tem o seu (OFX é o formato mais comum, sem ser obrigatório).

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-32 (a origem do lançamento gerado é "extrato
bancário", não manual).

**Dados.** Modelo novo: regra de contabilização (empresa, critério de
casamento — texto contido, valor, faixa —, conta de contrapartida); área
intermediária de importação (linhas do extrato ainda não contabilizadas, com
status).

**Regras.** Importação **não** grava registro classificado como erro sem
revisão; reimportar o mesmo arquivo não duplica (idempotência por
identificador da transação bancária, quando o formato do arquivo o fornecer,
ou por hash do conteúdo da linha).

**Telas e documentos.** Nova tela de importação — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa: reimportação do
mesmo arquivo não duplica lançamento; linha sem regra casada fica pendente,
visível, nunca descartada em silêncio.

### CTB-41 — Conciliação bancária (1:1, 1:N, N:1) com trava por data

**O que é.** Confirmar que um lançamento contábil corresponde a um movimento
real do extrato bancário — um lançamento para um movimento (1:1), um
lançamento para vários movimentos somados (1:N), ou vários lançamentos para
um movimento (N:1). Uma vez conciliada, a conta **trava** contra alteração
retroativa: nenhum lançamento novo nem edição anterior à data conciliada.

**Referência de rotina.** Manual, páginas 238-247, 667-676.

**Fonte normativa.** Não se aplica — controle operacional.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-40.

**Dados.** Modelo novo: conciliação (conta bancária, data até a qual está
conciliada, vínculo entre item(ns) de lançamento e linha(s) de extrato).

**Regras.** Conta conciliada até uma data recusa inclusão, alteração e
exclusão de lançamento anterior a essa data — **mesmo com o período de
trabalho (CTB-08) ainda aberto** (é um terceiro controle, mais fino que
competência e período de trabalho, conforme a ideia estrutural 2 do mapa
funcional); desconciliação é ato explícito, auditado.

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa: teste que tenta
alterar lançamento anterior à data conciliada e é recusado; teste de
desconciliação restaurando a possibilidade de alteração.

### CTB-42 — Conciliação de clientes e fornecedores

**O que é.** Confirmar que os valores em aberto de contas a receber/pagar de
um cliente ou fornecedor específico batem com o que ele próprio reconhece —
"a Confecções Silva deve R$ 4.200,00 para nós, e ela confirma esse valor".

**Referência de rotina.** Manual, páginas 238-247, 667-676 (mesma seção da
conciliação bancária, no manual).

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-39.

**Dados.** Reaproveita o modelo de conciliação de CTB-41, com participante em
vez de conta bancária como eixo.

**Regras.** Mesmo princípio de trava por data de CTB-41, aplicado por
participante.

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa.

### CTB-43 — Importações (outra empresa, leiaute padrão, genérico)

**O que é.** Trazer dado de fora para dentro do sistema: de outra empresa do
mesmo escritório (mesma estrutura de plano de contas), de um leiaute padrão
de mercado, ou de um formato genérico configurável (mapeamento de colunas de
planilha, por exemplo).

**Referência de rotina.** Manual, páginas 782-829 — a segunda maior seção do
manual, depois dos livros.

**Fonte normativa.** Não se aplica — cada leiaute-alvo tem a sua fonte, se
oficial (ex.: SPED, tratado no mapa fiscal, fora deste módulo).

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-02.

**Dados.** Depende do leiaute-alvo; padrão comum: área intermediária de
validação em camadas antes de gravar (a capacidade "importação com
validação em camadas" já está confirmada como existente no domínio, mapa
funcional).

**Regras.** Reimportar o mesmo conteúdo não duplica (RC-14); a importação
**recusa** arquivo de empresa diferente da empresa ativa — prática barata
recomendada pela leitura do manual (**BL-403**), a implementar desde a
**primeira** versão de qualquer importador, não como correção depois de um
incidente.

**Telas e documentos.** Nova tela por tipo de importação — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa, por tipo de
importação.

**Não copiar / riscos.** "Cópia de lançamento de uma empresa para outra"
(diferente de **importar dados externos**) é capacidade que o manual tem e
que **recomendamos não copiar** — ver **CTB-65**.

### CTB-44 — Exportações

**O que é.** Tirar dado de dentro do sistema para um arquivo (planilha, texto,
leiaute de terceiro) — o caminho inverso da importação.

**Referência de rotina.** Manual, páginas 829-832.

**Fonte normativa.** Não se aplica — depende do leiaute-alvo.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-02.

**Dados.** Nenhum modelo novo — serialização de dado já existente.

**Regras.** Exportação respeita o mesmo isolamento por empresa de qualquer
outra saída (RC-18) — checar explicitamente, porque é o tipo de rotina em
que "exportar tudo" por engano é um vazamento silencioso entre clientes.

**Telas e documentos.** Nova tela por tipo de exportação — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; teste de
isolamento entre empresas obrigatório.

### CTB-45 — Alteração de lançamentos em massa

**O que é.** Corrigir muitos lançamentos de uma vez por um filtro amplo (ex.:
"todos os lançamentos de outubro na conta X, trocar para a conta Y") — sem
reeditar um por um.

**Referência de rotina.** Manual, páginas 730-732.

**Fonte normativa.** Não se aplica — é operação de produto, desenhada
deliberadamente **diferente** do sistema de referência (ver "Não copiar").

**Situação no DataLedger.** **Não existe** (**RC-51**, desenho em **DE-017**).

**Depende de.** CTB-07 (fechamento — o comportamento muda conforme o
período), CTB-32 (para não alcançar lançamento de origem automática sem
permissão própria — ver CTB-47).

**Dados.** Versionamento do lançamento: a versão anterior é gravada **inteira**
(cabeçalho e partidas), com autor, data, motivo e identificador da operação
em lote.

**Regras.** **Período aberto:** altera e guarda a versão anterior completa —
o Diário mostra só o lançamento corrigido (DE-017). **Período encerrado:**
não altera — gera lançamento de ajuste (estorno e relançamento) vinculado ao
original, com motivo. `save()` direto continua recusado — a alteração passa
por serviço explícito, nunca contorna a imutabilidade do modelo. Operação
atômica e idempotente; pré-visualização da contagem antes de aplicar.

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** Já descritos em **BL-65**: alteração em lote por
filtro, com pré-visualização; versão anterior gravada na mesma transação;
`save()` direto continua recusado; lançamento de período encerrado gera
ajuste; operação atômica; teste com falha induzida no meio do lote provando
que nada fica pela metade.

**Não copiar / riscos.** O sistema de referência **sobrescreve** o
lançamento efetivado, sem rastro do valor anterior descrito no material lido
— o DataLedger **nunca** faz isso (AGENTS.md §10, RC-15). A decisão de
implementar mesmo assim (DE-017) veio de o Fred ter pedido a capacidade
(RC-51); o desenho é diferente, preserva a trilha.

**Perguntas.** **PE-35**, já registrada: quais campos o escritório precisa
corrigir na prática (conta, histórico, centro de custo, data, valor), e com
que frequência?

### CTB-46 — Regeração de lançamentos derivados

**O que é.** Apagar e refazer, de uma vez, os lançamentos que **vieram de
outro processo** (a escrita fiscal, a folha) — nunca lançamento manual. O
caso real: o plano de contas muda no meio do ano, e é preciso refazer a
contabilização de todas as notas já escrituradas, que continuam intactas.

**Referência de rotina.** Manual, páginas 841-847 ("Exclusões e eliminação
de período" no manual — mas o caso de uso real do Fred, confirmado, é este).

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe** (**RC-59**, desenho em **DE-018**).

**Depende de.** CTB-32 (origem), CTB-07 (só período aberto), CTB-48
(integração fiscal→contábil, de onde os lançamentos derivados vêm).

**Dados.** Nenhum modelo novo — usa `origem` e `documento_origem` de CTB-32.

**Regras.** Só alcança lançamento cuja origem seja um processo do sistema,
nunca manual; só em período aberto (recusa, não aviso, em período fechado);
**não** alcança lançamento conciliado ou ajustado à mão, salvo autorização
explícita; apaga e refaz na mesma transação; idempotente por **chave
natural** (documento de origem + tipo), para que reprocessar não duplique
mesmo que a rotina falhe no meio; registra na trilha quantos saíram e
quantos entraram (**BL-66**).

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** Já descritos em **BL-66**.

**Não copiar / riscos.** O sistema de referência regera com duas proteções
**opcionais** (não regerar o alterado à mão, não regerar o conciliado) — no
DataLedger as duas são **padrão**, e desligar exige ato explícito; período
encerrado é **recusa**, não aviso; duplicidade é evitada por **chave
natural**, não confiada à rotina (as quatro diferenças deliberadas já estão
registradas em [mapa-funcional-contabil.md](../mapa-funcional-contabil.md),
seção "A regeração, e o que faremos diferente").

### CTB-47 — Permissão própria para alterar lançamento de origem automática

**O que é.** Uma permissão **distinta** da de lançar, exigida para editar ou
excluir um lançamento que veio de outro módulo (não digitado à mão) — quem
lança no dia a dia não deveria, por acidente, desfazer o que a escrita fiscal
gerou.

**Referência de rotina.** Levantado no material de referência (mapa funcional,
2026-09-13) e adotado por ser bom desenho, não por cópia cega.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe** (**BL-73**).

**Depende de.** CTB-32.

**Dados.** Nenhum modelo novo — nova permissão no sistema de papéis
(`apps/tenancy`).

**Regras.** Permissão própria, verificada **no servidor**; sem ela, 403 e
nada muda; lançamento de origem automática que tenha sido alterado à mão
fica **marcado como tal**, e a regeração (CTB-46) o preserva por padrão.

**Telas e documentos.** Sem tela nova — regra de autorização.

**Critérios de aceite.** Já descritos em **BL-73**: permissão própria testada
no caminho HTTP; marca de "alterado à mão" preservada pela regeração.

### CTB-48 — Integração fiscal → contábil

**O que é.** O mecanismo pelo qual uma nota fiscal escriturada no módulo
Fiscal **vira** lançamento contábil, automaticamente. A conta não vem do
produto nem do participante — vem de **duas** configurações que se somam: a
**classificação da operação** (contas do valor principal, frete, seguro,
despesas, parcelas) e o **cadastro de cada imposto** (contas de "a recolher"
e "a recuperar"). O histórico do lançamento gerado vem de um **modelo com
variáveis** (número da nota, participante, valor, data), não de texto fixo.

**Referência de rotina.** Levantado no manual público de escrita fiscal
(2026-09-13) — ver [mapa-funcional-contabil.md](../mapa-funcional-contabil.md),
seção "Integração fiscal → contábil: como a nota vira lançamento".

**Fonte normativa.** Não se aplica ao mecanismo em si — as alíquotas e
retenções de cada imposto são matéria do módulo Fiscal, com fonte própria a
confirmar lá, não aqui.

**Situação no DataLedger.** **Não existe** — depende da existência do módulo
Fiscal (DL-010 e etapas seguintes), fora deste plano.

**Depende de.** CTB-32, CTB-37 (histórico modelo), e a existência do módulo
Fiscal.

**Dados.** Modelo novo: classificação de operação (contas de débito/crédito
do valor principal, frete, seguro, despesas acessórias, pedágio, parcelas),
configuração contábil por imposto (contas de "a recolher"/"a recuperar",
histórico próprio, devoluções e ajustes) — **BL-74**.

**Regras.** Dois momentos, não um: ao gravar a nota, monta-se a **prévia** do
lançamento (visível e editável dentro da própria nota); a **efetivação** é
rotina em lote, por período — separar os dois permite conferir antes de
tocar a contabilidade, e reprocessar um período inteiro. Conferência lista
operações e impostos **sem conta configurada** antes de qualquer geração —
gerar lançamento pela metade é pior que não gerar (**BL-74**). Exclusão de
nota contabilizada oferece, como escolha **explícita**, excluir também o
lançamento gerado — nunca implicitamente, e só sob as mesmas regras de
período aberto e lançamento não conciliado.

**Telas e documentos.** Aba "Contabilidade" dentro da tela da nota fiscal
(módulo Fiscal) + rotina de efetivação em lote — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa da integração,
depois de o módulo Fiscal existir; herda os critérios de CTB-46 para a
regeração.

**Não copiar / riscos.** As quatro diferenças deliberadas já registradas em
CTB-46 valem aqui igualmente — são a mesma decisão, vista pelo lado da
geração em vez da regeração.

### CTB-49 — Backup, inclusive antes de operação destrutiva

**O que é.** Cópia de segurança dos dados, com atenção especial ao momento
que precede qualquer operação que apague ou sobrescreva em massa.

**Referência de rotina.** Manual, páginas 715-723.

**Fonte normativa.** Não se aplica — é obrigação de engenharia (AGENTS.md
§12), não regra contábil.

**Situação no DataLedger.** **Não existe procedimento verificado** (**PE-07**,
aberta desde o início do projeto).

**Depende de.** — (é infraestrutura, atravessa todos os módulos, não só
Contabilidade).

**Dados.** Não se aplica a este módulo especificamente.

**Regras.** Operação destrutiva (CTB-64, eliminação de escrituração) exige
backup verificado **antes** de executar, com restauração testada (mesma
exigência já registrada no mapa funcional).

**Telas e documentos.** Não se aplica — operação de infraestrutura.

**Critérios de aceite.** A definir com o Fred: quem executa, com que
frequência, e como se testa a restauração (PE-07).

**Perguntas.** **PE-07**, já registrada: qual é a política de backup e
restauração hoje, e quem a executa?

### CTB-50 — Plano de contas referencial e vínculo por vigência

**O que é.** Um plano de contas **oficial** (padronizado pela Receita Federal,
usado nas obrigações digitais), ao qual cada conta analítica da empresa
precisa estar **vinculada**, por vigência — é o que a ECD/ECF exigem para
aceitar a escrituração.

**Referência de rotina.** Manual, páginas 765-769.

**Fonte normativa.** **A confirmar** — o plano de contas referencial e sua
tabela de códigos vêm do **Manual de Orientação do Leiaute da ECD**,
publicado pela Receita Federal/Sped, com atualização periódica. **Não
conferido nesta sessão** — a vigência da tabela usada precisa ser verificada
antes de qualquer implementação.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01.

**Dados.** Modelo novo: plano de contas referencial (código oficial, descrição,
vigência) — dado importado da tabela oficial, não digitado; vínculo
conta↔referencial por vigência.

**Regras.** Pré-condição verificável: sem 100% das contas **movimentadas**
vinculadas ao plano referencial vigente, a escrituração digital do período
**não pode ser gerada** — bloqueia ou sinaliza, nunca sai em silêncio com
conta faltando (regra 9 do mapa funcional).

**Telas e documentos.** Nova tela de vínculo (conta → código referencial) —
classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; teste de recusa
de geração de ECD/ECF com conta sem vínculo.

**Perguntas.** O vínculo é sempre 1:1 (uma conta, um referencial por
vigência), ou pode ser **N** (mais de um referencial válido para a mesma
conta, com a escolha feita na **partida**, não no cadastro)? Achado **BL-392**
da leitura integral: o manual mostra que, quando há mais de um referencial
possível, o campo vem em branco no lançamento para o usuário escolher —
ver **CTB-56**, que trata esta decisão de modelagem separadamente por ser de
alto custo se errada.

### CTB-51 — ECD (Escrituração Contábil Digital)

**O que é.** O arquivo que a empresa transmite ao Sped com toda a
escrituração contábil do exercício (Diário, Razão, plano de contas,
demonstrações) num leiaute estruturado que a Receita Federal processa.

**Referência de rotina.** Manual, páginas 359-374.

**Fonte normativa.** **A confirmar** — **Manual de Orientação do Leiaute da
ECD**, publicado pela Receita Federal/Sped, com leiaute e regras de
validação (o "validador" oficial). **Não conferido nesta sessão** — leiaute e
vigência precisam ser conferidos em texto oficial antes de qualquer
implementação (mesma ressalva já registrada em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md): "existência
confirmada; leiaute e vigência a conferir").

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01 a CTB-11 (a base inteira de escrituração), CTB-26
(a ECD **é**, essencialmente, o Diário e o Razão num arquivo estruturado),
CTB-28, CTB-29 (sócios e contador são signatários), CTB-50 (plano referencial,
pré-condição de geração).

**Dados.** Modelo novo: entrega ECD (protocolo, período, cadeia de
retificação) — achado **BL-397** da leitura integral: a entrega digital é
uma **entidade com identidade própria**, distinta do lançamento — o padrão de
cadeia rastreável que `estorno_de` já resolve para o lançamento **não** se
aplica direto aqui; retificação de entrega substitui o **documento**, não
corrige o **fato contábil**.

**Regras.** Geração recusada com conta sem vínculo referencial (CTB-50);
protocolo da transmissão é capturado e preservado — se não for capturado no
momento da entrega, recuperá-lo depois depende de recibo fora do sistema
(achado **BL-397**, classificado como "perda provável", faixa 2).

**Telas e documentos.** Nova tela de geração — classe **R** (arquivo
regulatório, leiaute oficial, zero margem de personalização).

**Critérios de aceite.** A definir junto do plano de etapa, com validação
contra o validador oficial do Sped antes de qualquer entrega real.

**Perguntas.** O escritório do Fred transmite ECD hoje, para quais clientes,
e com qual periodicidade (a ECD é anual)?

### CTB-52 — ECF (Escrituração Contábil Fiscal) e ajustes

**O que é.** O arquivo que integra a apuração do IRPJ/CSLL (via Lalur) com a
escrituração contábil — ajusta o resultado contábil pelas adições e exclusões
fiscais até chegar ao lucro real (quando aplicável).

**Referência de rotina.** Manual, páginas 375-541 (a maior seção do manual
inteiro) e 737-765 (ajustes).

**Fonte normativa.** **A confirmar** — **Manual de Orientação do Leiaute da
ECF**, publicado pela Receita Federal/Sped. **Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-51 (a ECF importa dados da ECD), e do módulo **Lalur**
(fora deste plano — ver CTB-74).

**Dados.** Depende inteiramente do desenho do módulo Lalur, ainda não
planejado.

**Regras.** A definir junto do plano de etapa do Lalur/ECF, quando
priorizado.

**Telas e documentos.** Classe **R**.

**Critérios de aceite.** A definir.

**Não copiar / riscos.** **BL-398**, já registrado: o Lalur Parte B é
sub-livro com saldo que atravessa exercícios e **não é partida dobrada** —
generalizar `Conta` para cobri-lo seria erro (ver CTB-74).

### CTB-53 — Apuração de CMV e CPV

**O que é.** O cálculo do Custo da Mercadoria Vendida (CMV) ou do Custo do
Produto Vendido (CPV): estoque inicial + compras − estoque final, gerando um
lançamento de ajuste.

**Referência de rotina.** Manual, páginas 660-663 (relatório) e 832-839
(cálculo/lançamento).

**Fonte normativa.** Fórmula agregada é prática contábil geral (não há
dispositivo único a citar); o **critério de custeio** (PEPS, custo médio,
outros) tem implicação fiscal e precisa ser confirmado com o Fred antes de
qualquer implementação — já registrado como pendência no mapa funcional
("fórmula agregada confirmada; critério de custeio a conferir").

**Situação no DataLedger.** **Não existe** — **bloqueado pela ausência de
módulo de estoque**, que este plano não cobre (é módulo próprio, fora do
escopo desta demanda).

**Depende de.** Módulo de estoque (inexistente), CTB-01, CTB-02.

**Dados.** Depende do desenho do módulo de estoque.

**Regras.** `estoque inicial + compras − estoque final` satisfeito, e o
lançamento gerado bate com o valor apurado (regra 12 do mapa funcional, já
registrada como candidata a teste).

**Telas e documentos.** Classe **C** + lançamento.

**Critérios de aceite.** A definir quando o módulo de estoque existir.

**Perguntas.** Qual critério de custeio o escritório usa na prática (PEPS,
custo médio)? Não implementar sem essa resposta confirmada com fonte, se
houver implicação fiscal (Lucro Real, por exemplo).

### CTB-54 — Autorização com escopo de empresa

**O que é.** Hoje, quem tem vínculo com um escritório enxerga **todas** as
empresas dele — não há como dizer "este usuário só vê estes cinco clientes".
É a lacuna mais grave encontrada na leitura integral do manual, e — o que
importa mais — ela é lacuna contra o **nosso próprio** `docs/escopo.md`, não
contra o concorrente.

**Referência de rotina.** Não veio do manual diretamente — veio de comparar
o código com `docs/escopo.md:20`, que já exige "permissões por módulo,
operação, empresa e categoria de informação". O manual serviu de lente para
enxergar a lacuna.

**Fonte normativa.** Não se aplica — é arquitetura de autorização
(AGENTS.md §11, RC-17).

**Situação no DataLedger.** **Não existe** (**BL-389**, "a mais grave da
leitura até aqui"). `VinculoUsuarioEscritorio` é `(usuario, escritorio,
papel)` e mais nada — quem tem vínculo enxerga todas as empresas do
escritório.

**Depende de.** — (decisão de arquitetura que atravessa **todo** o módulo,
não só Contabilidade — mas é aqui, no domínio de escrituração, que o sigilo
entre clientes do mesmo escritório mais importa).

**Dados.** Tabela de associação nova (usuário, empresa) — ou (usuário,
escritório, empresas alcançáveis), a definir pelo `arquiteto-senior`.

**Regras.** Autorização verificada **no servidor** em toda view e serviço que
hoje só olha `escritorio` — não se resolve escondendo menu.

**Telas e documentos.** Nova tela de gestão de acesso por empresa — classe
**C**.

**Critérios de aceite.** A definir junto do plano de etapa: migração de
**todos** os vínculos existentes; teste que confirma que um usuário sem
acesso a uma empresa recebe 403/404 em toda rota de Contabilidade daquela
empresa, não só nas telas que "aparecem".

### CTB-55 — Correspondência de conta entre exercícios (reclassificação do plano)

**O que é.** Quando o escritório reorganiza o plano de contas de um cliente de
um ano para o outro (a conta X de 2025 virou a conta Y de 2026), registrar
essa correspondência — sem isso, ela se perde no momento da reclassificação e
não há como reconstruí-la depois.

**Referência de rotina.** Achado da leitura integral, **BL-395**: o sistema
de referência tem tela própria para declarar, na entrega da escrituração
digital, que uma conta mudou de código ou classificação em relação ao
exercício anterior, com a identidade antiga e o saldo que ela tinha.

**Fonte normativa.** Não se aplica diretamente — é exigido pela própria
lógica da ECD (CTB-51), que precisa da correspondência entre planos de
exercícios diferentes.

**Situação no DataLedger.** **Não existe** — e é o item de **maior gravidade
contábil** de toda a leitura integral, porque o dado se perde **no ato** da
reclassificação, não depois: não há migração que reconstrua depois quem virou
quem.

**Depende de.** CTB-01, CTB-50 (a correspondência entre exercícios se cruza
com o vínculo referencial).

**Dados.** Modelo novo: correspondência de conta (conta antiga, conta nova,
exercício de transição, saldo transferido).

**Regras.** Toda reclassificação de conta **com lançamento** (diferente do
código reduzido reaproveitável de conta **sem** lançamento, RC-100) registra
a correspondência no momento em que acontece — nunca depois, porque depois
não há de onde recuperar.

**Telas e documentos.** Nova tela, provavelmente amarrada ao fluxo de virada
de exercício (CTB-24) — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Perguntas.** Quando um cliente reorganiza o plano de um ano para o outro, o
escritório registra essa correspondência em algum lugar hoje, ou ela se
perde?

### CTB-56 — Vínculo conta↔plano referencial N (escolha na partida)

**O que é.** A decisão de modelagem, isolada de CTB-50 por ser a de **maior
custo se errada** de toda a leitura integral: se uma conta pode ter **mais de
um** referencial válido, a escolha entre eles precisa ficar na **partida**
(no momento do lançamento), não presumida 1:1 no cadastro.

**Referência de rotina.** Achado **BL-392** — o manual mostra o campo em
branco no lançamento quando há mais de uma opção.

**Fonte normativa.** Não se aplica — decisão de modelagem.

**Situação no DataLedger.** **Não existe** — e o mapa funcional **presumia
1:1 por vigência**, premissa que este achado corrige antes de qualquer código
ser escrito.

**Depende de.** CTB-50.

**Dados.** Se a resposta for "sim, pode ser N": campo de escolha de
referencial na **partida** (`ItemLancamento`), não na conta.

**Regras.** A definir conforme a resposta.

**Telas e documentos.** Campo condicional na tela de lançamento, só quando
houver ambiguidade — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa.

**Não copiar / riscos.** O custo de errar aqui é "o pior da leitura inteira"
(texto do achado original): modelar 1:1, descobrir que é N, e ter de
reclassificar **retroativamente** qual referencial cada lançamento antigo
deveria ter usado é trabalho que só o contador consegue fazer, lançamento a
lançamento — não é migração automática.

**Perguntas.** A exigência de vincular 100% das contas (CTB-50) tolera conta
com mais de um referencial válido ao mesmo tempo, ou isso se resolve sempre
no cadastro antes de lançar?

### CTB-57 — Unicidade condicional de classificação analítica

**O que é.** A decisão de se o código/classificação de uma conta analítica
precisa ser **sempre** único dentro da empresa (como é hoje,
`UniqueConstraint(empresa, codigo)`), ou se deve admitir exceção para casos
específicos (ex.: filial, SCP) — o sistema de referência oferece isso como
**opção**, com lista de exceção de grupos.

**Referência de rotina.** Achado **BL-390** da leitura integral.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Constraint absoluta hoje** (`codigo_unico_por_empresa`,
CTB-01) — o achado é registrar a possível necessidade de exceção **antes** de
a classificação ser modelada como campo próprio (RC-64 já prevê classificação
distinta do código de cadastro).

**Depende de.** CTB-01.

**Dados.** Se a resposta exigir: campo de "grupo com exceção de unicidade"
associado à constraint condicional.

**Regras.** A definir conforme a resposta.

**Telas e documentos.** Não se aplica isoladamente — é ajuste de constraint.

**Critérios de aceite.** A definir junto do plano de etapa, se necessário.

**Perguntas.** Alguma empresa da carteira precisa de duas analíticas com a
mesma classificação — por filial ou SCP, por exemplo —, ou é opção do
sistema de referência que ninguém usa na prática?

### CTB-58 — Sócio, contador e responsável como a mesma pessoa física entre papéis

**O que é.** A mesma pessoa física pode ser sócia de um cliente **e**
contadora responsável de outro — ou até as duas coisas do mesmo cliente. A
decisão de modelagem é: cada papel nasce como tabela própria com CPF
duplicado, ou existe um cadastro central de pessoa física com papéis
vinculados?

**Referência de rotina.** Achado **BL-393** da leitura integral — o sistema
de referência avisa quando o CPF informado já existe em outro papel.

**Fonte normativa.** Não se aplica — decisão de modelagem.

**Situação no DataLedger.** **Não existe nenhum dos dois cadastros ainda**
(sócio — CTB-28 — e contador — CTB-29 — são itens deste mesmo plano, ainda
não implementados) — é a hora **mais barata** de decidir, porque decidir
depois do primeiro cadastro custa deduplicação manual, registro a registro.

**Depende de.** — (precede CTB-28 e CTB-29).

**Dados.** Se a resposta for "cadastro central": modelo `PessoaFisica` (CPF,
nome) com papéis vinculados (sócio de empresa X, contador de empresa Y).

**Regras.** A definir conforme a resposta.

**Telas e documentos.** Não se aplica isoladamente.

**Critérios de aceite.** A definir junto do plano de etapa de CTB-28/CTB-29.

**Perguntas.** Quando a mesma pessoa é sócia de um cliente e contadora
responsável de outro, é a mesma pessoa no cadastro com dois papéis, ou dois
registros independentes na prática do escritório?

### CTB-59 — Consolidação entre empresas / plano de contas compartilhado

**O que é.** Duas capacidades próximas que o sistema de referência tem e que
**colidem** com um invariante de segurança do DataLedger: (a) somar
relatórios de empresas diferentes que compartilham o mesmo plano de contas,
sem exigir vínculo societário; (b) um plano de contas cadastrado uma vez e
usado por várias empresas.

**Referência de rotina.** Achados **BL-399** e **PE-55** da leitura integral
— duas leituras independentes chegaram ao mesmo lugar.

**Fonte normativa.** Não se aplica — decisão de arquitetura.

**Situação no DataLedger.** **Não existe.** `Empresa` é a fronteira de
isolamento **repetida em toda consulta, relatório, exportação e tarefa** —
regra permanente do projeto (RC-18). Introduzir consolidação depois obriga
decidir, consulta por consulta, onde a fronteira pode ser cruzada — e cada
esquecimento vira vazamento entre clientes.

**Depende de.** — (decisão de arquitetura que precede qualquer relatório
gerencial consolidado).

**Dados.** A definir conforme a resposta — provavelmente um modelo de "grupo
econômico" que **declara** explicitamente quais empresas podem ser somadas,
nunca inferido.

**Regras.** Enquanto não houver decisão, **nenhuma** consulta soma dado de
duas empresas — o padrão atual (isolamento total) é o mais seguro e continua
valendo por omissão.

**Telas e documentos.** Não se aplica sem a decisão.

**Critérios de aceite.** A definir junto do plano de etapa, se e quando
priorizado.

**Perguntas.** Há clientes em grupo econômico, com CNPJs distintos, que
precisam de balancete ou DRE consolidado? O escritório usa plano de contas
padronizado entre clientes (o que tornaria "plano compartilhado" valioso), ou
cada cliente tem o seu?

### CTB-60 — Alteração da estrutura do plano de contas (reorganização em massa)

**O que é.** Mover várias contas de grupo de uma vez, reorganizando a
hierarquia do plano — diferente de editar uma conta por vez.

**Referência de rotina.** Manual, páginas 734-737.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Parcial.** A edição de **uma** conta por vez
(mover de grupo) já tem tela própria pendente (**BL-541**, aberta — hoje só
pelo admin do Django). A reorganização **em massa** de várias contas de uma
vez **não existe**.

**Depende de.** CTB-01, BL-541 (edição unitária, pré-requisito natural).

**Dados.** Nenhum modelo novo — operação em lote sobre `Conta.conta_pai`.

**Regras.** As mesmas guardas de `Conta.clean()` que já recusam mover conta
com movimento para outra empresa, ou trocar natureza de conta movimentada,
valem em massa — a operação em lote não pode ser um atalho que contorna
`clean()`.

**Telas e documentos.** Extensão da tela de plano de contas — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; teste que
confirma que a operação em massa recusa exatamente os mesmos casos que a
edição unitária recusaria, um a um.

### CTB-61 — Registro de atividades (trilha de auditoria)

**O que é.** O log de quem fez o quê, quando, no sistema.

**Referência de rotina.** Manual, páginas 848-850.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Existe, e supera o pedido do manual.** A trilha
de auditoria (`apps/auditoria/`, DL-024/DL-030) já cobre criação, alteração e
tentativa de exclusão, inclusive pelo Django admin (signal genérico,
confirmado por execução: `test_dl024_trilha_admin.py` → `7 passed`) — sem
exigir que cada view chame `registrar()` manualmente, o que o manual (na
leitura do item de registro de atividades) não parece garantir com a mesma
uniformidade.

**Depende de.** — (é transversal, não específico de Contabilidade).

**Dados.** `RegistroAuditoria` (`apps/auditoria/models.py`), já existente.

**Regras.** Já cumpridas: ator, contexto, operação e resultado, com proteção
de dado sensível (RC-06).

**Telas e documentos.** Fora do escopo deste módulo (é de plataforma).

**Critérios de aceite.** Já cobertos pelos testes existentes de
`apps/auditoria/`.

### CTB-62 — Cópia de configuração entre empresas do escritório

**O que é.** Copiar parâmetros e cadastros (não escrituração) de uma empresa
já configurada para uma empresa nova — plano de contas, parâmetros contábeis,
históricos padronizados, lançamentos padrão, centros de custo.

**Referência de rotina.** Registrado como capacidade confirmada no mapa
funcional, seção "Operação e conferência".

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.**

**Depende de.** CTB-01, CTB-11, CTB-33, CTB-37, CTB-38 (tudo que é
configuração, não escrituração, pode ser copiado).

**Dados.** Nenhum modelo novo — serviço de cópia que lê a configuração de uma
empresa e grava em outra, com novos IDs (nunca compartilhando o registro).

**Regras.** A cópia gera registros **independentes** — editar o cadastro
copiado numa empresa nunca afeta a outra (mesma regra de CTB-31, perfis de
empresa, que é capacidade próxima).

**Telas e documentos.** Nova tela — classe **C**.

**Critérios de aceite.** A definir junto do plano de etapa; sobrepõe-se com
CTB-31 — avaliar juntas antes de construir as duas separadamente.

### CTB-63 — Carnê-leão e livro-caixa (pessoa física) — módulo adjacente

**O que é.** A escrituração de clientes **pessoa física** que prestam
serviço: livro-caixa (regime de caixa, não partida dobrada) e apuração
mensal do imposto de renda (carnê-leão). É um regime de escrituração
**diferente** do resto deste plano — `Empresa` em modo livro-caixa **recusa**
a contabilidade por partidas dobradas (RC-114).

**Referência de rotina.** Não vem do manual de 856 páginas de Contabilidade
(que é sobre partida dobrada) — vem do próprio acervo do escritório do Fred
e de fontes oficiais da Receita Federal, já levantadas em
[requisitos.md](../requisitos.md) (RC-112 a RC-134).

**Fonte normativa.** **Já conferida na fonte primária** para a apuração
mensal de 2026: Lei 15.191/2025, Lei 15.270/2025, Lei 9.250/1995, Lei
7.713/1988, RIR/2018 — registrada como **RC-131**.

**Situação no DataLedger.** **Existe (DL-046)**, em `apps/livro_caixa/`, app
**separado** de `apps/contabilidade/` — fronteira deliberada, porque o
regime de caixa e a partida dobrada são domínios com pressupostos
incompatíveis (o mesmo cuidado que **BL-398** registra para o Lalur Parte B,
CTB-74). `criar_lancamento_caixa`, `estornar_lancamento_caixa`,
`apurar_livro_caixa` (`apps/livro_caixa/services.py`) e `carne_leao.py` para
a apuração mensal.

**O que falta para paridade:** fatia 3 do plano DL-046 — o **arquivo** no
leiaute oficial de importação/exportação do Carnê-Leão Web (RC-127 confirma
que o escritório usa os dois caminhos: digitação e importação de arquivo);
código de ocupação e cadastro nominal de dependentes, hoje simplificados por
decisão de produto (HI-34, HI-35).

**Depende de.** — (é módulo adjacente; não depende dos itens deste plano).

**Dados.** Fora de `apps/contabilidade/` — ver `apps/livro_caixa/models.py`.

**Regras.** Já implementadas e testadas na DL-046, fatias 1 e 2.

**Telas e documentos.** `apps/livro_caixa/views_web.py` — classe **C**/**R**
(o arquivo do Carnê-Leão Web, quando existir, é leiaute oficial).

**Critérios de aceite.** Já cobertos pelos testes da DL-046.

**Não copiar / riscos.** Não generalizar `Conta`/`LancamentoContabil` para
cobrir o regime de caixa — é exatamente o erro que **BL-398** avisa para não
cometer no Lalur, e o mesmo raciocínio protege este módulo: "conta com saldo"
tem formas incompatíveis entre partida dobrada e regime de caixa.

## Fora de escopo ou dependente de confirmação

Estes onze itens não entram em código sem uma decisão do Fred antes, ou já
têm decisão de "não agora" registrada, com o motivo escrito.

### CTB-64 — Eliminação de escrituração (apagar sem origem para regerar)

**O que é.** Diferente da regeração (CTB-46, que apaga e **refaz** a partir
de uma origem que continua existindo): isto é apagar lançamento **sem**
possibilidade de reconstrução — redução de volume histórico.

**Referência de rotina.** Manual, páginas 841-847.

**Fonte normativa.** Não se aplica diretamente — mas exclusão de dado
contábil pode colidir com prazo de guarda obrigatório (guarda de livros e
documentos fiscais/contábeis, tipicamente 5 anos ou mais conforme a
obrigação — **a confirmar** dispositivo exato antes de implementar qualquer
exclusão definitiva).

**Situação no DataLedger.** **Não existe, e a recomendação registrada é não
implementar por ora** (mapa funcional, seção "Duas capacidades que entram em
choque com as nossas regras"). O próprio material de referência recomenda
backup antes de executar — indício de que não há como desfazer.

**Depende de.** CTB-49 (backup verificado e restauração testada) — a
DE-018 já condiciona esta operação a **BL-33** (restauração testada), que
não existe.

**Dados.** Se um dia for implementada: inventário permanente do que saiu, com
contagem e totais, e papel autorizado.

**Regras (se um dia implementada).** Só período encerrado; exportação
verificada antes de apagar, com aborto em caso de falha; papel autorizado com
contagem e totais registrados; só depois de haver restauração provada
(BL-33).

**Não copiar / riscos.** Onde o sistema de referência apagaria, o DataLedger
**registra** — é o princípo geral que rege toda esta seção. A mesma lógica
vale para "exclusões em massa" citadas no manual.

**Perguntas.** **PE-34** já tem parte da resposta (o caso real é regeração,
CTB-46, não isto) — o que falta é: existe, na prática do escritório, uma
necessidade real de **apagar sem regerar** (empresa que saiu da carteira,
volume, LGPD)? Sem essa resposta, este item continua sem implementação.

### CTB-65 — Cópia de lançamento entre empresas — recomendação de não copiar

**O que é.** O sistema de referência copia lançamento de uma empresa para
outra (filtrando por data, número, conta ou valor) — um utilitário, não uma
funcionalidade contábil neutra: é fato contábil de uma pessoa jurídica
aparecendo no livro de outra.

**Referência de rotina.** Achado **BL-402** da leitura integral.

**Fonte normativa.** Não se aplica — a recomendação é de arquitetura, não de
norma.

**Situação no DataLedger.** **Não existe, e a recomendação é NÃO
implementar como o sistema de referência faz.** `Conta.clean()` já trata
reatribuir empresa como violação (mesma guarda de BL-83).

**Depende de.** — (é decisão de não fazer, não item a planejar).

**Dados.** Não se aplica.

**Regras.** Se a necessidade existir de fato (rateio em grupo econômico,
holding), o desenho correto **não é** gravar lançamento na empresa alheia —
é lançamento de **mútuo ou transferência** entre as duas contabilidades,
cada uma fechando sozinha, preservando a personalidade jurídica de cada
entidade.

**Não copiar / riscos.** Copiar bruto quebra a personalidade jurídica de
cada empresa, e é o tipo de atalho impossível de desfazer depois que os
livros foram entregues.

**Perguntas.** Existe hoje, no escritório, a prática de copiar lançamento de
um cliente para outro? Se sim, qual é o caso de uso real — provavelmente
resolvido melhor por CTB-59 (consolidação) ou por lançamento de mútuo, não
por cópia.

### CTB-66 — SCP (Sociedade em Conta de Participação)

**O que é.** Um arranjo societário em que a escrituração da SCP convive com a
do sócio ostensivo, **dentro do mesmo CNPJ** — é uma partição abaixo do nível
de empresa que o DataLedger hoje não representa.

**Referência de rotina.** Manual, páginas 153-160.

**Fonte normativa.** **A confirmar** — regulada pelo Código Civil (arts.
991-996) e com tratamento fiscal próprio (**IN RFB nº 1.700/2017**, entre
outras). **Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe.** `Conta`, `LancamentoContabil` e
`Competencia` têm `empresa` como **única** chave de escopo — não há nível
abaixo dela.

**Depende de.** CTB-54 (mesmo tipo de decisão de escopo de autorização, um
nível abaixo).

**Dados.** Se implementada: nível de partição dentro de `Empresa`, com as
mesmas garantias de isolamento que `Empresa` já tem entre si.

**Regras.** Lançamento efetivado é imutável (decisão do projeto) — se a
partição vier depois de centenas de lançamentos gravados, não dá para
reclassificar retroativamente, só por estorno em massa, refazendo o trabalho
do contador (achado **BL-400**).

**Não copiar / riscos.** Vira urgente **só se** houver cliente com SCP hoje —
não implementar preventivamente.

**Perguntas.** Algum cliente atendido pelo escritório tem SCP registrada?

### CTB-67 — Conglomerado econômico

**O que é.** Um agrupamento de empresas sob controle comum, para fins de
relatório e, eventualmente, consolidação.

**Referência de rotina.** Manual, páginas 178-179.

**Fonte normativa.** **A confirmar** — regras de consolidação contábil vêm da
**Lei 6.404/76, arts. 249-250** e da **NBC TG 36** (equivalente ao CPC 36).
**Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe** — sobrepõe-se a CTB-59
(consolidação entre empresas), que já registra a decisão de arquitetura
pendente.

**Depende de.** CTB-59.

**Dados.** A definir junto de CTB-59.

**Regras.** A definir junto de CTB-59.

**Perguntas.** As mesmas de CTB-59 — este item não tem pergunta própria
adicional.

### CTB-68 — Matriz e filial com escrituração centralizada

**O que é.** Uma empresa com matriz e filiais que escritura tudo num único
livro contábil, em vez de um livro por CNPJ.

**Referência de rotina.** Registrado como capacidade confirmada no mapa
funcional, seção "Cadastros", marcada "Decisão do Fred".

**Fonte normativa.** Não se aplica diretamente — é opção de organização
contábil, dentro do que a lei permite.

**Situação no DataLedger.** **Não existe** — `Empresa` (com CNPJ próprio) é
hoje a unidade de escrituração; não há conceito de matriz agregando filiais
na mesma escrituração.

**Depende de.** CTB-54, CTB-59 (mesma família de decisão de escopo/isolamento
entre entidades).

**Dados.** A definir conforme a resposta.

**Regras.** A definir.

**Perguntas.** **PE-30**, já registrada: existe empresa na carteira com
matriz e filiais em escrituração centralizada? Se sim, o lançamento precisa
identificar a filial desde o início — mudança de modelo que é cara de
acrescentar depois.

### CTB-69 — Múltiplas classificações paralelas do plano de contas

**O que é.** O sistema de referência mantém até **três** estruturas paralelas
para o mesmo plano de contas (contábil, de relatório, gerencial) — a mesma
conta sob três esqueletos hierárquicos diferentes, não três layouts do
mesmo relatório.

**Referência de rotina.** Achado **BL-391** da leitura integral.

**Fonte normativa.** Não se aplica.

**Situação no DataLedger.** **Não existe.** `Conta.codigo` é um campo só;
guardar uma conta sob várias classificações por finalidade exige **tabela**
relacionando conta a cada esquema, não coluna nova — é mudança de estrutura,
não de campo.

**Depende de.** CTB-01.

**Dados.** Se implementada: tabela de classificação paralela (conta, esquema,
código dentro do esquema).

**Regras.** A definir conforme a resposta.

**Não copiar / riscos.** Construído sem demanda real, vira peso morto — este
item **fica registrado e não entra no desenho** enquanto não houver
confirmação de necessidade.

**Perguntas.** O escritório atende empresa com contabilidade gerencial
paralela (um plano para a contabilidade oficial, outro para a visão
gerencial interna do cliente)?

### CTB-70 — Índices de correção monetária e moeda estrangeira

**O que é.** Aplicar um índice de correção (ex.: variação de moeda,
inflação) a saldos contábeis, ou consolidar valores em moeda diferente da de
apresentação.

**Referência de rotina.** Manual, páginas 145-148.

**Fonte normativa.** **A confirmar, com um alerta relevante:** a correção
monetária de balanço foi **extinta para fins societários e fiscais** pela
**Lei 9.249/1995, art. 4º**, a partir de 1996 — se confirmado, a maior parte
desta capacidade está **obsoleta** para a generalidade das empresas
brasileiras hoje. Moeda estrangeira (consolidação de investida no exterior)
continua sendo matéria válida, mas de público pequeno na carteira típica de
um escritório brasileiro de porte médio — já registrado como avaliação de
baixa prioridade em
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md).

**Situação no DataLedger.** **Não existe, e a recomendação é não
implementar sem confirmação de necessidade real** — o risco de implementar
uma capacidade obsoleta é maior que o de não a ter.

**Depende de.** — (nenhuma, precisamente porque não está priorizado).

**Dados.** Não se aplica sem confirmação.

**Regras.** Não se aplica sem confirmação.

**Perguntas.** Algum cliente da carteira tem investimento no exterior que
exija consolidação em moeda estrangeira? Sem isso, este item permanece fora
de escopo.

### CTB-71 — Balancetes e arquivos setoriais (regulatórios)

**O que é.** Balancetes e arquivos exigidos por reguladores setoriais
específicos: ANEEL (energia), ANTT (transporte), Bacen (instituições
financeiras), ANS/DIOPS (saúde suplementar), Sinco, TCE/SC (tribunal de
contas estadual), prestação de contas de partidos políticos.

**Referência de rotina.** Manual, páginas 542-567.

**Fonte normativa.** Cada regulador tem a sua norma própria — **nenhuma
conferida nesta sessão**, e não seria produtivo conferir todas sem saber se
algum cliente da carteira está sujeito a alguma delas.

**Situação no DataLedger.** **Não existe, e é nicho por natureza** — só
entra em escopo se houver cliente regulado por um desses órgãos.

**Depende de.** CTB-09, CTB-10 (a maioria destes arquivos deriva do
Balanço/DRE, com ajustes setoriais).

**Dados.** A definir por regulador, se e quando houver cliente.

**Regras.** A definir por regulador.

**Perguntas.** **PE-32**, já registrada, cobre parcialmente isto: quais
obrigações contábeis o escritório de fato entrega hoje? Nenhuma das listadas
aqui deve entrar em código sem confirmação de cliente real sujeito a ela — o
material é de 2018 e cita obrigações provavelmente extintas ou substituídas.

### CTB-72 — Balanço fiscal e FCONT

**O que é.** O FCONT (Controle Fiscal Contábil de Transição) era o
mecanismo que neutralizava, para fins fiscais, os efeitos da adoção do IFRS
no Brasil durante o RTT (Regime Tributário de Transição).

**Referência de rotina.** Manual, páginas 280-285 (balanço fiscal), 663-666
(conferência do FCONT).

**Fonte normativa.** **A confirmar, com indício forte de obsolescência:** o
RTT foi extinto pela **Lei 12.973/2014**, o que tipicamente extingue também
a razão de ser do FCONT. **Não conferido em texto oficial nesta sessão** —
mas a suspeita já está registrada no próprio
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md).

**Situação no DataLedger.** **Não existe, e a recomendação é não
implementar** — obrigação provavelmente extinta.

**Depende de.** — (nenhuma, por não estar priorizado).

**Dados.** Não se aplica.

**Regras.** Não se aplica.

**Perguntas.** Confirmação de que o FCONT está de fato extinto (Lei
12.973/2014) — se algum cliente antigo da carteira ainda tiver obrigação
residual, isso muda a resposta, mas é improvável em 2026.

### CTB-73 — Balanço social, DOAR e DSP (terceiro setor)

**O que é.** Três capacidades para perfis específicos: Balanço Social
(responsabilidade social corporativa, voluntário), DOAR (Demonstração das
Origens e Aplicações de Recursos, **extinta** como obrigação desde a Lei
11.638/2007, que a substituiu pela DFC), DSP (Demonstração do Superávit ou
Déficit, para entidades sem fins lucrativos/terceiro setor).

**Referência de rotina.** Manual, páginas 285-287 (balanço social), 611-616 e
631-637 (DOAR, DSP).

**Fonte normativa.** **A confirmar, com uma certeza parcial:** a **DOAR foi
extinta** pela **Lei 11.638/2007**, que a substituiu pela DFC (CTB-15) — este
ponto tem indício forte o bastante para **não implementar a DOAR**. A DSP,
para entidades do terceiro setor, segue a **ITG 2002** (equivalente à NBC
TG); **não conferida nesta sessão**.

**Situação no DataLedger.** **Não existe.** Balanço social e DOAR são
nicho/histórico (DOAR, especificamente, obsoleta); DSP depende de haver
cliente do terceiro setor na carteira.

**Depende de.** CTB-09, CTB-10 (DSP deriva de estrutura semelhante ao
Balanço/DRE, adaptada a entidade sem fins lucrativos).

**Dados.** A definir se houver cliente do terceiro setor.

**Regras.** A definir.

**Perguntas.** O escritório atende alguma entidade sem fins lucrativos
(associação, fundação, ONG) que exija DSP?

### CTB-74 — Lalur Parte B (referência cruzada — módulo próprio)

**O que é.** O Livro de Apuração do Lucro Real, Parte B: um razão de
controle fiscal (não partida dobrada) que acumula adições e exclusões
temporárias, com saldo que **atravessa exercícios** — por exemplo, uma
diferença de depreciação fiscal × contábil que só se resolve anos depois.

**Referência de rotina.** Não é item do manual de 856 páginas de
Contabilidade — é achado preventivo da leitura integral, **BL-398**,
registrado aqui só como referência cruzada, porque toca a estrutura de
`Conta` que este módulo possui.

**Fonte normativa.** **A confirmar** — Lalur regido pelo **Decreto-Lei
1.598/1977** e pela **IN RFB nº 1.700/2017**; hoje entregue dentro da ECF
(CTB-52). **Não conferido nesta sessão.**

**Situação no DataLedger.** **Não existe, e o planejamento correto é um
módulo próprio** — [mapa-funcional-contabil.md](../mapa-funcional-contabil.md)
já registra a ordem: "depois de Patrimônio e com a DRE" ([DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md)).
Este plano **não** cobre o Lalur; o item existe aqui só para deixar escrito
o motivo de **não** generalizar `Conta` para cobri-lo.

**Depende de.** CTB-10 (DRE, ponto de partida do ajuste), CTB-52 (ECF, onde o
Lalur é entregue), e o módulo de Patrimônio (fora deste plano, para a
depreciação fiscal × contábil que tipicamente origina a Parte B).

**Dados.** Fora deste plano — quando o módulo Lalur for planejado, o dado
correto é um "razão memorando" próprio, **não** uma extensão de `Conta`.

**Regras.** Não se aplica a este plano.

**Não copiar / riscos.** **"Conta com saldo" no domínio contábil-fiscal tem
pelo menos duas formas incompatíveis:** a societária, por partida dobrada
(`Conta` já cobre isso), e a de controle fiscal, que é razão memorando.
`Conta` carrega `natureza`, `aceita_lancamento` e o par débito/crédito —
pressupostos que **não se aplicam** à segunda. Este registro existe para
impedir que, no dia do Lalur, alguém estenda `Conta` por parecer parecido.

**Perguntas.** O Lalur está no horizonte próximo do escritório, ou é
distante? Determina se CTB-74 deveria virar plano de módulo próprio já, ou
continuar como nota preventiva.

## Glossário

| Termo | Significado |
| --- | --- |
| **Analítica** | Conta sem descendentes na hierarquia (folha da árvore); é a que recebe lançamento direto na prática, embora a permissão de lançar seja um campo próprio, não derivado disso (DE-022). |
| **Sintética** | Conta com descendentes (grupo/subgrupo); soma o movimento das filhas. |
| **Retificadora** | Conta de natureza contrária dentro de um grupo, que reduz o total dele (ex.: depreciação acumulada, dentro do Ativo). |
| **Competência** | O mês contábil de uma empresa — a unidade de fechamento (CTB-07). |
| **Período de trabalho** | A janela de digitação corrente, diferente do fechamento formal (CTB-08). |
| **Lote** | Um lançamento contábil inteiro — o conjunto de débitos e créditos que precisa fechar em zero, não cada partida isolada. |
| **Partida** | Uma linha de débito ou crédito dentro de um lançamento (`ItemLancamento`). |
| **Origem** | De onde um lançamento veio: manual, escrita fiscal, folha, zeramento etc. (CTB-32). |
| **Zeramento** | O encerramento periódico (mensal, trimestral ou anual) que zera as contas de resultado e transfere o saldo ao Patrimônio Líquido (CTB-11). |
| **Encerramento do exercício** | O ato **anual** formal, distinto do zeramento periódico — inclui termos e, quando aplicável, compensação entre exercícios (CTB-24). |
| **Plano de contas referencial** | O plano de contas oficial da Receita Federal, ao qual cada conta analítica precisa estar vinculada para a ECD/ECF (CTB-50). |
| **ECD** | Escrituração Contábil Digital — o arquivo Sped com Diário, Razão e demonstrações (CTB-51). |
| **ECF** | Escrituração Contábil Fiscal — integra a apuração do IRPJ/CSLL à escrituração contábil (CTB-52). |
| **Lalur** | Livro de Apuração do Lucro Real — módulo próprio, fora deste plano (CTB-74). |
| **Classe de documento** | C (conferência), D (demonstração), L (livro), R (arquivo regulatório) — de [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md). |
| **Rascunho × efetivado** | Distinção ainda não implementada (BL-10): hoje todo lançamento nasce efetivado. |

## Perguntas abertas ao Fred, consolidadas

Todas já citadas no item correspondente; reunidas aqui para facilitar a
conversa com o Fred sem precisar reabrir os 74 itens.

1. **CTB-11/CTB-24 (HI-26/PE-38/PE-69):** como o escritório compensa lucros e
   prejuízos acumulados entre períodos — todo mês, só no fechamento anual, ou
   lançamento à mão? Na implantação de saldos, qual o tratamento de lucros e
   prejuízos acumulados? Como desfazer um zeramento feito com parâmetro
   errado?
2. **CTB-08:** o escritório usa um controle de "período de trabalho"
   diferente do fechamento mensal, ou o fechamento já basta?
3. **CTB-13/CTB-14:** o escritório emite DLPA isolada, ou sempre DMPL? Quais
   tipos de reserva usa além da legal?
4. **CTB-15:** o escritório precisa do método direto da DFC, do indireto, ou
   dos dois?
5. **CTB-16/CTB-17:** algum cliente da carteira é companhia aberta ou tem
   operação que gere "outros resultados abrangentes" ou exija DVA?
6. **CTB-18:** o escritório emite notas explicativas hoje, para quais
   clientes e com que conteúdo típico?
7. **CTB-25/CTB-26 (PE-60/PE-61):** o termo do livro precisa do cadastro
   **como era** na data do período, ou do atual? O que precisa sair em cada
   folha, não só na primeira?
8. **CTB-27:** o escritório usa carta de responsabilidade da administração
   na prática, para quais clientes?
9. **CTB-28/CTB-58 (BL-393):** quando a mesma pessoa é sócia de um cliente e
   contadora responsável de outro, é o mesmo cadastro com dois papéis, ou
   registros independentes?
10. **CTB-29 (PE-52):** qual é a legislação específica que exige autenticação
    de livro contábil digital?
11. **CTB-35/PE-35:** na alteração em massa, quais campos o escritório
    precisa corrigir na prática, e com que frequência?
12. **CTB-37 (HI-19):** o complemento do histórico padronizado entra sempre
    no fim, ou há históricos com lacuna no meio da frase?
13. **CTB-49 (PE-07):** qual é a política de backup e restauração hoje, e
    quem a executa?
14. **CTB-50/CTB-56 (BL-392):** a exigência de vincular 100% das contas ao
    plano referencial tolera conta com mais de um referencial válido, com
    escolha na partida?
15. **CTB-51:** o escritório transmite ECD hoje, para quais clientes, com
    qual periodicidade?
16. **CTB-53:** qual critério de custeio (PEPS, custo médio) o escritório
    usa para CMV/CPV?
17. **CTB-55:** quando um cliente reorganiza o plano de contas de um ano para
    o outro, o escritório registra a correspondência entre contas, ou ela se
    perde hoje?
18. **CTB-57:** alguma empresa da carteira precisa de duas contas analíticas
    com a mesma classificação (filial, SCP)?
19. **CTB-59/CTB-67:** há clientes em grupo econômico que precisam de
    balancete ou DRE consolidado? O escritório usa plano de contas
    padronizado entre clientes?
20. **CTB-64 (PE-34):** existe necessidade real de apagar escrituração sem
    possibilidade de regeração (volume, empresa que saiu da carteira, LGPD)?
21. **CTB-65:** existe hoje a prática de copiar lançamento de um cliente para
    outro? Qual é o caso de uso real?
22. **CTB-66/CTB-68:** algum cliente tem SCP registrada, ou matriz/filiais em
    escrituração centralizada?
23. **CTB-69:** o escritório atende empresa com contabilidade gerencial
    paralela à oficial?
24. **CTB-70:** algum cliente tem investimento no exterior que exija
    consolidação em moeda estrangeira?
25. **CTB-71 (PE-32):** quais obrigações contábeis o escritório de fato
    entrega hoje (ECD, ECF, arquivos setoriais)?
26. **CTB-72:** confirmação de que o FCONT está extinto (indício: Lei
    12.973/2014).
27. **CTB-73:** o escritório atende entidade sem fins lucrativos que exija
    DSP?
28. **CTB-74:** o Lalur está no horizonte próximo do escritório, ou é
    distante?

> Auditoria de software não substitui a validação profissional das regras
> contábeis e legais (AGENTS.md §10). Todo item marcado "a confirmar" neste
> plano precisa de leitura da fonte oficial vigente, com item e data de
> consulta citados, e validação do Fred como responsável técnico, antes de
> qualquer linha de código de cálculo ou leiaute.

## Itens acrescentados pela DL-068

Encontrados na análise de 05/10/2026 (pesquisa normativa e releitura dos
manuais). Detalhe, fonte e critério de aceite na
[DL-068](../../planos/DL-068-plano-do-modulo-contabil.md); cada um vira plano
próprio quando priorizado.

| ID | Item | Por que entrou | Situação no DataLedger |
| --- | --- | --- | --- |
| CTB-75 | Subcontas correlatas | Lei 12.973/2014 (ajuste a valor justo, mais e menos-valia, ágio) e a ECD pedem o vínculo da subconta à conta principal | Não existe |
| CTB-76 | Implantação de saldos | CON-03 do plano mestre não tinha item CTB; sem ela nenhum cliente novo entra; a Lei 15.270/2025 exige separar lucros acumulados por exercício de apuração | Não existe |
| CTB-77 | Perfil contábil e matriz de demonstrações | O conjunto exigido muda por porte (NBC TG 1001 e 1002), natureza (LSA art. 176) e exercício | Não existe |
| CTB-78 | Comparativo com o exercício anterior | LSA art. 176, §1º | Não existe em nenhuma demonstração |
| CTB-79 | Lucros por exercício de apuração e deliberação | Transição da Lei 15.270/2025 (lucros até 2025 aprovados até 31/12/2025) | Não existe |
| CTB-80 | Pré-validação da ECD e riscos contábeis-fiscais | Conferir antes do programa oficial; caixa credor, contas de sócios, AFAC, lucros acumulados positivos em S/A | Não existe |
| CTB-81 | Cruzamentos com obrigações | ECD × ECF, ECF × DCTFWeb/MIT, Reinf × DARF × razão, EFD-Contribuições × ECD; os cruzamentos com DIRF e DCTF clássica não valem mais | Não existe |
| CTB-82 | Demonstrações pela NBC TG 51 | Exercícios iniciados a partir de 01/01/2027 | Não existe |
| CTB-83 | IBS e CBS na contabilidade | Orientação Técnica CFC nº 1/2026; CBS substitui PIS e Cofins em 01/2027 | Não existe |
| CTB-84 | Reserva de incentivos fiscais | Lei 14.789/2023, arts. 16 e 18 | Não existe |
