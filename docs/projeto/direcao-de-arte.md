# Direção de arte do DataLedger

**Leia antes de desenhar a primeira tela de qualquer módulo novo** — Fiscal,
Folha, Honorários, Processos/Paralegal, Lalur/ECF, portal do cliente. Também
antes de acrescentar tela a um módulo existente.

Isto não é um manual de gosto. É o contrato visual do produto, e ele existe por
um motivo prático: **um sistema contábil que muda de cara a cada módulo obriga
o usuário a reaprender a ler**. Quem passa oito horas por dia aqui não pode
gastar atenção decifrando onde está o total desta vez.

A escolha da direção está em **[DE-042](decisoes.md)**, confirmada pelo Fred em
**RC-89**, e foi decidida por medição, não por gosto: ver
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
8. **Densidade medida, não alegada.** A tela de tabela de um módulo novo mostra
   **pelo menos 15 linhas** em 1280×800 sem rolar. O número existe porque foi
   medido: o estado anterior mostrava ~8, e a direção escolhida mostra 15.
9. **pt-BR em tudo**: `1.234,56`, `dd/mm/aaaa`, e o termo que o contador usa.
10. **O que já foi auditado não regride.** Contraste, foco, estados e mensagens
    de erro custaram rodadas de auditoria nas DL-009, DL-017 e DL-024.

## 5. Como isto é verificado, e não só pedido

Regra sem mecanismo é só pedido — e este projeto já aprendeu isso três vezes.
A verificação é a varredura de interface descrita na
[DL-024](../planos/DL-024-identidade-visual-e-interface.md), que reprova a
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
- A régua de 15 linhas vale para **1280×800**. Em monitor maior o ganho é
  proporcional, e em telas menores a regra precisa ser revista com medição
  nova — não por estimativa.
