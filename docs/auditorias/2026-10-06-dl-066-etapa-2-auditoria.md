# Auditoria independente — DL-066, etapa 2 (portas, telas e método indireto da DFC)

- **Papel:** `auditor-qa`, rodada ÚNICA (§3.1 do [AGENTS.md](../../AGENTS.md) — sem terceira rodada).
- **Escopo auditado:** delta `origin/main..HEAD` (10 commits, `383d422..95f9785`) da branch
  `feat/dl-066-portas-e-indireto` — a etapa 2 do fecho da fatia 1 da
  [DL-066](../planos/DL-066-dfc.md): porta de classificação da conta (três campos, trava e
  trilha), guarda de período fechado da DL-065 estendida, método indireto com os ajustes do
  item 20, API GET/PATCH, telas da DFC e de classificação, e as guardas derivadas.
- **Data:** 06/10/2026. **Motor de execução:** Python 3.14 / SQLite (PostgreSQL local bloqueado
  por política — ver §5). Toda evidência abaixo é saída real de comando executado por este
  auditor; a suíte do produto roda 65 testes DL-066 e todos passam no estado entregue.

## 1. Veredito

**APROVADO COM RESSALVAS** — os oito critérios 14–21 fecham por execução e o caso de
referência fecha ao centavo nos dois métodos, mas a correção única precisa fechar uma
guarda cega do PATCH parcial (GRAVE: a mutação destrutiva sobrevive ao teste que diz
protegê-la), a colisão 20(a)×20(b) que torna inemitível o livro com provisões classificadas
pela própria ajuda do produto, e três caminhos declarados e não medidos (permissões das
portas novas, a trava de concorrência e a escrita dos três campos no cadastro inicial).

## 2. Critérios 14 a 21 — verificados por execução

Comando-base (executado 3× nesta auditoria, sempre com o mesmo resultado):

```powershell
$env:DATABASE_URL = "sqlite:///C:/Users/conta/OneDrive/Área de Trabalho/Harness/.dsh-tmp/dataledger-auditoria.sqlite3"
$py = "C:\Users\conta\OneDrive\Área de Trabalho\Harness\DataLedger\.venv\Scripts\python.exe"
& $py -m pytest apps/contabilidade/tests/test_dl066_dfc.py apps/contabilidade/tests/test_dl066_classificacao.py `
    apps/contabilidade/tests/test_dl066_indireto.py apps/contabilidade/tests/test_dl066_api.py `
    apps/contabilidade/tests/test_dl066_tela_dfc.py -q
```

Saída: `65 passed, 43 warnings in 13.25s` (os warnings são o `RuntimeWarning` esperado de
degradação de lock em SQLite). Contagem por arquivo: `test_dl066_dfc.py` 20 passed,
`test_dl066_classificacao.py` 10 passed, `test_dl066_indireto.py` 9 passed,
`test_dl066_api.py` 11 passed, `test_dl066_tela_dfc.py` 15 passed.

