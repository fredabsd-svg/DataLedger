# Consulta ao contador-senior sobre a escrituração das NF-e — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Grau de segurança geral:** médio-alto para receita bruta, segregação do Simples e Presumido (textos lidos no Planalto e em cópia íntegra da Res. CGSN 140); baixo para a tabela de CFOP (CONFAZ inacessível hoje) e para ICMS-TO (SEFAZ-TO inacessível) · **Marcas:** *lido* = texto oficial lido hoje (Planalto, XSD PL 010f e MOC 7.0 já baixados do Portal da NF-e); *cópia* = cópia íntegra em site terceiro; *secundário* = fonte não oficial ou rotina; *não conferido* = conhecimento meu, a confirmar.

Tudo abaixo é hipótese para validação do Fred (AGENTS.md §10). O que o repositório já decidiu (DL-072 a DL-080) foi lido e é citado pelo caminho do arquivo.

**Fontes lidas hoje (com URL):**
- LC 123/2006, arts. 3º, 13, 18 — *lido*: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- Lei 9.430/1996, art. 25 — *lido*: https://www.planalto.gov.br/ccivil_03/leis/l9430.htm
- DL 1.598/1977, art. 12 — *lido*: https://www.planalto.gov.br/ccivil_03/decreto-lei/del1598.htm
- Lei 9.249/1995, arts. 15 e 20 — *lido*: https://www.planalto.gov.br/ccivil_03/leis/l9249.htm
- Lei 9.718/1998, arts. 2º e 3º — *lido*: https://www.planalto.gov.br/ccivil_03/leis/l9718compilada.htm
- Lei 10.147/2000, arts. 1º e 2º — *lido*: https://www.planalto.gov.br/ccivil_03/leis/l10147.htm
- LC 214/2025, arts. 343 a 348 — *lido*: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm
- Res. CGSN 140/2018 consolidada (arts. 2º, 16 a 18, 25, 28, 30 a 35) — *cópia* (PDF de 128 páginas, com as anotações da Res. 190/2026): https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf. O oficial em http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278 devolve só a casca da página, como em 08/10.
- XSD `leiauteNFe_v4.00.xsd` do PL 010f e MOC 7.0 Anexo I — *lido* (arquivos baixados do Portal da NF-e em 09/10/2026 pela pesquisa da DL-080, ainda no scratchpad).
- Portal da NF-e, aviso de 04/09/2026 "Informe Técnico 2023.002 v2.10 que divulga atualização na tabela de CFOP" — *lido* só o aviso: https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false&Informe=nCdXYyjCKQg=
- **Não alcançados:** CONFAZ (Convênio s/nº de 1970 e Ajuste SINIEF 07/01: `connection reset` em três URLs e 503 pelo WebFetch); `dtri.sefaz.to.gov.br` e `sefaz.to.gov.br` (sem resposta). Nenhum CFOP individual abaixo está marcado *lido* a não ser os que o MOC 7.0 transcreve.

---

## 1. Primeiro corte

**Resposta curta.** Escriturar primeiro as **saídas próprias** (empresa no papel de emitente, `tpNF` = 1, `finNFe` = 1, modelos 55 e 65) como receita bruta por natureza, **mais a devolução de venda recebida** (`finNFe` = 4), porque sem ela a receita fica superestimada e a norma manda deduzir. As **entradas de compra** (crédito de ICMS, custo, estoque) ficam só na recepção, como já estão. É o corte que cobre 611 das 618 notas do acervo e alimenta de imediato o RBT12 (DL-074) e, no Presumido, a atividade "comércio" da DL-079, que hoje recusa receita de NF-e por desenho (`docs/planos/DL-079-lucro-presumido-irpj-csll.md`, "Fica fora").

**NORMA.** Receita bruta do Simples: LC 123, art. 3º, § 1º (*lido*). Devolução deduz no mês em que ocorre: Res. CGSN 140, art. 17, I e II (*cópia*). Presumido deduz devoluções, vendas canceladas e descontos incondicionais: Lei 9.430, art. 25, I (*lido*). Nenhuma norma obriga a escriturar a entrada antes da saída; a ordem é decisão de produto.

**Proposta para o produto.** Uma DL "escrituração das NF-e de saída" no desenho da DL-072: rascunho → efetivada → estorno, natureza sugerida pelo XML e confirmada pelo contador, valores copiados do documento, cancelamento posterior vira pendência. Diferenças em relação à NFS-e: (a) a natureza é **por item**, não por nota, porque uma NF-e mistura CFOP e CST (DL-067 já previa "uma nota com mais de uma natureza divide-se por item", `docs/planos/DL-067-plano-do-modulo-fiscal.md:401`); a tela sugere uma natureza por grupo de itens com o mesmo sinal e o contador confirma em bloco; (b) a competência é o mês de `dhEmi` (não há `dCompet` na NF-e); (c) `EscrituracaoFiscal` é da NFS-e (`valor_servico`, `iss_retido`; `apps/fiscal/models.py:423-437`): a NF-e precisa de tabela própria de escrituração, como a DL-080 fez com o documento, e `receita.composicao_do_mes` (`apps/fiscal/receita.py:194-232`) passa a somar as duas fontes por mercado. NFC-e entra no mesmo fluxo: o MOC fixa `tpNF` = 1, `idDest` = 1 e `finNFe` = 1 para o modelo 65 (consulta de leiaute, seção 5, *lido*).

