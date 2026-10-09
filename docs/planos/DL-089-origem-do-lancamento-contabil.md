# DL-089 — Contabilidade: origem e documento de origem do lançamento (BL-72 e BL-73)

**Demanda:** ordem do Fred de 09/10/2026 (RC-175). A
[revisão do fiscal](../projeto/revisao-do-fiscal-2026-10-09.md) (lacuna A6)
põe esta etapa como pré-requisito técnico da integração fiscal → contábil.
A [consulta da classificação fiscal](../projeto/consultas/2026-10-09-contador-senior-classificacao-fiscal.md)
pede a mesma coisa (peça 3, modelo contábil). **Corre em paralelo** às
etapas do fiscal, porque só toca `apps/contabilidade`.
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1), porque muda o
modelo do lançamento contábil, que é imutável e protegido por gatilho no
banco. A auditoria faz uma rodada, uma correção e uma reconferência.

## O problema

`LancamentoContabil` não guarda de onde veio. Com isso:

- não se distingue lançamento digitado de lançamento gerado;
- não se chega da nota ao lançamento, nem do lançamento à nota;
- a regeração controlada (BL-66) e a integração fiscal → contábil ficam
  impossíveis.

## Escopo

1. **Origem:** campo de origem com valores controlados:
   - `manual`, o padrão de tudo o que existe hoje;
   - `importacao`, para a importação de TXT e Excel da DL-077, se o código a
     identificar com segurança;
   - `escrita_fiscal`, reservado para a integração.

   A origem é gravada na criação e **não muda depois**: o gatilho de
   imutabilidade do banco passa a cobrir os campos novos.
2. **Documento de origem:** referência ao documento que originou o
   lançamento, por tipo e identificador estável.
   - Exemplos: a escrituração de NF-e, a escrituração de NFS-e, o lote de
     importação.
   - A referência é genérica e sem chave estrangeira entre apps, para não
     acoplar a contabilidade ao fiscal.
   - Ela entra também na **chave natural** de idempotência (BL-66).
3. **Consultas nos dois sentidos**, sempre com isolamento por escritório e
   empresa:
   - do documento aos lançamentos;
   - do lançamento ao documento.
4. **Permissão própria (BL-73):**
   - estornar ou alterar lançamento de origem automática exige uma
     permissão distinta da de lançar, verificada no servidor;
   - sem ela, 403 e nada muda;
   - o estorno de lançamento automático fica marcado.
5. **Migração.**
   - É aditiva: o que já existe recebe `manual`.
   - O backfill respeita os gatilhos de imutabilidade. Siga o padrão do
     backfill da DL-016 F5, documentado no modelo.
   - A reversão recusa se houver lançamento de outra origem.
6. **Tela e API:**
   - o lançamento mostra a origem e o link ao documento, quando houver;
   - o Razão e o Diário permitem filtrar por origem.

**Fica fora:**
- a geração de lançamento pelo fiscal (é a integração, depois da DL-087);
- a regeração (BL-66);
- a configuração contábil por natureza e por imposto (BL-74).

## Critérios de aceite

1. Todo lançamento existente fica com origem `manual`, e os novos que vêm
   dos caminhos atuais recebem a origem certa.
2. A origem e o documento de origem não mudam depois de gravados, nem pelo
   ORM nem por SQL direto (gatilho), com teste no PostgreSQL.
3. As consultas nos dois sentidos funcionam e isolam escritórios e
   empresas.
4. **Permissão:** sem a permissão nova, o estorno de lançamento automático
   dá 403. Com ela, passa e fica marcado.
5. Os testes da contabilidade passam sem mudar expectativa; as exceções
   ficam listadas e justificadas.
6. **Mutação:** cada um destes defeitos derruba teste:
   - origem editável;
   - consulta sem filtro de empresa;
   - estorno de lançamento automático sem a permissão.
7. Regressão completa numa única invocação. Migração aditiva e reversível.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — modelo, migração e gatilho, serviços, permissão, API e tela | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/contabilidade/` (modelos, migração, serviços, permissões, API, views, templates da contabilidade), `apps/core/restricoes.py` e o inventário de trilha, se a guarda pedir; testes `test_dl089_*` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |
