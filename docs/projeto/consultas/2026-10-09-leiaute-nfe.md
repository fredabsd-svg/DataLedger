# Relatório de pesquisa para a DL-080: recepção de NF-e modelo 55 e NFC-e 65

Data da consulta: 09/10/2026. Pesquisa somente de leitura: não alterei o repositório nem executei nada baixado.

**Convenções**
- Marcas: CONFIRMADO (fonte oficial, com URL, arquivo e linha), SECUNDÁRIO, NÃO ENCONTRADO. As leituras minhas vão como INFERÊNCIA.
- Atalhos de caminho:
  - `S` = `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/nfe`
  - `XSD` = `S/pl010f/ex/PL_010f_v1.04/leiauteNFe_v4.00.xsd`
  - `TB` = `S/pl010f/ex/PL_010f_v1.04/tiposBasico_v4.00.xsd`
  - `DFE` = `S/pl010f/ex/PL_010f_v1.04/DFeTiposBasicos_v1.00.xsd`
  - `PROC` = `S/pl9q/ex/PL_009q_NT2025_001_v1.00/procNFe_v4.00.xsd`
  - `EVT` = `S/pl010d103/ex/PL_010d_v1.03/Evento/leiauteEvento_v1.00.xsd`
  - `MOC` = `S/nt_txt/moc7_visao_geral.txt`
  - `ANX` = `S/nt_txt/moc7_anexo_i.txt`
  - `NT25` = `S/nt_txt/nt2025002_v152.txt`
- Todo download veio de `www.nfe.fazenda.gov.br/portal/` ou de `dfe-portal.svrs.rs.gov.br`, em 09/10/2026.
- O diretório `nfe/` não ficou vazio. Baixei a página do portal e o cookie jar direto nele antes de criar os subdiretórios, então ele tem esses dois arquivos soltos além dos pacotes (cada um em subdiretório próprio). Nada foi executado e nada fora de `scratchpad` foi tocado.

---

## 1. Pacote de esquemas vigente

**CONFIRMADO: PL 010f é o pacote em uso.**
- Fonte: `https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=`, seção "VERSÕES OFICIAIS (em uso)", primeiro item.
- Título: "Schemas XML NF-e – Pacote de Liberação nº 010f – NT 2025.002 v.1.50 e NT 2026.007 v.1.00 (Publicado em 31/08/26)".
- Download: `https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=8ITFuBLltXs=` (exige cookie `AspxAutoDetectCookieSupport`).
- Arquivo: `PL_010f_v1.04.zip`, 41.682 bytes.
- **sha256 do zip: `b8589490a58a09a993a80e6ac4d7ed10f20892061ecfc56719337098d4b95998`** (calculado por mim).
- Conteúdo, com sha256:

| Arquivo | sha256 |
| --- | --- |
| `leiauteNFe_v4.00.xsd` | `2bace939973916d54184ff3e2740041a932de5d79772f3363504504160f22542` |
| `tiposBasico_v4.00.xsd` | `772619c85723e598840667ca66e7298a250442df47eeb94b397d2a333ce62047` |
| `DFeTiposBasicos_v1.00.xsd` | `173577a4e3a9dc1d0deced85b89b955b6064bb5a4ae5a96f6727d2da8a694d09` |
| `nfe_v4.00.xsd` | `adce3646c13ceb54922ec3142fc1dc45bd4fb839ac35ad583e86c733c07d27df` |
| `xmldsig-core-schema_v1.01.xsd` | `f56744a5f51c03f027de13f39f869307091781a9ef1d91b1ebe14719ce28e1ac` |

**Atenção ao pacote.**
- O PL 010f traz só 5 arquivos. **Não tem `procNFe_v4.00.xsd` nem os esquemas de evento.**
- O elemento `nfeProc` vem do pacote `PL_009q_NT2025_001_v1.00.zip`. URL: `exibirArquivo.aspx?conteudo=0qRvxtvKcj4=`.
  - sha256 do zip: `82a26d04a778fc214bf8c6c6e5c65ea577721e32ed5efa9a11a80098b8f9802f`.
  - sha256 do `procNFe_v4.00.xsd`: `b7af3072ff7398aa557c42bc6d8198dd3c006b1a6ecaad66bc839a5c34cbcb84`.
  - O tipo `TNfeProc` está no próprio `XSD:6954`.
- Os esquemas de evento vêm do pacote `PL_010d_v1.03.zip`. URL: `exibirArquivo.aspx?conteudo=%2BpBOYTXBtbk%3D`.
  - sha256 do zip: `45ceefe4dfbbfec93958283b650a2f1e1734784f4770d070b9907754de081d9b`.
  - O `Evento/leiauteEvento_v1.00.xsd` dele já aceita CNPJ alfanumérico.

**Há versão mais nova que o pacote?** Parcialmente.
- Em 01/10/2026 saíram a NT 2025.002 v1.52, a NT 2026.007 v1.10 e a NT 2026.008 v1.00. O Portal as lista em `listaConteudo.aspx?tipoConteudo=04BIflQt1aY=`, na seção "Documentos vigentes".
- As v1.51 e v1.52 da NT 2025.002 alteram só regras de validação (`NT25:244-275`).
- A **NT 2026.008 cria campos novos no leiaute** (`vUnComLiq`, `vProdLiq`, `vProdLiqTot`, `vICMSPrevisto`). Procurei esses nomes no XSD do PL 010f e há 0 ocorrências.
- Logo, o PL 010f é o pacote em uso, mas **não é o último leiaute que vai circular**.
- **NÃO ENCONTRADO:** pacote PL 010g ou posterior. Eu o esperaria com a NT 2026.008.

**Atenção às datas (CONFIRMADO).**
- Fonte: Informe do Portal de 05/10/2026, `https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false&Informe=GyPA/cEjrMk=`.
- Texto: as NTs NF-e 2025.002 v1.52, 2026.007 v1.10 e 2026.008 v1.00 "ficam postergadas para 26/outubro em homologação e 16/novembro em produção".
- Isso **supera** as datas impressas nos PDFs. Os PDFs dizem 05/10/2026 na homologação e 03/11/2026 na produção (`NT25:273-275`).

**Versão de leiaute: CONFIRMADO 4.00.**
- `XSD:7561-7569`: `TVerNFe`, padrão `4\.00`.
- `XSD:6620` é o atributo `versao` de `infNFe`.
- `XSD:6769` é o `versao` de `TProtNFe`.
- `XSD:6962` é o `versao` de `TNfeProc`.

### Caminhos dos campos (todos CONFIRMADOS no XSD do PL 010f)

Os caminhos partem de `nfeProc/NFe/infNFe`.

