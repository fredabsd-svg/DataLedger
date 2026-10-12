# Reconferência da DL-088 — 11/10/2026

Passo final do ciclo do §3.1 (uma auditoria, uma correção, uma reconferência — depois desta não há
terceira rodada). Correção auditada: commit `f69cf53` sobre `8e56ba4`, branch `ccr-bf4b4a55-hpqgbp`.

## Veredito: APROVADA

Os sete achados da rodada 1 estão **fechados**: cada verificação que eu havia escrito para cada um
passou no terreno, e os seis mutantes que reapliquei (os três sobreviventes A3/A4/A5, os dois do A1
e o do A2) **morrem** nos testes novos. O dinheiro que a A2 mudou bate ao centavo nas quatro pontas
que promete (efetivação, composição do mês, pré-DAS e RBT12 — medidos por sonda própria), e a nota
sem desconto não mudou. A reversão de `migrate fiscal 0016` com dado do contador recusa **sem
alterar nada**, nas três classes de dado juntas (sonda própria, com instantâneo).

A divergência do A4 está **decidida a favor do desenvolvedor**, com medição minha: a derivação da
BL-584 já cobria as rotas novas e já derrubava o mutante — o achado A4 da rodada 1 era artefato da
**amostra de testes que eu rodei**, e não lacuna de cobertura do produto. O erro foi meu, e está
registrado abaixo com as medições dos dois lados. O caso cruzado que a correção acrescentou é
endurecimento bem-vindo (e cobre também a rota nova de cancelamento).

Restam duas observações que não bloqueiam: o frete cobrado na receita de 2027 segue como dúvida de
domínio com o Fred (P15, declarada — a correção só fechou o desconto, como eu propus), e as duas
divergências menores declaradas pelo desenvolvedor (piso de 5 caracteres no motivo; janela dos
semestres posteriores como prazo final) são **limites honestos** do desenho, não achado novo.

## Versão e ambiente

- Árvore auditada: `f69cf53` (correção A1–A7) sobre `8e56ba4` (frente B). `git status` limpo no
  início e no fim; os únicos arquivos que escrevi foram as sondas temporárias da reconferência
  (apagadas antes do fechamento) e este relatório.
- Python 3.14.7, PostgreSQL 16, Django 6.1, `.venv` do repositório, banco de teste próprio
  `dataledger_dl088aud`.
- Suíte DL-088: **141 testes** (115 da rodada 1 + 26 da correção), coletados e verdes no início.
  Com o teste da BL-584 e os de referência do RBT12: **273 passaram** em 34,44 s.
- Regressão completa em UMA invocação (`pytest -q -p no:randomly`): **9.805 passaram, 24 falharam,
  78 pularam**, 4 subtestes, 2 avisos, em 881,84 s (14 min 41 s). As 24 falhas são as mesmas de
  ambiente Windows da rodada 1 (`test_dl017_rodada2/3_frontend`, `test_agentes_multiplataforma` e
  `scripts/test_medir_identificacao_do_emitente`), sem mudança no conjunto. A contagem reconcilia
  com a declarada na correção (9.802/25/78): são as **duas sondas minhas** a mais (+2 passaram) e o
  **flutuante BL-703**, que falhou na rodada do desenvolvedor e passou na minha (o comportamento
  flutuante já é o declarado).

## Estado dos achados da rodada 1

| Achado | Estado | O que foi revalidado |
| --- | --- | --- |
| A1 — cancelamento da opção sem espelho da Res. 194/2026 | **Fechado** | Cancelamento com janela citada, motivo, trilha e efeito no motor; testes de serviço, API e tela; mutantes M-A1a e M-A1b mortos |
| A2 — receita de 2027 sem descontar o desconto incondicional | **Fechado** | `vProd − vDesc` nas quatro pontas (sonda própria, 95,00/95,00/95,00/275.095,00 e o espelho 100,00 intacto); mutante "vProd cheio" morto |
| A3 — semestre da opção sem teste no pré-DAS público | **Fechado** | Dois testes novos de PA 07/2027 (669,83 com art. 22-A e o espelho de recusa); mutante morto |
| A4 — ordem BL-584 sem teste nas rotas novas | **Fechado, reclassificado** | A cobertura EXISTIA (derivação da BL-584); o achado era artefato da minha amostra — ver a seção da divergência; o caso cruzado novo é endurecimento |
| A5 — receita não prendida contra o `vProdLiq` | **Fechado** | Teste com item trazendo `v_prod`, `v_desc` e `v_prod_liq` (95,00, e não 90,00); mutante morto |
| A6 — fórmulas do sublimite fora do módulo | **Fechado** | Escopo 1 do plano corrigido, item movido para "Fica fora" com o motivo e BL-704 (critério de fechamento escrito) |
| A7 — HI-152 desatualizada | **Fechado** | HI-152, item 2, reescrita no estado atual e coerente com o código |

