# Consulta ao contador-senior sobre faturamento, RBT12 e pré-DAS — 08/10/2026

Segunda consulta do `arquiteto-senior` ao `contador-senior` (skill
`anthropic-skills:contador-senior`, em Fable), por ordem do Fred (RC-164),
antes de planejar a etapa de faturamento e RBT12 do Simples. Registro
integral.

⚠️ **Tudo abaixo é HIPÓTESE (HI-54)** até o Fred validar. As hipóteses que
viraram regra de produto estão em [requisitos.md](../requisitos.md) (HI-64 em
diante). A seção 7 **corrige três artigos** citados na
[primeira consulta](2026-10-08-contador-senior-fiscal.md), item 9.

**Legislação validada até:** 08/10/2026 · **Competências em análise:** 10/2026 a 03/2027 (com a virada da Res. CGSN 190/2026 em 01/01/2027) · **Grau de segurança geral:** alto nos itens 2, 4, 6, 7 e 8 (textos oficiais lidos); médio no 1 (prática de sistema por fonte secundária) e no 3 (texto da Res. 190/2026 não aberto).

Tudo abaixo é **HIPÓTESE para validação do Fred**. Marcas: *lido* = li o texto oficial (PDF do próprio órgão ou cópia íntegra), *cópia* = cópia em site terceiro, *secundário* = notícia/informativo, *não conferido* = conhecimento meu.

O que consegui abrir hoje e sustenta quase tudo: **Resolução CGSN 140/2018 consolidada com anotações até a Res. 190/2026** (PDF íntegro, *lido*), **Manual do PGDAS-D e DEFIS, versão de 17/06/2025** (PDF oficial da RFB, 139 páginas, *lido*), **Portaria CGSN 54/2025** (*cópia*), **SC Cosit 102/2026** (PDF, *lido*), LC 123/2006 (*cópia* normaslegais; Planalto deu 503 de novo). Não abri: texto da Res. CGSN 190/2026 (só informativos), Perguntas e Respostas do Simples (página oficial "não encontrada"), central de ajuda da Domínio (403; usei o resumo que o buscador devolveu).

---

## 1. Origem da receita: NFS-e escriturada + "receita informada"

**Resposta curta.** Sim, e não há alternativa: a receita bruta do Simples é a **receita total da empresa** (bens, serviços, conta alheia e demais receitas da atividade), não "a soma das notas". Um sistema que só tem NFS-e nacional **precisa** de um lançamento de receita informada para fechar o mês e os 12 meses anteriores — é exatamente o que o PGDAS-D faz na primeira apuração ("receitas anteriores à opção") e o que o Domínio faz na rotina "Receita Bruta Acumulada". A salvaguarda é tratar o mês como **"receita confirmada completa"** por ato do contador, e só apurar RBT12/pré-DAS sobre meses confirmados.

**NORMA.**
- Receita bruta: "o produto da venda de bens e serviços nas operações de conta própria, o preço dos serviços prestados, o resultado nas operações em conta alheia e as demais receitas da atividade ou objeto principal", excluídas vendas canceladas e descontos incondicionais — Res. CGSN 140, art. 2º, II (red. Res. 183/2025, *lido*); LC 123, art. 3º, § 1º (*cópia*). § 4º do art. 2º inclui custo de financiamento em vendas a prazo, gorjetas, royalties/aluguéis/cessão de uso e patrocínio; § 5º exclui venda de imobilizado, juros/multas de mora, bonificações e amostras, multa rescisória (parte não executada), repasse ao profissional-parceiro e rendimentos de aplicações (*lido*). Atenção: a Res. 190/2026 anota "modificação prevista para 01/01/2027" nos §§ 4º e 5º — o informativo FIEMG diz que juros/multas/encargos passam a compor e aplicações saem (*secundário*).
- Reconhecimento: "quando do faturamento, da entrega do bem ou do direito ou à proporção em que os serviços forem efetivamente prestados, o que primeiro ocorrer" — art. 2º, § 8º (*lido*). Ou seja, receita sem documento também é receita.
- RBT12 = receita bruta **total** acumulada nos 12 meses anteriores ao PA — art. 22, § 1º; alíquota pela fórmula do art. 21, II (*lido*).
- Devolução de mercadoria: deduz no PA da devolução (art. 17); **cancelamento de documento em período posterior deduz no PA da tributação originária** (art. 18, *lido*) — isso bate com a pendência "nota cancelada depois de escriturada" da DL-072: o efeito fiscal é retificar o mês original, não abater o mês corrente.
- O que o contador informa no PGDAS-D "tem caráter declaratório e constitui confissão de dívida" — LC 123, art. 18, § 15-A (*cópia*). O dado digitado é o que vale; por isso a trilha de quem informou o quê importa.

