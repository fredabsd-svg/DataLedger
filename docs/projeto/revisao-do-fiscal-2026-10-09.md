# Revisão do módulo fiscal — mapa de lacunas — 09/10/2026

> **Retrato datado, não fonte de estado.** Análise feita por um agente de pesquisa em 09/10/2026, por ordem do Fred (RC-175). O estado vivo do projeto mora só em [estado.md](../agents/estado.md). Das inconsistências apontadas na seção 3, as I1, I2, I5 e I6 foram corrigidas no `estado.md` e no `README.md` no mesmo dia. As demais ficam para a etapa de revisão de documentação, que será planejada junto com o desenho dos acumuladores.

**Método.** Li `apps/fiscal/` (modelos, serviços, rotas), os templates, `base.html`, `module_homes.py` e `LancamentoContabil`. Li também os planos DL-067 e DL-072 a DL-085, o `estado.md`, o `mapa-funcional-fiscal.md`, o `catalogo-de-relatorios.md`, o `escopo.md` e as partes pertinentes do backlog e dos requisitos.

**Não executei nenhum teste.** Cito os números de linha base do `estado.md` como "Inferido da documentação". Não li o AGENTS.md §3.1: os níveis de risco abaixo seguem o que o DL-067 diz (cálculo, guia e arquivo de obrigação são nível 1; importador, tela e relatório de conferência são nível 2).

**Legenda.** **M** = Medido no código. **D** = Inferido da documentação.

## Resumo em dez linhas

1. O fiscal tem hoje duas coisas sólidas. A primeira é a **recepção** de NFS-e, NF-e e NFC-e. A segunda é a **escrituração** de NFS-e prestada, NFS-e tomada e NF-e de saída ou devolução, ligada à **receita** e à **apuração de quatro impostos**. Os quatro são pré-DAS de serviços, ISS, retenções e IRPJ/CSLL do Presumido (M).
2. **Não existe nada** de ICMS, IPI, PIS/Cofins, livros, guias, obrigações acessórias, calendário central, participantes, produtos, acumuladores ou integração contábil (M, detalhes abaixo).
3. O que o escritório do Fred mais precisa e não tem:
   - **ICMS-TO** do comércio e dos postos.
   - **Escrituração de entradas** (compras e créditos).
   - **PIS/Cofins** do Presumido, que ainda vale para out, nov e dez de 2026.
   - A **virada de 2027**. Hoje o código recusa por design o Simples 2027 (`rbt12.py:58,487`, `pre_das.py:831`), a NF-e de 2027 (`escrituracao_nfe.py:759-777`) e o caixa a partir de 2027 (`receita.py:1307`).
   - A **integração contábil**, bloqueada pelo BL-72 (o lançamento contábil não tem origem).
4. A **classificação que dirige o cálculo** já existe, mas "em código". São três catálogos fechados em `TextChoices`: `NaturezaOperacao`, `NaturezaTomada` e `NaturezaOperacaoNFe` com `CATALOGO_NATUREZA_NFE` (`models.py:629, 896, 2639, ~2695`). Eles são o embrião do acumulador, mas não têm vigência, tributo por tributo, nem conta contábil. Detalhe na seção 2.1.
5. O `estado.md`, o README, o `paridade/fiscal.md` e o catálogo de relatórios têm afirmações **desmentidas pelo código** (seção 3). Há ao menos um banner dentro do produto que ainda diz "apuração fiscal ainda não disponível".

---

## 1. O que existe hoje, por capacidade

| Capacidade | Situação | Evidência | Tipo |
| --- | --- | --- | --- |
| **Recepção NFS-e nacional** | Existe. XML, ZIP, leiautes 1.00 e 1.01, deduplicação, eventos de cancelamento, tpAmb=2 recusado. | `leitor.py:332-365`, `services.py`, rotas `recepcao/`, `documentos/` (`urls_web.py:100-115`) | M |
| **Recepção NF-e (55) e NFC-e (65)** | Existe. Leiaute 4.00 com protocolo, denegada recusada, séries 890-899, eventos de cancelamento, eventos sem nota. | `leitor_nfe.py` (docstring, `_DOMINIO_MODELO` ~l.101), `models.py:399-620`, rotas `nfe/` (`urls_web.py:117-130`), API `api_nfe.py` | M |
| **CT-e, NFCom, GTVe, MDF-e, BP-e, CF-e** | **Não existe.** Qualquer namespace diferente da NFS-e e da NF-e é recusado com "tipo ainda não suportado". O acervo real tinha 9 CT-e, 69 NFCom e 1 GTVe (D, `mapa-funcional-fiscal.md:145-152`). | `leitor.py:359,365` | M |
| **Entrada em RAR** | **Não existe.** Só XML e ZIP, embora o RC-43 peça RAR. A busca por "rar" em `apps/fiscal/*.py` não retornou nada. | `services.py` (ZIP), `requisitos.md:306` | M |
| **Importação de SPED Fiscal (RC-44) e do formato de intercâmbio de terceiros (FIS-73)** | **Não existe.** Não achei código. | busca em `apps/fiscal` | M |
| **Limite de envio** | 2.000 arquivos e 50 MB por envio, um envio por vez por escritório. Para um posto com 10.000 ou mais NFC-e por mês isso são 5 envios ou mais. A DL-085 mediu a escrituração, mas a medida do envio "ficou como proposta". | `services.py:65` | M / D |
| **Escrituração NFS-e prestadas** | Existe. Rascunho, efetivada e estorno, 6 naturezas, três datas, conferência recebidas × escrituradas. | `models.py:629-693`, rotas `escrituracao/*` (`urls_web.py:150-175`) | M |
| **Escrituração NFS-e tomadas** | Existe. 6 naturezas (T1, T2, T3, T5, T6, T7). T4 (importação de serviço) fica fora, com recusa nomeada. | `models.py:896-1100`, `tomadas.py`, rotas `tomadas/*` | M |
| **Escrituração NF-e de saída e devolução de venda** | Existe. Natureza **por item**, conferência W16, reclassificação em massa. | `escrituracao_nfe.py:7-10,162-203`, `models.py:2835-3300`, rotas `nfe/escrituracao/*` | M |
| **Escrituração NF-e/NFC-e em lote (DL-085)** | Existe na branch: prévia por grupo, confirmação em bloco com assinatura, efetivação em partes de 100, leitura de itens em partes de 400. A rodada 1 foi aprovada com ressalvas e a correção está em andamento. | `escrituracao_nfe_lote.py` (1.246 linhas), `models.py:3304-3447`, migração `0013`, `urls_web.py:139`, `urls_api.py` (lote/previa, confirmar, ler) | M / D |
| **Entradas, compras e créditos (NF-e)** | **Não existe.** A elegibilidade recusa de propósito: "nota de entrada (compra): fora desta escrituração, só a recepção". Exceção: a devolução de venda que chega como entrada própria (`tpNF` 0, `finNFe` 4). | `escrituracao_nfe.py:10,186-203` | M |
| **Itens de NF-e (base para ICMS, PIS/Cofins e IPI)** | **O dado está guardado e não é usado.** `ItemNFe` grava CFOP, NCM, CEST, CST/CSOSN, orig, vBC, pICMS, vICMS, vICMSDeson, ST (vBCST, vICMSST, vICMSSTRet), partilha da UF de destino, vIPI, vPIS, vCOFINS, vII, o grupo IBS/CBS bruto e cBenef. O docstring diz: "a apuração do ICMS (etapa própria) vai ler daqui". | `models.py:3027-3175`, `itens_nfe.py` | M |
| **Receita e RBT12 do Simples** | Existe. Receita do mês = notas efetivadas + receita informada, confirmação mensal, reabertura, a retificar, RBT12 **por mercado**, limites como dado com vigência, regime de caixa tratado como bloqueio. | `receita.py`, `rbt12.py`, `models.py:1220-1660`, rotas `simples/receita/` | M |
| **Pré-DAS, serviços (Anexos III a V)** | Existe. Tabelas dos Anexos I a V como dado, fator r (folha informada), alíquota efetiva, repartição, teto do ISS, segregação, atividades da empresa. Os exemplos 2, 4 e 5 do Manual do PGDAS-D batem ao centavo (D). | `pre_das.py:819-1228`, `simples_tabelas.py:537`, `models.py:1661-1950` | M |
| **Pré-DAS, comércio e indústria (Anexos I e II)** | **Recusa o mês com NF-e.** Em desenvolvimento na DL-082. A cópia de trabalho `dl082` está fora deste checkout (`git status` limpo). | `pre_das.py:869-880` (bloqueio HI-122) | M |
| **Pré-DAS 2027** | **Recusado por design.** | `pre_das.py:831`, `rbt12.py:58,487-489` | M |
| **Guia DAS, transmissão ao PGDAS-D, importação do extrato** | **Não existe** (HI-55; PE-87 "conciliação real"). | `DL-074:62`, `DL-082` | M / D |
| **ISS por município** | Existe. Regras legais do município (vencimentos), alíquotas por subitem **informadas pelo escritório** com vigência e fonte, regime do ISS por empresa. Também existem a conferência por nota, a apuração do ISS próprio fora do Simples, o retido sofrido e o ISS devido a outros municípios. | `models.py:1950-2190`, `iss_municipal.py`, `iss_nota.py`, rotas `iss/*` | M |
| **ISS, cobertura de municípios** | Só Palmas tem lógica (`PALMAS` em `tomadas.py`). O cadastro aceita outros, "mas nenhum vem pronto". A tabela de alíquotas de Palmas não foi achada, então o escritório cadastra (HI-82, PE-79 com o Fred). O acervo tem NFS-e de 52 municípios (RC-76). | `DL-076:69-73`, `estado.md:237-239` | M / D |
| **ISS retido pelo tomador (a recolher)** | Existe, com vencimento pela regra do município. Sem regra cadastrada, mostra "não parametrizado". | `retencoes.py:195`, `iss_municipal.py:991-1018` | M |
| **Retenções federais (IRRF, CSRF, INSS) em tomadas** | Existe. Três "relógios" de competência: ISS pela competência, INSS pela emissão, IRRF e CSRF pela data de pagamento informada. Só leitura e totalização. | `retencoes.py:1-40`, rota `tomadas/retencoes-federais/` | M |
| **IRRF e CSRF sofridos (prestadas) no Presumido** | Existe. Retenção proposta por nota, **confirmada pelo contador**, e só então deduzida. | `presumido.py:20,716-747`, rota `presumido/retencoes/` | M |
| **Presumido: IRPJ e CSLL trimestrais** | Existe. Percentuais de presunção por atividade como dado, acréscimo da LC 224 com sobra e limite, 3 colunas (sem LC 224, com, parcela), medida judicial, quotas e vencimentos, receita informada, receita de NF-e (DL-083) com combustível em duas naturezas. | `presumido.py` (1.907 linhas), `presumido_calculo.py:129-610`, `presumido_tabelas.py`, `models.py:2188-2640`, rotas `presumido/*`, API `api_presumido.py` | M |
| **Presumido: adicional de 10%, ganho de capital, receitas financeiras** | O adicional de 10% sobre o excedente de R$ 60.000 por trimestre está no cálculo (D, `DL-067`). **Ganho de capital, regime de caixa e PER/DCOMP estão fora** (D). | `DL-079:85-91` | M / D |
| **PIS/Cofins (qualquer regime)** | **Não existe cálculo, apuração nem parâmetro.** Aparece só como (a) campo lido na nota, (b) segregação no pré-DAS e (c) coerência da CSLL retida. | busca em `apps/fiscal/*.py` | M |
| **ICMS (próprio, ST, DIFAL, FECOEP, CIAP, crédito)** | **Não existe apuração.** Só o dado lido por item e o total do `ICMSTot`. Marcas de ST e de monofásico são **natureza do item** para a receita, não apuração. | `models.py:463-490,3074-3140` | M |
| **IPI** | **Não existe.** Só o `vIPI` lido por item. | `models.py:477,3142` | M |
| **IBS/CBS, conformidade (NFS-e)** | Existe, em modo aviso. Presença do grupo, CST × cClassTrib, alíquotas de teste de 2026, aritmética. Só para NFS-e **recebida**. | `ibscbs.py`, `views_conformidade.py`, rota `conformidade/` | M |
| **IBS/CBS, NF-e** | Só guarda a presença e o XML bruto do grupo por item; **nada é interpretado** (HI-123). Não há validador de NF-e. | `itens_nfe.py:301-356`, `models.py:3166-3169` | M |
| **IBS/CBS, apuração ou apuração assistida da CBS** | **Não existe.** | busca em `apps/fiscal` | M |
| **Livros fiscais** (entradas, saídas, apuração, inventário, termos) | **Não existe.** | busca em `apps/fiscal`; nenhuma rota | M |
| **Obrigações acessórias** (EFD ICMS/IPI, EFD-Contribuições, EFD-Reinf, DCTFWeb/MIT, DeSTDA, GIA/DIF-TO, DEFIS, PGDAS-D, DIRF) | **Não existe**, nem como conferência. | busca em `apps/fiscal` | M |
| **Relatórios de conferência** | Existem: conferência de NFS-e (recebidas × escrituradas), conferência de NF-e (W16, `vNF`), conformidade IBS/CBS, "ISS retido sofrido" e "outros municípios", "controle do limite" do Presumido. | rotas `conferencia_escrituracao`, `nfe_conferencia`, `conformidade_ibscbs`, `presumido/limite/` | M |
| **Exportação e impressão** | **Nenhum relatório fiscal exporta ou imprime.** Não há CSV, PDF nem XLSX em `apps/fiscal`; o único download é o XML original. Isso contraria o RC-94 (personalização de relatório vale para todos os módulos), pois nenhum relatório fiscal usa a identificação do emitente dos documentos imprimíveis. | busca por `text/csv`, `application/pdf` e `print` em `apps/fiscal` e `templates/fiscal`; `views_web.py:681` | M |
| **Integração contábil** | **Não existe.** `LancamentoContabil` não tem campo de origem nem de documento de origem; apenas `estorno_de`, `criado_por` e `chave_idempotencia`. O BL-72 está "planejada". Nenhum import de `apps.contabilidade` em `apps/fiscal`. | `contabilidade/models.py:2257-2346`, backlog BL-72, BL-66, BL-73, BL-74 | M |
| **Parâmetros fiscais da empresa** | Fragmentados, sem tela única. Existem `RegimeIssEmpresa`, `AtividadeEmpresa` (Simples), `AtividadePresuncaoEmpresa`, `CriterioReceitaPresumido`, `OpcaoRegimeCaixaSimples`, `FolhaFatorR`. O regime federal vem de `HistoricoRegimeTributario` em `empresas`. No cadastro de `Empresa` não achei IE, IM nem CNAE (só o campo `municipio` em `Estabelecimento`); isso é consistente com o DL-067 (D). | `models.py:1600-1950,2108-2410`, `empresas/models.py:684-811` | M |
| **Calendário de obrigações e vencimentos** | **Não existe um calendário.** Só vencimentos soltos por cálculo: quotas do Presumido, ISS retido, INSS (dia 20 "informativo"). O DAS não tem vencimento. A DL-084 traz feriados e Páscoa; hoje `presumido_calculo.py:442-510` tem `pascoa` e `datas_a_conferir`. | `presumido_calculo.py:442-563`, `retencoes.py:195`, `iss_municipal.py:991` | M |
| **Guias** (DARF, DAS, DARE, GNRE, ISS) | **Não existe** (HI-55). | busca em `apps/fiscal` | M |
| **Participantes (cadastro)** | **Não existe.** Emitente, destinatário e tomador ficam em campos do documento. | `models.py:66, 382` (só enums) | M |
| **Produtos e NCM (cadastro)** | **Não existe.** Cada item grava o próprio NCM. Há tabelas de apoio: CFOP (`dados/cfop_it2023002_v210.csv`, ~620 linhas) e NCM de combustível (`ncm_combustivel.py`). | `cfop.py`, `ncm_combustivel.py` | M |
| **Estoque e inventário** | **Não existe.** O DL-051 põe estoque e inventário dentro do Fiscal. | busca | M |
| **Permissões** | Uma matriz herdada da contabilidade (HI-21, hipótese; PE-08). CLIENTE sem acesso. | `permissoes.py:28-58` | M |
| **Painel do módulo na página inicial** | Só NFS-e: recusas, eventos sem nota, NFS-e canceladas. O banner diz "Emissão, obrigações, certificado e apuração fiscal ainda não estão disponíveis". | `module_homes.py:750-916` | M |

