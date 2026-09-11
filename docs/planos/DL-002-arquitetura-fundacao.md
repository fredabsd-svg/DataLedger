# DL-002 — Arquitetura e fundação técnica

## Objetivo e diagnóstico

Definir a stack técnica do DataLedger e criar o esqueleto executável mínimo
que a suporta, sem implementar ainda nenhum modelo de negócio dos módulos
(Fiscal, Folha, Contabilidade, Honorários, Processos/Paralegal). Esta é a
etapa "Arquitetura e controles" prevista no [README](../../README.md).

Na inspeção inicial desta demanda, o repositório continha apenas a
documentação da DL-001: nenhum código de aplicação, dependência ou
verificação de backend existia. As decisões de stack foram levantadas com o
responsável do produto antes da implementação, por serem bloqueantes.

## Decisões de arquitetura

| Decisão | Escolha | Motivo |
| --- | --- | --- |
| Linguagem/backend | Python 3.14, Django 6.1 + Django REST Framework | Fornece ORM maduro com suporte nativo a `DECIMAL`/`NUMERIC` (obrigatório para valores fiscais e contábeis), sistema de permissões e grupos, admin interno e migrações prontos, reduzindo retrabalho nas etapas de fundação (autenticação, permissões, auditoria). |
| Frontend | Templates do Django renderizados no servidor, com HTMX e Alpine.js para interatividade pontual | Um único projeto e um único processo de build, mais simples de operar em uma VPS própria; adequado ao perfil de telas de cadastro, listagem e formulário previsto no escopo. |
| Banco de dados | PostgreSQL 16 | Precisão decimal exata para valores monetários, suporte maduro a transações e isolamento, adequado ao volume e às exigências de auditoria do domínio contábil. |
| Hospedagem alvo | VPS própria com Docker Compose (aplicação + banco) | Escolha do responsável pelo produto nesta etapa; mantém a arquitetura portável (containers) caso a hospedagem mude no futuro. |
| Dependências Python | `requirements/base.txt` e `requirements/dev.txt`, versões fixadas | Simplicidade compatível com "evitar abstrações prematuras"; um gerenciador adicional (Poetry/PDM) pode ser avaliado quando houver necessidade concreta. |
| Servidor de aplicação | Gunicorn atrás do próprio container, arquivos estáticos servidos por WhiteNoise | Dispensa um serviço adicional (ex.: Nginx) nesta etapa inicial; pode ser adicionado depois como proxy reverso se necessário. |
| Lint/formatação/testes | Ruff (lint e formatação) e Pytest + pytest-django | Ferramentas rápidas e amplamente adotadas no ecossistema Python atual, com configuração única em `pyproject.toml`. |

Fora do escopo desta etapa, tratado nas etapas seguintes do roadmap:

- Modelo de dados de negócio (escritórios, empresas, usuários, permissões) —
  etapa "Fundação" do README.
- Autenticação, autorização e auditoria.
- Servidor MCP e assistente de IA.
- Fila de tarefas em segundo plano (Celery/outro), quando houver caso de uso
  concreto (importação assíncrona, por exemplo).
- Proxy reverso, TLS e configuração definitiva de produção na VPS.
- Proteção da branch `main` no GitHub (requer ação administrativa fora do
  código; ver "Riscos, limitações e próximos passos").

## Etapa e entregáveis

- Estado deste registro: `em validação`. O resultado de publicação e CI deve
  constar no PR, associado ao commit testado.
- Branch de trabalho: `feat/dl-002-arquitetura-fundacao`.
- Destino: `main`.
- Entregáveis:
  - Este documento de plano e decisão de arquitetura.
  - Projeto Django mínimo (`manage.py`, `config/`, `apps/core/`) com um
    endpoint de verificação de saúde (`/api/health/`).
  - Dependências fixadas em `requirements/base.txt` e `requirements/dev.txt`.
  - `Dockerfile` e `docker-compose.yml` (aplicação + PostgreSQL).
  - `.env.example` documentando as variáveis de ambiente necessárias.
  - Configuração de lint/formatação/testes em `pyproject.toml`.
  - Workflow de CI `.github/workflows/backend.yml` (lint, formatação,
    `manage.py check`, migrações em banco vazio, testes).
  - Correção do filtro de diretórios ignorados em
    `scripts/validate-docs.ps1`, que passou a listar `.md` de dependências
    Python (`.venv`, pacotes) após a introdução do projeto Python.
  - Atualização do README com instruções reais de execução local.
- Dependências: acesso de escrita ao repositório e GitHub Actions habilitado
  para a execução remota do novo workflow.
- Fora do escopo: listado na seção anterior.

## Critérios de aceite

- O sistema fica de pé localmente (`manage.py runserver`) e via Docker
  Compose, respondendo `200 {"status": "ok"}` em `/api/health/`.
- `manage.py check` não aponta problemas.
- Migrações padrão do Django aplicam em um banco vazio.
- `ruff check` e `ruff format --check` passam sem alterações pendentes.
- A suíte Pytest passa, incluindo um teste automatizado do endpoint de saúde.
- O validador de documentação (`scripts/validate-docs.ps1`) continua
  aprovando os documentos do repositório após a criação da `.venv` local.
- Nenhum segredo, certificado ou dado real é versionado; `.env` real está
  fora do controle de versão.
- CI documental (já existente) e o novo CI de backend são conferidos no
  commit publicado.

