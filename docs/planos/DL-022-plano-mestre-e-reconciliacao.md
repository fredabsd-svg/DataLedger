# DL-022 — Plano mestre de evolução e reconciliação do estado

**Estado:** **em validação, no PR #23.** Aberta em 2026-09-16, a partir da `main`
em `b8c66a6` (PR #22 integrado). As cinco verificações da integração contínua
ficaram verdes na revisão `40bc0c2`, lidas pelos `check-runs` daquela revisão
exata. A situação atual mora no
[estado](../agents/estado.md) — este plano não a repete.

**Natureza da etapa:** **documental.** Nenhuma linha de código de produto,
nenhuma migração, nenhum teste novo de negócio. O que entra é plano, registro
de decisão e correção de documentação divergente.

## Como isto apareceu

O Fred entregou, em 2026-09-16, um **plano mestre de evolução por módulos**
produzido sobre a revisão `b8c66a6` — a mesma `main` que existe hoje — e pediu:
*"análise e suba para o GitHub, e lembre de atualizar o README e a landing page
do GitHub"*. No DataLedger a landing page **é** o `README.md`; não há
`gh-pages` nem site publicado, e isso foi conferido nesta data.

O documento não é só um roteiro: ele **mediu** o repositório e encontrou
divergências reais na nossa documentação. Três delas são erro nosso, e são o
motivo de esta etapa existir além da simples incorporação do arquivo.

## Objetivo

1. Incorporar o plano mestre ao repositório **sem editar uma linha do texto do
   Fred**, com a análise do `arquiteto-senior` acrescentada **depois** dele.
2. Fechar as divergências que o documento mediu, para que a documentação pare
   de se contradizer.
3. Registrar a regra que impede o próprio plano mestre de virar o próximo lugar
   onde o estado do projeto diverge.

## Requisitos

### Confirmados

| # | Requisito | Origem |
| --- | --- | --- |
| 1 | O plano mestre entra no repositório **preservado integralmente**. | Regra do projeto para texto de terceiro (a mesma dos relatórios de auditoria) |
| 2 | A análise do arquiteto vem **depois** do texto preservado, sem alterá-lo. | Idem |
| 3 | O `README.md` é a landing page do GitHub e precisa ser atualizado. | Pedido literal do Fred, 2026-09-16 |
| 4 | A direção de sequência (corrigir bloqueadores e intercalar Contabilidade com recepção/conferência de NFS-e) fica registrada como **RC-87**. | Plano mestre, seção 4; ver a ressalva (d) das notas quanto à origem |

### Hipóteses declaradas

| # | Hipótese | Como validar |
| --- | --- | --- |
| H1 | A falha reproduzida em SQLite/Python 3.12 descrita na seção 2 do plano mestre existe como descrita. | Repetir o ensaio; não foi repetido nesta etapa |
| H2 | Os percentuais do acervo fiscal continuam válidos. | Já eram medição de **uma** amostra (RC-65/RC-76); não foram recontados |

### Pendência aberta

| # | Pendência | Impacto |
| --- | --- | --- |
| **PE-47** | A "primeira fila de execução" da seção 16 é **ordem aprovada** ou recomendação? | Decide qual é a próxima etapa de código. Sem a resposta, a sequência que vale continua sendo a do `estado.md` — que hoje coincide com a fila nos dois primeiros itens |

## Escopo

1. **`docs/projeto/plano-mestre.md`** — preâmbulo curto, o documento do Fred
   preservado byte a byte, e as notas do `arquiteto-senior` ao final.
2. **`README.md`** — desduplicar a DL-020; marcar a DL-021 como concluída;
   acrescentar a DL-022; apontar o plano mestre na navegação e na lista de
   leitura de quem chega.
3. **`docs/agents/estado.md`** — cabeçalho na revisão certa; DL-021 como
   **integrada (PR #22)**; DL-022 na tabela de etapas; "Próximo passo" e
   "Estado do repositório" atualizados.
4. **`docs/planos/DL-021-robustez-do-gerador-no-windows.md`** — o cabeçalho
   passa a dizer o que aconteceu: **integrada, com a pendência de permissão no
   Windows declarada e ainda aberta**.
5. **`docs/projeto/decisoes.md`** — **DE-041**: o plano mestre é mapa, não fonte
   de estado.
6. **`docs/projeto/requisitos.md`** — **RC-87** e **PE-47**.
7. **`docs/projeto/backlog.md`** — nota de precisão na **BL-211** sobre a
   ordenação do histórico de regime, **acrescentada sem apagar** o texto do
   auditor.

## Fora do escopo

- Qualquer alteração em `apps/**`, `config/**`, `scripts/**` ou `templates/**`.
- Transformar as linhas das tabelas do plano mestre em itens de backlog. Elas
  são endereços de um mapa; trabalho executável nasce como etapa `DL-xxx`.
- Corrigir a BL-83, a BL-211 ou qualquer bloqueador de implantação. Eles
  continuam abertos e **nomeados**; esta etapa não os toca.
- Fechar a **BL-02** (proteção da `main`): é ação administrativa do Fred.
- Reescrever relatório de auditoria para concordar com o plano mestre. Onde o
  plano corrige um achado, a correção entra como **nota acrescentada**.

## Critérios de aceite

1. `docs/projeto/plano-mestre.md` contém o texto entregue pelo Fred **byte a
   byte**, verificável por comparação com o arquivo original.
2. Nenhuma etapa aparece simultaneamente como não iniciada e integrada, em
   nenhum documento do repositório (é o critério ORG-01 do próprio plano
   mestre).
3. A DL-020 aparece **uma vez** no roadmap do README.
4. A DL-021 aparece como integrada no README, no `estado.md` e no cabeçalho do
   seu próprio plano — **com a pendência de permissão no Windows preservada**,
   e não como "compatibilidade Windows comprovada".
5. A nota de precisão da BL-211 **acrescenta** e não substitui: o texto
   original do achado do auditor continua legível.
6. `ruff check`, `ruff format --check`, `manage.py check`, `pytest` e
   `validate-docs` passam na revisão que for ao PR, e os `check-runs` dessa
   revisão exata são lidos antes de qualquer declaração de "verde".
7. O corpo do PR traz o atestado de leitura do `AGENTS.md`, a caixa de estado e
   a referência `DL-022` — o check "Regras do projeto" reprova sem isso.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `arquiteto-senior` | `docs/projeto/plano-mestre.md`, `docs/planos/DL-022-*.md`, `docs/planos/DL-021-*.md` (apenas o cabeçalho de estado), `README.md`, `docs/agents/estado.md`, `docs/projeto/decisoes.md`, `docs/projeto/requisitos.md`, `docs/projeto/backlog.md` |
| Demais papéis | Nada nesta etapa |

Etapa de um responsável só, em série: não há dois agentes no mesmo arquivo.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`, reiniciada
  a partir de `origin/main` em `b8c66a6`.
- **Branch de destino:** `main`, por PR.
