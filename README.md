<p align="center">
  <img src="docs/assets/logo-dataledger.svg" alt="Símbolo do DataLedger: laço duplo azul entrelaçado por uma fita verde, com um conjunto de cubos de dados no laço direito" width="128" />
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
| <img src="docs/assets/icons/ledger.svg" alt="" width="28" /> | **Contabilidade** — plano de contas, lançamentos por partidas dobradas, Diário, Razão e Balancete por período | ✅ Implementada. Interface no navegador: [DL-017](docs/planos/DL-017-interface-da-contabilidade.md); identidade visual e direção de arte: [DL-026](docs/planos/DL-026-identidade-visual-e-interface.md) |
| <img src="docs/assets/icons/building.svg" alt="" width="28" /> | **Multiempresa** — escritórios, empresas, estabelecimentos e isolamento de dados | ✅ Implementado e auditado |
| <img src="docs/assets/icons/shield.svg" alt="" width="28" /> | **Permissões e auditoria** — acesso controlado no servidor e trilha de alterações | ✅ Fundação implementada |
| <img src="docs/assets/icons/file-code.svg" alt="" width="28" /> | **Fiscal** — recepção de XML, ZIP e SPED; depois escrituração, apuração e integração contábil | 🗺️ Planejado — [DL-010](docs/planos/DL-010-recepcao-de-documentos-fiscais.md) |
| <img src="docs/assets/icons/users.svg" alt="" width="28" /> | **Folha** — vínculos, eventos, férias, 13º, rescisões e encargos | 🗺️ Planejado |
| <img src="docs/assets/icons/briefcase.svg" alt="" width="28" /> | **Honorários e Paralegal** — contratos, cobranças, processos, prazos e documentos | 🗺️ Planejado |
| <img src="docs/assets/icons/sparkles.svg" alt="" width="28" /> | **IA + MCP** — consulta assistida e operações controladas pelas mesmas permissões do sistema | 🗺️ Planejado |

A coluna acima diz se a **capacidade** existe no repositório, em traço grosso. Em que pé está cada etapa — em execução, em auditoria, reprovada, integrada — fica em [`docs/agents/estado.md`](docs/agents/estado.md), e **só lá**. Este arquivo já afirmou duas vezes coisa que o repositório desmentia; as duas por descrever estado em segundo lugar.

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

O que a experiência ensinou é que **regra sem mecanismo é só pedido**. Por isso parte das regras deixou de depender de alguém lembrar: gancho que injeta as regras no início de cada sessão, verificação que reprova pull request sem atestado de leitura, teste que reprova quando o estado documentado diverge do repositório, e **varredura de interface** que reprova tela fora do contrato visual — cor, medida, tabulação de algarismos, legenda de tabela, moldura comum e o "momento da verdade" de cada módulo. O que é imposto por máquina e o que é só instrução está declarado no fim do [`AGENTS.md`](AGENTS.md).

Essas guardas também são atacadas de propósito. Na [DL-026](docs/planos/DL-026-identidade-visual-e-interface.md), a auditoria sabotou a varredura de seis maneiras e passou nas seis; as seis viraram detector com prova de que reprovam. Guarda que nunca falhou em teste não é guarda confiável — é guarda que ainda não foi testada.

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

Abra `http://localhost:8000/` e escolha **Cadastrar minha empresa**. Informe os
dados do responsável e do escritório para criar sua conta e seu espaço de trabalho.
Você entra como administrador do seu próprio escritório; depois, cadastre as
empresas clientes no painel. Para contas existentes, use **Entrar** (usuário antigo
ou e-mail usado no novo cadastro). Não é necessário criar superusuário nem abrir
o admin para começar. Fluxo e critérios: [DL-036](docs/planos/DL-036-entrada-e-cadastro.md).

A verificação de saúde fica em `GET /api/health/`. O comando
`python manage.py createsuperuser` continua disponível para administração técnica,
mas não faz parte do cadastro normal.

Sem `DATABASE_URL` configurada e com `DEBUG=True`, o sistema usa SQLite local e avisa isso ao subir. **Com `DEBUG=False` ele exige PostgreSQL e recusa subir sem ele** — é proteção, não limitação.

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

O `web` aplica as migrações e sobe o gunicorn em `http://localhost:8000`. Na primeira vez o PostgreSQL cria o volume do zero, e isso pode levar mais de um minuto antes de o `web` começar — é esperado.

Depois que subir, abra `http://localhost:8000/`: **Cadastrar minha empresa** cria
conta e escritório pelo navegador; **Entrar** acessa uma conta já existente.
Para atualizar uma instalação existente após integrar a alteração, execute
`git pull` e `docker compose up --build -d`. Preserve o volume do banco de dados.

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

