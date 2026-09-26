# DL-043 — Parâmetros contábeis por empresa e zeramento do resultado

**Demanda:** fila aprovada pelo Fred (plano mestre §16; RC-88) e ordem de
26/09/2026 de *"seguir para a próxima etapa sem parar para perguntar"*. Regras
de negócio confirmadas pelo Fred em 2026-09-20: **RC-104** (zeramento por
lançamento, em duas etapas, destino pelo sinal) e **RC-105** (periodicidade
alternativa e por empresa). Resolve o **BL-474**.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — lançamento, saldo, competência e documento entregue.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** `claude/vigilant-bardeen-jo12l4` → `main`, depois do merge da DL-042.

O plano antigo `DL-016-F3` (branch `claude/dl-016-f3-encerramento-competencia`,
nunca integrada) tratava do **fechamento da competência mensal**, que já existe
(DL-016 fatia 1 e DL-031). Ele não é a base desta etapa e fica superado.

## Problema

Sem zeramento, as contas de receita e despesa acumulam saldo indefinidamente, o
Balanço só fecha mostrando o resultado não transferido (pergunta ainda aberta de
21/09) e o escritório não consegue encerrar o exercício pelo produto. Não existe
lugar para guardar parâmetro contábil por empresa.

## Fatia 1 — Parâmetros contábeis por empresa, com vigência

- Conceito próprio (não campos soltos em `Empresa`), no molde do
  `HistoricoRegimeTributario` (DE-039): **periodicidade do zeramento**
  (mensal, trimestral, anual) e **três contas de destino** — resultado do
  exercício, lucros acumulados, (-) prejuízos acumulados — com `vigencia_inicio`
  e `vigencia_fim`.
- Uma única vigência aberta por empresa; vigências não se sobrepõem; no banco.
- As três contas são analíticas, da mesma empresa e do grupo do Patrimônio
  Líquido; a de prejuízos é retificadora (natureza devedora dentro do PL, RC-61).
- Empresa em modo livro-caixa não recebe parâmetro contábil (DL-038).
- API e admin; tela na fatia 3.

## Fatia 2 — Zeramento

- Serviço que, para um período da periodicidade vigente, gera **dois
  lançamentos** na data final do período:
  1. contas de receita e despesa (analíticas, com saldo no período) contra a
     conta de resultado do exercício;
  2. saldo da conta de resultado do exercício contra lucros acumulados (credor)
     ou (-) prejuízos acumulados (devedor), pelo sinal.
- Valores em `Decimal`, partidas dobradas iguais, dentro de **uma** transação.
- **Idempotente:** repetir o zeramento do mesmo período não duplica; se houve
  lançamento novo no período depois do zeramento (competência ainda aberta),
  um novo pedido gera só o **complemento** da diferença, também idempotente.
- Recusado em competência encerrada (RC-57); a correção segue o estorno
  (RC-103).
- Só ADMINISTRADOR e GESTOR (mesma regra do fechamento, RC-102), verificado no
  servidor; trilha de auditoria na mesma transação.
- Lançamentos identificáveis como zeramento (histórico padronizado e chave de
  idempotência determinística), para o Razão e a conferência.

## Fatia 3 — Telas

Parâmetros na empresa; ação "Zerar resultado do período" na tela do fechamento,
com prévia dos valores antes de gravar e mensagem do que foi gerado.

## Critérios de aceite

1. Parâmetro com vigência: sobreposição e segunda vigência aberta recusadas no
   banco; contas de destino inválidas recusadas com mensagem.
2. Casos de referência calculados à mão: lucro, prejuízo, resultado zero,
   só receitas, só despesas, conta retificadora de receita (devoluções), centavos.
3. Depois do zeramento, receitas e despesas analíticas ficam com saldo zero no
   período, e o resultado aparece em lucros ou prejuízos acumulados pelo sinal.
4. Balancete antes e depois concilia: soma dos débitos igual à dos créditos, e a
   variação do PL igual ao resultado apurado.
5. Repetição e complemento sem duplicidade; concorrência de dois pedidos no
   PostgreSQL resulta num único zeramento.
6. Competência encerrada recusa; papel sem permissão recebe 403 sem gravar.
7. Periodicidade trimestral e anual zeram só no último mês do período; a
   mensal, todo mês.
8. Isolamento entre empresas e escritórios em todas as portas.
9. Suíte completa, lint, formatação, `check`, `makemigrations --check`,
   migração em banco vazio e em SQLite.

## Pendências e hipóteses

- **HI-24:** o zeramento é disparado pelo usuário na tela do fechamento, e não
  automaticamente ao encerrar a competência. Reversível; confirmar com o Fred.
- A destinação do lucro (dividendos, reservas) fica fora: é outra etapa, com
  fonte normativa (Lei 6.404/76) levantada antes.
