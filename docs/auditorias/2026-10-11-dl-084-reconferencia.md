# Reconferência da DL-084 — 11/10/2026

Passo final do ciclo do §3.1 (uma auditoria, uma correção, uma reconferência). Correção auditada:
commit `8ac49f4` sobre `14f13a2`, ambos sobre `f6b4578`, branch `ccr-bf4b4a55-hpqgbp`.

## Veredito: APROVADA

Os cinco achados da rodada 1 estão **fechados**: cada verificação que eu havia escrito para cada um
passou no terreno, os dois mutantes sobreviventes (M8 e M9) agora morrem nos testes novos, e as
duas nuances declaradas pelo desenvolvedor são **limites aceitáveis** do desenho — comprovados por
sonda — e não achado novo. Ficam duas observações de documentação, que não bloqueiam.

## Versão e ambiente

- Árvore auditada: `8ac49f4` (correção A1–A5) + `14f13a2` (relatório da rodada 1 e DE-106) sobre
  `f6b4578`. `git status` limpo no início e no fim; os únicos arquivos que escrevi foram as sondas
  temporárias da reconferência (apagadas antes do fechamento) e este relatório.
- Python 3.14.7, PostgreSQL 16, Django 6.1, banco de teste próprio `dataledger_dl084aud`.
- Suíte DL-084 + teste da BL-584: **257 passaram** em 28,04 s no fim (e antes da mutação também).
- Regressão completa em UMA invocação (`pytest -q`): **9.700 passaram, 24 falharam, 78 pularam**,
  4 subtestes, 2 avisos, em 783,94 s (13 min 03 s). As 24 falhas são as mesmas de ambiente Windows
  da rodada 1 (`test_dl017_rodada2/3_frontend`, `test_agentes_multiplataforma` e
  `scripts/test_medir_identificacao_do_emitente`), sem mudança no conjunto. A contagem confere ao pé
  da letra com a declarada no commit da correção.

## Estado dos achados da rodada 1

| Achado | Estado | O que foi revalidado |
| --- | --- | --- |
| A1 — feriados locais atravessando escritórios | **Fechado** | DE-106 + escopo do escritório + testes e mutante (abaixo) |
| A2 — reversão apagava feriado do contador | **Fechado** | Guardas das migrações 0015/0016 + teste `--fake` + sonda com as cinco classes |
| A3 — base da coerência da CSLL sem teste de desconto | **Fechado** | Os dois testes novos matam o mutante M8 |
| A4 — ordem BL-584 sem teste nas rotas do fiscal | **Fechado** | Derivação das rotas do fiscal no teste da BL-584 mata o mutante M9 |
| A5 — guarda de reversão testada em 1 das 3 classes | **Fechado** | Guarda parametrizada nas cinco classes, com instantâneo |

### A1 — Fechado

A verificação que eu escrevi na rodada 1 era: *"teste em que o gestor do escritório B, pela empresa
dele, tenta alterar a linha de Palmas usada pelo escritório A — e a recusa (ou a trilha visível nos
dois escritórios) aparece"*. O arranjo escolhido (DE-106,
`docs/projeto/decisoes.md:5412-5447`) foi melhor do que as duas alternativas que eu tinha
oferecido: a base (lei, data da leitura e fonte bancária) vira global e **somente leitura**, e a
escrita passa a nascer escopada ao escritório que agiu, valendo só para as empresas dele.

- **Modelo e cálculo:** `apps/fiscal/models.py:2728-2741` (`FeriadoLocal.escritorio`, anulável,
  vazio = base) e `:2813-2825` (`ExcecaoFeriadoLocal.escritorio`); `apps/fiscal/presumido_calculo.py:
  674-713` (`_substitui_a_linha` e `linhas_efetivas`: escritório→base, praça→estado, exceção do
  ano fundida por ano com a mesma precedência, um aviso por dia).
- **Leitura:** `apps/fiscal/presumido.py:2169-2220` (`_feriados_locais_da_praca` filtra
  `Q(escritorio__isnull=True) | Q(escritorio=empresa.escritorio)` e as exceções pelo mesmo critério).
- **Escrita e recusa da base:** `apps/fiscal/views_web.py:7469-7477` e `:7630-7637` (edição/gravacao
  da base → 409 com `_MENSAGEM_LINHA_DA_BASE`, definida em `:7124`), `:7665-7675` (exclusão da base
  → 409), `:7543` e `:7832-7840` (a linha e a exceção nascem com
  `escritorio=empresa.escritorio`; o pré-check de ano repetido está em `:7820-7821`),
  `:7870-7875` (a exceção de outro escritório responde 404) e `:7902-7903` (só a exceção do
  escritório se exclui). A UI mostra a ação **desabilitada com o motivo**, com o mesmo
  texto do servidor (`templates/fiscal/presumido_feriados.html:113-148`,
  `presumido_feriado_form.html:144-158`, `presumido_feriado_excluir.html:69-82`,
  `presumido_feriado_excecao_excluir.html:65-81`).
