# Consulta ao contador-senior sobre o ISS de Palmas — 08/10/2026

Quinta consulta do `arquiteto-senior` ao `contador-senior` (Fable), por ordem
do Fred (RC-164), antes de planejar a etapa de ISS por município
([DL-076](../../planos/DL-076-iss-por-municipio-palmas.md)). Registro integral da
resposta. As hipóteses que viraram regra de produto estão em
[requisitos.md](../requisitos.md) (HI-82 a HI-86 e PE-79).

**Legislação validada até:** 08/10/2026 · **Competências de referência:** 10/2026 a 03/2027 · **Município:** Palmas/TO (carteira em 52 municípios) · **Grau de segurança geral:** médio — prazos, base de cálculo, ISS fixo, retenção, NFS-e e multa foram lidos em cópia íntegra ou em fonte oficial; **a tabela de alíquotas vigente não foi encontrada em nenhuma fonte** (detalhe no item 1).

⚠️ Tudo abaixo é **HIPÓTESE para validação do Fred**. Marcas de fonte: *lido* = texto oficial aberto hoje; *cópia* = texto íntegro em site terceiro (legisweb, normasbrasil, contabeis); *secundário* = notícia, blog, fornecedor; *não conferido* = conhecimento meu sem texto aberto hoje.

Li antes, no repositório: [consulta fiscal](2026-10-08-contador-senior-fiscal.md) (itens 3, 6 e 10 citam Palmas dia 10/15 pelo Decreto 1.667/2018, Anexo I) e [leiaute IBS/CBS](2026-10-08-leiaute-ibscbs-nfse.md). O que achei hoje **confirma** o dia 10/15 e **não contradiz** nada dos dois documentos.

**Observação sobre acesso:** o portal legislativo de Palmas (`legislativo.palmas.to.gov.br`) devolveu 503 em todas as tentativas por WebFetch e falha de cadeia TLS no `curl` (não desliguei verificação). Por isso a LC 285/2013 consolidada oficial, a LC 300/2014, a LC 418/2021 e o Decreto 2.787/2025 **não foram lidos no original**; usei as cópias do legisweb e do normasbrasil, que são consolidadas e coerentes entre si, e a do contabeis, que é o **texto original de 2013 sem consolidação** (serve só para a redação original). Planalto abriu via `curl` com User-Agent de navegador (LC 116 e DL 406 *lidos*).

---

## 1. Alíquotas do ISS em Palmas (2026)

**Resposta curta.** **Não consegui determinar a tabela vigente.** O que está documentado: (a) a redação original do CTM (LC 285/2013, art. 57) fixava **2%** para transporte coletivo municipal urbano (sobre tarifas), **3%** para hospedagem (item 9.01) e **5%** para "as demais atividades"; (b) as duas cópias consolidadas marcam o art. 57 como **"Revogado pela Lei Complementar nº 300 DE 30/07/2014"**; (c) o Anexo II vigente (lista de serviços, redação da LC 385/2017, efeitos 01/01/2018) **não tem coluna de alíquota** nas cópias; (d) o RCTM (Decreto 1.667/2018) não fixa percentual — só fala em "alíquota da operação" (art. 132); (e) a alíquota mínima de 2% está no **art. 57-A** da LC 285 (LC 385/2017, efeitos 30/12/2017). **O texto da LC 300/2014 não foi encontrado em nenhum site**, então não sei se ela moveu as alíquotas para outro dispositivo/anexo, unificou em 5% ou outra coisa.

**NORMA.**
- LC 116/2003, art. 8º, II: máxima 5% (*lido*); art. 8º-A: mínima 2%, § 1º veda benefício que resulte em carga menor, exceto 7.02, 7.05 e 16.01; § 2º nulidade da lei municipal que desrespeite a mínima para tomador em outro município; § 3º restituição (*lido*).
- LC 285/2013, art. 57 (redação original, *cópia* contabeis): "I – 2% para os serviços de transporte coletivo municipal urbano de passageiros, em relação às tarifas; II – 3% para os serviços de hospedagem, previsto no item 9.01; III – 5%, para as demais atividades." Marcado "(Revogado pela LC 300 DE 30/07/2014)" nas cópias legisweb e normasbrasil.
- LC 285/2013, art. 57-A (LC 385/2017): "A alíquota mínima do ISS é de 2%", §§ 1º a 3º espelham o art. 8º-A da LC 116 (*cópia*, duas fontes).
- LC 285/2013, art. 62 teve "redação dada pela LC 300/2014" (isenções — transporte coletivo e ambulantes), o que **sugere** que a LC 300/2014 tratou do transporte coletivo e pode ter reorganizado as alíquotas — **inferência minha**, não comprovada.

