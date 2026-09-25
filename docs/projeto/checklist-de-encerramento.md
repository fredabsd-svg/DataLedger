# Checklist de encerramento de etapa

**Este é o checklist único do projeto.** O [AGENTS.md §14](../../AGENTS.md) aponta
para cá e **não** repete a lista; o
[modelo de pull request](../../.github/pull_request_template.md) também aponta, e
guarda só as caixas que a integração contínua lê.

⚠️ **Por que ele mora FORA do `AGENTS.md`, e o motivo é medido:** o `AGENTS.md`
estava a **20 bytes** da margem de segurança de 30.000 (29.980) quando esta
versão do checklist foi escrita, e a versão longa o levaria a 37.005. O limite
real do Codex CLI — `project_doc_max_bytes` — é **32.768 bytes**, e acima dele a
ferramenta **trunca as regras EM SILÊNCIO**, cortando **primeiro as últimas
seções**, que são justamente "Como estas regras são impostas" e a divisão de
trabalho da equipe. `apps/core/tests/test_agentes_multiplataforma.py` reprova o
build quando a margem é estourada — e reprovou a primeira versão desta mudança,
que é como o risco apareceu.

⚠️ **Repetir lista em dois arquivos foi a causa raiz registrada em 2026-09-13, e
ela reincidiu em 2026-09-25 — ver 14.5. A redação anterior deste checklist era
genérica — "documentação e evidências
atualizadas" — e foi MARCADA como cumprida enquanto o checklist do `README.md`
afirmava que duas etapas integradas na `main` não tinham sido feitas.** Item
vago é item que se marca sem fazer. Cada linha abaixo nomeia **o que conferir** e
**quem impõe**.

**Legenda da coluna "quem impõe":** `teste` = reprova o build · `workflow` =
deixa o PR vermelho · `gancho` = executa antes da primeira ação · `honra` =
ninguém verifica além de você. ⚠️ **Nenhuma delas impede o merge hoje** — leia
"Como estas regras são impostas", no fim do [AGENTS.md](../../AGENTS.md), antes
de confiar em qualquer linha.

### 14.1 Antes de escrever a primeira linha

| # | Confira | Quem impõe |
| --- | --- | --- |
| 1 | `AGENTS.md` lido integralmente, e as instruções das pastas afetadas | `gancho` + `workflow` |
| 2 | Plano `DL-xxx` existe, com **escopo, critérios de aceite e o que está fora** | `workflow` |
| 3 | Cada requisito classificado em **confirmado, hipótese ou pendência** em `docs/projeto/requisitos.md` — e **hipótese nunca apresentada como confirmada** | `honra` |
| 4 | Regra contábil ou normativa **citada em fonte oficial**, com item e data de consulta. Manual de outro produto responde **rotina**, nunca **norma** | `honra` |
| 5 | Critério que toca **fronteira** definida por norma ou documento do projeto **cita o documento e a palavra dele** — *dentro*, *fora*, *em cada página* (DE-072) | `honra` |
| 6 | Recomendação de auditoria que o **próprio auditor declarou não ter testado** entra como **hipótese a medir**, nunca como número a assertar (DE-069) | `honra` |
| 7 | Arquivos de cada frente **disjuntos**, ou execução **em sequência**, ou isolamento real com revisão-base declarada | `honra` |

### 14.2 Enquanto implementa

| # | Confira | Quem impõe |
| --- | --- | --- |
| 8 | Regra do domínio contábil aplicável **virou teste** — precisão monetária exata, débito igual a crédito, rascunho distinto de efetivado, idempotência, período encerrado, isolamento entre empresas | `honra` |
| 9 | **Autorização verificada no servidor**, não só na interface — e o **corpo da resposta assertado**, não apenas o código HTTP (BL-211) | `honra` |
| 10 | Nenhuma regra existe em **duas implementações**; mapa e derivação em vez de lista enumerada (§8, DE-056) | `honra` |
| 11 | Comentário e **docstring** dizem só o que o teste ao lado entrega. ⚠️ **Promessa em docstring já falhou três vezes neste projeto** (DE-058) | `honra` |
| 12 | Teste que guarda **regra contábil** não se corta nem se afrouxa; só muda quando a **regra** mudou, e com o motivo escrito (DE-063) | `honra` |
| 13 | Ao **desligar uma trava**: prova de **comportamento**, um cenário por trava que sobrou, **derivada da estrutura** que as lista. Partição, união e congelamento de chaves provam que a lista está **completa**, nunca que um item está do **lado certo** (DE-071) | `honra` |
| 14 | Dados **sintéticos**. Nenhum segredo, chave, certificado, `.env` real ou dado real de cliente — em código, teste, log ou memória | `honra` |

