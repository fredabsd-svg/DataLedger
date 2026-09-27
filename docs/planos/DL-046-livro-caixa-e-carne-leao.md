# DL-046 — Livro-caixa e carnê-leão do cliente pessoa física

**Demanda:** fila aprovada pelo Fred (RC-113: o escritório faz livro-caixa e
carnê-leão para os clientes pessoa física). Respostas dele em 2026-09-26
(RC-127 a RC-129).
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — cálculo de imposto e livro entregue ao cliente.
Plano completo, testes de sucesso, erro e limite, e auditoria independente.
**Branch:** worktree `dl046-livro-caixa`, integrada por PR depois da DL-044
(PR #50) e da DL-045.

## Problema

O cliente pessoa física já existe no cadastro, em modo livro-caixa (DL-038),
e o produto recusa a contabilidade por partidas dobradas para ele. Mas não há
onde escriturar o livro-caixa nem apurar o carnê-leão.

## Fontes (consultadas em 2026-09-26)

- **Norma — RIR/2018 (Decreto 9.580/2018)**, texto consolidado na Câmara dos
  Deputados (o Planalto não respondeu):
  - **arts. 68 e 69 — livro-caixa:** quem escritura (trabalhador não
    assalariado, titular de serviço notarial e de registro, leiloeiro); o que
    se deduz (remuneração e encargos de empregado, emolumentos pagos a
    terceiros, despesas de custeio necessárias à receita); o que não se deduz
    (depreciação, arrendamento, locomoção — salvo representante comercial
    autônomo); a dedução não excede a receita do mês e o excesso passa aos
    meses seguintes **até dezembro**, sem ir ao ano seguinte; escrituração com
    documentação idônea; o livro **independe de registro**.
  - **arts. 118 a 125 — recolhimento mensal obrigatório (carnê-leão):** quem
    recolhe, base de cálculo (art. 121: rendimentos menos as deduções dos
    arts. 67, 68 e 70 a 72; a do livro-caixa só contra rendimento do trabalho
    não assalariado), tabela mensal (art. 122) e prazo (art. 123).
- **Receita Federal (gov.br):** tabela progressiva mensal de 2026 (Lei
  15.191/2025); redução da Lei 15.270/2025 a partir de 01/2026; pagamento até o
  último dia útil do mês seguinte, DARF código 0190, valor abaixo de R$ 10,00
  acumula para o mês seguinte.
- **Receita Federal — leiaute público de importação do Carnê-Leão Web**
  (arquivo `escrituracao-carne-leao.zip`, instruções de 2025): CSV com `;`,
  datas `DD/MM/AAAA`, valores com vírgula, rendimentos por código
  (`R01.xxx.xxx`) e pagamentos por código (`P10` dedutível, `P11` não
  dedutível, `P20` imposto pago, pensão, previdência).
- **Rotina — manual do sistema de referência (Contabilidade e Folha):**
  carnê-leão habilitado só para inscrição diferente de CNPJ em modo
  livro-caixa; grupo do carnê-leão em cada conta; lançamento de caixa com CPF do
  titular do pagamento e do beneficiário; relatórios Livro Caixa e demonstrativo
  mensal e anual; controle de excesso de deduções do mês anterior e para o mês
  seguinte; CAEPF no cadastro de pessoa física.

## Fatia 1 — Livro-caixa

- Plano de contas do livro-caixa por cliente (receitas e despesas), cada conta
  com o **código do Carnê-Leão Web** que corresponde a ela (rendimento
  `R01...` ou pagamento `P10`/`P11`/`P20`), e a dedutibilidade decorrendo
  desse código.
- Lançamento de caixa (entrada ou saída): data, conta, valor em `Decimal`,
  histórico, documento de origem, CPF do titular do pagamento e do beneficiário
  quando o código exigir, recebido de PF/PJ/exterior. Todos os tipos de receita
  (RC-128): lançamento manual é a porta principal.
- Só para empresa em modo livro-caixa; isolamento, autorização no servidor,
  trilha de auditoria, idempotência, correção por estorno (mesmo padrão da
  contabilidade).
- Cadastro: CAEPF opcional no cliente pessoa física (RC-129).
- Relatório **Livro Caixa** do período, conferível com os lançamentos.

## Fatia 2 — Apuração mensal do carnê-leão

- Tabela progressiva e redução **como dado com vigência**, nunca no código;
  valores de 2026 com a fonte citada.
- Base: rendimentos do mês menos deduções (livro-caixa limitado à receita do
  trabalho não assalariado, previdência oficial, dependentes, pensão), com o
  **excesso de deduções** levado aos meses seguintes até dezembro (art. 69).
- Demonstrativo mensal e anual, com memória de cálculo; valor abaixo de
  R$ 10,00 acumulado.
- ~~Antes de codificar a redução da Lei 15.270/2025 no carnê-leão, confirmar
  na fonte integral que ela se aplica ao recolhimento mensal (PE-71).~~
  **Confirmado em 2026-09-27 (RC-131)** — ver "PE-71 respondida", abaixo.
- Desconto simplificado mensal como alternativa às deduções reais: a
  apuração calcula as duas e aplica a mais benéfica, mostrando as duas
  (HI-33).

## Fatia 3 — Arquivo para o Carnê-Leão Web (RC-127)

- Geração dos CSV no leiaute oficial (rendimentos e pagamentos), com os códigos
  vindos das contas; conferência de que o arquivo gerado bate com o
  livro-caixa do mês.

## Critérios de aceite

1. Lançamento só em cliente em modo livro-caixa; recusa em modo contabilidade.
2. Casos de referência calculados à mão: mês com lucro, com dedução maior que a
   receita (excesso carregado), excesso em dezembro que não passa para janeiro,
   dependentes, faixa isenta, cada faixa da tabela, centavos.
3. Livro Caixa do período concilia com os lançamentos; estorno rastreável.
4. Tabela e redução versionadas por vigência; mudança de tabela não altera
   apuração já feita.
5. CSV gerado no leiaute oficial, validado contra os modelos da Receita.
6. Isolamento entre clientes e escritórios; autorização no servidor.
7. Suíte completa, lint, formatação, `check`, migrações.

## Hipóteses e pendências

- **HI-30:** a dedutibilidade de cada conta decorre do código do Carnê-Leão Web
  associado a ela (`P10` dedutível, `P11` não dedutível), como no plano de
  contas padrão da Receita. O escritório pode associar outro código.
- **PE-71:** confirmar na fonte integral a aplicação da redução da Lei
  15.270/2025 ao carnê-leão, e obter a tabela completa de códigos de
  rendimento, pagamento e ocupação (página de ajuda da Receita bloqueada à
  leitura automática em 2026-09-26).
- **Fora desta etapa:** carnê-leão do **empregador** pessoa física calculado a
  partir da folha (no sistema de referência fica no módulo Folha, que ainda
  não existe aqui); DARF (o Carnê-Leão Web gera a guia); integração automática
  com NFS-e recebida.
- Validação profissional dos casos de referência é do Fred.

## Implementação da fatia 1 (2026-09-26, `desenvolvedor-pleno`)

Servidor + API apenas — a tela vem depois pelo `especialista-frontend`. App
novo `apps/livro_caixa`, isolado de `apps/contabilidade` (regime de caixa, um
valor por lançamento, nunca partida dobrada).

### O que foi feito

1. **Modelos.** `ContaLivroCaixa` (código único por empresa, natureza
   receita/despesa, `codigo_carne_leao`, ativa/inativa) e `LancamentoCaixa`
   (empresa, conta, data, valor `Decimal` com escala máxima 2, histórico,
   documento de origem, `recebido_de` PF/PJ/EX só para receita, CPF do
   titular do pagamento/beneficiário do serviço e CNPJ do pagador opcionais,
   chave de idempotência, `estorno_de` — mesmo padrão de imutabilidade e
   correção por estorno de `LancamentoContabil`).
2. **Recusa por modo de escrituração, espelhada.** `apps.empresas.services.
   recusar_se_nao_livro_caixa`/`EmpresaNaoEmModoLivroCaixa` — o espelho exato
   de `recusar_se_livro_caixa`, no mesmo módulo (ponto único da comparação
   `modo_escrituracao`). Aplicada em `ContaLivroCaixa.clean()`,
   `LancamentoCaixa.clean()`, `criar_conta_livro_caixa`,
   `criar_lancamento_caixa` e `EmpresaEscopadaLivroCaixaMixin.get_empresa()`
   (a mesma defesa em profundidade de três camadas que a contabilidade já
   tem). Nenhuma mudança em `apps.contabilidade` — confirmado que a recusa já
   existente (DL-038) continua intacta.
3. **CAEPF opcional (RC-129/HI-31).** Campo `Empresa.caepf` (14 dígitos), só
   para `tipo_inscricao=CPF`, com `CheckConstraint`
   "empresa_caepf_so_para_cpf_com_formato_valido". Fonte pesquisada
   (SERPRO, Cadastro Compartilhado) confirma a composição de 14 posições (9
   do CPF + 5 do número resumido) mas **não documenta** o algoritmo de
   dígito verificador — validação por FORMATO e por coerência estrutural com
   o CPF do titular, nunca um DV inventado. Registrado como **HI-31** em
   `requisitos.md`.
4. **Coerência natureza × código do Carnê-Leão Web (HI-30).** Formato
   levantado nos modelos de referência da Receita (só o PADRÃO de dígitos e
   separadores, nunca o conteúdo dos arquivos): `R01.xxx.xxx` para receita,
   `P10`/`P11`/`P20` + dígitos para despesa — nunca copiado para o
   repositório.
5. **Serviços** (`apps/livro_caixa/services.py`): `criar_conta_livro_caixa`
   (valida por `full_clean()`, traduz `IntegrityError` da constraint de
   código único), `criar_lancamento_caixa` (validação completa +
   idempotência por impressão digital SHA-256, mesmo desenho de
   `criar_lancamento`), `estornar_lancamento_caixa` (`select_for_update()`,
   recusa estorno de estorno e estorno duplicado, data nunca anterior à do
   original) e `apurar_livro_caixa` (relatório do período).
6. **API REST (DRF)**: `ContaLivroCaixaListCreateView`,
   `LancamentoCaixaListCreateView`, `EstornarLancamentoCaixaView`,
   `LivroCaixaView` (GET do relatório) — política dos cinco dicionários
   (BL-196) em toda rota de escrita; papéis autorizados espelhando a matriz
   da contabilidade (ADMINISTRADOR/GESTOR/ANALISTA/FINANCEIRO escrevem;
   + PARALEGAL lê).
7. **Admin.** `ContaLivroCaixaAdmin` com inclusão/alteração (a regra mora no
   modelo, `full_clean()` do `ModelForm` já aplica); `LancamentoCaixaAdmin`
   só leitura (mesma decisão de `LancamentoContabilAdmin` — a escrituração é
   sempre pelo serviço, nunca pelo admin).

### Achados corrigidos durante a implementação (autorrevisão, antes de pedir auditoria)

| # | Achado | Correção |
| --- | --- | --- |
| 1 | `casas_decimais()` normaliza zeros à direita, mas `DecimalField.full_clean()` olha o expoente CRU de `Decimal` — um valor como `"100.000"` passava na checagem de escala do serviço e ainda assim era recusado por `full_clean()`, com mensagem contraditória. | `criar_lancamento_caixa` agora faz `valor.quantize(Decimal("0.01"))` depois de confirmar (via `casas_decimais()`) que a redução não perde informação. |
| 2 | `cpf_titular_pagamento`/`cpf_beneficiario_servico`/`cnpj_pagador` não tinham `validators=[validar_cpf]`/`validar_cnpj` no campo do modelo — `full_clean()` não recusava formato inválido. | Validadores adicionados aos três campos (mesmo padrão de `Empresa.cpf`). |
| 3 | A instrução da tarefa citava "CPF titular e beneficiário" para trabalho não assalariado; a leitura dos modelos de referência mostrou que ambos os campos aparecem juntos só para este código — implementado exigindo os DOIS quando o código é `R01.001.001` e `recebido_de=PF` (ver "Regras reportadas, não decididas" abaixo). | — |

### Testes

- `apps/livro_caixa/tests/test_dl046_livro_caixa.py` (46 testes): modelo
  (sucesso/erro/limite de `ContaLivroCaixa`/`LancamentoCaixa`), recusa por
  modo nos dois sentidos (unitária e via API, espelhando
  `test_dl038_recusa_livro_caixa.py`), isolamento entre empresas do MESMO
  escritório (exercita `get_queryset()`, não só `get_empresa()`),
  idempotência (mesma chave/mesmo conteúdo, mesma chave/conteúdo diferente,
  chave por empresa), estorno (imutabilidade, unicidade — inclusive
  contornando o serviço direto no ORM —, ordem de data, visibilidade no
  relatório), conciliação do relatório, papéis (escritura × leitura), e
  contrato da API (campo desconhecido, valor como número JSON).
- `apps/empresas/tests/test_dl046_caepf.py` (15 testes): validador puro,
  `Empresa.clean()`, `CheckConstraint` (bypassando `full_clean()`, mesmo
  padrão de `test_dl076_b8_modo_escrituracao_constraint.py`), e API.
- Ajustes em três testes mecânicos pré-existentes para reconhecer o app
  novo: `test_dl024_atalhos_e_acessibilidade.py` (as quatro rotas da API
  entram em `EXCLUSOES_NOMEADAS_DE_TELA` — só servidor + API nesta fatia),
  `test_dl023_varredura_admin.py` (decisão "defendida" para os dois
  `ModelAdmin` novos) e `test_dl024_trilha_admin.py` (os dois modelos
  entram na cobertura esperada da trilha).
- **Mutantes aplicados (vivo, revertido depois de confirmar vermelho):**
  1. `recusar_se_nao_livro_caixa`: condição trocada por `False` — 3 testes
     (unitário, modelo e varredura da API) ficaram vermelhos.
  2. Isolamento: `ContaLivroCaixaListCreateView.get_queryset()` trocado por
     `.objects.all()` — o teste de isolamento entre empresas do mesmo
     escritório ficou vermelho.
  3. Coerência de código: condição de `mensagem_de_codigo_carne_leao_
     invalido` para receita trocada por `False` — o teste de código de
     pagamento numa conta de receita ficou vermelho.
  4. Estorno: primeira tentativa mutou a guarda `estornos.exists()` em
     `estornar_lancamento_caixa` — **sobreviveu**, porque `full_clean()`
     (chamado dentro de `criar_lancamento_caixa`) já verifica a
     `UniqueConstraint` "lancamento_caixa_estorno_de_unico" antes de
     gravar, e essa segunda camada também traduz para `LancamentoCaixaInvalido`
     — achado ok (defesa em profundidade funcionando), mas não isolava a
     guarda testada. Mutação refeita no ponto sem redundância —
     `LancamentoCaixa.save()`, a condição de imutabilidade — e aí sim o
     teste de imutabilidade ficou vermelho.

### Verificação

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 296 arquivos já formatados.
- `python manage.py check` — nenhum problema.
- `python manage.py makemigrations --check --dry-run` — nenhuma alteração
  pendente.
- `pytest` (suíte completa): **2899 passed, 1 failed (pré-existente, fora do
  escopo desta etapa — `test_versao_minima_python.py` falha também na `main`,
  ambiente Python 3.13 em vez do 3.14 esperado pela CI), 45 skipped**.
- Migrações aplicadas com sucesso em PostgreSQL vazio (`dataledger_dl046`) e
  em SQLite vazio (arquivo novo).

### Regras reportadas, não decididas (para o `arquiteto-senior`/Fred)

- **CPF titular/beneficiário do trabalho não assalariado**: a instrução da
  tarefa dizia "quando o código de rendimento de trabalho não assalariado
  exigir" — implementei exigindo os DOIS campos (titular do pagamento e
  beneficiário do serviço) só para o código `R01.001.001` com
  `recebido_de=PF`, por ser o único código, nos modelos de referência lidos,
  que mostra os dois campos preenchidos juntos. Aluguel e outros
  rendimentos não exigem nenhum dos dois; serviços notariais mostram só um.
  Isto é leitura minha dos modelos de referência, não uma regra confirmada
  pelo Fred.
- **Faixa de data do lançamento de caixa** (`DATA_MINIMA_LANCAMENTO_CAIXA`):
  reaproveitada POR ANALOGIA de `apps.contabilidade.validators` (RC-77,
  2000-01-01 até hoje + 30 dias) — o Fred confirmou essa faixa para o
  lançamento CONTÁBIL, não especificamente para o livro-caixa.
- **Convenção de sinal do estorno na apuração** (`apurar_livro_caixa`): um
  estorno aparece como linha própria (nunca oculto), mas contribui aos
  totais com o sinal INVERTIDO do original, do MESMO lado (entradas ou
  saídas) — nunca como um lançamento do lado oposto. É desenho meu desta
  etapa, sem instrução explícita da tarefa sobre a convenção de sinal.
- **HI-31 (CAEPF sem DV confirmado)**: ver `requisitos.md`.

### Contrato da API (para o `especialista-frontend`)

Prefixo `livro-caixa/` (`config/urls.py`), paralelo a `contabilidade/`.

- `GET/POST livro-caixa/empresas/<empresa_id>/contas/`
  - `POST` — corpo: `{"codigo", "nome", "natureza": "receita"|"despesa",
    "codigo_carne_leao", "ativa"}` (campos desconhecidos são recusados,
    BL-196). `201` com a conta criada.
  - `GET` — lista as contas da empresa.
- `GET/POST livro-caixa/empresas/<empresa_id>/lancamentos/`
  - `POST` — corpo: `{"conta", "data": "AAAA-MM-DD", "valor": "100.00"
    (sempre TEXTO), "historico", "documento_origem", "recebido_de":
    "PF"|"PJ"|"EX", "cpf_titular_pagamento", "cpf_beneficiario_servico",
    "cnpj_pagador"}`; cabeçalho opcional `Idempotency-Key`. `201` (criado) ou
    `200` (repetição idempotente) com o lançamento; `409` em conflito de
    idempotência.
  - `GET` — lista os lançamentos da empresa.
- `POST livro-caixa/empresas/<empresa_id>/lancamentos/<lancamento_id>/estornar/`
  — sem corpo (a data é decidida pelo servidor). `201` com o lançamento de
  estorno.
- `GET livro-caixa/empresas/<empresa_id>/livro-caixa/?inicio=AAAA-MM-DD&fim=AAAA-MM-DD`
  — relatório do período:

  — **contrato revisado na rodada 1** (D3/DE-087 item 13: `P20` sai num
  grupo próprio, separado das despesas de custeio):

  ```json
  {
    "empresa": 1,
    "data_inicio": "2026-01-01",
    "data_fim": "2026-01-31",
    "itens": [
      {
        "lancamento_id": 10,
        "data": "2026-01-15",
        "conta": "R1",
        "conta_nome": "Honorários recebidos",
        "natureza": "receita",
        "grupo": "entrada",
        "valor": "1500.00",
        "historico": "Honorários de janeiro",
        "documento_origem": "",
        "estorno_de_id": null,
        "e_estorno": false
      }
    ],
    "total_entradas": "1500.00",
    "total_saidas_custeio": "0.00",
    "total_saidas_deducao_carne_leao": "0.00",
    "total_saidas": "0.00",
    "saldo": "1500.00"
  }
  ```

  `grupo` é um de `"entrada"`, `"saida_custeio"` ou
  `"saida_deducao_carne_leao"`. `total_saidas` continua a soma dos dois
  grupos de saída (mantido por compatibilidade); o saldo de caixa não muda.

