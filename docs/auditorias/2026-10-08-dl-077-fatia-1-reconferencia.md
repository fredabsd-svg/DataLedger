# Reconferência da DL-077 (fatia 1, plano de contas) — 2026-10-08

## 1. Revisão e ambiente

- Revisão auditada: `02be3edcef0d6320b0c702a9dbd743a2ebf66629`, HEAD destacado em `/home/user/wt-audit077b`. O SHA confere.
- Escopo: `97a986f..02be3ed`, 17 arquivos, +1.877/−147 linhas.
- Ambiente: Linux, Python 3.13.16, Django 6.1, PostgreSQL 16, openpyxl 3.1.5, 4 núcleos. LibreOffice (`soffice`) está disponível e foi usado.
- Dados 100% sintéticos.
- Higiene:
  - Sondas e mutantes rodaram em cópias do `git archive` dentro de `scratchpad/r77/` (`copia`, `mutdir`, `antes`). Também usei `lo/`, `man/` e os scripts `xl_*.py`.
  - Ao fim, `git status` e `git diff --stat` estão vazios em `wt-audit077b` e em `DataLedger`. Não toquei em `wt-dl077` nem em `wt-dl077f3`. O `wt-dl077f3` mostra 13 alterações; não são minhas.
  - Não houve commit, push nem GitHub.
  - Os bancos `test_audit_dl077b_m`, `test_audit_dl077b_s` e `audit_dl077b_mig` foram apagados. O banco `test_audit_dl077b` da suíte completa foi destruído pelo próprio pytest.
- Limitação: o instrumento (`pkill -f` com o nome de um arquivo de sonda) encerrou por engano meu próprio shell uma vez. Não afetou o repositório.

## 2. Fechamento de A1 a A12

| # | Situação | Evidência (executada) |
| --- | --- | --- |
| A1 | **Fechado** | NUL, `\t`, `\x1b`, `\x07`, `\x7f` e `\n` no nome do `proprio`: prévia com `pode_aplicar=false` e erro em `nome`. NUL e `\t` no código: erro em `codigo`. `criar_conta_pelo_plano(nome="X\x00Y")` recusa. Nenhuma conta gravada. |
| A2 | **Fechado** | COD_NAT 04 sob pai ativo (cadastro ou arquivo): erro nomeado "não pode herdar 'ativo'". Por prefixo `ativo` ou `patrimonio_liquido`: erro. Por prefixo `receita` ou `despesa`: passa. Cadastro `ativo` com arquivo 04: erro. Cadastro `receita`: sem mudança. 04 sob pai 04 com prefixo `receita`: filha herda `receita`. |
| A3 | **Fechado** | Cadastro com `1` e `1.1`, arquivo com `1.1.01`: pai `1.1`. Arquivo com `1` e `1.1.01`, cadastro com `1.1`: pai `1.1`. Fronteira respeitada (`1.10` não captura `1.1.01`). Sem separador (`1101`, com `11` no cadastro): pai `11`, com aviso de "imediato inexistente". Pai analítico no cadastro vira erro. Pai inexistente continua erro. |
| A4 | **Parcial (reaberto na mesma classe, ver R3)** | Fechados os dois casos da rodada 1: 79 KB com 16 M de `<c/>` recusa em 0,07 s (mais de 50 células na linha). `sharedStrings` de 138 MB recusa em 0,01 s (parte acima de 16 MB). Na leitura, `reset_dimensions` fecha a coluna além da `dimension` (N04 morto). Continuam abertos: colunas esparsas, elementos desconhecidos na planilha e `styles`/`sharedStrings` dentro do teto de 16 MB (R3). |
| A5 | **Fechado** | Empresa `12ABC34501DE35`. ECD: 0000 igual passa; minúsculas passam (canonizadas); 0000 de outra empresa recusa; com máscara recusa nomeado; 13 dígitos recusa. Exportação `proprio` e `ecd` ok. Referência: leitura e exportação recusam com a mensagem nomeada. PE-81 e BL-673 registrados no tronco. |
| A6 | **Fechado, com ressalva (R4)** | 2.024 contas: aplicação em 10,2 s e 16.199 consultas (rodada 1: 22,6 s e 42.507). 5.000 contas: 27,7 s com o sistema ocioso e 40.007 consultas. 5.001 contas: 413 na API e 400 com mensagem na tela, 0 contas. |
| A7 | **Fechado** | Na API, `formato`, `politica`, `prefixos`, `sha256` e `assinatura` enviados como arquivo dão 400 no campo, na prévia e na aplicação. |
| A8 | **Fechado no arquivo; risco remanescente no cadastro (R1)** | Cadeia de 51 contas aceita; de 52 a 5.000, em ordem direta e inversa, erro nomeado em até 0,19 s. ECD com 1.200 níveis: erro, sem 500. Em cadeias acumuladas por importações sucessivas a exportação falha (R1). |
| A9 | **Fechado** | Dois 0000 (ECD e referência): erro. 0000 sem CNPJ ou com poucos campos: aviso. ECD sem 0000: aviso visível na prévia HTTP. Referência sem 0000: erro, como antes. |
| A10 | **Fechado** | Coberto por 4 testes de tela; o mutante que reverte o descarte silencioso (N42) e o de `prefixo_N` (N43) morreram. |
| A11 | **Fechado como backlog** | BL-673 está no tronco. Comentário no código. O limite continua dependendo do proxy. |
| A12 | **Parcial** | Fechados: aviso de conta nova sem classificação, mapa de prefixos na trilha e frase duplicada "nenhuma conta". Abertos: especificação do formato próprio ainda só no docstring (`grep` em `docs/` não acha o cabeçalho); `proprio.py` intacto, então `=`/`+`/`-`/`@` iniciais saem crus; pergunta do reduzido não registrada como pendência; telas fora do `universo_de_telas`; `estado.md` desatualizado (passo do arquiteto). |

