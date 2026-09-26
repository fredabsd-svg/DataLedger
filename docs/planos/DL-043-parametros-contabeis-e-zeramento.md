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
  lucros acumulados com natureza devedora. ⚠️ **Correção da reconferência
  (achado R3):** a frase acima, ao ser escrita, afirmava cobertura que não
  existia — os mutantes N14 (Lucros credora), N15 (destino ativo) e N16
  (destino folha) sobreviviam à suíte inteira (2672 passed), sem nenhum
  teste dedicado. Fechado com três testes novos em
  `test_dl043_parametro_contabil.py` (`test_n14_lucros_com_natureza_
  devedora_e_400_via_http_sem_gravar`, `test_n15_destino_inativo_e_400_
  via_http_sem_gravar`, `test_n16_destino_com_filha_e_400_via_http_sem_
  gravar`), cada um matando o mutante correspondente (confirmado ao vivo:
  reaplicar cada mutação faz o teste falhar; revertida, volta a passar).
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
  ler ou escrever o estado de vigência. ⚠️ **Correção da reconferência
  (achado R3):** a auditoria reproduziu B10 por conta própria (três rodadas
  com threads reais, terminando em `VigenciaParametroContabilConflitante`
  nas três) e mediu que o mutante N6 (tirar a trava) sobrevivia — este
  parágrafo, na versão anterior, dizia "sem teste dedicado" como se fosse
  aceitável; passou a ser um teste dedicado:
  `test_n6_registrar_vigencia_concorrente_com_zeramento_sempre_recusa`
  (`test_dl043_parametro_contabil.py`, três rodadas reais, mata N6).

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

**Decisão do `arquiteto-senior` (2026-09-26):** a leitura do desenvolvedor está
certa. "0 falhas" no critério de concorrência significa **nenhuma exceção
inesperada e nenhum valor contado em dobro**. A recusa `ZeramentoForaDeOrdem`
de quem perde a corrida é a regra cronológica da DE-078 (item 2) funcionando:
o mês recusado é zerado depois, na ordem, pelo próprio usuário (se o mês
posterior já foi zerado, o caminho é estornar esse zeramento e refazer na
ordem, RC-103). Não é falha de aceite.

### Achado de integração: estorno do zeramento fora de ordem ficava sem efeito

Encontrado na integração da correção com as telas, antes da reconferência:
`_recusar_zeramento_fora_de_ordem` contava QUALQUER lançamento com chave
`zeramento:` e data posterior, inclusive um que já tivesse sido ESTORNADO
(`estornos.exists()` verdadeiro) — o caminho de correção que a própria
mensagem da recusa recomenda (estornar o zeramento fora de ordem e refazer
na ordem certa, RC-101/RC-103) não funcionava: depois de estornar o
zeramento de um mês posterior, o mês anterior continuava recusado para
sempre, porque a chave do zeramento estornado nunca desaparece do banco (o
estorno é um lançamento NOVO, nunca uma edição).

Corrigido acrescentando `estornos__isnull=True` ao filtro — um zeramento com
QUALQUER estorno já lançado deixa de contar como "zeramento posterior"; se
a etapa 1 foi dividida em várias partes (RC-79) e só algumas partes foram
estornadas, a recusa continua valendo para as que restam, porque cada
`LancamentoContabil` tem seu próprio estorno (ou a ausência dele).

O cálculo de complemento (`_calcular_zeramento`) não precisou de mudança: já
lê o saldo PRÓPRIO via `apurar_balancete`, que soma TODOS os lançamentos
(inclusive estornos) — o estorno já neutraliza o efeito no saldo por
construção, sem nenhuma lista própria de "o que já foi zerado" para manter
sincronizada. **Ressalva encontrada e não decidida aqui:** como o cálculo lê
saldo acumulado ATÉ a data final do PRÓPRIO período, o estorno só neutraliza
corretamente o zeramento errado se for datado até esse mesmo último dia — um
estorno datado depois (por exemplo, "hoje", se a correção acontece semanas
depois do erro) ficaria fora da janela que o zeramento daquele período lê ao
ser refeito, e a correção pareceria incompleta. A mensagem da recusa passou a
avisar disso; se a prática real do escritório é sempre corrigir "hoje", pode
valer a pena um aviso mais forte (ou uma validação) no próprio
`estornar_lancamento` — não decidido aqui, é pergunta de produto para o Fred,
não algo que o código deva presumir.

