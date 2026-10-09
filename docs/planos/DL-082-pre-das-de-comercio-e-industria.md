# DL-082 — Fiscal: pré-DAS de comércio e indústria (Anexos I e II)

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170).
Continua o roteiro do [DL-067](DL-067-plano-do-modulo-fiscal.md) depois da
escrituração das NF-e ([DL-081](DL-081-escrituracao-das-nfe-de-saida.md)).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1), porque é o valor
do DAS que o contador confere e paga. A auditoria independente faz uma rodada,
uma correção e uma reconferência.

**É pré-apuração, nunca transmissão.** O produto calcula para o contador
conferir contra o PGDAS-D. Não gera DAS nem transmite (HI-55).

**Depende da [DL-083](DL-083-receita-de-nfe-no-presumido.md)** (RC-172, PE-85.3 e 85.5): a receita do item passa a ser uma função única, com o item fora do total e o ICMS desonerado, e a natureza "combustível" se divide em duas. O pré-DAS usa essa função e recusa as duas naturezas de combustível (HI-132).

## Base

[Consulta ao contador-senior sobre o pré-DAS de comércio e indústria](../projeto/consultas/2026-10-09-contador-senior-pre-das-comercio.md),
de 09/10/2026.

- A LC 123 foi lida no Planalto, e a repartição do Anexo II e da 6ª faixa do
  Anexo I foi conferida contra `simples_tabelas.py`.
- A Res. CGSN 140 foi lida em cópia íntegra.
- O Manual do PGDAS-D (versão de 17/06/2025) foi lido. Os exemplos 1, 2, 3 e
  6 bateram ao centavo com as tabelas do repositório.

Hipóteses HI-125 a HI-132. Pendências PE-86 e PE-87.

## Frente A: rodada de ajuste (decisões do arquiteto)

Aplicadas sobre o commit `2ec6e89`:

1. **Cascata de migrações.** Os testes que revertem `empresas` ou `fiscal`
   restauram o head de todas as apps (`leaf_nodes()`, em `finally`), sem mudar
   asserção: `apps/empresas/tests/test_dl038_migracao.py`,
   `test_dl039_bl529_gatilho_estabelecimento_cpf.py`, `test_dl041_migracao.py`,
   `test_dl076_b8_modo_escrituracao_constraint.py`,
   `apps/fiscal/tests/test_dl083_migracao.py` e `test_dl085_migracao.py`.
2. **Anexo pelo CFOP.** Para `revenda_st_substituido`, `substituto_st`,
   `monofasico`, `exportacao_direta` e `comercial_exportadora`, o anexo vem da
   descrição oficial do CFOP (`apps/fiscal/dados/cfop_it2023002_v210.csv`).
   Produção (5.101, 5.401, 5.501, 7.101) vai para o Anexo II; mercadoria
   adquirida de terceiros (5.102, 5.403, 5.405, 5.502, 7.102) vai para o
   Anexo I. CFOP que não decide gera a recusa `anexo_da_mercadoria_a_confirmar`
   com natureza e CFOP. Código em `apps/fiscal/models.py` (`anexo_pelo_cfop`,
   `anexo_da_mercadoria`) e `apps/fiscal/pre_das.py`. Testes em
   `apps/fiscal/tests/test_dl082_anexo_cfop.py`, incluindo o caso F ponta a
   ponta, com valores conferidos à mão contra a tabela do Anexo II.
3. **Reversão da 0014.** A reversão recusa, sem alterar nada, se houver item
   com marca de monofásico ou segmento de devolução em escrituração em
   rascunho ou efetivada. Com só estornadas, a reversão segue, e o valor de
   cada item fica nos eventos `monofasico_definido` e
   `segmento_devolucao_definido` (`antes` e `depois`). Testes em
   `apps/fiscal/tests/test_dl082_migracao_reversao.py`, pelo `migrate` real.
4. **Mutante.** Anexo pelo CFOP ignorado (sempre Anexo I): 12 testes falham nos
   arquivos `test_dl082_anexo_cfop`, `calculo` e `recusas`. O arquivo foi
   restaurado e comparado byte a byte com o original.

Verificações desta rodada: `ruff check .` e `ruff format --check .` passaram;
`manage.py check` sem problemas; `makemigrations --check` sem mudanças; ida,
volta e ida da 0014 no banco de desenvolvimento; `pytest apps/fiscal` com 3092
passando e 1 pulado; suíte completa numa invocação com 9.009 passando, 54
pulados e 1 falha de ambiente (`test_versao_minima_python`, Python 3.13 local
contra a integração em 3.14).

