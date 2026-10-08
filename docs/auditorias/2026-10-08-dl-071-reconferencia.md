# Reconferência da DL-071 (rodada 2, última permitida)

**Papel:** `auditor-qa`. **Nível de risco:** 1 (AGENTS.md §3.1). **Não corrigi nada.**
**Revisão auditada:** `f4f2a721c30dc9d77bd4820d25415c17da64dab9`, branch `ccr-bf4b4a55-hpqgbp`. Relatório anterior: [rodada 1](2026-10-08-dl-071-rodada-1.md), sobre `dcfbb67`.

**Início:** HEAD `f4f2a72`, `git status --porcelain` vazio. Conferi que `5a78947` e `2e37e43` não alteram nenhum `.py` (`git show --name-only`). Só `f4f2a72` altera código: `apps/contabilidade/services.py` e `apps/contabilidade/tests/test_dl071_marcacao_dmpl_periodo_fechado.py`. No arquivo de teste, a única linha existente que mudou é o import de `_gestor`. O resto é acréscimo, então nenhuma expectativa anterior foi enfraquecida.

**Fim:** HEAD é o mesmo SHA. `git status --porcelain` e `git diff --stat` do repositório principal estão vazios. Removi as worktrees `/home/user/wt-reconf071` e `/home/user/wt-reconf071b`, e os bancos `dataledger_reconf071` e `dataledger_reconf071b` (e os `test_*` derivados) foram apagados. Não toquei `/home/user/wt-dl072a`. Vi só, por `git status`, que ela tem alterações próprias do outro programador.

## Parecer: **APROVADO COM RESSALVAS**

As correções de A2, A3, A4, B2 e B3 funcionam e foram reproduzidas por execução. Não encontrei defeito novo nem mutante da rodada 1 que tenha voltado a sobreviver. A suíte completa deu exatamente o esperado.

As ressalvas são explícitas e não escondem falha essencial:

1. **A1 continua aberto**, de gravidade alta e fora do escopo da DL-071. Está registrado como BL-656 com honestidade. A DL-071 não o corrige, e a reclassificação de conta ainda altera DMPL e DLPA de período fechado.
2. **O critério 7 continua parcial** para competência sem linha (A5). O arquiteto aceitou o limite (BL-657 e seção no plano). A aceitação é decisão dele. Ela não torna verdadeiro o texto do critério 7 no plano, que segue sem exceção. Recomendo reescrevê-lo.
3. **B1 aberto** (BL-658, baixa).
4. **R1** (baixa): faltam testes que fixem o comportamento de um `OperationalError` que não é `lock_timeout`.

Ambiente: PostgreSQL 16, Python 3.13.16, worktrees descartáveis de `f4f2a72`. Auditoria de software não substitui validação contábil e legal, e não afirmo ausência de bugs.

## Achados da rodada 1 × situação

| Achado | Situação | Evidência executada |
| --- | --- | --- |
| **A1** (reclassificação de conta com o mesmo furo) | **Aberto, registrado com honestidade como BL-656** | Registro conferido: o backlog diz "alta, nível 1", cita os 4 cenários e marca a DFC como "inferido, não medido". Diz que a parte do saldo de exercícios anteriores depende do Fred. O `models.py` não mudou desde `dcfbb67`. **Não reexecutei a reprodução** (o diff não toca `models.py`). |
| **A2** (`lock_timeout` na trava do lançamento virava 500) | **Corrigido** | Sonda minha, abaixo. |
| **A3** (isolamento por empresa sem teste) | **Corrigido** | `test_competencia_fechada_de_outra_empresa_nao_trava_nem_e_travada` passa no real. M5 agora é **morto** por ele. |
| **A4** (precedência do período sobre o conteúdo) | **Corrigido** | `test_periodo_fechado_vem_antes_do_conteudo_invalido` passa no real. M7 agora é **morto** por ele. |
| **A5** (competência sem linha) | **Limite aceito, registrado** | Seção "Limite aceito depois da auditoria" no plano e BL-657. O texto bate com o que medi. **Não reexecutei a sonda** nesta rodada (o código da guarda não mudou nesse ponto). |
| **B1** (tela não avisa antes do envio) | **Aberto como BL-658** | Registro conferido, responsável `especialista-frontend`. |
| **B2** (mensagem não nomeava o estado gravado) | **Corrigido** | Mensagens medidas, abaixo. |
| **B3** (concordância no plural) | **Corrigido** | Mensagens medidas, abaixo. |

### A2 por execução (sonda minha, `transaction=True`, `lock_timeout` de 200 ms, lock do lançamento segurado por outra thread)

