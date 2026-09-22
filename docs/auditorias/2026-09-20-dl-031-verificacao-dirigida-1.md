# Verificação dirigida da DL-031 (fatia 2) e das ressalvas BL-463 a BL-468 — rodada 1

> **Nota do `arquiteto-senior`, e é só esta:** relatório do `auxiliar-verificacao`,
> preservado **integralmente**. Eu não edito, não suavizo e não omito achado
> nenhum.
>
> ⚠️ **O achado bloqueador é o retorno exato da [DE-055](../projeto/decisoes.md):**
> *correção de concorrência é onde defeito novo nasce*. O defeito **não** está na
> tela nem na regra contábil — está **no caminho de erro da própria correção que
> fechou o BL-463**, e nenhum dos 2.006 testes o alcançava. Foi encontrado porque
> eu pedi explicitamente um eixo que nenhum dos dois relatórios tivesse
> discutido.
>
> O encaminhamento está em [`docs/agents/estado.md`](../agents/estado.md) e no
> [backlog](../projeto/backlog.md), **não** aqui dentro.

---

**Revisão verificada:** `0e6651f` (`claude/accounting-agent-team-setup-mn6lyf`)
**Data:** 2026-09-20 · **Verificador:** `auxiliar-verificacao` · **Nível de risco:** 2 (§3.1 do [AGENTS.md](../../AGENTS.md))
**Plano:** [DL-031](../planos/DL-031-fatia-2-a-tela-do-fechamento.md), os oito critérios de aceite.

## Parecer em uma frase

A tela do fechamento (DL-031) atende aos oito critérios do plano com testes reais e passa em toda a bateria de não-regressão que eu mesmo rodei — mas achei um **bloqueador reproduzível e não coberto por nenhum teste**: sob a concorrência real que o BL-463 foi criado para tornar segura, a tradução do estouro de `lock_timeout` quebra e vaza um erro cru de banco (nunca `CompetenciaOcupada`), violando diretamente o critério 5 ("nunca 500") — a etapa não deve fechar até isso ser corrigido.

Ambiente usado: banco próprio (`verif_dl031_v2`, criado e depois apagado por mim), commit `0e6651f`, branch `claude/accounting-agent-team-setup-mn6lyf`.

---

## V1 — Os oito critérios do plano

**Testado.** Rodei os dois arquivos de teste relevantes juntos:

```
pytest -q apps/contabilidade/tests/test_dl031_fechamento_de_competencia.py apps/contabilidade/tests/test_dl016_fatia1_fechamento_reabertura_entrega.py
→ 74 passed in 6.29s
```

Li cada teste do arquivo novo (`apps/contabilidade/tests/test_dl031_fechamento_de_competencia.py`, 562 linhas) e confirmo que cada um dos 8 critérios tem teste nomeado que o exercita:

- **Critério 1**: `test_criterio1_analista_forcando_a_acao_recebe_403_e_banco_intacto` — asserta `resposta.status_code == 403` **e** `competencia.estado == EstadoCompetencia.ABERTA` (banco, não só o código). Confere.
- **Critério 2**: `test_criterio2_painel_bloqueia_o_link_de_fechar_e_aponta_para_a_conferencia` — com lote desbalanceado, `">Fechar<" not in corpo` e o link da Conferência aparece. Confere.
- **Critério 5**: cada recusa (`fechar`/`reabrir`/`entregar`) tem par negativo+`test_..._controle_positivo_...` no mesmo cenário (ex.: `test_criterio5_post_fechar_com_lote_desbalanceado_recusa_em_portugues_sem_500` + `test_criterio5_controle_positivo_post_fechar_sem_lote_desbalanceado_funciona`). O controle positivo de fato fecha (`status_code == 302`, `estado == ENCERRADA`) — se a tela quebrasse ele reprovaria. Confere.
- Critérios 3, 4, 6, 7, 8: também com teste nomeado e passando.

## V2 — BL-463 (a ordem RC-58/lock)

**Testado, com achado.** Confirmei por leitura de `apps/contabilidade/services.py` que a checagem `localizar_lotes_desbalanceados(...)` roda **antes** de `_travar_competencia_para_transicao` em `encerrar_competencia` (linhas ~1030–1045), e que a recusa continua de pé sem lock: `test_bl463_fechar_com_lote_desbalanceado_continua_recusando_sem_lock` (passou). **RC-58 continua recusando** — não foi afrouxado.

Não refiz a comparação exata "1,73s → ~20ms" (exigiria recriar a versão antiga do código para a metade "antes"), mas medi a ordem de grandeza da janela **atual** do lock diretamente, com duas conexões PostgreSQL reais (thread A segura `FOR UPDATE` por 3s; thread B chama `encerrar_competencia` concorrente):

```
RESULTADO: {'segurando': True,
 'encerrar_resultado': 'CompetenciaTravadaPorOutraOperacao: A competência 01/2030 ... não foi possível travá-la a tempo...',
 'encerrar_duracao': 1.2303243879998718}
```

A duração bate com `lock_timeout=1210ms`, confirmando que a janela do lock em `encerrar_competencia` hoje é mínima (estoura no próprio timeout, não em segundos de varredura) — consistente com a alegação do desenvolvedor.

## V3 — `lock_timeout` de 1210ms

**Testado, achado BLOQUEADOR.**

1. Confirmei que está em vigor na conexão: `SHOW lock_timeout` → `1210ms`.
2. Confirmei detecção por SQLSTATE, nunca texto: `apps/contabilidade/services.py:427-437`, função `_e_estouro_de_lock_timeout`, compara `causa.sqlstate == "55P03"`. Inspecionado, correto.
3. **No caminho `encerrar_competencia`/`reabrir_competencia`/`marcar_competencia_como_entregue` (`_travar_competencia_para_transicao`), o estouro vira `CompetenciaTravadaPorOutraOperacao` com mensagem legível — confirmei na prática (medição acima).**
4. **No caminho `criar_lancamento` (`_travar_competencia_em_modo_compartilhado`) — que é exatamente o ponto medido no achado B1 original, 1,73s de espera — a tradução QUEBRA.** Reproduzi duas vezes, sob concorrência real (thread segurando `FOR UPDATE`, thread tentando `criar_lancamento`):

   - Direto no serviço:
     ```
     'lancar_resultado': 'OUTRA EXCECAO (InternalError): current transaction is aborted, commands ignored until end of transaction block'
     'lancar_duracao': 1.227s
     ```
   - Pela API real (`Client().post(".../lancamentos/")`, DRF), a exceção sobe **sem ser capturada** pelo `except CompetenciaEncerrada` de `apps/contabilidade/views.py:727`, porque `django.db.utils.InternalError` não é subclasse dela — vira exceção não tratada na view, o que em produção é **HTTP 500 cru**, não a mensagem em português que o critério 5 exige.

   **Causa raiz, com linha exata:** `apps/contabilidade/services.py:453`

   ```python
   raise CompetenciaOcupada(
       f"A competência {competencia.mes:02d}/{competencia.ano} de "
       f"{competencia.empresa} está sendo fechada por outra operação "   # <-- linha 453
       ...
   ) from exc
   ```

   `competencia.mes`/`competencia.ano` são campos escalares já carregados (ok), mas `competencia.empresa` é uma FK **não cacheada** neste objeto (veio de `obter_ou_criar_competencia`, que usa `get_or_create(empresa=empresa, ...)` — isso não popula o cache da relação). Acessá-la dispara uma nova consulta SQL — que falha, porque a transação Postgres já está **abortada** pelo próprio estouro do `FOR SHARE` (nenhum savepoint isola essa consulta). O `except OperationalError` correto já tinha sido executado; é a **construção da mensagem de erro** que gera uma segunda falha e substitui `CompetenciaOcupada` por um `InternalError` cru.

   **Gravidade: BLOQUEADOR.** Acontece exatamente no cenário de concorrência normal do escritório (fechar o mês enquanto alguém lança), é o ÚNICO ponto que a medição original do achado B1 mediu, e nenhum teste no repositório cobre esse caminho — busquei `lock_timeout|55P03|CompetenciaOcupada|CompetenciaTravadaPorOutraOperacao` em `apps/` e só há ocorrências em `services.py`/`settings.py` (produção), nenhuma em teste. A suíte inteira (2006 passed) não pega isso porque nenhum teste simula o lock_timeout estourando no caminho de `criar_lancamento`.
   **Responsável:** `desenvolvedor-pleno` (arquivo é dele nesta etapa, `services.py`).
   **Correção sugerida (não fiz, não tenho Edit):** capturar `competencia.mes`/`competencia.ano`/`empresa` (o parâmetro já em memória, como `_travar_competencia_para_transicao` já faz) em vez de reacessar `competencia.empresa` depois do erro — mesmo padrão que já funciona no outro lock.

