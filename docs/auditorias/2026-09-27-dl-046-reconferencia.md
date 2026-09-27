# Reconferência independente — DL-046 fatia 1 (livro-caixa do cliente pessoa física)

- **Data:** 2026-09-27
- **Auditor:** `auditor-qa`, sem delegação a auxiliares
- **Versão auditada:** worktree `wt-dl046`, branch `dl046-livro-caixa`, HEAD `92c6850e8e5e72f422c7b06e546e0bf91e17e1eb`, conferido com `git rev-parse HEAD`. Árvore limpa antes e depois (`git status --short` e `git diff --stat` vazios). Diferença desde a rodada 1 (`6d99fb0..HEAD`): 27 arquivos, +2505/-104.
- **Escopo:** reconferência única da fatia 1 (AGENTS.md §3.1). As fatias 2 e 3 estão **fora do escopo**.
- **Nível de risco:** 1.
- **Método:** tudo rodou em cópias descartáveis, nunca no worktree:
  - cópias `git archive` do HEAD, para os experimentos;
  - clones `git clone` do HEAD, para a suíte, os mutantes e a impressão;
  - bancos próprios `dataledger_qa46r*`.

  Foram feitos: suíte completa, lint, formatação, `check`, `makemigrations --check`, migração e reversão em PostgreSQL e SQLite, experimentos de caixa-preta e de concorrência com threads, percurso real no Chromium, duas execuções do instrumento de impressão e 52 mutantes.

## Parecer

**REPROVADA.**

Os três achados altos da rodada 1 (A1, A2, A3) estão **fechados**, com reprodução do cenário original. Os 14 mutantes sobreviventes da rodada 1 agora **morrem todos**. A correção, porém, introduziu ou deixou:

- **1 achado de gravidade alta:**
  - **N1:** a tela de lançamento não tem o indicador "CPF do beneficiário não informado". Com a regra de CPF nova, a tela passou a **recusar** todo rendimento recebido de pessoa física sem CPF do beneficiário. Isso inclui aluguel e outros rendimentos, que na rodada 1 eram aceitos e cujo leiaute oficial nem tem campo de CPF. A mensagem de erro manda marcar um controle que não existe.
- **4 achados de gravidade média:**
  - **N2:** a correção de A2 criou uma regressão: 500 com `chave_idempotencia` longa na tela.
  - **N3:** o instrumento de impressão do próprio projeto **REPROVA** o Livro Caixa quando a tabela P20 cai numa folha própria.
  - **N4:** o estorno P20 sai no papel sem sinal e sem referência (M8 parcial).
  - **M5 parcial:** a regra de CPF diverge do leiaute oficial em três das doze linhas dos modelos.

A decisão de produto e a validação contábil e normativa continuam sendo do Fred. Esta auditoria não as substitui.

## Achados da rodada 1 → estado