| # | Critério | Como foi medido (comando → saída real) | Resultado |
| --- | --- | --- | --- |
| 14 | Classificação grava com trava, trilha antes/depois e recusa de período fechado (encerrada e entregue) com mensagem verdadeira | `pytest test_dl066_classificacao.py -q` → `10 passed`; `test_classifica_os_tres_campos_e_registra_antes_e_depois` mede a trilha `{antes, depois}` só do que mudou; `test_competencia_entregue_nao_manda_reabrir...` proíbe a frase "reabra a competência" em competência entregue e exige a orientação de ajuste; a mutação M1 (guarda desligada) derrubou **8 testes** (ver §4) | **Verificado** (ressalva A4 sobre a trava de concorrência) |
| 15 | A recusa vale pelo caminho validado do admin (regra em `Conta.clean()`) | `test_o_full_clean_puro_tambem_recusa_e_carrega_o_codigo_da_dl065` → passed, com `CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO` no erro; sonda do auditor no `ModelForm` real do `ContaAdmin` (clone descartável): `form.is_valid(): False`, erro com "03/2026 ... encerrada", e os três campos **visíveis** no formulário | **Verificado** (ressalva B2: o teste do produto cobre `full_clean()`, não o formulário do admin como o DL-065 fez) |
| 16 | Caso de referência fecha ao centavo no indireto, com `confere = True` | `test_criterio16_o_caso_de_referencia_fecha_no_indireto_ao_centavo` → passed: `lucro_liquido 90000.00`, `total_dos_ajustes -5000.00`, `fluxo_operacional 85000.00` = `pelo_direto 85000.00`, `diferenca 0.00`, `confere True`, caixa `40000.00 → 105000.00`, `pode_emitir True` | **Verificado** |
| 17 | As três famílias do item 20 nomeadas, com sinal; zeramento não contamina | `test_criterio17_familia_20a/20b/20c` + `test_criterio17_o_zeramento...` + `test_precedencia_o_20b_vem_antes_do_20c` → all passed; sinais conferidos contra a regra do plano (ativo operacional `−`, passivo `+`, depreciação `+`, item de investimento/financiamento `−`); a mutação M5 (zeramento incluído) derrubou o teste do critério 17 **e** 2 testes da DRE | **Verificado** (ressalva A2 sobre a colisão 20(a)×20(b)) |
| 18 | Identidade que não fecha veta (`indireto_nao_fecha`) e nomeia a diferença | `test_criterio18_a_identidade_que_nao_fecha_veta_e_nomeia_a_diferenca` → passed (`diferenca 10000.00` nomeada, `pode_emitir False`, `diferenca_de_caixa` sem pendência — nenhum saldo calibrado); a mutação M9 (veto removido) derrubou 2 testes | **Verificado** |
| 19 | API GET e PATCH espelham as irmãs, 409 em período fechado, isolamento entre empresas | `pytest test_dl066_api.py -q` → `11 passed`: GET 200 com o contrato da tela (dinheiro em texto), GET 409 com o corpo inteiro e motivo nomeado, GET 400 fora da faixa, GET e PATCH isolados (`403/404` e `404` para empresa/conta alheia — nunca o dado), PATCH 409 sem gravar nem registrar em período fechado, corpo malformado 400, chave fora do contrato recusada por nome | **Verificado**, com **ressalva GRAVE A1** (PATCH parcial: ver §3) |
| 20 | Tela da DFC obedece o veredito, não imprime na recusa, traz identificação e não tem valor por ação (52A) | `pytest test_dl066_tela_dfc.py -q` → `15 passed`; `test_quando_o_veredito_veta...` (3 vetos parametrizados) mede que na recusa não há `tabela-dfc`, `identificacao-do-documento`, `carimbo`, `valor-monetario` nem trecho da demonstração; `test_nenhum_trecho_de_valor_por_acao...` varre o HTML inteiro dos dois desfechos; bloco de identificação com razão social, "Demonstração dos Fluxos de Caixa", "Valores em Real (R$)" e "período de 01/01/2026 a 31/03/2026"; a mutação M7 (tela ignorando o veto) derrubou 5 testes | **Verificado** |
| 21 | Telas novas no universo de telas; navegação presente; lint, formatação, check e migrações limpos | `pytest test_dl024_atalhos_e_acessibilidade.py -k "toda_rota_do_produto or acessivel_nos_atalhos"` → `15 passed` (universo cobre `dfc` e `conta_classificacao_dfc`); `test_toda_pendencia_da_dfc_tem_titulo_no_servico_e_acao_na_tela` → passed; `ruff check .` → `All checks passed!`; `ruff format --check .` → `365 files already formatted`; `manage.py check` → `System check identified no issues`; `makemigrations --check --dry-run` → `No changes detected`; `validate-docs.ps1` → `Documentação válida: 227 arquivos Markdown verificados` | **Verificado** |

