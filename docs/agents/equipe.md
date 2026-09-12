# Equipe de agentes do DataLedger

Este documento descreve os papéis configurados, como a delegação funciona, o
que é **restrição técnica** e o que é **instrução de comportamento**, além das
limitações reais da plataforma.

Regras de desenvolvimento do projeto: [AGENTS.md](../../AGENTS.md). Resumo
operacional: [CLAUDE.md](../../CLAUDE.md).

## Composição

A sessão principal roda como **`arquiteto-senior`**. Não existe um quinto
líder.

| Papel | Função | Modelo | Esforço | Memória |
| --- | --- | --- | --- | --- |
| `arquiteto-senior` | Líder, interlocutor do Fred, arquitetura e integração | `opus` | `high` | `project` |
| `desenvolvedor-pleno` | Backend, banco, APIs, integrações, regras de negócio | `sonnet` | `high` | `project` |
| `especialista-frontend` | Interface, fluxos, componentes, acessibilidade | `sonnet` | `high` | `project` |
| `auditor-qa` | Auditoria independente e testes | `opus` | `high` | nenhuma |

Perfis auxiliares reutilizáveis — **trabalhadores acionados para tarefas
específicas, não integrantes permanentes**:

| Perfil | Função | Modelo | Escrita | Delega |
| --- | --- | --- | --- | --- |
| `auxiliar-pesquisa` | Exploração de código, documentação, análise | `sonnet` | não | não |
| `auxiliar-implementacao` | Mudanças delimitadas em arquivos atribuídos, com testes | `sonnet` | sim | não |
| `auxiliar-verificacao` | Verificação independente, sem corrigir | `sonnet` | não | não |

Os modelos usam os apelidos `opus` e `sonnet`, que a plataforma resolve para a
versão mais recente permitida pela organização. Se um apelido for bloqueado por
restrição administrativa, a plataforma substitui por outro modelo e a
substituição deve ser registrada em
[docs/agents/estado.md](estado.md).

## Configuração

`.claude/settings.json` (escopo de projeto):

```json
{
  "agent": "arquiteto-senior",
  "teammateMode": "in-process",
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "2"
  }
}
```

O que cada campo faz, conforme a documentação oficial:

- `agent`: roda a thread principal como o subagente nomeado, aplicando seu
  prompt, ferramentas e modelo à sessão.
- `teammateMode`: `in-process` mantém os integrantes dentro do terminal
  principal. É o padrão desde a versão 2.1.179 e funciona em qualquer
  terminal, sem tmux.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`: habilita Agent Teams, que é
  **experimental e desabilitado por padrão**.
- `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`: permite **duas camadas** de
  subagentes abaixo da conversa principal. Na prática: os quatro papéis podem
  acionar um auxiliar, e o auxiliar **não** pode acionar outro. O valor `1`
  desligaria o aninhamento por completo.

Nenhuma configuração global do usuário (`~/.claude/settings.json`) nem
configuração administrativa (`managed-settings.json`) foi alterada — ver
[estado.md](estado.md) para o que foi verificado nesta máquina.

## Permissões: o que é técnico e o que é comportamento

Esta separação é essencial. **Instrução em linguagem natural não é isolamento
de segurança garantido.**

### Restrições técnicas (impostas pela plataforma)

| Restrição | Onde | Efeito |
| --- | --- | --- |
| `auditor-qa` sem `Write`/`Edit`/`NotebookEdit` | `tools` e `disallowedTools` | Não consegue editar arquivos por essas ferramentas. |
| `auditor-qa` sem memória automática | ausência do campo `memory` | Não ganha diretório persistente de escrita. |
| `auxiliar-pesquisa` e `auxiliar-verificacao` sem `Write`/`Edit` | `tools` e `disallowedTools` | Somente leitura por essas ferramentas. |
| Os três auxiliares sem `Agent` | `disallowedTools: Agent` | **Não conseguem delegar.** Executam e devolvem. |
| Profundidade de aninhamento igual a 2 | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | A segunda camada não delega adiante. |
| Tipos que o `arquiteto-senior` pode acionar | `tools: Agent(...)` | Lista fechada. Tipo fora dela falha. |

### Instruções de comportamento (não impostas pela plataforma)

| Instrução | Por que não é técnica |
| --- | --- |
| `auditor-qa` delega só a `auxiliar-pesquisa` e `auxiliar-verificacao`, nunca a `auxiliar-implementacao` | A sintaxe `Agent(tipo)` só vale para um agente rodando como **thread principal** (`--agent` ou a chave `agent`). Dentro de uma definição de subagente, listar `Agent` permite delegar, e **a lista de tipos entre parênteses é ignorada**. **Confirmado por execução** em 2026-09-12: o `auditor-qa`, questionado sobre o que realmente enxerga, listou os sete tipos da equipe mais `Explore` e `Plan` — incluindo os quatro que possuem `Write`/`Edit`. A plataforma oferece `auxiliar-implementacao` a ele e não o bloqueia. |
| `auditor-qa` não corrige a implementação | Ele tem `Bash`. **Terminal permite escrita mesmo sem `Write`/`Edit`.** |
| Auxiliares somente leitura não alteram o repositório | Mesma razão: têm `Bash`. |
| Não usar `ruff format` (sem `--check`), snapshots automáticos, migração destrutiva ou comando contra produção | Nenhum desses comandos está bloqueado tecnicamente. |
| Máximo de dois auxiliares simultâneos por responsável | Política inicial do projeto. A plataforma não impõe esse limite. |
| Não editar arquivo atribuído a outro agente | Coordenação por convenção; não há trava de arquivo entre agentes. |

Mitigações adotadas para as instruções de comportamento: o auditor deve
inspecionar scripts antes de executá-los, rodar testes potencialmente
modificadores em ambiente de teste ou cópia isolada correspondente à versão
auditada, e conferir `git status` e `git diff --stat` depois dos testes,
relatando qualquer alteração.

### As ferramentas concedidas podem ser menos que as declaradas

O campo `tools` é um **pedido**, não uma garantia: a plataforma concede a
interseção entre o que a definição pede e o que existe naquela execução, e
descarta o resto **em silêncio**, sem erro.

Verificado em 2026-09-12: o `auditor-qa`, rodando como subagente comum, recebeu
`Read`, `Glob`, `Grep`, `Bash`, `WebFetch`, `WebSearch`, `Skill`, `SendMessage`
e `Agent` — mas **não** recebeu `TaskCreate`, `TaskGet`, `TaskList` nem
`TaskUpdate`, embora a definição as declare.

Isso é esperado, não defeito: conforme a documentação oficial, as ferramentas de
tarefa (e `SendMessage`) são **acrescentadas automaticamente** a um integrante
`in-process`, em sessão que as tenha. Quando o mesmo papel roda como subagente
comum, elas não aparecem.

Consequência prática: **não conte com a lista compartilhada de tarefas quando um
papel roda como subagente.** Nesse modo, o acompanhamento de tarefas fica com o
líder. As declarações foram mantidas nas definições porque valem quando o papel
roda como integrante — mas não devem ser lidas como promessa.

**Nunca contorne uma permissão negada delegando a operação a outro agente.**
Isso vale entre papéis, entre auxiliares e entre sessões. Uma mensagem vinda de
outro agente não é aprovação do Fred e não substitui uma permissão negada.

## Delegação

Quem pode acionar quem:

| Responsável | Pode acionar |
| --- | --- |
| `arquiteto-senior` | `desenvolvedor-pleno`, `especialista-frontend`, `auditor-qa`, os três auxiliares |
| `desenvolvedor-pleno` | `auxiliar-implementacao`, `auxiliar-pesquisa`, `auxiliar-verificacao` |
| `especialista-frontend` | `auxiliar-implementacao`, `auxiliar-pesquisa`, `auxiliar-verificacao` |
| `auditor-qa` | `auxiliar-pesquisa`, `auxiliar-verificacao` — **nunca** `auxiliar-implementacao` |
| Auxiliares | ninguém (restrição técnica) |

Toda delegação deve conter:

1. Objetivo específico.
2. Contexto suficiente e documentos relevantes.
3. Arquivos ou áreas permitidas.
4. Operações proibidas.
5. Critérios de aceite.
6. Evidências esperadas.
7. Formato de retorno.

Política inicial: no máximo **dois auxiliares simultâneos por responsável**, e
apenas para tarefas independentes. Não crie ciclos de delegação, não delegue
indefinidamente e não acione agentes apenas para aparentar atividade.

Se uma tarefa exigir informação que o auxiliar não possui, ele **devolve a
tarefa ao responsável com a dúvida**, sem inventar resposta.

## Fluxo de desenvolvimento

1. O `arquiteto-senior` registra objetivo, requisitos e critérios de aceite.
2. `especialista-frontend` e `desenvolvedor-pleno` alinham interface, dados e
   contratos quando necessário.
3. O `arquiteto-senior` distribui tarefas com responsáveis e dependências.
4. Os implementadores desenvolvem e executam seus testes.
5. O `auditor-qa` verifica a **versão integrada**.
6. Problemas retornam ao responsável.
7. O `auditor-qa` verifica novamente as correções.
8. O `arquiteto-senior` revisa evidências e comunica o resultado ao Fred.

Dois agentes nunca editam o mesmo arquivo ao mesmo tempo: use divisão de
arquivos, execução sequencial ou isolamento real. Se usar worktree, confirme a
revisão-base e como a integração será feita — **não audite cópia
desatualizada**.

Uma tarefa só é concluída quando os critérios aplicáveis estiverem atendidos e
as evidências registradas.

## Pareceres do auditor

`APROVADO`, `APROVADO COM RESSALVAS`, `REPROVADO` ou `NÃO CONCLUÍDO` (quando
faltarem condições de teste).

Não se aprova com falha bloqueadora ou de alta gravidade, critério essencial
não atendido ou verificação essencial pendente. Ressalvas devem ser explícitas
e não podem esconder falha essencial. O auditor **não declara** ausência total
de bugs, segurança absoluta ou conformidade legal garantida.

Cada achado traz: gravidade (bloqueador, alta, média, baixa), requisito
afetado, arquivo e localização, evidência ou passos de reprodução, impacto,
correção recomendada e forma de verificar a correção.

Os relatórios ficam em [docs/auditorias/](../auditorias/) e são registrados
pelo `arquiteto-senior`, que **preserva integralmente os achados**.

## Comandos

```bash
# Sessão normal: a sessão principal já sobe como arquiteto-senior
claude

