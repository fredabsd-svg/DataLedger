# Reconferência independente — DL-066, etapa 2 (correção `c59f809`)

- **Papel:** `reconferente independente` — terceiro passo do ciclo de uma rodada
  (auditoria → correção única → reconferência). Não escrevi a
  [auditoria](2026-10-06-dl-066-etapa-2-auditoria.md) nem a correção `c59f809`;
  mãos limpas. Não corrigi código: o que não fechou volta ao orquestrador.
- **O que esta reconferência devia fechar:** os achados A1–A6/B1 da auditoria da
  etapa 2, item a item, por execução — exatamente a lista do §6 do relatório de
  auditoria.
- **Data:** 06/10/2026. **Motor:** Python 3.14 / SQLite
  (`sqlite:///C:/Users/conta/OneDrive/Área de Trabalho/Harness/.dsh-tmp/dataledger-reconf.sqlite3`),
  venv do repositório, workdir na raiz do `DataLedger`.
- **Cópias descartáveis** (worktrees do commit `c59f809`, em
  `..\ .dsh-tmp\mut-reconf-m6`, `mut-reconf-m8` e `mut-reconf-sonda`): só nelas
  as mutações destrutivas e as sondas foram aplicadas. O repositório auditado
  permaneceu intocado (`git status --short` sem saída ao final).
- **Linha de base de ambiente** (aceita como limite, não como achado):
  concorrência/threads em SQLite, Chromium, POSIX/umask e constraints do SQLite
  — o R4 da DRE e o novo teste de corrida da DFC caem nesta classe.

## 1. Veredito do ciclo

**REPROVADO** — seis dos sete achados fecham por execução (A1, A2, A3, A5, A6,
B1), com as mutações destrutivas A1/A3 agora MORTAS pelos testes que a correção
criou. O ciclo não fecha porque **A4 (MÉDIO) não fechou**: o teste de corrida
novo **não espelha o R4 da DRE** — falta o
`@pytest.mark.django_db(transaction=True)` que o R4 tem — e, sem ele, a prova
que a A4 pedia (CI/PostgreSQL) **não vai medir a trava**: as threads do teste
não enxergam o cenário criado na transação do teste e morrem antes da barreira.
O defeito é novo (N1, §3) e foi encontrado nesta reconferência.

O que falta para o ciclo fechar é **uma linha** (o decorator acima, em
`test_dl066_classificacao.py::test_a4_corrida_na_classificacao_da_dfc_serializa_e_a_trilha_fica_coerente`);
a terceira rodada de auditoria é proibida (AGENTS.md §3.1), então o caminho é
corrigir na etapa de entrega e deixar a CI/PostgreSQL ser a prova que a A4
pedia — ou reabrir o critério com o Fred.

## 2. Resumo, achado a achado

| Achado | Nível | Veredito | Prova |
| --- | --- | --- | --- |
| A1 — PATCH parcial cego | GRAVE | **FECHADO** | mutação M6 reproduzida → teste reprova |
| A2 — provisão/20(a)×20(b) | MÉDIO | **FECHADO** (observação menor em §3.2) | 4 textos conferidos + 3 cenários executados |
| A3 — permissões das 4 portas | MÉDIO | **FECHADO** | 4 testes de CLIENTE passam; mutação M8 reproduzida → 4 reprovações |
| A4 — trava `select_for_update()` | MÉDIO | **NÃO FECHADO** | teste existe e local reprova como previsto (limite de ambiente), mas não espelha o R4 (falta `transaction=True`) → prova de CI inviável (N1) |
| A5 — descarte mudo | MÉDIO | **FECHADO** | POST recusa a chave por nome (400), nada gravado; BL-631 registrada; comentário honesto (as duas portas medidas) |
| A6 — registro | BAIXO | **FECHADO** | BL-629 fechada com critério cumprido; data do plano = 06/10/2026; `estado.md` = pendente de entrega |
| B1 — formulário do admin | BAIXO | **FECHADO** | 2 testes do `ModelForm` do admin passam (recusa + campos visíveis) |

