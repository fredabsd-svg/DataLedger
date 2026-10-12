"""DL-052 (A1) — as invariantes do livro-razão valem NO BANCO, não só em Python.

Antes desta etapa, `valor > 0`, débito = crédito e a imutabilidade do
lançamento só existiam em `criar_lancamento` e em `save()`/`delete()` dos
modelos. A análise de 30/09/2026 desbalanceou um lançamento com
`QuerySet.update(valor=...)` e apagou outro com `.delete()`, sem rastro.

Critérios do plano cobertos (números do plano):

3. `.update()`/`.delete()` em `LancamentoContabil` e `ItemLancamento` →
   `DatabaseError`, nada alterado (gatilhos BEFORE UPDATE OR DELETE).
4. `bulk_create` de itens desbalanceados, ou lançamento com um só lado/sem
   partidas → recusado no COMMIT (CONSTRAINT TRIGGER adiado); o lançamento
   balanceado de `criar_lancamento` e o estorno continuam funcionando.
5. Item com `valor <= 0` gravado por fora do serviço → recusado (CHECK).
8. A migração aplica em banco vazio e é reversível; com dado que viola as
   invariantes ela FALHA ALTO nomeando o lote, sem alterar nada.

Decisão do Fred (30/09/2026), exceções do gatilho de UPDATE: UMA só,
`competencia_id` NULL → preenchido, isolada (backfill da DL-016 F5).

Os testes de gatilho exigem PostgreSQL e são PULADOS em SQLite, com motivo
(a migração 0013 é no-op lá; mesmo limite aceito da 0009). O CHECK de `valor`
vale nos dois bancos. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.contabilidade.models import (
    Competencia,
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, estornar_lancamento
from apps.contabilidade.tests.gatilhos_do_livro import (
    BALANCEADO_ITEM,
    BALANCEADO_LANCAMENTO,
    IMUTAVEL_ITEM,
    IMUTAVEL_LANCAMENTO,
    gatilho_desligado,
    modelos_do_esquema,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason=(
        "Os gatilhos da migração 0013 (DL-052) existem só em PostgreSQL; em SQLite a "
        "invariante fica na aplicação (limite aceito, como na 0009)."
    ),
)


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-052 banco", cnpj="52525252000152")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-052 banco Ltda", cnpj="52525252000153"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {"empresa": empresa, "caixa": caixa, "capital": capital}


def _lancamento_valido(cenario, valor="100.00", data=date(2026, 3, 10)):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico="Lançamento válido",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _julgar_no_commit():
    """Faz o PostgreSQL julgar AGORA os gatilhos adiados — o que o COMMIT faz.
    Dentro do `TestCase` do pytest-django a transação do teste nunca comita;
    `check_constraints()` emite `SET CONSTRAINTS ALL IMMEDIATE`, a mesma
    avaliação. O teste de COMMIT real está mais abaixo (`transaction=True`)."""
    connection.check_constraints()


# ---------------------------------------------------------------------------
# Critério 3 — UPDATE e DELETE recusados
# ---------------------------------------------------------------------------


@so_postgresql
def test_update_de_valor_do_item_e_recusado_e_nada_muda(cenario):
    lancamento = _lancamento_valido(cenario)

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            ItemLancamento.objects.filter(lancamento=lancamento).update(valor=Decimal("1.00"))

    assert _nome_da_restricao(erro) == "item_lancamento_imutavel"
    assert sorted(i.valor for i in lancamento.itens.all()) == [Decimal("100.00")] * 2


@so_postgresql
def test_update_de_lancamento_e_recusado_e_nada_muda(cenario):
    lancamento = _lancamento_valido(cenario)

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(historico="Reescrito")

    assert _nome_da_restricao(erro) == "lancamento_contabil_imutavel"
    lancamento.refresh_from_db()
    assert lancamento.historico == "Lançamento válido"


@so_postgresql
def test_delete_em_massa_de_item_e_de_lancamento_e_recusado_e_nada_some(cenario):
    lancamento = _lancamento_valido(cenario)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            ItemLancamento.objects.filter(lancamento=lancamento).delete()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            # Emite DELETE dos itens (cascata) e do lançamento; o banco recusa.
            LancamentoContabil.objects.filter(pk=lancamento.pk).delete()

    assert LancamentoContabil.objects.filter(pk=lancamento.pk).exists()
    assert lancamento.itens.count() == 2


@so_postgresql
def test_sql_direto_tambem_e_recusado(cenario):
    lancamento = _lancamento_valido(cenario)

    for sql in (
        "UPDATE contabilidade_itemlancamento SET valor = 1 WHERE lancamento_id = %s",
        "DELETE FROM contabilidade_itemlancamento WHERE lancamento_id = %s",
        "UPDATE contabilidade_lancamentocontabil SET historico = 'x' WHERE id = %s",
        "DELETE FROM contabilidade_lancamentocontabil WHERE id = %s",
    ):
        with pytest.raises(DatabaseError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [lancamento.pk])

    assert lancamento.itens.count() == 2


@so_postgresql
def test_estorno_continua_funcionando_e_nao_altera_o_original(cenario):
    original = _lancamento_valido(cenario)

    estorno = estornar_lancamento(original)
    _julgar_no_commit()

    assert estorno.estorno_de_id == original.pk
    assert original.itens.count() == 2
    assert estorno.itens.count() == 2


# ---------------------------------------------------------------------------
# Exceção única do UPDATE: competencia_id NULL -> preenchido, ISOLADA
# ---------------------------------------------------------------------------


def _lancamento_sem_competencia(cenario):
    """Lançamento anterior à DL-016 F2: `competencia_id` NULL. Criado por
    `objects.create` (o serviço sempre preenche a competência)."""
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa"], data=date(2026, 3, 10), historico="Legado sem competência"
    )
    ItemLancamento.objects.bulk_create(
        [
            ItemLancamento(
                lancamento=lancamento,
                conta=cenario["caixa"],
                tipo=TipoPartida.DEBITO,
                valor=Decimal("10.00"),
            ),
            ItemLancamento(
                lancamento=lancamento,
                conta=cenario["capital"],
                tipo=TipoPartida.CREDITO,
                valor=Decimal("10.00"),
            ),
        ]
    )
    return lancamento


@so_postgresql
def test_backfill_da_competencia_passa_sozinho(cenario):
    lancamento = _lancamento_sem_competencia(cenario)
    competencia = Competencia.objects.create(empresa=cenario["empresa"], ano=2026, mes=3)

    atualizados = LancamentoContabil.objects.filter(pk=lancamento.pk).update(
        competencia=competencia
    )

    assert atualizados == 1
    lancamento.refresh_from_db()
    assert lancamento.competencia_id == competencia.pk


@so_postgresql
@pytest.mark.parametrize(
    "outra_coluna",
    [{"historico": "Reescrito junto"}, {"data": date(2026, 3, 11)}],
    ids=["com_historico", "com_data"],
)
def test_backfill_junto_com_outra_coluna_e_recusado(cenario, outra_coluna):
    lancamento = _lancamento_sem_competencia(cenario)
    competencia = Competencia.objects.create(empresa=cenario["empresa"], ano=2026, mes=3)

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(
                competencia=competencia, **outra_coluna
            )

    assert _nome_da_restricao(erro) == "lancamento_contabil_imutavel"
    lancamento.refresh_from_db()
    assert lancamento.competencia_id is None
    assert lancamento.historico == "Legado sem competência"


@so_postgresql
def test_competencia_ja_preenchida_nao_muda_para_outra(cenario):
    lancamento = _lancamento_valido(cenario)  # competência de março preenchida pelo serviço
    outra = Competencia.objects.create(empresa=cenario["empresa"], ano=2026, mes=4)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(competencia=outra)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(competencia=None)

    lancamento.refresh_from_db()
    assert lancamento.competencia_id != outra.pk
    assert lancamento.competencia_id is not None


@so_postgresql
def test_criado_por_para_nulo_nao_e_mais_excecao(cenario):
    """Decisão do Fred (30/09/2026): usuário se desativa, não se apaga. O
    `SET_NULL` de autoria não existe mais, e o banco recusa o UPDATE que o
    emitiria — aqui por SQL direto."""
    usuario = get_user_model().objects.create_user(
        username="autor-dl052", email="autor-dl052@escritorio.com.br", password="senha-forte-123"
    )
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Com autor",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("5.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("5.00")},
        ],
        criado_por=usuario,
    )

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contabilidade_lancamentocontabil SET criado_por_id = NULL WHERE id = %s",
                [lancamento.pk],
            )

    assert _nome_da_restricao(erro) == "lancamento_contabil_imutavel"
    lancamento.refresh_from_db()
    assert lancamento.criado_por_id == usuario.pk


def test_apagar_usuario_que_escriturou_e_recusado_pelo_orm(cenario):
    from django.db.models import ProtectedError

    usuario = get_user_model().objects.create_user(
        username="autor2-dl052", email="autor2-dl052@escritorio.com.br", password="senha-forte-123"
    )
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Com autor",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("5.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("5.00")},
        ],
        criado_por=usuario,
    )

    with pytest.raises(ProtectedError):
        with transaction.atomic():
            usuario.delete()

    assert get_user_model().objects.filter(pk=usuario.pk).exists()
    lancamento.refresh_from_db()
    assert lancamento.criado_por_id == usuario.pk


# ---------------------------------------------------------------------------
# Critério 4 — partidas dobradas julgadas no COMMIT
# ---------------------------------------------------------------------------


def _bulk_itens(cenario, lancamento, partidas, esquema=None):
    # `esquema`: registro histórico (`modelos_do_esquema`) quando a gravação acontece dentro
    # de uma janela de migração. Com `_id`, o mesmo código serve ao modelo atual e ao histórico.
    modelo_item = (
        ItemLancamento if esquema is None else esquema.get_model("contabilidade", "ItemLancamento")
    )
    modelo_item.objects.bulk_create(
        [
            modelo_item(
                lancamento_id=lancamento.pk,
                conta_id=cenario["caixa" if tipo == TipoPartida.DEBITO else "capital"].pk,
                tipo=tipo,
                valor=Decimal(valor),
            )
            for tipo, valor in partidas
        ]
    )


def _lancamento_nu(cenario, esquema=None):
    # `esquema`: ver `_bulk_itens`. DL-089 (0026): sem ele, dentro de uma janela anterior à
    # 0026 o INSERT do modelo atual mandaria a coluna `origem`, que a janela não tem.
    modelo = (
        LancamentoContabil
        if esquema is None
        else esquema.get_model("contabilidade", "LancamentoContabil")
    )
    return modelo.objects.create(
        empresa_id=cenario["empresa"].pk, data=date(2026, 3, 10), historico="Gravado por fora"
    )


@so_postgresql
def test_bulk_create_de_itens_desbalanceados_e_recusado_no_commit(cenario):
    lancamento = _lancamento_nu(cenario)
    _bulk_itens(
        cenario, lancamento, [(TipoPartida.DEBITO, "100.00"), (TipoPartida.CREDITO, "90.00")]
    )

    with pytest.raises(IntegrityError) as erro:
        _julgar_no_commit()

    assert _nome_da_restricao(erro) == "lancamento_debito_igual_a_credito"
    assert "100.00" in str(erro.value) and "90.00" in str(erro.value)


@so_postgresql
def test_lancamento_com_um_so_lado_e_recusado_no_commit(cenario):
    lancamento = _lancamento_nu(cenario)
    _bulk_itens(cenario, lancamento, [(TipoPartida.DEBITO, "30.00"), (TipoPartida.DEBITO, "70.00")])

    with pytest.raises(IntegrityError):
        _julgar_no_commit()


@so_postgresql
def test_lancamento_sem_nenhuma_partida_e_recusado_no_commit(cenario):
    _lancamento_nu(cenario)

    with pytest.raises(IntegrityError) as erro:
        _julgar_no_commit()

    assert _nome_da_restricao(erro) == "lancamento_com_debito_e_credito"


@so_postgresql
def test_bulk_create_balanceado_fora_do_servico_e_aceito(cenario):
    """O gatilho não inventa regra: lote com débito = crédito > 0, gravado por
    fora do serviço e em ordem qualquer (crédito antes do débito), é aceito."""
    lancamento = _lancamento_nu(cenario)
    _bulk_itens(
        cenario,
        lancamento,
        [
            (TipoPartida.CREDITO, "60.00"),
            (TipoPartida.DEBITO, "25.00"),
            (TipoPartida.CREDITO, "40.00"),
            (TipoPartida.DEBITO, "75.00"),
        ],
    )

    _julgar_no_commit()  # não levanta

    assert lancamento.itens.count() == 4


@so_postgresql
def test_criar_lancamento_do_servico_continua_funcionando(cenario):
    lancamento = _lancamento_valido(cenario)

    _julgar_no_commit()

    assert lancamento.itens.count() == 2


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_commit_real_recusa_lote_desbalanceado_e_nao_grava_nada(cenario):
    """Sem `check_constraints()`: é o COMMIT do `atomic` externo que julga."""
    antes = LancamentoContabil.objects.count()

    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            lancamento = _lancamento_nu(cenario)
            _bulk_itens(
                cenario,
                lancamento,
                [(TipoPartida.DEBITO, "100.00"), (TipoPartida.CREDITO, "99.99")],
            )

    assert _nome_da_restricao(erro) == "lancamento_debito_igual_a_credito"
    assert LancamentoContabil.objects.count() == antes
    assert ItemLancamento.objects.count() == 0


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_commit_real_aceita_lancamento_do_servico_e_estorno(cenario):
    original = _lancamento_valido(cenario)
    estorno = estornar_lancamento(original)

    assert LancamentoContabil.objects.filter(pk__in=[original.pk, estorno.pk]).count() == 2


# ---------------------------------------------------------------------------
# Critério 5 — valor > 0 no banco (vale em SQLite também)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["0.00", "-0.01", "-50.00"])
def test_item_com_valor_nao_positivo_gravado_por_fora_e_recusado(cenario, valor):
    with gatilho_desligado(BALANCEADO_LANCAMENTO, BALANCEADO_ITEM):
        lancamento = _lancamento_nu(cenario)
        with pytest.raises(IntegrityError) as erro:
            with transaction.atomic():
                ItemLancamento.objects.create(
                    lancamento=lancamento,
                    conta=cenario["caixa"],
                    tipo=TipoPartida.DEBITO,
                    valor=Decimal(valor),
                )

    assert _nome_da_restricao(erro) == "ck_itemlancamento_valor_positivo"
    assert ItemLancamento.objects.count() == 0


def test_item_com_menor_valor_positivo_e_aceito(cenario):
    with gatilho_desligado(BALANCEADO_LANCAMENTO, BALANCEADO_ITEM):
        lancamento = _lancamento_nu(cenario)
        ItemLancamento.objects.create(
            lancamento=lancamento,
            conta=cenario["caixa"],
            tipo=TipoPartida.DEBITO,
            valor=Decimal("0.01"),
        )

    assert ItemLancamento.objects.get().valor == Decimal("0.01")


# ---------------------------------------------------------------------------
# O recurso de teste (`gatilho_desligado`) é local e religa no fim
# ---------------------------------------------------------------------------


@so_postgresql
def test_gatilho_desligado_permite_dado_invalido_so_dentro_do_bloco(cenario):
    lancamento = _lancamento_valido(cenario)

    with gatilho_desligado(IMUTAVEL_ITEM, IMUTAVEL_LANCAMENTO, BALANCEADO_ITEM):
        ItemLancamento.objects.filter(lancamento=lancamento).update(valor=Decimal("1.00"))
        connection.check_constraints()  # nada enfileirado: sem erro

    # Religado: a mesma instrução volta a ser recusada.
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            ItemLancamento.objects.filter(lancamento=lancamento).update(valor=Decimal("2.00"))


# ---------------------------------------------------------------------------
# Critério 8 — migração: banco vazio, reversão, e falha alta com dado ruim
# ---------------------------------------------------------------------------

ANTERIOR = [("contabilidade", "0012_dl048_conta_classificacao_dlpa")]
ESTA = [("contabilidade", "0013_dl052_invariantes_do_livro_no_banco")]


def _gatilhos_do_livro():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgrelid IN ('contabilidade_lancamentocontabil'::regclass, "
            "'contabilidade_itemlancamento'::regclass)"
        )
        return {linha[0] for linha in cursor.fetchall()}


SQL_CONTA_CHECK_DE_VALOR = (
    "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_itemlancamento_valor_positivo'"
)

ESPERADOS = {
    "trg_lancamento_contabil_imutavel",
    "trg_item_lancamento_imutavel",
    "trg_item_lancamento_balanceado",
    "trg_lancamento_contabil_balanceado",
    # Rodada 1 (D2), migração 0016.
    "trg_lancamento_contabil_marca_transacao",
    "trg_item_lancamento_so_em_lancamento_novo",
}


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_migracao_e_reversivel_e_remove_gatilhos_e_constraint():
    from django.db.migrations.executor import MigrationExecutor

    alvo_atual = MigrationExecutor(connection).loader.graph.leaf_nodes("contabilidade")
    assert ESPERADOS <= _gatilhos_do_livro()
    try:
        MigrationExecutor(connection).migrate(ANTERIOR)

        assert not (ESPERADOS & _gatilhos_do_livro())
        with connection.cursor() as cursor:
            cursor.execute(SQL_CONTA_CHECK_DE_VALOR)
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT count(*) FROM pg_proc WHERE proname IN "
                "('contabilidade_recusar_alteracao_do_livro', "
                "'contabilidade_exigir_lancamento_balanceado', "
                "'contabilidade_marcar_lancamento_da_transacao', "
                "'contabilidade_item_so_em_lancamento_da_transacao')"
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_itemlancamento_tipo_valido'"
            )
            assert cursor.fetchone()[0] == 0
    finally:
        MigrationExecutor(connection).migrate(alvo_atual)

    assert ESPERADOS <= _gatilhos_do_livro()
    with connection.cursor() as cursor:
        cursor.execute(SQL_CONTA_CHECK_DE_VALOR)
        assert cursor.fetchone()[0] == 1


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_migracao_falha_alto_nomeando_o_lote_quando_o_banco_ja_tem_dado_invalido(cenario):
    from django.db.migrations.executor import MigrationExecutor

    alvo_atual = MigrationExecutor(connection).loader.graph.leaf_nodes("contabilidade")
    lote_ruim = None
    try:
        MigrationExecutor(connection).migrate(ANTERIOR)
        # Sem gatilho neste estado do esquema: monta o lote desbalanceado, com o modelo
        # HISTÓRICO do estado ANTERIOR (DL-089: o atual tem `origem`, que o esquema não tem).
        esquema = modelos_do_esquema(ANTERIOR)
        lote_ruim = _lancamento_nu(cenario, esquema=esquema)
        _bulk_itens(
            cenario,
            lote_ruim,
            [(TipoPartida.DEBITO, "100.00"), (TipoPartida.CREDITO, "90.00")],
            esquema=esquema,
        )

        with pytest.raises(RuntimeError) as erro:
            MigrationExecutor(connection).migrate(ESTA)

        mensagem = str(erro.value)
        assert "0013" in mensagem
        assert f"[{lote_ruim.pk}]" in mensagem
        assert "nenhum dado foi alterado" in mensagem
        # Nada mudou: os itens do lote ruim continuam como estavam e a migração
        # não foi registrada como aplicada.
        assert sorted(i.valor for i in lote_ruim.itens.all()) == [
            Decimal("90.00"),
            Decimal("100.00"),
        ]
        assert not (ESPERADOS & _gatilhos_do_livro())
    finally:
        # Limpeza: o dado ruim só pôde existir porque os gatilhos ainda não
        # existiam. A limpeza é em SQL puro, NÃO pelo ORM: nesta janela o
        # esquema está de volta a ANTERIOR, e o coletor do Django consultaria
        # tabelas das migrações POSTERIORES ao alvo — ex. as marcações da DMPL
        # (FK PROTECT sobre o lançamento, BL-605), que não existem aqui. Uma
        # falha nessa limpeza deixaria o esquema do banco de teste velho para o
        # resto da sessão e derrubaria os testes seguintes em cascata (foi
        # exatamente o que a CI do PR #79 mostrou). A restauração do esquema
        # fica garantida mesmo se a limpeza falhar.
        try:
            if lote_ruim is not None:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM contabilidade_itemlancamento WHERE lancamento_id = %s",
                        [lote_ruim.pk],
                    )
                    cursor.execute(
                        "DELETE FROM contabilidade_lancamentocontabil WHERE id = %s",
                        [lote_ruim.pk],
                    )
        finally:
            MigrationExecutor(connection).migrate(alvo_atual)

    assert ESPERADOS <= _gatilhos_do_livro()


# ---------------------------------------------------------------------------
# Rodada 1 de auditoria — D1: `tipo` só débito/crédito
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tipo_invalido", ["lixo", "DEBITO", "Credito", ""])
def test_d1_item_com_tipo_fora_de_debito_ou_credito_e_recusado_e_nada_e_gravado(
    cenario, tipo_invalido
):
    """Com o gatilho de partidas dobradas sozinho, o terceiro item (tipo
    inválido) era ignorado pela soma e o commit passava — Razão e Balancete
    divergiam. `transaction=True`: é o COMMIT real que julga."""
    antes = LancamentoContabil.objects.count()

    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            lancamento = _lancamento_nu(cenario)
            _bulk_itens(
                cenario,
                lancamento,
                [
                    (TipoPartida.DEBITO, "10.00"),
                    (TipoPartida.CREDITO, "10.00"),
                    (tipo_invalido, "5000.00"),
                ],
            )

    assert _nome_da_restricao(erro) == "ck_itemlancamento_tipo_valido"
    assert LancamentoContabil.objects.count() == antes
    assert ItemLancamento.objects.count() == 0


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d1_migracao_0015_falha_alto_nomeando_o_lote_com_tipo_invalido(cenario):
    from django.db.migrations.executor import MigrationExecutor

    antes_da_0015 = [("contabilidade", "0014_dl052_autoria_protegida")]
    ate_a_0015 = [("contabilidade", "0015_dl052_r1_tipo_do_item_valido")]
    alvo_atual = MigrationExecutor(connection).loader.graph.leaf_nodes("contabilidade")
    lote_ruim = None
    try:
        MigrationExecutor(connection).migrate(antes_da_0015)
        # Modelo histórico do estado ANTERIOR à 0015 (DL-089: ver o teste acima).
        esquema = modelos_do_esquema(antes_da_0015)
        with transaction.atomic():
            lote_ruim = _lancamento_nu(cenario, esquema=esquema)
            _bulk_itens(
                cenario,
                lote_ruim,
                [
                    (TipoPartida.DEBITO, "10.00"),
                    (TipoPartida.CREDITO, "10.00"),
                    ("lixo", "5.00"),
                ],
                esquema=esquema,
            )

        with pytest.raises(RuntimeError) as erro:
            MigrationExecutor(connection).migrate(ate_a_0015)

        assert "0015" in str(erro.value)
        assert f"[{lote_ruim.pk}]" in str(erro.value)
        assert "nenhum dado foi alterado" in str(erro.value)
        assert lote_ruim.itens.filter(tipo="lixo").exists()
    finally:
        # Limpeza em SQL puro, NÃO pelo ORM (mesma razão do teste acima: na
        # janela com o esquema em antes_da_0015, o coletor do Django consultaria
        # tabelas de migrações posteriores — as marcações da DMPL, BL-605 — que
        # não existem aqui, e uma falha na limpeza deixaria o esquema do banco
        # de teste velho para o resto da sessão). Os gatilhos de imutabilidade
        # continuam desligados durante a limpeza, e a restauração do esquema é
        # garantida mesmo se a limpeza falhar.
        try:
            if lote_ruim is not None:
                with gatilho_desligado(IMUTAVEL_ITEM, IMUTAVEL_LANCAMENTO):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM contabilidade_itemlancamento WHERE lancamento_id = %s",
                            [lote_ruim.pk],
                        )
                        cursor.execute(
                            "DELETE FROM contabilidade_lancamentocontabil WHERE id = %s",
                            [lote_ruim.pk],
                        )
        finally:
            MigrationExecutor(connection).migrate(alvo_atual)


# ---------------------------------------------------------------------------
# Rodada 1 de auditoria — D2: partida nova só em lançamento da MESMA transação
# ---------------------------------------------------------------------------

MARCADOR = "dataledger.lancamentos_da_transacao"


def _marcador_atual():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [MARCADOR])
        return cursor.fetchone()[0] or ""


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d2_par_balanceado_em_transacao_posterior_e_recusado_e_o_lancamento_fica_intacto(
    cenario,
):
    lancamento = _lancamento_valido(cenario)  # efetivado e comitado
    assert lancamento.itens.count() == 2

    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            _bulk_itens(
                cenario,
                lancamento,
                [(TipoPartida.DEBITO, "7.00"), (TipoPartida.CREDITO, "7.00")],
            )

    assert _nome_da_restricao(erro) == "item_lancamento_em_lancamento_efetivado"
    assert sorted(i.valor for i in lancamento.itens.all()) == [Decimal("100.00")] * 2


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d2_criar_lancamento_estorno_e_bulk_create_na_mesma_transacao_seguem_funcionando(
    cenario,
):
    original = _lancamento_valido(cenario)
    estorno = estornar_lancamento(original)
    with transaction.atomic():
        novo = _lancamento_nu(cenario)
        _bulk_itens(
            cenario,
            novo,
            [(TipoPartida.DEBITO, "3.00"), (TipoPartida.CREDITO, "3.00")],
        )

    assert estorno.itens.count() == 2
    assert novo.itens.count() == 2


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d2_lancamento_criado_em_savepoint_aceita_itens_no_savepoint_e_depois_dele(cenario):
    with transaction.atomic():
        with transaction.atomic():  # savepoint do lançamento
            lancamento = _lancamento_nu(cenario)
            _bulk_itens(
                cenario,
                lancamento,
                [(TipoPartida.DEBITO, "4.00"), (TipoPartida.CREDITO, "4.00")],
            )
        # savepoint liberado; ainda na transação externa: par extra balanceado
        _bulk_itens(
            cenario,
            lancamento,
            [(TipoPartida.DEBITO, "6.00"), (TipoPartida.CREDITO, "6.00")],
        )

    assert lancamento.itens.count() == 4
    # Comitado: agora está efetivado, e partida nova é recusada.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _bulk_itens(
                cenario,
                lancamento,
                [(TipoPartida.DEBITO, "1.00"), (TipoPartida.CREDITO, "1.00")],
            )


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d2_savepoint_revertido_nao_deixa_id_fantasma_no_marcador(cenario):
    efetivado = _lancamento_valido(cenario)

    class _Desfazer(Exception):
        pass

    fantasma = None
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            try:
                with transaction.atomic():
                    fantasma = _lancamento_nu(cenario)
                    assert f",{fantasma.pk}," in _marcador_atual()
                    raise _Desfazer
            except _Desfazer:
                pass
            # Revertido: o id desfeito saiu do marcador, e o efetivado nunca esteve.
            assert f",{fantasma.pk}," not in _marcador_atual()
            _bulk_itens(
                cenario,
                efetivado,
                [(TipoPartida.DEBITO, "2.00"), (TipoPartida.CREDITO, "2.00")],
            )

    assert _nome_da_restricao(erro) == "item_lancamento_em_lancamento_efetivado"
    assert efetivado.itens.count() == 2
    assert not LancamentoContabil.objects.filter(pk=fantasma.pk).exists()


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_d2_marcador_some_no_fim_da_transacao(cenario):
    with transaction.atomic():
        lancamento = _lancamento_nu(cenario)
        assert f",{lancamento.pk}," in _marcador_atual()
        _bulk_itens(
            cenario,
            lancamento,
            [(TipoPartida.DEBITO, "1.00"), (TipoPartida.CREDITO, "1.00")],
        )

    assert f",{lancamento.pk}," not in _marcador_atual()


# ---------------------------------------------------------------------------
# Rodada 1 de auditoria — D3: backfill só com competência da MESMA empresa
# ---------------------------------------------------------------------------


@so_postgresql
def test_d3_backfill_com_competencia_de_outra_empresa_e_recusado(cenario):
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["empresa"].escritorio,
        razao_social="Outra empresa DL-052 Ltda",
        cnpj="52525252000154",
    )
    competencia_alheia = Competencia.objects.create(empresa=outra_empresa, ano=2026, mes=3)
    lancamento = _lancamento_sem_competencia(cenario)

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(
                competencia=competencia_alheia
            )

    assert _nome_da_restricao(erro) == "lancamento_contabil_imutavel"
    lancamento.refresh_from_db()
    assert lancamento.competencia_id is None
