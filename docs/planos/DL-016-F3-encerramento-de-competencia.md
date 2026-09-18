# DL-016-F3 — Encerramento de competência

**Estado:** em planejamento. Não iniciada.
**Branch prevista:** `claude/dl-016-f3-encerramento-competencia` a partir de `main` (HEAD atual `b588af9`).
**Próximo identificador de decisão livre:** **DE-053** (DE-050 é Onda 1 da DL-016, DE-051 é fechamento da F5, DE-052 é fechamento da F6 — todos ocupados).

**Pré-requisito de:** DL-016-F4 (reabertura autorizada e auditada) — F4 não
faz sentido sem F3, porque não há nada para reabrir.

**Pré-requisito desta DL:** DL-016-F5 (backfill da FK) já integrada
em `main` (PR #33, `700a50b`); DL-016-F6 (CHECK constraint `empresa_id`
NOT NULL) já integrada em `main` (PR #34, `15f6a98`). F5 garante que,
ao encerrar uma competência, todos os lançamentos do mês têm
`competencia_id` preenchido. F6 blinda o bypass do ORM na coluna
`empresa_id` (defesa em profundidade independente desta F3, mas
relevante porque F3 introduz novo hook de gravação).

**Onde esta DL se encaixa na DL-016:** é a próxima sub-DL da DL-016
no backlog declarado em `docs/agents/estado.md` linha 218.

| Onda | Conteúdo                                  | Status                          |
|------|-------------------------------------------|---------------------------------|
| F1   | Modelo `Competencia` + migration + admin  | ✅ integrada (`fa15cf1`)         |
| F2   | Vinculação automática em `criar_lancamento` | ✅ integrada (`fa15cf1`)       |
| F5   | Backfill da FK                            | ✅ integrada (`700a50b`)         |
| F6   | CHECK constraint `empresa_id` NOT NULL    | ✅ integrada (`15f6a98`)         |
| **F3** | **Encerramento de competência (esta DL)** | 🟡 **em planejamento**          |
| F4   | Reabertura autorizada e auditada          | ⏳ depende de F3                 |

## Por que esta etapa vem agora

- DL-010 (importador em massa) está planejada mas parada; ela vai
  consumir competências existentes. Se F3 fechar o mês corrente com
  sucesso, o importador já sabe respeitar a fronteira do fechado.
- A DE-019 (data do lançamento = mês da competência) já está em vigor.
  F3 não precisa migrar dados — só mudar o `estado` da `Competencia`.
- O `EstadoCompetencia` enum já tem os 3 estados reservados
  (`aberta`, `em_encerramento`, `encerrada`) desde F1. F3 é onde
  esses estados começam a ser usados de verdade.

## O que existe hoje

Tudo de F1, F2, F5, F6 já está em `main`:

- `apps/contabilidade/models.py:33-86` — `Competencia` com campos:
  `empresa` (FK `Empresa`, PROTECT), `ano` (IntegerField),
  `mes` (IntegerField), `estado` (CharField TextChoices com
  `ABERTA`/`EM_ENCERRAMENTO`/`ENCERRADA`, default `ABERTA`),
  `criado_em` (DateTimeField auto_now_add). **Sem campos `encerrado_por`,
  `encerrado_em`, `papel_encerramento`, `data_conferencia`** —
  precisam ser criados em migration nova nesta F3.
- `apps/contabilidade/models.py:Competencia.Meta.constraints` —
  `UniqueConstraint(empresa, ano, mes)` (DE-008 camada 1),
  `CheckConstraint(mes 1..12)`,
  `CheckConstraint(ano 1970..2999)`.
- `apps/contabilidade/services.py:criar_lancamento` — `competencia`
  preenchida automaticamente via `get_or_create` (F2).
- `apps/contabilidade/management/commands/backfill_lancamento_competencia.py`
  — backfill rodou em produção via F5.
- `apps/contabilidade/services.py:1271` —
  `localizar_lotes_desbalanceados(*, empresa)` (DL-015, BL-64 achado 9).
  **Hoje não tem parâmetros `ano`/`mes`.** Ver Pergunta A.
- Migration `0005_check_lancamento_empresa_not_null.py` — CHECK
  constraint `empresa_id IS NOT NULL` (F6).
- `apps/auditoria/services.py` — `registrar(*, acao, usuario=None,
  escritorio=None, objeto=None, detalhes=None, request=None)`. Se
  `request` for passado, infere `endereco_ip` de `request.META["REMOTE_ADDR"]`,
  infere `usuario` de `request.user.is_authenticated`, infere `escritorio`
  de `getattr(request, "escritorio", None)`. **Não há parâmetro `ip=` nem
  `contexto=` separado.** Aceita `request=None`.
- `apps/auditoria/models.py` — `RegistroAuditoria` com FKs nullable
  (SET_NULL custom preserva trilha), `acao` (CharField 100),
  `objeto_tipo` (CharField 100 derivado de `type(objeto).__name__`),
  `objeto_id` (CharField 50 derivado de `str(objeto.pk)`),
  `detalhes` (JSONField default=dict), `endereco_ip`
  (GenericIPAddressField null), `criado_em` (auto_now_add).
- `apps/contabilidade/permissoes.py:69` — `papel_pode_ler_contabilidade(papel)`
  e a tupla `PAPEIS_QUE_LEEM_CONTABILIDADE`. É o padrão que F3
  espelhará para `papel_pode_encerrar_competencia`.
- 7 migrations: `0001_initial` a `0005_check_lancamento_empresa_not_null`.
  A próxima é `0006_*` (ver Pergunta C).

O que falta: **mudar `estado` da `Competencia` de `aberta` para
`encerrada` de forma auditada, recusando lançamentos no servidor
quando a competência estiver fechada**.

## Migration nova (proposta — ver Pergunta C e bloco MIGRATION CONCRETA no fim)

Quatro campos adicionados em
`apps/contabilidade/migrations/0006_competencia_campos_encerramento.py`,
na ordem abaixo (padrão "FK primeiro, depois DateTimes, depois CharField"
usado em `0004`):

1. `encerrado_por` — `ForeignKey(AUTH_USER_MODEL, on_delete=SET_NULL, null=True,
   blank=True, related_name="competencias_encerradas")`. `SET_NULL` porque
   o usuário pode ser excluído mas a trilha de quem fechou precisa
   sobreviver (mesma lógica da auditoria; aqui não precisamos da função
   custom porque `Competencia` não tem signal de imutabilidade).
2. `encerrado_em` — `DateTimeField(null=True, blank=True)`. Não é
   `auto_now_add` nem `auto_now` porque só é preenchido quando a
   competência passa a `ENCERRADA` (não na criação).
3. `papel_encerramento` — `CharField(max_length=20, blank=True)`.
   Validação (papel ∈ `Papel.choices`) fica no **serviço**
   (`encerrar_competencia`), não no modelo — porque o modelo só
   guarda string curta, e a regra de "qual papel pode fechar" é
   uma decisão de produto que pode evoluir sem migração (mesmo
   padrão de `VinculoUsuarioEscritorio.papel` em
   `apps/tenancy/models.py:65`).
4. `data_conferencia` — `DateTimeField(null=True, blank=True)`. Marca
   o instante em que a conferência da DL-015 passou.

Nenhum default é aplicado — todos `null=True, blank=True`. Linhas
existentes ficam com os 4 campos `NULL`. Não há backfill (não há
dados de `Competencia` "encerrada" hoje para preencher — todas estão
`ABERTA`).

A migration depende de
`("contabilidade", "0005_check_lancamento_empresa_not_null")` e de
`migrations.swappable_dependency(settings.AUTH_USER_MODEL)`.

## Escopo

1. **Endpoint `POST /empresas/<id>/competencias/<YYYY-MM>/fechar/`**
   — chama `encerrar_competencia(empresa, ano, mes, *, autor, papel,
   escritorio, request=None)`. Recusa com 409 se a conferência da
   DL-015 acusar desbalanceamento. Recusa com 409 se a competência
   já está `EM_ENCERRAMENTO` (concorrência). Devolve 200 idempotente
   se já está `ENCERRADA` (regrava estado, mas **não** regrava autor/data).
2. **Hook em `criar_lancamento`** — se a `Competencia` da data do
   lançamento está `ENCERRADA`, recusa com
   `LancamentoInvalido("competência YYYY-MM está encerrada; reabra
   antes de lançar")`. View devolve 409.
3. **Hook em `estornar_lancamento`** — mesma recusa, pelo mesmo
   motivo (a data do estorno herda a do lançamento original; ver
   Pergunta D).
4. **Idempotência** — segunda chamada a `encerrar_competencia` para a
   mesma `(empresa, ano, mes)` retorna o registro existente **sem
   mudar `encerrado_por`/`encerrado_em`/`papel_encerramento`/
   `data_conferencia`**.
5. **Isolamento** — fechamento de empresa A não afeta empresa B;
   fechamento de empresa em escritório X não afeta escritório Y.
6. **Auditoria** — `RegistroAuditoria(acao="competencia.encerrar",
   objeto=competencia, ...)` criado dentro do mesmo
   `transaction.atomic()` que envolve a mudança de estado (mesma
   lição do BL-14 da DL-024: trilha fora da transação = contabilidade
   diz uma coisa, trilha diz outra).

**Fora do escopo:**

- Não reabre — F4.
- Não trata período de trabalho (RC-56) — vem depois do F4.
- Não cria UI — DL-017.
- Não cria modelo `Fechamento` separado — o plano antigo
  (`docs/agents/dl-016-plano-de-execucao.md`) que propunha isso está
  SUPPLANTED (a `Competencia` de F1 absorveu o conceito). Esta F3 fecha
  o ciclo usando `Competencia.estado`.

## Decisões de modelagem (propostas, marcadas [C] vs [P])

Itens `[C]` são decisão do agente com justificativa; itens `[P]`
exigem resposta do Frederico (ver Perguntas A–E no fim).

| #  | Decisão                                                    | Status |
|----|------------------------------------------------------------|--------|
| 1  | Lock otimista via `estado = EstadoCompetencia.EM_ENCERRAMENTO` (sem campo `em_encerramento: Bool` novo) | [C]    |
| 2  | Migration nova `0006_competencia_campos_encerramento.py` adiciona 4 campos: `encerrado_por`, `encerrado_em`, `papel_encerramento`, `data_conferencia` | [C]    |
| 3  | `papel_pode_encerrar_competencia(papel)` adicionado em `apps/contabilidade/permissoes.py` ao lado de `papel_pode_ler_contabilidade` | [C]    |
| 4  | Serviço `apps.auditoria.services.registrar` chamado por `objeto=competencia` (deriva `objeto_tipo="Competencia"` e `objeto_id=str(competencia.pk)`) | [C]    |
| 5  | `request=None` é aceito (IP fica `None`); se a view tiver `request`, ele é passado e `endereco_ip` sai automático | [C]    |
| 6  | Endpoint HTTP `POST /empresas/<id>/competencias/<YYYY-MM>/fechar/` chama `encerrar_competencia` | [C]    |
| 7  | `select_for_update().get(empresa=..., ano=..., mes=...)` para impedir concorrência dupla | [C]    |
| 8  | Conferência da DL-015 (filtrada por ano/mês da competência) é pré-condição automática | [C]    |
| 9  | Recusa de lançamento/estorno quando competência está `encerrada` (passa a morar em `criar_lancamento` e `estornar_lancamento`) | [C]    |
| 10 | Permissão: apenas papéis `ADMINISTRADOR` e `GESTOR` podem encerrar (CONSTANTE P2 — confirmar com Frederico) | [P]    |
| 11 | Esterno herda data do lançamento original (regra DL-006 / RC do DL-016 #2) | [P]    |

### P1 — Lock otimista intermediário: usado de verdade

Sequência dentro do `transaction.atomic()`:

```
select_for_update().get(empresa=..., ano=..., mes=...)   # camada 1 (DB row lock)
if estado != ABERTA:
    if estado == ENCERRADA:
        return competencia   # idempotência
    raise ConcenciaJaEmEncerramento(...)  # estado == EM_ENCERRAMENTO
estado = EM_ENCERRAMENTO
save(update_fields=["estado"])
# conferencia...
if conferencia_ok:
    estado = ENCERRADA
    encerrado_por = autor
    encerrado_em = timezone.now()
    papel_encerramento = papel
    data_conferencia = timezone.now()
    save()
    registrar(acao="competencia.encerrar", ...)
```

A rele `if estado != ABERTA` **dentro do lock** cobre 3 cenários:

- (a) Fechamento concorrente: segunda transação vê `EM_ENCERRAMENTO`
  e recusa.
- (b) Fechamento já concluído: vê `ENCERRADA` e devolve idempotentemente
  sem regravar autor.
- (c) Estado inconsistente por bypass do ORM: qualquer valor diferente
  de `ABERTA` recusa (sem assumir limpo).

**Por que NÃO criar campo `em_encerramento: Bool` separado?** Porque
o `estado` já tem a cadeira reservada desde F1 e o lock intermediário
fica em uma linha (`select_for_update` no `estado`) em vez de duas
(`em_encerramento` + `estado`). Menos coluna, menos CHECK constraint
a defender, menos migration.

### P2 — Quem pode encerrar

Função `papel_pode_encerrar_competencia(papel)` em
`apps/contabilidade/permissoes.py`, ao lado de
`papel_pode_ler_contabilidade`. Proposta inicial do agente:

```
PAPEIS_QUE_ENCERRAM_COMPETENCIA = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
)
```

Justificativa: ADMINISTRADOR (ato formal, mesma lógica de "quem pode
mudar settings globais" em DL-014) e GESTOR (opera a contabilidade
no dia a dia). ANALISTA / FINANCEIRO / PARALEGAL / CLIENTE não
encerram.

**Esta composição é P2 — confirmar com Frederico.** A recomendação
do agente é manter ADMINISTRADOR + GESTOR.

### P3 — Conferência como pré-condição (automática)

`localizar_lotes_desbalanceados(*, empresa)` é chamado filtrando por
`(ano, mes)` da `Competencia`. Se a lista vier não-vazia, recusa com
409 mencionando quantos lotes e os primeiros 5 ids (não os valores —
sigilo). Ver Pergunta A sobre a assinatura do filtro.

### P4 — Fechamento não cascata

Fecha só o mês pedido. Operador fecha cada mês na ordem que quiser.
A `UniqueConstraint(empresa, ano, mes)` em `Competencia.Meta` já
garante granularidade mensal (DE-008 camada 1).

### P5 — Auditoria mínima (F3)

Campos da `Competencia`: `encerrado_por`, `encerrado_em`,
`papel_encerramento`, `data_conferencia`. Registro de
`RegistroAuditoria` com `acao="competencia.encerrar"`,
`objeto=competencia` (o serviço deriva `objeto_tipo="Competencia"` e
`objeto_id=str(competencia.pk)`),
`detalhes={"empresa_id": ..., "ano": ..., "mes": ..., "papel": ...,
"fechado_por": ...}`. IP entra automaticamente se `request` for
passado à view; se a view não tiver `request`, fica `None` (cenário
de management command futura, fora desta F3).

### P6 — Estorno em competência encerrada

`estornar_lancamento` consulta a `Competencia` da data do **lançamento
original** (regra DL-006 / RC do DL-016 #2: estorno herda data do
original). Se está `ENCERRADA`, recusa com
`LancamentoInvalido("competência YYYY-MM do lançamento original está
encerrada; reabra antes de estornar")`. Ver Pergunta D.

## Sequência do `transaction.atomic` (proposta)

Serviço `encerrar_competencia(empresa, ano, mes, *, autor, papel,
escritorio, request=None)` em `apps/contabilidade/services.py`:

```python
from django.db import transaction
from django.utils import timezone
from apps.auditoria.services import registrar
from apps.contabilidade.models import Competencia, EstadoCompetencia
from apps.contabilidade.services import localizar_lotes_desbalanceados


class CompetenciaNaoPodeSerEncerrada(Exception):
    """Levantada quando a conferência acusa desbalanceamento."""


class CompetenciaJaEmEncerramento(Exception):
    """Levantada quando outra transação já marcou EM_ENCERRAMENTO."""


def encerrar_competencia(empresa, ano, mes, *, autor, papel,
                         escritorio, request=None):
    """Encerra uma competencia (empresa, ano, mes) de forma atomica.

    Lock em duas camadas:
      1. SELECT ... FOR UPDATE na linha da Competencia (DB row lock).
      2. Rele do estado dentro do lock: estado != ABERTA recusa
         (cobre "em_encerramento" e "encerrada" em uma unica checagem).
    """
    with transaction.atomic():
        # Camada 1: lock pessimista.
        competencia = (
            Competencia.objects
            .select_for_update()
            .get(empresa=empresa, ano=ano, mes=mes)
        )

        # Camada 2: rele do estado dentro do lock.
        if competencia.estado != EstadoCompetencia.ABERTA:
            if competencia.estado == EstadoCompetencia.ENCERRADA:
                # Idempotência: segunda chamada devolve o registro
                # existente sem regravar autor/data_conferencia/papel.
                return competencia
            # Estado == EM_ENCERRAMENTO: outra transação em curso.
            raise CompetenciaJaEmEncerramento(
                f"competência {ano}-{mes:02d} já está em encerramento"
            )

        # Marca lock otimista. update_fields=["estado"] evita regravar
        # os 4 campos novos por engano (estão NULL neste momento).
        competencia.estado = EstadoCompetencia.EM_ENCERRAMENTO
        competencia.save(update_fields=["estado"])

        # Pre-condicao: conferencia da DL-015 filtrada por (ano, mes).
        # Ver Pergunta A sobre a assinatura exata do filtro.
        lotes_problematicos = localizar_lotes_desbalanceados(
            empresa=empresa, ano=ano, mes=mes
        )
        if lotes_problematicos:
            # Rollback automatico: reverte o save do estado=EM_ENCERRAMENTO.
            raise CompetenciaNaoPodeSerEncerrada(
                f"competência {ano}-{mes:02d} tem {len(lotes_problematicos)} "
                f"lote(s) desbalanceado(s); confira antes de fechar"
            )

        # Conferencia OK: fecha de fato.
        agora = timezone.now()
        competencia.estado = EstadoCompetencia.ENCERRADA
        competencia.encerrado_por = autor
        competencia.encerrado_em = agora
        competencia.papel_encerramento = papel
        competencia.data_conferencia = agora
        competencia.save()

        # Auditoria dentro da MESMA transacao (licao BL-14 / DL-024).
        registrar(
            acao="competencia.encerrar",
            usuario=autor,
            escritorio=escritorio,
            objeto=competencia,
            detalhes={
                "empresa_id": empresa.id,
                "ano": ano,
                "mes": mes,
                "papel": papel,
                "fechado_por_id": autor.id if autor else None,
            },
            request=request,
        )

    return competencia
```

Notas:

- `select_for_update()` exige `transaction.atomic()` — satisfeito
  pelo `with`. Em SQLite (testes) é silenciosamente no-op (sem efeito,
  sem erro) — ver Riscos para PostgreSQL.
- O segundo `save()` (sem `update_fields`) regrava todos os campos
  — intencional: 4 campos vão de `NULL` para os valores.
- `registrar()` é chamado com `objeto=competencia`. Dentro dele,
  `type(objeto).__name__ == "Competencia"` e `getattr(objeto, "pk")`
  é o id. Resultado: `objeto_tipo="Competencia"`, `objeto_id=str(pk)`.
- Se `request is None` (cenário management command futura, fora de F3),
  `endereco_ip` fica `None` no `RegistroAuditoria` — comportamento
  já documentado em `apps/auditoria/services.py`.

## View (referência)

Nova view em `apps/contabilidade/views.py`, no padrão das views
existentes:

```python
class EncerrarCompetenciaView(EmpresaEscopadaMixin, APIView):
    permission_classes = [TemEscritorioAtivo, PodeEncerrarCompetencia]

    def post(self, request, empresa_id, ano, mes):
        papel = request.papel  # resolvido pelo EscritorioAtivoMiddleware
        if not papel_pode_encerrar_competencia(papel):
            raise PermissionDenied("seu papel não pode encerrar competência")

        try:
            competencia = encerrar_competencia(
                empresa_id, ano, mes,
                autor=request.user,
                papel=papel,
                escritorio=request.escritorio,
                request=request,
            )
        except Competencia.DoesNotExist:
            return Response({"detail": "competência inexistente"}, status=404)
        except CompetenciaJaEmEncerramento as exc:
            return Response({"detail": str(exc)}, status=409)
        except CompetenciaNaoPodeSerEncerrada as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(CompetenciaSerializer(competencia).data, status=200)
```

URL: `path("empresas/<int:empresa_id>/competencias/<int:ano>-<int:mes>/fechar/", EncerrarCompetenciaView.as_view(), name="competencia-fechar")` em `apps/contabilidade/urls.py`.

## Permissão

Em `apps/contabilidade/permissoes.py`, adicionar ao lado de
`PAPEIS_QUE_LEEM_CONTABILIDADE` e `papel_pode_ler_contabilidade`:

```python
PAPEIS_QUE_ENCERRAM_COMPETENCIA = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
)


def papel_pode_encerrar_competencia(papel):
    """Responde: este papel pode encerrar competencia?

    None -> False (ausencia de papel nunca e permissao).
    """
    return papel in PAPEIS_QUE_ENCERRAM_COMPETENCIA
```

A permissão DRF `PodeEncerrarCompetencia` chama
`papel_pode_encerrar_competencia` em `has_permission`.

## Pré-requisitos não-bloqueantes

- `localizar_lotes_desbalanceados(*, empresa)` precisa de overload com
  `ano` e `mes` (ver Pergunta A). Sem isso, a conferência pré-fecha
  varre a empresa inteira e pode dar falso positivo.
- `estornar_lancamento` precisa consultar `Competencia.estado` da data
  original e recusar (mudança contida ao serviço, sem impacto na view).

## Critérios de aceite

1. **CA-1**: Encerrar uma competência aberta transita
   `ABERTA -> EM_ENCERRAMENTO -> ENCERRADA` de forma atômica. Estado
   final é `ENCERRADA` ou a operação falhou por exceção. Nunca fica em
   `EM_ENCERRAMENTO` deixado pra trás.
2. **CA-2**: Encerrar uma competência já `ENCERRADA` é idempotente:
   retorna o registro existente, `encerrado_por`/`encerrado_em`/
   `papel_encerramento`/`data_conferencia` **não mudam**.
3. **CA-3**: Encerrar uma competência com conferência acusando
   desbalanceamento é recusado com `CompetenciaNaoPodeSerEncerrada`,
   e a `Competencia` continua `ABERTA` (rollback automático do
   `transaction.atomic()`).
4. **CA-4**: Lançar em competência `ENCERRADA` é recusado no servidor
   (no `criar_lancamento`) com mensagem indicando qual mês está fechado.
   View devolve 409.
5. **CA-5**: Estornar lançamento cuja data cai em competência
   `ENCERRADA` é recusado pelo mesmo motivo. View devolve 409.
6. **CA-6**: Concorrência — duas transações simultâneas chamando
   `encerrar_competencia` para a mesma `(empresa, ano, mes)`: uma
   vence, a outra recebe `CompetenciaJaEmEncerramento`. (SQLite: teste
   sequencial valida a regra; PG: lock real. Ver Riscos.)
7. **CA-7**: Isolamento — encerramento de empresa A não afeta
   `Competencia` de empresa B.
8. **CA-8**: Isolamento multi-escritório — encerramento de empresa em
   escritório X não afeta `Competencia` de empresa em escritório Y.
9. **CA-9**: Trilha gravada — `RegistroAuditoria` com
   `acao="competencia.encerrar"`, `objeto_tipo="Competencia"`,
   `objeto_id` igual ao `pk`, `detalhes` com `empresa_id`, `ano`,
   `mes`, `papel`, `fechado_por_id`. `endereco_ip` populado quando a
   chamada vem de view com `request`; `None` quando vem de
   script/management command.
10. **CA-10**: Permissão — usuário com papel que não está em
    `PAPEIS_QUE_ENCERRAM_COMPETENCIA` recebe `PermissionDenied` da DRF
    (403).
11. **CA-11**: Sem regressão — suíte completa da DL-016 (F1+F2+F5+F6)
    continua passando.

## Cenários de teste

Em `apps/contabilidade/tests/test_dl016_f3_encerramento.py`:

1. `test_encerrar_competencia_aberta_sucesso` — fecha, estado final
   `ENCERRADA`, 4 campos preenchidos, trilha criada.
2. `test_encerrar_competencia_ja_encerrada_e_idempotente` — segunda
   chamada não muda autor/data.
3. `test_encerrar_competencia_em_encerramento_recusa` — simula estado
   `EM_ENCERRAMENTO` direto (bypass do ORM), `encerrar_competencia`
   levanta `CompetenciaJaEmEncerramento`.
4. `test_encerrar_competencia_com_lotes_desbalanceados_recusa` —
   injeta 1 lote desbalanceado, levanta
   `CompetenciaNaoPodeSerEncerrada`, `Competencia` continua `ABERTA`.
5. `test_criar_lancamento_em_competencia_encerrada_recusa` —
   `criar_lancamento` levanta `LancamentoInvalido`, nada gravado.
6. `test_estornar_lancamento_em_competencia_encerrada_recusa` — idem
   para estorno.
7. `test_concorrencia_encerrar_mesma_competencia` — sequencial (SQLite);
   valida que a rele do estado protege.
8. `test_isolamento_empresas_distintas` — fecha empresa A, empresa B
   permanece inalterada.
9. `test_trilha_auditoria_gravada` — após `encerrar_competencia`,
   `RegistroAuditoria.objects.filter(acao="competencia.encerrar").count() == 1`.
10. `test_trilha_auditoria_com_request_infere_ip` — view com `request`
    mockado tendo `META["REMOTE_ADDR"]="10.0.0.1"`; `RegistroAuditoria.endereco_ip == "10.0.0.1"`.
11. `test_trilha_auditoria_sem_request_ip_none` — chamada direta ao
    serviço sem `request`; `RegistroAuditoria.endereco_ip is None`.
12. `test_permissao_papel_nao_autorizado_recusa_403` — usuário com papel
    `ANALISTA` recebe `PermissionDenied` da view.
13. `test_permissao_papel_autorizado_passa` — usuário com papel `GESTOR`
    consegue.
14. `test_rollback_em_excecao_nao_deixa_em_encerramento` — se
    `localizar_lotes_desbalanceados` levantar exceção inesperada,
    `Competencia.estado` permanece `ABERTA` (verificado por
    `refresh_from_db`).

## Riscos (com mitigação para SQLite vs PostgreSQL)

| Risco | SQLite (testes) | PostgreSQL (produção) | Mitigação |
|-------|------------------|------------------------|-----------|
| `select_for_update()` é no-op no SQLite (sem efeito, sem aviso). Concorrência real só é testável em PG. | Camada 2 (rele do estado dentro do lock) garante o invariante sequencialmente. | Camada 1 (row lock) + Camada 2 (rele) garantem serialização real. | F3 não introduz teste concorrente novo dependente de PG — segue o padrão DL-006. |
| Migration com FK para `AUTH_USER_MODEL` em SQLite vs PG. | `swappable_dependency` é honrado pelos dois. | Idem. | Migration declara `migrations.swappable_dependency(settings.AUTH_USER_MODEL)` nas `dependencies`. |
| Migration com `DateTimeField(null=True)` em SQLite vs PG. | Idem. | Idem. | Sem risco material — campo nullable padrão. |
| Bypass do ORM (UPDATE direto no banco) pula o lock otimista. | Possível. | Possível. | Detecção em auditoria — comparar contagem de `Competencia.estado='encerrada'` com `RegistroAuditoria(acao='competencia.encerrar').count()`. Discrepância indica bypass. |
| Estorno em competência encerrada — semântica confusa. | Decisão do Fred (Pergunta D). | Idem. | Default proposto: esterno herda data do lançamento original; se a `Competencia` dessa data está `ENCERRADA`, recusa. |
| `papel_encerramento` armazenado como `CharField` sem `choices` no modelo. | Validação só no serviço. | Idem. | Aceito — segue padrão de `VinculoUsuarioEscritorio.papel` (`apps/tenancy/models.py:65`). |

## Auditoria

DE-004 obriga auditoria independente antes do merge. Como F3 introduz
**endpoint novo + migration nova + regra de concorrência + hook em 2
serviços críticos (`criar_lancamento`, `estornar_lancamento`)**, precisa
de rodada 1 própria. Estimativa: 1 rodada, com 11 pontos de inspeção
(1 por critério de aceite + 1 para a migration).

## Pendências conhecidas

1. **Migration `0004` (F1) ainda precisa ser regenerada por
   `makemigrations`** no primeiro deploy Python 3.12+. Esta F3 não
   interfere (a 0006 também será hand-written seguindo o padrão da 0004).
2. **Runbook DL-016-F5 deploy** ainda não escrito. F3 não depende dele.
3. **Perguntas A–E** abaixo bloqueiam o início do código. Sem
   respostas, não começar.

## Plano obsoleto

`docs/agents/dl-016-plano-de-execucao.md` (184 linhas) propunha:

- Modelo `Fechamento(empresa, ano, mes, situacao, autor,
  data_fechamento, motivo_reabertura, reaberto_por, reaberto_em)`
  separado.
- 7 decisões D1–D7 a confirmar.
- 6 fatias F1–F6, com F3 sendo "Período de trabalho" (não
  "Encerramento").

Estado: **SUPPLANTED**. Razões:

- F1 da DL-016 acabou criando `Competencia` (não `Fechamento`) como
  modelo do ciclo de vida mensal, e `Competencia.estado` absorveu o
  que `Fechamento.situacao` faria.
- A "F3" deste plano antigo (período de trabalho, RC-56) virou onda
  separada, dependente de F4.
- Este plano novo (`DL-016-F3-encerramento-de-competencia.md`) é a
  F3 real, baseada no que existe em `main` hoje (HEAD `b588af9`).

Ação: marcar `docs/agents/dl-016-plano-de-execucao.md` como
SUPPLANTED no cabeçalho (não deletar — preservação de histórico).

---

**Próximo passo:** Frederico responde Perguntas A–E. Com as respostas,
este plano é finalizado e o código começa na branch
`claude/dl-016-f3-encerramento-competencia`. PR único com migration +
service + view + permissão + testes + DE-053 no `decisoes.md`
quando concluído.


### MIGRATION CONCRETA: 0006_competencia_campos_encerramento.py ###

Localização: `apps/contabilidade/migrations/0006_competencia_campos_encerramento.py`

```python
# DL-016-F3 — Quatro campos de auditoria do encerramento de competencia.
#
# Hand-written seguindo o mesmo padrão da migration 0004 (sandbox Python 3.11
# sem Django 6.1.1, `makemigrations` nao roda). Regenerar com
# `python manage.py makemigrations` no primeiro `migrate` em ambiente Python
# 3.12+ e comparar diff item a item.
#
# Escopo desta migration:
#   1. encerrado_por — FK para AUTH_USER_MODEL, SET_NULL, nullable.
#      SET_NULL (e nao PROTECT/CASCADE) porque a trilha de quem fechou
#      precisa sobreviver a exclusao do usuario.
#   2. encerrado_em — DateTimeField nullable. NAO e auto_now_add nem
#      auto_now porque so e preenchido quando a competencia passa para
#      ENCERRADA.
#   3. papel_encerramento — CharField(max_length=20, blank=True).
#      Validacao (papel in apps.tenancy.models.Papel.choices) mora no
#      SERVICO encerrar_competencia, nao no modelo.
#   4. data_conferencia — DateTimeField nullable. Marca o instante em que
#      a conferencia da DL-015 passou antes do fechamento.
#
# Sem defaults: todas as colunas ficam NULL em Competencias pre-F3.
# Nao ha backfill — todas as Competencias existentes estao ABERTA.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contabilidade", "0005_check_lancamento_empresa_not_null"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1) encerrado_por — FK para o usuario que fechou.
        migrations.AddField(
            model_name="competencia",
            name="encerrado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="competencias_encerradas",
                to=settings.AUTH_USER_MODEL,
                verbose_name="encerrado por",
            ),
        ),
        # 2) encerrado_em — DateTime do fechamento.
        migrations.AddField(
            model_name="competencia",
            name="encerrado_em",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="encerrado em",
            ),
        ),
        # 3) papel_encerramento — papel do usuario no momento do fechamento.
        migrations.AddField(
            model_name="competencia",
            name="papel_encerramento",
            field=models.CharField(
                blank=True,
                max_length=20,
                verbose_name="papel no encerramento",
            ),
        ),
        # 4) data_conferencia — DateTime da conferencia da DL-015 que passou.
        migrations.AddField(
            model_name="competencia",
            name="data_conferencia",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="data da conferência",
            ),
        ),
    ]
```


### 5 PERGUNTAS ABERTAS PARA FREDERICO ###

### ⚠️ A — Assinatura do filtro em `localizar_lotes_desbalanceados` para F3

Hoje a função é
`localizar_lotes_desbalanceados(*, empresa)` em
`apps/contabilidade/services.py:1271`. F3 precisa filtrar por
`(ano, mes)` da competência que está sendo encerrada — sem isso,
a conferência pré-fecha varre a empresa inteira e dá falso positivo
se houver desbalanceamento em **outra** competência.

Três opções:

- **(a)** Adicionar parâmetros opcionais `ano=None, mes=None` à função
  existente. Se ambos `None`, mantém o comportamento atual (sem filtro).
  F3 chama com `ano=X, mes=M`. Sem migração de dados; só assinatura.
- **(b)** Criar função nova
  `localizar_lotes_desbalanceados_no_periodo(empresa, ano, mes)` e
  deixar a antiga como wrapper. Código duplicado (mesma query em 2
  funções); risco de divergência silenciosa.
- **(c)** Sempre exigir `ano` e `mes` como argumentos obrigatórios.
  Quebra todas as chamadas atuais (a função é usada em outros lugares
  a confirmar).

**Recomendação do agente: (a).** Menor mudança, zero regressão em
outros callers, e a opcionalidade preserva o uso em auditorias
gerais ("empresa inteira torta, sem mês definido").

### ⚠️ B — `papel_encerramento` armazenado vs inferido

O modelo `Competencia` ganha `papel_encerramento: CharField`. Quando
o usuário muda de papel depois (ex.: era GESTOR quando fechou
2026-09, depois virou ADMINISTRADOR), o valor guardado continua
sendo "GESTOR" — fiel ao momento do ato.

Alternativa: **não guardar**, e inferir de `VinculoUsuarioEscritorio`
no momento da leitura. Mas isso muda quando o vínculo muda
(mais arriscado), e a auditoria perde fidelidade histórica.

**Recomendação do agente: armazenar** (o que esta F3 já propõe).

Confirmar.

### ⚠️ C — Número da nova migration

Proposta: `0006_competencia_campos_encerramento.py`. A próxima na
ordem após `0005_check_lancamento_empresa_not_null.py`.

Confirmar.

### ⚠️ D — Estorno: cascata de competência original ou da data atual?

Regra historicamente conhecida na DL-006 / RC do DL-016 #2: o
estorno **herda** a data do lançamento original, não usa "hoje".
Confirmar isso para esta F3.

Duas leituras alternativas:

- (a) Estorno usa data do lançamento original (regra histórica).
  Se a `Competencia` dessa data está `ENCERRADA`, recusa
  estorno (default desta F3).
- (b) Estorno usa "hoje" como data. Cai na `Competencia` atual.
  Mesma regra de negócio do (a) mas com semântica diferente —
  confuso para o usuário que está estornando algo de 2026-09 em
  dezembro.
- (c) Decidir isso em F4 (reabertura) e deixar F3 só cobrir a
  recusa de `criar_lancamento` em competência encerrada.

**Recomendação do agente: (a)** — segue a regra histórica. Mas
isso é decisão de negócio, não técnica — Frederico confirma.

### ⚠️ E — Rollback explícito vs savepoint

Se `localizar_lotes_desbalanceados(empresa=..., ano=..., mes=...)`
levantar **exceção inesperada** (bug, timeout de DB), o
`transaction.atomic()` da função `encerrar_competencia` reverte
tudo automaticamente (incluindo o `save(update_fields=["estado"])`
anterior). Não precisa de `try/except` explícito.

Alternativa: `try/except` + `raise` customizado para mapear o erro
genérico em `CompetenciaNaoPodeSerEncerrada` com mensagem fixa.
Problema: mascarar bugs reais de DB.

**Recomendação do agente: deixar o `transaction.atomic()` reverter
naturalmente.** Exceção inesperada sobe para a view como 500, o que
é o sinal correto de "algo quebrou de verdade". A Competencia
permanece `ABERTA` (cenário CA-14 nos testes).

Confirmar.
