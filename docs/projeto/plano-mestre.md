# Plano mestre de evolução por módulos

**Este arquivo tem duas partes, e elas não se misturam.**

1. O **documento que o Fred entregou em 2026-09-16**, reproduzido **sem uma
   única edição**. Começa no `# DataLedger` logo abaixo e termina em
   "Referências complementares".
2. As **notas do `arquiteto-senior`**, no fim do arquivo, escritas *depois* do
   texto dele e *sem* tocar nele: o que eu verifiquei uma a uma, o que confirmei,
   **o que ele corrigiu de mim** e as ressalvas.

É a mesma regra que este projeto aplica a relatório de auditoria: **texto de
terceiro se preserva integralmente; comentário vem depois, nunca por cima.**

Três avisos de leitura, antes de começar:

- O estado do projeto continua morando num lugar só,
  [docs/agents/estado.md](../agents/estado.md). Este plano é **mapa de
  decomposição, não segunda fonte de estado** — a regra está escrita na
  [DE-041](decisoes.md).
- Os códigos `ORG`, `BAS`, `CON`, `FIS`, `FOL`, `OBR`, `HON`, `PAR`, `POR`,
  `IA`, `MCP` e `OPS` são **deste mapa**. Eles não substituem nem renumeram
  `DL`, `BL`, `RC` e `DE`, que continuam sendo os identificadores de trabalho.
- A incorporação deste documento no repositório é a etapa
  [DL-022](../planos/DL-022-plano-mestre-e-reconciliacao.md).

---

# DataLedger

## Plano mestre de evolução por módulos

**Diagnóstico e proposta para revisão de Fred | 16 de setembro de 2026**

**Base analisada:** `main`, commit `b8c66a60ae11f2877c1f0317608c7bf1ed52bfec`, após o PR #22. Este documento é uma fotografia dessa revisão e uma proposta de execução. Não altera requisitos aprovados nem representa autorização de implantação.

**Direção escolhida por Fred nesta conversa:** corrigir os bloqueadores e intercalar Contabilidade com recepção e conferência de NFS-e para entregar utilidade mais cedo. O envio ao GitHub fica para depois da revisão deste plano.

### Leitura recomendada

Comece pelo diagnóstico e pela sequência de entregas. Em seguida, consulte as etapas de cada módulo. Os códigos ORG, BAS, CON, FIS, FOL, OBR, HON, PAR, POR, IA, MCP e OPS são referências deste planejamento; não substituem os identificadores DL, BL, RC e DE existentes.

## 1. Diagnóstico: onde o projeto está

**O DataLedger está na fase de fundação funcional com contabilidade básica utilizável.** Já há código de negócio, persistência, interface e testes. Ainda falta completar o ciclo operacional e tratar riscos que impedem considerá-lo pronto para dados reais de clientes. A recomendação é aproveitar a arquitetura atual e organizar a evolução em entregas pequenas e completas.

O projeto usa Django, Django REST Framework, PostgreSQL e templates no servidor, com CSS próprio. Não há evidência que justifique reescrever a aplicação ou trocar a stack para executar este plano. A implantação em nuvem, acesso pelo navegador e alvo de aproximadamente 50 usuários simultâneos já estão registrados como decisões do produto.

| Área | Estado encontrado no código | Principal trabalho restante |
| --- | --- | --- |
| Autenticação e escritórios | Usuários, login/logout, vínculos por escritório e papéis | Primeiro acesso, gestão de equipe e permissões por empresa e departamento |
| Cadastro central | Empresas, estabelecimentos, CNPJ alfanumérico e histórico de regime | Sócios, responsáveis, contatos, atividades, inscrições e manutenção completa pela interface |
| Contabilidade | Plano hierárquico, lançamentos, estornos, Diário, Razão, Balancete e conferência | Fechamento, abertura de saldos guiada, origem, conciliação, centros de custo, demonstrações e obrigações |
| Auditoria | Registros por ator, escritório e objeto; consulta restrita | Atomicidade, cobertura de alterações e proteção contra exclusão |
| Fiscal | Plano DL-010 e levantamento de documentos | Aplicação ainda não implementada |
| Folha | Escopo funcional registrado | Aplicação ainda não implementada |
| Honorários e financeiro do escritório | Escopo funcional registrado | Aplicação ainda não implementada |
| Processos/Paralegal | Escopo funcional registrado | Aplicação ainda não implementada |
| Portal, documentos e tarefas compartilhadas | Capacidades previstas no escopo | Fluxos e componentes ainda precisam ser construídos |
| Assistente de IA e MCP | Requisitos e limites registrados | Serviços e integrações ainda não implementados |

Os seis aplicativos de domínio/base registrados atualmente são `core`, `accounts`, `tenancy`, `empresas`, `auditoria` e `contabilidade`. Ter um papel chamado financeiro ou paralegal não significa que o módulo correspondente exista.

**Por que é difícil acompanhar:** o estado operacional se mistura com histórico de sessões, configuração de agentes e auditorias. O README duplica a DL-020 com marcações diferentes. A DL-021 já foi integrada, mas seu plano e o estado ainda a descrevem como não iniciada. Mapas funcionais guardam fotografias antigas e algumas perguntas resolvidas continuam acompanhadas do texto anterior. O problema exige reconciliação de informações, preservando o histórico.

Fontes: [configuração dos aplicativos](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/config/settings.py), [modelos contábeis](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/apps/contabilidade/models.py), [escopo](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/escopo.md) e [requisitos](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/requisitos.md).

## 2. Evidências e limites da revisão

A análise combinou leitura do código, modelos, serviços, rotas, interface e configuração; confronto dos planos com requisitos e backlog; histórico remoto; e revisão independente de código e documentação. Os achados administrativos abaixo foram confirmados por inspeção estática e já possuem reproduções históricas no projeto. Não foram repetidos aqui contra uma instalação com dados de clientes.

| Verificação | Resultado e alcance |
| --- | --- |
| GitHub Actions do commit analisado | Backend e Documentação com sucesso |
| Log do Backend no PostgreSQL 16, Python 3.14 | **1.200 testes aprovados e 2 pulados**; os dois pulados exigem navegador funcional para medir CSS |
| Lint e formatação locais | Aprovados; 156 arquivos conferidos pela formatação |
| Verificação local do Django | Sem problemas identificados |
| Verificação de migrações pendentes | Nenhuma alteração de modelos sem migração detectada |
| Gerador de papéis, neste Linux | 7 papéis, derivados sincronizados |
| Reprodução local com Python 3.12 e SQLite | Suíte integral não concluída: apresentou falhas e foi interrompida. Execução dirigida reproduziu 1 falha e 40 aprovações até parar |
| Proteção remota da main | Consulta retornou `protected: false`; lista de rulesets vazia. A proteção declarada nos documentos não está comprovada como ativa |

A falha local dirigida foi a criação de conta com código repetido: no SQLite, a violação de unicidade escapou como erro de integridade, em vez de retornar o erro de validação esperado. A tradução atual de restrições usa diagnóstico do PostgreSQL. Isso evidencia uma diferença entre o ambiente SQLite oferecido no README e o ambiente oficial da CI; não demonstra falha equivalente no PostgreSQL. Recomendo padronizar desenvolvimento, homologação e testes críticos em PostgreSQL e decidir expressamente o alcance do suporte a SQLite.

**Não foi feita homologação fiscal/trabalhista, teste completo de produção, ensaio de carga ou restauração de backup.** Não há base para informar um percentual global de conclusão. A quantidade de testes não mede quantos módulos do produto estão prontos.