**Grau de segurança:** alto na ordem; alto na norma.

## 2. Natureza da operação na NF-e

**Resposta curta.** Catálogo fechado com **quatorze naturezas** de saída e devolução. Cada uma diz se compõe receita bruta, qual anexo do Simples e qual atividade de presunção. O XML **sugere** com força variável; o contador **confirma**. Onde o XML não basta (monofásico sem CST confiável, comercial exportadora, bonificação condicional), a sugestão fica em branco, como a DL-072 fez com "não incidência".

### Catálogo proposto

| # | Natureza | Sinal no XML que sugere | Receita bruta | Simples | Presumido |
| --- | --- | --- | --- | --- | --- |
| 1 | Venda de mercadoria adquirida de terceiros (revenda) | `tpNF` 1, `finNFe` 1; CFOP x.102 ou x.104 (*lido* no MOC, I08-150); CSOSN 101/102/900 ou CST 00/20 | Sim | Anexo I (LC 123, art. 18, § 4º, I) | Comércio 8/12 |
| 2 | Venda de produção própria | CFOP x.101 ou x.103 (*lido* no MOC); CRT 1 com CSOSN, ou CRT 3 com IPI destacado | Sim | Anexo II (art. 18, § 4º, II) | Indústria 8/12 |
| 3 | Revenda com ICMS-ST, substituído | **CSOSN 500** (CRT 1/2) ou **CST 60** (CRT 3); CFOP x.405 (*lido* no MOC) | Sim | Anexo I ou II, segregada "sujeita a ST": percentual do ICMS desconsiderado (Res. 140, art. 25, § 8º, I) | 8/12 |
| 4 | Venda como substituto tributário (ST retida na saída) | **CSOSN 201/202/203** ou **CST 10/30/70**; `vST` > 0; CFOP x.401/x.403 (*não conferido*) | Sim pela operação própria; **`vST` fora** (Res. 140, art. 28, § 4º) | Receita "não sujeita a ST" (art. 25, § 8º, II, a); o ICMS-ST vai à SEFAZ por fora (LC 123, art. 13, § 1º, XIII, a) | 8/12; `vST` fora (DL 1.598, art. 12, § 4º) |
| 5 | Venda de produto monofásico de PIS/Cofins | PIS/COFINS CST 04 (monofásico) ou 06 (alíquota zero) **sugere**; NCM na tabela decide; emitente do Simples costuma informar CST 49 ou 99, então o CST sozinho não serve | Sim | Segregada: PIS e Cofins desconsiderados (Res. 140, art. 25, §§ 6º e 7º) | 8/12 (PIS/Cofins a zero na revenda: Lei 10.147, art. 2º, *lido*, só fármacos e perfumaria) |
| 6 | Revenda de combustíveis | CFOP x.656 ou x.667 (*lido* no MOC); NCM 2710/2207 (*não conferido*); grupo `ICMS61`/`vICMSMono` | Sim | ICMS monofásico/ST fora do DAS (LC 123, art. 13, § 1º, XIII, a); PIS/Cofins concentrados | **1,6% IRPJ** (Lei 9.249, art. 15, § 1º, I) e **12% CSLL** |
| 7 | Exportação direta | **`idDest` = 3** e CFOP 7.xxx (MOC I08-30, *lido*); CST 41 | Sim, **mercado externo** | Segregada: Cofins, PIS, IPI, ICMS e ISS desconsiderados (Res. 140, art. 25, § 3º; LC 123, art. 18, § 14) | 8/12 |
| 8 | Venda a comercial exportadora com fim específico | CFOP 5.501/5.502 (*não conferido*); `idDest` 1 ou 2 | Sim | Mesma segregação da exportação (LC 123, art. 18, § 4º-A, IV); **o XML não prova o fim específico: sem sugestão** | 8/12 |
| 9 | Devolução de venda recebida | **`finNFe` = 4** em nota de terceiro em que a empresa é destinatária (CFOP x.201/x.202, *não conferido*), ou nota própria de entrada (`tpNF` 0, `finNFe` 4; CFOP 1.949/2.949 para não contribuinte, *lido* no MOC I08-140) | **Dedução** | Deduz no mês da devolução, pelas regras daquele mês, com saldo para os seguintes (Res. 140, art. 17) | Deduz do trimestre (Lei 9.430, art. 25, I) |
| 10 | Remessa, retorno, demonstração, conserto, armazém, mostruário | CFOP x.9xx exceto 5.929/5.933 (*não conferido* individualmente) | Não | Fora da base | Fora da base |
| 11 | Transferência entre estabelecimentos | Emitente e destinatário da mesma empresa (marca HI-111 da DL-080); CFOP x.151/x.152 (*não conferido*) | Não | Fora | Fora |
| 12 | Bonificação, doação, brinde, amostra grátis | CFOP x.910/x.911 (*não conferido*) | Não, **se incondicional** (Res. 140, art. 2º, § 5º, III e IV); **sem sugestão**, o contador atesta a condição | Fora | Fora (hipótese: DL 1.598 não trata; prática) |
| 13 | Nota referente a operação já registrada em NFC-e/cupom | CFOP 5.929 (*lido* no MOC I08-180, "lançamento relativo a Cupom Fiscal") | **Não** (a receita já entrou pela NFC-e) | Risco de duplicidade | Idem |
| 14 | Prestação de serviço em NF-e conjugada | CFOP 5.933 com grupo `ISSQN` (*lido* no MOC I08-160/170) | Sim, **mas é serviço** | Anexo III/IV/V e ISS; **fora do pré-DAS deste corte**, recusa nomeada | Serviços 32/32 |

