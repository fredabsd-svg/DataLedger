# Tabelas oficiais do Simples Nacional vigentes em 2026 — pesquisa de 08/10/2026

Pesquisa feita por `auxiliar-pesquisa` a pedido do `arquiteto-senior`, para o
pré-DAS do Simples (etapa seguinte à
[DL-074](../../planos/DL-074-receita-e-rbt12-do-simples.md)). Registro
integral. As tabelas foram lidas no **Planalto** (LC 123/2006, Anexos na
redação da LC 155/2016) e conferidas contra a LC 155 original e o Manual do
PGDAS-D; o que é **inferência** do pesquisador está marcado. Os arquivos
baixados ficaram fora do repositório e **não** são versionados aqui.

Data de consulta: 08/10/2026. Nada foi alterado no repositório. Os downloads ficaram em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/anexos/`.

## 1. Fontes

| # | URL | Título e versão | Publicação | Natureza |
|---|---|---|---|---|
| F1 | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm | LC 123/2006, texto compilado. Republicações de 2009 e 2012 (rodapé do texto). Anexos I a V na redação da LC 155/2016 | DOU 15.12.2006 | **Oficial** |
| F2 | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp155.htm | LC 155, de 27/10/2016 (traz os Anexos I a V novos e o art. 11) | DOU 28.10.2016 | **Oficial** |
| F3 | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm | LC 214, de 16/01/2025 (arts. 519, 520 e 544) | DOU 17.01.2025 | **Oficial** |
| F4 | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp227.htm | LC 227, de 13/01/2026 (arts. 168, 169 e 170 e redação do art. 544, III, da LC 214) | DOU 14.01.2026, republicada 15.01.2026, retificada 23.01.2026 | **Oficial** |
| F5 | https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf | Manual do PGDAS-D e Defis, "Versão – 17 de junho de 2025", 139 páginas | 17/06/2025 | **Oficial** (Portal do Simples Nacional, página de Manuais) |
| F6 | https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/Anexos_LC%20123_Evolucao_Historica.pdf | "Evolução legislativa dos anexos de tributação", 6 páginas (metadados: 18/01/2018). É resumo; o próprio documento diz que não dispensa a legislação | 2018 | **Oficial** |
| F7 | https://www.normaslegais.com.br/legislacao/Resolucao-cgsn-190-2026.htm | Res. CGSN 190, de 04/08/2026 (DOU 10/08/2026, segundo a própria cópia) | 10/08/2026 | **CÓPIA** (site de legislação) |
| F8 | https://www.normaslegais.com.br/legislacao/resolucao-cgsn-140-2018.htm | Res. CGSN 140/2018 | DOU 24/05/2018 | **CÓPIA**, só 10 KB (não vi os artigos 25 e 26) |

Erros e dificuldades registrados:
- **LC 123 (F1):** abriu na primeira tentativa, com `User-Agent` de navegador. Resposta HTTP 200, 1.622.252 bytes. Não houve 503.
- **LC 155, 214 e 227:** a URL com `Lcp` maiúsculo respondeu `301 Moved Permanently` ("The document has moved here."). Com `lcp` minúsculo e `-L` abriram (HTTP 200).
- **LC 227 pelo WebFetch:** "The server returned HTTP 503 Service Unavailable." O `curl` funcionou.
- **Res. CGSN 140, texto oficial:** **não obtido.** `normas.receita.fazenda.gov.br` devolve página dinâmica sem conteúdo. O menu "Legislação" do Portal do Simples também é dinâmico. A F8 é cópia parcial.
- **Divergência de data de publicação da Res. 190:** a cópia F7 diz DOU 10/08/2026. Um resultado de busca atribuiu 11/08/2026 à FIEMG. Não verifiquei o DOU.

## 2. Tabelas (F1, redação da LC 155/2016)

Todas as tabelas abaixo foram lidas da F1.

**Verificação cruzada que fiz:** comparei todos os números dos cinco Anexos da F1 com os da F2 (LC 155 original). Os conjuntos são idênticos (57, 63, 64, 55 e 57 valores). A F1 também traz as versões antigas de 2012, que não usei.

**Conferência com o Manual (F5):** as alíquotas, as parcelas a deduzir e as repartições usadas nos exemplos do Manual batem com a F1. Os Anexos dentro do Manual são imagens e não os conferi célula a célula.

**Soma das repartições:** conferi por conta própria que cada faixa soma 100,00%. Isso vale também para a repartição da 5ª faixa com ISS limitado a 5%, nos Anexos III e IV.

**Faixas, iguais em todos os Anexos.** Cabeçalho literal: "Receita Bruta em 12 Meses (em R$)", "Alíquota", "Valor a Deduzir (em R$)".

| Faixa | Receita Bruta em 12 Meses (em R$) |
|---|---|
| 1ª | Até 180.000,00 |
| 2ª | De 180.000,01 a 360.000,00 |
| 3ª | De 360.000,01 a 720.000,00 |
| 4ª | De 720.000,01 a 1.800.000,00 |
| 5ª | De 1.800.000,01 a 3.600.000,00 |
| 6ª | De 3.600.000,01 a 4.800.000,00 |

Alíquota nominal e valor a deduzir, por faixa (a célula da 1ª faixa vem como "-" ou "–" na F1):

| Faixa | I (Comércio) | II (Indústria) | **III** | **IV** | **V** |
|---|---|---|---|---|---|
| 1ª | 4,00% / – | 4,50% / – | **6,00% / –** | **4,50% / –** | **15,50% / –** |
| 2ª | 7,30% / 5.940,00 | 7,80% / 5.940,00 | **11,20% / 9.360,00** | **9,00% / 8.100,00** | **18,00% / 4.500,00** |
| 3ª | 9,50% / 13.860,00 | 10,00% / 13.860,00 | **13,50% / 17.640,00** | **10,20% / 12.420,00** | **19,50% / 9.900,00** |
| 4ª | 10,70% / 22.500,00 | 11,20% / 22.500,00 | **16,00% / 35.640,00** | **14,00% / 39.780,00** | **20,50% / 17.100,00** |
| 5ª | 14,30% / 87.300,00 | 14,70% / 85.500,00 | **21,00% / 125.640,00** | **22,00% / 183.780,00** | **23,00% / 62.100,00** |
| 6ª | 19,00% / 378.000,00 | 30,00% / 720.000,00 | **33,00% / 648.000,00** | **33,00% / 828.000,00** | **30,50% / 540.000,00** |

### Percentual de Repartição dos Tributos (literal)

**Anexo III** (colunas: IRPJ, CSLL, Cofins, PIS/Pasep, CPP, ISS (*))

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS (*) |
|---|---|---|---|---|---|---|
| 1ª | 4,00% | 3,50% | 12,82% | 2,78% | 43,40% | 33,50% |
| 2ª | 4,00% | 3,50% | 14,05% | 3,05% | 43,40% | 32,00% |
| 3ª | 4,00% | 3,50% | 13,64% | 2,96% | 43,40% | 32,50% |
| 4ª | 4,00% | 3,50% | 13,64% | 2,96% | 43,40% | 32,50% |
| 5ª | 4,00% | 3,50% | 12,82% | 2,78% | 43,40% | 33,50% (*) |
| 6ª | 35,00% | 15,00% | 16,03% | 3,47% | 30,50% | – |

Nota de rodapé do Anexo III, literal:
> "(*) O percentual efetivo máximo devido ao ISS será de 5%, transferindo-se a diferença, de forma proporcional, aos tributos federais da mesma faixa de receita bruta anual. Sendo assim, na 5a faixa, quando a alíquota efetiva for superior a 14,92537%, a repartição será:"

| | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS |
|---|---|---|---|---|---|---|
| 5ª Faixa, com alíquota efetiva superior a 14,92537% | (Alíquota efetiva – 5%) x 6,02% | (Alíquota efetiva – 5%) x 5,26% | (Alíquota efetiva – 5%) x 19,28% | (Alíquota efetiva – 5%) x 4,18% | (Alíquota efetiva – 5%) x 65,26% | Percentual de ISS fixo em 5% |

O sinal de menos entre "efetiva" e "5%" aparece como espaço na minha extração do HTML, e a F5 (Exemplo 8) confirma a leitura "– 5%". Isso é inferência minha.

**Anexo IV** (colunas: IRPJ, CSLL, Cofins, PIS/Pasep, ISS (*)). Não há coluna CPP.

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | ISS (*) |
|---|---|---|---|---|---|
| 1ª | 18,80% | 15,20% | 17,67% | 3,83% | 44,50% |
| 2ª | 19,80% | 15,20% | 20,55% | 4,45% | 40,00% |
| 3ª | 20,80% | 15,20% | 19,73% | 4,27% | 40,00% |
| 4ª | 17,80% | 19,20% | 18,90% | 4,10% | 40,00% |
| 5ª | 18,80% | 19,20% | 18,08% | 3,92% | 40,00% (*) |
| 6ª | 53,50% | 21,50% | 20,55% | 4,45% | - |

Nota de rodapé do Anexo IV, literal:
> "(*) O percentual efetivo máximo devido ao ISS será de 5%, transferindo-se a diferença, de forma proporcional, aos tributos federais da mesma faixa de receita bruta anual. Sendo assim, na 5a faixa, quando a alíquota efetiva for superior a 12,5%, a repartição será:"

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | ISS |
|---|---|---|---|---|---|
| 5ª Faixa, com alíquota efetiva superior a 12,5% | (Alíquota efetiva – 5%) x 31,33% | (Alíquota efetiva – 5%) x 32,00% | (Alíquota efetiva – 5%) x 30,13% | (Alíquota efetiva – 5%) x 6,54% | Percentual de ISS fixo em 5% |

**Anexo V** (colunas: IRPJ, CSLL, Cofins, PIS/Pasep, CPP, ISS). Não tem nota de rodapé na F1.

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS |
|---|---|---|---|---|---|---|
| 1ª | 25,00% | 15,00% | 14,10% | 3,05% | 28,85% | 14,00% |
| 2ª | 23,00% | 15,00% | 14,10% | 3,05% | 27,85% | 17,00% |
| 3ª | 24,00% | 15,00% | 14,92% | 3,23% | 23,85% | 19,00% |
| 4ª | 21,00% | 15,00% | 15,74% | 3,41% | 23,85% | 21,00% |
| 5ª | 23,00% | 12,50% | 14,10% | 3,05% | 23,85% | 23,50% |
| 6ª | 35,00% | 15,50% | 16,44% | 3,56% | 29,50% | - |

**Anexo I** (colunas: IRPJ, CSLL, Cofins, PIS/Pasep, CPP, ICMS)

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ICMS |
|---|---|---|---|---|---|---|
| 1ª | 5,50% | 3,50% | 12,74% | 2,76% | 41,50% | 34,00% |
| 2ª | 5,50% | 3,50% | 12,74% | 2,76% | 41,50% | 34,00% |
| 3ª | 5,50% | 3,50% | 12,74% | 2,76% | 42,00% | 33,50% |
| 4ª | 5,50% | 3,50% | 12,74% | 2,76% | 42,00% | 33,50% |
| 5ª | 5,50% | 3,50% | 12,74% | 2,76% | 42,00% | 33,50% |
| 6ª | 13,50% | 10,00% | 28,27% | 6,13% | 42,10% | - |

**Anexo II** (colunas: IRPJ, CSLL, Cofins, PIS/Pasep, CPP, IPI, ICMS)

| Faixa | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | IPI | ICMS |
|---|---|---|---|---|---|---|---|
| 1ª a 5ª (idênticas) | 5,50% | 3,50% | 11,51% | 2,49% | 37,50% | 7,50% | 32,00% |
| 6ª | 8,50% | 7,50% | 20,96% | 4,54% | 23,50% | 35,00% | - |

**Regras de cálculo na própria LC 123 (art. 18, F1), literais:**
- **§ 1º-A.** A alíquota efetiva é o resultado de: `(RBT12 x Aliq − PD) / RBT12`. RBT12 é a receita bruta acumulada nos doze meses anteriores ao período de apuração. Aliq é a alíquota nominal e PD é a parcela a deduzir (incisos I a III). O sinal de menos e a barra de divisão não aparecem no texto extraído do HTML; a fórmula com `/ RBT12` está no Manual F5, item 8.1.
- **§ 1º-B.** "Os percentuais efetivos de cada tributo serão calculados a partir da alíquota efetiva, multiplicada pelo percentual de repartição constante dos Anexos I a V desta Lei Complementar, observando-se que: I - o percentual efetivo máximo destinado ao ISS será de 5% (cinco por cento), transferindo-se eventual diferença, de forma proporcional, aos tributos federais da mesma faixa de receita bruta anual; II - eventual diferença centesimal entre o total dos percentuais e a alíquota efetiva será transferida para o tributo com maior percentual de repartição na respectiva faixa de receita bruta."
- **§ 2º.** "Em caso de início de atividade, os valores de receita bruta acumulada constantes dos Anexos I a V desta Lei Complementar devem ser proporcionalizados ao número de meses de atividade no período."
- **§ 3º.** "Sobre a receita bruta auferida no mês incidirá a alíquota efetiva determinada na forma do caput e dos §§ 1º, 1º-A e 2º deste artigo, podendo tal incidência se dar, à opção do contribuinte, na forma regulamentada pelo Comitê Gestor, sobre a receita recebida no mês, sendo essa opção irretratável para todo o ano-calendário."

**RBT12 acima da 5ª faixa (3,6 milhões).** O que está na F1 é a coluna "–" na 6ª faixa de ISS e ICMS. A regra de cálculo vem do Manual F5, Exemplos 8 e 10, e a Res. CGSN 140 não foi lida no original.
- A F5 aplica a alíquota efetiva da 6ª faixa ao total.
- Para ISS (ou ICMS), soma o percentual calculado como a alíquota efetiva da 5ª faixa multiplicada pelo percentual de repartição da 5ª faixa, com ISS limitado a 5%.
- A redistribuição do excedente do ISS segue a nota do Anexo III.
- Os cálculos estão no item 6 (Exemplo 8).

## 3. Fator r (LC 123, art. 18, F1) — texto literal

> **§ 5º-J.** "As atividades de prestação de serviços a que se refere o § 5º-I serão tributadas na forma do Anexo III desta Lei Complementar caso a razão entre a folha de salários e a receita bruta da pessoa jurídica seja igual ou superior a 28% (vinte e oito por cento)." (Incluído pela LC 155/2016)

> **§ 5º-K.** "Para o cálculo da razão a que se referem os §§ 5º-J e 5º-M, serão considerados, respectivamente, os montantes pagos e auferidos nos doze meses anteriores ao período de apuração para fins de enquadramento no regime tributário do Simples Nacional." (Incluído pela LC 155/2016)

> **§ 5º-L.** (VETADO).

> **§ 5º-M.** "Quando a relação entre a folha de salários e a receita bruta da microempresa ou da empresa de pequeno porte for inferior a 28% (vinte e oito por cento), serão tributadas na forma do Anexo V desta Lei Complementar as atividades previstas: I - nos incisos XVI, XVIII, XIX, XX e XXI do § 5º-B deste artigo; II - no § 5º-D deste artigo."

> **§ 24.** "Para efeito de aplicação do § 5º-K, considera-se folha de salários, incluídos encargos, o montante pago, nos doze meses anteriores ao período de apuração, a título de remunerações a pessoas físicas decorrentes do trabalho, acrescido do montante efetivamente recolhido a título de contribuição patronal previdenciária e FGTS, incluídas as retiradas de pró-labore." (Redação dada pela LC 155/2016.) O § 25, que segue, restringe às remunerações informadas na forma prevista no texto, e não li o resto dele.

**§ 5º-I (literal, vigente).** "Sem prejuízo do disposto no § 1º do art. 17 desta Lei Complementar, as seguintes atividades de prestação de serviços serão tributadas na forma do Anexo V desta Lei Complementar:" (Redação dada pela LC 155/2016.) São sempre Anexo V, mas vão ao Anexo III se r ≥ 0,28 (§ 5º-J). Incisos em vigor:
- II - medicina veterinária;
- V - serviços de comissaria, de despachantes, de tradução e de interpretação;
- VI - engenharia, medição, cartografia, topografia, geologia, geodésia, testes, suporte e análises técnicas e tecnológicas, pesquisa, design, desenho e agronomia; (Redação dada pela LC 155/2016)
- VII - representação comercial e demais atividades de intermediação de negócios e serviços de terceiros;
- VIII - perícia, leilão e avaliação;
- IX - auditoria, economia, consultoria, gestão, organização, controle e administração;
- X - jornalismo e publicidade;
- XI - agenciamento, exceto de mão de obra;
- XII - outras atividades do setor de serviços que tenham por finalidade a prestação de serviços decorrentes do exercício de atividade intelectual, de natureza técnica, científica, desportiva, artística ou cultural, que constitua profissão regulamentada ou não, desde que não sujeitas à tributação na forma dos Anexos III ou IV desta Lei Complementar. (Redação dada pela LC 155/2016)

Os incisos I, III e IV (medicina; odontologia; psicologia etc.) foram revogados pela LC 155/2016. Isso está marcado no texto como "(Revogado pela Lei Complementar nº 155, de 2016)".

**Atividades do Anexo III que migram ao Anexo V com r < 0,28 (§ 5º-M).**
- **Do § 5º-B (Anexo III):** XVI - fisioterapia; XVIII - arquitetura e urbanismo; XIX - medicina, inclusive laboratorial, e enfermagem; XX - odontologia e prótese dentária; XXI - psicologia, psicanálise, terapia ocupacional, acupuntura, podologia, fonoaudiologia, clínicas de nutrição e de vacinação e bancos de leite.
- **Do § 5º-D (Anexo III, redação da LC 155/2016):**
  - I - administração e locação de imóveis de terceiros;
  - II - academias de dança, de capoeira, de ioga e de artes marciais;
  - III - academias de atividades físicas, desportivas, de natação e escolas de esportes;
  - IV - elaboração de programas de computadores, inclusive jogos eletrônicos, desde que desenvolvidos em estabelecimento do optante;
  - V - licenciamento ou cessão de direito de uso de programas de computação;
  - VI - planejamento, confecção, manutenção e atualização de páginas eletrônicas, desde que realizados em estabelecimento do optante;
  - IX - empresas montadoras de estandes para feiras;
  - XII - laboratórios de análises clínicas ou de patologia clínica;
  - XIII - serviços de tomografia, diagnósticos médicos por imagem, registros gráficos e métodos óticos, bem como ressonância magnética;
  - XIV - serviços de prótese em geral.
  - Os incisos VII, VIII, X e XI estão revogados.
- A F6 confirma o resumo "III ou V conforme o fator 'r'" para essas atividades em 2018.

**Demais atividades do Anexo III, sem fator r** (§ 5º-B incisos I a V, IX, XIII a XV e XVII; locação de bens móveis; § 5º-F). Estão no texto da F1 (§ 5º-B) e não as listei aqui.

**Regra operacional do Manual F5 (item 8.2.1) — rotina do sistema, não norma.** O Manual dá estes detalhes de operação:
- Se FS12 = 0 (com RBT12 = 0 ou maior), o fator r vale 0,01; se FS12 > 0 e RBT12 = 0, vale 0,28.
- Para empresa nova, o Manual descreve uma regra com soma de meses (há também fator r do mês de abertura com FSPA/RPA).
- Desde 04/2018 o sistema usa duas casas decimais sem arredondamento (0,2774 vira 0,27).
- Cita o art. 26 da Res. CGSN 140, que **não li**.
- Se r ≥ 0,28, usa Anexo III; se r < 0,28, Anexo V.
- Isso é rotina do PGDAS-D e não deve ser tratado como fundamento normativo sem checar a Res. CGSN 140.

## 4. Anexo IV e CPP fora do DAS (F1)

**§ 5º-C, literal:** "Sem prejuízo do disposto no § 1º do art. 17 desta Lei Complementar, as atividades de prestação de serviços seguintes serão tributadas na forma do Anexo IV desta Lei Complementar, hipótese em que não estará incluída no Simples Nacional a contribuição prevista no inciso VI do caput do art. 13 desta Lei Complementar, devendo ela ser recolhida segundo a legislação prevista para os demais contribuintes ou responsáveis:"
- I - construção de imóveis e obras de engenharia em geral, inclusive sob a forma de subempreitada, execução de projetos e serviços de paisagismo, bem como decoração de interiores;
- VI - serviço de vigilância, limpeza ou conservação.
- VII - serviços advocatícios. (Incluído pela LC 147/2014)
- Os incisos II a V estão revogados.

**Art. 13, caput, inciso VI** (a contribuição referida no § 5º-C), literal: "Contribuição Patronal Previdenciária - CPP para a Seguridade Social, a cargo da pessoa jurídica, de que trata o art. 22 da Lei nº 8.212, de 24 de julho de 1991, exceto no caso da microempresa e da empresa de pequeno porte que se dedique às atividades de prestação de serviços referidas no § 5º-C do art. 18 desta Lei Complementar;"

**Observação sobre o texto da lei.** O Anexo IV da lei não tem coluna CPP, em coerência com essa exclusão.

## 5. Vigência

**LC 155/2016, art. 11 (F2), literal:** "Esta Lei Complementar entra em vigor na data de sua publicação, produzindo efeitos: I - na data de sua publicação, com relação ao art. 9º desta Lei Complementar; II - a partir de 1º de janeiro de 2017, com relação aos arts. 61-A, 61-B, 61-C e 61-D da Lei Complementar nº 123, de 14 de dezembro de 2006; III - a partir de 1º de janeiro de 2018, quanto aos demais dispositivos."
- Os cinco Anexos da F1/F2 trazem "(Vigência: 01/01/2018)".
- Verificado: as tabelas valem desde **01/01/2018**.
- Inferência minha: continuam valendo durante todo 2026, porque as mudanças encontradas só produzem efeito em 2027.

**2027, só registro. As tabelas de 2027 não foram transcritas.**
- **LC 214/2025, art. 519 (F3):** "Os Anexos I a V da Lei Complementar nº 123, de 14 de dezembro de 2006, passam a vigorar com a redação dos Anexos XVIII a XXII desta Lei Complementar."
- **LC 214/2025, art. 544 (F3):** o inciso III produz efeitos a partir de 1º de janeiro de 2027 em relação aos arts. 519 a 534, entre outros. Esse inciso foi reescrito pela **LC 227/2026**, que manteve "519 a 534" e acrescentou os arts. 168 a 171, 309 a 315, 444 e 462.
- **LC 214/2025, art. 520:** acrescenta o Anexo VII à LC 123.
- **Em cada Anexo da F1:** a página do Planalto traz "(Vide Lei Complementar nº 214, de 2025) Produção de efeitos".
- **LC 227/2026 (F4), art. 169:** altera o art. 18 da LC 123 (a parte vista inclui o § 4º). Efeitos a partir de 01/01/2027 (art. 170, I, "b"). Não li o art. 169 inteiro.
- **LC 227/2026, Anexo XX:** o Anexo III aparece com "(Vigência: 1º/1/2027 a 31/12/2028)". Isso indica vigências escalonadas, que não detalhei.
- **Res. CGSN 190/2026 (F7, cópia):**
  - Art. 6º: "Os Anexos I a V da Resolução CGSN nº 140, de 22 de maio de 2018, passam a vigorar com a seguinte redação:".
  - Art. 7º: acrescenta o Anexo XIII.
  - Art. 9º, literal: "Esta Resolução entra em vigor na data de sua publicação no Diário Oficial da União e produzirá efeitos a partir de 1º de janeiro de 2027."
  - Isso responde à pergunta do pedido: **sim**, a Res. 190 e a LC 214 alteram as tabelas a partir de 01/01/2027, e não antes.
  - Inferência: a Res. 140 reproduz os Anexos I a V. Não li o texto original da Res. 140.

## 6. Exemplos numéricos oficiais (Manual F5, itens 8.1 e 12)

Todos usam PA de 2018 e tabelas idênticas às de 2026. O Manual diz (item 12): "O cálculo do valor devido no PGDAS-D considera todas as casas decimais. Neste manual, para fins didáticos, foi demonstrado até a 5ª casa decimal." O RBT12 informado é o valor que o Manual indica, e as contas conferem.

**Exemplo 4 do Manual — Anexo III, fator r = 0,50, 3ª faixa** (PDF p. 110–111)
- FS12 = 250.000,00; RBT12 = 500.000,00; RPA 07/2018 = 10.000,00. Fator r = 250.000 / 500.000 = 0,50, logo Anexo III.
- Alíquota nominal 13,50%; parcela a deduzir R$ 17.640,00.
- Alíquota efetiva = (500.000 × 13,50% – 17.640) / 500.000 = **9,972%**. Valor devido = 10.000 × 9,972% = **997,20**.

| | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS | Total |
|---|---|---|---|---|---|---|---|
| Repartição 3ª faixa | 4,00% | 3,50% | 13,64% | 2,96% | 43,40% | 32,50% | 100% |
| Alíquota efetiva do tributo | 0,39888% | 0,34902% | 1,36018% | 0,29517% | 4,32785% | 3,24090% | 9,97200% |
| Valor devido (R$) | 39,89 | 34,90 | 136,02 | 29,52 | 432,78 | 324,09 | 997,20 |

Na extração do PDF a tabela ficou desalinhada. Reconstruí as colunas pela ordem dos tributos, e os valores conferem com repartição × 9,972%.

**Exemplo 5 do Manual — Anexo V, fator r = 0,20, 3ª faixa** (PDF p. 111–112)
- FS12 = 100.000,00; RBT12 = 500.000,00; RPA = 10.000,00. r = 0,20, logo Anexo V.
- Alíquota nominal 19,50%; parcela a deduzir R$ 9.900,00.
- Alíquota efetiva = (500.000 × 19,50% – 9.900) / 500.000 = **17,52%**. Valor devido = **1.752,00**.

| | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS | Total |
|---|---|---|---|---|---|---|---|
| Repartição 3ª faixa | 24,00% | 15,00% | 14,92% | 3,23% | 23,85% | 19,00% | 100% |
| Alíquota efetiva | 4,20480% | 2,62800% | 2,61398% | 0,56590% | 4,17852% | 3,32880% | 17,52% |
| Valor devido (R$) | 420,48 | 262,80 | 261,40 | 56,59 | 417,85 | 332,88 | 1.752,00 |

**Exemplo 2 do Manual — Anexo III, 2ª faixa** (PDF p. 108–109). A empresa tem duas receitas no mesmo mês.
- RBT12 = 300.000.
- RPA2 (prestação de serviços, Anexo III) = 100.000, nominal 11,20%, PD 9.360,00.
- Alíquota efetiva = **8,08%**. Valor devido = **8.080,00**.

| | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS | Total |
|---|---|---|---|---|---|---|---|
| Repartição 2ª faixa | 4,00% | 3,50% | 14,05% | 3,05% | 43,40% | 32,00% | 100% |
| Alíquota efetiva | 0,3232% | 0,2828% | 1,13524% | 0,24644% | 3,50672% | 2,5856% | 8,08% |
| Valor devido (R$) | 323,20 | 282,80 | 1.135,24 | 246,44 | 3.506,72 | 2.585,60 | 8.080,00 |

**Exemplo 8 do Manual — Anexo III, RBT12 na 6ª faixa** (PDF p. 115–117). Estado sem sublimite de R$ 1,8 milhão, com sublimite vigente de R$ 3.600.000,00.
- RBT12 = 4.500.000; RBA = 4.000.000; RPA = 1.000.000.
- Parcela que não excede o sublimite: P1 = 600.000. Parcela que excede: P2 = 400.000.
- Alíquota efetiva da 6ª faixa = (4.500.000 × 33,00% – 648.000) / 4.500.000 = **18,60%**.
- ISS pela 5ª faixa = [(4.500.000 × 21,00% – 125.640) / 4.500.000] × 33,5% = **6,09968%**. O excedente sobre 5% é 1,09968%.
- Redistribuição do excedente (valores do Manual): IRPJ 0,0662%, CSLL 0,0578%, Cofins 0,2120%, PIS 0,0460%, CPP 0,7177%.
- Valor devido P1 = 600.000 × (18,60% + 6,09968%) = 600.000 × 24,69968% = **148.198,08**.

| | IRPJ | CSLL | Cofins | PIS/Pasep | CPP | ISS | Total |
|---|---|---|---|---|---|---|---|
| Repartição 6ª faixa | 35,00% | 15,00% | 16,03% | 3,47% | 30,50% | – | 100% |
| Alíquota efetiva 6ª faixa | 6,51000% | 2,79000% | 2,98158% | 0,64542% | 5,67300% | – | 18,60% |
| Percentual efetivo ISS | | | | | | 5,00% | |
| Sobra ISS 5ª faixa | 0,0662% | 0,0578% | 0,2120% | 0,0460% | 0,7177% | – | 1,09968% |
| Alíquota efetiva com redistribuição | 6,57620% | 2,84784% | 3,19360% | 0,69139% | 6,39065% | 5,00% | 24,69968% |
| Valor devido (R$) | 39.457,20 | 17.087,06 | 19.161,59 | 4.148,32 | 38.343,91 | 30.000,00 | 148.198,08 |

Os cálculos da parcela P2 (que excedeu o sublimite) foram lidos só em parte e não os transcrevi.

**Exemplo do item 8.1 — Anexo I** (PDF p. 75, para teste de fórmula pura). Receitas de 12 meses = R$ 1.500.000; nominal 10,70%; PD 22.500,00. Alíquota efetiva = (1.500.000 × 10,70% – 22.500) / 1.500.000 = 138.000 / 1.500.000 = 0,092 = **9,2%**. A frase "Para determinação da alíquota efetiva, quando RBT12=0, considerar RBT12=1" está literal no item 8.1.

Outros exemplos do Manual, não transcritos: Exemplo 1 (Anexo I, 2ª faixa), 3 (início de atividade), 6, 7 (regime de caixa), 10 (6ª faixa Anexo I). Não há exemplo numérico do Anexo IV no Manual (verifiquei a lista de exemplos; só aparece a relação de atividades do Anexo IV).

## Classificação

**Verificado** (li e conferi):
- As tabelas de F1 e F2, e a coincidência numérica entre elas.
- A soma de 100% das repartições.
- Os arts. 18 e 13 da LC 123, os §§ 5º-B a 5º-M e o § 24.
- O art. 11 da LC 155.
- Os arts. 519, 520 e 544 da LC 214, na redação dada pela LC 227.
- Os exemplos e fórmulas do Manual.
- O art. 9º da Res. 190, em cópia.

**Inferido:**
- As tabelas de 2018 permanecem as vigentes durante 2026, porque as mudanças encontradas só entram em 2027.
- O sinal "–" na fórmula do rodapé.
- A Res. 140 reproduz os Anexos I a V.

**Não obtido:**
- Texto oficial integral da Res. CGSN 140 (art. 25 e 26 em especial).
- Leitura completa do art. 169 da LC 227 e dos Anexos XVIII a XXII de 2027.
- DOU original da Res. 190.
- Conferência célula a célula dos Anexos reproduzidos como imagem no Manual F5.
- Exemplo numérico oficial do Anexo IV.

**Divergências entre fontes:** nenhuma de valores numéricos entre F1, F2 e F5. Só há a divergência de data de publicação da Res. 190 (item 1) e diferenças de rótulo: o título do Anexo III diz "serviços não relacionados no § 5º-C", mas ele também recebe atividades do § 5º-B e do § 5º-D, que passam ao Anexo V com r < 0,28.

**Pendências para decisão do Fred ou do `arquiteto-senior` (não resolvi):**
1. Obter o texto oficial da Res. CGSN 140, arts. 25 e 26, que cobre fator r e a regra de RBT12 > 3,6 milhões. Se o Portal não oferece link direto estável, há de decidir se a cópia do normaslegais basta como fonte secundária.
2. Decidir como o produto trata a faixa 6 (RBT12 > 3,6 milhões) e o sublimite estadual. O Manual traz a regra, mas ela depende de sublimite por UF, que não pesquisei.

## Arquivos locais (para reprodução)

- Planalto: `.../scratchpad/anexos/planalto/lc123.html`, `lc123s.txt` (com marcação de riscado entre « »), `lc123cur.txt`.
- Leis: `.../scratchpad/anexos/lcp155/`, `lcp214/` e `lcp227/` (`.html` e `.txt`).
- Manual e evolução: `.../scratchpad/anexos/pdf/pgdasd.pdf`, `pgdasd.txt`, `evolucao.pdf`.
- Res. 190: `.../scratchpad/anexos/cgsn/r190.html`, `r190.txt`.
- Scripts de extração: `.../scratchpad/scripts/ext.py` e `ext2.py`.

Sources:
- [LC 123/2006 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm)
- [LC 155/2016 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp155.htm)
- [LC 214/2025 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm)
- [LC 227/2026 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp227.htm)
- [Manual do PGDAS-D (Portal do Simples Nacional)](https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf)
- [Evolução legislativa dos anexos (Portal do Simples Nacional)](https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/Anexos_LC%20123_Evolucao_Historica.pdf)
- [Res. CGSN 190/2026 (cópia, normaslegais)](https://www.normaslegais.com.br/legislacao/Resolucao-cgsn-190-2026.htm)
- [Res. CGSN 140/2018 (cópia parcial, normaslegais)](https://www.normaslegais.com.br/legislacao/resolucao-cgsn-140-2018.htm)
