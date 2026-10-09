# Pesquisa sobre os acumuladores do sistema de referência — 09/10/2026

**Convenção de marcas.** Todas as páginas citadas são páginas impressas do PDF, que coincidem com as do arquivo.
- *manual EF p.N*: `Domínio Escrita Fiscal.pdf`, versão 10.1A-12, © 2018.
- *manual IP p.N*: `Importação Padrão.pdf`, mesma versão.
- *leiaute*: `leiautes.zip`, arquivos de 2011.
- *central (URL)*: artigo da Central de Soluções que li inteiro.
- *secundário (URL)*: fórum de contadores.
- *inferência*: leitura minha, não comprovada.

O texto abaixo é reescrito em palavras minhas. Só entre aspas ficam nomes curtos de campo. Nada foi gravado no repositório. Os arquivos baixados estão só no scratchpad, em `dominio/`, `leiautes_x/` e `scripts/`.

**Achado de fonte que desmente o repositório.** `docs/projeto/fontes-de-referencia.md` (linhas 132-145, nota de 2026-09-13) diz que a Central de Soluções não é legível por agente. Hoje ela é. `curl` com UA de navegador devolveu os artigos completos no HTML, e o `WebFetch` seguiu com 403. Conferi os códigos 121, 201, 653, 776, 786, 814, 824, 894 e 922: os tamanhos e os corpos são diferentes entre si. A nota do repositório precisa de revisão, e isso é decisão do responsável.

---

## 1. O que é um acumulador e o que ele guarda

**Definição.** É um cadastro da Escrita Fiscal que classifica cada lançamento de entrada, saída, serviço, outras receitas e outras deduções. Serve para totalizar valores e apurar impostos, e o manual o declara indispensável para a exatidão do cálculo (manual EF p.365).

**Cabeçalho.**
- Código sequencial editável, nome pela operação fiscal e data de cadastro.
- Situação ativo/inativo, com data a partir da qual fica inativo.
- Vigências, com "Nova Vigência" e "Excluir Vigência" (manual EF p.366).

**Grupos de campos e função de cada um:**

