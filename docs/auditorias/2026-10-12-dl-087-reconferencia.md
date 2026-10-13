# Reconferência da DL-087 — 12/10/2026

## Parecer

**APROVADA COM RESSALVAS.**

- **A1 (alta) está resolvido.** A regra revogada deixa de casar com qualquer nota, em todos os pontos que testei. A efetivada fica intocada e a origem fica preservada. A confirmação com prévia antiga recebe 409. O banco recusa desativação que não seja revogação.
- **Nenhum achado alto ou bloqueador novo.** Os achados novos são 1 médio (R1) e 4 baixos.
- **Os pontos abertos são ressalvas, não impedimentos.** A7, A9 e A6 continuam parciais, com decisão do arquiteto ou do Fred pendente. Há duas lacunas de teste, provadas por mutante.
- **Suíte completa em uma única invocação:** 10.114 passaram, 56 foram ignoradas e 1 falhou. A falha é `test_versao_minima_python`, causada pelo Python 3.13 local.

Isto não é garantia de ausência de defeitos nem de conformidade legal. A validação das regras contábeis e fiscais continua com o Fred.

## Versão e ambiente

- **Cópia auditada:** `/home/user/wt-rc087`, commit `dc02d23`.
  - Ao final: `git status --short` vazio, HEAD `dc02d23`, `git diff --stat` vazio.
  - Nada foi escrito nessa cópia.
- **Cópia de sondas:** `git archive dc02d23`, idêntica à auditada (`diff -rq apps` sem diferença antes de acrescentar sondas). Sondas, mutantes e medidas rodaram nela.
- **Ambiente:** Python 3.13 local (a CI usa 3.14). PostgreSQL local. Bancos `rc_dl087*` usados e **apagados** no fim.
- **Evidências:** `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc087/`. Os arquivos principais são `suite.log`, `mut2.log`, `mut2b.log`, `volume.log`, `volume_pior.log`, `golden_nova.log`, `golden_base.log` e `micro.py`.

## Tabela A1 a A13

| # | Situação | Evidência (executada) |
|---|---|---|
| A1 | **Resolvido (Testado)** | Detalhes abaixo da tabela. |
| A2 | **Resolvido (Testado)** | Prévia empatada com regra existente: API 409 e tela 409 com a mensagem nomeando a regra. Criar duplicada: 409. Prévia normal: 200. Prévia igual a regra revogada: 200. Mutantes C06 e C07 mortos. |
| A3 | **Resolvido (Testado)** | Regra de escritório com 2 itens confirmados na empresa A. A lista da empresa "Outra", via API e via tela, mostra 0. A lista da empresa A mostra 2. A tela de desativar usa a contagem filtrada. Mutantes C04 e C05 mortos. |
| A4 | **Resolvido (Testado)** | Com lote em andamento, os ids `abc`, `a\|b`, vazio e natureza inteira respondem 400 com mensagem. Antes era 500. Mutante C15 morto. |
| A5 | **Resolvido (Testado)** | API: `22AB`, árabe-índico, largura total, espaço e hífen respondem 400 com mensagem. `2203.00.00` e ` 2203 ` são aceitos. A tela responde 400 com a mensagem. Mutantes C08 e C09 mortos. |
| A6 | **Parcial (Testado)** | Índice por CFOP e NCM provado equivalente à busca completa. Medida de 10.000 NFC-e e pior caso abaixo. |
| A7 | **Parcial (Inspecionado, Testado)** | Aviso do mês presente na fila, na prévia do lote (serviço e tela) e na prévia de impacto (API e tela). A API do lote não traz o aviso (declarado). DE-108 está registrada, mas **sem confirmação do Fred**. Mutantes C13 e C14 mortos. |
| A8 | **Resolvido, com R1 e R4 (Testado)** | A nota efetivada mostra a origem gravada ("regra n.º 4 (da empresa), desativada (revogada) em 12/10/2026"). "Ver notas" funciona na tela e na API, com paginação. Banco recusa UPDATE e DELETE de origem de efetivada e de estornada. Mutantes C16, C21 e C22 mortos. |
| A9 | **Parcial (Testado)** | Volta recusada com origem de efetivada (mutante C23 morto). Com origem só de estornada ou de rascunho, a volta passa e **descarta a origem**. A estornada já foi efetivada, então é fato de auditoria. Está declarado e é baixo (R5). |
| A10 | **Resolvido (Testado)** | Reproduzi a equivalência fora do repositório: base `9e0640a` e `dc02d23` dão o mesmo sha256 em 2.852.352 combinações (abaixo). |
| A11 | **Resolvido (Testado)** | M16 (reclassificação em massa sem origem) agora é morto (C17). M22 (regra sobrepõe natureza escolhida na tela) agora é morto (C18). |
| A12 | **Resolvido (Inspecionado, Testado)** | Texto "CFOP x.501, x.502, x.910 ou x.911" confere com `_CFOP_SEM_SUGESTAO`. A referência ao teste inexistente saiu. A lista ainda é manual, mas tem teste de guarda. |
| A13 | **Resolvido (Testado)** | Enter: o primeiro submit do formulário é o botão oculto "Ver o alcance, sem gravar" (`value="previa"`, `tabindex=-1`), que nunca grava. "Criar regra" na fila é `botao--secundario botao--pequeno`. A lista de regras usa `_paginacao.html`. O gatilho recusa TRUNCATE da regra com linha (C25 morto) e desativação por SQL que não seja revogação (C20 morto). O TRUNCATE da origem foi removido, o que está declarado e aceito. Ver R3. |

**A1 em profundidade (Testado)**

- Regra de empresa criada e depois revogada: o fim gravado é a véspera do início (2026-02-28 para início em 2026-03-01).
- **Lote.**
  - A assinatura da prévia mudou e o grupo sumiu.
  - `confirmar_lote` com a prévia antiga lança `PreviaDesatualizada` (409 na API), e nada foi gravado.
  - Revogar no meio do lote: a nota já efetivada fica, e as duas restantes **falham**. Nenhuma foi efetivada com a regra revogada.
- **Fila:** o item volta à fila (1 item).
- **Sugestão direta:** `sugerir_natureza_com_regras` devolve `None`/produto.
- **Telas e API.** A tela de rascunho não cita regra. A API da fila responde 200 sem a regra. Todos os consumidores passam por `contexto_da_empresa` e `sugerir_natureza_com_regras`, que exclui a regra revogada em `_casa`.
- **Efetivada.**
  - Natureza, estado, receita e `efetivada_em` ficam idênticos.
  - A linha de origem fica idêntica (pk, origem, regra, `gravada_em`).
  - UPDATE e DELETE por SQL de origem de efetivada e de estornada são recusados.
  - "Ver notas" lista a nota efetivada da regra revogada.
- **SQL.** UPDATE de desativação com fim 2099, NULL, igual ao início ou início menos 2 dias: **recusado**. Só início menos 1 dia (a revogação) é aceito. Segundo UPDATE: recusado.
- **Brechas.**
  - Gestor de outro escritório: 404 por API e por tela (com a empresa certa e com a dele).
  - Analista revogando regra de escritório: 403.
  - Paralegal: 403.
  - Regra de outra empresa pela URL desta: 404.
  - Segunda revogação: 409 na API e na tela.
  - Motivo vazio: 400.
  - Anônimo: 403 na API e 302 na tela.
  - Quatro threads revogando ao mesmo tempo: 1 sucesso, 3 recusas e **1 registro de trilha**.
- **Trilha.** Registra `efeito: revogada`, o fim gravado e o motivo, sem segredo.

**Equivalência sem regra (Testado)**

- Corpus de 619 CFOP × NCM × CST × `idDest` × tipos, com os 4 padrões de combustível.
- `golden_base.log` (base `9e0640a`) e `golden_nova.log` (`dc02d23`): ambos `2852352 combinacoes, sha256 8445f08f4aefe1636ad4ea81d4c3c1b8235d05d6270d477ca633ba8413f78a8b`.

**Índice versus busca completa (Testado)**

- Diferencial próprio: 360.000 amostras em 3 sementes, mais 120.000 numa quarta rodada com contagem por origem.
- Cada amostra tem regras aleatórias (sem NCM, exato, prefixos de 2 a 7, CST, `idDest`, escopos, vigências, revogadas) e itens aleatórios.
- **0 diferenças.** A amostra não é vazia: numa rodada deu 20.715 respostas "regra", 433 "conflito", 3.490 "padrão" e 95.362 "produto".

**Desempenho de A6 (10.000 NFC-e, mesmo teste do desenvolvedor, minha máquina)**

