# DL-053 — Fechamento de mês do livro-caixa

**Demanda:** Fred, 30/09/2026, respondendo à PE-73: *"livro-caixa pode ter
fechamento de mês"* (RC-145) e *"pode ser a mesma regra da contabilidade"*
(RC-146). Origem: achado M4 da análise de 30/09 (BL-551).
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `claude/zealous-goldberg-jr5ggu` → `main` (branch imposta pela
plataforma da sessão, reiniciada da `main` depois do merge do PR #66).
**Risco:** nível 1 (o carnê-leão apurado e o arquivo entregue ao cliente).
Auditoria independente **obrigatória**.

## Problema

Hoje qualquer lançamento ou estorno no livro-caixa pode cair num mês cujo
carnê-leão já foi apurado, pago ou importado no Carnê-Leão Web, e muda o
resultado sem aviso. A RC-130 já diz que o erro de mês anterior se corrige
**reabrindo o mês original** — mas não existe mês fechado para reabrir.

## Decisões de desenho (`arquiteto-senior`)

1. **Controle próprio do livro-caixa**, não a `Competencia` contábil: a
   contabilidade recusa cliente em modo livro-caixa por desenho
   (`recusar_se_livro_caixa`), e reaproveitar a `Competencia` acoplaria os
   dois módulos. O modelo novo fica em `apps/livro_caixa` (por empresa, ano e
   mês; estados aberto/encerrado; quem e quando fechou; reabertura com
   motivo), espelhando o padrão da DL-016.
2. **Papéis (RC-146 = RC-102):** fecha e reabre ADMINISTRADOR ou GESTOR;
   ANALISTA não; FINANCEIRO, PARALEGAL e CLIENTE não alcançam. A lista de
   papéis vem do **mesmo ponto** da contabilidade — não uma segunda lista.
3. **Mês sem registro = aberto.** Fechar cria o registro; reabrir exige
   motivo e registra na trilha.
4. **A trava vale para toda porta de escrita** que grave `LancamentoCaixa`:
   tela, API e qualquer caminho automático (o implementador lista os
   caminhos encontrados). O estorno já usa a data do original (DE-091 item 4),
   então estornar lançamento de mês fechado exige reabrir — exatamente a
   RC-130.
5. **Concorrência:** a gravação trava o registro do mês (`FOR SHARE`, como em
   `criar_lancamento` da contabilidade) para que fechar e lançar ao mesmo
   tempo não deixe lançamento em mês fechado.
6. **Dependentes do carnê-leão (RC-147, BL-571):** o implementador mediu que
   registrar dependentes com início no passado ou retificar quantidade
   vigente muda a dedução de meses já apurados. O Fred decidiu que também
   travam: a alteração que mude o resultado de algum mês encerrado é
   recusada até o mês ser reaberto.
7. **Fora do escopo:** estado "entregue" do mês, trava por gatilho de banco e
   fechamento em lote de vários clientes.

## Critérios de aceite

1. Lançamento (tela e API) com data em mês encerrado → recusado com mensagem
   clara, nada gravado, banco inalterado. Mês aberto e mês sem registro →
   aceito.
2. Estorno de lançamento de mês encerrado → recusado; depois de reabrir →
   aceito.
3. Fechar e reabrir por ADMINISTRADOR e GESTOR → aceito, com trilha (quem,
   quando, motivo na reabertura). ANALISTA, FINANCEIRO, PARALEGAL e CLIENTE →
   403 **e banco inalterado**, testado pela requisição, não pela tela.
4. Reabrir sem motivo → recusado. Fechar mês já fechado e reabrir mês aberto
   → recusados sem efeito.
5. Isolamento: usuário de outro escritório não fecha, não reabre e não vê o
   estado do mês de cliente alheio (404).
6. Concorrência: fechar e lançar simultaneamente no mesmo mês nunca termina
   com lançamento gravado em mês encerrado (teste com duas conexões, com
   timeout e asserção de conclusão, conforme a DL-050).
7. Dependentes (RC-147): registrar com início em mês encerrado, ou retificar
   registro cuja mudança alcance mês encerrado → recusado, nada gravado;
   alteração que só alcança meses abertos → aceita; depois de reabrir →
   aceita.
8. Tela: o mês encerrado aparece como encerrado no livro-caixa, a ação de
   lançar não é oferecida nele, e fechar/reabrir só aparecem para quem pode
   — sem substituir a checagem do servidor.
9. Suíte completa verde em PostgreSQL; migração aplica em banco vazio e é
   reversível.

## Impacto, riscos e reversão

- **Dados:** tabela nova; nenhum dado existente muda; todos os meses nascem
  abertos.
- **Operação:** o escritório passa a ter de reabrir o mês para corrigir
  lançamento dele (RC-130).
- **Reversão:** revert do PR e `migrate livro_caixa <anterior>`.

## Distribuição

- `desenvolvedor-pleno`: modelo, migração, serviços, trava, API, testes.
- `especialista-frontend`: tela de fechamento e estado do mês nas telas do
  livro-caixa, depois do contrato do backend.
- `auditor-qa`: versão integrada.

## Evidências

Implementação (PostgreSQL 16 local, Python 3.13):

- **Servidor** (`desenvolvedor-pleno`): `FechamentoMesCaixa` e migração
  0010; `encerrar_mes_caixa`/`reabrir_mes_caixa` atômicos com a trilha;
  trava no único caminho de gravação (`criar_lancamento_caixa`, por onde
  passa o estorno); lock consultivo por empresa, ano e mês cobre o mês sem
  registro; papéis num ponto só (`apps/core/papeis_de_fechamento.py`).
  Mutação: sem a trava, 23 testes reprovam; sem o lock, 6.
- **Dependentes (RC-147):** a alteração recusa quando muda a quantidade
  aplicada num mês encerrado ou em qualquer mês até dezembro do mesmo ano
  (encadeamento da apuração). Regra conservadora: pode recusar alteração de
  efeito nulo. Lock consultivo por empresa. Mutação: sem a trava, 9
  reprovam.
- **Tela** (`especialista-frontend`): painel dos 12 meses, encerrar e
  reabrir, aviso de mês encerrado em lista, formulário e estorno, recusa nos
  dependentes. Chromium em 1.440 e 390 px sem rolagem horizontal. Mutação:
  qualquer papel fechando, 11 reprovam.
- Integração (`arquiteto-senior`): item no menu lateral, rótulos da trilha,
  mensagem do servidor sem identificador interno (a asserção nova reprova
  com ele).
- Suíte completa: **3.875 aprovados, 50 pulados, 1 reprovado** (o conhecido
  de Python 3.13).
- Não testado: leitor de tela, Firefox e Safari; Python 3.14 (CI).

Auditoria independente: [`docs/auditorias/`](../auditorias/).
