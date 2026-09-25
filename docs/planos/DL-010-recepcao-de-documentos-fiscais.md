# DL-010 — Recepção de documentos fiscais

Primeira fatia do módulo Fiscal, escolhida pelo Fred: **importação e
conferência** é a rotina que mais consome tempo no escritório (RC-40).

**Estado:** **revisado em 2026-09-14 pelo acervo real do escritório.** O Fred
confirmou o foco: *"foca na importação e conferência"*.

> ## Revisão de prioridade — o plano estava com a ordem invertida
>
> Este plano foi escrito a partir de manual e conversa, e priorizava **NF-e e
> SPED**. Em 2026-09-14 o Fred enviou **5.850 XMLs** do acervo, e a medição
> desmentiu a suposição:
>
> | Documento | Quantidade | Participação |
> | --- | --- | --- |
> | **NFS-e nacional** (serviço prestado, RC-66) | 4.979 | **85%** |
> | NF-e modelo 55 | 618 — **611 de saída** | 11% |
> | NFCom 62, CT-e 57, GTVe 64 | 79 | 1% |
>
> Seguir o plano original seria construir primeiro exatamente a parte que menos
> aparece na carteira dele. **A primeira fatia passa a ser a NFS-e nacional.**
>
> O levantamento de leiaute de NF-e e de SPED, mais abaixo, **continua válido e
> não foi descartado** — muda a ordem em que é usado, não o conteúdo.

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

Reorganizado em 2026-09-14 pela medição do acervo.

**Fatia 1 — o que o escritório mais recebe:**

- Receber arquivo: XML solto, vários XMLs, ou ZIP contendo XMLs.
- **NFS-e nacional**, versões `1.00` e `1.01` (RC-72), que é 85% do movimento.
- **Classificação pelo conteúdo do documento**, nunca pelo nome do arquivo ou
  pasta (RC-71).
- **Deduplicação pelo identificador do documento** (RC-69, RC-74).
- **Eventos, inclusive órfãos** — guardados mesmo sem a nota correspondente, e
  aplicados quando ela chegar (RC-70).
- Identificar a **empresa** pelo CNPJ **ou CPF** (RC-73), dentro do escritório
  ativo.
- **Isolamento**: documento que não pertence a nenhuma empresa do escritório é
  recusado, com motivo, e nunca gravado.
- **Conferência**: o que entrou, o que já existia, o que foi recusado e por quê,
  o que está cancelado, e o que chegou sem par.

**Fatia 2, com o leiaute já levantado neste plano:** NF-e modelo 55.

**Fatia 3, quando houver demanda medida:** NFCom, CT-e, GTVe — juntos são 1% do
acervo, e o NFCom vem de **um único emitente**.

**Fora, declarado:**

- **SPED Fiscal** — sai da primeira fatia. O leiaute está levantado aqui, mas o
  Fred ainda não forneceu arquivo, e a medição mostra que o volume está na
  NFS-e. Volta quando houver amostra.
- Apuração de qualquer imposto.
- Classificação fiscal e cadastro de regras por vigência.
- Contabilização automática (é a integração fiscal-contábil, ver
  [mapa contábil](../projeto/mapa-funcional-contabil.md)).
- Livros e obrigações acessórias.
- Segmentos especializados (RC-42), que afetam apuração, não recepção.
- **Bloco IBS/CBS** enquanto **PE-39** não for decidido pelo Fred: 12% das notas
  já o trazem (RC-76), e recepcionar sem ele descarta informação que chegou —
  mas o leiaute e a regra precisam de fonte oficial vigente, que não levantei.

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

Reescritos em 2026-09-14. Os de 1 a 14 valiam antes e continuam valendo, com a
NFS-e no lugar da NF-e onde couber; de 15 a 22 vêm da medição do acervo real e
**cada um tem um número medido por trás**.

