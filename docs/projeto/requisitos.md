# Requisitos do DataLedger

Este documento separa **requisitos confirmados**, **hipóteses** e
**pendências**. A separação é obrigatória: hipótese nunca é apresentada como
requisito confirmado.

Fonte primária do escopo: [docs/escopo.md](../escopo.md). Regras de
desenvolvimento: [AGENTS.md](../../AGENTS.md).

> Auditoria de software não substitui validação profissional das regras
> contábeis e legais. Todo item marcado como regra contábil ou fiscal depende
> de validação do Fred, como responsável técnico do domínio.

## Legenda

| Estado | Significado |
| --- | --- |
| **Confirmado** | Declarado pelo Fred ou presente em documento versionado do projeto. |
| **Hipótese** | Presumido para permitir avanço. Precisa de validação antes de virar comportamento definitivo. |
| **Pendência** | Falta informação, e isso bloqueia ou arrisca a entrega. |

## Confirmados

Estes itens vêm do escopo e das regras já versionadas no repositório, e estão
refletidos em código já integrado ou em planos aprovados.

### Produto e plataforma

| ID | Requisito | Origem |
| --- | --- | --- |
| RC-01 | Aplicação web para escritórios de contabilidade brasileiros, reunindo Fiscal, Folha, Contabilidade, Honorários e Processos/Paralegal. | [escopo.md](../escopo.md) |
| RC-02 | Vários escritórios, cada um com empresas e estabelecimentos isolados dos demais. | [escopo.md](../escopo.md) |
| RC-03 | Cadastro central de empresas, sócios, responsáveis, contatos e atividades. | [escopo.md](../escopo.md) |
| RC-04 | Perfis por papel: administrador, gestor, analistas por departamento, financeiro, paralegal e cliente. | [escopo.md](../escopo.md) |
| RC-05 | Seletores visíveis de empresa, estabelecimento e competência. | [escopo.md](../escopo.md) |
| RC-06 | Trilha de auditoria de ator, contexto, operação e resultado. | [escopo.md](../escopo.md), `apps/auditoria/` |

### Engenharia obrigatória

| ID | Requisito | Origem |
| --- | --- | --- |
| RC-10 | Precisão monetária exata, com escala e arredondamento explícitos; proibido ponto flutuante binário comum em cálculo monetário. | [AGENTS.md](../../AGENTS.md) §10 |
| RC-11 | Lançamento efetivado tem total de débitos igual ao de créditos. | [AGENTS.md](../../AGENTS.md) §10 |
| RC-12 | Rascunho é distinguível de lançamento efetivado. | [AGENTS.md](../../AGENTS.md) §10 |
| RC-13 | Operações relacionadas preservam atomicidade e consistência. | [AGENTS.md](../../AGENTS.md) §8 |
| RC-14 | Importação ou requisição repetida não gera duplicidade silenciosa. | [AGENTS.md](../../AGENTS.md) §8 |
| RC-15 | Correção de lançamento efetivado segue procedimento rastreável (estorno ou ajuste). | [AGENTS.md](../../AGENTS.md) §10 |
| RC-16 | Período encerrado exige controle explícito para alteração ou reabertura. | [AGENTS.md](../../AGENTS.md) §10 |
| RC-17 | Autorização verificada no servidor, não apenas na interface. | [AGENTS.md](../../AGENTS.md) §11 |
| RC-18 | Isolamento entre empresas em consultas, relatórios, exportações, arquivos e tarefas em segundo plano. | [AGENTS.md](../../AGENTS.md) §11 |
| RC-19 | Relatórios e saldos conciliáveis com os lançamentos de origem. | [AGENTS.md](../../AGENTS.md) §10 |
| RC-20 | Testes com dados sintéticos ou devidamente anonimizados. | [AGENTS.md](../../AGENTS.md) §7 |
| RC-21 | Cálculo determinístico separado da IA; a IA consulta, explica e propõe, mas não produz resultado oficial. | [AGENTS.md](../../AGENTS.md) §11 |

### Stack técnica

