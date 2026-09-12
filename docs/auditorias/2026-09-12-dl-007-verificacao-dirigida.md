# Verificação dirigida DL-007 — 2026-09-12

Verificação de escopo estreito do `auditor-qa`, limitada aos achados **N1** e
**N2** da [rodada 2](2026-09-12-dl-007-rodada-2.md), mais ausência de regressão.

Escopo deliberadamente estreito: A1 a A8 já estavam aprovados e provados por
mutação. Refazer auditoria completa a cada ajuste é como se entra em ciclo
indefinido.

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**.

## Parecer da etapa

**APROVADO COM RESSALVAS**

## N1 — colisão de impressão digital: SANADO

1. **Par exato do relatório anterior:** com a concatenação antiga,
   `historico="Honorario"` com 3 itens e
   `historico="Honorario|3:debito:100.00"` com 2 itens produzem o mesmo
   SHA-256 (`99969c1ceab2783d…`). Com o `json.dumps` atual produzem
   `8e9f8697…` e `60bb9181…` — **diferem**. Fim a fim pela API, o par agora
   devolve **201 e depois 409**, com 1 lançamento no banco.
2. **Injetividade atacada novamente:** **72.151 entradas adversariais** —
   `"`, `\`, `,`, `:`, `{`, `}`, `[`, `]`, `|`, espaço, TAB, LF, NBSP,
   acentuados, emoji, `null`, `true`, histórico imitando o JSON inteiro
   (`","itens":[[3,"debito","100.00"]],"zz":"`), conteúdo movido de `itens`
   para `historico` e de `data` para `historico`, fronteiras
   `empresa_id`↔`data` (1/2024 vs 12/024 vs 2024), fronteiras
   `conta`↔`tipo`↔`valor` (pk 11 vs 110, `tipo="debito:100.00"`), e 60.000
   aleatórias. **Zero colisões.**
3. **Mutação M19** (volta à concatenação com `|`) derruba
   `test_impressao_digital_nao_colide_por_ambiguidade_do_separador`. Existe
   rede de proteção.

**Observação informativa do auditor, não achado:** `ensure_ascii=True` não é
injetivo em teoria para *lone surrogates* — `chr(0xD83D)+chr(0xDE00)` gera o
mesmo texto que o emoji U+1F600. **Não reproduzível pela API**, porque
`json.loads` colapsa o par de escapes no caractere astral, então a string
ambígua nunca chega à função.

## N2 — comportamentos da impressão digital: PARCIALMENTE SANADO

| Mutação | Resultado |
| --- | --- |
| M13 (remove `sorted`) | **Derruba** `test_itens_em_ordem_invertida_nao_geram_falso_conflito` |
| M14 (remove `quantize`) | **Derruba** `test_valores_com_escalas_diferentes_nao_geram_falso_conflito` |
| M15 (remove `empresa_id`) | **Sobrevive** à suíte inteira — ver achado N4 |

### Achado N4 — BAIXA: teste afirmava matar M15 e não matava

- **Gravidade:** baixa.
- **Requisito afetado:** RC-14; achado N2 da rodada 2.
- **Localização:** `apps/contabilidade/tests/test_bl40_bl41.py`
  (`test_mesma_chave_e_conteudo_em_empresas_diferentes_nao_gera_conflito`, cuja
  docstring afirmava "mata M15"); função em `apps/contabilidade/services.py`.
- **Evidência:** aplicada a mutação M15 na cópia isolada, o teste **passa**, e a
  suíte completa fecha 90/90. Causa: as duas comparações de impressão só
  ocorrem dentro de `filter(empresa=empresa, chave_idempotencia=…)`, e o índice
  único é parcial por empresa — logo `empresa_id` no hash é **redundância
  inobservável por teste de comportamento**. O auditor provou que é matável por
  teste **direto** da função: `_impressao_digital(empresa_id=1, …) !=
  _impressao_digital(empresa_id=2, …)` falha sob M15 e passa sem ela.
- **Impacto:** não há defeito funcional hoje. Mas a defesa em profundidade
  segue sem prova, e a docstring afirmava cobertura que não existe — risco de
  **confiança indevida**, contra a regra de honestidade em relatórios.
- **Correção recomendada:** asserção direta dos dois hashes com `empresa_id`
  diferente; ou reescrever a docstring como "redundância inobservável por
  comportamento", como foi feito em A7.
- **Como verificar:** aplicar M15 e exigir falha.

## Regressão — não há

`pytest -q`: **90 passaram**, 0 falhas. `ruff check`: aprovado.
`ruff format --check`: 104 arquivos. `manage.py check`: 0 problemas.
`makemigrations --check --dry-run`: sem alterações; migrações seguem `0001` e
`0002`, nenhuma nova.

Reconfirmado pela API: ordem invertida → **200** (mesmo id); escalas `100`,
`100.0`, `100.000` → **200**; `tipo` trocado → **409**; data diferente →
**409**; empresas diferentes com mesma chave e conteúdo → **2 lançamentos**.
Repetição idêntica com histórico contendo acento, `"`, `\`, `{`, `[`, `|`, `:`
→ **200**: nenhum falso conflito novo foi introduzido pela troca para JSON.

