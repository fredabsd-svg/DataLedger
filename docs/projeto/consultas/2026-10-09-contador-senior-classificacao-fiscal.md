# Consulta ao contador-senior sobre a classificação fiscal (acumulador), as regras de importação e a sequência do fiscal — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Carteira de referência:** Palmas/TO; Simples e Presumido; comércio, postos (posto, distribuidora, TRR) com NFC-e em alto volume; serviços (RC-173) · **Grau de segurança geral:** médio-alto nas decisões de produto; alto nas normas marcadas *lido*; médio onde só há *cópia*.

**Marcas.** *lido* = texto oficial no Planalto, baixado hoje por curl; *cópia* = cópia íntegra em site terceiro; *manual* = pesquisa de hoje (`pesquisa-acumuladores-2026-10-09.md`), rotina e não norma; *código* = arquivo e linha do repositório; *secundário* = notícia ou artigo; *não conferido* = conhecimento meu, sem leitura hoje.

**O que li hoje em fonte oficial (Planalto):** LC 214/2025 arts. 12, 41, 47, 127, 172, 343, 346, 347, 348, 509, 542, 543, 544; EC 132/2023, ADCT arts. 125 e 126; Lei 9.715/1998 art. 8º; Lei 9.718/1998 arts. 3º e 4º; MP 2.158-35 art. 42; Lei 10.833/2003 arts. 2º e 10 (caput e inciso I). **Em cópia:** Res. CGSN 190/2026 (normaslegais; o texto dos Anexos I a V novos **não** está na cópia). **Não alcançado:** portal do Simples Nacional (a página de resoluções abre, mas não lista o texto da 190), `normas.receita` (só renderiza com JS), Anexos I a V da Res. 190, NT 2026.008 da NF-e, RICMS/TO.

Tudo abaixo é **HIPÓTESE para validação do Fred** (HI-54). Separo em cada item **NORMA** (com marca), **ROTINA/PRODUTO** (prática de escritório e decisão de software) e **RECOMENDAÇÃO**.

---

## 1. Desenho da classificação fiscal do DataLedger (o nosso acumulador)

**Resposta curta.** A classificação fiscal deve ser **uma escolha só do contador por item de documento** (natureza), que **expande por regra declarativa com vigência** em linhas por tributo, contas contábeis e marcas de obrigação. Isso confirma o item 1 da consulta de 08/10 e a decisão 4 do DL-067 ("quatro peças"), e a pesquisa de hoje reforça o motivo: o acumulador do sistema de referência junta natureza, imposto, conta e importação num único cadastro mutável por empresa, e os erros relatados no próprio suporte dele (acumulador sem imposto, troca que não recalcula, vigência velha) nascem dessa junção (*manual*, seções 2.3 e 5). O que não deve ser copiado é a junção; o que deve ser absorvido é a **lista de atributos** que a prática provou necessária.

### Fundamento

- **NORMA.** Não há leiaute oficial de acumulador. O que a norma exige é que cada valor de tributo seja reconstruível a partir do documento e da lei vigente **na data do fato gerador** (CTN art. 144 — *não conferido hoje*, texto estável), e a guarda por cinco anos (NT RFB 011/2026 para a EFD-Contribuições — *cópia*, consulta de 08/10, item 7). Tudo o mais nesta pergunta é rotina e produto.
- **ROTINA (manual, não norma).** O acumulador de referência guarda: incide sobre faturamento/receita bruta (p.367); tipo de movimento (p.375); impostos que fazem base, com percentual de base, alíquota, redução e destino da diferença para isentas/outras (p.379-385); Simples com anexo, tabela e situação fiscal por tributo (p.2089-2090); PIS/Cofins por CST, natureza da receita, vínculo e base de crédito (p.390-394); contas por acumulador e por imposto, com histórico (p.385-386, 407-414, 426-431); CFOPs permitidos (p.405-407); vigência com "Nova Vigência" (p.366). Isso é o inventário de **atributos**, não o desenho.
- **CÓDIGO.** Hoje a natureza carrega só `papel`, `mercado`, `segregacao`, `anexo_simples` (texto) e `atividade_presumido` (`apps/fiscal/models.py:2664-2797`); `ItemNFe` já guarda CST/CSOSN, `orig`, `cst_pis`, `cst_cofins`, `cst_ipi`, `c_benef`, `v_icms_deson`, FCP e o grupo IBS/CBS bruto (`models.py:3027-3175`, campos em 3070-3153). Ou seja, **o dado para gerar linhas por tributo já está guardado; falta a regra que o interpreta.** O regime da empresa tem vigência (`apps/empresas/models.py:690-711`); a atividade de presunção e a alíquota de ISS também (pesquisa, seção 7).

### Proposta para o produto

**Quatro peças, com os atributos abaixo.** O contador toca só a peça 1 no dia a dia; as peças 2 a 4 são dados versionados.

**Peça 1 — Natureza da operação (a escolha do contador).**

