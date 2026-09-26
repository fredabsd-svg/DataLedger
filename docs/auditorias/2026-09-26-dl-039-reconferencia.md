# Reconferência da DL-039

**Auditor:** `auditor-qa`. Única reconferência; não há terceira rodada.
**Data:** 2026-09-26
**Relatório conferido:** [rodada 1](2026-09-26-dl-039-rodada-1.md)
**Revisão:** `06802732fe664990d8d418fb9a7dadae16eab1a3`, commit de correção `0680273`, migração nova `apps/empresas/migrations/0011_bl533_bl534_gatilho_com_nome_e_trava.py`.

**Ambiente:**
- Toda a reconferência rodou em worktrees **minhas, fora do repositório**, na revisão `0680273`: `scratchpad/aud-dl039` e uma segunda, `aud-dl039b`, só para as mutações em paralelo.
- Bancos de teste próprios: `dataledger_aud` (gera `test_dataledger_aud`), `dataledger_aud2`, `dataledger_aud3` e `dataledger_audrev`, além de um SQLite em arquivo temporário. Nada rodou na árvore principal, que recebe trabalho concorrente da DL-041.
- Worktrees e bancos meus foram removidos ao final. A worktree de outro agente em `.claude/worktrees/` não foi tocada.
- Python 3.13 (a integração contínua usa 3.14) e PostgreSQL 16 local.

Auditoria de software não substitui validação profissional das regras contábeis e fiscais. Este relatório não declara ausência de defeitos.

## Comandos executados

| Comando (worktree própria em `0680273`, banco `dataledger_aud`) | Resultado |
| --- | --- |
| `pytest --create-db` (suíte completa) | `1 failed, 2618 passed, 45 skipped, 2 warnings, 4 subtests passed in 128.75s`. A única falha é a preexistente `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `271 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `pwsh ./scripts/validate-docs.ps1` | **Não executado**: não há `pwsh` neste ambiente |

**A margem do AGENTS.md:** `test_agentes_multiplataforma.py::test_agents_md_nao_ultrapassa_a_margem_de_seguranca_do_codex` **passou** na minha worktree, que fica fora do repositório e não tem `.claude/worktrees/` dentro. Isso é compatível com a explicação do implementador: a falha que ele viu vem da worktree de outro agente dentro do diretório, que faz o AGENTS.md ser contado em dobro. **Concordo que é artefato de sessão**, não defeito da entrega.

## Reversão 0011 → 0010 → 0009 e ida de novo

| Banco | Resultado |
| --- | --- |
| PostgreSQL (`dataledger_audrev`) | Depois de `migrate`: a função do gatilho de estabelecimento tem `FOR SHARE` e `CONSTRAINT` nomeada; a de transição tem `CONSTRAINT` nomeada. Depois de voltar à 0010, as duas voltam ao corpo da 0010, sem `FOR SHARE` e sem `CONSTRAINT`. Depois de voltar à 0009, as duas somem. A ida de novo recria o estado da 0011, com os 2 gatilhos |
| SQLite limpo (`DATABASE_URL=sqlite:///<tmp>/db.sqlite3`, `DEBUG=True`) | `Applying ...0010 OK`, `...0011 OK`; volta `Unapplying ...0011 OK`, `...0010 OK`; ida `Applying ...0010 OK`, `...0011 OK`. Sem erro |

## Situação dos achados da rodada 1

### D1 / BL-533 — gatilho recusava com 500 — **Fechado com ressalva baixa**

