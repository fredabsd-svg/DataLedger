# DL-084 — Fiscal: ajustes de rotina do Lucro Presumido (RC-172)

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170). Traz
para o código as respostas delegadas da RC-172 sobre a rotina do Presumido.
Executa depois da [DL-082](DL-082-pre-das-de-comercio-e-industria.md). Ajustada pelas respostas do Fred da RC-173 (itens 1, 3, 5 e 6).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1), porque mexe no
vencimento e na dedução das retenções. A auditoria faz uma rodada, uma
correção e uma reconferência.

## Base

[Consulta ao contador-senior sobre as PE-83 a PE-85](../projeto/consultas/2026-10-09-contador-senior-pe83-pe84-pe85.md),
de 09/10/2026: PE-83, itens 1, 3, 4, 6, 9, 11 e 12, e PE-85.1 (padrão de
combustível). Hipóteses: HI-102, HI-103, HI-105, HI-135 e HI-136, como
atualizadas pela RC-172.

## Escopo

1. **Dias sem expediente bancário** (HI-105 substituída):
   - Sexta-feira Santa, segunda e terça de Carnaval e Corpus Christi são
     calculados pela Páscoa e tratados como dias não úteis para o
     vencimento, que é antecipado;
   - fonte: instruções do DARF avulso da RFB, lidas em gov.br em
     09/10/2026;
   - o aviso "calendário a conferir" sai;
   - confirmar que 20 de novembro (Lei 14.759/2023) já está na tabela
     nacional.
2. **Feriados locais.** Cada empresa tem uma tabela opcional de feriados
   estaduais e municipais, com data, descrição e fonte.
   - A tabela **nasce preenchida para Palmas e o Tocantins** (RC-173, item
     6).
   - Entra só a data cuja lei for lida na fonte oficial, com a data da
     leitura. A [consulta dos feriados de Palmas e do Tocantins](../projeto/consultas/2026-10-09-contador-senior-feriados-palmas-tocantins.md)
     já leu as cinco datas da HI-137: 15/08, 08/09 e 05/10 (estaduais) e
     19/03 e 20/05 (Palmas). O 18/03 fica fora.
   - A tabela aceita **exceção por ano**: em 2026 o 05/10 foi observado em
     09/10, por decreto.
   - Dois avisos, conforme a fonte bancária (RC-174, lista da Febraban
     trazida pelo Fred):
     - "feriado bancário em Palmas (Febraban)" nas datas que a lista
       confirma: 19/03, 20/05, 15/08, 08/09 e a exceção de 09/10/2026;
     - "feriado local: confirmar expediente bancário na praça" no 05/10,
       que a lei estadual fixa mas a lista não traz para Palmas em 2027.
   - Cada linha guarda a fonte bancária, quando houver: lista Febraban, CAF501
     v.007541 de 07/10/2026.
   - A Sexta-feira Santa continua só na tabela de dias sem expediente
     bancário nacional, que passa a citar também a Lei municipal 577/96.
     A Res. CMN 4.880/2020, art. 6º, lida, é a fonte do Carnaval e de Corpus
     Christi como dias não úteis.
   - Quando o vencimento cai num deles, a tela mostra "antecipar: sem
     expediente bancário na praça".
   - A data normativa não muda.
3. **Teste de coerência da CSLL retida** (HI-103):
   - `vRetCSLL` igual a 4,65% da base (`vServ − desconto incondicional`), com
     tolerância de um centavo, confirma a estimativa de 1/4,65;
   - igual a 1% da base vira "a classificar", com o aviso "o tomador reteve
     só a CSLL?";
   - fora das duas faixas, "a classificar".

   Nenhuma dedução acontece sem a confirmação do contador.
4. **Retenção tardia** (HI-102). Confirmar uma retenção cujo trimestre de
   origem já está efetivado reabre esse trimestre como "a retificar", na
   mesma transação. Se o trimestre já foi pago, o excesso aparece como
   "saldo negativo: PER/DCOMP", nunca como crédito automático. Antes de
   codificar, medir se o comportamento já existe.
5. **Competência ou parcela na receita informada** (HI-135). O campo entra na
   identidade contra duplicidade. A mensagem da recusa pede a competência
   quando for outra parcela do mesmo contrato.
