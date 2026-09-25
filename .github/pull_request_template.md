# Pull request

## Problema e resultado

Descreva o problema e o comportamento resultante da alteração.

## Demanda e etapa

Informe o identificador, o caminho do plano, o escopo desta etapa e as dependências de outros PRs.

## Critérios de aceite e validação

Liste critérios atendidos, testes executados, comandos, ambiente e resultados. Diferencie validação manual, teste automatizado e homologação externa. Informe o commit validado e a execução de CI correspondente.

## Riscos e operação

Explique impacto em permissões, dados, regras de cálculo, contratos e desempenho. Documente migrações e reversão quando aplicáveis. Justifique itens não aplicáveis.

## Checklist

⚠️ **O checklist completo é o do [AGENTS.md §14](../AGENTS.md#14-checklist-de-conclusão-de-cada-etapa) — 30 itens, com a coluna de quem impõe cada um. Percorra-o lá.** Este bloco tem **só** as caixas que a integração contínua lê, e por isso não pode ser reescrito sem ajustar o workflow `Regras do projeto`. **Repetir a lista aqui foi a duplicação que este projeto já pagou duas vezes.**

- [ ] Li o AGENTS.md e as instruções das pastas afetadas antes de alterar arquivos.
- [ ] Percorri o checklist do AGENTS.md §14 inteiro, item por item, e não marquei nada que não conferi.
- [ ] Atualizei o estado do projeto em `docs/agents/estado.md` e conferi que o `README.md` não contradiz a realidade. O estado mora **num lugar só**; não o duplique.
- [ ] Conferi o checklist de etapas do README contra a branch padrão: marca `[x]` só para o que já está lá, `[ ]` só para o que não está.
- [ ] Informei limitações, pendências e o que **não** foi medido, classificando cada item como Implementado, Inspecionado, Testado, Não testado, Bloqueado ou Fora do escopo.

⚠️ **Item pendente não pode ser marcado como aprovado, e marcar o que não foi conferido é PIOR que deixar em branco** — o checklist passa a ser prova falsa. Foi assim que a divergência do README sobreviveu a vários PRs marcados como completos (AGENTS.md §14.5, item 26).

O PR não substitui revisão autorizada nem autoriza publicação em produção.
