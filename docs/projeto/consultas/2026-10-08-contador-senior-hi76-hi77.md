# Consulta ao contador-senior sobre HI-76 e HI-77 — 08/10/2026

Quarta consulta do `arquiteto-senior` ao `contador-senior` (Fable), por ordem do
Fred (RC-164), depois da reconferência da DL-074. Registro integral da resposta
(só a frase inicial de transição do agente foi omitida). Efeito: HI-76 mantida,
HI-77 **ajustada**, PE nova sobre a alíquota no § 5º, e a recusa do Simples
iniciado antes da abertura (R4 da reconferência) confirmada — ver
[requisitos.md](../requisitos.md).

Terceira consulta do `arquiteto-senior` ao `contador-senior`, por ordem do Fred, para fechar os achados A1 (HI-76) e A5 (HI-77) da auditoria da DL-074 e a regra de consistência "início do Simples antes da abertura". **Tudo abaixo é HIPÓTESE até o Fred validar.**

**Legislação validada até:** 08/10/2026 · **Competências em análise:** 2025–2026 (não tratei 2027; os dispositivos citados trazem a anotação "modificação prevista para 01/01/2027 — Res. CGSN 190/2026", cujo texto não li) · **Grau de segurança geral:** alto nos itens 1, 2 e 4; alto no item 3 quanto ao limite comparado, **baixo quanto à mecânica exata da alíquota** (ver "não determinado").

**O que abri hoje (todos HTTP 200, texto extraído e lido nos trechos citados):**
- Res. CGSN 140/2018 consolidada, PDF íntegro em guiatributario.net — *cópia* (texto íntegro em site terceiro; o oficial no sijut2consulta não renderiza sem JS).
- Manual do PGDAS-D e DEFIS, versão 17/06/2025, PDF oficial da RFB — *lido*.
- LC 123/2006 no Planalto, via `curl` com User-Agent de navegador — *lido*.

Marcas: *lido* = texto oficial aberto hoje; *cópia* = texto íntegro em site terceiro; *secundário*; *não conferido*.

---

## 1. HI-76 — RBT12 proporcional atravessando a virada do ano

**Resposta curta.** Sim. A regra proporcional vale nos **12 primeiros meses de atividade contados do mês da abertura no CNPJ**, sem qualquer corte na virada do ano-calendário. No exemplo (abertura e opção em 15/10/2025; out 10.000, nov 20.000, dez 30.000, jan 40.000), o PA 02/2026 é o **5º mês de atividade** e o RBT12 é **100.000 / 4 × 12 = 300.000,00** (§ 3º), não 100.000. O § 1º passa a valer no **13º mês de atividade = PA 10/2026**; e nesse PA as duas regras coincidem numericamente (média de 12 meses × 12 = soma dos 12 meses), de modo que a transição não produz salto.

**NORMA.**
- Res. CGSN 140, art. 22, § 2º (*cópia*): "No caso de início de atividade **no próprio ano-calendário da opção** pelo Simples Nacional, para efeito de determinação da alíquota **no 1º (primeiro) mês de atividade**, o sujeito passivo utilizará, como receita bruta total acumulada, a receita auferida no próprio mês de apuração multiplicada por 12 (doze)." (LC 123, art. 18, § 2º)
- Art. 22, § 3º (*cópia*): "Na hipótese prevista no § 2º, para efeito de determinação da alíquota **nos 11 (onze) meses posteriores ao do início de atividade**, o sujeito passivo utilizará a média aritmética da receita bruta total auferida nos meses anteriores ao do período de apuração, multiplicada por 12 (doze)."
- Art. 22, § 1º (*cópia*): regra geral — "receita bruta total acumulada auferida nos 12 (doze) meses anteriores ao do período de apuração".
- Art. 2º, V (*cópia*): "data de início de atividade a data de abertura constante do CNPJ".
- LC 123, art. 18, § 2º (*lido*, Planalto, red. LC 147/2014): "Em caso de início de atividade, os valores de receita bruta acumulada constantes das tabelas dos Anexos I a VI desta Lei Complementar devem ser proporcionalizados ao número de meses de atividade no período."
- Manual do PGDAS-D, item 8.3 (*lido*, p. 78): "Receita Bruta Acumulada Proporcionalizada (RBT12p) é um critério utilizado **nos 12 primeiros meses de atividade** da empresa [...] Assim, nos 12 primeiros meses de atividade, o enquadramento na tabela de faixas de alíquotas é feito com base na [RBT12p]." Reitera: 1º mês → receita do mês × 12; "nos 11 (onze) meses posteriores ao do início de atividade" → média dos meses anteriores × 12.