**PRÁTICA (Manual do PGDAS-D, *lido*, e Domínio, *secundário*).**
- PGDAS-D, item 6.3: na **primeira apuração** o programa abre o "quadro de receitas anteriores" pedindo a receita de cada um dos 12 PA anteriores, separada em mercado interno e externo; o quadro não aparece para quem já era optante nos 12 PA anteriores nem quando o mês de início de atividade coincide com o PA. Há a função "Receitas Brutas Anteriores" para consultar e retificar. O manual alerta que informar R$ 0,00 por engano zera RBT12/RBA/RBAA "com reflexos... na determinação das alíquotas dos períodos posteriores" (item 5.1).
- Domínio (central de ajuda, solução 65, via resumo de busca — página deu 403): em *Controle > Parâmetros* informa-se "Início efetivo das atividades" (data de abertura na RFB); em *Movimentos > Outros > Simples Nacional > Receita Bruta Acumulada* informa-se a data de início do cálculo no sistema e o programa lista os até 12 meses anteriores para digitação manual, "Importar dos Lançamentos" (troca de regime) ou "Importar do PGDAS" (extrato, com certificado). Orientação explícita: em troca de escritório/sistema, preencher **conforme o PGDAS**, senão há diferença Domínio × PGDAS. Isso só se faz **antes do primeiro cálculo**; depois o sistema acumula sozinho. Empresa sem histórico → RBT12 proporcional.
- Rotina real do escritório: a receita do mês do PGDAS-D sai do "resumo de faturamento" (notas de serviço + cupons/NF-e + "outras receitas" que o cliente manda por planilha). Receita de mercadoria de cliente misto é o caso mais comum de receita fora da NFS-e.

**RECOMENDAÇÃO.**
1. Entidade **"Receita informada"** por empresa, competência e **mercado (interno/externo)**, com `origem` fechada: histórico pré-sistema (meses anteriores ao uso); venda de mercadoria (NF-e/NFC-e ainda não escrituradas); serviço com documento de município não integrado; outras receitas do art. 2º, § 4º; ajuste/retificação. Campos obrigatórios: motivo, documento de suporte (ex.: "extrato PGDAS-D PA 03/2026"), autor, trilha. Imutável depois de confirmada (estorno com motivo, como na DL-072).
2. **Receita do mês = Σ escriturações efetivadas (por natureza e mercado) + Σ receitas informadas**, com a composição visível ("82% documento, 18% informado").
3. **Confirmação mensal explícita** ("receita de MM/AAAA completa"), com permissão igual à de escriturar. O RBT12 só é calculado quando os 12 meses anteriores (ou todos desde a abertura, no início de atividade) estão confirmados; falta algum → **bloqueia** o pré-DAS e lista os meses pendentes. Receita informada de origem "histórico" só é aceita em meses anteriores à data de início de uso do sistema.
4. **Importador do extrato do PGDAS-D** (PDF/arquivo do Portal) para carregar o histórico de 12 meses e para a conciliação mensal "nosso cálculo × extrato" — é o que o Domínio faz e o que o Fred vai conferir de qualquer jeito.
5. Anti-duplicidade: alerta (nível "justificativa") quando há receita informada de origem "serviço" num mês/município que já tem NFS-e escriturada; alerta quando a receita informada é zero num mês com notas.
6. Cancelamento posterior (Res. 140, art. 18): ao estornar a escrituração, marcar o mês original como "a retificar" e reabrir a confirmação daquele mês — nunca abater silenciosamente o mês corrente.

**Confiança:** alta na norma; média na prática de sistema (Domínio por fonte secundária).

---

## 2. Data de início de atividade

**Resposta curta.** É a **data de abertura constante do CNPJ** — nem a data da opção pelo Simples, nem outra data. Para a proporcionalização (art. 22, §§ 2º-3º) e para o limite proporcional (art. 3º da Res. 140 / LC 123, art. 3º, § 2º) conta-se da abertura do CNPJ, fração de mês como mês completo. Empresa que já existia: se a abertura foi **no ano imediatamente anterior ao da opção**, usa a média × 12 até completar 12 meses de atividade e a regra geral do 13º mês em diante (§ 4º); se a abertura foi há mais de um ano, é regra geral desde o primeiro PA, com os 12 meses anteriores informados (inclusive meses em que era Presumido/Real).

**NORMA (Res. CGSN 140, *lido*).**
- Art. 2º, IV: "empresa em início de atividade aquela que se encontra no período de 60 (sessenta) dias a partir da data de abertura constante do CNPJ"; **V: "data de início de atividade a data de abertura constante do CNPJ"**. Manual do PGDAS-D, item 8.3, repete literalmente, citando o art. 2º, V (*lido*).
- Art. 22, § 2º: "início de atividade **no próprio ano-calendário da opção**" → 1º mês: receita do mês × 12; § 3º: 11 meses seguintes, média dos meses anteriores × 12; **§ 4º: início "em ano-calendário imediatamente anterior ao da opção"** → regra do § 3º até completar 12 meses e regra geral (§ 1º) "a partir do décimo terceiro mês de atividade". O manual exemplifica (empresa aberta em 02/2018; mês sem receita entra como zero).
- Art. 3º: no ano de início, cada limite = R$ 400.000,00 × meses "entre o início de atividade e o final do respectivo ano-calendário, considerada a fração de mês como mês completo"; § 3º: início no ano anterior ao da opção → para **opção** vale o proporcional, para **permanência** vale o cheio.
- Art. 26, § 4º: folha para fator r com menos de 13 meses de atividade segue os mesmos critérios do art. 22. Manual 8.2.1: entre a abertura e o PA inferior a 13 meses → Σ FS / Σ receitas desde o mês da abertura até o mês anterior ao PA.
- Res. 190/2026 (vigência 01/01/2027) redefine como "data de inscrição no CNPJ" e vincula "início de atividade" à inscrição (FIEMG, *secundário*) — na prática é a mesma data; só muda o rótulo.

