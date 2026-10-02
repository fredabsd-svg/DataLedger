# Relatório de auditoria QA — DL-061, etapa 2 (BL-603, BL-623, BL-624)

**Auditor:** `auditor-qa` — auditoria independente, SOMENTE LEITURA. Nenhum arquivo do
repositório `DataLedger` foi criado, alterado ou excluído. As sondas próprias rodaram de
um arquivo fora do repositório (`%TEMP%\probe_auditor_dl061_etapa2.py`).
**Versão auditada:** árvore de trabalho da branch `feat/dl-061-ressalvas`, ainda SEM commit
(`git status`/`git diff` de 02/10/2026): 9 arquivos modificados + 3 novos (migração 0019 e
dois arquivos de teste).
**Escopo:** nível 1 (demonstração contábil entregue ao cliente), §3.1 do AGENTS.md.

---

## 1. Veredito

**APROVADO COM RESSALVAS** — os números da coluna da RC-153 conferem ao centavo com o
cálculo à mão e a regra de eventos opostos (RC-155) se comporta como aprovado nos
cenários-limite que executei, mas a etapa ainda não satisfaz o critério de aceite 8:
`ruff format --check .` reprova no arquivo de teste novo e precisa ser corrigido antes do
commit (mais dois achados de baixa, abaixo).

---

## 2. Achados

### Desta etapa

**A1 — MÉDIA — `ruff format --check .` reprova: o arquivo de teste novo está fora do formato.**
- **Arquivo:linha:** `apps/contabilidade/tests/test_dl061_bl623_bl624_eventos_opostos_e_texto_do_veto.py:63`.
- **O que é:** a compreensão de lista de `_linhas_de_evento` está escrita em 4 linhas; o
  `ruff format` a colapsa em 1. Saída real: `1 file would be reformatted, 350 files already
  formatted`, exit 1.
- **Impacto:** o critério de aceite 8 do plano ("`ruff` … limpos") não está cumprido e o job
  `Lint e testes` da CI ficaria vermelho. Sem impacto contábil algum.
- **Correção recomendada:** `ruff format` apenas neste arquivo (ou `.`), reexecutar
  `ruff format --check .` e `ruff check .` e registrar a saída. (Como auditor, não executei
  o `ruff format` — a regra do projeto veda "ruff format" em auditoria.)

**A2 — BAIXA — limite da propriedade do BL-623: contas da MESMA coluna com naturezas cadastradas OPOSTAS escapam do veto e o líquido volta a ser publicado (reproduzido).**
- **Arquivo:linha:** `apps/contabilidade/services.py:6502-6517` (`_com_eventos_opostos`, que
  decide pela natureza CADASTRADA); origem da propriedade: E12 do plano
  (`docs/planos/DL-061-dmpl.md:412-431`).
- **O que é:** o veto dispara quando os dois lados têm contas de mesma natureza. Se as duas
  contas da coluna tiverem naturezas cadastradas opostas — minha sonda usou "(-) Ações em
  Tesouraria" (devedora) no débito e "Ações em Tesouraria (credora)" no crédito —, compra de
  600 e venda de 500 no MESMO lançamento **não é vetada** e o documento publica
  "Aquisição de ações ou quotas em tesouraria **(100,00)**": exatamente a classe de número
  que a RC-155 mandou recusar (o líquido não é evento nenhum). Evidência: sonda S4
  (`pode_emitir: True`, `lancamentos_ambiguos` vazio).
- **Impacto:** baixo e condicionado a cadastro de natureza fora do padrão (conta de
  tesouraria registrada como CREDORA; ou o par de subscrição lido ao contrário). Dentro do
  padrão (tesouraria/prejuízos devedoras; capital/reservas/lucros credoras) a propriedade
  cobre todos os cenários da M2 — os testes e minhas sondas confirmam. **A implementação
  segue fielmente a propriedade aprovada (E12/RC-155); o residual é do desenho, não do código.**
- **Correção recomendada:** registrar o residual no plano/backlog e levar à validação do
  Fred (BL-626); alternativa técnica futura: nas colunas que são SÓ retificadoras
  (tesouraria, ajustes de avaliação), onde o par "conta principal × retificadora" não existe,
  vetar qualquer D e C na mesma coluna com outra partida, como nas reservas de lucros.

**A3 — BAIXA — o texto da AÇÃO da tela (BL-624) não tem guarda contra regressão.**
- **Arquivo:linha:** `apps/contabilidade/tests/test_dl061_tela_dmpl.py:788-790` (compara a
  constante `ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA` com a própria página — é
  renderização, não conteúdo); `apps/contabilidade/tests/test_dl061_bl623_bl624_eventos_opostos_e_texto_do_veto.py:327-353`
  (a propriedade "nenhuma mensagem manda estornar ou dividir" só varre
  `dmpl["pendencias"]`, ou seja, as mensagens do `services.py`); `apps/contabilidade/views_web.py:4728-4739`.
