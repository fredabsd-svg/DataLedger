# Auditoria DL-080 — reconferência

**Versão auditada:** cópia descartável `/home/user/wt-aud080b`, HEAD detached `392af42`. Ficou intacta: `git status --short` e `git diff --stat` saíram vazios depois da suíte completa e de tudo o mais. Experimentos e mutações rodaram em cópias fora do repositório, em `.../scratchpad/aud/rc/{copy,mutlab/m1..m3}`.

**Data:** 2026-10-09. **Auditor:** `auditor-qa`. Esta é a última rodada pela regra de parada do §3.1 do AGENTS.md.

## Parecer: APROVADO COM RESSALVAS

- **Falhas essenciais.** Não encontrei falha bloqueadora nem de alta gravidade. A causa da reprovação (A1) está fechada com evidência executada. Datas absurdas, inclusive nas bordas de 2000 e 2099 com os fusos extremos permitidos, são recusadas ou aceitas sem derrubar nenhuma tela ou API.
- **Isolamento, notas cancelada/denegada e `tpAmb` de evento e retorno.** O núcleo do risco nível 1 continua firme. Nenhuma empresa é ligada por chave, `autXML`, transportador, retirada, entrega ou `infAdic`. Nenhum vazamento entre escritórios apareceu. A cancelada fica fora do total das autorizadas. O evento e o retorno de homologação são recusados.
- **Ressalva principal (R1, média).** A correção do dev enfraqueceu um teste e deixou sem proteção, na faixa de séries isenta, o invariante "a chave não liga empresa". O mutante M04 passou a **sobreviver** à suíte do dev. O código está correto: o meu teste de round 1 mata o mutante. É lacuna de teste, não defeito de código.
- **Segunda ressalva (R2, baixa).** A exceção de séries 890 a 919 não bate com o MOC. Pela Tabela 2-4, só 890 a 899 levam o CNPJ da SEFAZ na chave. O plano ainda diz "890 a 899" numa linha e "890 a 999" noutra.
- **Demais achados (R3 a R7, baixa).** Pontos abertos do dev e acabamentos. Nenhum compromete o isolamento nem os cálculos.

Este parecer não declara ausência de bugs, segurança absoluta nem conformidade legal. O leiaute é a leitura do PL 010f e continua dependendo de validação do Fred. A recepção segue sem verificar assinatura nem `digVal`, limite declarado no plano.

---

## Situação dos achados da rodada 1

| Achado | Situação | Evidência executada |
| --- | --- | --- |
| A1 datas fora do XSD | **Fechado** | 114 testes meus (`test_rc_a1.py`) passam. Detalhes na seção "A1 a fundo". Mutantes N01, N01b e N01c morrem. |
| A2 paginação sem desempate | **Fechado** | Lote com 600 NF-e de mesma `dhEmi`: 600 distintas em 24 páginas. 130 eventos órfãos de mesma data e sequência: 130 distintos em 6 páginas. Mutantes N03 e N04 morrem. |
| A3 evento de homologação cancela produção | **Fechado** | `tpAmb` do evento e do retorno em 2, ausente, 3 ou 9: tudo recusado, nada gravado, nota segue "valida". `tpAmb` da nota ausente, vazio, 3, 2, `" 1"` ou `"01"`: recusado. Mutantes N05, N06, N07 e N07b morrem. A lacuna restante é o `tpAmb` do protocolo (R3). |
| A4 lacunas de teste (mutação) | **Fechado, exceto M04** | Todos os sobreviventes da rodada 1 agora morrem: M03b, M03c, M07d, M07g, M07h, M07l, M11b, M12b, M28, M30, M40, M06f. Os sobreviventes novos são M04 (R1), os mutantes fracos M06 e M06b (já fracos na rodada 1) e M32 (equivalente). |
| A5 totais misturados | **Fechado** | Reconciliação (`test_rc_a5.py`): 60 notas aleatórias, saída, entrada, entrada própria e a conferir, canceladas e uma sem `vNF`. Quantidade e soma por direção igualam à soma da API, sem filtro e com `papel=emitente`, `modelo=55` e `modelo=65&papel=emitente`. A cancelada fica só na linha dela. Mutantes N17, N18 e N19 morrem. |
| A6 gerador não valida no XSD | **Parcial, com ressalva (R7)** | Com `DL080_XSD_DIR` e `xmllint`: `test_dl080_corpus_xsd.py` deu 20 passed. São 9 casos de NF-e e 1 de evento validados no XSD e lidos pelo leitor, mais 10 de leitura. O gerador `xml_nfe_dl080.py` continua não validando, e agora avisa. Sem a variável, os 10 testes de `xmllint` nem são criados (R7). |
| A7 136 cancela | **Fechado** | 136 e 573 não cancelam, 155 cancela, e "sem retorno" fica sem efeito. Detalhe da API traz `aviso`, e o detalhe na tela mostra o aviso com a nota "Autorizada". Mutantes N15, N15b, N16 e N28 morrem. Pendência de produto: HI-116 depende do Fred. Resíduos em R4. |
| A8 leniências | **Quase todas fechadas** | `tpAmb` ausente e `nfeProc` com duas `NFe` são recusados. Retorno com `tpEvento` ou `nSeqEvento` diferente é recusado, e `"01"` também. Chave × emitente é conferida. Fica aberto o que o dev declarou: `nfeProc` com dois `protNFe` (R3). A exceção 890–919 é a ressalva R2. Não foi tratada a leniência de ZIP com raiz depois de 1 MB de comentário, como em round 1. |
| A9 interface | **Fechado, com ressalvas (R5 e R6)** | CNPJ sem quebra, rótulo "Recepção de documentos fiscais", "Carta de Correção" e "NF-e já recebida" conferidos. Em 1280 e 1024 px a página não ganha barra horizontal. |
| A10 imutabilidade sem gatilho | **Registrado** | BL-683 existe em `docs/projeto/backlog.md`, linha 2248. |
| A11 observações | **Sem achado** | Meus testes de permissão e isolamento seguem verdes (ver "Isolamento"). |

