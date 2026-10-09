# Auditoria DL-081 — reconferência

**Versão auditada:** cópia descartável `/home/user/wt-aud081b`, HEAD detached `9767151` (frentes A e B e a correção, sobre `b05fd16`, que é a `main` `c01b451` com a DL-080 e mais documentação).
**Data:** 09/10/2026.
**Auditor:** `auditor-qa`.
**Risco:** nível 1 (AGENTS.md §3.1). Esta é a última rodada, pela regra de parada. Achado novo está registrado como ressalva, pendência ou decisão do arquiteto.

## Parecer

**APROVADO COM RESSALVAS.**

Os três achados altos da rodada 1 (A1, A2 e A3) estão fechados, com evidência executada por mim. Nenhuma falha bloqueadora ou de alta gravidade ficou aberta, nem foi achada nesta rodada.

Fatos que sustentam o parecer:
- Cálculo da receita e da conferência com o `vNF`:
  - O gerador de 239 notas e dois sorteios novos de 400 notas deram 0 nota errada aceita e 0 nota correta bloqueada, fora dos dois bloqueios PE-85.
  - Todas as perturbações de ±0,01 foram recusadas.
- Leitura dos itens:
  - Comparei 320 combinações do `imposto` com o `xmllint`.
  - Todas as combinações que o XSD aceita foram lidas.
- Imutabilidade:
  - O gatilho recusa UPDATE, DELETE e INSERT em item e leitura de nota efetivada ou estornada, inclusive por SQL direto.
- Presumido:
  - Está parcial do trimestre da NF-e em diante, nos quatro trimestres.
  - O ano seguinte não é afetado.
- Desempenho:
  - O número de consultas ficou constante com 5, 60 e 400 notas.
  - Uma comparação diferencial contra a árvore anterior deu resultado idêntico, em 3 sorteios.
- Isolamento e permissões:
  - Sem regressão, nas 8 rotas da API e nas 5 telas.
- Regressão completa:
  - 8.576 testes passaram. A única falha é a mesma da rodada 1, em `test_versao_minima_python.py`.

O que impede um "aprovado" simples, todas ressalvas explícitas:
- **R1 (média):** o controle do limite do ano do Presumido ignora a NF-e e não sinaliza nada.
- **R2 (média, condicional):** a releitura dos itens provoca deadlock contra a reclassificação em massa e contra a confirmação de natureza.
- **R3 (baixa a média, latente):** a troca de versão do leitor deixa casos sem saída.
- **A9 (parcial):** o mutante X7 continua vivo, e há outras lacunas menores de teste.
- **Documentação:** a HI-119 está desatualizada em relação ao código.
- **Não testado:** `scripts/validate-docs.ps1`, porque `pwsh` não existe no ambiente.

A auditoria é de software e não substitui a validação do contador sobre as regras. As hipóteses HI-117 a HI-124 seguem como hipóteses. A PE-85 segue como pendência do Fred.

## Achados da rodada 1: situação

