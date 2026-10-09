# Consulta ao contador-senior sobre a leitura oficial da virada de 2027 no Simples — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Escopo:** HI-144 e pendências P1–P4 da consulta de 09/10 (classificação fiscal) · **Grau de segurança:** alto nos itens marcados *lido* (texto oficial baixado hoje por curl e extraído por script); médio onde há *cópia* ou *secundário*.

**Marcas.** *lido* = texto oficial (DOU em in.gov.br; Planalto) baixado hoje · *cópia* = cópia íntegra em terceiro · *secundário* = notícia/artigo · *código* = arquivo e linha do repositório · *não conferido* = conhecimento meu, sem leitura hoje.

**Resumo em três frases.** (1) A **Res. CGSN 190/2026 foi lida no texto oficial do DOU, com os cinco Anexos novos** — P1 e P2 estão resolvidas, e as tabelas de 2027-2028 abaixo são dado oficial pronto para `simples_tabelas.py`. (2) Há **duas mudanças de regra que o código não tem**: o RBT12 passa a ser os 12 meses **antecedentes ao mês anterior** ao PA (defasagem de um mês, na **LC** e na Resolução), e o início de atividade vira "1ª faixa nos meses 1-2; média × 12 do 3º ao 13º mês". (3) P3 (NF-e) está **meio resolvida** (o leiaute está lido; a regra de receita, não) e P4 (alíquota de referência da CBS) **continua pendente** por fato: o Senado ainda não publicou a resolução, e para o optante do Simples no regime único ela **não importa** — CBS e IBS saem dos Anexos.

---

## 1. Res. CGSN 190, de 04/08/2026 — texto oficial e Anexos I a V

### O que li

| Fonte | URL | Marca |
| --- | --- | --- |
| Res. CGSN 190/2026, DOU 10/08/2026, **Edição 149-A, Seção 1 – Extra A** | https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-190-de-4-de-agosto-de-2026-724454118 | **lido** (HTML da Imprensa Nacional; rodapé "não substitui a versão certificada") |
| Mesma resolução, PDF do DOU em terceiro (8 p.) | reformatributaria.com (…/Resolucao-CGSN-no-190…DOU-Imprensa-Nacional.pdf) | cópia (usada só para conferir que o HTML estava completo) |
| Cópia normaslegais (a da consulta anterior) | normaslegais.com.br/legislacao/Resolucao-cgsn-190-2026.htm | cópia — **confirmado que termina no art. 6º, sem os Anexos** |
| Res. CGSN 186/2026 (DOU) | in.gov.br/…/resolucao-cgsn-n-186-de-9-de-abril-de-2026-700230741 | lido |
| Res. CGSN 191, 192, 193 (DOU 10/08/2026) e **194 (25/09/2026, DOU 28/09/2026, Ed. 183-C Extra C)** | in.gov.br/…/resolucao-cgsn-n-19{1,2,3}-de-4-de-agosto-de-2026-…; …/resolucao-cgsn-n-194-de-25-de-setembro-de-2026-735097948 | lido |

Busca no DOU por "Resolução CGSN" (hoje): a mais recente é a **194**. Não há 195 ou 196 publicadas até 09/10/2026 (verificado na busca do in.gov.br; o portal do Simples e o `normas.receita` não renderizaram sem JS).

Arquivos baixados: `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/virada2027/` (`dou_res190.txt`, `dou_res186.txt`, `dou_res191..194.txt`, `anexo_I..V_parsed.txt`, `lcp123.txt`, `lcp214.txt`, `lcp227.txt`). Scripts em `…/scratchpad/virada2027_scripts/`.

### Vigência e estrutura (lido)

- **Art. 9º:** entra em vigor na publicação e **produz efeitos a partir de 01/01/2027**.
- **Art. 6º:** os Anexos I a V da Res. 140 passam a vigorar com a redação dada (tabelas por vigência: 2027-2028; 2029; 2030; 2031; 2032; 2033).
- **Art. 7º:** inclui o Anexo XIII na Res. 140 (valores fixos do MEI: 2027-2028 ICMS R$ 1,00, ISS R$ 5,00, CBS R$ 0,994, IBS R$ 0,006, total R$ 7,00).
- **Art. 8º, XIV: revoga o § 3º do art. 22 da Res. 140** (a regra "2º ao 12º mês = média × 12" do código atual). Revoga também o § 1º do art. 18 e os §§ 4º e 4º-A do art. 25, entre outros.

### Dispositivos pedidos (lido no DOU)

**Art. 4º (tributos do DAS):** "… IX - Contribuição sobre Bens e Serviços (CBS); e X - Imposto sobre Bens e Serviços (IBS)." Revogados os incisos IV e V (Cofins e PIS). **Art. 5º** (fora do DAS): "XVI - CBS e IBS apurados e recolhidos de acordo com o regime regular…; XXI - CBS e IBS nas operações sujeitas ao regime de tributação concentrada em uma única etapa (monofásica); XXII - tributos devidos … na condição de substituto ou responsável".

