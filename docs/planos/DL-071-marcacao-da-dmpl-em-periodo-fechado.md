# DL-071 — A marcação manual da DMPL respeita o período fechado

**Demanda:** ordem do Fred de 08/10/2026, *"Próxima etapa"* (RC-163), dita
depois da integração da DL-070. **Estado:** [fonte única](../agents/estado.md).
**Branch:** `ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1) — é o
documento entregue ao cliente. Auditoria independente com uma rodada, uma
correção e uma reconferência.

## Por que esta etapa, e não a DFC fatia 2

A fila do estado punha a DFC fatia 2 (método direto) em primeiro lugar. O
diagnóstico dela, em 08/10/2026, encontrou e **reproduziu por execução** um
defeito de nível 1 na peça que a DFC ia copiar "no molde exato": a marcação
manual por lançamento da DMPL (`MarcacaoDmpl`, DL-061 fatia 2, BL-605) **não
consulta o estado da competência**. É o mesmo critério que escolheu a DL-062:
o ponto aberto de nível 1 em que o produto entrega documento errado vai
primeiro. A DFC fatia 2 continua na fila e depende de decisões do Fred
(classes de recebimento e pagamento), já levantadas no texto oficial do
CPC 03 (R2).

## Problema (medido)

Reprodução do `auxiliar-verificacao` em PostgreSQL 16, 08/10/2026, competência
02/2026 encerrada **ou** entregue, 12 combinações (trocar, remover, marcar
pela primeira vez × serviço e API):

| Tentativa | Aceita? | Efeito na DMPL já apurada do período |
| --- | --- | --- |
| Trocar a marcação | Sim, 200 | alienação 1.300,00 → 300,00; aquisição −2.200,00 → −1.200,00 |
| Remover a marcação | Sim, 200 | `pode_emitir` True → **False** (veto retroativo) |
| Marcar lançamento sem marcação | Sim, 200 | `pode_emitir` False → **True** |

No mesmo cenário, `classificar_conta_na_dmpl` recusa com
`ClassificacaoAlteraPeriodoFechado` — a trava da DL-065 funciona onde foi
posta, e a marcação ficou fora dela.

## Regra (decisão do arquiteto, derivada de regra já confirmada)

A DL-065 (BL-550) fixou que **a demonstração de um período encerrado ou
entregue não muda retroativamente** por ato de classificação. A marcação
manual é um ato de classificação **por lançamento**, com o mesmo efeito. Esta
etapa estende a regra, sem criar regra contábil nova:

1. Gravar, trocar ou remover a marcação da DMPL de um lançamento é **recusado**
   quando alguma DMPL que lê esse lançamento pertence a período encerrado ou
   entregue.
2. **Quais DMPL leem o lançamento** sai da MESMA definição de período que
   `apurar_dmpl` usa (início do exercício até o mês pedido). O implementador
   mede essa definição no código e a reusa — *guarda que filtra por critério
   diferente do que a apuração filtra é guarda que pode ser contornada*
   (lição A1 da DL-065). Consequência esperada: lançamento de fevereiro com
   março encerrado no mesmo exercício também é recusado, mesmo com fevereiro
   aberto.
3. A competência é achada **pela data** do lançamento, não pela FK (anulável
   em dado legado — A1 da DL-065).
4. A recusa vira **409** na API e mensagem na tela, pelo mesmo caminho de
   tradução da DL-065. A mensagem **distingue** competência encerrada (pode
   ser reaberta) de entregue (não reabre, RC-101) — lição A3 da DL-065: nunca
   mandar o contador fazer algo que o sistema recusa.
5. A leitura do estado é protegida contra corrida com o fechamento pelo
   primitivo do módulo, `_travar_competencia_em_modo_compartilhado`
   (`FOR SHARE`) — lição A2 da DL-065 — e o estouro de `lock_timeout` não
   pode virar 500 (lição N1 da DL-065).
6. Custo constante: o número de consultas da guarda não cresce com o
   histórico de competências (lição N2 da DL-065).
7. Toda porta de escrita da marcação passa pela regra: serviço, API e tela.
   Se `MarcacaoDmpl` tiver admin que grava, ele também (lição E1 da DL-065).

## Critérios de aceite

1. Com a competência do lançamento **encerrada**: trocar, remover e marcar
   pela primeira vez são recusados no serviço (exceção própria do período
   fechado) e na API (**409**); nada é gravado; a DMPL apurada do período é
   idêntica antes e depois.
2. Idem com a competência **entregue**, e a mensagem não manda reabrir.
3. Com a competência do lançamento **aberta** e uma competência **posterior do
   mesmo exercício encerrada**: recusado (regra 2). Com a posterior em
   **outro exercício**: aceito — se a medição do código mostrar que a DMPL do
   exercício seguinte não lê o lançamento.
4. Com todas as competências relevantes abertas: o comportamento atual da
   marcação continua igual (testes da DL-061 verdes, sem alterar expectativa).
5. Competência **reaberta** depois de encerrada: aceito.
6. Tela: a recusa aparece na guia de marcação com a mensagem, status 200, sem
   gravar.
7. Corrida: fechamento concorrente com a marcação não termina com o período
   encerrado e a marcação trocada (teste com duas threads e
   `django_db(transaction=True)`, que só roda de verdade em PostgreSQL).
   **Exceção aceita depois da auditoria:** competência que ainda não tem
   linha no banco não é travada (A5, BL-657 — ver "Limite aceito" abaixo).
8. `lock_timeout` estourado responde 409 (ou recusa na tela), nunca 500.
9. Isolamento: lançamento de outra empresa ou de outro escritório continua
   404, antes de qualquer consulta de período.
10. Consultas da guarda constantes com 1 e com 24 competências encerradas.
11. Mutação: sem a guarda, os testes 1, 2 e 3 caem.
12. Não regressão: suíte completa sem reprovação nova contra a linha de base
    da DL-070 (5.021 aprovados, 1 reprovado de ambiente, 53 pulados);
    `ruff`, `check` e `makemigrations --check` limpos.

## Fora do escopo, registrado

- Gatilho de banco para a tabela da marcação (como a DL-069 fez para o
  lançamento): a trava desta etapa é de aplicação. Registrar como limite.
- Se a auditoria constatar que a **reclassificação de conta** da DL-065 tem o
  mesmo furo da regra 2 (mês posterior encerrado no exercício), vira item de
  backlog próprio, não escopo desta etapa.
- DFC fatia 2: a `MarcacaoDfc` herdará esta regra quando for feita.

## Limite aceito depois da auditoria

**Competência sem linha (A5, BL-657).** A guarda trava as competências da
janela que **existem** no banco. Marcar um lançamento e, no mesmo instante,
encerrar um mês posterior do exercício que nunca teve lançamento (e portanto
não tem linha) termina com o mês encerrado e a marcação trocada — medido pelo
auditor. O arquiteto aceitou o limite em 08/10/2026: exige simultaneidade
sobre um mês sem movimento, e as duas correções possíveis (criar linhas de
competência só para travar, ou mudar o encerramento) mexem no núcleo de
nível 1 fora do escopo desta etapa.

## Segurança, dados e reversão

Sem migração prevista. Nenhum dado gravado muda; a etapa só recusa escrita.
Reverter é reverter o commit.

## Equipe

| Papel | Modelo | Função |
| --- | --- | --- |
| `arquiteto-senior` | Opus | plano, integração, registro |
| `desenvolvedor-pleno` | Sonnet (RC-143) | implementação e testes |
| `auditor-qa` | Sonnet | auditoria independente da versão integrada |

O Haiku da RC-160 não implementa aqui: a HI-53 limitou-o à DL-070, e esta
etapa é nível 1.

## Evidências

Ver a seção desta etapa no [estado](../agents/estado.md) e os relatórios em
`docs/auditorias/`.
