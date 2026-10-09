# Consulta ao contador-senior sobre as pendências PE-83, PE-84 e PE-85 — 09/10/2026

**Legislação validada até:** 09/10/2026 · **Delegação:** Fred, 09/10/2026, sobre as três pendências: *"Consulte o Fable 5.1 para responder essas 3 perguntas"* (RC-172) · **Marcas:** *lido* = texto oficial aberto hoje (Planalto, gov.br, Portal da NF-e, MOC 7.0 e NTs já baixados no scratchpad); *lido em 08/10* ou *lido em 09/10 (consulta anterior)* = texto oficial aberto nas consultas anteriores e não reaberto hoje; *cópia* = texto íntegro em site terceiro; *secundário* = notícia, fornecedor ou fórum; *não conferido* = conhecimento meu sem texto aberto. O que é **rotina/produto** está dito como tal: é a minha posição de contador sênior, reversível pelo Fred.

**O que li antes de responder (repositório):** `/home/user/DataLedger/docs/projeto/requisitos.md` (PE-83 a PE-85, HI-100 a HI-124, RC-172); `/home/user/DataLedger/docs/projeto/consultas/2026-10-08-contador-senior-presumido.md`; `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-leiaute-nfe.md`; `/home/user/DataLedger/docs/projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md`; as seções de decisão de `/home/user/DataLedger/docs/planos/DL-079-lucro-presumido-irpj-csll.md` (linhas 116-184), `/home/user/DataLedger/docs/planos/DL-080-recepcao-de-nfe.md` (127-191) e `/home/user/DataLedger/docs/planos/DL-081-escrituracao-das-nfe-de-saida.md` (115-194); `/home/user/DataLedger/apps/fiscal/presumido.py` (527-551, guarda de duplicidade); `/home/user/DataLedger/docs/projeto/backlog.md` (BL-685, BL-686). **Não localizei plano nem menção a "DL-082"** em `docs/` (grep em `docs/`, `backlog.md` e `estado.md`): a pergunta 3 da PE-85 fala dela como já planejada; aqui trato o pré-DAS de comércio pelo conteúdo, não pelo número.

**Lidos hoje em fonte oficial:** Lei 9.430 arts. 5º e 25; DL 1.598 art. 12 (caput e § 1º); LC 123 art. 3º § 1º; Lei 9.249 art. 15 § 1º, I; Lei 9.779 art. 15; Lei 9.093 arts. 1º e 2º; Lei 14.759 art. 1º; Lei 10.833 arts. 30 e 36; LC 87 arts. 11 § 3º, II e 12 § 4º (trecho); MOC 7.0 Anexo I (I17b, I17b-10, W07-10 a W16-10); NT 2026.008 v1.00 (íntegra) e NT 2026.009 v1.00 (íntegra); informes do Portal da NF-e até hoje; RFB "Instruções para emissão de DARF avulso" (gov.br); RFB Perguntas e Respostas "Contagem de prazos" (gov.br, atualizado até 31/12/2010). **Cópias íntegras lidas hoje:** SC Cosit 25/2023 (PDF no site do IBET); Res. CGSN 140, art. 17. **Não alcançado hoje:** Guia Prático da EFD ICMS/IPI (503), texto da SCI Cosit 16/2013, lista de feriados bancários da Febraban, tabela de CFOP do CONFAZ, Convênio ICMS 109/2024, Ato Conjunto RFB/CGIBS 8/2026.

---

## PE-83 — Rotina do Lucro Presumido

### 1. Quem classifica a atividade de presunção, e quando

- **Resposta.** O contador, **no cadastro da empresa, na entrada** (antes da primeira apuração), com uma atividade padrão por empresa e vigência; a nota só sugere. A classificação na apuração é a exceção, para corrigir o que a sugestão errou.
- **Fundamento.** Norma: Lei 9.249, art. 15, § 2º, "no caso de atividades diversificadas será aplicado o percentual correspondente a cada atividade" (*cópia*, transcrito na SC Cosit 25/2023, item 14; o § 1º, I, *lido* hoje). A lei fala em atividade da pessoa jurídica, não em código de serviço: é informação do contador. Rotina: é o que o sistema de referência também faz pelo cadastro (mapa fiscal, *secundário*).
- **O que o produto faz.** Manter HI-101 como está. Acrescentar só a regra de prazo: empresa do Presumido **sem atividade padrão vigente** aparece na lista de pendências do mês, não só na recusa da apuração.
- **Segurança:** alta.

### 2. Notas com mais de uma atividade

- **Resposta.** Na NFS-e nacional o caso é raro (um `cTribNac` por DPS); na NF-e a natureza já é **por item** (HI-118), o que resolve o problema sem rateio. Quando acontecer em receita informada ou em nota antiga, o rateio é **manual, em valores** que somem exatamente a base da nota, com trilha.
- **Fundamento.** Norma: Lei 9.249, art. 15, § 2º (*cópia*). Não há regra de rateio na lei: o contador separa pelo que foi efetivamente prestado ou vendido.
- **O que o produto faz.** Manter. Nada a mudar agora: o rateio manual já está previsto na consulta de 08/10, item 11, e a NF-e por item cobre o caso real da carteira.
- **Segurança:** alta.