Regressão dos critérios 1–13 (fatia 1) e reflexos cruzados: `pytest apps/contabilidade -q`
→ `68 failed, 1839 passed, 33 skipped in 316.59s`. As 68 reprovações são todas da linha de
base declarada do motor (Chromium, threads/concorrência, constraints do SQLite): os nomes
batem com as classes declaradas, e **23 deles foram reproduzidos idênticos** num checkout de
`origin/main` (`test_dl034_*` 14, `test_dl038_identificacao_cpf` 2, `test_dl023_*` 2,
`test_dl030` 1, `test_dl032` 1, `test_dl043_zeramento_referencia` 1 e os demais já nomeados
como ambiente). DLPA, DMPL, DRE e Balanço não ganharam nenhuma reprovação nova; os testes de
`ContaSerializer`/cadastro de conta (`test_api.py`, `test_dl023_*`) seguem na mesma linha de
base de `origin/main`. `test_documentacao_do_estado.py` → `19 passed`.

## 3. Achados

### A1 — GRAVE — o teste que diz proteger o PATCH parcial não mede nada (mutação destrutiva sobrevive)

**Evidência.** `apps/contabilidade/tests/test_dl066_api.py:188-204`
(`test_patch_parcial_nao_mexe_no_que_nao_veio`) PATCHa apenas `{"classificacao_dfc": INVEST}`
sobre o cenário `patch-parcial`, em que `caixa_e_equivalentes` **e**
`item_de_resultado_sem_caixa` já são `False` — exatamente o valor que o código destrutivo
escreveria. Mutação aplicada em clone descartável
(`.dsh-tmp/mut-dl066/apps/contabilidade/views.py`, trecho de
`ContaClassificacaoDfcView.patch`, linhas 2315/2318/2321):

```text
entrada.validated_data.get("caixa_e_equivalentes", False)        # era conta.caixa_e_equivalentes
entrada.validated_data.get("classificacao_dfc", None)            # era conta.classificacao_dfc
entrada.validated_data.get("item_de_resultado_sem_caixa", False) # era conta.item_de_resultado_sem_caixa
```

Comando: `pytest apps/contabilidade/tests/test_dl066_api.py -q` sobre a mutação.
Saída: **`11 passed, 3 warnings in 2.32s`** — nenhuma reprovação. Ou seja: se um refator
amanhã fizer o PATCH destruir o que não veio (apagar a marca de caixa e o marcador de item
sem caixa em silêncio), a suíte inteira continua verde e o cliente perde classificação sem
aviso. A enumeração estática confirma que este é o teste ÚNICO que exercita a fusão do PATCH
(`grep classificacao-dfc` em `apps/`: só `test_dl066_api.py` e a varredura de livro-caixa, que
recusa antes da fusão).

**O que a correção precisa garantir para não voltar:** o cenário do teste precisa partir de
estado em que os campos ausentes tenham valores **diferentes** dos defaults destrutivos (por
exemplo uma conta com `caixa_e_equivalentes=True` e/ou `item_de_resultado_sem_caixa=True`),
asserter a sobrevivência dos dois **e** que a trilha registre somente o campo enviado; e a
reconferência precisa reexecutar esta mutação e colher reprovação.

### A2 — MÉDIO — a derivação do indireto ajusta o mesmo fato DUAS vezes em provisões, e o livro fica inemitível com as marcações que o próprio produto recomenda

**Evidência (execução).** Sondas do auditor em clone descartável
(`.dsh-tmp/mut-dl066/apps/contabilidade/tests/test_zz_auditoria_probe.py`), cenário: despesa
de provisão 10.000,00 marcada `item_de_resultado_sem_caixa` (é o que o `help_text` manda —
`apps/contabilidade/models.py:1156`: *"depreciação, amortização, **provisões** e semelhantes
entram no ajuste do método indireto"*) contra "Provisões a Pagar" (passivo
`classificacao_dfc=operacional` — é o que a tabela de derivação do plano,
`docs/planos/DL-066-dfc.md:441-446`, manda para "contas a pagar operacionais"):

