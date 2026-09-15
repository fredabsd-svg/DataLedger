# Como criar um papel novo na equipe de agentes

Este procedimento existe porque o Fred pediu explicitamente que outras
ferramentas de IA, além do Claude Code, também possam criar papéis para a
equipe do DataLedger — não só usar os que já existem (DL-019).

A equipe tem **uma fonte editável**: [`docs/agents/papeis/`](papeis/). Os
arquivos em [`.claude/agents/`](../../.claude/agents/) e
[`.codex/agents/`](../../.codex/agents/) são **gerados** por
[`scripts/gerar_agentes.py`](../../scripts/gerar_agentes.py) e nunca devem ser
editados à mão: a próxima geração sobrescreve qualquer edição direta, e o
teste de sincronia reprova o build se algum deles divergir da fonte.

## Passo a passo

1. **Crie o arquivo da fonte** em `docs/agents/papeis/<nome-do-papel>.md`,
   usando um papel existente como modelo de estrutura. O frontmatter tem dois
   blocos:

   - `perfil:` — o que o papel é e pode fazer, em termos neutros de
     ferramenta: `raciocinio` (`maximo` ou `equilibrado`), `esforco` (`alto`
     ou `medio`), `escreve_arquivos` (`sim`/`nao`), `memoria_de_projeto`
     (`sim`/`nao`) e `delega_para` (lista de nomes de papéis, vazia se o papel
     não delega).
   - `claude:` — os valores literais específicos do Claude Code hoje:
     `model`, `effort`, `memory` (só quando o papel tiver memória de projeto),
     `color`, `tools` e `disallowedTools` (quando aplicável).

   O corpo do arquivo (depois do frontmatter) é o texto em português que
   descreve o papel: responsabilidades, limites, regras do domínio que se
   aplicam, delegação e formato de retorno. Links relativos devem apontar para
   os documentos a partir de `docs/agents/papeis/` — o gerador recalcula esses
   links para cada formato de saída, você não precisa (e não deve) escrever
   um link diferente por formato.

2. **Rode o gerador em modo escrita**:

   ```bash
   .venv/bin/python scripts/gerar_agentes.py --escrever
   ```

   Isso produz `.claude/agents/<nome-do-papel>.md` e
   `.codex/agents/<nome-do-papel>.toml`. Se o frontmatter tiver um erro de
   estrutura, o gerador falha com uma mensagem que aponta o arquivo e a linha
   — e não grava nada, nem para os outros papéis.

3. **Rode o teste de sincronia**:

   ```bash
   .venv/bin/python -m pytest apps/core/tests/test_agentes_multiplataforma.py
   ```

   Ele confere que os dois formatos existem para todo papel da fonte, que
   nenhum deles diverge do que o gerador produziria agora, e que não sobrou
   derivado órfão. O mesmo comando roda como `--verificar`, sem gravar nada:

   ```bash
   .venv/bin/python scripts/gerar_agentes.py --verificar
   ```

4. **Peça ao `arquiteto-senior` para atualizar
   [`docs/agents/equipe.md`](equipe.md)** com o papel novo: quem pode acionar
   quem, e a linha da tabela de composição. **Não edite `equipe.md` você
   mesmo** — esse arquivo é mantido pelo arquiteto, que registra ali a
   arquitetura da equipe como um todo; um papel criado por fora dele ficaria
   descrito em dois lugares (o defeito que o projeto já corrigiu uma vez, ver
   [`CLAUDE.md`](../../CLAUDE.md), seção "Estado do projeto: um lugar só").

5. Se o papel for descartável (um experimento, uma prova de conceito), remova
   o arquivo da fonte e rode o gerador de novo para que os derivados
   desapareçam junto — não deixe `.claude/agents/` ou `.codex/agents/` com um
   papel que não existe mais na fonte. O teste de sincronia detecta esse
   resíduo (é o que o projeto chama de "derivado órfão") e reprova o build até
   ele ser removido.

## O que isto não faz

Este procedimento cria a **definição** do papel — o que ele é e pode fazer.
Não cria acesso a ferramentas que a plataforma ainda não concede, não muda
permissão de execução do Codex nem do Claude Code, e não substitui a revisão
do `arquiteto-senior` sobre se o papel novo faz sentido na equipe.