| # | Critério |
| --- | --- |
| 1 | XML de NFS-e válido é recebido e persistido, com rastreio ao arquivo de origem |
| 2 | ZIP com vários XMLs é processado, e o relatório informa cada um |
| 3 | **Reimportar o mesmo arquivo não duplica** nenhum documento |
| 4 | Reimportar o mesmo XML dentro de outro ZIP também não duplica |
| 5 | Documento cujo CNPJ/CPF não pertence a nenhuma empresa do escritório é **recusado**, com motivo, e não gravado |
| 6 | Documento de empresa de **outro escritório** nunca é acessível nem importável |
| 7 | XML malformado, truncado ou de tipo não suportado é recusado com mensagem útil, sem derrubar o lote |
| 8 | Um arquivo ruim no meio do ZIP **não impede** os demais de serem importados |
| 10 | Valores monetários entram por `Decimal`, pela política da DE-010, sem ponto flutuante |
| 11 | O relatório distingue: recebido, duplicado ignorado, recusado com motivo |
| 12 | Toda importação gera registro na trilha de auditoria, sem expor conteúdo sensível |
| 13 | A identificação de empresa por CNPJ/CPF está em **um único ponto** do código |
| 14 | Sem regressão; `ruff`, `format --check`, `manage.py check`, `makemigrations --check` limpos, **verificados em árvore limpa** (BL-81) |
| **15** | **Deduplicação pelo identificador do documento** (`Id` de `infNFSe`, `NFS` + 50 dígitos, RC-74) — **nunca** por nome de arquivo ou caminho. Teste com os dois casos reais medidos: o mesmo documento em **duas pastas de clientes diferentes**, e o mesmo documento **duas vezes na mesma pasta** (RC-69) |
| **16** | O número sequencial (`nNFSe`/`nDFSe`) **não** é usado como chave: varia de 1 a 13 dígitos sem padronização (RC-74). Teste que prove que dois documentos de emitentes distintos com o mesmo número **coexistem** |
| **17** | **Evento órfão é aceito e guardado** (RC-70), e aplicado à nota quando ela chegar depois. Teste nas duas ordens: evento antes da nota, e nota antes do evento. Nota cancelada **nunca** é apresentada como válida |
| **18** | **Classificação pelo conteúdo** (RC-71). Teste com o caso real: documento cujo nome de arquivo diz `evento` e cujo conteúdo é outro tipo — o sistema acerta pelo conteúdo |
| **19** | **As duas versões de leiaute** da NFS-e (`1.00` e `1.01`, RC-72) são aceitas. Teste com uma de cada |
| **20** | **CPF em qualquer papel** — prestador ou tomador pessoa física (RC-73) — é aceito. Teste com CPF no emitente e no tomador |
| **21** | **Variações de arquivo** (RC-75) não quebram a leitura: sem declaração de codificação, `UTF-8` maiúsculo e minúsculo, CRLF, minificado e indentado. Teste para cada, e um caso com **acentuação em razão social** provando que não corrompe |
| **22** | **CNPJ com zero à esquerda** é preservado (553 casos reais, RC-75). Teste que prove que o identificador nunca passa por conversão numérica |

### O que estes critérios protegem, em linguagem de escritório

O critério 15 evita **escriturar a mesma receita duas vezes**. O 17 evita
**escriturar nota cancelada como válida** — e, como os 29 cancelamentos do
acervo chegaram sem a nota, é o caso normal, não a exceção. O 21 e o 22 evitam
razão social corrompida e CNPJ mutilado, que são os defeitos que aparecem no
primeiro dia de uso e destroem a confiança no sistema.

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

## ⚠️ ABERTURA DA ETAPA — autorização do Fred em 2026-09-25: *"pode seguir com a escrita fiscal"*

Este plano estava escrito e **medido contra 5.850 XMLs reais** desde 2026-09-14,
e ficou parado esperando prioridade. A prioridade veio. **O que muda daqui para
frente é a execução, não o escopo** — os 22 critérios acima continuam valendo.

### O que mudou no projeto desde que este plano foi escrito, e afeta a execução

