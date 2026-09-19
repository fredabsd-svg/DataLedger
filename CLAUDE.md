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
| [docs/projeto/fontes-de-referencia.md](docs/projeto/fontes-de-referencia.md) | Onde pesquisar o domínio, e como usar sem copiar. **Leia antes de planejar módulo novo.** |
| [docs/projeto/mapa-funcional-fiscal.md](docs/projeto/mapa-funcional-fiscal.md) | Capacidades da escrita fiscal e o achado sobre formato de intercâmbio. |
| [docs/projeto/direcao-de-arte.md](docs/projeto/direcao-de-arte.md) | **Contrato visual do produto.** Obrigatório antes de criar tela de módulo novo (Fiscal, Folha, Honorários, Paralegal, Lalur) ou acrescentar tela às existentes. |
| [docs/projeto/mapa-funcional-contabil.md](docs/projeto/mapa-funcional-contabil.md) | Capacidades da contabilidade, cruzamento honesto com o código e o que **não** copiar. |
| [docs/projeto/personalizacao-de-relatorio.md](docs/projeto/personalizacao-de-relatorio.md) | As **três classes de documento** (conferência, demonstração, livro) e o que cada norma fixa. **Leia antes de mexer em qualquer relatório imprimível**, de qualquer módulo. |
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

## Estado do projeto: um lugar só

**[docs/agents/estado.md](docs/agents/estado.md) é a fonte única do estado.**
O `README.md` aponta para ele e **não** repete a informação.

Instrução permanente do Fred, de 2026-09-13, depois de encontrar o README
afirmando no topo que existia "apenas um esqueleto sem módulo de negócio"
enquanto o mesmo arquivo documentava a contabilidade funcionando — a afirmação
obsoleta estava em **quatro** lugares:

> Isso precisa ser atualizado para não confundir os agentes nem quem entrar no
> projeto. **Nunca esqueça de atualizar.**

Regras que decorrem disso:

1. **Ao concluir qualquer etapa, atualize `docs/agents/estado.md`.** Faz parte
   da entrega, como teste e commit.
2. **Não descreva o estado do projeto em outro arquivo.** Se precisar
   mencioná-lo, aponte para a fonte única.
3. `apps/core/tests/test_documentacao_do_estado.py` verifica isso na
   integração contínua: etapa com plano que não apareça no README ou no
   `estado.md` **reprova o build**, e afirmações já desmentidas não podem
   voltar.

A causa do problema não foi distração, foi **duplicação**. Texto repetido em
quatro lugares diverge assim que alguém atualiza um.

## Regras impostas por mecanismo

Parte das regras deixou de ser pedido: gancho de sessão que injeta o
`AGENTS.md` no contexto, workflow que reprova PR sem atestado de leitura, teste
que reprova estado divergente, e o job que mede o documento imprimível no
navegador real.

⚠️ **Mas há uma diferença que você precisa saber antes de confiar em qualquer
uma delas: verificação que RODA e reprova não é verificação que IMPEDE o
merge.** A `main` **não tem proteção de branch** — medido em três endpoints da
API do GitHub na nona auditoria
([J2](docs/auditorias/2026-09-19-dl-026-dl-028-rodada-9.md)). Então, hoje, as
verificações ficam vermelhas e **não bloqueiam nada**: são conselho.

A tabela no fim do [AGENTS.md](AGENTS.md) diz, linha por linha, o que impede o
merge e o que não impede, e como ligar o que falta. **Não presuma imposição a
partir da existência de um workflow.**

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

Desde a [DL-019](docs/planos/DL-019-portabilidade-entre-ferramentas-de-ia.md),
`.claude/agents/*.md` é **arquivo gerado**: a fonte de cada papel está em
`docs/agents/papeis/`, e dela sai também o formato do **Codex CLI**
(`.codex/agents/*.toml`). São **só esses dois** — Copilot e Gemini ficaram de
fora por decisão (DE-037). Editar o arquivo gerado é erro, e o teste acusa —
altere a fonte e rode `python scripts/gerar_agentes.py --escrever`.