| Atributo | Valores | Fonte do atributo |
| --- | --- | --- |
| Código curto e nome | ex.: `S-REV` "Revenda de mercadoria" | produto |
| Tipo de movimento | saída, entrada, serviço prestado, serviço tomado, ajuste, estorno | produto; corresponde ao "Lançamentos" do manual (p.375) |
| Papel na receita bruta | receita, dedução, não receita | já existe (`models.py:2681`) |
| Mercado | interno, externo | já existe |
| Documentos admitidos | NF-e, NFC-e, NFS-e, CT-e, NFCom, lançamento manual | produto |
| CFOPs admitidos (lista fechada opcional) | ex.: revenda só x.102/x.403 | produto; evita o erro "serviço lançado como comércio" |
| Situação | ativa/inativa com data | produto |

**Peça 2 — Regra tributária declarativa (uma por natureza × regime × tributo × vigência).**

| Tributo | Atributos da regra | Norma de origem (a cadastrar com fonte e data) |
| --- | --- | --- |
| **Receita** | incide em faturamento; incide em receita bruta; segregação do Simples (normal, ST, monofásico, exportação, ISS retido, outro município) | LC 123 art. 18 § 4º-A; Res. CGSN 140 art. 25 (*cópia*, consulta de 08/10) |
| **Simples** | anexo (I a V), fator R aplicável, situação de cada tributo componente (tributado, isento/reduzido, ST, monofásico, imune, fora do DAS), percentual de redução | LC 123 art. 18; Res. CGSN 140 arts. 21-25. Desde 01/01/2027: CBS e IBS como componentes e segregação de "tributação concentrada ou ST de IBS/CBS" (Res. 190, novo § 6º do art. 25 — *cópia*) |
| **IRPJ/CSLL (Presumido)** | atividade de presunção (já existe), receita que entra integral (financeira, ganho de capital) | Lei 9.249 art. 15 (já citado no código) |
| **ICMS** | situação (tributado / isento ou não tributado / outras / ST / diferido / suspenso), direito a crédito (sim, não, parcial com motivo), alíquota ou "a da nota", redução de base, ST (substituto, substituído, antecipação), DIFAL (contribuinte × não contribuinte), FECOEP, `cBenef`, código de ajuste da apuração | RICMS/TO e Convênios (*não conferido hoje*; DL-067 §ICMS lista alíquota 20% e FECOEP como *secundário*) |
| **IPI** | CST, alíquota ou "a da nota", crédito sim/não | TIPI (*não conferido*); zero em 2027 salvo ZFM (ADCT art. 126, III, a — *lido*) |
| **PIS/Cofins (até 12/2026)** | regime (cumulativo/não cumulativo), CST de saída e de entrada, natureza da receita (tabela 4.3.x do SPED), monofásico/alíquota zero, ST, crédito (vínculo e base, só Real), base com ICMS fora | Lei 9.715 art. 8º, I: 0,65% (*lido*); Lei 9.718 art. 4º, IV e art. 8º: 3% (*lido parcialmente*: vi o 3% no art. 4º, IV; o caput do art. 8º não saiu no texto extraído); Lei 10.833 art. 10 (*lido* caput e inciso I; o inciso II, Presumido, *não conferido* no trecho); MP 2.158-35 art. 42, I: alíquota zero na revenda de gasolina, diesel e GLP por distribuidores e varejistas (*lido*) |
| **ISS** | devido pelo prestador / retido / outro município / imune-isento-reduzido / fora da lista, subitem LC 116, alíquota por município (já existe) | LC 116; Dec. 1.667/2018 de Palmas (*cópia*) |
| **Retenções** | IRRF, CSRF (PIS+Cofins+CSLL até 12/2026; só CSLL 1% a partir de 2027), INSS, ISS retido, bases e dispensa (Simples) | Lei 10.833 arts. 30-31 na redação da LC 214 art. 509, eficácia 01/01/2027 (LC 214 art. 544, III — *lido*) |
| **IBS/CBS** | CST e cClassTrib esperados, crédito (regular) ou "no DAS" (Simples), tributação concentrada em combustíveis | LC 214 arts. 12, 41, 47, 172 (*lido*) |

Cada regra tem: `vigencia_inicio`, `vigencia_fim`, `fonte` (norma, artigo, data de consulta), `situacao` (confirmada/hipótese/desativada) e `escopo` (global, escritório, empresa). **Regra em "hipótese" gera linha com aviso; regra "desativada" não gera e bloqueia a efetivação** (HI-56).

**Peça 3 — Modelo contábil (por natureza e por tributo).** Papéis de conta, não números: "receita de revenda", "clientes", "ICMS a recolher", "ICMS a recuperar", "PIS a recolher", "ISS retido a compensar", "devoluções de vendas", frete, seguro e despesas acessórias. O escritório **mapeia papel → conta do plano da empresa** uma vez; a natureza não conhece conta. Históricos por modelo com variáveis (número, participante, competência). Isso corresponde às abas Contabilidade (p.407-414) e Contas por imposto (p.385-386, 426-431) do manual, mas desacoplado do plano de contas de cada empresa.

