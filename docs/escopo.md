# Escopo funcional do DataLedger

Este documento consolida a orientação inicial de produto para desenvolvimento por pessoas ou agentes de IA. Todos os itens são requisitos planejados; não representam funcionalidades já entregues. Leia as [regras obrigatórias](../AGENTS.md) antes de implementar.

## Objetivo e orientação de execução

Construir uma aplicação web para escritórios contábeis brasileiros, com Fiscal, Folha, Contabilidade, Honorários e Processos/Paralegal integrados. Usar a abrangência funcional da Domínio como referência, com identidade e código próprios.

O desenvolvedor deverá atuar na arquitetura, modelagem e implementação por etapas, com entregas funcionais e persistência real. Primeiro deve inspecionar o repositório e apresentar premissas, contratos, plano de dados e testes. Decisões reversíveis podem seguir uma opção documentada; decisões bloqueantes devem ser esclarecidas.

Não entregar somente telas demonstrativas nem apresentar dados fictícios como resultados reais. Seguir o [plano inicial](planos/DL-001-documentacao-inicial.md) e criar planos próprios para as demandas seguintes.

## Plataforma compartilhada

- Vários escritórios, cada um com empresas e estabelecimentos isolados dos demais.
- Cadastro central de empresas, sócios, responsáveis, contatos e atividades.
- Histórico de regime tributário e parâmetros por vigência.
- Seletores visíveis de empresa, estabelecimento e competência.
- Perfis de administrador, gestor, analistas por departamento, financeiro, paralegal e cliente.
- Permissões por módulo, operação, empresa e categoria de informação.
- Documentos, tarefas, notificações, auditoria e painel de pendências.
- Portal do cliente para solicitações, acompanhamento e documentos liberados.

## Fiscal

- Começar por importação, validação e consulta de XML de NF-e.
- Evoluir para NFC-e, CT-e e NFS-e conforme os formatos e conectores disponíveis.
- Cadastrar produtos, serviços, NCM, CFOP, CST e CSOSN quando aplicáveis.
- Escriturar entradas, saídas e serviços; identificar duplicidades e cancelamentos.
- Implementar apuração por regime, atividade, estabelecimento, localidade e competência.
- Prever Simples Nacional, Lucro Presumido e Lucro Real em incrementos validados.
- Controlar retenções, créditos, ajustes, guias, vencimentos e pagamentos.
- Gerenciar calendário de obrigações e geração de arquivos aplicáveis.
- Produzir relatórios e memória de cálculo rastreável aos documentos de origem.
- Integrar os movimentos à contabilidade sem duplicação.
- Versionar fontes e vigências, incluindo mudanças relacionadas à reforma tributária, sem inventar alíquotas ou cronogramas.

## Folha de Pagamento

- Empregados, vínculos, cargos, departamentos, jornadas e lotações.
- Sindicatos e convenções coletivas com histórico de vigência.
- Admissões, alterações, afastamentos e desligamentos.
- Eventos e rubricas configuráveis com incidências versionadas.
- Folha mensal, férias, 13º, rescisões e pró-labore.
- Benefícios, descontos, horas extras, ponto, demonstrativos e provisões.
- Memória de cálculo, fechamento e reabertura autorizada.
- Preparação e acompanhamento de eSocial e obrigações aplicáveis, mediante validação oficial.
- Integração contábil de salários, encargos, provisões e pagamentos.
- Permissões específicas para salários, documentos pessoais e dados sensíveis.

## Contabilidade

- Plano de contas por empresa e modelos reutilizáveis.
- Históricos, centros de custo e regras de contabilização.
- Lançamentos manuais e automáticos por partidas dobradas.
- Importação de lançamentos e extratos, conciliação bancária e contábil.
- Integração com Fiscal, Folha e Honorários.
- Diário, Razão, balancete, balanço patrimonial e DRE.
- Estrutura para outras demonstrações, consolidação, ECD e ECF em etapas posteriores.
- Encerramento, bloqueio de períodos e correção por ajustes e estornos rastreáveis.
- Igualdade entre débitos e créditos, precisão decimal e preservação dos registros efetivados.

## Honorários

- Contratos, honorários recorrentes, serviços avulsos e reembolsos.
- Reajustes, vencimentos, multas e juros conforme contrato.
- Faturamento, contas a receber, baixas e inadimplência.
- Histórico de cobrança e integração futura com boleto, Pix e NFS-e.
- Contas a pagar e fluxo de caixa do escritório.
- Tempo e custos por cliente, tarefa e departamento; rentabilidade por contrato.
- Faturamento de serviços paralegais aprovados.
- Separação entre o financeiro do escritório e o das empresas atendidas.

