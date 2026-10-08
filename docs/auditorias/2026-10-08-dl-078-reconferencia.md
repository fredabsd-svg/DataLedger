# Auditoria DL-078 — reconferência

**Parecer: APROVADA COM RESSALVAS.**

Os achados A1 a A7 e A9 da rodada 1 estão fechados, com evidência executada. Não encontrei falha bloqueadora nem de gravidade alta. A suíte completa deu o mesmo resultado que o desenvolvedor relatou. Os mutantes M5b, M7 e M9 agora morrem, e toda a tabela da rodada 1 foi reexecutada.

Ficam 3 achados novos de gravidade baixa (R1 a R3) e 2 lacunas de teste de gravidade média (R4 e R5). O produto está correto nos dois pontos das lacunas, mas dois mutantes sobrevivem à suíte do desenvolvedor. Pela regra de parada do §3.1 do AGENTS.md, nenhum deles bloqueia: cada um vira ressalva, pendência registrada ou decisão do arquiteto. Nenhuma regra fiscal ou contábil foi validada aqui. A janela de 366 dias e o sinal de T3 continuam hipóteses de produto (HI-98 e HI-99) à espera do Fred.

## 1. Versão e ambiente

- **Árvore auditada:** `/home/user/wt-aud078b`, HEAD `5400e69`, destacado. Ao final, `git status --short` e `git diff --stat` ficaram vazios. Não toquei em `/home/user/DataLedger` nem em `/home/user/wt-dl078`, e não houve commit nem push.
- **Ambiente:** Python 3.13.16 (a CI usa 3.14), PostgreSQL 16 e ruff do venv. Mantive o banco `aud_dl078_rc`. Criei e descartei `aud_dl078_m2` e `aud_dl078_x3`, mais os `test_*` deles.
- **Mutantes e casos próprios:** rodaram só em cópias fora do repositório, feitas por `git archive 5400e69`, cada uma com `git init` próprio. Os arquivos estão em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/`. Cada mutante foi restaurado por `git checkout`, e o `git diff --stat` ficou vazio depois de cada um.
- **Cópia da mutação:** `mut2/wt` e `exp3/wt`. A fixture de relógio dos meus testes `aud078` foi acrescentada só nessas cópias.
- **Contaminação própria detectada e corrigida:** meu teste de concorrência (`transaction=True`) limpa o banco de teste reutilizado e apagou a regra de Palmas semeada. Recriei o banco de teste com `--create-db`. Os testes do desenvolvedor não usam `transaction=True`. A regra de Palmas estava presente (contagem 1) no banco da mutação ao final, então a tabela de mutantes não foi afetada.

## 2. Achados da rodada 1

| Achado | Situação | Evidência |
| --- | --- | --- |
| A1: data de pagamento absurda e sem como desfazer | **Fechado** | Seção 3. Janela aplicada em serviço, API e tela. Limpar com motivo e trilha. Os mutantes N1 a N7, N15 a N17 e N19 a N23 morrem. |
| A2: botões sem saída e motivo do `tpEmit` escondido | **Fechado** | Seção 4. `tpEmit` 2 e 3 mostram a recusa na tela e na lista. Sem natureza, os botões ficam habilitados e `POST` vazio não grava nada. N12a e N12b morrem. |
| A3: mutantes M5b, M7 e M9 sobreviviam | **Fechado** | M5b, M7 e M9 caem 1 teste cada (seção 5). Os testes de `test_dl078_correcao_retencoes.py` têm controle positivo. |
| A4: não contaminação vazia para RBT12, pré-DAS e ISS próprio | **Fechado** | `_afirmar_que_executam` exige `"ok"` antes de comparar. Cenário do Simples cobre composição, RBT12, pré-DAS, retido sofrido e outros municípios. O cenário por alíquota cobre a apuração do ISS próprio. M4 cai em 3 testes. |
| A5: `AMBIGUO_PIS_COFINS` com `vPis` e `vCofins` zerados | **Fechado** | Teste próprio: 0,00 e ausente não disparam, 0,01 e 1,00 disparam, em todos os `tpRetPisCofins` de retenção. N13 morre. |
| A6: valores dos avisos fora de pt-BR | **Fechado** | Aviso A1 sai como `10.000,00` e `12.345,67`; A2, como `1.234,50`; A5, como `R$ 10,00`. N14 morre. |
| A7: função privada e texto da ordem duplicado na tela | **Fechado** | `recusa_de_natureza` é pública. A tela mostra `nota.motivo_sugestao`, que vem do serviço. Conferi o texto de T1, T2, T3, T5, T6 e T7 contra o serviço. N24 morre. |
| A8: sinal de T3 difere da consulta | **Mantido, decisão registrada** | Está como HI-99 em `requisitos.md`. Continua pendente da confirmação do Fred, não é defeito. |
| A9: limite do `INSERT` direto no banco | **Fechado** | Comentário na migração `0008`. O comentário não declara que a janela da data de pagamento também não está no banco (R2). |
| A10: observações de uso | **Aberto, previsto** | Registrado como BL-678. Fora desta correção. |

## 3. A1 a fundo

**Janela:** vai de `data_emissao − 366 dias` até hoje. Os dois limites são inclusivos.

| Caso | Resultado |
| --- | --- |
| Emissão 05/10/2026 e relógio 15/12/2026: 03/10/2025 | Recusado |
| Emissão 05/10/2026 e relógio 15/12/2026: 04/10/2025 e 05/10/2025 | Aceitos |
| Emissão 05/10/2026 e relógio 15/12/2026: 15/12/2026 | Aceito |
| Emissão 05/10/2026 e relógio 15/12/2026: 16/12/2026 | Recusado |
| `0001-01-01`, `1900-01-01`, `2062-10-10`, `9999-12-31` | Recusados em serviço, API (400) e tela, sem gravar e sem trilha |
| `datetime`, texto, `None` e inteiro | Recusados |
| Ano bissexto: emissão 01/03/2028 | Início em 01/03/2027 |
| Emissão em `0001` ou perto de `date.min` | Início em `date.min`, sem `OverflowError` |

**Fuso e virada de dia:** `hoje()` é `timezone.localdate()`, em `America/Sao_Paulo`. Congelei `timezone.now`.

| Instante | `hoje()` |
| --- | --- |
| 23:59:59 em São Paulo, dia 08/10 (02:59:59 UTC do dia 09) | 08/10; 09/10 recusado |
| 00:00:00 em São Paulo, dia 09/10 (03:00:00 UTC) | 09/10; 09/10 aceito e 10/10 recusado |
| 23:00 UTC de 31/12 | 31/12/2026 |
| 02:59 UTC de 01/01/2027 | 31/12/2026 |

A tela mostra a janela do dia real ("Aceita de 04/10/2025 até 08/10/2026 (hoje)").

**Limpar:**

- **Efeito:** só as 4 colunas de pagamento mudam (`data_pagamento`, `pagamento_informado_em`, `pagamento_informado_por_id`, `motivo_pagamento`). Nenhuma outra coluna é alterada. A retenção volta a "pendente" e o total do mês fica `None`.
- **Limpar de novo:** é no-op e não grava trilha.
- **Motivo:** vazio ou só espaços é recusado, também sobre nota já limpa.
- **Informar de novo:** depois de limpar, informar a mesma data é fato novo, com trilha. A sequência de ações na trilha é informar, limpar, informar.
- **Nota estornada ou em rascunho:** recusada pelo serviço, pela API (409) e pela tela (200 com mensagem), sem alterar nada.
- **Concorrência:** 4 `limpar` simultâneos dão 1 limpeza e 1 registro de trilha. Limpar, informar, estornar e limpar juntos terminam com a nota estornada e o grupo de pagamento coerente, sem `IntegrityError`.
- **Trilha** (`escrituracao_tomada.data_pagamento_limpa`): guarda `antes`, `depois`, `motivo` e usuário, sem segredo. A tela mostra "Data informada" e "Data limpa" na ordem, com o motivo de cada uma.

**SQL direto:**

- **Fora do grupo de pagamento:** `v_iss_qn`, `v_ret_irrf`, `natureza` e `estado` continuam recusados pelos gatilhos depois de limpar.
- **Limite novo (R2):** o banco aceita `data_pagamento = '0001-01-01'` e também `data_pagamento = NULL` deixando informante e motivo preenchidos. A janela só existe na aplicação.

**Permissões da rota nova** (API `.../data-pagamento/limpar/` e tela correspondente):

| Caso | API | Tela |
| --- | --- | --- |
| CLIENTE | 403 | 403 |
| PARALEGAL | 403 | 403 |
| ANALISTA, FINANCEIRO, ADMINISTRADOR, GESTOR | 200 | 302 |
| Anônimo | 401 ou 403 | 302 para o login |
| Gestor de outro escritório, com empresa de A, de B ou inexistente | 404 | 404 |
| Gestor de A com a empresa errada do mesmo escritório, ou escrituração inexistente | 404 | 404 |
| `GET`, `PUT`, `PATCH`, `DELETE` | 405 | `GET` dá 405 |

- **Entrada:** `motivo` vazio, só espaços, com 501 caracteres, nulo ou lista dá 400. Campos extras (`estado`, `hoje`) dão 400. Na tela, motivo vazio devolve 200 com mensagem e `estado` extra devolve 400. CSRF (cliente com checagem ligada) dá 403.
- **Quirk do DRF, sem efeito:** `motivo` inteiro (`5`) é convertido em texto e aceito.

**Relógio injetável:**

- **Produção:** `tomadas.hoje()` é uma função de módulo que lê só `timezone.localdate()`. Não consulta variável de ambiente, configuração nem cabeçalho. O contrato rejeita `hoje` no corpo (400), na API e na tela.
- **Teste:** a fixture `relogio_do_teste` não é `autouse` e usa `monkeypatch`.
- **Vazamento:** um teste que roda depois de `test_dl078_pagamento` e `test_dl078_correcao_pagamento` confirma `tomadas.hoje() == timezone.localdate()`.
- **Sem a fixture:** os módulos que informam pagamento declaram a fixture. O `test_dl078_imutabilidade` usa `UPDATE` do ORM e não precisa dela.
- **Relógio do sistema deslocado:** rodei `test_dl078_*` com o relógio do sistema fixo em 2030-06-15 e em 2027-03-01, e todos passaram. Em 2024-01-10, isto é, relógio anterior aos dados de teste, `test_tomadas_nao_entram_em_nenhum_calculo_da_prestadora` falha com `EntradaInvalidaReceita`. Isso não é cenário de produção.

## 4. Regressões da correção

- **`formatacao_ptbr.py`:** comparei o `_valor_ptbr` antigo (extraído de `b0ef594`) com `valor_ptbr` novo em 200.013 entradas, incluindo `None`, negativos, meio-centavo, notação científica e até 15 dígitos. Houve 0 diferenças. As telas antigas importam as duas funções por alias, e nenhum outro módulo as usa.
- **Inventários:** `test_dl024_atalhos_e_acessibilidade.py` lista a rota nova com os 3 testes que a cobrem. Os inventários de `apps/core` passaram na suíte completa. A rota é só `POST`, então não precisa de rótulo de tela em `context_processors.py`. Como `POST` com erro renderiza a tela de pagamento, conferi que a resposta é 200 com a mensagem esperada.
- **Tela sem natureza:** para `tpRetISSQN` 3, os dois botões saem habilitados. `POST` com natureza vazia, ausente, inventada, T1 ou T2 (incompatíveis) não grava linha em `EscrituracaoTomada`. As ações `salvar` e `qualquer` dão 400. Só T6, escolhida pelo contador, efetiva. Em `tpEmit` 2 e 3, os botões saem desabilitados com o motivo na tela e na lista, e `POST` não grava nada.
- **Aviso `PAGAMENTO_ANTES_DA_EMISSAO`:** aparece só nas retenções federais, tela e API, no mês do pagamento. No dia da emissão não dispara.

## 5. Mutantes

Rodei contra os 214 testes `test_dl078_*` (base verde: 214 passed em 15 s). Cada linha é um mutante aplicado por substituição exata e restaurado.

| Mutante | Defeito | Testes que caem |
| --- | --- | --- |
| M1a | Somar também estornada | 7 |
| M1b | Não excluir cancelada | 7 |
| M2 | Emissão no lugar do pagamento (IRRF e CSRF) | 14 |
| M2b | Agrupar por pagamento ou emissão | 0 (equivalente, igual à rodada 1) |
| M2c | Presumir pago | 6 |
| M3a | Soma sem valores dá zero | 5 |
| M3b | `vRetIRRF` ausente vira zero | 3 |
| M3c | `vISSQN` ausente vira zero | 6 |
| M14 | `vRetCP` ausente vira zero | 4 |
| M4 | Somar tomada na receita | 3 |
| M5a | Sem filtro de empresa no relatório | 1 |
| **M5b** | Sem filtro de empresa em `notas_tomadas` | **1 (antes 0)** |
| M5c | Sem filtro de empresa no estorno da API | 1 |
| M5d | Sem filtro de empresa na tela | 2 |
| M6 | ISS retido volta a só T1 | 10 |
| **M7** | INSS pela competência | **1 (antes 0)** |
| M8 | ISS retido pela emissão | 4 |
| **M9** | Dispensar `tpRetISSQN` 2 em T5, T6 e T7 | **1 (antes 0)** |
| M10 | Data de pagamento em nota não efetivada | 2 |
| M11 | Estorno sem motivo | 2 |
| M12 | Retirar a recusa de T1 sem retenção | 2 |
| M13 | Aceitar `tpEmit` 2 e 3 | 5 |
| N1 | Janela sem limite superior (hoje) | 9 |
| N2 | Janela sem limite inferior | 7 |
| N3a / N3b | Janela de 365 / 367 dias | 13 / 12 |
| N3c | Limites exclusivos | 3 |
| N3d | Hoje exclusivo | 2 |
| N4a / N4b | Aviso de adiantamento removido / disparando no mesmo dia | 1 / 1 |
| N5 | Limpar sem motivo | 4 |
| N6 | Limpar sem trilha | 3 |
| N7 | Limpar em qualquer estado | 1 |
| **N8** | API de limpar sem exigir papel de escriturar | **0** |
| N9 | API de limpar sem filtro de empresa | 1 |
| **N10** | Tela de limpar sem exigir papel de escriturar | **0** |
| N10b | Tela de limpar sem filtro de escritório | 1 |
| **N11** | `hoje()` em UTC (`now().date()`) | **0** |
| N12a | Natureza vazia testada antes do bloqueio | 3 |
| N12b | Botões desabilitados sem natureza | 2 |
| N13 | Aviso de PIS/Cofins com valor zero | 1 |
| N14 | Aviso A1 sem pt-BR | 1 |
| N15 | Informar sem janela | 16 |
| N16 | Limpar deixando o informante | 1 |
| N17 | Limpar sem no-op | 1 |
| N19 | Tela só com a trilha de informar | 1 |
| N20 | Tela sem o motivo da limpeza | 1 |
| N23 | Trilha de limpar sem `antes` | 1 |
| N24 | `motivo_sugestao` vazio | 8 |
| N25 | Recusa de T2 removida | 1 |

- **Sobrevivem à suíte do desenvolvedor:** M2b (equivalente conhecido), N8, N10 e N11 (R4 e R5).
- **Meus testes derrubam N8, N10 e N11:** N8 cai em `test_api_limpar_papeis[paralegal-403]`, N10 em `test_web_limpar_papeis[paralegal-403]` (2 testes) e N11 em `test_audr2_relogio.py::test_tela_mostra_janela_do_dia_real` (5 testes).
- **C1, equivalente, não é achado:** tentei misturar tomadas na apuração do ISS próprio (`_escrituracoes_da_competencia`) e nenhum teste caiu. A apuração tem uma segunda guarda: só soma a natureza `PRESTADO_ISS_DEVIDO_PRESTADOR`, e as naturezas de tomada são outras. Conferi pelo código e por um teste de sonda.
- **Tabela da rodada 1 reaplicada:** todos os mutantes antigos que morriam continuam morrendo, com as contagens atualizadas.

## 6. Suíte e verificações

- **`pytest -q -p no:cacheprovider -rs`, uma invocação, sem fatias e sem `-n`:** `1 failed, 7527 passed, 53 skipped, 2 warnings, 4 subtests passed in 611.41s (0:10:11)`. Bate com o relato do desenvolvedor.
- **Única falha:** `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É a preexistente, que exige Python 3.14, e o ambiente tem 3.13.16.
- **Pulados:** os 53 são os mesmos da rodada 1. Os avisos são `RemovedInDjango2028Warning` de `savepoint()` em testes antigos da contabilidade.
- **Linha de base:** a rodada 1 teve 7466 aprovados e esta, 7527. A diferença, +61, vem dos testes novos da correção.
- **Linters e checagens:**