**Peça 4 — Mapa para obrigações.** Registros do SPED e campos do PGDAS-D que a natureza alimenta (C100/C170/C190, natureza da receita, campo de receita segregada). Só quando esses geradores existirem; o atributo nasce vazio.

**Escopo e sobreposição.**

| Camada | Quem mantém | O que pode fazer | O que não pode |
| --- | --- | --- | --- |
| **Global (pacote padrão)** | o produto, com fonte e vigência por regra | catálogo de naturezas, regras de norma federal e do TO, tabelas (CFOP, NCM monofásico, Anexos do Simples) | nada específico de uma empresa |
| **Escritório** | o Fred | ativar/desativar naturezas, mapear papéis de conta ao plano padrão do escritório, criar regra para município ou benefício do TO que o pacote não trouxe, criar natureza derivada (nunca editar a global) | alterar regra global; usar regra sem fonte |
| **Empresa** | o Fred, por empresa | mapa de contas da empresa, benefício fiscal próprio (`cBenef`, TARE), opção de regime (já existe com vigência), ativação de natureza por empresa | regra sem vigência nem fonte |

Precedência de leitura: empresa > escritório > global, sempre pela regra **vigente na data do fato gerador**, e a linha gerada grava **qual regra, de qual camada e de qual vigência** a produziu.

**Vigência e mudança de regra — a regra que protege a conciliação.**

1. Regra nunca é editada depois de usada por lançamento efetivado: cria-se **nova vigência**, e a anterior ganha `vigencia_fim`. É o "Nova Vigência" do manual (p.366), com uma diferença: aqui a antiga fica imutável.
2. Lançamento efetivado **não recalcula em silêncio** (DL-067, decisão 6; é o que a central do concorrente admite não fazer, só que lá por omissão — *manual*, central 653). Ao criar vigência que alcance competências com lançamentos efetivados, o produto lista os afetados e oferece **"reprocessar com trilha"**: estorna e reescritura em bloco, com assinatura e memória antes/depois, só em competência aberta. Competência encerrada exige reabertura explícita (RC-101).
3. Alterar a **natureza** de um item efetivado segue o mesmo caminho (estorno + nova efetivação com trilha), nunca `UPDATE` na linha. Hoje `reclassificar_em_massa` só atua em rascunho (`apps/fiscal/escrituracao_nfe.py:1118-1191`, pesquisa seção 7); isso está certo e fica.
4. Linha de tributo **não é editável** pelo contador. Divergência só por natureza específica ou por "exceção com motivo" gravada na trilha (HI-56).

### Segurança

- Alta na arquitetura (quatro peças, vigência, imutabilidade): é prática consolidada e já decidida no DL-067.
- Média na lista de atributos por tributo: completa para Simples, Presumido, PIS/Cofins e ISS; para ICMS-TO a lista é correta em gênero, mas cada atributo (benefícios, códigos de ajuste, FECOEP) precisa do RICMS/TO lido antes de virar regra global.
- Risco principal: tentar cadastrar todas as peças de uma vez. Primeiro corte deve **migrar os três catálogos atuais para a peça 1 e 2 sem mudar comportamento** (mesmo resultado nos 8.791 testes citados em `revisao-do-fiscal-2026-10-09.md`), e só depois acrescentar tributos.

---

## 2. Regras de importação (critério → classificação)

**Resposta curta.** O produto deve ter uma **tabela de regras do escritório** (com cópia por empresa) separada do catálogo de naturezas, com critérios **CFOP, CST/CSOSN do ICMS, CST do PIS, NCM (ou faixa), papel da empresa na nota, origem (`idDest`/UF), forma de pagamento e participante**; precedência **explícita por especificidade declarada e, em empate, por ordem numérica da regra**; e tudo que não casar vai para a **fila "a classificar"** com o motivo, nunca para um padrão silencioso. A sugestão em código de hoje vira o **pacote global de regras**, legível e com vigência, e deixa de ser `if` em Python.

### Fundamento

- **NORMA.** Nenhuma. É rotina.
- **ROTINA (manual).** O sistema de referência usa, por formato de arquivo, linhas "critérios → acumulador" com: operação/forma de pagamento, CFOP, CST de ICMS, CST de PIS, origem, produto (código, NCM ou grupo) e cliente/fornecedor; tipo de inscrição e regime do fornecedor nas entradas; acumulador de exceção quando nada casa; nota com vários CFOPs segmentada por CFOP; e a marca "considerar Todos como exceção" para a específica vencer a genérica (p.464-470, 508-513, 542-550; central 824, 894, 922). A precedência geral **não está documentada** (pesquisa, seção 4). Os erros mais comuns do suporte: falta de linha para a combinação; CSOSN contra CST; CFOP de saída sem conversão para entrada; nota de posto à vista e a prazo no mesmo CFOP (central 121; fórum 2016, *secundário*).
- **CÓDIGO.** Hoje a sugestão de NF-e é determinística em `apps/fiscal/escrituracao_nfe.py:226-395`: finalidade (`finNFe`) → CFOP (tabela oficial em `cfop.py`) → NCM de combustível/lubrificante → CST/CSOSN → `idDest`. Conflito entre sinais e "sem sinal" devolvem `None` com motivo (linhas 387-393). A tomada segue uma lista ordenada "a primeira que casa vence" (`apps/fiscal/tomadas.py:430-468`). O lote agrupa por (CFOP, CST/CSOSN, natureza sugerida) e lista as notas fora do lote com motivo (`escrituracao_nfe_lote.py:22-39, 352-357`; DL-085 linhas 29, 60, 154). Ou seja, **o produto já tem o comportamento certo (sem padrão silencioso); o que falta é tirar a regra do código e dar ao escritório o poder de acrescentar critérios.**