---

## 2. O que falta, classificado

**Classes.** (a) núcleo para o escritório do Fred, (b) importante, (c) depois. Para o risco, usei o nível do DL-067 (apuração, guia e arquivo = nível 1; importador, tela e relatório de conferência = nível 2). Tamanho: P, M ou G. A coluna "Transmissão/guia" diz se esbarra no que o produto não faz (HI-55).

### 2.1 Classe (a): núcleo para o escritório do Fred

| # | Lacuna | O que é e por que importa | Depende de | Risco | Tam. | Transmissão/guia |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | **Acumulador ou classificação versionada** | Hoje a classificação que dirige o cálculo está "em código": três catálogos fechados, com `papel`, `mercado`, `segregacao` e `atividade_presumido` apenas para receita (`models.py:2665-2700`). Falta a dimensão **imposto por imposto** (ICMS, PIS, Cofins, IPI, ISS), a **vigência**, a **conta contábil** e a **configuração por escritório ou empresa**. Sem ela, cada imposto novo (ICMS, PIS/Cofins) reabre o catálogo no código. É a decisão estrutural do DL-067 (decisão 4: "quatro peças") e do mapa funcional (FIS-07). O Fred pediu a pesquisa; o desenho precisa dela. | Pesquisa dos acumuladores (em paralelo), consulta ao contador-senior, decisão de migrar ou conviver com os `TextChoices` atuais | 1 | G | Não |
| A2 | **Escrituração de NF-e de entrada (compras e créditos)** | Sem entradas não há crédito de ICMS, PIS/Cofins nem apuração. É metade do movimento de qualquer comércio e posto. Hoje a recepção guarda a nota, e a elegibilidade a recusa. | A1 (natureza de entrada com tributação), CFOP de entrada | 1 | G | Não |
| A3 | **Apuração do ICMS-TO (próprio, ST, DIFAL, FECOEP)** | Comércio e postos do Presumido ou Simples com ICMS fora do DAS pagam ICMS no TO. É o imposto que mais pesa e mais erra no comércio. Os dados dos itens já estão guardados. Exige legislação do TO lida em fonte oficial (alíquota 20% desde 2024, FECOEP, Anexo XXI do RICMS/TO, vencimento dia 9). O DL-067 lista as pendências de benefício e DARE (D). Postos: ICMS monofásico sobre combustíveis (regra própria). | A1, A2, tabelas de ST (NCM + CEST), `cBenef` | 1 | G (dividir em ICMS próprio, depois ST e DIFAL) | Esbarra em **guia** (DARE): apurar e conferir, sem emitir |
| A4 | **PIS/Cofins do Presumido (cumulativo, 0,65% e 3%) e conferência para out a dez de 2026** | Todo cliente do Presumido tem PIS/Cofins mensal até a competência 12/2026 (D, DL-067). O produto não tem nenhum cálculo. **Há contradição de plano** entre o DL-067 (decisão 8: PIS/Cofins "congelado em 12/2026", "sem gerador novo", o arquivo continua saindo do Domínio) e o `paridade/fiscal.md` (FIS-29 a FIS-34 planejam a EFD-Contribuições inteira). O NT RFB 11/2026 que encerra a EFD-Contribuições ainda não foi lido em fonte oficial (D, DL-067:119-123). Na prática, falta uma **apuração mensal do PIS/Cofins para conferência**, base = receita da escrituração, com monofásico, ST e ICMS fora da base. | A1, leitura oficial da NT RFB 11/2026 e Leis 10.637 e 10.833, **decisão do Fred** (construir ou deixar no Domínio) | 1 | M | Esbarra em **DARF** e **DCTFWeb**: só conferência |
| A5 | **Virada de 2027** | Hoje o código recusa 2027 em quatro pontos (RBT12, pré-DAS, NF-e, caixa). Em 01/01/2027 o escritório não consegue apurar nenhum cliente do Simples nem escriturar NF-e. Conteúdo: tabelas do Simples 2027 (Res. CGSN 190/2026), IBS/CBS no DAS, regra de receita da NF-e de 2027 (NT 2026.008 e `vNF`, HI-133), CBS plena. A janela do Simples regular fecha em 15/10 e 30/10/2026; a opção pelo regime regular volta em março/2027 (D, DL-067). | Leitura oficial da Res. CGSN 190/2026 e NT 2026.008; decisão do Fred sobre ordem | 1 | G | Não |
| A6 | **Integração contábil** (lançamento gerado pela escrituração) | É o que dá valor à contabilidade já pronta (DL-067, mapa funcional, "onda 4"). Pré-requisito técnico: **BL-72**, origem e documento de origem no `LancamentoContabil` (hoje inexistente; M). Depois BL-66 (regeração controlada), BL-73 (permissão própria) e BL-74 (configuração contábil por classificação e imposto). A prévia do lançamento (FIS-18) vem antes do lote. | BL-72 (migração em `contabilidade`, nível 1), A1 (contas por natureza) | 1 | G | Não |
| A7 | **Livros fiscais: Registro de Entradas e de Saídas** | Não existem. O escritório entrega o livro e a obrigação sai dele. | A2 (entradas), A3, forma da legislação fiscal (classe "Livro" da personalização de relatório) | 1 | M | Não, mas é "arquivo/documento entregue" |
| A8 | **Mais ISS fora de Palmas** | O acervo tem 52 municípios. Hoje o cadastro aceita, mas nenhum vem pronto, e a alíquota de Palmas ainda não foi fornecida (PE-79). Não bloqueia código, mas bloqueia **uso**. | Fornecimento da tabela pelo Fred, leitura oficial de cada município | 1 | P por município, pesquisa | Não |
| A9 | **Pré-DAS comércio e indústria** (em andamento, DL-082) | Fecha o Simples do comércio. Fora do primeiro corte: 6ª faixa, excesso de sublimite, benefício estadual de ICMS, tabela de NCM monofásico, combustíveis, `NFref`, caixa e 2027. | DL-083, DL-085 | 1 | M (em curso) | Não |
| A10 | **Postos: volume, monofásico e combustíveis no Simples** | A DL-082 recusa a natureza combustível. Há posto no Presumido (DL-083, DL-085) mas, se algum for do Simples, fica sem pré-DAS. Também: tabela de NCM monofásico fora do primeiro corte (a marca é do contador, item a item, o que não escala em NFC-e de alto volume). Limite de 2.000 arquivos por envio. | A1 (marca por regra, não por item), medida de envio | 1 | M | Não |

