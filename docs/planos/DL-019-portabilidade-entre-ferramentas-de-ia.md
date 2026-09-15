# DL-019 — Portabilidade entre ferramentas de IA: um papel, vários modelos

**Estado:** em encerramento — ver "Como esta etapa fecha", no fim.

**Faixa de rigor (DE-038): ferramental interno.** Esta etapa não toca dado de
cliente, cálculo, período encerrado nem isolamento entre empresas. Pela regra
que ela própria originou, caberia **uma** rodada de auditoria, com o resto indo
para o backlog. Foram três, e isso custou horas do Fred — o registro fica aqui
porque a faixa passou a ser declarada **antes** de começar, e esta é a etapa que
ensinou o porquê.

| Item | Valor |
| --- | --- |
| Branch de trabalho | `claude/multi-model-ia-structure-k1um7i` |
| Branch de destino | `main` |
| Origem | Pedido do Fred em 2026-09-15: *"Você criou dentro do repositório uma pasta chamada `.Claude` e dentro dela tinha os agentes de IAs. Crie uma pasta chamada `.CODEX` e outra chamada `.AGENTS`, para eu poder usar com o ChatGPT e outros modelos (…) A ideia é que não só os modelos do Claude possam trabalhar, mas os outros também, e não fiquem perdidos e também possam criar agentes"* |

## O problema

A equipe de agentes do DataLedger existe em **um formato só**: sete arquivos em
`.claude/agents/*.md`, com frontmatter do Claude Code. Quem abrir o repositório
com ChatGPT/Codex, Gemini ou Copilot encontra as regras do
[AGENTS.md](../../AGENTS.md) — que é padrão aberto e já é lido por várias
ferramentas —, mas **não encontra os papéis**: não sabe que existe um auditor
que não corrige implementação, um auxiliar que não delega, nem por que essas
restrições existem.

O efeito prático é o que o Fred descreveu: o modelo "fica perdido". Ele
improvisa um papel, ignora a divisão de responsabilidades que o projeto usa
para separar quem implementa de quem audita, e a auditoria independente — que
já pegou bloqueador em cinco rodadas seguidas da DL-017 — deixa de existir
porque ninguém contou a ele que ela existe.

## Por que não são três pastas com três cópias

O pedido literal era criar `.CODEX` e `.AGENTS` com os agentes dentro, ao lado
de `.claude`. Isso resolve o sintoma e reintroduz a causa do problema que o
próprio Fred mandou corrigir em 2026-09-13, quando encontrou o estado do
projeto afirmado em quatro lugares e já divergente:

> *"Isso precisa ser atualizado para não confundir os agentes nem quem entrar no
> projeto. **Nunca esqueça de atualizar.**"*

Três cópias do papel do auditor divergem no primeiro ajuste. A regra que o
projeto extraiu daquele episódio está no [CLAUDE.md](../../CLAUDE.md) e vale
aqui sem exceção: **a causa da divergência é duplicação, não distração.**

Esta etapa entrega as pastas pedidas — e mais duas —, mas **geradas** a partir
de uma fonte única, com guarda na integração contínua que reprova o build se um
derivado divergir.

## Dois ajustes de forma, e o acerto do Fred no conteúdo

1. `AGENTS.md` já existe e é **arquivo**, não pasta. É a convenção aberta lida
   nativamente por Cursor, Jules, OpenCode, Zed, Roo Code, Cline, Kiro e
   (parcialmente) Copilot. Criar uma pasta `.AGENTS` competindo com ele
   atrapalharia em vez de ajudar.
2. Nomes de pasta em minúsculas. Linux diferencia maiúsculas: `.CODEX` não
   seria lido por ferramenta nenhuma.
3. **A intuição do Fred estava certa quanto ao `.agents`:** o Codex varre
   `.agents/skills/` de cada diretório até a raiz do repositório. A pasta que
   ele pediu existe de verdade na convenção — com outro propósito.

## Fontes consultadas

Levantamento de 2026-09-15, em documentação oficial. O que não foi confirmado
está marcado como tal e **não vira arquivo**.

