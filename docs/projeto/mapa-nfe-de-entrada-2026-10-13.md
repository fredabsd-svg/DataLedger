# Mapa da NF-e/NFC-e com a empresa como destinatária (entradas e compras) — 13/10/2026

Pesquisa somente leitura sobre a `main` em `9a89bb2` (docs sobre `58a6fc4`). Caminhos relativos a `/home/user/DataLedger`. O working tree estava limpo e não editei nada.

Resumo: a recepção (DL-080) vincula a nota de compra à empresa destinatária e guarda o XML. A leitura de itens (DL-081) já grava os campos de ICMS, ST, IPI, PIS/Cofins e IBS/CBS. A escrituração recusa a compra de propósito e só aceita a devolução de venda recebida. Não existe ICMS, DIFAL, livro, EFD nem lançamento contábil de origem `escrita_fiscal`.

## 1. Recepção (DL-080)

**Verificado**

- **Vínculo.** A empresa vem só de `emit` e `dest`, pelo mesmo ponto único da NFS-e (`localizar_empresa_do_escritorio`). Vem "nunca da chave, nem de autXML, transportador, retirada, entrega" (`apps/fiscal/services.py:489-492`, `:539-540`).
  - Emitente cliente gera um vínculo com `PapelNFe.EMITENTE`. Destinatário cliente gera um vínculo com `PapelNFe.DESTINATARIO` (`services.py:543-549`). A mesma nota pode gerar dois vínculos, um por empresa.
  - Se emitente e destinatário são a mesma empresa, fica um vínculo só, como emitente, com `transferencia_entre_estabelecimentos=True` (`services.py:546-548`, `models.py:501-504`, HI-111). O lado de entrada dessa transferência não existe como vínculo.
  - Nota sem nenhuma parte no escritório é recusada. O motivo é a mesma mensagem da NFS-e, exista ou não o CNPJ em outro escritório (`services.py:550-554`).
  - Reenvio acrescenta o vínculo que faltava, quando a empresa foi cadastrada depois (`services.py:613-629`).
- **Modelos.**
  - `PapelNFe` tem EMITENTE e DESTINATARIO (`models.py:392-397`).
  - `VinculoNFeEmpresa` tem unicidade `(documento, empresa)` (`models.py:522-546`).
  - `DocumentoNFe` tem unicidade `(escritorio, chave)` (`models.py:507-516`).
- **Sentido para o cliente** (`apps/fiscal/api_nfe.py:70-83`):
  - destinatário com tpNF 1 é `entrada`;
  - destinatário com tpNF 0 é `a_conferir`, porque "a pesquisa não encontrou, em fonte oficial, a regra desse caso" (`api_nfe.py:76-77`);
  - emitente com tpNF 0 é `entrada_propria`.

**Campos de `DocumentoNFe`** (`models.py:400-505`)

- **Identificação:** modelo, versão, chave, `xml_original`, sha256, série, número, `dh_emissao`, `tp_nf`, `fin_nfe`, `tp_nf_debito`, `tp_nf_credito`, `id_dest`, `c_uf`.
- **Emitente:** tipo de documento, documento, nome e `emitente_crt`.
- **Destinatário** (opcional): tipo de documento, documento e nome. Não há IE nem UF do destinatário.
- **Totais do ICMSTot:**
  - lidos em `leitor_nfe.py:538-551`: `v_nf`, `v_prod`, `v_icms`, `v_st`, `v_ipi`, `v_pis`, `v_cofins`, `v_desc`, `v_frete`;
  - não lidos nesse nível: vBC, vBCST, vSeg, vOutro, vFCP, vII, vIPIDevol, vTotTrib.
- **Protocolo:** `c_stat`, `n_prot`, `dh_recbto`.
- **Outros:** `quantidade_itens`, `tem_ibscbs_total`, `tem_ibscbs_item`, `transferencia_entre_estabelecimentos`.

**Campos de `ItemNFe`** (`models.py:3711-3856`, leitor em `apps/fiscal/itens_nfe.py:228-365`)