### Proposta para o produto

**Critérios do primeiro corte, em ordem de valor para a carteira do Fred:**

| # | Critério | Por que agora | Fonte no XML |
| --- | --- | --- | --- |
| 1 | CFOP (código, faixa ou grupo da tabela oficial) | já é o eixo da sugestão | `det/prod/CFOP` |
| 2 | CST/CSOSN do ICMS | separa ST, monofásico e tributado; aceitar os dois (regra escrita com CST e nota com CSOSN **casa pela tabela de equivalência**, nunca falha por isso — é o erro nº 1 do suporte do concorrente) | `ICMSxx/CST` ou `CSOSN` |
| 3 | CST do PIS (e Cofins, que acompanha) | distingue monofásico/alíquota zero (04, 06) de tributado (01) na mesma revenda; essencial para posto e para a segregação do Simples | `PIS/CST` |
| 4 | NCM (código, prefixo ou lista nomeada: combustíveis, lubrificantes, monofásicos) | já existe para combustível; a lista nomeada evita cadastrar produto | `prod/NCM` |
| 5 | Papel da empresa na nota | emitente × destinatário decide saída × entrada; pré-requisito das compras (A2) | `emit/CNPJ` vs `dest/CNPJ` |
| 6 | Origem/destino | `idDest` 1/2/3 e UF do emitente; decide DIFAL e exportação | `ide/idDest`, `emit/enderEmit/UF` |
| 7 | Forma de pagamento | só onde muda a classificação: regime de caixa e o caso à vista/a prazo que o concorrente precisa; **adiar** até haver empresa em caixa (hoje bloqueado, `receita.py:1307`) | `pag/detPag/tPag` |
| 8 | Participante (CNPJ/CPF, e para entradas: `CRT` do emitente = optante do Simples) | compras de fornecedor do Simples não dão crédito pleno de ICMS/PIS; transferência entre estabelecimentos; cliente específico com tratamento próprio | `emit/CRT`, `emit/CNPJ`, `dest/CNPJ` |
| 9 | Tipo de documento e finalidade | NF-e/NFC-e/CT-e/NFS-e; `finNFe` | `ide/mod`, `ide/finNFe` |

Fora do primeiro corte: código de produto do emitente (`cProd`), grupo de produto cadastrado, série, CEST sozinho. Entram quando houver cadastro de produto (B1).

**Precedência explícita (nenhuma implícita):**

1. Cada regra declara **escopo** (empresa > escritório > global) e **especificidade** = número de critérios preenchidos, com peso fixo publicado na tela: participante (8) > NCM código (6) > NCM lista/prefixo (5) > CST PIS (4) > CST/CSOSN ICMS (4) > CFOP código (3) > CFOP faixa (2) > origem/papel/finalidade (1 cada). Soma maior vence.
2. Empate na soma → escopo mais próximo da empresa vence.
3. Empate ainda → **conflito**: o item vai para "a classificar" com as duas regras nomeadas. Nunca "a primeira da lista".
4. Regra tem vigência; a que vale é a vigente na **data de emissão** do documento (para classificar) — a competência da receita continua sendo decidida pela natureza e pela data de competência (HI-57).
5. Nota com mais de um CFOP ou CST é classificada **por item** (já é assim: `NaturezaItemNFe`), não segmentada em várias notas.

**A fila "a classificar" (nunca padrão silencioso).** Cada item sem regra, com conflito ou com regra em "hipótese" entra numa fila por empresa e mês com: motivo nomeado (texto fixo, como hoje), sinais lidos (CFOP, CST, NCM, CRT), sugestão de regra nova pré-preenchida com esses sinais, e ação "criar regra e reaplicar aos pendentes deste mês". Fechamento da competência exige fila vazia ou cada item justificado (HI-59, nível "bloqueia" para o que muda guia). Isso substitui o "acumulador de exceção" do concorrente, que é o padrão silencioso que a consulta de 08/10 recusou (item 1, letra d).

**Convivência com a sugestão em código e com o lote (DL-085).**