**Art. 21, II, "a" (nova definição de RBT12):** "RBT12: receita bruta acumulada nos doze meses **antecedentes ao mês anterior** ao do período de apuração". **Art. 21, III:** teto do ISS em 5%, "eventual diferença será transferida, de forma proporcional, aos tributos federais **e IBS** da mesma faixa". **Art. 21, IV:** RBT12 acima da 5ª faixa → ICMS, ISS e IBS pela fórmula {[(RBT12 × alíquota nominal da 5ª faixa) − parcela a deduzir da 5ª faixa]/RBT12} × percentual de distribuição da 5ª faixa.

**Art. 22, § 2º (início de atividade no ano da opção):** "I - no 1º e 2º mês de atividade, as alíquotas previstas na **primeira faixa** dos anexos I a V; e II - do **3º ao 13º mês** de atividade, como RBT12 …, a **média aritmética da receita bruta total auferida nos meses antecedentes ao mês anterior** do período de apuração, multiplicada por 12." **§ 4º:** abertura no ano anterior ao da opção: "I - as regras do § 2º até completar 13 meses de atividade; II - a regra do § 1º a partir do 14º mês". **§ 5º, I:** "nos 12 meses antecedentes ao mês anterior ao do período de apuração for superior a qualquer um dos limites…".

**Art. 22-A:** optante que exerceu a opção do art. 40-C (regime regular de IBS/CBS) apura o DAS "na forma do art. 22, **deduzidas as parcelas correspondentes à CBS e ao IBS** previstas para a faixa". Parágrafo único: a dedução não dispensa a apuração/recolhimento pelo regime regular.

**Art. 25** (segregação): § 1º, **I-A** — bens materiais com IBS/CBS e sem ICMS → Anexo I **deduzida a parcela do ICMS**; **II** — mercadorias industrializadas **sujeitas ao IPI mantido** (ADCT art. 126, III, "a" — ZFM) → Anexo II; **X** — serviços e bens imateriais com IBS/CBS e sem ISS/ICMS → Anexo III **deduzida a parcela do ISS**. **§ 3º** (exportação): desconsiderados "os percentuais relativos ao **IBS, à CBS, ao IPI, ao ICMS e ao ISS**". **§ 6º (novo):** quem importa, industrializa ou comercializa produto com **tributação concentrada ou ST de IBS/CBS** segrega a receita e indica isso, "de forma que serão desconsiderados … os percentuais a elas correspondentes". **§ 8º, I:** substituído e antecipação com encerramento segregam como "sujeita à ST ou ao recolhimento antecipado do ICMS, do IBS ou da CBS".

**Art. 38-B:** a DEFIS passa a ser prestada "uma única vez **no PGDAS-D, de janeiro a março** de cada ano" (§ 1º); eventos especiais no PGDAS-D do mês do evento (§ 2º).

**Arts. 40-C e 40-D:** faculdade de recolher IBS/CBS pelo regime regular; opção/renúncia **irretratável por semestre**, no Portal: **01 a 30/09** (efeitos 01/01 seguinte) e **01 a 31/03** (efeitos 01/07); cancelável até **30/11** e **31/05**, respectivamente. **Art. 40-E:** vedado voltar ao regime único a quem recebeu ressarcimento de crédito de IBS/CBS no ano corrente ou anterior (LC 214 art. 41 § 5º).

**Arts. 144-D e 144-E (transição, relevantes para o escritório):** quem entra no Simples em 01/01/2027 vindo de outro regime (ou do SIMEI) informa receita e folha anteriores no módulo **"Receitas Anteriores à Opção" do PGDAS-D**; competências **12/2025 a 11/2026 até 20/12/2026**; competência 12/2026 até 20/01/2027. Sem manifestação, vale o pré-preenchimento da RFB "inclusive para o cálculo da alíquota efetiva **a ser disponibilizada aos emissores de documentos fiscais**". (Repare: a janela 12/2025–11/2026 é exatamente a do novo RBT12 para o PA 01/2027 — confirma a leitura da defasagem.)

**Res. 194/2026 (altera a 186):** para 2027, opção pelo Simples **01/09 a 15/10/2026** (cancelamento 03/11 a 20/12/2026); opção pelo **regime regular de IBS/CBS para jan-jun/2027: 01/09 a 30/10/2026** (cancelamento 03/11 a 20/12/2026). Isso **substitui** a janela "setembro" que a consulta de 09/10 registrou para este primeiro ciclo. **Res. 191:** NFS-e nacional obrigatória para ME/EPP a partir de **01/11/2026** (revoga a 189). **Res. 192:** arrecadação/partilha ao CGIBS (Res. 11). **Res. 193:** regimento interno.

### Anexos I a V — vigência 01/01/2027 a 31/12/2028 (lido, DOU; números oficiais)