### 2.2 Classe (b): importante

| # | Lacuna | O que é e por que importa | Depende de | Risco | Tam. | Transmissão/guia |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | **Participantes e produtos (cadastros)** | Hoje tudo é lido da nota. Para atributos fiscais com vigência (optante do Simples, contribuinte, IE) e para o crédito por produto, é preciso cadastro. O A1 pode adiar o produto se a regra for por NCM e CFOP. | A1 | 2 | M | Não |
| B2 | **Parâmetros fiscais da empresa em um lugar só** | Hoje cada DL criou o seu cadastro. Falta uma visão por empresa (regime, PIS/Cofins competência × caixa, atividades, forma de recolhimento, padrão de combustível) e a lista de pendências de cadastro, como a DL-084 prevê só para o Presumido. IE, IM e CNAE não existem no `Empresa`. | A1 | 2 | M | Não |
| B3 | **Calendário e vencimentos** | Vencimentos de DAS, DARF, ICMS, ISS e quotas dispersos. O DL-067 pede prazos por regra e painel da carteira. A DL-084 só cobre o Presumido. | B2 | 1 (prazo errado = multa), apesar de ser conferência | M | Não gera guia |
| B4 | **Exportação e impressão dos relatórios** | Nenhum relatório fiscal exporta ou imprime. O RC-94 e o RC-96 exigem a identificação do emitente e a classe do documento. | `personalizacao-de-relatorio.md`, `documentos/` | 2 | M | Não |
| B5 | **Validação de NF-e quanto ao IBS/CBS** | Regime regular exige o grupo desde 03/08/2026 (D, DL-067). Hoje só a NFS-e é validada. | Informe Técnico 2025.002 lido | 2 | M | Não |
| B6 | **Estorno de nota contabilizada e conferência de lançamentos** (FIS-15, FIS-16, FIS-20) | A conferência existe por tipo de nota. Falta a **alteração em massa** de NFS-e e tomadas (só a NF-e tem `nfe_reclassificar`) e a visão única "notas não lançadas" (FIS-17). | A1 | 2 | M | Não |
| B7 | **ISS: apuração do ISS por competência e "declaração municipal"** | Nome da declaração e vencimento de Palmas ainda a confirmar (D, DL-067:456, DL-076:69-73). | Prefeitura | 1 | P | **Guia** do WebISS: só conferência |
| B8 | **Resíduos do backlog fiscal** | BL-661 (livro-caixa na escrituração fiscal, decisão do Fred), BL-670 (atividade por nota), BL-678 a BL-688, BL-681 (painéis só contam NFS-e). Ver seção 3. | vários | 2 | M a P cada | Não |
| B9 | **CT-e e NFCom (entrada)** | O acervo tinha 9 CT-e e 69 NFCom (de um emitente). Servem para crédito de ICMS e PIS/Cofins em transporte e comunicação. | A2 | 2 | M | Não |
| B10 | **Parcelas e contas a pagar/receber** (FIS-41) | Exigidas para PIS/Cofins no regime de caixa do Presumido. O Fred disse que a maioria paga em quotas, mas o regime de caixa continua sem suporte. | Decisão sobre caixa | 1 | G | Não |

