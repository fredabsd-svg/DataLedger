# Reconferência da DL-077 (fatias 2 e 3, lançamentos) — 2026-10-08

**Parecer: REPROVADA.** Os doze achados da rodada 1 estão fechados nos casos reproduzidos, mas encontrei uma falha de gravidade alta que a correção não alcançou (R1). É o ponto material que o desenvolvedor levantou, e ele existe nos leitores do formato próprio e do Excel. Detalhes na seção 3.

## 1. Revisão e ambiente

| Item | Valor |
| --- | --- |
| Cópia auditada | `/home/user/wt-audit077f23b`, HEAD destacado `6e164da5da2760d2ac59a74f4570fd70f0d335fe` (confere). Diff `1ac253e..6e164da`: 20 arquivos, +2.226/−120. |
| Ambiente | Linux, Python 3.13.16, Django 6.1.2, PostgreSQL 16 local, 4 núcleos. Evidências em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/r77f23/`: `h/` (sondas), `h1/` (sondas da rodada 1 adaptadas), `mut/` (cópias `c0..c2`, `mutantes.log`). |
| Execução | Suíte completa em uma única invocação, sem `-n`, no banco `audit_dl077f23b`. |
| Fim | `git status` e `git diff --stat` vazios na cópia auditada, no tronco e no worktree do desenvolvedor, que não toquei. Nenhum commit, push ou acesso ao GitHub. Todos os bancos que criei foram apagados. Nenhum processo meu ficou ativo. |
| Servidor | `gunicorn config.wsgi:application` como no `Dockerfile` (sem `--timeout`, 1 worker sync, 30 s). Subi com `DEBUG=False` e `DJANGO_AMBIENTE=desenvolvimento`, atrás de cabeçalhos de proxy simulados, e encerrei ao fim. |

## 2. A1–A12 e lacunas

| # | Veredito | Evidência executada |
| --- | --- | --- |
| A1 | **Parcial** | Os casos da rodada 1 estão fechados. Segundo 0000 de outra empresa, enviado pela tela: o botão "só os válidos" some, e os dois POSTs dão 400 com 0 lançamentos no Diário. CNPJ de 13 dígitos na ECD, CNPJ alfanumérico na referência e aspas sem fechar no próprio: as duas políticas recusam. **A classe de defeito continua aberta nos leitores próprio, Excel e referência (R1 e R2).** |
| A2 | Fechado para o arquivo | NUL em 8 posições do próprio, 9 da ECD e 8 da referência: 400 na API e na tela, com 0 importações gravadas. Mensagens escapam controle como `\u0001`. **Resíduo em R3:** NUL em outros campos (motivo do descarte, números do aceite) ainda dá HTTP 500. |
| A3 | Fechado | 500×200 recusado em 1,1 s e 2.000×20 em 0,4 s, ambos com mensagem de teto de 4.000 partidas. 2.000×2 e 20×200 são aceitos, e 4.001 e 4.002 partidas são recusados. **Gunicorn real: efetivar 2.000×2 levou 16,4 s, 15,2 s e 14,9 s em três execuções, e 15,3 s com 2.000 avisos de duplicidade aceitos.** 1.000×4 levou 9,5 s e 20×200 levou 3,1 s. Cabe nos 30 s com cerca de 1,8× de margem. Na rodada 1 eram 21,1 s. |
| A4 | Fechado | 202 partidas viram erro de conferência, "no máximo 200". `so_validos` grava os demais e lista o excluído. 200 partidas exatas passam. |
| A5 | Fechado | Exportar o período e reimportar na mesma empresa: o próprio marca 7 de 7 com aviso "já existe lançamento igual", e a ECD 6 de 6. Tudo-ou-nada recusa. O Diário fica em 7 e só passa a 14 depois do aceite explícito. Dois lançamentos iguais dentro do mesmo arquivo não geram aviso. Arquivo F2 = F1 + 1: só os dois repetidos avisam. Aceite cai quando entra lançamento igual depois (`reconferir` zera o aceite). |
| A6 | Fechado | Com travessão, quebra de linha e tab, sem `normalizar_texto` a ECD e a referência recusam (400) e a mensagem manda marcar a opção. Com a opção, os 8 lançamentos afetados exportam e saem listados (número, antes, depois). O Diário não muda. `|`, `€` e emoji viram `?`, e o resultado sempre codifica em Latin-1. Opção no próprio dá 400. O SHA do relatório confere com o do conteúdo. O link da tela leva o parâmetro, e o download sem ele dá 400 pelo SHA. Texto `<img onerror>` sai escapado. |
| A7 | Fechado | Trilha `soma_debitos_efetivados: "100.00"` contra `soma_debitos: "300.00"` lido. A tela mostra "Gravado no Diário" e "Lido do arquivo", e usa o singular. |
| A8 | Fechado | Arquivo de 6,5 MB com 190.000 linhas inválidas: envio 65 KB (era 30,7 MB), detalhe 65 KB, lista 0,7 KB, tela de conferência 96 KB. Guarda 500 de 190.001, com a contagem total. Um erro de arquivo inteiro após 5.000 erros comuns fica na frente da lista e bloqueia o só-válidos. |
| A9 | Fechado | 10^16 vira erro de conferência e 9.999.999.999.999.999,99 é aceito e efetivado. Soma ≥ 10^16: 400 na API e na tela. Nenhum 500. |
| A10 | Fechado | Referência sem barras nas pontas é aceita com um aviso por arquivo. Forma canônica não avisa. Linha sem nenhum `|` continua erro. |
| A11 | Fechado | Próprio, Excel, ECD sem 0000, ECD com 0000 sem CNPJ e referência sem 0000 exigem aceite, nas duas políticas, e a exigência persiste após reconferir. ECD com CNPJ correto não exige. Aceite sem exigência dá 400, e CLIENTE leva 403 na API e na tela. |
| A12 | Fechado | Os 6 sobreviventes (M26, M27, M28, M46, M49, M58) agora morrem. A trilha guarda só a extensão do arquivo. RC-167 não foi repetido nesta rodada. |

## 3. Ponto material do desenvolvedor — veredito

**Veredito: é possível, e só-válidos grava lançamento incompleto. Acontece nos leitores próprio e Excel (R1), e em outra forma na referência (R2). Na ECD é impossível.**

Para o objetivo "uma partida perdida deixa o lançamento ainda equilibrado", usei três provas independentes. A primeira é a execução dos casos pedidos. A segunda é o código de cada leitor. A terceira é um fuzz que corrompe linhas de um único lançamento em arquivos com 3 lançamentos (um de 4 partidas e um de 5). Ele diz que há violação quando o leitor entrega o lançamento com menos partidas, equilibrado e sem erro bloqueante.

| Leitor | Resultado |
| --- | --- |
| **ECD** | **Seguro.** I250 malformado (8 campos, `IND_DC` ruim, valor `50,0`, histórico vazio) rejeita o lançamento inteiro. Linha sem barras ou `REG` desconhecido é erro bloqueante, e a verificação de `VL_LCTO` pega qualquer partida perdida. Fuzz: 20.000 casos, **0 violações**. |
| **Referência** | **Seguro para 6100 inválido.** Qualquer 6100 com campo ruim num lote D ou C derruba o lote inteiro (casos executados e fuzz de 30.000 com o identificador `6100` preservado: 0 violações). **Vulnerável a identificador de registro ilegível** (R2). |
| **Próprio** | **Vulnerável.** Linha de partida com número ilegível. Fuzz com 20.000 casos: 18 violações, todas dessa classe (R1). |
| **Excel** | **Vulnerável**, pela mesma causa (`montar_lancamentos` compartilhado). Fuzz com 1.500 casos: 15 violações. |

Tudo-ou-nada fica protegido em próprio e Excel, porque qualquer erro do arquivo o bloqueia. A classificação por nome de campo (`CAMPOS_DE_ERRO_DO_ARQUIVO`) é a fragilidade. Ela não tem como saber que uma linha descartada pertencia a um lançamento aceito.

## 4. Mutantes

Foram 49 mutantes, em cópias fora do repositório, rodando 963 testes (todos os `test_dl077_*` mais `test_dl038_recusa_livro_caixa`). **43 mortos e 6 sobreviventes.**

| Grupo | Resultado |
| --- | --- |
| Os 6 sobreviventes da rodada 1 (M26, M27, M28, M46, M49, M58) | **6 de 6 mortos.** |
| Outros mortos da rodada 1 reaplicados (débito ≠ crédito, conta sintética, competência encerrada, CNPJ divergente, de-para e contas sem filtro de empresa, reefetivar, descarte sem motivo) | 8 de 8 mortos. |
| Novos na lógica corrigida (N02 a N35) | 29 mortos de 35 (os 6 sobreviventes abaixo). |

Os novos cobrem: classificação de erro do arquivo (N02, N03, N05, N06), teto de partidas, incluindo fronteira (N07, N08, N09), duplicidade e sua consulta (N10, N11, N14), aceite de empresa e invalidação (N15, N16, N35), NUL e escape (N18, N19), 10^16 (N20, N21), somas efetivadas (N22, N23), corte de 500 com prioridade (N24, N25), reconferência sem reescrita (N26), normalização e sua lista (N27 a N30, N32), veredito da tela (N33) e referência sem barras (N34).

**Sobreviventes:**

| Mutante | Leitura |
| --- | --- |
| N04 (tudo-ou-nada só bloqueia erro inteiro) | **Lacuna real de teste.** Nenhum teste prova que tudo-ou-nada recusa quando o leitor descartou um lançamento. O produto está correto (verifiquei), mas o mutante passa. |
| N31 (o link do download perde `normalizar_texto`) | **Lacuna real.** O fluxo conferir e baixar pela tela com normalização não tem teste. Verifiquei à mão que funciona. |
| N12 e N13 (consultas de duplicidade sem filtro de empresa) | Equivalentes no resultado, porque a assinatura inclui `conta_id`, que é da empresa. Mas a consulta carregaria linhas de outros clientes na memória, e nenhum teste exige o filtro (isolamento da consulta). |
| N17 (aceite do arquivo sem que ele seja exigido) | Sem consequência material (só marca um flag). Falta o teste do 400. |
| N01 (linha 0 não conta como erro do arquivo inteiro) | Equivalente na prática. Os erros em linha 0 fora do conjunto, como "sem aba", acontecem sem lançamentos. |

## 5. Achados novos

### R1 — **Alta** — Partida com número ilegível some e "só os válidos" efetiva o lançamento incompleto (próprio e Excel)

- **Requisito:** erro nunca grava lançamento parcial (A1 da rodada 1, item d). Diário imutável.
- **Local:**
  - `apps/contabilidade/intercambio/formatos/proprio_lancamentos_leitura.py:109-110,132` e `:149-153` (`montar_lancamentos`: a linha sem número legível vira `None` e "quebra o bloco").
  - `apps/contabilidade/intercambio/formatos/excel_lancamentos.py:173-175`, que usa o mesmo `montar_lancamentos`.
  - Classificação em `apps/contabilidade/intercambio/importacao_lancamentos.py:159-161` e `:291-295`, e `_erros_que_bloqueiam` em `:1046-1057`. O erro de campo `numero` não é "do arquivo inteiro".
- **Reprodução (executada, serviço):**
  - Lançamento 1 com D100/C100 e, depois, `1x;2026-03-10;Compra;1.1.2;D;50.00` e `1x;…;3.1;C;50.00`. O leitor entrega o lançamento 1 com **2 partidas**, os dois erros `numero` ficam como ocorrência do arquivo, e `efetivar(politica="so_validos")` grava no Diário D100/C100. Perdem-se D50/C50.
  - Mesmo resultado com número vazio, `-1`, texto e 19 dígitos, no fim ou no início do lançamento. Excel: célula vazia ou `1x` nas duas últimas linhas.
  - Entre dois lançamentos, uma linha ruim derruba os dois blocos (correto).
  - Mesmo com a linha ruim no fim e o resto equilibrado, tudo-ou-nada recusa.
- **Impacto:** o Diário é imutável, e a correção posterior é por estorno. Os formatos afetados são o modelo Excel e o TXT próprio, exatamente os que o contador edita à mão. A tela mostra a lista de erros, mas o botão "Efetivar só os válidos" fica habilitado e o lançamento aparece limpo.
- **Correção recomendada:** a linha de dados que o leitor não conseguiu atribuir a nenhum lançamento deve bloquear o só-válidos. Exemplos: dar à linha sem número legível um campo próprio incluído em `CAMPOS_DE_ERRO_DO_ARQUIVO`, ou invalidar os blocos vizinhos à linha quebrada. A solução mais robusta é um invariante: todo erro de leitura deve apontar para um lançamento explicitamente descartado por inteiro, e erro sem dono bloqueia as duas políticas.
- **Teste proposto:** `T-R1`, em `h/test_x11_propostos.py`. Os 4 casos de próprio e Excel com `so_validos` e os 2 de referência (um por política) **falham no código auditado**, e os outros 5 passam.

```python
@pytest.mark.parametrize("formato,conteudo", [
    ("proprio", _proprio(*_par(1), "1x;2026-03-10;Compra;1.1.2;D;50.00", "1x;2026-03-10;Compra;3.1;C;50.00")),
    ("proprio", _proprio(*_par(1), ";2026-03-10;Compra;1.1.2;D;50.00", ";2026-03-10;Compra;3.1;C;50.00")),
    ("proprio", _proprio("x;2026-03-10;Compra;1.1.2;D;50.00", "x;2026-03-10;Compra;3.1;C;50.00", *_par(1))),
    ("excel", _xlsx([[…cabeçalho…], [1, D, "C", "1.1.1", "D", 100], [1, D, "C", "2.1", "C", 100],
                     [None, D, "C", "1.1.2", "D", 50], [None, D, "C", "3.1", "C", 50]])),
])
@pytest.mark.parametrize("politica", ["so_validos", "tudo_ou_nada"])
def test_nenhuma_politica_grava_lancamento_incompleto(cenario, formato, conteudo, politica):
    imp = _receber(cenario["empresa"], formato, conteudo)
    if imp.exige_aceite_do_arquivo: _aceitar_arquivo(imp)
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(imp, politica=politica, usuario=None)
    assert not _diario(cenario["empresa"]).exists()
