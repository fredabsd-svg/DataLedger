<p align="center">
  <img src="docs/assets/logo-dataledger.svg" alt="Símbolo do DataLedger: um razonete — a conta T da contabilidade — com lançamentos equilibrados e a linha verde de fechamento" width="128" />
</p>

# 📊 DataLedger

<p align="center">
  <strong>Sistema contábil brasileiro, multiempresa, auditável e preparado para evoluir por módulos.</strong>
</p>

<p align="center">
  <em>Feito para escritórios de contabilidade: cada número com origem, cada regra com vigência, cada alteração com autor.</em>
</p>

<p align="center">
  <a href="https://github.com/fredabsd-svg/DataLedger/actions/workflows/backend.yml"><img alt="Backend CI" src="https://github.com/fredabsd-svg/DataLedger/actions/workflows/backend.yml/badge.svg" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/actions/workflows/documentation.yml"><img alt="Docs CI" src="https://github.com/fredabsd-svg/DataLedger/actions/workflows/documentation.yml/badge.svg" /></a>
  <img alt="Python 3.12+ (CI em 3.14)" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="Django 6.1.1" src="https://img.shields.io/badge/Django-6.1.1-0C4B33?style=flat-square&logo=django&logoColor=white" />
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" />
  <a href="https://github.com/fredabsd-svg/DataLedger/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/forks"><img alt="Forks" src="https://img.shields.io/github/forks/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/issues"><img alt="Issues" src="https://img.shields.io/github/issues/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <img alt="Feito no Brasil" src="https://img.shields.io/badge/feito%20no-Brasil-009C3B?style=flat-square" />
</p>

<p align="center">
  <img src="docs/assets/hero.svg" alt="Visão do DataLedger: núcleo contábil, módulos, lançamento de exemplo e trilha de auditoria" width="100%" />
</p>

> **Onde o projeto está agora:** a fonte única do estado é [`docs/agents/estado.md`](docs/agents/estado.md) — revisão atual, etapas concluídas, próximo passo e pendências. Este README descreve o **produto e o processo**, que mudam pouco; o estado, que muda a cada etapa, mora num lugar só, de propósito. Em uma frase: a fundação (multiempresa, permissões, auditoria, contabilidade básica, política monetária, CNPJ alfanumérico) está entregue e auditada; **Fiscal, Folha, Honorários, Processos/Paralegal, IA e MCP ainda não existem**.

## ✨ O que o DataLedger quer resolver

O DataLedger nasce para reunir as rotinas de um escritório contábil em uma plataforma única, com **dados compartilhados entre módulos**, **rastreabilidade de origem**, **regras versionadas** e **isolamento entre escritórios e empresas**.

| | Capacidade | Situação |
| --- | --- | --- |
| <img src="docs/assets/icons/ledger.svg" alt="" width="28" /> | **Contabilidade** — plano de contas, lançamentos por partidas dobradas, Diário, Razão e Balancete | ✅ Base implementada e auditada |
| <img src="docs/assets/icons/building.svg" alt="" width="28" /> | **Multiempresa** — escritórios, empresas, estabelecimentos e isolamento de dados | ✅ Implementado e auditado |
| <img src="docs/assets/icons/shield.svg" alt="" width="28" /> | **Permissões e auditoria** — acesso controlado no servidor e trilha de alterações | ✅ Fundação implementada |
| <img src="docs/assets/icons/file-code.svg" alt="" width="28" /> | **Fiscal** — recepção de XML, ZIP e SPED; depois escrituração, apuração e integração contábil | 🧭 Próximo fluxo — [DL-010](docs/planos/DL-010-recepcao-de-documentos-fiscais.md) |
| <img src="docs/assets/icons/users.svg" alt="" width="28" /> | **Folha** — vínculos, eventos, férias, 13º, rescisões e encargos | 🗺️ Planejado |
| <img src="docs/assets/icons/briefcase.svg" alt="" width="28" /> | **Honorários e Paralegal** — contratos, cobranças, processos, prazos e documentos | 🗺️ Planejado |
| <img src="docs/assets/icons/sparkles.svg" alt="" width="28" /> | **IA + MCP** — consulta assistida e operações controladas pelas mesmas permissões do sistema | 🗺️ Planejado |