```
API PUT     409 {'detail': 'Não foi possível alterar as marcações agora: outra operação está alterando este lançamento. Tente de novo em instantes.'}
API DELETE  409 (mesma mensagem)
TELA salvar 200, div role="alert" com a mesma mensagem
TELA remover 200
```

- **Nada gravado:** marcações e trilha idênticas antes e depois.
- **Transação utilizável depois do savepoint:** dentro de um `transaction.atomic()` externo, a chamada levantou `ClassificacaoAlteraPeriodoFechado`. Em seguida o `COUNT` e um `update_or_create` funcionaram (3 para 4 linhas), sem `InternalError`.
- **Erro que não é lock sobe intacto:** usei `statement_timeout = 200ms`, que produz um erro real do banco com SQLSTATE `57014` (`QueryCanceled`). `salvar` e `remover` levantaram `OperationalError`, com `__cause__.sqlstate == "57014"`. Não viraram recusa.
- **Teste do desenvolvedor:** `test_a2_lock_timeout_na_trava_do_lancamento_vira_recusa_e_nao_500` passa. Com a correção removida (A2a) ele cai com `Conflict`/erro cru.
- **Não executei:** o ramo `40P01` (deadlock) da trava do lançamento. Só o inspecionei no código, onde usa o mesmo helper `_e_deadlock` das outras guardas.

### B2 e B3 por execução (mensagens do serviço, 10 cenários, mais API e tela)

- **Um estado `EM_ENCERRAMENTO`, forçado por ORM:** "a competência 02/2026 está em encerramento … A marcação só pode mudar com a competência aberta." Não diz "Reabra" nem "encerrada". API 409 e tela 200 trazem o mesmo texto.
- **Estados misturados, e três competências:** "as competências 02/2026 (em encerramento) e 03/2026 (encerrada) não estão abertas" e "02/2026 (em encerramento), 03/2026 (encerrada) e 04/2026 (em encerramento)". Sem "Reabra".
- **Só encerradas:** a sugestão de reabrir continua e lista todas as competências que barram.
- **Entregue:** nunca manda reabrir. Ela vence a mistura: "entregue+encerrada" e "em encerramento+entregue" falam só da entregue. É o desenho da A3 da DL-065 e não mudou.
- **Plural (B3):** "as DMPLs de 02/2026 e 03/2026 acumulam … e incluem este lançamento". Singular: "a DMPL de 02/2026 acumula … e inclui". Para três competências: "as DMPLs de 02/2026, 03/2026 e 04/2026 acumulam …". Vale para encerradas e para entregues.
- **Mensagens trocadas?** Não. O `lock_timeout` da competência continua "Tente de novo em instantes" e sem "encerrada" (M13 morto).

## Mutantes

Cada mutante foi aplicado isoladamente sobre `f4f2a72`, rodando o arquivo `test_dl071_marcacao_dmpl_periodo_fechado.py` (44 testes). O arquivo foi restaurado depois de cada um. Os que nomeio com "ex." são os testes que o matam, listados parcialmente.

| Mutante | Resultado | Testes que matam |
| --- | --- | --- |
| **M0** sem a chamada da guarda | **Morto** | 31 testes |
| **M1** `mes__gte` por `mes` | **Morto** | 6 testes (ex.: fronteira, critério 3) |
| M1b `mes__gt` | **Morto** | 30 testes |
| M1c sem filtro de ano | **Morto** | fronteira, "outro exercício" |
| M1d `mes__lte` | **Morto** | 7 testes |
| **M2** guarda pela FK `lancamento.competencia` em vez da data | **Morto** | `criterio3_lancamento_sem_competencia_gravada_e_achado_pela_data` |
| **M3** sem `FOR SHARE` | **Morto** | 3 testes (corrida ×2 e `lock_timeout`) |
| **M4** sem a bifurcação de entregue | **Morto** | 10 testes |
| **M12a** `entregues = []` | **Morto** | 10 testes |
| **M12b** entregue fora da lista que barra | **Morto** | 10 testes |
| **M13** mensagem de timeout dizendo "encerrada" | **Morto** | `criterio8_...` |
| M6 sem a tradução do `lock_timeout` da competência | **Morto** | `criterio8_...` |
| **M5** sem `empresa_id` (sobrevivia) | **Morto agora** | `test_competencia_fechada_de_outra_empresa_...` |
| **M7** guarda depois do conteúdo (sobrevivia) | **Morto agora** | `test_periodo_fechado_vem_antes_do_conteudo_invalido` |
| A2a sem `try/except` (500 de volta) | **Morto** | `test_a2_...` |
| A2e mensagem da trava do lançamento dizendo "encerrada" | **Morto** | `test_a2_...` |
| B2a `if True` (sempre "Reabra") | **Morto** | 2 testes `b2` |
| B2b `any` em vez de `all` | **Morto** | `b2_estados_misturados` |
| B2c rótulo fixo "encerrada" | **Morto** | `b2_estado_gravado_...` |
| B2d sem o estado ao lado da competência | **Morto** | `b2_estados_misturados` |
| B2e "Reabra" na mensagem de outros estados | **Morto** | 2 testes `b2` |
| B3a sempre singular | **Morto** | 2 testes `b3` |
| B3b sempre plural | **Morto** | `b3_uma_competencia_...` |
| B3c e B3d singular fixo em cada ramo | **Morto** | um teste `b3` cada |
| **A2c** sem checar SQLSTATE (qualquer `OperationalError` vira recusa) | **SOBREVIVE** | nenhum teste do desenvolvedor (R1) |
| **A2d** sem `or _e_deadlock(exc)` | **SOBREVIVE** | nenhum (R1) |
| A2b sem o `transaction.atomic()` interno | **SOBREVIVE, equivalente** | nenhum, e nem minha sonda o distingue (ver nota abaixo) |

