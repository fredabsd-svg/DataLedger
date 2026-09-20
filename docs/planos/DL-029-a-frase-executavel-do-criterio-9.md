# DL-029 — A frase executável do critério 9

**Demanda:** recomendação central da décima auditoria
([relatório integral](../auditorias/2026-09-20-dl-026-dl-028-rodada-10.md)),
registrada como **PE-56** e **BL-414**, decidida pelo Fred em 2026-09-20 com
uma frase: *"Você decide"*. A decisão está em **DE-059**.

**Responsável pelo produto:** Fred.
**Arquiteto:** `arquiteto-senior`.
**Fecha:** BL-404 (bloqueador), BL-405, BL-406, BL-407.
**Antecede:** a [DL-027](DL-027-documento-emitido-e-personalizacao.md), que
repete a identificação do escritório em cabeçalho e rodapé personalizáveis — e
que, sobre o instrumento de hoje, tornaria o BL-405 permanente.

## Objetivo

Escrever **uma vez** o critério 9 inteiro, como frase verificável, e fazer o
instrumento de medição ser julgado **por ela** — em vez de continuar corrigindo
achado a achado.

A frase, proposta pelo `auditor-qa` e **corrigida por ele mesmo em
2026-09-20, depois de medi-la** ([DE-061](../projeto/decisoes.md)):

> **A folha A4 exportada carrega, com tinta que contrasta com o papel,
> exatamente as linhas de identificação do escritório emitente que o servidor
> declarou, cada uma no seu próprio lugar; e — no conteúdo que o documento
> controla, isto é, tinta na folha e metadados do arquivo, excluída a faixa que
> o navegador acrescenta por fora e que nenhuma folha de estilo alcança
> (BL-332) — não carrega nenhum identificador do fornecedor do software, em
> qualquer caixa ou espaçamento.**

⚠️ **A fronteira nova não é afrouxamento.** A redação original prometia
*"nenhum identificador do fornecedor"*, e isso é **impossível**: exportando com
as opções padrão do diálogo de impressão, a faixa que o navegador acrescenta
carrega a **URL**, que em produção **é** o identificador do fornecedor — e o
`base.css` já declarava (BL-332) que nenhuma folha de estilo a suprime. Manter a
promessa seria **garantia inexistente descrita como imposta**, que é o defeito
de 2026-09-13.

## Por que isto, e não mais uma rodada

A décima auditoria mediu e disse, com franqueza, que **o retorno de mais uma
rodada da forma atual não paga**:

> *"O produto está certo em tudo que eu consegui medir, de novo, pela quarta
> rodada seguida; o que se poliu foi a **garantia**; e a garantia continua
> descrita por uma lista de achados em vez de por um enunciado do critério … se
> a rodada 11 for escrita contra os meus K1–K4, eu prevejo K12 na rodada 11."*

A causa que ele nomeia é de **régua**: a régua de cada rodada tem sido o
**relatório anterior**, não o **critério**. Por isso o achado sobe de nível a
cada vez e nunca acaba.

E em **2026-09-20**, numa tarde, a mesma lição apareceu **três vezes seguidas**,
nas três dentro de uma guarda escrita **para fechar a ocorrência anterior** —
BL-415, BL-416 e BL-418. Na terceira, a causa raiz apareceu e **já tinha sido
decidida**: era a [DE-057](../projeto/decisoes.md) outra vez, um nível abaixo.
Não é teoria; é o mesmo dia de trabalho.

## As cinco cláusulas, e o que cada uma fecha

A frase se decompõe em cinco perguntas mensuráveis. **Esta tabela é o contrato
da etapa** — o instrumento passa a ser julgado por ela, e cada achado aberto é
consequência de uma cláusula que não existia.

| # | Cláusula da frase | O que passa a ser medido | Fecha |
| --- | --- | --- | --- |
| C1 | *"A folha A4 exportada"* | **Toda** tela imprimível derivada, e **todas as páginas** do PDF — não a primeira por premissa não declarada | BL-406, BL-410 |
| C2 | *"com tinta que contrasta com o papel"* | Contraste entre a faixa da linha e o **fundo da própria folha**, na mesma rasterização — não um limiar fixo de luminância | BL-407 |
| C3 | *"exatamente as linhas … que o servidor declarou"* | Comparação de **conjuntos**: o esperado vem do servidor, e **faltar** ou **sobrar** linha reprova | (a fenda do "texto distinto" no BL-405) |
| C4 | *"cada uma no seu próprio lugar"* | Âncora por **ocorrência** na ordem de leitura, com o **número** de ocorrências conferido contra o número de elementos do timbre | BL-405 |
| C5 | *"não carrega nenhum identificador do fornecedor, em qualquer caixa ou espaçamento"* | Ausência **normalizada** (caixa, espaço, pontuação, separadores) sobre o texto de **todas** as páginas, com o identificador **derivado de onde o produto o escreve** | BL-404 |

