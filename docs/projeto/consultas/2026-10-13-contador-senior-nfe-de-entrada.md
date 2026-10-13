# Consulta ao contador-senior sobre a NF-e de entrada (DL-091) — 13/10/2026

**Legislação validada até:** 13/10/2026 **só para a legislação federal** lida hoje no Planalto (LC 87/1996, LC 123/2006, LC 192/2022). **A legislação do Tocantins não foi validada hoje:** o sítio da SEFAZ-TO (`dtri.sefaz.to.gov.br`) não respondeu (falha de DNS no `WebFetch`; proxy devolveu 502 no `curl`), e o portal do STF devolveu 403. Onde isso pesa, o texto diz "pendência". · **Carteira de referência:** Palmas/TO; Simples e Presumido; comércio, posto de combustível (posto, distribuidora e TRR), indústria pequena; NFC-e em alto volume (RC-173). · **Grau de segurança geral:** alto nas decisões de produto e nas normas marcadas *lido*; médio onde só há *manual* ou *cópia*; baixo em tudo o que depende do RICMS-TO.

**Marcas.** *lido* = texto oficial lido hoje (Planalto, por `curl`). *cópia* = cópia íntegra em sítio de terceiro (hoje: consolidação da Lei 1.287/2001 **até 2013**, impressa da página da SEFAZ em 2015 e arquivada em sítio da OCDE; serve só para dizer **onde** a regra mora, nunca o que ela diz hoje). *secundário* = resultado de busca ou notícia. *não conferido* = conhecimento meu, sem leitura hoje. *manual* = Domínio Escrita Fiscal 10.1A-12 (2018), cópia local do scratchpad, página do PDF; **rotina, nunca norma**, reescrita com palavras minhas. *código* = arquivo e linha do repositório, lido hoje.

**O que li hoje.** Repositório: DL-067 (seções "Escrituração", "ICMS-TO e EFD ICMS/IPI", "Pendências e fontes", "Execução autônoma"), `revisao-do-fiscal-2026-10-09.md`, `pesquisa-acumuladores-2026-10-09.md`, `fontes-de-referencia.md`, as consultas de 09/10 (classificação fiscal) e 12/10 (DL-087), `requisitos.md` (PE-86 a PE-92, RC-164 a RC-178, HI-109 a HI-153), **`docs/projeto/mapa-nfe-de-entrada-2026-10-13.md`** (commit `fd466a2`, de hoje), `apps/fiscal/escrituracao_nfe.py:1-460`, `apps/fiscal/models.py:3085-3345` e `3711-3970`, `apps/fiscal/tomadas.py:1-120` e `400-490`, `apps/fiscal/cfop.py` inteiro, `apps/fiscal/dados/cfop_it2023002_v210.csv` (códigos citados abaixo), assinaturas de `apps/fiscal/classificacao.py`. Normas: LC 87, arts. 20, 23 e 33; LC 123, art. 13, § 1º, XIII (alíneas a a h), §§ 5º e 6º, e art. 23 (caput e §§ 1º a 5º); LC 192, arts. 1º a 6º. Manual: p. 462-463, 489-492, 499-500, 506, 1051-1052, 1559-1560, 1639.

Tudo abaixo é **hipótese para validação do Fred** (HI-54; RC-164, RC-170 e RC-178: decisão delegada, reversível).

---

## 1. O que o escritório precisa primeiro das notas de entrada

**Resposta curta.** A ordem por valor e risco para esta carteira é **(a) escrituração das entradas com natureza e conferência recebidas × escrituradas** → **(d) e (c) juntos, como memória** (o que a nota destaca de ICMS próprio, ST retido e crédito do fornecedor do Simples, sem apurar) → **(e) aviso de compra interestadual do Simples** → **(b) livro de entradas** → **(g) integração contábil** → **(f) PIS/Cofins na entrada, que para esta carteira é quase irrelevante**. O **corte 1** entrega (a) por inteiro, (c) e (d) como linhas de memória por item com a marca "dá crédito / não dá / limitado / vedado", e (e) como aviso. Nada de cálculo estadual, nada de livro oficial, nada de lançamento contábil.

### Fundamento

- **Por que (a) primeiro.** A rotina mais cara do escritório é importar e conferir (RC-40, RC-41), e hoje a compra chega, fica na lista de recebidas como "Fora da escrituração" e não aparece na lista "a escriturar" (*código* `escrituracao_nfe.py:211-230`; mapa de hoje, §2). Sem a entrada classificada, nenhuma das outras seis letras existe: crédito, ST, DIFAL, livro, custo e PIS/Cofins são **atributos da natureza de entrada**, e a conferência recebidas × escrituradas é o que fecha o mês do comércio (no manual, "Notas não lançadas" só cobre saídas e serviços, p. 1639 — *manual*; o produto pode fazer melhor).
- **Presumido é ICMS "normal" no TO? Sim.** Presumido é regime federal (IRPJ/CSLL). Para o ICMS, quem não é optante do Simples apura por débito e crédito (LC 87, art. 20: direito de creditar-se do imposto "anteriormente cobrado" nas entradas — *lido*; a não cumulatividade do art. 19 é *não conferida* hoje, texto estável). O optante do Simples **não** se apropria nem transfere crédito (LC 123, art. 23, caput — *lido*). Logo o comércio do Presumido em Palmas tem CRT 3 e apura ICMS no TO, salvo regime especial (TARE, crédito presumido da Lei 1.201/2000 citada no DL-067 — *não conferido*; ver pergunta ao Fred H12).
- **Por que (d) é o maior risco e ainda assim não é cálculo.** No TO a cobrança que pega o comércio pequeno na entrada é a antecipação e o ST, e a Lei 1.287/2001 remete os dois ao regulamento ("pode ser exigido o recolhimento antecipado do imposto nas condições e prazos previstos em regulamento", art. 28-A, redação da Lei 1.754/2006 — *cópia* de 2013). O RICMS-TO não foi lido hoje. **Calcular sem ler é o erro que o projeto proíbe** (HI-54).
- **Por que (e) vale cedo.** Para o optante do Simples, a LC 123 põe fora do DAS o ICMS da antecipação com e sem encerramento (art. 13, § 1º, XIII, "g", itens 1 e 2) e o diferencial de alíquota nas demais aquisições interestaduais (alínea "h"), calculado com as alíquotas de não optantes (§ 5º) — *lido*. Esse é um fato que o XML já permite detectar (UF do emitente diferente de TO, ou `idDest` 2) e que o escritório precisa ver **no mês**, porque a guia é mensal. O produto não calcula: aponta.
- **Por que (f) fica por último.** Presumido está no cumulativo e **não tem crédito** de PIS/Cofins (Lei 10.833, art. 10, e Lei 10.637, art. 8º — *lidos parcialmente em 09/10/2026, não relidos hoje*); o Simples não tem crédito (LC 123, art. 23 — *lido*); e PIS/Cofins acabam em 01/01/2027 (HI-143). Só o Lucro Real teria crédito, e o Real está fora da paridade por falta de cliente. Para esta carteira, basta **guardar** CST e valor por item (já guardados: `ItemNFe.cst_pis`, `v_pis`, `cst_cofins`, `v_cofins`, *código* `models.py:3833-3840`).
- **Por que (g) depende de outra etapa.** A origem `escrita_fiscal` existe no lançamento contábil e nada a grava (mapa, §5); a prévia e os papéis de conta são a DL-094. O corte 1 deve só **gravar na natureza o efeito contábil** (estoque, custo, despesa, imobilizado), para a DL-094 mapear.

