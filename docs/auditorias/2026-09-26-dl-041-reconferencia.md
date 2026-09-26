# Reconferência da DL-041

**Auditor:** `auditor-qa`. Única reconferência; não há terceira rodada.
**Data:** 2026-09-26
**Relatório conferido:** [rodada 1](2026-09-26-dl-041-rodada-1.md)
**Plano:** [DL-041](../planos/DL-041-unicidade-por-escritorio.md)
**Branch:** `claude/vigilant-bardeen-jo12l4`
**Revisão:** `6b76ddc981a02899f67b893e6e1e7695ef363e29`. A mensagem do commit diz "preservação, não entrega"; segundo o coordenador, o conteúdo é a correção completa. Auditei o conteúdo desta revisão.

**Ambiente:**
- Duas worktrees **minhas, fora do repositório**, nesta revisão: `rc41` e `rc41x`.
- Bancos de teste próprios: `dataledger_rc41`, `dataledger_rc41x` e `dataledger_rc41rev`, além de um SQLite temporário.
- Nada rodou na árvore principal nem na worktree do outro agente em `.claude/worktrees/`. As minhas foram removidas ao final.
- Python 3.13 (a integração contínua usa 3.14) e PostgreSQL 16 local.

Auditoria de software não substitui validação profissional das regras contábeis e fiscais. Este relatório não declara ausência de defeitos.

## Comandos executados

| Comando (worktree própria em `6b76ddc`) | Resultado |
| --- | --- |
| `pytest --create-db` (suíte completa) | `1 failed, 2658 passed, 45 skipped, 2 warnings, 4 subtests passed in 131.10s`. A única falha é a preexistente `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `274 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| PostgreSQL: `migrate` vazio, volta à 0012, ida de novo | 0012 e 0013 `OK`. Com a 0013, o gatilho de estabelecimento cobre `escritorio_id` e existe `trg_empresa_recusa_troca_de_escritorio`. Voltando à 0012, só resta o gatilho de estabelecimento, restrito a `empresa_id`. A ida recria os dois |
| SQLite limpo: `migrate`, volta à 0011, ida de novo | `Applying ...0012 OK`, `...0013 OK`; `Unapplying ...0013 OK`, `...0012 OK`; ida `OK` |
| `pwsh ./scripts/validate-docs.ps1` | **Não executado**: não há `pwsh` neste ambiente |

## Situação dos achados da rodada 1

| Achado | Situação | Evidência (reexecutada nesta revisão) |
| --- | --- | --- |
| **U-A1** — estabelecimento duplicado no mesmo escritório dava 500 no admin (média) | **Fechado** | Detalhado abaixo |
| **U-B1** — coluna `escritorio` do estabelecimento divergia por ORM ou SQL (baixa) | **Fechado** | Detalhado abaixo |
| **U-B2** — comentário da 0012 sobre a reversão (baixa) | **Fechado** | O diff entre `92b4503` e `6b76ddc` na 0012 só muda comentários e uma linha em branco perto dos `import`. As operações são idênticas. Aceitável, porque a 0012 ainda não está na `main` |
| **U-B3** — gatilho de sincronização sem teste direto (baixa) | **Fechado** | Novos testes diretos: `test_estabelecimento_queryset_update_de_escritorio_direto_e_sincronizado` e `test_empresa_queryset_update_de_escritorio_e_recusado`. As mutações V4 e V5 morrem |
| **U-B4** — CNPJ repetido entre empresa e estabelecimento de outra empresa do mesmo escritório (baixa, preexistente) | **Fechado com ressalva** | Recusado pela API e pelo admin, com os casos legítimos preservados. **A tela `empresas:criar` não recusa**, ver **V-B1** |

**U-A1 em detalhe:**
- Admin, estabelecimento com o CNPJ de estabelecimento de outra empresa do mesmo escritório: **200**, erro no inline `estabelecimento com este CNPJ já existe neste escritório.`, nada gravado. Na rodada 1 dava 500.
- Admin, duas linhas iguais no mesmo envio do inline: **200**, erro na linha, 0 gravados.
- Admin, mesmo CNPJ de estabelecimento em outro escritório: **302**, gravado.
- Mutações V1 (sem a checagem no escritório) e V2 (sem a checagem entre linhas) morrem.