```

Acrescentar um teste de propriedade (corromper N linhas de um lançamento e exigir que o Diário nunca fique com um lançamento menor que o original). Apliquei uma versão disso nos 4 leitores, em `h/fuzz_incompleto*.py`.

### R2 — **Média** — Referência: partida com identificador de registro ilegível some em silêncio, e até tudo-ou-nada efetiva

- **Requisito:** igual a R1. Aqui não há sequer aviso.
- **Local:** `apps/contabilidade/intercambio/formatos/referencia_lancamentos_leitura.py:483-484` (`lote_atual = None; ignorados[reg] += 1`). A importação de lançamentos descarta `registros_ignorados`, que a importação do plano mostra em `plano_importar_previa.html:108`.
- **Reprodução (executada):** lote `C` com 6100 de 60,00 e 40,00 e um terceiro de 25,00 cujo identificador é `6l00`. Resultado: 0 ocorrências, lançamento de **100,00** com 3 partidas, e **tudo-ou-nada efetivou** (`criados=1`) com o Diário em D60/D40/C100. O total do lote é derivado das linhas, por isso ele "fecha". Se o registro ruim está no meio do lote, o 6100 seguinte vira "sem lote" (erro bloqueante). O vazamento é só quando o registro ruim é o último do lote. Fuzz de 20.000 casos: 2.316 violações, todas desse tipo.
- **Impacto:** perda silenciosa em arquivo corrompido por edição manual. Pelo que testei, truncar o arquivo não dispara o defeito, porque a linha cortada deixa de terminar em `|` e vira erro bloqueante. Por isso classifiquei como média e não alta. Se o fornecedor exportar registros desconhecidos dentro do lote como rotina, o risco sobe.
- **Correção recomendada:** registro desconhecido dentro de um lote (entre o 6000 e o próximo 6000 ou 0000) vira aviso por registro, com aceite. Guardar e mostrar `registros_ignorados` também na importação de lançamentos, como no plano.
- **Teste proposto:** o caso `referencia-6100-com-identificador-ilegivel-no-fim-do-lote` de T-R1, que falha nas duas políticas hoje.

### R3 — **Baixa** — Byte nulo em outros campos gera HTTP 500

- **Local:** `importacao_lancamentos.py:1039` (`descartar`, `atual.save()` com `motivo_do_descarte`) e `:981-984` (`aceitar_avisos`, filtro `numero_origem__in=numeros`). Rotas: `views.py:3322` (descartar na API) e as rotas de aceite de avisos da API e da tela. A tela de descarte também sobe `DataError`.
- **Reprodução (executada):** `motivo` com NUL na API e na tela, e `numeros: ["1\u0000"]` no aceite de avisos (API e tela), todos com `DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`. Sem efeito sobre dados.
- **Correção:** recusar NUL com 400 nesses campos, como já é feito no de-para.
- **Teste proposto:** os três POSTs devem dar 400.

### R4 — **Baixa** — Lacunas de teste (mutantes sobreviventes)

- **N04:** tudo-ou-nada recusa quando o leitor descarta um lançamento. Testei à mão e o produto recusa. Teste proposto, que passa hoje (`test_t_r4…` em `h/test_x11_propostos.py`): ECD com o I200 nº 2 com `VL_LCTO` de 999,00. Tudo-ou-nada recusa, e só-válidos grava só o nº 1.
- **N31:** conferir e baixar pela tela com `normalizar_texto=on` (o link deve conter o parâmetro e o download deve devolver 200).
- **N12 e N13:** a duplicidade consulta só a empresa. Usar `CaptureQueriesContext` e exigir `empresa_id` nas duas consultas.
- **N17:** `aceitar_arquivo` sem exigência dá 400.

### Observações (não são achados)

- **Margem de tempo:** a efetivação máxima mede 15–16 s no meu ambiente, com banco local. Em produção, com banco em rede, a margem de 1,8× pode encolher. BL-675 continua o remédio.
- **Duplicidade:** a mensagem cita o lançamento mais recente (ordenação `-data, -criado_em`). Quando entra outro idêntico no Diário o texto muda e o aceite cai. É conservador e coerente, mas vale documentar.
- **Migração 0025:** sem *backfill*. Importações já existentes antes dela ficam com contadores em zero e, se efetivadas, com "gravado no Diário" em 0,00. Só importa se a 0024 chegou a algum ambiente.
- **CNPJ alfanumérico na referência:** empresa com CNPJ alfanumérico não consegue importar referência por nenhuma política. É a decisão do arquiteto (A1), ligada à PE-81, e está registrada aqui para o Fred.
- **Documentação:** não verifiquei, porque nenhum `.md` está no commit auditado.

## 6. Verificações com números

| Verificação | Resultado |
| --- | --- |
| `pytest` completo, invocação única | **1 reprovado, 7.154 aprovados, 53 pulados**, 2 avisos, 4 subtestes, em 636,87 s. O reprovado é `test_versao_minima_python::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (exige Python 3.14; o ambiente tem 3.13). Na rodada 1 eram 7.091 aprovados. |
| `ruff check .` | All checks passed. |
| `ruff format --check .` | 489 arquivos já formatados. |
| `manage.py check` | 0 problemas. |
| `makemigrations --check --dry-run` | No changes detected. |
| Subconjunto dos mutantes | 963 aprovados em 77 s (base). |
| Migração 0025 | Depende só de `0024_dl077_importacao_lancamentos`. Só `ADD COLUMN` e `DROP DEFAULT`, sem `DROP TABLE` nem `ALTER COLUMN`. `migrate` em banco vazio, reversão até a 0024 e reaplicação funcionam, inclusive com uma importação efetivada e outra em conferência já gravadas. |

**Regressões (por execução):**

- **Exportação e conciliação I155 × balancete:** SQL independente e balancete do produto passam. A ECD e o próprio têm campos, nome e janela de 366 dias conferidos. A referência recusa e omite N×M como antes. O dado do cenário no 6000/6100 está inalterado. Uma sonda minha da rodada 1 falhou por asserção desatualizada (esperava 1 lote `C`, e o zeramento é um segundo `C`). Não é regressão do produto.
- **Atomicidade:** falha injetada no meio do lote e efetivação recusada deixam 0 lançamentos e a importação em conferência.
- **Imutabilidade:** gatilhos por SQL direto recusam UPDATE, DELETE, INSERT e mover linha em importação efetivada ou descartada. UPDATE em conferência é permitido. ORM `update`, `delete` e `save` recusam.
- **Idempotência:** mesmo arquivo dá 409, efetivar duas vezes é recusado, chave com prefixo `importacao:` é recusada em qualquer caixa na API e na tela.
- **Isolamento e permissões:** a matriz de papéis, o outro escritório, outra empresa do mesmo escritório, livro-caixa e CSRF passam.
- **Concorrência:** `encerrar_competencia` com efetivação em curso recusa a efetivação (sem estado híbrido).
- **Ida e volta:** os quatro formatos passam (ECD sem e com saldos, próprio, Excel, referência), agora com o aceite de empresa.