Faixas de RBT12 iguais para os cinco anexos: 1ª até 180.000,00 · 2ª 180.000,01–360.000,00 · 3ª 360.000,01–720.000,00 · 4ª 720.000,01–1.800.000,00 · 5ª 1.800.000,01–3.600.000,00 · 6ª 3.600.000,01–4.800.000,00.

**Anexo I — Comércio**

| Faixa | Alíq. nominal | Deduzir (R$) | IRPJ | CSLL | CBS | CPP | ICMS | IBS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1ª | 4,00% | – | 5,50% | 3,50% | 15,33% | 41,50% | 34,00% | 0,17% |
| 2ª | 7,30% | 5.940,00 | 5,50% | 3,50% | 15,33% | 41,50% | 34,00% | 0,17% |
| 3ª | 9,50% | 13.860,00 | 5,50% | 3,50% | 15,33% | 42,00% | 33,50% | 0,17% |
| 4ª | 10,70% | 22.500,00 | 5,50% | 3,50% | 15,33% | 42,00% | 33,50% | 0,17% |
| 5ª | 14,30% | 87.300,00 | 5,50% | 3,50% | 15,33% | 42,00% | 33,50% | 0,17% |
| 6ª | **18,90%** | 378.000,00 | 13,58% | 10,06% | 34,02% | 42,34% | – | – |

Nota do anexo: RBT12 acima da 5ª faixa, parcela até o sublimite: ICMS = {[(RBT12 × 14,30%) − 87.300,00]/RBT12} × 33,50%; IBS = idem × 0,17%.

**Anexo II — Indústria** (só IPI mantido — ZFM; a indústria em geral vai ao Anexo I, art. 25 § 1º I e II; LC 123 art. 18 § 5º na redação da LC 214)

| Faixa | Alíq. nominal | Deduzir (R$) | IRPJ | CSLL | CBS | CPP | IPI | ICMS | IBS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1ª–5ª | 4,50% / 7,80% / 10,00% / 11,20% / 14,70% | – / 5.940,00 / 13.860,00 / 22.500,00 / 85.500,00 | 5,50% | 3,50% | 13,85% | 37,50% | 7,50% | 32,00% | 0,15% |
| 6ª | **29,90%** | 720.000,00 | 8,53% | 7,53% | 25,22% | 23,59% | 35,13% | – | – |

Nota: ICMS = {[(RBT12 × 21%) − 125.640,00]/RBT12} × 33,50% (assim está no DOU — a fórmula do ICMS no Anexo II usa os parâmetros da 5ª faixa do **Anexo III**; registro como está, sem corrigir); IBS = {[(RBT12 × 14,70%) − 85.500,00]/RBT12} × 0,15%.

**Anexo III — Serviços (inciso III do § 1º do art. 25; inciso V com fator r ≥ 28%)**

| Faixa | Alíq. nominal | Deduzir (R$) | IRPJ | CSLL | CBS | CPP | ISS (*) | IBS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1ª | 6,00% | – | 4,00% | 3,50% | 15,43% | 43,40% | 33,50% | 0,17% |
| 2ª | 11,20% | 9.360,00 | 4,00% | 3,50% | 16,91% | 43,40% | 32,00% | 0,19% |
| 3ª | 13,50% | 17.640,00 | 4,00% | 3,50% | 16,41% | 43,40% | 32,50% | 0,19% |
| 4ª | 16,00% | 35.640,00 | 4,00% | 3,50% | 16,41% | 43,40% | 32,50% | 0,19% |
| 5ª | 21,00% | 125.640,00 | 4,00% | 3,50% | 15,43% | 43,40% | 33,50% (*) | 0,17% |
| 6ª | **32,90%** | 648.000,00 | 35,09% | 15,04% | 19,29% | 30,58% | – | – |

(*) Teto do ISS 5%: na 5ª faixa, alíquota efetiva **superior a 14,92537%** → ISS fixo em 5% e (alíq. efetiva − 5%) × **IRPJ 6,02% · CSLL 5,26% · CBS 23,20% · CPP 65,26% · IBS 0,26%**. Nota do sublimite: ISS = {[(RBT12 × 21%) − 125.640,00]/RBT12} × 33,50%; IBS idem × 0,17%.

**Anexo IV — Serviços do inciso IV do § 1º do art. 25 (sem CPP no DAS)**

| Faixa | Alíq. nominal | Deduzir (R$) | IRPJ | CSLL | CBS | ISS (*) | IBS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1ª | 4,50% | – | 18,80% | 15,20% | 21,26% | 44,50% | 0,24% |
| 2ª | 9,00% | 8.100,00 | 19,80% | 15,20% | 24,73% | 40,00% | 0,27% |
| 3ª | 10,20% | 12.420,00 | 20,80% | 15,20% | 23,74% | 40,00% | 0,26% |
| 4ª | 14,00% | 39.780,00 | 17,80% | 19,20% | 22,75% | 40,00% | 0,25% |
| 5ª | 22,00% | 183.780,00 | 18,80% | 19,20% | 21,76% | 40,00% (*) | 0,24% |
| 6ª | **32,90%** | 828.000,00 | 53,71% | 21,59% | 24,70% | – | – |

