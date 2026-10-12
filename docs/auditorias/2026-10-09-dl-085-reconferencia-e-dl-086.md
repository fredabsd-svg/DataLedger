# Reconferência da DL-085 e verificação da DL-086 — 09/10/2026

**Parecer DL-085 (nível 1, última rodada): APROVADA COM RESSALVAS.**
Os achados A1 a A3 (médios) estão fechados com evidência executada. Não há bloqueador nem achado de gravidade alta. Restam um achado novo médio (R1) e achados baixos, que o arquiteto ajusta ou registra.

**Parecer DL-086 (nível 3, documentação e painel): APROVADA COM RESSALVAS.**
Das I1 a I17, as de escopo estão corrigidas. Restam a I4, textos remanescentes e uma guarda que cobre pouco.

Esta auditoria não substitui a validação profissional das regras contábeis e fiscais.

## 1. Versão e ambiente

- **Versão:** cópia destacada `/home/user/wt-rc085`, commit `6b1d90f`, na branch `ccr-bf4b4a55-hpqgbp`. `git status` e `git diff` estão vazios no fim. Removi só o `.ruff_cache`, que eu criei ao rodar o ruff.
- **Stack:** Python 3.13.16, Django 6.1.2, PostgreSQL 16.15 local, 4 núcleos, `PYTHONDONTWRITEBYTECODE=1`.
- **Carga concorrente:** outro agente rodava um `pytest` completo em `/home/user/wt-dl082` na mesma máquina. A carga média ficou entre 2 e 5. Os tempos absolutos abaixo estão inflados. As comparações A/B foram feitas alternadas, sob a mesma carga.
- **Bancos:** `aud_dl085_rc2` (suíte completa), `rc3` (experimentos), `m1`, `m2` e `m3` (mutantes), `ui` (navegador).
- **Artefatos:** tudo em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc085b/`.
  - Testes: `tree/apps/fiscal/tests/test_rc085_equiv2.py` e `test_rc085_conc.py`. Reaproveitei também `test_aud085_*` e `test_rc085_a4.py`.
  - Mutantes: `mutar.py`, `mut_1.log` e `mut_2.log`.
  - Logs: `pytest_completo.log`, `travamento_10000.log`, `validate_docs.py` e `browser.py`.
- **Dos artefatos parciais do auditor anterior,** usei os scripts. Os logs de mutantes estavam incompletos e eu os refiz inteiros.

## 2. DL-085 — achados da rodada 1

| # | Situação | Evidência executada |
| --- | --- | --- |
| A1 contadores e trilha inflados | **Fechado** | `_processar_nota` devolve `_OUTRA_CHAMADA` e `_gravar_estado` devolve booleano. O teste com duas threads (T3) falha 4 de 4 vezes no mutante que volta ao comportamento antigo (M4a2). Na versão corrigida passa 5 de 5. Os mutantes M4a, M4a2, M21 e N1 morrem. |
| A2 rascunho com natureza manual sobrescrito | **Fechado, com lacuna de teste** | O rascunho com natureza diferente da sugestão sai do lote com o motivo `natureza_escolhida`. A regra é revalidada na efetivação. Meu teste de equivalência com rascunhos preexistentes deu 23 notas iguais ao caminho individual (vazio, mesma natureza e parcial entram; divergente fica rascunho com `bonificacao` intacta). N4 a N7 morrem. N8 sobrevive (R4). |
| A3 devolução ausente na tela | **Fechado** | No navegador real (Chromium), o grupo de devolução mostra 40,00 na coluna "Devolução". O resumo diz "devolução de 40,00". N21 e N22 morrem. |
| A4 repetição sem `grupos` | **Fechado, com efeito colateral (R6)** | `_grupos_divergem` trata `None` como "todos". N15, N16 e N44 morrem. |
| A5 ordem de travas e deadlock | **Fechado** | Medição na seção 5. Sem o ajuste `5ca0d5f` há deadlock reproduzível. Com ele não houve nenhum em 3 execuções. M10, N25 e N26 morrem. |
| A6 parte dimensionada por quantidade | **Fechado** | Orçamento de 10 s por parte. Com relógio real, 10 notas de 2,5 s cada resultaram em 4 efetivadas e 6 restantes, em 10,2 s. N9, N10 e N11 morrem. Ressalva: a preparação da chamada fica fora do orçamento (seção 5). |
| A7 memória e XML | **Parcial** | A prévia caiu 44 a 46% (seção 5). O XML ainda é lido 3 vezes por nota na efetivação (R2). |
| A8 comentários desatualizados | **Parcial** | Os dois comentários apontados foram corrigidos. A correção criou comentários novos desatualizados (R3). |
| A9 acessibilidade e Post/Redirect/Get | **Fechado, com ressalvas** | No navegador, o POST responde com redirect para um GET. O progresso aparece uma vez e a recarga mostra a prévia, sem reenviar o POST. Cada caixa de grupo tem nome acessível único. Ressalvas: R5 (rótulo visível não contido no nome acessível) e R7 (backlog). |

## 3. Casos de teste propostos T1 a T10

| T | Teste do desenvolvedor | Avaliação |
| --- | --- | --- |
| T1 dois lotes (M33) | `test_dois_lotes_em_andamento_nao_se_tocam` | Fechado. M33 morre. |
| T2 cancelada (M26) | `test_nota_cancelada_nao_entra_nem_vira_escrituracao` | Fechado. M26 morre. |
| **T3** duas partes (A1) | `test_duas_partes_simultaneas_contam_cada_nota_uma_vez`, mais `test_parte_unica_registra_as_cinco...` | **Fechado.** O teste de threads detecta o mutante 4 de 4 vezes e passa 5 de 5 no código real. A trilha `lote_parte` soma 20 e há um único `lote_concluido`. |
| T4 teto 151 e 801 (M18) | `test_limite_acima_do_teto_*` e `test_api_recusa_limite_*` | Fechado. M18 e N40 morrem. |
| **T5** repetição sem `grupos` (A4) | `test_repetir_sem_grupos_com_lote_parcial_recusa_409`, mais o caso complementar de lote completo | **Fechado.** Os dois lados estão cobertos. N15 e N44 morrem. |
| **T6** natureza manual (A2) | 3 testes em `test_dl085_correcao_naturezas.py`, mais o da tela | **Fechado**, mas sem o caso "rascunho vazio entra no lote". N8 sobrevive (R4). |
| T7 devolução na tela | `test_devolucao_de_40_aparece_na_coluna_devolucao_do_grupo` | Fechado. |
| T8 nome acessível | `test_cada_caixa_de_grupo_tem_nome_acessivel_proprio` | Fechado. N23 morre. |
| T9 ordem de travas | Teste determinístico por SQL, mais um teste de threads | O teste determinístico é a guarda real e mata M10, N25 e N26. O de threads usa 1 nota e **passa também sem o ajuste `5ca0d5f`** (N26), então é fraco. |
| T10 orçamento de tempo | 2 testes com relógio falso | Fechado. Confirmei com relógio real. |

## 4. Achados novos

**R1 — Média. A primeira confirmação segura a trava da empresa por um tempo maior que o `lock_timeout` do banco.**
- **Requisito afetado:** concorrência e consistência. O escopo da DL-085 é o alto volume de NFC-e.
- **Local:** `apps/fiscal/escrituracao_nfe_lote.py:1371`. `confirmar_lote` trava a empresa e chama `_criar_lote` (linha 956) dentro da mesma transação. `_criar_lote` recalcula a prévia inteira e grava as linhas do lote. O banco usa `lock_timeout=1210ms` (`config/settings.py:303-306`). O fiscal não traduz o erro de `lock_timeout`, ao contrário da contabilidade (`apps/contabilidade/services.py:497`).
- **Evidência** (`test_rc085_conc.py::test_travamento_da_primeira_chamada`):
  - Com 2.000 notas, a trava ficou presa por 0,51 s. Nada falhou: a criação individual levou 0,27 s, a recepção 0,74 s e o duplo clique devolveu 0 efetivadas.
  - Com 10.000 notas, a trava ficou presa por 3,29 s (sob carga). Todas estas operações caíram com `OperationalError: canceling statement due to lock timeout`:
    - o segundo POST de confirmar (duplo clique), após 1,3 s;
    - a recepção de uma nota nova da mesma empresa, após 1,5 s;
    - a criação individual de rascunho, após 2,53 s.
  - A primeira chamada concluiu normalmente (5 efetivadas, 3,65 s).
- **Impacto:** a partir de cerca de 4.000 notas no mês, enquanto o primeiro POST de confirmação roda, qualquer outra operação sobre a mesma empresa leva 500. Isso inclui um duplo clique e a recepção de XML. A transação é desfeita e nada fica pela metade, então não há perda de dado nem de valor. A causa já existia na versão da rodada 1, e o ajuste `5ca0d5f` não a agrava: o INSERT já pedia KEY SHARE na empresa.
- **Correção recomendada:** calcular a prévia e a assinatura fora da trava. Dentro dela, só reconferir "sem lote em andamento" e inserir. A restrição única parcial do banco já garante um lote em andamento por empresa e mês. Outra opção é traduzir o `lock_timeout` em 409 "tente de novo", como na contabilidade.
- **Como verificar:** repetir o teste com 2.000 notas e `SET lock_timeout='200ms'`. A segunda chamada tem de continuar o lote ou devolver 409, nunca `OperationalError`, e a recepção concorrente não pode falhar.

**R2 — Baixa. A efetivação ainda lê o `xml_original` 3 vezes por nota (A7 residual).**
- **Local:** `escrituracao_nfe.py:589` (`_travar_vinculo` usa `select_related("documento")` sem `defer`), a consulta de escrituração com trava, e o comentário de `escrituracao_nfe_lote.py:79` e `:1196`.
- **Evidência:** `test_rc085_conc.py::test_parte_nao_carrega_xml` falha com 18 consultas com `xml_original` em 6 notas. O detalhe de 3 notas mostra 3 em `fiscal_vinculonfeempresa` e 6 em `fiscal_escrituracaonfe`.
- **Impacto:** carga transitória, sem crescimento de memória. O módulo afirma o contrário no comentário.
- **Correção:** adiar o campo nas duas consultas, ou corrigir o comentário.
- **Verificação:** o mesmo teste, que hoje falha.

**R3 — Baixa. Comentários desatualizados depois do `5ca0d5f` (A8 residual).**
- `escrituracao_nfe_lote.py:1094-1118` (docstrings de `_processar_nota` e `_processar_nota_uma_vez`) ainda dizem que o deadlock com a criação individual "é possível", que a ordem "NÃO evita" o problema e que a individual trava o vínculo antes da empresa. Isso agora é falso.
- Linhas 69-72 do docstring do módulo: o bullet "A primeira leitura de uma nota nunca lida custa uma leitura de XML, documentada acima" ficou duplicado e contraditório com o bullet seguinte.
- O docstring da prévia (linhas 12-18) não lista o motivo `natureza_escolhida`.

**R4 — Baixa. Lacunas de teste que os mutantes sobreviventes mostram.**
- N8: nenhum teste cria rascunho vazio e o põe no lote.
- N13, N14 e N42: o retry de deadlock não tem teste.
- N18 e N18b: nenhum teste cobre a sessão de outra empresa ou outra competência.
- N3: nenhum teste cobre a falha concorrente.
- N20 e N20b: nenhum teste cobre o `defer`.
- Meus testes propostos matam N8, N13, N14 e N42 (verificado). O teste de XML da R2 cobre N20 e N20b, mas falha no código atual.

**R5 — Baixa. WCAG 2.5.3 (rótulo no nome).** Em `templates/fiscal/nfe_lote.html:191-192`, o `aria-label` ("Incluir o grupo 1: CFOP ...") não contém o texto visível "Incluir este grupo". Quem usa comando de voz não consegue acionar a caixa pelo rótulo que enxerga. Correção: iniciar o `aria-label` com o texto visível.

**R6 — Baixa. A4 devolve 409 também na repetição legítima depois que chega nota de grupo novo.**
- Evidência: `test_rc085_a4.py`. Com o lote parcial em andamento e uma nota nova de outro grupo, repetir a primeira chamada com a mesma assinatura dá `LoteEmAndamento`. A continuação por `lote_id` funciona.
- Impacto: só quem repete a primeira chamada (API, ou resposta perdida) recebe o 409.
- A mensagem já aponta para o `lote_id`. Basta registrar.

**R7 — Baixa. Backlog do avanço automático ausente.** O plano diz que o avanço automático das partes "vai para o backlog" (`DL-085...md:148`), mas `docs/projeto/backlog.md` não tem esse item.

**R8 — Baixa (DL-086). Superfícies de texto sem guarda.**
- Os mutantes D2 a D6 sobreviveram, ou seja, a frase antiga pode voltar sem teste falhar. São eles: o texto do cartão (`module_homes.py`), o do seletor (`tenancy/views.py`), o `mh-availability` e os dois trechos de `landing.html`. Só o banner (D1) é guardado.
- A guarda de README e estado é lista de 4 frases exatas. Reinserir "Planejado — DL-010" no README e "Recepção e consulta de NFS-e nacional" no estado foi detectado. Uma paráfrase ("O fiscal só recebe NFS-e") passou, e "Escrituração de documentos | Não existe" no mapa-funcional também.
- As afirmações das I7 a I17 não são guardadas.
- Isso é a "guarda derivada de lista" que o AGENTS.md §8 declara frágil.

**R9 — Baixa (DL-086). Texto remanescente ou impreciso.**
- `templates/registration/public_base.html:4`: o comentário diz que o Fiscal "hoje é só recepção/consulta de NFS-e". A meta description (linha 9) cita só NFS-e.
- `apps/tenancy/views.py:637`: a ação rápida continua "Receber NFS-e".
- O banner diz "não escritura notas de entrada" (`module_homes.py:918`). NFS-e tomadas, que são entrada de serviço, são escrituradas, assim como a devolução recebida como entrada própria. O texto devia dizer "compras de mercadoria".
- A landing marca o card do Fiscal como "Disponível" e o texto do herói diz "apuração fiscal ... hoje", mas só com a ressalva "para conferência".

**R10 — Baixa (DL-086). I4 ainda presente, fora do escopo declarado do plano.**
- `docs/agents/estado.md` mantém "Medido em 25/09/2026 ... remedido em 30/09/2026" no Resumo e "Linha de base vigente ... 8.791 aprovados". A linha de base atual é outra (8.961 na minha execução).
- O README repete numa frase o estado do Fiscal, o que contraria a regra de fonte única do CLAUDE.md. É o mesmo padrão que já existia.
- O plano da DL-086, no escopo 3, promete indicadores de NF-e no painel. O `estado.md` explica que não foram entregues (BL-681 item 2), mas o plano não foi anotado.

## 5. Medidas

**Deadlock lote × criação individual** (`test_lote_x_individual_stress`: 1 lote e 2 criadores individuais em ordens opostas, 59 notas, 3 execuções por versão):

| Versão | Deadlocks por execução | Resultado |
| --- | --- | --- |
| Corrigida (`5ca0d5f`) | 0, 0, 0 | lote com 59 efetivadas, sem erro propagado |
| Sem a trava da empresa na criação individual (N26) | 1, 1, 2 | o retry do lote absorveu todos (59 de 59, sem erro propagado) |

**Serialização da criação individual** (mesma empresa, notas diferentes, 160 notas por rodada, 2 repetições, sob carga):

| Cenário | Tempo total | Por criação |
| --- | --- | --- |
| 1 thread, corrigida | 2,14 a 2,48 s | 13,4 a 15,5 ms |
| 4 threads, corrigida | 2,34 a 2,49 s | média 58 a 62 ms (p95 67 a 82 ms, máx. 101 a 128 ms) |
| 4 threads, sem a trava (N26) | 1,57 a 1,69 s | média 39 a 41 ms |

Conclusão: a criação individual da mesma empresa ficou serializada, com teto de cerca de 65 a 70 criações por segundo. Com 4 criadores simultâneos o custo é cerca de 45 a 50% a mais no tempo total. Por criação, são cerca de 15 ms de fila. O `lock_timeout` de 1,21 s comportaria dezenas de criadores na fila, muito acima do uso real. Para usuários distintos em empresas distintas não há efeito.

**Volume com 2.000 NFC-e** (HTTP, Django client, sob carga):

| Etapa | Medido | Rodada 1 |
| --- | --- | --- |
| Envio | 9,05 s | 7,64 s |
| GET prévia sem leitura | 0,58 s | 0,68 s |
| POST ler 400 | 5,1 a 5,3 s | 4,4 a 4,6 s |
| GET prévia já lida | 0,44 s | 0,52 s |
| Confirmar, 1ª chamada | 5,70 s | 4,68 s |
| Parte de 100 | 4,7 a 5,4 s (média 4,98 s em 20 chamadas) | 3,98 a 4,66 s |
| Conferência do mês | 0,36 s | 0,44 s |

Resultado final: 2.000 efetivadas, 0 falhas, soma efetivada 3.298.570,00 igual à soma gerada.

**Memória** (tracemalloc, teste do desenvolvedor, `DL085_MEDIR_MEMORIA=1`):

| Cenário | Prévia sem leitura | Prévia já lida |
| --- | --- | --- |
| 2.000 notas | 8,0 MB (rodada 1: 14,2) | 13,4 MB (rodada 1: 24,3) |
| 10.000 notas | 39,7 MB (rodada 1: 70,7) | 63,6 MB (rodada 1: 118,9) |

A memória ainda cresce com o tamanho do mês (a redução é de cerca de 45%). A leitura de 800 notas com 10.000 no mês levou 12,55 s: cerca de 2,4 s de preparação mais o orçamento de 10 s. A preparação das chamadas cresce com o mês e fica fora do orçamento. Não testei acima de 10.000 notas.

## 6. Equivalência lote × individual

O roteiro tem 33 notas por empresa, das quais 24 são elegíveis, mais cancelada, entrada e outro mês. A empresa A foi pelo lote (4 partes) e a B nota a nota pela API.
- **Resultado:** as 24 notas coincidem em estado, tipo, competência, `data_emissao`, `valor_nf`, `soma_itens`, receita, devolução, naturezas por item e trilha por nota.
- **Receitas:** conferidas contra valores escritos à mão, incluindo ICMS desonerado, frete, `indTot=0` e devolução.
- **Fora do lote:** `por_motivo` bate com o esperado (atribuição 1, conflito 1, ilegível 1, sem sugestão 2, W16 1).
- **Variante com 4 rascunhos preexistentes:** 23 notas iguais; a nota com natureza `bonificacao` fica rascunho intacta, com o motivo `natureza_escolhida`.

## 7. Mutantes

Rodei 52 mutantes sobre o código da correção, cada um contra os testes `test_dl085_*` (151 testes). Resultado: **36 mortos e 16 sobreviventes.**

- **Mortos:** M2, M3, M4a, M4a2, M4c, M10, M18, M21, M26, M31, M32, M33, N1, N4 a N7, N9 a N11, N15 a N17b, N19, N21 a N23, N25 a N27, N40, N41, N43, N44 e D1.
- **Sobreviventes da rodada 1:**
  - M4a, M18, M21, M26 e M33 agora morrem.
  - M10 também morre, por causa do teste determinístico de ordem de travas.
- **Sobreviventes da DL-085 (11):** N2, N3, N8, N13, N14, N18, N18b, N20, N20b, N28 e N42.
  - N2 e N28 são equivalentes na prática: N2 é um ramo defensivo inalcançável, e N28 produz o mesmo conjunto de grupos.
  - Os demais são lacunas de teste (R4).
- **Sobreviventes da DL-086 (5):** D2 a D6, os textos do cartão, do seletor, da disponibilidade parcial e da landing (R8).
- **Guarda de documentação:** mutação reinserindo frase desmentida em README e estado é detectada. A paráfrase passa (R8).

## 8. DL-086 — I1 a I19

| # | Situação | Observação |
| --- | --- | --- |
| I1 | Corrigida | Linha do Fiscal no Resumo reescrita (`estado.md:33`). Capacidades conferidas contra o código. |
| I2 | Corrigida | A linha "Não existe" lista só o que falta de fato. |
| I3 | Corrigida | DL-067 aparece como "Plano integrado ... em execução desde 08/10/2026 (RC-164)". |
| I4 | **Ainda presente** | Datas de medição e linha de base antigas no `estado.md`. Fora do escopo declarado (R10). |
| I5 | Corrigida | README:31. Duplica o estado numa frase (R10). |
| I6 | Corrigida | README:54 "Em construção — DL-067". |
| I7 | Corrigida | `paridade/fiscal.md`: tabela de capacidade por DL e situação de 13 itens FIS corrigidas. Verifiquei contra o código: `tpRetISSQN` usado em `retencoes.py` e `iss_nota.py`, a recusa de 2027 cita a Res. CGSN 190/2026, o bloqueio HI-122 existe. |
| I8 | Corrigida | `mapa-funcional-fiscal.md`: tabelas "O que já existe" e "DataLedger". |
| I9 | Corrigida | Linhas de importação e movimento. |
| I10 | Corrigida | `catalogo-de-relatorios.md`. |
| I11 | Corrigida | Banner conferido capacidade por capacidade. Ver R9. |
| I12 | Sem divergência | Já era coerente. |
| I13 | Corrigida | DL-067 aponta para PE-90 e HI-145. |
| I14 | Corrigida | Linhas "a numerar" apontam para DL-074, DL-075, DL-073 e DL-076. |
| I15 | Corrigida | Item 11 do estado aponta para o item 15. A linha da DL-082 aponta para o Próximo passo. |
| I16 | Corrigida | Nota de 09/10/2026 na DL-072. |
| I17 | Corrigida | Seis relatórios de conferência listados. |
| I18 | Sem divergência | Já era coerente. |
| I19 | Não tratada | Era "inferido" e fora do escopo do plano. |

Os textos de página inicial, cartão, seletor e disponibilidade parcial dizem a verdade nos pontos principais. Cada capacidade citada existe no código, e cada ausência citada é real. Ressalvas em R9.

## 9. Verificações executadas

| Item | Resultado |
| --- | --- |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 601 files already formatted |
| `python manage.py check` | System check identified no issues (0 silenced) |
| `makemigrations --check --dry-run` | No changes detected |
| `pytest` completo, uma invocação, `-W ignore` | **8961 passed, 1 failed, 55 skipped, 4 subtests passed em 1058,21 s** |
| Falha única | `test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`: `SyntaxError ... must be parenthesized` do Python 3.13 (a CI usa 3.14). É a falha de ambiente conhecida. |
| `test_corrida_real_de_evento_produz_um_unico_evento` | Passou nesta execução, mesmo com a máquina sob carga. |
| Testes `test_dl085_*` | 153 coletados (rodada 1: 129). Os 24 novos fazem parte da suíte completa. |
| Migrações | A correção não adicionou migração. `makemigrations` limpo. |
| Documentação | `pwsh` indisponível. Reimplementei `validate-docs.ps1` em Python: 301 arquivos `.md`, 0 problemas (UTF-8, título, espaço no fim, nova linha final, links relativos). `gerar_agentes.py --verificar`: OK. |
| Efeitos colaterais | `git status` e `git diff` vazios. |

**Navegador real (Chromium)** — fluxo completo com 116 notas: ler, prévia, confirmar, continuar, concluído.
- Coluna "Devolução" com 40,00.
- Nome acessível único por grupo.
- O redirect aconteceu e a recarga não reenviou o POST.
- Não houve rolagem horizontal no documento.
- O único erro de console foi o 404 de `favicon`, como na rodada 1.

## 10. Testes propostos (texto para o responsável)

- **P1 (N8):** três NFC-e de revenda. Nota 1 com rascunho vazio, nota 2 com rascunho com a natureza `revenda`, nota 3 de dois itens com rascunho que define só o item 1. Afirmar prévia sem notas fora e `efetivadas_total == 3`. Versão pronta: `test_rc085_equiv2.py`.
- **P2 (N13, N14, N42):** simular `OperationalError` com `DeadlockDetected` duas vezes e depois sucesso (3 chamadas, `efetivada`). Três falhas repassam o erro. `AdminShutdown` não repete (1 chamada). Versão pronta: `test_rc085_conc.py::test_retry_de_deadlock_simulado`.
- **P3 (N18, N18b):** com progresso na sessão da empresa A, um GET da empresa B (e de outro mês) não mostra o progresso.
- **P4 (R2, N20, N20b):** `test_parte_nao_carrega_xml`, que hoje falha.
- **P5 (R1):** primeira confirmação com muitas notas e `lock_timeout` curto. A segunda chamada continua ou devolve 409, e a recepção concorrente não levanta `OperationalError`.
- **P6 (R5):** o nome acessível contém o texto do rótulo visível.
- **P7 (R8):** testes para o texto do cartão (`montar_home`), do seletor (`_modulos_do_painel`), do `mh-availability` e da landing (herói e card).
- **P8 (N3):** `_gravar_estado` devolvendo `False` no ramo de falha faz `_processar_nota` devolver `("outra_chamada", "")`.

## 11. O que não foi testado

- PostgreSQL remoto ou com latência.
- Meses com mais de 10.000 notas: a preparação das chamadas e a trava de R1 crescem com o tamanho do mês.
- Composição da receita e apuração do Presumido com 10.000 notas, e mês "a retificar" em escala.
- Leitor de tela real.
- Recepção concorrente durante as partes seguintes (testei só durante a primeira chamada).
- Mobile em 390 px (não repeti).
- CI do GitHub, `validate-docs.ps1` oficial (usei reimplementação), Python 3.14.
- Probabilidade real de deadlock em produção.

Os tempos absolutos foram medidos sob carga de outro processo e só valem em comparação com as medidas alternadas.
