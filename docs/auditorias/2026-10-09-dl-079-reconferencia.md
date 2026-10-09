# Auditoria DL-079 — reconferência

**Parecer: APROVADO COM RESSALVAS.**

Esta é a última rodada. Nenhuma regra fiscal foi validada aqui, e isso continua sendo do Fred.

- **Números e permissões:** o cálculo bate ao centavo com a minha implementação independente (`Fraction`), como na rodada 1. Isolamento entre empresas e permissões no servidor não regrediram.
- **Rodada 1:**
  - Dos 11 achados que o desenvolvedor disse corrigir, fechei 10 com evidência executada.
  - A2 (entrada estranha devolve 500) fica **parcial**: os 12 vetores da API e os 3 da tela que eu apontei viraram 400, mas sobram vetores do mesmo tipo.
  - A9, A11, A13 e A15 estão registrados nos documentos do projeto.
- **Achados novos:** nenhum bloqueador nem de gravidade alta. R1 é média (resíduo de A2); R2 a R6 são baixas e viram ressalva.
- **Mutação:** dos meus 70 mutantes da rodada 1, 69 caem. O único que sobrevive é o M07d, que já era equivalente. Os 15 sobreviventes não equivalentes da rodada 1 agora caem.

## 1. Versão e ambiente

- **Árvore auditada:** `/home/user/wt-aud079b`, HEAD `c8ab98a` (correção sobre `22b52ae`).
- **Estado ao final:** `git status --short` e `git diff --stat` vazios. Não editei o repositório, não fiz commit nem push, e não toquei `/home/user/DataLedger`, `/home/user/wt-dl079` nem `/home/user/wt-dl080`.
- **Ambiente:** Linux, Python 3.13.16 (a CI usa 3.14), PostgreSQL 16, ruff do venv.
- **Banco:** `aud_dl079_rc`, mantido. Os bancos de experimento foram criados e descartados.
- **Mutantes e experimentos:** rodaram só em cópias de `git archive HEAD`, em `.../scratchpad/aud079/rc/` (`wtx`, `wtm1`, `wtm2`, `wtold`). Cada cópia tem `git init` próprio, e no fim as cópias de mutantes estavam com `git status` vazio.
- **Cálculo independente:** `.../scratchpad/aud079/calc/indep.py`, o mesmo da rodada 1. Não importa nada do repositório.
- **Registros em documentos:** A9, A11, A13 e A15 estão em `/home/user/DataLedger/docs/projeto/` (PE-83, BL-680, HI-114 e HI-115), não no commit `c8ab98a`. O plano com a seção "Decisões tomadas na correção (rodada 1)" também está lá.

## 2. Situação dos achados da rodada 1

| # | Achado | Situação | Evidência executada |
| --- | --- | --- | --- |
| A1 | Fechamento do ano nos T1 a T3 com números falsos | **Fechado**, com risco residual em R3 | Com o exemplo de quatro trimestres, `fechamento_irpj` e `fechamento_csll` saem nulos de T1 a T3 (serviço, API e tela, sem o texto "Fechamento do ano") e T4 traz caso III para IRPJ e CSLL. O caso bate com o independente. No controle do limite, com o relógio em 01/03 e 30/09 não há fechamento, e em 01/10, 31/12 e 20/01/2027 há. Os mutantes N01 a N04 caem |
| A2 | Entrada estranha devolve 500 | **Parcial** | Os 12 vetores da API e os 3 da tela viraram 400. Sobram vetores novos (R1 e R2) |
| A3 | Reenvio duplica a receita | **Fechado**, com lacuna de teste em R4 | API: 201 e depois 409, e a base fica em 100.000,00. Tela: 302 e depois 409. 4 threads simultâneas dão 1 criada e 3 recusas. Estornar a primeira e relançar passa. Valor, suporte, atividade, trimestre e empresa diferentes passam. A mesma receita com outra descrição é recusada (por desenho) |
| A4 | Mutação parcial (16 de 70 sobreviviam) | **Fechado** | Seção 4: sobra 1 de 70, o M07d, equivalente. Cada um dos demais cai com pelo menos 1 teste |
| A5 | Uma consulta por nota | **Fechado** | Consultas com 5, 25 e 55 notas: `apurar_trimestre` T1 em 10, T4 em 24, `retencoes_do_trimestre` em 5, API da apuração em 14, tela da apuração em 14, tela das retenções em 9, tela do limite em 26. São constantes, contra +1 por nota na rodada 1. A anotação `Exists` é equivalente à de `documentos_do_escritorio`, e o N23 (volta ao N+1) cai |
| A6 | API sem campos novos | **Fechado** | O `limite` traz `diferenca_recalculo` e `suspensa_por_medida` por linha, e o `fechamento` traz `trimestres`. N24 e N25 caem |
| A7 | Atividade e critério sem gatilho | **Fechado**, com lacuna de teste em R4 | Por SQL direto, recusados: `UPDATE` de `atividade`, `padrao`, `inicio` e `empresa`; `UPDATE` de `fim` junto com `padrao` ou `inicio`; reencerrar; `fim` voltando a nulo; `DELETE` da atividade; `UPDATE` e `DELETE` do critério. Aceito só o `UPDATE` de `fim` de nulo para data. Migração `0009` revertida para `0008` (6 gatilhos e 6 funções somem), reaplicada e revertida de novo: ciclo íntegro |
| A8 | Faltava o plano de 2 quotas | **Fechado** | Seção 6, item 3 |
| A9 | Sexta-feira Santa e Carnaval | **Registrado** | PE-83 |
| A10 | Empresa Simples de Crédito e rótulo hospitalar | **Fechado** | O rótulo é o texto literal da Lei 9.249, art. 15, § 1º, III, "a" (conferido no Planalto, cópia da rodada 1). A ESC (38,4%, art. 15, § 1º, IV) é nomeada na recusa de atividade fora do catálogo e na tela de atividades. N30 e N31 caem. A ESC continua fora do catálogo, por decisão registrada |
| A11 | Medida sem data efetiva | **Registrado** | BL-680 |
| A12 | API confirmava nota fora da base | **Fechado**, com R5 | A nota sem atividade e a com XML inválido são recusadas com 400 na API e na tela. Nota da base é confirmada (serviço, API e tela). Tomada da própria empresa dá "não encontrada". N20 e N22 caem |
| A13 | Hipóteses não registradas | **Registrado** | HI-114 e HI-115 |
| A14 | Validação frouxa | **Fechado** | `atividade_id` 1,5, `ano` 2026.0 e `criterio.ano` 2026.0 dão 400. Datas `0001-01-01` e `9999-12-31` dão 400, e `2101-01-01` também. `2100-12-31` é aceita (limite do intervalo). Id gigante (10**30) dá 400. N05 a N08 caem, mas N33 sobrevive (R4) |
| A15 | `views_web.py` muito grande | **Registrado** | BL-680 |