| Medida (média de 3) | Sem regra | 50 regras com NCM que não casa | 50 regras que casam todo item |
|---|---|---|---|
| Prévia do lote | 2,54 s | 2,98 s (+17%) | 4,81 s |
| Fila | 1,93 s | 2,13 s (+10%) | 4,27 s |
| Prévia de impacto | 2,49 s | 2,62 s (+5%) | 6,65 s |
| Prévia da tela (variantes) | 2,83 s | 3,11 s (+10%) | 9,14 s |
| Confirmação (média das 100 partes) | 5,06 s | 5,45 s (+7,6%) | 5,23 s (+3,4%) |

- **Ruído.** A variação entre as 3 repetições "sem regra" chega a 16% na prévia do lote. As diferenças de +10% a +17% estão no nível do ruído. A afirmação do desenvolvedor de "±5%" **não se reproduziu**.
- **Critério 7 como a DL-085 o define** (média das partes de confirmação): +7,6% e +3,4%, dentro de 10%. As duas execuções com regras (+7,6% e +3,4%) ficaram dentro de 10% nesta máquina, mas são medidas únicas e sujeitas ao mesmo ruído.
- **Microbenchmark da resolução** (10.000 itens, memória, melhor de 5):
  - sem regra: 0,052 s;
  - 50 regras com NCM que não casa: 0,059 s;
  - 50 regras sem NCM e vigência fora da data: 0,200 s;
  - 50 regras que casam todo item: 0,654 s (13 vezes).
- **O índice por NCM funciona.** O custo só dispara quando muitas regras do mesmo CFOP casam o mesmo item.
- **Pior caso interativo (R5):** a prévia da tela chega a 9,1 s com 50 regras empilhadas (25 por CFOP) que casam todo item. Isso é sintético, mas não há limite nem teste desse caso.
- **N+1:** não há.
  - Fila (tela): 16 → 13 consultas, de 2 para 14 grupos.
  - Regras (tela): 7 → 7. API: 5 → 5.
  - Escriturar: 21 consultas com 1 item, 18 com 12 itens.
  - "Ver notas": 8 → 8 na tela e 7 → 7 na API, com 2 e depois 32 itens.

**Gatilho de imutabilidade da origem (item 3, Testado)**

Os fluxos legítimos continuam funcionando:

- `definir_natureza` três vezes seguidas em rascunho;
- efetivar, estornar e criar novo rascunho (duas vezes) e efetivar de novo;
- reclassificação em massa em rascunho, duas vezes, gravando origem `regra` e depois `manual`;
- lote sobre notas que incluem nota estornada e reescriturada, terminando com todas efetivadas.

Nenhum fluxo foi bloqueado.

**Item 4: ajuste no teste da DL-082 (Testado)**

- A proteção continua: a volta é recusada e as colunas e o valor `monofasico` seguem no banco.
- **A mensagem da DL-082 deixou de ser coberta para nota efetivada.** Os casos de rascunho e de segmento ainda a cobrem. O ramo "efetivada" da guarda da 0014 ficou sem teste (R4).
- O mutante C24 (a guarda da 0014 ignora efetivada) **sobreviveu** com 255 passando.
- Escrevi o teste que o mata e o rodei: **passa no código real e falha no mutante** ("DID NOT RAISE"). O texto está em R4.

## Achados novos

**R1 — Média — Paginação de "ver notas" na API dá 500 com `pagina` enorme**

- **Local:** `apps/fiscal/api_classificacao.py:311-327` (`_paginacao`), `:361` (`inicio = (pagina - 1) * tamanho`) e `:369` (fatia da consulta).
- **Evidência.**
  - `GET /fiscal/api/empresas/<id>/nfe/classificacao/regras/<id>/notas/?pagina=99999999999999999999` → **500**.
  - O mesmo com `pagina=9223372036854775807` → **500**. O erro é `DataError: bigint out of range`.
  - `pagina=184467440737095516` → 200.
  - A tela com os mesmos valores responde 200, porque o `Paginator` trata.
- **Impacto:** usuário autenticado com permissão de consulta provoca 500 por entrada estranha, contra o contrato do módulo ("nunca 500", docstring de `api_classificacao.py`). Sem corrupção de dados.
- **Correção:** limitar `pagina` a um teto (por exemplo, 400 se `pagina > 1_000_000`), ou calcular a última página e devolver 200 com lista vazia.
- **Verificação:**