- **Testados (rodaram verdes):** `test_dl084_feriados_locais.py:194-263` (a linha do escritório B
  não afeta as empresas de A; substitui a da base no mesmo dia; a exceção do escritório substitui a
  da base só para as empresas dele) e `test_dl084_frente_b_telas.py:965-1130` (o gestor de outro
  escritório não edita nem exclui a linha da base — recusa nomeada e dado intocado; a linha que B
  cria só aparece e só afeta as empresas dele; os avisos de A não mudam quando B cadastra feriado e
  exceção na mesma praça).
- **Sondas minhas (verdes):** a linha DO ESCRITÓRIO A responde 404 nas três rotas de ato do
  escritório B (editar, excluir, exceção nova) e a exceção de A responde 404 na exclusão por B,
  com o dado intocado.
- **Mutante E1** (remover o filtro de escopo da leitura do serviço): **morto** por 3 testes de
  isolamento. A regra de substituição também está prendida (ver mutantes E2/E3).

### A2 — Fechado

A verificação era: *"teste de reversão com feriado cadastrado pela tela esperando `RuntimeError`
'Reversão da DL-084 recusada' e nada alterado"*.

- `apps/fiscal/migrations/0015_dl084_rotina_do_presumido.py:196-262`: a guarda passou a contar
  feriado e exceção do escritório (com `_linhas_do_escritorio`, consulta direta porque o modelo
  histórico não enxerga a coluna da 0016 — contra-seguro documentado), e o comentário obsoleto
  ("a tabela não tem caminho de escrita pelo cliente") foi corrigido.
- `apps/fiscal/migrations/0016_dl084_escopo_do_escritorio_feriados.py:24-56`: guarda **ampliada**
  com as cinco classes, como última operação (roda primeiro na reversão) — a correção da observação
  certa: cada migração tem a sua transação, e sem ela as colunas cairiam antes da recusa da 0015.
- **Testados (rodaram verdes):** `test_dl084_migracao.py:173-204` (parametrizado nas cinco classes,
  com instantâneo de antes/depois), `:206-245` (reversão da 0016 recusa com linha do escritório e
  passa sem elas, preservando a linha da base), `:247-280` (contra-seguro da 0015 com a reversão
  da 0016 falsificada por `--fake`).
- **Sonda minha (verde):** as cinco classes de dado do contador **presentes ao mesmo tempo**, com
  instantâneo completo do banco antes/depois (contagens das cinco classes, linhas da base, lista de
  tabelas e as colunas de escopo): `migrate fiscal 0014` levantou `RuntimeError` "Reversão da
  DL-084 recusada" e **o instantâneo saiu idêntico** — recusa sem alterar nada.

### A3 — Fechado

A verificação era o caso exato que eu propus: *"vServ 1.000,00, desconto incondicional 200,00 e
vRetCSLL 37,20 (4,65% de 800,00): esperado 'estimada', CSLL 8,00"*, mais o espelho.

- `test_dl084_csll_e_retencao.py:157-213`: `test_desconto_incondicional_desconta_na_base_da_
  coerencia_pelo_banco` (1.000,00 − 200,00, 37,20 → "estimada", 8,00) e
  `test_espelho_os_4650_da_base_errada_sem_o_desconto_caem_a_classificar` (46,50 → "a classificar").
- **Mutante M8** (`_ler_nota` com base `valor` sem o desconto): **morto** pelos dois testes novos
  (2 falhas, 16 passaram — só eles pegam).

### A4 — Fechado

A verificação era: *"derivar as rotas de `apps/fiscal/urls_web.py` no teste da BL-584"*.

- `apps/contabilidade/tests/test_dl086_papel_antes_da_empresa.py:44-84`: a derivação passou a
  incluir `apps.fiscal.urls_web` (85 combinações com `empresa_id`, contagem medida na execução), e
  o controle de vacuidade ganhou o assert de PRESENÇA das rotas do fiscal (`:81-84`) — sem ele, uma
  derivação que só enxergasse a contabilidade passaria em silêncio.