| Achado | Estado | Evidência (Testado, salvo indicação) |
| --- | --- | --- |
| A1 troca de modo com movimento | **Fechado** (ressalva N6) | Com lançamento, `PATCH /empresas/api/empresas/<id>/ {"modo_escrituracao":"contabilidade"}` dá **400** e o modo continua `livro_caixa`. Só com conta, sem lançamento, também dá **400**. A contraprova sem movimento dá **200**. `Empresa.full_clean()` recusa. No admin, o POST de alteração dá **200** com a mensagem e o modo não muda. Mutantes N01 a N04 mortos. |
| A2 corrida de idempotência | **Fechado** (mas a correção causou N2) | 30 pares em threads, cada uma com conexão própria. Sem barreira: `{(200,201): 30}` com conteúdo igual e `{(201,409): 30}` com conteúdo diferente. Com barreira forçada depois de `full_clean()`: os mesmos números. 60 linhas gravadas (uma por par), nenhum 500, 30 registros `lancamento_caixa.criacao_repetida` com `corrida=True`. |
| A3 alcance das telas | **Fechado** | Percurso real no Chromium, sem digitar URL: Início → "Abrir" → Plano de contas do livro-caixa → menu "Lançamentos" → menu "Livro Caixa" → "Trocar de empresa" (`/empresas/?secao=relatorio`) → "Ações › Continuar aqui" leva ao Livro Caixa de outra empresa em livro-caixa. O mesmo caminho para empresa em contabilidade leva ao plano de contas contábil. Em Empresas, "Abrir" e "Ações › Lançar" funcionam. `trocar-secao` com 9 seções diferentes dá sempre 302 seguido de 200; outro escritório dá 404. |
| M1 `conta` malformada na tela | **Fechado** | `abc`, `1.5`, espaços, `-1`, `9999999999999999999999`, vazio e `0x1` dão **400**, com nada gravado e o formulário preservado. Mutante N29 morto. |
| M2 caractere NUL | **Fechado** | Na API, `codigo` e `nome` da conta e `documento_origem`, `historico`, os dois CPFs e `cnpj_pagador` do lançamento dão 400. Na tela, `documento_origem`, `historico`, `cpf_titular_pagamento` e `cnpj_pagador` dão 400. A tela de conta dá 200 com erro de formulário. |
| M3 conta muda de empresa | **Fechado** | `full_clean()` recusa. No admin, `empresa` é somente leitura: o POST com `empresa=A2` dá 302 e a empresa não muda. A contraprova sem lançamento é aceita. Mutantes N10 e N11 mortos. |
| M4 código do Carnê-Leão mutável | **Fechado** | `full_clean()` recusa com mensagem no campo `codigo_carne_leao`. No admin, dá 200 com erro e o código não muda. O estorno de lançamento antigo depois de renomear e inativar a conta funciona e copia o CPF e o indicador. Mutantes N09 e N14 mortos. |
| M5 regra de CPF × leiaute oficial | **Parcial** | Ver a seção "M5 linha a linha" e o achado N1. |
| M6 inscrição e CAEPF impressos | **Fechado** | No PDF A4 da empresa CPF: "— CPF 123.456.789-09" e "CAEPF 12345678900017". No PDF da empresa CNPJ: "— CNPJ 11.222.333/0001-81". Mutantes N31 e N32 mortos. |
| M7 mutantes sobreviventes | **Fechado** para os 14 | Os 14 morreram. Novos sobreviventes estão em N10. |
| M8 nº e referência do estorno | **Parcial** | Tabela principal: coluna "Nº" presente e "Estorno do lançamento nº 2" no PDF (mutante N30 morto). Tabela P20: estorno sem referência e sem parênteses (N4). |
| B1 conta inativa | **Fechado** | Serviço recusa; API 400; tela 400. O estorno em conta inativa pela tela dá 302 e cria 1 estorno. |
| B2 máscara de CPF e CNPJ | **Fechado** | API com `111.444.777-35` dá 201 e grava `11144477735`. Tela com CNPJ mascarado dá 302. |
| B3 tipos da API de conta | **Fechado** | `codigo` como lista, espaços, número, `null` ou objeto dá 400; `nome`, `natureza` ou `codigo_carne_leao` como lista dá 400; `ativa="nao"` dá 400. |
| B4 estorno de data futura | Aberto **por decisão** (DE-087 item 11) | Inspecionado. |
| B5 ações próprias na trilha | **Fechado** | `lancamento_caixa.estornado` e `lancamento_caixa.criacao_repetida`, esta nas repetições sequencial e concorrente. Mutante N34 morto. |
| B6 consultas | **Fechado no comportamento, sem teste** | Lista da tela: 5 consultas com 1 lançamento e 5 com 41. API paginada (`count`, `next`, `previous`, `results`). Mutantes N33 e N38 **sobrevivem**. |
| B7 imutabilidade por `QuerySet` | Aberto **por decisão** (DE-087 item 11) | Inspecionado. |
| B8 trilha de navegação | **Fechado no comportamento, sem teste** | Trilha "Início › Livro-caixa › <empresa> › Lançamentos" e "… › Livro Caixa". Mutantes N25 e N26 **sobrevivem**. |
| D1 data e sinal do estorno | Registrado como **PE-72** | Inspecionado em `requisitos.md`. |
| D2 base legal | Implementado conforme DE-087 item 12 | No PDF: "Base: RIR/2018 (Decreto 9.580/2018), arts. 68 e 69 (livro-caixa) e 118 a 125 (recolhimento mensal obrigatório)." A adequação normativa é dúvida do Fred. |
| D3 grupo P20 | **Parcial** | Tabela própria "Pagamentos que deduzem a base do carnê-leão — não são despesa de custeio". Ver N3, N4 e N5. |
| D4 (HI-31) e D5 | Hipóteses mantidas | Inspecionado. |
| D6 CNPJ em livro-caixa | Resolvido para impressão pela DE-087 item 7 | Restrição do carnê-leão a CPF: fatia 2, fora do escopo. |

### M5 linha a linha, contra os modelos oficiais (Receita, 2025)

Cada linha dos seis CSV oficiais foi reproduzida como lançamento no serviço. Arquivos consultados: `Modelo de arquivo para rendimentos do Trabalho não Assalariado.csv`, `…Serviços Notariais e de Registro.csv`, `…Aluguel e Outros rendimentos.csv`, `…recibos do Receita Saúde.csv` e as instruções em PDF.

| Linha oficial | Leiaute | Sistema |
| --- | --- | --- |
| R01.001.001 PF, titular e beneficiário | aceita | aceita |
| R01.001.001 PF, titular, sem beneficiário, indicador `S` | aceita | aceita (**só pela API**, ver N1) |
| R01.001.001 PJ com CNPJ | aceita | aceita |
| R01.001.001 EX | aceita | aceita |
| R01.001.002 EX | aceita | aceita |
| R01.001.002 PF com titular; beneficiário "vazio"; indicador "vazio" (instruções, itens 9 e 10 do modelo notarial) | aceita | **recusa** ("Informe o CPF do beneficiário… ou marque…") |
| R01.001.002 PJ | aceita | aceita |
| R01.003.001 PF (aluguel; o leiaute só tem 7 campos, sem CPF) | aceita | **recusa** ("exige o CPF do titular") |
| R01.003.001 EX | aceita | aceita |
| R01.004.001 PF (outros; 7 campos, sem CPF) | aceita | **recusa** |
| R01.004.001 EX | aceita | aceita |
| Receita Saúde R01.001.001 PF com os dois CPFs | aceita | aceita |

Também foram recusados, como devem: PF sem titular; beneficiário informado junto com o indicador; CPF em PJ; CNPJ em EX; CNPJ em PF; indicador em EX. O caso PJ sem CNPJ é **aceito**. Todas as linhas PJ do leiaute trazem CNPJ, então isso fica como **dúvida** para o Fred.

