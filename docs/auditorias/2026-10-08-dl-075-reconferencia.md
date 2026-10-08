# Reconferência da DL-075 — 08/10/2026

**Parecer: APROVADA COM RESSALVAS.** Os achados A1 a A9 e A11 estão fechados, com evidência executada. O A6 está parcial (R1) e o A10 também (falta a linha de base do `estado.md`). Não há achado de gravidade alta nem bloqueadora. Os achados novos são uma lacuna de teste em isolamento e em tela (média), um resíduo da guarda do A6 (baixa), lacunas de teste menores (baixa) e pendências de documentação (baixa).

## 1. Revisão e ambiente

- **Revisão:** `4f42117c4102a962abd7deb75d4c776d759180c1`, HEAD destacado em `/home/user/wt-audit075b`. O SHA bate com o pedido.
- **Ambiente:** Python 3.13.16, PostgreSQL 16 local, venv do projeto, sem `-n`. Usei bancos descartáveis próprios e os removi ao fim.
- **Suíte completa:** numa única invocação, na cópia auditada.
- **Sondas e mutantes:** rodaram numa cópia sem `.git` (`.../scratchpad/aud2/mut`). A cópia auditada nunca foi alterada.
- **Estado final:** `git status` e `git diff --stat` vazios na cópia auditada. Não toquei em `/home/user/DataLedger` nem em `/home/user/wt-dl076`.

## 2. Fechamento de A1 a A11

| # | Veredito | Evidência executada |
|---|---|---|
| A1 | **Fechado** | `pytest` completo, numa só invocação: **1 reprovado, 5.973 aprovados, 53 pulados**, 2 avisos, 4 subtestes, 562,92 s. O único reprovado é `test_versao_minima_python…` (exige Python 3.14). As 4 reprovações da rodada 1 sumiram. Reverter `empresas` para `0007` desfaz 25 migrações e **não** desfaz `fiscal 0005`. A `0005` agora depende de `empresas 0007`. |
| A2 | **Fechado** (ressalva R2) | M10, M11 e M12 mortos por `test_pre_das_da_auditada_nao_enxerga_…` e `test_fator_r_da_auditada_usa_so_a_propria_folha`. O M13 não achou mais o código (a consulta foi refatorada); reancorado em `_vigentes_no_mes` (M13b), morreu. Acrescentei X01 (`_checar_padrao` sem empresa), morto. |
| A3 | **Fechado** | M38 morto por `test_fator_r_soma_o_mercado_externo_no_rbt12_conjunto`. M45 morto por `test_confirmar_folha_de_outra_empresa_responde_404…`. |
| A4 | **Fechado** | Tela da folha: "10.000", "1.234", "1,234", "12,3,4", ".500,00", "-1.234,56" e "1.23,4" respondem **200 com mensagem e nada gravado**. "1.234,56" grava 1234,56; "1.234.567,89" grava 1234567,89. A tela da receita se comporta igual. Serviço: `"10.000"` e `Decimal("10.000")` são recusados. N14 e N20 mortos. |
| A5 | **Fechado** | Duas atividades vigentes e uma nota: bloqueio `notas_sem_atividade_definida`. A API devolve 409, e a tela mostra a mensagem com a lista e o BL-670. Uma atividade só com nota calcula 8.080,00. Duas atividades sem nota, ou segunda encerrada em 31/05, calculam. N01, N02, N03 e N26 mortos. |
| A6 | **Parcial** (resíduo R1, baixa) | Mês 06/2025 a 06/2026 confirmado. Mudar enquadramento, excluir, tirar a padrão, encerrar para trás e adiantar o início sobre mês confirmado são recusados, nomeando o mês, na API (409) e na tela. Uso legítimo passa: encerrar em 31/07/2026 e depois cadastrar nova padrão a partir de 01/08/2026. Mudar só a descrição também passa. N04, N05 e N06 mortos. O furo está em R1. |
| A7 | **Fechado** | PA 07/2025 dá `limites_nao_cadastrados`, tanto com receita pequena quanto com 3,4 ou 3,7 mi. O PA 01/2026 calcula 8.080,00. N09 morto. Todo PA anterior a 2026 passa a recusar (ver R4). |
| A8 | **Fechado** | API: 400 com "situação do ISS". Tela: mensagem, e a receita continua em rascunho. Exportação sem situação continua confirmável. O mês também confirma com o rascunho legado. N10, N11 e N25 mortos. |
| A9 | **Fechado** (lacunas R3) | A lista de folhas caiu de **176 para 10 consultas** (7 para outros anos). `fs12_do_ano` bate com `fs12` em 2 cenários × 12 meses: empresa aberta em 10/2025, estorno e recusas. N12 morto. |
| A10 | **Parcial** | **10.1 fechado:** o sufixo "Fora do primeiro corte" não aparece mais no aviso de limite não apurado (N22 morto). **10.2 fechado:** mensagem própria para troca no meio do mês (N32 morto). **10.3 fechado:** "não confirmado" em texto e dinheiro com 2 casas (N31 e N33 mortos). **10.4 aberto:** a linha de base do `estado.md` continua a da DL-074 (R4). |
| A11 | **Fechado** (resíduo R5) | API recusa float JSON (1.5, 0.1) e "1E+3", "1e3", "1e+3" na receita e nos 5 componentes da folha. Recusa início de atividade em `0001-01-01` e `2017-12-31`; aceita `2018-01-01`. O serviço também recusa notação científica, `Infinity` e `NaN`. N16 a N19 e N21 mortos. |