Nota sobre **M2:** nesta rodada usei a variante `lancamento.competencia.ano/mes`. Ela só é distinguível do código real pelo teste de dado legado (lançamento sem competência gravada), que a mata. Na rodada 1 a variante de M2 podia ser outra, e ela era morta por 4 testes. Não consigo afirmar que sejam idênticas, mas o teste que importa a mata.

Nota sobre **A2b:** `salvar_marcacoes_da_dmpl` já é `@transaction.atomic`, então o savepoint interno é redundante com o decorador. A transação externa se recupera de qualquer forma, e o `except` só usa atributos escalares. Não é achado, apenas defesa em profundidade.

## Verificações de saúde

| Verificação | Resultado |
| --- | --- |
| Suíte completa, em worktree limpa (executada) | **5.065 aprovados, 1 reprovado, 53 pulados**, 2 avisos, 365 s. O reprovado é `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`, de ambiente (3.13 contra 3.14), como esperado. |
| Arquivo da DL-071 | 44 passaram. Os testes de corrida e de `lock_timeout` ficaram estáveis em 5 de 5 repetições. |
| `ruff check .` | Limpo. |
| `ruff format --check .` | 381 arquivos já formatados. |
| `python manage.py check` | Sem problemas. |
| `makemigrations --check --dry-run` | Sem mudanças. |

## Achados novos

### R1: nenhum teste fixa o que acontece com um `OperationalError` que não é lock

- **Gravidade:** **baixa** (teste ausente). O código está correto, e eu o verifiquei por execução.
- **Requisito afetado:** AGENTS.md §7 (regra aplicável vira teste). Critério 8 da DL-071 e DE-078 item 5, que pedem não transformar em recusa um erro de banco que não seja de espera.
- **Local:** `apps/contabilidade/services.py`, bloco do `try/except OperationalError` em `salvar_marcacoes_da_dmpl` (cerca das linhas 8604 a 8623). Os mutantes **A2c** e **A2d** sobrevivem aos 44 testes.
- **Reprodução literal:** aplicar A2c, trocando `if not (_e_estouro_de_lock_timeout(exc) or _e_deadlock(exc)): raise` por `if False: raise`, e rodar `pytest apps/contabilidade/tests/test_dl071_marcacao_dmpl_periodo_fechado.py`. Resultado: `44 passed`.
- **Impacto:** uma queda de conexão ou um `statement_timeout` na trava do lançamento passaria a ser mostrado ao contador como "outra operação está alterando este lançamento. Tente de novo". Isso esconderia a falha real e mudaria o status de 500 para 409. Hoje o código está certo, mas nada impede a regressão.
- **Correção recomendada:** acrescentar o teste abaixo. Já o executei: passa no real e cai com A2c. A2d (ramo de deadlock) é difícil de provocar de forma determinística e é inalcançável nesta trava sem transação externa que já segure outro lock. Aceito que ele fique sem teste, mas registro.

