# DL-057 — IP real na trilha atrás de proxy

**Demanda:** BL-553 (achado M6 da análise de 30/09/2026); Fred autorizou em
30/09/2026 até 4 agentes paralelos em itens independentes. **Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 1
(trilha de auditoria).

## Problema

`apps/auditoria/services.py:13` grava sempre `REMOTE_ADDR`. Em produção há
proxy reverso (`config/settings.py` ~367), então toda a trilha fica com o IP
do proxy.

## Decisão (`arquiteto-senior`, reversível)

- Uma função única `ip_do_cliente(request)` em `apps/auditoria`, usada pela
  trilha (e disponível para a DL-056).
- `X-Forwarded-For` só é considerado quando `REMOTE_ADDR` está numa lista de
  **proxies confiáveis** configurável (`settings`, vazia por padrão). Nesse
  caso, percorre a lista da direita para a esquerda e pega o primeiro endereço
  que não é proxy confiável. Sem proxy confiável configurado, o cabeçalho é
  ignorado (não se confia em cabeçalho do cliente).
- Endereço inválido → cai para `REMOTE_ADDR`, nunca erro.

## Critérios de aceite

1. Sem proxy confiável: `X-Forwarded-For` forjado é ignorado.
2. Com proxy confiável: grava o IP do cliente; com cadeia de proxies, o
   primeiro não confiável a partir da direita.
3. Cabeçalho malformado, IPv6, espaços → sem erro, IP válido gravado.
4. Todas as gravações da trilha usam a função única (varredura por teste).
5. Suíte completa verde.
