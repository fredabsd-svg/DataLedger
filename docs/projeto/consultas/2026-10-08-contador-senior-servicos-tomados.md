# Consulta ao contador-senior sobre serviços tomados e retenções — 08/10/2026

Sétima consulta do `arquiteto-senior` ao `contador-senior` (Fable), por ordem do
Fred (RC-164), antes de planejar a
[DL-078](../../planos/DL-078-servicos-tomados-e-retencoes.md). Registro integral da
resposta. Hipóteses em [requisitos.md](../requisitos.md) (HI-93 a HI-96, PE-82).

**Legislação validada até:** 08/10/2026 · **Competências de referência:** 10/2026 a 03/2027 · **Município-base:** Palmas/TO (carteira em 52 municípios) · **Grau de segurança geral:** médio-alto — LC 116, Lei 10.833, Lei 8.212, RIR/2018, Lei 9.430 e LC 123 **lidos no Planalto** hoje (via `curl` com User-Agent de navegador); XSD 1.00/1.01 da NFS-e nacional **lido** (pacote já no scratchpad da sessão, mesmo sha256 citado em `apps/fiscal/iss_nota.py:11-12`); P&R NFS-e v1.1 **lido**; Res. CGSN 140 e IN SRF 459, IN RFB 765 e IN RFB 2.110 em **cópia**; RCTM de Palmas em **cópia** (legisweb). `normas.receita.fazenda.gov.br` só devolve a casca Angular (sem texto) e o portal do SPED deu 500 — por isso as INs são *cópia* e o manual da EFD-Reinf é *secundário*.

⚠️ Tudo abaixo é **HIPÓTESE para validação do Fred**. Marcas: *lido* = texto oficial aberto hoje; *cópia* = texto íntegro em site terceiro; *secundário* = notícia/fornecedor/fórum; *não conferido* = conhecimento meu sem texto aberto hoje.

Li antes, no repositório: consulta fiscal (item 10), consulta ISS Palmas (itens 2, 6, 7) e pesquisa de leiaute IBS/CBS. **Uma correção à consulta fiscal, item 10:** ela diz que a competência das retenções federais é a do pagamento "(Reinf/DCTFWeb)". Isso vale para **IRRF e CSRF**; para o **INSS de 11%** a lei manda recolher "até o dia 20 do mês subsequente ao da **emissão** da respectiva nota fiscal" (Lei 8.212, art. 31, red. Lei 11.933/2009 — *lido*). São três relógios diferentes, detalhados no item 4.

---

## 1. Naturezas de serviço tomado e a data de competência

**Resposta curta.** Catálogo de **7 naturezas** de entrada, escolhidas pelo contador (mesmo desenho da DL-067/DL-072), com a leitura automática só **sugerindo** a natureza a partir de `tpRetISSQN`, `cLocIncid`, `opSimpNac`, tipo de documento do prestador e `tpEmit`:

| # | Natureza (entrada) | Sinal no XML (sugestão, não decisão) | Efeito no primeiro corte |
| --- | --- | --- | --- |
| T1 | Tomado — **ISS retido pelo cliente tomador** | `tpRetISSQN = 2` e `cLocIncid` = município do cliente (E0031 garante isso) | Gera linha "ISS retido a recolher" por município/competência (item 2) |
| T2 | Tomado — ISS do prestador (sem retenção) | `tpRetISSQN = 1` | Só despesa; nada a recolher de ISS |
| T3 | Tomado — prestador de **outro município**, ISS devido no local do tomador, **sem** destaque de retenção | `tpRetISSQN = 1`, município do prestador ≠ município do cliente, `cTribNac` nas exceções do art. 3º da LC 116 | **Aviso** "responsabilidade possível sem destaque"; nenhum cálculo (ver CNES/RANFS de Palmas no item 2) |
| T4 | Tomado do **exterior** (importação de serviço) | `tpEmit = 2` + `cMotivoEmisTI = 1` (XSD 1.01 :776-788) | **Fora do corte**: o Emissor Nacional ainda não permite `tpEmit = 2` (P&R 7.8); não haverá XML. Registrar como pendência |
| T5 | Tomado de **MEI** | `opSimpNac = 2` | Despesa; avisos de retenção indevida (item 3) |
| T6 | Tomado de **ME/EPP do Simples** | `opSimpNac = 3` (+ `regApTribSN`) | Despesa; ISS retido possível (alíquota do Simples); avisos de CSRF/IRRF indevidos |
| T7 | Tomado de **pessoa física** (prestador CPF) | `prestador_tipo_documento = CPF` | Despesa; campos federais vêm vazios por regra E0675; retenções (IRRF tabela, INSS 11% do contribuinte individual) **fora do corte**, só aviso |

**NORMA.**
- Fato gerador do ISS = prestação; incide também sobre serviço "proveniente do exterior do País ou cuja prestação se tenha iniciado no exterior" (LC 116, art. 1º, caput e § 1º — *lido*). Responsáveis: tomador de serviço do exterior (art. 6º, § 2º, I); PJ tomadora nos subitens 3.05, 7.02, 7.04, 7.05, 7.09, 7.10, 7.12, 7.16, 7.17, 7.19, 11.02, 17.05 e 17.10 (art. 6º, § 2º, II, red. LC 183/2021 — **atenção**: 7.14 e 7.15 saíram da lista na redação vigente, a consulta anterior os listou pela redação antiga); § 4º do art. 3º (inc. III); cartões 15.01 (inc. IV) — *lido*.
- Simples como **tomador**: o DAS "não exclui a incidência" do ISS devido "em relação aos serviços sujeitos à substituição tributária ou retenção na fonte" e "na importação de serviços" (LC 123, art. 13, § 1º, XIV, "a" e "b" — *lido*). Ou seja, o tomador do Simples **retém e recolhe ISS normalmente**.
- Simples como **prestador**: LC 123, art. 21, § 4º, I a VI (*lido*) e Res. CGSN 140, art. 27, I a VII (*cópia*) — ver item 2.
- Competência do ISS retido: "no mesmo mês do fato gerador, independentemente do resultado financeiro ou do pagamento" (RCTM Palmas, Decreto 1.667/2018, art. 145 — *cópia*); regime de caixa só para órgãos públicos (art. 146).
- `dCompet` = data de competência da prestação (P&R 23.1; já no modelo em `apps/fiscal/models.py:165`).

**Data que define a competência.** Para a **escrituração fiscal e para o ISS retido: `dCompet`**. Para a **despesa contábil: competência (`dCompet`)**. Para as **retenções federais: três datas distintas** (item 4). Guardar, como já recomendado, `dhEmi`, `dCompet` e data de escrituração, e **acrescentar um campo opcional "data de pagamento (informada)"**.

**O que muda por regime do tomador.**
- **Presumido e Real**: retêm IRRF (RIR arts. 714, 716, 718 — *lido*) e CSRF 4,65% (Lei 10.833, arts. 30–31 — *lido*); retêm INSS 11% se cessão de mão de obra/empreitada (Lei 8.212, art. 31 — *lido*). Real ainda apropria crédito de PIS/Cofins sobre serviços tomados — **fora do escopo** (DL-067).
- **Simples**: **não** retém CSRF ("Não estão obrigadas a efetuar a retenção... as pessoas jurídicas optantes pelo SIMPLES", Lei 10.833, art. 30, § 2º — *lido*). **Retém ISS** (art. 13, § 1º, XIV) e **retém INSS 11%** quando contratante por cessão/empreitada (IN RFB 2.110, art. 133 — *cópia*). **IRRF**: não encontrei dispensa para o Simples como **fonte pagadora** a PJ não optante; o art. 13, § 1º, XI só trata de pagamentos a pessoas físicas. **Inferência**: o tomador do Simples retém IRRF 1,5%/1% quando paga PJ não optante por serviço do art. 714/716/718. Grau médio — levar ao Fred como pergunta de rotina, não como norma pronta.

**Grau de segurança:** alto no catálogo e nas normas; médio no IRRF do tomador Simples.

## 2. ISS retido pelo tomador — apuração e vencimento

**Resposta curta.** **Sim**: o produto apura o "ISS retido a recolher" do cliente tomador pela **soma de `vISSQN` das notas com `tpRetISSQN = 2`**, agrupada por `cLocIncid` e por mês de `dCompet`. Não recalcula alíquota: em Palmas, na retenção "prevalecem os valores de ISS apurados na nota fiscal de serviços, cabendo [ao prestador] a responsabilidade pela veracidade das informações" (RCTM, art. 148 — *cópia*). Palmas: **dia 15** do mês seguinte (Anexo I, "retenção/substituição"), rolando para o 1º dia útil seguinte (art. 86, § 3º). A saída é **conferência da DAM**, não guia: o DAM é gerado no WebISS "por nota ou por grupo de NFS-e" pelo "tomador responsável" (art. 214, § 2º — *cópia*).

**NORMA.**
- LC 116, art. 6º, § 1º: responsáveis recolhem integralmente "independentemente de ter sido efetuada sua retenção na fonte" (*lido*).
- RCTM arts. 141 (indicados **devem** reter; substitutos/solidários **podem**), 143 (substituto recolhe mesmo sem ter retido), 145 (mês do FG), 148 (prevalece a nota), 214 (DAM), **215** (responsável responde ao tomar serviço de empresas "sediadas ou não neste Município"), **216** (não recolher o retido "constitui apropriação indébita") — *cópia*.
- **Novidade relevante para a natureza T3 (achada hoje):** RCTM arts. **218–222** — prestador de fora de Palmas que emite nota para tomador em Palmas deve inscrever-se no **CNES**; se não estiver inscrito, o imposto "será automaticamente gerado para o tomador do serviço como retenção tributária" (art. 219, § 3º); o tomador em Palmas deve exigir o **RANFS** (art. 220), emitir se o prestador não emitir (§ 4º) e aceitar/rejeitar "até o dia 5 do mês seguinte à sua emissão" (art. 222, § 1º), com aceitação tácita depois (§ 2º) — *cópia*. **Inferência**: isso se aplica a notas de prestadores de fora **não** convertidas pelo WebISS; se e como se aplica a uma NFS-e nacional de outro município que chega via ADN eu **não determinei**. Produto: aviso informativo "prestador de outro município — verificar CNES/RANFS (RCTM arts. 218–222)" para cliente estabelecido em Palmas, sem cálculo.
- Tomador do **Simples** retém: LC 123, art. 13, § 1º, XIV, "a" (*lido*); nada no RCTM arts. 141–148 excepciona o tomador optante (*cópia*, texto lido nos dois trechos). **Não muda nada** na apuração.
- Prestador do **Simples** (`opSimpNac = 3`): retenção só nas hipóteses dos arts. 3º e 6º da LC 116; alíquota da nota = "alíquota efetiva de ISS a que a ME ou EPP estiver sujeita no mês anterior ao da prestação" (LC 123, art. 21, § 4º, I, red. LC 155/2016 — *lido*; Res. 140, art. 27, I, com RBT12 "que antecederem o mês anterior" — *cópia*); 2% no mês de início (inc. II); **5% se a nota não informar a alíquota** (inc. V); **sem retenção** se ISS por valor fixo, "salvo quando o ISS for devido a outro Município" (Res. 140, art. 27, IV); retido recolhido é definitivo (inc. VII). O prestador continua responsável pela diferença se informou alíquota menor (inc. VI).
- **Ponto de atenção:** a consulta fiscal (item 3) registrou que, para Simples com `regApTribSN = 1`, o ISS "não aparece destacado na nota" (P&R 20.2). Se isso valer também quando `tpRetISSQN = 2`, haverá nota retida **sem `vISSQN`**. Nesse caso o produto **não** soma zero nem aplica 5%: lista a nota como "retida sem valor destacado — conferir" (mesmo princípio de `iss_nota.py`: ausente ≠ zero).

**Vencimento em outros municípios.** **Não listo** — não li lei de nenhum dos outros 51 e a regra do projeto proíbe inventar prazo. Parametrizar "vencimento do ISS retido" por município com vigência e fonte; sem parâmetro, mostrar "vencimento não parametrizado".

**Grau de segurança:** alto (Palmas); CNES/RANFS × NFS-e nacional não determinado.

## 3. Retenções federais na nota — campos, primeiro corte e avisos

**Caminhos exatos (XSD lido; linhas do elemento em `tiposComplexos_v1.01.xsd` | `v1.00.xsd`; namespace `http://www.sped.fazenda.gov.br/nfse`; todos `minOccurs="0"`, inclusive o próprio `tribFed`).** Prefixo: `NFSe/infNFSe/DPS/infDPS/valores/trib/`