### A1 a fundo

- **Datas.** Os 31 valores ruins nos três campos (`dhEmi`, `dhRecbto`, `dhEvento`) foram recusados com o campo nomeado e nada foi gravado. Depois de cada recusa, lista da API, lista web, órfãos (com e sem filtro), `/fiscal/recepcao/` e relatório do lote responderam 200.
- **Valores ruins testados.** `0001-01-01…`, `9999-12-31…`, `1999…`, `2100…`, os meses, dias e horas impossíveis, e as formas de fuso inválidas. Ficaram de fora os fusos extremos, tratados abaixo.
- **Fusos extremos.** `+14:00` e `−12:00` nas bordas de 2000 e de 2099 são recusados, e o mutante N01c (que os aceitaria) morre. O XSD só permite de −11:00 a +12:00.
- **Aceitos nas bordas.** Cada um dos três campos aceita `2000-01-01T00:00:00+12:00`, `2000-01-01T00:00:00−11:00`, `2099-12-31T23:59:59−11:00` e `2099-12-31T23:59:59+12:00`. Com cada um dos três campos nesses valores, as 7 URLs (lista e detalhe web e API, órfãos, recepção, relatório do lote) deram 200, e os filtros de período nos extremos deram 200.
- **Outros caminhos que gravam data.** No código só `dh_emissao`, `dh_recbto` e `dh_evento` vêm do XML, e todos passam por `_data_hora`. `dhRegEvento` não é lido nem gravado.
- **Valores hostis em XML recusado.** `<script>` e `<img onerror>` no `dhEmi`, no `tpAmb` e no retorno saem escapados no relatório do lote. Valor de 3 MB no `dhEmi`, no `tpAmb` e no `tpAmb` do evento é recusado, o motivo é truncado em 500 caracteres e a página responde 200.

---

## Achados novos

### R1 — MÉDIA — O mutante M04 (ligar empresa pela chave) sobrevive: a correção tirou da suíte do dev a proteção do invariante na faixa isenta

- **Requisito:** HI-109 a HI-113 e risco nível 1 (empresa só por `emit` e `dest`, nunca pela chave). O critério 5 do plano exige "Nada é ligado por `autXML` nem por transportador" e o critério 10 pede mutação sobre "ligar empresa pela chave".
- **Local:**
  - `apps/fiscal/tests/test_dl080_recepcao_nfe.py:222-241` (`test_chave_com_cnpj_de_cliente_nao_liga_a_empresa`).
  - `apps/fiscal/tests/test_dl080_correcao_rodada1.py:440-446` (`test_nfa_e_com_cnpj_da_sefaz_na_chave_e_aceita`).
