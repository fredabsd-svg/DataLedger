# Consulta ao contador-senior sobre o módulo fiscal — 08/10/2026

Registro integral da consulta feita pelo `arquiteto-senior` ao
`contador-senior` (skill `anthropic-skills:contador-senior`, rodando em
Fable), por ordem do Fred (RC-164), antes de planejar o módulo fiscal.

⚠️ **Tudo abaixo é HIPÓTESE (HI-54), não requisito confirmado.** É opinião de
IA especialista, com as fontes que ela citou e o grau de leitura de cada uma.
Vale para planejar e para não parar o trabalho; **não** vale como validação
profissional, que é do Fred (AGENTS.md §10). As hipóteses que viraram regra
de produto estão numeradas em [requisitos.md](../requisitos.md) (HI-56 em
diante).

⚠️ **Correção posterior (08/10/2026):** a
[segunda consulta](2026-10-08-contador-senior-rbt12.md), seção 7, corrigiu
três artigos do item 9 abaixo — a exclusão por comunicação é o **art. 81** da
Res. CGSN 140; o limite proporcional é o **art. 3º**; o sublimite proporcional
é o **art. 12, § 2º**. O texto abaixo fica como foi respondido.

Perguntas feitas: escrituração (acumulador × linha por tributo); competência
da NFS-e; ISS retido para o prestador; IBS/CBS em 2026 (PE-39); conferência
bloqueia ou avisa; prioridade de apuração; EFD-Contribuições e a NT 11/2026;
obrigações caducas; RBT12 e início de atividade; datas nos serviços tomados.

---

**Legislação validada até:** 08/10/2026 · **Data de referência das operações:** competências 10/2026 a 03/2027 · **Município-base em análise:** Palmas/TO, com carteira em 52 municípios · **Grau de segurança geral:** médio (vários textos oficiais lidos em cópia íntegra; Planalto, portal do SPED e `normas.receita` estavam indisponíveis hoje — detalho item a item)

Tudo abaixo é **HIPÓTESE para validação do Fred**. Em cada item separo **NORMA** (com a marca *lido* = li o texto, *cópia* = li cópia íntegra em site terceiro, *não conferido* = conhecimento meu), **PRÁTICA** (rotina de escritório e dos sistemas de referência) e **RECOMENDAÇÃO** (produto).

## 1. Escrituração — acumulador × "linha por tributo"

**Resposta curta.** Os dois modelos não competem: o acumulador do Domínio é, na prática, *natureza da operação + conjunto de regras por tributo + contas contábeis* embrulhados num único cadastro. O mais seguro e auditável para o primeiro corte é o modelo da DL-067 (uma escolha única de natureza; linhas por tributo geradas por regra declarativa com vigência), **desde que** o contador continue enxergando e escolhendo a natureza, veja as linhas geradas com a explicação ("por que esta alíquota") e possa sobrepor por exceção, com trilha. Ele **não** deve editar livremente a linha de tributo de uma nota (isso é o que quebra a conciliação no Domínio); deve editar a **natureza** da nota ou a **regra** (com nova vigência).

**NORMA.** Não há leiaute oficial de acumulador (paridade FIS-07 já diz isso). O que a norma exige é rastreabilidade: cada valor de tributo precisa ser reconstruível a partir do documento e da regra vigente na data do fato gerador (CTN art. 144 — *não conferido hoje, mas estável*).

**PRÁTICA.** No Domínio, 80% dos erros de apuração que o escritório descobre no fechamento são "acumulador errado": nota de serviço lançada com acumulador de comércio, acumulador sem o imposto, acumulador com vigência velha. O contador cria acumulador novo a cada situação nova (benefício, retenção, município diferente), e a base cresce sem controle. Questor e Alterdata trabalham com "operação/CFOP + tributação do item", que é mais próximo do modelo por linhas. Em todos, o contador **vê e mexe** na classificação; em nenhum ele recalcula o imposto da nota à mão sem marcar "alterado manualmente".

**RECOMENDAÇÃO.** (a) Primeiro corte com um **catálogo fechado e pequeno de naturezas** (ordem de 10 a 15: serviço prestado tributado, serviço com ISS retido, serviço devido a outro município, serviço tomado, venda de mercadoria, devolução, cancelamento, etc.), cada uma expandindo para linhas por tributo conforme regime da empresa e data. (b) Tela da nota mostra: natureza (editável), linhas por tributo (somente leitura, com link para a regra e a base legal), botão "divergir" que exige motivo e grava trilha. (c) Regras globais do produto, sobreposição por escritório e por cliente, exatamente como a DL-067 propõe. (d) Nunca permitir "acumulador sem imposto" silencioso: natureza sem regra vigente para o regime da empresa bloqueia o lançamento (mesma lógica dos critérios de FIS-03 e FIS-07).

**Confiança:** alta (é decisão de produto apoiada em prática consolidada).