```python
@pytest.mark.parametrize("p", ["99999999999999999999", "9223372036854775807"])
def test_ver_notas_api_com_pagina_enorme_nao_da_500(client, gestor, empresa, regra, p):
    client.force_login(gestor)
    r = client.get(url_api_notas(empresa, regra) + f"?pagina={p}")
    assert r.status_code in (200, 400)
```

**R2 — Baixa — Rascunho com natureza vinda de regra revogada pode ser efetivado sem aviso**

- **Local:** `apps/fiscal/classificacao.py:913-960` (`desativar_regra`) e `escrituracao_nfe.py:1322` (`efetivar`).
- **Evidência:** rascunho com natureza confirmada pela regra, regra revogada, `efetivar` OK. A tela do rascunho mostra "Origem da natureza confirmada: regra n.º 3 (da empresa), desativada (revogada) em 12/10/2026". A tela de desativar não avisa que os rascunhos já confirmados com essa regra mantêm a natureza.
- **Impacto:** é coerente com o critério 4 (não altera natureza já escolhida em rascunho), mas é um caminho residual para o erro que a revogação quis cortar. O contador vê a marca, mas nada o obriga a rever.
- **Correção recomendada.** Decisão do arquiteto ou do Fred, entre:
  - avisar na tela de desativar quantos rascunhos mantêm a natureza e levar ao "ver notas" filtrado por estado; ou
  - avisar na efetivação.
- **Verificação:** teste de tela da desativação com rascunho confirmado e a frase do aviso.

**R3 — Baixa — O gatilho de TRUNCATE da regra quebra o `flush` de teste transacional e do `manage.py flush`**

- **Local:** `migrations/0019_dl087_regra_de_classificacao_nfe.py:73-87`.
- **Evidência:** um teste `@pytest.mark.django_db(transaction=True)` que cria uma regra termina com `CommandError: Database test_rc_dl087_b couldn't be flushed` (`IntegrityError: regras de classificação de NF-e gravadas não podem ser truncadas`).
- **Impacto:** qualquer teste transacional futuro que crie regra falha no encerramento, com mensagem confusa. O comentário da migração diz só que tabela vazia pode ser truncada. A suíte atual passa porque nenhum teste transacional cria regra.
- **Correção recomendada:** documentar a restrição no comentário, no `estado.md` e no `AGENTS.md`, ou tratar como o gatilho da origem (sem TRUNCATE). A escolha é do arquiteto.
- **Verificação:** teste transacional que cria regra e termina sem erro de flush, ou nota explícita na documentação de testes.

**R4 — Baixa — Duas lacunas de teste provadas por mutante**

- **(a) C24.** A guarda da 0014 (DL-082) para nota efetivada sem origem gravada, que é dado anterior à DL-087, ficou sem cobertura. Teste proposto, **verificado** (passa no real, falha no mutante):

```python
@pytest.mark.django_db(transaction=True)
def test_reversao_dl082_recusa_com_marca_em_efetivada_sem_origem_gravada(escritorio_a, usuario_gestor_a):
    empresa = Empresa.objects.create(escritorio=escritorio_a, razao_social="Sem origem Ltda", cnpj=CNPJ_EMITENTE_A)
    documento = nota(escritorio_a, usuario_gestor_a, empresa, numero=905, itens=[{"cfop": "5102", "vprod": "1000.00"}])
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    item_id = ItemNFe.objects.get(documento=documento).pk
    servico_nfe.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, [item_id], usuario=usuario_gestor_a)
    servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario_gestor_a)
    OrigemNaturezaItemNFe.objects.all().delete()   # dado anterior à DL-087 (apagável só em rascunho)
    servico_nfe.efetivar(esc, usuario=usuario_gestor_a)
    try:
        with pytest.raises(RuntimeError) as erro:
            call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
        assert MENSAGEM in str(erro.value)
        assert "1 item(ns) com marca de monofásico" in str(erro.value)
    finally:
        call_command("migrate", verbosity=0)
```

- **(b) C27.** A API de "ver notas" aceita regra de qualquer escritório sem que teste algum reclame. Na prática o filtro por empresa limita o dado, e meus 404 manuais passaram, mas falta o teste. Proposta: `GET .../regras/<id da regra de outro escritório>/notas/` e `.../<regra de outra empresa>/notas/` devem dar 404 na API, como já existe na tela.

**R5 — Baixa — Pior caso de volume sem limite nem teste**

