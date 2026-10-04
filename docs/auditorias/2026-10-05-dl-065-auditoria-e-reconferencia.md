# Auditoria e reconferência — DL-065 (BL-550)

**Auditor:** `auditor-qa`, somente leitura, sondas fora do repositório.
**Rodada:** 1 de no máximo 2 (AGENTS.md §3.1: a terceira é proibida).
**Objeto:** commit `c979162`, branch `fix/dl-065-reclassificacao-em-competencia-encerrada`.
**Ambiente:** PostgreSQL 16.15 na porta 5433, Django 6.1.1, Python 3.14.7.
**Fora do escopo:** a suíte fora de `apps/contabilidade`, o `pytest` do
repositório inteiro, a CI remota e a porta do MCP (que não existe neste
repositório).

---

# PARECER: APROVADO COM RESSALVAS

Os treze critérios de aceite são verdadeiros e todos foram verificados por
execução própria do auditor, sem regressão. Restam três achados de gravidade
média — ponto cego da guarda, corrida entre reclassificar e fechar o mês, e
uma mensagem que manda o contador para um caminho que o próprio produto
recusa — e quatro de baixa.

**Nenhum bloqueador.**

## Critérios 1 a 13

| # | Veredito | Como o auditor verificou |
| --- | --- | --- |
| 1 | Verdadeiro | `test_criterio1_...` — 200, trilha com antes/depois |
| 2 | Verdadeiro | `test_criterio2_...`; sonda S8 imprime `...na competência 03/2026, que está encerrada...` |
| 3 | Verdadeiro | `test_criterio3_...`; **sonda S8**: remover a coluna da DMPL em março encerrado → recusado, valor intacto |
| 4 | Verdadeiro | `test_criterio4_...` — primeira classificação grava com o mês encerrado |
| 5 | Verdadeiro | `test_criterio5_...` (DLPA) + **sonda S8** (DMPL, que a suíte não cobria) |
| 6 | Verdadeiro | `test_criterio6_...` (DMPL) + **sonda S9** (descendente bloqueando a linha da **DLPA** do grupo) |
| 7 | Verdadeiro | `test_criterio7_...`; **sonda S4** imprime `...que está entregue...` |
| 8 | Verdadeiro | `test_criterio8_*`; a mutação imprime os campos do `ModelForm`: `(...;classificacao_dre;classificacao_dlpa;classificacao_dmpl;...)` |
| 9 | Verdadeiro | `test_criterio9_...` + **sonda S7**: trilha `2 → 2 → 2` nas três portas (API 409, tela 200, admin inválido) |
| 10 | Verdadeiro | `test_criterio10_...` + **sonda S3**: DRE trocada pelo **ModelForm do admin** com movimento em mês encerrado → `form.is_valid() True`, gravada. A DE-086 está intacta inclusive no caminho que o plano não cita |
| 11 | Verdadeiro (escopo: API) | `test_criterio11_...` → 404. A porta de **tela** não tinha teste (achado **A7**) |
| 12 | Verdadeiro | `pytest apps/contabilidade` → **8 failed, 1830 passed**, exatamente a linha de base |
| 13 | Verdadeiro | `ruff check` limpo; `ruff format --check` 356 arquivos; `manage.py check` sem problema; `makemigrations --check` sem mudança; `validate-docs.ps1` 223 md; `test_documentacao_do_estado.py` 19 passed |

⚠️ A **primeira** execução do auditor deu 23 failed e 35 errors: foi caused
pelo próprio auditor, que rodou outra `pytest` contra o mesmo banco de
teste em paralelo. Resultado descartado e reexecutado limpo.

## Mutação — os testes provam a regra?

- Guarda removida **em memória** (patch de
  `Conta._competencia_fechada_com_movimento`): **13 dos 21 testes falham**.
  Nenhum mutante sobrevive.
- `code` do modelo diferente do que o serviço reconhece: **11 falham**,
  incluindo os dois 409 da API. O vazamento do `code` está preso por teste.

## Achados

### A1 — **média** — a guarda é cega a lançamento com `competencia` nula

**Requisito afetado:** critério 2 e 3 (o período encerrado precisa barrar).
**Local:** `apps/contabilidade/models.py`, guarda de período fechado.
**Evidência:** lançamento legado criado com `competencia=None` mais itens na
conta, `encerrar_competencia`, depois `classificar_conta_na_dlpa` → **ACATA e
grava** (`reserva_legal`). O gatilho do banco recusa desfazer o vínculo
(`IntegrityError ... não pode ser alterado`), mas `criar_lancamento` sempre
grava a competência e existe o backfill da DL-016 F5 — o estado é de dado
pré-DL-016, alcançável, e nada impede fechar o mês assim.
**Impacto:** período encerrado cuja DLPA/DMPL é reescrita — exatamente o dano
que a trava existe para impedir.
**Correção recomendada:** filtrar o movimento pela faixa de datas da
competência, que é o critério que a apuração usa.
**Forma de verificar:** teste com lançamento sem competência e período
encerrado, esperando a recusa.