- Fase 1: a sugestão atual passa a **gravar qual regra sugeriu** (hoje grava só a origem do sinal, `Sugestao.motivo`). As regras do código viram **dados do pacote global**, carregados por migração de dados, com os mesmos testes passando (migração sem mudança de comportamento).
- Fase 2: a tabela do escritório entra **antes** da global na resolução; a prévia do lote continua agrupando por (CFOP, CST/CSOSN, natureza), acrescentando a **regra que decidiu** à assinatura do grupo. A troca de natureza por grupo que a DL-085 já faz passa a oferecer "transformar esta escolha em regra do escritório" — é assim que o posto com 10.000 NFC-e deixa de ser revisado item a item (A10).
- Reaplicação: regra nova **não altera efetivada**; reaplica só a rascunhos e à fila. Para efetivadas, o caminho é o da pergunta 1 (estorno + reescrituração com trilha).

### Segurança

Alta no desenho (é o que o produto já faz, generalizado). Média nos pesos de precedência: são proposta minha; o Fred pode preferir ordem manual numérica por regra (como "número da linha" no concorrente). Qualquer das duas serve, **desde que seja explícita e visível na tela da fila**.

---

## 3. Sequência das próximas etapas

**Resposta curta.** Primeiro a **classificação versionada migrada sem mudar comportamento** (DL-087) **junto com** a leitura oficial da virada de 2027, porque 01/01/2027 é o único prazo que **para o escritório inteiro** (o código recusa Simples, NF-e e caixa de 2027 em quatro pontos). Depois **notas de entrada**, depois **ICMS-TO em fatias**, depois **integração contábil e livros**. PIS/Cofins do Presumido só como conferência e só se o Fred decidir (pergunta 4).

### Fundamento normativo das datas (o que mudou com a leitura de hoje)

- **PIS/Cofins acabam em 01/01/2027.** ADCT art. 126, II (EC 132/2023): "a partir de 2027 ... serão extintas as contribuições previstas no art. 195, I, 'b', e IV, e a contribuição para o PIS ... desde que instituída a CBS" (*lido*). A CBS foi instituída pela LC 214/2025 (*lido*), e o art. 542 da LC 214 revoga a partir de 01/01/2027 a base legal histórica (LC 7/1970 art. 3º, b; LC 70/1991 arts. 1º a 6º; etc.) (*lido*). **Logo, para out, nov e dez/2026 valem PIS 0,65% (Lei 9.715 art. 8º, I — *lido*) e Cofins 3% (Lei 9.718 — *lido* no art. 4º, IV; caput do art. 8º não extraído) no regime cumulativo do Presumido (Lei 10.833 art. 10 — caput e inciso I *lidos*; inciso II *não conferido*).** O que **não** acaba: o dever de retificar e guardar a EFD-Contribuições por 5 anos (NT 011/2026, *cópia*, consulta de 08/10, item 7), e a compensação do saldo credor de 31/12/2026 com a CBS.
- **CBS em 2027.** Alíquota de referência menos 0,1 p.p. em 2027-2028 (LC 214 art. 347; ADCT art. 127 — *lidos*). A resolução do Senado com a alíquota de referência **não foi lida**; o DL-067 a dá como prevista até 15/12/2026 (*secundário*). Combustíveis: regime específico monofásico (LC 214 arts. 172-180 — art. 172 *lido*), fora da redução do art. 347.
- **Simples 2027.** Res. CGSN 190, de 04/08/2026, DOU 10/08/2026, **existe**, altera a Res. 140 e produz efeitos a partir de **01/01/2027** (art. 9º — *cópia*). Confirmado nela: CBS e IBS entram no art. 4º (tributos do DAS) e saem PIS/Cofins; art. 5º passa a excluir do DAS a CBS/IBS do regime regular e a "tributação concentrada em uma única etapa (monofásica)"; seção IV-A (arts. 40-C e 40-D): opção pelo regime regular **semestral**, janela 01 a 30/09 para janeiro e 01 a 31/03 para julho, cancelável até 30/11 (janeiro) ; art. 22-A deduz do DAS as parcelas de CBS/IBS de quem optou pelo regular; art. 38-B: a DEFIS passa a ser prestada **no PGDAS-D, de janeiro a março**; art. 25 § 6º novo: segregar receita com tributação concentrada ou ST de IBS/CBS; **art. 22 § 2º novo: nos 1º e 2º meses de atividade usa-se a 1ª faixa, e do 3º ao 13º a média dos meses anteriores** — isso **muda a regra de RBT12 que o código implementa hoje** (`rbt12.py`, regra do art. 22 §§ 2º-3º atual: 1º mês × 12). Os **Anexos I a V novos (tabelas de repartição 2027-2033) não estão na cópia que li**: tabelas do DAS 2027 continuam **não lidas**.
- **NF-e 2027.** A regra de receita (NT 2026.008, `vProd` com IBS/CBS) continua **não lida** (HI-133). O bloqueio em `escrituracao_nfe.py:759-779` está certo até alguém ler.

### Sequência que eu faria