| # | Situação | Evidência executada |
| --- | --- | --- |
| A1 (alta) | **Fechado** | 320 combinações do `imposto` (ICMS, IPI nas 5 variantes, II, ISSQN, PIS, COFINS, PISST, COFINSST, vTotTrib, ICMSUFDest, IBSCBS) validadas por `xmllint` e lidas: 104 válidas e lidas, 152 inválidas e recusadas, 64 inválidas e lidas (ver R4), **0 válida recusada**. Valores conferidos: IPI+`cEnq` com `v_ipi` 10,00; `IPINT`; ISSQN só (`v_issqn` 1,00, todos os campos de ICMS `None`); `imposto` vazio; ICMS+ISSQN e IPI/II soltos recusados. Nota conjugada com ICMS e ISSQN e `ISSQNtot`: efetivada com receita 150,00, e a natureza 14 está alcançável. Notas lidas pela versão 1: ilegível vira `lida` v2 na releitura; lida v1 em rascunho é relida, com naturezas recriadas **vazias**; `efetivar` recusa leitura v1 com mensagem; nota efetivada fica na versão antiga. Lacunas na versão: ver R3. |
| A2 (alta) | **Fechado** | 8 datas de NF-e (jan, mar, abr, jun, jul, out, dez/2026 e jan/2027) × 8 trimestres. NF-e em janeiro e em março: T1 a T4/2026 parciais com `receita_nfe_nao_integrada`. Abril e junho: T2 a T4. Julho: T3 e T4. Outubro e dezembro: só T4. Em todos, 2027 `completa`. NF-e em jan/2027: só 2027. Antes/depois sem NF-e: `pre_das`, `rbt12`, composição, situação e os 4 trimestres do Presumido idênticos à `b05fd16`, exceto os ids. Lacuna correlata: R1. |
| A3 (alta) | **Fechado** | Com nota efetivada: UPDATE de `receita_bruta_item`, `ind_tot`, `v_prod`, `cfop`, `n_item` e `documento_id` em item, DELETE de item, INSERT de item (por ORM), UPDATE, DELETE e INSERT em leitura, e UPDATE de `versao_leitor`. Todos recusados com SQLSTATE 23514, e a composição ficou em 150,00. Rascunho: UPDATE no item e na leitura continua permitido, e a releitura funciona. Estorno legítimo funciona; depois dele, item e leitura seguem protegidos. A mutação que remove o gatilho da migração derruba 8 testes (banco recriado). DELETE do documento e alteração do vínculo são barrados por FK e por unicidade. |
| A4 (média) | **Fechado** | Gerador de 239 notas: 155 efetivadas (141 e 14 com `vFCPST`), 84 bloqueadas, todas por item `indTot` 0 com desconto ou despesa, 0 aceita com receita errada. Dois sorteios novos de 400 notas (397 válidas cada), com `vFCPST`, `indDeduzDeson` 0/1 e `indTot` 0: 505 aceitas com a receita igual ao meu oráculo, 148 e 139 bloqueadas pelos dois bloqueios PE-85 (126+22 e 124+17), 0 bloqueada indevidamente, 0 aceita quando devia bloquear. 1.010 perturbações de ±0,01 no `vNF`: todas recusadas, com a mensagem de divergência. O `vFCPST` vem de `ICMSTot` (`v_fcp_st_total`). Os dois textos PE-85 saem na tela (botão desabilitado com o motivo) e na API (409). Nota com `indDeduzDeson` 0 e `vICMSDeson`: efetiva. Registro da regra: R8. |
| A5 (média) | **Fechado** | `vProd` 9.999.999.999.999,99 com `vFrete` 5,00, com `vOutro`, soma de dois itens ≥ 10^13 e dois de 6×10^12: leitura gravada como ilegível com motivo ("receita do item acima do limite" ou "soma ... acima do limite"). API 409, tela 409, repetição 409, GET da nota 200, nenhum 500. Casos de fronteira lidos sem erro: `vUnCom` e `qCom` máximos, `pICMS` 100, `vBC` máximo, desconto maior que o item. O 409 na API é coerente com o comportamento das demais notas ilegíveis: aceito. |
| A6 (média) | **Fechado** | Rotas HTTP medidas com 5, 60 e 400 notas, em consultas: API lista 11, tela lista 10, tela de uma nota 14, API conferência 10, tela conferência 15, tela receita do mês 30, API receita do mês 10. Nenhuma variou com N. Antes eram 411, 410, 415, 509 e 917. RBT12 com 60 meses de devolução: 19 consultas pela função e 26 pela API (antes 2.134). Diferencial com 3 sorteios de 30 meses (NFS-e, NF-e, exportação e devolução, 82 meses com saldo ou dedução): composição e RBT12 idênticos entre `8eb0b58` e `9767151`. |
| A7 (média) | **Fechado na tela; API mantida** | Tela da receita do mês nos meses 2 a 8 com NFS-e, informado, venda, exportação e devoluções interna e externa: em todos, NFS-e + NF-e + informado − devolução deduzida = total, por mercado. A API mantém o contrato de `por_mercado` e traz a NF-e em `nfe_por_mercado`, por decisão comentada no código. Aceito. |
| A8 (média) | **Fechado no cálculo; parcial na conferência** | Devolução com CFOP 1.202 (4.000,00) reduz o interno, e a de CFOP 3.201 (900,00) reduz o externo. O saldo transportado também sai separado por mercado. A conferência por natureza ainda rotula a devolução inteira como interna (R5). |
| A9 (média) | **Parcial** | Ver a tabela de mutantes. Os 7 defeitos do critério 10 morrem. Dos sobreviventes da rodada 1, morreram todos menos X7. Lacunas novas menores: N4b, N11c, N14, N21. |
| A10 (baixa) | **Fechado** | Prévia com 2 notas e 2 itens. Uma nota é efetivada e outra criada, com a mesma contagem: a confirmação responde 409 e não grava nada. Sem assinatura ou com assinatura inválida: 409. Confirmação legítima: 302, grava. |
| A11 (baixa) | **Fechado** | 7.949 e 7.551 com `idDest` 3 ficam sem sugestão. 7.101 com `idDest` 3 continua `exportacao_direta`. Monofásico segue sem sugestão: isso é o que a HI-118 diz, e eu estava errado ao tratar como defeito. |
| A12 (baixa) | **Parcial** | Fechados: `valor_bruto_por_cfop`, `conferir_valores` pública, mensagem de divergência em pt-BR e CFOP com ponto na API. Persiste: o aviso de `vNFTot` ainda usa `:f` (R6). `motivo` numérico no estorno ainda é aceito por coerção (200). |