### 3. CSLL retida estimada por 1/4,65 (HI-103)

- **Resposta.** Aceitar o fluxo "estimada + confirmação do contador", **com um teste de coerência** que o produto pode fazer sozinho: se `vRetCSLL` ≈ 4,65% da base (`vServ − desconto incondicional`), a estimativa 1/4,65 é consistente; se ≈ 1%, o tomador reteve só CSLL e o código 3 está errado (tratar como "a classificar", com aviso); fora dessas duas faixas, "a classificar". A fonte definitiva é o comprovante do tomador (EFD-Reinf R-4020), não a nota.
- **Fundamento.** Norma: Lei 10.833, art. 31, caput (4,65% = 1% CSLL + 3% Cofins + 0,65% PIS) e § 2º (isenção parcial muda a proporção) — *lido em 08/10*; art. 30 (hipóteses de retenção) e art. 36 (retenção é antecipação do devido) — *lidos* hoje. A separação por 1/4,65 só vale quando as três foram retidas às alíquotas-padrão; o teste de coerência confirma isso pela própria nota.
- **O que o produto faz.** Mudar pouco: acrescentar o teste de coerência à sugestão. Nenhuma dedução sem confirmação, como hoje.
- **Segurança:** média-alta.

### 4. Competência da dedução da retenção (HI-102)

- **Resposta.** Deduz-se no trimestre em que **a receita integrou a base**, não no do pagamento. Se a retenção só se materializa depois (o tomador retém ao pagar, e o pagamento cai no trimestre seguinte), a dedução continua pertencendo ao trimestre da receita: se ele já foi efetivado, reabre como "a retificar"; se o IRPJ daquele trimestre já foi pago, o excesso vira saldo negativo para PER/DCOMP. **Nunca** jogar a retenção para o trimestre seguinte.
- **Fundamento.** Norma: RIR/2018, art. 599 ("imposto pago ou retido na fonte sobre as receitas que integraram a base de cálculo") — *lido em 08/10*; IN 1.700, arts. 221, § 1º e 222, parágrafo único — *cópia*; Lei 10.833, art. 30 (a retenção ocorre nos "pagamentos efetuados") — *lido* hoje. Procurei hoje solução de consulta Cosit sobre retenção em trimestre posterior ao da receita e **não localizei** (*não conferido*). A prática de deduzir no trimestre do pagamento existe em escritórios por comodidade, mas não é o que o texto diz.
- **O que o produto faz.** Manter HI-102. Garantir que a confirmação de retenção posterior à efetivação reabra o trimestre de origem como "a retificar" (mesmo princípio do estorno em `receita.py`), e que o saldo negativo apareça como "PER/DCOMP", nunca como crédito automático.
- **Segurança:** alta na norma; média na operação (retificação de DCTFWeb/MIT é trabalho do escritório, fora do produto).

### 5. Arredondamento por linha (HI-100)

- **Resposta.** Manter: cada linha da memória em centavos (`ROUND_HALF_UP`), resíduo do rateio na última linha, soma fechando ao centavo.
- **Fundamento.** Rotina/produto: não há norma. O DARF e a ECF são em centavos; a memória que o contador confere linha a linha precisa somar. A diferença contra o cálculo "sem arredondar" é de centavos e fica documentada.
- **O que o produto faz.** Manter.
- **Segurança:** alta (decisão sem risco fiscal relevante).

### 6. Uso de 3 quotas

- **Resposta.** Rotina. Escritórios usam quotas em clientes com caixa apertado no mês seguinte ao trimestre; a 2ª quota custa só 1%, a 3ª Selic + 1%. Mostrar a quota única em destaque e o plano em quotas (2 ou 3) como **opção recolhida**, com um parâmetro por empresa "forma de recolhimento padrão" (única / quotas).
- **Fundamento.** Norma: Lei 9.430, art. 5º, caput e §§ 1º a 3º — *lido* hoje: quota única até o último dia útil do mês seguinte; até três quotas mensais iguais e sucessivas; nenhuma quota abaixo de R$ 1.000,00; imposto abaixo de R$ 2.000,00 em quota única; juros Selic a partir do 1º dia do 2º mês seguinte, mais 1% no mês do pagamento. O plano em duas quotas (rodada 1, A8) está dentro de "até três".
- **O que o produto faz.** Manter o cálculo; acrescentar o parâmetro por empresa para a tela abrir no plano que o escritório usa. Não é ruído: é informação de caixa que o cliente pergunta.
- **Segurança:** alta.

### 7. Limite da LC 224 por CNPJ raiz, somando filiais (HI-107)