| Grupo | Para que serve | Fonte |
| --- | --- | --- |
| Geral, "Incide sobre" | Diz se a operação entra no faturamento e/ou na receita bruta. | manual EF p.367 |
| Geral, marcadores de natureza | Devolução e retorno de remessa; tratamento do Simples municipal e do Simples/SC; bares e restaurantes. | manual EF p.367-368 |
| Geral, opções de cálculo | Serviço terceirizado no Simples (IN 391/04); não somar com serviço no adicional de 50%; alíquota diferenciada; receita diferida de PIS/Cofins e IRPJ/CSLL (art. 25 da IN 247/2002); veículos usados; ônus do IRRF assumido pela fonte. Cada opção só habilita se o parâmetro da empresa correspondente estiver ligado. | manual EF p.368-369 |
| Geral, crédito de ICMS do ativo | Define se as saídas contam no coeficiente de crédito do ativo imobilizado, com guia "Patrimônio" para dizer qual valor da nota alimenta "saídas tributadas" e "saídas isentas". | manual EF p.369-370, 417-419 |
| Notas | Gerar parcelas, dados de frete, digitação de estoque, dedução de ISS (LC 116, art. 7º, §2º, I), ICMS desonerado, DMED. Também as marcas de PIS/Cofins de transporte e de outros créditos presumidos, salão-parceiro e SCP. | manual EF p.370-373 |
| Opções | Gerar bem no Patrimônio (com ou sem soma do diferencial de alíquota); gerar a nota de entrada em outra empresa; tipo à vista/a prazo para o SINCO. | manual EF p.373-374 |
| Lançamentos | Restringe o acumulador a um tipo de movimento: entrada, saída, serviço, Redução Z, CF-e, RMD e outros. | manual EF p.375 |
| Notas II | Observações e informações complementares do fisco e do contribuinte; documentos referenciados que geram os registros C111 a C114 do SPED; empreendimento imobiliário. | manual EF p.376-379 |
| Impostos | Lista os impostos que fazem base nesse acumulador, escolhidos entre os impostos que a empresa habilitou nos parâmetros. Cada linha tem o percentual de base e uma janela de "Definições". | manual EF p.379-381 |
| Impostos, Geral | Para PIS/Cofins: classificação DACON de outras receitas e de crédito. Para os demais: código de recolhimento, destino da diferença entre valor contábil e base (isentas, outras ou nenhuma), redução do imposto por percentual (no lançamento ou como estorno na apuração) e débitos especiais do SPED (registro C197). | manual EF p.382-384 |
| Impostos, Alíquota | Alíquota fixa, ou tabela interestadual de ICMS mais alíquota interna, mais o percentual de redução de base. | manual EF p.384-385 |
| Impostos, Contas | Para imposto "lançado": contas de recolher, recuperar, devoluções e estorno, com os históricos. | manual EF p.385-386 |
| Impostos, Compensações, MVA, Recolhimentos | Retenções do COSIRF (IN 306/2003). Percentuais de MVA, com redução, para ST e antecipação. Códigos de recolhimento de IPI, IRRF, retidos e FUNRURAL. | manual EF p.387-389 |
| SPED, PIS/Cofins | Linhas por CST. Entradas (Lucro Real, transporte ou crédito presumido): vínculo e base do crédito, natureza do frete, alíquotas e códigos de recolhimento. Saídas: natureza da receita, redução de base, alíquota percentual ou por unidade. Também entidades financeiras equiparadas. | manual EF p.390-394 |
| SPED, INSS sobre Receita Bruta e EFD-Reinf | Atividade por NCM/serviço ou pelo CNAE principal. Tipo de serviço e dados de processo para a Reinf, quando existe INSS retido. | manual EF p.394-399 |
| Estadual e Estadual II | Muitos incentivos de ICMS estaduais, entre eles créditos presumidos, ressarcimento de ST, estorno de crédito e crédito de energia. Também o município, o pedágio e o controle de CFOP por UF. | manual EF p.399-405 |
| CFOP/CFPS | Lista de CFOPs e CFPSs permitidos. Se marcada a opção de discriminar, o F2 do lançamento só oferece esses códigos. | manual EF p.405-407, 1053 |
| Contabilidade | Ver a seção 3. | manual EF p.407-414 |
| Municipais, I-SIMP | Tabelas municipais e dados de agente regulado. | manual EF p.414-417 |

**Conferência com o repositório.** `mapa-funcional-fiscal.md:321` cita as páginas 365-419 e está correto: o cadastro vai de 365 a 418, e o cadastro de Impostos começa na 419.

---

## 2. Como o acumulador entra no cálculo dos impostos

**2.1 O acumulador não calcula sozinho.** O cálculo tem três camadas (manual EF p.379, 421).

1. **Cadastro do imposto**, que a Domínio mantém e o usuário só altera.
   - O imposto tem competência (federal, estadual ou municipal), periodicidade e vigência própria (manual EF p.419-421).
   - O tipo pode ser *calculado*: o sistema apura sozinho com percentual de base e alíquota.
   - Pode ser *lançado por nota*: o usuário informa os valores no lançamento, e o cadastro escolhe quais campos pedir (base, alíquota, valor, isento, outros).
   - Pode ser *lançado por produto* (manual EF p.421-422).
   - Se o tipo do imposto muda, o sistema pergunta se a nova vigência vale também nos acumuladores que têm esse imposto (manual EF p.420-421).
2. **O acumulador escolhe quais impostos incidem** e pode sobrepor percentual de base, alíquota e redução (manual EF p.381-385).
3. **A nota.** Os impostos "lançados" do acumulador viram linhas na nota, já preenchidas e editáveis (manual EF p.1055).

**2.2 De onde vêm base e alíquota, por imposto:**
- **ICMS próprio.**
  - No lançamento de produtos, a alíquota vem do cadastro do produto, ou da alíquota lançada na nota quando o produto não a traz (manual EF p.1085).
  - A base nasce do valor do produto.
  - O acumulador pode impor alíquota, tabela interestadual e redução (manual EF p.384-385).
