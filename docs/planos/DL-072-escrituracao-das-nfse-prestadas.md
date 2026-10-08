# DL-072 — Fiscal F1: escrituração das NFS-e prestadas

**Demanda:** ordem do Fred de 08/10/2026 (RC-164): *"comece a codar o fiscal
por completo"*. Primeira etapa do roteiro de execução registrado na
[DL-067](DL-067-plano-do-modulo-fiscal.md).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1) — a nota
escriturada é a base do faturamento, do RBT12 e do DAS que o contador entrega.
Auditoria independente: uma rodada, uma correção, uma reconferência.

## Por que começar aqui

O `contador-senior` (consulta de 08/10/2026,
[registro](../projeto/consultas/2026-10-08-contador-senior-fiscal.md))
recomendou a ordem **Simples → ISS por município → Presumido** (HI-60). Todas
as três dependem do mesmo primeiro elo: saber **quais notas a empresa
prestou, em que competência, e com que natureza**. Hoje o sistema só recebe e
guarda a NFS-e; nada diz que ela foi conferida e escriturada.

## Escopo

**Entra:**

1. **Escrituração** de NFS-e nacional em que a empresa cliente é
   **prestadora** (`VinculoDocumentoEmpresa.papel = prestador`): uma
   escrituração por vínculo, com estado **rascunho → efetivada**, e
   **estorno** rastreável da efetivada (nunca edição silenciosa).
2. **Natureza da operação** — catálogo **fechado e pequeno**, definido em
   código (HI-56), só para serviço prestado neste corte:
   - serviço prestado, ISS devido pelo prestador;
   - serviço prestado, ISS retido pelo tomador (`tpRetISSQN` 2) ou pelo
     intermediário (3);
   - serviço prestado, ISS devido a outro município;
   - serviço prestado sem incidência de ISS (exportação, imunidade, não
     incidência — o contador escolhe; o sistema não presume).
   A natureza é **sugerida** a partir do XML (retenção → "retido") e
   **confirmada** pelo contador. Nenhuma natureza carrega alíquota nesta etapa.
3. **Três datas** (HI-57): emissão (`dhEmi`), **competência** (`dCompet`,
   que define o mês da escrituração) e escrituração (quando o contador
   efetivou). Nota com mês de competência diferente do de emissão recebe
   **aviso**.
4. **Valores** copiados do documento no momento da efetivação (valor do
   serviço, valor líquido, indicador de retenção) — a escrituração não
   recalcula imposto.
5. **Nota cancelada** (pelo evento já tratado na DL-010): não pode ser
   efetivada; se o cancelamento chegar **depois** da efetivação, a
   escrituração vira **pendência** "nota cancelada depois de escriturada —
   estorne", sem estorno automático.
6. **Conferência** "recebidas × escrituradas × pendentes" por empresa e
   competência, nos três níveis da HI-59 (bloqueia / exige justificativa /
   avisa) — nesta etapa só relatório; nenhum fechamento ainda.
7. Telas: lista de notas a escriturar por empresa e competência, escriturar
   (confirmar natureza), detalhe com trilha, estornar com motivo, e o
   relatório de conferência. Seguem a
   [direção de arte](../projeto/direcao-de-arte.md).

**Fica fora (registrado):** notas em que a empresa é **tomadora** (entradas,
serviços tomados — etapa própria); NF-e (DL-010 fatia 2); fechamento de
período fiscal (etapa própria; até lá a escrituração **não** é travada por
período, e isso é limite declarado); alíquota, imposto, guia; integração
contábil (HI-01, BL-72).

## Regras de engenharia

- Escrituração **efetivada é imutável**: correção só por estorno com motivo,
  e o estorno é ato próprio, registrado na trilha na mesma transação.
- Uma escrituração **ativa** por vínculo (restrição de unicidade parcial no
  banco); repetir a efetivação é idempotente ou recusada com mensagem — nunca
  duplica.
- Isolamento: escritório e empresa verificados no servidor em toda porta
  (tela e API); vínculo de outra empresa responde 404.
- Permissão no servidor: escriturar e estornar seguem os mesmos papéis que
  escrituram na contabilidade (ADMINISTRADOR, GESTOR, ANALISTA); CLIENTE não
  vê (DL-055). O implementador mede o padrão existente e o reusa.
- Valores em `Decimal`, escala do documento, sem ponto flutuante.

## Critérios de aceite

1. Nota prestada recebida aparece como "a escriturar" na competência do
   `dCompet`, não na do `dhEmi`.
2. Efetivar grava natureza, as três datas e os valores do documento; trilha
   com antes/depois na mesma transação.
3. Natureza sugerida = "ISS retido" quando `tpRetISSQN` ∈ {2, 3}; o contador
   pode trocar antes de efetivar; a sugestão nunca é gravada como efetivada
   sem ato do contador.
4. Efetivada não se edita (serviço, API, tela e admin); estorno exige motivo,
   devolve a nota para "a escriturar" e fica na trilha.
5. Nota cancelada não é efetivada (recusa nomeada); cancelamento posterior à
   efetivação gera a pendência, e a pendência some quando a escrituração é
   estornada.
6. Efetivar duas vezes (dois cliques, duas abas) não gera duas
   escriturações ativas — teste de concorrência em PostgreSQL.
7. Nota tomada (papel tomador) não aparece nesta lista.
8. Conferência: recebidas = escrituradas + pendentes por empresa e
   competência, com os casos de aviso (competência ≠ emissão) e de bloqueio
   (nota sem natureza efetivada) listados.
9. Isolamento entre escritórios e entre empresas: 404 nas duas direções, na
   tela e na API.
10. Papel CLIENTE não acessa; papel sem permissão de escriturar recebe 403
    na API e recusa na tela.
11. Mutação: sem a restrição de unicidade, o teste 6 cai; sem a trava de
    imutabilidade, o 4 cai.
12. Não regressão: suíte completa sem reprovação nova; `ruff`, `check`,
    `makemigrations --check` limpos; migração aplica em banco vazio.

## Hipóteses usadas (validação do Fred)

HI-56 (natureza em catálogo fechado), HI-57 (`dCompet` define o mês), HI-58
(ISS retido compõe a receita bruta; aqui só se marca), HI-59 (três níveis de
conferência). Nenhuma alíquota, prazo ou leiaute novo entra nesta etapa.

## Divisão do trabalho

| Frente | Quem | Arquivos | Depende |
| --- | --- | --- | --- |
| A — modelo, migração, serviços, API, testes do domínio | `auxiliar-implementacao` (Haiku, RC-164) | `apps/fiscal/models.py`, `apps/fiscal/migrations/`, `apps/fiscal/escrituracao.py` (novo), `apps/fiscal/permissoes.py`, API nova, testes `apps/fiscal/tests/test_dl072_*` | — |
| B — telas e relatório de conferência | `auxiliar-implementacao` (Haiku), com a skill `direcao-de-arte` | `apps/fiscal/views_web.py`, `apps/fiscal/urls_web.py`, `templates/fiscal/`, menu e universo de telas, testes de tela | A integrada |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita | A e B integradas |

## Reversão

Migração nova, só aditiva (tabela nova). Reverter é reverter a migração e o
commit; nenhum dado existente muda.

## Evidências

Ver o [estado](../agents/estado.md) e `docs/auditorias/`.
