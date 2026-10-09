# Consulta ao contador-senior sobre os feriados de Palmas e do Tocantins — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Delegação:** RC-173, item 6 (a tabela de feriados locais nasce preenchida para Palmas e o Tocantins) · **Marcas:** *lido* = texto oficial aberto hoje; *cópia* = texto íntegro em site terceiro; *secundário* = ato de outro órgão, notícia ou calendário; *não conferido* = conhecimento meu sem texto aberto.

**O que li antes de responder (repositório):** `/home/user/DataLedger/docs/planos/DL-084-rotina-do-presumido.md` (linhas 25-39 e 76, 88); `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-pe83-pe84-pe85.md` (itens 9 e 11 da PE-83); cópia local da Lei 9.093 baixada do Planalto em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/leis/l9093.html` (Planalto devolveu 503 hoje).

**Como cheguei às fontes oficiais.** A busca da Assembleia Legislativa do TO funciona por POST em `https://www.al.to.leg.br/legislacaoEstadual` (campos `documento.numero`, `documento.ano`, `documento.texto`) e devolve PDF por `/arquivo/<id>`. O portal legislativo de Palmas (`legislativo.palmas.to.gov.br`) e o Diário Oficial do Município enviam só o certificado-folha e omitem o intermediário público da Let's Encrypt ("YR1"); baixei esse intermediário no endereço AIA publicado no próprio certificado (`http://yr1.i.lencr.org/`) e montei um bundle com o CA do sistema, **sem desligar a verificação TLS**. Os sites do Governo do Estado (`diariooficial.to.gov.br`, `www.to.gov.br`) recusaram a conexão (reset) por curl e WebFetch: **não li nenhum texto do DOE-TO hoje.** Os PDFs lidos estão em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/feriados/`.

---

## A resposta

Entram na tabela inicial **três feriados estaduais** (15/8, 8/9, 5/10) e **dois municipais de Palmas** (19/3 e 20/5), todos com a lei lida no texto oficial hoje. **18 de março fica fora:** a Lei 960/1998 criou o feriado, mas a Lei 2.013/2009 reescreveu o parágrafo único e tirou a palavra "feriado"; nada posterior o restaurou. A **Sexta-feira Santa** é feriado municipal de Palmas por lei (Lei 577/96, art. 1º, I), mas já está coberta pela tabela (b) de dias sem expediente bancário nacional — registre a fonte municipal nela, sem duplicar. **Finados (2/11)** também consta da lei municipal, mas é nacional: fora. Novidade que não estava na pergunta: **15 de agosto (Senhor do Bonfim)** é feriado estadual desde a Lei 4.509/2024, vigente desde 2025.

Reflexo cruzado importante para o produto: o Estado **transferiu o feriado de 5/10/2026 para hoje, 9/10/2026** (Decreto estadual 7.238, de 23/09/2026, com base na Lei 1.088/1999), e Palmas acompanhou (Decreto municipal 2.993, de 28/09/2026, *lido*). Isso não muda a tabela permanente, mas mostra que **a tabela precisa aceitar exceção por ano** (data movida por decreto) — a data fixa da lei não basta para o aviso "sem expediente bancário na praça" em anos como este.

---

## 1. Feriados estaduais do Tocantins

### 1.1 — 15 de agosto — Dia do Senhor do Bonfim — ESTADUAL