### 2.3 Classe (c): depois

| # | Lacuna | Observação |
| --- | --- | --- |
| C1 | EFD ICMS/IPI (leiaute 021) | Depende de A2, A3, A7 e de inventário. O DL-067 planeja a Onda 2 (abr a jun/2027). **Gera arquivo** que vai ao PVA; só conferência, sem transmissão. Tam. G, nível 1. |
| C2 | EFD-Reinf, DCTFWeb/MIT, DIF-TO, DEFIS, DASN-SIMEI | Vigência a confirmar em fonte oficial (D). Todas esbarram em transmissão. |
| C3 | EFD-Contribuições (gerador) | Possivelmente descontinuada após 12/2026. Aguardar leitura da NT RFB 11/2026 e a decisão do Fred. |
| C4 | Guias (DARF, DAS, DARE, GNRE, DARM) | HI-55. Só cálculo e conferência. |
| C5 | Lucro Real, Lalur e ECF | Fora do fiscal pela paridade; o DL-067 manda para LAL e CTB-52. |
| C6 | Estoque, inventário, Bloco K, CIAP, cupom fiscal/Redução Z | Segmentos especializados; o próprio DL-067 questiona a Redução Z. |
| C7 | Integração com Honorários | Depende do módulo Honorários, que não existe. |
| C8 | Captura automática (Distribuição DF-e, ADN) e cofre de certificados | Condicionada à decisão do Fred (RC-41). Infraestrutura nova de nível 1. |
| C9 | Fila em segundo plano (`django.tasks`, DE-015, BL-52) | Só se a medida da DL-085 mostrar que as partes não bastam. |

