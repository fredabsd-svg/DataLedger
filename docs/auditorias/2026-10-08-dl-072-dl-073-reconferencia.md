# Reconferência independente DL-072 e DL-073 (última rodada do §3.1)

## Identificação da revisão

| Item | Início | Fim |
| --- | --- | --- |
| HEAD | `3f1eef48bb7b3457b44e5a1744168fba30bfa297` | `3f1eef48bb7b3457b44e5a1744168fba30bfa297` |
| Branch | `ccr-bf4b4a55-hpqgbp` | idem |
| `git status --porcelain` | vazio | vazio |
| `git diff --stat` | vazio | vazio |

- **Base do diff de código:** `a88e2fc..3f1eef4`, 18 arquivos, +1.416/−120. Correções: `5c8c1b1` (DL-073) e `ede3966` (DL-072). O resto é documentação.
- **Ambiente:** Python 3.13.16 e PostgreSQL 16.15. O `pwsh` não existe aqui.
- **Isolamento:** usei três worktrees descartáveis (`/home/user/wt-reconf072`, `…m` e `…p`) e bancos `dataledger_reconf072*`. Removi as worktrees e derrubei os bancos. O repositório principal ficou intacto.
- **Worktree `wt-dl074`:** estava listada no início e **não existe mais no fim**, nem a branch local `dl074`. Eu não executei `git branch -d` nem `worktree remove` nelas. Só removi os três caminhos `wt-reconf072*` e rodei `git worktree prune`. A remoção partiu de outro ator durante a auditoria. Resta `wt-dl074int` (`dl074-int`), que não toquei.
- **Sondas:** os arquivos estão em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rec/sondas/`, fora do repositório.

## Pareceres (separados)

| Etapa | Nível (§3.1) | Parecer |
| --- | --- | --- |
| **DL-072**, escrituração das NFS-e prestadas | 1 | **APROVADO COM RESSALVAS** |
| **DL-073**, validador de conformidade IBS/CBS | 2 | **APROVADO COM RESSALVAS** |

- **Alcance:** não encontrei bloqueador nem falha de alta ou média gravidade em nenhuma das duas. A correção única fechou os achados da rodada 1 por execução, salvo A10, que ficou parcial e registrado (BL-662 e BL-664), e B4, aceito com o limite declarado na tela e em BL-663.
- **Ressalvas da DL-072:**
  - R1: o aviso de divergência dispara quando o contador aceita a própria sugestão do sistema (4 de 30 combinações).
  - R2: o banco ainda aceita INSERT de linha estornada com valores arbitrários.
  - R3: a migração `0002` foi editada no lugar, e bancos locais já migrados ficam sem a trava do A4.
  - R4 e R5: duas lacunas de teste.
  - R6: o `estado.md` voltou a ficar defasado no HEAD.
  - A10: o XML de todas as notas do mês ainda é lido na lista e na conferência.
- **Ressalvas da DL-073:** o limite B4 (falsos avisos futuros no desenho da NT 009, declarado) e as regras fiscais ainda como hipóteses HI-56 a HI-67.
- **Alcance deste parecer:** ele cobre o software. Não valida as regras contábeis e fiscais, que dependem da validação do Fred e do contador. Não afirmo ausência total de defeitos.

## Verificações gerais

| Verificação | Resultado |
| --- | --- |
| `pytest` completo, 1ª execução | **Testado.** 5.408 aprovados, 3 reprovados, 53 pulados. Eu rodava a bateria de mutantes ao mesmo tempo (quatro processos). Dois reprovados são `test_concorrencia.py::test_corrida_real_de_documento_produz_um_unico_documento` e `…_de_evento_produz_um_unico_evento` (DL-010/DL-076). Eles dependem de a segunda thread colidir com o lock. A falha foi `resultados == [1, 0]`, e a segunda thread chegou depois de a primeira terminar. O terceiro é o de ambiente. |
| Os dois de concorrência, isolados | 3 execuções, 2 aprovados em todas. Os arquivos não estão no diff. Não foram reproduzidos com a máquina ociosa. Registro como teste sensível à carga, preexistente e fora desta entrega. |
| `pytest` completo, 2ª execução (máquina ociosa) | **Testado.** **5.410 aprovados, 1 reprovado, 53 pulados**, 2 avisos de depreciação preexistentes (`savepoint()`), 382 s. A reprovação é `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (Python 3.13). Confere com o esperado. |
| 340 testes DL-072/073 (9 arquivos) | Aprovados em 13 s. |
| `ruff check .` | Limpo. |
| `ruff format --check .` | 395 arquivos já formatados. |
| `manage.py check` | Sem problemas. |
| `makemigrations --check --dry-run` | Sem mudanças. |
| `migrate` em banco vazio | Aplicou tudo. Dois gatilhos criados. A função contém a trava nova (`position('valores do documento')` = 885). |
| `migrate fiscal 0001` e reaplicação de `0002` | Desfez as 2 funções e a tabela (`to_regclass` nulo). Reaplicou limpo, com 2 gatilhos e 2 funções. |
| Documentação | `pwsh` ausente, então `validate-docs.ps1` **não foi executado**. Verificação equivalente em Python nos 4 `.md` alterados desde `a88e2fc` (título, UTF-8, espaço no fim, nova linha final, links relativos): 0 problemas. |