## 3. Achados novos

Pela regra de parada, todos viram ressalva, pendência ou decisão do arquiteto.

### R1 — Caractere substituto solitário em texto da API devolve 500 (média, resíduo de A2)

- **Requisito afetado.** Entrada estranha devolve 400, nunca 500. É a verificação 10 do pedido e o docstring de `test_dl079_api.py`.
- **Local.** `apps/fiscal/presumido.py`, função `_texto`. Ela só trata o byte NUL. A API usa `_corpo(request)` direto, sem serializador do DRF. Os `CharField` do DRF usados no resto do repositório já recusam esse caractere.
- **Evidência.** JSON com `"\ud800"` (surrogate solitário) devolve 500 (`UnicodeEncodeError` ao gravar):

  | Campo | Status |
  | --- | --- |
  | `receitas.descricao` | 500 |
  | `receitas.suporte` | 500 |
  | `estornar.motivo` | 500 |
  | `integrais.observacao` | 500 |
  | `medidas.numero_processo` | 500 |
  | `medidas.orgao` | 500 |
  | `medidas.suporte` | 500 |
  | `revogar.motivo` | 500 |
  | `retencoes.motivo`, `atividades.atividade`, `criterio.criterio`, `receitas.tipo` | 400 |

  Para comparação, a rota da DL-074 `receitas-informadas/` responde 400, com a mensagem "Caracteres substitutos não são permitidos". A tela não tem o problema, porque o Django substitui os bytes inválidos antes de chegar ao serviço.
- **Impacto.** Erro 500 em rota autenticada. A transação é atômica e nada é gravado pela metade. É falha de contrato e de robustez, não de integridade.
- **Correção recomendada.** Em `_texto`, recusar o texto que não codifica em UTF-8 (`bruto.encode("utf-8")` com `UnicodeEncodeError`), com mensagem nomeada.
- **Como verificar.** Teste T-R1 (seção 8).

### R2 — A soma das integrais acima do campo devolve 500 ao declarar (baixa, resíduo de A2)

- **Local.** `apps/fiscal/presumido.py`, `declarar_receitas_integrais` e `_integrais_ativas`. O teto vale por receita (9.999.999.999.999,99), mas `DeclaracaoReceitasIntegrais.total` é `max_digits=15`.
- **Evidência.** Duas integrais de 9.999.999.999.999,99 (ou uma de 9.999.999.999.999,99 e outra de 0,01) e depois "declarar": `DataError: numeric field overflow`. A API devolve 500, e a tela também (POST em `integrais/` com `modo=declarar`). A apuração com a soma enorme devolve 200.
- **Impacto.** O mesmo de R1. Exige valores acima de 10^13 no trimestre.
- **Correção recomendada.** Recusar com 400 ou 409 a declaração cujo total passa do teto, ou barrar a receita integral que levaria o total acima dele.
- **Como verificar.** Teste T-R2 (seção 8).

### R3 — Fechamento no controle do limite com o 4º trimestre em curso (baixa; decisão do arquiteto)