## Achados novos

### R1 — Média. O controle do limite do ano do Presumido ignora a NF-e e não sinaliza

- **Requisito afetado:** HI-122 ("nunca calcular ignorando a receita de mercadoria") e o próprio fundamento da correção A2 (o limite da LC 224 se propaga).
- **Arquivo e localização:**
  - `apps/fiscal/presumido.py:1596` (`controle_limite_ano`).
  - A recusa `receita_nfe_nao_integrada` está só em `apurar_trimestre`, `presumido.py:1477`.
  - Consumidores: `apps/fiscal/api_presumido.py:587` e `apps/fiscal/views_web.py:6291`.
- **Evidência:** empresa do Presumido com NFS-e de 2.000.000,00 por trimestre e NF-e efetivada de 30.000.000,00 em fevereiro. `controle_limite_ano(2026, "irpj")` devolve exatamente o mesmo quadro de antes da NF-e:
  - receita presumida de 2.000.000,00 por trimestre;
  - fechamento com `receita_no_acrescimo` de 8.000.000,00 e `excedente_anual` de 3.000.000,00.
  - `recusas` fica vazia, e a tela e a API (`recusas: []`) não avisam nada.
  - No mesmo cenário, `apurar_trimestre` dá `parcial` nos 4 trimestres.
- **Impacto:** a tela de controle mostra limite, excedente, sobra e fechamento como se estivessem completos. Esses valores ignoram a receita de mercadoria. Por isso não classifiquei como alta: `apurar_trimestre` não usa essa função, então nenhum valor a recolher sai errado. Mesmo assim, o contador pode ler excedente e fechamento subestimados.
- **Correção recomendada:** aplicar a mesma recusa (NF-e em qualquer mês do ano) em `controle_limite_ano`, e exibir o aviso na tela e na API. Alternativa: decisão do arquiteto de declarar a tela como informativa e rotulá-la.
- **Como verificar:** NF-e só em fevereiro: `recusas` com `receita_nfe_nao_integrada` na API e aviso na tela. Sem NF-e, o quadro continua igual.

### R2 — Média, condicional. Deadlock da releitura dos itens contra reclassificação e confirmação de natureza

- **Requisito afetado:** consistência sob concorrência (AGENTS.md). Sem concorrência nova testada pelo dev, como ele declarou.
- **Arquivo e localização:**
  - `apps/fiscal/itens_nfe.py:445` (`_recriar_naturezas_dos_rascunhos`).
  - `apps/fiscal/itens_nfe.py:461` (`_gravar_leitura`: apaga os itens, que apagam em cascata as naturezas, e recria).
  - Conflito com `reclassificar_em_massa` e `definir_natureza`.
- **Evidência:** nota com leitura v1 e rascunho. Uma thread chama `ler_itens` e outra uma operação concorrente, 12 vezes cada par, em teste com transação real:
  - `ler_itens` × `reclassificar_em_massa`: 8 de 12 com `OperationalError: deadlock detected`.
  - `ler_itens` × `definir_natureza`: 2 de 12.
  - `ler_itens` × `efetivar` e × `criar_rascunho`: 0 deadlock.
  - Nos 4 pares, o final é consistente (uma natureza por item).