| Campo | Caminho | Arquivo:linha |
| --- | --- | --- |
| Chave (atributo) | `infNFe/@Id`, padrão `NFe[0-9]{6}[0-9A-Z]{12}[0-9]{26}` | `XSD:6625-6634` |
| Versão | `infNFe/@versao` | `XSD:6620` |
| Chave no protocolo | `protNFe/infProt/chNFe`, tipo `TChNFe` | `XSD:6709` |
| Tipo `TChNFe` | `[0-9]{6}[0-9A-Z]{12}[0-9]{26}` | `TB:49-58` |
| `cUF` | `ide/cUF` | `XSD:24` |
| `mod` | `ide/mod`, valores 55 ou 65 | `XSD:51`, `TB:359-367` |
| `serie` | `ide/serie` | `XSD:56`, `TB:378` |
| `nNF` | `ide/nNF`, `[1-9][0-9]{0,8}` | `XSD:61`, `TB:369-377` |
| `dhEmi` | `ide/dhEmi` | `XSD:66` |
| `tpNF` | `ide/tpNF`, 0=entrada, 1=saída | `XSD:81-92` |
| `idDest` | `ide/idDest`, 1=interna, 2=interestadual, 3=exterior | `XSD:93-105` |
| `finNFe` | `ide/finNFe`, 1 a 6 | `XSD:185-195`, `XSD:7471-7483` |
| `tpNFDebito` | `ide/tpNFDebito` | `XSD:196`, enumeração em `XSD:7485` |
| `tpNFCredito` | `ide/tpNFCredito` | `XSD:201`, enumeração em `XSD:7509` |
| Emitente | `emit/CNPJ` ou `emit/CPF` (`xs:choice`); `TCnpj` aceita letras; `TCpf` só dígitos | `XSD:526`, `XSD:531`, `TB:89-98`, `TB:119-127` |
| Regime | `emit/CRT`, valores 1 a 4 | `XSD:601` |
| IE do emitente | `emit/IE`, `minOccurs=0` | `XSD:564` |
| Destinatário | `dest`, `minOccurs=0` | `XSD:734` |
| Documento do destinatário | `dest/CNPJ`, `dest/CPF` ou `dest/idEstrangeiro` | `XSD:741`, `XSD:746`, `XSD:751` |
| Nome do destinatário | `dest/xNome`, `minOccurs=0` | `XSD:763` |
| Item | `det` (`maxOccurs=990`) | `XSD:867` |
| `cProd` | `det/prod/cProd` | `XSD:879` |
| `xProd` | `det/prod/xProd` | `XSD:913` |
| `NCM` | `det/prod/NCM` | `XSD:924` |
| `CFOP` | `det/prod/CFOP` | `XSD:1026` |
| `qCom` | `det/prod/qCom` | `XSD:1048` |
| `vProd` do item | `det/prod/vProd` | `XSD:1058` |
| ICMS | `det/imposto/ICMS/ICMS00/CST` (e demais variantes) | `XSD:2106`, `XSD:2119`, `XSD:2125`, `XSD:2139` |
| CSOSN | `ICMSSN101/CSOSN`, `ICMSSN900/CSOSN` | `XSD:3899`, `XSD:3913`, `XSD:4260`, `XSD:4273` |
| IBS/CBS por item | `det/imposto/IBSCBS`, tipo `TTribNFe`, `minOccurs=0` | `XSD:5186` |
| IBS/CBS por item, interior | `CST`, `cClassTrib`, `gIBSCBS` (tipo `TCIBS_NFe`) | `DFE:328`, `DFE:333`, `DFE:340`, `DFE:875` |
| Imposto Seletivo por item | `det/imposto/IS` | `XSD:5181` |
| Devolução de tributo (percentual) | `det/impostoDevol` | `XSD:5194` |
| Valor do item | `det/vItem` | `XSD:5289` |
| Referenciamento por item | `det/DFeReferenciado` (`chaveAcesso`, `nItem`) | `XSD:5294-5310` |
| Totais | `total/ICMSTot` | `XSD:5333`, `XSD:5339` |
| `vBC` | `total/ICMSTot/vBC` | `XSD:5345` |
| `vICMS` | `total/ICMSTot/vICMS` | `XSD:5350` |
| `vST` | `total/ICMSTot/vST` | `XSD:5385` |
| `vFCP` | `total/ICMSTot/vFCP` | `XSD:5375` |
| `vProd` | `total/ICMSTot/vProd` | `XSD:5430` |
| `vFrete` | `total/ICMSTot/vFrete` | `XSD:5435` |
| `vDesc` | `total/ICMSTot/vDesc` | `XSD:5445` |
| `vIPI` | `total/ICMSTot/vIPI` | `XSD:5455` |
| `vIPIDevol` | `total/ICMSTot/vIPIDevol` | `XSD:5460` |
| `vPIS` | `total/ICMSTot/vPIS` | `XSD:5465` |
| `vCOFINS` | `total/ICMSTot/vCOFINS` | `XSD:5470` |
| `vNF` | `total/ICMSTot/vNF` | `XSD:5480` |
| Total de IS | `total/ISTot` | `XSD:5617` |
| Total de IBS/CBS | `total/IBSCBSTot`, tipo `TIBSCBSMonoTot` | `XSD:5622` |
| Campos de `IBSCBSTot` | `vBCIBSCBS`, `gIBS/vIBS`, `gCBS/vCBS`, `gMono`, `gEstornoCred` | `DFE:563`, `DFE:568`, `DFE:622`, `DFE:640`, `DFE:656`, `DFE:674`, `DFE:714` |
| Total com tributos por fora | `total/vNFTot`, `minOccurs=0` | `XSD:5627` |
| Protocolo | `protNFe/infProt` | `XSD:6686`, `XSD:6691` |
| `dhRecbto` | `protNFe/infProt/dhRecbto` | `XSD:6714` |
| `nProt` | `protNFe/infProt/nProt`, `minOccurs=0`, 15 ou 17 dígitos | `XSD:6719`, `TB:59-67` |
| `cStat` | `protNFe/infProt/cStat`, 3 a 4 dígitos | `XSD:6729`, `TB:79-88` |
| `digVal` | `protNFe/infProt/digVal` | `XSD:6724` |
| Raiz `nfeProc` | `NFe` + `protNFe` | `PROC:4`, `XSD:6954-6962` |
| Raiz `NFe` | `NFe` | `S/pl010f/ex/PL_010f_v1.04/nfe_v4.00.xsd:5` |
| Raiz `enviNFe` | `enviNFe` | `S/pl9q/ex/PL_009q_NT2025_001_v1.00/enviNFe_v4.00.xsd:4` |
| Suplemento da NFC-e | `infNFeSupl` (`qrCode`, `urlChave`), opcional | `XSD:6641`, `XSD:6647`, `XSD:6669` |
| Assinatura da NF-e | `ds:Signature`, obrigatória | `XSD:6683` |

Padrões de valor para o leitor:
- `TDec_1302` (`TB:301-307`) é `0|0\.[0-9]{2}|[1-9][0-9]{0,12}(\.[0-9]{2})?`: sem sinal, até 13 inteiros, 2 casas.
- `qCom` (`TDec_1104v`, `TB:229`) aceita de 0 a 4 casas.
- `vUnCom` (`TDec_1110v`, `TB:247`) aceita de 0 a 10 casas.
- O `_FORMATO_DECIMAL` do `leitor.py:73` é da NFS-e (15 inteiros) e **não serve** para NF-e.
- `TDec1302RTC` (`DFE:86-92`) tem o mesmo padrão do `TDec_1302`. Nenhum campo do IBS/CBS no esquema aceita sinal negativo.

---

## 2. Eventos da NF-e

### Caminhos (CONFIRMADO)

O arquivo é `EVT` (PL 010d_v1.03), em `exibirArquivo.aspx?conteudo=%2BpBOYTXBtbk%3D`.

**Entrada**
- Raiz `envEvento` (`Evento/envEvento_v1.00.xsd:4`), tipo `TEnvEvento` (`EVT:280-295`).
- `evento` aparece até 20 vezes (`EVT:293`).

**Raiz de distribuição**
- `procEventoNFe` (`Evento/procEventoNFe_v1.00.xsd:4`), tipo `TProcEvento` (`EVT:341-349`).
- Contém `evento` (`EVT:346`) e `retEvento` (`EVT:347`).
- `@versao` é `1.00` (`EVT:350-367`).

Campos do evento, a partir de `evento/infEvento`:

| Campo | Linha no `EVT` |
| --- | --- |
| `cOrgao` | 13 |
| `tpAmb` | 18 |
| `CNPJ` ou `CPF` do autor | 29 e 34 |
| `chNFe` | 40 |
| `dhEvento` | 45 |
| `tpEvento`, `[0-9]{6}` | 50-57 |
| `nSeqEvento`, `[1-9][0-9]{0,1}` | 61-68 |
| `verEvento` | 72 |
| `detEvento` | 82 |
| `infPAA`, novo, opcional | 94 |