**U-B1 em detalhe**, em PostgreSQL:
- `QuerySet.update(escritorio=...)`, `bulk_update([...], ["escritorio"])` e SQL direto `UPDATE ... SET escritorio_id` agora **não divergem**: o gatilho recalcula a coluna a partir da empresa.
- `Empresa.objects.filter(...).update(escritorio=...)` é **recusado** com `IntegrityError: Não é possível mudar o escritório desta empresa (DL-023)`.
- `update(empresa=<empresa de outro escritório>)` continua sincronizando.

## Verificação da U-B4 contra os casos legítimos

| Porta | Caso | Resultado | Esperado |
| --- | --- | --- | --- |
| API | Matriz com o **próprio** CNPJ da empresa | **201** | aceito |
| API | Estabelecimento da empresa A2 com o CNPJ da empresa A1 (mesmo escritório) | **400** | recusado |
| API | Empresa nova com CNPJ de estabelecimento da A2 | **400** "Este CNPJ já é de um estabelecimento (matriz/filial) de outra empresa deste escritório." | recusado |
| API | PATCH da A1 para o CNPJ de estabelecimento da A2 | **400** | recusado |
| API | PATCH só do nome de uma empresa que tem estabelecimento próprio | **200** | aceito |
| API (escritório B) | Empresa com CNPJ de estabelecimento do escritório A | **201** | aceito |
| API (escritório B) | Estabelecimento com CNPJ de empresa do escritório A | **201** | aceito |
| Admin | Criar empresa **junto com a matriz no inline, com o mesmo CNPJ** | **302**, 1 estabelecimento | aceito |
| **Tela `empresas:criar`** | **Empresa nova com CNPJ de estabelecimento da A2** | **302, gravada** | recusado, ver **V-B1** |

## O gatilho de troca de escritório atrapalha algum fluxo legítimo?

Não encontrei conflito.

| Fluxo | Resultado |
| --- | --- |
| `Empresa.save()` completo, mesmo escritório | ok. A função compara `IS DISTINCT FROM`, então regravar o mesmo valor não dispara |
| `QuerySet.update(escritorio=<o mesmo>, razao_social=...)` | ok |
| Admin editando empresa | **302** |
| API PATCH de empresa | **200** |
| API PUT com `escritorio` no corpo | **400**, recusado pelo contrato de campos, e o escritório continua o mesmo |
| Excluir empresa com estabelecimento | ok |
| Suíte completa (inclui os testes da DL-023 e os testes de migração que vão e voltam) | passa |
| Migração 0013 em banco com dados | Não varre linhas e não recusa nada preexistente, porque só age em `UPDATE` |

## Mutações

Todas contra a **suíte completa** (deselecionada só a falha preexistente), com banco de teste **recriado a cada uma**, porque duas alteram migração. Arquivos restaurados depois de cada execução; as worktrees terminaram limpas.

| Mutação | Resultado | Teste que matou |
| --- | --- | --- |
| V1 — formset sem checagem de duplicata no escritório | **Morta** | `test_admin_edita_empresa_e_adiciona_estabelecimento_duplicado_no_escritorio_da_200` |
| V2 — formset sem checagem entre linhas | **Morta** | `test_admin_cria_empresa_com_dois_estabelecimentos_de_mesmo_cnpj_no_mesmo_envio_da_200` |
| V3 — `save_related` sem `erro_de_cnpj_duplicado_como_400` | **Sobreviveu** | ver **V-B2** |
| V4 — gatilho de estabelecimento sem `escritorio_id` (0013) | **Morta** | `test_estabelecimento_queryset_update_de_escritorio_direto_e_sincronizado` |
| V5 — sem gatilho de troca de escritório (0013) | **Morta** | `test_empresa_queryset_update_de_escritorio_e_recusado` |
| V6 — U-B4 de estabelecimento sem efeito | **Morta** | `test_api_estabelecimento_com_cnpj_de_outra_empresa_do_mesmo_escritorio_e_recusado` |
| V7 — U-B4 de empresa sem efeito | **Morta** | `test_api_criar_empresa_com_cnpj_de_estabelecimento_de_outra_empresa_e_recusado` |
| V8 — U-B4 fora do `Empresa.clean` | **Morta** | `test_modelo_empresa_clean_recusa_cnpj_de_estabelecimento_de_outra_empresa` |

## Regressões

- O isolamento entre escritórios da rodada 1 se mantém: a mesma inscrição é aceita em outro escritório pela API e pelo admin, e duplicata no mesmo escritório é recusada com "neste escritório".
- Suíte completa, lint e checagens limpos.
- Não encontrei regressão.

