# Consulta ao contador-senior sobre o cálculo do pré-DAS — 08/10/2026

Terceira consulta do `arquiteto-senior` ao `contador-senior` (Fable), por ordem
do Fred (RC-164), durante a DL-075 (pré-DAS do Simples). Registro
integral da resposta, abaixo. As hipóteses que viraram regra de produto estão em
[requisitos.md](../requisitos.md) (HI-78 a HI-81).

Consulta do `arquiteto-senior` ao `contador-senior`, por ordem do Fred, sobre sete pontos do cálculo do pré-DAS de prestadoras de serviço. **Tudo abaixo é HIPÓTESE até o Fred validar.** Competências em análise: 2026 (todos os dispositivos da Res. 140 citados trazem anotação "modificação prevista para 01/01/2027 — Res. CGSN 190/2026"; não tratei 2027).

**Fontes abertas hoje e marcação usada:**

| Fonte | Como obtive | Marca |
| --- | --- | --- |
| LC 123/2006, texto compilado do Planalto (`lcp123.htm`) | `curl` com User-Agent de navegador, HTTP 200, 1.622.252 bytes (o WebFetch deu 503 duas vezes) | *lido* |
| Res. CGSN 140/2018 consolidada, anotada até a Res. 190/2026 (PDF íntegro, 128 p.) | cópia em `guiatributario.net` — o oficial `normas.receita.fazenda.gov.br` (`idAto=92278`, nas visões padrão, anotado e compilado) devolve só o título "Normas", sem texto | *cópia* |
| Manual do PGDAS-D e DEFIS, "Versão – 17 de junho de 2025", 139 p. | PDF oficial da RFB (`www8.receita.fazenda.gov.br/.../MANUAL_PGDAS-D_2018_V4.pdf`) | *lido* |

Legenda: **NORMA** = lei ou resolução; **ROTINA** = comportamento do PGDAS-D descrito no Manual (não é fundamento normativo); **INFERÊNCIA** = leitura minha a partir dos textos, sem dispositivo que a enuncie literalmente.

---

## 1. ISS retido: o percentual do ISS é apenas desconsiderado, sem redistribuição?

**Resposta curta.** Sim. A receita com ISS retido/substituído é segregada e, no cálculo do DAS, o **percentual efetivo do ISS é desconsiderado** — os percentuais dos tributos federais ficam exatamente como estariam sem a retenção. Não há nenhum dispositivo mandando redistribuir a parcela do ISS aos federais nesse caso; a única redistribuição que existe no sistema é a do **excedente a 5%** (pergunta 3), que é outra coisa.

**NORMA.**
- LC 123, art. 18, **§ 4º-A, II** (*lido*): o contribuinte "deverá segregar, também, as receitas: ... II - sobre as quais houve retenção de ISS na forma do § 6º deste artigo e § 4º do art. 21 desta Lei Complementar, ou, na hipótese do § 22-A deste artigo, seja devido em valor fixo ao respectivo município".
- LC 123, art. 18, **§ 12** (red. LC 147/2014, *lido*): "serão consideradas as reduções relativas aos tributos já recolhidos ... ou, no caso do ISS, que o valor tenha sido objeto de retenção ou seja devido diretamente ao Município".
- Res. CGSN 140, **art. 25, § 9º, II** (*cópia*): a ME/EPP "deverá informar: ... II - se houve retenção do imposto, quando então será desconsiderado, no cálculo do valor devido no âmbito do Simples Nacional, o percentual do ISS".
- A retenção é definitiva na operação: LC 123, art. 13, § 1º, XIV, "a" (ISS devido nos serviços sujeitos a substituição ou retenção fica **fora** do Simples) e art. 21, § 4º (*lido*); Res. 140, art. 27 (*cópia*).

**ROTINA (Manual, item 6.5, *lido*).** O PGDAS-D obriga a escolher, em cada item de serviço, uma de três situações: "sem retenção/substituição tributária de ISS, com ISS devido a outro(s) Município(s)", "sem retenção..., com ISS devido ao próprio Município do estabelecimento" ou "com retenção/substituição tributária de ISS". Não há exemplo numérico de ISS retido no Manual (verifiquei os exemplos 1–10); o único exemplo de "desconsiderar percentual" é o exemplo 6 (exportação), que mostra os tributos desconsiderados **zerados** na tabela e o total igual à soma dos remanescentes — sem redistribuição.