## 3. Achados novos

### R1 — Baixa — A cadeia de superiores se acumula entre importações e quebra a exportação

- **Requisito:** A8, "recursão remanescente". O comentário em `plano.py:110-113` diz que o limite "mantém segura" a exportação em árvore. Isso não é verdade.
- **Local:** `plano.py:877-906` (`_ordenar_em_arvore.visitar`, recursivo) e `formatos/ecd.py:746-778` (`nivel_de`, recursivo). O limite de 50 níveis (`plano.py:329-351`) conta só superiores dentro do arquivo.
- **Reprodução:** 24 importações `proprio` de 50 níveis, cada uma com a raiz apontando para a última conta da anterior. Resultado: 1.200 contas encadeadas, sem nenhum erro. Em seguida `GET .../exportacao/?formato=proprio` (e `ecd`, `referencia`) levanta `RecursionError` (500).
- **Impacto:** a exportação de uma empresa fica inutilizável, de forma persistente. Pré-existente e improvável na prática, mas alcançável por um usuário autenticado.
- **Correção recomendada:** tornar `visitar` e `nivel_de` iterativos e/ou contar a profundidade contra o cadastro na conferência.
- **Verificação:** T-R1.

### R2 — Média — `.xlsx` malformado produz 500, não recusa com linha e campo

- **Requisito:** critério 1 e critério 6 do plano (leitor recusa o que foge do leiaute, com mensagem).
- **Local:** `excel.py:355-475`. Só `_abrir` converte exceção em recusa. A iteração de `iter_rows` em `_ler_planilha` não é protegida.
- **Reprodução:** pela API e pela tela, na prévia e na aplicação (9 de 9 dão 500): `<c t="s"><v>99999</v>` (IndexError), `<c t="n"><v>abc</v>` (ValueError) e `<extLst><ext>x</ext></extLst>` sem `uri` (TypeError).
- **Outros formatos que disparam exceção crua** (`excel.ler`): `t="d"` com texto, `t="b"` com `x`, `<v>inf</v>`/`nan`, `<row r="x">`, `<c r="1A">`, `<c r="ZZZZ2">`, `mergeCells count="x"`, `hyperlink` sem `ref`, `sheetViews zoomScale="abc"`, `sheetFormatPr` e `cols` inválidos, `tabColor` inválida.
- **Impacto:** 500 sem efeito sobre dados, mas arquivo corrompido ou hostil não recebe diagnóstico.
- **Correção recomendada:** envolver a leitura da aba em `try/except Exception` → `IntercambioRecusado` ("planilha com XML inválido").
- **Verificação:** T-R2.

### R3 — Média — A4 não está fechado: o orçamento SAX não limita o custo real

