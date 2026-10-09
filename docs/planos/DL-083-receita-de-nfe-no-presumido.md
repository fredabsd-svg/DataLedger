# DL-083 — Fiscal: receita de NF-e no Lucro Presumido e regras de receita da RC-172

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170), com as
respostas delegadas da RC-172. Continua o roteiro do
[DL-067](DL-067-plano-do-modulo-fiscal.md) depois da escrituração das NF-e
([DL-081](DL-081-escrituracao-das-nfe-de-saida.md)). **Executa antes da
[DL-082](DL-082-pre-das-de-comercio-e-industria.md)**, porque a regra de
receita do item muda aqui e o pré-DAS de comércio a usa.
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1): muda a receita
bruta do Simples, o RBT12 e a base do IRPJ e da CSLL. A auditoria
independente faz uma rodada, uma correção e uma reconferência.

**É conferência, nunca transmissão.** O produto não gera DARF, DCTFWeb nem
ECF.

## Base

[Consulta ao contador-senior sobre as PE-83 a PE-85](../projeto/consultas/2026-10-09-contador-senior-pe83-pe84-pe85.md),
de 09/10/2026, com a delegação do Fred (RC-172):

- PE-85.3: a receita de NF-e entra no Presumido "agora". Enquanto não entra,
  todo cliente do Presumido com NF-e fica parcial o ano inteiro.
- PE-85.5: os dois bloqueios conservadores da DL-081 saem, e a fórmula do
  MOC 7.0 os substitui. O MOC 7.0 (Anexo I, I17b e W07-10 a W16-10) foi lido
  em 09/10/2026.
- PE-85.1: a natureza "combustível" se divide pela operação (Lei 9.249,
  art. 15, § 1º, I, lida; SC Cosit 25/2023, em cópia).
- PE-84.4: a NT 2026.008 não diz como fica o `vNF` em 2027.

Hipóteses: HI-118, HI-119, HI-122 e HI-133 a HI-134 (RC-172).

## Escopo

1. **Uma função única de receita do item** (HI-119 complementada). Toda soma
   de receita de NF-e passa por ela: conferência, efetivação, composição do
   mês, segregação, RBT12 e Presumido.
   - item `indTot` 1: `vProd − vDesc − vICMSDeson (só se indDeduzDeson = 1) + vFrete + vSeg + vOutro`;
   - item `indTot` 0: `− vDesc − vICMSDeson (idem) + vFrete + vSeg + vOutro`.
     O `vProd` não foi cobrado.

   **Decisão do arquiteto:** o campo gravado `receita_bruta_item` não muda e
   a versão do leitor não sobe. Subir a versão deixaria sem saída a nota
   estornada (R3 da [reconferência da DL-081](../auditorias/2026-10-09-dl-081-reconferencia.md),
   BL-686). As notas que os dois bloqueios barravam nunca foram efetivadas,
   então nenhum valor gravado muda de sentido. O campo passa a ser
   documentado como "valor bruto do item", e não como "receita".
2. **Os dois bloqueios saem**: `MENSAGEM_ITEM_FORA_DO_TOTAL` e
   `MENSAGEM_ICMS_DESONERADO_DEDUZIDO`. A conferência W16 continua com
   tolerância zero, agora somando a receita de **todos** os itens.
3. **Item fora do total.** O valor cobrado num item `indTot` 0 segue a
   natureza do item.
   - Se a natureza não é de receita e há valor cobrado positivo (frete,
     seguro ou outras despesas acima do desconto), a efetivação recusa com o
     motivo nomeado "item fora do total com valor cobrado: escolha uma
     natureza de receita". Frete cobrado é receita (HI-119), e deixá-lo
     escapar paga a menos.
   - A memória e a tela avisam: "item n fora do total: vProd R$ X não compõe
     a receita".
4. **ICMS desonerado deduzido.** A memória mostra a linha "ICMS desonerado
   deduzido do total: R$ X". Com `indDeduzDeson` 0 ou ausente, nada se
   deduz. Fecha o item 1 do BL-685.
5. **Combustível em duas naturezas** (HI-118):
   - `combustivel` passa a significar "revenda de combustíveis para
     consumo", com 1,6% no IRPJ;
   - `combustivel_revenda` é a natureza nova, "revenda de combustíveis para
     revenda", com 8% no IRPJ;
   - a CSLL fica em 12% nas duas.

   A sugestão pelo CFOP só existe quando a descrição oficial na tabela de
   CFOP do repositório (`apps/fiscal/cfop.py`) confirma o caso; sem
   confirmação, não há sugestão. O padrão por empresa fica na
   [DL-084](DL-084-rotina-do-presumido.md).