- **Produto:**
  - Identificação: `n_item`, `c_prod`, `x_prod`, `ncm`, `cest`, `u_com`, `q_com`, `v_un_com`, `v_prod`.
  - `cfop` é o CFOP que veio no XML, isto é, o do emitente. Não há campo separado nem conversão (`itens_nfe.py:339`).
  - Valores acessórios: `v_desc`, `v_frete`, `v_seg`, `v_outro`, `ind_tot`, `c_benef`.
- **ICMS:** o grupo é lido pelo nome dos filhos (`itens_nfe.py:228-264`).
  - Classificação: `orig`, `cst`, `csosn`, `mod_bc`.
  - Próprio: `v_bc`, `p_icms`, `v_icms`.
  - Desoneração: `v_icms_deson`, `ind_deduz_deson`, `mot_des_icms`.
  - ST: `mod_bc_st`, `v_bc_st`, `p_icms_st`, `v_icms_st`, `v_bc_st_ret`, `v_icms_st_ret`.
  - Crédito do Simples: `p_cred_sn`, `v_cred_icms_sn`.
  - FCP: `v_fcp`, `v_fcp_st`.
- **Partilha (DIFAL):** só `v_icms_ufdest` (`itens_nfe.py:352-354`).
- **IPI, PIS, Cofins:**
  - IPI: `cst_ipi`, `v_ipi`.
  - PIS: `cst_pis`, `v_pis`.
  - Cofins: `cst_cofins`, `v_cofins`.
- **Outros tributos:** `v_issqn`, `v_ii`.
- **IBS/CBS:** `tem_ibscbs` e `ibscbs_xml` (XML bruto), "nada é interpretado" (`itens_nfe.py:301-306`, HI-123).
- **Derivado:** `receita_bruta_item`, que é o valor bruto do item e não a receita (`models.py:3721-3724`).

**`LeituraItensNFe`** (`models.py:3871-3937`) grava o estado da leitura (lida ou ilegível, com `motivo`), `v_ii`, `v_ipi_devol`, `v_nf_tot`, `v_ibs`, `v_cbs`, `v_is` e `v_fcp_st_total`.

**Não encontrado** (grep em `models.py`, `itens_nfe.py`, `leitor_nfe.py` e `escrituracao_nfe.py`):

- `cEAN`/`cEANTrib`;
- `pRedBC`, `pRedBCST` e `pMVAST`;
- `vBCFCP` e `pFCP`;
- `vBCUFDest`, `pICMSUFDest`, `vICMSUFRemet` e `vFCPUFDest`;
- grupos de ICMS monofásico (`ICMSMono`);
- `vICMSSubstituto`, `vICMSOp` e `pDif` (diferimento);
- base e alíquota de PIS, Cofins e IPI (`pPIS`, `pCOFINS`, `pIPI`);
- `vTotTrib`, `infAdProd` e `NFref`.

Os itens são lidos de `xml_original` e não se perde o XML. O que falta em `ItemNFe` pode ser relido do XML guardado, pelo mecanismo de versão do leitor (`itens_nfe.py:50-54`).

## 2. Escrituração (DL-081, DL-085, DL-087)

**Verificado**

- **Tipos.** `TipoEscrituracaoNFe` tem `SAIDA_PROPRIA`, `DEVOLUCAO` ("Devolução de venda recebida (finNFe 4)") e `AJUSTE` (`models.py:3515-3520`). Não há tipo de compra ou entrada.
- **Regra de `tipo_da_nota`** (`apps/fiscal/escrituracao_nfe.py:194-214`):
  - Só modelos 55 e 65.
  - Emitente: tpNF 1 com finNFe 1 é saída própria; tpNF 1 com finNFe 2, 3, 5 ou 6 é ajuste; tpNF 0 com finNFe 4 é devolução (nota própria de entrada).
  - Destinatário: só finNFe 4 é elegível, como devolução ("a nota é de terceiro e a empresa é a destinatária", `:211-213`). Qualquer outra combinação devolve `None`.
  - Teste: destinatário com tpNF 1 ou 0 e finNFe 1 dá `None` (`apps/fiscal/tests/test_dl081_sugestao.py:204-205`).
