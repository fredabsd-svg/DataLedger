# DL-073 — Fiscal: validador de conformidade IBS/CBS das NFS-e recebidas

**Demanda:** ordem do Fred de 08/10/2026 (RC-164), *"codar o fiscal por
completo"*; etapa 4 do roteiro de execução do
[DL-067](DL-067-plano-do-modulo-fiscal.md), que pode correr em paralelo às
etapas do Simples. **Estado:** [fonte única](../agents/estado.md).
**Branch:** `ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 2 (§3.1) —
relatório de conferência; nada é calculado para guia, nenhum dado gravado
muda. Responde à PE-39 como **hipótese** (HI-61), até o Fred validar.

## Problema

Desde 01/10/2026 o destaque de IBS/CBS na NFS-e é **obrigatório** para a
maioria dos serviços da LC 116 (01/12/2026 para outras categorias; Simples
só a partir de 01/01/2027 para quem optar pelo regime regular). Até
31/12/2026 a ausência **não rejeita** a nota, mas é "desconformidade"
(P&R NFS-e v1.1, itens 15.1, 15.2 e 15.4). Os clientes do Presumido emitem
pelos próprios emissores, e o escritório precisa saber quais notas saíram
sem o grupo ou com ele incoerente — antes da intimação. O DataLedger já
**guarda o XML íntegro** de cada NFS-e recebida (DE-074) e não lê o grupo.

## Fontes (lidas em 08/10/2026)

Todas registradas em
[consultas/2026-10-08-leiaute-ibscbs-nfse.md](../projeto/consultas/2026-10-08-leiaute-ibscbs-nfse.md):
XSD NFS-e v1.01 (09/02/2026); Anexo I v1.01 (regras E1515, E1517, E0850,
E1530 e seguintes); Anexo VI v1.04.01 e NT 009 v1.01 (11/09/2026); P&R NFS-e
v1.1 (22/09/2026); LC 214/2025 arts. 343 (IBS 0,1%) e 346 (CBS 0,9%), lidos
no Planalto; Informe Técnico 2025.002 v1.60 (2026: `pIBSUF` 0,1, `pIBSMun`
0, `pCBS` 0,9).

## Escopo

**Entra:** um leitor do grupo IBS/CBS a partir do `xml_original` já gravado
(sem migração, sem copiar campo para tabela — reprocessável) e um relatório
de conformidade por empresa **prestadora** e competência (`dCompet`), em
**modo aviso** (HI-59, HI-61), com estas verificações:

1. **Leiaute 1.00:** o grupo não existe nesse leiaute — a nota é listada como
   "leiaute sem grupo IBS/CBS", sem aviso de desconformidade.
2. **Presença** (leiaute 1.01, competência a partir de 01/10/2026, prestador
   **não optante** do Simples segundo a própria nota): grupo `IBSCBS`
   ausente → aviso, citando o cronograma do P&R 15.1 (01/10 ou 01/12/2026,
   conforme a categoria do serviço, que o sistema **não** classifica).
   Prestador optante: sem aviso em 2026 (P&R 15.4).
3. **Coerência entre DPS e NFS-e:** grupo da DPS sem o da NFS-e, ou o
   contrário (E1515, E1517).
4. **CST e cClassTrib:** presentes e no formato (3 e 6 dígitos), lidos **nas
   duas posições** que as fontes oficiais divergem (`valores/trib/gIBSCBS/` no
   XSD de produção; `valores/trib/` na NT 009). A existência do código na
   tabela oficial **não** é verificada nesta etapa — a tabela ainda não é
   importada (fica para a etapa das tabelas oficiais), e o relatório diz isso.
5. **Alíquotas de teste de 2026:** `pCBS` 0,90, `pIBSUF` 0,10, `pIBSMun` 0
   para competência em 2026 (LC 214 arts. 343 e 346; Informe 2025.002);
   diferente → aviso nomeando o esperado e a fonte.
6. **Aritmética:** `vCBS ≈ vBC × pCBS/100`, `vIBSUF ≈ vBC × pIBSUF/100`,
   `vIBSMun ≈ vBC × pIBSMun/100`, e `vBC` contra a fórmula da E1530 de 2026
   (`vServ − descIncond − vCalcReeRepRes − vISSQN − vPIS − vCOFINS`), com
   tolerância de **R$ 0,01** — a margem da calculadora oficial. **Não** há
   regra oficial de arredondamento; o validador não inventa uma.

Tela: relatório por empresa e competência, lista de notas com os avisos e a
fonte de cada um, e a nota de que é conferência (classe 1 da
[personalização](../projeto/personalizacao-de-relatorio.md)), não
demonstração. Segue a [direção de arte](../projeto/direcao-de-arte.md).

**Fica fora:** apuração de CBS/IBS (não há em 2026); importação da tabela
cClassTrib; validação contra a calculadora oficial; notas em que a empresa é
tomadora; campos que só existem na NT 009 e ainda não no XSD de produção.

## Critérios de aceite

1. Nota 1.00 → "leiaute sem grupo", nunca "desconforme".
2. Nota 1.01 de prestador não optante, competência ≥ 01/10/2026, sem
   `IBSCBS` → aviso de ausência com a citação do cronograma; mesma nota com
   competência 09/2026 → sem aviso de ausência.
3. Prestador optante do Simples em 2026 → sem aviso de ausência.
4. CST/cClassTrib lidos nas duas posições; formato inválido → aviso.
5. Alíquota diferente da de teste em 2026 → aviso com o valor esperado e o
   dispositivo; alíquotas certas → nenhum aviso.
6. Valor fora da tolerância de R$ 0,01 → aviso; dentro → nenhum aviso.
   Teste nos dois lados da fronteira (0,01 e 0,02).
7. `vBC` contra a fórmula da E1530 com a mesma tolerância.
8. Decimais lidos como `Decimal`, aceitando `0.9` e `0.90`.
9. XML malformado ou sem o elemento esperado → aviso nomeado, nunca 500.
10. Isolamento: empresa de outro escritório → 404; papel sem permissão de
    consulta fiscal → recusa; CLIENTE não vê.
11. Desempenho: o relatório de um mês não faz uma consulta por nota além da
    leitura do XML (medido com 2 e 20 notas).
12. Não regressão: suíte completa sem reprovação nova; `ruff`, `check` e
    `makemigrations --check` limpos.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| Domínio, tela e testes | `auxiliar-implementacao` (Haiku, RC-164), em cópia isolada | `apps/fiscal/ibscbs.py` (novo), `apps/fiscal/views_conformidade.py` (novo), `templates/fiscal/conformidade_ibscbs.html` (novo), uma linha em `apps/fiscal/urls_web.py`, `apps/fiscal/tests/test_dl073_*.py` (novos, com gerador próprio de XML sintético) |
| Revisão | `arquiteto-senior` | integração; nível 2 não exige auditoria por rodada, mas a primeira entrega do validador passa pelo `auditor-qa` junto com a DL-072 |

## Reversão

Sem migração e sem dado gravado: reverter é reverter o commit.