- **Causa provável:** a releitura trava a nota, apaga as naturezas e, ao recriá-las, a FK pega `FOR KEY SHARE` na escrituração. Isso conflita com o `FOR UPDATE` da reclassificação. A ordem de travas é invertida: empresa → escrituração → natureza → item de um lado, nota → natureza → escrituração do outro.
- **Impacto:** o PostgreSQL aborta uma das duas, e a transação é desfeita sem corromper dado. O `OperationalError` não é traduzido no módulo fiscal. O contabilidade já traduz o deadlock; no fiscal, o pedido provavelmente vira 500, o que não testei por HTTP. A exposição é baixa hoje, porque a releitura só ocorre com leitura de versão antiga.
- **Correção recomendada:** travar na releitura as escriturações em rascunho da nota, na mesma ordem das demais operações (empresa, depois escrituração), antes de apagar os itens. Alternativa: traduzir o deadlock em 409 com pedido de nova tentativa.
- **Como verificar:** repetir o par `ler_itens` × `reclassificar_em_massa` 50 vezes sem `OperationalError`.

### R3 — Baixa a média, latente. Versão do leitor sem saída em dois casos

- **Requisito afetado:** critério 1 e a recomendação A12 da rodada 1 (prever releitura).
- **Arquivo e localização:**
  - `templates/fiscal/nfe_escriturar.html:106` (botão "Criar rascunho" só aparece sem escrituração e com leitura `lida`).
  - `apps/fiscal/escrituracao_nfe.py:711` (a mensagem manda "gerar o rascunho de novo").
  - `apps/fiscal/itens_nfe.py:494` e `503`.
- **Evidência:**
  1. Nota ilegível pela v1: a tela mostra o erro e **nenhum botão**. O POST `acao=criar` é aceito pelo servidor e relê (302, nota vira `lida`), e a API também. O caminho existe, mas a tela não o oferece.
  2. Rascunho com leitura v1: `efetivar` recusa e manda "gerar o rascunho de novo", mas não há botão com rascunho existente.
  3. Nota efetivada na v2 e estornada, depois a versão sobe para 3 (simulei por monkeypatch): o novo rascunho não pode ser efetivado ("Itens lidos por versão anterior") e **não pode ser relido**, porque o gatilho protege item e leitura de nota estornada.
- **Impacto:** nenhuma nota real está nesse estado hoje, já que a DL-081 não foi integrada. O problema vira real na primeira troca de versão: nota estornada para correção nunca mais volta a ser escriturada.
- **Correção recomendada:** decisão do arquiteto sobre a regra de versão. Opções: oferecer a releitura na tela, ou permitir que a releitura de nota estornada crie uma leitura nova para o novo rascunho.
- **Como verificar:** o cenário 3 deve terminar em efetivada, ou em recusa com caminho de saída documentado.

### R4 — Baixa. O leitor é mais permissivo que o XSD em duas combinações

- **Arquivo e localização:** `apps/fiscal/itens_nfe.py:206` e `:260`.
- **Evidência:** das 64 combinações que o XSD recusa e o leitor lê (24 + 32 + 8):
  - IPI sem `cEnq` (qualquer combinação);
  - II junto com ISSQN.
  O motivo de aceitar é que o grupo do IPI é achado pelo nome, e que a regra "IPI/II soltos" só olha ICMS e ISSQN.
- **Impacto:** quase nulo, já que nota autorizada pela SEFAZ não traz essas combinações. Mas o critério 1 ("bate com o XSD") fica um pouco mais frouxo, e a DL-080 não valida o schema inteiro na recepção.
- **Correção recomendada:** recusar, ou registrar a tolerância.
- **Como verificar:** os mesmos 64 casos passam a ilegíveis (ou ficam documentados).

### R5 — Baixa (declarada pelo dev). A conferência por natureza rotula a devolução de exportação como interna

- **Arquivo e localização:** `apps/fiscal/escrituracao_nfe.py:1151` (`_preencher_receita` usa `mercado_da_natureza_nfe`).
- **Evidência:** abril com devolução 1.202 (4.000,00) e 3.201 (900,00). A conferência traz uma linha `devolucao_venda: ('interno', bruto 4.900,00, soma -4.900,00)` na tela e na API. A composição logo abaixo está correta (interno 4.000,00 e externo 900,00).
- **Impacto:** só exibição. Mas a linha "Receita de NF-e do mês" da conferência não reconcilia por mercado com a composição.
- **Correção recomendada:** agrupar por natureza e mercado do item.
- **Como verificar:** a conferência mostra duas linhas de devolução, interna e externa.

### R6 — Baixa. Resíduos de A12 no formato de valores

