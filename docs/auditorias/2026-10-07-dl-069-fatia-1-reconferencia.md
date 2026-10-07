# Reconferência: DL-069, fatia 1 (única, §3.1)

**Registro do arquiteto:** relatório transcrito **integralmente**, sem edição,
supressão nem suavização de achado. Rodada anterior:
[rodada 1](2026-10-07-dl-069-fatia-1-rodada-1.md). Plano:
[DL-069](../planos/DL-069-travas-no-banco.md). Pelo §3.1 **não há terceira
rodada**. O tratamento está no fim, separado do texto do auditor.

---

**Versão:** `/home/user/DataLedger`, HEAD `de7fd43`, sobre `c163990`. Python
3.13.16 e PostgreSQL. Não deleguei. A árvore ficou limpa (`git status` vazio) e
os bancos temporários foram removidos.

## Veredito: APROVADO COM RESSALVAS

Não achei defeito introduzido pelas correções, nem falha de gravidade alta ou
bloqueadora. Restam dois achados de gravidade baixa, R1 e R2. Isto não é
garantia de ausência de defeitos.

## Achados anteriores

| Achado | Fechado? | Evidência |
| --- | --- | --- |
| A1 | **Parcial** | O plano (critério 4), o comentário da `0011` e o BL-644 deixam de afirmar que "a varredura cobra" o registro. O comentário da `0011` (linhas 76-81) diz que nenhuma verificação exige o registro e que a tela futura precisa usar `restricao_como_400`. O BL-644 registra "sem guarda nova". Resta uma contradição de texto no critério 4 (R1). |
| A2 | **Fechado para o que foi pedido** | Os 8 testes novos passam. A mutação "encerramento aceita `criado_em`" falha com 1 reprovado e 48 aprovados, em `test_reencerramento_com_coluna_imutavel_junto_e_recusado[criado_em]`. Sobraram lacunas vizinhas (R2). |
| A3 | **Fechado** | O limite está declarado na `0011` (linhas 69-75: "O GATILHO VÊ COLUNAS, NÃO A TRILHA") e no plano ("Limite declarado (A3)"). A decisão sobre a amarração à transição também foi para o plano. |

## Migração (item 4)

O diff da `0011` entre `9713aa9` e HEAD tem 14 linhas, todas comentário. O
arquivo sem linhas `#` é idêntico ao de `9713aa9`, então o SQL não mudou.

## Mutações

Cópias via `git archive` em `/tmp/claude-0/…/scratchpad/mut`, um banco por
cópia, repositório intocado. Cada mutação acrescenta uma coluna às duas listas
da transição na função `livro_caixa_recusar_alteracao_do_fechamento`.

| Mutação | Resultado |
| --- | --- |
| Encerramento aceita `criado_em` | Morre (1 reprovado) |
| Encerramento aceita `ano`, `mes` ou `empresa_id` | Morre, cada uma no teste parametrizado novo |
| Encerramento aceita `motivo_reabertura` | Morre (teste antigo) |
| Reabertura aceita `ano`, `empresa_id` ou `criado_em` | Morre, cada uma no teste novo |
| Reabertura aceita `mes` | Morre (2 reprovados) |
| Reabertura aceita `fechado_por_id` | Morre (teste antigo) |
| **Reabertura aceita `fechado_em`** | **Sobrevive** (49 aprovados) |
| **Encerramento aceita `reaberto_em`** | **Sobrevive** (49 aprovados) |
| **Encerramento aceita `reaberto_por_id`** | **Sobrevive** (49 aprovados) |

## Regressão

- **Suíte completa** (`dataledger_auditor`): 4.944 aprovados, 1 reprovado e 53
  pulados, em 548 s.
  - A conta fecha: 4.936 mais 8.
  - O reprovado é o mesmo da rodada 1
    (`test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`),
    de ambiente (Python 3.13).
- **Verificações:** `ruff check .` limpo; `ruff format --check .` com 371
  arquivos já formatados; `manage.py check` sem problemas; `makemigrations
  --check --dry-run` com "No changes detected"; `gerar_agentes.py --verificar`
  com "7 papéis, todos os derivados sincronizados".

## Documentação

- **Validador.** Reproduzi o `validate-docs.ps1` em Python, com a mesma regra
  de bloco de código na coluna 0, sobre os 235 `.md` do repositório. Não achei
  problema de título, espaço no fim da linha, nova linha final ou link
  relativo.
- **Relatório da rodada 1.** O bloco de código que reprovaria o validador
  (recuado, em `c163990`) está corrigido em `de7fd43`.
- **`estado.md`.** Está fiel ao que aconteceu:
  - dá 4.936 aprovados para a rodada 1, o que é correto;
  - diz "8 testes";
  - diz "Falta a reconferência e o PR".
  - Quando esta reconferência for registrada, ele precisa ser atualizado, o que
    cabe ao `arquiteto-senior`. O total passa a 4.944 aprovados.