(*) Teto do ISS 5%: 5ª faixa com alíquota efetiva **superior a 12,5%** → ISS 5% e (alíq. efetiva − 5%) × **IRPJ 31,33% · CSLL 32,00% · CBS 36,27% · IBS 0,40%**. Sublimite: ISS = {[(RBT12 × 22%) − 183.780,00]/RBT12} × 40,00%; IBS idem × 0,24%.

**Anexo V — Serviços do inciso V com fator r < 28%**

| Faixa | Alíq. nominal | Deduzir (R$) | IRPJ | CSLL | CBS | CPP | ISS | IBS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1ª | 15,50% | – | 25,00% | 15,00% | 16,96% | 28,85% | 14,00% | 0,19% |
| 2ª | 18,00% | 4.500,00 | 23,00% | 15,00% | 16,96% | 27,85% | 17,00% | 0,19% |
| 3ª | 19,50% | 9.900,00 | 24,00% | 15,00% | 17,95% | 23,85% | 19,00% | 0,20% |
| 4ª | 20,50% | 17.100,00 | 21,00% | 15,00% | 18,94% | 23,85% | 21,00% | 0,21% |
| 5ª | 23,00% | 62.100,00 | 23,00% | 12,50% | 16,96% | 23,85% | 23,50% | 0,19% |
| 6ª | **30,40%** | 540.000,00 | 35,10% | 15,54% | 19,78% | 29,58% | – | – |

Sublimite: ISS = {[(RBT12 × 23%) − 62.100,00]/RBT12} × 23,50%; IBS idem × 0,19%.

Conferi a soma de cada linha de repartição de 2027-2028 (= 100,00%) e dos dois conjuntos de teto (= 100,00%) à mão; o teste `test_dl075_tabelas.py` deve repetir isso para 2027.

### 2029 a 2033 (lido; só o que muda em relação a 2027-2028)

Alíquotas nominais e deduções iguais, exceto a 6ª faixa a partir de 2029: Anexo I **18,90%** (Res.) — ver divergência abaixo; II 30,00%; III 33,00%; IV 33,00%; V 30,50%. Em 2029 as 6ªs faixas voltam às repartições de hoje (I: 13,50/10,00/34,40 CBS/42,10; II: 8,50/7,50/25,50/23,50/35,00; III: 35,00/15,00/19,50/30,50; IV: 53,50/21,50/25,00; V: 35,00/15,50/20,00/29,50). CBS nas faixas 1-5 a partir de 2029: I 15,50%; II 14,00%; III 15,60/17,10/16,60/16,60/15,60; IV 21,50/25,00/24,00/23,00/22,00; V 17,15/17,15/18,15/19,15/17,15. ICMS/ISS cedem ao IBS 10% ao ano do total do par (ex.: Anexo I 1ª faixa ICMS/IBS 30,60/3,40 (2029) → 27,20/6,80 → 23,80/10,20 → 20,40/13,60 → só IBS 34,00% (2033); Anexo IV 1ª faixa ISS/IBS 40,05/4,45 → 35,60/8,90 → 31,15/13,35 → 26,70/17,80 → IBS 44,50%). Teto do ISS cai 0,5 p.p. ao ano (4,5% em 2029 … 3% em 2032; some em 2033), com redistribuições próprias por ano (transcritas em `anexo_III_parsed.txt` e `anexo_IV_parsed.txt`). Não transcrevo tudo aqui porque não entra no produto agora; está nos arquivos, extraído do texto oficial.

---

## 2. LC 123/2006 na redação de 2027 (Planalto) — onde mora cada regra

**Fontes (lido, Planalto, curl hoje):** LC 123 compilada (`lcp123.htm`); **LC 214/2025** (`Lcp214.htm`), em especial **art. 517** (reescreve a LC 123), **art. 519** ("Os Anexos I a V da LC 123 passam a vigorar com a redação dos Anexos XVIII a XXII desta LC"), **art. 544, III** (arts. 517 e 519 a 534 produzem efeitos em **01/01/2027**), **Anexos XVIII a XXII**; **LC 227, de 13/01/2026** (`Lcp227.htm`), que alterou a LC 214 e a LC 123.

**Resposta à pergunta:** os percentuais de 2027 estão **nos dois lugares**: a **lei** (LC 123, Anexos I a V na redação da LC 214 art. 519, com retoques da LC 227) e a **Resolução** (Res. 140, Anexos I a V na redação da Res. 190 art. 6º). Comparei por script os blocos de 2027-2028 dos cinco anexos entre o texto do Planalto e o DOU: **idênticos** (Anexo III: o texto original da LC 214 trazia CBS 16,42% nas 3ª/4ª faixas; a redação da LC 227, que o Planalto consolida, e a Res. 190 trazem **16,41%**). Uma **divergência real a partir de 2029**: Anexo I, 6ª faixa, alíquota nominal **19,00% na LC 214 (Planalto, l. 23294) × 18,90% na Res. 190**. Não afeta 2027-2028; registro para o backlog de 2029.