- **Evidência:**
  - Antes da correção o teste usava série comum, e a recusa vinha da mensagem "nenhum participante". Agora, em série comum, a recusa vem da conferência chave × emitente, e a asserção foi trocada por `"diferente do emitente" in motivo`. O teste antigo deixou de exercitar o fallback por chave.
  - Na faixa isenta (890 a 919) a conferência não age, e é lá que a chave poderia voltar a ligar empresa. O teste novo dessa faixa só lê o documento no leitor (`_ler`). Não passa pelo serviço e não confere vínculo.
  - Mutante M04 (se não há vínculo, usar `chave[6:20]` como emitente) dá **0 falhas** nos 312 testes `test_dl080_*` (N27 repete isolado, também com 0).
  - Meu `test_aud080_a.py::test_nada_por_autxml_transporta_infadic_retirada_entrega_chave` (caso série 890, chave de cliente, `emit` e `dest` estranhos) **mata** N27: a nota vira "recebido" e liga a empresa errada.
  - No código real, o comportamento está correto: o meu teste passa nesse subcaso.
- **Impacto:** quem reintroduzir a ligação pela chave só será pego pelo caminho 890 a 919. Hoje a suíte do dev não o pega. É um teste perdido da correção, não um defeito de código.
- **Correção recomendada:** ver proposta 1. Teste de serviço com `emit` e `dest` estranhos e chave do cliente em 890, 899, 900 e 919, esperando recusa com `MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO`, sem vínculo nem documento. Se o R2 for aceito, vale só para 890 e 899.
- **Como verificar:** reaplicar o mutante N27. Sem o teste, 0 falhas. Com o teste, pelo menos 1.

### R2 — BAIXA — A exceção de séries 890 a 919 é mais larga que o MOC, e a documentação diverge de si mesma

- **Requisito:** HI-110 e a conferência de chave do leitor.
- **Local:**
  - `apps/fiscal/leitor_nfe.py` (`_SERIES_NFA_E = range(890, 920)` e o comentário acima dela).
  - `docs/planos/DL-080-recepcao-de-nfe.md`, linhas 82 ("890 a 899") e 162 ("890 a 999").
- **Evidência:**
  - A Tabela 2-4 do MOC 7.0 (texto extraído em `.../scratchpad/nfe/nt_txt/moc7_visao_geral.txt`, linhas 1046-1062) diz:
    - série 890-899: chave com o CNPJ **da SEFAZ**;
    - série 900-909: chave com o CNPJ **do Emitente**;
    - série 910-919: chave com o CPF **do Emitente**;
    - série 920-969: chave com o CPF do Emitente.
  - Logo, só 890 a 899 justificam a exceção. Em 900 a 919 a chave deve bater com o emitente, e a exceção a elas isenta uma conferência que o MOC mandaria fazer.
  - A pesquisa (`docs/projeto/consultas/2026-10-09-leiaute-nfe.md`, linha 298) diz "900-909 e 910-919 são de SEFAZ para CNPJ e CPF". É ambígua, e o dev a leu como "chave com CNPJ da SEFAZ". O comentário do código repete: "a faixa 900-919 é SEFAZ".
  - Os testes fixam 900 e 919 como aceitos (`test_dl080_correcao_rodada1.py:440`). Meu mutante N12b (exceção 890-899) cai em 2 testes, o que mostra que os testes precisariam mudar junto.
  - Efeito medido (`test_rc_a3.py::test_serie_x_chave`): com `emit` do cliente e chave de outro CNPJ, as séries 900, 909, 910 e 919 foram "recebido".
- **Sobre a decisão do dev ("890 a 919" em vez do meu "890 a 999").** O meu "890 a 999" estava errado, porque 920 a 969 são de CPF do próprio emitente. A escolha do dev cobre 920 a 999 com a conferência, o que está certo. Fica a sobra 900 a 919, cuja origem é a leitura da pesquisa e não o MOC. Não li o PDF: trabalhei sobre a extração em texto, em que as colunas aparecem alinhadas.
- **Impacto:** nenhum risco de isolamento, porque a empresa só vem de `emit` e `dest`. É conferência de consistência deixada de fora, mais divergência documental.
- **Correção recomendada:** `_SERIES_NFA_E = range(890, 900)`, corrigir o comentário e a linha 162 do plano, ajustar os testes de 900 e 919 para "chave do emitente aceita, chave de outro recusada". Se o arquiteto preferir manter a faixa larga, registrar a divergência em vez de citar o MOC como fonte.
- **Como verificar:** com N12b aplicado como código real, os testes de série 900 e 919 passam a exigir recusa para chave de outro CNPJ.