O desenvolvedor registrou a regra em `_quarto_trimestre_existe`: de 1º de outubro em diante o controle mostra o fechamento, mesmo com o T4 parcial. Avaliação do risco:

- **O que acontece.** O fechamento sai com o que foi lançado até o dia. Cenário com T1 de 2.000.000, T2 de 100.000 e T3 de 300.000, relógio em 15/10/2026:

  | Situação do T4 | Controle do limite | Apuração do T4 (IRPJ) |
  | --- | --- | --- |
  | Vazio | caso I, excedente anual 0,00, S 750.000,00 | dedução 0,00 (sem imposto no T4) |
  | Com 1.000.000 | caso I | dedução 1.500,00 |
  | Com 3.500.000 | **caso III**, excedente anual 900.000,00 | dedução **0,00** |

  Portanto o caso e a dedução podem mudar à medida que as receitas do T4 entram.
- **Mitigação existente.** A apuração do T4 já se comporta assim, e os números estão corretos para o que foi lançado. Antes de 1º de outubro o fechamento não aparece (A1 fechado). Em nenhum momento sai caso com número falso: o que existe é número provisório sem rótulo.
- **Risco.** Baixo. Um contador lê "caso I, dedução X" em outubro e planeja o 4º trimestre antes de o trimestre fechar.
- **Sugestão.** Rotular o bloco como "provisório até o 4º trimestre fechar". A alternativa é mostrar só depois do fim do ano.

### R4 — Lacunas de teste que os mutantes novos expuseram (baixa)

Seis mutantes sobre as correções sobrevivem à suíte do desenvolvedor. Em todos, o produto está correto: eu executei o comportamento contra o código real e ele atende.

| Mutante | O que a suíte não afirma | Verificação no produto |
| --- | --- | --- |
| N13, N14 e N15 | A duplicidade **não** bloqueia receita igual de outra atividade, de outro trimestre, nem de **outra empresa**. O N15 (guarda sem filtro de empresa) faria uma empresa bloquear a receita de outra, e vazaria o id dela na mensagem | "outra atividade", "outro trimestre" e "outra empresa" são criadas no produto |
| N21 | A checagem de "a nota não está na base do trimestre". Não achei caso que a diferencie das checagens anteriores (nota cancelada, tomada "não encontrada"); provável defesa em profundidade | Não aplicável |
| N26 | O gatilho da atividade recusa `UPDATE` de `fim` **junto com** outra coluna. Um teste que só atualize `fim` não derruba o N26 | Recusado por SQL no produto |
| N33 | O teto do identificador: id acima de 2**63-1 | Recusado (400) no produto |

O N18 (plano de 2 quotas sem o mínimo) e o N34 (NaN) são equivalentes pelas portas de entrada. Com imposto de 2.000,00 ou mais, a menor das duas quotas já é pelo menos 1.000,00. O NaN só chegaria por `Decimal` direto, nunca pelo texto da API ou da tela.

### R5 — Tela de confirmação de retenção (baixa, informativa)

- **O que mudou.** O `ano` e o `trimestre` ocultos que não coincidem com a nota deixaram de dar 404 no POST. Nota do T1 enviada com `trimestre=3` é confirmada (a confirmação é da nota) e o redirecionamento segue o trimestre digitado (302 para `...trimestre=3`). O GET com o trimestre errado continua 404.
- **Impacto.** Nenhum efeito numérico nem de isolamento. Só o redirecionamento vai para o trimestre digitado.
- **Segundo efeito.** O POST de nota fora da base mostra a lista de retenções vazia com a mensagem de erro (`retencoes=[]`). Só acontece por URL manipulada, porque a lista não oferece essas notas.

### R6 — Identidade da duplicidade é por trimestre, não por mês (baixa; decisão de produto)

A guarda recusa receita com o mesmo trimestre, tipo, atividade, valor e suporte. Receitas legítimas recorrentes de mesmo valor no mesmo trimestre com o mesmo "Contrato 12" (três mensalidades iguais, por exemplo) recebem 409 na segunda e na terceira. A mensagem orienta: informar outro suporte ou estornar. É o mesmo desenho da DL-074, só que lá a identidade inclui o mês. Fica como observação para o Fred.

## 4. Mutantes

Reapliquei os 70 mutantes da rodada 1 (M01 a M56, com M07a a M07o) em cópia, contra os 8 arquivos `test_dl079_*.py` (278 testes, dos quais 63 novos). Os padrões de seis mutantes (M07o, M15, M20, M43, M45 e M51) foram reescritos para o código novo. Acrescentei 34 mutantes sobre as correções (N01 a N34). Cada mutante rodou com restauração da cópia.

**Resumo.**

