# DL-080 — Fiscal: recepção de NF-e (modelo 55) e NFC-e (modelo 65)

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170); etapa
8 do roteiro de execução do [DL-067](DL-067-plano-do-modulo-fiscal.md) e
**fatia 2** da [DL-010](DL-010-recepcao-de-documentos-fiscais.md). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) — documento de outra empresa importado
para a empresa errada, ou nota cancelada tratada como válida, contamina tudo
o que vier depois. Auditoria independente: uma rodada, uma correção, uma
reconferência.

**Recepção e conferência, nunca escrituração:** a NF-e entra, é deduplicada,
ligada às empresas do escritório e mostrada para conferência. Classificar,
escriturar, apurar e contabilizar ficam para a etapa seguinte.

## Base

[Pesquisa do leiaute da NF-e](../projeto/consultas/2026-10-09-leiaute-nfe.md),
feita em 09/10/2026 no Portal Nacional da NF-e e no espelho da SVRS: pacote
de esquemas vigente **PL 010f** (31/08/2026, leiaute 4.00), MOC 7.0, NT
2025.002 v1.52, NT 2026.004, 2026.007 e 2026.008, NT 2020.001 v1.60, NT
Conjunta 2025.001 (CNPJ alfanumérico) e os esquemas de evento (PL 010d e
eventos da reforma), com arquivo, linha e sha256 de cada um. O acervo do
escritório tinha 618 NF-e modelo 55, 611 delas de saída (DL-010).

Correções que a pesquisa fez a documentos nossos:

- **DL-067:** a manifestação conclusiva do destinatário tem prazo de **90
  dias** desde 01/06/2026 (era 180), e cada tipo admite duas ocorrências.
- **DL-067:** a lista de eventos da reforma omite 112120, 112130, 112140 e
  112150.
- **NT 2025.002:** as datas da v1.52 foram adiadas por informe de
  05/10/2026, para 26/10/2026 em homologação e 16/11/2026 em produção.

## Decisão de desenho: tabelas próprias para a NF-e

`DocumentoFiscal`, `VinculoDocumentoEmpresa` e `EventoFiscal` são da NFS-e:
competência, valor do serviço e retenção são obrigatórios, e receita, ISS,
pré-DAS e serviços tomados os consultam presumindo NFS-e. A NF-e ganha
**tabelas próprias** (documento, vínculo com a empresa, evento) e reaproveita
o lote de recepção, o resultado por arquivo, a identificação da empresa em um
ponto só, os limites e a leitura segura do XML. Assim, nenhuma NF-e aparece
por engano num cálculo de NFS-e.

## Escopo

1. **Reconhecimento pela raiz e pela versão**, nunca só pelo namespace:
   - aceitos: `nfeProc` no leiaute 4.00 e `procEventoNFe`;
   - recusas nomeadas, uma para cada caso:
     - nota sem autorização (`NFe` sem protocolo);
     - mensagens de transmissão (`enviNFe`, `retEnviNFe`, `envEvento`);
     - inutilização (`procInutNFe`, `retInutNFe`);
     - resumos da distribuição (`resNFe`, `resEvento`);
     - consulta de situação (`retConsSitNFe`);
     - leiautes 1.10, 2.00, 3.00 e 3.10, cada um nomeado;
     - versão desconhecida.
2. **Conferências da leitura:**
   - chave com 44 posições no padrão do XSD;
   - dígito verificador pelo módulo 11 com `ASCII − 48`, reaproveitando o
     validador da DL-011;
   - `infNFe/@Id` igual ao `protNFe/infProt/chNFe`;
   - valores pelo padrão `TDec_1302` (até 13 inteiros, duas casas, sem
     sinal), em `Decimal`;
   - campo ausente fica ausente, nunca zero.
3. **Protocolo:**
   - `cStat` 100 ou 150: autorizada.
   - Denegada (110, 301, 302 ou 303): recusada com o motivo "NF-e denegada —
     sem efeito fiscal" (HI-109).
   - Outro `cStat`: recusada com o código.
4. **Campos extraídos:**
   - identificação: chave, modelo, série, número, `dhEmi`, `tpNF`, `finNFe`
     (e `tpNFDebito`/`tpNFCredito`), `idDest`, `cUF`;
   - emitente: CNPJ ou CPF, nome, CRT;
   - destinatário: CNPJ, CPF ou `idEstrangeiro`, e nome, tudo opcional;
   - totais: `vNF`, `vProd`, `vICMS`, `vST`, `vIPI`, `vPIS`, `vCOFINS`,
     `vDesc`, `vFrete`;
   - protocolo: `cStat`, `nProt`, `dhRecbto`;
   - itens: só a quantidade;
   - IBS/CBS: só a **presença** de `total/IBSCBSTot` e do grupo por item, sem
     interpretar (a política da fatia 1, enquanto a PE-39 não for decidida).