Ver a tabela de desempenho: a prévia da tela chega a 9,1 s e a prévia de impacto a 6,6 s com 50 regras que casam todo item. Recomendação: registrar no plano a medida do pior caso e decidir se há teto de regras por CFOP. Verificação: repetir `DL087_PIOR=1` (script em `probe/apps/fiscal/tests/test_rc087_volume.py`, na cópia de sondas).

**R6 — Baixa — Reversão da 0020 descarta a origem de nota estornada**

É o resíduo de A9, declarado pelo desenvolvedor. Se o arquiteto quiser tratar a origem de estornada como fato de auditoria, basta ampliar o filtro da guarda para efetivada e estornada. Verificação: `migrate fiscal 0018` com estornada deve recusar.

## Mutantes

28 mutantes em cópia (`git archive dc02d23`), rodados contra todos os `test_dl087_*` e `test_dl082_migracao_reversao`, com `-x`. **25 mortos, 3 sobreviventes.**

| Mutante | Resultado | Teste que matou, ou motivo |
|---|---|---|
| C01 revogar volta a fim = ontem | Morto | `test_dl087_api::test_analista_nao_desativa_regra_de_escritorio_e_gestor_desativa` |
| C02 revogar grava fim = início | Morto | idem |
| C03 `_casa` sem checar `desativada_em` | **Sobreviveu** | Equivalente: a vigência vazia já exclui a regra. A guarda explícita é redundante e declarada. |
| C04 contagem sem filtro por empresa | Morto | `test_a3_api_conta_so_os_itens_confirmados_da_empresa_da_url` |
| C05 ver notas sem filtro de empresa | Morto | `test_a3_tela_de_desativar_conta_so_a_empresa_da_url` |
| C06 prévia sem checar duplicidade | Morto | `test_a2_previa_de_regra_duplicada_recusa_com_a_regra_existente` |
| C07 `_chave_pk` volta a `regra.pk` | Morto | `test_a2_ordenacao_tolera_a_regra_da_previa_sem_pk` |
| C08 NCM aceita letras | Morto | `test_a5_...[22AB]` |
| C09 NCM aceita dígitos Unicode | Morto | `test_a5_...[٢٢٠٣]` |
| C10 índice ignora prefixos | Morto | `test_a6_indice_acha_as_mesmas_candidatas_que_a_busca_completa` |
| C11 índice ignora regras sem NCM | Morto | `test_dl087_api::test_previa_de_impacto_conta_sem_gravar_nada` |
| C12 índice exato usa NCM errado | Morto | `test_a6_candidatas_do_item_nao_incluem_regra_de_ncm_que_nao_casa` |
| C13 prévia de impacto sem aviso do mês | Morto | `test_a7_previa_do_lote_e_previa_de_impacto_avisam_o_mes_confirmado` |
| C14 lote sem aviso do mês | Morto | idem |
| C15 id malformado volta a IndexError | Morto | `test_a4_escolha_com_identificador_malformado_e_400_com_lote_aberto` |
| C16 tela efetivada sem origem gravada | Morto | `test_a8_nota_efetivada_mostra_a_origem_gravada_e_nao_a_sugestao_de_hoje` |
| C17 reclassificação em massa sem origem | Morto | `test_a11_reclassificacao_em_massa_grava_origem_regra_e_depois_manual` |
| C18 regra sobrepõe natureza escolhida (tela) | Morto | `test_a11_natureza_escolhida_continua_selecionada_depois_de_regra_nova` |
| C19 revogar duas vezes aceito | Morto | `test_dl087_cadastro::test_desativar_duas_vezes_responde_409_e_nada_muda` |
| C20 gatilho da regra aceita qualquer fim | Morto | `test_a1_sql_recusa_desativacao_que_nao_e_revogacao` |
| C21 gatilho da origem aceita INSERT em efetivada | Morto | `test_a8_gatilho_recusa_mudar_origem_de_escrituracao_efetivada` |
| C22 gatilho da origem aceita UPDATE ou DELETE em efetivada | Morto | idem |
| C23 reversão da 0020 não recusa origem efetivada | Morto | `test_a8_reversao_da_0020_recusa_com_origem_de_efetivada_e_nao_com_rascunho` |
| C24 guarda da 0014 ignora efetivada | **Sobreviveu** | Lacuna de teste, ver R4(a). |
| C25 gatilho de TRUNCATE da regra não recusa | Morto | `test_a8_truncate_da_regra_recusa_com_linha` |
| C26 API de ver notas sem teto de `tamanho` | Morto | `test_a8_lista_de_notas_da_regra_com_paginacao_invalida_e_400` |
| C27 API de ver notas aceita regra de qualquer escritório | **Sobreviveu** | Lacuna de teste, ver R4(b). |
| C28 variantes da prévia usam o resultado do completo | Morto | `test_dl087_api::test_previa_de_impacto_conta_sem_gravar_nada` |