**Grau de segurança: alto** na regra (texto literal da LC e da Resolução); **médio** na mecânica exata do programa (sem exemplo oficial com retenção).

---

## 2. Exportação de serviço: PIS, Cofins e ISS desconsiderados sem redistribuição; CPP e IRPJ/CSLL permanecem?

**Resposta curta.** Sim. Na receita de exportação de serviço desconsideram-se **Cofins, PIS/Pasep e ISS** (e IPI/ICMS, que não se aplicam a serviço puro). **IRPJ, CSLL e CPP permanecem**, com seus percentuais inalterados — não há redistribuição da parcela desonerada. A alíquota efetiva da receita exportada é calculada com o **RBT12 de exportação**, separado do interno (isso já está na consulta anterior, item 4; só registro porque o produto precisa aplicá-lo antes de desconsiderar os percentuais).

**NORMA.**
- LC 123, art. 18, **§ 4º-A, IV** (*lido*): segregar as receitas "decorrentes da exportação para o exterior".
- LC 123, art. 18, **§ 14** (red. LC 155/2016, *lido*): "A redução no montante a ser recolhido no Simples Nacional relativo aos valores das receitas decorrentes da exportação de que trata o inciso IV do § 4º-A deste artigo corresponderá **tão somente** às alíquotas efetivas relativas à Cofins, à Contribuição para o PIS/Pasep, ao IPI, ao ICMS e ao ISS, constantes dos Anexos I a V". O "tão somente" é o que fecha a porta à redistribuição e à exclusão de qualquer outro tributo.
- Res. CGSN 140, **art. 25, § 3º** (*cópia*): segregar a exportação, "quando então serão desconsiderados, no cálculo do valor devido no âmbito do Simples Nacional, conforme o caso, os percentuais relativos à Cofins, à Contribuição para o PIS/Pasep, ao IPI, ao ICMS e ao ISS constantes dos Anexos I a V". Definição de exportação de serviço: **§ 4º** (= LC 116, art. 2º, parágrafo único) e **§ 4º-A** (manutenção de recursos no exterior, Lei 11.371/2006).
- Alíquota separada por mercado: Res. 140, **art. 23** (*cópia*).

**ROTINA (Manual, exemplo 6, *lido*).** Revenda para o exterior, RBT12 ext = 1.000.000, alíquota efetiva ext 8,45%, 4ª faixa do Anexo I: a tabela traz Cofins, PIS e ICMS como **0,00%** e os demais com seu percentual normal (IRPJ 0,46475%, CSLL 0,29575%, CPP 3,549%), total 4,3095%, valor 2.154,76. Frase do Manual: "Na revenda de mercadorias para o exterior não há incidência de Cofins, Pis/Pasep e ICMS." Para serviço o análogo é Cofins, PIS e ISS (a CPP continua). Na aba de atividades, o item "9 - Prestação de Serviços para o exterior" **não** tem sub-opções de retenção/município — exportação e retenção são excludentes no PGDAS-D.

**Grau de segurança: alto.**

---

## 3. Teto de 5% do ISS combinado com retenção ou exportação: qual a ordem?

**Resposta curta.** Opção **(a)**: primeiro se determinam os **percentuais efetivos de cada tributo** da receita (alíquota efetiva × repartição, **já com o teto de 5% e a transferência do excedente aos federais**), e só então se **desconsidera o percentual do ISS** (que, nessa faixa, é 5%) da receita retida ou exportada. Os federais ficam com a parcela redistribuída. Na exportação, o mesmo: aplica-se o teto, redistribui, e depois desconsideram-se ISS (5%), Cofins e PIS **com os seus percentuais já acrescidos do excedente**; IRPJ, CSLL e CPP permanecem com os valores pós-redistribuição.

**NORMA (de onde sai a ordem).**
- O teto é parte da **definição** de "percentual efetivo de cada tributo": LC 123, art. 18, **§ 1º-B, I** (*lido*): "Os percentuais efetivos de cada tributo serão calculados a partir da alíquota efetiva, multiplicada pelo percentual de repartição ..., observando-se que: I - o percentual efetivo máximo destinado ao ISS será de 5%, transferindo-se eventual diferença, de forma proporcional, aos tributos federais da mesma faixa"; Res. 140, **art. 21, III, "a"** (*cópia*), idem.
- A desconsideração é operação **posterior**, feita sobre "o percentual do ISS" já definido: Res. 140, **art. 25, § 9º, II** (retenção) e **§ 3º** (exportação) — e o art. 25, caput, manda aplicar "as alíquotas efetivas calculadas na forma prevista nos arts. 21, 22 e 24". Ou seja, o art. 21 (com o teto) roda antes do art. 25 (com a desconsideração).
- As notas de rodapé dos Anexos III e IV da LC 123 (*lido*, já transcritas em `docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md`) **redefinem a própria tabela de repartição** da 5ª faixa quando a alíquota efetiva passa de 14,92537% (III) ou 12,5% (IV): "a repartição será: IRPJ (Alíq. ef. – 5%) × 6,02% ... ISS fixo em 5%". Logo "o percentual do ISS" a desconsiderar nessa faixa **é 5%**, por construção da tabela — não existe um "ISS de 33,5%" a desconsiderar.