| Comando | Saída |
| --- | --- |
| `ruff check --no-cache .` | `All checks passed!` |
| `ruff format --check --no-cache .` | `511 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |

- **Migração:** `migrate` do zero, `migrate fiscal 0007` (tabela `fiscal_escrituracaotomada` some, 0 gatilhos de tomada) e `migrate fiscal` (reaplica, 2 gatilhos). Todos OK.
- **Meus testes da rodada 2:** 127 passaram (120 mais 7 de concorrência e uma nova checagem de `test_aud078_d`), todos fora do repositório e rodados em cópia.

## 7. Critérios 1 a 10 do plano

| # | Situação | Observação |
| --- | --- | --- |
| 1 | Atende | `tomadas_campos.py` e o modelo não mudaram. Revalidado pela suíte. |
| 2 | Atende | A2 fechado. Imutabilidade por SQL direto conferida de novo depois da correção. |
| 3 | Atende | M5b, M7, M9, M6 e M8 mortos. |
| 4 | Atende | Coberto pela suíte, sem alteração no código de vencimento. |
| 5 | Atende | A1 fechado. Pendente, limpar e informar de novo conferidos. |
| 6 | Atende | Avisos A1 a A8, mais `PAGAMENTO_ANTES_DA_EMISSAO`, A5 e A6 corrigidos. |
| 7 | Atende | Os seis cálculos executam de fato nos dois cenários. |
| 8 | Atende | Rota nova: 404 entre escritórios e empresas, 403 para CLIENTE e PARALEGAL. |
| 9 | Atende, com R4 e R5 | M5b, M7 e M9 caem. N8, N10 e N11 sobrevivem à suíte do desenvolvedor, mas o produto está correto. |
| 10 | Atende | A única falha é a preexistente. Migração reversível. |

## 8. Achados novos

### R1: Baixa, nota emitida muito à frente fecha a janela de pagamento

- **Critério:** HI-98.
- **Local:** `apps/fiscal/tomadas.py`, `janela_da_data_de_pagamento` e `_recusa_da_data_de_pagamento`.
- **Evidência:** teste próprio `test_emissao_no_futuro_distante_janela_vazia`, com o relógio em 08/10/2026. Uma nota com `dhEmi` de 01/01/2030 é efetivada. Informar qualquer data é recusado com "de 31/12/2028 … até 08/10/2026 (hoje)", e o início vem depois do fim.
- **Impacto:** a retenção fica "pendente" até a data chegar. Um erro de ano no `dhEmi` trava o pagamento até lá, com mensagem que não explica a causa. Nenhum número fica errado.
- **Sugestão:** no texto, avisar que a emissão informada é futura. Alternativamente, o arquiteto decide se a efetivação deve recusar emissão posterior a hoje mais 366 dias.

### R2: Baixa, janela e consistência do grupo de pagamento não estão no banco

- **Critério:** AGENTS.md (limites declarados); A9.
- **Local:** migração `0008`, gatilho de `efetivada→efetivada`.
- **Evidência:** teste `test_sql_direto_apos_limpar_e_janela_no_banco`. `UPDATE … SET data_pagamento = '0001-01-01'` com informante foi aceito, e `SET data_pagamento = NULL` deixou `pagamento_informado_por_id` e `motivo_pagamento` preenchidos.
- **Impacto:** exige privilégio de escrita no banco, o mesmo limite de A9. O comentário novo da migração declara o limite do `INSERT`, mas não o da janela nem o da limpeza parcial.
- **Sugestão:** acrescentar duas linhas ao comentário da migração e ao plano. Não exige mudança de gatilho.

### R3: Baixa, aviso de adiantamento só aparece na tela das retenções

- **Critério:** HI-98.
- **Evidência:** `test_aud078r2_aviso.py`. Ao informar 01/09/2026 para uma nota emitida em 05/10/2026, a resposta (tela e API 201) não traz o aviso. Ele aparece em "retenções federais" do mês 9 (tela e API), e a competência 10 não mostra nada. O texto estático da tela diz que o aviso existe.
- **Impacto:** quem informa não vê o aviso na hora. Fora do relatório do mês do pagamento, a nota não é lembrada.
- **Sugestão:** mostrar uma mensagem `messages.warning` no `POST` da tela e um campo `avisos` na resposta da API, ou registrar como observação de uso (BL-678).

### R4: Média, permissão da rota nova de limpar não é testada

- **Critério:** AGENTS.md §11 (autorização no servidor) e critério 8.
- **Local:** `apps/fiscal/tests/test_dl078_correcao_pagamento.py`, `apps/fiscal/api.py` (`DataPagamentoLimparTomadaView.permission_classes`) e `views_web.py` (`tomada_data_pagamento_limpar`).
- **Evidência:** N8 e N10 sobrevivem a `test_dl078_*`. O produto está correto, e meus testes derrubam os dois mutantes.
- **Impacto:** uma refatoração poderia deixar o PARALEGAL limpar a data de pagamento sem que a suíte acuse.
- **Sugestão:**

```python
@pytest.mark.parametrize("papel,esperado", [
    (Papel.CLIENTE, 403), (Papel.PARALEGAL, 403), (Papel.ANALISTA, 200)])
