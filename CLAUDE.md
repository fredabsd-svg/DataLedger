# CLAUDE.md — instruções para agentes no DataLedger

DataLedger é um sistema contábil para escritórios de contabilidade
brasileiros. Responsável pelo produto: **Fred**, contador. Converse em
**português**.

## Leitura obrigatória

**Antes de editar qualquer arquivo, leia [AGENTS.md](AGENTS.md) integralmente.**
Ele é a regra de desenvolvimento do projeto e prevalece sobre este arquivo em
caso de conflito. Este documento é apenas o resumo operacional.

| Documento | Para quê |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Regras obrigatórias de desenvolvimento, testes, Git e PR. |
| [docs/escopo.md](docs/escopo.md) | Escopo funcional do produto. |
| [docs/agents/equipe.md](docs/agents/equipe.md) | Papéis, delegação, permissões e limitações da equipe de agentes. |
| [docs/agents/estado.md](docs/agents/estado.md) | Estado atual e próximo passo. |
| [docs/projeto/requisitos.md](docs/projeto/requisitos.md) | Requisitos confirmados, hipóteses e pendências. |
| [docs/projeto/backlog.md](docs/projeto/backlog.md) | Tarefas, prioridades, dependências e critérios de aceite. |
| [docs/projeto/decisoes.md](docs/projeto/decisoes.md) | Decisões arquiteturais e justificativas. |
| [docs/planos/](docs/planos/) | Plano versionado de cada demanda `DL-xxx`. |
| [docs/auditorias/](docs/auditorias/) | Relatórios de auditoria efetivamente realizados. |

## Stack

Django 6.1 + Django REST Framework, PostgreSQL 16, Python 3.14 na integração
contínua. Apps em `apps/`, configuração em `config/`, templates Django em
`templates/`. Dependências em `requirements/`.

## Comandos de verificação

```bash
ruff check .                  # lint
ruff format --check .         # formatação (nunca "ruff format" em auditoria)
python manage.py check        # verificação do Django
python manage.py migrate      # migrações em banco vazio
pytest                        # testes
pwsh ./scripts/validate-docs.ps1   # validação da documentação
```

`scripts/validate-docs.ps1` roda na integração contínua e verifica **todos** os
arquivos `.md` do repositório, inclusive `.claude/agents/*.md`. Cada arquivo
Markdown precisa de: título `# ` no corpo, UTF-8 válido, sem espaço no fim da
linha, com nova linha final, e links relativos que existam de verdade.

## Regras de engenharia do domínio contábil

Transforme em teste toda regra aplicável à sua tarefa:

- Precisão monetária exata, com escala e arredondamento explícitos. **Não use
  ponto flutuante binário comum** para cálculo monetário que exija exatidão.
- Lançamento efetivado: total de débitos igual ao de créditos.
- Rascunho é distinguível de lançamento efetivado.
- Operações relacionadas preservam atomicidade e consistência.
- Importação ou requisição repetida não gera duplicidade silenciosa.
- Correção de lançamento efetivado segue procedimento rastreável.
- Período encerrado exige controle explícito para alteração ou reabertura.
- Autorização é verificada **no servidor**, não apenas na interface.
- Dados de empresas diferentes ficam isolados em consultas, relatórios,
  exportações, arquivos e tarefas em segundo plano.
- Trilha de auditoria protegida, suficiente e sem expor segredos.
- Relatórios e saldos conciliáveis com os lançamentos de origem.
- Backup e restauração planejados e verificados.
- Testes com dados sintéticos ou devidamente anonimizados.

Não invente alíquota, incidência, prazo, fórmula ou leiaute oficial. Distinga
**regra confirmada**, **hipótese** e **pendência**, e leve dúvida material ao
Fred. Auditoria de software não substitui validação profissional das regras
contábeis e legais.

## Honestidade nos relatórios

Classifique cada item como **Implementado**, **Inspecionado**, **Testado**,
**Não testado**, **Bloqueado** ou **Fora do escopo**.

Não diga que um teste passou sem tê-lo executado. Build bem-sucedido não é
prova de correção funcional. Falha preexistente deve ser registrada, não
escondida.

## Segredos

Nunca exiba, versione ou registre em memória: credenciais, chaves, certificados
privados, `.env` real ou dados reais de clientes. `.env` está no `.gitignore`;
use `.env.example` como referência.

## Equipe de agentes

A sessão principal roda como **`arquiteto-senior`** (definido em
`.claude/settings.json`). Os integrantes são `desenvolvedor-pleno`,
`especialista-frontend` e `auditor-qa`. Os perfis `auxiliar-pesquisa`,
`auxiliar-implementacao` e `auxiliar-verificacao` são trabalhadores acionados
para tarefas específicas e **não delegam**.

O `auditor-qa` não tem `Write`/`Edit` e **não corrige a implementação**: ele
registra o achado e o encaminha ao responsável. Detalhes, permissões e
limitações reais em [docs/agents/equipe.md](docs/agents/equipe.md).