## 7. Implementado / Inspecionado / Testado / Não testado

| Classe | Itens |
| --- | --- |
| **Implementado** | O que a correção `6e164da` entrega: classificação de erro do arquivo inteiro, tetos de partidas, aviso de duplicidade, aceite de empresa, normalização de texto, somas efetivadas, guarda de 500 ocorrências e migração 0025. |
| **Inspecionado** | Diff completo `1ac253e..6e164da`. Os quatro leitores por inteiro, o serviço de importação, as views da API e da tela, os templates alterados e a migração. |
| **Testado (executado)** | Tudo da seção 6, os casos e sondas das seções 2 e 3 (API, tela, serviço), três fuzzers de incompletude (20.000+ casos por leitor), 49 mutantes, gunicorn real (envio e efetivação, 7 execuções) e migração com dados. |
| **Não testado** | Navegador real e acessibilidade visual. Planilha gerada pelo Excel de verdade. Validação do arquivo no PGE da Receita e importação no sistema de referência. Banco em rede ou de produção. Gunicorn com mais de um worker. Python 3.14. Documentação (`estado.md`, plano). RC-167 não repetido. Não dá para dizer que não existem outros defeitos além dos exercitados. |

## 8. Parecer

**REPROVADA.**

R1 é falha de gravidade alta em regra de nível 1: lançamento incompleto entra no Diário imutável por uma política oferecida na tela, nos dois formatos que o contador digita à mão. R2 é a mesma classe nos leitores da referência. R3 e R4 não impedem aprovação.

