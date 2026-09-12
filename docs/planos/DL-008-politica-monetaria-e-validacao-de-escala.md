# DL-008 — Política monetária e validação de escala

Implementa a decisão **DE-010** ([decisoes.md](../projeto/decisoes.md)) e fecha
os itens **BL-17** e **BL-44** do [backlog](../projeto/backlog.md).

Autorizado pelo Fred em 2026-09-12, com a decisão de arredondamento delegada ao
`arquiteto-senior`.

**Estado:** em desenvolvimento.

## Objetivo

Duas coisas, ligadas pela mesma causa:

1. Criar o **módulo monetário compartilhado**, com políticas de arredondamento
   explícitas e nomeadas, para que todo motor de cálculo futuro (fiscal, folha,
   honorários) parta de uma base correta e rastreável.
2. Fechar o **achado 4** da auditoria de 2026-09-11 (BL-17): hoje os validadores
   de sinal e escala do `ItemLancamento` **não executam** no caminho de
   gravação, então partida **negativa** é aceita e valor com mais de duas casas é
   arredondado pelo banco **depois** da checagem `débito = crédito`. E o
   **BL-44** (achado N3): entrada do corpo acima dos limites do banco vira
   **500** em vez de 400.

## Por que os dois juntos

São a mesma falha vista de dois ângulos: o sistema confia em limites do banco
como se fossem validação de entrada. O banco não valida, ele **falha** — ora
truncando em silêncio, ora estourando com 500. A correção é validar na
fronteira, com escala e política declaradas.

## Escopo delimitado

**Dentro:**

- `apps/core/dinheiro.py` (novo): políticas e função de quantização.
- `apps/core/tests/` : testes do módulo.
- `apps/contabilidade/services.py` e `views.py`: validação de sinal, escala e
  limites de entrada.
- `apps/contabilidade/tests/`.

**Fora, declarado:** não criar motor de cálculo fiscal, de folha ou de
honorários. Este plano entrega a **base**; os motores dependem de requisitos que
o Fred ainda não definiu (PE-01, PE-03). Não inventar alíquota, prazo, fórmula
ou leiaute.

## Contrato do módulo monetário

```python
class PoliticaArredondamento(models.TextChoices):
    ABNT_NBR_5891 = "abnt_nbr_5891"  # meio para o par (ROUND_HALF_EVEN)
    MEIO_PARA_CIMA = "meio_para_cima"  # ROUND_HALF_UP
    TRUNCAR = "truncar"  # descarta excedente (ROUND_DOWN)


def quantizar(valor, *, casas, politica):
    """Reduz `valor` a `casas` decimais aplicando `politica`.

    `politica` é OBRIGATÓRIA e não tem padrão: ninguém deve arredondar por
    acidente (DE-010).
    """
```

> Atenção ao editar este documento: o `ruff` desta versão **formata blocos de
> código Python dentro de Markdown**, e `ruff format --check .` roda na
> integração contínua. Comentário alinhado com espaços extras em bloco
> ```python``` **quebra a CI**. Foi o que aconteceu com a primeira versão deste
> plano.

Requisitos do módulo:

1. `politica` é **argumento obrigatório**, sem valor por omissão. Chamar sem ela
   é erro de programação e deve falhar.
2. Aceita `Decimal`; recusa `float` explicitamente, com mensagem que explique o
   porquê. Aceita `str` e `int`, convertendo por `Decimal`.
3. Recusa `NaN` e infinitos (`Infinity`, `-Infinity`) — são a origem do 500 do
   BL-44.
4. `TRUNCAR` descarta em direção a zero, e isso vale também para negativos:
   documente o comportamento escolhido, porque truncar `-1,999` pode dar `-1,99`
   ou `-2,00` conforme a direção.
5. Nunca usa `float` internamente.
6. Função auxiliar `casas_decimais(valor)`, para validar escala sem arredondar.

## Validação na escrituração (BL-17)

Em `criar_lancamento`, **antes** da checagem `débito = crédito`:

1. **Sinal:** valor de partida deve ser **maior que zero**. Partida negativa é
   recusada com `LancamentoInvalido`. Débito e crédito são expressos pelo campo
   `tipo`, não pelo sinal do valor — permitir negativo cria duas representações
   para a mesma coisa e quebra os totais.
2. **Escala:** valor com mais de **2 casas decimais** é **recusado**, não
   arredondado (DE-010). Mensagem deve dizer o valor recebido e a escala aceita.