### Proposta para o produto

Ordem (a) → (d)+(c) memória → (e) aviso → (b) → (g) → (f). Corte 1: (a) completo; (c) e (d) como memória não editável; (e) como aviso nomeado; relatório de conferência de entradas na classe "conferência" (sem impressão oficial). Detalhe do corte na lista final.

### Grau de segurança

Alto na ordem e no "nada de cálculo estadual". Alto em "Presumido apura ICMS normal". Médio em (b) depois de (e): se o Fred entregar o Livro de Entradas de muitos clientes a partir do produto, o livro sobe.

---

## 2. Naturezas de entrada: catálogo mínimo e conversão de CFOP

**Resposta curta.** Onze naturezas de entrada **por item**, mais a devolução de venda que já existe e uma natureza nova de saída (`devolucao_compra`, pergunta 4). Cada natureza carrega quatro efeitos: **estoque/custo**, **crédito de ICMS no regime normal**, **ST/antecipação (marca)** e **DIFAL possível (marca)**; nenhuma compõe receita. A conversão do CFOP do emitente para o de entrada **não é regra fixa nem tabela mecânica: o primeiro dígito é fixo (5→1, 6→2, 7→3) e o grupo é escolha do destinatário, porque depende da destinação que só ele conhece** (5.102 do fornecedor vira 1.102, 1.556 ou 1.551 conforme a compra seja para revenda, consumo ou ativo). Logo, o CFOP de entrada **decorre da natureza escolhida**, e o produto sugere o par (natureza, CFOP de entrada) a partir do CFOP do emitente, do CST/CSOSN e do NCM. O manual confirma que no sistema de referência isso é **tabela mantida pelo contador**, não automatismo.

### Fundamento

- **ROTINA (manual).** A configuração de importação de entradas tem uma guia que "relaciona os CFOPs de saída para determinar o CFOP da nota de entrada", com um CFOP de entrada por linha e vários CFOPs de saída vinculados a ele (p. 506; a mesma guia, no sentido inverso, para a NF-e do portal, p. 462-463). Há opção para "permitir relacionar o mesmo CFOP de saída com mais de um CFOP de entrada" e outra para importar "conforme o CFOP do cadastro de produtos" (p. 490) — isto é, o próprio sistema de referência admite que o mesmo 5.102 vire mais de um CFOP de entrada e oferece o produto como critério alternativo. A central lista "nota de entrada traz CFOP de saída sem conversão" como causa de erro de importação (central 121, via pesquisa dos acumuladores, seção 4). O acumulador restringe-se a um tipo de movimento, entrada inclusive (p. 375), e lista os CFOPs permitidos (p. 405-407). Há ainda a opção "importar o valor do crédito do ICMS nos termos do art. 23 da LC 123" para notas de entrada de fornecedor do Simples (p. 492).
- **NORMA.** O CFOP é do Convênio s/nº de 15/12/1970 (*não conferido* hoje); a tabela do produto é a de apoio do Informe 2023.002 v2.10, com a ressalva registrada em `cfop.py:13-15` de que o Convênio prevalece. A estrutura por primeiro dígito (1 interna, 2 interestadual, 3 exterior) é estável e visível nas descrições do próprio CSV. O crédito do regime normal e suas vedações: LC 87, art. 20, caput e §§ 1º a 3º e 5º (*lido*). Uso e consumo sem crédito até 31/12/2032: LC 87, art. 33, I, redação da LC 171/2019 (*lido*). Crédito de fornecedor do Simples limitado ao ICMS informado na nota: LC 123, art. 23, §§ 1º e 2º; não se aplica nos quatro casos do § 4º (valores fixos, alíquota não informada, isenção estadual da faixa, remetente no regime de caixa) — *lido*. Combustíveis da LC 192: pergunta 5.
- **CÓDIGO.** `ItemNFe.cfop` guarda o CFOP do emitente, sem campo de entrada (mapa, §1; `itens_nfe.py:339`). A tabela de CFOP tem 131 códigos 1.xxx, 125 códigos 2.xxx e 32 códigos 3.xxx (mapa, §4), e as descrições abaixo foram conferidas no CSV hoje. O catálogo atual só tem saída, devolução de venda e ajuste (`models.py:3091-3113`). A sugestão e a classificação assumem papel EMITENTE (`escrituracao_nfe.py:397-398`; `classificacao.py:385`, pelo mapa).

### Catálogo proposto (CFOPs típicos conferidos no CSV de `apps/fiscal/dados/`)

