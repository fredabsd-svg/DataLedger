# DL-078 — Fiscal: serviços tomados, ISS retido pelo tomador e retenções federais

**Demanda:** ordem do Fred de 08/10/2026 (RC-164); etapa 6 do roteiro de
execução do [DL-067](DL-067-plano-do-modulo-fiscal.md). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) — é o ISS que o cliente reteve e precisa
recolher. Auditoria independente: uma rodada, uma correção, uma
reconferência.

**Conferência, nunca guia nem transmissão:** nada de DAM, DARF, EFD-Reinf ou
DCTFWeb; o produto mostra o que a nota destaca e o que o cliente precisa
recolher, para o contador conferir.

## Base

[Consulta ao contador-senior sobre serviços tomados](../projeto/consultas/2026-10-08-contador-senior-servicos-tomados.md)
(LC 116, Lei 10.833, Lei 8.212, RIR/2018, Lei 9.430 e LC 123 lidos no
Planalto; XSD 1.00 e 1.01 e Perguntas e Respostas v1.1 da NFS-e nacional;
RCTM de Palmas em cópia). Hipóteses HI-93 a HI-96; pendência PE-82 com o Fred.

## Escopo

1. **Escrituração das NFS-e tomadas** num registro próprio (separado da
   escrituração das prestadas, para nada contaminar receita, RBT12, pré-DAS e
   ISS próprio), com rascunho, efetivação, estorno com motivo e
   imutabilidade, como a DL-072. **Natureza da entrada** num catálogo
   fechado (HI-93), **sugerida** pelo XML e **confirmada** pelo contador:
   tomado com ISS retido pelo cliente; tomado sem retenção; prestador de
   outro município com possível ISS devido no local do tomador; tomado de MEI;
   tomado de ME/EPP do Simples; tomado de pessoa física. Importação de serviço
   (tomado do exterior) fica fora, com recusa nomeada — o emissor nacional
   ainda não gera esse XML.
2. **Campos da nota** lidos do XML guardado, com caminho conferido no XSD e
   ausência nunca virando zero: `tpRetISSQN`, `vISSQN`, `cLocIncid`,
   `vLiq`, `opSimpNac`, `regApTribSN`, `tpEmit` e o grupo `tribFed`
   (`vRetCP`, `vRetIRRF`, `vRetCSLL`, `piscofins/tpRetPisCofins`, `vPis`,
   `vCofins`).
3. **ISS retido a recolher pelo cliente tomador** (HI-94): soma do `vISSQN`
   das notas efetivadas como "ISS retido pelo cliente", por município de
   incidência e mês de competência; vencimento pela regra do município
   (Palmas: dia 15, já cadastrado na DL-076); nota retida sem ISS destacado
   aparece para conferir, nunca como zero; aviso de cadastro do prestador de
   fora em Palmas (CNES/RANFS).
4. **Retenções federais destacadas** (HI-95): listar e totalizar por tributo
   — "CSRF retida (PIS + COFINS + CSLL)" pelo `vRetCSLL`, IRRF, contribuição
   previdenciária (`vRetCP`) — **sem recalcular nem decidir se era devida**.
   Competência (HI-96): INSS pelo mês de **emissão**; IRRF e CSRF pela **data
   de pagamento**, informada pelo contador num campo opcional com trilha —
   sem ela, a retenção fica "pendente de data de pagamento", nunca presumida.
   Avisos A1 a A8 da consulta (valor líquido que não fecha, código de
   retenção incoerente, retenção provavelmente indevida de prestador do
   Simples ou MEI, tomador do Simples que não retém CSRF, valor abaixo do
   mínimo de dispensa, INSS sobre optante, INSS só em cessão de mão de obra,
   prestador pessoa física ou MEI sem campos federais).
5. Telas e API: escriturar tomadas, ISS retido a recolher, retenções
   federais; isolamento e permissões como na DL-072.

**Fica fora:** lançamento contábil automático (desenhado para depois, como
rascunho que fecha pela fórmula do valor líquido); importação de serviço;
retenções de pessoa física; crédito de PIS/Cofins no Lucro Real; guias e
obrigações acessórias; vencimento do ISS retido nos outros 51 municípios (sem
regra cadastrada, mostra "não parametrizado").

## Decisões tomadas na implementação

- **Natureza × retenção:** a natureza diz o tipo da operação e do
  prestador; a retenção vem do `tpRetISSQN`. "ISS retido pelo cliente"
  exige retenção no XML e "sem retenção" e "prestador de outro município"
  exigem ausência dela (recusa na efetivação). MEI, Simples e pessoa física
  aceitam os dois casos, e com retenção entram no total do ISS retido
  (HI-94); MEI com retenção gera aviso.
- **Nota emitida pelo tomador** (`tpEmit` 2 ou 3) é recusada no primeiro
  corte: o XSD mostra que o tipo 2 cobre importação **e** outros motivos de
  emissão pelo tomador (`cMotivoEmisTI`), e o tratamento de cada um ainda não
  foi decidido (HI-97).
- **Data de pagamento** só em tomada efetivada, com motivo e trilha; o banco
  permite alterar só esse grupo de colunas depois da efetivação.
- **Prestador de outro município** é identificado por `cLocIncid` diferente
  do local da prestação, sem a lista de subitens do art. 3º da LC 116; o
  aviso de CNES/RANFS vale para incidência em Palmas.
- **INSS** vence no dia 20 nominal do mês seguinte ao da emissão; IRRF e
  CSRF são agrupados pela data de pagamento, sem data de vencimento
  calculada.

## Critérios de aceite

1. Campos lidos batem com o XSD nas duas versões, com o caminho citado;
   ausência nomeada, nunca zero.
2. Natureza sugerida corretamente nos sete sinais do XML; o contador pode
   trocar; efetivada é imutável em todas as portas (inclusive SQL direto);
   estorno com motivo.
3. ISS retido a recolher = soma do `vISSQN` das notas retidas efetivadas da
   competência, por município; prestadas, rascunho, estornadas e canceladas
   não entram; nota retida sem `vISSQN` aparece para conferir.
4. Vencimento de Palmas: competência 10/2026 → 15/11/2026, com o dia da
   semana quando cair em fim de semana.
5. Retenções federais totalizadas por tributo conferem com as notas; INSS
   pelo mês de emissão; IRRF e CSRF sem data de pagamento ficam pendentes.
6. Cada aviso A1 a A8 dispara no caso que o justifica e não dispara no
   contrário.
7. Nenhuma tomada aparece em receita, RBT12, pré-DAS ou ISS próprio.
8. Isolamento entre escritórios e empresas; permissões no servidor.
9. Mutação: somar retenção de nota não efetivada, usar a emissão para o
   IRRF, tratar ausência como zero, contar tomada como receita, ou remover o
   filtro de empresa derruba testes.
10. Não regressão completa numa única invocação; migração aditiva e
    reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — campos, modelo, escrituração tomada, ISS retido, retenções, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/fiscal/` (módulos novos `tomadas.py`, `retencoes.py`, leitura de campos), modelos, migração, testes `test_dl078_*` |
| B — telas | `auxiliar-implementacao` (Haiku) | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Tabelas novas; nenhuma tabela existente muda. Reverter é reverter a migração
e o merge.