### R3 — BAIXA — O protocolo `protNFe` não é conferido por inteiro (ponto aberto do dev, confirmado)

- **Requisito:** HI-109 (ambiente) e HI-110 (nota autorizada com protocolo).
- **Local:** `apps/fiscal/leitor_nfe.py`, `_ler_nfe_proc`, onde lê `protNFe` e `infProt`.
- **Evidência (`test_rc_a3.py`, `test_rc_prot.py`):**
  - `protNFe/infProt/tpAmb = 2` com `ide/tpAmb = 1` é **recebido** e fica `cStat 100`.
  - `nfeProc` com dois `protNFe`, o segundo com `cStat 110` (denegada), é **recebido** com `c_stat` 100 gravado, e o `xml_original` guarda o segundo protocolo contraditório.
  - Dois `protNFe`, o segundo com outra `chNFe`: também recebido.
- **Impacto:** um XSD-inválido contraditório é arquivado como autorizado. O risco prático é baixo, porque só a forja de um XML dá esse resultado, e a assinatura não é verificada de qualquer forma. A inconsistência é de critério: o dev recusou duas `NFe` e aceita dois protocolos.
- **Correção recomendada:** recusar mais de um `protNFe`, e recusar protocolo com `tpAmb` diferente de 1 ou diferente do `ide/tpAmb`.
- **Como verificar:** proposta 3.

### R4 — BAIXA — O 136 não aparece com aviso na lista de órfãos, e a API chama de `registrado: false` o que o MOC chama "registrado"

- **Requisito:** HI-116.
- **Local:**
  - `templates/fiscal/nfe_eventos_orfaos.html` (colunas "Retorno" e "Efeito").
  - `apps/fiscal/api_nfe.py`, `_evento_da_nota`, campo `registrado`.
- **Evidência:**
  - Na tela de órfãos, o evento 136 mostra "136" e "Sem efeito sobre a situação", sem o aviso que o detalhe mostra.
  - Na API, o 136 sai com `registrado: false` e `aviso: "registrado, mas não vinculado a NF-e (cStat 136) — conferir"`.
  - `registrado` significa na prática "tem efeito", e o texto do aviso diz "registrado". Os dois lados se contradizem para um consumidor.
- **Impacto:** nota de acabamento. Nenhum efeito sobre a situação da nota.
- **Correção recomendada:** mostrar o aviso na tela de órfãos. Renomear o campo ou documentar o significado (por exemplo `com_efeito`).
- **Como verificar:** GET dos órfãos com um 136 deve trazer o texto do aviso, e o JSON do detalhe deve documentar o campo.

### R5 — BAIXA — Textos do produto ainda falam só de NFS-e

- **Local:** `apps/core/module_homes.py:909` ("Recepção de NFS-e disponível") e `templates/registration/landing.html:23` e `:58` ("Recepção de NFS-e nacional").
- **Evidência:** `grep` do repositório fora dos testes. O rótulo da barra lateral em `templates/base.html` foi corrigido para "Recepção de documentos fiscais".
- **Impacto:** a página pública e o cartão do módulo subestimam o que o produto faz. Não é afirmação falsa.
- **Correção:** acrescentar NF-e e NFC-e, ou aceitar e registrar a divergência.
- **Como verificar:** `grep -rn "Recepção de NFS-e"` fora dos testes.

### R6 — BAIXA — Em 1280 px a tabela da lista agora rola por dentro, e a regra de CSS nova não tem teste