- **ICMS-ST e antecipação.**
  - Com convênio ou protocolo cadastrado, a base soma produto, frete, seguro, despesas, IPI e MVA, menos o desconto (manual EF p.1085-1087).
  - A alíquota é a interna do produto (manual EF p.1086-1087).
  - Os percentuais de MVA ficam no acumulador (manual EF p.387-388, 1054).
  - O cadastro do produto pode determinar o código de recolhimento (manual EF p.1087).
- **IPI.** Base igual ao valor do produto mais frete, seguro e despesas. Alíquota do produto, ou a lançada na nota. Existe cálculo por unidade de medida quando o produto o pede (manual EF p.1087-1088).
- **PIS e Cofins.** Dependem do regime e da forma de cálculo dos parâmetros (manual EF p.390; central https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=201).
  - Cumulativo e não cumulativo são impostos distintos, com códigos próprios no sistema (manual EF p.380).
  - *Lucro Presumido simplificado por nota*: a aba SPED é preenchida pelo acumulador (central codigo=201).
  - *Simplificado por produto*: é preciso mandar gerar a partir da movimentação de produtos (central codigo=201; manual EF p.1247).
  - *Lucro Real, e Presumido completo*: o acumulador só carrega CST, vínculo e base de crédito nos casos especiais (transporte, crédito presumido). No restante, o tratamento vem do produto (manual EF p.390-391; `mapa-funcional-fiscal.md:336-349`).
  - Monofásico e ST de PIS/Cofins aparecem como linhas por CST, com natureza da receita, nas saídas (manual EF p.392-393, 460).
- **ISS.**
  - O imposto "ISS" ou "ISS retido" no acumulador é o que liga o serviço ao tratamento. As deduções da LC 116 só habilitam com um desses dois (manual EF p.371).
  - Na importação, o sistema pode usar as definições de ISS do acumulador em vez das do XML (manual EF p.454, 679, 684).
- **Retenções federais** (PIS, Cofins, CSLL, IRRF, INSS).
  - Na importação de saída, a base é o valor dos produtos, a alíquota vem do cadastro do imposto e o valor vem do grupo de retenção do XML (manual IP p.139-141).
  - O COSIRF usa a alíquota do acumulador quando os impostos retidos estão marcados no acumulador (manual IP p.143).
- **Simples Nacional.**
  - O imposto "Simples Nacional" faz parte do acumulador e traz o tipo de receita, ou seja, anexo, seção e tabela.
  - Traz também a "situação fiscal" de cada tributo componente (tributado, redução e outras) e o percentual de redução de base para ICMS, ISS, PIS e Cofins (manual EF p.2089-2090).
  - Há um utilitário para incluir e configurar o Simples em todos os acumuladores de uma vez (manual EF p.2089).
  - O Anexo IV liga o acumulador ao INSS sobre receita bruta (manual EF p.1101, 1248).
  - No regime de caixa, cada parcela recebe um acumulador próprio (manual EF p.1252, 2092-2096).

**2.3 Quando a nota diverge do cálculo:**
- **No lançamento manual**, os campos nascem calculados mas são editáveis.
  - Se a soma de base, isentas, outras, IPI e ST ficar abaixo do valor contábil, o sistema avisa e oferece abrir outra linha do imposto com a diferença (manual EF p.1055-1056).
  - Alterar o valor contábil abre automaticamente uma linha com a diferença (manual EF p.1055).
- **Na importação de XML**, por padrão prevalece o que o XML traz para os impostos "lançados" (manual IP p.131-137).
  - O acumulador sobrepõe o XML só por opção explícita.
  - As opções são: usar base e alíquota de ICMS do acumulador, e usar as definições de IPI, ST e ISS do acumulador (manual EF p.454, 492).
  - Há também "ignorar impostos não definidos no acumulador" e "incluir IPI quando o acumulador o tem e a nota não" (manual EF p.492).
  - A central dá dois usos práticos. O primeiro é escriturar sem crédito, com base e alíquota zeradas (central codigo=786). O segundo é corrigir CT-e emitido sem destaque (central codigo=814).
  - O próprio texto da central adverte que, em muitos estados, o erro de CT-e deve ser corrigido com CT-e complementar, e não só por ajuste de escrituração.