- Todas as rotas recusam (400, corpo `{"empresa": ["..."]}`) para empresa em
  modo contabilidade. `403` para papel sem autorização; `404` para empresa de
  outro escritório. A lista de lançamentos é **paginada** (B6, rodada 1):
  `{"count", "next", "previous", "results": [...]}`.

## Correção da rodada 1 (2026-09-27, `desenvolvedor-pleno`)

Correção do SERVIDOR dos três achados altos e dos médios/baixos aplicáveis
da [rodada 1 de auditoria](../auditorias/2026-09-26-dl-046-rodada-1.md),
seguindo as decisões de [DE-087](../projeto/decisoes.md#de-087).
A tela (A1 continua exigindo trabalho de tela no menu/lista — DE-087 item 3;
M1, M6 texto de impressão, M8, M24) foi corrigida em paralelo pelo
`especialista-frontend`, noutra worktree.

### Achado → mudança → teste

| Achado | Mudança | Teste |
| --- | --- | --- |
| A1 | `apps.empresas.services.recusar_transicao_para_contabilidade_com_movimento_de_caixa`/`TransicaoParaContabilidadeInvalida` — espelho exato de `recusar_transicao_para_livro_caixa_com_movimento` (R6), chamada nos dois pontos que a R6 já usa (`Empresa.clean()`, `EmpresaSerializer.validate`). | `test_recusar_transicao_para_contabilidade_com_*`, `test_empresa_full_clean_recusa_troca_...`, `test_api_patch_recusa_troca_de_modo_com_lancamento_gravado` + contraprova sem movimento. |
| A2 | `criar_lancamento_caixa`: `save()` num savepoint próprio; `IntegrityError` da chave de idempotência reconsulta e devolve o existente (200) ou o conflito (409); `full_clean(exclude={"chave_idempotencia"})` fecha a janela em que `validate_constraints()` via a linha da corrida antes do `INSERT`. | `test_a2_corrida_de_idempotencia_mesmo_conteudo_dois_201_ou_200_nunca_500` e a contraprova com conteúdo diferente (`{201,409}`) — threads reais + barreira dentro de `full_clean()`. |
| M2 | `ProhibitNullCharactersValidator` em `codigo`, `nome`, `historico`, `documento_origem`, `chave_idempotencia`. | `test_api_conta_recusa_nul_em_texto_livre`, `test_api_lancamento_recusa_nul_em_documento_origem`. |
| M3 | `ContaLivroCaixa.clean()` recusa troca de `empresa` com lançamento gravado; admin com `empresa` somente leitura na edição. | `test_conta_com_lancamento_nao_muda_de_empresa`, `test_admin_nao_oferece_empresa_editavel_para_conta_existente`. |
| M4 | `ContaLivroCaixa.clean()` recusa troca de `codigo_carne_leao` com lançamento gravado; `criar_lancamento_caixa(_pular_validacao_dependente_da_conta=True)` faz o estorno copiar o original sem revalidar CPF/CNPJ contra a conta atual. | `test_conta_com_lancamento_nao_muda_o_codigo_carne_leao`, `test_estorno_de_lancamento_antigo_continua_possivel_apos_alteracao_permitida_da_conta`. |
| M5 | Regra de CPF do leiaute oficial, universal para toda RECEITA (não mais restrita a `R01.001.001`): PF exige titular; beneficiário pode faltar com o novo campo `cpf_beneficiario_nao_informado`; CPF só em PF, CNPJ só em PJ. | `test_m17_*`, `test_m18_*`, `test_pf_com_cnpj_pagador_e_recusado`. |
| B1 | `criar_lancamento_caixa` recusa lançamento NOVO em conta inativa (`estorno_de is None`); estorno de lançamento antigo não é afetado. | `test_b1_conta_inativa_recusa_lancamento_novo`, `test_b1_conta_inativa_permite_estorno_de_lancamento_antigo`. |
| B2 | `_normalizado_ou_vazio` normaliza CPF/CNPJ (com ou sem máscara) ANTES da impressão digital e de `full_clean()`. | `test_b2_cpf_com_mascara_e_normalizado`, `test_b2_cnpj_com_mascara_e_normalizado`, `test_b2_api_aceita_cpf_com_mascara`. |
| B3 | `ContaLivroCaixaListCreateView.post` valida `codigo`/`nome` como texto, com `strip`, antes do serviço. | `test_b3_api_recusa_codigo_nao_textual`, `test_b3_api_recusa_codigo_so_de_espacos`, `test_b3_api_grava_codigo_e_nome_sem_espaco_nas_bordas`. |
| B5 | Ação de trilha `lancamento_caixa.estornado` (era `lancamento_caixa.criado` para os dois); `lancamento_caixa.criacao_repetida` na repetição idempotente (sequencial e sob corrida). | `test_b5_trilha_do_estorno_usa_acao_propria`, `test_b5_trilha_da_repeticao_idempotente_e_registrada`. |
| B6 | `PaginacaoLancamentoCaixa` (`PageNumberPagination`, `page_size=100`) em `LancamentoCaixaListCreateView`. | `test_b6_api_lancamentos_e_paginada`. |
| D3 | `apurar_livro_caixa` separa `P20` (`codigo_carne_leao_e_deducao_do_carne_leao`) das despesas de custeio: `total_saidas_custeio`/`total_saidas_deducao_carne_leao` por total, `grupo` por item; `total_saidas`/`saldo` inalterados. | `test_d3_relatorio_separa_p20_das_despesas_de_custeio`, `test_d3_api_relatorio_expoe_os_dois_grupos_de_saida`. |
| Achado do frontend | `_CAMPO_DA_RESTRICAO_DE_EMPRESA["empresa_caepf_so_para_cpf_com_formato_valido"] = "caepf"`. | `test_achado_frontend_campo_da_restricao_de_caepf_e_caepf_nao_cnpj`. |

### Mutantes mortos (M7)

`M04`, `M06`, `M07`, `M16`, `M17`, `M18`, `M19`, `M27`, `M28` e `M32` —
aplicados VIVOS (um por vez, no código de produção), confirmados vermelhos,
e revertidos antes do próximo:

| # | Ponto mutado | Teste que matou |
| --- | --- | --- |
| M04 | `LancamentoCaixaListCreateView.get_queryset()` sem filtro de empresa | `test_m04_api_lista_lancamentos_de_a_nao_contem_nada_de_a2` |
| M06 | `apurar_livro_caixa` sem filtro de empresa | `test_m06_apurar_livro_caixa_de_a_nao_contem_nada_de_a2` |
| M07 | `EstornarLancamentoCaixaView` busca o lançamento sem filtrar por empresa | `test_m07_api_estorno_de_a_com_id_de_lancamento_de_a2_da_404` |
| M16 | Formato de rendimento reduzido a `^R01\..*$` | `test_m16_codigo_de_rendimento_mal_formado_e_recusado` (3 casos) |
| M17 | Exigência do CPF do beneficiário (ou indicador) removida | `test_m17_pf_com_titular_mas_sem_beneficiario_e_sem_indicador_e_recusado` (achado: a primeira tentativa de mutação sobreviveu aos 3 testes M17 originais — nenhum isolava exatamente esta condição; teste novo adicionado) |
| M18 | Exigência de CPF do titular estendida a PJ/EX | `test_m18_pj_sem_cpf_e_aceito` |
| M19 | Coerência do CAEPF × CPF comparando só 8 dígitos | `test_m19_caepf_que_difere_do_cpf_so_no_nono_digito_e_recusado` (teste novo — os dois já existentes não isolavam o 9º dígito) |
| M27 | API aceita `valor` como `int` JSON | `test_m27_api_recusa_valor_como_numero_json_inteiro` |
| M28 | Guarda de NATUREZA de conta com lançamento removida | `test_m28_conta_de_receita_com_lancamento_nao_muda_para_despesa_mesmo_com_codigo_coerente` (troca natureza E código, os dois coerentes entre si, para a guarda de TRANSIÇÃO ser o que recusa — não a coerência) |
| M32 | Estorno somado no lado das ENTRADAS, independente da natureza | `test_m32_estorno_de_despesa_reduz_saidas_sem_alterar_entradas` |

`M03` (recusa por modo no serviço de lançamento) continua equivalente —
`LancamentoCaixa.clean()` já recusa pela mesma via, como a rodada 1 já tinha
apontado.

### Achado colateral corrigido: migração de `livro_caixa` fragilizava testes de reversão de `empresas`

`makemigrations` gerou `livro_caixa.0001_inicial` dependente de
`empresas.0014_dl046_caepf` (a migração MAIS RECENTE de `empresas` no
momento da geração) — mas este app só precisa que o MODELO `Empresa`
exista (para o `ForeignKey`), não de nenhum campo específico dela.
Rodar a suíte COMPLETA (não só os testes de `livro_caixa`) expôs o efeito:
`test_dl076_b8_modo_escrituracao_constraint.py`,
`test_dl038_migracao.py` e outros que revertem `empresas` para uma
migração anterior a `0014` — dentro da MESMA sessão de banco
(`django_db(transaction=True)`) — forçam o Django a desaplicar
`livro_caixa.0001` primeiro (porque ele dependia de `0014`), e só
reaplicam os líderes de `empresas`, nunca o de `livro_caixa`: as tabelas
de `livro_caixa` ficavam apagadas para o RESTO da suíte, e o próximo
teste deste app (`test_a2_corrida_de_idempotencia_...`) quebrava com
`UndefinedTable`, só na execução da suíte completa — nunca isolado.
Corrigido editando a dependência à mão para `empresas.0001_initial` (onde
`Empresa` nasce), a migração menos recente que ainda satisfaz o que este
app de fato usa. `makemigrations --check` continua limpo depois da edição.

### Contrato revisado do relatório (para o frontend)

Ver a seção "Contrato da API" acima, já atualizada com `grupo`,
`total_saidas_custeio`, `total_saidas_deducao_carne_leao` e a paginação de
`GET .../lancamentos/`. Novo campo em `LancamentoCaixa`:
`cpf_beneficiario_nao_informado` (booleano, aceito no `POST` e devolvido no
corpo).

### Verificação

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 299 arquivos já formatados.
- `python manage.py check` — nenhum problema.
- `python manage.py makemigrations --check --dry-run` — nenhuma alteração
  pendente.
- `pytest` (suíte completa): **2981 passed, 1 failed (pré-existente, fora do
  escopo — `test_versao_minima_python.py`, ambiente Python 3.13 em vez do
  3.14 esperado pela CI), 45 skipped**.
- Migração `livro_caixa.0002_rodada1` aplicada com sucesso em PostgreSQL
  vazio e em SQLite vazio, com reversão e reaplicação das duas migrações do
  app confirmadas nos dois bancos.

### Não testado / bloqueado nesta correção

- `pwsh ./scripts/validate-docs.ps1` — `pwsh` não existe neste ambiente
  (mesmo bloqueio já registrado pela auditoria).
- Tela/navegação (A3), impressão (M6, M8), acessibilidade — do
  `especialista-frontend`, noutra worktree.
- D1 (data/sinal do estorno para a apuração mensal) virou **PE-72**
  (requisitos.md) — decisão de produto antes da fatia 2, não desta rodada.
- Dígito verificador do CAEPF (HI-31) — sem fonte oficial.

## Correção da reconferência (2026-09-27, `desenvolvedor-pleno`)

A [reconferência](../auditorias/2026-09-27-dl-046-reconferencia.md) fechou
A1, A2 e A3, mas reprovou por N1 (tela — do `especialista-frontend`, noutra
worktree, `wt-dl046f`) e pela regra de CPF que a DE-087 item 6 generalizava
para toda receita. Correção final do SERVIDOR, sem nova rodada de auditoria
(DE-088 item 7 — fechamento por verificação independente).

### Achado → mudança → teste

| Achado | Mudança | Teste |
| --- | --- | --- |
| M5/DE-088 item 1 | Regra de CPF/CNPJ **por MODELO** de rendimento (`apps.livro_caixa.validators.modelo_do_codigo_de_rendimento`/`erros_de_cpf_cnpj_do_rendimento`), substituindo a regra universal da DE-087 item 6: trabalho não assalariado (titular + beneficiário XOR indicador, PJ exige CNPJ); notarial (titular obrigatório, beneficiário/indicador sempre vazios, PJ exige CNPJ); aluguel/outros (nunca CPF nem CNPJ); código fora dos quatro modelos conhecidos (sem exigência, PE-71) — coerência universal (CPF só PF, CNPJ só PJ, indicador só onde o modelo prevê) continua valendo em qualquer caso. | `test_m5_linha_a_linha_dos_modelos_oficiais` (as 12 linhas), mais 6 testes de coerência por modelo (notarial, aluguel, código desconhecido). |
| N2 | `criar_lancamento_caixa` separa `full_clean(validate_constraints=False)` (valida TODOS os campos, inclusive tamanho/NUL de `chave_idempotencia`) de `validate_constraints(exclude=...)` (só esta chamada dispensa a `UniqueConstraint` da idempotência). | `test_n2_servico_recusa_chave_de_256_caracteres`, `..._de_300_caracteres`, `..._aceita_chave_no_limite_de_255`, `..._corrida_com_chave_valida_continua_201_200`. |
| N6 | `select_for_update()` na `Empresa` nos dois caminhos de gravação: `EmpresaDetailView.update()` (troca de modo) e `criar_conta_livro_caixa` (criação de conta) — trava a MESMA linha, com a instância travada e FRESCA usada na checagem de modo (achado do próprio desenvolvedor: travar a linha no banco não bastava enquanto a checagem ainda lia o objeto `empresa` em cache, com o valor ANTIGO). | `test_n6_corrida_entre_troca_de_modo_e_criacao_de_conta_sempre_recusa_um_dos_dois` — threads reais + barreira; sem a correção, media `{'patch': 200, 'post': 201}` (os dois aceitos). |
| N7 | `_impressao_digital_caixa` passa a incluir `cpf_beneficiario_nao_informado`. | `test_n07_barreira_entre_pre_checagem_e_full_clean_da_200_nunca_400` (também cobre a corrida do próprio N7 indiretamente — ver a seção de mutantes). |
| N13 | Já copiado desde a rodada 1 (`estornar_lancamento_caixa` passa `cpf_beneficiario_nao_informado=lancamento.cpf_beneficiario_nao_informado`) — faltava o TESTE. | `test_n13_estorno_copia_o_indicador_de_beneficiario_nao_informado`. |
| N16 | Já coberto pela coerência universal (`recebido_de != "PF"` recusa o indicador) — faltava o TESTE isolando PJ/EX. | `test_n16_indicador_marcado_fora_de_pf_e_recusado` (parametrizado). |
| N21 | Já coberto (`codigo_carne_leao_e_deducao_do_carne_leao` só reconhece `P20`) — faltava o TESTE isolando P11. | `test_n21_conta_p11_permanece_em_saida_custeio`. |
| N12 (opcional) | Sem mudança de código (o estorno já não revalida, M4/rodada 1) — teste com dado gravado por ORM sob a regra antiga. | `test_n12_lancamento_legado_gravado_por_orm_continua_estornavel`. |
| Fora do meu escopo | N1, N3, N4, N5, N8, N9, N25, N26, N33, N38 — telas, impressão e navegação, do `especialista-frontend` (`wt-dl046f`). | — |

### Mutantes mortos (aplicados vivos, confirmados vermelhos, revertidos)

| # | Ponto mutado | Teste que matou |
| --- | --- | --- |
| N07 | `validate_constraints(exclude=...)` volta a `validate_constraints()` sem exclusão | `test_n07_barreira_entre_pre_checagem_e_full_clean_da_200_nunca_400` |
| N12 | `_pular_validacao_dependente_da_conta=True` volta a `False` no estorno | `test_n12_lancamento_legado_gravado_por_orm_continua_estornavel` |
| N13 | Estorno passa `cpf_beneficiario_nao_informado=False` (fixo) em vez de copiar | `test_n13_estorno_copia_o_indicador_de_beneficiario_nao_informado` |
| N16 | Recusa do indicador fora de PF (coerência universal) neutralizada | `test_n16_indicador_marcado_fora_de_pf_e_recusado[EX]` |
| N21 | `codigo_carne_leao_e_deducao_do_carne_leao` passa a reconhecer também `P11` | `test_n21_conta_p11_permanece_em_saida_custeio` |
| Regra por modelo (notarial exigindo beneficiário) | Notarial passa a EXIGIR `cpf_beneficiario_servico` em vez de proibir | `test_m5_linha_a_linha_dos_modelos_oficiais[R01.001.002 PF...]` e `test_m5_notarial_pf_com_beneficiario_e_recusado` |

`N07` também foi confirmado como um teste DETERMINÍSTICO (sem threads):
dentro do `mock.patch.object(LancamentoCaixa, "full_clean", ...)`, a
primeira chamada dispara uma chamada RECURSIVA a `criar_lancamento_caixa`
com o MESMO conteúdo — simulando a "outra requisição" comprometendo a linha
bem no meio da janela entre a pré-checagem e o `full_clean()`/
`validate_constraints()` da chamada externa.

### Achado colateral que corrigi ao escrever o teste de N6

`criar_conta_livro_caixa` travava a LINHA da empresa no banco
(`select_for_update()`), mas continuava validando o modo de escrituração
contra o objeto `empresa` recebido como PARÂMETRO — que o Django mantém em
CACHE com o valor lido pela VIEW, ANTES do lock. Travar a linha no banco não
adianta se a checagem em Python nunca relê o valor fresco: a primeira versão
deste teste mediu os dois lados da corrida aceitos (`{'patch': 200, 'post':
201}`). Corrigido usando a instância FRESCA, lida DEPOIS do
`select_for_update()`, para construir a `ContaLivroCaixa` que será validada.

### Verificação

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 299 arquivos já formatados.
- `python manage.py check` — nenhum problema.
- `python manage.py makemigrations --check --dry-run` — nenhuma alteração
  pendente (nenhum campo novo nesta correção).
- `pytest` (suíte completa): **3037 passed, 1 failed (pré-existente, fora do
  escopo — `test_versao_minima_python.py`, ambiente Python 3.13 em vez do
  3.14 esperado pela CI), 45 skipped**. Os testes com threads reais (A2, N6,
  N07) confirmados estáveis em execuções repetidas.
- Migrações: nenhuma nova nesta correção. Reversão parcial de `empresas`
  (até `0007`) confirmada, em PostgreSQL e SQLite vazios, sem tocar em
  `livro_caixa` — mesma prova da rodada 1, repetida contra o HEAD atual.

### Não testado / bloqueado nesta correção

- Tela/navegação (N1), impressão (N3, N4, N5), acessibilidade — do
  `especialista-frontend`.
- N8 (teste instável "RB"), N9 (comentários obsoletos), N25/N26 (trilha de
  navegação), N33/N38 (número de consultas da tela) — todos em arquivos do
  frontend, fora do meu escopo.
- `pwsh ./scripts/validate-docs.ps1` — `pwsh` não existe neste ambiente.
- RC-130 (D1/PE-72) é da fatia 2, lida para contexto, sem mudança nesta
  correção (fatia 1).

## Verificação do fechamento (sem nova rodada de auditoria)

AGENTS.md §3.1 não prevê terceira rodada. A correção da reconferência
(servidor `4afa24f` + telas `7035ace`, integradas em `dcda0db`) foi conferida
pelo `auxiliar-verificacao`, de forma independente, em 2026-09-27. O
resultado está abaixo sem omissão.

**Confirmado:**

- 13 dos 15 casos propostos pela reconferência têm teste dedicado e passam.
- Reprodução direta pela tela, pelo serviço e pela API:
  - N1: o indicador de beneficiário não informado grava pela tela (302);
  - M5: as 12 linhas dos modelos oficiais aceitam conforme a DE-088, e as
    contraprovas (notarial com beneficiário, notarial PJ sem CNPJ, aluguel
    com CPF) recusam;
  - N2: chave de 300 caracteres pela tela devolve 400, nada gravado.
- 12 mutantes aplicados em cópia descartável, todos mortos: N07, N12, N13,
  N16, N21, N25, N26, N33, N38, "tabela P20 sem identificação", "notarial
  exigindo beneficiário" e "aluguel exigindo CPF".
- N6: a corrida entre troca de modo e criação de conta passou três vezes
  seguidas, com exatamente uma das duas operações aceita.
- Suíte completa no `dcda0db`: 3046 passed, 45 skipped, 1 falha de ambiente
  conhecida (`test_versao_minima_python.py`, Python 3.13 local, 3.14 na CI).

**Achados da verificação:**

1. **O instrumento de medição do N3 estava quebrado.** O `7035ace` passou a
   importar `CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO` de
   `apps.livro_caixa.validators`; o `4afa24f` removeu essa constante ao
   trocar a regra de CPF por modelo. O script recusava com `ImportError`
   antes de abrir o navegador, e os 31 testes ponta a ponta do instrumento
   falhavam — mas só com `DL_PYTHON_DO_SISTEMA` definido, que a suíte local
   não define e a CI do job de identificação define. O N3 não estava
   verificado desde o `4afa24f`.
2. **N7 sem teste automatizado.** O comportamento estava correto (409, um
   registro só), mas nenhum teste cobria a repetição da chave mudando só o
   indicador.
3. **N2 pela tela sem teste automatizado.** Só o serviço tinha teste; o
   comportamento da tela estava correto.

**Correção de integração (arquiteto-senior, 2026-09-27):**

- A constante voltou a `validators.py` com nome público, e o dicionário de
  modelos passou a usá-la. Ao consertar o import, apareceram mais dois
  defeitos que ele escondia:
  - o cenário sintético do instrumento lançava rendimento PJ sem CNPJ do
    pagador, que a DE-088 recusa. Ganhou um CNPJ sintético;
  - a montagem do cenário não era atômica. Uma falha no meio deixava a
    empresa gravada sem lançamentos; a execução seguinte a reaproveitava e
    media um relatório de **uma folha só** — "PASSOU" sem medir o N3.
    Agora é `transaction.atomic()`.
- O arnês dos testes ponta a ponta substitui a varredura de telas por uma
  tela fabricada e estreitava só o piso original. O piso novo do Livro Caixa
  reprovava todo controle limpo (6 testes). O arnês estreita os dois pisos,
  e o teste novo `test_ponta_a_ponta_piso_do_livro_caixa_ausente_reprova`
  prova que o piso do Livro Caixa continua reprovando quando a tela some.
- Testes novos: `test_n7_mesma_chave_mudando_so_o_indicador_de_beneficiario_e_conflito`
  e `test_n2_tela_recusa_chave_longa_com_400_e_nada_gravado` (256 e 300).
  Com o indicador tirado da impressão digital (mutante), o teste do N7
  falha; a primeira versão dele mudava também o CPF do beneficiário e
  deixava o mutante vivo — foi corrigida para mudar só o indicador.

**Evidência depois da correção** (PostgreSQL 16, Chromium local):

- `scripts/medir_identificacao_do_emitente.py` em banco limpo: código de
  saída 0; relatório do Livro Caixa com 7 folhas e
  `folhas_sem_bloco_de_identificacao: []`. O PDF, conferido folha a folha,
  tem a folha 7 só com pagamentos P20, e ela traz a identificação do
  emitente — o cenário que o N3 exige.
- `scripts/test_medir_identificacao_do_emitente.py` com
  `DL_PYTHON_DO_SISTEMA` definido, como na CI: 136 passed. Na `main`, os 31
  ponta a ponta passavam, então a falha era da DL-046 e não do ambiente.

**Não testado:** a CI deste conjunto ainda vai rodar no PR.

## PE-71 respondida (2026-09-27)

Pesquisa do `auxiliar-pesquisa` em fonte oficial, lida em texto integral e
conferida pelo `arquiteto-senior` nos pontos decisivos. Registro em RC-131
e HI-32 a HI-34.

- **A redução mensal da Lei 15.270/2025 se aplica ao carnê-leão.** A lei
  insere o art. 3º-A na Lei 9.250/1995, ao lado da tabela mensal que o art.
  3º manda aplicar ao art. 8º da Lei 7.713/1988 (o carnê-leão). A Receita
  diz isso expressamente no Perguntas e Respostas IRPF 2026 (v1.00, de
  23/04/2026), nas perguntas 266 e 267, as do carnê-leão: *"A partir de 1º
  de janeiro de 2026, será concedido redução mensal do imposto aos
  contribuintes com rendimento tributável de até R$ 7.350,00"*.
- **Códigos do Carnê-Leão Web:** a página de tópicos de ajuda continua
  recusando leitura automática (403), mas as páginas do Manual do
  Carnê-Leão (rendimentos, pagamentos, pagamentos do plano de contas e
  ocupações) responderam e trazem as tabelas. O código de previdência
  oficial é `P20.01.00001`, no formato que o livro-caixa já usa.
- **DARF 0190**, vencimento no último dia útil do mês seguinte, e valor
  abaixo de R$ 10,00 levado ao mês seguinte: confirmados na página
  "Carnê-leão — pagar", no RIR/2018 art. 123 e na pergunta 267.

**Erro da pesquisa, corrigido antes do registro.** O relatório terminou
recomendando uma tabela progressiva com parcelas a deduzir de R$ 636,13
(22,5%) e R$ 869,36 (27,5%), valores de tabela antiga. O texto bruto da
Lei 15.191/2025 (art. 2º, que dá nova redação ao art. 1º, XII, da Lei
11.482/2007, "a partir do mês de maio do ano-calendário de 2025") traz
**R$ 675,49** e **R$ 908,73**. O RC-131 registra os valores da lei. Quem
codificar a fatia 2 grava a tabela como dado com vigência e confere de novo
contra o texto da lei.

**Ainda hipótese:** o valor por dependente de 2026 (R$ 189,59) é o último
fixado em norma, sem alteração encontrada, mas nenhuma fonte diz "2026"
literalmente (HI-32).

## Fatia 2 — objetivo, escopo e critérios (2026-09-27, `arquiteto-senior`)

**Objetivo:** o escritório vê, por cliente pessoa física e por mês, quanto de
carnê-leão é devido, com a memória de cálculo completa, calculado a partir do
livro-caixa já escriturado. Nível de risco 1: cálculo de tributo.

**Divisão:** servidor e API primeiro (`desenvolvedor-pleno`); tela do
demonstrativo depois (`especialista-frontend`); auditoria da versão integrada
(`auditor-qa`). A geração do DARF continua fora: o Carnê-Leão Web gera a
guia.

**Escopo do servidor:**

1. **Dados normativos com vigência, nunca no código** (RC-131): tabela
   progressiva mensal, redução mensal da Lei 15.270/2025 e valor por
   dependente, cada um com data inicial de vigência e fonte citada, gravados
   por migração de dados. O desconto simplificado mensal sai da tabela
   vigente (25% do limite da faixa de alíquota zero), não de número solto.
   Nova vigência não altera a apuração de mês anterior a ela.
2. **Dependentes por cliente, com vigência mensal** (HI-35): quantidade
   informada pelo escritório, a partir de um mês.
3. **Apuração mensal** derivada dos lançamentos de caixa, sem gravar
   resultado que possa divergir deles (RC-130: corrigir o mês original muda
   aquele mês e o encadeamento dos seguintes). Por mês:
   - rendimentos sujeitos ao carnê-leão, por origem e código;
   - deduções reais: previdência oficial (`P20.01.00001`), pensão
     alimentícia (`P20.01.00002`), dependentes × valor vigente e livro-caixa
     (`P10`), este só contra rendimento do trabalho não assalariado e
     limitado a ele, com o **excesso levado aos meses seguintes até
     dezembro**, nunca a janeiro;
   - desconto simplificado mensal, como alternativa; aplica a forma mais
     benéfica e mostra as duas (HI-33);
   - imposto pela tabela, menos a parcela a deduzir, menos a redução da Lei
     15.270/2025 (limitada ao imposto, § 1º);
   - compensação do imposto pago no exterior (`P20.01.00003`) nos limites da
     norma;
   - valor abaixo de R$ 10,00 somado ao mês seguinte; código 0190.
4. **Demonstrativo anual:** os 12 meses do ano-calendário com os totais.
5. **API** somente leitura para o demonstrativo, com o mesmo padrão de
   autorização, isolamento e leitura sob snapshot do Balanço (DE-067); só
   cliente em modo livro-caixa.

**Dúvidas que o `desenvolvedor-pleno` resolve na fonte oficial antes de
codificar** (texto integral do Perguntas e Respostas IRPF 2026, RIR/2018 e
Manual do Carnê-Leão; a regra de consultar antes de perguntar vale para ele
também). O que continuar sem resposta vira hipótese registrada, nunca
comportamento silencioso:

- a redução da Lei 15.270/2025 é calculada sobre o **rendimento tributável
  bruto** do mês ou sobre a **base depois das deduções**;
- rendimento recebido de **pessoa jurídica** entra na base do carnê-leão, ou
  só serve de limite para a dedução do livro-caixa;
- limite da compensação do imposto pago no exterior;
- arredondamento de cada etapa (usar `apps/core/dinheiro.py`, com a política
  escolhida declarada e justificada).

**Critérios de aceite:**

1. Casos de referência **calculados à mão** no teste, com o cálculo escrito
   no comentário: faixa isenta; cada faixa da tabela; rendimento de R$
   5.000,00 (imposto zero pela redução); R$ 6.000,00 (redução parcial); R$
   7.350,00 e R$ 7.350,01 (fim da redução); dedução maior que a receita, com
   o excesso carregado; excesso em dezembro que não passa a janeiro;
   dependentes; desconto simplificado mais benéfico e menos benéfico; valor
   abaixo de R$ 10,00 acumulado; centavos.
2. Troca de vigência da tabela no meio do ano: os meses anteriores não mudam.
3. Estorno e correção no mês original refletem no mês e no encadeamento
   (RC-130).
4. Isolamento entre clientes e escritórios em toda porta; autorização no
   servidor; recusa para cliente em modo contabilidade.
5. Nenhum número normativo no código: teste que falha se a tabela vier de
   constante.
6. Suíte completa, lint, formatação, `check`, `makemigrations --check`,
   migração em banco vazio.

**Hipótese nova:** **HI-35** — dependentes são informados pelo escritório
por quantidade, com vigência mensal, sem cadastro nominal nesta fatia.

## Implementação da fatia 2 (2026-09-27, `desenvolvedor-pleno`)

Servidor + API apenas — a tela vem depois pelo `especialista-frontend`.
Branch `dl046-f2`, base `58f66fb`, worktree `wt-dl046f2`.

### Dúvidas resolvidas na fonte antes de codificar

As quatro dúvidas listadas na seção anterior, na ordem em que aparecem lá:

1. **Base da redução da Lei 15.270/2025: rendimento bruto ou base após
   deduções?** ⚠️ **Respondida ERRADO na primeira rodada, corrigida por
   ordem do arquiteto-senior em 2026-09-27** — ver "Correção da RC-133",
   abaixo. **Resposta correta: RENDIMENTO BRUTO, antes de qualquer
   dedução** (inclusive livro-caixa) — nunca a base de cálculo. Registrado
   como **RC-133**.
2. **Rendimento de pessoa jurídica entra na base do carnê-leão, ou só serve
   de limite para a dedução do livro-caixa?** **Não entra na BASE, exceto
   notarial.** RIR/2018, art. 118, caput, restringe a base a rendimento
   recebido de OUTRA PESSOA FÍSICA ou de fonte do EXTERIOR; o inciso IV é
   explícito para aluguel ("recebidos de pessoas físicas"). A Lei nº
   7.713/1988, art. 8º, §1º, estende o caput aos emolumentos/custas de
   serventuários da Justiça SEM restringir a fonte pagadora — só esse
   modelo (notarial) integra a base vindo de PJ. Rendimento de PJ fora
   desse caso é tributado por retenção na fonte pela própria fonte
   pagadora, fora do escopo desta fatia.
   ⚠️ **A frase seguinte desta resposta estava ERRADA e foi corrigida na
   rodada 1 da auditoria da fatia 2 (achados A-1/A-2, DE-091 item 1):** a
   versão original dizia "como consequência, PJ também não entra no
   limite da dedução do livro-caixa" — **falso**. O LIMITE do livro-caixa
   (art. 68/69, RIR/2018) é DIFERENTE da BASE do carnê-leão: a Perguntas e
   Respostas IRPF 2026, pergunta 428, diz que a dedução é "limitada ao
   valor da receita mensal recebida de pessoa física **ou jurídica**", e a
   página oficial "Carnê-leão — Deduções" confirma "pessoa física, de
   pessoa jurídica e do exterior". O limite soma a receita de trabalho não
   assalariado **e** notarial de QUALQUER origem (PF, PJ, exterior); só a
   DEDUÇÃO em si (contra a base) fica restrita ao rendimento que integra a
   base. Registrado como **RC-132** (corrigida), junto com a imunidade da
   pensão alimentícia recebida (STF, ADI 5.422, citada no Perguntas e
   Respostas IRPF 2026, pergunta 266).
3. **Limite da compensação do imposto pago no exterior?** A diferença
   entre o imposto apurado COM a inclusão do rendimento de fontes do
   exterior daquele mês e o imposto apurado SEM essa inclusão (mesma
   dedução — real ou simplificada — já escolhida como mais benéfica); o
   excesso não compensado é levado aos meses seguintes até dezembro do
   mesmo ano-calendário e à Declaração de Ajuste Anual — Perguntas e
   Respostas IRPF 2026, pergunta 267 ("Atenção"). Registrado como
   **RC-134**.
4. **Arredondamento de cada etapa?** **Sem fonte encontrada** — nenhuma
   das quatro fontes lidas fixa a política das etapas intermediárias (só o
   resultado final, implicitamente, por ser sempre em reais e centavos).
   Registrado como **HI-36**: `PoliticaArredondamento.MEIO_PARA_CIMA`
   (ROUND_HALF_UP) a 2 casas, aplicado a cada valor que se torna uma linha
   da memória de cálculo — opção CONSERVADORA (nunca truncar, que
   reduziria o imposto devido em relação ao valor exato).

### Achado material da primeira rodada — SUPERADO pela correção da RC-133

A primeira versão desta seção registrava aqui um "achado material": a
combinação da tabela progressiva com a fórmula de redução, usando a BASE
DE CÁLCULO (após deduções) como referência da redução, não reproduzia a
"imposto zero até R$ 5.000,00" que a lei descreve — dava R$ 153,38 para
R$ 5.000,00 de rendimento sem outras deduções. **Esse achado nasceu de uma
leitura errada da norma** (RC-133 usava a base, deveria usar o rendimento
BRUTO — ver "Correção da RC-133", abaixo). Corrigida a referência, a
frase da lei volta a se verificar: qualquer rendimento bruto até
R$ 5.000,00, sem outras deduções, produz imposto ZERO pela forma
simplificada (que a apuração escolhe por ser mais benéfica) — ver
`test_bruto_ate_5000_sempre_zera_via_forma_mais_beneficia`. O texto desta
seção fica só como registro histórico do erro e da correção; não descreve
o comportamento atual.

### O que foi feito

1. **Quatro modelos normativos, nunca constante no código** (RC-131 a
   RC-134, HI-32, HI-36): `VigenciaTabelaProgressivaCarneLeao` +
   `FaixaTabelaProgressivaCarneLeao` (tabela progressiva, uma vigência com
   N faixas), `VigenciaReducaoCarneLeao` (redução da Lei 15.270/2025),
   `VigenciaDependenteCarneLeao` (valor por dependente) — todos com
   `fonte` obrigatória, gravados só por MIGRAÇÃO DE DADOS
   (`0004_fatia2_seed_tabelas_normativas.py`, com a fonte de cada valor
   citada no próprio código da migração), sem `ModelAdmin` (DE-090).
   Unicidade de `vigencia_inicio` por `UniqueConstraint` em
   `Meta.constraints`, nunca `unique=True` de campo (DE-089, evita a lista
   separada de índices únicos implícitos — ver "Não testado/bloqueado").
2. **`DependentesCarneLeaoCliente`** (empresa, quantidade, competência):
   único modelo desta fatia com caminho de ESCRITA de cliente
   (`registrar_dependentes_carne_leao`, trava a empresa por
   `select_for_update()` mesmo padrão de N6/DL-046 fatia 1).
3. **Motor de cálculo** (`apps/livro_caixa/carne_leao.py`): funções PURAS
   (`_pipeline`/`_imposto_pela_tabela`/`_reducao_bruta`/`_agregados_do_mes`,
   sem ORM, testáveis com casos calculados à mão) separadas da camada ORM
   (`_apurar_ano_calendario`, que agrega lançamentos + vigências com número
   de consultas CONSTANTE em relação ao número de meses). Encadeamento
   (excesso de livro-caixa, saldo de crédito do exterior, saldo abaixo de
   R$ 10,00) SEMPRE recalculado a partir de janeiro do ano pedido — nunca
   lê nem grava resultado (RC-130).
4. **Leitura sob SNAPSHOT** (DE-067, mesmo padrão de
   `apurar_balanco_patrimonial`/`_apurar_coluna_dre`, contabilidade):
   `apurar_carne_leao_mensal`/`apurar_carne_leao_anual` rodam sob
   `REPEATABLE READ` quando não já dentro de uma transação.
5. **API somente leitura**: `GET .../carne-leao/mensal/?ano=&mes=`,
   `GET .../carne-leao/anual/?ano=`; e a única de escrita desta fatia,
   `GET/POST .../dependentes-carne-leao/`. Mesma matriz de papéis e mesma
   recusa por modo de escrituração da fatia 1
   (`EmpresaEscopadaLivroCaixaMixin`).

## Correção da RC-133 (2026-09-27, ordem do arquiteto-senior)

A RC-133 original (base de cálculo) estava ERRADA. O arquiteto-senior leu
fonte adicional — Receita Federal, "Exemplos de Aplicação da Lei
15.270/2025" (gov.br/receitafederal, cópia em `scratchpad/exemplos15270.html`)
e IN RFB nº 2.299/2025 (cópia do DOU em `scratchpad/in2299.txt`) — e
determinou a correção. Fonte e trecho literal na RC-133 reescrita
(requisitos.md).

**O texto que decide, do Exemplo 5 oficial** (bruto R$ 7.607,20, sem
dedução real, base de cálculo R$ 7.000,00 — dentro do limite de
R$ 7.350,00): *"o salário (rendimento tributável sujeito à incidência
mensal) é superior ao valor de R$ 7.350,00 (...) não é permitida a
redução (...). Importante observar que se utiliza nessa tabela de redução
o valor do SALÁRIO (R$ 7.607,20), e NÃO o da BASE DE CÁLCULO
(R$ 7.000,00)."*

### Achado → mudança → teste

| Achado | Mudança | Teste |
| --- | --- | --- |
| RC-133 usava a BASE em vez do BRUTO na redução da Lei 15.270/2025 (nas duas chamadas — real e simplificada) | `_reducao_bruta` passa a receber `rendimento_bruto` (não mais `base`); `_pipeline` recebe os dois parâmetros separados; `_limite_compensacao_exterior` passa o bruto certo (com/sem o rendimento do exterior) nas duas chamadas | Os cinco exemplos oficiais da Receita adaptados ao carnê-leão (`test_exemplo_oficial_1` a `_5`), `test_bruto_ate_5000_sempre_zera_via_forma_mais_beneficia`, `test_reducao_limitada_ao_imposto_com_deducoes_reais_altas` |
| Consequência: o "achado material" (R$ 5.000,00 não zerava) deixa de existir — corrigido o bruto/base, a forma simplificada sempre alcança zero até R$ 5.000,00, como a lei descreve | `test_rendimento_5000_sem_outras_deducoes_nao_zera_o_imposto` REMOVIDO; docstring do módulo e desta seção do plano reescritos | `test_bruto_ate_5000_sempre_zera_via_forma_mais_beneficia` |
| Dois testes que já existiam tinham valores calculados com a fórmula ERRADA (base) | Recalculados com a fórmula CORRETA (bruto), conferidos via shell antes de gravar no comentário | `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`, `test_apuracao_le_valor_do_banco_nao_de_constante` (este também passou a mirar `memoria_deducoes_reais.reducao_aplicada` em vez do campo do topo — no cenário daquele teste especificamente, sem outra dedução real, o desconto simplificado era a MAIOR dedução e por isso a forma escolhida; a mutação de `reducao_maxima` só é visível na memória da forma perdedora. ⚠️ **Correção da rodada 1 da auditoria da fatia 2 (B-3): a frase geral "bruto ≤ R$ 5.000,00 SEMPRE escolhe a forma simplificada" que estava aqui era FALSA** — a escolha depende da MAIOR DEDUÇÃO (DE-091 item 2/M-1), e uma dedução real maior que o desconto simplificado vence mesmo com bruto baixo; ver `test_dependentes_reduzem_a_base`, corrigido na mesma rodada, que é exatamente um contraexemplo.) |