**INFERÊNCIA (coerência com a retenção).** Res. 140, **art. 27, I** (*cópia*): o tomador retém pelo "percentual efetivo de ISS decorrente da aplicação das tabelas dos Anexos III, IV ou V" — isto é, pelo percentual já limitado a 5%. Se o produto desconsiderasse o ISS "cheio" (33,5% da alíquota efetiva) e não redistribuísse, o contribuinte pagaria menos federais do que um concorrente sem retenção e o município receberia 5%: a soma não fecharia com a alíquota efetiva. A leitura (a) é a única em que retido + DAS = carga sem retenção.

**O que o Manual mostra.** Não há exemplo oficial combinando teto de 5% com retenção ou exportação (verifiquei). O exemplo 8 (*lido*) mostra o teto + redistribuição numa receita **sem** retenção (ISS 5,00%, excedente 1,09968% repartido em IRPJ 0,0662%, CSLL 0,0578%, Cofins 0,2120%, PIS 0,0460%, CPP 0,7177%). A ordem para o caso combinado é **inferência textual minha**, não demonstração do Manual.

**Grau de segurança: médio-alto** na ordem (estrutura normativa clara, sem exemplo oficial); recomendo registrar como HI e, na primeira empresa real da 5ª faixa com retenção, conciliar com o extrato do PGDAS-D.

---

## 4. Receita sem documento ("receita informada"): presumir ISS ao próprio município ou exigir o segmento?

**Resposta curta.** **Exigir.** O produto não deve presumir segmento. A recomendação como contador: a receita informada de serviço só é aceita com (i) **mercado** (interno/exportação), (ii) **situação do ISS** (próprio município / outro município + qual / retido ou substituído) e (iii) **enquadramento** (item do PGDAS-D) preenchidos pelo contador. Pode-se **pré-sugerir** "próprio município, sem retenção" como valor mais frequente, mas com confirmação explícita e trilha — nunca default silencioso.

**Por quê (NORMA).**
- A segregação é dever do contribuinte, não opção do sistema: LC 123, art. 18, **§ 4º-A** (*lido*) e Res. 140, **art. 25, § 9º** (*cópia*): "deverá informar: I - a qual Município é devido o imposto; II - se houve retenção; III - se o valor é devido em valor fixo".
- O que se declara é confissão de dívida: LC 123, art. 18, **§ 15-A, I** (*lido*). Um pré-DAS que "presume" produz número que o contador tende a copiar.
- O erro tem sentido duplo e nenhum é inofensivo: presumir "próprio município" numa receita que teve ISS retido **duplica o ISS** (retido pelo tomador e pago no DAS); presumir "próprio município" numa receita devida a outro município **destina ao ente errado** (o DAS carrega o código do município); presumir "mercado interno" numa exportação **cobra PIS/Cofins/ISS indevidos** e ainda infla o RBT12 interno.

**ROTINA (Manual, 6.5 e 6.6, *lido*).** O PGDAS-D **não tem default**: para cada item de serviço o usuário escolhe a situação do ISS e, se "outro Município", "é necessário selecionar o Município/UF para o qual é destinado o ISS". Vale copiar essa exigência.

**Prática de escritório (*não conferido*).** O caso típico — serviço com NFS-e de município não integrado ao padrão nacional — **tem documento**: a nota municipal informa se houve retenção e o local de incidência. O contador que lança a "receita informada" tem o dado na mão; o custo de pedir é baixo e evita a classe de erro mais cara (ISS duplicado).

**Grau de segurança: alto** na norma; a recomendação é de produto, para o Fred decidir.

---

## 5. Sublimite de R$ 3,6 mi: dispositivo e segurança de recusar o cálculo