- O `@Id` é `ID[0-9]{12}[0-9A-Z]{12}[0-9]{28}` (`EVT:129-137`). É "ID" + `tpEvento` (6) + chave (44) + `nSeqEvento` (2) = 52 caracteres.
  - **Já aceita letras no CNPJ.** A versão antiga do esquema (`Evento_Generico_PL_v1.01`) era `ID[0-9]{52}`.

Retorno, em `retEvento/infEvento`:

| Campo | Linha no `EVT` |
| --- | --- |
| `cStat` | 171 |
| `xMotivo` | 176 |
| `chNFe` | 181 |
| `tpEvento` | 186 |
| `xEvento` | 197 |
| `nSeqEvento` | 208 |
| `dhRegEvento` | 250 |
| `nProt` | 261 |

- O `@Id` do retorno é `ID[0-9]{15}` e é opcional (`EVT:267-270`).
- No lote, `retEnvEvento/cStat` está em `EVT:327`.

**Qual `cStat` vale para considerar o evento registrado.**
- **CONFIRMADO no MOC 7.0:**
  - `135` = "Evento registrado e vinculado a NF-e" (`ANX:6470`; `MOC:7034`).
  - `136` = "Evento registrado, mas não vinculado a NF-e" (`ANX:6471`; `MOC:7036`).
  - `128` = lote processado (`MOC:7030`).
- Cancelamento fora de prazo: `MOC:6181` cita "155-Cancelamento homologado fora de prazo". O quadro de códigos do MOC não lista `155`. Lista `101` e `151` (`ANX:6456`, `ANX:6478`). **O próprio MOC é inconsistente aqui.**
- **INFERÊNCIA:** o evento só deve ser aplicado quando o `procEventoNFe` traz `retEvento` com `cStat` em {135, 136, 155}. Um `envEvento` sem retorno, ou um `retEvento` rejeitado, não prova registro.

### Tipos de evento

**Eventos do emitente** (MOC 7.0, Tabela 3-1, `MOC:1493-1531`; Portal, esquemas)

| Código | Descrição oficial | Fonte do schema |
| --- | --- | --- |
| 110110 | Carta de Correção Eletrônica | `S/cce/ex/Evento_CCe_PL_v1.01/e110110_v1.00.xsd:17` ("Carta de Correção") |
| 110111 | Cancelamento (pelo Emitente) | `S/cancel/ex/Evento_Canc_PL_v1.01/e110111_v1.00.xsd:17` |
| 110112 | Cancelamento por substituição | `S/cancsubst/ex/Evento_CancSubst_v1.01/e110112_v1.00.xsd:17`; campo `chNFeRef` na linha 53 |
| 110140 | EPEC (Emissão em Contingência) | `MOC:1503` |
| 110150 | Ator interessado, transportador | `MOC:1525` |
| 111500, 111501, 111502, 111503 | Prorrogação de ICMS e seus cancelamentos | `MOC:1507-1531` |

**Manifestações do destinatário** (`MOC:1548-1566`; `S/manif102/ex/PL/EventoManifestaDestinat_v100/`)

| Código | Descrição | Linha da descrição no schema |
| --- | --- | --- |
| 210200 | Confirmação da Operação | `e210200_v1.00.xsd:17` |
| 210210 | Ciência da Operação | `e210210_v1.00.xsd:17` |
| 210220 | Desconhecimento da Operação | `e210220_v1.00.xsd:17` |
| 210240 | Operação não Realizada | `e210240_v1.00.xsd:16` |

**Eventos novos da reforma** (NT 2025.002; `NT25:3649-3683`; schemas em `S/evt140/ex/Eventos_RTC/`, pacote `Eventos_RTC.zip`)
- URL: `exibirArquivo.aspx?conteudo=kp0SXLu%2BZdI%3D`.
- sha256 do zip: `a4c57ce95b225cd8852f90bd6c39ca28ae551636ff3f67eb2602b9fa847129b2`.

| Código | Evento | Autor |
| --- | --- | --- |
| 112110 | Informação de efetivo pagamento integral para liberar crédito presumido do adquirente | Emitente |
| 112120 | Importação em ALC/ZFM não convertida em isenção | Emitente |
| 112130 | Perecimento, perda, roubo ou furto durante o transporte contratado pelo fornecedor | Emitente |
| 112140 | Fornecimento não realizado com pagamento antecipado | Emitente |
| 112150 | Atualização da Data de Previsão de Entrega | Emitente |
| 211110 | Solicitação de Apropriação de crédito presumido | Emitente ou destinatário |
| 211124 | Perecimento, perda, roubo ou furto durante o transporte contratado pelo adquirente | Destinatário |
| 211128 | Aceite de débito na apuração por emissão de nota de crédito | Destinatário |
| 211130 | Imobilização de Item | Destinatário |
| 211140 | Solicitação de Apropriação de Crédito de Combustível | Destinatário |
| 211150 | Solicitação de Apropriação de Crédito para bens e serviços que dependem de atividade do adquirente | Destinatário |
| 212110 | Manifestação sobre Pedido de Transferência de Crédito de IBS em Operações de Sucessão | Sucessora |
| 212120 | O mesmo, para CBS | Sucessora |
| 412120 | Manifestação do Fisco sobre Pedido de Transferência de Crédito de IBS em Operações de Sucessão | Fisco |
| 412130 | O mesmo, para CBS | Fisco |
| 110001 | Cancelamento de Evento (genérico) | Mesmo autor do evento cancelado |

- Nota sobre o 211120: a NT 2025.002 v1.40 o **eliminou** (`NT25:234`: "Eliminação do Evento 211120"). Ele ainda aparece na enumeração `tpEventoAut` do `e110001_v1.00.xsd:43`.
  - Isso é uma ponta solta do próprio esquema. Não afeta a recepção, mas o leitor não deve assumir que toda a enumeração é viva.

### Quais tornam a nota sem efeito

- **CONFIRMADO, `MOC:1398-1404`:** o evento pode ou não modificar a situação do documento. O MOC cita como exemplo de modificação "autorização de uso, cancelamento". Cita como exemplo de evento que não modifica "carta de correção, registro de passagem".
- **Cancelam a nota:**
  - `110111`, "Cancelamento da NF-e" (`MOC:1495`).
  - `110112`, que o MOC define como "cancelamento, em prazo não superior a 168 horas, de NFC-e emitida em duplicidade" (`MOC:1497`, seção 3.5 em `MOC:2445-2475`). Ele é próprio da NFC-e.
    - **O MOC descreve o 110112 só para NFC-e.** O schema `e110112` não restringe o modelo no próprio arquivo. Não encontrei no MOC regra que o proíba no modelo 55.
- **Não cancelam:**
  - Todas as manifestações. O texto de `MOC:1548-1566` não fala em efeito sobre a validade da nota.
  - `110110` (CC-e).
  - Os eventos novos da reforma. São eventos de apuração (`NT25:3649`). Nenhum está descrito como cancelamento da NF-e.
  - **`110001` cancela outro evento, não a nota.** Isso importa: um `110001` pode anular um `211110`, por exemplo.