- **Requisito:** critério 6 (segurança do arquivo recebido).
- **Local:** `excel.py:75-83` (limites), `:196-262` (SAX conta só `row` e `c`), `:482-492` (`reset_dimensions`).
- **Medições, com `excel.ler`:**
  - **Colunas esparsas:** `<row r="N"><c r="XFD{N}"/></row>` sem `dimension`. O openpyxl preenche 16.383 células vazias por linha, nos dois passes. 2.000 linhas (11,5 KB): **9,9 s**. 20.000 linhas (97 KB): **100,3 s** (confirmado). Extrapolando linearmente, 199.000 linhas (~1 MB) dariam ~16 min. Cabe nos limites: 1 célula por linha, menos de 500 mil células, menos de 200 mil linhas.
  - **Elementos desconhecidos:** 15 M de `<a/>` no `sheetData` (arquivo de 60 KB): **65,6 s, RSS de 311 para 1.406 MB**. Aninhamento de 1 M de níveis: 4,8 s e 357 MB.
  - **`styles.xml` de 15 MB (24 KB zipado, 3 M de `<xf/>`):** **36 s e RSS de 1,5 GB**. Com 2,3 M de `<font/>`: 31 s.
  - **`sharedStrings.xml` de 16 MB (2,3 M de `<si/>`):** 18,3 s antes da recusa.
  - **Planilha legítima no teto de células:** 82.998 contas (1,8 MB) leem em 18 s e só então são recusadas pelo teto de 5.000.
- **Origem:** o orçamento conta `c` e `row`, mas não conta elementos nem a coluna da referência. O `reset_dimensions` removeu a única guarda da coluna.
- **Pré-existente:** no `97a986f`, as mesmas 2.000 linhas esparsas levam 9,9 s com `dimension` ausente ou forjada (`A1:XFD3000`). Não é regressão de exposição. É a mesma classe do A4, não coberta pela correção.
- **Impacto:** o `Dockerfile` roda `gunicorn` sem `--timeout` nem `--workers`: um worker síncrono, morto aos 30 s. Um arquivo de 11 KB trava o sistema inteiro por cerca de 10 s, e repetível por qualquer usuário com papel de escrita.
- **Correção recomendada:**
  - recusar `c` com coluna acima de ~50 (ler o atributo `r`);
  - contar todos os elementos (teto global de elementos por parte);
  - baixar os tetos de `styles`/`sharedStrings` (por exemplo 2–4 MB) e da planilha (por exemplo 16 MB);
  - baixar o orçamento de células para algo próximo do que o teto de contas permite (~60 mil);
  - ou ler o openpyxl num subprocesso com limite de CPU e memória.
- **Verificação:** T-R3a, T-R3b, T-R3c.

### R4 — Baixa — O teto de 5.000 contas leva ~28 s, na beira do timeout padrão do gunicorn

- **Local:** `plano.py:107-111` (teto) e `Dockerfile:50` (CMD sem `--timeout`).
- **Reprodução:** aplicação de 5.000 contas em 27,7 s com o sistema ocioso (31 s com captura de consultas). O lock da empresa fica retido durante todo o tempo.
- **Impacto:** no teto, a requisição pode ser interrompida em 30 s. A transação é atômica, então desfaz tudo e não grava parcial. Falha de usabilidade, não de integridade.
- **Correção recomendada:** teto menor (por exemplo 2.500), ou executar em segundo plano, ou documentar `--timeout` no deploy.
- **Verificação:** medir a aplicação do teto em CI e comparar com o timeout configurado.

### R5 — Baixa — Documentação não acompanha as decisões da correção

- O plano (`DL-077-...md`) e o HI-87 continuam sem: COD_NAT 04 só aceita receita ou despesa (A2); pai pelo maior prefixo no arquivo ou no cadastro (A3); teto de 5.000 contas (A6); profundidade 50 (A8); limites do Excel (64/16 MB, 500 mil células, 50 colunas); caracteres de controle (A1). `grep` por "5.000 contas" e "50 níveis" fora de `docs/auditorias` não acha nada.
- O `estado.md` ainda diz "Correção única em andamento" (passo do arquiteto, depois deste parecer).
- O docstring de `plano.py:110-113` contém a afirmação falsa citada em R1.

### R6 — Baixa — Lacunas de teste (sobreviventes novos)

- **N07:** a guarda "aba `plano` fora de `xl/worksheets/`" não tem teste. Verifiquei por execução que o código recusa com mensagem nomeada, então só falta o teste.
- **N27:** `>` virou `>=` no teto de contas e nenhum teste usa exatamente 5.000.
- **N30:** a constante 50 virou 49 e os testes usam a própria constante (`_cadeia(MAXIMO_DE_NIVEIS_DE_SUPERIOR)`), então o valor documentado não é fixado.
- **Casos equivalentes:** N06 (a checagem tardia de linhas em `_ler_planilha` levanta o mesmo erro), N18 (a `CheckConstraint empresa_cnpj_canonico` já garante maiúsculas) e X05 (só a mensagem).
- **Verificação:** T-lacunas.