| Tag | 1.01 | 1.00 | Tipo | Documentação literal do XSD |
| --- | --- | --- | --- | --- |
| `tribFed` | :1645 | :1249 | `TCTribFederal` | "Grupo de informações de outros tributos relacionados ao serviço prestado" |
| `tribFed/piscofins` | :1989 | :1605 | `TCTribOutrosPisCofins` | grupo PIS/COFINS |
| `tribFed/piscofins/CST` | :2022 | :1639 | `TSTipoCST` | CST PIS/COFINS (00, 01–09, 49–75, 98, 99) |
| `tribFed/piscofins/vBCPisCofins` | :2063 | :1680 | `TSDec15V2` | "Base de Cálculo do PIS/COFINS, relativo à **apuração própria**" |
| `tribFed/piscofins/pAliqPis` / `pAliqCofins` | :2070 / :2077 | :1687 / :1694 | `TSDec2V2` | alíquotas, apuração própria |
| `tribFed/piscofins/vPis` / `vCofins` | :2084 / :2091 | :1701 / :1708 | `TSDec15V2` | "Valor do **débito** de PIS/COFINS **apuração própria**" (já lidos em `apps/fiscal/ibscbs.py:132-133`) |
| `tribFed/piscofins/tpRetPisCofins` | :2098 | :1715 | `TSTipoRetPISCofins` | 0 não retidos; 1 PIS/COFINS retidos; 2 PIS/COFINS não retidos; 3 PIS/COFINS/CSLL retidos; 4 PIS/COFINS retidos, CSLL não; 5 PIS retido, COFINS/CSLL não; 6 COFINS retido, PIS/CSLL não; 7 PIS não, COFINS/CSLL retidos; 8 PIS/COFINS não, CSLL retido; 9 COFINS não, PIS/CSLL retidos |
| `tribFed/vRetCP` | :1996 | :1612 | `TSDec15V2` | "Valor monetário do CP (R$)" |
| `tribFed/vRetIRRF` | :2003 | :1619 | `TSDec15V2` | "Valor monetário do IRRF (R$)" |
| `tribFed/vRetCSLL` | :2010 | :1626 | `TSDec15V2` | "Valor monetário do CSLL (R$)" |

**Achado decisivo (P&R v1.1, itens 13.1 e 13.2 — *lido*):** desde a **NT SE/CGNFS-e 007/2026 (vigente 09/02/2026)**, quando o tomador retém PIS, COFINS e/ou CSLL, "os três valores devem ser somados e lançados exclusivamente" em **`vRetCSLL`**, com `tpRetPisCofins = 3`; `vPis`/`vCofins` são **débito próprio do prestador** e "nunca são descontados do valor líquido". Fórmula oficial: **`vLiq = vServ − vDescIncond − vDescCond − vTotalRet`, onde `vTotalRet = vRetCP + vRetIRRF + vRetCSLL + vISSQN (se retido)`**. Consequências para o produto:
1. **Não é possível separar PIS, COFINS e CSLL** a partir da nota. Totalizar como **"CSRF retida (PIS+COFINS+CSLL)"**, com `tpRetPisCofins` como qualificador exibido.
2. "CP" em `vRetCP` não é explicado pelo XSD; **inferência forte**: contribuição previdenciária retida (Lei 8.212, art. 31), confirmada indiretamente pelo P&R 11.1 ("IRRF/INSS/CSLL/PIS/COFINS").
3. Notas de **Palmas** chegam ao ADN convertidas do ABRASF (que tem ValorPis, ValorCofins, ValorInss, ValorIr, ValorCsll separados). **Não determinei** como o WebISS mapeia isso para `vRetCSLL`/`vPis`/`vCofins`. O leitor deve tolerar `vPis`/`vCofins` preenchidos junto com `tpRetPisCofins` de retenção e **marcar como ambíguo**, nunca somar os dois.
4. Prestador **CPF**: regra **E0675** bloqueia todos os campos de `tribFed`; MEI: **E0676** (P&R 11.1 — *lido*). Ausência não é "sem retenção".