- **Local:** `static/css/base.css` (`.documento-sem-quebra { white-space: nowrap; }`) e `templates/fiscal/nfe_lista.html`.
- **Evidência (Chromium, `.../rc/pw.py`):**
  - Em 1280 px a tabela tem 1018 px dentro de um contêiner de 992 px (`overflow-x: auto`). A coluna "Transferência entre estabelecimentos" fica cortada, e antes da correção cabia sem rolagem.
  - A página não ganha barra horizontal em 1280 nem em 1024 (`scrollWidth` igual ao `clientWidth`). Em 1024 a rolagem fica só dentro da tabela, como a correção pretendia.
  - O mutante N21 (`nowrap` trocado por `normal`) dá 0 falhas.
- **Impacto:** só estética. A informação continua acessível por rolagem dentro da tabela.
- **Correção:** encurtar o rótulo da última coluna ou reduzir uma coluna. Se quiserem teste de CSS, só em navegador real, já que o teste Django não vê a regra.
- **Como verificar:** medir de novo em 1280 px.

### R7 — BAIXA — A validação do corpus no XSD só roda com variável de ambiente, e a suíte comum nem lista esses testes

- **Local:** `apps/fiscal/tests/test_dl080_corpus_xsd.py`, bloco `if _XMLLINT and _DIR_XSD and Path(...)`.
- **Evidência:**
  - Sem `DL080_XSD_DIR`, a suíte completa que rodei deu 8.178 passed. O dev relata 8.188. A diferença são os 10 testes de `xmllint` (9 de NF-e e 1 de evento), que só existem com a variável. Isso bate com o relato do dev.
  - Rodei o arquivo do corpus com `DL080_XSD_DIR` apontando para os XSD do auditor (com o `procNFe` e o `procEventoNFe` na mesma pasta): 20 passed.
- **Impacto:** na CI comum o corpus nunca é validado contra o XSD, e o teste não aparece nem como pulado. O risco de o corpus divergir do XSD sem aviso persiste. O dev declarou isso no cabeçalho do arquivo.
- **Correção:** manter os XSD fora do repositório, como decidido, mas registrar a execução com a variável como etapa manual da DL-080, ou criar o teste como pulado explícito.
- **Como verificar:** rodar com `DL080_XSD_DIR` e ver 20 passed.

---

## Regressões da correção

- **Testes antigos alterados.**
  - "NF-e já recebida", "Carta de Correção", totais por direção e retirada do 136 da parametrização: sem perda de força. A retirada do 136 foi substituída por testes novos de 136 na lib, na API e na tela.
  - Exceção: a troca da asserção da chave com CNPJ de cliente enfraqueceu o invariante, e o mutante M04 passou a sobreviver (R1).
- **Exceção de séries 890 a 919 contra o MOC e a pesquisa.** R2. Meus testes de série (`test_rc_a3.py::test_serie_x_chave`):
  - 1, 889, 920, 969, 970, 999 e 0 com chave de outro CNPJ: recusados.
  - 890, 899, 900, 909, 910 e 919: aceitos.
  - 1 com o próprio CNPJ: aceito.
  - CPF do emitente na série 920 e CNPJ alfanumérico `AB12CD34EF5602`: aceitos.
- **136 na API e na tela.** Fechado (A7). O 136 tem aviso na API e no detalhe web. Falta na lista de órfãos (R4).
- **Quadro por direção, cancelada fora.** Reconciliado com a API em quatro combinações de filtro. Exemplo, sem filtro: saída 11 notas e 48.779,31, entrada 15 e 70.955,73, entrada própria 15 e 75.866,61, a conferir 12 e 55.232,35, cancelada 8 e 46.284,30. Cada valor igual à soma da API, e as quantidades somam as 61 notas.
- **Pontos abertos do dev.**
  - `procEventoNFe` sem `retEvento`: aceito como "sem efeito", nota fica "valida". Risco baixo e seguro. O XSD exige o retorno, mas aceitar e guardar sem efeito não cancela nada.
  - `protNFe/tpAmb` e dois `protNFe`: R3.
  - Textos "Recepção de NFS-e": R5.
  - O 136 fora do aviso na lista de órfãos: R4.

---

## Isolamento, permissões, entrada estranha, não contaminação, desempenho

- **Meus testes `test_aud080_a` a `i`: 63 passed e 3 failed, e as 3 falhas são consequência da correção, não regressão:**
  - `test_cstat_evento[136-True]` esperava que o 136 cancelasse, e agora não cancela (HI-116).
  - `test_totais_cancelada_nao_soma` usava a chave `valida` do contexto, que virou as chaves por direção.
  - O terceiro caso de `test_nada_por_autxml…` (série 1, chave de cliente) agora recusa com "CNPJ ou CPF da chave de acesso diferente do emitente" em vez de "nenhum participante". O primeiro caso do mesmo teste (série 890) continua passando.