O que passou continua de pé:

- Os doze achados da rodada 1 estão fechados nos casos reproduzidos.
- A correção melhorou o custo da efetivação (21 s para 15–16 s).
- Exportação, conciliação, atomicidade, imutabilidade, isolamento, permissões e ida e volta não regrediram.

Este parecer não substitui a validação profissional das regras contábeis e legais.

**Arquivos relevantes** (todos em `/home/user/wt-audit077f23b/`):
- `apps/contabilidade/intercambio/formatos/proprio_lancamentos_leitura.py` (R1, `montar_lancamentos`)
- `apps/contabilidade/intercambio/formatos/excel_lancamentos.py` (R1)
- `apps/contabilidade/intercambio/formatos/referencia_lancamentos_leitura.py` (R2)
- `apps/contabilidade/intercambio/importacao_lancamentos.py` (classificação em `:159-161`, `:291-295`, `:1046-1057`; R3 em `:981-984` e `:1039`)
- `apps/contabilidade/views.py` (R3, `:3322`)

**Scripts das sondas e dos mutantes** (em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/r77f23/`):
- `h/test_x11_propostos.py` (testes T-R1 e T-R4 prontos)
- `h/fuzz_incompleto.py` e `h/fuzz_incompleto2.py` (fuzz de incompletude)
- `h/live.py` (cliente do gunicorn)
- `mut/mutantes.py` e `mut/mutantes.log` (49 mutantes)