- **Resposta.** Confirmo: o limite de R$ 5 milhões é da **pessoa jurídica**, somando todos os estabelecimentos. **Corrijo a fonte** da consulta de 08/10: a Lei 9.779, art. 15 (*lido* hoje), centraliza na matriz o IRRF (I), o crédito presumido de IPI (II), PIS/Cofins (III) e as declarações (IV) — **não menciona IRPJ nem CSLL**. A conclusão não precisa dela: o contribuinte do IRPJ e da CSLL é a pessoa jurídica (Lei 9.430, arts. 1º e 25, "a pessoa jurídica", *lido*), e a LC 224, art. 4º, § 5º fala em "receita bruta total" da PJ no ano-calendário (*lido em 08/10*). Filial não é pessoa jurídica.
- **Fundamento.** Acima. ECF é uma por PJ (*não conferido*, conceito estável).
- **O que o produto faz.** Manter HI-107; corrigir a redação da hipótese para citar Lei 9.430, art. 1º e LC 224, art. 4º, § 5º em vez da Lei 9.779.
- **Segurança:** alta.

### 8. Declaração de receitas integrais para sair de "parcial" (HI-104)

- **Resposta.** Manter a fricção. É exatamente o passo do fechamento trimestral que o escritório já faz (abrir o extrato bancário e ver rendimentos de aplicação, juros recebidos, aluguel, recuperação de despesa). Um botão "não houve receitas do art. 25, II neste trimestre", com autor e data, é um clique e deixa trilha do que foi conferido.
- **Fundamento.** Norma: Lei 9.430, art. 25, II (ganhos de capital, rendimentos de aplicações e demais receitas entram integrais) — *lido* hoje. Esquecer uma receita financeira é o erro mais comum do Presumido e gera autuação pequena e certa.
- **O que o produto faz.** Manter. Opcional: a declaração do trimestre anterior aparece como referência ("no trimestre anterior você declarou R$ X de rendimentos"), sem copiar.
- **Segurança:** alta.

### 9. Feriados locais no vencimento (HI-105)

- **Resposta.** O calendário do produto considera **só feriados nacionais por lei** (hoje: 1º/1, 21/4, 1º/5, 7/9, 12/10, 2/11, 15/11, **20/11** e 25/12). Feriado estadual ou municipal **não muda a data oficial**, mas pode impedir o pagamento na praça; o produto oferece uma tabela editável de feriados locais por UF/município da empresa, e quando o vencimento cai num deles mostra "antecipar: sem expediente bancário na praça", sem mudar a data normativa. Antecipar nunca gera multa; atrasar gera 0,33% ao dia.
- **Fundamento.** Norma: Lei 9.430, art. 5º, "último dia útil" (*lido*); Leis 662/1949 e 6.802/1980 (*lidas em 08/10*); Lei 14.759/2023, art. 1º, 20 de novembro feriado nacional (*lido* hoje; vale desde 2024); Lei 9.093/1995, arts. 1º e 2º: a data magna do Estado é feriado civil e os municípios declaram até quatro feriados religiosos, "neste incluída a Sexta-Feira da Paixão" (*lido* hoje). RFB, Perguntas e Respostas sobre contagem de prazos: no pagamento de tributos "deverá ser levado em conta o funcionamento da rede bancária local (e não o funcionamento da repartição)" (*lido* hoje em gov.br; texto atualizado até 31/12/2010). SCI Cosit 16/2013: a agenda tributária não antecipa nem prorroga por feriado não nacional (*secundário*, Econet; texto oficial não localizado). Com DARF pago por internet banking, o feriado local raramente impede o pagamento, mas a data de liquidação pode cair no dia útil seguinte (*não conferido*): daí o aviso.
- **O que o produto faz.** Mudar pouco: acrescentar 20/11 à tabela nacional (se ainda não está) e a tabela opcional de feriados locais com o aviso. A data exibida continua sendo a do calendário nacional.
- **Segurança:** média (norma clara, prática bancária não conferida).

### 10. Clientes com medida judicial contra a LC 224

- **Resposta.** Depende da carteira; não sei se há. Padrão do produto: **nenhuma medida cadastrada**, parcela da LC 224 sempre calculada e exibida; o contador cadastra a medida (processo, juízo, data, tributo, períodos, depósito) quando existir. Com liminar sem depósito, mostrar a parcela suspensa **acumulada** e o aviso de que, cassada a liminar, ela volta com juros.
- **Fundamento.** CTN, art. 151, IV e V (*não conferido* hoje, conceito estável). ADI 7936 e 7944 sem decisão até 27/08/2026 (portal do STF, *lido em 08/10*; **não reconferi hoje**).
- **O que o produto faz.** Manter HI-106 e a regra da DL-079 de excluir da dedução do 4º trimestre os trimestres com medida ativa. Reconferir o andamento das ADIs a cada etapa e guardar a data.
- **Segurança:** alta na decisão; depende de fato da carteira.

### 11. Vencimento na Sexta-feira Santa ou na terça de Carnaval