Casos que o leitor marca e **não** escritura como receita neste corte (natureza "ajuste", com pendência): `finNFe` = 2 (complementar: só é receita se complementa valor; se complementa imposto, não; o contador decide), `finNFe` = 3 (ajuste: nunca receita), `finNFe` = 5 e 6 (nota de crédito e de débito, só modelo 55, só IBS/CBS, sem ICMS/PIS/Cofins pela regra B25-80 da NT 2026.008, *lido* ontem; sentido sempre do emissor; não compõem receita de 2026), venda de ativo imobilizado (CFOP x.551, *não conferido*; não é receita bruta do Simples, Res. 140, art. 2º, § 5º, I; no Presumido é ganho de capital, Lei 9.430, art. 25, II, § 1º) e faturamento para entrega futura com remessa posterior (CFOP 5.922 e 5.116/5.117, *não conferido*; a receita é uma só).

### Grupos de CFOP

O primeiro dígito está **confirmado no MOC 7.0** (*lido*, regras I08-10 a I08-50): 1, 2, 3 = entradas (interna, interestadual, exterior); 5, 6, 7 = saídas (interna, interestadual, exterior); CFOP iniciado por 7 exige `idDest` = 3, por 6 exige `idDest` = 2, por 5 exige `idDest` = 1. O autorizador rejeita a mistura, então o leitor pode confiar nessa coerência em nota autorizada.

Os subgrupos a seguir são **conhecimento meu, não conferido hoje** no Anexo do Convênio s/nº de 15/12/1970 (tabela dada pelo Ajuste SINIEF 07/2001 e alterada por ajustes posteriores): x.100 vendas de produção própria e de terceiros; x.150 transferências; x.200 (em **saída**) devolução de **compra**, logo não é receita e não é dedução de receita; x.250 energia; x.300 comunicação; x.350 transporte; x.400 operações com ST; x.500 exportação e comercial exportadora; x.550 ativo imobilizado e uso/consumo; x.650 combustíveis; x.900 outras saídas (remessas, retornos, bonificação, demonstração, 5.929 cupom, 5.933 serviço, 5.949 residual). Em **entrada**, 1.200/2.200 é devolução de **venda** (dedução) e 1.949/2.949 vale como devolução para não contribuinte (*lido*).

**NORMA da tabela.** Convênio s/nº de 15/12/1970, art. 5º e Anexo (CFOP), com a tabela vigente dada pelo Ajuste SINIEF 07/2001 e alterações — *não conferido hoje*: https://www.confaz.fazenda.gov.br/legislacao/convenios/1970/cvsn_70 (reset e 503). O Portal da NF-e publica uma **tabela de apoio** com indicadores `indNFe` e `indDevol` que o MOC cita (I08-04 e I08-140, *lido*) e que foi atualizada em 04/09/2026 pelo Informe Técnico 2023.002 v2.10 (*lido* o aviso; o arquivo não baixei).

**Proposta para o produto.** A tabela de CFOP entra como **dado com fonte e vigência**, importada do arquivo oficial do Portal da NF-e (que já traz `indDevol`), nunca digitada de memória. A natureza carrega "CFOPs permitidos" (DL-067:369) e a sugestão é por **combinação**: primeiro `finNFe`, depois CFOP, depois CST/CSOSN, depois NCM; conflito entre sinais (por exemplo CFOP x.102 com CSOSN 500) rebaixa a sugestão para "a classificar". Nenhuma natureza de "não receita" soma na mesma base que venda (regra já em `docs/projeto/paridade/fiscal.md:434`).

**Grau de segurança:** alto no desenho e no primeiro dígito; **baixo na descrição individual dos CFOP** até o CONFAZ voltar.

## 3. Simples Nacional: receita de mercadoria

