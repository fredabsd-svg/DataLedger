# DL-010 — Recepção de documentos fiscais

Primeira fatia do módulo Fiscal, escolhida pelo Fred: **importação e
conferência** é a rotina que mais consome tempo no escritório (RC-40).

**Estado:** planejada.

## Objetivo

Receber documentos fiscais de fontes que o escritório **já usa hoje**, sem
exigir que ele mude a ferramenta de captura, e entregar a base sobre a qual a
conferência será construída.

## As três fontes, e por que cada uma existe

O Fred confirmou que o escritório recebe **XML cru, ZIP ou RAR**, vindo de um
sistema de gestão de XML de terceiros (RC-41), e pediu também importação em
**formato SPED Fiscal**.

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

### 1. CNPJ alfanumérico já está em vigor — e hoje o sistema recusa

Ver **BL-46**. Desde **31/07/2026** (IN RFB nº 2.229), o CNPJ pode conter
letras. O validador atual descarta letras e recusa o documento.

Isto **atravessa esta etapa inteira**: a empresa do documento é identificada
por CNPJ, e a chave de acesso da NF-e contém o CNPJ do emitente.

**Consequência de projeto:** a identificação de empresa por CNPJ fica
**isolada num único ponto**, para que a correção do BL-46 entre em um lugar só e
valha para todos os caminhos de importação.

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
| 6 | Documento de empresa de **outro escritório** nunca é acessível nem importável |
| 7 | XML malformado, truncado ou que não seja NF-e é recusado com mensagem útil, sem derrubar o lote |
| 8 | Um arquivo ruim no meio do ZIP **não impede** os demais de serem importados |
| 9 | Arquivo SPED Fiscal é lido e os documentos do bloco C são extraídos |
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
