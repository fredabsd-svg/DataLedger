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
- **Antes de codificar a redução da Lei 15.270/2025 no carnê-leão**, confirmar
  na fonte integral que ela se aplica ao recolhimento mensal (PE-71).

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
        "valor": "1500.00",
        "historico": "Honorários de janeiro",
        "documento_origem": "",
        "estorno_de_id": null,
        "e_estorno": false
      }
    ],
    "total_entradas": "1500.00",
    "total_saidas": "0.00",
    "saldo": "1500.00"
  }
  ```

- Todas as rotas recusam (400, corpo `{"empresa": ["..."]}`) para empresa em
  modo contabilidade. `403` para papel sem autorização; `404` para empresa de
  outro escritório.
