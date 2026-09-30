# DL-052 — Integridade do livro e do acesso

**Demanda:** Fred, 30/09/2026: *"Aprovo a DL-052, pode seguir"*, sobre a
análise do repositório feita na mesma conversa (commit `dbc6113`).
**Estado:** [fonte única](../agents/estado.md).
**Branch:** `claude/zealous-goldberg-jr5ggu` → `main`. O nome segue a
branch imposta pela plataforma desta sessão, não o padrão `fix/<demanda>` do
AGENTS.md §6; o conflito está registrado aqui e não muda mais nada.
**Risco:** nível 1 (livro-razão, trilha de auditoria e isolamento entre
escritórios). Auditoria independente **obrigatória**.

## Origem

A análise de 30/09/2026 (`auditor-qa`, por inspeção e experimento em banco
próprio) reprovou três invariantes, conferidas também pelo `arquiteto-senior`
no código:

| Achado | Defeito | Evidência |
| --- | --- | --- |
| A2 (alta) | Convite de escritório nunca vence e é aceito por qualquer usuário, com qualquer e-mail | `aceitar_convite_e_criar_vinculo` em `apps/tenancy/services/primeiro_acesso.py` não consulta `ConviteEscritorio.expirado` nem o e-mail; convite de 400 dias aceito por e-mail divergente, com papel de analista |
| A1 (alta) | Débito = crédito, `valor > 0` e imutabilidade do lançamento só existem em Python | `LancamentoContabil.save/delete` e `ItemLancamento.save/delete`; `QuerySet.update()` e `.delete()` desbalancearam e apagaram lançamento sem rastro |
| M1 (média) | Estorno gravado fora da transação da trilha | `EstornoView.post` em `apps/contabilidade/views.py` chama `registrar` depois do commit de `estornar_lancamento`; com a trilha falhando, 500 e estorno persistido sem registro |

## Escopo

1. **A2 — convite.** Recusar na aceitação o convite com mais de 7 dias
   (prazo já documentado no modelo) e o convite apresentado por usuário cujo
   e-mail difere do convidado (comparação sem diferença de maiúsculas e
   espaços). A tela do convite também informa o vencimento.
2. **A1 — invariantes no banco (PostgreSQL).**
   - `CHECK (valor > 0)` no item.
   - Gatilhos que **recusam UPDATE e DELETE** em `LancamentoContabil` e
     `ItemLancamento`, espelhando exatamente o `save`/`delete` de hoje.
     **Uma exceção**, achada pelo implementador e aprovada pelo
     `arquiteto-senior` em 30/09/2026, válida só se nenhuma outra coluna
     mudar na mesma instrução: `competencia_id` de nulo para preenchido
     (comando `backfill_lancamento_competencia`, DL-016 F5). O implementador
     achou também `criado_por_id` virando nulo ao apagar usuário
     (`SET_NULL`); o Fred decidiu (RC-144) que usuário se desativa e não se
     apaga, então essa via é fechada em vez de liberada.
   - **Usuário não se exclui (RC-144, BL-559):** `PROTECT` na autoria de
     `LancamentoContabil.criado_por`, `Competencia.fechada_por` e
     `entregue_por`, `RegistroAuditoria.usuario`, `LancamentoCaixa.criado_por`
     e `DependentesCarneLeaoCliente.criado_por`; admin sem exclusão de
     usuário; desativar continua possível. `RegistroAuditoria.escritorio`
     mantém o `SET_NULL` que preserva o evento.
   - Gatilho de restrição **adiado para o fim da transação** que recusa
     lançamento cujos itens não somem débito igual a crédito, ou que não tenha
     ao menos um débito e um crédito (as mesmas regras de `criar_lancamento`;
     o implementador confirma quais são e as espelha, sem inventar regra).
   - Mensagens do banco nomeadas e traduzidas para erro legível onde uma
     porta de escrita puder alcançá-las.
3. **M1 — estorno atômico.** `estornar_lancamento` e `registrar` na mesma
   transação. Varrer as demais rotas de escrita da API contábil pelo mesmo
   padrão e corrigir as que o repetirem.
