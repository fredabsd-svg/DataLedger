# Consulta ao contador-senior sobre o pré-DAS de comércio e indústria — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Grau de segurança geral:** alto no cálculo dos Anexos I e II, na segregação de ST, monofásico e exportação e no uso do RBT12 total (texto literal da LC 123 lido hoje no Planalto, Res. CGSN 140 em cópia íntegra coerente com o Manual, exemplos oficiais batendo centavo a centavo); médio na devolução por segmento (norma clara, mecânica do PGDAS-D inferida); baixo no ICMS do Tocantins (SEFAZ-TO fora do ar, só fonte secundária) · **Marcas:** *lido* = texto oficial lido hoje (LC 123 baixada do Planalto em 09/10/2026, HTTP 200, 1.622.252 bytes; Manual do PGDAS-D e DEFIS v. 17/06/2025 do Portal do Simples Nacional); *cópia* = Res. CGSN 140/2018 consolidada em PDF de terceiro (o SIJUT oficial não renderiza); *secundário* = notícia ou rotina sem valor normativo; *não conferido* = conhecimento meu, a confirmar; *calculado* = exemplo que eu produzi, não oficial.

Tudo abaixo é hipótese até o Fred validar. Fontes:
- LC 123/2006, arts. 13, 13-A, 18, 19 e 20 — *lido*: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- Res. CGSN 140/2018, arts. 12, 17, 21 a 26, 28, 30 a 36 — *cópia*: https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf (oficial sem texto: http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278)
- Manual do PGDAS-D e DEFIS, itens 6.4 a 6.6.4, 8.1, 8.4, 12 e exemplos 1 a 12 — *lido*: https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf
- Tabela oficial de CFOP já baixada do Portal da NF-e pela DL-081 (arquivo `cfop_oficial.csv` do scratchpad) — *lido*
- Repositório: `apps/fiscal/pre_das.py`, `apps/fiscal/simples_tabelas.py`, `apps/fiscal/receita.py`, `apps/fiscal/models.py`, `docs/planos/DL-075-pre-das-do-simples.md`, `docs/planos/DL-081-escrituracao-das-nfe-de-saida.md` — *lido*
- Script da skill `contador-senior/scripts/simples_nacional.py` — executado; ele calcula alíquota efetiva e DAS cheio e **não faz repartição** (aviso do próprio script). A repartição dos exemplos calculados foi feita por mim em `Decimal`, com as tabelas de `apps/fiscal/simples_tabelas.py`.
- **Não alcançados hoje:** `dtri.sefaz.to.gov.br` (CONNECT 502) e `sefaz.to.gov.br` (connection reset).

---

## 1. Cálculo do Anexo I e do Anexo II

**Resposta curta.** Igual aos serviços. A alíquota efetiva é a mesma fórmula do § 1º-A, `(RBT12 × Aliq − PD) / RBT12`, com RBT12 = 0 valendo R$ 1,00; o percentual efetivo de cada tributo é alíquota efetiva × repartição da faixa (§ 1º-B), e a diferença centesimal vai ao tributo de maior repartição (§ 1º-B, II). **Não há teto para o ICMS nem redistribuição**: o teto de 5% é só do ISS (§ 1º-B, I), e a nota (*) existe apenas nos Anexos III e IV. O ICMS da 6ª faixa (RBT12 acima de R$ 3,6 mi) tem regra própria (ICMS pela 5ª faixa), que fica fora do primeiro corte.

**Repartição conferida contra a DL-075.** Reconferi hoje no Planalto os sete percentuais do Anexo II (1ª a 5ª faixas: IRPJ 5,50%, CSLL 3,50%, Cofins 11,51%, PIS 2,49%, CPP 37,50%, IPI 7,50%, ICMS 32,00%; 6ª: 8,50%, 7,50%, 20,96%, 4,54%, 23,50%, IPI 35,00%, sem ICMS) e a 6ª do Anexo I (13,50%, 10,00%, 28,27%, 6,13%, 42,10%, sem ICMS). Batem com `apps/fiscal/simples_tabelas.py` (linhas 167 a 276). O Anexo I das faixas 2, 3, 4 e 5 bate centavo a centavo com os exemplos 1, 3 e 6 do Manual (item 8 abaixo). O Anexo II não tem exemplo numérico no Manual (verifiquei os doze exemplos): a conferência é só textual.

**NORMA.**
- LC 123, art. 18, § 1º (RBT12), § 1º-A (fórmula), § 1º-B, I e II (repartição, teto só do ISS, diferença centesimal), § 3º ("Sobre a receita bruta auferida no mês incidirá a alíquota efetiva determinada na forma do caput e dos §§ 1º, 1º-A e 2º"), § 4º, I e II (revenda → Anexo I; industrializadas → Anexo II), § 5º ("As atividades industriais serão tributadas na forma do Anexo II") — *lido*.
- Nota (*) do teto de 5%: aparece duas vezes no texto compilado, uma depois do cabeçalho do Anexo III e outra depois do Anexo IV; não há nota nos Anexos I, II e V — *lido* (conferido por busca no HTML baixado hoje).
- Res. CGSN 140, art. 21, I a III e parágrafo único; art. 25, § 1º, I e II — *cópia*. O art. 21, III, "a" também só fala em ISS. O art. 21, III, "b" é a regra do ICMS/ISS para RBT12 acima da 5ª faixa.
- Manual, item 8.1 ("quando RBT12=0, considerar RBT12=1") e exemplo 1 (repartição completa do Anexo I) — *lido*.

