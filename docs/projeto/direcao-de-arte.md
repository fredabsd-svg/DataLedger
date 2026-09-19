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
   | Razão | **11** | conta consolidada, período filtrado | `53388c8` |

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