## Cenários de teste

| Cenário | Resultado esperado |
| --- | --- |
| Requisição `GET /api/health/` sem autenticação | HTTP 200 e corpo `{"status": "ok"}`, com verificação de que a consulta ao banco (`SELECT 1`) funciona. |
| `manage.py check` no projeto | Nenhum problema reportado. |
| `manage.py migrate` em banco novo (SQLite local e PostgreSQL na CI) | Todas as migrações padrão do Django aplicam sem erro. |
| `ruff check .` e `ruff format --check .` | Sem apontamentos. |
| `pytest` | Testes passam, incluindo o teste de saúde. |
| `scripts/validate-docs.ps1` com `.venv` presente no repositório | Continua aprovando, sem listar arquivos de dependências como documentação inválida. |
| `scripts/validate-docs.ps1` em cópia com link relativo inexistente (cenário herdado da DL-001) | Continua falhando conforme esperado. |

## Impacto em segurança, dados, cálculos, contratos e desempenho

- **Segurança:** o endpoint de saúde não expõe dados de negócio nem exige
  autenticação, por ser destinado a monitoramento/orquestração. Configurações
  de segurança de produção (SSL redirect, cookies seguros, HSTS) foram
  incluídas, ativas apenas quando `DEBUG=False`. Nenhuma regra de permissão
  de negócio foi implementada ainda — o `DEFAULT_PERMISSION_CLASSES` do DRF
  exige autenticação por padrão para qualquer endpoint futuro que não a
  dispense explicitamente.
- **Dados:** nenhuma tabela de negócio foi criada. O banco de dados usa
  PostgreSQL com suporte nativo a `NUMERIC`, atendendo à exigência de
  precisão decimal quando os módulos forem implementados.
- **Cálculos:** não aplicável nesta etapa; nenhuma regra de cálculo foi
  implementada.
- **Contratos:** o único contrato exposto é o endpoint de saúde
  (`GET /api/health/`), documentado neste plano.
- **Desempenho:** sem impacto mensurável; volume de dados é zero nesta
  etapa.

## Estratégia de reversão

Não há migração de dados de produção nem usuários reais afetados. Reversão:
fechar o PR antes do merge ou, após integração, propor um commit de
reversão em novo PR, preservando o histórico. Como nenhuma etapa posterior
depende ainda deste código além da configuração base, a reversão não tem
efeitos colaterais em outros módulos.

## Validação reproduzível

Executado localmente em ambiente Windows, com Python 3.14 (instalado no
ambiente de desenvolvimento) e PowerShell 7 (instalado nesta etapa via
`winget install Microsoft.PowerShell`, necessário porque o script de
validação usa `[System.IO.Path]::GetRelativePath`, disponível apenas a
partir do PowerShell 7):

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux/macOS: source .venv/bin/activate
pip install -r requirements/dev.txt

python manage.py check
python manage.py migrate
pytest
ruff check .
ruff format --check .

pwsh -NoProfile -File scripts/validate-docs.ps1
```

Resultados obtidos em 11/09/2026:

- `python manage.py check`: nenhum problema encontrado.
- `python manage.py migrate` (SQLite local, `--run-syncdb`): todas as
  migrações padrão do Django aplicaram com sucesso.
- `pytest`: 1 teste executado, 1 aprovado (verificação do endpoint de
  saúde).
- `ruff check .`: sem apontamentos após correção automática de dois imports
  não usados nos arquivos gerados pelo `startapp`.
- `ruff format --check .`: sem apontamentos após formatação automática dos
  arquivos gerados.
- `scripts/validate-docs.ps1`: 6 arquivos Markdown aprovados, após a
  correção do filtro de diretórios ignorados.

**Limitação registrada:** este ambiente de desenvolvimento não possui Docker
nem PostgreSQL instalados, portanto `docker compose up` e a conexão real com
PostgreSQL não foram executados localmente. O workflow
`.github/workflows/backend.yml` cobre esse caminho na integração contínua,
com um serviço `postgres:16-alpine`; o resultado dessa execução deve ser
conferido no PR e não pode ser tratado como aprovado antes disso.

## Riscos, limitações e próximos passos

- **Proteção da branch `main`:** ainda não configurada. É uma ação
  administrativa no GitHub (fora do código-fonte) e precisa constar como
  etapa explícita de implantação, com teste das verificações obrigatórias e
  registro do que foi ativado, conforme a seção 13 do
  [AGENTS.md](../../AGENTS.md).
- **Ambiente de produção na VPS:** esta etapa entrega apenas os artefatos
  (`Dockerfile`, `docker-compose.yml`) necessários para rodar a aplicação em
  um servidor; o provisionamento, TLS, backups e monitoramento da VPS real
  ficam para uma etapa de implantação futura.
- **Fila de tarefas em segundo plano:** não avaliada nesta etapa por falta
  de caso de uso concreto; será decidida quando um módulo precisar de
  processamento assíncrono (ex.: importação de XML de NF-e).
- **Próxima etapa sugerida:** modelagem da fundação de dados compartilhada
  (escritórios, empresas, usuários e permissões) e autenticação, conforme a
  etapa "Fundação" do roadmap do README.

Hash do commit, link do PR, resultado da CI e eventuais ajustes serão
registrados na descrição do PR e no relatório de entrega; não inserir
identificadores fictícios neste documento.