## V4 — Critério 7 (tabulação e contraste)

**Testado (Chromium real, 1280×800, Playwright).**

**Contraste:** medi todos os elementos de texto visíveis nas quatro telas (`fechamento`, `fechar`, `reabrir`, `entregar`) com a mesma fórmula WCAG do `scripts/juiz.py` (luminância relativa + composição de fundo por alfa). Corrigi um bug do meu próprio script no caminho (eu compunha o fundo a partir do elemento-PAI, não do próprio elemento — produzia falsos ~1:1 em botões; corrigido para bater com `fundoComposto(el)`, igual ao `juiz.py`). Depois da correção: **zero elementos abaixo do piso** (4,5:1 texto / 3:1 grande). Mínimo real encontrado: **5,14:1**; máximo: **16,37:1**. E os dois números específicos que o frontend citou **batem exatamente** com os que medi nos mesmos elementos: "Encerrada" (texto de estado) = **7,38:1**; H2 "Esta é a única ação desta tela..." (tela de entrega) = **14,58:1**. Confirma a alegação.

**Tabulação:** medi, célula a célula, a largura de `111111` vs `888888` na MESMA fonte computada de cada célula com dígito. Nas quatro telas, todo conteúdo numérico (datas, "02/2026", "20/09/2026 19:46") sai com `w1 == w8 == 48px` — mas usando `IBM Plex Serif` com `font-variant-numeric: normal`, **não** o token `--fonte-numerica`/`.valor-monetario`. Ou seja: os dígitos ficam alinhados por **coincidência da métrica da fonte serifada**, não por aplicação deliberada da régua de tabulação. **Não consegui reproduzir o número exato "57,796875px"** em nenhum elemento presente nas quatro telas — nenhuma delas carrega a classe `.valor-monetario` nem o `--fonte-numerica` em conteúdo de dado; esse número provavelmente veio de um teste isolado do token CSS, não do conteúdo da página. **Não testado** esse número específico, por falta do elemento que o produziu.

**Sobre a declaração honesta do frontend** ("esta tela não exibe valor monetário, a régua não se aplica diretamente"): **verifiquei e é verdadeira e consistente com o projeto**, não só uma alegação. O próprio instrumento de auditoria do produto (`scripts/juiz.py`, regex `PADRAO_VALOR = re.compile(r"_ptbr\b")` combinada com `/\d[\d.]*,\d{2}/` para células) só cobra tabulação de valores com **vírgula decimal** (formato monetário) — datas são **explicitamente isentas por desenho** (comentário do próprio arquivo: "Nem todo `_ptbr` é dinheiro — data também usa"). E as telas de referência já auditadas (Diário, Razão, Balancete) também **não** aplicam `.valor-monetario` às suas colunas de data (`<td>{{ item.data|date:"d/m/Y" }}</td>`, sem classe). A alegação do frontend é, portanto, **correta e alinhada com o precedente do produto** — não é uma brecha nova.

## V5 — Não-regressão

**Testado**, todos os números medidos por mim, banco próprio, árvore limpa:

| Comando | Resultado medido |
|---|---|
| `pytest -q` | `2006 passed, 14 skipped, 2 warnings, 4 subtests passed in 96.37s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `209 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced)` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`, exit 0 |
| `python manage.py migrate` (banco vazio) | todas as migrações aplicadas sem erro |

O número de teste bate exatamente com o declarado em `docs/agents/estado.md` ("2006 passed, 14 skipped").

⚠️ Nota sobre `pytest --collect-only -q` isolado (método citado pelo BL-466): ele **sempre** termina em exit 1 nesta árvore, com ou sem mudança do DL-031 — é o mecanismo `BL-218` de `conftest.py` (pré-existente, não introduzido por esta etapa) reprovando porque nenhuma superfície de escrita foi de fato exercitada em modo `--collect-only` (nenhum teste roda de verdade). Confirmei que `conftest.py` já continha esse mecanismo bem antes da DL-031 (`git log` mostra commits anteriores a esta etapa). **Não é regressão desta entrega** — só registro para não ser confundido como tal; o número certo de testes vem da linha "N tests collected", não do código de saída.

## V6 — O que ninguém nomeou