## Achados da rodada 1: situação

| Achado | Situação | Evidência executada |
| --- | --- | --- |
| **A1** (atomicidade trilha/estorno sem teste) | **Fechado** | M11b agora morre por 2 testes (`test_falha_na_trilha_desfaz_efetivar_rascunho_e_estornar` e `…_o_estorno_com_commit_real`). M11 (efetivar) morre por 6 e M11s (rascunho) por 1. Antes M11b sobrevivia. |
| **A2** (data de emissão no fuso de Brasília) | **Fechado** (HI-72) | Sonda de fuso com 11 combinações: `-04:00 23:30` e `dCompet` 31/01 grava 31/01 sem aviso (antes 01/02 com aviso falso). `-05:00 22:30`, `+05:00`, `-12:00`, `Z` e fração de segundo gravam o dia escrito. `00:00-03:00` do dia 01/02 com `dCompet` 31/01 continua avisando (correto). Nota sem `dhEmi`: tela de lista, conferência e escriturar respondem 200 com "—"; efetivar recusa com mensagem nomeada (tela 200, API 409); rascunho grava; a API de lista devolve `data_emissao: null`. Mutantes N-A2-brasilia (4 mortos), N-A2-utc (5) e N-A2-nulo-grava (1). HI-72 registrada em `requisitos.md`. |
| **A3** (`estado.md` desatualizado) | **Fechado em `fccbec9`**, mas **ressurgiu no HEAD** | Ver R6. |
| **A4** (INSERT de efetivada com valores arbitrários) | **Fechado**, com resíduo R2 e R3 | Sonda: INSERT efetivada com `valor_servico` 999999.99, `valor_liquido` 1.00 ou `data_competencia` 2030 é **recusado** (`escrituracao efetivada precisa ter os valores do documento`). UPDATE rascunho→efetivada com valor 777 é recusado. Valores do documento, aceito. NULL, recusado pelo CHECK. Efetivar+estornar legítimos funcionam. Estorno depois de o documento ser alterado funciona. Mutantes do gatilho: A4-all morto por 6, A4-vserv, A4-vliq e A4-comp por 2 cada. |
| **A5** (mensagem crua de natureza) | **Fechado** | Tela: `""` e campo ausente mostram "Escolha a natureza da operação."; `sem_incidencia` e `<script>x</script>` mostram a mensagem do catálogo, sem ecoar o valor. API: `""` e `{}` → 400 com a mesma mensagem; `xyz` e `5` → 400 do catálogo; `null` → 400 do DRF. Nada gravado. N-A5-vazio morto por 5. |
| **A6** (lista mostra só a natureza sugerida) | **Fechado** | Sonda: "Escriturada" e "Rascunho, não efetivada" aparecem com a natureza gravada, e "Sem sugestão do XML" para não incidência. O ramo "Sugerida pelo XML" só é exercido pelo teste da suíte, não pela minha sonda. N-A6 morto por 1. |
| **A7** (divergência só na trilha) | **Fechado**, com falso positivo R1 | Conferência lista as divergências. Mutantes N-A7-ret (6), N-A7-exp1 (2) e N-A7-exp2 (1) mortos. |
| **A8** (identidade tautológica) | **Fechado** | Cenário misto com valores à mão: 1000,00 efetivada; 200,10 efetivada e estornada; 50,05 efetivada e cancelada depois; 7,77 cancelada; 3,33 rascunho; 0,01 a escriturar; 9999,99 em outro mês. Resultado: recebidas 6 = R$ 1.261,26; escrituradas 1 = R$ 1.000,00; pendentes 5 = R$ 261,26; gravada 1.000,00; documentos 1.000,00; diferença 0,00. Tudo `Decimal`. Bloqueios: `a_escriturar`, `cancelada_depois_de_escriturada`, `rascunho`, `a_escriturar`. A tela mostra "1.261,26", "1.000,00" e "sem diferença", sem o erro de não fechamento. Com o documento alterado para 1000,01, a diferença é −0,01 e a tela destaca. O identificador "recebidas = escrituradas + pendentes" continua tautológico. A comparação gravada × documento é real. Mutantes N-A8-esc, -pend, -rec, -grav e -sinal mortos. Lacuna R5 no mutante com `float`. |
| **A9** (400 em vez de 404) | **Fechado** (404, alinhado ao plano) | Gestor e PARALEGAL na lista, na conferência e na conformidade: empresa própria 200; de outro escritório 404; inexistente 404; malformada, negativa e gigante 400. CLIENTE: 403 em todos os casos. Anônimo: 302. Corpo do 404 de outro escritório idêntico ao da empresa inexistente, sem o nome da empresa B. Empresa de outro escritório com competência inválida: 404 (a empresa é checada antes). Mutante N-A9 (sem escopo) morto por 3 testes. |
| **A10** (desempenho) | **Parcial, aceito pelo registro** | Detalhe e escriturar de uma nota deixaram de reprocessar o mês: o detalhe não seleciona `xml_original` (consultas medidas: `defer`), a tela de uma nota usa `nota_do_vinculo`. Consultas constantes com 22 notas: detalhe 9, escriturar 8, lista 9, conferência 9, conformidade 6. Falta paginar a API (BL-662) e deixar de ler o XML na lista e na conferência (BL-664). Não remedi tempo com 1.000 notas. |
| **A11** (detalhe sem histórico) | **Fechado** | Escrituração estornada e reefetivada: o detalhe de cada uma lista a outra com link e mostra a trilha ("Efetivada", "Estornada", quem e quando). Registro forjado de outro escritório com o mesmo `objeto_id`: **não aparece**, nem o nome do gestor de B. Gestor de B no detalhe de A, com `empresa_a` ou `empresa_b` na URL: 404. N-A11-esc morto por 1. N-A11-outras sobrevive e é equivalente: todas as linhas de um vínculo têm a mesma empresa por gatilho. |
| **B1** (parser seguro sem teste) | **Fechado** | M22 morre por `test_dtd_com_entidade_nao_forja_a_sugestao_de_natureza`. M22b morre por `test_dtd_com_entidade_dentro_de_nota_valida_e_recusado_pelo_validador`. Antes ambos sobreviviam. |
| **B2** (tomadora na conformidade) | **Fechado** | M33 morre por `test_conformidade_do_mes_nao_lista_nota_em_que_a_empresa_e_tomadora`. Sonda: `conformidade_do_mes(empresa_a2)` devolve `[]`. |
| **B3** (decimal via `float`) | **Fechado** | M38 morre por `test_decimal_lido_sem_passar_por_float`. |
| **B4** (falsos `elemento_ausente` da NT 009) | **Aceito**, limite declarado | A tela traz o parágrafo "Limite da NT 009". O texto confere com `consultas/…leiaute-ibscbs-nfse.md`, linhas 141 a 144 e 196. BL-663 registra a dependência da tabela cClassTrib e a ressalva de que a NT 009 só dá exemplos (400, 410, 820). O comportamento não mudou. |
| **B5** (canceladas com avisos) | **Fechado** | Sonda: nota cancelada vem com `cancelada=True` e `avisos` vazio, e a tela mostra "Não conferida: nota cancelada". A não cancelada com o mesmo defeito segue avisada. Evento de cancelamento de outro escritório com a mesma chave **não** cancela. A lista usa `dCompet` (nota emitida em 01/11 com `dCompet` 31/10 entra em outubro). A ordem é por emissão. A consulta é 1 para 24 notas. N-B5 morto por 1. |

