# DL-058 — Pequenas fugas de informação

**Demanda:** BL-554 e BL-555 (achados B1 a B4 da análise de 30/09/2026);
Fred autorizou até 4 agentes paralelos em itens independentes (RC-149).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 1 (isolamento e trilha), de baixa severidade.

## Itens e decisões (`arquiteto-senior`, reversíveis)

1. **B1 — enumeração por `conta_pai`** (`apps/contabilidade/serializers.py`
   ~47 e ~194): id de conta de outro escritório e id inexistente passam a
   receber **a mesma mensagem**.
2. **B2 — defesa em profundidade** (`apps/contabilidade/views_web.py` ~4386):
   a consulta de lançamentos por `id__in` passa a filtrar também pela empresa.
3. **B3 — trilha de falha de login** (`apps/accounts/signals.py` ~19-24):
   o texto digitado no campo de usuário só é gravado se corresponder a uma
   conta existente; caso contrário grava-se apenas um prefixo de HMAC do texto
   normalizado (mesmo método da DL-056, se já disponível; senão, função local
   equivalente), para não gravar uma senha digitada no campo errado.
4. **B4 — autenticação da API explícita** (`config/settings.py`,
   `REST_FRAMEWORK`): declarar `DEFAULT_AUTHENTICATION_CLASSES` só com
   sessão (o produto não usa Basic nem token), desligando o Basic implícito.

## Critérios de aceite

1. B1: mesma resposta e mensagem para id alheio e inexistente (API).
2. B2: teste que forja um id de outra empresa na lista e não o devolve.
3. B3: falha com usuário inexistente não grava o texto digitado; com usuário
   existente grava o nome da conta; nenhuma senha na trilha.
4. B4: requisição com cabeçalho Basic válido não autentica na API.
5. Suíte completa verde.

## Evidências e integração

- Implementação (`desenvolvedor-pleno`, cópia isolada) e integração sobre a
  DL-056: o resumo do nome de usuário na trilha usa a mesma função da DL-056
  (`resumo_do_usuario`, HMAC com `SECRET_KEY`).
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-058-rodada-1.md):
  **aprovada com ressalvas** — B1 a B4 medidos por HTTP; achado relevante: o
  login Basic, que o produto não usa, **autenticava de verdade** em
  `/api/escritorios/` e `/api/escritorio-ativo/` e permitia testar senhas fora
  do limite de tentativas; a DL-058 fechou esse canal. Suíte com 4.148
  aprovados e a falha conhecida de Python 3.13. Ressalvas: BL-592 a BL-596.
- Decisão registrada (J3): DE-096.