3. A ordem importa: recusar escala **antes** de somar débitos e créditos. Se a
   soma vier primeiro, o arredondamento do banco pode reintroduzir o achado 4.

## Validação de limites de entrada (BL-44)

Na view de criação de lançamento, devolver **400** com mensagem útil, nunca 500:

- `historico` acima de 300 caracteres (limite do campo).
- `valor` que não caiba em `max_digits=18, decimal_places=2`.
- `valor` não finito (`NaN`, `Infinity`, `-Infinity`).
- `data` fora de faixa aceitável pelo banco.

## Critérios de aceite

| # | Critério |
| --- | --- |
| 1 | `quantizar` sem `politica` falha (argumento obrigatório) |
| 2 | `ABNT_NBR_5891`: `2,345` → `2,34` e `2,355` → `2,36` em 2 casas (meio para o par) |
| 3 | `ABNT_NBR_5891`: 5 seguido de algarismo diferente de zero sobe — `2,3451` → `2,35` |
| 4 | `MEIO_PARA_CIMA`: `2,345` → `2,35` |
| 5 | `TRUNCAR`: `2,349` → `2,34`; comportamento com negativo documentado e testado |
| 6 | `quantizar` recusa `float` com mensagem explicativa |
| 7 | `quantizar` recusa `NaN` e infinitos |
| 8 | Partida com valor **negativo** → 400, nada gravado |
| 9 | Partida com valor **zero** → 400 |
| 10 | Partida com **3 casas decimais** → 400, **recusada e não arredondada** |
| 11 | O cenário exato do achado 4 (`débito 100,004 + 100,004` contra `crédito 200,008`) → 400, nada gravado |
| 12 | `historico` com 5000 caracteres → 400, não 500 |
| 13 | `valor` com 25 dígitos → 400, não 500 |
| 14 | `valor` `"Infinity"` e `"NaN"` → 400, não 500 |
| 15 | Sem regressão: a suíte inteira continua passando |
| 16 | `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check --dry-run` |

Não deve haver migração nova: a mudança é de validação e de um módulo novo, sem
alteração de campo.

### Correção do critério 11 — erro de redação do `arquiteto-senior`

A primeira versão deste critério pedia `débito 100,004 + 100,004` contra
**`crédito 200,00`**. Esse cenário **nunca exercitou o achado 4**: a soma
`200,008` jamais foi igual a `200,00`, então já era recusado **antes** da
correção. O teste escrito a partir dele passava por construção, e a auditoria
provou por mutação — removendo a validação de escala, os testes do critério 11
continuavam passando.

O mecanismo real do achado 4 é `débito 100,004 + 100,004` contra **`crédito
200,008`**:

- antes da correção: **201**, gravando `débito 200,00 / crédito 200,01` —
  desbalanceado **no banco**, porque a igualdade era conferida antes do
  arredondamento da coluna;
- depois da correção: **400**, nada gravado.

O critério foi corrigido acima. O erro foi de quem escreveu o plano, não de quem
o implementou — e só apareceu porque o auditor rodou o código **pré-correção**
em cópia isolada para medir se o teste reproduzia o defeito, em vez de confiar
no enunciado. **Técnica a repetir:** um teste de regressão só vale se falhar
contra a versão que tinha o defeito.

## Impacto

- **Dados:** fecha um caminho que gravava lançamento desbalanceado. É o objetivo.
- **Contratos:** requisição que hoje é aceita e grava valor arredondado passa a
  ser **recusada com 400**. É mudança de comportamento **desejada** — o que era
  aceito estava errado. Nenhum cliente real existe ainda.
- **Cálculos:** nenhum cálculo existente muda; o módulo é base para os futuros.
- **Migração:** nenhuma.

## Reversão

Reverter o commit. Sem alteração de esquema, sem dado a recuperar.

## Divisão de responsabilidade

| Agente | Arquivos |
| --- | --- |
| `arquiteto-senior` | `docs/**` |
| `desenvolvedor-pleno` | `apps/core/**`, `apps/contabilidade/**` |
| `auditor-qa` | nenhum (somente leitura) |

## Limite declarado

Este plano implementa **engenharia monetária**, não homologação tributária. A
tabela de métodos por obrigação está em DE-010 com as fontes; a regra aplicável
a cada tributo deve ser conferida em texto oficial e validada pelo Fred antes de
qualquer cálculo destinado a uso real.