## 2. Competência da NFS-e: `dhEmi` × `dCompet`

**Resposta curta.** **`dCompet` é a data da prestação do serviço** e define o mês do fato gerador do ISS e o mês da receita no regime de competência (Simples e Presumido por competência). `dhEmi` é só a data do documento. Quando os dois meses coincidem (caso normal), nada muda; quando divergem (nota emitida em outubro por serviço de setembro), o ISS e a receita de competência são de **setembro**. No regime de **caixa** (Simples ou Presumido optantes), a base mensal é o **recebimento**, e nem uma nem outra data serve.

**NORMA.**

- ISS: fato gerador é a *prestação* do serviço (LC 116/2003, art. 1º — *não conferido hoje, texto estável*). Em Palmas, apuração mensal "de acordo com os fatos geradores ocorridos no período" (Decreto 1.667/2018, art. 140), NFS-e emitida "no ato da execução dos serviços" (art. 194), e competência errada não se corrige por substituição, só por nova NFS-e na competência certa (arts. 226, I e 227, IV) — *cópia*.
- Leiaute nacional: `dCompet` é "data de competência da prestação do serviço", obrigatório, não pode ser posterior a `dhEmi` (regra E0015), não pode ser anterior a 01/01/2026 para destacar IBS/CBS (E0850) — *lido*: Perguntas e Respostas NFS-e v1.1 (22/09/2026), itens 23.1, 23.7 e 15.4; a definição literal do campo vem do leiaute (não abri o XSD hoje; o repositório já o usa como `d_competencia`, `apps/fiscal/models.py:141`).
- Simples: base de cálculo é a "receita bruta total mensal **auferida** (Regime de Competência) ou **recebida** (Regime de Caixa)" (Res. CGSN 140/2018, art. 16, *cópia íntegra consolidada*); a opção pelo caixa vale só para a base mensal — limites, sublimites e alíquota seguem a competência (art. 19, parágrafo único); parcela a receber não recebida entra na base até o fim do ano seguinte (art. 20, I).
- Presumido: receita por competência como regra; opção pelo caixa (Lei 9.718/1998, art. 13, § 2º; IN RFB 1.700/2017, art. 223 — *não conferido hoje*; o art. 223 exige NF emitida na conclusão do serviço e controle dos recebimentos em conta específica vinculada à nota).

**PRÁTICA.** O Domínio escritura a saída pela data de emissão e permite "data de competência" diferente; o PGDAS-D é preenchido pelo mês de emissão em quase todo escritório, e a divergência de `dCompet` só é tratada quando o cliente emite nota extemporânea no fechamento. Na prática o escritório olha o mês de emissão e considera a competência a exceção.

**RECOMENDAÇÃO.** Guardar as duas datas (já guarda); **escriturar pela `dCompet`** no regime de competência; exibir alerta "nota emitida em mês diferente da competência" e listá-las no relatório de conferência; para empresas em regime de caixa, não apurar enquanto não houver contas a receber (FIS-41) — nunca usar a emissão como aproximação. Para ISS, usar sempre `dCompet`.

**Confiança:** alta para ISS e Simples; média para a prática do PGDAS-D.

## 3. ISS retido (`tpRetISSQN` = 2 ou 3) — efeito para o prestador

**Resposta curta.** (a) **Entra na receita bruta** do Simples e do Presumido pelo valor **bruto** do serviço: retenção é forma de pagamento do imposto, não redução de preço. (b) **Sai do "ISS a recolher" do prestador**: a responsabilidade pelo recolhimento passa ao tomador (LC 116, art. 6º). (c) No Simples, a receita com retenção é **segregada** no PGDAS-D e o **percentual do ISS é desconsiderado** no cálculo do DAS daquela receita; o retido é definitivo. O dispositivo da LC 123 é o **art. 21, § 4º** (regras da retenção) combinado com o **art. 18, § 4º-A, II** (segregação) — não "art. 18 § 4º-A" sozinho.

**NORMA.**

