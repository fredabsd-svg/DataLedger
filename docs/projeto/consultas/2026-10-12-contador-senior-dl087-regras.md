# Consulta ao contador-senior sobre a DL-087 (precedência e permissão das regras de classificação) — 12/10/2026

**Legislação validada até:** não se aplica — as quatro perguntas são de rotina de escritório, controle interno e desenho de produto; nenhuma depende de alíquota, prazo ou leiaute. Nenhuma norma foi lida hoje, e nenhuma é citada como fundamento. · **Carteira de referência:** Palmas/TO; Simples e Presumido; comércio e postos com NFC-e em alto volume. · **Grau de segurança geral:** alto nas posições 1, 3 e 4 (decorrem do que o código já faz e do que o suporte do sistema de referência registra como erro); médio na 2 (controle interno depende do tamanho do escritório do Fred, que eu não conheço).

**Marcas.** *manual* = texto do sistema de referência lido hoje na cópia local do scratchpad (`dominio/escrita.txt`, páginas do PDF; `dominio/sol824.html`, `sol922.html`, `sol121.html`, artigos da central); é **rotina, não norma**, reescrita com palavras minhas. *código* = arquivo e linha do repositório, lido hoje. *não conferido* = conhecimento meu, sem leitura hoje. Não há marca *lido* nem *cópia* de norma nesta consulta porque nenhuma norma foi necessária.

**O que li hoje:** `docs/planos/DL-087-classificacao-fiscal-versionada.md` inteiro; `docs/projeto/pesquisa-acumuladores-2026-10-09.md` inteiro; a consulta de 09/10 (itens 1 e 2) e o item 1 da de 08/10; `requisitos.md` (HI-141, HI-142, HI-153, PE-91, RC-102, RC-178, HI-132); `apps/fiscal/escrituracao_nfe.py:160-453` e `1762-1772`; `apps/fiscal/permissoes.py` inteiro; `apps/fiscal/api_presumido.py:93-102`; `apps/fiscal/models.py:2806-2875` e `3474-3497`; `apps/tenancy/models.py:89-102`; no manual, por busca de termos, as páginas 453, 464-470, 490-491 e 542-550 e os três artigos da central acima.

Tudo abaixo é **hipótese para validação do Fred** (HI-54; RC-178: decisão delegada, reversível).

---

## 1. Precedência: pesos por especificidade ou ordem numérica manual (PE-91, item 1)

**Resposta curta.** **Pesos por especificidade**, e não ordem manual. Para quem classifica milhares de NFC-e, a regra "vence a que diz mais sobre o item" se explica numa frase e não exige conhecer a lista inteira; a ordem numérica exige, e quebra silenciosamente quando alguém insere uma linha nova sem renumerar. Os pesos propostos são corretos na ordem (NCM acima de CST), mas produzem **empates evitáveis** entre conjuntos diferentes de critérios; recomendo potências de dois. E há **um critério condicionalmente obrigatório** além do CFOP: regra cujo resultado é natureza de combustível **exige NCM**.

### Fundamento

- **ROTINA (manual).** O sistema de referência não documenta o algoritmo geral de precedência (pesquisa, seção 4, confirmada hoje). O que ele tem é uma **marca de configuração** que muda o comportamento da tabela inteira: só com ela marcada a linha específica vence a linha "Todos" para o mesmo CFOP; sem ela, o mesmo CFOP em duas linhas depende de outra opção ("permitir relacionar o mesmo CFOP para mais de um acumulador", manual EF p.453 e 490). O exemplo oficial é o de duas linhas para o CFOP 5.101, uma com tudo "Todos" e outra com CST e forma de pagamento (central 824 e 922). O próprio artigo de erro mais comum (central 121) manda **marcar essa opção** como primeiro passo da correção, isto é, a precedência implícita e configurável é causa registrada de atrito. A duplicação de linha copia os critérios e não copia o acumulador (manual EF p.470 e 550), o que favorece listas longas e parecidas.
- **CÓDIGO.** A sugestão embutida já decide por **conjunto de sinais** e devolve conflito só quando os sinais apontam **naturezas diferentes** (`escrituracao_nfe.py:406-416`: compara `naturezas`, não `candidatos`). A natureza de combustível **nunca** sai do CFOP sozinho: exige NCM na lista (`:319-322`, HI-139), e NCM de lubrificante no CFOP de combustível manda para revenda (8%) e não para o 1,6%. O CSOSN 500/CST 60 no CFOP de combustível não é tratado como sinal (`:330`), porque é o caso normal do posto.