- Dos 70, 69 caem. O M07d sobrevive e é equivalente: a lista de ids de escrituração já vem das notas da empresa.
- Os 15 sobreviventes não equivalentes da rodada 1 (M05 como frágil; M07b a M07m; M13; M18; M32; M45; M50) caem agora, cada um com 1 a 5 testes.
- Os 7 mutantes nomeados no plano caem com 26, 7, 15, 15, 2, 4 e 3 testes (M01 a M06 e M07a).
- O M05 passou de 1 teste a 2.
- Muitos mutantes de filtro de empresa caem com um único teste. Eles caem, mas a proteção é estreita.
- Dos 34 novos (N01 a N34), 28 caem. Os 6 que sobrevivem estão no R4, e dois deles (N18 e N34) são equivalentes.

**Mutantes M01 a M56** (rodada 1 contra agora, em número de testes que caem):

| Mutante | Descrição | Rodada 1 | Agora |
| --- | --- | --- | --- |
| M01 | somar 10 pontos em vez de multiplicar | 24 | 26 |
| M02 | acréscimo na CSLL do T1/2026 | 6 | 7 |
| M03 | receita integral conta no limite | 14 | 15 |
| M04 | esquecer a sobra | 15 | 15 |
| M05 | deduzir retenção não confirmada | 1 | 2 |
| M06 | adicional na CSLL | 3 | 4 |
| M07a | sem filtro de empresa nas notas | 2 | 3 |
| M07b | sem filtro de empresa nas receitas informadas (apuração) | 0 (sobrevivia) | 1 |
| M07c | sem filtro de empresa nas integrais ativas | 0 (sobrevivia) | 1 |
| M07d | sem filtro de empresa nas confirmações | 0 (sobrevivia) | 0 (sobrevive, equivalente) |
| M07e | sem filtro de empresa nas medidas (apuração) | 0 (sobrevivia) | 1 |
| M07f | sem filtro de empresa nas atividades padrão | 0 (sobrevivia) | 1 |
| M07g | sem filtro de empresa na declaração | 0 (sobrevivia) | 1 |
| M07h | sem filtro de empresa em listar_receitas | 0 (sobrevivia) | 1 |
| M07i | sem filtro de empresa em listar_atividades | 0 (sobrevivia) | 1 |
| M07j | sem filtro de empresa em listar_medidas | 0 (sobrevivia) | 1 |
| M07k | sem filtro de empresa ao estornar receita | 0 (sobrevivia) | 2 |
| M07l | sem filtro de empresa ao confirmar retenção | 2 | 5 |
| M07m | sem filtro de empresa ao revogar medida | 0 (sobrevivia) | 2 |
| M07n | sem filtro de empresa ao encerrar atividade | 1 | 3 |
| M07o | receita com atividade de outra empresa | 1 | 1 |
| M08 | desconto ausente = valor da nota | 21 | 32 |
| M09 | incluir trimestre com medida na dedução | 5 | 5 |
| M10 | ROUND_HALF_UP trocado por HALF_EVEN | 67 | 95 |
| M11 | inverter caso II e III | 12 | 17 |
| M12 | limite trimestral de 1.500.000 | 30 | 36 |
| M13 | meses do adicional fixos em 3 | 0 (sobrevivia) | 1 |
| M14 | CSLL do comércio igual à do IRPJ (8%) | 4 | 6 |
| M15 | nota cancelada entra | 1 | 2 |
| M16 | receita estornada entra | 1 | 2 |
| M17 | N sempre 4 no fechamento | 4 | 6 |
| M18 | resíduo do rateio perdido | 0 (sobrevivia) | 1 |
| M19 | declaração nunca cai | 2 | 2 |
| M20 | imposto mínimo para 3 quotas de 1.000 | 1 | 2 |
| M21 | quota mínima de 500 | 2 | 6 |
| M22 | 2ª quota com Selic | 2 | 3 |
| M23 | feriados nacionais ignorados | 2 | 2 |
| M24 | 20/11 só a partir de 2030 | 2 | 2 |
| M25 | Sexta-feira Santa = Páscoa − 3 | 4 | 4 |
| M26 | divisor da CSLL estimada 4,5 | 2 | 2 |
| M27 | tp 8 deixa de ser exata | 14 | 15 |
| M28 | ambiguidade de vPis ignorada | 1 | 1 |
| M29 | "a recolher" pode ficar negativo | 1 | 1 |
| M30 | dedução sem teto | 2 | 2 |
| M31 | trimestres anteriores à abertura contam em N | 1 | 2 |
| M32 | a medida ignora o tributo | 0 (sobrevivia) | 1 |
| M33 | medida revogada continua valendo | 1 | 1 |
| M34 | regime não Presumido não recusa | 3 | 3 |
| M35 | critério caixa não recusa | 2 | 2 |
| M36 | hospitalar sem requisitos aceito | 2 | 2 |
| M37 | API de escrita liberada ao PARALEGAL | 10 | 10 |
| M38 | API de leitura liberada ao CLIENTE | 8 | 8 |
| M39 | tela de escrita sem checar papel | 2 | 2 |
| M40 | tela de leitura sem checar papel | 1 | 1 |
| M41 | desconto somado em vez de subtraído | 1 | 1 |
| M42 | retenção ignorada no "a recolher" | 10 | 10 |
| M43 | CSLL retida = IRRF | 1 | 1 |
| M44 | caso I tratado como caso III | 4 | 4 |
| M45 | descartar o 3º mês do trimestre na leitura das notas | 0 (sobrevivia) | 2 |
| M46 | fator 1,10 trocado por 1,11 | 26 | 28 |
| M47 | CSLL de 9% para 10% | 4 | 6 |
| M48 | limite do adicional de 20.000 para 25.000 | 17 | 18 |
| M49 | IRPJ da revenda de combustíveis de 1,6% para 8% | 1 | 1 |
| M50 | caso II sem resíduo | 0 (sobrevivia) | 1 |
| M51 | vencimento da quota única no mês do fim do trimestre | 1 | 3 |
| M52 | `suspensos` não usado no cálculo anual | 3 | 3 |
| M53 | controle do limite sem `suspensos` | 2 | 3 |
| M54 | sobra negativa não zerada (E sem `max`) | 18 | 21 |
| M55 | CSLL com início em 2027 | 6 | 8 |
| M56 | IRPJ com início em 04/2026 | 30 | 35 |