- Outros fatos:
  - **Denegação não é evento.** Vem no `protNFe` com `cStat` 110 (e 301, 302, 303 nas regras). O MOC diz que nota denegada fica gravada na base com esse status e o uso como documento fiscal é "Vedado" (`MOC:4095-4108`; `ANX:6465`, `ANX:7160-7162`).
  - A confirmação da operação (210200) impede o emitente de cancelar: "a empresa emitente fica automaticamente impedida de cancelar a NF-e" (`S/nt_txt/pt_nt2020001_v160.txt:111`).
    - Fonte: NT 2020.001 v1.60, `exibirArquivo.aspx?conteudo=%2BWTd7iuD21s%3D`, sha256 `f610878ad54708086aaa20dc668d714adf89cf109b8afbea687f69ef733efe46`.
  - **O destinatário pode registrar até 2 eventos de cada manifestação conclusiva, e vale a última** (`pt_nt2020001_v160.txt:140-142`; Ajuste SINIEF 43/23). **O prazo da manifestação conclusiva é 90 dias** da autorização (Ajuste SINIEF 14/26, vigente desde 01/06/2026, `pt_nt2020001_v160.txt:38-41` e `:151`). Ciência da emissão: 10 dias.
    - **Consequência para a recepção:** a unicidade do evento precisa incluir `nSeqEvento` (o `@Id` já o inclui). A situação de manifestação não pode ser "o último que chegou". Tem de ser "o de maior `nSeqEvento`, por tipo".
- **NÃO ENCONTRADO:** documento oficial que tabele, evento a evento, "efeito sobre a validade da nota". A lista acima é leitura dos textos do MOC e das NTs. O efeito de cada código novo da reforma na validade do documento é INFERÊNCIA (o MOC e a NT 2025.002 não o dizem como cancelamento).

---

## 3. Chave de acesso

- **CONFIRMADO, `MOC:914-947` (MOC 7.0, Tabela 2-1)**, composição de 44 posições:

| Bloco | Tamanho |
| --- | --- |
| `cUF` | 2 |
| `AAMM` | 4 |
| CNPJ ou CPF do emitente | 14 |
| `mod` | 2 |
| `serie` | 3 |
| `nNF` | 9 |
| `tpEmis` | 1 |
| `cNF` | 8 |
| `cDV` | 1 |

- **CPF vai com zeros à esquerda para 14 posições** (`MOC:940-942`).
- **DV, `MOC:950-960`:** módulo 11 com pesos 2 a 9 da direita para a esquerda. `DV = 11 - resto`, e resto 0 ou 1 dá DV 0.
- **CNPJ alfanumérico, NT Conjunta DFe 2025.001, `S/nt_txt/ntcj2025001.txt:136-172`:**
  - Regex `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`.
  - O DV troca os 44 caracteres por `ASCII - 48` e aplica o mesmo módulo 11.
  - Fonte: `https://dfe-portal.svrs.rs.gov.br/DFE/DownloadArquivoEstatico/?sistema=DFE&tipoArquivo=3&nomeArquivo=DFe NTCJ 2025.001_CNPJ Alfa_v1.00.pdf`. sha256 do PDF: `671d546b24ad4682e267fc76a9eeca8f14ad15ead2be20721ee2aec5438cf964`.
  - O Portal Nacional lista a mesma NT (`exibirArquivo.aspx?conteudo=5ZkvIZt10mQ=`). Não baixei esse link.
- **Bate com a DL-010 e a DL-011.** Comparei com `DL-011-cnpj-alfanumerico.md:168-182` (estrutura, regex e DV). **Nada a corrigir.** O "se `dv >= 10` então 0" da DL-011 é equivalente à regra "resto 0 ou 1" do MOC.
- **Dois acréscimos que a DL-010 não registrou:**
  1. **Série 890 a 899 (NFA-e, nota avulsa de site de SEFAZ) leva o CNPJ da SEFAZ na chave**, não o do emitente (`MOC:1047-1053`, Tabela 2-4). Séries 900-909 e 910-919 são de SEFAZ para CNPJ e CPF. 920-969 é aplicativo da empresa com CPF.
     - **Consequência:** a empresa do documento deve vir de `emit/CNPJ|CPF`, não de fatiar a chave.
  2. **Discrepância de datas entre duas NTs:**
     - A NT Conjunta diz implantação em produção em **06/07/2026** (`ntcj2025001.txt`, quadro "Histórico de Alterações").
     - A NT 2026.004 v1.01 diz **01/07/2026** para a atualização do schema (`S/nt_txt/nt2026004.txt:40-47`).
     - Fonte da NT 2026.004: `dfe-portal.svrs.rs.gov.br/NFE/DownloadArquivoEstatico/` (`tipoArquivo=3`, `nomeArquivo=NT_2026.004_v1.01_AlteraSchemaNFCeNFeCNPJAlfa.pdf`). sha256 do PDF: `5f24a25351e790692754b07bbefac42ac67e70167a62a7806395d880f56675be`.
     - Não decide a recepção, mas fica registrado. A nota da NT Conjunta diz que autorizadores devem rejeitar CNPJ alfanumérico antes da data de implantação.
- **A prosa do MOC 7.0 continua dizendo "44 caracteres numéricos"** (`MOC:915`), e o XSD aceita letras (`TB:56`). Confirma a armadilha 3 da DL-010. Para formato vale o XSD. O MOC 7.0 (PDF criado em 04/11/2020, `pdfinfo`) está desatualizado nesse ponto.
- **Chave natural, `MOC:1018-1027`:** UF, CNPJ ou CPF do emitente, série, número, modelo e ambiente. **INFERÊNCIA:** a dedupe por `(escritório, chave)` é correta e coincide com a chave natural que o próprio autorizador usa.

---

## 4. Notas técnicas que mudam o que a recepção lê

Fontes:
- Portal: `https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY=`.
- Espelho SVRS: `https://dfe-portal.svrs.rs.gov.br/Nfe/Documentos`. Os links do SVRS são JavaScript, `download_arquivo_estatico('NFE', 3, '<arquivo>')`, resolvidos para `/NFE/DownloadArquivoEstatico/?sistema=NFE&tipoArquivo=3&nomeArquivo=<arquivo>`.

### NT 2025.002 (IBS/CBS e outros): CONFIRMADO

- **Versão atual:** v1.52, publicada em 01/10/2026 (setembro de 2026 na capa). PDF de 94 páginas.
- sha256 do PDF: `54ed893327040a20a4a3c0562d342953542a1dc98e55d73dbe607d6c13d3d416`.
- Baixei o mesmo arquivo das duas fontes: Portal (`exibirArquivo.aspx?conteudo=HXPO8VLbh4o=`) e SVRS. Os bytes são idênticos.
- **Datas de obrigatoriedade (`NT25:295-329`), válidas só para CRT=3 (regime normal):**

| Ambiente | Data | Regra |
| --- | --- | --- |
| Homologação | 01/07/2026 | Campos IBS/CBS obrigatórios |
| Produção | 03/08/2026 | Campos IBS/CBS obrigatórios por regra de validação |
| Produção | 01/01/2026 | Já havia valor jurídico dos novos tributos; as regras de validação se aplicam quando o grupo é informado |

- **CRT=1, 2 e 4 e tributação monofásica:** as orientações "serão publicadas em NT futura". A tributação do IBS/CBS/IS para esses contribuintes só ocorre a partir de 2027 (Art. 348 da LC 214/25; `NT25:326-329`).
  - **Efeito:** nota de cliente do Simples normalmente **não** traz IBS/CBS ainda.
- **Data nova (05/10/2026):** NT 2025.002 v1.52, NT 2026.007 v1.10 e NT 2026.008 v1.00 passam para 26/10/2026 (homologação) e 16/11/2026 (produção). Fonte: `informe.aspx?ehCTG=false&Informe=GyPA/cEjrMk=`.

**Efeito por campo:**