---

## 3. Inconsistências entre documentação e código

Todas medidas lendo o texto e o código; o código é a fonte.

| # | Onde | Afirmação | O que o código mostra | Tipo |
| --- | --- | --- | --- | --- |
| I1 | `docs/agents/estado.md:33` (Resumo) | Fiscal = "Recepção e consulta de NFS-e nacional" | Existem também NF-e/NFC-e, escrituração, receita, pré-DAS, ISS, tomadas e Presumido (13 migrações, 152 arquivos de teste) | M |
| I2 | `estado.md:35` | "Não existe: escrituração fiscal e apuração" | Existem escrituração e quatro apurações (seção 1) | M |
| I3 | `estado.md:134` | DL-067 "Planejada" | O plano foi integrado e a seção "Execução autônoma" (RC-164) está em execução | M |
| I4 | `estado.md:22-24,43-60` (Resumo e verificação) | "Medido em 25/09/2026", remedido em 30/09 | Muito anterior ao estado de 09/10 (linha de base 8.791 testes) | D |
| I5 | `README.md:31` | "Fiscal ... ainda não existem" | O código mostra o contrário | M |
| I6 | `README.md:54` | Fiscal "Planejado — DL-010" | Idem | M |
| I7 | `docs/projeto/paridade/fiscal.md:99-123` | "Estado atual medido (2026-09-27)": "só a recepção de NFS-e"; "NF-e detecta e recusa" | Superado por DL-072 a DL-085 | M |
| I8 | `docs/projeto/mapa-funcional-fiscal.md:188-209,303-332` | Tabelas "O que já existe" e "DataLedger" com "Não existe" em escrituração, apuração, importação de XML, classificação | Importação de XML (NFS-e e NF-e), escrituração, apuração (4 impostos) existem. "Classificação fiscal" existe em forma de catálogo de naturezas no código (não como cadastro). | M |
| I9 | `mapa-funcional-fiscal.md:325-326` | Importação "Parcial: NFS-e nacional" e "a recepção grava o documento, não o lançamento fiscal" | Há NF-e/NFC-e e lançamento fiscal (`EscrituracaoFiscal`, `EscrituracaoTomada`, `EscrituracaoNFe`) | M |
| I10 | `docs/projeto/catalogo-de-relatorios.md:57` | "Fiscal tem a recepção de NFS-e" | Idem I1 | M |
| I11 | `apps/core/module_homes.py:909-912` | Banner: "recebe e consulta XML de NFS-e nacional. ... apuração fiscal ainda não estão disponíveis" | O painel fala só de NFS-e; o produto apura. O BL-684 (2) e BL-681 (2) registram a metade do problema, mas o banner não é citado | M |
| I12 | `estado.md:158-160` | Item 16 do Próximo passo diz "duas pesquisas em paralelo" | Coerente com o pedido; sem divergência | — |
| I13 | `DL-067:188` | Roteiro: PIS/Cofins "congelado em 12/2026", sem gerador | O `paridade/fiscal.md` mantém FIS-29 a FIS-34 em escopo; o DL-067 reconhece (Divergência 5) mas **nenhum documento a resolveu** | D |
| I14 | `DL-067:1020-1034` | A tabela de execução ainda traz linhas "a numerar" (ordens 2 a 5), que viraram DL-074 a DL-076 e DL-073 | Os números existem; só a tabela não foi atualizada | D |
| I15 | `estado.md:338-345` (item 11) e linha 150 | DL-082 "planejada ... Executa depois da DL-083" | O item 15 diz que a frente A está em andamento; a ordem do item 13 é DL-083, DL-085, DL-082, DL-084. Texto parcialmente desatualizado | D |
| I16 | `DL-072:73` | "alíquota, imposto, guia; integração contábil" fora | Alíquota e imposto vieram com DL-074 a DL-076; a integração contábil segue fora | M |
| I17 | `mapa-funcional-fiscal.md:297-312` | Inventário de relatórios: "Acompanhamento e conferência ... Não existe (a consulta de NFS-e recebidas é o embrião)" | Existem seis relatórios de conferência (seção 1) | M |
| I18 | `README.md:271` | "[ ] Fiscal completo" | Coerente (está aberto) | — |
| I19 | `catalogo-de-relatorios.md` (§1 e §2) | "80 dos 120 são módulos": o próprio documento admite que o número "não é auditável" | A direção se confirma para o fiscal (nenhum livro, guia ou obrigação) | D |

