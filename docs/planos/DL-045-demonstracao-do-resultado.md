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
  em relação ao número de contas (testado com 10 → 60 contas).
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
- **Pendências** (critério 6): `contas_sem_classificacao_dre_com_
  movimento` (folha de RECEITA/DESPESA, com movimento na coluna, sem
  classificação própria nem ancestral — a régua é o MOVIMENTO NA COLUNA,
  não uma propriedade fixa da conta, mesma lição do BL-498/DL-033) veta a
  leitura via `avaliar_emissao_da_dre`; `contas_nao_folha_sem_
  classificacao_dre_com_movimento_proprio` (BL-487), `contas_com_
  classificacao_dre_aninhada` e `contas_com_classificacao_dre_
  desconhecida` são informativas (nunca vetam) — mesma partição em duas
  tuplas de `avaliar_emissao_do_balanco` (DL-034/BL-502).
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
  operacional; o Fred confirma a apresentação.
- **PE-70 respondida** por fonte primária em 2026-09-26 (ver requisitos.md).
- Comparativo com o exercício anterior: fora desta etapa.
- Validação profissional da estrutura e dos casos de referência é do Fred.