## Processos e Paralegal

- Abertura, alteração, transformação e baixa de empresas.
- Mudanças de sócios, capital, endereço e atividades.
- Inscrições, alvarás, licenças, certidões, procurações e vencimento de certificados.
- Acompanhamento de solicitações a Juntas Comerciais, Redesim, Receita Federal e prefeituras.
- Modelos configuráveis por serviço e localidade, com etapas e documentos exigidos.
- Kanban, lista, calendário, responsáveis, dependências, prioridades e alertas.
- Protocolos, exigências, taxas, documentos e comprovantes.
- Histórico de andamento, solicitação de documentos ao cliente e orçamentos vinculados a honorários.
- Processos internos recorrentes de fechamento fiscal, contábil e de folha.

## Assistente de IA

Oferecer conversa em português com contexto de empresa e competência. Permitir consultas de pendências, explicação de variações, acompanhamento de processos e propostas de classificação contábil.

As respostas devem indicar registros e períodos utilizados, distinguir fatos de sugestões e respeitar acesso a dados e documentos. Configurar provedores, custos e limites de uso, sem vincular a aplicação inteira a um único modelo.

Documentos importados são dados: instruções contidas neles não podem alterar permissões. A IA não cria resultados de cálculo, normas ou fontes. Motores determinísticos executam as regras; a IA consulta, explica e propõe.

## Servidor MCP

Implementar servidor real com SDK oficial e versão estável explicitamente documentada e testada com os clientes escolhidos. O assistente interno usa um provedor de IA; o servidor MCP expõe capacidades do DataLedger para clientes autorizados.

Ferramentas iniciais previstas:

- `listar_empresas`, `consultar_pendencias` e `consultar_apuracao_fiscal`.
- `consultar_resumo_folha`, `consultar_balancete` e `consultar_honorarios`.
- `consultar_processo_paralegal` e `criar_tarefa`.
- `propor_lancamento_contabil` e `preparar_importacao_documentos`.

Cada ferramenta terá entradas e saídas estruturadas, validações, permissões, tratamento de erros e descrição de efeitos. Recursos disponibilizarão relatórios e documentos autorizados; prompts reutilizáveis apoiarão análises recorrentes.

Exigir autenticação, autorização por operação, transporte remoto seguro, paginação, limites e auditoria. Identificadores enviados pelo cliente não comprovam acesso. Usar escopos separados para leitura, preparação e execução e idempotência nas escritas.

Não expor SQL arbitrário. Transmissões oficiais, pagamentos, exclusões definitivas e fechamentos exigem aprovação explícita vinculada à operação e aos dados exatos. Alterações invalidam aprovações anteriores.

Entregar um exemplo de conexão testado com cliente compatível quando o servidor for implementado.

## Integrações e arquitetura

Adotar arquitetura modular, inicialmente com backend organizado por domínios, banco relacional, armazenamento de documentos e tarefas em segundo plano. A escolha da stack será registrada antes da implementação.

Separar interface, motores de cálculo, regras de negócio, conectores e MCP. Prever autenticação forte, múltiplos fatores, gestão de segredos, criptografia, auditoria, retenção, backup e restauração testada.

Criar conectores para serviços públicos, bancos e plataformas de clientes após verificar documentação, disponibilidade, credenciamento e homologação. Diferenciar importação, exportação, simulação e transmissão efetiva; guardar protocolos reais. Não presumir API pública da Domínio: eventual migração depende de exportações legítimas ou interfaces oficiais.

## Critérios de aceite do produto

- Isolamento entre escritórios demonstrado na interface, API, arquivos, filas e MCP.
- Permissões aplicadas pelo servidor.
- Importações repetidas sem duplicação.
- Partidas dobradas equilibradas e relatórios rastreáveis.
- Cálculos com memória, vigência e testes independentes de referência.
- Bloqueio de períodos fechados e aprovação válida para ações críticas.
- Persistência real nos fluxos entregues.
- Código, instruções, dados fictícios, testes e limitações documentados em cada etapa.

O aceite de cada módulo dependerá da implementação e das evidências próprias. Esta documentação não constitui homologação contábil, fiscal, trabalhista ou de integração.