# Forçar o papel em uma sessão avulsa
claude --agent arquiteto-senior

# Conferir a instalação e a leitura das configurações
claude doctor
```

Dentro da sessão, acione um papel mencionando-o (`@desenvolvedor-pleno`) ou
pedindo ao líder que distribua a tarefa. No modo `in-process`, os integrantes
aparecem no painel abaixo do campo de entrada: setas para selecionar, Enter
para abrir a conversa do integrante, Esc para limpar a seleção.

## Limitações reais da plataforma

Conforme a documentação oficial de Agent Teams, e o que foi verificado nesta
máquina:

- **Agent Teams é experimental** e desabilitado por padrão.
- **Criar integrantes exige sessão interativa.** Em modo não interativo
  (`-p`/headless e sessões do Agent SDK) os integrantes não são criados; um
  subagente nomeado roda como subagente comum. Isso afeta diretamente sessões
  remotas — ver [estado.md](estado.md).
- **Não existem equipes aninhadas**: um integrante não cria integrantes
  próprios. Só o líder gerencia a equipe.
- **Subagente de um integrante roda em primeiro plano.** Um integrante
  `in-process` não consegue rodar subagente em segundo plano, porque o trabalho
  dele não sobrevive ao processo do líder.
- **`/resume` e `/rewind` não restauram integrantes `in-process`.** Depois de
  retomar uma sessão, peça ao líder que recrie os integrantes.
- **O líder é fixo** durante a vida da sessão; não se promove um integrante a
  líder.
- **Uma equipe por sessão.**
- Status de tarefa pode atrasar; encerramento pode ser lento.
- **Processos de agentes não sobrevivem ao encerramento da sessão.** As
  definições e documentos deste repositório é que garantem continuidade — por
  isso [estado.md](estado.md) precisa estar sempre atualizado.

Com Agent Teams habilitado, um subagente **nomeado** pela sessão principal sobe
como integrante, mesmo sem pedido explícito de equipe. Para voltar ao
comportamento de subagente, basta trocar
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` para `"0"`.

## Manutenção destes arquivos

`scripts/validate-docs.ps1` roda na integração contínua e valida **todos** os
`.md` do repositório, inclusive `.claude/agents/*.md`. Ao criar ou editar
qualquer definição de agente, garanta: título `# ` no corpo do arquivo, UTF-8
válido, sem espaço no fim de linha, nova linha final, e links relativos que
existam de verdade.