| Campo | Efeito | Referência |
| --- | --- | --- |
| `det/imposto/IBSCBS` e `det/imposto/IS` | Grupos novos por item, opcionais | `XSD:5181`, `XSD:5186` |
| `total/IBSCBSTot` e `total/ISTot` | Grupos novos nos totais | `XSD:5617`, `XSD:5622` |
| `total/vNFTot` | Total "por fora" com IBS/CBS/IS; **`vNF` não muda de significado em 2026** | `XSD:5627`, `NT25:1440` |
| `ide/cMunFGIBS` | Novo, opcional | `XSD:111` |
| `ide/gCompraGov` e `ide/gPagAntecipado` | Novos, opcionais | `XSD:497`, `XSD:502` |
| `ide/dPrevEntrega` (B10a) e `ide/cIndOp` (B25d) | Novos | `NT25:661-735`; `dPrevEntrega` não localizei no XSD pela busca de nomes |
| `emit/ISUFemit` (C22) | Citado pela NT na v1.40 (`NT25:219-231`). **Procurei `ISUFemit` no XSD do PL 010f e não achei elemento com esse nome**; só existe `dest/ISUF` (`XSD:800`) | NÃO CONFIRMADO no esquema |
| `emit/IE` | Opcional: NT 2026.007 permite NF-e sem IE para contribuinte exclusivo do IBS/CBS (autorizada só na SVRS) | `S/nt_txt/nt2026007.txt:107-134`, `XSD:564` |

### Devolução por item: CONFIRMADO

- Grupo `det/DFeReferenciado` com `chaveAcesso` e `nItem` (`XSD:5294-5310`, `NT25:1373-1381`).
- Regra **VC02-14** (`NT25:3434-3446`): em `finNFe=4`, o referenciamento deve ser por item, e **fica proibido referenciar a nota em `refNFe`**.
- **Datas, com divergência a registrar:**
  - O PDF v1.52 diz produção em **03/11/2026** (`NT25:257-261` e `:274-275`).
  - O Informe de 05/10/2026 move as NTs da leva para 16/11/2026.
  - **NÃO CONFIRMADO** se a VC02-14 em particular acompanhou o adiamento. O Informe cita a NT inteira, não a regra.
- **O `impostoDevol` antigo** (`pDevol`, `vIPIDevol`) continua no esquema (`XSD:5194-5215`). **INFERÊNCIA:** o leitor pode ver os dois estilos de devolução durante a transição.

### Finalidades 5 e 6: CONFIRMADO

- `finNFe` 5 = nota de crédito, 6 = nota de débito (`XSD:185-195`, `TB`-equivalente `XSD:7471-7483`, `NT25:408-428`).
- O "sentido de débito e crédito é sempre o do emissor" (`NT25:412-418`).
- **Só existem no modelo 55** (`NT25:420`: "cria na NF-e modelo 55").
- `tpNFDebito` 01 a 08 (`XSD:7485-7507`). `tpNFCredito` 01 a 06, e o 06 é novo na v1.40 (`XSD:7509-7527`, `NT25:217`).
- Regra B25-80 (`S/nt_txt/nt2026008.txt:105-120`): nota com `finNFe` 5 ou 6 só pode ter IBS/CBS, **não pode ter ICMS, IPI, PIS, COFINS, II nem ISSQN**, com exceções por tipo.
- **Consequência para o leitor:** nota de crédito ou de débito vem com o item sem ICMS. O leitor não pode exigir `det/imposto/ICMS`.

### Outras NTs que mudam `ide`, `total` ou o item: CONFIRMADO

| NT | Efeito | Datas | Fonte |
| --- | --- | --- | --- |
| **2026.008 v1.00** | Cria `vUnComLiq`, `vProdLiq` (item) e `vProdLiqTot` (total), `vICMSPrevisto`. **A partir de 2027 os valores de IBS, CBS e IS compõem o `vProd` do item**, "exceto nas notas de importação" | Homologação 05/10/2026 → 26/10/2026; produção 03/11/2026 → 16/11/2026 (Informe); regra NB01-30 em 01/03/2027 | `nt2026008.txt:48-60`, `:135-162` |
| **2026.007 v1.10** | Emitente sem IE (contribuinte exclusivo de IBS/CBS) | Idem; autorização só pela SVRS | `nt2026007.txt:107-134` |
| **2026.004 v1.01** | Schema alfanumérico para CNPJ e chave | Produção 01/07/2026 | `nt2026004.txt:40-47` |
| **2023.002 v1.01** | NFC-e com emitente CPF (produtor rural), série 920-969; elimina denegação e lote na NFC-e | Produção 04/09/2023 (v1.00); SC avulsa 02/02/2026 | `pt_nt2023002_v101.txt:56-110` |
| **2020.001 v1.60** | Manifestação: 2 ocorrências por tipo; prazo conclusivo 90 dias | Produção 01/06/2026 | `pt_nt2020001_v160.txt:38-41` |
| **2024.001** (CRT-MEI) | `emit/CRT=4` | Título citado no espelho SVRS | NÃO li o PDF |

- Fonte da NT 2023.002: `exibirArquivo.aspx?conteudo=T3QyeMfpios%3D`. sha256: `b0cb9528bfaa6e0b5ac2986c879898eebcbb9457e97fcf0af985a00659649031`.
- Fonte da NT 2026.008: SVRS `tipoArquivo=3`, `NT_2026.008_v1.00_RTC_ValorLiquidoProduto.pdf`. sha256: `bc56e76ae5f3354f7ae636d87908840c5c685284f0f8f32bb29579f8124e44cd`.
- Fonte da NT 2026.007: SVRS `tipoArquivo=3`. sha256: `4a9d9de64504f4091c55e3e8a2d499116d4bac1a2009a874a7b9ce26d9fe8b10`.
- NÃO LI: NT 2023.001 (monofásico de combustível), NT 2024.003 (agro), NT 2025.001 (QR Code v3). Os efeitos delas no XSD estão em `XSD:5400-5425` (campos `qBCMono`, `vICMSMono` etc.), mas não li as NTs.
- NÃO LI: o Ato Conjunto RFB/CGIBS nº 8/2026, publicado em 01/10/2026, que "aprova diversas documentações técnicas" (`informe.aspx?...Informe=aG9hbbgK/JM=`).
- NÃO ENCONTRADO: texto oficial sobre **como `vNF` se comporta a partir de 2027**. A NT 2026.008 diz que IBS/CBS entram no `vProd` e **não** são somados de novo em `vNFTot`. Não diz o que ocorre com `vNF`.
  - A relação `vNF`/`vNFTot` em 2027 é **pendência para o Fred**.

---

## 5. NFC-e modelo 65

- **Mesmo esquema da NF-e. CONFIRMADO** (`XSD:51`, `TB:359-367`). O leiaute 3.00 já tinha `mod` 55 e 65 (`S/pl7a/ex/PL_007a/tiposBasico_v3.00.xsd:313-314`).
- **`dest` é opcional no esquema** (`XSD:734`) e, na NFC-e, a ausência é normal. Se informado, o CNPJ não pode ser igual ao do emitente (`ANX:3719`, E02-20, rejeição 220).
  - Com `indPres=4` (entrega a domicílio), o `dest` é obrigatório (`ANX:3715`, E01-20).
  - **Nuance sobre a armadilha 1:** para o **modelo 55**, o MOC 7.0 rejeita nota sem destinatário (regra E01-10, rejeição 719, `ANX:3714`; `ANX:510` diz "grupo obrigatório para NF-e modelo 55"). O esquema deixa opcional só porque é compartilhado com a NFC-e.
    - **INFERÊNCIA:** nota 55 autorizada sem `dest` não deveria existir. A DL-010 está certa em não tratar a ausência como malformação; vale registrar que isso é regra de validação do autorizador, não de esquema.
- **`infNFeSupl` com `qrCode` e `urlChave`:** `XSD:6641`, `XSD:6647`, `XSD:6669`. É obrigatório para a NFC-e (ZX02-10, rejeição 394, `ANX:5766`) e proibido na NF-e (ZX01-10, rejeição 393, `ANX:5764`).
  - Cinco padrões de QR Code convivem (`XSD:6652-6662`): v1, v2 on/offline, v3 on/offline. Servem para distinguir NFC-e de NF-e **pelo conteúdo**.
