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
   de limite para a dedução do livro-caixa?** **Não entra, exceto
   notarial.** RIR/2018, art. 118, caput, restringe a base a rendimento
   recebido de OUTRA PESSOA FÍSICA ou de fonte do EXTERIOR; o inciso IV é
   explícito para aluguel ("recebidos de pessoas físicas"). A Lei nº
   7.713/1988, art. 8º, §1º, estende o caput aos emolumentos/custas de
   serventuários da Justiça SEM restringir a fonte pagadora — só esse
   modelo (notarial) integra a base vindo de PJ. Rendimento de PJ fora
   desse caso é tributado por retenção na fonte pela própria fonte
   pagadora, fora do escopo desta fatia. Como consequência, PJ também não
   entra no limite da dedução do livro-caixa (que só se aplica ao
   rendimento que É base do carnê-leão). Registrado como **RC-132**, junto
   com a imunidade da pensão alimentícia recebida (STF, ADI 5.422, citada
   no Perguntas e Respostas IRPF 2026, pergunta 266).
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
| Dois testes que já existiam tinham valores calculados com a fórmula ERRADA (base) | Recalculados com a fórmula CORRETA (bruto), conferidos via shell antes de gravar no comentário | `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`, `test_apuracao_le_valor_do_banco_nao_de_constante` (este também passou a mirar `memoria_deducoes_reais.reducao_aplicada` em vez do campo do topo, porque a rendição bruto ≤ R$ 5.000,00 SEMPRE escolhe a forma simplificada — a mutação de `reducao_maxima` só é visível na memória da forma perdedora) |

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

### Achado material registrado, não corrigido nesta etapa (mensagem do
### arquiteto-senior, 2026-09-27, DE-091)

Durante a integração, o `dev-carne-leao` corrigiu (outro worktree,
`dl046-f2`, ainda não integrado aqui) o CRITÉRIO de escolha entre
deduções reais e desconto simplificado: de "menor imposto após a redução
da Lei 15.270/2025" (o que este worktree calcula, HI-33/RC-133, com os
cinco exemplos oficiais da Receita batendo) para "maior dedução antes da
redução" (achado M-1 da auditoria da fatia 2 do servidor, docs/auditorias/
2026-09-27-dl-046-fatia2-rodada-1.md — os exemplos oficiais da Receita
comparam DEDUÇÕES, não o imposto final; os dois critérios só divergem no
empate, porque a redução depende só do bruto — igual nas duas formas — e
o imposto é monotônico na base).

**Eu não escrevi esse critério na tela** (nem no texto explicativo nem em
lugar nenhum): imprimir um critério que o motor DESTE worktree não aplica
seria a mesma classe de defeito que a direção de arte proíbe — "o
documento diz com que critérios foi gerado", e o critério impresso tem
que ser o REAL. Isolei o texto "Forma aplicada neste mês" — MENOR
imposto..." numa constante única (`_CRITERIO_ESCOLHA_FORMA_TEXTO_PADRAO`,
`views_web.py`) e no contexto correspondente
(`criterio_escolha_forma_texto`), lida com `resultado.get("criterio_
escolha_forma", _CRITERIO_ESCOLHA_FORMA_TEXTO_PADRAO)`: o motor corrigido
vai devolver `criterio_escolha_forma` (texto PRONTO) nesse dicionário —
na integração, a chave aparece e o texto novo troca sozinho, sem editar o
template (`carne_leao_mensal.html`, comentário lá aponta para este
mesmo parágrafo).

**Aviso do art. 42 (RIR/2018) para aluguel** e os campos adicionais
(`rendimentos` por código, `imposto_com_exterior`/`sem_exterior`,
`vencimento` pronto, `alertas`, totais anuais estruturados do motor,
PATCH de dependentes) — combinados na mesma mensagem — ainda não
existem no contrato deste worktree; ficam para a integração (mensagem
do arquiteto-senior registrada, não implementados aqui para não deixar
código contra um campo inexistente).

### Achado próprio: o motor não expõe "rendimentos por código" nem
### "faixa/alíquota/parcela do imposto pela tabela"

A tarefa pedia "rendimentos sujeitos (por código)" e "imposto pela
tabela (faixa e parcela)". `apurar_carne_leao_mensal` só devolve as
CATEGORIAS agregadas (`rendimento_total_sujeito`, `rendimento_trabalho_
nao_assalariado`, `rendimento_exterior_sujeito`) e o imposto FINAL pela
tabela (`imposto_pela_tabela`), sem o detalhamento por código individual
nem a faixa/alíquota/parcela usada. Reconstruir esse detalhamento na
view exigiria repetir, fora do motor, a classificação por código
(RC-132) e a busca de faixa (`_faixa_da_base`) — o "cálculo na view" que
a tarefa proíbe. A tela mostra as categorias que o motor de fato
devolve, nomeadas com precisão (nunca "por código" quando é "por
categoria"). Registrado para o `arquiteto-senior`/`desenvolvedor-pleno`
decidirem se o motor ganha os dois campos numa etapa futura — a mensagem
do arquiteto-senior sobre o campo `rendimentos` (lista por código) na
correção do servidor sugere que sim.

### Testes

`apps/livro_caixa/tests/test_dl046_telas_carne_leao.py` (21 testes):
renderização do mês com a memória de cálculo completa (identificação,
rótulos, valores), forma aplicada marcada com `.selo` no lugar certo
(nunca nas deduções reais quando o simplificado venceu), mês sem
movimento (aviso de estado, não de erro), competência/ano inválidos
(400, formulário/estado reexibido), navegação de competência, anual (12
meses + totais, ano inválido), isolamento entre escritórios (404) nas
três telas, recusa para empresa em modo contabilidade (403) nas três,
papel sem permissão de leitura (403, `Papel.CLIENTE`) nas três,
formulário de dependentes (sucesso, erro de dia≠1, sem permissão de
escrita — `Papel.PARALEGAL` lê mas não escreve), e número de consultas
CONSTANTE (mensal: poucos x muitos lançamentos no mês; anual: um mês x
nove meses com movimento — não 12, porque `criar_lancamento_caixa`
recusa data além de "hoje + 30 dias" e o ambiente de teste roda em
2026-09-27).

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

- `ruff check .` — sem apontamentos.
- `ruff format --check .` — 305 arquivos já formatados.
- `python manage.py check` — nenhum problema.
- `python manage.py migrate` — aplicado com sucesso em PostgreSQL vazio
  (`dl046f2t`), sem migração nova nesta etapa (só telas).
- `pytest` (suíte completa): **3239 passed, 1 failed (pré-existente,
  fora do escopo — `test_versao_minima_python.py`, ambiente Python 3.13
  em vez do 3.14 esperado pela CI), 46 skipped**.
- `scripts/test_medir_identificacao_do_emitente.py` com
  `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3` e
  `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/
  chrome`: **136 passed**.
- `scripts/medir_identificacao_do_emitente.py`, contra banco descartável
  PostgreSQL (`dl046f2t_instrumento`, confirmado por
  `DL_CONFIRMO_BANCO_DESCARTAVEL`), com `scripts/semear_base_de_
  medicao.py` rodado antes: **código de saída 0** — as 13 telas
  derivadas (8 com timbre, 2 de classe 2, 3 do Livro Caixa) saem com a
  identificação completa, inclusive as duas novas do carnê-leão.
- Capturas 1440×900 e 390×844 (Chromium local, mesmo binário do
  instrumento) das três telas: `docs/assets/telas/dl046/carne-leao-
  mensal-*.png`, `carne-leao-anual-*.png`, `carne-leao-dependentes-
  *.png`. Sem estouro horizontal em nenhuma das seis — medido (largura
  do PNG exportado bate com a largura pedida: 1440px e 390px nas seis);
  o estouro medido inicialmente no demonstrativo anual (846px em vez de
  390px) foi corrigido pelo invólucro de rolagem (achado do item 6,
  acima) antes da captura final.
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

- Leitor de tela real (NVDA/VoiceOver) — limite declarado da direção de
  arte, não desta etapa.
- Firefox/Safari — só Chromium testado, mesmo limite declarado.
- `pwsh ./scripts/validate-docs.ps1` — `pwsh` não existe neste ambiente.
- Validação profissional dos textos/rótulos da memória de cálculo — do
  Fred.
- O achado material do critério de escolha da forma (DE-091) e os
  campos novos do contrato mencionados pelo arquiteto-senior
  (`rendimentos` por código, `imposto_com_exterior`/`sem_exterior`,
  `vencimento` pronto, `alertas`, totais anuais estruturados, PATCH de
  dependentes, aviso do art. 42 do aluguel) — ficam para a integração
  entre `dl046-f2` (servidor) e `dl046-f2-tela` (esta etapa); o ponto de
  troca no código está isolado e comentado (`criterio_escolha_forma_
  texto`, `_CRITERIO_ESCOLHA_FORMA_TEXTO_PADRAO`, `views_web.py`).
- Auditoria independente desta tela — ainda não solicitada (nível de
  risco 1: cálculo de imposto e documento entregue ao cliente — a
  auditoria da versão INTEGRADA, servidor+tela, é do `auditor-qa`,
  conforme o plano desta fatia).
