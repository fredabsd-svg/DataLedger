# DL-010 — Recepção de documentos fiscais

Primeira fatia do módulo Fiscal, escolhida pelo Fred: **importação e
conferência** é a rotina que mais consome tempo no escritório (RC-40).

**Estado:** planejada.

## Objetivo

Receber documentos fiscais de fontes que o escritório **já usa hoje**, sem
exigir que ele mude a ferramenta de captura, e entregar a base sobre a qual a
conferência será construída.

## As três fontes, e por que cada uma existe

O Fred confirmou que o escritório recebe os documentos de um **sistema de gestão
de XML** de terceiros (RC-41), que **exporta XML puro e também zipado** (RC-47),
e pediu também importação em **formato SPED Fiscal** (RC-44).

| Fonte | O que é | Papel |
| --- | --- | --- |
| **XML de NF-e** | O documento como foi emitido e autorizado | **Primária.** Fonte da verdade, padrão público de governo |
| **SPED Fiscal (EFD ICMS/IPI)** | O período **já escriturado**, como foi transmitido | **Migração e conferência.** Ver abaixo |
| Formato de intercâmbio de terceiros | Arquivo texto do sistema atual | Caminho de adoção — decisão pendente do Fred |

### Por que o SPED Fiscal vale mais do que parece

Importar SPED Fiscal **não é só mais um formato de entrada**. É o mecanismo de
**migração e comparação**:

> O escritório exporta o SPED do sistema atual, importa no DataLedger, e
> **compara período a período**. Onde os dois divergem, há algo a investigar —
> no sistema novo, no antigo, ou no entendimento da regra.

Essa é a única forma responsável de trocar um sistema contábil: **conferindo,
não confiando**. E ela permite rodar os dois em paralelo durante o tempo que for
necessário, sem risco para o escritório.

Vale registrar a diferença de natureza entre as duas fontes principais:

- O **XML** traz o documento como emitido. É matéria-prima.
- O **SPED** traz o documento **já classificado e apurado** pelo sistema de
  origem, incluindo CFOP, CST e valores de base e imposto. É resultado.

Comparar os dois é, por si só, uma conferência valiosa.

## Fontes oficiais — obtidas, não presumidas

| Assunto | Fonte |
| --- | --- |
| EFD ICMS/IPI | **Guia Prático versão 3.2.3**, atualização de 06/05/2026, do Portal SPED |
| Base legal do leiaute | **Ato COTEPE/ICMS nº 44**, de 07/08/2018, e alterações |
| Alterações futuras | **Nota Técnica EFD ICMS IPI nº 2026.001**, com efeitos a partir de **01/01/2027** |
| NF-e | Pacote de esquemas e Manual de Orientação do Contribuinte, do [Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br) |

Blocos da EFD ICMS/IPI, conforme o guia oficial: `0` abertura e identificação,
`B` ISS, `C` documentos de mercadorias (ICMS/IPI), `D` serviços, `E` apuração de
ICMS e IPI, `G` CIAP, `H` inventário, `K` produção e estoque, `1` outras
informações, `9` encerramento.

Para **receber notas**, o alvo é o **bloco C**. Os demais blocos ficam fora
desta etapa.

## Duas restrições reais, levantadas antes de planejar

### 1. CNPJ alfanumérico — resolvido na DL-011, mas a consequência de projeto fica

Desde **31/07/2026** (IN RFB nº 2.229), o CNPJ pode conter letras. Quando esta
etapa foi planejada, o validador descartava letras e **recusava** qualquer CNPJ
alfanumérico — defeito em vigor, não hipotético.

**Resolvido pela [DL-011](DL-011-cnpj-alfanumerico.md)**, que fechou o BL-46.

A consequência de projeto **permanece**, e por outro motivo: a empresa do
documento é identificada por CNPJ, e a chave de acesso da NF-e contém o CNPJ do
emitente. A identificação por CNPJ fica **isolada num único ponto**, para que
qualquer mudança futura na regra do CNPJ entre em um lugar só e valha para todos
os caminhos de importação.

### 2. RAR saiu do escopo — resolvido pela origem, não por limitação nossa

`zipfile` é nativo em Python. **RAR é formato proprietário** e exigiria binário
externo, que não existe neste ambiente (verificado: sem `unrar`, `unar`, `7z`
ou `bsdtar`), com licença própria e mais uma peça para manter.