**Evidência de prática (fraca).** Três NFS-e de Palmas publicadas na transparência da Câmara dos Deputados (07/2024, 12/2025 e 03/2026) são todas de optantes do Simples, então a "Alíquota ISS (%)" impressa (2,0000 e 5,0000) é o percentual do Simples, **não** serve para inferir a alíquota municipal.

**RECOMENDAÇÃO.** Não codificar nenhum percentual como padrão de Palmas. Tabela de alíquotas **por subitem, com vigência e fonte**, preenchida pelo escritório; sem linha vigente para o subitem, a apuração **bloqueia** (mesmo critério de FIS-03/FIS-07). Validações independentes da tabela: `pAliqAplic` fora de [2%, 5%] → aviso forte (art. 8º e 8º-A); abaixo de 2% com tomador em outro município → aviso de nulidade (art. 8º-A § 2º). **Pergunta objetiva ao Fred:** qual percentual o WebISS de Palmas aplica hoje a cada subitem dos clientes dele (o sistema municipal calcula a alíquota por item) — essa é a tabela de fato; a de direito está na LC 300/2014 (DOM de 30/07/2014), que precisa ser lida.

**Grau de segurança:** baixo para a tabela; alto para os limites 2%–5%.

## 2. Prazo de recolhimento (próprio e retido)

**Resposta curta.** **Confirmado em cópia íntegra:** ISS próprio ("normal") **dia 10** do mês seguinte à competência; ISS **retido/substituição dia 15**; estimativa dia 10; ISS fixo em 12 parcelas no último dia de cada mês, a 1ª (ou única) em 31/01. Dia não útil → **primeiro dia útil seguinte**. Não encontrei alteração do Anexo I; as anotações de alteração do RCTM nas cópias são dos Decretos 1.916/2020 e 2.165/2022 (arts. 2º, 3º, 53 e 73 — nada de prazo) e do Decreto 2.787/2025 (materiais de construção, art. 126 — *secundário*, texto não lido). **Vigência em 2026 é hipótese forte, não confirmada por ato de 2026**, porque o art. 86, § 1º permite à Sefin alterar o calendário temporariamente.

**NORMA (Decreto 1.667/2018 — RCTM, *cópia* legisweb).**
- Art. 86: recolhimento "obedecerá aos prazos fixados no Calendário Fiscal" (Anexo I); § 1º: a Secretaria de Finanças pode alterar o calendário temporariamente, criar regime diferenciado e fixar valor mínimo (exceto ISS fixo, estimativa, Simples e Simei); § 2º: convênios prevalecem; § 3º: vencimento em dia não útil é transferido "para o primeiro dia útil seguinte".
- Art. 140: "O regime de apuração do ISS será mensal, considerado o calendário civil."
- Art. 145: retenção/substituição "no mesmo mês do fato gerador, independentemente do pagamento"; art. 146 e LC 285 art. 61, § 2º: órgãos públicos podem usar regime de caixa para o retido.
- Art. 214: ISS das NFS-e pago "exclusivamente por meio de DAM", nos prazos do Calendário Fiscal, excluídos Simei e ME/EPP do Simples; § 2º: o sistema permite ao contribuinte ou ao tomador responsável emitir DAM por nota ou por grupo de notas.
- Anexo I, Tabela 1.1 (Calendário Fiscal): mês de referência janeiro → normal 10/02, retenção/substituição 15/02, estimativa 10/02, fixo 31/01 (1ª/única); e assim por diante até dezembro → 10/01, 15/01, 10/01, fixo 31/12 (12ª). Estimativa de eventos (ingressos) até 2 dias úteis antes do evento.
- LC 285/2013, art. 61: "pagamento... na forma e prazos definidos em calendário fiscal a ser expedido pelo Chefe do Poder Executivo" (*cópia*).

**RECOMENDAÇÃO.** Parametrizar vencimento como regra do município com vigência (Palmas: dia 10 próprio, dia 15 retido, rolagem para o dia útil seguinte usando calendário de feriados **municipais** de Palmas — a regra fala em "dia não útil", então feriado municipal conta; isso é inferência). Exibir "fonte: Dec. 1.667/2018, Anexo I" no relatório.

**Grau de segurança:** alto para o texto; médio para a vigência em 2026 (sem ato de 2026 lido).

