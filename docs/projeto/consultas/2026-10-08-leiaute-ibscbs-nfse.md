# Leiaute IBS/CBS da NFS-e nacional — pesquisa em fonte oficial, 08/10/2026

Pesquisa feita por `auxiliar-pesquisa` a pedido do `arquiteto-senior`, para a
[DL-073](../../planos/DL-073-validador-ibscbs.md). Registro integral. Os
caminhos e regras abaixo foram lidos nos documentos oficiais citados; o que é
**inferência** do pesquisador está marcado como tal. Os arquivos baixados
ficaram fora do repositório (pasta temporária da sessão) e **não** são
versionados aqui.

Tudo foi consultado em 08/10/2026. Os downloads estão em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/ibscbs/`. Não alterei nada no repositório.

## Resumo para quem vai implementar

1. **Só o leiaute 1.01 tem o grupo.** O XSD 1.00 oficial não tem nenhuma ocorrência de `IBSCBS`. O validador deve tratar nota 1.00 como "sem grupo possível".
2. **A posição de CST e cClassTrib mudou entre duas fontes oficiais.**
   - XSD 1.01 em produção (09/02/2026): `.../valores/trib/gIBSCBS/CST`.
   - Anexo VI v1.04.01 da NT 009 (11/09/2026): `.../valores/trib/CST`, fora de `gIBSCBS`.
   - **Inferência:** a NT 009 ainda não está no XSD de produção. Não encontrei XSD para ela. O leitor deve aceitar as duas posições.
3. **Formato dos números.** Os decimais são strings com pontos fixos de casas (`TSDec2V2` e afins). `0.9` é inválido pelo XSD e `0.90` é válido. O leitor deve usar `Decimal` e tolerar as duas formas.
4. **Não há regra oficial de arredondamento** nos documentos que li. Veja o item 5.

## 1. Fontes consultadas

| # | URL exata | Título e versão | Publicação | Consulta |
|---|---|---|---|---|
| 1 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/nfse-esquemas_xsd-v1-01-20260209.zip | XSD NFS-e v1.01 (pastas `Schemas/1.00` e `Schemas/1.01`). Arquivos internos datados de 11/02/2026. | 09/02/2026 (pelo nome do arquivo) | 08/10/2026, HTTP 200 |
| 2 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/anexo_i-sefin_adn-dps_nfse-snnfse-v1-01-20260209.xlsx | Anexo I, leiaute DPS/NFS-e e regras de negócio, v1.01 (produção) | 09/02/2026 (pelo nome) | HTTP 200 |
| 3 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx | Anexo VI, Leiautes e RN RTC IBSCBS v1.04.01 (NT 009) | Não consta no arquivo. A página RTC foi atualizada em 02/10/2026. | HTTP 200 |
| 4 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nota-tecnica-009-se-cgnfs-e-v-1-01.pdf | Nota Técnica nº 009, v1.01 (SE/CGNFS-e) | 11/09/2026 | HTTP 200 (a 1ª tentativa deu `curl: (35) Recv failure: Connection reset by peer`; a 2ª funcionou) |
| 5 | https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-e-respostas-nfs-e-v-1-1-20260922.pdf | Perguntas e Respostas v1.1 | 22/09/2026 | HTTP 200 |
| 6 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc e https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual | Páginas índice. "Atualizado em" 02/10/2026 17h57 (RTC) e 15/08/2026 09h58 (Documentação Atual). | | HTTP 200 |
| 7 | https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=jxTMMQeEVM8= | Informe Técnico 2025.002 v1.60 (tabelas cClassTrib, CST e crédito presumido), 12 páginas | 22/06/2026 | HTTP 302 para definir cookie, depois 200 (PDF) |
| 8 | https://dfe-portal.svrs.rs.gov.br/DFE/ClassificacaoTributaria | Portal da Conformidade Fácil, tabela online de cClassTrib | A página não mostra versão. Há itens com publicação até 2026-10-01. | HTTP 200 (HTML de 4 MB com os dados embutidos) |
| 9 | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm | LC 214/2025, arts. 343 e 346 | | 1ª tentativa `curl: (52) Empty reply from server`; com User-Agent HTTP 200 |

Também baixei, como contexto: NT 001 v1.0 (01/08/2024), NT 003 v1.2 (04/07/2025), Anexo VII (IndOp v1.03.00 NT009) e Anexo C (IndOp v1.01).

## 2. Caminhos XPath

**Namespace de todos os elementos:** `http://www.sped.fazenda.gov.br/nfse`. O XSD tem `elementFormDefault="qualified"`. É o mesmo `NS_NFSE` de `apps/fiscal/leitor.py:30`.