### Por que pesos e não ordem manual, na rotina real

1. **Escala.** Um posto com loja de conveniência gera dezenas de combinações (CFOP × NCM × CSOSN). Com ordem manual, a 40ª regra inserida precisa ser posicionada em relação às 39 anteriores; quem insere raramente lê as outras. Com especificidade, a regra nova é avaliada só contra as que casam com o mesmo item.
2. **Explicabilidade na fila.** "Venceu a regra 12 porque tem NCM exato; a 7 só tem CFOP" é verificável por quem classifica. "Venceu a 7 porque está acima da 12" não diz nada sobre o item.
3. **Erro silencioso.** Na ordem manual, uma regra genérica posta no topo **engole** todas as específicas abaixo sem aviso: é exatamente o acumulador de exceção disfarçado. Na especificidade, a genérica só vale quando nenhuma específica casa.
4. **Rotatividade.** Em escritório, quem cadastra a regra hoje não é quem mantém daqui a um ano. Pesos publicados sobrevivem à troca de pessoa; a ordem é conhecimento tácito.

Ordem manual só tem vantagem quando o contador quer **forçar** uma exceção sem conseguir expressá-la em critério; isso não deve existir no corte 1 (se o critério não existe, ele vai para o corte 2, como lista nomeada de NCM, participante ou CRT).

### Os pesos

A ordem está certa: **NCM acima de CST/CSOSN**. O NCM identifica a mercadoria e é o que separa combustível (1,6%, ICMS fora do DAS, PIS/Cofins concentrado) de lubrificante e de item de conveniência; o CST/CSOSN descreve o tratamento de ICMS que o emitente **declarou**, que é a parte do XML que mais vem errada em posto e pequeno comércio (central 121 lista "CSOSN contra CST" como causa de erro; o código já ignora o 500/60 no combustível por esse motivo). `idDest` é o sinal mais fraco e certo como 1.

O problema não é a ordem, é a **soma**. Com CFOP 8, NCM exato 4, prefixo 2, CST 2, `idDest` 1:

| Regra A | Regra B | Soma | Resultado hoje |
| --- | --- | --- | --- |
| CFOP + NCM prefixo | CFOP + CST | 10 × 10 | conflito |
| CFOP + NCM exato | CFOP + prefixo + CST | 12 × 12 | conflito |
| CFOP + NCM exato + idDest | CFOP + prefixo + CST + idDest | 13 × 13 | conflito |

Esses empates são entre conjuntos **diferentes** de critérios e caem no contador como "conflito" sem que ele veja por quê. **Proposta:** pesos em potências de dois, com o CFOP acima de todos: **CFOP 16, NCM exato 8, NCM por prefixo 4, CST/CSOSN 2, `idDest` 1.** Como NCM exato e prefixo são excludentes dentro de uma regra, dois conjuntos distintos de critérios nunca somam igual; o empate só ocorre entre regras com os **mesmos** critérios preenchidos, que é o único caso em que "conflito" é informativo. Dois desempates adicionais, ainda dentro da especificidade:

- entre dois prefixos de NCM que casam o mesmo item (por exemplo `2710` e `271012`), vence o **mais longo**;
- empate com os mesmos critérios e a **mesma natureza** não é conflito: o item recebe a sugestão e o motivo nomeia as duas regras (é o que o código embutido já faz em `:407-412`). Conflito é só natureza diferente.

### Critério obrigatório além do CFOP

Não torne NCM nem CST obrigatórios em geral: o uso principal da regra de empresa é justamente "todo 5.102 desta loja é revenda", sem NCM. Mas há **uma** obrigatoriedade condicional que eu não abriria mão, porque reproduz no dado a salvaguarda que o código já tem (HI-139):

- **Regra cujo resultado é `combustivel`, `combustivel_revenda` ou `devolucao_combustivel_consumo` exige NCM** (exato ou prefixo). Sem isso, uma regra "CFOP 5.656 → combustível" levaria lubrificante e aditivo ao 1,6% e tiraria do DAS receita que fica dentro dele: recolhimento a menos, em cada nota, para todos os clientes se a regra for de escritório.
- Complemento barato: se o prefixo informado alcança NCM de lubrificante (`NCM_LUBRIFICANTE`) e o resultado é combustível, a tela **avisa** antes de salvar. Não bloqueia: pode ser intenção, com trilha.