```text
[PROBE provisao-dois-lados] {'lucro_liquido': '-10000',
 'ajustes': [('20(a)', '2.3', '+', '10000'), ('20(b)', '5.5', '+', '10000')],
 'total_dos_ajustes': '20000', 'fluxo_operacional': '10000', 'pelo_direto': '0',
 'diferenca': '10000', 'confere': False}
[PROBE provisao-dois-lados] pode_emitir: False
[PROBE provisao-paga mes=4] confere: False ... pode_emitir: False   # mesmo depois de PAGA em caixa
[PROBE provisao-paga-20a mes=4] ajustes: [] confere: True pode_emitir: True  # só sem o marcador 20(b)
```

Ou seja: um fato contábil trivial (provisão/accrual) classificado exatamente como a ajuda do
produto e a tabela do plano recomendam ajusta o mesmo fato duas vezes (20(b) pela despesa e
20(a) pelo passivo), a identidade nunca fecha — nem antes nem depois do pagamento — e a DFC
**não emite**. A única saída é **deixar de seguir** o `help_text` (desmarcar o item sem caixa
e usar só a variação do passivo). O docstring de `_apurar_operacional_indireto`
(`apps/contabilidade/services.py:6249`) afirma *"cada conta em exatamente UMA delas — o
princípio que sustenta a identidade é que cada fato contábil é ajustado UMA vez"*, e essa
frase é falsa neste caso. A pendência diz "confira as marcações", quando as marcações estão
certas segundo a documentação do próprio produto. O teste `test_criterio18_...`
(`test_dl066_indireto.py:377-415`) consolida o cenário como "marcação dupla = erro do
usuário", e o limite "marcação dupla vira veto" **não está registrado no plano nem no
estado** (grep por "dupl"/"uma vez" em `docs/planos/DL-066-dfc.md` → sem ocorrências): só em
comentário de código e docstring de teste.

**O que a correção precisa garantir para não voltar:** ou a derivação passa a ajustar cada
fato UMA vez (ex.: excluir de 20(a) o efeito já capturado por 20(b)/20(c), ou o inverso) e o
cenário de provisão com passivo operacional fecha e emite; ou o Fred ratifica a convenção
"um marcador por fato" como decisão de produto, registrada no plano (seção de limites), no
`help_text` de `item_de_resultado_sem_caixa` e no texto da pendência, que passa a nomear a
convenção em vez de mandar o contador procurar erro onde não há. A reconferência precisa
reexecutar os três cenários da sonda (provisão não paga, paga no mês seguinte, e sem o
marcador) e confirmar qual dos dois caminhos foi adotado.

### A3 — MÉDIO — as quatro portas novas não têm teste de permissão; a mutação que remove as permissões derruba zero testes

**Evidência.** Comportamento está certo (sonda do auditor, papel CLIENTE): `GET api dfc: 403`,
`PATCH api classificacao: 403`, `GET web dfc: 403`, `GET web classificacao: 403`, `POST web
classificacao: 403`, e nada gravado. Mas a mutação M8 — `permission_classes = []` em
`DfcView` e `ContaClassificacaoDfcView` (`apps/contabilidade/views.py:2249, 2301`) e
`if False:` no `_pode_ler`/`_pode_escriturar` de `dfc` e `conta_classificacao_dfc`
(`apps/contabilidade/views_web.py:1478, 6278`) — rodada contra
`test_dl066_api.py + test_dl066_tela_dfc.py + test_dl038_recusa_livro_caixa.py` deu
**`76 passed, 14 warnings in 9.73s`**. Nenhum teste do produto exige CLIENTE 403 nas portas
novas (os docstrings das views **afirmam** "CLIENTE nunca lê (403)" — afirmação sem medição).

**O que a correção precisa garantir para não voltar:** testes de CLIENTE (e anônimo) nas
quatro rotas novas, assertando 403/404 e nada gravado, no molde de
`test_dl048_d8_api_da_dlpa.py`; a mutação de remoção das permissões precisa reprovar.