| Então | Agora |
| --- | --- |
| **Competência não existia** (BL-15) e era o passo 1 da ordem técnica | **Pronta e auditada** (DL-016 + DL-031). O primeiro passo já está pago |
| A contabilidade tinha Diário, Razão e Balancete | Tem também **Balanço Patrimonial**, camada de saldos e classificação patrimonial (DL-032 a DL-035) |
| Nenhum documento imprimível tinha guarda de identificação medida | O instrumento mede **por página, no navegador real** (DL-035/BL-501) |

### ⚠️ O acervo real NÃO está mais neste ambiente, e isso MUDA a forma de testar

O contêiner é efêmero: os 5.850 XMLs que produziram RC-66 a RC-76 **não estão
aqui**. Isso não é perda — é o comportamento correto, e a regra do projeto já
exigia o mesmo resultado:

⚠️ **Toda fixture é XML SINTÉTICO, construído para reproduzir a característica
medida.** Nenhum arquivo de cliente entra no repositório, em nenhuma
circunstância. Os critérios 15 a 22 continuam obrigatórios: o que eles exigem é
**o comportamento diante da característica**, não a posse do arquivo original.

Exemplo do que isso significa na prática: o critério 22 exige provar que **CNPJ
com zero à esquerda** é preservado. A fixture é um CNPJ sintético começando com
`0`; os 553 casos reais são a **justificativa** do teste, não o seu insumo.

### Decisão nova, e ela dissolve a PE-39: [DE-074](../projeto/decisoes.md#de-074)

**O XML original é guardado íntegro; os campos lidos são projeção derivada dele.**

A PE-39 perguntava se o bloco de **IBS/CBS** (12% das notas, RC-76) entra no
escopo agora ou depois — e **as duas respostas erravam**: interpretar exige
leiaute oficial que não temos confirmado; não recepcionar descarta informação que
já chega hoje. Guardando o original, **nada se perde** e a interpretação do bloco
vira etapa futura que lê o que já está no banco.

⚠️ **E o custo fica declarado:** o original contém **dado real de cliente**. Mesmo
isolamento por empresa de qualquer outro dado; **nunca** em log, em mensagem de
erro, na trilha ou em teste; entra no plano de backup; e cresce com o volume.

### Sequência de execução, e por que NÃO em paralelo

| Ordem | Frente | Responsável |
| --- | --- | --- |
| **1** | **Leiaute oficial da NFS-e nacional** — fonte, namespace, elemento raiz por tipo, caminhos dos campos, versões vigentes, eventos, IBS/CBS, e a diferença entre **padrão nacional e padrão municipal** | `auxiliar-pesquisa` (somente leitura) |
| **2** | **Servidor:** app `fiscal` novo, persistência, importador, deduplicação, eventos órfãos, relatório de conferência **como estrutura de dados**, e os testes dos 22 critérios | `desenvolvedor-pleno` |
| **3** | **Tela** de importação e conferência | `especialista-frontend` |

⚠️ **O passo 1 vem antes por regra, não por cautela:** *"não invente leiaute
oficial"*. Nome de elemento e caminho de campo **não se adivinham**.