## 3. Achados, com comando e saída real

### A1 (GRAVE) — FECHADO — a mutação M6 agora é morta pelo teste

A correção reconstruiu o cenário de `test_patch_parcial_nao_mexe_no_que_nao_veio`
(`apps/contabilidade/tests/test_dl066_api.py:191`) com os campos ausentes em
valores **diferentes** do default destrutivo (`item_de_resultado_sem_caixa=True`
numa conta, `caixa_e_equivalentes=True` em outra), asserção de sobrevivência dos
dois **e** trilha só do campo enviado.

Mutação M6 reaplicada em cópia descartável
(`..\ .dsh-tmp\mut-reconf-m6\apps\contabilidade\views.py`, o merge do
`ContaClassificacaoDfcView.patch`):

```text
caixa_e_equivalentes=entrada.validated_data.get("caixa_e_equivalentes", False)        # era conta.caixa_e_equivalentes
classificacao_dfc=entrada.validated_data.get("classificacao_dfc", None)               # era conta.classificacao_dfc
item_de_resultado_sem_caixa=entrada.validated_data.get("item_de_resultado_sem_caixa", False)  # era conta.item_de_resultado_sem_caixa
```

Comando: `pytest apps/contabilidade/tests/test_dl066_api.py -q` sobre a mutação.

Saída real (recorte):

```text
>       assert despesa.item_de_resultado_sem_caixa is True, (
            "o campo que não veio no PATCH não pode voltar ao default"
        )
E       AssertionError: o campo que não veio no PATCH não pode voltar ao default
E       assert False is True
apps\contabilidade\tests\test_dl066_api.py:220: AssertionError
FAILED apps/contabilidade/tests/test_dl066_api.py::test_patch_parcial_nao_mexe_no_que_nao_veio
1 failed, 13 passed, 3 warnings in 7.02s
```

Na auditoria a mesma mutação dava `11 passed` (sobrevivia). Agora **morre**.
O teste também mede a trilha (`{"classificacao_dfc": {"antes": FINANC, "depois": ATIV}}`,
só o campo que mudou) e a segunda perna do cenário (`caixa_e_equivalentes` True
sobrevive a um PATCH que só envia `classificacao_dfc: null`). **FECHADO.**

### A2 (MÉDIO) — FECHADO — os textos orientam o caminho que fecha; os três cenários fecham/vetam como prometido

**(a) Textos** (inspeção, com citação literal):

- `help_text` de `item_de_resultado_sem_caixa` (`apps/contabilidade/models.py:1153-1171`):
  *"Para PROVISÃO operacional, não use esta marcação: marque a contrapartida (o
  passivo) como atividade operacional — marcar as duas ajusta o mesmo fato duas
  vezes e a conciliação do item 20A veta a DFC."* → caminho que fecha **e** o que
  acontece com as duas marcadas.
- Mensagem da pendência `indireto_nao_fecha` (`apps/contabilidade/services.py:6233-6238`):
  *"(confira se uma despesa marcada como sem caixa e sua contrapartida patrimonial
  operacional estão marcadas as DUAS — só uma das duas pode ajustar o mesmo fato)"*
  → nomeia a colisão e a convenção "um marcador por fato" (ver observação §3.2).
- Docstring de `_apurar_operacional_indireto` (`apps/contabilidade/services.py:6271-6287`):
  *"A saída não é ajustar o número — é marcar **uma** das duas metades […]: o
  passivo operacional marcado, a despesa sem a marcação. Um fato que misture as
  famílias mesmo assim vira `indireto_nao_fecha`, que veta e nomeia a diferença."*
  A frase falsa da auditoria ("cada fato contábil é ajustado UMA vez") foi
  substituída por "cada CONTA em exatamente UMA delas" + o limite dito direito.