**Observação de processo.** O CLAUDE.md diz que o `estado.md` é a fonte única e que o `test_documentacao_do_estado.py` reprova afirmações desmentidas. Não rodei esse teste. As frases I1, I2 e I5 convivem com o teste na `main`, o que sugere que o teste **não cobre** a descrição das capacidades do fiscal. Isso é **inferido**, não medido.

---

## 4. Sequência recomendada (DL-086 em diante)

**Premissas.** Em andamento: DL-085 (correção), DL-082 (frente A), DL-084 (planejada). A pesquisa dos acumuladores corre em paralelo e **deve chegar antes de DL-086**. Cada passo abaixo é proposta do mapa de lacunas, não decisão.

### 4.1 Antes: fechar o que está aberto

1. **DL-085**: terminar a correção e a reconferência.
2. **DL-082**: terminar o pré-DAS de comércio. Tem de sair antes da virada, e o Simples do comércio depende dela.
3. **DL-084**: rotina do Presumido (feriados, quotas, medida judicial encerrada). Nível 1 e já com decisão do Fred.

### 4.2 Depois: o que desbloqueia o resto

| Ordem | Etapa proposta | Conteúdo | Por que nesta posição |
| --- | --- | --- | --- |
| 1 | **DL-086: Revisão de documentação** (sem código, nível 3) | Corrigir I1 a I11 (estado, README, paridade, mapa funcional, catálogo, banner I11 vira correção de código pequena). Reconciliar PIS/Cofins entre DL-067 e paridade (I13). | Custa pouco e é instrução permanente do Fred ("nunca esqueça de atualizar"). Evita planejar contra mapa errado. |
| 2 | **DL-087: Desenho do acumulador** (documento e protótipo mínimo, nível 1 por tocar o modelo) | Dado o resultado da pesquisa e a consulta ao contador-senior: decidir se `CATALOGO_NATUREZA_NFE` e os outros dois viram tabela de dados com vigência, com colunas de tributo (ICMS, PIS, Cofins, IPI, ISS), conta contábil e escopo (escritório ou empresa). Pode começar com o catálogo atual como "pacote global" e **migrar sem mudar o comportamento**. | É a decisão estrutural que A2, A3, A4, A6 e B1 dependem. Fazê-la depois é refazer. |
| 3 | **DL-088: BL-72** (origem e documento de origem no lançamento contábil) | Migração em `contabilidade`; consulta nos dois sentidos; isolamento. | Pré-requisito técnico de A6. Pode correr **em paralelo** a DL-087, pois não depende do desenho do acumulador. |
| 4 | **DL-089: A5, virada de 2027, parte Simples** (tabelas, IBS/CBS no DAS, regra de receita da NF-e de 2027) | Leitura da Res. CGSN 190/2026 e NT 2026.008. | Tem prazo duro: 01/01/2027. Se a leitura oficial for longa, inicie a pesquisa antes. |
| 5 | **DL-090: A4, PIS/Cofins mensal para conferência** (Presumido cumulativo, out a dez/2026) | Só conferência. Decisão do Fred sobre construir ou não. | Prazo curto (out a dez/2026). Se o Fred decidir não construir, a etapa vira só a leitura da NT e a documentação. |
| 6 | **DL-091: A2, escrituração de NF-e de entrada** | Compras, créditos, CFOP de entrada, devolução de compra. | Depende de DL-087. |
| 7 | **DL-092 e DL-093: A3, ICMS-TO** em duas fatias (próprio; depois ST, DIFAL e FECOEP) | Leitura do RICMS-TO e Convênios; só conferência. | Depende de DL-091. É a maior lacuna para o comércio e os postos. |
| 8 | **DL-094: A6, integração contábil, fatia 1** | Prévia do lançamento (FIS-18), configuração contábil por natureza (BL-74), conferência de natureza sem conta. | Depende de DL-087 e DL-088. |
| 9 | **DL-095: A7, Livros de Entradas e de Saídas** | Classe "Livro" da personalização. | Depende de DL-091 e DL-092. |
| 10 | **DL-096 em diante**: B-itens por valor ao Fred (exportação e impressão B4; parâmetros B2; calendário B3; validação de NF-e B5; CT-e B9) | | |

