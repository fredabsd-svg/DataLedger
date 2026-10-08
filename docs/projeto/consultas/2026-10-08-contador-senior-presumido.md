# Consulta ao contador-senior sobre o Lucro Presumido (IRPJ e CSLL) — 08/10/2026

**Legislação validada até:** 08/10/2026 · **Competências de referência:** 1º a 4º trimestres de 2026 (com a transição da CSLL) e 2027 em diante · **Grau de segurança geral:** alto no mecanismo e nas alíquotas, médio nos pontos operacionais (feriados, separação da CSLL retida, rotina do escritório). **Lidos hoje no Planalto** (`curl` com User-Agent de navegador, HTTP 200 em todos): LC 224/2025, Lei 9.249/1995, Lei 9.430/1996, Lei 7.689/1988, Lei 8.981/1995, Lei 9.718/1998, Lei 10.833/2003, DL 1.598/1977, Decreto 9.580/2018 (RIR), Decreto 12.808/2025, CF/88, Leis 662/1949 e 6.802/1980. **Lidos em gov.br:** Perguntas e Respostas da RFB "Redução dos incentivos e benefícios tributários — V5, atualizado em 30/07/2026" (PDF, 24 páginas, itens 11 a 14) e as tabelas de códigos de receita IRPJ e CSLL (atualizadas em 12/03/2024). **Lido no portal do STF:** andamento da ADI 7936 (incidente 7501902) e a notícia de 18/02/2026. **Cópia** (normaslegais.com.br, texto íntegro): IN RFB 2.305/2025 na redação atual, IN RFB 2.306/2026 e IN RFB 1.700/2017 — `normas.receita.fazenda.gov.br` devolveu só a casca Angular (45 KB sem texto), como na consulta anterior. **Secundário:** notícias sobre liminares de primeira instância. **Não conferido:** redação ORIGINAL dos incisos I e II do art. 15 da IN 2.305 (revogados; a cópia só mostra a redação atual), Lei 9.093/1995 e Lei 14.759/2023 (feriados), Lei 11.196/2005 art. 70, Lei 9.779/1999 art. 15 (apuração centralizada), manual do sistema de referência.

⚠️ Tudo abaixo é **HIPÓTESE para validação do Fred**. Marcas: *lido* = texto oficial aberto hoje; *cópia* = texto íntegro em site terceiro; *secundário* = notícia/fornecedor/fórum; *não conferido* = conhecimento meu sem texto aberto hoje.

**Li antes, no repositório:** `/home/user/DataLedger/docs/planos/DL-067-plano-do-modulo-fiscal.md:472-489` e `:969`; `/home/user/DataLedger/docs/projeto/consultas/2026-10-08-contador-senior-servicos-tomados.md` (formato e marcas); `/home/user/DataLedger/apps/fiscal/receita.py` (integral); `/home/user/DataLedger/docs/projeto/mapa-funcional-fiscal.md:293-388`; `/home/user/DataLedger/docs/projeto/fontes-de-referencia.md:48-96`. **`apps/fiscal/retencoes.py` não existe** no repositório (conferido por `Glob` em `apps/fiscal/*.py`); as retenções da NFS-e estão descritas na consulta de serviços tomados, item 3, que cita `apps/fiscal/models.py` — não abri o `models.py` hoje. O **manual do sistema de referência não está no repositório** por decisão registrada em `fontes-de-referencia.md:81-85`; o que há é o resumo reescrito do mapa fiscal (linhas 316-362), usado no item 11.

**Três correções ao que a pesquisa preliminar e o DL-067 trazem:** (a) o exemplo de "R$ 122 mil" não é secundário, é o **exemplo oficial do P&R da RFB, item 11** (8% × 1.250.000 + 8,8% × 250.000) — a multiplicação por 1,10 está confirmada em fonte oficial; (b) nas quotas, a **2ª quota tem só 1%**; a Selic só começa a correr para a **3ª** (Lei 9.430, art. 5º, § 3º — *lido*), não "Selic mais 1% a partir da 2ª"; (c) o DL-067:484 fala em "excedente de R$ 550.000 rateado pelo peso de cada atividade" — o resultado (R$ 346.266,67 e R$ 80.566,67) está **certo** e bate com o método do P&R item 14, que rateia o **limite** em vez do excedente; os dois são algebricamente iguais (ver item 4).

---

## 1. Alíquotas e adicional

**Resposta curta.** IRPJ 15% + adicional de 10% sobre a parcela da base que exceder R$ 20.000 × meses do período (R$ 60.000 no trimestre). CSLL 9%, **sem adicional**. O adicional é exclusivamente do imposto de renda; a CSLL tem alíquota única para "as demais pessoas jurídicas".

**NORMA.**
- Lei 9.249/1995, art. 3º, caput ("quinze por cento") e § 1º, red. Lei 9.430/1996 ("parcela do lucro real, presumido ou arbitrado, que exceder o valor resultante da multiplicação de R$ 20.000,00 pelo número de meses do respectivo período de apuração, sujeita-se à incidência de **adicional de imposto de renda** à alíquota de dez por cento"); § 4º: o adicional "será recolhido integralmente, não sendo permitidas quaisquer deduções" — *lido*. Repercussão para o produto: incentivos não abatem o adicional; a dedução de IRRF (item 6) abate do **imposto total apurado** (15% + adicional), porque o § 4º veda deduções **de incentivo**; o RIR art. 599 autoriza deduzir "do imposto sobre a renda devido no período" o retido — *lido*. Essa leitura (IRRF abate do total, inclusive adicional) é a praxe e é a que os programas da RFB aplicam — **inferência**, grau alto.
- Lei 7.689/1988, art. 3º: 9% "no caso das demais pessoas jurídicas" (inciso incluído pela Lei 13.169/2015; a numeração dos incisos foi alterada por MP 1.034/2021, Lei 14.183/2021 e LC 224/2025 — a alíquota de 9% para as demais PJ está em todas as redações) — *lido*. Alíquotas majoradas (15%, 20%) só para financeiras, seguradoras, instituições de pagamento, fintechs e bets — fora do escopo.
- IN 1.700/2017, art. 221 (IRPJ: alíquota do art. 29 + adicional do § 1º) e art. 222 (CSLL: alíquota do art. 30 sobre a base) — *cópia*.

**Proposta para o produto.** `IRPJ = 15% × base + 10% × max(0; base − 20.000 × meses)`; `CSLL = 9% × base_CSLL`. "Meses" = meses do período de apuração (3 no trimestre cheio; menos em início ou encerramento de atividade — Lei 9.249, art. 3º, § 1º, pela redação vigente, e § 2º). Alíquota da CSLL parametrizada por empresa com valor padrão 9% e recusa nomeada para empresas das atividades de alíquota majorada ("alíquota de CSLL majorada — fora do escopo").

**Grau de segurança:** alto.

## 2. Percentuais da CSLL

