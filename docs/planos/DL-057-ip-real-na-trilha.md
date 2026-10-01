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

## Evidências

Implementação (`desenvolvedor-pleno`, cópia isolada, integrada por
cherry-pick): `apps/auditoria/ip.py` (`ip_do_cliente`), `registrar` usando a
função única, `PROXIES_CONFIAVEIS` lida de `DJANGO_PROXIES_CONFIAVEIS` (vazia
por padrão; entrada que não seja IP ou CIDR impede a subida) e a variável no
`.env.example`.

- Achado do implementador: o Python aceita IPv6 com escopo
  (`2001:db8::1%eth0`), texto controlado por quem faz a requisição; passou a
  ser tratado como malformado, com teste.
- `REMOTE_ADDR` em código de produção só existia em
  `apps/auditoria/services.py`; nenhum outro ponto lê `X-Forwarded-For`.
- Suíte completa (PostgreSQL, Python 3.13): **3.916 aprovados, 50 pulados,
  1 reprovado** (o conhecido de Python 3.13). Mutação: voltar a
  `REMOTE_ADDR` → 4 reprovam; ignorar a lista confiável → 8; percorrer o
  cabeçalho da esquerda → 7.
- **Operação:** em produção, `DJANGO_PROXIES_CONFIAVEIS` precisa receber o
  IP ou a rede do proxy que fala com o Django; sem isso a trilha continua
  com o IP do proxy.
- Não testado: proxy real (nginx); Python 3.14 (CI).

## Integração

[Auditoria rodada 1](../auditorias/2026-10-01-dl-057-rodada-1.md):
**aprovada com ressalvas**, sem bloqueador. Integrada pela autorização do
Fred (RC-150). F2 é resolvida na integração da DL-056 (BL-578); F1 é
obrigatória antes da implantação (BL-577); F3 a F6 e a observação O1 estão
no backlog (BL-579 a BL-583).