## 4. Mutantes

Execução: 386 testes `test_dl077_*` (14 arquivos), `-x`, em `mutdir`, restaurado após cada mutante.

| Grupo | Total | Mortos | Sobreviventes |
| --- | --- | --- | --- |
| Sobreviventes da rodada 1 (S) | 7 | 7 | 0 |
| Mortos da rodada 1, reaplicados (G) | 25 | 25 | 0 |
| Novos na lógica corrigida (N01–N48) | 48 | 43 | 5 (N06, N07, N18, N27, N30) |
| Extras (X01–X06, S4b) | 6 | 5 | 1 (X05) |
| **Total** | **86** | **80** | **6** |

- **Rodada 1:** M19, M25 (criação e unicidade), N10, N11 (no filtro `analiticas` isolado, S4b), N13 e N24 estão **todos mortos**.
- **Mortos que importam, em destaque:**
  - SAX: colunas por linha, orçamento de células, limite por parte, teto de parte de apoio e `reset_dimensions` (N01–N05, N08).
  - Escolha do pai: sempre o imediato, ignorar cadastro, ignorar arquivo, o mais curto, sem aviso (N09–N13, X03).
  - `tipos_aceitos`: não conferido, aceita ativo, não passa do leitor (N14–N16).
  - CNPJ: canonização apaga letras, 0000 alfanumérico recusado, sem `upper` no ECD (N17, N19, N20).
  - 0000 repetido, sem CNPJ e ausente (N21–N23); mensagem nomeada do CNPJ na referência (N24, N25).
  - Teto de contas removido e 413 da API (N26, N28).
  - Profundidade: limite 10⁶ e altura 0 (N29, N31).
  - Barras canônicas e sem barras (N32–N36).
  - Controles no código, no nome, 127 e no serviço (N37–N39, X04).
  - Campos de texto como arquivo, na API e na tela (N40–N43); trilha com prefixos (N44).
  - Aviso de classificação e frase duplicada (N45, N46); consultas por conta (N47, X01) e pai errado do mapa (N48).
- Os 6 sobreviventes estão classificados em R6.

## 5. A8: o mutante que "derruba o processo (sinal 9)"

- **Teste da profundidade:** adequado. Três mutantes da regra de profundidade foram mortos por asserção ou `RecursionError` visível: limite 10⁶ (N29), `_altura_da_cadeia` retornando 0 (N31) e, no teste de 1.200 níveis, a profundidade tratada como ilimitada.
- **Reprodução do kill -9:** tirar as duas guardas do laço de `_altura_da_cadeia` (`atual not in visitados` e `altura <= MAXIMO`) faz o teste de ciclo entrar em **laço infinito** (CPU 99,8 % por 5 min, memória estável a 90 MB). O "sinal 9" é o `timeout` da execução, não OOM.
- **Outros dois mutantes dessas guardas:**
  - Tirar só `altura <= MAXIMO` é equivalente em resultado (62 testes passam; só custa mais tempo).
  - Tirar só `atual not in visitados` também é equivalente em resultado (a outra guarda ainda limita o laço).
- **Avaliação:** detecção por hang é insuficiente como prova automática; um `pytest-timeout` ou um teste de ciclo com limite de tempo daria falha por asserção. Risco no código real: nenhum laço sem guarda em `_altura_da_cadeia`.
- **Recursão remanescente em outro ponto:** sim, `visitar` e `nivel_de` (R1).

## 6. Regressões

- **Ida e volta com 2.024 contas:**
  - **Próprio:** 10 inativas voltam ativas. Comportamento já conhecido, não é achado novo.
  - **ECD:** idem, e exige o mapa de prefixos para `receita` e `despesa` (conforme HI-87 e A2).
  - **Referência:** 0 diferenças (a situação A/I viaja).
  - **Excel:** arquivo gerado pelo openpyxl produz plano idêntico ao do `proprio` (`snapshot` igual). Também testei um `.xlsx` regravado pelo **LibreOffice real** (57 KB, com `sharedStrings`, `styles` e `docProps`): 2.024 contas lidas sem erro em 0,28 s.
  - **Reimportar na mesma empresa:** 2.024 "sem mudança" (re-prévia em 0,11 s).