- Validação profissional dos casos de referência é do Fred.

## Rodada 1 da auditoria

[Relatório integral](../auditorias/2026-09-26-dl-043-rodada-1.md) em `c021436`:
**REPROVADA**. Bloqueadores B1 (conta com filhas conta o resultado em dobro) e B2
(zeramento fora de ordem, complemento tardio ou meses concorrentes contam em
dobro); alta B3 (erros previsíveis viram 500; 200 contas não zeram); médias B4
(chave de zeramento forjável), B5 (cálculo quadrático), B6 (mutantes
sobreviventes); baixas B7, B8, B10. Decisões da correção em **DE-078** e
**HI-25**; B9 (sem admin) decidido na DE-078. P1 (meses alternados de lucro e
prejuízo inflam as duas contas do PL) em consulta ao manual do sistema de
referência antes de ir ao Fred. Correção única em andamento, depois uma
reconferência.

## Correção da rodada 1

Feita na worktree `wt-dl043c`, branch `dl043-correcao`, a partir de `70dbdc5`
(que já trazia o relatório da rodada 1 e a DE-078). Sem migração nova — a
DE-078 previu isso como possível se a trava por empresa exigisse tabela
própria, mas `select_for_update()` sobre a própria linha de `Empresa` bastou.

- **B1 (BLOQUEADOR, hierarquia dobra o resultado):** `_calcular_zeramento`
  passou a ler `debitos_proprios_totais`/`creditos_proprios_totais` de
  `apurar_balancete` (saldo PRÓPRIO, não o `saldo_final` consolidado que soma
  filhas — regra única de saldo da DE-020) para cada conta de
  receita/despesa, sintética ou não. Sintética com saldo próprio diferente de
  zero (só possível em dado legado, fora do fluxo normal de lançamento)
  recusa com `ParametroContabilInvalido` em vez de ignorar ou dobrar o valor.
  Testado: `test_b1_hierarquia_zera_pelo_saldo_proprio_sem_dobrar`,
  `test_b1_sintetica_legada_com_saldo_proprio_recusa_sem_gravar`.
- **B2 (BLOQUEADOR, ordem cronológica e concorrência):** nova
  `_recusar_zeramento_fora_de_ordem` recusa zerar/complementar um período se
  já existe zeramento gravado com data posterior (`ZeramentoForaDeOrdem`,
  subclasse de `CompetenciaEncerrada`). Nova trava por empresa
  (`_travar_empresa_para_operacao_de_zeramento`, `select_for_update()` na
  própria linha de `Empresa`) serializa todo `zerar_resultado`,
  `registrar_parametro_contabil` e `encerrar_vigencia_de_parametro_contabil`
  da mesma empresa, fechando a lacuna que a trava só de competência deixava
  entre meses diferentes. Testado:
  `test_b2_zerar_fora_de_ordem_e_recusado_sem_gravar`,
  `test_b2_complemento_tardio_depois_de_periodo_posterior_e_recusado`,
  `test_b2_concorrencia_entre_meses_diferentes_nunca_conta_em_dobro` (15
  rodadas reais em PostgreSQL, `threading.Barrier`).
- **HI-25 (período não terminado):** `_periodo_de_zeramento` recusa com
  `ParametroContabilInvalido` quando a data final do período é posterior a
  hoje. Testado: dentro de `test_b3_5b_mes_futuro_e_400_sem_gravar`.
- **B3 (ALTA, quatro 500 previsíveis):**
  - RC-79 (mais de 200 contas): nova `_dividir_em_lancamentos_balanceados`
    parte a etapa 1 em vários lançamentos balanceados, cada um com sua
    própria contrapartida recalculada; `zerar_resultado` grava todos numa só
    transação. Testado:
    `test_b3_5a_duzentas_contas_de_resultado_divide_a_etapa1_sem_500`.
  - Mês futuro: coberto pela HI-25 acima, agora 400 em vez de 500 por violar
    RC-77 depois. Testado: `test_b3_5b_mes_futuro_e_400_sem_gravar`.
  - Chave já ocupada: com `_proximo_complemento` corrigido (pega o maior
    número já usado e soma 1, em vez de contar linhas), colisão deixou de ser
    alcançável pelo fluxo normal; o teste força o caminho defensivo com
    `monkeypatch` para provar que a view devolve 409, não 500. Testado:
    `test_b3_5c_chave_ja_ocupada_e_409_sem_gravar`.
  - `lock_timeout` (SQLSTATE 55P03) na trava de empresa: convertido para
    `EmpresaTravadaPorOutraOperacao` (subclasse de
    `CompetenciaOperacaoRecusada`), views devolvem 409. Testado:
    `test_b3_5d_lock_timeout_real_na_empresa_e_409_sem_500`.