- **Resposta.** **Antecipar para o dia útil bancário anterior**, em vez de exibir a própria data com aviso. Nesses dias não há expediente bancário em nenhuma praça do país, e a regra da RFB para DARF é antecipar. Incluir também a **segunda de Carnaval** e **Corpus Christi** (quinta-feira, que já caiu em 31 de maio, data de 2ª quota do 1º trimestre), marcados como "dia sem expediente bancário (Febraban), não feriado por lei".
- **Fundamento.** Norma: Lei 9.430, art. 5º, "último dia útil" (*lido*). Sexta-feira Santa **não** é feriado nacional por lei federal: é feriado religioso municipal (Lei 9.093, art. 2º, *lido*); Carnaval e Corpus Christi são ponto facultativo federal. RFB, instruções do DARF avulso: "se for feriado, a data de vencimento do Darf deve ser antecipada para o dia útil imediatamente anterior" (*lido* hoje, gov.br). RFB, contagem de prazos: vale "o funcionamento da rede bancária local" (*lido*, 2010). Calendário de feriados bancários da Febraban (*não conferido* hoje; conhecimento estável de que bancos fecham nesses quatro dias).
- **O que o produto faz.** Mudar: tabela de "dias sem expediente bancário" com fonte e vigência (Sexta-feira Santa, segunda e terça de Carnaval, Corpus Christi, calculados pela Páscoa), tratados como não úteis para o vencimento. Trocar o aviso "calendário a conferir" por "antecipado: sem expediente bancário". O aviso fica só para feriado local da tabela do item 9.
- **Segurança:** média-alta.

### 12. Receitas informadas iguais no mesmo trimestre

- **Resposta.** Aceitar quando o contador **diferencia explicitamente**; recusar quando tudo é igual. Três mensalidades do mesmo contrato, mesmo valor e mesmo suporte, são receitas distintas e legítimas, e pedir "outro suporte" é pedir um documento que não existe. O que as distingue é a **competência (mês) ou a parcela**, e é isso que deve entrar na identidade.
- **Fundamento.** Rotina/produto. A regra do projeto é "requisição repetida não gera duplicidade silenciosa": a segunda mensalidade não é repetição, é outro fato com um atributo diferente. Hoje a identidade é (tipo, atividade, valor, suporte) e a descrição fica fora de propósito (`/home/user/DataLedger/apps/fiscal/presumido.py`, linhas 527-551).
- **O que o produto faz.** Mudar: campo "competência/parcela" (mês dentro do trimestre, ou número da parcela) na receita informada, **que entra na identidade**; sem ele, a guarda atual continua. A mensagem passa a dizer "se for outra parcela do mesmo contrato, informe a competência". Não usar a descrição livre como diferenciador.
- **Segurança:** alta.

---

## PE-84 — Recepção de NF-e

### 1. NFC-e (HI-113)

- **Resposta.** **Continuar aceitando.** Não sei se o escritório recebe NFC-e hoje, mas sei que, se há cliente comércio varejista ou posto de combustível no Presumido ou no Simples (a PE-85 pressupõe um), a venda ao consumidor sai em NFC-e e **sem ela a receita de varejo não existe no produto**. O acervo medido (618 notas, só modelo 55) é amostra, não prova de ausência.
- **Fundamento.** Rotina/produto. O MOC fixa `tpNF` 1, `idDest` 1, `finNFe` 1 e `indFinal` 1 no modelo 65 (*lido em 09/10, consulta de leiaute*), o que a torna o caso mais simples de receita.
- **O que o produto faz.** Manter. Pendência de produto, não de norma: posto emite milhares de NFC-e por mês; os limites de lote (2.000 arquivos, 50 MB) precisam ser medidos com volume real antes do primeiro cliente de varejo.
- **Segurança:** alta.

### 2. NF-e denegada (HI-109)

- **Resposta.** **Guardar marcada**, sem itens na receita e sem efeito fiscal, em vez de recusar. Dois motivos de rotina: (a) a numeração do emitente fica com um "buraco" que o contador precisa explicar na conferência de sequência (cancelada, inutilizada ou denegada); (b) denegação por 301/302/303 é **sinal de irregularidade cadastral** do cliente ou do destinatário, e o escritório precisa saber para regularizar. Recusar o arquivo apaga essa informação.
- **Fundamento.** MOC 7.0: uso da denegada como documento fiscal é "Vedado" (*lido em 09/10, consulta de leiaute*). Na EFD ICMS/IPI, o código de situação 04 (denegada) foi **descontinuado a partir de 31/12/2022** pelo Guia Prático 3.1.0 (*secundário*, portalspedbrasil; o Guia em sped.rfb.gov.br devolveu 503 hoje): a escrituração fiscal já não a exige, então a decisão é só de produto.
- **O que o produto faz.** Mudar HI-109, com prioridade baixa: gravar com situação "denegada — sem efeito fiscal", visível na recepção e na futura conferência de sequência, excluída de receita, totais e escrituração. Até a conferência de sequência existir, a recusa nomeada de hoje não causa dano.
- **Segurança:** média.

### 3. Transferência entre estabelecimentos da mesma empresa (HI-111)