**Resolvido em 2026-09-12 (RC-47):** o Fred confirmou que o sistema de gestão de
XML **exporta XML puro e também zipado**. O RAR, portanto, **não é necessário**.

Esta é a forma mais barata de resolver uma dependência: descobrir que ela não é
preciso. **Escopo: XML solto e ZIP.**

## Escopo desta etapa

**Dentro:**

- Receber arquivo: XML solto, vários XMLs, ou ZIP contendo XMLs.
- Receber arquivo SPED Fiscal e extrair os documentos do **bloco C**.
- Identificar a **empresa** do documento pelo CNPJ, dentro do escritório ativo.
- Persistir o documento com **rastreabilidade até o arquivo de origem**.
- **Idempotência pela chave de acesso.**
- **Isolamento**: documento de CNPJ que não pertence a nenhuma empresa do
  escritório é recusado, com motivo, e nunca gravado.
- Relatório do que foi recebido, duplicado, recusado e por quê.

**Fora, declarado:**

- Apuração de qualquer imposto.
- Classificação fiscal e o cadastro de regras por vigência.
- Livros e obrigações acessórias.
- Blocos da EFD além do `C`.
- Segmentos especializados (RC-42), que afetam apuração, não recepção.
- RAR.

## Decisão de domínio: aqui a chave natural é correta

Registro deliberado, porque **contraria** a decisão DE-009 tomada para
lançamentos manuais — e a diferença importa.

Em DE-009 recusamos deduplicar lançamento por semelhança, porque **dois
lançamentos idênticos podem ser legítimos**. Aqui é o oposto:

> A **chave de acesso** da NF-e tem 44 posições e identifica **um** documento.
> Dois arquivos com a mesma chave **são o mesmo documento**, sempre.

**Correção de 2026-09-12, depois da pesquisa do leiaute do SPED:** a frase acima
vale para o **documento eletrônico**. Nota modelo 1/1A, nota de produtor e cupom
fiscal **não têm chave**, e chegam assim pelo SPED. A regra continua correta no
que afirma; o que faltava era dizer **a que documentos ela se aplica**. Ver
PE-22.

Portanto, para documento fiscal, **deduplicar pela chave é correto e
obrigatório** — é o que permite reimportar o mesmo ZIP sem duplicar
escrituração, que é o comportamento que o escritório precisa.

A regra geral que concilia as duas decisões: **deduplica-se por identificador
emitido por terceiro confiável, nunca por semelhança de conteúdo.**

## Critérios de aceite

| # | Critério |
| --- | --- |
| 1 | XML de NF-e válido é recebido e persistido, com rastreio ao arquivo de origem |
| 2 | ZIP com vários XMLs é processado, e o relatório informa cada um |
| 3 | **Reimportar o mesmo arquivo não duplica** nenhum documento |
| 4 | Reimportar o mesmo XML dentro de outro ZIP também não duplica |
| 5 | Documento cujo CNPJ não pertence a nenhuma empresa do escritório é **recusado**, com motivo, e não gravado |
| 5a | Documento **sem bloco `dest`** é tratado como caso próprio, com motivo distinto de "CNPJ não reconhecido" — nunca como XML malformado |
| 5b | Arquivo de **evento** (`envEvento` ou `procEventoNFe`) é reconhecido pelo elemento raiz, relatado com o tipo e a chave que referencia, e **não** tratado como nota |
| 5c | XML de NF-e em **leiaute anterior ao 4.00** é recusado com mensagem específica, não com erro genérico de esquema |
| 6 | Documento de empresa de **outro escritório** nunca é acessível nem importável |
| 7 | XML malformado, truncado ou que não seja NF-e é recusado com mensagem útil, sem derrubar o lote |
| 8 | Um arquivo ruim no meio do ZIP **não impede** os demais de serem importados |
| 9 | Arquivo SPED Fiscal é lido em **ISO-8859-1** e os documentos do bloco C são extraídos |
| 9a | A integridade do arquivo é conferida pelas contagens de `9900`, `9990`, `9999` e `C990` **antes** de importar; arquivo com contagem divergente é recusado por inteiro |
| 9b | `C100` **sem** `C170` e `C190` — cancelado, denegado, inutilizado — é lido sem erro e classificado pelo `COD_SIT`, nunca tratado como arquivo malformado |
| 9c | `C100` de modelo **não eletrônico**, sem `CHV_NFE`, é lido e relatado; o tratamento de duplicidade desses documentos segue a decisão de **PE-22**, e não é silencioso |
| 10 | Valores monetários entram por `Decimal`, pela política da DE-010, sem ponto flutuante |
| 11 | O relatório distingue: recebido, duplicado ignorado, recusado com motivo |
| 12 | Toda importação gera registro na trilha de auditoria, sem expor conteúdo sensível |
| 13 | A identificação de empresa por CNPJ está em **um único ponto** do código |
| 14 | Sem regressão; `ruff`, `format --check`, `manage.py check`, `makemigrations --check` limpos |