**Resposta curta.** A CSLL tem só **três** percentuais: 32% para as atividades do art. 15, § 1º, III, da Lei 9.249 (serviços em geral, intermediação, administração/locação/cessão de bens, factoring, construção vinculada a concessão); 38,4% para Empresa Simples de Crédito; **12% para "as demais receitas brutas"**. Logo combustíveis (1,6% no IRPJ), transporte de passageiros (16% no IRPJ) e serviços hospitalares (8% no IRPJ) são todos **12% na CSLL** — sim, é o residual.

**NORMA.** Lei 9.249/1995, art. 20, caput, I, II e III, red. LC 167/2019 — *lido*. Serviços hospitalares: a exceção do art. 15, § 1º, III, "a", red. Lei 11.727/2008, exige "prestadora destes serviços organizada sob a forma de **sociedade empresária** e [que] atenda às normas da **Anvisa**" — *lido*. Como a receita hospitalar está **excluída** do inciso III, cai no residual de 12% do art. 20, III. IN 1.700, art. 215, § 1º (resultado presumido pelos percentuais do art. 34) — *cópia*.

**Proposta para o produto.** Tabela de **atividade de presunção** com dois percentuais (IRPJ, CSLL), fonte e vigência, carregada com: comércio/indústria/transporte de cargas 8/12; revenda de combustíveis 1,6/12; transporte de passageiros 16/12; serviços em geral 32/32; intermediação 32/32; administração/locação de bens 32/32; serviços hospitalares (com os dois requisitos legais marcados pelo contador) 8/12. Não inferir "hospitalar" a partir de `cTribNac`: os requisitos (tipo societário e Anvisa) estão fora da nota. Sem "percentual padrão": a atividade da receita é informação do contador (item 11).

**Grau de segurança:** alto.

## 3. LC 224/2025, art. 4º, §§ 4º, VII e 5º

**Resposta curta.** (a) **Multiplica por 1,10**: 8% → 8,8%, 32% → 35,2%, 1,6% → 1,76%, 16% → 17,6%, 12% → 13,2%. Não é soma de 10 pontos. (b) Vale para **IRPJ e CSLL**. (c) **IRPJ desde 01/01/2026** (1º trimestre); **CSLL desde 01/04/2026** (2º trimestre). (d) O limite de **R$ 3.750.000,00 para a CSLL em 2026** está **certo** e é a posição oficial da RFB.

**NORMA.**
- LC 224/2025, art. 4º, § 4º, VII: "regimes de tributação em que a base de cálculo seja presumida: **acréscimo de 10% (dez por cento) nos percentuais de presunção**"; § 5º: no presumido "somente se aplica aos percentuais de presunção incidentes sobre a parcela da receita bruta total que exceda o valor de R$ 5.000.000,00 no ano-calendário, aplicando-se: I — o limite proporcionalmente a cada período de apuração no ano, permitido o ajuste nos períodos seguintes; e II — o acréscimo proporcionalmente às receitas de cada uma das atividades" — *lido*. "Acréscimo de 10% **nos** percentuais" é relativo (10% de 8 = 0,8), e o P&R da RFB item 11 confirma com 8,8% e item 14 com 35,2% — *lido*. O texto da lei, sozinho, admitiria a leitura "10 pontos"; a regulamentação (Decreto 12.808/2025, arts. 11 e 12 — *lido*; IN 2.305, arts. 13 e 14 — *cópia*) e o P&R fecham a questão em 1,10. Quem defende "10 pontos" terá que litigar; o produto segue a RFB e mostra a parcela separada (item 10).
- Decreto 12.808/2025, art. 12, caput e parágrafo único, I e II — *lido*: repete a lei para "IRPJ e CSLL".
- Vigência: LC 224, art. 14, I, "a": 1º dia do 4º mês após a publicação (publicada em 26/12/2025, edição extra → **01/04/2026**) "ao disposto no art. 4º, para os tributos que estejam sujeitos ao disposto na alínea c do inciso III do caput do art. 150 da CF"; III: "a partir de 1º de janeiro de 2026, em relação aos demais dispositivos" — *lido*. CF, art. 150, § 1º, red. EC 42/2003: "a vedação do inciso III, c, **não se aplica** aos tributos previstos nos arts. 148, I, 153, I, II, **III** e V" — o art. 153, III é o **imposto de renda** — *lido*. Portanto o IRPJ não está sujeito à noventena do art. 150, III, "c", e cai no inciso III do art. 14: **01/01/2026**. A CSLL tem noventena própria no art. 195, § 6º ("só poderão ser exigidas após decorridos noventa dias da data da publicação da lei") — *lido*. Sutileza: o art. 14, I, "a", fala no art. 150, III, "c", e não no art. 195, § 6º; mas 90 dias de 26/12/2025 dão 26/03/2026, e como a apuração é trimestral o primeiro período inteiramente alcançado é o **2º trimestre** — exatamente a posição da RFB (P&R item 12: "a partir do primeiro trimestre de 2026 para o IRPJ e a partir do segundo trimestre de 2026 para a CSLL" — *lido*).
- Limite da CSLL em 2026: P&R item 13: "o limite anual será de R$ 3.750.000,00 [...] o equivalente a ¾ (três quartos) do limite anual" — *lido*. O DL-067:474 está correto.
- Receitas financeiras e ganhos de capital **não** entram no cômputo do limite de R$ 5 milhões (P&R item 11.1 — *lido*), porque não são receitas "submetidas aos coeficientes de presunção".

**Proposta para o produto.** Parâmetro por tributo: `inicio_acrescimo = 2026-01-01` (IRPJ) e `2026-04-01` (CSLL); trimestres anteriores ao início não têm acréscimo nem sobra (item 4). Fator `Decimal("1.10")` aplicado ao percentual da atividade, nunca soma de pontos. Tabela de percentuais efetivos exibida na memória de cálculo ("8% / 8,8%").

**Grau de segurança:** alto (lei, decreto, IN e P&R convergem).

## 4. IN RFB 2.305/2025, art. 15, na redação da IN 2.306/2026 — fórmula e exemplo

**Resposta curta.** Limite trimestral de R$ 1.250.000,00 verificado pela receita bruta **do próprio trimestre**; a parte não usada em trimestre abaixo do limite **soma ao limite dos trimestres seguintes do mesmo ano**; no 4º trimestre confere-se o limite anual com três desfechos; início/encerramento usa `nº de trimestres em atividade × 1.250.000`; rateio por atividade pela participação na receita bruta total do trimestre; **a IN não diz nada sobre filiais** (conferido no texto integral da 2.306 — *cópia*).