## O que muda

Hoje o pré-DAS da [DL-075](DL-075-pre-das-do-simples.md) só cobre serviços e
**recusa** o mês com receita de NF-e (HI-122). Esta etapa tira essa recusa nos
casos que o primeiro corte cobre.

## Escopo

1. **Anexo da linha de mercadoria vem da natureza do item:** revenda vai para
   o Anexo I e produção própria para o Anexo II. A atividade padrão da empresa
   não decide o anexo de mercadoria, e a NF-e não dispara o bloqueio de nota
   sem atividade definida.
2. **Mesma cadeia de cálculo da DL-075:** alíquota efetiva do § 1º-A,
   repartição do § 1º-B, diferença centesimal para o tributo de maior
   percentual, valor de cada tributo arredondado a centavo e total como soma
   (HI-71, agora corroborada pelos exemplos 1, 6 e 9 do Manual). Nos Anexos I
   e II não há teto nem redistribuição.
3. **Um RBT12 por mercado para todos os anexos.** A empresa com serviço e
   mercadoria no mesmo mês aplica o mesmo RBT12 a cada anexo (exemplo 2 do
   Manual). O fator r continua decidindo só o anexo dos serviços do inciso V.
4. **Segregação sem redistribuição:**
   - ICMS-ST substituído desconsidera o ICMS;
   - monofásico desconsidera PIS e Cofins;
   - exportação desconsidera PIS, Cofins, IPI, ICMS e ISS (inclui o IPI, que
     faltava no conjunto de hoje);
   - substituto entra no segmento normal, com o `vST` fora da receita;
   - combinações desconsideram a união dos conjuntos.
5. **Monofásico como marca do item**, separada da natureza do ICMS (HI-128).
   O contador marca o item como monofásico de PIS e Cofins. Isso permite o
   caso "ST e monofásico" no mesmo item. Sem marca, o item é tratado como
   normal, o lado conservador. A tabela de NCM fica fora do primeiro corte.
6. **Devolução por segmento** (HI-129, HI-130):
   - a devolução deduz dentro do anexo e do segmento da mercadoria devolvida;
   - o segmento é derivado do item da devolução: CFOP x.201 ou x.410 indica
     produção, x.202 ou x.411 indica revenda, x.410, x.411 ou CSOSN 500
     indicam ST, a marca de monofásico decide o monofásico, e CFOP 3.xxx
     indica exportação;
   - o contador confirma o segmento;
   - o saldo do art. 17, II é carregado por mercado, anexo e segmento, e só o
     mesmo segmento o consome;
   - devolução sem segmento confirmado recusa o pré-DAS do mês, com o motivo
     nomeado. Rateio nunca.