| Cód. | Natureza de entrada | CFOP de entrada típico (1/2/3.xxx) | Estoque / custo | Crédito de ICMS (regime normal) | Marcas |
| --- | --- | --- | --- | --- | --- |
| E1 | Compra para comercialização | 1.102, 2.102, 3.102; variantes 1.113, 1.117, 1.121 | Estoque, sim | **Sim**, o destacado (LC 87, art. 20); de fornecedor CRT 1/2: **limitado ao `vCredICMSSN`** (LC 123, art. 23, §§ 1º-2º) ou **nenhum** (§ 4º) | DIFAL: não (revenda) |
| E2 | Compra para industrialização ou insumo | 1.101, 2.101, 3.101; 1.111, 1.116, 1.120, 1.122; 1.124-1.125 (industrialização por terceiro) | Estoque/custo, sim | Sim, como E1; vedado se a saída do produto for isenta/não tributada (art. 20, § 3º, I) | — |
| E3 | Compra com ICMS-ST (substituído) | 1.403, 2.403 (revenda); 1.401, 2.401 (indústria) | Estoque, sim; **o ST retido compõe o custo** | **Não** sobre o próprio nem sobre o retido (regra do regime; exceções do TO *não conferidas*) | ST retido: memória |
| E4 | Compra para uso ou consumo | 1.556, 2.556, 3.556; 1.407, 2.407 (ST) | Despesa | **Vedado até 31/12/2032** (LC 87, art. 33, I) | DIFAL possível se interestadual |
| E5 | Compra para o ativo imobilizado | 1.551, 2.551, 3.551; 1.406, 2.406 (ST) | Imobilizado (Patrimônio) | **1/48 por mês, CIAP** (art. 20, § 5º) — **fora do corte 1**, só marca | DIFAL possível se interestadual |
| E6 | Compra de combustível ou lubrificante para revenda | 1.652, 2.652 | Estoque, sim | Gasolina, diesel, GLP, etanol anidro: **monofásico, sem crédito** (LC 192, art. 2º); etanol hidratado e lubrificante: **a conferir** (ST/regime do TO) | ver pergunta 5 |
| E7 | Combustível ou lubrificante para consumo próprio | 1.653, 2.653 | Despesa | Não (monofásico ou uso/consumo) | — |
| E8 | Transferência recebida de estabelecimento da mesma empresa | 1.151, 1.152, 2.151, 2.152 | Estoque, sim | Sim, o destacado | Depende do vínculo de entrada da filial (HI-111; mapa, lacuna 6) |
| E9 | Bonificação, doação, brinde ou amostra recebida | 1.910, 1.911, 2.910, 2.911 | Estoque, sim, **sem custo de aquisição** (contabilização na DL-094) | Só se destacado e tributado; aviso | Receita no Presumido: **pendência** (P9) |
| E10 | Remessa, retorno, consignação, demonstração, conserto, industrialização por encomenda | 1.901-1.903, 1.912-1.913, 1.915-1.917, 1.920-1.926; 1.949 só com confirmação | Não entra no estoque próprio (ou retorna a ele) | Normalmente sem destaque; se houver, aviso | — |
| E11 | Compra para prestação de serviço e aquisição de serviço em NF-e | 1.126, 1.128, 1.933 | Custo do serviço | 1.126: a confirmar; 1.128/1.933: não | Sem sugestão automática |
| — | Devolução de venda recebida (já existe, DL-081) | 1.201, 1.202, 1.660-1.662 | Retorna ao estoque | Crédito do débito original: **etapa do ICMS** | Deduz receita (HI-121) |
| — | **A classificar** | — | — | — | Fila da DL-087; nunca padrão silencioso |

Regra transversal: **nenhuma natureza de entrada compõe receita bruta**, no Simples nem no Presumido; a tabela de `papel` recebe o valor `nao_receita` em todas.

### Conversão do CFOP do emitente

1. **Primeiro dígito, regra do produto:** 5→1, 6→2, 7→3 (estrutura do CFOP; *não conferido* no Convênio, estável). Divergência entre `idDest`/UF do emitente e o primeiro dígito do CFOP do emitente é aviso ("CFOP interestadual em nota com UF igual à da empresa").
2. **Grupo e subgrupo, pela natureza:** E1+emitente 5.102/5.405 → 1.102/1.403; E4+5.102 → 1.556; E5+5.102 → 1.551; E6+5.655/5.656 → 1.652; E7+5.656 → 1.653; E8+5.152 → 1.152; E9+5.910 → 1.910. Se o emitente usa CFOP de ST (x.401 a x.405) ou CST 10/30/60/70 ou CSOSN 201/202/203/500, a variante ST (1.403, 1.401, 1.406, 1.407) é sugerida; sem esses sinais, a comum.
3. **Quem decide é o contador:** a sugestão nunca grava (mesmo desenho de `NaturezaItemNFe`); `1.949` só por escolha manual; CFOP de entrada fora da tabela oficial é recusado.
4. **Dois campos no item:** `cfop` (do emitente, imutável) e `cfop_entrada` (do destinatário, confirmado). Nunca sobrescrever o do XML.
5. **Regra do escritório (DL-087):** as regras de classificação ganham `tipo` = entrada e critérios de **CRT do emitente** e **UF do emitente** (HI-142 já os previa); a conversão específica de um fornecedor vira regra de empresa.

### Grau de segurança

Alto no catálogo e nos efeitos federais (*lidos*). Alto em "conversão por natureza, não por tabela mecânica" (manual e estrutura do CFOP concordam). Médio no detalhe das variantes ST (depende de CST que o fornecedor declara). Baixo em qualquer exceção estadual de crédito (TO não lido).

---

## 3. ICMS no Tocantins para o corte 1: calcular ou só memória

**Resposta curta.** **Nada de ICMS estadual é seguro para CALCULAR hoje**, porque o RICMS-TO e a Lei 1.287/2001 vigentes não foram lidos (a cópia que alcancei para até 2013 e traz alíquota de 17%, já superada segundo o DL-067). O que **é** seguro, com norma federal lida: (i) registrar o **crédito destacado elegível** como memória por item, com a marca que vem de LC 87 e LC 123; (ii) marcar **ICMS-ST retido** como "sem crédito, compõe o custo"; (iii) marcar **compra interestadual de optante do Simples** com o aviso da LC 123, art. 13, § 1º, XIII, "g" e "h"; (iv) marcar combustível da LC 192 como "monofásico, sem crédito nem débito". Antecipação parcial/total do TO e DIFAL do regime normal ficam como **aviso sem valor**.

### Fundamento