**Mutantes N01 a N34** (novos, sobre as correções):

| Mutante | Descrição | Testes que caem |
| --- | --- | --- |
| N01 | fechamento do IRPJ nos T1 a T3 (A1 revertido) | 3 |
| N02 | fechamento da CSLL nos T1 a T3 (A1 revertido) | 3 |
| N03 | controle sempre mostra o fechamento (A1) | 1 |
| N04 | controle: fechamento só depois do fim do ano | 4 |
| N05 | teto do valor removido (A2) | 4 |
| N06 | NUL aceito em texto (A2) | 10 |
| N07 | `inteiro_de_entrada` aceita qualquer texto (A2) | 4 |
| N08 | faixa de datas removida (A14) | 5 |
| N09 | guarda de duplicidade removida (A3) | 2 |
| N10 | duplicidade conta a receita estornada (A3) | 1 |
| N11 | duplicidade ignora o suporte (A3) | 2 |
| N12 | duplicidade ignora o valor (A3) | 1 |
| N13 | duplicidade ignora a atividade (A3) | 0 (sobrevive) |
| N14 | duplicidade ignora o trimestre (A3) | 0 (sobrevive) |
| N15 | duplicidade sem filtro de empresa (A3) | 0 (sobrevive) |
| N16 | sem plano de 2 quotas (A8) | 6 |
| N17 | plano de 3 quotas sem mínimo (A8) | 6 |
| N18 | plano de 2 quotas sem mínimo (A8) | 0 (sobrevive, equivalente) |
| N19 | resíduo das quotas na primeira (A8) | 3 |
| N20 | confirmação de nota fora da base aceita (A12) | 2 |
| N21 | A12 sem checar a lista de notas da base | 0 (sobrevive) |
| N22 | A12 ignora a recusa de leitura da nota | 2 |
| N23 | N+1 de volta (A5) | 1 |
| N24 | composição do fechamento omitida na API (A6) | 1 |
| N25 | limite da API sem `suspensa_por_medida` (A6) | 1 |
| N26 | gatilho da atividade aceita qualquer `UPDATE` (A7) | 0 (sobrevive) |
| N27 | gatilho da atividade aceita `DELETE` (A7) | 1 |
| N28 | gatilho da atividade bloqueia o encerramento legítimo (A7) | 7 (4 falhas e 3 erros) |
| N29 | gatilho do critério ausente (A7) | 1 |
| N30 | ESC não nomeada na recusa (A10) | 1 |
| N31 | tela de atividades sem a ESC (A10) | 1 |
| N32 | tela ignora o plano de duas quotas (A8) | 1 |
| N33 | teto do identificador removido | 0 (sobrevive) |
| N34 | NaN aceito (verificação de número finito) | 0 (sobrevive, equivalente) |

## 5. Cálculos independentes contra o produto

O produto foi consultado pela API. Comparei por trimestre e tributo: bases, impostos, parcela da LC 224, adicional, dedução, saldo para PER/DCOMP, "a recolher", saldo negativo, memória por atividade e caso. Nenhum número mudou em relação à rodada 1.

Os 12 cenários abaixo foram comparados também na API. A tabela mostra o IRPJ e, onde há caso interessante, a CSLL. "Dedução" é a dedução **aplicada** no T4, limitada ao imposto do T4. A diferença bruta pode ser maior, e o excesso vai para o saldo de PER/DCOMP.

| Cenário | Tributo | Caso | Excedente anual | S | Dedução T4 | A recolher T1, T2, T3, T4 |
| --- | --- | --- | --- | --- | --- | --- |
| P&R item 11 (1.500.000 de comércio no T1) | IRPJ | I | 0,00 | 250.000,00 | 0,00 | 24.500,00; 0,00; 0,00; 0,00 |
| P&R item 11 | CSLL | I | 0,00 | 0,00 | 0,00 | 16.200,00; 0,00; 0,00; 0,00 |
| Exemplo de 4 trimestres (consulta, item 4), sem retenção | IRPJ | III | 500.000,00 | 300.000,00 | 0,00 | 30.000,00; 78.263,15; 42.000,00; 56.800,00 |
| Mesmo cenário | CSLL | III | 850.000,00 | 650.000,00 | 0,00 | 15.120,00; 35.333,05; 20.160,00; 26.256,00 |
| Caso I (T1 2.000.000, T2 100.000, T4 100.000) | IRPJ | I | 0,00 | 750.000,00 | 1.200,00 (de 1.500,00 brutos) | 35.500,00; 1.200,00; 0,00; 0,00 |
| Caso II (2.500.000; 500.000; 1.000.000; 1.500.000) | IRPJ | II | 500.000,00 | 1.250.000,00 | 1.500,00 | 46.500,00; 6.000,00; 14.000,00; 22.500,00 |
| Caso II com 4 atividades e centavos | IRPJ | II | 1.277.901,24 | 1.777.901,24 | 1.774,32 | 87.320,98; 57.437,60; 34.000,00; 22.225,68 |
| Mesmo cenário | CSLL | II | 293.333,35 | 793.333,35 | 686,82 | 38.133,33; 29.157,75; 14.400,00; 15.513,18 |
| Resíduo de 0,01 no caso II (2.336.044,50; 1.842.852,49; 2.495.609,64; 531.218,21) | IRPJ | II | 2.205.724,84 | 2.924.506,63 | 1.437,56 | 42.892,98; 32.042,75; 46.403,42; 4.937,06 |
| Mesmo cenário | CSLL | II | 1.119.680,34 | 1.838.462,13 | 776,28 | 25.229,28; 20.543,09; 28.297,84; 4.960,88 |
| Caso II da CSLL (1.000.000; 3.000.000; 500.000; 500.000) | CSLL | II | 250.000,00 | 1.750.000,00 | 2.520,00 | 10.800,00; 53.385,04; 14.400,00; 2.889,01 |
| Caso III com 3 atividades e centavos | IRPJ | III | 4.555.666,64 | 2.027.888,85 | 0,00 | 81.300,65; 126.547,62; 45.677,78; 126.900,32 |
| Mesmo cenário | CSLL | III | 3.916.777,76 | 1.388.999,97 | 0,00 | 34.400,00; 51.484,28; 23.135,77; 59.366,76 |
| Rateio com resíduo de 0,01 no trimestre (1.264.058,77; 1.222.522,33; 287.516,72) | IRPJ | I | 0,00 | 1.524.097,82 | 0,00 | 148.110,22 no T1 |
| Ano abaixo do limite (4 x 500.000 de comércio e 100.000 de serviços) | IRPJ | I | 0,00 | 0,00 | 0,00 | 12.000,00 em cada trimestre |
| Centavos no limite exato (1.250.000,00 e 1.250.000,01) | IRPJ | I | 0,00 | 0,01 | 0,00 | 19.000,00; 19.000,00; 0,00; 0,00 |

Os demais cenários, todos passando contra o produto:

- **Pipeline completo da consulta (item 4):** NFS-e com desconto incondicional, retenção confirmada (`tpRetPisCofins` 8), receita informada, integrais e declaração.
  - IRPJ a recolher: 25.500,00; 68.763,15; 36.000,00; 49.300,00.
  - CSLL a recolher: 12.120,00; 29.033,05; 16.160,00; 21.256,00.
  - A situação do trimestre sai "completa".
- **Medida judicial:** as 14 variantes da rodada 1 (só T4, só T1, T2 a T3, ano todo, indeterminada, só CSLL, "ambos", com depósito, excesso de dedução, duas medidas). Nenhuma divergiu, e "a recolher" nunca ficou negativo.
- **Abertura no meio do ano:** os 6 casos (15/05, 10/08, 01/07, 30/06, 31/10, 02/03) coincidiram em N e nos meses do adicional.
- **Resíduo:** o exemplo do P&R item 14 (base IRPJ de 237.440,00) e os dois resíduos de 0,01 batem.
- **NFS-e pelo pipeline real:** 146.000,00 no T1 e 30.000,00 no T2. IRPJ de 7.008,00 e CSLL de 4.204,80 no T1.

## 6. Regressões da correção

1. **Ajustes em testes existentes.** Rodei os 4 arquivos `test_dl079_{api,servico,telas,imutabilidade}.py` da versão `22b52ae` contra o código corrigido: **2 falhas e 8 erros**.
   - As 2 falhas e os 8 erros são os que a correção força. O critério caixa trocava o critério por `DELETE`, hoje recusado pelo gatilho do A7. A nota sem atividade usava `UPDATE` do `inicio`, recusado pelo A7. O fixture de imutabilidade tinha atividade não padrão, e hoje a confirmação de nota sem atividade vira 400 (A12).
   - As asserções não foram enfraquecidas. O critério caixa foi para 2027 e a recusa "caixa" com a citação da IN 1.700 continua sendo exercida. A recusa de nota sem atividade passou a usar o encerramento legítimo (`fim` em 28/02 e nota de março, o 3º mês), com a mesma recusa nomeada.
   - Um achado colateral: a nota de março é exatamente o 3º mês, e por isso o M45 também cai com esse teste ajustado.