### A1 — Fechado

A verificação que eu escrevi era: *"teste de gravação do cancelamento dentro da janela (com trilha
e efeito no pré-DAS do semestre) — ou, se for DE, o texto nomeando a limitação na tela e na memória
do pré-DAS"*. O arranjo escolhido foi o primeiro: o cancelamento virou ato à parte, no molde dos
estornos da casa.

- **Modelo:** `apps/fiscal/models.py:1713-1722` (`cancelada_em`/`cancelada_por`/`motivo_cancelamento`
  na própria linha, sem apagar o histórico) e `:1733` (a unicidade
  `opcao_regime_ibs_cbs_unica_por_semestre` virou PARCIAL em `cancelada_em__isnull=True`: duas
  opções ATIVAS impossíveis, a cancelada libera o semestre).
- **Serviço:** `apps/fiscal/receita.py:1723-1799` (`cancelar_opcao_regime_ibs_cbs`: motivo
  obrigatório com piso (`MOTIVO_CANCELAMENTO_MINIMO`, `:1627`) e teto da casa, trava da empresa e
  `select_for_update` da linha ativa, janela validada, ato único — sem opção recusa e já cancelada
  recusa — e trilha `regime_ibs_cbs.opcao_cancelada` com antes/depois e motivo). A leitura ignora a
  cancelada (`:1519-1531`), então o motor, a API e a tela voltam a "opção não informada".
- **Janela com a fonte citada:** `receita.py:1648-1686` — 03/11 a 20/12/2026 para o 1º semestre de
  2027 (Res. CGSN 194/2026, o único caso com janela fechada na fonte) e, nos demais semestres, o
  prazo final dos arts. 40-C/40-D (até 30/11 do ano anterior ao 1º semestre; até 31/05 do próprio
  ano no 2º), com `inicio = None` porque **a fonte não fixa abertura**. A leitura "respectively" da
  consulta (01–30/09 → efeitos 01/01 → cancelável até 30/11; 01–31/03 → efeitos 01/07 → até 31/05)
  confere com o código, e nada de prazo foi inventado (AGENTS §10).
- **Telas e API:** tela em duas etapas com `.botao--perigoso` nomeando o alvo, janela e fonte na
  tela (`test_dl088_b_telas.py:787-865`) e recusa fora da janela mostrando o prazo sem gravar
  (`:866-889`, 409); API `.../opcao-regime-ibs-cbs/cancelar/` com motivo obrigatório (400), fora da
  janela (409 com o prazo), campo fora do contrato (400) e permissão/isolamento
  (`test_dl088_a2_api.py:540-606`).
- **Testados (rodaram verdes):** cancelamento feliz com trilha e re-registro liberado
  (`test_dl088_a2_api.py::test_cancelamento_na_janela_e_feliz_com_trilha`,
  `::test_re_registro_depois_do_cancelamento_aceito_e_vira_a_unica_ativa`), fora da janela recusado
  citando o prazo (`::test_cancelamento_fora_da_janela_e_recusado_citando_o_prazo`,
  `::test_o_2_semestre_de_2027_vale_a_regra_geral_ate_31_05`), sem opção e já cancelada
  (`::test_cancelamento_sem_opcao_ativa_e_recusado`, `::test_cancelar_duas_vezes_e_recusado`),
  motivo obrigatório (`::test_o_motivo_do_cancelamento_e_obrigatorio`) e o efeito no motor
  (`test_dl088_a2_calculo_2027.py:417-448`: registrada, o pré-DAS apura 808,00; cancelada na janela,
  volta a recusar `opcao_regime_regular_nao_informada`).
