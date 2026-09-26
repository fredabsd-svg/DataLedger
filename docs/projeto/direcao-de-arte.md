# Direção de arte do DataLedger

**Leia antes de desenhar a primeira tela de qualquer módulo novo** — Fiscal,
Folha, Honorários, Processos/Paralegal, Lalur/ECF, portal do cliente. Também
antes de acrescentar tela a um módulo existente.

Isto não é um manual de gosto. É o contrato visual do produto, e ele existe por
um motivo prático: **um sistema contábil que muda de cara a cada módulo obriga
o usuário a reaprender a ler**. Quem passa oito horas por dia aqui não pode
gastar atenção decifrando onde está o total desta vez.

A escolha da direção está em **[DE-053](decisoes.md)**, confirmada pelo Fred em
**RC-90**, e foi decidida por medição, não por gosto: ver
[`docs/assets/design/gauntlet/MEDICOES.md`](../assets/design/gauntlet/MEDICOES.md).

## A tese, em uma frase

**Tipografia é a estrutura, o número é o herói, e a cor quase não aparece** —
a interface herda a autoridade do impresso bem diagramado, não a estética de
software.

## 1. Os tokens moram no CSS, não aqui

**Este documento não contém um único valor de cor, tamanho ou espaçamento.**
Isso é deliberado, e é a lição mais cara deste projeto: em 2026-09-13 o mesmo
fato estava escrito em quatro lugares do README e já tinha divergido. Texto
duplicado diverge assim que alguém atualiza um lugar.

A **fonte única dos valores é [`static/css/base.css`](../../static/css/base.css)**,
no bloco `:root`. Aqui ficam só os **papéis** de cada família de token, e a
regra de uso:

| Família | Papel | Regra |
| --- | --- | --- |
| Tinta (texto) | Principal, secundária, auxiliar | Texto auxiliar **também** respeita 4,5:1; "é só uma legenda" não isenta ninguém |
| Papel (fundo) | Superfície da página, superfície elevada, faixa de destaque | Nunca branco puro na página inteira: a direção é papel, não tela de escritório |
| Acento | **Uma** tinta, para ação principal e foco | Se aparecer uma segunda cor de acento, a direção foi quebrada |
| Semânticas | Sucesso, erro, aviso, informação | Sempre acompanhadas de **texto**; nunca sozinhas |
| Numérico | Família monoespaçada tabulada | Todo algarismo de valor, sem exceção |
| Espaço | Escala de espaçamento | Nada de medida solta: se precisa de um valor que não existe na escala, a escala está errada ou o desenho está |

**Proibido**: cor, tamanho de fonte, raio ou espaçamento escrito direto em
template ou em regra CSS de tela. Se o token não existe, crie o token.

## 2. Os cinco arquétipos de tela

Todo módulo do DataLedger cai nestes cinco. Antes de inventar um sexto,
convença-se de que ele não é um destes com outro nome.

### A. Tabela de consulta

Balancete, Razão, Diário, livro fiscal, folha do mês, relação de honorários,
relação de processos.

- **Cabeçalho da tabela fixo** ao rolar. **Totalizador fixo** também: o total
  nunca exige rolar até o fim.
- **Números à direita, com largura de dígito constante.** Colunas não dançam.
- **Hierarquia por peso e recuo**, não por coluna "nível" nem por cor.
- **Valor invertido em relação à natureza do registro vai entre parênteses** —
  convenção contábil mais antiga que a tinta vermelha e mais difícil de
  adulterar: um traço transforma `-` em `+`; um parêntese não se desfaz.
- **Filtro não come a tela.** É o defeito mais reclamado do concorrente
  internacional: barras demais antes do dado. Ver a régua de densidade (§4).
- Exportação e impressão saem com a **marca do escritório**, nunca com a do
  DataLedger — é vício documentado do mercado nacional, e o produto promete o
  contrário **na própria tela**.

### B. Formulário de documento

Lançamento contábil, nota fiscal, rubrica de folha, título de honorário,
protocolo de processo.

- A **pergunta de verdade do documento** fica visível **antes de gravar**, numa
  faixa fixa: no contábil é "fecha ou não fecha"; nos outros módulos, ver §3.