- **O que é:** o critério 6 exige "a ação da tela também; os textos antigos não voltam". Os
  textos da ação estão CORRETOS hoje (li todos: dizem que o efetivado não se altera e que a
  saída é a marcação manual da fatia 2), mas, se alguém devolvesse "Divida cada lançamento
  listado em um por evento (estorne e lance de novo)", a suíte continuaria verde.
- **Impacto:** nenhum hoje; risco de regressão silenciosa de orientação falsa (a M3).
- **Correção recomendada:** estender a propriedade `test_nenhuma_das_mensagens_de_veto_da_dmpl_manda_estornar_ou_dividir`
  para também varrer `views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA` (e o
  `_ORIENTACAO_PADRAO_CONTA_SEM_COLUNA_POSSIVEL`).

### Pré-existente / fora do escopo (registrados, não bloqueiam esta etapa)

- **3 testes auto-pulados** em `test_dl061_tela_dmpl_correcoes.py:601` — `pdftotext`
  (poppler-utils) ausente no ambiente; limitação pré-existente, declarada.
- **BL-622 (M1) e BL-625 (M4)** seguem abertas por decisão de escopo do plano
  ("Fora do escopo desta etapa"), com responsável no backlog — confirmado, não é defeito
  desta entrega.
- **Observação sem gravidade:** a E12 previa o veto "com motivo `eventos_opostos` nomeando a
  coluna"; o item de `lancamentos_ambiguos` traz a coluna nomeada em `colunas` e a causa
  escrita na `mensagem` ("quando os dois lados são eventos opostos…"), sem campo `motivo`
  estruturado. A substância do critério 5 está cumprida; o campo seria só contrato de dados.
- **PE-75 segue aberta** (texto integral da ICPC 08 (R1) não lido): a regra de não citar item
  numerado foi cumprida em código e documentos — verifiquei por varredura do diff.

---

## 3. Cenários que tentei quebrar (evidência executada)

Sondas independentes (minhas, fora do repositório — comando:
`$env:PYTHONPATH=<repo>; .\.venv\Scripts\python.exe -m pytest -c pyproject.toml $env:TEMP\probe_auditor_dl061_etapa2.py -q -s`
→ **`6 passed, 6 warnings in 2.21s`**):

| # | Cenário-limite | Esperado à mão | Resultado |
|---|---|---|---|
| S1 | Ciclo completo da RC-153: destinação 1.000, aprovação 300, reversão 200 | proposta: lucros (800)/nova +800, total 0,00; "Dividendos": nova (300); saldo final nova +500; DLPA proposta (800); conciliação 0,00 por coluna e total | **Bateu ao centavo**; `pode_emitir=True` |
| S2 | Entrada mista ancorada nos lucros: `D lucros 1.000 / C proposto 700 / C dividendos 300` | proposta: lucros (700)/nova +700; dividendos: lucros (300) (mais os 10.000 do caso A); invariante N1 (soma das células = movimento da coluna) | **Bateu**; identidade DLPA × DMPL ok |
| S3 | BL-623: 3+ itens na coluna nos dois lados (2 contas D, 2 C de tesouraria + caixa) | veto; nenhuma célula publicada; saldo final −150,00 preservado | **Vetado**; saldo correto |
| S4 | Tentativa de QUEBRAR a propriedade: tesouraria devedora no D × tesouraria **credora** no C (compra 600 / venda 500) | pela propriedade aprovada (naturezas opostas = par conta × retificadora) NÃO veta | **Escapou do veto** (`pode_emitir: True`) e publicou "Aquisição… (100,00)" — limite da propriedade, virou o achado A2 |
| S5 | Veto + entrada legítima no mesmo exercício | a legítima mantém a célula certa (aumento de capital 20.000); saldo da tesouraria −500 preservado; conciliação 0,00 | **Sem contaminação** |
| S6 | Eventos opostos na coluna NOVA (`D proposto 100 / D caixa 50 / C proposto 150`) | veto; saldo final nova +50,00 preservado | **Vetado**; saldo correto |

Tentativas que NÃO quebraram (já cobertas pelos testes do repositório, que li e executei):
duas contas de mesma natureza nos dois lados (veto); conta principal × retificadora
(subscrição parcial sai "Aumento de capital" 20.000 e subscrição pura tem efeito zero, sem
pendência); coluna de lucros acumulados excluída do veto (M1/BL-622 segue como exceção
documentada); reservas de lucros com a regra antiga (N7) mantida; estorno dos dois vetos não
libera a emissão (E14) e as mensagens não mandam estornar nem dividir.