### Grau de segurança

Alto na escolha de pesos sobre ordem manual (prática e código concordam). Alto na condição do NCM para combustível (é a HI-139 em forma de dado). Médio nos valores numéricos: qualquer conjunto sem empate entre conjuntos distintos serve; o que não serve é o conjunto que empata.

---

## 2. Quem pode criar regra (HI-153, item 3)

**Resposta curta.** A proposta é coerente: regra de **empresa** por quem escritura (hoje ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO); regra de **escritório** só ADMINISTRADOR e GESTOR. **Não** criar fluxo de aprovação prévia no corte 1: a revisão já existe no ponto certo (a natureza é confirmada pelo contador, e a regra só muda sugestão). O que falta não é aprovação, é **revisão posterior possível**: lista filtrável por autor, prévia de impacto e rastro "quais itens foram confirmados a partir desta regra". FINANCEIRO criando regra fiscal **não** faz sentido pela função do papel, mas a inconsistência está na matriz do fiscal inteiro (HI-21), não nesta regra; não resolva aqui.

### Fundamento

- **ROTINA (controle interno de escritório).** Segregação de funções em escritório contábil pequeno é, na prática, "quem lança não fecha" e "quem parametriza para todos os clientes é quem responde pelo escritório". O produto já tem a primeira (RC-102: fechar e reabrir só ADMINISTRADOR e GESTOR; `requisitos.md:252`). A regra de escritório alcança todos os clientes e, se errada, erra a receita, o anexo e a segregação de todos: é parametrização, e parametrização cabe a quem responde. Isso é prática consolidada e coerente com o conceito de controle interno das normas de auditoria (NBC TA 315, *não conferido hoje*; cito só o conceito, não o item).
- **CÓDIGO.** O padrão de combustível por empresa, que já muda sugestão, é gravado por `papel_pode_escriturar_fiscal` (`api_presumido.py:93-102`); a regra de empresa com a mesma permissão mantém uma matriz só. A composição ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO é a HI-21 reusada da contabilidade, nunca confirmada pelo Fred (`permissoes.py:11-14` e `63-69`; PE-08). A sugestão nunca grava natureza (`NaturezaItemNFe` é gravada pelo contador; `escrituracao_nfe.py:243`); o lote tem prévia e assinatura com 409 (plano, item 4).

### Aprovação prévia: por que não

1. A regra **não produz efeito fiscal sozinha**: entre a regra e o imposto há a confirmação da natureza (item a item ou por grupo do lote) e a efetivação. É um controle de dupla ação já embutido; um terceiro passo só atrasa a fila.
2. No escritório pequeno, aprovação prévia vira autoaprovação (o GESTOR cria e aprova) e dá **falsa** sensação de segregação.
3. O que protege de verdade é poder **desfazer com alcance conhecido**: desativar a regra (já previsto) e encontrar o que ela influenciou (falta, ver abaixo).

### Proposta para o produto

| Item | O que fazer | Por quê |
| --- | --- | --- |
| Permissão | Como proposto. Regra de empresa: `PAPEIS_QUE_ESCRITURAM_FISCAL`; regra de escritório: ADMINISTRADOR e GESTOR, como RC-102. Desativar segue a mesma permissão de criar, no mesmo escopo. | Uma matriz só; parametrização global com quem responde |
| Origem persistida | Ao confirmar natureza (rascunho ou lote), gravar **qual regra** (id e escopo) produziu a sugestão aceita, ou "produto" ou "padrão da empresa". Hoje o plano diz que a sugestão "diz de onde veio"; falta **guardar** isso no item confirmado. | Sem isso, desativar uma regra errada não diz quais notas ela alcançou; com isso, `reclassificar_em_massa` (rascunho) e o estorno (efetivada) têm alvo |
| Prévia de impacto | Antes de salvar, mostrar quantos itens a escriturar e quantos grupos da fila mudam de sugestão com a regra (uma passada, sem gravar). | É a prévia do lote aplicada à regra; evita a regra que "engole" |
| Lista revisável | Filtro por autor, data, escopo, situação; coluna "itens confirmados a partir desta regra". | Revisão posterior pelo GESTOR, que é a segregação possível no escritório pequeno |
| FINANCEIRO | Não criar lista nova. Registrar em PE-08/HI-21 que a regra herda a dúvida da matriz fiscal. | Divergir aqui criaria a segunda lista que o teste `test_dl072_permissoes.py` existe para impedir |

