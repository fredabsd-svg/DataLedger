# Reconferência da DL-082 — 09/10/2026

## Parecer: APROVADA COM RESSALVAS

Dos 13 achados da rodada 1, 12 estão fechados. O A10 foi mantido por decisão do arquiteto, com a exceção registrada. Nenhum dos 13 ficou aberto. Os valores que prometi conferir bateram ao centavo, pela execução do pré-DAS real contra o meu oráculo em `Fraction`.

Encontrei 7 achados novos (R1 a R7), todos de gravidade baixa. Nenhum é bloqueador nem de gravidade alta. Dois deles são os resíduos que o desenvolvedor declarou. Mostro que um é mais amplo do que o declarado.

Esta é auditoria de software. Não substitui a validação do contador sobre as regras (HI-125 a HI-132) nem a conciliação com o PGDAS-D real (PE-86 e PE-87).

## Versão e ambiente

- Árvore `/home/user/wt-rc082`, commit `5e36a47`, com a correção `8e18d59`.
  - O `git status` ficou limpo no início e no fim.
  - Não executei nada dentro dela, exceto um teste só de leitura (`scripts/test_decidir_caminhos_vigiados.py`).
- Python 3.13.16 local (a CI usa 3.14), PostgreSQL 16, Django 6.1.
- Trabalhei em cópias sem `.git`, em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc082/`:
  - `copia/`: meus testes `test_rc082_casos.py`, `test_rc082_sondas2.py` e `test_rc082_telas.py`, mais os `test_aud082_*` da rodada 1.
  - `limpa/`: árvore intocada, onde rodei a suíte completa e as verificações estáticas.
  - `mut/`: árvore dos mutantes.
  - `mutar_rc.py`: o script dos mutantes.
  - `mutantes_rc.txt` e `suite_completa.log`: os resultados.

## Tabela A1 a A13

| # | Situação | Evidência executada |
| --- | --- | --- |
| A1 | Fechado | Venda 5102 mais devolução 1202 pelo lote: a devolução sai em `fora` com `devolucao_segmento_a_confirmar` ("escriture esta nota individualmente"). Só a saída própria foi efetivada. A recusa da devolução efetivada sem segmento agora diz que a nota precisa de estorno (Testado, mutantes N1 e N12 mortos). Ver R3 e R6. |
| A2 | Fechado para o mês, parcial no histórico | Devolução 1660, 1661, 1662, 2660, 2661 e 2662 com natureza `devolucao_venda`: todas recusam com `devolucao_combustivel_cfop`. O caso 2.157,01 virou recusa (Testado). A devolução de compra (5661) não é essa recusa. O mês seguinte ainda carrega o saldo, ver R1. |
| A3 | Fechado | Caso 1503: total 3.494,50 (interno II 3.076,00 mais externo II 418,50), igual ao oráculo. Confirmar `PRODUCAO` para 1503 é recusado. 2503, 1505 e 2505 dão 3.494,50. 1504 com venda 5502: 3.480,00, que é 3.076,00 mais 404,00 (Anexo I externo). A sugestão de segmento aponta exportação. Ver R4. |
| A4 | Fechado | Exportação 7102, idDest 3, de 20.000, com CSOSN 102, 500, 900, 300, 400 e 103: todas calculam 404,00. O 900 gera aviso. Venda interna com 300, 400 e 103 continua recusando. A comercial exportadora (5501) com CSOSN 400 calcula 418,50 (Testado). |
| A5 | Fechado | 14 CFOP recusam com `servico_de_comunicacao_ou_transporte`: 5353, 5302, 5301, 5307, 5351, 5357, 5359, 5360, 5932, 6932, 6353, 6307, 7301 e 7358. Também recusa sob produção própria, exportação direta, ST substituído e monofásico (Testado). Conferi a lista contra o CSV, ver abaixo. |
| A6 | Fechado, com lacuna de teste | 5102 com idDest 1 gera o aviso e calcula 404,00. Combinações: 7102/3 não avisa; 7102/1, 5102/3 e 5102/1 avisam; 7101/3 não avisa (Testado). A suíte do desenvolvedor não isola cada lado do "ou", ver R5. |
| A7 | Fechado para venda mais devolução integral | Venda ST de 20.000 mais devolução de 20.000 aparece na tela, na API e na memória como bruto 20.000,00, deduzido 20.000,00 e líquido 0,00. O total é 2.876,00, igual a 40.000 pelo oráculo. Ver R2 para o caso sem venda no segmento. |
| A8 | Fechado | A chave `st_monofasico` existe na memória (20.000,00, com `sujeita_st` em 0,00), na tela e na API (Testado, mutante N8 morto). |
| A9 | Fechado | 3201 e 2503 oferecem só os dois segmentos de exportação. 2411 e 1201 oferecem só os de mercado interno. A validação e o seletor usam a mesma função (Testado, N9 e N3e mortos). |
| A10 | Mantido por decisão | O serviço mantém "0,00 — valor zero" e a mercadoria mostra "desconsiderado". A exceção está registrada no plano. |
| A11 | Fechado | O banner diz que o pré-DAS de comércio e indústria existe nos casos do corte (N14 morto). |
| A12 | Fechado | Reclassificar em massa para `bonificacao` um item com marca de monofásico recusa a operação inteira e nada muda. Vale também para uma devolução com segmento indo para `devolucao_combustivel_consumo`. Reclassificar para natureza de mercadoria passa (Testado). |
| A13 | Fechado | RBT12 de 3.600.000,00 calcula 1.187,50. Com 0,01 a mais, recusa (Testado). O mutante M39 (N11) morreu. |

## Os dois resíduos declarados

**Resíduo (a): botão da recusa de devolução efetivada sem segmento (Baixa).** Confirmado na tela. A mensagem diz "a nota precisa de estorno", mas o botão continua "Abrir as NF-e a escriturar", e a nota efetivada não está nessa lista. É um problema de orientação, sem efeito em valor. Ver R3, onde o problema aparece em mais dois códigos de recusa.

**Resíduo (b): segmento invisível (Baixa).** Confirmado e **mais amplo que o declarado**. Ver R2.

## Achados novos

### R1 — Baixa — A recusa de devolução de combustível olha só o mês; o saldo de um mês anterior é consumido em silêncio

- **Requisito afetado:** HI-132 e a decisão A2.
- **Local:** `apps/fiscal/pre_das.py`, bloco `devolucao_de_combustivel` (linhas 1090 a 1113), que varre só `nfe_do_mes`.
- **Evidência (Testado, `test_rc082_sondas2.py::test_historico_devolucao_de_combustivel_em_mes_anterior`):**
  - Maio: venda 5102 de 5.000 e devolução 1661 de 8.000 (`devolucao_venda`, segmento `revenda`). O pré-DAS de maio recusa com `devolucao_combustivel_cfop`.
  - Junho: só venda 5102 de 10.000, sem nenhuma nota de combustível. O pré-DAS calcula 488,60 sobre 7.000, que é 10.000 menos 3.000 de saldo da devolução de combustível de maio.
- **Impacto:** o DAS de junho sai subestimado, sem aviso, se o contador tratou maio fora do sistema em vez de estornar a nota. Exige duas condições raras: devolução maior que as vendas do segmento no mês e mês anterior não corrigido. Classifiquei como baixa por isso, mas a direção do erro é a perigosa. O arquiteto pode elevar.
- **Correção recomendada:** estender o bloqueio aos meses que alimentam o saldo carregado, ou excluir do saldo a devolução com CFOP de combustível.
- **Verificação:** o cenário acima deve levantar `PreDasRecusado` em junho com bloqueio nomeado.

### R2 — Baixa — Segmento sem venda no mês é invisível, e isso inclui a devolução do próprio mês

- **Requisito afetado:** conciliação entre pré-DAS e lançamentos de origem; resíduo (b).
- **Local:** `apps/fiscal/receita.py:652` (`mercadoria_do_mes` itera só `apuracao.vendas`) e o filtro do A7 em `pre_das.py`.
- **Evidência (Testado, `test_r_b_devolucao_sem_venda_no_segmento_invisivel`):** venda normal de 40.000 e devolução ST de 5.000 (`revenda_st`) sem venda ST. O resultado tem só o segmento `normal`. O total é 2.876,00, a memória não cita a devolução e não há aviso. No meu teste do Anexo I externo com 1504, o saldo de 10.000 também ficou sem rastro.
- **Impacto:** o valor está certo e é conservador, porque o saldo fica retido. Mas o contador não vê em lugar nenhum que uma devolução escriturada não abateu nada. É o mesmo problema do A7, num caso que o A7 não cobriu.
- **Correção recomendada:** listar os segmentos que têm devolução ou saldo, com a linha "saldo a deduzir em meses futuros".
- **Verificação:** o cenário acima deve mostrar o segmento `sujeita_st` com bruto 0,00, deduzido 0,00 e saldo retido de 5.000,00.

### R3 — Baixa — O botão "Abrir as NF-e a escriturar" também serve a duas recusas que só se resolvem por estorno

- **Requisito afetado:** HI-125 e HI-129; extensão do resíduo (a).
- **Local:** `apps/fiscal/views_web.py:2181-2185` (`_CODIGOS_DA_ESCRITURACAO_NFE`), com `pre_das.py` (mensagem do `anexo_da_mercadoria_a_confirmar`).
- **Evidência (Inspecionado, com a tela da recusa de devolução Testada):** `anexo_da_mercadoria_a_confirmar` também nasce de nota efetivada. A mensagem manda "confirmar a natureza ou o CFOP" e não fala de estorno. `deducao_sem_segmento` vem de saldo de mês anterior, mas o botão aponta para o mês corrente.
- **Impacto:** orientação enganosa. O contador chega a uma lista onde a nota não está. Não altera valor.
- **Correção recomendada:** dar a esses dois códigos o mesmo tratamento dos códigos de CFOP efetivado (texto de estorno, sem link), e dizer o mês de origem no `deducao_sem_segmento`.
- **Verificação:** teste de tela que exija o texto "estorne" nas três recusas.

### R4 — Baixa, pendente de validação — O CFOP x.505 e x.506 é devolução de remessa para formação de lote de exportação, e não de venda

- **Requisito afetado:** HI-129.
- **Local:** `apps/fiscal/models.py:2877-2897` (`ANEXO_DA_DEVOLUCAO_DE_EXPORTACAO_DE_ENTRADA`) e a sugestão de segmento.
- **Evidência (Inspecionado no CSV oficial):**
  - 1.503 e 1.504 devolvem remessa "com fim específico de exportação". A remessa original (5.501 e 5.502) é venda à comercial exportadora, então a dedução faz sentido.
  - 1.505 e 1.506 devolvem "mercadorias remetidas para formação de lote de exportação". A origem (5.504 e 5.505) é remessa, não venda. Em tese não há receita a deduzir.
- **Origem do problema:** na rodada 1 eu escrevi que todos os x.503 a x.506 eram "devoluções de venda a comercial exportadora". Para x.505 e x.506 a afirmação foi larga demais. O desenvolvedor seguiu a decisão baseada nela.
- **Impacto:** se o contador aceitar a sugestão de segmento de exportação para 1.505 ou 1.506, a dedução reduz o DAS sem receita de origem. É raro, e a natureza é confirmação do contador.
- **Correção recomendada:** levar ao contador-senior ou ao Fred se x.505 e x.506 devem ser `remessa_retorno`, sem sugestão de segmento. Enquanto isso, retirar a sugestão automática para esses quatro códigos.
- **Verificação:** definida pela decisão do contador.

### R5 — Baixa — O aviso do A6 não tem teste de cada lado do "ou"

- **Requisito afetado:** critério 5 do plano.
- **Local:** `pre_das.py`, condição `not (linha.cfop.startswith("7") and linha.id_dest == "3")`.
- **Evidência (Testado por mutação):** os mutantes N6a (`and` virou `or`), N6b (ignora o idDest) e N6c (ignora o CFOP) sobreviveram a 198 testes do conjunto `test_dl082_*`. Meus testes de combinação (`test_a6_combinacoes`) os matariam.
- **Impacto:** o aviso pode regredir sem a suíte perceber. Não afeta valor.
- **Correção recomendada:** acrescentar os casos abaixo.
- **Verificação:** os três mutantes devem morrer.

Teste proposto, parametrizado (CFOP, idDest, esperado): `("7102","3",False)`, `("7102","1",True)`, `("5102","3",True)`, `("7101","3",False)`. Natureza `exportacao_direta` e janela 50.000 × 12 interna mais 10.000 × 12 externa. Afirmar a presença do aviso "exportação direta" em `res.avisos`.

### R6 — Baixa — Sem aviso de nota pendente no pré-DAS, a devolução deixada de fora do lote passa a ser ignorada em silêncio

- **Requisito afetado:** A1 e conciliação.
- **Local:** `pre_das.py`, sem nenhuma checagem de NF-e do mês ainda não escriturada. O `confirmar_mes` também não checa.
- **Evidência (Testado, `test_a1_lote_nao_efetiva_devolucao`):** depois do lote, a devolução fica "a escriturar", o mês é confirmado e o pré-DAS calcula 1.438,00 sem aviso, ignorando a devolução de 5.000.
- **Impacto:** antes da correção o lote efetivava e o pré-DAS recusava, o que era barulhento. Agora a falha é omissão. A direção é conservadora para a devolução (DAS maior). A falta de aviso para nota pendente é preexistente e atinge qualquer nota. Ela passa a atingir a devolução por caminho recomendado pelo produto. O lote mostra "Devolução: segmento a confirmar", mas isso não chega ao pré-DAS.
- **Correção recomendada (futura):** aviso no pré-DAS "há N NF-e do mês a escriturar".
- **Verificação:** o mesmo cenário deve trazer o aviso em `res.avisos`.

### R7 — Baixa — Dois resíduos de interface

- **Efetivação individual:** a tela de escrituração não avisa que efetivar uma devolução sem segmento trava o mês (Testado: `escriturar()` sem segmento efetiva e o mês recusa). O A1 tratou só o lote.
- **Coluna "Devolução" do lote:** `templates/fiscal/nfe_lote.html:181` mostra uma coluna que agora é sempre 0,00, porque a devolução saiu do lote (Inspecionado, não testado).
- **Impacto:** o primeiro é uma armadilha que permanece. O segundo é cosmético.
- **Correção recomendada:** aviso na efetivação individual da devolução sem segmento, e retirar a coluna morta do lote.

## Observação sem número

A venda com CFOP 5.656 (combustível) sob a natureza `revenda` calcula 719,01 sobre 10.000 (Testado). A guarda de combustível é por natureza, que é confirmação do contador (HI-118), exceto na devolução, onde o A2 usa o CFOP. Não é regressão nem está nos A1 a A13. Só registro a assimetria.

## CFOP novos contra o CSV oficial

`apps/fiscal/dados/cfop_it2023002_v210.csv` (Inspecionado, com extração própria por descrição):

- **Comunicação e transporte:** a lista da descrição "Prestação de serviço de comunicação/transporte" é exatamente a do comentário do código.
  - Comunicação: 5.301 a 5.307, 6.301 a 6.307 e 7.301.
  - Transporte: 5.351 a 5.357, 5.359, 5.360, 5.932, 6.351 a 6.357, 6.359, 6.360, 6.932 e 7.358.
  - Os 5.931 e 6.931 têm a flag de transporte, mas são "Lançamento…", e ficam corretamente fora.
  - Os 5.205, 5.206, 5.254 e 5.255 (e equivalentes) são anulação ou venda de energia, e ficam fora.
- **Devolução de venda de combustível:** 1.660 a 1.662 e 2.660 a 2.662 têm `indDevol` 1 e descrição "Devolução de venda de combustíveis ou lubrificantes". Os 5.66x e 6.66x são "Devolução de compra…" e não entram (Testado, N2a morto).
- **Exportação:** 1.503 a 1.506 e 2.503 a 2.506 têm `indDevol` 1. A produção (503 e 505) e a revenda (504 e 506) batem com as descrições. Ver R4 para o 505 e o 506.

## Regressão

- **Meses só de serviço:** rodei `test_dl075_*` e `test_dl076_apuracao` com o meu plugin de gravação, 294 testes passando.
  - 83 registros: 36 resultados, 26 recusas e 21 respostas HTTP.
  - Comparados com o `dump_novo` da rodada 1: 83 iguais, 0 diferentes.
  - Esse dump já era idêntico ao de `2eb0f11` depois de remover os campos novos. Logo, rc é idêntico à base (inferência por transitividade, não rodei rc contra `2eb0f11` direto).
- **Lote contra individual (DL-085):** `test_dl085_equivalencia.py` mais `test_dl085_correcao_tela.py`: 7 passaram. A equivalência não envolve devolução, então o resto não mudou.
  - O resultado é consistente: a devolução saiu do lote, e nenhum teste de equivalência a usava.
- **Testes alterados:**
  - `test_dl081_escrituracao`: só acrescenta a chave `st_monofasico` em 0,00. Legítimo.
  - `test_module_homes`: texto do banner. Legítimo.
  - `test_dl085_correcao_tela`: o teste que media a coluna "Devolução" do grupo foi trocado por um que confere a saída com o motivo. É consequência do A1 e foi declarado. Efeito colateral: ver R7 (a coluna morta).

## Oráculo

- Meu `Fraction` com `ROUND_HALF_UP` por tributo coincide com o produto nos valores novos. Observação: a coincidência vale para tabelas que eu transcrevi de memória e que os exemplos do Manual já corroboraram na rodada 1.

| Caso | Oráculo | Produto |
| --- | --- | --- |
| A2 (30.000 líquidos) | 2.157,01 | recusa, como pedido |
| A3, 1503 | 3.076,00 + 418,50 = 3.494,50 | 3.494,50 |
| A3, 1504 com 5502 | 3.076,00 + 404,00 = 3.480,00 | 3.480,00 |
| A4, exportação | 404,00 | 404,00 |
| A7, venda de 40.000 | 2.876,00 | 2.876,00 |
| A13, limite | 1.187,50 | 1.187,50 |
| H, venda de 10.000 | 719,01 | 719,01 |

- **Matriz de 58 cenários mais a cadeia de saldo:** rodei de novo `test_aud082_matriz.py`, `test_aud082_sondas.py` e `test_aud082_telas.py` contra a correção. 67 passaram.
- **Meus testes novos:** `test_rc082_casos.py` tem 54 testes, 53 passaram. A falha foi minha: `test_a1_devolucao_com_marca_ou_mista_tambem_sai_do_lote` esperava criar o lote sem nenhuma nota pendente, e o produto recusa com razão ("Não há nota pendente"). Não é defeito do produto. Os outros 3 arquivos têm 8 testes e todos passaram.

## Mutantes

36 mutantes novos sobre a correção, rodados contra `test_dl082_*`, `test_dl081_rodada1_receita` e `test_dl085_correcao_tela` (e `test_module_homes` para o banner).

- **32 mortos:** N1 (lote efetiva devolução), N2a e N2b, N3a a N3i, N4a e N4b, N5a a N5c, N6d, N7, N8, N9, N10a a N10c, N11, N12, N13 e N14 a N18.
- **4 sobreviveram:**
  - N6a, N6b e N6c: lacuna de teste, ver R5.
  - N5d (retirar o filtro de natureza de mercadoria da recusa A5): provável equivalente, porque as outras naturezas de receita (combustível, serviço conjugado) já recusam por outro motivo. Não provei equivalência.
- **Sobreviventes da rodada 1:**
  - M39 foi morto, é o N11.
  - M35 (devolução CFOP 3 como interno) foi morto pelo `test_dl081_rodada1_receita` na rodada 1 e agora também pelo N3c e N3g.
  - M34 continua mutante equivalente. Não o reexecutei.

## Verificações

- `ruff check --no-cache .`: "All checks passed!".
- `ruff format --check --no-cache .`: 619 arquivos já formatados.
- `python manage.py check`: sem problemas.
- `makemigrations --check --dry-run`: "No changes detected".
- `pytest` completo numa única invocação, na árvore intocada, sem o `.git`:
  - **2 falharam, 9.242 passaram, 55 pulados, 2 avisos, 4 subtestes**, em 1.082,47 s (18 min 02 s). O limite do projeto é 20 min, então a folga é de cerca de 2 min.
  - A medida foi tomada com meus mutantes rodando em paralelo em parte do tempo, então pode estar inflada. O desenvolvedor mediu 18 min 19 s.
  - Falha 1: `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É a falha de ambiente conhecida (Python 3.13 contra sintaxe da 3.14).
  - Falha 2: `scripts/test_decidir_caminhos_vigiados.py::test_caminhos_nao_relevantes_so_esconde_prosa_e_imagem_conhecida`. É artefato da minha cópia sem `.git`: `git ls-files` devolveu 128. Rodei esse arquivo na árvore real e passou (31 passaram). A suíte completa na árvore real não foi repetida.