## Impacto

- **Dados:** cria persistência nova. Migração aditiva.
- **Isolamento:** é o ponto mais sensível. Importar documento para a empresa
  errada é pior que não importar — por isso o critério 5 recusa em vez de
  adivinhar.
- **Desempenho:** lote pode ter milhares de XMLs. A importação deve ser
  resiliente a arquivo ruim e informar progresso.
- **Reversão:** a migração é reversível; documentos importados podem ser
  removidos por lote de importação.

## Leiaute da NF-e — levantado em fonte oficial, não presumido

Levantamento de 2026-09-12 pelo `auxiliar-pesquisa`, contra o **Manual de
Orientação do Contribuinte versão 7.0** (novembro de 2020) e contra os
**esquemas XSD oficiais** do Portal Nacional da NF-e: pacote base `PL_009`
(15/03/2019) e **pacote vigente `PL_010f`, de 31/08/2026**.

### O que está confirmado

- **Namespace único, que não varia por versão:**
  `http://www.portalfiscal.inf.br/nfe`. O manual veda declaração diferente e
  veda prefixo.
- **Três raízes distintas, no mesmo namespace**, e a diferença importa:

  | Raiz | O que é |
  | --- | --- |
  | `nfeProc` | A nota **com** o protocolo de autorização. É o formato de distribuição — o que o escritório normalmente recebe. |
  | `NFe` | A nota isolada, **sem** protocolo. Gerada e ainda não autorizada, ou salva antes disso. |
  | `enviNFe` | Lote de **envio à SEFAZ**. É mensagem de submissão, não de distribuição. |

- **Caminhos dos campos de identificação**, confirmados no XSD:

  | Campo | Caminho a partir de `nfeProc` |
  | --- | --- |
  | Chave de acesso | atributo `Id` de `NFe/infNFe`, com prefixo `NFe`; repetida em `protNFe/infProt/chNFe` |
  | CNPJ do emitente | `NFe/infNFe/emit/CNPJ` (ou `CPF`, desde o leiaute 4.00) |
  | Destinatário | `NFe/infNFe/dest/CNPJ`, `dest/CPF` ou `dest/idEstrangeiro` |
  | Número, série, modelo | `NFe/infNFe/ide/nNF`, `ide/serie`, `ide/mod` (`55` ou `65`) |
  | Data de emissão | `NFe/infNFe/ide/dhEmi` |
  | Valor total | `NFe/infNFe/total/ICMSTot/vNF` |
  | Autorização | `protNFe/infProt/cStat` (`100` = autorizado), com `xMotivo`, `nProt`, `dhRecbto` |

- **NFC-e (modelo 65) usa o mesmo esquema** da NF-e (modelo 55). Diferenças na
  recepção: costuma não ter destinatário identificado, traz o bloco
  `infNFeSupl/qrCode`, e por norma só admite dois eventos.
- **Codificação oficial: UTF-8**, com declaração única por arquivo.
- **A chave de acesso registrada na DL-011 confere com a fonte oficial** —
  composição das 44 posições, regra do dígito verificador e expressão regular
  `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`. A fraseologia do manual (`resto` 0 ou 1 → DV
  igual a zero) é matematicamente equivalente à que registramos. **Nada a
  corrigir.**

### Cinco armadilhas que mudam o desenho desta etapa

Estas não estavam no plano e teriam custado uma rodada de auditoria cada.

**1. O bloco `dest` é opcional no esquema.** Importador que trate destinatário
ausente como XML malformado **recusa nota legítima**. O critério 5 precisa
distinguir dois casos que hoje trata como um: *CNPJ do destinatário não
pertence a nenhuma empresa do escritório* é diferente de *não há destinatário
no documento*.