### A4 — MÉDIO — a trava `select_for_update()` da porta de classificação é afirmada e nunca medida (nem na CI); a mutação que a remove derruba zero testes

**Evidência.** O docstring de `classificar_conta_na_dfc`
(`apps/contabilidade/services.py:6174`) afirma: *"CORRIDA: `select_for_update()` antes de ler
os valores gravados — duas classificações concorrentes da MESMA conta serializam"*. A mutação
M10 (trocar `Conta.objects.select_for_update()` por `Conta.objects` na função) rodada contra
`test_dl066_classificacao.py + test_dl066_api.py + test_dl066_tela_dfc.py` deu
**`36 passed, 21 warnings in 8.20s`**. Não existe teste de corrida para esta porta em lugar
nenhum — nem o de threads que a irmã DRE tem (`test_dl045_dre.py::
test_r4_corrida_na_classificacao_serializa_e_a_trilha_fica_coerente`, que roda na CI e morre
na linha de base local por ser concorrência). A afirmação de concorrência vale, portanto,
como código — não como garantia medida.

**O que a correção precisa garantir para não voltar:** espelhar o teste R4 da DRE para a
porta da DFC (execução de prova na CI; localmente cai na linha de base de concorrência e isso
é limite, não reprovação), ou reescrever o docstring para dizer que a serialização é
pretensão de código sem medição. A mutação de remoção da trava precisa reprovar na CI.

### A5 — MÉDIO — os três campos são `read_only` no cadastro: dado enviado é ignorado em silêncio, contra a decisão D2 que o Fred tomou para o campo irmão

**Evidência.** `apps/contabilidade/serializers.py:145-149` marca os três campos
`read_only_fields`, enquanto `classificacao_dmpl` (linhas 114-129) é **gravável** por decisão
D2 da DL-063, *"decisão do Fred em 04/10/2026"*, com o motivo literal: *"quem integrava por
API não tinha porta nenhuma para dizer em que coluna a conta entra — a porta própria
reclassifica conta EXISTENTE, e não serve para quem está criando a conta"*. O mesmo argumento
vale palavra por palavra para os três campos da DFC, e o plano promete a API como *"espelho
exato dos endpoints da DMPL"* (`docs/planos/DL-066-dfc.md:414-415`). Sonda do auditor:
`ContaSerializer(data={"caixa_e_equivalentes": True, ...})` → `is_valid()` sem nenhum erro
nos três campos — DRF **descarta em silêncio** o que veio (a classe de defeito que o projeto
chama BL-196: "dado enviado nunca é ignorado em silêncio"). O comentário do serializer (linhas
139-140) ainda é ambíguo: *"A extensão da escrita ao cadastro inicial é a decisão D2 da
DL-063 aplicada a estes campos — fica declarada, não escondida"* — frase que descreve a
decisão oposta à que o código implementa.

**O que a correção precisa garantir para não voltar:** decidir com o Fred (ou D2 por paridade
— escrita no cadastro inicial com as coerências completas replicadas, como a DL-063 fez —,
ou recusa explícita da chave quando enviada, nunca descarte mudo); registrar a decisão em
`docs/projeto/decisoes.md`/backlog; corrigir o comentário para dizer o que o código faz.

### A6 — BAIXO — registro: BL-629 já corrigida mas "aberta" no backlog; data do cabeçalho da etapa 2; estado.md ainda promete o que esta etapa entregou