- **Mutante M9** (`presumido_parametros_gravar` resolvendo a empresa antes da permissão): **morto**
  por `test_cliente_recebe_a_mesma_resposta_para_empresa_existente_e_inexistente
  [fiscal_web:presumido_parametros_gravar]` (o cliente passou a receber 403 para a empresa
  existente e 404 para a inexistente — respostas divergentes, o que o teste reprova). Os outros 84
  casos passaram, como esperado: só a rota mutada muda.

### A5 — Fechado

A verificação era: *"parametrizar o teste de reversão para as três classes"* — entregue nas cinco
(`test_dl084_migracao.py:173-204`, ids `parametro`, `competencia`, `encerramento`,
`feriado_escritorio`, `excecao_escritorio`), cada um com o instantâneo antes/depois e com o banco
seguindo no head (colunas do escopo no lugar). A sonda de duas classes independentes (as cinco de
uma vez) confirmou o mesmo resultado.

## Os três testes re-apontados da frente B

Julgados um a um: **a intenção sobreviveu**. Os três mudaram apenas a FIXTURE — da linha da BASE,
que com o A1 passou a ser somente leitura e cujo comportamento antigo é exatamente o ato que a
rodada 1 reprova, para a linha do ESCRITÓRIO, que é o caminho legítimo do usuário. As asserções
foram preservadas ou reforçadas; nenhuma foi enfraquecida.

| Teste | Antes (fixture) | Depois (fixture) | Asserções |
| --- | --- | --- | --- |
| `test_alterar_feriado_pela_tela_edita_sem_mudar_a_data_normativa` (`test_dl084_frente_b_telas.py:314-365`) | editava a linha da BASE 19/03 de Palmas | cria a linha do escritório (07/09) e a edita | preservadas: data normativa não muda, fundamento muda, fonte some e o aviso fica mais fraco; ganhou `escritorio == escritorio_a` (nasce escopada) |
| `test_feriado_com_excecao_nao_se_exclui_e_manda_excluir_a_excecao` (`:397-455`) | usava a linha da base 05/10 com a exceção da carga | cria linha do escritório com exceção do escritório | preservadas: 409, "exclua cada exceção antes de excluir", nada apagado |
| `test_excluir_excecao_pela_tela_com_confirmacao` (`:468-515`) | excluía a exceção da BASE de 2026 | cria e exclui a exceção do escritório (2027) | preservadas: `.botao--perigoso`, rótulo nomeando o alvo, exclusão efetivada, feriado intocado |

## As duas nuances declaradas

Ambas **aceitáveis como limite do desenho** — não são achado novo. Foram medidas por sonda
própria e batem com o que o desenvolvedor declarou.

1. **Exceção do escritório para o mesmo (feriado, ano) da base é barrada pelo índice único.**
   Medido: a recusa vem **antes** do banco, como erro nomeado de campo —
   "Já existe exceção para este ano neste feriado." (400, `id="erro_excecao_ano"`, nada gravado;
   `apps/fiscal/views_web.py:7820-7821`) — e o índice `excecao_feriado_unica_por_ano` segue como
   segunda defesa. O caminho de saída existe e está testado: o escritório cadastra a PRÓPRIA linha
   do dia e a PRÓPRIA exceção, e aí substitui a da base só para as empresas dele
   (`test_dl084_feriados_locais.py:228-263`). O custo é o contador re-citar a lei e a leitura na
   linha dele — coerente com o critério 8 (toda linha cita a fonte) e sem efeito em dinheiro ou
   data (o feriado local nunca muda o vencimento). Manter o índice preserva a migração estritamente
   aditiva, como declarado.
2. **A UI da exceção sobre linha da base canaliza "cadastre a sua para a sua praça", sem atalho.**
   Medido: a linha da base não tem "Alterar" habilitado na lista (ação desabilitada com o motivo,
   `presumido_feriados.html:127-148`), então a página do feriado — onde mora o formulário de
   exceção — não tem caminho de navegação; a URL direta responde 409 com o motivo e o botão de
   gravar desabilitado, e a rota de exceção continua funcional e testada
   (`test_dl084_frente_b_telas.py:439-466` cadastra exceção do escritório sobre a linha da base
   19/03; sonda minha idem, criando exceção 2027 escopada ao escritório). É o desenho declarado.

**Observações (não bloqueiam):** (a) as duas nuances estão registradas hoje na mensagem de entrega e
em comentários de código, não na DE-106 — vale acrescentá-las ali em duas linhas, para o limite não
viver só na conversa; (b) na página da linha da base, o motivo "cadastre a sua para a sua praça"
pende da ação de GRAVAR, enquanto o formulário de exceção logo abaixo continua ativo — o texto de
ajuda poderia distinguir "a linha do feriado é da base" de "a exceção do ano pode ser a sua", para
ninguém achar que a exceção também está proibida.