def test_api_limpar_exige_papel_de_escriturar(client, nota_com_data, empresa_a2, escritorio_a, papel, esperado):
    client.force_login(usuario(escritorio_a, papel, f"u-{papel}"))
    r = post_json(client, url_limpar_api(empresa_a2, nota_com_data), {"motivo": "engano"})
    assert r.status_code == esperado
    nota_com_data.refresh_from_db()
    assert (nota_com_data.data_pagamento is None) == (esperado == 200)
```

Replicar para a tela, com 403, 403 e 302.

- **Como verificar:** reaplicar N8 e N10 e conferir que o teste novo cai.

### R5: Média, virada de dia e fuso da janela não são testados

- **Critério:** HI-98.
- **Evidência:** N11, `hoje()` com `timezone.now().date()` (UTC), sobrevive. O relógio fica fixo em 15/12/2026, longe da meia-noite. Entre 21:00 e 23:59 em São Paulo, o UTC já é o dia seguinte, e a janela aceitaria a data de amanhã.
- **Impacto:** o produto está correto hoje. Uma regressão faria o sistema aceitar pagamento futuro nas últimas 3 horas do dia, que é o "presumido" que a HI-96 proíbe.
- **Sugestão:**

```python
def test_hoje_e_a_data_de_sao_paulo(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 9, 2, 59, 59, tzinfo=UTC))
    assert servico.hoje() == date(2026, 10, 8)   # 23:59:59 em São Paulo
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 9, 3, 0, 0, tzinfo=UTC))
    assert servico.hoje() == date(2026, 10, 9)   # 00:00:00 em São Paulo