**NORMA** (IN 2.305, art. 15, red. IN 2.306/2026, DOU de 23/01/2026, em vigor na publicação — *cópia*; arts. 1º a 3º da IN 2.306 lidos por inteiro):
- § 2º: "limite proporcional [...] corresponde a R$ 1.250.000,00 por trimestre e deve ser verificado considerando a receita bruta do respectivo trimestre".
- § 3º: no trimestre acima do limite, o percentual "acrescido em 10%" incide "sobre a parcela da receita bruta que exceder o referido limite".
- § 4º: no trimestre abaixo do limite, "a diferença poderá ser considerada para fins de apuração do limite aplicável aos trimestres subsequentes do mesmo ano-calendário".
- § 5º (último trimestre, pela receita acumulada do ano): **I** — receita do ano **abaixo** de R$ 5 milhões: sem acréscimo no 4º e a PJ **poderá** recalcular os trimestres em que aplicou o acréscimo, apurar a diferença e **deduzi-la do IRPJ e da CSLL devidos no 4º trimestre**; **II** — receita do ano acima do limite, mas excedente anual **menor** que a soma dos excedentes dos trimestres anteriores: sem acréscimo no 4º e recálculo dos anteriores com o excedente anual **rateado** na proporção do excedente de cada trimestre, deduzindo a diferença no 4º; **III** — excedente anual **maior** que a soma dos anteriores: o excedente do 4º "será limitado à diferença entre a parcela da receita bruta acumulada que exceder o limite anual e o somatório das parcelas excedentes dos trimestres anteriores".
- § 6º: atividades diversificadas observam "em cada trimestre, a proporção da receita bruta decorrente de cada atividade em relação à receita bruta total do trimestre".
- §§ 7º e 8º: se a dedução do § 5º superar o devido no 4º trimestre, o excesso vai a **restituição ou compensação** (PER/DCOMP), com Selic acumulada desde o mês seguinte ao 4º trimestre e 1% no mês da disponibilização.
- § 9º: início ou encerramento no ano → "limite anual [...] proporcionalmente, considerando o número de trimestres efetivamente em atividade, multiplicado pelo limite estabelecido no § 2º".
- Art. 2º da IN 2.306 revogou os incisos I e II do art. 15 original (que, segundo a pesquisa preliminar, verificavam pela receita acumulada — **não conferi a redação original**).
- P&R item 14 (*lido*): rateia o **limite** pela participação de cada atividade e aplica o percentual normal até o limite rateado e o acrescido no restante. Algebricamente: `R_i − L·R_i/R = (R − L)·R_i/R = E·R_i/R`. Rateio do limite = rateio do excedente. O DL-067 e o P&R dizem a mesma coisa.

**FÓRMULA EXATA (proposta):** para cada tributo `k ∈ {IRPJ, CSLL}` e trimestre `t` do ano a partir do trimestre inicial do acréscimo (`t₀ = 1` para IRPJ; `t₀ = 2` para CSLL só em 2026):

```
R_t      = Σ_i R_{t,i}                                   receita bruta do trimestre sujeita a presunção
                                                         (já deduzidos devoluções, cancelamentos e descontos incondicionais;
                                                          receitas do art. 25, II NÃO entram — P&R 11.1)
L_t      = 1.250.000,00 + sobra_{t-1}      (sobra_{t₀-1} = 0)
E_t      = max(0; R_t − L_t)                             excedente do trimestre
sobra_t  = max(0; L_t − R_t)
E_{t,i}  = E_t × R_{t,i} / R_t                           rateio por atividade (§ 6º; P&R 14)
base_k,t = Σ_i [ (R_{t,i} − E_{t,i}) × p_{k,i} + E_{t,i} × p_{k,i} × 1,10 ] + outras receitas integrais (art. 25, II)

No último trimestre do ano (ou de atividade):
N        = nº de trimestres em atividade sujeitos ao acréscimo        (§ 9º; para CSLL/2026, N = 3)
ExcAnual = max(0; Σ_{t≥t₀} R_t − 1.250.000,00 × N)
S        = Σ_{t<último} E_t
caso III (ExcAnual ≥ S):  E_último = ExcAnual − S        (a fórmula de sobra já produz este valor)
caso II  (0 < ExcAnual < S): E_último = 0; E'_t = E_t × ExcAnual / S para t<último; recalcular base e tributo;
                             dedução_último = Σ_t (tributo_t − tributo'_t)
caso I   (ExcAnual = 0):  E_último = 0; E'_t = 0; dedução_último = Σ_t (tributo_t − tributo sem acréscimo_t)
Se dedução_último > tributo devido no último: saldo → PER/DCOMP (§§ 7º-8º), nunca abatido automaticamente.
```

Observação verificada: desenrolando a recorrência, `E_t = max(0; Σ_{≤t} R − 1.250.000 × (t − t₀ + 1) − Σ_{<t} E)`, de modo que no caso III o 4º trimestre pela regra da sobra e pelo § 5º, III dão **o mesmo número** (o script abaixo tem um `assert` disso). Os casos I e II são correções de **antecipação**: receita concentrada no início do ano gera acréscimo que a visão anual não sustenta.