- **Arquivo e localização:** `apps/fiscal/escrituracao_nfe.py:1039` (aviso de `vNFTot` com `:f`, ponto decimal e sem R$).
- **Evidência:** no mesmo módulo, a mensagem de divergência já saiu em pt-BR. O estorno com `{"motivo": 12}` retorna 200 por coerção (rodada 1, ainda aberto).
- **Correção recomendada:** usar `valor_ptbr` no aviso, e exigir string em `motivo`.
- **Como verificar:** texto do aviso em pt-BR e 400 para `motivo` numérico.

### R7 — Baixa. A validação contra o XSD não roda na integração contínua

- **Arquivo e localização:** `apps/fiscal/tests/test_dl081_itens.py:589` (`DL080_XSD_DIR`). Nenhum arquivo de `.github` ou `scripts` define essa variável.
- **Evidência:** com `DL080_XSD_DIR` apontando para o conjunto da DL-080, 12 testes do corpus rodam e passam. Sem a variável, rodam só 2. Na integração contínua só valem os 2. Executei os 12 aqui.
- **Impacto:** a garantia "fixture válida contra o XSD" depende de execução manual, igual à DL-080.
- **Correção recomendada:** registrar a limitação, ou fornecer os XSD à integração contínua.
- **Como verificar:** o job lista o corpus como executado, não ignorado.

### R8 — Baixa a média (documental). Texto de requisito e plano divergem do código

- **Arquivo e localização:**
  - `docs/projeto/requisitos.md:181` (HI-119) e `:98` (PE-85).
  - `docs/planos/DL-081-escrituracao-das-nfe-de-saida.md:124` e `:128`.
  - O commit `9767151` não altera nenhum `.md`.
- **Evidência:**
  - A HI-119 ainda diz "tem de bater com `vNF − vST − vIPI − vII − vIPIDevol`". O código subtrai também `vFCPST` e bloqueia os dois casos PE-85.
  - A seção "Decisões tomadas na correção" diz "decisão do Fred, PE-85", mas a PE-85 segue como pendência do Fred, sem registro de decisão.
  - A seção "Decisões tomadas na implementação" ainda diz que a devolução "entra sempre no mercado interno" e que a de exportação fica no BL-685, contradizendo a correção A8.
  - `docs/agents/estado.md` não foi atualizado pela correção.
- **Correção recomendada:** atualizar a HI-119 e a PE-85, corrigir o plano e o `estado.md`. A formulação "decisão do Fred" precisa ser confirmada pelo Fred ou reescrita.
- **Como verificar:** leitura cruzada dos três textos com o código.

### R9 — Baixa (procedimento). A migração 0011 foi editada no lugar

- **Arquivo e localização:** `apps/fiscal/migrations/0011_dl081_escrituracao_nfe.py`.
- **Evidência:** a correção acrescentou as colunas `ind_deduz_deson`, `versao_leitor` e `v_fcp_st_total` e o gatilho de itens dentro da mesma `0011`. Ambiente que já aplicou a `0011` anterior fica sem as colunas e sem o gatilho.
- **Impacto:** nenhum na `main`, onde a 0011 nunca entrou. Vale para qualquer banco de desenvolvimento.
- **Correção recomendada:** nesses bancos, `migrate fiscal 0010` e depois `migrate fiscal`. A reversão e reaplicação funcionam (ver item 11).
- **Como verificar:** idem.

## Verificação dos itens pedidos