- Campo tem **rótulo**, sempre. Placeholder não é rótulo.
- **Erro é texto**, com o que fazer a seguir. Cor é reforço.
- O formulário **não some** quando dá erro: o que a pessoa digitou continua lá.
- Estado **sem permissão** é desenhado: o botão aparece desabilitado **com o
  motivo**, nunca sumindo — sumir ensina a pessoa a duvidar da própria memória.
  E a autorização de verdade é conferida **no servidor**, não na tela.

### C. Caixa de entrada e conferência

Recepção de NFS-e, documentos do portal, importações, pendências do mês.

- Cada item mostra **em que estado está** e **o que falta**, em texto.
- Duplicidade e rejeição são **primeira classe**, não nota de rodapé: é para
  isso que a tela existe.
- Nome de pasta ou de arquivo **não decide natureza de operação** — o conteúdo
  decide.

### D. Painel de período

O que o módulo mostra quando a pessoa entra nele.

- Responde três perguntas em um relance: **em que empresa estou**, **em que
  competência**, e **o que falta fazer**.
- Não é vitrine de métrica. Caixinha bonita sem dado acionável é espaço
  roubado da tabela.

### E. Assistente com etapas

Implantação de saldos, fechamento de competência, apuração, transmissão de
obrigação.

- Cada etapa diz **o que vai acontecer** e **o que ainda dá para desfazer**.
- A última etapa mostra o que será gravado **antes** de gravar.
- Assistente nunca esconde o caminho manual de quem já sabe o que quer.

## 3. O "momento da verdade" de cada módulo

O arquétipo B exige que a pergunta central do documento esteja visível antes de
gravar. Ela **muda por módulo**, e é isto que dá identidade funcional a cada um
sem mudar a identidade visual:

| Módulo | A pergunta que a tela responde antes de gravar |
| --- | --- |
| **Contábil** | Débito é igual a crédito? |
| **Fiscal** | O documento é elegível, não é duplicado, e a apuração confere com a memória de cálculo? |
| **Folha** | Proventos menos descontos dá o líquido, e as bases de encargo batem? |
| **Honorários** | O que está sendo faturado corresponde ao contrato vigente, e não é cobrança repetida? |
| **Processos/Paralegal** | A etapa tem a evidência exigida, e o prazo em risco está à vista? |
| **Lalur/ECF** | O resultado contábil concilia com a base fiscal depois das adições e exclusões? |

Quem for construir um módulo novo **escreve a sua linha nesta tabela antes de
desenhar a tela**. Se não souber responder, o problema não é de design.

## 4. As regras que não se negociam

Valem para todo módulo, e são medidas por mecanismo (§5).

1. **Todo algarismo de valor é tabulado.** Declaração de fonte não prova nada:
   `111111` e `888888` têm de ter a **mesma largura** — é assim que se mede.
2. **Contraste calculado**, nunca estimado: 4,5:1 em texto, 3:1 em borda de
   componente e em indicador de foco.
3. **Cor nunca é o único canal** de informação. ~8% dos homens têm deficiência
   de visão de cor.
4. **Foco de teclado visível**, e o estilo muda **de fato** ao focar.
5. **Nenhuma dependência externa**: sem CDN, sem biblioteca visual, sem fonte
   remota (DE-011). Fonte auto-hospedada vem com a licença junto.