**Proposta para o produto.** Reaproveitar `aliquota_efetiva`, `percentuais_efetivos` e `valor_do_tributo` de `apps/fiscal/pre_das.py` (linhas 311 a 385) sem mudança: `percentuais_efetivos` já trata `teto_iss is None` para os Anexos I e II. O que muda é a origem do anexo: na NF-e ele vem da **natureza do item** (`revenda` → I; `producao_propria` → II; `CATALOGO_NATUREZA_NFE`, `apps/fiscal/models.py:2677-2763`), não da atividade padrão da empresa. O bloqueio `notas_sem_atividade_definida` (BL-670, `pre_das.py:936-949`) não deve disparar por causa de NF-e: a NF-e já diz o anexo.

**Grau de segurança: alto.**

---

## 2. Empresa com mais de um anexo no mesmo mês

**Resposta curta.** O RBT12 é **um só, o total da empresa** (interno e externo separados, nada mais): cada anexo aplica a sua alíquota nominal e a sua parcela a deduzir sobre o **mesmo** RBT12, e a receita do mês é dividida por anexo. O fator r é apurado com a folha e a receita **da empresa inteira** (conjunto interno + externo), mas só **decide o anexo das atividades do inciso V** (serviços sujeitos ao fator r); a revenda continua no Anexo I e a indústria no Anexo II qualquer que seja o r. O PGDAS-D faz exatamente isso: uma receita bruta total do PA, uma linha por atividade e segregação, cada linha no seu anexo.

**NORMA.**
- LC 123, art. 18, § 1º ("receita bruta acumulada nos 12 meses anteriores ao do período de apuração", sem recorte por atividade), § 3º e § 4º, I a VI ("considerar, destacadamente, para fim de pagamento, as receitas decorrentes da" revenda, indústria, serviços etc.) — *lido*. O § 3º citado no pedido não fala em RBT12 por anexo: fala na incidência da alíquota efetiva sobre a receita do mês; o RBT12 único vem do § 1º.
- Res. CGSN 140, art. 22, § 1º ("receita bruta **total** acumulada auferida nos 12 meses anteriores"), art. 23 (só interno e exportação são separados), art. 25, caput e § 1º (segregação por anexo "para fim de cálculo e pagamento"), art. 26, caput (fator r só "na hipótese de ... obter receitas decorrentes da prestação de serviços previstas no inciso V do § 1º do art. 25"), § 5º, V (RBT12r conjunto) — *cópia*.
- LC 123, art. 18, §§ 5º-J, 5º-K e 24 (razão folha/receita **da pessoa jurídica**) — *lido* na consulta de 08/10.

**ROTINA (Manual, *lido*).** Exemplo 2: mesma empresa, RBT12 = 300.000, revenda 300.000 (Anexo I, efetiva 5,32%, 15.960,00) e serviço 100.000 (Anexo III, efetiva 8,08%, 8.080,00), total 24.040,00. Item 6.4: a receita bruta do PA é informada uma vez, por mercado, para todos os estabelecimentos; item 6.5: as atividades são linhas separadas ("1 - Revenda de mercadorias, exceto para o exterior" com e sem ST; "2 - Revenda para o exterior"; "3 - Venda de mercadorias industrializadas" com e sem ST; "4 - industrializadas para o exterior"; e os itens de serviço).

**Proposta para o produto.** Chave de agrupamento do pré-DAS passa a ser `(mercado, anexo, segmento)` como hoje (`pre_das.py:1040-1048`), com as linhas de NF-e entrando com anexo fixo pela natureza e as linhas de serviço pelo enquadramento da atividade. O RBT12 por mercado continua sendo o de `apuracao.rbt12`, que já soma NF-e (DL-081). O fator r só é exigido se houver linha de serviço com `ANEXO_III_OU_V_FATOR_R`; receita de mercadoria não o dispara, mas **entra** no RBT12 conjunto do denominador, como já entra hoje.

**Grau de segurança: alto.**

---

## 3. Segregação na revenda (Anexo I)

**Resposta curta.** Em todos os casos a regra é a mesma do ISS retido: o percentual do tributo desonerado é **desconsiderado e os demais ficam exatamente como estão**; não há redistribuição (a única redistribuição do sistema é a do excedente do ISS a 5%, que não existe no ICMS). O que muda de caso para caso é **quais** percentuais saem:

| Caso | Percentuais desconsiderados | Permanecem | Dispositivo |
| --- | --- | --- | --- |
| ICMS-ST **substituído** (CSOSN 500 / CST 60), e antecipação com encerramento | ICMS | IRPJ, CSLL, Cofins, PIS, CPP | Res. 140, art. 25, § 8º, I; LC 123, art. 18, § 4º-A, I e § 12 |
| **Substituto** (CSOSN 201/202/203): operação própria | **nenhum** — receita "não sujeita à ST", ICMS próprio no DAS | todos | Res. 140, art. 25, § 8º, II, "a"; art. 28, I |
| Substituto: o `vST` | não é receita (fora da base e do RBT12); o ICMS-ST vai à SEFAZ por fora | — | Res. 140, art. 28, §§ 1º e 4º; LC 123, art. 13, § 1º, XIII, "a" |
| PIS/Cofins **monofásico** (ou ST de PIS/Cofins) | Cofins e PIS | IRPJ, CSLL, CPP, ICMS | Res. 140, art. 25, §§ 6º e 7º, II; LC 123, art. 18, § 4º-A, I e § 12 |
| **Exportação** (direta ou por comercial exportadora) | Cofins, PIS, IPI, ICMS (e ISS) — "tão somente" | IRPJ, CSLL, CPP, na alíquota do **RBT12 externo** | Res. 140, art. 25, § 3º; art. 23; LC 123, art. 18, § 4º-A, IV e § 14 |
| **ST + monofásico no mesmo item** | ICMS + Cofins + PIS | IRPJ, CSLL, CPP | soma dos §§ 6º e 8º, I; Manual 6.5 e 6.6 |
| Exportação + ST ou + monofásico | nada além da exportação (ICMS, PIS e Cofins já saíram) | IRPJ, CSLL, CPP | § 3º já abrange |
| Substituto + monofásico | Cofins e PIS; ICMS próprio fica | IRPJ, CSLL, CPP, ICMS | §§ 6º e 8º, II, "a" |