**Primeiro corte: sim, só listar e totalizar o destacado**, por tributo (ISS retido, CSRF, IRRF, CP) e por competência, **sem recalcular alíquota e sem decidir se a retenção era devida**. Motivo normativo: a base das retenções federais é "o montante a ser pago"/"importâncias pagas ou creditadas" (Lei 10.833, art. 31; RIR art. 714), que a nota não conhece; e as hipóteses de incidência dependem de fatos fora do XML (cessão de mão de obra, anexo do Simples, isenções).

**Avisos simples e seguros** (todos nível "aviso", nunca bloqueio):

| # | Aviso | Fundamento | Marca |
| --- | --- | --- | --- |
| A1 | `vLiq` ≠ fórmula do P&R 13.2 (tolerância R$ 0,01) | P&R 13.2 | *lido* |
| A2 | `tpRetPisCofins` indica retenção (1, 3–9) e `vRetCSLL` ausente/zero, ou o inverso | P&R 13.1 | *lido* |
| A3 | Prestador `opSimpNac` = 2 ou 3 **e** (`vRetCSLL` > 0 ou `vRetIRRF` > 0): "retenção provavelmente indevida" | Lei 10.833, art. 32, III (*lido*); IN RFB 765/2007, art. 1º (*cópia*); IN SRF 459, art. 3º, II (*cópia*) | — exceto se `regApTribSN = 3` (federais por fora do SN) — **inferência** |
| A4 | Cliente **tomador** optante do Simples e `vRetCSLL` > 0: "tomador do Simples não retém CSRF" | Lei 10.833, art. 30, § 2º | *lido* |
| A5 | `vRetCSLL` > 0 e ≤ R$ 10,00; `vRetIRRF` > 0 e ≤ R$ 10,00: "abaixo do mínimo de dispensa" | Lei 10.833, art. 31, § 3º, red. Lei 13.137/2015 (*lido*; **o limite de R$ 5.000 está revogado**, § 4º revogado); Lei 9.430, art. 67 / RIR art. 785 | *lido* |
| A6 | `vRetCP` > 0 e prestador `opSimpNac = 3`: "INSS 11% sobre optante só se Anexo IV" | IN RFB 2.110, arts. 166–167 (*cópia*); LC 123, art. 18, § 5º-C (*não conferido hoje* — o grep do texto do Planalto não achou a âncora) | *cópia* |
| A7 | `vRetCP` > 0: informativo "só cabe em cessão de mão de obra/empreitada (serviços dos arts. 111–112 da IN 2.110); não se aplica a empreitada total e transporte de cargas (art. 114)" | Lei 8.212, art. 31, §§ 3º–4º (*lido*); IN 2.110 arts. 111–114 (*cópia*) | mapeamento `cTribNac` → arts. 111/112 **não é oficial**; não automatizar no primeiro corte |
| A8 | Prestador CPF ou MEI com `tribFed` vazio: "retenções, se houver, foram calculadas fora da nota" | P&R 11.1 (E0675/E0676) | *lido* |

**Não recomendo** no primeiro corte: conferir percentual (4,65%, 1,5%, 1%) sobre `vServ` — a base legal é o valor pago, há exclusões (RIR art. 718, § 1º) e isenções parciais (Lei 10.833, art. 31, § 2º); a divergência geraria falso positivo.

**Grau de segurança:** alto nos caminhos e na agregação em `vRetCSLL`; médio nos avisos A3/A6/A7 (dependem de dado que a nota não traz).

## 4. Competência das retenções federais sem contas a pagar