**Conclusão:** o serviço segue literalmente o texto da DE-087 item 6 ("rendimento recebido de PF exige o CPF do titular…; o beneficiário pode faltar desde que marcado o indicador"). Esse texto, porém, generaliza para toda receita uma regra que o leiaute oficial aplica **por modelo**. Detalhes no achado M5 abaixo.

## Achados novos e remanescentes

### N1 — ALTA — A tela não oferece o indicador "CPF do beneficiário não informado"; todo rendimento de PF sem beneficiário passou a ser recusado na interface

1. **Gravidade:** alta.
2. **Requisito afetado:** DE-087 item 6; M5 da rodada 1; "verificar se a interface funciona de verdade"; formulário que orienta o preenchimento.
3. **Local:**
   - `apps/livro_caixa/views_web.py:340-357`: `_CONTRATO_DO_FORMULARIO_DE_LANCAMENTO_CAIXA` não declara `cpf_beneficiario_nao_informado`.
   - `apps/livro_caixa/views_web.py:455-470`: a chamada a `criar_lancamento_caixa` não passa o indicador.
   - `templates/livro_caixa/lancamento_form.html:99-117`: sem o controle. O texto de ajuda ainda diz "Exigido para rendimento do trabalho não assalariado recebido de pessoa física", o que contradiz a regra nova.
   - `apps/livro_caixa/models.py` (`LancamentoCaixa.clean()`, ramo PF): a regra universal.
4. **Evidência (Testado):**
   - A página GET do formulário não contém `cpf_beneficiario_nao_informado`.
   - POST com PF, titular e `cpf_beneficiario_nao_informado=on`: **400**, 0 gravados (recusado como dado não contratado).
   - POST com PF e titular, sem beneficiário: **400**, com a mensagem "Informe o CPF do beneficiário do serviço, ou marque 'CPF do beneficiário não informado'…". Esse controle não existe na tela.
   - **Regressão**, mesma requisição na tela (conta `R01.003.001`, `recebido_de=PF`, sem CPF): no commit da rodada 1 (`1991cf7`) dava **302** e gravava 1 lançamento; no HEAD dá **400** e grava 0.
   - Percurso no Chromium: `[name=cpf_beneficiario_nao_informado]` tem 0 ocorrências no formulário.
5. **Impacto:**
   - Pela interface principal, o contador não consegue registrar o caso oficial "trabalho não assalariado de PF sem CPF do beneficiário".
   - Para aluguel e outros rendimentos recebidos de PF, precisa digitar dois CPFs que o leiaute nem prevê. Isso induz dado inventado num registro fiscal.
   - A decisão do item 6 da DE-087 só está disponível pela API.
6. **Correção recomendada:**
   - `especialista-frontend`: incluir o controle (checkbox) no formulário, no contrato e na chamada ao serviço, preservando-o em caso de erro, e corrigir os textos de ajuda.
   - Resolver junto a regra de M5 (abaixo), porque, se ela continuar universal, a tela continuará exigindo CPF para aluguel de PF.
7. **Como verificar:** teste de tela com PF, titular e indicador marcado (302, gravado com `cpf_beneficiario_nao_informado=True`); teste de tela com aluguel de PF conforme a regra decidida; teste de que o formulário renderiza o controle e o preserva num 400.

### N2 — MÉDIA — Regressão: 500 com `chave_idempotencia` de mais de 255 caracteres na tela (efeito da correção de A2)

1. **Gravidade:** média, a mesma classe de M1 e M2 (500 provocável por POST forjado).
2. **Requisito afetado:** "nenhum 500 para entrada malformada"; DE-087 item 2 ("nunca 500").
3. **Local:**
   - `apps/livro_caixa/services.py:332-334`: `full_clean(exclude={"chave_idempotencia"})` também dispensa a validação de **campo** (`max_length=255` e o validador de NUL), não só a `UniqueConstraint`.
   - `apps/livro_caixa/views_web.py:406`: a chave vem do POST sem limite de tamanho. A API tem o limite (`views.py`, `TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA_CAIXA`); a tela não.
4. **Evidência (Testado, PostgreSQL):**
   - POST na tela com `chave_idempotencia="k"*300`: **500**.
   - No serviço: `django.db.utils.DataError: value too long for type character varying(255)`.
   - O mesmo POST no commit `1991cf7` dava **400**.
   - Contraprova: chave com NUL na tela dá 400 (o serviço confere NUL à mão); chave de 256 caracteres na API dá 400.
5. **Impacto:** erro de servidor provocável. O caminho de corrida trata só `IntegrityError`; `DataError` escapa.
6. **Correção recomendada:** manter a unicidade fora de `full_clean` sem desligar a validação do campo. Duas saídas: `full_clean(validate_constraints=False)` seguido de `validate_constraints(exclude={"chave_idempotencia"})`; ou validar tamanho e NUL da chave no serviço, antes de tudo, para a tela e a API.
7. **Como verificar:** teste de tela e de serviço com chave de 256 e de 300 caracteres: 400 e nada gravado. O mutante N07 (abaixo) deve continuar tratado por teste próprio.

### N3 — MÉDIA — Livro Caixa: a tabela P20 em folha própria sai sem a identificação do contribuinte (instrumento REPROVADO)

