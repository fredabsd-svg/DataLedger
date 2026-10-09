# Consulta ao contador-senior sobre frete em item não-receita, lubrificante e devolução de combustível — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Origem:** auditoria da DL-083, rodada 1, achados A1, A3 e A6 · **Marcas:** *lido* = texto oficial aberto hoje (Planalto via curl, MOC 7.0 e tabela de CFOP já no scratchpad, textos de IN e Resolução já baixados em `scratchpad/leis/`); *cópia* = texto íntegro em site terceiro; *secundário* = notícia, fornecedor ou fórum; *não conferido* = conhecimento meu sem texto aberto hoje. O que é **rotina/produto** está dito como tal e é reversível pelo Fred.

**O que li no repositório:** `docs/auditorias/2026-10-09-dl-083-rodada-1.md` (A1, A3, A6, mutantes N03/N06/M11b/M11c); `docs/planos/DL-083-receita-de-nfe-no-presumido.md`; `docs/projeto/consultas/2026-10-09-contador-senior-pe83-pe84-pe85.md` (PE-85.1, 85.2, 85.5); HI-119 e HI-124 em `docs/projeto/requisitos.md:188,193`; `apps/fiscal/cfop.py:110-127`; `apps/fiscal/escrituracao_nfe.py:189-220` e `:689-738`; `apps/fiscal/itens_nfe.py:364-402`; `apps/fiscal/models.py:2639-2812` (catálogo de naturezas; `ItemNFe.ncm` em `:3029`); `apps/fiscal/presumido.py:972-1025`; `apps/fiscal/presumido_tabelas.py:46-78`; `apps/fiscal/dados/cfop_it2023002_v210.csv` (faixas x.65x, x.66x, x.91x).

**Lidos hoje em fonte oficial:** Lei 9.249, art. 15, caput e §§ 1º e 2º (Planalto, hoje); IN RFB 1.700, art. 33, caput e § 1º, I, e art. 26 (texto baixado); DL 1.598, art. 12, I a IV e § 1º; LC 123, art. 3º, § 1º; MOC 7.0, Anexo I, I17b, I17b-10, W07-10 a W16-10, LA01/LA02. **Cópias:** SC Cosit 25/2023 (PDF do IBET, itens 16 a 23 relidos hoje); Res. CGSN 140, art. 2º, § 5º, III, e art. 17 (PDF já no scratchpad); SC Cosit 150/2019 (LegisWeb). **Secundários:** SC Cosit 42/2026 (Fenacon, CFC/contadores.cnt.br, amdjus; o portal de normas da Receita é aplicação de página única e não devolveu texto ao curl, e o agregador respondeu 403); SC Cosit 143/2021 (tributodevido); SC Disit/SRRF07 64/2013 (fórum). **Não localizei** solução de consulta Cosit sobre lubrificante no percentual de 1,6% (duas buscas, uma estendida) nem sobre frete destacado em venda de bens no Presumido.

---

## 1. Frete, seguro e outras despesas rateados em item que não é receita

### Resposta

**É receita, e é receita da venda.** O frete, o seguro e as "outras despesas" cobrados numa nota em que há venda compõem o produto da venda, não importa em qual item o sistema do emitente os rateou. O item bonificado não tem preço; o frete rateado nele continua sendo o que o adquirente pagou para receber a mercadoria **vendida**. Pelo mesmo raciocínio, um desconto lançado num item `indTot` 0 de bonificação, que reduz o `vNF`, é desconto incondicional da nota e **reduz a receita da venda**. Regra que recomendo: **(a)**, rateio do resíduo dos itens não-receita sobre os itens de receita da mesma nota, **proporcional** à receita de cada um, com aviso na memória; **(b)** só quando a nota não tem nenhum item de receita e o resíduo é diferente de zero.

### Fundamento