- **Crédito destacado (memória).** Direito ao crédito do imposto anteriormente cobrado nas entradas, inclusive uso/consumo e ativo (LC 87, art. 20, caput — *lido*), condicionado à idoneidade do documento e à escrituração nos prazos (art. 23 — *lido*), extinto em cinco anos da emissão (art. 23, parágrafo único — *lido*). Vedações federais: isentas/não tributadas e alheias à atividade (art. 20, § 1º; veículos de transporte pessoal presumem-se alheios, § 2º); saída subsequente não tributada (§ 3º) — *lidos*. Uso e consumo só a partir de 01/01/2033 (art. 33, I — *lido*). Ativo 1/48 com coeficiente de saídas tributadas (art. 20, § 5º — *lido*). A **alíquota** não interessa à memória: o produto só repete `vBC`, `pICMS`, `vICMS`, CST/CSOSN que o emitente destacou (`models.py:3759-3773`).
- **Fornecedor do Simples.** Crédito igual ao informado no documento e limitado ao ICMS devido pela optante (LC 123, art. 23, §§ 1º e 2º — *lido*); a nota traz `pCredSN` e `vCredICMSSN`, já lidos (`models.py:3806-3815`). Quatro exclusões do § 4º (*lido*). O manual tem a opção equivalente para notas de entrada (p. 492 — *manual*).
- **ICMS-ST retido.** Para o optante, o ICMS de operações sujeitas a ST e à antecipação com encerramento fica fora do DAS (LC 123, art. 13, § 1º, XIII, "a" — *lido*). Para o regime normal, o substituído não se credita do retido (Convênio ICMS 142/2018 — *não conferido* hoje; prática consolidada). Memória: `vBCSTRet` e `vICMSSTRet` (`models.py:3800-3805`).
- **Antecipação e DIFAL do Simples.** Alínea "g": antecipação nas aquisições interestaduais, com encerramento (item 1) ou sem encerramento, "hipótese em que será cobrada a diferença entre a alíquota interna e a interestadual, sendo vedada a agregação de qualquer valor" (item 2); alínea "h": diferença de alíquota nas demais aquisições interestaduais; § 5º: alíquotas de não optantes; § 6º, II: o CGSN pode disciplinar a antecipação — todos *lidos*. **Jurisprudência (*secundário*, busca de hoje; portal do STF 403):** o Tema 517 (RE 970.821, maio/2021) declarou constitucional a cobrança do DIFAL de optante do Simples; o Tema 1284 (ARE 1.460.254, nov/2023) exige **lei estadual em sentido estrito** para a cobrança. Se o TO tem lei nesse sentido e qual é a sua redação vigente: **não lido**. A Lei 1.287/2001 (*cópia* de 2013) menciona "antecipação parcial e pagamento do imposto em valor equivalente à diferença da alíquota interestadual de origem e a interna" como medida sancionatória do art. 51, e o art. 28-A remete ao regulamento — isso só mostra onde procurar.
- **O que não leio hoje e por isso não calcula:** alíquota interna (DL-067 cita 20% desde 2024 pela Lei 4.141/2023 e FECOEP da Lei 3.019/2015 — *secundário* no DL-067, não lido por mim), MVA e Anexo XXI do RICMS-TO, antecipação parcial e total, benefícios (`cBenef`), códigos de ajuste, vencimento (Portaria 61/2026, *secundário*).

### Proposta para o produto

| Fato no item | Marca gravada (memória, não editável) | Base |
| --- | --- | --- |
| CST 00/10/20/70 ou CSOSN 101/201 com `vICMS` > 0 e natureza E1/E2/E8 | "crédito destacado elegível: R$ x" | LC 87, art. 20 |
| Idem, emitente CRT 1 ou 2 | "crédito limitado ao informado: `vCredICMSSN`" ou "sem crédito (art. 23, § 4º)" quando `pCredSN` ausente | LC 123, art. 23 |
| Natureza E4 | "crédito vedado até 31/12/2032" | LC 87, art. 33, I |
| Natureza E5 | "crédito 1/48 (CIAP) — etapa do ICMS" | LC 87, art. 20, § 5º |
| CST 60 / CSOSN 500, ou `vICMSSTRet` > 0 | "ICMS-ST retido: sem crédito; compõe o custo" | regra do regime (TO *não conferido*) |
| CST 40/41/50/51/60/90 em natureza com crédito | aviso "CST sem direito a crédito pleno: conferir" | LC 87, art. 20, § 1º |
| NCM de combustível da LC 192 (gasolina, diesel, GLP, etanol anidro) | "ICMS monofásico: sem crédito nem débito" | LC 192, arts. 2º e 4º |
| UF do emitente ≠ UF da empresa (ou `idDest` 2) e empresa do Simples na data | **aviso** "possível antecipação ou DIFAL do Simples (LC 123, art. 13, § 1º, XIII, g e h): regra do TO não lida" | LC 123 |
| UF do emitente ≠ UF da empresa e natureza E4/E5 em regime normal | **aviso** "possível DIFAL de uso, consumo ou ativo: regra do TO não lida" | CF art. 155, § 2º, VII e VIII (*não conferido*) |

Totais do mês, por empresa, só como conferência: soma de "crédito destacado elegível", soma de "ST retido", lista de notas com aviso interestadual. **Nenhuma linha de apuração, nenhuma guia, nenhuma alíquota do TO em código.**

### Grau de segurança

Alto nas marcas federais. Médio no "ST retido sem crédito" para regime normal (prática, Convênio não lido). Baixo em tudo o que é TO: pendência P1, P2, P3.

---

## 4. Devolução de compra e devolução de venda

**Resposta curta.** São operações **simétricas em sentidos opostos**, e o produto já trata uma delas. A **devolução de venda** (recebida de terceiro com `finNFe` 4, ou nota própria de entrada `tpNF` 0 + `finNFe` 4) é **entrada que deduz receita** (DL-081, HI-121, HI-140) e aparecerá no futuro livro de entradas como 1.201/1.202 — ela **não** deve ganhar segunda escrituração como "compra". A **devolução de compra** é **saída própria** (`tpNF` 1, `finNFe` 1, CFOP com `indDevol` 1: 5.201, 5.202, 5.208-5.210, 5.410-5.413, 5.553, 5.555, 5.556, 5.660-5.662, 5.918, 5.919, 5.921 e os 6.xxx correspondentes, conferidos no CSV) que **anula uma entrada**: não é receita, sai do estoque e, no regime normal, **estorna o crédito tomado** (via débito na saída, pela base e alíquota da entrada — mecânica estadual, *não conferido*). No corte 1 ela ganha natureza própria `devolucao_compra`, papel `nao_receita`; o vínculo item a item com a compra original fica para quando o leitor ler `NFref`.