- **Permissões e isolamento.** 404 entre escritórios e entre empresas, 403 para CLIENTE, 302/403 para anônimo, POST 405. Consulta de PARALEGAL conferida em round 1 e não alterada.
- **Entrada estranha.** Filtros e paginação com valores absurdos continuam em 200 ou 400. Não apareceu 500 em nenhuma das respostas medidas.
- **Não contaminação.** A suíte completa passa, incluindo `test_dl080_nao_contaminacao.py`. O commit de correção não toca `leitor.py`.
- **Desempenho.**
  - Lote de 730 arquivos (600 NF-e de 3 itens e 130 eventos): 2,69 s, 3.658 consultas.
  - Lista web, página 3: 7 consultas.
  - Lista da API com 600 notas: 0,09 s e 189 KB.

---

## Tabela de mutantes

Alvo: os 8 arquivos `test_dl080_*`, **312 testes** (eram 217 na rodada 1), todos verdes na linha de base. A coluna "Caem" é o número de testes que falharam. Mutantes não listados em linha própria seguem o mesmo padrão. Os de round 1 que aparecem como "sobrevive" abaixo já sobreviviam lá, e estão marcados.

| Mutante | Caem | Resultado |
| --- | --- | --- |
| M01a, M01b, M02 (4), M02b | 1, 1, 4, 1 | Mortos |
| M03a, M03c | 3, 3 | Mortos |
| M03b → N24 (lista, evento rejeitado cancela) | 1 | **Morto** (sobrevivia na rodada 1) |
| M03d → N25 (lista, evento sem retorno cancela) | 2 | Morto |
| **M04 ligar empresa pela chave** | **0** | **Sobrevive** (R1; N27 idem) |
| M05, M06c, M06d, M06e, M06f | 12, 1, 1, 1, 3 | Mortos (M06f sobrevivia na rodada 1) |
| M06 e M06b (autXML/transportador só sem `dest`) | 0 | Sobrevivem, mutantes fracos como na rodada 1 (M06c e M06d cobrem) |
| M07a a M07l (todos) | 7, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1 | Mortos. M07d, M07g, M07h e M07l sobreviviam na rodada 1 |
| M08, M09, M10a, M10b, M10c | 2, 1, 2, 1, 4 | Mortos |
| M11 → N17 e N19 (cancelada soma no total) | 4 e 4 | Mortos |
| M11b, M11c, M11d | 1, 2, 1 | Mortos. M11b sobrevivia |
| M12, M12b, M12c | 2, 2, 2 | Mortos. M12b sobrevivia |
| M13a a M13d, M15, M16 | 1 cada, 2, 2 | Mortos |
| M14 → N07b (homologação nunca recusada) | 6 | Morto |
| M17, M18, M18b, M18c, M19 | 10, 3, 1, 1, 1 | Mortos |
| M20, M21, M21b, M22, M23, M24 | 4, 1, 1, 3, 2, 1 | Mortos |
| M25, M26, M27, M29 | 18, 4, 2, 8 | Mortos |
| M28 modelo 57 aceito | 1 | **Morto** (sobrevivia) |
| M30 → N28 (573 efetivo) | 3 | **Morto** (sobrevivia) |
| M31, M34, M35, M36 | 6, 2, 2, 1 | Mortos |
| M32 (relatório sem `select_related`) | 0 | Equivalente, só consulta |
| M33 → N30 (filtro de situação ignorado) | 2 | Morto (não medido na rodada 1) |
| M40, M41, M42, M43, M44 | 1, 1, 1, 8, 1 | Mortos. M40 sobrevivia |
| M45 (desempate da paginação, já no código) | n/a | Absorvido por N03 e N04 |
| **Novos da correção** | | |
| N01 ano 4 dígitos qualquer | 18 | Morto |
| N01b só `dhEmi` e `dhRecbto` checados | 6 | Morto |
| N01c fuso +14/−12 aceito | 2 | Morto |
| N03, N04 sem desempate (lista, órfãos) | 1, 1 | Mortos |
| N05, N06, N07, N07b `tpAmb` (nota, evento, retorno, homologação nunca recusada) | 1, 3, 3, 6 | Mortos |
| N08, N09, N10 retorno `tpEvento`, `nSeqEvento`, duas `NFe` | 1, 1, 1 | Mortos |
| N11 chave × emitente removida | 4 | Morto |
| N12 exceção vira 890–999 | 2 | Morto |
| N12b exceção vira 890–899 (MOC) | 2 | Morto (os testes de 900 e 919 teriam de mudar, R2) |
| N13 exceção em todas as séries | 4 | Morto |
| N14 CPF sem zeros | 3 | Morto |
| N15, N15b 136 efetivo, 155 não efetivo | 2, 2 | Mortos |
| N16 aviso do 136 removido | 2 | Morto |
| N18 direção sempre "saída" | 1 | Morto |
| N22, N23 textos "recebida" e "Carta de Correção" | 2, 3 | Mortos |
| N26 M04 sem a conferência de chave | 4 | Morto |
| **N21 `nowrap` do CSS** | **0** | **Sobrevive** (R6) |
| **N27 só o fallback pela chave** | **0** | **Sobrevive** (R1) |
| N29 `situacao` da linha fixa | 0 | Equivalente: `linha.situacao` não é usada pelo template |