Fontes: [execução Backend](https://github.com/fredabsd-svg/DataLedger/actions/runs/35038116862), [execução Documentação](https://github.com/fredabsd-svg/DataLedger/actions/runs/35038116864), [workflow](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/.github/workflows/backend.yml) e [tradução de restrições](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/apps/core/restricoes.py).

## 3. O que precisa ser corrigido primeiro

Estes itens formam a entrega inicial de estabilização. A gravidade considera uso real; uma etapa anterior ter sido integrada não elimina uma pendência de implantação registrada separadamente.

| Referência | Risco ou lacuna | Entrega e critério de conclusão |
| --- | --- | --- |
| BL-83 | Conta movimentada pode mudar de empresa ou natureza pelo admin | Bloquear transições indevidas no domínio e no admin; requisições autenticadas devem ser recusadas sem mudar conta, Diário ou Balancete |
| BL-211/A3 | Uma empresa inteira pode mudar de escritório pelo admin | Impedir transferência cotidiana; provar que escrituração e visibilidade continuam no escritório original |
| BL-211/A2 | Histórico tributário admite sobreposição e mais de um período aberto | Invariantes no banco/domínio, fluxo único e concorrência testada; API e admin não deixam regimes incompatíveis |
| BL-14, BL-16 e BL-57 | Auditoria fora da transação, exclusão do log e alterações cadastrais sem trilha | Operação e auditoria atômicas; falha induzida reverte ambas; exclusão administrativa recusada e alterações relevantes registradas |
| DL-016 | Não existe fechamento formal de competência | Bloquear gravações no período fechado, controlar reabertura e provar concorrência entre fechamento e lançamento |
| DL-018 / BL-125 | Instalação nova depende do admin para começar | Fluxo pelo produto até a primeira empresa e o primeiro lançamento |
| BL-02 | main consultada sem proteção ativa | Configurar e comprovar PR obrigatório e verificações; tratar revisão conforme a realidade do mantenedor, sem afirmar controles inexistentes |
| BL-86 e BL-76 | Consistência concorrente e escala dos relatórios | Totais conciliáveis no mesmo retrato dos dados; paginação sem alterar totais do período |

**Precisão dos achados:** o admin de lançamentos já bloqueia inclusão, alteração e exclusão. Não há fundamento para repetir o falso positivo antigo de lançamento arbitrário por essa tela. O histórico de regime também tem ordenação implícita por início; o risco confirmado é sobreposição e falta de desempate para inícios iguais, não ausência completa de ordenação.

A DL-021 corrigiu a escrita com quebras de linha no gerador. O próprio plano registra uma pendência distinta de permissões no Windows. Deve constar como correção integrada com limitação remanescente, e não como trabalho inexistente ou compatibilidade Windows integralmente comprovada.

Fontes: [backlog](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/backlog.md), [admin contábil](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/apps/contabilidade/admin.py), [admin de empresas](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/apps/empresas/admin.py), [admin de auditoria](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/apps/auditoria/admin.py) e [DL-021](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/planos/DL-021-robustez-do-gerador-no-windows.md).

## 4. Sequência de entregas aprovada como direção

Os marcos abaixo organizam o projeto inteiro. A ordem interna de cada módulo aparece nas seções seguintes. Não é necessário concluir todos os módulos para liberar um piloto delimitado; cada marco precisa satisfazer seus próprios critérios operacionais.

| Marco | Trabalho principal | Resultado observável |
| --- | --- | --- |
| M0 - Estado confiável | Reconciliar documentação, fixar prioridades e corrigir bloqueadores de isolamento/auditoria | Uma lista atual de entregas e uma base segura para continuar |
| M1 - Entrada e recepção | Primeiro acesso e cadastros mínimos; NFS-e XML/ZIP em área de conferência | Operador recebe documentos, vê duplicidades e erros, sem contabilização automática prematura |
| M2 - Núcleo contábil protegido | Fechamento/reabertura, origem, saldos iniciais; ampliar conferência da NFS-e | Competência protegida e documentos prontos para escrituração |
| M3 - Primeiro ciclo integrado | Classificação fiscal, prévia e integração contábil; Balanço e DRE básicos; primeiro perfil de apuração | Documento rastreável até lançamento, relatório e apuração conferida |
| M4 - Operação recorrente | Conciliação, centros de custo, correções/regeração, livros; NF-e e SPED conforme amostras | Um fechamento mensal repetível e comparável ao sistema atual |
| M5 - Folha inicial completa | Cadastros, cálculo, eventos da rotina escolhida, encargos, eSocial e integração | Uma competência de folha validada, com recibos e contabilização |
| M6 - Gestão do escritório | Honorários, processos, documentos, tarefas e portal | Cobrança e acompanhamento operacional conectados à carteira |
| M7 - Fechamento anual e expansão | Demonstrações ampliadas, ECD, ECF/Lalur/Lacs, regimes e segmentos adicionais | Ciclos anuais e obrigações validados para perfis definidos |
| M8 - Assistência e integrações avançadas | IA, MCP e conectores adicionais | Consulta assistida e operações controladas sobre módulos existentes |

**Como intercalar na prática:** enquanto a Contabilidade recebe fechamento e rastreabilidade, a frente Fiscal constrói a recepção em área intermediária. Essa recepção pode existir antes da integração contábil porque não altera a escrituração. A contabilização automática só é liberada após fechar as dependências CON-01, CON-02, CON-04 e CON-08.

Honorários e Paralegal podem avançar após cadastros, permissões e documentos, quando houver capacidade de execução. A preparação da ECD e da ECF começa no desenho das contas e das origens; os validadores e a homologação entram quando os dados estiverem maduros. Se um calendário real da carteira exigir obrigação antes de M6, reordenar esse marco sem saltar dependências.

**Primeiro piloto recomendado:** uma carteira pequena de prestadores de serviços, com municípios e regime definidos por Fred, importação das NFS-e recebidas da ferramenta já usada e comparação de uma competência com o sistema atual. É proposta de recorte; não presume quais clientes ou regime compõem o piloto.

## 5. Organização e plataforma compartilhada

### Organização do trabalho

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| ORG-01 - Reconciliação | Atualizar estado de DL-020/021, duplicidades, perguntas resolvidas e dependências antigas | Nenhuma mesma etapa aparece simultaneamente como não iniciada e integrada |
| ORG-02 - Visão de produto | Quadro por módulo: existente, próximo incremento, bloqueio e evidência | Fred identifica em uma tela o que está sendo feito e o próximo resultado |
| ORG-03 - Backlog executável | Relacionar cada incremento aos BL/RC/DE existentes, com dono e aceite | Pendência tem destino; histórico permanece preservado e consultável |
| ORG-04 - Controle de mudanças | PR por incremento coerente, CI e revisão proporcional ao risco | Entrega tem código/documento, evidência e status verificáveis |

Proposta de organização futura: manter `docs/agents/estado.md` como fonte de estado até uma migração explícita; o plano mestre descreve sequência e critérios, sem virar um segundo status diário. Relatos antigos podem ser movidos para histórico com links, sem reescrever relatórios de auditoria.

### Cadastros, acesso e serviços comuns

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| BAS-01 - Limites de acesso | Matriz por escritório, empresa, módulo, ação e informação sensível | Usuário de um cliente não acessa outros por tela, API, arquivo ou tarefa |
| BAS-02 - Primeiro acesso | Escritório inicial, administrador, empresa e orientação de próximos passos | Instalação limpa chega ao primeiro lançamento sem admin técnico |
| BAS-03 - Equipe | Inclusão, desativação, recuperação de acesso e permissões | Desativação revoga acesso e mantém autoria histórica |
| BAS-04 - Cadastro completo | Sócios, responsáveis, contatos, CNAEs, inscrições, matriz/filiais e históricos | Dados reaproveitados pelos módulos, sem cadastros concorrentes |
| BAS-05 - Regime e vigências | Corrigir sobreposição e integrar mudanças ao cálculo por competência | Uma competência resolve regime inequívoco; mudança não altera resultado histórico silenciosamente |
| BAS-06 - Contexto de trabalho | Empresa, estabelecimento e período visíveis e validados no servidor | Troca de contexto não transporta formulário, arquivo ou resultado indevido |
| BAS-07 - Documentos e filas | Arquivos privados, classificação, processamento, progresso e recuperação | Falha/reinício não perde arquivo nem duplica processamento |
| BAS-08 - Tarefas e calendário | Responsáveis, pendências, vencimentos, notificações e checklists | Toda pendência tem origem, dono, prazo e condição de encerramento |

Dependências: BAS-01 precede portal e dados sensíveis; BAS-02 depende das escolhas de criação de escritórios e equipe ainda abertas na DL-018; BAS-04/05 alimentam Fiscal, Folha e Paralegal. BAS-07 é necessária para importações assíncronas.

## 6. Contabilidade: do núcleo existente ao fechamento completo

**Aproveitar:** plano de contas, partidas dobradas, serviços decimais, estorno, idempotência e relatórios já entregues. As etapas abaixo completam e ampliam essa base.

| Etapa | Trabalho a executar | Evidência de conclusão |
| --- | --- | --- |
| CON-01 - Competência e bloqueio | Executar DL-016: período de trabalho separado de fechamento, reabertura com motivo e responsável | Gravação concorrente com fechamento respeita uma ordem consistente; mês fechado recusa alterações em todas as entradas |
| CON-02 - Origem e documento | Identificar lançamento manual, fiscal, folha, honorários, abertura e encerramento; vincular documento e versão geradora | Navegação documento-lançamento funciona nos dois sentidos e respeita empresa |
| CON-03 - Implantação de saldos | Assistente para o lançamento único dos saldos do balanço anterior, com data e natureza corretas | Totais conciliam com o balanço aprovado, incluindo retificadoras e tratamento explícito do resultado anterior |
| CON-04 - Preparação e efetivação | Rascunho, revisão, conferência e efetivação; proteger o registro efetivado | Rascunho não entra no saldo oficial; repetição da efetivação não duplica |
| CON-05 - Cadastros contábeis | Modelos de plano, sintéticas/analíticas, vigências, históricos e lançamentos padrão; preparar vínculos de demonstrações e plano referencial | Conta inválida ou encerrada não recebe movimento; vínculos ausentes geram pendência |
| CON-06 - Centros de custo | Departamento, centros, percentuais por conta, habilitação por data, proposta e ajuste de rateio | Rateio fecha com a partida; habilitação não muda histórico; relatórios filtram a dimensão |
| CON-07 - Importações | Lançamentos e extratos por formatos contratados, prévia, erros por linha e confirmação | Reimportação não duplica; lote inválido não deixa escrituração parcial inesperada |
| CON-08 - Integração entre módulos | Contrato comum de prévia, regras versionadas, idempotência e pendências; entregar primeiro o adaptador Fiscal | Aceite separado por origem: Fiscal concilia em M3; Folha e Honorários integram depois, sem bloquear o primeiro ciclo |
| CON-09 - Conciliação | Extrato-contabilidade 1:1, 1:N e N:1, diferenças, desfazimento autorizado e conta conciliada até data | Saldo bancário reconcilia; vínculo conciliado protege retroatividade e regeração |
| CON-10 - Correções em massa | Seleção explícita, prévia, campos permitidos, aprovação, versão e trilha | Original é preservado; alteração afeta só o conjunto aprovado e respeita fechamento |
| CON-11 - Regeração de derivados | Reprocessar lançamentos automáticos a partir das notas e regras, em período aberto | Operação atômica e idempotente; notas permanecem; conciliados/ajustados são protegidos |
| CON-12 - Balanço e DRE | Estruturas vinculadas a contas, comparativos, saldos de abertura e conferência | Balanço fecha e DRE concilia com Razão/Balancete; nenhuma conta relevante some silenciosamente |
| CON-13 - Encerramento de resultado | Zeramento das contas de resultado, transferência e abertura do exercício seguinte | Encerramento reproduzível, sem duplicação e com rastreio até o resultado apurado |
| CON-14 - Livros e exportações | Diário/Razão numerados, termos, paginação consistente e exportações | Totais refletem todo o período; numeração e conteúdo não variam por paginação da tela |
| CON-15 - Demonstrações ampliadas | DLPA, DMPL, DFC, DVA, notas e índices, conforme perfil; estruturas e comparativos | Cada demonstração concilia e explicita vínculos, critérios e aplicabilidade |
| CON-16 - Análise e consolidação | Análises vertical/horizontal, orçamento e consolidação, quando demandados | Comparações usam bases equivalentes; consolidação trata eliminações e não mistura escritórios |

**Dependências principais:** CON-01/02 antes de integração e regeração; CON-04 antes de efetivação em lote; CON-03/05 antes de demonstrações; CON-12/13/14 sustentam ECD e ECF. Rascunho não precisa bloquear a implementação do fechamento dos lançamentos já existentes: a dependência antiga deve ser corrigida no planejamento.

**Regras já escolhidas a preservar:** datas de 01/01/2000 até hoje + 30 dias; estorno nunca anterior ao original; teto de 200 partidas com recusa explícita; conta sem pais permitida com aviso/confirmação; saldos apresentados com indicador D/C; implantação por lançamento de saldos; centros de custo opcionais por empresa; livros numerados. Para carga acima do teto, desenhar divisão/importação validada, sem ampliar o limite silenciosamente.

Antes de implementar correções em massa, harmonizar DE-017 com RC-57: distinguir a data do lançamento original e a data do ajuste. O plano não autoriza alterar período fechado nem introduz exclusão genérica de escrituração. A “eliminação” esclarecida por Fred corresponde à regeração de derivados.

Fontes: [DL-016](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/planos/DL-016-competencia-e-fechamento.md), [mapa contábil](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/mapa-funcional-contabil.md) e [decisões](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/decisoes.md).

## 7. Fiscal: recepção primeiro, apuração por recortes

**Ponto de partida confirmado:** documentos vêm da ferramenta de XML já utilizada pelo escritório; XML solto e ZIP são suficientes. A documentação registra aproximadamente 85% de NFS-e nacional na amostra recebida, principalmente serviços prestados. A amostra não está no repositório e não foi recontada nesta revisão. Há divergências nas contagens detalhadas dos documentos de projeto; não tratá-las como novas medições.

| Etapa | Trabalho a executar | Evidência de conclusão |
| --- | --- | --- |
| FIS-01 - Corpus e contrato | Recuperar as amostras já fornecidas, anonimizar e complementar municípios/provedores; fixar versões e casos | Conjunto de referência rastreável, sem dados reais versionados; casos aceitos e recusados definidos |
| FIS-02 - Recepção XML/ZIP | Upload privado, limites de tamanho/expansão, defesa contra XML malicioso, fila e progresso | Arquivo inválido é rejeitado com motivo; um lote não vaza entre empresas nem bloqueia o servidor |
| FIS-03 - NFS-e nacional | Leitura das versões presentes no acervo, identificação de prestador/tomador CPF ou CNPJ, datas, valores e origem | Conteúdo extraído confere com XML; leiaute desconhecido não vira sucesso aparente |
| FIS-04 - Identidade e eventos | Deduplicação por identidade fiscal e contexto, cancelamento/substituição, eventos órfãos e reprocessamento | Nota repetida não duplica; evento anterior à nota é guardado e aplicado quando ela chega |
| FIS-05 - Conferência | Caixa de entrada por empresa/competência; pendências, totais, divergências e revisão do operador | Operador explica aceitos, duplicados, rejeitados e pendentes; nome de pasta não decide natureza da operação |
| FIS-06 - Cadastros fiscais | Participantes, serviços/produtos, municípios, unidades, classificações e tabelas pertinentes por vigência | Documento classificado tem tratamento e fonte rastreáveis; regra inexistente impede apuração silenciosa |
| FIS-07 - Escrituração | Serviços prestados/tomados, entradas/saídas, retenções, ajustes e situação fiscal | Documento recebido só compõe apuração quando escriturado e elegível; cancelamento produz efeito controlado |
| FIS-08 - Integração contábil | Classificação governa contas, históricos e retenções; prévia e geração | Documento liga receita/despesa, tributos e contrapartidas; reprocessar não duplica |
| FIS-09 - Primeiro perfil de apuração | Escolher empresa/regime/localidade do piloto; motor determinístico, memória e conferência | Competência confere com caso independente aprovado por Fred; divergências são explicadas |
| FIS-10 - Simples Nacional | Quando no perfil: receitas segregadas, histórico, anexos/faixas e fatores aplicáveis, exclusões e retenções | Memória explica enquadramento e bases; saídas conciliam com documentos e processo oficial aplicável |
| FIS-11 - Lucro Presumido | Receitas por atividade, bases e períodos, retenções/deduções e tributos aplicáveis | Apuração e saldos conciliam; cenários de receita, cancelamento e retenção validados |
| FIS-12 - Mercadorias e transporte | NF-e, NFC-e, CT-e e outros modelos da carteira; cadastro/classificação próprios | Cada modelo possui amostra e testes; tipo ainda não suportado fica identificado como pendência |
| FIS-13 - SPED e migração | Importação dos registros definidos, confronto XML-SPED e preservação da origem | Mesmo fato em duas fontes não duplica escrituração; diferenças ficam conciliáveis |
| FIS-14 - Regimes/segmentos ampliados | Créditos, ICMS/IPI/ISS e contribuições conforme perfil; interface com Lucro Real; inventário e custeio quando exigidos | Cada combinação de regime, atividade e localidade é liberada separadamente |
| FIS-15 - Fechamento e tributos | Conferência, encerramento/reabertura, guias ou preparação, vencimentos, parcelamentos e baixa | Resultado fechado é reproduzível; pagamento exige evidência própria e não é inferido da emissão da guia |
| FIS-16 - Obrigações e conectores | Arquivos, validação, retornos, protocolos e captura direta apenas quando necessária | Obrigação aplicável segue OBR; conexão só é anunciada após teste do canal oficial disponível |

**Reforma tributária é transversal.** Preservar o XML integral e os campos recebidos de IBS/CBS desde a recepção; distinguir informação apenas armazenada, informação interpretada e cálculo validado. A profundidade de interpretação continua decisão aberta (PE-39). Nenhuma ausência de parser pode descartar silenciosamente o documento original. Parâmetros, leiautes e motores devem coexistir por vigência e competência.

Não implementar todos os regimes ao mesmo tempo: FIS-09 escolhe um recorte, e FIS-10/11/14 ampliam a cobertura conforme a carteira. Os segmentos especializados já mencionados por Fred precisam de levantamento próprio; a prioridade de serviços não os elimina do plano. RAR e captura própria inicial da SEFAZ permanecem fora da primeira entrega, conforme decisões existentes.

Dependências: FIS-02 usa BAS-01/07; FIS-07 usa BAS-05 e FIS-06; FIS-08 usa CON-01/02/04/08; apuração usa regras oficiais versionadas e casos independentes. Importar arquivo SPED e gerar obrigação SPED são entregas diferentes.

Fontes: [DL-010](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/planos/DL-010-recepcao-de-documentos-fiscais.md), [mapa fiscal](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/mapa-funcional-fiscal.md) e [documentação oficial de APIs NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao), que separa produção restrita e produção.

## 8. Folha de pagamento: ciclo completo por perfil

O módulo ainda não está implementado. Começar pelo perfil real de empregadores, vínculos e convenções do escritório. A interface de folha, o motor de cálculo e o envio de eventos são partes distintas do mesmo ciclo e precisam de evidência própria.

| Etapa | Trabalho a executar | Evidência de conclusão |
| --- | --- | --- |
| FOL-01 - Perfil e casos | Definir categorias, vínculos, sindicatos, convenções, quantidade de empregados e rotinas do piloto | Matriz de cenários, fontes e casos esperados aprovada pelo responsável técnico |
| FOL-02 - Estrutura | Empregador, estabelecimentos, lotações, cargos, departamentos e jornadas | Cadastros reutilizam empresas e alimentam cálculo e eventos sem divergência |
| FOL-03 - Pessoas e vínculos | Empregados, dependentes, admissão, contratos, alterações salariais e dados necessários | Histórico por vigência; salário/documentos protegidos por permissão específica |
| FOL-04 - Rubricas e regras | Proventos, descontos, incidências, tabelas, fórmulas e convenções versionadas | Cálculo histórico usa a versão original e guarda memória reproduzível |
| FOL-05 - Variáveis do mês | Ponto importado, faltas, horas extras, adicionais, comissões, benefícios e descontos | Origem e aprovação de cada variável; carga repetida não duplica eventos |
| FOL-06 - Folha mensal | Cálculo individual/em lote, proporcionalidades, arredondamentos, conferência e diferenças | Bruto, descontos, bases, encargos e líquido conciliam com casos independentes |
| FOL-07 - Pró-labore e outras categorias | Pró-labore e, conforme carteira, contribuintes/categorias adicionais | Regras próprias não são tratadas como empregado padrão; totalizadores conferidos |
| FOL-08 - Férias | Períodos aquisitivos/concessivos, programação, médias, abono, cálculo e recibos | Férias conciliam com a folha e os períodos; duplicidade e saldos indevidos são bloqueados |
| FOL-09 - Afastamentos | Motivos, datas, retorno, efeitos no contrato, cálculo e eventos | Linha do tempo consistente e repercussões verificadas por motivo |
| FOL-10 - Décimo terceiro | Parcelas, médias, ajustes e encerramento | Resultado anual concilia com adiantamentos e eventos correspondentes |
| FOL-11 - Rescisões | Motivos, aviso, verbas, férias/13º proporcionais, descontos e documentos | Cada tipo suportado tem caso de referência; efeitos na folha e eventos conciliam |
| FOL-12 - Provisões e contabilização | Férias, 13º, encargos, baixas, centros de custo e integração contábil | Provisão inicial + movimentos - baixas = saldo final; lançamentos conciliam |
| FOL-13 - Fechamento e pagamentos | Revisão, bloqueio/reabertura, holerites, resumo e preparação de pagamentos | Reabertura registra motivo; pagamento efetivo tem confirmação e evidência separadas |
| FOL-14 - eSocial | Tabelas/cadastros, eventos não periódicos/periódicos, lotes, assinatura, retorno, totalizadores, retificação e exclusão | Ordem e dependências respeitadas; homologação, rejeições e recibos rastreáveis |
| FOL-15 - Obrigações e conferência final | Reconciliar encargos, eSocial e obrigações aplicáveis; integração com OBR | Diferença entre cálculo interno e retorno oficial impede encerramento silencioso |
| FOL-16 - Segurança e expansão | Documentos, portal restrito, SST por escopo/conector e categorias adicionais | Acesso mínimo e casos próprios por novo perfil; expansão não altera folhas antigas |

Dependências: BAS-01/04/05/07, regras versionadas e contratos de integração contábil. Construir a infraestrutura do eSocial cedo, mas liberar produção somente após validar os fluxos de cálculo e eventos. Ponto próprio, medicina ocupacional completa, domésticos e categorias especiais não entram automaticamente: a primeira entrega deve nomear expressamente o que suporta.

Um piloto de folha deve incluir o mês normal e os eventos que ocorrerão durante o uso: admitir, alterar, afastar, conceder férias e desligar. Entregar apenas cálculo mensal não equivale a substituir o departamento pessoal.

Fonte oficial para o desenvolvimento: [documentação técnica do eSocial](https://www.gov.br/esocial/pt-br/documentacao-tecnica). A versão de leiaute, esquemas e manual deve ser fixada na abertura da etapa e conferida novamente antes da homologação.

## 9. Obrigações, ECD, ECF e apuração do lucro

Esta é uma frente compartilhada de controle e integração. O cálculo permanece no módulo de origem; o controle de obrigação reúne aplicabilidade, arquivo/evento, validação, aprovação, protocolo, recibo e retificação. Uma obrigação não fica “entregue” porque um arquivo foi gerado.

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| OBR-01 - Matriz de obrigações | Empresa, regime, atividade, localidade, competência, fonte e versão | Lista aplicável ao piloto revisada; obrigação de manual antigo não é herdada automaticamente |
| OBR-02 - Central de controle | Calendário, responsável, dependências, estados e documentos comprobatórios | Preparado, validado, aprovado, transmitido e aceito são estados distintos |
| OBR-03 - Base para ECD | Plano de contas, vínculos requeridos pelo leiaute, participantes/responsáveis, livros, saldos, lançamentos e demonstrações | Integridade contábil e campos necessários conferidos por período |
| OBR-04 - Geração e validação da ECD | Gerador por leiaute/exercício, validações internas, importação no programa oficial e tratamento de erros | Arquivo validado no programa oficial aplicável; recibo somente após transmissão efetiva autorizada |
| OBR-05 - Base de ECF | Plano referencial e recuperação/conciliação de dados contábeis, fiscais e saldos anteriores | Mapeamentos e cruzamentos compatíveis com o perfil e período |
| OBR-06 - Lalur/Lacs e Lucro Real | Adições/exclusões, compensações, controles de partes A/B, saldos e evidências; métodos de apuração aplicáveis | Resultado contábil concilia com base fiscal; saldos controlados entre períodos sem dupla apuração |
| OBR-07 - Geração e validação da ECF | Registros/tabelas dinâmicas por versão, validação e cruzamentos com ECD e apuração | Programa oficial aceita o arquivo conforme regras aplicáveis; erros e advertências têm tratamento documentado |
| OBR-08 - Obrigações fiscais | EFD ICMS/IPI, EFD-Contribuições, EFD-Reinf e demais obrigações que a matriz determinar | Cada obrigação tem origem, leiaute e validação próprios; cobertura declarada por perfil |
| OBR-09 - Obrigações de folha e tributos | Reconciliar eSocial, DCTFWeb/MIT e FGTS Digital quando aplicáveis, conforme canais oficiais disponíveis | Bases, débitos e guias conferidos; não presumir API de transmissão para todos os serviços |
| OBR-10 - Transmissão e retificação | Credenciais/certificados, aprovação vinculada ao conteúdo, envio, retorno e substituições | Alterar conteúdo invalida aprovação; repetição de rede não cria obrigação duplicada |

**Responsabilidade dos dados:** Contabilidade é dona dos livros e saldos; Fiscal é dono da escrituração e classificação tributária; Folha é dona da remuneração e eventos trabalhistas; a frente de Lucro Real é dona dos ajustes e controles fiscais; OBR coordena o ciclo de entrega. Evitar que ECF e Fiscal calculem a mesma base por motores independentes.

ECD depende do núcleo contábil, livros e demonstrações exigidos para o perfil. ECF depende de contabilidade conciliada, dados fiscais e apuração correspondente ao regime. Lalur/Lacs não é requisito universal para todo cliente. Não bloquear empresas de perfis mais simples pela conclusão de todos os cenários de Lucro Real.

Fontes a fixar em cada execução: manuais e programas oficiais da Receita/SPED, documentação do eSocial, FGTS Digital e legislação do ente competente. Esta revisão não certifica leiautes nem versões futuras; o plano exige consulta e registro antes de codificá-los.

## 10. Honorários e financeiro do escritório

O escopo é o financeiro do escritório contábil. A escrituração de caixa/bancos dos clientes aparece na Contabilidade; transformar o produto em um financeiro operacional completo dos clientes exige decisão adicional.

| Etapa | Trabalho a executar | Evidência de conclusão |
| --- | --- | --- |
| HON-01 - Serviços e contratos | Carteira, serviços recorrentes/avulsos, reembolsos e condições | Contrato versionado determina o que será faturado e desde quando |
| HON-02 - Reajustes e vencimentos | Índices, datas, descontos, multas e juros conforme contrato | Simulação e cálculo reproduzíveis; mudança não altera títulos antigos sem procedimento |
| HON-03 - Faturamento | Geração por competência, proporcionalidade e aprovação | Executar duas vezes não duplica cobrança; título aponta para contrato/serviço |
| HON-04 - Contas a receber | Parcelas, baixas totais/parciais, abatimentos, estornos e inadimplência | Saldo do título reconcilia com movimentos e comprovantes |
| HON-05 - Cobrança | Régua de acompanhamento, histórico e comunicação autorizada | Contato registrado; não enviar cobrança indevida ou duplicada |
| HON-06 - Pagamentos e caixa | Contas a pagar, bancos, conciliação e fluxo de caixa do escritório | Previsão e caixa realizado são distintos e conciliáveis |
| HON-07 - Integrações | Pix/boleto, retornos bancários e emissão de NFS-e conforme provedor escolhido | Homologação, idempotência e verificação de notificações; recebimento só com confirmação válida |
| HON-08 - Rentabilidade | Tempo, custos e despesas por cliente/contrato/departamento | Margem explica a origem dos custos; dado ausente não vira lucro aparente |
| HON-09 - Contabilização | Receitas, despesas, recebimentos e tributos do escritório | Lançamentos chegam à empresa contábil correta, sem misturar carteira dos clientes |

Dependências: BAS-01/04/07, cadastro da entidade do escritório, contratos de CON-08 e processos de OBR para emissão aplicável. PAR envia serviços aprovados e valores; não gera cobrança automática sem regra contratual.

## 11. Processos e Paralegal

| Etapa | Trabalho a executar | Evidência de conclusão |
| --- | --- | --- |
| PAR-01 - Catálogo | Abertura, alteração, transformação, baixa e serviços por localidade | Modelo define documentos, etapas, dependências e responsáveis |
| PAR-02 - Abertura do processo | Solicitação, escopo, orçamento, aprovação e vínculo com empresa | Processo pode existir antes do CNPJ definitivo sem criar cadastro fiscal fictício |
| PAR-03 - Documentos e execução | Checklist, tarefas, exigências, responsáveis e histórico | Etapa não conclui sem evidência necessária; alterações são rastreáveis |
| PAR-04 - Visões de acompanhamento | Lista, Kanban, calendário, prioridades e alertas | Mesmo processo apresenta estado consistente em todas as visões |
| PAR-05 - Protocolos e taxas | Órgão, número, comprovante, pagamento, exigência e retorno | Protocolo real separado de rascunho; despesas ligadas ao processo |
| PAR-06 - Licenças e vencimentos | Inscrições, alvarás, certidões, procurações e certificados | Vencimento gera tarefa e responsável; segredo do certificado não fica em documento público |
| PAR-07 - Alteração cadastral | Sócios, capital, endereço, atividades e estabelecimentos | Conclusão atualiza cadastro central com vigência e evidência, sem sobrescrita silenciosa |
| PAR-08 - Cliente e honorários | Solicitações, acompanhamento, serviço aprovado e reembolso | Cliente vê apenas o seu processo; faturamento não duplica honorário |
| PAR-09 - Conectores | Juntas, Redesim, Receita e prefeituras quando houver canal disponível | Disponibilidade e credenciamento verificados; acompanhamento manual funciona quando não houver integração |
| PAR-10 - Rotinas recorrentes | Checklists fiscais, contábeis e de folha por competência | Fechamentos usam tarefas comuns, mantendo regras de negócio nos módulos de origem |

Dependências: BAS-04/07/08 para operação interna; portal apenas para PAR-08 e interação com clientes; HON para cobrança. Catálogo, tarefas e protocolos podem funcionar antes do portal. Não prometer protocolo automático em todos os órgãos: o produto deve distinguir registro manual, consulta e transmissão.

## 12. Documentos, portal e comunicação

Essas capacidades atendem vários departamentos e devem compartilhar infraestrutura. O cliente não recebe automaticamente o mesmo acesso de um funcionário do escritório.

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| POR-01 - Identidade e acesso | Usuário vinculado às empresas autorizadas, perfis e revogação | Testes de troca de identificador não revelam dados de outro cliente |
| POR-02 - Recepção documental | Solicitar/enviar documentos, categoria, competência e situação | Arquivos privados, origem preservada, revisão e tratamento de risco de upload |
| POR-03 - Publicação | Liberação de guias, demonstrações e relatórios por responsável | Rascunho não é publicado; substituição mantém histórico e destinatários corretos |
| POR-04 - Pendências e processos | Acompanhar tarefas, exigências, prazos e entrega | Cliente entende a próxima ação e o escritório enxerga o responsável |
| POR-05 - Folha e sigilo | Entrega de holerites/documentos conforme identidade e permissão | Empregado ou cliente não acessa remunerações indevidas |
| POR-06 - Aprovações | Registrar aprovações relacionadas a documentos e operações | Identidade, versão, data e conteúdo ficam vinculados; mudança invalida aprovação |
| POR-07 - Notificações | Preferências, alertas, histórico de entrega e falhas | Reenvio controlado, sem expor informações sensíveis no corpo do aviso |
| POR-08 - Retenção e pesquisa | Busca autorizada, versões, política de retenção e exportação | Busca e download aplicam o mesmo isolamento do cadastro |

Dependências: BAS-01/03/07/08; módulos produtores precisam definir quem libera cada documento. A primeira versão pode publicar apenas documentos já conferidos, sem esperar todos os departamentos.

## 13. Capacidades complementares do mapa funcional

Estas frentes aparecem nos mapas e referências, mas **não estão confirmadas como módulos autônomos obrigatórios**. Devem entrar como extensões justificadas pela carteira. Não são motivo para atrasar NFS-e ou fechamento contábil inicial.

| Frente | Etapas propostas | Integração e conclusão |
| --- | --- | --- |
| Patrimônio/imobilizado | Cadastro e aquisição; componentes/vida útil/valor residual; depreciação e amortização; transferências/baixas; revisão de estimativas; controles fiscais quando aplicáveis | Contabilidade recebe movimentos; saldos e baixas conciliam; critérios e vigências documentados |
| Estoque e custeio | Saldos iniciais; entradas/saídas; inventário; critério de custeio; perdas/ajustes; custo contabilizado | Fiscal fornece documentos e Contabilidade recebe custo; quantidades e valores fecham; não presumir ERP industrial completo |
| Ponto | Importar marcações; jornadas; ocorrências; revisão; enviar variáveis à Folha | Folha rastreia variáveis; motor próprio e obrigações do ponto só entram após definição específica |
| Orçamento e gestão | Plano orçamentário; versões; centros; realizado; desvios | Realizado vem da Contabilidade; previsão nunca altera escrituração |
| Consolidação e nichos | Grupos, eliminações e moedas quando necessários; combustíveis, imobiliário, transporte e outras particularidades da carteira | Cada extensão tem recorte, fonte e casos próprios; nenhuma é considerada coberta pelo fiscal genérico |

As necessidades desses segmentos já devem ser registradas na análise da carteira. A sequência de implementação depende do benefício e da obrigação concreta, não da existência de um manual de referência.

## 14. Assistente de IA e servidor MCP

O assistente interno e o servidor MCP são produtos relacionados, com autenticação e contratos próprios. Ambos usam os mesmos serviços e permissões do DataLedger. Não expõem SQL arbitrário nem substituem cálculos oficiais por respostas de modelo.

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| IA-01 - Configuração | Provedores, orçamento, limites, política de dados e contexto permitido | Custos e acesso observáveis; dados não autorizados não seguem ao provedor |
| IA-02 - Consulta | Pendências, lançamentos, relatórios e processos com referência de origem | Resposta aponta empresa, período e registros usados; ausência de informação é explícita |
| IA-03 - Explicações | Variações, diferenças e memórias de cálculo já produzidas pelo motor | Explicação não inventa números nem altera resultado oficial |
| IA-04 - Sugestões | Classificação contábil/fiscal e tarefas propostas | Usuário revisa antes de efetivar; sugestão e decisão ficam diferenciadas |
| IA-05 - Avaliação | Casos de erro, vazamento entre empresas, instruções em documentos e custo | Conteúdo importado não altera permissões; respostas críticas têm rastreio e revisão |
| MCP-01 - Base | SDK/versão, transporte, autenticação, escopos e limites | Cliente autorizado conecta; cliente sem escopo é recusado |
| MCP-02 - Leitura | Empresas, pendências, balancete, folha, honorários e processos já implementados | Paginação e autorização aplicadas por objeto; ferramenta não anuncia módulo inexistente |
| MCP-03 - Preparação | Propor lançamento, preparar importação e criar tarefa delimitada | Mesmos validadores do produto; repetição não duplica escrita |
| MCP-04 - Operações críticas | Aprovação vinculada à ação, conteúdo e usuário autorizado | Alteração invalida aprovação; auditoria e idempotência preservadas |
| MCP-05 - Homologação | Cliente compatível testado, documentação e regressão de contratos | Exemplo real de conexão e testes de permissões/erros documentados |

Dependências: APIs estáveis, auditoria íntegra, BAS-01/07 e módulos efetivamente implementados. Consulta assistida pode ser antecipada após essas condições; automações de escrita ficam atrás das garantias de negócio.

## 15. Operação, qualidade e implantação

Esta frente começa em M0 e acompanha cada liberação. Segurança operacional e restauração não ficam para depois que todos os módulos estiverem prontos.

| Etapa | Entrega | Critério de conclusão |
| --- | --- | --- |
| OPS-01 - Ambiente reproduzível | Desenvolvimento/homologação em PostgreSQL, instalação e migrações limpas | Outra instalação sobe pelos comandos documentados; diferenças do SQLite ficam explícitas |
| OPS-02 - CI e repositório | Proteção da main, verificações, revisão e limites dos testes | PR sem verificação obrigatória não integra; testes pulados são visíveis e tratados |
| OPS-03 - Segurança operacional | HTTPS, sessões, segredos, certificados, permissões administrativas e atualizações | Segredos fora do código; perfis normais sem acesso técnico desnecessário |
| OPS-04 - Backup e restauração | Banco + documentos + configuração necessária, retenção, recuperação e responsáveis | Restauração isolada executada, tempos e perda máxima aceitável definidos e medidos |
| OPS-05 - Observabilidade | Erros, logs sem dados sensíveis, correlação, métricas de filas e alertas | Falha é detectável e rastreável até a operação afetada |
| OPS-06 - Desempenho | Volumes reais por competência e cenário de 50 usuários simultâneos | Metas de resposta e processamento definidas antes do ensaio e atendidas com evidência |
| OPS-07 - Migração | Inventário da origem, mapeamento, saneamento, carga e reconciliação | Quantidades, valores, saldos e documentos conferem; rejeições têm tratamento |
| OPS-08 - Piloto paralelo | Carteira limitada, mesma competência no sistema atual e no DataLedger | Diferenças explicadas e aprovadas; usuário percorre fluxo completo |
| OPS-09 - Entrada em produção | Versão, responsáveis, manual, suporte, monitoramento e retorno | Aceite funcional/técnico registrado; plano de reversão testado e reconciliável |
| OPS-10 - Manutenção | Atualizações normativas, dependências, incidentes e suporte | Mudança de regra cria nova vigência; histórico calculado continua reproduzível |

**Reversão:** código e configuração podem voltar à versão anterior quando compatíveis; migração de dados exige estratégia própria. Para importações, usar lote e origem para desfazer a carga de teste com controle. Depois de escriturar ou transmitir, não usar restauração ou exclusão como correção rotineira: aplicar estorno, ajuste, reabertura ou retificação conforme o domínio e reconciliar os efeitos externos.

**Portão de liberação por módulo:** fluxo completo com persistência, permissões e isolamento; cálculo conferido quando aplicável; repetição/concorrência; migração; interface com vazio/erro/sucesso; documentação de limites; CI do commit; restauração e operação; aceite de Fred para uso no perfil escolhido.

## 16. Primeira fila de execução

Esta é a fila recomendada depois da aprovação do plano. Cada linha pode gerar um ou mais PRs pequenos, conforme o risco. Não abrir um único PR com todos os módulos.

| Ordem | Pacote | Resultado e vínculo existente |
| --- | --- | --- |
| 1 | Plano mestre e reconciliação | ORG-01/02/03; alinhar DL-020/021, BL e decisões, preservando auditorias |
| 2 | Integridade administrativa | Fechar BL-83 e BL-211; teste HTTP e concorrência no PostgreSQL |
| 3 | Trilha íntegra e processo | BL-14/16/57, proteção da main e decisão do suporte SQLite |
| 4 | Primeiro acesso e importação | BAS-01/02 e DL-018; iniciar FIS-01/02 com arquivos em área de conferência |
| 5 | Fechamento e leitor NFS-e | CON-01/02 com DL-016; FIS-03/04 com DL-010, em trabalhos independentes |
| 6 | Saldos, revisão e conferência fiscal | CON-03/04 e FIS-05/06; documentos elegíveis e empresa implantada |
| 7 | Escrituração e contabilização | FIS-07/08 e CON-08; nota com prévia, aprovação, origem e lançamento |
| 8 | Relatórios e primeiro cálculo | Recorte de CON-05 com estruturas/vínculos das demonstrações, CON-12 e FIS-09; relatórios e apuração conciliáveis, sem esperar todo o plano referencial |
| 9 | Piloto e repetição do mês | OPS-04/05/08; corrigir diferenças do uso real e demonstrar segundo processamento sem duplicação |
| 10 | Expansão controlada | CON-06/07/09/10/11/14, FIS-12/13 e preparação da Folha conforme próxima prioridade |

**Primeira demonstração que Fred deve receber:** entrar no produto, selecionar empresa, enviar ZIP, acompanhar processamento, examinar rejeições e duplicidades, conferir uma NFS-e e seu XML. Na demonstração seguinte: classificar, revisar a contabilização, efetivar, localizar a origem pelo Razão e comprovar o bloqueio do período fechado.

Isso cria resultados visíveis sem anunciar Fiscal completo antes de haver apuração nem Contabilidade completa antes de haver fechamento, demonstrações e obrigações.

## 17. Decisões abertas, no momento certo

Estas perguntas não impedem aprovar o mapa geral. Devem ser respondidas antes da implementação afetada; não precisam virar um questionário único agora. Questões de documentação oficial devem ser pesquisadas pela equipe e submetidas tecnicamente, sem transferir essa pesquisa para Fred.

| Antes de | Decisão necessária | Por que muda a entrega |
| --- | --- | --- |
| DL-018 e acessos | Quem cria escritório, quem se torna administrador e como entra o próximo funcionário | Define convite/cadastro e fronteira de isolamento |
| Multi-escritório operacional | Permissão por empresa e unicidade do CNPJ global ou por escritório | Hoje o CNPJ global limita a mesma empresa em carteiras distintas; há impacto de sigilo e migração |
| Fechamento e implantação | Responsáveis pela reabertura, regra do resultado anterior, matriz/filiais e data do ajuste | Define livros, autorização e saldos iniciais |
| Correção em massa | Campos permitidos e política para registros conciliados/derivados | Evita alterar valor/data com o mesmo tratamento de uma descrição |
| Regime tributário | Piso de vigência anterior a 2000, ainda hipótese HI-07 | O limite de lançamento já confirmado não autoriza impor automaticamente o mesmo piso ao regime |
| Primeiro cálculo fiscal | Regime, municípios/UFs, atividades e empresas do piloto | Determina regras e casos de referência, sem tentar cobrir o país inteiro de uma vez |
| Ampliação de importadores | Acesso às amostras já fornecidas, SPED e amostras de outras origens; leitura estruturada de IBS/CBS | Reduz adaptação excessiva a um município/provedor |
| Folha | Categorias, convenções, ponto, benefícios e volumes | Define o primeiro ciclo completo de cálculo e eventos |
| Obrigações | Obrigações realmente entregues por perfil e calendário operacional | Ordena ECD/ECF e demais entregas por necessidade concreta |
| Produção | Provedor, volumes, retenção, responsáveis e metas de recuperação | Permite dimensionar custo, segurança, carga e continuidade |

**Já decidido e preservado:** nuvem/navegador; cerca de 50 usuários; NFS-e como primeira recepção; XML/ZIP; RAR dispensado; origem em ferramenta existente; regras contábeis listadas em CON; exclusão do último regime incorreto com trilha técnica, conforme RC-86/DE-039; sequência intercalada confirmada nesta conversa.

## 18. Como medir avanço e levar ao GitHub

**Medir por entregas aceitas:** competências fechadas e reconciliadas; documentos recebidos/conferidos sem duplicação; divergências com o sistema de referência; obrigações validadas/aceitas; tempo de operação; falhas pendentes por gravidade. Não usar linhas de código, número de agentes ou quantidade de testes como percentual do produto.

Não há prazo global confiável sem conhecer disponibilidade de desenvolvimento, volumes, integrações e perfis de clientes. Estimar cada pacote depois de fechar seu escopo, usando a velocidade observada nos primeiros incrementos. Obrigações, municípios e convenções adicionais aumentam a cobertura necessária.

Após a revisão de Fred, o encaminhamento proposto é:

1. Conferir novamente a revisão da main e preservar mudanças ocorridas após este diagnóstico.
2. Criar branch documental própria e reservar identificador DL sem colisão; os códigos deste plano continuam como mapa de decomposição.
3. Incorporar o plano mestre em `docs/projeto/`, relacionar DL/BL/RC/DE e ajustar os documentos de estado conflitantes no escopo aprovado.
4. Validar links, identificadores, coerência dos estados e documentação. Não reescrever relatórios de auditoria para fazê-los concordar com decisões posteriores.
5. Fazer commit, push e abrir PR de planejamento com objetivo, critérios, evidências e limites. Nenhuma implementação de módulo entra nesse PR.
6. Depois da integração aprovada, abrir os pacotes da primeira fila e manter apenas o trabalho realmente em curso como “em desenvolvimento”.

**Modelo de cartão de implementação:** objetivo; perfil atendido; entradas e saídas; regras/fontes/vigências; dependências; responsável; critérios observáveis; casos de sucesso/erro/limite; segurança e concorrência; migração/reversão; evidência de testes; revisão e commit/PR. Estados: planejada, em desenvolvimento, em validação, bloqueada, em revisão e integrada. “Integrada” deve continuar acompanhada dos limites de uso.

**Situação desta entrega:** análise e planejamento preparados para revisão. Nenhum arquivo do repositório foi alterado, nenhum commit/push/PR foi realizado e nenhuma mudança foi publicada no GitHub.

### Referências complementares

- [Estado registrado no projeto](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/agents/estado.md): usar com as divergências documentadas nesta análise.
- [DL-018: primeiro acesso](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/planos/DL-018-primeiro-acesso.md).
- [Regras do projeto](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/AGENTS.md).
- [Fontes de referência do domínio](https://github.com/fredabsd-svg/DataLedger/blob/b8c66a60ae11f2877c1f0317608c7bf1ed52bfec/docs/projeto/fontes-de-referencia.md): manuais comerciais antigos servem ao levantamento de capacidades, não à definição da regra vigente.
- [Documentação técnica NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica) e [eSocial](https://www.gov.br/esocial/pt-br/documentacao-tecnica): fontes oficiais consultadas para orientar as frentes de integração. Esquemas, parâmetros e regras devem ser fixados por vigência na etapa de implementação.

---

## Notas do `arquiteto-senior` — 2026-09-16

**Nada acima desta linha foi escrito, reescrito, suavizado ou abreviado por
mim.** O que segue é minha análise, e ela vem depois de propósito.

### Por que estas notas existem

O Fred pediu "análise e suba para o GitHub". Publicar sem analisar seria
transformar um documento de terceiro em requisito do projeto só porque ele
chegou bem escrito — que é exatamente o erro que este projeto persegue desde
2026-09-13. Então eu **fui medir** as afirmações verificáveis do documento,
uma a uma, na mesma revisão que ele analisou (`b8c66a6`, conferida por mim
nesta data: é a `main` atual).

### 1. O que eu medi, e o resultado

| Afirmação do documento | Como medi | Resultado |
| --- | --- | --- |
| "O README duplica a DL-020 com marcações diferentes" | Leitura do `README.md` na `main` | **Verdadeiro.** Duas linhas para a mesma etapa, uma marcada `- [ ]` e outra `- [x]`, a três linhas de distância. Um leitor não tem como decidir qual vale. **Corrigido na DL-022** |
| "A DL-021 já foi integrada, mas o plano e o estado ainda a descrevem como não iniciada" | `docs/agents/estado.md`, `docs/planos/DL-021-*.md` e `git log` | **Verdadeiro.** A DL-021 entrou pelo PR #22 e os dois documentos diziam "planejada, não iniciada". **Corrigido na DL-022** |
| "A proteção da `main` consultada retornou `protected: false`" | Consulta à API do GitHub em 2026-09-16, nesta sessão | **Verdadeiro.** `protected: False`, com o `head` em `b8c66a6`. A **BL-02** continua aberta e é ação administrativa do Fred — nenhum agente pode fechá-la |
| "1.200 testes aprovados e 2 pulados no commit analisado" | Execuções do GitHub Actions de `b8c66a6` | **Verdadeiro.** Os 2 pulados são as medições de CSS que exigem navegador (BL-229) |
| "O admin de lançamentos já bloqueia inclusão, alteração e exclusão; não há fundamento para repetir o falso positivo antigo" | `apps/contabilidade/admin.py` | **Verdadeiro, e o falso positivo era meu.** Já está registrado como erro meu na BL-211, com a correção escrita antes desta análise |
| "O histórico de regime tem ordenação implícita por início; o risco confirmado é sobreposição e falta de desempate" | `apps/empresas/models.py` e `apps/empresas/services.py` | **Verdadeiro, e me corrige** — ver o item 3 abaixo |

### 2. O que eu **não** medi, e portanto não endosso como fato

Registro porque metade de um relatório honesto é a lista do que ele **não**
prova:

- A reprodução local com **Python 3.12 e SQLite** e a falha de código repetido:
  não repeti esse ensaio nesta sessão. O diagnóstico é plausível e o
  encaminhamento proposto (padronizar PostgreSQL e **decidir expressamente** o
  alcance do SQLite) me parece certo, mas continua sendo **hipótese de
  trabalho** até alguém rodar.
- Os percentuais do acervo fiscal (≈85% de NFS-e, ≈12% com bloco IBS/CBS). O
  próprio documento já diz que a amostra **não está no repositório** e que não
  foi recontada. Eles vêm de `RC-65`/`RC-76` e continuam valendo com a mesma
  força que já tinham: medição de **uma** amostra, não do universo.
- A contagem "seis aplicativos de domínio/base" e a leitura de que ter papel de
  financeiro ou paralegal não significa módulo existente: **não recontei**, mas
  ela bate com o que o `estado.md` afirma há várias etapas.
- Nada neste documento é **validação contábil ou fiscal**. Ele descreve
  capacidade de software. Alíquota, leiaute, prazo e incidência continuam
  exigindo fonte oficial vigente e a validação profissional do Fred.

### 3. Onde o documento corrige a **mim**, e eu aceito

Este é o item que mais me interessa, porque é o único em que a análise muda um
registro meu.

Eu escrevi, acolhendo o achado A2 da auditoria, que
`registrar_regime_tributario` fazia `.first()` **"sem `order_by`"**. Isso é
literalmente verdade na linha do serviço — e **enganoso**, porque
`HistoricoRegimeTributario.Meta` declara `ordering = ["-vigencia_inicio"]`, e o
Django aplica essa ordenação ao `.first()`. Conferido por mim hoje, nos dois
arquivos.

O risco **não some**, muda de nome, e essa é a diferença entre corrigir a coisa
certa e a errada:

- **Continua verdadeiro:** nada impede **dois períodos abertos ao mesmo tempo**
  (não há `UniqueConstraint`), e o inline do admin cria esse estado.
- **Continua verdadeiro:** com dois períodos de **mesmo `vigencia_inicio`**,
  não existe desempate — o `.first()` escolhe conforme o plano de execução do
  banco, e o "último regime" deixa de ser único, que é justamente o registro
  que o `RC-86`/`DE-039` autoriza apagar.
- **Deixa de ser verdadeiro:** dizer que a consulta não tem ordenação nenhuma.

A correção prescrita continua a mesma (restrição de **um** período aberto por
empresa, desempate explícito, e o inline saindo do admin ou passando pelo
serviço). O que mudou foi a **descrição do defeito** — e descrição errada de
defeito produz correção errada de defeito. A nota de precisão foi acrescentada
à **BL-211 sem apagar o texto do auditor**, pela mesma regra do começo deste
arquivo.

### 4. O que eu adoto como direção, sem ressalva

- **Medir avanço por entregas aceitas**, nunca por número de testes, linhas ou
  agentes. A suíte com 1.200 testes não diz que 1.200/N do produto está pronto;
  ela diz que o que existe está defendido. O documento acerta em cheio, e isso
  vale contra um vício que este projeto já teve.
- **Recepção fiscal antes de integração contábil.** Receber, conferir e mostrar
  duplicidade **não altera escrituração** — então pode andar em paralelo ao
  fechamento, e é a primeira coisa que o Fred consegue **ver funcionando**.
- **"Obrigação entregue" não é "arquivo gerado".** Estado separado para
  preparado, validado, aprovado, transmitido e aceito. É a diferença entre um
  sistema que ajuda e um que mente para o contador.
- **Portão de liberação por módulo** e **cartão de implementação** — os dois
  cabem no que o projeto já faz (plano com critérios de aceite numerados,
  auditoria independente da versão integrada).

### 5. Ressalvas

**(a) Mapa não é estado, e esta é a lição mais cara deste projeto.** Em
2026-09-13 o Fred encontrou o README afirmando, no topo, que o sistema era "um
esqueleto sem módulo de negócio" enquanto o mesmo arquivo, mais abaixo,
documentava a contabilidade funcionando — a afirmação obsoleta estava em
**quatro** lugares. A causa não foi distração, foi **duplicação**. Um plano
mestre com 12 famílias de códigos e mais de 100 etapas é o candidato perfeito a
virar o quinto lugar onde o estado do projeto mora e diverge. Por isso a
**DE-041**: este arquivo descreve **sequência e critérios**; quem quiser saber
em que pé está qualquer coisa lê `docs/agents/estado.md`. O próprio documento
propõe isso na seção 5 — eu só transformei a proposta em regra registrada.

**(b) Os códigos deste mapa não viram fila de tarefas.** `ORG-01`, `CON-04`,
`FIS-09` são endereços de um mapa de decomposição. Trabalho executável continua
nascendo como **etapa `DL-xxx` com plano próprio**, critérios de aceite
numerados, divisão de arquivos e auditoria. Se cada linha destas tabelas virar
um item de backlog agora, o projeto ganha 100 itens sem dono e perde a
propriedade que faz o backlog funcionar: **pendência com destino**.

**(c) Uma frase do documento envelheceu no instante em que ele foi
incorporado — e eu não a editei.** A seção 18 diz: *"Nenhum arquivo do
repositório foi alterado, nenhum commit/push/PR foi realizado e nenhuma
mudança foi publicada no GitHub."* Isso era **verdade quando o documento foi
escrito** e deixou de ser verdade exatamente com o commit que o trouxe para
cá. Eu poderia ter apagado a frase; não apaguei, porque texto preservado que
alguém "ajusta depois" deixa de ser preservado. Fica declarado aqui: **a partir
da DL-022, a situação daquela frase é outra**, e a atual está no
`estado.md`.

**(d) A direção atribuída ao Fred foi registrada por outra sessão.** O documento
abre dizendo "direção escolhida por Fred nesta conversa". Eu **não** ouvi essa
conversa; o que eu tenho é o documento e a instrução dele de publicá-lo. Por
honestidade de origem, registrei como **RC-87 citando a fonte**, e deixei em
aberto, como **PE-47**, a única coisa que muda o que eu faço amanhã: se a
"primeira fila de execução" da seção 16 é **ordem aprovada** ou recomendação
sujeita à palavra dele.

### 6. O que a DL-022 mudou no repositório

Só documentação. **Nenhuma linha de código de produto.** O detalhe está no
[plano da etapa](../planos/DL-022-plano-mestre-e-reconciliacao.md); em resumo:
este arquivo, a desduplicação da DL-020 no README, a DL-021 marcada como
integrada nos três lugares onde ela estava errada, a nota de precisão da
BL-211, e os registros **DE-041**, **RC-87** e **PE-47**.

### 7. O que continua aberto, e depende do Fred

- **PE-47** — a fila da seção 16 é ordem aprovada?
- **BL-02** — a proteção da `main` é ação administrativa dele, e segue medida
  como inexistente.
- As decisões da seção 17 do documento, que já têm endereço próprio em
  `docs/projeto/requisitos.md` e não precisam virar questionário agora.