### Fundamento

- **CÓDIGO.** Hoje a saída com `indDevol` 1 recebe "sem sugestão: devolução de compra em saída, fora do catálogo" (`escrituracao_nfe.py:418-420`) e, sem natureza, **não efetiva** — recusa correta por omissão. A devolução de venda usa `indDevol`, não a faixa (`escrituracao_nfe.py:407-411`; `cfop.py:17-19`). A nota de terceiro com `tpNF` 0 em que a empresa é destinatária está "a conferir" (`api_nfe.py:76-77`, pelo mapa). `NFref` e `infAdProd` não são lidos (mapa, lacuna 4). A unicidade "escrituração ativa única por vínculo" (`_NOME_RESTRICAO_UNICA`, `escrituracao_nfe.py:117`) já impede que a mesma devolução de venda vire também "entrada".
- **NORMA.** Devolução de venda deduz receita no mês da devolução (Res. CGSN 140, art. 17 — *cópia*, HI-121; Lei 9.430, art. 25, I, no Presumido — *lido* em 09/10). Devolução de compra não é receita de nenhum regime (decorre do conceito de receita bruta; *não conferido* hoje). O estorno do crédito na devolução de compra é tratado pela legislação estadual (*não conferido*).
- **ROTINA (manual).** O acumulador tem marcador "devolução" e contas próprias de devolução por imposto (p. 367, 385-386 — *manual*), isto é, o sistema de referência separa a devolução da operação comum nos dois sentidos.

### Proposta para o produto

- Natureza nova de **saída** `devolucao_compra` (papel `nao_receita`, mercado interno, sem anexo, sem atividade do Presumido), sugerida quando `tpNF` 1, `finNFe` 1 e CFOP com `indDevol` 1 cuja descrição comece por "Devolução de compra", "Devolução de mercadoria recebida em transferência", "Devolução de bem do ativo", "Devolução de mercadoria destinada para uso ou consumo" ou "Devolução de embalagens"; aviso fixo "estorno do crédito de ICMS: etapa do ICMS".
- Separar `devolucao_compra` de `devolucao_venda` também no **segmento** do Simples: a devolução de compra **não** entra no saldo de devolução do art. 17 (HI-129/HI-130).
- **Recusar por enquanto, com nome:** (i) nota de terceiro com `tpNF` 0 em que a empresa é destinatária e `finNFe` ≠ 4 ("entrada emitida por terceiro: confirmar o fato antes de escriturar"); (ii) devolução de compra com `finNFe` 4 em saída própria (contradição: `finNFe` 4 é devolução de venda); (iii) NFC-e (modelo 65) em que a empresa é destinatária ("NFC-e como compra: confirmar"); (iv) qualquer tentativa de escriturar a mesma nota como devolução de venda e como entrada (a restrição do banco já cobre).
- Quando `NFref` for lido (nova versão do leitor): vincular a devolução de compra à compra escriturada e avisar "devolução sem compra escriturada" ou "quantidade devolvida maior que a comprada".

### Grau de segurança

Alto na separação e nas recusas. Médio no estorno de crédito (mecânica estadual); por isso só aviso.

---

## 5. Posto de combustível: o que muda na entrada e o que fazer

**Resposta curta.** Na compra de **gasolina, diesel, GLP e etanol anidro** o posto **não é contribuinte do ICMS**: a LC 192/2022 faz o imposto incidir **uma única vez**, com contribuinte o produtor ou importador e fato gerador na saída dele (arts. 2º, 4º e 5º — *lidos*; a LC 227/2026 acrescentou "correntes" aos incisos I e II — *lido*). Logo: **sem crédito, sem débito, o ICMS pago na origem compõe o custo**. **Etanol hidratado e lubrificantes não estão na LC 192** (art. 2º lista só anidro) e seguem o regime do TO (ST ou normal — *não conferido*). PIS/Cofins: revenda de gasolina, diesel e GLP com alíquota zero no varejo (MP 2.158-35, art. 42, I — *lido em 09/10/2026*), e o Presumido não tem crédito de qualquer forma. A **loja de conveniência** é comércio comum com muita ST (bebidas, cigarros, higiene: natureza E3). No corte 1, o posto recebe E6/E7 com a marca "monofásico" por NCM, e a conveniência recebe E1/E3 com o mesmo lote da DL-085.

### Fundamento

- **NORMA.** LC 192, art. 1º (incidência única), art. 2º (gasolina e correntes, etanol anidro, diesel e correntes, biodiesel, GLP), art. 3º, II (imposto cabe ao Estado de consumo para derivados de petróleo), art. 3º, V, b (alíquota ad rem), art. 4º (contribuinte: produtor e importador), art. 5º (fato gerador na saída do produtor) — *lidos*. LC 123, art. 13, § 1º, XIII, "a": monofásico de combustíveis fora do DAS (*lido*; HI-132 já o registra). Alíquotas ad rem dos convênios do CONFAZ e regime do etanol hidratado: *não conferidos*.
- **CÓDIGO.** As listas de NCM de combustível e lubrificante existem (`ncm_combustivel.py`, usadas em `escrituracao_nfe.py:107-112, 150, 329-338`). Os grupos **ICMS monofásico do XML (ICMS02, 15, 53, 61) não são lidos** (mapa, lacuna 4); hoje `cst` ficaria vazio ou o item poderia cair como ilegível, o que precisa de verificação na implementação. CFOPs 1.652 e 1.653 conferidos no CSV.
- **ROTINA.** O posto compra poucas NF-e de combustível (dezenas por mês) e muitas de conveniência; a escrituração em volume (DL-085) foi medida para saídas, e a prévia por grupo (CFOP, CST/CSOSN, natureza) serve igualmente às entradas.

### Proposta para o produto