Testes novos em `test_dl043_correcao_rodada1.py`: `test_integracao_
zeramento_fora_de_ordem_recupera_com_estorno_e_refazer` (zera abril, estorna,
zera março com sucesso, refaz abril com o valor exato — 200,00 — sem
duplicar os 500,00 do cálculo errado nem perder valor), `test_integracao_
novo_zeramento_de_abril_e_idempotente` (repetir o zeramento refeito não gera
lançamento nem muda saldo) e `test_integracao_zeramento_posterior_nao_
estornado_continua_bloqueando` (sem estornar nada, a recusa do B2 continua
valendo — a correção não afrouxa o bloqueio original).

## Integração com as telas (fatia 3)

Ao juntar a correção com as telas, três portas da tela ainda não conheciam as
recusas novas do serviço — um estouro de trava, uma chave ocupada ou uma recusa
de lançamento virariam 500 na tela, e o zeramento feito pela tela gravava a
trilha sem IP (achado B8 na porta web). Ajuste de integração em
`views_web.py`: a tela passa `request` ao serviço e trata as mesmas recusas que
a API mapeia para 400/409, como mensagem, sem gravar. Seis testes novos em
`test_dl043_fatia3_telas.py`; reprovam com o `views_web.py` anterior (medido:
6 falhas) e passam com o ajuste.

## Correção da reconferência

A [reconferência](../auditorias/2026-09-26-dl-043-reconferencia.md) reprovou
a correção da rodada 1 por uma REGRESSÃO (R1, ALTA) e apontou que a
orientação de recuperação por estorno (R2, MÉDIA) prometia uma data que
nenhuma porta do produto aceita. Decisões: **DE-078, adendo**
(`docs/projeto/decisoes.md`). Pelo AGENTS.md §3.1, esta foi a última
correção: sem terceira rodada de auditoria — o fechamento é verificado
pelos testes que a própria reconferência propôs e pela morte dos mutantes
N6, N14, N15 e N16.

- **R1 (ALTA, regressão):** a trava de empresa
  (`_travar_empresa_para_operacao_de_zeramento`) usava `select_for_update()`
  puro (`FOR UPDATE`), que conflita com o `FOR KEY SHARE` que toda FK
  `DEFERRABLE INITIALLY DEFERRED` do Django verifica no COMMIT — a
  reconferência mediu 16 de 30 rodadas HTTP concorrentes (`POST
  /lancamentos/` × `POST` do zeramento do MESMO mês) terminando em deadlock
  real (SQLSTATE 40P01) e HTTP 500. Corrigido trocando para `select_for_
  update(no_key=True)` (`FOR NO KEY UPDATE`), que continua serializando
  zeramento/vigência entre si mas não conflita com `FOR KEY SHARE`. Defesa
  em profundidade: nova `_e_deadlock` (SQLSTATE 40P01) traduzida para o
  mesmo 409 que `_e_estouro_de_lock_timeout` (55P03) já traduz, nos três
  pontos de trava (competência, transição de competência, empresa).
  Testado: `test_r1_lancamento_concorrente_com_zeramento_do_mesmo_mes_nunca_da_500`
  (30 rodadas HTTP reais; confirmado que **2 de 30** rodadas dão 500 com
  `no_key=False`, o mesmo mecanismo que a reconferência mediu) e
  `test_r1_variante_criar_lancamento_segurando_a_transacao_nunca_bloqueia_o_zeramento`
  (janela alargada em 0,3s com `Event` — confirmado **5 de 5** rodadas
  fora do esperado com `no_key=False`, batendo com a medição "5 de 5" da
  própria reconferência).