| Item | Resultado |
| --- | --- |
| 1. A1 a A12 | Tabela acima. |
| 2. Mutantes e `aud_*` | 97 mutantes aplicados (tabela abaixo). Rodei de novo `aud_t1`, `t2`, `t3` (gerador de 239 notas), `t4`, `t5`, `t6`, `t7`, `t8`, `t9`, `t10`, `t11`, `t18` a `t21` e `aud_antes_depois`, que não viu nenhuma regressão. `aud_t5` quebra só porque o campo `receita_por_cfop` foi renomeado. `aud_t7` falhou num `assert` de contagem porque a chamada de estorno com `motivo` numérico tem sucesso (R6), sem relação com a correção. |
| 3. A1 a fundo | XML válidos contra o XSD com IPI+`cEnq`, `IPINT`, ISSQN só, `imposto` vazio e combinações proibidas: lidos ou recusados como esperado. Releitura por versão testada nos três estados da nota (R3). |
| 4. A2 | Quatro trimestres, jan/2027 e antes/depois: fechado. |
| 5. A3 | Gatilho por SQL em UPDATE, DELETE e INSERT: recusa. Rascunho editável e relível, estorno possível. |
| 6. A4 | Dois bloqueios PE-85 com mensagem, origem do `vFCPST` conferida, ±0,01 recusado. |
| 7. Entrada estranha | Nenhum 500 nas 7 rotas da API de escrituração (`aud_t7`: lista, criar, detalhe, naturezas, efetivar, estornar, reclassificar, mais conferência), nas 5 telas (`aud_t8`) e na tela e API da receita do mês (13 consultas hostis cada). |
| 8. A6 por HTTP | Constante com 5, 60 e 400 notas. |
| 9. Não contaminação | `pre_das`, `rbt12`, composição, situação e Presumido idênticos à `b05fd16` onde não há NF-e. A tela da DL-074 soma as colunas em 7 meses. A suíte completa de ISS, tomadas e pré-DAS passou (item 11). |
| 10. Isolamento e permissões | API: anônimo e cliente 403; paralegal lê (200) e não escreve (403); analista e financeiro escrevem (200), exceto estorno e efetivação, que não testei neles; outro escritório 404. Telas: cliente 403; paralegal 200 nas leituras e 403 nas telas de ação; outro escritório 404. Sem regressão. |
| 11. Suíte e verificações | Ver "Números da suíte". |

## Mutantes

Fiz o ajuste dos âncoras de cada mutante da rodada 1 para o código corrigido e acrescentei os mutantes da correção. Cada mutante rodou com os 357 testes `test_dl081_*` e `-x`. Os sobreviventes rodaram de novo com os testes `test_dl074_*` e `test_dl075_*` juntos (26 arquivos). A árvore auditada ficou intacta; todos os mutantes foram aplicados em cópias.

Resultado: 97 mutantes aplicados, 86 mortos e 11 vivos (6 equivalentes ou quase, 5 lacunas de teste).

**Os 7 defeitos do critério 10 morrem:** somar `vST` (M1a, M1b), `vNF` direto (M2), devolução sem transporte de saldo (M3), remessa como receita (M4), aceitar divergência (M5), reclassificar nota efetivada (M6d) e remover o filtro de empresa (M7a, M7b, M7c).

| Mutante | Resultado |
| --- | --- |
| M1a, M1b, M2, M3, M4, M5, M6d | Mortos |
| M7a (NF-e), M7b, M7c | Mortos |
| M7a2 (NFS-e sem filtro de empresa), M7a3 (informado sem filtro) | **Sobreviveram nos testes `test_dl081_*`**; mortos pelo teste `test_composicao_e_confirmacao_isolam_empresas`, da DL-074. Lacuna só no conjunto da DL-081. |
| M7d (reclassificar sem filtro de empresa nas candidatas) | Sobreviveu. Equivalente: o filtro de empresa em `_itens_que_casam` cobre. |
| M7e (primeira devolução sem filtro de empresa) | Sobreviveu. Equivalente: só antecipa o início da caminhada, com zeros. |
| E1, E2a, E2b, E4, E4b, E5, E6, E8, E9, E10, E11, E12, E13, E14, E15, E17, E18, E19, E20, E21, E22 | Mortos (E4b, E6 e E17, que sobreviveram na rodada 1, morreram) |
| X4a, X4b, X5, X6, X8, X10, X11, X12, X13, X14, X15, X16, X17, X18, X22, X23 | Mortos (X4b, X6, X8, X12, X13, X14 e X17, que sobreviveram na rodada 1, morreram) |
| X2 (efetivar sem validar natureza × tipo) | Sobreviveu. Equivalente, como na rodada 1: `definir_natureza` já valida. |
| **X7** (o saldo transportado ignora NFS-e e informado) | **Sobreviveu**, inclusive com DL-074 e DL-075. Lacuna real de teste (ver proposta 4). Na rodada 1 era X7 e X8 juntos. |
| W1 a W7, W9, W10, W10b | Mortos |
| N1 (IPI com grupo único), N2 (ICMS ausente), N3, N3b (ICMS+ISSQN, IPI/II soltos), N4 (versão ignorada) | Mortos |
| N4b (efetivar aceita leitura de versão antiga) | **Sobreviveu**. É a pendência que o dev declarou. |
| N4c (releitura sem a guarda de efetivada) | Sobreviveu. Equivalente: o gatilho barra a exclusão. |
| N6a (gatilho de itens removido da migração) | Morto: com banco recriado, 8 testes falham e há 1 erro. Na execução em lote ele aparece como sobrevivente porque o banco reaproveitado manteve o gatilho. |
| N7, N7b, N8a, N8b, N8c (W16 e os dois PE-85) | Mortos |
| N9, N9b, N9c (limites e `DataError`) | Mortos |
| N11 (devolução 3xxx pelo interno) | Morto |
| N11b (3xxx em qualquer natureza) | Sobreviveu. Quase equivalente: nenhuma outra natureza de receita tem CFOP 3xxx. |
| **N11c** (devolução 2xxx no externo) | **Sobreviveu**. Lacuna: nenhum teste exige que a devolução interestadual (2.202) siga no interno. |
| N12, N13, N13b, N15, N15b, N16, N16b, N17, N18, N19 | Mortos |
| N14 (itens sem sugestão contados em nota efetivada) | **Sobreviveu**. Lacuna de teste cosmética. |
| N20 (informados do período sem o corte de mês) | Sobreviveu. Equivalente: os meses extras nunca são lidos. |
| **N21** (a tela deixa de distinguir PE-85 de divergência) | **Sobreviveu**. Lacuna: nenhum teste confere o texto PE-85 na tela. Eu o conferi à mão. |