**Resposta curta.** Confirmo o dispositivo, com uma **correção de premissa**: o que tira ICMS/ISS do DAS **não é o RBT12** acima de R$ 3,6 mi, e sim a **receita bruta acumulada no ano-calendário (RBA)** acima do sublimite, com efeito no mês seguinte (excesso > 20%) ou no ano seguinte (≤ 20%). RBT12 acima de 3,6 mi com RBA ainda dentro mantém o ISS **no** DAS, calculado pela fórmula da 5ª faixa. Recusar o pré-DAS **em qualquer dessas situações** (RBT12 > 3,6 mi, ou RBA > 3,6 mi, ou empresa marcada como impedida) é escolha **segura e defensável** para o primeiro corte, desde que a recusa seja nomeada e explique o motivo.

**NORMA.**
- Sublimite obrigatório de R$ 3.600.000,00 (interno) + igual para exportação, onde o Estado não optou por 1,8 mi: Res. 140, **art. 9º, § 1º** (*cópia*); LC 123, arts. 13-A e 19, § 4º (*lido*). Para ISS, art. 10 da Res. 140 / art. 20 da LC 123. Em 2026 todas as UFs estão em 3,6 mi (Portaria CGSN 54/2025 — consulta anterior, *cópia*).
- Impedimento: Res. 140, **art. 12**, caput ("Caso a receita bruta acumulada pela empresa **no ano-calendário** ultrapasse quaisquer dos sublimites ... estará impedido de recolher o ICMS e o ISS pelo Simples Nacional") e **§ 1º, I e II** (mês subsequente se > 20%; ano seguinte se ≤ 20%); LC 123, **art. 20, §§ 1º e 1º-A** (*lido*). Ano de início: art. 12, § 2º (R$ 300.000 × meses).
- Três regimes de cálculo distintos que o produto teria de distinguir se quisesse cobrir isso:
  1. **RBT12 > 3,6 mi, RBA ≤ sublimite** → ISS continua no DAS; percentual do ISS = [(RBT12 × alíq. nominal 5ª faixa − PD 5ª faixa)/RBT12] × repartição do ISS da 5ª faixa, com teto de 5%; federais pela 6ª faixa — Res. 140, **art. 21, III, "b"** (*cópia*); Manual, exemplo 8 (*lido*).
  2. **RBA > sublimite, antes dos efeitos do impedimento** → parcela excedente: federais pelo art. 21, ISS por {[(3.600.000 × alíq. nominal 5ª) − PD 5ª]/3.600.000} × repartição do ISS — Res. 140, **art. 24, I, "b", 2** (*cópia*); LC 123, art. 18, §§ 17 e 17-A (*lido*).
  3. **Impedimento em vigor** → ISS fora do DAS, recolhido ao município pela legislação própria; o DAS só tem federais.

**Recomendação.** Primeiro corte: recusar quando `RBT12_interno > 3.600.000` **ou** `RBA_interno (ano corrente, incluído o PA) > 3.600.000` **ou** cadastro marca "impedido de recolher ISS no DAS", com mensagem citando art. 12/21/24 e dizendo qual das três situações disparou. É uma recusa, não um erro: nenhum número sai. Marcar como **Fora do escopo** no plano, não como "não implementado".

**Grau de segurança: alto.**

---

## 6. Início de atividade: folha do fator r nos 12 primeiros meses e os zeros

**Resposta curta.** A folha segue **o mesmo critério da receita** — anualização pela média × 12 — por remissão expressa; e como o fator r é uma razão, (média FS × 12) / (média RBT × 12) **é igual** a (Σ FS) / (Σ receitas) dos meses decorridos, que é exatamente a fórmula que o Manual mostra. Só o **mês de abertura** é diferente: r = FSPA / RPA (folha e receita do próprio PA). Zeros: FS12 = 0 → r = 0,01 (Anexo V); FS12 > 0 e RBT12 = 0 → r = 0,28 (Anexo III); ambos zero → 0,01. Resultado truncado em 2 casas (0,2774 → 0,27).