Também verifiquei à mão que o N1 (soma das células = movimento da coluna) não quebra em
lançamento balanceado: cada ramo (coluna única, âncora, líquido das livres) conserva a soma —
a tentativa de construir contraexemplo exigiria lançamento desbalanceado, que o
`criar_lancamento` recusa.

---

## 4. Classificação e verificações que EU executei

| Item do escopo | Classificação | Evidência |
|---|---|---|
| A. BL-603 — números das linhas destinação/aprovação/reversão e saldos | **Testado** | S1/S2 + 9 testes novos; cálculo à mão conferido ao centavo (ver §3) |
| A. Identidade DLPA × DMPL nos novos cenários; suíte da DLPA sem mudança | **Testado** | `_conferir_identidade_com_a_dlpa` nos testes novos e em S1/S2; `test_dl048_dlpa.py` (51 testes) **intocado pelo diff** e verde |
| A. Par de classificações no `clean()` e tabela de consistência; tipo fora de PL recusado | **Testado** | `test_combinacoes_inconsistentes_de_classificacao_sao_recusadas_no_cadastro` (5 recusas + 1 aceitação); mapas cobertos por teste derivado (`test_os_mapas_cobrem_exatamente_o_enum`) |
| A. Conciliação com o Balanço com a coluna nova; `Decimal` | **Testado / Inspecionado** | S1 e teste novo: diferença 0,00 por coluna e total; `isinstance(..., Decimal)`; todo cálculo em `Decimal` (varredura do diff) |
| B. BL-623 — cenários-limite do veto | **Testado** | S3–S6 + 8 testes novos de eventos opostos/subscrição/reservas/lucros |
| B. Veto preserva o movimento líquido da coluna | **Testado** | S3, S5, S6 e teste novo (saldo final −500,00 com células zeradas) |
| C. BL-624 — três mensagens verdadeiras; estorno não libera | **Testado / Inspecionado** | 4 testes novos (inclusive as duas propriedades de texto); li as três mensagens e as 8 ações da tela: nenhuma manda estornar/dividir; lacuna de guarda = A3 |
| D. Testes novos verificam COMPORTAMENTO | **Inspecionado** | afirmam células, saldos, listas de pendência e textos — não repetem a implementação; a identidade reusa a tabela de mapeamento (padrão pré-existente do projeto) |
| D. As 4 expectativas atualizadas | **Inspecionado** | ver §4.1 — todas mudaram porque o comportamento pedido mudou |
| E. RC-151 (não decide → recusa com a lista do que falta) | **Testado** | crédito livre vira pendência "Classifique a conta."; par sem regra veta nomeando origem/destino; nenhum rateio presumido |
| E. Comentários explicando o PORQUÊ | **Inspecionado** | presentes nas regras novas (models, services, testes), com fonte normativa e PE-75 |
| E. Migração segura (banco vazio e base anterior) | **Testado (indireto) / Inspecionado** | `0019` é só `AlterField` de `choices` (nenhum dado regravado); o banco de teste é construído do zero com todas as migrações em ordem em toda execução; `makemigrations --check` limpo |
| E. Sem segredos nem dado real; escopo fechado | **Inspecionado** | diff varrido por inteiro: CNPJs sintéticos de teste, nenhum credencial; só os 12 arquivos da etapa |
| Permissões, isolamento, trilha | **Inspecionado** (inalterados) | nenhum caminho de autorização/escopo foi tocado pelo diff |
| Suíte completa do repositório | **Não testado por mim** | instrução do enunciado: preferir os arquivos afetados (suítes completas podem rodar em paralelo) |
| `validate-docs.ps1` | **Testado** | `Documentação válida: 216 arquivos Markdown verificados.` |
| Marcação manual (fatia 2, BL-605) e reconhecimento de par estornado | **Fora do escopo** (E14) | decisão registrada no plano e no backlog |

### 4.1 As quatro expectativas atualizadas, uma a uma

1. **Ordem das colunas (`test_dl061_dmpl.py:397-412`):** `len(COL.values)` 12→13 e última
   coluna agora é a de dividendo adicional proposto. Mudou porque a RC-153 **criou** a
   coluna (E10: última, grupo próprio). Não esconde defeito — o teste ficou mais preciso
   (`[-2] == lucros…`).
2. **Ordem das linhas E4 (`test_dl061_dmpl.py:667-689`):** `"dividendo_adicional_proposto"`
   entra antes de `"dividendos"`. Decisão E11 (a proposta precede a distribuição). Não
   esconde defeito.
