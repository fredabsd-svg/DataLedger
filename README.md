<p align="center">
  <img src="docs/assets/logo-dataledger.svg" alt="Logo do DataLedger: livro-razão com símbolo de código" width="128" />
</p>

# 📊 DataLedger

<p align="center">
  <strong>Sistema contábil brasileiro, multiempresa, auditável e preparado para evoluir por módulos.</strong>
</p>

<p align="center">
  <em>Onde devs brasileiros organizam, consultam e versionam dados como código.</em>
</p>

<p align="center">
  <a href="https://github.com/fredabsd-svg/DataLedger/actions/workflows/backend.yml"><img alt="Backend CI" src="https://github.com/fredabsd-svg/DataLedger/actions/workflows/backend.yml/badge.svg" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/actions/workflows/documentation.yml"><img alt="Docs CI" src="https://github.com/fredabsd-svg/DataLedger/actions/workflows/documentation.yml/badge.svg" /></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="Django 6.1.1" src="https://img.shields.io/badge/Django-6.1.1-0C4B33?style=flat-square&logo=django&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-ready-336791?style=flat-square&logo=postgresql&logoColor=white" />
  <a href="https://github.com/fredabsd-svg/DataLedger/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/forks"><img alt="Forks" src="https://img.shields.io/github/forks/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <a href="https://github.com/fredabsd-svg/DataLedger/issues"><img alt="Issues" src="https://img.shields.io/github/issues/fredabsd-svg/DataLedger?style=flat-square&logo=github" /></a>
  <img alt="Feito no Brasil" src="https://img.shields.io/badge/feito%20no-Brasil-009C3B?style=flat-square" />
</p>

<p align="center">
  <img src="docs/assets/hero.svg" alt="Visão visual do DataLedger conectando módulos contábeis a um núcleo auditável" width="100%" />
</p>

> **Estado atual:** a base do produto já inclui autenticação, isolamento entre escritórios, cadastro de empresas e estabelecimentos, permissões, auditoria e contabilidade básica com plano de contas, partidas dobradas, Diário, Razão e Balancete. A DL-011 acrescentou suporte ao CNPJ alfanumérico e elevou a suíte automatizada para 272 testes. Fiscal, Folha, Honorários, Processos/Paralegal, IA e MCP seguem como evolução planejada.

## ✨ O que o DataLedger quer resolver

O DataLedger nasce para reunir as rotinas de um escritório contábil em uma plataforma única, com **dados compartilhados entre módulos**, **rastreabilidade de origem**, **regras versionadas** e **isolamento entre escritórios e empresas**.

| | Capacidade | Situação |
| --- | --- | --- |
| <img src="docs/assets/icons/ledger.svg" alt="" width="28" /> | **Contabilidade** — plano de contas, lançamentos por partidas dobradas, Diário, Razão e Balancete | ✅ Base implementada |
| <img src="docs/assets/icons/building.svg" alt="" width="28" /> | **Multiempresa** — escritórios, empresas, estabelecimentos e isolamento de dados | ✅ Implementado |
| <img src="docs/assets/icons/shield.svg" alt="" width="28" /> | **Permissões e auditoria** — acesso controlado e trilha de alterações | ✅ Fundação implementada |
| <img src="docs/assets/icons/file-code.svg" alt="" width="28" /> | **Fiscal** — recepção de documentos, escrituração, apuração e integração contábil | 🧭 Próximo grande fluxo |
| <img src="docs/assets/icons/users.svg" alt="" width="28" /> | **Folha** — vínculos, eventos, férias, 13º, rescisões e encargos | 🗺️ Planejado |
| <img src="docs/assets/icons/briefcase.svg" alt="" width="28" /> | **Honorários e Paralegal** — contratos, cobranças, processos, prazos e documentos | 🗺️ Planejado |
| <img src="docs/assets/icons/sparkles.svg" alt="" width="28" /> | **IA + MCP** — consulta assistida e operações controladas pelas mesmas permissões do sistema | 🗺️ Planejado |

## 🧭 Arquitetura em uma imagem

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Arquitetura do DataLedger com Django, DRF, PostgreSQL, módulos de negócio, auditoria e interfaces" width="100%" />
</p>

O núcleo atual usa **Python 3.12+, Django 6.1.1, Django REST Framework 3.18.1 e PostgreSQL**, com templates renderizados no servidor e evolução de interface apoiada por HTMX/Alpine.js. A regra central é simples: **cálculo oficial deve ser determinístico, testável e reproduzível; IA consulta, explica e propõe**.

## 🥊 Gauntlet Loop de qualidade

