# DL-032 — A camada de saldos

**Demanda:** autorização do Fred em 2026-09-20 — *"pode seguir com a camada de
saldos"*, depois de ler o
[cruzamento do catálogo de 120 relatórios](../projeto/catalogo-de-relatorios.md).
**Nível de risco: 1** (§3.1 do [AGENTS.md](../../AGENTS.md)) — é o elo de que
Balanço, DRE e DMPL vão derivar. Erro aqui vira documento errado na mão do
cliente.

## Por que esta etapa, e por que agora

O catálogo mostrou que os 120 relatórios saem de **uma** cadeia, e que o
DataLedger tem os três primeiros elos e não tem o quarto:

> transações → lançamentos e plano de contas → Diário e Razão → **saldos e
> conciliações** → demonstrações e indicadores

**Enquanto esse elo não existir, cada demonstração custa o preço cheio.** Depois
dele, Balanço, DRE, DMPL, DLPA, análise vertical e horizontal viram **consulta e
leiaute** — não módulos.

## ⚠️ A decisão de arquitetura, e ela é minha: NÃO MATERIALIZAR

**A camada de saldos é um CONTRATO DE DERIVAÇÃO, não uma tabela.** Nada de
`SaldoConta` gravado no banco nesta etapa.

**O motivo é o defeito mais caro que um sistema contábil pode ter:** uma tabela
de saldos que **diverge** dos lançamentos. Ela não avisa quando diverge — ela
simplesmente passa a contar outra história, e a divergência só aparece quando um
cliente confronta o papel com o extrato. É a mesma classe da **DE-019** (*"dois
campos poderiam discordar, e a partir daí Diário e Balancete contariam histórias
diferentes"*), e viola a exigência do projeto de que **relatório e saldo sejam
conciliáveis com os lançamentos de origem** (RC-19).

⚠️ **Se um dia o desempenho exigir materialização, isso é uma decisão PRÓPRIA**,
com um verificador que compare o valor gravado com o derivado e **reprove** na
divergência. Cache sem verificador é a tabela que mente.

**Consequência prática:** a camada **reusa o motor do Balancete**, que já resolve
a parte difícil — a regra única de saldo da **DE-020** (o saldo de qualquer conta
é o movimento próprio **mais** o das descendentes, com a natureza aplicada uma
única vez, no fim). Reimplementar isso seria criar a segunda fonte pela porta dos
fundos.

## O momento da verdade desta camada

> **"O que eu somei fecha, e quando não fecha eu DIGO — nunca conserto."**

Vem do próprio catálogo, item 1, e é a frase que eu quero no código:

> *"saldos contábeis **não devem ser alterados apenas para fechar a equação**."*

## A equação, e a forma dela que é honesta o ano inteiro

Balanço fecha com **Ativo = Passivo + Patrimônio Líquido**. Mas isso só vale
**depois** do encerramento do exercício, quando o resultado foi transferido ao
PL por lançamentos (catálogo, item 25). **Durante o ano, o resultado ainda está
nas contas de receita e despesa**, e a equação ingênua não fecha — sem que haja
erro nenhum.

**A forma que vale nos dois estados, e é a que a camada expõe:**

```
Ativo = Passivo + Patrimônio Líquido + (Receita − Despesa)
```

O termo `(Receita − Despesa)` é o **resultado ainda não transferido**. Depois do
encerramento ele é zero por construção, e a equação se reduz à clássica.

⚠️ **Isto NÃO é invenção minha e NÃO é norma que eu esteja citando:** é a
consequência aritmética de o encerramento ser feito por lançamento, que é o que
o catálogo descreve no item 25. **A obrigatoriedade, a periodicidade e a conta
que recebe o resultado são matéria do Fred** — viram a **PE-62** abaixo.

`TipoConta` já existe no modelo com os cinco grupos (`ativo`, `passivo`,
`patrimonio_liquido`, `receita`, `despesa`), então a agregação é derivável
**hoje**, sem campo novo.

## Escopo da fatia 1

1. **`apurar_saldos(*, empresa, data_base)`** — saldo de **cada** conta na data,
   com código, nome, tipo, natureza e nível, reusando o motor do Balancete.
2. **Agregação por `TipoConta`** — os cinco totais.
3. **A equação, com a diferença DECLARADA** quando não fecha. Nunca ajustada,
   nunca escondida, nunca arredondada para fechar.
4. **Conciliação provada com o Balancete** — mesmo período, mesmos números, por
   teste, não por afirmação.
5. **Saldo de abertura**: a camada trata `data_base` anterior a qualquer
   lançamento devolvendo zeros, não erro.

**Fora do escopo, e não deve aparecer no diff:** tela de Balanço ou DRE,
encerramento de exercício, classificação circulante / não circulante,
comparativo entre períodos, exportação, indicadores.

## Critérios de aceite

1. **`apurar_saldos` e `apurar_balancete` NUNCA discordam.** Teste que, para o
   mesmo período e a mesma empresa, compara conta a conta e **reprova na
   primeira divergência de centavo**. ⚠️ **Este é o critério que justifica a
   etapa inteira** — se as duas fontes puderem divergir, não construímos uma
   camada, construímos um segundo problema.
2. **A equação é reportada, nunca forçada.** Havendo diferença, a resposta a
   carrega **com valor e sinal**, e nenhum saldo é alterado. Teste com base
   deliberadamente torta: a diferença aparece, os saldos ficam intactos.
3. **Precisão exata**: `Decimal`, escala e arredondamento explícitos, nunca
   ponto flutuante binário. Teste com valores que quebram `float`.
4. **Os cinco tipos somam o universo**: nenhuma conta fica fora da agregação.
   Teste derivado — anda pelos `TipoConta` do modelo e **reprova** se um tipo
   novo aparecer sem tratamento. ⚠️ **Derivado, não enumerado** (DE-056).
5. **Isolamento**: saldo de uma empresa nunca inclui lançamento de outra, nem de
   outro escritório. Teste com duas empresas de escritórios diferentes.
6. **Leitura pura**: `apurar_saldos` **não grava nada** — nem saldo, nem cache,
   nem trilha. Competência encerrada ou entregue **não muda** o resultado.
   Teste que confere a contagem de escritas antes e depois.
7. **Data futura e data absurda** são tratadas como o resto do produto: sem
   erro cru, com o comportamento declarado.
8. **Sem regressão**: suíte, `ruff check`, `ruff format --check`,
   `manage.py check`, `makemigrations --check --dry-run` (**exit 0**, e **sem
   migração nova** — esta etapa não mexe em modelo).

## Riscos declarados

- **Desempenho.** O motor do Balancete percorre a hierarquia recursivamente.
  Medir o custo de `apurar_saldos` num plano de contas realista e **declarar o
  número**. Se for proibitivo, **parar e avisar** antes de entregar — não
  materializar por conta própria.
- **Conta sem tipo coerente com a natureza.** Contas retificadoras são
  deliberadas (o modelo permite). A camada **não** deve "corrigir" natureza:
  soma o que está lá e deixa a classificação para quem classificou.

## O que esta etapa NÃO resolve, e é preciso dizer antes

1. **Não faz Balanço.** Para apresentar um BP é preciso **circulante × não
   circulante**, e esse campo **não existe** no modelo. Vira fatia própria.
2. **Não faz encerramento de exercício** (catálogo, item 25). Depende da PE-62.
3. **Não faz DRE**, que precisa da estrutura de receita bruta, deduções, custos
   e despesas — outra classificação que o modelo ainda não tem.

## Pendência aberta com o Fred

**PE-62 — o encerramento do exercício no escritório dele.** Três perguntas, e
**não bloqueiam a fatia 1**:

1. O escritório faz o encerramento por **lançamentos de encerramento**, como o
   catálogo descreve, ou trabalha com o resultado derivado?
2. Com que **periodicidade** — anual, ou também mensal para fins gerenciais?
3. Qual **conta do PL** recebe o resultado?

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Camada de saldos | `desenvolvedor-pleno` | `apps/contabilidade/services.py`, testes correspondentes |
| Ressalvas abertas | `especialista-frontend` | **BL-471** e **BL-472**, em `apps/contabilidade/tests/test_dl031_*.py` |
| Documentação | `arquiteto-senior` | `docs/**` |

**Proibido a ambos:** migração de banco (esta etapa não mexe em modelo),
`templates/**` e `static/**`.

## Verificação

**Nível 1: auditoria independente da versão integrada**, por quem não escreveu.
Regra de parada da §3.1: uma auditoria, uma correção, uma reconferência — **sem
terceira**.

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