- **Permissões** (API e tela): ANALISTA, ADMINISTRADOR e FINANCEIRO operam; PARALEGAL só exporta; CLIENTE 403; gestor de outro escritório 404; anônimo 403 na API e 302 na tela; empresa inexistente 404.
- **Isolamento:** conta de outra empresa do mesmo escritório e de outro escritório não aparece na exportação.
- **Livro-caixa:** 400 na API, 403 na tela.
- **CSRF:** 403 nos 4 POST, 0 contas.
- **Atomicidade e verificações da prévia:**
  - Arquivo trocado dá 409 e 0 contas.
  - Aplicação dupla dá 409 sem duplicar.
  - SHA-256 e assinatura são conferidos (G08, G09 e G21 mortos).
  - Atomicidade (G10) e os testes de falha no meio da aplicação passam.
  - A política trocada com o mesmo SHA e a mesma assinatura aplicou (200). Isso é aceitável aqui, porque a política não altera nenhum item de uma empresa vazia; a assinatura cobre os itens.
- **Concorrência:** 3 threads aplicando o mesmo arquivo dão `[200, 409, 409]` e 300 contas.
- **Trilha:** `plano_de_contas.importado` com SHA-256, assinatura, contagens e agora `prefixos`; `conta.criada` por conta.

## 7. Fidelidade e RC-167

- **Escrita da referência:** `|0000|CNPJ|` e `|0200|…|` com 11 campos entre as barras, `\r\n`, ISO-8859-1, reduzido sequencial. Exemplo exportado:

```
|0000|77777777000177|
|0200|3|1.2|A|Banco antigo||I|||||
```

- **Leitura:**
  - com barras: sem aviso de forma;
  - sem barras (uma só barra removida de cada ponta): 3 contas lidas e um único aviso por arquivo;
  - misto: um aviso;
  - só início ou só fim: aceitos com aviso;
  - 12 ou 10 campos: erro com contagem.
- **RC-167:** busca automática de trechos de 6 a 7 palavras do "Importação Padrão" (capítulo e PDF, 3 MB de texto) e dos demais textos de manual de terceiro contra `+` linhas do diff `371f152..02be3ed` e do diff de docs do tronco. Resultado: **0 coincidências**. As 2 ocorrências são citações de títulos oficiais (Manual da ECD, título da seção do capítulo "Importação Padrão").

## 8. Documentação

Ver R5. O plano, o HI-87 e o estado não refletem as decisões da correção. HI-91 e PE-81 correspondem ao código (barras canônicas; CNPJ alfanumérico recusado com mensagem nomeada).

## 9. Verificações com números