**2. Evento não é nota, e compartilha o mesmo namespace.** Cancelamento
(`110111`), carta de correção (`110110`) e as quatro manifestações do
destinatário (`210200`, `210210`, `210220`, `210240`) vêm com raiz `envEvento`
ou `procEventoNFe`, referenciando a nota por `chNFe`. Reconhecer "é NF-e"
apenas porque o namespace bate faz o importador tratar um cancelamento como
nota e falhar de forma confusa. **O reconhecimento tem de ser pelo elemento
raiz.**

**3. O texto do manual e o esquema vigente já divergem entre si.** O MOC 7.0, de
2020, ainda descreve a chave como "44 caracteres numéricos". O XSD do pacote de
31/08/2026 já aceita letra nas posições do CNPJ. Quem implementar lendo só a
prosa do manual erra. **Para formato, o XSD vigente é a fonte; o texto do manual
é contexto.**

**4. O leiaute evoluiu sem trocar o namespace.** Arquivo histórico do escritório
pode vir em leiaute 3.10 ou anterior, com namespace idêntico e estrutura
diferente — inclusive na montagem da chave. Precisa haver decisão explícita:
aceitar só a versão 4.00 e **recusar as demais com mensagem específica**, em vez
de estourar com erro genérico de esquema.

**5. A mais séria: cancelar não altera o XML da nota.** Uma nota cancelada
continua com `cStat=100` no seu próprio arquivo. O cancelamento vive num evento
**separado**, que pode nunca ter sido arquivado pelo escritório.

> **Consequência que precisa estar declarada:** recepção de nota **sem** os
> eventos correspondentes **não reflete a situação jurídica atual do
> documento**. Uma nota cancelada, recebida sem o evento de cancelamento,
> aparece como válida.

Isso não é defeito a corrigir nesta etapa — é limite a declarar. E é o que torna
a conferência contra o SPED valiosa: o SPED traz a situação do documento
**depois** de tudo que aconteceu com ele.

## Leiaute do SPED Fiscal — levantado em fonte oficial

Levantamento de 2026-09-12 pelo `auxiliar-pesquisa`, contra o **Guia Prático
EFD-ICMS/IPI versão 3.2.3**, de 06/05/2026, e contra a **NT EFD ICMS IPI
2024.001 v1.0**, que instituiu o leiaute vigente desde 01/01/2025.

### Formato físico, confirmado

| Item | Valor |
| --- | --- |
| Codificação | **ISO-8859-1 (Latin-1)** — **não é UTF-8** |
| Separador de campo | `\|` (pipe, ASCII 124) |
| Início e fim da linha | A linha **começa e termina** com pipe |
| Terminador de registro | CR + LF |
| Campo vazio | Dois pipes adjacentes, `\|\|` |
| Decimal | Vírgula, sem separador de milhar, sem sinal |
| Data | `ddmmaaaa`, sem separador |

### Registros do bloco C que interessam à recepção

`C001` abre o bloco. `C100` é o documento, com 29 campos — dos quais importam à
recepção: `IND_OPER` (entrada ou saída), `IND_EMIT` (emissão própria ou de
terceiros), `COD_PART`, `COD_MOD`, `COD_SIT`, `SER`, `NUM_DOC`, `CHV_NFE`,
`DT_DOC`, `DT_E_S` e `VL_DOC`. `C170` é o item, `C190` o registro analítico, e
`C990` encerra o bloco com a contagem de linhas.

O bloco `9` permite **validar a integridade do arquivo antes de importar**:
`9900` traz a contagem de cada tipo de registro, `9990` o total do bloco 9 e
`9999` o total do arquivo. Conferir essas contagens contra a contagem real é a
mesma lógica que o validador oficial aplica.

### Quatro achados que corrigem o plano

**1. O arquivo não é UTF-8.** Abrir com a codificação padrão do Python falha em
qualquer razão social com acento. Tem de ser explícito no importador.

**2. A decisão de domínio desta etapa estava incompleta — e o erro é meu.**

O plano afirma, em "Decisão de domínio", que a chave de acesso identifica um
documento **sempre**. Isso vale para o subconjunto eletrônico. Mas:

> `CHV_NFE` **só existe** para `COD_MOD` `55` (NF-e) e `65` (NFC-e). Nota
> modelo 1/1A, nota de produtor e cupom fiscal **não têm chave de 44 posições**.