- Receita bruta no Simples: "produto da venda de bens e serviços... o preço dos serviços prestados", excluídas só vendas canceladas e descontos incondicionais (LC 123, art. 3º, § 1º — *cópia*); Res. CGSN 140, art. 2º, §§ 4º e 5º listam o que compõe/não compõe e **não** excluem tributo retido (*cópia íntegra*).
- Presumido: "na receita bruta incluem-se os tributos sobre ela incidentes" (DL 1.598/1977, art. 12, § 5º, red. Lei 12.973/2014 — *cópia*); STJ, Tema repetitivo 1.240: "o ISS compõe a base de cálculo do IRPJ e da CSLL no Lucro Presumido" (*fonte secundária*). Logo, ISS retido não reduz a base de IRPJ/CSLL/PIS/Cofins.
- Simples, retenção: Res. CGSN 140, **art. 27** (*cópia íntegra*, red. Res. 174/2023): só nas hipóteses dos arts. 3º e 6º da LC 116; alíquota na nota = percentual efetivo de ISS do mês anterior (inc. I); 2% no mês de início de atividade (inc. II); 5% se a nota não informar (inc. V); "o valor retido, devidamente recolhido, será definitivo... e sobre a receita de prestação de serviços que sofreu a retenção não haverá incidência de ISS a ser recolhido pelo Simples Nacional" (inc. VII). **Art. 25, § 9º, II**: se houve retenção, "será desconsiderado, no cálculo do valor devido no âmbito do Simples Nacional, o percentual do ISS". LC 123, art. 18, § 4º-A, II: segregar receitas "sobre as quais houve retenção de ISS" (*cópia*).
- NFS-e nacional: o sistema só aceita `tpRetISSQN = 2` quando o município de incidência (`cLocIncid`) é o do tomador (regra E0031; P&R 7.1 e 7.9, *lido*). Para empresa do Simples com `regApTribSN = 1`, o valor do ISS não aparece destacado na nota (P&R 20.2).

**PRÁTICA.** Domínio: acumulador "serviço com ISS retido" e o imposto ISS configurado como "retido" — o valor cai em "ISS retido na fonte" (conferência) e não na guia. No PGDAS-D marca-se "com retenção" na receita. Contabilização usual do prestador: D Clientes (líquido) / D ISS retido a compensar ou Despesa de ISS / C Receita (bruta). Com Simples, a maioria lança o ISS retido como despesa (não há o que compensar, o DAS já excluiu).

**RECOMENDAÇÃO.** FIS-14 está certa; acrescentar: (i) validar a alíquota de retenção da nota contra o percentual efetivo de ISS do mês anterior (art. 27, I) e apontar divergência; (ii) relatório "ISS retido sofrido" por município para o prestador; (iii) para `tpRetISSQN = 3` (intermediário), mesmo tratamento do 2 quanto ao prestador.

**Confiança:** alta.

## 4. IBS/CBS em 2026 nas NFS-e (PE-39)

**Resposta curta.** O destaque em 2026 é "de teste" quanto ao **dinheiro** (0,9% CBS + 0,1% IBS compensáveis com PIS/Cofins e, para quem cumpre as obrigações acessórias, **dispensados de recolhimento**), mas **não** quanto à **obrigação acessória**: para serviços da lista da LC 116 o preenchimento do grupo IBS/CBS na NFS-e é obrigatório desde **01/10/2026** (demais, 01/12/2026); a ausência não rejeita a nota até 31/12/2026, porém configura "desconformidade" sujeita às sanções do Ato Conjunto RFB/CGIBS 4/2026, e o PNCT (Ato Conjunto 5/2026) exige correção até 31/12/2026. Para **Simples Nacional** (ME/EPP/MEI) o preenchimento é **facultativo em 2026** e só obrigatório em 01/01/2027 para quem optar pelo regime regular. Logo: para clientes do **Presumido**, um validador leve tem valor real **agora**; para os do Simples, é informativo.

**NORMA.**

- LC 214/2025, art. 343 (IBS 0,1% em 2026), art. 346 (CBS 0,9%), art. 348 (compensação com PIS/Cofins; § 1º: "fica dispensado o recolhimento do IBS e da CBS... para os sujeitos passivos que cumprirem as obrigações acessórias"; não se aplica a optantes do Simples) — *cópia* (modeloinicial/legjur; Planalto 503).
- P&R NFS-e v1.1 (*lido*), 15.1: cronograma 01/10/2026, 01/12/2026 e 01/01/2027; "não rejeição é diferente de sem consequência"; 15.2: só a validação de presença está suspensa — se o grupo vier, **todas as validações de conteúdo se aplicam**; 15.4: para ME/EPP/MEI "só é obrigatório a partir de 1º de janeiro de 2027"; 15.5: em 2026 `vTotNF = vLiq` (IBS/CBS não somam ao total).
- Ato Conjunto RFB/CGIBS 4/2026 (cronograma) e 5/2026 (PNCT) — *fonte secundária*; texto oficial não aberto.

**Obrigações reais em 2026.** Presumido: destacar IBS/CBS nas NFS-e emitidas (desde 01/10 ou 01/12), com CST/cClassTrib corretos; não há guia nem recolhimento se cumprir isso (art. 348, § 1º); EFD-Contribuições **não** recebe os valores de CBS/IBS de 2026 (NT 011/2026, *lido*). Simples: nenhuma obrigação de destaque em 2026; decisão de opção pelo regime regular (janela de setembro/2026, já passada; 2ª janela 01 a 31/03/2027 — *secundário*, Res. CGSN 190/2026 não lida).

**PRÁTICA.** Os escritórios estão fazendo exatamente isso: conferir se o emissor do cliente está marcando "preencher IBS/CBS" e se o cClassTrib bate com o NBS. Quem não confere vai receber intimação do PNCT.