**Resposta curta.** Três relógios, todos *lidos*:
- **IRRF** (serviços PJ): incide sobre importâncias "**pagas ou creditadas**" (RIR arts. 714, 716, 718). Crédito contábil pode anteceder o pagamento — é a controvérsia clássica; o produto **não decide**.
- **CSRF**: "pagamentos efetuados" (Lei 10.833, art. 30); recolhimento "até o último dia útil do segundo decêndio do mês subsequente àquele mês em que tiver ocorrido o **pagamento**" (art. 35, red. Lei 13.137/2015; RIR art. 722) — na prática dia 20 ou o dia útil anterior (**inferência de calendário**).
- **INSS 11%**: recolher "até o dia 20 do mês subsequente ao da **emissão** da respectiva nota fiscal ou fatura, ou até o dia útil imediatamente anterior se não houver expediente bancário" (Lei 8.212, art. 31, red. Lei 11.933/2009 — *lido*; IN 2.110, art. 123 — *cópia*). Aqui a nota **basta**: a competência é `dhEmi`.
- Prazo do **IRRF** sobre serviços PJ: Lei 11.196/2005, art. 70, I, "e" (último dia útil do 2º decêndio do mês seguinte ao FG) — **não conferido hoje** (o texto que extraí do Planalto mostrou só a parte alteradora).
- **DCTFWeb**: último dia útil do mês seguinte (IN RFB 2.237/2024, art. 6º — *secundário*, consulta anterior). **EFD-Reinf R-4020**: campo `dtFG` = data do pagamento/crédito — *secundário* (fórum SPED Brasil, manuais de fornecedor); portal SPED indisponível hoje.

**Tratamento no produto (recomendação).**
1. Campo opcional **"data de pagamento informada"** na nota tomada (manual, com trilha). Sem ele, a retenção fica em estado **"destacada — competência federal pendente de data de pagamento"**, visível no relatório; **nunca** presumir pagamento = emissão nem = competência.
2. Para `vRetCP`, apurar por **mês de `dhEmi`** (lei), com vencimento dia 20 informativo.
3. Para IRRF/CSRF, agrupar por data de pagamento **quando informada**; sem data, listar em "a classificar", com aviso de que DCTFWeb/Reinf exigirão a data.
4. Prazos só como texto informativo, com a fonte ao lado; nenhuma geração de DARF, Reinf ou DCTFWeb.

**Grau de segurança:** alto na norma; médio na prática Reinf.

## 5. Lançamento contábil automático da nota tomada

**Resposta curta.** **Fora do primeiro corte, mas desenhado para o segundo.** Verifiquei que a escrituração das prestadas (DL-072) **não gera lançamento contábil** hoje (`apps/fiscal/escrituracao.py` não referencia lançamento/contábil; o plano DL-072 só registra "fica fora" para tomadas, linha 69). Criar integração contábil pela **entrada** antes da **saída** inverteria a ordem e duplicaria regra.

**Recomendação para quando entrar:** gerar **rascunho** (estado distinguível, como já existe em `EstadoEscrituracao`) com partidas: D Despesa (conta por natureza T1–T7, parametrizada pelo escritório) pelo **bruto** (`vServ − vDescIncond`); C Fornecedor pelo **líquido** (`vLiq`); C "ISS retido a recolher" (`vISSQN` se `tpRetISSQN = 2`); C "CSRF a recolher" (`vRetCSLL`); C "IRRF a recolher" (`vRetIRRF`); C "INSS retido a recolher" (`vRetCP`). Fecha por construção com a fórmula do P&R 13.2 — se A1 falhar, não gera rascunho. O contador confirma; nunca efetivar automático. Plano de contas das retenções: **pendência para o Fred**.

**Grau de segurança:** alto (decisão de produto).

## 6. Fora do primeiro corte e pendências para o Fred

**Fora, com segurança:** importação de serviço (T4; sem XML, mais PIS/Cofins-Importação, IRRF-remessa e CIDE — *não conferido*); notas ABRASF não nacionais e RANFS/CNES de Palmas (só aviso); crédito de PIS/Cofins no Lucro Real; cálculo de retenção devida ou de alíquota; geração de DAM/DARF; EFD-Reinf e DCTFWeb; contas a pagar; cliente como **intermediário** (`tpRetISSQN = 3` do lado de quem retém); prestador pessoa física (RPA, IRRF tabela, INSS do contribuinte individual); CPP de 20% sobre MEI contratado (LC 123, art. 18-B — *não conferido hoje*); lançamento contábil (item 5); substituição/cancelamento de nota tomada.