- Natureza E6 sugerida por **CFOP do emitente de combustível** (5.655/5.656 ou 6.xxx correspondentes) **e NCM da lista positiva**, exigindo NCM como já se exige para a venda (HI-139; consulta de 12/10, H2). Lubrificante → E1 ou E3 com aviso "lubrificante: não é monofásico da LC 192"; etanol hidratado → E6 com aviso "regime do etanol hidratado no TO não lido".
- Leitor de itens: **nova versão** que leia os grupos ICMS monofásico (`qBCMono`, `adRemICMS`, `vICMSMono`, `vICMSMonoRet`), guardando-os como memória; sem isso o posto fica com `cst` vazio nas compras.
- Nenhum cálculo de ICMS, PIS ou Cofins na entrada do posto. Nenhum efeito no pré-DAS: a HI-132 continua (posto no Simples ainda é fato da carteira, PE-91).
- Conveniência: E3 por CST 60 / CSOSN 500 / CFOP 5.405 do fornecedor; "ST retido compõe o custo" como memória.

### Grau de segurança

Alto no monofásico da LC 192 (*lido*). Médio na leitura dos grupos ICMS do XML (depende de implementação). Baixo em etanol hidratado e lubrificante (TO não lido).

---

## 6. O que fica fora do corte 1 e o que precisa do Fred

**Resposta curta.** Fora do corte 1, como pendência nomeada: toda **apuração** de ICMS (próprio, ST, antecipação, DIFAL, FECOEP, CIAP), **livro de entradas**, **integração contábil**, **cadastro de participantes e produtos**, **CT-e e NFCom**, **NFref**, **SPED Fiscal de entrada (RC-44)**, **estoque e inventário**, **PIS/Cofins não cumulativo**, **regime de caixa**. Do Fred, cinco fatos da carteira e duas decisões de produto (tabela adiante).

### Fora do corte 1 (vira pendência com nome)

| # | Fora | Por quê | Para onde |
| --- | --- | --- | --- |
| F1 | Apuração do ICMS próprio (débito × crédito, saldo credor) | RICMS-TO e alíquotas não lidos | DL-092 |
| F2 | ST, antecipação parcial e total, MVA, FECOEP | Anexo XXI e decretos de 2026 não lidos | DL-093 |
| F3 | DIFAL (Simples e regime normal) com valor | Lei estadual em sentido estrito a localizar (Tema 1284, *secundário*) | DL-093 |
| F4 | CIAP e crédito do ativo | Depende do Patrimônio | DL-092/Patrimônio |
| F5 | Livro Registro de Entradas | Classe "livro" da personalização; forma do Convênio s/nº de 1970 não lida | DL-095 |
| F6 | Lançamento contábil da compra (estoque, custo, despesa, imobilizado, ICMS a recuperar) | DL-094; origem `escrita_fiscal` reservada e não gravada | DL-094 |
| F7 | Cadastro de fornecedor com atributos com vigência e cadastro de produto | B1 da revisão; CRT do emitente já basta no corte 1 | B1 |
| F8 | CT-e, NFCom, energia (frete e crédito de transporte) | leitor recusa o namespace | B9 |
| F9 | `NFref`, `infAdProd`, `pRedBC`, `pMVAST`, partilha completa, IE/UF do destinatário | nova versão do leitor | DL-091 frente técnica, se couber; senão DL-092 |
| F10 | Importação de SPED Fiscal de entradas (RC-44) e formato de intercâmbio (PE-18) | decisão pendente | — |
| F11 | PIS/Cofins não cumulativo (crédito) | sem cliente do Real | — |
| F12 | Parcelas, regime de caixa | bloqueado (`receita.py:1307`) | B10 |

### Para o Fred (fato da carteira ou decisão de produto)

| # | Pergunta | O que muda |
| --- | --- | --- |
| Q1 | **Competência da entrada:** o escritório escritura pela **data de entrada** (como o manual, p. 1051-1052: "tomará em conta a data de entrada e não a data de emissão") ou pela **data de emissão**? Proposta padrão: campo "data de entrada" obrigatório, sugerido igual ao `dhEmi`, competência = mês da data de entrada; nota de mês encerrado segue RC-57/RC-101 (extemporânea no mês aberto). | Define `dia_e_competencia` para entradas e o livro futuro |
| Q2 | Há cliente com **TARE, crédito presumido (Lei 1.201/2000) ou outro regime especial de ICMS** no TO? | Esses regimes costumam exigir estorno de créditos de entrada; a marca "crédito destacado elegível" ficaria errada para eles |
| Q3 | Há **posto no Simples**? (PE-91, repetida) | Pré-DAS do combustível; não a classificação |
| Q4 | Há cliente que precise de **CIAP** já (indústria pequena com máquinas)? | Antecipa F4 |
| Q5 | Escriturar entradas **também dos clientes do Simples** no corte 1? Recomendo **sim**: o valor para eles é o aviso de compra interestadual (DIFAL/antecipação), que é mensal. | Escopo do corte 1 |
| Q6 | **Bonificação recebida em mercadoria** (E9): o escritório a trata como receita no Presumido? | Pendência P9; só memória no corte 1 |
| Q7 | As **7 NF-e de entrada do acervo** são todas devolução de venda (RC-173, item 4)? Se alguma for compra, serve de caso real de teste. | Dados de teste |

---

## Hipóteses para o Fred validar