**Leitura.** A expressão "no próprio ano-calendário da opção" do § 2º qualifica a **hipótese de entrada** (abertura e opção no mesmo ano), não a duração da regra; a duração é dada pelo próprio texto — "1º mês de atividade" + "11 meses posteriores" = 12 meses de atividade — e o Manual a nomeia literalmente de "12 primeiros meses de atividade". Nenhum dos dispositivos menciona 31 de dezembro ou ano-calendário como fronteira. O mês de abertura conta como 1º mês independentemente do dia: o Manual 8.3 trata PA 05/2018 de empresa "aberta em fevereiro/2018" como "quarto mês de atividade", e o item 8.2.1 (fator r) soma "desde o mês da data de abertura" (*lido*, p. 76). Mês sem receita entra na média como zero (Manual 8.3, março/2018 = R$ 0,00 dividido por 3 meses).

**Cronograma do exemplo (hipótese):**

| PA | Mês de atividade | Regra | RBT12 |
| --- | --- | --- | --- |
| 10/2025 | 1º | § 2º | 10.000 × 12 = 120.000 |
| 11/2025 | 2º | § 3º | 10.000/1 × 12 = 120.000 |
| 12/2025 | 3º | § 3º | 30.000/2 × 12 = 180.000 |
| 01/2026 | 4º | § 3º | 60.000/3 × 12 = 240.000 |
| **02/2026** | **5º** | **§ 3º** | **100.000/4 × 12 = 300.000** |
| ... | ... | § 3º | média × 12 |
| 09/2026 | 12º | § 3º | Σ(out/25–ago/26)/11 × 12 |
| **10/2026** | **13º** | **§ 1º** | Σ(out/25–set/26) — igual a média de 12 × 12 |

**Exemplo do Manual com abertura em ano anterior:** **não existe.** Busquei no PDF "imediatamente anterior", "ano anterior", "13º", "décimo terceiro", "aberta em", "abertura em": os exemplos 3 a 12 (p. 108 em diante) usam empresas "aberta em janeiro/2018" (Exemplo 3, que só vai até março/2018), "aberta em 2009" ou "aberta em 2012", todas sem atravessar a virada dentro da janela proporcional. O item 6.3 (*lido*, p. 19) só diz que o quadro de receitas anteriores não aparece para quem já era optante nos 12 PA anteriores ou cujo mês de início coincide com o PA. Portanto a afirmação "a regra atravessa o ano" é **leitura literal do texto + definição do Manual**, não exemplo oficial.

**Grau de segurança:** **alto** na regra (texto sem fronteira de ano, Manual nomeia "12 primeiros meses de atividade"); **médio** apenas por não haver exemplo oficial cruzando a virada — se o Fred quiser certeza operacional, uma simulação no PGDAS-D de empresa real aberta em out/2025 confirma em um minuto.

---

## 2. § 4º — abertura no ano imediatamente anterior ao da opção

**Resposta curta.** Sim: a proporcional (regra do § 3º) segue **até completar 12 meses de atividade** e o § 1º entra **no 13º mês de atividade**. Para abertura em 05/03/2025 e opção com efeitos em 01/01/2026: mar/25 = 1º mês ... dez/25 = 10º, **PA 01/2026 = 11º** (média de mar–dez/25, 10 meses, × 12), **PA 02/2026 = 12º** (média de 11 meses × 12), **PA 03/2026 = 13º → § 1º** (soma mar/25–fev/26). O implementado está de acordo com o texto.