**NORMA (texto literal, *cópia*).**
- Art. 25, § 6º: quem importa, industrializa ou comercializa produto monofásico ou com ST de PIS/Cofins "deve segregar a receita ... de forma que serão desconsiderados, no cálculo do valor devido no âmbito do Simples Nacional, os percentuais a elas correspondentes"; § 7º, II: "os valores relativos aos demais tributos ... serão calculados tendo como base de cálculo a receita total decorrente da venda do produto".
- Art. 25, § 8º, I: o substituído e o contribuinte da antecipação com encerramento segregam a receita "como 'sujeita à substituição tributária ou ao recolhimento antecipado do ICMS', quando então será desconsiderado ... o percentual do ICMS"; II, "a": o substituto deve "recolher o imposto sobre a operação própria pelo Simples Nacional e segregar a receita correspondente como 'não sujeita à substituição tributária'"; "b": recolher o ICMS-ST na forma do art. 28, §§ 1º a 3º.
- Art. 28, § 4º: "não será considerado receita de venda ou revenda de mercadorias o valor do tributo devido a título de substituição tributária".
- Art. 25, § 3º: exportação, "inclusive as vendas realizadas por meio de comercial exportadora ou sociedade de propósito específico", desconsiderando "os percentuais relativos à Cofins, à Contribuição para o PIS/Pasep, ao IPI, ao ICMS e ao ISS".
- LC 123, art. 18, § 4º-A, I ("tributação concentrada em uma única etapa (monofásica), bem como, em relação ao ICMS, que o imposto já tenha sido recolhido por substituto tributário ou por antecipação tributária com encerramento de tributação"), § 12 ("serão consideradas as reduções relativas aos tributos já recolhidos, ou sobre os quais tenha havido tributação monofásica") e § 14 ("tão somente") — *lido*.

**ROTINA (Manual, *lido*).** Itens 6.6.2 a 6.6.4 repetem três vezes a frase-chave: "essas receitas continuam fazendo parte da base de cálculo dos demais tributos abrangidos pelo Simples Nacional" — é a confirmação de que não há redistribuição. Item 6.6.3 (quadro "IMPORTANTE"): o substituto segrega como "Sem substituição tributária" e "o aplicativo irá calcular o ICMS sobre a operação própria com base na receita informada"; o ICMS-ST "é recolhido diretamente ao ente federado competente, em guia específica, fora do Simples Nacional". Item 6.5: a qualificação é **por tributo** (list box: "COFINS – Tributação monofásica; COFINS – Substituição tributária; PIS – ...; ICMS – Antecipação com encerramento de tributação; ICMS – Substituição tributária"), e o botão "+" subdivide a receita quando "parte da receita tem substituição de ICMS e a outra parte tem tributação monofásica de PIS e Cofins" — por isso a combinação no mesmo item é só a união dos conjuntos. Não há exemplo numérico de ST nem de monofásico no Manual; o único exemplo de desconsideração é o 6 (exportação), com os tributos zerados na tabela e o total igual à soma dos restantes.

**Proposta para o produto.** Estender `_DESCONSIDERADOS` (`pre_das.py:198-201`) com os segmentos de mercadoria: `sujeita_st` → {ICMS}; `monofasico` → {PIS, COFINS}; `st_e_monofasico` → {ICMS, PIS, COFINS}; `exportacao` → {PIS, COFINS, IPI, ICMS, ISS} (hoje só PIS, Cofins e ISS: para o Anexo II o IPI precisa entrar). A natureza `substituto_st` vai ao segmento normal, como o catálogo já marca (`models.py:2691-2697`), e a receita do item já exclui o `vST` (HI-119). O catálogo de hoje não tem segmento combinado: a natureza é uma por item, então "ST + monofásico" exige ou uma natureza nova ou uma marca de monofásico ortogonal à natureza (recomendo a segunda: `monofasico` como atributo do item, decidido pelo NCM, independente da natureza de ICMS). Enquanto não houver tabela de NCM monofásico, o item marcado `monofasico` pelo contador vale; o não marcado é tratado como normal, que é o lado conservador (paga a mais, nunca a menos).

**Grau de segurança: alto** na regra; **médio** só na combinação no mesmo item, que não tem exemplo oficial (mas tem rotina explícita do Manual).

---

## 4. Anexo II (indústria)