Atenção ao **Planalto**: o texto compilado da LC 123 **não inlinou** as redações da LC 214 com efeitos em 2027 (mostra "(Vide LC 214) Produção de efeitos" ao lado dos incisos IV, V, VII e VIII do art. 13 e mantém o art. 18 § 1º na redação da LC 155). O texto vigente em 2027 tem de ser lido no **art. 517 da LC 214**. Dele (lido):

- **Art. 13:** "IX - Imposto sobre Bens e Serviços (IBS); X - Contribuição Social sobre Bens e Serviços (CBS)" (redação LC 227). **§ 10:** faculdade de apurar IBS/CBS pelo regime regular; **§ 10/11 (redação LC 227):** opção por semestre (janeiro e julho), exercida em **setembro e março** (a LC 214 original dizia "setembro e abril"; a 227 corrigiu e a Res. 190 segue março).
- **Art. 18, § 1º:** "receita bruta acumulada nos **doze meses antecedentes ao mês anterior** ao do período de apuração"; **§ 1º-A, I:** idem para RBT12 — a defasagem está **na lei**, não só na Resolução. **§ 1º-B, I (LC 227):** teto do ISS 5%, diferença "aos tributos federais e IBS". **§ 2º:** não reescrito — continua "proporcionalizados ao número de meses de atividade" (redação LC 155); a regra operacional é a da Res. 190 art. 22 § 2º. **§ 4º, II / § 5º:** Anexo II só para IPI mantido; indústria em geral → Anexo I. **§ 4º-A, I:** monofásico e, "em relação ao ICMS, ao IBS e à CBS", ST/antecipação com encerramento. **§ 5º-K e § 24:** fator r com folha e receita dos "doze meses antecedentes ao mês anterior" (a mesma defasagem vale para o **FS12**). **§ 14 / § 14-A:** exportação reduz ICMS/ISS e **IPI, IBS e CBS**.
- **Art. 23, §§ 1º-3º:** crédito de ICMS, **IBS e CBS** ao adquirente não optante "em montante equivalente ao cobrado por meio desse regime único"; a alíquota do crédito **vai no documento fiscal** e corresponde aos percentuais dos Anexos para a faixa do mês da operação (no mês de início, a menor alíquota). É por isso que a alíquota efetiva precisa ser conhecida **antes** de emitir a nota — daí a defasagem de um mês.
- **Art. 25:** PGDAS mensal; art. 25 § 2º (DEFIS anual) → Res. 190 art. 38-B.
- **Limite de R$ 4,8 mi e sublimite de R$ 3,6 mi:** a Res. 190 mantém o art. 9º (3,6 mi, agora "ICMS, ISS e IBS") e o art. 12 § 2º (R$ 300.000,00/mês no início) — *lido*. O art. 3º, II da LC 123 (4,8 mi) e o art. 2º da Res. 140 **não aparecem alterados** no que li; não reli o art. 3º, II hoje — *inferido*, baixo risco.

---

## 3. NT 2026.008 da NF-e — `vProd`, `vNF` e IBS/CBS em 2027 (HI-133)

**Fonte:** texto local extraído da NT (`…/scratchpad/nfe/nt_txt/nt2026008.txt`, v1.00, setembro/2026) e NT 2025.002 v1.52 (`pt_nt2025002_v152.txt`); informes do Portal da NF-e (`…/nfe/informes_hoje.html`, capturado hoje 10:46). Marca: **lido em cópia local do PDF oficial** (não rebaixei do portal hoje).

O que a NT diz (lido):

- Introdução: "os valores do IBS e da CBS incidentes na operação **deverão ser acrescidos ao valor do produto ou serviço, compondo o valor informado no campo vProd**. A inclusão … não implica sua inclusão na base de cálculo desses tributos." E: "por já estarem compreendidos no valor do produto, **não deverão ser adicionados novamente** na composição do valor total da NF-e/NFC-e (**vNFTot**), evitando duplicidade. Os valores de IBS e CBS permanecem destacados … porém são **meramente informativos**."
- Campo **I11 vProd**, observação: "**A partir de 2027**, os valores de IBS, CBS e IS compõem o Valor Total Bruto, exceto nas notas de importação."
- Novos campos: **I11b vUnComLiq**, **I11c vProdLiq** (valor líquido sem tributos; regras I11c-10/20) e **W01a vProdLiqTot** (regras W01a-10/20).
- **VB01-10/20 (vItem)**: "(+) vProd (**contém vIBS, vCBS e vIS**) …"; as linhas "(+) vIBS (+) vCBS (+) vIS" continuam listadas com "Exceção 1: em 2025 e 2026 não somar" e "**Observação: Implementação Futura**" — isto é, a regra do item **ainda não está fechada** no texto; a leitura coerente com a introdução é que, a partir de 2027, IBS/CBS entram **uma vez**, dentro do `vProd`.
- **vNF (W16)**: a NT 2026.008 **não traz regra para o `vNF` clássico**; só menciona o `vNFTot` (W60, criado pela NT 2025.002: "soma dos vItem", também "Implementação futura"). UB16-10 (base do IBS/CBS = vProd + … − tributos) foi **removida**.
- Cronograma: homologação 05/10/2026 → **postergada para 26/10/2026**; produção 03/11/2026 → **16/11/2026** (Informe de 05/10/2026). NB01-30: homologação 01/02/2027, produção 01/03/2027.
- Não há NT ou Informe posterior sobre `vNF` no portal até hoje (o informe mais recente é o de 05/10/2026).