| Ferramenta | Caminho lido no repositório | Formato | Confirmado |
| --- | --- | --- | --- |
| Codex CLI e Codex Cloud | `AGENTS.md` (raiz e subdiretórios, o mais próximo prevalece, limite padrão de 32 KiB) | Markdown puro | Sim |
| Codex CLI | `.codex/agents/<nome>.toml` — agentes customizados versionáveis | TOML: `name`, `description`, `developer_instructions` obrigatórios | Sim |
| Codex CLI | `.agents/skills/<nome>/SKILL.md` — mecanismo atual de fluxo reutilizável, substitui os prompts customizados | Markdown com frontmatter `name` e `description` | Sim |
| GitHub Copilot | `.github/copilot-instructions.md`; `.github/agents/*.agent.md` | Markdown com frontmatter; `description` obrigatório; corpo até 30.000 caracteres | Sim |
| Gemini CLI | `GEMINI.md` (hierárquico); `.gemini/agents/*.md` para subagentes | Markdown com frontmatter `name` e `description` | Sim |
| Gemini CLI | `AGENTS.md` **não** é lido por padrão; exige `context.fileName` nas configurações | JSON | Sim, e é limitação declarada |
| Cursor, Jules, OpenCode, Zed, Roo Code, Cline, Kiro | `AGENTS.md` na raiz | Markdown puro | Sim |
| ChatGPT (aplicativo/web, conector de GitHub) | nenhuma convenção de arquivo privilegiada | — | **Não confirmado.** O projeto não afirma que existe |
| Codex CLI | `.codex/config.toml` versionado no repositório | — | **Não confirmado.** Configuração é global, em `~/.codex`. Não será criado |
| Codex prompts customizados no repositório | — | — | **Confirmadamente inexistente**: vivem no diretório pessoal e estão descontinuados |

## O desenho

```text
docs/agents/papeis/<papel>.md      FONTE ÚNICA — frontmatter neutro + corpo
        │
        ├─ gera → .claude/agents/<papel>.md          (Claude Code)
        └─ gera → .codex/agents/<papel>.toml         (Codex CLI)
```

**Escopo reduzido a dois formatos em 2026-09-15**, durante a execução. Perguntei
ao Fred quais ferramentas ele usa de fato e a resposta foi direta: *"Codex pelo
terminal"*. Copilot e Gemini saíram — ver [DE-037](../projeto/decisoes.md) e o
critério 14, que nasceu dessa resposta. `.github/copilot-instructions.md`
permanece porque é ponteiro de custo zero, já existente desde a DL-014.

Regra de desenho desta etapa, que vale para o que vier depois:

- **Conteúdo substantivo** — o que um papel é, pode e não pode fazer — tem
  **uma fonte e é gerado** para cada formato.
- **Regra de processo** — o `AGENTS.md` — **não é copiada**: cada ferramenta
  ganha, quando precisa, um arquivo fino que **aponta** para ele. É o que
  `.github/copilot-instructions.md` já faz desde a DL-014.

## Honestidade obrigatória nos derivados

Restrição técnica e instrução de comportamento **não são a mesma coisa**, e a
diferença muda de ferramenta para ferramenta. Hoje:

- No Claude Code, `auditor-qa` não tem `Write`/`Edit`: a restrição é **técnica**
  (e mesmo assim ele tem `Bash`, que permite escrita — já declarado em
  [equipe.md](../agents/equipe.md)).
- Nos demais formatos, **não há campo equivalente confirmado**. A mesma
  restrição vira **apenas instrução**.

Cada arquivo gerado para ferramenta que não impõe a restrição DEVE dizer isso
no próprio corpo. Um papel que promete isolamento inexistente é pior que papel
nenhum.

Pelo mesmo motivo, os derivados **não fixam nome de modelo** fora do Claude
Code: identificadores de modelo mudam com frequência e o projeto não inventa
identificador. Onde a ferramenta aceita `model` opcional, o campo fica ausente
e o padrão do usuário prevalece.

## Critérios de aceite

| # | Critério | Como se verifica |
| --- | --- | --- |
| 1 | A geração inicial **não altera um único byte** dos sete arquivos em `.claude/agents/` | `git diff --stat .claude/agents/` vazio após rodar o gerador sobre a fonte extraída |
| 2 | Existe `docs/agents/papeis/<papel>.md` para os sete papéis, com frontmatter neutro e corpo em português | Leitura e execução do gerador |
| 3 | `.codex/agents/<papel>.toml` gerado para os sete, com `name`, `description` e `developer_instructions` | Arquivo existe e é TOML válido (`tomllib.load`) |
| 4 | ~~`.github/agents/<papel>.agent.md`~~ | **Fora do escopo** desde 2026-09-15: o Fred não usa Copilot |
| 5 | ~~`.gemini/agents/<papel>.md`~~ | **Fora do escopo** desde 2026-09-15: o Fred não usa Gemini |
| 6 | Links relativos são recalculados para a pasta de destino e continuam existindo | `scripts/validate-docs.ps1` (ou verificação equivalente) aprovada |
| 7 | Um teste reprova o build quando qualquer derivado divergir da fonte | Alterar um derivado à mão e ver o teste falhar; reverter e ver passar |
| 8 | Um teste reprova o build quando um papel existir na fonte e faltar em um dos quatro formatos | Remover um derivado e ver o teste falhar |
| 9 | Ferramenta que não impõe restrição de escrita recebe o aviso explícito no corpo | Teste que exige a frase-marcador nos formatos sem restrição técnica |
| 10 | `.agents/skills/` existe como **ponteiro**, sem copiar regra do `AGENTS.md` | Teste que reprova se o texto de regra do `AGENTS.md` aparecer duplicado. ~~`GEMINI.md`~~ **fora do escopo** desde 2026-09-15 (DE-037) — o critério foi corrigido tarde, e a incoerência virou o achado 4 da rodada 1 |
| 11 | Qualquer ferramenta consegue **criar um papel novo** seguindo um procedimento escrito | `docs/agents/como-criar-um-papel.md` existe, é citado nos quatro formatos e o procedimento foi executado de ponta a ponta uma vez |
| 12 | Nenhuma regressão na suíte | `pytest`, `ruff check`, `ruff format --check`, `python manage.py check` |
| 13 | O estado do projeto é atualizado | `DL-019` presente no README e em `docs/agents/estado.md` |
| 14 | **`AGENTS.md` não pode crescer até ser truncado em silêncio pelo Codex** | Teste reprova acima de 30.000 bytes. Medição de 2026-09-15: **22.601 bytes**, 69% do limite padrão de 32.768 |