- Receita bruta é "o produto da venda de bens nas operações de conta própria" (DL 1.598, art. 12, I, *lido*; LC 123, art. 3º, § 1º, *lido*), "não incluídas as vendas canceladas e os descontos incondicionais concedidos" (LC 123, idem; Lei 9.249, art. 15, caput, red. Lei 12.973, *lido*: "deduzida das devoluções, vendas canceladas e dos descontos incondicionais concedidos"). O produto da venda é o que o comprador paga pela operação; a nota autorizada diz quanto foi isso (`vNF`).
- A lei não tem texto expresso sobre frete cobrado do adquirente em venda de bens. É a lacuna que a HI-119 já registra (*requisitos.md:188*). O que existe: para o Simples, a SC Cosit 143/2021 (frete e comissão integram a base; LC 123, art. 3º, § 1º; Res. 140, art. 2º, II) e a SC Disit/SRRF07 64/2013 ("compreende-se na receita bruta de venda [...] o custo do frete destacado nas notas fiscais de venda") — ambas *secundárias*, não li os textos oficiais. Para serviços no Presumido, as SC Cosit 110/2017 e 144/2023 (custos faturados ao tomador integram o preço) — *secundárias*. A direção é uma só e nunca vi orientação em contrário.
- O MOC confirma que o emitente **cobrou** esses valores: W08-10, W09-10, W10-10 e W15-10 somam frete, seguro, desconto e `vOutro` de **todos** os itens, sem filtro de `indTot`; só W07-10 filtra `indTot` 1 (*lido*). O `vNF` da nota do exemplo (venda 100 + bonificação 10 com `vDesc` 10 em `indTot` 0 + frete 50) é **140**, e o cliente pagou 140. Receita de 145,45 (o que o código faz hoje, pelo A3/E1) é a mais; receita de 100 (E2) é a menos.
- A bonificação sai da receita **porque não tem contraprestação** (Res. CGSN 140, art. 2º, § 5º, III, *cópia*: "desde que seja incondicional e não haja contraprestação por parte do destinatário"). Frete cobrado **é** contraprestação. Logo o item bonificado com frete cobrado não é bonificação pura: o produto é brinde, o frete é receita. No Presumido a exclusão da bonificação é prática sem texto expresso (HI-124, *não conferido*), o que reforça: na dúvida, o valor cobrado entra.

### Em qual atividade ou anexo

Não há norma de rateio (Lei 9.249, art. 15, § 2º, só diz "o percentual correspondente a cada atividade", *lido*). É **regra de produto**, e a minha posição é: o resíduo (positivo ou negativo) dos itens não-receita é distribuído sobre os itens de receita **da mesma nota**, proporcional à `receita_do_item` de cada um, resíduo de arredondamento no item de maior valor. Cada parcela herda natureza, atividade de presunção, anexo e segregação do item que a recebeu. Motivos: (i) é neutro e reproduzível, o contador refaz à mão; (ii) "ao maior" é arbitrário e muda com um centavo; (iii) em 95% das notas há uma só natureza de receita e o rateio vira transferência simples; (iv) preserva W16 ao centavo, porque a soma da nota não muda.

### Proposta para o produto

1. `receita_do_item` continua como está (ela já é a regra do MOC). O que muda é **uma etapa de atribuição por nota**, antes de somar por natureza: resíduo = Σ `receita_do_item` dos itens com papel `nao_receita`; se ≠ 0 e há itens de receita na nota, ratear sobre eles; o resíduo deixa de ficar "sem lugar".
2. A guarda de `escrituracao_nfe.py:712` passa a valer para `indTot` 0 **e** 1 e para `valor != 0`, mas **só bloqueia quando a nota não tem item de receita** (remessa pura, transferência pura, 5.910 sozinho) — aí o frete cobrado é receita sem venda (DL 1.598, art. 12, IV) e o contador escolhe. Natureza `deducao` fica fora da guarda (M11c): devolução com frete é dedução do frete devolvido.
3. Aviso na memória e na tela: "item n (bonificação): R$ X de frete/seguro/outros (ou desconto) atribuído à receita da venda desta nota". Se houver mais de uma natureza de receita, o aviso mostra o rateio.
4. Se o resíduo negativo exceder a receita da nota (receita ficaria < 0), bloquear: nota anômala.
5. Testes: E1 (resíduo −10 → receita 90) e E2 (+50 → receita 150); nota com revenda e produção própria recebendo rateio; nota só de remessa com frete → recusa; devolução com frete → sem recusa.

Isso não bloqueia a escrituração em volume (DL-085, RC-173): a NFC-e rejeita `indTot` 0 (I17b-10, *lido*), e bonificação com frete em `indTot` 1 resolve-se pelo rateio sem intervenção.

### Segurança

Alta em "é receita e reduz/aumenta a receita da venda". Média no critério proporcional, que é produto, não norma.

---

## 2. Lubrificante no 1,6%

### Resposta

**Lubrificante fica no 8%.** O 1,6% é para "revenda, para consumo, de **combustível** derivado de petróleo, álcool etílico carburante e gás natural" (Lei 9.249, art. 15, § 1º, I, *lido* hoje). Lubrificante é derivado de petróleo, mas não é combustível: não se destina à queima. A SC Cosit 25/2023 decompõe o inciso em três requisitos e o primeiro é "o produto negociado deve ser combustível derivado de petróleo, álcool etílico carburante e gás natural" (item 16, *cópia*) — e ela própria aplica a regra "onde a lei não distingue, o intérprete não distingue" (item 18), que corta nos dois sentidos: a lei também não **amplia** para o que não é combustível. A tabela de CFOP junta "combustíveis ou lubrificantes" na mesma faixa por razão de ICMS (CF, art. 155, § 2º, X, "b", trata petróleo "inclusive lubrificantes", *não conferido* hoje), não de IRPJ; a descrição de CFOP não é fundamento normativo (`cfop.py:13-15` já diz isso).