6. **Receita de 2027 bloqueada** (HI-133). A efetivação de nota com `dhEmi`
   em 2027 ou depois recusa com o motivo "regra de receita de 2027 pendente:
   NT 2026.008 e vNF".
7. **Receita de NF-e no Presumido** (HI-134):
   - **atividade de presunção pela natureza do item:**
     - revenda, produção própria, revenda com ST, substituto, monofásico,
       exportação direta e comercial exportadora vão para comércio e
       indústria;
     - `combustivel` vai para a revenda de combustíveis (1,6%);
     - `combustivel_revenda` vai para comércio e indústria (8%);
     - a tabela de mapeamento mora num lugar só, ao lado do catálogo de
       naturezas, e o texto livre `atividade_presumido` deixa de ser a fonte;
   - **trimestre** pelo mês de `dhEmi`, como a competência da escrituração;
   - **devolução:**
     - deduz no trimestre da devolução (Lei 9.430, art. 25, I), na
       atividade de comércio e indústria;
     - se o CFOP do item, na tabela oficial, for de devolução de
       combustível, a apuração recusa com o motivo "devolução de combustível:
       atividade a confirmar". Deduzir a 8% o que foi vendido a 1,6% paga a
       menos;
     - o que exceder a receita da atividade no trimestre passa aos
       trimestres seguintes do mesmo ano;
     - o saldo que sobrar no fim do ano aparece como aviso;
   - **cancelamento:** deduz na origem, como já faz a composição;
   - **serviço em NF-e conjugada:** recusa com o motivo "serviço em NF-e
     conjugada: atividade de presunção a informar". O percentual de serviço
     não sai da nota;
   - **a recusa `receita_nfe_nao_integrada` sai.** No lugar dela, o trimestre
     (e o controle do limite do ano) fica parcial com o motivo "NF-e do
     trimestre ainda não escriturada", quando houver nota elegível do
     período, a escriturar ou em rascunho;
   - **o limite da LC 224** passa a considerar a receita de NF-e: a soma
     entra pelos mesmos períodos;
   - **memória:** cada linha de NF-e aparece com a origem "NF-e", a
     natureza, a atividade e o valor, nas três colunas da DL-079;
   - a retenção destacada em NF-e (`retTrib`) fica fora: não é proposta nem
     deduzida, e a memória avisa quando existir.
8. **Telas:** a memória do Presumido mostra as linhas de NF-e. A escrituração
   mostra os avisos do item fora do total e do ICMS desonerado, e oferece as
   duas naturezas de combustível.

**Fica fora:**
- padrão de combustível por empresa (DL-084);
- `vProdLiq` e os estabelecimentos de origem e destino (BL-687);
- retenção em NF-e;
- regime de caixa;
- pré-DAS de comércio (DL-082).

## Decisões tomadas na implementação (frentes A e B)

- **Regra única:** `itens_nfe.receita_do_item(item)`. A fonte única das
  linhas de NF-e para o Simples, o RBT12 e o Presumido é
  `receita.linhas_nfe_do_periodo`. `receita_de_nfe_no_mes` ficou sem uso em
  produção e não foi removida.
- **Valor bruto mantido:** `bruto` por natureza e `valor_bruto_por_cfop`
  continuam sendo o bruto dos itens `indTot` 1. A tela da conferência diz
  "Valor bruto (itens indTot 1)".
- **Atividade de presunção:** `atividade_presumido`, no catálogo de
  naturezas, passou de texto livre a **código da atividade**, e é a fonte
  única do mapeamento.
- **Sugestão de combustível pela descrição oficial do CFOP** (tabela do
  Informe 2023.002 v2.10):
  - 5.656, 6.656, 5.667 e 6.667 → `combustivel`;
  - 5.655 e 6.655 → `combustivel_revenda`;
  - 5.651 a 5.653 e 6.651 a 6.653 (produção do estabelecimento) ficam sem
    sugestão.
- **Devolução de combustível:** CFOP 1.660 a 1.662 e 2.660 a 2.662, pela
  descrição oficial.
- **Ajuste de integração do arquiteto:** na venda de combustível, CSOSN 500
  ou CST 60 não conflita com o CFOP. Antes, toda NFC-e de posto ficava sem
  sugestão, e a escrituração em volume (DL-085) não teria o que confirmar. O
  sinal de substituto continua gerando conflito.