- **Compra comum recebida** (destinatário, finNFe 1, ou tpNF 0 de terceiro):
  - Não é recusada na recepção e fica na lista de recebidas.
  - A situação é `nao_elegivel`, rotulada "Fora da escrituração" (`escrituracao_nfe.py:588-593`, `views_web.py:8444`).
  - **Motivo exibido literal:** "nota de entrada (compra): fora desta escrituração, só a recepção." (`escrituracao_nfe.py:221-222`). É exibido na tela de uma nota por `fora_motivo` (`views_web.py:9141-9145`, `templates/fiscal/nfe_escriturar.html:70-73`).
  - Tentar criar rascunho levanta `EscrituracaoNFeErro` com esse mesmo motivo (`escrituracao_nfe.py:733-735`).
  - A lista "a escriturar" mostra só as elegíveis: `elegiveis = [nota for nota in notas if nota.tipo is not None]` (`views_web.py:8700`). A compra não aparece nessa lista.
- **Devolução de venda recebida** (destinatário, finNFe 4):
  - É elegível como `DEVOLUCAO` e usa o fluxo comum de rascunho, natureza por item, efetivação e estorno.
  - A natureza vem de `devolucao_venda` ou `devolucao_combustivel_consumo`, pelo `indDevol` do CFOP e não pela faixa do CFOP (`escrituracao_nfe.py:353-388`, `:407-411`, `cfop.py:17-19`).
  - Efeito: deduz receita (HI-121, HI-140). É dedução de receita e não escrituração de entrada.
  - A nota própria de entrada (emitente, tpNF 0, finNFe 4) também entra como `DEVOLUCAO` (`escrituracao_nfe.py:207-209`).
- **Sugestão de natureza** assume o papel EMITENTE por padrão (`escrituracao_nfe.py:397-398`). Em `classificacao.py:385` o papel EMITENTE está fixo. O catálogo `NaturezaOperacaoNFe` (`models.py:3091-3113`) só tem naturezas de saída, devolução de venda e ajuste. Não há natureza de compra.
- **Regras de classificação (DL-087):** o critério "papel da empresa" é citado em HI-142 (`docs/projeto/requisitos.md:218`). O código chama `tipo_da_nota` com `PapelNFe.EMITENTE` fixo (`classificacao.py:385`). No lote, usa `linha.vinculo.papel` (`escrituracao_nfe_lote.py:1176`).
- **Saída com CFOP de devolução de compra** (`indDevol` 1 em saída): "sem sugestão: devolução de compra em saída, fora do catálogo" (`escrituracao_nfe.py:418-420`).
- **A decisão está documentada.** HI-117 diz "as compras ficam só na recepção" (`requisitos.md:193`). Consulta do contador-senior: entradas de compra (crédito de ICMS, custo, estoque) "ficam só na recepção" (`docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md:24`). `docs/planos/DL-081-escrituracao-das-nfe-de-saida.md:98` lista "escrituração das entradas (compras e créditos)" em "Fica fora". `docs/projeto/paridade/fiscal.md:131` diz "Não existe; a elegibilidade recusa de propósito".

## 3. Serviços tomados (DL-078)

**Verificado**

- **Registro próprio.** `EscrituracaoTomada` é separada da `EscrituracaoFiscal` das prestadas (HI-93), com vínculo de tomador (`VinculoDocumentoEmpresa`) (`models.py:890-943`, `tomadas.py:1-10`). A tomada nunca entra em receita, RBT12, pré-DAS nem ISS próprio.
- **Naturezas.** Catálogo fechado `NaturezaTomada` de seis itens (`models.py:897-916`): T1 ISS retido pelo cliente, T2 sem retenção, T3 prestador de outro município, T5 MEI, T6 ME/EPP do Simples e T7 pessoa física. Não há T4.
- **Sugestão e confirmação** (`tomadas.py:430-475`):
  - Ordem: tpRetISSQN 2, depois opSimpNac 2 e 3, depois CPF, depois T3, depois T2.
  - O contador confirma e a sugestão nunca efetiva sozinha (HI-93).
  - A sugestão vem com o sinal do XML que a determinou (`:400-415`).
- **Recusas.**
  - tpEmit 2 ou 3 é recusado (`tomadas.py:77`, `:108-112`, `:379-394`).
  - Natureza incompatível com tpRetISSQN também é recusada (T1 exige 2; T2 e T3 exigem 1) (`tomadas.py:478-506`).