### Mutante M6 (aplicado vivo, confirmado vermelho, revertido)

`_pipeline` voltou a chamar `_reducao_bruta(base, reducao_cfg)` em vez de
`_reducao_bruta(rendimento_bruto, reducao_cfg)` — **3 testes** ficaram
vermelhos: os dois exemplos oficiais que dependem da distinção
(`test_exemplo_oficial_4_renda_acima_de_5000_com_reducao`,
`test_exemplo_oficial_5_base_menor_que_7350_mas_bruto_maior_sem_reducao`)
e `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`.

### Verificação da correção

Commits da correção: `f286361` (RC-133) e `dd4b3ad` (guardas). `apps/livro_caixa/
tests/test_dl046_fatia2_carne_leao.py`: **40 testes, todos passando**
(35 da entrega original, 4 removidos/substituídos pelos 5 exemplos
oficiais + os 2 casos adicionais pedidos). `ruff check`/`ruff format
--check`/`manage.py check`/`makemigrations --check` limpos (sem mudança
de schema nesta correção — só código e dados de teste).

### Regras reportadas, não decididas (para o `arquiteto-senior`/Fred)

- **Pensão alimentícia paga × dependente do MESMO beneficiário**
  (RIR/2018, art. 72, §1º: veda deduzir os dois para o mesmo beneficiário
  no mesmo mês). Como os dependentes desta fatia são só QUANTIDADE (HI-35,
  sem nome), a apuração SOMA as duas deduções sem verificar coincidência
  de beneficiário — se o escritório escriturar pensão e dependente da
  MESMA pessoa, a contagem duplicada é responsabilidade de quem digita a
  quantidade, não uma verificação do sistema. Documentado no código
  (`apps/livro_caixa/carne_leao.py`).
- **Modelo ALUGUEL_OUTROS (código `R01.004.001`, "outros rendimentos")
  segue a MESMA restrição de aluguel** (só PF/EX na base) por analogia —
  a fonte confirma isso literalmente só para aluguel (art. 118, IV); não
  encontrei fonte específica para "outros rendimentos".
- **Código de rendimento fora dos quatro modelos oficiais mapeados** (nem
  trabalho não assalariado, nem notarial, nem aluguel/outros, nem pensão):
  integra a base independentemente da fonte pagadora — opção CONSERVADORA
  (nunca presumir isenção sem fonte), até a tabela completa de códigos
  (PE-71) aparecer.
- **Saldo "abaixo de R$ 10,00" reinicia em janeiro NESTA IMPLEMENTAÇÃO** —
  registrado como **HI-37** (requisitos.md), por ordem do arquiteto-senior:
  mantido como está (a apuração nunca lê dezembro do ano anterior), sem
  fonte que confirme esse corte por ano-calendário especificamente para
  este saldo (diferente do excesso do livro-caixa e do crédito do
  exterior, que a norma confirma reiniciarem em janeiro).
- **Desempate entre deduções reais e desconto simplificado**, quando os
  dois produzem o MESMO imposto após redução: fica com as deduções REAIS
  (regra geral, art. 68) — desenho meu, sem instrução explícita sobre o
  desempate.

### Testes

`apps/livro_caixa/tests/test_dl046_fatia2_carne_leao.py` (**40 testes**,
depois da correção da RC-133): motor puro com os CINCO exemplos oficiais
da Receita Federal adaptados ao carnê-leão (Exemplos 1 a 5 — RC-133),
mais o caso "bruto ≤ R$ 5.000,00 sempre zera" e "redução limitada ao
imposto com deduções reais altas" (pedidos do arquiteto-senior), cada
faixa da tabela, centavos na fronteira de faixa; motor ORM (excesso de
livro-caixa carregado e não carregado ao ano seguinte, dependentes com
vigência mensal, desconto simplificado mais e menos benéfico, valor
abaixo de R$ 10,00 acumulado, compensação do imposto pago no exterior,
rendimento de PJ excluído da base, pensão recebida imune, notarial de PJ
incluído), troca de vigência no meio do ano (critério 2), RC-130 (estorno
no mês original refletindo no encadeamento), isolamento/autorização/modo
via API, e a prova de que a tabela nunca vem de constante (deletar todas
as vigências levanta `TabelaCarneLeaoNaoConfigurada`; mudar um valor só
no banco muda o resultado).

**Mutantes aplicados (vivos, confirmados vermelhos, revertidos):**

| # | Ponto mutado | Teste que matou |
| --- | --- | --- |
| M1 | `_reducao_bruta`: faixa plena da redução desativada | `test_reducao_por_faixa_do_rendimento_bruto` |
| M2 | `_apurar_um_mes`: reset de dezembro do excesso de livro-caixa desativado | `test_excesso_de_dezembro_nao_passa_para_janeiro` |
| M3 | `rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal`: sempre `True` (RC-132 desativada) | `test_rendimento_de_pessoa_juridica_nao_entra_na_base_do_trabalho_nao_assalariado` |
| M4 | `_lancamentos_por_mes`: filtro de `empresa` removido da consulta | `test_api_carne_leao_mensal_isolamento_entre_empresas_do_mesmo_escritorio` |
| M5 | `_agregados_do_mes`: sinal do estorno deixa de inverter | `test_estorno_no_mes_original_reflete_no_encadeamento`, `test_agregados_do_mes_estorno_tem_sinal_invertido` |
| M6 | `_pipeline`: redução volta a usar a BASE em vez do BRUTO (correção da RC-133 desativada) | `test_exemplo_oficial_4_renda_acima_de_5000_com_reducao`, `test_exemplo_oficial_5_base_menor_que_7350_mas_bruto_maior_sem_reducao`, `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais` |

### Verificação

Commits: `8996522`, `b6775f8`, `f286361`, `dd4b3ad` (branch `dl046-f2`, worktree
`wt-dl046f2`).

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — sem apontamentos (arquivos novos/alterados
  formatados com `ruff format` durante a implementação).
- `python manage.py check` — nenhum problema.
- `python manage.py makemigrations --check --dry-run` — nenhuma alteração
  pendente.
- Migrações `livro_caixa.0003_fatia2_tabelas_normativas` e
  `0004_fatia2_seed_tabelas_normativas` aplicadas com sucesso em
  PostgreSQL vazio, com reversão e reaplicação confirmadas.
- `pytest` (suíte completa): ver o relatório de entrega para o número
  exato — a única falha é a pré-existente e esperada
  (`test_versao_minima_python.py`, ambiente Python 3.13 local em vez do
  3.14 da CI, já registrada nas fatias anteriores). As duas guardas de
  repositório que ficaram vermelhas na entrega original (rotas novas em
  `EXCLUSOES_NOMEADAS_DE_TELA`; modelos novos na cobertura da trilha)
  foram corrigidas com autorização explícita do arquiteto-senior, nos
  dois arquivos e exatamente nas entradas descritas — sem pendência.

### Não testado / bloqueado

- **As duas guardas de repositório que ficaram vermelhas na entrega
  original foram corrigidas** com autorização explícita do
  arquiteto-senior, exatamente nos dois arquivos e entradas indicados —
  `apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py`
  (`EXCLUSOES_NOMEADAS_DE_TELA`, as três rotas novas) e
  `apps/core/tests/test_dl024_trilha_admin.py` (import + `esperados_cobertos`,
  os cinco modelos novos). Sem pendência.
- **Dígito verificador do CAEPF, faixa de data do lançamento de caixa,
  HI-31** — herdados da fatia 1, sem mudança aqui.
- **Tela do demonstrativo** — do `especialista-frontend`, fora do meu
  escopo.
- **Validação profissional dos casos de referência** (Fred) — a correção
  da RC-133 bate, número a número, com os cinco exemplos oficiais da
  Receita Federal (ver "Correção da RC-133"), o que reduz bastante o
  risco deste item, mas não substitui a validação profissional.
- HI-37 (saldo abaixo de R$ 10,00 sem atravessar o ano-calendário) —
  mantido como está, por ordem do arquiteto-senior; ver requisitos.md.
- `pwsh ./scripts/validate-docs.ps1` — `pwsh` não existe neste ambiente
  (mesmo bloqueio já registrado pelas fatias anteriores).

## Correção da rodada 1 da fatia 2 (2026-09-27, `desenvolvedor-pleno`)

**REPROVADA** na [auditoria da rodada
1](../auditorias/2026-09-27-dl-046-fatia2-rodada-1.md) (dois achados
ALTOS, oito MÉDIOS, seis BAIXOS). Encaminhamento pelo `arquiteto-senior`:
A-1, A-2, M-1 a M-6 e M-8 ao `desenvolvedor-pleno`; M-2 com o
`especialista-frontend`; M-3 e M-7 decididos pelo próprio arquiteto (ver
[DE-091](../projeto/decisoes.md)). Esta é a ÚNICA correção antes da
reconferência (AGENTS.md §3.1).

### Item a item da DE-091

1. **A-1/A-2 (limite do livro-caixa, ALTO).** O limite do art. 68/69
   (RIR/2018) passa a somar a receita de trabalho não assalariado **e**
   notarial, de QUALQUER origem (PF, PJ ou exterior) — `_agregados_do_mes`
   ganhou `receita_atividade_limite`, calculado FORA do filtro de
   sujeição da base. A DEDUÇÃO em si continua restrita ao rendimento que
   integra a base (RC-132, corrigida — ver acima). A parte do excesso
   carregada ao mês seguinte é só o que passa do LIMITE; a parte dentro
   do limite sem contrapartida na base (receita de PJ, por exemplo) não é
   carregada — pertence à declaração anual, fora do escopo. Testes:
   `test_aud_a1_notarial_livro_caixa`, `test_aud_a2_pj_no_limite_do_livro_caixa`,
   `test_aud_a6_aluguel_nao_entra_no_limite_do_livro_caixa`.