- **Norma:** Lei nº 4.509, de 25/09/2024, art. 1º ("Fica declarado feriado estadual o dia 15 de agosto, em celebração ao Dia do Senhor do Bonfim"). Publicada no DOE nº 6.664, de 26/09/2024. Vigência: data da publicação (art. 3º); primeiro ano observado: 2025.
- **URL lida:** https://www.al.to.leg.br/arquivo/71668 (redireciona para `/arquivos/lei_4509-2024_71668.PDF`) — **09/10/2026** — *lido*.
- **Alteração/revogação:** nenhuma anotada no texto da ALETO; nenhuma lei posterior localizada na busca por "feriado" (duas páginas de resultados lidas).
- **Confirmação secundária:** Portaria SJTO-Diref 1/2025 da Justiça Federal lista "15 — Dia do Senhor do Bonfim — Feriado Estadual — Lei nº 4.509, de 25/09/2024" (*secundário*, https://trf1.jus.br/sjto/conteudo/impressos/1697-Portaria_SJTO_Diref_21993179.pdf).
- **Segurança:** alta.

### 1.2 — 8 de setembro — Nossa Senhora da Natividade, Padroeira do Estado — ESTADUAL

- **Norma:** Lei nº 627, de 28/12/1993, art. 1º ("Fica instituído feriado estadual, o dia 08 (oito) de setembro de cada ano") e art. 2º (reverência a Nossa Senhora da Natividade). Publicada no DOE nº 298.
- **URL lida:** https://www.al.to.leg.br/arquivo/6883 — **09/10/2026** — *lido*.
- **Alteração/revogação:** nenhuma anotada (a ALETO anota alterações no próprio PDF, como fez na Lei 960 — ver 1.4; a ausência de anotação aqui é **inferência** de vigência, não prova).
- **Confirmação secundária:** Portarias SJTO-Diref 1/2021 e 1/2025 (*secundário*).
- **Segurança:** alta.

### 1.3 — 5 de outubro — Criação do Estado e promulgação da primeira Constituição Estadual — ESTADUAL

- **Norma:** Lei nº 098, de 17/11/1989, art. 1º ("É declarado feriado, em todo o território do Estado, o dia 05 (cinco) de outubro de cada ano, data de criação do Estado do Tocantins e da promulgação da primeira Constituição Estadual"). Publicada no DOE nº 23. Assinada em Miracema do Tocantins.
- **URL lida:** https://www.al.to.leg.br/arquivo/6358 — **09/10/2026** — *lido*.
- **Alteração/revogação:** nenhuma anotada. **Transferência excepcional em 2026:** ver item 4.
- **Segurança:** alta na lei; ver item 3 sobre "data magna".

### 1.4 — 18 de março — Dia da Autonomia — ESTADUAL — **NÃO é feriado**

- **Norma original:** Lei nº 960, de 17/03/1998, art. 1º, parágrafo único, redação original: "É feriado estadual a data que trata o caput deste artigo". Publicada no DOE nº 676.
- **Alteração:** Lei nº 2.013, de 18/02/2009, art. 1º, deu nova redação ao parágrafo único: "São os órgãos dos diversos poderes responsáveis por promover ações a fim de comemorar esse dia, organizando festividades nas diversas comunidades do Estado, com maior participação popular". **A palavra "feriado" saiu.** O "Dia da Autonomia" continua existindo como data comemorativa (caput), sem ser feriado. Publicada no DOE nº 2.839.
- **URLs lidas:** https://www.al.to.leg.br/arquivo/15717 (Lei 960, texto compilado com a nota "*Parágrafo único com redação determinada pela Lei nº 2.013, de 18/02/2009*") e https://www.al.to.leg.br/arquivo/15724 (Lei 2.013) — **09/10/2026** — ambos *lidos*.
- **Restauração posterior?** Houve projeto em 2013 para restaurar a redação original (notícia do Conexão Tocantins de 12/03/2013, *secundário*). **Não localizei lei que o tenha feito:** a busca textual da ALETO por "feriado" (duas páginas) e por "Autonomia" não devolveu nenhuma lei nesse sentido, e as portarias da Justiça Federal de 2021 e 2025 **não listam** 18/3 (*secundário*). Em 2014 a associação comercial de Palmas dizia que 18/3 não era feriado (*secundário*).
- **Segurança:** alta de que não é feriado hoje; a busca por lei restauradora não é exaustiva (a busca da ALETO é por relevância, sem contagem total exibida).

### 1.5 — Fundamento da transferência por decreto

- **Norma:** Lei nº 1.088, de 23/09/1999, art. 1º: "Fica o Chefe do Poder Executivo autorizado a antecipar ou prorrogar feriados e dias santificados, sempre que convier aos interesses do serviço público, em harmonia com os reclamos dos segmentos organizados da sociedade." Publicada no DOE nº 845.
- **URL lida:** https://www.al.to.leg.br/arquivo/7336 — **09/10/2026** — *lido*.
- **Por que importa:** é a base legal pela qual o governador move feriado estadual de ano em ano (como fez em 2026). A redação fala em "interesses do serviço público", o que sustenta a leitura de que a transferência alcança o **serviço público**; se alcança bancos e setor privado é a dúvida do item 5.

**Nenhum outro feriado estadual localizado.** Das leis devolvidas pela ALETO para "feriado", as únicas que criam ou alteram feriado são as cinco acima; as demais (custas, estatutos, plantões, Diário Oficial Eletrônico etc.) só usam a palavra.

---

## 2. Feriados municipais de Palmas

### 2.1 — 19 de março — São José, Padroeiro de Palmas — MUNICIPAL (religioso)

- **Norma:** Lei nº 577/96, de 02/04/1996, art. 1º, III ("São José-Padroeiro de Palmas (19 de março)"). Lei promulgada pela Câmara a partir da Medida Provisória municipal nº 34, de 14/03/1996.
- **URL lida:** `https://legislativo.palmas.to.gov.br/media/leis/LEI ORDINARIA Nº 577 de 02-04-1996 13-18-58.pdf` (localizada pela busca `/resultado-pesquisa/?opcao=numero&tipo_lei=0&texto=577`) — **09/10/2026** — *lido*.
- **Alteração/revogação:** busca textual por "Lei nº 577", "577/96", "Calendário de Feriados" e "feriados municipais" no portal não devolveu lei alteradora (a LC 455/2026 que apareceu é sobre loteamento — falso positivo). Decreto municipal 2.881, de 26/03/2026 (*lido*), ainda cita a Lei 577/96 como vigente.
- **Confirmação secundária:** Portarias SJTO-Diref 1/2021 e 1/2025; notícia de 17/03/2026 (Justiça Federal sem expediente em Palmas em 19/03/2026 pela Portaria SJTO-Diref 1/2026, que não localizei em PDF).
- **Segurança:** alta.

### 2.2 — 20 de maio — Aniversário de Palmas / Lançamento da Pedra Fundamental — MUNICIPAL (civil)

- **Norma:** Lei nº 108/91, de 15/05/1991, art. 1º ("Fica instituído o Feriado Municipal em Palmas [...] no dia 20 de maio, consagrado ao aniversário da cidade"); **mantido** pela Lei 577/96, art. 2º ("Permanece o dia 20 de maio feriado municipal, previsto na Lei nº 108/91, passando esta data comemorativa do Lançamento da Pedra Fundamental de Palmas").
- **URL lida:** `https://legislativo.palmas.to.gov.br/media/leis/LEI ORDINARIA Nº 108 de 15-05-1991 7-5-52.pdf` (só aparece na busca por texto "feriado municipal"; a busca por número 108 não a devolve) — **09/10/2026** — *lido*; Lei 577/96 idem.
- **Segurança:** alta na lei municipal. **Atenção:** a Lei federal 9.093/95 só admite feriado civil municipal no centenário (art. 1º, III) e feriados religiosos até quatro (art. 2º); um feriado civil de aniversário não cabe literalmente em nenhum dos dois. Isso **não muda o produto** (a tabela só gera aviso, e os bancos de Palmas fecham — ver item 5), mas é o motivo de eu não tratar o 20/5 como "feriado civil" na redação da tabela: chamar de "feriado municipal (Lei 108/91 e 577/96)" e pronto.

### 2.3 — Sexta-feira Santa (móvel) — MUNICIPAL (religioso) — coberta pela tabela (b)

- **Norma:** Lei 577/96, art. 1º, I ("6ª Feira Santa — data móvel") — *lido*. É a hipótese da Lei 9.093, art. 2º, "neste incluída a Sexta-Feira da Paixão". Decreto 2.881/2026 (*lido*) cita "o feriado de sexta-feira santa, constante no art. 1º, inciso I, da Lei n° 577, de 2 de abril de 1996".
- **Produto:** já está na tabela (b) como dia sem expediente bancário nacional (Febraban, lista 2026 *lida* hoje: "03 de abril — Sexta-Feira da Paixão"). **Não duplicar** na tabela local; acrescentar à fonte da linha (b) a referência municipal.

### 2.4 — 2 de novembro — Finados — MUNICIPAL — fora

- **Norma:** Lei 577/96, art. 1º, II — *lido*. É feriado nacional pela Lei 662/49 (*lida em 08/10*). Redundante: fora da tabela local.

**Total municipal:** a Lei 577/96 fixa exatamente quatro datas (três religiosas + 20/5), dentro do limite do seu art. 1º. Não há feriado de Corpus Christi, Carnaval ou outro por lei municipal — nesses dias Palmas edita só **ponto facultativo** por decreto.

---

## 3. "Data magna" do Estado (Lei 9.093, art. 1º, II)

- **Texto federal (cópia local do Planalto):** "Art. 1º São feriados civis: I - os declarados em lei federal; II - a data magna do Estado fixada em lei estadual."
- **O que verifiquei:** a Lei 98/1989 **não usa a expressão "data magna"**; declara feriado o 5 de outubro como "data de criação do Estado do Tocantins e da promulgação da primeira Constituição Estadual". A Constituição do Tocantins (PDF da ALETO, 185 páginas, https://al.to.leg.br/arquivos/documento_68367.PDF, *lido* hoje por busca textual) **não contém** "data magna" nem declara feriado.
- **O que infiro:** em substância, o 5 de outubro é a data magna do Estado (criação pela CF/88, art. 13 do ADCT, e promulgação da Constituição Estadual em 05/10/1989), fixada em lei estadual como feriado. É a única das três que cabe no art. 1º, II. **8 de setembro e 15 de agosto são feriados religiosos estaduais**, figura que a Lei 9.093 não prevê (ela só admite feriado religioso por **lei municipal**). É problema de constitucionalidade que não cabe ao produto resolver: na prática o Estado observa, a Justiça Federal observa e os bancos locais fecham. Para a tabela, os três entram com a mesma função (aviso).
- **Segurança:** alta de que nenhuma lei usa o termo; média na qualificação do 5/10 como data magna (leitura minha).

---

## 4. Decretos de 2026 que mudam datas ou criam ponto facultativo (só registro)

| Esfera | Ato | Efeito | Fonte e marca |
| --- | --- | --- | --- |
| Estado | Decreto nº 7.097/2026 | Ponto facultativo 16 e 17/02 (Carnaval) | notícia Conexão TO 11/02/2026 — *secundário* |
| Estado | Decreto nº 7.142/2026 | Ponto facultativo 20/04 (véspera de Tiradentes) | notícia Conexão TO 15/04/2026 — *secundário* |
| Estado | Decreto nº 7.168/2026 | Ponto facultativo 4 e 5/06 (Corpus Christi) | notícia Conexão TO 26/05/2026 — *secundário* |
| **Estado** | **Decreto nº 7.238, de 23/09/2026** (DOE ed. 7.149, de 23/09/2026) | **Transfere, só em 2026, o feriado estadual de 5/10 para 9/10** (racionalização do serviço público pela proximidade de 12/10) | citado com número, data e edição do DOE no Decreto municipal 2.993/2026 (*lido*); notícia NC News 29/09/2026 (*secundário*). **Texto do DOE não lido** (site inacessível hoje) |
| Palmas | Decreto nº 2.881, de 26/03/2026 | Ponto facultativo 02/04 (quinta de endoenças) | https://legislativo.palmas.to.gov.br/media/leis/decreto-2.881-2026-03-26-27-3-2026-14-22-4.pdf — *lido* |
| Palmas | Decreto nº 2.900/2026 | Ponto facultativo 20/04 | notícia Conexão TO 16/04/2026 — *secundário* |
| **Palmas** | **Decreto nº 2.993, de 28/09/2026** (DOM nº 4.042, de 28/09/2026) | Fixa 9/10/2026 para as comemorações do feriado estadual de 5/10, "excepcionalmente transferido pelo Poder Executivo do Estado"; sem atividade nos órgãos municipais em 9/10, salvo essenciais | https://legislativo.palmas.to.gov.br/media/leis/decreto-2.993-2026-09-28-29-9-2026-16-14-9.pdf — *lido* |

Não localizei decreto estadual ou municipal de 2026 que mova 15/8, 8/9, 19/3 ou 20/5. Para o Carnaval e Corpus Christi de Palmas em 2026 não achei o decreto municipal (irrelevante: ponto facultativo não fecha banco).

---

## 5. Os bancos de Palmas fecham nesses feriados?

- **Norma bancária (lida hoje):** Resolução CMN nº 4.880, de 23/12/2020, art. 6º: "Não são considerados dias úteis, para fins de operações praticadas no mercado financeiro e de prestação de informações ao Banco Central do Brasil, os sábados, domingos e feriados de âmbito nacional, bem como: I - a segunda-feira e a terça-feira de Carnaval; e II - o dia dedicado a Corpus Christi." Art. 2º, § 1º, II: horário especial na Quarta-feira de Cinzas, 24/12 e "festividades locais". Art. 3º: sem atendimento no último dia útil do ano. (JSON oficial do BCB, https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolu%C3%A7%C3%A3o%20CMN&p2=4880 — *lido*, DOU 24/12/2020.)
- **O que a norma diz e o que não diz:** a Resolução define dia **não útil para o mercado financeiro** só para feriados **nacionais** mais Carnaval e Corpus Christi. **Ela não manda fechar agência em feriado estadual ou municipal, nem proíbe.** O fechamento local é prática institucional: a Febraban mantém um sistema oficial de "Feriados Estaduais e Municipais" por UF/município (https://feriadosbancarios.febraban.org.br/Municipais/Listar, *lido* hoje; a lista de municípios do TO inclui PALMAS), e a página federal diz que os feriados nacionais "não são considerados dias úteis" nos termos da Res. 4.880. **A consulta municipal exige token reCAPTCHA v3 e devolveu a página vazia sem ele; não a contornei.** Então **não li** a lista Febraban de Palmas.
- **Lista federal Febraban 2026 (*lida*, JSON oficial):** 1/1, 16/2, 17/2, 3/4, 21/4, 1/5, 4/6, 7/9, 12/10, 2/11, 15/11, 20/11, 25/12 — confirma a tabela (b) da DL-084 (Carnaval, Sexta-feira Santa, Corpus Christi) e o 20/11.
- **Confirma a prática local:** ninguém oficial; Justiça Federal fecha em Palmas em 19/3 e 20/5 (*secundário*); matérias de imprensa dizem que agência fecha em feriado municipal da praça (*secundário*). O escritório do Fred já antecipou DARF por feriado municipal (RC-173): é a melhor evidência de que a praça fecha.
- **Consequência para o vencimento do IRPJ/CSLL:** nenhuma das cinco datas é último dia útil de mês; o risco real é nas **quotas** e em outros tributos, e principalmente no **5 de outubro transferido**: em 2026, 5/10 (segunda) teve expediente normal na administração e 9/10 (hoje) não — se os bancos de Palmas seguiram o Estado ou a lei, **não sei**.
- **Segurança:** alta na norma; média-baixa na prática bancária local (não conferida na fonte Febraban).

---

## Tabela: entra na tabela inicial / fica fora

| Data | Nome | Esfera | Norma | Marca | Decisão |
| --- | --- | --- | --- | --- | --- |
| 15/08 | Dia do Senhor do Bonfim | Estadual | Lei 4.509, 25/09/2024, art. 1º | *lido* | **Entra** (vigência desde 2025) |
| 08/09 | N. Sra. da Natividade, Padroeira do TO | Estadual | Lei 627, 28/12/1993, arts. 1º-2º | *lido* | **Entra** |
| 05/10 | Criação do Estado e 1ª Constituição | Estadual | Lei 098, 17/11/1989, art. 1º | *lido* | **Entra**; em 2026 observado em 09/10 por decreto (exceção anual) |
| 18/03 | Dia da Autonomia | Estadual | Lei 960/1998 alterada pela Lei 2.013/2009 | *lido* | **Fora**: deixou de ser feriado em 2009 |
| 19/03 | São José, Padroeiro de Palmas | Municipal | Lei 577/96, art. 1º, III | *lido* | **Entra** |
| 20/05 | Aniversário de Palmas | Municipal | Lei 108/91, art. 1º; Lei 577/96, art. 2º | *lido* | **Entra** |
| móvel | Sexta-feira Santa | Municipal | Lei 577/96, art. 1º, I | *lido* | **Fora da tabela local**: já é dia sem expediente bancário nacional (tabela b); citar a lei municipal na fonte da linha (b) |
| 02/11 | Finados | Municipal | Lei 577/96, art. 1º, II | *lido* | **Fora**: feriado nacional (Lei 662/49) |
| 09/10/2026 | 5/10 transferido | Estadual + Palmas | Decreto est. 7.238/2026; Decreto mun. 2.993/2026 | mun. *lido*; est. citado em ato oficial, texto não lido | **Fora da tabela permanente**; registrar como exceção de 2026 se o produto tiver esse campo |

**Sugestão de produto (minha posição, reversível pelo Fred):** a tabela local precisa de três coisas que a lei fixa e o decreto muda: (1) data fixa anual com lei e data da leitura; (2) **exceção por ano** ("em 2026 observado em 09/10, Decreto 7.238") — sem isso, em 2026 o aviso sairia no dia errado; (3) texto do aviso que diga "feriado local: confirmar expediente bancário na praça", porque a Res. 4.880 não garante o fechamento e eu não li a lista Febraban de Palmas. Hoje, 9/10/2026, é exatamente um dia em que o produto não saberia o que dizer.

---

## Pendências

1. **Texto do Decreto estadual 7.238/2026 no DOE-TO (ed. 7.149, 23/09/2026):** não lido; os sites do Estado recusaram conexão. O número, a data e a edição vêm do Decreto municipal 2.993/2026 (texto oficial de Palmas, *lido*). Conferir quando o DOE voltar — em especial se o texto alcança o setor privado ou só "os órgãos e entidades da Administração".
2. **Lista Febraban de feriados de Palmas:** exige reCAPTCHA; não contornei. É a única fonte institucional de "banco fecha ou não" por praça. O Fred pode abrir https://feriadosbancarios.febraban.org.br/Municipais/Listar no navegador (UF = TO, Município = PALMAS) e confirmar as cinco datas e o tratamento de 5/10 vs 9/10 em 2026.
3. **Lei restauradora do 18/3:** não localizada; a busca da ALETO não é exaustiva. Se alguém apresentar lei pós-2009, reabrir.
4. **Portaria SJTO-Diref 1/2026** (calendário 2026 da Justiça Federal em Palmas): citada em notícias, PDF não localizado. Não é fonte normativa; serviria só de confirmação secundária.
5. **Compatibilidade com a Lei 9.093/95:** feriados religiosos estaduais (8/9, 15/8) e feriado civil municipal de aniversário (20/5) não cabem literalmente na lei federal. Não afeta o produto (aviso), mas convém não escrever na interface que são "feriados civis nos termos da Lei 9.093".
6. **Palmas: decretos de Carnaval e Corpus Christi 2026** não localizados (irrelevante para banco).

**Fontes oficiais abertas hoje (09/10/2026):**
- https://www.al.to.leg.br/arquivo/71668 (Lei 4.509/2024) · https://www.al.to.leg.br/arquivo/6883 (Lei 627/1993) · https://www.al.to.leg.br/arquivo/6358 (Lei 098/1989) · https://www.al.to.leg.br/arquivo/15717 (Lei 960/1998, compilada) · https://www.al.to.leg.br/arquivo/15724 (Lei 2.013/2009) · https://www.al.to.leg.br/arquivo/7336 (Lei 1.088/1999) · https://al.to.leg.br/arquivos/documento_68367.PDF (Constituição do TO)
- `https://legislativo.palmas.to.gov.br/media/leis/LEI ORDINARIA Nº 577 de 02-04-1996 13-18-58.pdf` · `https://legislativo.palmas.to.gov.br/media/leis/LEI ORDINARIA Nº 108 de 15-05-1991 7-5-52.pdf` · https://legislativo.palmas.to.gov.br/media/leis/decreto-2.993-2026-09-28-29-9-2026-16-14-9.pdf · https://legislativo.palmas.to.gov.br/media/leis/decreto-2.881-2026-03-26-27-3-2026-14-22-4.pdf
- https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolu%C3%A7%C3%A3o%20CMN&p2=4880 (Res. CMN 4.880/2020) · https://feriadosbancarios.febraban.org.br/Home/ObterFeriadosFederais?ano=2026 · https://feriadosbancarios.febraban.org.br/Municipais/Listar
- Secundários: https://trf1.jus.br/sjto/conteudo/impressos/1697-Portaria_SJTO_Diref_21993179.pdf (Portaria SJTO-Diref 1/2025) · https://trf1.jus.br/sjto/conteudo/files/PORTARIA%20FERIADOS%20-%20PALMAS.pdf (Portaria 1/2021) · https://ncnews.com.br/2026/09/29/palmas-e-araguaina-transferem-feriado-de-5-para-9-de-outubro/ · https://conexaoto.com.br/2026/03/17/justica-federal-suspende-expediente-em-palmas-no-feriado-de-sao-jose · https://crcms.org.br/?p=35005 (reprodução do comunicado Febraban 2026) · https://conexaoto.com.br/2013/03/12/feriado-do-dia-da-autonomia-podera-ser-restaurado