- **Cópia dos valores.** Os valores são copiados do documento e do XML na efetivação, com ausência igual a NULO e nunca zero (`models.py:986-987`, `tomadas.py:25-26`).
- **Retenções** (`apps/fiscal/retencoes.py:1-21`). Só lê e totaliza o que a nota destaca, sem recalcular alíquota nem gerar guia. O ISS retido usa o mês de `dCompet`. O INSS usa o mês de emissão. IRRF e CSRF dependem da data de pagamento informada pelo contador, e sem ela ficam pendentes.
- **Mesmo desenho de imutabilidade.** Uma linha por vínculo e por tentativa, rascunho, efetivada e estornada, unicidade parcial e gatilhos do banco (migração 0008), trilha na mesma transação (`models.py:919-941`, `tomadas.py:36-39`).

**Inferido.** O padrão serve como molde estrutural: registro próprio por tipo, catálogo fechado, sugestão com motivo, confirmação do contador, valores copiados na efetivação e ausência igual a NULO. A DL-081 (NF-e de saída) já replicou esse desenho, com `EscrituracaoNFe` e `NaturezaItemNFe` por item. Duas diferenças pesam para a mercadoria. A tomada é uma natureza por nota; a NF-e é por item e com itens lidos do XML. E as retenções da tomada são destaque do XML sem cálculo, enquanto o crédito de ICMS de compra exigiria regra de apuração, que não existe.

## 4. CFOP de entrada

**Verificado**

- **Tabela oficial.** `apps/fiscal/cfop.py` carrega `dados/cfop_it2023002_v210.csv` (Informe Técnico 2023.002 v2.10, `cfop.py:1-22`). O CSV tem 619 códigos: 131 iniciados em 1, 125 em 2 e 32 em 3, sem contar o cabeçalho.
  - A tabela traz as colunas `codigo;descricao;indNFe;indComunica;indTransp;indDevol;vigencia_inicio;vigencia_fim`.
  - Exemplos no CSV: 1.101 "Compra para industrialização ou produção rural", 1.102 "Compra para comercialização", 1.201 e 1.202 (devolução de venda, `indDevol` 1) e 1.401 a 1.409 (ST).
  - `cfop(codigo)` aceita "5102" ou "5.102" e devolve `None` para código fora da tabela (`cfop.py:98-107`).
- **O que o código usa dessa tabela:** `indDevol` (devolução), devolução de combustível por texto (`cfop.py:110-167`) e prestação de comunicação e transporte pela descrição, sem tocar em aquisição (`cfop.py:170-191`). O texto de `cfop.py:115` diz que as devoluções de compra recebidas vêm como 5.660 a 5.662 e 6.660 a 6.662.
- **Conversão CFOP do emitente para CFOP de entrada do destinatário: não encontrada.** Não há função, tabela nem constante de conversão em `apps/fiscal/`.
  - Os grep por `cfop_de_entrada`, `converter_cfop` e `CFOP_DE_ENTRADA` não acharam nada.
  - O `ItemNFe.cfop` guarda o do emitente.
  - A pesquisa dos acumuladores descreve essa conversão no sistema de referência como "uma tabela à parte" (`docs/projeto/pesquisa-acumuladores-2026-10-09.md:168`) e cita a falha de "nota de entrada traz CFOP de saída sem conversão" (`:185`).
  - A consulta de classificação planeja "CFOP de entrada derivado do de saída" na DL-091 (`docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md:155`).

## 5. ICMS, livro de entradas, EFD/SPED e integração contábil

**Verificado por grep em `apps/fiscal` e `apps/contabilidade`, excluindo testes e migrações**

- **ICMS (apuração, crédito, DIFAL, ST, antecipação): não encontrado.**
  - O que existe de ICMS são campos lidos dos itens, sem cálculo (`models.py:3716`, `itens_nfe.py:5`).
  - Existe também a segregação do Simples, em que ICMS-ST substituído tira o ICMS do DAS (`models.py:3306`, `escrituracao_nfe.py:951`). É segregação de receita e não apuração.
  - `NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO` e `SUBSTITUTO_ST` existem só para saída (`models.py:3094-3095`).