6. **Parâmetros por empresa** (HI-136):
   - **forma de recolhimento padrão:** o padrão do escritório é três
     quotas, porque a grande maioria dos clientes paga assim (RC-173, item
     5); cada empresa pode mudar;
   - **padrão de combustível:** posto e TRR → "para consumo"; distribuidora
     → sem padrão, e quem decide é o item (RC-173, item 3). O padrão sugere
     a natureza quando o CFOP não decide.
7. **Encerrar a medida judicial num trimestre** (BL-680, item 1; RC-173,
   item 1: o escritório tem cliente com medida). Hoje revogar a medida a
   tira de todos os trimestres, inclusive os já apurados. O ato novo encerra
   a medida em (ano, trimestre), com trilha e sem apagar o histórico.
   Reconferir no portal do STF o andamento das ADI 7936 e 7944 e atualizar
   a data do aviso.
8. **Pendência de cadastro** (HI-136). A empresa do Presumido sem atividade
   de presunção padrão vigente aparece na lista de pendências do mês.

## Entrega da frente A (10/10/2026)

Commit integrado na branch; o desenvolvedor mediu a suíte completa num banco
próprio: 9.302/1/55 (a falha é a de ambiente, Python 3.13 local).

- **Itens 1, 2, 3, 5, 7 e 8:** implementados e testados. Mutantes do
  critério 9 derrubam testes (Páscoa deslocada, retenção no trimestre
  seguinte, competência fora da identidade, aviso local mudando a data).
- **Item 4 (retenção tardia):** medido, a dedução **já** ficava no trimestre
  da receita, e o excesso aparece como saldo negativo; o teste novo prende
  isso. "Reabrir como a retificar" e "já pago" ficam **bloqueados**: o
  Presumido não tem estado de trimestre efetivado ou pago. Isso vira etapa
  própria (BL-692).
- **Item 6:** os parâmetros por empresa existem (três quotas por padrão), e a
  função do padrão de combustível também, mas **ainda não está ligada** ao
  lote, à API de escrituração e à tela, que estavam fora dos arquivos
  permitidos. A ligação vai com a frente B.
- **Item 7:** o portal do STF respondeu 403 neste ambiente; o andamento das
  ADI 7936 e 7944 não foi reconferido, e a data do aviso continua 08/10/2026.
- **20/11:** a vigência passou para 2024 (a Lei 14.759 foi publicada em
  22/12/2023). Não muda vencimento de 2026 em diante.
- Hipóteses novas: HI-151 (encerramento cobre o trimestre; praça pela
  matriz).

Próximo: frente B (telas, ligação do padrão de combustível, retirada do
aviso "calendário a conferir" em `views_web.py`), depois a auditoria.

## Critérios de aceite

1. O vencimento é antecipado nas quatro datas, em anos com Páscoa em março e
   em abril. As datas esperadas são escritas à mão.
2. O feriado local mostra o aviso e não muda a data.
3. A coerência da CSLL é testada nas três faixas, inclusive nas bordas de um
   centavo.
4. A retenção tardia reabre o trimestre de origem e nunca deduz no trimestre
   seguinte.
5. Três mensalidades iguais com competências diferentes são aceitas; sem a
   competência, a segunda é recusada como hoje.
6. Os parâmetros por empresa têm trilha, isolamento e permissão no servidor.
   A empresa nova abre em três quotas.
7. A medida encerrada num trimestre continua valendo nos trimestres
   anteriores e deixa de valer nos seguintes. A trilha mostra o
   encerramento.
8. Cada feriado local preenchido cita a lei e a data da leitura.
9. Mutação: trocar a data da Páscoa, deduzir no trimestre seguinte e ignorar
   a competência na identidade derrubam teste.
10. Regressão completa numa única invocação. Migração aditiva e reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — calendário, coerência, retenção tardia, competência, parâmetros, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/presumido*.py`, `retencoes.py`, `models.py`, migração, `api_presumido.py`; testes `test_dl084_*` |
| B — telas | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge devolve o aviso "calendário a conferir" e a identidade antiga
da receita informada. As colunas novas saem com a reversão da migração.