Sobre FINANCEIRO: na rotina de escritório, "financeiro" é honorários, cobrança e caixa do escritório, não classificação fiscal do cliente. Se a resposta do Fred à HI-21 for "financeiro não escritura", a regra de empresa acompanha sozinha, porque usa a mesma tupla.

### Grau de segurança

Alto na permissão por escopo e na recusa de aprovação prévia. Alto na origem persistida (é o que torna a trilha "suficiente", regra do projeto). Médio no FINANCEIRO: depende do que o escritório do Fred entende por esse papel.

---

## 3. O que o sistema de referência permite e nós não devemos reproduzir; salvaguardas que faltam

**Resposta curta.** Cinco comportamentos a **não** reproduzir, dos quais o corte 1 já evita três; e seis salvaguardas que faltam ou estão implícitas no plano e deveriam ficar explícitas.

### Não reproduzir (manual e central)

| Comportamento | Onde está no sistema de referência | Situação no corte 1 |
| --- | --- | --- |
| Acumulador de exceção quando nada casa | manual EF p.470 e 550; central 121 passo 3 | **Evitado** (fila, nunca padrão) |
| Precedência que depende de uma marca de configuração ("Todos como exceção") | central 824, 922, 121 | **Evitado**, desde que os pesos sejam fixos no código e não configuráveis por escritório. Não ofereça "modo de precedência" como opção |
| Trocar a classificação sem recalcular e sem avisar | central 653 | **Evitado** (regra só muda sugestão; efetivada intocada) |
| Reimportar para aplicar regra nova | manual IP p.107 | **Evitado** (sugestão calculada na hora) |
| Duplicar linha copiando critérios | manual EF p.470 e 550 | **Não previsto**; não inclua "duplicar regra" no corte 1. A ação "criar regra pela fila" já pré-preenche a partir do item real, que é o caminho seguro |

### Salvaguardas que faltam ou precisam ficar explícitas

1. **Conflito só entre naturezas diferentes** (item 1 acima). O plano diz "empate de escopo: conflito"; se duas regras do mesmo escopo e mesma especificidade apontam a mesma natureza, isso é redundância, não conflito. Caso contrário, a fila enche de falsos conflitos e o contador aprende a ignorá-la.
2. **NCM obrigatório para resultado de combustível** (item 1).
3. **Origem persistida na natureza confirmada** (item 2). É a salvaguarda que falta mais; sem ela, a trilha de "criar e desativar regra" não se conecta aos lançamentos.
4. **Competência encerrada.** A fila é "por empresa e mês"; itens de notas em competência fechada (RC-101) não podem aparecer como "a classificar" acionável, nem a regra nova deve mudar sugestão de nota cuja competência está encerrada. Hoje o plano não menciona o encerramento. Proposta: a fila só lista competências abertas; para fechadas, mostra contagem em somente leitura.
5. **Regra de escritório escrita com CST contra cliente do Simples.** O corte 1 compara CST/CSOSN "como está na nota" e deixa a equivalência para o corte 2. Isso não cria padrão silencioso (o item cai na sugestão embutida ou na fila), mas cria regra que **nunca casa** sem que o autor saiba. Proposta: ao salvar regra de escritório com CST de regime normal, aviso "clientes do Simples emitem CSOSN; esta regra não os alcança". É o erro número 1 do suporte do concorrente (central 121), e custa uma frase.
6. **Regra pré-preenchida pela fila com todos os critérios do grupo.** O grupo traz CFOP, NCM, CST, `idDest`; se a regra nasce com tudo preenchido, a loja de conveniência gera uma regra por NCM. Proposta: a tela pré-preenche, mas destaca que NCM, CST e `idDest` são opcionais e mostra, na prévia de impacto, quantos grupos a regra alcança **com** e **sem** cada critério. O contador decide o quão genérica ela fica, vendo o alcance.

