# Reconferência da DL-091 — 13/10/2026

## Parecer

**APROVADA COM RESSALVAS.**

- **A1 (alta) está resolvido e verificado de ponta a ponta.** Um comprador do Simples nunca recebe crédito elegível. Isso vale para a memória gravada, a conferência e as telas. Regime desconhecido ou ambíguo no dia fica "a conferir". A troca de regime no meio do ano segue a data de entrada.
- **Não há bloqueador nem achado de gravidade alta ou média.**
- **Os 13 achados:**
  - Resolvidos: A1 a A12.
  - Encaminhado ao BL-706 por decisão registrada: A13.
- **Ressalvas:** cinco achados novos, todos de gravidade baixa (N1 a N5, abaixo). Duas lacunas de teste e um efeito do rascunho legado são ressalvas de teste. Duas são de documento ou texto. Nenhuma esconde falha essencial.
- **Suíte completa:** 10.403 passaram e 1 falhou. A falha é `test_versao_minima_python`, de ambiente (Python 3.13 local, CI em 3.14).
- **Não executado:** `pwsh ./scripts/validate-docs.ps1` (`pwsh` ausente) e navegador real. Ver "O que não foi testado".

## Versão e ambiente

- **Cópia:** `/home/user/wt-rc091`, commit `8e4bd7a`, destacada. A árvore ficou limpa (`git status --short | wc -l` deu `0`). Não criei branch nem commit.
- **Diff auditado:** `git diff 8a05489 8e4bd7a -- apps templates`. São 22 arquivos, com 1.917 linhas a mais.
- **Interpretador:** Python 3.13, PostgreSQL local. Banco `rc_dl091`, mais `rc_dl091_p` (sondas), `rc_dl091_m` (migrações) e `rc_dl091_mm*` (mutantes). Todos foram apagados no fim.
- **Cópias de trabalho:** sondas e mutantes rodaram em cópias `git archive 8e4bd7a` no scratchpad. Os mutantes foram apagados. As sondas ficaram em `.../scratchpad/rc091/copia/apps/fiscal/tests/test_rc_probe_*.py`.

## Tabela A1 a A13

| # | Achado | Estado | Evidência executada |
| --- | --- | --- | --- |
| A1 | Comprador do Simples com crédito elegível | **Resolvido (Testado)** | P1: `MARCA sem_credito_optante_do_simples None` e `CONF credito elegivel 0.00`. Matriz Q1 e demais sondas na seção "A1 em profundidade". |
| A2 | `DEVOLUCAO_COMPRA` reabre o mês confirmado | **Resolvido (Testado)** | P15: março `confirmada` antes e depois, e a fotografia do pré-DAS igual. O estorno também não reabre (teste do desenvolvedor, mutante R06 morto). |
| A3 | Reclassificação em massa com compra em rascunho | **Resolvido (Testado)** | P9: a venda vira `revenda` e a natureza E4 é recusada só pela venda. P10: a compra fica E1/1.102, sem incoerência. Q6 (venda, compra e devolução de compra juntas): só a venda mudou. |
| A4 | Lote sobrescreve o CFOP de entrada escolhido | **Resolvido (Testado)** | P2: `ANTES 1113`, `FORA [('9001','natureza_escolhida')]`. A revalidação na efetivação é coberta pelo teste do desenvolvedor, e os mutantes R08 e R09 morrem. |
| A5 | Autorização e trilha sem teste | **Resolvido (Testado)** | M20, N06, N07 e N08 agora morrem. P5: PARALEGAL 403, outro escritório 404, anônimo 403, data intacta. |
| A6 | Conferência de saída e segunda camada de receita | **Resolvido, com 1 equivalente** | N13, M04, M13 e M13b morrem. N14 sobrevive, mas não muda resultado (ver Mutantes). |
| A7 | Regime pela data e avisos | **Resolvido (Testado)** | N19, M17 e N10 morrem. |
| A8 | Compra em 2027, escolha no lote, CFOP em saída | **Resolvido (Testado)** | N04, N31, N25 e N17 morrem. P13 e Q11 (emissão futura no lote) efetivam. |
| A9 | N+1 na tela e na API | **Resolvido (Testado)** | Tela com 2 e 30 itens: de 29 e 82 consultas para 26 e 23. API: de 17 e 101 para 13 e 13. Na efetivada (Q8): 23 e 20 na tela e 13 e 13 na API. R14, R15 e R17 morrem. |
| A10 | `aria-describedby` com id inexistente | **Resolvido (Inspecionado e Testado)** | Template corrigido. R16 morre no teste que confere todo IDREF. |
| A11 | Data de entrada sem limite superior | **Resolvido (Testado)** | P7: 2062 e 9999 recusadas com motivo nomeado, nota continua em 03/2026. Teto e fuso na seção "Regressões". |
| A12 | Texto do estorno | **Resolvido (Testado)** | Q9: "A compra não compõe a receita…", sem os campos de receita. R13 morre. Ver N4 sobre o termo "compra". |
| A13 | Tela da compra sem ação em bloco | **Fora do escopo desta rodada** | Foi para o BL-706 (1) por decisão do arquiteto. Não é critério de aceite. |

