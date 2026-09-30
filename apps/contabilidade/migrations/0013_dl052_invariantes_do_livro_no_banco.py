# DL-052 (A1), critérios 3, 4, 5 e 8 do plano — as invariantes do livro-razão
# que até aqui só existiam em Python (`criar_lancamento`, `save`/`delete` dos
# modelos) passam a existir também NO BANCO, para valer contra o que o Python
# não alcança: `QuerySet.update()`, `QuerySet.delete()`, `bulk_create()`,
# `objects.create()` e SQL direto. A análise de 30/09/2026 desbalanceou um
# lançamento com `.update(valor=...)` e apagou outro com `.delete()`, sem
# nenhum rastro.
#
# O que esta migração faz, em ordem:
#
# 1. PRÉ-CONFERÊNCIA (todos os bancos): se já houver item com `valor <= 0`,
#    lançamento sem partidas ou lote cujos débitos diferem dos créditos, a
#    migração FALHA ALTO, nomeando os lotes, e NÃO corrige dado nenhum —
#    corrigir lançamento efetivado em silêncio seria justamente a violação
#    que esta etapa existe para impedir. (Sem dado real de cliente hoje —
#    backup, PE-07, ainda não existe —, falhar alto é o comportamento
#    desejado; ver o plano.)
#
# 2. `CheckConstraint(valor > 0)` em `ItemLancamento` — declarada também no
#    `Meta` do modelo, para o Django saber dela. Vale em SQLite e PostgreSQL.
#
# 3. SÓ EM POSTGRESQL (`RunPython` com guarda de `connection.vendor`, no-op
#    em SQLite — mesmo LIMITE ACEITO e declarado da 0009: produção nunca
#    roda SQLite, `config/settings.py` recusa subir assim com `DEBUG=False`):
#
#    a) Gatilhos BEFORE UPDATE OR DELETE em `LancamentoContabil` e
#       `ItemLancamento`, que espelham `save()`/`delete()` de
#       `apps/contabilidade/models.py` ("lançamento efetivado nunca se edita
#       nem se apaga; corrige-se por estorno"). Recusam também o DELETE em
#       cascata que o Django emitiria ao apagar um lançamento.
#
#       ÚNICA EXCEÇÃO, e só uma: `LancamentoContabil.competencia_id` de NULL
#       para um valor, SEM mudar nenhuma outra coluna na mesma instrução. É
#       o que o comando de gerência `backfill_lancamento_competencia`
#       (DL-016 F5) faz com `QuerySet.update(competencia=...)` para
#       preencher, nos lançamentos anteriores à DL-016 F2, a competência
#       que já deveria existir; `competencia_id` NOT NULL mudando para outro
#       valor continua recusado. A comparação "nenhuma outra coluna mudou"
#       usa `to_jsonb(NEW) - 'competencia_id' = to_jsonb(OLD) - ...`, que
#       cobre também colunas acrescentadas no futuro (uma coluna nova
#       nasce imutável, sem ninguém precisar lembrar de editar o gatilho).
#       A outra exceção cogitada — `criado_por_id` virar NULL pelo
#       `on_delete=SET_NULL` ao apagar um usuário — foi REMOVIDA por decisão
#       do Fred (30/09/2026): usuário se DESATIVA, não se apaga, e a
#       migração 0014 troca esse `on_delete` para PROTECT.
#
#    b) `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`, AFTER INSERT,
#       em `ItemLancamento` E em `LancamentoContabil`, que no COMMIT recusa
#       lançamento cujos débitos diferem dos créditos ou que não tenha ao
#       menos um débito e um crédito. Dispara nas DUAS tabelas porque só o
#       gatilho do item nunca dispararia para lançamento SEM nenhum item, e
#       `criar_lancamento` também recusa esse caso ("ao menos duas
#       partidas"). Espelha EXATAMENTE as regras de `criar_lancamento`:
#       `total_debito != total_credito` → recusa; `total_debito <= 0` →
#       recusa (com `valor > 0` em todo item, isso equivale a "ao menos um
#       débito e um crédito"). Não acrescenta regra nova: o teto de
#       partidas, a escala e a empresa da conta continuam só em Python.
#       É "adiado" porque os itens são gravados UM A UM, depois do
#       lançamento: no meio da transação o lote está legitimamente
#       incompleto, e só o fim dela pode julgar.
#
#       Custo: o gatilho do item roda por linha e faz uma agregação sobre o
#       lote (no máximo `LIMITE_PARTIDAS_POR_LANCAMENTO` linhas, indexadas
#       por `lancamento_id`); aceito em troca de não manter estado de
#       sessão entre linhas.
#
#    Limite declarado: `TRUNCATE` não aciona gatilhos de linha. Quem tem
#    privilégio de TRUNCATE ou de desabilitar gatilho (dono da tabela) está
#    fora do que o banco consegue impedir sozinho — restrição de papéis do
#    PostgreSQL é assunto de implantação, não desta migração.
#
# `RAISE ... USING ERRCODE = '23514', CONSTRAINT = '<nome>'`: é o que faz
# `IntegrityError.__cause__.diag.constraint_name` chegar ao Django com um
# nome ESTÁVEL (mesmo mecanismo da 0009), registrado em
# `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_GATILHO`. Nenhuma porta de
# escrita do produto alcança essas recusas (os serviços validam antes); o
# registro existe para que, se uma alcançar, o erro seja legível, e não um
# 500 cru.
#
# Sinal de porcentagem: `schema_editor.execute(sql, params=None)` NÃO passa a
# string por placeholders do driver, então `%` do `RAISE` do plpgsql pode ser
# escrito simples (a 0009 usa `%%` porque chama `execute` com `params=()`).
#
# Reversão: `migrate contabilidade 0012` remove os gatilhos, as funções e a
# constraint, sem perda de dado. A pré-conferência não tem reversão (é só
# leitura).