**Resumo:** 111 resultados. Três sobreviventes reais (M04/N27 por R1, N21 por R6), dois mutantes fracos já registrados (M06, M06b) e dois equivalentes (M32, N29). Todos os sobreviventes de A4 da rodada 1 morrem, exceto M04.

**Incidente do auditor, registrado.** Na primeira rodada de mutação, o mutante M03d (dois trechos) aplicou o primeiro trecho, falhou no segundo e deixou `services.py` modificado na cópia `m2`. Os resultados do trecho da `m2` depois dele ficaram contaminados. Descobri pela comparação final entre as cópias e a árvore auditada. Restaurei a cópia e **refiz os 31 mutantes afetados** na cópia limpa. Os números da tabela vêm desses resultados. Em seguida corrigi o meu runner para desfazer em caso de falha de aplicação, e confirmei que as três cópias de mutação ficaram iguais à árvore auditada.

---

## Números da suíte

- **Suíte completa, uma invocação, sem fatias e sem `-n`, em `/home/user/wt-aud080b`:** `1 failed, 8178 passed, 53 skipped, 2 warnings, 4 subtests passed in 697.53s (0:11:37)`.
  - A falha é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, a esperada (Python 3.13 no ambiente).
  - Os 2 avisos são `RemovedInDjango2028Warning` em `test_dl016_f6_check_empresa_not_null.py`, preexistentes.
  - Sem `DL080_XSD_DIR` a suíte tem 10 testes a menos que a do dev, que relatou 8.188 passados. A diferença são os 10 testes de `xmllint` (9 de NF-e e 1 de evento).
- **Testes DL-080:** 312 (eram 217). Os 20 do corpus XSD passam com `DL080_XSD_DIR`.
- **`ruff check .`:** "All checks passed!".
- **`ruff format --check .`:** "538 files already formatted".
- **`manage.py check`:** "System check identified no issues (0 silenced)".
- **`makemigrations --check --dry-run`:** "No changes detected".
- **Migração `0010`:** revertida (`migrate fiscal 0009`) e reaplicada, sem erro, no banco `aud_dl080_rcm2`. O commit de correção não altera a migração.
- **Árvore auditada:** `git status --short` e `git diff --stat` vazios.

---

## Limitações

- `pwsh` não existe no ambiente: não rodei `validate-docs.ps1` nem validei links dos `.md`.
- Python 3.13, e não o 3.14 da CI. Por isso a falha esperada.
- Não li o PDF do MOC 7.0. A Tabela 2-4 vem da extração de texto que está nos arquivos do auditor, e as colunas aparecem alinhadas. A conclusão de R2 depende dessa leitura.
- Não repeti o teste de concorrência da rodada 1 (3 threads). A correção não mexeu nesse caminho, mas não o reexecutei.
- A mutação cobre os 8 arquivos `test_dl080_*`, e não a suíte inteira por mutante.
- Meus testes `test_rc_*` e a rodada visual no Chromium são de uma execução cada.
- Chromium só em 1280 e 1024 px. Não testei teclado, leitor de tela nem contraste.
- Não conferi assinatura nem `digVal`, limite declarado no plano. Evento forjado com `cStat` 135 continua cancelando qualquer nota do mesmo escritório.
- Não tenho XML real de produção. Os XML são sintéticos, os meus e os do corpus do dev.
- O 136 depende do Fred (HI-116 é hipótese). A leitura do 900–919 (R2) também precisa da validação dele ou de revisão da pesquisa.

