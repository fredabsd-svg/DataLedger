"""Management command: backfill de `LancamentoContabil.competencia` (DL-016 F5).

PRE-CONDIÇÃO: o modelo `Competencia` (DL-016 F1) e o `get_or_create`
em `criar_lancamento.materializa_competencia` (DL-016 F2) já estão em
`main`. Esta command existe para preencher a FK nos lançamentos
gravados ANTES de F2 entrar em produção — todos eles com
`competencia_id IS NULL`.

O QUE A COMMAND FAZ, EM ORDEM:
  1. Itera sobre `LancamentoContabil.objects.filter(competencia__isnull=True)`
     em batches via `.iterator(chunk_size=batch_size)`.
  2. Para cada lançamento, deriva `(empresa_id, ano, mes)` de
     `lancamento.empresa_id` e `lancamento.data`. Lançamentos sem
     `empresa_id` válida viram "órfãos" — contados, logados, pulados.
  3. Faz `Competencia.objects.get_or_create(...)` — a
     `UniqueConstraint` em `Meta.constraints` (DE-008 camada 1)
     garante que duas tentativas simultâneas para a mesma chave
     resultem em UMA Competencia, não em race condition.
  4. Faz `LancamentoContabil.objects.filter(id__in=batch_ids,
     competencia__isnull=True).update(competencia=comp)` no fim da
     passada — um único UPDATE por batch, mantendo locks curtos.
  5. Repete 1-4 `max_passes` vezes (default 2). A segunda passada é
     curta e serve apenas para reduzir a janela em que um
     `criar_lancamento` concorrente (F2) consegue inserir um
     lançamento que ESCAPA da primeira passada.

CONTRATO:
  - Por padrão, `--dry-run` está ligado: nada é alterado, apenas
    contado e logado. É o modo seguro para qualquer ambiente.
  - `--apply` efetiva. Exige confirmação consciente do operador.
  - A command é IDEMPOTENTE: rodar duas vezes seguidas não muda nada
    na segunda passada, porque a cláusula `competencia__isnull=True`
    limita o queryset.
  - Órfãos NÃO causam exit code != 0. O relatório fica para revisão
    manual antes de aplicar em produção.

FORA DO ESCOPO (declarado no plano docs/planos/DL-016-F5-backfill-competencia.md):
  - Nao vira a FK em `null=False`. Isso e uma DL separada (F6) que
    depende do relatorio desta command mostrar zero orfaos em prod.
  - Nao fecha nem reabre competencias (F3, F4).
  - Nao migra competencias entre empresas.
"""

from collections import Counter
from time import monotonic

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.contabilidade.models import Competencia, LancamentoContabil