Duas observações que não são salvaguarda, mas evitam retrabalho: (a) a imutabilidade da regra e o fim de vigência "com motivo" estão certos e são melhores que o "Nova Vigência" editável do manual (p.366); (b) a vigência comparada com a **data de emissão** está certa para classificar (HI-57), e nada muda com a competência da receita.

### Grau de segurança

Alto nos itens 1 a 4 (decorrem do código atual e de regras já confirmadas do projeto). Alto no 5 como aviso. Médio no 6: é ergonomia, e o Fred pode preferir regras específicas.

---

## 4. Posto de combustível no Simples (PE-91, item 2): o que muda e o que fazer enquanto o Fred não responde

**Resposta curta.** Não muda **nada no corte 1**. Os critérios (CFOP, NCM, CST/CSOSN, `idDest`) e o resultado (natureza) são os mesmos para Simples e Presumido; a natureza de combustível já existe para os dois regimes e a sugestão embutida já trata o CSOSN 500 do posto. O que muda com um posto no Simples é só o **cálculo**: o pré-DAS recusa a natureza combustível com nome (HI-132: ICMS fora do DAS e PIS/Cofins concentrado; LC 192/2022 **não lida**, P6 da consulta anterior). Enquanto o Fred não responde, o produto **não faz nada novo**: mantém a recusa nomeada no pré-DAS, e a própria fila e a escrituração vão mostrar se existe empresa do Simples com item de combustível.

### Fundamento

- **CÓDIGO.** `tipo_da_nota`, `naturezas_permitidas` e `_candidatos_do_item` não consultam regime (`escrituracao_nfe.py:193-239`, `287-334`). O CSOSN 500 e o CST 60 são tratados igualmente no CFOP de combustível (`:330`). O pré-DAS recebe a natureza e decide por `classificacao_da_venda` (`models.py:3474-3492`), com o lado conservador declarado ("paga a mais, nunca a menos").
- **CÓDIGO, com uma ressalva.** O padrão de combustível mora em `ParametrosPresumidoEmpresa` (`models.py:2819-2847`) e é lido por `presumido.parametros_da_empresa(empresa)` em `escrituracao_nfe.py:1765`. **Inferência:** a leitura não filtra regime, então um posto do Simples também receberia o padrão se ele estiver gravado; mas a tela e o nome do modelo dizem "Presumido", e um posto do Simples pode simplesmente **não ter** o parâmetro cadastrado. Não verifiquei a tela. Isso é pendência de produto, não de classificação.
- **NORMA.** Nenhuma lida hoje. A afirmação "ICMS do combustível fora do DAS" está na HI-132 com a base da LC 123 (art. 13, § 1º, XIII, "a"), registrada em consulta anterior; não a reli.

### Proposta para o produto

- Corte 1: nada condicionado à resposta. Não bloquear, não criar natureza nova, não criar critério de regime.
- Se a resposta for "sim, há posto no Simples": a frente é o pré-DAS (DL-088/089), com a leitura da LC 192/2022 e da Res. CGSN 140 sobre segregação, e a decisão de mover o padrão de combustível para fora dos "parâmetros do Presumido" (ou renomear). Nenhuma dessas é DL-087.
- Se a resposta for "não": nada muda, e a recusa do pré-DAS continua como proteção contra cliente futuro.

### Grau de segurança

Alto em "não muda a classificação". Médio na leitura do padrão de combustível para empresa do Simples (inferência de código; a tela não foi verificada).

---

## Hipóteses para o Fred validar

