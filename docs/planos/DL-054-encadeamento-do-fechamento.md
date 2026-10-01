# DL-054 — Mês encerrado congelado contra o encadeamento do carnê-leão

**Demanda:** Fred, 30/09/2026, respondendo à PE-74 com *"Sim"* à
recomendação (RC-148), e *"prossiga para próxima etapa"*. Origem: achado E1
da [auditoria da DL-053](../auditorias/2026-09-30-dl-053-rodada-1.md)
(BL-572).
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `claude/zealous-goldberg-jr5ggu` → `main`, depois do merge da
DL-053.
**Risco:** nível 1 (carnê-leão apurado e entregue ao cliente). Auditoria
independente **obrigatória**.

## Problema

O carnê-leão se encadeia de janeiro a dezembro: excesso de livro-caixa,
crédito do exterior e saldo abaixo de R$ 10,00 passam de um mês para o
seguinte (`carne_leao.py`, `_apurar_ano_calendario`). A DL-053 trava o mês
encerrado, mas um lançamento num mês **aberto anterior** ainda muda o
resultado de um mês **posterior encerrado** do mesmo ano. A auditoria mediu
uma despesa de R$ 2.000,00 em janeiro baixando o imposto de fevereiro
encerrado de R$ 1.016,27 para R$ 466,27.

## Regra (RC-148)

1. **Lançar ou estornar em mês M** é recusado se existir mês **encerrado**
   posterior a M no mesmo ano-calendário. A mensagem nomeia o primeiro mês
   encerrado alcançado. É a mesma regra conservadora já aprovada para os
   dependentes (RC-147).
2. **Reabrir mês M** com meses encerrados depois dele no mesmo ano tem dois
   caminhos: reabrir só M é **recusado** e explicado; ou reabrir **em
   cascata** M e todos os meses encerrados posteriores do ano, num único ato,
   com um motivo, tudo na mesma transação e registrado na trilha (um registro
   por mês reaberto, todos com o mesmo motivo e a indicação da cascata).
3. **Encerrar** não muda: fechar fora de ordem continua possível. A regra 1 é
   que impede o efeito em cadeia.
4. Concorrência: a checagem da regra 1 lê os meses posteriores do ano sob os
   mesmos locks consultivos da DL-053 (compartilhado nos meses alcançados, em
   ordem crescente), para que "lançar em janeiro" e "encerrar fevereiro" ao
   mesmo tempo nunca terminem com fevereiro encerrado e alterado.
5. Fora do escopo: a virada do ano (o encadeamento é anual) e os dependentes
   (já cobertos pela RC-147).

## Critérios de aceite

1. Com fevereiro encerrado e janeiro aberto: lançar ou estornar em janeiro →
   409, banco inalterado, mensagem cita 02/aaaa. Com só meses anteriores
   encerrados, ou em outro ano → aceito.
2. O cenário do E1 (despesa em janeiro, fevereiro encerrado) não altera a
   apuração de fevereiro — teste que compara a apuração antes e depois.
3. Reabrir janeiro com fevereiro e março encerrados: sem cascata → recusado,
   nada muda; com cascata → os três ficam abertos, três registros na trilha
   com o mesmo motivo, numa transação (trilha falhando → nada muda).
4. Cascata respeita papéis (ADMINISTRADOR e GESTOR), isolamento e motivo
   obrigatório, pela API e pela tela; negativas com banco inalterado.
5. Concorrência: lançar em M × encerrar mês posterior, com duas conexões
   (join com timeout + asserção), nunca termina com mês posterior encerrado e
   alterado.
6. Tela: a reabertura informa os meses encerrados posteriores e oferece a
   cascata; o formulário de lançamento avisa a regra. Sem identificador
   interno visível.
7. Suíte completa verde em PostgreSQL.

## Impacto e reversão

Sem migração prevista (a regra lê a tabela existente). Reversão: revert do
PR.

## Distribuição

`desenvolvedor-pleno` (serviços, API, testes), depois `especialista-frontend`
(tela da reabertura em cascata e aviso), depois `auditor-qa`.

## Evidências e integração

- Servidor (`desenvolvedor-pleno`): recusa de lançar ou estornar em mês com
  mês posterior encerrado no ano, sob locks consultivos de M a dezembro;
  `reabrir_mes_caixa_em_cascata` atômica, um registro de trilha por mês;
  API de reabrir com `cascata`.
- Tela (`especialista-frontend`): lista dos meses antes do formulário,
  confirmação explícita, painel e avisos no formulário, na lista e no
  estorno.
- Um teste da DL-053 mudou de expectativa por consequência direta da RC-148
  (novembro recusado com dezembro encerrado no mesmo ano).
- [Auditoria rodada 1](../auditorias/2026-10-01-dl-054-rodada-1.md):
  **aprovada com ressalvas** — cenário E1 reproduzido (imposto de
  fevereiro 1.016,27 inalterado), estresse de cerca de 3.000 operações sem
  deadlock nem estado misto, suíte com 4.080 aprovados e a falha conhecida
  de Python 3.13. Ressalvas: BL-588 a BL-591; H1 e H2 na DL-060.
- **Contrato da API alterado pela [DL-060](DL-060-confirmacao-da-cascata.md):**
  a reabertura com `cascata: true` passou a exigir `meses_confirmados` (lista
  de `{ano, mes}` com os meses mostrados); lista divergente dá 409 sem
  efeito, lista ausente ou sem `cascata: true` dá 400.
