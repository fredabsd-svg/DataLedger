# DL-045 — Demonstração do Resultado do Exercício (DRE)

**Demanda:** fila aprovada pelo Fred (CON-12 do plano mestre; próximo item depois
da DL-043). Decisões dele em 2026-09-26, ao aceitar a recomendação: *"Pode
seguir com a sua recomendação"* — RC-118, RC-119 e RC-120.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — demonstração contábil entregue ao cliente.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** worktree `dl045-dre`, integrada por PR depois da DL-043 (PR #49).

## Problema

O escritório não consegue emitir a DRE pelo produto. A camada de saldos (DL-032)
declara por escrito que não serve para a DRE (`apurar_saldos`, docstring): a DRE
se constrói pelo **movimento** do período, não pelo saldo de uma data. E há um
risco novo, medido no código pela pesquisa: o zeramento (DL-043) é gravado no
**último dia do próprio período**. Uma DRE de março emitida depois de zerar
março somaria o lançamento de zeramento e sairia zerada. A DRE precisa excluir
os lançamentos de zeramento.

## Fontes

- **Norma — Lei 6.404/76, art. 187 e art. 175**, lidos no Planalto e na Câmara
  em 2026-09-26, texto idêntico (PE-70).
- **NBC TG 26 (R5) item 82, NBC TG 1000 (R1) item 5.7 e ITG 1000 (2022)**, lidos
  nos PDFs do CFC em 2026-09-26: fundamentam a posição do resultado financeiro e
  a linha de equivalência patrimonial (HI-29).
- **Rotina — manual do sistema de referência:** DRE por estrutura de grupos
  associada a contas, emissão por período livre, uma única linha "antes do IR".
  Usado como rotina, nunca como norma.

## Fatia 1 — Linha da DRE na conta (RC-118)

- Campo de classificação na conta de resultado, no molde do circulante × não
  circulante da DL-033: uma das linhas do art. 187 —
  receita bruta; deduções da receita (impostos, devoluções e abatimentos);
  custo (CMV/CPV/CSP); despesas com vendas; despesas gerais e administrativas;
  receitas financeiras; despesas financeiras; outras despesas operacionais;
  outras receitas; outras despesas; resultado de equivalência patrimonial;
  provisão para IRPJ e CSLL; participações (HI-29).
- Só conta de resultado recebe a classificação; conta patrimonial com ela é
  recusada. Herança pela hierarquia no mesmo desenho da DL-033 (o
  desenvolvedor confirma o precedente e registra).
- Conta retificadora dentro do grupo segue o RC-61 (ex.: devoluções dentro das
  deduções).
- API e plano de contas; a tela entra na fatia 3.

## Fatia 2 — Apuração

- Serviço de apuração da DRE para `[inicio, fim]` pelo **movimento** do período
  (`apurar_balancete` ou consulta própria), **excluindo** os lançamentos de
  zeramento (prefixo reservado `zeramento:`, DL-043).
- Duas colunas (RC-119): **mês** e **acumulado do exercício** (do início do
  exercício até o fim do mês). Exercício = ano civil (HI-28).
- Subtotais: receita líquida, lucro bruto, **resultado antes das receitas e
  despesas financeiras**, resultado financeiro, resultado antes dos tributos
  sobre o lucro, lucro ou prejuízo líquido (NBC TG 26 item 82 e NBC TG 1000
  item 5.7, HI-29).
- Valores em `Decimal`, conciliáveis: o lucro líquido da DRE do período é igual
  ao resultado que o zeramento do mesmo período transfere (etapa 2), e igual à
  soma das contas de resultado no Balancete sem os lançamentos de zeramento.
- Isolamento por empresa e escritório; leitura consistente sob snapshot, como o
  Balanço (DE-067).

## Fatia 3 — Emissão (demonstração formal, RC-120)

- Tela e documento imprimível na classe 2 de
  [personalizacao-de-relatorio.md](../projeto/personalizacao-de-relatorio.md),
  como o Balanço (DL-034): identificação do emitente em toda página, critério de
  apuração impresso.
- **Emissão recusada** enquanto houver conta de resultado analítica com
  movimento no período **sem classificação** — a tela lista as pendências, no
  mesmo desenho do veto do Balanço.
- Tela no padrão visual da DL-044; entra pelo hub de Relatórios.

## Critérios de aceite

1. Classificação: só em conta de resultado; recusa com mensagem; herança
   documentada e testada.
2. Casos de referência calculados à mão: lucro, prejuízo, só receita, com
   deduções e devoluções (retificadora), com resultado financeiro negativo,
   com IRPJ/CSLL, centavos.
3. **DRE de período já zerado é igual à DRE antes do zeramento** (o lançamento
   de zeramento não entra), no mês e no acumulado com vários zeramentos
   mensais.
4. Conciliação: lucro líquido da DRE = resultado transferido pelo zeramento do
   mesmo período; soma de débitos e créditos conferida.
5. Acumulado do exercício = soma das DREs mensais do exercício.
6. Emissão recusada com conta sem classificação, listando as contas; nada
   emitido.