## Mutantes da reconferência

Um por vez, com `git checkout --` ao final e `git status` conferido limpo depois de cada um.

| Mutante | Resultado |
| --- | --- |
| M8 — base da coerência da CSLL sem o desconto incondicional (`presumido.py:965`) | **Morto.** 2 falhas: `test_desconto_incondicional_desconta_na_base_da_coerencia_pelo_banco` e o espelho (`test_dl084_csll_e_retencao.py`). |
| M9 — empresa resolvida antes da permissão em `presumido_parametros_gravar` (BL-584) | **Morto.** 1 falha: `test_cliente_recebe_a_mesma_resposta_para_empresa_existente_e_inexistente[fiscal_web:presumido_parametros_gravar]` (403/404 divergentes). |
| E1 — filtro de escopo do escritório removido da leitura (`presumido.py:2187`) | **Morto.** 3 falhas de isolamento (`test_dl084_feriados_locais.py:194`, `test_dl084_frente_b_telas.py:1004,1043`). |
| E2 — `_substitui_a_linha` sempre falsa (substituição do mesmo dia anulada) | **Sobreviveu — mutante equivalente.** A ordenação de `_feriados_locais_da_praca` (`presumido.py:2193`) já entrega o mesmo vencedor do dia que a regra escolheria, e a fusão de exceções anda na mesma ordem. Não é lacuna de asserção (o resultado está prendido, ver E3), mas a regra em si só se distingue da ordem com entrada fora de ordem: um teste unitário direto de `linhas_efetivas` com tupla invertida deixaria a regra prendida por ela mesma. |
| E3 — ordenação de `_feriados_locais_da_praca` invertida | **Morto.** 3 falhas — a precedência do dia (linha e exceção que vencem) está prendida pelo resultado. |

## Verificações

- Suíte DL-084 + BL-584 no banco próprio: **257 passaram** em 28,04 s (fim da reconferência; antes
  das mutações também verde).
- Regressão completa em UMA invocação: **9.700/24/78** em 783,94 s — igual à declarada no commit da
  correção; as 24 falhas são as de ambiente Windows conhecidas, sem mudança.
- Sondas próprias da reconferência (4 testes temporários, apagados): cinco classes de dado do
  contador na reversão com instantâneo idêntico antes/depois; nuance 1 (recusa nomeada de campo,
  nada gravado); nuance 2 (tela da base com o motivo e rota de exceção funcional); linha do
  escritório A respondendo 404 nas rotas de ato do B. 4/4 verdes.
- `git status` e `git diff --stat`: sem alteração em nenhum arquivo do produto no fim — mutantes
  revertidos um a um e sondas apagadas. O único arquivo novo é este relatório.

## O que não pude verificar

- **Confirmação do Fred sobre a HI-151 e o arranjo da tabela por praça:** segue como hipótese
  registrada; a DE-106 documenta a decisão técnica e o motivo, mas a palavra final sobre a regra de
  domínio é do responsável pelo produto (mesma ressalva da rodada 1).
- **Reversão em banco de produção:** medida só no banco de teste próprio, com as cinco classes e o
  contra-seguro `--fake`. O comportamento observado é o declarado, mas a operação real num banco com
  histórico de produção não foi exercitada.
- **Navegador real, leitor de tela e impressão das telas:** verifiquei o HTML e as checagens de
  acessibilidade do produto; não abri as telas num navegador nesta rodada.
- **Concorrência real** entre escrita de feriado e apuração: as travas e unicidades foram lidas e
  testadas em série; dois processos simultâneos não foram exercitados.
- O mutante E2 não se distingue da regra pelos testes atuais (equivalente dada a ordenação) — a
  observação está registrada acima, para quem mantiver `linhas_efetivas`.

## Arquivos relevantes

- `apps/fiscal/models.py`, `apps/fiscal/presumido_calculo.py`, `apps/fiscal/presumido.py`
- `apps/fiscal/migrations/0015_dl084_rotina_do_presumido.py`,
  `apps/fiscal/migrations/0016_dl084_escopo_do_escritorio_feriados.py`
- `apps/fiscal/views_web.py`, `templates/fiscal/presumido_feriado_*.html`
- `apps/fiscal/tests/test_dl084_feriados_locais.py`, `test_dl084_frente_b_telas.py`,
  `test_dl084_csll_e_retencao.py`, `test_dl084_migracao.py`
- `apps/contabilidade/tests/test_dl086_papel_antes_da_empresa.py`
- Decisão: `docs/projeto/decisoes.md:5412-5447` (DE-106); rodada 1:
  `docs/auditorias/2026-10-11-dl-084-rodada-1.md`
