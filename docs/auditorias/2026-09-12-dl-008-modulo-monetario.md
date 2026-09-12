# Auditoria DL-008 — módulo monetário — 2026-09-12

Parecer do `auditor-qa` sobre a etapa
[DL-008](../planos/DL-008-politica-monetaria-e-validacao-de-escala.md), que
implementa a decisão DE-010 e fecha BL-17 e BL-44.

Registrado pelo `arquiteto-senior`, **com os achados preservados
integralmente**.

## Parecer

**APROVADO COM RESSALVAS** — as ressalvas eram condição para integrar, e todas
foram corrigidas antes do commit. Ver a seção final.

## Método

Escopo restrito aos 5 arquivos da DL-008. **14 mutações**, ~40 sondagens de
entrada malformada na view, e — a técnica mais importante desta auditoria —
**execução comparativa do código pré-DL-008** em cópia isolada
(`git show HEAD:…`), para medir se os testes reproduzem de fato o defeito
original.

Verificações: `ruff check` limpo; `manage.py check` limpo;
`makemigrations --check --dry-run` sem alterações; `pytest apps/core
apps/contabilidade -q` → **103 passaram**. `ruff format --check` falhava em 1
arquivo (achado 4).

## Achados

### Achado 1 — MÉDIA: `conta` não numérica ainda produzia 500

- **Requisito:** BL-44 / achado N3; AGENTS.md §8.
- **Localização:** `apps/contabilidade/views.py`, `_extrair_itens` — o
  `except (Conta.DoesNotExist, KeyError, TypeError)` **não capturava
  `ValueError`**.
- **Evidência:** POST com `{"conta": "abc", "tipo": "debito", "valor":
  "100.00"}` → `ValueError: Field 'id' expected a number but got 'abc'` →
  **500**. Variantes lista, dict, float e inteiro gigante devolviam 400
  corretamente; só a string não numérica escapava.
- **Impacto:** erro de servidor por entrada trivial do cliente — a classe de
  defeito que a etapa se propôs a fechar permanecia aberta neste campo.
- **Correção recomendada:** acrescentar `ValueError` ao `except`.
- **Como verificar:** teste parametrizado com `["abc", "", "1x"]` esperando 400.

### Achado 2 — MÉDIA: o teste do achado 4 passava por construção

- **Requisito:** critério 11; BL-17.
- **Evidência:** rodando o cenário do critério 11 (`débito 100,004 + 100,004`
  contra `crédito 200,00`) **contra o código pré-DL-008**: `400, nada gravado` —
  **já era recusado**, porque a soma `200,008` nunca foi igual a `200,00`.

  O mecanismo real é `débito 100,004 + 100,004` contra `crédito 200,008`:
  pré-DL-008 → **201**, gravando `débito 200,00 / crédito 200,01`,
  **desbalanceado**. Com a DL-008 → 400.

  Confirmado por mutação: removendo a validação de escala, os dois testes do
  critério 11 **continuavam passando**.
- **Impacto:** o achado 4 **estava de fato fechado** (o auditor verificou), mas
  o teste que leva seu nome não protegia contra regressão do mecanismo real, e
  a evidência documental do critério era enganosa.
- **Correção recomendada:** usar o cenário real e corrigir o enunciado do
  critério 11 no plano.
- **Como verificar:** o novo teste deve falhar quando a checagem de escala é
  removida.

### Achado 3 — MÉDIA: `quantizar` vazava `decimal.InvalidOperation`

- **Requisito:** contrato do módulo; AGENTS.md §8.
- **Evidência:** `quantizar(Decimal("1E+30"), casas=2, …)` →
  `decimal.InvalidOperation`, não `ValorMonetarioInvalido`. Idem `casas=50`.
  `casas` não era validado: `casas=-2` quantizava para **centenas em silêncio**;
  `casas="2"` ou `None` → `TypeError` cru. O módulo também não declarava o
  contexto decimal assumido, embora se proponha a ser a base dos motores
  fiscais.
- **Impacto:** motor de cálculo futuro receberia exceção fora do contrato,
  virando 500, e a docstring prometia `ValorMonetarioInvalido`.
- **Correção recomendada:** capturar `InvalidOperation` e relançar; exigir
  `casas` inteiro ≥ 0; declarar o contexto e a precisão.

### Achado 4 — MÉDIA: critério 16 não atendido, CI vermelha