**PRÁTICA.** O erro de escritório é usar a data da **opção** como início (empresa aberta em outubro que opta em janeiro seguinte): o PGDAS-D aplica o § 4º e a conta "manual" do contador diverge. O Domínio pede a data de abertura na RFB em parâmetro próprio justamente por isso.

**RECOMENDAÇÃO.** Cadastro da empresa ganha dois campos distintos, ambos obrigatórios para apurar: **data de abertura no CNPJ** (importável da consulta CNPJ/cartão; validar contra a data da NFS-e mais antiga) e **histórico de regime com vigência** (Simples: data de efeitos da opção; competência/caixa por ano). O motor decide: abertura no ano do PA → §§ 2º-3º; abertura no ano anterior ao da opção → § 4º; demais → § 1º. Sem data de abertura: bloqueia com mensagem nomeada.

**Confiança:** alta.

---

## 3. Regime de caixa

**Resposta curta.** Recusar o **pré-DAS** (base mensal) e explicar; **não** recusar RBT12, limites, sublimites e fator r, que mesmo no caixa são pela competência. Não vale construir módulo de caixa: a opção acaba no PA 12/2026 (LC 214/2025 alterou o art. 18, § 3º da LC 123; Res. CGSN 190/2026 revoga os arts. 16 § 1º, 19, 20, 77 e 78 da Res. 140 a partir de 01/01/2027).

**NORMA.**
- Res. 140, art. 16: base = "receita bruta total mensal auferida (Regime de Competência) ou recebida (Regime de Caixa), conforme opção"; § 1º: irretratável no ano (*lido*).
- Art. 19: opção registrada no PGDAS-D na apuração de novembro (já optante) ou do mês de início dos efeitos; **parágrafo único: o caixa "servirá exclusivamente para a apuração da base de cálculo mensal", e a competência vale "para as demais finalidades, especialmente, para determinação dos limites e sublimites e da alíquota"** (*lido*).
- Art. 20: parcela a prazo não vencida entra na base até o último mês do ano seguinte (I); receita auferida e não recebida entra na base no encerramento, no **último mês de vigência do caixa ao retornar à competência** (II, "b") e no mês anterior à exclusão (*lido*). Esse inciso II, "b" é o que vai pegar os optantes do caixa em **12/2026**, salvo regra de transição na Res. 190 — **não li o texto; conferir**.
- Art. 77: registro de valores a receber (Anexo IX) por documento: nº e data, valor, parcelas e vencimentos, data e valor recebidos, saldo, créditos não cobráveis; art. 78: descumprimento → opção desconsiderada de ofício e recálculo pela competência com acréscimos (*lido*).
- **SC Cosit 102/2026** (29/06/2026, *lido*): confirma que o caixa "restringe-se à apuração da base de cálculo mensal", que RBT12, alíquota e fator r continuam pela receita auferida, que **todos** os valores a prazo (não só inadimplidos) vão ao registro, que o prazo de escriturar é o vencimento do DAS do PA, e que a possibilidade "se esgotará no período de apuração (PA) dezembro de 2026" (LC 214/2025, art. 517 c/c art. 544, III).
- Res. CGSN 190/2026 (datada de 04/08/2026 nas anotações da Res. 140; publicada no DOU em 10 ou 11/08/2026 — fontes divergem): revoga art. 16 § 1º, arts. 19 e 20 e a subseção dos arts. 77-78, efeitos em 01/01/2027 (Agência Gov/RFB, 14/08/2026, *lido*; FIEMG IE 52, *lido*). Texto oficial não aberto.
- Manual do PGDAS-D, 5.1 (*lido*): o optante pelo caixa **informa os dois valores** (competência e caixa, cada um separado em interno/externo); a soma das receitas segregadas por atividade deve bater com a receita pelo caixa.

**PRÁTICA.** Quem tem cliente no caixa controla recebimentos em planilha ou no financeiro e digita os dois números no PGDAS-D; o erro clássico é zerar a competência.

**RECOMENDAÇÃO.** (1) Regime de reconhecimento por **ano-calendário** no histórico de regime (competência/caixa; a partir de 2027 só competência, travado). (2) Para 2026 com caixa: RBT12, limites e fator r rodam normalmente; o pré-DAS **bloqueia** com a mensagem "empresa optante pelo regime de caixa em 2026: a base mensal é a receita recebida (Res. CGSN 140, arts. 16 e 77); o sistema não tem contas a receber e não aproxima pela emissão" — e oferece o campo "receita recebida informada" (interno/externo) só se o Fred quiser; nunca inferir. (3) Avisar na competência 12/2026 dessas empresas: "receita auferida e não recebida integra a base deste mês (art. 20, II, 'b') — conferir regra de transição da Res. 190/2026".

**Confiança:** alta na regra vigente; média na transição (texto da Res. 190 não lido).

---

## 4. Exportação de serviços

**Resposta curta.** Mercado interno e exportação são **duas bases e dois RBT12 distintos**: o PGDAS-D calcula uma alíquota efetiva com o RBT12 interno para a receita interna e **outra** com o RBT12 de exportação para a receita exportada (não soma). O limite de R$ 4,8 mi é **um para cada** (e o sublimite de R$ 3,6 mi também, e o proporcional de R$ 400 mil × meses também). Só o **fator r** usa a receita conjunta. Sobre a receita de exportação, desconsideram-se PIS, Cofins, IPI, ICMS e **ISS**. Portanto a natureza "sem incidência de ISS" do produto **mistura três tratamentos diferentes** e precisa ser desdobrada; "exportação de serviço" tem de ser natureza própria.

