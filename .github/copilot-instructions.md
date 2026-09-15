# Instruções para assistentes de IA neste repositório

Este arquivo existe para ferramentas que leem `.github/copilot-instructions.md`
(GitHub Copilot e compatíveis). As regras do projeto **não** moram aqui.

**Antes de alterar qualquer arquivo, leia integralmente [`AGENTS.md`](../AGENTS.md)**
na raiz do repositório. Ele é a regra obrigatória de desenvolvimento, testes,
Git e pull request, e prevalece sobre qualquer instrução deste arquivo.

Depois, leia [`docs/agents/estado.md`](../docs/agents/estado.md), que é a
fonte única do estado do projeto: o que está pronto, o que é o próximo passo e
o que depende de decisão do responsável pelo produto.

Resumo do que é imposto tecnicamente, e não só pedido:

- Pull request sem a caixa "Li o AGENTS.md" marcada e sem plano `DL-xxx` citado
  **reprova** na integração contínua.
- Etapa com plano em `docs/planos/` que não apareça no README e em
  `docs/agents/estado.md` **reprova** na integração contínua.
- A branch `main` só recebe alteração por pull request com as verificações
  verdes.

Ferramentas que leem `AGENTS.md` nativamente já encontram as regras sem este
arquivo. Levantamento em documentação oficial, de 2026-09-15
([DL-019](../docs/planos/DL-019-portabilidade-entre-ferramentas-de-ia.md)):
Cursor, Codex, Google Jules, OpenCode, Zed, Roo Code, Cline e Kiro leem.

**Correção de uma afirmação desta página:** até 2026-09-15 este arquivo
afirmava que o **Gemini CLI** lê `AGENTS.md` nativamente. **Não lê** — ele usa
`GEMINI.md`, e só lê `AGENTS.md` com a chave `context.fileName` configurada
fora do repositório. A afirmação vinha da DL-014, sem fonte, e a pesquisa da
DL-019 a desmentiu.
