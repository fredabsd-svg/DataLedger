# DL-055 — O papel Cliente não vê a carteira do escritório

**Demanda:** BL-549 (achado M2 da análise de 30/09/2026); Fred autorizou em
30/09/2026 o trabalho em até 4 agentes paralelos sobre itens independentes
do backlog. **Estado:** [fonte única](../agents/estado.md). **Branch:**
`claude/zealous-goldberg-jr5ggu` → `main`, integrada uma etapa por vez.
**Risco:** nível 1 (isolamento de dados entre clientes).

## Problema

`apps/empresas/views.py` (GETs de lista e detalhe de empresa e
estabelecimentos, ~216-222, ~441-452, ~555-566) e a tela (~718) exigem só
`TemEscritorioAtivo`. Um usuário com papel CLIENTE recebe 200 com razão
social e CNPJ/CPF de **todos** os clientes do escritório, contra a DE-020 §4
(sigilo de cliente contra cliente). Nas contas ele já recebe 403.

## Decisão (`arquiteto-senior`, reversível)

O papel CLIENTE não lê o cadastro de empresas nem de estabelecimentos, pela
API e pela tela: **403, sem revelar se o id existe**. Não existe hoje vínculo
entre usuário CLIENTE e uma empresa específica; quando existir (portal do
cliente), o acesso restrito à própria empresa entra em etapa própria. Os
demais papéis mantêm exatamente o acesso atual.

## Critérios de aceite

1. CLIENTE em cada GET de empresa/estabelecimento (lista, detalhe, filtros)
   pela API e pela tela → 403; nenhum dado de empresa no corpo.
2. Os outros 5 papéis → comportamento idêntico ao atual (teste de matriz).
3. Id existente e inexistente devolvem a mesma resposta ao CLIENTE.
4. Escrita já recusada ao CLIENTE continua recusada.
5. Suíte completa verde em PostgreSQL.

## Evidências e integração

- Servidor (`desenvolvedor-pleno`): `apps/empresas/permissoes.py` com
  `PAPEIS_QUE_LEEM_CARTEIRA` apontando para a mesma lista da contabilidade;
  403 ao Cliente em toda leitura da API e das telas de empresas, inclusive a
  troca de seção, que antes revelava a existência do id.
- Tela (`especialista-frontend`): menu, links de troca, indicador e atalhos
  do Início e botão da página 403 coerentes para quem não lê a carteira.
- Dois testes antigos mudaram de expectativa porque afirmavam o defeito
  ("o Cliente lista empresas"); a auditoria confirmou que não é afrouxamento.
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-055-rodada-1.md):
  **aprovada com ressalvas** — varredura de 95 rotas e 6.251 requisições do
  Cliente sem nenhum dado de empresa; os outros 5 papéis idênticos; 12
  mutações detectadas; suíte com 3.963 aprovados e a falha conhecida de
  Python 3.13. Ressalvas no backlog: BL-584 a BL-587.
- Decisão registrada: DE-095.

