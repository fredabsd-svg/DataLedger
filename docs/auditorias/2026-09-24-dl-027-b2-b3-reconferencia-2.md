# Reconferência independente DL-027 B2/B3 — rodada 2

Transcrição literal do parecer recebido do auditor independente:

```text
## Parecer: **APROVADO**

Reconferência única da §3.1 no commit exato **`befd65263a8aabee786db0943f1705b42fb972cb`**, branch `fix/dl-027-b2-b3-audit`. O clone e o worktree temporários terminaram limpos; a cópia fonte permaneceu no mesmo commit e sem alterações locais.

### Achados da rodada 1

1. **Veto 409:** corrigido. A view retorna uma página de recusa dedicada, sem contexto de apuração, totais, carimbo ou template imprimível do Balancete ([views_web.py](/home/fred/Documentos/DataLedger/apps/contabilidade/views_web.py:2542), [balancete_emissao_recusada.html](/home/fred/Documentos/DataLedger/templates/contabilidade/balancete_emissao_recusada.html:1)). O teste força a divergência e verifica ausência de linhas, totais, carimbo e tabela, além da diferença `0,01` e da orientação `Verifique` ([test_dl027_fatia_b1_bloqueia_emissao_balancete.py](/home/fred/Documentos/DataLedger/apps/contabilidade/tests/test_dl027_fatia_b1_bloqueia_emissao_balancete.py:147)). O template de recusa não contém o timbre do Balancete.

2. **Filtro de abertura:** corrigido. `com_movimento` agora retém contas com movimento consolidado no período ou saldo líquido de abertura não zero; lançamentos históricos compensatórios não contam como saldo ([services.py](/home/fred/Documentos/DataLedger/apps/contabilidade/services.py:1800)). Testes cobrem abertura compensada, abertura não zero e sintética com movimento de filha ([test_dl027_fatia_b2_criterio_impresso.py](/home/fred/Documentos/DataLedger/apps/contabilidade/tests/test_dl027_fatia_b2_criterio_impresso.py:230)). A regra é rotulada no formulário e no resumo do Balancete; este fica fora do formulário que o CSS de impressão oculta.

### Verificações executadas

No clone isolado, com Python 3.12.3 e SQLite temporário:

- Testes DL-027, regressões de telas, impressão, veredito e isolamento de Balancete: **98 passaram**, 34 avisos sobre indisponibilidade de locks PostgreSQL no SQLite.
- `ruff check .`: passou.
- `ruff format --check .`: **225 arquivos já formatados**.
- `python manage.py check`: nenhum problema.

Repeti M5, M5b e M5c, um por vez, em um `git worktree` isolado no mesmo commit. Cada mutante fez falhar o teste A4 no assert esperado: mensagem de erro ausente, diferença em pt-BR ausente e orientação ausente, respectivamente. Restaurei `views_web.py` ao HEAD após cada execução; o worktree terminou limpo. A documentação da prova consta no plano B.2, linhas 180–183.

O líder também reportou **238 testes direcionados/regressões** em PostgreSQL 16 e Python 3.14.7, além de lint, formatação e `manage.py check`; não repeti essa execução.

### Limite

Não medi PDF/paginação A4 real nesta reconferência: as verificações de `chromium`, `google-chrome` e variantes no `PATH` não encontraram navegador, e `scripts/medir_impressao.py` não foi executado. A presença imprimível do critério foi conferida pelo HTML/CSS e pelos testes; a paginação física continua sem nova medição independente.
```