## 3. Base de cálculo, deduções e o que a NFS-e traz

**Resposta curta.** Base = preço do serviço. Deduções que Palmas admite: **materiais** dos subitens 7.02/7.05 (com regras próprias de cadastro — Recom — e um regime estimativo de até 30%); **pagamentos a credenciados** em 4.22/4.23 (limite 60%); serviços de terceiros em 17.06; taxa judiciária em 21.01; **desconto incondicional**. **Subempreitada não é dedutível** em Palmas (vedação expressa) nem pela LC 116 (inciso vetado). O produto deve **conferir** o `vISSQN` da nota contra a tabela, não recalcular para a guia — em Palmas a guia (DAM) sai do WebISS a partir das notas (art. 214), e correção de valor se faz por **substituição da NFS-e** (art. 226), não por ajuste na escrituração.

**NORMA.**
- LC 116, art. 7º: "A base de cálculo do imposto é o preço do serviço"; § 2º, I: não se inclui "o valor dos materiais fornecidos pelo prestador dos serviços previstos nos itens 7.02 e 7.05"; § 2º, II (subempreitadas) **VETADO** (*lido*). DL 406/1968, art. 9º, § 2º, "b" (subempreitadas já tributadas) — *lido*, mas a aplicação após a LC 116 é controvertida e Palmas veda.
- LC 285/2013, art. 53: preço do serviço; art. 54: deduções — I materiais 7.02/7.05; II serviços de terceiros a agências de publicidade (17.06); III taxa judiciária e congêneres (21.01); IV repasses de cooperativas em 4.22/4.23 (LC 293/2014); parágrafo único: notários destacam o imposto fora do preço (*cópia*).
- RCTM, art. 114: preço = receita bruta; § 2º: materiais 7.02/7.05, pagamentos a credenciados 4.22/4.23, **descontos incondicionais**; arts. 126–131: Recom e regimes de dedução de materiais (regime estimativo deduz até 30% — art. 131); art. 130, parágrafo único, IV: **veda dedução de "quaisquer subempreitadas"**; art. 137: planos de saúde, deduções até 60% da base mensal; art. 138: receitas e deduções "consideram-se declaradas" pela emissão das NFS-e; art. 139: desconto incondicional dedutível; art. 148: na retenção "prevalecem os valores de ISS apurados na nota fiscal" (*cópia*).
- Decreto 2.787/2025 (20/10/2025): restringe a dedução de materiais ao que o próprio prestador fornece e que seja mercadoria tributada por ICMS, com base no STF RE 603.497 (Tema 247), alterando o art. 126 do RCTM — *secundário* (preâmbulo em snippet de busca; texto não lido).
- Campos da NFS-e nacional (`vServ`, `vDescIncond`, `vDescCond`, deduções/`vDR`, `vBC`, `pAliqAplic`, `vISSQN`, `tpRetISSQN`): **não conferi o leiaute hoje**; o repositório já os lê (`apps/fiscal/leitor.py`), use o que está lá.

**RECOMENDAÇÃO.** Para cada nota prestada tributada em Palmas: `esperado = (vServ − vDescIncond − deduções) × alíquota_tabela`; comparar com `vISSQN` com tolerância de R$ 0,01 (mesma lógica do validador IBS/CBS, sem inventar arredondamento). Divergência → nível "exige justificativa"; dedução informada em subitem que Palmas não admite (p.ex. 7.02 sem Recom, ou subitem fora de 7.02/7.05/4.22/4.23/17.06/21.01) → aviso. O total da apuração **soma o `vISSQN` das notas** (é o que a DAM vai cobrar) e mostra, ao lado, a diferença acumulada contra a tabela, para o contador decidir se substitui notas.

**Grau de segurança:** alto na norma; médio na recomendação (depende de o DAM de Palmas ser gerado só pelas notas, item 4).

## 4. Palmas e a NFS-e nacional

**Resposta curta.** Palmas é **"Conveniado Ativo"** na NFS-e nacional, **aderente ao Ambiente de Dados Nacional (Sim)**, **não** usa o Emissor Nacional (Não), não aderiu ao MAN; publicação 11/08/2023, início de vigência **02/10/2023** (planilha oficial *lida*). A **emissão continua no WebISS municipal** (padrão ABRASF; `palmasto.webiss.com.br`) e as notas de 2026 saem com "Chave de Acesso da NFS-e Nacional" impressa — evidência de que o município **compartilha** as notas com o ADN. **Não há DMS/DES geral em Palmas**: a única declaração periódica é a DES-IF (instituições financeiras) e a DEF (estimativa); o ISS "considera-se declarado" pela emissão das NFS-e (art. 138) e a **guia (DAM) é gerada no sistema a partir das notas** (art. 214, § 2º). Exportação **tem NFS-e** (emissão obrigatória; não incidência pelo art. 2º, I da LC 116). Serviço de prestador estabelecido em Palmas com imposto devido a outro município também é emitido no WebISS de Palmas, com "Exigibilidade do ISS" em outro município.