Raiz: `/NFSe[@versao='1.01']/infNFSe`. O atributo `versao` aceita `1\.00|1\.01` (`TVerNFSe`). Tudo foi lido de `x1/Schemas/1.01/tiposComplexos_v1.01.xsd`. As linhas abaixo são dessa fonte.

### 2.1 Grupo gerado pelo sistema, na NFS-e (`TCRTCIBSCBS`, linhas 142 e 287 em diante)

Prefixo: `NFSe/infNFSe/IBSCBS`. A cardinalidade "XSD 1.01" vem do XSD. A coluna "Anexo VI v1.04.01" vem do layout da NT 009.

| Tag (literal) | XSD 1.01 | Anexo VI v1.04.01 | Tipo e tamanho |
|---|---|---|---|
| `IBSCBS` | 0..1 | 0-1 | `TCRTCIBSCBS` |
| `cLocalidadeIncid` | 1..1 | 0-1 | `TSCodMunIBGE` (7 dígitos) |
| `xLocalidadeIncid` | 1..1 | 0-1 | `TSDesc600` (1 a 600 caracteres) |
| `pRedutor` | 0..1 | 0-1 | `TSDec2V2` |
| `valores` | 1..1 | 0-1 | `TCRTCValoresIBSCBS` |
| `valores/vBC` | 1..1 | 0-1 | `TSDec15V2` |
| `valores/uf/pIBSUF` | 1..1 | 1-1 | `TSDec2V2` |
| `valores/uf/pRedAliqUF` | 0..1 | 0-1 | `TSDec3V2` |
| `valores/uf/pAliqEfetUF` | 1..1 | 1-1 | `TSDec2V2` |
| `valores/mun/pIBSMun` | 1..1 | 1-1 | `TSDec2V2` |
| `valores/mun/pRedAliqMun` | 0..1 | 0-1 | `TSDec3V2` |
| `valores/mun/pAliqEfetMun` | 1..1 | 1-1 | `TSDec2V2` |
| `valores/fed/pCBS` | 1..1 | 1-1 | `TSDec2V2` |
| `valores/fed/pRedAliqCBS` | 0..1 | 0-1 | `TSDec3V2` |
| `valores/fed/pAliqEfetCBS` | 1..1 | 1-1 | `TSDec2V2` |
| `totCIBS/vTotNF` | 1..1 | 1-1 | `TSDec15V2` |
| `totCIBS/gIBS/vIBSTot` | 1..1 | 0-1 | `TSDec15V2` |
| `totCIBS/gIBS/gIBSUFTot/vIBSUF` | 1..1 | 1-1 (dentro de grupo 0-1) | `TSDec15V2` |
| `totCIBS/gIBS/gIBSUFTot/vDifUF` | 0..1 | 0-1 | `TSDec15V2` |
| `totCIBS/gIBS/gIBSMunTot/vIBSMun` | 1..1 | 1-1 (dentro de grupo 0-1) | `TSDec15V2` |
| `totCIBS/gIBS/gIBSMunTot/vDifMun` | 0..1 | 0-1 | `TSDec15V2` |
| `totCIBS/gCBS/vCBS` | 1..1 | 0-1 | `TSDec15V2` |
| `totCIBS/gCBS/vDifCBS` | 0..1 | 0-1 | `TSDec15V2` |
| `totCIBS/gIBS/gIBSCredPres/{pCredPresIBS,vCredPresIBS}` | grupo 0..1 | 0-1 | `TSDec2V2` e `TSDec15V2` |
| `totCIBS/gCBS/gCBSCredPres/{pCredPresCBS,vCredPresCBS}` | grupo 0..1 | 0-1 | `TSDec2V2` e `TSDec15V2` |
| `totCIBS/gTribRegular/{pAliqEfeRegIBSUF,vTribRegIBSUF,pAliqEfeRegIBSMun,vTribRegIBSMun,pAliqEfeRegCBS,vTribRegCBS}` | grupo 0..1 | 0-1 | `TSDec2V2` e `TSDec15V2` |
| `totCIBS/gTribCompraGov/{pIBSUF,vIBSUF,pIBSMun,vIBSMun,pCBS,vCBS}` | grupo 0..1 | 0-1 | idem |

Na NFS-e, o IBS é separado em estadual (`uf`, `gIBSUFTot`) e municipal (`mun`, `gIBSMunTot`).

### 2.2 Grupo declarado pelo emitente, na DPS embutida

Prefixo: `NFSe/infNFSe/DPS/infDPS/IBSCBS` (`TCRTCInfoIBSCBS`, linha 2207 em diante). Todas as tags abaixo estão no XSD 1.01.

| Tag (literal) | Cardinalidade | Tipo e valores |
|---|---|---|
| `finNFSe` | 1..1 | enum `0` (regular) |
| `indFinal` | 0..1 | `0` ou `1` |
| `cIndOp` | 1..1 | 6 dígitos |
| `tpOper` | 0..1 | `1` a `5` |
| `gRefNFSe/refNFSe` | 0..1, e 1 a 99 chaves | `TSChaveNFSe` |
| `tpEnteGov` | 0..1 | `1` a `4` |
| `indDest` | 1..1 | `0` ou `1` |
| `dest` | 0..1 | `TCRTCInfoDest` |
| `imovel` | 0..1 | `TCRTCInfoImovel` |
| `valores` | 1..1 | |
| `valores/gReeRepRes` | 0..1 | |
| `valores/trib` | 1..1 | |
| `valores/trib/gIBSCBS` | 1..1 | `TCRTCInfoTributosSitClas` |
| **`valores/trib/gIBSCBS/CST`** | 1..1 | `[0-9]{3}` |
| **`valores/trib/gIBSCBS/cClassTrib`** | 1..1 | `[0-9]{6}` |
| `valores/trib/gIBSCBS/cCredPres` | 0..1 | `[0-9]{2}` |
| `valores/trib/gIBSCBS/gTribRegular/{CSTReg,cClassTribReg}` | grupo 0..1, campos 1..1 | 3 e 6 dígitos |
| `valores/trib/gIBSCBS/gDif/{pDifUF,pDifMun,pDifCBS}` | grupo 0..1, campos 1..1 | `TSDec3V2` |

**Mudança da NT 009** (item 2.16 da NT e planilha `LEIAUTE DPS_NFS-e - RT`):
- `valores/trib/CST` e `valores/trib/cClassTrib` ficam 1-1 e o `gIBSCBS` passa a 0-1.
- `cIndOp` passa a 0-1.
- `finNFSe` sai desse grupo. O `indDest` e o `dest` sobem para `infDPS`.

### 2.3 Tipos decimais (`tiposSimples_v1.01.xsd`, literal)

- **`TSDec2V2`:** `0|0\.[0-9]{2}|[1-9]{1}[0-9]{0,1}(\.[0-9]{2})?`
- **`TSDec3V2`:** `0|0\.[0-9]{2}|[1-9]{1}[0-9]{0,2}(\.[0-9]{2})?`
- **`TSDec15V2`:** `0|0\.[0-9]{2}|[1-9]{1}[0-9]{0,14}(\.[0-9]{2})?`

### 2.4 Indicadores de regime e de "destaque informativo 2026"