```python
@pytest.mark.django_db(transaction=True)
def test_erro_de_banco_que_nao_e_lock_sobe_intacto_e_nao_vira_recusa():
    empresa, contas, gestor, p1, p2 = _cenario()
    antes = _marcacoes(p1)
    segurando, largar, da_thread = threading.Event(), threading.Event(), {}

    def _segurar():
        with transaction.atomic():
            LancamentoContabil.objects.select_for_update().get(pk=p1.pk)
            segurando.set()
            largar.wait(timeout=60)

    t = _na_thread(_segurar, da_thread)
    t.start()
    try:
        assert segurando.wait(timeout=30)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '200ms'")  # SQLSTATE 57014, não 55P03
        with pytest.raises(OperationalError) as erro:
            _tentar_pelo_servico("trocar", p1, gestor)
        assert erro.value.__cause__.sqlstate == "57014"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET statement_timeout")
        largar.set()
        t.join(timeout=60)
    assert _marcacoes(p1) == antes
```

- **Verificação:** o teste passa sem mutação e cai com A2c.

### R2: concordância ainda singular em trechos da mensagem plural

- **Gravidade:** **baixa (cosmética).**
- **Local:** `apps/contabilidade/services.py`, textos do `else` de encerradas e de outros estados (linhas 8496 a 8545).
- **Evidência:** com duas ou mais competências, o sujeito e os verbos da abertura ficaram no plural (B3 corrigido), mas o resto fala no singular: "a demonstração **daquele período** mudaria retroativamente" e "a demonstração **daquele período** não muda enquanto a competência não estiver aberta".
- **Impacto:** nenhum comportamental.
- **Correção recomendada:** tratar no mesmo helper `_concordancia_das_dmpls`, ou deixar como está.
- **Verificação:** a mensagem de duas competências deve dizer "daqueles períodos".

Não encontrei defeito introduzido pela correção. Não achei mensagem trocada, regressão de mutante da rodada 1, nem aumento no número de consultas da guarda: os testes do critério 10 passam.

## Registros do arquiteto: conferidos

- **BL-656 (A1):** "alta, nível 1", cenários e a dependência do Fred conferem com o que relatei. A extensão para a DFC está marcada como inferida.
- **BL-657 e seção do plano (A5):** o texto bate com a medição. Está dito que o limite foi **aceito** e **medido pelo auditor**, sem minimizar o dano. O critério 7 do plano continua escrito sem exceção, o que é uma pendência de redação.
- **BL-658 (B1):** correto.
- **`estado.md`:** ainda diz "em desenvolvimento" para a DL-071 e não registra as rodadas 1 e 2. É o fechamento que cabe ao `arquiteto-senior` depois deste parecer. Pelo CLAUDE.md, ele é parte da entrega.

## Não verificado, e por quê

| Item | Situação | Motivo |
| --- | --- | --- |
| `pwsh ./scripts/validate-docs.ps1` | **Não testado** | `pwsh` não existe neste ambiente. O teste `test_documentacao_do_estado.py` roda dentro da suíte e passou. Não conferi à mão os links dos `.md` desta rodada (relatório, plano, backlog, `requisitos.md`, planos da DL-072 e consulta fiscal). |
| Python 3.14 e os quatro checks do GitHub | **Não testado** | O ambiente é 3.13.16 e a CI não foi executada. Verificação que roda não é proteção de `main`. |
| Reprodução da sonda do A1 e da A5 | **Não reexecutado** | O diff de `f4f2a72` não toca `models.py` nem a parte da guarda que a A5 descreve. Confiei na medição da rodada 1. |
| Ramo de deadlock (`40P01`) da trava do lançamento | **Inspecionado, não executado** | Difícil de provocar de forma determinística (ver R1). |
| Mutantes de view (M8 a M11, M14, M15) | **Não rerodados** | `views.py` e `views_web.py` não mudaram, e os testes só ganharam casos. |
| Extensão do A1 para a DFC, medição visual, permissão de CLIENTE (403) e anônimo | **Não testado** | Mesmo motivo da rodada 1: fora do que o diff toca. |
| Conteúdo da DL-072 (`docs/planos`, `requisitos.md` HI-56 a HI-63, consulta fiscal, README) | **Fora do escopo** | Só confirmei que os commits `5a78947` e `2e37e43` não alteram `.py`. |

## Arquivos relevantes

- `apps/contabilidade/services.py` (guarda a partir de 8376; correção do A2 em cerca de 8604 a 8623; B2 e B3 entre 8352 e 8545)
- `apps/contabilidade/tests/test_dl071_marcacao_dmpl_periodo_fechado.py`
- `docs/planos/DL-071-marcacao-da-dmpl-em-periodo-fechado.md`
- `docs/projeto/backlog.md` (BL-655 a BL-658)
- `docs/agents/estado.md` (pendente de atualização pelo arquiteto)

---

Registrado pelo `arquiteto-senior` em 08/10/2026, sem edição dos achados.
