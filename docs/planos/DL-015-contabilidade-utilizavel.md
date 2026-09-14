# DL-015 — Contabilidade utilizável: saídas com período e conferência

**Estado:** **onda 1 encerrada em 2026-09-14, aprovada com ressalvas.**
Quatro rodadas de auditoria: reprovada em [1](../auditorias/2026-09-13-dl-015-rodada-1.md),
[2](../auditorias/2026-09-14-dl-015-rodada-2.md) e
[3](../auditorias/2026-09-14-dl-015-rodada-3.md); aprovada com ressalvas em
[4](../auditorias/2026-09-14-dl-015-rodada-4.md), sobre a revisão `7bf6dae`.
Ressalvas convertidas em BL-83 a BL-86. **Onda 2 (interface, BL-62) não
iniciada.**

## Por que esta etapa existe

O Fred determinou em 2026-09-13 (RC-50) que a prioridade passa a ser a
Contabilidade, a partir do manual de referência. O levantamento resultante está
em [mapa-funcional-contabil.md](../projeto/mapa-funcional-contabil.md).

O cruzamento com o código revelou o desconforto central: o núcleo contábil está
**correto e auditado** — partidas dobradas, imutabilidade, estorno rastreável,
idempotência, precisão decimal, isolamento entre empresas — mas as saídas não
servem para o trabalho real:

- Razão e Balancete **não aceitam período**. Devolvem o acumulado desde o
  primeiro lançamento. Nenhum contador emite balancete "de sempre".
- O Balancete tem **uma coluna**. Um balancete de verificação tem quatro: saldo
  anterior, débitos do período, créditos do período, saldo final.
- O Balancete lista só contas analíticas; não totaliza os grupos.
- **Não existe Diário** como livro: há a listagem cronológica da API.
- Nada varre a base procurando **lote desbalanceado** gravado por caminho que
  não passe pelo serviço.

## Objetivo

Entregar as saídas contábeis que permitem **conferir o sistema contra a
realidade**: Diário, Razão e Balancete por período, conciliáveis entre si, mais
a conferência de lotes desbalanceados.

## Escopo

**Onda 1 — backend (esta delegação):** BL-59, BL-60, BL-61, BL-64.
**Onda 2 — interface (depois, com o contrato já estável):** BL-62.

Fora do escopo desta etapa, registrado para não haver dúvida: competência e
fechamento de período (BL-15, BL-11, dependem de PE-05), saldo inicial de
implantação (BL-63, depende de PE-27), rascunho e efetivação (BL-10), centro de
custo, plano referencial, Balanço, DRE e demais demonstrações.

## Decisão de contrato: o período é obrigatório

Hoje `GET /razao/<conta>/` e `GET /balancete/` respondem sem parâmetro. Passam a
**exigir** `inicio` e `fim`. Quebra de contrato deliberada, registrada como
DE-016: o sistema não está implantado, não há cliente consumindo a API, e uma
saída contábil sem período é uma resposta errada com aparência de certa. É mais
barato quebrar agora do que conviver com o padrão errado.

## Contrato das quatro saídas

Prefixo existente: `/api/contabilidade/empresas/<empresa_id>/`.
Todas exigem `inicio` e `fim` no formato `AAAA-MM-DD`, com `inicio <= fim`.
Todos os valores monetários são **string** com duas casas decimais, como já faz
`_como_moeda` — nunca `float`.

### 1. Diário — `GET diario/?inicio=&fim=`

```json
{
  "inicio": "2026-01-01",
  "fim": "2026-01-31",
  "lancamentos": [
    {
      "id": 12,
      "data": "2026-01-05",
      "historico": "Venda à vista",
      "total_debito": "1000.00",
      "total_credito": "1000.00",
      "itens": [
        {"conta": "1.1.1.01", "nome": "Caixa", "tipo": "debito", "valor": "1000.00"}
      ]
    }
  ],
  "total_debito": "1000.00",
  "total_credito": "1000.00"
}
```

Ordenação cronológica estável: `data`, depois `criado_em`, depois `id`.

### 2. Razão — `GET razao/<conta_id>/?inicio=&fim=`

```json
{
  "conta": "1.1.1.01",
  "nome": "Caixa",
  "inicio": "2026-01-01",
  "fim": "2026-01-31",
  "saldo_anterior": "500.00",
  "total_debito": "1000.00",
  "total_credito": "300.00",
  "saldo_final": "1200.00",
  "itens": [
    {
      "lancamento_id": 12,
      "data": "2026-01-05",
      "historico": "Venda à vista",
      "tipo": "debito",
      "valor": "1000.00",
      "saldo": "1500.00"
    }
  ]
}
```

`saldo_anterior` é o saldo apurado com **todos** os itens de data anterior a
`inicio`, respeitando a natureza da conta. A coluna `saldo` acumula a partir do
saldo anterior — não de zero.