**Evidência.** `docs/projeto/backlog.md:2163` registra a BL-629 como `aberta`, mas esta etapa
já corrigiu exatamente o que ela pede (lista explícita de chaves em
`test_dl066_dfc.py:307-317`, comentário citando a BL-629). O cabeçalho da etapa 2 no plano
(`docs/planos/DL-066-dfc.md:381`) diz "(10/10/2026)" enquanto os 10 commits são de 06/10/2026
(`git log --format='%h %ad'` → `383d422 06/10/2026 10:26` … `95f9785 06/10/2026 15:45`) —
data que não é a da execução. E `docs/agents/estado.md` (seção Próximo passo) ainda diz que
*"Falta para a fatia fechar: o serviço de classificação da atividade com trilha, a tela, a API
e a apresentação do método indireto"* — o que esta etapa entrega; a atualização do estado é
etapa obrigatória da entrega (CLAUDE.md) e não está neste delta. Nenhum "verde" sem execução
foi encontrado: a seção de evidências do plano não afirma execução desta etapa, e as
afirmações da fatia 1 conferem (`7c0eae7` existe no repositório). A BL-630 está registrada e
aberta com "decisão do Fred" (`backlog.md:2164`) ✓.

**O que a correção precisa garantir para não voltar:** fechar a BL-629 no backlog, corrigir a
data do cabeçalho e atualizar `estado.md` na entrega (a reconferência confere os três).

### B1 — BAIXO — critério 15 coberto por `full_clean()` puro; o precedente do DL-065 testava o formulário do admin

**Evidência.** `test_dl066_classificacao.py:329-357` chama `full_clean()` direto; o DL-065
tinha `_formulario_do_admin` (`test_dl065_portas.py:156-204`) com o `ModelForm` real do
`ContaAdmin`, mais a guarda de o campo continuar **visível**. O comportamento está certo
(sonda do auditor no `ModelForm` real: recusa com a mensagem verdadeira e os três campos
presentes), mas a proteção contra uma regressão do admin não está na suíte.

**O que a correção precisa garantir para não voltar:** um teste no molde do
`_formulario_do_admin` para os três campos, incluindo visibilidade.

## 4. Mutações em memória (executadas em clone descartável; o repositório auditado não foi tocado)

| # | Mutação imaginada | Testes que a matam (saída real) |
| --- | --- | --- |
| M1 | Guarda de período fechado dos três campos desligada em `Conta.clean()` | **MORTA** — 8 reprovações: 5 em `test_dl066_classificacao.py` (trocar atividade, competência entregue, desmarcar caixa, desmarcar item, descendente), + `test_o_full_clean_puro...`, + `test_patch_responde_409...` e `test_classificacao_em_periodo_fechado...` |
| M2 | Sinal trocado em 20(b) e 20(c) (`-creditos_menos_debitos` → `creditos_menos_debitos`) | **MORTA** — 10 reprovações (critério 16 ×2, 20(b), 20(c), precedência, critério 18 e 4 de tela) |
| M3 | Sinal trocado em 20(a) | **MORTA** — 9 reprovações (critério 16 ×2, 20(a), critério 18 e 5 de tela) |
| M4 | Precedência invertida (20(c) antes de 20(b)) | **MORTA** — `test_precedencia_o_20b_vem_antes_do_20c` reprova |
| M5 | Exclusão do zeramento removida do agregador de movimento | **MORTA** — `test_criterio17_o_zeramento_do_resultado_nao_contamina_nenhuma_familia` + 2 testes da DRE (`test_criterio3_dre_de_mes_zerado...`, `test_a10_totais_da_dre_conciliam...`) |
| M6 | PATCH parcial destrutivo (campo ausente vira default) | **SOBREVIVE** — `11 passed` em `test_dl066_api.py` (achado A1) |
| M7 | Tela da DFC ignora o veredito (`if not emissao["pode_emitir"]` → `if False`) | **MORTA** — 5 reprovações (3 vetos parametrizados, link de correção, ponte) |
| M8 | Permissões removidas das 4 portas novas (API e tela) | **SOBREVIVE** — `76 passed` (achado A3) |
| M9 | Veto `indireto_nao_fecha` nunca emitido | **MORTA** — `test_criterio18_...` e o veto de tela correspondente |
| M10 | Trava `select_for_update()` removida de `classificar_conta_na_dfc` | **SOBREVIVE** — `36 passed` (achado A4) |