from django.db import migrations, models
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

_LIMITE_DE_LOTES_NA_MENSAGEM = 20


def _recusar_dado_que_viola_as_invariantes(apps, schema_editor):
    """Falha alto, nomeando os lotes, se o banco já contém dado que as novas
    restrições recusariam. NÃO corrige nada."""
    banco = schema_editor.connection.alias
    Item = apps.get_model("contabilidade", "ItemLancamento")
    Lancamento = apps.get_model("contabilidade", "LancamentoContabil")
    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))

    def _ids(consulta):
        ids = sorted(set(consulta))
        return ids[:_LIMITE_DE_LOTES_NA_MENSAGEM], len(ids)

    problemas = []

    nao_positivos, total = _ids(
        Item.objects.using(banco).filter(valor__lte=0).values_list("lancamento_id", flat=True)
    )
    if total:
        problemas.append(
            f"{total} lote(s) com item de valor menor ou igual a zero: {nao_positivos}"
        )

    sem_partidas, total = _ids(
        Lancamento.objects.using(banco).filter(itens__isnull=True).values_list("id", flat=True)
    )
    if total:
        problemas.append(f"{total} lançamento(s) sem nenhuma partida: {sem_partidas}")

    desequilibrados, total = _ids(
        Item.objects.using(banco)
        .values("lancamento_id")
        .annotate(
            debitos=Coalesce(Sum("valor", filter=Q(tipo="debito")), zero),
            creditos=Coalesce(Sum("valor", filter=Q(tipo="credito")), zero),
        )
        .filter(~Q(debitos=F("creditos")) | Q(debitos__lte=0) | Q(creditos__lte=0))
        .values_list("lancamento_id", flat=True)
    )
    if total:
        problemas.append(
            f"{total} lote(s) com débitos diferentes dos créditos ou sem um dos lados: "
            f"{desequilibrados}"
        )

    if problemas:
        raise RuntimeError(
            "DL-052: a migração 0013 não pode ser aplicada porque o banco já contém "
            "lançamentos que violam as invariantes do livro (nenhum dado foi alterado). "
            "Corrija cada lote por estorno/ajuste rastreável e repita. "
            + " | ".join(problemas)
            + " (números são o id do lançamento, o 'lote')."
        )


