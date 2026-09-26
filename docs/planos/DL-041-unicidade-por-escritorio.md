# DL-041 — Unicidade de CNPJ e CPF por escritório

**Demanda:** Fred, 26/09/2026, resposta à PE-68: *"Sim, pode seguir com a PE-68
por escritório"* (RC-115, DE-077). Fecha também a PE-21 e o BL-48.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — isolamento entre escritórios e migração de restrições no
cadastro central. Auditoria independente, uma rodada.
**Branch:** `claude/vigilant-bardeen-jo12l4` → `main`.
**Depende de:** correção única da [DL-039](DL-039-ressalvas-recepcao-e-pessoa-fisica.md)
(BL-533, BL-534), que altera os mesmos arquivos de `apps/empresas`.

## Objetivo

Um escritório nunca descobre, pelo cadastro, pela API ou pelo admin, que uma
inscrição (CNPJ ou CPF) pertence a cliente de outro escritório. Dentro do mesmo
escritório, a inscrição continua única.

## Critérios de aceite

1. Empresa: CNPJ único por `(escritório, CNPJ)` e CPF único por
   `(escritório, CPF)`, no banco; o mesmo CNPJ e o mesmo CPF podem existir em
   escritórios diferentes.
2. Estabelecimento: CNPJ único dentro do escritório da empresa, no banco. O
   desenho (coluna de escritório mantida consistente com a empresa, gatilho ou
   outra alternativa) fica com o implementador, com a decisão e o motivo no
   código; a empresa não muda de escritório (DL-023), o que o desenho pode usar.
3. Duplicata **no mesmo escritório** continua recusada com 400 (API), erro de
   formulário (tela e admin), nunca 500; duplicata **em outro escritório** é
   aceita, pela tela, pela API e pelo admin.
4. A mensagem de duplicata só fala do próprio escritório.
5. Migração em banco vazio e com dados; reversível enquanto não houver inscrição
   repetida entre escritórios (declarar o limite, como na DL-038).
6. A recepção fiscal continua vinculando a nota só à empresa do escritório que
   envia, inclusive quando o mesmo CNPJ existe em dois escritórios (teste com os
   dois).
7. Testes que afirmavam a unicidade global (BL-48, DL-011, DL-038) são
   **atualizados por mudança de requisito** (RC-115), citando-a, e não apagados.
8. Suíte completa, lint, formatação, `manage.py check`, `makemigrations --check`
   e `migrate` em SQLite limpo.

## Responsáveis

`desenvolvedor-pleno`: `apps/empresas/**`, `apps/core/restricoes.py`, testes
afetados em `apps/*/tests`. `auditor-qa`: auditoria da versão integrada.
Reversão: revert do commit e da migração, com o limite do critério 5.

## Auditoria

[Rodada 1](../auditorias/2026-09-26-dl-041-rodada-1.md) em `92b4503` (commit com
mensagem de preservação; o conteúdo é a entrega do `desenvolvedor-pleno`):
**REPROVADA** por U-A1 (média: estabelecimento duplicado no mesmo escritório dá
500 no admin, regressão do critério 3). Objetivo central medido e atendido.
Correção única em andamento: U-A1, U-B1 (gatilho também em `escritorio_id` e
recusa de troca de escritório da empresa no banco), U-B2, U-B3 e, por decisão do
arquiteto, U-B4 (CNPJ de estabelecimento igual ao de **outra** empresa do mesmo
escritório é recusado na aplicação).