**O que isso resolve e o que não resolve.** Resolve o **leiaute**: em 2027 `vProd` (e `vItem`) **carregam IBS/CBS por dentro**, e `vProdLiq` dá o valor sem tributos. **Não** resolve a **regra de receita**: (a) para o optante do Simples no regime único, a nota não tem IBS/CBS "por fora" — o produto pode continuar a reconhecer receita bruta pelo `vProd` (hipótese; LC 123 art. 3º § 1º na redação da LC 214: receita bruta = produto da venda/preço dos serviços "não incluídas as vendas canceladas e os descontos incondicionais" — sem exclusão de tributos, *lido*); (b) para o **Presumido** e para o optante **pelo regime regular**, se IBS/CBS "calculados por fora" ficam dentro do `vProd`, a receita bruta do DL 1.598 art. 12 § 4º ("tributos não cumulativos cobrados destacadamente … mero depositário") pede leitura própria — *não conferido*. Ou seja, o bloqueio em `escrituracao_nfe.py:759-779` continua certo **para 2027 no Presumido**; para o Simples no regime único há caminho, mas é decisão de produto com hipótese a validar.

---

## 4. Alíquota de referência da CBS/IBS para 2027

**Lido (Planalto, LC 214):** art. 346 — 2026: CBS 0,9%; art. 347 — 2027-2028: CBS = alíquota fixada nos termos do art. 14 "reduzida em 0,1 ponto percentual", exceto combustíveis (arts. 172-180); art. 348, III, "c" — em 2026 as alíquotas de teste **não se aplicam** aos optantes do Simples; art. 349, § 1º — TCU envia cálculos até **15/09**, Senado fixa até **31/10** do ano anterior; § 2º — se passar de **22/12** sem fixação, valem as alíquotas calculadas pelo TCU; **art. 353, § 2º — em 2026 esses prazos ficam prorrogados em 45 dias** (daí o "30/10" e "15/12" das notícias: tem base legal, e está na LC). Art. 41, §§ 1º-4º: optante do Simples "fica sujeito às regras desse regime" (§ 2º); pode optar pelo regular (§ 3º), nos termos da LC 123 (§ 4º).

**Resolução do Senado:** **não publicada até hoje**. Busca (secundário: Jornal Contábil, Contmatic, BMA, TAGD, NetCPA, APET): RFB enviou a metodologia ao TCU em 14/09/2026 sem número; estimativa do CGIBS (Res. CGIBS 14/2026, 31/07/2026) de 27,91% conjunto (CBS ≈ 9,21%) é **estimativa, não alíquota**. Não encontrei página do Senado; não li a Res. CGIBS 14.

**Resposta à pergunta:** para o optante do Simples **no regime único**, CBS e IBS **saem dos Anexos** (LC 123 art. 13, IX e X; art. 18 e Anexos; LC 214 art. 41 § 2º; Res. 190 art. 4º, IX e X). A alíquota de referência **só importa** para (i) o optante que exerceu a opção do art. 40-C (regime regular, com dedução das parcelas de CBS/IBS do DAS pelo art. 22-A) e (ii) os clientes do Presumido. **P4 continua pendente por fato, não por falta de leitura.**

---

## 5. O que muda no produto

**`apps/fiscal/simples_tabelas.py` (dado).** Novo conjunto `ANEXOS_2027_2028` com vigência 01/01/2027–31/12/2028 e tributos `IRPJ, CSLL, CBS, CPP, ICMS, IBS` (I); `+IPI` (II); `IRPJ, CSLL, CBS, CPP, ISS, IBS` (III e V); `IRPJ, CSLL, CBS, ISS, IBS` (IV). `TetoIss` do III (limiar 14,92537%; redistribuição com **IBS 0,26%**) e do IV (12,5%; **IBS 0,40%**). `FONTE` = DOU 10/08/2026, Ed. 149-A, Seção 1 Extra A, URL acima, consultado em 09/10/2026; `dispositivo` = Res. CGSN 140 (redação da Res. 190 art. 6º) e LC 123 Anexos I-V (redação da LC 214 art. 519 e LC 227). `tabelas_vigentes_em` e `anexo()` passam a escolher por data. Teste: soma 100,00% por linha e por teto; igualdade das faixas/deduções de 1ª a 5ª com 2026; 6ª faixa nominal **18,90 / 29,90 / 32,90 / 32,90 / 30,40**.