**RECOMENDAÇÃO.** Prioridade **média-alta e pequena**: validador de conformidade sobre as NFS-e já recebidas, em modo **aviso**, com três checagens — (1) grupo IBSCBS presente quando o prestador é não optante do Simples e `dCompet` ≥ data de obrigatoriedade da categoria; (2) CST/cClassTrib existentes na tabela oficial vigente (importador MF-CAD-10); (3) coerência aritmética 0,9%/0,1% sobre a base (que exclui ISS/PIS/Cofins — LC 214, art. 12, § 2º, *não conferido hoje*). Nada de apuração de CBS/IBS em 2026. Isso não compete com a escrituração de ISS/Simples; é relatório de conferência (classe 1 da personalização).

**Confiança:** alta no cronograma e na dispensa; média nas sanções (atos conjuntos não lidos).

## 5. Conferência: bloquear ou avisar?

**Resposta curta.** **Avisar por padrão; bloquear só o que muda valor de guia ou arquivo.** Três níveis: *bloqueia* (nota sem natureza; nota de empresa sem parâmetro fiscal vigente; débito ≠ crédito na prévia contábil; natureza incompatível com o regime), *exige justificativa para fechar* (CNPJ do tomador divergente do cadastro; `dCompet` em mês diferente da emissão; alíquota de retenção fora do percentual efetivo), *avisa* (retenção sem comprovante/guia do tomador; participante rascunho; valor zerado).

**NORMA.** Não há. O que existe é o dever de escrituração exata e a trilha (já tratados em RC-57, RC-101 a 103).

**PRÁTICA.** O "Conferência de Lançamentos" do Domínio é informativo; o escritório fecha com pendência e corrige no mês seguinte, porque o vencimento do DAS (dia 20) e do ISS (Palmas: dia 10 próprio, dia 15 retido — Decreto 1.667/2018, Anexo I, *cópia*) não espera. "Retenção sem guia" é problema do **tomador**, não do prestador: para o prestador é só conferência de recebível; para o cliente **tomador** que reteve, é guia a emitir e aí sim bloqueia a guia dele, não o fechamento do prestador.

**RECOMENDAÇÃO.** Responder a pergunta de FIS-15 assim: a apuração roda com avisos; a **emissão de guia/arquivo** e o **fechamento da competência** exigem que não haja item de nível "bloqueia" e que os de nível "justificativa" estejam justificados (texto gravado na trilha). O fechamento continua reversível antes da entrega (RC-101).

**Confiança:** alta (produto + prática).

## 6. Prioridade de regime/apuração

**Resposta curta.** **(a) Simples (faturamento, segregação, RBT12, fator R, pré-DAS) → (b) ISS próprio e retido por município → (c) IRPJ/CSLL presumido; PIS/Cofins só como conferência até 12/2026.**

**Justificativa pela rotina mensal.**

- (a) É a rotina de **todos** os clientes do Simples, todo mês, até o dia 20; depende de RBT12 (histórico de 12 meses), fator R (folha), segregação de receitas (ISS retido, outro município, monofásico) — exatamente o que o escritório digita no PGDAS-D e erra. O DataLedger não transmite o PGDAS-D; entrega **pré-apuração e conferência** contra o extrato do PGDAS-D. É o maior volume e o maior risco de erro.
- (b) ISS "por fora" só existe para Presumido e para os casos do Simples com retenção/outro município/valor fixo. Com 52 municípios, começar por **Palmas** (dia 10/15) e pelo relatório de ISS retido por município para todos; municípios restantes entram como parâmetros com vigência, sem cálculo até conferidos.
- (c) Presumido: IRPJ/CSLL são **trimestrais** (menos pressão mensal) e o cálculo é estável; PIS/Cofins cumulativos (0,65% e 3% — *não conferido hoje*) acabam na competência **12/2026**, com a CBS plena em 2027. Construir gerador de PIS/Cofins agora rende 3 competências. **Atenção**: a DL-067 cita a LC 224/2025 e a IN RFB 2.306/2026 alterando o Presumido em 2026 e uma liminar (ADI 7936) — **não li esses textos**; qualquer número do Presumido entra com vigência e fonte conferida antes.

**NORMA.** DAS: dia 20 (Res. CGSN 140, art. 40 — *não conferido hoje*). ISS Palmas: Decreto 1.667/2018, Anexo I (*cópia*). IRPJ/CSLL trimestral: Lei 9.430/1996, arts. 1º e 25 (*não conferido hoje*). PIS/Cofins: dia 25 (*não conferido*).

**PRÁTICA.** O fechamento mensal do escritório é, nesta ordem: folha → Simples (PGDAS-D) → ISS dos Presumidos → PIS/Cofins → trimestralmente IRPJ/CSLL. O sistema que mais ajuda é o que fecha o Simples sem redigitar.