- Os 20 testes mais lentos são de migração e nenhum é novo da DL-082. O mais lento levou 19,9 s.
- `git -C /home/user/wt-rc082 status`: limpo, sem alteração.

## O que não foi testado

- `pwsh ./scripts/validate-docs.ps1`: o `pwsh` não existe aqui. Conferi à mão os dois documentos tocados (plano e `estado.md`): sem espaço no fim da linha e sem link relativo quebrado. Não conferi a regra do título nem a nova linha final do arquivo (`xxd` ausente).
- `migrate` em banco vazio: coberto indiretamente pelo banco de teste do pytest. Não executei `migrate` à parte. A correção não traz migração.
- O A1 foi exercitado só com notas sintéticas e o lote real, sem concorrência.
- Navegador real, leitor de tela e acessibilidade das telas: não testei.
- Volume e desempenho, 6ª faixa, excesso de sublimite, regime de caixa, conciliação com o PGDAS-D real e benefício estadual: fora do corte, como na rodada 1.
- Concorrência real entre marca, segmento e efetivação: não exercitei dois processos.
- Python 3.14: a suíte rodou em 3.13.

## Arquivos relevantes

- `/home/user/wt-rc082/apps/fiscal/pre_das.py`, `receita.py`, `models.py`, `cfop.py`, `escrituracao_nfe.py`, `escrituracao_nfe_lote.py`, `views_web.py` e `/home/user/wt-rc082/apps/core/module_homes.py`
- Meus testes, em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/rc082/copia/apps/fiscal/tests/`: `test_rc082_casos.py`, `test_rc082_sondas2.py`, `test_rc082_telas.py`.
- Mutantes: `rc082/mutar_rc.py` e `rc082/mutantes_rc.txt` (os cinco últimos, N14 a N18, foram rodados à parte e não estão nesse arquivo). Suíte: `rc082/suite_completa.log`.