- **Mutantes:** M-A1a (cancelamento sem validar a janela) e M-A1b (leitura não ignora a cancelada)
  **mortos** — 4 falhas cada, em serviço, API, tela e motor (tabela abaixo).

### A2 — Fechado

A verificação era: *"teste com `vProd` 100,00 e `vDesc` 5,00 esperando a receita decidida (95,00
pela fonte citada) e o efeito no pré-DAS do mês"*.

- **Regra:** `apps/fiscal/itens_nfe.py:409-435` (`receita_do_item_2027` = `vProd − vDesc` no item
  `indTot` 1; `indTot` 0 continua 0,00), com a fonte citada no docstring (LC 123, art. 3º, § 1º, na
  redação da LC 214: "não incluídas … os descontos incondicionais"). A memória da efetivação mostra
  as parcelas (`regra`, `v_prod`, `v_desc`, `receita`, `v_prod_liq`) — só o dict da memória mudou; o
  valor da nota sem desconto não.
- **Testados (rodaram verdes):** o teste do desconto
  (`test_dl088_a2_nfe_2027.py:162`, nota 100,00 com 5,00 de desconto → 95,00 na efetivação, com a
  memória completa) e o da composição do mês (`:208`, 95,00 — o que o pré-DAS e o RBT12 leem). A
  nota sem desconto continua 100,00 (`:131`).
- **Sonda minha (verde), o dinheiro nas quatro pontas:** nota de 02/2027 com `vProd` 100,00 e
  `vDesc` 5,00, janelas confirmadas e o mês confirmado depois da efetivação: **efetivação 95,00 ·
  composição do mês 95,00 · pré-DAS de 02/2027 com o segmento de mercadoria em 95,00 (Anexo I) ·
  RBT12 do PA 04/2027 = 275.095,00** (11 × 25.000 + 95). Espelho sem desconto: **100,00** nas
  quatro pontas e RBT12 **275.100,00** — a nota sem desconto não mudou.
- **Mutante:** M-A2 ("vProd cheio", sem descontar o `vDesc`) **morto** por 4 falhas (os dois testes
  novos, o do `vProdLiq` que também compara o valor e a sonda de ponta a ponta).
- **Resto declarado:** o frete cobrado (`vFrete`) e os demais acréscimos continuam fora da receita
  de 2027, com a dúvida registrada na P15 e no docstring — é o que eu propus ("decidir com o Fred…
  o tratamento de `vDesc` e `vFrete`"): o desconto foi decidido pela fonte citada; o frete fica com
  o Fred. Não é achado aberto.

### A3 — Fechado

A verificação era: *"um teste do caminho público com PA 07/2027 e a opção do 2º semestre (CBS e IBS
deduzidos) e o espelho com a opção só do 1º semestre (recusa `opcao_regime_regular_nao_informada`)"*.

- `test_dl088_a2_calculo_2027.py:371-398` (o pré-DAS público lê a opção do 2º semestre em julho):
  PA 07/2027 com a opção REGIME REGULAR do 2º semestre, RBT12 300.000 pela janela defasada
  de 06/2026 a 05/2027 (a janela está escrita à mão no suporte do teste), faixa 2 do Anexo III:
  808,00 menos CBS 136,63 e IBS 1,54 = **669,83**, com os deduzidos na memória. Valores conferidos à
  mão por mim (é a mesma conta da rodada 1, agora no caminho público de julho).
- `:400-415` (espelho): com a opção só do 1º semestre, o PA 07/2027 recusa
  `opcao_regime_regular_nao_informada`.
- **Mutante:** M-A3 (pré-DAS lendo sempre o 1º semestre) **morto** pelos dois testes (2 falhas).

### A4 — Fechado, com reclassificação (a divergência, decidida por mim)