- Nota do plano (`docs/planos/DL-066-dfc.md:454-466`, seção Etapa 2):
  *"**Decisão:** […] marcar o **passivo** como operacional […] e **não** marcar a
  despesa. […] quem marcar as duas mesmo assim recebe o veto nomeando a diferença."*

**(b) Os três cenários, executados** (sonda descartável em
`..\ .dsh-tmp\mut-reconf-sonda\apps\contabilidade\tests\test_zz_reconferencia_sonda.py`;
provisão 10.000,00: despesa 5.3 × "Provisões a Pagar" 2.3 marcado operacional):

Comando: `pytest apps/contabilidade/tests/test_zz_reconferencia_sonda.py -q -s`
→ `5 passed`.

```text
[S1 provisao-nao-paga, uma marcação] {'lucro_liquido': '-10000',
 'ajustes': [('20(a)', '2.3', '+', '10000')], 'total_dos_ajustes': '10000',
 'fluxo_operacional': '0', 'pelo_direto': '0', 'diferenca': '0',
 'confere': True, 'pode_emitir': True, 'motivos': [], 'pendencias': {}}

[S2 mes 3]  ... 'confere': True, 'pode_emitir': True ...
[S2 mes 4, provisao paga] {'lucro_liquido': '-10000', 'ajustes': [],
 'total_dos_ajustes': '0', 'fluxo_operacional': '-10000',
 'pelo_direto': '-10000.00', 'diferenca': '0.00',
 'confere': True, 'pode_emitir': True, 'motivos': [], 'pendencias': {}}

[S3 mes 3, marcação dupla] {'lucro_liquido': '-10000',
 'ajustes': [('20(a)', '2.3', '+', '10000'), ('20(b)', '5.3', '+', '10000')],
 'total_dos_ajustes': '20000', 'fluxo_operacional': '10000',
 'pelo_direto': '0', 'diferenca': '10000', 'confere': False,
 'pode_emitir': False, 'motivos': ['a conciliação do método indireto não fecha
 — os ajustes do item 20 não reproduzem o fluxo operacional apurado pelos
 lançamentos (confira se uma despesa marcada como sem caixa e sua contrapartida
 patrimonial operacional estão marcadas as DUAS — só uma das duas pode ajustar
 o mesmo fato) (1)'], 'pendencias': {'indireto_nao_fecha': 1}}
[S3 diferença nomeada] 10000
[S3 mes 4, depois de paga] ... 'confere': False, 'pode_emitir': False ...
```

- Provisão **não paga**, UMA marcação (só o passivo operacional): **fecha**
  (`confere True`, `diferenca 0`, emite).
- Provisão **paga no mês seguinte**, mesma marcação única: março **e** abril
  **fecham** (`confere True`, emitem; em abril os ajustes somam 0 e o fluxo do
  direto é −10.000,00, o que bate).
- **Despesa marcada + passivo operacional** (duas marcações): **veta** com
  `indireto_nao_fecha` nomeando a diferença (`10000`), `pode_emitir False`, e a
  mensagem nomeia a marcação dupla ("estão marcadas as DUAS") — antes e depois
  do pagamento. É o comportamento que a decisão registrada promete.

**FECHADO.**

### A3 (MÉDIO) — FECHADO — as quatro portas têm teste de CLIENTE e a mutação M8 morre

Comando (árvore limpa):
`pytest <os 4 testes a3 de test_dl066_api.py e test_dl066_tela_dfc.py> -q`
→ `4 passed, 2 warnings in 3.51s` (API GET da DFC, API PATCH da classificação,
tela da DFC, tela de classificação — todas exigem 403 para CLIENTE; as de
escrita ainda asseguram que nada foi gravado nem registrado).