**Não localizei solução de consulta Cosit** que diga isso expressamente sobre lubrificante, nem em sentido contrário. A posição é leitura literal do texto da lei e da IN 1.700, art. 33, § 1º, I (*lido*, mesma redação), confirmada pelo desenho da SC 25/2023. Digo isso com clareza porque o Fred pode querer confirmar pela base de soluções de consulta (normas.receita.fazenda.gov.br, busca "lubrificante" e "percentual de presunção").

### Impacto

Posto que vende óleo de motor na pista, em NFC-e com CFOP 5.656 (que a tabela descreve como "combustíveis **ou** lubrificantes"), hoje recebe sugestão de 1,6%. A diferença é 6,4 pontos de base × 15% = **0,96% da receita de lubrificantes** em IRPJ a menos (sem adicional), fora o risco de confirmação em bloco. CSLL não muda (12% nas duas).

### Proposta para o produto

1. A sugestão `combustivel` pelo CFOP (`escrituracao_nfe.py:194-220`) ganha uma **segunda condição pelo NCM** (`ItemNFe.ncm`, `models.py:3029`), como tabela com fonte (TIPI), ao lado da tabela de CFOP:
   - NCM de combustível (lista positiva): 2710.12 (gasolinas), 2710.19.1 (querosenes), 2710.19.2 (diesel e óleo combustível), 2711 (GLP, gás natural), 2207 (álcool etílico), 2710.20 (diesel com biodiesel) → sugestão mantida;
   - NCM 2710.19.3 (óleos lubrificantes) e 3403 (preparações lubrificantes) → sugerir `revenda` (8%), com aviso "lubrificante: fora do 1,6% (Lei 9.249, art. 15, § 1º, I)";
   - NCM fora das duas listas, ou ausente → **sem sugestão**, mesmo com CFOP 5.656.

   As faixas de NCM acima são conhecimento meu, **não conferidas hoje na TIPI**: quem implementar confere na TIPI vigente antes de gravar a tabela, e registra a data e o sha, como fez em `cfop.py`. Biodiesel B100 (NCM 3826) não é derivado de petróleo nem álcool carburante nem gás natural: pela letra, 8%; deixo como hipótese (abaixo).
2. Sinal auxiliar, não decisivo: o grupo `comb`/`cProdANP` (LA01/LA02) é obrigatório para "combustíveis líquidos e lubrificantes" (*lido* hoje no MOC), então **também** vem no lubrificante e não separa os dois. Não usar como critério.
3. Mesma gate de NCM na natureza de **devolução** de combustível (item 3).
4. Teste: NFC-e de posto com dois itens, gasolina (2710.12.59) e óleo lubrificante (2710.19.32), ambos 5.656: sugestão 1,6% só no primeiro.

### Segurança

Alta na leitura da lei (literal e coerente com a SC 25/2023). Média na ausência de SC específica: se existir uma em sentido contrário, não a encontrei.

---

## 3. Devolução de combustível recebida e própria

### Resposta

**A proposta do arquiteto está correta na essência e eu a refino em dois pontos.** (i) A devolução deduz na **atividade da venda original**: duas naturezas de devolução (consumo 1,6% × comércio 8%) resolvem o bloqueio hoje sem saída. (ii) **Discordo de "sem sugestão"**: o CFOP da devolução de combustível descreve exatamente o requisito que decide o percentual (destinação), então o produto deve **sugerir e pedir confirmação**, como já faz na venda — bloquear o trimestre sem caminho é pior do que sugerir com confirmação. (iii) Acrescento: o **saldo de devolução transportado precisa ser por atividade**, não um só.

### Fundamento