**NORMA (Res. 140, *cópia*).**
- **Art. 26, § 4º**: "Na hipótese de a ME ou EPP ter menos de 13 (treze) meses de atividade, adotar-se-ão, para a determinação da folha de salários anualizada, incluídos encargos, os mesmos critérios para a determinação da receita bruta total acumulada, estabelecidos no art. 22, no que couber."
- **Art. 22, §§ 2º–4º**: 1º mês = receita do mês × 12; 11 meses seguintes = média dos meses anteriores × 12; abertura no ano anterior ao da opção = regra do § 3º até completar 12 meses e regra geral a partir do 13º.
- **Art. 26, § 6º** (mês de início): I - FSPA > 0 e RPAr = 0 → 0,28; II - FSPA = 0 e RPAr > 0 → 0,01; III - ambos > 0 → FSPA/RPAr.
- **Art. 26, § 7º** (PA posterior ao início): I - FS12 = 0 e RBT12r = 0 → 0,01; II - FS12 > 0 e RBT12r = 0 → 0,28; III - ambos > 0 → FS12/RBT12r; IV - FS12 = 0 e RBT12r > 0 → 0,01.
- RBT12r é **conjunto** interno + exportação (§ 5º, V); FS12 é folha **paga** (regime de caixa), só remunerações informadas em GFIP/eSocial (§§ 1º–2º).
- LC 123, art. 18, §§ 5º-J, 5º-K e 24 (*lido*).

**ROTINA (Manual 8.2.1, *lido*).** Reproduz os §§ 6º e 7º literalmente e traz a fórmula operacional: "Para empresas em início de atividade, se o período de tempo decorrido entre a data de abertura e o período de apuração for inferior a 13 meses: Fator r = soma das FS desde o mês da data de abertura até o mês anterior ao do PA / soma das receitas desde o mês da data de abertura até o mês anterior ao do PA". E: "A partir de 04/2018, o sistema considera duas casas decimais sem arredondamento". Atenção à advertência do Manual (item 8.2): retificar FS ou receita de um mês obriga a retificar **todos os PA posteriores**, mesmo que seus valores não tenham mudado — o produto deve recalcular em cascata.

**INFERÊNCIA.** O art. 26, § 4º fala em "folha anualizada", e o Manual usa somas simples; as duas são equivalentes para o quociente (o fator 12/n cancela). Para o **RBT12 da alíquota** (não do fator r) continua valendo a anualização do art. 22, com RBT12 = 0 → R$ 1,00 (art. 21, parágrafo único). O produto deve calcular as duas grandezas em separado: anualizar para a alíquota, dividir somas (ou anualizar ambas) para o fator r — o resultado é o mesmo, mas misturar RBT12 anualizado com FS não anualizada é o erro clássico.

**Grau de segurança: alto.**

---

## 7. ISS devido a outro município: muda algo no cálculo?

**Resposta curta.** **Não muda o valor.** O ISS é calculado pelo mesmo percentual efetivo (alíquota efetiva × repartição do Anexo, com teto de 5%) e recolhido **dentro do DAS**; o que muda é a **destinação** — o PGDAS-D exige o código do município e repassa a ele. A alíquota de ISS da lei do outro município é **irrelevante** para o DAS (o Simples substitui a legislação municipal de alíquota). O que pode mudar é a **situação** do ISS naquele município (valor fixo, isenção/redução por lei local — arts. 30–35 da Res. 140), que já está fora do primeiro corte.

**NORMA.**
- LC 123, art. 18, **§ 4º-A, V** (*lido*): segregar as receitas "sobre as quais o ISS seja devido a Município diverso do estabelecimento prestador, **quando será recolhido no Simples Nacional**".
- Res. 140, **art. 25, § 9º, I** (*cópia*): informar "a qual Município é devido o imposto" — e, diferentemente dos incisos II e III do mesmo parágrafo, **sem** a cláusula "quando então será desconsiderado o percentual do ISS".
- Base de cálculo do ISS no Simples = receita bruta total mensal, afastada a legislação municipal de valor fixo enquanto optante: Res. 140, **art. 25, § 12** (*cópia*).
- Local de incidência: segue a LC 116, art. 3º (regra geral: estabelecimento prestador; exceções nos incisos) — o produto deriva isso de `cLocIncid` do XML, mas a regra material é da LC 116, **não conferida hoje**.

**ROTINA (Manual 6.6, *lido*).** "Para as atividades de prestação de serviços ... com ISS devido a outro(s) Município(s) é necessário selecionar o Município/UF para o qual é destinado o ISS"; se houver mais de um município no mesmo item, segrega-se a receita por município com o botão "+". Para o pré-DAS isso significa: a linha de receita precisa carregar **o município de destino** e o conferente precisa ver o ISS **por município**, porque é assim que o extrato do PGDAS-D vai mostrar.

**Grau de segurança: alto.**

---

