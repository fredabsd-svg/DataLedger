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
`receita_nfe_nao_integrada`. A natureza `combustivel_revenda`, se já tiver
sido usada, impede a reversão da migração até o contador reclassificar os
itens: a reversão recusa com o motivo, nunca apaga.