- **R2 (MÉDIA):** a mensagem de `ZeramentoForaDeOrdem` orientava estornar
  "datando o estorno até o último dia do período" — nenhuma porta aceita
  informar a data de um estorno (`EstornarLancamentoView` recusa o campo
  `data`; a tela não chama `estornar_lancamento`), e seguir a única porta
  real (estorno pela API, que sempre data "hoje") infla Lucros e
  Prejuízos e distorce o resultado dos períodos envolvidos. Corrigido
  garantindo a ordem NA ENTRADA: nova `_recusar_se_periodo_anterior_tem_
  saldo` recusa (`ParametroContabilInvalido`, "Zere primeiro MM/AAAA")
  zerar um período enquanto o período de encerramento IMEDIATAMENTE
  ANTERIOR da mesma periodicidade tiver saldo próprio ≠ 0 em alguma conta
  de resultado ANALÍTICA no seu último dia — ignorada quando esse período
  anterior termina antes do início da vigência atual (primeiro período de
  uma vigência nova não é bloqueado por saldo de implantação), e também
  quando o período anterior JÁ TEM zeramento gravado (não estornado) —
  nesse caso o caminho certo é complementar o ÚLTIMO período zerado, não
  bloquear o seguinte. Uma única `apurar_balancete` para o período
  anterior (B5: nº de consultas continua constante). A mensagem de
  `ZeramentoForaDeOrdem` deixou de pedir data de estorno: agora explica
  que um lançamento novo num período anterior ao último zerado é
  absorvido pelo COMPLEMENTO do último período zerado. O filtro
  `estornos__isnull=True` (da correção anterior) foi mantido. Testado, só
  por portas HTTP (R2.7): `test_r2a_zerar_fora_de_ordem_e_recusado_na_
  entrada_depois_funciona_na_ordem`, `test_r2b_lancamento_tardio_em_
  periodo_ja_zerado_e_absorvido_pelo_complemento_do_ultimo`,
  `test_r2c_mes_sem_movimento_no_meio_nao_trava_o_seguinte`,
  `test_r2d_primeiro_periodo_da_vigencia_nao_e_bloqueado_por_saldo_
  anterior_a_ela`. O teste antigo que estorna com `data=` explícita no
  serviço (`test_integracao_zeramento_fora_de_ordem_recupera_com_estorno_
  e_refazer` e os dois relacionados) continuou válido como teste de
  SERVIÇO para um estado LEGADO (uma empresa poderia ter esse estado
  gravado de antes desta correção) — mas passou a simular esse estado
  com `criar_lancamento`/`permitir_prefixo_reservado=True` em vez de
  chamar `zerar_resultado` fora de ordem, porque a R2 agora RECUSA essa
  chamada na entrada; não é mais a única prova, como o achado pedia.
