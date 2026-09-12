# DL-007 — Correção dos bloqueadores de contabilidade

Plano da etapa que corrige os dois achados **bloqueadores** registrados em
[docs/auditorias/2026-09-11-diagnostico-inicial.md](../auditorias/2026-09-11-diagnostico-inicial.md),
itens BL-40, BL-41 e BL-42 do [backlog](../projeto/backlog.md).

Autorizado pelo Fred em 2026-09-12.

**Estado:** em validação — implementado e revisado pelo `arquiteto-senior`,
aguardando auditoria independente.

## Histórico de revisão do arquiteto

A primeira entrega do `desenvolvedor-pleno` foi **devolvida**, com dois defeitos
e uma decisão de contrato pendente:

1. **`validate_conta_pai` falhava aberto.** A condição exigia
   `empresa is not None` para validar; com o contexto ausente, a validação era
   silenciosamente ignorada e o vazamento entre empresas voltava. Em controle de
   isolamento, a falha tem de ser **fechada**: na dúvida, recusa. Corrigido, com
   teste que instancia o serializer sem empresa no contexto e prova a recusa.
2. **A trilha de auditoria afirmava criação que não ocorreu.** Numa repetição
   idempotente nada é gravado, mas a ação registrada continuava
   `lancamento.criado`. Isso grava fato falso na peça que deveria servir de
   prova, contra o AGENTS.md §11, que exige registrar operação **e resultado**.
   Corrigido: repetição gera a ação distinta `lancamento.criacao_repetida`,
   rastreável e referenciando o mesmo lançamento. O registro **não** foi
   suprimido — saber que houve repetição é informação útil.
3. **Contrato decidido pelo arquiteto:** `201` apenas na criação real, `200` na
   repetição. `201 Created` é afirmação de fato; na repetição o sistema não
   criou nada. Além de ser mais honesto, torna duplo clique observável.

## Objetivo

Fechar dois caminhos que permitem corromper dados contábeis:

1. Criar conta cujo pai pertence a **outra empresa**, atravessando a fronteira
   de isolamento (RC-18).
2. **Estornar o mesmo lançamento mais de uma vez**, e repetir a criação de
   lançamento sem proteção contra duplicidade (RC-14, RC-15).

## Escopo delimitado

**Dentro do escopo:** apenas o app `apps/contabilidade`, mais a migração
correspondente e os testes.

**Fora do escopo, e registrado como tal:** os achados 3 a 10 da auditoria
(gravidades alta, média e baixa). Em especial o **achado 4** — validadores de
sinal e escala que não executam na gravação — permanece aberto como BL-17.
Ele é real e precisa de correção, mas depende da política de arredondamento que
o Fred ainda vai definir (PE-02), e não será resolvido por suposição.

## Causa raiz comum (BL-42)

Os dois bloqueadores têm a mesma origem: **o Django REST Framework não executa
`full_clean()`**. Portanto `Model.clean()` e os validadores de campo **não
rodam** no caminho da API, e também não rodam em `Model.objects.create()`.

Toda regra escrita apenas em `Model.clean()` é decorativa fora do Django admin
e dos formulários.

### Decisão de arquitetura

Registrada como **DE-008** em [decisoes.md](../projeto/decisoes.md). Toda
invariante contábil deve ser imposta em **pelo menos um** destes lugares, em
ordem de preferência:

1. **Restrição de banco** — a mais forte, sobrevive a shell, ORM e corrida.
2. **Camada de serviço** (`services.py`) — para regra que envolve várias linhas
   ou precisa de bloqueio transacional.
3. **Serializer** — na fronteira da API, para validar o que o cliente enviou.

`Model.clean()` continua existindo, porém **apenas como conveniência para o
admin**, nunca como única defesa.

Por que a regra de `conta_pai` não vira restrição de banco: a condição compara
`conta_pai.empresa_id` com `self.empresa_id`, ou seja, atravessa linhas. Um
`CheckConstraint` do PostgreSQL não expressa isso sem gatilho. Fica na camada 3
(serializer), e o `clean()` é mantido para o admin.

## Entregáveis

| Item | Arquivo |
| --- | --- |
| Validação de `conta_pai` na fronteira da API | `apps/contabilidade/serializers.py` |
| Empresa disponível no contexto do serializer | `apps/contabilidade/views.py` |
| Restrição de estorno único e chave de idempotência | `apps/contabilidade/models.py` |
| Bloqueio transacional e checagem explícita no estorno | `apps/contabilidade/services.py` |
| Migração correspondente | `apps/contabilidade/migrations/0002_*.py` |
| Testes | `apps/contabilidade/tests/` |

**Dependências:** nenhuma. A `main` já contém DL-002 a DL-006.

## Critérios de aceite observáveis

### BL-40 — isolamento de `conta_pai`

1. `POST /contabilidade/empresas/<A>/contas/` com `conta_pai` de uma conta da
   empresa B retorna **400**, e nenhuma conta é criada.
2. Vale mesmo quando A e B pertencem ao **mesmo escritório** — a fronteira é a
   empresa, não só o escritório.
3. `conta_pai` da própria empresa continua funcionando (não houve regressão).
4. `conta_pai` nulo continua aceito.

### BL-41 — estorno único e idempotência

5. Estornar o mesmo lançamento **duas vezes** retorna **400** na segunda
   tentativa, e existe exatamente **um** estorno.
6. A proteção resiste a **corrida**: duas execuções concorrentes produzem um
   único estorno, garantido por restrição de banco, não só por checagem prévia.