## 3. Mutantes

**Rodada 1 reaplicada (50):**
- 47 mortos. Isso inclui os seis que estavam vivos: M10, M11, M12, M13 (reancorado), M38 e M45.
- M42 também foi reancorado, e o mutante equivalente (M42b) morreu.
- 3 vivos equivalentes, como na rodada 1: M25, M40 e M50.
- M15 conferido de novo: morto por `test_regime_de_caixa_em_2026_recusa_o_pre_das`.

**Novos (33 + 3):**
- N01 a N33 sobre a lógica corrigida (bloqueio do A5, guarda do A6, bloqueio do A7, recusa do A8, lote do A9, parser do A4, float e notação do A11, textos do A10): **23 mortos e 10 vivos**.
- X01 morto e X02 vivo.
- Vivos:
  - N07: `_meses_confirmados` conta confirmação em qualquer estado.
  - N08: fronteira do `fim` da vigência (`>=` para `>`).
  - N13: lote do FS12 inclui folha estornada.
  - N15: segunda vírgula aceita. Por inspeção, só muda a mensagem, porque o serviço recusa o valor de qualquer forma. Não executei.
  - N23: dinheiro truncado na exibição.
  - N24: lista da tela trata folha estornada como ativa. Por inspeção, é equivalente, porque a folha ativa é sempre a de maior id.
  - N27: troca de padrão deixa de contar como mudança de cálculo.
  - N28 e N29: fronteiras de `_escolher_periodo` em lote.
  - N30: memória na tela perde o dinheiro.
  - X02: `_meses_confirmados` sem filtro de empresa.
- N07, N08, N13, N23, N27, N28, N29, N30 e X02 são lacunas de teste (R2 e R3).

## 4. Regressões

- **Exemplos 2, 4 e 5:** continuam centavo a centavo (M01, M02, M22, M30 mortos por eles).
  - Reproduzi o exemplo 2 pela API e pela tela: total 8.080,00, IRPJ 323,20, CSLL 282,80, Cofins 1.135,24, PIS 246,44, CPP 3.506,72, ISS 2.585,60.
- **Permissões** (dez chamadas de API e tela nas rotas alteradas):

  | Papel | Resultado |
  |---|---|
  | CLIENTE | 403 em tudo |
  | PARALEGAL | lê (200) e é recusado (403) em toda escrita |
  | ANALISTA | escreve |
  | Sem vínculo | 403 na API; telas devolvem a página "sem escritório" (200), sem nome nem CNPJ da empresa |
  | Outro escritório | 404 em tudo |

  Nada foi gravado por quem não podia.
- **Formato da memória:**
  - A tela mostra "300.000,00" e "0,080800000000", sem quebra.
  - O resto da API não mudou: os campos numéricos estruturados seguem em ponto decimal.
  - Só `memoria[].valor` e `descricao` passaram a misturar dinheiro em pt-BR com percentuais em ponto (R4).
  - Os testes existentes da API não fixavam o formato.

## 5. Achados novos