### A1 em profundidade (Testado)

Cada linha foi efetivada de verdade, com `HistoricoRegimeTributario`, pela efetivação, memória gravada e conferência. As colunas mostram a marca e o crédito gravados; a conferência bateu com a soma.

| Regime do comprador | Fornecedor CRT 3, CST 00, `vICMS` 18,00 | CRT 1 com `pCredSN` e 28,00 | CRT 1 sem `pCredSN` (CSOSN 101 e 102) |
| --- | --- | --- | --- |
| Simples | `sem_credito_optante_do_simples`, crédito `None` | idem | idem |
| Presumido | `credito_destacado`, 18,00 | `credito_limitado_ao_informado`, 28,00 | `sem_credito_sem_pcredsn`, `None` |
| Real | `credito_destacado`, 18,00 | `credito_limitado_ao_informado`, 28,00 | `sem_credito_sem_pcredsn`, `None` |
| Sem regime cadastrado | `a_conferir`, `None` | idem | idem |

- Conferência: Simples e "sem regime" dão 0,00. Presumido e Real dão 18,00 e 28,00 nas células com crédito, e 0,00 na terceira coluna.
- **Troca de regime no meio do ano** (Simples até 30/06/2026, Presumido desde 01/07):

| Nota | Data de entrada | Resultado |
| --- | --- | --- |
| Emitida 15/03 | 15/03 | optante |
| Emitida 10/08 | 10/08 | normal, 18,00 |
| Emitida 15/06 | 05/07 | normal, 18,00 (a data de entrada decide, não a emissão) |
| Emitida 30/06 | 30/06 | optante |
| Emitida 30/06 | 01/07 | normal |

- **Regime ambíguo no dia** (Simples e Presumido sobrepostos em 15/03): `a_conferir`, `None`.
- **Telas:**
  - Rascunho, nota efetivada e conferência mostram o rótulo "Sem crédito: comprador optante do Simples (LC 123, art. 23, caput)".
  - Nenhuma mostra "Crédito destacado: elegível".
  - O total da conferência é 0,00.
  - O cabeçalho "Crédito elegível" da tabela da nota efetivada é só título de coluna.
- **Isolamento do contexto (Q7):**
  - Duas empresas do mesmo escritório (Simples e Presumido) foram lidas em sequência alternada, em API e tela, em duas rodadas.
  - Cada uma sempre devolveu a própria marca, sem vazamento entre requisições.
  - Outro escritório recebeu 404 na API e na tela.
  - Consultar a escrituração de uma empresa pela rota de outra deu 404.
  - O contexto é calculado dentro da requisição, sem `lru_cache` nem variável de módulo.

### Regressões da correção (R1, R2…)

- **R1 — Teto da data de entrada (Testado).**
  - Hoje é aceito e amanhã recusado, com o motivo "posterior a hoje".
  - Anterior à emissão continua recusado.
  - Com emissão futura (hoje + 10 dias): a data padrão (= emissão) é aceita, emissão + 1 é recusada, hoje é recusado por ser anterior à emissão. O lote efetiva essa nota normalmente (Q11).
  - Fuso, com `timezone.now` fixo em 01h30 UTC de 14/10 (22h30 em SP, ainda dia 13): 14/10 recusada, 13/10 aceita. Com 03h30 UTC (00h30 do dia 14 em SP): 14/10 aceita.
  - **Sem regressão.** Resíduo em N2 e N3.