7. Documento emitido com identificação do emitente em toda página, medido no
   navegador pelo job de CI existente.
8. Autorização no servidor; isolamento entre empresas e escritórios em todas
   as portas.
9. Suíte completa, lint, formatação, `check`, `makemigrations --check`,
   migração em banco vazio e em SQLite.

## Implementação das fatias 1 e 2

Worktree `wt-dl045`, branch `dl045-dre`. Servidor + API, sem template/CSS
(a tela é a fatia 3, do `especialista-frontend`).

### Fatia 1 — classificação (RC-118)

- `ClassificacaoDre` (`models.py`, `models.TextChoices`), no MESMO molde de
  `ClassificacaoPatrimonial` (DL-033): campo `Conta.classificacao_dre`,
  `null=True`/`blank=True`, nunca inferido do código ou do nome. Treze
  linhas (as doze do plano original + "resultado de equivalência
  patrimonial", da revisão da HI-29): receita bruta, deduções da receita,
  custo, despesas com vendas, despesas gerais e administrativas, outras
  receitas, outras despesas, outras despesas operacionais, resultado de
  equivalência patrimonial, receitas financeiras, despesas financeiras,
  provisão IRPJ/CSLL, participações.
- **Precedente da DL-033 confirmado** (pedido explícito da tarefa):
  `ClassificacaoPatrimonial` NÃO tem restrição de banco — só migração
  `AddField`, sem `CheckConstraint` nem gatilho; a única guarda de
  compatibilidade com `tipo` mora em `Conta.clean()`. `ClassificacaoDre`
  segue o MESMO desenho: migração simples (`0010_dl045_conta_
  classificacao_dre.py`), guarda só em `clean()`.
- **Mapeamento linha → `TipoConta` esperado é inferência do desenvolvedor,
  reportada, não decidida como regra contábil nova** (o plano lista as
  linhas, mas não diz o `TipoConta` de cada uma — diferente da DL-033,
  onde o art. 178 nomeia Ativo/Passivo linha a linha): `TIPOS_ACEITOS_
  DA_CLASSIFICACAO_DRE` segue RC-61 (retificadora dentro do MESMO
  tipo/grupo) — "deduções da receita" é tipo RECEITA; as demais linhas de
  custo/despesa/provisão/participações são tipo DESPESA.
- **Decisão do arquiteto, 26/09/2026, revisando o mapeamento inicial:**
  aceito como estava, com UMA correção — **"resultado de equivalência
  patrimonial" pode ser GANHO ou PERDA**, então aceita conta de tipo
  RECEITA **ou** DESPESA (a perda de equivalência costuma ficar
  classificada no grupo de despesas). `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`
  passou a mapear cada linha a uma TUPLA de tipos aceitos (a maioria com
  um só elemento; só a MEP com dois). O sinal exibido não mudou: continua
  vindo de `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE` (por LINHA, fixo, lado
  CREDOR para a MEP) — uma conta de DESPESA classificada em MEP soma
  NEGATIVO ao resultado automaticamente, sem `if` especial em lugar
  nenhum. **Achado corrigido durante o ajuste**: o cálculo do resíduo por
  tipo (`residuo_por_tipo`) somava a contribuição de CADA linha
  classificada usando um `TipoConta` FIXO por linha (o "esperado" antigo)
  — com a MEP aceitando dois tipos, isso jogava a contribuição de uma
  conta de DESPESA classificada em MEP para o resíduo de RECEITA, e a
  identidade nunca fechava em zero mesmo num plano coerente. Corrigido
  atribuindo a contribuição ao `TipoConta` REAL da conta topo-classificada
  (`soma_classificada_por_tipo`, em `_apurar_coluna_dre`), não a um tipo
  fixo da linha — testado com mutação (ver tabela abaixo) e com o caso de
  referência `test_criterio1j_ganho_e_perda_de_mep_no_mesmo_periodo_
  liquido_correto` (ganho numa conta RECEITA + perda numa conta DESPESA,
  mesma linha, líquido e resíduo corretos nos dois tipos). "Deduções da
  receita" e "participações" seguem como estavam — atribuições ainda
  discutíveis, documentadas no docstring de `ClassificacaoDre` para o
  Fred confirmar.
- **Achado durante a implementação, corrigido:** o sinal NATURAL de cada
  linha da DRE não é o mesmo que o sinal natural do `TipoConta` esperado
  — "deduções da receita" é tipo RECEITA (para a guarda de `clean()`
  aceitar, RC-61), mas o lado NATURAL dela, para efeito de MAGNITUDE
  exibida, é DEVEDOR (ela é alimentada por débitos que reduzem a receita).
  Corrigido com um dict PRÓPRIO, `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE`
  (por LINHA, não por `TipoConta`) — ver o docstring dele em `models.py`
  e o teste `test_criterio2d_deducoes_com_devolucao_retificadora_por_
  heranca`, que expôs o defeito antes de chegar à entrega.
- **Herança pela hierarquia**, confirmada e testada no mesmo desenho da
  DL-033: classificar o nó TOPO consolida toda a subárvore (regra única
  de saldo, DE-020); classificação ANINHADA (pai e filho ambos
  classificados) é declarada, nunca somada duas vezes.
- Guarda de TRANSIÇÃO (mesmo molde do BL-83/DL-023 e da DL-033/HI-18):
  reclassificar uma conta que já tem movimento é recusado — reescreveria
  uma DRE de período já apurado. A PRIMEIRA classificação (gravada `None`)
  é sempre livre, mesmo com movimento.
- **API do plano de contas**: `classificacao_dre` acrescentado a
  `ContaSerializer.Meta.fields` e a `CONTRATO_POST_CONTA` (a "política dos
  cinco dicionários", BL-196 — sem isto, o campo seria recusado como "dado
  não contratado" mesmo já declarado no serializer). Validação de
  compatibilidade com `tipo` repetida no serializer (`validate()`,
  cross-field) porque o DRF não chama `Model.full_clean()` (BL-40/DE-008).
  Mesma autorização de hoje: nenhuma `permission_class` nova em
  `ContaListCreateView`.

### Fatia 2 — apuração (RC-119/RC-120, HI-28, HI-29)

- `apurar_dre(*, empresa, ano, mes)` (`services.py`) — agregação PRÓPRIA
  (`_agregar_movimento_dre_por_conta`), NUNCA `apurar_saldos` (a própria
  docstring dela avisa: "não serve para a DRE") nem `apurar_balancete` sem
  adaptação (ele conta o zeramento). Reusa só a construção de HIERARQUIA
  (`_construir_hierarquia`) do motor do Balancete.
- **Exclusão do zeramento**: `.exclude(lancamento__chave_idempotencia__
  istartswith="zeramento:")` — case-insensitive, mesma correção do achado
  R4 da reconferência da DL-043 (SQLite resolve `LIKE` sem diferenciar
  caixa).
- **Duas colunas** (RC-119): mês (`[01/mês, fim do mês]`) e acumulado do
  exercício (`[01/01, fim do mês]`, HI-28 — ano civil). Uma consulta de
  hierarquia + uma agregação por coluna — número de consultas CONSTANTE
  em relação ao número de contas (testado com 10 → 50 contas extras).
- **Subtotais (HI-29 revista após a PE-70)**: receita líquida → lucro
  bruto → resultado antes das receitas e despesas financeiras →
  resultado financeiro (destacado) → resultado antes dos tributos sobre o
  lucro → (− provisão IRPJ/CSLL) → (− participações) → lucro/prejuízo
  líquido. A ORDEM mora isolada em duas tuplas,
  `_LINHAS_ANTES_DO_RESULTADO_FINANCEIRO` e `_LINHAS_DO_RESULTADO_
  FINANCEIRO` (`services.py`) — trocar a apresentação (ex.: financeiro de
  volta para dentro do operacional, como a LETRA do art. 187, III) é
  mudar só estas duas tuplas.
- **Resíduo por tipo** (`residuo_por_tipo`, RECEITA e DESPESA): mesma
  identidade aritmética do resíduo do Balanço (DE-068/BL-496), adaptada —
  soma das raízes de cada tipo pelo lado natural do TIPO, menos a soma
  das linhas classificadas daquele tipo (convertidas de volta ao lado do
  tipo antes de somar, por causa da exceção de "deduções da receita"
  citada acima). Zero no caso são; protege contra irmãs topo-classificadas
  com natureza divergente (a aritmética do BL-486) e qualquer topologia
  não pensada.
- **Pendências** (critério 6), REVISTAS na correção da rodada 1 (ver
  seção própria abaixo — **esta afirmação, na entrega original, estava
  ERRADA**: `contas_com_classificacao_dre_aninhada` e `contas_com_
  classificacao_dre_desconhecida` NÃO eram tratadas como no Balanço; a
  auditoria mediu, achado A1): `contas_sem_classificacao_dre_com_
  movimento` (folha de RECEITA/DESPESA, com movimento na coluna, sem
  classificação própria nem ancestral — a régua é o MOVIMENTO NA COLUNA,
  não uma propriedade fixa da conta, mesma lição do BL-498/DL-033),
  `contas_com_classificacao_dre_aninhada_linha_diferente` e
  `contas_com_classificacao_dre_desconhecida` VETAM; `contas_nao_folha_
  sem_classificacao_dre_com_movimento_proprio` (BL-487) e `contas_com_
  classificacao_dre_aninhada_mesma_linha` são informativas (nunca vetam)
  — agora sim a MESMA partição do Balanço (DL-034/BL-502), com teste que
  prova a partição (`test_bl502`, molde replicado nesta etapa).
- **AS DUAS COLUNAS VETAM** — decisão do arquiteto, 26/09/2026, revendo a
  primeira versão (que só olhava o mês): a DRE formal imprime a coluna do
  ACUMULADO, e uma pendência só nela também deixa um número impresso
  errado. O argumento anterior ("vetar o mês atual por uma pendência de
  um mês já fechado tornaria a DRE inemitível para sempre") não se
  sustenta — a PRIMEIRA classificação de uma conta é livre mesmo com
  movimento (guarda de transição), então corrigir a pendência é sempre
  possível, sem reabrir nada. `avaliar_emissao_da_dre` passou a percorrer
  as DUAS colunas; `residuo_pendente`/`listas_pendentes`/`listas_
  informativas` agora são agrupados por coluna (`"coluna_mes"`/`"coluna_
  acumulado"`, só a que tem algo a reportar aparece), para o cliente
  saber DE ONDE vem cada pendência. Teste novo:
  `test_criterio6b_pendencia_so_no_acumulado_tambem_veta_e_indica_a_coluna`
  (conta usada em janeiro sem classificação, DRE de março: sem pendência
  no mês, mas o acumulado de jan-mar a inclui — 409, pendência só sob
  `"coluna_acumulado"`).
- **Endpoint de leitura** (`DreView`, GET
  `empresas/<empresa_id>/dre/<ano>/<mes>/`, rota `contabilidade:dre`):
  `PodeLerContabilidade`, a MESMA autorização das outras saídas contábeis
  com período (Diário, Razão, Balancete) — nunca `PodeFecharCompetencia`.
  200 quando `pode_emitir`; 409 (com as pendências, agrupadas por coluna)
  quando não; 409 também para `HierarquiaInconsistente` (mesmo padrão do
  Balancete/Razão). Isolamento herdado de `EmpresaEscopadaContabilMixin`
  (404 entre escritórios) — inclusive a recusa automática para empresa em
  modo livro-caixa (`get_empresa()` já chama `recusar_se_livro_caixa` para
  TODA view que usa esta mixin; nenhum código novo precisou disso).
- Conciliação (critério 4) testada e batendo: lucro líquido da DRE do mês
  = valor que a etapa 2 do zeramento (DL-043) do MESMO período transfere,
  nos dois sentidos (lucro → Lucros Acumulados; prejuízo → (-) Prejuízos
  Acumulados, com o sinal certo).

### Testes e mutação

32 testes em `apps/contabilidade/tests/test_dl045_dre.py` (28 da entrega
inicial + 4 do ajuste de 26/09/2026: `test_criterio1h`/`test_criterio1i`/
`test_criterio1j` para a MEP RECEITA-ou-DESPESA, `test_criterio6b` para o
veto pelas duas colunas). Mutação aplicada e revertida nos três pontos
críticos pedidos, mais um ponto novo do ajuste:

| Ponto crítico | Mutação aplicada | Teste que mata |
| --- | --- | --- |
| Filtro de zeramento | Remover `.exclude(...istartswith="zeramento:")` | `test_criterio3_dre_de_mes_zerado_e_igual_a_antes_do_zeramento` |
| Sinal da retificadora | Usar `conta.natureza` (cadastrada) em vez de `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE` (fixo por linha) | `test_sinal_da_linha_usa_a_natureza_natural_da_linha_nunca_a_da_conta` |
| Coluna acumulada | `data_inicio_exercicio = data_inicio_mes` (acumulado vira igual ao mês) | `test_criterio5_acumulado_e_a_soma_dos_meses` |
| Atribuição do resíduo por tipo (MEP) | Atribuir a contribuição de CADA linha a um `TipoConta` FIXO (o antigo "esperado"), em vez do `conta.tipo` REAL da conta topo-classificada | `test_criterio1j_ganho_e_perda_de_mep_no_mesmo_periodo_liquido_correto` |

Um teste novo (`test_sinal_da_linha_usa_a_natureza_natural_da_linha_
nunca_a_da_conta`) foi escrito depois de o mutante "sinal da retificadora"
sobreviver ao primeiro conjunto de testes de referência — todos os cenários
de referência, por coincidência, classificavam a linha numa conta cuja
natureza CADASTRADA já coincidia com a natureza NATURAL da linha, então a
mutação era equivalente para eles. O teste novo classifica "deduções da
receita" numa conta com natureza CADASTRADA atípica (CREDORA, quando o
natural é DEVEDORA) para separar as duas perguntas.

Migração `contabilidade/0010_dl045_conta_classificacao_dre.py` — só
`AddField`, sem dado de migração (toda conta nasce sem classificação); sem
migração nova no ajuste de 26/09/2026 (só lógica de validação/apuração,
nenhum campo de modelo mudou).

## Hipóteses e pendências

- **HI-28:** exercício social = ano civil. Reversível; o estatuto pode fixar
  outra data (Lei 6.404, art. 175).
- **HI-29 (revista depois da PE-70):** resultado financeiro destacado e
  equivalência patrimonial em linha própria, como a NBC TG 26, a NBC TG 1000 e
  os modelos da ITG 1000. A letra do art. 187, III embute o financeiro no
  operacional. **Estrutura substanciada por RC-121, RC-122, RC-123 e RC-125**
  (requisitos.md, 26/09/2026 — dúvidas D1 a D6 da rodada 1 de auditoria,
  decididas pelo arquiteto-senior por delegação do Fred, conferidas nos
  manuais e normas); a validação profissional final continua sendo do Fred,
  como cada RC registra.
- **PE-70 respondida** por fonte primária em 2026-09-26 (ver requisitos.md).
- **RC-124** (operações descontinuadas) e **RC-126** (DRE por período livre,
  para conciliar com zeramento trimestral/anual) ficam fora desta etapa —
  RC-126 sobe de prioridade na fila (ver estado.md).
- Comparativo com o exercício anterior: fora desta etapa.
- Validação profissional da estrutura e dos casos de referência é do Fred.

## Rodada 1 da auditoria

A [rodada 1](../auditorias/2026-09-26-dl-045-rodada-1.md) **reprovou** o
servidor: os casos de referência calculados à mão batem, mas há quatro achados
altos no veto, na hierarquia e no estorno (A1 a A4), a leitura sem snapshot
(A5) e 12 mutantes sobreviventes. Decisões em DE-085. Correção com o
`desenvolvedor-pleno`; depois, uma reconferência única, que inclui a fatia 3.

## Correção da rodada 1

Implementada em cima do commit `31b5f2c` (docs da rodada 1 + DE-085), branch
`dl045-dre`. Achado → mudança → teste → mutante:

| Achado | Mudança | Teste | Mutante(s) morto(s) |
| --- | --- | --- | --- |
| A1 (aninhada) | `contas_com_classificacao_dre_aninhada` virou DUAS listas: `..._linha_diferente` (veta) e `..._mesma_linha` (só avisa); `contas_com_classificacao_dre_desconhecida` passou para a tupla de veto. Partição provada contra o inventário real. | `test_a1_aninhada_com_linha_diferente_da_herdada_veta`, `test_particao_das_listas_contas_da_dre_e_igual_ao_inventario_real` | — |
| A2 (tipo divergente) | Nova lista `contas_com_tipo_divergente_da_linha` (veta): toda conta com movimento próprio cujo `tipo` não é aceito pela linha efetiva (própria ou herdada) — inclui conta patrimonial sob linha de resultado. | `test_a2a_conta_ativo_sob_receita_bruta_veta`, `test_a2b_conta_despesa_sob_receita_bruta_veta` | — |
| A3 (estorno de zeramento) | `_agregar_movimento_dre_por_conta` exclui também `lancamento__estorno_de__chave_idempotencia__istartswith="zeramento:"`; nova lista informativa `estornos_de_zeramento_na_coluna` (nunca veta) declara o estorno na coluna em que ele foi datado. | `test_a3_estorno_de_zeramento_nao_dobra_o_acumulado` | — |
| A4 (`""` trava a conta) | Serializer normaliza `""` -> `None` (`validate_classificacao_dre`); `Conta.clean()` normaliza no topo do método e usa veracidade (`bool(...)`), não `is not None`, na guarda de transição; `CheckConstraint` nova (`ck_conta_classificacao_dre_nao_vazia`) + migração 0011 com `RunPython` normalizando dado legado. | `test_a4_post_com_string_vazia_grava_none_e_libera_a_primeira_classificacao`, `test_a4_check_constraint_recusa_string_vazia_por_sql_direto` | — |
| A5 (sem snapshot) | `apurar_dre` ganhou o MESMO wrapper de `apurar_balanco_patrimonial`: `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` como primeira instrução, quando fora de outro `atomic()`; degrada (pula o comando) quando já dentro de um. | `test_a5_sem_o_wrapper_a_escrita_concorrente_produz_lucro_fantasma`, `test_a5_com_o_wrapper_o_snapshot_protege_do_lucro_fantasma` | — |
| A6 (guarda contornável) | Novo guard: primeira classificação de um nó recusada se a subárvore já tiver conta classificada com movimento (`_subarvore_tem_conta_classificada_dre_com_movimento`); reparentamento recusado se a linha EFETIVA herdada mudar (`_classificacao_dre_ancestral_via`, antes/depois). **DE-086 (reconferência) removeu as DUAS guardas** — eram elas que fechavam a única saída do veto do A2 (R1, achado ALTO); os dois métodos privados citados também saíram. Os testes abaixo MUDARAM DE SENTIDO (agora provam que a operação é LIVRE) e foram renomeados. | `test_a6a_primeira_classificacao_do_pai_sobre_filha_ja_classificada_e_livre` (+ contraprova sem movimento), `test_a6b_reparentamento_que_muda_a_linha_efetiva_com_movimento_e_livre` (+ contraprova sem mudança de linha) | — |
| A7 (sem porta operacional) | Serviço novo `classificar_conta_na_dre(*, conta, classificacao, usuario, request=None)` (guardas em `Conta.clean()`, trilha via `registrar()`); `PATCH /empresas/<id>/contas/<id>/classificacao-dre/` (`ContaClassificacaoDreView`, `PodeEscriturar`); admin ganhou `classificacao_dre` em `list_display`/`list_filter`; mensagem da guarda de transição da DRE fala em "movimento do exercício", não "saldo". **DE-086: o serviço ganhou `select_for_update()` (R4) e a guarda de transição saiu — reclassificar com movimento é livre.** | `test_a7_servico_classifica_conta_existente_e_grava_trilha`, `test_a7_servico_propaga_a_guarda_de_tipo_incompativel`, `test_a7_patch_classifica_conta_existente_via_api`, `test_a7_patch_recusa_para_papel_que_nao_escritura`, `test_a7_patch_reclassifica_conta_com_movimento_e_grava_trilha` (renomeado — MUDOU DE SENTIDO), `test_a7_patch_isolamento_conta_de_outro_escritorio_e_404` | M23-análogo (validação de tipo do serviço) |
| A8 (mutantes) | 13 casos de teste propostos, implementados. | ver tabela de mutantes abaixo | M04, M05, M06, M08, M12, M13, M14, M21, M25, M28, M30 (M27: ver nota) |
| A9 (documentação) | `models.py` (`_LINHAS_ANTES_DO_FINANCEIRO` -> nome real); este plano (contagem "50 contas", partição igual ao Balanço); `docs/agents/estado.md` (pendência revogada removida, rodada 1 e DE-085 citadas). | busca pelos termos corrigidos | — |
| A10 (`total_debitos`/`total_creditos`) | Passaram a somar SÓ contas de tipo RECEITA/DESPESA (própria, sem zeramento) — nunca a contrapartida patrimonial. | `test_caso6_isolamento_dos_totais_entre_empresas` | M27 sobreviveu aqui; morto na reconferência (ver nota) |

### Tabela de mutantes (achado A8)

| # | Mutação | Teste que mata |
| --- | --- | --- |
| M04 | `data_inicio_exercicio = date(ano - 1, 1, 1)` | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M05 | `lancamento__data__lte` -> `__lt` | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M06 | `lancamento__data__gte` -> `__gt` | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M08 | `if residuo or pendentes` -> `if pendentes` | `test_caso2_raiz_despesa_sem_classificacao_com_movimento_veta_pelo_residuo` |
| M12 | `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE[OUTRAS_DESPESAS_OPERACIONAIS]` DEVEDORA -> CREDORA | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M13 | `OUTRAS_RECEITAS` movida para `_LINHAS_DO_RESULTADO_FINANCEIRO` | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M14 | `RESULTADO_EQUIVALENCIA_PATRIMONIAL` removida de qualquer tupla de subtotal | `test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor` |
| M21 | `DEDUCOES_DA_RECEITA` aceita `(RECEITA, DESPESA)` | `test_m21_deducoes_da_receita_recusa_conta_de_tipo_despesa` |
| M25 | Remover `_validar_ano_mes(ano, mes)` de `DreView.get` | `test_caso4_datas_invalidas_devolvem_400` (mutante produz 500, não 400) |
| M27 | Remover `conta__empresa=empresa`/`lancamento__empresa=empresa` de `_agregar_movimento_dre_por_conta` | Sobreviveu à suíte desta correção; **não é equivalente** (ver nota) — morto na reconferência por `test_r7_m27_m27b_isolamento_da_dre_com_item_forjado_de_outra_empresa` |
| M28 | Remover o `try/except HierarquiaInconsistente` de `DreView.get` | `test_caso5_ciclo_na_hierarquia_devolve_409_nunca_500` (mutante produz 500) |
| M30 | `conta.tipo not in (RECEITA, DESPESA)` -> `conta.tipo != RECEITA` | `test_caso3_conta_despesa_sem_classificacao_com_movimento_aparece_na_lista` |

**M21 deixou de ser provisório:** a D3 do relatório da rodada 1 ("deduções da
receita só em conta de receita — decisão provisória") foi confirmada como
**RC-123** (requisitos.md, 26/09/2026), junto com D1/D2/D4/D5/D6 (RC-121,
RC-122, RC-124, RC-125, RC-126) — decididas pelo arquiteto-senior por
delegação do Fred e conferidas nos manuais e normas. Nenhuma exigiu mudança
de código nesta correção: a implementação já seguia RC-121, RC-122, RC-123 e
RC-125; RC-124 (operações descontinuadas) e RC-126 (período livre) ficam
fora desta etapa.

**A alegação de que M27 é equivalente, feita nesta correção, é FALSA — a
reconferência mediu o dano real e a retira.** O argumento acima ("todo
consumidor de `agregados_proprios` lê por `conta.id` a partir de `contas`,
já filtrada por empresa") só vale para dado ÍNTEGRO: pressupõe que todo
`ItemLancamento` tenha `conta.empresa == lancamento.empresa`, um invariante
que `criar_lancamento` garante, **nunca o banco** (sem `CheckConstraint` nem
`trigger`). A sonda da reconferência forjou por ORM um item de crédito de
7,00 numa conta da empresa B, dentro de um lançamento da empresa A: com os
dois filtros no código, a DRE de B dava `receita_bruta 0`/`total_creditos
0` (correto); sem eles (M27 e, sozinho, M27b — só `lancamento__empresa`),
os dois números davam 7,00 — o item forjado vazava para a DRE de uma empresa
que nunca o lançou. O projeto trata dado corrompido como cenário de teste
de isolamento de propósito (é o mesmo padrão do achado 10 da DL-015,
`test_dl015_saidas_com_periodo.py::test_item_de_lancamento_de_outra_empresa_nao_aparece_no_razao_nem_no_balancete`)
— "equivalente" presumia um invariante que o produto não impõe no banco.
Teste novo, na reconferência:
`test_r7_m27_m27b_isolamento_da_dre_com_item_forjado_de_outra_empresa`.

## Correção da reconferência

A [reconferência](../auditorias/2026-09-26-dl-045-reconferencia.md)
**reprovou** com o achado R1 (ALTO — a guarda de reparentamento do A6
fechava a única saída da pendência criada pela correção do A2, deixando a
DRE inemitível até o fim do exercício e o Balanço, DL-034, sem prazo) mais
seis achados médios (R2 a R7) e cinco baixos (R8 a R12). Decisões em
[DE-086](../projeto/decisoes.md#de-086). Correção do **servidor** com o
`desenvolvedor-pleno`, em cima do commit `eb87471` (docs da reconferência +
DE-086), branch `dl045-tela`; a correção da **tela** (R5, R6, R8 a R10, R7
na tela) é do `especialista-frontend`, em paralelo, noutra worktree. Sem
nova rodada de auditoria (AGENTS.md §3.1 não prevê terceira rodada; decisão
do arquiteto, como na DL-043): o fechamento é por verificação independente
dos 14 casos propostos e dos mutantes sobreviventes.

Achado → mudança → teste:

| Achado | Mudança | Teste |
| --- | --- | --- |
| **R1** (ALTA — guarda de reparentamento fecha o veto do A2) | DE-086 item 1: removidas a guarda de TRANSIÇÃO de `classificacao_dre` e as DUAS guardas do A6 em `Conta.clean()` (models.py) — a linha da DRE pode mudar com movimento; o reparentamento volta a obedecer só à regra de NATUREZA (BL-261). Os dois métodos privados que só serviam às guardas removidas (`_subarvore_tem_conta_classificada_dre_com_movimento`, `_classificacao_dre_ancestral_via`) saíram também. | `test_r1_reparentamento_de_conta_ativo_libera_a_dre_e_o_balanco`: reparenta a conta ATIVO `3.1.99` para uma raiz ATIVO; a DRE de março e o Balanço de 31/03 emitem depois. |
| **R2** (classificação desconhecida sem correção possível) | Consequência direta da remoção acima: sem guarda de transição, qualquer valor gravado (inclusive fora de `ClassificacaoDre.values`) pode ser substituído por uma classificação válida, mesmo com movimento. | `test_r2_classificacao_desconhecida_com_movimento_e_corrigida_pela_api`: conta com `classificacao_dre="linha_antiga_renomeada"` (gravada por ORM) e movimento — o PATCH aceita a correção, e a DRE volta a emitir. |
| **R3** (PATCH devolve 500 com corpo malformado) | `ClassificacaoDrePatchSerializer` novo (serializers.py), com `ChoiceField(allow_null=True, allow_blank=True)`; `ContaClassificacaoDreView.patch` (views.py) valida o corpo com ele ANTES de chamar o serviço, em vez de `request.data.get(...)` direto. | `test_r3_patch_com_corpo_malformado_devolve_400_nunca_500` (parametrizado): `{"classificacao_dre": {"a": 1}}`, `{"classificacao_dre": ["receita_bruta"]}` e o corpo `["x"]` devolvem 400, nada gravado. |
| **R4** (corrida na classificação) | `classificar_conta_na_dre` (services.py) faz `Conta.objects.select_for_update().filter(pk=conta.pk).values_list("classificacao_dre", flat=True).get()` DENTRO da transação, ANTES de mudar `conta` — trava a linha e lê o valor REALMENTE gravado (não o que a instância recebida trazia) para a trilha. | `test_r4_corrida_na_classificacao_serializa_e_a_trilha_fica_coerente` (`transaction=True`, barreira em `Conta.full_clean` monkeypatchado): as duas gravações serializam, e o "antes" da segunda é o "depois" da primeira. |
| **R7** (17 mutantes sobreviventes) | Ver a tabela de mutantes abaixo. | `test_r7_m27_m27b_isolamento_da_dre_com_item_forjado_de_outra_empresa`, `test_r7_n05_estornos_de_zeramento_isolados_entre_empresas`, `test_r7_n06_estorno_de_zeramento_de_fevereiro_nao_aparece_em_marco`, `test_r7_n03_classificacao_desconhecida_veta_pela_lista_certa`, `test_r7_n12_t08_patch_isolamento_conta_de_outra_empresa_do_mesmo_escritorio_e_404`, `test_r7_t05_patch_recusa_para_paralegal`, `test_r7_n13_migracao_0011_normaliza_dado_legado_com_string_vazia`, `test_a10_totais_da_dre_conciliam_com_o_balancete_sem_zeramento` (promessa da DE-085 item 9, cumprida agora). |
| **R11** (documentação defasada) | `docs/agents/estado.md` (linhas "sem tela"/"Tela da DRE… não existe" removidas — a tela existe nesta branch); este plano (esta seção); `test_a4_check_constraint_recusa_string_vazia_por_sql_direto` deixou de usar `transaction.savepoint()`/`savepoint_commit()`/`savepoint_rollback()` (depreciados no Django 6.1) — usa `transaction.atomic()` aninhado, que cria e desfaz o mesmo savepoint por baixo dos panos. | Busca pelos termos corrigidos; suíte sem o aviso novo (`RemovedInDjango70Warning`). |

### Mutantes verificados na reconferência (achado R7)

Cada mutante foi aplicado sozinho, o teste-alvo confirmado como reprovado,
e revertido — `git diff` confere vazio depois de cada reversão.

| # | Mutação | Teste que mata |
| --- | --- | --- |
| M27 | Remover `conta__empresa=empresa` **e** `lancamento__empresa=empresa` de `_agregar_movimento_dre_por_conta` | `test_r7_m27_m27b_isolamento_da_dre_com_item_forjado_de_outra_empresa` |
| M27b | Remover só `lancamento__empresa=empresa` (mantém `conta__empresa`) | `test_r7_m27_m27b_isolamento_da_dre_com_item_forjado_de_outra_empresa` |
| N03 | Mover `contas_com_classificacao_dre_desconhecida` para `_LISTAS_DA_DRE_QUE_SO_AVISAM` | `test_r7_n03_classificacao_desconhecida_veta_pela_lista_certa` |
| N05 | Remover `empresa=empresa` de `_estornos_de_zeramento_na_coluna` | `test_r7_n05_estornos_de_zeramento_isolados_entre_empresas` |
| N06 | Remover `data__gte`/`data__lte` de `_estornos_de_zeramento_na_coluna` | `test_r7_n06_estorno_de_zeramento_de_fevereiro_nao_aparece_em_marco` |
| N12/T08 | Remover `empresa=empresa` de `get_object_or_404(Conta, pk=conta_id, empresa=empresa)` em `ContaClassificacaoDreView.patch` | `test_r7_n12_t08_patch_isolamento_conta_de_outra_empresa_do_mesmo_escritorio_e_404` |
| T05 | Trocar `PodeEscriturar` por `PodeLerContabilidade` em `ContaClassificacaoDreView.permission_classes` | `test_r7_t05_patch_recusa_para_paralegal` |
| Guarda de reparentamento religada | Reintroduz a guarda do A6(b) removida pela DE-086 (comparação da linha ancestral antes/depois do reparentamento) | `test_r1_reparentamento_de_conta_ativo_libera_a_dre_e_o_balanco`, `test_a6b_reparentamento_que_muda_a_linha_efetiva_com_movimento_e_livre` |
| N13 | Migração 0011: `RunPython` virando `pass` | `test_r7_n13_migracao_0011_normaliza_dado_legado_com_string_vazia` |

Os mutantes de tela (T01 a T04, N22) e os de apresentação (R5, R6, R8 a R10)
são do `especialista-frontend` — fora do escopo desta seção.

## Verificação do fechamento (sem nova rodada de auditoria)

AGENTS.md §3.1 não prevê terceira rodada. A correção da reconferência
(servidor `ea7610e` + tela `56370ea`, integradas em `fd0ac93`) foi conferida
pelo `auxiliar-verificacao`, de forma independente, em 2026-09-26:

- Os 14 casos de teste propostos pela reconferência existem e passam (o caso
  14, conciliação com o Balancete, é
  `test_a10_totais_da_dre_conciliam_com_o_balancete_sem_zeramento`). Os casos
  1 a 4 mudaram de sentido pela DE-086 e os testes refletem isso.
- R1 reproduzido do zero: conta ATIVO sob receita bruta com movimento veta a
  DRE (409); reparentada para raiz ATIVO, a DRE de março e o Balanço de 31/03
  voltam a emitir.
- Mutantes aplicados em cópia descartável, todos mortos: M27, M27b, N03, N05,
  N06, N12/T08, T05, T06, T01, T02, T03, T04, N22 e a guarda de
  reparentamento do A6(b) religada.
- R3: os três corpos malformados devolvem 400, nada gravado. R5: PDF gerado no
  Chromium sem "Mês anterior"/"Mês seguinte", com o critério de apuração.
- Suíte completa no `fd0ac93`: 2941 passed, 45 skipped, 1 falha de ambiente
  conhecida (`test_versao_minima_python.py`, Python 3.13 local, 3.14 na CI).

**Ressalva registrada:** hoje o único caminho para mover uma conta de grupo
(reparentar) é o admin do Django — não há tela de edição de conta no produto.
O R1 deixa de exigir SQL, mas exige usuário com acesso ao admin. Tela de editar
conta vai para o backlog (BL-541).