**Resposta curta.** O Anexo II traz o IPI na repartição (7,50% nas cinco primeiras faixas; 35,00% na 6ª), e o IPI do optante está **dentro** do DAS. Na segregação: **ST desconsidera só o ICMS** (o IPI fica, porque não há substituição de IPI); **exportação desconsidera também o IPI** (o § 3º e o § 14 o listam expressamente); **monofásico desconsidera PIS e Cofins** (o § 6º fala em quem "industrializa"); a indústria é tipicamente o **substituto** do ICMS-ST, então o caso mais comum é operação própria no segmento normal e `vST` fora da receita. Nada mais muda: mesma fórmula, mesmo RBT12 total, sem teto.

**NORMA.** LC 123, art. 18, § 4º, II e § 5º; § 14 (IPI entre os "tão somente") — *lido*. Res. CGSN 140, art. 25, § 1º, II, § 3º (IPI), § 6º ("industrialização"), § 8º — *cópia*. Repartição do Anexo II — *lido* hoje no Planalto (item 1). O IPI dentro do Simples: LC 123, art. 13, II, citado como *lido* na consulta de 09/10 (não o reli hoje).

**ROTINA (Manual, *lido*).** Item 6.5: "3 - Venda de mercadorias industrializadas pelo contribuinte, exceto para o exterior" com e sem ST/monofásico/antecipação; "4 - ... para o exterior". Item 6.6.4: a opção monofásica se aplica à "atividade de venda de mercadorias industrializadas OU de revenda". Não há exemplo numérico do Anexo II.

**Proposta para o produto.** Nenhuma regra nova além do IPI no conjunto da exportação e da natureza `producao_propria` → Anexo II. Casos a recusar com nome no primeiro corte: "atividade com incidência simultânea de IPI e ISS" (Res. 140, art. 25, § 1º, VII: Anexo II sem ICMS mais ISS do Anexo III) e os itens II e III do § 17 (materiais produzidos em obra); são raros no acervo de um escritório comum. A NF-e de optante (CRT 1 ou 2) com `vIPI` destacado continua inconsistência a sinalizar (consulta de 09/10, item 3).

**Grau de segurança: alto.**

---

## 5. Devolução de venda deduzida no mês, com saldo

**Resposta curta.** A norma manda deduzir a devolução **dentro do segmento a que a mercadoria devolvida pertence**, pelas regras do mês da devolução — nem "proporcionalmente", nem "do total". O texto do art. 17, I, diz "deduzido da receita bruta total ... **segregada** pelas regras vigentes ... nesse mês", e o inciso II fala em saldo quando a devolução supera "a receita bruta total **ou das receitas segregadas**" do mês. O PGDAS-D não tem campo de devolução: o contribuinte informa a receita **de cada atividade e segregação já líquida** da devolução daquele tipo (inferência pela ausência do campo). Proporcional não tem base. O segmento da venda original **não é desconhecido**: o item da NF-e de devolução carrega CFOP, CSOSN/CST e NCM, e os CFOP de devolução de venda distinguem produção própria de revenda e ST de não ST.

**NORMA.** Res. CGSN 140, art. 17, I e II (texto acima) — *cópia*. LC 123, art. 3º, § 1º (vendas canceladas e descontos incondicionais não compõem a receita) — *lido* na consulta de 09/10. Tabela oficial de CFOP (Portal da NF-e, `indDevol` = 1) — *lido*:
- 1.201 / 2.201 / 3.201: "Devolução de venda de **produção do estabelecimento**" (→ Anexo II; 3.201 = devolução de exportação);
- 1.202 / 2.202 / 3.202: "Devolução de venda de **mercadoria adquirida ou recebida de terceiros**" (→ Anexo I);
- 1.410 / 2.410: devolução de venda de produção "em operação com produto sujeito ao regime de **substituição tributária**";
- 1.411 / 2.411: devolução de venda de mercadoria de terceiros "sujeita ao regime de substituição tributária";
- 1.660 a 1.662: devolução de venda de combustíveis.
O CFOP de ST na devolução não diz se a empresa era substituta ou substituída; isso vem do CSOSN/CST do item (500/60 = substituído, segmento `sujeita_st`; 201/202/203 ou 10/30/70 = substituto, segmento normal), do mesmo modo que na venda (HI-120). Monofásico: pelo NCM, como na venda.

**ROTINA (Manual, *lido*).** Nos itens 6.4 a 6.6 não existe campo de devolução no PGDAS-D; a palavra "devolução" só aparece na DEFIS (item 8: "Total de devoluções de vendas de mercadorias para comercialização ou industrialização"). Logo o aplicativo recebe a receita por atividade e segregação já deduzida — rotina inferida, não descrita.

**Proposta para o produto.**
1. A devolução recebe `(anexo, segmento)` **por item**, derivado dos mesmos sinais da venda: CFOP x.201/x.410 → Anexo II; x.202/x.411 → Anexo I; x.410/x.411 ou CSOSN 500/CST 60 → `sujeita_st`; CSOSN 201-203/CST 10-30-70 → normal; NCM → monofásico (quando houver tabela; antes disso, marcação do contador); CFOP 3.xxx → exportação (já feito, `models.py:2776-2787`). Sugerido e confirmado pelo contador como as demais naturezas (HI-118). Sinais conflitantes (ex.: CFOP 1.202 com item marcado produção) → sem sugestão; devolução sem segmento confirmado → **recusa nomeada** do pré-DAS daquele mês, nunca rateio silencioso.
2. O saldo do art. 17, II, passa a ser carregado **por `(mercado, anexo, segmento)`**, e não só por mercado como hoje (`apps/fiscal/receita.py:426-428` e `432-447`). Hipótese minha: o saldo de um segmento abate só receita futura **do mesmo segmento**; é a leitura literal de "receitas segregadas", mas não há exemplo oficial.
3. Ligar ao `NFref` da nota de origem fica como melhoria (hoje não é lido, `docs/planos/DL-081-escrituracao-das-nfe-de-saida.md:127`): serviria para **conferir** o segmento sugerido, não para substituí-lo, porque a devolução pode ser parcial e a origem pode ter vários itens.

