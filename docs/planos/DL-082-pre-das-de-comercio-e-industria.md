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

**Fica fora:** 6ª faixa e excesso de sublimite (exemplos 9 a 11 do Manual
ficam como referência futura); benefício estadual de ICMS; tabela de NCM
monofásico; combustíveis; leitura do `NFref`; regime de caixa; 2027.

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