| Ordem | Etapa | Conteúdo mínimo | Risco de atrasar, para o cliente |
| --- | --- | --- | --- |
| 0 (em curso) | DL-085, DL-082, DL-084 | fechar o aberto | Simples do comércio sem pré-DAS de 11/2026; Presumido sem rotina de quotas |
| 1 | **DL-086** revisão de documentação | I1-I11 e banner `module_homes.py:909-912` | nenhum para o cliente; alto para a equipe (planeja contra mapa errado) |
| 2 | **DL-087 classificação versionada, corte 1** | peças 1 e 2 como dados; migrar os 3 catálogos sem mudar comportamento; tabela de regras com a fila "a classificar"; a sugestão em código vira pacote global | tudo o que vem depois reabre o catálogo em código; postos continuam revisando item a item |
| 2' (paralelo) | **Leitura oficial da virada** | Anexos da Res. 190 no DOU/portal; NT 2026.008; resolução do Senado (CBS 2027) | **01/01/2027 o escritório não apura nenhum Simples nem escritura NF-e**: é o único atraso que para a carteira inteira |
| 3 | **DL-088 BL-72** origem no lançamento contábil | migração em `contabilidade` | sem ele não há integração; não afeta guia |
| 4 | **DL-089 virada 2027, parte Simples** | tabelas 2027 como dado com vigência; CBS/IBS no DAS; art. 22 § 2º novo; segregação de concentrado/ST de IBS-CBS; destravar `rbt12.py:58,487`, `pre_das.py:831`; receita da NF-e 2027 quando a NT for lida | **multa e DAS errado em fevereiro/2027** para todo cliente do Simples; e a janela de março/2027 do regime regular passa sem simulador |
| 5 | **DL-091 NF-e de entrada** (compras, devolução de compra, CFOP de entrada derivado do de saída, crédito como linha gerada mas **sem apuração** ainda) | depende de 2 | sem entradas não há ICMS nem livro; o Domínio continua fazendo (sem dano ao cliente, só sem ganho) |
| 6 | **DL-092/093 ICMS-TO** em fatias: (a) próprio e conferência contra a nota; (b) ST/antecipação e DIFAL; (c) FECOEP e benefícios; postos: combustível com ICMS monofásico (LC 192/2022, *não conferido*; revogada só em 2033, LC 214 art. 543, VII — *lido*) fora da apuração própria | depende de 5; RICMS/TO lido | ICMS do TO vence dia 9 (DL-067, *secundário*): erro = multa mensal no maior imposto do comércio; mas o Domínio cobre até a migração |
| 7 | **DL-094 integração contábil, fatia 1** | papéis de conta por natureza, prévia do lançamento | contabilidade digitada em dobro; sem risco fiscal |
| 8 | **DL-095 livros de entradas e saídas** | classe "Livro" | obrigação de guarda; sem prazo mensal |
| 9 | **DL-090 PIS/Cofins conferência** | só se o Fred decidir (pergunta 4) | três competências; o Domínio cobre |

Por que a virada entra antes das entradas e do ICMS, mesmo com o ICMS sendo "o que mais pesa": porque o ICMS **tem quem faça** (o Domínio, até cada obrigação passar no paralelo, decisão 11 do DL-067) e a virada **não tem substituto dentro do produto** — em 01/01/2027 o DataLedger simplesmente para para o Simples. E a virada depende de leitura que ainda não aconteceu; começar a leitura agora é barato e evita descobrir em dezembro que falta a tabela.

### Segurança

Alta na ordem 1-4 (datas lidas hoje). Média em 5-8: a ordem entre entradas e ICMS é técnica (uma depende da outra), mas o tamanho do ICMS-TO depende do RICMS/TO, que ninguém leu em fonte oficial ainda.

---

## 4. As duas decisões do Fred — minha recomendação

**(a) PIS/Cofins do Presumido para out-dez/2026: construir conferência ou deixar no Domínio?**

**Recomendação: deixar no Domínio e não construir gerador nem apuração própria agora.** Construir, no máximo, a **marca de PIS/Cofins na classificação** (CST, natureza da receita, monofásico/alíquota zero) como atributo da peça 2 — isso a CBS vai reaproveitar em 2027 e custa pouco; o cálculo de 0,65% e 3% sobre a receita já escriturada é uma linha de relatório que pode ser ligada em uma tarde **se** sobrar tempo depois da virada. Motivos: (i) três competências de vida útil (ADCT art. 126, II — *lido*); (ii) o escritório já fecha PIS/Cofins no Domínio e vai continuar entregando a EFD-Contribuições de lá até 02/2027 (decisão 8 do DL-067); (iii) o risco de erro para o cliente é nulo, porque o DataLedger não gera guia nem arquivo (HI-55); (iv) o tempo que isso consome é o tempo da virada. O que **não** se pode deixar de fazer: guardar o saldo credor de PIS/Cofins em 31/12/2026 por empresa (importando a última EFD), porque ele compensa com a CBS (NT 011/2026, *cópia*). Posição: se o Fred quiser a conferência mesmo assim, limitar a "receita escriturada × 0,65% e 3%, menos monofásico e alíquota zero, com ICMS fora da base", sem caixa e sem crédito.

**(b) Se faltar tempo: ICMS-TO antes ou virada de 2027 antes?**