- **Resposta.** Para **receita**, a marca atual basta (natureza 11, fora da base). Para o **ICMS**, que é por estabelecimento, os dois papéis vão ser necessários: o estabelecimento de origem registra a saída e o de destino a entrada com o crédito. Decisão: manter um vínculo, mas **gravar desde já qual `Estabelecimento` é o emitente e qual é o destinatário**, para não reabrir o XML quando a apuração do ICMS chegar.
- **Fundamento.** Norma: LC 87, art. 11, § 3º, II, "é autônomo cada estabelecimento do mesmo titular" (*lido* hoje); art. 12, § 4º (red. LC 204/2023), não se considera ocorrido o fato gerador na saída para estabelecimento do mesmo titular (*lido* hoje, trecho inicial); transferência de crédito regulada pelo Convênio ICMS 109/2024 (*não conferido*). A EFD ICMS/IPI é entregue por inscrição estadual (*não conferido* hoje, conceito estável).
- **O que o produto faz.** Mudar pouco: dois campos de estabelecimento no vínculo (origem e destino). A tela de conferência mostra "transferência: estabelecimento X → Y". A unicidade `(documento, empresa)` pode ficar.
- **Segurança:** média-alta.

### 4. `vNF` a partir de 2027 (NT 2026.008)

- **Resposta.** Nada novo publicado. Conferi hoje os informes do Portal da NF-e: o último é o de 05/10/2026 (postergação das NTs 2025.002 v1.52, 2026.007 v1.10 e **2026.008 v1.00 para 26/10 em homologação e 16/11 em produção**); nenhum texto oficial sobre o comportamento de `vNF` em 2027, e nenhum pacote de esquemas posterior ao PL 010f. Li a NT 2026.008 inteira: ela diz que "a partir de 2027, os valores de IBS, CBS e IS compõem o Valor Total Bruto" (`vProd`), "exceto nas notas de importação"; que esses valores "não deverão ser adicionados novamente" em `vNFTot`; e que o `vItem` passa a somar "vProd (contém vIBS, vCBS e vIS)" com a exceção "em 2025 e 2026 não somar". **Não há uma linha sobre a regra W16 (`vNF`).** Minha leitura: como W16 soma `vProd`, o `vNF` de 2027 passará a conter IBS/CBS por arrasto, e `vNFTot` tende a igualar `vNF`; mas isso é inferência, não norma.
- **Fundamento.** NT 2026.008 v1.00, introdução e regras VB01-10/VB01-20 (*lido* hoje); MOC 7.0, W16-10 (*lido* hoje); informes do Portal (*lido* hoje). Ato Conjunto RFB/CGIBS 8/2026, de 01/10/2026 (*não lido*). Regra de receita bruta de 2027: IBS e CBS são por fora e destacados, o que os aproxima do IPI no DL 1.598, art. 12, § 4º (*lido em 09/10, consulta da escrituração*), mas sem texto expresso para IRPJ/Simples (*não conferido*); Res. CGSN 190/2026 (*não lida*).
- **O que o produto faz até lá.** (1) Nada muda para competências de 2026. (2) O leitor passa a **guardar** `vUnComLiq`, `vProdLiq` e `vProdLiqTot` quando presentes (a partir de 16/11/2026 já podem aparecer), sem interpretar. (3) Para nota com `dhEmi` em 2027 ou posterior, **bloquear a efetivação da receita com motivo nomeado** ("regra de receita de 2027 pendente: NT 2026.008 e `vNF`"), deixando o mês parcial, até a Receita publicar a regra ou o Fred decidir. A primeira competência de 2027 só vence em fevereiro de 2027; há tempo. (4) Reconferir o Portal em cada etapa e registrar a data.
- **Segurança:** alta na decisão de bloquear; o fato "nada publicado" vale para hoje.

---

## PE-85 — Escrituração das NF-e

### 1. Combustíveis: posto ou distribuidor; padrão e indicação

- **Resposta.** A norma não olha o tipo de empresa, olha **a operação**: 1,6% exige (i) combustível derivado de petróleo, álcool carburante ou gás natural, (ii) **revenda** (não venda do produtor) e (iii) destinação **a consumo** pelo adquirente, "e não a serem por estes alienados a terceiros". Então: **posto** = 1,6% nas vendas a consumidor; **distribuidora** = 8% no que vende a postos (revenda para recomercialização) e 1,6% no que vende a consumidor final (frotas, indústria, TRR que consome). A CSLL é 12% nos dois casos. Padrão do produto: a atividade de presunção vem da **natureza por item**, com duas naturezas de combustível ("revenda para consumo — 1,6%" e "revenda para revenda — 8%"); a empresa tem um padrão (posto → consumo), e o contador muda por natureza ou por item. Como não sei qual é o cliente, o padrão para CNAE de posto é 1,6% e para distribuidora é "por item, sem padrão".
- **Fundamento.** Norma: Lei 9.249, art. 15, § 1º, I (*lido* hoje); SC Cosit 25/2023, itens 16 a 23 (*cópia* íntegra, PDF no IBET): os três requisitos acima, "independentemente da condição do consumidor (residencial, industrial, comercial)" e da forma de entrega; a "revenda com a finalidade de subsequente comercialização" fica fora (item 8, acolhido no item 21). Sugestão pelo CFOP: x.656 e x.667 (venda a consumidor final) → 1,6%; x.655 (a comerciante) → 8%; x.651 a x.653 (produção própria) → 8% por não ser revenda — descrições dos CFOP *não conferidas* hoje (CONFAZ inacessível), só sugestão. PIS/Cofins do posto a alíquota zero na revenda (Lei 9.718, art. 4º, *não conferido* hoje) é outra conta, fora deste item.
- **O que o produto faz.** Mudar: dividir a natureza 6 em duas; a confirmação explícita "revenda, para consumo" (HI-118/consulta item 10) passa a ser a escolha entre as duas. Padrão por empresa configurável.
- **Segurança:** alta na norma; média na sugestão por CFOP até a tabela ser lida.