2. **Relógio fixo em 31/12/2026.** Com o relógio em 30/09/2026, os testes originais de `servico` e de `telas` que leem o fechamento no controle falham (2 testes). O relógio fixo evita que eles dependam do dia em que rodam. Com a data real de hoje (09/10/2026) eles já passariam. O comportamento real por data é afirmado nos testes novos de A1 (T-A1) e por mim com relógio em 5 datas. Não vi comportamento escondido pelo relógio fixo.
3. **A8 contra a Lei 9.430, art. 5º, §§ 1º e 2º** (texto conferido na cópia da rodada 1). O § 1º diz "em até três quotas". O § 2º diz que nenhuma quota pode ser inferior a R$ 1.000,00 e que imposto abaixo de R$ 2.000,00 é pago em quota única. Resultados do produto:

   | Imposto | 2 quotas | 3 quotas |
   | --- | --- | --- |
   | 1.999,99 | não | não (só quota única) |
   | 2.000,00 | 1.000,00 e 1.000,00 | não |
   | 2.999,99 | 1.500,00 e 1.499,99 | não |
   | 3.000,00 | 1.500,00 e 1.500,00 | 1.000,00 em cada |
   | 3.000,01 | 1.500,01 e 1.500,00 | 1.000,00; 1.000,00; 1.000,01 |
   | 10.000,01 | 5.000,01 e 5.000,00 | 3.333,34; 3.333,34; 3.333,33 |

   A soma fecha em todos. O resíduo vai para a última quota. Juros em texto: 1ª "sem juros", 2ª "1%", 3ª "Selic acumulada de [mês do 2º subsequente] + 1%". É o que o § 3º descreve. Vencimentos de um T4 de 6.000,00: quota única 29/01/2027; duas quotas 29/01 e 26/02; três quotas 29/01, 26/02 e 31/03.
4. **A12 não impede confirmar nota legítima.** Em 4 notas legítimas (T1 e T2, inclusive a de 31/03 e a de 01/04) o serviço confirma todas. A API aceita o id em texto de dígitos (201). A tela aceita nota da base (302).
5. **A7 não bloqueia o encerramento legítimo.** O serviço encerra, a API devolve 200 e a tela 302. Fluxo "encerrar a padrão e abrir outra padrão" funciona: nota de fevereiro a 32% e de agosto a 8% apuram certo. O mutante N28, que bloquearia o encerramento legítimo, derruba 7 testes.
6. **A2: `_valor_decimal` com o teto exato.** "9999999999999.99" é aceito (201). "10000000000000.00" e "10000000000000" são recusados. `Decimal('1E+13')` e `Decimal('NaN')` são recusados. Id 0 dá 404, -1 dá 400 e 10**30 dá 400. A soma de duas integrais no teto tem o resíduo R2.
7. **A3 não bloqueia receitas legítimas.** Ver seção 2. O limite fica na observação R6.
8. **Migração.** `0009` foi editada no lugar. Isso só é seguro enquanto nenhum ambiente a tiver aplicado. Ela não está na branch principal do repositório (`git branch --contains 29d179d` lista só `dl079` e `dl080`), e a `dl080` foi feita sobre `c8ab98a`. Uma base que já tenha rodado a `0009` antiga não recebe os gatilhos novos.

## 7. Isolamento, permissões e entrada estranha

- **Matriz executada** nas 11 rotas de API (7 de leitura e 9 de escrita no cenário) e nas 16 telas (7 de consulta, 6 de formulário e 9 de POST):

  | Perfil | API | Tela |
  | --- | --- | --- |
  | Gestor, administrador, analista, financeiro | leitura 200, escrita 2xx | consulta 200, formulário 200 (uma nota fora da base responde 404) |
  | PARALEGAL | leitura 200, escrita 403 | consulta 200, formulário e POST 403 |
  | CLIENTE | 403 | 403 |
  | Anônimo | 401 ou 403 | 302 para o login |
  | Gestor de outro escritório | 404 | 404 |

  Nenhum POST negado alterou estado. As contagens de receitas, atividades, medidas e confirmações foram iguais antes e depois.
- **IDOR.** Com a URL da empresa B do mesmo escritório e ids da empresa A, o encerramento, o estorno, a revogação e a confirmação de retenção respondem 404. O lançamento com `atividade_id` de A em B responde 400. Os GET de formulário com ids alheios respondem 404. Empresa de outro escritório responde 404 nos dois sentidos.
- **CSRF.** Com verificação ativa, os 9 POST de API e os 9 de tela devolvem 403. Com token válido a receita grava (302).
- **Entrada estranha.** Zero 500 nas varreduras da rodada 1 (45 corpos de API, 19 consultas, 17 POST de tela e os corpos malformados). Os 500 que sobram estão em R1 e R2.