**NORMA.**
- Res. 140, art. 22, § 4º (*cópia*): "Na hipótese de início de atividade em ano-calendário imediatamente anterior ao da opção pelo Simples Nacional, o sujeito passivo utilizará: I - a regra prevista no § 3º **até completar 12 (doze) meses de atividade**; e II - a regra prevista no § 1º **a partir do décimo terceiro mês de atividade**."
- Base de competência: LC 123, art. 2º, I e § 6º e art. 18, § 2º (citados no próprio § 4º).
- Receitas dos meses em que a empresa estava em outro regime **entram** na média e na soma: Manual 6.3 (*lido*, p. 18–19) exige, na primeira apuração, "o valor da receita auferida nos meses anteriores à opção" pelo regime de competência, e alerta que informar zero por engano distorce RBT12/RBA/RBAA.
- Fronteira do § 4º: só vale se a abertura foi no **ano imediatamente anterior**. Abertura em 2024 com opção em 01/2026 já é 13º mês ou mais em qualquer PA de 2026, logo § 1º direto — coerente.

**Nota.** O § 2º fala em "no próprio ano-calendário da opção" e o § 4º em "ano-calendário imediatamente anterior ao da opção". O que está entre os dois (opção em janeiro por empresa aberta em dezembro do ano anterior, por exemplo) é § 4º. Na prática, a opção em janeiro produz efeitos em 1º de janeiro (Res. 140, art. 6º, § 1º, *cópia*), então "ano da opção" = ano dos efeitos.

**Grau de segurança:** **alto** (texto literal; não há exemplo oficial, como no item 1).

---

## 3. HI-77 — art. 22, § 5º: qual limite se compara ao RBT12

**Transcrição integral (Res. 140, art. 22, § 5º, *cópia*):**

> § 5º Serão adotadas as alíquotas correspondentes às últimas faixas de receita bruta das tabelas dos Anexos I a V desta Resolução, quando, cumulativamente, a receita bruta acumulada: (Lei Complementar nº 123, de 2006, art. 2º, inciso I e § 6º)
> I - nos 12 (doze) meses anteriores ao do período de apuração for superior a qualquer um dos limites previstos no § 1º do art. 2º, observado o disposto nos §§ 2º a 4º do caput; e
> II - no ano-calendário em curso for igual ou inferior aos limites previstos no § 1º do art. 2º.

**Resposta curta.** A HI-77 está **certa na primeira metade e precisa de ajuste na segunda.**
- **Certo:** o RBT12 — inclusive o **proporcional**, por força da remissão expressa "observado o disposto nos §§ 2º a 4º" — é comparado com os **limites cheios do art. 2º, § 1º** (R$ 4.800.000,00 no mercado interno e, separadamente, R$ 4.800.000,00 em exportação). Nenhuma menção ao art. 3º (limite proporcional).
- **Ajuste:** a condição II (receita do ano em curso "dentro") também é medida contra o **limite cheio do art. 2º, § 1º** pelo texto literal — não contra o proporcional do art. 3º. O limite proporcional de R$ 400.000 × meses **existe e vale para a receita acumulada no ano de início**, mas como regra **de exclusão** (Res. 140, art. 3º, §§ 1º e 2º; LC 123, art. 3º, §§ 2º, 10 e 12), que é um **aviso independente**, não a condição do § 5º. Na prática, uma empresa que ultrapassa o proporcional já está excluída (retroativamente se > 20%, ou do ano seguinte se ≤ 20%), então o pré-DAS deve emitir **dois avisos distintos**: (a) § 5º — "RBT12 proporcional R$ X acima de R$ 4,8 mi com ano dentro de R$ 4,8 mi → alíquota da última faixa"; (b) art. 3º — "receita acumulada no ano R$ Y acima do limite proporcional R$ 400.000 × N meses → hipótese de exclusão, efeitos retroativos/ano seguinte". Os dois podem disparar juntos (RBT12p de 6 mi em julho com RBA de 3,5 mi excede o proporcional de 2,8 mi para 7 meses, mas não excede 4,8 mi).