### O limite que fica declarado, e não fechado

**Marca do fornecedor como DESENHO** — logotipo vetorial, `background-image`,
tipografia convertida em curvas — **não tem objeto de texto**, e nenhuma
cláusula desta etapa a alcança. Isso entra **no código**, no formato da
[DE-056](../projeto/decisoes.md), como limite declarado — e *limite declarado
não é limite fechado*. Fechá-lo exigiria comparação de imagem, que é outra
etapa e outra decisão.

## O que NÃO está no escopo

1. **Nenhuma mudança de produto.** `static/css/base.css` e `templates/**` não são
   tocados. Esta etapa mexe no **instrumento**, não no que sai impresso.
2. **Não se apaga o motor simulado.** Ele continua sendo a primeira linha
   barata, como a DE-057 já decidiu; a palavra final é do navegador.
3. **Não se fecha o lado do `pytest`** (código que nenhum teste exercita). É
   conversa de cobertura, é outra decisão, e está registrada à parte.

## Critérios de aceite

Cada um é uma **sabotagem que tem de reprovar**, medida no produto real, com o
código de saída e a mensagem conferidos — não inspeção de código.

1. **C5 / BL-404.** `Relatorio gerado por DATALEDGER - dataledger.com.br` no
   `balancete.html` faz o instrumento sair com código **não-zero**, nomeando a
   tela e o texto. Idem para `dataledger`, `Data Ledger`, `D a t a L e d g e r`
   e `dataledger.com.br`, em casos de teste **sem navegador**.
2. **C5 / derivação.** O identificador do fornecedor é **lido** de onde o produto
   o escreve. Trocar o nome no produto e **não** trocar no instrumento não pode
   produzir job verde.
3. **C4 / BL-405.** Com um rodapé repetindo a primeira linha do timbre, a
   medição daquela linha volta ao valor do **timbre** (~820 px), não ao do
   rodapé (384). E esconder o primeiro `<p>` do timbre, **com o rodapé
   presente**, sai com código não-zero.
4. **C3.** Duas linhas do timbre com o **mesmo texto**, escondendo uma delas,
   **reprova** — o caso que hoje colapsa porque as linhas são chaveadas por
   texto.
5. **C1 / BL-406.** Timbre injetado em `lancamento_detalhe.html` (rota que exige
   `lancamento_id`) **é medido**, ou o instrumento sai com código não-zero
   nomeando a rota. Aviso em job verde não atende.
6. **C1 / BL-410.** `margin-top: 260mm` no timbre produz mensagem que nomeia
   **paginação**, não *"0 pixels escuros"*.
7. **C2 / BL-407 — CORRIGIDO em 2026-09-20, e o erro era meu.** O texto original
   deste critério dizia *"`opacity: 0.4` — timbre legível — **passa**"*. Eu o
   copiei do K4 da auditoria, que afirma *"as três linhas perfeitamente
   legíveis"* — **juízo visual**, não medição, e eu o herdei sem medir.

   **Medido pelo `desenvolvedor-pleno` em 2026-09-20**, varredura de opacidade
   no produto real: `opacity: 0.4` produz razão de contraste de **2,81:1**,
   abaixo do piso do **WCAG 2.2** até para texto grande (3:1) e muito abaixo do
   piso para texto normal (4,5:1).

   **O critério passa a ser:** o piso de contraste é **derivado do WCAG 2.2** —
   4,5:1 para texto normal, 3:1 para texto grande ou negrito — e aplicado **por
   linha**, a partir do tamanho e peso **realmente renderizados**, que a sonda do
   navegador informa. Logo, **`opacity: 0.4` REPROVA**, e a mensagem tem de
   nomear *"contraste 2,81:1, abaixo do mínimo de 4,5:1 para texto normal"* —
   nunca *"0 pixels escuros"*.

   ⚠️ **O K4 não cai inteiro, e a precisão importa:** a docstring que afirmava
   *"nenhum pixel entre 1 e 254"* era **falsa** e continua sendo; a mensagem que
   culpava a ausência de tinta estava **errada** e continua. Cai **só** a
   terceira parte — *"reprovar `opacity: 0.4` é falso alarme"*.

   ⚠️ **O WCAG entra como EMPRÉSTIMO DECLARADO, não como norma.** Ele governa
   conteúdo **web**, não papel impresso, e **não é norma contábil**. É adotado
   como referência de legibilidade por **escolha nossa**, registrada no código
   com versão e data, na falta de piso específico para documento contábil — ver
   **PE-57**. Apresentá-lo como exigência normativa seria inventar exigência, o
   que o `AGENTS.md` proíbe.

   **Por que o número não é nosso, e isso é o ponto:** um limiar escolhido para
   fazer um caso passar é exatamente a forma que esta etapa combate — número que
   existe porque um teste precisava dele. Derivar de padrão publicado, versionado
   e citável é a mesma família da [DE-057](../projeto/decisoes.md): **perguntar a
   quem decide, em vez de inventar a régua**.