**NORMA.**
- LC 123, art. 3º, § 14 (limite adicional de exportação) e **§ 15**: receitas do mercado interno e de exportação "serão consideradas separadamente" para alíquota (art. 18, § 1º), base (art. 18, § 3º) e majorações (*cópia*). Res. 140, art. 2º, § 1º: até R$ 4,8 mi no mercado interno "e, adicionalmente", exportação "desde que as receitas de exportação também não excedam R$ 4.800.000,00"; art. 3º: "cada um dos limites" × R$ 400 mil/mês; art. 9º, § 1º: sublimite de R$ 3,6 mi interno "e, adicionalmente, igual sublimite para exportação"; art. 16, § 3º, II: "separadamente, em bases distintas"; **art. 23: separadas "para fins de determinação da alíquota"** (*lido*).
- Manual do PGDAS-D (*lido*): siglas RBT12 int / RBT12 ext / RBA int / RBA ext / RPA int / RPA ext; exemplo 6 calcula "Alíquota efetiva int" com RBT12 Int = 2.000.000 (5ª faixa) e "Alíquota efetiva ext" com RBT12 Ext = 1.000.000 (4ª faixa), e soma os dois valores devidos; item 8.4: sublimite observado separadamente para cada mercado, cada um proporcionalizado no ano de início.
- Fator r: RBT12r "considerando conjuntamente as receitas brutas auferidas no mercado interno e aquelas decorrentes da exportação" — art. 26, II e § 5º, V (*lido*).
- Receita de exportação segregada; "serão desconsiderados... os percentuais relativos à Cofins, à Contribuição para o PIS/Pasep, ao IPI, ao ICMS e ao ISS" — art. 25, § 3º; LC 123, art. 18, § 14 (*lido*/*cópia*). Definição: "prestação de serviços para pessoa física ou jurídica residente ou domiciliada no exterior, cujo pagamento represente ingresso de divisas, exceto quanto aos serviços desenvolvidos no Brasil cujo resultado aqui se verifique" — art. 25, § 4º (= LC 116, art. 2º, parágrafo único); § 4º-A: independe do ingresso se os recursos ficam no exterior (Lei 11.371/2006) (*lido*).
- Imunidade/isenção/redução de ISS por lei do município é outra coisa: continua **mercado interno**, afeta só a parcela do ISS e exige segregação própria — art. 25, § 10 e arts. 30-35 (*lido*, só títulos dos arts. 30-35). Serviço fora da lista da LC 116 (ex.: locação de bens móveis) é Anexo III "deduzida a parcela correspondente ao ISS" — art. 25, § 1º, VI e § 5º.

**PRÁTICA.** No PGDAS-D a exportação é item próprio ("9 - Prestação de Serviços para o exterior", sem as sub-opções de retenção/município); imunidade/isenção entra como informação de ISS por município dentro dos itens de mercado interno. Escritório confunde "não destacou ISS" com "exportação" — e o ISS não é o único efeito: PIS/Cofins também saem.

**RECOMENDAÇÃO.** Desdobrar a natureza em três: **(a) exportação de serviço** (mercado externo; derivável do XML — o leiaute nacional tem, no grupo `tribMun`, o campo `tribISSQN` com valores 1 tributável / 2 imunidade / 3 exportação / 4 não incidência, além de `cPaisResult` e local da prestação — **conferir no XSD**; o `leitor.py` hoje lê só `tpRetISSQN`); **(b) ISS imune/isento/reduzido por lei do ente** (mercado interno; exige parâmetro municipal com base legal e vigência; sem parâmetro, bloqueia); **(c) sem incidência de ISS por estar fora da lista** (mercado interno; Anexo III sem parcela de ISS). E o campo **mercado** (interno/externo) passa a existir em toda receita, inclusive na informada. RBT12 e limite proporcional calculados por mercado; fator r conjunto.

**Confiança:** alta.

---

## 5. Segregações que o pré-DAS vai precisar (prestador de serviço)

**Resposta curta.** Para serviço, o PGDAS-D cruza quatro eixos: **mercado** (interno/exterior), **enquadramento da atividade** (Anexo III fixo; sujeita ao fator r → III ou V; Anexo IV; escritório contábil com ISS fixo; construção 7.02/7.05 e 16.01; transporte municipal; comunicação/transporte intermunicipal — Anexo III com ICMS e sem ISS; locação de bens móveis — Anexo III sem ISS; IPI+ISS simultâneo), **situação do ISS** (devido ao próprio município / devido a outro(s) município(s) / retido ou substituído / valor fixo / imune-isento-reduzido por lei do ente) e **fator r** (FS12). Monofásico/ST só existe para mercadoria — irrelevante para serviço puro; só entra se o cliente também vende.

**NORMA.** LC 123, art. 18, §§ 4º (I-VII) e **4º-A** (I monofásico/ST; II ISS retido ou em valor fixo; III valor fixo/isenção/redução de ISS ou ICMS; IV exportação; **V ISS devido a município diferente do estabelecimento prestador**), §§ 5º-B a 5º-I (atividades por anexo), 5º-J/5º-K/5º-M (fator r), 12-14, 18/18-A (valor fixo) (*cópia*). Res. 140, art. 25, § 1º, III a IX e § 2º (lista por anexo, *lido* — incisos III a IX transcritos acima na pesquisa), § 9º ("a qual Município é devido o imposto"; retenção → desconsidera o percentual do ISS; valor fixo → idem), § 10 (imunidade/isenção/redução → arts. 30-35), § 17 (7.02/7.05: dedução de materiais e Anexo II para mercadoria produzida fora do local). Valor fixo de ISS: só ME até R$ 360 mil, sem filiais, fora do ano de início, e só subitens 7.02, 7.05 e 16.1 (Manual 6.6.12, *lido*; art. 33).

**O que o PGDAS-D pede (Manual, item 6.5, *lido*):** item 7 "Prestação de Serviços, exceto para o exterior" com sub-opções {escritório contábil com ISS fixo; sujeitos ao fator r × (sem retenção, ISS a outro município / sem retenção, ISS ao próprio município / com retenção ou substituição); não sujeitos ao fator r Anexo III × (as mesmas três); Anexo IV × (as mesmas três)}; item 8 (7.02/7.05/16.1 e transporte coletivo municipal, mesmas combinações, Anexo III ou IV); item 9 "para o exterior" (contábil / fator r / Anexo III / Anexo IV); itens 11-14 (comunicação/transporte interestadual; IPI+ISS). Depois, se houver atividade do fator r, pede **FS12**. Para ISS devido a outro município, pede o município e o valor por município.

**Derivável × cadastro.**

| Eixo | Derivável da escrituração? | Fonte / cadastro necessário |
| --- | --- | --- |
| Mercado interno × exportação | **Sim**, se a natureza "exportação" existir (item 4); sugestão pelo `tribISSQN`=3 do XML (conferir XSD) | — |
| ISS retido/substituído | **Sim** (natureza "ISS retido", `tpRetISSQN` 2/3) | — |
| ISS devido a outro município + qual | **Sim** (natureza "outro município" + `cLocIncid` do XML) | Nada além do XML |
| ISS ao próprio município | **Sim** (natureza "devido pelo prestador") | — |
| Imunidade/isenção/redução de ISS por lei do ente | Parcialmente (natureza desdobrada no item 4) | **Parâmetro municipal** com lei, percentual e vigência (arts. 30-35) |
| Anexo da atividade (III / fator r / IV / contábil / construção / transporte / locação) | **Não** da natureza; **sugestão** pelo código de tributação nacional da NFS-e (`cTribNac` = subitem LC 116 + desdobro) e pelo CNAE | **Cadastro "atividades da empresa → item do PGDAS-D"**, com tabela produto subitem LC 116 → anexo/fator r seedada do art. 25, § 1º e validada pelo Fred; nota com `cTribNac` sem mapeamento bloqueia |
| Fator r | **Não** | **FS mensal informada** (item 6) |
| Valor fixo de ISS (escritório contábil) | Não | Parâmetro municipal + condição de ME; só 7.02/7.05/16.1 |
| 7.02/7.05: dedução de materiais na base do ISS | Não | Valor dos materiais por nota (campo `vDedRed`/dedução no XML — conferir) + lei municipal |
| Monofásico/ST (PIS/Cofins/ICMS) | Não se aplica a serviço | Só quando entrar NF-e (DL-010 fatia 2) |
| Excesso de sublimite/limite (alíquota majorada, art. 24) | **Sim**, a partir das receitas acumuladas por mercado | Limites como dado com vigência (item 7) |

**RECOMENDAÇÃO.** Primeiro corte do pré-DAS cobre: Anexo III não sujeito ao fator r, sujeito ao fator r (III/V), Anexo IV, com as três situações de ISS, mercado interno e exportação. Fora do corte (com recusa nomeada): valor fixo de ISS, imunidade/isenção/redução municipal, construção civil com dedução de materiais, comunicação/transporte interestadual, IPI+ISS. A segregação sai de uma **"linha de receita"** = (mercado, atividade→item PGDAS-D, situação do ISS, município do ISS, valor), gerada por regra declarativa a partir da escrituração + cadastro de atividades (DL-067), com o contador vendo e podendo divergir com motivo.

**Confiança:** alta na lista; média no mapeamento `cTribNac` → anexo (é decisão de produto; a norma enquadra por atividade, não por código).

---

## 6. Fator r sem módulo de folha

**Resposta curta.** Prática aceitável e idêntica à do PGDAS-D: o contador **informa a folha** — mas por **mês** (FS mensal), não o FS12 agregado, para o sistema somar a janela correta e refazer a conta quando um mês muda. Componentes: remunerações pagas a pessoas físicas pelo trabalho **informadas em GFIP/eSocial** (empregados, avulsos, contribuintes individuais — **pró-labore e autônomos**), **13º** na competência da incidência, mais **CPP efetivamente recolhida** (inclusive a parcela dentro do DAS) e **FGTS efetivamente recolhido**. Fora: aluguéis e distribuição de lucros (e qualquer verba não informada em GFIP/eSocial).

**NORMA.** LC 123, art. 18, § 24 (red. LC 155/2016): folha = montante pago nos 12 meses anteriores a título de remuneração a PF decorrente do trabalho, "incluídas retiradas de pró-labore", acrescido de CPP e FGTS efetivamente recolhidos; § 25: só remunerações informadas na forma do art. 32, IV da Lei 8.212/1991 (GFIP → eSocial/DCTFWeb); § 26: exclui aluguéis e lucros (*cópia*). Res. 140, **art. 26** (*lido*): I FS12 e II RBT12r conjunto; § 1º (definição acima); § 2º, II: "consideram-se salários o valor da base de cálculo da contribuição prevista nos incisos I e III do art. 22 da Lei nº 8.212" (empregados/avulsos **e** contribuintes individuais), 13º agregado na competência da incidência (Lei 8.620/1993, art. 7º); § 3º exclui aluguéis e lucros; § 4º menos de 13 meses → critérios do art. 22; §§ 6º-7º: regras de zero (FS>0 e receita=0 → r = 0,28; FS=0 e receita>0 → 0,01; ambos zero → 0,01). Manual 1.5 e 8.2.1 (*lido*): FS12 inclui "Contribuição Patronal Previdenciária (inclusive a recolhida dentro do Simples Nacional)"; FS12 é pelo **pago** ("regime de caixa"), informado em GFIP ou eSocial; **de 04/2018 em diante o sistema considera duas casas decimais sem arredondamento (0,2774 → 0,27)**; r ≥ 0,28 → Anexo III, < 0,28 → Anexo V. Res. 190/2026 anota modificação em 01/01/2027 (janela "12 meses antecedentes ao mês anterior ao PA", Econet, *secundário*).

**PRÁTICA.** O Domínio puxa o FS12 do módulo de folha; quem não tem integração digita o total no PGDAS-D a partir do resumo da folha + guia da CPP (DAS ou DCTFWeb, Anexo IV) + guia do FGTS. O erro frequente é usar folha **devida** em vez de **paga/recolhida** e esquecer o 13º e a CPP contida no DAS.

**RECOMENDAÇÃO.** Lançamento "**Folha para fator r**" por empresa e competência, com os componentes separados: remuneração de empregados/avulsos (base INSS), pró-labore e autônomos (base INSS), 13º (na competência da incidência), CPP recolhida (com origem: DAS ou DCTFWeb), FGTS recolhido; total calculado; confirmação mensal como a da receita. FS12 = soma dos 12 anteriores (ou regra do art. 22 se < 13 meses); r truncado em 2 casas; bloqueia o pré-DAS de atividade "sujeita ao fator r" se faltar mês. Quando o módulo de folha existir, vira importação; o lançamento manual continua como sobreposição com trilha.

**Confiança:** alta.

---

## 7. Limites como dado (vigentes em 2026)

| Dado | Valor | Base (artigo) | Vigência | Leitura |
| --- | --- | --- | --- | --- |
| Limite ME | R$ 360.000,00/ano | LC 123, art. 3º, I; Res. 140, art. 2º, I, "a" | desde 2012 (LC 139/2011) — *não conferido hoje* | *cópia* / *lido* |
| Limite EPP | R$ 4.800.000,00/ano | LC 123, art. 3º, II (red. LC 155/2016); Res. 140, art. 2º, I, "b" e § 1º | **01/01/2018** (LC 155/2016, art. 11 — *não conferido hoje*) | *cópia* / *lido* |
| Limite adicional de exportação | R$ 4.800.000,00/ano, separado | LC 123, art. 3º, § 14; Res. 140, art. 2º, § 1º | 01/01/2018 | *lido* |
| Sublimite ICMS/ISS | R$ 3.600.000,00 (interno) + igual para exportação, **todos os Estados e DF em 2026** | LC 123, arts. 13-A e 19, § 4º; Res. 140, art. 9º, § 1º; **Portaria CGSN 54/2025** (DOU 19/11/2025), art. 2º | ano-calendário 2026 (portaria anual, até o último dia útil de novembro — art. 11, § 2º) | *lido* / *cópia* |
| Sublimite opcional p/ UF com PIB ≤ 1% | R$ 1.800.000,00 (nenhuma UF optou para 2026) | Res. 140, art. 9º, caput | — | *lido* |
| Limite proporcional no ano de início | R$ **400.000,00** × meses (fração = mês completo), por mercado | LC 123, art. 3º, § 2º; **Res. 140, art. 3º** | 01/01/2018 | *lido* |
| Sublimite proporcional no ano de início | R$ **300.000,00** × meses (ou R$ 150.000,00 onde vigora 1,8 mi) | LC 123, art. 3º, § 11; **Res. 140, art. 12, § 2º** | 01/01/2018 | *lido* |
| Excesso do limite ≤ 20% | exclusão a partir do ano seguinte | LC 123, art. 3º, § 9º-A (empresa em curso) e § 12 (ano de início); Res. 140, art. 2º, § 3º, II; art. 3º, § 2º, II; **art. 81, II, "a", 2 e "b", 2** (comunicação até o último dia útil de janeiro) | — | *lido* |
| Excesso do limite > 20% | em curso: efeitos no mês seguinte ao excesso; ano de início: **retroativo ao início** | LC 123, art. 3º, §§ 9º e 10; Res. 140, art. 2º, § 3º, I; art. 3º, § 2º, I; art. 81, II, "a", 1 e "b", 1 (comunicação até o último dia útil do mês seguinte) | — | *lido* |
| Excesso do sublimite | mesma lógica de 20%, impedimento de recolher ICMS/ISS no DAS (ano anterior ultrapassado → desde janeiro) | LC 123, art. 3º, §§ 11 e 13; art. 20, §§ 1º e 1º-A; Res. 140, art. 12, §§ 1º, 3º, 4º e 6º; Manual 8.4.1 | — | *lido* |
| Alíquota majorada sobre a parcela excedente | sublimite: ICMS/ISS pela fórmula da 5ª faixa com 3,6 mi; limite: federais pela 6ª faixa com 4,8 mi | LC 123, art. 18, §§ 16, 16-A, 17, 17-A; **Res. 140, art. 24** | — | *lido* |
| RBT12 acima do limite com ano em curso dentro | alíquota da última faixa | Res. 140, art. 22, § 5º | — | *lido* |
| RBT12 = 0 | considerar R$ 1,00 só para a alíquota | Res. 140, art. 21, parágrafo único | — | *lido* |

**Correções à consulta anterior (item 9).** O artigo da exclusão por comunicação na Res. 140 é o **81** (o 79 é certificação digital e o 80, envasadora de bebidas); o do limite proporcional é o **art. 3º** da Res. 140 (não o 22, que é o RBT12); o do sublimite proporcional é o **art. 12, § 2º**. Todos esses dispositivos trazem a anotação "modificação prevista para 01/01/2027 — Res. CGSN 190/2026": **cada valor entra no produto com data de início e fim de vigência**, e a tabela de 2027 só entra depois de lido o texto da 190.

**Confiança:** alta nos valores e artigos; média só nas datas de vigência da LC 155 (art. 11 não lido hoje).

---

## 8. Arredondamento

**Resposta curta.** **Não há regra em lei ou resolução** sobre casas decimais da alíquota efetiva ou do DAS. O que existe é a declaração do Manual do PGDAS-D: "O cálculo do valor devido no PGDAS-D considera **todas as casas decimais**" (o manual mostra até a 5ª só "para fins didáticos"); e, para o fator r, a regra operacional de **duas casas sem arredondamento** desde 04/2018. Como o valor final é arredondado a centavos (e se é por tributo ou no total) o manual **não diz**.

**NORMA.** Nenhuma localizada na LC 123 nem na Res. 140 (*lido*, busquei "arredond" e "casas decimais" no PDF íntegro: só aparece no manual). Manual do PGDAS-D, item 12 e 8.2.1 (*lido*).

**PRÁTICA.** Os sistemas de escritório reproduzem com precisão total e aceitam diferença de centavos contra o PGDAS-D; a Domínio tem artigo específico "Diferença Simples Nacional (Domínio × PGDAS)" (não abri, 403). Em fórum, as divergências relatadas vêm de quem arredondou a alíquota intermediária.

**RECOMENDAÇÃO.** `Decimal` com precisão alta em toda a cadeia (sem arredondar RBT12, alíquota efetiva nem percentual por tributo); arredondar **só o valor devido de cada tributo** para 2 casas no fim (modo `ROUND_HALF_UP` é **hipótese**, não norma — registrar como HI); total = soma dos tributos arredondados (é como o manual soma nos exemplos: 546,43 + 347,73 + … = 9.935,02, com diferença de R$ 0,02 contra 100.000 × 9,935%). Fator r truncado em 2 casas. Na conciliação com o extrato do PGDAS-D, tolerância configurável (sugiro ± R$ 0,05 por tributo) marcada como "diferença de arredondamento", acima disso é divergência real. Exibição da alíquota efetiva com 4 casas (como o manual), deixando claro que é exibição.

**Confiança:** alta em "não há norma"; média na mecânica exata do PGDAS-D.

---

## Tabela-resumo

| # | Pergunta | Resposta | Tipo | Fonte principal | Confiança |
| --- | --- | --- | --- | --- | --- |
| 1 | NFS-e + receita informada | Sim; receita bruta é total da empresa; "receita informada" com origem/mercado/trilha; mês só apura após confirmação "completa"; RBT12 exige 12 meses confirmados; importar extrato PGDAS-D | Norma + prática + recomendação | Res. 140 arts. 2º II e §§ 4º-8º, 17, 18, 22 §1º; Manual PGDAS-D 5.1/6.3; Domínio sol. 65 (secundário) | Alta / média (prática) |
| 2 | Data de início de atividade | Data de abertura no CNPJ (Res. 140 art. 2º V); § 4º do art. 22 para abertura no ano anterior à opção; regra geral se mais antiga; cadastro precisa de abertura + histórico de regime | Norma | Res. 140 arts. 2º IV-V, 3º, 22 §§2º-4º, 26 §4º; Manual 8.3 | Alta |
| 3 | Regime de caixa | Bloquear só o pré-DAS com explicação; RBT12/limites/fator r pela competência; opção acaba no PA 12/2026; atenção art. 20 II "b" em 12/2026 | Norma + recomendação | Res. 140 arts. 16, 19, 20, 77-78; SC Cosit 102/2026; Res. 190/2026 (secundário); Manual 5.1 | Alta / média (transição) |
| 4 | Exportação | Bases e RBT12 separados por mercado; alíquota separada; limite e sublimite um para cada; fator r conjunto; sem PIS/Cofins/ISS; natureza própria "exportação" + desdobrar "sem incidência" em imune/isento e fora da lista | Norma + recomendação | LC 123 art. 3º §§14-15, art. 18 §14; Res. 140 arts. 2º §1º, 3º, 9º §1º, 16 §3º II, 23, 25 §§3º-4º-A, 10; Manual ex. 6 e 8.4 | Alta |
| 5 | Segregação prestador | Eixos: mercado × atividade/anexo (III, fator r, IV, contábil, construção, transporte, locação) × situação do ISS (próprio/outro/retido/fixo/imune) × fator r; derivável: mercado, retido, outro município; cadastro: atividade→item PGDAS-D, FS, parâmetros municipais | Norma + recomendação | LC 123 art. 18 §§4º, 4º-A, 5º-B a 5º-M; Res. 140 art. 25 §§1º, 9º, 10, 17; Manual 6.5, 6.6.12 | Alta / média (mapeamento) |
| 6 | Fator r sem folha | Contador informa FS mensal por componente (remuneração base INSS, pró-labore/autônomos, 13º, CPP recolhida incl. DAS, FGTS recolhido); exclui aluguéis e lucros; r truncado em 2 casas | Norma + prática | LC 123 art. 18 §§24-26; Res. 140 art. 26; Manual 1.5 e 8.2.1 | Alta |
| 7 | Limites | 4,8 mi (e 4,8 mi exportação), sublimite 3,6 mi em todas as UFs em 2026 (Portaria 54/2025), 400 mil e 300 mil × meses, 20% (arts. 2º §3º, 3º §2º, 12, 81 da Res. 140; art. 24 majoração); tudo com vigência, mudança anotada para 01/01/2027 | Norma | Res. 140 (íntegra); Portaria CGSN 54/2025; LC 123 art. 3º | Alta |
| 8 | Arredondamento | Sem norma; manual: "todas as casas decimais"; fator r 2 casas sem arredondar; arredondar só o valor final por tributo; tolerância na conciliação | Norma (ausência) + recomendação | Manual PGDAS-D itens 12 e 8.2.1 | Alta (ausência) / média (mecânica) |

---

## Fontes (consultadas em 08/10/2026)

**Textos oficiais lidos integralmente**
- Resolução CGSN 140/2018 consolidada, com anotações até a Res. CGSN 190/2026 (PDF íntegro; cópia): https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf — oficial em http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278 (não renderiza sem JS)
- Manual do PGDAS-D e DEFIS, versão 17/06/2025 (RFB, PDF oficial): https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf
- Solução de Consulta Cosit 102/2026, de 29/06/2026 (cópia PDF Fenacon): https://fenacon.org.br/wp-content/uploads/2026/07/SC-Cosit-no-102-2026.pdf
- Portaria CGSN 54/2025 (DOU 19/11/2025) — cópia: https://www.normaslegais.com.br/legislacao/portaria-cgsn-54-2025.htm
- LC 123/2006 — cópia: https://www.normaslegais.com.br/legislacao/lc123_2006.htm (Planalto https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm deu 503)
- Agência Gov/RFB, "Regime de caixa deixa de ser utilizado na apuração do Simples Nacional", 14/08/2026: https://agenciagov.ebc.com.br/noticias/202608/regime-de-caixa-deixa-de-ser-utilizado-na-apuracao-do-simples-nacional
- FIEMG, Informação Estratégica nº 52, 11/08/2026 (Res. CGSN 190/2026) — PDF: https://www.fiemg.com.br/wp-content/uploads/2026/08/IE-52-Alteracao-Simples-Nacional-Reforma-Tibutaria-1.pdf
- Resolução CGSN 186/2026 (prazos de opção 2027; alterada pela 194/2026) — cópia: https://www.legisweb.com.br/legislacao/?id=494351
- Repositório: `docs/projeto/consultas/2026-10-08-contador-senior-fiscal.md`, `docs/planos/DL-072-escrituracao-das-nfse-prestadas.md`, `apps/fiscal/leitor.py` (lê `dCompet`, `vServ`, `vLiq`, `tpRetISSQN`; não lê `tribISSQN`/`cTribNac`/`cLocIncid`)

**Fontes secundárias (onde o oficial não abriu)**
- Domínio, "Como preencher a receita bruta dos últimos 12 meses do Simples Nacional?" (solução 65; página 403 hoje, usado o resumo do buscador): https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=65 · "Diferença Simples Nacional (Domínio x PGDAS)" (solução 654, não aberta): https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=654
- Econet, "Simples Nacional: o que muda no RBT12 e no FS12 a partir de 2027": https://blog.econeteditora.com.br/simples-nacional-o-que-muda-no-rbt12-e-no-fs12-a-partir-de-2027/
- BMA Advogados (Res. 190 e 191/2026): https://www.bmalaw.com.br/conteudo/direito-tributario/reforma-tributaria/reforma-tributaria-resolucoes-promovem-mudancas-significativas-no-simples-nacional/pdf · netcpa (Res. 190/2026): https://netcpa.com.br/colunas/resolucao-cgsn-no-1902026-altera-a-resolucao-cgsn-no-140-de-22-de-maio-de-2018-que-dispoe-sobre-o-regime-especial-unificado-de-arrecadacao-de-tributos-e-contribuicoes/28166
- Guia Tributário, "Aplicação das alíquotas quando há receita de exportação": https://guiatributario.net/?p=10117 · Legisweb (Res. 126/2016): https://www.legisweb.com.br/noticia/?id=15960

**Não alcançados hoje (conferir antes de virar regra):** texto integral da Res. CGSN 190/2026 (data no DOU: 10 ou 11/08/2026, fontes divergem; dispositivos revogados e nova janela do RBT12 só por informativos); Perguntas e Respostas do Simples Nacional (página oficial "não encontrada"); LC 155/2016, art. 11 (vigência dos limites de 2018); Res. 140, arts. 30-35 (li só os títulos); XSD da NFS-e nacional para `tribISSQN`/`cTribNac`/`cPaisResult`.