**NORMA de apoio.**
- Res. 140, art. 2º, § 1º (*cópia*): limites de R$ 4.800.000,00 interno "e, adicionalmente" R$ 4.800.000,00 em exportação.
- Res. 140, art. 3º, caput e §§ 1º–2º (*cópia*): no ano de início "cada um dos limites previstos no § 1º do art. 2º será de R$ 400.000,00 multiplicados pelo número de meses [...] considerada a fração de mês como mês completo"; "Se a receita bruta acumulada no ano-calendário de início de atividade [...] for superior a qualquer um dos limites a que se refere o caput, a empresa estará excluída"; efeitos retroativos se o excesso > 20%, ou a partir do ano seguinte se ≤ 20%.
- LC 123, art. 3º, § 2º (*lido*): limite "proporcional ao número de meses em que a [ME/EPP] houver exercido atividade, inclusive as frações de meses"; § 10 (*lido*): ultrapassar o proporcional → excluída "com efeitos retroativos ao início de suas atividades"; § 12 (*lido*): não retroage se o excesso ≤ 20%, efeitos no ano seguinte.
- Manual 8.3 (*lido*): exemplo com RBT12p de R$ 2.400.000 em maio/2018 enquadrado na 5ª faixa — mostra que o RBT12p é levado direto à tabela de faixas; não há exemplo com RBT12p > 4,8 mi.

**Consequência de cálculo (o que o texto diz).** Aplicam-se "as alíquotas correspondentes às últimas faixas" — a **6ª faixa** do Anexo da atividade (de R$ 3.600.000,01 a R$ 4.800.000,00), tanto no mercado interno quanto, separadamente, na exportação (art. 23). A empresa **não é excluída** por isso e **não** há majoração do art. 24 nesse momento, porque o art. 24 pressupõe receita **do ano em curso** acima do sublimite/limite, e o § 5º, II, exige exatamente o contrário.

**O que NÃO consegui determinar (e é material):** o § 5º fala em "alíquotas" das últimas faixas, mas desde 2018 a alíquota aplicada é a **efetiva** da fórmula do art. 21 — (RBT12 × alíquota nominal − parcela a deduzir) / RBT12 — e nem a Resolução nem o Manual dizem se, nesse caso, o RBT12 que entra na fórmula é o **proporcional real** (ex.: 6.000.000) ou **truncado em 4.800.000**. A diferença não é cosmética: no Anexo III, 6ª faixa (33% nominal, PD 648.000), com RBT12p de 6 mi a efetiva é 22,20%; com 4,8 mi é 19,50%. Minha **leitura** (não comprovada) é que o PGDAS-D usa o RBT12p real na fórmula, porque é o que o § 1º do art. 18 da LC 123 manda e o § 5º só fixa a **faixa**; mas isso é hipótese e deve ser **conferido por simulação no PGDAS-D** ou com o Fred antes de o pré-DAS calcular o valor. Até lá, o aviso deve informar a faixa e **bloquear o valor**, não calcular.

**Grau de segurança:** **alto** em "compara-se com o limite cheio do art. 2º, § 1º, nos dois incisos" e em "art. 3º é regra de exclusão sobre a receita acumulada no ano"; **baixo** na mecânica da alíquota efetiva (RBT12 real × truncado) — **pendência**.

---

## 4. Período do Simples iniciado antes da abertura no CNPJ

**Resposta curta.** **Não é possível**; recusar como dado inconsistente é correto. A opção só produz efeitos (a) a partir de 1º de janeiro do ano da opção, para empresa já existente, ou (b) a partir da **data de inscrição no CNPJ**, para empresa em início de atividade — em nenhum caso antes de a empresa existir. O próprio PGDAS-D recusa PA anterior à abertura. **Não há exceção** que coloque o início do Simples antes da abertura. As duas nuances relevantes são outras: o início do Simples pode ser **igual** à data de abertura, em qualquer dia do mês (não só dia 1º), e pode ser **posterior** (opção em janeiro seguinte). O produto deve aceitar `inicio_simples >= data_abertura` e recusar `<`.