**Resposta curta.** A receita bruta de uma NF-e de saída é, **por item**, `vProd` menos o **desconto incondicional** (`vDesc`), mais frete, seguro e outras despesas **cobradas do adquirente na nota** (hipótese); **fora** ficam o ICMS-ST retido (`vST`) e, se houver, IPI destacado. `vNF` não serve direto, porque soma `vST` e IPI. Para optante (CRT 1 ou 2), IPI destacado é inconsistência: o IPI está no DAS (Anexo II). Devolução **deduz no mês da devolução**; cancelamento deduz no **período de origem**. Os dois são diferentes e o código de hoje cita só o segundo.

**NORMA.**
- LC 123, art. 3º, § 1º (*lido*): receita bruta é "o produto da venda de bens e serviços nas operações de conta própria, o preço dos serviços prestados, o resultado nas operações em conta alheia e as demais receitas da atividade ou objeto principal", "não incluídas as vendas canceladas e os descontos incondicionais concedidos".
- Res. CGSN 140, art. 2º, § 4º (*cópia*): compõem também o custo do financiamento nas vendas a prazo, gorjetas, royalties e patrocínio; § 5º: não compõem a venda de ativo imobilizado, juros e multas de atraso, bonificação/doação/brinde incondicional sem contraprestação, amostra grátis, indenização por rescisão, rendimentos financeiros.
- Res. CGSN 140, art. 28, § 4º (*cópia*): para o substituto, "não será considerado receita de venda ou revenda de mercadorias o valor do tributo devido a título de substituição tributária".
- Res. CGSN 140, art. 16, § 3º (*cópia*): a receita é segregada na forma do art. 25 e **em bases distintas** para mercado interno e exportação (LC 123, art. 3º, § 15, *lido*).
- Res. CGSN 140, art. 17 (*cópia*): devolução de mercadoria em PA posterior deduz "no período de apuração do mês da devolução, segregada pelas regras vigentes nesse mês", com saldo para os meses seguintes; no caixa, limitada ao valor efetivamente devolvido.
- Res. CGSN 140, art. 18 (*cópia*): cancelamento deduz no período da tributação originária; nova emissão em substituição vai ao período da operação originária.
- Frete e seguro cobrados: **não há texto expresso**. Minha leitura: fazem parte do preço da operação ("produto da venda"); *não conferido* em solução de consulta.
- **Não existe art. 25-A na Res. CGSN 140.** O grep do PDF só encontra referências ao art. 25-A **da LC 123** (recolhimento por documento único). A segregação está toda no art. 25 (§§ 1º, 3º, 6º a 10) e no art. 28.

**Segregação por anexo e situação, e quem decide:**

| Situação | Dispositivo | O XML decide? |
| --- | --- | --- |
| Anexo I (revenda) × Anexo II (produção própria) | LC 123, art. 18, § 4º, I e II (*lido*); Res. 140, art. 25, § 1º, I e II | **Sugere forte** pelo CFOP x.101/x.103 × x.102/x.104; contador confirma |
| ICMS-ST, substituído | Res. 140, art. 25, § 8º, I (*cópia*); LC 123, art. 18, § 4º-A, I (*lido*) | **Sim**: CSOSN 500 |
| ICMS-ST, substituto | Res. 140, art. 25, § 8º, II, e art. 28 (*cópia*) | **Sim**: CSOSN 201/202/203 e `vST`; operação própria tributada normalmente, `vST` fora da receita |
| PIS/Cofins monofásico | Res. 140, art. 25, §§ 6º e 7º (*cópia*); LC 123, art. 18, § 4º-A, I e § 12 (*lido*); listas: Lei 10.147 (*lido*, fármacos e perfumaria), Lei 10.485 (autopeças), Lei 10.833, art. 58-A e seguintes (bebidas), Lei 9.718, art. 4º (combustíveis) — as três últimas *não conferidas* hoje | **Não com segurança**: CST 04/06 sugere; o decisor é o **NCM** contra tabela própria com vigência. Sem tabela, sem sugestão |
| Exportação | LC 123, art. 18, § 14 (*lido*); Res. 140, art. 25, § 3º (*cópia*) | **Sim** para direta (`idDest` 3, CFOP 7.xxx). **Não** para comercial exportadora |
| ICMS isento, reduzido ou com valor fixo por lei estadual | LC 123, art. 18, § 4º-A, III (*lido*); Res. 140, arts. 31 a 35 (*cópia*): o benefício vem "na forma de redução do percentual efetivo do ICMS" e precisa constar da lei estadual por faixa | CSOSN 103/300/400 **sugere**, mas a redução depende da lei do TO, que não li hoje. **Fora do corte, recusa nomeada**, como a DL-075 fez com ISS imune (`apps/fiscal/pre_das.py:179-188`) |
| Serviço em NF-e conjugada (5.933) | Res. 140, art. 25, § 1º, III a V | Natureza marcada; fora do pré-DAS de mercadorias |

