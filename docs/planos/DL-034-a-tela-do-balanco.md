# DL-034 — A tela do Balanço Patrimonial

**Demanda:** autorização do Fred em 2026-09-21 — *"pode seguir com a tela do
balanço"*.
**Depende de:** [DL-032](DL-032-a-camada-de-saldos.md) (entregue) e
[DL-033](DL-033-circulante-e-nao-circulante.md) — **as duas ENTREGUES**. O
contrato de `apurar_saldos` parou de se mover, e a implementação está
**liberada** (autorização do Fred em 2026-09-21).

## ⚠️ Nível de risco: 1, e NÃO 2 — a diferença é o tipo do documento

A tela do fechamento (DL-031) foi **nível 2** porque as regras moravam no
servidor e a tela só as acionava. **Aqui é diferente**, por três motivos que se
somam:

1. **É a primeira DEMONSTRAÇÃO CONTÁBIL que o produto emite.** Diário, Razão e
   Balancete são **conferência** ou **livro**; o Balanço é a **classe 2** da
   [personalizacao-de-relatorio.md](../projeto/personalizacao-de-relatorio.md),
   e essa classe tem **bloco de identificação prescrito por norma** (RC-95).
2. **A autorização no servidor NUNCA foi medida nesta cadeia.** O auditor da
   DL-032 registrou textualmente que o critério *"migra inteiro para a fatia
   2"*: nem `apurar_saldos` nem `apurar_balancete` verificam permissão, e nada
   media isso porque **não havia superfície**. Esta etapa cria a superfície.
3. **O documento vai à mão do cliente.** Erro aqui não é usabilidade: é papel
   errado arquivado.

## As três dívidas que esta etapa HERDA, e que não são novas

Estão declaradas em auditoria e em decisão. Nenhuma é surpresa; todas vencem
aqui.

| Dívida | Origem | O que esta etapa deve fazer |
| --- | --- | --- |
| **Autorização no servidor** | Auditoria DL-032, seção "o que não consegui medir" | A superfície nasce **com** verificação de permissão, e com teste que manda a requisição com papel errado e confere **403 e nada exposto** |
| **Leitura sem snapshot** | [DE-067](../projeto/decisoes.md) | *"A fatia 2 herda isto como requisito, não como sugestão"*: a leitura que gera **documento imprimível** roda sob snapshot, com o teste de corrida nascendo junto |
| **Emissão com declaração pendente** | **BL-488** | Qualquer lista de declaração não vazia — resíduo, tipo divergente, classificação aninhada, conta sem classificação — **impede a emissão** |

## ⚠️ O bloco de identificação é NORMA, não diagramação

**RC-95**, com texto literal em [requisitos.md](../projeto/requisitos.md): a
**NBC TG 26 (R5), item 51** exige, *"de forma destacada e repetida quando
necessário"*:

| Alínea | O que é | Temos? |
| --- | --- | --- |
| (a) | nome da entidade, e **qualquer alteração dessa identificação** desde o período anterior | Razão social, sim. A **alteração** depende do histórico cadastral (**BL-396**) |
| (b) | se são de entidade **individual ou de grupo** | ❌ **não existe** |
| (c) | a data de encerramento ou o período coberto | Sim |
| (d) | a **moeda de apresentação** | ❌ **não existe** |
| (e) | o **nível de arredondamento** usado | ❌ **não existe** — o RC-95 já registrava isso em 2026-09-19 |

E o **item 52** diz **como** se cumpre: *"pela apresentação apropriada de
cabeçalhos de página, títulos de demonstração, de nota, de coluna e similares
**em cada página**"*.

⚠️ **Consequência dura, e é o motivo de esta seção existir:** repetir o
cabeçalho entre as folhas deixa de ser capricho de diagramação e passa a ser **a
forma prescrita de cumprir a norma**. E a **PE-61** já mediu que hoje **só a
folha 1** traz empresa e período — as seguintes têm só cabeçalho de coluna.
**Para Balancete isso é ressalva; para o Balanço é descumprimento do item 52.**

