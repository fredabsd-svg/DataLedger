# DL-069 — Travas no banco: livro-caixa, período encerrado e trilha

**Demanda:** ordem do Fred de 07/10/2026, *"Próxima etapa"* (RC-158), dada
depois da DL-068. A análise do repositório da mesma data recomendava esta
etapa como a seguinte. **Estado:** [fonte única](../agents/estado.md).
**Branch:** `ccr-9e799dfb-48okf5` → `main`. **Risco:** nível 1 (§3.1). É a
proteção do livro e da trilha, com uma auditoria independente por fatia e um
PR por fatia.

## Problema

A contabilidade já tem a imutabilidade do lançamento e o débito igual ao
crédito garantidos **no PostgreSQL** (DL-052, migrações `0013`, `0016` e
`0017`). Três proteções do mesmo nível ainda vivem só na aplicação. Basta uma
escrita que passe por fora do serviço para quebrá-las: um `QuerySet.update()`
num script, uma migração de dados ou um SQL de manutenção.

| # | Proteção | Onde está hoje | O que o banco não impede |
| --- | --- | --- | --- |
| 1 | Lançamento do livro-caixa imutável | `LancamentoCaixa.save()` e `delete()` em Python | `update()` e `delete()` de queryset e SQL direto alteram o livro que alimenta o carnê-leão |
| 2 | Período encerrado sem lançamento novo | `criar_lancamento` e `criar_lancamento_caixa`, com trava `FOR SHARE` | INSERT por fora do serviço em competência encerrada ou entregue, ou em mês de caixa encerrado |
| 3 | Trilha de auditoria imutável | `QuerySet` e sinais | SQL direto reescreve ou apaga a trilha |

O **limite aceito** segue o princípio do BL-569 (que trata do livro contábil): as travas protegem contra
escrita **acidental**, não contra quem tem acesso de dono ao banco (`TRUNCATE`,
`DISABLE TRIGGER`).

## Fatias

### Fatia 1 — livro-caixa imutável no banco (sem dependência)

**Base medida** no levantamento de 07/10/2026:
- Nenhum caminho legítimo faz UPDATE ou DELETE em `LancamentoCaixa` depois do
  INSERT. O estorno é um lançamento novo.
- `FechamentoMesCaixa` é atualizado por encerrar e reabrir, inclusive na
  cascata da DL-054, e nunca é apagado.

**Decisão (`arquiteto-senior`, reversível):** seguir o padrão da `0013` e da
`0017`, com gatilho `BEFORE UPDATE OR DELETE FOR EACH ROW`, erro `23514` com
`CONSTRAINT` estável traduzido em `apps/core/restricoes.py`, e no-op em SQLite.
- `LancamentoCaixa`: recusa **todo** UPDATE e DELETE, sem exceção.
- `FechamentoMesCaixa`:
  - recusa DELETE;
  - UPDATE só pode mudar as colunas que os serviços de encerrar e reabrir
    escrevem;
  - **qualquer outra coluna, inclusive as que vierem a existir, fica
    imutável**, pela técnica `to_jsonb(NEW) - permitidas = to_jsonb(OLD) -
    permitidas` da `0017`.

**Critérios de aceite:**
1. `LancamentoCaixa`:
   - `QuerySet.update()` em qualquer coluna é recusado com `IntegrityError`
     nomeando a restrição, e o valor no banco não muda;
   - SQL direto (`UPDATE` por `cursor`) é recusado do mesmo jeito;
   - o mesmo vale para `QuerySet.delete()` e `DELETE` por SQL.
2. `FechamentoMesCaixa`:
   - DELETE por ORM e por SQL é recusado;
   - UPDATE de `empresa_id`, `ano`, `mes` ou `criado_em` é recusado.
3. Encerrar, reabrir, a reabertura em cascata (DL-054), o lançamento, o
   estorno e os dependentes do carnê-leão continuam funcionando. A suíte
   existente de `apps/livro_caixa` passa.
4. A recusa tem mensagem em português registrada em
   `MENSAGENS_DE_RESTRICAO_DE_GATILHO`. **Hoje nenhuma porta do produto (tela,
   API, admin ou comando) provoca essa recusa**, porque nenhuma faz UPDATE ou
   DELETE nessas tabelas. A porta que um dia fizer isso precisa traduzir a
   recusa com `restricao_como_400` e ter teste de tela. Nenhuma verificação
   automática cobra isso (BL-644).
   *Histórico:* a primeira versão dizia que a recusa chegava à tela e à API e
   que "a varredura existente cobra o registro". As duas afirmações eram
   falsas e foram corrigidas pelos achados A1 da rodada 1 e R1 da
   reconferência.