**NORMA / FONTES.**
- Planilha "municipios-aderentes-20260928.xlsx" do portal gov.br/nfse, linha Palmas/TO, CNPJ 24851511000185: StatusConvenioSEFIN "Conveniado Ativo"; AderenteAmbienteNacional "Sim"; AderenteEmissorNacional "Não"; AderenteMAN "Não"; Publicação 11/08/2023; Início de Vigência 02/10/2023 (*lido*).
- NFS-e de Palmas emitida em 23/03/2026 (documento público na transparência da Câmara): cabeçalho "MUNICÍPIO DE PALMAS – Secretaria Municipal de Finanças", campo "Chave de Acesso da NFS-e Nacional: 1721000...", validação em `palmasto.webiss.com.br`, rodapé "emitida com respaldo no Decreto nº 1667 de 6 de dezembro de 2018" e "Esta NFS-e é autodeclaratória" (*lido*). A de 07/2024 não trazia a chave nacional.
- RCTM: art. 192 (NFS-e em sistema da Sefin; obrigatória inclusive para Simples e Simei), art. 194 (emissão no ato da execução ou do adiantamento), art. 199 (identificação por subitem), art. 203 (natureza da operação: tributada no Município, imune, isenta), art. 214 (DAM), arts. 225–228 (substituição em 180 dias; **competência e tomador não se corrigem por substituição** — art. 226; cancelamento por inexecução, divergência de tomador, duplicidade ou competência incorreta, com análise prévia; cancelamento irreversível, § 8º; guarda dos XML — art. 228), arts. 231–233 (DES-IF: bancos e quem usa Cosif; módulo 2 "apuração mensal do ISS" até o dia 5 do mês seguinte), arts. 237–238 (DEF anual) (*cópia*). Nenhuma menção a "padrão nacional"/"ADN" no RCTM.
- Notícia de 09/01/2026: Prefeitura concluiu adequações do "Sistema de Gestão do ISS" para envio ao ADN a partir de janeiro/2026 (*secundário*, notagateway). Blog de 07/07/2026: WebISS ABRASF 2.02, certificado A1; "passou a enviar dados ao ADN a partir de janeiro de 2026" (*secundário*).

**Ponto de atenção para o produto (inferência).** As NFS-e de Palmas chegam ao ADN **convertidas** pelo município a partir do leiaute ABRASF do WebISS. Não sei que versão/completude de XML nacional o ADN entrega para elas (1.00 ou 1.01; presença de `vDR`, `tpRetISSQN`, grupo IBS/CBS). O leitor precisa tolerar campos ausentes e registrar a origem.

**Grau de segurança:** alto na adesão e no modelo "sem declaração, guia pelas notas"; médio na data em que as notas passaram a ir ao ADN (a planilha diz 10/2023; as evidências de chave nacional só aparecem em 2026).

## 5. ISS fixo (autônomos e sociedades de profissionais)

**Resposta curta.** Palmas mantém o regime: fato gerador em **1º de janeiro**; autônomo inscrito no Cades paga **valor anual em UFIP pelo Anexo III**; sociedade de profissionais paga **por profissional habilitado** se cumprir 7 requisitos (entre eles até 2 empregados por sócio e não ser sociedade empresária), com **opção anual** requerida até **20 de dezembro** para o exercício seguinte; pagamento em **12 parcelas** (último dia de cada mês, 1ª em 31/01) ou **cota única com 10% de desconto**. Esses contribuintes **não sofrem retenção**. Sim: o produto deve apenas **identificar** (flag de regime "fixo" com vigência anual) e **recusar a apuração por alíquota**, listando as notas para conferência.