- **BL-644.** Existe e está correto.

## Achados novos

**R1 — baixa — O critério 4 do plano ainda abre com a promessa que o código não
cumpre**
- **Requisito:** DL-069, critério 4.
- **Localização:** `docs/planos/DL-069-travas-no-banco.md:62-63`.
- **Evidência:** a frase "A recusa chega ao usuário pela tela e pela API como
  mensagem em português, nunca como erro 500" continua como critério. O
  parágrafo seguinte diz que hoje a recusa não chega ao usuário, porque nenhuma
  porta faz UPDATE ou DELETE. O critério continua prometendo mais do que o
  código faz, e a ressalva só aparece depois.
- **Impacto:** quem ler só a primeira frase conclui que a tela e a API tratam a
  recusa.
- **Correção:** reescrever o critério como "a mensagem está registrada e em
  português. Nenhuma porta provoca a recusa hoje. A porta futura traduz com
  `restricao_como_400`", e mover o histórico para o fim.
- **Verificação:** a leitura do critério 4 sozinho não pode sugerir cobertura de
  tela ou API.
- **Responsável:** `arquiteto-senior`.

**R2 — baixa — Colunas da transição oposta ainda não têm teste**
- **Requisito:** DL-069, critérios 1 e 2 (amarração à transição).
- **Localização:**
  `apps/livro_caixa/tests/test_dl069_livro_caixa_imutavel_no_banco.py` (os 8
  testes novos e
  `test_transicao_legitima_com_coluna_de_fora_da_transicao_e_recusada`); SQL da
  `0011`, linhas 135-148.
- **Evidência:**
  - Sobrevivem as mutações "reabertura aceita `fechado_em`", "encerramento
    aceita `reaberto_em`" e "encerramento aceita `reaberto_por_id`" (tabela
    acima).
  - Os testes cobrem só as quatro colunas imutáveis, `fechado_por_id` na
    reabertura e `motivo_reabertura` no encerramento.
  - O SQL real recusa as três por construção. Falta só o teste que prove isso.
- **Impacto:** uma regressão futura poderia deixar o reencerramento apagar ou
  regravar a trilha de reabertura, ou a reabertura reescrever `fechado_em`, sem
  nenhum teste acusar.
- **Correção:** parametrizar sobre a coluna da transição oposta.

```python
@so_postgresql
@pytest.mark.parametrize("coluna,valor", [("reaberto_em", lambda: timezone.now()),
                                          ("reaberto_por_id", lambda c: c["gestor"].pk)])
# encerramento sobre _mes_reaberto: estado=ENCERRADO + fechado_em + fechado_por_id + {coluna: novo}
# reabertura sobre _mes_encerrado: estado=ABERTO + reaberto_em + reaberto_por_id + motivo + fechado_em=timezone.now()
```

  Cada caso deve usar `_recusado(RESTRICAO_FECHAMENTO, …)` e conferir
  `_linha(...) == antes`.
- **Verificação:** as três mutações acima passam a reprovar.
- **Responsável:** `desenvolvedor-pleno`.

**Observação, sem achado:** o plano e a `0011` chamam o limite de "o mesmo do
BL-569", mas o texto do BL-569 trata de `ON CONFLICT DO NOTHING` e do marcador
forjado. O sentido (escrita acidental, não acesso de dono) é o mesmo, mas a
referência é frouxa.

## Não verificado

- Suíte em SQLite e em Python 3.14 (CI).
- Concorrência real entre encerrar e reabrir com o gatilho ligado.
- `pg_restore --disable-triggers` (PE-07).
- Privilégios do papel dono das tabelas (implantação).
- Fluxo de ponta a ponta de tela e API. Dependi da suíte e da rodada 1; não
  refiz o script próprio.
- Regra contábil ou legal. Auditoria de software não substitui validação
  profissional.

---

## Tratamento (arquiteto-senior, 07/10/2026)

O ciclo de auditoria da fatia 1 termina aqui. As correções abaixo **não**
passaram por auditoria independente. A verificação delas é a dos testes com
mutação e a da CI do PR.

| Achado | Decisão |
| --- | --- |
| R1 | **Corrigido.** O critério 4 agora diz só o que vale: a mensagem está registrada, nenhuma porta provoca a recusa hoje, e a porta futura traduz com `restricao_como_400` (BL-644). O texto antigo foi para um parágrafo de histórico |
| R2 | **Corrigido.** Três testes novos: o reencerramento não reescreve `reaberto_em` nem `reaberto_por_id`, e a reabertura não reescreve `fechado_em`. As três mutações que sobreviviam agora morrem, cada uma no seu teste (1 reprovado e 51 aprovados por mutação). Com o código real: 52 aprovados |
| Observação | **Corrigida.** O plano e a migração falam em "o princípio do BL-569, que trata do livro contábil" |