| Caso | Antes (rodada 1) | Agora |
| --- | --- | --- |
| Admin: criar empresa CPF com estabelecimento no inline (caminho comum) | 500 | **200**, erro do formset: "Não é possível cadastrar estabelecimento (matriz/filial) para uma empresa do tipo CPF...". **0 empresas, 0 estabelecimentos** gravados |
| Admin: editar empresa CPF acrescentando estabelecimento no inline | não medido | **200**, 0 estabelecimentos |
| Admin: criar PJ com estabelecimento no inline (regressão) | — | **302**, 1 empresa e 1 estabelecimento |
| API: `POST api-estabelecimentos` para empresa CPF na janela de corrida (checagem em Python anulada) | 500 | **400** `{"empresa":["Não é possível cadastrar estabelecimento ..."]}`, nada gravado |
| API: `PATCH api-detalhe` de PJ com filial para CPF na janela de corrida | 500 | **400** `{"tipo_inscricao":["Não é possível mudar esta empresa para CPF ..."]}`, tipo continua CNPJ |
| **Admin na janela de corrida** (checagem do formset anulada; é a ressalva que o implementador declarou) | 500 | **500**. Medido: 0 empresas, 0 estabelecimentos, 0 registros novos de trilha, e a resposta **não** contém o texto do banco. A exceção é `django.core.exceptions.ValidationError`, levantada por `EmpresaAdmin.save_model`/`save_related` e que o admin do Django não trata |

**Julgamento da ressalva do admin: baixa.**
- É 500, e não 200 com erro de formulário: o implementador declarou isso corretamente.
- Só acontece na janela entre a validação do formset e a gravação, quando outra transação muda a mesma empresa ao mesmo tempo.
- O admin é restrito a superusuário.
- Não grava nada, não deixa trilha e não expõe texto do banco.
- O caminho comum, que era o do achado D1, está corrigido.
- Correção possível, fora desta etapa: capturar a recusa em `changeform_view`/`response_add` e devolver `message_user` com o formulário reapresentado. Responsável sugerido: `desenvolvedor-pleno`.

### D2 / BL-534 — os gatilhos não fechavam a corrida — **Fechado**

Corrida real com duas conexões (`transaction=True`), nas duas ordens:

| Ordem | Resultado | Invariante |
| --- | --- | --- |
| Estabelecimento primeiro, transação segurada 0,3 s | O `UPDATE` para CPF **espera** e então recebe `IntegrityError: Empresa não pode mudar para tipo_inscricao=CPF com estabelecimento já gravado` (0,21 s depois de liberado). Final: CNPJ com 1 estabelecimento | ok |
| CPF primeiro, segurada 0,3 s | O INSERT de estabelecimento espera e recebe `IntegrityError: Estabelecimento não pode ser vinculado a uma empresa com tipo_inscricao=CPF`. Final: CPF com 0 estabelecimentos | ok |
| Estabelecimento primeiro, segurada 2,0 s | A transação que espera cai no `lock_timeout` de 1210 ms: `OperationalError: canceling statement due to lock timeout` (1,23 s). Final: CNPJ com 1 estabelecimento | ok |
| CPF primeiro, segurada 2,0 s | Idem, pela outra ponta. Final: CPF com 0 estabelecimentos | ok |

Na rodada 1, a mesma corrida terminava em **CPF com 1 estabelecimento**. Agora a invariante se mantém nas duas ordens.

**Observação (baixa, não é defeito desta etapa):** quando a transação que segura a trava passa de 1210 ms, quem espera recebe `OperationalError` de `lock_timeout`, que a API não traduz, e a resposta seria 500. Isso decorre da política geral de `lock_timeout` do projeto (BL-463, `config/settings.py`). As transações de cadastro de empresa e de estabelecimento são curtas, então o caso é improvável. Registro para quem revisar essa política.

### D3 — invariante só na aplicação em SQLite — **Sem mudança (limite declarado)**

A 0011 também é no-op fora do PostgreSQL. Continua valendo o limite declarado de ambiente de desenvolvimento.

## Desenho do dicionário separado `MENSAGENS_DE_RESTRICAO_DE_GATILHO`

**Inspecionado e testado por mutação:** `apps/core/restricoes.py` separa as mensagens de gatilho de `MENSAGENS_DE_RESTRICAO`.

