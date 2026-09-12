# DataLedger

Sistema contábil brasileiro com inteligência artificial e integração MCP, planejado para reunir Fiscal, Folha de Pagamento, Contabilidade, Honorários e Processos/Paralegal em uma plataforma para escritórios de contabilidade.

**Status: arquitetura e fundação técnica.** Existe um esqueleto executável mínimo (Django com endpoint de verificação de saúde), sem nenhum módulo de negócio, motor de cálculo, servidor MCP ou integração oficial implementados ainda. As capacidades abaixo representam o escopo de desenvolvimento.

## Visão do produto

Centralizar as rotinas do escritório, compartilhar cadastros entre departamentos e preservar a origem de cada documento, cálculo e lançamento. A plataforma deverá atender vários escritórios e empresas, com permissões específicas e isolamento de dados.

A abrangência funcional das [Soluções Domínio](https://www.dominiosistemas.com.br/solucoes/dominio-pro/) é uma referência para o produto. O DataLedger terá identidade e implementação próprias, sem vínculo declarado com a Thomson Reuters e sem pressupor acesso a APIs da Domínio.

## Módulos planejados

| Módulo | Objetivo e capacidades previstas |
| --- | --- |
| Fiscal | Importação de documentos, escrituração, apurações versionadas, memória de cálculo, obrigações e integração contábil. |
| Folha de Pagamento | Empregados, vínculos, eventos, folha, férias, 13º, rescisões, encargos e evolução para obrigações oficiais. |
| Contabilidade | Plano de contas, partidas dobradas, conciliação, Diário, Razão, balancete, balanço, DRE e fechamento. |
| Honorários | Contratos, cobranças recorrentes, serviços avulsos, contas a receber, inadimplência e rentabilidade do escritório. |
| Processos/Paralegal | Abertura, alteração e baixa de empresas, licenças, certidões, protocolos, documentos, prazos e responsáveis. |

Os módulos compartilharão cadastros de empresas, estabelecimentos, usuários, documentos, tarefas e competências. Um portal do cliente permitirá acompanhar solicitações e receber documentos autorizados.

## Inteligência artificial e MCP

O projeto prevê duas capacidades distintas:

1. **Assistente interno:** conversa em português para consultar informações, explicar variações e preparar sugestões dentro do sistema.
2. **Servidor MCP:** disponibiliza ferramentas e recursos para aplicativos de IA autorizados, respeitando as mesmas permissões da aplicação.

Exemplos de solicitações previstas:

- “Quais empresas têm documentos pendentes nesta competência?”
- “Explique a variação da folha em relação ao mês anterior.”
- “Liste os honorários vencidos e os processos com prazo nesta semana.”
- “Prepare uma proposta de lançamento para revisão.”

Os cálculos serão realizados por regras determinísticas, versionadas e testadas. A IA deverá indicar as fontes dos dados, distinguir sugestões de resultados efetivados e depender de aprovação para operações críticas. Ela não terá acesso irrestrito ao banco de dados.

## Princípios de construção

- Isolamento entre escritórios e controle de acesso por empresa e operação.
- Valores monetários com precisão decimal e arredondamento explícito.
- Rastreabilidade, memória de cálculo e histórico de alterações.
- Regras legais com fonte, vigência e casos de referência validados.
- Operações repetíveis sem duplicação indevida de documentos ou cobranças.
- Distinção visível entre simulação, homologação e produção.
- Testes e revisão em todas as etapas de desenvolvimento.

## Documentação e contribuição

**Antes de alterar qualquer arquivo, leia integralmente o [AGENTS.md](AGENTS.md).**

- [Escopo funcional e orientação de implementação](docs/escopo.md).
- [Plano da primeira entrega](docs/planos/DL-001-documentacao-inicial.md).
- [Plano de arquitetura e fundação técnica](docs/planos/DL-002-arquitetura-fundacao.md).
- [Plano de fundação: autenticação e multiempresa](docs/planos/DL-003-fundacao-multiempresa.md).
- [Plano de cadastro central de empresas](docs/planos/DL-004-cadastro-empresas.md).
- [Plano de permissões por papel e auditoria](docs/planos/DL-005-permissoes-auditoria.md).
- [Plano de contabilidade básica](docs/planos/DL-006-contabilidade-basica.md).
- [Modelo de pull request](.github/pull_request_template.md).
- [Verificação da documentação](scripts/validate-docs.ps1).

Cada etapa deve ter critérios de aceite e evidências de teste. O fluxo obrigatório é: validar, revisar o diff, commitar, fazer push, abrir ou atualizar o PR e conferir as verificações automáticas. O merge depende de revisão autorizada.

## Estado atual e continuidade (leia antes de continuar o desenvolvimento)

Esta seção existe para que quem retomar o projeto depois não precise
reconstruir o contexto do zero. Atualize-a a cada etapa integrada.

**Onde paramos (11/09/2026):** a `main` contém tudo de DL-001 a DL-006 —
documentação inicial, arquitetura/fundação técnica (Django + DRF +
PostgreSQL), autenticação e isolamento entre escritórios, cadastro central
de empresas/estabelecimentos, permissões básicas por papel, auditoria, e o
primeiro módulo de negócio (Contabilidade básica: plano de contas,
lançamentos por partidas dobradas, Diário, Razão, Balancete). Todas as
migrações aplicam em banco vazio, os 55 testes automatizados passam e o
lint/formatação (`ruff`) e a validação de documentação estão limpos —
conferido rodando a suíte completa sobre a `main` consolidada nesta data.

A etapa 3 (Fundação) está encerrada. Da etapa 4 ("Primeiros fluxos"), só a
Contabilidade básica foi entregue; Paralegal, Honorários, Fiscal (XML de
NF-e) e cadastros de folha continuam planejados, cada um em PR próprio.

### Incidente resolvido: PRs encadeados mesclados na branch errada

Durante a integração das etapas DL-003 a DL-006, os PRs correspondentes
(#3 a #6) foram mesclados **para dentro da branch de origem encadeada de
cada um** (prática prevista no AGENTS.md, seção 6, para PRs dependentes)
em vez de terem a `base` reapontada para `main` antes do merge. O conteúdo
de cada etapa ficou "preso" uma branch antes do destino final, mesmo
aparecendo como "Merged" no GitHub — nenhum trabalho foi perdido, mas a
`main` ficou temporariamente atrasada em relação ao que já estava pronto.

Corrigido pelos PRs #7, #8 e #9 (mesmo conteúdo dos PRs #3 a #6, só com a
`base` correta), mesclados nessa ordem diretamente em `main`. Já
integrados; nenhuma ação pendente relacionada a isso.

**Lição registrada no AGENTS.md (seção 6):** ao mesclar um PR cuja `base`
não é `main` (um PR encadeado), reapontar a `base` para `main` **antes**
de mesclar, assim que o PR do qual ele depende já estiver integrado.

### Pull requests — histórico

Todos os PRs abaixo estão mesclados; a tabela fica para referência de
como cada etapa chegou à `main`.

| PR | Etapa | Situação |
| --- | --- | --- |
| [#1](https://github.com/fredabsd-svg/DataLedger/pull/1) | DL-001 — Documentação inicial | Integrado em `main`. |
| [#2](https://github.com/fredabsd-svg/DataLedger/pull/2) | DL-002 — Arquitetura e fundação técnica | Integrado em `main`. |
| [#3](https://github.com/fredabsd-svg/DataLedger/pull/3) a [#6](https://github.com/fredabsd-svg/DataLedger/pull/6) | DL-003 a DL-006 | Mesclados na branch encadeada errada (ver incidente acima); conteúdo trazido à `main` pelos PRs #7 a #9. |
| [#7](https://github.com/fredabsd-svg/DataLedger/pull/7) | Correção DL-003 (+DL-004) → `main` | Integrado em `main`. |
| [#8](https://github.com/fredabsd-svg/DataLedger/pull/8) | Correção DL-005 → `main` | Integrado em `main`. |
| [#9](https://github.com/fredabsd-svg/DataLedger/pull/9) | Correção DL-006 → `main` | Integrado em `main`. |

### Próximos passos, em ordem

1. Apagar as branches remotas já mescladas e sem PR aberto:
   `feat/dl-002-arquitetura-fundacao`, `feat/dl-003-fundacao-multiempresa`,
   `feat/dl-004-cadastro-empresas`, `feat/dl-005-permissoes-auditoria` e
   `feat/dl-006-contabilidade-basica`. Puramente organizacional — todo o
   conteúdo já está em `main`.
2. Configurar a proteção da branch `main` (etapa 2 do roadmap, ainda
   pendente): exigir PR, revisão e verificações obrigatórias aprovadas
   antes do merge. Isso bloquearia estruturalmente o tipo de merge indevido
   do incidente acima, em vez de depender só de atenção humana.
3. Escolher e planejar o próximo fluxo da etapa 4 (Honorários,
   Processos/Paralegal ou Fiscal/XML de NF-e — decisão de produto, não
   técnica) e abrir sua branch **a partir da `main` já atualizada**.

## Como começar

A stack técnica foi definida na etapa de arquitetura: Python com Django e
Django REST Framework, PostgreSQL e templates renderizados no servidor
(HTMX/Alpine.js). Ainda não há módulo de negócio implementado; o que existe
é o esqueleto do projeto e um endpoint de verificação de saúde. Detalhes e
motivação em [docs/planos/DL-002-arquitetura-fundacao.md](docs/planos/DL-002-arquitetura-fundacao.md).

Para obter o repositório, use Git com suporte a HTTPS:

```sh
git clone https://github.com/fredabsd-svg/DataLedger.git
cd DataLedger
```

Para rodar a aplicação localmente sem Docker (requer Python 3.12 ou
superior):

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux/macOS: source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Para rodar com Docker Compose (aplicação e PostgreSQL):

```sh
cp .env.example .env
docker compose up --build
```

Em ambos os casos, `GET /api/health/` deve responder `{"status": "ok"}`. Para
autenticar, crie um usuário com `python manage.py createsuperuser` e acesse
`/login/`; o painel em `/` mostra o escritório ativo do usuário, conforme
descrito em [docs/planos/DL-003-fundacao-multiempresa.md](docs/planos/DL-003-fundacao-multiempresa.md).

Para rodar o lint, a formatação e os testes do backend:

```sh
ruff check .
ruff format --check .
pytest
```

Para validar a documentação a partir da raiz, use PowerShell 7 ou superior:

```sh
pwsh -NoProfile -File scripts/validate-docs.ps1
```

A verificação confere arquivos obrigatórios, UTF-8, títulos, espaços ao final das linhas e existência dos destinos de links relativos. Não valida conteúdo jurídico, URLs externas ou âncoras. Os workflows de documentação e de backend executam essas verificações em pushes e pull requests.

## Etapas de evolução

| Etapa | Entrega esperada | Situação |
| --- | --- | --- |
| 1. Documentação inicial | README, regras, escopo, plano, modelo de PR e verificação documental. | Proposta nesta entrega. |
| 2. Arquitetura e controles | Stack, modelo de dados, contratos, estratégia de testes e proteção da branch principal. | Stack definida e esqueleto do projeto entregue; proteção da branch principal ainda pendente. |
| 3. Fundação | Autenticação, escritórios, empresas, permissões, auditoria e persistência. | Entregue: autenticação, isolamento entre escritórios, cadastro de empresas/estabelecimentos, permissões básicas por papel e auditoria. Matriz fina de permissões por operação fica para quando os módulos de negócio existirem. |
| 4. Primeiros fluxos | Paralegal, honorários, contabilidade básica, XML de NF-e e cadastros de folha, em PRs independentes. | Contabilidade básica (plano de contas, lançamentos por partidas dobradas, Diário, Razão, Balancete) entregue. Demais fluxos planejados. |
| 5. IA e MCP | Consultas autorizadas, recursos e preparação controlada de operações. | Planejada. |
| 6. Cálculos e integrações | Motores validados, fechamentos, obrigações e conectores homologados. | Planejada. |

Cada etapa ampla será desdobrada em incrementos revisáveis. A presença do AGENTS.md não ativa proteções de branch; essa configuração precisa ser feita e verificada separadamente. Os testes da aplicação serão adicionados junto aos respectivos componentes.

## Referências

- [Visão funcional das Soluções Domínio](https://www.dominiosistemas.com.br/solucoes/dominio-pro/).
- [Documentação oficial do Model Context Protocol](https://modelcontextprotocol.io/).

Integrações e regras legais deverão ser verificadas nas fontes oficiais durante sua implementação, considerando vigência, credenciamento e disponibilidade técnica.