## 🧭 Arquitetura em uma imagem

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Arquitetura do DataLedger com Django, DRF, PostgreSQL, módulos de negócio, auditoria e interfaces" width="100%" />
</p>

O núcleo usa **Python 3.12+ (a integração contínua roda em 3.14), Django 6.1.1, Django REST Framework 3.18.1 e PostgreSQL 16**, com templates renderizados no servidor e **CSS próprio, sem biblioteca visual externa** ([DE-011](docs/projeto/decisoes.md)). A regra central é simples: **cálculo oficial deve ser determinístico, testável e reproduzível; IA consulta, explica e propõe**.

## 🔁 Ciclo de qualidade

<p align="center">
  <img src="docs/assets/ciclo-de-qualidade.svg" alt="Ciclo de qualidade do DataLedger: planejar, implementar, testar, atacar, corrigir, auditar e integrar" width="100%" />
</p>

A engenharia do DataLedger trata software contábil como software crítico. Uma mudança não termina quando "funciona na máquina": ela passa por planejamento, testes, revisão do diff, **auditoria independente com teste de mutação**, integração contínua e registro das decisões. Na DL-011, por exemplo, foram **cinco rodadas de auditoria** — a primeira reprovou, e cada rodada seguinte encontrou algo que a anterior não tinha visto. Os relatórios estão em [`docs/auditorias/`](docs/auditorias/), preservados integralmente.

## 🧱 Princípios que não negociamos

- **Isolamento por escritório e empresa** aplicado no servidor, não apenas escondido na interface.
- **Partidas dobradas** e invariantes contábeis protegidos por regra, por restrição de banco e por teste.
- **Valores monetários com precisão decimal**, escala e arredondamento explícitos — nunca ponto flutuante.
- **Rastreabilidade** de documentos, lançamentos, cálculos, atores e alterações.
- **Regras legais versionadas por vigência**, com fonte oficial e casos de referência.
- **Idempotência** para importações, cobranças e operações sujeitas a repetição.
- **Falha visível**: erro nunca vira sucesso aparente.
- **IA sem acesso irrestrito ao banco** e sem substituir o motor determinístico.

## 🚀 Como rodar localmente

### 1. Clone o repositório

```bash
git clone https://github.com/fredabsd-svg/DataLedger.git
cd DataLedger
```

### 2. Crie o ambiente e instale as dependências

Requer Python 3.12 ou superior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements/dev.txt
```

### 3. Configure, migre e execute

```bash
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

A verificação de saúde fica em `GET /api/health/`. Para entrar na aplicação, crie um usuário administrativo com `python manage.py createsuperuser` e acesse `/login/`.

Sem `DATABASE_URL` configurada e com `DEBUG=True`, o sistema usa SQLite local e avisa isso ao subir. **Com `DEBUG=False` ele exige PostgreSQL e recusa subir sem ele** — é proteção, não limitação.

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

## 🧪 Verificações de desenvolvimento