## 8. Propostas de teste

Todos passam contra o produto corrigido, exceto T-R1 e T-R2, que falham hoje e devem passar depois da correção.

**T-R1 (caractere substituto).** Parametrizar com o JSON cru `"\ud800"` em `receitas.descricao`, `receitas.suporte`, `estornar.motivo`, `integrais.observacao`, `medidas.numero_processo`, `medidas.orgao`, `medidas.suporte` e `revogar.motivo`. Cada um deve devolver 400 e não gravar.

**T-R2 (soma das integrais).** Duas integrais (9.999.999.999.999,99 e 0,01) no mesmo trimestre. Declarar deve devolver 400 ou 409 nomeado, sem 500, na API e na tela. Nada é gravado.

**T-R4a (duplicidade não bloqueia o legítimo).**
- Receita igual (mesmo valor e suporte) em outra atividade passa.
- Receita igual em outro trimestre passa.
- Receita igual em **outra empresa do mesmo escritório** passa, e a mensagem da recusa de A nunca cita receita de B. Isso mata N13, N14 e N15.

**T-R4b (gatilho da atividade).** `UPDATE ... SET fim='2026-06-30', padrao=false WHERE id=...` recusado, e também `SET fim=..., inicio=...`. Isso mata o N26.

**T-R4c (teto do identificador).** `escrituracao_id` e `atividade_id` iguais a 2**63 e 10**30 devolvem 400. Isso mata o N33.

## 9. Suíte, lint e verificações

| Verificação | Resultado | Classificação |
| --- | --- | --- |
| `pytest` completo, uma única invocação, sem `-n`, na árvore auditada | **1 failed, 7849 passed, 53 skipped, 2 warnings, 4 subtests passed in 647,63s** | Testado |
| Falha única | `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É preexistente: exige sintaxe do Python 3.14 e aqui roda 3.13 (`SyntaxError: multiple exception types must be parenthesized`). Reproduzi isoladamente | Testado |
| Linha de base | Rodada 1: 7.786 passaram. Agora 7.849, ou seja, +63, que são os 63 testes novos de `test_dl079_auditoria_r1.py` (conferido com `--collect-only`). Total de `test_dl079_*`: 278 testes | Testado |
| Warnings | 2, preexistentes (`RemovedInDjango2028Warning`) | Testado |
| `ruff check .` | All checks passed | Testado |
| `ruff format --check .` | 525 arquivos já formatados | Testado |
| `manage.py check` | sem problemas | Testado |
| `makemigrations --check --dry-run` | No changes detected | Testado |
| Migração revertida e reaplicada | `migrate` completo; `migrate fiscal 0008` (6 gatilhos, 6 funções e 2 tabelas somem); `0009` de novo (voltam); `0008` e `migrate` outra vez, tudo íntegro | Testado |
| `pwsh ./scripts/validate-docs.ps1` | `pwsh` ausente | **Não testado** |
| Meus testes de exploração (199 passam e 3 falham, na cópia) | Os 3 que falham dependiam de apagar critério, de confirmar nota sem atividade e de `UPDATE` direto, e as correções A7 e A12 mudam isso por desenho | Testado |

A árvore auditada terminou com `git status --short` e `git diff --stat` vazios.

## 10. Limitações e o que não foi testado

- **Python 3.14** (CI), navegador, acessibilidade, volume acima de 55 notas por trimestre, banco que não seja PostgreSQL 16, backup e restauração, e a interação com o fechamento de período da contabilidade: **Não testado**.
- **`validate-docs.ps1`:** **Não testado**. O `pwsh` não está disponível.
- **Normas:** as leituras da IN RFB 2.305 e 2.306 (cópia), da Portaria MGI e do andamento das ADI 7936 e 7944 seguem como na rodada 1: fonte secundária ou cópia. Reli apenas o texto da Lei 9.430, art. 5º, e da Lei 9.249, art. 15, § 1º, III e IV, nas cópias da rodada 1.
- **As regras de 2027 em diante** são as de 2026 estendidas, sem texto legal que as confirme.
- **A validação profissional** das regras (HI-100 a HI-108, HI-114, HI-115 e PE-83) continua do Fred.
- **Mutação em cópia:** cada mutante rodou só nos 8 arquivos `test_dl079_*.py`, não na suíte inteira.

Arquivos relevantes na cópia auditada (todos em `/home/user/wt-aud079b`):

- `apps/fiscal/presumido.py`
- `apps/fiscal/presumido_calculo.py`
- `apps/fiscal/api_presumido.py`
- `apps/fiscal/views_web.py`
- `apps/fiscal/migrations/0009_dl079_presumido.py`
- `apps/fiscal/tests/test_dl079_auditoria_r1.py`

Os experimentos estão em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud079/rc/` (`mut2.py`, `tabela_m.md`, `tabela_n.md` e `wtx/apps/fiscal/tests/test_aud079_rc.py`).