**Três campos não existem.** Eles são **da entidade e da emissão**, não do
plano de contas, e entram nesta etapa como **valores declarados**, nunca
presumidos:

- **(b) individual ou consolidada** — o produto não consolida, então o valor é
  *individual*; **declarado, não deduzido**.
- **(d) moeda** — Real; a NBC ITG 2000 exige moeda nacional para escrituração
  (**RC-96**), então não há escolha a fazer hoje.
- **(e) nível de arredondamento** — o produto apresenta em **unidade de real,
  com centavos** (DE-010). **Declarar isso no documento é o cumprimento da
  alínea (e)**, e é barato porque a política já existe.

## O momento da verdade desta tela

> **"O que eu vou entregar fecha, e eu sei o que ele NÃO diz."**

O Balanço só sai quando a equação fecha **e** todas as declarações estão vazias.
Havendo pendência, a tela **não emite** — mostra o que falta, nomeado, e o
caminho para resolver.

⚠️ **É a lição das três últimas auditorias posta como regra de tela:** o
sistema errou três vezes seguidas **afirmando que tinha fechado**. Aqui ele não
vai poder afirmar: ou fecha e emite, ou não emite e diz por quê.

## Escopo

1. **Tela do Balanço** por empresa e data-base, com os grupos da lei:
   Ativo Circulante, Ativo Não Circulante (com os quatro subgrupos e subtotal),
   Passivo Circulante, Passivo Não Circulante e Patrimônio Líquido.
2. **Bloco de identificação do item 51, em cada página** — incluindo os três
   campos novos, declarados.
3. **Recusa de emissão** com qualquer declaração pendente.
4. **Autorização verificada no servidor**, na porta nova.
5. **Leitura sob snapshot** (DE-067).
6. Os **cinco estados**: vazio, carregando, erro, sucesso, sem permissão.

**Fora do escopo:** DRE, DMPL, DFC, notas explicativas, comparativo com o
exercício anterior, exportação em arquivo, e o histórico cadastral da alínea (a)
(**BL-396**), que fica **declarado como limite**.

## Critérios de aceite

1. ⚠️ **A CONDIÇÃO DE EMISSÃO, escrita por extenso em 2026-09-21, ANTES da
   primeira linha de código — e ela é conjunção, não um número só.**

   A redação anterior deste critério dizia *"o resíduo é zero — senão não
   emite"*. **Resíduo zero é necessário e NÃO é suficiente**, e a
   [reconferência da DL-033](../auditorias/2026-09-21-dl-033-rodada-2.md) mediu
   o contra-exemplo (**V1d**): dois defeitos no mesmo Ativo, **calibrados para
   se anularem** — retificadora entre irmãs (+500,00) e nó intermediário
   movimentado sem classificação (−500,00). Resultado: **resíduo `0,00`, as
   CINCO listas vazias, equação fechando** — e o **Ativo Circulante errado em
   R$ 500,00** e o **Imobilizado errado em R$ 500,00**. O total por tipo está
   certo; **os grupos que o Balanço imprime, não**.

   **O Balanço só é emitido quando TODAS valerem:**

   | # | Condição |
   | --- | --- |
   | 1 | `residuo_por_tipo` é **zero** em todos os tipos |
   | 2 | as **cinco** listas de declaração estão **vazias** |
   | 3 | **nenhum grupo tem nó topo-classificado irmão de natureza cadastrada divergente**, sob o mesmo ancestral não classificado |
   | 4 | **nenhum nó não-folha sem classificação própria nem ancestral tem movimento próprio** |

   ⚠️ **E a correção de FUNDO, que é a opção (b) do auditor e eu a adoto como
   preferida:** somar o nó classificado **normalizando o sinal pela natureza
   natural do TIPO** (devedora no Ativo, credora no Passivo), não pela natureza
   **cadastrada** da conta. Isso torna o número **certo** em vez de apenas
   detectado, e fecha a condição 3 de vez. ⚠️ **O próprio auditor declarou o
   limite da sugestão dele:** conferiu a aritmética à mão, **não implementou nem
   testou**, e pode haver interação com retificadora **de grupo** que ele não
   enxergou. **Implementar (b) e manter 3 e 4 como guarda** — cinto e suspensório
   enquanto (b) não tiver prova.

   **Teste obrigatório:** o cenário **V1d** do relatório, exigindo **recusa**; e
   **controle positivo** no cenário V1c (cinco classificações, retificadoras em
   dois grupos, centavos quebrados) exigindo **emissão** com resíduo `0,00`. Se
   a opção (b) for implementada, exigir também os números certos por grupo:
   `ativo_circulante == 2.750,00` e `ativo_nao_circulante == 8.500,00`.

   ⚠️ **A lição de método, que virou [DE-068](../projeto/decisoes.md):**
   **invariante mal dimensionada é mais perigosa que lista, porque parece
   completa.** Lista declara o que sabe e admite o que não sabe; identidade
   aritmética convida a acreditar que fechou tudo. **Enuncie a invariante E o
   escopo dela** — sobre qual agregação vale, e sobre qual não vale.