- **Livro de entradas: não encontrado.** `docs/projeto/revisao-do-fiscal-2026-10-09.md:60`: "Livros fiscais ... Não existe". Em `catalogo-de-relatorios.md` só aparecem os livros Diário e Razão (`:81-82`).
- **EFD ICMS/IPI e SPED Fiscal: não encontrado.** No código fiscal, "SPED" aparece só no namespace da NFS-e (`apps/fiscal/leitor.py:38`). "EFD-Reinf" aparece só em texto de aviso (`retencoes.py:4`, `views_web.py:4355`). Também não há importador de SPED Fiscal (RC-44).
- **Integração contábil:**
  - O valor `OrigemLancamento.ESCRITA_FISCAL` existe, rotulado "Escrita fiscal (reservado)" (`apps/contabilidade/models.py:2283`). A docstring diz "Nenhum caminho o grava hoje" (`:2276-2278`).
  - Os tipos de documento reservados são `escrituracao_nfe` e `escrituracao_nfse` (`:2301-2307`). O CHECK `ck_lancamentocontabil_origem_pareada_ao_documento` aceita `escrita_fiscal` apenas com esses dois tipos (`:2592-2613`).
  - Grep por `ESCRITA_FISCAL` e `escrita_fiscal` fora de testes só acha definição, rótulos, seletor do Diário e restrições (`contabilidade/services.py`, `views.py`, `views_web.py`, `core/restricoes.py`). Nenhum código de `apps/fiscal` grava essa origem, e a revisão registra que não há import de `apps.contabilidade` em `apps/fiscal` (`revisao-do-fiscal-2026-10-09.md:62`, anterior à DL-089).
  - A integração contábil (prévia, configuração por natureza) é a DL-094 proposta (`revisao-do-fiscal-2026-10-09.md:174`).

## 6. Telas e API que listam NF-e recebidas

**Verificado**

- **Rotas web** (`apps/fiscal/urls_web.py`):
  - `nfe/` é `fiscal_web:nfe_recebidas`.
  - `nfe/empresas/<id>/notas/<doc>/` é `nfe_detalhe`.
  - `nfe/eventos-sem-nota/` é `nfe_eventos_orfaos`.
  - `nfe/escrituracao/` é `nfe_a_escriturar`.
  - `nfe/escrituracao/conferencia/` é `nfe_conferencia`.
  - `nfe/escrituracao/reclassificar/` é `nfe_reclassificar`.
  - `nfe/escrituracao/empresas/<id>/lote/` é `nfe_lote`.
  - `nfe/escrituracao/empresas/<id>/notas/<vinculo>/` é `nfe_escriturar`.
  - `…/estornar/` é `nfe_estornar`.
  - As regras e a fila de classificação ficam em `nfe/classificacao/...` (`urls_web.py:137-192`).
- **Rotas de API** (`apps/fiscal/urls_api.py:97-149`):
  - `empresas/<id>/nfe/` é `NotasNFeView`, com filtros `inicio`, `fim`, `papel`, `modelo` e `situacao` (`api_nfe.py:232-249`).
  - `empresas/<id>/nfe/<documento_id>/` é `DetalheNFeView` (`api_nfe.py:252-274`).
  - Há também as rotas de `nfe/escrituracao/` (lista, detalhe, naturezas, marca de monofásico, segmento de devolução, efetivar, estornar e reclassificar) e `nfe/conferencia/`.
- **Lista web `nfe_recebidas`** (`views_web.py:8225-8244`, `templates/fiscal/nfe_lista.html`).
  - Colunas: modelo, série, número, emissão, contraparte (nome e documento), papel, direção (Saída, Entrada, Entrada própria, A conferir), situação, `v_nf`, marca de IBS/CBS e marca de transferência.
  - Totais separados por direção (`views_web.py:8177-8222`, `nfe_lista.html:105-140`). A nota cancelada tem linha própria e não entra nas direções.
  - A contraparte da nota de entrada é o emitente (`views_web.py:8158-8174`).
  - Nota de entrada não mostra itens nem impostos nessa lista.
- **Detalhe web e API.**
  - O detalhe web traz cabeçalho, totais do ICMSTot, protocolo, eventos e a presença de IBS/CBS; só conta itens (`nfe_detalhe.html:173`), sem listá-los.
  - O detalhe da API repete o cabeçalho, com `direcao` e os nove totais (`api_nfe.py:172-229`).
  - Na tela de escrituração (`nfe_escriturar`), a nota de compra mostra o motivo fora da escrituração (§2).