**Memória de cálculo (Python, `Decimal`, executada hoje).** NF-e sintética de saída, CRT 1, quatro itens: revenda tributada R$ 1.000,00 com desconto R$ 50,00 e frete R$ 30,00; revenda ST substituído (CSOSN 500) R$ 800,00; revenda monofásico R$ 600,00; venda como substituto (CSOSN 201) R$ 500,00 com `vST` R$ 90,00. `vNF` = 2.970,00; receita bruta = **2.880,00** (= `vNF` − `vST`), segregada em 1.480,00 normal, 800,00 ST, 600,00 monofásico. Com RBT12 de R$ 500.000,00, Anexo I, 2ª faixa (nominal 7,30%, PD 5.940,00, repartição IRPJ 5,5%, CSLL 3,5%, Cofins 12,74%, PIS 2,76%, CPP 41,5%, ICMS 34%: tabela da DL-075, *não reconferida hoje no Planalto*), alíquota efetiva 6,112%; DAS por segmento: 90,47 + 32,27 + 30,99. Serve só para mostrar a mecânica; não é caso oficial.

**Proposta para o produto.** (a) Receita por item = `vProd` − `vDesc` + `vFrete` + `vSeg` + `vOutro`, conferida contra `vNF` − `vST` − `vIPI` − `vII` − `vIPIDevol` com tolerância zero; divergência bloqueia a efetivação (nunca um "ajuste" silencioso). (b) Devolução de venda com natureza própria e **sinal negativo no mês da devolução** (art. 17), com saldo a transportar quando exceder a receita do mês (art. 17, II); isto é regra nova em `receita.composicao_do_mes`, que hoje só conhece a dedução no período de origem (art. 18, `apps/fiscal/receita.py:21-24`). (c) Mercado interno × externo pela natureza, reaproveitando `mercado_da_natureza` (`apps/fiscal/models.py:400-410`), estendido ao catálogo novo. (d) Tabela de NCM monofásico como dado com fonte e vigência, só sugestão. (e) Pré-DAS de Anexos I e II com os segmentos ST e monofásico é **DL própria**, depois desta.

**Grau de segurança:** alto na composição e na segregação por ST, exportação e devolução; médio no frete e nas listas de monofásico; o benefício de ICMS do TO é pendência.

## 4. Lucro Presumido

**Resposta curta.** A NF-e de saída entra como receita bruta da atividade de presunção que o **contador escolheu para a empresa** (DL-079, HI-101): comércio/indústria/transporte de cargas 8% IRPJ e 12% CSLL; revenda de combustíveis "para consumo" 1,6% IRPJ e 12% CSLL. Deduzem-se **devoluções, vendas canceladas e descontos incondicionais**; **IPI e ICMS-ST não compõem** a receita (mero depositário); **ICMS próprio compõe**. A sugestão pelo CFOP x.656/x.667 para combustíveis é só sugestão: o percentual de 1,6% exige "revenda, para consumo", e distribuidor que vende a revendedor não está literalmente no inciso.

**NORMA.**
- Lei 9.430, art. 25, I (*lido*): percentuais do art. 15 da Lei 9.249 sobre a receita bruta do art. 12 do DL 1.598, "deduzida das devoluções e vendas canceladas e dos descontos incondicionais concedidos"; II: ganhos de capital e demais receitas, integrais.
- DL 1.598, art. 12 (*lido*): caput, I a IV (produto da venda, preço dos serviços, conta alheia, demais receitas da atividade); § 4º: "não se incluem os tributos não cumulativos cobrados, destacadamente, do comprador ou contratante pelo vendedor dos bens ou pelo prestador dos serviços na condição de mero depositário" (IPI e ICMS-ST); § 5º: "incluem-se os tributos sobre ela incidentes" (ICMS próprio, PIS, Cofins).
- Lei 9.249, art. 15, caput e § 1º, I e II, a (*lido*): 8% regra geral; 1,6% "revenda, para consumo, de combustível derivado de petróleo, álcool etílico carburante e gás natural"; transporte de carga 8%; art. 20 (*lido*): CSLL 12%, e 32% para as atividades do § 1º, III.
- Lei 9.718, art. 3º, § 2º, I (*lido*): PIS/Cofins cumulativos excluem vendas canceladas e descontos incondicionais (vale para a conferência até 12/2026).

**Memória.** NF-e de indústria CRT 3: `vProd` 10.000,00, `vDesc` 200,00, `vFrete` 100,00, `vIPI` 500,00, `vST` 300,00; `vNF` = 10.700,00; receita bruta para presunção = **9.900,00**; base IRPJ 8% = 792,00; base CSLL 12% = 1.188,00.

**Proposta para o produto.** A DL-079 já tem "atividade de presunção por empresa, com vigência e uma padrão" e recusa nota sem atividade. A NF-e escriturada entra na receita do trimestre pelo mês de `dhEmi`, pelo mesmo valor por item do Simples (sem `vST` nem `vIPI`), com devolução recebida como dedução no trimestre da devolução. Para combustíveis, a natureza 6 sugere a atividade "revenda de combustíveis" e a tela exige confirmação com a frase do inciso ("revenda, para consumo"). Venda de ativo imobilizado fica fora com a pendência "ganho de capital" já declarada na DL-079.