**NORMA.**
- DL 406/1968, art. 9º, § 1º (trabalho pessoal: alíquotas fixas) e § 3º (sociedades: imposto por profissional habilitado) — *lido*.
- LC 285/2013: art. 47 (FG 1º de janeiro, ressalvado início no exercício); art. 58 (autônomo inscrito → "alíquotas fixas determinadas no Anexo III"; parágrafo único: equiparado a empresa se não inscrito ou com mais de 2 empregados/autônomos); art. 59 (sociedades simples, 7 requisitos); art. 61, § 1º (12 parcelas ou única com 10%); art. 52 (não sujeitos à retenção: estimativa, alíquota fixa e instituições financeiras) (*cópia*).
- **Anexo III (valores anuais em UFIP, *cópia* em duas fontes coincidentes):** Nível superior — médicos, odontólogos, advogados, engenheiros, arquitetos e contadores: **1.200 UFIP**; demais profissionais de nível superior: **780**; nível médio técnico: **540**; demais nível médio: **300**; nível fundamental: **180**.
- RCTM: art. 153, § 1º (definição de autônomo); art. 154 (equiparação a empresa); art. 157; art. 159 (opção anual das sociedades); art. 161 (pedido até 20/12); arts. 162–163 (sem pedido ou sem requisitos → receita bruta); art. 147 (sem retenção para autônomo no Cades); art. 93, III (parcelamento em 12); Anexo I (fixo: 31/01 … 31/12) (*cópia*).
- UFIP 2026: atualizada em **4,46%** pelo Decreto 2.832/2025 (DOM 30/12/2025, efeitos 01/01/2026; Portaria 23/2025/GAB/SEFAZ) — *cópia*. **Valor em R$ não encontrado** (um cálculo indireto a partir de notícia de IPTU sugere ≈ R$ 4,83 — *inferência de terceiro*, não use).
- STJ, repetitivo de 10/2025 (REsp 2.162.486/2.162.487): sociedade uniprofissional limitada pode ter o regime fixo — *secundário*.

**RECOMENDAÇÃO.** Cadastro da empresa com "regime ISS Palmas = fixo (autônomo | sociedade de profissionais)", vigência por exercício e lembrete em dezembro (pedido até 20/12). Para essas empresas: nenhuma linha de ISS por alíquota; relatório lista notas e alerta se alguma NFS-e vier com `vISSQN` > 0 ou retenção (`tpRetISSQN` ≠ 1), porque não deveria (art. 52). Não calcular o valor anual sem o valor da UFIP confirmado.

**Grau de segurança:** alto na estrutura; médio nos valores do Anexo III (duas cópias coincidentes, original não lido); baixo no valor da UFIP.

## 6. ISS devido a outro município

**Resposta curta.** Para o prestador de Palmas, o imposto vai ao outro município nas exceções do art. 3º (I a XXV) da LC 116, com a **lei de lá**. O produto deve **listar por município de incidência** (`cLocIncid`), com alíquota e `vISSQN` da própria nota, **sem calcular**, até que o município tenha parâmetros conferidos (como a DL-067 já prevê). Palmas espelha a LC 116 no art. 44 da LC 285 (incisos XXI–XXIII e § 4º pela LC 385/2017; ajustes pela LC 418/2021).

**NORMA.**
- LC 116, art. 3º, caput (red. LC 157/2016): devido no estabelecimento prestador, exceto incisos I a XXV; III (7.02, 7.19 e **14.14**, red. LC 218/2025); XXIII (4.22, 4.23, 5.09 — domicílio do tomador); XXIV (15.01 — cartões); XXV (15.09 — leasing, red. LC 175/2020; o 10.04 saiu); §§ 5º a 12 (quem é o tomador nesses casos, LC 175/2020); § 4º (descumprida a alíquota mínima, devido no tomador) — *lido*.
- LC 116, art. 6º, § 2º, II (responsabilidade do tomador PJ em 3.05, 7.02, 7.04, 7.05, 7.09, 7.10, 7.12, 7.14, 7.15, 7.16, 7.17, 7.19, 11.02, 17.05, 17.10, red. LC 183/2021), III (§ 4º do art. 3º), IV (15.01, LC 175/2020) — *lido*.
- LC 285/2013, art. 44, incisos XXI a XXIII e § 4º (LC 385/2017, efeitos 01/01/2018); art. 51, XXIII e §§ 1º–2º (*cópia*). LC 418/2021 alterou arts. 44 e 51 e acrescentou inciso XXIV ao art. 51 — *secundário* (não li).
- LC 175/2020 (padrão nacional de obrigação acessória para 4.22/4.23/5.09/15.01/15.09, CGOA): **não conferido hoje** além do que está incorporado ao art. 3º da LC 116.