---

## Propostas de teste

1. **R1, nível serviço (para o dev implementar):**
   ```python
   @pytest.mark.parametrize("serie", ["890", "899", "900", "919"])
   def test_nfa_e_com_chave_de_cliente_e_participantes_estranhos_nao_liga_a_empresa(
       escritorio_a, usuario_gestor_a, emitente, serie
   ):
       chave = chave_nfe(emitente=CNPJ_EMITENTE_A, serie=serie)
       lote = _enviar(
           escritorio_a, usuario_gestor_a,
           xml_nfe(serie=serie, chave=chave,
                   emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CNPJ", CNPJ_SEM_CADASTRO)),
       )
       r = _unico(lote)
       assert r.resultado == TipoResultadoArquivo.RECUSADO
       assert r.motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO
       assert not VinculoNFeEmpresa.objects.exists()
       assert not DocumentoNFe.objects.exists()
   ```
   Se o R2 for aceito, trocar a lista por `["890", "899"]` e acrescentar o caso "900 e 919 com chave de outro CNPJ: recusado".
2. **R2:** com `_SERIES_NFA_E = range(890, 900)`: série 900 e 919 com chave de outro CNPJ recusadas, com a mensagem "diferente do emitente", e série 900 com o CNPJ do próprio emitente aceita.
3. **R3:** `nfeProc` com dois `protNFe`, o segundo com `cStat 110`, recusado. `protNFe/infProt/tpAmb` 2 com `ide/tpAmb` 1 recusado. `protNFe` com `chNFe` de outra chave recusado.
4. **R4:** GET dos órfãos com um evento 136 contém o texto "registrado, mas não vinculado a NF-e". O JSON do detalhe tem o campo documentado com o mesmo significado de `efeito`.
5. **A1 (já cobertos pelo dev, sugestão de reforço):** `dhEmi`, `dhRecbto` e `dhEvento` em `2099-12-31T23:59:59-11:00` e `2000-01-01T00:00:00+12:00`: aceitos, e as 7 URLs (lista e detalhe web e API, órfãos, recepção, relatório do lote) respondem 200. O meu `test_rc_a1.py` (114 casos) cobre isso, e o dev pode reaproveitá-lo.
6. **A5:** teste de reconciliação do quadro de totais contra a lista da API, como `test_rc_a5.py`, com 60 notas aleatórias, cancelamentos e uma nota sem `vNF`, em quatro combinações de filtro.
7. **A2:** lote de 600 notas e 130 eventos órfãos com a mesma data, como `test_rc_a2.py`, esperando 600 e 130 distintos nas páginas.

## Arquivos relevantes

- **Código auditado:** `/home/user/wt-aud080b/apps/fiscal/leitor_nfe.py`, `services.py`, `api_nfe.py`, `views_web.py`, `models.py`, `migrations/0010_dl080_nfe.py`, `templates/fiscal/nfe_*.html`, `static/css/base.css`.
- **Testes do dev:** `/home/user/wt-aud080b/apps/fiscal/tests/test_dl080_correcao_rodada1.py`, `test_dl080_correcao_rodada1_telas.py`, `test_dl080_corpus_xsd.py`, `xml_nfe_xsd_dl080.py`.
- **Evidência do auditor:** `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/aud/rc/`:
  - `copy/apps/fiscal/tests/test_rc_a1.py`, `test_rc_a2.py`, `test_rc_a3.py`, `test_rc_a5.py`, `test_rc_prot.py`, `test_rc_xss.py`;
  - `full_suite.log`;
  - `mut_out_*.txt`, `mutN_out_*.txt`, `rerun1_out.txt`, `rerun2_out.txt`;
  - `mutar3_rc.py`;
  - capturas `shot_*.png` e `s_*.png`.