- Lei 9.249, art. 15, caput: percentual "sobre a receita bruta [...] deduzida das devoluções"; § 2º: "no caso de atividades diversificadas será aplicado o percentual correspondente a cada atividade" (*lido* hoje). A IN 1.700, art. 33, caput, fecha a leitura: "receita bruta [...] **auferida na atividade**, deduzida das devoluções, das vendas canceladas e dos descontos incondicionais" (*lido*). Devolução é dedução da receita bruta **daquela atividade**; não existe "devolução de 8%" ou "de 1,6%", existe devolução da venda que foi a 8% ou a 1,6%. Lei 9.430, art. 25, I, repete a dedução (*lido em 09/10, consulta anterior*).
- SC Cosit 42/2026 (DOU 17/03/2026), conforme Fenacon e CFC (*secundário*): as deduções "correspondem a uma redução da receita bruta da respectiva atividade", e, sem receita no mês, vão "para períodos posteriores em que haja receita **da mesma natureza**", limitadas à receita do período. Vincula-se à SC Cosit 150/2019 (*cópia*: dedução em períodos subsequentes, "vedada a repetição de indébito"). Isso sustenta duas coisas que o produto faz ou precisa fazer: o saldo passa adiante **e** passa dentro da mesma atividade.
- Res. CGSN 140, art. 17, I (*cópia*): dedução "segregada pelas regras vigentes no Simples Nacional nesse mês" — mesma lógica de "dentro do segmento" (HI-129); combustível no Simples já recusa (HI-132), fora do caso.
- Tabela de CFOP (*lido*, CSV do repositório): a devolução **recebida** chega com o CFOP do cliente — 5.660/6.660 "adquiridos para industrialização", 5.661/6.661 "adquiridos para comercialização", 5.662/6.662 "adquiridos por consumidor ou usuário final", todos `indDevol` 1. A **própria** (nota de entrada) vem com 1.660–1.662/2.660–2.662, "destinados à industrialização / comercialização / consumidor final". O terceiro dígito final diz a destinação original: **x.662 → venda para consumo (1,6%); x.660 e x.661 → venda para industrialização ou comercialização (8%)**. É o requisito III da SC 25/2023, item 21 (*cópia*).

### Proposta para o produto

1. Catálogo: `devolucao_venda` (deduz de `COMERCIO_INDUSTRIA_TRANSPORTE_CARGA`, mantém) e nova `devolucao_combustivel_consumo` (deduz de `REVENDA_COMBUSTIVEIS`). Nome em tela: "Devolução de venda de combustível para consumo (deduz do 1,6%)".
2. Reconhecimento (corrige A1): `e_devolucao_de_venda_de_combustivel` passa a cobrir também o prefixo "Devolução de compra de combustíveis ou lubrificantes" com `indDevol` 1 (5.660–5.662, 6.660–6.662), **só quando a empresa é destinatária**. Segundo sinal: NCM de combustível (lista do item 2), para pegar devolução com CFOP genérico (1.202/2.202/5.202, 1.949).
3. Sugestão, nunca gravação: x.662 com NCM de combustível → `devolucao_combustivel_consumo`; x.660/x.661 → `devolucao_venda`; NCM de lubrificante → `devolucao_venda` com aviso; CFOP genérico com NCM de combustível → **sem sugestão**, recusa nomeada até confirmar; sem sinal nenhum → `devolucao_venda` como hoje. Se a empresa for produtora (não revenda), nenhum combustível é 1,6% — isso vem do padrão da empresa (DL-084), não da nota.
4. A recusa `devolucao_combustivel` **continua existindo**, mas só para devolução com sinal de combustível **ainda em `devolucao_venda` sem confirmação do contador**; confirmada, sai. Isso dá o caminho que hoje não existe. Confirmação em bloco permitida para sugestão por x.662/x.661, como na venda.
5. **Saldo por atividade**: `saldo_transportado` e `devolucao_deduzida` passam a ser por código de atividade. Hoje a devolução de 8% consome receita de 8%; com a natureza nova, a de 1,6% só consome receita de 1,6% (SC 42/2026, "mesma natureza", *secundário*). Teste: trimestre com comércio 100.000 e combustível 100.000, devolução 10.000 em cada natureza → IRPJ muda em 96,00 por 10.000 entre as duas (a conta do A1).
6. **Ponto que não determinei e que pede verificação:** uma NF-e com CFOP 5.661 **emitida pela própria empresa** (posto devolvendo à distribuidora) é devolução de **compra**, saída própria com `finNFe` 4, e não pode deduzir receita nem ser receita. A auditoria testou 5.661 só no papel de destinatário. Confira como a elegibilidade trata emitente + `finNFe` 4; se cair em `TipoEscrituracaoNFe.DEVOLUCAO`, é defeito a mais.

### Segurança

Alta em "deduz na atividade da venda original" (lei, IN e duas SCs convergem). Média na sugestão por x.662/x.661 (descrição de tabela de apoio, não norma; o contador confirma). Média-baixa no detalhe "receita da mesma natureza" da SC 42/2026, lida só em notícia.

---

## Tabela: pergunta × decisão × muda o código?