### A2 — **média** — corrida entre reclassificar e fechar a competência

**Requisito afetado:** o mesmo critério 2, agora sob concorrência.
**Local:** a mesma guarda; `encerrar_competencia` (`services.py`) trava a
competência, e ninguém travava a conta no caminho da classificação.
**Evidência:** duas threads com barreira — `estado da competencia: encerrada |
classificacao: reserva_legal`, zero erros. A guarda rodou com o mês aberto, o
fechamento commitou, e a reclassificação **commitou depois**.
**Impacto:** a regra é contornável na janela entre a leitura e o commit.
**Correção recomendada:** ler a competência no modo compartilhado antes de
gravar, reaproveitando `_travar_competencia_em_modo_compartilhado`.
**Forma de verificar:** teste de duas threads.

### A3 — **média** — a mensagem manda para um caminho que o produto recusa

**Requisito afetado:** critério 7 e a honestidade da recusa (BL-142, mesma
classe de "mensagem que não corresponde ao produto").
**Local:** a mensagem do achado A1/A2.
**Evidência (S4):** para competência **entregue** a mensagem diz *"Reabra a
competência para corrigir a classificação"*, e `reabrir_competencia` na mesma
competência responde *"não é possível reabrir... a correção vai no mês
aberto"*. A mesma frase afirma *"a correção de período encerrado nunca é uma
reclassificação de conta"*, quando a frase anterior — e
`test_limite_periodo_reaberto_deixa_de_barrar` — provam que, reaberta, a
correção **é** a reclassificação.
**Impacto:** instrução falsa ao contador em recusa de nível 1.
**Correção recomendada:** bifurcar a mensagem por `entregue`, como o BL-468
fez em `criar_lancamento`, e dizer o ajuste real.
**Forma de verificar:** asserção de que a mensagem de `entregue` não manda
reabrir.

### A4 — **baixa** — `EM_ENCERRAMENTO` reportado como "que está encerrada"

O estado gravado não é a palavra da mensagem. Alcançável só por ORM direto,
mas o texto fixo mente sobre o registro.

### A5 — **baixa** — o plano afirma que conta sem movimento não paga consulta

**Medido (S6b):** 22 consultas, uma delas recursiva — a troca em conta
**sem** movimento paga a recursiva. Só a primeira classificação é
curto-circuitada. A afirmação do plano estava errada.

### A6 — **baixa** — script de medição grava a coluna da DMPL sem a guarda

`scripts/medir_identificacao_do_emitente.py:883-885` escreve
`classificacao_dmpl` por fora de `full_clean()`. Risco aceito (DE-008), mas é
o único caminho do repositório que escreve o campo sem a guarda.

### A7 — **baixa** — cobertura faltando

A tela da DMPL (`conta_classificacao_dmpl`) e a recusa do admin para
`classificacao_dmpl` não tinham teste; o critério 11 só era testado na API.

## Vazamentos procurados e **não** achados

Nenhuma porta validada grava `classificacao_dlpa`/`dmpl` sem `full_clean()`:
só existe rota de **criação** de conta (sem rota de atualização), o admin usa
`ModelForm`, não há *management command* nem importador que toque o campo, e
não há MCP neste repositório. Os dois serviços de classificação só têm dois
chamadores, e ambos tratam a nova exceção. O `code` real confere com
`django/core/exceptions.py` do Django 6.1.1: o `hasattr(exc, "error_dict")` de
`_codigos_da_validacao` é o mesmo protocolo que o próprio Django usa.

## Cenários que o auditor tentou quebrar

| Tentativa | Resultado |
| --- | --- |
| Lançamento com `competencia` nula + mês encerrado | **Vazou** (A1) |
| Concorrência reclassificar × `encerrar_competencia` | **Vazou** (A2) |
| `EM_ENCERRAMENTO` | Barrou, mas chamou de "encerrada" (A4) |
| DRE pelo admin com mês encerrado | Gravou — **a DE-086 está intacta**, e por um caminho mais forte que o teste do critério 10 |
| Remover DMPL / descendente na DLPA (não cobertos pela suíte) | Barraram (S8/S9) |
| Destravar a guarda e o `code` em memória | 13 e 11 testes caíram — a cobertura é real |
| Isolar a empresa; recusa por API, tela e admin deixando rastro | 404 e trilha inalterada |

## O que o auditor NÃO verificou

A suíte **fora** de `apps/contabilidade` e o `pytest` do repositório inteiro;
a CI remota e o estado do PR; a corrida entre **duas** classificações
concorrentes da mesma conta (o `select_for_update` na conta existe e é o
mesmo molde da DRE, mas o auditor não montou essa corrida); o comportamento
de `FOR SHARE` sob o `lock_timeout` real do banco; e a inalcançabilidade de
`EM_ENCERRAMENTO` por serviços (declarada no modelo, não testada por ele).

**Nenhum arquivo do repositório foi escrito ou editado** pelo auditor: as
sondas e o plugin de mutação viveram em `%TEMP%` e foram removidos.