- **Isolamento.** A lista exige uma empresa do escritório ativo. Nota de outra empresa responde 404 (`api_nfe.py:252-258`, `views_web.py:8030-8032`).

## 7. Documentos de projeto relevantes

**Verificado (leitura)**

- **`docs/projeto/revisao-do-fiscal-2026-10-09.md`:**
  - **A2** (`:85`): "Escrituração de NF-e de entrada (compras e créditos)". Sem entradas não há crédito de ICMS, PIS/Cofins nem apuração; a recepção guarda a nota e a elegibilidade a recusa. Depende de A1 (natureza de entrada com tributação) e do CFOP de entrada. Nível 1, tamanho G.
  - **A3** (ICMS-TO: próprio, ST, DIFAL, FECOEP) depende de A1 e A2 (`:86`).
  - **A7** (livros de entradas e saídas) depende de A2 e A3.
  - **B1** (participantes e produtos), **B9** (CT-e e NFCom de entrada) e **C1** (EFD ICMS/IPI).
  - **Ordem proposta** (`:175`): DL-091 é a escrituração de NF-e de entrada, "Compras, créditos, CFOP de entrada, devolução de compra", e depende da DL-087.
  - A DL-092/093 (ICMS-TO) vem depois, a DL-094 é a integração contábil e a DL-095 são os livros.
  - Observação: a numeração real divergiu da proposta (DL-087, 088, 089 e 090 têm outros conteúdos no roteiro da DL-067). Por isso o item 18 do roteiro está como "a numerar".
- **`docs/planos/DL-067-plano-do-modulo-fiscal.md:1045`:** linha 18, "a numerar", "NF-e de entrada (compras e créditos); depois ICMS-TO em fatias; integração contábil; livros", nível 1, depende da etapa 15 (DL-087). Dentro do plano mestre, a escrituração tem "Escrituração: Documento, itens, tributos por item, parcelas, referências, estado por evento" (`:299`). A decisão 3 é "Tributo é dado, não coluna" (`:202`). Os "Produtos" do cadastro trazem "tabela de apelidos que liga o código do fornecedor ao produto interno" (`:318`).
- **`docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md:155`:** DL-091 com "compras, devolução de compra, CFOP de entrada derivado do de saída, crédito como linha gerada mas **sem apuração** ainda", dependendo da DL-087.
- **`docs/projeto/pesquisa-acumuladores-2026-10-09.md`.** O que o sistema de referência faz, só como rotina:
  - **Importação de entradas** (`:151-152`): regra por linha com os mesmos critérios das saídas (operação, CFOP, CST de ICMS, CST de PIS, origem, produto), mais o fornecedor e, conforme a central, tipo de inscrição e regime do fornecedor.
  - **CFOP de entrada** (`:168`): tabela à parte que traduz o CFOP de saída do emissor no de entrada do destinatário.
  - **ICMS-ST e antecipação** (`:72-75`): base soma produto, frete, seguro, despesas, IPI e MVA, menos o desconto, com a alíquota interna do produto.
  - **Duas empresas do mesmo escritório** (`:197`): a saída de uma pode gerar a entrada na outra.
  - **Falhas típicas** (`:184-186`): falta de linha para a combinação, CSOSN contra regra escrita em CST, e CFOP de saída sem conversão.
  - **Cobertura do DataLedger** (`:264`): "Crédito e impostos de entrada: Nenhum".
  - Regra do `CLAUDE.md`: manual de concorrente responde rotina, nunca norma.
- **`docs/projeto/mapa-funcional-fiscal.md`:** `:204` diz que não há escrituração de entradas (compras). Em `:326`, "Movimento: Notas de entrada ..." é "parcial ... entradas (compras) ... não". Livros fiscais em `:309` constam "Não existe". Em `:385`, o item 6 é "NF-e de entrada e saída".
- **`docs/projeto/paridade/fiscal.md`:** FIS-36 "Lançamento de nota de entrada" está como "Não existe" e depende de FIS-35, FIS-04, FIS-05 e FIS-07; exige produto (FIS-05) e estoque (FIS-39) (`:1490-1517`). A competência pelo manual de referência é a data de entrada e não a de emissão (`:1496-1499`). Isso é rotina do manual e não norma.
- **`docs/projeto/catalogo-de-relatorios.md`:** não há "Livro de Entradas". O catálogo só trata Diário e Razão (`:81-82`) como livros com forma prescrita.
- **Requisitos HI/PE** (`docs/projeto/requisitos.md`):
  - HI-117 (`:193`): compras só na recepção.
  - HI-111 (`:187`): transferência entre estabelecimentos tem "os dois lados do fato ... para a escrituração da NF-e".
  - HI-142 (`:218`): regras de importação com critérios que incluem papel da empresa e CRT do emitente.
  - HI-153 (`:229`): regra do escritório vale antes da sugestão embutida.
  - HI-120 e HI-127: ST e CSOSN 500/201/202/203.
  - PE-86 (`:99`): benefício do TO sobre ICMS no DAS, pendente de leitura da lei do Tocantins.
  - PE-90 (`:103`): PIS/Cofins até 12/2026 e a ordem entre virada de 2027 e ICMS-TO.
  - RC-44: importar SPED Fiscal.
  - Não encontrei HI/PE específicos de DIFAL nem de antecipação no filtro que apliquei às linhas de `requisitos.md`. Não li o arquivo inteiro.