- **R2 — Reclassificação (Testado).** A venda reclassifica. A compra e a devolução de compra em rascunho ficam intactas. A natureza de entrada com venda no filtro continua recusada pela venda, com a mensagem de antes.
- **R3 — Lote (Testado).** Nota com CFOP igual ao sugerido entra. Nota com CFOP diferente sai do lote com `natureza_escolhida`. A revalidação da efetivação também recusa. Nota de saída não ganha comparação de CFOP, porque `zip(strict=True)` tem listas de mesmo tamanho nos dois ramos.
- **R4 — Resíduo declarado da saída própria (Testado).** Q10: saída própria com `finNFe` 1 e natureza `devolucao_compra` ainda reabre março (`a_retificar`). Está declarado no BL-706 (5). É coerente com o que recomendei na rodada 1, e a repetição (efetivar e estornar) não depende do tipo.

## Achados novos

Todos de gravidade **baixa**.

- **N1 — Efetivação não revalida o teto da data de entrada.**
  - **Local:** `apps/fiscal/entradas.py`, `efetivar_entrada`, por volta das linhas 764-768, que só confere `data < emissão`.
  - **Evidência (Inspecionado):** `validar_data_de_entrada` só é chamada na criação do rascunho e na troca de data.
  - **Impacto:** só afeta rascunho gravado antes da correção com data futura (nenhum deve existir, pois a DL-091 ainda não foi liberada). Nenhuma data fica futura com o passar do tempo.
  - **Correção recomendada:** `efetivar_entrada` chama `validar_data_de_entrada` também, ou o texto do plano declara a omissão.
  - **Verificação:** rascunho gravado direto no ORM com data de 2062 não efetiva.
- **N2 — `hoje_em_sao_paulo` sem teste que a proteja (R12 sobreviveu).**
  - **Local:** `entradas.py:186-190`, onde o mutante troca `astimezone(FUSO_SP)` por `.date()` do UTC.
  - **Comportamento atual:** correto (Q4c). A regressão deixaria entrar a data de amanhã entre 21h e 24h em SP.
  - **Teste proposto:** `timezone.now` fixo em 2026-10-14 01:30 UTC. `definir_data_de_entrada(14/10)` deve ser recusada e `13/10` aceita.
- **N3 — Exclusão da `DEVOLUCAO_COMPRA` na reclassificação sem teste (R07b sobreviveu).**
  - **Local:** `escrituracao_nfe.py:1765`.
  - **Evidência:** com só `ENTRADA` excluída, a sonda Q6 falha com a recusa "não cabe". O comportamento atual está certo, mas nenhum teste do desenvolvedor o protege.
  - **Teste proposto:** a venda e uma devolução de compra (5.202, `finNFe` 4, natureza `devolucao_compra`) em rascunho. `reclassificar_em_massa(empresa, "revenda", Filtros())` altera 1 nota e deixa a devolução intacta.
- **N4 — Conferência sem teste de defesa para marca não elegível com valor (R04 sobreviveu).**
  - **Local:** `conferencia_entradas.py:219-227`.
  - **Evidência:** nenhuma entrada gerada pelo código traz valor em marca não elegível. O filtro só protege contra linha anômala.
  - **Teste proposto:** criar `MemoriaEntradaItemNFe(marca_credito=optante, credito_elegivel=18.00)` direto no ORM e esperar total 0,00. Memória antiga gravada com a marca errada não é corrigida (ver "Não testado").
- **N5 — Documento e texto.**
  - `docs/projeto/requisitos.md`, HI-158, não menciona o teto "posterior a hoje" (só consta no plano).
  - O texto de estorno da `DEVOLUCAO_COMPRA` diz "A escrituração da compra nº…". Para devolução, "devolução de compra" seria mais exato (`templates/fiscal/nfe_estornar.html:33-38`).
  - **Verificação:** leitura da HI-158 e do template.

## Mutantes

Base: `test_dl091_*.py` mais `test_dl081*` (N13, N14, M04), `test_dl082*` (R05), os de reclassificação (R07, R07b) e `test_dl087_telas_acessibilidade` (R16). Cada execução rodou com `-x`.

### Os 15 pedidos

