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

## Evidências e integração

- Implementação (`desenvolvedor-pleno`, cópia isolada): modelo
  `TentativaDeAcesso` e migração `accounts.0002`; reserva da tentativa sob
  lock consultivo antes de verificar a senha (duas requisições simultâneas não
  passam do limite); bloqueio com a mesma mensagem e o mesmo status do login
  inválido; chave do usuário por HMAC; cadastro acima do limite → 429 com
  `Retry-After`; limpeza oportunista de registros vencidos.
- Integração sobre a DL-057: IP por `ip_do_cliente`; **sem IP conhecido, o
  limite por IP não é aplicado** (só o por usuário), para que um proxy mal
  configurado não bloqueie o login de todos; guarda única por AST sobre todo
  `apps/` contra leitura direta de IP e gravação direta na trilha (fecha a
  ressalva F2 da DL-057, BL-578).
- Testes: 24 da implementação, mais 11 casos da integração; mutação: sem a
  comparação com o limite, 15 reprovam; sem a trava consultiva, os de
  concorrência reprovam; leitura de IP fora da função única reprova a guarda.
- Suíte completa na versão integrada (`3ba0a3d`): **4.134 aprovados, 50
  pulados, 1 reprovado** (o conhecido de Python 3.13).
- Nível 2: sem auditoria independente obrigatória (AGENTS.md §3.1).
- **Hipótese a validar com o Fred:** os limites (5 falhas por usuário e 20 por
  IP em 15 minutos; 5 cadastros por IP por hora). Quem errar 5 vezes o usuário
  de outra pessoa a bloqueia por até 15 minutos — limite inerente ao bloqueio
  por usuário.
- Não testado: navegador real; implantação com vários processos gunicorn
  (a concorrência foi provada com conexões PostgreSQL reais).