2. **M-1 (forma pela maior dedução).** `_apurar_um_mes` passou a escolher
   entre desconto simplificado e deduções reais pela MAIOR DEDUÇÃO, ANTES
   da redução — critério da própria Receita (P&R 267: "o desconto
   simplificado é mais vantajoso... quando o valor for maior"). Empate:
   simplificado (dispensa comprovação). Os dois testes que fixavam o
   desempate "real" antigo (`test_excesso_de_dezembro_nao_passa_para_
   janeiro`, `test_dependentes_reduzem_a_base`) foram corrigidos; a frase
   "SEMPRE escolhe a forma simplificada" (achado dela mesma, B-3) foi
   corrigida na tabela de achados da correção da RC-133, acima. Testes:
   `test_aud_exemplo1_forma_escolhida_via_orm`,
   `test_aud_exemplo2_forma_escolhida_via_orm`,
   `test_aud_criterio_escolha_forma_no_empate`.
3. **M-3/HI-38 (compensação do exterior, leitura literal).** Decisão do
   arquiteto-senior (DE-091): leitura LITERAL da P&R 267 — só a parte do
   pagamento do mês que cabe dentro do limite (diferença entre o imposto
   COM e SEM o rendimento do exterior) entra no crédito disponível; o que
   passa do limite nunca compensa nem carrega. Achado do desenvolvedor
   durante a implementação, não previsto no pedido original: sob esta
   definição, o crédito disponível de um mês NUNCA excede o imposto
   daquele mês (a diferença "com − sem" nunca é maior que o "com"), então
   a linha `if mes == 12: saldo = 0` é uma defesa em profundidade contra
   mudança futura da fórmula, nunca alcançada pela apuração real — testada
   diretamente via `_apurar_um_mes` com um saldo anterior FORÇADO
   (`test_aud_a14_saldo_exterior_zera_em_dezembro`). Imposto pago no
   exterior sem rendimento do exterior no mês (HI-38): recusado na
   APURAÇÃO (não na gravação do lançamento) — ver o docstring de
   `ImpostoExteriorSemRendimentoExterior` para a justificativa completa da
   escolha do ponto de recusa. Testes: `test_aud_exterior_limite`,
   `test_aud_hi38_imposto_exterior_sem_rendimento_exterior_e_recusado`,
   `test_aud_api_recusa_mes_com_imposto_exterior_sem_rendimento`.
4. **M-4 (estorno e alerta).** `estornar_lancamento_caixa` passa a usar a
   data do ORIGINAL como padrão (era "hoje"); data explícita de outro mês
   é recusada, citando RC-130. A apuração devolve um alerta explícito
   para qualquer mês com rendimento líquido negativo. Testes fatia 1
   ajustados: `test_api_estorno_e_relatorio`,
   `test_relatorio_mostra_estorno_visivel`; ajuste pontual autorizado em
   `scripts/medir_identificacao_do_emitente.py` (comentário, sem mudança
   de data — a data já ficava no mesmo mês do original).
5. **M-5 (2025 fora do escopo).** Migração `0006` semeia a tabela
   progressiva de jan-abr/2025 (P&R 267, valores conferidos em
   `scratchpad/pr_irpf_2026.txt`). Ausência de vigência de REDUÇÃO antes
   de 2026 passa a ser tratada como ausência LEGÍTIMA (`reducao_cfg=None`
   em `_reducao_bruta`/`_pipeline`), nunca erro. Ano < 2025: mensagem
   explícita de fora de escopo (`_PRIMEIRO_ANO_COM_TABELA`). Testes:
   `test_aud_m5_fevereiro_2025_sem_reducao_tabela_jan_abr`,
   `test_aud_m5_junho_2025_tabela_rc131_sem_reducao`,
   `test_aud_m5_ano_anterior_a_2025_e_explicitamente_fora_do_escopo`.
6. **M-6 (retificação de dependentes).** Nova função
   `retificar_dependentes_carne_leao` (PATCH), com trilha de auditoria
   antes/depois — nunca um novo registro concorrente. Rota
   `dependentes-carne-leao/<id>/` (PATCH), exigindo `PodeEscriturarLivro
   Caixa`. Testes: `test_aud_m6_retificacao_de_dependentes_com_trilha`,
   `test_aud_m6_api_patch_dependentes_sucesso`,
   `test_aud_m6_api_patch_dependentes_outro_escritorio_404`,
   `test_aud_m6_api_patch_dependentes_papel_sem_escrita_403`.
7. **M-2/B-6 (contrato da API).** Mensal: `rendimentos` (lista de
   `{codigo, origem, valor, entra_na_base, motivo_exclusao}`),
   `imposto_com_exterior`/`imposto_sem_exterior`, `vencimento` (texto),
   `alertas`, `criterio_escolha_forma` (texto gerado no MESMO ponto da
   escolha da forma — acréscimo do arquiteto-senior). Cada memória de
   cálculo (`memoria_deducoes_reais`/`memoria_desconto_simplificado`)
   ganhou `faixa_aplicada` e `vigencia_tabela_inicio` (segundo acréscimo).
   Anual: `totais` — soma EXATA dos 12 meses de 8 campos nomeados.
   Testes: `test_aud_m2_rendimentos_por_codigo_e_origem`,
   `test_aud_m2_vencimento_ultimo_dia_util_do_mes_seguinte`,
   `test_aud_m2_imposto_com_e_sem_exterior_no_mensal`,
   `test_aud_m2_totais_anuais_sao_a_soma_exata_dos_12_meses`,
   `test_aud_faixa_aplicada_e_vigencia_em_cada_memoria`.
8. **B-1 (percentual do desconto simplificado no banco).** Novo campo
   `percentual_desconto_simplificado` em `VigenciaTabelaProgressivaCarneLeao`
   (migração `0005`, backfill `0,25` com fonte, `preserve_default=False`).
   `_LIMITE_DARF` (R$ 10,00) permanece constante LEGAL no código — exceção
   CONSCIENTE ao critério 5, documentada no docstring do módulo e na
   DE-091 item 9. Teste: `test_aud_b1_percentual_simplificado_muda_so_no_banco`.
9. **B-2 a B-5 (correções pontuais).** HI-36: retirada a frase "nunca
   reduz o imposto em relação ao exato" (requisitos.md). DE-089: corrigida
   a menção a `unique=True` para `UniqueConstraint` (decisoes.md). Nova
   HI-40: limitação pensão × dependente do mesmo beneficiário (art. 72,
   §1º, RIR/2018) não modelada nesta fatia (sem cadastro nominal).
   Mensagem de duplicidade de competência dos dependentes mapeada em
   `apps/core/restricoes.py` E como `violation_error_message` da
   constraint (cobre os dois caminhos). Toda vigência normativa (e a
   competência dos dependentes) ganhou `CheckConstraint` de dia 1
   (migração `0005`).
10. **M-8 (lacunas de teste).** Casos da seção 5 do relatório de auditoria
    implementados (ver a lista de testes acima e os itens 1-9). Mutantes
    A2, A6, A8 a A15, A17, A19, A21 a A23 reaplicados e confirmados
    vermelhos (tabela no relatório de entrega desta correção).

### Não testado / bloqueado nesta correção

- Concorrência real no PATCH/POST de dependentes (A24 — mesma limitação
  já registrada na rodada anterior, `select_for_update` mitiga mas não
  prova).
- Comportamento real do Carnê-Leão Web (inacessível) para M-3/M-1 —
  decisão tomada pelo arquiteto-senior sem essa confirmação (DE-091).
- M-7 (exclusões do aluguel, RIR/2018 art. 42) — decisão do
  arquiteto-senior de manter fora do escopo desta correção (DE-091 não a
  lista); HI-39 continua registrando a limitação.
- A tela (fora do escopo — outro worktree, `especialista-frontend`).
- `pwsh ./scripts/validate-docs.ps1` — mesmo bloqueio de ambiente.

## Tela da fatia 2 (2026-09-27, `especialista-frontend`)

Servidor + API já prontos (seção anterior, `desenvolvedor-pleno`, worktree
`dl046-f2`); esta etapa é só a FRENTE DA TELA, worktree `dl046-f2-tela`,
base `5ed0e5e`. Nenhuma linha de `apps/livro_caixa/carne_leao.py`,
`models.py`, `services.py`, `serializers.py` nem `views.py` (API) foi
tocada — a regra é só apresentar o que o motor devolve.

### O que foi feito

1. **Três telas novas** (`apps/livro_caixa/views_web.py`,
   `apps/livro_caixa/urls_web.py`):
   - `carne_leao_mensal` (`GET /livro-caixa/painel/empresas/<id>/
     carne-leao/?ano=&mes=`) — arquétipos D (painel de período, navegação
     "‹ Mês anterior / Mês seguinte ›", mesmo desenho de
     `contabilidade_web:dre`) e documento de conferência combinados:
     UMA tabela (`<table class="tabela-dados">`) com a identificação do
     documento no `<thead>` (repete em toda folha impressa,
     `display: table-header-group`, mesma técnica do Livro Caixa/DRE/
     Balanço) e a memória de cálculo completa em seções (`<tbody>` por
     grupo): rendimentos sujeitos, deduções reais linha a linha,
     desconto simplificado com a comparação lado a lado das duas
     memórias (`memoria_deducoes_reais`/`memoria_desconto_simplificado`,
     já prontas no motor) e um `.selo` "Aplicada" na forma vencedora,
     apuração do imposto (base, imposto pela tabela, redução da Lei
     15.270/2025 — com o texto explícito "calculada sobre o rendimento
     tributável BRUTO... nunca sobre a base de cálculo" citando o
     valor bruto usado), compensação do exterior, resultado do mês
     (imposto devido, saldo abaixo de R$ 10,00, valor a pagar, código
     0190 e "Último dia útil de MM/AAAA" — MM/AAAA é o mês seguinte à
     competência, por aritmética de calendário civil pura, nunca
     resolução de dia útil/feriado, conforme a tarefa pediu
     explicitamente).
   - `carne_leao_anual` (`GET .../carne-leao/anual/?ano=`) — os 12 meses
     em tabela (Mês/Rendimento sujeito/Dedução aplicada/Forma/Imposto
     após redução/Compensação exterior/Valor a pagar) com uma linha de
     TOTAL calculada por soma de apresentação dos 12 valores que o motor
     já produziu (nenhuma regra tributária nova — ver a nota sobre "sem
     cálculo na view", abaixo) — cada linha "Dedução aplicada" mostra o
     valor da forma EFETIVAMENTE aplicada naquele mês (reais ou
     simplificado, conforme `forma_escolhida`), e o total soma
     exatamente esses 12 valores, nunca sempre as deduções reais
     (senão o total impresso não bateria com a soma da coluna — direção
     de arte, regra de apresentação contábil).
   - `dependentes_carne_leao` (`GET/POST .../carne-leao/dependentes/`)
     — arquétipos A+B combinados (mesmo molde de
     `contabilidade_web:parametros_contabeis`): tabela das vigências já
     registradas + formulário (`DependentesCarneLeaoForm`, `ModelForm`
     sobre `DependentesCarneLeaoCliente`) que chama
     `registrar_dependentes_carne_leao` (o único serviço de ESCRITA
     desta fatia) — nunca grava direto pelo formulário.
2. **Nenhum cálculo tributário na view/template** — as funções
   `_contexto_resultado_mensal_carne_leao`/`_linha_anual_carne_leao`
   só formatam (`_valor_ptbr`) e rotulam os campos que o motor já
   devolve. Duas exceções PRESENTACIONAIS, documentadas em comentário
   no código, e reportadas como achado (abaixo): o mês de vencimento do
   DARF (deslocamento de calendário civil, `_competencia_carne_leao_
   adjacente`, cópia local do mesmo algoritmo PURO de
   `_competencia_adjacente`, contabilidade) e a soma de apresentação dos
   totais anuais (12 números já calculados pelo motor, somados só para
   exibição).
3. **Formulário de dependentes** com os cinco estados: sucesso (302 +
   mensagem), erro (400, formulário reexibido com o que foi digitado —
   `Model.clean()` já recusa dia diferente de 1, HI-35), sem permissão
   (403 no POST; GET mostra a tabela sem o formulário, sem convidar quem
   não pode escrever), vazio (nenhuma vigência ainda: `.estado-vazio`) e
   carregando (não aplicável — view síncrona).
4. **Menu** (`templates/base.html`): três itens novos no MESMO grupo
   "Livro-caixa" do submenu lateral (Carnê-leão, Carnê-leão anual,
   Dependentes (carnê-leão)) — nenhum grupo próprio, mesmo critério que
   "Parâmetros contábeis" usou dentro de "Cadastros" na contabilidade.
5. **Documento imprimível** (`_identificacao_do_documento_carne_leao.
   html`, novo partial): nome/razão social, CPF ou CNPJ conforme o TIPO
   DE INSCRIÇÃO cadastrado (nunca "CPF" fixo — mesma correção M6/DE-087
   item 7 que o relatório Livro Caixa já aplica), CAEPF quando houver, e
   base legal curta (RIR/2018 arts. 118 a 125; Lei nº 15.270/2025;
   tabela vigente — com a data de vigência no demonstrativo MENSAL, onde
   há uma vigência só; sem data fixa no ANUAL, onde os 12 meses podem
   usar vigências diferentes). Reaproveita o MESMO marcador CSS
   (`.identificacao-do-documento`) do relatório Livro Caixa — as duas
   telas novas entraram no piso do instrumento (abaixo).
6. **Achado de CSS corrigido nesta etapa** (medido pelo próprio
   instrumento, não hipotetizado): a tabela do demonstrativo anual tem
   sete colunas e não cabe em 390px — o primeiro invólucro
   (`overflow-x: auto`, classe nova `.tabela-com-rolagem-horizontal`,
   `static/css/base.css`) resolveu o estouro horizontal em TELA, mas
   criou um defeito em IMPRESSÃO: sem barra de rolagem no papel, a
   tabela crescia além da largura da folha e o conteúdo que passava da
   borda era CORTADO — inclusive parte do bloco de identificação
   ("15.270/2025" saía "15.270/202", faltando o "5"). Uma regra dentro
   de `@media print` (`overflow-x: visible`) desliga o rolamento só na
   impressão, devolvendo `table-layout: auto` normal (colunas encolhem
   para caber na página) — o instrumento, que tinha REPROVADO com o
   defeito, voltou a PASSAR depois da correção.

### Integração com o servidor corrigido (2026-09-27, mesmo dia, DE-091)

O `arquiteto-senior` integrou, neste worktree (`wt-dl046f2t`, branch
`dl046-f2-tela`), o merge de `dl046-f2` (motor corrigido pela rodada 1 de
auditoria da fatia 2, DE-091) — commit de merge no HEAD. A integração
quebrou 6 testes de tela (contrato do motor mudou); esta seção documenta
a adaptação.

**O que mudou no motor, e o que a tela passou a fazer:**

1. **Critério de escolha da forma** — o motor agora decide pela MAIOR
   DEDUÇÃO antes da redução (empate para o simplificado), e devolve
   `criterio_escolha_forma` (texto PRONTO, gerado no MESMO ponto em que a
   escolha acontece, com os dois valores comparados). A constante
   `_CRITERIO_ESCOLHA_FORMA_TEXTO_PADRAO` (que isolava o texto do
   critério ANTIGO, "menor imposto após a redução", enquanto o motor
   corrigido não chegava a este worktree) foi REMOVIDA — a tela imprime
   `resultado["criterio_escolha_forma"]` diretamente, sem texto fixo
   nenhum.
2. **Rendimentos por código e origem** — `resultado["rendimentos"]`
   (lista de `{codigo, origem, valor, entra_na_base, motivo_exclusao}`)
   substituiu as duas categorias agregadas antigas
   (`rendimento_trabalho_nao_assalariado`, que não existe mais — viraram
   `rendimento_trabalho_base`/`rendimento_notarial_base`, mais a lista
   detalhada). A tela agora mostra uma linha por (código, origem), com o
   motivo de exclusão quando o rendimento não entra na base (ex.:
   trabalho recebido de PJ, fora do modelo notarial) — fecha o achado
   próprio da entrega anterior ("o motor não expõe rendimento por
   código").
3. **Faixa aplicada e vigência da tabela** — cada memória
   (`memoria_deducoes_reais`/`memoria_desconto_simplificado`) ganhou
   `faixa_aplicada` (limite inferior/superior, alíquota, parcela a
   deduzir) e `vigencia_tabela_inicio`. A tela mostra os quatro dados por
   forma — fecha o outro achado próprio ("faixa/alíquota/parcela não
   expostas"). A alíquota (fração, ex. `0.0750`) é multiplicada por 100
   só para NOTAÇÃO de exibição (`_faixa_aplicada_ptbr`,
   `apps/livro_caixa/views_web.py`) — conversão de unidade para leitura,
   não um cálculo tributário novo.
4. **Imposto com/sem exterior** — `imposto_com_exterior`/`imposto_sem_
   exterior` (renomeados de um cálculo antes só interno) aparecem na
   tela SÓ quando há rendimento sujeito de origem exterior no mês
   (`ha_rendimento_exterior`, calculado a partir da própria lista
   `rendimentos` que o motor já classificou — nenhuma consulta nova).
5. **Vencimento pronto** — `resultado["vencimento"]` chega como texto
   PRONTO ("último dia útil de MM/AAAA"); a função local
   `_competencia_carne_leao_adjacente` deixou de ser usada para calcular
   o mês seguinte na tela mensal (continua existindo só para a navegação
   "‹ Mês anterior / Mês seguinte ›", que é sobre a COMPETÊNCIA exibida,
   não sobre o vencimento do DARF).
6. **Alertas** — `resultado["alertas"]` (lista de texto pronto — hoje só
   o de rendimento líquido negativo) aparece num componente de aviso
   (`.mensagem.mensagem-warning`) quando não vazio.
7. **`ImpostoExteriorSemRendimentoExterior`** — nova exceção do motor,
   levantada quando há imposto pago no exterior lançado sem nenhum
   rendimento sujeito de origem exterior no MESMO mês (HI-38). As duas
   telas (mensal e anual) capturam essa exceção ao lado de
   `TabelaCarneLeaoNaoConfigurada`, mostrando a mensagem do próprio motor
   como erro (409), nunca 500.
8. **Totais anuais do motor** — `apurar_carne_leao_anual` passou a
   devolver `resultado["totais"]` (soma EXATA dos 12 meses, 8 campos:
   `rendimento_bruto`, `deducoes_aplicadas`, `base`, `imposto_tabela`,
   `reducao_aplicada`, `compensacao_exterior`, `imposto_devido`,
   `valor_a_pagar`). `_totais_anuais_carne_leao` (que somava os 12 meses
   NA VIEW) foi REMOVIDA — `_totais_anuais_ptbr` só FORMATA o que o
   motor já somou. A tabela anual ganhou colunas correspondentes (dez ao
   todo: Mês, Rendimento bruto, Dedução aplicada, Forma, Base, Imposto
   pela tabela, Redução, Compensação exterior, Imposto devido, Valor a
   pagar) — cada uma espelhando, 1 para 1, um campo de `resultado
   ["totais"]", para a linha de total nunca precisar de uma soma que o
   motor não fez.
9. **Aviso fixo do art. 42 (RIR/2018)** — "Lance o aluguel sem IPTU,
   condomínio e taxa de administração pagos pelo locador" — mostrado na
   tela mensal quando há qualquer rendimento com o código de aluguel
   (`R01.003.001`) na lista `rendimentos`, entrando ou não na base.
10. **Retificação de dependentes** (DE-091 item 6/M-6) — nova view
    `dependentes_carne_leao_retificar` (`POST .../carne-leao/dependentes/
    <id>/retificar/`, rota de AÇÃO, só POST, sem tela própria — mesmo
    padrão de `contabilidade_web:parametro_contabil_encerrar`), chamando
    `retificar_dependentes_carne_leao` (o serviço novo do motor).
    Formulário inline na própria linha da tabela de vigências
    (`dependentes_carne_leao.html`), com `<input type="number" size="3">`
    (atributo HTML, não CSS — a largura padrão do navegador para
    `<input type="number">` estourava 390px).
11. **Estorno de lançamento de caixa** — o servidor passou a datar o
    estorno no MÊS do original por padrão, recusando data explícita de
    outro mês; como a tela NUNCA envia `data` explícita (o serviço já
    decide o padrão), este comportamento não muda nada visível — dois
    testes novos confirmam que o fluxo de estorno continua funcionando e
    que a recusa (estorno duplicado) continua saindo como erro de
    formulário (400), nunca 500.

**Achado de CSS adicional, medido pelo instrumento na integração:** o
`overflow-x: visible` do item 6 da seção anterior (que resolvia o corte
de impressão da tabela de SETE colunas) voltou a REPROVAR quando a
tabela anual ganhou DEZ colunas — a tabela, mesmo sem rolamento, continua
mais larga que a folha A4, e o `<th colspan="10">` do bloco de
identificação herdava essa largura inteira, então o texto só quebrava
linha muito além da borda física do papel (medido de novo: "15.270/2025"
voltou a cortar). Correção: `max-width: var(--largura-conteudo-agrupado)`
(token EXISTENTE, 40rem) só no bloco `.identificacao-do-documento`
DENTRO de `.tabela-com-rolagem-horizontal`, em `@media print` — força o
TEXTO da identificação a quebrar dentro de uma largura que cabe em A4,
independente de quantas colunas a tabela tiver; os DADOS da tabela
continuam podendo ficar mais largos que a folha (limitação aceita de
tabela larga impressa, sem novo teste de paginação de dados nesta
etapa). O mesmo estouro apareceu numa SEGUNDA tabela (vigências de
dependentes, coluna "Ações" nova) e recebeu o MESMO invólucro
(`.tabela-com-rolagem-horizontal`), reaproveitando a correção de
impressão já feita — nenhuma regra nova para aquela tabela.

### Testes

`apps/livro_caixa/tests/test_dl046_telas_carne_leao.py` (34 testes,
depois da integração com o servidor corrigido — eram 21 antes da
DE-091): renderização do mês com a memória de cálculo completa
(identificação, rótulos, valores), forma aplicada marcada com `.selo`
no lugar certo (nunca nas deduções reais quando o simplificado
venceu), mês sem movimento (aviso de estado, não de erro),
competência/ano inválidos (400, formulário/estado reexibido),
navegação de competência, anual (12 meses + totais, ano inválido),
isolamento entre escritórios (404) nas três telas, recusa para empresa
em modo contabilidade (403) nas três, papel sem permissão de leitura
(403, `Papel.CLIENTE`) nas três, formulário de dependentes (sucesso,
erro de dia≠1, sem permissão de escrita — `Papel.PARALEGAL` lê mas não
escreve), e número de consultas CONSTANTE (mensal: poucos x muitos
lançamentos no mês; anual: um mês x nove meses com movimento — não 12,
porque `criar_lancamento_caixa` recusa data além de "hoje + 30 dias" e
o ambiente de teste roda em 2026-09-27).

Treze testes novos, cobrindo a integração com o servidor corrigido
(DE-091) item a item:

- `test_carne_leao_mensal_mostra_rendimentos_por_codigo_e_origem` —
  cada linha da lista `rendimentos` do motor (código, origem, valor,
  se entra na base, motivo da exclusão) aparece na tabela.
- `test_carne_leao_mensal_mostra_aviso_fixo_do_aluguel_quando_ha_rendimento_r01_003_001`
  — o aviso do art. 42 do RIR/2018 aparece quando há rendimento do
  código `R01.003.001` no mês e some quando não há (dois meses
  comparados na mesma empresa, um com aluguel e outro sem).
- `test_carne_leao_mensal_mostra_faixa_aplicada_e_criterio_pronto_do_motor`
  — importa `apurar_carne_leao_mensal` diretamente no teste e compara o
  texto de `criterio_escolha_forma` DO MOTOR, caractere a caractere,
  com o texto renderizado na tela (nunca um texto fixo do template);
  confirma também que o texto antigo ("MENOR imposto após a...") NÃO
  aparece mais em lugar nenhum do HTML.
- `test_carne_leao_mensal_mostra_comparacao_com_e_sem_exterior` —
  `imposto_com_exterior`/`imposto_sem_exterior` e a faixa aplicada
  aparecem quando há rendimento do exterior sujeito.
- `test_carne_leao_mensal_imposto_exterior_sem_rendimento_e_erro_nao_500`
  e `test_carne_leao_anual_imposto_exterior_sem_rendimento_e_erro_nao_500`
  — `ImpostoExteriorSemRendimentoExterior` vira estado de erro (**409**,
  corrigido de "400" — R-B5 da reconferência: o texto desta seção dizia
  400, mas o código sempre devolveu 409, conferido pelos dois testes
  citados), nunca uma página de erro do servidor.
- `test_carne_leao_anual_usa_totais_do_motor_sem_somar_na_view` —
  dois meses com valores diferentes (não múltiplos um do outro, para
  que uma soma errada não coincida por acaso com o valor certo);
  importa `apurar_carne_leao_anual` diretamente no teste e confirma que
  TODOS os oito campos de `resultado["totais"]`, formatados em pt-BR,
  aparecem na tela — nenhum recalculado a partir de outros campos.
- `test_dependentes_retificar_sucesso`,
  `test_dependentes_retificar_quantidade_invalida_e_erro_sem_gravar`,
  `test_dependentes_retificar_sem_permissao_de_escrita`,
  `test_dependentes_retificar_isolamento_entre_empresas_da_404` — os
  quatro estados da retificação por PATCH (sucesso, erro de validação
  sem gravar nada, papel sem permissão de escrita, isolamento entre
  empresas com 404 em vez de vazar o registro de outra empresa).
- `test_lancamento_caixa_estorno_continua_funcionando` e
  `test_lancamento_caixa_estorno_duplicado_e_erro_de_formulario_nao_500`
  — confirmam que a tela de estorno do livro-caixa (fatia 1, não
  tocada nesta rodada) continua funcionando com a nova regra do
  serviço (estorno datado no mês do lançamento original) e que a
  recusa de um segundo estorno aparece como erro de formulário, nunca
  como página de erro do servidor.

`apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py`: três
entradas novas em `NOMES_DE_TELA_LIVRO_CAIXA_FORA_DA_CONTABILIDADE` +
três funções de teste (`test_tela_livro_caixa_carne_leao_mensal_e_
acessivel`, `..._anual_e_acessivel`, `..._dependentes_carne_leao_e_
acessivel`), mesmo padrão das seis telas de fatia 1 — a guarda
`test_toda_rota_do_produto_esta_coberta_ou_excluida` exigia a
classificação das três rotas novas.

`scripts/medir_identificacao_do_emitente.py`/`scripts/test_medir_
identificacao_do_emitente.py`: `TELAS_MINIMAS_LIVRO_CAIXA_COM_
IDENTIFICACAO_ESPERADAS` ganhou `livro_caixa_web:carne_leao_mensal` e
`livro_caixa_web:carne_leao_anual` (mesmo marcador CSS do relatório
Livro Caixa) — `dependentes_carne_leao` (formulário de cadastro, não
documento de conferência) fica de fora, de propósito.

### Verificação

Rodada original (antes da integração com o servidor corrigido):

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 305 arquivos já formatados.
- `python manage.py check` — nenhum problema.
- `python manage.py migrate` — aplicado com sucesso em PostgreSQL vazio
  (`dl046f2t`), sem migração nova nesta etapa (só telas).
- `pytest` (suíte completa): 3239 passed, 1 failed (pré-existente, fora
  do escopo — `test_versao_minima_python.py`), 46 skipped.
- Capturas 1440×900 e 390×844 (Chromium local) das três telas. Sem
  estouro horizontal em nenhuma das seis — o estouro medido inicialmente
  no demonstrativo anual (846px em vez de 390px) foi corrigido pelo
  invólucro de rolagem antes da captura final.

Rodada desta integração (2026-09-27, mesmo dia, depois do merge do
servidor corrigido — DE-091), repetida do zero:

- `ruff check .` — **sem apontamentos** (`All checks passed!`).
- `ruff format --check .` — **305 arquivos já formatados**.
- `python manage.py check` — **nenhum problema** (`System check
  identified no issues`).
- `python manage.py makemigrations --check --dry-run` — **nenhuma
  migração pendente** (`No changes detected`) — confirma que nenhuma
  mudança desta etapa deveria ter mexido em modelo, e nenhuma mexeu.
- `python manage.py migrate` — aplicado com sucesso contra o banco
  `dl046f2t` (as seis migrações de `livro_caixa`, incluindo as duas da
  correção da rodada 1 da fatia 2, já aplicadas; nada pendente).
- `pytest` (suíte completa, rodada limpa — sem outro processo
  concorrendo pelo mesmo banco): **3293 passed, 1 failed (pré-existente,
  fora do escopo — `test_versao_minima_python.py`, ambiente Python 3.13
  em vez do 3.14 esperado pela CI), 46 skipped, 4 subtests passed**, em
  202 s. O único vermelho é a mesma falha de versão de Python já
  registrada antes desta etapa, não uma regressão dela. (Uma execução
  anterior, disparada em paralelo com o instrumento de identificação
  contra o MESMO banco de testes, produziu dois erros de fixture do
  pytest-django — `AssertionError` em `_finalizers` — por disputa de
  conexão entre os dois processos; refeita sozinha, sem paralelismo,
  saiu limpa, confirmando que o erro era de bancada, não do produto.)
- `scripts/test_medir_identificacao_do_emitente.py` com
  `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3` (o
  próprio ambiente do projeto tinha Playwright instalado nesta rodada,
  apesar do comentário do script sobre a venv não ter) e
  `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`: **136 passed** em 502 s (0:08:22).
- `scripts/medir_identificacao_do_emitente.py`, contra banco descartável
  PostgreSQL novo (`dl046f2t_instrumento`, criado do zero nesta rodada e
  confirmado por `DL_CONFIRMO_BANCO_DESCARTAVEL`), com `scripts/semear_
  base_de_medicao.py` rodado antes: **código de saída 0** — as telas
  derivadas medidas nesta rodada (`contabilidade_web:balanco`,
  `contabilidade_web:dre`, `livro_caixa_web:carne_leao_anual`,
  `livro_caixa_web:carne_leao_mensal`, `livro_caixa_web:relatorio`,
  entre outras da execução completa) saem **PASSOU**, inclusive as duas
  do carnê-leão com a tabela anual de 10 colunas — confirma que o ajuste
  de CSS do item "Achado de CSS adicional" (abaixo) resolveu o corte que
  a rodada anterior não tinha.
- Capturas 1440×900 e 390×844 das três telas (`docs/assets/telas/dl046/
  carne-leao-mensal-*.png`, `carne-leao-anual-*.png`, `carne-leao-
  dependentes-*.png`), conferidas de novo nesta rodada com `file`: as
  seis batem exatamente com a largura pedida (1440px ou 390px); as
  telas não mudaram nesta rodada (só os testes), então as capturas da
  rodada anterior continuam válidas.
- Percurso por teclado: não testado com leitor de tela real (limite
  declarado da direção de arte, §7 — nenhuma tela do produto foi testada
  assim até hoje). Inspecionei a marcação: toda célula de valor tem
  `class="valor-monetario"` (guardado por
  `test_todo_valor_em_celula_usa_a_classe_do_sistema`, que reprovou uma
  vez durante esta etapa — corrigido), todo `<th>` tem `scope`, o botão
  "Salvar" do formulário de dependentes é `<button>` nativo (focável e
  ativável por teclado sem atributo extra), e os links de navegação de
  competência são `<a class="botao">` (mesmo padrão da DRE).

### Não testado / bloqueado

O achado material do critério de escolha da forma (DE-091) e os campos
novos do contrato (`rendimentos` por código, `faixa_aplicada`/
`vigencia_tabela_inicio`, `imposto_com_exterior`/`sem_exterior`,
`vencimento` pronto, `alertas`, totais anuais estruturados, PATCH de
dependentes, aviso do art. 42 do aluguel, `ImpostoExteriorSemRendimento
Exterior`) — que ficavam pendentes de integração na rodada anterior —
**estão resolvidos** nesta etapa (ver "Integração com o servidor
corrigido", acima) e saem da lista. O que segue genuinamente sem
verificar:

- Leitor de tela real (NVDA/VoiceOver) — limite declarado da direção de
  arte, não desta etapa.
- Firefox/Safari — só Chromium testado, mesmo limite declarado.
- `pwsh ./scripts/validate-docs.ps1` — `pwsh` não existe neste ambiente
  (confirmado de novo nesta rodada).
- Validação profissional dos textos/rótulos da memória de cálculo,
  inclusive do texto NOVO de `criterio_escolha_forma` e do aviso do
  art. 42 do aluguel — do Fred.
- Auditoria independente da versão INTEGRADA (servidor `dl046-f2` +
  tela `dl046-f2-tela`, depois do merge) — ainda não solicitada (nível
  de risco 1: cálculo de imposto e documento entregue ao cliente; é do
  `auditor-qa`, conforme o plano desta fatia). A rodada 1 da auditoria
  (DE-091) avaliou o SERVIDOR antes deste merge; esta integração ainda
  não passou por uma rodada própria.

## Correção da reconferência da fatia 2 — servidor (2026-09-27, `desenvolvedor-pleno`)

A [reconferência](../auditorias/2026-09-27-dl-046-fatia2-reconferencia.md)
**reprovou** a versão integrada (um achado ALTO novo na impressão do anual,
R-A1, que é da `especialista-frontend`; cinco achados MÉDIOS). Não há
terceira rodada (AGENTS.md §3.1): o fechamento é por verificação
independente dos itens mínimos, decididos em
[DE-092](../projeto/decisoes.md#de-092).
Esta seção cobre só a parte do **servidor** (motor, serviço, modelo e
restrições); a parte da tela é do `especialista-frontend`, noutro worktree.

### Item a item da DE-092 (parte do servidor)

1. **R-M4/item 1 — HI-38 revista.** Imposto pago no exterior num mês SEM
   rendimento sujeito de fonte no exterior NÃO bloqueia mais a apuração — a
   versão da rodada 1 levantava `ImpostoExteriorSemRendimentoExterior` (HI-38),
   e como a apuração de qualquer mês encadeia desde janeiro (RC-130), a
   recusa de UM mês bloqueava o RESTO do ano-calendário inteiro (achado da
   reconferência: maio, setembro e o anual de 2026 recusavam todos). A P&R
   IRPF 2026 prevê justamente esse caso (pagamento em mês posterior ao
   rendimento) como compensável no mês do próprio pagamento. `_apurar_um_mes`
   parou de levantar a exceção; a compensação DAQUELE pagamento já sai zero
   pela própria fórmula (a diferença entre o imposto "com" e "sem" um
   rendimento do exterior de R$ 0,00 é sempre R$ 0,00 — a mesma propriedade
   matemática que a rodada 1 já tinha provado para o `saldo_credito_exterior_
   novo`), e um alerta em linguagem simples avisa o aproveitamento na
   declaração anual. `ImpostoExteriorSemRendimentoExterior` continua
   **definida** (nunca mais levantada) só porque a tela do carnê-leão
   (`views_web.py`, outro worktree) ainda a importa e a captura — removê-la
   quebraria esse import; reportado ao arquiteto-senior, que decide se a tela
   deve parar de importá-la numa etapa futura. Teste:
   `test_rec_r_m4_hi38_nao_bloqueia_meses_seguintes_nem_o_anual` (maio,
   setembro e o anual do cenário da reconferência),
   `test_rec_api_mes_com_imposto_exterior_sem_rendimento_nao_bloqueia`.
2. **R-M1/item 2 — alerta.** Passou a disparar só quando
   `rendimento_total_sujeito < 0` (não mais quando a dedução escolhida supera
   o rendimento, que é o caso comum e disparava em quase todo mês — achado da
   reconferência: 11 de 12 meses de um cenário real). Negativo formatado
   entre parênteses, sem sinal de menos (RC-90). A ORM nunca produz
   `rendimento_total_sujeito` negativo (nenhuma combinação de lançamento e
   estorno no MESMO mês soma menos que zero); o alerta é defesa, testada
   forçando o valor em `agregados`, fora do ORM. Testes:
   `test_rec_r_m1_sem_alerta_em_mes_vazio`,
   `test_rec_r_m1_sem_alerta_com_rendimento_de_500`,
   `test_rec_r_m1_sem_alerta_com_estorno_no_mesmo_mes`,
   `test_rec_r_m1_alerta_so_quando_rendimento_sujeito_negativo`.
3. **R-M2/item 3 — sem identificador interno nem jargão.** Tiradas as
   referências `(RC-130)` (recusa do estorno, `services.py`) e `(HI-35)`
   (dia ≠ 1, `models.py`); a mensagem de duplicidade de competência dos
   dependentes (`models.py`, `restricoes.py`) trocou "use a retificação
   (PATCH)" por "use Retificar" (o nome do botão na tela, conforme a
   reconferência mediu). Teste de varredura:
   `test_rec_r_m2_sem_identificador_interno_nas_mensagens` (exercita
   `TabelaCarneLeaoNaoConfigurada`, `DependentesCarneLeaoInvalido`,
   `ValidationError` do modelo, a mensagem de `restricoes.py`,
   `LancamentoCaixaInvalido` do estorno em quatro cenários, e os textos de
   `criterio_escolha_forma`/`alertas` de um mês normal — nenhum casa
   `\b(RC|HI|DE|PE|BL|DL)-\d+` nem contém "PATCH").
4. **N9 (R-M5/item 5) — estorno de outro mês.** A recusa em si já existia
   (M-4 da rodada 1), mas não tinha teste — o mutante N9 sobrevivia à suíte.
   Teste: `test_rec_n9_estorno_em_outro_mes_recusado` (o caso exato da seção
   6 da reconferência: receita de 10/01/2026, R$ 6.000,00; estorno com data
   explícita de março → `LancamentoCaixaInvalido`; sem data explícita →
   estorno de 10/01, janeiro com rendimento e imposto 0,00).
5. **R-B5/item 5 (parte do motor) — `deducao_aplicada` por mês.**
   `_apurar_um_mes` passou a devolver `deducao_aplicada` (a dedução da forma
   ESCOLHIDA) em cada mês, mensal e anual; `_totais_anuais` passou a ler esse
   campo em vez de repetir a regra "simplificado? desconto : deduções reais"
   (a duplicação entre o motor e a tela, cada um com a sua cópia da regra,
   foi a causa do mutante N21 escapar na tela — a correção da TELA é do
   `especialista-frontend`, noutro worktree). A citação "P&R IRPF 2026,
   pergunta 267" para a frase "mais vantajoso" estava ERRADA — a fonte certa
   é "Exemplos de Aplicação da Lei 15.270/2025" (a P&R não traz essa frase);
   corrigida no comentário do motor. Testes:
   `test_rec_r_b5_deducao_aplicada_por_mes`,
   `test_rec_r_b5_deducao_aplicada_pela_forma_real`.
6. **R-B3/item 5 — guarda da redução a partir de 2026.** Ausência de
   vigência de redução vira `TabelaCarneLeaoNaoConfigurada` para qualquer
   competência a partir de 2026-01-01; a ausência continua LEGÍTIMA (sem
   erro) só ANTES disso (2025, Lei 15.270/2025, art. 8º). A versão da rodada
   1 aceitava a ausência para QUALQUER mês (bug: a reconferência mediu
   imposto MAIOR em silêncio ao apagar a vigência de 2026 e apurar mar/2026
   sem erro). Testes: `test_rec_r_b3_reducao_ausente_em_2026_levanta`,
   `test_rec_r_b3_reducao_ausente_em_2025_continua_legitima`.
7. **R-B4/item 5 (parte do motor) — memória completa.** Cada mês passou a
   devolver `valor_por_dependente` (além de `dependentes_valor`, já
   existente), `reducao_vigente` (booleano — `False` só nos meses de 2025,
   quando a ausência é legítima) e `imposto_exterior_nao_compensavel` (a
   parte do pagamento do mês que passa do limite e nunca compensa, com
   rótulo próprio — antes só desaparecia sem nome). Testes:
   `test_rec_r_b4_memoria_traz_valor_por_dependente_e_vigencia`,
   `test_rec_r_b4_reducao_vigente_marcada_por_mes`, e o próprio
   `test_rec_r_m4_hi38_nao_bloqueia_meses_seguintes_nem_o_anual` (item 1)
   cobre o rótulo do não compensável.
8. **R-B6/item 5 — trava da empresa na retificação.** `retificar_
   dependentes_carne_leao` passou a travar a linha da EMPRESA
   (`select_for_update`) além da linha do registro — a mesma corrida N6 que
   `registrar_dependentes_carne_leao` já fechava, agora fechada também na
   retificação. Concorrência REAL não foi testada (mesma limitação
   declarada do A24 desde a rodada 1) — só a trava em si, exercitada pelos
   testes de retificação já existentes (nenhum quebrou).

### Efeito colateral esperado e reportado: dois testes de TELA quebram

O item 1 muda o CONTRATO da apuração para um caso que a tela (outro
worktree, `dl046-f2-tela`) já tinha teste fixando o comportamento ANTIGO
(409 para o mesmo cenário). Os dois testes ficam vermelhos — **não foram
alterados**, por instrução explícita (a tela é do `especialista-frontend`):

- `apps/livro_caixa/tests/test_dl046_telas_carne_leao.py::
  test_carne_leao_mensal_imposto_exterior_sem_rendimento_e_erro_nao_500`
  (esperava 409, recebe 200 — o cenário não é mais erro).
- `apps/livro_caixa/tests/test_dl046_telas_carne_leao.py::
  test_carne_leao_anual_imposto_exterior_sem_rendimento_e_erro_nao_500`
  (mesmo motivo, no anual).

### Arquivos alterados

`apps/livro_caixa/carne_leao.py`, `apps/livro_caixa/services.py`,
`apps/livro_caixa/models.py`, `apps/livro_caixa/views.py`,
`apps/core/restricoes.py`,
`apps/livro_caixa/tests/test_dl046_fatia2_carne_leao.py`. Nenhuma migração
(todas as mudanças são de código, sem alteração de esquema).

### Não testado / bloqueado nesta correção

- Concorrência real na retificação de dependentes (R-B6) — mesma limitação
  declarada do A24.
- Os dois testes de tela listados acima (fora do meu escopo; a correção é
  da `especialista-frontend`).
- `pwsh ./scripts/validate-docs.ps1` — mesmo bloqueio de ambiente.
- Validação profissional do Fred sobre o texto do novo alerta (item 1) e a
  leitura conservadora que ele descreve.

  tela `dl046-f2-tela`, depois do merge) — **atualização (mesmo dia)**:
  esta auditoria aconteceu — é a reconferência de
  `docs/auditorias/2026-09-27-dl-046-fatia2-reconferencia.md` — e
  **REPROVOU**, por um achado ALTO novo (R-A1, corte de impressão no
  demonstrativo anual) e cinco achados MÉDIOS. Ver a seção "Correção da
  reconferência da fatia 2 — tela", abaixo, para a resposta item a
  item. Não há terceira rodada (AGENTS.md §3.1); o fechamento é por
  verificação independente dos seis itens mínimos que a reconferência
  listou.

## Correção da reconferência da fatia 2 — tela (2026-09-27, `especialista-frontend`)

A reconferência (`docs/auditorias/2026-09-27-dl-046-fatia2-reconferencia.md`,
REPROVADA, DE-092) encaminhou seis itens para esta função: **R-A1**
(ALTO), **R-M2** (parte da tela), **R-M3**, **R-B1**, **R-B2** e **N21**.
Os itens **R-M1**, **R-M2** (mensagens do motor/serviço), **R-M4** (que
depende de decisão sobre o alcance da recusa da HI-38) e **R-B3** a
**R-B6** são do `desenvolvedor-pleno`, em outro worktree (`dl046-f2`),
integrados depois por quem coordena. Nenhum arquivo de servidor
(`carne_leao.py`, `models.py`, `services.py`, `views.py` da API,
`restricoes.py`, migrações) foi tocado nesta correção.

**N21 não foi corrigido nesta rodada** — a reconferência também o
encaminhou a esta função, mas ele depende de `deducao_aplicada` por mês
vir do MOTOR (R-B5 do relatório: hoje `_deducao_aplicada_do_mes_para_tela`,
em `views_web.py`, repete a regra de `_deducao_aplicada_do_mes` do motor —
é exatamente essa repetição que deixa a coluna "Dedução aplicada" vulnerável
a divergir se um dos dois lados mudar sozinho) — a integração dessa
mudança de contrato é do `arquiteto-senior`/`desenvolvedor-pleno`, mesma
combinação de N21/R-M4 mencionada no pedido desta rodada.

### R-A1 (ALTO) — o demonstrativo anual impresso cortava "Imposto devido" e "Valor a pagar"

**Diagnóstico, medido de novo no Chromium real antes de corrigir:** a
tabela de dez colunas tinha largura NATURAL de 1.197px (medida com
`scrollWidth`), contra 794px de largura útil A4 com margem 0mm e 698px
com margem 12,7mm — o mesmo número que a reconferência publicou. A causa
raiz tinha DUAS camadas, as duas medidas antes de escrever qualquer CSS:

1. `.tabela-dados th.cabecalho-numerico { min-width: var(--largura-
   minima-coluna-valor) }` (8rem/128px) — com OITO colunas numéricas
   nesta tabela, o PISO sozinho já somava quase 1.024px, antes de
   qualquer conteúdo. Reduzir só esse mínimo (mesmo padrão já usado por
   `.tabela-dre`/`.tabela-lancamentos-caixa` na tela, achado da fatia 1)
   ajudou, mas não bastou sozinho.
2. O NÚMERO mais largo do ano de teste (`5.042.937,01`, doze caracteres
   monoespaçados, `.valor-monetario { white-space: nowrap }` — nunca
   quebra linha) continuava maior que qualquer mínimo reduzido, porque
   `table-layout: auto` nunca encolhe uma coluna abaixo do conteúdo
   MAIS LARGO que ela precisa mostrar sem cortar.

**Duas opções, a decisão documentada no CSS (`static/css/base.css`,
comentário junto à regra):**

- **Paisagem só para o anual (`@page` nomeada)** — testada e
  **descartada**: `page.pdf()` (Playwright/Puppeteer, a chamada que
  `scripts/medir_identificacao_do_emitente.py` e o método da
  reconferência usam) só dá prioridade ao `@page { size: ... }` do CSS
  quando o CHAMADOR passa `preferCSSPageSize: true` — nenhuma das
  chamadas deste projeto passa essa opção, e não está ao alcance da
  `especialista-frontend` mudar o instrumento de medição para passá-la.
  Depender de uma opção de exportação que ninguém neste projeto liga é
  uma correção que PARECE funcionar (o PDF continuaria saindo A4
  RETRATO na prática) e não funciona na verificação real — descartada
  antes de escrever qualquer `@page` nova.
- **Tipografia de impressão, escopada a esta tabela** (escolhida): dois
  tokens NOVOS em `:root` (`--tipo-print-tabela-larga`, 9px, e
  `--esp-print-tabela-larga`, 2px — ambos abaixo do menor token
  existente, `--tipo-2xs`/`--esp-1`, com o comentário explicando por
  que o piso existente não bastava) aplicados só à classe
  `.tabela-carne-leao-anual` (nova, só nesta tabela) dentro de `@media
  print`, mais `min-width: 0` nos `cabecalho-numerico` dela — as três
  mudanças JUNTAS, nenhuma sozinha.

**Medido depois da correção**, com uma base sintética de 12 meses de
2025 e rendimento mensal acima de R$ 1.000.000,00 (duas empresas, uma
delas escalada para o "Valor a pagar" do ano passar de R$ 5.000.000,00):
tabela caindo para 650–659px — cabe com folga nos dois cenários de
margem (698px e 794px), **zero** célula fora da largura útil nos oito
casos medidos (2 empresas × mensal/anual × 2 margens); `pdftotext`
(`-layout`) mostra "5.042.937,01", "78.306,88" e "2.574,06" inteiros —
nenhum valor cortado. O demonstrativo MENSAL (tabela de duas colunas)
já cabia antes e continua cabendo; não precisou de nenhuma regra nova.

**Teste automatizado** (pedido explícito da reconferência):
`test_carne_leao_anual_impresso_todas_as_colunas_cabem_na_folha`, em
`scripts/test_medir_identificacao_do_emitente.py` (mesma infraestrutura
de dois intérpretes da seção "ponta a ponta" já existente nesse
arquivo — `DL_PYTHON_DO_SISTEMA`, `DL_CHROMIUM_EXECUTAVEL`,
`pytestmark_ponta_a_ponta`, reaproveitando `medir_impressao.
_com_css_local` para abrir o HTML renderizado pelo Django via `file://`
sem precisar de servidor rodando). Cria um cenário sintético próprio
(12 meses de 2025, valores ≥ R$ 1.000.000,00), renderiza o anual pela
rota real, mede no DOM sob `emulate_media("print")` (nenhuma célula com
`right` além de 794px/698px) e confirma no `pdftotext` de cada margem
que os totais do ano (lidos do PRÓPRIO motor, `apurar_carne_leao_anual`,
nunca hardcoded) aparecem por inteiro. Vive junto dos testes ponta a
ponta porque usa a MESMA infraestrutura, mas é um teste PRÓPRIO — nunca
uma extensão do instrumento genérico, que continua medindo só a
identificação do emitente, não células de dados (limite M3/BL-445,
documentado na docstring do instrumento).

### R-M2 (parte da tela) — nenhum identificador interno nem "PATCH" no texto visível

Três ocorrências em `templates/livro_caixa/carne_leao_mensal.html`
removidas do texto VISÍVEL (nenhuma delas tinha uma substituição por
citação de norma necessária — os parágrafos ao redor já citam a norma
certa, ou o identificador não acrescentava nada que o texto em
linguagem simples não dissesse):

- linha do rendimento total sujeito: "(RC-132)" removido;
- "Limite da dedução do livro-caixa (DE-091)" → "Limite da dedução do
  livro-caixa (RIR/2018, arts. 68 e 69)" — trocado pela NORMA, não só
  removido, porque esta frase é a única do parágrafo que fundamenta o
  número;
- parágrafo da redução da Lei 15.270/2025: "(RC-133)" removido — o
  título da seção já cita "Lei nº 15.270/2025".

Em `templates/livro_caixa/dependentes_carne_leao.html`, o parágrafo de
apresentação perdeu "— HI-35: só a quantidade, sem cadastro nominal
NESTA FATIA" → "— apenas a quantidade, sem cadastro nominal" (also
tirou "nesta fatia", jargão de projeto, não de produto).

Em `apps/livro_caixa/views_web.py`, o `help_text` do campo "Vigente a
partir de (mês)" perdeu "(HI-35)".

**O que ficou de fora, de propósito, e por quê:** quatro mensagens que
a reconferência também encontrou nascem em arquivo de SERVIDOR fora do
escopo desta correção — a mensagem de `ImpostoExteriorSemRendimento
Exterior` ("...HI-38, requisitos.md...", `carne_leao.py`), a de dia
diferente de 1 ("...(HI-35).", `models.py`) e a de duplicidade de
competência ("...use a retificação (PATCH)...", `restricoes.py`/
`models.py`). Cinco testes novos de varredura
(`test_sem_identificador_interno_*`, `apps/livro_caixa/tests/
test_dl046_telas_carne_leao.py`) renderizam as três telas em sucesso
(passam limpo) e os três estados de erro citados (marcados
`@pytest.mark.xfail(strict=True)`, com o motivo nomeado apontando o
arquivo de servidor exato) — `strict=True` para que, se alguém corrigir
a mensagem do lado do servidor sem tirar a marca, o teste vire XPASS e
quebre a suíte, forçando tirar a marca em vez de deixar a correção
passar despercebida. Nenhuma mensagem do servidor foi reescrita por
esta função.

### R-M3 — rótulos duplicados de "limite da dedução do livro-caixa"

As duas linhas "— do qual, trabalho não assalariado (limite da dedução
do livro-caixa)" e "— do qual, notarial e de registro (limite da
dedução do livro-caixa)" (que descrevem um valor da BASE do carnê-leão,
não do limite do livro-caixa) trocaram o parêntese para "(integra a
base)" — a frase "limite da dedução do livro-caixa" passa a aparecer
uma ÚNICA vez na memória de cálculo, na linha que realmente é sobre o
limite ("Receita da atividade").