## Mutantes

Cada mutante rodou nos 340 testes dos 9 arquivos `test_dl072_*` e `test_dl073_*`, com a árvore restaurada a cada rodada. O estado da árvore foi conferido no fim.

**Mutantes da rodada 1**

| Mutante | Resultado |
| --- | --- |
| M1 sem unicidade parcial | Morto por 2 |
| M1b M1 + sem `select_for_update` | Morto por 4 |
| M2 sem guarda no `save()` | Morto por 3 |
| M2b sem guarda no `delete()` | Morto por 1 |
| M3 sem gatilho de imutabilidade | Morto por 6 |
| M3b sem gatilho prestador/empresa | Morto por 8 (inclui os testes novos do A4) |
| M4 `dCompet` → `dhEmi` no filtro | Morto por 8 |
| M4b `dCompet` → `dhEmi` na data gravada | Morto por 5 |
| M5a (vínculo, tela) | Morto por 1 |
| M5b (vínculo, API) | Morto por 1 |
| M5c (escrituração, API) | Morto por 1 |
| M5d (escrituração, tela) | Morto por 1 |
| M6 precedência da retenção invertida | Morto por 6 |
| M7 tabela 1.00 trocada pela 1.01 | Morto por 4 |
| M7b tabela 1.01 trocada pela 1.00 | Morto por 13 |
| M11 efetivar sem `atomic` | Morto por 6 |
| **M11b** estornar sem `atomic` | **Morto por 2** (antes sobrevivia) |
| M11s rascunho sem `atomic` | Morto por 1 |
| **M22** sugestão com `ElementTree.fromstring` | **Morto por 1** (antes sobrevivia) |
| **M22b** validador com `ElementTree.fromstring` | **Morto por 1** (antes sobrevivia) |
| M24 tolerância `<=` → `<` | Morto por 7 |
| M25 tolerância 0,02 | Morto por 7 |
| M31 alíquota de 2026 também em 2027 | Morto por 1 |
| M31b M31 + fórmula E1530 em 2027 | Morto por 2 |
| **M33** conformidade inclui tomadas | **Morto por 1** (antes sobrevivia) |
| **M38** `Decimal` via `float` | **Morto por 1** (antes sobrevivia) |