**Confiança:** alta.

## 7. EFD-Contribuições e a "NT RFB 11/2026"

**Resposta curta.** **Procede, com uma correção de termo.** A Nota Técnica nº 011/2026 (RFB, orientativa, publicada em 03/02/2026) diz que a EFD-Contribuições "deixará de ser utilizada para a apuração de novos fatos geradores de PIS e COFINS a partir de janeiro de 2027", mas **não é "encerrada"**: a obrigação de manter, consultar e **retificar** persiste "pelo prazo mínimo de 5 (cinco) anos", os saldos credores até 31/12/2026 continuam escriturados para compensação com a CBS, e **não há alteração de leiaute** para CBS/IBS/IS em 2026 ("estes valores não devem ser somados aos valores dos itens ou dos documentos fiscais no ano de 2026").

**NORMA.** NT 011/2026 — *lido* o texto integral, em cópia PDF publicada pela Fenacon (documento da RFB, autor interno, criado em 04/02/2026). As páginas do portal do SPED (`sped.rfb.gov.br/pagina/show/8017` e `/arquivo/show/8016`, apontadas pela Senior) retornaram 503 hoje — **conferir lá antes de emendar FIS-29 a FIS-34**. Última competência: 12/2026, entrega até o 10º dia útil do 2º mês subsequente (IN RFB 1.252/2012, art. 7º — *não conferido hoje*; a data exata de fevereiro/2027 depende do calendário de dias úteis da RFB: a DL-067 diz 16/02/2027, fontes secundárias oscilam entre 12 e 16/02 — **não confirmado**).

**RECOMENDAÇÃO.** Manter a decisão 8 da DL-067: sem gerador novo; importador das EFD entregues (saldos, auditoria); motor de PIS/Cofins só para conferência das 3 competências restantes. Emendar FIS-29 a FIS-34 para "leitura e conferência".

**Confiança:** alta no conteúdo da NT; média na URL oficial (não aberta).

## 8. Obrigações caducas: DCTF mensal, DeSTDA/TO, Redução Z

**DCTF mensal (PGD).** **Caduca.** A IN RFB 2.237/2024 (04/12/2024) unificou DCTF e DCTFWeb na "DCTFWeb" para fatos geradores a partir de **01/01/2025** (art. 1º, § 1º, I); os tributos antes da DCTF PGD (IRPJ, CSLL, PIS, Cofins, IPI, IOF etc.) entram pelo **MIT** (arts. 8º e 9º); optantes do Simples **não** informam na DCTFWeb os tributos abrangidos pelo regime (art. 8º, § 4º); revoga a IN 2.005/2021 (art. 18). Prazo: último dia útil do mês seguinte (art. 6º, red. IN RFB 2.248/2025 — *secundário*). *Cópia íntegra* da IN 2.237 lida (normaslegais); página oficial da DCTFWeb no gov.br lida (cita a IN). **Produto:** FIS-67 vira "preparação da MIT" (como MF-FED-17), nunca DCTF PGD. Confiança: **alta**.

**DeSTDA no Tocantins.** **Extinta no TO, mas só por fonte secundária.** O Decreto 6.696, de 01/11/2023 (DOE-TO de 01/11/2023), alterou o RICMS/TO e "revogou o dispositivo que instituiu a DeSTDA", com efeitos nas datas do próprio ato (substituicaotributaria.com, 03/11/2023). **Não consegui ler o decreto** (PDF da COAD: 403; portal `dtri.sefaz.to.gov.br`: DNS falhou; AL/TO: PDF ilegível), então **artigo revogado e data de efeitos não confirmados**. Nacionalmente o Ajuste SINIEF 12/2015 segue e outras UFs exigem a DeSTDA de quem tem IE lá. **Produto:** FIS-68 fora de escopo para estabelecimentos no TO; manter como "a confirmar por UF" se houver cliente com IE em outra UF. Confiança: **média**.

**Redução Z (ECF).** **Sem norma nacional de extinção**, mas obsoleta na prática e no TO. O Convênio ICMS 09/2009 (ECF/PAF-ECF) não foi revogado, porém cada UF substituiu o ECF pela NFC-e; no Tocantins a Portaria SEFAZ 1.328/2019 tornou a NFC-e obrigatória (2019, regime normal e Simples; MEI dispensado) com cessação de uso dos ECF — *fonte secundária*. Os registros C400/C405 da EFD ICMS/IPI continuam no leiaute só para legado. **Produto:** FIS-40 fora de escopo; qualquer varejo entra por NFC-e. Confiança: **média** (texto da portaria não lido).

## 9. RBT12, início de atividade e limites 2026