- **R3 (BAIXA):** as validações do B7 (Lucros credora, destino ativo,
  destino folha) e a trava do B10 tinham código sem teste — mutantes N14,
  N15, N16 e N6 sobreviviam à suíte inteira. Fechado com quatro testes
  novos em `test_dl043_parametro_contabil.py`: `test_n14_lucros_com_
  natureza_devedora_e_400_via_http_sem_gravar`, `test_n15_destino_
  inativo_e_400_via_http_sem_gravar`, `test_n16_destino_com_filha_e_400_
  via_http_sem_gravar` e `test_n6_registrar_vigencia_concorrente_com_
  zeramento_sempre_recusa` (três rodadas reais com threads). A frase deste
  documento que afirmava cobertura inexistente ("Coberto pelos testes de
  test_dl043_parametro_contabil.py") foi corrigida nas seções B7 e B10
  acima.
- **R4 (BAIXA):** a recusa do prefixo `zeramento:` (`criar_lancamento`)
  usava `str.startswith` puro, sensível a maiúsculas — em SQLite (nunca em
  produção — DE-014/BL-50) as buscas que localizam zeramento gravado usam
  `LIKE`, insensível a caixa ali, reabrindo o ataque do B4 em SQLite com
  uma chave `ZERAMENTO:…`. Corrigido normalizando os dois lados com
  `.lower()`. Testado:
  `test_r4_prefixo_reservado_recusa_sem_diferenciar_maiuscula`
  (parametrizado com `ZERAMENTO:`, `Zeramento:` e `zErAmEnTo:`).
- **R5 (BAIXA, `especialista-frontend`, autorização pontual):**
  `templates/contabilidade/zerar_resultado.html` mostrava só o primeiro
  lançamento da etapa 1 quando ela é dividida (RC-79). Corrigido listando
  `resultado.lancamentos_etapa1` (a lista completa) em vez de `resultado.
  lancamento_etapa1` (singular, mantido só para compatibilidade).
  Testado: `test_r5_etapa1_dividida_lista_todos_os_lancamentos_na_tela`
  (205 contas, confere os DOIS números de lançamento no HTML).
- **R6 (BAIXA):** o comentário de bloco em `views_web.py` (perto da linha
  3803) dizia que a prévia do zeramento exigia só `_pode_ler`, mas o
  comportamento sempre foi `_pode_fechar_competencia` — alinhado. O teste
  `test_analista_le_previa_mas_nao_confirma` foi renomeado para
  `test_analista_recebe_403_na_previa_e_na_confirmacao`, refletindo o que
  o próprio corpo do teste sempre verificou.

### Mutantes da reconferência → teste que mata

| Mutante | Teste que mata |
| --- | --- |
| N6 (sem trava de empresa em `registrar_parametro_contabil`) | `test_n6_registrar_vigencia_concorrente_com_zeramento_sempre_recusa` |
| N14 (sem exigir Lucros credora) | `test_n14_lucros_com_natureza_devedora_e_400_via_http_sem_gravar` |
| N15 (sem exigir destino ativo) | `test_n15_destino_inativo_e_400_via_http_sem_gravar` |
| N16 (sem exigir destino folha) | `test_n16_destino_com_filha_e_400_via_http_sem_gravar` |

Todos os quatro confirmados ao vivo: reaplicar a mutação correspondente faz
o teste falhar; revertida, volta a passar (mesma disciplina da rodada 1).

## P1 — lucros e prejuízos acumulados no zeramento mensal

A auditoria perguntou (P1) o que acontece quando a empresa alterna lucro e
prejuízo entre meses: com o destino pelo sinal (RC-104), as duas contas do PL
crescem. A pesquisa não conseguiu ler a central de soluções do sistema de
referência (403, limite já documentado em
[fontes-de-referencia.md](../projeto/fontes-de-referencia.md)); os títulos
indexados dos artigos sugerem que lá a compensação é lançamento separado, ligado
à demonstração anual. Registrado como **HI-26** e ampliação da **PE-38**; a
DL-043 entrega o que o RC-104 confirmou e **não** compensa automaticamente.

## Verificação do fechamento (sem terceira rodada)

AGENTS.md §3.1 proíbe a terceira rodada de auditoria. A correção da
reconferência (`cbe7876`) foi conferida pelo `auxiliar-verificacao`, de forma
independente, contra a evidência que a própria reconferência pediu
(2026-09-26):

- Os seis casos de teste propostos existem e passam (11 sub-casos); os cinco
  arquivos `test_dl043_*.py`: 135 passed.
- Mutantes aplicados em cópia descartável, todos mortos: N6, N14, N15, N16, R1
  (sem `no_key=True`: o teste principal reprovou em todas as execuções, com 9 e
  12 de 30 rodadas em deadlock, e a variante em 15 de 15), R2 (sem a recusa de
  período anterior) e R4 (prefixo sem `.lower()`).
- Cenário R2 reescrito do zero pela porta HTTP: zerar abril antes de março é
  recusado com "Zere primeiro 03/2026" e banco inalterado; na ordem, abril grava
  lucro de 200,00, lucros acumulados somam 500,00 e prejuízos não são tocados.
- Suíte completa no `cbe7876`: 2818 passed, 45 skipped, com o arquivo de
  versão mínima do Python desmarcado (falha de ambiente conhecida: Python 3.13
  local, 3.14 na CI).
- Ressalva registrada pelo verificador: o caso 2 não segue o roteiro literal
  "zerar, estornar, refazer" de R2.7, porque a decisão (adendo da DE-078) foi a
  terceira alternativa de R2.6 — recusar na entrada.