- **Motivo aceito:** a varredura da DL-019 exige que `MENSAGENS_DE_RESTRICAO` contenha só restrições do ORM (`Meta.constraints`). Um nome de gatilho ali quebraria essa garantia. A separação mantém a varredura verdadeira e dá à tradução o mesmo formato (`restricao_como_400`, por `diag.constraint_name`).
- **Mutação R4** (renomear a chave no dicionário): **morta**. A API passa a dar 500 e a suíte reprova.
- **Limite de desenho, observação baixa:** nenhuma varredura confere que todo `CONSTRAINT = '...'` declarado em gatilho de migração tem entrada no dicionário. Um gatilho novo sem registro só seria pego pelo teste de comportamento que alguém escrevesse para ele. Sugestão, fora desta etapa: uma varredura que extraia os `CONSTRAINT = '...'` das migrações e compare com as chaves do dicionário.

## Mutações da reconferência

Todas contra a **suíte completa** (deselecionada só a falha preexistente), com o banco de teste **recriado a cada mutação** (`--create-db`), porque três delas alteram migração. Arquivos restaurados depois de cada execução; as worktrees terminaram limpas.

| Mutação | Resultado | Teste que matou |
| --- | --- | --- |
| R1 — sem `CONSTRAINT` no gatilho de estabelecimento | **Morta** | `test_api_post_estabelecimento_na_janela_de_corrida_da_400_nao_500` |
| R2 — sem `CONSTRAINT` no gatilho de transição | **Morta** | `test_api_patch_empresa_para_cpf_na_janela_de_corrida_da_400_nao_500` |
| R3 — sem `FOR SHARE` | **Morta** | `test_corrida_insert_estabelecimento_primeiro_nunca_deixa_cpf_com_estabelecimento` |
| R4 — nome divergente no dicionário de gatilho | **Morta** | `test_api.py::test_criar_estabelecimento_via_api_com_cnpj_mascarado_e_aceito` (500) |
| R5 — formset do admin sem a checagem de CPF | **Morta** | `test_admin_cria_empresa_cpf_com_estabelecimento_no_inline_da_200_sem_gravar` |
| R6 — 0011 no-op também em PostgreSQL | **Morta** | `test_api_post_estabelecimento_na_janela_de_corrida_da_400_nao_500` |

Nenhuma sobreviveu.

## Regressões

- A suíte completa passa, com a mesma falha preexistente de antes.
- O admin continua criando PJ com estabelecimento no inline (302).
- A API continua recusando empresa CPF no caminho normal (checagem em Python, 400), e a regra agora vale também no banco.
- Não encontrei regressão.

## Achados novos

Nenhum de gravidade média ou superior. As observações baixas estão acima:
- 500 do admin na janela de corrida (ressalva do D1, declarada pelo implementador e medida);
- `lock_timeout` sem tradução quando a espera passa de 1210 ms (política geral do projeto);
- falta de varredura entre os nomes `CONSTRAINT` dos gatilhos e o dicionário.

## O que NÃO foi verificado

- `validate-docs.ps1`: sem `pwsh` no ambiente.
- Python 3.14.
- Tela e admin sobre SQLite: em SQLite verifiquei só `migrate`, a reversão e a ida de novo.
- Gatilho diante de dado inconsistente preexistente (empresa CPF que já tinha estabelecimento antes da 0010/0011).
- A árvore principal e a worktree do outro agente: fora do escopo, de propósito.

## Parecer final da DL-039

- **BL-526, BL-527, BL-528:** fechados na rodada 1 e sem regressão aqui.
- **BL-529 com BL-533 e BL-534:** fechados.
  - A recusa do banco chega como 400 com mensagem na API e como erro de formulário no admin, pelo caminho comum.
  - A corrida entre os gatilhos está fechada nas duas ordens, medida com conexões reais.
  - A 0011 reverte corretamente em PostgreSQL e em SQLite.
- **Ressalvas, todas baixas e explícitas:**
  1. 500 no admin só na janela de corrida, sem gravar, sem trilha e sem texto do banco.
  2. `lock_timeout` de 1210 ms não traduzido quando a transação concorrente é longa (política geral, BL-463).
  3. Nenhuma varredura amarra os nomes `CONSTRAINT` dos gatilhos ao dicionário de mensagens.
  4. Em SQLite a invariante continua só na aplicação (limite declarado, D3).

**Parecer: APROVADO COM RESSALVAS**