| # | Hipótese | Tipo | Fonte e marca | O que muda se discordar |
| --- | --- | --- | --- | --- |
| H1 | Precedência por **especificidade com pesos fixos**, não ordem manual; pesos em potências de dois (CFOP 16, NCM exato 8, prefixo 4, CST/CSOSN 2, `idDest` 1), prefixo mais longo vence, e empate com a mesma natureza não é conflito | produto | *manual* (central 121, 824, 922; EF p.453, 470, 490, 550); *código* `escrituracao_nfe.py:406-416` | Se preferir ordem manual, exigir que a tela mostre a lista inteira ordenada e avise regra genérica acima de específica; eu não recomendo |
| H2 | Regra com resultado de **natureza de combustível exige NCM**; prefixo que alcança lubrificante gera aviso | produto, decorrente da HI-139 | *código* `:319-322`; HI-139 | Sem a condição, lubrificante pode cair no 1,6% por regra de escritório |
| H3 | Regra de empresa: quem escritura; regra de escritório: ADMINISTRADOR e GESTOR; **sem aprovação prévia**; revisão posterior por lista, prévia de impacto e origem persistida | produto, controle interno | RC-102; *código* `api_presumido.py:93-102`, `permissoes.py:63-78` | Se quiser aprovação prévia, só para regra de escritório, e com prazo para não travar a fila |
| H4 | **Origem da sugestão gravada** na natureza confirmada (regra, produto ou padrão da empresa) | produto, trilha | regra do projeto "trilha suficiente"; *código* `escrituracao_nfe.py:243` | Sem isso, desativar regra errada não encontra o que ela alcançou |
| H5 | FINANCEIRO continua na tupla por **reuso** (HI-21), não por adequação à função; a dúvida é da matriz fiscal (PE-08), não da DL-087 | produto | `permissoes.py:11-14` | Se o Fred tirar FINANCEIRO da escrituração, a regra acompanha sozinha |
| H6 | Fila e reaplicação de sugestão **respeitam competência encerrada** (RC-101) | produto | RC-101 | — |
| H7 | Aviso ao salvar regra de escritório com CST de regime normal: não alcança clientes do Simples (CSOSN); equivalência fica no corte 2 | produto | *manual* (central 121, causa 2) | — |
| H8 | Posto no Simples **não muda o corte 1**; muda só o pré-DAS (HI-132) e exige leitura da LC 192/2022 | produto + norma pendente | *código* `:193-239`, `:287-334`, `models.py:3474-3492`; HI-132 | — |

## Pendências

| # | Pendência | Onde resolver | Bloqueia |
| --- | --- | --- | --- |
| P1 | Fato da carteira: há posto no Simples? (PE-91 item 2, P12 anterior) | Fred | Nada na DL-087; afeta DL-088/089 |
| P2 | Composição real da matriz fiscal (FINANCEIRO escritura?) — HI-21/PE-08 | Fred | Nada na DL-087 (reuso da tupla) |
| P3 | Tela e modelo do padrão de combustível estão sob "Presumido" (`models.py:2819`); confirmar se empresa do Simples consegue gravá-lo, se P1 for "sim" | arquiteto (código) | Só se P1 for "sim" |
| P4 | LC 192/2022 e Res. CGSN 140 sobre combustível no DAS (P6 anterior), não lidas | Planalto; portal do Simples | Pré-DAS de posto no Simples; não a classificação |
| P5 | A definição exata de "conflito" (natureza diferente) e o desempate por prefixo mais longo precisam entrar no plano e nos testes de mutação (critério 8 do plano) | arquiteto | DL-087, frente A |

## Fontes consultadas hoje

**Manual e central do sistema de referência (cópia local do scratchpad, baixada em 09/10/2026; rotina, não norma):** `dominio/escrita.txt` (Domínio Escrita Fiscal, versão 10.1A-12, 2018), páginas 453, 464-470, 490-491, 542-550, por busca de termos; `dominio/sol121.html`, `sol824.html`, `sol922.html` (Central de Soluções, códigos 121, 824 e 922), texto integral extraído.

**Repositório (caminhos absolutos):** `/home/user/DataLedger/docs/planos/DL-087-classificacao-fiscal-versionada.md` · `/home/user/DataLedger/docs/projeto/pesquisa-acumuladores-2026-10-09.md` · `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md` · `/home/user/DataLedger/docs/projeto/consultas/2026-10-08-contador-senior-fiscal.md` (linhas 31-41) · `/home/user/DataLedger/docs/projeto/requisitos.md` (linhas 104, 126-130, 208, 217-229, 252) · `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py` (160-453, 1762-1772) · `/home/user/DataLedger/apps/fiscal/permissoes.py` · `/home/user/DataLedger/apps/fiscal/api_presumido.py` (93-102) · `/home/user/DataLedger/apps/fiscal/models.py` (2806-2875, 3474-3497) · `/home/user/DataLedger/apps/tenancy/models.py` (89-102).

**Norma:** nenhuma lida hoje; CTN art. 144 e NBC TA 315 mencionados só como conceito, *não conferidos*.