## Achados novos

### V-B1 — A tela `empresas:criar` não aplica a recusa da U-B4

- **Gravidade:** baixa. A U-B4 era baixa e preexistente, e a recusa foi declarada só "na aplicação".
- **Requisito:** decisão do arquiteto na correção (U-B4), que deve valer em toda porta de cadastro.
- **Onde:** `apps/empresas/models.py:541`. `Empresa.clean` só verifica quando `self.escritorio_id is not None`. Na tela, o formulário não tem `escritorio`, que só é atribuído depois de `form.is_valid()` (`empresa.escritorio = request.escritorio` em `apps/empresas/views.py`, `criar_empresa`). Por isso a checagem nunca roda nessa porta, e `empresa.save()` não repete a checagem.
- **Evidência:** a empresa A2 do escritório A tem uma filial com CNPJ `11444777000161`. O gestor de A cadastra pela tela uma empresa nova com esse CNPJ: **302**, gravada (1 empresa com esse CNPJ em A). Pela API, o mesmo pedido dá 400.
- **Impacto:** reabre, só por essa porta, a ambiguidade da U-B4. A recepção fiscal vincula a nota à empresa e não à dona da filial, sem aviso. É o mesmo comportamento anterior à correção.
- **Correção recomendada:** em `criar_empresa`, chamar `recusar_cnpj_de_empresa_igual_a_estabelecimento_de_outra_empresa(request.escritorio.pk, cnpj, empresa=Empresa())` antes de gravar e devolver o erro no formulário. Outra opção: passar o escritório ao `EmpresaForm` e validar em `clean()`.
- **Como verificar:** o POST acima deve dar 200 com erro no campo `cnpj`, sem gravar. Um teste de tela deve reprovar se a recusa sumir.
- **Responsável:** `desenvolvedor-pleno`.

### V-B2 — A defesa final de `save_related` não tem efeito visível nem teste

- **Gravidade:** baixa.
- **Evidência:** a mutação V3 (retirar `erro_de_cnpj_duplicado_como_400` de `save_related`) sobrevive à suíte completa. Na janela de corrida o admin dá 500 com ou sem esse gerenciador: ele converte o `IntegrityError` em `ValidationError`, que o admin do Django não trata. O implementador declarou esse limite.
- **Impacto:** nenhum dado gravado errado. A proteção final no banco (`estabelecimento_cnpj_unico_por_escritorio`) continua valendo.
- **Correção sugerida:** tratar a recusa na visão do admin (`changeform_view`) com `message_user`, reapresentando o formulário, e testar isso. Se não houver interesse, retirar o gerenciador e deixar só o limite declarado.
- **Responsável:** `desenvolvedor-pleno`.

## O que NÃO foi verificado

- `validate-docs.ps1`: sem `pwsh` no ambiente.
- Python 3.14.
- Tela e admin sobre SQLite: em SQLite verifiquei só `migrate`, a volta e a ida.
- Corrida real de dois estabelecimentos duplicados no mesmo escritório pelo admin. A pela API está coberta pelo teste do implementador, que anula o validador.
- A árvore principal e a worktree do outro agente: fora do escopo, de propósito.

## Parecer final da DL-041

- **U-A1** (o motivo da reprovação na rodada 1) está fechado: estabelecimento duplicado no mesmo escritório agora dá erro de formulário no admin, inclusive entre linhas do mesmo envio. O critério 3 do plano está atendido.
- **U-B1, U-B2 e U-B3** estão fechados. A coluna de escritório do estabelecimento não diverge mais por ORM ou SQL em PostgreSQL, e a troca de escritório da empresa é recusada no banco sem atrapalhar os fluxos do produto.
- **U-B4** está fechado na API e no admin, com os casos legítimos preservados (matriz com o próprio CNPJ e a mesma inscrição em outro escritório).
- Não encontrei regressão.
- **Ressalvas, todas baixas e explícitas:**
  - **V-B1:** a tela de criar empresa não aplica a recusa da U-B4.
  - **V-B2:** a defesa final de `save_related` não muda o resultado na janela de corrida e não tem teste.
  - Limites declarados que continuam valendo: 500 no admin na janela de corrida; em SQLite as regras continuam só na aplicação.

**Parecer: APROVADO COM RESSALVAS**