### 2. Como chega a devolução de venda e tratamento padrão

- **Resposta.** Chega de **duas formas**, e o produto aceita as duas como natureza 9: (a) cliente contribuinte emite NF-e de devolução (`finNFe` 4, `tpNF` 1 do emitente; a empresa é destinatária); (b) cliente não contribuinte ou consumidor devolve e **a própria empresa emite nota de entrada** (`tpNF` 0, `finNFe` 4, CFOP 1.202/2.202 ou 1.949/2.949). No varejo (b) é a regra; no atacado (a) é a regra. Padrão: dedução **no mês da devolução** (Simples) e **no trimestre da devolução** (Presumido), sem exigir vínculo com a nota de origem; quando a devolução excede a receita do mês, o saldo passa aos meses seguintes.
- **Fundamento.** Norma: Res. CGSN 140, art. 17, I e II — "deve ser deduzido da receita bruta total, no período de apuração do mês da devolução", e saldo "nos meses subsequentes" (*cópia*, lida hoje); Lei 9.430, art. 25, I, "deduzida das devoluções e vendas canceladas" (*lido* hoje); NT 2026.009 (*lido* hoje): a regra I08-140 aceita CFOP 1.949 e 2.949 "na devolução de venda" com `finNFe` 4, confirmando a forma (b); VC02-14 da NT 2025.002 passa a exigir `DFeReferenciado` por item a partir de 16/11/2026 (*lido em 09/10*), o que permitirá ligar à origem depois.
- **O que o produto faz.** Manter HI-117 e HI-121 como estão (as duas formas já cabem no corte). Confirmar nos testes a forma (b) com CFOP 1.949/2.949. Ligação à nota de origem fica para quando `DFeReferenciado` circular (BL-685).
- **Segurança:** alta.

### 3. Quando integrar a receita de NF-e ao Presumido e criar o pré-DAS de comércio

- **Resposta.** **Presumido primeiro, agora**: o esforço é pequeno (a receita entra pela atividade de presunção da natureza, pelo mês de `dhEmi`, deduzidas devoluções), e enquanto não entra **todo cliente do Presumido com NF-e fica "parcial" o ano inteiro**, inclusive o posto. **Pré-DAS de comércio em seguida**, mas não sem a segregação mínima: para posto e comércio em geral, calcular DAS sem separar ST (CSOSN 500), monofásico (natureza 6 confirmada) e exportação **superestima o DAS**; a segregação por natureza confirmada entra no primeiro corte, e a tabela de NCM monofásico fica como sugestão posterior.
- **Fundamento.** Rotina/produto. Normas já lidas: Lei 9.430, art. 25, I (*lido*); LC 123, art. 18, §§ 4º e 4º-A e Res. 140, arts. 25 e 28 (*lido/cópia em 09/10*).
- **O que o produto faz.** Mudar: (1) DL curta "receita de NF-e no Presumido" encerrando a parte do HI-122 que diz "fica parcial"; (2) pré-DAS de Anexos I e II com segregação por natureza (ST substituído, substituto com `vST` fora, monofásico, exportação) e recusa nomeada para benefício estadual de ICMS até a lei do TO ser lida. Não localizei "DL-082" em `docs/`; se ela existe fora do repositório, é esta.
- **Segurança:** alta.

### 4. Hipóteses HI-117 a HI-124

| Hipótese | Posição | Ajuste |
| --- | --- | --- |
| HI-117 (corte: saídas próprias + devolução recebida) | **Validada** | Explicitar que `tpNF` 0 com `finNFe` 4 (nota própria de entrada) é devolução de venda, não compra (item 2) |
| HI-118 (natureza por item, catálogo de 14) | **Validada** | Dividir a natureza 6 em "para consumo" e "para revenda" (item 1) |
| HI-119 (receita por item = `vProd − vDesc + vFrete + vSeg + vOutro`; `vST`, `vIPI`, `vII` fora; conferência W16) | **Validada com complemento** | Incluir `− vICMSDeson` quando `indDeduzDeson` = 1 (item 5b); itens `indTot` 0 pela regra do MOC (item 5a). Frete, seguro e outras despesas cobradas na nota compõem o "produto da venda" (DL 1.598, art. 12, I e IV, *lido*): continua sem texto expresso, hipótese mantida |
| HI-120 (CSOSN 500 substituído; 201/202/203 substituto; `idDest` 3 exportação; monofásico pelo NCM) | **Validada** | Acrescentar CST 60 (CRT 3) como substituído, já previsto no catálogo |
| HI-121 (devolução deduz no mês; cancelamento no período de origem) | **Validada** | Nenhum; o art. 17 da Res. 140 foi lido hoje em cópia e diz exatamente isso |
| HI-122 (pré-DAS recusa e Presumido parcial enquanto não integra) | **Validada como transição** | Substituir pelo item 3 |
| HI-123 (IBS/CBS de 2026 fora da receita; só avisos) | **Validada** | Para 2027, item 4 da PE-84 |
| HI-124 (5.929 não é receita nova; bonificação só fora quando incondicional) | **Validada** | No Presumido a exclusão da bonificação é prática sem texto expresso (*não conferido*); manter "só com atestado do contador" |