5. **Empresa e papel:** a empresa vem de `emit` e `dest`, nunca da chave (na
   NFA-e, série 890 a 899, a chave leva o CNPJ da SEFAZ) e nunca de `autXML`,
   transportador, retirada, entrega ou informação adicional.
   - Papéis possíveis: **emitente** e **destinatário**. A direção para o
     cliente vem do papel combinado com o `tpNF`, nunca do `tpNF` sozinho.
   - Documento sem nenhuma parte no escritório é recusado com a mesma
     mensagem da fatia 1, exista ou não a empresa em outro escritório.
   - A mesma nota pode ligar duas empresas do escritório.
   - Quando emitente e destinatário são **a mesma empresa** (transferência
     entre estabelecimentos), ficam um vínculo e a marca "transferência entre
     estabelecimentos" (HI-111).
6. **Eventos** (`procEventoNFe`):
   - O evento é guardado sempre, inclusive órfão.
   - Ele só tem efeito com `retEvento/cStat` 135 ou 155 (HI-116; o 136 é
     guardado com aviso).
   - Tornam a nota **cancelada** o 110111 e o 110112.
   - Os demais (carta de correção, manifestações, eventos da reforma, 110001)
     são guardados e listados, sem mudar a situação.
   - A unicidade é pelo `@Id` do evento, que inclui o número de sequência.
   - A situação "cancelada" é consultada por escritório e chave,
     independentemente da ordem de chegada.
7. **Deduplicação** por escritório e chave. Arquivo com a mesma chave e
   conteúdo diferente é sinalizado, e o XML guardado nunca é sobrescrito.
8. **Limite por XML:** até **4 MB** para a NF-e, porque a nota admite 990
   itens; a NFS-e continua com 1 MB. Os limites do lote não mudam (HI-112).
9. **Conferência na tela e na API:**
   - o relatório do lote passa a distinguir NF-e, NFC-e e eventos;
   - lista de NF-e por empresa e período, com papel, direção, situação
     (autorizada ou cancelada), modelo, número, série, valor e presença de
     IBS/CBS;
   - detalhe da nota com os eventos;
   - isolamento e permissões como na fatia 1.

**Fica fora**, com o limite declarado:

- escrituração, CFOP, CST e CSOSN por item;
- notas de crédito e débito e devolução como ajustes;
- apuração e livros;
- manifestação do destinatário como ação do usuário;
- validação da assinatura digital e do `digVal` (limite declarado, como na
  fatia 1);
- comparação do `vNF` com a soma dos itens;
- comportamento do `vNF` a partir de 2027 (NT 2026.008, pendente);
- campos novos da NT 2026.008, que o PL 010f ainda não tem;
- NFCom, CT-e e GTVe (fatia 3).

## Decisões tomadas na implementação (frente A)

- **Evento com o mesmo `@Id` e conteúdo diferente** (por exemplo, retorno
  rejeitado primeiro e cancelamento aceito depois): é gravado como outro
  registro e sinalizado no lote. A unicidade é escritório, identificador e
  SHA-256 do arquivo. Assim a nota fica cancelada nas duas ordens de chegada.
- **O `@Id` do evento tem 54 posições** (`ID` + 52), não 52 como a pesquisa
  escreveu (`leiauteEvento_v1.00.xsd`, linha 136).
- **Conferências além do plano:** a nota de ambiente de homologação
  (`tpAmb` 2) é recusada; UF, modelo, série e número são conferidos contra a
  chave; o `@Id` do evento é conferido contra tipo, chave e sequência.
- **Cancelamento de evento (110001)** que anule um cancelamento aceito não
  devolve a nota à situação válida no primeiro corte: limite declarado,
  BL-681.
- O relatório do lote (tela já existente) passou a mostrar NF-e, NFC-e e
  eventos de NF-e já nesta frente.

## Decisões tomadas na correção (rodada 1)

[Rodada 1](../auditorias/2026-10-09-dl-080-rodada-1.md): **reprovada** por A1
(data absurda aceita travava a lista, o detalhe e o relatório do lote com erro
de servidor). O núcleo do risco se sustentou: nenhuma empresa ligada por
chave ou terceiros, nenhuma cancelada como válida, nenhum vazamento entre
escritórios. Correção única:

- **Datas** (A1): `dhEmi`, `dhRecbto` e `dhEvento` só no padrão do XSD (ano
  20xx); fora dele, recusa com o campo nomeado.
- **Paginação** (A2): ordem com desempate determinístico na lista e nos
  eventos sem nota.
- **Ambiente** (A3, A8): evento de homologação recusado como a nota;
  `tpAmb` ausente recusado (o XSD o exige).