### 14.3 Ao fechar: evidência, não paráfrase

| # | Confira | Quem impõe |
| --- | --- | --- |
| 15 | `ruff check .` · `ruff format --check .` · `python manage.py check` · `makemigrations --check --dry-run` · `pytest` · `pwsh ./scripts/validate-docs.ps1`. ⚠️ **Nunca `ruff format` sem `--check`** | `teste` + `workflow` |
| 16 | Contagem de testes **antes e depois**, conferida com `--collect-only`, e **toda variação explicada** | `honra` |
| 17 | Verificação que **não pôde** ser executada é declarada como **Não medido** ou **substituto declarado** — substituto não declarado é a mesma falha que medir errado (DE-060) | `honra` |
| 18 | Cada item classificado em **Implementado, Inspecionado, Testado, Não testado, Bloqueado** ou **Fora do escopo**. ⚠️ **Build verde não é prova de correção funcional, e merge não é entrega** (DE-054) | `honra` |
| 19 | Falha **preexistente** registrada, não escondida; falha de **outro agente** isolada e provada como tal | `honra` |
| 20 | Diff completo relido de forma adversarial: arquivo temporário, segredo, linha de teste cortada sem intenção | `honra` |

### 14.4 Git e integração

| # | Confira | Quem impõe |
| --- | --- | --- |
| 21 | `git add` **nunca** com caminho de diretório — arquivo por arquivo (BL-368) | `honra` |
| 22 | **Não commitar trabalho em voo de outro agente** (DE-064). Árvore suja durante trabalho de terceiro é sinal correto, não problema a resolver | `honra` |
| 23 | Quando **duas frentes tocaram o mesmo arquivo**, o commit de integração **declara a procedência** e quem mediu o quê (DE-073) | `honra` |
| 24 | Commit, push, PR com base correta, e **CI conferida no commit mais recente** | `workflow` |

### 14.5 ⚠️ O estado do projeto — a linha que este projeto mais erra

| # | Confira | Quem impõe |
| --- | --- | --- |
| 25 | `docs/agents/estado.md` atualizado. **É a fonte única do estado** | `teste` |
| 26 | **O checklist de etapas do `README.md` confere com a realidade, item por item** — marca `[x]` só para o que está **na branch padrão**, e `[ ]` só para o que **não está**. ⚠️ **Falhou em 2026-09-25: DL-027 e DL-030 estavam integradas e marcadas como não feitas** | `workflow`, **só o atestado** — ver o aviso abaixo |
| 27 | **Nenhum outro arquivo descreve o estado.** Precisando mencioná-lo, aponte para a fonte única | `teste` (parcial) |
| 28 | Achado de auditoria arquivado em `docs/auditorias/` **integralmente** — quem integra **não edita, não suaviza e não omite achado** | `honra` |
| 29 | Todo achado registrado em `docs/projeto/backlog.md` com **identificador, gravidade e dono**; decisão tomada registrada em `docs/projeto/decisoes.md` com o que foi **descartado** | `honra` |
| 30 | Pendência que depende do responsável pelo produto **levada a ele**, nomeada como pendência — depois de consultar manual e fonte oficial (§0) | `honra` |

⚠️ **O item 26 é o único deste checklist cuja falha já foi medida DUAS vezes.**
Desde 2026-09-25 o workflow `Regras do projeto` exige uma caixa **nomeada** para
ele — *"Conferi o checklist de etapas do README contra a branch padrão"* —, para
que marcá-la sem conferir seja uma **afirmação específica e falsa**, e não um
genérico *"documentação atualizada"* que qualquer coisa satisfaz. Foi com a caixa
genérica marcada que a divergência atravessou vários PRs.

⚠️ **Mas o limite disso precisa ficar escrito, senão esta seção comete o próprio
defeito que denuncia: o workflow verifica o ATESTADO, não o FATO.** Ninguém
compara a marca do README com a branch padrão. O
`test_documentacao_do_estado.py` verifica que a etapa **apareça** no README e no
`estado.md`; **não** verifica se o `[x]` corresponde à realidade. **A correção de
fundo é mecanismo, e está registrada como pendência no backlog:** a marca do
README precisa ser **derivada ou conferida por teste**, no molde do arquivo
gerado da [DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md) —
porque a causa raiz aqui **não é distração, é duplicação**, e texto repetido em
dois lugares diverge assim que alguém atualiza um.

**Itens não aplicáveis exigem justificativa escrita no PR.** Ausência de tempo
não justifica dispensar teste obrigatório. ⚠️ **E marcar item que não foi
conferido é pior que deixá-lo em branco:** o checklist passa a ser prova falsa,
que é como a divergência do item 26 sobreviveu a vários PRs marcados como
completos.