**Grau de segurança:** alto.

## 5. ICMS próprio do Tocantins

**Resposta curta.** A **apuração** (débito, crédito, DIFAL, ST, FECOEP, E110/E111) fica para etapa própria, na ordem da DL-067 (ICMS depende das entradas, que este corte não escritura). O que **não pode faltar agora** é guardar, **por item e em `Decimal`**, tudo o que a apuração vai ler, para não reabrir o XML depois: CFOP, NCM, CEST, `orig`, CST ou CSOSN, `modBC`, `vBC`, `pRedBC`, `pICMS`, `vICMS`, `vICMSDeson` e `motDesICMS`, `modBCST`, `pMVAST`, `pRedBCST`, `vBCST`, `pICMSST`, `vICMSST`, `vBCSTRet`/`vICMSSTRet` (CSOSN 500 e CST 60), `pCredSN`/`vCredICMSSN` (CSOSN 101/201: crédito que o adquirente do Simples pode transferir, LC 123, art. 23, *não conferido hoje*), `vFCP`/`vFCPST`, grupo `ICMSUFDest` (DIFAL), `cBenef`, grupo monofásico de combustíveis (`qBCMono`, `vICMSMono`), IPI (CST, `vBC`, `pIPI`, `vIPI`), PIS e Cofins (CST, `vBC`, alíquota, valor), `ISSQN` quando houver, e o grupo `IBSCBS` bruto. Mais `idDest`, `indFinal`, `indIEDest`, UF do destinatário e `CRT` do emitente, que decidem alíquota interestadual e DIFAL.

**NORMA.** "Não foi possível confirmar a redação vigente do dispositivo. A conclusão deve ser validada diretamente na legislação oficial ou por consulta formal à SEFAZ/TO." Os portais `dtri.sefaz.to.gov.br` e `sefaz.to.gov.br` não responderam hoje. A alíquota interna de 20% desde 01/01/2024 e o FECOEP de 2 pontos constam da DL-067 (`docs/planos/DL-067-plano-do-modulo-fiscal.md:439`) como *secundário* e não foram reconferidos. Os caminhos dos campos acima estão no XSD do PL 010f (*lido*; o repositório já cita as linhas na consulta de leiaute).

**Proposta para o produto.** Tabela de **itens** da NF-e com esses campos tipados (leitura sim, interpretação não), gravada na recepção ou na escrituração, mais a regra de validação do DL-067:415 ("CST ou CSOSN coerente com o CRT") em modo aviso. Nenhum cálculo de ICMS nesta DL.

**Grau de segurança:** alto na lista de campos (é o leiaute); legislação do TO não validada.

## 6. IBS/CBS em 2026

**Resposta curta.** **Não muda a receita** nem do Simples nem do Presumido em 2026. É ano de teste: CBS 0,9% e IBS 0,1%, compensáveis com PIS/Cofins, com **recolhimento dispensado** para quem cumpre as obrigações acessórias, e as alíquotas de 2026 **não se aplicam ao optante do Simples**. Para o cliente do Presumido o que vale é a **conformidade do destaque** (validador em modo aviso, já recomendado em 08/10); para o do Simples, `IBSCBSTot` em nota de 2026 é anomalia a sinalizar. A partir de 2027 o quadro muda (IBS/CBS passam a compor `vProd`, NT 2026.008), e isso é pendência.

**NORMA.** LC 214, art. 343 (IBS 0,1% em 2026), art. 346 (CBS 0,9%), art. 348, I (compensação com PIS/Cofins "no mesmo período de apuração"), II (saldo compensável com outro tributo federal ou ressarcido em 60 dias), III, c (as alíquotas de 2026 "não serão aplicadas em relação às operações dos contribuintes optantes pelo Simples Nacional"), § 1º ("fica dispensado o recolhimento do IBS e da CBS... para os sujeitos passivos que cumprirem as obrigações acessórias"), § 2º (a dispensa não afasta o pagamento integral de PIS/Cofins) — tudo *lido*. Receita bruta: DL 1.598, art. 12, § 4º (*lido*): tributo não cumulativo cobrado destacadamente como mero depositário não compõe a receita; IBS e CBS são não cumulativos e destacados, logo ficam fora (inferência jurídica minha, sem solução de consulta, *não conferido*). Em 2026 `vNF` não inclui IBS/CBS; o total "por fora" é `vNFTot` (NT 2025.002, *lido* ontem pela pesquisa da DL-080, seção 4). CRT 1, 2 e 4 só terão regra em NT futura e tributação a partir de 2027 (NT 2025.002, *lido* ontem).