**Grau de segurança: alto** na norma (dedução dentro do segmento); **médio** na mecânica do saldo por segmento e na rotina do PGDAS-D (inferida).

---

## 6. Sublimite estadual de R$ 3,6 milhões

**Resposta curta.** Sim, o primeiro corte recusa com nome, e isso está correto para comércio e indústria tanto quanto para serviços — a regra do ICMS é a mesma do ISS. Reafirmo a correção de premissa da consulta de 08/10: o que tira o ICMS do DAS é a **receita acumulada no ano (RBA)** acima do sublimite, com efeito no mês seguinte (excesso > 20%) ou no ano seguinte (≤ 20%); RBT12 acima de 3,6 mi com RBA dentro mantém o ICMS no DAS, pela fórmula da 5ª faixa. O código recusa nas três situações: `excesso_de_limite_ou_sublimite` (`apps/fiscal/pre_das.py:910-924`, a partir dos avisos de `rbt12.py:375-400`) e `rbt12_acima_do_primeiro_corte` por mercado (`pre_das.py:1050-1066`, limite `LIMITE_DO_PRIMEIRO_CORTE` = R$ 3.600.000,00). Nenhuma mudança é necessária na DL-082 além de manter essas recusas para as linhas de mercadoria.

**NORMA.** LC 123, art. 13-A ("Para efeito de recolhimento do ICMS e do ISS no Simples Nacional, o limite máximo ... será de R$ 3.600.000,00"), art. 19 e art. 20, §§ 1º e 1º-A — *lido*. Res. CGSN 140, art. 12, caput e § 1º, I e II (impedimento), art. 21, III, "b" (ICMS pela 5ª faixa quando RBT12 > 5ª faixa e sublimite não excedido), art. 22, § 5º (últimas faixas quando RBT12 > 4,8 mi e RBA dentro), art. 24, I, "b", 2 (parcela excedente com sublimite de 3,6 mi) — *cópia*. Sublimite de R$ 3,6 mi em todas as UFs em 2026: Portaria CGSN 54/2025, *cópia* na consulta de 08/10.

**ROTINA (Manual, *lido*).** Item 8.4: "Quando o sublimite é ultrapassado, o contribuinte não deve fazer nada em relação ao preenchimento do PGDAS-D, o próprio aplicativo identifica". Exemplos 9, 10 e 11 são os casos oficiais do ICMS acima do sublimite (item 8 abaixo), reservados para uma DL futura.

**Proposta para o produto.** Manter as recusas; registrar o excesso de sublimite/6ª faixa como **Fora do escopo** nomeado, com os exemplos 9, 10 e 11 do Manual como casos de referência da DL que vier a tratá-lo.

**Grau de segurança: alto.**

---

## 7. ICMS com benefício estadual (Res. 140, arts. 31 a 35) e o Tocantins

**Resposta curta.** O mecanismo nacional é claro: o Estado pode conceder isenção ou redução ao optante, mas **obrigatoriamente "na forma de redução do percentual efetivo do ICMS"** da tabela, com o percentual por faixa escrito na lei estadual; na isenção o percentual do ICMS é desconsiderado, na redução é reduzido proporcionalmente — e os federais não mudam. Para o Tocantins **não consegui ler a legislação** (SEFAZ-TO fora do ar). A única fonte que achei é uma notícia de 08/01/2024 dizendo que uma medida provisória alterou o art. 1º-A da Lei estadual 1.303/2002 para estender ao Simples uma redução de 75% (2024), 50% (2025) e 25% (2026) **"na base de cálculo da complementação de alíquota"** — isto é, do ICMS recolhido **por fora** do DAS (complementação/antecipação nas compras interestaduais), e não do percentual de ICMS dentro do DAS. Não encontrei indício de que o TO reduza o percentual efetivo do ICMS no DAS, mas não posso afirmar que não exista. **A recusa nomeada continua**, e precisa ganhar um gatilho que hoje não existe para NF-e.

