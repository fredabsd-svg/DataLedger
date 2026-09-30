# DL-056 — Limite de tentativas no login e no cadastro

**Demanda:** BL-552, parte 1 (achado M5 da análise de 30/09/2026); Fred
autorizou em 30/09/2026 até 4 agentes paralelos em itens independentes.
**Fora do escopo:** prova de titularidade do CNPJ no cadastro (depende de
decisão do Fred). **Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 2.

## Problema

`apps/accounts/views.py` (login) e o cadastro de novo escritório não limitam
tentativas: força bruta de senha e cadastro em massa são possíveis.

## Decisão (`arquiteto-senior`, reversível)

- Sem dependência nova: contagem persistida no **banco** (funciona com vários
  processos do gunicorn; cache local por processo não serviria).
- Login: após N falhas na janela J para o mesmo usuário digitado, **ou** para
  o mesmo IP, recusa temporária com mensagem genérica (sem dizer se o usuário
  existe). Valores iniciais N=5 por usuário e 20 por IP, J=15 min,
  configuráveis em `settings` — hipótese a validar com o Fred.
- Cadastro de escritório: limite por IP (ex.: 5 por hora), configurável.
- Sucesso de login zera a contagem daquele usuário.
- IP obtido pela mesma função da trilha (se a DL-057 ainda não estiver
  integrada, usar `REMOTE_ADDR` e deixar o ponto único anotado).
- A tentativa bloqueada é registrada na trilha sem gravar a senha nem o texto
  digitado no campo de usuário (ver BL-555, B3).

## Critérios de aceite

1. N falhas → próxima tentativa, mesmo com senha correta, recusada até a
   janela passar (relógio controlado); depois da janela → aceita.
2. Limite por IP vale entre usuários diferentes.
3. Mensagem idêntica para usuário existente e inexistente.
4. Cadastro acima do limite por IP → recusado sem criar nada.
5. Suíte completa verde; migração aplica e reverte.