_CRIAR_GATILHOS_SQL = """
-- Imutabilidade: espelha LancamentoContabil.save/delete e
-- ItemLancamento.save/delete (apps/contabilidade/models.py).
CREATE OR REPLACE FUNCTION contabilidade_recusar_alteracao_do_livro()
RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_lancamentocontabil' THEN
        -- ÚNICA exceção: o backfill da competência (comando de gerência
        -- `backfill_lancamento_competencia`, DL-016 F5) preenche
        -- `competencia_id` de NULL para um valor e NÃO toca em mais nada.
        -- NOT NULL -> outro valor continua recusado.
        IF TG_OP = 'UPDATE'
           AND OLD.competencia_id IS NULL
           AND NEW.competencia_id IS NOT NULL
           AND (to_jsonb(NEW) - 'competencia_id') = (to_jsonb(OLD) - 'competencia_id')
        THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
            'Lançamento contábil efetivado não pode ser alterado nem excluído (% do lançamento %); '
            'registre um estorno.', TG_OP, OLD.id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_contabil_imutavel';
    END IF;

    RAISE EXCEPTION
        'Item de lançamento efetivado não pode ser alterado nem excluído (% do item %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'item_lancamento_imutavel';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lancamento_contabil_imutavel
    BEFORE UPDATE OR DELETE ON contabilidade_lancamentocontabil
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_recusar_alteracao_do_livro();

CREATE TRIGGER trg_item_lancamento_imutavel
    BEFORE UPDATE OR DELETE ON contabilidade_itemlancamento
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_recusar_alteracao_do_livro();

-- Partidas dobradas, julgadas no COMMIT: espelha as checagens de
-- `criar_lancamento` (débitos = créditos; total de débitos > 0).
CREATE OR REPLACE FUNCTION contabilidade_exigir_lancamento_balanceado()
RETURNS trigger AS $$
DECLARE
    v_lancamento_id bigint;
    v_debitos numeric;
    v_creditos numeric;
BEGIN
    IF TG_TABLE_NAME = 'contabilidade_itemlancamento' THEN
        v_lancamento_id := NEW.lancamento_id;
    ELSE
        v_lancamento_id := NEW.id;
    END IF;

    SELECT COALESCE(SUM(valor) FILTER (WHERE tipo = 'debito'), 0),
           COALESCE(SUM(valor) FILTER (WHERE tipo = 'credito'), 0)
      INTO v_debitos, v_creditos
      FROM contabilidade_itemlancamento
     WHERE lancamento_id = v_lancamento_id;

    IF v_debitos <> v_creditos THEN
        RAISE EXCEPTION
            'Lançamento %: débitos (%) e créditos (%) devem ser iguais.',
            v_lancamento_id, v_debitos, v_creditos
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_debito_igual_a_credito';
    END IF;

    IF v_debitos <= 0 THEN
        RAISE EXCEPTION
            'Lançamento %: precisa de ao menos um débito e um crédito de valor maior que zero.',
            v_lancamento_id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'lancamento_com_debito_e_credito';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_item_lancamento_balanceado
    AFTER INSERT ON contabilidade_itemlancamento
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_exigir_lancamento_balanceado();

CREATE CONSTRAINT TRIGGER trg_lancamento_contabil_balanceado
    AFTER INSERT ON contabilidade_lancamentocontabil
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_exigir_lancamento_balanceado();
"""

_REMOVER_GATILHOS_SQL = """
DROP TRIGGER IF EXISTS trg_lancamento_contabil_balanceado ON contabilidade_lancamentocontabil;
DROP TRIGGER IF EXISTS trg_item_lancamento_balanceado ON contabilidade_itemlancamento;
DROP TRIGGER IF EXISTS trg_item_lancamento_imutavel ON contabilidade_itemlancamento;
DROP TRIGGER IF EXISTS trg_lancamento_contabil_imutavel ON contabilidade_lancamentocontabil;
DROP FUNCTION IF EXISTS contabilidade_exigir_lancamento_balanceado();
DROP FUNCTION IF EXISTS contabilidade_recusar_alteracao_do_livro();
"""


def _criar_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_GATILHOS_SQL, params=None)


def _remover_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHOS_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0012_dl048_conta_classificacao_dlpa"),
    ]

    operations = [
        migrations.RunPython(_recusar_dado_que_viola_as_invariantes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="itemlancamento",
            constraint=models.CheckConstraint(
                condition=models.Q(("valor__gt", 0)),
                name="ck_itemlancamento_valor_positivo",
            ),
        ),
        migrations.RunPython(_criar_gatilhos, _remover_gatilhos),
    ]