| # | Hipótese | Tipo | Fonte e marca | O que muda se discordar |
| --- | --- | --- | --- | --- |
| H1 | Ordem de valor: escrituração com natureza e conferência → memória de crédito/ST → aviso interestadual do Simples → livro → contábil → PIS/Cofins | produto | RC-40; LC 87, art. 20 (*lido*); LC 123, art. 13 e 23 (*lidos*); manual p. 1639 | Se o Fred quiser o livro já, F5 sobe e a DL-095 funde com a DL-091 |
| H2 | Presumido apura ICMS normal (CRT 3) no TO, salvo regime especial | norma + fato | LC 87, art. 20; LC 123, art. 23 (*lidos*); regime especial *não conferido* | Q2 |
| H3 | Catálogo de 11 naturezas de entrada por item, todas `nao_receita`, com quatro efeitos (estoque, crédito, ST, DIFAL) | produto | manual p. 375, 405-407 (*manual*); CSV de CFOP (*código*) | Naturezas a mais ou a menos; não muda o desenho |
| H4 | CFOP de entrada decorre da natureza; primeiro dígito fixo; dois campos no item; sugestão confirmada | produto + estrutura do CFOP | manual p. 462-463, 490, 506 (*manual*); Convênio s/nº 1970 (*não conferido*) | Se preferir tabela mecânica única, perde-se 1.556/1.551 a partir do mesmo 5.102 |
| H5 | Crédito de ICMS só como **memória** com marcas federais; nenhuma apuração nem alíquota do TO em código | produto + norma | LC 87, arts. 20, 23, 33, I (*lidos*); LC 123, art. 23 (*lido*) | — |
| H6 | Fornecedor CRT 1/2: crédito limitado a `vCredICMSSN`; ausência de `pCredSN` = sem crédito | norma | LC 123, art. 23, §§ 1º, 2º e 4º, II (*lido*) | — |
| H7 | Compra interestadual de optante do Simples gera **aviso** de antecipação/DIFAL, sem valor | norma + produto | LC 123, art. 13, § 1º, XIII, g e h, § 5º (*lido*); Temas 517 e 1284 (*secundário*) | Valor só depois de ler a lei do TO |
| H8 | Combustível da LC 192 na entrada: monofásico, sem crédito nem débito; etanol hidratado e lubrificante a conferir | norma | LC 192, arts. 2º, 4º, 5º (*lidos*) | — |
| H9 | `devolucao_compra` é natureza de **saída**, `nao_receita`, fora do saldo de devolução do art. 17; vínculo por `NFref` depois | produto | *código* `escrituracao_nfe.py:418-420`; Res. CGSN 140, art. 17 (*cópia*) | — |
| H10 | Recusas nomeadas: `tpNF` 0 de terceiro como destinatária, NFC-e como compra, `finNFe` 4 em saída própria | produto | `api_nfe.py:76-77` (mapa) | — |
| H11 | Competência da entrada = mês da **data de entrada** informada, sugerida pelo `dhEmi` | produto; rotina do manual (p. 1051-1052) | *manual*; Convênio s/nº 1970 (*não conferido*) | Q1 |
| H12 | Entradas de clientes do Simples entram no corte 1 | produto | LC 123, art. 13, § 1º, XIII, g e h (*lido*) | Q5 |

## Pendências

| # | Pendência | Onde resolver | Bloqueia |
| --- | --- | --- | --- |
| P1 | RICMS-TO (Decreto 2.912/2006) vigente: crédito, vedações, antecipação parcial e total, Anexo XXI, DIFAL, cBenef, códigos de ajuste | `dtri.sefaz.to.gov.br` (inacessível em 13/10/2026) ou DOE-TO | DL-092/093, não o corte 1 |
| P2 | Lei 1.287/2001 vigente (a cópia alcançada para em 2013 e traz 17%) e Lei 4.141/2023 (20%) | SEFAZ-TO; al.to.leg.br | Qualquer alíquota do TO |
| P3 | Lei estadual do TO que institui DIFAL/antecipação para o Simples (Tema 1284) | SEFAZ-TO; STF (portal 403 hoje) | Valor do aviso H7 |
| P4 | Convênio ICMS 142/2018 (ST: substituído sem crédito; MVA) e Convênio s/nº de 1970 (CFOP, data de entrada no livro) | CONFAZ | Marca "ST sem crédito" para regime normal; H4 e H11 |
| P5 | Regime do etanol hidratado e dos lubrificantes no TO; alíquotas ad rem do monofásico (convênios) | CONFAZ; SEFAZ-TO | Aviso em E6 |
| P6 | Tese literal dos Temas 517 e 1284 | portal do STF | Texto do aviso |
| P7 | Leitor de itens: grupos ICMS monofásico, `pRedBC`, `pMVAST`, partilha completa, `NFref`, IE/UF do destinatário | arquiteto (nova `VERSAO_LEITOR_ITENS`) | Posto (H8), devolução vinculada (H9), DIFAL futuro |
| P8 | Vínculo de entrada da filial na transferência (HI-111) | arquiteto | E8 |
| P9 | Bonificação em mercadoria recebida: receita no Presumido? | Fred (Q6); RFB (*não conferido*) | Só memória no corte 1 |
| P10 | Regras da DL-087 com `tipo` entrada, critérios CRT e UF do emitente | arquiteto (teste `test_tipo_da_regra_precisa_ser_o_tipo_da_nota`, pelo mapa) | Sugestão por regra nas entradas |
| P11 | Lei 10.833, art. 10, e Lei 10.637, art. 8º: confirmação literal do cumulativo sem crédito | Planalto (textos já baixados em 09/10) | Só o texto do aviso de PIS/Cofins |

## Proposta de corte 1 da DL-091