**Resposta curta.** Artigos exatos: **LC 123, art. 18, §§ 1º, 1º-A e 2º** e **art. 3º, § 2º**; **Res. CGSN 140/2018, art. 21 (fórmula) e art. 22, §§ 1º a 5º** (RBT12 e proporcionalização). O art. 22 (não o 21) é o da proporcionalização. Limites 2026: **R$ 4,8 milhões** (LC 123, art. 3º, II) e sublimite **R$ 3,6 milhões em todos os Estados e DF** (Res. CGSN 140, art. 9º, § 1º; Portaria CGSN 54/2025, DOU 19/11/2025) — **vigentes**.

**NORMA (Res. CGSN 140, *cópia íntegra consolidada*).**

- Art. 21, II: alíquota efetiva = (RBT12 × Aliq − PD) / RBT12; III, "a": percentual efetivo máximo de ISS 5%, diferença redistribuída aos federais; parágrafo único: RBT12 = 0 → considerar R$ 1,00.
- Art. 22, § 1º: RBT12 = receita bruta acumulada nos 12 meses anteriores ao PA.
- § 2º: **1º mês de atividade** → receita do próprio mês × 12.
- § 3º: **11 meses seguintes** → média aritmética da receita dos meses **anteriores** ao PA × 12 (mês sem receita entra como zero).
- § 4º: início no ano anterior ao da opção → regra do § 3º até completar 12 meses; regra geral a partir do 13º mês.
- § 5º: RBT12 acima do limite (mas receita do ano dentro) → alíquota da última faixa.
- LC 123, art. 3º, § 2º: no início de atividade "o limite... será proporcional ao número de meses em que a ME/EPP houver exercido atividade, inclusive as frações de meses" (R$ 400 mil × meses; sublimite R$ 300 mil × meses) — *cópia*.
- Art. 18, § 2º: "em caso de início de atividade, os valores de receita bruta acumulada constantes dos Anexos I a V... devem ser proporcionalizados ao número de meses de atividade no período" — *cópia*.
- **Atenção:** todos esses artigos trazem a anotação "modificação prevista para 01/01/2027, nos termos da Res. CGSN 190/2026" (IBS/CBS no Simples). Texto da 190 não lido.

**Exemplo (síntese, não oficial).** Empresa aberta em 10/03/2026 (fração = mês inteiro): limite 2026 = 10 × 400.000 = R$ 4,0 mi; sublimite = 10 × 300.000 = R$ 3,0 mi. Receitas: mar 20.000, abr 30.000, mai 25.000. RBT12 para mar = 20.000 × 12 = 240.000; abr = 20.000 × 12 = 240.000; mai = ((20.000 + 30.000)/2) × 12 = 300.000; jun = ((20.000+30.000+25.000)/3) × 12 = 300.000. O `scripts/simples_nacional.py` da skill já implementa isso.

**PRÁTICA.** O PGDAS-D calcula sozinho; o erro do escritório é na **retenção** (art. 27, I, "b": média dos meses que antecedem o **mês anterior**, não o PA) e em esquecer que fração de mês conta como mês inteiro no limite proporcional.

**Confiança:** alta.

## 10. Datas na escrituração de serviços tomados (entradas)

**Resposta curta.** Para o **ISS retido pelo tomador**, a competência é o **mês do fato gerador (`dCompet`)**, não a data em que a nota chegou ao escritório; em Palmas, a retenção "deve ocorrer no mesmo mês do fato gerador, independentemente do pagamento" (Decreto 1.667/2018, art. 145 — *cópia*). Para **PIS/Cofins/IRPJ** o serviço tomado só importa (crédito) no Lucro Real, fora de escopo; no Presumido e no Simples a entrada de serviço é **despesa contábil por competência** e documento para retenções federais (IRRF/CSRF/INSS), cuja competência é a do **pagamento/crédito** (Reinf/DCTFWeb), não a da nota. Não há norma que mande usar a "data de recebimento do documento" na escrituração fiscal; isso é convenção de sistema.

**NORMA.** LC 116, art. 1º (fato gerador = prestação, *não conferido hoje*); Decreto 1.667/2018 de Palmas, arts. 140 e 145 (*cópia*). Para os demais 51 municípios, confirmar a lei local (a maioria copia a LC 116). EFD-Contribuições registra, para serviços tomados (A100), data de emissão e data de execução/conclusão do serviço (`DT_DOC`/`DT_EXE_SERV` — *não conferido hoje*, Guia Prático).

**PRÁTICA.** Domínio: "data de entrada" (escrituração) ≠ "data de emissão"; a apuração usa a entrada, salvo extemporâneo (paridade FIS-13 já registra). O escritório lança a entrada no mês em que o cliente manda o documento — é por isso que ISS retido de serviço tomado em setembro vira guia de outubro com multa.