1. **Gravidade:** média.
2. **Requisito afetado:** identificação do contribuinte em toda folha impressa (item 6 da tarefa; `docs/projeto/personalizacao-de-relatorio.md`, classe "livro"); DE-087 item 13.
3. **Local:** `templates/livro_caixa/relatorio.html`, bloco `{% if pagamentos_p20_carne_leao %}`. A segunda `<table>` não tem a linha `.linha-identificacao-do-documento` no `<thead>`, que é o que repete a identificação em cada folha.
4. **Evidência (Testado, Chromium 1194, `scripts/medir_identificacao_do_emitente.py`):**
   - Com a semeadura padrão (1 lançamento): saída **0**, tudo PASSOU.
   - Com a empresa de medição enriquecida (CAEPF; 71 receitas, 15 despesas P10, 31 pagamentos P20, 2 estornos): saída **1**, `livro_caixa_web:relatorio: REPROVADO — bloco de identificação do documento AUSENTE em 1 de 6 página(s): folha(s) [6]`.
   - O `pdftotext` da folha 6 começa direto em "Nº DATA CONTA HISTÓRICO VALOR / 90 04/03/2026 3 — Previdência oficial INSS 3 50,00", sem nome, CPF nem período.
5. **Impacto:**
   - Basta a tabela P20 começar numa folha nova. Isso ocorre sempre que a tabela principal termina perto do fim da página, mesmo com 1 ou 2 pagamentos P20.
   - A integração contínua não pega, porque a semeadura do instrumento tem só 1 lançamento de receita.
6. **Correção recomendada:** repetir o cabeçalho de identificação no `<thead>` da tabela P20, ou apresentar o grupo dentro da mesma tabela (seção de `<tbody>`). Incluir P20 e volume suficiente na preparação do instrumento (`_preparar_empresa_livro_caixa`) para que a CI meça esse caso.
7. **Como verificar:** repetir a medição acima (dados de várias folhas, com P20) e obter saída 0 e `folhas_sem_bloco_de_identificacao: []`.

### N4 — MÉDIA — M8 parcial: o estorno de pagamento P20 sai sem parênteses e sem "Estorno do lançamento nº X"

1. **Gravidade:** média.
2. **Requisito afetado:** DE-087 item 8; critério 3 do plano (estorno rastreável); direção de arte §2A (valor invertido entre parênteses); conciliação entre relatório e lançamentos.
3. **Local:** `templates/livro_caixa/relatorio.html`, `<tbody>` da tabela P20. Não trata `item.e_estorno` nem `item.estorno_de_id`.
4. **Evidência (Testado):**
   - HTML: a coluna de valores da tabela P20 lista `['50,00', '50,00']`, ou seja, o original e o estorno iguais. "Estorno do lançamento nº <id>" não aparece para o P20.
   - PDF: `119 28/03/2026 3 — Previdência oficial Estorno do lançamento de caixa 87 50,00`, positivo e sem parênteses. A referência só aparece porque o histórico padrão a contém; um histórico informado a apagaria.
   - A soma literal da coluna P20 dá 1.600,00; o total real do grupo é 1.500,00.
5. **Impacto:** no papel, o estorno de um pagamento dedutível parece um segundo pagamento. É exatamente o que M8 e §2A existem para evitar.
6. **Correção recomendada:** aplicar à tabela P20 o mesmo tratamento da tabela principal (parênteses e referência ao original).
7. **Como verificar:** teste de tela com um P20 estornado: "(50,00)" e "Estorno do lançamento nº <id>" dentro da tabela P20; mesma verificação no PDF.

### M5 (remanescente) — MÉDIA (defeito em relação à fonte citada, com dúvida normativa) — A regra universal de CPF diverge do leiaute oficial em três das doze linhas

1. **Gravidade:** média.
2. **Requisito afetado:** DE-087 item 6 ("CPF segue o leiaute oficial"); RC-127 e RC-128.
3. **Local:** `apps/livro_caixa/models.py`, `LancamentoCaixa.clean()`, ramo `recebido_de == PF`.
4. **Evidência:** tabela "M5 linha a linha" acima.
   - Notarial de PF: o leiaute manda beneficiário e indicador "vazio"; o sistema exige um dos dois.
   - Aluguel e outros rendimentos de PF: o leiaute não tem campos de CPF; o sistema exige o titular e mais o beneficiário ou o indicador.
   - O indicador, pelo leiaute, é "preenchido somente nos casos em que houver a exigência do CPF do beneficiário". O sistema obriga a marcá-lo em códigos onde não há essa exigência.
5. **Impacto:** a escrituração recusa ou força dados que o arquivo oficial não tem. Na fatia 3, isso pode gerar linha com campos que deveriam estar vazios.
6. **Correção recomendada:**
   - `arquiteto-senior`, com o Fred se necessário: rever o texto da DE-087 item 6 para uma regra **por código de rendimento**, como nas instruções.
     - R01.001.001: titular obrigatório; beneficiário ou indicador.
     - R01.001.002: titular obrigatório; beneficiário e indicador vazios.
     - R01.003.001 e R01.004.001: sem CPF.
   - Decidir também se PJ exige CNPJ.
   - A implementação vem depois da decisão.
7. **Como verificar:** um teste por linha dos seis modelos oficiais (as 12 linhas acima), cada uma aceita ou recusada conforme a regra revista, no serviço, na API e na tela.

### N5 — BAIXA — Apresentação do grupo P20: sem total do grupo, "Saídas" soma os dois grupos, e "Nenhum lançamento" aparece com P20 no período