**NORMA.**
- LC 123, art. 16, § 2º (*lido*): opção em janeiro, "produzindo efeitos a partir do primeiro dia do ano-calendário da opção, ressalvado o disposto no § 3º"; § 3º (*lido*): "A opção produzirá efeitos a partir da data do início de atividade, desde que exercida nos termos, prazo e condições a serem estabelecidos no ato do Comitê Gestor".
- Res. 140, art. 6º, § 1º (*cópia*): formalizada até o último dia útil de janeiro, "produzirá efeitos a partir do primeiro dia do ano-calendário da opção, ressalvado o disposto no § 5º"; § 5º (red. Res. 183/2025, *cópia*): para empresa em início de atividade "a realização da solicitação será simultânea à inscrição no CNPJ por meio do [...] Portal Redesim", e inciso **V: "a opção produzirá efeitos a partir da data de inscrição no CNPJ"**; VI: indeferida por pendência, regularização em até 30 dias contados da inscrição — o deferimento pode ser posterior, mas os efeitos retroagem **à inscrição**, nunca antes dela. (Os incisos I a IV e alíneas, que traziam os prazos de 30/180 dias da redação anterior, foram **revogados pela Res. 183/2025** — não usar a regra antiga.)
- Res. 140, art. 2º, V (*cópia*): "data de início de atividade a data de abertura constante do CNPJ" — logo "data de início de atividade" (LC 123, art. 16, § 3º) e "data de abertura" são a mesma data para fins do Simples; não há uma "data de início de atividade" diferente da abertura que pudesse antecedê-la.
- Manual do PGDAS-D, mensagem **MSG_E0124** (*lido*, p. 134): "Período inferior à data de abertura da empresa — O período de apuração informado pelo usuário é anterior à data de abertura da empresa. Solução: informe um período de apuração válido."
- Reforço por analogia (exclusão): Res. 140, art. 81, II, "c" (*cópia*, red. Res. 145/2019) — efeitos "a partir da data de abertura constante do CNPJ, caso a abertura e a comunicação sejam efetuadas no mesmo mês de janeiro". A data de abertura é o marco zero em todo o sistema da Resolução.

**Casos que o produto precisa aceitar (não são exceção à regra, mas quebram se a validação for ingênua):**
1. `inicio_simples == data_abertura` com dia ≠ 1 (ex.: 15/10/2025) — é o caso normal de opção na abertura; o PA 10/2025 é o 1º mês de atividade inteiro.
2. `inicio_simples == 01/01/AAAA` e `data_abertura` em ano anterior — opção em janeiro (§ 4º do art. 22 no RBT12).
3. Abertura em novembro/dezembro com opção simultânea — nada muda na data; só a opção pelo regime de apuração é feita duas vezes (Manual, p. 15, *lido*).
4. MEI desenquadrado que permanece no Simples — mesmo CNPJ e mesma abertura; o quadro de receitas anteriores aparece na primeira apuração (Manual 6.3, *lido*).

**Não conferido:** se, no cadastro da Redesim/estadual, existe um campo "data de início das atividades" distinto da "data de abertura" do Comprovante de Inscrição. Para o Simples isso é irrelevante pela equiparação do art. 2º, V; o produto deve guardar a **data de abertura do CNPJ**. Em 2027 a Res. 190/2026 passa a dizer "data de inscrição no CNPJ" (informação *secundária* da consulta anterior) — mesma data, outro rótulo.

**Grau de segurança:** **alto**.

---

## Tabela-resumo

