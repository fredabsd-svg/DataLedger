# DL-023 — Integridade administrativa: nenhuma regra vale só na porta pela qual foi escrita

**Estado:** **em execução.** Aberta em 2026-09-16, a partir da `main` em
`24f6bbc` (PR #23 integrado — DL-022).

**Origem:** pacote 2 da fila de execução do
[plano mestre](../projeto/plano-mestre.md), aprovada pelo Fred em 2026-09-16
(**RC-88**). Vem antes de qualquer módulo novo.

## Por que esta etapa é a primeira de código

Os dois itens que ela fecha são **bloqueadores de implantação**: não é aceitável
existir dado real de cliente num sistema onde eles são possíveis.

| Item | O que está medido hoje | Efeito |
| --- | --- | --- |
| **BL-83** | `ContaAdmin` permite mover conta **com movimento** para outra empresa e trocar a **natureza** de conta já movimentada | O balancete da empresa de origem passa a mostrar **zero de débito contra mil de crédito** enquanto o Diário continua fechando, e **nenhuma** das quatro categorias da conferência acusa. Trocar a natureza **inverte o sinal de todo o histórico** da conta |
| **BL-211 / A3** | `EmpresaAdmin` permite mover uma **empresa inteira** de escritório com um POST — medido: `302`, `escritorio agora: 4 \| era: 3` | Leva junto plano de contas, escrituração e estabelecimentos, **sem `RegistroAuditoria`**. O escritório de origem perde a carteira sem nada acusar; o de destino passa a ver contabilidade de cliente que nunca foi dele |
| **BL-211 / A2** | O inline de regime tributário grava sem passar pelo serviço — medido: `302` e `periodos ABERTOS simultaneos: 2` | O regime tributário governa a apuração fiscal. Com dois períodos abertos, e sem desempate entre períodos de mesmo início, o "último regime" — justamente o que o **RC-86/DE-039** autoriza apagar — **deixa de ser único** |
| **BL-211 / classe** | A superfície do admin **nunca foi varrida** contra as regras de negócio | Dois achados independentes na mesma superfície significam que a superfície não foi varrida, e não que existam dois defeitos isolados |

**Precisão herdada da DL-022, para não corrigir a coisa errada:** o histórico de
regime **tem** ordenação (`HistoricoRegimeTributario.Meta.ordering =
["-vigencia_inicio"]`). O defeito confirmado é **sobreposição de períodos** e
**falta de desempate** para inícios iguais — não ausência de ordenação. E o
admin de lançamentos **já recusa** inclusão, alteração e exclusão: não há
terceiro caso de lançamento arbitrário, e afirmar que havia foi erro do
`arquiteto-senior`, registrado na BL-211.

## A classe do problema, não os casos

> **A classe é:** nenhuma regra de negócio vale apenas na porta pela qual ela
> foi escrita, e nenhuma alteração de dado estruturante acontece sem trilha.

Os três casos acima são **exemplos**. O que a etapa precisa entregar é a
propriedade: regra que o admin tem de respeitar mora no **modelo** (validador,
`clean()` ou restrição de banco), não só no serviço — porque o serviço defende
uma porta, e o modelo defende todas, inclusive ORM direto, `shell`, importação
e tarefa em segundo plano.

## Objetivo

1. Fechar **BL-83** e os dois casos vivos da **BL-211** (A2 e A3), com a defesa
   no modelo e não só no admin.
2. Varrer a superfície inteira do admin contra as regras de domínio, com
   inventário verificável de **cada** `ModelAdmin` e `Inline` registrado.
3. Provar cada defesa por **requisição autenticada ao admin** — nunca por
   `full_clean()` verde, que não prova que o admin chama `full_clean()`.

## Requisitos

### Confirmados

| # | Requisito | Origem |
| --- | --- | --- |
| 1 | Conta **com movimento ou com filhas** não muda de empresa. | BL-83 |
| 2 | Conta **com movimento** não muda de natureza nem de tipo. | BL-83 |
| 3 | Empresa **com escrituração** (plano de contas, lançamento ou estabelecimento) não muda de escritório pelo uso cotidiano. | BL-211/A3 |
| 4 | Uma empresa tem, no máximo, **um** período de regime tributário aberto. | BL-211/A2 |
| 5 | Períodos de regime **não se sobrepõem**, e a escolha do "último" é determinística. | BL-211/A2 + DE-039 |
| 6 | Gravação de regime tributário passa **pelo serviço** em qualquer porta, ou a porta deixa de existir. | BL-211/A2 |
| 7 | Vigência de regime respeita o teto "hoje" (**RC-85**) e o caminho de exclusão do **RC-86/DE-039**, também no admin. | RC-85, RC-86, DE-039 |
| 8 | Alteração relevante feita pelo admin gera **`RegistroAuditoria`**, não só `LogEntry` do Django. | BL-211/A3, BL-57 |

### Hipóteses declaradas

| # | Hipótese | Como validar |
| --- | --- | --- |
| H1 | Bloquear a troca de escritório no `change` e liberá-la no `add` atende a operação real do escritório. | O Fred confirma se **existe** caso legítimo de transferir empresa entre escritórios. Se existir, ele não é "editar um campo": é procedimento explícito, com trilha, e vira etapa própria |
| H2 | Nenhum fluxo do produto depende de editar `Conta.natureza` depois do primeiro movimento. | Varredura do código e das telas; se depender, a regra muda de forma, não de existência |

### Pendência

| # | Pendência | Impacto |
| --- | --- | --- |
| P1 | **Transferir empresa entre escritórios é operação que o escritório precisa?** Com que frequência, quem autoriza, e o que deve acontecer com a escrituração já feita? | Decide se a correção é "recusar sempre" ou "recusar no caminho cotidiano e oferecer procedimento auditado". Enquanto não houver resposta, vale **recusar**, que é o lado seguro e reversível |

## Critérios de aceite

Cada critério é medido por **requisição autenticada ao admin**, com objeto
conferido depois da resposta.

1. POST no `change` de conta **com partidas** trocando `empresa` → recusa, e a
   conta permanece **byte a byte** como estava (empresa, natureza, tipo).
2. POST no `change` de conta **com filhas** trocando `empresa` → recusa.
3. POST trocando `natureza` ou `tipo` de conta **com movimento** → recusa. O
   sinal do histórico não muda; Diário, Razão e Balancete continuam
   conciliáveis entre si antes e depois da tentativa.
4. Conta **sem movimento e sem filhas** continua editável: a defesa não
   engessa o cadastro legítimo.
5. POST no `change` de empresa **com escrituração** trocando `escritorio` →
   recusa, e uma consulta pelo escritório de origem **continua** devolvendo a
   empresa, o plano de contas e os lançamentos.
6. Pelo admin, **não nasce** segundo período de regime aberto: a tentativa é
   recusada e a contagem de períodos abertos por empresa continua ≤ 1 — medida
   **no banco**, não na resposta.
7. A invariante do item 6 vale **também por ORM direto**, provada por
   `UniqueConstraint` (ou equivalente) em migração: o teste grava sem passar
   pelo admin nem pelo serviço e recebe erro de integridade.
8. **Concorrência**: duas requisições simultâneas que abririam período de regime
   para a mesma empresa resultam em **um** período aberto, sem 5xx. Medido em
   **PostgreSQL**, não em SQLite.
9. **Desempate determinístico**: com dois períodos de mesmo `vigencia_inicio`
   plantados no banco, a consulta do "último regime" devolve **sempre o mesmo**
   registro, em execuções repetidas.
10. Vigência futura continua recusada no admin (**RC-85**), e a exclusão segue o
    alcance do **RC-86/DE-039** (só o último período; o anterior volta a
    vigente; o evento vai para `RegistroAuditoria`).
11. Cada recusa dos itens 1 a 10 grava, ou deixa de precisar gravar,
    `RegistroAuditoria` de forma **declarada** — e cada alteração
    **bem-sucedida** de campo estruturante grava.
12. **Inventário da varredura versionado**: existe teste que enumera todo
    `ModelAdmin` e `Inline` registrado e **reprova nomeadamente** quando aparece
    superfície nova sem decisão registrada. Superfície nova sem dono é o defeito,
    não a exceção.
13. **Prova por mutação**: para cada defesa nova, remover a defesa mata ao menos
    um teste. Defesa cuja remoção não mata teste **não está defendida** — é a
    medição que a DL-019 e a DL-020 tornaram obrigatória.
14. `ruff check`, `ruff format --check`, `manage.py check`,
    `makemigrations --check --dry-run` e `pytest` verdes, medidos em **cópia
    limpa** (`git archive <hash> | tar -x`), e os `check-runs` da revisão exata
    lidos antes de qualquer declaração de "verde".

## Fora do escopo

- Criar procedimento de transferência de empresa entre escritórios. Esta etapa
  **recusa**; o procedimento, se for necessário, é etapa própria (pendência P1).
- **BL-14, BL-16 e BL-57** (auditoria fora da transação, exclusão do log,
  atomicidade da trilha) — são o **pacote 3** da fila. Aqui entra apenas o
  registro das alterações que esta etapa passa a governar.
- Módulos novos, fechamento de competência (DL-016), primeiro acesso (DL-018) e
  recepção fiscal (DL-010).
- **BL-02** (proteção da `main`): ação administrativa do Fred.

## Divisão de arquivos

Conjuntos **disjuntos**, para que dois agentes nunca editem o mesmo arquivo.

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` | `apps/contabilidade/models.py`, `apps/contabilidade/admin.py`, `apps/empresas/models.py`, `apps/empresas/admin.py`, `apps/empresas/services.py`, migrações novas em `apps/*/migrations/`, testes novos `apps/*/tests/test_dl023_*.py` |
| `auditor-qa` | Nada. Audita a versão integrada e **não corrige** |
| `arquiteto-senior` | `docs/**`, `README.md`, integração e commit |

Nenhum implementador commita: a integração é do `arquiteto-senior`.

## Ordem obrigatória de execução

1. **Restrição de banco primeiro** (um período aberto por empresa), com migração
   e teste por ORM direto. É a defesa que vale em todas as portas.
2. **Depois** as defesas de modelo de `Conta` e `Empresa` (`clean()` e
   validadores), com teste por requisição.
3. **Depois** o admin: `readonly_fields`, remoção do inline ou passagem pelo
   serviço.
4. **Por último** a varredura enumerativa e a prova por mutação.

Fazer o admin antes da restrição produz a armadilha que este projeto já
encontrou três vezes: a regra passa a valer **na porta** e continua falhando
por ORM direto, e o teste verde esconde isso.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`, a partir
  de `24f6bbc`.
- **Branch de destino:** `main`, por PR.