**Recomendação: virada de 2027 antes, sem dúvida.** O critério é "quem fica sem cobertura": o ICMS-TO tem o Domínio como oficial até o paralelo; a virada não tem. Em 01/01/2027, sem a DL-089, **todo cliente do Simples perde o pré-DAS e toda NF-e fica sem receita no produto** — e é exatamente o mês em que a regra muda (CBS/IBS no DAS, art. 22 § 2º novo, DEFIS no PGDAS-D), quando o escritório mais precisa de uma segunda conta. Já o ICMS-TO lido sem pressa, com RICMS/TO em fonte oficial, erra menos do que ICMS-TO feito às pressas em dezembro — e um ICMS errado é multa no imposto mais pesado da carteira. A única inversão que aceito: se a leitura oficial das tabelas de 2027 **não estiver disponível** até o fim de outubro, adiantar a fatia (a) do ICMS (próprio, conferência contra a nota) enquanto a virada espera a fonte; não dá para codar tabela que ninguém leu.

---

## Tabela de hipóteses para o Fred

| # | Hipótese | Tipo | Fonte e marca | O que muda se o Fred discordar |
| --- | --- | --- | --- | --- |
| H1 | Classificação em quatro peças; o contador escolhe só a natureza; linhas por tributo não editáveis, divergência só por exceção com trilha | produto | consulta 08/10 item 1; DL-067 dec. 4; *manual* como contraexemplo | se o Fred quiser editar linha de tributo na nota, perde-se a conciliação por regra; alternativa é "exceção com motivo" |
| H2 | Três camadas (global, escritório, empresa), com precedência empresa > escritório > global, e regra global imutável pelo escritório (só derivar) | produto | *manual* (acumulador por empresa, inferência) | se o escritório puder editar a global, o pacote padrão deixa de ser auditável |
| H3 | Mudança de regra ou de natureza em efetivada = estorno + reescrituração com trilha; nunca recálculo silencioso | produto; coerente com CTN art. 144 (*não conferido*) | DL-067 dec. 6; central 653 (*manual*) | — |
| H4 | Critérios de importação do primeiro corte: CFOP, CST/CSOSN, CST PIS, NCM (lista), papel, origem, participante/CRT, finalidade; forma de pagamento adiada | produto | *manual* seção 4; código atual | se houver empresa em regime de caixa em 2026, forma de pagamento entra já |
| H5 | Precedência por especificidade pesada e, em empate, escopo; empate final = conflito na fila | produto | proposta minha | o Fred pode preferir ordem numérica manual; ambas são explícitas |
| H6 | Nunca "acumulador de exceção": fila "a classificar" bloqueia o fechamento (nível "bloqueia" da HI-59) | produto | consulta 08/10 item 1 (d) e item 5 | — |
| H7 | PIS 0,65% e Cofins 3% cumulativos valem para o Presumido nas competências 10, 11 e 12/2026; extintos para fatos geradores a partir de 01/01/2027 | norma | Lei 9.715 art. 8º I (*lido*); Lei 9.718 art. 4º IV (*lido*; caput art. 8º não extraído); Lei 10.833 art. 10 (*lido* parcial); ADCT art. 126 II (*lido*); LC 214 art. 542 (*lido*) | — |
| H8 | Revenda de gasolina, diesel e GLP por varejista e distribuidor tem PIS/Cofins alíquota zero (monofásico) até 12/2026 | norma | MP 2.158-35 art. 42, I (*lido*); etanol: incisos II e III revogados pela Lei 11.727/2008, regra atual *não conferida* | atinge a classificação dos postos; etanol precisa de leitura própria |
| H9 | Res. CGSN 190/2026 existe (04/08/2026, DOU 10/08/2026), efeitos em 01/01/2027: CBS/IBS no DAS, opção semestral pelo regular (set e mar), DEFIS no PGDAS-D jan-mar, novo art. 22 § 2º (1ª faixa nos 2 primeiros meses), segregação de concentrado/ST de IBS-CBS | norma | *cópia* normaslegais; Anexos I a V **não lidos** | — |
| H10 | A regra de RBT12 de início de atividade **muda em 2027** (art. 22 § 2º novo) e exige vigência nova em `rbt12.py` | norma + código | Res. 190 (*cópia*); `rbt12.py` | confirmar no texto oficial antes de codar |
| H11 | Deixar PIS/Cofins no Domínio; guardar só o saldo credor de 31/12/2026 e as marcas de CST na classificação | produto | DL-067 dec. 8; NT 011/2026 (*cópia*) | se o Fred quiser conferência, escopo mínimo descrito em 4(a) |
| H12 | Virada de 2027 antes do ICMS-TO em caso de conflito de agenda | produto | datas *lidas* (ADCT 126; Res. 190 art. 9º) | inverter só se a fonte das tabelas não aparecer até fim de outubro |

## Pendências (o que não li e precisa de fonte antes de virar regra)