8. **Não regride o que já aguenta.** Continuam reprovando: tinta branca no
   timbre, `font-size: 1px`, `font-size: 3px`, e `display`/`color` na marca do
   fornecedor pela camada barata. Continua **passando** o controle limpo e a
   quebra de linha do timbre (`width: 90px`).
9. **Custo declarado e medido:** tempo do passo de medição antes e depois, no job
   real, não estimado.
10. **DE-058 em cada frase nova:** toda afirmação de medição escrita no código
    tem, ao lado, o teste que a reprova se deixar de valer — ou a marca
    explícita de **não medido**.

## Rodada 2 — o que a décima primeira auditoria REPROVOU

Relatório integral em
[2026-09-20-dl-029-rodada-11.md](../auditorias/2026-09-20-dl-029-rodada-11.md).
**C1, C4 e C5 fecham**, com limites declarados. **C2 e C3 não fecham.**

⚠️ **A régua desta rodada é a [DE-060](../projeto/decisoes.md), não a lista de
achados.** Os quatro achados altos têm **um** padrão atrás:

> **O instrumento mede um SUBSTITUTO mais fácil de obter que a propriedade, e o
> substituto não está declarado como substituto.**

| A propriedade | O substituto medido hoje | Diverge quando | Achado |
| --- | --- | --- | --- |
| Que tamanho a linha tem **no papel** | `getComputedStyle().fontSize` | `transform`, `zoom` | **BL-428** |
| Qual é a **razão de contraste do WCAG** | luminância de raster em **cinza** | a tinta não é cinza | **BL-429** |
| A linha **está no papel** | substring do `pdftotext -layout` | `letter-spacing` | **BL-430** |
| **Quantas** linhas o papel carrega | contagem de `<p>` do DOM | é a **mesma** consulta que alimenta a recusa de infraestrutura | **BL-427** |

⚠️ **Três das quatro correções usam dado que o instrumento JÁ CALCULA E
DESCARTA** — o `bbox` de cada linha, em pontos de PDF, do papel de verdade.
**Não é escopo novo: é parar de jogar fora a medida melhor.**

### Critérios de aceite da rodada 2

Todos são **sabotagem medida no produto real**, com **código de saída** e
**substring da mensagem** conferidos. Inspeção de código não atende.

11. **BL-427 / C3.** `{% for linha in timbre_linhas|slice:':2' %}` no Balancete
    — servidor declara três linhas, papel sai com duas — tem de sair com código
    **1**, nomeando *"número de linhas do timbre no papel (2) diverge do número
    declarado pelo servidor (3)"*. **Nunca** código 2, nunca *"falha de
    infraestrutura"*. A direção *"sobrar"* idem.
12. **BL-427 / recusa preservada.** `fonte_das_linhas is None` (subprocesso
    antigo, sonda que não rodou) **continua** saindo com código 2 — isso é
    infraestrutura de verdade, e a distinção é o achado.
13. **BL-428 / C2.** `transform: scale(0.6)` e `zoom: 0.6` saem com código
    **1**, nomeando **tamanho**, com o número medido **no papel**.