| ID | Requisito | Origem |
| --- | --- | --- |
| RC-30 | Backend Django 6.1 com Django REST Framework. | `requirements/base.txt` |
| RC-31 | Banco relacional PostgreSQL 16. | `docker-compose.yml`, `.github/workflows/backend.yml` |
| RC-32 | Verificações obrigatórias: `ruff check`, `ruff format --check`, `manage.py check`, `manage.py migrate`, `pytest`. | `.github/workflows/backend.yml` |
| RC-33 | Validação de documentação por `scripts/validate-docs.ps1` na integração contínua. | `.github/workflows/documentation.yml` |
| RC-34 | Interface em templates Django, em `templates/`. | Código integrado |

## Hipóteses

Itens presumidos a partir do repositório, **ainda não confirmados pelo Fred**.
Cada um precisa de validação antes de virar comportamento definitivo.

| ID | Hipótese | Por que foi presumida | Como validar |
| --- | --- | --- | --- |
| HI-01 | O próximo módulo a evoluir é Contabilidade, continuando a DL-006, antes de Fiscal e Folha. | É a última etapa implementada e a base para integração dos demais módulos. | Confirmar prioridade com o Fred. |
| HI-02 | A jurisdição é exclusivamente Brasil, com foco inicial em um único regime por empresa por competência. | O escopo cita Simples Nacional, Lucro Presumido e Lucro Real, sem definir ordem. | Confirmar qual regime atender primeiro. |
| HI-03 | A escala monetária padrão é duas casas decimais, com arredondamento definido por regra específica quando houver. | Prática contábil usual; o escopo exige política explícita mas não a fixa. | Fred definir a política por tipo de cálculo. |
| HI-04 | A interface continua em templates Django renderizados no servidor, sem SPA. | É o padrão já integrado no repositório. | Confirmar antes de qualquer investimento em frontend. |
| HI-05 | "Escritório" é a fronteira de isolamento mais externa, e "empresa" a interna. | Modelagem observada em `apps/tenancy/` e `apps/empresas/`. | Confirmar com o Fred e com o auditor. |
| HI-06 | O ambiente de desenvolvimento usa Python 3.13 ou superior. | A CI usa 3.14 e Django 6.1.1 exige 3.12+; o contêiner padrão traz 3.11. | Fixar a versão mínima suportada. |

## Pendências

Faltam informações. Cada item indica o impacto de seguir sem a resposta.

| ID | Pendência | Impacto se não for resolvida |
| --- | --- | --- |
| PE-01 | Qual módulo e qual rotina do escritório têm prioridade de negócio agora? | Sem isso, o backlog é ordenado por dependência técnica, não por valor. |
| PE-02 | Política de arredondamento por tipo de cálculo (fiscal, folha, contábil) e em qual etapa arredondar. | Risco de divergência de centavos entre relatório e lançamento. |
| PE-03 | Regime tributário e porte das empresas atendidas inicialmente. | Define a complexidade do módulo Fiscal e o que pode ficar fora do escopo. |
| PE-04 | Volume esperado: número de escritórios, empresas por escritório e lançamentos por competência. | Define paginação, índices e estratégia de relatório. |
| PE-05 | Como é feito hoje o fechamento e a reabertura de período no escritório do Fred. | RC-16 depende do procedimento real, não de uma suposição. |
| PE-06 | Há migração de dados de sistema atual? Em qual formato? | Muda prioridade de importadores e de idempotência. |
| PE-07 | Política de backup e restauração, e quem a executa. | Exigida pelas regras de engenharia; hoje não existe procedimento verificado. |
| PE-08 | Quais papéis de usuário existem de fato no escritório e o que cada um pode fazer. | RC-04 e RC-17 dependem da matriz real de permissões. |
| PE-09 | O trabalho encadeado dos PRs #7, #8 e #9 deve ser concluído antes de nova etapa? | Ver [estado.md](../agents/estado.md); afeta qual revisão-base a equipe usa. |

## Como atualizar

O `arquiteto-senior` mantém este documento. Ao confirmar uma hipótese, mova-a
para a tabela de confirmados citando a origem da confirmação. Ao resolver uma
pendência, registre a decisão em
[docs/projeto/decisoes.md](decisoes.md) e o requisito resultante aqui.