- Regras de validação que fixam o conteúdo de uma NFC-e (`ANX`):

| Campo | Valor exigido | Linha |
| --- | --- | --- |
| `tpNF` | 1 (saída) | 3386 |
| `idDest` | 1 | 3387 |
| `finNFe` | 1 | 3421 |
| `indFinal` | 1 | 3437 |
| `tpImp` | 4 ou 5 | 3392 |

- Item-level: NFC-e não pode usar `DFeReferenciado` (VC02-04, `NT25:3425`).
- **Emitente pode ser CPF** (produtor rural), com série 920-969 (`pt_nt2023002_v101.txt:98-110`). Isso importa porque a empresa pode ser pessoa física.
- **Eventos admitidos, CONFIRMADO em `MOC:1470-1472`:** o MOC diz que, conforme a cláusula décima terceira do Ajuste SINIEF 19/16, a NFC-e só admite "o Cancelamento e o Evento Prévio de Emissão em Contingência".
  - O **110112** (cancelamento por substituição) é variante do cancelamento prevista só para a NFC-e (`MOC:2445-2475`, introduzido pelo Ajuste SINIEF 07/18).
  - **A DL-010 está certa em "dois eventos"**, mas o conjunto de **códigos** aceitáveis é {110111, 110112, 110140}.
  - Os eventos da reforma dizem "Modelo: NF-e modelo 55" onde examinei (112110 em `NT25:3700`).
  - **NÃO ENCONTRADO** texto que declare explicitamente, para os demais eventos novos, que estão vedados na NFC-e.
- **A NFC-e não é mais denegada** desde o Ajuste SINIEF 10/2023 (`pt_nt2023002_v101.txt:275-296`). Emitente irregular leva rejeição 781, não aparece em `nfeProc`.
- **Lote:** a NFC-e não usa lote com mais de um documento. Não afeta a recepção.

---

## 6. Leiautes antigos: 1.10, 2.00, 3.00, 3.10

**Como reconhecer. CONFIRMADO**
- Atributo `versao` de `infNFe` (e de `nfeProc` e `protNFe`). Cada versão trava o valor no esquema:
  - `1\.10` em `S/pl5d/ex/leiauteNFe_v1.10.xsd:4676`.
  - `2\.00` em `S/pl6g/ex/PL_006g/leiauteNFe_v2.00.xsd:5791`.
  - `3\.00` em `S/pl7a/ex/PL_007a/leiauteNFe_v3.00.xsd:6783`.
  - `3\.10` em `S/pl8i2/ex/PL_008i2_CFOP_EXTERNO/leiauteNFe_v3.10.xsd:5899`.
  - `4\.00` em `XSD:7561-7569`.
- **O namespace é o mesmo** (`http://www.portalfiscal.inf.br/nfe`) em todas.
- **As raízes são as mesmas**: `nfeProc`, `NFe`, `enviNFe`. Mudam os nomes dos arquivos de esquema (`procNFe_v3.10.xsd`, por exemplo, `MOC:7125`).
- Pacotes lidos:

| Leiaute | Pacote | Arquivo | sha256 do zip |
| --- | --- | --- | --- |
| 1.10 | PL 5d | `exibirArquivo.aspx?conteudo=04BIflQt1aY=` | `b877b7d96d7fd940a5f455fc01fd6de450b47d38a6ffc48455d5158f2ff4e394` |
| 2.00 | PL 6g | `...conteudo=mOb%2Bmjeespc%3D` | `aa3e9f7df1219f4a1dc056259634f9cca7aa455df64f19e0769324f714d8f073` |
| 3.00 | PL 7a | `...conteudo=TZtY9OKF4PY%3D` | `aca60e51ab02c4cbc95a29a4532f84e962146e0002acec5746133dc0107d8f19` |
| 3.10 | PL 8i2 | `...conteudo=OriMsXS1nS0%3D` | `4089e22ea8ce88d56d33c36bda41f4f8ef517992cd93b197d22f83b84624fb30` |

**O que muda na estrutura (leitura direta dos XSD):**

| Item | 1.10 | 2.00 | 3.00 / 3.10 | 4.00 |
| --- | --- | --- | --- | --- |
| Padrão do `@Id` | `NFe[0-9]{44}` (`pl5d:3317`) | `NFe[0-9]{44}` (`pl6g:4401`) | `NFe[0-9]{44}` (`pl8i2:5002`) | `NFe[0-9]{6}[0-9A-Z]{12}[0-9]{26}` |
| Data de emissão | `dEmi` (data) | `dEmi` | `dhEmi` (data e hora com fuso) | `dhEmi` |
| `indPag` em `ide` | sim | sim | sim | **não**; vai para `pag/detPag` (`XSD:5971`) |
| `idDest`, `indFinal`, `indPres` | não | não | sim (3.00/3.10) | sim, mais `indIntermed` |
| Grupo `pag` | não | não | sim, `pag` com `maxOccurs=100` (`pl8i2:4582`) | `pag/detPag` e `vTroco` (`XSD:5971`, `XSD:6102`) |
| `emit/CRT` | não | sim | sim | sim |
| `dest` | obrigatório | obrigatório | opcional (`pl8i2:656`) | opcional |
| `dest/idEstrangeiro` | não | não | sim (3.10) | sim |
| Modelo 65 | não | não | sim (`tiposBasico_v3.00.xsd:314`) | sim |
| `infNFeSupl` (QR Code) | não | não | sim (`pl8i2:5012`) | sim |
| `CEST` em `prod` | não | não | opcional (`pl8i2:857`) | `cBarra`, `CEST`, `indEscala` |
| `ICMSTot` | sem `vFCP`, `vFCPST`, `vFCPSTRet`, `vIPIDevol` | idem | idem (`pl8i2:4025-4111`) | com esses campos |

- **Chave de acesso por versão, CONFIRMADO em `MOC:985-1013`:**
  - Até 1.10: cNF com 9 posições, sem `tpEmis`.
  - De 2.00 em diante: `tpEmis` entra e cNF cai para 8.
- **Recomendação para a recusa nomeada** (decisão de produto):
  - Ler `versao` **antes** de qualquer outra coisa. Fora de `4.00` → "NF-e em leiaute X.XX; só o leiaute 4.00 é aceito".
  - Dar mensagem própria quando o valor for `1.10`, `2.00`, `3.00` ou `3.10`, que são as versões que existiram.
  - Valor fora dessa lista → "versão desconhecida".
  - Esta recomendação é minha. As fontes não prescrevem o comportamento do importador.
- **Divergência pequena com a DL-010:** ela escreve "emit/CNPJ (ou CPF, desde o leiaute 4.00)". Em XSD, o `xs:choice` CNPJ|CPF do `emit` já existe no 1.10 (`pl5d` na seção `emit`, que li). O que mudou em 4.00 foi a regra da chave com CPF e a faixa de séries (`MOC:932-947`).
- Versões **3.00 e 3.10 convivem** com a 4.00 em arquivo histórico. Isso foi verificado nos esquemas, não em XML real.

---

## 7. Recomendação de escopo para a DL-080

### Primeiro corte (recepção)

1. **Reconhecimento pela raiz e pela versão**, nunca só pelo namespace.
   - Aceitar `nfeProc` (4.00).
   - Aceitar `procEventoNFe`.
   - Recusa nomeada para cada uma das raízes seguintes. A lista é minha, extraída de `MOC:5183`, `PROC` e dos pacotes:
     - `NFe` sem protocolo: "nota sem autorização".
     - `enviNFe`, `retEnviNFe` e `envEvento`: mensagens de transmissão.
     - `procInutNFe` e `retInutNFe`: inutilização. **Não é nota nem evento.** Tem nome, tipo e efeito próprios.
     - `resNFe` e `resEvento`: resumos da distribuição DF-e, sem itens.
     - `retConsSitNFe`.