2. **Autorização no servidor**: papel sem permissão recebe **403** e **nenhum
   valor** aparece no corpo. ⚠️ **Asserte o corpo, não só o código** — é a
   lição do BL-211.
3. **Isolamento**: empresa de outro escritório devolve **404**, sem confirmar
   existência.
4. **O bloco do item 51 aparece em TODAS as folhas** do documento impresso —
   medido no **navegador real**, como a DL-028 já faz, não por inspeção de
   template.
5. **Os cinco grupos da lei somam o Ativo e o Passivo**, e o subtotal do não
   circulante soma os quatro subgrupos. ⚠️ **Derivado do mapa de grupos
   (BL-490), nunca por prefixo de string.**
6. **Precisão e apresentação**: algarismo tabulado medido (`111111` e `888888`
   com a mesma largura), contraste 4,5:1, **valor invertido entre parênteses**,
   cor nunca sozinha, nenhuma dependência externa.
7. **Leitura sob snapshot**, com teste de corrida que prove que o documento não
   sai com número de dois instantes diferentes.
8. **Sem regressão**, com os números declarados e conferidos por
   `--collect-only`.

## O CONTRATO entre as duas frentes, fixado por mim ANTES de começarem

⚠️ **Escrevo isto porque foi exatamente a ausência de um enunciado deste tipo
que produziu o bloqueador da DL-033.** As duas frentes correm em paralelo, em
arquivos disjuntos, e **precisam concordar sobre a forma antes de escrever
código** — senão uma delas testa contra a versão errada da outra.

`apurar_saldos` **já devolve**, e a forma **não muda** nesta etapa:
`totais_por_grupo` (chaveado por `GrupoDaLei`), `totais_por_classificacao`,
`residuo_por_tipo`, e as **cinco** listas de declaração.

⚠️ **O que MUDA de valor, e não de forma:** a correção **(b)** do critério 1
(normalizar o sinal pela natureza natural do tipo) altera **os números** de
`totais_por_classificacao` e `totais_por_grupo` em cenários com **retificadora
dentro de um grupo**. **Consequência direta para quem faz a tela: NÃO escreva
fixture de teste com conta retificadora dentro de um grupo** enquanto a frente
do servidor não entregar — use cenários limpos, ou você fixará por teste o
número que está sendo corrigido.

Três chaves **nascem** nesta etapa, na frente do servidor, e a tela as consome:
os campos do item 51 que não existem — **(b) individual ou de grupo**,
**(d) moeda** e **(e) nível de arredondamento**.

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Tela e impressão | `especialista-frontend` | `templates/contabilidade/**`, `static/css/**`, `views_web.py`, `urls_web.py`, testes de tela |
| Campos da entidade e snapshot | `desenvolvedor-pleno` | `apps/empresas/**`, `apps/contabilidade/services.py`, migrações |
| Documentação | `arquiteto-senior` | `docs/**` |

## Verificação

**Nível 1: auditoria independente da versão integrada**, com medição **no
navegador real** para o critério 4. Regra de parada da §3.1: uma auditoria, uma
correção, uma reconferência — **sem terceira**.

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