## 5. O que não pôde ser medido (e por quê)

- **Concorrência real.** PostgreSQL local bloqueado por Controle de Aplicativo do Windows
  (registro do projeto desde 05/10/2026); SQLite degrada o lock para leitura em memória
  (`RuntimeWarning` esperado, citado até no cabeçalho do teste). A trava de
  `classificar_conta_na_dfc` e a corrida com o fechamento de competência não são medíveis
  nesta máquina; a prova é da CI. **É limite declarado, não achado** — o achado A4 é outra
  coisa: nem sequer existe teste de corrida escrito para esta porta.
- **Navegador real (Chromium) e a bateria de identificação do emitente.** Fora do alcance
  local (falhas de frontend na linha de base); o template da DFC tem o bloco de
  identificação medido pelos testes de renderização, não pelo navegador real.
- **CI e PR desta etapa.** A branch está **apenas local** (`git branch -vv` →
  `feat/dl-066-portas-e-indireto ... [origin/main: ahead 10]`, sem upstream): push, PR e
  checks desta etapa **ainda não existem** e nada os afirma — a evidência de CI citada no
  plano (run `37386866890`, commit `7c0eae7`, hash verificado como existente) é da fatia 1.
  Push/PR/CI são pendência do ciclo de entrega (AGENTS.md §5), conferida na reconferência.
- **Suíte completa em PostgreSQL.** `apps/contabilidade` completo foi rodado em SQLite
  (`68 failed, 1839 passed`); as 68 reprovações foram conferidas contra `origin/main` e/ou
  nomeadamente classificadas na linha de base (§2). `apps/core` e `apps/documentos` não
  foram rodados inteiros nesta auditoria (exceto `test_documentacao_do_estado.py`).

## 6. Limites do próprio instrumento de auditoria

- As **mutações não foram "em memória"** no sentido estrito: rodaram em um clone descartável
  em `.dsh-tmp/mut-dl066` (o repositório auditado permaneceu intacto — `git status` limpo ao
  final). A lista de mutações é a que este auditor imaginou; outras mutações plausíveis não
  testadas podem sobreviver.
- As **sondas** (cenário de provisão, CLIENTE, formulário do admin, descarte do serializer)
  são instrumento meu, não versão do produto: comprovam comportamento hoje, mas nada as
  impede de regredir amanhã — por isso elas viram exigência de correção nos achados.
- Não verifiquei adequação **normativa** das famílias do item 20 além da coerência interna,
  do caso de referência e da contradição demonstrada em A2: qual a derivação contábilmente
  canônica para provisões é juízo do contador responsável (Fred), não desta auditoria.
- Não avaliei integração com PostgreSQL real, migrações em base anterior, desempenho sob
  volume, nem os módulos fora do delta (Fiscal, DLPA/DMPL além das suítes rodadas, DRE além
  do impacto cruzado).
- Não li os manuais do sistema de referência; o caso de referência foi conferido contra a
  tabela do plano e os números calculados à mão ali (90.000,00 / 15.000,00 / (20.000,00) /
  85.000,00 / (30.000,00) / 10.000,00 / 65.000,00 / 40.000,00 / 105.000,00), que fecham ao
  centavo nos dois métodos.
- Rodada única (§3.1): os achados acima estão escritos para que **uma única correção** os
  feche; a etapa seguinte é a **reconferência**, e ela precisa conferir exatamente: (A1) a
  mutação M6 reprova; (A2) os três cenários de provisão da sonda e a decisão registrada no
  plano/`help_text`/mensagem; (A3) a mutação M8 reprova com os testes de CLIENTE novos;
  (A4) a mutação M10 reprova na CI (ou o docstring foi reescrito); (A5) a decisão D2
  registrada e o descarte mudo eliminado; (A6) BL-629 fechada, data corrigida e `estado.md`
  atualizado; (B1) o teste do formulário do admin existe.