M31 morre por menos testes que na rodada 1 (7). Isso vem de como montei o mutante: minha variante só altera uma das duas linhas de ano. O caso completo é o M31b.

**Mutantes do gatilho de valores (A4)**

| Mutante | Resultado |
| --- | --- |
| A4-all, sem a checagem inteira | Morto por 6 |
| A4-vserv, sem `valor_servico` | Morto por 2 |
| A4-vliq, sem `valor_liquido` | Morto por 2 |
| A4-comp, sem `data_competencia` | Morto por 2 |

**Mutantes novos da correção**

| Mutante | Resultado |
| --- | --- |
| N-A2-brasilia, N-A2-utc, N-A2-nulo-grava | Mortos (4, 5 e 1) |
| N-A5-vazio | Morto por 5 |
| N-A6 | Morto por 1 |
| N-A7-ret, N-A7-exp1, N-A7-exp2 | Mortos (6, 2 e 1) |
| N-A8-esc, N-A8-pend, N-A8-rec, N-A8-grav, N-A8-sinal | Mortos (1, 1, 2, 2 e 2) |
| **N-A8-float** (soma via `float`) | **Sobrevive**: ver R5 |
| N-A9 | Morto por 3 |
| N-A9-400 | Morto por 22 |
| N-A11-esc | Morto por 1 |
| N-A11-outras | Sobrevive, **equivalente** |
| N-B5 | Morto por 1 |
| **N-A4-estornoPuro** (checagem de valores também no estorno) | **Sobrevive**: ver R4 |

Nenhum mutante da rodada 1 voltou a sobreviver.

## Achados novos

### R1. Baixa. Aceitar a sugestão do sistema gera aviso de divergência (falso positivo do A7)

- **Requisito:** HI-59 ("avisa") e HI-67, plano DL-072 item 3.
- **Local:** `apps/fiscal/escrituracao.py:182` (`_sugestao`, retenção tem precedência) contra `:386-412` (`_divergencias_da_natureza`, regra de exportação no `:407`).
- **Reprodução:** sonda com versões 1.00 e 1.01, `tribISSQN` 1 a 4 ou ausente e `tpRetISSQN` 1, 2 e 3 (30 combinações). Para cada nota, gravo como rascunho a natureza que o próprio `sugerir_natureza` devolve e consulto as divergências.
  - 4 combinações divergem: leiaute 1.01 com `tribISSQN=3` e `tpRet` 2 ou 3, e leiaute 1.00 com `tribISSQN=2` e `tpRet` 2 ou 3.
  - Texto emitido: "O XML traz tribISSQN de exportação, mas a natureza gravada é 'Serviço prestado — ISS retido pelo tomador ou pelo intermediário'."