- **Local:**
  - `templates/livro_caixa/relatorio.html`: os cartões mostram só Entradas, Saídas e Saldo.
  - `apps/livro_caixa/views_web.py:739-742`: `total_saidas_custeio_ptbr` e `total_saidas_deducao_carne_leao_ptbr` são calculados e nunca usados no template.
- **Evidência (Testado):**
  - Cartões `['1.000,00', '0,00', '1.000,00']`, sem subtotal de P20 no papel.
  - Com período contendo só um P20, o HTML traz "Nenhum lançamento neste período." e, logo abaixo, a tabela P20 preenchida (`(True, True)`).
- **Impacto:** o livro separa as linhas, mas não o total, que é o dado que a apuração do carnê-leão usará. E a mensagem de vazio contradiz a tabela.
- **Correção:** imprimir "Saídas de custeio" e "Pagamentos P20" (ou total do grupo no rodapé da tabela P20); condicionar a mensagem de vazio aos dois grupos.
- **Verificar:** teste de tela com os dois totais e com período só P20.

### N6 — BAIXA — Corrida entre a troca de modo (A1) e a criação de conta de caixa

- **Local:** `apps/empresas/serializers.py:281-294` e `apps/livro_caixa/services.py:87-122`. É uma checagem de existência sem trava da `Empresa`, e a DE-087 item 1 menciona também o caminho de "gravação", que não ganhou guarda.
- **Evidência (Testado, `transaction=True`, barreira depois da guarda e de `ContaLivroCaixa.full_clean`):** 10 de 10 pares terminaram em `(PATCH 200, POST conta 201)`, com a empresa em `contabilidade` e 1 conta de caixa órfã.
- **Impacto:** exige duas pessoas agindo ao mesmo tempo na mesma empresa. A guarda R6, no sentido oposto, tem o mesmo limite, então é o precedente aceito.
- **Correção:** `select_for_update()` na `Empresa` nos dois caminhos, ou gatilho de banco (padrão das migrações 0010 a 0013 de `empresas`). Registrar como limite, se for aceito.
- **Verificar:** repetir o experimento; espera-se sempre um dos dois recusado.

### N7 — BAIXA — A impressão digital da idempotência ignora `cpf_beneficiario_nao_informado`

- **Local:** `apps/livro_caixa/services.py:52-84`.
- **Evidência (Testado, API):**
  - POST 1 com PF, titular e indicador `true`, chave `kk`: **201**.
  - POST 2 com o mesmo corpo e indicador `false`, mesma chave: **200** (tratado como repetição).
  - O mesmo corpo do POST 2 com chave nova: **400**.
- **Impacto:** corpo inválido devolvido como sucesso de repetição. Entre corpos válidos o indicador é determinado pelos demais campos, por isso a gravidade é baixa.
- **Correção:** incluir o campo na impressão digital.
- **Verificar:** o experimento acima deve dar 409 no segundo POST.

### N8 — BAIXA — Teste instável: `test_plano_de_contas_da_tela_nao_mostra_nada_de_outra_empresa`

- **Local:** `apps/livro_caixa/tests/test_dl046_telas_livro_caixa.py:828` (`assert "RB" not in conteudo`).
- **Evidência (Testado):** em 1000 renderizações da mesma tela, **22** continham "RB" dentro do `csrfmiddlewaretoken` aleatório, por exemplo `value="2oR5lok60tVjo3jRBj1HGo62s…"`. Taxa de falso vermelho de cerca de 2,2% por execução.
- **Impacto:** vermelho intermitente na CI e ruído no teste de mutantes. Uma execução do mutante N06 parou nesse teste.
- **Correção:** asserção sobre um marcador inequívoco (nome da conta de B, `href` com o id da conta de B), nunca sobre uma substring curta.
- **Verificar:** repetir o laço de 1000 renderizações contra a nova asserção.

### N9 — BAIXA — Comentários e variáveis obsoletos

- **Local:**
  - `apps/livro_caixa/views_web.py:715-727`: o comentário afirma "Hoje a chave nunca existe no retorno do serviço, então este bloco é GENÉRICO e INERTE", mas o serviço já marca `grupo` e o bloco está ativo.
  - `views_web.py:685-686`: `cpf_formatado` e `cnpj_formatado` continuam no contexto sem uso no template.
  - Texto de ajuda do formulário (ver N1).
- **Impacto:** documentação que contradiz o código engana o próximo agente.
- **Correção:** remover ou atualizar.

### N10 — BAIXA — Lacunas de teste: 9 mutantes novos sobrevivem

N07, N12, N13, N16, N21, N25, N26, N33 e N38 (ver a tabela). Os mais relevantes:

- **N13:** o estorno pode deixar de copiar o indicador sem nenhum teste falhar. Como o estorno pula a revalidação, gravaria um registro PF sem beneficiário e sem indicador.
- **N25 e N26:** B8 sem teste.
- **N33 e N38:** B6 sem teste de número de consultas.
- **N07:** a janela em que `full_clean` vê a linha da corrida.

**Correção:** os casos propostos abaixo.

### Observação — não é defeito da DL-046: fragilidade de ordem na suíte

- `pytest apps/empresas apps/core/tests/test_dl030_trilha_cobre_o_admin.py` falha com `UndefinedTable: contabilidade_parametrocontabilempresa`.
- A causa: testes de `empresas` revertem para migrações antigas e desaplicam `contabilidade.0008/0009`, que não são reaplicadas. É a mesma classe que a correção resolveu para `livro_caixa`.
- **Pré-existente:** reproduzido no commit base `004e027` (1 failed, 393 passed).
- A suíte completa, na ordem padrão, passa.

