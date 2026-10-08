"""DL-069, fatia 2 — mês encerrado recusa INSERT de lançamento no banco.

Antes desta fatia, a trava de mês encerrado (e do encadeamento do carnê-leão,
DL-054) só existia em `criar_lancamento_caixa`. Um `objects.create()`, um
`bulk_create()` ou um SQL direto gravavam lançamento em mês fechado — mudando o
carnê-leão já entregue sem rastro. A migração 0012 cria o gatilho, no mesmo
padrão da 0011 (fatia 1, imutabilidade) e da 0013 da contabilidade.

Critérios do plano cobertos (números do plano da fatia 2):

2. INSERT de `LancamentoCaixa` é recusado pelo BANCO (`IntegrityError`
   nomeando a restrição), por ORM e por SQL direto, com o dado intacto, quando
   o mês do lançamento está encerrado, quando um mês POSTERIOR do mesmo ano
   está encerrado (encadeamento da DL-054) e no estorno de mês encerrado.
5. Continua permitido: lançar e estornar em mês aberto, encerrar, reabrir e a
   reabertura em cascata da DL-054.
6. A restrição está registrada em `MENSAGENS_DE_RESTRICAO_DE_GATILHO` e o
   tradutor `restricao_como_400` converte a recusa real do banco.
8. Cenários negativos e mutação: sem o gatilho, a escrita passa.
10/11. Migração reversível e no-op declarado fora do PostgreSQL.

Os testes de gatilho exigem PostgreSQL e são PULADOS em SQLite, com motivo
declarado (a migração é no-op lá — mesmo limite aceito da 0009/0011). A prova
dos gatilhos é da CI (`postgres:16-alpine`). Dados sintéticos.
"""

# ruff: noqa: F811
# (as fixtures importadas são usadas como parâmetro, o padrão do repositório)
import importlib
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.contabilidade.tests.gatilhos_do_livro import gatilho_desligado
from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO_DE_GATILHO,
    RestricaoViolada,
    mensagens_de_gatilho,
    restricao_como_400,
)
from apps.livro_caixa.models import EstadoMesCaixa, FechamentoMesCaixa, LancamentoCaixa
from apps.livro_caixa.services import estornar_lancamento_caixa, reabrir_mes_caixa_em_cascata
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (  # noqa: F401
    _encerrar,
    _lancar,
    cenario,
)

pytestmark = pytest.mark.django_db

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason=(
        "O gatilho da migração 0012 (DL-069, fatia 2) existe só em PostgreSQL; em SQLite a "
        "trava de mês fica na aplicação (limite aceito, como na 0009, 0011 e 0013)."
    ),
)

TABELA_LANCAMENTO = LancamentoCaixa._meta.db_table

GATILHO_INSERT_LANCAMENTO = (TABELA_LANCAMENTO, "trg_lancamento_caixa_so_em_mes_aberto")
RESTRICAO_LANCAMENTO = "dl069_lancamento_caixa_so_em_mes_aberto"


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _recusado(restricao, operacao):
    """Executa `operacao()` dentro de um savepoint e exige a recusa do gatilho."""
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            operacao()
    assert _nome_da_restricao(erro) == restricao


def _sql(sql, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parametros)


def _linha(modelo, pk):
    """Todas as colunas da linha, para provar que NADA mudou depois da recusa."""
    return modelo.objects.filter(pk=pk).values().get()


def _lancamento_direto(cenario, *, data, estorno_de=None, historico="Direto pelo ORM"):
    """Lançamento de caixa gravado por FORA de `criar_lancamento_caixa`."""
    return LancamentoCaixa.objects.create(
        empresa=cenario["empresa"],
        conta=cenario["conta"],
        data=data,
        valor=Decimal("25.00"),
        historico=historico,
        estorno_de=estorno_de,
    )


# ---------------------------------------------------------------------------
# Critério 2 — mês encerrado e encadeamento do ano recusam o INSERT
# ---------------------------------------------------------------------------


@so_postgresql
def test_orm_create_em_mes_encerrado_e_recusado_e_nada_entra(cenario):
    fechamento = _encerrar(cenario, ano=2026, mes=3)
    assert fechamento.estado == EstadoMesCaixa.ENCERRADO
    antes = LancamentoCaixa.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 10)),
    )

    assert LancamentoCaixa.objects.count() == antes


@so_postgresql
def test_sql_direto_em_mes_encerrado_e_recusado_e_nada_entra(cenario):
    _encerrar(cenario, ano=2026, mes=3)
    antes = LancamentoCaixa.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _sql(
            f"INSERT INTO {TABELA_LANCAMENTO} (empresa_id, conta_id, data, valor, historico, "
            "documento_origem, cpf_titular_pagamento, cpf_beneficiario_servico, "
            "cpf_beneficiario_nao_informado, cnpj_pagador, criado_em) "
            "VALUES (%s, %s, %s, %s, %s, '', '', '', false, '', %s)",
            [
                cenario["empresa"].pk,
                cenario["conta"].pk,
                date(2026, 3, 10),
                Decimal("25.00"),
                "SQL direto",
                timezone.now(),
            ],
        ),
    )

    assert LancamentoCaixa.objects.count() == antes