⚠️ **E os passos 2 e 3 são SEQUENCIAIS, não paralelos — a razão é uma lição
recente e caríssima.** Na DL-034 as duas frentes correram juntas sobre um
contrato **novo**, o contrato mudou **duas vezes** no meio da janela, a frente da
tela refez trabalho duas vezes, e ainda houve colisão de agentes no mesmo arquivo
([DE-073](../projeto/decisoes.md#de-073)). **Aqui o contrato nasce do zero, então
ele vai se mover.** A tela entra quando ele parar.

### Nível de risco: 1 — e os dois motivos são de dado, não de tela

1. **Importar documento para a empresa errada é pior que não importar.** Por isso
   o critério 5 **recusa** em vez de adivinhar.
2. **É a primeira vez que o produto guarda documento de terceiro com dado real de
   cliente.** Isolamento, trilha sem conteúdo e ausência em log deixam de ser
   boas práticas e passam a ser critério.

Verificação: **auditoria independente da versão integrada**, com a regra de
parada da §3.1 — uma auditoria, uma correção, uma reconferência, **sem terceira**.

### O que segue FORA, e agora com o motivo de cada um

Além do que a seção de escopo já declara: **NF-e modelo 55** (fatia 2, leiaute já
levantado neste plano), **SPED Fiscal** (espera amostra do Fred), **NFCom, CT-e e
GTVe** (1% do acervo, e o NFCom vem de um único emitente), **apuração**,
**classificação fiscal versionada** e **contabilização automática** — esta última
é a integração fiscal-contábil, e só faz sentido depois de existir escrituração
para contabilizar.

⚠️ **PE-41 continua aberta e é o maior risco de fundo desta fatia:** 82% das
notas do acervo são de **um único município**. O risco é ajustar o leitor ao
provedor de software de uma prefeitura e descobrir no cliente seguinte. **Uma
segunda amostra, de outro município, vale mais que qualquer refinamento sobre
esta** — e é pedido ao Fred, não bloqueio.

## Leiaute da NFS-e nacional — levantado em fonte oficial em 2026-09-25

Levantamento do `auxiliar-pesquisa` contra o **pacote oficial de esquemas XSD
vigente** (`NFSe-ESQUEMAS_XSD-v1.01-20260209.zip`, publicado 09/02/2026, da
Documentação Técnica Atual do portal `gov.br/nfse`), **lido nos `.xsd`, não em
prosa de manual**. Registrado como **RC-110 a RC-113** e **PE-66 a PE-68**.

⚠️ **Nada do que segue foi deduzido.** Onde a fonte não respondeu, virou
pendência declarada — não hipótese disfarçada de requisito.

### O que está CONFIRMADO, e o que cada item obriga

| Achado | O que obriga nesta fatia |
| --- | --- |
| **Namespace único** `http://www.sped.fazenda.gov.br/nfse`, **igual** em 1.00 e 1.01 **e igual para todos os tipos** | ⚠️ **O tipo do documento NÃO pode ser reconhecido pelo namespace.** O reconhecimento é pelo **elemento raiz** — a mesma armadilha já levantada para a NF-e, agora confirmada aqui |
| **Elementos raiz:** `NFSe`, `DPS`, `evento`, `pedRegEvento` | Quatro raízes conhecidas. **Raiz desconhecida é recusa com mensagem específica**, nunca tentativa de adivinhar (mitiga a PE-66) |
| **Versão no atributo `versao` da raiz**, restrita por esquema a `1.00` ou `1.01` | Versão fora dessas duas é **recusa com mensagem própria**, não erro genérico de esquema |
| `Id` de `infNFSe` = `NFS` + 50 dígitos = **53 caracteres**, com regra de formação documentada no próprio esquema | Confirma a **RC-74**. É a chave, e a única |
| `nNFSe` é `string` com `maxLength=13`, **sem mínimo** | Confirma que **não serve como chave** (critério 16) |
| CNPJ e CPF são `xs:string` com `pattern`, **nunca tipo numérico** | Confirma o critério 22: zero à esquerda se preserva porque o campo **é texto na própria norma** |
| `toma` (tomador) é **opcional**, e admite `NIF`/`cNaoNIF` para o exterior | Tomador ausente **não** é arquivo malformado. É a mesma armadilha do bloco `dest` da NF-e |
| **UTF-8** | — |

### ⚠️ O achado que MUDA o modelo de dados: a situação não está na nota

`NFSe/infNFSe/cStat` é enumeração **fechada** de **quatro** valores, e **todos são
de geração**: `100` gerada, `102` decisão judicial, `103` avulsa, `107` MEI.

> **Nenhum valor significa "cancelada".** Cancelamento e substituição existem
> **só como EVENTO, em arquivo separado**, que aponta para a nota pela **chave**
> `chNFSe`.

**Consequência de projeto, e ela é dura:** ⚠️ **a situação do documento é
DERIVADA — nota mais eventos aplicados —, nunca um campo copiado do XML.** Um
importador que gravasse `cStat` como "situação" afirmaria que a nota está válida
**enquanto ela pode estar cancelada**. É exatamente o defeito que o critério 17
existe para impedir, agora com **fundamento oficial** em vez de só a medição do
acervo.

E há **treze** eventos confirmados — cancelamento com motivo, cancelamento por
substituição com a chave da substituta, análise fiscal deferida e indeferida,
confirmações, rejeições, anulação de rejeição, cancelamento por ofício, bloqueio e
desbloqueio. ⚠️ **Todos com o MESMO elemento raiz `evento`**: o código vive dentro
de `pedRegEvento/infPedReg`, como escolha. Reconhecer "é cancelamento" pela raiz é
impossível; é preciso ler o código dentro.

### O que o levantamento acrescenta aos critérios de aceite

Estes **somam** aos 22 já escritos; nenhum os substitui.

| # | Critério |
| --- | --- |
| **23** | **Reconhecimento pelo ELEMENTO RAIZ** (RC-110), nunca pelo namespace nem pelo nome do arquivo. Teste com os quatro raízes conhecidas, e com **raiz desconhecida** exigindo recusa de mensagem específica |
| **24** | **Versão fora de `1.00`/`1.01` é recusada com mensagem própria**, distinguível de erro genérico de esquema |
| **25** | ⚠️ **A situação do documento é DERIVADA de nota + eventos** (RC-111), e `cStat` **não** é gravado como situação. Teste: nota com `cStat=100` **e** evento de cancelamento aplicado **não** é apresentada como válida — nas duas ordens de chegada |
| **26** | **Tomador ausente não é arquivo inválido** (o bloco é opcional na norma). Teste com nota sem tomador, e com tomador no exterior |
| **27** | **O código do evento é lido de dentro de `pedRegEvento/infPedReg`**, não da raiz. Teste com dois eventos de códigos diferentes provando que o importador os distingue |

### ⚠️ A fonte oficial NÃO fechou a PE-41 — ela a CONFIRMOU como risco

Texto literal da fonte: município que opta por sistema próprio **pode manter seu
padrão técnico interno**, e só precisa se adaptar ao padrão nacional **para
compartilhar** documentos pelo ambiente nacional (**RC-113**).

**Ou seja:** as notas do município que concentra **82% do acervo** podem
legitimamente **não** seguir este XSD, se vierem direto do provedor local. A
norma não nos protege disso.

⚠️ **Existe um teste barato que decide a questão, e ele entra como tarefa:**
conferir se essas notas têm o `Id` de **53 caracteres** e a estrutura
`infNFSe`/`infDPS`. Se tiverem, são padrão nacional **de fato**. **Isso vale mais
que qualquer refinamento do leitor**, e depende da segunda amostra pedida ao Fred.

### Três pendências declaradas, nenhuma bloqueando a fatia

- **PE-66** — existe envelope de distribuição do ambiente nacional, com raiz
  própria? Não localizado no pacote XSD. **Mitigado de graça** pelo critério 23:
  raiz desconhecida é recusada com mensagem, não adivinhada.
- **PE-67** — data exata em que o bloco de IBS/CBS entrou no esquema. Irrelevante
  agora, pela DE-074; material quando a interpretação entrar.
- **PE-68** — ⚠️ **pergunta ao Fred, e é a mais importante das três:** o acervo
  medido tem os **arquivos de evento**, ou só as notas? Pela RC-111, sem os
  eventos a situação de boa parte do acervo é **desconhecida**, não "válida".

⚠️ **E um limite da própria fonte, que o pesquisador declarou em vez de
esconder:** o manual conceitual que sustenta a RC-113 é classificado **pelo
próprio portal** como *"leiaute e esquemas antigos (julho de 2022 a
28/09/2025)"*, e **não foi localizado substituto** na Documentação Atual. O
conceito pode ter mudado depois dessa data, e **isso não está confirmado**.