- **Impacto:** o sistema sugere "retido" e, quando o contador o aceita, avisa que está errado. É só aviso, sem bloqueio, e a combinação (exportação retida) é rara. Mas é o tipo de ruído que ensina o contador a ignorar a lista de divergências.
- **Correção recomendada:** a regra "XML traz exportação e a natureza não é exportação" não deve disparar quando a natureza gravada é "retido" e o XML indica retenção. É a mesma precedência da sugestão. Um único ponto define as duas regras.
- **Verificação:** teste parametrizado nas 30 combinações:

```python
@pytest.mark.parametrize("versao,trib", [(v, t) for v in ("1.00", "1.01") for t in ("1", "2", "3", "4", None)])
@pytest.mark.parametrize("tp_ret", ["1", "2", "3"])
def test_aceitar_a_sugestao_nunca_gera_divergencia(escritorio_a, empresa_a, usuario_gestor_a, versao, trib, tp_ret):
    documento = _nota(escritorio_a, usuario_gestor_a, versao=versao, trib_issqn=trib, tp_ret_issqn=tp_ret)
    vinculo = _vinculo(documento, empresa_a)
    sugerida = servico.nota_do_vinculo(empresa_a, vinculo).natureza_sugerida
    if sugerida is None:
        pytest.skip("não incidência: sem sugestão")
    servico.salvar_rascunho(vinculo, sugerida, usuario_gestor_a)
    assert servico.nota_do_vinculo(empresa_a, vinculo).divergencias_de_natureza == ()
```

### R2. Baixa. INSERT direto de linha estornada com valores arbitrários é aceito

- **Requisito:** plano DL-072, valores copiados do documento, e AGENTS §10. Resíduo do A4.
- **Local:** `apps/fiscal/migrations/0002_dl072_escrituracao_fiscal.py:54`. A checagem só vale para `NEW.estado = 'efetivada'`.
- **Reprodução:** `EscrituracaoFiscal.objects.create(..., estado="estornada", valor_servico=Decimal("5555.55"), estornada_em=..., estornada_por=..., motivo_estorno="x", efetivada_em=..., efetivada_por=..., data_emissao=..., data_competencia=..., valor_liquido=..., iss_retido=False)` sobre uma nota de vServ 100,00. Foi **aceito** e, dali em diante, é imutável. Do mesmo modo, uma efetivada com `iss_retido=True` numa nota sem retenção também é aceita. `iss_retido` e `data_emissao` não são conferidos no banco. O dia de emissão só existe no XML, então não dá para conferi-lo ali. Esse limite não está declarado.
- **Impacto:** só quem escreve SQL ou código chega a isso. A conferência usa apenas linhas ativas, então os totais não mudam. Mas a trilha pode ganhar uma linha que afirma um ato que o documento não tem, e ela não pode ser corrigida depois.
- **Correção recomendada:** no `INSERT`, aplicar a mesma checagem também a `'estornada'`, com `TG_OP = 'INSERT'`. Não aplicar no UPDATE de estorno (ver R4). Comparar `iss_retido` com o `tp_ret_issqn` do documento, ou declarar no plano que esse campo e o dia de emissão não são conferidos no banco.
- **Verificação:** os testes `test_insert_de_efetivada_com_valor_alheio…` parametrizados também com `estado="estornada"`. Efetivar e estornar pelo serviço seguem funcionando.

### R3. Baixa. Migração `0002` editada no lugar: bancos já migrados ficam sem a trava do A4

- **Requisito:** AGENTS §12 ("não editar migrações já aplicadas em ambientes compartilhados") e §6 (migrações no PR).
- **Local:** `apps/fiscal/migrations/0002_dl072_escrituracao_fiscal.py` (função `fiscal_escrituracao_vinculo_prestador`).
- **Evidência:** a `0002` só existe nesta branch. `main` está em `389aafe` e `git log --all` só a mostra na branch (`2912ffc` em diante), então a regra do §12 não foi violada. Mas o Django considera a `0002` aplicada e não a reexecuta. Consulta somente de leitura ao catálogo de `dataledger_dl074`, que é o banco do trabalho da DL-074:
  - `django_migrations` tem `fiscal.0002` aplicada, e a função não contém "valores do documento" (posição 0).
  - Em `dataledger_corr072` (migrado depois) a posição é 885.