@so_postgresql
def test_encadeamento_insert_anterior_a_mes_encerrado_do_mesmo_ano_e_recusado(cenario):
    """DL-054 (RC-148): o carnê-leão se encadeia de janeiro a dezembro — um
    lançamento em janeiro muda o resultado de fevereiro, e fevereiro encerrado
    é resultado entregue que não pode mudar em silêncio."""
    _encerrar(cenario, ano=2026, mes=2)
    antes = LancamentoCaixa.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 1, 10)),
    )
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _sql(
            f"INSERT INTO {TABELA_LANCAMENTO} (empresa_id, conta_id, data, valor, historico, "
            "documento_origem, cpf_titular_pagamento, cpf_beneficiario_servico, "
            "cpf_beneficiario_nao_informado, cnpj_pagador, criado_em) "
            "VALUES (%s, %s, %s, %s, %s, '', '', '', false, '', %s)",
            [
                cenario["empresa"].pk,
                cenario["conta"].pk,
                date(2026, 1, 11),
                Decimal("25.00"),
                "SQL direto",
                timezone.now(),
            ],
        ),
    )

    assert LancamentoCaixa.objects.count() == antes


@so_postgresql
def test_estorno_em_mes_encerrado_e_recusado(cenario):
    """A data do estorno é a do original (DE-091 item 4), então estornar
    lançamento de mês encerrado exige reabrir o mês primeiro (RC-130) — a
    mesma regra do lançamento comum, com a frase própria de estorno."""
    original = _lancar(cenario, date(2026, 3, 10))
    _encerrar(cenario, ano=2026, mes=3)
    antes = LancamentoCaixa.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(
            cenario, data=date(2026, 3, 10), estorno_de=original, historico="Estorno direto"
        ),
    )

    assert LancamentoCaixa.objects.count() == antes


@so_postgresql
def test_mes_encerrado_de_outro_ano_nao_recusa(cenario):
    """Limite do encadeamento: ele é ANUAL. Dezembro/2025 encerrado não
    bloqueia janeiro/2026 (a virada do ano isola)."""
    _encerrar(cenario, ano=2025, mes=12)

    lancamento = _lancamento_direto(cenario, data=date(2026, 1, 10))

    assert LancamentoCaixa.objects.filter(pk=lancamento.pk).exists()


@so_postgresql
def test_mes_encerrado_anterior_nao_bloqueia_o_posterior(cenario):
    """Limite do encadeamento: só mês POSTERIOR encerrado bloqueia o anterior.
    Janeiro encerrado não impede lançamento em março."""
    _encerrar(cenario, ano=2026, mes=1)

    lancamento = _lancamento_direto(cenario, data=date(2026, 3, 10))

    assert LancamentoCaixa.objects.filter(pk=lancamento.pk).exists()


# ---------------------------------------------------------------------------
# Critério 5 — o ciclo do produto continua funcionando (gatilho LIGADO)
# ---------------------------------------------------------------------------


def test_lancar_estornar_encerrar_reabrir_cascata_e_reencerrar_continuam_funcionando(cenario):
    """O ciclo inteiro de escrita do livro-caixa pelos serviços — a prova de
    que o gatilho não recusa nenhum caminho legítimo."""
    original = _lancar(cenario, date(2026, 1, 10))
    estorno = estornar_lancamento_caixa(original, criado_por=cenario["gestor"])
    assert estorno.estorno_de_id == original.pk

    for mes in (1, 2, 3):
        _encerrar(cenario, ano=2026, mes=mes)
    assert {f.mes: f.estado for f in FechamentoMesCaixa.objects.all()} == {
        1: EstadoMesCaixa.ENCERRADO,
        2: EstadoMesCaixa.ENCERRADO,
        3: EstadoMesCaixa.ENCERRADO,
    }

    # Cascata da DL-054: janeiro reabre junto com fevereiro e março.
    reabertos = reabrir_mes_caixa_em_cascata(
        empresa=cenario["empresa"],
        ano=2026,
        mes=1,
        usuario=cenario["gestor"],
        motivo="Corrigir despesa de janeiro lançada a menos",
        meses_confirmados={(2026, 2), (2026, 3)},
    )
    assert [f.mes for f in reabertos] == [1, 2, 3]

    # Mês reaberto aceita lançamento e estorno de novo (RC-103).
    novo = _lancar(cenario, date(2026, 1, 20), valor="30.00")
    estornar_lancamento_caixa(novo, criado_por=cenario["gestor"])

    _encerrar(cenario, ano=2026, mes=1)
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa"]).count() == 4