## Árvore de trabalho

`git status --short` e `git diff --stat` idênticos ao início. O auditor não
alterou nada. Único efeito colateral: `.pytest_cache/`, ignorado pelo Git,
atualizado pela execução dos testes.

## Ressalvas remanescentes

Todas explícitas, nenhuma escondendo falha essencial:

| Ressalva | Situação |
| --- | --- |
| **N4** | **Resolvido pelo `arquiteto-senior`** — ver abaixo |
| **A7** (`criado_agora` sem prova) | Aceita: o caminho é inalcançável por construção, não há teste possível |
| Camada `select_for_update` sem teste próprio | Aceita: coberta no nível do resultado pela mutação M18 |
| `scripts/validate-docs.ps1` não executado | `pwsh` indisponível neste ambiente; roda na integração contínua |
| **N3 / BL-44** | Pré-existente, registrado no backlog, fora do escopo desta etapa |

> O auditor não afirma ausência de outros defeitos, segurança absoluta nem
> conformidade legal. Auditoria de software não substitui validação
> profissional das regras contábeis e legais.

## Resolução de N4 pelo `arquiteto-senior`

N4 foi corrigido pelo próprio arquiteto, como **ajuste pontual de integração**,
sem abrir nova rodada com o `desenvolvedor-pleno`: a correção são três linhas de
asserção e um comentário, e abrir um ciclo completo de implementação e
auditoria para isso seria desproporcional.

O que foi feito:

1. **Docstring corrigida** em
   `test_mesma_chave_e_conteudo_em_empresas_diferentes_nao_gera_conflito`: ela
   afirmava "mata M15", o que é falso. Agora declara explicitamente que cobre o
   comportamento observável e **não** prova a participação de `empresa_id`,
   apontando para o teste que prova. Comentário que promete cobertura inexistente
   é pior que comentário ausente.
2. **Teste novo** `test_impressao_digital_considera_empresa_id`: compara
   diretamente `_impressao_digital(empresa_id=1, …)` com
   `_impressao_digital(empresa_id=2, …)`, exigindo que difiram, e confirma que a
   impressão é estável para a mesma entrada.

**Verificação do próprio ajuste**, pelo arquiteto e nos mesmos termos exigidos
de qualquer outro código: aplicada a mutação M15 em cópia isolada do
repositório, o teste novo **falha**; sem a mutação, passa. A suíte completa
segue verde. Evidência registrada no commit desta etapa.

Por que manter `empresa_id` no hash, mesmo sendo redundante hoje: se algum dia a
consulta de idempotência deixar de ser escopada por empresa, ou a função for
reaproveitada em outro contexto — um cache global, por exemplo — é esse campo
que impede a escrituração de uma empresa ser confundida com a de outra. É defesa
em profundidade, e agora tem prova.