- **`docs/agents/estado.md:35`** lista como inexistentes: "escrituração de entradas (compras), ICMS, IPI, PIS/Cofins, livros fiscais, obrigações acessórias, guias, integração contábil, cadastro de classificação com vigência". O trecho de `estado.md:622` confirma a sequência seguinte: NF-e de entrada, ICMS-TO, integração contábil e livros. Porém A1, o cadastro de classificação com vigência, já saiu como DL-087 corte 1 (#110, `58a6fc4`).

## Lacunas para a etapa de entradas

1. **Elegibilidade.** `tipo_da_nota` e `motivo_fora_da_escrituracao` recusam destinatário com finNFe diferente de 4 (`escrituracao_nfe.py:211-214`, `:221-222`). Falta tipo de entrada em `TipoEscrituracaoNFe` (`models.py:3515`) e regra para tpNF 0 de terceiro com destinatário, que hoje é "a conferir" (`api_nfe.py:76-77`).
2. **Natureza de entrada.** `NaturezaOperacaoNFe` só tem saída, devolução de venda e ajuste (`models.py:3091-3113`). `sugerir_natureza_item` e `classificacao.py:385` assumem o papel EMITENTE. A classificação de entrada com tributação por imposto (A1 da revisão) não existe.
3. **CFOP de entrada.** Há a tabela 1.xxx, 2.xxx e 3.xxx, mas não há conversão do CFOP do emitente (5, 6, 7) para o de entrada (1, 2, 3). `ItemNFe.cfop` guarda só o do emitente. É preciso decidir a regra com fonte oficial: o CSV é tabela de apoio e a ressalva do Convênio s/nº de 1970 prevalece (`cfop.py:13-15`).
4. **Campos de itens ausentes** para crédito e ST de entrada:
   - `cEAN`/`cEANTrib`;
   - `pRedBC`, `pRedBCST` e `pMVAST`;
   - base e alíquota de IPI, PIS e Cofins;
   - `vBCFCP` e `pFCP`;
   - os campos da partilha além de `vICMSUFDest`;
   - ICMS monofásico, diferimento e `vICMSSubstituto`;
   - `NFref` e `infAdProd`.
   - Totais do documento ausentes: vBC, vBCST, vSeg, vOutro e vFCP.
   - Destinatário sem IE nem UF.
   - O XML guardado permite reler, mas qualquer ampliação exige nova `VERSAO_LEITOR_ITENS` e cuidado com a imutabilidade das notas escrituradas (`itens_nfe.py:50-54`).
5. **Participantes e produtos.** Não há cadastro de fornecedor com atributos fiscais com vigência (optante do Simples, contribuinte, IE) nem de produto para crédito (B1 da revisão). O CRT do emitente existe em `emitente_crt`.
6. **Transferência entre estabelecimentos.** O vínculo de entrada da filial destinatária não existe (`services.py:546-548`, HI-111); o lado de entrada fica para esta etapa.
7. **Competência.** `dia_e_competencia` usa o dia do `dhEmi` (`escrituracao_nfe.py:188-191`). Para entrada, a data de entrada ou escrituração é decisão de produto aberta, e não achei decisão do Fred sobre ela.
8. **ICMS.** Não há apuração, crédito, DIFAL, ST nem antecipação, e a legislação do TO não foi lida em fonte oficial (A3, PE-86). A orientação da consulta é "crédito como linha gerada mas sem apuração ainda".
9. **Livros e obrigações.** Não há Livro de Entradas, EFD ICMS/IPI, importador de SPED Fiscal (RC-44) nem inventário. Nenhum relatório fiscal exporta ou imprime (B4).
10. **Integração contábil.** O fiscal não grava `OrigemLancamento.ESCRITA_FISCAL` nem os tipos `escrituracao_nfe`/`escrituracao_nfse`, que estão reservados. A numeração (DL-091 a DL-095) é só proposta; o item 18 do roteiro está "a numerar".
11. **Conferência e relatórios.** `nfe_conferencia` (W16, vNF) e a conferência recebidas × escrituradas foram desenhadas para saída e devolução, então precisariam de versão para entradas. Isso é inferência: li as rotas, não o código dessas conferências.
12. **Regras de importação da DL-087.** Falta confirmar se as regras do corte 1 (CFOP, CST/CSOSN, NCM, papel da empresa) aceitam `tipo` de entrada. `test_tipo_da_regra_precisa_ser_o_tipo_da_nota` (`apps/fiscal/tests/test_dl087_precedencia.py:380`) sugere um vínculo entre tipo da regra e tipo da nota. Não li o corpo desse teste nem o modelo de regra.
13. **Pontos que dependem do Fred:** a competência da entrada, a origem da conversão de CFOP, e se os 7 NF-e de entrada do acervo são devolução (PE-85.2, `consultas/2026-10-09-contador-senior-escrituracao-nfe.md:193`).

## Limites da pesquisa

- **Inferido:** o padrão da DL-078 como molde (§3) e a necessidade de nova versão do leitor (lacuna 4).
- **Não determinei:**
  - o conteúdo completo da DL-087, que li só por grep e não integralmente;
  - o comportamento de `nfe_conferencia` e `ReclassificarNFeView` para papel DESTINATARIO;
  - se há resposta do Fred sobre competência de entrada ou conversão de CFOP em `requisitos.md`, que li só por filtro de linhas;
  - o corpo do modelo de regra de classificação e se aceita tipo de entrada.
- **Não executei** testes, `manage.py` nem comandos de verificação.

## Arquivos-chave

- `/home/user/DataLedger/apps/fiscal/models.py`
- `/home/user/DataLedger/apps/fiscal/services.py`
- `/home/user/DataLedger/apps/fiscal/itens_nfe.py`
- `/home/user/DataLedger/apps/fiscal/leitor_nfe.py`
- `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py`
- `/home/user/DataLedger/apps/fiscal/cfop.py`
- `/home/user/DataLedger/apps/fiscal/dados/cfop_it2023002_v210.csv`
- `/home/user/DataLedger/apps/fiscal/tomadas.py`
- `/home/user/DataLedger/apps/fiscal/retencoes.py`
- `/home/user/DataLedger/apps/fiscal/api_nfe.py`
- `/home/user/DataLedger/apps/fiscal/views_web.py`
- `/home/user/DataLedger/apps/fiscal/urls_web.py`
- `/home/user/DataLedger/apps/fiscal/urls_api.py`
- `/home/user/DataLedger/apps/contabilidade/models.py`
- `/home/user/DataLedger/templates/fiscal/nfe_lista.html`
- `/home/user/DataLedger/templates/fiscal/nfe_escriturar.html`
- `/home/user/DataLedger/templates/fiscal/nfe_detalhe.html`
- `/home/user/DataLedger/docs/planos/DL-067-plano-do-modulo-fiscal.md`
- `/home/user/DataLedger/docs/projeto/revisao-do-fiscal-2026-10-09.md`
- `/home/user/DataLedger/docs/projeto/pesquisa-acumuladores-2026-10-09.md`
- `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md`
- `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md`
- `/home/user/DataLedger/docs/projeto/paridade/fiscal.md`
- `/home/user/DataLedger/docs/projeto/requisitos.md`