**`apps/fiscal/rbt12.py` (regra).** Para PA ≥ 01/2027: (a) **janela do § 1º = índices `pa−13 … pa−2`** (12 meses antecedentes ao mês anterior), não `pa−12 … pa−1`; (b) início de atividade: **n = 1 ou 2 → regra "1ª faixa"** (sem RBT12; o resultado precisa de um estado novo, não um número); **n = 3 … 13 → média dos meses `abertura … pa−2` × 12**; **n ≥ 14 → § 1º**; o rótulo "§ 3º" desaparece (revogado) e o § 4º passa a ter incisos I-II; (c) § 5º, I, usa a mesma janela defasada; (d) `LIMITES` ganham vigência 2027+ (sublimite 3,6 mi e 300 mil/mês confirmados na Res. 190 arts. 9º e 12 § 2º; 4,8 mi e 400 mil/mês sem alteração encontrada — *inferido*); (e) destravar `ANO_RECUSADO`, com recusa só para 2029+ enquanto a divergência 19,00/18,90 não for esclarecida. O **FS12 do fator r** (DL-075) também passa a usar "doze meses antecedentes ao mês anterior" (LC 123 art. 18 §§ 5º-K e 24).

**`apps/fiscal/pre_das.py` (cálculo).** (a) Remover a recusa de 2027 (l. 829-844) e citar a fonte lida; (b) `_DESCONSIDERADOS[SEG_EXPORTACAO]` para 2027 = **{CBS, IBS, IPI, ICMS, ISS}** (hoje `{PIS, COFINS, ISS}`, correto só até 12/2026); (c) **novos segmentos**: "tributação concentrada/ST de IBS-CBS" (art. 25 §§ 6º e 8º, I — desconsidera CBS e IBS) e, quando houver comércio, "ST/antecipação de ICMS"; (d) **art. 22-A**: empresa com opção pelo regime regular (dado novo em `HistoricoRegimeTributario` ou equivalente, por semestre) → deduzir CBS e IBS da faixa; (e) teto do ISS redistribui também ao **IBS** (`TetoIss.redistribuicao` já comporta); (f) 6ª faixa continua fora do corte, mas a fórmula do art. 21, IV agora alcança **IBS**; (g) Anexo II restrito a IPI mantido — a classificação "indústria" em 2027 cai no Anexo I salvo ZFM (afeta `EnquadramentoAtividade`); (h) mensagens e `dispositivo` com "Res. CGSN 140, arts. 21-22 e 25 (redação da Res. 190/2026)".

**Receita de NF-e (`escrituracao_nfe.py:759-779`).** O texto fixo "regra de receita de 2027 pendente: NT 2026.008 e vNF" pode ser refinado: a NT está lida; o que falta é **decisão de receita por regime** (seção 3). Para Simples no regime único, proposta de hipótese: receita = `vProd` (que já contém IBS/CBS), guardando `vProdLiq` como memória; para Presumido e optante pelo regular, manter a recusa até leitura do DL 1.598 art. 12 § 4º / norma da RFB. Produção da NT em **16/11/2026**: a partir daí notas de 2026 podem trazer `vProdLiq` sem mudar a receita (IBS/CBS só entram no `vProd` em 2027).

---

## Pronto para virar código (com fonte oficial lida)

1. Tabelas 2027-2028 dos cinco Anexos, tetos do ISS e fórmulas do sublimite — **DOU + Planalto, idênticos**.
2. Nova definição de RBT12 (defasagem de um mês) e nova regra de início de atividade (1ª faixa / média × 12 do 3º ao 13º mês / § 1º do 14º) — **LC 214 art. 517 + Res. 190 arts. 21-22**.
3. CBS/IBS no DAS; PIS/Cofins fora; exportação desconsidera IBS, CBS, IPI, ICMS, ISS; segregação de concentrado/ST de IBS-CBS; dedução do art. 22-A; Anexo II só ZFM — **Res. 190 arts. 4º, 5º, 22-A, 25**.
4. Calendário 2026-2027 para a tela do escritório: opção Simples 2027 até **15/10/2026**; regime regular jan-jun/2027 até **30/10/2026**; cancelamentos 03/11–20/12/2026; "Receitas Anteriores à Opção" até **20/12/2026** e **20/01/2027**; DEFIS no PGDAS-D jan-mar/2027; NFS-e nacional obrigatória **01/11/2026** — **Res. 186/194/190/191**.
5. Leiaute NF-e 2027: `vProd` contém IBS/CBS; `vProdLiq`/`vProdLiqTot` — **NT 2026.008 v1.00**.

## Continua pendente