| Id | Resultado | Teste que mata |
| --- | --- | --- |
| M20 | **Morto** | `test_troca_de_data_de_entrada_recusa_quem_so_consulta_com_403[paralegal]` |
| M17 | **Morto** | `test_id_dest_2_sozinho_gera_aviso_de_simples_quando_nao_ha_uf_da_matriz` |
| N06 | **Morto** | `test_troca_de_data_e_de_natureza_deixam_trilha_com_antes_e_depois` |
| N07 | **Morto** | mesmo teste |
| N08 | **Morto** | `test_troca_de_data_em_escrituracao_efetivada_responde_409_e_nao_muda_a_data` |
| N10 | **Morto** | `test_cfop_6_com_emitente_da_uf_da_empresa_gera_aviso_de_uf_incoerente` |
| N13 | **Morto** | `test_compras_do_mes_nao_mudam_os_numeros_da_conferencia_de_saida` |
| N14 | **Sobreviveu: equivalente** | 628 passaram. Em `conferencia_do_mes` o `continue` da `ENTRADA` vem antes de somar `sem_sugestao`, então a saída não muda. O efeito é só trabalho desperdiçado. |
| N19 | **Morto** | `test_aviso_de_outro_estado_segue_a_data_de_entrada_e_nao_o_regime_de_hoje` |
| N04 | **Morto** | `test_compra_de_2027_entra_no_lote_e_efetiva_no_presumido` |
| N31 | **Morto** | `test_detalhe_da_compra_de_2027_nao_mostra_bloqueio_da_regra_de_receita` |
| N25 | **Morto** | `test_escolha_de_natureza_no_lote_grava_o_cfop_final_da_natureza_escolhida` |
| N17 | **Morto** | `test_api_recusa_cfop_de_entrada_em_escrituracao_de_saida` |
| M04 | **Morto** | `test_compra_com_natureza_de_receita_gravada_no_banco_nao_entra_na_receita` |
| M13 | **Morto** | `test_totais_da_conferencia_de_entradas_ignoram_escrituracao_de_outra_empresa` |
| M13b | **Morto** | mesmo teste |

Resultado: 14 dos 15 pedidos morrem, e o sobrevivente (N14) é equivalente.

### Meus mutantes novos (19)

| Id | Mutação | Resultado |
| --- | --- | --- |
| R01 | Remove o desvio do Simples em `marca_do_credito` | Morto |
| R02 | Remove a recusa de regime ambíguo | Morto |
| R03 | Remove a recusa de regime desconhecido | Morto |
| R04 | Conferência soma qualquer marca com valor | **Sobreviveu** (N4) |
| R05 | `DEVOLUCAO_COMPRA` reabre ao efetivar | Morto |
| R06 | `DEVOLUCAO_COMPRA` retifica ao estornar | Morto |
| R07 | Reclassificação não exclui `ENTRADA` | Morto |
| R07b | Reclassificação não exclui `DEVOLUCAO_COMPRA` | **Sobreviveu** (N3, confirmado pela sonda Q6) |
| R08 | Lote ignora o CFOP gravado diferente | Morto |
| R09 | Revalidação do lote ignora o CFOP sugerido | Morto |
| R10 | Teto da data é só `hoje` (sem `max` com emissão) | Morto |
| R11 | Teto da data é só a emissão | Morto |
| R12 | `hoje` em UTC em vez de SP | **Sobreviveu** (N2) |
| R13 | Estorno da devolução de compra volta ao texto de receita | Morto |
| R14 | `previa_do_item` sempre relê o contexto | Morto |
| R15 | API volta a ler memória por item | Morto |
| R16 | `aria-describedby` volta ao id inexistente | Morto |
| R17 | Tela deixa de passar o contexto | Morto |
| R18 | Inverte `simples` em `contexto_da_entrada` | Morto |
| R19 | Renomeia o valor da marca nova | Sobreviveu à suíte de testes, mas `makemigrations --check` acusa a migração `0024`. Não é falha de teste. |

Resultado: 15 mortos, 3 sobreviventes (R04, R07b, R12) e R19 pego pelo `makemigrations`. Os 3 sobreviventes não escondem comportamento errado hoje (todos se confirmam corretos), mas viram as lacunas N2 a N4.

## Verificações

| Comando | Saída |
| --- | --- |
| `pytest apps/fiscal/tests/test_dl091_*.py -q -p no:cacheprovider` (cópia auditada) | `261 passed in 47.38s` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `694 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate` (banco vazio) | OK |
| `migrate fiscal 0020` | `Unapplying 0023… OK`, `0022… OK`, `0021… OK` |
| `migrate fiscal 0022` e `migrate` (ida) | `Applying 0021, 0022` e depois `0023… OK` |
| `migrate fiscal 0022` e `migrate` (volta e ida do 0023) | `Unapplying 0023… OK` e `Applying 0023… OK` |
| Volta de `0020` com 1 escrituração de entrada | `RuntimeError: Reversão da DL-091 recusada, sem alterar nada: 1 escrituração(ões) de entrada…`. `showmigrations`: 0021 e 0022 aplicadas, 0023 desfeita, nada alterado. |
| Suíte completa, uma invocação: `pytest -q -p no:cacheprovider -rs --no-header` | `1 failed, 10403 passed, 56 skipped, 2 warnings, 4 subtests passed in 1654.97s (0:27:34)` |
| Falha única | `SyntaxError: multiple exception types must be parenthesized` (`apps/core/tests/test_versao_minima_python.py`), de ambiente |
| `git status --short \| wc -l` na cópia auditada | `0` |