## DE-087: as decisões foram seguidas como escritas?

| Item | Situação |
| --- | --- |
| 1 (A1) | Seguido no serializer e em `Empresa.clean()`. O texto cita também "gravação": não há guarda em `save()` nem gatilho, e o plano declara "dois pontos". Limite de corrida em N6. |
| 2 (A2) | Seguido para a corrida. **"Nunca 500" violado** por N2, efeito colateral da própria correção. |
| 3 (A3) | Seguido: Início, lista de empresas, troca de empresa e trilha. |
| 4 (M4) | Seguido: código imutável com lançamento; estorno copia sem revalidar. |
| 5 (M3) | Seguido. |
| 6 (M5) | Seguido **literalmente** no modelo e na API. **Não entregue na tela** (N1). O próprio texto diverge do leiaute oficial que invoca (M5 remanescente). |
| 7 (M6) | Seguido na impressão (CPF, CNPJ, CAEPF). A restrição do carnê-leão a CPF é da fatia 2. |
| 8 (M8) | Seguido na tabela principal; **não** na tabela P20 (N4). |
| 9 (B1) | Seguido. |
| 10 | Seguido para B2, B3, B5, B6, B8, M1 e M2; B6 e B8 sem teste (N10). |
| 11 (B4, B7) | Mantidos como no precedente, conforme decidido. |
| 12 (D2) | Seguido, com o texto exato. |
| 13 (D3) | Grupo próprio implementado. Quebra a identificação por folha (N3), sem total do grupo (N5) e com o estorno sem sinal (N4). |
| 14 | PE-72 registrada. HI-31 mantida. |
| 15 (M7) | Os 14 sobreviventes morreram; o caso proposto 14 foi atendido. |

## Mutantes

### Método

- Clone descartável do HEAD. Um mutante por vez, aplicado por substituição exata de texto, com contagem de ocorrências conferida (todas iguais a 1), e revertido antes do próximo.
- `pytest -x` contra o conjunto `apps/livro_caixa` + `apps/empresas/tests/test_dl046_caepf.py` + `apps/contabilidade/tests/test_dl038_recusa_livro_caixa.py`, que tem **193 testes verdes** (122 na rodada 1; estável em 6 repetições).
- Mutantes de A1 somam `apps/empresas`.
- Mutantes de navegação somam `apps/core/tests`, `apps/tenancy` e `apps/empresas`, com a falha de ambiente conhecida desmarcada (1346 verdes).
- Os mutantes de isolamento foram feitos na versão **mais difícil**: vazamento para empresas do **mesmo escritório** (`empresa__escritorio=…`), não a simples remoção do filtro.

### Sobreviventes da rodada 1: 14 de 14 mortos

| # | Teste que matou |
| --- | --- |
| M04 | `test_m04_api_lista_lancamentos_de_a_nao_contem_nada_de_a2` |
| M05 | `test_lista_de_lancamentos_da_tela_nao_mostra_nada_de_outra_empresa` |
| M06 | `test_m06_apurar_livro_caixa_de_a_nao_contem_nada_de_a2` |
| M07 | `test_m07_api_estorno_de_a_com_id_de_lancamento_de_a2_da_404` |
| M08 | `test_estornar_lancamento_de_outra_empresa_pela_tela_da_404` |
| M09 | `test_plano_de_contas_da_tela_nao_mostra_nada_de_outra_empresa` |
| M16 | `test_m16_codigo_de_rendimento_mal_formado_e_recusado[R01.1.1]` |
| M17 | `test_m17_pf_com_titular_mas_sem_beneficiario_e_sem_indicador_e_recusado` |
| M18 (regras de PF aplicadas também a PJ) | `test_conta_recusa_mudar_natureza_com_lancamento_gravado` (o fixture quebra antes) |
| M19 | `test_m19_caepf_que_difere_do_cpf_so_no_nono_digito_e_recusado` |
| M24 | `test_paralegal_recebe_403_ao_tentar_estornar_pela_tela` |
| M27 | `test_m27_api_recusa_valor_como_numero_json_inteiro` |
| M28 | `test_m28_conta_de_receita_com_lancamento_nao_muda_para_despesa_mesmo_com_codigo_coerente` |
| M32 | `test_m32_estorno_de_despesa_reduz_saidas_sem_alterar_entradas` |

### Mutantes novos: 38, dos quais 29 mortos e 9 sobreviventes