**RECOMENDAÇÃO.** Relatório "ISS devido a outros municípios" por competência: município (código IBGE + nome), subitem, nº da nota, `vBC`, `pAliqAplic`, `vISSQN`, `tpRetISSQN`. Validações: alíquota < 2% ou > 5% → aviso; subitem fora das exceções do art. 3º com `cLocIncid` ≠ Palmas → aviso "incidência possivelmente errada" (o emitente escolheu local de incidência incompatível com a regra geral). Nenhum cálculo, nenhuma guia.

**Grau de segurança:** alto.

## 7. ISS retido sofrido (prestador)

**Resposta curta.** O relatório deve mostrar, por competência: tomador (CNPJ/nome), município de incidência, subitem, nº/chave da nota, `vBC`, alíquota, **valor retido** (`vISSQN` quando `tpRetISSQN` = 2 ou 3), e o total por município. Na apuração de Palmas, as notas com retenção **não entram no ISS a recolher** do prestador — a responsabilidade é do tomador, que recolhe no dia 15; o prestador não precisa de guia do tomador para fechar o mês. **Comprovante do tomador** é prudência, não requisito: a própria NFS-e com retenção destacada é o documento do prestador; em Palmas, "prevalecem os valores de ISS apurados na nota fiscal" (RCTM art. 148), e o crédito é considerado satisfeito "quando o prestador comprova o pagamento" (art. 144), o que **sugere** que, se o tomador não recolher, a Prefeitura pode voltar-se contra o prestador — não li o art. 49 da LC 285 (solidariedade) por inteiro para afirmar isso.

**NORMA.**
- LC 116, art. 6º: município pode atribuir responsabilidade a terceiro "excluindo a responsabilidade do contribuinte ou atribuindo-a a este em caráter supletivo"; § 1º: responsáveis recolhem integralmente "independentemente de ter sido efetuada sua retenção na fonte" — *lido*.
- LC 285/2013, art. 51 (24 incisos de responsáveis: Município, órgãos federais/estaduais, bancos, operadoras de cartão, incorporadoras/construtoras, concessionárias, organizadores de eventos, shoppings, seguradoras, escolas, hospitais, planos de saúde, concessionárias de veículos, entidades de classe, sindicatos/cooperativas, transportadoras, empresas de informática, condomínios, consórcios, agências de publicidade, serviços sociais autônomos, tomadores dos serviços listados em XXII, XXIII — § 4º do art. 44, XXIV — LC 418/2021); art. 52 (quem não sofre retenção) (*cópia*, lista resumida pela fonte).
- RCTM: art. 141 (I: tomadores indicados **devem** reter; II: substitutos/solidários **podem**); art. 142 (exime solidários salvo erro, má-fé, dolo, fraude, simulação); art. 143 (substituto recolhe mesmo sem ter retido); art. 144 (crédito satisfeito quando o prestador comprova o pagamento; cobrança complementar); art. 145 (retenção no mês do FG); art. 148 (prevalecem os valores da nota; prestador responde pela veracidade) (*cópia*).
- NFS-e nacional: `tpRetISSQN` = 2 só aceito quando `cLocIncid` é o do tomador (regra E0031) — já registrado na consulta anterior, item 3.

**RECOMENDAÇÃO.** Manter o que a consulta anterior já disse (FIS-14): retido compõe a receita bruta e sai do "a recolher". Acrescentar coluna "comprovante do tomador anexado (S/N)" opcional, nível **aviso**, nunca bloqueio. Para o cliente que é **tomador** em Palmas (reteve), a apuração espelho é "ISS retido a recolher — dia 15", por nota ou agrupado (art. 214, § 2º).

**Grau de segurança:** alto.

## 8. Reforma tributária e o ISS em 2026

**Resposta curta.** **Nada muda para o ISS até 12/2028.** A redução começa em **2029**: 10% em 2029, 20% em 2030, 30% em 2031 e 40% em 2032, sobre as alíquotas municipais vigentes em 31/12/2028; benefícios reduzidos na mesma proporção. Em 2026 só existe o destaque de teste de IBS/CBS (0,1% / 0,9%) nas notas, já tratado na consulta anterior (item 4) e na pesquisa de leiaute.

**NORMA.** LC 116, art. 8º-B, I a IV e § 1º (incluído pela LC 214/2025) — *lido*. LC 214/2025, arts. 343 e 346 — *lido* na pesquisa de leiaute de hoje. EC 132/2023 (ADCT) — *não conferido hoje*.

**Grau de segurança:** alto.