**RECOMENDAÇÃO.** Guardar três datas no lançamento de entrada: emissão (`dhEmi`), competência (`dCompet`) e escrituração (hoje); apurar ISS retido pela competência; se a competência já estiver fechada, lançar na competência aberta com marca "extemporâneo" e alerta de guia em atraso (ISS retido Palmas dia 15 do mês seguinte ao fato gerador). Para retenções federais, usar a data de pagamento quando houver (integração com contas a pagar, fora do primeiro corte) e, sem ela, alertar em vez de presumir.

**Confiança:** alta para Palmas; média para os demais municípios.

## Tabela-resumo

| # | Pergunta | Resposta | Base | Fonte principal | Confiança |
| --- | --- | --- | --- | --- | --- |
| 1 | Acumulador × linhas por tributo | Natureza única escolhida pelo contador; linhas por tributo geradas por regra, visíveis e explicadas; divergência só por exceção com trilha | Prática + recomendação | DL-067 (motor), paridade FIS-07 | Alta |
| 2 | `dhEmi` × `dCompet` | `dCompet` = prestação → ISS e receita por competência; caixa = recebimento | Norma | P&R NFS-e v1.1 (23.1, 23.7); Res. CGSN 140 arts. 16, 19, 20; Dec. 1.667/2018 arts. 140, 194, 226-227 | Alta |
| 3 | ISS retido para o prestador | Compõe receita bruta; sai do ISS a recolher; no Simples, receita segregada e percentual do ISS desconsiderado (retido é definitivo) | Norma | Res. CGSN 140 arts. 25 §9º II e 27; LC 123 arts. 3º §1º, 18 §4º-A II, 21 §4º; DL 1.598 art. 12 §5º; STJ Tema 1.240 | Alta |
| 4 | IBS/CBS 2026 nas NFS-e | Destaque obrigatório para não-Simples desde 01/10 ou 01/12/2026; sem rejeição até 31/12; dispensa de recolhimento se cumprir acessórias; Simples facultativo em 2026 → validador leve em modo aviso | Norma + recomendação | LC 214 arts. 343, 346, 348; P&R NFS-e 15.1-15.5; Atos Conjuntos 4 e 5/2026 (secundário) | Alta/Média |
| 5 | Conferência bloqueia ou avisa | Avisa por padrão; bloqueia só o que muda guia/arquivo; nível intermediário exige justificativa | Prática + recomendação | Dec. 1.667/2018 Anexo I (prazos) | Alta |
| 6 | Prioridade de apuração | (a) Simples → (b) ISS por município (Palmas primeiro) → (c) IRPJ/CSLL presumido; PIS/Cofins só conferência até 12/2026 | Prática + recomendação | NT 011/2026; rotina mensal | Alta |
| 7 | NT RFB 11/2026 | Procede: sem novos FG a partir de 01/2027; mantida 5 anos para retificação/créditos; sem leiaute CBS em 2026 | Norma | NT 011/2026 (cópia Fenacon; portal SPED 503) | Alta/Média |
| 8 | DCTF, DeSTDA/TO, Redução Z | DCTF PGD caduca (IN 2.237/2024, MIT); DeSTDA revogada no TO pelo Dec. 6.696/2023 (secundário); Redução Z sem extinção nacional, obsoleta no TO (NFC-e desde 2019) | Norma + secundário | IN 2.237/2024; gov.br DCTFWeb; substituicaotributaria.com; Portaria SEFAZ-TO 1.328/2019 (secundário) | Alta / Média / Média |
| 9 | RBT12 e início de atividade; limites | Res. CGSN 140 art. 22 §§1º-5º; LC 123 arts. 3º §2º e 18 §§1º-2º; R$ 4,8 mi e sublimite R$ 3,6 mi vigentes em 2026 | Norma | Res. CGSN 140 (cópia íntegra); Portaria CGSN 54/2025; LC 123 (cópia) | Alta |
| 10 | Data em serviços tomados | Competência (`dCompet`) para ISS retido; escrituração registra também emissão e data de lançamento; retenções federais pelo pagamento | Norma (Palmas) + prática | Dec. 1.667/2018 arts. 140, 145; LC 116 art. 1º | Alta (Palmas) / Média |

## Fontes (consultadas em 08/10/2026)

**Textos oficiais lidos integralmente (em cópia quando indicado)**