- **Impacto:** qualquer banco migrado antes de `ede3966` continua sem a proteção do A4 até ser recriado. Testes não detectam isso, porque criam o banco do zero.
- **Correção recomendada:** registrar no PR (§6, "migrações e reversão") que bancos locais anteriores a `ede3966` precisam ser recriados, ou que a função precisa ser reaplicada à mão. Se a `0002` tiver sido aplicada em qualquer ambiente compartilhado, a correção deve virar uma `0003` e a `0002` voltar ao texto original.
- **Verificação:** em um banco com a `0002` antiga, `migrate` mostra "No migrations to apply" e a consulta ao `pg_proc` não traz a trava. Com a nota no PR ou com a `0003`, o banco fica igual ao de um banco novo.

### R4. Baixa. Nenhum teste prova que o estorno continua possível depois de o documento mudar

- **Requisito:** comentário do próprio gatilho ("Estorno não é conferido, para nunca bloquear o estorno") e plano DL-072, correção rastreável.
- **Local:** `apps/fiscal/migrations/0002_dl072_escrituracao_fiscal.py:54`.
- **Reprodução:** mutante N-A4-estornoPuro (troca `NEW.estado = 'efetivada'` por `NEW.estado IN ('efetivada','estornada')`). Os 340 testes passam. Esse mutante impediria o estorno de qualquer nota cujo documento tivesse mudado depois da efetivação, que é justamente o caso em que o estorno é mais necessário. A sonda `A4 estorno apos doc alterado` mostra que o código atual faz certo.
- **Verificação:** o teste abaixo falha com o mutante e passa na linha de base.

```python
def test_estorno_funciona_mesmo_depois_de_o_documento_mudar(escritorio_a, empresa_a, usuario_gestor_a):
    documento = _nota(escritorio_a, usuario_gestor_a, v_serv="10.00", v_liq="10.00")
    efetivada = servico.efetivar_escrituracao(_vinculo(documento, empresa_a), DEVIDO, usuario_gestor_a)
    DocumentoFiscal.objects.filter(pk=documento.pk).update(v_serv=Decimal("11.00"))
    estornada = servico.estornar_escrituracao(efetivada, "documento mudou", usuario_gestor_a)
    assert estornada.estado == EstadoEscrituracao.ESTORNADA
```

### R5. Baixa. Nenhum teste detecta soma de totais via `float`

- **Requisito:** AGENTS §10 e CLAUDE.md ("Não use ponto flutuante binário comum"). O A8 pedia valores escritos à mão.
- **Local:** `apps/fiscal/escrituracao.py:415` (`_soma`).
- **Reprodução:** mutante N-A8-float, `return Decimal(str(sum(float(v) for v in valores)))`. Os 340 testes passam. Os valores dos testes (1000,00, 250,50, 0,01) somam sem resíduo binário.
- **Impacto:** uma regressão que somasse em `float` passaria na suíte, e o total monetário da conferência poderia sair com resíduo.
- **Verificação:** o teste abaixo falha com o mutante, pois `0.10 + 0.20` em `float` dá `0.30000000000000004`.

```python
def test_totais_da_conferencia_somam_centavos_sem_float(escritorio_a, empresa_a, usuario_gestor_a):
    _nota(escritorio_a, usuario_gestor_a, sufixo=1, v_serv="0.10", v_liq="0.10")
    _nota(escritorio_a, usuario_gestor_a, sufixo=2, v_serv="0.20", v_liq="0.20")
    _nota(escritorio_a, usuario_gestor_a, sufixo=3, v_serv="999999999999999.99", v_liq="1.00")
    c = servico.conferencia(empresa_a, 2024, 1)
    assert c.total_recebidas == Decimal("1000000000000000.29")
    assert str(c.total_pendentes) == "1000000000000000.29"
```

### R6. Baixa. `docs/agents/estado.md` defasado no HEAD