**R1 — Baixa — a guarda do A6 deixa passar mudança parcial de vigência e cadastro retroativo**
- **Local:** `apps/fiscal/pre_das.py`, `_mes_cruza_vigencia` e `_recusar_mudanca_em_mes_confirmado`, a partir da linha 571. `cadastrar_atividade` não tem guarda.
- **Reprodução:**
  - Padrão III desde 2018, 06/2026 confirmado, pré-DAS de 8.080,00. `alterar_atividade(a, {"fim": date(2026, 6, 15)})` é **permitido**. O pré-DAS de 06/2026 passa a ser bloqueio `atividade_padrao_muda_no_mes`.
  - Com nota no mês, `cadastrar_atividade` não padrão retroativa (2018) é permitido. O mês confirmado passa a bloqueio `notas_sem_atividade_definida`.
- **Impacto:** falha segura, porque bloqueia e não muda o valor. Mas "mês confirmado não muda" deixa de valer para o mês já conferido.
- **Correção recomendada:** recusar também a transição de cobertura inteira para parcial, e recusar cadastro retroativo que cubra mês confirmado.
- **Verificar:** teste com `fim=15/06` sobre 06/2026 confirmado, esperando recusa.

**R2 — Média — o código novo tem dois pontos sem teste: isolamento da guarda do A6 e valores da memória na tela**
- **Local:** `apps/fiscal/pre_das.py`, `_meses_confirmados` (linha 564). `apps/fiscal/views_web.py:2223`, `_texto_da_memoria_em_ptbr`.
- **Evidência:**
  - **X02:** tirar `empresa=empresa` de `_meses_confirmados` sobrevive a 224 testes. Se alguém fizer isso, o mês confirmado de **outra empresa** passa a bloquear a alteração de atividade e é citado na mensagem.
  - **N30:** trocar o retorno do regex por `","` sobrevive. Reproduzi na tela: a memória inteira vira "RBT12 … ,", "IRPJ = , × 0,0032…", "Total do pré-DAS ,". O teste `test_tela_do_pre_das_mostra_dinheiro_pt_br…` passa porque "300.000,00" também aparece no resumo da página.
- **Impacto:** a regra de isolamento e o critério 8 (memória na tela) ficam sem prova de execução.
- **Correção recomendada (propostas de teste):**
  1. Duas empresas do mesmo escritório. A vizinha tem meses confirmados; a auditada não. `alterar_atividade(enquadramento=…)` da auditada deve passar, e a mensagem de recusa nunca cita mês da vizinha.
  2. Na tela, extrair as linhas da memória e afirmar valores exatos. Por exemplo, a linha "RBT12 do mercado interno" vale "300.000,00" e "Total do pré-DAS" vale "8.080,00" dentro da tabela da memória, e nenhum valor é ",".
- **Verificar:** reaplicar X02 e N30 e vê-los morrer.

**R3 — Baixa — lacunas de teste menores**
- **N27:** `padrao → False` com o mesmo enquadramento não é mais coberto. O código atual recusa; nada trava isso.
- **N07:** não há teste de que mês "a retificar" ou não confirmado **não** bloqueie a alteração de atividade.
- **N08:** falta a fronteira em que o `fim` da atividade cai exatamente no dia 1º do mês confirmado.
- **N13, N28, N29:** o teste de equivalência do FS12 em lote não inclui estorno seguido de nova folha, nem os limites de período aberto e fechado.
- **N23:** a exibição do RBT12 proporcional não é testada. Exemplo: 120,017142857… aparece como "120,02".
- **Observação:** a memória deixou de mostrar o RBT12 proporcional com precisão total. É só exibição; o cálculo segue em precisão total.

**R4 — Baixa — documentação do plano, do estado e da API**
- O plano `docs/planos/DL-075-pre-das-do-simples.md`:
  - Escopo 2 (linha 39) ainda diz "por nota ou padrão da empresa".
  - Em "Decisões tomadas" não constam o bloqueio do A5 (BL-670), a guarda do A6, a recusa do A7 nem a data mínima de 2018.
  - O `estado.md` registra só o A5.
- A linha de base vigente do `estado.md` (linha 238) segue a da DL-074 (5.691 aprovados, 409 arquivos). Isso é o A10.4 da rodada 1, não corrigido. Medido agora: **5.973 aprovados, 1 reprovado, 53 pulados; 427 arquivos**.
- O efeito do A7 não está dito: **todo PA de 2018 a 2025 passa a ser recusado**, enquanto o plano fala em tabelas de 2018 a 2026.
- Contrato da API: `memoria[].valor` agora mistura dinheiro em pt-BR com percentual em ponto. Isso não está registrado nem testado na API.
- **Correção:** atualizar plano e estado; incluir um teste de API para a memória.
- **Verificar:** leitura dos documentos e `test_documentacao_do_estado`.