6. **JavaScript é enfeite.** Nenhum dado existe só porque um script rodou.
7. **Sem rolagem horizontal em 1280px.**
8. **Densidade medida, não alegada — e o número de referência é o do PRODUTO.**
   A tela de tabela de um módulo novo é medida em 1280×800, com base
   realista, contando linha **inteiramente** visível sem rolar, e o método vai
   escrito junto (quantas contas, qual tela, qual largura).

   ⚠️ **Esta regra dizia "pelo menos 15 linhas" e estava errada.** Os 15 vinham
   do **protótipo** do gauntlet; a auditoria mediu o **produto** e achou **9** no
   balancete com período filtrado (achado M1 da [rodada
   1](../auditorias/2026-09-18-dl-024-rodada-1.md)). Um módulo novo estava
   prestes a ser cobrado contra um número que a tela de referência não
   alcança.

   **O piso, hoje, é o que a referência entrega, com o método junto:**

   | Tela | Piso medido | Em que estado | Medido em |
   | --- | --- | --- | --- |
   | Balancete | **10** | **com período filtrado** | `53388c8` |
   | Balancete | **5** | **entrada padrão, mês sem movimento** | `53388c8` |
   | Plano de contas | **14** | — | `53388c8` |
   | Diário | **14** | — | `53388c8` |
   | Razão | **sem piso publicado** | ver a nota abaixo | — |

   ⚠️ **A linha do Razão saiu desta tabela, e a razão é constrangedora para
   mim.** Eu publiquei aqui "**11**, conta consolidada", e a sexta auditoria
   registrou (**F8**) que **não conseguiu reproduzir o número** com a base
   semeada: a conta mais movimentada dela rende 5 lançamentos. O 11 veio de
   uma conta que eu não nomeei — e número sem o dado que o produz é
   exatamente o defeito **M4** que eu acabara de fechar, cometido por mim na
   mesma linha em que o fechei.

   O Razão volta a ter piso quando a base de medição tiver uma conta
   deliberadamente concentrada (**BL-339**, aberto). Até lá, **não há piso do
   Razão**, e isso é melhor do que um piso que ninguém consegue conferir.

   ⚠️ **Esta tabela já divergiu uma vez, e a correção está aqui pelo motivo
   errado ter acontecido.** Até a rodada 6 ela dizia 9 / 4 / 14 / 11, e não
   tinha linha do Razão. A rodada 6 **mediu** os números novos — eles estavam
   no `BL-277`, no backlog — e não os trouxe para cá. O auditor achou na
   rodada 5 (**M4**): *"quem for construir o Fiscal vai medir a sua tabela
   contra um Diário de 11 linhas que na verdade entrega 14 — e vai entregar
   uma tela pior que a referência **cumprindo o contrato**"*.

   **A classe é:** o número medido foi publicado no registro da **tarefa** e
   não no **contrato**. Backlog é histórico de quem fez; este documento é o
   que o próximo lê. O número vive nos dois, e divergiu no primeiro dia — que
   é exatamente a lição de 2026-09-13 citada no §1 deste mesmo arquivo.

   **Enquanto esta tabela for texto escrito à mão, ela vai divergir de novo.**
   A correção durável é gerá-la a partir da medição, e ela depende do
   instrumento que o **BL-337** está criando (hoje a medição de impressão nem
   instrumento versionado tem). Até lá, isto é uma obrigação humana declarada,
   não uma garantia — e está escrito assim de propósito.

   **Procedência dos números acima:** medidos de forma independente pelo
   `auditor-qa` na quinta auditoria
   ([relatório](../auditorias/2026-09-19-dl-026-rodada-5.md), §1), com Chromium
   próprio e base semeada por ele, batendo com os que o
   `especialista-frontend` havia medido no BL-277. Dois instrumentos
   independentes, mesmo resultado.

   **Método, sem o qual os números acima não valem nada:** 1280×800, base
   sintética de **73 contas em 4 níveis e 60 lançamentos**, contando linha
   **inteiramente** visível (`rect.top >= 0 && rect.bottom <= innerHeight`),
   Chromium.

   **A base é reproduzível:**
   [`scripts/semear_base_de_medicao.py`](../../scripts/semear_base_de_medicao.py),
   com semente fixa. Até a rodada 2 ela morava fora do repositório, no
   scratchpad de quem mediu — o achado B2 chamou isso de *"medição que só uma
   pessoa consegue repetir"*, e tinha razão. A contagem é feita pelo juiz do
   gauntlet, que **não roda na integração contínua** porque exige Chromium.
   Logo: **rodar a medição antes de fechar etapa que mexa na altura acima da
   primeira linha** — faixa, filtro, aviso, título — é obrigação escrita, não
   automatizada. Foi uma mudança desse tipo que derrubou a densidade de 9 para
   6 sem nenhum teste acusar.

   ⚠️ **Esta regra já errou duas vezes, e as duas por publicar número sem
   método.** Primeiro dizia "pelo menos 15", que eram do **protótipo** do
   gauntlet e não do produto (achado M1 da [rodada
   1](../auditorias/2026-09-18-dl-024-rodada-1.md)). Corrigido para 9 — e o
   texto corrigido **continuou sem dizer** quantas contas, qual largura e, o
   que mais importa, que os 9 são **com período filtrado**: a entrada padrão
   entrega **4** (achado B1 da [rodada
   2](../auditorias/2026-09-18-dl-024-rodada-2.md)). Quem fosse construir o
   Fiscal e medisse "o balancete" como ele abre encontraria 4 e concluiria que
   a referência não cumpre o próprio piso.

   **A lição é a do parágrafo acima, que já exigia o método e não foi
   obedecido pelo parágrafo seguinte:** número sem método é opinião com casas
   decimais — inclusive quando o número está certo.

   Os **15 continuam como meta**, com a causa nomeada e item de backlog
   próprio. Abaixar a meta para caber no resultado seria trocar a medição pela
   conveniência; fingir que o piso é 15 seria pior.
