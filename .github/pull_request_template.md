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

- [ ] Li o AGENTS.md e as instruções das pastas afetadas antes de alterar arquivos.
- [ ] Registrei plano e critérios de aceite.
- [ ] Mantive o escopo da etapa e preservei alterações de terceiros.
- [ ] Comentei regras e decisões relevantes no código, quando aplicável.
- [ ] Executei os testes pertinentes e registrei os resultados.
- [ ] Verifiquei regressões, permissões e isolamento quando afetados.
- [ ] Atualizei a documentação e revisei o diff completo.
- [ ] Atualizei o estado do projeto em `docs/agents/estado.md` e conferi que o `README.md` não contradiz a realidade. O estado mora **num lugar só**; não o duplique.
- [ ] Não incluí segredos, certificados privados ou dados reais de clientes.
- [ ] Commit e envio da branch concluídos.
- [ ] CI aprovada para o commit mais recente.
- [ ] Informei limitações, pendências e dependências.

Itens pendentes não podem ser marcados como aprovados. O PR não substitui revisão autorizada nem autoriza publicação em produção.