| # | Pergunta | Resposta | Dispositivo | Tipo | Segurança |
| --- | --- | --- | --- | --- | --- |
| 1 | HI-76: proporcional atravessa a virada do ano? | **Sim.** 12 primeiros meses de atividade desde o mês da abertura, sem corte em 31/12. PA 02/2026 do exemplo = 5º mês → 100.000/4 × 12 = **300.000**. § 1º a partir do **13º mês (PA 10/2026)**, onde média × 12 = soma. Sem exemplo oficial cruzando o ano. | Res. 140 art. 22 §§ 1º–3º; art. 2º V; LC 123 art. 18 § 2º; Manual 8.3 ("12 primeiros meses de atividade") | Norma + leitura | Alto (regra) / médio (ausência de exemplo) |
| 2 | § 4º: abertura no ano anterior à opção | Proporcional (§ 3º) até completar 12 meses de atividade; § 1º no 13º. Abertura 05/03/2025, opção 01/01/2026: PA 01/26 (11º) e 02/26 (12º) pelo § 4º, I; PA 03/26 (13º) pelo § 1º. **Implementação confere.** Receitas pré-opção entram. | Res. 140 art. 22 § 4º; art. 6º § 1º; Manual 6.3 | Norma | Alto |
| 3 | HI-77: § 5º compara com qual limite | RBT12 (inclusive proporcional, §§ 2º–4º) × **limite cheio de R$ 4,8 mi** por mercado (art. 2º § 1º). **Ajuste:** o inciso II (ano em curso) também usa o limite cheio; o proporcional do art. 3º é regra **de exclusão** sobre a receita acumulada no ano — aviso separado. Consequência: **6ª faixa** do Anexo, sem exclusão e sem art. 24. **Pendência:** RBT12 real ou truncado em 4,8 mi na fórmula da alíquota efetiva. | Res. 140 art. 22 § 5º I–II; art. 2º § 1º; art. 3º §§ 1º–2º; LC 123 art. 3º §§ 2º, 10, 12 | Norma + pendência | Alto (limite) / **baixo** (mecânica da alíquota) |
| 4 | Simples iniciado antes da abertura | **Impossível; recusar.** Efeitos da opção: 1º/01 do ano (empresa existente) ou **data de inscrição no CNPJ** (início de atividade). PGDAS-D recusa PA < abertura (MSG_E0124). Aceitar `inicio_simples >= data_abertura`, inclusive dia ≠ 1. | LC 123 art. 16 §§ 2º–3º; Res. 140 art. 6º §§ 1º e 5º V–VI (red. Res. 183/2025); art. 2º V; art. 81 II "c"; Manual MSG_E0124 | Norma | Alto |

**Recomendações ao arquiteto (hipóteses de produto):**
1. HI-76: manter o texto atual da hipótese; acrescentar que o mês de abertura é o 1º mês independentemente do dia e que mês sem receita entra como zero na média. Teste de fronteira: PA do 12º mês (média de 11 × 12) e do 13º (soma de 12), e teste de virada de ano com abertura em outubro.
2. HI-77: reescrever para "ambos os incisos do § 5º usam os limites cheios do art. 2º, § 1º, por mercado; o limite proporcional do art. 3º alimenta um aviso de exclusão separado sobre a receita acumulada no ano". Registrar **nova pendência**: RBT12 na fórmula do art. 21 quando RBT12p > 4,8 mi (real × truncado) — bloquear o valor do pré-DAS até o Fred confirmar ou simular no PGDAS-D.
3. Consistência: validação `inicio_simples >= data_abertura_cnpj`; mensagem nomeada citando Res. 140, art. 6º, §§ 1º e 5º, V.

**O que verifiquei:** os textos transcritos acima, nos arquivos baixados hoje (Res. 140 consolidada, Manual PGDAS-D v. 17/06/2025, LC 123 no Planalto). **O que inferi:** a leitura de que "no próprio ano-calendário da opção" qualifica a entrada e não a duração; a contagem do mês de abertura como 1º mês (apoiada no Manual 8.3 e 8.2.1); a hipótese de RBT12p real na fórmula do item 3. **O que não determinei:** exemplo oficial de RBT12p cruzando a virada do ano (não existe no Manual); a mecânica exata da alíquota efetiva no § 5º; o campo "início das atividades" da Redesim; o texto da Res. 190/2026 para 2027.

---

## Sources

- Resolução CGSN 140/2018 consolidada (PDF íntegro, *cópia*): https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf — oficial (não renderiza sem JS): http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278
- Manual do PGDAS-D e DEFIS, versão 17/06/2025 (RFB, *lido*): https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf
- LC 123/2006, Planalto (*lido*, via `curl` com User-Agent de navegador): https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- Repositório: [consulta RBT12](2026-10-08-contador-senior-rbt12.md) (itens 2 e 7); [requisitos.md](../requisitos.md), linhas 123–124 (HI-76 e HI-77)