- **Competência fora de faixa** (`ano`/`mes` inválidos) nas rotas da tela: **Testado**. `POST .../fechar/` com `ano=99999,mes=13` → 302 + "Competência inválida" (nunca 500); `GET` com `ano=-5,mes=0` e com `ano=abc,mes=xyz` → 302, nunca 500 ou erro cru.
- **Atalho `Alt+Z`**: **Inspecionado**. Não colide com nenhum outro atalho já definido no produto (P, M, R, C, I, L, K, N). Não testei colisão com atalhos nativos de Firefox/Safari — fora do escopo já declarado pela própria direção de arte ("só Chromium foi testado").
- **Isolamento entre escritórios nas quatro telas**: **Testado parcialmente**. Só o painel (`fechamento`) tem teste explícito de 404 para empresa de outro escritório (`test_isolamento_empresa_de_outro_escritorio_e_404`, passou). As três telas de ação (`competencia_fechar/reabrir/entregar`) usam a **mesma** função compartilhada `_empresa_do_escritorio_ativo` (já validada em outras telas do módulo) — por isso a proteção existe (Inspecionado), mas não há teste automatizado dedicado nas três telas de ação. **Ressalva baixa**, não bloqueia.
- **Duplo clique / reenvio em "marcar como entregue"**: Inspecionado. `marcar_competencia_como_entregue` é **deliberadamente repetível por desenho** (documentado no docstring), então reenvio duplicado não cria duplicidade de estado — apenas atualiza `entregue_em`/`entregue_por` de novo. Não é defeito.

## Achados

1. **BLOQUEADOR** — `apps/contabilidade/services.py:453`, função `_travar_competencia_em_modo_compartilhado`: sob estouro real de `lock_timeout` no caminho de `criar_lancamento` (o cenário exato medido no achado B1/BL-463), a construção da mensagem de `CompetenciaOcupada` acessa `competencia.empresa` (FK não cacheada), dispara nova consulta numa transação Postgres já abortada, e o `InternalError` resultante **substitui** `CompetenciaOcupada` — propaga cru até a view da API (`views.py:727`), que não o captura, resultando em erro não-tratado (500 em produção). Viola o critério 5 do plano DL-031 e o próprio texto do commit BL-463 ("em todo ponto que pode esperar o lock"). Zero cobertura de teste para este caminho. **Responsável: `desenvolvedor-pleno`.**

2. **Ressalva baixa** — as três telas de ação (fechar/reabrir/entregar) não têm teste explícito de isolamento entre escritórios (compartilham função já testada alhures, mas sem teste dedicado nesta fatia). **Responsável: `especialista-frontend`.**

3. **Ressalva baixa** — o número "111111/888888 com 57,796875px" citado pelo frontend não corresponde a nenhum elemento presente nas quatro telas desta fatia (não há conteúdo com `.valor-monetario`/`--fonte-numerica`); não pude confirmar de onde veio. Não é defeito — a alegação central (a régua não se aplica, porque não há valor monetário) está correta e verificada — mas o número específico fica sem procedência rastreável, o que o próprio `docs/projeto/direcao-de-arte.md` (§4.8) trata como lição cara do projeto ("número sem método é opinião com casas decimais"). **Responsável: `especialista-frontend`**, só para registrar a procedência na próxima vez que citar um número.

## O que não consegui medir, e por quê

- A comparação direta "1,73s → ~20ms" do BL-463 como A/B: só medi o "depois" (código atual); o "antes" exigiria reverter a correção, o que está fora do escopo desta verificação dirigida.
- O número exato "57,796875px" de tabulação: nenhum elemento das quatro telas desta fatia carrega o token/classe que produziria esse valor; não encontrei onde reproduzi-lo.
- Colisão de `Alt+Z` com atalhos nativos de Firefox/Safari: esses navegadores não estão disponíveis/testados neste ambiente, e a própria direção de arte já declara esse limite ("só Chromium foi testado").
- Leitor de tela real (NVDA/VoiceOver) sobre as quatro telas: fora do escopo desta verificação e já declarado como limite geral do projeto.

**Alteração na árvore de trabalho:** nenhuma minha. `git status`/`git diff --stat` no fim: árvore limpa. Registro que, no início da minha sessão, `git status` mostrava `docs/projeto/backlog.md` modificado e não-staged (presumivelmente de outro agente concorrente nesta mesma sessão) — eu não toquei nesse arquivo, e ao final ele já não aparecia mais como modificado; não sei explicar a mudança, e não investiguei porque está fora do meu escopo (não tenho Write/Edit e essa mudança não é minha).