A lista abaixo diz **o que existe**, nunca em que pé está. O estado de cada etapa — em execução, auditada, reprovada, integrada — vive num lugar só, [`docs/agents/estado.md`](docs/agents/estado.md). Descrever estado aqui já divergiu duas vezes; a causa é duplicação, não distração. A **sequência do que vem depois**, módulo por módulo e com critérios de conclusão, está em [`docs/projeto/plano-mestre.md`](docs/projeto/plano-mestre.md).

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
- [x] **DL-015** — contabilidade utilizável: Diário, Razão e Balancete por período, conciliáveis entre si
- [x] **DL-017** — interface da contabilidade: plano de contas, lançamento, Diário, Razão e Balancete no navegador
- [ ] **DL-016** — competência e fechamento de período, com reabertura autorizada e auditada
- [ ] **DL-010** — recepção de documentos fiscais: XML, ZIP e SPED, em segundo plano
- [x] **DL-018** — primeiro acesso de uma instalação nova: autocadastro assistido do primeiro escritório + primeiro usuário vira ADMINISTRADOR + convite por e-mail para o segundo funcionário (papel ANALISTA). PR #27 em `1b828e7`, 5/5 checks verdes
- [x] **DL-019** — portabilidade entre ferramentas de IA: os papéis da equipe em um formato só, gerados para Claude Code e Codex CLI
- [x] **DL-020** — consolidação pós-auditoria: as ressalvas da rodada 6 e as quatro regras contábeis confirmadas
- [x] **DL-021** — robustez do gerador de papéis em ambiente Windows: gravador não usa mais a camada de texto da plataforma; rede de segurança no repositório para `core.autocrlf`
- [x] **DL-022** — plano mestre de evolução por módulos e reconciliação da documentação divergente
- [x] **DL-023** — integridade administrativa: nenhuma regra de negócio vale só na porta pela qual foi escrita (rodadas 1/3/5/7 do auditor; correções das rodadas 4 e 6 integradas via PR #27; ressalvas contábeis BL-261/262/263 ainda abertas)
- [ ] **DL-024** — trilha íntegra e processo: `registrar()` dentro da mesma transação que grava, `RegistroAuditoria` imutável contra `update()`/`delete()` em massa, PUT/PATCH com diff dos campos alterados, e teste do gate SQLite/PostgreSQL. Plano em [docs/planos/DL-024-trilha-integra-e-processo.md](docs/planos/DL-024-trilha-integra-e-processo.md)
- [ ] **DL-025** — ordens diretas do responsável: uma solicitação de Fred é demanda formal e autoriza a execução do escopo pedido
- [ ] **DL-026** — identidade visual e redesenho da interface, por gauntlet de variantes cegas com juiz mecânico
- [ ] **DL-027** — o documento emitido: identificação obrigatória por **classe de documento** (conferência, demonstração, livro) e personalização do que é legítimo personalizar — logotipo do escritório ou do cliente, marca d'água, e o critério de apuração impresso no próprio papel. Plano em [docs/planos/DL-027-documento-emitido-e-personalizacao.md](docs/planos/DL-027-documento-emitido-e-personalizacao.md)
- [ ] **DL-028** — o juiz aponta para o produto: a pergunta *"o documento que o escritório entrega ao cliente sai identificado?"* passa a ser respondida pelo **navegador**, em job de integração contínua delimitado por caminho, e o motor de cascata simulado é rebaixado de única garantia para primeira linha barata. Plano em [docs/planos/DL-028-o-juiz-aponta-para-o-produto.md](docs/planos/DL-028-o-juiz-aponta-para-o-produto.md)
- [ ] **DL-029** — a frase executável do critério 9: o critério *"o documento sai com a identificação do escritório e sem a marca do fornecedor"* passa a ser escrito **uma vez**, como frase verificável, e o instrumento de medição passa a ser julgado por ela em vez de corrigido achado a achado. Plano em [docs/planos/DL-029-a-frase-executavel-do-criterio-9.md](docs/planos/DL-029-a-frase-executavel-do-criterio-9.md)
- [ ] **DL-030** — a trilha de auditoria passa a cobrir o **admin**: quem alterou, quando, e **com que valor antes e depois**. Nasce de uma medição — a razão social de uma empresa era sobrescrita no lugar, e o valor anterior deixava de existir no sistema. Plano em [docs/planos/DL-030-a-trilha-cobre-o-admin.md](docs/planos/DL-030-a-trilha-cobre-o-admin.md)
- [ ] **DL-031** — a tela do fechamento (fatia 2 da DL-016): hoje a trava de competência encerrada existe no servidor e **não há porta para acioná-la** — o contador não consegue fechar o mês pelo produto. Painel de competências, fechar com a conferência à vista **antes** do botão, reabrir com motivo registrado, e marcar como entregue com o aviso de que não tem volta. Plano em [docs/planos/DL-031-fatia-2-a-tela-do-fechamento.md](docs/planos/DL-031-fatia-2-a-tela-do-fechamento.md)
- [x] **DL-032** — a **camada de saldos**: o elo de que Balanço, DRE, DMPL e os indicadores vão derivar. Nasce do cruzamento do catálogo de 120 relatórios, que mostrou que todo relatório contábil sai de UMA cadeia e que o produto tem os três primeiros elos e não tem o quarto. **Contrato de derivação, não tabela** — saldo gravado que diverge dos lançamentos é o defeito mais caro de um sistema contábil. Plano em [docs/planos/DL-032-a-camada-de-saldos.md](docs/planos/DL-032-a-camada-de-saldos.md)
- [x] **DL-033** — **circulante e não circulante**: o único dado que falta para o Balanço Patrimonial existir. A norma foi levantada em fonte oficial antes do desenho (Lei 6.404/76 arts. 178-180 e NBC TG 26 (R5) itens 60-76, RC-106), e ela impôs três consequências que não se adivinham — entre elas que o ativo não circulante tem **quatro** subgrupos nomeados por lei. ⚠️ **A etapa NÃO adivinha a classificação das contas existentes**: conta existente nasce sem classificação e a camada declara quais faltam — inferir grupo pela posição na árvore foi o achado que reprovou a DL-032. Plano em [docs/planos/DL-033-circulante-e-nao-circulante.md](docs/planos/DL-033-circulante-e-nao-circulante.md)
- [x] **DL-034** — a **tela do Balanço Patrimonial**: a primeira **demonstração contábil** que o produto emite, e por isso a primeira sujeita ao bloco de identificação prescrito pela NBC TG 26 (R5) item 51, **em cada página** (RC-95). ⚠️ **Três dos cinco itens desse bloco NÃO existiam** — entidade individual ou de grupo, moeda de apresentação e nível de arredondamento. A etapa também venceu três dívidas declaradas: autorização no servidor (que nunca teve superfície onde ser medida), leitura sob snapshot (DE-067) e recusa de emissão com declaração pendente (BL-488). Plano em [docs/planos/DL-034-a-tela-do-balanco.md](docs/planos/DL-034-a-tela-do-balanco.md)
- [x] **DL-035** — as **guardas da demonstração**: as cinco ressalvas da reconferência da DL-034, numa etapa própria em vez de uma terceira volta (a §3.1 proíbe a terceira). ⚠️ **Nenhum item é defeito no que o produto entrega hoje** — todos são buracos na **guarda**, o que passaria numa mudança futura: o bloco normativo sai **invisível do papel** por uma declaração de cor com o job verde (BL-514), e mover 5 das 6 travas de emissão para a tupla de aviso **não reprova nada** (BL-515). Plano em [docs/planos/DL-035-as-guardas-da-demonstracao.md](docs/planos/DL-035-as-guardas-da-demonstracao.md) — integrada pelo PR #43 (`898b334`); auditoria aprovada e BL-514–519 encerradas.
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
- [`docs/projeto/plano-mestre.md`](docs/projeto/plano-mestre.md) — **para onde o projeto vai**: sequência de entregas por módulo, com os critérios de conclusão. É mapa de decomposição, não fonte de estado.
- [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) — requisitos confirmados, hipóteses e pendências.
- [`docs/projeto/backlog.md`](docs/projeto/backlog.md) — prioridades, dependências e critérios de aceite.
- [`docs/projeto/decisoes.md`](docs/projeto/decisoes.md) — decisões arquiteturais e justificativas.
- [`docs/projeto/direcao-de-arte.md`](docs/projeto/direcao-de-arte.md) — **o contrato visual**: os cinco arquétipos de tela, as regras que não se negociam e o checklist para módulo novo.
- [`docs/projeto/mapa-funcional-fiscal.md`](docs/projeto/mapa-funcional-fiscal.md) — visão funcional do domínio Fiscal.
- [`docs/planos/`](docs/planos/) — planos versionados das demandas DL.
- [`docs/auditorias/`](docs/auditorias/) — auditorias preservadas das etapas realizadas.

Fluxo esperado: **branch própria → implementação pequena → testes → revisão do diff → push → pull request → CI → revisão autorizada**.

## 📚 Navegação rápida

| Documento | Para que serve |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Regras obrigatórias de desenvolvimento |
| [`CLAUDE.md`](CLAUDE.md) | Resumo operacional para agentes de IA |
| [`docs/agents/equipe.md`](docs/agents/equipe.md) | Papéis da equipe de agentes, em todas as ferramentas suportadas |
| [`docs/agents/estado.md`](docs/agents/estado.md) | Estado atual e retomada do trabalho — fonte única |
| [`docs/escopo.md`](docs/escopo.md) | Escopo funcional do sistema |
| [`docs/projeto/plano-mestre.md`](docs/projeto/plano-mestre.md) | Sequência de evolução por módulo e critérios de conclusão |
| [`docs/projeto/requisitos.md`](docs/projeto/requisitos.md) | Requisitos e hipóteses |
| [`docs/projeto/backlog.md`](docs/projeto/backlog.md) | Backlog priorizado |
| [`docs/projeto/decisoes.md`](docs/projeto/decisoes.md) | Registro de decisões |
| [`docs/projeto/direcao-de-arte.md`](docs/projeto/direcao-de-arte.md) | Direção de arte: o padrão visual de todos os módulos |
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