Mutação M8 reaplicada em cópia descartável
(`..\ .dsh-tmp\mut-reconf-m8`): `permission_classes = []` em `DfcView` e em
`ContaClassificacaoDfcView` (`apps/contabilidade/views.py:2249, 2301`) e
`if False:` nas checagens de papel de `dfc` e `conta_classificacao_dfc`
(`apps/contabilidade/views_web.py:6278, 1478`).

Comando: `pytest test_dl066_api.py test_dl066_tela_dfc.py test_dl038_recusa_livro_caixa.py -q`
sobre a mutação.

Saída real (resumo):

```text
FAILED apps/contabilidade/tests/test_dl066_api.py::test_a3_o_get_da_dfc_nao_e_de_cliente
FAILED apps/contabilidade/tests/test_dl066_api.py::test_a3_o_patch_da_classificacao_nao_e_de_cliente
FAILED apps/contabilidade/tests/test_dl066_tela_dfc.py::test_a3_a_tela_da_dfc_nao_e_de_cliente
FAILED apps/contabilidade/tests/test_dl066_tela_dfc.py::test_a3_a_tela_de_classificacao_nao_e_de_cliente
4 failed, 77 passed, 17 warnings in 17.51s
```

Na auditoria a mesma mutação dava `76 passed`. Agora **morre** nos quatro
testes novos (o exemplo do fim: `assert 302 == 403` — a tela classifica e
redireciona quando a checagem de papel some). **FECHADO.**

### A4 (MÉDIO) — NÃO FECHADO — o teste existe e o resultado local é o previsto, mas não espelha o R4 (defeito novo N1)

O que **fechou**:

- O teste de corrida novo existe
  (`test_dl066_classificacao.py:432`) e reproduz a mecânica do R4 da DRE
  (barreira em `full_clean()`, duas threads, coerência da trilha).
- Resultado honesto da execução local
  (`pytest test_dl066_classificacao.py::test_a4_corrida_na_classificacao_da_dfc_serializa_e_a_trilha_fica_coerente -q`):

```text
>       assert primeira_travou.wait(timeout=5), "a primeira thread não chegou à barreira a tempo"
E       AssertionError: a primeira thread não chegou à barreira a tempo
apps\contabilidade\tests\test_dl066_classificacao.py:479: AssertionError
...
django.db.utils.OperationalError: database table is locked: contabilidade_conta
    (em Thread-1, na PRIMEIRA consulta da thread: Conta.objects.get(pk=receita.pk))
1 failed, 3 passed, 2 warnings in 6.99s   (rodado junto com A5/B1)
```

  É exatamente o previsto no seu roteiro: falha de **classe de ambiente**
  (SQLite degrada o lock), igual ao R4 da linha de base. Não é reprovação do
  produto.
- O docstring do serviço **não** afirma medição local: `classificar_conta_na_dfc`
  (`apps/contabilidade/services.py:6174-6176`) diz *"CORRIDA:
  `select_for_update()` antes de ler os valores gravados — duas classificações
  concorrentes da MESMA conta serializam […] (mesmo molde das irmãs)"* —
  afirmação de código, sem nenhuma menção a medição — e o próprio teste declara
  o limite: *"Vale como prova de corrida só em PostgreSQL (a CI); em SQLite […]
  este teste é da classe de ambiente"*.

O que **não fechou** — o espelho do R4 está incompleto e a prova de CI não vai
funcionar (defeito novo **N1**, §4): o R4 tem
`@pytest.mark.django_db(transaction=True)` (`test_dl045_dre.py:3159`); o teste
novo tem apenas o `pytestmark = pytest.mark.django_db` do módulo
(`test_dl066_classificacao.py:49`) — `pyproject.toml` não tem marcador global.
Sem `transaction=True` o cenário fica na transação do teste e as threads, com
conexão própria, **não o enxergam**. **NÃO FECHADO.**

### A5 (MÉDIO) — FECHADO — a chave é recusada por nome (400), nada é gravado, e o comentário é honesto