Se o escritório escriturava documento não eletrônico no sistema antigo, o SPED
desses períodos chega **sem chave**, e a idempotência da etapa não tem em que se
apoiar. Registrado como **PE-22**: não pode virar "fora do escopo" silencioso.

**3. Documento cancelado, denegado ou inutilizado aparece no arquivo com o
`C100` quase vazio e sem `C170` nem `C190`.** Não é erro do arquivo, é regra do
leiaute. Parser que exija ao menos um item por documento quebra nos casos que
são normais e frequentes. Os códigos de `COD_SIT` que importam: `00` regular,
`01` extemporâneo, `02` e `03` cancelado, `06` e `07` complementar, `08` regime
especial. `04` e `05` estão descontinuados desde janeiro de 2023. `09` e `10`
entram em **01/01/2027**, pela Reforma Tributária.

**4. Isto limita a promessa de comparar SPED com XML.** Para nota eletrônica de
emissão própria, a regra geral exige apenas `C100` e `C190` — o detalhe de item
(`C170`) **muitas vezes não está no arquivo**, porque a unidade federativa não
exige. Comparar e encontrar "item faltando no SPED" **não é divergência**; é
ausência por desenho do leiaute. Quem construir a conferência precisa saber
disso, ou vai produzir uma lista de falsas divergências.

Uma observação menor, registrada por honestidade: o próprio Guia Prático se
contradiz quanto à data do Ato COTEPE nº 44 — cita 07/08/2018 num ponto e
08/08/2018 em outro. Adotamos **07/08/2018**, que é o que consta em fontes
externas, e registramos a divergência em vez de escolher em silêncio.

## Restrição herdada da DL-011 que precisa estar à vista

A [DE-013](../projeto/decisoes.md) estreitou a aceitação de máscara de CNPJ:
`normalizar_cnpj` reconhece **apenas** o leiaute exato `XX.XXX.XXX/XXXX-XX`.

Consequência direta para esta etapa: arquivo de terceiro que traga CNPJ com
separação parcial — por exemplo `11222333/0001-81` — **será recusado**.

O importador **não deve** presumir tolerância a pontuação arbitrária. Se uma
origem real usar separação parcial, isso é decisão nova: normalizar na borda do
importador, com teste próprio, ou ampliar a DE-013 com justificativa. O que não
pode é ser resolvido em silêncio dentro do validador.

## Pendências

| # | Pendência | Situação |
| --- | --- | --- |
| 1 | Algoritmo oficial do DV do CNPJ alfanumérico (**BL-46**) | **Resolvida.** NT 2025.001 obtida; [DL-011](DL-011-cnpj-alfanumerico.md) em revisão. |
| 2 | Origem pode exportar **ZIP** em vez de RAR? | **Resolvida** (RC-47): exporta XML puro e zipado. RAR fora do escopo. |
| 3 | Amostra real de **SPED Fiscal** e lote de **XML** (PE-17) | **Em atendimento.** O Fred está preparando. Até chegarem, os casos saem do leiaute oficial e de amostras sintéticas escritas por nós. |
| 4 | Decisão sobre o formato de intercâmbio de terceiros (PE-18) | Aberta. Não bloqueia: o XML é a fonte primária. |
| 5 | Quais **segmentos especializados** existem na carteira (PE-13/RC-42) | Aberta. Afeta apuração, não recepção. |

### Por que a falta da amostra real não para a etapa, mas limita o que posso afirmar

O leiaute oficial define o que é **válido**. A amostra real mostra o que
**aparece**: campo opcional que a origem sempre preenche, campo obrigatório que
vem vazio, codificação de caractere, quebra de linha, acento em razão social,
XML com assinatura, XML de cancelamento e de carta de correção no meio do lote.

Dá para construir a recepção sem a amostra. **Não** dá para afirmar que ela
aguenta o lote do escritório antes de ter rodado contra um lote do escritório.
Isso ficará declarado no relatório da etapa, não escondido.

## Divisão de responsabilidade

| Agente | Arquivos |
| --- | --- |
| `arquiteto-senior` | `docs/**` |
| `desenvolvedor-pleno` | `apps/fiscal/**` (novo), `config/settings.py` |
| `especialista-frontend` | telas de importação e relatório, em etapa própria |
| `auditor-qa` | nenhum (somente leitura) |
