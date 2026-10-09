# DL-086 — Fiscal: documentação e painel alinhados ao que existe

**Demanda:** ordem do Fred de 09/10/2026 (RC-175), revisão completa do fiscal.
A [revisão do módulo fiscal](../projeto/revisao-do-fiscal-2026-10-09.md),
seção 3, achou afirmações desmentidas pelo código. Isso fere a instrução
permanente do Fred de 13/09/2026 ("nunca esqueça de atualizar").
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 3 (documentação), com uma
mudança de código pequena no painel do módulo (nível 2). A verificação é
feita pelo `auditor-qa` sobre a versão integrada.

## Escopo

1. **Documentos.** Corrigir as inconsistências I3 e I7 a I17 da revisão, em
   cada arquivo:
   - `docs/projeto/paridade/fiscal.md`;
   - `docs/projeto/mapa-funcional-fiscal.md`: tabelas "O que já existe" e
     "DataLedger" e o inventário de relatórios;
   - `docs/projeto/catalogo-de-relatorios.md`: a afirmação sobre o fiscal;
   - `docs/planos/DL-067-plano-do-modulo-fiscal.md`: linhas "a numerar" da
     tabela de execução e a divergência do PIS/Cofins, que agora aponta para
     a PE-90 e a HI-145.

   A regra de todas as correções: o texto descreve **capacidade**, e o estado
   continua só no [estado.md](../agents/estado.md). Onde a afirmação velha
   tiver valor histórico, ela fica riscada, com a data e o motivo.
2. **Fonte de referência.** Atualizar a nota de
   `docs/projeto/fontes-de-referencia.md` que diz que a central de soluções do
   sistema de referência não é legível por agente. A pesquisa de 09/10/2026 a
   leu por `curl` com UA de navegador. A regra de uso sem cópia continua.
3. **Painel do módulo fiscal** (`apps/core/module_homes.py`, cerca das linhas
   750 a 916):
   - o banner deixa de dizer que o módulo só recebe NFS-e e que a apuração
     não existe;
   - ele passa a dizer o que existe (recepção de NFS-e, NF-e e NFC-e;
     escrituração; apuração para conferência) e o que não existe (guia,
     transmissão, ICMS, PIS/Cofins, livros);
   - os indicadores de NF-e entram ao lado dos de NFS-e, na medida em que o
     domínio já os ofereça sem consulta nova (BL-681, item 2; BL-684, item
     2);
   - teste do texto e dos indicadores.
4. **Teste de documentação.** Se `apps/core/tests/test_documentacao_do_estado.py`
   tiver uma lista de afirmações proibidas, entram nela as frases desmentidas
   do fiscal, para que não voltem.

## Critérios de aceite

1. Nenhum dos arquivos acima afirma que o fiscal "só recebe NFS-e" ou que a
   escrituração e a apuração "não existem".
2. O banner do painel descreve o que existe e o que não existe, com teste.
3. As afirmações desmentidas entram na guarda do teste de documentação, se
   ela existir.
4. `ruff`, `manage.py check`, o teste de documentação e a suíte de
   `apps/core` passam.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| Documentos e painel | `auxiliar-implementacao` (Haiku) | os quatro documentos do item 1, `fontes-de-referencia.md`, `apps/core/module_homes.py`, testes do painel e de documentação |
| Verificação | `auditor-qa` (Sonnet) | sem escrita |