5. A migração é reversível: um teste com `transaction=True` migra para trás e
   para frente, e depois de voltar o UPDATE passa.
6. Em SQLite as travas não existem. Isso é **declarado** no código e no teste
   (o teste é pulado fora do PostgreSQL), sem fingir cobertura.
7. Teste existente que prepara dado "torto" por `update()` só pode ser
   adaptado se o propósito dele for outro. A lista vai no relatório, com o
   motivo de cada um. **Proibido** mudar expectativa para ficar verde.
8. A suíte completa não regride. Linha de base de 07/10/2026, Python 3.13 no
   contêiner: 4.895 aprovados, 1 reprovado de ambiente e 53 pulados.

**Decisão tomada na implementação e confirmada pela auditoria:** o UPDATE do
fechamento é amarrado à **transição**.
- `aberto→encerrado` só muda `estado`, `fechado_em` e `fechado_por_id`.
- `encerrado→aberto` só muda `estado`, `reaberto_em`, `reaberto_por_id` e
  `motivo_reabertura`.
- Sem mudança de estado, nada muda.

Só a lista de colunas permitidas não recusaria "trocar `fechado_por` por fora
do serviço". O custo é que um UPDATE futuro sem transição, como retificar o
motivo, exigirá migração nova.

**Limite declarado (A3):** o gatilho olha colunas, não a trilha. Uma
reabertura completa feita por SQL passa sem registro na trilha. É o limite do
BL-569.

**Cenários negativos:**
- trocar `valor`, `data`, `empresa_id` ou `estorno_de_id` de um lançamento;
- trocar `fechado_por` ou `criado_em` de um fechamento por fora do serviço;
- apagar o fechamento de um mês encerrado;
- mutação: sem o gatilho, os testes de recusa caem.

### Fatia 2 — período encerrado recusa INSERT no banco (sem dependência do Fred)

Ponto de maior risco técnico, porque a trava no gatilho precisa da mesma
leitura protegida contra corrida que o serviço faz (`FOR SHARE`, BL-456).

O que entra:
- INSERT de `LancamentoContabil` com data em competência que não está
  `aberta`. A competência é achada **pela data**, não pela FK, porque a FK pode
  ser NULL em dado antigo.
- INSERT de `LancamentoCaixa` em mês encerrado, ou com mês posterior do mesmo
  ano encerrado (o encadeamento da DL-054).
- `Competencia.entregue_em` não volta a NULL.
- Competência entregue não volta a `aberta` (RC-101).

O que continua permitido:
- o backfill NULL→valor;
- o estorno em mês aberto (RC-103);
- a reabertura de competência não entregue.

Critérios detalhados serão escritos ao fim da fatia 1, com a medição do custo.

### Fatia 3 — trilha imutável no banco (**depende do Fred**)

Hoje apagar um escritório **sem empresas** mantém a trilha com
`escritorio_id=NULL`. Esse é o único UPDATE legítimo na tabela, e é do
`SET_NULL`. Uma trava completa precisa saber, antes:

- ~~**PE-76:** a trilha de um escritório pode ser apagada junto com ele, por
  exemplo num pedido de exclusão pela LGPD? Ou ela precisa sobreviver?~~
  **Respondida (RC-159):** a trilha é **preservada**, e nenhum DELETE na
  trilha é legítimo.
- **PE-77:** existe prazo de retenção da trilha?

O BL-637 (500 ao apagar escritório no admin) é tratado junto, porque mexe no
mesmo caminho.

## Impacto e reversão

- **Dados:** nenhum dado é alterado. As migrações só criam funções e
  gatilhos.
- **Desempenho:** na fatia 1, custo zero no INSERT, porque o gatilho só
  dispara em UPDATE e DELETE.
- **Reversão:** a migração reversa remove funções e gatilhos
  (`DROP ... IF EXISTS`).
- **Restauração de backup:** `pg_restore --data-only` passa a exigir
  `--disable-triggers`, o mesmo limite já declarado para a contabilidade
  (PE-07).

## Distribuição da fatia 1

| Responsável | Arquivos |
| --- | --- |
| `desenvolvedor-pleno` | migração nova em `apps/livro_caixa/migrations/`, `apps/core/restricoes.py` (só o registro das mensagens novas), testes novos em `apps/livro_caixa/tests/`, e os testes existentes que precisarem de adaptação, listados no relatório |
| `arquiteto-senior` | plano, `docs/`, integração |
| `auditor-qa` | auditoria da versão integrada, sem escrita |

## Evidências

Ver a seção desta etapa no [estado](../agents/estado.md) e os relatórios em
`docs/auditorias/`.