9. **pt-BR em tudo**: `1.234,56`, `dd/mm/aaaa`, e o termo que o contador usa.
10. **O que já foi auditado não regride.** Contraste, foco, estados e mensagens
    de erro custaram rodadas de auditoria nas DL-009, DL-017 e DL-026.

## 5. Como isto é verificado, e não só pedido

Regra sem mecanismo é só pedido — e este projeto já aprendeu isso três vezes.
A verificação é a varredura de interface descrita na
[DL-026](../planos/DL-026-identidade-visual-e-interface.md), que reprova a
integração contínua quando:

- um template usa cor, tamanho ou espaçamento **fora dos tokens**;
- uma tabela de valores tem célula numérica **sem tabulação**;
- uma tabela não tem `caption` nem `th` com `scope`;
- um template de tela **não estende** a moldura comum;
- um módulo novo aparece **sem a sua linha** na tabela do §3.

**Enquanto a varredura não existir, este documento é instrução, não garantia**
— e está escrito assim de propósito.

## 6. Checklist para módulo novo

Antes de abrir a primeira tela do Fiscal, da Folha, de Honorários, do Paralegal
ou do Lalur:

1. Escreva a linha do módulo na tabela do §3 — a pergunta que a tela responde.
2. Classifique cada tela prevista em um dos cinco arquétipos do §2.
3. Confirme que **nenhum token novo** é necessário. Se for, ele nasce em
   `base.css` com o contraste medido, não na folha de estilo da tela.
4. Desenhe os **cinco estados** antes do caminho feliz: vazio, carregando,
   erro, sucesso, sem permissão.
5. Meça a densidade da tela de tabela **antes** de considerá-la pronta.
6. Rode a varredura de interface (§5) e a suíte.

## 7. Limites declarados desta direção

- **Nenhum leitor de tela real** foi usado até aqui — nem NVDA, nem VoiceOver.
  O que existe é marcação correta e contraste medido, o que **não é a mesma
  coisa** que ter sido usado por quem depende dele.
- **Só Chromium foi testado.** Firefox e Safari, não.
- **Modo escuro não faz parte da direção** por enquanto. Se entrar, entra com
  contraste recalculado, não por inversão automática.
- **Celular é consulta, não operação.** A direção é desenhada para 1280px ou
  mais; telas pequenas recebem leitura, não lançamento.
- A régua de densidade vale para **1280×800**, e o piso é o **medido no
  produto** (§4.8), não o do protótipo. Em monitor maior o ganho é
  proporcional; em tela menor a regra precisa de medição nova, não de
  estimativa.
- **Os HTML dos três protótipos do gauntlet não estão versionados** — só as
  capturas. A medição que escolheu a direção **não é reproduzível hoje**, e
  isso é limite desta decisão, não detalhe de arquivo.
- **A cor do TEXTO na tela não é a cor do texto no PDF exportado, e isso foi
  medido em 2026-09-20 (BL-440).** Texto claro com **múltiplos canais RGB
  elevados** sai **mais escuro** no PDF do que a tela mostra:
  `rgb(137,138,139)` vira `(54,54,55)`. **Cor de canal único passa intacta**
  (`rgb(137,0,0)` sai `137,0,0`), e **forma vetorial SVG é fiel** — o mesmo
  `rgb(137,138,139)` num `<rect>` exporta exato. A **captura de tela** também é
  fiel: só o **texto no PDF** diverge.

  ⚠️ **O mecanismo interno do Chromium/Skia NÃO foi determinado**, e está
  escrito assim de propósito. O que foi determinado, por inspeção dos bytes do
  PDF: o fluxo já contém a cor deslocada, então a transformação é da
  **exportação de texto**, não da rasterização nem da renderização. Duas
  hipóteses foram **descartadas por medição**: leitura errada do fluxo (o
  operador é único e imediatamente anterior ao `Tj`) e segundo objeto de desenho
  (há um só bloco `BT…ET` por elemento).

  ⚠️ **A direção do desvio é SEGURA** — mais escuro significa **mais**
  contraste, não menos. E o impacto prático hoje é **baixo**: o produto imprime
  o timbre com tokens escuros. **Mas a [DL-027](../planos/DL-027-documento-emitido-e-personalizacao.md)
  é a etapa que deixa cada escritório escolher a cor**, e é nela que isto deixa
  de ser curiosidade: *a cor que o escritório escolher na tela não é a que sai
  no papel*. Quem desenhar aquela tela precisa saber disto **antes**, e é por
  isso que está aqui e não só no backlog.