A alegação do desenvolvedor é que a derivação da BL-584 **já** cobria as duas rotas de POST e **já**
derrubava o mutante, e que o mutante passou na rodada 1 porque a minha execução não incluiu
`apps/contabilidade/tests/test_dl086_papel_antes_da_empresa.py`. **Medi os dois lados, e ele tem
razão:**

| Execução (mutante "empresa resolvida antes da permissão" em `opcao_regime_ibs_cbs_registrar`) | Resultado |
| --- | --- |
| BL-584 (`test_dl086_papel_antes_da_empresa.py`), versão ATUAL | **2 falhas** — `test_cliente_recebe_a_mesma_resposta_para_empresa_existente_e_inexistente[fiscal_web:opcao_regime_ibs_cbs_registrar]` e o caso cruzado novo |
| BL-584, versão de **`8e56ba4`** (a que existia na rodada 1, sem o caso cruzado) | **1 falha** — `test_cliente_recebe_a_mesma_resposta_para_empresa_existente_e_inexistente[fiscal_web:opcao_regime_ibs_cbs_registrar]` (403 para a existente, 404 para a inexistente: respostas divergentes, que o teste reprova) |
| Amostra da rodada 1 (`test_dl088_b_telas.py` + `test_dl088_a2_api.py`) | **61 passaram** — o mutante sobrevive, exatamente como eu medi |

Ou seja: a cobertura existia desde a correção da DL-084 (a derivação inclui
`apps.fiscal.urls_web.urlpatterns` — o docstring do arquivo, idêntico em `8e56ba4`, diz isso e o
controle de vacuidade prende a presença das rotas do fiscal), a rota `opcao_regime_ibs_cbs_registrar`
entra na varredura por ter `empresa_id`, e o par existente/inexistente distingue as duas ordens tão
bem quanto o cruzamento que eu pedi. **O achado A4 da rodada 1 estava errado como afirmação sobre o
produto** ("nada prende a ordem"): o que era verdade é que os testes da DL-088 sozinhos não prendem
a ordem — e eu não rodei o arquivo da BL-584. Foi artefato da minha amostra.

A correção acrescentou mesmo assim o caso cruzado nomeado
(`test_dl086_papel_antes_da_empresa.py:212-262`: CLIENTE × empresa de outro escritório → 403 em
registro, cancelamento e gravação, nada gravado) e o mesmo cruzamento nas consultas novas
(`test_dl088_b_telas.py:936-…`). É endurecimento aceitável — e necessário para a rota nova de
cancelamento entrar com nome.
O registro fica: quem auditar varredura derivada deve **rodar o arquivo da varredura**, não só os
testes da entrega.

### A5 — Fechado

A verificação era: *"um teste de `receita_do_item_2027` com item trazendo `v_prod` e `v_prod_liq`
diferentes, esperando o `vProd`"*.

- `test_dl088_a2_nfe_2027.py::test_a_regra_de_2027_nao_usa_o_v_prod_liq_como_receita`: item com
  `v_prod` 100,00, `v_desc` 5,00 e `v_prod_liq` 90,00 → **95,00** (e não 90,00); sem desconto →
  100,00 (também não é o `vProdLiq`). O `vProdLiq` segue só como memória.
- **Mutante:** M-A5 (usar o `v_prod_liq` quando existir) **morto** por 1 falha (este teste).

### A6 — Fechado

A verificação era: *"teste número a número das fórmulas dos cinco anexos… ou registrar que elas
ficam para depois em 'Fica fora' do plano, com o motivo"* — entregue a segunda opção, que é a
honestas enquanto o Anexo II/III não estiver confirmado pelo domínio:

- `docs/planos/DL-088-virada-de-2027-no-simples.md`: o escopo 1 agora marca as fórmulas do
  sublimite como **saídas desta etapa**, e o "Fica fora" as lista com o motivo (a do Anexo II para o
  ICMS usa parâmetros do Anexo III na consulta e não está confirmada).
- `docs/projeto/backlog.md` (**BL-704**) com o critério de fechamento escrito: fórmula confirmada em
  fonte oficial (com data da leitura) e implementada com casos de referência escritos à mão, ou o
  escopo 1 corrigido para refletir a leitura. É o que faltava para o item não viver só na entrega.