- **No XSD 1.01 não existe tag de destaque informativo.** O nome `verCalcIBSCBS` e as outras listadas abaixo têm 0 ocorrências no `tiposComplexos_v1.01.xsd`.
- **Só no Anexo VI v1.04.01 (NT 009), não no XSD:**
  - `NFSe/infNFSe/verCalcIBSCBS` (0-1, caractere de 1 a 20): versão da calculadora que gerou a nota.
  - `.../DPS/infDPS/prest/regTrib/regApIBSCBSSN` (0-1): valores `1`, `2` e `3`.
  - `NFSe/infNFSe/IBSCBS/totCIBS/gTribSN/{pIBSSN,vIBSSN,pCBSSN,vCBSSN}`.
  - `.../valores/vReceitaBrutaSN`.
  - `.../IBSCBS/indZFMALC`.
  - `.../IBSCBS/indDoacao`.
  - `.../valores/vCalcAjusteBCIBSCBS`.
- **Fórmula de `vTotNF`** (no XSD e no Anexo VI): `vTotNF = vLiq` em 2026, e `vLiq + vCBS + vIBSTot` a partir de 2027.

## 3. Regras de validação oficiais

Todas têm efeito "Rej." (rejeita) e aplicação "Obrig.", nas planilhas `RN DPS_NFS-e`. Dois conjuntos aparecem:
- **Anexo I v1.01 (produção).** Marcado "(prod)" abaixo.
- **Anexo VI v1.04.01.** Marcado "(NT009)".

**Presença do grupo**
- **E1515 (prod e NT009):** "É obrigatório informar o grupo de informações de IBS/CBS da NFS-e quando o grupo de informações de IBS/CBS da DPS for informado."
- **E1517 (prod e NT009):** "Não é permitido informar o grupo de informações de IBS/CBS da NFS-e quando o grupo de informações de IBS/CBS da DPS não for informado."
- **E0850:** "É permitido declarar informações de IBS/CBS somente a partir da data de competência 01/01/2026."
- **E0322:** é obrigatório informar um item da NBS se houver qualquer informação de IBS/CBS.

**Presença condicionada a ind_gIBSCBS (NT009)**
- **E1518:** proíbe `cLocalidadeIncid` quando `ind_gIBSCBS = 0`.
- **E1524 e E1525:** proíbem ou exigem os campos de `valores` conforme `ind_gIBSCBS`.
- **E1526:** proíbe `vBC` quando `ind_gIBSCBS = 0`.
- **E1562 e E1563:** o mesmo para o grupo `gIBS`.
- **E1573 e E1574:** o mesmo para o grupo `gCBS`.
- **E0859 e E0860:** o mesmo para `cIndOp`.
- **E0960 e E0961:** o mesmo para `gIBSCBS` da DPS.

**CST e cClassTrib**
- **E0958 e E0969:** "cClassTrib para IBS/CBS incorreto para operação de prestação de serviços." Validação via Calculadora (`validoParaSiglaDfeInformado = false`).
- **E0964 e E0965:** `gTribRegular` não deve ou deve ser informado, conforme `exigeGrupoTributacaoRegular`.
- **E0971:** diferimento só se permitido (`permiteDiferimento`).
- **E1583 e E1584:** o mesmo para `gTribRegular` na NFS-e.
- **E0901:** `cIndOp` inexistente na tabela do Anexo C.

**Cálculo (prod e NT009; comparação com a Calculadora, "Margem de erro de R$ 0,01" na coluna de observações)**
- **E1530:** "Valor da Base de cálculo para IBS/CBS incorreto."
  - Fórmula em prod: `vBC = vServ - descIncond - vCalcReeRepRes - vISSQN - vPIS - vCOFINS` em 2026, e sem PIS e COFINS de 2027 a 2032.
  - A NT009 usa `vCalcAjusteBCIBSCBS` e `+ vAjusteBCIBSCBSComExt`.