7. Estornar um estorno continua sendo recusado (não houve regressão).
8. `POST` de lançamento com o cabeçalho `Idempotency-Key` repetido, na mesma
   empresa, **não cria segundo lançamento**: devolve o lançamento original.
9. A mesma chave em **empresas diferentes** não colide.
10. `POST` **sem** o cabeçalho continua funcionando como hoje, criando o
    lançamento. O contrato permanece compatível.

### Regressão

11. Os 55 testes existentes continuam passando.
12. `ruff check .`, `ruff format --check .`, `manage.py check` e
    `manage.py migrate` em banco vazio aprovados.

## Decisão de produto registrada: por que uma chave, e não dedução automática

**Não** vamos deduzir duplicidade por chave natural (empresa + data +
histórico + itens). Em contabilidade, **dois lançamentos idênticos no mesmo dia
podem ser absolutamente legítimos** — duas taxas iguais, dois recebimentos de
mesmo valor, dois honorários de mesmo contrato. Deduzir duplicidade por
semelhança recusaria lançamento verdadeiro e corromperia a escrituração por
omissão, que é pior que o duplicado, porque não aparece na conciliação.

Portanto a idempotência é **explícita e opcional**: o cliente envia
`Idempotency-Key` quando quer garantia de não duplicar em caso de repetição de
rede ou duplo clique. Isso é aditivo e não quebra nenhum cliente atual.

**Pendência decorrente:** a interface deverá passar a enviar essa chave nos
formulários de lançamento. Registrado no backlog; não faz parte desta etapa,
porque não existe tela de lançamento ainda.

## Cenários de teste

| Cenário | Esperado |
| --- | --- |
| `conta_pai` de outra empresa, mesmo escritório | 400, nada criado |
| `conta_pai` de outra empresa, outro escritório | 400 ou 404, nada criado |
| `conta_pai` da mesma empresa | 201 |
| `conta_pai` ausente ou nulo | 201 |
| Segundo estorno do mesmo lançamento | 400, um único estorno |
| Estorno concorrente (constraint) | `IntegrityError` contido, um único estorno |
| Estorno de estorno | 400 |
| Mesma `Idempotency-Key` duas vezes | um lançamento, segunda resposta devolve o mesmo |
| Mesma chave em duas empresas | dois lançamentos, sem colisão |
| Sem `Idempotency-Key` | 201, comportamento atual |

## Impacto

- **Segurança e dados:** fecha um vazamento entre empresas e um caminho de
  corrupção de saldo. É o objetivo da etapa.
- **Cálculos:** nenhum cálculo muda. O estorno duplicado é justamente o que
  distorcia saldo e balancete.
- **Contratos:** **compatível**. A validação nova recusa o que já era inválido;
  o cabeçalho de idempotência é opcional.
- **Desempenho:** desprezível. Uma restrição de unicidade e um `SELECT FOR
  UPDATE` por estorno.
- **Migração:** acrescenta restrição de unicidade e um campo opcional. Não
  altera dado existente.

## Detecção prévia antes de aplicar a migração em base real (achado A9)

A migração cria um índice único sobre `estorno_de`. Se a base já contiver
**estornos duplicados**, ela falha — e isso é o comportamento desejado, não um
problema a contornar. O auditor verificou que a falha é **limpa e atômica**: a
coluna não é criada e a migração não é marcada como aplicada.

Antes de aplicar em base com dados reais, **rode esta consulta** e trate o que
ela devolver:

```sql
SELECT estorno_de_id, COUNT(*) AS estornos
FROM contabilidade_lancamentocontabil
WHERE estorno_de_id IS NOT NULL
GROUP BY estorno_de_id
HAVING COUNT(*) > 1;
```

Nenhuma linha devolvida significa que a migração pode ser aplicada. Consulta
conferida contra o banco de desenvolvimento em 2026-09-12; devolveu zero linhas.

Se houver linhas, **pare**: são lançamentos reais estornados mais de uma vez, e
os saldos dessas empresas já estão distorcidos. É caso de análise contábil,
não de decisão técnica — o tratamento (qual estorno preservar, qual ajustar)
precisa de aprovação do responsável. **Nunca remova a restrição para a migração
passar.**

Nota de operação, também do achado A9: o `CREATE UNIQUE INDEX` é emitido sem
`CONCURRENTLY` e portanto toma `ACCESS EXCLUSIVE` na tabela durante a
aplicação. Com o volume atual isso é irrelevante; quando houver base grande em
produção, avaliar criação concorrente em migração própria.

## Reversão

A migração é reversível (`migrate contabilidade 0001`). Como só acrescenta
restrição e campo anulável, a reversão não perde dado. Se a restrição de estorno
único falhar ao aplicar, é sinal de que **já existem estornos duplicados em
base real** — nesse caso, parar e tratar os dados antes de prosseguir, nunca
remover a restrição para "passar".

## Branch

Trabalho e destino: `claude/accounting-agent-team-setup-mn6lyf`.

## Divisão de responsabilidade

| Agente | Responsabilidade | Arquivos |
| --- | --- | --- |
| `arquiteto-senior` | Requisitos, critérios, decisão DE-008, integração, este plano | `docs/` |
| `desenvolvedor-pleno` | Implementação e testes | `apps/contabilidade/**` |
| `auditor-qa` | Verificação independente da versão integrada | nenhum (somente leitura) |

Nenhum arquivo é editado por dois agentes ao mesmo tempo.

## Evidências

A registrar ao concluir: saída real de `ruff check`, `ruff format --check`,
`manage.py check`, `manage.py migrate` e `pytest`, além do parecer do
`auditor-qa`.
