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

   **Toda afirmação sobre o que a ferramenta impede vai dentro de um bloco
   `{{MECANISMO}}`.** É a regra mais importante deste documento, e a que uma
   auditoria encontrou quebrada: frases como "você não tem `Write`, essa
   restrição é técnica" são **verdade no Claude Code e mentira no Codex**, que
   lê o mesmo texto e tem a ferramenta. Um papel que promete isolamento
   inexistente é pior que papel nenhum. A sintaxe é exatamente esta, sem
   espaço dentro das chaves, em maiúsculas, com as duas seções e o fechamento:

   ```text
   {{MECANISMO}}
   CLAUDE:
   Você não tem `Write` nem `Edit`. Essa restrição é **técnica**.
   CODEX:
   Você não edita arquivos. Aqui isso é **instrução de comportamento**, não
   isolamento técnico: a ferramenta não impede, você é que não faz.
   {{/MECANISMO}}
   ```

   O gerador escolhe uma das duas versões por destino. Marcador escrito de
   qualquer outra forma **é recusado** com erro apontando arquivo e linha —
   antes ele vazava literal para dentro do arquivo que o modelo lê, ou
   engolia em silêncio o texto entre dois blocos. O mesmo vale para
   **capacidade**, não só restrição: "você tem memória de projeto" é verdade
   num lado e falso no outro, e também precisa do bloco.

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
   o arquivo da fonte e rode o gerador de novo. **Atenção, porque os dois lados
   se comportam de forma diferente de propósito:**

   - `.codex/agents/<papel>.toml` **é apagado sozinho**, porque o gerador
     reconhece a marca que ele mesmo escreveu ali, citando este papel.
   - `.claude/agents/<papel>.md` **não é apagado**: você precisa removê-lo à
     mão. Esse arquivo não tem onde carregar a marca sem quebrar a exigência
     de que os papéis existentes fiquem byte a byte idênticos, e o diretório
     `.claude/agents/` é um lugar onde é legítimo alguém guardar um agente
     pessoal. Apagar sozinho o que não se tem certeza de ter escrito já
     destruiu um arquivo de usuário durante uma auditoria desta etapa.

   O gerador diz, na saída, exatamente o que removeu e o que preservou. Só
   depois de remover o `.md` à mão o `--verificar` fica verde. Enquanto
   sobrar qualquer um dos dois, o teste de sincronia reprova o build — é o que
   o projeto chama de "derivado órfão".

## O que isto não faz

Este procedimento cria a **definição** do papel — o que ele é e pode fazer.
Não cria acesso a ferramentas que a plataforma ainda não concede, não muda
permissão de execução do Codex nem do Claude Code, e não substitui a revisão
do `arquiteto-senior` sobre se o papel novo faz sentido na equipe.