### A7 — Fechado

A verificação era: *"leitura do texto novo coerente com `pre_das.py` e `receita.py`"*.

- `docs/projeto/requisitos.md` (HI-152, item 2) reescrito: "O produto **TEM** o dado de IPI mantido
  (Zona Franca) desde a frente A2 (`IpiMantidoZfmEmpresa`, com fonte obrigatória)… sem o dado, o
  produto NÃO presume ZFM — vai ao Anexo I com aviso nomeado". Coerente com
  `apps/fiscal/pre_das.py:415-427` e `:1680-1691` e com `apps/fiscal/receita.py:1808-…`. A validação
  do Fred (HI-152 item 1 e clientes na ZFM) segue declarada, como em qualquer hipótese.

## As duas divergências menores declaradas

Ambas **aceitáveis como limite do desenho** — não são achado novo, e as duas respeitam AGENTS §10
(nada de prazo sem fonte oficial).

1. **Piso de 5 caracteres no motivo do cancelamento** (`receita.py:1627`,
   `MOTIVO_CANCELAMENTO_MINIMO`): a fonte legal não fixa tamanho de motivo, e o comentário diz que é
   decisão de produto (um motivo "x" não diz nada a quem ler a trilha depois). É a mesma exigência
   de motivo dos estornos da casa, e a constante está declarada como sem fonte. Medido: o piso recusa
   com mensagem nomeada e nada grava (`test_o_motivo_do_cancelamento_e_obrigatorio`).
2. **Janela dos semestres posteriores como prazo FINAL, sem abertura** (`inicio = None`): os
   arts. 40-C/40-D dizem "cancelável até 30/11 e até 31/05" — só o prazo final — e o docstring
   registra que não se exige abertura que a fonte não traz. Preferível a inventar um início; a
   Res. 194/2026, que tem janela fechada, está fixada à mão como ela própria diz.

## Mutantes da reconferência

Seis mutantes aplicados, um por vez, sempre com `git checkout -- <arquivo>` (ou `git checkout HEAD --
<arquivo>` quando a versão antiga de um arquivo de teste entrou na medição) ao final, com `git
status` conferido limpo depois de cada um. Alvo: a suíte DL-088 inteira (141 testes), mais o teste
da BL-584 e as sondas nos casos indicados.

| Mutante | Resultado |
| --- | --- |
| M-A3 — pré-DAS público lendo sempre o 1º semestre (`pre_das.py:1445`) | **Morto.** 2 falhas: `test_o_pre_das_publico_le_a_opcao_do_2_semestre_em_julho` e `test_a_opcao_do_1_semestre_nao_libera_o_pa_de_julho` (`test_dl088_a2_calculo_2027.py`). |
| M-A4 — empresa resolvida antes da permissão em `opcao_regime_ibs_cbs_registrar` (`views_web.py:10308-10312`) | **Morto pela BL-584** (2 falhas na versão atual; 1 falha na versão `8e56ba4`); sobrevive só à amostra da DL-088 (61 passaram). Ver a seção da divergência. |
| M-A5 — `vProdLiq` como receita quando o campo existe (`itens_nfe.py:430-435`) | **Morto.** 1 falha: `test_a_regra_de_2027_nao_usa_o_v_prod_liq_como_receita`. |
| M-A2 — `vProd` cheio, sem descontar o `vDesc` (`itens_nfe.py:432-435`) | **Morto.** 4 falhas: os dois testes de desconto, o do `vProdLiq` e a sonda de ponta a ponta. |
| M-A1a — cancelamento sem validar a janela legal (`receita.py:1761-1764`) | **Morto.** 4 falhas: serviço, API e tela (`test_dl088_a2_api.py` e `test_dl088_b_telas.py`). |
| M-A1b — leitura da opção não ignorando a cancelada (`receita.py:1529-1531`) | **Morto.** 4 falhas: trilha, re-registro, API e o efeito no motor (`test_dl088_a2_calculo_2027.py:417`). |

## Verificações