### Por que o critério 14 existe

O Codex concatena os arquivos de instrução e **para ao atingir
`project_doc_max_bytes`, 32.768 por padrão**. Enquanto nenhuma pessoa da equipe
usava Codex, isso era nota de rodapé. Com o Fred usando Codex no terminal, virou
risco operacional: o `AGENTS.md` cresce a cada etapa, e quando estourar o limite
a ferramenta passará a ler uma versão **incompleta** das regras sem avisar
ninguém. O que some primeiro é o **fim** do arquivo — onde estão justamente
"Como estas regras são impostas" e a seção que apresenta a equipe.

É o mesmo padrão de defeito que o projeto já conhece: não é o erro que aparece,
é o que passa despercebido porque nada acusa.

## Cenários de teste

1. Gerador executado duas vezes seguidas produz o mesmo resultado (idempotência).
2. Derivado editado à mão → teste de sincronia falha com mensagem que aponta o
   arquivo e o comando de regeração.
3. Papel novo acrescentado só na fonte → teste falha até os quatro derivados
   existirem.
4. Papel removido da fonte → derivado órfão é detectado.
5. Fonte com frontmatter inválido → gerador falha com erro claro, sem gravar
   arquivo parcial.
6. TOML gerado é carregável por `tomllib` e o `developer_instructions` preserva
   acentuação (UTF-8).
7. Caminho de link inexistente na fonte → validação de documentação reprova.

## Impacto

- **Segurança e dados:** nenhum. A etapa não toca em código de negócio, modelo
  de dados, permissões do servidor nem cálculo. Não há migração.
- **Risco real:** um gerador com defeito corromperia as definições da equipe
  Claude, que é a ferramenta em uso hoje. Mitigado pelo critério 1 — a primeira
  geração tem de reproduzir os arquivos atuais byte a byte — e pelo teste de
  sincronia.
- **Reversão:** `git revert` do commit. Não há estado externo.

## O que esta etapa NÃO faz

- Não altera o `AGENTS.md` como regra; só acrescenta ponteiros para ele.
- Não configura nada fora do repositório (`~/.codex`, `~/.gemini` e as
  configurações pessoais continuam sendo do usuário).
- Não promete que ChatGPT no navegador leia o repositório de alguma forma
  especial — **isso não foi confirmado e não será afirmado**.
- Não cria papéis novos. Os sete existentes apenas passam a existir em quatro
  formatos.
- Não torna técnica, em outra ferramenta, uma restrição que lá é só instrução.

## Como esta etapa fecha

Decidido com o Fred em 2026-09-15, depois de duas reprovações e de ele cobrar o
tempo gasto: **a rodada 3 é a última.** Qualquer achado que ela traga e que não
esteja na lista de danos da [DE-038](../projeto/decisoes.md) — corromper dado,
errar cálculo, vazar entre empresas, desbalancear lançamento, alterar período
encerrado, derrubar o servidor — vira item de backlog nomeado, e a etapa fecha
assim mesmo. **Não haverá rodada 4.**

Isso não é aprovação antecipada, e a diferença importa: o parecer do auditor
será registrado na íntegra, seja ele qual for, e o que ficar aberto fica
**escrito como aberto**, não silenciado por encerramento.

### O que já funciona, independentemente do parecer

| Entrega | Situação |
| --- | --- |
| Sete papéis em `.codex/agents/*.toml` | Funcionando — o Codex CLI enxerga a equipe |
| Sete papéis em `.claude/agents/*.md` | Funcionando, **byte a byte idênticos** aos de antes da etapa |
| Fonte única em `docs/agents/papeis/` | Funcionando, com gerador e teste de sincronia |
| `AGENTS.md` apresentando a equipe a qualquer ferramenta | Funcionando |
| Procedimento para criar papel novo | Escrito e executado de ponta a ponta |
| Guarda contra truncamento silencioso do `AGENTS.md` no Codex | Funcionando (22.783 de 30.000 bytes) |
| Suíte do projeto | 846 testes, com uma falha pré-existente de outra etapa |