7. **Recusas nomeadas do primeiro corte:**
   - RBT12 acima de R$ 3,6 milhões ou excesso de sublimite (mantido);
   - item com CSOSN 103, 300 ou 400 ("benefício ou imunidade de ICMS sem
     parâmetro estadual", HI-131); CSOSN 900 gera aviso;
   - natureza "combustível" (ICMS fora do DAS e PIS/Cofins concentrados,
     HI-132);
   - serviço em NF-e conjugada (CFOP 5.933);
   - comercial exportadora sem confirmação do contador;
   - atividade com IPI e ISS ao mesmo tempo;
   - outras atividades do art. 25, § 1º, que o corte não cobre.
8. **Tela e API do pré-DAS:** linhas por anexo e segmento, com o tributo
   desconsiderado mostrado como tal, e não como zero digitado.

**Fica fora:** medicamentos manipulados e outras atividades do art. 25, § 1º, que não têm sinal na NF-e (decisão da correção da rodada 1, A5); 6ª faixa e excesso de sublimite (exemplos 9 a 11 do Manual
ficam como referência futura); benefício estadual de ICMS; tabela de NCM
monofásico; combustíveis; leitura do `NFref`; regime de caixa; 2027.

## Decisões para a correção (rodada 1)

A [rodada 1](../auditorias/2026-10-09-dl-082-rodada-1.md) foi **aprovada com
ressalvas**: o cálculo bate ao centavo com o Manual e com o oráculo do
auditor, os meses de serviço ficaram idênticos e os seis mutantes do plano
caem. Decisões do arquiteto para a correção única:

- **A1:** o lote (DL-085) não efetiva devolução: a nota sai do lote com o
  motivo "segmento da devolução a confirmar: escriture esta nota
  individualmente". A recusa do pré-DAS para devolução já efetivada sem
  segmento diz que a nota precisa de estorno.
- **A2:** a devolução com CFOP de devolução de combustível (1.660 a 1.662,
  2.660 a 2.662) recusa o pré-DAS seja qual for a natureza.
- **A3:** CFOP x.503 a x.506 (devolução de venda com fim de exportação)
  pertencem ao mercado externo, na função de mercado, na validação e na
  sugestão do segmento.
- **A4:** a recusa de CSOSN 103, 300 e 400 vale só para o mercado interno.
  Na exportação, o ICMS já é desconsiderado e o benefício estadual não muda
  o cálculo (decisão do arquiteto, reversível).
- **A5:** item com CFOP de prestação de serviço de comunicação ou de
  transporte, sob natureza de mercadoria, recusa com o motivo nomeado. Os
  códigos são conferidos na tabela oficial. Medicamento manipulado fica
  fora, registrado no plano.
- **A6:** aviso para natureza de exportação sem CFOP 7.xxx ou `idDest` 3.
- **A7:** segmento zerado por devolução continua visível, com receita
  líquida 0,00.
- **A8:** a memória da escrituração ganha a chave `st_monofasico`.
- **A9:** o seletor de segmento só oferece os segmentos permitidos para o
  item, por uma função de domínio.
- **A10:** fica a exceção. O serviço mantém o contrato da DL-075 ("0,00 —
  valor zero"); a mercadoria mostra "desconsiderado".
- **A11:** o banner do módulo deixa de dizer que o pré-DAS de comércio não
  existe.
- **A12:** a reclassificação em massa recusa a operação inteira se algum item
  tiver marca ou segmento incompatível com a natureza nova.
- **A13:** teste do limite exato de R$ 3.600.000,00.

## Decisões tomadas na correção

- **A2:** função nova para a devolução de venda de combustível (1.660 a
  1.662 e 2.660 a 2.662). A função da DL-083 também pega a devolução de
  compra.
- **A5:** os códigos seguem a descrição oficial da tabela, que inclui 5.932
  e 6.932 (transporte iniciado em outra UF).
- **A6:** o aviso sai quando falta o CFOP 7.xxx **ou** o `idDest` 3.
- **A9:** `segmentos_permitidos` recebe o CFOP.
- **A12:** a verificação vale para todo item que casa com o filtro.
- **Resíduos para a reconferência:**
  - o botão da recusa de devolução efetivada sem segmento ainda leva a
    "NF-e a escriturar";
  - um segmento que só tem saldo de devolução de meses anteriores não
    aparece no pré-DAS.
- **Medido pelo desenvolvedor:** 9.160/1/55, em 18 min 19 s numa única
  invocação local.

## Critérios de aceite

1. Os exemplos oficiais 1, 2, 3 e 6 do Manual do PGDAS-D batem ao centavo por
   tributo, inclusive o total interno de 9.935,02 do exemplo 6. Os valores
   esperados são escritos à mão nos testes, sem chamar a função de produção.
2. Os casos calculados D, E, F, G e H da consulta (ST com monofásico, ST e
   monofásico no mesmo item, Anexo II com ST e exportação, dois anexos,
   substituto) também batem ao centavo.
3. Segregação sem redistribuição: cada tributo desconsiderado sai zero e os
   demais ficam exatamente como no segmento normal.
4. A devolução deduz no segmento certo. O saldo é transportado por segmento.
   Devolução sem segmento confirmado recusa o pré-DAS.
5. Cada recusa nomeada do item 7 tem teste e mensagem.
6. Os meses só com serviço ficam idênticos ao que eram antes. Os testes da
   DL-075 passam sem mudar a expectativa.
7. Isolamento entre escritórios e empresas, e permissões no servidor.
8. Mutação. Cada um destes defeitos derruba teste:
   - trocar o conjunto desconsiderado de um segmento;
   - somar o `vST` à receita;
   - usar RBT12 por anexo;
   - redistribuir o ICMS desconsiderado;
   - devolução fora do segmento;
   - ignorar a marca de monofásico.
9. Regressão completa numa única invocação. Migração aditiva e reversível, se
   houver.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — cálculo, segregação, devolução por segmento, marca de monofásico, recusas, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/pre_das.py`, `receita.py`, `escrituracao_nfe.py`, modelos e migração, se for preciso; testes `test_dl082_*` |
| B — telas: pré-DAS por anexo e segmento; marca de monofásico e segmento da devolução na escrituração | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge devolve a recusa do pré-DAS em mês com NF-e. A marca de
monofásico e o segmento da devolução, se forem colunas novas, saem com a
reversão da migração.