| # | Pendência | Onde resolver | Bloqueia |
| --- | --- | --- | --- |
| P1 | Anexos I a V da Res. CGSN 190/2026 (tabelas de repartição 2027-2033 com CBS/IBS) | DOU de 10/08/2026; portal do Simples Nacional (Legislação) | DL-089 |
| P2 | Texto oficial da Res. 190 (a cópia é de terceiro) e da Res. 194/2026 citada no DL-067 | idem | DL-089 |
| P3 | NT 2026.008 da NF-e: `vProd`/`vNF` com IBS/CBS em 2027 | portal da NF-e | receita de NF-e 2027 (`escrituracao_nfe.py:759-779`) |
| P4 | Resolução do Senado com a alíquota de referência da CBS para 2027 | Senado; prevista até 15/12/2026 (*secundário*) | qualquer cálculo de CBS |
| P5 | RICMS/TO: alíquotas, FECOEP, Anexo XXI (ST), DIFAL, códigos de ajuste, vencimento | SEFAZ-TO (`dtri.sefaz.to.gov.br` falhou em 08/10) | DL-092/093 |
| P6 | ICMS monofásico de combustíveis (LC 192/2022 e convênios) e o reflexo no posto do Simples | Planalto; CONFAZ | postos |
| P7 | Lei 9.718 art. 8º caput (Cofins 3%) e Lei 10.833 art. 10, II (Presumido cumulativo) — confirmação literal | Planalto (textos baixados; só falta extrair) | H7 |
| P8 | Regra atual de PIS/Cofins do etanol no varejo (após Lei 11.727/2008) | Planalto | classificação de posto |
| P9 | Tabela 4.3.x do SPED (natureza da receita) e tabela de NCM monofásico oficial | portal do SPED (503 em 08/10) | peça 2, PIS/Cofins |
| P10 | Portaria SEFAZ-TO de vencimento do ICMS (dia 9) e DARE | SEFAZ-TO | calendário |
| P11 | Precedência de importação: pesos (H5) ou ordem manual — decisão do Fred | Fred | DL-087 |
| P12 | Se algum posto da carteira está no Simples (afeta A10 e H8) | Fred | DL-087, DL-089 |

## Fontes consultadas hoje

**Oficiais (Planalto, por curl, 09/10/2026):** [LC 214/2025](https://www.planalto.gov.br/ccivil_03/leis/lcp/Lcp214.htm) · [EC 132/2023](https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm) · [Lei 9.715/1998](https://www.planalto.gov.br/ccivil_03/leis/L9715.htm) · [Lei 9.718/1998](https://www.planalto.gov.br/ccivil_03/leis/L9718.htm) · [MP 2.158-35/2001](https://www.planalto.gov.br/ccivil_03/mpv/2158-35.htm) · [Lei 10.833/2003](https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833.htm).

**Cópia:** [Res. CGSN 190/2026 — normaslegais](https://www.normaslegais.com.br/legislacao/Resolucao-cgsn-190-2026.htm).

**Secundárias (busca de hoje, só para localizar a norma):** [APET](https://apet.org.br/noticia/nova-resolucao-regulamenta-entrada-de-ibs-e-cbs-no-simples-nacional/) · [IOB](https://noticias.iob.com.br/?p=90121) · [NetCPA](https://netcpa.com.br/colunas/cgsn-atualiza-regras-do-simples-nacional-para-adequacao-a-reforma-tributaria/28174) · [Sinduscon-PR](https://sindusconpr.com.br/simples-nacional-cgsn-atualiza-regras-para-ibs-e-cbs-nfs-e-nacional-e-partilha-da-arrecadacao-11-08-2026/) · [NotaGateway](https://notagateway.com.br/blog/o-que-muda-para-o-simples-nacional-com-a-resolucao-cgsn-no-190-2026/) · [AmdJus](https://amdjus.com.br/ressarcimento-de-ibs-e-cbs-simples-nacional-nao-retorna-ao-das/).

**Repositório (caminhos absolutos):** `/home/user/DataLedger/docs/projeto/pesquisa-acumuladores-2026-10-09.md` · `/home/user/DataLedger/docs/projeto/revisao-do-fiscal-2026-10-09.md` · `/home/user/DataLedger/docs/projeto/consultas/2026-10-08-contador-senior-fiscal.md` · `/home/user/DataLedger/docs/planos/DL-067-plano-do-modulo-fiscal.md` (linhas 190-204, 425-510) · `/home/user/DataLedger/docs/planos/DL-085-escrituracao-de-nfe-em-volume.md` · `/home/user/DataLedger/docs/projeto/requisitos.md` (RC-175, linha 123) · `/home/user/DataLedger/apps/fiscal/models.py` (629-680, 896-915, 2639-2832, 3027-3175) · `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py` (166-395, 759-779) · `/home/user/DataLedger/apps/fiscal/escrituracao_nfe_lote.py` (22-39, 352-357) · `/home/user/DataLedger/apps/fiscal/tomadas.py` (430-468) · `/home/user/DataLedger/apps/empresas/models.py` (684-711) · `/home/user/DataLedger/apps/fiscal/presumido_tabelas.py` (46-52).

**Não alcançado hoje:** portal do Simples Nacional (texto da Res. 190), `normas.receita.fazenda.gov.br` (JS), Anexos da Res. 190, NT 2026.008, RICMS/TO, resolução do Senado da CBS.