# ---------------------------------------------------------------------------
# Critério 6 — a recusa vira mensagem em português pelo tradutor do projeto
# ---------------------------------------------------------------------------


def test_a_restricao_da_fatia_2_esta_registrada_em_portugues():
    mensagem = MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_LANCAMENTO]
    assert mensagem.strip() and mensagem.endswith(".")
    # Sem jargão de banco: o contador lê esta frase.
    assert not {"trigger", "gatilho", "constraint", "SQL"} & set(mensagem.split())
    assert "carnê-leão" in mensagem  # o encadeamento da DL-054 é a segunda metade da regra
    # `mensagens_de_gatilho` levanta KeyError para nome fora do registro: é a
    # prova de que o nome que a migração grava é o que o tradutor procura.
    assert set(mensagens_de_gatilho(RESTRICAO_LANCAMENTO)) == {RESTRICAO_LANCAMENTO}


@so_postgresql
def test_o_tradutor_converte_a_recusa_real_do_banco_na_mensagem_registrada(cenario):
    _encerrar(cenario, ano=2026, mes=3)

    with pytest.raises(RestricaoViolada) as erro:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            _lancamento_direto(cenario, data=date(2026, 3, 10))

    assert erro.value.nome == RESTRICAO_LANCAMENTO
    assert str(erro.value) == MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_LANCAMENTO]


# ---------------------------------------------------------------------------
# Critério 8 — mutação: sem o gatilho, os testes de recusa caem
# ---------------------------------------------------------------------------


@so_postgresql
def test_sem_o_gatilho_a_escrita_em_mes_encerrado_passa(cenario):
    _encerrar(cenario, ano=2026, mes=3)

    with gatilho_desligado(GATILHO_INSERT_LANCAMENTO):
        lancamento = _lancamento_direto(cenario, data=date(2026, 3, 10))
        assert LancamentoCaixa.objects.filter(pk=lancamento.pk).exists()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 11)),
    )


# ---------------------------------------------------------------------------
# Critérios 10/11 — migração reversível; SQLite é no-op declarado
# ---------------------------------------------------------------------------

ANTERIOR = [("livro_caixa", "0011_dl069_livro_caixa_imutavel_no_banco")]
ESTA = "0012_dl069_mes_encerrado_recusa_insert"

GATILHOS_ESPERADOS = {"trg_lancamento_caixa_so_em_mes_aberto"}
FUNCOES_ESPERADAS = {"livro_caixa_recusar_lancamento_em_mes_encerrado"}


def _gatilhos_da_fatia_2():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            f"AND tgrelid = '{TABELA_LANCAMENTO}'::regclass"
        )
        return {linha[0] for linha in cursor.fetchall()}


def _funcoes_da_fatia_2():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT proname FROM pg_proc WHERE proname = ANY(%s)", [list(FUNCOES_ESPERADAS)]
        )
        return {linha[0] for linha in cursor.fetchall()}


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_migracao_e_reversivel_e_depois_de_voltar_a_escrita_passa(cenario):
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    alvo_atual = executor.loader.graph.leaf_nodes("livro_caixa")
    assert ("livro_caixa", ESTA) in executor.loader.applied_migrations
    assert GATILHOS_ESPERADOS <= _gatilhos_da_fatia_2()
    assert _funcoes_da_fatia_2() == FUNCOES_ESPERADAS

    _encerrar(cenario, ano=2026, mes=3)

    try:
        MigrationExecutor(connection).migrate(ANTERIOR)

        assert not (GATILHOS_ESPERADOS & _gatilhos_da_fatia_2())
        assert _funcoes_da_fatia_2() == set()
        # Sem o gatilho, o INSERT passa — é o que prova que era ele quem
        # recusava (a mutação derruba os testes de recusa acima).
        lancamento = _lancamento_direto(cenario, data=date(2026, 3, 10))
        assert LancamentoCaixa.objects.filter(pk=lancamento.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(alvo_atual)

    # Para a frente de novo: gatilho de volta e a recusa volta junto.
    assert GATILHOS_ESPERADOS <= _gatilhos_da_fatia_2()
    assert _funcoes_da_fatia_2() == FUNCOES_ESPERADAS
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 11)),
    )


def test_a_migracao_e_no_op_fora_do_postgresql():
    """Critério 10: em SQLite as travas não existem, e a migração declara isso
    por não emitir SQL nenhum — nem na ida, nem na volta. Vale em qualquer
    banco (não é um teste de gatilho; é do no-op)."""
    migracao = importlib.import_module(f"apps.livro_caixa.migrations.{ESTA}")

    class _Conexao:
        vendor = "sqlite"

    class _EditorQueNaoDeveExecutar:
        connection = _Conexao()

        def execute(self, *args, **kwargs):
            raise AssertionError("a migração emitiu SQL fora do PostgreSQL")

    editor = _EditorQueNaoDeveExecutar()
    migracao._criar_gatilho(None, editor)
    migracao._remover_gatilho(None, editor)