```

Mais um caso que recusa 09/10 às 23:59:59 locais e aceita às 00:00:00 do dia 09. Esse teste não pode usar `relogio_do_teste`.

- **Como verificar:** reaplicar N11 e conferir que o teste novo cai.

## 9. Limitações

- **Python 3.13.16:** a suíte rodou em 3.13.16 e a CI usa 3.14, que é a causa da falha preexistente.
- **`pwsh`:** `scripts/validate-docs.ps1` não foi executado, porque o ambiente não tem `pwsh`. A conformidade deste relatório com a validação de documentação é por inspeção: título `# `, UTF-8, sem espaço no fim de linha, sem links relativos.
- **Navegador real:** não testei carga, backup nem restauração, nem acessibilidade em navegador. A leitura do HTML renderizado e os contratos de rota foram verificados.
- **Regras fiscais:** nenhuma regra fiscal ou contábil foi validada. A janela de 366 dias (HI-98) e o sinal de T3 (HI-99) são hipóteses do arquiteto, à espera do Fred. As ressalvas da rodada 1 sobre XML sintético, XSD e P&R 13.2 permanecem.
- **Escopo da suíte nova:** meus testes da rodada 2 são pontuais, fora do repositório, e não substituem os do desenvolvedor.
- **Documentação do estado:** não conferi `docs/agents/estado.md` item a item. `test_documentacao_do_estado` passou na suíte completa.