| Pergunta | Decisão | Muda o código? |
| --- | --- | --- |
| 1. Frete/seguro/outros e desconto em item não-receita | É receita (ou redução) da **venda da mesma nota**; rateio proporcional aos itens de receita; bloqueio só em nota sem item de receita; guarda vale para `indTot` 0 e 1, `valor != 0`, exclui `deducao` | **Sim**: etapa de atribuição por nota; guarda em `escrituracao_nfe.py:712`; avisos; testes E1, E2, nota só remessa, devolução com frete |
| 2. Lubrificante | **8%**, não 1,6% (Lei 9.249, art. 15, § 1º, I, literal; SC 25/2023, requisito I); sem SC específica localizada | **Sim**: tabela de NCM com fonte (TIPI, a conferir); sugestão de `combustivel` exige CFOP **e** NCM; lubrificante sugere `revenda` com aviso |
| 3. Devolução de combustível | Deduz na atividade da venda original; natureza nova `devolucao_combustivel_consumo`; reconhecer 5.66x/6.66x recebidas e NCM; **sugerir** por x.662/x.661 com confirmação; saldo transportado **por atividade** | **Sim**: `cfop.py:114-127`, catálogo, sugestão, `presumido.py:972-1025` e saldo por atividade; migração aditiva; testes do A1, N03, N06 |

## Hipóteses para o Fred

1. **HI (produto):** o resíduo de item não-receita é rateado proporcionalmente sobre os itens de receita da mesma nota. Alternativa reversível: atribuir todo ao item de receita de maior valor. O critério não muda a receita total, só a atividade/anexo em nota mista.
2. **HI (normativa, literal):** lubrificante (NCM 2710.19.3 e 3403) está fora do 1,6%. Vale confirmar na base de SCs da Receita; se o escritório já apura posto com lubrificante a 1,6%, é risco a corrigir, não a manter.
3. **HI (normativa):** biodiesel puro (B100, NCM 3826) e GNV: GNV é "gás natural", 1,6%; B100 pela letra não é derivado de petróleo → 8%. Não localizei SC; o padrão do produto deve ser 8% (lado que paga a mais) até confirmar.
4. **HI (normativa, SC 42/2026 em secundário):** o saldo de devolução só consome receita da **mesma atividade**. Peço que alguém com acesso ao portal de normas abra a SC 42/2026 e confirme a redação "mesma natureza"; se o texto disser outra coisa, a parte do saldo por atividade volta a ser decisão de produto.
5. **Fato da carteira:** se o posto/TRR/distribuidora da RC-173 vende lubrificante na pista e como o emite (CFOP 5.656 ou 5.102; NCM preenchido corretamente). Decide a prioridade da tabela de NCM, não a regra.
6. **Verificação técnica pendente (item 3.6):** devolução de **compra** emitida pela própria empresa (5.66x, `finNFe` 4) não pode virar dedução de receita. Não determinei o comportamento atual.

**O que não consegui determinar hoje:** texto oficial da SC Cosit 42/2026 e da SC Cosit 150/2019 (só cópia/notícia); existência de SC Cosit sobre lubrificante no Presumido; faixas exatas da TIPI para os NCM citados; texto da SC Cosit 143/2021 e da SC Disit 64/2013 sobre frete.

Fontes abertas hoje: https://www.planalto.gov.br/ccivil_03/leis/l9249.htm · https://www.ibet.com.br/wp-content/uploads/2023/01/SC_Cosit_n_25-2023.pdf (cópia) · https://www.legisweb.com.br/legislacao/?id=377767 (SC 150/2019, cópia) · https://fenacon.org.br/noticias/receita-esclarece-deducao-de-devolucoes-de-vendas-no-lucro-presumido-para-irpj-e-csll/ e https://amdjus.com.br/entenda-como-deduzir-devolucoes-de-vendas-no-lucro-presumido-para-irpj-e-csll-segundo-a-receita-federal/ (SC 42/2026, secundário; apontam para normasinternet2.receita.fazenda.gov.br/#/consulta/externa/149976, não acessível ao curl) · https://tributodevido.com.br/portal/frete-e-taxa-de-comissao-integram-base-de-calculo-do-simples-nacional/ (SC 143/2021, secundário) · https://www.contabeis.com.br/forum/tributos-estaduais-municipais/255696/frete-e-tributavel-no-simples-nacional/ (SC Disit 64/2013, secundário) · arquivos locais: `scratchpad/leis/in1700.txt`, `del1598.txt`, `lcp123.txt`, `res140.txt`; `scratchpad/nfe/nt_txt/moc7_anexo_i.txt`; `apps/fiscal/dados/cfop_it2023002_v210.csv`.