2. **Só nota com protocolo** (`protNFe`).
   - `cStat` 100 e 150 → autorizada.
   - `cStat` 110, 301, 302, 303 → **proposta:** recusar com motivo nomeado "NF-e denegada, sem efeito fiscal" ou gravar marcada. É decisão de produto: **pergunta para o Fred.**
3. **Campos a extrair** (todos já têm caminho confirmado na seção 1):
   - Chave, `mod`, `serie`, `nNF`, `dhEmi`, `tpNF`, `finNFe`, `idDest`, `cUF`, `CRT`.
   - Emitente (CNPJ ou CPF) e destinatário (CNPJ, CPF ou `idEstrangeiro`, opcional).
   - Totais `vNF`, `vProd`, `vICMS`, `vST`, `vIPI`, `vPIS`, `vCOFINS`, `vDesc`, `vFrete`.
   - Protocolo (`cStat`, `nProt`, `dhRecbto`).
   - Valores com `Decimal` a partir de texto, padrão `TDec_1302`, 13 inteiros e 2 casas, sem sinal.
4. **IBS/CBS:** guardar o XML inteiro (como na fatia 1) e **extrair só a presença** de `IBSCBSTot` e de `det/imposto/IBSCBS`. Não interpretar até o Fred decidir o PE-39. Isso mantém a política da fatia 1.
5. **Eventos:**
   - Guardar qualquer `procEventoNFe`, inclusive órfão.
   - Aplicar apenas com `retEvento/cStat` em {135, 136, 155}.
   - Marcar a nota como cancelada por 110111 (qualquer modelo) e 110112 (NFC-e). Os dois pertencem ao conjunto que cancela.
   - Guardar sem efeito sobre a situação: CC-e, manifestações, eventos da reforma, 110001.
   - Unicidade do evento inclui `nSeqEvento`, que já está no `@Id`.
6. **Dedupe** por `(escritório, chave)`. **Identificador:** `infNFe/@Id` com o prefixo `NFe` (3 caracteres) e 44 posições.
7. **Fora do primeiro corte, para a escrituração da NF-e (DL posterior):**
   - CFOP, CST e CSOSN por item (leitura sim, interpretação não).
   - Itens, `DFeReferenciado`, notas de débito e de crédito como ajustes, devolução.
   - Classificação, apuração, livros, contabilização.
   - Manifestação do destinatário como ação do usuário (`DL-067:338`).
   - Validação de assinatura (`ds:Signature`) e do `digVal`: **o leitor atual não confere e o plano deve declarar o limite**, como a DL-010-F1 fez com o DV do `Id` da NFS-e.
   - Comparação `vNF` com a soma dos itens.
8. **Modelo 65:** aceitar. O que muda para o escritório é pouco, porque normalmente não há `dest`. **Pergunta para o Fred:** o escritório recebe NFC-e de clientes? A DL-010 mediu 618 NF-e modelo 55 e nenhuma NFC-e (RC-65 só cita "NF-e modelo 55").

### Riscos de isolamento

1. **Papel da empresa.** Hoje só existem `PRESTADOR` e `TOMADOR` (`models.py:77-79`). Para NF-e o certo é `EMITENTE` e `DESTINATARIO`, mais o `tpNF` do documento.
   - Casos a testar:

| Cliente é | `tpNF` | Visão do cliente (INFERÊNCIA) |
| --- | --- | --- |
| Emitente | 1 | Saída própria (611 dos 618 do acervo, RC-66) |
| Destinatário | 1 | Entrada de terceiro |
| Emitente | 0 | Entrada própria (importação, produtor rural etc.) |
| Destinatário | 0 | Raro; **não confirmei em fonte oficial** |

   - O `tpNF` é do ponto de vista do emitente. Quem usar `tpNF` como "entrada ou saída" do cliente sem olhar o papel inverte a direção para a nota em que ele é destinatário.
2. **A mesma nota em duas empresas do escritório.** Já é suportada: `VinculoDocumentoEmpresa` (`models.py:216-239`) e `_adicionar_vinculos_que_faltam` (`services.py:345-385`).
   - **Lacuna (INFERÊNCIA):** a unicidade `(documento, empresa)` (`models.py:235-238`) impede que a mesma `Empresa` tenha **dois papéis**. Em **transferência entre matriz e filial da mesma `Empresa`**, o `_vincular_participantes` (`services.py:336`) grava um vínculo só, como prestador. Para NF-e isso perde a informação de que a nota também entrou. Precisa de decisão.
3. **Mesmo CNPJ em dois escritórios.** Desde a DL-041 isso é possível (`test_dl041_mesmo_cnpj_dois_escritorios.py`). A restrição `(escritorio, identificador)` (`models.py:205-210`) continua certa. Os testes de NF-e devem repetir esse cenário.
4. **Nota de terceiros dentro do XML.** Só `emit` e `dest` identificam partes. **Não vincular** por `autXML` (até 10 CNPJs autorizados, `XSD:848`), `transporta`, `retirada` ou `entrega`, nem por `infAdic`. Nenhum desses é parte da operação.
5. **NFA-e (série 890-899):** a chave carrega o CNPJ da SEFAZ (seção 3). Identificar pelo `emit`, não pela chave.
6. **Evento órfão e `escritorio`.** O evento do NF-e trará `CNPJ|CPF` do autor (`EVT:29-34`) e `chNFe`. A tabela atual liga o evento a uma empresa só pelo autor (`services.py:423-440`). Para NF-e, o autor do cancelamento é o emitente; o da manifestação é o destinatário. **A situação "cancelada" continua sendo consultada por `(escritorio, chave)`,** o que isola bem.
7. **Mensagem de recusa idêntica** exista ou não a empresa em outro escritório (critério 27 da F1), mantida para NF-e.
8. **Tamanho.** O limite atual é 1 MB por XML (`services.py:62`). O esquema admite até 990 itens por nota (`XSD:867`). O MOC cita "aproximadamente 10 KB" por nota (`MOC` seção 5.7.3). **INFERÊNCIA:** notas grandes podem passar de 1 MB e seriam recusadas pelo limite genérico, que é de NFS-e. A mensagem de recusa não diz que o arquivo é uma NF-e legítima grande.

---

## Divergências com a DL-010

| # | DL-010 diz | Fonte oficial mostra |
| --- | --- | --- |
| 1 | "Pacote vigente PL_010f de 31/08/2026" | CONFIRMADO (`PL_010f_v1.04.zip`, "Publicado em 31/08/26"). Mas já há NT 2025.002 v1.52, NT 2026.007 v1.10 e **NT 2026.008 v1.00 de 01/10/2026**, e a 2026.008 cria campos que o PL 010f não tem. O pacote seguinte (que não achei) é esperado |
| 2 | "O bloco `dest` é opcional" (armadilha 1) | Correto no XSD (`XSD:734`). Nuance: o MOC 7.0 **rejeita** modelo 55 sem destinatário (RV E01-10, `ANX:3714`). Opcional é por causa da NFC-e |
| 3 | `emit/CPF` "desde o leiaute 4.00" | O `xs:choice` CNPJ|CPF já existe no XSD 1.10. A mudança de 4.00 foi a chave com CPF e as séries reservadas (`MOC:932-947`) |
| 4 | NFC-e "só admite dois eventos" | CONFIRMADO (`MOC:1470-1472`): Cancelamento e EPEC. O 110112 é uma variante do cancelamento só da NFC-e |
| 5 | Armadilha 2: raízes `envEvento` ou `procEventoNFe` | Correto. Faltam outras raízes no mesmo namespace que o leitor deve nomear: `procInutNFe`, `retInutNFe`, `resNFe`, `resEvento`, `retConsSitNFe`, `retEnviNFe` |
| 6 | Armadilha 5: cancelar não altera o XML da nota | Correto. Acréscimo: a confirmação da operação (210200) impede o cancelamento (`pt_nt2020001_v160.txt:111`) |
| 7 | Chave de acesso: "nada a corrigir" | CONFIRMADO (seção 3). Acréscimos: série 890-899 (CNPJ da SEFAZ), e as duas datas conflitantes entre a NT Conjunta (06/07/2026) e a NT 2026.004 (01/07/2026) |
| 8 | "MOC versão 7.0" como fonte | O MOC 7.0 é de 04/11/2020 (`pdfinfo`). Várias regras mudaram depois: manifestação com 90 dias (era 180), 2 ocorrências por tipo, fim da denegação na NFC-e |

