# DL-001 — Documentação inicial

## Objetivo e diagnóstico

Organizar a documentação de entrada do DataLedger e publicar as regras acordadas. Na inspeção inicial, a branch `main` continha somente um README de duas linhas, sem aplicação, testes, workflows ou proteção de branch ativada.

Esta demanda é uma etapa documental única, reunindo diagnóstico, implementação dos documentos e validação. O desdobramento reduzido segue a adaptação para demandas pequenas prevista no [AGENTS.md](../../AGENTS.md).

## Etapa e entregáveis

- Estado deste registro: `em validação`. O resultado posterior de publicação e CI deve constar no PR, associado ao commit testado.
- Branch proposta: `docs/dl-001-documentacao-inicial`.
- Destino: `main`.
- Entregáveis: README, AGENTS.md, escopo funcional, este plano, modelo de PR, verificador documental e workflow.
- Dependências: acesso de escrita ao repositório e GitHub Actions habilitado para a execução remota.
- Fora do escopo: código dos módulos, definição final da stack, migrações, transmissão oficial e deploy.

## Critérios de aceite

- README identifica o projeto, cinco módulos, IA e MCP e o estado ainda não implementado.
- Regras de desenvolvimento estão na raiz, com testes, comentários e fluxo de commit, push e PR por etapa.
- Escopo contempla os requisitos funcionais acordados.
- Links relativos apontam para arquivos existentes.
- Documentação usa UTF-8, possui títulos e não contém espaços finais indevidos.
- Verificador passa nos arquivos reais e rejeita uma referência relativa inexistente em uma cópia de teste.
- Alterações são publicadas em branch própria e PR, sem modificar diretamente a main.
- CI documental é conferida no commit publicado; uma execução ausente ou falha não pode ser registrada como aprovada.

## Validação reproduzível

Executar na raiz com PowerShell 7 ou superior:

```sh
pwsh -NoProfile -File scripts/validate-docs.ps1
```

Para testar o cenário de falha, usar uma cópia descartável dos documentos e acrescentar um link relativo para um arquivo inexistente no README. Executar o script com `-Root` apontando para essa cópia e confirmar que ele falha. O script original deve continuar passando sem alteração.

Revisar o diff completo e conferir o conteúdo remoto após o envio. A primeira entrega não possui testes de aplicação porque nenhum módulo está implementado. A verificação documental não certifica conteúdo jurídico nem substitui futuros testes de cálculo e integração.

Validação local executada em 11/09/2026, com PowerShell no Windows: cinco arquivos Markdown aprovados; cenário negativo com link inexistente rejeitado conforme esperado. O resultado de CI será registrado no PR após a publicação.

## Riscos, reversão e próximos passos

Não há migrações, dados operacionais ou alteração de comportamento da aplicação. O risco principal é apresentar requisitos planejados como funcionalidades prontas; os documentos identificam explicitamente esse limite.

Reversão: fechar o PR antes do merge ou, após integração, propor um commit de reversão em novo PR. Preservar o histórico.

A etapa seguinte deve definir arquitetura, modelo de dados e contratos, detalhar os testes por componente e configurar a proteção da main com revisão e verificações obrigatórias. Este PR adiciona verificação documental, mas não ativa proteção de branch, detecção especializada de segredos ou testes de aplicação.

Hash do commit, link do PR, resultados de validação e estado da CI serão registrados na descrição do PR e no relatório de entrega; não inserir identificadores fictícios neste documento.