## 9. Multa e juros de mora em Palmas

**Resposta curta.** Pagamento em atraso: **atualização monetária** + **multa de mora de 0,33% por dia, até 30 dias; a partir daí 10%** do tributo + **juros de 1% ao mês ou fração**; multa e juros incidem sobre o valor atualizado. A UFIP (e os créditos) é atualizada a cada 1º de janeiro pelo IPCA — não achei índice de atualização intra-anual, então **inferência**: dentro do exercício, sem atualização.

**NORMA.** LC 285/2013, art. 142, I–III e § 1º (*cópia*, três fontes coincidentes, texto literal confirmado); art. 146 e parágrafo único (*cópia*). RCTM art. 92 repete os mesmos percentuais para parcelamento (*cópia*). Reduções da LC 367/2017 (70%/50%/30%) são para multas **punitivas**, não de mora — *secundário*.

**RECOMENDAÇÃO.** Aviso informativo "guia em atraso: multa 0,33%/dia (máx. 10%) + juros 1%/mês ou fração — LC 285/2013, art. 142", sem calcular o valor (atualização monetária não parametrizada).

**Grau de segurança:** alto no texto; médio na aplicação da atualização monetária.

---

## Tabela-resumo

| # | Tema | Resposta | Fonte principal | Marca | Segurança |
| --- | --- | --- | --- | --- | --- |
| 1 | Alíquotas Palmas | **Não determinada.** Original 2013: 2% transporte, 3% hospedagem, 5% demais; art. 57 revogado pela LC 300/2014 (texto não achado); Anexo II sem coluna de alíquota; mínima 2% art. 57-A | LC 285 arts. 57/57-A; LC 116 arts. 8º, 8º-A | cópia / lido | Baixa (tabela) / Alta (limites) |
| 2 | Prazos | Próprio dia 10; retido dia 15; fixo 12× último dia do mês; dia não útil → próximo útil; Sefin pode alterar | Dec. 1.667/2018 arts. 86, 140, 145, 214; Anexo I | cópia | Alta (texto) / Média (2026) |
| 3 | Base e deduções | Preço; materiais 7.02/7.05 (Recom; até 30% estimativo), credenciados 4.22/4.23 (60%), 17.06, 21.01, desconto incondicional; subempreitada vedada; **conferir**, não recalcular | LC 116 art. 7º; LC 285 arts. 53–54; RCTM arts. 114, 126–139, 148 | lido / cópia | Alta |
| 4 | NFS-e nacional | Conveniado ativo; ADN Sim (vig. 02/10/2023); Emissor Nacional Não; emissão no WebISS; sem DMS; DAM gerada das notas | Planilha gov.br/nfse 28/09/2026; NFS-e 03/2026; RCTM arts. 138, 192–228, 231–238 | lido / cópia | Alta |
| 5 | ISS fixo | FG 1º/jan; Anexo III: 1.200/780/540/300/180 UFIP/ano; opção até 20/12; 12 parcelas ou única −10%; sem retenção; produto só identifica e recusa alíquota | LC 285 arts. 47, 52, 58–61, Anexo III; RCTM arts. 153–163; DL 406 art. 9º | cópia / lido | Média-alta; UFIP R$ não achado |
| 6 | Outro município | Listar por `cLocIncid` com alíquota/valor da nota; não calcular | LC 116 arts. 3º, 6º § 2º; LC 285 art. 44 | lido / cópia | Alta |
| 7 | Retido sofrido | Por competência/tomador/município/nota/valor; sai do a recolher; comprovante = aviso | LC 116 art. 6º; LC 285 arts. 51–52; RCTM arts. 141–148 | lido / cópia | Alta |
| 8 | Reforma | ISS integral até 2028; redução 10/20/30/40% em 2029–2032 | LC 116 art. 8º-B (LC 214/2025) | lido | Alta |
| 9 | Mora | 0,33%/dia até 30 dias, depois 10%; juros 1% a.m. ou fração; sobre valor atualizado | LC 285 art. 142 | cópia | Alta |

## O que verifiquei, o que inferi, o que não determinei

**Verificado (texto aberto hoje).** LC 116/2003 arts. 1º, 2º, 3º, 6º, 7º, 8º, 8º-A, 8º-B (Planalto); DL 406/1968 art. 9º (Planalto); planilha oficial de municípios aderentes à NFS-e nacional (linha Palmas/TO); três NFS-e de Palmas e uma de Araguaína publicadas na transparência da Câmara (cabeçalho, chave nacional, rodapé, campos de valores). Cópias íntegras: Decreto 1.667/2018 (legisweb, 3 trechos), LC 285/2013 (legisweb e normasbrasil consolidadas; contabeis original), LC 385/2017, LC 297/2014, Decreto 2.832/2025.