1. **Elegibilidade:** novo `TipoEscrituracaoNFe.ENTRADA` para a empresa **destinatária** com `finNFe` 1, modelos 55 (NFC-e 65 recusada com nome); `finNFe` 2 e 3 de terceiro entram como "ajuste de entrada" sem receita; `finNFe` 4 continua `DEVOLUCAO`; `tpNF` 0 de terceiro recusado com nome.
2. **Competência:** data de entrada informada (padrão `dhEmi`), mês encerrado segue RC-57/RC-101 (H11; Q1 ao Fred).
3. **Natureza por item**, catálogo fechado E1-E11 + "a classificar", todas `nao_receita`, com atributos estoque/custo, crédito (sim, limitado, vedado até 2032, 1/48, monofásico, não), marca ST e marca DIFAL possível.
4. **Dois CFOPs no item:** do emitente (imutável) e de entrada (confirmado); sugestão (natureza, CFOP de entrada) a partir de CFOP do emitente + CST/CSOSN + NCM + CRT do emitente; `1.949` só manual; CFOP fora da tabela recusado.
5. **Memória por item, não editável:** ICMS destacado com a marca de crédito; ST retido; `vCredICMSSN`; FCP; IPI; PIS/Cofins (CST e valor). Nenhuma linha de apuração, nenhuma alíquota do TO.
6. **Avisos nomeados:** compra interestadual de optante do Simples (LC 123, art. 13, § 1º, XIII, g e h); compra interestadual de uso/consumo/ativo em regime normal; CST sem crédito pleno em natureza com crédito; fornecedor do Simples sem `pCredSN`; lubrificante e etanol hidratado em E6; CFOP do emitente com UF incoerente.
7. **Natureza de saída `devolucao_compra`** (`nao_receita`), sugerida por `indDevol` 1 e descrição "Devolução de compra…", fora do saldo de devolução do Simples, com aviso de estorno de crédito; vínculo por `NFref` quando o leitor o ler.
8. **Fila "a classificar" e regras da DL-087** aceitando `tipo` entrada, com critérios CRT e UF do emitente (P10).
9. **Lote da DL-085** reutilizado para entradas (prévia por CFOP do emitente, CST/CSOSN, natureza sugerida).
10. **Conferência do mês de entradas:** recebidas × escrituradas × fora, totais por natureza e CFOP de entrada, soma de crédito destacado elegível, soma de ST retido, lista de notas com aviso interestadual — classe "conferência", sem impressão oficial e sem livro.
11. **Leitor de itens, nova versão** (P7), se couber na etapa; se não, a etapa declara a lacuna e o posto fica com aviso "grupo ICMS monofásico não lido".
12. **Testes de regra (nível 1):** item com `vICMS` e natureza E4 nunca vira "elegível"; fornecedor CRT 1 com `pCredSN` ausente nunca vira "elegível"; devolução de compra nunca soma receita nem saldo de devolução; nenhuma entrada altera receita, RBT12, pré-DAS ou Presumido; nota já escriturada como devolução de venda não aceita segunda escrituração; conversão 5→1, 6→2, 7→3 e recusa de CFOP de entrada fora da tabela.
13. **Fora, com nome:** F1 a F12 acima.

## Fontes consultadas hoje

**Oficiais (Planalto, por `curl`, 13/10/2026):** [LC 87/1996](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm) (arts. 20, 23, 33) · [LC 123/2006](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) (art. 13, § 1º, XIII, §§ 5º-6º; art. 23) · [LC 192/2022](https://www.planalto.gov.br/ccivil_03/leis/lcp/Lcp192.htm) (arts. 1º-6º).

**Cópia (não vigente; só localização da regra):** consolidação da Lei 1.287/2001 até a MP 26/2013, impressão de 23/02/2015 da página da SEFAZ-TO arquivada em [webfs.oecd.org](https://webfs.oecd.org/TADWEB/agriculture/data/AMIS/Indicators/Sources/TO_Lei_1.287-01.pdf) (arts. 27, 28, 28-A, 30, 31, 51).

**Não alcançados hoje:** [RICMS-TO, Decreto 2.912/2006](https://dtri.sefaz.to.gov.br/legislacao/ntributaria/decretos/Decreto2.912-06.htm) e [Lei 1.287/2001 na SEFAZ](https://dtri.sefaz.to.gov.br/legislacao/ntributaria/Leis/Lei1.287-01.htm) (DNS/502); [Tema 517 no portal do STF](https://portal.stf.jus.br/jurisprudenciaRepercussao/tema.asp?num=517) (403).

**Secundárias (só para localizar a jurisprudência):** [Tema 1284, TJGO](https://www.tjgo.jus.br/images/img/CCS/docs/Tema_1284_STF_1.pdf) · [Senior: DIFAL do Simples depende de lei específica](https://documentacao.senior.com.br/exigenciaslegais/noticias/federal/2023/2023-11-30-cobranca-de-diferencial-de-icms-para-optantes-simples-depende-lei-específica-decide-stf) · [Tributário nos Bastidores: Tema 517](https://tributarionosbastidores.com.br/2021/05/stf-e-constitucional-o-difal-exigido-das-empresas-do-simples/) · [Coad: Tema 1284](https://www.coad.com.br/home/noticias-detalhe/123060/stf-decide-que-cobranca-do-diferencial-de-aliquotas-do-icms-de-optantes-pelo-simples-nacional-depende-de-lei-especifica) · [P&R Advogados](https://pradvogados.com.br/2021/05/14/stf-e-constitucional-o-difal-exigido-das-empresas-do-simples/) · [Guia Tributário](https://guiatributario.net/tag/diferencial-de-aliquotas/) · [al.to.leg.br, arquivo 56502](https://al.to.leg.br/arquivo/56502) (lista de leis alteradoras; não lido no mérito).

**Manual do sistema de referência (cópia local do scratchpad, baixada em 09/10/2026; rotina, não norma):** Domínio Escrita Fiscal 10.1A-12 (2018), p. 462-463, 489-492, 499-500, 506, 1051-1052, 1559-1560, 1639.

**Repositório (caminhos absolutos):** `/home/user/DataLedger/docs/projeto/mapa-nfe-de-entrada-2026-10-13.md` · `/home/user/DataLedger/docs/planos/DL-067-plano-do-modulo-fiscal.md` (linhas 400-451, 820-843, 955-986, 1015-1051) · `/home/user/DataLedger/docs/projeto/revisao-do-fiscal-2026-10-09.md` · `/home/user/DataLedger/docs/projeto/pesquisa-acumuladores-2026-10-09.md` · `/home/user/DataLedger/docs/projeto/fontes-de-referencia.md` · `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md` · `/home/user/DataLedger/docs/projeto/consultas/2026-10-12-contador-senior-dl087-regras.md` · `/home/user/DataLedger/docs/projeto/requisitos.md` (linhas 99-130, 178-230) · `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py` (1-460) · `/home/user/DataLedger/apps/fiscal/models.py` (3085-3345, 3711-3970) · `/home/user/DataLedger/apps/fiscal/tomadas.py` (1-120, 400-490) · `/home/user/DataLedger/apps/fiscal/cfop.py` · `/home/user/DataLedger/apps/fiscal/dados/cfop_it2023002_v210.csv` · `/home/user/DataLedger/apps/fiscal/classificacao.py` (assinaturas).

**O que não determinei:** redação vigente de qualquer dispositivo estadual do Tocantins; se o TO tem lei em sentido estrito para o DIFAL do Simples; o comportamento do leitor de itens diante dos grupos ICMS monofásico; se as regras da DL-087 aceitam `tipo` entrada (li só assinaturas de `classificacao.py`, não o modelo de regra). Não executei testes nem comandos de verificação.