- **Requisito:** CLAUDE.md, "Estado do projeto: um lugar só" (instrução permanente do Fred, 2026-09-13).
- **Local:** `docs/agents/estado.md:181-191` e `:199-203`.
- **Evidência:** o arquivo diz "correção única em andamento (DL-072: A1, A2, A4 a A11; DL-073: B1 a B5), em cópias isoladas" e dá a linha de base "5.358 aprovados … sobre `a88e2fc`". No HEAD `3f1eef4` as correções estão integradas (`5c8c1b1` e `ede3966`) e a suíte mede 5.410 aprovados. A correção do A3 em `fccbec9` estava certa para o seu momento. O texto voltou a ficar defasado com a integração das correções.
- **Impacto:** é a mesma classe de defeito do A3. `test_documentacao_do_estado` não o detecta.
- **Correção recomendada:** ao encerrar esta reconferência, o arquiteto atualiza o `estado.md` (correção integrada, ciclo do §3.1 encerrado, nova linha de base, BL-662 a BL-665 abertos).
- **Verificação:** reler o arquivo contra `git log` e o resultado da suíte.

## Observações sem classificação

- **A API da conferência** continua sem totais, conciliação e divergências. Está registrado como BL-665. Uma conferência só pela API não vê o que a tela mostra.
- **Telas da DL-073 e a de documentos** continuam exibindo `dh_emissao|date:"d/m/Y H:i"`, o instante convertido para Brasília. A HI-72 cobre a data gravada na escrituração. O contador pode ver "01/02 00:30" numa tela e "31/01" na outra para a mesma nota emitida em `-04:00`.
- **Teste de concorrência da DL-010/076** sensível à carga (ver "Verificações gerais"). Vale um olhar do dono desse teste.

## O que não foi verificado e por quê

| Item | Estado | Motivo |
| --- | --- | --- |
| Aparência e acessibilidade no navegador | Não testado | Sem navegador. Só HTML renderizado e os testes de moldura acessível da suíte. |
| `pwsh ./scripts/validate-docs.ps1` | Não testado | `pwsh` ausente. Substituído por verificação equivalente em Python (0 problemas). |
| Python 3.14, CI e proteção de branch | Não testado | Ambiente com Python 3.13.16. |
| Validade normativa (HI-56 a HI-67, HI-72, cronograma, alíquotas de teste, naturezas) | Fora do escopo do software | Hipóteses até validação do Fred e do contador. Não reabri as fontes oficiais. |
| Tempo com 1.000 notas depois da correção | Não testado | Só contagem de consultas (constante) com 22 notas. O ganho de tempo depende de BL-664. |
| Migração sobre base volumosa com linhas já gravadas, e reversão com dados | Não testado | Só banco vazio. |
| Reprodução do reprovado de concorrência sob carga | Não reproduzido | Passa isolado (3 vezes) e na suíte limpa; a falha ocorreu apenas com carga concorrente da minha bateria. |
| M5e, M32 e os mutantes M8 a M10, M12 a M21, M26 a M30, M34 a M37, M39 e M40 | Não reaplicados | Não estavam entre os pedidos desta reconferência. Os testes que os matavam na rodada 1 continuam na suíte e passaram. |
| Livro-caixa (BL-661) | Não testado | Limite declarado. |

## Efeitos colaterais

- **Repositório principal:** HEAD `3f1eef4`, `git status --porcelain` e `git diff --stat` vazios no início e no fim. Não usei `ruff format` sem `--check`.
- **Worktrees e bancos:** removidas as três worktrees `wt-reconf072`, `…m` e `…p`. Derrubados `dataledger_reconf072`, `…m`, `…p`, `…s` e os `test_dataledger_reconf072*`. A única consulta fora dos meus bancos foi leitura ao catálogo de `dataledger_dl074` e `dataledger_corr072` (R3). Não alterei nada neles.
- **`wt-dl074`:** ver a nota na identificação. A remoção da worktree e da branch local `dl074` não foi feita por mim.

Arquivos relevantes: `apps/fiscal/escrituracao.py`, `apps/fiscal/migrations/0002_dl072_escrituracao_fiscal.py`, `apps/fiscal/views_web.py`, `apps/fiscal/ibscbs.py`, `docs/agents/estado.md`.

---

Registrado pelo `arquiteto-senior` em 08/10/2026, sem edição dos achados. A worktree `wt-dl074` citada na identificação foi removida pelo arquiteto durante a auditoria, depois de o trabalho dela ser reaplicado em `wt-dl074int`.