3. **Orientação N4 (`test_dl061_dmpl_correcao_rodada1.py:644-660`):** o texto antigo mandava
   "aguarde a coluna (BL-603)"; a BL-603 existe, então a orientação mudou. O teste novo é
   MAIS estrito que o antigo: exige "Dividendo adicional proposto" no texto, **proíbe**
   "aguarde" e mantém as demais frases. Não esconde defeito.
4. **Literal do veto (`test_dl061_tela_dmpl.py:707-714`):** "Divida o lançamento em um por
   evento" → "a saída prevista é a marcação manual do lançamento". É o próprio BL-624/E13 —
   o texto antigo era a mentira que a M3 acusou. Não esconde defeito (a guarda de regressão
   do texto da AÇÃO da tela, porém, é a lacuna A3).

### Verificações executadas (comandos e saídas reais)

```
.\.venv\Scripts\python.exe -m pytest <2 arquivos novos> -q
    → 20 passed, 19 warnings in 5.61s   (9 + 11 testes)

.\.venv\Scripts\python.exe -m pytest <test_dl061_dmpl, test_dl061_dmpl_correcao_rodada1,
    test_dl061_tela_dmpl, test_dl061_tela_dmpl_correcoes, test_dl048_dlpa> -q
    → 292 passed, 3 skipped, 245 warnings in 78.81s   (coleta: 295; 51 são da DLPA)

.\.venv\Scripts\python.exe manage.py check
    → System check identified no issues (0 silenced).

.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
    → No changes detected

.\.venv\Scripts\python.exe -m ruff check .
    → All checks passed!

.\.venv\Scripts\python.exe -m ruff format --check .
    → 1 file would be reformatted, 350 files already formatted   [exit 1]  ← A1

pwsh ./scripts/validate-docs.ps1
    → Documentação válida: 216 arquivos Markdown verificados.

pytest %TEMP%\probe_auditor_dl061_etapa2.py -q -s   (sondas S1–S6, fora do repo)
    → 6 passed (S4 com o comportamento registrado em stdout — ver §3)
```

Os 3 skips são os auto-pulos de PDF (`pdftotext` ausente,
`test_dl061_tela_dmpl_correcoes.py:601`) — pré-existentes e declarados.

---

## 5. O que muda o que o Fred aprovou × o que é técnico

**NÃO muda o aprovado:**
- **RC-151:** a regra não decide → recusa com a lista do que falta; nunca presume. Confirmado
  nos caminhos novos (crédito livre na coluna nova → pendência; par sem regra → veto).
- **RC-152:** intocado pelo diff.
- **RC-155 (BL-623):** veto de eventos opostos na mesma coluna e subscrição com
  integralização parcial como aumento líquido — exatamente a opção B aprovada; a propriedade
  implementada é a descrita na decisão E12.
- **RC-153 (BL-603):** a coluna e as duas linhas entregues como pedido; a aprovação sai em
  "Dividendos", conforme a tabela da E11.

**Precisa do Fred (validação contábil — já roteirizada no BL-626, nada foi decidido por mim):**
a coluna "dividendo adicional proposto" FORA dos grupos do 111A; a linha própria na DLPA e na
DMPL; a aprovação saindo em "Dividendos" na coluna nova; e o residual da propriedade por
natureza (achado A2). A base normativa (ICPC 08 (R1)) foi identificada em fonte oficial, mas o
texto integral continua não lido (PE-75 aberta) — nenhum item numerado é citado, como manda a
regra.

**Técnico (não toca regra contábil):** migração 0019 (só `choices`), ordem de linhas/colunas,
textos de pendência/ação, formatação `ruff` (A1), guarda de teste (A3).

---

## Pendências da entrega (fora da auditoria, para o responsável)

1. Corrigir A1 (`ruff format`) antes do commit — é critério de aceite.
2. Registrar A2 como residual da propriedade (plano/backlog, levar ao BL-626) e A3 como
   teste a acrescentar (pode ser na única correção permitida — AGENTS.md §3.1: **uma
   auditoria, uma correção, uma reconferência; a terceira é proibida**).
3. O ciclo de entrega (commit, push, PR, `docs/agents/estado.md`) ainda não aconteceu — o
   trabalho está sem commit, como esperado nesta fase.

*Auditoria de software não substitui a validação profissional das regras contábeis e legais.
Este relatório não declara ausência de defeitos além dos testados.*

---

# RECONFERÊNCIA (rodada única permitida — AGENTS.md §3.1)

Verificadas SOMENTE as correções de A1, A2 e A3, com evidência executada por mim.