| Verificação | Resultado |
| --- | --- |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 461 files already formatted |
| `manage.py check` | no issues (0 silenced) |
| `makemigrations --check --dry-run` | No changes detected |
| `manage.py migrate` em banco vazio | Aplicado sem erro (4,6 s) |
| `pytest` completo, invocação única | **1 failed, 6626 passed, 53 skipped, 2 warnings, 4 subtests passed em 589,03 s (9m50s)** |
| Falha | Só `test_versao_minima_python::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, a esperada |
| Testes `test_dl077_*` | 386 aprovados em 16 s (rodada 1: 320 coletados; +66 testes novos) |
| `git status` / `git diff --stat` ao fim | Vazios em `wt-audit077b` e `DataLedger` |

## 10. Classificação

- **Testado:**
  - Suíte completa.
  - A1–A12 por reexecução.
  - Ida e volta dos 4 formatos com 2.024 contas.
  - Matriz de permissões, isolamento, livro-caixa, CSRF e concorrência.
  - 86 mutantes.
  - Probes do Excel (20 formas de XML malformado, esparsidade, elementos desconhecidos, `styles`, `sharedStrings`, aba fora de `xl/worksheets/`).
  - `.xlsx` gerado pelo LibreOffice real.
  - Busca de literais (RC-167).
- **Inspecionado:** diff completo `97a986f..02be3ed`, plano, requisitos, estado e `Dockerfile`.
- **Implementado, confirmado:** teto de contas, profundidade, controles, escolha do pai, `tipos_aceitos`, CNPJ alfanumérico, barras canônicas e campos de texto.
- **Não testado:**
  - Navegador real e acessibilidade visual.
  - Arquivo gerado por Excel real (só LibreOffice).
  - Proxy e limites de corpo (BL-673).
  - Importação do arquivo exportado no sistema de referência e validação do I050 no programa da Receita.
  - Backup e restauração.
  - Execução do gunicorn real: o efeito de R3 e R4 sobre o servidor foi inferido do `Dockerfile` e do tempo medido.

## 11. Casos de teste propostos (para o responsável)

- **T-R1:**
  - Cadastro com cadeia de 1.200 contas, criada por ORM.
  - `GET exportacao` em `proprio`, `ecd` e `referencia` não pode dar `RecursionError`: responder 200 ou 400 com mensagem.
  - Importação cujo pai está no cadastro e que passaria de ~100 níveis totais: erro nomeado.
- **T-R2:** parametrizar os 14 XML malformados acima (por exemplo `t="s"` com `<v>99999</v>`, `t="n"` com `abc`, `extLst` sem `uri`, `mergeCells count="x"`, `row r="x"`, `c r="ZZZZ2"`). Esperado: `IntercambioRecusado` na leitura e 400 pela API e pela tela, sem 500.
- **T-R3a:** `.xlsx` com 3.000 linhas `<row r="N"><c r="XFD{N}"/></row>` e sem `dimension` → `IntercambioRecusado` em menos de 2 s.
- **T-R3b:** `sheet1.xml` com `<a/>` repetido 3.000.000 vezes dentro do `sheetData` → recusa em menos de 3 s.
- **T-R3c:** `styles.xml` com 3.000.000 de `<xf/>`, registrado nas relações do pacote, → recusa em menos de 2 s.
- **T-lacunas:**
  - Plano apontado para `xl/sheet1.xml` → recusa nomeada (N07).
  - Arquivo com exatamente 5.000 contas → prévia sem erro de teto (N27).
  - `assert MAXIMO_DE_NIVEIS_DE_SUPERIOR == 50` ou cadeia literal de 51 aceita e 52 recusada (N30).
  - Teste de ciclo com `pytest.mark.timeout` (A8).
- **T-R4:** teste de CI com 5.000 contas ou o teto reduzido, comparando o tempo com o timeout do deploy.

## 12. Parecer

**REPROVADA.**

Motivo único: o leitor Excel (R2 e R3). O critério 6 do plano, e o A4 que foi condição desta reconferência, não estão atendidos:
- Planilha malformada produz 500 em vez de recusa com mensagem (R2).
- Uma planilha de 11 KB ainda trava o servidor por ~10 s, uma de 97 KB por ~100 s, e uma de ~1 MB, por extrapolação, por ~16 min (R3). Isso reproduz o dano do A4, e a causa (padrão de uso de colunas esparsas) já existia no `97a986f`.

O que está aprovado nesta rodada:
- Núcleo, ECD, referência e `proprio`: A1, A2, A3, A5, A6 (com R4), A7, A8 (no arquivo), A9, A10.
- Atomicidade, permissões no servidor, isolamento, livro-caixa, CSRF, SHA-256 e assinatura, trilha, ida e volta e fidelidade da escrita.
- Suíte: 6.626 aprovados e só a falha de ambiente conhecida. Os 6 sobreviventes da rodada 1 morreram.

Observação de processo (não é decisão minha): o §3.1 do AGENTS.md proíbe uma terceira rodada. R2 e R3 têm correção pequena e localizada em `excel.py`. A decisão do arquiteto-senior e do Fred é entre (a) corrigir sem nova rodada e (b) entregar a fatia com o Excel desativado ou com R2/R3 registrados no backlog como risco aceito. R1, R4, R5 e R6 vão para o backlog como baixa. Auditoria de software não substitui validação profissional das regras contábeis e legais, e este relatório não declara ausência de bugs além do que as verificações acima cobrem.

## Caminhos relevantes

- `/home/user/wt-audit077b/apps/contabilidade/intercambio/formatos/excel.py` (R2, R3)
- `/home/user/wt-audit077b/apps/contabilidade/intercambio/plano.py` (R1, R4, R6)
- `/home/user/wt-audit077b/apps/contabilidade/intercambio/formatos/ecd.py` (R1)
- `/home/user/wt-audit077b/Dockerfile` (R3, R4)
- Sondas e saídas em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/r77/`: `mut_out.txt`, `mutantes_def.py`, `mutantes_def2.py`, `xl_p*.py`, `pytest_full.txt`, `copia/apps/contabilidade/tests/test_sonda_r*.py`.