**Proposta para o produto.** Manter a política da DL-080 (guardar presença e XML, não interpretar), acrescentando três avisos na escrituração: grupo presente em nota de CRT 1/2/4 em 2026; grupo ausente em nota de CRT 3 emitida a partir de 03/08/2026; `vNFTot` diferente de `vNF` + IBS + CBS + IS. Nada entra na receita.

**Grau de segurança:** alto na dispensa e na não aplicação ao Simples; médio na fundamentação "fora da receita" no Presumido.

## 7. Rotina do escritório que o produto deve espelhar

**Resposta curta.** No sistema de referência o contador **importa o XML**, e a importação atribui o **acumulador** por uma regra "CFOP → acumulador" (e, quando configurado, por CST e produto); o contador revisa as exceções e corrige **em massa**. As conferências que ele espera, pela ordem em que usa no fechamento: (1) **resumo por acumulador e por CFOP e alíquota** do mês; (2) **notas importadas e não lançadas** ("notas não lançadas"); (3) **canceladas** separadas das válidas, com a nota que ficou lançada depois de cancelada em destaque; (4) **faturamento do mês** contra o que vai ao PGDAS-D, com a **receita bruta acumulada** (RBT12); (5) divergência entre total da nota e soma dos itens.

**NORMA.** Não há. É rotina, documentada no mapa funcional a partir do manual de 2018: `docs/projeto/mapa-funcional-fiscal.md:34-50` (classificação dirige cálculo), `:103-115` (importação, conferência, alteração em massa, rastreio até o documento) e `:311` (relatórios de "conferência de entradas, saídas...; faturamento; receita bruta acumulada do Simples; resumo por acumulador e por CFOP e alíquota; notas não lançadas"). Marca: *secundário*. A consulta de 08/10 (item 1, `docs/projeto/consultas/2026-10-08-contador-senior-fiscal.md:37`) já registrou que "acumulador errado" é a principal fonte de erro.

**Proposta para o produto.** Relatório de conferência da NF-e (classe conferência, `docs/projeto/personalizacao-de-relatorio.md`) com: receita por natureza e por CFOP; recebidas × escrituradas × pendentes por empresa e mês (como a DL-072, item 6); canceladas e "escriturada e cancelada depois"; itens com sugestão em branco; e **reclassificação em massa por filtro** (CFOP, CST, NCM, período) com trilha, que é a função que mais economiza tempo e o mapa já pede.

**Grau de segurança:** alto (produto e prática).

## 8. Fora do primeiro corte, como pendência nomeada

1. Escrituração das **entradas** (compras, crédito de ICMS/IPI/PIS/Cofins, custo, estoque, uso e consumo, ativo).
2. **Apuração de ICMS-TO** (próprio, ST, DIFAL, FECOEP, antecipação do Simples, CIAP) e EFD ICMS/IPI; legislação do TO a validar na SEFAZ.
3. **Pré-DAS de comércio e indústria** (Anexos I e II) com os segmentos ST, monofásico e exportação de mercadoria; o pré-DAS atual é só de serviços (`apps/fiscal/pre_das.py:161-166`).
4. **Benefício estadual de ICMS no Simples** (isenção, redução, valor fixo; Res. 140, arts. 31 a 35) e no regime normal (`cBenef`).
5. **Tabela oficial de CFOP** importada do arquivo do Portal da NF-e e conferida no Anexo do Convênio s/nº de 1970 quando o CONFAZ responder.
6. **Tabela de NCM monofásico** de PIS/Cofins com fonte e vigência (Leis 10.147, 10.485, 10.833 e 9.718, art. 4º).
7. **Combustíveis**: regime monofásico de ICMS (LC 192/2022, *não conferido*), campos `ICMS61`/`vICMSMono`, e a leitura literal de "revenda, para consumo" do 1,6%.
8. **Nota complementar, de ajuste, de crédito e de débito** (`finNFe` 2, 3, 5 e 6) como ajustes de valor e de IBS/CBS.
9. **Venda para entrega futura** e **venda à ordem** (receita única, duas notas).
10. **Venda de ativo imobilizado** e ganho de capital no Presumido.
11. **Serviço em NF-e conjugada** (5.933) no pré-DAS e no ISS.
12. **Regime de caixa** (Simples 2026 e Presumido): sem contas a receber, segue bloqueado.
13. **Manifestação do destinatário** como ação do usuário.
14. **2027**: IBS/CBS compondo `vProd` (NT 2026.008), Res. CGSN 190/2026 (Simples com IBS/CBS) e o comportamento de `vNF`.
15. **Integração contábil** do lançamento fiscal (HI-01, BL-72).

---

## Hipóteses para o Fred validar