## 8. Navegação global, trilha e cabeçalho de página (DL-040)

O produto ganhou um menu ESTRUTURADO por módulo — antes disso, a navegação
principal (`templates/base.html`) era uma lista plana de dois links
("Painel", "Empresas"), e cada módulo novo (Fiscal, e os que ainda vão
nascer) só tinha como se anunciar acrescentando mais um item à mesma
lista, sem hierarquia. O mapa completo — quantas telas existem, quais são
ativas/secundárias, e o raciocínio da barra superior — está em
[mapa-de-telas.md](mapa-de-telas.md); esta seção fixa só o PADRÃO, para o
próximo módulo seguir sem reabrir a discussão.

### 8.1 Menu principal

- **Revisão (DL-042).** Barra **lateral** esquerda, não mais superior —
  decisão revertida em relação à DL-040 (raciocínio completo, incluindo
  o PORQUÊ da escolha original, em
  [mapa-de-telas.md](mapa-de-telas.md#revisão-dl-042-barra-lateral-não-superior),
  para não duplicar o mesmo fato aqui). Resumo: o argumento de largura da
  DL-040 ("lateral fixa tira ~220px sempre") só vale para lateral que não
  recolhe; a DL-042 implementa recolhimento a `--largura-barra-lateral-
  recolhida` (56px, só ícones) só em CSS (técnica "checkbox hack" —
  `input[type=checkbox]` oculto + `:checked ~ seletor`, sem JavaScript),
  então o custo de largura passa a ser escolha de quem usa a tela, não
  perda fixa. `--largura-barra-lateral` (expandida) é 15rem/240px, dentro
  da faixa 220–260px que `shell-navegacao.md` (skill) recomenda.
- **Ícones** (novidade da DL-042): um conjunto próprio de SVG embutidos
  (`<symbol>` num sprite oculto em `templates/base.html`, referenciado por
  `<use>`), 18px, traço único via `currentColor` — existem porque o modo
  recolhido, só com texto, seria ilegível; não existiam antes (a
  identidade "papel e tinta" não usava ícone nenhum). O rótulo de texto
  (`.rotulo-menu`) continua sendo o nome acessível do link mesmo recolhido
  (técnica de `.visualmente-oculto`: afasta da tela, nunca `display:
  none`) — o ícone é sempre `aria-hidden`.
- Cada módulo é um item com submenu em **dropdown nativo**
  (`<details>`/`<summary>`) — nenhuma dependência de JavaScript (regra 6
  deste documento). O item do módulo ativo recebe `aria-current="page"`
  no próprio `<summary>`; cor nunca é o único sinal (o texto do rótulo já
  diz qual módulo é).
- Um módulo só aparece no menu para quem o SERVIDOR já deixaria entrar —
  a mesma função de permissão do domínio decide as duas coisas (nunca uma
  lista de papéis própria do menu). O menu deixa de CONVIDAR quem seria
  recusado; a recusa em si nunca é decidida na tela.
- **Nenhum dado sensível de OUTRA empresa aparece no menu de uma tela
  escopada a UMA empresa** — nem numa lista de opções, nem num rótulo.
  Medido: a primeira versão desta etapa listava as demais empresas do
  escritório num seletor embutido em toda tela de uma empresa, e isso
  vazava a razão social de uma empresa na tela de OUTRA (mesmo
  escritório) — contra a garantia do AGENTS.md de que "dados de empresas
  diferentes ficam isolados". A troca de empresa existe (`empresas:
  trocar-secao`), mas o caminho até ela passa pela tela que já lista
  todas as empresas de propósito (`empresas/lista.html`), nunca por um
  item de menu que repita nomes de empresa na tela de uma empresa
  diferente.
- **Revisão (DL-040, segunda passada).** A regra acima — um item por
  módulo, sem repetir a navegação interna da tela — respondia à
  duplicação de FORMA, mas escondia telas ativas do escritório inteiro:
  quem abria "Contabilidade" sem estar dentro de uma empresa via só
  "Plano de contas", nunca o Diário, o Balancete, o Balanço, a
  Conferência ou o Fechamento — e quem já estava numa tela de
  contabilidade não enxergava as OUTRAS telas do módulo sem sair da
  página e procurar `_navegacao_empresa.html`. Revisão: cada dropdown de
  módulo lista **todas as suas telas ativas**, agrupadas por rótulo de
  grupo (`<p class="menu-grupo__rotulo">` + `<ul aria-labelledby="...">`)
  — ex. Contabilidade → **Movimento** (Novo lançamento) · **Cadastros**
  (Plano de contas) · **Relatórios** (Diário, Balancete, Balanço — o
  Razão fica só como atalho dentro do item do Diário/Plano de contas,
  porque exige uma conta escolhida, não é destino direto) ·
  **Rotinas** (Conferência, Fechamento) · "Trocar de empresa" ao fim.
  Isso **reintroduz**, de propósito, a redundância que a regra antiga
  evitava: a mesma tela aparece tanto no dropdown quanto em
  `_navegacao_empresa.html` (esta última segue viva em telas largas —
  ver 8.1a). A redundância é aceita porque resolve um problema maior
  (descoberta do módulo a partir de QUALQUER tela, inclusive fora de uma
  empresa) e porque as duas fontes são geradas do MESMO padrão de
  permissão/URL, não de listas independentes que poderiam divergir sem
  aviso — o teste de mutação de
  `apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py`
  continua provando que os atalhos de teclado (`Alt+`) vivem SÓ em
  `_navegacao_empresa.html`; o dropdown nunca duplica atalho, só o link.
  O item da tela atual aparece sempre (nunca escondido), mas como texto
  simples com `aria-current="page"`, nunca como link para si mesma. Sem
  empresa no contexto (ex.: painel, fora de qualquer empresa), o
  dropdown de Contabilidade mostra "Escolha uma empresa" apontando para
  `empresas:lista` — nunca um item de tela que exigiria uma empresa
  inexistente.

### 8.1a Menu em telas estreitas (≤48rem)

Primeiro breakpoint responsivo do produto. Até a DL-040 a barra superior
cabia numa linha em qualquer largura testada; medido naquela etapa a
390×844 (iPhone padrão de teste): o menu quebrava em duas linhas, "Sair"
ocupava uma linha própria, e a faixa de contexto empilhava cinco blocos
(usuário, escritório, empresa, período, emitido em) — o título da tela
só aparecia a **≈470px** do topo, abaixo da dobra em qualquer aparelho
comum. A DL-040 corrigiu para **≈230px**; a DL-042 (nova moldura,
medição própria) mede **≈270px** no mesmo Balancete — uma pequena
regressão em relação à DL-040, registrada como resultado honesto (não
arredondado para parecer melhor): a barra lateral, mesmo recolhida por
padrão no celular (vira gaveta fechada), soma uma faixa "marca + Menu"
própria acima do cabeçalho de contexto, que a barra superior não tinha
(ela JÁ ERA essa faixa).

- **Revisão (DL-042).** Abaixo de `48rem` de largura, a barra lateral
  inteira (`<aside class="barra-lateral">`) vira GAVETA, recolhida atrás
  de um botão "Menu" — mesma técnica "irmão, nunca envoltório" da DL-040
  (abaixo), só que aplicada à barra lateral em vez da `<nav>`:
  `<details class="menu-movel-gatilho">` é IRMÃO de `.barra-lateral`
  dentro de `.app-shell` (nunca a envolve), e a visibilidade dela é
  controlada pelo combinador de irmão geral do CSS
  (`.menu-movel-gatilho[open] ~ .barra-lateral { display: flex; }`).
  **Achado de implementação da DL-040, ainda válido:** um `<details>`
  fechado é excluído da árvore de composição pelo navegador — um
  `display` forçado com `!important` num DESCENDENTE do `<details>`
  fechado não funciona, mesmo que `getComputedStyle` diga que o valor
  está "certo". Por isso o elemento controlado precisa ficar FORA do
  `<details>`, como irmão, nunca dentro.
- **Achado novo da DL-042, medido nesta etapa:** com `flex-wrap: wrap`
  (necessário para a barra empilhar abaixo da faixa "marca + Menu") e
  `min-height: 100vh` no contêiner (`.app-shell`), o `align-content`
  PADRÃO (`stretch`) distribuía a altura extra entre as DUAS linhas do
  flex, esticando a primeira e empurrando o conteúdo ~230px para baixo —
  um vão em branco medido em `empresas/lista.html`. Corrigido com
  `align-content: flex-start`. Registrado porque é o tipo de defeito que
  só aparece com conteúdo curto (poucas linhas) somado a `min-height`
  alto — o gauntlet e a maioria das telas de tabela, mais longas, não o
  revelariam.
- A faixa de contexto (`.cabecalho__contexto`) continua compacta: só
  empresa e período numa linha; usuário e escritório vivem só dentro do
  menu "Conta" (8.4a) — a informação não desaparece, só muda de lugar, e
  "Escritório ativo" continua presente na tela (não dentro de um
  `<details>` fechado) porque a impressão depende dele em telas sem
  timbre (ver 8.5 e o teste
  `test_cabecalho_mostra_escritorio_ativo_em_toda_pagina_autenticada`).
- `_navegacao_empresa.html` (os seis atalhos com `Alt+`) fica oculta
  nesta largura — com o dropdown/gaveta agora completo (8.1), ela vira
  redundante justamente na largura onde espaço é mais caro; os atalhos
  de teclado continuam documentados e funcionando (não dependem de
  estarem visíveis), só o texto/link visual some.

### 8.1b Largura do conteúdo em telas grandes

`--largura-conteudo` passou de `75rem` (1200px) para `90rem` (1440px) —
medido no Balancete a 1440×900: a área útil de tabela ganha 240px
(+20%), sem alterar o layout de formulário (os arquétipos B continuam
confortáveis porque a largura é um TETO, não uma largura fixa — um
formulário curto não estica até a borda). Critério: mais colunas de
tabela visíveis sem rolagem horizontal, na régua de densidade já fixada
pelo §4.8.

### 8.2 Trilha de navegação (breadcrumbs) e "Voltar"

- `<nav aria-label="Trilha de navegação">` com uma lista ordenada
  (`<ol>`), mais um link/botão "Voltar" nas telas secundárias — os dois
  juntos, no topo do conteúdo, antes de qualquer mensagem.
- **Revisão (DL-040, segunda passada).** A regra original ("só em telas
  secundárias") deixava as telas ATIVAS sem resposta para "onde estou" —
  a única pista de contexto era a faixa `.cabecalho__contexto`
  (empresa/período), sem o caminho de módulos que levou até ali. Agora a
  trilha aparece em **toda tela autenticada abaixo de Início**, ativa ou
  secundária: um `{% block trilha %}` em `base.html` gera a trilha
  padrão (`Início › Módulo › Empresa › Tela`) a partir do
  `resolver_match` e do `context_processor`
  `apps.core.context_processors.navegacao_do_menu`, sem cada template
  precisar montá-la à mão; telas secundárias continuam podendo
  sobrescrever o bloco quando precisam de um passo a mais (ex.: "Voltar
  para Documentos" no detalhe fiscal). Uma tela pode ZERAR o bloco
  (`{% block trilha %}{% endblock %}`) quando a trilha padrão vazaria
  informação que a própria tela existe para esconder — caso real:
  `balancete_emissao_recusada.html` é servida quando a emissão do
  Balancete é recusada por regra de negócio, e a trilha padrão mostraria
  o nome da empresa numa tela pensada para não expor mais do que o
  aviso.
- O último item da trilha é a própria tela, em texto, com
  `aria-current="page"` — nunca um link para a página atual (mesma regra
  do item de menu ativo).

### 8.3 Cabeçalho de página

Título (`<h1>` único), contexto (quando houver — empresa, competência) e
a área de ações, numa faixa só: `.cabecalho-pagina` (título +
`.cabecalho-pagina__acoes`, à direita). Padrão aplicado onde uma tela
ativa tem uma ação primária clara (ex.: "Nova empresa" na lista de
empresas) — não é obrigatório em toda tela: uma tela de documento
imprimível (Balancete, Diário, Razão, Balanço) não ganha um botão de ação
ao lado do título, porque ali o título É parte do papel impresso
(`titulo_sufixo_do_fornecedor`, `templates/base.html`) e ações de tela
(botões) já são ocultadas na impressão por regra própria.

### 8.4 Botão de ação — três tons, nunca mais

`.botao--primario` (ação principal — mesmo visual do `<button>` padrão),
`.botao--secundario` (ação alternativa — "Voltar", trocar contexto) e
`.botao--perigoso` (ação sensível — reabrir competência, marcar como
entregue). O TOM é reforço; o texto do botão já nomeia a consequência
("Reabrir competência 09/2026", nunca só "Confirmar") — mesma regra do
arquétipo E (§2) aplicada ao próprio rótulo do botão, não só ao texto ao
redor dele.

### 8.4a Menu "Conta" (DL-040, segunda passada; reposicionado na DL-042)

Usuário, e o botão "Sair" ficam agrupados num dropdown "Conta" (mesmo
padrão `<details>`/`<summary>` do menu de módulo, sem JavaScript),
liberando a faixa de contexto para informação do DOCUMENTO/tela em vez de
informação da SESSÃO. **Revisão (DL-042):** o menu "Conta" migrou do
canto superior direito (DL-040) para o RODAPÉ da barra lateral —
`.barra-lateral__rodape`, mesmo padrão "configurações/perfil no rodapé"
que `shell-navegacao.md` (skill) recomenda para a navegação lateral;
conteúdo e regras idênticos, só a posição mudou. **Uma
exceção deliberada:** "Escritório ativo" **não** entrou no menu Conta —
continua na faixa de contexto (`.cabecalho__contexto`), porque cinco
telas sem timbre próprio dependem dele para identificação no papel
impresso (`test_cabecalho_mostra_escritorio_ativo_em_toda_pagina_autenticada`)
e qualquer coisa dentro de um `<details>` fechado fica fora da árvore de
composição do navegador (8.1a) — inclusive na impressão. Mover
"Escritório ativo" para dentro do menu Conta teria escondido a
identificação exigida sempre que alguém imprimisse com o menu fechado,
que é o estado padrão. Não há hoje tela de "Configurações" nem
"Convites" no produto (mapa-de-telas.md confirma: `tenancy:
emitir-convite` não tem template) — o menu Conta não lista itens que
não existem.

### 8.5 Impressão

Menu, trilha e qualquer seletor de navegação somem no papel — a mesma
lista de `display: none` de `@media print` que já escondia o menu antigo
ganhou as classes novas (`.trilha`), sem precisar de uma segunda regra:
`.menu-dropdown` nasce DENTRO de `.barra-lateral` (DL-042) ou, antes
dela, de `.cabecalho__topo` (DL-040) — em qualquer um dos dois, o
container já era oculto inteiro. Medido na DL-040, por captura de tela em
modo impressão do produto real: o documento impresso não ganhou nem
perdeu identificação nenhuma.

**DL-042, verificado por navegador real (Chromium, `page.emulate_media
("print")`, contra o produto rodando de verdade, não simulação de CSS em
Python):** no Balancete (tela COM timbre), `.barra-lateral` fica oculta,
`.cabecalho__contexto` continua visível, `.timbre-impressao` aparece; no
Plano de contas (tela SEM timbre), `.barra-lateral` também some e
`.cabecalho__contexto` — com "Escritório ativo" — continua sendo a única
identificação do emitente, visível. **Não medido nesta etapa:** a
PAGINAÇÃO do PDF (quantas folhas, se o cabeçalho da tabela repete em
cada uma) — `scripts/medir_identificacao_do_emitente.py` exige
`pdfinfo`/`pdftotext` (poppler-utils), indisponíveis neste ambiente (sem
rede para `apt install`); a suíte `pytest` de timbre/impressão
(`apps/contabilidade/tests/test_bl282_timbre_de_impressao.py`) continua
verde. Rodar aquele script antes de integrar, num ambiente com
poppler-utils — ver "Bloqueado" no relatório de entrega da DL-042.