- **Localização:** `docs/planos/DL-008-…md` — bloco Python com espaços de
  alinhamento antes do `#`.
- **Evidência:** `ruff format --check .` → `1 file would be reformatted`, e o
  workflow roda exatamente esse comando. Pré-existente desde o commit de
  planejamento; **arquivo do `arquiteto-senior`, não do implementador**.

### Achado 5 — BAIXA: mutação sobrevivente na checagem de zero

`if valor <= 0` → `if valor < 0` mantinha **103/103 passando**. O critério 9 usa
`{0,00; 0,00}`, que o teste pré-existente de total já barrava. Cenário não
coberto: `{débito 100,00; débito 0,00; crédito 100,00}` — pré-DL-008 gravava a
partida zero (verificado: 201); hoje é 400, mas sem teste.

### Achado 6 — BAIXA: tipos aceitos pelo módulo que o serviço não suportava

`criar_lancamento` com `valor="100.00"` (str, tipo que o módulo divulga) →
`TypeError`. `bool` passava: `True` gravava `1,00`, porque `bool` é subclasse de
`int`. `Decimal(0.5)`, construído de float, era aceito — a recusa de `float` é
por tipo, contornável. Nenhum alcançável pela API, mas o serviço é chamável de
outros pontos.

### Achado 7 — BAIXA: parse permissivo reinterpretava a entrada

`"1_000"` gravava **1000,00**; `"  100.00  "` era aceito. É semântica do
`Decimal`, mas reinterpretar em silêncio o que o cliente enviou é impróprio num
sistema contábil.

## Observações sem gravidade

A tabela de ABNT NBR 5891 confere com o documentado em DE-010 em todos os casos
testados (`2,345→2,34`; `2,355→2,36`; `2,365→2,36`; `0,015→0,02`; `0,025→0,02`;
`2,3451→2,35`, negativos e `casas=0`) — **o auditor não afirma conformidade
legal**. `TRUNCAR` com negativo vai em direção a zero, como documentado.
`1E+2`, `1.00E+2`, `100E-2`, `0.00`, `-0.000`, `100.`, `.5`, `+100.00` contam
casas corretamente. Conciliação pós-gravação conferida: débito igual a crédito
no banco em todos os casos aceitos.

**Registrado e não remediado:** lançamentos negativos ou zerados que já tenham
sido gravados pelo defeito antigo não são diagnosticados nem corrigidos, e seu
estorno agora falha com 400. O plano declara não haver cliente real.

## Correções aplicadas antes da integração

Todas as sete ressalvas foram corrigidas pelo `desenvolvedor-pleno`, exceto o
achado 4, que era do `arquiteto-senior` e foi corrigido por ele.

| Achado | Correção |
| --- | --- |
| 1 | `ValueError` acrescentado ao `except`; teste parametrizado |
| 2 | Teste passa a usar `crédito 200,008`; enunciado do critério 11 corrigido no plano |
| 3 | `casas` validado (inteiro ≥ 0, `bool` recusado); `InvalidOperation` relançada como `ValorMonetarioInvalido`; contexto decimal declarado |
| 4 | Alinhamento do bloco Python corrigido; `ruff format --check` limpo (commit `4aba528`) |
| 5 | Teste `{débito 100,00; débito 0,00; crédito 100,00}` acrescentado |
| 6 | `para_decimal` virou pública, recusa `bool` explicitamente; serviço normaliza o valor no início do laço |
| 7 | `PADRAO_VALOR_DECIMAL_SIMPLES` aplicado no módulo e na view, recusando `_`, espaços e notação científica |

**Verificação independente do `arquiteto-senior`** sobre o achado 2, que era o
seu próprio erro: no repositório, os dois testes do critério 11 passam; em cópia
isolada com a validação de escala desligada, **os dois falham**. O teste passou
a proteger de verdade.

Contraprova honesta registrada pelo implementador, e mantida: `Decimal(0.5)`
construído de float **passa** pela validação, porque é exatamente representável.
Está documentado como limite conhecido, não escondido. `Decimal(0.1)` é barrado
por consequência, porque tem 55 casas decimais.

Suíte após as correções: **178 testes**, sem regressão.

> O auditor não afirma ausência de outros defeitos, segurança absoluta nem
> conformidade legal. A correspondência das políticas de arredondamento com cada
> obrigação continua dependendo de conferência em texto oficial e validação do
> Fred, como responsável técnico.