| # | Ponto mutado | Resultado |
| --- | --- | --- |
| N01 | Guarda A1 neutralizada | Morto |
| N02 | Chamada A1 no serializer removida | Morto |
| N03 | Chamada A1 em `Empresa.clean` removida | Morto |
| N04 | A1 ignora conta sem lançamento | Morto |
| N05 | Corrida com mesmo conteúdo vira 409 | Morto |
| N06 | Corrida com conteúdo diferente vira 200 | Morto (a primeira execução parou antes no teste instável N8; reexecução isolada: `test_a2_corrida_de_idempotencia_conteudo_diferente_e_conflito_nunca_500` falha) |
| N07 | Exclusão da chave em `full_clean` removida | **Sobreviveu** |
| N08 | Savepoint removido | Morto (500) |
| N09 | Imutabilidade do código removida | Morto |
| N10 | Guarda de empresa da conta removida | Morto |
| N11 | Admin com `empresa` editável | Morto |
| N12 | Estorno volta a revalidar | **Sobreviveu** (quase equivalente com a regra atual; deixa de ser com dado legado gravado sob a regra antiga) |
| N13 | Estorno não copia o indicador | **Sobreviveu** |
| N14 | Estorno não copia o CPF do titular | Morto |
| N15 | Indicador junto com CPF do beneficiário aceito | Morto |
| N16 | Indicador aceito em PJ/EX | **Sobreviveu** |
| N17 | Conta inativa aceita lançamento novo | Morto |
| N18 | Conta inativa bloqueia estorno | Morto |
| N19 | P20 nunca vai para o grupo próprio (serviço) | Morto |
| N20 | Tabela P20 nunca separada (tela) | Morto |
| N21 | Grupo P20 passa a incluir P11 | **Sobreviveu** |
| N22 | Troca de empresa ignora o modo | Morto |
| N23 | Mapa do livro-caixa sem "relatorio" | Morto |
| N24 | Lista ignora a seção do livro-caixa | Morto |
| N25 | Ramo `livro_caixa_web` da trilha removido | **Sobreviveu** |
| N26 | Rótulo "Livro Caixa" da trilha removido | **Sobreviveu** |
| N27 | "Abrir" do Início aponta para a contabilidade | Morto |
| N28 | "Lançar" do livro-caixa removido da lista | Morto |
| N29 | Tela sem `para_id` (M1) | Morto (500) |
| N30 | Referência do estorno removida do papel | Morto |
| N31 | CNPJ impresso como "CPF" | Morto |
| N32 | CAEPF não impresso | Morto |
| N33 | Cache de empresa volta à chave própria | **Sobreviveu** |
| N34 | Estorno registrado como "criado" | Morto |
| N35 | CPF do titular sem normalizar | Morto |
| N36 | `codigo` sem `strip` | Morto |
| N37 | Base legal antiga | Morto |
| N38 | N+1 na lista (`estornos.exists()` por linha) | **Sobreviveu** |

**Totais:** 52 mutantes, 43 mortos, 9 sobreviventes, todos novos (achado N10).

## Migrações

- **A edição à mão da dependência** (`livro_caixa.0001` → `empresas.0001_initial`) é **segura** quanto à publicação:
  - `git ls-remote --heads origin` listou 33 branches; nenhuma contém `5b3caa1`, o commit que criou a `0001`, e nenhuma é da DL-046.
  - Consulta só de leitura a `django_migrations` mostrou a `livro_caixa.0001` aplicada apenas em bancos locais de desenvolvimento (`dataledger`, `dataledger_dl046`, `dataledger_front46`). Em todos eles `empresas.0001` já está aplicada, então não há histórico inconsistente (Inspecionado, sem migrar esses bancos).
  - Consequência medida e aceitável: com a dependência nova, `migrate empresas 0007` não desaplica mais o `livro_caixa`.
- **PostgreSQL vazio:** `migrate` com saída 0 e **50** linhas `OK`, incluindo `livro_caixa.0001_inicial` e `livro_caixa.0002_rodada1`. Sequência de reversão e reaplicação, toda `OK`:
  1. `migrate livro_caixa 0001` (desaplica a 0002);
  2. `migrate livro_caixa zero`;
  3. `migrate empresas 0013`;
  4. `migrate` (reaplica as três);
  5. `migrate empresas 0007` (9 desaplicações, sem tocar no `livro_caixa`);
  6. `migrate` (9 reaplicações).
- **SQLite vazio** (`DEBUG=True`): 50 `OK`. A mesma sequência de reversão e reaplicação: todas `OK`.
- **Não testado:** reversão da `0002` com dados gravados.

## Impressão