- **E1539:** `pIBSUF` incorreta.
- **E1577:** `pAliqEfetUF` incorreta.
- **E1578:** `pIBSMun` incorreta.
- **E1549:** `pAliqEfetMun` incorreta.
- **E1558:** `pCBS` incorreta.
- **E1554:** `pAliqEfetCBS` incorreta.
- **E1556:** "Valor total do IBS incorreto."
- **E1568:** "Valor total do IBS estadual incorreto."
- **E1572:** "Valor total do IBS municipal incorreto."
- **E1582:** "Valor total da CBS da União incorreto." (consta só "CALCULADORA", sem margem na coluna).
- **E1555:** "Valor total da NFS-e está incorreto." (`vTotNF`).
- **Reduções de alíquota:** E1540, E1541, E1543 e E1557 (UF); E1545 a E1548 (Município); E1550 a E1553 (CBS).
- **Diferimento:** E1565, E1567, E1569, E1570, E1571 e E1581.
- **Tributação regular:** E1585 a E1590.
- **Compra governamental:** E1522, E1600 e E1602 a E1607.
- **Crédito presumido:** E1560 e E1575.

**P&R sobre obrigatoriedade (itens 15.1, 15.2 e 15.4)**
- **Cronograma:** a maioria dos serviços LC 116 passa a ter destaque obrigatório em 01/10/2026. Outras categorias ficam para 01/12/2026. Optantes do Simples que aderirem voluntariamente ficam para 01/01/2027.
- **Consequência da ausência:** "até 31/12/2026, a ausência do IBS/CBS não rejeita o documento fiscal — mas evidencia 'desconformidade'".
- **Se o grupo for informado:** "todo o conjunto de validações de conteúdo desses grupos passa a ser aplicado normalmente".
- **Nota no Anexo VI:** o campo `tpRetPisCofins` cita "grupos IBSCBS se tornarem obrigatórios (01/10/2026) para a autorização/recepção".

## 4. Tabela CST e cClassTrib

- **Onde está a tabela:** Informe Técnico 2025.002 v1.60, de 22/06/2026, PDF no portal NF-e (fonte 7).
  - O PDF só descreve as colunas, com mais de 170 códigos de cClassTrib, mas não os lista.
  - As tabelas estão online em https://dfe-portal.svrs.rs.gov.br/DFE/TabelaClassificacaoTributaria e em https://consumo.tributos.gov.br/servico/calcular-tributos-consumo/calculadora/classificacoes-tributarias (não abri esses dois).
  - O JSON oficial fica em https://dfe-portal.svrs.rs.gov.br/CFF/Servicos, com acesso por certificado digital (não testei).
- **Formato de download:** a página tem botões "CSV", "Excel" e "JSON" gerados no navegador (xlsx.js). Não obtive uma URL de arquivo direta.
- **O que consegui extrair:** o HTML da fonte 8 traz um JSON embutido (`var dadosOriginais`). Salvei em `.../ibscbs/cclasstrib.json`.
  - São 18 CST e 173 cClassTrib. Destes, 73 têm `IndNfse = true`.
  - Três códigos, 220001 a 220003, têm fim de vigência em 2026-01-01.
  - A maior `DthPublicacao` é 2026-10-01, depois da v1.60 do Informe. **Inferência:** a tabela online é mais nova que o PDF v1.60.
- **Colunas do JSON (literais):** `CodClassTrib, NomeClassTrib, IndTribRegular, IndPermiteCredPres, PercRedIbs, PercRedCbs, DthPublicacao, DthIniVig, DthFimVig, Cst, NomeReduzido, IndNfse, IndNfsvia, NroAnexo, TipoAliq, IndEstornoCred, TipoRbSn, TipoDoacao`, entre outras.
- **Não há campo `ind_gIBSCBS` no JSON.** O Informe define esse indicador (CST) e o JSON tem `IndExigeTrib` no nível do CST. **Inferência:** `IndExigeTrib` corresponde a `ind_gIBSCBS`, porque ele é `false` exatamente nos CST 400, 410, 820 e outros, e a NT 009 diz que esses CST não exigem `gIBSCBS`. Isso não está confirmado em documento.

Cinco linhas literais (campos selecionados; `IndNfse` é `true` em todas):

