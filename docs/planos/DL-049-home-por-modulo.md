# DL-049 — Página inicial de trabalho por módulo

**Demanda:** Fred, 29/09/2026: aplicar o prompt revisado de Home por módulo,
usar Prototype, Emil Design Engineering, Pick UI Library, Review Animations
e Mobile Native, revisar, commitar, enviar ao GitHub e mesclar. A ordem
posterior autoriza escolha autônoma da variante e execução sem novas perguntas.
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `feat/dl-049-home-modulos` → `main`.
**Risco:** nível 2, interface de consulta; a agregação e o isolamento recebem
revisão independente. Nenhuma alteração de cálculo, migração ou transmissão.

## Escopo e etapas

1. Comparar três variantes isoladas da fila, com o mesmo contexto: Compacta
   (lista por urgência), Etapas (sequência de conferência) e Carteira (empresa
   primeiro). Escolher por legibilidade operacional, estabilidade e densidade;
   registrar a decisão e remover a superfície experimental da entrega.
2. Implementar um contrato comum de home e lista filtrada, com empresa,
   seleção de empresas e competência persistentes. Contábil, recepção Fiscal e
   Livro-caixa usam dados reais; Financeiro, Folha, Vendas e Estoque explicam
   indisponibilidade sem números ou atalhos fictícios.
3. Validar navegação, estados, consultas, permissões, visual e movimento;
   revisar independentemente; publicar commit/PR, conferir CI e mesclar.

## Critérios de aceite e testes

- Até quatro indicadores com unidade, eixo temporal, status e destino
  filtrado. Zero significa apuração conhecida; indisponibilidade usa “—”.
- Empresa e competência histórica sobrevivem à troca de módulo e retorno;
  IDs são revalidados no escritório ativo. Grupo é seleção, não consolidação.
- Carteira com empresas abertas/fechadas mantém estado individual. Competência
  ausente não vira aberta; competência entregue não oferece reabertura.
- RC-58 reaproveita o detector de lançamentos desbalanceados, inclusive fora
  do mês. A consulta da home não cria competência nem executa fechamento.
- Fiscal diferencia data de recepção e competência do documento; recusas sem
  identificação não são atribuídas à empresa. Ocorrência histórica não vira
  pendência resolvida sem persistência de tratamento.
- Livros-caixa não recebem ações de fechamento ou demonstrações por partidas
  dobradas. A leitura recusa papéis não autorizados, sem nomes/contagens/R$.
- Fila inicial limitada, lista completa paginada e consultas sem crescimento
  por empresa. Testar dois escritórios, IDs adulterados, filtros inválidos,
  recusa de permissão, configuração incompleta e competência fechada/mista.
- Visual em 1.440 × 900, 1.280 px e 390 × 844: foco visível, teclado, ausência
  de rolagem horizontal da página e área de toque adequada. Manter zoom.
- Navegação e filtros sem animação; movimento pontual justificado, curto e
  reduzido conforme preferência. Registrar inspeção por Before/After/Why.
- Executar testes de comportamento, regressões pertinentes, suíte PostgreSQL,
  ruff, checks Django, migrações e documentação. Hardware móvel indisponível
  permanece limitação explícita; emulação não é validação em telefone real.

## Implementação e decisões

Templates Django, tokens existentes, CSS e controles nativos permanecem.
As bibliotecas React da lista Pick UI Library não se aplicam à stack atual;
não introduzir framework ou dependência apenas para implementar a home.
Os oito estados do prompt se aplicam às capacidades reais: certificado,
integração bancária e processamento de Folha não são simulados em produção.
Não alterar a landing, relatórios emitidos ou regras monetárias.

## Operação, reversão e evidências

Sem migração nem dados de cliente. Reversão por commit de reversão do PR;
as rotas e ações anteriores continuam disponíveis. Filtros ficam na sessão
por escritório e na URL; leitura não grava dados de negócio.
Evidências executadas, decisão de variante e relatório independente serão
registrados junto à entrega. Não declarar testes, CI ou merge concluídos
antes de conferir seus resultados.
