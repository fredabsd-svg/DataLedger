# DL-087 — Fiscal: classificação fiscal versionada e regras de importação (corte 1)

**Demanda:** ordem do Fred de 09/10/2026 (RC-175): entender os acumuladores do
sistema de referência e codar o que falta. **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1), porque a classificação dirige a receita, o
pré-DAS e o Presumido. A auditoria faz uma rodada, uma correção e uma
reconferência. **Executa depois de a DL-085 e a DL-082 serem integradas**,
porque as três mexem na escrituração de NF-e.

## Base

- [Pesquisa sobre os acumuladores](../projeto/pesquisa-acumuladores-2026-10-09.md),
  de 09/10/2026, no manual e na central de soluções. É rotina, não norma.
- [Consulta ao contador-senior sobre a classificação fiscal](../projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md),
  itens 1 e 2: HI-141 e HI-142.
- [Revisão do módulo fiscal](../projeto/revisao-do-fiscal-2026-10-09.md),
  lacuna A1.

## O problema

Hoje a classificação que dirige o cálculo está **no código**: três catálogos
fechados (`NaturezaOperacao`, `NaturezaTomada` e `NaturezaOperacaoNFe` com
`CATALOGO_NATUREZA_NFE`), sem vigência, sem regra por tributo e sem conta. A
sugestão também está no código, como `if` em Python.

- Cada imposto novo (ICMS, PIS/Cofins, IBS/CBS) reabre o catálogo no código.
- O escritório não consegue ensinar ao produto uma regra nova, como "este
  CFOP com este NCM é combustível para consumo".

## Escopo do corte 1: migrar sem mudar comportamento

1. **Naturezas como dado.**
   - Tabela de naturezas com código, nome, tipo de movimento, papel na
     receita, mercado, documentos admitidos, situação e vigência.
   - Tabela de **regras tributárias** por natureza × regime × tributo ×
     vigência, com fonte e situação (confirmada, hipótese, desativada).
   - No corte 1, os tributos são só os que já existem:
     - receita: papel, mercado e segregação do Simples;
     - anexo do Simples;
     - atividade de presunção do Presumido;
     - situação do ISS.
   - Migração de dados que carrega o catálogo atual como **pacote global**,
     com a fonte de cada valor citada no código de hoje.
   - Os `TextChoices` continuam como chave estável, para não reescrever
     linhas efetivadas. O `CATALOGO_NATUREZA_NFE` passa a **ler** da tabela,
     com uma função única de consulta.
2. **Regras de importação como dado.**
   - Tabela de regras com critérios: CFOP (código ou faixa), CST/CSOSN do
     ICMS com equivalência, CST do PIS, NCM (código, prefixo ou lista
     nomeada), papel da empresa, `idDest`, CRT do emitente e finalidade.
   - Cada regra tem escopo (global, escritório, empresa), vigência e
     especificidade calculada.
   - As regras da sugestão de hoje (`escrituracao_nfe.sugerir_natureza_item`,
     `tomadas.py`) viram regras **globais**. A sugestão passa a resolver pela
     tabela, com a mesma resposta nos testes de hoje.
3. **Precedência explícita:**
   1. maior especificidade;
   2. empate: escopo mais próximo da empresa;
   3. empate: conflito, e o item fica sem sugestão, com as duas regras
      nomeadas.

   Os pesos são publicados no código e na tela (HI-142; a escolha entre
   pesos e ordem manual é a PE-91).
4. **A sugestão grava a regra que a produziu.** O lote da DL-085 passa a
   incluir a regra na assinatura do grupo.
5. **Regra do escritório:**
   - o escritório cria regra (por exemplo, "CFOP 5.656 com NCM 2710.12.59 →
     combustível para consumo") e escolhe o escopo, escritório ou empresa;
   - a regra nunca altera efetivada: ela reaplica só a rascunhos e às notas a
     escriturar;
   - a regra global é imutável pelo escritório, que só pode derivar.
6. **Fila "a classificar"** por empresa e mês. Cada item sem regra ou em
   conflito aparece com o motivo, os sinais lidos e uma sugestão de regra
   pré-preenchida. A ação "criar regra e reaplicar aos pendentes" a acompanha.
7. **API e telas:**
   - cadastro de regras do escritório;
   - fila "a classificar";
   - consulta do pacote global, só leitura.

**Fica fora do corte 1:**
- regras de ICMS, IPI, PIS/Cofins, IBS/CBS e retenções (cortes seguintes);
- modelo contábil (DL-088 e integração);
- forma de pagamento como critério;
- reprocessamento de efetivadas por mudança de regra;
- cadastro de produto e de participante.

## Critérios de aceite

1. **Sem mudança de comportamento.**
   - A suíte inteira passa sem mudar expectativa. As únicas exceções são os
     testes que olhavam a implementação do catálogo, listados e justificados.
   - Um teste de equivalência compara a sugestão antiga com a nova sobre o
     corpus de notas dos testes e sobre todos os CFOP da tabela oficial.
2. O pacote global carrega cada natureza atual com os mesmos atributos e cita
   a fonte.
3. A precedência segue a ordem declarada; o empate dá conflito com as duas
   regras nomeadas.
4. Uma regra do escritório:
   - muda a sugestão de rascunhos e notas a escriturar;
   - nunca altera efetivada;
   - tem trilha, vigência, isolamento por escritório e empresa e permissão
     no servidor.
5. A fila "a classificar" lista cada item sem regra ou em conflito, com o
   motivo. Criar a regra pela fila reaplica aos pendentes do mês.
6. O lote da DL-085 continua equivalente ao individual.
7. **Mutação:** cada um destes defeitos derruba teste:
   - inverter a precedência de escopo;
   - ignorar a vigência;
   - regra do escritório que altera efetivada;
   - padrão silencioso quando nada casa.
8. Regressão completa numa única invocação. Migração aditiva e reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — modelos, migração de dados, resolução, sugestão pela tabela, regra do escritório, fila, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/models.py`, migrações, módulo novo `classificacao.py`, `escrituracao_nfe.py`, `tomadas.py`, `escrituracao_nfe_lote.py`, APIs; testes `test_dl087_*` |
| B — telas: regras, fila, pacote global | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge volta a sugestão ao código. As tabelas novas saem com a
reversão da migração; as naturezas gravadas nos itens são as mesmas chaves de
antes e continuam válidas.