### R-B1 — faixa "X a sem limite" na última faixa da tabela progressiva

`carne_leao_mensal.html`, memória de deduções reais e de desconto
simplificado: quando a faixa aplicada não tem limite superior
(`tem_limite_superior` falso), o texto mudou de "{limite inferior} a
sem limite" para "a partir de {limite inferior}" — usa só o dado que a
tela já tinha (`limite_inferior_ptbr`, vindo do motor), sem calcular
nenhum valor novo (não citei "4.664,68"/"acima de", que exigiria
subtrair um centavo do limite inferior — um cálculo que esta tela não
faz). Quando HÁ limite superior, o texto ganhou o prefixo "de" ("de X a
Y"), por simetria.

### R-B2 — CAEPF sem máscara

Máscara `999.999.999/999-99` (composição documentada pela HI-31: 9
dígitos do CPF do titular + 5 do "resumido" da inscrição, sem dígito
verificador conhecido — a Receita não publica o algoritmo, então nenhum
DV é inventado) aplicada nos DOIS partials de identificação do
documento (`_identificacao_do_documento_carne_leao.html`, do carnê-leão,
e `_identificacao_do_documento.html`, do Livro Caixa, fatia 1 — os dois
recebem `caepf` do MESMO contexto, `views_web.py`). Nova função
`_mascara_caepf` (`views_web.py`, ao lado de `_mascara_cpf`/
`_mascara_cnpj`, mesmo padrão), aplicada nos três pontos do módulo que
montam o contexto de identificação (`livro_caixa_relatorio`,
`carne_leao_mensal`, `carne_leao_anual`). Testes atualizados para
esperar o valor MASCARADO (nunca os 14 dígitos crus) em
`test_dl046_telas_carne_leao.py` e `test_dl046_telas_livro_caixa.py`
(este último ganhou também uma asserção negativa: os dígitos crus NÃO
aparecem no HTML).

### R-B5 (item da tela) — docstring e afirmação do plano desatualizadas

- Docstring de `carne_leao_anual` (`views_web.py`) corrigida: citava
  `_totais_anuais_carne_leao`, função REMOVIDA na integração anterior
  (a view não soma nada — só formata `resultado["totais"]` do motor).
- A seção "Testes" deste plano (acima) dizia que
  `ImpostoExteriorSemRendimentoExterior` virava estado de erro **400**
  — o código sempre devolveu **409**; corrigido no texto, com nota
  explicando o engano.

### Verificação

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — todos os arquivos já formatados.
- `pytest apps/livro_caixa/tests/test_dl046_telas_carne_leao.py
  apps/livro_caixa/tests/test_dl046_telas_livro_caixa.py
  apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py`:
  **150 passed, 4 xfailed** (os quatro documentados acima, mensagens de
  servidor fora de escopo).
- `pytest scripts/test_medir_identificacao_do_emitente.py`, com
  `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3` e
  `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`: **137 passed** (136 já existentes + o teste novo
  `test_carne_leao_anual_impresso_todas_as_colunas_cabem_na_folha`).
- `python manage.py check`/`makemigrations --check --dry-run` — sem
  apontamento (nenhum modelo tocado nesta correção).
- `scripts/medir_identificacao_do_emitente.py` — resultado da rodada
  anterior preservado (esta correção não mexeu no bloco de
  identificação em si, só na largura da tabela de dados ao redor dele).
- `pytest` (suíte completa, sem as variáveis do Playwright — a mesma
  execução que a CI roda por padrão): **3296 passed, 1 failed
  (pré-existente — `test_versao_minima_python.py`, Python 3.13 em vez
  de 3.14), 47 skipped, 4 xfailed, 4 subtests passed**. O único
  vermelho é a mesma falha de versão já registrada antes desta etapa; o
  skip a mais, em relação à rodada anterior, é o teste novo de R-A1
  pulando sem as variáveis de Playwright (a mesma classe dos demais
  testes "ponta a ponta" já existentes).
- Capturas 1440×900 e 390×844 das três telas recapturadas nesta rodada
  (os rótulos mudaram — R-M2/R-M3/R-B1/R-B2): larguras conferidas com
  `file`, as seis batem exatamente 1440px ou 390px.

### Não testado / bloqueado nesta correção

**Atualização (mesmo dia, depois do merge do servidor corrigido):** os
itens abaixo — R-M1, a parte de R-M2 sobre mensagens do motor/serviço,
R-M4, N21 e R-B3 a R-B6 — estavam bloqueados/pendentes NESTA lista até
o `arquiteto-senior` integrar o servidor corrigido
(`dl046-f2`→`dl046-f2-tela`, merge `089f8ee`) e pedir a última parte da
tela. **Todos os itens que dependiam do servidor estão resolvidos** —
ver a seção "Correção final da reconferência — R-A1 (paisagem), R-M4,
N21, R-B4", abaixo. Ficam:

- Firefox/Safari, leitor de tela real — mesmos limites já declarados.
- Validação profissional dos textos trocados (normas citadas em vez de
  identificador interno; "integra a base"; "a partir de X"; os novos
  textos de alerta/R-B4) — do Fred.
- Fechamento por verificação independente (nível de risco 1, sem
  terceira rodada) — ainda não realizado; é responsabilidade de quem
  coordena/audita a versão integrada final.

## Correção final da reconferência — R-A1 (paisagem), R-M4, N21, R-B4 (2026-09-27, `especialista-frontend`)

O `arquiteto-senior` integrou o servidor corrigido neste worktree (merge
`089f8ee`, `dl046-f2` → `dl046-f2-tela`) e pediu a última parte da tela:
R-A1 com MUDANÇA DE RUMO (paisagem, não mais tipografia reduzida), R-M4
(a HI-38 antiga vira alerta, não erro), N21 (dedução aplicada do motor) e
R-B4 (memória completa: valor por dependente, vigência, "sem redução
vigente", "imposto exterior não compensável"). Mesmos arquivos
permitidos; nenhum arquivo de servidor tocado.

### R-A1 — mudança de rumo: paisagem, não tipografia de 9px

A rodada anterior tinha escolhido tipografia reduzida a 9px, ABAIXO do
piso de legibilidade que o próprio instrumento usa
(`TAMANHO_MINIMO_RENDERIZADO_PX = 11`, `scripts/medir_identificacao_
do_emitente.py`) — e é o valor que o CLIENTE paga. O `arquiteto-senior`
corrigiu o rumo: a paisagem, descartada na rodada anterior por uma
suposta limitação de `page.pdf()` sem `prefer_css_page_size`, na
verdade funciona — medido de novo, no MESMO Chromium do instrumento
(`/opt/pw-browsers/chromium-1194`), a ORIENTAÇÃO (retrato/paisagem) de
`@page { size: ... }` já é respeitada por `page.pdf(format="A4")` SEM
nenhuma opção especial; só o TAMANHO EXATO da folha depende de
`prefer_css_page_size`. O erro da rodada anterior foi generalizar de
"tamanho" para "orientação" sem medir os dois separadamente.

**Implementado:**

- `@page carne-leao-anual-paisagem { size: A4 landscape; }`
  (`static/css/base.css`, junto do `@page` padrão) — página NOMEADA,
  nunca global.
- `body.pagina-carne-leao-anual-impressao { page: carne-leao-anual-
  paisagem; }`, dentro de `@media print` — a propriedade `page`
  PRECISA estar no `<body>` (ou outro elemento de topo); aplicada num
  elemento aninhado (testei na própria `<table>`) NÃO propaga a
  orientação para a folha inteira, medido.
- `{% block classe_body %}pagina-carne-leao-anual-impressao{% endblock
  %}`, só em `carne_leao_anual.html` — nenhuma outra tela herda a
  classe.
- Os dois tokens novos da rodada anterior (`--tipo-print-tabela-larga`,
  9px, e `--esp-print-tabela-larga`, 2px) foram REMOVIDOS. A paisagem
  sozinha não bastava para o ano com os valores mais altos
  (`5.042.937,01`) — sobrava a última coluna fora da folha —, mas a
  combinação de MÍNIMO de coluna mais estreito (`--largura-minima-
  coluna-valor-estreita`, 4,5rem/72px, MESMO token que `.tabela-dre`/
  `.tabela-lancamentos-caixa` já usam) resolveu sem precisar de
  nenhuma fonte abaixo de 11px: `.tabela-carne-leao-anual th.
  cabecalho-numerico { min-width: var(--largura-minima-coluna-valor-
  estreita); }`. Medido: tabela cai de 1.197px para 978–1.105px,
  dentro do orçamento de largura útil em paisagem (1.026px com margem
  12,7mm; 1.122px com margem 0mm) — a fonte da tabela continua a
  PADRÃO do produto (`--tipo-sm`/13px no corpo, `--tipo-2xs`/11px no
  cabeçalho), nenhum token novo.

**Achado cross-cutting, fora do escopo desta correção, REGISTRADO aqui
para quem for verificar ou usar as mesmas ferramentas em outro
documento:** o Chromium 141.0.7390.37 (binário `/opt/pw-browsers/
chromium-1194`) exportado via `page.pdf()` do Playwright **não aplica
a mídia "print" corretamente quando a margem passa de ~1mm** —
reproduzido de forma isolada e determinística: margem 0mm e 1mm saem
CORRETAS (barra lateral/menu escondidos, como o CSS manda); margem
5mm, 10mm, 12mm, 13mm e 12,7mm saem TODAS com a barra lateral
("DataLedger."/"Menu") visível no PDF exportado, mesmo com
`emulate_media("print")` já ativo — testado com e sem
`prefer_css_page_size`, com e sem `print_background`, com `format` e
com `width`/`height` explícitos, em DOIS documentos (mensal retrato,
anual paisagem): o comportamento é sempre o mesmo, e é do EXPORTADOR
de PDF, não do CSS do produto — uma captura de TELA (`page.
screenshot()`, não `page.pdf()`) sob a MESMA `emulate_media("print")`
sai perfeitamente correta em qualquer margem, confirmando que a folha
de estilo está certa.

Isto **não invalida** a verificação de R-A1 desta correção: a checagem
de "cabe na largura útil" (a pergunta que importa) é feita no DOM, via
`emulate_media("print")` + `getBoundingClientRect()` — que NUNCA passa
por `page.pdf()` e por isso não sofre este defeito —, e o CONTEÚDO
(totais) continua saindo íntegro no `pdftotext` mesmo nos PDFs com a
barra lateral poluindo o topo (conferido linha a linha: "5.042.937,01"
sai inteiro nos dois). Mas **é um risco para qualquer evidência
VISUAL** tirada de um PDF exportado com margem não-zero neste
ambiente: a imagem do PDF em paisagem pedida para esta entrega
(`docs/assets/telas/dl046/carne-leao-anual-paisagem-pdf.png`) foi
gerada com margem **0mm** de propósito, por ser a única que sai limpa
neste binário. `scripts/medir_impressao.py` (MODOS_DE_IMPRESSAO,
modo "com-cabecalho") usa margem 10mm — dentro da faixa que reproduz o
defeito — e é o script cujas funções o instrumento de identificação
reaproveita para a paginação do Balancete/Diário/Razão; não investiguei
se os números de paginação já publicados foram afetados (não é desta
correção, e o arquivo não está nos meus permitidos), só registro o
achado para o `arquiteto-senior` decidir se vale investigar.

**Verificado** (base sintética de 12 meses com valores ≥ R$ 1.000.000,00,
mesma técnica da rodada anterior): as quatro combinações (2 empresas ×
2 margens) saem com **zero** célula fora da largura útil em paisagem,
fonte medida em 11px (nunca abaixo), e PDF em paisagem confirmado por
`pdfinfo` (842×596pt, mais largo que alto) nos dois margens. `pdftotext`
mostra "5.042.937,01", "78.306,88" e "VALOR A / PAGAR" inteiros. O
demonstrativo MENSAL (sem `@page` nomeada) continua em retrato — sem
regressão.

**Teste automatizado atualizado**
(`test_carne_leao_anual_impresso_todas_as_colunas_cabem_na_folha`,
`scripts/test_medir_identificacao_do_emitente.py`): viewports de medição
recalculados para paisagem (1.122px/1.026px), `prefer_css_page_size=True`
nos dois `page.pdf()` do subprocesso, e uma nova asserção de tamanho de
fonte (`tamanho_fonte_px >= instrumento.TAMANHO_MINIMO_RENDERIZADO_PX`)
lida da MESMA constante que o instrumento já declara, nunca um número
novo escrito à parte.

**`prefer_css_page_size=True` também em `scripts/medir_identificacao_
do_emitente.py`:** testado empiricamente ANTES de aplicar — rodei o
instrumento completo (13 telas) com e sem a opção, contra a MESMA base
sintética, e comparei os dois JSONs de saída: a ÚNICA diferença é o
nome da pasta temporária (aleatório a cada execução); nenhuma medida,
veredito ou contagem mudou para NENHUMA tela. Seguro de manter — a
opção só passa a ter efeito quando o documento declara `@page` PRÓPRIO
(hoje, só o anual do carnê-leão).

### R-M4 — imposto pago no exterior sem rendimento do exterior vira alerta

O motor não levanta mais `ImpostoExteriorSemRendimentoExterior` (DE-092
item 1) — o mês apura normalmente, com um alerta. A tela:

- removeu a captura da exceção nas duas views (`carne_leao_mensal`,
  `carne_leao_anual`) e o import (não sobrou nenhum uso; a classe
  continua existindo no motor por compatibilidade, mas a tela não a
  importa mais);
- o comentário do bloco de erro (`{% if erro_configuracao %}`) foi
  reescrito — não é mais "dois motivos possíveis", só um
  (`TabelaCarneLeaoNaoConfigurada`).

**Testes reescritos**
(`test_carne_leao_mensal_imposto_exterior_sem_rendimento_vira_alerta_
nao_erro`, `test_carne_leao_anual_imposto_exterior_sem_rendimento_vira_
alerta_nao_erro`): maio (o mês do pagamento) apura com 200 e o alerta
visível (`.mensagem-warning`); setembro (mês seguinte, sem NENHUM
lançamento de imposto exterior) apura com 200 e SEM alerta — prova que
a recusa antiga não vaza mais para os meses seguintes (o próprio achado
da reconferência: a recusa bloqueava o resto do ano-calendário inteiro,
porque a apuração encadeia desde janeiro); o anual mostra os 12 meses,
sem erro.

### N21 — "Dedução aplicada" do anual vem do motor

`_deducao_aplicada_do_mes_para_tela` (a seleção "simplificado? desconto
: deduções reais" que a TELA reimplementava) foi REMOVIDA de
`views_web.py`; `_linha_anual_carne_leao` agora lê `mes_resultado
["deducao_aplicada"]` direto — o motor devolve o campo pronto, desde a
correção do servidor (a mesma regra que `_totais_anuais` já usava para
o total do ano).

**Teste novo** (`test_tela_anual_deducao_da_forma_aplicada`), com o
cenário exato da reconferência (fev/2026: trabalho PF R$ 6.000,00,
previdência R$ 100,00 → desconto simplificado R$ 607,20, MAIOR que a
dedução real de R$ 100,00 → forma simplificado). **Mutante aplicado
VIVO e confirmado, não só descrito**: troquei `mes_resultado
["deducao_aplicada"]` por `mes_resultado["deducoes_reais_total"]` em
`_linha_anual_carne_leao` e rodei o teste — FALHOU, mostrando 100,00 em
vez de 607,20 na célula de fevereiro (evidência capturada no log desta
sessão); revertido antes do commit. Os dois valores foram escolhidos de
propósito bem DIFERENTES (607,20 contra 100,00) para o teste não passar
por coincidência numérica caso os dois algoritmos dessem o mesmo
resultado num cenário mais ameno.

### R-B4 — memória completa

Três acréscimos à memória de cálculo mensal (`_contexto_resultado_
mensal_carne_leao`/`carne_leao_mensal.html`), todos formatação/exibição
de campos que o motor já devolve (`valor_por_dependente`, `reducao_
vigente`, `imposto_exterior_nao_compensavel`) — nenhum cálculo novo:

1. **Valor por dependente e vigência**: a linha "Dependentes" mostra
   `{quantidade} × {valor por dependente}`, com a data de vigência
   desse valor num `texto-apoio` — antes só o total (quantidade ×
   valor) aparecia, sem o FATOR.
2. **"Sem redução vigente"**: quando `reducao_vigente` é falso
   (legítimo só antes de 2026-01-01, R-B3), a linha da redução diz
   isso explicitamente, em vez de deixar "0,00" parecer um cálculo que
   deu zero.
3. **"Imposto pago no exterior acima do limite (não compensável)"**:
   nova linha na seção de compensação do exterior, só quando
   `imposto_exterior_nao_compensavel > 0` — a parte do pagamento que
   NUNCA compensa neste mês (passa do limite) tinha ficado sem rótulo
   próprio; agora aparece, com a mesma explicação do alerta de R-M4
   (pode ser aproveitada na declaração anual).

**Três testes novos**: um para cada acréscimo, com cenários dedicados
(inclusive um com rendimento do exterior e imposto pago bem acima do
limite de compensação, para forçar `imposto_exterior_nao_compensavel >
0` de verdade, não um valor forçado).

### Verificação

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 305 arquivos já formatados.
- `python manage.py check` / `makemigrations --check --dry-run` — sem
  apontamento.
- `pytest apps/livro_caixa/tests/test_dl046_telas_carne_leao.py` —
  **43 passed**, ZERO `xfail` restante (os dois que sobreviviam da
  rodada anterior — dia≠1 e duplicidade — viraram XPASS com o servidor
  corrigido; as marcas foram removidas, não deixadas quebrando a
  suíte à toa).
- `pytest` (suíte completa, sem as variáveis de Playwright — a mesma
  execução que a CI roda por padrão): **3312 passed, 1 failed
  pré-existente (`test_versao_minima_python.py`), 47 skipped, ZERO
  xfail**.
- `pytest scripts/test_medir_identificacao_do_emitente.py`, com
  `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3` e
  `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`: **137 passed**.
- `scripts/medir_identificacao_do_emitente.py`, contra banco
  descartável PostgreSQL novo, semeado por `semear_base_de_medicao.py`:
  **código de saída 0** — as 13 telas derivadas (8 com timbre, 2 de
  classe 2, 3 do Livro Caixa) saem PASSOU, com `prefer_css_page_size=
  True` já aplicado (testado idêntico ao resultado sem a opção, exceto
  o nome da pasta temporária).
- Capturas 1440×900/390×844 das três telas (mensal/anual/dependentes)
  recapturadas: larguras conferidas, as seis batem 1440px ou 390px.
- Nova captura: `docs/assets/telas/dl046/carne-leao-anual-paisagem-
  pdf.png` — primeira folha do PDF do demonstrativo anual, margem 0mm
  (a única confirmada limpa neste Chromium — ver o achado acima),
  confirmado em paisagem por `pdfinfo` e visualmente (sem "DataLedger."
  nem "Menu", 10 colunas visíveis).

  ⚠️ **Correção (verificação independente do fechamento, 2026-09-27,
  achado (a) abaixo)**: a afirmação acima, "totais completos", estava
  IMPRECISA — o cenário usado para capturar aquela imagem (`gestor-
  captura-cl`/"Fulano de Tal", só março com lançamento) não tinha
  volume suficiente para expor o defeito de paginação que existia
  então; a imagem em si só mostrava a PRIMEIRA folha de um PDF que,
  com 12 meses de dados de valor alto, saía em DUAS folhas — com o
  "TOTAL DO ANO" sozinho na segunda, fora da imagem capturada. Nenhum
  total estava de fato "completo" nesse sentido — só não fazia parte
  do que a imagem mostrava. Corrigido e recapturado na correção
  seguinte (achado (a) abaixo).

### Não testado / bloqueado nesta correção

- Firefox/Safari, leitor de tela real — mesmos limites já declarados.
- Validação profissional dos textos novos (alertas de R-M4, rótulos de
  R-B4) — do Fred.
- Investigar se a paginação já publicada de Balancete/Diário/Razão
  (`scripts/medir_impressao.py`, modo "com-cabecalho", margem 10mm) foi
  afetada pelo achado do exportador de PDF — fora do escopo desta
  correção e do meu arquivo permitido; só registrado.
- Fechamento por verificação independente (nível de risco 1, sem
  terceira rodada) — realizado depois desta correção; achou três
  pontos novos, corrigidos na seção seguinte.

## Correção dos achados da verificação independente do fechamento (a/b/c, 2026-09-27, `especialista-frontend`)

Mesmo worktree/branch/banco desta etapa. A verificação independente do
commit anterior (`b2d27eb`) confirmou os 6 itens mínimos da correção de
R-A1/R-M4/N21/R-B4 (seção acima), e trouxe três achados novos.

### (a) DEFEITO — "Total do ano" sozinho na segunda folha

Com 12 meses de dados de valor alto (base >= R$ 1.000.000,00/mês —
`_criar_cenario_carne_leao_anual_sintetico`, `scripts/test_medir_
identificacao_do_emitente.py`), o demonstrativo anual saía em DUAS
folhas: a primeira terminava em dezembro sem nenhum total visível; a
segunda só tinha o cabeçalho de identificação repetido (`<thead>`,
`display: table-header-group`) e a linha "TOTAL DO ANO", sozinha.

**Causa raiz nº 1 — bug de paginação do Chromium, não de conteúdo.**
"Total do ano" morava num `<tfoot>` próprio. Isolado por eliminação
(bancada, scripts descartáveis, não versionados): reduzir todo o
respiro de impressão a zero e relaxar `break-inside`/`break-before` na
linha do total NÃO resolviam a paginação em dois — medido por DOM e
por captura de tela que o conteúdo cabia com folga na altura útil da
folha. Só desligar a página NOMEADA em paisagem (`page: auto`, voltando
ao `@page` padrão) resolvia a paginação sozinho — mas isso sacrifica a
paisagem que R-A1 exige. A explicação que sobrou, e a única testada com
sucesso: é um comportamento específico deste Chromium ao combinar
`page: <nome>` com um `<tfoot>` próprio nesta tabela — mover a linha do
total para DENTRO do `<tbody>`, como última linha, eliminou a
paginação em dois com a página nomeada continuando ativa. Ver o
comentário completo em `templates/livro_caixa/carne_leao_anual.html`.

**Causa raiz nº 2 — altura real, uma vez resolvida a causa nº 1.** A
mudança acima sozinha resolveu o cenário usado na rodada anterior desta
etapa (identificação de uma linha só), mas NÃO o cenário oficial da
reconferência (CAEPF soma uma segunda linha ao bloco de identificação,
repetido a cada folha pelo `<thead>`) — ainda saía em duas folhas,
agora por ALTURA de verdade. Reduzido respiro de impressão (padding da
faixa de contexto, margem do timbre, tipografia da identificação do
documento para `--tipo-2xs`/11px — o MESMO piso de legibilidade de
sempre, nunca abaixo), tudo escopado a `body.pagina-carne-leao-anual-
impressao` — nenhuma outra tela muda de respiro por causa desta
correção. A fonte da TABELA DE DADOS continua em 11px, sem alteração.

**Teste novo** (mesmo arquivo do teste de R-A1):
`test_carne_leao_anual_impresso_total_do_ano_nunca_fica_sozinho_na_
pagina` — `pdftotext -f N -l N` por página: a página que tem
"Dezembro" tem "TOTAL DO" (marcador escolhido por causa de como
`pdftotext -layout` reconstrói a célula "Total do ano", que quebra em
duas linhas — ver o comentário no teste), e nenhuma página tem o total
sem nenhum mês junto.

### (b) DECISÃO (arquiteto-senior) — mês sem rendimento sujeito

`desconto_simplificado` (motor) é um TETO da tabela — percentual do
limite da faixa zero, calculado sobre a TABELA, nunca sobre o
rendimento do mês — por isso é positivo mesmo sem nenhum rendimento
sujeito, e sempre "vence" a comparação contra R$ 0,00 de deduções
reais. Sem tratamento, tanto o anual quanto o mensal mostravam esse
valor como se tivesse sido de fato deduzido de uma renda que não
existiu (ex.: "Dedução aplicada 607,20" num mês sem nenhum lançamento).

Só apresentação — o motor não mudou. Regra isolada num único ponto,
`_mes_sem_rendimento_sujeito(mes_resultado)` (`views_web.py`),
reaproveitado pelas duas telas (nunca reescrito): anual mostra "—" nas
colunas "Dedução aplicada" e "Forma", com "Sem movimento" ao lado do
mês; mensal mostra "Sem rendimento sujeito no mês" na linha "Forma
aplicada neste mês", em vez do nome da forma. O TOTAL do ano continua
somando o valor verdadeiro que o motor calculou para aquele mês — só a
CÉLULA muda, nunca a soma (comentário em `carne_leao_anual.html`).

Dois testes novos: `test_carne_leao_anual_mes_sem_rendimento_mostra_
travessao_e_sem_movimento` e `test_carne_leao_mensal_sem_rendimento_
mostra_aviso_em_vez_de_deducao_enganosa`. Os dois foram MATADOS por
mutante (bancada, revertido antes do commit): forçar
`_mes_sem_rendimento_sujeito` a sempre devolver `False` faz os dois
falharem, mostrando "607,20"/"Desconto simplificado" em vez do aviso.

### (c) DEFEITO de CSS — link azul no papel

`.barra-lateral ~ .area-principal a:not(.botao)` (especificidade 0-3-1,
regra de TELA) vencia, na impressão, a regra `a { color: var(
--impressao-tinta) }` (especificidade 0-0-1, dentro de `@media
print`). `.barra-lateral` continua no DOM mesmo escondida no papel
(`display: none` não remove do DOM; o combinador `~` só olha
estrutura) — então QUALQUER link de conteúdo saía AZUL (`--app-
acento`) no PDF exportado, em qualquer documento do produto, não só o
carnê-leão.

Corrigido por EMPATE de especificidade dentro de `@media print`: o
MESMO seletor da regra de tela, que ganha por ORDEM de declaração (o
bloco `@media print` vem depois no arquivo) — sem precisar de
`!important` nem de um seletor mais específico que o necessário (mesma
técnica que a correção de `.botao--primario` × esta mesma regra já usa,
comentário logo acima dela). Regra GERAL — `.area-principal` é o
`<div>` que `templates/base.html` usa para todo conteúdo de página,
qualquer módulo.

**Teste novo**: `test_link_de_conteudo_sai_em_tinta_de_impressao_nunca_
azul` (`scripts/test_medir_identificacao_do_emitente.py`) — sob
`emulate_media("print")`, mede a cor computada (`getComputedStyle`) de
um link de conteúdo em DOIS documentos de módulos diferentes (o mês do
demonstrativo anual do carnê-leão, e a conta do Balancete que leva ao
Razão) — os dois precisam sair `rgb(0, 0, 0)`. Morto por mutante:
removendo a regra nova, o link do carnê-leão media `rgb(10, 88, 202)`
(exatamente `--app-acento`).

### Achado cross-cutting confirmado de novo (não desta correção)

A nota do arquiteto-senior ("margem > ~1mm no `page.pdf()` deste
Chromium vaza a barra lateral no PDF") confirma, de forma
independente, o achado já registrado na seção anterior (bug do
EXPORTADOR de PDF, não da folha de estilo — `page.screenshot()` sob a
mesma emulação de impressão sai correto em qualquer margem). Nenhuma
mudança nova motivada por ele nesta correção — só a evidência visual
(imagem do PDF) continua usando margem 0mm, como já vinha sendo feito,
e está declarado aqui de novo por transparência.

### Verificação (a/b/c)

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 305 arquivos já formatados.
- `python manage.py check` — sem apontamento.
- `pytest` (suíte completa, banco `dl046f2t`): **3314 passed, 1 failed
  pré-existente (`test_versao_minima_python.py`, Python 3.13 vs. 3.14 —
  já aceita nas rodadas anteriores), 49 skipped, ZERO xfail**.
- `pytest scripts/test_medir_identificacao_do_emitente.py`, com
  `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3` e
  `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`: **139 passed** (137 da rodada anterior + os 2 testes novos
  desta correção, achados (a) e (c)).
- `scripts/medir_identificacao_do_emitente.py` (instrumento standalone,
  contra banco descartável PostgreSQL novo `rf46_instr`, semeado por
  `semear_base_de_medicao.py`, DEPOIS da correção (c)): **código de
  saída 0** — as 13 telas derivadas saem PASSOU, ZERO FALHOU — nenhuma
  tela regrediu com a correção do link.
- Nova captura: `docs/assets/telas/dl046/carne-leao-anual-paisagem-
  pdf.png` recapturada com o cenário oficial da reconferência (12
  meses de 2025, valores >= R$ 1.000.000,00, CAEPF de 2 linhas) — 1
  folha só (`pdfinfo`: `Pages: 1`), "Dezembro" e "TOTAL DO ANO"
  visíveis juntos na mesma folha, confirmado por `pdftotext` e
  visualmente; margem 0mm (a única confirmada limpa neste Chromium —
  achado cross-cutting registrado na seção anterior).

### Não testado / bloqueado nesta correção

- Mesmos itens já declarados na seção anterior (Firefox/Safari/leitor
  de tela real; validação profissional dos textos; paginação de
  Balancete/Diário/Razão no modo "com-cabecalho" do exportador).
- Uma quarta rodada de verificação independente, se pedida.

## Verificação do fechamento da fatia 2 (sem terceira rodada de auditoria)

AGENTS.md §3.1 não prevê terceira rodada. A versão `b2d27eb` (servidor e
tela, depois da reconferência) foi conferida pelo `auxiliar-verificacao`, de
forma independente, em 2026-09-27, contra os seis itens mínimos da seção 8
da [reconferência](../auditorias/2026-09-27-dl-046-fatia2-reconferencia.md):

- **R-A1:** anual em A4 paisagem nas margens 0 e 12,7 mm; nenhuma célula
  fora da largura útil; fonte mínima de 11px; todos os totais inteiros no
  `pdftotext`; mensal em retrato sem regressão. Fechado.
- **R-M1:** sem alerta em mês vazio, com 500,00 e com estorno no mesmo mês.
  Fechado.
- **R-M2:** nenhum identificador interno nem "PATCH" nos oito PDFs e nas
  mensagens de erro. Fechado.
- **R-M3:** o texto do limite do livro-caixa aparece uma única vez.
  Fechado.
- **R-M5:** os mutantes N9 e N21 morrem. Fechado.
- **R-M4:** pagamento no exterior sem rendimento do exterior gera alerta em
  maio, e setembro e o anual apuram normalmente. Fechado.
- Suíte completa (3312 passed, só a falha conhecida de Python 3.13), lint,
  formatação, `check`, `makemigrations --check`, migração em banco vazio,
  testes do instrumento (137 passed) e o instrumento (saída 0, 13 telas).

**Achados da verificação, fora dos seis itens**, confirmando o que o
`arquiteto-senior` viu na captura do PDF:

1. **Defeito:** com 12 meses, o anual impresso saía em duas páginas e a linha
   "Total do ano" ficava sozinha na segunda; a primeira página não tinha
   total. O teste de R-A1 passava porque lia o texto do PDF inteiro.
2. **Decisão de apresentação (`arquiteto-senior`):** mês sem rendimento
   sujeito mostrava "Dedução aplicada 607,20" com base zero. Passa a mostrar
   "—" e "Sem movimento"; o motor não muda.
3. **Defeito:** links saíam azuis no papel, porque uma regra de tela vencia a
   regra de impressão por especificidade — em todos os documentos, não só no
   carnê-leão.
4. **Ambiente:** o `page.pdf()` do Chromium local, com margem acima de ~1 mm,
   deixa a barra lateral aparecer no PDF. Os valores não mudam; evidência
   visual de PDF deste ambiente é gerada com margem 0.

Os três primeiros foram corrigidos no commit `76781ec`, pela
`especialista-frontend`, com teste para cada um (o do total confere o texto
**por página**) e prova de mutação. Registro da correção na seção
"Correção final da reconferência" acima.