class Command(BaseCommand):
    help = (
        "Backfill da FK LancamentoContabil.competencia para lancamentos "
        "anteriores a DL-016 F2 (DL-016 F5). Por padrao roda em --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Efetiva o backfill no banco. Sem esta flag, a command roda "
                "em dry-run (apenas conta e loga, nao altera nada)."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help=(
                "Tamanho do batch para iteracao e UPDATE. Default 2000. "
                "Em bases muito grandes, considere reduzir para diminuir "
                "tempo de lock por batch."
            ),
        )
        parser.add_argument(
            "--max-passes",
            type=int,
            default=2,
            help=(
                "Numero de passadas. A segunda passada eh curta e serve "
                "apenas para pegar lancamentos concorrentes. Default 2. "
                "Use 1 se quiser garantir que nao havera segunda escrita."
            ),
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        batch_size = options["batch_size"]
        max_passes = options["max_passes"]

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(
            self.style.NOTICE(
                f"[backfill_lancamento_competencia] iniciando em modo {mode} "
                f"(batch_size={batch_size}, max_passes={max_passes})"
            )
        )

        # Totais agregados em todas as passadas (so para log final).
        totais = Counter(
            lidos=0,
            fks_atribuidas=0,
            competencias_criadas=0,
            orfaos_pulados=0,
        )

        tempo_inicio = monotonic()

        for numero_passada in range(1, max_passes + 1):
            self.stdout.write(
                self.style.NOTICE(
                    f"[backfill_lancamento_competencia] passada {numero_passada}/{max_passes} ..."
                )
            )
            contadores_passada = self._executar_passada(
                apply=apply, batch_size=batch_size, numero_passada=numero_passada
            )
            for chave, valor in contadores_passada.items():
                totais[chave] += valor
            self.stdout.write(
                self.style.NOTICE(
                    f"[backfill_lancamento_competencia] passada "
                    f"{numero_passada}/{max_passes} concluida: "
                    f"lidos={contadores_passada['lidos']}, "
                    f"fks_atribuidas={contadores_passada['fks_atribuidas']}, "
                    f"competencias_criadas={contadores_passada['competencias_criadas']}, "
                    f"orfaos_pulados={contadores_passada['orfaos_pulados']}"
                )
            )
            # Se nao ha mais nada para processar, nao precisa de mais passadas.
            if contadores_passada["lidos"] == 0:
                self.stdout.write(
                    self.style.NOTICE(
                        f"[backfill_lancamento_competencia] passada "
                        f"{numero_passada} nao encontrou nada para processar; "
                        f"encerrando passadas restantes."
                    )
                )
                break

        duracao = monotonic() - tempo_inicio
        self.stdout.write(
            self.style.SUCCESS(
                f"[backfill_lancamento_competencia] CONCLUIDO em {duracao:.2f}s. "
                f"TOTAIS: lidos={totais['lidos']}, "
                f"fks_atribuidas={totais['fks_atribuidas']}, "
                f"competencias_criadas={totais['competencias_criadas']}, "
                f"orfaos_pulados={totais['orfaos_pulados']}. "
                f"Modo: {mode}."
            )
        )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "[backfill_lancamento_competencia] DRY-RUN: nada foi "
                    "alterado. Rode novamente com --apply para efetivar."
                )
            )

    def _executar_passada(self, *, apply: bool, batch_size: int, numero_passada: int) -> Counter:
        """Uma passada completa do backfill. Retorna contadores desta passada."""
        contadores = Counter(
            lidos=0,
            fks_atribuidas=0,
            competencias_criadas=0,
            orfaos_pulados=0,
        )

        # Filtramos aqui para garantir idempotencia: a segunda passada
        # naturalmente so enxerga o que sobrou (lancamentos concorrentes
        # que entraram DURANTE a primeira passada, ou lancamentos com
        # empresa nula que foram pulados mas agora tem empresa).
        queryset = LancamentoContabil.objects.filter(competencia__isnull=True).order_by("id")

        # Buffer para acumular IDs do batch atual ate atingirmos
        # batch_size; depois disso fazemos o UPDATE em uma unica query.
        ids_pendentes: list[int] = []
        # Mapa (empresa_id, ano, mes) -> Competencia ja resolvida nesta
        # passada. Evita repetir get_or_create para a mesma chave dentro
        # da mesma passada. NAO e cache compartilhado entre passadas: a
        # Competencia pode ter sido criada em uma passada anterior e a
        # .get(...) abaixo pega ela de qualquer jeito.
        cache_chaves: dict[tuple[int, int, int], Competencia] = {}

        for lancamento in queryset.iterator(chunk_size=batch_size):
            contadores["lidos"] += 1

            empresa_id = lancamento.empresa_id
            if empresa_id is None:
                # Orfao: lancamento sem empresa. Conta, loga, pula.
                contadores["orfaos_pulados"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  [passada {numero_passada}] orfao: lancamento "
                        f"id={lancamento.id} sem empresa_id; pulando."
                    )
                )
                continue

            chave = (empresa_id, lancamento.data.year, lancamento.data.month)
            competencia = cache_chaves.get(chave)
            if competencia is None:
                # Cache miss para esta chave. get_or_create: idempotente
                # pela UniqueConstraint do banco. Em dry-run, NAO criamos
                # competencias novas; apenas checamos se ja existe.
                if apply:
                    competencia, criada = Competencia.objects.get_or_create(
                        empresa_id=empresa_id,
                        ano=chave[1],
                        mes=chave[2],
                    )
                    if criada:
                        contadores["competencias_criadas"] += 1
                else:
                    # Dry-run: so consulta, nunca cria.
                    competencia = Competencia.objects.filter(
                        empresa_id=empresa_id, ano=chave[1], mes=chave[2]
                    ).first()
                    if competencia is None:
                        # Em dry-run, contamos como "competencia que SERIA
                        # criada" para o operador ter visibilidade. O
                        # contador `competencias_criadas` aqui representa
                        # "que teriam sido criadas no apply", o que eh o
                        # espelho do que o apply faria.
                        contadores["competencias_criadas"] += 1
                        # Sem objeto para atribuir, pulamos este lancamento
                        # tambem (em dry-run nao ha nada para atribuir).
                        continue
                cache_chaves[chave] = competencia

            ids_pendentes.append(lancamento.id)
            if len(ids_pendentes) >= batch_size:
                self._flushar_batch(
                    ids_pendentes=ids_pendentes,
                    competencia=competencia,
                    apply=apply,
                    numero_passada=numero_passada,
                    contadores=contadores,
                )
                ids_pendentes = []

        # Flush final: o ultimo batch incompleto.
        if ids_pendentes:
            self._flushar_batch(
                ids_pendentes=ids_pendentes,
                competencia=competencia,  # type: ignore[arg-type]
                apply=apply,
                numero_passada=numero_passada,
                contadores=contadores,
            )

        return contadores

    def _flushar_batch(
        self,
        *,
        ids_pendentes: list[int],
        competencia: Competencia,
        apply: bool,
        numero_passada: int,
        contadores: Counter,
    ) -> None:
        """Aplica um UPDATE em batch para os IDs acumulados.

        A transacao existe para garantir que a atomicidade do batch eh
        respeitada: ou todos os IDs do batch sao atualizados, ou nenhum
        eh. Em dry-run, a transacao ainda existe mas o update() nao
        roda, garantindo que o dry-run nao toque em nada.
        """
        if not ids_pendentes:
            return
        with transaction.atomic():
            if apply:
                atualizadas = LancamentoContabil.objects.filter(
                    id__in=ids_pendentes, competencia__isnull=True
                ).update(competencia=competencia)
                contadores["fks_atribuidas"] += atualizadas
                self.stdout.write(
                    f"  [passada {numero_passada}] batch: {atualizadas} "
                    f"FKs atribuidas para competencia id={competencia.id} "
                    f"({competencia})."
                )
            else:
                # Dry-run: nada a fazer, mas mantemos a transacao para
                # simetria com o apply (e para que possiveis signals
                # fakes na DB nao vazem).
                self.stdout.write(
                    f"  [passada {numero_passada}] dry-run batch: "
                    f"{len(ids_pendentes)} lancamentos seriam associados "
                    f"a competencia {competencia}."
                )