- **Base da dedução da devolução:** é a receita de comércio e indústria do
  trimestre, incluindo NFS-e e receitas informadas, e não só a NF-e ("receita
  da atividade no trimestre").
- **Saldo de devolução:** o aviso do saldo restante sai na apuração do 4º
  trimestre; antes dele, o valor aparece como saldo transportado.
- **Janela da recusa `nfe_nao_escriturada`:** na apuração, de janeiro ao fim
  do trimestre (a mesma janela da recusa antiga, por causa do limite da
  LC 224); no controle do ano, os doze meses.
- **Retenção destacada (`retTrib`):** nenhum código lê esse grupo, então o
  aviso não existe. Fica para quando o leitor ler `retTrib`.
- **Mutante "deduzir no trimestre da venda":** não é expressável sem o
  vínculo da devolução com a venda de origem (BL-685). Foi usado o mutante
  vizinho "não deduzir no trimestre da devolução".
- **Tela:** o botão "Efetivar" continua habilitado para nota de 2027. O
  servidor recusa com 409 e a mensagem nomeada.
- **Testes da DL-081 reescritos para a regra nova:** cinco da conferência
  W16, um da API, a parte do Presumido em `test_dl081_protecao.py`,
  `test_dl081_reconferencia.py` e um de tela. Nenhuma expectativa da DL-074,
  da DL-075 ou da DL-079 mudou.
- **Medido pelos desenvolvedores**, Python 3.13 local: frente A com
  8.638/1/53 e frente B com 8.666/1/53, numa única invocação. A reprovação é
  a de ambiente.

## Decisões para a correção (rodada 1)

Com base na [consulta do frete, do lubrificante e da devolução de combustível](../projeto/consultas/2026-10-09-contador-senior-frete-lubrificante-devolucao.md)
(HI-138 a HI-140):

- **A1 — devolução de combustível.**
  - Nova natureza `devolucao_combustivel_consumo`, que deduz do 1,6%.
  - Reconhecimento dos CFOP 1.660 a 1.662, 2.660 a 2.662, 5.660 a 5.662 e
    6.660 a 6.662, e do NCM.
  - Sugestão com confirmação: x.662 → consumo; x.660 e x.661 → devolução
    de venda.
  - O saldo de devolução passa a ser **por atividade**.
  - A recusa sem caminho de confirmação sai. No lugar, a memória avisa
    quando uma devolução x.662 foi deduzida a 8%.
- **A6 — lubrificante.** A sugestão de combustível exige CFOP **e** NCM.
  - A tabela de NCM vem da nomenclatura vigente do Portal Único Siscomex,
    vigente em 09/10/2026 (Resolução Gecex 926/2026, sha256
    `4ca9f857…de59b`).
  - Álcool etílico (2207.10 e 2207.20.1) e diesel com biodiesel (2710.20)
    contam como combustível só com CFOP de combustível. A descrição da NCM
    não diz "carburante", mas, com CFOP de "combustíveis ou lubrificantes"
    e NCM que não é lubrificante, a única leitura é combustível (decisão do
    arquiteto).
  - Lubrificante sugere revenda (8%), com aviso.
- **A3 — item que não é receita.**
  - O valor líquido dos itens que não são receita é rateado
    proporcionalmente sobre os itens de receita da mesma nota.
  - O resíduo de arredondamento vai para o item de maior valor.
  - A efetivação bloqueia só a nota sem item de receita e o resíduo negativo
    maior que a receita.
- **A2 — reversão da migração 0012.**
  - A migração é alterada no próprio arquivo, porque ainda não foi para a
    `main`.
  - A reversão recusa só quando há item em rascunho ou efetivado com as
    naturezas novas. Com itens só estornados, o CHECK antigo volta como
    `NOT VALID`.
- **A4:** testes para os mutantes sobreviventes.
- **A7:** a função sem uso sai.
- **A8:** recusa própria para nota de 2027 e botão desabilitado na tela.
- **A5 e A10:** vão para o BL-688.

## Decisões tomadas na correção

- **D1, aceita pelo arquiteto:** no item que não é receita, o resíduo é
  diferente conforme o `indTot`.
  - Com `indTot` 1, o resíduo é só frete, seguro e outras despesas. O `vProd`
    do item bonificado nunca foi receita (HI-124), e o desconto dele abate o
    próprio `vProd`.
  - Com `indTot` 0, o resíduo é a `receita_do_item` inteira.
  - A regra literal faria uma remessa de R$ 300 com `indTot` 1 virar receita
    da venda.
- **D2:** um terceiro bloqueio, para resíduo positivo sem base de rateio
  (itens de receita somando zero).
- **D3 e D4:** CFOP de combustível com NCM ausente ou fora das listas fica
  sem sugestão. Exceção: x.660 e x.661 sem NCM sugerem `devolucao_venda`.
- **D5, limitação aceita:** álcool ou diesel B devolvidos com CFOP genérico
  ficam em `devolucao_venda`, sem aviso.
- **D8:** `devolucao_por_atividade` na API é o valor **deduzido** por
  atividade, e o nome pode enganar. Fica para a reconferência opinar.
- **D9:** no Simples, a devolução de combustível para consumo deduz como
  qualquer devolução. O pré-DAS já recusa combustível (HI-132).
- **Coluna `natureza`:** passa de 24 para 29 caracteres, por causa do nome
  novo.
- **Testes existentes ajustados:** os da DL-081 e da DL-083 listados no
  relatório da correção. Nenhum teste da DL-074, da DL-075 ou da DL-079 foi
  tocado.
- **Medido:** 8.765/1/53 numa única invocação (Python 3.13 local).

## Critérios de aceite

1. Receita do item nos quatro casos (`indTot` 1 ou 0 × `indDeduzDeson` 1 ou
   0 ou ausente), com valores escritos à mão no teste.
2. A conferência W16 fecha ao centavo nas notas que antes bloqueavam, usando
   o gerador de notas da auditoria da DL-081, se estiver nos testes, ou um
   equivalente. A nota que não fecha continua bloqueada.
3. O item fora do total com valor cobrado positivo e natureza que não é de
   receita recusa com a mensagem nomeada.
4. A nota de 2027 recusa a efetivação com a mensagem nomeada. Nota de 31/12/2026
   às 23h59 no fuso de São Paulo efetiva.
5. Presumido: um trimestre com NFS-e e NF-e (revenda a 8% e combustível a
   1,6%) bate ao centavo com a conta feita à mão, no IRPJ, no adicional, na
   CSLL e na parcela da LC 224. A devolução deduz no trimestre dela. O saldo
   excedente passa ao trimestre seguinte. O cancelamento deduz na origem.
6. A devolução de combustível, o serviço conjugado e a NF-e não escriturada
   recusam, cada um com seu motivo.
7. Os meses e trimestres sem NF-e ficam idênticos ao que eram antes. Os
   testes da DL-074, da DL-075, da DL-079 e da DL-081 passam sem mudar a
   expectativa, exceto os que testavam os dois bloqueios e a recusa
   `receita_nfe_nao_integrada`. Cada teste mudado é listado no relatório.
8. Isolamento entre escritórios e empresas, e permissões no servidor.
9. Mutação. Cada um destes defeitos derruba teste:
   - somar `vProd` de item `indTot` 0;
   - deduzir `vICMSDeson` com `indDeduzDeson` 0;
   - trocar 1,6% e 8% entre as naturezas de combustível;
   - deduzir a devolução no trimestre da venda;
   - perder o saldo excedente da devolução;
   - esquecer a NF-e no limite da LC 224.
10. Regressão completa numa única invocação. Migração aditiva e reversível,
    se houver.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — função de receita, bloqueios, combustível, 2027, Presumido, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/itens_nfe.py`, `escrituracao_nfe.py`, `receita.py`, `presumido.py`, `presumido_calculo.py`, `presumido_tabelas.py`, `models.py`, migração, `api_presumido.py`, `api_escrituracao_nfe.py`; testes `test_dl083_*` e os testes existentes que precisarem mudar, listados |
| B — telas: memória do Presumido com NF-e; avisos e naturezas na escrituração | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge devolve os dois bloqueios e a recusa
`receita_nfe_nao_integrada`.

A reversão da migração `fiscal 0012` funciona assim:
- **recusa**, com o motivo, se houver item em rascunho ou efetivado com
  `combustivel_revenda` ou `devolucao_combustivel_consumo`; o contador
  estorna e reclassifica primeiro;
- com itens só estornados, que são imutáveis, recria o CHECK antigo como
  `NOT VALID`, que vale só para linhas novas;
- a coluna fica com 29 caracteres;
- nunca apaga dado.