**Divergências fora da DL-010, que o planejamento da DL-080 vai encontrar:**
- `DL-067:338` diz "confirmação, desconhecimento ou não realização em até 180 dias". A NT 2020.001 v1.60 diz **90 dias** desde 01/06/2026.
- `DL-067:405` diz "Devolução por item é exigida na NF-e desde 09/2026 (NT 2025.002 v1.40)". O PDF v1.52 diz **03/11/2026** em produção para a VC02-14. O Informe de 05/10/2026 adia a NT para 16/11/2026. Não está explícito se a regra acompanhou.
- `DL-067:905` lista os eventos novos, incluindo 211120? Não: lista 112110, 211110, 211124, 211128, 211130, 211140, 211150, 212110, 212120, 412120, 412130 e 110001, mas **omite** 112120, 112130, 112140 e 112150, que o esquema `Eventos_RTC.zip` traz e a NT lista (`NT25:3657-3661`).

---

## O que o código atual já faz e o que falta

### Já faz (VERIFICADO por leitura, nada executado)

- **Reconhecimento e recusa de NF-e.** `leitor.py:39` define `NS_NFE`. `leitor.py:330-331` devolve `ArquivoRecusado("tipo ainda não suportado: NF-e")` para qualquer raiz no namespace da NF-e. É nomeada, mas **só pelo namespace**: `nfeProc`, `NFe`, `procEventoNFe`, `envEvento` e `procInutNFe` recebem a mesma mensagem.
  - Testes: `test_leitor.py:138-140` e `test_receber_envio.py:803-818`. A NF-e sintética é `xml_sinteticos.py:222-231`.
  - **O leitor não confere versão de NF-e.**
- **Deduplicação.** `models.py:205-210` tem a restrição única `(escritorio, identificador)`. `services.py:520-547` converte o `IntegrityError` em "duplicado". `services.py:443-471` sinaliza "conteúdo DIFERENTE" quando o SHA muda. O XML nunca é sobrescrito.
- **Evento órfão.** `models.py:245-303` e `services.py:423-440` aceitam evento sem empresa (RC-70). `services.py:975-1060` deriva a situação "cancelada" por consulta (`Exists` por `escritorio` e `chave_nfse = Substr(identificador, 4)`), independente da ordem de chegada.
- **Identificação de empresa em um ponto só.** `services.py:201-235` (mapa por escritório, em memória, inclui `Estabelecimento`), `:238-274` e `:277-305`. Filtra por escritório na montagem do mapa. Aceita CNPJ e CPF.
- **Vínculos múltiplos.** `services.py:314-342` e `:345-385` criam e completam vínculos. Mensagem de recusa idêntica para empresa inexistente ou de outro escritório (`services.py:195-198`, 338-341).
- **Limites e segurança.** `uploads.py` (limite de corpo), `services.py:60-63` (50 MB, 2.000 arquivos, 1 MB por XML, 200 MB descompactados), `defusedxml` com DTD proibido (`leitor.py:266-309`), savepoint por arquivo (`services.py:509`).

### Falta para aceitar NF-e (INFERÊNCIA minha sobre o código)

1. **`TipoDocumentoFiscal`** tem só `NFSE_NACIONAL` (`models.py:56-62`). O comentário diz "pronto para a fatia 2". Faltam NF-e 55 e NFC-e 65.
2. **`DocumentoFiscal` é de NFS-e** (`models.py:131-199`): `prestador_*`, `tomador_*`, `v_serv`, `v_liq`, `tp_ret_issqn`, `d_competencia`, `versao` com `max_length=4`. NF-e precisa de `mod`, `serie`, `nNF`, `tpNF`, `finNFe`, `vNF` e o resto dos totais, emitente e destinatário (opcional), protocolo. Decisão: tabela própria ou tabela comum com campos genéricos.
3. **`PapelDocumento`** só tem `PRESTADOR` e `TOMADOR` (`models.py:77-79`).
4. **`EventoFiscal.codigo`** guarda `e` + 6 dígitos (NFS-e, `models.py:267-269`). O código da NF-e é `tpEvento` de 6 dígitos puros (ex.: 110111). Mapear sem colisão com os códigos de NFS-e exige decisão, ou tabela separada.
5. **`CODIGOS_QUE_CANCELAM`** (`services.py:975`) é `{e101101, e105102, e105104, e305101}`, só NFS-e. Precisa de conjunto por tipo de documento.
6. **`EventoFiscal.chave_nfse`** (`models.py:271`) é nomeada e dimensionada para 50 dígitos (NFS-e). Uma chave de NF-e (44) cabe por tamanho, mas a comparação em `services.py:1015-1020` usa `Substr(identificador, 4)`. Funciona para `NFe`+44 por coincidência de prefixo de 3 caracteres, não por projeto.
7. **O leitor** não tem: leitura de `nfeProc`/`procEventoNFe`, padrão de decimal da NF-e (`_FORMATO_DECIMAL` é de NFS-e, `leitor.py:73`), padrão de `Id`, validação de DV da chave (módulo 11 com ASCII-48), leitura de `protNFe`, tratamento de `dest` opcional.
8. **Recusa por versão** de NF-e: não existe.
9. **Telas e API** do módulo (`views_web.py`, `api.py`) são de NFS-e. Não examinei quanto delas depende do tipo.

### O que não consegui determinar

- Pacote PL posterior ao 010f (esperado com a NT 2026.008).
- Se a regra VC02-14 acompanhou o adiamento do Informe de 05/10/2026.
- O texto da NT 2025.001 v1.03 (QR Code 3), da NT 2024.001 (CRT-MEI), da NT 2023.001 (monofásico), da NT 2024.003 e do Ato Conjunto RFB/CGIBS nº 8/2026. Não li.
- O efeito sobre a validade da nota de cada evento novo da reforma além do que o texto da NT diz (nenhum descrito como cancelamento).
- Comportamento do `vNF` a partir de 2027.
- XML real de NF-e de leiaute 3.00 ou 3.10. Só olhei os esquemas.
- Se o escritório recebe NFC-e (o RC-65 só cita NF-e modelo 55).

### Perguntas que só o Fred responde

1. Nota **denegada** (cStat 110/301/302/303): recusar com motivo nomeado ou gravar marcada?
2. Nota **sem protocolo** (`NFe` pura): recusar? A recomendação é recusar, mas é decisão de produto.
3. O escritório recebe **NFC-e**?
4. Transferência entre matriz e filial da mesma empresa: a recepção deve registrar os dois papéis?

Artefatos baixados e extraídos em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/nfe/`, cada pacote no seu subdiretório. Nada foi escrito dentro do repositório.

Fontes:
- https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w= (esquemas)
- https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY= (notas técnicas)
- https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false&Informe=GyPA/cEjrMk= (Informe de 05/10/2026)
- https://dfe-portal.svrs.rs.gov.br/Nfe/Documentos (espelho SVRS: NTs até 01/10/2026; a lista de esquemas dele termina em 23/07/2026 e é anterior ao 010d–f, por isso usei o Portal Nacional para esquemas)