- `scripts/semear_base_de_medicao.py` com saída 0, seguido de `scripts/medir_identificacao_do_emitente.py`:
  - senha sintética aleatória, não registrada;
  - `DL_PYTHON_DO_SISTEMA=/home/user/DataLedger/.venv/bin/python3`;
  - `DL_CHROMIUM_EXECUTAVEL=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
- **Execução 1 (semeadura padrão):** saída **0**. "telas derivadas com timbre (5)": as 5 com PASSOU, incluindo `livro_caixa_web:relatorio`. Livro caixa: `livro_caixa_web:relatorio: PASSOU`.
- **Execução 2 (`--telas=livro_caixa_web:relatorio`, dados de 6 folhas com P20 e estornos):** saída **1**, REPROVADO, folha 6 sem identificação (achado N3).
- **PDF do Livro Caixa, empresa CPF (6 folhas):**
  - "— CPF 123.456.789-09" e "CAEPF 12345678900017";
  - base legal da DE-087 item 12;
  - grupo P20 com o título próprio;
  - "Estorno do lançamento nº 2" na tabela principal;
  - nenhum controle de tela: 0 ocorrências de "Consultar período", "Trocar de empresa", "Estornar" e "Voltar ao período".
- **PDF da empresa CNPJ** (1 folha, pelo navegador, com `emulate_media("print")`): "— CNPJ 11.222.333/0001-81", base legal presente, 0 controles de tela.

## Critério 7 — comandos e números exatos

- `pytest -q -p no:cacheprovider`, suíte completa, clone `git` do HEAD, PostgreSQL: **1 failed, 3005 passed, 45 skipped, 2 warnings, 4 subtests passed in 129.26s**, saída 1.
  - A única falha é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, a falha de ambiente conhecida (Python 3.13.12, não 3.14). É preexistente.
  - Numa cópia `git archive`, sem `.git`, houve uma segunda falha, `scripts/test_decidir_caminhos_vigiados.py::test_caminhos_nao_relevantes_so_esconde_prosa_e_imagem_conhecida` (`git ls-files` falha). É artefato da cópia: no clone, esse arquivo dá `31 passed`.
  - O plano registra "2981 passed" porque mediu antes da integração das telas.
- `ruff check .` (ruff 0.16.7): `All checks passed!`, saída 0.
- `ruff format --check .`: `299 files already formatted`, saída 0. Não usei `ruff format` sem `--check`.
- `python manage.py check`: `System check identified no issues (0 silenced).`, saída 0.
- `python manage.py makemigrations --check --dry-run`: `No changes detected`, saída 0. Houve um aviso de que o banco ainda não existia na hora da consulta de histórico; o resultado não é afetado.
- Conjunto do livro-caixa (193 testes): 6 repetições, `193 passed` em todas.

## Casos de teste propostos (para o responsável implementar)

1. **N1:** tela com PF, titular e indicador marcado deve dar 302 e gravar `cpf_beneficiario_nao_informado=True`. O formulário deve renderizar e preservar o controle num 400. O texto de ajuda deve corresponder à regra.
2. **N2:** tela e serviço com chave de 256 e de 300 caracteres devem dar 400 e nada gravado. Serviço com chave válida numa corrida continua devolvendo {201, 200}.
3. **N3:** medição com o Livro Caixa de várias folhas contendo P20 deve dar `folhas_sem_bloco_de_identificacao: []`. Incluir P20 e volume na preparação do instrumento.
4. **N4:** P20 estornado: dentro da tabela P20 devem aparecer "(50,00)" e "Estorno do lançamento nº <id>".
5. **M5:** as 12 linhas dos modelos oficiais, cada uma aceita ou recusada conforme a regra revista, no serviço, na API e na tela.
6. **N5:** totais dos dois grupos impressos; período só com P20 não deve mostrar "Nenhum lançamento neste período".
7. **N7:** mesma chave, corpo igual exceto o indicador: 409.
8. **N8:** reescrever a asserção "RB" com marcador inequívoco.
9. **N13:** o estorno de um lançamento com indicador marcado deve copiar o indicador.
10. **N16:** indicador marcado com `recebido_de` PJ ou EX: recusado.
11. **N21:** conta P11 deve permanecer em `saida_custeio` e fora da tabela P20.
12. **N25 e N26:** trilha "Início › Livro-caixa › <empresa> › Livro Caixa" nas telas do livro-caixa.
13. **N33 e N38:** número de consultas da lista da tela constante entre 1 e 40 lançamentos, com a mesma chave de cache do processador de contexto.
14. **N07:** barreira entre a pré-checagem e `full_clean` (a outra requisição já comprometida): espera-se 200, nunca 400 "já existe".
15. **N12 (opcional):** lançamento legado gravado sob a regra antiga (por exemplo, aluguel de PF sem CPF, criado por ORM) deve continuar estornável.

## Dúvidas contábeis e normativas (do Fred; não são defeitos de software)

- **M5:** a regra de CPF deve ser por código de rendimento, como nos modelos oficiais? Rendimento de PJ exige CNPJ?
- **D2:** a citação "arts. 68 e 69 … e 118 a 125" cobre o conteúdo impresso?
- **D3 e N5:** o livro deve imprimir o total do grupo P20 separado das saídas de custeio? "Saídas" deve incluir P20?
- **PE-72 (D1):** o estorno afeta o mês original ou o mês da correção? Precisa de decisão antes da fatia 2.
- **HI-31 (dígito verificador do CAEPF) e faixa de data por analogia:** continuam hipóteses.

## Não testado

- `pwsh ./scripts/validate-docs.ps1`: `pwsh` não existe neste ambiente (**Bloqueado**).
- Python 3.14 da CI; jobs no GitHub; proteção de branch.
- Acessibilidade (teclado e leitor de tela), contraste, leiaute a 390 px. As capturas em `docs/assets/telas/dl046/` não foram revisadas.
- Impressão em navegador que não seja Chromium; numeração de folhas (limite M3/BL-445 do instrumento).
- Reversão da `livro_caixa.0002` com dados gravados.
- Admin de `Empresa` e `ContaLivroCaixa` no navegador (testado via `Client`).
- Backup e restauração.
- Fatias 2 e 3 (**Fora do escopo**).
- Validação profissional das regras contábeis e normativas (é do Fred).

## Efeitos colaterais e limpeza

- Worktree auditado: HEAD continua `92c6850e8e5e72f422c7b06e546e0bf91e17e1eb`; `git status --short` e `git diff --stat` estão vazios. O repositório principal `/home/user/DataLedger` também está sem alterações (`git status --short`: 0 linhas).
- Cópias e clones descartáveis removidos (`scratchpad/rc46`: 0 entradas restantes), incluindo PDFs, capturas e o arquivo da senha sintética.
- Servidor de desenvolvimento da porta 8765 encerrado.
- Bancos `dataledger_qa46rmig` e `dataledger_qa46rmed` apagados. Os bancos de teste `test_dataledger_qa46r*` foram destruídos pelo pytest-django. A consulta final `select count(*) from pg_database where datname like '%qa46r%'` retornou **0**.
