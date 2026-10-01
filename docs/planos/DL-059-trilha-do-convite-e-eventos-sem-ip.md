# DL-059 — Trilha do convite e eventos sem IP

**Demanda:** BL-560, BL-566 e BL-579 (achados das auditorias da DL-052 e da
DL-057); Fred autorizou até 4 agentes paralelos em itens independentes
(RC-149) e o merge com auditoria e CI verdes (RC-150).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 1 (trilha de auditoria).

## Itens e decisões (`arquiteto-senior`, reversíveis)

1. **BL-566 — recusa de convite na trilha:** convite vencido, de e-mail
   divergente ou para usuário já vinculado gera o evento
   `convite.escritorio.recusado` com `convite_id` e `motivo`
   (`vencido`, `email_divergente`, `ja_vinculado`), **sem** o e-mail de
   ninguém. Como a recusa acontece dentro de uma transação que é desfeita, o
   registro é gravado fora dela (depois do rollback), para não sumir junto.
2. **BL-560 — convite já consumido:** a tela do convite consumido informa
   que ele já foi usado e não oferece o botão "Aceitar" (o POST já recusava).
3. **BL-579 — eventos sem IP:** os seis chamadores de `registrar` sem
   `request` passam a informar a origem: as duas views de ativar escritório
   (`apps/tenancy/views.py` ~199 e ~875) passam `request`; os serviços de
   primeiro acesso, convite emitido e aceito
   (`apps/tenancy/services/primeiro_acesso.py`) e de envio fiscal recebido
   (`apps/fiscal/services.py` ~946) recebem `request` opcional dos seus
   chamadores web e o repassam.

## Critérios de aceite

1. Cada motivo de recusa gera exatamente um evento de trilha, com motivo e
   sem e-mail; nenhum vínculo criado; convite não consumido.
2. GET de convite consumido não mostra o botão e explica; POST continua
   recusado.
3. Os seis eventos gravam o IP da requisição (teste por evento, com
   `REMOTE_ADDR` conhecido); chamadas sem request continuam funcionando.
4. Suíte completa verde.

## Evidências e integração

- Implementação (`desenvolvedor-pleno`, cópia isolada) sobre a DL-058: o
  evento `convite.escritorio.recusado` é gravado **fora** do bloco atômico
  revertido, com o motivo e sem e-mail nem token; os eventos que saíam sem IP
  passam a receber o `request` e usam a função única `ip_do_cliente`.
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-059-rodada-1.md):
  **aprovada com ressalvas** — recusa sobrevive ao rollback real, corrida de
  aceite resiste, IP gravado em todos os eventos inclusive com
  `X-Forwarded-For` forjado. Suíte com 4.170 aprovados e a falha conhecida de
  Python 3.13. Ressalvas: BL-597 a BL-601.
- Decisão registrada (K1): se a própria trilha falhar ao gravar a recusa, a
  resposta é erro 500 (*fail-closed*, isto é, falha sem liberar nada). A
  recusa de negócio já foi revertida antes; perder o evento seria pior que
  mostrar a tela de erro. Teste que documente isso fica no BL-597.