### 4.3 O que fica para o Fred decidir (não decido eu)

1. PIS/Cofins: construir conferência até 12/2026 ou deixar no Domínio (I13, A4).
2. Ordem entre ICMS-TO e a virada de 2027, se houver conflito de agenda.
3. Tabela de alíquotas de Palmas e dos outros municípios (PE-79, A8).
4. BL-661: empresa em modo livro-caixa na escrituração fiscal.
5. Captura automática e cofre de certificados (C8).

### 4.4 Riscos que a ordem acima não elimina

- **A pesquisa dos acumuladores pode trazer material do sistema de referência.** A regra do `fontes-de-referencia.md` é usar sem copiar; o desenho deve ser em palavras nossas.
- **Dependência de leitura oficial.** A5, A4, A3 e A8 dependem de fontes oficiais com data (HI-54). Quando a fonte não for achada, a etapa entrega o que não depende dela e nomeia a pendência.
- **Volume dos postos.** A medida da DL-085 foi feita com dado sintético; o envio de 2.000 arquivos por vez ainda não foi medido com NFC-e (D).

---

## 5. O que verifiquei, o que inferi, o que não consegui determinar

**Verifiquei (M).**
- A lista de rotas (`urls_web.py`, `urls_api.py`) e os modelos (`models.py`, índice de classes).
- Que não há PIS/Cofins, ICMS, IPI, livro, guia, obrigação, calendário, participante, produto ou acumulador como cadastro em `apps/fiscal`.
- Que `LancamentoContabil` não tem origem.
- As recusas de 2027 e a do pré-DAS com NF-e.
- A elegibilidade da escrituração de NF-e (sem compras).
- O banner de `module_homes.py`.
- Que o menu `base.html` lista as telas da recepção, escrituração, Simples, ISS, tomadas e Presumido.

**Inferi (D).** Todo número de testes e de linha de base; o estado das correções da DL-085 e da DL-082; o conteúdo normativo (alíquotas, prazos, NT RFB 11/2026) vem dos planos e não foi conferido por mim em fonte oficial. A cópia `dl082` e a cópia `dl085d` citadas no `estado.md` **não estão neste checkout** (branch `ccr-bf4b4a55-hpqgbp`, `git status` limpo), então não medi o que elas já fazem.

**Não consegui determinar.**
- Se o `test_documentacao_do_estado.py` cobre a descrição do fiscal no Resumo do `estado.md`.
- O conteúdo do AGENTS.md §3.1 (usei o resumo do DL-067).
- Quais dos 12 relatórios fiscais do catálogo de 120 o Fred considera prioridade (o catálogo cita o número, não os nomes).
- Se algum cliente do Fred está no Simples com combustível (afeta A10).
- Qual a cobertura de testes de cada capacidade; só contei arquivos (152 em `apps/fiscal/tests`).

**Arquivos principais citados** (caminhos absolutos):
- `/home/user/DataLedger/apps/fiscal/models.py`
- `/home/user/DataLedger/apps/fiscal/urls_web.py`
- `/home/user/DataLedger/apps/fiscal/urls_api.py`
- `/home/user/DataLedger/apps/fiscal/escrituracao_nfe.py`
- `/home/user/DataLedger/apps/fiscal/pre_das.py`
- `/home/user/DataLedger/apps/fiscal/rbt12.py`
- `/home/user/DataLedger/apps/fiscal/presumido.py`
- `/home/user/DataLedger/apps/fiscal/leitor.py`
- `/home/user/DataLedger/apps/fiscal/leitor_nfe.py`
- `/home/user/DataLedger/apps/contabilidade/models.py`
- `/home/user/DataLedger/apps/core/module_homes.py`
- `/home/user/DataLedger/docs/agents/estado.md`
- `/home/user/DataLedger/docs/projeto/mapa-funcional-fiscal.md`
- `/home/user/DataLedger/docs/projeto/paridade/fiscal.md`
- `/home/user/DataLedger/docs/planos/DL-067-plano-do-modulo-fiscal.md`