| Cst | CodClassTrib | NomeClassTrib (resumido) | PercRedIbs | PercRedCbs | DthIniVig |
|---|---|---|---|---|---|
| 000 | 000001 | Situações tributadas integralmente pelo IBS e CBS. | 0.0 | 0.0 | 2025-05-05 |
| 000 | 000006 | Situações tributadas integralmente pelo IBS e CBS realizadas por autônomo | 0.0 | 0.0 | 2026-01-01 |
| 010 | 010001 | Operações do FGTS não realizadas pela Caixa Econômica Federal… | 0.0 | 0.0 | 2025-05-05 |
| 011 | 011003 | Intermediação de planos de assistência à saúde… | 60.0 | 60.0 | 2025-05-05 |
| 400 | 400001 | Fornecimento de serviços de transporte público coletivo de passageiros… | 0.0 | 0.0 | 2025-05-05 |

## 5. Alíquotas de teste de 2026 e arredondamento

- **IBS 0,1% (estadual):** LC 214/2025, art. 343, caput: "o IBS será cobrado mediante aplicação da alíquota estadual de 0,1% (um décimo por cento)". Vale para fatos geradores de 1º/01 a 31/12/2026. Texto lido em planalto.gov.br.
- **CBS 0,9%:** LC 214/2025, art. 346: "a CBS será cobrada mediante aplicação da alíquota de 0,9% (nove décimos por cento)".
- **Ano 2026 no Informe 2025.002 v1.60, seção 05:** `pIBSUF` 0,1, `pIBSMun` 0 e `pCBS` 0,9.
  - O IBS de 2026 tem componente municipal zero.
  - Em 2027 e 2028 o IBS é 0,05 estadual mais 0,05 municipal (art. 344). A CBS fica "Aguardar Legislação".
- **Arredondamento:** não obtido. Procurei "arredond" e "trunc" no Anexo I, no Anexo VI, na NT 009, no Informe 2025.002 e no P&R, e não achei nada. O que existe:
  - o tipo dos valores (2 casas decimais);
  - as fórmulas do XSD, como `vIBSUF = vBC x (pIBSUF ou pAliqEfetUF)`, sem método de arredondamento;
  - a comparação com a Calculadora com "Margem de erro de R$ 0,01".
- **Consequência:** o validador deve comparar `vBC x alíquota` com o valor declarado usando tolerância de R$ 0,01. Não deve inventar uma regra de arredondamento.

## 6. O que não foi obtido

- **XSD correspondente ao Anexo VI v1.04.01 (NT 009).** Não encontrei. O XSD mais novo que consegui ler tem `IBSCBS` e `TCRTCInfoTributosSitClas` com `CST` dentro de `gIBSCBS`, o que difere da NT 009. O cronograma de implantação da NT 009 "será publicado" (texto da NT).
- **O pacote `nfse-esquemas_xsd-rtc-v1-00-20251210.zip`.** Está em outra pasta do portal (`producao-restrita/`). Tem o mesmo desenho de `IBSCBS` do pacote de fevereiro de 2026. As diferenças que vi são só de texto e na ordem de elementos fora do grupo.
- **Página `.../documentacao-tecnica/producao-restrita`.** A requisição deu `curl: (35) Recv failure: Connection reset by peer`, por falha da conexão com o proxy, e eu não repeti.
- **NT 004, 005, 006, 007, 008 e 010 e o Anexo VIII.** Não li. Baixei as NT 001 e 003 e a 009, só para busca de texto.
- **Arquivo CSV ou XLSX direto da tabela cClassTrib.** O botão de download é gerado em JavaScript (o WebFetch devolveu só os nomes dos botões). O JSON oficial exige certificado digital e eu não testei.
- **Divergências entre fontes:**
  - A NT 009 cita "AnexoVII-IndOp_IBSCBS_V1.02.01", mas a página RTC lista a v1.03.00 NT009.
  - O P&R 15.3 descreve `gCBS`, `gDevTrib`, `gDeson`, `cstCBSDeson` e `cClassTribCBSDeson` como "estrutura confirmada no schema oficial". Isso não existe no XSD 1.01 que li. Provavelmente são nomes do JSON da Calculadora. Não usar esses nomes.
- **Texto do Ato Conjunto RFB/CGIBS nº 4/2026.** Só o P&R o cita. Não li o ato.