**Exemplo numérico (Python, `Decimal`, `ROUND_HALF_UP`, centavos; dados sintéticos).** Script em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/calc/presumido.py`, executado hoje. Receitas por trimestre (comércio 8/12, serviços 32/32): T1 600.000 + 300.000 = 900.000; T2 1.200.000 + 700.000 = 1.900.000; T3 800.000 + 400.000 = 1.200.000; T4 1.000.000 + 500.000 = 1.500.000; ano 5.500.000. Outras receitas integrais: T2 12.000; T4 8.000. IRRF retido: 4.500 / 9.500 / 6.000 / 7.500. CSLL retida: 3.000 / 6.300 / 4.000 / 5.000.

| Trim. | R_t | L_t (IRPJ) | E_t | Base IRPJ | IRPJ (15%+ad.) | − IRRF | A pagar | Sem LC 224 | Parcela LC 224 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | 900.000,00 | 1.250.000,00 | 0,00 | 144.000,00 | 30.000,00 | 4.500,00 | 25.500,00 | 30.000,00 | 0,00 |
| T2 | 1.900.000,00 | 1.600.000,00 (sobra T1 350.000) | 300.000,00 | 337.052,63 | 78.263,15 | 9.500,00 | 68.763,15 | 77.000,00 | 1.263,15 |
| T3 | 1.200.000,00 | 1.250.000,00 | 0,00 | 192.000,00 | 42.000,00 | 6.000,00 | 36.000,00 | 42.000,00 | 0,00 |
| T4 | 1.500.000,00 | 1.300.000,00 (sobra T3 50.000) | 200.000,00 | 251.200,00 | 56.800,00 | 7.500,00 | 49.300,00 | 56.000,00 | 800,00 |

Abertura do T2: comércio 1.200.000 → E = 189.473,68 → 1.010.526,32 × 8% = 80.842,11 + 189.473,68 × 8,8% = 16.673,68; serviços 700.000 → E = 110.526,32 → 589.473,68 × 32% = 188.631,58 + 110.526,32 × 35,2% = 38.905,26; soma 325.052,63 + 12.000 integrais = 337.052,63; IRPJ = 50.557,89 + 10% × 277.052,63 = 78.263,15. Fechamento do ano: ExcAnual = 5.500.000 − 5.000.000 = 500.000; S = E1+E2+E3 = 300.000 < 500.000 → **caso III**, E4 = 200.000 (igual ao da sobra). Total IRPJ a pagar no ano: 179.563,15.

CSLL/2026 (acréscimo só a partir do T2; limite anual 3.750.000; sobra começa no T2): T1 base 168.000,00, CSLL 15.120,00 − 3.000 = 12.120,00 (sem acréscimo); T2 L = 1.250.000 (sem sobra do T1, porque o T1 não está no período do acréscimo), E = 650.000, base 392.589,47, CSLL 35.333,05 − 6.300 = 29.033,05; T3 E = 0, base 224.000,00, CSLL 20.160,00 − 4.000 = 16.160,00; T4 L = 1.300.000, E = 200.000, base 291.733,34, CSLL 26.256,00 − 5.000 = 21.256,00. Fechamento: ExcAnual = 4.600.000 − 3.750.000 = 850.000; S = 650.000 → caso III, E4 = 200.000.

Conferência do exemplo oficial: 1.250.000 × 8% + 250.000 × 8,8% = **122.000,00** (P&R item 11) — bate.

**Arredondamento.** Rateio e percentuais calculados em `Decimal` sem truncar; **cada linha da memória** (normal e acréscimo, por atividade) quantizada a 0,01 `ROUND_HALF_UP`; a última linha do rateio recebe o resíduo para que `Σ E_{t,i} = E_t` exatamente. Isso gera diferença de até alguns centavos contra o cálculo "exato" sem arredondar linhas (no exemplo, a base da CSLL do T4 ficou 283.733,34 em vez de 283.733,33). Não há norma sobre isso; é escolha de produto — **hipótese 5**.

**Filiais.** Nada na lei, no decreto, na IN nem no P&R. O limite é da "receita bruta total" da **pessoa jurídica** no ano; a apuração do IRPJ/CSLL é centralizada na matriz (Lei 9.779/1999, art. 15 — **não conferido hoje**). Produto: limite por empresa (CNPJ raiz), somando todos os estabelecimentos — **inferência**, grau médio-alto.

**Proposta para o produto.** Um "controle do limite LC 224" por empresa, ano e tributo, com uma linha por trimestre (R_t, L_t, E_t, sobra_t) e o fechamento do ano com o caso (I, II, III) nomeado, a dedução do 4º trimestre quando houver e o saldo que vai a PER/DCOMP. Receita sujeita a presunção separada das receitas integrais (as integrais não entram em R_t). Recalcular em cadeia: alteração em um trimestre efetivado reabre os seguintes como "a retificar" (mesmo princípio de `receita.py:665-730`). Casos I e II **não executei em Python** — fazer teste unitário dos três casos no plano.

**Grau de segurança:** alto na fórmula dos §§ 2º a 6º e 9º; médio na redação original revogada (não lida) e em filiais.

## 5. Base de cálculo: deduções e receitas integrais

**Resposta curta.** Da receita bruta deduzem-se **só** devoluções, vendas canceladas e descontos **incondicionais**. ISS, ICMS próprio e PIS/Cofins incluem-se na receita bruta (não se deduzem); só ficam fora os tributos **não cumulativos cobrados destacadamente como mero depositário** (IPI, ICMS-ST) e o ajuste a valor presente. Entram **integrais** (sem presunção): ganhos de capital, rendimentos e ganhos líquidos de aplicações financeiras, demais receitas e resultados positivos não abrangidos pela receita bruta, inclusive juros Selic de restituição, locação de imóvel fora do objeto, mútuo, variações monetárias ativas, recuperações de custos. Desconto **condicional** não deduz.

**NORMA.** Lei 9.430/1996, art. 25, I, red. Lei 12.973/2014 (receita bruta do art. 12 do DL 1.598 "deduzida das devoluções e vendas canceladas e dos descontos incondicionais concedidos") e II (ganhos de capital, aplicações financeiras, demais receitas, AVP, "demais valores determinados nesta Lei") — *lido*; art. 51 (juros do art. 9º da Lei 9.249 e rendimentos de operações financeiras "serão adicionados ao lucro presumido") e art. 53 (valores recuperados) — *lido*; art. 29 (mesma estrutura para a CSLL) — *lido*. DL 1.598/1977, art. 12, caput (I a IV), § 1º (receita líquida: devoluções, descontos incondicionais, tributos, AVP), § 4º ("não se incluem os tributos não cumulativos cobrados, destacadamente, do comprador [...] na condição de mero depositário") e § 5º ("incluem-se os tributos sobre ela incidentes") — *lido*. Lei 9.249, art. 15, caput e art. 20, caput — *lido*. IN 1.700, art. 215, § 3º, I, "a" a "h" (lista das receitas integrais) — *cópia*. RIR/2018, art. 595 — *lido*.

**O que o primeiro corte tem e o que fica de fora.** `receita.py:174-232` compõe a receita do mês por `valor_servico` (`vServ`) das escriturações **efetivadas** mais receita informada confirmada, por mercado. Para o presumido isso significa: (1) a base de presunção sai de `vServ − vDescIncond` (o desconto incondicional é dedução legal; o condicional e o ISS **não** são) — confirmar se `vDescIncond` está gravado na escrituração, o que **não verifiquei** no `models.py`; (2) notas **substituídas/canceladas** reduzem no trimestre de origem (vendas canceladas), como já se faz no estorno (`receita.py:21-27`); (3) **ficam de fora**: receitas de mercadorias (NF-e), receitas financeiras, ganhos de capital, aluguéis, recuperações, qualquer receita sem NFS-e. Exportação de serviços **entra** na receita bruta do presumido normalmente (não há exclusão; diferente do PIS/Cofins) — **inferência** forte, grau alto.

**Como avisar.** A apuração do trimestre só fica "completa" quando o contador **declarar** as receitas do art. 25, II (valor com documento de suporte **ou** a afirmação explícita "não houve receitas integrais neste trimestre"). Sem a declaração, a apuração é exibida como **"parcial — só receita de NFS-e prestadas; receitas do art. 25, II não declaradas"** e não pode ser marcada como conferida. Mesma mecânica para "receita de mercadorias / outras receitas de presunção não escrituradas": campo manual por atividade com documento de suporte (reaproveitando `ReceitaInformada`, que já exige motivo e suporte — `receita.py:762-872`), com a atividade de presunção obrigatória.

**Grau de segurança:** alto na norma; médio na leitura dos campos da escrituração (não abri `models.py`).

## 6. Dedução das retenções sofridas

**Resposta curta.** IRPJ: deduz-se "o imposto pago ou retido na fonte sobre as receitas que integraram a base de cálculo" — RIR/2018, art. 599 (fundado na Lei 8.981, art. 34, e Lei 9.430, art. 51, parágrafo único) e IN 1.700, art. 221, § 1º. CSLL: deduz-se "a CSLL retida na fonte sobre receitas que integraram a base" — IN 1.700, art. 222, parágrafo único, I; o fundamento legal é a Lei 10.833, art. 36 (retenções dos arts. 30, 33 e 34 "consideradas como antecipação do que for devido [...] em relação ao imposto de renda e às respectivas contribuições") e, para órgãos federais, a Lei 9.430, art. 64, §§ 3º e 4º ("somente poderá ser compensado com o que for devido em relação à mesma espécie"). **A NFS-e não permite separar a CSLL** dentro de `vRetCSLL`; só se pode **estimar** quando `tpRetPisCofins = 3`.

**NORMA.** RIR, art. 599, caput e parágrafo único (excesso → compensação, Lei 9.430, art. 74) — *lido*. Lei 8.981, art. 34, red. Lei 9.065/1995 — *lido*. Lei 9.430, art. 51, parágrafo único (IRRF sobre financeiras "antecipação") — *lido*. Lei 10.833, art. 31, caput: 4,65% = 1% CSLL + 3% Cofins + 0,65% PIS; § 2º: beneficiária de isenção de uma das contribuições → alíquota só das não isentas — *lido*. Art. 36 — *lido*. Lei 9.430, art. 64, §§ 3º a 6º (órgãos federais: IR = 15% × percentual do art. 15 sobre o pago; CSLL = 1%) — *lido*. IN 1.700, arts. 221, § 1º e 222, parágrafo único — *cópia*. NFS-e: `vRetIRRF` e `vRetCSLL` em `infDPS/valores/trib/tribFed`; desde a NT 007/2026 "os três valores devem ser somados e lançados exclusivamente em `vRetCSLL`, com `tpRetPisCofins = 3`" (consulta de serviços tomados, item 3, P&R NFS-e 13.1 — *lido* naquela consulta, não reaberto hoje).

**Como separar a CSLL.** Não há como pela nota. Três regras, nesta ordem:
1. `tpRetPisCofins = 8` (só CSLL retida): `CSLL_retida = vRetCSLL` — exata.
2. `tpRetPisCofins = 3` (PIS+Cofins+CSLL): `CSLL_retida_estimada = vRetCSLL × 1,00 / 4,65`, marcada **"estimada — conferir no comprovante de retenção / R-4020 do tomador"**. Só vale se o tomador reteve as três às alíquotas-padrão; se houver isenção parcial (art. 31, § 2º) a proporção muda.
3. Códigos 4, 5, 6, 7, 9 e nota ambígua (`vPis`/`vCofins` preenchidos junto com código de retenção): "**a classificar**", sem valor.
A dedução **só entra na apuração depois que o contador confirma** o valor (campo editável com trilha); o produto propõe, não deduz. Retenção de órgão público federal (Lei 9.430, art. 64) vem com IR calculado pelo percentual de presunção e CSLL 1% — a nota nacional não distingue a hipótese; tratar como as demais, com o aviso. Competência da dedução: a retenção abate no trimestre em que a **receita integrou a base** (texto do art. 599 e do art. 222) — para quem apura por competência, o trimestre da `dCompet`, independentemente da data do pagamento. Se IRRF > IRPJ do trimestre: **saldo negativo**, "PER/DCOMP", nunca compensado automaticamente no trimestre seguinte.

**Grau de segurança:** alto na norma; **médio** na estimativa 1/4,65 (depende de fato fora da nota) — **hipótese 3**.

## 7. Quotas (Lei 9.430, art. 5º)

**Resposta curta.** Quota única até o último dia útil do mês seguinte ao trimestre; opção por até **3 quotas mensais, iguais e sucessivas**, vencendo no último dia útil dos três meses seguintes; **nenhuma quota abaixo de R$ 1.000,00**; imposto **abaixo de R$ 2.000,00** paga-se em quota única. Juros: Selic acumulada **a partir do 1º dia do 2º mês seguinte** ao trimestre até o último dia do mês anterior ao pagamento, **mais 1% no mês do pagamento** — logo a **1ª quota não tem juros**, a **2ª tem só 1%**, a **3ª tem Selic do 2º mês + 1%**. Vale para a CSLL por força do art. 28. Sobre feriados: a lei só diz "último dia útil"; **não achei norma da RFB dizendo quais feriados contam** — proponho calendário com feriados nacionais por lei, mais tabela editável, e etiqueta "a conferir".

**NORMA.** Lei 9.430, art. 5º, caput e §§ 1º a 4º (§ 4º: incorporação/fusão/cisão/extinção sem a opção por quotas) — *lido*; art. 28 (aplicam-se à CSLL "os arts. 1º a 3º, 5º a 14...") — *lido*. Feriados nacionais: Lei 662/1949, art. 1º, red. Lei 10.607/2002: 1º/jan, 21/abr, 1º/mai, 7/set, 2/nov, 15/nov, 25/dez — *lido*; Lei 6.802/1980, art. 1º (12 de outubro) — *lido*. **Não conferidos hoje:** Lei 14.759/2023 (20 de novembro como feriado nacional — a tabela precisa dele desde 2024), Lei 9.093/1995 (feriados civis estaduais e religiosos municipais), Portaria MGI de pontos facultativos. A agenda tributária da RFB (gov.br, janeiro/2026) **não traz nota** sobre vencimento em dia não útil (WebFetch hoje). Para "último dia útil do mês", um fim de semana ou feriado **antecipa** o vencimento (não há dia útil seguinte dentro do mês) — leitura literal, grau alto.

**Proposta para o produto.** Exibir quota única e o plano em 3 quotas (`quota = devido/3` quantizado; resíduo na 3ª), recusando o plano quando `devido < 2.000` ou `quota < 1.000`. Juros das quotas: 2ª = 1%; 3ª = "Selic de [mês] + 1%" com a Selic **informada pelo contador ou importada com fonte e data** — o produto não embute taxa. Vencimentos calculados com sábado, domingo e feriados nacionais da tabela (fonte e vigência em cada linha), com etiqueta "**calendário a conferir**" em todo vencimento que caia em véspera de feriado local, Carnaval, Sexta-feira Santa ou Corpus Christi (dias sem expediente bancário que não são feriados nacionais por lei). Nunca gerar DARF; só a conferência de valores e datas.

**Grau de segurança:** alto na mecânica; médio-baixo no calendário.

## 8. Códigos de DARF

**Resposta curta.** Há fonte oficial: as tabelas de códigos de receita da RFB em gov.br listam **2089/01 — "IRPJ - Lucro Presumido"** (trimestral) e **2372/01 — "CSLL - Lucro Presumido ou Arbitrado - Entidade não financeira"** (trimestral). No DARF usa-se o código de 4 dígitos (2089 e 2372); a extensão (/01) é da DCTF/MIT. Variações: 2089/02 (PJ exclusivamente prestadora de serviços — diferença de imposto postergado), 2089/08 e 2372/08 (SCP), 2089/10 e 2372/10 (postergação), 2089/12 e 2372/12 (Rota 2030), 2372/03 (arbitrado, financeira).

**NORMA.** Páginas gov.br/receitafederal "Tabelas de códigos e extensões — IRPJ" e "— CSLL", atualizadas em 12/03/2024 (WebFetch hoje) — *lido*. Sites de fornecedor e fóruns confirmam, mas são *secundários*.

**Proposta para o produto.** Mostrar "2089 — IRPJ Lucro Presumido" e "2372 — CSLL Lucro Presumido" com a fonte (URL e data de consulta) ao lado, e mantê-los em tabela parametrizável com vigência. Não usar "a conferir" aqui, porque a fonte é oficial; usar "a conferir" apenas para SCP e para empresa que tenha ultrapassado o limite de receita (2089/02), ambos fora do corte.

**Grau de segurança:** alto.

## 9. Regime de caixa no presumido

**Resposta curta.** Sim: no primeiro corte, **recusar com nome**. O regime de caixa exige reconhecer a receita "na medida do recebimento", com livro Caixa indicando "em registro individual, a nota fiscal a que corresponder cada recebimento" (ou conta contábil específica), e tratar adiantamentos como receita do faturamento/entrega/conclusão, o que vier antes — isso é contas a receber, que o produto não tem (o mapa fiscal já registra isso para o sistema de referência: `mapa-funcional-fiscal.md:347-354`).

**NORMA.** IN 1.700/2017, art. 223, caput e §§ 1º a 4º (§ 4º: receita computada em período posterior ao devido → IRPJ/CSLL com juros e multa); art. 223-A (passagem de caixa para competência: reconhecer em dezembro as receitas auferidas e não recebidas) — *cópia*. Lei 9.718, art. 13, § 2º (limite de opção considerado "segundo o regime de competência ou de caixa, observado o critério adotado") — *lido*.

**Proposta para o produto.** Parâmetro "critério de reconhecimento da receita no presumido" por empresa e ano (competência / caixa); com "caixa", a apuração é recusada com a mensagem nomeando a IN 1.700, art. 223, e a falta de contas a receber. Não existe meio-termo (apurar por competência para quem optou pelo caixa é erro, não aproximação).

**Grau de segurança:** alto.

## 10. ADI 7936 e liminares — cálculo duplo

**Resposta curta.** O produto calcula **sempre as duas colunas** (com e sem o acréscimo) e mostra a **"parcela LC 224"** como linha própria em cada tributo e trimestre; o contador registra, por empresa, tributo e período, uma **decisão judicial** (número do processo, juízo, data, abrangência, se há depósito) que **suspende a exigibilidade da parcela**, e o produto passa a exibir "a pagar" = coluna sem acréscimo, mantendo a parcela suspensa visível e acumulada. O produto não opina sobre a ação.

**NORMA e fatos.** ADI 7936, CNS, relator Min. Luiz Fux, distribuída em 02/2026, impugna o art. 4º da LC 224, arts. 2º e 12 do Decreto 12.808 e arts. 2º, 4º, 13, 14 e 15 da IN 2.305 (notícia STF de 18/02/2026, atualizada em 16/03/2026 — *lido*); ADI 7944 da OAB sobre a mesma matéria (mesma notícia). Andamento do STF (incidente 7501902): informações da Presidência/Senado em 03-04/2026, AGU em 07/04/2026, PGR em 22/04/2026, última manifestação em **27/08/2026**; **nenhuma decisão cautelar ou de mérito visível** até hoje — *lido*. Liminares de 1ª instância (ex.: 1ª Vara Federal de Resende, MS 5000259-79.2026.4.02.5116) e relato de centenas de pedidos negados — *secundário*. CTN, art. 151, IV e V (suspensão da exigibilidade por liminar/tutela) — *não conferido hoje*, conceito estável.

**Proposta para o produto.** (1) Colunas "sem LC 224", "com LC 224" e "parcela LC 224" em toda memória. (2) Cadastro de "medida judicial" (processo, órgão, data, tributo(s), períodos, depósito judicial sim/não, documento de suporte) com trilha; só com cadastro ativo a tela mostra "a recolher sem a parcela — exigibilidade suspensa (decisão X)". (3) Aviso permanente: "ADI 7936 e 7944 sem decisão até [data da última conferência]; liminar vale só para a impetrante". (4) Se houver depósito judicial, mostrar a parcela como "depositar" em vez de "suspensa". (5) Nunca escolher "sem acréscimo" por padrão.

**Grau de segurança:** alto (decisão de produto; fatos processuais lidos no portal).

## 11. Rotina do escritório que o produto deve espelhar

**Resposta curta.** Quem informa a atividade (e, portanto, o percentual) é **o contador, no cadastro**, não a nota. Nota de serviço com várias atividades é **rateada manualmente** pelo contador em valores por atividade (a NFS-e nacional tem um serviço por DPS, então o caso real é raro: a nota já nasce por `cTribNac`; o rateio aparece em notas antigas ou em receitas informadas). A memória que o contador espera é a mesma que ele faria à mão: por trimestre e atividade, receita bruta → deduções → base presumida (normal e acrescida) → receitas integrais → base total → tributo → adicional → retenções → a pagar → quotas, com a lista de notas que compõem cada linha.

**O que isso tem de fonte.** O manual do sistema de referência **não está no repositório** (`fontes-de-referencia.md:81-85`) e eu **não o li**. O resumo reescrito no mapa fiscal (`mapa-funcional-fiscal.md:321-362`) diz que, no sistema de referência, "a regra que liga o documento ao tratamento tributário" é um **cadastro** (o "acumulador") definido pelo escritório, e que a cadeia é parâmetros da empresa → impostos por vigência → acumuladores → lançamento fiscal → apuração → guias e integração contábil. Ou seja: lá também é o contador que classifica; o documento não decide. O produto já faz isso para o Simples (`natureza` da escrituração em `receita.py:9-10`, `atividade` da `ReceitaInformada` em `receita.py:235-248` e `:801-807`, DL-075/HI-68). A atividade de presunção pode ser um atributo da mesma `natureza`/`atividade` — **inferência de produto**, a confirmar com o Fred.

**Proposta para o produto.**
1. Cadastro "atividade de presunção" por empresa (item 2), com vigência; cada natureza de escrituração e cada receita informada aponta para uma. Sem atividade → a nota fica "sem atividade de presunção" e a apuração do trimestre é recusada nomeando as notas (mesmo padrão de `receitas_informadas_sem_situacao_iss`, `receita.py:287-297`).
2. Sugestão automática a partir de `cTribNac`/natureza **só como sugestão**, com a mesma regra da consulta anterior (XML sugere, contador decide).
3. Nota com várias atividades: rateio manual em valores (não percentuais), somando exatamente `vServ − vDescIncond`, com trilha; a nota original permanece íntegra.
4. Memória de cálculo em três camadas: (a) demonstrativo do trimestre (por atividade e total, as três colunas do item 10); (b) controle do limite LC 224 do ano (item 4); (c) conciliação: lista de escriturações e receitas informadas por atividade, somando à receita bruta usada — relatório de **conferência**, classe definida em `docs/projeto/personalizacao-de-relatorio.md` (não reli hoje).
5. Hipóteses de rotina para o Fred (quem classifica, quando confere, se usa 3 quotas) — abaixo.

**Grau de segurança:** médio (rotina; manual não lido).

## 12. Fora do primeiro corte — pendências nomeadas

Fora, com segurança: regime de caixa (item 9); receitas do art. 25, II além do campo manual (importação de extratos, ganhos de capital calculados); receita de mercadorias e NF-e; atividade imobiliária (RIR art. 224; Lei 9.249, art. 15, § 4º); serviços hospitalares com verificação dos requisitos; SCP; empresa com alíquota majorada de CSLL; obrigatoriedade do Lucro Real por excesso do limite de R$ 78 milhões (Lei 9.718, art. 13 — *lido*; art. 14 — não lido na íntegra) e mudança de regime no ano; casos I e II do § 5º com dedução maior que o devido (PER/DCOMP); saldo negativo de IRRF/CSLL retida (só exibir); bônus de adimplência (IN 1.700, art. 222, parágrafo único, II); juros Selic das quotas com taxa automática; geração de DARF, MIT/DCTFWeb, ECF (bloco do presumido) e PER/DCOMP; filiais com apuração centralizada (regra não conferida); Lucro Arbitrado; incorporação, fusão, cisão e extinção (Lei 9.430, art. 5º, § 4º); retenção de órgãos públicos federais com cálculo próprio (Lei 9.430, art. 64, § 5º); calendário de feriados além dos nacionais por lei.

---

## Hipóteses para o Fred validar

1. **Quem classifica a atividade de presunção** de cada nota/receita no escritório hoje, e se a classificação é feita na entrada (cadastro) ou na apuração.
2. **Notas com mais de uma atividade**: acontecem na carteira (notas antigas, ABRASF)? Como são rateadas hoje?
3. **Separação da CSLL em `vRetCSLL`** pela proporção 1,00/4,65 quando `tpRetPisCofins = 3`, sempre como "estimada" e confirmada pelo contador — o escritório aceita esse fluxo ou prefere digitar o valor do comprovante?
4. **Competência da dedução da retenção**: trimestre em que a receita integrou a base (texto do RIR art. 599), e não o trimestre do pagamento — é assim que o escritório faz?
5. **Arredondamento por linha** da memória (centavos em cada parcela, resíduo na última linha do rateio), aceitando diferença de centavos contra o cálculo sem arredondar — ou o escritório arredonda só o total?
6. **Quotas**: o escritório usa 3 quotas em algum cliente? Se não, mostrar o plano em quotas é útil ou ruído?
7. **Limite de R$ 5 milhões por empresa (CNPJ raiz)**, somando filiais — confere com a prática?
8. **Declaração explícita "não houve receitas integrais no trimestre"** como condição para a apuração sair de "parcial" — o escritório aceita essa fricção?
9. **Calendário**: o escritório antecipa vencimento federal em feriado municipal/estadual ou considera só nacionais? Se houver DARF que já caiu nesse caso, qual foi a prática?
10. **Empresas com decisão judicial** sobre a LC 224 na carteira: há alguma? Com depósito?

## Pendências

1. Texto **oficial** das INs 2.305/2025 e 2.306/2026 (e 1.700/2017) em `normas.receita.fazenda.gov.br` — hoje só a casca do portal; as cópias são íntegras mas terceiras. Inclui a redação **original** dos incisos I e II do art. 15 (revogados).
2. Lei 14.759/2023 (20/11), Lei 9.093/1995 e Lei 9.779/1999, art. 15 — abrir no Planalto antes de codificar calendário e filiais.
3. Nota da RFB (agenda tributária ou IN) sobre vencimento em dia não útil e feriados locais — não localizada; a planilha anexa da agenda não foi aberta.
4. Lei 9.718, art. 14 (obrigatoriedade do Real) — ler na íntegra ao tratar a mudança de regime.
5. Conferir no `apps/fiscal/models.py` se `vDescIncond` e `tpRetPisCofins` estão gravados na escrituração (a consulta anterior cita `models.py:131-243`, não reaberto hoje).
6. Executar em Python (teste) os casos I e II do § 5º, que não rodei.
7. Andamento das ADIs 7936 e 7944 deve ser reconferido na data de cada etapa; o produto deve guardar a "data da última conferência" exibida no aviso.
8. Leiaute do bloco do Lucro Presumido na ECF (para a conciliação futura) — não pesquisado.

---

## Tabela-resumo

| # | Tema | Resposta | Fonte principal | Marca | Segurança |
| --- | --- | --- | --- | --- | --- |
| 1 | Alíquotas | IRPJ 15% + adicional 10% sobre > R$ 20 mil × meses (só IRPJ); CSLL 9% | Lei 9.249 art. 3º; Lei 7.689 art. 3º; IN 1.700 arts. 221-222 | lido / cópia | Alta |
| 2 | Percentuais CSLL | 32% (art. 15 § 1º III), 38,4% (ESC), **12% residual** — combustível, passageiros e hospitalar = 12% | Lei 9.249 art. 20 | lido | Alta |
| 3 | LC 224 | ×1,10; IRPJ e CSLL; IRPJ 1T/2026, CSLL 2T/2026; limite CSLL 2026 = 3,75 mi | LC 224 art. 4º §§ 4º VII e 5º, art. 14; CF 150 § 1º, 195 § 6º; Decreto 12.808 art. 12; P&R RFB 11-13 | lido | Alta |
| 4 | IN 2.305/2.306 | L_t = 1,25 mi + sobra; E_t = max(0, R_t − L_t); rateio por atividade; 4º tri casos I/II/III; § 9º início/fim; nada sobre filiais | IN 2.305 art. 15 §§ 1º-9º red. IN 2.306; P&R 14 | cópia / lido | Alta (fórmula); média (filiais) |
| 5 | Base | Deduz devoluções, cancelamentos e descontos incondicionais; ISS entra; integrais: financeiras, ganhos de capital, demais | Lei 9.430 arts. 25, 29, 51, 53; DL 1.598 art. 12; IN 1.700 art. 215 § 3º | lido / cópia | Alta |
| 6 | Retenções | IRRF: RIR 599 / IN 1.700 art. 221 § 1º; CSLL: Lei 10.833 art. 36, Lei 9.430 art. 64 §§ 3º-4º, IN 1.700 art. 222; CSLL em `vRetCSLL` só estimável (1/4,65 se código 3) | idem | lido / cópia | Alta (norma); média (estimativa) |
| 7 | Quotas | Única ou 3; ≥ R$ 1.000; < R$ 2.000 única; 2ª = 1%; 3ª = Selic + 1%; CSLL idem (art. 28); feriados nacionais por lei, resto "a conferir" | Lei 9.430 arts. 5º, 28; Leis 662 e 6.802 | lido | Alta / média-baixa (calendário) |
| 8 | DARF | 2089/01 e 2372/01, fonte oficial | gov.br tabelas DCTF | lido | Alta |
| 9 | Caixa | Recusar com nome (IN 1.700 art. 223) | IN 1.700 arts. 223, 223-A | cópia | Alta |
| 10 | ADI 7936 | Duas colunas + parcela LC 224 + cadastro de decisão judicial; sem decisão no STF até 27/08/2026 | Portal STF | lido / secundário | Alta |
| 11 | Rotina | Contador classifica; rateio manual; memória em 3 camadas | Mapa fiscal (repo) + rotina usual | inferência | Média |
| 12 | Fora do corte | Lista nomeada acima | — | — | — |

## O que verifiquei, o que inferi, o que não consegui determinar

**Verificado (texto aberto hoje).** LC 224 art. 4º §§ 3º-5º e art. 14; Lei 9.249 arts. 3º, 15, 16, 19, 20; Lei 9.430 arts. 1º, 5º, 6º, 25, 26, 28, 29, 51-53, 64; Lei 7.689 art. 3º (todas as redações); Lei 8.981 art. 34; Lei 9.718 art. 13; Lei 10.833 arts. 31, 36; DL 1.598 art. 12; RIR arts. 595, 599; Decreto 12.808 arts. 11-12; CF arts. 150 (III, § 1º) e 195 § 6º; Leis 662 e 6.802 — Planalto. P&R RFB V5 (30/07/2026) itens 11, 11.1, 12, 13, 14; tabelas de códigos IRPJ e CSLL — gov.br. ADI 7936: notícia e andamento — STF. Repositório: `DL-067:472-489, 969`, consulta de serviços tomados, `receita.py` integral, `mapa-funcional-fiscal.md:293-388`, `fontes-de-referencia.md:48-96`; `Glob` de `apps/fiscal/*.py`. **Cópias íntegras:** IN 2.306 (arts. 1º-3º completos), IN 2.305 arts. 13-15 (redação atual) e 19, IN 1.700 arts. 215, 221, 222, 223, 223-A. **Cálculo:** script Python executado (saída transcrita no item 4).

**Inferido.** IRRF abate do imposto total inclusive adicional; exportação de serviços entra na receita bruta do presumido; limite de R$ 5 mi por PJ somando filiais; estimativa da CSLL retida por 1/4,65; atividade de presunção como atributo da natureza/atividade já existente; rotina do escritório (classificação pelo contador, rateio manual).

**Não determinado.** Redação original dos incisos I e II do art. 15 da IN 2.305; norma da RFB sobre feriados locais no vencimento; Lei 14.759/2023, Lei 9.093/1995, Lei 9.779 art. 15 (não abertos); campos `vDescIncond`/`tpRetPisCofins` no `models.py`; comportamento numérico dos casos I e II do § 5º (não executado); manual do sistema de referência (fora do repositório).

Sources:
- [LC 224/2025 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp224.htm)
- [Lei 9.249/1995 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l9249.htm)
- [Lei 9.430/1996 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l9430.htm)
- [Lei 7.689/1988 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l7689.htm)
- [Lei 8.981/1995 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l8981.htm)
- [Lei 9.718/1998 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l9718.htm)
- [Lei 10.833/2003 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833.htm)
- [Decreto-Lei 1.598/1977 — Planalto](https://www.planalto.gov.br/ccivil_03/decreto-lei/del1598.htm)
- [Decreto 9.580/2018 (RIR) — Planalto](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/decreto/D9580.htm)
- [Decreto 12.808/2025 — Planalto](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/D12808.htm)
- [Constituição Federal — Planalto](https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm)
- [Lei 662/1949 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l0662.htm)
- [Lei 6.802/1980 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l6802.htm)
- [Perguntas e Respostas — Redução dos incentivos e benefícios tributários, V5 (30/07/2026) — RFB](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/beneficios-fiscais/perguntas-e-respostas-reducao-dos-incentivos-e-beneficios-tributarios-v5-final.pdf)
- [Tabela de códigos e extensões — IRPJ — RFB](https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/dctf/tabelas-de-codigos-extensoes/irpj)
- [Tabela de códigos e extensões — CSLL — RFB](https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/dctf/tabelas-de-codigos-extensoes/csll)
- [Agenda Tributária janeiro/2026 — RFB (sem nota sobre feriados)](https://www.gov.br/receitafederal/pt-br/assuntos/agenda-tributaria/2026/janeiro)
- [IN RFB 2.306/2026 — cópia normaslegais](https://www.normaslegais.com.br/legislacao/instrucao-normativa-rfb-2306-2025.htm)
- [IN RFB 2.305/2025 (redação atual) — cópia normaslegais](https://www.normaslegais.com.br/legislacao/instrucao-normativa-rfb-2305-2025.htm)
- [IN RFB 1.700/2017 — cópia normaslegais](https://www.normaslegais.com.br/legislacao/instrucao-normativa-rfb-1700-2017.htm)
- [ADI 7936 — notícia STF 18/02/2026](https://noticias.stf.jus.br/postsnoticias/confederacao-contesta-lei-que-alterou-regime-do-lucro-presumido/)
- [ADI 7936 — detalhe do processo (incidente 7501902) — STF](https://portal.stf.jus.br/processos/detalhe.asp?incidente=7501902)
- [ADI 7944 (CNC) — notícia STF](https://noticias.stf.jus.br/postsnoticias/cnc-questiona-normas-que-elevaram-base-de-calculo-do-lucro-presumido/)
- [Liminar de Resende/RJ — Barbieri Advogados (secundário)](https://www.barbieriadvogados.com/lucro-presumido-liminar/)
- [ADI 7936 — PR Advogados (secundário)](https://pradvogados.com.br/2026/02/19/adi-7936-discussao-sobre-a-inconstitucionalidade-do-adicional-de-10-no-lucro-presumido-instituido-pela-lc-224-2025/)
- [IN 2.306 comentada — Econet (secundário)](https://blog.econeteditora.com.br/acrescimo-10-lucro-presumido-novas-regras/)
- [Códigos 2089/2372 — Contabilizei (secundário)](https://www.contabilizei.com.br/contabilizei-responde/qual-o-codigo-da-receita-para-pagamento-de-darf/)
- [Portaria MGI feriados 2026 — gov.br/gestao](https://www.gov.br/gestao/pt-br/assuntos/noticias/2025/dezembro/confira-o-calendario-oficial-de-feriados-nacionais-e-pontos-facultativos-em-2026)
- Não alcançados hoje: [normas.receita (casca Angular, sem texto)](http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=81268) · [Câmara legin LC 224 (404)](https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-224-26-dezembro-2025-797645-publicacaooriginal-176660-pl.html)