### 3. Balancete — `GET balancete/?inicio=&fim=&nivel=`

`nivel` é opcional. Ausente, devolve todas as contas, analíticas e sintéticas.
Presente, devolve as contas até aquele nível de hierarquia (raiz = nível 1),
com as sintéticas totalizando as filhas.

```json
{
  "inicio": "2026-01-01",
  "fim": "2026-01-31",
  "contas": [
    {
      "conta": "1.1.1.01",
      "nome": "Caixa",
      "nivel": 4,
      "analitica": true,
      "saldo_anterior": "500.00",
      "debitos": "1000.00",
      "creditos": "300.00",
      "saldo_final": "1200.00"
    }
  ],
  "total_debitos": "1000.00",
  "total_creditos": "1000.00"
}
```

`total_debitos` e `total_creditos` somam **apenas as contas analíticas**, para
não contar o mesmo valor duas vezes através das sintéticas. Os dois têm de ser
iguais: é a partida dobrada aparecendo na saída.

### 4. Conferência — `GET conferencia/lotes-desbalanceados/`

Sem período: uma base torta é torta em qualquer recorte.

```json
{
  "lotes": [
    {"id": 77, "data": "2026-01-09", "historico": "Ajuste",
     "total_debito": "100.00", "total_credito": "90.00", "diferenca": "10.00"}
  ]
}
```

Lista vazia é o resultado esperado numa base sadia.

## Critérios de aceite

Numerados para a auditoria conferir um a um.

1. As quatro rotas existem, exigem escritório ativo e respeitam o isolamento
   entre empresas: pedir dados de empresa de outro escritório devolve 404 ou 403,
   nunca dado.
2. `inicio` ou `fim` ausente, malformado, ou `inicio > fim`, devolve **400** com
   mensagem útil — nunca 500 nem resposta silenciosa com período implícito.
3. O Razão apura `saldo_anterior` a partir dos lançamentos anteriores a `inicio`,
   e a coluna `saldo` parte dele.
4. No Balancete, para cada conta analítica:
   `saldo_final = saldo_anterior ± (debitos − creditos)`, conforme a natureza.
5. No Balancete, `total_debitos == total_creditos` para qualquer período.
6. **Conciliação Razão × Balancete:** para a mesma conta e período, os quatro
   valores do Balancete são iguais aos do Razão. Teste explícito.
7. **Conciliação Diário × Balancete:** o `total_debito` do Diário do período é
   igual ao `total_debitos` do Balancete do mesmo período. Teste explícito.
8. Conta sintética no Balancete soma exatamente as analíticas subordinadas, em
   hierarquia de pelo menos três níveis. Teste explícito.
9. A conferência encontra um lote desbalanceado gravado por caminho que **não**
   passa pelo serviço (o teste deve criar o lote torto deliberadamente, via ORM,
   já que `criar_lancamento` corretamente o impediria).
10. Um lançamento com data fora do intervalo não aparece em nenhuma das três
    saídas, e não entra em nenhum total. Teste de borda **inclusiva** nos dois
    extremos: lançamento exatamente em `inicio` e exatamente em `fim` **entram**.
11. Estorno aparece nas saídas como lançamento próprio, na data dele; o par
    original + estorno resulta em saldo zero no período que contém os dois.
12. Sem N+1: o Balancete não pode fazer duas consultas por conta, como faz hoje.
    Medir com `django_assert_num_queries` ou equivalente e fixar um teto.
13. Valores sempre como string decimal com duas casas; nenhum `float` na
    resposta. Teste que inspeciona o JSON cru.
14. Suíte, `ruff check`, `ruff format --check`, `manage.py check` e migrações em
    banco vazio limpos. Nenhuma regressão nos 92 testes de contabilidade.

## Validação

- `pytest apps/contabilidade` e suíte completa.
- Auditoria independente pelo `auditor-qa` na versão integrada, com teste de
  mutação: espera-se que mutar o sinal da natureza, o limite do intervalo e a
  soma das sintéticas mate testes.

## Impacto e reversão

Sem migração de banco: as quatro saídas são de leitura. O risco está na quebra
de contrato deliberada (DE-016) e na aritmética de saldos. Reverter o commit
restaura o comportamento anterior.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` (onda 1) | `apps/contabilidade/views.py`, `services.py`, `serializers.py`, `urls.py`, `apps/contabilidade/tests/**` |
| `especialista-frontend` (onda 2) | `templates/contabilidade/**`, `apps/contabilidade/views_web.py`, `urls_web.py`, `static/**` |
| `arquiteto-senior` | documentação, integração e costura entre as ondas |

Ninguém edita o arquivo de outro. A onda 2 só começa com o contrato da onda 1
integrado e auditado.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`
- **Branch de destino:** `main`