Comando: `pytest test_dl066_api.py::test_a5_os_campos_da_dfc_no_cadastro_sao_recusados_nunca_descartados -q`
→ passed (rodado em `1 failed, 3 passed` conjunto; ele é o `3 passed` junto com
os dois B1).

O corpo real do 400 (sonda `test_a5_qual_porta_responde_o_post`, em
`mut-reconf-sonda`, mesma requisição do teste):

```text
[A5 corpo do 400] 400 ['Campo(s) não reconhecido(s) no cadastro de conta:
classificacao_dfc. Campos aceitos: aceita_lancamento, ativo, classificacao_dlpa,
classificacao_dmpl, classificacao_dre, codigo, conta_pai, natureza, nome, tipo.']
```

- A recusa vem da **primeira** porta (`CONTRATO_POST_CONTA` via
  `apps/core/requisicao.py:256-267`): nomeia a chave **e** lista os campos
  aceitos; o teste mede ainda que **nada é gravado** (`Conta` com `codigo 9.9`
  não existe).
- O comentário do serializer (`apps/contabilidade/serializers.py:139-152` e
  `206-237`) é **honesto sobre as duas portas**: diz que `read_only` puro
  descartava em silêncio (BL-196), que a primeira porta é o contrato de
  requisição (medida no teste) e que o `validate()` que recusa pelo
  `initial_data` é a **segunda**, "defesa em profundidade para quando uma rota
  aceitar o corpo sem contrato", apontando o PATCH da classificação. A sonda
  acima confirma a ordem declarada (a primeira porta responde hoje).
