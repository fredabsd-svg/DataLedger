# DL-023 — Integridade administrativa: nenhuma regra vale só na porta pela qual foi escrita

**Estado:** **em validação** — rodada 1 REPROVADA, rodada 2 corrigiu os dez
itens, rodada 3 (segunda auditoria) **APROVOU COM RESSALVAS** em `a612604`;
rodada 4 curta em curso com três itens baratos. Aberta em
2026-09-16, a partir da `main` em `24f6bbc` (PR #23 integrado — DL-022).
Situação atual, sempre, em [docs/agents/estado.md](../agents/estado.md).

> **O cabeçalho dizia "em execução", termo que não existe no vocabulário do
> `AGENTS.md` §3** e que nenhum outro plano do projeto usa. Quem mediu foi o
> auditor (achado A7, BL-260). Corrigido para `em desenvolvimento`.

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

## Inventário da superfície, medido na abertura da etapa

Varredura feita pelo `auxiliar-pesquisa` em `24f6bbc`, por leitura de código
(declarada como estática onde foi estática). **Onze** superfícies de escrita
registradas: `EmpresaAdmin`, `EstabelecimentoInline`,
`HistoricoRegimeTributarioInline`, `ContaAdmin`, `ItemLancamentoInline`,
`LancamentoContabilAdmin`, `EscritorioAdmin`, `VinculoInline`,
`VinculoUsuarioEscritorioAdmin`, `UserAdmin` e `RegistroAuditoriaAdmin`.

**O que o inventário confirmou dos itens já conhecidos:** `Conta.clean()`
(`apps/contabilidade/models.py:64-131`) defende `conta_pai` (empresa diferente e
ciclo) e a reclassificação para sintética — **e não olha `empresa`, `natureza`
nem `tipo`**. `Empresa` **não tem `clean()` nenhum**; só `save()` normalizando
CNPJ. `HistoricoRegimeTributario` não tem `clean()` nem
`Meta.constraints` — o validador de campo cobre só a **faixa** de data, e o
fechamento do período anterior existe apenas dentro de
`registrar_regime_tributario`, que o inline **não chama**.

**Três achados que o inventário acrescentou, e que esta etapa passa a
carregar:**

| Achado | Medido | Decisão do `arquiteto-senior` |
| --- | --- | --- |
| **`RegistroAuditoriaAdmin` não bloqueia exclusão.** `has_add_permission` e `has_change_permission` devolvem `False`, e todos os campos são `readonly` — mas `has_delete_permission` **não é sobrescrito**, então a exclusão fica sujeita só à permissão de modelo | `apps/auditoria/admin.py:7-18`, por leitura; **sem nenhum teste por requisição** cobrindo | **Entra nesta etapa.** A trilha de auditoria é o que resta quando todo o resto falha; deixar a porta aberta sabendo dela seria escolher não fechar. O que **não** entra é o resto da **BL-16/BL-14/BL-57** (atomicidade da trilha e proteção fora do admin), que segue no pacote 3 |
| **Nenhuma alteração feita pelo admin gera `RegistroAuditoria`.** Nenhum `admin.py` chama `registrar()`, nenhum sobrescreve `save_model`/`delete_model`/`save_formset`, e não há signal genérico | grep em `apps/**/admin.py` e `apps/*/signals.py` | **Registrado como BL-244**, e o critério 11 desta etapa foi **estreitado** de acordo: aqui se exige o registro nas operações que esta etapa governa e a **declaração explícita** da ausência nas demais. Prometer trilha completa no admin nesta etapa seria escopo do pacote 3 disfarçado |
| **Seis superfícies não têm teste algum por requisição autenticada:** `EmpresaAdmin`, `EstabelecimentoInline`, `ContaAdmin`, `EscritorioAdmin`/`VinculoInline`, `VinculoUsuarioEscritorioAdmin`, `UserAdmin` e `RegistroAuditoriaAdmin` | busca por `/admin/` em `apps/**/tests/**`: só quatro arquivos contêm a string | É a prova de que a BL-211 é **classe**, não caso. O critério 12 (varredura enumerativa) passa a exigir que **cada** uma das onze superfícies tenha decisão registrada: defendida, deliberadamente livre, ou fora do produto |

**O que o inventário declarou não ter medido**, e continua valendo como limite:
se o `LogEntry` nativo do Django está gravando; o comportamento efetivo de
`has_*_permission` herdado, fora dos casos com teste; e se cada
`Meta.constraints` já está migrada no banco. Nada disso vira afirmação desta
etapa sem execução.

## A classe do problema, não os casos

> **A classe é:** nenhuma regra de negócio vale apenas na porta pela qual ela
> foi escrita, e nenhuma alteração de dado estruturante acontece sem trilha.

Os três casos acima são **exemplos**. O que a etapa precisa entregar é a
propriedade: regra que o admin tem de respeitar mora no **modelo**, não só no
serviço — porque o serviço defende uma porta e o modelo alcança mais de uma.

> **Correção de uma frase FALSA que estava aqui, medida pelo auditor (achado
> P3, BL-247).** Este parágrafo afirmava que "o modelo defende **todas** as
> portas, inclusive ORM direto, `shell`, importação e tarefa em segundo plano".
> Isso é **falso para `clean()`**, e a **DE-008** deste projeto já dizia: ele só
> roda quando alguém chama `full_clean()`, o que na prática significa
> `ModelForm` e admin. O auditor mediu a invariante caindo por `.save()`,
> `QuerySet.update()` e `bulk_update`, com o balancete indo a `0 D × 1.000 C`.
>
> **As duas camadas não são equivalentes, e a diferença é esta:**
>
> | Camada | Alcance real |
> | --- | --- |
> | Restrição de banco (`Meta.constraints`) | **Toda** porta, inclusive ORM direto, `shell`, SQL cru e importação. O auditor confirmou nos três |
> | `Model.clean()` | Só quem chama `full_clean()` — `ModelForm` e admin |
> | Serviço | Só quem chama o serviço |
>
> Nesta etapa, o regime tributário ganhou a camada de **banco**; a conta e a
> empresa ficaram com `clean()`. Hoje **não existe porta de cliente** para
> `Conta.empresa`, `Conta.natureza` nem `Empresa.escritorio` — o auditor
> conferiu a API, a tela e os serializadores. A camada de banco para esses dois
> casos está registrada como **BL-247**, com a **DL-010** (importação em lote)
> como gatilho: é o primeiro caminho que grava sem `full_clean()`. O limite
> passa a estar escrito aqui, na DE-008 e nos comentários do código — nos três
> lugares dizendo a mesma coisa.

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
| 2 | Conta com movimento **próprio ou de qualquer descendente** não muda de natureza nem de tipo. | BL-83; **corrigido na rodada 1** pelo achado P1/BL-245 — a redação anterior dizia só "com movimento", e a sintética com filha movimentada passava. A natureza da sintética é a que governa a apresentação do grupo no Balancete, então recortar pelo movimento próprio foi escrever a regra pelo mecanismo em vez do efeito proibido, contra a **DE-032** |
| 3 | Empresa **com escrituração** (plano de contas, lançamento ou estabelecimento) não muda de escritório pelo uso cotidiano. | BL-211/A3 |
| 4 | Uma empresa tem, no máximo, **um** período de regime tributário aberto. | BL-211/A2 |
| 5 | Períodos de regime **não se sobrepõem**, e a escolha do "último" é determinística. | BL-211/A2 + DE-039 |
| 6 | Gravação de regime tributário passa **pelo serviço** em qualquer porta, ou a porta deixa de existir. | BL-211/A2 |
| 7 | Vigência de regime respeita o teto "hoje" (**RC-85**) e o caminho de exclusão do **RC-86/DE-039**, também no admin. | RC-85, RC-86, DE-039 |
| 8 | Alteração relevante feita pelo admin gera **`RegistroAuditoria`**, não só `LogEntry` do Django — **nesta etapa, nas operações que ela governa**; a cobertura completa do admin é **BL-244** e fica no pacote 3. Onde a trilha não existir, a ausência é **declarada**, não silenciosa. | BL-211/A3, BL-57, BL-244 |
| 9 | Registro de auditoria **não se apaga pelo admin**. | Inventário de `24f6bbc`; família da BL-16 |

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
11. **Trilha: o que esta etapa promete, medido, e nada além.** Está medido que
    **nenhuma** alteração feita pelo admin gera `RegistroAuditoria` hoje
    (**BL-244**). Aqui se exige: (a) o registro nas operações que esta etapa
    governa; (b) a **ausência declarada**, no código e no relatório, onde ela
    permanece. Prometer trilha completa do admin nesta etapa seria o pacote 3
    disfarçado — e promessa maior que a defesa é a família de defeitos que este
    projeto mais repetiu.
12. **Inventário da varredura versionado**: existe teste que enumera todo
    `ModelAdmin` e `Inline` registrado e **reprova nomeadamente** quando aparece
    superfície nova sem decisão registrada. As **onze** superfícies de `24f6bbc`
    entram com decisão explícita: defendida, deliberadamente livre, ou fora do
    produto. Superfície nova sem dono é o defeito, não a exceção.
13. **A exclusão de registro de auditoria pelo admin é recusada**, provada por
    requisição autenticada: `has_delete_permission` devolve `False` em
    `RegistroAuditoriaAdmin`, o POST de exclusão individual **e** a ação em lote
    são recusados, e o registro continua no banco depois da tentativa.
14. **Prova por mutação**: para cada defesa nova, remover a defesa mata ao menos
    um teste. Defesa cuja remoção não mata teste **não está defendida** — é a
    medição que a DL-019 e a DL-020 tornaram obrigatória.
15. `ruff check`, `ruff format --check`, `manage.py check`,
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
| `desenvolvedor-pleno` | `apps/contabilidade/models.py`, `apps/contabilidade/admin.py`, `apps/empresas/models.py`, `apps/empresas/admin.py`, `apps/empresas/services.py`, **`apps/auditoria/admin.py`** (só o bloqueio de exclusão do critério 13), migrações novas em `apps/*/migrations/`, testes novos `apps/*/tests/test_dl023_*.py` |
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

## Rodada 1 — REPROVADA em `96284a4`

Relatório integral, preservado sem edição, em
[docs/auditorias/2026-09-16-dl-023-rodada-1.md](../auditorias/2026-09-16-dl-023-rodada-1.md).

O auditor refez por execução própria o lint, o formato, o `manage.py check`, o
`makemigrations --check` e a suíte inteira em cópia limpa (**1251 passed**), e
refez a **prova por mutação completa**: as **9** defesas novas matam teste,
9 de 9. O que reprova **não é falta de defesa** — são dois casos que a defesa
não alcança, e os dois estão dentro do que a etapa existe para fechar:

| Achado | Gravidade | O que é |
| --- | --- | --- |
| **P1 / BL-245** | ALTA | Conta **sintética** com filha movimentada troca natureza e tipo pelo admin (`302`), e a linha do grupo no Balancete vai de `+1000` para `-1000` com o rodapé continuando a fechar |
| **P2 / BL-246** | ALTA | A etapa **introduziu** um 5xx: `DELETE` de regime sob concorrência com o `POST` devolve **500**, reproduzido 6 vezes em 8. Sem corrupção — reverte inteiro —, mas é a classe da BL-144 que esta etapa declarava fechada |
| **P3 / BL-247** | MÉDIA | A defesa de conta e empresa vale só na porta do `ModelForm`; e o **plano afirmava o contrário do que a DE-008 já dizia** (corrigido acima) |
| **P4 / BL-248** | MÉDIA | Fronteira de **escritório** não é checada ao mover conta, e o formulário lista empresas de outros escritórios |
| **A1 / BL-254** | MÉDIA | **Achado contra o `arquiteto-senior`:** os 14 testes de admin de `empresas` passam com `payload` impossível — nenhum distingue "a defesa recusou" de "o formulário quebrou" |
| P5–P9, A2–A7 | BAIXA a MÉDIA | BL-249 a BL-253 e BL-255 a BL-260 |

**O que o auditor confirmou funcionando, e não aceitou de declaração:** a
restrição de banco é real (índice conferido no banco) e resiste a ORM direto,
`bulk_create` e SQL cru; 8 `POST` simultâneos dão `201` + sete `400`, sem 5xx;
a troca de ordem da exclusão é **atômica e sem janela**, com trilha correta
inclusive sob falha induzida no meio; o critério 13 funciona de fato; e o
`LogEntry` nativo — que este plano havia declarado "não medido" — grava, registra
só o que mudou e **não** tem `ModelAdmin`, logo não é apagável pelo admin.

**Distribuição da rodada 2:** P1, P2, P4, P5, P7, A1, A2, A5, A6 ao
`desenvolvedor-pleno` (são arquivos dele, inclusive os de teste); A3, A4
(docstring), A7 e o texto deste plano ao `arquiteto-senior`. P3, P6, P8, P9 e a
fenda do registro de restrições ficam **registrados e fora da rodada 2**, com o
motivo escrito em cada item do backlog — corrigir sem medição é o que produziu o
P2.

## Rodada 3 — APROVADA COM RESSALVAS em `a612604`

Relatório integral em
[docs/auditorias/2026-09-16-dl-023-rodada-3.md](../auditorias/2026-09-16-dl-023-rodada-3.md).
**Os dez itens da rodada 2 foram verificados um a um**; oito estão fechados, o
BL-248 **parcialmente** e o BL-254 fechado só nos arquivos de `empresas`.

**Fechado e provado por execução do auditor:** a sintética com filha movimentada
recebe `200` e a linha do grupo continua `+1000,00`; o guard novo resiste a
profundidade 1200, a **ciclo pré-existente** (termina sozinho em 0,8 ms — a
afirmação sobre o `UNION` procede) e a subárvore inconsistente, errando para o
lado estrito; a corrida `3 POST + 3 DELETE` que dava **500 em 6 de 8** deu
**zero 5xx em 12 rodadas**, mais 10 rodadas de seis formas diferentes e 8 de
conferência da linha do tempo, sem sobreposição nem buraco; a migração `0005` é
`no-op` nos dois sentidos, aplicada, revertida e reaplicada; nenhum 5xx novo em
14 telas; conciliação, isolamento e idempotência sem regressão; e a prova por
mutação passou de 9/9 para **11/11**.

**As ressalvas, e o que foi feito com cada uma:**

| Ressalva | Destino |
| --- | --- |
| **BL-261** — terceiro caminho do mesmo dano: reparentar conta movimentada para grupo de natureza oposta | **Pergunta ao Fred.** Retificadora é exatamente natureza mista num grupo; software não distingue a legítima do erro de classificação, e o auditor parou onde devia |
| **BL-262** — o admin não tem isolamento por escritório em **nenhuma** superfície; uma de seis foi fechada, e o `/admin/autocomplete/` é inalcançável pela camada instalada | **Etapa própria.** A classe é maior que a BL-248 e nunca foi escopo desta etapa |
| **BL-264**, **BL-265**, **BL-266** | **Rodada 4**, curta: um `DoesNotExist` que esta etapa introduziu, dois nomes de coluna literais, e um teste que mede a camada errada |
| **BL-263** (contra o `arquiteto-senior`), **BL-267**, **BL-268**, **BL-269** | Backlog nomeado, sem rodada |

**Correção da classificação da varredura, feita por causa do achado P2:** a
decisão "defendida" para `contabilidade.Conta` passou a **nomear o que fica de
fora** — foi exatamente essa omissão que transformou a BL-248 em achado.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`, a partir
  de `24f6bbc`.
- **Branch de destino:** `main`, por PR. **O PR é parte da entrega** (achado
  A7/BL-260: sem ele, o workflow "Regras do projeto" não roda, e dos três
  mecanismos impostos só dois foram exercitados nesta revisão).