## Verificações

| Comando | Resultado |
|---|---|
| `pytest -q` (suíte completa, uma invocação, banco próprio) | `1 failed, 10114 passed, 56 skipped, 2 warnings, 4 subtests passed in 1209.72s`. A falha é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (`SyntaxError`, Python 3.13 local). Os avisos são `savepoint()` obsoleto, de `contabilidade`, preexistentes. |
| `ruff check --no-cache .` | `All checks passed!` |
| `ruff format --check --no-cache .` | `670 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `migrate` em banco vazio, `migrate fiscal 0018`, `migrate` | Ida, volta e ida OK. Unapplying 0020 e 0019 OK. |
| Volta com regra ativa ou revogada | `RuntimeError: Reversão da DL-087 recusada, sem alterar nada: 1 regra(s)...`. 0019 e 0020 seguem aplicadas. |
| Volta com origem de efetivada, sem regra | `RuntimeError: ... 1 origem(ns) de natureza de NF-e de escrituração efetivada...`. Nada muda. |
| Volta com origem de rascunho ou de estornada | Passa e descarta a origem. A ida refaz as tabelas. |
| `pytest apps/fiscal` | Não rodado isolado: coberto pela suíte completa. |
| Mutantes | `mut2.log` e `mut2b.log`. |
| Banco | Bancos `rc_dl087*` apagados. |

## O que não foi testado

- **Navegador real e densidade 1280×800.** Inspecionei só o HTML. Não executei verificação de acessibilidade automatizada.
- **`pwsh ./scripts/validate-docs.ps1`:** `pwsh` não está instalado. **Bloqueado.**
- **Python 3.14** (CI): rodei em 3.13.
- **Concorrência de criação de regras:** só a revogação concorrente foi executada.
- **Backup e restauração da tabela de regras.**
- **Medida de volume em CPU isolada.** Rodei no mesmo ambiente de 4 núcleos, em sequência, sem carga paralela. O ruído de 16% entre repetições impede confirmar ou refutar diferenças menores que isso.
- **A decisão de A7 pelo Fred:** pendente, não é verificável por teste.

## Arquivos relevantes

- Código auditado:
  - `/home/user/wt-rc087/apps/fiscal/classificacao.py` (`vigencia_revogada`, `_casa`, `candidatas_do_item`, `desativar_regra`, `previas_de_impacto`, `contagem_de_confirmados`, `confirmados_da_regra`)
  - `/home/user/wt-rc087/apps/fiscal/api_classificacao.py` (`_paginacao`, `RegraNotasView`, linhas 311 a 369)
  - `/home/user/wt-rc087/apps/fiscal/views_web.py`
  - `/home/user/wt-rc087/apps/fiscal/escrituracao_nfe.py` e `escrituracao_nfe_lote.py`
  - `/home/user/wt-rc087/apps/fiscal/migrations/0019_dl087_regra_de_classificacao_nfe.py`, `0020_dl087_origem_da_natureza_confirmada.py` e `0014_dl082_pre_das_comercio.py` (guarda de R4(a))
  - `/home/user/wt-rc087/apps/fiscal/tests/test_dl082_migracao_reversao.py` (item 4)
  - `/home/user/wt-rc087/apps/fiscal/tests/test_dl087_correcao_rodada1.py`
  - `/home/user/wt-rc087/apps/fiscal/tests/test_dl087_volume.py`
  - `/home/user/wt-rc087/templates/fiscal/classificacao_regra_notas.html`
- Sondas, mutantes e medidas (cópia de sondas):
  - `.../scratchpad/rc087/probe/apps/fiscal/tests/test_rc087_*.py`
  - `.../scratchpad/rc087/mutar2.py`
  - `.../scratchpad/rc087/diff_indice.py`
  - `.../scratchpad/rc087/micro.py`
  - `.../scratchpad/rc087/mig_seed.py`
- Relatórios anteriores: `/home/user/wt-rc087/docs/auditorias/2026-10-12-dl-087-rodada-1.md`.