- **Diferença entre valor contábil e base**: o acumulador manda para "isentas", "outras" ou nenhuma. Na importação, uma tabela por CST refina isso (manual EF p.383, 456-457, 495-496).
- **Troca de acumulador depois**: não recalcula impostos. A central afirma isso e manda usar o utilitário de alterar ICMS, ou reimportar (central codigo=653).

---

## 3. Como liga as regras contábeis

**Contas por acumulador** (manual EF p.407-414):
- Débito e crédito do valor da nota, com histórico padrão.
- Contas próprias de frete, seguro, despesas acessórias e pedágio.
- Par de contas "de compensação", se a opção estiver marcada.
- Baixa de parcelas: contas e históricos de pagamento/recebimento, juros, multa, outras, desconto e devolução.
- Ajuste a valor presente (AVP), com contas de provisão, juros e apropriação, se o parâmetro estiver ligado.
- Rateio por centro de custo e exibição obrigatória da tela de contabilização a cada lançamento (opções).

**Contas por imposto.**
- O cadastro do imposto tem as contas de a recolher e a recuperar, devoluções, compensação, ajustes, estorno de crédito, crédito presumido, diferido e valor suspenso (manual EF p.426-431).
- Ele escolhe se contabiliza por nota ou na apuração, e pode gerar provisão mensal de IRPJ/CSLL trimestrais (manual EF p.426).
- O acumulador pode ter, para impostos "lançados", uma aba própria de contas (a recolher, a recuperar, devolução, estorno) (manual EF p.385-386).

*Refinamento do que o repositório afirma.* `mapa-funcional-contabil.md` (seção "Integração fiscal → contábil") diz que as contas vêm de duas configurações: o acumulador e o cadastro do imposto. O manual confirma isso, mas mostra uma terceira camada, de menor alcance: as contas por imposto dentro do acumulador (manual EF p.385-386).

**Quando e como o lançamento nasce:**
- No lançamento da nota, a aba de contabilidade traz as linhas geradas, editáveis, com botão para regerar e para ratear (manual EF p.1253-1254).
- Na importação, "gerar lançamentos contábeis" é opção da configuração e só habilita se a empresa gera contabilidade (manual EF p.453, 489, 679, 684).
- A "Integração Contábil" é uma segunda etapa, no nível da apuração. Ela gera os lançamentos dos impostos do período, mostra data, conta de débito, conta de crédito e valor, e permite gerar para várias empresas. Pode bloquear refazer período já integrado, dependendo do parâmetro (manual EF p.1550-1552).
- O histórico é escolhido por código de histórico padrão. As variáveis de modelo ficam na configuração de históricos (manual EF p.335-365; `mapa-funcional-contabil.md`).

**Por empresa ou por padrão.** O manual lido não diz explicitamente que o acumulador é por empresa. A leitura é que ele é por empresa (*inferência*), por quatro indícios:
- o código no arquivo de importação TXT é "conforme cadastro da empresa" (leiaute `Leiaute Completo.pdf`, registros 4015 e outros);
- os impostos oferecidos vêm dos parâmetros da empresa (manual EF p.379);
- as opções do acumulador dependem de parâmetros da empresa;
- existe importação de cadastros e configurações de outra empresa, por perfil (manual EF p.2099-2101).

O manual não lista explicitamente os acumuladores nessa importação. *Não determinei se eles são copiáveis.*

---

## 4. Como a importação escolhe o acumulador

O cadastro de acumuladores é o mesmo; a escolha na importação é outra tabela de regras. Fica em "Configuração de Importação", uma por formato: NF-e portal, NF-e XML, NFC-e, CF-e, NFS-e (ABRASF e nacional), CT-e, BP-e, SPED, Sintegra, cupom e outros (manual EF p.447-961; manual IP índice, p.3-14).