- A **BL-631** está registrada no [backlog](../projeto/backlog.md) (linha 2165):
  descarte mudo eliminado; o que fica em aberto é aceitar a escrita no cadastro
  inicial pela **decisão D2 da DL-063** (Fred, 04/10/2026), com o critério de
  aceite pedido ("Decidir se os campos da DFC seguem a D2 […] ou permanecem só
  na porta própria"), `aberta — decisão do Fred`.

**FECHADO.**

### A6 (BAIXO) — FECHADO — registro corrigido; `estado.md` é pendente de entrega

- **BL-629 fechada** no [backlog](../projeto/backlog.md) (linha 2163):
  *"**fechada na DL-066, etapa 2** (commit `96e0997`): o teste passou a exigir a
  enumeração EXPLÍCITA das chaves (`CHAVES_ESPERADAS_DAS_PENDENCIAS_DA_DFC`) […]
  | cumprido"*. O critério foi conferido por execução: `test_dl066_dfc.py:313`
  declara a lista digitada no teste e as linhas 332-333 comparam os DOIS lados
  contra ela (`set(dfc["pendencias"]) == …` e `set(_TITULOS_DAS_PENDENCIAS_DA_DFC) == …`).
- **Data da Etapa 2 do plano** corrigida:
  `docs/planos/DL-066-dfc.md:381` → `### Etapa 2 — o fecho da fatia 1: portas,
  telas e método indireto (06/10/2026)`.
- **`estado.md`**: `docs/agents/estado.md:160` ainda traz "Falta para a fatia
  fechar: o serviço de classificação da atividade com…". Como seu roteiro manda,
  isto **não** é achado aberto: é item da **etapa de entrega** que segue esta
  reconferência — registrado em §5 como pendente de entrega.

**FECHADO** (com o item de entrega acima).

### B1 (BAIXO) — FECHADO — o critério 15 agora tem teste pelo `ModelForm` do admin

Comando: `pytest test_dl066_classificacao.py::test_b1_o_modelo_do_admin_recusa_a_mudanca_em_periodo_fechado
test_dl066_classificacao.py::test_b1_os_tres_campos_continuam_visiveis_no_admin -q`
→ passed (dentro do `1 failed, 3 passed` conjunto; são os dois de B1).

- `test_b1_o_modelo_do_admin_recusa_a_mudanca_em_periodo_fechado`
  (`test_dl066_classificacao.py:392`) instancia o `ModelForm` real do
  `ContaAdmin` (molde do `_formulario_do_admin` do DL-065), exige
  `form.is_valid() == False` e a mensagem com "03/2026".
- `test_b1_os_tres_campos_continuam_visiveis_no_admin` (linha 415) garante que
  `caixa_e_equivalentes`, `classificacao_dfc` e `item_de_resultado_sem_caixa`
  continuam **visíveis** no formulário (a trava é a regra, não o sumiço).

**FECHADO.**

## 4. Defeito NOVO encontrado nesta reconferência (primeira vez)

**N1 — MÉDIO — o teste de corrida da A4 não tem
`@pytest.mark.django_db(transaction=True)`: a prova prometida de CI/PostgreSQL
não vai medir a trava e deve reprovar por motivo errado.**

Evidência:

1. **Estrutura medida.** O R4 da DRE que o teste diz espelhar é
   `@pytest.mark.django_db(transaction=True)` (`test_dl045_dre.py:3159`); o novo
   `test_a4_corrida_na_classificacao_da_dfc_serializa_e_a_trilha_fica_coerente`
   (`test_dl066_classificacao.py:432`) só tem o `pytestmark = pytest.mark.django_db`
   do módulo (linha 49), e `pyproject.toml:76-78` não define marcador global.
2. **Convenção do repositório.** Os ~40 testes de threads do projeto usam
   `django_db(transaction=True)`, alguns com o motivo escrito —
   `apps/fiscal/tests/test_concorrencia.py:18-22`: *"`django_db(transaction=True)`
   é necessário para que as duas threads, cada uma com sua própria conexão,
   enxerguem de fato o commit uma da outra — o modo padrão de teste do Django
   envolve tudo numa transação que não seria visível entre conexões"*;
   `apps/contabilidade/tests/test_bl40_bl41.py:1080` e
   `apps/contabilidade/tests/test_dl043_zeramento_concorrencia_e_permissoes.py:316`
   dizem que o marcador "sobrepõe o `pytestmark` do módulo".
3. **Prova de visibilidade executada** (sonda `test_n1_visibilidade_*`, em
   `mut-reconf-sonda`, mesma conta lida por uma thread):

```text
[N1 django_db padrao] thread -> OperationalError: database table is locked: contabilidade_conta
[N1 django_db(transaction=True)] thread -> viu a conta criada no teste
```

4. **Consequência.** A falha local já mostra o ponto exato: a thread morre na
   PRIMEIRA consulta (`Conta.objects.get(pk=receita.pk)`), antes de chegar ao
   serviço. Em SQLite isso aparece como `database table is locked`; em
   PostgreSQL (CI), onde não há lock de tabela em leitura, a linha simplesmente
   **não existe** para a conexão da thread (não commitada) → `Conta.DoesNotExist`
   → a thread morre sem tocar a barreira → o teste reprova em
   `assert primeira_travou.wait(timeout=5)` **toda vez**, com ou sem
   `select_for_update()`. Ou seja: a prova que a A4 pedia ("a real é a
   CI/PostgreSQL") não mede a trava — e a CI desta branch ficaria vermelha.

**Correção sugerida** (para o orquestrador — eu não corrijo): acrescentar
`@pytest.mark.django_db(transaction=True)` ao teste A4, no molde literal do R4;
a CI/PostgreSQL passa então a ser a prova que faltava (e, com a mutação M10 —
trava removida —, a reprovação é o teste que a mata).

### 3.2 Observação menor (não reprova): a mensagem da pendência não nomeia qual marcação manter

A mensagem de `indireto_nao_fecha` nomeia a colisão e a convenção ("só uma das
duas pode ajustar o mesmo fato"), mas não diz qual das duas manter; o caminho
explícito ("passivo operacional marcado, despesa sem a marcação") está no
`help_text`, no docstring e no plano. Como o docstring afirma que "a orientação
está no `help_text` … e na mensagem da pendência", fica uma mini-imprecisão de
texto. O pedido da auditoria ("a pendência passa a nomear a convenção") está
cumprido; registro para eventual ajuste de texto, sem efeito no veredito.

## 5. Verificação de regressão obrigatória

Comando-base (workdir na raiz do repositório, `DATABASE_URL` do cabeçalho):

```powershell
& $py -m pytest apps/contabilidade/tests/test_dl066_dfc.py apps/contabilidade/tests/test_dl066_classificacao.py `
    apps/contabilidade/tests/test_dl066_indireto.py apps/contabilidade/tests/test_dl066_api.py `
    apps/contabilidade/tests/test_dl066_tela_dfc.py apps/contabilidade/tests/test_dl038_recusa_livro_caixa.py -q
```

Saída real: `1 failed, 122 passed, 47 warnings in 23.17s`. A única reprovação é
`test_a4_corrida_na_classificacao_da_dfc_serializa_e_a_trilha_fica_coerente`,
com `database table is locked` — **classe de ambiente** declarada (concorrência
em SQLite), exatamente a prevista no roteiro desta reconferência e a mesma do R4
da linha de base. Nada fora da linha de base.

| Verificação | Comando | Saída real |
| --- | --- | --- |
| Lint | `ruff check apps/contabilidade/ scripts/` | `All checks passed!` |
| Formatação | `ruff format --check .` | `365 files already formatted` |
| Documentação | `pwsh -NoProfile -File scripts/validate-docs.ps1` | `Documentação válida: 229 arquivos Markdown verificados.` (inclui este parecer) |

## 6. Pendências da etapa de ENTREGA (não são achados desta reconferência)

1. `docs/agents/estado.md` atualizado (o item "estado.md atualizado" do achado
   A6) — etapa de entrega, como o roteiro determinou registrar.
2. Push da branch `feat/dl-066-portas-e-indireto`, PR e CI — a branch segue
   apenas local (`git branch -vv` → sem upstream), como a auditoria já declarou.
3. A correção do N1 (uma linha) antes do push, para a CI não ficar vermelha; a
   CI/PostgreSQL será então a prova de corrida que a A4 pede (inclusive para a
   mutação M10 — trava removida — que esta reconferência não pôde executar em
   PostgreSQL: **não executado**, bloqueado pelo ambiente, igual ao §5 da
   auditoria).
4. Decisões do Fred registradas como abertas no backlog: BL-630 e BL-631.

## 7. Limites deste instrumento

- PostgreSQL local segue bloqueado (política do projeto desde 05/10/2026): toda
  prova de concorrência real é da CI. A consequência prática do N1 foi medida
  por inspeção + prova de visibilidade em SQLite (§4.3) e pela documentação do
  próprio repositório; o comportamento exato em PostgreSQL é previsão bem
  fundamentada, não execução — assim como o era o §5 da auditoria.
- As mutações M6 e M8 rodaram em worktrees descartáveis
  (`..\ .dsh-tmp\mut-reconf-m6` e `mut-reconf-m8`), preservados para
  re-verificação; o repositório auditado não foi tocado. A mutação M10 (trava
  removida) **não** foi reexecutada: sem PostgreSQL ela não tem como reprovar
  localmente, e o roteiro desta reconferência não a pedia.
- As sondas (cenários de provisão, porta do POST, visibilidade de threads) são
  instrumento meu, em `..\ .dsh-tmp\mut-reconf-sonda` — comprovam comportamento
  hoje; o que protege o futuro são os testes do produto, conferidos acima.
- Não avaliei adequação normativa das famílias do item 20 além da coerência
  interna e da contradição demonstrada (juízo do contador responsável), nem
  integração, desempenho ou os módulos fora do delta.