**Inferido.** Que a LC 300/2014 reorganizou as alíquotas (ela deu redação ao art. 62, sobre isenção do transporte coletivo); que "dia não útil" inclui feriado municipal; que as notas do WebISS chegam ao ADN convertidas e podem vir com campos ausentes; que a atualização monetária é só anual; que a Prefeitura pode cobrar do prestador o retido não recolhido pelo tomador (art. 144).

**Não determinado.** (1) **Tabela de alíquotas vigente de Palmas** — LC 300/2014 não encontrada em nenhum site; portal legislativo de Palmas inacessível (503/TLS). (2) Valor da UFIP 2026 em R$. (3) Texto do Decreto 2.787/2025 (só preâmbulo em snippet). (4) Texto da LC 418/2021. (5) Ato de 2026 confirmando ou alterando o Calendário Fiscal. (6) Versão/completude do XML que o ADN entrega para notas de Palmas. (7) Art. 49 da LC 285 (solidariedade) por inteiro. (8) Decreto 28.899/15 citado por blog sobre autônomos — não identificado. **Pedir ao Fred:** as alíquotas que o WebISS aplica aos subitens dos clientes dele e, se possível, cópia da LC 300/2014 (DOM de 30/07/2014) e do valor da UFIP 2026.

Sources:
- [LC 116/2003 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm)
- [DL 406/1968 — Planalto](https://www.planalto.gov.br/ccivil_03/decreto-lei/del0406.htm)
- [Decreto 1.667/2018 Palmas (RCTM) — legisweb](https://www.legisweb.com.br/legislacao/?id=375471)
- [LC 285/2013 Palmas consolidada — legisweb](https://www.legisweb.com.br/legislacao/?id=261379)
- [LC 285/2013 Palmas consolidada — normasbrasil](https://www.normasbrasil.com.br/norma/lei-complementar-285-2013-palmas_261379.html)
- [LC 285/2013 Palmas texto original — contabeis](https://www.contabeis.com.br/legislacao/56429/lei-complementar-285-2013/)
- [LC 385/2017 Palmas — normasbrasil](https://www.normasbrasil.com.br/norma/lei-complementar-385-2017-palmas_346557.html)
- [LC 297/2014 Palmas — legisweb](https://www.legisweb.com.br/legislacao/?id=272839)
- [Decreto 2.832/2025 Palmas (UFIP 2026) — normasbrasil](https://www.normasbrasil.com.br/norma/decreto-2832-2025-palmas_488956.html)
- [Monitoramento das adesões à NFS-e — gov.br](https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes)
- [Planilha municípios aderentes 28/09/2026 — gov.br](https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes/municipios-aderentes-20260928.xlsx)
- [NFS-e Palmas 03/2026 (transparência Câmara)](https://www.camara.leg.br/cota-parlamentar/documentos/publ/3435/2026/8070783.pdf)
- [NFS-e Palmas 07/2024 (transparência Câmara)](https://www.camara.leg.br/cota-parlamentar/documentos/publ/3023/2024/7776998.pdf)
- [Palmas ajusta NFS-e para ADN — notagateway (secundário)](https://notagateway.com.br/blog/palmas-to-ajusta-nfs-e-para-envio-de-dados-ao-ibs-e-cbs-a-partir-de-2026/)
- [Palmas na NFS-e nacional — nfe.io (secundário)](https://nfe.io/docs/prefeituras-integradas/tocantins/palmas-to-1721000/)
- [Nota fiscal Palmas 2026 — Contmatic (secundário)](https://simplifique.contmatic.com.br/blogs/nota-fiscal-palmas-como-emitir)
- Não alcançados (503/TLS): [LC 285 consolidada 2024 — Câmara de Palmas](https://legislativo.palmas.to.gov.br/media/leis/lei-complementar-285-2013-10-31-21-2-2024-17-23-49.pdf) · [Decreto 2.787/2025](https://legislativo.palmas.to.gov.br/media/leis/decreto-2.787-2025-10-20-23-10-2025-15-54-18.pdf) · [LC 418/2021](https://legislativo.palmas.to.gov.br/media/leis/lei-complementar-418-2021-09-29-30-9-2021-14-13-56.pdf)