**NF-e, NFC-e e CF-e: regra por linha.**
- Cada linha vincula um acumulador a um conjunto de critérios.
- Critérios de saída: operação (tag `indPag`, ou a forma de pagamento `tPag` na versão 4.0), CFOP, CST de ICMS, CST de PIS, origem, produto ou cliente (manual EF p.464-470, 542-550; central codigo=824).
- Critérios de entrada: os mesmos, mais fornecedor e, conforme a central, tipo de inscrição e regime do fornecedor (manual EF p.508-513; central codigo=922).
- O produto é identificado por código, NCM ou grupo, e o campo escolhido habilita a coluna correspondente (manual EF p.453, 491; central codigo=894).
- Há duplicação de linha, que copia critérios sem copiar o acumulador (manual EF p.470, 550).
- Há opção para permitir o mesmo CFOP em mais de um acumulador (manual EF p.453, 490).
- Há um acumulador de exceção para quando nenhuma linha casa (manual EF p.470, 550).
- Nota com mais de um CFOP é segmentada: uma por CFOP e por acumulador (manual IP p.125).
- Para a diferença à vista/a prazo no mesmo CFOP, a central mostra duas linhas, uma por CST e forma de pagamento. A marca de "considerar Todos como exceção" faz a linha específica valer sobre a genérica (central codigo=824 e 922; secundário https://www.contabeis.com.br/forum/tecnologia-contabil/232971/como-lancar-notas-de-saida-que-esta-dando-erro-no-cfop-5102/, tópico de 2016 com uma resposta).

*Não determinei* o algoritmo geral de precedência quando várias linhas casam. O texto da central é ambíguo. Só o exemplo à vista/a prazo está documentado.

**NFS-e (ABRASF).**
- Critérios: item de serviço, tipo de ISS (normal ou retido) e natureza da operação.
- Há acumulador de exceção, cliente ou produto padrão, e CFPS por origem do cliente (manual EF p.680-686).

**CT-e.** Critérios: operação, modalidade do frete, CFOP e CST, com acumulador de exceção (manual EF p.754-757).

**CFOP de entrada a partir do de saída.** Uma tabela à parte traduz o CFOP de saída do emissor no de entrada do destinatário (manual EF p.462-464, 507-508; central codigo=121).

**TXT com separador, e os leiautes de 2011.**
- O arquivo traz o código do acumulador em cada registro de nota (leiaute `Leiaute 6 - Notas fiscais de Entrada (19).pdf` e `Leiaute 7`, campo "Código do Acumulador"; manual IP p.1304, 1345 e seguintes).
- Aqui não há tabela de regras. O acumulador é decidido por quem gera o arquivo, e o importador só confere se o código existe.
- A importação de TXT pode usar o histórico do arquivo, o do lançamento padrão, ou ambos (manual IP p.1220).

**O que fica pendente.**
- Não há "fila de pendências" documentada. O que existe é o *Resumo dos dados*, ao fim de cada arquivo, em quatro frentes (manual IP p.106-112):
  - registros prontos;
  - advertências, que o usuário marca uma a uma para gravar;
  - erros, que não podem ser gravados;
  - críticas de estrutura, e produtos sem relacionamento.
- Sem acumulador compatível, o erro é "não foi encontrada relação de acumulador" (central codigo=121).
- As causas listadas pela central:
  - falta linha para a combinação de operação, forma de pagamento, CFOP e CST;
  - o XML do Simples traz CSOSN e a regra foi escrita com CST do regime normal;
  - a nota de entrada traz CFOP de saída sem conversão;
  - o XML veio de fonte não oficial.
- Existe conversão de CST/CSOSN na importação (central codigo=121).
- Dá para salvar os arquivos com erro ou advertência para reprocessar (manual IP p.106).

**Como o contador revisa e corrige em massa:**
- *Conferência de lançamentos*: marca lançamentos como conferidos, com filtro por movimento e período, mostrando acumulador e CFOP (manual EF p.2006-2008).
- *Alterar notas* (entradas, saídas, serviços): troca em massa de acumulador, série, espécie, CFOP, datas, CST e situação "cancelada" (manual EF p.2008-2013). Ao trocar o acumulador, o sistema mostra uma inconsistência se o destino tem configuração diferente, com relatório da diferença (central codigo=653).
- *Resumo por acumulador*: serve também para achar erro de acumulador (manual EF p.1635).
- *Reimportar* depois de corrigir a regra, que se aplica no momento da importação (manual IP p.107, botão "Reimportar"; *inferência* de que não reaplica retroativamente).

**Dois casos especiais:**
- *Duas empresas do mesmo escritório, uma vende para a outra.* A nota de saída pode gerar a nota de entrada na empresa compradora. Para isso marca-se o acumulador e a importação (manual EF p.374; central codigo=776).
- *Notas canceladas.* Usam CFOPs próprios por origem (estadual, interestadual, exterior) (manual EF p.452).

---

## 5. Vigência, manutenção e erros comuns

**Vigência.**
- O acumulador tem "Nova Vigência". Alterar campo com o período da empresa posterior ao início da vigência faz o sistema perguntar se leva o período de volta ao início da vigência (manual EF p.366-367).
- A central manda criar vigência nova do acumulador para o período quando a regra muda (central codigo=786, 814).
- O imposto também tem vigências, e a mudança pode ser propagada aos acumuladores que o contêm (manual EF p.420-421).
- Várias opções do acumulador só habilitam a partir de certa vigência, por exemplo a partir de 2014 em PIS/Cofins de entidades financeiras (manual EF p.394). A EFD-Reinf só a partir de 01/2017 (manual EF p.398).
- A configuração da importação, nos trechos lidos, não mostra vigência própria. *Não determinei* se ela é versionada.

**Se a regra muda.**
- Não há migração automática de notas já lançadas. Troca-se o acumulador em lote, o que não recalcula valores, ou reimporta-se (central codigo=653).
- O utilitário do Simples (manual EF p.2089) é o exemplo de ajuste em lote de um tratamento dentro dos acumuladores.

**Erros e atritos relatados (central e fórum):**
- falta de acumulador para a combinação do documento (central codigo=121);
- CSOSN contra CST (central codigo=121);
- acumulador à vista e a prazo para o mesmo CFOP (secundário, fórum de 2016);
- acumulador sem PIS/Cofins vinculado, o que desabilita a aba SPED (central codigo=201);
- troca de acumulador esperando que os impostos mudem junto (central codigo=653).

A frase "80% dos erros de apuração são acumulador errado", de `consultas/2026-10-08-contador-senior-fiscal.md:37`, é uma percepção registrada como prática naquela consulta. Não achei fonte que a confirme, e não a adoto como dado.

---

## 6. Relatórios e conferências que dependem do acumulador

- **Resumo por acumulador**: lançamentos de entradas, saídas e serviços por código, para achar erro de classificação (manual EF p.1635).
- **Resumo das operações por CFOP e alíquota**, por empresa (manual EF p.1636).
- **Notas não lançadas**: só saídas e serviços (manual EF p.1639).
- **Receita bruta global acumulada do Simples**, por ano (manual EF p.1635).
- **Demonstrativos de PIS/Cofins** ordenáveis e filtráveis por acumulador, CST, vínculo e base de crédito, natureza da receita e CFOP (manual EF p.1604-1608).
- **Conferência de lançamentos**, **integração contábil** e **apuração**, que lêem o que o acumulador classificou (manual EF p.1550-1552, 2006-2008).
- O "Incide sobre" decide se a nota entra em faturamento ou receita bruta (manual EF p.367).
- Não li o detalhe de cada livro fiscal. O índice está em `mapa-funcional-fiscal.md:305-314` (*inferência* de que os livros lêem as mesmas classificações).

---

## 7. Cruzamento com o DataLedger

**O que verifiquei no código:**
- Catálogos fechados de natureza em código:
  - NFS-e prestadas, `NaturezaOperacao`, `apps/fiscal/models.py:629`;
  - NFS-e tomadas, `NaturezaTomada`, `models.py:896`;
  - NF-e, `NaturezaOperacaoNFe`, `models.py:2639`.
- `CATALOGO_NATUREZA_NFE`, `models.py:2692`, traz papel, mercado, segregação, anexo e atividade de presunção (dataclass em `models.py:2659-2690`).
- A natureza da NF-e é por item (`NaturezaItemNFe`, `models.py:3269`) e nunca é gravada pela sugestão sozinha.
- Sugestão por CFOP/CST/NCM em `apps/fiscal/escrituracao_nfe.py:225-364`. Para tomadas, a sugestão sai de sinais do XML (`apps/fiscal/tomadas.py:430-468`).
- `reclassificar_em_massa` (`escrituracao_nfe.py:1118-1191`) só altera rascunho, com trilha por nota, e recusa a operação inteira se uma nota não aceitar a natureza.
- Lote de escrituração (`models.py:3316`; `escrituracao_nfe_lote.py:352`, grupos por CFOP, CST/CSOSN e natureza).
- Vigência existe para alíquota de ISS por escritório (`models.py:2028-2060`), regra de ISS por município (`models.py:1965`), atividade de presunção (`models.py:1668-1693`) e histórico de regime (`presumido.py:257-269`).
- Os valores de ICMS, IPI e ST do XML são usados só para conferir o total, com tolerância zero (`escrituracao_nfe.py:22-23, 836-883`).
- Não achei, no código não-teste do app fiscal, lançamento contábil de nota, plano de contas, nem cálculo de crédito de entrada. `mapa-funcional-fiscal.md:326, 331` já declara movimento fiscal e integração contábil como "não existe".

**Tabela final:**

| Função do acumulador | O que o DataLedger tem hoje | Lacuna |
| --- | --- | --- |
| Classificar o lançamento (a "natureza" da operação) | Natureza em catálogo fechado em código, por nota (NFS-e) ou por item (NF-e). Sugerida por CFOP/CST/NCM ou pelo XML, e confirmada pelo contador. | O escritório não cria nem edita naturezas. Sem código próprio nem inativação por data, e sem regra "esta combinação vai para esta natureza" configurável. |
| Regra da importação (critério → classificação) | Sugestão programada em código (`escrituracao_nfe.py`, `tomadas.py`). | Sem tabela de regras do escritório, sem critério por fornecedor, cliente, produto, forma de pagamento ou origem. Sem exceção configurável. Sem relatório de "não casou" como cadastro. |
| Escolher quais impostos incidem e como | Natureza com papel, mercado e segregação do Simples; ISS por município e subitem, com vigência. | Não há conjunto de impostos por natureza. Faltam ICMS próprio, ICMS-ST, IPI e PIS/Cofins como linhas geradas. |
| Base e alíquota (cálculo) | Receita da NF-e e alíquota de ISS; presumido e pré-DAS calculam. | O sistema lê o XML só para conferir total. Não há linhas por tributo da nota, nem base ou alíquota própria sobrepondo o XML, nem aviso de divergência por tributo. |
| PIS/Cofins (cumulativo, não cumulativo, monofásico) | Existe a natureza "monofasico", só para a segregação do Simples. | Sem CST, natureza da receita, vínculo e base de crédito. Sem regime não cumulativo ou crédito. |
| Crédito e impostos de entrada | Nenhum. As tomadas tratam ISS e retenções. | ICMS recuperável, IPI, PIS/Cofins de crédito, ST de entrada e DIFAL ficam fora. |
| Retenções | Retenções federais sobre NFS-e (DL-078). | Sem retenções sobre NF-e, nem COSIRF, INSS Reinf e FUNRURAL. |
| Simples (anexo e tipo de receita) | Anexo e segregação como informação da natureza; pré-DAS de serviços e de comércio/indústria. | O anexo é texto informativo, não parâmetro por regra. Sem situação fiscal por tributo ou percentual de redução por classificação. |
| Contas contábeis, históricos, integração | Nenhum no fiscal. | Todo o conjunto: contas por classificação, por imposto, frete, parcelas e AVP; geração de lançamento por nota; integração por período. |
| Vínculo por fornecedor, produto e cliente | Nenhum. | Falta tabela de regras com esses critérios. |
| Vigência da regra | Vigência em ISS, atividade de presunção e regime. | O catálogo de natureza não tem vigência. Sem "nova vigência" de classificação nem propagação para o que a usa. |
| Acumulador de exceção ("nada casou") | Nota sem natureza confirmada não efetiva. | Intencional e mais seguro. O sistema de referência cai num padrão; aqui o bloqueio é o desenho (`consultas/2026-10-08...:39`). |
| Correção em massa | `reclassificar_em_massa` só em rascunho, com trilha. Lote com prévia e assinatura (DL-085). | Sem correção de efetivada por procedimento rastreável nesta rotina; sem relatório de diferenças entre classificações. |
| Conferência por acumulador | Prévia do lote por grupo de CFOP, CST e natureza; consulta de NFS-e recebidas. | Sem resumo por classificação e por CFOP/alíquota do mês, sem "notas não lançadas", sem conferido/não conferido. |
| Efeitos em outros módulos | Sem integração com Patrimônio, SPED ou DMED. | Fora do escopo atual. |
| Vigência e escopo por empresa | Natureza global, regra ISS por escritório. | Nenhuma regra de classificação por empresa ou escritório, nem importação de configuração entre empresas. |

**Pontos que decorrem da pesquisa, para a decisão do arquiteto (inferência):**
- O sistema de referência junta, num cadastro só, natureza, regras de imposto, contas e regras de importação, e isso permite muita configuração e muita variação. O desenho do DataLedger, que separa natureza (escolha do contador) de regra (dado versionado), é mais auditável. Isso concorda com `consultas/2026-10-08-contador-senior-fiscal.md:33-39`.
- O que o sistema de referência prova ser necessário na prática de escritório: uma tabela de regras de importação por critérios (CFOP, CST, forma de pagamento, produto/NCM, fornecedor/cliente), com exceção e precedência declaradas, e uma lista de "o que não casou". Hoje as sugestões estão no código.

---

## O que não consegui determinar

- Se o acumulador é copiável entre empresas.
- O algoritmo exato de precedência entre linhas de importação.
- Se a configuração de importação tem vigência.
- Se alterar a regra de importação afeta notas já lançadas (leitura: não).
- O comportamento atual do produto. O manual é de 2018 e os artigos da central são recentes, mas não têm data visível no corpo lido.
- Nada aqui é norma. Alíquotas, CSTs e regras tributárias que o manual cita precisam de fonte oficial vigente antes de virar requisito.

---

## Fontes abertas

**Manual, Domínio Sistemas** (baixado em 09/10/2026 de `https://ftpdownload.dominiosistemas.com.br/manuais/`):
- `Domínio Escrita Fiscal.pdf` (2.324 páginas): p. 335-365, 365-419, 419-431, 447-513, 524-550, 675-686, 749-757, 1036, 1052-1062, 1084-1089, 1101, 1118, 1247-1254, 1550-1553, 1604-1608, 1635-1639, 2006-2013, 2089-2101.
- `Importação Padrão.pdf` (1.495 páginas): p. 3-4 (índice), 104-115, 125-144, 1217-1220, 1304-1345.
- `leiautes.zip`: `Leiaute 6 - Notas fiscais de Entrada (19).pdf`, `Leiaute 7 - Notas fiscais de Saída (19).pdf`, `Leiaute Completo.pdf`.

**Central de Soluções, Domínio/Thomson Reuters** (leitura de 09/10/2026 por curl):
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=121
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=201
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=653
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=776
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=786
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=814
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=824
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=894
- https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=922

Os códigos 765, 859, 921 e 823 apareceram na busca, mas eu não os abri.

**Secundário:** https://www.contabeis.com.br/forum/tecnologia-contabil/232971/como-lancar-notas-de-saida-que-esta-dando-erro-no-cfop-5102/ (WebFetch em 09/10/2026; tópico de 2016, uma resposta).

**Repositório:**
- `/home/user/DataLedger/docs/projeto/fontes-de-referencia.md`
- `/home/user/DataLedger/docs/projeto/mapa-funcional-fiscal.md`
- `/home/user/DataLedger/docs/projeto/mapa-funcional-contabil.md`
- `/home/user/DataLedger/docs/projeto/consultas/2026-10-08-contador-senior-fiscal.md`
- `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md`
- `/home/user/DataLedger/docs/projeto/requisitos.md` (RC-175)
- `/home/user/DataLedger/apps/fiscal/models.py`
- `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py`
- `/home/user/DataLedger/apps/fiscal/escrituracao_nfe_lote.py`
- `/home/user/DataLedger/apps/fiscal/tomadas.py`