```bash
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

Documentação (PowerShell 7 ou superior):

```powershell
pwsh -NoProfile -File scripts/validate-docs.ps1
```

## 🛠️ Tecnologias em uso

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Django-6.1.1-0C4B33?style=for-the-badge&logo=django&logoColor=white" alt="Django" />
  <img src="https://img.shields.io/badge/DRF-3.18.1-A30000?style=for-the-badge" alt="Django REST Framework" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

Só aparece aqui o que está em `requirements/` ou no repositório. Biblioteca que ainda não entrou não é anunciada.

## 🗺️ Roadmap real do repositório

- [x] **DL-001** — documentação inicial e regras de contribuição
- [x] **DL-002** — arquitetura e fundação técnica
- [x] **DL-003** — autenticação e isolamento multiempresa
- [x] **DL-004** — cadastro central de empresas e estabelecimentos
- [x] **DL-005** — permissões e auditoria
- [x] **DL-006** — contabilidade básica
- [x] **DL-007** — correções de bloqueadores da contabilidade
- [x] **DL-008** — política monetária e validação de escala
- [x] **DL-009** — fundação de interface
- [x] **DL-011** — CNPJ alfanumérico (NT 2025.001 / IN RFB 2.229)
- [x] **DL-012** — redesenho do README e identidade visual
- [x] **DL-013** — logo oficial
- [x] **DL-014** — guardas de processo: regras impostas por gancho, workflow e proteção da `main`
- [ ] **DL-010** — recepção de documentos fiscais: XML, ZIP e SPED, em segundo plano
- [ ] **Fiscal completo** — escrituração, apuração, obrigações e integração contábil
- [ ] **Folha de Pagamento**
- [ ] **Honorários**
- [ ] **Processos/Paralegal**
- [ ] **IA e servidor MCP**

> A numeração DL reflete a ordem em que as demandas foram abertas, não a de conclusão: a DL-011 fechou antes da DL-010 porque removia um bloqueio dela (o CNPJ alfanumérico está em vigor desde 31/07/2026 e o sistema o recusava).

## 🤝 Contribuindo

<p align="center">
  <img src="docs/assets/contributing.svg" alt="Ilustração de contribuição no DataLedger com branch, revisão, testes e pull request" width="760" />
</p>

Contribuições técnicas são bem-vindas, mas o projeto possui regras rígidas porque lida com domínio contábil e isolamento de dados. **Antes de alterar qualquer arquivo, leia integralmente [`AGENTS.md`](AGENTS.md).**

Comece por estes documentos:

- [`docs/agents/estado.md`](docs/agents/estado.md) — **onde o projeto está** e qual é o próximo passo.
- [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) — requisitos confirmados, hipóteses e pendências.
- [`docs/projeto/backlog.md`](docs/projeto/backlog.md) — prioridades, dependências e critérios de aceite.
- [`docs/projeto/decisoes.md`](docs/projeto/decisoes.md) — decisões arquiteturais e justificativas.
- [`docs/projeto/mapa-funcional-fiscal.md`](docs/projeto/mapa-funcional-fiscal.md) — visão funcional do domínio Fiscal.
- [`docs/planos/`](docs/planos/) — planos versionados das demandas DL.
- [`docs/auditorias/`](docs/auditorias/) — auditorias preservadas das etapas realizadas.

Fluxo esperado: **branch própria → implementação pequena → testes → revisão do diff → push → pull request → CI → revisão autorizada**.

## 📚 Navegação rápida

| Documento | Para que serve |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Regras obrigatórias de desenvolvimento |
| [`CLAUDE.md`](CLAUDE.md) | Resumo operacional para agentes de IA |
| [`docs/agents/estado.md`](docs/agents/estado.md) | Estado atual e retomada do trabalho — fonte única |
| [`docs/escopo.md`](docs/escopo.md) | Escopo funcional do sistema |
| [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) | Requisitos e hipóteses |
| [`docs/projeto/backlog.md`](docs/projeto/backlog.md) | Backlog priorizado |
| [`docs/projeto/decisoes.md`](docs/projeto/decisoes.md) | Registro de decisões |
| [`docs/planos/`](docs/planos/) | Histórico das etapas DL |
| [`docs/auditorias/`](docs/auditorias/) | Relatórios de auditoria |

## 🇧🇷 Construído para a realidade contábil brasileira

O DataLedger é desenvolvido com foco em rastreabilidade, isolamento, auditabilidade e evolução segura de regras. Integrações oficiais e regras legais só são tratadas como implementadas depois de validação nas fontes oficiais, evidência técnica correspondente e **validação profissional do responsável técnico** — auditoria de software não substitui a do contador.

<p align="center">
  <strong>Feito com engenharia, café e responsabilidade por <a href="https://github.com/fredabsd-svg">fredabsd-svg</a>.</strong>
</p>

<p align="center">
  ⭐ Se o projeto fizer sentido para você, acompanhe a evolução e deixe uma estrela.
</p>
