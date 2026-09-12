# DL-011 — CNPJ alfanumérico

Fecha o **BL-46**, que estava bloqueado por falta da especificação oficial do
dígito verificador. O Fred forneceu o documento em 2026-09-12.

**Estado:** em desenvolvimento.

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
**nenhuma migração de dados é necessária**.

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

## Impacto

- **Dados:** nenhum. Compatibilidade retroativa verificada; nenhuma migração.
- **Contratos:** ampliação — passa a aceitar o que hoje recusa.
- **Risco de não fazer:** empresa com CNPJ novo não consegue ser cadastrada, e
  documento fiscal dela não poderá ser importado.