| # | Pendência | Estado | Onde resolver |
| --- | --- | --- | --- |
| P1 | Anexos I-V da Res. 190 | **resolvida** (DOU lido) | — |
| P2 | Texto oficial da Res. 190 e Res. 194 | **resolvida** (DOU lido) | — |
| P3 | `vProd`/`vNF` em 2027 | **leiaute resolvido; regra de receita por regime pendente** (DL 1.598 art. 12 § 4º para Presumido/regular; `vNF` W16 sem regra na NT) | Planalto (DL 1.598); portal NF-e (NT futura sobre VB01/W16) |
| P4 | Alíquota de referência da CBS 2027 | **pendente de fato** — Senado até ~15/12/2026 (LC 214 art. 349 § 1º c/ art. 353 § 2º); irrelevante para Simples no regime único | Senado/DOU |
| P13 | Divergência Anexo I, 6ª faixa, 2029+: LC 214 19,00% × Res. 190 18,90% | nova; não afeta 2027-2028 | CGSN/errata ou LC futura; recusar 2029+ até lá |
| P14 | Limite 4,8 mi / 400 mil-mês para 2027 | sem alteração encontrada; não reli art. 3º, II | Planalto (LC 123 art. 3º) — leitura de 2 minutos |
| P15 | Receita bruta do Simples com IBS/CBS dentro do `vProd` (optante no regime único): confirmar que `vProd` = receita | hipótese, coerente com LC 123 art. 3º § 1º | Fred (produto) + manual do PGDAS-D 2027 quando sair |
| P16 | Res. CGIBS 14/2026 (estimativa 27,91%) e Ato Conjunto RFB/CGIBS 8/2026 | não lidos; só secundário | portal NF-e "Atos Técnicos"; CGIBS |

## Fontes consultadas hoje

**Oficiais (lido):** [Res. CGSN 190/2026 — DOU](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-190-de-4-de-agosto-de-2026-724454118) · [Res. 186](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-186-de-9-de-abril-de-2026-700230741) · [Res. 191](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-191-de-4-de-agosto-de-2026-724399487) · [Res. 192](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-192-de-4-de-agosto-de-2026-724399510) · [Res. 193](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-193-de-4-de-agosto-de-2026-724208269) · [Res. 194](https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-194-de-25-de-setembro-de-2026-735097948) · [LC 123](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm) · [LC 214](https://www.planalto.gov.br/ccivil_03/leis/lcp/Lcp214.htm) · [LC 227](https://www.planalto.gov.br/ccivil_03/leis/lcp/Lcp227.htm).

**Cópia:** NT 2026.008 v1.00 e NT 2025.002 v1.52 (PDFs oficiais já baixados em `…/scratchpad/nfe/nt_txt/`); informes do Portal da NF-e (captura de hoje); [PDF do DOU da Res. 190 em reformatributaria.com](https://www.reformatributaria.com/wp-content/uploads/2026/08/Resolucao-CGSN-no-190-de-4-de-agosto-de-2026-Resolucao-CGSN-no-190-de-4-de-agosto-de-2026-DOU-Imprensa-Nacional.pdf); [normaslegais](https://www.normaslegais.com.br/legislacao/Resolucao-cgsn-190-2026.htm).

**Secundárias (só para localizar):** [Jornal Contábil](https://jornalcontabil.com.br/noticia/aliquota-reforma-tributaria-indefinicao-15-dezembro/) · [Contmatic](https://simplifique.contmatic.com.br/blogs/aliquota-cbs-2027-tcu-prazo-30-outubro-senado) · [BMA](https://www.bmalaw.com.br/conteudo/direito-tributario/reforma-tributaria/reforma-tributaria-cgibs-divulga-nova-estimativa-para-as-aliquota-de-referencia-em-2027/pdf) · [Contábeis](https://www.contabeis.com.br/noticias/78568/cgibs-estima-aliquota-de-referencia-de-27-91-para-ibs-e-cbs/) · [TAGD](https://tagdlaw.com.br/?p=15539) · [NetCPA](https://netcpa.com.br/colunas/reforma-tributaria-tcu-tem-ate-30-de-outubro-para-enviar-ao-senado-calculos-da-aliquota-da-cbs/28404) · [APET](https://apet.org.br/?p=142819) · [FIEMG IE-52](https://www.fiemg.com.br/wp-content/uploads/2026/08/IE-52-Alteracao-Simples-Nacional-Reforma-Tibutaria-1.pdf) · [COAD](https://coad.com.br/home/noticias-detalhe/139271/nfs-e-nacional-sera-obrigatoria-para-optantes-do-simples-nacional-a-partir-de-1-11-2026).

**Repositório (lido):** `/home/user/DataLedger/apps/fiscal/simples_tabelas.py` (1-27, 35-41, 580-584) · `/home/user/DataLedger/apps/fiscal/rbt12.py` (9-40, 56-58, 96-139, 320-335, 486-492) · `/home/user/DataLedger/apps/fiscal/pre_das.py` (155-205, 829-844) · `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py` (759-779) · `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md`.

**Não alcançado hoje:** portal do Simples Nacional e `normas.receita` (sem JS); site do Senado (nenhuma resolução localizada); Res. CGIBS 14/2026; Ato Conjunto RFB/CGIBS 8/2026; DL 1.598 art. 12 § 4º (não baixado).