- Suíte DL-088 (141 testes) + BL-584 (89) + `test_dl074_rbt12_referencia.py`: **273 passaram** em
  34,44 s no início da reconferência; a suíte DL-088 esteve verde em todas as rodadas limpas.
- Regressão completa em UMA invocação: **9.805/24/78** em 881,84 s (reconciliada com a declarada —
  ver "Versão e ambiente"); as 24 falhas são as de ambiente Windows conhecidas, sem mudança.
- Sondas próprias da reconferência (2 testes temporários, apagados): **dinheiro do `vDesc` nas
  quatro pontas** com o espelho sem desconto, e **reversão de `migrate fiscal 0016`** com as três
  classes de dado do contador (opção ativa, opção cancelada e IPI mantido) — `RuntimeError`
  "Reversão da DL-088 recusada" e instantâneo do banco **idêntico** antes e depois, com o banco
  terminando no HEAD (0018). 2/2 verdes.
- Mutantes: 6 aplicados e revertidos um a um (tabela acima).
- `ruff check .` e `ruff format --check .`: limpos no produto (os únicos apontamentos eram do
  arquivo temporário de sondas, apagado). `manage.py check`: "System check identified no issues".
  `manage.py makemigrations --check --dry-run`: "No changes detected".
- `git status` e `git diff --stat`: sem alteração em nenhum arquivo do produto no fim — mutantes
  revertidos e sondas apagadas. O único arquivo novo é este relatório.

## O que não pude verificar

- **A validação do Fred** sobre HI-149/P15 (o frete cobrado na receita de 2027) e HI-152 (clientes na
  Zona Franca): seguem como hipóteses registradas. O desconto incondicional foi decidido pela fonte
  citada e está testado; o frete continua como dúvida de domínio declarada — a palavra final é do
  responsável pelo produto.
- **As fórmulas do sublimite (BL-704):** a conferência do Anexo II/III com a fonte oficial e a
  implementação ficaram para a etapa que a BL-704 descreve; não reli a Res. 190 neste ambiente.
- **Reversão em banco de produção:** medida só no banco de teste próprio, com as três classes de
  dado juntas e instantâneo; num banco com histórico de produção a operação não foi exercitada.
- **Navegador real, leitor de tela e impressão das telas novas** (opção, cancelamento e IPI mantido):
  verifiquei o HTML e as checagens de acessibilidade do produto nos testes; não abri as telas num
  navegador.
- **Flutuação do BL-703:** o teste passou na minha regressão; não refiz a medida de 1 falha em 3
  rodadas sob carga. O comportamento declarado (flutuante) segue em aberto no backlog.
- **Concorrência real** entre cancelamento, re-registro e apuração: as travas (`travar_empresa`,
  `select_for_update`) e a unicidade parcial foram lidas e testadas em série; dois processos
  simultâneos não foram exercitados.

## Arquivos relevantes

- `apps/fiscal/models.py`, `apps/fiscal/receita.py`, `apps/fiscal/itens_nfe.py`,
  `apps/fiscal/escrituracao_nfe.py`, `apps/fiscal/pre_das.py`
- `apps/fiscal/migrations/0018_dl088_cancelamento_da_opcao_de_regime.py`
- `apps/fiscal/api.py`, `apps/fiscal/views_web.py`, `templates/fiscal/opcao_regime_ibs_cbs.html`,
  `templates/fiscal/opcao_regime_ibs_cbs_cancelar.html`
- Testes: `apps/fiscal/tests/test_dl088_*.py` (141 testes) e
  `apps/contabilidade/tests/test_dl086_papel_antes_da_empresa.py` (BL-584)
- Rodada 1: [2026-10-11-dl-088-rodada-1.md](2026-10-11-dl-088-rodada-1.md); plano:
  [../planos/DL-088-virada-de-2027-no-simples.md](../planos/DL-088-virada-de-2027-no-simples.md);
  fonte: [../projeto/consultas/2026-10-09-contador-senior-virada-2027-simples.md](../projeto/consultas/2026-10-09-contador-senior-virada-2027-simples.md);
  BL-704: [../projeto/backlog.md](../projeto/backlog.md); HI-152:
  [../projeto/requisitos.md](../projeto/requisitos.md)