**R5 — Baixa — entradas exóticas aceitas**
- O serviço e a API aceitam `"1_000"` (grava 1000,00) e dígitos Unicode (`"٣"` grava 3,00), porque o `Decimal` do Python os aceita. É herança da DL-074; nada se corrompe. A tela recusa "1 000,00".
- **Correção:** exigir `^\d+(\.\d{1,2})?$` no serviço.
- **Verificar:** teste parametrizado.

**Observações, não são defeitos:**
- O bloqueio do A5 dispara também com duas atividades do mesmo anexo e com atividade que começa no dia 20 do mês. Está de acordo com a decisão do arquiteto e é conservador.
- A mensagem mostra "BL-670" ao contador. Isso é cosmético.

## 6. Verificações com números

| Verificação | Resultado |
|---|---|
| `ruff check .` | Todas as verificações passaram |
| `ruff format --check .` | 427 arquivos já formatados |
| `manage.py check` | 0 problemas |
| `makemigrations --check --dry-run` | Nenhuma alteração |
| `migrate` em banco vazio | Aplicou tudo até `fiscal 0005`, em 5,9 s |
| Reversão `fiscal 0005` e `0004`, com reaplicação | Coluna `situacao_iss` saiu e voltou. Os dois reaplicaram. Não repeti a reversão com dados nas tabelas; a rodada 1 já a verificou, e esta correção só mudou a dependência. |
| `pytest` completo | **1 reprovado, 5.973 aprovados, 53 pulados**, 2 avisos, 4 subtestes, 562,92 s. O reprovado é o esperado de Python 3.13. |
| Testes novos | 51 coletados nos 2 arquivos. |
| Mutantes | Rodada 1: 47 mortos e 3 equivalentes vivos. Novos: 23 mortos e 10 vivos nos N; X01 morto e X02 vivo. |
| `git status` / `git diff --stat` da cópia auditada | Vazios |

## 7. Classificação

- **Testado (executado):** suíte completa; tabelas e exemplos 2, 4 e 5 pelos testes do projeto e pela API e tela; fechamento de A1 a A11; matriz de permissões em 10 chamadas por 5 papéis; migrações (vazio, reversão, `empresas 0007`); mutantes.
- **Inspecionado:** a guarda do A6 usa a trava da empresa antes da atividade (mesma ordem de `confirmar_mes`, mas não testei concorrência); templates; docs.
- **Não testado:**
  - `scripts/validate-docs.ps1`: não há `pwsh`. Fiz só emulação em Python nos 4 arquivos tocados, sem problema.
  - Acessibilidade e visual em navegador.
  - Conciliação com o PGDAS-D real, HI-71 e HI-79.
  - Concorrência da guarda do A6.
  - Tabelas de 2027.
- **Bloqueado:** nada.
- **Fora do escopo:** atividade por nota (BL-670), ISS por município (BL-668), PE-78.

## 8. Parecer: APROVADA COM RESSALVAS

A suíte completa está verde, exceto o teste de ambiente conhecido. Todos os casos da rodada 1 foram reproduzidos e fechados. Os exemplos 2, 4 e 5 seguem centavo a centavo, e o isolamento e as permissões se mantiveram.

O registro dos achados novos no backlog fica com o arquiteto, na gravidade dada acima: R2 é média; R1, R3, R4 e R5 são baixas.

Esta auditoria não substitui a validação profissional das regras contábeis e legais, e não declara ausência de defeitos.

Arquivos relevantes (em `/home/user/wt-audit075b`):
- `apps/fiscal/pre_das.py`: R1 (linha 571), R2 (linha 564), A5 (linha 896).
- `apps/fiscal/views_web.py`: R2 (linha 2223).
- `apps/fiscal/tests/test_dl075_correcao_auditoria.py`, `apps/fiscal/tests/test_dl075_correcao_telas_api.py`: onde entram os testes propostos.
- `docs/planos/DL-075-pre-das-do-simples.md` e `docs/agents/estado.md`: R4.

Material de apoio fora do repositório, em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud2/`: `pytest_full.txt`, `mut_out.txt`, `mutar3.py`, `mutar4.py`, `probes/`.
