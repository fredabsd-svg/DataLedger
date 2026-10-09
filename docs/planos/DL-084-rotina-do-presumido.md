# DL-084 — Fiscal: ajustes de rotina do Lucro Presumido (RC-172)

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170). Traz
para o código as respostas delegadas da RC-172 sobre a rotina do Presumido.
Executa depois da [DL-082](DL-082-pre-das-de-comercio-e-industria.md).
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
6. **Parâmetros por empresa** (HI-136): a forma de recolhimento padrão
   (quota única ou quotas) e o padrão de combustível (para consumo, para
   revenda ou sem padrão). O padrão de combustível sugere a natureza quando o
   CFOP não decide.
7. **Pendência de cadastro** (HI-136). A empresa do Presumido sem atividade
   de presunção padrão vigente aparece na lista de pendências do mês.

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
7. Mutação: trocar a data da Páscoa, deduzir no trimestre seguinte e ignorar
   a competência na identidade derrubam teste.
8. Regressão completa numa única invocação. Migração aditiva e reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — calendário, coerência, retenção tardia, competência, parâmetros, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/presumido*.py`, `retencoes.py`, `models.py`, migração, `api_presumido.py`; testes `test_dl084_*` |
| B — telas | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge devolve o aviso "calendário a conferir" e a identidade antiga
da receita informada. As colunas novas saem com a reversão da migração.
