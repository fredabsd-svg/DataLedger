# DL-085 — Fiscal: escrituração de NF-e e NFC-e em volume

**Demanda:** resposta do Fred de 09/10/2026 (RC-173, item 2): o escritório
recebe NFC-e em **alto volume**. A RC-173 também diz que há muitos clientes do
Presumido com NF-e em 2026 (item 7) e que há posto, distribuidora e TRR
(item 3). **Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1), porque efetiva
receita em lote. A auditoria faz uma rodada, uma correção e uma
reconferência. **Executa depois da [DL-083](DL-083-receita-de-nfe-no-presumido.md)
e antes da [DL-082](DL-082-pre-das-de-comercio-e-industria.md).**

## O problema

A escrituração da [DL-081](DL-081-escrituracao-das-nfe-de-saida.md) é feita
nota a nota: rascunho, natureza por item e efetivação. Um posto emite
milhares de NFC-e por mês. Nota a nota, o contador não fecha o mês. E sem
efetivação a receita não entra no Simples nem no Presumido (DL-083).

O envio aceita 2.000 arquivos e 50 MB (HI-22). Esses limites foram medidos
com NFS-e, não com NFC-e.

## Escopo

1. **Prévia do mês em lote.** Para a empresa e o mês, o produto agrupa as
   notas elegíveis ainda não efetivadas por tipo, CFOP, CST ou CSOSN e
   natureza sugerida. Cada grupo mostra a quantidade de notas e de itens e o
   valor de receita, pela função de receita da DL-083. Ficam **fora do
   lote**, listadas com o motivo:
   - nota com item sem sugestão ou com sugestão em conflito;
   - nota ilegível;
   - nota que não fecha a conferência W16;
   - nota de 2027 (HI-133).
2. **Confirmação em bloco** (HI-118 já previa "confirmada em bloco pelo
   contador"). O contador aceita a sugestão de cada grupo, ou escolhe outra
   natureza permitida para o grupo, e confirma o lote.
   - A confirmação leva a **assinatura da prévia**, como na reclassificação
     em massa da DL-081.
   - Se as notas mudaram desde a prévia, a confirmação recusa com 409 e
     pede uma prévia nova.
   - Nada é efetivado sem a confirmação explícita.
3. **Efetivação em lote, idempotente e em partes.** Cada nota continua com
   a sua `EscrituracaoNFe`, com as mesmas regras e a mesma trilha da
   efetivação nota a nota: nenhum atalho na regra.
   - O lote roda em partes de tamanho medido, para caber no tempo do
     servidor de aplicação. Cada chamada devolve "efetivadas X, restam Y".
   - Repetir a chamada não duplica nada.
   - Uma trilha do lote registra quem confirmou, a assinatura, as
     quantidades e os grupos.
   - Mês já confirmado vira "a retificar", como hoje.
4. **Medida de volume.** Medir com NFC-e sintéticas: 10.000 notas num mês,
   de um a cinco itens cada, numa empresa.
   - Medir a prévia, cada parte da efetivação, a conferência do mês, a
     composição da receita e a apuração do Presumido.
   - Medir também o envio de 2.000 NFC-e.
   - Registrar os tempos no plano.
   - Se o limite de arquivos do envio puder subir com segurança, propor o
     novo número com a medida; senão, manter e registrar.
5. **Telas:**
   - prévia por grupo, com o valor e a natureza;
   - lista das notas fora do lote, com o motivo;
   - botão de confirmar, com o progresso das partes.

**Fica fora:** processamento em segundo plano (fila), que só entra se a
medida mostrar que as partes não bastam; apuração do ICMS; NFC-e em
contingência sem protocolo, que continua recusada (HI-110).

## Critérios de aceite

1. A prévia agrupa certo e lista cada nota fora do lote com o motivo.
2. A confirmação com assinatura desatualizada recusa com 409, sem efetivar
   nada.
3. A efetivação em lote produz, nota a nota, exatamente o mesmo resultado da
   efetivação individual: mesma receita, mesma natureza, mesma trilha. O
   teste compara os dois caminhos sobre as mesmas notas.
4. Interromper o lote no meio e repetir completa sem duplicar.
5. A receita do mês e o Presumido do trimestre batem com a soma das notas
   efetivadas.
6. Isolamento entre escritórios e empresas: o lote de uma empresa nunca
   toca nota de outra. Permissões no servidor.
7. Os tempos medidos ficam registrados, e cada parte cabe no tempo do
   servidor com folga.
8. Mutação. Cada um destes defeitos derruba teste:
   - efetivar nota fora do lote;
   - ignorar a assinatura;
   - pular a conferência W16 no lote;
   - efetivar duas vezes.
9. Regressão completa numa única invocação. Migração aditiva e reversível,
   se houver.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — prévia, confirmação, efetivação em partes, trilha, medida, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/escrituracao_nfe.py` ou módulo novo `escrituracao_nfe_lote.py`, `api_escrituracao_nfe.py`, `models.py` e migração, se for preciso; testes `test_dl085_*` |
| B — telas | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge tira a prévia e o lote. As escriturações efetivadas em lote
continuam válidas, porque são as mesmas da efetivação individual.