### 5. Os dois bloqueios conservadores

**(a) Item fora do total (`indTot` 0) com desconto, frete, seguro ou outras despesas.**

- **Resposta.** **Aceitar, com a fórmula do próprio MOC.** Receita bruta da nota = o que foi cobrado do adquirente. Pelas regras do autorizador, o `vProd` do item com `indTot` 0 **não** entra no total (W07-10 soma "somente os valores dos itens com a TAG indTot = 1"), mas **seus** desconto, frete, seguro e outras despesas **entram** (W08-10, W09-10, W10-10 e W15-10 somam todos os itens, sem filtro). Logo: receita do item com `indTot` 1 = `vProd − vDesc + vFrete + vSeg + vOutro`; receita do item com `indTot` 0 = `−vDesc + vFrete + vSeg + vOutro` (o `vProd` não foi cobrado), e a natureza desse item fica como "fora da receita" (bonificação, brinde, demonstração) com aviso. A conferência W16 fecha com tolerância zero. Só modelo 55: a NFC-e rejeita `indTot` 0 (I17b-10).
- **Fundamento.** Norma de receita: LC 123, art. 3º, § 1º, "produto da venda de bens" (*lido*); DL 1.598, art. 12, I (*lido*); Lei 9.430, art. 25, I (*lido*). Regras: MOC 7.0, Anexo I, I17b, I17b-10, W07-10 a W16-10 (*lido* hoje). O valor não cobrado não é "produto da venda"; a nota foi autorizada sob essas regras, então o produto pode confiar nelas.
- **O que o produto faz.** Mudar: trocar o bloqueio pela fórmula acima e um aviso na memória ("item n fora do total: `vProd` R$ X não compõe a receita"). Teste com o gerador W16 do auditor.
- **Segurança:** média-alta.

**(b) ICMS desonerado deduzido do total (`indDeduzDeson` 1).**

- **Resposta.** **Aceitar, deduzindo.** Quando o emitente marca `indDeduzDeson` 1, o preço cobrado é `vProd − vICMSDeson`: o adquirente **não pagou** o imposto desonerado, e a redução consta da própria nota, sem condição futura. Para a receita bruta isso é, em substância, **desconto incondicional**, e as três normas o excluem. Receita por item = `vProd − vDesc − vICMSDeson (se indDeduzDeson = 1) + vFrete + vSeg + vOutro`; com `indDeduzDeson` 0 ou ausente nada se deduz (o adquirente pagou o valor cheio). A conferência W16 já subtrai `vICMSDeson` e tolera a nota que não subtraiu (Exceção 3), por isso o produto segue o indicador, não a regra cega.
- **Fundamento.** Norma: LC 123, art. 3º, § 1º, "não incluídas as vendas canceladas e os descontos incondicionais concedidos" (*lido*); DL 1.598, art. 12, § 1º, II (*lido*); Lei 9.430, art. 25, I, "deduzida [...] dos descontos incondicionais concedidos" (*lido*). MOC 7.0, W16-10, "(−) vICMSDeson (id:W04a)" e Exceção 3 (*lido* hoje). A caracterização como desconto incondicional é **leitura minha**, sem solução de consulta localizada (*não conferido*); o resultado numérico é o mesmo da leitura "receita = valor cobrado". Risco se eu estiver errado: presunção × alíquota sobre o ICMS desonerado (no comércio, 8% × 15% = 1,2% do ICMS), contra a alternativa de deixar 100% da receita do mês fora por bloqueio.
- **O que o produto faz.** Mudar: aplicar a fórmula, mostrar na memória a linha "ICMS desonerado deduzido do total: R$ X" e manter o aviso. Fecha o item (1) do BL-685.
- **Segurança:** média-alta.

---

## Tabela-resumo: subitem × decisão × muda o código?