## 10. Arquivos relevantes

Código auditado (somente leitura), em `/home/user/wt-aud078b`:

- `apps/fiscal/tomadas.py`
- `apps/fiscal/retencoes.py`
- `apps/fiscal/api.py`
- `apps/fiscal/views_web.py`
- `apps/fiscal/urls_api.py`
- `apps/fiscal/urls_web.py`
- `apps/fiscal/formatacao_ptbr.py`
- `apps/fiscal/migrations/0008_dl078_escrituracao_tomada.py`
- `templates/fiscal/tomada_data_pagamento.html`
- `templates/fiscal/tomadas_lista.html`
- `apps/fiscal/tests/conftest.py`
- `apps/fiscal/tests/test_dl078_correcao_pagamento.py`
- `apps/fiscal/tests/test_dl078_correcao_retencoes.py`
- `apps/fiscal/tests/test_dl078_nao_contaminacao.py`

Casos próprios e scripts (fora do repositório), em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/`:

- `exp3/wt/apps/fiscal/tests/test_aud078r2_a1.py`
- `exp3/wt/apps/fiscal/tests/test_aud078r2_a2.py`
- `exp3/wt/apps/fiscal/tests/test_aud078r2_a7.py`
- `exp3/wt/apps/fiscal/tests/test_aud078r2_aviso.py`
- `exp3/wt/apps/fiscal/tests/test_aud078r2_conc.py`
- `exp3/wt/apps/fiscal/tests/test_audr2_relogio.py`
- `scripts/mutar_r2.py`
- `scripts/rodar_mutantes_r2.sh`
- `mutantes_r2_dev.txt`
- `suite_dl078_rc.txt`