14. **BL-428 / mensagem.** `scale(0.45)`, `(0.35)` e `(0.25)` param de acusar
    *"poucos pixels"* e *"contraste insuficiente"* com tinta preto puro: a causa
    é **tamanho** e a mensagem diz isso.
15. **BL-429 / C2.** `color: #FF0000` no timbre sai com código **1**, relatando
    a razão **RGB do WCAG** — **ou** passa, com a mensagem e a docstring dizendo
    *"luminância monocromática do papel, não a razão RGB do WCAG"* e com o teste
    que compara as duas fórmulas. **A escolha entre (a) e (b) é minha, e depende
    da PE-59** — ver abaixo.
16. **BL-430 / C1-C3.** `letter-spacing: 0.2em` no timbre sai com código **0**.
    E `font-size: 4px` sai com código 1 nomeando **tamanho**, nunca ausência.
17. **BL-432.** Duas asserções guardam a premissa do BL-426:
    `print_background` fora do subprocesso e `print-color-adjust` fora do
    `base.css`, com mensagem mandando reler a docstring.
18. **BL-434 — e este é o que teria pego o BL-427.** Para **cada** cláusula da
    frase, **um** caso de aceite ponta a ponta que afirme o **código de saída** e
    a **substring da mensagem**. Hoje há 60 testes puros excelentes e **zero**
    desses.
19. **Nada regride.** Tudo que já reprovava continua reprovando, e tudo que já
    passava continua passando — incluindo as cinco grafias do fornecedor, o
    decoy do C4, a paginação, `lancamento_id`, `font-size: 8px` e o
    pseudo-elemento `::after`.
20. **DE-060 escrita.** Cada uma das cinco medições declara, no código, **se
    mede a propriedade ou um substituto** — e, quando for substituto, **de que
    ele diverge** e **a medição dessa divergência** ao lado.

### A decisão que o BL-429 exige, e ela é minha com insumo do Fred

A **PE-59** pergunta se o documento é pensado para impressão **monocromática**
ou **colorida**. As duas respostas se defendem, e o auditor foi explícito: *"o
problema não é escolher um dos dois; é que o instrumento não diz qual modela"*.

**Decido medir em COR**, e a razão é de risco, não de gosto: a medida em cor é a
**mais estrita** das duas e cobre os dois usos — o PDF na tela do cliente, onde a
cor existe, e a impressora monocromática, onde ela vira cinza e o critério só
fica mais folgado. Escolher o inverso aprovaria folha que o próprio piso adotado
reprova, que é o **BL-429** exatamente.

**A impressão monocromática fica declarada** como cenário mais permissivo, no
formato da DE-058. Se o Fred responder a PE-59 dizendo que o escritório imprime
só em preto e branco, a decisão se revisa — **mas o lado seguro não espera pela
resposta.**

## Riscos declarados

- **O contraste (C2) pode ficar frouxo demais.** Um limiar de contraste mal
  escolhido aceita cinza ilegível. Mitigação: o critério 8 exige que as
  sabotagens que hoje reprovam continuem reprovando, e a `opacity` do critério 7
  é o par de calibração. **Se os dois não puderem valer juntos, pare e traga a
  medição** — é decisão de produto, não de engenharia.
- **A derivação do identificador (C5) pode não ter fonte única hoje.** Se o nome
  do fornecedor estiver escrito em mais de um lugar no produto, isso é achado
  próprio: registre em vez de escolher um.
- **O custo pode subir.** Medir todas as páginas e o contraste custa mais que
  contar pixel escuro na folha 1. O critério 9 existe para isso aparecer.

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| DL-029 (esta etapa) | `desenvolvedor-pleno` | `scripts/medir_identificacao_do_emitente.py`, `scripts/test_medir_identificacao_do_emitente.py`, `scripts/semear_base_de_medicao.py` |
| BL-418 (em curso) | `desenvolvedor-pleno` | `scripts/test_decidir_caminhos_vigiados.py` |
| Documentação e integração | `arquiteto-senior` | `docs/**` |
| Auditoria | `auditor-qa` | Nada — audita a versão integrada |

**Proibido a todos nesta etapa:** `static/css/base.css` e `templates/**` — esta
etapa não muda o que sai impresso. Sabotagem só em cópia isolada (BL-311).

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`, como as etapas anteriores.
O PR cita este plano. A etapa **não** se declara fechada sem auditoria da versão
integrada, conforme a [DE-054](../projeto/decisoes.md).