| Pendência | Subitem | Decisão | Muda o código? |
| --- | --- | --- | --- |
| PE-83 | 1. Quem classifica | Contador, no cadastro, na entrada | Não (só pendência de cadastro na lista do mês) |
| PE-83 | 2. Várias atividades | Por item na NF-e; rateio manual em valores no resto | Não |
| PE-83 | 3. CSLL 1/4,65 | Aceitar como estimativa + teste de coerência (4,65% ou 1% da base) | Sim, pequeno |
| PE-83 | 4. Competência da retenção | Trimestre da receita; retenção tardia reabre "a retificar"; saldo → PER/DCOMP | Confirmar comportamento; mudança pequena se faltar |
| PE-83 | 5. Arredondamento por linha | Manter | Não |
| PE-83 | 6. Quotas | Manter cálculo; parâmetro por empresa "forma de recolhimento padrão" | Sim, pequeno |
| PE-83 | 7. Limite por CNPJ raiz | Confirmado; corrigir a fonte (não é a Lei 9.779) | Não (só documentação) |
| PE-83 | 8. Declaração de receitas integrais | Manter | Não |
| PE-83 | 9. Feriados locais | Só nacionais na data; tabela local opcional com aviso de antecipar; 20/11 na tabela | Sim, pequeno |
| PE-83 | 10. Medida judicial | Padrão sem medida; manter HI-106 | Não |
| PE-83 | 11. Sexta-feira Santa e Carnaval | **Antecipar** (mais segunda de Carnaval e Corpus Christi) como dias sem expediente bancário | Sim |
| PE-83 | 12. Receitas iguais | Aceitar com campo competência/parcela na identidade; sem ele, recusar | Sim |
| PE-84 | 1. NFC-e | Continuar aceitando | Não (medir volume) |
| PE-84 | 2. Denegada | Guardar marcada, sem efeito fiscal | Sim, prioridade baixa |
| PE-84 | 3. Transferência | Um vínculo, com estabelecimentos de origem e destino gravados | Sim, pequeno |
| PE-84 | 4. `vNF` 2027 | Nada publicado; guardar campos novos; bloquear receita de 2027 com motivo nomeado | Sim, pequeno |
| PE-85 | 1. Combustíveis | Por operação: consumo 1,6%, revenda 8%; duas naturezas; padrão por empresa | Sim |
| PE-85 | 2. Devolução | Duas formas aceitas; dedução no mês/trimestre da devolução | Não (testar 1.949/2.949) |
| PE-85 | 3. Integração | Presumido já; pré-DAS de comércio com segregação por natureza em seguida | Sim (duas DLs) |
| PE-85 | 4. HI-117 a HI-124 | Todas validadas; ajustes em HI-118 e HI-119 | Via itens 1 e 5 |
| PE-85 | 5a. `indTot` 0 | Aceitar pela regra do MOC (vProd fora, despesas dentro) | Sim |
| PE-85 | 5b. `indDeduzDeson` 1 | Aceitar deduzindo `vICMSDeson` como desconto incondicional | Sim |

## O que continua dependendo de fato da carteira do Fred

1. **Se há cliente com medida judicial** contra a LC 224 (PE-83.10) e se há depósito; o padrão é "nenhuma".
2. **Se o escritório recebe NFC-e** hoje e em que volume mensal (PE-84.1): a aceitação não depende disso, o dimensionamento do lote depende.
3. **Qual é o cliente de combustíveis** (posto, distribuidora ou TRR) e para quem vende (PE-85.1): decide o padrão da empresa; a regra por operação vale para qualquer um.
4. **Como as devoluções chegam** na carteira real e se as 7 NF-e de entrada do acervo são notas próprias de devolução (PE-85.2): muda só a prioridade de teste.
5. **Se algum cliente usa quotas** (PE-83.6): decide o valor padrão do parâmetro, não a existência da função.
6. **Se o escritório já antecipou DARF por feriado municipal** alguma vez (PE-83.9): decide se a tabela de feriados locais nasce preenchida para Palmas/TO.
7. **Se há cliente do Presumido com NF-e já em 2026** (PE-85.3): decide a urgência da integração, que eu coloquei como "agora".

**O que não consegui determinar hoje:** texto oficial da SCI Cosit 16/2013; lista oficial de feriados bancários (Febraban/BCB); Guia Prático da EFD ICMS/IPI vigente (503); descrições individuais dos CFOP de combustível e de devolução (CONFAZ); regra de receita bruta de 2027 (LC 214 e Res. CGSN 190/2026 não lidas); solução de consulta sobre retenção em trimestre posterior ao da receita; andamento das ADIs 7936/7944 depois de 27/08/2026.

Fontes oficiais abertas hoje:
- https://www.planalto.gov.br/ccivil_03/leis/l9430.htm
- https://www.planalto.gov.br/ccivil_03/decreto-lei/del1598.htm
- https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
- https://www.planalto.gov.br/ccivil_03/leis/l9249.htm
- https://www.planalto.gov.br/ccivil_03/leis/l9779.htm
- https://www.planalto.gov.br/ccivil_03/leis/l9093.htm
- https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14759.htm
- https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833.htm
- https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm
- https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false (informes até 05/10/2026)
- https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/DCTFWeb/notas-orientativas/arquivos/instrucoes-para-emissao-de-darf-avulso.pdf
- https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/dipj/respostas-2011/capituloii-contagemdeprazos2011.pdf
- Cópias: https://www.ibet.com.br/wp-content/uploads/2023/01/SC_Cosit_n_25-2023.pdf (SC Cosit 25/2023); https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf (Res. CGSN 140)
- Secundários: https://blog.econeteditora.com.br/?p=4738 (SCI Cosit 16/2013); https://portalspedbrasil.com.br/?p=18048 (COD_SIT 04/05 descontinuados)
- Arquivos locais lidos: NT 2026.008 e NT 2026.009 em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/nfe/nt_txt/`; MOC 7.0 Anexo I no mesmo diretório; leis convertidas em `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/leis/`