4. **Nível 3, sem auditoria:** passo `makemigrations --check` na CI;
   `estado.md` enxuto e coerente com o Git; preferência de modelo do Fred
   registrada na equipe.

**Fora do escopo** (registrado no backlog, BL-547 a BL-558): token do convite
fora da URL, confirmação de e-mail no cadastro, papel Cliente lendo a
carteira (M2), reclassificação de conta em período encerrado (M3), trava de
período do livro-caixa (M4 — PE-73 respondida, RC-145; vira a DL-053), limite de tentativas no login
e titularidade de CNPJ (M5), IP atrás de proxy (M6) e os achados baixos.

## Critérios de aceite

1. Convite com `criado_em` há mais de 7 dias → recusado, nenhum vínculo
   criado, convite continua não consumido. Convite com exatamente 7 dias
   menos um segundo → aceito (limite).
2. Usuário com e-mail diferente do convite → recusado, sem vínculo. Mesmo
   e-mail com maiúsculas/espaços diferentes → aceito.
3. `ItemLancamento.objects.filter(...).update(valor=...)`,
   `LancamentoContabil.objects.filter(...).update(...)` e `.delete()` nas
   duas tabelas → `DatabaseError` (PostgreSQL), nada alterado.
4. `bulk_create` de itens desbalanceados, ou lançamento com um só lado →
   recusado no commit; lançamento balanceado criado por `criar_lancamento` e
   estorno continuam funcionando, sem mudança de contrato da API.
5. Item com `valor <= 0` gravado por fora do serviço → recusado pelo banco.
6. Estorno com `registrar` forçado a falhar → 0 estornos gravados e o
   estorno pode ser refeito depois. O mesmo para cada rota corrigida na
   varredura.
7. Suíte completa verde em PostgreSQL; nenhum teste existente afrouxado.
   Teste que precise montar dado inválido de propósito desliga o gatilho de
   forma explícita, local e comentada.
8. Excluir usuário que escriturou → recusado (ORM e admin); desativar →
   aceito, e o usuário desativado não entra.
9. Migração aplica em banco vazio e é reversível (`migrate contabilidade
   <anterior>` remove gatilhos e restrição).

## Impacto, riscos e reversão

- **Dados:** a migração falha se já houver item com `valor <= 0` ou lote
  desbalanceado. Não há dado real de cliente (backup, PE-07, ainda não
  existe), então falhar alto é o comportamento desejado; o erro nomeia o
  lote.
- **SQLite:** os gatilhos são só PostgreSQL, como a `0009`; em SQLite a
  invariante fica na aplicação — mesmo limite aceito no BL-535 (produção
  nunca roda em SQLite).
- **Convite:** convites pendentes com mais de 7 dias deixam de funcionar;
  o administrador emite outro. Comportamento prometido desde a DL-018.
- **Reversão:** revert do PR e `migrate contabilidade <anterior>`; sem
  perda de dado.

## Evidências

Implementação (`desenvolvedor-pleno`, PostgreSQL 16 local, Python 3.13):

- Suíte completa: **3.658 aprovados, 50 pulados, 1 reprovado** — a
  reprovação é a conhecida de versão do Python (exige 3.14), igual à linha de
  base de 30/09 (3.591 aprovados).
- Testes novos reprovam contra o código anterior: convite 7 falhas; estorno e
  criação pela API 2 falhas; admin de usuário 3 falhas. Os gatilhos
  reprovaram 9 testes e deram erro em 24 ao serem ligados, até as adaptações
  de montagem (`gatilho_desligado`, asserções intactas).
- `ruff check` limpo; 326 arquivos formatados; `makemigrations --check` sem
  mudança; migrações aplicadas e revertidas nas duas direções.
- Não testado: `TRUNCATE` e o dono da tabela desligando gatilho (fora do que
  o banco impede); concorrência dos gatilhos adiados.

Auditoria independente: relatório em [`docs/auditorias/`](../auditorias/).