**NORMA.**
- LC 123, art. 18, § 4º-A, III, §§ 20, 20-A, 20-B e 21 — *lido*.
- Res. CGSN 140, art. 31 (competência), art. 32, §§ 1º a 3º ("o benefício deve ser concedido na forma de redução do percentual efetivo do ICMS ou do ISS"; percentuais por faixa "devem constar da respectiva legislação"), art. 35, I e II (isenção → desconsiderar; redução → redução proporcional), art. 36 (cesta básica: Cofins, PIS e ICMS), art. 30 (imunidade: alíquota = soma dos demais) — *cópia*.
- Tocantins: Lei 1.303/2002, art. 1º-A, alterado por MP de janeiro de 2024 — *secundário* (https://conexaoto.com.br/2024/01/08/governo-mantem-reducao-da-base-de-calculo-do-icms-para-empresas-do-simples-nacional; a COAD devolveu 403). O arquivo da Assembleia que a busca apontou é a Lei 1.036/1998, revogada, sem relação. "Não foi possível confirmar a redação vigente do dispositivo. A conclusão deve ser validada diretamente na legislação oficial ou por consulta formal à SEFAZ/TO."

**ROTINA (Manual, *lido*).** Item 6.6.1: qualificação "Isenção/Redução: ICMS e ISS" e "Isenção/Redução Cesta Básica: ICMS" por tributo. Exemplo 12 (ISS, Campinas, redução de 50%) mostra a mecânica oficial: percentual efetivo do ISS 3,24090% × 0,5 = 1,62045%, elevado ao piso de 2% da LC 116; o mesmo desenho vale para ICMS, sem o piso de 2% (que é só do ISS, art. 31, parágrafo único).

**Proposta para o produto.** O catálogo da DL-081 **não tem natureza** para ICMS isento ou reduzido por lei estadual (as quatorze de `NaturezaOperacaoNFe`, `models.py:2639-2654`): um item com CSOSN 103 ("isenção do ICMS para faixa de receita bruta"), 300 (imune) ou 400 (não tributada) hoje cai em `revenda` e o pré-DAS calcularia ICMS cheio — conservador, mas divergente do PGDAS-D se houver benefício. Recomendo que o pré-DAS de mercadoria leia o `csosn` do item (`ItemNFe.csosn`, `models.py:3033`) e **recuse com nome** quando encontrar 103, 300 ou 400 ("benefício ou imunidade de ICMS sem parâmetro estadual com lei e vigência"), como `MOTIVO_FORA_DO_CORTE` faz com o ISS (`pre_das.py:179-188`); CSOSN 900 gera aviso. Parametrizar o benefício do TO só depois de ler a lei na SEFAZ-TO ou no Diário Oficial do Estado.

**Grau de segurança: alto** no mecanismo nacional; **baixo** no Tocantins.

---

## 8. Casos de referência para os testes

**Oficiais (Manual do PGDAS-D, item 12, *lido*; PA de 2018, tabelas iguais às de 2026).** Todos os valores abaixo foram reproduzidos hoje com as tabelas de `apps/fiscal/simples_tabelas.py` e `Decimal`, arredondando só o valor de cada tributo (`ROUND_HALF_UP`): bateram centavo a centavo.

| Ex. | Caso | Dados | Resultado oficial |
| --- | --- | --- | --- |
| 1 | Anexo I, 2ª faixa, revenda sem ST | RBT12 300.000; RPA 100.000; nominal 7,30%; PD 5.940 | efetiva 5,32%; IRPJ 292,60; CSLL 186,20; Cofins 677,77; PIS 146,83; CPP 2.207,80; ICMS 1.808,80; total 5.320,00 |
| 2 | **Mais de um anexo**, RBT12 único | RBT12 300.000; revenda 300.000 (I) + serviço 100.000 (III, sem fator r) | I: 5,32% → 877,80; 558,60; 2.033,30; 440,50; 6.623,40; 5.426,40 = 15.960,00. III: 8,08% → 8.080,00. Total 24.040,00 |
| 3 | Anexo I, início de atividade | aberta 01/2018; jan 10.000, fev 100.000, mar 100.000 | jan e fev: 4% → 400,00 e 4.000,00; mar: RBT12 prop. 660.000, 3ª faixa, 7,40% → IRPJ 407,00; CSLL 259,00; Cofins 942,76; PIS 204,24; CPP 3.108,00; ICMS 2.479,00 = 7.400,00 |
| 6 | **Exportação** de mercadoria, dois mercados | RBT12 int 2.000.000 (5ª faixa), RPA int 100.000; RBT12 ext 1.000.000 (4ª faixa), RPA ext 50.000 | int 9,935% → 546,43; 347,73; 1.265,72; 274,21; 4.172,70; 3.328,23 = **9.935,02**. ext 8,45% com Cofins, PIS e ICMS 0,00 → IRPJ 232,38; CSLL 147,88; CPP 1.774,50 = 2.154,76. Total 12.089,78 |
| 9, 10, 11 | ICMS acima do sublimite ou 6ª faixa (futuro) | ex. 10: RBT12 6.000.000, RBA 3.100.000, RPA 100.000, sublimite 3,6 mi | 6ª faixa 12,70% + ICMS pela 5ª 4,30308% = 17,00308% → 17.003,08 (ICMS 4.303,08). Ex. 9 usa sublimite de 1,8 mi (Acre), não vale para o TO em 2026. Ex. 11: impedimento após excesso > 20% |

**Não existe** exemplo oficial com ST, com monofásico, nem numérico do Anexo II (verificado nos exemplos 1 a 12). Os seguintes são ***calculados*** por mim hoje (alíquota efetiva conferida também pelo script da skill; repartição com as tabelas do repositório):

**D — Anexo I, 3ª faixa, com ST substituído e monofásico.** RBT12 600.000; nominal 9,50%; PD 13.860; efetiva **7,19%**. Receita do mês 50.000 = 30.000 normal + 12.000 ST substituído (CSOSN 500) + 8.000 monofásico.
- normal 30.000: IRPJ 118,64; CSLL 75,50; Cofins 274,80; PIS 59,53; CPP 905,94; ICMS 722,60 → 2.157,01
- ST 12.000: IRPJ 47,45; CSLL 30,20; Cofins 109,92; PIS 23,81; CPP 362,38; ICMS 0,00 → 573,76
- monofásico 8.000: IRPJ 31,64; CSLL 20,13; Cofins 0,00; PIS 0,00; CPP 241,58; ICMS 192,69 → 486,04
- **total 3.216,81**

**E — ST + monofásico no mesmo item** (mesma empresa): 5.000 → IRPJ 19,77; CSLL 12,58; Cofins 0,00; PIS 0,00; CPP 150,99; ICMS 0,00 → **183,34**.

**H — Substituto** (mesma empresa): operação própria 10.000 com `vST` 1.800 fora da receita → IRPJ 39,55; CSLL 25,17; Cofins 91,60; PIS 19,84; CPP 301,98; ICMS 240,87 → **719,01**; o ICMS-ST de 1.800 vai à SEFAZ por fora.

**F — Anexo II, 4ª faixa, com ST e exportação.** RBT12 int 900.000; nominal 11,20%; PD 22.500; efetiva **8,70%**. RBT12 ext 150.000 (1ª faixa, 4,50%).
- normal 40.000: IRPJ 191,40; CSLL 121,80; Cofins 400,55; PIS 86,65; CPP 1.305,00; IPI 261,00; ICMS 1.113,60 → 3.480,00
- ST substituído 10.000: IRPJ 47,85; CSLL 30,45; Cofins 100,14; PIS 21,66; CPP 326,25; IPI 65,25; ICMS 0,00 → 591,60
- exportação 20.000 (efetiva 4,50%): IRPJ 49,50; CSLL 31,50; Cofins 0,00; PIS 0,00; CPP 337,50; IPI 0,00; ICMS 0,00 → 418,50
- **total 4.490,10**

**G — Dois anexos com RBT12 único** (espelho do exemplo 2 com outros valores): RBT12 300.000; revenda 60.000 (I, 5,32%) → 175,56; 111,72; 406,66; 88,10; 1.324,68; ICMS 1.085,28 = 3.192,00; serviço 20.000 (III, 8,08%) → 64,64; 56,56; 227,05; 49,29; 701,34; ISS 517,12 = 1.616,00; **total 4.808,00**.

**Proposta para o produto.** Critérios de aceite: exemplos 1, 2, 3 e 6 do Manual centavo a centavo por tributo (o 6 inclusive no total **9.935,02**); D, E, F, G e H como *calculados*, com mutação (trocar o conjunto desconsiderado de qualquer segmento, somar o `vST` à receita, usar RBT12 por anexo em vez do total, ou redistribuir o ICMS desconsiderado deve derrubar teste).

**Grau de segurança: alto** nos oficiais; os calculados são hipótese de mecânica, coerentes com a norma e com a rotina do Manual.

---

## 9. Arredondamento (HI-71)

**Resposta curta.** Vale igual, e para os Anexos I e II a evidência oficial é **mais forte** do que era para serviços: o exemplo 6 do Manual dá o total interno como **9.935,02**, que é a soma dos seis tributos arredondados a centavo, e não 100.000 × 9,935% = 9.935,00; o exemplo 9 (P2) dá 21.722,10 pela soma contra 21.722,09 pelo produto. Ou seja, o PGDAS-D arredonda **cada tributo** e soma. O exemplo 1 mostra ainda que é arredondamento e não truncamento: Cofins 100.000 × 0,67777% = 677,768 → **677,77**. O que a norma e o Manual não dizem é o tratamento do meio-centavo exato (`HALF_UP` × `HALF_EVEN`); nenhum exemplo oficial cai nesse caso.

**NORMA.** Não há dispositivo de arredondamento na LC 123 nem na Res. 140 (verificado por busca em ambas). Manual, item 12: "O cálculo do valor devido no PGDAS-D considera todas as casas decimais. Neste manual, para fins didáticos, foi demonstrado até a 5ª casa decimal" — *lido*. Os totais dos exemplos 6 e 9 — *lido*.

**Proposta para o produto.** Manter `valor_do_tributo` e o total como soma (`pre_das.py:380-385` e `1163-1181`); trocar a marca de HI-71 de "hipótese sem exemplo" para "hipótese corroborada pelos exemplos 1, 6 e 9 do Manual (Anexo I)"; manter `ROUND_HALF_UP` como escolha do produto, registrando que o meio-centavo exato não tem exemplo oficial.

**Grau de segurança: alto** (arredondar por tributo e somar); **médio** no modo do meio-centavo.

---

## 10. Fora do primeiro corte: pendências nomeadas

Cada uma deve recusar o pré-DAS do mês com mensagem que nomeie o motivo, como a DL-075 faz:
1. RBT12 acima de R$ 3.600.000,00 (6ª faixa; ICMS pela 5ª faixa, art. 21, III, "b") e excesso de sublimite ou limite no ano (arts. 12 e 24). Casos oficiais futuros: exemplos 9, 10 e 11.
2. ICMS isento, reduzido, com valor fixo, imune ou cesta básica por lei estadual (arts. 30 a 36; CSOSN 103, 300, 400; qualificação "Isenção/Redução" do PGDAS-D). Tocantins a ler.
3. Combustíveis (natureza `combustivel`): ICMS fora do DAS (LC 123, art. 13, § 1º, XIII, "a") e PIS/Cofins concentrados. O catálogo marca a segregação como `normal` (`models.py:2705-2711`); o pré-DAS **não pode** calcular essa natureza como normal — recusar com nome até a regra (LC 192/2022, *não conferido*) ser lida.
4. Monofásico decidido por tabela de NCM com fonte e vigência (Leis 10.147, 10.485, 10.833 e 9.718, art. 4º); até lá, só marcação do contador.
5. Devolução sem segmento confirmado (item 5) e leitura do `NFref`.
6. Atividade com IPI e ISS simultâneos (art. 25, § 1º, VII), transporte intermunicipal/interestadual e comunicação (IX), medicamentos manipulados (§ 2º), consignação de veículos (§ 16), salão-parceiro (§ 18), materiais em obra (§ 17).
7. Serviço em NF-e conjugada (CFOP 5.933): continua fora do pré-DAS.
8. Comercial exportadora: a natureza existe e a segregação é a da exportação, mas o XML não prova o fim específico; exigir confirmação do contador antes de calcular.
9. Regime de caixa (HI-66), antecipação com encerramento quando não vier com CSOSN 500, e `vICMSDeson` que reduz o total (PE-85).
10. 2027: Res. CGSN 190/2026, IBS/CBS em `vProd` e novas tabelas (LC 214, arts. 519 a 534).

---

## Hipóteses para o Fred validar

1. Anexos I e II usam a mesma cadeia da DL-075 (alíquota efetiva, repartição, diferença centesimal), sem teto nem redistribuição; o anexo vem da natureza do item da NF-e, não da atividade padrão.
2. Empresa com vários anexos usa **um** RBT12 por mercado para todos; o fator r usa folha e receita da empresa inteira e decide só o anexo dos serviços do inciso V.
3. Segregação sem redistribuição: ST substituído tira ICMS; monofásico tira PIS e Cofins; exportação tira Cofins, PIS, IPI e ICMS; substituto é normal com `vST` fora; combinações são a união dos conjuntos.
4. "ST + monofásico" no mesmo item exige marca de monofásico ortogonal à natureza de ICMS (ou natureza combinada); recomendo a marca.
5. Devolução deduz **dentro do segmento** da mercadoria devolvida, derivado do item da devolução (CFOP x.201/x.410 = produção; x.202/x.411 = revenda; x.410/x.411 ou CSOSN 500 = ST; NCM = monofásico; CFOP 3.xxx = exportação); sem segmento confirmado, recusa; nunca rateio.
6. Saldo de devolução (art. 17, II) carregado por `(mercado, anexo, segmento)` e consumido só pelo mesmo segmento.
7. Itens com CSOSN 103, 300 ou 400 recusam o pré-DAS com nome ("benefício ou imunidade de ICMS sem parâmetro estadual").
8. Natureza `combustivel` recusa o pré-DAS com nome enquanto não houver regra de ICMS monofásico e PIS/Cofins concentrados.
9. HI-71 confirmada para os Anexos I e II pelos exemplos 1, 6 e 9 do Manual: arredondar cada tributo e somar; `ROUND_HALF_UP` continua escolha do produto.
10. Casos de teste: exemplos 1, 2, 3 e 6 do Manual (oficiais) e D, E, F, G, H (calculados).

## Pendências

1. Ler na SEFAZ-TO (ou no Diário Oficial do Estado) a Lei 1.303/2002, art. 1º-A, e confirmar se existe algum benefício do TO que reduza o **percentual efetivo do ICMS dentro do DAS** (arts. 31 a 35 da Res. 140) ou se o benefício noticiado alcança só a complementação de alíquota recolhida por fora. Portal inacessível em 08/10 e 09/10.
2. Confirmar no texto oficial da Res. CGSN 140 (SIJUT) os arts. 17, 21, 24, 25 (§§ 3º, 6º a 10) e 28, lidos em cópia.
3. Confirmar junto ao Portal do Simples Nacional (Perguntas e Respostas, não acessível em 08/10) a rotina de informar a receita líquida de devolução por atividade e segregação, que inferi da ausência de campo no PGDAS-D.
4. Montar a tabela de NCM monofásico com fonte e vigência antes de qualquer sugestão automática.
5. Decidir com o Fred se a DL-082 calcula a comercial exportadora após confirmação explícita ou a recusa no primeiro corte.
6. Ler a LC 192/2022 e o regime monofásico de ICMS dos combustíveis antes de liberar a natureza `combustivel` no pré-DAS.
7. Conciliar, na primeira empresa real com ST ou monofásico, o pré-DAS com o extrato do PGDAS-D, porque não há exemplo oficial desses segmentos.
8. Portaria CGSN 54/2025 (sublimites de 2026) continua em cópia; se sair portaria para 2027, revisar.

Sources: [Planalto, LC 123/2006](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) · [Manual do PGDAS-D e DEFIS, v. 17/06/2025 (RFB)](https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf) · [Res. CGSN 140/2018 consolidada, cópia](https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf) · [Res. CGSN 140/2018, página oficial sem texto renderizado](http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278) · [Conexão Tocantins, 08/01/2024, redução da base de cálculo para o Simples (secundário)](https://conexaoto.com.br/2024/01/08/governo-mantem-reducao-da-base-de-calculo-do-icms-para-empresas-do-simples-nacional) · [COAD, mesma notícia (403 hoje)](https://www.coad.com.br/home/noticias-detalhe/123677/tocantins-mantem-reducao-da-base-de-calculo-do-icms-para-empresas-do-simples-nacional) · [RICMS/TO, Decreto 2.912/2006 (inacessível hoje)](https://dtri.sefaz.to.gov.br/legislacao/ntributaria/decretos/Decreto2.912-06.htm)
