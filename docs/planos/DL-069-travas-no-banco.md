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

**Critérios de aceite (escritos em 07/10/2026, ao fim da fatia 1 — PR #92
mesclado em 07/10/2026, merge `a610c70`):**

1. INSERT de `LancamentoContabil` com **data** em competência que não está
   `aberta` é recusado NO BANCO com `IntegrityError` nomeando a restrição
   `dl069_lancamento_contabil_so_em_competencia_aberta`, e nada é gravado:
   - por ORM (`objects.create()`, `Model.save()`, `bulk_create()`);
   - por SQL direto (`INSERT` por `cursor`);
   - a competência é achada **pela data** (empresa + ano/mês de `data`),
     nunca pela FK: lançamento com `competencia_id` NULL ou apontando para
     outro mês segue recusado quando a DATA cai em período não aberto;
   - toda condição que não `aberta` recusa, inclusive `em_encerramento` (a
     comparação é `!= aberta`, como em `criar_lancamento`,
     `apps/contabilidade/services.py:1026`).
2. INSERT de `LancamentoCaixa` é recusado com `IntegrityError` nomeando
   `dl069_lancamento_caixa_so_em_mes_aberto`, por ORM e por SQL direto, com o
   dado intacto, quando:
   - o mês do lançamento está encerrado; ou
   - existe mês **posterior do mesmo ano-calendário** encerrado (o
     encadeamento da DL-054 — a regra exata é a de
     `_recusar_se_mes_caixa_encerrado`, `apps/livro_caixa/services.py:569-639`,
     reproduzida item a item);
   - o estorno entra pela mesma regra: a data do estorno é a do original
     (DE-091 item 4), então estorno em mês encerrado é recusado como o
     lançamento.
3. `Competencia.entregue_em` não volta a NULL: UPDATE (ORM ou SQL) que tente
   zerar é recusado com `IntegrityError` nomeando
   `dl069_competencia_entregue_nao_volta_a_null`, e o valor não muda.
4. Competência entregue não volta a `aberta` (RC-101): UPDATE que faça a
   transição para `aberta` numa linha com `entregue_em` preenchido é recusado
   com `IntegrityError` nomeando `dl069_competencia_entregue_nao_reabre`.
5. Continua **permitido**, com teste provando que passa com os gatilhos
   ligados:
   - o backfill NULL→valor (`backfill_lancamento_competencia --apply` e o
     `QuerySet.update(competencia=...)` dele), inclusive quando a
     competência de destino já está encerrada — o backfill preenche dado
     legado e não grava lançamento novo;
   - o estorno em mês aberto (RC-103);
   - a reabertura de competência **não** entregue (contabilidade) e a do mês
     do livro-caixa;
   - o ciclo completo dos serviços: lançar, estornar, encerrar, entregar,
     reabrir e a reabertura em cascata da DL-054.
6. A recusa é traduzível: as quatro restrições ficam em
   `MENSAGENS_DE_RESTRICAO_DE_GATILHO`, com mensagem em português, e
   `restricao_como_400` converte a recusa real do banco na mensagem
   registrada. **Nenhuma porta do produto (tela, API, admin ou comando)
   alcança essas recusas hoje** — os serviços recusam antes, com a mensagem
   da competência/mês —; a porta que um dia alcançar precisa traduzir com
   `restricao_como_400` e ter teste de porta (mesma ressalva da fatia 1,
   BL-644).
7. A trava reproduz a leitura protegida contra corrida que o serviço faz,
   antes de julgar o estado:
   - contabilidade: `SELECT ... FOR SHARE` sobre a linha da competência
     achada pela data (BL-456;
     `_travar_competencia_em_modo_compartilhado`,
     `apps/contabilidade/services.py:526-667`);
   - livro-caixa: o lock consultivo COMPARTILHADO do mês e dos meses
     posteriores do ano, em ordem crescente, antes de ler o estado
     (`_adquirir_locks_dos_meses_do_ano` e
     `_recusar_se_mes_caixa_encerrado`, `apps/livro_caixa/services.py:547-639`);
   - a ordem de lock do gatilho é a mesma do serviço e não cria ciclo (o
     raciocínio está no comentário de cada migração).
8. Cenários negativos: INSERT direto em competência encerrada, entregue ou
   `em_encerramento`; INSERT com a FK `competencia` mentindo (outro mês);
   INSERT de estorno em mês encerrado; INSERT em janeiro com fevereiro
   encerrado (encadeamento); UPDATE zerando `entregue_em`; UPDATE reabrindo
   competência entregue, inclusive a reabertura completa por SQL; e mutação —
   sem o gatilho, os testes de recusa caem (a escrita passa).
9. **Limite declarado** (a família do BL-569): o gatilho não protege contra
   `TRUNCATE`, `DISABLE TRIGGER` nem contra quem escreve SQL de propósito. E
   há UMA corrida que ele não ordena: INSERT **por fora do serviço** em mês
   que ainda não tem linha de `Competencia`, cruzado com o PRIMEIRO
   fechamento daquele mês. O caminho do serviço está protegido —
   `obter_ou_criar_competencia` cria a linha antes do INSERT e o fechamento
   passa pelo mesmo `get_or_create` + `FOR UPDATE` — e o INSERT direto com
   linha existente também está (`FOR SHARE` do gatilho contra `FOR UPDATE` do
   fechamento). Criar a linha a partir do gatilho fecharia o canto, mas
   emprestaria ao INSERT um efeito colateral (nascer `Competencia` em
   qualquer INSERT direto, inclusive os de dado legado/torto dos testes e do
   backfill) — decisão registrada no comentário da migração.
10. Em SQLite as travas não existem: as migrações são no-op (declarado no
    código e no teste, sem fingir cobertura), os testes de recusa são pulados
    fora do PostgreSQL com o motivo escrito, e `manage.py migrate` completo
    (ida e volta) funciona em SQLite num banco temporário.
11. A migração é reversível: teste com `transaction=True` migra para trás e
    para frente; com a migração revertida a escrita passa (é o que prova que
    era o gatilho quem recusava — teste de mutação), e religada a recusa
    volta.
12. Nenhum teste existente é adaptado sem necessidade; toda adaptação (se
    houver) vai no relatório com o motivo de cada uma. **Proibido** mudar
    expectativa de teste para deixar a suíte verde.
13. A suíte completa não regride. Linha de base medida em 07/10/2026 nesta
    máquina (Windows, SQLite, Python 3.14.7, sem PostgreSQL local):
    **4.687 aprovados, 165 reprovados, 149 pulados em 454,68s** (segunda
    rodada: 4.683/169/149 em 495,25s — a flutuação de 4 testes é de
    concorrência em SQLite). Os reprovados são pré-existentes e de ambiente
    (`diag` do psycopg, threads, Chromium, poppler, permissões POSIX/umask,
    `ruff` fora do PATH). A comparação honesta é antes × depois no
    **conjunto** dos reprovados, não só na contagem. A prova dos gatilhos é
    da CI (`postgres:16-alpine`), que é onde os testes pulados localmente
    rodam de verdade.

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