## Veredito final: **APROVADO**

Os três achados da auditoria estão **fechados**; as correções não introduziram achado novo.

## Estado de cada achado

- **A1 (formato) — FECHADO.** `.\.venv\Scripts\python.exe -m ruff format --check .` →
  "351 files already formatted"; `ruff check .` → "All checks passed!". O `ruff format`
  aplicado nos dois arquivos de teste novos foi conferido: `test_dl061_bl603_...` está
  idêntico em conteúdo (só forma) e `test_dl061_bl623_...` ganhou apenas os 2 testes novos
  mais formatação.
- **A2 (limite da propriedade) — FECHADO**, com residual registrado como manda a correção
  recomendada. `services.py:_com_eventos_opostos` (6502-6527): tesouraria agora veta D e C
  com outra partida **sempre** (a direção define eventos opostos por construção; não existe
  par conta × retificadora na coluna) — comentário explica o porquê e cita a auditoria;
  capital continua julgando pela natureza (é o par da subscrição que a RC-155 manda manter
  líquido — endurecer quebraria o aprovado); residual registrado como **BL-627** no backlog
  (com responsável, dependência do Fred e critério de aceite) e no plano (E12).
  Minha sonda S4 reproduzida: `pode_emitir: False`, `lancamentos_ambiguos: True`,
  `saldo_final tesouraria: -100.00`, nenhuma célula de evento publicada — exatamente o
  esperado. O teste de regressão
  `test_tesouraria_com_natureza_fora_do_padrao_tambem_e_eventos_opostos` cobre o caso, e os
  testes de subscrição (parcial = "Aumento de capital" 20.000; pura = efeito zero)
  continuam verdes.
- **A3 (guarda da ação da tela) — FECHADO.**
  `test_nenhuma_das_acoes_da_tela_da_dmpl_manda_estornar_ou_dividir` varre o dict
  `ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA` inteiro e reprova "estorne" ou "divida";
  os textos antigos ("Divida cada lançamento… (estorne e lance de novo)") não podem voltar
  sem quebrar a suíte.

## Achados NOVO introduzidos pelas correções

**Nenhum.** `git status`: os mesmos 12 arquivos da auditoria (9 modificados + 3 novos), sem
arquivo alheio; o diff das correções restringe-se a `_com_eventos_opostos` (+docstring),
os 2 testes novos, a formatação dos arquivos de teste e o registro do BL-627 (backlog +
plano). Observação de fronteira (não é achado novo, é o próprio residual do BL-627): a
regra por natureza continua valendo para as demais colunas julgadas por natureza (ajustes
de avaliação, reservas de capital, coluna nova) — o critério de aceite do BL-627 ("natureza
esperada por coluna") as cobre quando o Fred decidir.

## Evidência executada nesta rodada

```
ruff format --check .   → 351 files already formatted
ruff check .            → All checks passed!
sonda S4 (fora do repo) → S4 pode_emitir: False / S4 ambiguidades: True /
                          S4 saldo_final tesouraria: -100.00 / só a linha saldo_final
                          carrega a coluna   [6 passed no conjunto das sondas]
7 arquivos afetados     → 314 passed, 3 skipped in 77.67s   (3 skips de PDF, preexistentes)
testes nomeados (regressão S4 + guarda A3 + subscrição parcial + pura) → 4 passed
git status              → mesmos 9 modificados + 3 novos da auditoria; diffstat 360+ / 44−
```

## Classificação final (itens A/B/C/D do relatório)

| Item | Estado final |
|---|---|
| **A. BL-603 (RC-153)** | **Testado** — inalterado nesta rodada; números conferidos à mão (S1/S2) e identidade DLPA × DMPL verdes |
| **B. BL-623 (RC-155)** | **Testado** — A2 fechado: tesouraria endurecida (S4 agora vetada com saldo preservado), capital pelo par da subscrição (RC-155), residual em BL-627 |
| **C. BL-624 (M3)** | **Testado** — A3 fechado: três mensagens + ações da tela com guarda de regressão; estorno não libera (E14) |
| **D. Testes** | **Testado** — 314 passed / 3 skipped; os 2 testes novos da correção verificam comportamento; as 4 expectativas atualizadas seguem legítimas |

**Pendências declaradas (não são defeito — validação de produto):** BL-626/BL-627 com o
Fred (escolhas contábeis e limite da natureza cadastrada) e PE-75 (texto integral da
ICPC 08 (R1)). Ciclo de entrega (commit/push/PR/`estado.md`) segue com o responsável.
**Esta foi a reconferência; terceira rodada é proibida (AGENTS.md §3.1).**
