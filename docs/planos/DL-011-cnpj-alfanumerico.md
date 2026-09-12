# DL-011 — CNPJ alfanumérico

Fecha o **BL-46**, que estava bloqueado por falta da especificação oficial do
dígito verificador. O Fred forneceu o documento em 2026-09-12.

**Estado:** **integrada** na branch de trabalho, aguardando integração à `main`.

| Item | Valor |
| --- | --- |
| Branch de trabalho | `claude/accounting-agent-team-setup-mn6lyf` |
| Branch de destino | `main` |
| Commit de fechamento | `44f9fe6` |
| Evidências | **272 testes**; `ruff check`, `ruff format --check` (127 arquivos), `manage.py check`, `makemigrations --check` limpos; migração aplicada em banco vazio e revertida |
| Verificação pendente | Resultado da integração contínua no remoto. As sete verificações foram **reproduzidas localmente**, o que é evidência, não substituto. |

### As cinco rodadas, e o que cada auditoria encontrou

| Rodada | Commit | Parecer | O que foi corrigido |
| --- | --- | --- | --- |
| 1 | — | [**REPROVADO**](../auditorias/2026-09-12-dl-011-cnpj-alfanumerico.md) | O algoritmo do DV passou; falhou o entorno. Sete achados: sem canonização antes de gravar (duplicata por caixa), máscara recusada no fluxo real, `.upper()` alterando comprimento, fronteira `resto < 2` não exercida, tipo inválido, máscara em posição livre, testes fracos |
| 2 | `fe5387d` | [aprovado com ressalvas](../auditorias/2026-09-12-dl-011-reauditoria-rodada-2.md) | Dez achados. O **R2** mostrou o defeito da máscara **reaparecendo no Django admin**, com a mensagem literal da rodada 1 |
| 3 | `6ae84e5` | [aprovado com ressalvas](../auditorias/2026-09-12-dl-011-reauditoria-rodada-3.md) | Campo de CNPJ próprio (`fields.py`) e `CheckConstraint` no banco. Sete achados novos; o **A1** mostrou o R4 ainda aberto no `PUT`/`PATCH` |
| 4 | `3794378` | [aprovado com ressalvas](../auditorias/2026-09-12-dl-011-auditoria-rodada-4.md) | A1, A2, A3 fechados. O **B1** apontou o `except` largo demais, com falha virando sucesso aparente |
| 5 | `40c61c6` → `44f9fe6` | [aprovado, **pode encerrar**](../auditorias/2026-09-12-dl-011-auditoria-rodada-5-fechamento.md) | B1 e B2 fechados; depois C1, C2, C5, C6 e C7 |

### Duas divergências registradas, e como terminaram

1. **Rodada 4 — o `arquiteto-senior` contrariou o auditor.** Ele aprovou e
   declarou que nada impedia fechar; eu discordei quanto ao **B1** e mandei
   corrigir. Na rodada 5 o auditor **julgou a divergência e concluiu que foi
   acerto**, acrescentando uma razão que eu não tinha: corrigir na raiz trouxe
   cobertura de brinde, porque o `except` largo não era só defeito latente — era
   trecho **intestável**.
2. **Rodada 5 — o auditor corrigiu uma leitura minha.** Eu reportei que mutar os
   quatro `except` matava "exatamente dois testes, nenhum a mais", e apresentei
   isso como precisão. Era o contrário: quatro pontos mutados com dois testes
   disparando significa **dois pontos sem proteção alguma**. Regra que fica para
   a equipe: **mutar um ponto de cada vez; morrer menos que N é buraco, não
   redundância.**

### O que ficou em backlog, declarado e não esquecido

`BL-54` (fortalecer a restrição de banco para o formato completo — **antes de a
DL-010 importar em lote**), `BL-55`, `BL-56`, `BL-57` (alteração de CNPJ sem
trilha de auditoria, preexistente), `BL-58`, e `BL-48` (escopo da unicidade,
que depende de decisão do Fred).

## Migração e reversão — corrigido, era afirmação errada minha

O achado **A4** da rodada 3 pegou uma afirmação falsa que eu tinha escrito aqui:
*"a etapa não cria migração de dados"*. Corrigindo, com o que foi verificado:

**A etapa cria a migração `empresas/0002`.** Ela é de **esquema**, não de dados —
nenhum registro é reescrito —, mas acrescenta duas `CheckConstraint`
**validantes**: `empresa_cnpj_canonico` e `estabelecimento_cnpj_canonico`.

Consequência que eu tinha ignorado, e que o auditor reproduziu em banco
descartável:

> Aplicada sobre base que já contenha CNPJ não canônico, **a migração falha** e o
> *deploy* para. A falha é limpa — a transação é atômica e nada fica pela
> metade —, mas para.

**Antes de aplicar em base existente**, executar e esperar zero nas duas:

```sql
SELECT count(*) FROM empresas_empresa
 WHERE cnpj <> upper(cnpj) OR cnpj ~ '[^A-Z0-9]';
SELECT count(*) FROM empresas_estabelecimento
 WHERE cnpj <> upper(cnpj) OR cnpj ~ '[^A-Z0-9]';
```

O risco real é baixo — antes desta etapa o validador recusava letras e a coluna
é `varchar(14)` —, mas isso é estimativa, não verificação contra a base do Fred.

**Estratégia de reversão, corrigida.** A anterior estava errada: `git revert` dos
commits **não desfaz a restrição no banco**, e o banco continuaria recusando o
que o código revertido volta a produzir. A ordem correta é:

1. `python manage.py migrate empresas 0001` — remove as duas restrições.
2. `git revert` dos commits de código.

O efeito de reverter é voltar a **recusar** CNPJ alfanumérico, que é um defeito
em vigor. Reverter só faz sentido diante de problema maior que esse.

## Por que é urgente

O CNPJ alfanumérico **está em vigor desde 31/07/2026**. O DataLedger hoje
**recusa** qualquer CNPJ com letras: o validador descarta letras e depois exige
14 dígitos, então um CNPJ alfanumérico vira 9 dígitos e é rejeitado.

Não é defeito hipotético nem futuro. É defeito atual.

## Fonte oficial

**Nota Técnica Conjunta CNPJ Alfanumérico — NT 2025.001, versão 1.00, de 25 de
abril de 2025**, do ENCAT, que abrange os ambientes de autorização de NF-e,
NFC-e, CT-e, CT-e OS, GTV-e, MDF-e, BP-e, BP-e TM, NF3e e NFCom.

Base legal: **Instrução Normativa RFB nº 2.229**, de 15/10/2024.

O documento traz implementações de referência: Anexo I (validação do CNPJ em
JavaScript) e Anexo II (validação da chave de acesso em Visual Basic .NET).

## Especificação — transcrita da fonte, não presumida

### Formato

14 posições, assim distribuídas:

| Posições | Conteúdo |
| --- | --- |
| 1 a 8 | **Raiz** — alfanumérica (letras maiúsculas e números) |
| 9 a 12 | **Ordem do estabelecimento** — alfanumérica |
| 13 e 14 | **Dígitos verificadores** — **sempre numéricos** |

Expressão regular oficial do campo: `[A-Z0-9]{12}[0-9]{2}`

Caracteres de máscara removidos antes de validar: `.` `/` `-`

### Cálculo do dígito verificador

O cálculo **continua sendo módulo 11**. A mudança é que cada caractere é
substituído pelo seu **valor na tabela ASCII menos 48**.

Com isso, `0`–`9` mantêm seus valores, e as letras assumem `A=17`, `B=18`,
`C=19`, e assim por diante.

Pesos, conforme o Anexo I: `[6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]`

- **DV1**: soma de `(ASCII(c[i]) - 48) × pesos[i+1]`, para `i` de 0 a 11.
- **DV2**: soma de `(ASCII(c[i]) - 48) × pesos[i]`, para `i` de 0 a 11, **mais**
  `DV1 × pesos[12]`.
- Em ambos: se `soma % 11 < 2`, o dígito é `0`; senão, é `11 - (soma % 11)`.

Rejeitar o CNPJ zerado (`00000000000000`).

### Compatibilidade retroativa — verificada

A nota afirma que o novo cálculo preserva o DV dos CNPJs numéricos existentes.
**Conferido pelo `arquiteto-senior`** contra CNPJs numéricos válidos conhecidos:

| CNPJ | DV real | DV pelo algoritmo novo |
| --- | --- | --- |
| `11222333000181` | 81 | 81 |
| `11444777000161` | 61 | 61 |
| `34028316000103` | 03 | 03 |
| `00000000000191` | 91 | 91 |
| `19131243000197` | 97 | 97 |

**Compatibilidade confirmada.** Nenhum CNPJ já cadastrado deixa de ser válido, e
**nenhum registro precisa ser reescrito**.

Cuidado com a leitura: isto vale para o **dígito verificador**. A etapa cria sim
uma migração de **esquema**, com duas restrições de banco — ver "Migração e
reversão" no início deste plano.

## Ponto que NÃO deve ser implementado

A nota registra, textualmente, que algumas letras — `I`, `O`, `U`, `Q` e `F` —
não deveriam ser aceitas, mas afirma que essa exclusão **"precisa ser
confirmada"**.

**Não implemente essa exclusão.** Recusar CNPJ legítimo por regra não confirmada
é pior do que aceitar um que a Receita venha a não emitir. Registrar como
pendência, e revisitar quando houver confirmação oficial.

## Chave de acesso — especificação obtida, implementação na DL-010

A mesma nota traz o cálculo do DV da **chave de acesso**, que será necessário na
[DL-010](DL-010-recepcao-de-documentos-fiscais.md). Registrado aqui para não se
perder, **mas fora do escopo desta etapa**:

- Estrutura das 44 posições: `cUF`(2) + `AAMM`(4) + `CNPJ`(14) + `mod`(2) +
  `serie`(3) + `nNF`(9) + `tpEmis`(1) + código numérico(8) + `cDV`(1).
- Expressão regular: `[0-9]{6}[A-Z0-9]{12}[0-9]{26}`.
- DV: substituir **todos os 43 caracteres** por ASCII menos 48; somar **do fim
  para o começo** com peso começando em 2, incrementando, voltando a 2 depois de
  9; `dv = 11 - (soma % 11)`, e se `dv >= 10`, então `dv = 0`.

## Escopo

**Dentro:**

- `apps/empresas/validators.py` — validação conforme a especificação acima.
- Normalização de entrada: remover máscara e **converter para maiúsculas** antes
  de validar. A implementação oficial recusa minúsculas; converter na fronteira
  é conveniência de digitação que **não** altera a semântica da validação.
- Garantir que o campo do modelo comporta letras.
- Revisar **todo** ponto que compare ou normalize CNPJ, para que nenhum descarte
  letras.

**Fora:**

- DV da chave de acesso (vai na DL-010).
- Exclusão das letras `I`, `O`, `U`, `Q`, `F` — não confirmada.
- Código de barras CODE-128 dos documentos auxiliares.

## Critérios de aceite

| # | Critério |
| --- | --- |
| 1 | Os cinco CNPJs numéricos da tabela acima continuam válidos |
| 2 | CNPJ alfanumérico com DV correto é **aceito** |
| 3 | CNPJ alfanumérico com DV incorreto é **recusado** |
| 4 | CNPJ com letras nas posições 13–14 é recusado (DV é sempre numérico) |
| 5 | CNPJ com 13 ou 15 caracteres é recusado |
| 6 | `00000000000000` é recusado |
| 7 | Máscara `.` `/` `-` é aceita e removida, em CNPJ numérico e alfanumérico |
| 8 | Entrada em minúsculas é normalizada e validada corretamente |
| 9 | Caractere fora de `[A-Z0-9./-]` é recusado com mensagem útil |
| 10 | Nenhum ponto do sistema descarta letras ao normalizar CNPJ |
| 11 | O campo do modelo persiste CNPJ alfanumérico sem truncar |
| 12 | Comentário no código cita a NT 2025.001 e a IN RFB 2.229 como fonte |
| 13 | Sem regressão; `ruff`, `format --check`, `manage.py check`, `makemigrations --check` limpos |

## Decisões tomadas durante a execução, que o plano original não previa

Registradas a pedido do achado R6 da rodada 2, que apontou — com razão — que
três decisões de engenharia tinham ficado sem registro em lugar algum.

### 1. A correção foi estendida a `Estabelecimento`

O plano fala em "o campo do modelo", no singular, pensando em `Empresa`.
`Estabelecimento.cnpj` tem `unique=True` e passa pelo mesmo caminho de API sem
`full_clean()`, logo tinha o mesmo defeito. Decisão do `arquiteto-senior`:
estender. Deixar o defeito lá seria incoerente e viraria achado na etapa
seguinte.

### 2. Espaço em branco na borda é tolerado

Ampliação de contrato não prevista no plano. Motivo: o `CharField` de formulário
do Django já removia o espaço, e a API não — o mesmo valor era aceito num
caminho e recusado no outro. CNPJ colado de planilha vem com espaço, e com
frequência.

### 3. O critério 7 foi **estreitado** — e isto tem consequência para a DL-010

Esta é a decisão que mais importa registrar.

O plano transcreve da nota técnica: "caracteres de máscara removidos antes de
validar: `.` `/` `-`". A implementação **não** faz remoção cega desses
caracteres: reconhece **apenas o leiaute exato** `XX.XXX.XXX/XXXX-XX`.

Motivo: a remoção cega aceitava entradas absurdas como `../-11222333000181`,
que só por coincidência sobram com 14 caracteres — achado 6 da rodada 1.

É a decisão certa para **digitação humana**. Mas é **mais restritiva do que a
letra do plano**, e cria risco declarado para a
[DL-010](DL-010-recepcao-de-documentos-fiscais.md): arquivo de terceiro que
traga CNPJ com separação parcial, como `11222333/0001-81`, **será recusado na
importação**.

Consequência de projeto: a DL-010 **não deve** presumir que `normalizar_cnpj`
aceita qualquer pontuação. Se um formato de origem real usar separação parcial,
isso é decisão nova — normalizar na borda do importador, ou ampliar a regra —
e não pode ser resolvida em silêncio dentro do validador.

## Impacto

- **Dados:** nenhum registro é reescrito. Compatibilidade retroativa do dígito
  verificador verificada. **Há migração de esquema** (`empresas/0002`), com as
  duas restrições e a pré-checagem descritas no início deste plano.
- **Contratos:** ampliação — passa a aceitar o que hoje recusa.
- **Risco de não fazer:** empresa com CNPJ novo não consegue ser cadastrada, e
  documento fiscal dela não poderá ser importado.