1. Primeiro corte = saídas próprias (emitente, `tpNF` 1, `finNFe` 1, modelos 55 e 65) mais devolução de venda recebida (`finNFe` 4); compras só na recepção.
2. Natureza da NF-e é **por item**, sugerida pela combinação `finNFe` → CFOP → CST/CSOSN → NCM, confirmada em bloco pelo contador; conflito de sinais deixa a sugestão em branco.
3. Catálogo de quatorze naturezas da seção 2; `finNFe` 2, 3, 5 e 6, ativo imobilizado e entrega futura ficam marcados como "ajuste", fora da receita, com pendência.
4. Receita bruta por item = `vProd` − `vDesc` + `vFrete` + `vSeg` + `vOutro`; `vST`, `vIPI` e `vII` fora; a soma tem de bater com `vNF` menos esses valores, senão bloqueia.
5. Frete, seguro e outras despesas cobradas na nota compõem a receita bruta do Simples e do Presumido (sem texto expresso).
6. Devolução de venda deduz no **mês da devolução** (Res. 140, art. 17), com saldo transportado; cancelamento continua no período de origem (art. 18). Regra nova para `receita.composicao_do_mes`.
7. ICMS-ST retido pelo substituto do Simples (`vST`) não é receita (Res. 140, art. 28, § 4º); a operação própria é tributada normalmente no DAS.
8. CSOSN 500 decide "ICMS-ST substituído"; CSOSN 201/202/203 decide "substituto"; `idDest` 3 decide exportação direta; comercial exportadora e monofásico exigem o contador (o CST de PIS da nota do Simples não é confiável).
9. Benefício estadual de ICMS (CSOSN 103/300/400) é natureza marcada e recusa nomeada no pré-DAS, até a lei do TO ser lida.
10. No Presumido, a NF-e entra pela atividade de presunção da empresa; combustíveis a 1,6% só com confirmação explícita de "revenda, para consumo".
11. IBS/CBS de 2026 não entram na receita de nenhum regime; `IBSCBSTot` em nota de CRT 1/2/4 gera aviso.
12. Nota com CFOP 5.929 (operação já registrada em NFC-e/cupom) não é receita nova.
13. Bonificação, doação e brinde só saem da receita quando o contador atesta que são incondicionais (Res. 140, art. 2º, § 5º, III).
14. Campos por item da seção 5 são gravados já nesta etapa, em `Decimal`, sem interpretação.
15. NFC-e segue o mesmo fluxo da NF-e de saída (o MOC fixa `tpNF` 1, `idDest` 1, `finNFe` 1 no modelo 65).

## Pendências

1. Ler o Anexo do Convênio s/nº de 15/12/1970 e o Ajuste SINIEF 07/2001 no CONFAZ (inacessível hoje) e baixar a tabela de apoio de CFOP do Portal da NF-e (Informe Técnico 2023.002 v2.10, de 04/09/2026) antes de gravar qualquer descrição de CFOP.
2. Ler no RICMS/TO (Decreto 2.912/2006) e na Lei 1.287/2001 os dispositivos de alíquota interna, FECOEP, ST e benefícios ao Simples (SEFAZ-TO inacessível hoje).
3. Confirmar no texto oficial da Res. CGSN 140 (portal da Receita só renderiza com JavaScript) os arts. 2º, 17, 18, 25 e 28 lidos em cópia.
4. Confirmar a composição da receita com frete/seguro/outras despesas em solução de consulta Cosit ou no Manual do PGDAS-D.
5. Montar a tabela de NCM monofásico com as quatro leis (só a 10.147 foi lida hoje).
6. Decidir com o Fred se o cliente de combustíveis é posto (revenda para consumo, 1,6%) ou distribuidor.
7. Confirmar no acervo real como chega a devolução de venda (nota do cliente com a empresa como destinatária, ou nota própria de entrada) e se as 7 NF-e de entrada do acervo são isso.
8. Reconferir no Planalto a repartição do Anexo I usada na memória de cálculo (veio da tabela cadastrada na DL-075).
9. Comportamento de `vNF`, `vProd` e da receita bruta a partir de 2027 (NT 2026.008) e Res. CGSN 190/2026, antes de qualquer competência de 2027.
10. Decidir se a DL-079 passa a aceitar receita de NF-e já nesta etapa ou na seguinte (hoje recusa por desenho).

Sources: [Planalto, LC 123/2006](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) · [Planalto, Lei 9.430/1996](https://www.planalto.gov.br/ccivil_03/leis/l9430.htm) · [Planalto, DL 1.598/1977](https://www.planalto.gov.br/ccivil_03/decreto-lei/del1598.htm) · [Planalto, Lei 9.249/1995](https://www.planalto.gov.br/ccivil_03/leis/l9249.htm) · [Planalto, Lei 9.718/1998](https://www.planalto.gov.br/ccivil_03/leis/l9718compilada.htm) · [Planalto, Lei 10.147/2000](https://www.planalto.gov.br/ccivil_03/leis/l10147.htm) · [Planalto, LC 214/2025](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm) · [Res. CGSN 140/2018 consolidada (cópia)](https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf) · [Portal da NF-e, Informe sobre a tabela de CFOP](https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false&Informe=nCdXYyjCKQg=) · [CONFAZ, Convênio s/nº 1970 (não alcançado)](https://www.confaz.fazenda.gov.br/legislacao/convenios/1970/cvsn_70)