A suíte completa inclui `apps/fiscal`, `apps/core` e `apps/contabilidade`. Nenhum teste de rotas, restrições ou trilha regrediu.

**Verificação manual da documentação** (sem `pwsh`): nos cinco `.md` tocados (`estado.md`, o plano da DL-091, `backlog.md`, `requisitos.md` e o relatório da rodada 1) conferi título `# `, nova linha final, ausência de espaço no fim da linha e existência dos links relativos. Tudo ok. Não substitui `validate-docs.ps1`.

**Sondas executadas:**

- **P1, P2, P3, P5, P6, P7, P8, P9, P10, P13, P14, P15 e P16:** repetidas sobre `8e4bd7a`.
- **Q1 a Q11 (novas):** estas foram as mais longas.
- **Contagem de consultas** (P11/P12, lote): compra 51 a 56 por nota e venda 47 a 52, igual à rodada 1.

## O que não foi testado

- **Navegador real:** só inspecionei o HTML renderizado pelo `client` do Django. Playwright e Chromium não estão disponíveis, e os testes que dependem deles foram pulados na suíte (56 ignorados). Nenhum teste visual ou de foco.
- **Python 3.14:** só rodei no 3.13. A falha `test_versao_minima_python` é desse ambiente.
- **`pwsh ./scripts/validate-docs.ps1`:** não executado (`pwsh` ausente). Substituí por conferência manual parcial.
- **Memória já gravada antes da correção:** a migração `0023` só altera `choices`, sem migrar dados. Se algum comprador do Simples já tiver memória gravada como `credito_destacado`, ela fica e a conferência continua somando. Presumo que não exista dado assim, porque a DL-091 está em auditoria, mas não verifiquei produção.
- **Concorrência:** não exercitei duas efetivações simultâneas. A correção não mexeu na ordem de bloqueios.
- **Escala:** o lote e a tela não foram medidos com milhares de notas. Só a contagem de consultas de 2 e 30 itens.
- **Normas:** não reli LC 87, LC 123 ou LC 192. O art. 23, caput, da LC 123 segue como fonte secundária da consulta do `contador-senior`. A regra de A1, a lista de NCM monofásico e o PE-93 dependem de validação do Fred.
- **BL-706:** os resíduos (ação em bloco, retorno em `finNFe` 4, NCM de gasolina e diesel, `vICMSMono`, saída própria com `devolucao_compra`) estão registrados. Só repeti a última (Q10).

## Arquivos relevantes

- Código auditado (`/home/user/wt-rc091`):
  - `apps/fiscal/entradas.py`
  - `apps/fiscal/conferencia_entradas.py`
  - `apps/fiscal/escrituracao_nfe.py`
  - `apps/fiscal/escrituracao_nfe_lote.py`
  - `apps/fiscal/api_escrituracao_nfe.py`
  - `apps/fiscal/views_web.py`
  - `apps/fiscal/models.py`
  - `apps/fiscal/migrations/0023_dl091_marca_optante_do_simples.py`
  - `templates/fiscal/nfe_escriturar_entrada.html`
  - `templates/fiscal/nfe_estornar.html`
- Testes novos do desenvolvedor: `apps/fiscal/tests/test_dl091_rodada1_*.py` (8 arquivos).
- Documentos: `docs/planos/DL-091-nfe-de-entrada.md`, `docs/projeto/requisitos.md` (HI-155, HI-158), `docs/projeto/backlog.md` (BL-706), `docs/agents/estado.md`.
- Sondas, mutantes e logs (descartáveis, fora do repositório), em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc091/`:
  - `copia/apps/fiscal/tests/test_rc_probe_a1.py`, `test_rc_probe_b.py`, `test_rc_probe_c.py`, `test_rc_probe_d.py`
  - `mutar_rc.py`
  - `mutantes.json`
  - `mut_resultado.txt`
  - `suite_completa.txt`

Auditoria de software não substitui validação profissional das regras contábeis e legais.