- **B4 (MÉDIA, chave `zeramento:` forjável):** `criar_lancamento` recusa
  qualquer chave de idempotência iniciada por `zeramento:` vinda de fora, com
  `LancamentoInvalido`; novo parâmetro interno
  `permitir_prefixo_reservado=True` usado só por `zerar_resultado`, nunca
  exposto em view/API. Testado:
  `test_b4_chave_reservada_e_400_e_nao_bloqueia_o_gestor` (recusa a um
  ANALISTA que tenta forjar, depois confirma que o zeramento do GESTOR
  continua funcionando).
- **B5 (MÉDIA, custo quadrático):** resolvido como efeito colateral da
  correção do B1 — `apurar_balancete` passou a ser chamado UMA vez por
  zeramento (não uma vez por conta). Testado:
  `test_b5_numero_de_consultas_e_constante_com_o_numero_de_contas` (compara o
  número de consultas com poucas e com muitas contas de resultado, via
  `CaptureQueriesContext`).
- **B6 (MÉDIA, mutantes sobreviventes):** ver tabela mutante → teste abaixo.
- **B7 (BAIXA, contas de destino inadequadas):** `registrar_parametro_contabil`
  passou a recusar conta de resultado do exercício ou de lucros/prejuízos
  acumulados que seja sintética (tem filhas) ou inativa, e recusa conta de
  lucros acumulados com natureza devedora. Coberto pelos testes de
  `test_dl043_parametro_contabil.py` (critérios de contas de destino) e pela
  suíte nova onde essas contas aparecem nos cenários de referência.
- **B8 (BAIXA, trilha sem IP):** `zerar_resultado` passou a aceitar
  `request=None` opcional e a registrar `endereco_ip` na trilha quando
  presente; a view passa a chamar com `request=request`. Testado:
  `test_b8_trilha_do_zeramento_tem_ip_usuario_e_escritorio`.
- **B9 (BAIXA, sem admin do parâmetro):** nenhuma mudança de código — a
  DE-078 confirmou que a ausência de admin é aceitável neste momento (mesmo
  padrão já usado para outros modelos operacionais do módulo).
- **B10 (BAIXA, corrida entre `registrar_parametro_contabil` e
  `zerar_resultado`):** resolvido como efeito colateral da mesma trava por
  empresa do B2 — `registrar_parametro_contabil` e
  `encerrar_vigencia_de_parametro_contabil` agora travam a empresa antes de
  ler ou escrever o estado de vigência. Sem teste de concorrência real
  dedicado (a auditoria não tinha reproduzido B10; o teste de concorrência do
  B2 já exercita a mesma trava).

### Mutante → teste que mata

| Mutante | Teste que mata |
| --- | --- |
| M4 (remover checagem de competência ABERTA) | `test_m4_competencia_encerrada_sem_movimento_recusa_sem_trilha_nem_gravacao` |
| M12 (ignorar `vigencia_fim`) | `test_m12_zerar_apos_vigencia_fim_sem_sucessora_e_recusado` |
| M14 (incluir sintéticas no universo sem tratamento) | `test_b1_sintetica_legada_com_saldo_proprio_recusa_sem_gravar` (confirmado reaplicando a mutação equivalente na correção: sem a recusa, o teste falha; com ela, passa) |
| M16 (remover `registrar()` do zeramento) | `test_b8_trilha_do_zeramento_tem_ip_usuario_e_escritorio` |
| M17 (remover `registrar()` do parâmetro) | `test_m17_trilha_do_parametro_contabil_e_gravada` |
| M20 (encerrar vigência com início futuro) | `test_m20_encerrar_vigencia_com_inicio_futuro_e_409_sem_gravar` |
| M22 (anual aceitando mês diferente de dezembro) | `test_m22_anual_recusa_cada_mes_diferente_de_dezembro` (parametrizado 1–11) e `test_m22_anual_aceita_dezembro` |
| M24 (`_conta_da_empresa_ou_400` sem filtro de empresa) | `test_m24_conta_de_outra_empresa_tem_a_mesma_mensagem_que_conta_inexistente` |

### Ponto levado à arquitetura, não decidido aqui

Na concorrência entre meses diferentes (teste do B2), um dos dois lados pode
legitimamente receber `ZeramentoForaDeOrdem` quando perde a corrida contra o
outro mês (aconteceu em 7 das 15 rodadas medidas) — é a recusa correta, não
uma falha; o total continua exato (150,00) nas 15 rodadas. A DE-078/relatório
da rodada 1 fala em "0 falhas" para esse caso; não decidi se essa recusa
legítima deveria contar como "falha" para efeito de aceite — reporto a
diferença de leitura, e o teste só marca falha para exceções que não sejam
`ZeramentoForaDeOrdem`.