## Tabela-resumo

| # | Pergunta | Resposta | Tipo | Dispositivos | Segurança |
| --- | --- | --- | --- | --- | --- |
| 1 | ISS retido | Percentual do ISS desconsiderado; federais inalterados; sem redistribuição | Norma | LC 123 art. 18 §§ 4º-A II, 12; art. 13 § 1º XIV "a"; art. 21 § 4º; Res. 140 art. 25 § 9º II, art. 27 | Alta |
| 2 | Exportação | Cofins, PIS e ISS desconsiderados ("tão somente"); IRPJ, CSLL e CPP ficam; alíquota pelo RBT12 ext | Norma + exemplo 6 | LC 123 art. 18 §§ 4º-A IV, 14; Res. 140 art. 23, art. 25 §§ 3º, 4º, 4º-A | Alta |
| 3 | Teto 5% + retenção/exportação | Ordem (a): teto e redistribuição primeiro (art. 21), desconsideração depois (art. 25); ISS desconsiderado = 5% | Norma (estrutura) + inferência | LC 123 art. 18 § 1º-B I e notas dos Anexos III/IV; Res. 140 art. 21 III "a", art. 25 §§ 3º, 9º, art. 27 I | Médio-alta; conciliar com extrato |
| 4 | Receita informada | Exigir mercado, situação do ISS e município; pré-sugestão com confirmação, nunca default silencioso | Norma + recomendação | LC 123 art. 18 §§ 4º-A, 15-A; Res. 140 art. 25 § 9º; Manual 6.5/6.6 | Alta (norma); decisão do Fred |
| 5 | Sublimite | Gatilho é RBA do ano, não RBT12; três regimes (art. 21 III "b", art. 24, art. 12); recusar nos três é seguro | Norma + recomendação | Res. 140 arts. 9º § 1º, 10, 12, 21 III "b", 24; LC 123 arts. 13-A, 19, 20 §§ 1º–1º-A, 18 §§ 17, 17-A | Alta |
| 6 | Fator r em início de atividade | FS pelo mesmo critério da receita (média × 12 ≡ Σ/Σ); mês de abertura FSPA/RPA; zeros: 0,01 / 0,28; truncar 2 casas | Norma + rotina | Res. 140 art. 26 §§ 4º–7º, art. 22 §§ 2º–4º, art. 21 p. único; Manual 8.2.1 | Alta |
| 7 | ISS outro município | Mesmo percentual, recolhido no DAS, só muda destino; alíquota municipal irrelevante; informar município | Norma | LC 123 art. 18 § 4º-A V; Res. 140 art. 25 §§ 9º I, 12; Manual 6.6 | Alta |

## O que não consegui determinar

- Texto **oficial** da Res. CGSN 140 (SIJUT não renderiza sem JavaScript); usei cópia íntegra consolidada, coerente com o Manual e com a LC 123 em todos os pontos conferidos.
- Exemplo oficial combinando teto de 5% com retenção ou exportação — não existe no Manual; a ordem da pergunta 3 é inferência textual.
- Regra de local de incidência (LC 116, art. 3º) para a pergunta 7 — não abri a LC 116 hoje.
- Nada aqui trata de 2027: todos os artigos da Res. 140 citados estão anotados com "modificação prevista para 01/01/2027" pela Res. 190/2026, cujo texto não li.

## Arquivos de trabalho (fora do repositório, não versionados)

`/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/manual/` — `manual_v4.pdf`/`manual.txt` (RFB), `res140.pdf`/`res140.txt` (cópia), `lc123.html`/`lc123n.txt` (Planalto). Nenhum arquivo do repositório foi alterado.

Sources:
- [Manual do PGDAS-D e DEFIS, v. 17/06/2025 (RFB)](https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf)
- [LC 123/2006 compilada (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm)
- [Res. CGSN 140/2018 consolidada — cópia íntegra (Guia Tributário)](https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf)
- [Res. CGSN 140/2018 — página oficial (SIJUT, sem texto renderizado)](http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278)
- [Espelho do Manual (SEFIN-RO, versão 04/2022, não usado)](https://www.sefin.ro.gov.br/portalsefin/manuais/MANUAL_PGDAS-D_2018_V4.pdf)
- Repositório: [consulta RBT12](2026-10-08-contador-senior-rbt12.md) e [tabelas de 2026](2026-10-08-tabelas-simples-2026.md) (notas dos Anexos III/IV e § 1º-B já transcritos do Planalto)