**Pendências para o Fred (rotina do escritório dele):**
1. Quem emite a DAM do ISS retido no WebISS — o escritório ou o cliente — e se por nota ou agrupada (RCTM art. 214, § 2º).
2. Clientes tomadores do Simples em Palmas: o WebISS marca a retenção automaticamente ou o cliente escolhe?
3. Como o escritório recebe a **data de pagamento** das notas tomadas (há algum controle de contas a pagar nos clientes?).
4. Quais clientes tomam serviços com **INSS 11%** (construção, limpeza, vigilância) e quem calcula hoje.
5. Rotina atual de CNES/RANFS para prestadores de fora de Palmas.
6. **Amostra de XML** (anonimizada) de nota tomada de Palmas com retenções federais, para ver como o WebISS preenche `vRetCSLL` × `vPis`/`vCofins` × `tpRetPisCofins`.
7. Contas contábeis padrão para despesa por natureza e para as quatro retenções a recolher.
8. Se o escritório retém IRRF quando o cliente do Simples paga PJ não optante (item 1, inferência).

---

## Tabela-resumo

| # | Tema | Resposta | Fonte principal | Marca | Segurança |
| --- | --- | --- | --- | --- | --- |
| 1 | Naturezas e data | 7 naturezas (T1–T7) sugeridas pelo XML, escolhidas pelo contador; `dCompet` para ISS e despesa; Simples tomador retém ISS/INSS, não CSRF | LC 116 arts. 1º, 3º, 6º; LC 123 arts. 13 §1º XIV, 21 §4º; Lei 10.833 art. 30 §2º; RCTM art. 145 | lido / cópia | Alta; média (IRRF do tomador Simples) |
| 2 | ISS retido pelo tomador | Soma de `vISSQN` com `tpRetISSQN = 2` por `cLocIncid`/`dCompet`; Palmas dia 15; conferência da DAM; aviso CNES/RANFS; outros municípios só parametrizados | RCTM arts. 141–148, 214–222, Anexo I; Res. 140 art. 27 | cópia | Alta (Palmas) |
| 3 | Campos federais | `infDPS/valores/trib/tribFed/{vRetCP, vRetIRRF, vRetCSLL, piscofins/...}`; desde NT 007/2026 PIS+COFINS+CSLL retidos vão **somados em `vRetCSLL`**; `vPis`/`vCofins` = débito próprio; listar/totalizar sem recalcular; 8 avisos | XSD 1.00/1.01; P&R 11.1, 13.1, 13.2; Lei 10.833 arts. 30–32; IN 765; IN 2.110 arts. 166–167 | lido / cópia | Alta (campos); média (avisos A3, A6, A7) |
| 4 | Competência federal | IRRF: pago ou creditado; CSRF: pagamento (vence 2º decêndio seguinte); INSS 11%: **emissão** (dia 20 seguinte); sem data de pagamento → "pendente", nunca presumir | RIR arts. 714, 722, 785; Lei 10.833 arts. 30, 35; Lei 8.212 art. 31 | lido | Alta |
| 5 | Lançamento contábil | Fora do primeiro corte; depois, rascunho que fecha pela fórmula do `vLiq` | Repositório (DL-072 não gera contábil) | verificado | Alta |
| 6 | Fora do corte / pendências | Importação, RANFS, Real, cálculo de retenção, guias, Reinf/DCTFWeb, PF, MEI 20%, contábil; 8 perguntas ao Fred | — | — | — |

## O que verifiquei, o que inferi, o que não consegui determinar

**Verificado (texto aberto hoje).** LC 116 arts. 1º, 2º, 3º (caput), 6º, 7º; Lei 10.833 arts. 30–36; Lei 8.212 art. 31 (todas as redações); RIR/2018 arts. 714–718, 721 §3º, 722, 785; Lei 9.430 arts. 64, 67; LC 123 arts. 13, 18 §4º-A, 21 §4º — Planalto. XSD 1.00 e 1.01 (grupo `tribFed`, `tpRetPisCofins`, `tpEmit`, `cMotivoEmisTI`, `TSOpSimpNac`, `TSRegimeApuracaoSimpNac`). P&R NFS-e v1.1 itens 6.6, 7.8, 11.1, 11.2, 13.1, 13.2. Repositório: `apps/fiscal/iss_nota.py`, `apps/fiscal/models.py:131-243, 358-410`, `apps/fiscal/ibscbs.py:132-133`, `apps/fiscal/escrituracao.py`, `docs/planos/DL-072...md:69`. **Cópias íntegras:** Res. CGSN 140 art. 27 (PDF guiatributario); RCTM Palmas arts. 141–148, 195–196, 204, 214–224 (legisweb, em três janelas); IN SRF 459 arts. 1º–9º e IN RFB 765 (legisweb, resumo); IN RFB 2.110 arts. 108–123, 133, 164–171 (legisweb, resumo).