- **`cStat` 136** (A7, HI-116): "registrado, mas não vinculado a NF-e" não
  cancela; o evento é guardado e mostrado com o aviso de conferir. Só 135 e
  155 têm efeito.
- **Leniências do leitor** (A8): `nfeProc` com mais de uma nota recusado;
  retorno do evento com tipo ou sequência diferentes do evento recusado; CNPJ
  da chave conferido com o do emitente, exceto nas séries 890 a 899, em que
  a chave leva o CNPJ da SEFAZ (MOC 7.0, Tabela 2-4; em 900 a 919 a chave
  leva o documento do próprio emitente).
- **Totais da tela** (A5): a soma do `vNF` das autorizadas sai separada por
  direção (saídas, entradas); a cancelada continua fora.
- **Testes** (A4, A6): os casos que os mutantes sobreviventes expuseram e o
  corpus de XML validado contra o XSD montado pelo auditor.
- **Interface** (A9): documento sem quebra no meio; rolagem só dentro da
  tabela em telas estreitas; rótulos ("Carta de Correção", "NF-e já
  recebida", nome do módulo de recepção).
- **Imutabilidade sem gatilho** (A10): aceita nesta fatia, como na NFS-e;
  BL-683.

## Decisões tomadas na reconferência

[Reconferência](../auditorias/2026-10-09-dl-080-reconferencia.md): aprovada com
ressalvas; A1 a A9 fechados, o núcleo do risco firme. Pela regra de parada do
§3.1 não houve nova correção:

- **R1** (o teste que protegia "a chave não liga empresa" perdeu força) e
  **R2** (a exceção de séries era 890 a 919; o MOC 7.0, Tabela 2-4, lido em
  09/10/2026, só põe o CNPJ da SEFAZ na chave em 890 a 899): ajuste do
  arquiteto, com teste de serviço que derruba o mutante de ligar pela chave.
- **R3** (dois `protNFe` ou protocolo de homologação aceitos): recusados.
- **R4** (o cStat 136 sem aviso na lista de órfãos e o campo `registrado` da
  API), **R5** (textos da página inicial e do cartão do módulo ainda dizem
  "NFS-e"), **R6** (coluna cortada em 1280 px) e **R7** (validação do corpus
  contra o XSD só com variável de ambiente): BL-684.

## Critérios de aceite

1. Os aceitos e cada recusa do item 1 têm teste com XML sintético montado
   segundo o XSD do PL 010f, com o caminho citado.
2. A chave com dígito errado e a chave do `@Id` diferente da do protocolo são
   recusadas; a chave com CNPJ alfanumérico válido é aceita.
3. Denegada recusada com o motivo; autorizada com 100 e com 150 aceita.
4. Os totais entram em `Decimal`; ausência fica ausente; valor fora do padrão
   recusado com o campo.
5. Empresa como emitente, como destinatário e nos dois papéis em empresas
   diferentes do escritório. Nota sem destinatário (NFC-e) aceita. Nada é
   ligado por `autXML` nem por transportador. Recusa com mensagem idêntica
   para empresa de outro escritório. Mesmo CNPJ em dois escritórios isolado.
6. Cancelamento antes e depois da nota, nas duas ordens. Evento com retorno
   rejeitado ou sem retorno não cancela. Carta de correção e manifestação não
   mudam a situação. A nota cancelada nunca aparece como válida.
7. Reimportar o mesmo arquivo, ou o mesmo XML dentro de outro ZIP, não
   duplica; conteúdo diferente com a mesma chave é sinalizado.
8. Nenhuma NF-e aparece em receita, RBT12, pré-DAS, ISS, serviços tomados ou
   nas listas de NFS-e; a recepção de NFS-e não muda.
9. Isolamento entre escritórios e empresas em todas as rotas novas;
   permissões no servidor; trilha de auditoria sem conteúdo sensível.
10. Mutação: aceitar `NFe` sem protocolo, aceitar denegada, cancelar por
    evento rejeitado, ligar empresa pela chave, tratar `tpNF` como direção
    do cliente, contar NF-e como NFS-e ou remover o filtro de escritório —
    cada um derruba testes.
11. Não regressão completa numa única invocação; migração aditiva e
    reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — leitor, modelos, migração, serviço de recepção, eventos, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/fiscal/` (módulo novo `leitor_nfe.py`, ajustes pontuais em `leitor.py` e `services.py` para despachar), modelos, migração, testes `test_dl080_*` |
| B — telas de conferência | `auxiliar-implementacao` (Haiku), depois de A | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Tabelas novas; a recepção de NFS-e não muda. Reverter é reverter a migração e
o merge; os XML de NF-e recebidos saem junto.
