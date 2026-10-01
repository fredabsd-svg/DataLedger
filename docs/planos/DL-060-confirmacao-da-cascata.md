# DL-060 — A reabertura em cascata confirma exatamente os meses mostrados

**Demanda:** achados H1 e H2 da [auditoria da DL-054](../auditorias/2026-10-01-dl-054-rodada-1.md)
(BL-588, BL-589); Fred autorizou o merge com auditoria e CI verdes (RC-150).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 1 (mês encerrado, possivelmente já pago, não reabre sem
consentimento).

## Problema

A tela de reabrir em cascata mostra os meses encerrados seguintes, mas o
POST só manda "confirmo a cascata". Se outra pessoa encerrar mais um mês
entre a tela e o clique, ele é reaberto junto, sem ter constado da
confirmação. O mesmo vale para a API com `cascata: true`.

## Decisão (`arquiteto-senior`, reversível)

1. A cascata recebe a **lista de meses confirmados**. A tela envia a lista
   que mostrou (campo oculto); a API aceita `meses_confirmados` (lista de
   `{ano, mes}`) junto de `cascata: true`.
2. O serviço lê o conjunto de meses encerrados posteriores **sob lock** e
   compara com a lista confirmada. Se divergir (mês a mais **ou** a menos),
   recusa com 409 (`ReaberturaExigeCascata`, com a lista atual) e não
   altera nada; a tela volta ao formulário com a lista nova.
3. API sem `meses_confirmados` com `cascata: true` → 400 (o contrato
   passa a exigir a lista; não há cliente externo da API hoje).
4. Testes de concorrência que faltavam (H2): reabrir simples × encerrar mês
   posterior nas duas ordens, e a asserção de estado final no teste de duas
   cascatas.
5. API com `meses_confirmados` **sem** `cascata: true` → 400. Lista de
   confirmação sem pedido de cascata é pedido ambíguo; recusar é mais seguro
   que ignorá-la. Decisão do `desenvolvedor-pleno` na implementação,
   aceita pela auditoria (L5) e registrada aqui.

## Critérios de aceite

1. Tela: mês encerrado entre o GET e o POST → 409, nenhum mês alterado,
   formulário com a lista atual; sem divergência → reabre exatamente os
   mostrados.
2. API: lista divergente → 409 sem efeito; lista ausente com cascata → 400;
   lista malformada → 400.
3. Testes da H2 implementados e discriminantes por mutação.
4. Papéis, isolamento e trilha como na DL-054; suíte completa verde.

## Evidências e integração

- Implementação (`desenvolvedor-pleno`, cópia isolada) sobre a DL-059: a
  tela envia os meses mostrados em campo oculto; a API exige
  `meses_confirmados` com `cascata: true`; o serviço compara a lista com os
  meses encerrados posteriores **sob lock** e recusa com 409 se divergir.
  `services.py` não mudou na correção.
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-060-rodada-1.md):
  **aprovada com ressalvas** — L1 (nenhum teste guardava a comparação sob
  lock) a L5 (registro documental).
- [Reconferência](../auditorias/2026-10-01-dl-060-reconferencia.md):
  **aprovada com ressalvas**, parecer final — L1 a L4 fechados e provados
  por mutação; L5 cumprido nesta integração; M1 (força de um caso de teste)
  no BL-602. Suíte com 4.269 aprovados e a falha conhecida de Python 3.13.