<p align="center">
  <img src="docs/assets/gauntlet-loop.svg" alt="Ciclo de qualidade do DataLedger: planejar, implementar, testar, atacar, corrigir, auditar e integrar" width="100%" />
</p>

A engenharia do DataLedger trata software contábil como software crítico. Uma mudança não termina quando “funciona na máquina”: ela passa por planejamento, testes, revisão do diff, auditoria, CI e registro das decisões. Na DL-011, por exemplo, sucessivas rodadas de auditoria encontraram falhas que rodadas anteriores não haviam visto — e os testes cresceram junto com as correções.

## 🧱 Princípios que não negociamos

- **Isolamento por escritório e empresa** aplicado no backend, não apenas escondido na interface.
- **Partidas dobradas** e invariantes contábeis protegidos por regra e teste.
- **Valores monetários com precisão decimal**, escala e arredondamento explícitos.
- **Rastreabilidade** de documentos, lançamentos, cálculos, atores e alterações.
- **Regras legais versionadas por vigência**, com fonte e casos de referência.
- **Idempotência** para importações, cobranças e operações sujeitas a repetição.
- **Falha visível**: erro nunca deve virar sucesso aparente.
- **IA sem acesso irrestrito ao banco** e sem substituir o motor determinístico.

## 🚀 Como rodar localmente

### 1. Clone o repositório

```bash
git clone https://github.com/fredabsd-svg/DataLedger.git
cd DataLedger
```

### 2. Crie o ambiente e instale as dependências

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

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

## 🧪 Verificações de desenvolvimento

```bash
ruff check .
ruff format --check .
pytest
python manage.py check
python manage.py makemigrations --check
```

Documentação:

```powershell
pwsh -NoProfile -File scripts/validate-docs.ps1
```

## 🛠️ Tech stack

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Django-6.1.1-0C4B33?style=for-the-badge&logo=django&logoColor=white" alt="Django" />
  <img src="https://img.shields.io/badge/DRF-3.18.1-A30000?style=for-the-badge" alt="Django REST Framework" />
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/HTMX-3366CC?style=for-the-badge&logo=htmx&logoColor=white" alt="HTMX" />
  <img src="https://img.shields.io/badge/Alpine.js-8BC0D0?style=for-the-badge&logo=alpinedotjs&logoColor=111827" alt="Alpine.js" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

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
- [x] **DL-011** — CNPJ alfanumérico
- [ ] **DL-010** — recepção de documentos fiscais / evolução do fluxo Fiscal
- [ ] **Fiscal completo** — escrituração, apuração, obrigações e integração contábil
- [ ] **Folha de Pagamento**
- [ ] **Honorários**
- [ ] **Processos/Paralegal**
- [ ] **IA e servidor MCP**

> A ordem dos números DL reflete dependências e decisões de implementação; uma etapa posterior pode ser concluída antes de outra quando ela remove um bloqueio técnico.

## 🤝 Contribuindo

<p align="center">
  <img src="docs/assets/contributing.svg" alt="Ilustração de contribuição no DataLedger com branch, revisão, testes e pull request" width="760" />
</p>

Contribuições técnicas são bem-vindas, mas o projeto possui regras rígidas porque lida com domínio contábil e isolamento de dados. **Antes de alterar qualquer arquivo, leia integralmente [`AGENTS.md`](AGENTS.md).**

Comece por estes documentos:

- [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) — requisitos confirmados e pendências.
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
| [`CLAUDE.md`](CLAUDE.md) | Contexto operacional para agentes e retomada do trabalho |
| [`docs/escopo.md`](docs/escopo.md) | Escopo funcional do sistema |
| [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) | Requisitos e hipóteses |
| [`docs/projeto/backlog.md`](docs/projeto/backlog.md) | Backlog priorizado |
| [`docs/projeto/decisoes.md`](docs/projeto/decisoes.md) | Registro de decisões |
| [`docs/planos/`](docs/planos/) | Histórico das etapas DL |
| [`docs/auditorias/`](docs/auditorias/) | Relatórios de auditoria |

## 🇧🇷 Construído para a realidade contábil brasileira

O DataLedger é desenvolvido com foco em rastreabilidade, isolamento, auditabilidade e evolução segura de regras. Integrações oficiais e regras legais só devem ser tratadas como implementadas depois de validação nas fontes oficiais e evidência técnica correspondente.

<p align="center">
  <strong>Feito com engenharia, café e responsabilidade por <a href="https://github.com/fredabsd-svg">fredabsd-svg</a>.</strong>
</p>

<p align="center">
  ⭐ Se o projeto fizer sentido para você, acompanhe a evolução e deixe uma estrela.
</p>