## Números da suíte

**Regressão completa**, numa única invocação, sem `-n` (`pytest -q -p no:cacheprovider --create-db`, com `DL080_XSD_DIR` apontando para o conjunto da DL-080): **1 falhou, 8.576 passaram, 53 ignorados, 2 avisos, 4 subtestes passaram, 796,46 s (0:13:16)**.

- A única falha é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, a mesma da rodada 1. Não a reexecutei na `b05fd16` nesta rodada.
- Os 2 avisos são `RemovedInDjango2028Warning` de `savepoint()` em `test_dl016_f6_check_empresa_not_null.py`, preexistentes.
- A DL-081 tem 357 testes em 22 arquivos (eram 278 em 13), todos passando. Rodei também este conjunto isolado em 40 s.

Verificações complementares, todas na árvore auditada:
- `ruff check --no-cache .`: "All checks passed!".
- `ruff format --check --no-cache .`: 568 arquivos já formatados.
- `manage.py check`: sem problemas.
- `makemigrations --check --dry-run`: "No changes detected".
- Migração `fiscal 0011`:
  - Aplicada: 4 tabelas, 3 funções, 4 gatilhos.
  - Revertida a `0010`: 0 tabelas e 0 funções restantes.
  - Reaplicada: 4 tabelas, 3 funções, 4 gatilhos (inclusive `trg_item_nfe_imutavel` e `trg_leitura_itens_nfe_imutavel`).
  - A migração tem 4 `CreateModel` e nenhuma alteração em tabela existente.
- `scripts/validate-docs.ps1`: **não testado**, porque `pwsh` não existe no ambiente.

Efeitos colaterais: `git status` e `git diff --stat` vazios ao final. Existe um `db.sqlite3` de 0 byte na raiz, ignorado pelo `.gitignore` e criado às 09:03; não sei dizer qual comando o criou.

## Limitações

- **Normas:** não refiz a leitura de LC 123, Res. CGSN 140 e Lei 9.430. A fundamentação normativa segue com o contador-senior, para validação do Fred. A fórmula W16 do MOC 7.0 inclui `vServ` do ISSQN. Testei só uma nota conjugada coerente. A regra não se aplica a CFOP 3xxx (exceção 2 do MOC), e a conferência bloqueia (falha fechada) a nota própria de entrada 3.201 se o `vNF` não seguir a fórmula. Não medi a frequência.
- **Dados:** só dados sintéticos. Não testei contra o acervo real de 618 notas.
- **Concorrência:** testei 4 threads em criação e efetivação, o cenário misto de reclassificação com estorno e os pares de releitura de R2. O deadlock de R2 foi medido em teste, não por HTTP.
- **Interface:** conferi estado, mensagens e HTML por requisição. Não abri navegador; a verificação visual e de acessibilidade da tabela de seis colunas da receita do mês ficou fora.
- **Desempenho:** medido em máquina de teste, com 400 notas e 60 meses de devolução. É tendência, não limite.
- **Banco:** os gatilhos só valem em PostgreSQL, e `TRUNCATE` não os aciona. A tabela `DocumentoNFe` (DL-080) não tem gatilho: `xml_original`, `dh_emissao` e `v_nf` aceitam UPDATE por SQL, sem efeito sobre a receita já efetivada, que usa snapshot. Não testei se alterar a `chave` desfaz um cancelamento. Fora do escopo da DL-081.
- **Mutação:** o teste de N6a precisou de banco recriado. Os mutantes de migração não são confiáveis no modo `--reuse-db`.
- **Cópias de trabalho:** três cópias foram criadas fora do repositório. Uma delas foi copiada durante uma mutação em andamento, e eu refiz os testes que a usavam depois de restaurar o arquivo.