**Inferido.** `vRetCP` = INSS retido (Lei 8.212 art. 31); tomador do Simples retém IRRF de PJ não optante; "último dia útil do 2º decêndio" ≈ dia 20 ou útil anterior; CNES/RANFS não se aplicam (ou se aplicam de outro modo) a NFS-e nacional via ADN; `regApTribSN = 3` afasta o aviso A3; mapeamento de `cTribNac` para os arts. 111/112 da IN 2.110.

**Não determinado.** (1) Como o WebISS de Palmas converte os campos ABRASF de retenção para `vRetCSLL`/`vPis`/`vCofins` — precisa de XML real. (2) Se nota retida de prestador Simples (`regApTribSN = 1`) traz `vISSQN`. (3) Texto do art. 70, I, "e" da Lei 11.196 (prazo IRRF). (4) LC 123 art. 18 § 5º-C e art. 18-B (não localizados no texto convertido). (5) Manual da EFD-Reinf (dtFG) em fonte oficial — portal SPED 500. (6) Textos oficiais das INs (normas.receita sem renderização). (7) Vencimento do ISS retido nos outros 51 municípios. (8) Valor do "limite mínimo" do art. 115, I, da IN 2.110.

Sources:
- [LC 116/2003 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm)
- [Lei 10.833/2003 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/2003/l10.833.htm)
- [Lei 8.212/1991 consolidada — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l8212cons.htm)
- [Decreto 9.580/2018 (RIR) — Planalto](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/decreto/D9580.htm)
- [Lei 9.430/1996 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/l9430.htm)
- [LC 123/2006 — Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm)
- [Lei 13.137/2015 — Planalto](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13137.htm)
- [Lei 11.196/2005 — Planalto (art. 70 não conferido)](https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2005/lei/l11196.htm)
- [XSD NFS-e v1.01 (pacote com 1.00 e 1.01) — gov.br/nfse](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/nfse-esquemas_xsd-v1-01-20260209.zip)
- [Perguntas e Respostas NFS-e v1.1 (22/09/2026) — gov.br/nfse](https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-e-respostas-nfs-e-v-1-1-20260922.pdf)
- [Res. CGSN 140/2018 consolidada — cópia guiatributario](https://guiatributario.net/wp-content/uploads/2026/08/resolucao140.pdf)
- [Decreto 1.667/2018 Palmas (RCTM) — legisweb](https://www.legisweb.com.br/legislacao/?id=375471)
- [IN SRF 459/2004 — legisweb](https://www.legisweb.com.br/legislacao/?id=75965)
- [IN RFB 765/2007 — legisweb](https://www.legisweb.com.br/legislacao/?id=77206)
- [IN RFB 2.110/2022 — legisweb](https://www.legisweb.com.br/legislacao/?id=437340)
- [IN RFB 2.110/2022 — legjur (403 hoje)](https://www.legjur.com/legislacao/htm/out_2404202400021102022)
- [EFD-Reinf R-4020 dtFG — fórum SPED Brasil (secundário)](https://portalspedbrasil.com.br/?p=13737)
- [EFD-Reinf série R-4000 — Econet (secundário)](https://blog.econeteditora.com.br/efd-reinf-serie-r-4000.md)
- [Retenção INSS Simples Anexo IV — Portal Contnews (secundário)](https://www.portalcontnews.com.br/retencao-de-inss-do-simples-nacional-para-o-anexo-iv)
- [IN RFB 2.289/2025 e cessão de mão de obra — COAD (secundário)](https://coad.com.br/home/noticias-detalhe/139607/orientacao-contribuicao-cessao-de-mao-de-obra)
- [ME/EPP dispensadas de retenção — COAD (secundário)](https://www.coad.com.br/home/noticias-detalhe/10584/me-e-epp-ficam-dispensadas-da-retencao-de-ir-e-contribuicoes)
- Não alcançados hoje: [normas.receita (IN 459)](http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=15367) · [normas.receita (IN 2.110)](http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=126757) · [portal SPED EFD-Reinf](http://sped.rfb.gov.br/pagina/show/2135)