- Nota Técnica nº 011/2026 EFD-Contribuições (RFB, 03/02/2026) — cópia PDF: <https://fenacon.org.br/wp-content/uploads/2026/02/Nota-Tecnica-011_2026-Descontinuidade-da-EFD-Contribuicoes-Orientacoes-para-os-contribuintes.pdf> · páginas oficiais indicadas pela Senior (503 hoje): <http://sped.rfb.gov.br/pagina/show/8017> e <http://sped.rfb.gov.br/arquivo/show/8016>
- Perguntas e Respostas NFS-e v1.1, 22/09/2026 (SE/CGNFS-e): <https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-e-respostas-nfs-e-v-1-1-20260922.pdf>
- Res. CGSN 140/2018 consolidada (com anotações até Res. 190/2026) — cópia: <https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf> (oficial em <http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=92278> não renderizou)
- Portaria CGSN 54/2025 (DOU 19/11/2025) — cópia: <https://www.normaslegais.com.br/legislacao/portaria-cgsn-54-2025.htm>
- IN RFB 2.237/2024 consolidada — cópia: <https://www.normaslegais.com.br/legislacao/in-rfb-2237-2024.htm> · página oficial DCTFWeb: <https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/DCTFWeb>
- LC 123/2006 — cópia: <https://www.normaslegais.com.br/legislacao/lc123_2006.htm> (Planalto 503)
- LC 214/2025, arts. 343, 346, 348 — cópias: <https://modeloinicial.com.br/lei/LCP-214-2025/lei-complementar-214/art-348> (e art-343, art-346) (Planalto 503)
- Decreto 1.667/2018 de Palmas (RCTM) e Anexo I — cópia: <https://www.legisweb.com.br/legislacao/?id=375471>
- Repositório: `docs/planos/DL-067-plano-do-modulo-fiscal.md`, `docs/projeto/paridade/fiscal.md`, `docs/projeto/requisitos.md` (RC-76, RC-110, PE-39), `apps/fiscal/models.py`, `apps/fiscal/leitor.py`

**Fontes secundárias (usadas onde o oficial não abriu)**

- Senior, NT 011/2026: <https://documentacao.senior.com.br/exigenciaslegais/noticias/federal/2026/2026-02-04-nota-tecnica-11-2026-descontinuidade-efd-contribuicoes-com-orientacoes-para-contribuintes-pis-e-cofins> · Fenacon: <https://fenacon.org.br/reforma-tributaria/nota-tecnica-orienta-contribuintes-sobre-a-transicao-da-efd-contribuicoes-com-a-reforma-tributaria/>
- Decreto 6.696/2023 (TO) e DeSTDA: <https://www.substituicaotributaria.com/SST/substituicao-tributaria/noticia/03/11/2023/to-alterou-legislacao-de-substituicao-tributaria-e-da-destda> · PDF do decreto (403 hoje): <https://coad.com.br/app/webroot/imagensMat/dec6696to2023.pdf>
- NFC-e no TO (Portaria SEFAZ 1.328/2019): <https://www.conexaoto.com.br/2018/12/10/nfc-e-sera-obrigatoria-para-todos-os-comerciantes-do-tocantins-em-2019> · Portaria 167/2023: <https://www.legisweb.com.br/legislacao/?id=443073>
- IN RFB 2.248/2025 (prazo DCTFWeb): <https://www.pwc.com.br/pt/consultoria-tributaria-societaria/thinking-about-taxes/tax-legis/2025/ctfweb---alteracao-e-prorrogacao-do-prazo-de-entrega---in-rfb-n-.html>
- Ato Conjunto RFB/CGIBS 4/2026 e 5/2026 (PNCT): <https://inventti.com.br/ato-conjunto-rfb-cgibs-no-4-2026-define-cronograma-oficial-para-emissao-dos-documentos-fiscais-da-reforma-tributaria/> · <https://www.contabeis.com.br/noticias/79499/nfs-e-compliance>
- DL 1.598/1977, art. 12 §§ 4º e 5º: <https://www.legjur.com/legislacao/art/lei_00129732014-2> · STJ Tema 1.240: <https://www.ibet.com.br/stj-1a-secao-repetitivo-irpj-csll-apuracao-pelo-lucro-presumido-base-de-calculo-inclusao-do-iss-cabimento/>
- Res. CGSN 190/2026 (janelas do regime regular): <https://www.coad.com.br/home/noticias-detalhe/139518/receita-federal-alerta-sobre-o-prazo-para-opcao-pelo-simples-nacional-e-para-a-escolha-do-modelo-de-recolhimento-do-ibs-e-da-cbs-em-2027>
- SC Cosit 298/2019 (ISS retido no Simples): <https://www.ibet.com.br/solucao-de-consulta-cosit-no-298-de-12-de-dezembro-de-2019/>
- Prazo EFD-Contribuições (IN 1.252 art. 7º): <https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/ecf/perguntas-e-respostas-pessoa-juridica-2021-arquivos/capitulo-xxvii-efd-contribuicoes-2021.pdf>

**Não alcançados hoje (conferir antes de virar regra):** Planalto (503 em todas as tentativas — LC 123, LC 116, LC 214, DL 1.598); portal do SPED (503); `normas.receita.fazenda.gov.br` (só renderiza com JS); `dtri.sefaz.to.gov.br` (DNS); Perguntas e Respostas do Simples Nacional (PDF oficial de 18/09/2026 está "em atualização", só capa); IN RFB 1.700/2017 art. 223; Res. CGSN 190/2026; LC 224/2025 e IN RFB 2.306/2026 (Presumido 2026).