## Propostas de teste (para o responsável implementar)

1. **R1.** Empresa do Presumido, NF-e efetivada só em fevereiro. `controle_limite_ano(ano, "irpj")` deve trazer a recusa `receita_nfe_nao_integrada`, e a tela e a API devem exibir o aviso. Sem NF-e, o quadro não muda.
2. **R2.** Transação real, 12 repetições do par `ler_itens` (nota com leitura v1 e rascunho) × `reclassificar_em_massa`. Sem `OperationalError`, e uma natureza por item no fim.
3. **R3.** Nota efetivada na v2, estornada, com `VERSAO_LEITOR_ITENS` em 3 (monkeypatch). Novo rascunho deve ser efetivável, ou a recusa deve trazer caminho de saída. Tela: nota ilegível v1 e rascunho v1 devem ter botão de releitura.
4. **X7.** Devolução NF-e de 1.000,00 em abril, NFS-e de 600,00 em maio, NF-e de 700,00 em junho. Composição interna de junho: saldo de entrada 400,00, deduzido 400,00, total 300,00. Rodei este cenário: o produto dá esses números.
5. **N4b.** `efetivar` com `versao_leitor` diferente da atual deve recusar com a mensagem de versão, e o estado deve continuar rascunho.
6. **N11c.** Devolução 2.202 (interestadual) deduz o interno e não toca o externo.
7. **N21.** GET da nota com item `indTot` 0 com frete e GET com `indDeduzDeson` 1: a tela mostra "PE-85" e não "não confere". Nota com divergência comum: mostra "não confere" e não PE-85.
8. **N14.** Conferência com nota efetivada e itens sem sugestão: `itens_sem_sugestao` conta só rascunho e a escriturar.
9. **M7a2, M7a3.** Duas empresas do mesmo escritório, NFS-e e receita informada só na outra: `composicao_do_mes` da primeira não muda. Faz parte do conjunto `test_dl081_*`, e não só do DL-074.
10. **R4.** Decidir a regra e testá-la: IPI sem `cEnq` e II+ISSQN ficam ilegíveis, ou ficam aceitos e documentados.
11. **R5.** Conferência com devolução 1.202 e 3.201: duas linhas por mercado.
12. **R6.** Aviso de `vNFTot` em pt-BR. Estorno com `motivo` numérico responde 400.
13. **R7.** Passo de integração contínua com `DL080_XSD_DIR`, ou teste que registre que o corpus XSD não rodou.
14. **A5, A4.** Já estão cobertos por testes do dev (mutantes N8a, N8b, N9, N9b e N9c morrem). Mantive os meus geradores de 239 e 800 notas como referência para uma futura suíte de propriedade.

## Arquivos relevantes

Árvore auditada, em `/home/user/wt-aud081b`:
- `apps/fiscal/itens_nfe.py`
- `apps/fiscal/escrituracao_nfe.py`
- `apps/fiscal/receita.py`
- `apps/fiscal/presumido.py`
- `apps/fiscal/models.py`
- `apps/fiscal/migrations/0011_dl081_escrituracao_nfe.py`
- `apps/fiscal/api_escrituracao_nfe.py`
- `apps/fiscal/views_web.py`
- `templates/fiscal/nfe_escriturar.html`
- `templates/fiscal/receita_do_mes.html`
- `docs/projeto/requisitos.md`
- `docs/planos/DL-081-escrituracao-das-nfe-de-saida.md`

Evidências executáveis, fora do repositório, em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud081rc/`:
- `lab/repo/apps/fiscal/tests/aud_r1_*.py`, `lab3/repo/apps/fiscal/tests/aud_r1_*.py` (os testes desta rodada);
- `mutar3.py`, `mut_a.log`, `mut_b.log`, `mut_c.log`, `mut_d.log` (mutação);
- `suite_full.txt` (suíte completa);
- `antes_*.json`, `depois_*.json`, `dif_prev_*.json`, `dif_novo_*.json` (comparações).
